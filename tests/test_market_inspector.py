"""v3.23.37 — MarketInspector analyzer pin tests.

Covers:
  * Per-TF analysis math (BB position, z-score, extreme flags)
  * Score-market ladder (HIGH / MEDIUM / LOW / WATCHLIST / NONE)
  * Pearson correlation on returns
  * Opposing-pair filter (in-window vs out-of-window)
  * scan_universe wiring end-to-end
  * Module-level shared inspector singleton
"""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# --- Candle stub matching ta_engine.Candle enough for the analyzer -----


@dataclass
class _StubCandle:
    open: float
    high: float
    low: float
    close: float
    volume: float = 100.0
    timestamp: int = 0


def _make_flat_series(price: float, n: int = 25):
    """Flat price series → std dev is 0 → analyzer returns None."""
    return [_StubCandle(price, price, price, price) for _ in range(n)]


def _make_upper_extreme_series(n: int = 25):
    """Series that ends near the upper Bollinger band with high z-score."""
    # Baseline around 100, last candle spikes to 130.
    out = [_StubCandle(100 + (i % 2), 101, 99, 100 + (i % 2)) for i in range(n - 1)]
    out.append(_StubCandle(130, 131, 129, 130))
    return out


def _make_lower_extreme_series(n: int = 25):
    """Series that ends near the lower Bollinger band with low z-score."""
    out = [_StubCandle(100 + (i % 2), 101, 99, 100 + (i % 2)) for i in range(n - 1)]
    out.append(_StubCandle(70, 71, 69, 70))
    return out


# --- Analyzer imports (require ta_engine) ------------------------------

from src.trading.market_inspector import (  # noqa: E402
    MarketInspector,
    MarketSignal,
    OpposingPair,
    TimeframeAnalysis,
    SIGNAL_ENTRY_LONG_HIGH,
    SIGNAL_ENTRY_LONG_MEDIUM,
    SIGNAL_ENTRY_LONG_LOW,
    SIGNAL_ENTRY_SHORT_HIGH,
    SIGNAL_ENTRY_SHORT_MEDIUM,
    SIGNAL_ENTRY_SHORT_LOW,
    SIGNAL_WATCHLIST,
    SIGNAL_NONE,
    HTF_TIMEFRAMES,
    get_shared_inspector,
)


class TestConstants:
    def test_timeframes_are_d_w_m(self):
        assert HTF_TIMEFRAMES == ("1d", "1w", "1M")

    def test_signal_constants_distinct(self):
        # Sanity — every signal constant is a distinct string.
        constants = {
            SIGNAL_ENTRY_LONG_HIGH,
            SIGNAL_ENTRY_LONG_MEDIUM,
            SIGNAL_ENTRY_LONG_LOW,
            SIGNAL_ENTRY_SHORT_HIGH,
            SIGNAL_ENTRY_SHORT_MEDIUM,
            SIGNAL_ENTRY_SHORT_LOW,
            SIGNAL_WATCHLIST,
            SIGNAL_NONE,
        }
        assert len(constants) == 8


class TestPerTfAnalysis:
    def test_flat_series_returns_none(self):
        """Zero standard deviation → analyzer refuses (no meaningful BB)."""
        insp = MarketInspector()
        a = insp._analyze_tf("1d", _make_flat_series(100, 25))
        assert a is None

    def test_short_series_returns_none(self):
        insp = MarketInspector()
        a = insp._analyze_tf("1d", _make_upper_extreme_series(10))
        assert a is None

    def test_upper_extreme_detected(self):
        insp = MarketInspector(z_threshold=1.5)
        a = insp._analyze_tf("1d", _make_upper_extreme_series(25))
        assert a is not None
        assert a.at_upper_extreme is True
        assert a.at_lower_extreme is False
        assert a.z_score > 1.5
        assert a.bb_position > 0.80

    def test_lower_extreme_detected(self):
        insp = MarketInspector(z_threshold=1.5)
        a = insp._analyze_tf("1d", _make_lower_extreme_series(25))
        assert a is not None
        assert a.at_lower_extreme is True
        assert a.at_upper_extreme is False
        assert a.z_score < -1.5
        assert a.bb_position < 0.20

    def test_tf_label_preserved(self):
        insp = MarketInspector()
        a = insp._analyze_tf("1w", _make_upper_extreme_series(25))
        assert a is not None
        assert a.tf == "1w"


