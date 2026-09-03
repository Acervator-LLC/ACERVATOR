"""The shipped design tokens and the Qt-free surface, side by side.

A failure means the view model carries a different colour, a different
type size, a different spacing, a different radius, a different motion
duration, a different target size, a different focus setting, a
different shadow or a different second name than
``src.gui.design_system`` ships.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import design_system as shipped
from src.gui.main_tabs import design_system_surface as surface
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

SHIPPED_PATH = REPO_ROOT / "src/gui/design_system.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/design_system_surface.py"
BRIDGE_PATH = REPO_ROOT / "src/core/desktop_bridge.py"
CALLER_PATH = REPO_ROOT / "src/gui/widgets/bot_status_table.py"

METHOD_NAME = "design_system.state"

PIXEL_SIZE = (980, 400)

TOKEN_TOTAL = 195
COLOR_TOTAL = 139
ALIAS_TOTAL = 6
GROUP_TOTAL = 13

# Every token value, typed out here rather than read from either module.
# Neither side can satisfy this table by copying the other, and an edit
# made to both files together is still reported.
EXPECTED = {
    "SURFACE_0": "#0a0a0f",
    "SURFACE_1": "#141420",
    "SURFACE_2": "#1a1a28",
    "SURFACE_3": "#22223a",
    "SURFACE_4": "#2a2a44",
    "TEXT_HIGH": "#e0e0f0",
    "TEXT_MED": "#a8a8c5",
    "TEXT_LOW": "#8a8ab0",
    "TEXT_DISABLED": "#555577",
    "PRIMARY": "#00ffcc",
    "ON_PRIMARY": "#003d33",
    "PRIMARY_CONTAINER": "#00998a",
    "ON_PRIMARY_CONTAINER": "#c8fff0",
    "SECONDARY": "#ff00aa",
    "ON_SECONDARY": "#3d0029",
    "SECONDARY_CONTAINER": "#a8006d",
    "ON_SECONDARY_CONTAINER": "#ffd8ee",
    "SUCCESS": "#00ff88",
    "DANGER": "#ff5577",
    "WARNING": "#ffaa00",
    "INFO": "#4fc3ff",
    "OUTLINE": "#7a7a9c",
    "OUTLINE_STRONG": "#a0a0c0",
    "GLOW_PRIMARY": "rgba(0,255,204,51)",
    "GLOW_SECONDARY": "rgba(255,0,170,51)",
    "SCRIM": "rgba(0,0,0,136)",
    "CARD_STOCK_SURFACE": "#0e1428",
    "CARD_STOCK_BORDER": "#1a2a4f",
    "CARD_STOCK_LABEL": "#6688aa",
    "CARD_STOCK_VALUE": "#e0e8f0",
    "CARD_METRIC_SURFACE": "#12121f",
    "CARD_METRIC_BORDER": "#2a2a3f",
    "CARD_METRIC_LABEL": "#888",
    "ERROR": "#ff3366",
    "WARNING_STRONG": "#ff6600",
    "STATUS_INFO": "#00aaff",
    "STATUS_NEUTRAL": "#8899aa",
    "STATUS_AUTHENTICATED": "#00ddff",
    "PRIMARY_BRIGHT": "#00ffee",
    "ACCENT_GOLD": "#ffd700",
    "LAYER_CRYPTO": "#00ccaa",
    "LAYER_STOCK": "#6699ff",
    "TEXT_MAX": "#ffffff",
    "TEXT_NEUTRAL": "#cccccc",
    "TEXT_CONSOLE": "#c0c0c0",
    "TEXT_INACTIVE": "#aaaaaa",
    "TEXT_EMPTY_STATE": "#8a8aab",
    "TEXT_MUTED": "#666666",
    "TEXT_PLACEHOLDER": "#555555",
    "TEXT_INFO_SOFT": "#66ccff",
    "TEXT_LOG_MINT": "#c0ffe0",
    "TEXT_ON_LIGHT": "#000000",
    "SURFACE_CHART": "#0a0a12",
    "SURFACE_CONTROL": "#1a1a2e",
    "SURFACE_CONSOLE": "#05050a",
    "SURFACE_CONSOLE_HEADER": "#0a0a14",
    "BORDER_DISABLED": "#444444",
    "MENU_SURFACE": "#1a1a2f",
    "MENU_BORDER": "#3a3a5f",
    "MENU_ITEM_SELECTED": "#2a2a4f",
    "STATE_ARMED": "#3ed080",
    "STATE_ENGAGED": "#2d9d5f",
    "STATE_ENGAGED_DIM": "#2d5f48",
    "STATE_ENGAGED_GLOW": "#557766",
    "STATE_PENDING": "#ffcc44",
    "STATE_STARTING": "#00e6ff",
    "STATE_MARKET": "#88ccff",
    "FOLD_RATIO_AMBER": "#ff9900",
    "FOLD_SOURCE_MANUAL": "#00ccff",
    "FOLD_TRANCHE_SURFACE": "#123a63",
    "FOLD_TRANCHE_BORDER": "#6ea6e6",
    "EXTRACTOR_TRANCHE_SURFACE": "#b3261e",
    "EXTRACTOR_TRANCHE_BORDER": "#ffb0a6",
    "SETTINGS_PRIMARY_HOVER": "#00ddaa",
    "SETTINGS_ON_INFO": "#001122",
    "SETTINGS_DANGER_SURFACE": "#3a2020",
    "SETTINGS_WARNING_HOVER": "#ff8833",
    "SETTINGS_DESTRUCTIVE_SURFACE": "#440011",
    "SETTINGS_DESTRUCTIVE_HOVER": "#660022",
    "SETTINGS_DISABLED_SURFACE": "#1a1a1a",
    "SETTINGS_DISABLED_DEEP": "#333333",
    "GLOW_PRIMARY_EDGE": "rgba(0,255,204,85)",
    "GLOW_PRIMARY_FAINT": "rgba(0,255,204,34)",
    "VIZ_PANEL_SURFACE": "#0c0c1a",
    "VIZ_PANEL_BORDER": "#1a1a3f",
    "VIZ_SWARM_SURFACE": "#070710",
    "VIZ_TAB_SELECTED": "#0a0a20",
    "VIZ_TAB_TEXT": "#666677",
    "VIZ_HEADING": "#c8d8f0",
    "VIZ_CAPTION": "#445566",
    "VIZ_CAPTION_DIM": "#556677",
    "VIZ_LIST_SURFACE": "#0a0a18",
    "VIZ_LIST_BORDER": "#1a2a4a",
    "VIZ_LIST_TEXT": "#aaccff",
    "VIZ_INPUT_SURFACE": "#142244",
    "VIZ_INPUT_BORDER": "#2244aa",
    "VIZ_GO_HOVER": "#001a0a",
    "VIZ_GO_HOVER_DEEP": "#00290f",
    "VIZ_STOP_HOVER": "#1a0011",
    "VIZ_STOP_HOVER_DEEP": "#2a0018",
    "VIZ_SIM_HOVER": "#001a18",
    "VIZ_GOLD_HOVER": "#1a1400",
    "VIZ_CONFIRM_SURFACE": "#003822",
    "VIZ_NUCLEAR_SURFACE": "#ff0000",
    "VIZ_NUCLEAR_BORDER": "#cc0000",
    "VIZ_LANE_LIVE": "#091a0e",
    "VIZ_LANE_PAPER": "#0e0e09",
    "MAIN_TOOLBAR_SURFACE": "#14141e",
    "MAIN_SEPARATOR": "#2a2a3a",
    "MAIN_BUTTON_SURFACE": "#1a1a26",
    "MAIN_BUTTON_BORDER": "#3a3a4a",
    "MAIN_BUTTON_HOVER": "#22222e",
    "MAIN_TOGGLE_SURFACE": "#1a1a3a",
    "MAIN_TOGGLE_HOVER": "#222250",
    "MAIN_TOGGLE_CHECKED": "#3a1a1a",
    "MAIN_TOGGLE_CHECKED_AMBER": "#663300",
    "MAIN_TOOLTIP_BORDER": "#00cccc",
    "MAIN_TABLE_HEADER": "#c0c4d8",
    "MAIN_CAPTION": "#7a7d99",
    "MAIN_BADGE_TEXT": "#7fb3ff",
    "MAIN_BADGE_MAGENTA": "#ff66dd",
    "MAIN_ALERT_SURFACE": "#d61a3d",
    "MAIN_HIGHLIGHT_AMBER": "#33220a",
    "MAIN_HIGHLIGHT_AMBER_TEXT": "#ffb000",
    "MAIN_LOG_NAME": "#88c0ff",
    "MAIN_LOG_SITE": "#667788",
    "MAIN_LOG_CRITICAL": "#ff0044",
    "CARD_STOCK_PANEL": "#0a1020",
    "CARD_STOCK_BODY": "#aabbcc",
    "CARD_STOCK_LOG_SURFACE": "#080c18",
    "CARD_STOCK_BUTTON_BORDER": "#2a3a5f",
    "CARD_STOCK_BUTTON_HOVER": "#2a3a6f",
    "STOCK_POSITIVE": "#00cc66",
    "STOCK_NEGATIVE": "#ff4466",
    "STOCK_WARNING": "#ddaa00",
    "STOCK_BUTTON_HOVER": "#0088dd",
    "STOCK_LOG_DEBUG": "#444455",
    "STOCK_LOG_TIMESTAMP": "#555566",
    "STOCK_LOG_CRITICAL": "#ff0033",
    "TYPE_DISPLAY": 36,
    "TYPE_H1": 28,
    "TYPE_H2": 22,
    "TYPE_H3": 18,
    "TYPE_H4": 15,
    "TYPE_BODY": 13,
    "TYPE_SMALL": 11,
    "TYPE_CAPTION": 10,
    "TYPE_CARD_VALUE": 16,
    "LINE_HEIGHT_TIGHT": 1.2,
    "LINE_HEIGHT_BODY": 1.4,
    "LINE_HEIGHT_LOOSE": 1.5,
    "FONT_FAMILY_UI": "'Rajdhani', 'Orbitron', 'Segoe UI', sans-serif",
    "FONT_FAMILY_MONO": "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
    "WEIGHT_REGULAR": 400,
    "WEIGHT_MEDIUM": 500,
    "WEIGHT_BOLD": 700,
    "SPACE_XS": 4,
    "SPACE_XXS": 2,
    "SPACE_CARD_TIGHT": 10,
    "SPACE_CARD_PAD": 12,
    "SPACE_S": 8,
    "SPACE_M": 16,
    "SPACE_L": 24,
    "SPACE_XL": 32,
    "SPACE_XXL": 48,
    "RADIUS_NONE": 0,
    "RADIUS_XS": 4,
    "RADIUS_CARD": 6,
    "RADIUS_SM": 8,
    "RADIUS_MD": 12,
    "RADIUS_LG": 16,
    "RADIUS_FULL": 9999,
    "MOTION_INSTANT": 0,
    "MOTION_SHORT": 100,
    "MOTION_MEDIUM": 250,
    "MOTION_LONG": 500,
    "MOTION_EXTRA": 1000,
    "TARGET_MIN": 24,
    "TARGET_COMFORTABLE": 32,
    "TARGET_LARGE": 44,
    "TABLE_COL_FIRE_W": 70,
    "TABLE_COL_DETAIL_W": 60,
    "FOCUS_RING_WIDTH": 2,
    "FOCUS_RING_OFFSET": 2,
    "FOCUS_RING_COLOR": "#a0a0c0",
    "SHADOW_0": (0, 0, "00"),
    "SHADOW_1": (1, 2, "40"),
    "SHADOW_2": (2, 4, "50"),
    "SHADOW_3": (4, 8, "60"),
    "SHADOW_4": (8, 16, "70"),
    "BG": "#0a0a0f",
    "CARD": "#141420",
    "FG": "#e0e0f0",
    "DIM": "#a8a8c5",
    "HINT": "#8a8ab0",
}

# The group each token belongs to, typed out here so a token moved
# from one group to another on one side alone is reported.
EXPECTED_COLOR_NAMES = (
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

EXPECTED_TYPE_NAMES = (
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

EXPECTED_LINE_HEIGHT_NAMES = (
    "LINE_HEIGHT_TIGHT",
    "LINE_HEIGHT_BODY",
    "LINE_HEIGHT_LOOSE",
)

EXPECTED_FONT_FAMILY_NAMES = (
    "FONT_FAMILY_UI",
    "FONT_FAMILY_MONO",
)

EXPECTED_WEIGHT_NAMES = (
    "WEIGHT_REGULAR",
    "WEIGHT_MEDIUM",
    "WEIGHT_BOLD",
)

EXPECTED_SPACE_NAMES = (
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

EXPECTED_RADIUS_NAMES = (
    "RADIUS_NONE",
    "RADIUS_XS",
    "RADIUS_CARD",
    "RADIUS_SM",
    "RADIUS_MD",
    "RADIUS_LG",
    "RADIUS_FULL",
)

EXPECTED_MOTION_NAMES = (
    "MOTION_INSTANT",
    "MOTION_SHORT",
    "MOTION_MEDIUM",
    "MOTION_LONG",
    "MOTION_EXTRA",
)

EXPECTED_TARGET_NAMES = (
    "TARGET_MIN",
    "TARGET_COMFORTABLE",
    "TARGET_LARGE",
)

EXPECTED_TABLE_COLUMN_NAMES = (
    "TABLE_COL_FIRE_W",
    "TABLE_COL_DETAIL_W",
)

EXPECTED_FOCUS_NAMES = (
    "FOCUS_RING_WIDTH",
    "FOCUS_RING_OFFSET",
)

EXPECTED_SHADOW_NAMES = (
    "SHADOW_0",
    "SHADOW_1",
    "SHADOW_2",
    "SHADOW_3",
    "SHADOW_4",
)

EXPECTED_ALIAS_NAMES = (
    "BG",
    "CARD",
    "FG",
    "DIM",
    "HINT",
    "FOCUS_RING_COLOR",
)

EXPECTED_ORDER = (
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

EXPECTED_ALIAS_TARGETS = {
    "BG": "SURFACE_0",
    "CARD": "SURFACE_1",
    "FG": "TEXT_HIGH",
    "DIM": "TEXT_MED",
    "HINT": "TEXT_LOW",
    "FOCUS_RING_COLOR": "OUTLINE_STRONG",
}

EXPECTED_GROUP_MEMBERS = {
    "colors": EXPECTED_COLOR_NAMES,
    "type_scale": EXPECTED_TYPE_NAMES,
    "line_heights": EXPECTED_LINE_HEIGHT_NAMES,
    "font_families": EXPECTED_FONT_FAMILY_NAMES,
    "weights": EXPECTED_WEIGHT_NAMES,
    "spacing": EXPECTED_SPACE_NAMES,
    "radii": EXPECTED_RADIUS_NAMES,
    "motion_ms": EXPECTED_MOTION_NAMES,
    "target_sizes": EXPECTED_TARGET_NAMES,
    "table_columns": EXPECTED_TABLE_COLUMN_NAMES,
    "focus": EXPECTED_FOCUS_NAMES,
    "shadows": EXPECTED_SHADOW_NAMES,
    "aliases": EXPECTED_ALIAS_NAMES,
}


# The shipped module defines no function and no class, so nothing here
# has a counterpart upstream. These seven carry the view model the
# renderer reads and are named so one added or lost is reported.
SURFACE_ONLY = (
    "token",
    "has_token",
    "group_tokens",
    "alias_target",
    "requested_names",
    "build_view_model",
    "view_model",
)

# Every token is compared as a value on both sides, so no list decides
# which of them a render is asked to report.


# The awkward names a caller may ask for. None is a token.
UNKNOWN_NAMES = {
    "empty": "",
    "zero": "0",
    "negative": "-1",
    "very_large": "9" * 40,
    "unicode": "Δ→⚡",
    "long": "X" * 200,
    "markup": "<b>PRIMARY</b>",
    "lowercase": "primary",
    "spaced": " PRIMARY ",
    "dotted": "colors.PRIMARY",
    "private": "_TOKENS",
    "dunder": "__all__",
    "annotations": "annotations",
    "quoted": '"PRIMARY"',
    "newline": "PRIMARY\nSUCCESS",
}

# The defaults a caller may hand `token`, each a different shape.
DEFAULT_VALUES = ("", 0, -1, 9.5, "Δ→⚡", "X" * 200, "<b>x</b>", None)

SAMPLE_TEXT = "Ag8"
SWATCH = 22
COLUMNS = 34
SHADOW_HOSTS = ("SHADOW_0", "SHADOW_1", "SHADOW_2", "SHADOW_3", "SHADOW_4")

TYPE_TRIPLES = (
    ("TYPE_DISPLAY", "TEXT_HIGH", "WEIGHT_BOLD"),
    ("TYPE_H1", "TEXT_MED", "WEIGHT_MEDIUM"),
    ("TYPE_H2", "TEXT_LOW", "WEIGHT_REGULAR"),
    ("TYPE_H3", "PRIMARY", "WEIGHT_BOLD"),
    ("TYPE_H4", "SECONDARY", "WEIGHT_MEDIUM"),
    ("TYPE_BODY", "SUCCESS", "WEIGHT_REGULAR"),
    ("TYPE_SMALL", "DANGER", "WEIGHT_BOLD"),
    ("TYPE_CAPTION", "WARNING", "WEIGHT_MEDIUM"),
    ("TYPE_CARD_VALUE", "INFO", "WEIGHT_REGULAR"),
)
SHAPE_TRIPLES = (
    ("TABLE_COL_FIRE_W", "RADIUS_NONE", "CARD_STOCK_SURFACE"),
    ("TABLE_COL_DETAIL_W", "RADIUS_CARD", "CARD_METRIC_SURFACE"),
    ("TARGET_MIN", "RADIUS_SM", "MENU_SURFACE"),
    ("TARGET_COMFORTABLE", "RADIUS_MD", "STATE_ARMED"),
    ("TARGET_LARGE", "RADIUS_LG", "VIZ_PANEL_SURFACE"),
    ("SPACE_XXL", "RADIUS_FULL", "MAIN_ALERT_SURFACE"),
    ("SPACE_XL", "RADIUS_XS", "VIZ_CONFIRM_SURFACE"),
)

SWATCH_ORDER = EXPECTED_COLOR_NAMES + EXPECTED_ALIAS_NAMES


# ---------------------------------------------------------------------
# The two token tables, and the panel painted from one of them
# ---------------------------------------------------------------------


def shipped_tokens():
    """Every token the shipped module exports, by name, stamped."""
    return sealed({name: getattr(shipped, name) for name in shipped.__all__})


def surface_tokens():
    """Every token the surface exports, by name, stamped."""
    return sealed({name: surface.token(name) for name in surface.TOKEN_NAMES})


def app():
    """The process application object every render needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def _shadowed(frame, setting, tint):
    """Hang one drop shadow on `frame` from a shadow token's three parts."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QGraphicsDropShadowEffect

    offset_y, blur, alpha_hex = setting
    effect = QGraphicsDropShadowEffect(frame)
    effect.setOffset(0, offset_y)
    effect.setBlurRadius(blur)
    effect.setColor(QColor("#" + alpha_hex + tint.lstrip("#")[:6]))
    frame.setGraphicsEffect(effect)


def build_panel(values):
    """One panel painted from a token table, and from nothing else.

    A swatch carries every colour, a label carries every type size,
    weight and family, a block carries every radius and target width,
    and a drop shadow carries every shadow setting. `values` is the only
    source, so the same call on the two sides is the parity comparison.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QVBoxLayout,
        QWidget,
    )

    unaltered(values)
    app()
    root = QWidget()
    root.setStyleSheet("QWidget { background: %s; }" % values["SURFACE_0"])
    outer = QVBoxLayout(root)
    outer.setContentsMargins(
        values["SPACE_S"],
        values["SPACE_S"],
        values["SPACE_S"],
        values["SPACE_S"],
    )
    outer.setSpacing(values["SPACE_XS"])

    grid = QGridLayout()
    grid.setSpacing(values["SPACE_XXS"])
    for index, name in enumerate(SWATCH_ORDER):
        cell = QFrame()
        cell.setFixedSize(SWATCH, SWATCH)
        cell.setStyleSheet(
            "QFrame { background: %s; border: %dpx solid %s; "
            "border-radius: %dpx; }"
            % (
                values[name],
                values["FOCUS_RING_WIDTH"],
                values["OUTLINE"],
                values["RADIUS_XS"],
            )
        )
        grid.addWidget(cell, index // COLUMNS, index % COLUMNS)
    outer.addLayout(grid)

    type_row = QHBoxLayout()
    type_row.setSpacing(values["SPACE_XS"])
    for size_name, color_name, weight_name in TYPE_TRIPLES:
        label = QLabel(SAMPLE_TEXT)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            "QLabel { font-size: %dpx; color: %s; font-weight: %d; "
            "font-family: %s; background: %s; padding: %dpx %dpx; }"
            % (
                values[size_name],
                values[color_name],
                values[weight_name],
                values["FONT_FAMILY_UI"],
                values["SURFACE_1"],
                values["SPACE_CARD_TIGHT"],
                values["SPACE_CARD_PAD"],
            )
        )
        type_row.addWidget(label)
    type_row.addSpacing(values["SPACE_L"])
    outer.addLayout(type_row)

    shape_row = QHBoxLayout()
    shape_row.setSpacing(values["SPACE_M"])
    for width_name, radius_name, fill_name in SHAPE_TRIPLES:
        block = QFrame()
        block.setFixedSize(values[width_name], values["TARGET_COMFORTABLE"])
        block.setStyleSheet(
            "QFrame { background: %s; border-radius: %dpx; "
            "border: %dpx solid %s; }"
            % (
                values[fill_name],
                values[radius_name],
                values["FOCUS_RING_OFFSET"],
                values["OUTLINE_STRONG"],
            )
        )
        shape_row.addWidget(block)
    shape_row.addStretch(1)
    outer.addLayout(shape_row)

    shadow_row = QHBoxLayout()
    shadow_row.setSpacing(values["SPACE_XL"])
    shadow_row.setContentsMargins(
        values["SPACE_M"],
        values["SPACE_XS"],
        values["SPACE_M"],
        values["SPACE_XS"],
    )
    for name in SHADOW_HOSTS:
        block = QFrame()
        block.setFixedSize(values["TARGET_LARGE"], values["TARGET_COMFORTABLE"])
        block.setStyleSheet(
            "QFrame { background: %s; border-radius: %dpx; }"
            % (values["CARD_STOCK_VALUE"], values["RADIUS_SM"])
        )
        _shadowed(block, values[name], values["PRIMARY"])
        shadow_row.addWidget(block)
    shadow_row.addStretch(1)
    outer.addLayout(shadow_row)

    mono = QLabel(SAMPLE_TEXT)
    mono.setStyleSheet(
        "QLabel { font-family: %s; font-size: %dpx; color: %s; background: %s; }"
        % (
            values["FONT_FAMILY_MONO"],
            values["TYPE_BODY"],
            values["TEXT_CONSOLE"],
            values["SURFACE_CONSOLE"],
        )
    )
    mono.setFixedHeight(values["TARGET_LARGE"])
    outer.addWidget(mono)
    return root


