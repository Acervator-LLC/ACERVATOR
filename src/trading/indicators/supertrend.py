"""Supertrend -- ATR trailing stop (Oliver Seban).

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _true_range,
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
                "supertrend",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        # ATR (Wilder) -- THE WHOLE TRUE RANGE SERIES, FIRST BAR
        # INCLUDED. Supertrend is an ATR trailing stop, so its ATR
        # is Wilder's ATR and it is seeded the same way: the average
        # of the first `period` True Ranges, of which the first is
        # `high - low` (StockCharts, reproducing Wilder's
        # worksheet). This comprehension started at bar 1 and
        # dropped that value. `_true_range` is the module's one
        # definition; the per-bar expression is the identical max
        # of the identical three terms.
        tr_list = _true_range(candles)

        # Simple ATR smoothing (Wilder)
        atr = [0.0] * (self.period)
        if len(tr_list) >= self.period:
            first_atr = sum(tr_list[: self.period]) / self.period
            atr = [first_atr]
            for tr in tr_list[self.period :]:
                atr.append((atr[-1] * (self.period - 1) + tr) / self.period)

        if not atr:
            return Signal(
                "supertrend",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        # Align. `tr_list[k]` is now the True Range of candle k, so
        # `atr[0] = mean(tr_list[:period])` is the ATR AT candle
        # `period - 1`, and `atr[j]` is the ATR at candle
        # `period - 1 + j`. Re-anchored below as
        # `idx_atr = i - (period - 1)`.
        #
        # The band loop still starts at candle `period`, so the
        # same candles carry bands as before -- only the ATR values
        # move, by the seed the line above restored.
        start = self.period
        curr_atr = atr[-1]

        # Build Supertrend series (need history for sticky bands)
        ub = [0.0]
        lb = [0.0]
        st = [True]  # True = bullish
        for i in range(start, n):
            idx_atr = i - (self.period - 1)
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
