"""``KaufmanERIndicator``, Perry Kaufman's Efficiency Ratio.

``lines`` answers the ratio for every candle; ``compute`` reads the last
two entries into a ``Signal`` named ``kaufman_er`` carrying ``er``,
``er_prev`` and the regime flags it derives from them.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)

#: One entry per candle, ``None`` before ``period`` bars and on a window
#: whose closes never moved.
_Line = list[float | None]


class KaufmanERIndicator:
    """Efficiency Ratio over ``period`` candles.

    ``lines`` answers the ratio a chart draws; ``compute`` reports ``er``,
    ``er_rising``, ``er_falling``, ``ideal_ranging``, ``moderate``,
    ``trending``, ``highly_efficient``, ``er_peak_falling`` and
    ``price_up`` in the ``Signal`` details.
    """

    def __init__(self, period: int = 10, weight: float = 1.0):
        self.period = period
        self.weight = weight

    def lines(self, candles: list) -> _Line:
        """Kaufman's Efficiency Ratio per candle: the net change across ``window``
        as a fraction of ``price_travel``, the total of its bar-to-bar moves.

        A window with no travel divides by nothing and its entry stays ``None``.
        """
        closes = [c.close for c in candles]
        n = len(closes)
        out: _Line = [None] * n
        for i in range(self.period, n):
            window = closes[i - self.period : i + 1]
            price_travel = sum(
                abs(window[k] - window[k - 1]) for k in range(1, len(window))
            )
            if price_travel <= 0.0:
                continue
            out[i] = abs(window[-1] - window[0]) / price_travel
        return out

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 2:
            return Signal(
                "kaufman_er",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        closes = [c.close for c in candles[-(self.period + 1) :]]
        ratios = self.lines(candles)
        er = ratios[-1]

        if er is None:
            return Signal(
                "kaufman_er",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        # The previous window's ratio, read from the third bar past the
        # window on; ``er`` where that window had no travel.
        er_prev = er
        if len(candles) >= self.period + 3 and ratios[-2] is not None:
            er_prev = ratios[-2]

        er_rising = er > er_prev
        er_falling = er < er_prev

        ideal_ranging = er < 0.25
        moderate = 0.25 <= er < 0.50
        trending = er >= 0.50
        highly_efficient = er >= 0.70
        er_peak_falling = er_falling and er_prev >= 0.60

        price_up = closes[-1] > closes[0]

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
                "er": er,
                "er_prev": er_prev,
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