class TestScoreMarket:
    def _mk_analysis(self, tf, at_lower=False, at_upper=False, tight=False):
        return TimeframeAnalysis(
            tf=tf,
            bb_position=0.1 if at_lower else 0.9 if at_upper else 0.5,
            z_score=-2.0 if at_lower else 2.0 if at_upper else 0.0,
            at_lower_extreme=at_lower,
            at_upper_extreme=at_upper,
            tightening=tight,
        )

    def test_none_signal_on_no_extremes(self):
        insp = MarketInspector()
        per_tf = {
            "1d": self._mk_analysis("1d"),
            "1w": self._mk_analysis("1w"),
            "1M": self._mk_analysis("1M"),
        }
        sig = insp._score_market("XYZ", per_tf, is_active=False)
        assert sig.signal == SIGNAL_NONE
        assert sig.score == 0.0

    def test_three_lower_plus_tightening_gives_high(self):
        insp = MarketInspector()
        per_tf = {
            tf: self._mk_analysis(tf, at_lower=True, tight=True)
            for tf in ("1d", "1w", "1M")
        }
        sig = insp._score_market("BTC", per_tf, is_active=False)
        assert sig.signal == SIGNAL_ENTRY_LONG_HIGH
        assert sig.score == pytest.approx(0.9)
        assert sig.direction == "long"

    def test_three_lower_no_tightening_gives_medium(self):
        insp = MarketInspector()
        per_tf = {
            tf: self._mk_analysis(tf, at_lower=True, tight=False)
            for tf in ("1d", "1w", "1M")
        }
        sig = insp._score_market("BTC", per_tf, is_active=False)
        assert sig.signal == SIGNAL_ENTRY_LONG_MEDIUM
        assert sig.score == pytest.approx(0.6)

    def test_two_of_three_lower_plus_tightening_medium(self):
        insp = MarketInspector()
        per_tf = {
            "1d": self._mk_analysis("1d", at_lower=True, tight=True),
            "1w": self._mk_analysis("1w", at_lower=True, tight=False),
            "1M": self._mk_analysis("1M"),
        }
        sig = insp._score_market("BTC", per_tf, is_active=False)
        assert sig.signal == SIGNAL_ENTRY_LONG_MEDIUM
        assert sig.direction == "long"

    def test_two_of_three_lower_no_tightening_low(self):
        insp = MarketInspector()
        per_tf = {
            "1d": self._mk_analysis("1d", at_lower=True, tight=False),
            "1w": self._mk_analysis("1w", at_lower=True, tight=False),
            "1M": self._mk_analysis("1M"),
        }
        sig = insp._score_market("BTC", per_tf, is_active=False)
        assert sig.signal == SIGNAL_ENTRY_LONG_LOW
        assert sig.score == pytest.approx(0.35)

    def test_three_upper_plus_tightening_gives_short_high(self):
        insp = MarketInspector()
        per_tf = {
            tf: self._mk_analysis(tf, at_upper=True, tight=True)
            for tf in ("1d", "1w", "1M")
        }
        sig = insp._score_market("ETH", per_tf, is_active=False)
        assert sig.signal == SIGNAL_ENTRY_SHORT_HIGH
        assert sig.direction == "short"

    def test_watchlist_on_tightening_without_extreme(self):
        insp = MarketInspector()
        per_tf = {
            "1d": self._mk_analysis("1d", tight=True),
            "1w": self._mk_analysis("1w"),
            "1M": self._mk_analysis("1M"),
        }
        sig = insp._score_market("BTC", per_tf, is_active=False)
        assert sig.signal == SIGNAL_WATCHLIST
        assert sig.score == pytest.approx(0.15)

    def test_active_flag_preserved(self):
        insp = MarketInspector()
        per_tf = {
            tf: self._mk_analysis(tf, at_lower=True, tight=True)
            for tf in ("1d", "1w", "1M")
        }
        sig = insp._score_market("BTC", per_tf, is_active=True)
        assert sig.is_active is True


class TestPearson:
    def test_perfect_positive(self):
        c = MarketInspector._pearson([1, 2, 3, 4], [1, 2, 3, 4])
        assert c == pytest.approx(1.0)

    def test_perfect_negative(self):
        c = MarketInspector._pearson([1, 2, 3, 4], [4, 3, 2, 1])
        assert c == pytest.approx(-1.0)

    def test_no_correlation(self):
        # xs varies, ys constant → correlation undefined → 0.0
        c = MarketInspector._pearson([1, 2, 3, 4], [5, 5, 5, 5])
        assert c == 0.0

    def test_too_short_returns_zero(self):
        c = MarketInspector._pearson([1, 2], [2, 1])
        assert c == 0.0


