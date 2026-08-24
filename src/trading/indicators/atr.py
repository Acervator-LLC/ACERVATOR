"""Average True Range (Wilder).

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""
from __future__ import annotations


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
            return {"atr": 0.0, "atr_pct": 0.0, "expanding": False,
                    "contracting": False, "extreme_high": False}
        true_ranges = []
        for i in range(1, len(candles)):
            c, p = candles[i], candles[i - 1]
            tr = max(c.high - c.low,
                     abs(c.high - p.close),
                     abs(c.low  - p.close))
            true_ranges.append(tr)
        # Wilder smoothing (exponential, alpha = 1/period)
        atr = sum(true_ranges[:self.period]) / self.period
        for tr in true_ranges[self.period:]:
            atr = (atr * (self.period - 1) + tr) / self.period
        price = candles[-1].close
        atr_pct = (atr / price) * 100 if price > 0 else 0.0
        # Trend vs range detection
        recent = true_ranges[-5:] if len(true_ranges) >= 5 else true_ranges
        older  = true_ranges[-10:-5] if len(true_ranges) >= 10 else true_ranges
        expanding   = sum(recent) / len(recent) > sum(older) / len(older) * 1.10
        contracting = sum(recent) / len(recent) < sum(older) / len(older) * 0.90
        return {
            "atr":         round(atr, 8),
            "atr_pct":     round(atr_pct, 4),   # ATR as % of price
            "expanding":   expanding,             # volatility growing (trending)
            "contracting": contracting,           # volatility shrinking (coiling)
            "extreme_high": atr_pct > 5.0,        # >5% ATR = highly volatile
        }
