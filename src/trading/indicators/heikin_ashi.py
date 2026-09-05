"""Heikin Ashi candle conversion (Munehisa Homma).

``compute_heikin_ashi`` transforms candles into ``HACandle`` values and
returns no Signal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .types import (
    Candle,
)


# Heikin Ashi candle conversion
@dataclass
class HACandle:
    """Heikin Ashi candle."""

    timestamp: float
    open: float
    high: float
    low: float
    close: float
    body_pct: float  # |close-open| / (high-low) as %; nan when no range


def compute_heikin_ashi(candles: list[Candle]) -> list[HACandle]:
    """Convert standard candles to Heikin Ashi.

    Homma's transform, with ``body_pct`` carrying ``abs(ha_close - ha_open)``
    as a percent of ``hl_range``, and ``math.nan`` where ``hl_range`` is zero:

        ha_close = (open + high + low + close) / 4
        ha_open  = (prev ha_open + prev ha_close) / 2
        ha_high  = max(high, ha_open, ha_close)
        ha_low   = min(low, ha_open, ha_close)
    """
    if not candles:
        return []
    ha: list[HACandle] = []
    for i, c in enumerate(candles):
        ha_close = (c.open + c.high + c.low + c.close) / 4
        if i == 0:
            ha_open = (c.open + c.close) / 2
        else:
            ha_open = (ha[-1].open + ha[-1].close) / 2
        ha_high = max(c.high, ha_open, ha_close)
        ha_low = min(c.low, ha_open, ha_close)
        hl_range = ha_high - ha_low
        # `ha_high` and `ha_low` are the max and min of the same three
        # numbers, so this test is exact at every price scale. A body has no
        # share of a range that does not exist, and 0.0 would read to
        # `detect_bb_proximity` as the tightest possible consolidation.
        if hl_range <= 0.0:
            body_pct = math.nan
        else:
            body_pct = abs(ha_close - ha_open) / hl_range * 100
        ha.append(HACandle(c.timestamp, ha_open, ha_high, ha_low, ha_close, body_pct))
    return ha
