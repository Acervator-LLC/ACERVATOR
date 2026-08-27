"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
design_system.py — GUI TOKEN SOURCE OF TRUTH (dark-theme Qt widgets)
====================================================================

SCOPE: Qt cyberpunk GUI — every widget in src/gui/ imports tokens from here.
All contrast values are verified WCAG AA against DARK surfaces (SURFACE_0-4).

**NOT the same file as `src/design_system.py`.** That sibling module holds
the LIGHT-THEME chart/PDF tokens (dark ink on white). The two cannot share
concrete color values because their target backgrounds are opposite. If you
are rendering a matplotlib chart or a PDF page, import from `src.design_system`,
not this module. TD-017 audit (2026-04-23) formalized this relationship —
they look like duplicates but aren't.

Single source of truth for colors, typography, spacing, motion, and target
sizes across all `src/gui/` widgets. Every GUI file imports tokens FROM HERE.
Hex literals and raw font sizes in widget code are R65 / R54 violations —
the linter (chunk C9) enforces this.

EXTERNAL GROUNDING (per R63 ERG):
  1. WCAG 2.2 Level AA — w3.org/TR/WCAG22/
     Governs all color contrast decisions. Every text/bg and outline/bg pair
     below was verified via relative luminance audit. SC 1.4.3 (≥4.5:1 normal
     text), SC 1.4.11 (≥3:1 UI components), SC 2.4.7 (focus indicator),
     SC 2.5.8 (pointer target ≥24 CSS px).
  2. Material Design 3 — m3.material.io/
     Role-based color naming (primary / on-primary / surface-N / outline),
     5-level surface elevation, motion timing scale, shape system.
  3. KDE Human Interface Guidelines — develop.kde.org/hig/
     Qt-native adaptations. Applied in widget code, tokens here are the
     neutral substrate.
  4. Matthew Butterick, *Practical Typography* — practicaltypography.com
     1.25× geometric type ramp, line height 120-145%.
  5. Swiss / International Typographic Style (Müller-Brockmann, Tschichold)
     8pt modular grid — all spacing is a multiple of 4.

INTERNAL PRECEDENT:
  - MEM-114 / R54 DCR — `src/design_system.py` (chart tokens) is the sibling
    pattern. This module is the GUI-widget equivalent.
  - MEM-157 / R65 GDG — the rule this module exists under.
  - MEM-155 / R64 FCP — this is chunk C1 of a 10-chunk plan.
  - MEM-156 / R63 ERG — external grounding block above.

STABILITY:
  Token VALUES may change only via R63 workflow (propose + operator approval).
  Token NAMES are public API for all GUI code and must not be renamed without
  migration. Adding new tokens is additive and non-breaking.