def altered(name, value):
    """One token changed, to blind the value comparison in the test below.

    The returned value keeps the type of the one it replaces, so the
    comparison it blinds fails on the value and not on the type.
    """
    if isinstance(value, tuple):
        return (value[0] + 3, value[1] + 3, "ff")
    if isinstance(value, str) and value.startswith("#"):
        return "#ff00aa" if value.lower() != "#ff00aa" else "#00ff88"
    if isinstance(value, str):
        return "'Courier New'"
    if isinstance(value, float):
        return value + 0.5
    if name in EXPECTED_RADIUS_NAMES:
        return 3 if value != 3 else 5
    if name in EXPECTED_SPACE_NAMES:
        return value + 5
    if name in EXPECTED_WEIGHT_NAMES:
        return 400 if value != 400 else 700
    if name in EXPECTED_MOTION_NAMES:
        return value + 777
    return value + 17


def digest(payload):
    """A stable hash over one side's whole answer."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=list).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------
# The two sides, value for value
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", shipped.__all__)
def test_every_shipped_token_is_the_surfaces_own(name):
    """A token the shipped module exports carries a different value."""
    old = getattr(shipped, name)
    new = surface.token(name)
    assert new == old, f"{name}: shipped {old!r}, surface {new!r}"
    assert type(new) is type(old), f"{name}: shipped {type(old)}, new {type(new)}"


@pytest.mark.parametrize("name", surface.TOKEN_NAMES)
def test_every_surface_token_is_the_shipped_modules_own(name):
    """A token the surface exports is absent or different upstream."""
    assert hasattr(shipped, name), f"the surface invented {name}"
    assert surface.token(name) == getattr(shipped, name), name


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_token_matches_the_value_typed_here(name):
    """Both sides moved together away from the value written in this file."""
    assert getattr(shipped, name) == EXPECTED[name], name
    assert surface.token(name) == EXPECTED[name], name


def test_a_token_changed_on_one_side_alone_is_reported():
    """The value comparison passed because it read one side twice."""
    old = shipped_tokens()
    new = surface_tokens()
    assert old == new
    for name in ("PRIMARY", "TYPE_BODY", "LINE_HEIGHT_BODY", "SHADOW_2", "BG"):
        blinded = dict(new)
        blinded[name] = altered(name, blinded[name])
        assert blinded != old, name
        assert blinded[name] != old[name], name
    assert dict(new, PRIMARY="#00ffcc") == old


def test_the_two_sides_hash_the_same():
    """The whole table differs between the two sides."""
    old = digest(shipped_tokens())
    new = digest(surface_tokens())
    assert new == old, f"shipped {old}, surface {new}"


def test_the_sample_hashes_are_reported():
    """A hash that names no side is a hash of nothing."""
    old = shipped_tokens()
    new = surface_tokens()
    samples = {
        "whole_table": (old, new),
        "colors": (
            {n: old[n] for n in EXPECTED_COLOR_NAMES},
            {n: new[n] for n in EXPECTED_COLOR_NAMES},
        ),
        "numbers": (
            {n: v for n, v in old.items() if isinstance(v, (int, float))},
            {n: v for n, v in new.items() if isinstance(v, (int, float))},
        ),
        "shadows": (
            {n: old[n] for n in EXPECTED_SHADOW_NAMES},
            {n: new[n] for n in EXPECTED_SHADOW_NAMES},
        ),
        "aliases": (
            {n: old[n] for n in EXPECTED_ALIAS_NAMES},
            {n: new[n] for n in EXPECTED_ALIAS_NAMES},
        ),
    }
    reported = {}
    for label, (old_side, new_side) in samples.items():
        old_hash = digest(old_side)
        new_hash = digest(new_side)
        assert new_hash == old_hash, f"{label}: shipped {old_hash}, new {new_hash}"
        reported[label] = old_hash
    assert len(set(reported.values())) == len(reported), reported
    print(json.dumps(reported, indent=1))


def test_the_hash_can_report_a_difference():
    """The hash returns one value whatever it is given."""
    old = shipped_tokens()
    changed = dict(old)
    changed["PRIMARY"] = "#00ffcd"
    assert digest(changed) != digest(old)
    assert digest(old) == digest(dict(old))


# ---------------------------------------------------------------------
# The names, their order and their count
# ---------------------------------------------------------------------


def test_the_token_names_are_the_shipped_modules_export_list():
    """A name was added, lost or moved on one side alone."""
    assert list(surface.TOKEN_NAMES) == list(shipped.__all__)
    assert list(surface.TOKEN_NAMES) == list(EXPECTED_ORDER)
    assert len(surface.TOKEN_NAMES) == TOKEN_TOTAL
    assert len(set(surface.TOKEN_NAMES)) == TOKEN_TOTAL
    assert len(set(shipped.__all__)) == len(shipped.__all__)


def test_the_export_list_holds_every_name_the_shipped_module_defines():
    """A token the shipped module defines never reaches the surface."""
    public = {name for name in vars(shipped) if not name.startswith("_")}
    assert public - {"annotations"} == set(shipped.__all__)
    assert set(surface.TOKEN_NAMES) == set(shipped.__all__)


def test_a_name_added_or_lost_on_either_side_is_reported():
    """The name check passed because it compared a list to itself."""
    names = list(surface.TOKEN_NAMES)
    assert names[:-1] != list(shipped.__all__)
    assert names + ["EXTRA"] != list(shipped.__all__)
    assert list(reversed(names)) != list(shipped.__all__)
    assert "SURFACE_0" in names and "NO_SUCH_NAME" not in names
    assert surface.token("NO_SUCH_NAME") is None


def test_the_token_table_matches_the_name_list():
    """The table and the ordered name list drifted apart."""
    assert list(surface.TOKENS) == list(surface.TOKEN_NAMES)
    assert len(surface.TOKENS) == TOKEN_TOTAL
    assert surface.TOKENS == shipped_tokens()


# ---------------------------------------------------------------------
# The type each value carries
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", shipped.__all__)
def test_every_token_keeps_the_shipped_modules_type(name):
    """A whole number arrived as text, or text as a number."""
    assert type(surface.token(name)) is type(getattr(shipped, name)), name


def test_the_type_counts_are_the_shipped_modules_own():
    """The table gained or lost a value of one kind."""
    counts = {"str": 0, "int": 0, "float": 0, "tuple": 0}
    for name in surface.TOKEN_NAMES:
        counts[type(surface.token(name)).__name__] += 1
    assert counts == {"str": 147, "int": 40, "float": 3, "tuple": 5}
    assert sum(counts.values()) == TOKEN_TOTAL
    old = {"str": 0, "int": 0, "float": 0, "tuple": 0}
    for name in shipped.__all__:
        old[type(getattr(shipped, name)).__name__] += 1
    assert counts == old


def rgba_channels(value):
    """The four numbers of an `rgba(r, g, b, a)` value, or None."""
    if not value.startswith("rgba(") or not value.endswith(")"):
        return None
    fields = value[len("rgba(") : -1].split(",")
    if len(fields) != 4:
        return None
    return [int(one) for one in fields]


def test_every_colour_is_an_opaque_hash_or_an_rgba_and_every_size_is_whole():
    """A colour lost its hash, took eight digits, or a size gained a fraction."""
    for name in EXPECTED_COLOR_NAMES + EXPECTED_ALIAS_NAMES:
        value = surface.token(name)
        assert isinstance(value, str), (name, value)
        assert value == value.lower(), (name, value)
        if value.startswith("#"):
            assert len(value) in (4, 7), (name, value)
            assert all(one in "0123456789abcdef" for one in value[1:]), (name, value)
            continue
        channels = rgba_channels(value)
        assert channels is not None, (name, value)
        assert all(0 <= one <= 255 for one in channels), (name, value)
    for group in (
        EXPECTED_TYPE_NAMES,
        EXPECTED_WEIGHT_NAMES,
        EXPECTED_SPACE_NAMES,
        EXPECTED_RADIUS_NAMES,
        EXPECTED_MOTION_NAMES,
        EXPECTED_TARGET_NAMES,
        EXPECTED_TABLE_COLUMN_NAMES,
        EXPECTED_FOCUS_NAMES,
    ):
        for name in group:
            value = surface.token(name)
            assert isinstance(value, int) and not isinstance(value, bool), name
            assert value >= 0, (name, value)


def test_every_shadow_carries_an_offset_a_blur_and_an_alpha():
    """A shadow setting lost one of its three parts."""
    for name in EXPECTED_SHADOW_NAMES:
        setting = surface.token(name)
        assert isinstance(setting, tuple) and len(setting) == 3, (name, setting)
        offset_y, blur, alpha_hex = setting
        assert isinstance(offset_y, int) and offset_y >= 0, name
        assert isinstance(blur, int) and blur >= 0, name
        assert isinstance(alpha_hex, str) and len(alpha_hex) == 2, name
        assert int(alpha_hex, 16) >= 0, name
        assert setting == getattr(shipped, name), name


def test_every_line_height_is_a_fraction_above_one():
    """A line height stopped being a multiple of the type size."""
    for name in EXPECTED_LINE_HEIGHT_NAMES:
        value = surface.token(name)
        assert isinstance(value, float), name
        assert 1.0 < value < 3.0, (name, value)
        assert value == getattr(shipped, name), name


def test_every_font_family_names_a_stack_the_shipped_module_ships():
    """A font stack lost a family or changed its order."""
    for name in EXPECTED_FONT_FAMILY_NAMES:
        value = surface.token(name)
        assert isinstance(value, str), name
        assert not value.startswith("#"), name
        assert value == getattr(shipped, name), name
        assert value == EXPECTED[name], name
    assert surface.FONT_FAMILY_UI.count(",") == 3
    assert surface.FONT_FAMILY_MONO.count(",") == 3


# ---------------------------------------------------------------------
# The groups
# ---------------------------------------------------------------------


@pytest.mark.parametrize("group", sorted(EXPECTED_GROUP_MEMBERS))
def test_every_group_holds_the_names_typed_here(group):
    """A token moved from one group to another."""
    assert list(surface.GROUP_MEMBERS[group]) == list(EXPECTED_GROUP_MEMBERS[group])
    holding = surface.group_tokens(group)
    assert list(holding) == list(EXPECTED_GROUP_MEMBERS[group])
    for name in holding:
        assert holding[name] == getattr(shipped, name), (group, name)


def test_the_groups_cover_every_token_exactly_once():
    """A token belongs to two groups, or to none."""
    seen = []
    for names in surface.GROUP_MEMBERS.values():
        seen.extend(names)
    assert sorted(seen) == sorted(surface.TOKEN_NAMES)
    assert len(seen) == TOKEN_TOTAL
    assert len(set(seen)) == TOKEN_TOTAL
    assert len(surface.GROUP_NAMES) == GROUP_TOTAL
    assert list(surface.GROUP_NAMES) == list(EXPECTED_GROUP_MEMBERS)


def test_the_group_sizes_are_what_the_table_claims():
    """A group gained or lost a member."""
    sizes = {group: len(names) for group, names in surface.GROUP_MEMBERS.items()}
    assert sizes == {
        "colors": COLOR_TOTAL,
        "type_scale": 9,
        "line_heights": 3,
        "font_families": 2,
        "weights": 3,
        "spacing": 9,
        "radii": 7,
        "motion_ms": 5,
        "target_sizes": 3,
        "table_columns": 2,
        "focus": 2,
        "shadows": 5,
        "aliases": ALIAS_TOTAL,
    }
    assert sum(sizes.values()) == TOKEN_TOTAL


def test_a_token_moved_between_groups_is_reported():
    """The group check passed because it read one side twice."""
    moved = dict(EXPECTED_GROUP_MEMBERS)
    moved["radii"] = EXPECTED_RADIUS_NAMES + ("SPACE_S",)
    assert list(moved["radii"]) != list(surface.GROUP_MEMBERS["radii"])
    assert "SPACE_S" in surface.GROUP_MEMBERS["spacing"]
    assert "SPACE_S" not in surface.GROUP_MEMBERS["radii"]
    assert surface.group_tokens("radii") != surface.group_tokens("spacing")


def test_the_named_group_tables_are_the_group_map():
    """A group table and the group map drifted apart."""
    for group, table in (
        ("colors", surface.COLORS),
        ("type_scale", surface.TYPE_SCALE),
        ("line_heights", surface.LINE_HEIGHTS),
        ("font_families", surface.FONT_FAMILIES),
        ("weights", surface.WEIGHTS),
        ("spacing", surface.SPACING),
        ("radii", surface.RADII),
        ("motion_ms", surface.MOTION_MS),
        ("target_sizes", surface.TARGET_SIZES),
        ("table_columns", surface.TABLE_COLUMNS),
        ("focus", surface.FOCUS),
        ("shadows", surface.SHADOWS),
        ("aliases", surface.ALIASES),
    ):
        assert table == {n: getattr(shipped, n) for n in EXPECTED_GROUP_MEMBERS[group]}


# ---------------------------------------------------------------------
# The six second names
# ---------------------------------------------------------------------


def test_every_second_name_carries_the_value_of_the_token_it_copies():
    """A second name stopped tracking the token it stands for."""
    assert surface.ALIAS_TARGETS == EXPECTED_ALIAS_TARGETS
    assert len(surface.ALIAS_TARGETS) == ALIAS_TOTAL
    for name, target in EXPECTED_ALIAS_TARGETS.items():
        assert getattr(shipped, name) == getattr(shipped, target), name
        assert surface.token(name) == getattr(shipped, target), name
        assert surface.alias_target(name) == target, name


def test_a_second_name_pointed_at_the_wrong_token_is_reported():
    """The second-name check passed because both sides moved together."""
    for name, target in EXPECTED_ALIAS_TARGETS.items():
        wrong = [
            other
            for other in EXPECTED_COLOR_NAMES
            if getattr(shipped, other) != getattr(shipped, target)
        ][0]
        assert surface.token(name) != getattr(shipped, wrong), (name, wrong)
    assert surface.alias_target("SURFACE_0") == ""
    assert surface.alias_target("BG") == "SURFACE_0"


def test_the_six_second_names_are_the_only_repeated_colour_values():
    """A colour value repeated where the table says every name is distinct."""
    repeated = {}
    for name in EXPECTED_COLOR_NAMES + EXPECTED_ALIAS_NAMES:
        repeated.setdefault(surface.token(name), []).append(name)
    shared = {v: n for v, n in repeated.items() if len(n) > 1}
    assert len(shared) == ALIAS_TOTAL, shared
    for names in shared.values():
        assert len(names) == 2, names
        assert names[1] in EXPECTED_ALIAS_TARGETS, names
        assert EXPECTED_ALIAS_TARGETS[names[1]] == names[0], names


# ---------------------------------------------------------------------
# What the five helpers return
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", shipped.__all__)
def test_token_returns_the_shipped_value_for_every_name(name):
    """A lookup by name returned something other than the token."""
    assert surface.token(name) == getattr(shipped, name)
    assert surface.has_token(name) is True


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_token_returns_the_default_for_a_name_the_table_does_not_hold(case):
    """A name the table does not hold came back as a value."""
    asked = UNKNOWN_NAMES[case]
    assert asked not in shipped.__all__, asked
    assert surface.has_token(asked) is False, asked
    assert surface.token(asked) is None, asked
    for default in DEFAULT_VALUES:
        assert surface.token(asked, default) == default, (asked, default)
    assert surface.token(asked, "#00ffcc") == "#00ffcc"


def test_token_ignores_a_default_for_a_name_the_table_does_hold():
    """A default replaced a token the table holds."""
    for default in DEFAULT_VALUES:
        assert surface.token("PRIMARY", default) == shipped.PRIMARY
        assert surface.token("SHADOW_0", default) == shipped.SHADOW_0
    assert surface.token("PRIMARY") == "#00ffcc"


def test_has_token_answers_both_ways():
    """The membership answer is the same whatever it is asked."""
    assert surface.has_token("PRIMARY") is True
    assert surface.has_token("BG") is True
    assert surface.has_token("") is False
    assert surface.has_token("primary") is False
    assert surface.has_token("annotations") is False
    assert [surface.has_token(n) for n in shipped.__all__] == [True] * TOKEN_TOTAL
    assert any(not surface.has_token(n) for n in UNKNOWN_NAMES.values())


@pytest.mark.parametrize("group", sorted(EXPECTED_GROUP_MEMBERS))
def test_group_tokens_returns_the_whole_group(group):
    """A group lookup returned a different set of tokens."""
    holding = surface.group_tokens(group)
    assert holding == {
        name: getattr(shipped, name) for name in EXPECTED_GROUP_MEMBERS[group]
    }


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_group_tokens_returns_an_empty_table_for_any_other_name(case):
    """A group that does not exist came back holding tokens."""
    assert surface.group_tokens(UNKNOWN_NAMES[case]) == {}
    assert surface.group_tokens("colors") != {}


def test_group_tokens_hands_back_a_copy():
    """A caller edited the token table through the value it was given."""
    holding = surface.group_tokens("radii")
    holding["RADIUS_SM"] = 999
    holding["INVENTED"] = 1
    assert surface.token("RADIUS_SM") == shipped.RADIUS_SM
    assert surface.group_tokens("radii") == {
        name: getattr(shipped, name) for name in EXPECTED_RADIUS_NAMES
    }
    empty = surface.group_tokens("no_such_group")
    empty["X"] = 1
    assert surface.group_tokens("no_such_group") == {}


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_alias_target_names_nothing_for_a_name_that_is_not_a_second_name(case):
    """A name that copies nothing was reported as copying something."""
    assert surface.alias_target(UNKNOWN_NAMES[case]) == ""
    assert surface.alias_target("PRIMARY") == ""
    assert surface.alias_target("FG") == "TEXT_HIGH"


def test_requested_names_reads_a_list_and_refuses_anything_else():
    """A caller sending one word asked for the letters of that word."""
    assert surface.requested_names(["PRIMARY", "BG"]) == ["PRIMARY", "BG"]
    assert surface.requested_names(("PRIMARY",)) == ["PRIMARY"]
    assert surface.requested_names([]) == []
    assert surface.requested_names(()) == []
    assert surface.requested_names("PRIMARY") == []
    assert surface.requested_names(None) == []
    assert surface.requested_names(0) == []
    assert surface.requested_names(-1) == []
    assert surface.requested_names(9.5) == []
    assert surface.requested_names({"PRIMARY": 1}) == []
    assert surface.requested_names({"PRIMARY"}) == []
    assert surface.requested_names([1, 2]) == ["1", "2"]
    assert surface.requested_names(["Δ→⚡"]) == ["Δ→⚡"]
    assert surface.requested_names(["X" * 200]) == ["X" * 200]
    assert surface.requested_names(["<b>PRIMARY</b>"]) == ["<b>PRIMARY</b>"]


# ---------------------------------------------------------------------
# What the shipped module never had
# ---------------------------------------------------------------------


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    shipped_text = SHIPPED_PATH.read_text(encoding="utf-8")
    surface_text = SURFACE_PATH.read_text(encoding="utf-8")
    assert shipped_text.count(".connect(") == 0
    assert surface_text.count(".connect(") == 0
    assert surface.ACTIONS == {}
    assert len(surface.ACTIONS) == shipped_text.count(".connect(")
    assert len(surface.ACTIONS) == surface_text.count(".connect(")
    assert "import PySide6" not in shipped_text
    assert "from PySide6" not in shipped_text
    assert "import PySide6" not in surface_text
    assert "from PySide6" not in surface_text
    caller = CALLER_PATH.read_text(encoding="utf-8")
    assert caller.count(".connect(") > 0


def test_the_tokens_declare_no_action_no_timer_and_no_skin():
    """The table gained behaviour the module it replaces never had."""
    assert surface.ACTIONS == {}
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert surface.SKIN == {}
    assert surface.STYLE_SHEET == ""
    payload = surface.build_view_model()
    assert payload["actions"] == {}
    assert payload["timers"] == {}
    assert payload["timer_delays_ms"] == []
    assert payload["skin"] == {}
    assert payload["style_sheet"] == ""
    assert len(surface.ACTIONS) == len(surface.TIMERS) == 0


def test_the_shipped_module_defines_no_function_and_no_class():
    """A function grew on the shipped side with no counterpart here."""
    import inspect

    defined = {
        name
        for name, value in vars(shipped).items()
        if (inspect.isfunction(value) or inspect.isclass(value))
        and getattr(value, "__module__", "") == shipped.__name__
    }
    assert defined == set()
    assert len(defined) == 0
    assert set(SURFACE_ONLY) == {
        name
        for name, value in vars(surface).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == surface.__name__
    }
    assert len(SURFACE_ONLY) == 7


def test_the_function_counter_can_see_a_function():
    """The counter reported none because it can never report one."""
    import inspect

    from src.gui.main_tabs import table_cells_surface as neighbour

    defined = {
        name
        for name, value in vars(neighbour).items()
        if (inspect.isfunction(value) or inspect.isclass(value))
        and getattr(value, "__module__", "") == neighbour.__name__
    }
    assert len(defined) > 0, "the counter cannot see a function anywhere"
    assert "TableCellsModel" in defined
    assert "magnitude" in defined


@pytest.mark.parametrize("name", sorted(SURFACE_ONLY))
def test_every_surface_only_function_is_reachable_and_documented(name):
    """A named helper is missing, or carries no description."""
    found = getattr(surface, name)
    assert callable(found), name
    assert (found.__doc__ or "").strip(), name


def test_a_function_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "token" in SURFACE_ONLY
    assert "view_model" in SURFACE_ONLY
    assert not hasattr(shipped, "token")
    assert not hasattr(shipped, "view_model")
    assert not hasattr(shipped, "build_view_model")
    assert set(SURFACE_ONLY) - {"token"} != set(SURFACE_ONLY)
    with pytest.raises(AttributeError):
        surface.no_such_helper()


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    import ast

    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            else:
                imported.update(alias.name for alias in node.names)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    assert imported == {"__future__", "typing"}
    caller_tree = ast.parse(CALLER_PATH.read_text(encoding="utf-8"))
    caller_imports = {
        (node.module or "")
        for node in ast.walk(caller_tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in caller_imports), caller_imports


def test_the_surface_carries_its_own_copy_of_every_value(monkeypatch):
    """The surface read its values off the module it replaces.

    A surface that imported the shipped tokens would follow them, and
    the whole comparison above would be one side read twice. The shipped
    value is moved and the surface must not move with it.
    """
    for name, moved in (
        ("PRIMARY", "#123456"),
        ("TYPE_BODY", 99),
        ("SHADOW_1", (9, 9, "aa")),
        ("BG", "#654321"),
    ):
        was = getattr(shipped, name)
        monkeypatch.setattr(shipped, name, moved)
        assert getattr(shipped, name) == moved, name
        assert surface.token(name) == was, name
        assert surface.TOKENS[name] == was, name
        assert surface.build_view_model()["tokens"][name] == was, name
        monkeypatch.undo()
        assert getattr(shipped, name) == was, name


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------


def test_the_two_sides_paint_one_picture():
    """The surface painted a different panel than the shipped tokens."""
    app()
    assert_pictures_match(
        old_side=render_offscreen(build_panel(shipped_tokens()), PIXEL_SIZE),
        new_side=render_offscreen(build_panel(surface_tokens()), PIXEL_SIZE),
    )


LABEL_SIZE = (240, 70)


def build_sample_label(size_px, color):
    """One label painted from a type size and a colour, and nothing else."""
    from PySide6.QtWidgets import QLabel

    app()
    label = QLabel(SAMPLE_TEXT)
    label.setStyleSheet("QLabel { font-size: %dpx; color: %s; }" % (size_px, color))
    return label


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real type sizes and two real colours, one pair read from each
    side. A pass proves the comparison reports a label painted
    differently, so the match above is not green by being unable to
    fail.
    """
    app()
    assert shipped.TYPE_DISPLAY != surface.token("TYPE_CAPTION")
    assert shipped.TEXT_HIGH != surface.token("DANGER")
    assert_pictures_differ(
        old_side=render_offscreen(
            build_sample_label(shipped.TYPE_DISPLAY, shipped.TEXT_HIGH), LABEL_SIZE
        ),
        new_side=render_offscreen(
            build_sample_label(surface.token("TYPE_CAPTION"), surface.token("DANGER")),
            LABEL_SIZE,
        ),
        note="TYPE_DISPLAY from the shipped module against TYPE_CAPTION",
    )


