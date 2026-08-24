"""Landing Strip v2 -- three-layer tightening detection.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
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
# The one allowed cross-unit edge in this package. Heikin Ashi is a
# candle TRANSFORM, not a voter, and both Landing Strip detectors are
# defined in terms of it. tests/test_one_indicator_per_module.py holds
# the allowlist that keeps this the only such edge.
from .heikin_ashi import compute_heikin_ashi


# ---------------------------------------------------------------------------
# Landing Strip v2 — Three-Layer Tightening Detection
# ---------------------------------------------------------------------------
@dataclass
class TighteningResult:
    """Result of the 3-layer Landing Strip tightening detection."""
    detected: bool              # True if tightening at BB band detected
    side: str                   # "upper" or "lower" or ""
    length: int                 # Number of consecutive tightening candles
    tightening_ratio: float     # How much range shrank (0-1, higher = tighter)
    bb_position: float          # BB position when detected
    confidence_boost: float     # Recommended confidence boost (0.0-0.25)
    raw_tightenings: int        # Total tightenings found (pre-BB filter)


def detect_landing_strip_v2(
    candles: list[Candle],
    min_consecutive: int = 3,
    shrink_threshold: float = 0.90,
    bb_tolerance_pct: float = 3.0,
    use_ha: bool = True,
    bb_period: int = 20,
    bb_std: float = 2.0,
) -> TighteningResult:
    """
    Three-layer Landing Strip detection:
      Layer 1: Detect tightening (|close-open| shrinking consecutively)
      Layer 2: Filter by BB proximity (near upper or lower band)
      Layer 3: Score by length (longer strip = higher confidence boost)

    ``bb_period`` and ``bb_std`` are the Bollinger parameters Layer 2
    measures against. They match ``detect_bb_proximity`` and
    ``BollingerBands`` in name, default and meaning, so one bot's
    configuration reaches every band in its own tick.

    Inspired by CogNex edge detection in semiconductor metrology:
      Tightening = edge gradient, BB proximity = region of interest,
      Length scoring = template confidence.
    """
    empty = TighteningResult(False, "", 0, 0.0, 0.5, 0.0, 0)

    if len(candles) < 25:
        return empty

    # ── Layer 1: Compute body ranges ──────────────────────
    if use_ha:
        ha = compute_heikin_ashi(candles)
        bodies = [abs(h.close - h.open) for h in ha]
    else:
        bodies = [abs(c.close - c.open) for c in candles]

    # Normalize as % of price
    norm = [bodies[i] / max(candles[i].close, 1e-10) * 100
            for i in range(len(bodies))]

    # Count consecutive shrinks from the most recent candle backward
    # `ratio` below is one normalised body over the previous one, so an
    # unchanged body is exactly NO_SHRINK_RATIO. Reading the threshold
    # against that same reference puts both sides of the `<` in one
    # unit. The reference is 1.0, so the value is untouched.
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
        if shrink_count >= 12:  # Cap at 12
            break

    if shrink_count < min_consecutive:
        return TighteningResult(False, "", 0, 0.0, 0.5, 0.0, shrink_count)

    # Tightening ratio: how much did range shrink overall?
    start_idx = len(norm) - 1 - shrink_count
    start_body = norm[start_idx] if start_idx >= 0 else norm[0]
    end_body = norm[-1]
    tightening_ratio = 1.0 - (end_body / max(start_body, 1e-10))
    tightening_ratio = max(0.0, min(1.0, tightening_ratio))

    # ── Layer 2: BB proximity filter ──────────────────────
    # Use HIGH near upper BB and LOW near lower BB (wick-based proximity)
    # This is more sensitive than close-only: during consolidation the body
    # tightens in the middle but wicks still test the BB bands.
    closes = [c.close for c in candles]
    if len(closes) < bb_period:
        return TighteningResult(False, "", shrink_count, tightening_ratio, 0.5, 0.0, shrink_count)

    # THE BANDS READ THEIR CONFIGURATION.
    #
    # Bollinger's published definition is a middle band SMA(N) with
    # an upper and lower band at K standard deviations, and N and K
    # are PARAMETERS of the indicator -- Bollinger's own defaults
    # are 20 and 2. The other three sites that build these bands
    # take them as arguments: `BollingerBands.__init__(period,
    # std_dev)`, `detect_bb_proximity(bb_period, bb_std)` and
    # `SlingshotIndicator.__init__(bb_period, bb_std)`.
    #
    # This detector wrote `20` and `2` into the body. A bot
    # configured with any other pair would have had its landing
    # strip measured against bands no other part of the engine was
    # drawing -- a different indicator, under the same name, in the
    # same tick.
    #
    # The defaults are Bollinger's own and match every other site,
    # so nothing computed here moves today. MEASURED read-only on
    # the live fleet: none of the 38 bots carries a `bb_period` or
    # `bb_std` key, so all four sites agree at 20 / 2.0 right now.
    # The defect is that the value was STATIC where the definition
    # makes it dynamic.
    #
    # v3.24.22 — suffix-only; only [-1] is read below.
    sma_vals = _sma_tail(closes, bb_period, tail=1)
    std_vals = _stdev_tail(closes, bb_period, tail=1)
    mid = sma_vals[-1]
    upper = mid + bb_std * std_vals[-1]
    lower = mid - bb_std * std_vals[-1]
    # No channel, so no band to be near and no side to name. The
    # `mid * 0.01` floor removed here is the same fabricated 1%-of-price
    # scale the v1 detector carried, and it is forbidden for the same
    # reason: no published source defines it. The test is on the CLOSES
    # over the same 20 bars the bands are built from, because
    # `upper - lower` is 4*sigma and rounds to ULPs on a halt; the width
    # test is kept underneath as a subordinate floor.
    if _window_has_no_range(closes[-bb_period:]) or upper - lower <= 0:
        return TighteningResult(False, "", shrink_count, tightening_ratio,
                                0.5, 0.0, shrink_count)

    bb_range = upper - lower

    price = closes[-1]
    bb_pos = (price - lower) / (bb_range + 1e-12)
    tol = bb_range * (bb_tolerance_pct / 100.0)

    # Check recent candle highs/lows during the tightening window
    window_start = max(0, len(candles) - shrink_count - 1)
    recent = candles[window_start:]
    recent_high = max(c.high for c in recent)
    recent_low = min(c.low for c in recent)

    # Wick-based: does the HIGH reach near the upper BB?
    high_near_upper = recent_high >= (upper - tol)
    # Wick-based: does the LOW reach near the lower BB?
    low_near_lower = recent_low <= (lower + tol)
    # Also check close-based for fallback
    close_near_upper = price >= (upper - tol)
    close_near_lower = price <= (lower + tol)

    near_upper = high_near_upper or close_near_upper
    near_lower = low_near_lower or close_near_lower

    if not near_upper and not near_lower:
        # Tightening detected but not at BB band — return raw data
        return TighteningResult(False, "", shrink_count, tightening_ratio,
                                round(bb_pos, 4), 0.0, shrink_count)

    if near_upper and near_lower:
        # The tightening window reaches BOTH bands, so the channel is
        # narrower than the tolerance and no side can be named. The
        # ternary below resolved that tie to "upper" -- a reversal DOWN
        # -- regardless of where price actually sat.
        return TighteningResult(False, "", shrink_count, tightening_ratio,
                                round(bb_pos, 4), 0.0, shrink_count)

    side = "upper" if near_upper else "lower"

    # ── Layer 3: Length-scaled confidence boost ───────────
    length_factor = min(1.0, shrink_count / 8.0)  # Maxes at 8 candles
    tightness_factor = min(1.0, tightening_ratio * 1.5)  # How tight
    confidence_boost = 0.08 + 0.17 * length_factor * tightness_factor  # 0.08-0.25

    return TighteningResult(
        detected=True,
        side=side,
        length=shrink_count,
        tightening_ratio=round(tightening_ratio, 3),
        bb_position=round(bb_pos, 4),
        confidence_boost=round(confidence_boost, 4),
        raw_tightenings=shrink_count,
    )
