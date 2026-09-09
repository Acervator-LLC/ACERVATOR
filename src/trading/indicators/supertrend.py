"""Supertrend -- ATR trailing stop (Oliver Seban).

``SupertrendIndicator.compute`` builds Wilder's ATR from ``_true_range``
and returns a ``Signal`` whose direction follows the sticky band it last
crossed.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _true_range,
)


class SupertrendIndicator:
    """ATR trailing stop over one candle list, emitting a ``Signal``.

    THE PUBLISHED DEFINITION, Seban's Supertrend as StockCharts and
    TradingView reproduce it::

        basic upper = (high + low) / 2 + multiplier * ATR(period)
        basic lower = (high + low) / 2 - multiplier * ATR(period)
        final upper = basic upper if basic upper < prev final upper
                      or prev close > prev final upper, else prev final upper
        final lower = basic lower if basic lower > prev final lower
                      or prev close < prev final lower, else prev final lower

    The state is sticky: a bullish bar stays bullish while ``close`` holds
    at or above the final lower band, and a bearish bar turns bullish only
    when ``close`` exceeds the final upper band.
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

        # Wilder's ATR averages every True Range, bar 0 included.
        tr_list = _true_range(candles)

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

        # atr[j] is the ATR at candle period - 1 + j; see idx_atr below.
        start = self.period
        curr_atr = atr[-1]

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
        flip_bull = curr_bull and not prev_bull
        flip_bear = not curr_bull and prev_bull

        price = candles[-1].close
        st_line = lb[-1] if curr_bull else ub[-1]

        # `raw_lb` is `hl2 - multiplier * a` and goes at or below zero once
        # `a` passes `hl2 / multiplier`.
        if st_line <= 0.0:
            return Signal(
                "supertrend",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        dist_pct = abs(price - st_line) / st_line

        near_line = dist_pct < 0.005

        confidence = 0.0
        if flip_bull or flip_bear:
            confidence = 0.85
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
                "st_line": st_line,
                "dist_pct": dist_pct * 100,
                "near_line": near_line,
                "curr_atr": curr_atr,
            },
        )
