"""The ramp ``next_ramp_mode`` advances through ``RAMP_MODES``.

``RAMP_SEARCH`` waits, ``RAMP_TRACK`` follows a price out towards a band and
``RAMP_FIRE`` is the only mode that lets a target scrum arm.
``retreat_line`` answers the travel below which ``RAMP_SEARCH`` returns.
Both the live tick and the ATA-SPM scan call ``next_ramp_mode`` for the
transition and keep their own reading of ``travel`` and ``edge_gap``.
"""

from __future__ import annotations

RAMP_SEARCH = "search"
RAMP_TRACK = "track"
RAMP_FIRE = "fire"
RAMP_MODES = (RAMP_SEARCH, RAMP_TRACK, RAMP_FIRE)
RETREAT_DIVISOR = 2.0


def retreat_line(detect_limit: float) -> float:
    """``detect_limit`` over ``RETREAT_DIVISOR``."""
    return detect_limit / RETREAT_DIVISOR


def next_ramp_mode(
    mode: str,
    travel: float,
    detect_limit: float,
    retreat_limit: float,
    edge_gap: float,
    fire_limit: float,
    delta_clears: bool,
) -> str:
    """The mode one price reading moves ``mode`` to.

    ``travel`` shares a unit with ``detect_limit`` and ``retreat_limit``,
    ``edge_gap`` shares one with ``fire_limit``, ``delta_clears`` gates both
    exits from ``RAMP_SEARCH``, and a ``mode`` outside ``RAMP_MODES`` is read
    as ``RAMP_FIRE``.
    """
    near_band = edge_gap <= fire_limit
    if mode == RAMP_SEARCH:
        if near_band and delta_clears:
            return RAMP_FIRE
        if travel >= detect_limit and delta_clears:
            return RAMP_TRACK
        return RAMP_SEARCH
    if mode == RAMP_TRACK:
        if near_band:
            return RAMP_FIRE
        return RAMP_SEARCH if travel < retreat_limit else RAMP_TRACK
    if not near_band and travel >= detect_limit:
        return RAMP_TRACK
    return RAMP_SEARCH if not near_band and travel < retreat_limit else RAMP_FIRE
