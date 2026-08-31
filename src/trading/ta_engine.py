"""
ta_engine.py — Technical Analysis Engine v1.1
==============================================
# ┌─────────────────────────────────────────────────────────────┐
# │ AI DEVELOPER NOTE                                           │
# │                                                             │
# │ This file contains ALL technical analysis computation.      │
# │ Three novel inventions live here:                           │
# │                                                             │
# │ 1. detect_bb_proximity() — Landing Strip v1                 │
# │    Detects HA body consolidation at BB band extremes.       │
# │    Returns BBProximityResult with landing_strip flag.       │
# │                                                             │
# │ 2. detect_landing_strip_v2() — Tightening Detection         │
# │    Gradient-based: measures if consecutive HA bodies are     │
# │    SHRINKING (each smaller than the last). More reliable    │
# │    than v1's absolute threshold. Inspired by CogNex edge    │
# │    detection from semiconductor wafer inspection.           │
# │    Uses compute_heikin_ashi() internally — confirmed [HA✓]. │
# │                                                             │
# │ 3. compute_heikin_ashi() — HA candle computation            │
# │    Used for BOTH chart rendering AND LS detection.          │
# │    HA smooths noise; body_pct measures trend exhaustion.    │
# │                                                             │
# │ POSITION-AWARE TA (the BONK insight):                       │
# │    The same VX/MACD signal means different things at        │
# │    different BB positions. Strong VX bullish AT the upper   │
# │    band = price being PUSHED into resistance = SELL signal. │
# │    Same signal in the MIDDLE = weak/ignore.                 │
# │    This reinterpretation happens in the simulator's         │
# │    _sim_scrumming_tick(), NOT in this file.                 │
# │                                                             │
# │ Import path: from ..trading.ta_engine import ...            │
# │ (NOT from .ta_engine — that's the bug that killed LS v2)   │
# └─────────────────────────────────────────────────────────────┘

Comprehensive TA signal processing for Accumulation Trading bots.

Indicators:
  1. Bollinger Bands — price position within bands, squeeze detection
  2. Vortex Indicator — VI+ / VI- crossovers for trend direction
  3. MACD — histogram direction, signal crossovers, divergence
  4. Stochastic RSI — overbought/oversold with K/D crossovers
  5. Ichimoku Cloud — Tenkan/Kijun cross, price vs cloud, future cloud
  6. Volume — OBV trend, volume spikes, accumulation/distribution
  7. Slingshot Indicator — momentum reversal detection via band breaks

Each indicator produces a Signal with:
  - direction: bullish (+1) / bearish (-1) / neutral (0)
  - confidence: 0.0 to 1.0
  - weight: configurable per-indicator importance

The VotingEngine aggregates signals across indicators AND timeframes,
producing a final consensus with configurable thresholds.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
# A threshold that a RATIO is measured against has to be a ratio too.
# Bollinger's `squeeze` compared a dimensionless band width against an
# ABSOLUTE price width and the flag collapsed into a test on price:
# measured across 35 fleet symbols, every symbol at or below $0.42
# squeezed on 0.0% of windows and every symbol at or above $8.28 on
# 100.0%. The repair that landed did not add a comment -- it divided
# the other operand by the same quantity, so both sides of the `<`
# were built the same way.
#
# Thresholds that bound a ratio are therefore carried in PERCENT and
# converted down into ratio space once, through this constant, the way
# src/trading/extractor_bot.py states its rate-spike limit.
PERCENT_PER_RATIO_UNIT = 100.0

# One percentage point of a candle's own high-low range: the unit
# `HACandle.body_pct` is measured in.
HA_BODY_PCT_UNIT = 1.0

# A body that did not shrink at all: norm[j] == norm[j - 1].
NO_SHRINK_RATIO = 1.0

# A volume spike is this percentage of the window's average volume.
VOLUME_SPIKE_PCT = 200.0


# ---------------------------------------------------------------------------
# Core data types
# ---------------------------------------------------------------------------
class SignalDirection(int, Enum):
    BEARISH = -1
    NEUTRAL = 0
    BULLISH = 1


@dataclass
class Signal:
    """One indicator's output at a point in time."""

    indicator: str
    timeframe: str
    direction: SignalDirection
    confidence: float  # 0.0 – 1.0
    weight: float = 1.0  # Configurable importance
    details: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def weighted_score(self) -> float:
        """Signed score: direction × confidence × weight."""
        return self.direction.value * self.confidence * self.weight


@dataclass
class VotingSummary:
    """Aggregated result of all indicator votes."""

    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    total_bullish_score: float = 0.0
    total_bearish_score: float = 0.0
    net_score: float = 0.0  # Positive = bullish consensus
    consensus_confidence: float = 0.0  # 0.0 – 1.0
    signals: list[Signal] = field(default_factory=list)
    timeframe: str = ""

    @property
    def consensus_direction(self) -> SignalDirection:
        if self.net_score > 0.1:
            return SignalDirection.BULLISH
        elif self.net_score < -0.1:
            return SignalDirection.BEARISH
        return SignalDirection.NEUTRAL


# ---------------------------------------------------------------------------
# OHLCV candle helper
# ---------------------------------------------------------------------------
@dataclass
class Candle:
    """Single OHLCV candle."""

    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleDomainError(ValueError):
    """A raw OHLCV row carried a value that is not a price.

    Deliberately a ``ValueError``: every call site that already guards
    :func:`candles_from_raw` catches ``Exception``, so this raises
    through the handlers that exist instead of needing new ones.
    """


# THE CLOSED DOMAIN OF AN OHLC BAR
# --------------------------------
# Each constraint below is the DEFINITION of an OHLC bar. None of them
# is calibrated, so none of them invents a scale:
#
#   * every field is a real, finite number -- NaN, an infinity, a bool
#     and a string are not quantities a price can take;
#   * open/high/low/close are PRICES, and a traded price is > 0;
#   * ``low <= high``, because the two name one range;
#   * ``low <= open <= high`` and ``low <= close <= high``, because the
#     open and the close are trades that happened INSIDE that range.
#
# WHY THE DOMAIN IS THE REPAIR, AND NOT A COEFFICIENT. Measured on this
# tree: one ``close = 0.0`` in a 100-bar window moves 10 of the 12
# wired indicators, and 4 of them are still wrong 60 bars later.
# Slingshot's ``penetration * 8`` turning that bar into BULLISH at
# confidence 1.0000 is one symptom out of ten, so the coefficient is
# not the seat of the defect. Re-tuning it would fabricate a confidence
# scale no published source defines, and would leave the other nine
# exactly as exposed.
#
# WHAT IS DELIBERATELY NOT REFUSED. A bar that is internally consistent
# but absurd against its NEIGHBOURS -- a x1000 spike that lifts close
# and high together -- passes this screen. Calling that invalid needs a
# threshold; no published source supplies one; inventing one here is
# the exact fabrication this screen exists to avoid.


def _candle_field(value: object, field: str, row: int) -> float:
    """Return ``value`` as a finite float, or refuse it.

    The type test is EXACT, not ``isinstance``. ``isinstance`` admits
    subclasses, and ``bool`` is a subclass of ``int``: a price of
    ``True`` would coerce to 1.0 and read as a dollar. Nothing on the
    candle path produces a numeric subclass -- there is no numpy and no
    Decimal anywhere in it -- so exactness costs nothing here and shuts
    that door instead of naming one subclass and missing the rest.
    """
    if type(value) not in (int, float):
        raise CandleDomainError(f"row {row}: {field}={value!r} is not a number")
    number = float(value)
    if not math.isfinite(number):
        raise CandleDomainError(f"row {row}: {field}={value!r} is not finite")
    return number


def candles_from_raw(raw: Sequence[Sequence[object]]) -> list[Candle]:

    # sadp: R28  # candle conversion: fail-loudly on malformed data(R28)
    """Convert [[ts, O, H, L, C, V], ...] to Candle list.

    Refuses any row outside the closed domain described above, so a
    value that is not a price cannot reach an indicator's arithmetic.
    A short row still raises ``IndexError`` exactly as it always has.

    Raises
    ------
    CandleDomainError
        A field is not a finite number, a price is not positive, a
        volume is negative, or the bar's own range is contradictory.
    """
    out: list[Candle] = []
    for row, r in enumerate(raw):
        timestamp = _candle_field(r[0], "timestamp", row)
        open_px = _candle_field(r[1], "open", row)
        high_px = _candle_field(r[2], "high", row)
        low_px = _candle_field(r[3], "low", row)
        close_px = _candle_field(r[4], "close", row)
        volume = _candle_field(r[5], "volume", row)

        for name, price in (
            ("open", open_px),
            ("high", high_px),
            ("low", low_px),
            ("close", close_px),
        ):
            if price <= 0.0:
                raise CandleDomainError(
                    f"row {row}: {name}={price!r} is not a positive price"
                )
        if volume < 0.0:
            raise CandleDomainError(f"row {row}: volume={volume!r} is negative")
        if low_px > high_px:
            raise CandleDomainError(
                f"row {row}: low={low_px!r} is above high={high_px!r}"
            )
        if not low_px <= open_px <= high_px:
            raise CandleDomainError(
                f"row {row}: open={open_px!r} is outside "
                f"[low={low_px!r}, high={high_px!r}]"
            )
        if not low_px <= close_px <= high_px:
            raise CandleDomainError(
                f"row {row}: close={close_px!r} is outside "
                f"[low={low_px!r}, high={high_px!r}]"
            )

        out.append(Candle(timestamp, open_px, high_px, low_px, close_px, volume))
    return out


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------
def _ema(values: list[float], period: int) -> list[float]:
    """Compute EMA series.  Returns list of same length, first (period-1) are SMA-seeded."""
    if len(values) < period:
        return values[:]
    result = [0.0] * len(values)
    # Seed with SMA
    result[period - 1] = sum(values[:period]) / period
    multiplier = 2.0 / (period + 1)
    for i in range(period, len(values)):
        result[i] = (values[i] - result[i - 1]) * multiplier + result[i - 1]
    # Fill leading zeros with first valid value
    for i in range(period - 1):
        result[i] = result[period - 1]
    return result


_TAIL_DEFAULT = 35
"""How many trailing values the suffix-only variants compute.

Set by the hungriest consumer: ``SlingshotIndicator`` reads
``sma_v[i]`` / ``std_v[i]`` for ``i in range(n - (squeeze_lookback + 5), n)``
= the last 35. ``BollingerBands`` needs 20, and ``detect_bb_proximity`` /
``detect_landing_strip_v2`` read only ``[-1]``.
"""


def _sma(values: list[float], period: int) -> list[float]:
    """Simple moving average series."""
    return _sma_tail(values, period, tail=None)


def _stdev(values: list[float], period: int) -> list[float]:
    """Rolling standard deviation."""
    return _stdev_tail(values, period, tail=None)


def _sma_tail(
    values: list[float], period: int, tail: Optional[int] = _TAIL_DEFAULT
) -> list[float]:
    """Simple moving average, computing only the last ``tail`` entries.

    v3.24.22. The full-history form is O(n*period): every one of n
    outputs re-sums a window of `period` values. Consumers read at most
    the last 35 entries, so the first n-35 were computed and discarded
    on every tick, for every bot, for every candle.

    BIT-IDENTITY
    ============
    The per-element body is UNCHANGED — each output still comes from
    ``sum(values[i - period + 1 : i + 1]) / period`` over exactly the same
    slice in exactly the same order. Only the set of ``i`` narrows, so
    each computed element is bit-identical to the full-history version.

    This is deliberately NOT a rolling sum. A rolling accumulator was
    measured at 2.02e-12 max relative difference — close, but not
    identical — and every consumer here is a threshold comparison
    (``bb_pos < 0.15``, ``band_width < avg_width * 0.75``), with
    ``upper/lower = mid +/- 2*std``. A 2e-12 drift in std propagates
    straight into a live SCRUM/FOLD decision on a knife-edge candle.

    Entries before the tail are ``None``: reading one is a TypeError at
    the point of misuse rather than a plausible wrong number.
    """
    n = len(values)
    start = 0 if tail is None else max(0, n - int(tail))
    result: list = [None] * start
    for i in range(start, n):
        if i < period - 1:
            result.append(sum(values[: i + 1]) / (i + 1))
        else:
            result.append(sum(values[i - period + 1 : i + 1]) / period)
    return result


def _stdev_tail(
    values: list[float], period: int, tail: Optional[int] = _TAIL_DEFAULT
) -> list[float]:
    """Rolling standard deviation, last ``tail`` entries only.

    Same contract and same bit-identity argument as ``_sma_tail``: the
    per-window body is untouched, only the range of ``i`` narrows.
    """
    n = len(values)
    start = 0 if tail is None else max(0, n - int(tail))
    result: list = [None] * start
    for i in range(start, n):
        window = values[max(0, i - period + 1) : i + 1]
        if len(window) < 2:
            result.append(0.0)
        else:
            mean = sum(window) / len(window)
            var = sum((x - mean) ** 2 for x in window) / len(window)
            result.append(math.sqrt(var))
    return result


def _window_has_no_range(values: list[float]) -> bool:
    """True when every value in ``values`` is the same number.

    THE SOURCE QUANTITY, NOT A DERIVED ONE. A sample has zero dispersion
    exactly when it has no range, and ``max == min`` settles that on the
    numbers as the venue sent them. No arithmetic runs, so there is
    nothing to round, and the answer is exact at every price scale.

    ``_stdev_tail`` cannot answer the same question, and testing its
    output for zero is the defect this exists to remove. It computes
    ``mean = sum(w)/len(w)`` and then ``sum((x-mean)**2)/len(w)``, and
    summing N copies of one price GENERICALLY ROUNDS. MEASURED over 599
    fully halted 60-bar tapes built from venue decimal strings, 154 left
    sigma at a few ULPs instead of 0.0 -- 40 of 100 at 118.xx, 40 of 100
    at 61234.xx, 38 of 100 at 0.031200xx, and the very first at 0.11,
    which is the operator's own CHIP scale. On those tapes a test of
    ``upper - lower <= 0.0`` does NOT fire, the 1e-9 epsilon then
    dominates a ~1e-17 band, %B rounds to 0.0, and the indicator answers
    BULLISH at confidence 1.0000 on a market that has not moved.

    An empty window has no range either, and says so rather than
    raising, because every caller here has already length-checked.
    """
    if not values:
        return True
    return max(values) == min(values)


def _true_range(candles: list[Candle]) -> list[float]:
    """True Range series."""
    tr = [candles[0].high - candles[0].low]
    for i in range(1, len(candles)):
        c = candles[i]
        prev_close = candles[i - 1].close
        tr.append(
            max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
        )
    return tr


# ---------------------------------------------------------------------------
# 8. ADX / DMI — Average Directional Index + Directional Movement Index
# ---------------------------------------------------------------------------
class ADXIndicator:
    """
    Wilder's ADX/DMI (1978) — the only indicator that measures TREND STRENGTH
    rather than direction or exhaustion. Answers: "how committed is this move?"

    Components:
      DM+  : Directional Movement Plus  = max(high - prev_high, 0) if > |low - prev_low|
      DM-  : Directional Movement Minus = max(prev_low - low, 0)   if > |high - prev_high|
      TR   : True Range = max(H-L, |H-prevC|, |L-prevC|)
      DI+  : 100 × Smoothed(DM+) / Smoothed(TR)    — bullish force
      DI-  : 100 × Smoothed(DM-) / Smoothed(TR)    — bearish force
      DX   : 100 × |DI+ - DI-| / (DI+ + DI-)       — directional strength
      ADX  : Wilder-smoothed DX over period          — trend strength

    Signal thresholds:
      ADX < 20           = ranging / weak trend → accumulation ideal conditions
      ADX 20-35          = developing trend
      ADX > 35           = strong trend → lean into direction aggressively
      ADX > 50           = parabolic (unsustainable)
      DI+ > DI-          = bullish pressure dominant
      DI+ crossing DI-   = trend turning bullish (Golden Cross)
      DI- crossing DI+   = trend turning bearish
      ADX rising from <20 = new trend forming = slingshot sibling signal

    For accumulation:
      Ranging (ADX<20)   → full harvest efficiency, fold every oscillation
      Strong bull (ADX>35 + DI+>DI-) → scrums more aggressive, folds lean
      Strong bear (ADX>35 + DI->DI+) → folds more aggressive, scrums lean
      Trend reversal (DI cross) → confirmation for fold or scrum entry
    """

    def __init__(self, period: int = 14, weight: float = 1.0):
        self.period = period
        self.weight = weight

    @staticmethod
    def _wilder_smooth(values: list, period: int) -> list:
        """Wilder's smoothing — not EMA. First value = sum/period.

        v3.24.83 — THIS NOW MATCHES ITS OWN DOCSTRING.

        It read "First value = sum/period" and then did
        ``first = sum(values[:period])`` with no division, and recursed
        as ``prev - prev/period + v`` — the SUM form. Every value it
        returned was `period` times Wilder's average.

        That is invisible in +DI/-DI, which divide two of its outputs
        by each other so the scale cancels. It is NOT invisible in DX,
        which is already a 0-100 percentage: the returned ADX was ~14x
        its own definitional maximum. Measured before the fix, on 1174
        records: 99.8% above 100, max 761.5.

        The averaged form is the textbook one, so the textbook
        thresholds (25 trending / 30 strong / 50 extreme) now apply as
        written. `ScrummingTrendRegimeGate.adx_threshold` was empirically
        recalibrated to 500.0 against the OLD scale and is reset to 30.0
        in the same change — its docstring required exactly that.
        """
        if len(values) < period:
            return [0.0] * len(values)
        result = [0.0] * (period - 1)
        result.append(sum(values[:period]) / period)
        for v in values[period:]:
            result.append(result[-1] + (v - result[-1]) / period)
        return result

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:

        # sadp: R28  # indicator compute: fail-loudly(R28)
        n = len(candles)
        if n < self.period * 2 + 2:
            return Signal("adx", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        dm_plus = []
        dm_minus = []
        tr_list = []
        for i in range(1, n):
            h, l, _ = candles[i].high, candles[i].low, candles[i].close
            ph, pl, pc = candles[i - 1].high, candles[i - 1].low, candles[i - 1].close

            up = h - ph
            down = pl - l
            dm_plus.append(up if up > down and up > 0 else 0.0)
            dm_minus.append(down if down > up and down > 0 else 0.0)
            tr_list.append(max(h - l, abs(h - pc), abs(l - pc)))

        s_dmp = self._wilder_smooth(dm_plus, self.period)
        s_dmm = self._wilder_smooth(dm_minus, self.period)
        s_tr = self._wilder_smooth(tr_list, self.period)

        if not s_tr or s_tr[-1] < 1e-9:
            return Signal("adx", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        di_plus = 100.0 * s_dmp[-1] / s_tr[-1]
        di_minus = 100.0 * s_dmm[-1] / s_tr[-1]

        # Previous DI for crossover
        if len(s_tr) >= 2 and s_tr[-2] > 1e-9:
            p_dip = 100.0 * s_dmp[-2] / s_tr[-2]
            p_dim = 100.0 * s_dmm[-2] / s_tr[-2]
        else:
            p_dip = di_plus
            p_dim = di_minus

        di_sum = di_plus + di_minus
        100.0 * abs(di_plus - di_minus) / di_sum if di_sum > 1e-9 else 0.0

        # ADX = Wilder smooth of DX history
        # Compute full DX series for smoothing
        dx_series = []
        for j in range(len(s_tr)):
            # No true range in this window makes DI+ and DI- both 0/0.
            # The window has no DX -- which is exactly what the `ds` test
            # four lines below has always said for the same condition.
            # `s_tr[j]` is a Wilder sum of true ranges, and a true range
            # is a max of differences between equal prices on a halt, so
            # it cancels to EXACTLY 0.0 and this test is sound on it.
            if s_tr[j] <= 0.0:
                dx_series.append(0.0)
                continue
            dip_j = 100.0 * s_dmp[j] / (s_tr[j] + 1e-9)
            dim_j = 100.0 * s_dmm[j] / (s_tr[j] + 1e-9)
            ds = dip_j + dim_j
            dx_series.append(100.0 * abs(dip_j - dim_j) / ds if ds > 1e-9 else 0.0)

        # The leading `period - 1` entries of `dx_series` come from the
        # zero pad `_wilder_smooth` writes, not from real DI readings.
        # Averaging them in would drag the first ADX toward zero, so the
        # series starts at the first genuine DX.
        _dx_valid = dx_series[self.period - 1 :]
        s_dx = self._wilder_smooth(_dx_valid, self.period)
        adx = s_dx[-1] if s_dx else 0.0
        p_adx = s_dx[-2] if len(s_dx) >= 2 else adx

        # Signals
        ranging = adx < 20
        developing = 20 <= adx < 35
        strong_trend = adx >= 35
        parabolic = adx >= 50
        adx_rising = adx > p_adx
        bull_dominant = di_plus > di_minus
        bear_dominant = di_minus > di_plus
        di_bull_cross = p_dip <= p_dim and di_plus > di_minus  # DI+ crosses above DI-
        di_bear_cross = p_dip >= p_dim and di_plus < di_minus  # DI- crosses above DI+
        new_trend = adx_rising and p_adx < 20 and adx >= 20  # ADX emerging from ranging

        # Direction and confidence
        if bull_dominant and strong_trend:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, (adx - 35) / 30 + 0.5))
        elif bear_dominant and strong_trend:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, (adx - 35) / 30 + 0.5))
        elif bull_dominant:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(0.5, adx / 70))
        elif bear_dominant:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(0.5, adx / 70))
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="adx",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "adx": round(adx, 2),
                "di_plus": round(di_plus, 2),
                "di_minus": round(di_minus, 2),
                "ranging": ranging,
                "developing": developing,
                "strong_trend": strong_trend,
                "parabolic": parabolic,
                "adx_rising": adx_rising,
                "bull_dominant": bull_dominant,
                "bear_dominant": bear_dominant,
                "di_bull_cross": di_bull_cross,
                "di_bear_cross": di_bear_cross,
                "new_trend": new_trend,
            },
        )


