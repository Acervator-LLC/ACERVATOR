"""Wyckoff Spring -- a composite of three confirmations.

``detect_volume_confirmed_spring`` reads fields off the ``VotingSummary``
and ``BBProximityResult`` it is given, computing no arithmetic of its own
and calling no indicator.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .types import (
    VotingSummary,
)

if TYPE_CHECKING:  # a TYPE, never a computation
    from .bb_proximity import BBProximityResult


def detect_volume_confirmed_spring(
    voting_summary: VotingSummary,
    bb_proximity: Optional[BBProximityResult] = None,
    bb_pos_threshold: float = 0.20,
) -> dict:
    """Report a Wyckoff Spring: three confirmations read off ``voting_summary``.

    ``triggered`` is True only when ``bb_position`` from the
    ``bollinger_bands`` signal is below ``bb_pos_threshold``, when
    ``bb_proximity.landing_strip`` holds with ``landing_strip_side ==
    "lower"``, and when the ``volume`` signal reports
    ``obv_divergence == "bullish"``. The returned dict also carries
    ``bb_position`` (``-1.0`` when absent), ``landing_strip``,
    ``obv_divergence_bullish``, ``components_met``, ``bb_pos_threshold``
    and ``name``.
    """
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