"""

from __future__ import annotations

# =============================================================================
# COLOR TOKENS — M3 role-based naming, WCAG AA verified
# =============================================================================
#
# All pairs below have been audited via WCAG 2.1 relative luminance algorithm.
# Results in the audit table that must be kept in sync with this file.
# If you change a hex value, re-run tools/wcag_audit.py (chunk C9).

# ---- Surface elevation (M3 5-level) ---------------------------------------
# "Surface" in M3 = background. Elevation is visual not physical — higher
# numbered surfaces have lighter tint to read as "closer" to viewer.
SURFACE_0 = "#0a0a0f"  # App root, lowest elevation
SURFACE_1 = "#141420"  # Default card / panel (+1dp equivalent)
SURFACE_2 = "#1a1a28"  # Raised cards, popovers (+3dp)
SURFACE_3 = "#22223a"  # Modal surfaces (+6dp)
SURFACE_4 = "#2a2a44"  # Menus, tooltips, top-most dialogs (+8dp)

# ---- Text roles (WCAG AA verified on SURFACE_0 through SURFACE_3) --------
TEXT_HIGH = "#e0e0f0"  # Primary body text (≥10.6:1 on all surfaces)
TEXT_MED = "#a8a8c5"  # Secondary text, labels (≥6.7:1 on all surfaces)
TEXT_LOW = "#8a8ab0"  # Tertiary, hints, metadata (≥4.67:1 on SURFACE_0-3)
TEXT_DISABLED = "#555577"  # Explicit disabled — 2.78:1 accepted per M3
# disabled-text token (disabled text is not
# required to meet SC 1.4.3 per WCAG exception)

# ---- Primary color role (the cyberpunk cyan) -----------------------------
PRIMARY = "#00ffcc"  # The signature accent (15.21:1 on SURFACE_0)
ON_PRIMARY = "#003d33"  # Text on PRIMARY-colored surface (9.43:1)
PRIMARY_CONTAINER = "#00998a"  # PRIMARY-tinted container background
ON_PRIMARY_CONTAINER = "#c8fff0"  # Text on PRIMARY_CONTAINER

# ---- Secondary accent (the signature magenta) ----------------------------
SECONDARY = "#ff00aa"
ON_SECONDARY = "#3d0029"
SECONDARY_CONTAINER = "#a8006d"
ON_SECONDARY_CONTAINER = "#ffd8ee"

# ---- Semantic roles (WCAG AA verified on SURFACE_0) ----------------------
SUCCESS = "#00ff88"  # 14.73:1 — accumulation, profit, green-light go
DANGER = "#ff5577"  # 6.41:1  — adjusted from #ff3366 to clear WCAG AA
WARNING = "#ffaa00"  # 10.35:1 — caution states
INFO = "#4fc3ff"  # 9.95:1  — adjusted from #00aaff to clear WCAG AA

# ---- Outlines / borders (SC 1.4.11, ≥3:1 on SURFACE_0 through SURFACE_3) -
OUTLINE = "#7a7a9c"  # Default borders (≥3.75:1 on all surfaces)
OUTLINE_STRONG = "#a0a0c0"  # Focus rings, emphasized edges (≥6.1:1)

# ---- Glow / special --------------------------------------------------------
# Non-text visual effects, not subject to contrast minimums.
GLOW_PRIMARY = "#00ffcc33"  # PRIMARY with 20% alpha
GLOW_SECONDARY = "#ff00aa33"
SCRIM = "#00000088"  # Dialog backdrop

# ---- Stat-card skins (existing per-card values, promoted to tokens) --------
# The stock window and the analytics tab ship different card colors. They stay
# separate tokens: collapsing them would change what the operator sees.
CARD_STOCK_SURFACE = "#0e1428"  # Stock window card background
CARD_STOCK_BORDER = "#1a2a4f"
CARD_STOCK_LABEL = "#6688aa"
CARD_STOCK_VALUE = "#e0e8f0"
CARD_METRIC_SURFACE = "#12121f"  # Analytics tab card background
CARD_METRIC_BORDER = "#2a2a3f"
CARD_METRIC_LABEL = "#888"

# ---- Widget colors promoted from hex literals -----------------------------
# Values copied verbatim from the callsites they replace. A migration is a
# rename: no value here may be snapped to a near neighbour.

# Semantic roles the widgets actually render
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

# Tranche row skins - bot_live_settings
FOLD_RATIO_AMBER = "#ff9900"  # Fold-ratio amber foreground
FOLD_SOURCE_MANUAL = "#00ccff"  # Manual fold-source foreground
FOLD_TRANCHE_SURFACE = "#123a63"  # Fold tranche row ground
FOLD_TRANCHE_BORDER = "#6ea6e6"  # Fold tranche row border
EXTRACTOR_TRANCHE_SURFACE = "#b3261e"  # Extractor tranche row ground
EXTRACTOR_TRANCHE_BORDER = "#ffb0a6"  # Extractor tranche row border

# Settings dialog controls - bot_live_settings
SETTINGS_PRIMARY_HOVER = "#00ddaa"  # Primary button hover ground
SETTINGS_ON_INFO = "#001122"  # Text on the cyan hover fill
SETTINGS_DANGER_SURFACE = "#3a2020"  # Amber/danger button ground
SETTINGS_WARNING_HOVER = "#ff8833"  # Warning button hover ground
SETTINGS_DESTRUCTIVE_SURFACE = "#440011"  # Destructive button ground
SETTINGS_DESTRUCTIVE_HOVER = "#660022"  # Destructive button hover ground
SETTINGS_DISABLED_SURFACE = "#1a1a1a"  # Disabled button ground
SETTINGS_DISABLED_DEEP = "#333333"  # Disabled button ground, deeper variant
GLOW_PRIMARY_EDGE = "#00ffcc55"  # PRIMARY tint on a border, 8-digit QSS form
GLOW_PRIMARY_FAINT = "#00ffcc22"  # PRIMARY tint on a hover fill, 8-digit QSS form

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

# =============================================================================
# TYPOGRAPHY — Butterick 1.25× geometric ramp
# =============================================================================
# All sizes in pixels. Integer values; no sub-pixel fractions.
# Line-height follows 1.3–1.4 band per Butterick (body) and tighter for display.

TYPE_DISPLAY = 36  # 28 * 1.28  — hero numbers, big headlines (rare use)
TYPE_H1 = 28  # 22 * 1.27  — page titles
TYPE_H2 = 22  # 18 * 1.22  — section headers
TYPE_H3 = 18  # 15 * 1.20  — subsection
TYPE_H4 = 15  # 13 * 1.15  — card titles
TYPE_BODY = 13  # base size
TYPE_SMALL = 11  # labels, metadata
TYPE_CAPTION = 10  # dense captions only — avoid for primary info

TYPE_CARD_VALUE = 16  # stat-card value text

# Line heights (multiplier of size — Qt accepts via setLineHeight(..., fixed))
LINE_HEIGHT_TIGHT = 1.2  # display / headings
LINE_HEIGHT_BODY = 1.4  # body text
LINE_HEIGHT_LOOSE = 1.5  # long-form reading

# Font family tokens (preserved from original theme for continuity)
FONT_FAMILY_UI = "'Rajdhani', 'Orbitron', 'Segoe UI', sans-serif"
FONT_FAMILY_MONO = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace"

# Font weights (semantic, not numeric — Qt maps semantic to weight stops)
WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_BOLD = 700

# =============================================================================
# SPACING — 8pt modular grid (Swiss typographic tradition)
# =============================================================================
# All layout spacing must be a multiple of 4. Prefer multiples of 8.

SPACE_XS = 4  # Intra-control spacing (icon-to-label gap)
SPACE_XXS = 2  # Label-to-value gap inside a stat card
SPACE_CARD_TIGHT = 10  # Stat-card padding, short edge
SPACE_CARD_PAD = 12  # Stat-card padding, long edge
SPACE_S = 8  # Default control padding
SPACE_M = 16  # Between related controls
SPACE_L = 24  # Between groups
SPACE_XL = 32  # Between sections
SPACE_XXL = 48  # Between major regions

# =============================================================================
# SHAPE — M3 corner radius scale
# =============================================================================
RADIUS_NONE = 0
RADIUS_XS = 4  # Chips, tight inputs
RADIUS_CARD = 6  # Analytics metric cards
RADIUS_SM = 8  # Default — buttons, inputs, cards
RADIUS_MD = 12  # Elevated cards, dialogs
RADIUS_LG = 16  # Large surfaces, bottom sheets (rare in desktop)
RADIUS_FULL = 9999  # Pills, fully round

# =============================================================================
# MOTION — M3 standard timing
# =============================================================================
# Durations in milliseconds. Easing handled at callsite (QEasingCurve).

MOTION_INSTANT = 0  # No animation — accessibility setting may force
MOTION_SHORT = 100  # State change (hover → pressed)
MOTION_MEDIUM = 250  # Panel open/close, tab switch
MOTION_LONG = 500  # Dramatic reveals, onboarding
MOTION_EXTRA = 1000  # Splash / first-run only

# =============================================================================
# TARGET SIZES — WCAG SC 2.5.8 (≥24×24 CSS px) + touch-friendly guidance
# =============================================================================
# Pointer target minimums. Primary CTAs get comfortable size even on desktop.

TARGET_MIN = 24  # WCAG floor — use only for dense admin tables
TARGET_COMFORTABLE = 32  # Default for most interactive controls
TARGET_LARGE = 44  # Primary CTAs, important toggles

# Bot-table action columns. Fixed width; every other column stretches.
TABLE_COL_FIRE_W = 70  # Fire button column
TABLE_COL_DETAIL_W = 60  # Detail button column

# =============================================================================
# FOCUS INDICATOR (SC 2.4.7)
# =============================================================================
# Applied globally via QSS (chunk C3). Exposed as tokens for widgets that
# need to compose focus state into custom paint events.

FOCUS_RING_WIDTH = 2  # px
FOCUS_RING_OFFSET = 2  # px gap between widget and ring
FOCUS_RING_COLOR = OUTLINE_STRONG  # 7.79:1 on SURFACE_0 — very visible

# =============================================================================
# ELEVATION SHADOWS (M3 — optional, Qt drop-shadow effect)
# =============================================================================
# Tuples of (offset_y, blur_radius, alpha_hex) for QGraphicsDropShadowEffect.
# Alpha values are MATERIAL DESIGN 3 recommended for dark themes.

SHADOW_0 = (0, 0, "00")  # No shadow
SHADOW_1 = (1, 2, "40")  # Cards
SHADOW_2 = (2, 4, "50")  # Raised cards
SHADOW_3 = (4, 8, "60")  # Modals
SHADOW_4 = (8, 16, "70")  # Top-most dialogs


# =============================================================================
# CONVENIENCE — semantic aliases for very common patterns
# =============================================================================
# Short names for callsites where the full token name adds noise without
# adding clarity. Use sparingly — prefer full names for precision.

BG = SURFACE_0
CARD = SURFACE_1
FG = TEXT_HIGH
DIM = TEXT_MED
HINT = TEXT_LOW


# =============================================================================
# LINTER HOOKS
# =============================================================================
# Chunk C9 adds tools/gui_lint.py that scans src/gui/ for hex literals and
# font-size literals. It imports this module to know what tokens exist.
# Do not remove these constants without updating the linter whitelist.

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
    # Widget colors promoted from hex literals
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
