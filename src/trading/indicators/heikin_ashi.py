"""Heikin Ashi candle conversion (Munehisa Homma).

A candle TRANSFORM, not a voter: it returns candles, not
a Signal. Both Landing Strip detectors read it, and that
is the only cross-module edge in this package.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
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

    # sadp: R28  # indicator compute: fail-loudly(R28)
    """Convert standard candles to Heikin Ashi."""
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
        # A bar whose Heikin Ashi high equals its low has no range, so
        # the body's share OF that range does not exist. It is not zero:
        # the only consumer of this field tests
        # `body_pct <= tight_body_pct`, and 0.0 is the TIGHTEST possible
        # reading, so resolving 0/0 that way manufactured a
        # consolidation out of a market that had not moved. `nan` is
        # what "no ratio" means, and that consumer names the case
        # explicitly rather than leaning on comparison semantics.
        #
        # `ha_high` and `ha_low` are the max and min of the same three
        # numbers, so this IS the source-quantity test for this bar.
        if hl_range <= 0.0:
            body_pct = math.nan
        else:
            body_pct = abs(ha_close - ha_open) / (hl_range + 1e-12) * 100
        ha.append(HACandle(c.timestamp, ha_open, ha_high, ha_low, ha_close, body_pct))
    return ha