# ---------------------------------------------------------------------------
# 9. Supertrend — ATR-based dynamic support/resistance
# ---------------------------------------------------------------------------
class SupertrendIndicator:
    """
    Supertrend (Oliver Seban popularised; ATR trailing stop concept).
    Places a dynamic line above price in downtrend, below in uptrend.
    When price crosses the line, it flips direction.

    Unlike Ichimoku (26-bar displacement, complex), Supertrend is reactive:
    it gives a timestamped trend flip at the exact candle it occurs.
    The combination of Ichimoku (predictive) + Supertrend (reactive) gives
    both "what is coming" and "has it started."

    Computation:
      ATR over period
      Upper band = (H + L)/2 + multiplier × ATR
      Lower band = (H + L)/2 - multiplier × ATR
      Supertrend is bullish when close > lower band
      Supertrend is bearish when close < upper band
      Bands are "sticky" — only update when price crosses them

    For accumulation:
      Flip bearish→bullish = highest-quality fold entry (trend changed NOW)
      Flip bullish→bearish = harvest NOW, trend changed
      Bullish + close near line = Kijun-equivalent fold dip entry
      Distance from line = trend conviction
    """

    def __init__(self, period: int = 10, multiplier: float = 3.0, weight: float = 1.0):
        self.period = period
        self.multiplier = multiplier
        self.weight = weight

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        n = len(candles)
        if n < self.period + 2:
            return Signal(
                "supertrend", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        # ATR (Wilder)
        tr_list = [
            max(
                candles[i].high - candles[i].low,
                abs(candles[i].high - candles[i - 1].close),
                abs(candles[i].low - candles[i - 1].close),
            )
            for i in range(1, n)
        ]

        # Simple ATR smoothing (Wilder)
        atr = [0.0] * (self.period)
        if len(tr_list) >= self.period:
            first_atr = sum(tr_list[: self.period]) / self.period
            atr = [first_atr]
            for tr in tr_list[self.period :]:
                atr.append((atr[-1] * (self.period - 1) + tr) / self.period)

        if not atr:
            return Signal(
                "supertrend", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        # Align: atr[0] corresponds to candles[period]
        start = self.period
        curr_atr = atr[-1]

        # Build Supertrend series (need history for sticky bands)
        ub = [0.0]
        lb = [0.0]
        st = [True]  # True = bullish
        for i in range(start, n):
            idx_atr = i - start
            if idx_atr >= len(atr):
                idx_atr = len(atr) - 1
            a = atr[idx_atr]
            hl2 = (candles[i].high + candles[i].low) / 2.0
            raw_ub = hl2 + self.multiplier * a
            raw_lb = hl2 - self.multiplier * a

            # Sticky bands
            prev_ub = ub[-1] if ub else raw_ub
            prev_lb = lb[-1] if lb else raw_lb
            final_ub = (
                raw_ub
                if raw_ub < prev_ub or candles[i - 1].close > prev_ub
                else prev_ub
            )
            final_lb = (
                raw_lb
                if raw_lb > prev_lb or candles[i - 1].close < prev_lb
                else prev_lb
            )

            prev_bull = st[-1]
            if prev_bull:
                curr_bull = candles[i].close >= final_lb
            else:
                curr_bull = candles[i].close > final_ub

            ub.append(final_ub)
            lb.append(final_lb)
            st.append(curr_bull)

        curr_bull = st[-1]
        prev_bull = st[-2] if len(st) >= 2 else curr_bull
        flip_bull = curr_bull and not prev_bull  # just turned bullish
        flip_bear = not curr_bull and prev_bull  # just turned bearish

        price = candles[-1].close
        st_line = lb[-1] if curr_bull else ub[-1]
        dist_pct = abs(price - st_line) / (st_line + 1e-9)

        # Near-line: price within 0.5% of Supertrend line (fold entry in bull)
        near_line = dist_pct < 0.005

        confidence = 0.0
        if flip_bull or flip_bear:
            confidence = 0.85  # flip = strong signal
        elif curr_bull:
            confidence = max(0.0, min(0.6, dist_pct * 5 + 0.2))
        else:
            confidence = max(0.0, min(0.6, dist_pct * 5 + 0.2))

        direction = SignalDirection.BULLISH if curr_bull else SignalDirection.BEARISH

        return Signal(
            indicator="supertrend",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "bullish": curr_bull,
                "flip_bull": flip_bull,
                "flip_bear": flip_bear,
                "st_line": round(st_line, 6),
                "dist_pct": round(dist_pct * 100, 3),
                "near_line": near_line,
                "curr_atr": round(curr_atr, 6),
            },
        )


# ---------------------------------------------------------------------------
# 10. Z-Score — Absolute statistical price deviation from mean
# ---------------------------------------------------------------------------
class ZScoreIndicator:
    """
    Z-Score of price: how many standard deviations is the current close
    from its N-period mean?

    Z = (close - SMA_N) / STD_N

    Why this is NOT redundant with Bollinger Bands:
      BB uses a 20-period window and normalises to *current* volatility.
      If volatility doubles, the bands widen — a price at bb_pos=0.95 no
      longer represents the same statistical stretch as before.
      Z-score uses a longer window (default 50) and is an absolute measure.
      It catches moves that the 20-period BB has already normalised away.

    Thresholds (empirical, robust across assets):
      |Z| < 0.5  = near mean, neutral
      Z > +1.5   = stretched high, mild scrum signal
      Z > +2.0   = statistically stretched, scrum confidence boost
      Z > +3.0   = rare extreme (top 0.13%), strong scrum
      Z < -1.5   = stretched low, mild fold signal
      Z < -2.0   = statistically stretched, fold confidence boost
      Z < -3.0   = rare extreme, very strong fold signal

    For accumulation:
      Z < -2.5 + Ichimoku below cloud + StochRSI oversold
      = three independent mathematical frameworks saying the same thing
      = maximum fold confidence convergence
    """

    def __init__(self, period: int = 50, weight: float = 1.0):
        self.period = period
        self.weight = weight

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 1:
            return Signal(
                "zscore", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        closes = [c.close for c in candles[-self.period :]]
        sma = sum(closes) / self.period
        variance = sum((c - sma) ** 2 for c in closes) / self.period
        std = variance**0.5

        if std < 1e-9:
            return Signal(
                "zscore", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        z = (candles[-1].close - sma) / std

        # Rate of Z change (is it moving toward or away from mean?)
        #
        # A previous window with no dispersion has no Z to compare
        # against: (close - mean) / 0 is 0/0. `z_prev = z` is this
        # module's own no-information fallback, already used when the
        # history is too short, and it leaves `z_reverting` False rather
        # than asserting a direction of travel that was never measured.
        #
        # The test is `< 1e-9`, character for character the one the
        # primary guard above applies to `std`. Reusing that threshold
        # rather than `std2 > 0.0` is deliberate: `std2` is derived and
        # rounds to ULPs rather than to zero on a halted window, so an
        # exact test would let a ~1e-17 denominator through. This
        # abstains, which is the safe direction, and invents no new
        # coefficient.
        z_prev = z
        if len(candles) >= self.period + 2:
            c_prev = [c.close for c in candles[-self.period - 1 : -1]]
            s2 = sum(c_prev) / self.period
            v2 = sum((c - s2) ** 2 for c in c_prev) / self.period
            std2 = v2**0.5
            if not std2 < 1e-9:
                z_prev = (candles[-2].close - s2) / (std2 + 1e-9)

        z_reverting = (z > 0 and z < z_prev) or (z < 0 and z > z_prev)

        # Extreme signals
        extreme_high = z > 3.0
        strong_high = z > 2.0
        mild_high = z > 1.5
        extreme_low = z < -3.0
        strong_low = z < -2.0
        mild_low = z < -1.5

        if strong_high:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, (z - 2.0) / 2.0 + 0.5))
        elif strong_low:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, (-z - 2.0) / 2.0 + 0.5))
        elif mild_high:
            direction = SignalDirection.BEARISH
            confidence = 0.25
        elif mild_low:
            direction = SignalDirection.BULLISH
            confidence = 0.25
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="zscore",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "z": round(z, 3),
                "z_prev": round(z_prev, 3),
                "sma": round(sma, 6),
                "std": round(std, 6),
                "extreme_high": extreme_high,
                "strong_high": strong_high,
                "mild_high": mild_high,
                "extreme_low": extreme_low,
                "strong_low": strong_low,
                "mild_low": mild_low,
                "z_reverting": z_reverting,
            },
        )


# ---------------------------------------------------------------------------
# 11. Kaufman Efficiency Ratio — Market quality indicator
# ---------------------------------------------------------------------------
class KaufmanERIndicator:
    """
    Perry Kaufman's Efficiency Ratio (1995) — measures the quality of the
    market, not direction.

    ER = |net price change over N bars| / sum(|individual bar changes|)
    ER → 1.0: price moving EFFICIENTLY (trending) — one direction, little noise
    ER → 0.0: price moving RANDOMLY (choppy) — high noise, low direction

    This is the only indicator in the suite that answers:
    "Is this market suitable for accumulation right now?"

    Thresholds:
      ER < 0.25 = high noise, low direction = accumulation IDEAL
                  Every oscillation is harvestable. Hold nothing back.
      ER 0.25-0.50 = moderate efficiency = normal operation
      ER > 0.50 = trending efficiently = lean into trend
      ER > 0.70 = highly efficient trend = conservative on counter-trend folds
      ER rising  = trend forming (like ADX emerging from ranging)
      ER falling from high = trend weakening = prepare for ranging

    For accumulation:
      Low ER = volatile, oscillating market = strategy at full power
      High ER = trending = reduce counter-trend folds, boost trend-direction
      ER peak + beginning to fall = regime change coming = load fold queue
    """

    def __init__(self, period: int = 10, weight: float = 1.0):
        self.period = period
        self.weight = weight

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 2:
            return Signal(
                "kaufman_er", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        closes = [c.close for c in candles[-(self.period + 1) :]]
        net_change = abs(closes[-1] - closes[0])
        price_travel = sum(
            abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))
        )

        # A window where price never moved has travelled no distance, so
        # displacement over distance is 0/0. The market's quality is not
        # "perfectly choppy" or "perfectly efficient" here -- it is
        # unmeasured, and an unmeasured regime casts no vote.
        #
        # `price_travel` is a sum of |close[i] - close[i-1]|. Subtracting
        # two EQUAL floats is exact in IEEE 754, so every term is exactly
        # 0.0 and so is the sum: this test is on a derived quantity that
        # cancels exactly, and needs no source-window test behind it.
        if price_travel <= 0.0:
            return Signal(
                "kaufman_er", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        # Kaufman's Efficiency Ratio: net displacement over the total
        # distance travelled to get there. Both are prices, so `er` is
        # dimensionless and lies in [0, 1].
        er = net_change / (price_travel + 1e-9)

        # Previous ER for trend. A previous window that never moved has
        # no ER either; `er_prev = er` is this module's own fallback for
        # that, already used when the history is too short.
        er_prev = er
        if len(candles) >= self.period + 3:
            c2 = [c.close for c in candles[-(self.period + 2) : -1]]
            nc2 = abs(c2[-1] - c2[0])
            pl2 = sum(abs(c2[i] - c2[i - 1]) for i in range(1, len(c2)))
            if pl2 > 0.0:
                er_prev = nc2 / (pl2 + 1e-9)

        er_rising = er > er_prev
        er_falling = er < er_prev

        # Classify
        ideal_ranging = er < 0.25
        moderate = 0.25 <= er < 0.50
        trending = er >= 0.50
        highly_efficient = er >= 0.70
        er_peak_falling = er_falling and er_prev >= 0.60  # trend ending

        # Price direction (trending ER needs direction to be useful)
        closes_all = [c.close for c in candles]
        price_up = closes_all[-1] > closes_all[-self.period]

        if trending and price_up:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(0.7, er * 0.7))
        elif trending and not price_up:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(0.7, er * 0.7))
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="kaufman_er",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "er": round(er, 4),
                "er_prev": round(er_prev, 4),
                "er_rising": er_rising,
                "er_falling": er_falling,
                "ideal_ranging": ideal_ranging,
                "moderate": moderate,
                "trending": trending,
                "highly_efficient": highly_efficient,
                "er_peak_falling": er_peak_falling,
                "price_up": price_up,
            },
        )


# ===========================================================================
# INDICATOR IMPLEMENTATIONS
# ===========================================================================