def test_every_token_is_compared_as_a_value_on_both_sides():
    """A token reached no comparison, so nothing decided how it is checked."""
    assert sorted(shipped.__all__) == sorted(surface.TOKEN_NAMES)
    assert sorted(shipped.__all__) == sorted(EXPECTED)
    assert len(shipped.__all__) == TOKEN_TOTAL
    assert len(set(shipped.__all__)) == TOKEN_TOTAL
    for name in shipped.__all__:
        assert surface.token(name) == getattr(shipped, name), name
        assert surface.token(name) == EXPECTED[name], name


def label_style_sheets(panel):
    """The style sheet of every label the panel paints, in paint order."""
    from PySide6.QtWidgets import QLabel

    return [label.styleSheet() for label in panel.findChildren(QLabel)]


def test_the_card_padding_is_read_off_both_sides():
    """The card padding drifted between the shipped module and the surface.

    A font database absorbs the padding into the label box, so the
    render carries this proof on one host and not on the next. The
    number is read off the shipped module, off the surface, and off the
    style sheet each side paints its labels with.
    """
    app()
    assert surface.token("SPACE_CARD_PAD") == shipped.SPACE_CARD_PAD
    assert surface.token("SPACE_CARD_PAD") == EXPECTED["SPACE_CARD_PAD"] == 12
    assert surface.token("SPACE_CARD_TIGHT") == shipped.SPACE_CARD_TIGHT
    assert surface.token("SPACE_CARD_TIGHT") == EXPECTED["SPACE_CARD_TIGHT"] == 10
    assert shipped.SPACE_CARD_PAD != shipped.SPACE_CARD_TIGHT
    declared = "padding: %dpx %dpx" % (
        shipped.SPACE_CARD_TIGHT,
        shipped.SPACE_CARD_PAD,
    )
    old = label_style_sheets(build_panel(shipped_tokens()))
    new = label_style_sheets(build_panel(surface_tokens()))
    assert new == old, (old, new)
    assert sum(1 for sheet in new if declared in sheet) == len(TYPE_TRIPLES)


