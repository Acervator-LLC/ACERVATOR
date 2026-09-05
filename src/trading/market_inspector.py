"""market_inspector.py — HTF market discovery analyzer.

Scans a universe of crypto markets on daily / weekly / monthly candles.
Emits per-market entry-opportunity signals based on a 3-layer HTF gate
(BB position at extreme + z-score overextension + Landing Strip
tightening), aggregated across the three timeframes. Also identifies
opposing pairs — long-signal + short-signal markets that are
negatively correlated over a rolling 30-day return window.

Runtime contract:
    scan_universe(candles_by_symbol_by_tf, active_symbols,
                  closes_by_symbol)

The result is stored on ``self._last_signals`` and ``self._last_pairs``
and read back by GUI surfaces.

Reuses ta_engine.detect_landing_strip_v2 for HTF tightening.
Pure-Python BB + z-score math (no numpy).

sadp: R28 SSS + R70 RCN
v3.23.37 — Initial implementation (see design proposal
docs/engineering-notes/2026-07-27_market_inspector_audit_and_design_proposal.md).
"""

from __future__ import annotations

import logging
import math
import time as _time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("acervator.market_inspector")

try:
    from .ta_engine import Candle, detect_landing_strip_v2

    _HAS_TA = True
except ImportError:
    Candle = None  # type: ignore
    detect_landing_strip_v2 = None  # type: ignore
    _HAS_TA = False


HTF_TIMEFRAMES = ("1d", "1w", "1M")

SIGNAL_ENTRY_LONG_HIGH = "ENTRY_LONG_HIGH"
SIGNAL_ENTRY_LONG_MEDIUM = "ENTRY_LONG_MEDIUM"
SIGNAL_ENTRY_LONG_LOW = "ENTRY_LONG_LOW"
SIGNAL_ENTRY_SHORT_HIGH = "ENTRY_SHORT_HIGH"
SIGNAL_ENTRY_SHORT_MEDIUM = "ENTRY_SHORT_MEDIUM"
SIGNAL_ENTRY_SHORT_LOW = "ENTRY_SHORT_LOW"
SIGNAL_WATCHLIST = "WATCHLIST"
SIGNAL_NONE = "NONE"


@dataclass
class TimeframeAnalysis:
    """Per-timeframe BB + z-score + tightening state for one market."""

    tf: str
    bb_position: float = 0.5
    z_score: float = 0.0
    sma: float = 0.0
    upper_bb: float = 0.0
    lower_bb: float = 0.0
    tightening: bool = False
    tight_length: int = 0
    tight_ratio: float = 0.0
    at_upper_extreme: bool = False
    at_lower_extreme: bool = False


@dataclass
class MarketSignal:
    """Aggregated HTF signal for one market."""

    symbol: str
    signal: str = SIGNAL_NONE
    score: float = 0.0
    direction: str = ""  # "long" | "short" | ""
    per_tf: dict = field(default_factory=dict)
    is_active: bool = False  # Currently traded by a bot?


@dataclass
class OpposingPair:
    """A long-signal market paired with a short-signal market that
    moves negatively-correlated with it over a rolling window."""

    long_side: MarketSignal
    short_side: MarketSignal
    correlation_30d: float


