"""``MACD``, Gerald Appel's moving-average convergence/divergence.

``_lines`` builds the MACD line, the signal line and the histogram.
``compute``, ``lines`` and ``compute_histogram_series`` all read those
three series from there.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
    Candle,
)
from .helpers import (
    _ema,
)

#: One entry per candle, ``None`` before ``MACD._lines`` has a value.
_Line = list[float | None]

#: ``_ema`` returns a leading run of None and a value at every index
#: after it.
_INTERIOR_GAP = (
    "MACD line has an interior gap; _ema must return a "
    "leading run of None and nothing else"
)


class MACD:
    """``compute`` votes on the crossover, the histogram and divergence.

    ``fast``, ``slow`` and ``signal_period`` set the three EMA lengths
    ``_lines`` uses.
    """

    def __init__(
        self, fast: int = 12, slow: int = 26, signal: int = 9, weight: float = 1.0
    ):
        self.fast = fast
        self.slow = slow
        self.signal_period = signal
        self.weight = weight

    def _lines(self, closes: list[float]) -> tuple[_Line, _Line, _Line]:
        """``macd_line``, ``signal_line`` and ``histogram``, one per candle.

        ``macd_line`` first has a value at index ``max(fast, slow) - 1``
        and ``signal_line`` ``signal_period - 1`` entries after that;
        every earlier entry is ``None``.
        """
        ema_fast = _ema(closes, self.fast)
        ema_slow = _ema(closes, self.slow)
        macd_line: _Line = [
            None if (f is None or s is None) else f - s
            for f, s in zip(ema_fast, ema_slow)
        ]

        # macd_line's real part is a contiguous suffix; signal_line is
        # padded back to its indices.
        first = len(macd_line)
        for i, v in enumerate(macd_line):
            if v is not None:
                first = i
                break
        real: list[float] = []
        for v in macd_line[first:]:
            if v is None:
                raise ValueError(_INTERIOR_GAP)
            real.append(v)

        signal_line: _Line = [None] * first
        signal_line.extend(_ema(real, self.signal_period))
        histogram: _Line = [
            None if (m is None or g is None) else m - g
            for m, g in zip(macd_line, signal_line)
        ]
        return macd_line, signal_line, histogram

    def lines(self, candles: list[Candle]) -> tuple[_Line, _Line, _Line]:
        """``_lines`` over the closes of ``candles``.

        ``compute`` and ``compute_histogram_series`` read the same three
        series.
        """
        return self._lines([c.close for c in candles])

    def compute(self, candles: list[Candle], timeframe: str = "1h") -> Signal:
        closes = [c.close for c in candles]
        # At the default fast < slow, signal_line's first value sits at
        # index slow + signal_period - 2 and the block below reads -2.
        if len(closes) < self.slow + self.signal_period:
            return Signal(
                "macd",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        macd_line, signal_line, histogram = self._lines(closes)

        curr_hist = histogram[-1]
        prev_hist = histogram[-2]
        curr_macd = macd_line[-1]
        curr_signal = signal_line[-1]
        prev_macd = macd_line[-2]
        prev_signal = signal_line[-2]
        if (
            curr_hist is None
            or prev_hist is None
            or curr_macd is None
            or curr_signal is None
            or prev_macd is None
            or prev_signal is None
        ):
            # Reached only when fast > slow, where the guard above still
            # leaves signal_line[-2] None.
            return Signal(
                "macd",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        # Each scale is a fraction of the last close, so every quotient below
        # divides a price by a price.
        crossover_scale = abs(closes[-1]) * 0.001
        momentum_scale = abs(closes[-1]) * 0.002
        if crossover_scale == 0.0 or momentum_scale == 0.0:
            # No scale to divide by, so macd publishes no confidence here.
            return Signal(
                "macd",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        direction = SignalDirection.NEUTRAL
        confidence = 0.0
        crossover = False
        divergence = ""

        if prev_macd <= prev_signal and curr_macd > curr_signal:
            direction = SignalDirection.BULLISH
            crossover = True
            confidence = max(
                0.0,
                min(1.0, abs(curr_hist) / crossover_scale * 0.3 + 0.5),
            )
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            direction = SignalDirection.BEARISH
            crossover = True
            confidence = max(
                0.0,
                min(1.0, abs(curr_hist) / crossover_scale * 0.3 + 0.5),
            )
        elif curr_hist > 0 and curr_hist > prev_hist:
            direction = SignalDirection.BULLISH
            confidence = max(0.0, min(0.6, abs(curr_hist) / momentum_scale))
        elif curr_hist < 0 and curr_hist < prev_hist:
            direction = SignalDirection.BEARISH
            confidence = max(0.0, min(0.6, abs(curr_hist) / momentum_scale))
        elif curr_hist > 0:
            direction = SignalDirection.BULLISH
            confidence = 0.15
        elif curr_hist < 0:
            direction = SignalDirection.BEARISH
            confidence = 0.15

        # real_macd drops the None head; the 20- and 40-bar windows
        # count MACD values, not candles.
        real_macd = [v for v in macd_line if v is not None]
        n_macd = len(real_macd)
        if len(closes) >= 20 and n_macd >= 20:
            price_low = min(closes[-20:])
            price_prev_low = min(closes[-40:-20]) if len(closes) >= 40 else price_low
            macd_low = min(real_macd[-20:])
            macd_prev_low = min(real_macd[-40:-20]) if n_macd >= 40 else macd_low

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
                macd_high = max(real_macd[-20:])
                macd_prev_high = max(real_macd[-40:-20]) if n_macd >= 40 else macd_high
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
                "macd_line": curr_macd,
                "signal_line": curr_signal,
                "histogram": curr_hist,
                "crossover": crossover,
                "divergence": divergence,
            },
        )

    def compute_histogram_series(self, candles: list, n: int = 12) -> list[float]:
        """Return the last ``n`` values of the ``_lines`` histogram, oldest first.

        Fewer than ``n`` on a short tape and ``[]`` below ``slow +
        signal_period`` candles; ``None`` entries are dropped, never
        padded.
        """
        closes = [c.close for c in candles]
        min_len = self.slow + self.signal_period
        if len(closes) < min_len:
            return []
        histogram = self._lines(closes)[2]
        return [h for h in histogram if h is not None][-n:]
