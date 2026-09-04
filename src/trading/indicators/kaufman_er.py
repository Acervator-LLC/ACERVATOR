"""Perry Kaufman's Efficiency Ratio (1995).

``KaufmanERIndicator.compute`` reports the ratio as ``er`` and votes only
where ``trending`` holds.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)


class KaufmanERIndicator:
    """Net price change over the distance price travelled to make it.

    Kaufman, Smarter Trading (1995):

        ER = |Close - Close[N periods ago]|
             / sum(|Close - Close[1 period ago]|) over those N

    ``ideal_ranging``, ``moderate``, ``trending`` and ``highly_efficient``
    band ``er`` at 0.25, 0.50 and 0.70.
    """

    def __init__(self, period: int = 10, weight: float = 1.0):
        self.period = period
        self.weight = weight

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        """One Kaufman ER reading over ``candles`` at ``timeframe``.

        ``compute`` abstains below ``period + 2`` candles and on a window
        where ``price_travel`` is 0.0.
        """
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
        net_change = abs(closes[-1] - closes[0])
        price_travel = sum(
            abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))
        )

        # ``price_travel`` cancels to exactly 0.0 on a halted window, where
        # every term subtracts equal floats.
        if price_travel <= 0.0:
            return Signal(
                "kaufman_er",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        # ``net_change`` and ``price_travel`` are both prices, which puts
        # ``er`` in [0, 1] at every price scale.
        er = net_change / price_travel

        # ``er_prev`` holds the current ``er`` where the previous window is
        # short or never moved.
        er_prev = er
        if len(candles) >= self.period + 3:
            c2 = [c.close for c in candles[-(self.period + 2) : -1]]
            nc2 = abs(c2[-1] - c2[0])
            pl2 = sum(abs(c2[i] - c2[i - 1]) for i in range(1, len(c2)))
            if pl2 > 0.0:
                er_prev = nc2 / pl2

        er_rising = er > er_prev
        er_falling = er < er_prev

        ideal_ranging = er < 0.25
        moderate = 0.25 <= er < 0.50
        trending = er >= 0.50
        highly_efficient = er >= 0.70
        er_peak_falling = er_falling and er_prev >= 0.60

        # ``price_up`` reads the two endpoints ``net_change`` measures.
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