class TestOpposingPairs:
    @staticmethod
    def _build_series(start: float, step_sign: int):
        """Build a close series whose alternating returns are ±5 % / ±4 %.
        ``step_sign=+1`` → up 5 %, down 4 %, repeat.
        ``step_sign=-1`` → down 5 %, up 4 %, repeat (inverse).
        Produces 11 closes / 10 returns; enough for the 10-point minimum."""
        closes = [start]
        for i in range(10):
            pct = 0.05 if (i % 2 == 0) else 0.04
            direction = step_sign if (i % 2 == 0) else -step_sign
            closes.append(closes[-1] * (1 + direction * pct))
        return closes

    def test_pair_in_window_kept(self):
        insp = MarketInspector(corr_negative_max=-0.3, corr_negative_min=-1.0)
        long_sig = MarketSignal(
            symbol="A", signal=SIGNAL_ENTRY_LONG_MEDIUM, score=0.6, direction="long"
        )
        short_sig = MarketSignal(
            symbol="B", signal=SIGNAL_ENTRY_SHORT_MEDIUM, score=0.6, direction="short"
        )
        # A returns [+5, -4, +5, -4, …]; B returns [-5, +4, -5, +4, …].
        # Pearson of these two ten-return vectors is exactly −1.
        closes_by_sym = {
            "A": self._build_series(100, +1),
            "B": self._build_series(100, -1),
        }
        pairs = insp._find_opposing_pairs([long_sig, short_sig], closes_by_sym)
        assert len(pairs) == 1
        assert pairs[0].long_side.symbol == "A"
        assert pairs[0].short_side.symbol == "B"
        assert pairs[0].correlation_30d == pytest.approx(-1.0, abs=1e-6)

    def test_pair_out_of_window_dropped(self):
        insp = MarketInspector(corr_negative_max=-0.3, corr_negative_min=-1.0)
        long_sig = MarketSignal(
            symbol="A", signal=SIGNAL_ENTRY_LONG_LOW, score=0.35, direction="long"
        )
        short_sig = MarketSignal(
            symbol="B", signal=SIGNAL_ENTRY_SHORT_LOW, score=0.35, direction="short"
        )
        # Two identically-moving series → correlation +1 → filter drops.
        series = self._build_series(100, +1)
        closes_by_sym = {"A": series, "B": list(series)}
        pairs = insp._find_opposing_pairs([long_sig, short_sig], closes_by_sym)
        assert pairs == []

    def test_pair_needs_score_threshold(self):
        insp = MarketInspector()
        weak_long = MarketSignal(symbol="A", score=0.10, direction="long")
        weak_short = MarketSignal(symbol="B", score=0.10, direction="short")
        closes_by_sym = {
            "A": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
            "B": [110, 109, 108, 107, 106, 105, 104, 103, 102, 101, 100],
        }
        pairs = insp._find_opposing_pairs([weak_long, weak_short], closes_by_sym)
        # Both score < 0.3 → excluded
        assert pairs == []

    def test_insufficient_history_dropped(self):
        insp = MarketInspector()
        long_sig = MarketSignal(symbol="A", score=0.6, direction="long")
        short_sig = MarketSignal(symbol="B", score=0.6, direction="short")
        # Only 5 points each → returns[] has 4 < 10 → dropped
        closes = {
            "A": [100, 105, 110, 115, 120],
            "B": [120, 115, 110, 105, 100],
        }
        pairs = insp._find_opposing_pairs([long_sig, short_sig], closes)
        assert pairs == []


class TestScanUniverseE2E:
    def test_end_to_end_records_scan_ts(self):
        insp = MarketInspector()
        candles = {
            "BTC": {
                "1d": _make_upper_extreme_series(25),
                "1w": _make_upper_extreme_series(25),
                "1M": _make_upper_extreme_series(25),
            },
            "ETH": {
                "1d": _make_lower_extreme_series(25),
                "1w": _make_lower_extreme_series(25),
                "1M": _make_lower_extreme_series(25),
            },
        }
        closes = {"BTC": [100.0] * 30, "ETH": [100.0] * 30}
        insp.scan_universe(candles, active_symbols={"BTC"}, closes_by_symbol=closes)
        assert insp.last_scan_ts > 0
        # BTC should register as active
        btc_sig = insp.get_signal("BTC")
        assert btc_sig is not None
        assert btc_sig.is_active is True
        # ETH not in active_symbols set
        eth_sig = insp.get_signal("ETH")
        assert eth_sig is not None
        assert eth_sig.is_active is False

    def test_get_signal_missing_symbol_returns_none(self):
        insp = MarketInspector()
        insp.scan_universe({}, set(), {})
        assert insp.get_signal("NOTHING") is None


class TestSharedInspector:
    def test_shared_instance_is_singleton(self):
        a = get_shared_inspector()
        b = get_shared_inspector()
        assert a is b
        assert isinstance(a, MarketInspector)