class MarketInspector:
    """HTF market scanner.

    Feed via ``scan_universe(candles_by_symbol_by_tf, active_symbols,
    closes_by_symbol)``. Read results via ``last_signals`` and
    ``last_pairs`` properties.
    """

    def __init__(
        self,
        z_threshold: float = 1.5,
        corr_negative_max: float = -0.3,
        corr_negative_min: float = -1.0,
        bb_upper_extreme: float = 0.80,
        bb_lower_extreme: float = 0.20,
    ):
        self._z_threshold = z_threshold
        self._corr_max = corr_negative_max
        self._corr_min = corr_negative_min
        self._bb_upper = bb_upper_extreme
        self._bb_lower = bb_lower_extreme
        self._last_signals: list[MarketSignal] = []
        self._last_pairs: list[OpposingPair] = []
        self._last_scan_ts: float = 0.0

    @property
    def last_signals(self) -> list:
        return list(self._last_signals)

    @property
    def last_pairs(self) -> list:
        return list(self._last_pairs)

    @property
    def last_scan_ts(self) -> float:
        return self._last_scan_ts

    def _analyze_tf(self, tf: str, candles: list) -> Optional[TimeframeAnalysis]:
        """BB + z + tightening on one asset's candles for one TF.
        Returns None on insufficient data."""
        if not _HAS_TA or not candles or len(candles) < 20:
            return None
        closes = [float(c.close) for c in candles[-20:]]
        if len(closes) < 20:
            return None
        sma = sum(closes) / 20
        variance = sum((x - sma) ** 2 for x in closes) / 20
        std = math.sqrt(variance)
        if std < 1e-10:
            return None
        price = float(candles[-1].close)
        z = (price - sma) / std
        upper = sma + 2 * std
        lower = sma - 2 * std
        bb_pos = (price - lower) / max(upper - lower, 1e-12)
        tight_flag = False
        tight_len = 0
        tight_ratio = 0.0
        try:
            tr = detect_landing_strip_v2(
                candles, min_consecutive=3, shrink_threshold=0.90, bb_tolerance_pct=3.0
            )
            if tr and getattr(tr, "detected", False):
                tight_flag = True
                tight_len = int(getattr(tr, "length", 0) or 0)
                tight_ratio = float(getattr(tr, "tightening_ratio", 0.0) or 0.0)
        except Exception as _tight_exc:  # noqa: BLE001 - tightening probe best-effort
            logger.debug("tightening probe failed on %s: %s", tf, _tight_exc)
        at_upper = z > self._z_threshold and bb_pos > self._bb_upper
        at_lower = z < -self._z_threshold and bb_pos < self._bb_lower
        return TimeframeAnalysis(
            tf=tf,
            bb_position=bb_pos,
            z_score=z,
            sma=sma,
            upper_bb=upper,
            lower_bb=lower,
            tightening=tight_flag,
            tight_length=tight_len,
            tight_ratio=tight_ratio,
            at_upper_extreme=at_upper,
            at_lower_extreme=at_lower,
        )

    def _score_market(self, symbol: str, per_tf: dict, is_active: bool) -> MarketSignal:
        """Combine D/W/M analyses into a single signal.

        Signal ladder (require all 3 TFs to be evaluated for HIGH/MEDIUM):
          3 TFs at extreme + tightening on ≥ 2 → HIGH   (score 0.9)
          3 TFs at extreme                     → MEDIUM (score 0.6)
          2 of 3 at extreme + tightening on 1  → MEDIUM (score 0.55)
          2 of 3 at extreme                    → LOW    (score 0.35)
          any TF has tightening but no extreme → WATCHLIST (score 0.15)
          otherwise                            → NONE
        """
        long_tfs = [tf for tf, a in per_tf.items() if a and a.at_lower_extreme]
        short_tfs = [tf for tf, a in per_tf.items() if a and a.at_upper_extreme]
        long_tight = sum(1 for tf in long_tfs if per_tf[tf].tightening)
        short_tight = sum(1 for tf in short_tfs if per_tf[tf].tightening)
        n_long = len(long_tfs)
        n_short = len(short_tfs)
        n_tfs = len(per_tf)

        sig = SIGNAL_NONE
        direction = ""
        score = 0.0

        if n_long >= 2 and n_long > n_short:
            direction = "long"
            if n_tfs == 3 and n_long == 3 and long_tight >= 2:
                sig = SIGNAL_ENTRY_LONG_HIGH
                score = 0.9
            elif n_tfs == 3 and n_long == 3:
                sig = SIGNAL_ENTRY_LONG_MEDIUM
                score = 0.6
            elif n_long == 2 and long_tight >= 1:
                sig = SIGNAL_ENTRY_LONG_MEDIUM
                score = 0.55
            else:
                sig = SIGNAL_ENTRY_LONG_LOW
                score = 0.35
        elif n_short >= 2 and n_short > n_long:
            direction = "short"
            if n_tfs == 3 and n_short == 3 and short_tight >= 2:
                sig = SIGNAL_ENTRY_SHORT_HIGH
                score = 0.9
            elif n_tfs == 3 and n_short == 3:
                sig = SIGNAL_ENTRY_SHORT_MEDIUM
                score = 0.6
            elif n_short == 2 and short_tight >= 1:
                sig = SIGNAL_ENTRY_SHORT_MEDIUM
                score = 0.55
            else:
                sig = SIGNAL_ENTRY_SHORT_LOW
                score = 0.35
        else:
            any_tight = any(a.tightening for a in per_tf.values() if a is not None)
            if any_tight:
                sig = SIGNAL_WATCHLIST
                score = 0.15
                # Direction hint from whichever side has tightening
                if long_tight >= 1:
                    direction = "long"
                elif short_tight >= 1:
                    direction = "short"

        return MarketSignal(
            symbol=symbol,
            signal=sig,
            score=score,
            direction=direction,
            per_tf=per_tf,
            is_active=is_active,
        )

    @staticmethod
    def _pearson(xs: list, ys: list) -> float:
        n = len(xs)
        if n < 3 or len(ys) != n:
            return 0.0
        mx = sum(xs) / n
        my = sum(ys) / n
        cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
        var_x = sum((xs[i] - mx) ** 2 for i in range(n))
        var_y = sum((ys[i] - my) ** 2 for i in range(n))
        denom = math.sqrt(var_x * var_y)
        if denom < 1e-12:
            return 0.0
        return cov / denom

    @staticmethod
    def _returns(closes: list) -> list:
        """Simple returns [r1, r2, ...] where r_i = (c_i - c_{i-1}) / c_{i-1}."""
        out = []
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            if prev > 0:
                out.append((closes[i] - prev) / prev)
        return out

    def _find_opposing_pairs(self, signals: list, closes_by_symbol: dict) -> list:
        """Enumerate long × short candidates; keep pairs whose 30-day
        return correlation sits in the configured negative window."""
        longs = [s for s in signals if s.direction == "long" and s.score >= 0.3]
        shorts = [s for s in signals if s.direction == "short" and s.score >= 0.3]
        pairs = []
        for lo in longs:
            for sh in shorts:
                if lo.symbol == sh.symbol:
                    continue
                closes_l = closes_by_symbol.get(lo.symbol, [])
                closes_s = closes_by_symbol.get(sh.symbol, [])
                n = min(len(closes_l), len(closes_s), 30)
                if n < 10:
                    continue
                r_l = self._returns(closes_l[-n:])
                r_s = self._returns(closes_s[-n:])
                m = min(len(r_l), len(r_s))
                if m < 10:
                    continue
                corr = self._pearson(r_l[-m:], r_s[-m:])
                if self._corr_min <= corr <= self._corr_max:
                    pairs.append(
                        OpposingPair(long_side=lo, short_side=sh, correlation_30d=corr)
                    )
        # Rank: more negative correlation first, then higher combined score.
        pairs.sort(
            key=lambda p: (
                p.correlation_30d,
                -(p.long_side.score + p.short_side.score),
            )
        )
        return pairs[:5]

    def scan_universe(
        self,
        candles_by_symbol_by_tf: dict,
        active_symbols: set,
        closes_by_symbol: dict,
    ) -> None:
        """Run the full pipeline. Stores results on the analyzer.

        Args:
            candles_by_symbol_by_tf: {symbol: {tf: [Candle, ...]}}
                where tf is one of HTF_TIMEFRAMES.
            active_symbols: set of base-asset symbols currently traded
                by any running bot (e.g., {"BTC", "ETH"}).
            closes_by_symbol: {symbol: [close_float, ...]} — typically
                the same as the "1d" candles' closes, used for
                opposing-pair correlation.
        """
        signals: list = []
        for symbol, tf_candles in candles_by_symbol_by_tf.items():
            per_tf: dict = {}
            for tf, candles in tf_candles.items():
                a = self._analyze_tf(tf, candles)
                if a is not None:
                    per_tf[tf] = a
            if per_tf:
                sig = self._score_market(
                    symbol, per_tf, is_active=(symbol in active_symbols)
                )
                signals.append(sig)
        signals.sort(key=lambda s: -s.score)
        self._last_signals = signals
        self._last_pairs = self._find_opposing_pairs(signals, closes_by_symbol)
        self._last_scan_ts = _time.time()

    def get_signal(self, symbol: str) -> Optional[MarketSignal]:
        """Convenience lookup used by the Bot Details Market Inspector
        tab. Returns None if the symbol isn't in the most recent scan."""
        for s in self._last_signals:
            if s.symbol == symbol:
                return s
        return None


# Module-level shared instance (single analyzer feeds both GUI surfaces)

_GLOBAL_INSPECTOR: Optional[MarketInspector] = None


def get_shared_inspector() -> MarketInspector:
    """Return the process-wide Market Inspector instance.
    The top-level Market Inspector tab owns the fetch cycle and writes
    scan results here; the Bot Details per-bot tab reads them out."""
    global _GLOBAL_INSPECTOR
    if _GLOBAL_INSPECTOR is None:
        _GLOBAL_INSPECTOR = MarketInspector()
    return _GLOBAL_INSPECTOR
