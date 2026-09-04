"""Z-Score of price against its own N-period mean.

``ZScoreIndicator.compute`` returns the Signal.
"""

from __future__ import annotations

from .types import (
    SignalDirection,
    Signal,
)
from .helpers import (
    _window_has_no_range,
)


# ---------------------------------------------------------------------------
# 10. Z-Score — Absolute statistical price deviation from mean
# ---------------------------------------------------------------------------
class ZScoreIndicator:
    """Z-Score of the close against its own ``period`` mean.

    ``compute`` reads ``z = (close - sma) / std`` over the trailing
    ``period`` closes and ``z_prev`` over the window ending one bar earlier,
    then sets ``direction`` from ``strong_high`` and ``strong_low`` at 2.0
    and ``mild_high`` and ``mild_low`` at 1.5.
    """

    def __init__(self, period: int = 50, weight: float = 1.0):
        self.period = period
        self.weight = weight

    def compute(self, candles: list, timeframe: str = "1h") -> Signal:
        if len(candles) < self.period + 1:
            return Signal(
                "zscore",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        closes = [c.close for c in candles[-self.period :]]
        sma = sum(closes) / self.period
        variance = sum((c - sma) ** 2 for c in closes) / self.period
        std = variance**0.5

        # `_window_has_no_range` reads the closes the venue sent, so it is
        # exact at every price scale; `std` is derived and rounds to ULPs on
        # a halted window rather than to 0.0.
        if _window_has_no_range(closes):
            return Signal(
                "zscore",
                timeframe,
                SignalDirection.NEUTRAL,
                0.0,
                self.weight,
                abstained=True,
            )

        z = (candles[-1].close - sma) / std

        # ONE DIVISION, NOT TWO. `z_prev` is `z` over the window ending one
        # bar earlier and divides by `std2` exactly as `z` divides by `std`.
        # A previous window with no range leaves `z_prev = z`, which is this
        # module's own no-information fallback and holds `z_reverting` False.
        z_prev = z
        if len(candles) >= self.period + 2:
            c_prev = [c.close for c in candles[-self.period - 1 : -1]]
            if not _window_has_no_range(c_prev):
                s2 = sum(c_prev) / self.period
                v2 = sum((c - s2) ** 2 for c in c_prev) / self.period
                std2 = v2**0.5
                z_prev = (candles[-2].close - s2) / std2

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
