"""Average True Range (Wilder).

``ATRIndicator.compute`` averages the whole ``_true_range`` series and
smooths it with Wilder's ``alpha = 1 / period``.
"""

from __future__ import annotations

from .helpers import (
    _true_range,
)


class ATRIndicator:
    """Average True Range over ``period`` bars, an absolute volatility measure.

    ``compute`` returns ``atr``, ``atr_pct`` and the ``expanding``,
    ``contracting`` and ``extreme_high`` flags. Nothing in ``src``
    constructs it; it is exported through ``INDICATOR_MODULES`` only.
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
        # Wilder averages every True Range, bar 0 included.
        true_ranges = _true_range(candles)
        atr = sum(true_ranges[: self.period]) / self.period
        # Wilder smoothing, alpha = 1 / period.
        for tr in true_ranges[self.period :]:
            atr = (atr * (self.period - 1) + tr) / self.period
        price = candles[-1].close
        atr_pct = (atr / price) * 100 if price > 0 else 0.0
        recent = true_ranges[-5:] if len(true_ranges) >= 5 else true_ranges
        older = true_ranges[-10:-5] if len(true_ranges) >= 10 else true_ranges
        expanding = sum(recent) / len(recent) > sum(older) / len(older) * 1.10
        contracting = sum(recent) / len(recent) < sum(older) / len(older) * 0.90
        return {
            "atr": atr,
            "atr_pct": atr_pct,
            "expanding": expanding,
            "contracting": contracting,
            "extreme_high": atr_pct > 5.0,
        }
