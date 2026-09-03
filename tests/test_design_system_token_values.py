"""Every colour token added by the hex-literal migration, pinned to its value.

A failure means `src/gui/design_system.py` moved a colour that widget code
renders, and the operator's GUI changed. Each value below is the LITERAL the
callsite shipped before the token replaced it; the token is never used to
build its own expected value.
"""

from src.gui import design_system as ds

SHIPPED_VALUES = {
    # Semantic roles the widgets actually render
    "ERROR": "#ff3366",
    "WARNING_STRONG": "#ff6600",
    "STATUS_INFO": "#00aaff",
    "STATUS_NEUTRAL": "#8899aa",
    "STATUS_AUTHENTICATED": "#00ddff",
    "PRIMARY_BRIGHT": "#00ffee",
    "ACCENT_GOLD": "#ffd700",
    "LAYER_CRYPTO": "#00ccaa",
    "LAYER_STOCK": "#6699ff",
    # Text roles beyond TEXT_HIGH / MED / LOW
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
    # Surfaces beyond SURFACE_0..4
    "SURFACE_CHART": "#0a0a12",
    "SURFACE_CONTROL": "#1a1a2e",
    "SURFACE_CONSOLE": "#05050a",
    "SURFACE_CONSOLE_HEADER": "#0a0a14",
    "BORDER_DISABLED": "#444444",
    # Context menu
    "MENU_SURFACE": "#1a1a2f",
    "MENU_BORDER": "#3a3a5f",
    "MENU_ITEM_SELECTED": "#2a2a4f",
    # Control states
    "STATE_ARMED": "#3ed080",
    "STATE_ENGAGED": "#2d9d5f",
    "STATE_ENGAGED_DIM": "#2d5f48",
    "STATE_ENGAGED_GLOW": "#557766",
    "STATE_PENDING": "#ffcc44",
    "STATE_STARTING": "#00e6ff",
    "STATE_MARKET": "#88ccff",
    # Tranche row skins - bot_live_settings
    "FOLD_RATIO_AMBER": "#ff9900",
    "FOLD_SOURCE_MANUAL": "#00ccff",
    "FOLD_TRANCHE_SURFACE": "#123a63",
    "FOLD_TRANCHE_BORDER": "#6ea6e6",
    "EXTRACTOR_TRANCHE_SURFACE": "#b3261e",
    "EXTRACTOR_TRANCHE_BORDER": "#ffb0a6",
    # Settings dialog controls - bot_live_settings
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
    # Bot visualizer
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
    # Main window chrome
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
    # Stock window
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
}


def test_every_added_token_holds_its_shipped_value() -> None:
    """A failure means a token was edited and the GUI repainted."""
    wrong = {
        name: (expected, getattr(ds, name, None))
        for name, expected in SHIPPED_VALUES.items()
        if getattr(ds, name, None) != expected
    }
    assert not wrong, f"token values moved: {wrong}"


def test_every_added_token_is_exported() -> None:
    """A failure means a token is unreachable through `from ... import *`."""
    missing = [name for name in SHIPPED_VALUES if name not in ds.__all__]
    assert not missing, f"missing from __all__: {missing}"


def test_no_two_tokens_share_a_value() -> None:
    """A failure means two names describe one colour and one is redundant."""
    seen: dict[str, str] = {}
    clashes = []
    for name, value in SHIPPED_VALUES.items():
        if value in seen:
            clashes.append((seen[value], name, value))
        seen[value] = name
    assert not clashes, f"duplicate values: {clashes}"
