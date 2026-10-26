"""design_system_surface.py -- the colour, type, spacing and motion tokens.

Describes the one table of style values the whole interface draws
from. One hundred and ninety-five names carry a value each: 146
colours, two font families, 39 whole numbers, three line heights and
five shadow settings. Six of the 146 colours are second names for a
colour already in the table, and ``ALIAS_TARGETS`` says which name
each one copies.

The table declares style. It runs nothing, wires no control and
starts no timer, so ``ACTIONS``, ``TIMERS`` and ``SKIN`` are empty.

Five things leave this surface. ``token`` returns one value by name
and returns the caller's default for a name the table does not hold.
``has_token`` answers whether a name is in the table. ``group_tokens``
returns one named group and an empty table for a group that does not
exist. ``build_view_model`` returns the whole table, and the subset a
caller asked for. ``view_model`` is the bridge handler.

``src.core.desktop_bridge`` registers ``view_model`` as the handler
for the ``design_system.state`` method, which is how the Electron
renderer reaches it. ``TOKENS`` reads each of the 195 values from
``src.gui.design_system``, which declares every one and holds the
only copy. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import design_system
from ..color_alpha import css_colours

METHOD = "design_system.state"

# THE GROUPS

COLOR_NAMES = (
    "SURFACE_0",
    "SURFACE_1",
    "SURFACE_2",
    "SURFACE_3",
    "SURFACE_4",
    "TEXT_HIGH",
    "TEXT_MED",
    "TEXT_LOW",
    "TEXT_DISABLED",
    "PRIMARY",
    "ON_PRIMARY",
    "PRIMARY_CONTAINER",
    "ON_PRIMARY_CONTAINER",
    "SECONDARY",
    "ON_SECONDARY",
    "SECONDARY_CONTAINER",
    "ON_SECONDARY_CONTAINER",
    "SUCCESS",
    "DANGER",
    "WARNING",
    "INFO",
    "OUTLINE",
    "OUTLINE_STRONG",
    "GLOW_PRIMARY",
    "GLOW_SECONDARY",
    "SCRIM",
    "CARD_STOCK_SURFACE",
    "CARD_STOCK_BORDER",
    "CARD_STOCK_LABEL",
    "CARD_STOCK_VALUE",
    "CARD_METRIC_SURFACE",
    "CARD_METRIC_BORDER",
    "CARD_METRIC_LABEL",
    "ERROR",
    "WARNING_STRONG",
    "STATUS_INFO",
    "STATUS_NEUTRAL",
    "STATUS_AUTHENTICATED",
    "PRIMARY_BRIGHT",
    "ACCENT_GOLD",
    "LAYER_CRYPTO",
    "LAYER_STOCK",
    "TEXT_MAX",
    "TEXT_NEUTRAL",
    "TEXT_CONSOLE",
    "TEXT_INACTIVE",
    "TEXT_EMPTY_STATE",
    "TEXT_MUTED",
    "TEXT_PLACEHOLDER",
    "TEXT_INFO_SOFT",
    "TEXT_LOG_MINT",
    "TEXT_ON_LIGHT",
    "SURFACE_CHART",
    "SURFACE_CONTROL",
    "SURFACE_INPUT",
    "SURFACE_CONSOLE",
    "SURFACE_CONSOLE_HEADER",
    "BORDER_DISABLED",
    "MENU_SURFACE",
    "MENU_BORDER",
    "MENU_ITEM_SELECTED",
    "STATE_ARMED",
    "STATE_ENGAGED",
    "STATE_ENGAGED_DIM",
    "STATE_ENGAGED_GLOW",
    "STATE_PENDING",
    "STATE_STARTING",
    "STATE_MARKET",
    "FOLD_RATIO_AMBER",
    "FOLD_SOURCE_MANUAL",
    "FOLD_TRANCHE_SURFACE",
    "FOLD_TRANCHE_BORDER",
    "EXTRACTOR_TRANCHE_SURFACE",
    "EXTRACTOR_TRANCHE_BORDER",
    "SETTINGS_PRIMARY_HOVER",
    "SETTINGS_ON_INFO",
    "SETTINGS_DANGER_SURFACE",
    "SETTINGS_WARNING_HOVER",
    "SETTINGS_DESTRUCTIVE_SURFACE",
    "SETTINGS_DESTRUCTIVE_HOVER",
    "SETTINGS_DISABLED_SURFACE",
    "SETTINGS_DISABLED_DEEP",
    "GLOW_PRIMARY_EDGE",
    "GLOW_PRIMARY_FAINT",
    "VIZ_PANEL_SURFACE",
    "VIZ_PANEL_BORDER",
    "VIZ_SWARM_SURFACE",
    "VIZ_TAB_SELECTED",
    "VIZ_TAB_TEXT",
    "VIZ_HEADING",
    "VIZ_CAPTION",
    "VIZ_CAPTION_DIM",
    "VIZ_LIST_SURFACE",
    "VIZ_LIST_BORDER",
    "VIZ_LIST_TEXT",
    "VIZ_INPUT_SURFACE",
    "VIZ_INPUT_BORDER",
    "VIZ_GO_HOVER",
    "VIZ_GO_HOVER_DEEP",
    "VIZ_STOP_HOVER",
    "VIZ_STOP_HOVER_DEEP",
    "VIZ_SIM_HOVER",
    "VIZ_GOLD_HOVER",
    "VIZ_CONFIRM_SURFACE",
    "VIZ_NUCLEAR_SURFACE",
    "VIZ_NUCLEAR_BORDER",
    "VIZ_LANE_LIVE",
    "VIZ_LANE_PAPER",
    "MAIN_TOOLBAR_SURFACE",
    "MAIN_SEPARATOR",
    "MAIN_BUTTON_SURFACE",
    "MAIN_BUTTON_BORDER",
    "MAIN_BUTTON_HOVER",
    "MAIN_TOGGLE_SURFACE",
    "MAIN_TOGGLE_HOVER",
    "MAIN_TOGGLE_CHECKED",
    "MAIN_TOGGLE_CHECKED_AMBER",
    "MAIN_TOOLTIP_BORDER",
    "MAIN_TABLE_HEADER",
    "MAIN_CAPTION",
    "MAIN_BADGE_TEXT",
    "MAIN_BADGE_MAGENTA",
    "MAIN_ALERT_SURFACE",
    "MAIN_HIGHLIGHT_AMBER",
    "MAIN_HIGHLIGHT_AMBER_TEXT",
    "MAIN_LOG_NAME",
    "MAIN_LOG_SITE",
    "MAIN_LOG_CRITICAL",
    "CARD_STOCK_PANEL",
    "CARD_STOCK_BODY",
    "CARD_STOCK_LOG_SURFACE",
    "CARD_STOCK_BUTTON_BORDER",
    "CARD_STOCK_BUTTON_HOVER",
    "STOCK_POSITIVE",
    "STOCK_NEGATIVE",
    "STOCK_WARNING",
    "STOCK_BUTTON_HOVER",
    "STOCK_LOG_DEBUG",
    "STOCK_LOG_TIMESTAMP",
    "STOCK_LOG_CRITICAL",
)

TYPE_NAMES = (
    "TYPE_DISPLAY",
    "TYPE_H1",
    "TYPE_H2",
    "TYPE_H3",
    "TYPE_H4",
    "TYPE_BODY",
    "TYPE_SMALL",
    "TYPE_CAPTION",
    "TYPE_CARD_VALUE",
)

LINE_HEIGHT_NAMES = (
    "LINE_HEIGHT_TIGHT",
    "LINE_HEIGHT_BODY",
    "LINE_HEIGHT_LOOSE",
)

FONT_FAMILY_NAMES = (
    "FONT_FAMILY_UI",
    "FONT_FAMILY_MONO",
)

WEIGHT_NAMES = (
    "WEIGHT_REGULAR",
    "WEIGHT_MEDIUM",
    "WEIGHT_BOLD",
)

SPACE_NAMES = (
    "SPACE_XS",
    "SPACE_XXS",
    "SPACE_CARD_TIGHT",
    "SPACE_CARD_PAD",
    "SPACE_S",
    "SPACE_M",
    "SPACE_L",
    "SPACE_XL",
    "SPACE_XXL",
)

RADIUS_NAMES = (
    "RADIUS_NONE",
    "RADIUS_XS",
    "RADIUS_CARD",
    "RADIUS_SM",
    "RADIUS_MD",
    "RADIUS_LG",
)

MOTION_NAMES = (
    "MOTION_INSTANT",
    "MOTION_SHORT",
    "MOTION_MEDIUM",
    "MOTION_LONG",
    "MOTION_EXTRA",
)

TARGET_NAMES = (
    "TARGET_MIN",
    "TARGET_COMFORTABLE",
    "TARGET_LARGE",
)

TABLE_COLUMN_NAMES = (
    "TABLE_COL_FIRE_W",
    "TABLE_COL_DETAIL_W",
)

FOCUS_NAMES = (
    "FOCUS_RING_WIDTH",
    "FOCUS_RING_OFFSET",
)

SHADOW_NAMES = (
    "SHADOW_0",
    "SHADOW_1",
    "SHADOW_2",
    "SHADOW_3",
    "SHADOW_4",
)

ALIAS_NAMES = (
    "BG",
    "CARD",
    "FG",
    "DIM",
    "HINT",
    "FOCUS_RING_COLOR",
)

TOKEN_NAMES = (
    "SURFACE_0",
    "SURFACE_1",
    "SURFACE_2",
    "SURFACE_3",
    "SURFACE_4",
    "TEXT_HIGH",
    "TEXT_MED",
    "TEXT_LOW",
    "TEXT_DISABLED",
    "PRIMARY",
    "ON_PRIMARY",
    "PRIMARY_CONTAINER",
    "ON_PRIMARY_CONTAINER",
    "SECONDARY",
    "ON_SECONDARY",
    "SECONDARY_CONTAINER",
    "ON_SECONDARY_CONTAINER",
    "SUCCESS",
    "DANGER",
    "WARNING",
    "INFO",
    "OUTLINE",
    "OUTLINE_STRONG",
    "GLOW_PRIMARY",
    "GLOW_SECONDARY",
    "SCRIM",
    "CARD_STOCK_SURFACE",
    "CARD_STOCK_BORDER",
    "CARD_STOCK_LABEL",
    "CARD_STOCK_VALUE",
    "CARD_METRIC_SURFACE",
    "CARD_METRIC_BORDER",
    "CARD_METRIC_LABEL",
    "ERROR",
    "WARNING_STRONG",
    "STATUS_INFO",
    "STATUS_NEUTRAL",
    "STATUS_AUTHENTICATED",
    "PRIMARY_BRIGHT",
    "ACCENT_GOLD",
    "LAYER_CRYPTO",
    "LAYER_STOCK",
    "TEXT_MAX",
    "TEXT_NEUTRAL",
    "TEXT_CONSOLE",
    "TEXT_INACTIVE",
    "TEXT_EMPTY_STATE",
    "TEXT_MUTED",
    "TEXT_PLACEHOLDER",
    "TEXT_INFO_SOFT",
    "TEXT_LOG_MINT",
    "TEXT_ON_LIGHT",
    "SURFACE_CHART",
    "SURFACE_CONTROL",
    "SURFACE_INPUT",
    "SURFACE_CONSOLE",
    "SURFACE_CONSOLE_HEADER",
    "BORDER_DISABLED",
    "MENU_SURFACE",
    "MENU_BORDER",
    "MENU_ITEM_SELECTED",
    "STATE_ARMED",
    "STATE_ENGAGED",
    "STATE_ENGAGED_DIM",
    "STATE_ENGAGED_GLOW",
    "STATE_PENDING",
    "STATE_STARTING",
    "STATE_MARKET",
    "FOLD_RATIO_AMBER",
    "FOLD_SOURCE_MANUAL",
    "FOLD_TRANCHE_SURFACE",
    "FOLD_TRANCHE_BORDER",
    "EXTRACTOR_TRANCHE_SURFACE",
    "EXTRACTOR_TRANCHE_BORDER",
    "SETTINGS_PRIMARY_HOVER",
    "SETTINGS_ON_INFO",
    "SETTINGS_DANGER_SURFACE",
    "SETTINGS_WARNING_HOVER",
    "SETTINGS_DESTRUCTIVE_SURFACE",
    "SETTINGS_DESTRUCTIVE_HOVER",
    "SETTINGS_DISABLED_SURFACE",
    "SETTINGS_DISABLED_DEEP",
    "GLOW_PRIMARY_EDGE",
    "GLOW_PRIMARY_FAINT",
    "VIZ_PANEL_SURFACE",
    "VIZ_PANEL_BORDER",
    "VIZ_SWARM_SURFACE",
    "VIZ_TAB_SELECTED",
    "VIZ_TAB_TEXT",
    "VIZ_HEADING",
    "VIZ_CAPTION",
    "VIZ_CAPTION_DIM",
    "VIZ_LIST_SURFACE",
    "VIZ_LIST_BORDER",
    "VIZ_LIST_TEXT",
    "VIZ_INPUT_SURFACE",
    "VIZ_INPUT_BORDER",
    "VIZ_GO_HOVER",
    "VIZ_GO_HOVER_DEEP",
    "VIZ_STOP_HOVER",
    "VIZ_STOP_HOVER_DEEP",
    "VIZ_SIM_HOVER",
    "VIZ_GOLD_HOVER",
    "VIZ_CONFIRM_SURFACE",
    "VIZ_NUCLEAR_SURFACE",
    "VIZ_NUCLEAR_BORDER",
    "VIZ_LANE_LIVE",
    "VIZ_LANE_PAPER",
    "MAIN_TOOLBAR_SURFACE",
    "MAIN_SEPARATOR",
    "MAIN_BUTTON_SURFACE",
    "MAIN_BUTTON_BORDER",
    "MAIN_BUTTON_HOVER",
    "MAIN_TOGGLE_SURFACE",
    "MAIN_TOGGLE_HOVER",
    "MAIN_TOGGLE_CHECKED",
    "MAIN_TOGGLE_CHECKED_AMBER",
    "MAIN_TOOLTIP_BORDER",
    "MAIN_TABLE_HEADER",
    "MAIN_CAPTION",
    "MAIN_BADGE_TEXT",
    "MAIN_BADGE_MAGENTA",
    "MAIN_ALERT_SURFACE",
    "MAIN_HIGHLIGHT_AMBER",
    "MAIN_HIGHLIGHT_AMBER_TEXT",
    "MAIN_LOG_NAME",
    "MAIN_LOG_SITE",
    "MAIN_LOG_CRITICAL",
    "CARD_STOCK_PANEL",
    "CARD_STOCK_BODY",
    "CARD_STOCK_LOG_SURFACE",
    "CARD_STOCK_BUTTON_BORDER",
    "CARD_STOCK_BUTTON_HOVER",
    "STOCK_POSITIVE",
    "STOCK_NEGATIVE",
    "STOCK_WARNING",
    "STOCK_BUTTON_HOVER",
    "STOCK_LOG_DEBUG",
    "STOCK_LOG_TIMESTAMP",
    "STOCK_LOG_CRITICAL",
    "TYPE_DISPLAY",
    "TYPE_H1",
    "TYPE_H2",
    "TYPE_H3",
    "TYPE_H4",
    "TYPE_BODY",
    "TYPE_SMALL",
    "TYPE_CAPTION",
    "TYPE_CARD_VALUE",
    "LINE_HEIGHT_TIGHT",
    "LINE_HEIGHT_BODY",
    "LINE_HEIGHT_LOOSE",
    "FONT_FAMILY_UI",
    "FONT_FAMILY_MONO",
    "WEIGHT_REGULAR",
    "WEIGHT_MEDIUM",
    "WEIGHT_BOLD",
    "SPACE_XS",
    "SPACE_XXS",
    "SPACE_CARD_TIGHT",
    "SPACE_CARD_PAD",
    "SPACE_S",
    "SPACE_M",
    "SPACE_L",
    "SPACE_XL",
    "SPACE_XXL",
    "RADIUS_NONE",
    "RADIUS_XS",
    "RADIUS_CARD",
    "RADIUS_SM",
    "RADIUS_MD",
    "RADIUS_LG",
    "MOTION_INSTANT",
    "MOTION_SHORT",
    "MOTION_MEDIUM",
    "MOTION_LONG",
    "MOTION_EXTRA",
    "TARGET_MIN",
    "TARGET_COMFORTABLE",
    "TARGET_LARGE",
    "TABLE_COL_FIRE_W",
    "TABLE_COL_DETAIL_W",
    "FOCUS_RING_WIDTH",
    "FOCUS_RING_OFFSET",
    "FOCUS_RING_COLOR",
    "SHADOW_0",
    "SHADOW_1",
    "SHADOW_2",
    "SHADOW_3",
    "SHADOW_4",
    "BG",
    "CARD",
    "FG",
    "DIM",
    "HINT",
)

ALIAS_TARGETS = {
    "BG": "SURFACE_0",
    "CARD": "SURFACE_1",
    "FG": "TEXT_HIGH",
    "DIM": "TEXT_MED",
    "HINT": "TEXT_LOW",
    "FOCUS_RING_COLOR": "OUTLINE_STRONG",
}

GROUP_MEMBERS: dict[str, tuple[str, ...]] = {
    "colors": COLOR_NAMES,
    "type_scale": TYPE_NAMES,
    "line_heights": LINE_HEIGHT_NAMES,
    "font_families": FONT_FAMILY_NAMES,
    "weights": WEIGHT_NAMES,
    "spacing": SPACE_NAMES,
    "radii": RADIUS_NAMES,
    "motion_ms": MOTION_NAMES,
    "target_sizes": TARGET_NAMES,
    "table_columns": TABLE_COLUMN_NAMES,
    "focus": FOCUS_NAMES,
    "shadows": SHADOW_NAMES,
    "aliases": ALIAS_NAMES,
}

GROUP_NAMES = tuple(GROUP_MEMBERS)

TOKENS: dict[str, Any] = {name: getattr(design_system, name) for name in TOKEN_NAMES}

GROUPS: dict[str, dict[str, Any]] = {
    group: {name: TOKENS[name] for name in members}
    for group, members in GROUP_MEMBERS.items()
}

COLORS = GROUPS["colors"]
TYPE_SCALE = GROUPS["type_scale"]
LINE_HEIGHTS = GROUPS["line_heights"]
FONT_FAMILIES = GROUPS["font_families"]
WEIGHTS = GROUPS["weights"]
SPACING = GROUPS["spacing"]
RADII = GROUPS["radii"]
MOTION_MS = GROUPS["motion_ms"]
TARGET_SIZES = GROUPS["target_sizes"]
TABLE_COLUMNS = GROUPS["table_columns"]
FOCUS = GROUPS["focus"]
SHADOWS = GROUPS["shadows"]
ALIASES = GROUPS["aliases"]

# WHAT THE TABLE DOES NOT DO
# The table declares style and runs nothing. These stay empty and a test
# proves each one empty against the module the surface replaces.

ACTIONS: dict[str, str] = {}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
SKIN: dict[str, str] = {}
STYLE_SHEET = ""

MISSING_TOKEN = None
NOT_AN_ALIAS = ""
EMPTY_GROUP: dict[str, Any] = {}


def token(name: str, default: Any = MISSING_TOKEN) -> Any:
    """One token value by name, or `default` for a name not in the table."""
    return TOKENS.get(name, default)


def has_token(name: str) -> bool:
    """Whether the table holds a token under `name`."""
    return name in TOKENS


def group_tokens(group: str) -> dict[str, Any]:
    """One named group, or an empty table for a group that does not exist."""
    return dict(GROUPS.get(group, EMPTY_GROUP))


def alias_target(name: str) -> str:
    """The token a second name copies, or the empty string for any other name."""
    return ALIAS_TARGETS.get(name, NOT_AN_ALIAS)


def requested_names(names: Any) -> list:
    """The names a caller asked for, and an empty list for anything else.

    A caller that sends one bare string, a number or nothing asks for no
    token rather than for the letters of that string.
    """
    if isinstance(names, (list, tuple)):
        return [str(name) for name in names]
    return []


def build_view_model(
    names: Any = None,
    group: Optional[str] = None,
) -> dict:
    """Return the whole token table as one serialisable dict.

    `names` carries the tokens a caller asked for by name; every name it
    does not hold comes back under `unknown` with a null value. `group`
    carries one group name; a group the table does not hold comes back
    empty.

    The table itself carries the alpha byte Qt reads. The payload leaves
    under `src.gui.color_alpha.css_colours`, so the renderer receives the
    share a browser reads and no colour is copied twice.
    """
    asked = requested_names(names)
    wanted = str(group) if group else ""
    payload = {
        "token_names": list(TOKEN_NAMES),
        "tokens": dict(TOKENS),
        "group_names": list(GROUP_NAMES),
        "group_members": {
            found: list(members) for found, members in GROUP_MEMBERS.items()
        },
        "groups": {found: dict(members) for found, members in GROUPS.items()},
        "colors": dict(COLORS),
        "type_scale": dict(TYPE_SCALE),
        "line_heights": dict(LINE_HEIGHTS),
        "font_families": dict(FONT_FAMILIES),
        "weights": dict(WEIGHTS),
        "spacing": dict(SPACING),
        "radii": dict(RADII),
        "motion_ms": dict(MOTION_MS),
        "target_sizes": dict(TARGET_SIZES),
        "table_columns": dict(TABLE_COLUMNS),
        "focus": dict(FOCUS),
        "shadows": {found: list(value) for found, value in SHADOWS.items()},
        "aliases": dict(ALIASES),
        "alias_targets": dict(ALIAS_TARGETS),
        "requested": {found: token(found) for found in asked},
        "unknown": [found for found in asked if not has_token(found)],
        "group": wanted,
        "group_tokens": group_tokens(wanted),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "skin": dict(SKIN),
        "style_sheet": STYLE_SHEET,
    }
    return css_colours(payload)


def view_model(params: dict) -> dict:
    """Bridge handler for ``design_system.state``.

    Reads ``names`` and ``group`` from the request parameters. The table
    is the same on every call, so there is no state to reset.
    """
    return build_view_model(params.get("names"), params.get("group"))
