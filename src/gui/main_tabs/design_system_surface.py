"""design_system_surface.py -- the colour, type, spacing and motion tokens.

Describes the one table of style values the whole interface draws
from. One hundred and ninety-six names carry a value each: 146
colours, two font families, 40 whole numbers, three line heights and
five shadow settings. Six of the 146 colours are second names for a
colour already in the table, and ``ALIAS_TARGETS`` says which name
each one copies.

The table declares style. It runs nothing, wires no control and
starts no timer, so ``ACTIONS``, ``TIMERS`` and ``SKIN`` are empty and
a test proves them empty against the module they replace.

Five things leave this surface. ``token`` returns one value by name
and returns the caller's default for a name the table does not hold.
``has_token`` answers whether a name is in the table. ``group_tokens``
returns one named group and an empty table for a group that does not
exist. ``build_view_model`` returns the whole table, and the subset a
caller asked for. ``view_model`` is the bridge handler.

``src.core.desktop_bridge`` registers ``view_model`` as the handler
for the ``design_system.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather
than read from ``src.gui.design_system``, so a value changed on one
side alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

from ..color_alpha import css_colours

METHOD = "design_system.state"

# COLOURS

# ---- Surface elevation -------------------------------------------------
SURFACE_0 = "#0a0a0f"
SURFACE_1 = "#141420"
SURFACE_2 = "#1a1a28"
SURFACE_3 = "#22223a"
SURFACE_4 = "#2a2a44"

# ---- Text roles --------------------------------------------------------
TEXT_HIGH = "#e0e0f0"
TEXT_MED = "#a8a8c5"
TEXT_LOW = "#8a8ab0"
TEXT_DISABLED = "#555577"

# ---- Primary and secondary accents -------------------------------------
PRIMARY = "#00ffcc"
ON_PRIMARY = "#003d33"
PRIMARY_CONTAINER = "#00998a"
ON_PRIMARY_CONTAINER = "#c8fff0"
SECONDARY = "#ff00aa"
ON_SECONDARY = "#3d0029"
SECONDARY_CONTAINER = "#a8006d"
ON_SECONDARY_CONTAINER = "#ffd8ee"

# ---- Semantic roles ----------------------------------------------------
SUCCESS = "#00ff88"
DANGER = "#ff5577"
WARNING = "#ffaa00"
INFO = "#4fc3ff"

# ---- Outlines ----------------------------------------------------------
OUTLINE = "#7a7a9c"
OUTLINE_STRONG = "#a0a0c0"

# ---- Glow and scrim ----------------------------------------------------
GLOW_PRIMARY = "rgba(0,255,204,51)"
GLOW_SECONDARY = "rgba(255,0,170,51)"
SCRIM = "rgba(0,0,0,136)"

# ---- Stat-card skins ---------------------------------------------------
CARD_STOCK_SURFACE = "#0e1428"
CARD_STOCK_BORDER = "#1a2a4f"
CARD_STOCK_LABEL = "#6688aa"
CARD_STOCK_VALUE = "#e0e8f0"
CARD_METRIC_SURFACE = "#12121f"
CARD_METRIC_BORDER = "#2a2a3f"
CARD_METRIC_LABEL = "#888"

# ---- Widget colours ----------------------------------------------------
ERROR = "#ff3366"
WARNING_STRONG = "#ff6600"
STATUS_INFO = "#00aaff"
STATUS_NEUTRAL = "#8899aa"
STATUS_AUTHENTICATED = "#00ddff"
PRIMARY_BRIGHT = "#00ffee"
ACCENT_GOLD = "#ffd700"
LAYER_CRYPTO = "#00ccaa"
LAYER_STOCK = "#6699ff"

# ---- Text roles beyond high, medium and low ----------------------------
TEXT_MAX = "#ffffff"
TEXT_NEUTRAL = "#cccccc"
TEXT_CONSOLE = "#c0c0c0"
TEXT_INACTIVE = "#aaaaaa"
TEXT_EMPTY_STATE = "#8a8aab"
TEXT_MUTED = "#666666"
TEXT_PLACEHOLDER = "#555555"
TEXT_INFO_SOFT = "#66ccff"
TEXT_LOG_MINT = "#c0ffe0"
TEXT_ON_LIGHT = "#000000"

# ---- Surfaces beyond the five elevations -------------------------------
SURFACE_CHART = "#0a0a12"
SURFACE_CONTROL = "#1a1a2e"
SURFACE_INPUT = "#0e0e1a"
SURFACE_CONSOLE = "#05050a"
SURFACE_CONSOLE_HEADER = "#0a0a14"
BORDER_DISABLED = "#444444"

# ---- Context menu ------------------------------------------------------
MENU_SURFACE = "#1a1a2f"
MENU_BORDER = "#3a3a5f"
MENU_ITEM_SELECTED = "#2a2a4f"

# ---- Control states ----------------------------------------------------
STATE_ARMED = "#3ed080"
STATE_ENGAGED = "#2d9d5f"
STATE_ENGAGED_DIM = "#2d5f48"
STATE_ENGAGED_GLOW = "#557766"
STATE_PENDING = "#ffcc44"
STATE_STARTING = "#00e6ff"
STATE_MARKET = "#88ccff"

# ---- Tranche row skins -------------------------------------------------
FOLD_RATIO_AMBER = "#ff9900"
FOLD_SOURCE_MANUAL = "#00ccff"
FOLD_TRANCHE_SURFACE = "#123a63"
FOLD_TRANCHE_BORDER = "#6ea6e6"
EXTRACTOR_TRANCHE_SURFACE = "#b3261e"
EXTRACTOR_TRANCHE_BORDER = "#ffb0a6"

# ---- Settings dialog controls ------------------------------------------
SETTINGS_PRIMARY_HOVER = "#00ddaa"
SETTINGS_ON_INFO = "#001122"
SETTINGS_DANGER_SURFACE = "#3a2020"
SETTINGS_WARNING_HOVER = "#ff8833"
SETTINGS_DESTRUCTIVE_SURFACE = "#440011"
SETTINGS_DESTRUCTIVE_HOVER = "#660022"
SETTINGS_DISABLED_SURFACE = "#1a1a1a"
SETTINGS_DISABLED_DEEP = "#333333"
GLOW_PRIMARY_EDGE = "rgba(0,255,204,85)"
GLOW_PRIMARY_FAINT = "rgba(0,255,204,34)"

# ---- Bot visualizer ----------------------------------------------------
VIZ_PANEL_SURFACE = "#0c0c1a"
VIZ_PANEL_BORDER = "#1a1a3f"
VIZ_SWARM_SURFACE = "#070710"
VIZ_TAB_SELECTED = "#0a0a20"
VIZ_TAB_TEXT = "#666677"
VIZ_HEADING = "#c8d8f0"
VIZ_CAPTION = "#445566"
VIZ_CAPTION_DIM = "#556677"
VIZ_LIST_SURFACE = "#0a0a18"
VIZ_LIST_BORDER = "#1a2a4a"
VIZ_LIST_TEXT = "#aaccff"
VIZ_INPUT_SURFACE = "#142244"
VIZ_INPUT_BORDER = "#2244aa"
VIZ_GO_HOVER = "#001a0a"
VIZ_GO_HOVER_DEEP = "#00290f"
VIZ_STOP_HOVER = "#1a0011"
VIZ_STOP_HOVER_DEEP = "#2a0018"
VIZ_SIM_HOVER = "#001a18"
VIZ_GOLD_HOVER = "#1a1400"
VIZ_CONFIRM_SURFACE = "#003822"
VIZ_NUCLEAR_SURFACE = "#ff0000"
VIZ_NUCLEAR_BORDER = "#cc0000"
VIZ_LANE_LIVE = "#091a0e"
VIZ_LANE_PAPER = "#0e0e09"

# ---- Main window chrome ------------------------------------------------
MAIN_TOOLBAR_SURFACE = "#14141e"
MAIN_SEPARATOR = "#2a2a3a"
MAIN_BUTTON_SURFACE = "#1a1a26"
MAIN_BUTTON_BORDER = "#3a3a4a"
MAIN_BUTTON_HOVER = "#22222e"
MAIN_TOGGLE_SURFACE = "#1a1a3a"
MAIN_TOGGLE_HOVER = "#222250"
MAIN_TOGGLE_CHECKED = "#3a1a1a"
MAIN_TOGGLE_CHECKED_AMBER = "#663300"
MAIN_TOOLTIP_BORDER = "#00cccc"
MAIN_TABLE_HEADER = "#c0c4d8"
MAIN_CAPTION = "#7a7d99"
MAIN_BADGE_TEXT = "#7fb3ff"
MAIN_BADGE_MAGENTA = "#ff66dd"
MAIN_ALERT_SURFACE = "#d61a3d"
MAIN_HIGHLIGHT_AMBER = "#33220a"
MAIN_HIGHLIGHT_AMBER_TEXT = "#ffb000"
MAIN_LOG_NAME = "#88c0ff"
MAIN_LOG_SITE = "#667788"
MAIN_LOG_CRITICAL = "#ff0044"

# ---- Stock window ------------------------------------------------------
CARD_STOCK_PANEL = "#0a1020"
CARD_STOCK_BODY = "#aabbcc"
CARD_STOCK_LOG_SURFACE = "#080c18"
CARD_STOCK_BUTTON_BORDER = "#2a3a5f"
CARD_STOCK_BUTTON_HOVER = "#2a3a6f"
STOCK_POSITIVE = "#00cc66"
STOCK_NEGATIVE = "#ff4466"
STOCK_WARNING = "#ddaa00"
STOCK_BUTTON_HOVER = "#0088dd"
STOCK_LOG_DEBUG = "#444455"
STOCK_LOG_TIMESTAMP = "#555566"
STOCK_LOG_CRITICAL = "#ff0033"

# TYPOGRAPHY

# ---- Type ramp, in pixels ------------------------------------------------
TYPE_DISPLAY = 36
TYPE_H1 = 28
TYPE_H2 = 22
TYPE_H3 = 18
TYPE_H4 = 15
TYPE_BODY = 13
TYPE_SMALL = 11
TYPE_CAPTION = 10
TYPE_CARD_VALUE = 16

# ---- Line heights, as a multiple of the type size -------------------------
LINE_HEIGHT_TIGHT = 1.2
LINE_HEIGHT_BODY = 1.4
LINE_HEIGHT_LOOSE = 1.5

# ---- Font families, as the stack a style sheet names ----------------------
FONT_FAMILY_UI = "'Rajdhani', 'Orbitron', 'Segoe UI', sans-serif"
FONT_FAMILY_MONO = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace"

# ---- Font weights --------------------------------------------------------
WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_BOLD = 700

# SPACING, SHAPE, MOTION AND TARGET SIZE

# ---- Spacing, in pixels ------------------------------------------------
SPACE_XS = 4
SPACE_XXS = 2
SPACE_CARD_TIGHT = 10
SPACE_CARD_PAD = 12
SPACE_S = 8
SPACE_M = 16
SPACE_L = 24
SPACE_XL = 32
SPACE_XXL = 48

# ---- Corner radius, in pixels ------------------------------------------
RADIUS_NONE = 0
RADIUS_XS = 4
RADIUS_CARD = 6
RADIUS_SM = 8
RADIUS_MD = 12
RADIUS_LG = 16
RADIUS_FULL = 9999

# ---- Motion, in milliseconds -------------------------------------------
MOTION_INSTANT = 0
MOTION_SHORT = 100
MOTION_MEDIUM = 250
MOTION_LONG = 500
MOTION_EXTRA = 1000

# ---- Pointer target size, in pixels ------------------------------------
TARGET_MIN = 24
TARGET_COMFORTABLE = 32
TARGET_LARGE = 44

# ---- Bot-table fixed column widths, in pixels --------------------------
TABLE_COL_FIRE_W = 70
TABLE_COL_DETAIL_W = 60

# ---- Focus ring, in pixels ---------------------------------------------
FOCUS_RING_WIDTH = 2
FOCUS_RING_OFFSET = 2

# ---- Drop shadow: vertical offset, blur radius, alpha ---------------------
SHADOW_0 = (0, 0, "00")
SHADOW_1 = (1, 2, "40")
SHADOW_2 = (2, 4, "50")
SHADOW_3 = (4, 8, "60")
SHADOW_4 = (8, 16, "70")

# SECOND NAMES FOR A COLOUR ALREADY IN THE TABLE

BG = "#0a0a0f"
CARD = "#141420"
FG = "#e0e0f0"
DIM = "#a8a8c5"
HINT = "#8a8ab0"
FOCUS_RING_COLOR = "#a0a0c0"

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
    "RADIUS_FULL",
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
    "RADIUS_FULL",
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

TOKENS: dict[str, Any] = {name: globals()[name] for name in TOKEN_NAMES}

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
