"""Landing Strip v2 -- tightening detection at a Bollinger band.

``detect_landing_strip_v2`` returns a ``TighteningResult`` naming the band
that a run of shrinking candle bodies reached.
"""

from __future__ import annotations

from dataclasses import dataclass

from .types import (
    NO_SHRINK_RATIO,
    Candle,
)
from .helpers import (
    _sma_tail,
    _stdev_tail,
    _window_has_no_range,
)

# ``compute_heikin_ashi`` is a candle transform, not a voter, and both
# detectors here are defined on its bodies.
from .heikin_ashi import compute_heikin_ashi


@dataclass
class TighteningResult:
    """What ``detect_landing_strip_v2`` returns."""

    detected: bool
    side: str  # "upper", "lower" or ""
    length: int  # consecutive shrinking candles
    tightening_ratio: float  # 0-1, higher is tighter
    bb_position: float
    confidence_boost: float  # 0.0, or 0.08-0.25 when detected
    raw_tightenings: int  # counted before the band filter


def detect_landing_strip_v2(
    candles: list[Candle],
    min_consecutive: int = 3,
    shrink_threshold: float = 0.90,
    bb_tolerance_pct: float = 3.0,
    use_ha: bool = True,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> TighteningResult:
    """Detect a run of shrinking candle bodies that reaches a Bollinger band.

    ``min_consecutive`` and ``shrink_threshold`` bound the run, ``bb_period``
    and ``bb_std`` build the bands, and ``confidence_boost`` scales with
    ``length`` and ``tightening_ratio``.
    """
    empty = TighteningResult(False, "", 0, 0.0, 0.5, 0.0, 0)

    if len(candles) < 25:
        return empty

    if use_ha:
        ha = compute_heikin_ashi(candles)
        bodies = [abs(h.close - h.open) for h in ha]
    else:
        bodies = [abs(c.close - c.open) for c in candles]

    norm = [bodies[i] / max(candles[i].close, 1e-10) * 100 for i in range(len(bodies))]

    # ``NO_SHRINK_RATIO`` is the ratio an unchanged body produces, so both
    # sides of the ``<`` below carry one unit.
    shrink_limit_ratio = shrink_threshold / NO_SHRINK_RATIO
    shrink_count = 0
    for j in range(len(norm) - 1, 0, -1):
        if norm[j - 1] > 1e-8:
            ratio = norm[j] / norm[j - 1]
            if ratio < shrink_limit_ratio:
                shrink_count += 1
            else:
                break
        else:
            break
        if shrink_count >= 12:
            break

    if shrink_count < min_consecutive:
        return TighteningResult(False, "", 0, 0.0, 0.5, 0.0, shrink_count)

    start_idx = len(norm) - 1 - shrink_count
    start_body = norm[start_idx] if start_idx >= 0 else norm[0]
    end_body = norm[-1]
    tightening_ratio = 1.0 - (end_body / max(start_body, 1e-10))
    tightening_ratio = max(0.0, min(1.0, tightening_ratio))

    closes = [c.close for c in candles]
    if len(closes) < bb_period:
        return TighteningResult(
            False, "", shrink_count, tightening_ratio, 0.5, 0.0, shrink_count
        )

    sma_vals = _sma_tail(closes, bb_period, tail=1)
    std_vals = _stdev_tail(closes, bb_period, tail=1)
    mid = sma_vals[-1]
    upper = mid + bb_std * std_vals[-1]
    lower = mid - bb_std * std_vals[-1]
    # ``upper - lower`` rounds to ULPs on a halt, so ``closes`` is tested
    # for range directly.
    if _window_has_no_range(closes[-bb_period:]) or upper - lower <= 0:
        return TighteningResult(
            False, "", shrink_count, tightening_ratio, 0.5, 0.0, shrink_count
        )

    bb_range = upper - lower

    price = closes[-1]
    bb_pos = (price - lower) / bb_range
    tol = bb_range * (bb_tolerance_pct / 100.0)

    window_start = max(0, len(candles) - shrink_count - 1)
    recent = candles[window_start:]
    recent_high = max(c.high for c in recent)
    recent_low = min(c.low for c in recent)

    high_near_upper = recent_high >= (upper - tol)
    low_near_lower = recent_low <= (lower + tol)
    close_near_upper = price >= (upper - tol)
    close_near_lower = price <= (lower + tol)

    near_upper = high_near_upper or close_near_upper
    near_lower = low_near_lower or close_near_lower

    if not near_upper and not near_lower:
        return TighteningResult(
            False,
            "",
            shrink_count,
            tightening_ratio,
            bb_pos,
            0.0,
            shrink_count,
        )

    if near_upper and near_lower:
        # Reaching both bands means the channel is narrower than ``tol``,
        # so no ``side`` can be named.
        return TighteningResult(
            False,
            "",
            shrink_count,
            tightening_ratio,
            bb_pos,
            0.0,
            shrink_count,
        )

    side = "upper" if near_upper else "lower"

    length_factor = min(1.0, shrink_count / 8.0)
    tightness_factor = min(1.0, tightening_ratio * 1.5)
    confidence_boost = 0.08 + 0.17 * length_factor * tightness_factor

    return TighteningResult(
        detected=True,
        side=side,
        length=shrink_count,
        tightening_ratio=tightening_ratio,
        bb_position=bb_pos,
        confidence_boost=confidence_boost,
        raw_tightenings=shrink_count,
    )