def test_the_font_weights_are_read_off_both_sides():
    """A font weight drifted between the shipped module and the surface.

    A weight moves a pixel only where a font database supplies a second
    face. All three are read off the shipped module, off the surface,
    and off the style sheet each side paints its labels with.
    """
    app()
    weights = ("WEIGHT_REGULAR", "WEIGHT_MEDIUM", "WEIGHT_BOLD")
    for name in weights:
        assert surface.token(name) == getattr(shipped, name), name
        assert surface.token(name) == EXPECTED[name], name
    assert len({getattr(shipped, name) for name in weights}) == 3
    old = label_style_sheets(build_panel(shipped_tokens()))
    new = label_style_sheets(build_panel(surface_tokens()))
    assert new == old, (old, new)
    painted = "".join(new)
    for _size_name, _color_name, weight_name in TYPE_TRIPLES:
        assert "font-weight: %d" % getattr(shipped, weight_name) in painted


def test_the_font_families_are_read_off_both_sides():
    """A font family drifted between the shipped module and the surface.

    A family reaches a glyph only where a font database supplies it.
    Both names are read off the shipped module, off the surface, and off
    the style sheet each side paints its labels with.
    """
    app()
    for name in ("FONT_FAMILY_UI", "FONT_FAMILY_MONO"):
        assert surface.token(name) == getattr(shipped, name), name
        assert surface.token(name) == EXPECTED[name], name
    assert shipped.FONT_FAMILY_UI != shipped.FONT_FAMILY_MONO
    old = label_style_sheets(build_panel(shipped_tokens()))
    new = label_style_sheets(build_panel(surface_tokens()))
    assert new == old, (old, new)
    painted = "".join(new)
    assert "font-family: %s" % shipped.FONT_FAMILY_UI in painted
    assert "font-family: %s" % shipped.FONT_FAMILY_MONO in painted


