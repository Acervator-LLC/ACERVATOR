"""The ramp ``zone_ramp_mode`` reads, one of ``RAMP_MODES``.

``RAMP_SEARCH`` waits, ``RAMP_TRACK`` reads fast past Max Cartridge Size and
``RAMP_FIRE`` is the only mode that lets a target scrum arm.
The live tick and the ATA-SPM scan both call ``zone_ramp_mode``.
"""

from __future__ import annotations

RAMP_SEARCH = "search"
RAMP_TRACK = "track"
RAMP_FIRE = "fire"
RAMP_MODES = (RAMP_SEARCH, RAMP_TRACK, RAMP_FIRE)


def zone_ramp_mode(in_zone: bool, cartridge_reached: bool) -> str:
    """``RAMP_FIRE`` ``in_zone``, else ``RAMP_TRACK`` while ``cartridge_reached``, else ``RAMP_SEARCH``."""
    if in_zone:
        return RAMP_FIRE
    return RAMP_TRACK if cartridge_reached else RAMP_SEARCH
