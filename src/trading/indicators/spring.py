"""Wyckoff Spring -- a composite of three confirmations.

A COMPOSITE by declaration: it takes a VotingSummary and a
BBProximityResult as ARGUMENTS and reads fields off them. It
computes nothing and calls no indicator.

Moved out of ``ta_engine.py`` for issue #73. The body below is a
verbatim line slice of that file: no arithmetic was retyped.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .types import (
    VotingSummary,
)

if TYPE_CHECKING:  # a TYPE, never a computation
    from .bb_proximity import BBProximityResult


# ===========================================================================
# v3.19.25 — Tier-1 STRUCTURAL DETECTORS (L1 + L2 Part 6 closure)
# ===========================================================================
#
# Closes Part 6 L1 (Volume-confirmed Spring test) and L2 (W-Bottom / M-Top)
# pushbacks from docs/audits/2026-05-22_archetype_pushback_research.md.
#
# Both detectors are COMPOSITES of already-computed signals -- no new TA
# math, no new indicator weights. They expose pre-existing components as
# named, testable structural signals at the Tier-1 level (highest-
# confidence directional setups per ADR-005).
#
# Architectural contract:
#   - Detectors are PURE functions: same inputs always produce same output.
#   - They return a dict (not a Signal) -- explicit "structural detector"
#     shape distinct from voting indicators. Callers can compose freely.
#   - The dict always contains at minimum a `triggered: bool` key.
#     Detailed diagnostics live in adjacent keys so the operator can see
#     WHY a detector fired without re-running.
# ===========================================================================


def detect_volume_confirmed_spring(
    voting_summary: VotingSummary,
    bb_proximity: Optional[BBProximityResult] = None,
    bb_pos_threshold: float = 0.20,
) -> dict:
    """v3.19.25 -- Wyckoff Spring composite detector (L1 closure).

    A Wyckoff Spring is a bullish Tier-1 setup: price tests support but
    volume and structure confirm the test will not break down. The
    composite requires THREE simultaneous confirmations:

      1. bb_position < bb_pos_threshold (default 0.20) -- price is at
         the lower Bollinger band (near support).
      2. bb_proximity.landing_strip AND landing_strip_side == "lower"
         -- Heikin-Ashi consolidation near the lower band (price has
         STOPPED falling, not just touched). Without the consolidation,
         a tap of the lower band could be free-fall through it.
      3. volume.obv_divergence == "bullish" -- On-Balance Volume rising
         while price tests support (volume tells the smart-money story
         that price does not yet).

    All three must be present. Any single component on its own is a
    weaker Tier-2 signal at best; the composite is what makes this Tier-1.

    Args:
      voting_summary: VotingSummary from VotingEngine.compute_all().
      bb_proximity: BBProximityResult from detect_bb_proximity(); when
        None, landing_strip cannot be confirmed and the detector returns
        triggered=False defensively.
      bb_pos_threshold: BB position below which "near lower band" is
        true. Default 0.20 matches the L1 pushback spec.

    Returns:
      dict with keys:
        triggered (bool): True iff all 3 components confirm
        bb_position (float): the BB position value used (-1.0 sentinel
          if voting_summary lacks a bollinger_bands signal)
        landing_strip (bool): landing strip confirmation
        obv_divergence_bullish (bool): OBV divergence confirmation
        components_met (int): 0-3 count for partial-signal diagnostics
        bb_pos_threshold (float): threshold used (for diagnostic)
        name (str): "volume_confirmed_spring"

    sadp: R28 R55 R63
    """
    # NOT the module's `bb_pos`: this one is an OPTIONAL lookup that is
    # None whenever the summary carries no bollinger_bands signal -- see
    # BollingerBands.compute, which returns a Signal with no details
    # when it has too few candles.
    reported_bb_pos: Optional[float] = None
    bb_signals = [s for s in voting_summary.signals if s.indicator == "bollinger_bands"]
    if bb_signals:
        reported_bb_pos = bb_signals[0].details.get("bb_position")

    obv_div_value = "none"
    vol_signals = [s for s in voting_summary.signals if s.indicator == "volume"]
    if vol_signals:
        obv_div_value = vol_signals[0].details.get("obv_divergence", "none")

    near_lower = reported_bb_pos is not None and reported_bb_pos < bb_pos_threshold
    landing = (
        bb_proximity is not None
        and bb_proximity.landing_strip
        and bb_proximity.landing_strip_side == "lower"
    )
    obv_bull = obv_div_value == "bullish"
    components_met = sum([near_lower, landing, obv_bull])

    return {
        "triggered": near_lower and landing and obv_bull,
        "bb_position": (reported_bb_pos if reported_bb_pos is not None else -1.0),
        "landing_strip": landing,
        "obv_divergence_bullish": obv_bull,
        "components_met": components_met,
        "bb_pos_threshold": bb_pos_threshold,
        "name": "volume_confirmed_spring",
    }
