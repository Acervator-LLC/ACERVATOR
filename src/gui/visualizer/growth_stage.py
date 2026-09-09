"""Growth stages for the locust cards the Bot Swarm grid draws.

``realised_growth_pct`` turns one bot's exchange cost basis and realised profit
into a percentage and ``stage_for`` places that percentage in one of
``STAGE_NAMES``. ``stage_colors`` and ``id_text_color`` read the hex values a
theme holds for a card. The four stage names come from ``STAGE_SOURCE``.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

from ...trading.smart_wire import MATURE_GROWTH_PCT
from ..theme_engine import THEMES as THEME_TOKENS

STAGE_SOURCE = (
    "FAO Desert Locust Guidelines 1. Biology and behaviour, Symmons and Cressman"
)

STAGE_HOPPER = "hopper"
STAGE_FLEDGLING = "fledgling"
STAGE_IMMATURE = "immature_adult"
STAGE_MATURE = "mature_adult"
STAGE_NAMES = (STAGE_HOPPER, STAGE_FLEDGLING, STAGE_IMMATURE, STAGE_MATURE)

STAGE_LABELS = {
    STAGE_HOPPER: "Hopper",
    STAGE_FLEDGLING: "Fledgling",
    STAGE_IMMATURE: "Immature adult",
    STAGE_MATURE: "Mature adult",
}

STAGE_INITIALS = {
    STAGE_HOPPER: "H",
    STAGE_FLEDGLING: "F",
    STAGE_IMMATURE: "I",
    STAGE_MATURE: "M",
}

# The 200 % floor is MATURE_GROWTH_PCT, the figure the wire maturity test reads.
HOPPER_FLOOR_PCT = 0.0
FLEDGLING_FLOOR_PCT = 100.0
IMMATURE_FLOOR_PCT = MATURE_GROWTH_PCT
MATURE_FLOOR_PCT = 300.0

STAGE_FLOOR_PCT = {
    STAGE_HOPPER: HOPPER_FLOOR_PCT,
    STAGE_FLEDGLING: FLEDGLING_FLOOR_PCT,
    STAGE_IMMATURE: IMMATURE_FLOOR_PCT,
    STAGE_MATURE: MATURE_FLOOR_PCT,
}

STAGE_TOKENS = {
    STAGE_HOPPER: ("locust_hopper_body", "locust_hopper_trim"),
    STAGE_FLEDGLING: ("locust_fledgling_body", "locust_fledgling_trim"),
    STAGE_IMMATURE: ("locust_immature_body", "locust_immature_trim"),
    STAGE_MATURE: ("locust_mature_body", "locust_mature_trim"),
}

# A hopper is wingless and carries wing buds; wings reach full spread on fledging.
WING_SPREAD_RATIO = {
    STAGE_HOPPER: 0.35,
    STAGE_FLEDGLING: 0.80,
    STAGE_IMMATURE: 1.00,
    STAGE_MATURE: 1.00,
}

# Body reaches full size at IMMATURE_FLOOR_PCT, which is the full-grown stage.
BODY_SCALE_RATIO = {
    STAGE_HOPPER: 0.82,
    STAGE_FLEDGLING: 0.91,
    STAGE_IMMATURE: 1.00,
    STAGE_MATURE: 1.00,
}

TERGITE_COUNT = {
    STAGE_HOPPER: 2,
    STAGE_FLEDGLING: 3,
    STAGE_IMMATURE: 4,
    STAGE_MATURE: 4,
}

# Only STAGE_MATURE draws crown spines, which is its own decoration.
CROWN_SPINE_COUNT = {
    STAGE_HOPPER: 0,
    STAGE_FLEDGLING: 0,
    STAGE_IMMATURE: 0,
    STAGE_MATURE: 3,
}

DEFAULT_THEME_NAME = "cyberpunk_dark"
PCT_SCALE = 100.0
GROWTH_ABSENT_TEXT = "—"
GROWTH_FORMAT = "{pct:+.0f}%"

BASIS_KEY = "cost_basis_total_exchange"
REALISED_KEY = "realized_pnl_exchange"
FRESH_KEY = "exchange_data_fresh_ts"


def realised_growth_pct(cost_basis_usd, realised_pnl_usd) -> Optional[float]:
    """Return realised profit as a percentage of the cost basis, or None.

    None covers a basis that is absent, not a number or not above zero, and a
    realised figure that is not finite.
    """
    try:
        basis = float(cost_basis_usd or 0.0)
        profit = float(realised_pnl_usd or 0.0)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(basis) or not math.isfinite(profit) or basis <= 0.0:
        return None
    return profit / basis * PCT_SCALE


def growth_pct_from_stats(stats) -> Optional[float]:
    """Return ``realised_growth_pct`` for one bot's stats dict, or None.

    A stats dict whose ``FRESH_KEY`` is not above zero carries no exchange
    reading, and returns None.
    """
    if not isinstance(stats, dict):
        return None
    try:
        fresh = float(stats.get(FRESH_KEY, 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    if fresh <= 0.0:
        return None
    return realised_growth_pct(stats.get(BASIS_KEY), stats.get(REALISED_KEY))


def stage_for(growth_pct) -> str:
    """Return the stage name one growth percentage sits in.

    A growth percentage of None, or one that is not a finite number, is
    ``STAGE_HOPPER``.
    """
    if growth_pct is None:
        return STAGE_HOPPER
    try:
        pct = float(growth_pct)
    except (TypeError, ValueError):
        return STAGE_HOPPER
    if not math.isfinite(pct):
        return STAGE_HOPPER
    if pct >= MATURE_FLOOR_PCT:
        return STAGE_MATURE
    if pct >= IMMATURE_FLOOR_PCT:
        return STAGE_IMMATURE
    if pct >= FLEDGLING_FLOOR_PCT:
        return STAGE_FLEDGLING
    return STAGE_HOPPER


def growth_text(growth_pct) -> str:
    """Return the percentage the card prints, or ``GROWTH_ABSENT_TEXT``."""
    if growth_pct is None:
        return GROWTH_ABSENT_TEXT
    try:
        pct = float(growth_pct)
    except (TypeError, ValueError):
        return GROWTH_ABSENT_TEXT
    if not math.isfinite(pct):
        return GROWTH_ABSENT_TEXT
    return GROWTH_FORMAT.format(pct=pct)


def stage_colors(stage, theme_name: str = DEFAULT_THEME_NAME) -> Tuple[str, str]:
    """Return the body and trim hex values ``theme_name`` holds for ``stage``."""
    tokens = THEME_TOKENS.get(theme_name) or THEME_TOKENS[DEFAULT_THEME_NAME]
    body_token, trim_token = STAGE_TOKENS.get(stage, STAGE_TOKENS[STAGE_HOPPER])
    return (str(getattr(tokens, body_token)), str(getattr(tokens, trim_token)))


def id_text_color(theme_name: str = DEFAULT_THEME_NAME) -> str:
    """Return the hex value ``theme_name`` holds for the card's bot id text."""
    tokens = THEME_TOKENS.get(theme_name) or THEME_TOKENS[DEFAULT_THEME_NAME]
    return str(tokens.locust_id_text)


def stage_table(theme_name: str = DEFAULT_THEME_NAME) -> dict:
    """Return every stage's body and trim hex pair under one theme."""
    return {name: list(stage_colors(name, theme_name)) for name in STAGE_NAMES}


__all__ = [
    "BODY_SCALE_RATIO",
    "CROWN_SPINE_COUNT",
    "DEFAULT_THEME_NAME",
    "FLEDGLING_FLOOR_PCT",
    "GROWTH_ABSENT_TEXT",
    "GROWTH_FORMAT",
    "HOPPER_FLOOR_PCT",
    "IMMATURE_FLOOR_PCT",
    "MATURE_FLOOR_PCT",
    "STAGE_FLEDGLING",
    "STAGE_FLOOR_PCT",
    "STAGE_HOPPER",
    "STAGE_IMMATURE",
    "STAGE_INITIALS",
    "STAGE_LABELS",
    "STAGE_MATURE",
    "STAGE_NAMES",
    "STAGE_SOURCE",
    "STAGE_TOKENS",
    "TERGITE_COUNT",
    "WING_SPREAD_RATIO",
    "growth_pct_from_stats",
    "growth_text",
    "id_text_color",
    "realised_growth_pct",
    "stage_colors",
    "stage_for",
    "stage_table",
]