ALPHA_COLOR_NAMES = (
    "GLOW_PRIMARY",
    "GLOW_SECONDARY",
    "SCRIM",
    "GLOW_PRIMARY_EDGE",
    "GLOW_PRIMARY_FAINT",
)


def test_the_see_through_colours_are_compared_as_strings():
    """A see-through colour changed and no render could report it."""
    for name in ALPHA_COLOR_NAMES:
        old = getattr(shipped, name)
        new = surface.token(name)
        assert new == old, f"{name}: shipped {old!r}, surface {new!r}"
        assert new == EXPECTED[name], name
        assert new.startswith("rgba(") and new.endswith(")"), (name, new)
        assert len(new[len("rgba(") : -1].split(",")) == 4, (name, new)
    assert surface.token("GLOW_PRIMARY") == "rgba(0,255,204,51)"
    assert surface.token("GLOW_PRIMARY_EDGE") == "rgba(0,255,204,85)"
    assert surface.token("GLOW_PRIMARY_FAINT") == "rgba(0,255,204,34)"
    assert surface.token("GLOW_SECONDARY") == "rgba(255,0,170,51)"
    assert surface.token("SCRIM") == "rgba(0,0,0,136)"
    assert len({surface.token(n) for n in ALPHA_COLOR_NAMES}) == 5


