"""Bollinger Band proximity, with Heikin Ashi landing-strip detection.

``detect_bb_proximity`` returns a ``BBProximityResult``, and ``band_zone`` reads
the BB Tolerance zone off the Voting panel's ``PanelBand``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .types import (
    HA_BODY_PCT_UNIT,
    Candle,
    Signal,
)
from .helpers import (
    _sma_tail,
    _stdev_tail,
    _window_has_no_range,
)

# `compute_heikin_ashi` is a candle transform, not a voter;
# `test_one_indicator_per_module.py` allowlists this edge.
from .heikin_ashi import compute_heikin_ashi

#: Percentage points of a candle's own high-low range; a Heikin Ashi body at or
#: under this is tight.
CONSOLIDATION_THRESHOLD_PCT: float = 3.0

#: ``detect_bb_proximity`` reads ``tolerance_pct`` as a percent of the band's width.
TOLERANCE_OF_BAND_WIDTH: str = "band width"

#: ``detect_bb_proximity`` reads ``tolerance_pct`` as a percent of price, the BB Tolerance unit.
TOLERANCE_OF_PRICE: str = "price"

TOLERANCE_UNITS: tuple[str, ...] = (TOLERANCE_OF_BAND_WIDTH, TOLERANCE_OF_PRICE)


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
    upper_line: float = 1.0  # bb_position at which near_upper starts
    lower_line: float = 0.0  # bb_position at which near_lower ends


def detect_bb_proximity(
    candles: list[Candle],
    tolerance_pct: float = 1.0,  # 0.25% to 5% — distance from band
    consolidation_threshold: float = CONSOLIDATION_THRESHOLD_PCT,
    min_pattern_candles: int = 2,
    max_pattern_candles: int = 10,
    bb_period: int = 20,
    bb_std: float = 2.0,
    tolerance_of: str = TOLERANCE_OF_BAND_WIDTH,
) -> BBProximityResult:
    """Place ``candles`` within the Bollinger channel and detect a landing strip.

    ``landing_strip`` is True when exactly one of ``near_upper`` and
    ``near_lower`` holds and at least ``min_pattern_candles`` trailing Heikin
    Ashi bodies sit at or under ``consolidation_threshold``. ``tolerance_pct``
    is a percent of the band's width, or of price when ``tolerance_of`` is
    ``TOLERANCE_OF_PRICE``; any other ``tolerance_of`` raises ``ValueError``.
    """
    if tolerance_of not in TOLERANCE_UNITS:
        raise ValueError(
            f"tolerance_of {tolerance_of!r} is not one of {TOLERANCE_UNITS}"
        )
    closes = [c.close for c in candles]
    if len(closes) < bb_period:
        return BBProximityResult(
            0, 0, 0, 0.5, False, False, tolerance_pct, False, "", 0, 100.0, 0.0
        )

    # Only the last entry of `sma` and `std` is read.
    sma = _sma_tail(closes, bb_period, tail=1)
    std = _stdev_tail(closes, bb_period, tail=1)
    mid = sma[-1]
    upper = mid + bb_std * std[-1]
    lower = mid - bb_std * std[-1]
    price = closes[-1]

    # `_window_has_no_range` reads the closes; a halted window leaves
    # `upper - lower` at a few ULPs rather than zero.
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

    # %B = (Price - Lower) / (Upper - Lower). The abstention above returns
    # on `upper - lower <= 0`, so `bb_range` is strictly positive here.
    bb_pos = (price - lower) / bb_range

    tol_base = price if tolerance_of == TOLERANCE_OF_PRICE else bb_range
    tol_val = tol_base * (tolerance_pct / 100.0)
    near_upper = price >= (upper - tol_val)
    near_lower = price <= (lower + tol_val)
    upper_line = (upper - tol_val - lower) / bb_range
    lower_line = tol_val / bb_range

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
            upper_line,
            lower_line,
        )

    # `body_pct` and `consolidation_threshold` are both percentage points of
    # the candle's own high-low range.
    tight_body_pct = consolidation_threshold / HA_BODY_PCT_UNIT
    tight_count = 0
    recent_bodies = []
    for i in range(len(ha) - 1, max(len(ha) - max_pattern_candles - 1, -1), -1):
        # A NaN `body_pct` is an undefined body, not a tight one, and ends
        # the run.
        body_pct = ha[i].body_pct / HA_BODY_PCT_UNIT
        if math.isnan(body_pct):
            break
        if body_pct <= tight_body_pct:
            tight_count += 1
            recent_bodies.append(body_pct)
        else:
            break

    ha_body_avg = sum(recent_bodies) / len(recent_bodies) if recent_bodies else 100.0

    landing_strip = False
    landing_side = ""
    consolidation_strength = 0.0

    if tight_count >= min_pattern_candles:
        consolidation_strength = min(1.0, tight_count / max_pattern_candles)
        if ha_body_avg < 1.5:
            consolidation_strength = min(1.0, consolidation_strength * 1.3)

        if near_upper and near_lower:
            # The channel is narrower than `tol_val`, and neither side is the
            # one price reverts from.
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
        bb_position=bb_pos,
        near_upper=near_upper,
        near_lower=near_lower,
        tolerance_pct=tolerance_pct,
        landing_strip=landing_strip,
        landing_strip_side=landing_side,
        landing_strip_candles=tight_count,
        ha_body_avg=ha_body_avg,
        consolidation_strength=consolidation_strength,
        upper_line=upper_line,
        lower_line=lower_line,
    )


def bb_tolerance_reading(
    candles: list[Candle], bb_tolerance_pct: float, landing_strip_candles: int
) -> BBProximityResult:
    """``detect_bb_proximity`` with ``bb_tolerance_pct`` as a percent of price, for the band lines and the Landing Strip."""
    return detect_bb_proximity(
        candles,
        tolerance_pct=bb_tolerance_pct,
        consolidation_threshold=CONSOLIDATION_THRESHOLD_PCT,
        min_pattern_candles=landing_strip_candles,
        tolerance_of=TOLERANCE_OF_PRICE,
    )


#: The Voting panel's Bollinger indicator; its reading decides the BB Tolerance zone.
PANEL_BAND_INDICATOR: str = "bollinger_bands"


@dataclass(frozen=True)
class PanelBand:
    """The panel's Bollinger reading: ``upper`` and ``lower`` bands and the ``close`` they were drawn at."""

    upper: float
    lower: float
    close: float


def panel_band(signals: Sequence[Signal]) -> PanelBand | None:
    """The ``PANEL_BAND_INDICATOR`` signal's bands and close, or None when it abstained or holds no finite band."""
    for signal in signals:
        if signal.indicator != PANEL_BAND_INDICATOR or signal.abstained:
            continue
        details = signal.details or {}
        try:
            upper = float(details["upper"])
            lower = float(details["lower"])
            close = float(details["close"])
        except (KeyError, TypeError, ValueError):
            return None
        finite = all(math.isfinite(value) for value in (upper, lower, close))
        if not finite or upper <= lower or close <= 0.0:
            return None
        return PanelBand(upper=upper, lower=lower, close=close)
    return None


def band_zone(
    band: PanelBand | None, delta: float, tolerance_pct: float
) -> tuple[bool, bool]:
    """``(upper, lower)``: ``band.close`` within ``tolerance_pct`` of price of the upper band on a positive ``delta``, of the lower on a negative one."""
    if band is None:
        return (False, False)
    reach = band.close * tolerance_pct / 100.0
    return (
        bool(delta > 0 and band.close >= band.upper - reach),
        bool(delta < 0 and band.close <= band.lower + reach),
    )
