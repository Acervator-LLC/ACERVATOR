"""The Cartridge, BB Proximity and Landing Strip boost boxes every Live, Paper and Simulator settings page and wizard draws."""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtWidgets import QDoubleSpinBox

from ..trading.container.config import (
    BOOST_PCT_MAX,
    CARTRIDGE_BOOST_PCT_DEFAULT,
    LANDING_STRIP_BOOST_PCT_DEFAULT,
    PROXIMITY_BOOST_PCT_DEFAULT,
)
from .tooltips import set_description

BOOST_PCT_STEP: float = 0.25
BOOST_PCT_DECIMALS: int = 2

#: Each boost field's row label, description key and default.
BOOST_FIELDS: dict[str, tuple[str, str, float]] = {
    "cartridge_boost_pct": (
        "Cartridge Boost:",
        "cartridge_boost",
        CARTRIDGE_BOOST_PCT_DEFAULT,
    ),
    "proximity_boost_pct": (
        "BB Proximity Boost:",
        "proximity_boost",
        PROXIMITY_BOOST_PCT_DEFAULT,
    ),
    "landing_strip_boost_pct": (
        "Landing Strip Boost:",
        "landing_strip_boost",
        LANDING_STRIP_BOOST_PCT_DEFAULT,
    ),
}


def boost_value(config: Any, field: str) -> float:
    """``field`` of ``config`` as a finite non-negative percent, else its ``BOOST_FIELDS`` default."""
    default = BOOST_FIELDS[field][2]
    try:
        value = float(getattr(config, field, default))
    except (TypeError, ValueError):
        return default
    return value if math.isfinite(value) and value >= 0.0 else default


def boost_box(config: Any, field: str, description: str) -> QDoubleSpinBox:
    """A percent box from 0 to ``BOOST_PCT_MAX`` holding ``boost_value`` of ``field``, described by ``description``."""
    box = QDoubleSpinBox()
    box.setRange(0.0, BOOST_PCT_MAX)
    box.setDecimals(BOOST_PCT_DECIMALS)
    box.setSingleStep(BOOST_PCT_STEP)
    box.setSuffix(" %")
    box.setValue(boost_value(config, field))
    set_description(box, description)
    return box
