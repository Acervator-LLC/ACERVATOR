"""Stochastic RSI.

``StochasticRSI.rsi_values`` builds the Wilder RSI series, ``stoch_ratios``
positions each value within its window, ``window_is_flat`` marks a window
with no range, and ``lines`` aligns the result to candles.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
    Candle,
)
from .helpers import (
    _sma,
    _window_has_no_range,
)

#: One entry per candle. ``None`` where ``StochasticRSI.lines`` has no value.
_Line = list[float | None]


class StochasticRSI:
    """Stochastic oscillator over an RSI series.

    ``compute`` votes on the K/D crossover, where K smooths ``stoch_ratios``
    over ``k_smooth`` and D smooths K over ``d_smooth``.
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

    def rsi_values(self, closes: list[float]) -> tuple[list[float], bool]:
        """Wilder RSI over ``closes``, and whether the last bar is 0/0.

        Entry ``j`` describes candle ``rsi_period + j + 1``; nothing pads, and
        a ``closes`` shorter than the seed returns an empty list.
        """
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        # `losses` are positive magnitudes; the leading float zero keeps
        # `max` at +0.0 on a flat bar.
        gains = [max(0.0, d) for d in deltas]
        losses = [max(0.0, -d) for d in deltas]

        values: list[float] = []
        if len(deltas) < self.rsi_period:
            return values, False
        avg_gain = sum(gains[: self.rsi_period]) / self.rsi_period
        avg_loss = sum(losses[: self.rsi_period]) / self.rsi_period

        rs_indeterminate = False
        for i in range(self.rsi_period, len(deltas)):
            avg_gain = (avg_gain * (self.rsi_period - 1) + gains[i]) / self.rsi_period
            avg_loss = (avg_loss * (self.rsi_period - 1) + losses[i]) / self.rsi_period
            rs_indeterminate = avg_gain <= 0.0 and avg_loss <= 0.0
            if avg_loss > 0.0:
                values.append(100 - 100 / (1 + avg_gain / avg_loss))
            else:
                # Wilder: a zero `avg_loss` with any gain is an infinite RS,
                # i.e. RSI 100.
                values.append(100.0 if avg_gain > 0.0 else 0.0)
        return values, rs_indeterminate

    def window_is_flat(
        self, rsi_values: list[float], closes: list[float], i: int
    ) -> bool:
        """True when the StochRSI window ending at ``rsi_values[i]`` has no range.

        ``rsi_values[j]`` describes candle ``rsi_period + j + 1``, so the span
        of ``closes`` this reads is every close the window's deltas come from.
        """
        window = rsi_values[i - self.stoch_period + 1 : i + 1]
        span = closes[
            self.rsi_period + i - self.stoch_period + 1 : self.rsi_period + i + 2
        ]
        return max(window) - min(window) <= 0.0 or _window_has_no_range(span)

    def stoch_ratios(
        self, rsi_values: list[float], closes: list[float], tail: int | None = None
    ) -> tuple[int, list[float], bool]:
        """StochRSI over an RSI series: ``(first index, ratios, flat?)``.

        Chande and Kroll (1994) define ``StochRSI = (RSI - lowest RSI) /
        (highest RSI - lowest RSI)`` over ``stoch_period`` values as a 0-to-1
        ratio; ``tail`` bounds the computed range; and ``flat`` marks a window
        with no range, where the ratio is 0/0 and the entry is 0.0.
        """
        start = self.stoch_period - 1
        if tail is not None:
            start = max(start, len(rsi_values) - tail)
        ratios: list[float] = []
        flat = False
        for i in range(start, len(rsi_values)):
            # Identical closes hold the RSI mathematically constant while
            # Wilder's recursion rounds it across ULPs, and dividing by that
            # spread reports a halted market at one end of the oscillator.
            if self.window_is_flat(rsi_values, closes, i):
                flat = True
                ratios.append(0.0)
                continue
            window = rsi_values[i - self.stoch_period + 1 : i + 1]
            low = min(window)
            ratios.append((rsi_values[i] - low) / (max(window) - low))
        return start, ratios, flat

    def lines(self, candles: list[Candle]) -> _Line:
        """StochRSI as a 0-to-1 ratio, one entry per candle.

        Entries are ``None`` before the ``rsi_period`` seed and the
        ``stoch_period`` window have both closed, and on any flat RSI window.
        """
        closes = [c.close for c in candles]
        out: _Line = [None] * len(closes)
        rsi_values, _ = self.rsi_values(closes)
        start, ratios, _ = self.stoch_ratios(rsi_values, closes)
        for offset, ratio in enumerate(ratios):
            i = start + offset
            if self.window_is_flat(rsi_values, closes, i):
                continue
            out[self.rsi_period + i + 1] = ratio
        return out

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        closes = [c.close for c in candles]
        needed = self.rsi_period + self.stoch_period + self.d_smooth + 5
        if len(closes) < needed:
            return Signal(
                "stochastic_rsi",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        rsi_values, rs_indeterminate = self.rsi_values(closes)

        if rs_indeterminate or len(rsi_values) < self.stoch_period:
            return Signal(
                "stochastic_rsi",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        # `k_smooth + d_smooth` trailing ratios are exactly what `k_line[-2]`
        # and `d_line[-2]` reach back through.
        _stoch_need = self.k_smooth + self.d_smooth
        _, _ratios, stoch_indeterminate = self.stoch_ratios(
            rsi_values, closes, tail=_stoch_need
        )
        # The published ratio is 0-to-1; `stoch_rsi` is its 0-to-100 form.
        stoch_rsi = [r * 100 for r in _ratios]

        if stoch_indeterminate:
            return Signal(
                "stochastic_rsi",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        k_line = _sma(stoch_rsi, self.k_smooth)
        d_line = _sma(k_line, self.d_smooth)

        k = k_line[-1]
        d = d_line[-1]
        prev_k = k_line[-2] if len(k_line) > 1 else k
        prev_d = d_line[-2] if len(d_line) > 1 else d

        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover = ""

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