def test_the_shorthand_colour_is_compared_as_a_string():
    """The three-digit colour was replaced by its six-digit twin.

    ``#888`` and ``#888888`` are one colour, so no render can tell them
    apart. The exact text is read off both sides instead.
    """
    assert surface.token("CARD_METRIC_LABEL") == shipped.CARD_METRIC_LABEL
    assert surface.token("CARD_METRIC_LABEL") == "#888"
    assert surface.token("CARD_METRIC_LABEL") != "#888888"
    assert len(surface.token("CARD_METRIC_LABEL")) == 4
    shorthand = [
        name
        for name in EXPECTED_COLOR_NAMES + EXPECTED_ALIAS_NAMES
        if len(surface.token(name)) == 4
    ]
    assert shorthand == ["CARD_METRIC_LABEL"], shorthand


def test_the_second_names_are_compared_as_strings():
    """A second name and its token were swapped and nothing painted differently.

    The two carry one value, so swapping them paints one picture. The
    map that says which name copies which is read off both sides.
    """
    for name, target in EXPECTED_ALIAS_TARGETS.items():
        assert surface.token(name) == surface.token(target)
        assert getattr(shipped, name) == getattr(shipped, target)
        assert surface.alias_target(name) == target
        assert surface.alias_target(target) == ""
    assert surface.ALIAS_TARGETS == EXPECTED_ALIAS_TARGETS
    assert sorted(surface.ALIAS_TARGETS) == sorted(EXPECTED_ALIAS_NAMES)


def test_the_numbers_two_tokens_share_are_compared_by_name():
    """Two tokens holding one number were swapped and nothing moved.

    Ten numbers are carried by more than one name. Swapping any pair
    paints one picture, so each name is read against the shipped value
    it must carry.
    """
    shared = {}
    for name in surface.TOKEN_NAMES:
        value = surface.token(name)
        if isinstance(value, int) and not isinstance(value, bool):
            shared.setdefault(value, []).append(name)
    repeated = {v: n for v, n in shared.items() if len(n) > 1}
    assert len(repeated) == 10, repeated
    for value, names in repeated.items():
        for name in names:
            assert getattr(shipped, name) == value, (name, value)
            assert surface.token(name) == value, (name, value)
    assert {"SPACE_S", "RADIUS_SM"} <= set(repeated[8])
    assert {"SPACE_L", "TARGET_MIN"} <= set(repeated[24])
    assert {"WEIGHT_MEDIUM", "MOTION_LONG"} <= set(repeated[500])


