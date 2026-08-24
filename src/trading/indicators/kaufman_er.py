"""Perry Kaufman's Efficiency Ratio (1995).

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
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
            return Signal("kaufman_er", timeframe,
                          SignalDirection.NEUTRAL, 0.0, self.weight)

        closes = [c.close for c in candles[-(self.period + 1):]]
        net_change = abs(closes[-1] - closes[0])
        price_travel = sum(abs(closes[i] - closes[i-1]) for i in range(1, len(closes)))

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
            return Signal("kaufman_er", timeframe,
                          SignalDirection.NEUTRAL, 0.0, self.weight)

        # Kaufman's Efficiency Ratio: net displacement over the total
        # distance travelled to get there. Both are prices, so `er` is
        # dimensionless and lies in [0, 1].
        er = net_change / (price_travel + 1e-9)

        # Previous ER for trend. A previous window that never moved has
        # no ER either; `er_prev = er` is this module's own fallback for
        # that, already used when the history is too short.
        er_prev = er
        if len(candles) >= self.period + 3:
            c2 = [c.close for c in candles[-(self.period + 2):-1]]
            nc2 = abs(c2[-1] - c2[0])
            pl2 = sum(abs(c2[i] - c2[i-1]) for i in range(1, len(c2)))
            if pl2 > 0.0:
                er_prev = nc2 / (pl2 + 1e-9)

        er_rising  = er > er_prev
        er_falling = er < er_prev

        # Classify
        ideal_ranging    = er < 0.25
        moderate         = 0.25 <= er < 0.50
        trending         = er >= 0.50
        highly_efficient = er >= 0.70
        er_peak_falling  = er_falling and er_prev >= 0.60   # trend ending

        # Price direction, READ OFF THE ER WINDOW.
        #
        # Kaufman's Efficiency Ratio (Smarter Trading, 1995) is
        # DIRECTION over VOLATILITY, both measured on the SAME N
        # bars:
        #
        #     ER = |Close - Close[N periods ago]|
        #          / sum(|Close - Close[1 period ago]|) over those N
        #
        # `closes` above is `candles[-(period + 1):]` -- period + 1
        # bars, which is the period changes the denominator sums.
        # Its numerator is therefore `closes[-1] - closes[0]`.
        #
        # The direction test used to read `closes_all[-period]`,
        # which is `closes[1]`, NOT `closes[0]`: a window one bar
        # SHORTER than the ratio it labels. When ER said "trending"
        # and the two windows disagreed in sign, the vote was cast
        # the wrong way. The sign now comes from the same two
        # endpoints as the numerator, so `er` and `price_up`
        # describe one move.
        price_up   = closes[-1] > closes[0]

        if trending and price_up:
            direction  = SignalDirection.BULLISH
            confidence = max(0.0, min(0.7, er * 0.7))
        elif trending and not price_up:
            direction  = SignalDirection.BEARISH
            confidence = max(0.0, min(0.7, er * 0.7))
        else:
            direction  = SignalDirection.NEUTRAL
            confidence = 0.0

        return Signal(
            indicator="kaufman_er",
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            weight=self.weight,
            details={
                "er":              round(er, 4),
                "er_prev":         round(er_prev, 4),
                "er_rising":       er_rising,
                "er_falling":      er_falling,
                "ideal_ranging":   ideal_ranging,
                "moderate":        moderate,
                "trending":        trending,
                "highly_efficient": highly_efficient,
                "er_peak_falling": er_peak_falling,
                "price_up":        price_up,
            },
        )