# ---------------------------------------------------------------------------
# 1. Bollinger Bands
# ---------------------------------------------------------------------------
class BollingerBands:
    """
    Bollinger Bands: SMA(20) ± 2σ.
    Signals:
      - Price near lower band → bullish (oversold)
      - Price near upper band → bearish (overbought)
      - Band squeeze (narrow width) → breakout imminent
      - Band expansion → trend confirmation
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0, weight: float = 1.0):
        self.period = period
        self.std_dev = std_dev
        self.weight = weight

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        closes = [c.close for c in candles]
        if len(closes) < self.period:
            return Signal(
                "bollinger_bands", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        # v3.24.22 — suffix-only. Consumes sma[-1]/std[-1] plus the
        # widths slice over the last `period` entries, so `period` is
        # exactly the depth needed. Derived from config, not the module
        # default, so a bot configured with a longer period still gets
        # every value it reads.
        sma = _sma_tail(closes, self.period, tail=self.period)
        std = _stdev_tail(closes, self.period, tail=self.period)

        mid = sma[-1]
        upper = mid + self.std_dev * std[-1]
        lower = mid - self.std_dev * std[-1]
        price = closes[-1]
        band_width = (upper - lower) / (mid + 1e-9)

        # Squeeze detection (width below 20-period average width)
        #
        # v3.24.22 — the comprehension bound was `range(len(sma))`, i.e.
        # the ENTIRE history, while only the last `period` entries are
        # ever consumed by the `widths[-self.period:]` slice below.
        #
        # This is also the hard blocker for narrowing _sma/_stdev: it is
        # the only site that indexes sma/std across the whole range, so
        # until it is bounded, a suffix-only _sma would be read at
        # indices it never filled (TypeError: float * NoneType).
        #
        # The arithmetic expression is deliberately left VERBATIM rather
        # than simplified to `2 * std_dev * std[i]`. Every consumer of
        # these values is a threshold comparison, and changing the order
        # of float operations changes the last bits.
        #
        # v3.24.83 — DIVIDED BY sma[i]. IT WAS A UNITS MISMATCH.
        #
        # `band_width` above is `(upper - lower) / mid` — DIMENSIONLESS.
        # These historical widths were `(sma + k*std) - (sma - k*std)`;
        # the `sma[i]` terms cancel exactly, leaving `2*k*std[i]` in
        # PRICE UNITS, never normalised. Line below then compared the
        # ratio against the absolute width.
        #
        # So `squeeze` was a test on PRICE, not on volatility. Setting
        # sigma ~ sigma_avg, `band_width < 0.75 * avg_width` reduces to
        # `mid > 1.33` — an asset cheaper than about $1.33 can never
        # register a squeeze, and a dearer one almost always can.
        # MEASURED on the operator's own fleet: CHIP at $0.08 squeezed
        # 0 times in 400 candles, SPK at $0.03 zero in 402, XRP at
        # $1.44 226 of 379 (59.6%).
        #
        # It reaches trading: `confidence *= 0.7` below fires only when
        # squeezed, so the damping was applied by asset price.
        #
        # The correct form already existed twenty feet away —
        # `native_chart.py:1231-1236` averages bandwidth and compares
        # bandwidth. The chart drew squeezes the engine could not see.
        #
        # Numerator kept verbatim per the note above; only the
        # normalisation that `band_width` already had is added.
        widths = [
            ((sma[i] + self.std_dev * std[i]) - (sma[i] - self.std_dev * std[i]))
            / (sma[i] + 1e-9)
            for i in range(max(0, len(sma) - self.period), len(sma))
        ]
        # `width_count` is a COUNT of windows, not a bandwidth. Naming
        # it keeps the length test out of the bandwidth comparison on
        # the next line.
        width_count = len(widths)
        avg_width = (
            sum(widths[-self.period :]) / self.period
            if width_count >= self.period
            else band_width
        )
        squeeze = band_width < avg_width * 0.75

        # Position within bands (0 = lower, 1 = upper)
        #
        # %B is a position WITHIN a channel. A window whose price never
        # moved has no channel, so there is no position to report and no
        # vote to cast. Resolving 0/0 through the epsilon gave
        # bb_pos = 0.0, which the first branch below reads as hard
        # against the LOWER band and answers with confidence 1.0000 --
        # the largest vote any indicator in this engine casts, at weight
        # 1.0.
        #
        # The test is on the CLOSES, not on `upper - lower`. The band
        # width is 4*sigma out of `_stdev_tail`, and on a halted window
        # that rounds to a few ULPs rather than to zero on 154 of 599
        # measured price pegs, so a test of the width misses exactly the
        # markets this guard exists for. `upper - lower <= 0.0` is kept
        # underneath as a subordinate floor: it can only ever make this
        # abstain more often, never less.
        if _window_has_no_range(closes[-self.period :]) or upper - lower <= 0.0:
            return Signal(
                "bollinger_bands", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        bb_pos = (price - lower) / (upper - lower + 1e-9)

        direction = SignalDirection.NEUTRAL
        confidence = 0.0

        if bb_pos < 0.15:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, (0.15 - bb_pos) / 0.15 * 0.8 + 0.3))
        elif bb_pos > 0.85:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, (bb_pos - 0.85) / 0.15 * 0.8 + 0.3))
        elif bb_pos < 0.35:
            direction = SignalDirection.BULLISH
            confidence = 0.2
        elif bb_pos > 0.65:
            direction = SignalDirection.BEARISH
            confidence = 0.2

        if squeeze:
            confidence *= 0.7  # Less confident during squeeze

        return Signal(
            indicator="bollinger_bands",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "upper": round(upper, 6),
                "middle": round(mid, 6),
                "lower": round(lower, 6),
                "bb_position": round(bb_pos, 4),
                "band_width": round(band_width, 6),
                "squeeze": squeeze,
            },
        )


# ---------------------------------------------------------------------------
# 2. Vortex Indicator
# ---------------------------------------------------------------------------
# Vortex extremes — empirically observed typical ceiling/floor thresholds
# VI+ and VI- are RATIOS -- a directional-movement sum over a
# true-range sum -- so 1.0 is parity and the extremes are stated as a
# percentage OF that parity, then divided back into ratio space. Both
# sides of the ceiling/floor tests below then carry the same unit by
# construction rather than by convention.
VX_CEILING_PCT = 130.0  # VI at 130% of parity = momentum exhausted
VX_FLOOR_PCT = 70.0  # VI at  70% of parity = flat / no conviction
VX_CEILING = VX_CEILING_PCT / PERCENT_PER_RATIO_UNIT
VX_FLOOR = VX_FLOOR_PCT / PERCENT_PER_RATIO_UNIT


class VortexIndicator:
    """
    Vortex Indicator: VI+ and VI- trend direction.

    Enhanced signals (v3.7.0):
      - Crossover: VI+ crosses VI- or vice versa (primary signal)
      - Separation expansion after crossover: confirmation of direction
      - VI+ pegged at ceiling (>= VX_CEILING): bullish momentum exhausted
      - VI- pegged at ceiling (>= VX_CEILING): bearish momentum exhausted
      - VI+ pegged at floor (<= VX_FLOOR):    bullish conviction flat
      - Both lines converging near 1.0:        consolidation / no trend
    """

    def __init__(self, period: int = 14, weight: float = 1.0):
        self.period = period
        self.weight = weight

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 1:
            return Signal(
                "vortex", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        vm_plus = []
        vm_minus = []
        for i in range(1, len(candles)):
            vm_plus.append(abs(candles[i].high - candles[i - 1].low))
            vm_minus.append(abs(candles[i].low - candles[i - 1].high))

        tr = _true_range(candles)[1:]

        n = self.period
        if len(vm_plus) < n:
            return Signal(
                "vortex", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        sum_vp = sum(vm_plus[-n:])
        sum_vm = sum(vm_minus[-n:])
        sum_tr_window = sum(tr[-n:])

        # VI+ and VI- are directional movement OVER true range. With no
        # true range across the window there is no denominator at all,
        # and the epsilon became the whole of it.
        #
        # This is not simply the halted-market case. `tr` is aligned to
        # candle i while `vm_plus[i]` reaches back to candle i-1, so at
        # the moment a halt first fills the true-range window the VM sums
        # still carry the last live bar. Measured at halt length 14 --
        # exactly the period, and every halt of 14 bars or more passes
        # through it -- VI+ reached 2.2e8 and the separation -5.5e7. That
        # separation is overwhelmingly BEARISH and the vote came out
        # BULLISH, because VI- above VX_CEILING trips the bear-exhaustion
        # branch below, which overwrites the direction. The epsilon did
        # not inflate a number here; it inverted a trade.
        #
        # True range is a max of differences between equal prices on a
        # halt, so the sum cancels to EXACTLY 0.0 and `<= 0.0` is sound.
        if sum_tr_window <= 0.0:
            return Signal(
                "vortex", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        sum_tr = sum_tr_window + 1e-9

        vi_plus = sum_vp / sum_tr
        vi_minus = sum_vm / sum_tr

        # Previous period values for crossover + acceleration detection.
        # A previous window with no true range has no VI either, and this
        # module's own fallback for that is the current reading.
        prev_vp = vi_plus
        prev_vm = vi_minus
        if len(vm_plus) >= n + 1:
            prev_tr_window = sum(tr[-n - 1 : -1])
            if prev_tr_window > 0.0:
                prev_vp = sum(vm_plus[-n - 1 : -1]) / (prev_tr_window + 1e-9)
                prev_vm = sum(vm_minus[-n - 1 : -1]) / (prev_tr_window + 1e-9)

        separation = vi_plus - vi_minus
        prev_sep = prev_vp - prev_vm
        sep_acceleration = separation - prev_sep  # how fast lines are diverging

        # ── Ceiling / floor detection ─────────────────────────────────────
        vip_at_ceiling = vi_plus >= VX_CEILING  # bullish exhausted
        vim_at_ceiling = vi_minus >= VX_CEILING  # bearish exhausted
        vip_at_floor = vi_plus <= VX_FLOOR  # no bullish conviction
        vim_at_floor = vi_minus <= VX_FLOOR  # no bearish conviction
        both_converging = abs(separation) < 0.08  # lines near each other

        # ── Crossover ─────────────────────────────────────────────────────
        bullish_cross = prev_sep <= 0 and separation > 0
        bearish_cross = prev_sep >= 0 and separation < 0

        # ── Post-crossover divergence acceleration ────────────────────────
        # After a bullish cross, VI+ rising AND VI- falling simultaneously
        # is the strongest possible confirmation (your image arrows)
        bull_accel = (
            separation > 0
            and sep_acceleration > 0.05
            and vi_plus > prev_vp
            and vi_minus < prev_vm
        )
        bear_accel = (
            separation < 0
            and sep_acceleration < -0.05
            and vi_minus > prev_vm
            and vi_plus < prev_vp
        )

        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover = bullish_cross or bearish_cross

        if bullish_cross:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, abs(separation) * 3 + 0.5))
        elif bearish_cross:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(separation) * 3 + 0.5))
        elif bull_accel:
            # Post-crossover divergence expanding — highest-conviction bull signal
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, abs(separation) * 2 + 0.55))
        elif bear_accel:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(separation) * 2 + 0.55))
        elif separation > 0.05:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(0.6, abs(separation) * 2))
        elif separation < -0.05:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(0.6, abs(separation) * 2))

        # ── Ceiling/floor confidence modifiers ───────────────────────────
        # VI+ pegged at ceiling = uptrend is exhausted — lower scrum confidence
        # VI- pegged at ceiling = downtrend is exhausted — boost fold confidence
        # Both converging near 1.0 = no trend, consolidation
        if vip_at_ceiling:
            # Bullish momentum maxed out — reduce scrum confidence signal
            confidence = max(0.0, min(confidence, 0.45))
        if vim_at_ceiling:
            # Bearish momentum maxed out — this is a strong fold signal
            confidence = min(1.0, max(confidence, 0.60))
            direction = SignalDirection.BULLISH  # bear exhaustion = reversal coming

        return Signal(
            indicator="vortex",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "vi_plus": round(vi_plus, 4),
                "vi_minus": round(vi_minus, 4),
                "separation": round(separation, 4),
                "sep_acceleration": round(sep_acceleration, 4),
                "crossover": crossover,
                "bull_accel": bull_accel,
                "bear_accel": bear_accel,
                "vip_at_ceiling": vip_at_ceiling,
                "vim_at_ceiling": vim_at_ceiling,
                "vip_at_floor": vip_at_floor,
                "vim_at_floor": vim_at_floor,
                "both_converging": both_converging,
            },
        )


# ---------------------------------------------------------------------------
# 3. MACD
# ---------------------------------------------------------------------------
class MACD:
    """
    MACD: EMA(12) - EMA(26), Signal EMA(9), Histogram.
    Enhanced with divergence detection.
    """

    def __init__(
        self, fast: int = 12, slow: int = 26, signal: int = 9, weight: float = 1.0
    ):
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.weight = weight

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        closes = [c.close for c in candles]
        if len(closes) < self.slow + self.signal_period:
            return Signal("macd", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)

        ema_fast = _ema(closes, self.fast)
        ema_slow = _ema(closes, self.slow)
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
        signal_line = _ema(macd_line, self.signal_period)
        histogram = [m - s for m, s in zip(macd_line, signal_line)]

        curr_hist = histogram[-1]
        prev_hist = histogram[-2] if len(histogram) > 1 else 0
        curr_macd = macd_line[-1]
        curr_signal = signal_line[-1]
        prev_macd = macd_line[-2] if len(macd_line) > 1 else 0
        prev_signal = signal_line[-2] if len(signal_line) > 1 else 0

        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover = False
        divergence = ""

        # Crossover detection
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            direction = SignalDirection.BULLISH
            crossover = True
            confidence = max(
                0.0,
                min(1.0, abs(curr_hist) / (abs(closes[-1]) * 0.001 + 1e-9) * 0.3 + 0.5),
            )
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            direction = SignalDirection.BEARISH
            crossover = True
            confidence = max(
                0.0,
                min(1.0, abs(curr_hist) / (abs(closes[-1]) * 0.001 + 1e-9) * 0.3 + 0.5),
            )
        elif curr_hist > 0 and curr_hist > prev_hist:
            direction = SignalDirection.BULLISH
            confidence = max(
                0.0, min(0.6, abs(curr_hist) / (abs(closes[-1]) * 0.002 + 1e-9))
            )
        elif curr_hist < 0 and curr_hist < prev_hist:
            direction = SignalDirection.BEARISH
            confidence = max(
                0.0, min(0.6, abs(curr_hist) / (abs(closes[-1]) * 0.002 + 1e-9))
            )
        elif curr_hist > 0:
            direction = SignalDirection.BULLISH
            confidence = 0.15
        elif curr_hist < 0:
            direction = SignalDirection.BEARISH
            confidence = 0.15

        # Divergence detection (price makes new low but MACD doesn't)
        if len(closes) >= 20 and len(macd_line) >= 20:
            price_low = min(closes[-20:])
            price_prev_low = min(closes[-40:-20]) if len(closes) >= 40 else price_low
            macd_low = min(macd_line[-20:])
            macd_prev_low = (
                min(macd_line[-40:-20]) if len(macd_line) >= 40 else macd_low
            )

            if (
                closes[-1] <= price_low
                and price_low < price_prev_low
                and macd_low > macd_prev_low
            ):
                divergence = "bullish"
                direction = SignalDirection.BULLISH
                confidence = min(1.0, max(confidence, 0.7))
            elif closes[-1] >= max(closes[-20:]) and max(closes[-20:]) > max(
                closes[-40:-20] if len(closes) >= 40 else closes[-20:]
            ):
                macd_high = max(macd_line[-20:])
                macd_prev_high = (
                    max(macd_line[-40:-20]) if len(macd_line) >= 40 else macd_high
                )
                if macd_high < macd_prev_high:
                    divergence = "bearish"
                    direction = SignalDirection.BEARISH
                    confidence = min(1.0, max(confidence, 0.7))

        return Signal(
            indicator="macd",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "macd_line": round(curr_macd, 6),
                "signal_line": round(curr_signal, 6),
                "histogram": round(curr_hist, 6),
                "crossover": crossover,
                "divergence": divergence,
            },
        )

    def compute_histogram_series(self, candles: list, n: int = 12) -> list:

        # sadp: R28  # indicator compute: fail-loudly(R28)
        """
        Return the last `n` MACD histogram values as a list (oldest→newest).

        Single O(N) computation — more efficient than calling compute() N times.
        Used by the simulator snapshot to populate macd_histogram_buf, which
        feeds detect_macd_taper() in the confidence gate.

        Returns [] if fewer candles than the MACD warmup period.
        """
        closes = [c.close for c in candles]
        min_len = self.slow + self.signal_period
        if len(closes) < min_len:
            return []
        ema_fast = _ema(closes, self.fast)
        ema_slow = _ema(closes, self.slow)
        macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
        signal_line = _ema(macd_line, self.signal_period)
        histogram = [m - s for m, s in zip(macd_line, signal_line)]
        return histogram[-n:]


# ---------------------------------------------------------------------------
# 3b. MACD Consolidation / Taper Detection
# ---------------------------------------------------------------------------


def detect_macd_taper(histogram: list, lookback: int = 8) -> dict:
    """
    Detects MACD histogram deceleration and consolidation patterns.

    Three patterns:
      BULLISH TAPER  — negative bars shrinking toward zero (bearish momentum
                       decelerating); fold signal strengthened.
      BEARISH TAPER  — positive bars shrinking toward zero (bullish momentum
                       stalling); scrum confidence reduced.
      OSCILLATION WEDGE — alternating +/- bars with decreasing amplitude,
                       forming a converging triangle (pure consolidation /
                       indecision); breakout imminent, direction unknown.

    Args:
        histogram: list of recent MACD histogram values (newest last)
        lookback:  number of bars to analyse (default 8, ~8h on 1h TF)

    Returns dict:
        taper_type      : 'bullish' | 'bearish' | 'wedge' | 'none'
        taper_strength  : 0.0–1.0  (fraction of lookback bars tapering)
        bars_tapering   : int      (consecutive bars in taper)
        toward_cross    : bool     (MACD approaching zero line)
        consolidating   : bool     (any meaningful taper detected)
    """
    result = {
        "taper_type": "none",
        "taper_strength": 0.0,
        "bars_tapering": 0,
        "toward_cross": False,
        "consolidating": False,
    }

    if len(histogram) < lookback:
        return result

    recent = histogram[-lookback:]
    abs_vals = [abs(v) for v in recent]
    n = len(recent)

    # ── Pattern 1 & 2: directional taper ─────────────────────────────────
    # Count consecutive bars on the same side of zero, shrinking in magnitude
    def _directional_taper(bars, target_sign):
        """How many consecutive bars of target_sign are getting smaller?"""
        taper = 0
        prev_abs = None
        for v in reversed(bars):
            sign = 1 if v > 0 else (-1 if v < 0 else 0)
            if sign != target_sign:
                break
            abs_v = abs(v)
            if prev_abs is None or abs_v <= prev_abs:
                taper += 1
                prev_abs = abs_v
            else:
                break
        return taper

    bull_taper = _directional_taper(recent, -1)  # negative bars shrinking
    bear_taper = _directional_taper(recent, +1)  # positive bars shrinking

    # ── Pattern 3: oscillation wedge ─────────────────────────────────────
    # Alternating signs AND decreasing peak amplitude in both halves
    signs = [1 if v > 0 else -1 for v in recent if v != 0]
    alt_count = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
    alternating = alt_count >= len(signs) - 2 if len(signs) > 2 else False

    first_half_peak = max(abs_vals[: n // 2]) if n >= 4 else 0
    second_half_peak = max(abs_vals[n // 2 :]) if n >= 4 else 0
    amplitude_shrinking = second_half_peak < first_half_peak * 0.85

    # Overall bar shrinkage fraction (any direction)
    taper_count = sum(1 for i in range(1, n) if abs_vals[i] < abs_vals[i - 1])
    taper_strength = taper_count / max(n - 1, 1)

    # Approaching zero line?
    toward_cross = abs_vals[-1] < abs_vals[0] * 0.5 if abs_vals[0] > 1e-9 else False

    # ── Classify ──────────────────────────────────────────────────────────
    if alternating and amplitude_shrinking and taper_strength >= 0.5:
        result.update(
            {
                "taper_type": "wedge",
                "taper_strength": round(taper_strength, 3),
                "bars_tapering": taper_count,
                "toward_cross": toward_cross,
                "consolidating": True,
            }
        )
    elif bull_taper >= 3:
        result.update(
            {
                "taper_type": "bullish",
                "taper_strength": round(bull_taper / n, 3),
                "bars_tapering": bull_taper,
                "toward_cross": toward_cross,
                "consolidating": True,
            }
        )
    elif bear_taper >= 3:
        result.update(
            {
                "taper_type": "bearish",
                "taper_strength": round(bear_taper / n, 3),
                "bars_tapering": bear_taper,
                "toward_cross": toward_cross,
                "consolidating": True,
            }
        )
    elif taper_strength >= 0.65:
        # General taper without clear directional bias
        dominant_sign = 1 if sum(recent) > 0 else -1
        t_type = "bearish" if dominant_sign > 0 else "bullish"
        result.update(
            {
                "taper_type": t_type,
                "taper_strength": round(taper_strength, 3),
                "bars_tapering": taper_count,
                "toward_cross": toward_cross,
                "consolidating": True,
            }
        )

    return result


# ---------------------------------------------------------------------------
# 4. Stochastic RSI
# ---------------------------------------------------------------------------
class StochasticRSI:
    """
    Stochastic RSI: Stochastic oscillator applied to RSI values.
    K line = smoothed StochRSI, D line = SMA of K.
    """

    def __init__(
        self,
        rsi_period: int = 14,
        stoch_period: int = 14,
        k_smooth: int = 3,
        d_smooth: int = 3,
        weight: float = 1.0,
    ):
        self.rsi_period = rsi_period
        self.stoch_period = stoch_period
        self.k_smooth = k_smooth
        self.d_smooth = d_smooth
        self.weight = weight

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        closes = [c.close for c in candles]
        needed = self.rsi_period + self.stoch_period + self.d_smooth + 5
        if len(closes) < needed:
            return Signal(
                "stochastic_rsi", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        # Compute RSI series
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(0, d) for d in deltas]
        losses = [max(0, -d) for d in deltas]

        rsi_values = []
        avg_gain = sum(gains[: self.rsi_period]) / self.rsi_period
        avg_loss = sum(losses[: self.rsi_period]) / self.rsi_period

        rs_indeterminate = False
        for i in range(self.rsi_period, len(deltas)):
            avg_gain = (avg_gain * (self.rsi_period - 1) + gains[i]) / self.rsi_period
            avg_loss = (avg_loss * (self.rsi_period - 1) + losses[i]) / self.rsi_period
            # Wilder defines RS with no losses but SOME gains as an
            # infinite ratio, i.e. RSI 100. That case is defined and is
            # left exactly as it was. With neither gains nor losses the
            # ratio is 0/0 and there is no reading. The flag records the
            # state at the LAST bar, which is the reading the vote uses.
            #
            # Gains and losses are max(0, close[i] - close[i-1]) over
            # adjacent bars, exactly 0.0 on a halt, and Wilder smoothing
            # of exact zeros stays exactly 0.0, so `<= 0.0` is sound.
            rs_indeterminate = avg_gain <= 0.0 and avg_loss <= 0.0
            rs = avg_gain / (avg_loss + 1e-9)
            rsi_values.append(100 - 100 / (1 + rs))

        if rs_indeterminate or len(rsi_values) < self.stoch_period:
            return Signal(
                "stochastic_rsi", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        # Stochastic of RSI
        #
        # v3.24.25 — bounded to the tail the consumers actually reach.
        # Only k_line[-1], k_line[-2], d_line[-1] and d_line[-2] are read
        # (see the K/D crossover below). Walking the dependency chain
        # backwards:
        #
        #   d_line[-2] = mean(k_line[-4:-1])   -> needs k_line[-4:]
        #   k_line[-4] = mean(stoch[-6:-3])    -> needs stoch[-6:]
        #
        # so exactly k_smooth + d_smooth trailing stoch values suffice,
        # and every k_line entry those reads touch is past _sma's
        # shorter-divisor warm-up branch, so the values are unchanged.
        #
        # Taking FEWER than k_smooth + d_smooth would silently alter
        # k_line[-2] / d_line[-2], which drive the crossover tests that
        # emit confidence-0.8 SCRUM/FOLD signals. The max() keeps the
        # original full-range behaviour on short inputs.
        _stoch_need = self.k_smooth + self.d_smooth
        _stoch_from = max(self.stoch_period - 1, len(rsi_values) - _stoch_need)
        stoch_rsi = []
        stoch_indeterminate = False
        for i in range(_stoch_from, len(rsi_values)):
            window = rsi_values[i - self.stoch_period + 1 : i + 1]
            low = min(window)
            high = max(window)
            # A stochastic is a position within a range. An RSI window
            # with no range has no position in it, and every value this
            # loop computes feeds the K and D lines the crossover votes
            # on -- the loop is already bounded to exactly that tail.
            #
            # `high` and `low` are the max and min of the window itself,
            # so this IS the source-quantity test, applied to the series
            # the stochastic is actually positioned in.
            if high - low <= 0.0:
                stoch_indeterminate = True
            stoch_rsi.append((rsi_values[i] - low) / (high - low + 1e-9) * 100)

        if stoch_indeterminate:
            return Signal(
                "stochastic_rsi", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        # K line (SMA smoothing)
        k_line = _sma(stoch_rsi, self.k_smooth)
        # D line (SMA of K)
        d_line = _sma(k_line, self.d_smooth)

        k = k_line[-1]
        d = d_line[-1]
        prev_k = k_line[-2] if len(k_line) > 1 else k
        prev_d = d_line[-2] if len(d_line) > 1 else d

        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover = ""

        # K/D crossover
        if prev_k <= prev_d and k > d:
            crossover = "bullish"
            if k < 30:
                direction = SignalDirection.BULLISH
                confidence = 0.8
            elif k < 50:
                direction = SignalDirection.BULLISH
                confidence = 0.5
            else:
                direction = SignalDirection.BULLISH
                confidence = 0.25
        elif prev_k >= prev_d and k < d:
            crossover = "bearish"
            if k > 70:
                direction = SignalDirection.BEARISH
                confidence = 0.8
            elif k > 50:
                direction = SignalDirection.BEARISH
                confidence = 0.5
            else:
                direction = SignalDirection.BEARISH
                confidence = 0.25

        # Extreme zones without crossover
        if not crossover:
            if k < 15:
                direction = SignalDirection.BULLISH
                confidence = 0.5
            elif k > 85:
                direction = SignalDirection.BEARISH
                confidence = 0.5
            elif k < 30:
                direction = SignalDirection.BULLISH
                confidence = 0.2
            elif k > 70:
                direction = SignalDirection.BEARISH
                confidence = 0.2

        return Signal(
            indicator="stochastic_rsi",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={"k": round(k, 2), "d": round(d, 2), "crossover": crossover},
        )


# ---------------------------------------------------------------------------
# 5. Ichimoku Cloud
# ---------------------------------------------------------------------------
class IchimokuCloud:
    """
    Ichimoku Kinko Hyo — full correct five-line implementation.
    Developed by Goichi Hosoda (1969). Genuinely predictive because the cloud
    is displaced 26 periods forward, making future S/R levels visible now.

    LINES (all correct-indexed — inclusive of current candle):
      Tenkan-sen  (T): (9-period H+L)/2   — fast conversion line
      Kijun-sen   (K): (26-period H+L)/2  — base line, dynamic S/R
      Senkou A (SpA):  (T+K)/2 plotted 26 ahead — leading span A
      Senkou B (SpB):  (52-period H+L)/2 plotted 26 ahead — leading span B
      Chikou   (Ch):   current close plotted 26 BEHIND — lagging confirmation

    CLOUD DISPLACEMENT (critical for correctness):
      The CURRENT cloud = SpA/SpB computed from data 26 candles ago.
      The FUTURE cloud  = SpA/SpB computed from current data (appears 26 ahead).
      A TWIST occurs when future SpA crosses SpB — signals regime change in ~26 bars.

    PREDICTIVE HIERARCHY (strongest → weakest):
      1. Future cloud TWIST         — regime change coming in 26 bars
      2. Cloud BREAKOUT             — price exiting cloud confirms new trend
      3. TK CROSS location-adjusted — above cloud=strong, inside=weak, below=weak
      4. Chikou span confirmation   — current close vs 26-bar-ago landscape
      5. Kijun bounce               — textbook institutional S/R entry
      6. Price vs cloud (regime)    — ongoing trend context
      7. SpB flatness               — multi-period consolidation S/R level

    ACCUMULATION TUNING:
      - Future twist to bull + price below/inside cloud = PREMIUM fold window
      - Kijun bounce in bull regime = high-quality fold entry (buy the dip)
      - TK cross above cloud = scrum confirmation (momentum peak)
      - San-Ko-Shu bull + price at upper BB = harvest; at lower BB = accumulate
      - Future twist to bear + price above cloud = harvest NOW
    """

    def __init__(
        self, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52, weight: float = 1.0
    ):
        self.tenkan = tenkan
        self.kijun = kijun
        self.senkou_b = senkou_b
        self.weight = weight

    @staticmethod
    def _mid(candles: list, start: int, period: int) -> float:
        """(highest high + lowest low) / 2 over candles[start:start+period].
        Correct: _mid(candles, n-period, period) gives midpoint of LAST `period` candles.
        """
        if start < 0 or period <= 0 or start + period > len(candles):
            return 0.0
        w = candles[start : start + period]
        return (max(c.high for c in w) + min(c.low for c in w)) / 2.0

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        n = len(candles)
        T = self.tenkan  #  9
        K = self.kijun  # 26
        B = self.senkou_b  # 52
        D = self.kijun  # displacement = 26

        # Minimum: SpB(52) + displacement(26) + 1 for prev-period comparison
        if n < B + D + 1:
            return Signal(
                "ichimoku", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        price = candles[-1].close

        # ── CURRENT LINES ────────────────────────────────────────────────
        # Correct: period-midpoint INCLUSIVE of current candle
        #   Tenkan = midpoint of candles[n-T : n]   ← _mid(n-T, T)
        #   Kijun  = midpoint of candles[n-K : n]   ← _mid(n-K, K)
        tenkan = self._mid(candles, n - T, T)
        kijun = self._mid(candles, n - K, K)

        # Previous period (for TK crossover and future-cloud twist)
        p_tenkan = self._mid(candles, n - T - 1, T)
        p_kijun = self._mid(candles, n - K - 1, K)

        # ── CURRENT CLOUD (displaced D periods — what price compares against NOW) ─
        # SpA at time (n-1) = (Tenkan_D_ago + Kijun_D_ago) / 2
        # Tenkan D ago = midpoint of candles[n-D-T : n-D]
        t_D = self._mid(candles, n - D - T, T)  # Tenkan D periods ago
        k_D = self._mid(candles, n - D - K, K)  # Kijun  D periods ago
        curr_spa = (t_D + k_D) / 2.0
        curr_spb = self._mid(candles, n - D - B, B)  # SpB D periods ago

        cloud_top = max(curr_spa, curr_spb)
        cloud_bottom = min(curr_spa, curr_spb)
        cloud_thick = cloud_top - cloud_bottom
        cloud_thick_pct = cloud_thick / (price + 1e-9)

        # ── FUTURE CLOUD (computed now — appears D periods ahead — PREDICTIVE) ─
        fut_spa = (tenkan + kijun) / 2.0
        fut_spb = self._mid(candles, n - B, B)  # 52-period midpoint of current data

        p_fut_spa = (p_tenkan + p_kijun) / 2.0
        p_fut_spb = self._mid(candles, n - B - 1, B)  # SpB one period ago

        fut_bull = fut_spa > fut_spb
        # Twist: future SpA crossing SpB — regime change in D candles
        twist_bull = p_fut_spa <= p_fut_spb and fut_spa > fut_spb
        twist_bear = p_fut_spa >= p_fut_spb and fut_spa < fut_spb

        # ── CHIKOU SPAN ──────────────────────────────────────────────────
        # Current close compared to close D periods ago
        ch_price = candles[n - D - 1].close if n > D else price
        chikou_bull = price > ch_price
        chikou_bear = price < ch_price
        # Extra: Chikou vs the cloud of D periods ago (triple-layer confirmation)
        chikou_above_hist_cloud = chikou_bull and price > cloud_top
        chikou_below_hist_cloud = chikou_bear and price < cloud_bottom

        # ── TK CROSS + LOCATION ──────────────────────────────────────────
        tk_bull_cross = p_tenkan <= p_kijun and tenkan > kijun
        tk_bear_cross = p_tenkan >= p_kijun and tenkan < kijun
        tk_above_cloud = min(tenkan, kijun) > cloud_top
        tk_inside_cloud = (
            min(tenkan, kijun) <= cloud_top and max(tenkan, kijun) >= cloud_bottom
        )
        tk_below_cloud = max(tenkan, kijun) < cloud_bottom

        # ── PRICE POSITION ───────────────────────────────────────────────
        above_cloud = price > cloud_top
        below_cloud = price < cloud_bottom

        # Cloud breakout (price exiting cloud this candle)
        prev_p = candles[-2].close if n >= 2 else price
        prev_above = prev_p > cloud_top
        prev_below = prev_p < cloud_bottom
        prev_inside = not prev_above and not prev_below
        breakout_up = above_cloud and prev_inside
        breakout_down = below_cloud and prev_inside

        # ── KIJUN DYNAMICS ───────────────────────────────────────────────
        p_kijun2 = self._mid(candles, n - K - 2, K)
        kijun_rising = kijun > p_kijun2
        kijun_flat = abs(kijun - p_kijun2) < price * 0.0003

        # Kijun bounce: price within 0.8% of Kijun (premium entry signal)
        kijun_bounce_bull = above_cloud and kijun * 0.992 <= price <= kijun * 1.008
        kijun_bounce_bear = below_cloud and kijun * 0.992 <= price <= kijun * 1.008

        # ── TENKAN DIRECTION ─────────────────────────────────────────────
        p_tenkan2 = self._mid(candles, n - T - 2, T)
        tenkan_rising = tenkan > p_tenkan2
        price_above_tenkan = price > tenkan

        # ── SENKOU B FLATNESS ────────────────────────────────────────────
        # Flat SpB = multi-period consolidation zone = strongest static S/R
        p_fut_spb2 = self._mid(candles, n - B - 2, B)
        spb_flat = abs(fut_spb - p_fut_spb2) < price * 0.0005

        # ── SAN-KO-SHU ───────────────────────────────────────────────────
        sks_bull = above_cloud and chikou_bull and fut_bull
        sks_bear = below_cloud and chikou_bear and not fut_bull

        # ── CONFIDENCE SCORING ───────────────────────────────────────────
        # Score represents directional conviction. Final direction uses sign.
        score = 0.0

        # Cloud thickness multiplier (thick = stronger S/R signal)
        tw = min(1.6, 1.0 + cloud_thick_pct * 8.0)

        # 1. Future cloud TWIST — most predictive signal
        if twist_bull:
            score += 0.30  # regime change coming
        elif twist_bear:
            score -= 0.30

        # 2. Cloud breakout — momentum confirmation
        if breakout_up:
            score += 0.22
        elif breakout_down:
            score -= 0.22

        # 3. TK cross — location-adjusted strength
        if tk_bull_cross:
            score += 0.42 if tk_above_cloud else (0.18 if tk_inside_cloud else 0.08)
        elif tk_bear_cross:
            score -= 0.42 if tk_below_cloud else (0.18 if tk_inside_cloud else 0.08)

        # 4. Chikou confirmation
        if chikou_above_hist_cloud:
            score += 0.18  # three layers of bullish confirmation
        elif chikou_bull:
            score += 0.12
        elif chikou_below_hist_cloud:
            score -= 0.18
        elif chikou_bear:
            score -= 0.12

        # 5. Kijun bounce (institutional entry signal)
        if kijun_bounce_bull:
            score += 0.15
        elif kijun_bounce_bear:
            score -= 0.12

        # 6. Price vs cloud (regime bias — weighted by thickness)
        if above_cloud:
            score += 0.18 * tw
        elif below_cloud:
            score -= 0.18 * tw
        else:
            score -= 0.04  # inside = slight indecision penalty

        # 7. Future cloud direction
        if fut_bull:
            score += 0.10
        else:
            score -= 0.10

        # 8. San-Ko-Shu triple alignment
        if sks_bull:
            score += 0.15
        elif sks_bear:
            score -= 0.15

        # 9. SpB flatness (strong static S/R)
        if spb_flat:
            score += 0.06 if above_cloud else (-0.04 if below_cloud else 0.0)

        # 10. Tenkan momentum
        if tenkan_rising and price_above_tenkan:
            score += 0.05
        elif not tenkan_rising and not price_above_tenkan:
            score -= 0.05

        # Direction + confidence
        if score > 0.08:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, score))
        elif score < -0.08:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(score)))
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="ichimoku",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "price_vs_cloud": (
                    "above" if above_cloud else "below" if below_cloud else "inside"
                ),
                "cloud_top": round(cloud_top, 4),
                "cloud_bottom": round(cloud_bottom, 4),
                "cloud_thick_pct": round(cloud_thick_pct * 100, 2),
                "tenkan": round(tenkan, 4),
                "kijun": round(kijun, 4),
                "fut_cloud_bull": fut_bull,
                "twist_to_bull": twist_bull,
                "twist_to_bear": twist_bear,
                "chikou_bull": chikou_bull,
                "chikou_bear": chikou_bear,
                "chikou_above_cloud": chikou_above_hist_cloud,
                "tk_bull_cross": tk_bull_cross,
                "tk_bear_cross": tk_bear_cross,
                "tk_above_cloud": tk_above_cloud,
                "tk_inside_cloud": tk_inside_cloud,
                "tk_below_cloud": tk_below_cloud,
                "breakout_up": breakout_up,
                "breakout_down": breakout_down,
                "kijun_bounce_bull": kijun_bounce_bull,
                "kijun_bounce_bear": kijun_bounce_bear,
                "kijun_rising": kijun_rising,
                "kijun_flat": kijun_flat,
                "spb_flat": spb_flat,
                "san_ko_shu_bull": sks_bull,
                "san_ko_shu_bear": sks_bear,
                "score": round(score, 4),
            },
        )


# ---------------------------------------------------------------------------
# 6. Volume Analysis
# ---------------------------------------------------------------------------
# Helper: simple EMA used for MFI smoothing (already defined as _ema above)


class VolumeAnalysis:
    """
    Multi-indicator volume analysis suite.

    INDICATORS (in order of practical usefulness for accumulation):

    1. OBV DIVERGENCE (most powerful signal)
         Price makes lower low but OBV makes higher low  → bullish divergence
         = smart money accumulating despite price decline → strong FOLD signal
         Price makes higher high but OBV makes lower high → bearish divergence
         = distribution at peak levels                   → strong SCRUM signal

    2. MFI (Money Flow Index) — volume-weighted RSI (14-period)
         MFI > 80: volume-confirmed overbought            → SCRUM signal
         MFI < 20: volume-confirmed oversold              → FOLD signal
         MFI divergence mirrors OBV divergence but filters by volume weight.

    3. CMF (Chaikin Money Flow) — 20-period
         CMF > +0.05: net buying pressure (accumulation)
         CMF < -0.05: net selling pressure (distribution)
         CMF near zero: balanced / consolidation

    4. A/D LINE TREND — Accumulation/Distribution
         A/D rising while price flat/falling → underlying accumulation
         A/D falling while price flat/rising → underlying distribution

    5. VOLUME RATIO — current vs N-period average
         ratio > 1.5: above-average participation
         ratio > 2.5: significant spike
         Direction of the candle determines bullish/bearish interpretation.

    6. OBV TREND — slow trend component
         OBV EMA(5) vs EMA(20): basic direction of money flow.

    ACCUMULATION STRATEGY WIRING:
         Bullish divergence (OBV or MFI) → fold confidence +0.15 to +0.20
         Volume spike on DOWN candle + OBV rising → capitulation fold +0.18
         MFI < 20 → fold +0.12
         MFI > 80 → scrum +0.10
         Bearish divergence → scrum +0.12
         CMF strongly negative while OBV rising → premium fold (distribution
           near surface but net accumulation in the background)
    """

    def __init__(
        self,
        period: int = 20,
        spike_threshold_pct: float = VOLUME_SPIKE_PCT,
        weight: float = 0.8,
    ):
        self.period = period
        # `vol_ratio` in compute() is this candle's volume over the
        # window average: a RATIO, 1.0 for an average candle. The spike
        # limit is the same ratio, so it is carried in percent and
        # divided down here once -- see the Units note at the top.
        self.spike_threshold = spike_threshold_pct / PERCENT_PER_RATIO_UNIT
        self.weight = weight
        self.mfi_period = 14
        # A BAR COUNT, not a CMF reading. `cmf_period` read as a CMF
        # quantity, which is bounded [-1, 1], and 20 bars is not.
        self.chaikin_money_flow_period = 20
        self.div_lookback = 20  # candles to check for divergence

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _mfi(candles: list, period: int = 14) -> float:
        """Money Flow Index: volume-weighted RSI on typical price."""
        if len(candles) < period + 1:
            return 50.0
        pos_mf = neg_mf = 0.0
        for i in range(len(candles) - period, len(candles)):
            tp = (candles[i].high + candles[i].low + candles[i].close) / 3.0
            ptp = (
                candles[i - 1].high + candles[i - 1].low + candles[i - 1].close
            ) / 3.0
            mf = tp * candles[i].volume
            if tp > ptp:
                pos_mf += mf
            elif tp < ptp:
                neg_mf += mf
        # No negative money flow but SOME positive flow is the defined
        # case: the ratio diverges and MFI is 100. With NEITHER flow the
        # ratio is 0/0 and there is no reading, yet the test below
        # answered 100.0 -- the TOP of the scale, read by `mfi_ob` as
        # maximum overbought -- on a market where the typical price never
        # changed and so neither bucket was ever credited. 50.0 is this
        # function's own no-information value, returned by the
        # short-history branch above, and it leaves both `mfi_ob` and
        # `mfi_os` False.
        if pos_mf < 1e-9 and neg_mf < 1e-9:
            return 50.0
        if neg_mf < 1e-9:
            return 100.0
        return 100.0 - 100.0 / (1.0 + pos_mf / neg_mf)

    @staticmethod
    def _cmf(candles: list, period: int = 20) -> float:
        """Chaikin Money Flow: sum(CLV×Vol) / sum(Vol) over period."""
        if len(candles) < period:
            return 0.0
        window = candles[-period:]
        num = denom = 0.0
        for c in window:
            hl = c.high - c.low
            if hl > 0:
                clv = ((c.close - c.low) - (c.high - c.close)) / hl
            else:
                clv = 0.0
            num += clv * c.volume
            denom += c.volume
        return num / denom if denom > 0 else 0.0

    @staticmethod
    def _obv(candles: list) -> list:
        """On-Balance Volume cumulative series."""
        obv = [0.0]
        for i in range(1, len(candles)):
            if candles[i].close > candles[i - 1].close:
                obv.append(obv[-1] + candles[i].volume)
            elif candles[i].close < candles[i - 1].close:
                obv.append(obv[-1] - candles[i].volume)
            else:
                obv.append(obv[-1])
        return obv

    def _detect_divergence(self, closes: list, indicator: list, lookback: int) -> str:
        """
        Detect price/indicator divergence over `lookback` candles.
        Returns: 'bullish' | 'bearish' | 'none'
        Bullish: price lower low + indicator higher low (accumulation)
        Bearish: price higher high + indicator lower high (distribution)
        """
        if len(closes) < lookback + 1 or len(indicator) < lookback + 1:
            return "none"
        curr_close = closes[-1]
        curr_ind = indicator[-1]
        past_close = min(closes[-lookback:])
        past_ind_at_price_low = indicator[
            -lookback + closes[-lookback:].index(past_close)
        ]

        # Bullish divergence: price at/near low but indicator higher than its prior low
        price_near_low = curr_close <= past_close * 1.03
        ind_higher = curr_ind > past_ind_at_price_low * 1.01
        if price_near_low and ind_higher:
            return "bullish"

        # Bearish divergence: price at/near high but indicator lower than its prior high
        past_high = max(closes[-lookback:])
        past_ind_at_price_high = indicator[
            -lookback + closes[-lookback:].index(past_high)
        ]
        price_near_high = curr_close >= past_high * 0.97
        ind_lower = curr_ind < past_ind_at_price_high * 0.99
        if price_near_high and ind_lower:
            return "bearish"

        return "none"

    # ── main compute ────────────────────────────────────────────────────────

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        min_len = (
            max(
                self.period,
                self.mfi_period,
                self.chaikin_money_flow_period,
                self.div_lookback,
            )
            + 5
        )
        if len(candles) < min_len:
            return Signal(
                "volume", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        closes = [c.close for c in candles]
        volumes = [c.volume for c in candles]

        # ── OBV ──────────────────────────────────────────────────────────
        obv = self._obv(candles)
        obv_ema_s = _ema(obv, 5)
        obv_ema_l = _ema(obv, self.period)
        obv_rising = obv_ema_s[-1] > obv_ema_l[-1]
        obv_accel = obv[-1] > obv[-2]  # OBV up this candle?

        # OBV divergence
        obv_div = self._detect_divergence(closes, obv, self.div_lookback)

        # ── MFI ──────────────────────────────────────────────────────────
        mfi = self._mfi(candles, self.mfi_period)
        mfi_ob = mfi > 80
        mfi_os = mfi < 20
        # MFI direction (compare to 3 candles ago for stability)
        (
            self._mfi(candles[:-3], self.mfi_period)
            if len(candles) > self.mfi_period + 3
            else mfi
        )

        # Simple MFI divergence: price new low vs MFI higher
        mfi_closes = closes[-self.div_lookback :]
        if mfi_os and closes[-1] <= min(mfi_closes) * 1.02:
            mfi_div = "bullish"
        elif mfi_ob and closes[-1] >= max(mfi_closes) * 0.98:
            mfi_div = "bearish"
        else:
            mfi_div = "none"

        # ── CMF ──────────────────────────────────────────────────────────
        cmf = self._cmf(candles, self.chaikin_money_flow_period)
        cmf_bull = cmf > 0.05
        cmf_bear = cmf < -0.05
        cmf_strong_bull = cmf > 0.15
        cmf_strong_bear = cmf < -0.15

        # ── A/D LINE ─────────────────────────────────────────────────────
        # NOTE: a forward recurrence — each element reads ad[-1] — so this
        # one genuinely needs the full history and cannot be tail-bounded
        # the way the window statistics above were.
        ad: list[float] = []
        for c in candles:
            hl = c.high - c.low
            clv = ((c.close - c.low) - (c.high - c.close)) / hl if hl > 0 else 0.0
            ad.append(clv * c.volume + (ad[-1] if ad else 0.0))

        ad_trend = ad[-1] - ad[-self.period]  # + = net accumulation
        ad_rising = ad[-1] > ad[-2]
        # A/D vs price divergence: A/D rising while price falling
        price_trend = closes[-1] - closes[-self.period]
        ad_price_div_bull = ad_trend > 0 and price_trend < 0  # A/D up, price down
        ad_price_div_bear = ad_trend < 0 and price_trend > 0  # A/D down, price up

        # ── VOLUME RATIO ─────────────────────────────────────────────────
        avg_vol = sum(volumes[-self.period :]) / self.period
        curr_vol = volumes[-1]
        # A window that traded no volume has no average for the current
        # bar to be measured against, so the ratio is 0/0 -- and
        # `is_spike`, `is_high` and `is_low` below are all statements
        # about that ratio. Volumes are SOURCE values and non-negative
        # (candles_from_raw refuses a negative one), so their sum is 0.0
        # exactly when every bar traded nothing.
        if avg_vol <= 0.0:
            return Signal(
                "volume", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )
        vol_ratio = curr_vol / (avg_vol + 1e-9)
        is_spike = vol_ratio > self.spike_threshold
        is_high = vol_ratio > 1.5
        is_low = vol_ratio < 0.6  # low-volume move = weak conviction

        # Current candle direction
        candle_up = candles[-1].close >= candles[-1].open
        candle_dn = not candle_up

        # ── CAPITULATION SIGNAL ──────────────────────────────────────────
        # High/spike volume on a DOWN candle BUT OBV still rising:
        # Aggressive selling is being absorbed by buyers = premium fold entry
        capitulation = is_spike and candle_dn and obv_accel

        # ── WEAK RALLY ───────────────────────────────────────────────────
        # Price up but volume below average = rally not supported = caution on scrum
        weak_rally = candle_up and is_low and obv_rising

        # ── VOLUME CONFIRMATION ──────────────────────────────────────────
        # Strong volume confirming directional move = high conviction
        vol_confirms_bull = is_high and candle_up and obv_accel
        vol_confirms_bear = is_high and candle_dn and not obv_accel

        # ── COMPOSITE SCORE ──────────────────────────────────────────────
        score = 0.0

        # OBV divergence (most powerful)
        if obv_div == "bullish":
            score += 0.35
        elif obv_div == "bearish":
            score -= 0.35

        # MFI extreme + divergence
        if mfi_div == "bullish" or mfi_os:
            score += 0.25
        elif mfi_div == "bearish" or mfi_ob:
            score -= 0.25

        # CMF
        if cmf_strong_bull:
            score += 0.20
        elif cmf_bull:
            score += 0.10
        elif cmf_strong_bear:
            score -= 0.20
        elif cmf_bear:
            score -= 0.10

        # A/D divergence
        if ad_price_div_bull:
            score += 0.15
        elif ad_price_div_bear:
            score -= 0.15

        # OBV trend
        if obv_rising:
            score += 0.10
        else:
            score -= 0.10

        # Volume confirmation
        if capitulation:
            score += 0.20  # sellers exhausted, buyers absorbing
        elif vol_confirms_bull:
            score += 0.10
        elif vol_confirms_bear:
            score -= 0.10
        elif weak_rally:
            score -= 0.08

        if score > 0.1:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(1.0, score))
        elif score < -0.1:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(1.0, abs(score)))
        else:
            direction = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="volume",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "obv_rising": obv_rising,
                "obv_divergence": obv_div,
                "mfi": round(mfi, 1),
                "mfi_overbought": mfi_ob,
                "mfi_oversold": mfi_os,
                "mfi_divergence": mfi_div,
                "cmf": round(cmf, 4),
                "cmf_bull": cmf_bull,
                "cmf_bear": cmf_bear,
                "ad_rising": ad_rising,
                "ad_price_div_bull": ad_price_div_bull,
                "ad_price_div_bear": ad_price_div_bear,
                "vol_ratio": round(vol_ratio, 2),
                "vol_spike": is_spike,
                "vol_high": is_high,
                "vol_low": is_low,
                "capitulation": capitulation,
                "weak_rally": weak_rally,
                "vol_confirms_bull": vol_confirms_bull,
                "vol_confirms_bear": vol_confirms_bear,
            },
        )


# ---------------------------------------------------------------------------
# 7. CM Slingshot Indicator
# ---------------------------------------------------------------------------


class ATRIndicator:
    """Average True Range (14-period) — volatility absolute measure.

    Used for:
      - Dynamic interval calibration (widen when ATR/price % is high)
      - Position size scaling (reduce size when volatility is extreme)
      - Stop-loss calibration for REH and shadow positions
      - Regime detection (ATR expansion = trend, contraction = range)
    """

    def __init__(self, period: int = 14):
        self.period = period

    def compute(self, candles: list) -> dict:
        if len(candles) < self.period + 1:
            return {
                "atr": 0.0,
                "atr_pct": 0.0,
                "expanding": False,
                "contracting": False,
                "extreme_high": False,
            }
        true_ranges = []
        for i in range(1, len(candles)):
            c, p = candles[i], candles[i - 1]
            tr = max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
            true_ranges.append(tr)
        # Wilder smoothing (exponential, alpha = 1/period)
        atr = sum(true_ranges[: self.period]) / self.period
        for tr in true_ranges[self.period :]:
            atr = (atr * (self.period - 1) + tr) / self.period
        price = candles[-1].close
        atr_pct = (atr / price) * 100 if price > 0 else 0.0
        # Trend vs range detection
        recent = true_ranges[-5:] if len(true_ranges) >= 5 else true_ranges
        older = true_ranges[-10:-5] if len(true_ranges) >= 10 else true_ranges
        expanding = sum(recent) / len(recent) > sum(older) / len(older) * 1.10
        contracting = sum(recent) / len(recent) < sum(older) / len(older) * 0.90
        return {
            "atr": round(atr, 8),
            "atr_pct": round(atr_pct, 4),  # ATR as % of price
            "expanding": expanding,  # volatility growing (trending)
            "contracting": contracting,  # volatility shrinking (coiling)
            "extreme_high": atr_pct > 5.0,  # >5% ATR = highly volatile
        }


class RSIIndicator:
    """Relative Strength Index (Wilder 14-period) with divergence detection.

    v3.19.18: refactored from dict-returning to Signal-returning compute()
    so it can be wired into VotingEngine. Closes the last UNWIRED indicator
    from the v3.19.16 indicator-coverage audit. The dict-form metrics are
    still available via ``_compute_metrics()`` for any consumer that needs
    the rich detail.

    Used for:
      - Overbought (>70) / oversold (<30) regime signals
      - Bullish divergence (price new low, RSI higher low) = fold boost
      - Bearish divergence (price new high, RSI lower high) = scrum boost

    Signal mapping (v3.19.18):
      RSI > 70  → BEARISH (classical overbought; SCRUM-eligible signal)
      RSI < 30  → BULLISH (classical oversold; FOLD-eligible signal)
      else      → NEUTRAL
    Confidence scaled by distance from the neutral 50 line; divergence
    boosts confidence by +0.15 (capped at 1.0). Plain RSI is weighted
    lower (0.8) in VotingEngine than StochasticRSI (1.0) since StochRSI
    is the more refined two-stage indicator and they overlap.
    """

    def __init__(self, period: int = 14, weight: float = 0.8):
        self.period = period
        self.weight = weight

    def _compute_metrics(self, candles: list) -> dict:
        """Compute the rich-detail RSI dict. Pre-v3.19.18 callers used
        this signature (with the public name ``compute``). Now private,
        retained for any consumer needing the divergence / series detail."""
        if len(candles) < self.period + 1:
            # `rs_indeterminate` is False here on purpose: this is the
            # warm-up path, not a degenerate one. The rsi = 50.0 it
            # already returns maps to NEUTRAL at confidence 0.0, so the
            # behaviour of this branch is untouched.
            return {
                "rsi": 50.0,
                "overbought": False,
                "oversold": False,
                "bull_div": False,
                "bear_div": False,
                "rsi_series": [],
                "rs_indeterminate": False,
            }
        closes = [c.close for c in candles]
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        gains = [max(d, 0) for d in deltas]
        losses = [max(-d, 0) for d in deltas]
        avg_gain = sum(gains[: self.period]) / self.period
        avg_loss = sum(losses[: self.period]) / self.period
        rsi_series = []
        rs_indeterminate = False
        for i in range(self.period, len(deltas)):
            avg_gain = (avg_gain * (self.period - 1) + gains[i]) / self.period
            avg_loss = (avg_loss * (self.period - 1) + losses[i]) / self.period
            # Wilder's RS with no losses but SOME gains is an infinite
            # ratio, i.e. RSI 100, and that case is defined and left
            # alone. With neither gains nor losses it is 0/0. Resolved
            # through the epsilon that gave rs = 0.0 and rsi EXACTLY 0.0
            # -- the bottom of the scale -- which the mapping below reads
            # as maximum oversold and votes BULLISH at confidence 1.0000.
            rs_indeterminate = avg_gain <= 0.0 and avg_loss <= 0.0
            rs = avg_gain / (avg_loss + 1e-9)
            rsi_series.append(100 - 100 / (1 + rs))
        rsi = rsi_series[-1] if rsi_series else 50.0
        # Divergence: compare last 2 swing lows/highs
        bull_div = bear_div = False
        if len(rsi_series) >= 20 and len(closes) >= 20:
            p_lo1 = min(closes[-20:-10])
            p_lo2 = min(closes[-10:])
            r_lo1 = min(rsi_series[-20:-10])
            r_lo2 = min(rsi_series[-10:])
            bull_div = p_lo2 < p_lo1 and r_lo2 > r_lo1  # price lower, RSI higher
            p_hi1 = max(closes[-20:-10])
            p_hi2 = max(closes[-10:])
            r_hi1 = max(rsi_series[-20:-10])
            r_hi2 = max(rsi_series[-10:])
            bear_div = p_hi2 > p_hi1 and r_hi2 < r_hi1  # price higher, RSI lower
        return {
            "rsi": round(rsi, 2),
            "rs_indeterminate": rs_indeterminate,
            "overbought": rsi > 70,
            "oversold": rsi < 30,
            "bull_div": bull_div,
            "bear_div": bear_div,
            "rsi_series": rsi_series[-20:],  # last 20 values for chart overlay
        }

    def compute(self, candles: list, timeframe: str = "1h") -> "Signal":
        """v3.19.18 — Signal-returning compute() matching the VotingEngine
        protocol used by every other voter.

        Classical Wilder mapping:
          rsi > 70 → BEARISH (overbought)
          rsi < 30 → BULLISH (oversold)
          else     → NEUTRAL
        Confidence: scaled by absolute distance from the neutral 50 line,
        normalized so |rsi-50|=20 (i.e. crossing the 70 or 30 threshold)
        gives baseline confidence 0.4; saturates near 1.0 at the extremes.
        Divergence adds +0.15 to confidence (capped at 1.0).
        """
        metrics = self._compute_metrics(candles)
        if metrics["rs_indeterminate"]:
            return Signal("rsi", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight)
        rsi = metrics["rsi"]

        # Direction
        if rsi > 70:
            direction = SignalDirection.BEARISH
        elif rsi < 30:
            direction = SignalDirection.BULLISH
        else:
            direction = SignalDirection.NEUTRAL

        # Confidence — distance from neutral, scaled so a threshold cross
        # (|rsi-50|=20) starts producing meaningful signal
        dist = abs(rsi - 50.0)
        if dist <= 20.0:
            confidence = (dist / 20.0) * 0.4  # 0 at center, 0.4 at threshold
        else:
            # Beyond the threshold: linear ramp to ~1.0 at the extremes
            confidence = 0.4 + ((dist - 20.0) / 30.0) * 0.6
        confidence = min(1.0, max(0.0, confidence))

        # Divergence boost
        if metrics["bull_div"] and direction == SignalDirection.BULLISH:
            confidence = max(0.0, min(1.0, confidence + 0.15))
        elif metrics["bear_div"] and direction == SignalDirection.BEARISH:
            confidence = max(0.0, min(1.0, confidence + 0.15))

        # NEUTRAL signals have zero confidence by VotingEngine convention
        if direction == SignalDirection.NEUTRAL:
            confidence = 0.0

        return Signal(
            indicator="rsi",
            timeframe=timeframe,
            direction=direction,
            confidence=round(confidence, 4),
            weight=self.weight,
            details={
                "rsi": rsi,
                "overbought": metrics["overbought"],
                "oversold": metrics["oversold"],
                "bull_div": metrics["bull_div"],
                "bear_div": metrics["bear_div"],
            },
        )


# ── FVG (Fair Value Gap) — named constants (R44: no magic numbers) ────────
FVG_LOOKBACK = 24  # candles to scan for 3-candle gap patterns
FVG_PROXIMITY_PCT = 0.005  # "approaching from above": within 0.5% of FVG top
FVG_BULL_BOOST = 0.10  # fold confidence boost when in/near bullish FVG
FVG_BEAR_BOOST = 0.08  # scrum confidence boost when inside bearish FVG


class FVGIndicator:
    """Fair Value Gap detection — structural imbalance zones.

    3-candle FVG pattern:
      Bullish FVG: candles[k-1].high < candles[k+1].low  (gap up)
      Bearish FVG: candles[k-1].low  > candles[k+1].high (gap down)

    Price statistically returns to fill these gaps ~40-60% of the time
    within 48h (validated across BTC/ETH/SOL/ADA/GLD Apr24-Apr25 in Hop 3).
    When price is inside or approaching a bullish FVG from above, it acts
    as a fold magnet — accumulation confidence boost. When price is inside
    a bearish FVG, scrum confidence boost (expectation: gap fills up).

    Returns flat dict of booleans + nearest-zone bounds so downstream
    consumers (sim engine, battery engine, chart overlay) can read without
    coupling to the indicator class itself.
    """

    # sadp: R38, R42, R44
    def __init__(
        self, lookback: int = FVG_LOOKBACK, proximity_pct: float = FVG_PROXIMITY_PCT
    ):
        self.lookback = lookback
        self.proximity_pct = proximity_pct

    def compute(self, candles: list) -> dict:
        default = {
            "fvg_bull_zone": False,
            "fvg_bear_zone": False,
            "fvg_bull_count": 0,
            "fvg_bear_count": 0,
            "fvg_bull_top": 0.0,
            "fvg_bull_bot": 0.0,
            "fvg_bear_top": 0.0,
            "fvg_bear_bot": 0.0,
        }
        if len(candles) < 3:
            return default
        price = candles[-1].close
        if price <= 0:
            return default
        # Scan window: oldest index that still has k-1 and k+1 valid.
        # Use len(candles)-1 as exclusive upper bound so we never peek
        # past the last candle (it has no k+1).
        scan_end = len(candles) - 1
        scan_start = max(1, scan_end - self.lookback)
        bull_zones: list = []
        bear_zones: list = []
        for k in range(scan_start, scan_end):
            c_prev = candles[k - 1]
            c_next = candles[k + 1]
            if c_prev.high < c_next.low:
                bull_zones.append((c_next.low, c_prev.high))  # (top, bot)
            if c_prev.low > c_next.high:
                bear_zones.append((c_prev.low, c_next.high))  # (top, bot)
        # Bull trigger: price inside zone OR just above top (approaching
        # from above within proximity_pct). Pick highest-top active zone
        # (nearest to current price — fold magnet pulls downward).
        nearest_bull = None
        for top, bot in bull_zones:
            in_zone = bot <= price <= top
            approaching = (price > top) and (price <= top * (1.0 + self.proximity_pct))
            if in_zone or approaching:
                if nearest_bull is None or top > nearest_bull[0]:
                    nearest_bull = (top, bot)
        # Bear trigger: price inside zone (gap-down fill, scrum into strength).
        nearest_bear = None
        for top, bot in bear_zones:
            if bot <= price <= top:
                if nearest_bear is None or top > nearest_bear[0]:
                    nearest_bear = (top, bot)
        return {
            "fvg_bull_zone": nearest_bull is not None,
            "fvg_bear_zone": nearest_bear is not None,
            "fvg_bull_count": len(bull_zones),
            "fvg_bear_count": len(bear_zones),
            "fvg_bull_top": round(nearest_bull[0], 8) if nearest_bull else 0.0,
            "fvg_bull_bot": round(nearest_bull[1], 8) if nearest_bull else 0.0,
            "fvg_bear_top": round(nearest_bear[0], 8) if nearest_bear else 0.0,
            "fvg_bear_bot": round(nearest_bear[1], 8) if nearest_bear else 0.0,
        }


class SlingshotIndicator:
    """
    Slingshot — Volatility Squeeze + Directional Snapback.

    ── ATTRIBUTION, CORRECTED ────────────────────────────────────────────
    The NAME is Chris Moody's. The SQUEEZE is not. Moody's public-domain
    ``CM_SlingShotSystem`` (TradingView, 10-05-2014) is an EMA
    trend-and-pullback system — ``emaSlow = ema(close, 62)``,
    ``emaFast = ema(close, 38)`` — and contains no Bollinger Band, no
    Keltner Channel and no squeeze. The squeeze half descends from John
    Carter's TTM Squeeze, whose public-domain reference implementation is
    LazyBear's ``SQZMOM_LB``. The snapback half is John Bollinger's own
    published band rules. Each block below cites the source it implements.

    ── THE RULE MOODY'S SYSTEM SETTLES ───────────────────────────────────
    Moody's canonical BULLISH entry is ``emaFast > emaSlow and
    close < emaFast`` — bullish WHILE price sits below the reference
    line. Direction comes from a separate quantity (the EMA pair); it is
    never read off the price's own side of that line. The published
    pattern therefore REQUIRES "bullish" and "price below the line" to be
    expressible together.

    This class used to compute ``squeeze_bull = close > bb_mid``, which
    made those two mutually exclusive by construction. The snapback
    branch tests the same midline with the opposite sense, so the
    agreement bonus — which needs both at once — was a contradiction on a
    single tuple unpack and could not execute on any candle. Direction
    now comes from the canonical momentum value, and the contradiction is
    gone with it.

    ── SIGNAL 1: VOLATILITY SQUEEZE (Carter / TTM, via LazyBear) ─────────
    Squeeze ON when the Bollinger Bands close INSIDE the Keltner Channel:

        sqzOn = (lowerBB > lowerKC) and (upperBB < upperKC)

    Two different volatility measures are compared — standard deviation
    against true range — so "squeezed" has an absolute meaning. The
    squeeze FIRES on the release, the bar where ``sqzOn`` turns off.

    DIRECTION at the fire is the sign of the canonical momentum value:

        delta = close - (donchian_mid + sma(close, N)) / 2
        val   = linreg(delta, N, 0)          # val > 0 bullish

    ``val`` is a momentum quantity. ``close > sma`` is not, and the two
    disagree exactly when price coils under its own average while
    momentum turns up — the case the pattern exists to catch.

    ── SIGNAL 2: BAND SNAPBACK (Bollinger's rules 6 and 8) ───────────────
    Rule 8: a close OUTSIDE a band is a continuation signal, not a
    reversal. The re-entry is what converts it into a mean-reversion
    signal. So: a past close outside a band, then a later close back
    inside. A break below the lower band that re-enters is BULLISH.

    Bollinger requires re-entry and nothing more. The old code also
    demanded the close stay on the far side of the midline, which
    suppressed every reversal strong enough to cross the midline in one
    bar — the strongest ones — and was the term that collided with the
    direction test above.

    ── SEQUENCE, NOT COINCIDENCE ────────────────────────────────────────
    All three sources make this ordered: the TTM squeeze is a STATE that
    persists and then releases; Moody's conservative entry is literally a
    two-bar sequence; Bollinger's re-entry is on a LATER bar than the
    break. The bonus therefore rewards a snapback that resolves in the
    squeeze's direction on a bar AFTER the fire, not two flags that
    happen to be true on the same bar.

    ── WHY THIS IS NOT REDUNDANT WITH BB ────────────────────────────────
    BB detects WHERE price is relative to the bands (position).
    Slingshot detects the COMPRESSION→EXPANSION CYCLE (timing).
    A narrow band with price at 0.40 bb_pos = consolidation inside cloud.
    Slingshot fires when that consolidation ENDS and direction is clear.
    These are different questions about different market states.

    ── NO BLENDING ──────────────────────────────────────────────────────
    Every input here is raw candle data (close, high, low) or this
    class's own arithmetic over the module's shared scalar helpers. The
    Keltner Channel, the Donchian midline, the True Range series and the
    linear regression are all computed inside this class because the
    module has none of them. No other indicator's output is read.
    ``ATRIndicator``, ``BollingerBands``, ``IchimokuCloud`` and
    ``compute_heikin_ashi`` are deliberately NOT called. The previous
    docstring claimed "HA candle direction at expansion" as a direction
    input; the method never computed one, and importing one would be
    blending, so the claim is removed rather than honoured.
    """

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        squeeze_lookback: int = 30,
        snapback_lookback: int = 5,
        squeeze_threshold: float = 0.6,
        weight: float = 1.0,
        kc_mult: float = 1.5,
    ):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.squeeze_lookback = squeeze_lookback  # periods to measure avg bandwidth
        self.snapback_lookback = (
            snapback_lookback  # candles to look back for band break
        )
        self.squeeze_threshold = (
            squeeze_threshold  # fraction of avg bandwidth = squeeze
        )
        self.weight = weight
        # Keltner multiplier. Carter and StockCharts both specify BB 20/2.0
        # against KC 20/1.5. LazyBear's script multiplies the BB deviation
        # by multKC instead of its own mult -- a known quirk of that one
        # transcription. `bb_std` stays 2.0, which is what this class
        # already declared and what the two prose sources agree on.
        self.kc_mult = kc_mult

    @staticmethod
    def _bandwidth(upper: float, lower: float, mid: float) -> float:
        """BB bandwidth as fraction of midline (normalised)."""
        return (upper - lower) / (mid + 1e-9)

    @staticmethod
    def _linreg_endpoint(series: list) -> float:
        """Least-squares fit over ``series``, evaluated at the last point.

        This is Pine's ``linreg(src, length, 0)``: fit y = a + b*x over
        x = 0..N-1 oldest-to-newest, return the fitted value at x = N-1.
        Computed here because the module has no regression helper --
        ``linreg`` appears nowhere else in this file.
        """
        n = len(series)
        if n == 0:
            return 0.0
        if n == 1:
            return float(series[0])
        sum_x = n * (n - 1) / 2.0
        sum_xx = (n - 1) * n * (2 * n - 1) / 6.0
        sum_y = 0.0
        sum_xy = 0.0
        for x, y in enumerate(series):
            sum_y += y
            sum_xy += x * y
        denom = n * sum_xx - sum_x * sum_x
        if denom == 0.0:
            return sum_y / n
        slope = (n * sum_xy - sum_x * sum_y) / denom
        intercept = (sum_y - slope * sum_x) / n
        return intercept + slope * (n - 1)

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        n = len(candles)
        min_len = self.bb_period + self.squeeze_lookback + 2
        if n < min_len:
            return Signal(
                "slingshot", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        closes = [c.close for c in candles]
        # v3.24.22 — suffix-only. The loop below reads indices
        # range(n - win, n) where win = squeeze_lookback + 5, so that is
        # the exact depth required.
        _need = self.squeeze_lookback + 5
        sma_v = _sma_tail(closes, self.bb_period, tail=_need)
        std_v = _stdev_tail(closes, self.bb_period, tail=_need)

        # ── TRUE RANGE, COMPUTED HERE ────────────────────────────────
        # Carter's Keltner leg needs True Range. `_true_range` exists at
        # module level and `VortexIndicator` uses it, but it is inlined
        # here so that every input this class reads is unambiguously raw
        # candle data or its own arithmetic. `ATRIndicator.compute()`
        # would also return this number and is deliberately NOT called:
        # it is a voter's output, and reading it would be blending.
        tr_all = [candles[0].high - candles[0].low]
        for i in range(1, n):
            c = candles[i]
            prev_close = candles[i - 1].close
            tr_all.append(
                max(c.high - c.low, abs(c.high - prev_close), abs(c.low - prev_close))
            )
        trma_v = _sma_tail(tr_all, self.bb_period, tail=_need)

        # ── MOMENTUM DELTA SERIES, COMPUTED HERE ─────────────────────
        # delta = close - (donchian_mid + sma(close, N)) / 2, where
        # donchian_mid = (highest(high, N) + lowest(low, N)) / 2.
        # `IchimokuCloud` has a (highest+lowest)/2 helper; it is another
        # indicator's method, so this class builds its own.
        win = self.squeeze_lookback + 5
        delta_lo = max(0, n - win - self.bb_period)
        deltas: dict = {}
        for i in range(delta_lo, n):
            j0 = max(0, i - self.bb_period + 1)
            hi_n = max(candles[k].high for k in range(j0, i + 1))
            lo_n = min(candles[k].low for k in range(j0, i + 1))
            donchian_mid = (hi_n + lo_n) / 2.0
            sma_i = sma_v[i] if sma_v[i] is not None else closes[i]
            deltas[i] = closes[i] - (donchian_mid + sma_i) / 2.0

        # Build per-candle values (last squeeze_lookback + 5)
        bb = []
        for i in range(n - win, n):
            if i < self.bb_period:
                continue
            mid = sma_v[i]
            std = std_v[i]
            up = mid + self.bb_std * std
            lo = mid - self.bb_std * std
            bw = self._bandwidth(up, lo, mid)
            # Keltner Channel, this class's own: ma is the same SMA the
            # bands are built on, rangema is the SMA of True Range.
            rangema = trma_v[i] if trma_v[i] is not None else 0.0
            up_kc = mid + rangema * self.kc_mult
            lo_kc = mid - rangema * self.kc_mult
            # sqzOn = (lowerBB > lowerKC) and (upperBB < upperKC)
            sqz_on = (lo > lo_kc) and (up < up_kc)
            # val = linreg(delta, N, 0)
            seg = [
                deltas[k] for k in range(max(delta_lo, i - self.bb_period + 1), i + 1)
            ]
            val = self._linreg_endpoint(seg)
            bb.append((candles[i].close, up, lo, mid, bw, sqz_on, val, rangema))

        if len(bb) < self.squeeze_lookback:
            return Signal(
                "slingshot", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        last = len(bb) - 1
        (
            curr_close,
            curr_up,
            curr_lo,
            curr_mid,
            curr_bw,
            curr_sqz_on,
            curr_val,
            curr_rangema,
        ) = bb[last]

        # ── BANDWIDTH TELEMETRY ───────────────────────────────────────
        # Retained. This is no longer what decides a squeeze -- the
        # canonical BB-inside-KC test above is -- but `was_squeezed`,
        # `curr_bw`, `avg_bw`, `squeeze_depth` and `expansion_rate` are
        # all reported fields with live consumers, and a designed
        # behaviour is not deleted.
        avg_bw = sum(b[4] for b in bb[:-1]) / max(len(bb) - 1, 1)
        prev_bw = bb[-2][4] if len(bb) >= 2 else curr_bw
        prev2_bw = bb[-3][4] if len(bb) >= 3 else prev_bw
        recent_bw = [b[4] for b in bb[-4:]]

        # ── NO VOLATILITY UNIT, NO READING ────────────────────────────
        # `avg_bw` and `prev2_bw` are Bollinger bandwidths and
        # `curr_rangema` is the Keltner range. On a halted or pegged
        # window all three are zero, and `expansion_rate`,
        # `squeeze_depth` and `mom_norm` below each divide by one of
        # them. A squeeze is a statement about volatility; with no
        # volatility there is nothing to state. Measured on a halted
        # tape, `mom_norm` reached 6.6e7 and this indicator voted BEARISH
        # at confidence 1.0000 on weight 1.0.
        #
        # The bandwidths are 2*bb_std*sigma over the midline, so they
        # inherit `_stdev_tail`'s rounding and land on ULPs rather than
        # on zero. The decisive test is therefore on the SOURCE bars that
        # feed this window -- every high, low and close across the span
        # the `bb` loop reads. The three derived tests stay underneath as
        # subordinate floors; they can only make this abstain more often.
        _span = candles[max(0, n - win - self.bb_period) :]
        _span_px: list[float] = []
        for _c in _span:
            _span_px.extend((_c.high, _c.low, _c.close))
        if (
            _window_has_no_range(_span_px)
            or avg_bw <= 0.0
            or prev2_bw <= 0.0
            or curr_rangema <= 0.0
        ):
            return Signal(
                "slingshot", timeframe, SignalDirection.NEUTRAL, 0.0, self.weight
            )

        squeeze_bw_limit = avg_bw * self.squeeze_threshold
        n_squeezed = sum(1 for bw in recent_bw if bw < squeeze_bw_limit)
        was_squeezed = n_squeezed >= 2
        expanding = curr_bw > prev_bw * 1.02
        expansion_rate = (curr_bw - prev2_bw) / (prev2_bw + 1e-9)
        min_recent_bw = min(b[4] for b in bb[-4:])
        squeeze_depth = max(0.0, avg_bw - min_recent_bw) / (avg_bw + 1e-9)

        # ── SQUEEZE FIRE: THE RELEASE BAR ─────────────────────────────
        # StockCharts: the squeeze "is said to have 'fired'" when the
        # bands expand back outside the Keltner Channel. That is the
        # sqzOn -> not sqzOn transition. Find the most recent one.
        fire_idx = -1
        for k in range(last, 0, -1):
            if bb[k - 1][5] and not bb[k][5]:
                fire_idx = k
                break

        bars_since_fire = (last - fire_idx) if fire_idx >= 0 else -1
        # The release is live for `snapback_lookback` bars after it, which
        # is the same window the snapback search uses -- so a snapback can
        # confirm a fire without either being forced onto one bar.
        squeeze_live = 0 <= bars_since_fire <= self.snapback_lookback
        fire_val = bb[fire_idx][6] if fire_idx >= 0 else 0.0

        # Direction at the fire = sign of the momentum value. NOT the
        # price's side of the midline. `_excl(squeeze_bull, squeeze_bear)`
        # holds: a float is > 0, < 0, or neither.
        squeeze_bull = squeeze_live and fire_val > 0.0
        squeeze_bear = squeeze_live and fire_val < 0.0
        just_fired = squeeze_live

        # ── SQUEEZE CONFIDENCE ────────────────────────────────────────
        # Was `squeeze_depth * 3 + expansion_rate * 2 + 0.3`. Measured
        # across a 15,680-tuple grid, that expression was EXACTLY 1.0 on
        # 8,102 of 8,102 firings: `squeeze_depth` alone drives it past
        # the ceiling above 0.2334, so `min(1.0, ...)` pinned it. A
        # confidence that is always 1.0 carries no information, and it
        # also made the +0.15 agreement bonus a numeric no-op -- the
        # bonus re-clamps on the same line it is added.
        #
        # This is NOT a recalibration of those coefficients. It is the
        # canonical strength quantity replacing an invented one: TTM's
        # output IS the momentum histogram, so the squeeze's strength is
        # |val|, expressed in the volatility unit from the same formula
        # (the Keltner range). Both terms come from the published
        # definition. The clamp to [0, 1] is this codebase's `Signal`
        # contract, not Carter's -- TTM emits a raw histogram.
        mom_norm = abs(fire_val) / (curr_rangema + 1e-9)
        squeeze_conf = max(0.0, min(1.0, mom_norm))

        # ── SNAPBACK DETECTION ────────────────────────────────────────
        # Bollinger rule 8: a close outside the band is continuation; the
        # close back INSIDE is the signal. Re-entry is the only
        # requirement. The old `curr_close < curr_mid` conjunct is gone:
        # it has no basis in the published rules, it suppressed the
        # strongest reversals, and it was the term that contradicted the
        # direction test.
        snapback_type = ""
        snapback_conf = 0.0
        snapback_break_idx = -1

        for j in range(-self.snapback_lookback, -1):
            idx = len(bb) + j
            if idx < 1 or idx >= len(bb):
                continue

            past_close, past_up, past_lo, past_mid = bb[idx][:4]

            # BULLISH: past close below lower band, now back inside
            if past_close < past_lo:
                if curr_close > curr_lo:
                    penetration = (past_lo - past_close) / (past_lo + 1e-9)
                    # Better if the prior close was a significant penetration
                    # and current close is moving toward midline (not just touching lo)
                    midward = curr_close > past_close
                    snapback_conf = max(
                        0.0,
                        min(1.0, penetration * 8 + (0.2 if midward else 0.0) + 0.35),
                    )
                    snapback_type = "bullish_snapback"
                    snapback_break_idx = idx
                    break

            # BEARISH: past close above upper band, now back inside
            elif past_close > past_up:
                if curr_close < curr_up:
                    penetration = (past_close - past_up) / (past_up + 1e-9)
                    midward = curr_close < past_close
                    snapback_conf = max(
                        0.0,
                        min(1.0, penetration * 8 + (0.2 if midward else 0.0) + 0.35),
                    )
                    snapback_type = "bearish_snapback"
                    snapback_break_idx = idx
                    break

        # ── COMBINE ──────────────────────────────────────────────────
        # Squeeze takes precedence (predictive); snapback is reactive.
        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        active_type = ""

        if squeeze_bull:
            direction = SignalDirection.BULLISH
            confidence = squeeze_conf
            active_type = "squeeze_bull"
        elif squeeze_bear:
            direction = SignalDirection.BEARISH
            confidence = squeeze_conf
            active_type = "squeeze_bear"
        elif snapback_type == "bullish_snapback":
            direction = SignalDirection.BULLISH
            confidence = snapback_conf
            active_type = snapback_type
        elif snapback_type == "bearish_snapback":
            direction = SignalDirection.BEARISH
            confidence = snapback_conf
            active_type = snapback_type

        # A squeeze that outranks a CONTRADICTING snapback is a
        # precedence choice this codebase makes; canon has no such rule.
        # The precedence is kept -- it is a designed behaviour -- but the
        # discard is no longer silent. Measured at 7.2% of evaluations on
        # the grid, and it had no reported field at all.
        snapback_conflict = bool(
            snapback_type
            and (
                (squeeze_bull and snapback_type == "bearish_snapback")
                or (squeeze_bear and snapback_type == "bullish_snapback")
            )
        )

        # ── AGREEMENT BONUS ──────────────────────────────────────────
        # Sequential, per all three sources: the snapback's break must
        # land at or after the squeeze fire, and the re-entry (this bar)
        # must be strictly later than the fire. Two flags true on one bar
        # is not what the published pattern describes.
        sequential = (
            fire_idx >= 0 and bars_since_fire >= 1 and snapback_break_idx >= fire_idx
        )
        agree = False
        if sequential and squeeze_bull and snapback_type == "bullish_snapback":
            agree = True
            confidence = max(0.0, min(1.0, confidence + 0.15))
            active_type = "squeeze_bull+snapback"
        elif sequential and squeeze_bear and snapback_type == "bearish_snapback":
            agree = True
            confidence = max(0.0, min(1.0, confidence + 0.15))
            active_type = "squeeze_bear+snapback"

        return Signal(
            indicator="slingshot",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "slingshot_type": active_type,
                "squeeze_active": just_fired,
                "squeeze_bull": squeeze_bull,
                "squeeze_bear": squeeze_bear,
                "squeeze_depth": round(squeeze_depth, 4),
                "squeeze_conf": round(squeeze_conf, 4),
                "expansion_rate": round(expansion_rate, 4),
                "was_squeezed": was_squeezed,
                "snapback_type": snapback_type,
                "snapback_conf": round(snapback_conf, 4),
                "curr_bw": round(curr_bw, 6),
                "avg_bw": round(avg_bw, 6),
                "sqz_on": curr_sqz_on,
                "momentum": round(curr_val, 8),
                "fire_momentum": round(fire_val, 8),
                "mom_norm": round(mom_norm, 4),
                "bars_since_fire": bars_since_fire,
                "expanding": expanding,
                "snapback_conflict": snapback_conflict,
                "agree": agree,
            },
        )


# ===========================================================================
# VOTING ENGINE
# ===========================================================================

# Default indicator weights
DEFAULT_WEIGHTS = {
    "bollinger_bands": 1.0,
    "vortex": 0.9,
    "macd": 1.2,
    "stochastic_rsi": 1.0,
    "ichimoku": 1.1,
    "volume": 0.8,
    "slingshot": 1.0,
    "adx": 1.0,  # P2.9 / MEM-200 — trend-strength signal. Structural tier.
    # ── v3.19.17: indicator-coverage P0 closure (Trading-Discipline Arc #2) ──
    # Three voters previously built as full classes (Sessions 15-17 era) but
    # never wired into VotingEngine. Filed as UNWIRED in the v3.19.16
    # indicator-coverage audit. Wiring matches v3.19.16 ADX template.
    "kaufman_er": 1.0,  # Perry Kaufman Efficiency Ratio (regime classifier)
    "supertrend": 1.0,  # Oliver Seban ATR-trailing trend (reactive flip)
    "zscore": 0.9,  # Statistical extremity (longer window than BB)
    # ── v3.19.18: last UNWIRED indicator from v3.19.16 audit closed ──
    # Plain RSI weighted lower than StochRSI (1.0) because they overlap;
    # StochRSI is the more refined two-stage indicator. Both voting now —
    # the small redundancy is acceptable because RSI's classical 70/30
    # divergence detection still adds independent information.
    "rsi": 0.8,
}


class VotingEngine:
    """
    Aggregates signals from all indicators into a consensus vote.

    Features:
      - Weighted voting: each indicator's contribution is scaled by
        its weight × confidence.
      - Confidence threshold: consensus is only actionable if total
        confidence exceeds a minimum threshold.
      - Multi-timeframe: can aggregate across timeframes with higher
        timeframes weighted more heavily.
    """

    def __init__(
        self,
        confidence_threshold: float = 0.3,
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self._indicators = self._create_indicators()

    def _create_indicators(self) -> list:
        """Instantiate all indicator instances with configured weights."""
        return [
            BollingerBands(weight=self.weights.get("bollinger_bands", 1.0)),
            VortexIndicator(weight=self.weights.get("vortex", 0.9)),
            MACD(weight=self.weights.get("macd", 1.2)),
            StochasticRSI(weight=self.weights.get("stochastic_rsi", 1.0)),
            IchimokuCloud(weight=self.weights.get("ichimoku", 1.1)),
            VolumeAnalysis(weight=self.weights.get("volume", 0.8)),
            SlingshotIndicator(weight=self.weights.get("slingshot", 1.0)),
            # P2.9 / MEM-200 — ADX trend-strength indicator. Class fully
            # implemented since Session 15 but never consumed. Added to
            # address Manual Part 6 L4 (Oscillators Lead) objection.
            ADXIndicator(weight=self.weights.get("adx", 1.0)),
            # ── v3.19.17 (Trading-Discipline Arc #2 — indicator-coverage P0) ──
            # Three indicators built as full classes but never wired. Surfaced
            # by docs/audits/2026-05-22_indicator_coverage_audit.md and elevated
            # to P0 by operator 2026-05-22 ("the TA engine not being built
            # properly is also P0"). Wired into VotingEngine here; KaufmanER
            # additionally gets a discrete GateContext field + dedicated
            # SCRUM-suppressor gate (EfficiencyRatioRegimeGate) — see
            # gate_chain.py. The L3.b "ER is the Anti-pattern substitute"
            # claim in Part 6 — false at write time — becomes true with this
            # wiring.
            KaufmanERIndicator(weight=self.weights.get("kaufman_er", 1.0)),
            SupertrendIndicator(weight=self.weights.get("supertrend", 1.0)),
            ZScoreIndicator(weight=self.weights.get("zscore", 0.9)),
            # ── v3.19.18 — last UNWIRED indicator closed ──
            # Plain RSI refactored from dict-returning to Signal-returning
            # compute() in this ship (closes the v3.19.16 audit P0 fully).
            # See class docstring + _compute_metrics() for the dict form
            # that any external consumer of the rich detail still needs.
            RSIIndicator(weight=self.weights.get("rsi", 0.8)),
        ]

    def compute_all(
        self,
        candles: list[Candle],
        timeframe: str = "1h",
        symbol: Optional[str] = None,
    ) -> VotingSummary:

        # sadp: R28  # TA computation: fail-loudly on insufficient candles(R28)
        """
        Run all indicators on *candles* and aggregate into a VotingSummary.
        """
        signals: list[Signal] = []
        for ind in self._indicators:
            sig = ind.compute(candles, timeframe)
            signals.append(sig)

        return self._aggregate(signals, timeframe)

    def aggregate_multi_timeframe(
        self,
        summaries: list[VotingSummary],
        timeframe_weights: Optional[dict[str, float]] = None,
    ) -> VotingSummary:
        """
        Combine VotingSummaries from multiple timeframes.
        Higher timeframes are weighted more heavily by default.

        Default timeframe weights:
          5m=0.5, 15m=0.7, 1h=1.0, 4h=1.3, 1d=1.5
        """
        tf_weights = timeframe_weights or {
            "1m": 0.3,
            "5m": 0.5,
            "15m": 0.7,
            "30m": 0.85,
            "1h": 1.0,
            "2h": 1.1,
            "4h": 1.3,
            "6h": 1.35,
            "12h": 1.4,
            "1d": 1.5,
            "1w": 1.6,
        }

        all_signals: list[Signal] = []
        for summary in summaries:
            tf_w = tf_weights.get(summary.timeframe, 1.0)
            for sig in summary.signals:
                # Apply timeframe weight multiplier
                boosted = Signal(
                    indicator=sig.indicator,
                    timeframe=sig.timeframe,
                    direction=sig.direction,
                    confidence=sig.confidence,
                    weight=sig.weight * tf_w,
                    details=sig.details,
                    timestamp=sig.timestamp,
                )
                all_signals.append(boosted)

        return self._aggregate(all_signals, "multi")

    def _aggregate(self, signals: list[Signal], timeframe: str) -> VotingSummary:
        """Compute voting totals from a list of signals."""
        bullish = 0
        bearish = 0
        neutral = 0
        bull_score = 0.0
        bear_score = 0.0

        for sig in signals:
            ws = sig.weighted_score
            if sig.direction == SignalDirection.BULLISH:
                bullish += 1
                bull_score += abs(ws)
            elif sig.direction == SignalDirection.BEARISH:
                bearish += 1
                bear_score += abs(ws)
            else:
                neutral += 1

        net = bull_score - bear_score
        total_weight = sum(s.weight for s in signals) or 1.0
        consensus_conf = abs(net) / total_weight

        return VotingSummary(
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
            total_bullish_score=round(bull_score, 4),
            total_bearish_score=round(bear_score, 4),
            net_score=round(net, 4),
            consensus_confidence=round(min(1.0, consensus_conf), 4),
            signals=signals,
            timeframe=timeframe,
        )


# ---------------------------------------------------------------------------
# Convenience: single-function TA analysis
# ---------------------------------------------------------------------------
def analyze(
    candles_by_timeframe: dict[str, list[list[float]]],
    weights: Optional[dict[str, float]] = None,
) -> tuple[VotingSummary, dict[str, VotingSummary]]:
    """
    Run full TA analysis across multiple timeframes.

    Parameters
    ----------
    candles_by_timeframe : dict
        Maps timeframe string to OHLCV lists: {"1h": [[ts,O,H,L,C,V], ...], ...}
    weights : dict, optional
        Custom indicator weights.

    Returns
    -------
    (multi_summary, per_timeframe)
        Overall multi-timeframe consensus and per-timeframe summaries.
    """
    engine = VotingEngine(weights=weights)
    per_tf: dict[str, VotingSummary] = {}

    for tf, raw in candles_by_timeframe.items():
        candles = candles_from_raw(raw)
        per_tf[tf] = engine.compute_all(candles, tf)

    multi = engine.aggregate_multi_timeframe(list(per_tf.values()))
    return multi, per_tf


# ---------------------------------------------------------------------------
# Heikin Ashi candle conversion
# ---------------------------------------------------------------------------
@dataclass
class HACandle:
    """Heikin Ashi candle."""

    timestamp: float
    open: float
    high: float
    low: float
    close: float
    body_pct: float  # |close-open| / (high-low) as %; nan when no range


def compute_heikin_ashi(candles: list[Candle]) -> list[HACandle]:

    # sadp: R28  # indicator compute: fail-loudly(R28)
    """Convert standard candles to Heikin Ashi."""
    if not candles:
        return []
    ha: list[HACandle] = []
    for i, c in enumerate(candles):
        ha_close = (c.open + c.high + c.low + c.close) / 4
        if i == 0:
            ha_open = (c.open + c.close) / 2
        else:
            ha_open = (ha[-1].open + ha[-1].close) / 2
        ha_high = max(c.high, ha_open, ha_close)
        ha_low = min(c.low, ha_open, ha_close)
        hl_range = ha_high - ha_low
        # A bar whose Heikin Ashi high equals its low has no range, so
        # the body's share OF that range does not exist. It is not zero:
        # the only consumer of this field tests
        # `body_pct <= tight_body_pct`, and 0.0 is the TIGHTEST possible
        # reading, so resolving 0/0 that way manufactured a
        # consolidation out of a market that had not moved. `nan` is
        # what "no ratio" means, and that consumer names the case
        # explicitly rather than leaning on comparison semantics.
        #
        # `ha_high` and `ha_low` are the max and min of the same three
        # numbers, so this IS the source-quantity test for this bar.
        if hl_range <= 0.0:
            body_pct = math.nan
        else:
            body_pct = abs(ha_close - ha_open) / (hl_range + 1e-12) * 100
        ha.append(HACandle(c.timestamp, ha_open, ha_high, ha_low, ha_close, body_pct))
    return ha


# ---------------------------------------------------------------------------
# Bollinger Band Proximity + Landing Strip detection
# ---------------------------------------------------------------------------
@dataclass
class BBProximityResult:
    """Result of Bollinger Band proximity analysis."""

    upper: float
    middle: float
    lower: float
    bb_position: float  # 0 = at lower, 1 = at upper
    near_upper: bool  # Within tolerance of upper band
    near_lower: bool  # Within tolerance of lower band
    tolerance_pct: float  # Active tolerance %
    landing_strip: bool  # HA consolidation near BB detected
    landing_strip_side: str  # "upper" or "lower" or ""
    landing_strip_candles: int  # How many candles in the pattern
    ha_body_avg: float  # Average HA body % for recent candles
    consolidation_strength: float  # 0..1, how tight the consolidation is


def detect_bb_proximity(
    candles: list[Candle],
    tolerance_pct: float = 1.0,  # 0.25% to 5% — distance from band
    consolidation_threshold: float = 3.0,  # HA body % below this = tight
    min_pattern_candles: int = 2,
    max_pattern_candles: int = 10,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> BBProximityResult:
    """
    Detect proximity to Bollinger Bands with Heikin Ashi landing strip.

    A Landing Strip is:
      1. Price within `tolerance_pct` of upper or lower BB
      2. Heikin Ashi candles show tightening bodies (open ≈ close)
      3. HA body % drops below `consolidation_threshold` (1-3%)
      4. This pattern persists for `min_pattern_candles` to `max_pattern_candles`
      5. Indicates incoming reversal — high-confidence sell near upper,
         high-confidence buy near lower
    """
    closes = [c.close for c in candles]
    if len(closes) < bb_period:
        return BBProximityResult(
            0, 0, 0, 0.5, False, False, tolerance_pct, False, "", 0, 100.0, 0.0
        )

    # Compute BB
    # v3.24.22 — suffix-only; only [-1] is read below.
    sma = _sma_tail(closes, bb_period, tail=1)
    std = _stdev_tail(closes, bb_period, tail=1)
    mid = sma[-1]
    upper = mid + bb_std * std[-1]
    lower = mid - bb_std * std[-1]
    price = closes[-1]

    # No channel. There is no position within it and no proximity to
    # either edge, so this detector reports nothing at all.
    #
    # The `mid * 0.01` floor that stood here FABRICATED a 1%-of-price
    # band that no published source defines, and it is the step that let
    # a bandless market produce a landing strip: with a made-up width the
    # tolerance reached both edges at once, `near_upper` and `near_lower`
    # were both True, and the result claimed side "upper" -- a SELL --
    # while the same object reported bb_position 0.0. Under TA canon a
    # scale may not be invented; the domain is closed instead.
    #
    # The test is on the CLOSES, not on `upper - lower`: the width is
    # 4*sigma out of `_stdev_tail` and rounds to ULPs rather than to zero
    # on a halted window, so a test of the width misses the very markets
    # this guard is for. The old width test is kept as a subordinate
    # floor. A bb_position of 0.5 is this module's own no-information
    # value, already returned by the short-history branch above.
    if _window_has_no_range(closes[-bb_period:]) or upper - lower <= 0:
        return BBProximityResult(
            upper,
            mid,
            lower,
            0.5,
            False,
            False,
            tolerance_pct,
            False,
            "",
            0,
            100.0,
            0.0,
        )

    bb_range = upper - lower

    bb_pos = (price - lower) / (bb_range + 1e-12)

    # Proximity check with tolerance
    tol_val = bb_range * (tolerance_pct / 100.0)
    near_upper = price >= (upper - tol_val)
    near_lower = price <= (lower + tol_val)

    # Heikin Ashi analysis
    ha = compute_heikin_ashi(candles)
    if len(ha) < 3:
        return BBProximityResult(
            upper,
            mid,
            lower,
            bb_pos,
            near_upper,
            near_lower,
            tolerance_pct,
            False,
            "",
            0,
            100.0,
            0.0,
        )

    # Count consecutive tight HA candles from the end
    # `body_pct` (compute_heikin_ashi) is the HA body over the candle's
    # OWN high-low range, carried in percentage points of that range.
    # `consolidation_threshold` is the same quantity in the same unit;
    # reading it against that unit states so in code. HA_BODY_PCT_UNIT
    # is 1.0, so the value is untouched -- x / 1.0 is exact for every
    # float -- and only the unit becomes visible.
    tight_body_pct = consolidation_threshold / HA_BODY_PCT_UNIT
    tight_count = 0
    recent_bodies = []
    for i in range(len(ha) - 1, max(len(ha) - max_pattern_candles - 1, -1), -1):
        # A bar with no high-low range has no body ratio. An undefined
        # body is not a tight body, so the run of consolidation ends here
        # instead of being extended by a bar that measured nothing.
        body_pct = ha[i].body_pct
        if math.isnan(body_pct):
            break
        if body_pct <= tight_body_pct:
            tight_count += 1
            recent_bodies.append(body_pct)
        else:
            break

    ha_body_avg = sum(recent_bodies) / len(recent_bodies) if recent_bodies else 100.0

    # Landing Strip detection
    landing_strip = False
    landing_side = ""
    consolidation_strength = 0.0

    if tight_count >= min_pattern_candles:
        consolidation_strength = min(1.0, tight_count / max_pattern_candles)
        # Boost strength for very tight bodies
        if ha_body_avg < 1.5:
            consolidation_strength = min(1.0, consolidation_strength * 1.3)

        if near_upper and near_lower:
            # Both edges are within tolerance at once, which means the
            # channel is narrower than the tolerance. Neither side is
            # the one price is reverting FROM, and the plain `if/elif`
            # that stood here named "upper" -- a SELL -- on markets whose
            # own reported bb_position sat against the lower band.
            landing_strip = False
            landing_side = ""
        elif near_upper:
            landing_strip = True
            landing_side = "upper"  # Sell signal — reversal from upper
        elif near_lower:
            landing_strip = True
            landing_side = "lower"  # Buy signal — reversal from lower

    return BBProximityResult(
        upper=upper,
        middle=mid,
        lower=lower,
        bb_position=round(bb_pos, 4),
        near_upper=near_upper,
        near_lower=near_lower,
        tolerance_pct=tolerance_pct,
        landing_strip=landing_strip,
        landing_strip_side=landing_side,
        landing_strip_candles=tight_count,
        ha_body_avg=round(ha_body_avg, 2),
        consolidation_strength=round(consolidation_strength, 3),
    )


# ---------------------------------------------------------------------------
# Landing Strip v2 — Three-Layer Tightening Detection
# ---------------------------------------------------------------------------
@dataclass
class TighteningResult:
    """Result of the 3-layer Landing Strip tightening detection."""

    detected: bool  # True if tightening at BB band detected
    side: str  # "upper" or "lower" or ""
    length: int  # Number of consecutive tightening candles
    tightening_ratio: float  # How much range shrank (0-1, higher = tighter)
    bb_position: float  # BB position when detected
    confidence_boost: float  # Recommended confidence boost (0.0-0.25)
    raw_tightenings: int  # Total tightenings found (pre-BB filter)


def detect_landing_strip_v2(
    candles: list[Candle],
    min_consecutive: int = 3,
    shrink_threshold: float = 0.90,
    bb_tolerance_pct: float = 3.0,
    use_ha: bool = True,
) -> TighteningResult:
    """
    Three-layer Landing Strip detection:
      Layer 1: Detect tightening (|close-open| shrinking consecutively)
      Layer 2: Filter by BB proximity (near upper or lower band)
      Layer 3: Score by length (longer strip = higher confidence boost)

    Inspired by CogNex edge detection in semiconductor metrology:
      Tightening = edge gradient, BB proximity = region of interest,
      Length scoring = template confidence.
    """
    empty = TighteningResult(False, "", 0, 0.0, 0.5, 0.0, 0)

    if len(candles) < 25:
        return empty

    # ── Layer 1: Compute body ranges ──────────────────────
    if use_ha:
        ha = compute_heikin_ashi(candles)
        bodies = [abs(h.close - h.open) for h in ha]
    else:
        bodies = [abs(c.close - c.open) for c in candles]

    # Normalize as % of price
    norm = [bodies[i] / max(candles[i].close, 1e-10) * 100 for i in range(len(bodies))]

    # Count consecutive shrinks from the most recent candle backward
    # `ratio` below is one normalised body over the previous one, so an
    # unchanged body is exactly NO_SHRINK_RATIO. Reading the threshold
    # against that same reference puts both sides of the `<` in one
    # unit. The reference is 1.0, so the value is untouched.
    shrink_limit_ratio = shrink_threshold / NO_SHRINK_RATIO
    shrink_count = 0
    for j in range(len(norm) - 1, 0, -1):
        if norm[j - 1] > 1e-8:
            ratio = norm[j] / norm[j - 1]
            if ratio < shrink_limit_ratio:
                shrink_count += 1
            else:
                break
        else:
            break
        if shrink_count >= 12:  # Cap at 12
            break

    if shrink_count < min_consecutive:
        return TighteningResult(False, "", 0, 0.0, 0.5, 0.0, shrink_count)

    # Tightening ratio: how much did range shrink overall?
    start_idx = len(norm) - 1 - shrink_count
    start_body = norm[start_idx] if start_idx >= 0 else norm[0]
    end_body = norm[-1]
    tightening_ratio = 1.0 - (end_body / max(start_body, 1e-10))
    tightening_ratio = max(0.0, min(1.0, tightening_ratio))

    # ── Layer 2: BB proximity filter ──────────────────────
    # Use HIGH near upper BB and LOW near lower BB (wick-based proximity)
    # This is more sensitive than close-only: during consolidation the body
    # tightens in the middle but wicks still test the BB bands.
    closes = [c.close for c in candles]
    if len(closes) < 20:
        return TighteningResult(
            False, "", shrink_count, tightening_ratio, 0.5, 0.0, shrink_count
        )

    # v3.24.22 — suffix-only; only [-1] is read below.
    sma_vals = _sma_tail(closes, 20, tail=1)
    std_vals = _stdev_tail(closes, 20, tail=1)
    mid = sma_vals[-1]
    upper = mid + 2 * std_vals[-1]
    lower = mid - 2 * std_vals[-1]
    # No channel, so no band to be near and no side to name. The
    # `mid * 0.01` floor removed here is the same fabricated 1%-of-price
    # scale the v1 detector carried, and it is forbidden for the same
    # reason: no published source defines it. The test is on the CLOSES
    # over the same 20 bars the bands are built from, because
    # `upper - lower` is 4*sigma and rounds to ULPs on a halt; the width
    # test is kept underneath as a subordinate floor.
    if _window_has_no_range(closes[-20:]) or upper - lower <= 0:
        return TighteningResult(
            False, "", shrink_count, tightening_ratio, 0.5, 0.0, shrink_count
        )

    bb_range = upper - lower

    price = closes[-1]
    bb_pos = (price - lower) / (bb_range + 1e-12)
    tol = bb_range * (bb_tolerance_pct / 100.0)

    # Check recent candle highs/lows during the tightening window
    window_start = max(0, len(candles) - shrink_count - 1)
    recent = candles[window_start:]
    recent_high = max(c.high for c in recent)
    recent_low = min(c.low for c in recent)

    # Wick-based: does the HIGH reach near the upper BB?
    high_near_upper = recent_high >= (upper - tol)
    # Wick-based: does the LOW reach near the lower BB?
    low_near_lower = recent_low <= (lower + tol)
    # Also check close-based for fallback
    close_near_upper = price >= (upper - tol)
    close_near_lower = price <= (lower + tol)

    near_upper = high_near_upper or close_near_upper
    near_lower = low_near_lower or close_near_lower

    if not near_upper and not near_lower:
        # Tightening detected but not at BB band — return raw data
        return TighteningResult(
            False,
            "",
            shrink_count,
            tightening_ratio,
            round(bb_pos, 4),
            0.0,
            shrink_count,
        )

    if near_upper and near_lower:
        # The tightening window reaches BOTH bands, so the channel is
        # narrower than the tolerance and no side can be named. The
        # ternary below resolved that tie to "upper" -- a reversal DOWN
        # -- regardless of where price actually sat.
        return TighteningResult(
            False,
            "",
            shrink_count,
            tightening_ratio,
            round(bb_pos, 4),
            0.0,
            shrink_count,
        )

    side = "upper" if near_upper else "lower"

    # ── Layer 3: Length-scaled confidence boost ───────────
    length_factor = min(1.0, shrink_count / 8.0)  # Maxes at 8 candles
    tightness_factor = min(1.0, tightening_ratio * 1.5)  # How tight
    confidence_boost = 0.08 + 0.17 * length_factor * tightness_factor  # 0.08-0.25

    return TighteningResult(
        detected=True,
        side=side,
        length=shrink_count,
        tightening_ratio=round(tightening_ratio, 3),
        bb_position=round(bb_pos, 4),
        confidence_boost=round(confidence_boost, 4),
        raw_tightenings=shrink_count,
    )


# ===========================================================================
# v3.19.25 — Tier-1 STRUCTURAL DETECTORS (L1 + L2 Part 6 closure)
# ===========================================================================
#
# Closes Part 6 L1 (Volume-confirmed Spring test) and L2 (W-Bottom / M-Top)
# pushbacks from docs/audits/2026-05-22_archetype_pushback_research.md.
#
# Both detectors are COMPOSITES of already-computed signals -- no new TA
# math, no new indicator weights. They expose pre-existing components as
# named, testable structural signals at the Tier-1 level (highest-
# confidence directional setups per ADR-005).
#
# Architectural contract:
#   - Detectors are PURE functions: same inputs always produce same output.
#   - They return a dict (not a Signal) -- explicit "structural detector"
#     shape distinct from voting indicators. Callers can compose freely.
#   - The dict always contains at minimum a `triggered: bool` key.
#     Detailed diagnostics live in adjacent keys so the operator can see
#     WHY a detector fired without re-running.
# ===========================================================================


def detect_volume_confirmed_spring(
    voting_summary: "VotingSummary",
    bb_proximity: Optional["BBProximityResult"] = None,
    bb_pos_threshold: float = 0.20,
) -> dict:
    """v3.19.25 -- Wyckoff Spring composite detector (L1 closure).

    A Wyckoff Spring is a bullish Tier-1 setup: price tests support but
    volume and structure confirm the test will not break down. The
    composite requires THREE simultaneous confirmations:

      1. bb_position < bb_pos_threshold (default 0.20) -- price is at
         the lower Bollinger band (near support).
      2. bb_proximity.landing_strip AND landing_strip_side == "lower"
         -- Heikin-Ashi consolidation near the lower band (price has
         STOPPED falling, not just touched). Without the consolidation,
         a tap of the lower band could be free-fall through it.
      3. volume.obv_divergence == "bullish" -- On-Balance Volume rising
         while price tests support (volume tells the smart-money story
         that price does not yet).

    All three must be present. Any single component on its own is a
    weaker Tier-2 signal at best; the composite is what makes this Tier-1.

    Args:
      voting_summary: VotingSummary from VotingEngine.compute_all().
      bb_proximity: BBProximityResult from detect_bb_proximity(); when
        None, landing_strip cannot be confirmed and the detector returns
        triggered=False defensively.
      bb_pos_threshold: BB position below which "near lower band" is
        true. Default 0.20 matches the L1 pushback spec.

    Returns:
      dict with keys:
        triggered (bool): True iff all 3 components confirm
        bb_position (float): the BB position value used (-1.0 sentinel
          if voting_summary lacks a bollinger_bands signal)
        landing_strip (bool): landing strip confirmation
        obv_divergence_bullish (bool): OBV divergence confirmation
        components_met (int): 0-3 count for partial-signal diagnostics
        bb_pos_threshold (float): threshold used (for diagnostic)
        name (str): "volume_confirmed_spring"

    sadp: R28 R55 R63
    """
    # NOT the module's `bb_pos`: this one is an OPTIONAL lookup that is
    # None whenever the summary carries no bollinger_bands signal -- see
    # BollingerBands.compute, which returns a Signal with no details
    # when it has too few candles.
    reported_bb_pos: Optional[float] = None
    bb_signals = [s for s in voting_summary.signals if s.indicator == "bollinger_bands"]
    if bb_signals:
        reported_bb_pos = bb_signals[0].details.get("bb_position")

    obv_div_value = "none"
    vol_signals = [s for s in voting_summary.signals if s.indicator == "volume"]
    if vol_signals:
        obv_div_value = vol_signals[0].details.get("obv_divergence", "none")

    near_lower = reported_bb_pos is not None and reported_bb_pos < bb_pos_threshold
    landing = (
        bb_proximity is not None
        and bb_proximity.landing_strip
        and bb_proximity.landing_strip_side == "lower"
    )
    obv_bull = obv_div_value == "bullish"
    components_met = sum([near_lower, landing, obv_bull])

    return {
        "triggered": near_lower and landing and obv_bull,
        "bb_position": (reported_bb_pos if reported_bb_pos is not None else -1.0),
        "landing_strip": landing,
        "obv_divergence_bullish": obv_bull,
        "components_met": components_met,
        "bb_pos_threshold": bb_pos_threshold,
        "name": "volume_confirmed_spring",
    }


def detect_w_bottom(
    candles: list,
    bb_pos_history: list,
    lower_threshold: float = 0.10,
    midline_recovery: float = 0.40,
    min_separation: int = 5,
    lookback: int = 30,
) -> dict:
    """v3.19.25 -- Bollinger W-Bottom pattern (L2 closure, bullish half).

    Canonical Bollinger W-Bottom (from Bollinger on Bollinger Bands):
      The pattern is a double-tap of the lower band where:
        (a) Price makes a low touching the lower band (test 1).
        (b) Price RECOVERS toward the middle band (the pullback).
        (c) Price retests support but at a HIGHER absolute price AND a
            HIGHER bb_position than test 1 (the second test is
            "shallower" -- support is firming).
      Pattern is confirmed when price subsequently breaks above the
      pullback's high.

    This detector identifies the 4-point pattern in the most recent
    `lookback` candles. Returns triggered=True when the structural
    pattern is present, regardless of whether the break-above-pullback
    has occurred (that is a separate timing signal).

    Args:
      candles: candle history (uses .close + .low).
      bb_pos_history: per-candle bb_position values aligned with
        candles. Same length as candles. Caller must precompute.
      lower_threshold: bb_position below this counts as a "lower band
        test." Default 0.10 (canonical Bollinger).
      midline_recovery: bb_position above this counts as the "pullback
        recovery." Default 0.40.
      min_separation: minimum candles between the two tests. Default 5;
        prevents adjacent local minima from triggering.
      lookback: how many candles back to scan. Default 30.

    Returns dict with keys: triggered, name, test_1_idx, test_2_idx,
    test_1_low, test_2_low, test_1_bb_pos, test_2_bb_pos, pullback_idx,
    pullback_bb_pos, components_met.

    sadp: R28 R55 R63
    """
    n = len(candles)
    if n < 2 or len(bb_pos_history) != n:
        return {
            "triggered": False,
            "name": "w_bottom",
            "error": "insufficient candles or misaligned bb_pos_history",
        }

    start = max(0, n - lookback)
    window_candles = candles[start:]
    window_bb = bb_pos_history[start:]

    test_indices = [i for i, bp in enumerate(window_bb) if bp < lower_threshold]
    if len(test_indices) < 2:
        return {
            "triggered": False,
            "name": "w_bottom",
            "components_met": 0,
            "test_indices_found": len(test_indices),
        }

    best: Optional[dict] = None
    for i_test_1 in test_indices:
        for i_test_2 in test_indices:
            if i_test_2 - i_test_1 < min_separation:
                continue
            between = window_bb[i_test_1 + 1 : i_test_2]
            if not between:
                continue
            pullback_bb = max(between)
            if pullback_bb < midline_recovery:
                continue
            pullback_idx = i_test_1 + 1 + between.index(pullback_bb)
            test_1_low = window_candles[i_test_1].low
            test_2_low = window_candles[i_test_2].low
            test_1_bb = window_bb[i_test_1]
            test_2_bb = window_bb[i_test_2]
            if not (test_2_low > test_1_low and test_2_bb > test_1_bb):
                continue
            best = {
                "triggered": True,
                "name": "w_bottom",
                "test_1_idx": start + i_test_1,
                "test_2_idx": start + i_test_2,
                "test_1_low": test_1_low,
                "test_2_low": test_2_low,
                "test_1_bb_pos": test_1_bb,
                "test_2_bb_pos": test_2_bb,
                "pullback_idx": start + pullback_idx,
                "pullback_bb_pos": pullback_bb,
                "components_met": 4,
            }

    if best is None:
        return {
            "triggered": False,
            "name": "w_bottom",
            "components_met": 1,
            "test_indices_found": len(test_indices),
        }
    return best


def detect_m_top(
    candles: list,
    bb_pos_history: list,
    upper_threshold: float = 0.90,
    midline_pullback: float = 0.60,
    min_separation: int = 5,
    lookback: int = 30,
) -> dict:
    """v3.19.25 -- Bollinger M-Top pattern (L2 closure, bearish half).

    Mirror of W-Bottom: two distinct highs touching the upper band, with
    the second high at LOWER absolute price AND LOWER bb_position than
    the first (support is "softening" at the upper band; sellers are
    stepping in higher).

    Args follow detect_w_bottom -- upper_threshold is the high-band test
    bound (default 0.90); midline_pullback is the recovery-down bound
    (default 0.60); rest identical.

    Returns dict matching detect_w_bottom shape but with test_1_high /
    test_2_high instead of low, and the directional inequalities flipped.

    sadp: R28 R55 R63
    """
    n = len(candles)
    if n < 2 or len(bb_pos_history) != n:
        return {
            "triggered": False,
            "name": "m_top",
            "error": "insufficient candles or misaligned bb_pos_history",
        }

    start = max(0, n - lookback)
    window_candles = candles[start:]
    window_bb = bb_pos_history[start:]

    test_indices = [i for i, bp in enumerate(window_bb) if bp > upper_threshold]
    if len(test_indices) < 2:
        return {
            "triggered": False,
            "name": "m_top",
            "components_met": 0,
            "test_indices_found": len(test_indices),
        }

    best: Optional[dict] = None
    for i_test_1 in test_indices:
        for i_test_2 in test_indices:
            if i_test_2 - i_test_1 < min_separation:
                continue
            between = window_bb[i_test_1 + 1 : i_test_2]
            if not between:
                continue
            pullback_bb = min(between)
            if pullback_bb > midline_pullback:
                continue
            pullback_idx = i_test_1 + 1 + between.index(pullback_bb)
            test_1_high = window_candles[i_test_1].high
            test_2_high = window_candles[i_test_2].high
            test_1_bb = window_bb[i_test_1]
            test_2_bb = window_bb[i_test_2]
            if not (test_2_high < test_1_high and test_2_bb < test_1_bb):
                continue
            best = {
                "triggered": True,
                "name": "m_top",
                "test_1_idx": start + i_test_1,
                "test_2_idx": start + i_test_2,
                "test_1_high": test_1_high,
                "test_2_high": test_2_high,
                "test_1_bb_pos": test_1_bb,
                "test_2_bb_pos": test_2_bb,
                "pullback_idx": start + pullback_idx,
                "pullback_bb_pos": pullback_bb,
                "components_met": 4,
            }

    if best is None:
        return {
            "triggered": False,
            "name": "m_top",
            "components_met": 1,
            "test_indices_found": len(test_indices),
        }
    return best
