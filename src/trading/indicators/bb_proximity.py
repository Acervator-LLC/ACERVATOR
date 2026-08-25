"""Landing Strip v1 -- HA consolidation at a BB extreme.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .types import (
    HA_BODY_PCT_UNIT,
    Candle,
)
from .helpers import (
    _sma_tail,
    _stdev_tail,
    _window_has_no_range,
)

# The one allowed cross-unit edge in this package. Heikin Ashi is a
# candle TRANSFORM, not a voter, and both Landing Strip detectors are
# defined in terms of it. tests/test_one_indicator_per_module.py holds
# the allowlist that keeps this the only such edge.
from .heikin_ashi import compute_heikin_ashi


# ---------------------------------------------------------------------------
# Bollinger Band Proximity + Landing Strip detection
# ---------------------------------------------------------------------------
@dataclass
class BBProximityResult:
    """Result of Bollinger Band proximity analysis."""

    upper: float
    middle: float
    lower: float
    bb_position: float  # 0 = at lower, 1 = at upper
    near_upper: bool  # Within tolerance of upper band
    near_lower: bool  # Within tolerance of lower band
    tolerance_pct: float  # Active tolerance %
    landing_strip: bool  # HA consolidation near BB detected
    landing_strip_side: str  # "upper" or "lower" or ""
    landing_strip_candles: int  # How many candles in the pattern
    ha_body_avg: float  # Average HA body % for recent candles
    consolidation_strength: float  # 0..1, how tight the consolidation is


def detect_bb_proximity(
    candles: list[Candle],
    tolerance_pct: float = 1.0,  # 0.25% to 5% — distance from band
    consolidation_threshold: float = 3.0,  # HA body % below this = tight
    min_pattern_candles: int = 2,
    max_pattern_candles: int = 10,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> BBProximityResult:
    """
    Detect proximity to Bollinger Bands with Heikin Ashi landing strip.

    A Landing Strip is:
      1. Price within `tolerance_pct` of upper or lower BB
      2. Heikin Ashi candles show tightening bodies (open ≈ close)
      3. HA body % drops below `consolidation_threshold` (1-3%)
      4. This pattern persists for `min_pattern_candles` to `max_pattern_candles`
      5. Indicates incoming reversal — high-confidence sell near upper,
         high-confidence buy near lower
    """
    closes = [c.close for c in candles]
    if len(closes) < bb_period:
        return BBProximityResult(
            0, 0, 0, 0.5, False, False, tolerance_pct, False, "", 0, 100.0, 0.0
        )

    # Compute BB
    # v3.24.22 — suffix-only; only [-1] is read below.
    sma = _sma_tail(closes, bb_period, tail=1)
    std = _stdev_tail(closes, bb_period, tail=1)
    mid = sma[-1]
    upper = mid + bb_std * std[-1]
    lower = mid - bb_std * std[-1]
    price = closes[-1]

    # No channel. There is no position within it and no proximity to
    # either edge, so this detector reports nothing at all.
    #
    # The `mid * 0.01` floor that stood here FABRICATED a 1%-of-price
    # band that no published source defines, and it is the step that let
    # a bandless market produce a landing strip: with a made-up width the
    # tolerance reached both edges at once, `near_upper` and `near_lower`
    # were both True, and the result claimed side "upper" -- a SELL --
    # while the same object reported bb_position 0.0. Under TA canon a
    # scale may not be invented; the domain is closed instead.
    #
    # The test is on the CLOSES, not on `upper - lower`: the width is
    # 4*sigma out of `_stdev_tail` and rounds to ULPs rather than to zero
    # on a halted window, so a test of the width misses the very markets
    # this guard is for. The old width test is kept as a subordinate
    # floor. A bb_position of 0.5 is this module's own no-information
    # value, already returned by the short-history branch above.
    if _window_has_no_range(closes[-bb_period:]) or upper - lower <= 0:
        return BBProximityResult(
            upper,
            mid,
            lower,
            0.5,
            False,
            False,
            tolerance_pct,
            False,
            "",
            0,
            100.0,
            0.0,
        )

    bb_range = upper - lower

    bb_pos = (price - lower) / (bb_range + 1e-12)

    # Proximity check with tolerance
    tol_val = bb_range * (tolerance_pct / 100.0)
    near_upper = price >= (upper - tol_val)
    near_lower = price <= (lower + tol_val)

    # Heikin Ashi analysis
    ha = compute_heikin_ashi(candles)
    if len(ha) < 3:
        return BBProximityResult(
            upper,
            mid,
            lower,
            bb_pos,
            near_upper,
            near_lower,
            tolerance_pct,
            False,
            "",
            0,
            100.0,
            0.0,
        )

    # Count consecutive tight HA candles from the end
    # `body_pct` (compute_heikin_ashi) is the HA body over the candle's
    # OWN high-low range, carried in percentage points of that range.
    # `consolidation_threshold` is the same quantity in the same unit;
    # reading it against that unit states so in code. HA_BODY_PCT_UNIT
    # is 1.0, so the value is untouched -- x / 1.0 is exact for every
    # float -- and only the unit becomes visible.
    tight_body_pct = consolidation_threshold / HA_BODY_PCT_UNIT
    tight_count = 0
    recent_bodies = []
    for i in range(len(ha) - 1, max(len(ha) - max_pattern_candles - 1, -1), -1):
        # A bar with no high-low range has no body ratio. An undefined
        # body is not a tight body, so the run of consolidation ends here
        # instead of being extended by a bar that measured nothing.
        #
        # READ THROUGH THE SAME UNIT AS THE THRESHOLD. `tight_body_pct`
        # three lines above is `consolidation_threshold /
        # HA_BODY_PCT_UNIT`; this is the OTHER operand of the same `<=`
        # and it was read raw. While `compute_heikin_ashi` sat in this
        # same file the reader could follow `body_pct` back to its own
        # division and see the unit; issue #73 moved that function into
        # `heikin_ashi.py` and the provenance left with it, so the
        # comparison stopped stating its unit here. `HA_BODY_PCT_UNIT`
        # is 1.0 and `x / 1.0` is exact for every float -- nan included,
        # which the next line still catches -- so the value is untouched
        # and only the unit becomes visible.
        body_pct = ha[i].body_pct / HA_BODY_PCT_UNIT
        if math.isnan(body_pct):
            break
        if body_pct <= tight_body_pct:
            tight_count += 1
            recent_bodies.append(body_pct)
        else:
            break

    ha_body_avg = sum(recent_bodies) / len(recent_bodies) if recent_bodies else 100.0

    # Landing Strip detection
    landing_strip = False
    landing_side = ""
    consolidation_strength = 0.0

    if tight_count >= min_pattern_candles:
        consolidation_strength = min(1.0, tight_count / max_pattern_candles)
        # Boost strength for very tight bodies
        if ha_body_avg < 1.5:
            consolidation_strength = min(1.0, consolidation_strength * 1.3)

        if near_upper and near_lower:
            # Both edges are within tolerance at once, which means the
            # channel is narrower than the tolerance. Neither side is
            # the one price is reverting FROM, and the plain `if/elif`
            # that stood here named "upper" -- a SELL -- on markets whose
            # own reported bb_position sat against the lower band.
            landing_strip = False
            landing_side = ""
        elif near_upper:
            landing_strip = True
            landing_side = "upper"  # Sell signal — reversal from upper
        elif near_lower:
            landing_strip = True
            landing_side = "lower"  # Buy signal — reversal from lower

    return BBProximityResult(
        upper=upper,
        middle=mid,
        lower=lower,
        bb_position=round(bb_pos, 4),
        near_upper=near_upper,
        near_lower=near_lower,
        tolerance_pct=tolerance_pct,
        landing_strip=landing_strip,
        landing_strip_side=landing_side,
        landing_strip_candles=tight_count,
        ha_body_avg=round(ha_body_avg, 2),
        consolidation_strength=round(consolidation_strength, 3),
    )