def test_the_grey_colours_are_compared_as_strings():
    """A colour whose channels match had two of them swapped."""
    equal_channel = []
    for name in EXPECTED_COLOR_NAMES + EXPECTED_ALIAS_NAMES:
        written = surface.token(name)
        if not written.startswith("#"):
            continue
        value = written.lstrip("#")
        if len(value) == 3:
            value = "".join(letter * 2 for letter in value)
        if len({value[0:2], value[2:4], value[4:6]}) < 3:
            equal_channel.append(name)
    assert len(equal_channel) == 59, len(equal_channel)
    for name in equal_channel:
        assert surface.token(name) == getattr(shipped, name), name
        assert surface.token(name) == EXPECTED[name], name
    assert "CARD_METRIC_LABEL" in equal_channel
    assert "TEXT_MAX" in equal_channel
    assert "PRIMARY" not in equal_channel


BLIND_TO_THE_PICTURE = {
    "font_family_ui": "test_the_font_families_are_read_off_both_sides",
    "font_family_mono": "test_the_font_families_are_read_off_both_sides",
    "line_heights": "test_every_line_height_is_a_fraction_above_one",
    "motion_durations": "test_every_token_is_compared_as_a_value_on_both_sides",
    "weight_medium": "test_the_font_weights_are_read_off_both_sides",
    "space_card_tight": "test_the_card_padding_is_read_off_both_sides",
    "weight_bold": "test_the_font_weights_are_read_off_both_sides",
    "weight_regular": "test_the_font_weights_are_read_off_both_sides",
    "space_card_pad": "test_the_card_padding_is_read_off_both_sides",
    "see_through_colours": "test_the_see_through_colours_are_compared_as_strings",
    "shorthand_colour": "test_the_shorthand_colour_is_compared_as_a_string",
    "second_names": "test_the_second_names_are_compared_as_strings",
    "shared_numbers": "test_the_numbers_two_tokens_share_are_compared_by_name",
    "equal_channel_colours": "test_the_grey_colours_are_compared_as_strings",
    "name_order": "test_the_token_names_are_the_shipped_modules_export_list",
    "group_membership": "test_every_group_holds_the_names_typed_here",
    "value_types": "test_every_token_keeps_the_shipped_modules_type",
    "shadow_alpha": "test_every_shadow_carries_an_offset_a_blur_and_an_alpha",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """Eighteen values never reach a pixel comparison, each named here with its check."""
    app()
    assert len(BLIND_TO_THE_PICTURE) == 18
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert_pictures_match(
        old_side=render_offscreen(build_panel(shipped_tokens()), PIXEL_SIZE),
        new_side=render_offscreen(build_panel(surface_tokens()), PIXEL_SIZE),
    )


def test_the_panel_paints_something_to_compare():
    """The two sides matched because the panel painted one flat colour."""
    app()
    image = render_offscreen(build_panel(shipped_tokens()), PIXEL_SIZE)
    assert image.width() == PIXEL_SIZE[0]
    assert image.height() == PIXEL_SIZE[1]
    from PySide6.QtGui import QColor

    seen = set()
    for x in range(0, image.width(), 7):
        for y in range(0, image.height(), 7):
            seen.add(QColor(image.pixelColor(x, y)).name())
    assert len(seen) > 1, "the panel painted one colour, so no defect could show"


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = surface.build_view_model(["PRIMARY", "NO_SUCH_NAME"], "radii")
    encoded = json.loads(json.dumps(payload))
    assert encoded["tokens"]["PRIMARY"] == "#00ffcc"
    assert encoded["tokens"]["SURFACE_0"] == "#0a0a0f"
    assert encoded["tokens"]["TYPE_BODY"] == 13
    assert encoded["tokens"]["LINE_HEIGHT_BODY"] == 1.4
    assert encoded["tokens"]["SHADOW_2"] == [2, 4, "50"]
    assert encoded["token_names"] == list(shipped.__all__)
    assert len(encoded["tokens"]) == TOKEN_TOTAL
    assert encoded["requested"] == {"PRIMARY": "#00ffcc", "NO_SUCH_NAME": None}
    assert encoded["unknown"] == ["NO_SUCH_NAME"]
    assert encoded["group"] == "radii"
    assert encoded["group_tokens"] == {
        name: getattr(shipped, name) for name in EXPECTED_RADIUS_NAMES
    }
    assert encoded["alias_targets"] == EXPECTED_ALIAS_TARGETS
    assert encoded["colors"]["SUCCESS"] == "#00ff88"
    assert encoded["type_scale"]["TYPE_H1"] == 28
    assert encoded["spacing"]["SPACE_M"] == 16
    assert encoded["motion_ms"]["MOTION_MEDIUM"] == 250
    assert encoded["target_sizes"]["TARGET_LARGE"] == 44
    assert encoded["table_columns"]["TABLE_COL_FIRE_W"] == 70
    assert encoded["focus"]["FOCUS_RING_WIDTH"] == 2
    assert encoded["font_families"]["FONT_FAMILY_MONO"] == shipped.FONT_FAMILY_MONO
    assert encoded["weights"]["WEIGHT_BOLD"] == 700
    assert encoded["aliases"]["BG"] == "#0a0a0f"
    assert encoded["shadows"]["SHADOW_4"] == [8, 16, "70"]
    assert encoded["group_names"] == list(EXPECTED_GROUP_MEMBERS)
    assert encoded["actions"] == {}
    assert encoded["timer_delays_ms"] == []
    assert encoded["skin"] == {}
    assert encoded["style_sheet"] == ""


def test_the_payload_carries_every_token_the_shipped_module_ships():
    """A token the shipped module ships never reaches the renderer."""
    payload = surface.build_view_model()
    assert payload["tokens"] == shipped_tokens()
    assert payload["requested"] == {}
    assert payload["unknown"] == []
    assert payload["group"] == ""
    assert payload["group_tokens"] == {}
    for group, names in EXPECTED_GROUP_MEMBERS.items():
        assert payload["group_members"][group] == list(names)
        assert payload["groups"][group] == {
            name: getattr(shipped, name) for name in names
        }


def test_the_payload_hands_back_a_copy():
    """A caller edited the token table through the payload."""
    payload = surface.build_view_model()
    payload["tokens"]["PRIMARY"] = "#000000"
    payload["groups"]["radii"]["RADIUS_SM"] = 99
    payload["actions"]["fire"] = "x"
    assert surface.token("PRIMARY") == shipped.PRIMARY
    assert surface.token("RADIUS_SM") == shipped.RADIUS_SM
    assert surface.ACTIONS == {}
    assert surface.build_view_model()["tokens"] == shipped_tokens()


def test_bridge_registers_the_design_system_method():
    """The renderer cannot reach the token table through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == METHOD_NAME
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 14,
                "method": surface.METHOD,
                "params": {"names": ["PRIMARY", "SPACE_M"], "group": "weights"},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["requested"] == {"PRIMARY": "#00ffcc", "SPACE_M": 16}
    assert result["unknown"] == []
    assert result["group"] == "weights"
    assert result["group_tokens"] == {
        "WEIGHT_REGULAR": 400,
        "WEIGHT_MEDIUM": 500,
        "WEIGHT_BOLD": 700,
    }
    assert result["tokens"] == shipped_tokens()


def test_the_bridge_registration_is_two_lines_and_no_more():
    """The bridge grew more than the one registration this unit adds."""
    text = BRIDGE_PATH.read_text(encoding="utf-8")
    assert text.count("design_system_surface") == 3
    assert "design_system_surface.METHOD: design_system_surface.view_model" in text
    assert "design_system_surface,\n" in text


@pytest.mark.parametrize("group", sorted(EXPECTED_GROUP_MEMBERS))
def test_the_bridge_carries_every_group(group):
    """A group over the bridge came back with the wrong tokens."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 1, "method": METHOD_NAME, "params": {"group": group}}),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["group"] == group
    assert answer["result"]["group_tokens"] == {
        name: getattr(shipped, name) for name in EXPECTED_GROUP_MEMBERS[group]
    }


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_the_bridge_answers_an_unknown_name_with_nothing(case):
    """A name the table does not hold came back over the bridge as a value."""
    from src.core import desktop_bridge

    asked = UNKNOWN_NAMES[case]
    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 2,
                "method": METHOD_NAME,
                "params": {"names": [asked], "group": asked},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["requested"] == {asked: None}
    assert answer["result"]["unknown"] == [asked]
    assert answer["result"]["group_tokens"] == {}


def test_the_bridge_ignores_a_parameter_it_does_not_know():
    """A stray parameter changed what the table answered."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    plain = desktop_bridge.handle_line(
        json.dumps({"id": 3, "method": METHOD_NAME, "params": {}}), registry
    )
    noisy = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 4,
                "method": METHOD_NAME,
                "params": {"reset": True, "nonsense": [1, 2], "names": None},
            }
        ),
        registry,
    )
    assert plain["result"] == noisy["result"]
    assert plain["result"]["tokens"] == shipped_tokens()


def test_the_table_is_the_same_on_every_call():
    """The table changed between two calls, so it holds state it must not."""
    first = surface.view_model({"names": ["PRIMARY"]})
    second = surface.view_model({})
    third = surface.view_model({"names": ["PRIMARY"]})
    assert first["tokens"] == second["tokens"] == third["tokens"]
    assert first["requested"] == third["requested"] == {"PRIMARY": "#00ffcc"}
    assert second["requested"] == {}
    assert digest(first["tokens"]) == digest(third["tokens"])


# ---------------------------------------------------------------------
# The surface without Qt, proved in a process of its own
# ---------------------------------------------------------------------

BLOCK_QT = (
    "import sys\n"
    "class Refuse:\n"
    "    def find_module(self, name, path=None):\n"
    "        return self\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.split('.')[0] in ('PySide6', 'shiboken6'):\n"
    "            raise ImportError('Qt is blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, Refuse())\n"
)

BRIDGE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.core import desktop_bridge\n"
    "registry = desktop_bridge.build_registry()\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
    "    'method': 'design_system.state',\n"
    "    'params': {'names': ['PRIMARY', 'NOPE'], 'group': 'focus'}}), registry)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules, 'frame': frame}))\n"
)

TABLE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.gui.main_tabs import design_system_surface as s\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'count': len(s.TOKEN_NAMES), 'names': list(s.TOKEN_NAMES),\n"
    "    'tokens': {n: list(v) if isinstance(v, tuple) else v\n"
    "               for n, v in s.TOKENS.items()},\n"
    "    'primary': s.token('PRIMARY'), 'missing': s.token('NOPE'),\n"
    "    'fallback': s.token('NOPE', 'none'),\n"
    "    'alias': s.alias_target('BG'),\n"
    "    'groups': len(s.GROUP_NAMES)}))\n"
)


def run_script(source):
    """Run one probe in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the token table pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["requested"] == {"PRIMARY": "#00ffcc", "NOPE": None}
    assert result["unknown"] == ["NOPE"]
    assert result["group_tokens"] == {"FOCUS_RING_WIDTH": 2, "FOCUS_RING_OFFSET": 2}
    assert result["token_names"] == list(shipped.__all__)
    assert len(result["tokens"]) == TOKEN_TOTAL


def test_the_surface_carries_every_token_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(TABLE_PROBE)
    assert answered["qt"] is False
    assert answered["count"] == TOKEN_TOTAL
    assert answered["names"] == list(shipped.__all__)
    assert answered["primary"] == "#00ffcc"
    assert answered["missing"] is None
    assert answered["fallback"] == "none"
    assert answered["alias"] == "SURFACE_0"
    assert answered["groups"] == GROUP_TOTAL
    expected = {
        name: list(value) if isinstance(value, tuple) else value
        for name, value in shipped_tokens().items()
    }
    assert answered["tokens"] == expected


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script(
        "import sys"
        + chr(10)
        + "import PySide6.QtCore"
        + chr(10)
        + BRIDGE_PROBE.replace(BLOCK_QT, "")
    )
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_qt_block_stops_a_module_that_imports_qt():
    """The Qt block let a module through that imports PySide6."""
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui import instance_consent_dialog\n"
        "    blocked = False\n"
        "except ImportError:\n"
        "    blocked = True\n"
        "print(json.dumps({'blocked': blocked}))\n"
    )
    assert run_script(probe)["blocked"] is True


