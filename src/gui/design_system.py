# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""Dark-theme Qt widget tokens.

``SURFACE_0`` through ``SURFACE_4`` and ``TEXT_HIGH`` through ``TEXT_DISABLED``
hold hex values measured against dark grounds. ``TYPE_BODY``, ``SPACE_S``,
``RADIUS_SM``, ``MOTION_MEDIUM``, ``TARGET_MIN`` and ``SHADOW_1`` set the type,
spacing, shape, motion and pointer-target scales. ``__all__`` names every token
``src.gui`` widget code may import, and ``_rgba`` writes the alpha byte Qt reads.
"""

from __future__ import annotations

from .color_alpha import rgba as _rgba

# ---- Surface elevation, lightest tint reads as nearest ---------------------
SURFACE_0 = "#0a0a0f"  # App root, lowest elevation
SURFACE_1 = "#141420"  # Default card and panel ground
SURFACE_2 = "#1a1a28"  # Raised cards and popovers
SURFACE_3 = "#22223a"  # Modal surfaces
SURFACE_4 = "#2a2a44"  # Menus, tooltips, top-most dialogs

# ---- Text roles ------------------------------------------------------------
TEXT_HIGH = "#e0e0f0"  # Primary body text (≥10.63:1 on SURFACE_0-4)
TEXT_MED = "#a8a8c5"  # Secondary text, labels (≥6.68:1 on SURFACE_0-3)
TEXT_LOW = "#8a8ab0"  # Tertiary, hints, metadata (≥4.67:1 on SURFACE_0-3)
TEXT_DISABLED = "#555577"  # Disabled foreground (2.78:1 on SURFACE_0)

# ---- Primary accent --------------------------------------------------------
PRIMARY = "#00ffcc"  # The signature accent (15.21:1 on SURFACE_0)
ON_PRIMARY = "#003d33"  # Text on PRIMARY-colored surface (9.43:1)
PRIMARY_CONTAINER = "#00998a"  # PRIMARY-tinted container background
ON_PRIMARY_CONTAINER = "#c8fff0"  # Text on PRIMARY_CONTAINER

# ---- Secondary accent ------------------------------------------------------
SECONDARY = "#ff00aa"
ON_SECONDARY = "#3d0029"
SECONDARY_CONTAINER = "#a8006d"
ON_SECONDARY_CONTAINER = "#ffd8ee"

# ---- Semantic roles, ratios measured on SURFACE_0 --------------------------
SUCCESS = "#00ff88"  # 14.73:1, accumulation and profit
DANGER = "#ff5577"  # 6.41:1
WARNING = "#ffaa00"  # 10.35:1, caution states
INFO = "#4fc3ff"  # 9.95:1

# ---- Outlines and borders, ratios measured on SURFACE_0 through SURFACE_3 --
OUTLINE = "#7a7a9c"  # Default borders (≥3.75:1 on SURFACE_0-3)
OUTLINE_STRONG = "#a0a0c0"  # Focus rings, emphasized edges (≥6.1:1)

# ---- Glow and scrim; _rgba carries the alpha byte --------------------------
GLOW_PRIMARY = _rgba(PRIMARY, 51)
GLOW_SECONDARY = _rgba(SECONDARY, 51)
SCRIM = _rgba("#000000", 136)  # Dialog backdrop

# ---- Stat-card skins; the stock window and analytics tab differ ------------
CARD_STOCK_SURFACE = "#0e1428"  # Stock window card background
CARD_STOCK_BORDER = "#1a2a4f"
CARD_STOCK_LABEL = "#6688aa"
CARD_STOCK_VALUE = "#e0e8f0"
CARD_METRIC_SURFACE = "#12121f"  # Analytics tab card background
CARD_METRIC_BORDER = "#2a2a3f"
CARD_METRIC_LABEL = "#888"

# ---- Widget colours ---------------------------------------------------------

# Semantic roles the widgets render
ERROR = "#ff3366"  # Negative P&L, destructive controls, error text
WARNING_STRONG = "#ff6600"  # Cooldown state, warning-action button
STATUS_INFO = "#00aaff"  # Info log level, connection status
STATUS_NEUTRAL = "#8899aa"  # Neutral log level, no-data mark
STATUS_AUTHENTICATED = "#00ddff"  # Authenticated / armed indicator text
PRIMARY_BRIGHT = "#00ffee"  # Brighter cyan accent: privacy dot, Sim tab
ACCENT_GOLD = "#ffd700"  # Paper lane accent in the visualizer
LAYER_CRYPTO = "#00ccaa"  # Crypto layer accent
LAYER_STOCK = "#6699ff"  # Stock layer accent

# Text roles beyond TEXT_HIGH / MED / LOW
TEXT_MAX = "#ffffff"  # Maximum-contrast emphasis
TEXT_NEUTRAL = "#cccccc"  # Default value text
TEXT_CONSOLE = "#c0c0c0"  # Console body text
TEXT_INACTIVE = "#aaaaaa"  # Idle control text
TEXT_EMPTY_STATE = "#8a8aab"  # Empty-list and footer text
TEXT_MUTED = "#666666"  # Stopped state, disabled foreground
TEXT_PLACEHOLDER = "#555555"  # Empty-state and disabled-button text
TEXT_INFO_SOFT = "#66ccff"  # Soft info text
TEXT_LOG_MINT = "#c0ffe0"  # Gate-log console text
TEXT_ON_LIGHT = "#000000"  # Text on a light control

# Surfaces beyond SURFACE_0..4
SURFACE_CHART = "#0a0a12"  # Chart, console and group-box ground
SURFACE_CONTROL = "#1a1a2e"  # Chart gridline and control ground
SURFACE_INPUT = "#0e0e1a"  # Check box, radio and text field ground
SURFACE_CONSOLE = "#05050a"  # Console ground
SURFACE_CONSOLE_HEADER = "#0a0a14"  # Console header ground
BORDER_DISABLED = "#444444"  # Disabled control border

# Context menu
MENU_SURFACE = "#1a1a2f"  # Context-menu ground
MENU_BORDER = "#3a3a5f"  # Context-menu border and hover ground
MENU_ITEM_SELECTED = "#2a2a4f"  # Selected menu-item ground

# Control states
STATE_ARMED = "#3ed080"  # Armed control border and text
STATE_ENGAGED = "#2d9d5f"  # Engaged control ground
STATE_ENGAGED_DIM = "#2d5f48"  # Dimmed engaged ground
STATE_ENGAGED_GLOW = "#557766"  # Glow on the engaged control
STATE_PENDING = "#ffcc44"  # Pending-attention border and glow
STATE_STARTING = "#00e6ff"  # Starting state
STATE_MARKET = "#88ccff"  # Market state

# Tranche row skins
FOLD_RATIO_AMBER = "#ff9900"  # Fold-ratio amber foreground
FOLD_SOURCE_MANUAL = "#00ccff"  # Manual fold-source foreground
FOLD_TRANCHE_SURFACE = "#123a63"  # Fold tranche row ground
FOLD_TRANCHE_BORDER = "#6ea6e6"  # Fold tranche row border
EXTRACTOR_TRANCHE_SURFACE = "#b3261e"  # Extractor tranche row ground
EXTRACTOR_TRANCHE_BORDER = "#ffb0a6"  # Extractor tranche row border

# Settings dialog controls
SETTINGS_PRIMARY_HOVER = "#00ddaa"  # Primary button hover ground
SETTINGS_ON_INFO = "#001122"  # Text on the cyan hover fill
SETTINGS_DANGER_SURFACE = "#3a2020"  # Amber/danger button ground
SETTINGS_WARNING_HOVER = "#ff8833"  # Warning button hover ground
SETTINGS_DESTRUCTIVE_SURFACE = "#440011"  # Destructive button ground
SETTINGS_DESTRUCTIVE_HOVER = "#660022"  # Destructive button hover ground
SETTINGS_DISABLED_SURFACE = "#1a1a1a"  # Disabled button ground
SETTINGS_DISABLED_DEEP = "#333333"  # Disabled button ground, deeper variant
GLOW_PRIMARY_EDGE = _rgba(PRIMARY, 85)  # PRIMARY tint on a border
GLOW_PRIMARY_FAINT = _rgba(PRIMARY, 34)  # PRIMARY tint on a hover fill

# Bot visualizer
VIZ_PANEL_SURFACE = "#0c0c1a"  # Tab and button ground
VIZ_PANEL_BORDER = "#1a1a3f"  # Pane and group-box border
VIZ_SWARM_SURFACE = "#070710"  # Swarm scroll-area ground
VIZ_TAB_SELECTED = "#0a0a20"  # Selected tab ground
VIZ_TAB_TEXT = "#666677"  # Unselected tab text
VIZ_HEADING = "#c8d8f0"  # 9px heading text
VIZ_CAPTION = "#445566"  # 8px caption text
VIZ_CAPTION_DIM = "#556677"  # 8px caption text, dimmer variant
VIZ_LIST_SURFACE = "#0a0a18"  # List and frame ground
VIZ_LIST_BORDER = "#1a2a4a"  # List and frame border
VIZ_LIST_TEXT = "#aaccff"  # List and line-edit text
VIZ_INPUT_SURFACE = "#142244"  # Line-edit ground and list hover
VIZ_INPUT_BORDER = "#2244aa"  # Line-edit border
VIZ_GO_HOVER = "#001a0a"  # Green button hover ground
VIZ_GO_HOVER_DEEP = "#00290f"  # Green button hover ground, deeper variant
VIZ_STOP_HOVER = "#1a0011"  # Red button hover ground
VIZ_STOP_HOVER_DEEP = "#2a0018"  # Red button hover ground, deeper variant
VIZ_SIM_HOVER = "#001a18"  # Sim button hover ground
VIZ_GOLD_HOVER = "#1a1400"  # Gold button hover ground
VIZ_CONFIRM_SURFACE = "#003822"  # Confirm button ground
VIZ_NUCLEAR_SURFACE = "#ff0000"  # Nuclear control ground
VIZ_NUCLEAR_BORDER = "#cc0000"  # Nuclear control border
VIZ_LANE_LIVE = "#091a0e"  # Live and sim lane row tint
VIZ_LANE_PAPER = "#0e0e09"  # Paper lane row tint

# Main window chrome
MAIN_TOOLBAR_SURFACE = "#14141e"  # Toolbar strip ground
MAIN_SEPARATOR = "#2a2a3a"  # Header separator and toolbar rule
MAIN_BUTTON_SURFACE = "#1a1a26"  # Toolbar button ground
MAIN_BUTTON_BORDER = "#3a3a4a"  # Toolbar button border
MAIN_BUTTON_HOVER = "#22222e"  # Toolbar button hover ground
MAIN_TOGGLE_SURFACE = "#1a1a3a"  # Toggle button ground
MAIN_TOGGLE_HOVER = "#222250"  # Toggle button hover ground
MAIN_TOGGLE_CHECKED = "#3a1a1a"  # Checked toggle ground
MAIN_TOGGLE_CHECKED_AMBER = "#663300"  # Checked amber toggle ground
MAIN_TOOLTIP_BORDER = "#00cccc"  # Tooltip border
MAIN_TABLE_HEADER = "#c0c4d8"  # Table header text
MAIN_CAPTION = "#7a7d99"  # 10px caption text
MAIN_BADGE_TEXT = "#7fb3ff"  # Badge text
MAIN_BADGE_MAGENTA = "#ff66dd"  # Magenta badge text
MAIN_ALERT_SURFACE = "#d61a3d"  # Alert banner ground
MAIN_HIGHLIGHT_AMBER = "#33220a"  # Amber text-highlight ground
MAIN_HIGHLIGHT_AMBER_TEXT = "#ffb000"  # Amber text-highlight foreground
MAIN_LOG_NAME = "#88c0ff"  # Log name field
MAIN_LOG_SITE = "#667788"  # Log site field
MAIN_LOG_CRITICAL = "#ff0044"  # Critical log level

# Stock window
CARD_STOCK_PANEL = "#0a1020"  # Panel and group-box ground
CARD_STOCK_BODY = "#aabbcc"  # Body text
CARD_STOCK_LOG_SURFACE = "#080c18"  # Log view ground
CARD_STOCK_BUTTON_BORDER = "#2a3a5f"  # Button border
CARD_STOCK_BUTTON_HOVER = "#2a3a6f"  # Button hover ground
STOCK_POSITIVE = "#00cc66"  # Gain
STOCK_NEGATIVE = "#ff4466"  # Loss
STOCK_WARNING = "#ddaa00"  # Warning log level
STOCK_BUTTON_HOVER = "#0088dd"  # Primary button hover ground
STOCK_LOG_DEBUG = "#444455"  # Debug log level
STOCK_LOG_TIMESTAMP = "#555566"  # Log timestamp
STOCK_LOG_CRITICAL = "#ff0033"  # Critical log level

# ---- Type sizes in whole pixels, ramp steps of 1.10 to 1.29 ----------------

TYPE_DISPLAY = 36  # Hero numbers and big headlines
TYPE_H1 = 28  # Page titles
TYPE_H2 = 22  # Section headers
TYPE_H3 = 18  # Subsection headers
TYPE_H4 = 15  # Card titles
TYPE_BODY = 13  # base size
TYPE_SMALL = 11  # labels, metadata
TYPE_CAPTION = 10  # dense captions only — avoid for primary info

TYPE_CARD_VALUE = 16  # stat-card value text

# Line heights as a multiplier of the type size
LINE_HEIGHT_TIGHT = 1.2  # display / headings
LINE_HEIGHT_BODY = 1.4  # body text
LINE_HEIGHT_LOOSE = 1.5  # long-form reading

FONT_FAMILY_UI = "'Rajdhani', 'Orbitron', 'Segoe UI', sans-serif"
FONT_FAMILY_MONO = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace"

# Font weights on the CSS 100-to-900 scale
WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_BOLD = 700

# ---- Layout spacing in pixels ----------------------------------------------

SPACE_XS = 4  # Intra-control spacing (icon-to-label gap)
SPACE_XXS = 2  # Label-to-value gap inside a stat card
SPACE_CARD_TIGHT = 10  # Stat-card padding, short edge
SPACE_CARD_PAD = 12  # Stat-card padding, long edge
SPACE_S = 8  # Default control padding
SPACE_M = 16  # Between related controls
SPACE_L = 24  # Between groups
SPACE_XL = 32  # Between sections
SPACE_XXL = 48  # Between major regions

# ---- Corner radii ----------------------------------------------------------
RADIUS_NONE = 0
RADIUS_XS = 4  # Chips, tight inputs
RADIUS_CARD = 6  # Analytics metric cards
RADIUS_SM = 8  # Default — buttons, inputs, cards
RADIUS_MD = 12  # Elevated cards, dialogs
RADIUS_LG = 16  # Large surfaces, bottom sheets (rare in desktop)
RADIUS_FULL = 9999  # Pills, fully round

# ---- Animation durations in milliseconds -----------------------------------

MOTION_INSTANT = 0  # No animation
MOTION_SHORT = 100  # State change (hover → pressed)
MOTION_MEDIUM = 250  # Panel open/close, tab switch
MOTION_LONG = 500  # Dramatic reveals, onboarding
MOTION_EXTRA = 1000  # Splash / first-run only

# ---- Pointer target minimums in pixels -------------------------------------

TARGET_MIN = 24  # WCAG SC 2.5.8 floor, dense tables only

COIN_ICON_SIZE_PX = 18  # Coin badge in the Scrumming and Extractor Symbol cell
TARGET_COMFORTABLE = 32  # Default for most interactive controls
TARGET_LARGE = 44  # Primary CTAs, important toggles

# Bot-table action columns; a column absent from fixed_widths stretches
TABLE_COL_FIRE_W = 70  # Fire button column
TABLE_COL_DETAIL_W = 60  # Detail button column

# ---- Focus ring, composed into QSS at the callsite -------------------------

FOCUS_RING_WIDTH = 2  # px
FOCUS_RING_OFFSET = 2  # px gap between widget and ring
FOCUS_RING_COLOR = OUTLINE_STRONG  # 7.79:1 on SURFACE_0

# ---- Shadows as (offset_y, blur_radius, alpha_hex) -------------------------

SHADOW_0 = (0, 0, "00")  # No shadow
SHADOW_1 = (1, 2, "40")  # Cards
SHADOW_2 = (2, 4, "50")  # Raised cards
SHADOW_3 = (4, 8, "60")  # Modals
SHADOW_4 = (8, 16, "70")  # Top-most dialogs


# ---- Short aliases for five tokens above -----------------------------------

BG = SURFACE_0
CARD = SURFACE_1
FG = TEXT_HIGH
DIM = TEXT_MED
HINT = TEXT_LOW


__all__ = [
    # Surfaces
    "SURFACE_0",
    "SURFACE_1",
    "SURFACE_2",
    "SURFACE_3",
    "SURFACE_4",
    # Text
    "TEXT_HIGH",
    "TEXT_MED",
    "TEXT_LOW",
    "TEXT_DISABLED",
    # Primary / secondary
    "PRIMARY",
    "ON_PRIMARY",
    "PRIMARY_CONTAINER",
    "ON_PRIMARY_CONTAINER",
    "SECONDARY",
    "ON_SECONDARY",
    "SECONDARY_CONTAINER",
    "ON_SECONDARY_CONTAINER",
    # Semantic
    "SUCCESS",
    "DANGER",
    "WARNING",
    "INFO",
    # Outlines
    "OUTLINE",
    "OUTLINE_STRONG",
    # Glow / scrim
    "GLOW_PRIMARY",
    "GLOW_SECONDARY",
    "SCRIM",
    # Stat-card skins
    "CARD_STOCK_SURFACE",
    "CARD_STOCK_BORDER",
    "CARD_STOCK_LABEL",
    "CARD_STOCK_VALUE",
    "CARD_METRIC_SURFACE",
    "CARD_METRIC_BORDER",
    "CARD_METRIC_LABEL",
    # Widget colours
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
    # Type
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
    # Spacing
    "SPACE_XS",
    "SPACE_XXS",
    "SPACE_CARD_TIGHT",
    "SPACE_CARD_PAD",
    "SPACE_S",
    "SPACE_M",
    "SPACE_L",
    "SPACE_XL",
    "SPACE_XXL",
    # Shape
    "RADIUS_NONE",
    "RADIUS_XS",
    "RADIUS_CARD",
    "RADIUS_SM",
    "RADIUS_MD",
    "RADIUS_LG",
    "RADIUS_FULL",
    # Motion
    "MOTION_INSTANT",
    "MOTION_SHORT",
    "MOTION_MEDIUM",
    "MOTION_LONG",
    "MOTION_EXTRA",
    # Target sizes
    "TARGET_MIN",
    "COIN_ICON_SIZE_PX",
    "TARGET_COMFORTABLE",
    "TARGET_LARGE",
    "TABLE_COL_FIRE_W",
    "TABLE_COL_DETAIL_W",
    # Focus
    "FOCUS_RING_WIDTH",
    "FOCUS_RING_OFFSET",
    "FOCUS_RING_COLOR",
    # Shadows
    "SHADOW_0",
    "SHADOW_1",
    "SHADOW_2",
    "SHADOW_3",
    "SHADOW_4",
    # Aliases
    "BG",
    "CARD",
    "FG",
    "DIM",
    "HINT",
]