def test_the_shipped_module_needs_no_qt_either():
    """The shipped module grew a Qt import the surface would inherit."""
    probe = BLOCK_QT + (
        "import json, sys\n"
        "from src.gui import design_system as d\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
        "    'count': len(d.__all__), 'primary': d.PRIMARY,\n"
        "    'shadow': list(d.SHADOW_3)}))\n"
    )
    answered = run_script(probe)
    assert answered["qt"] is False
    assert answered["count"] == TOKEN_TOTAL
    assert answered["primary"] == "#00ffcc"
    assert answered["shadow"] == [4, 8, "60"]


# ---------------------------------------------------------------------
# Nothing the surface holds is left out of the snapshot
# ---------------------------------------------------------------------

# Every constant the surface exports that is not one of the 195 tokens,
# and the payload key that carries it. A comparison reading 40 of 50
# constants passes whether the other ten match or not; this closes that
# gap for every one of them at once.
PAYLOAD_KEYS = dict(
    (
        ("TOKEN_NAMES", "token_names"),
        ("TOKENS", "tokens"),
        ("GROUP_NAMES", "group_names"),
        ("GROUP_MEMBERS", "group_members"),
        ("GROUPS", "groups"),
        ("COLORS", "colors"),
        ("TYPE_SCALE", "type_scale"),
        ("LINE_HEIGHTS", "line_heights"),
        ("FONT_FAMILIES", "font_families"),
        ("WEIGHTS", "weights"),
        ("SPACING", "spacing"),
        ("RADII", "radii"),
        ("MOTION_MS", "motion_ms"),
        ("TARGET_SIZES", "target_sizes"),
        ("TABLE_COLUMNS", "table_columns"),
        ("FOCUS", "focus"),
        ("SHADOWS", "shadows"),
        ("ALIASES", "aliases"),
        ("ALIAS_TARGETS", "alias_targets"),
        ("ACTIONS", "actions"),
        ("TIMERS", "timers"),
        ("TIMER_DELAYS_MS", "timer_delays_ms"),
        ("SKIN", "skin"),
        ("STYLE_SHEET", "style_sheet"),
    )
)

# The group name lists reach the snapshot inside `group_members`.
NAME_LIST_GROUPS = {
    "COLOR_NAMES": "colors",
    "TYPE_NAMES": "type_scale",
    "LINE_HEIGHT_NAMES": "line_heights",
    "FONT_FAMILY_NAMES": "font_families",
    "WEIGHT_NAMES": "weights",
    "SPACE_NAMES": "spacing",
    "RADIUS_NAMES": "radii",
    "MOTION_NAMES": "motion_ms",
    "TARGET_NAMES": "target_sizes",
    "TABLE_COLUMN_NAMES": "table_columns",
    "FOCUS_NAMES": "focus",
    "SHADOW_NAMES": "shadows",
    "ALIAS_NAMES": "aliases",
}

# The four constants no snapshot key carries, each with the check that
# covers it. `METHOD` is the name the bridge registers under. The other
# three are the values the three lookups return when they find nothing.
NOT_IN_THE_SNAPSHOT = dict(
    (
        ("METHOD", "test_bridge_registers_the_design_system_method"),
        (
            "MISSING_TOKEN",
            "test_token_returns_the_default_for_a_name_the_table_does_not_hold",
        ),
        (
            "NOT_AN_ALIAS",
            "test_alias_target_names_nothing_for_a_name_that_is_not_a_second_name",
        ),
        ("EMPTY_GROUP", "test_group_tokens_returns_an_empty_table_for_any_other_name"),
    )
)


def surface_constants():
    """Every value the surface exports that is not a function."""
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def test_every_constant_the_surface_holds_reaches_the_snapshot():
    """A constant the surface exports is in no snapshot the tests read.

    A comparison that reads some of the constants passes whether the
    rest match or not. Every constant is accounted for here: a token, a
    snapshot key, a group name list, or one of the four named below with
    the check that covers it.
    """
    payload = surface.build_view_model()
    constants = surface_constants()
    assert len(constants) == TOKEN_TOTAL + 41, len(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in surface.TOKENS:
            assert payload["tokens"][name] == value, name
        elif name in PAYLOAD_KEYS:
            carried = payload[PAYLOAD_KEYS[name]]
            assert list(carried) == list(value), name
            if isinstance(value, dict):
                for key in value:
                    assert carried[key] == value[key] or list(carried[key]) == list(
                        value[key]
                    ), (name, key)
        elif name in NAME_LIST_GROUPS:
            assert payload["group_members"][NAME_LIST_GROUPS[name]] == list(value), name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(NOT_IN_THE_SNAPSHOT) == 4
    assert len(PAYLOAD_KEYS) == 24
    assert len(NAME_LIST_GROUPS) == GROUP_TOTAL


def test_every_snapshot_key_carries_a_constant_the_surface_holds():
    """The snapshot grew a key no constant on the surface backs."""
    payload = surface.build_view_model()
    answered = set(PAYLOAD_KEYS.values())
    request_only = {"requested", "unknown", "group", "group_tokens"}
    assert set(payload) == answered | request_only
    assert len(payload) == 28
    for key in request_only:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_constant():
    """The completeness check passed because it looks at nothing.

    A constant that reaches no snapshot key and no named exception must
    land in the unaccounted list, or the check above is empty.
    """
    payload = surface.build_view_model()
    invented = "INVENTED_CONSTANT"
    assert invented not in surface.TOKENS
    assert invented not in PAYLOAD_KEYS
    assert invented not in NAME_LIST_GROUPS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "PRIMARY" in surface_constants()
    assert "TOKENS" in surface_constants()
    assert "view_model" not in surface_constants()
    assert "token" not in surface_constants()
