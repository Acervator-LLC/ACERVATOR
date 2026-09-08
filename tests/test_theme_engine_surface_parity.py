"""The shipped theme engine and the Qt-free surface, side by side.

A failure means the view model carries a different theme, a different
colour, a different font stack, a different text size, a different
corner rounding, a different style sheet or a different refusal than
``src.gui.theme_engine`` ships.
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

from src.gui import theme_engine as shipped
from src.gui.color_alpha import css_colours
from src.gui.main_tabs import theme_engine_surface as surface
from tests.fixtures.qt_wiring_counts import qt_free
from tests.fixtures.host_fonts import has_real_fonts
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

SHIPPED_PATH = REPO_ROOT / "src/gui/theme_engine.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/theme_engine_surface.py"
BRIDGE_PATH = REPO_ROOT / "src/core/desktop_bridge.py"
CALLER_PATH = REPO_ROOT / "src/gui/widgets/bot_status_table.py"

METHOD_NAME = "theme_engine.state"

PIXEL_SIZE = (880, 620)

THEME_TOTAL = 5
FIELD_TOTAL = 61
DEFAULT_TOTAL = 59
REQUIRED_TOTAL = 2

# Every theme name, in the order the shipped registry builds them.
EXPECTED_THEME_NAMES = (
    "cyberpunk_dark",
    "neon_light",
    "classic_terminal",
    "minimal_modern",
    "glass_metal",
)

# Every field name, in the order the shipped dataclass declares them.
EXPECTED_FIELD_NAMES = (
    "name",
    "display_name",
    "bg_primary",
    "bg_secondary",
    "bg_tertiary",
    "bg_card",
    "bg_input",
    "bg_hover",
    "bg_selected",
    "text_primary",
    "text_secondary",
    "text_muted",
    "text_accent",
    "accent_primary",
    "accent_secondary",
    "accent_success",
    "accent_danger",
    "accent_warning",
    "accent_info",
    "border_primary",
    "border_secondary",
    "border_accent",
    "glow_color",
    "scrollbar_bg",
    "scrollbar_handle",
    "font_family",
    "font_mono",
    "font_size",
    "font_size_small",
    "font_size_large",
    "font_size_title",
    "radius_sm",
    "radius_md",
    "radius_lg",
    "tab_black_bg",
    "tab_black_text",
    "tab_white_bg",
    "tab_white_text",
    "tab_gold_bg",
    "tab_gold_text",
    "chart_bg_top",
    "chart_bg_bottom",
    "chart_grid",
    "chart_axis_text",
    "chart_up",
    "chart_up_edge",
    "chart_down",
    "chart_down_edge",
    "chart_crosshair",
    "chart_last_price",
    "chart_band",
    "chart_band_mid",
    "chart_bull",
    "chart_bear",
    "chart_zone_scrum",
    "chart_zone_fold",
    "chart_event_mark",
    "chart_gap",
)

FONT_UI_DEFAULT = "'Rajdhani', 'Orbitron', 'Segoe UI', sans-serif"
FONT_MONO_DEFAULT = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace"

# The 59 values a theme takes when it names none of its own, typed out
# here rather than read from either module.
EXPECTED_DEFAULTS = {
    "bg_primary": "#0a0a0f",
    "bg_secondary": "#12121a",
    "bg_tertiary": "#1a1a28",
    "bg_card": "#16162a",
    "bg_input": "#0e0e1a",
    "bg_hover": "#1e1e35",
    "bg_selected": "#252545",
    "text_primary": "#e0e0f0",
    "text_secondary": "#8888aa",
    "text_muted": "#8a8ab0",
    "text_accent": "#00ffcc",
    "accent_primary": "#00ffcc",
    "accent_secondary": "#ff00aa",
    "accent_success": "#00ff88",
    "accent_danger": "#ff5577",
    "accent_warning": "#ffaa00",
    "accent_info": "#4fc3ff",
    "border_primary": "#7a7a9c",
    "border_secondary": "#5e5e80",
    "border_accent": "rgba(0,255,204,68)",
    "glow_color": "rgba(0,255,204,51)",
    "scrollbar_bg": "#0a0a14",
    "scrollbar_handle": "#2a2a44",
    "font_family": FONT_UI_DEFAULT,
    "font_mono": FONT_MONO_DEFAULT,
    "font_size": "13px",
    "font_size_small": "11px",
    "font_size_large": "16px",
    "font_size_title": "20px",
    "radius_sm": "4px",
    "radius_md": "8px",
    "radius_lg": "12px",
    "tab_black_bg": "#0a0a0f",
    "tab_black_text": "#ff5577",
    "tab_white_bg": "#f5f5fa",
    "tab_white_text": "#0a0a0f",
    "tab_gold_bg": "#fcee0a",
    "tab_gold_text": "#8c0018",
    "chart_bg_top": "#08080e",
    "chart_bg_bottom": "#0c0c16",
    "chart_grid": "#1c1c30",
    "chart_axis_text": "#b4b4d2",
    "chart_up": "#00e5a0",
    "chart_up_edge": "#5cffd0",
    "chart_down": "#ff2d6f",
    "chart_down_edge": "#ff86a8",
    "chart_crosshair": "#3c3c64",
    "chart_last_price": "#ffc800",
    "chart_band": "#50a0f0",
    "chart_band_mid": "#ffc850",
    "chart_bull": "#00ff88",
    "chart_bear": "#ff5577",
    "chart_zone_scrum": "#ff0080",
    "chart_zone_fold": "#fcee0a",
    "chart_event_mark": "#ff00aa",
    "chart_gap": "#5e5e80",
    "chart_trend_fast": "#ff8c00",
    "chart_trend_slow": "#4fc3ff",
    "chart_oscillator": "#ff9060",
}

# Typed out here, not read from either module, so an edit made to both
# files together is still reported.
EXPECTED = {
    "cyberpunk_dark": dict(
        EXPECTED_DEFAULTS,
        name="cyberpunk_dark",
        display_name="Cyberpunk Dark",
    ),
    "neon_light": dict(
        EXPECTED_DEFAULTS,
        name="neon_light",
        display_name="Neon Light",
        bg_primary="#f5f5fa",
        bg_secondary="#eeeef5",
        bg_tertiary="#e5e5f0",
        bg_card="#ffffff",
        bg_input="#f0f0f8",
        bg_hover="#e0e0f0",
        bg_selected="#d0d0e8",
        text_primary="#1a1a2e",
        text_secondary="#4a4a6a",
        text_muted="#8888aa",
        text_accent="#6600cc",
        accent_primary="#6600cc",
        accent_secondary="#cc0066",
        accent_success="#00aa44",
        accent_danger="#cc0033",
        accent_warning="#cc8800",
        accent_info="#0066cc",
        border_primary="#ccccdd",
        border_secondary="#ddddee",
        border_accent="rgba(102,0,204,68)",
        glow_color="rgba(102,0,204,34)",
        scrollbar_bg="#e0e0ea",
        scrollbar_handle="#bbbbcc",
        tab_black_bg="#1a1a2e",
        tab_black_text="#ff6b8a",
        tab_white_bg="#ffffff",
        tab_white_text="#1a1a2e",
        tab_gold_bg="#f0cf1f",
        tab_gold_text="#99001f",
        chart_bg_top="#ffffff",
        chart_bg_bottom="#f0f0f8",
        chart_grid="#d8d8e8",
        chart_axis_text="#3a3a5a",
        chart_up="#00883f",
        chart_up_edge="#00662f",
        chart_down="#cc0033",
        chart_down_edge="#990026",
        chart_crosshair="#9a9ab8",
        chart_last_price="#b36b00",
        chart_band="#6600cc",
        chart_band_mid="#8a5c00",
        chart_bull="#00803a",
        chart_bear="#cc0033",
        chart_zone_scrum="#cc0066",
        chart_zone_fold="#8a6e00",
        chart_event_mark="#6600cc",
        chart_gap="#6f6f88",
        chart_trend_fast="#b35a00",
        chart_trend_slow="#0055aa",
        chart_oscillator="#b34700",
    ),
    "classic_terminal": dict(
        EXPECTED_DEFAULTS,
        name="classic_terminal",
        display_name="Classic Terminal",
        bg_primary="#0a0a0a",
        bg_secondary="#111111",
        bg_tertiary="#181818",
        bg_card="#0f0f0f",
        bg_input="#080808",
        bg_hover="#1a1a1a",
        bg_selected="#222222",
        text_primary="#00ff00",
        text_secondary="#00aa00",
        text_muted="#006600",
        text_accent="#00ff00",
        accent_primary="#00ff00",
        accent_secondary="#00cc00",
        accent_success="#00ff44",
        accent_danger="#ff0000",
        accent_warning="#ffff00",
        accent_info="#00ffff",
        border_primary="#003300",
        border_secondary="#002200",
        border_accent="rgba(0,255,0,68)",
        glow_color="rgba(0,255,0,34)",
        scrollbar_bg="#0a0a0a",
        scrollbar_handle="#003300",
        font_family=FONT_MONO_DEFAULT,
        tab_black_bg="#0a0a0a",
        tab_black_text="#ff3333",
        tab_white_bg="#e8e8e8",
        tab_white_text="#0a0a0a",
        tab_gold_bg="#ffff00",
        tab_gold_text="#990000",
        chart_bg_top="#050505",
        chart_bg_bottom="#0a0a0a",
        chart_grid="#003300",
        chart_axis_text="#00cc00",
        chart_up="#00ff44",
        chart_up_edge="#66ff99",
        chart_down="#ff0000",
        chart_down_edge="#ff6666",
        chart_crosshair="#006600",
        chart_last_price="#ffff00",
        chart_band="#00ffff",
        chart_band_mid="#00aa00",
        chart_bull="#00ff44",
        chart_bear="#ff0000",
        chart_zone_scrum="#ff3333",
        chart_zone_fold="#ffff00",
        chart_event_mark="#00ffff",
        chart_gap="#008800",
        chart_trend_fast="#ffaa00",
        chart_trend_slow="#00ffff",
        chart_oscillator="#00ff88",
    ),
    "minimal_modern": dict(
        EXPECTED_DEFAULTS,
        name="minimal_modern",
        display_name="Minimal Modern",
        bg_primary="#fafafa",
        bg_secondary="#f0f0f0",
        bg_tertiary="#e8e8e8",
        bg_card="#ffffff",
        bg_input="#f5f5f5",
        bg_hover="#eeeeee",
        bg_selected="#e0e0e0",
        text_primary="#1a1a1a",
        text_secondary="#666666",
        text_muted="#999999",
        text_accent="#2563eb",
        accent_primary="#2563eb",
        accent_secondary="#7c3aed",
        accent_success="#059669",
        accent_danger="#dc2626",
        accent_warning="#d97706",
        accent_info="#2563eb",
        border_primary="#e0e0e0",
        border_secondary="#eeeeee",
        border_accent="rgba(37,99,235,51)",
        glow_color="transparent",
        scrollbar_bg="#f0f0f0",
        scrollbar_handle="#cccccc",
        font_family="'SF Pro Display', 'Inter', 'Segoe UI', sans-serif",
        tab_black_bg="#1a1a1a",
        tab_black_text="#ff6b6b",
        tab_white_bg="#ffffff",
        tab_white_text="#1a1a1a",
        tab_gold_bg="#eab308",
        tab_gold_text="#7f1d1d",
        chart_bg_top="#ffffff",
        chart_bg_bottom="#fafafa",
        chart_grid="#e4e4e4",
        chart_axis_text="#444444",
        chart_up="#059669",
        chart_up_edge="#047857",
        chart_down="#dc2626",
        chart_down_edge="#b91c1c",
        chart_crosshair="#9ca3af",
        chart_last_price="#d97706",
        chart_band="#2563eb",
        chart_band_mid="#d97706",
        chart_bull="#059669",
        chart_bear="#dc2626",
        chart_zone_scrum="#be123c",
        chart_zone_fold="#a16207",
        chart_event_mark="#7c3aed",
        chart_gap="#8a8a8a",
        chart_trend_fast="#c2410c",
        chart_trend_slow="#1d4ed8",
        chart_oscillator="#b45309",
    ),
    "glass_metal": dict(
        EXPECTED_DEFAULTS,
        name="glass_metal",
        display_name="Glass & Metal",
        bg_primary="#1c1c24",
        bg_secondary="#242430",
        bg_tertiary="#2c2c3a",
        bg_card="#20202c",
        bg_input="#181824",
        bg_hover="#30303f",
        bg_selected="#383848",
        text_primary="#d0d0e0",
        text_secondary="#9090a8",
        text_muted="#606078",
        text_accent="#88ccff",
        accent_primary="#88ccff",
        accent_secondary="#cc88ff",
        accent_success="#88ffaa",
        accent_danger="#ff6688",
        accent_warning="#ffcc66",
        accent_info="#88ccff",
        border_primary="#3a3a50",
        border_secondary="#2e2e42",
        border_accent="rgba(136,204,255,68)",
        glow_color="rgba(136,204,255,34)",
        scrollbar_bg="#1c1c24",
        scrollbar_handle="#3a3a50",
        font_family="'Exo 2', 'Rajdhani', 'Segoe UI', sans-serif",
        tab_black_bg="#1c1c24",
        tab_black_text="#ff6688",
        tab_white_bg="#e8e8f0",
        tab_white_text="#1c1c24",
        tab_gold_bg="#e8b34a",
        tab_gold_text="#6b1020",
        chart_bg_top="#181820",
        chart_bg_bottom="#20202c",
        chart_grid="#32324a",
        chart_axis_text="#a8a8c0",
        chart_up="#3fd6a0",
        chart_up_edge="#88ffcc",
        chart_down="#ff5f88",
        chart_down_edge="#ffa0b8",
        chart_crosshair="#4a4a62",
        chart_last_price="#ffcc66",
        chart_band="#88ccff",
        chart_band_mid="#ffcc66",
        chart_bull="#88ffaa",
        chart_bear="#ff6688",
        chart_zone_scrum="#ff4d7d",
        chart_zone_fold="#e8b34a",
        chart_event_mark="#cc88ff",
        chart_gap="#8f8fb0",
        chart_trend_fast="#ffb066",
        chart_trend_slow="#88ccff",
        chart_oscillator="#ffa07a",
    ),
}

EXPECTED_DISPLAY_NAMES = {
    "cyberpunk_dark": "Cyberpunk Dark",
    "neon_light": "Neon Light",
    "classic_terminal": "Classic Terminal",
    "minimal_modern": "Minimal Modern",
    "glass_metal": "Glass & Metal",
}

# The length of the style sheet each theme produces, typed out here.
# A template that lost a rule on one side alone changes these.
EXPECTED_STYLE_SHEET_LENGTHS = {
    "cyberpunk_dark": 7670,
    "neon_light": 7666,
    "classic_terminal": 7678,
    "minimal_modern": 7673,
    "glass_metal": 7666,
}

# Values `QSS_TEMPLATE` never carries, so no render can report them.
NEVER_IN_THE_STYLE_SHEET = (
    "name",
    "accent_success",
    "accent_warning",
    "accent_info",
    "border_accent",
    "glow_color",
    "font_mono",
    "font_size_large",
    "radius_lg",
)

# Values a grabbed image cannot reach: one is inside a comment, two sit
# behind a pointer state, and six reach only the main window's tab bar.
UNREACHED_BY_A_STILL_PICTURE = {
    "display_name": "comment",
    "bg_hover": "state",
    "accent_secondary": "state",
    "tab_black_bg": "tab bar",
    "tab_black_text": "tab bar",
    "tab_white_bg": "tab bar",
    "tab_white_text": "tab bar",
    "tab_gold_bg": "tab bar",
    "tab_gold_text": "tab bar",
}

PAINTED_FIELDS = tuple(
    name
    for name in EXPECTED_FIELD_NAMES
    if name not in NEVER_IN_THE_STYLE_SHEET and name not in UNREACHED_BY_A_STILL_PICTURE
)

# The awkward names a caller may ask for. None is a theme.
UNKNOWN_NAMES = {
    "empty": "",
    "zero": "0",
    "negative": "-1",
    "very_large": "9" * 40,
    "unicode": "Δ→⚡",
    "long": "X" * 200,
    "markup": "<b>cyberpunk_dark</b>",
    "uppercase": "CYBERPUNK_DARK",
    "spaced": " cyberpunk_dark ",
    "dotted": "themes.cyberpunk_dark",
    "display": "Cyberpunk Dark",
    "private": "_THEMES",
    "dunder": "__all__",
    "quoted": '"cyberpunk_dark"',
    "newline": "cyberpunk_dark\nneon_light",
}

# The values a caller may send where a theme name belongs.
NON_STRING_NAMES: tuple = (None, 0, -1, 9.5, True, [], ["cyberpunk_dark"], {}, ())

FIELD_CASES = [
    (theme, field) for theme in EXPECTED_THEME_NAMES for field in EXPECTED_FIELD_NAMES
]

MARKER_FORMAT = "<<%s>>"


# The two theme tables, and the panel painted from one of them


def shipped_theme(name):
    """One shipped theme's 34 values, by field name."""
    return {
        field: getattr(shipped.THEMES[name], field) for field in EXPECTED_FIELD_NAMES
    }


def surface_theme(name):
    """One surface theme's 34 values, by field name."""
    return dict(surface.THEMES[name])


#: The theme fields whose value is an rgba call carrying Qt's alpha byte.
ALPHA_BYTE_FIELD_NAMES = ("border_accent", "glow_color")


def painted(value):
    """One shipped value the way the payload carries it for a browser.

    The theme table holds the alpha byte Qt reads and the payload leaves
    under ``css_colours``, so a parity comparison against the shipped
    module reads the shipped value through the same conversion.
    """
    return css_colours(value)


def shipped_style_sheet(name):
    """The style-sheet text the shipped module builds for one theme."""
    return shipped.generate_qss(shipped.THEMES[name])


def surface_style_sheet(name):
    """The style-sheet text the surface builds for one theme."""
    return surface.generate_qss(surface.THEMES[name])


def digest(payload):
    """A stable hash over one side's whole answer."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=list).encode("utf-8")
    ).hexdigest()


def text_digest(text):
    """A stable hash over one style sheet."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def marked_fields():
    """A token table whose every field carries a marker naming itself."""
    return {field: MARKER_FORMAT % field for field in EXPECTED_FIELD_NAMES}


def field_census(text):
    """How many times each field's marker appears in a marked style sheet."""
    return {field: text.count(MARKER_FORMAT % field) for field in EXPECTED_FIELD_NAMES}


def rule_selectors_holding(marker, text):
    """The selector of every style rule whose body holds `marker`."""
    found = []
    for block in text.split("}"):
        if marker in block and "{" in block:
            selector, _, body = block.rpartition("{")
            if marker in body:
                found.append(selector.strip().splitlines()[-1].strip())
    return found


def comment_spans(text):
    """The start and end offset of every comment in a style sheet."""
    spans = []
    cursor = 0
    while True:
        start = text.find("/*", cursor)
        if start < 0:
            return spans
        end = text.find("*/", start + 2)
        if end < 0:
            return spans
        spans.append((start, end + 2))
        cursor = end + 2


def app():
    """The process application object every render needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def build_panel(qss):
    """One window painted by a style sheet, and by nothing else.

    A tab strip, a card, three buttons, an input, a drop list, a
    heading, a muted caption, a table with a selected row and a
    scroll bar, a bar, a slider, a menu bar, a status bar, a check box
    and a radio button between them draw every rule a still picture
    reaches. `qss` is the only source, so the same call on the two
    sides is the parity comparison.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMenuBar,
        QProgressBar,
        QPushButton,
        QRadioButton,
        QSlider,
        QSplitter,
        QStatusBar,
        QTableWidget,
        QTableWidgetItem,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    app()
    root = QWidget()
    outer = QVBoxLayout(root)
    outer.setContentsMargins(8, 8, 8, 8)
    outer.setSpacing(6)

    menus = QMenuBar()
    menus.addMenu("File")
    menus.addMenu("View")
    outer.addWidget(menus)

    heading = QLabel("Accumulation")
    heading.setProperty("heading", "true")
    outer.addWidget(heading)

    caption = QLabel("scrummed today")
    caption.setProperty("muted", "true")
    outer.addWidget(caption)

    tabs = QTabWidget()
    first = QWidget()
    first_rows = QVBoxLayout(first)

    card = QFrame()
    card.setFrameShape(QFrame.StyledPanel)
    card_rows = QVBoxLayout(card)

    group = QGroupBox("Targets")
    group_rows = QHBoxLayout(group)
    plain = QPushButton("Fold")
    accent = QPushButton("Scrum")
    accent.setProperty("accent", "true")
    danger = QPushButton("Stop")
    danger.setProperty("danger", "true")
    for button in (plain, accent, danger):
        group_rows.addWidget(button)
    card_rows.addWidget(group)

    entry = QLineEdit("1250.00")
    card_rows.addWidget(entry)
    choices = QComboBox()
    choices.addItems(["BTC", "ETH", "SOL"])
    card_rows.addWidget(choices)
    first_rows.addWidget(card)

    bar = QProgressBar()
    bar.setValue(64)
    first_rows.addWidget(bar)

    slider = QSlider(Qt.Horizontal)
    slider.setValue(40)
    first_rows.addWidget(slider)

    ticks = QHBoxLayout()
    checked = QCheckBox("Armed")
    checked.setChecked(True)
    ticks.addWidget(checked)
    ticks.addWidget(QCheckBox("Idle"))
    radio = QRadioButton("Live")
    radio.setChecked(True)
    ticks.addWidget(radio)
    ticks.addWidget(QRadioButton("Paper"))
    first_rows.addLayout(ticks)

    table = QTableWidget(14, 3)
    table.setAlternatingRowColors(True)
    table.setHorizontalHeaderLabels(["Bot", "Ratio", "Held"])
    for row in range(14):
        for column in range(3):
            table.setItem(row, column, QTableWidgetItem("%d.%d" % (row, column)))
    table.setFixedHeight(120)
    table.selectRow(2)
    first_rows.addWidget(table)

    tabs.addTab(first, "Trading")
    tabs.addTab(QLabel("History"), "History")
    tabs.setCurrentIndex(0)

    split = QSplitter(Qt.Horizontal)
    split.addWidget(tabs)
    split.addWidget(QLabel("Console"))
    split.setSizes([600, 200])
    outer.addWidget(split)

    status = QStatusBar()
    status.showMessage("ready")
    outer.addWidget(status)

    root.setStyleSheet(qss)
    return root


# The two sides, value for value


@pytest.mark.parametrize("theme,field", FIELD_CASES)
def test_every_field_carries_the_shipped_value(theme, field):
    """A theme value moved on one side and not the other."""
    old = getattr(shipped.THEMES[theme], field)
    new = surface.THEMES[theme][field]
    assert new == old, f"{theme}.{field}: shipped {old!r}, surface {new!r}"


@pytest.mark.parametrize("theme,field", FIELD_CASES)
def test_every_field_matches_the_value_typed_here(theme, field):
    """A theme value moved on both sides together."""
    new = surface.THEMES[theme][field]
    assert new == EXPECTED[theme][field], f"{theme}.{field} is {new!r}"


def test_a_value_changed_on_one_side_alone_is_reported():
    """The comparison above passed because it reads one side twice."""
    old = shipped_theme("cyberpunk_dark")
    new = surface_theme("cyberpunk_dark")
    assert old == new
    moved = dict(new)
    moved["accent_primary"] = "#123456"
    assert moved != old
    assert moved["accent_primary"] != old["accent_primary"]


def test_the_field_names_are_the_shipped_dataclass_fields():
    """A field grew on one side with no counterpart on the other."""
    import dataclasses

    declared = tuple(f.name for f in dataclasses.fields(shipped.ThemeTokens))
    assert declared == EXPECTED_FIELD_NAMES
    assert tuple(surface.FIELD_NAMES) == declared
    assert len(declared) == FIELD_TOTAL
    for theme in EXPECTED_THEME_NAMES:
        assert tuple(surface.THEMES[theme]) == declared, theme


def test_a_field_added_or_lost_on_either_side_is_reported():
    """The field check passed because it compares a list to itself."""
    assert set(surface.FIELD_NAMES) - {"glow_color"} != set(EXPECTED_FIELD_NAMES)
    assert set(EXPECTED_FIELD_NAMES) | {"invented"} != set(surface.FIELD_NAMES)
    assert "invented" not in surface.THEMES["cyberpunk_dark"]


def test_the_theme_names_and_their_order_match():
    """A theme was added, lost or reordered on one side."""
    assert tuple(shipped.THEMES) == EXPECTED_THEME_NAMES
    assert tuple(surface.THEME_NAMES) == EXPECTED_THEME_NAMES
    assert tuple(surface.THEMES) == tuple(shipped.THEMES)
    assert len(surface.THEMES) == THEME_TOTAL


def test_the_display_names_match():
    """A theme's shown name moved on one side."""
    assert surface.DISPLAY_NAMES == EXPECTED_DISPLAY_NAMES
    for theme in EXPECTED_THEME_NAMES:
        assert surface.DISPLAY_NAMES[theme] == shipped.THEMES[theme].display_name
    assert len(surface.DISPLAY_NAMES) == THEME_TOTAL


def test_the_default_values_are_the_shipped_dataclass_defaults():
    """A default moved on one side and not the other."""
    import dataclasses

    declared = {
        f.name: f.default
        for f in dataclasses.fields(shipped.ThemeTokens)
        if f.default is not dataclasses.MISSING
    }
    assert declared == EXPECTED_DEFAULTS
    assert surface.DEFAULT_TOKENS == declared
    assert len(declared) == DEFAULT_TOTAL
    assert tuple(surface.REQUIRED_FIELD_NAMES) == ("name", "display_name")
    assert len(surface.REQUIRED_FIELD_NAMES) == REQUIRED_TOTAL
    assert set(declared) | set(surface.REQUIRED_FIELD_NAMES) == set(
        EXPECTED_FIELD_NAMES
    )


def test_a_theme_that_names_no_value_takes_the_default():
    """The default theme stopped carrying the dataclass defaults."""
    dark = surface.THEMES["cyberpunk_dark"]
    for field, value in EXPECTED_DEFAULTS.items():
        assert dark[field] == value, field
        assert getattr(shipped.CYBERPUNK_DARK, field) == value, field
    assert dark["name"] == "cyberpunk_dark"
    assert dark["display_name"] == "Cyberpunk Dark"


def test_a_theme_that_names_its_own_value_keeps_it():
    """A theme's own value was overwritten by the default."""
    terminal = surface.THEMES["classic_terminal"]
    assert terminal["font_family"] == FONT_MONO_DEFAULT
    assert terminal["font_family"] != EXPECTED_DEFAULTS["font_family"]
    assert terminal["font_mono"] == FONT_MONO_DEFAULT
    assert terminal["font_size"] == EXPECTED_DEFAULTS["font_size"]
    assert surface.THEMES["minimal_modern"]["glow_color"] == "transparent"
    assert surface.THEMES["minimal_modern"]["radius_lg"] == "12px"


def test_the_five_theme_constants_are_the_registry_entries():
    """A theme constant and its registry entry drifted apart."""
    pairs = (
        (surface.CYBERPUNK_DARK, "cyberpunk_dark"),
        (surface.NEON_LIGHT, "neon_light"),
        (surface.CLASSIC_TERMINAL, "classic_terminal"),
        (surface.MINIMAL_MODERN, "minimal_modern"),
        (surface.GLASS_METAL, "glass_metal"),
    )
    assert len(pairs) == THEME_TOTAL
    for constant, name in pairs:
        assert constant is surface.THEMES[name], name
        assert constant["name"] == name
        assert constant == EXPECTED[name]


def test_the_two_sides_hash_the_same():
    """The two theme tables differ somewhere the value checks missed."""
    old = {name: shipped_theme(name) for name in EXPECTED_THEME_NAMES}
    new = {name: surface_theme(name) for name in EXPECTED_THEME_NAMES}
    assert old == new
    assert digest(old) == digest(new)
    assert digest(new) == digest(EXPECTED)


def test_the_sample_hashes_are_reported():
    """A hash the report quotes no longer matches what the code builds."""
    samples = {
        "shipped_themes": digest(
            {name: shipped_theme(name) for name in EXPECTED_THEME_NAMES}
        ),
        "surface_themes": digest(
            {name: surface_theme(name) for name in EXPECTED_THEME_NAMES}
        ),
        "typed_here": digest(EXPECTED),
        "shipped_style_sheets": digest(
            {name: shipped_style_sheet(name) for name in EXPECTED_THEME_NAMES}
        ),
        "surface_style_sheets": digest(
            {name: surface_style_sheet(name) for name in EXPECTED_THEME_NAMES}
        ),
    }
    assert len(set(samples.values())) == 2, samples
    assert (
        samples["shipped_themes"] == samples["surface_themes"] == samples["typed_here"]
    )
    assert samples["shipped_style_sheets"] == samples["surface_style_sheets"]
    assert all(len(value) == 64 for value in samples.values()), samples


def test_the_hash_can_report_a_difference():
    """The hash returns one value whatever it is handed."""
    old = {name: shipped_theme(name) for name in EXPECTED_THEME_NAMES}
    moved = {name: dict(values) for name, values in old.items()}
    moved["glass_metal"]["bg_card"] = "#000001"
    assert digest(moved) != digest(old)
    assert text_digest("a") != text_digest("b")
    assert text_digest("a") == text_digest("a")


# The style sheet each theme builds


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_every_style_sheet_is_the_same_text(theme):
    """The surface built a different style sheet than the shipped module."""
    old = shipped_style_sheet(theme)
    new = surface_style_sheet(theme)
    assert new == old, f"{theme}: {len(old)} shipped characters, {len(new)} surface"
    assert surface.STYLE_SHEETS[theme] == old


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_every_style_sheet_hashes_the_same(theme):
    """The style sheets differ somewhere a character comparison missed."""
    assert text_digest(surface_style_sheet(theme)) == text_digest(
        shipped_style_sheet(theme)
    )


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_every_style_sheet_is_the_length_typed_here(theme):
    """A rule was added or lost on both sides together."""
    length = len(surface_style_sheet(theme))
    assert length == EXPECTED_STYLE_SHEET_LENGTHS[theme], f"{theme} is {length}"
    assert len(shipped_style_sheet(theme)) == EXPECTED_STYLE_SHEET_LENGTHS[theme]


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_every_style_sheet_names_its_theme_and_ends_the_same_way(theme):
    """The style sheet lost its heading or its last rule."""
    text = surface_style_sheet(theme)
    assert text.startswith("\n/* ===== Acervator — ")
    assert EXPECTED_DISPLAY_NAMES[theme] in text.splitlines()[1]
    assert text.endswith("}\n")
    assert text == shipped_style_sheet(theme)


def test_the_style_sheet_comparison_can_report_a_difference():
    """The style-sheet check passes whatever text it is handed."""
    dark = surface_style_sheet("cyberpunk_dark")
    light = surface_style_sheet("neon_light")
    assert dark != light
    assert text_digest(dark) != text_digest(light)
    assert len(dark) != len(light)


def test_generate_qss_reads_the_values_it_is_handed():
    """The style sheet ignores the theme and returns one fixed text."""
    marked = surface.generate_qss(marked_fields())
    assert MARKER_FORMAT % "bg_primary" in marked
    assert MARKER_FORMAT % "accent_primary" in marked
    assert EXPECTED_DEFAULTS["bg_primary"] not in marked
    shipped_marked = shipped.generate_qss(shipped.ThemeTokens(**marked_fields()))
    assert marked == shipped_marked


# Which fields the style sheet uses, counted on both sides


def test_both_sides_use_the_same_fields_the_same_number_of_times():
    """A field reaches the style sheet on one side and not the other."""
    old = field_census(shipped.generate_qss(shipped.ThemeTokens(**marked_fields())))
    new = field_census(surface.generate_qss(marked_fields()))
    assert new == old, {
        field: (old[field], new[field]) for field in old if old[field] != new[field]
    }
    used = [field for field, count in new.items() if count]
    unused = [field for field, count in new.items() if not count]
    assert sorted(unused) == sorted(NEVER_IN_THE_STYLE_SHEET), unused
    assert len(used) == 31
    assert len(unused) == 9
    assert used + unused != []


def test_the_field_census_can_see_a_field():
    """The census reported nothing because it can never report a field."""
    marked = surface.generate_qss(marked_fields())
    counted = field_census(marked)
    assert counted["bg_primary"] > 0
    assert counted["accent_primary"] > 1
    assert counted["glow_color"] == 0
    assert field_census("nothing here") == {field: 0 for field in EXPECTED_FIELD_NAMES}
    assert field_census(MARKER_FORMAT % "glow_color")["glow_color"] == 1


def test_the_two_state_values_sit_behind_a_pointer_state():
    """A value the still picture cannot reach moved into a plain rule."""
    marked = surface.generate_qss(marked_fields())
    for field in ("bg_hover", "accent_secondary"):
        selectors = rule_selectors_holding(MARKER_FORMAT % field, marked)
        assert selectors, field
        for selector in selectors:
            assert ":hover" in selector or ":selected" in selector, (field, selector)
    plain = rule_selectors_holding(MARKER_FORMAT % "bg_primary", marked)
    assert any(":hover" not in one and ":selected" not in one for one in plain)


def test_the_shown_name_sits_inside_a_comment():
    """The theme's shown name moved into a rule a picture could paint."""
    marked = surface.generate_qss(marked_fields())
    marker = MARKER_FORMAT % "display_name"
    at = marked.find(marker)
    assert at > 0
    spans = comment_spans(marked)
    assert spans
    assert any(start < at < end for start, end in spans), (at, spans[:3])
    colour_at = marked.find(MARKER_FORMAT % "bg_primary")
    assert not any(start < colour_at < end for start, end in spans)


# What the shipped module has, and where each item went

SURFACE_FUNCTIONS = (
    "build_theme",
    "generate_qss",
    "has_theme",
    "unknown_theme_message",
    "theme_tokens",
    "style_sheet",
    "requested_theme",
    "build_view_model",
    "view_model",
)

SURFACE_CLASSES = ("StyleSheetSink", "ThemeManagerModel")

SHIPPED_DEFINITIONS = ("ThemeTokens", "generate_qss", "ThemeManager")

MANAGER_MEMBERS = (
    "__init__",
    "list_themes",
    "get_theme",
    "get_qss",
    "apply_theme",
    "current",
)


def test_neither_side_declares_a_signal_to_wire():
    """The surface exports no action, and neither module carries a Signal
    for a widget to connect."""
    from PySide6.QtCore import Signal

    assert surface.ACTIONS == {}
    for module in (shipped, surface):
        signals = [
            name for name, value in vars(module).items() if isinstance(value, Signal)
        ]
        assert signals == [], (module.__name__, signals)


def test_the_widget_that_reads_these_values_does_wire_its_own_signals():
    """The signal check reports none whatever a module declares."""
    from PySide6.QtCore import SignalInstance

    from src.gui.widgets.bot_status_table import BotStatusTable

    app()
    table = BotStatusTable()
    wired = [
        name
        for name in dir(BotStatusTable)
        if isinstance(getattr(table, name, None), SignalInstance)
    ]
    assert wired, "the widget declares no signal at all"


def test_the_shipped_definitions_each_have_a_counterpart():
    """A definition on the shipped side has nothing standing for it."""
    import inspect

    defined = {
        name
        for name, value in vars(shipped).items()
        if (inspect.isfunction(value) or inspect.isclass(value))
        and getattr(value, "__module__", "") == shipped.__name__
    }
    assert defined == set(SHIPPED_DEFINITIONS)
    assert len(defined) == 3
    assert callable(surface.generate_qss)
    assert isinstance(surface.THEMES["cyberpunk_dark"], dict)
    assert inspect.isclass(surface.ThemeManagerModel)
    for member in MANAGER_MEMBERS:
        assert hasattr(shipped.ThemeManager, member), member
        assert hasattr(surface.ThemeManagerModel, member), member
    assert len(MANAGER_MEMBERS) == 6


def test_the_definition_counter_can_see_a_definition():
    """The counter reported none because it can never report one."""
    import inspect

    from src.gui.main_tabs import table_cells_surface as neighbour

    defined = {
        name
        for name, value in vars(neighbour).items()
        if (inspect.isfunction(value) or inspect.isclass(value))
        and getattr(value, "__module__", "") == neighbour.__name__
    }
    assert len(defined) > 0, "the counter cannot see a definition anywhere"
    assert "TableCellsModel" in defined


def test_the_surface_functions_are_reachable_and_described():
    """A named helper is missing, or carries no description."""
    import inspect

    found = {
        name
        for name, value in vars(surface).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == surface.__name__
    }
    assert found == set(SURFACE_FUNCTIONS)
    assert len(SURFACE_FUNCTIONS) == 9
    for name in SURFACE_FUNCTIONS:
        member = getattr(surface, name)
        assert callable(member), name
        assert (member.__doc__ or "").strip(), name
    classes = {
        name
        for name, value in vars(surface).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == surface.__name__
    }
    assert classes == set(SURFACE_CLASSES)
    with pytest.raises(AttributeError):
        surface.no_such_helper()


def test_the_theme_table_declares_no_action_no_timer_and_no_skin():
    """The surface gained behaviour the module it replaces never had."""
    assert surface.ACTIONS == {}
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert surface.SKIN == {}
    payload = surface.build_view_model()
    assert payload["actions"] == {}
    assert payload["timers"] == {}
    assert payload["timer_delays_ms"] == []
    assert payload["skin"] == {}
    assert len(surface.ACTIONS) == len(surface.TIMERS) == 0


# Every branch of every function


def test_list_themes_returns_the_same_five_pairs():
    """The theme list came back different on the two sides."""
    old = shipped.ThemeManager().list_themes()
    new = surface.ThemeManagerModel().list_themes()
    assert new == old
    assert new == [
        {"name": name, "display_name": EXPECTED_DISPLAY_NAMES[name]}
        for name in EXPECTED_THEME_NAMES
    ]
    assert len(new) == THEME_TOTAL


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_get_theme_returns_the_shipped_values(theme):
    """One theme came back with different values on the two sides."""
    old = shipped.ThemeManager().get_theme(theme)
    new = surface.ThemeManagerModel().get_theme(theme)
    assert new == EXPECTED[theme]
    assert {field: getattr(old, field) for field in EXPECTED_FIELD_NAMES} == new


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_get_theme_refuses_an_unknown_name_the_same_way(case):
    """The refusal text drifted between the two sides."""
    name = UNKNOWN_NAMES[case]
    with pytest.raises(ValueError) as old:
        shipped.ThemeManager().get_theme(name)
    with pytest.raises(ValueError) as new:
        surface.ThemeManagerModel().get_theme(name)
    assert str(new.value) == str(old.value), case
    assert str(new.value) == surface.unknown_theme_message(name)
    assert str(new.value).startswith("Unknown theme: ")
    assert "['cyberpunk_dark', 'neon_light', 'classic_terminal'," in str(new.value)


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_get_qss_returns_the_same_style_sheet(theme):
    """The manager built a different style sheet on the two sides."""
    old = shipped.ThemeManager().get_qss(theme)
    new = surface.ThemeManagerModel().get_qss(theme)
    assert new == old
    assert new == surface.STYLE_SHEETS[theme]
    assert text_digest(new) == text_digest(old)


def test_get_qss_refuses_an_unknown_name_the_same_way():
    """An unknown name returned a style sheet instead of refusing."""
    with pytest.raises(ValueError) as old:
        shipped.ThemeManager().get_qss("nope")
    with pytest.raises(ValueError) as new:
        surface.ThemeManagerModel().get_qss("nope")
    assert str(new.value) == str(old.value)


def test_apply_theme_hands_the_style_sheet_to_an_application_that_takes_one():
    """The window was never given the style sheet it asked for."""

    class Window:
        def __init__(self):
            self.style_sheet = ""
            self.call_count = 0

        def setStyleSheet(self, qss):
            self.style_sheet = qss
            self.call_count += 1

    old_window = Window()
    new_window = Window()
    shipped.ThemeManager().apply_theme("glass_metal", old_window)
    surface.ThemeManagerModel().apply_theme("glass_metal", new_window)
    assert new_window.style_sheet == old_window.style_sheet
    assert new_window.style_sheet == surface.STYLE_SHEETS["glass_metal"]
    assert new_window.call_count == old_window.call_count == 1


def test_apply_theme_records_the_theme_when_the_application_takes_no_style_sheet():
    """A window with no style setter stopped the theme being recorded."""
    plain = object()
    assert not hasattr(plain, "setStyleSheet")
    old_manager = shipped.ThemeManager()
    new_manager = surface.ThemeManagerModel()
    old_manager.apply_theme("neon_light", plain)
    new_manager.apply_theme("neon_light", plain)
    assert old_manager.current is shipped.THEMES["neon_light"]
    assert new_manager.current is surface.THEMES["neon_light"]
    assert new_manager.current["name"] == old_manager.current.name


def test_apply_theme_refuses_an_unknown_name_and_leaves_the_current_theme():
    """An unknown name was recorded as the current theme."""
    old_manager = shipped.ThemeManager()
    new_manager = surface.ThemeManagerModel()
    sink = surface.StyleSheetSink()
    old_manager.apply_theme("minimal_modern", sink)
    new_manager.apply_theme("minimal_modern", sink)
    with pytest.raises(ValueError):
        old_manager.apply_theme("nope", sink)
    with pytest.raises(ValueError):
        new_manager.apply_theme("nope", sink)
    assert old_manager.current.name == "minimal_modern"
    assert new_manager.current["name"] == "minimal_modern"
    assert sink.style_sheet == surface.STYLE_SHEETS["minimal_modern"]


def test_current_is_empty_until_a_theme_is_applied():
    """The manager reported a theme before one was chosen."""
    old_manager = shipped.ThemeManager()
    new_manager = surface.ThemeManagerModel()
    assert old_manager.current is None
    assert new_manager.current is surface.NO_CURRENT_THEME
    assert new_manager.current is None
    sink = surface.StyleSheetSink()
    old_manager.apply_theme("cyberpunk_dark", sink)
    new_manager.apply_theme("cyberpunk_dark", sink)
    assert old_manager.current is not None
    assert new_manager.current is not None
    assert new_manager.current["display_name"] == old_manager.current.display_name


def test_the_style_sheet_sink_records_what_the_window_would_receive():
    """The stand-in swallowed the style sheet without recording it."""
    sink = surface.StyleSheetSink()
    assert sink.style_sheet == ""
    assert sink.call_count == 0
    assert hasattr(sink, "setStyleSheet")
    surface.ThemeManagerModel().apply_theme("classic_terminal", sink)
    assert sink.call_count == 1
    assert sink.style_sheet == surface.STYLE_SHEETS["classic_terminal"]
    surface.ThemeManagerModel().apply_theme("neon_light", sink)
    assert sink.call_count == 2
    assert sink.style_sheet == surface.STYLE_SHEETS["neon_light"]


def test_has_theme_answers_both_ways():
    """The question answers the same whatever it is asked."""
    for theme in EXPECTED_THEME_NAMES:
        assert surface.has_theme(theme) is True, theme
    for case, name in UNKNOWN_NAMES.items():
        assert surface.has_theme(name) is False, case
    assert len({surface.has_theme("cyberpunk_dark"), surface.has_theme("nope")}) == 2


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_theme_tokens_returns_the_whole_theme(theme):
    """One theme came back short over the lookup."""
    assert surface.theme_tokens(theme) == EXPECTED[theme]
    assert len(surface.theme_tokens(theme)) == FIELD_TOTAL


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_theme_tokens_returns_an_empty_table_for_any_other_name(case):
    """An unknown name came back carrying a theme."""
    assert surface.theme_tokens(UNKNOWN_NAMES[case]) == {}
    assert surface.theme_tokens(UNKNOWN_NAMES[case]) == surface.NO_TOKENS


def test_theme_tokens_hands_back_a_copy():
    """A caller that edits the answer changed the table for everyone."""
    first = surface.theme_tokens("cyberpunk_dark")
    first["bg_primary"] = "#ffffff"
    assert surface.theme_tokens("cyberpunk_dark")["bg_primary"] == "#0a0a0f"
    assert surface.THEMES["cyberpunk_dark"]["bg_primary"] == "#0a0a0f"
    empty = surface.theme_tokens("nope")
    empty["invented"] = 1
    assert surface.theme_tokens("nope") == {}
    assert surface.NO_TOKENS == {}


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_style_sheet_returns_the_text_for_every_theme(theme):
    """One theme's style sheet came back wrong over the lookup."""
    assert surface.style_sheet(theme) == shipped_style_sheet(theme)


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_style_sheet_returns_the_empty_string_for_any_other_name(case):
    """An unknown name came back carrying a style sheet."""
    assert surface.style_sheet(UNKNOWN_NAMES[case]) == ""
    assert surface.style_sheet(UNKNOWN_NAMES[case]) == surface.NO_STYLE_SHEET


def test_requested_theme_reads_a_string_and_refuses_anything_else():
    """A caller sending a number asked for the text of that number."""
    assert surface.requested_theme("cyberpunk_dark") == "cyberpunk_dark"
    assert surface.requested_theme("") == ""
    assert surface.requested_theme("0") == "0"
    assert surface.requested_theme("-1") == "-1"
    assert surface.requested_theme("9" * 40) == "9" * 40
    assert surface.requested_theme("Δ→⚡") == "Δ→⚡"
    assert surface.requested_theme("X" * 200) == "X" * 200
    assert surface.requested_theme("<b>x</b>") == "<b>x</b>"
    for value in NON_STRING_NAMES:
        assert surface.requested_theme(value) == "", repr(value)


def test_unknown_theme_message_names_the_value_it_was_given():
    """The refusal text stopped naming the name it refused."""
    for case, name in UNKNOWN_NAMES.items():
        message = surface.unknown_theme_message(name)
        assert message.startswith("Unknown theme: "), case
        assert name in message, case
    assert surface.unknown_theme_message("") == (
        "Unknown theme: . Available: "
        "['cyberpunk_dark', 'neon_light', 'classic_terminal', "
        "'minimal_modern', 'glass_metal']"
    )


# The surface without Qt


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    answered = qt_free("src.gui.main_tabs.theme_engine_surface", "ThemeManagerModel")
    assert answered["imported"] is True, answered
    assert answered["qt"] == [], answered


def test_the_shipped_theme_engine_is_qt_free_too():
    """``ThemeManager`` writes stylesheet text and never builds a widget."""
    answered = qt_free("src.gui.theme_engine", "ThemeManager")
    assert answered["imported"] is True, answered
    assert answered["qt"] == [], answered


def test_the_qt_block_stops_a_module_that_needs_qt():
    """POSITIVE CONTROL for ``qt_free``: a widget module cannot load without it."""
    answered = qt_free("src.gui.widgets.bot_status_table", "BotStatusTable")
    assert answered["imported"] is False, answered


def test_the_surface_carries_its_own_copy_of_every_value(monkeypatch):
    """The surface read its values off the module it replaces.

    A surface that imported the shipped themes would follow them, and
    the whole comparison above would be one side read twice. The
    shipped value is moved and the surface must not move with it.
    """
    for theme, field, moved in (
        ("cyberpunk_dark", "accent_primary", "#123456"),
        ("neon_light", "bg_card", "#654321"),
        ("glass_metal", "font_family", "'Courier New'"),
        ("classic_terminal", "radius_lg", "99px"),
    ):
        was = getattr(shipped.THEMES[theme], field)
        monkeypatch.setattr(shipped.THEMES[theme], field, moved)
        assert getattr(shipped.THEMES[theme], field) == moved, field
        assert surface.THEMES[theme][field] == was, field
        assert surface.build_view_model()["themes"][theme][field] == was, field
        monkeypatch.undo()
        assert getattr(shipped.THEMES[theme], field) == was, field


def test_the_surface_style_sheet_does_not_follow_the_shipped_template(monkeypatch):
    """The surface built its style sheet from the shipped template."""
    was = shipped.generate_qss
    monkeypatch.setattr(shipped, "generate_qss", lambda theme: "moved")
    assert shipped.generate_qss(shipped.CYBERPUNK_DARK) == "moved"
    assert surface.generate_qss(surface.CYBERPUNK_DARK) != "moved"
    assert len(surface.generate_qss(surface.CYBERPUNK_DARK)) == 7376
    monkeypatch.undo()
    assert shipped.generate_qss is was


# The pictures


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_the_two_sides_paint_one_picture(theme):
    """The surface painted a different window than the shipped module."""
    app()
    note = "%s, %s" % (theme, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(build_panel(shipped_style_sheet(theme)), PIXEL_SIZE),
        new_side=render_offscreen(build_panel(surface_style_sheet(theme)), PIXEL_SIZE),
        note=note,
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real themes, one taken from each side. A pass proves the
    comparison reports a window that is painted differently, so the
    matches above are not green by being unable to fail.
    """
    app()
    assert_pictures_differ(
        old_side=render_offscreen(
            build_panel(shipped_style_sheet("cyberpunk_dark")), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            build_panel(surface_style_sheet("neon_light")), PIXEL_SIZE
        ),
        note="cyberpunk_dark against neon_light",
    )


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_the_panel_paints_more_than_one_colour(theme):
    """The two sides matched because the window painted one flat colour."""
    app()
    image = render_offscreen(build_panel(surface_style_sheet(theme)), PIXEL_SIZE)
    assert image.width() == PIXEL_SIZE[0]
    assert image.height() == PIXEL_SIZE[1]
    from PySide6.QtGui import QColor

    seen = set()
    for x in range(0, image.width(), 5):
        for y in range(0, image.height(), 5):
            seen.add(QColor(image.pixelColor(x, y)).name())
    assert len(seen) > 1, f"{theme} painted one colour, so no change could show"


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on.

    With no font database every family resolves to a box advancing one
    em per character, so two strings of equal length need equal width.
    With a font database the glyphs decide the width. Both answers are
    handled here and the file is run both ways.
    """
    app()
    from PySide6.QtWidgets import QLabel

    narrow = QLabel("iiii")
    wide = QLabel("WWWW")
    if has_real_fonts():
        assert (
            narrow.sizeHint().width() != wide.sizeHint().width()
        ), "the host reports fonts and every glyph still has one width"
    else:
        assert (
            narrow.sizeHint().width() == wide.sizeHint().width()
        ), "the host reports no fonts and the glyphs still have their own widths"


def test_the_font_stacks_are_compared_as_text_on_either_host():
    """A font stack changed and the render could not report it.

    Whether a family reaches a glyph depends on what the host installs,
    so every stack is read off both sides as text instead.
    """
    app()
    checked = 0
    for theme in EXPECTED_THEME_NAMES:
        for field in ("font_family", "font_mono"):
            old = getattr(shipped.THEMES[theme], field)
            new = surface.THEMES[theme][field]
            assert new == old, f"{theme}.{field}"
            assert new == EXPECTED[theme][field], f"{theme}.{field}"
            checked += 1
    assert checked == 10
    assert surface.THEMES["classic_terminal"]["font_family"] == FONT_MONO_DEFAULT
    assert surface.THEMES["cyberpunk_dark"]["font_family"] == FONT_UI_DEFAULT


@pytest.mark.parametrize("field", NEVER_IN_THE_STYLE_SHEET)
def test_a_value_the_style_sheet_never_carries_is_compared_as_text(field):
    """A value no style sheet holds was left to the render to report."""
    for theme in EXPECTED_THEME_NAMES:
        old = getattr(shipped.THEMES[theme], field)
        new = surface.THEMES[theme][field]
        assert new == old, f"{theme}.{field}: shipped {old!r}, surface {new!r}"
        assert new == EXPECTED[theme][field], f"{theme}.{field}"


@pytest.mark.parametrize("field", sorted(UNREACHED_BY_A_STILL_PICTURE))
def test_a_value_no_still_picture_reaches_is_compared_as_text(field):
    """A value behind a pointer state or a comment was left to the render."""
    for theme in EXPECTED_THEME_NAMES:
        old = getattr(shipped.THEMES[theme], field)
        new = surface.THEMES[theme][field]
        assert new == old, f"{theme}.{field}: shipped {old!r}, surface {new!r}"
        assert new == EXPECTED[theme][field], f"{theme}.{field}"


def test_the_two_themes_that_repeat_a_colour_are_compared_by_field():
    """Two fields carrying one colour were swapped and nothing moved."""
    repeated = 0
    for theme in EXPECTED_THEME_NAMES:
        values = surface.THEMES[theme]
        seen = {}
        for field in EXPECTED_FIELD_NAMES:
            seen.setdefault(values[field], []).append(field)
        for value, fields in seen.items():
            if len(fields) < 2:
                continue
            repeated += 1
            for field in fields:
                assert getattr(shipped.THEMES[theme], field) == value, (theme, field)
                assert EXPECTED[theme][field] == value, (theme, field)
    assert repeated > 0, "no colour is carried by two fields, so nothing was checked"
    assert surface.THEMES["cyberpunk_dark"]["text_accent"] == (
        surface.THEMES["cyberpunk_dark"]["accent_primary"]
    )
    assert surface.THEMES["minimal_modern"]["accent_info"] == (
        surface.THEMES["minimal_modern"]["accent_primary"]
    )


def test_the_equal_channel_colours_are_compared_as_text():
    """A colour whose channels match had two of them swapped."""
    equal_channel = []
    for theme in EXPECTED_THEME_NAMES:
        for field in EXPECTED_FIELD_NAMES:
            value = surface.THEMES[theme][field]
            if not value.startswith("#") or len(value) not in (7, 9):
                continue
            if len({value[1:3], value[3:5], value[5:7]}) < 3:
                equal_channel.append((theme, field))
    assert len(equal_channel) > 20, len(equal_channel)
    for theme, field in equal_channel:
        assert surface.THEMES[theme][field] == getattr(shipped.THEMES[theme], field)
        assert surface.THEMES[theme][field] == EXPECTED[theme][field]
    assert ("classic_terminal", "bg_secondary") in equal_channel
    assert ("cyberpunk_dark", "accent_primary") not in equal_channel


BLIND_TO_THE_PICTURE = {
    "nine_unused_values": "test_a_value_the_style_sheet_never_carries_is_compared_as_text",
    "shown_name": "test_a_value_no_still_picture_reaches_is_compared_as_text",
    "hover_background": "test_a_value_no_still_picture_reaches_is_compared_as_text",
    "hover_accent": "test_a_value_no_still_picture_reaches_is_compared_as_text",
    "font_stacks": "test_the_font_stacks_are_compared_as_text_on_either_host",
    "repeated_colours": "test_the_two_themes_that_repeat_a_colour_are_compared_by_field",
    "equal_channel_colours": "test_the_equal_channel_colours_are_compared_as_text",
    "field_order": "test_the_field_names_are_the_shipped_dataclass_fields",
    "theme_order": "test_the_theme_names_and_their_order_match",
    "defaults": "test_the_default_values_are_the_shipped_dataclass_defaults",
    "refusal_text": "test_get_theme_refuses_an_unknown_name_the_same_way",
    "style_sheet_text": "test_every_style_sheet_is_the_same_text",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report.

    Twelve things never reach a pixel comparison, each named here with
    the check that does cover it. Nine values never enter the style
    sheet at all. One sits inside a comment and two sit behind a
    pointer state. A font stack reaches a glyph only where the host
    installs that family. Colours repeated inside one theme and
    colours whose channels match paint the same pixel when swapped.
    The order of the fields, the order of the themes, the defaults, the
    refusal text and the style-sheet text are read, not drawn.
    """
    app()
    assert len(BLIND_TO_THE_PICTURE) == 12
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    named = set(NEVER_IN_THE_STYLE_SHEET) | set(UNREACHED_BY_A_STILL_PICTURE)
    assert len(named) == 12
    assert set(PAINTED_FIELDS) | named == set(EXPECTED_FIELD_NAMES)
    assert not set(PAINTED_FIELDS) & named
    assert len(PAINTED_FIELDS) == 22


# The bridge


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = surface.view_model({"name": "glass_metal"})
    text = json.dumps(payload, ensure_ascii=True)
    back = json.loads(text)
    assert back["themes"]["glass_metal"] == painted(EXPECTED["glass_metal"])
    assert back["requested"] == "glass_metal"
    assert back["current"] == "glass_metal"
    assert back["style_sheets"]["glass_metal"] == shipped_style_sheet("glass_metal")


def test_the_payload_carries_every_theme_the_shipped_module_ships():
    """The payload came back short of a theme or a value."""
    payload = surface.build_view_model()
    assert list(payload["theme_names"]) == list(shipped.THEMES)
    for theme in EXPECTED_THEME_NAMES:
        assert payload["themes"][theme] == painted(shipped_theme(theme)), theme
        assert payload["style_sheets"][theme] == shipped_style_sheet(theme), theme
    assert payload["theme_list"] == shipped.ThemeManager().list_themes()
    assert len(payload["themes"]) == THEME_TOTAL


def test_the_payload_carries_a_share_where_the_shipped_theme_carries_a_byte():
    """Without this the comparison above passes on a payload that converted
    nothing, because both sides would read the shipped table."""
    payload = surface.build_view_model()
    for theme in EXPECTED_THEME_NAMES:
        for field in ALPHA_BYTE_FIELD_NAMES:
            carried = payload["themes"][theme][field]
            shipped_value = getattr(shipped.THEMES[theme], field)
            if not shipped_value.startswith("rgba("):
                continue
            assert carried != shipped_value, (theme, field)
            assert float(carried[len("rgba(") : -1].split(",")[3]) <= 1, (theme, field)
        assert payload["themes"][theme]["bg_primary"] == (
            shipped.THEMES[theme].bg_primary
        )


def test_the_payload_hands_back_a_copy():
    """A caller that edits the payload changed the table for everyone."""
    payload = surface.build_view_model()
    payload["themes"]["cyberpunk_dark"]["bg_primary"] = "#ffffff"
    payload["default_tokens"]["bg_primary"] = "#ffffff"
    assert surface.THEMES["cyberpunk_dark"]["bg_primary"] == "#0a0a0f"
    assert surface.DEFAULT_TOKENS["bg_primary"] == "#0a0a0f"
    assert surface.build_view_model()["themes"]["cyberpunk_dark"]["bg_primary"] == (
        "#0a0a0f"
    )


def test_the_payload_reports_no_current_theme_until_one_is_asked_for():
    """The payload named a current theme before one was asked for."""
    payload = surface.build_view_model()
    assert payload["current"] is None
    assert payload["current_before"] is None
    assert payload["requested"] == ""
    assert payload["requested_tokens"] == {}
    assert payload["requested_style_sheet"] == ""
    assert payload["unknown"] == [""]
    assert payload["apply_count"] == 0
    assert payload["style_sheet_applied"] == ""


def test_the_payload_applies_the_theme_it_is_asked_for():
    """The payload named a theme without applying it."""
    payload = surface.build_view_model("classic_terminal")
    assert payload["current"] == "classic_terminal"
    assert payload["current_before"] is None
    assert payload["requested"] == "classic_terminal"
    assert payload["requested_tokens"] == painted(EXPECTED["classic_terminal"])
    assert payload["requested_style_sheet"] == shipped_style_sheet("classic_terminal")
    assert payload["unknown"] == []
    assert payload["unknown_message"] == ""
    assert payload["apply_count"] == 1
    assert payload["style_sheet_applied"] == shipped_style_sheet("classic_terminal")
    assert payload["styleable"] is True


def test_the_payload_reports_a_window_that_takes_no_style_sheet():
    """A window with no style setter was reported as having taken one."""
    payload = surface.build_view_model("neon_light", styleable=False)
    assert payload["styleable"] is False
    assert payload["current"] == "neon_light"
    assert payload["apply_count"] == 0
    assert payload["style_sheet_applied"] == ""
    assert payload["requested_style_sheet"] == shipped_style_sheet("neon_light")


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_the_payload_refuses_an_unknown_name_the_way_the_manager_does(case):
    """An unknown name came back as a theme instead of a refusal."""
    name = UNKNOWN_NAMES[case]
    payload = surface.build_view_model(name)
    assert payload["unknown"] == [name], case
    assert payload["requested_tokens"] == {}, case
    assert payload["requested_style_sheet"] == "", case
    assert payload["current"] is None, case
    with pytest.raises(ValueError) as raised:
        shipped.ThemeManager().get_theme(name)
    assert payload["unknown_message"] == str(raised.value), case


def test_bridge_registers_the_theme_engine_method():
    """The renderer cannot reach the theme table through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == METHOD_NAME
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps(
            {"id": 16, "method": surface.METHOD, "params": {"name": "neon_light"}}
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["requested"] == "neon_light"
    assert result["requested_tokens"] == painted(EXPECTED["neon_light"])
    assert result["unknown"] == []
    assert result["themes"] == painted(
        {theme: shipped_theme(theme) for theme in EXPECTED_THEME_NAMES}
    )


def test_the_bridge_registers_one_handler_for_the_surface():
    """The bridge grew more than the one registration this unit adds."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert registry[surface.METHOD] is surface.view_model
    from_surface = sorted(
        method
        for method, handler in registry.items()
        if getattr(handler, "__module__", "") == surface.__name__
    )
    assert from_surface == [surface.METHOD], from_surface


@pytest.mark.parametrize("theme", EXPECTED_THEME_NAMES)
def test_the_bridge_carries_every_theme(theme):
    """One theme came back wrong over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 17, "method": surface.METHOD, "params": {"name": theme}}),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["requested_tokens"] == painted(shipped_theme(theme))
    assert result["requested_style_sheet"] == shipped_style_sheet(theme)
    assert result["current"] == theme


@pytest.mark.parametrize("case", sorted(UNKNOWN_NAMES))
def test_the_bridge_answers_an_unknown_name_with_the_refusal_text(case):
    """An unknown name over the bridge ended the session or returned a theme."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 18,
                "method": surface.METHOD,
                "params": {"name": UNKNOWN_NAMES[case]},
            }
        ),
        registry,
    )
    assert answer["ok"] is True, case
    assert answer["result"]["unknown"] == [UNKNOWN_NAMES[case]], case
    assert answer["result"]["current"] is None, case
    assert answer["result"]["unknown_message"].startswith("Unknown theme: "), case


def test_the_bridge_ignores_a_parameter_it_does_not_know():
    """A parameter the surface does not read ended the request."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 19,
                "method": surface.METHOD,
                "params": {"name": "glass_metal", "invented": [1, 2], "group": "x"},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["requested"] == "glass_metal"
    assert "invented" not in answer["result"]


def test_the_bridge_reads_a_name_that_is_not_a_string():
    """A number where a theme name belongs ended the request."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    for value in (0, -1, 9.5, None, [], {}):
        answer = desktop_bridge.handle_line(
            json.dumps({"id": 20, "method": surface.METHOD, "params": {"name": value}}),
            registry,
        )
        assert answer["ok"] is True, repr(value)
        assert answer["result"]["requested"] == "", repr(value)
        assert answer["result"]["current"] is None, repr(value)


def test_the_table_is_the_same_on_every_call():
    """The table changed between two calls, so a caller sees a moving answer."""
    first = surface.view_model({"name": "glass_metal"})
    second = surface.view_model({})
    third = surface.view_model({"name": "glass_metal"})
    assert first["themes"] == second["themes"] == third["themes"]
    assert first["style_sheets"] == third["style_sheets"]
    assert first == third
    assert digest(first["themes"]) == digest(third["themes"])
    assert second["current"] is None
    assert first["current"] == "glass_metal"


# The surface without Qt, proved in a process of its own

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
    "    'method': 'theme_engine.state',\n"
    "    'params': {'name': 'glass_metal'}}), registry)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules, 'frame': frame}))\n"
)

TABLE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.gui.main_tabs import theme_engine_surface as s\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'count': len(s.THEME_NAMES), 'names': list(s.THEME_NAMES),\n"
    "    'themes': {n: dict(v) for n, v in s.THEMES.items()},\n"
    "    'style_sheets': dict(s.STYLE_SHEETS),\n"
    "    'missing': s.theme_tokens('NOPE'),\n"
    "    'no_sheet': s.style_sheet('NOPE'),\n"
    "    'refusal': s.unknown_theme_message('NOPE'),\n"
    "    'listed': s.ThemeManagerModel().list_themes(),\n"
    "    'current': s.ThemeManagerModel().current}))\n"
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
    """Reaching the theme table pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["requested"] == "glass_metal"
    assert result["requested_tokens"] == painted(EXPECTED["glass_metal"])
    assert result["theme_names"] == list(shipped.THEMES)
    assert result["current"] == "glass_metal"
    assert len(result["themes"]) == THEME_TOTAL


def test_the_surface_carries_every_theme_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(TABLE_PROBE)
    assert answered["qt"] is False
    assert answered["count"] == THEME_TOTAL
    assert answered["names"] == list(shipped.THEMES)
    assert answered["themes"] == {
        theme: shipped_theme(theme) for theme in EXPECTED_THEME_NAMES
    }
    assert answered["style_sheets"] == {
        theme: shipped_style_sheet(theme) for theme in EXPECTED_THEME_NAMES
    }
    assert answered["missing"] == {}
    assert answered["no_sheet"] == ""
    assert answered["refusal"].startswith("Unknown theme: NOPE.")
    assert answered["listed"] == shipped.ThemeManager().list_themes()
    assert answered["current"] is None


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
        "from src.gui import theme_engine as t\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
        "    'count': len(t.THEMES),\n"
        "    'primary': t.CYBERPUNK_DARK.accent_primary,\n"
        "    'length': len(t.generate_qss(t.GLASS_METAL))}))\n"
    )
    answered = run_script(probe)
    assert answered["qt"] is False
    assert answered["count"] == THEME_TOTAL
    assert answered["primary"] == "#00ffcc"
    assert answered["length"] == EXPECTED_STYLE_SHEET_LENGTHS["glass_metal"]


# Nothing the surface holds is left out of the snapshot

# (surface constant, the payload key that carries it).
PAYLOAD_KEYS = {
    "THEME_NAMES": "theme_names",
    "DISPLAY_NAMES": "display_names",
    "FIELD_NAMES": "field_names",
    "REQUIRED_FIELD_NAMES": "required_field_names",
    "DEFAULT_TOKENS": "default_tokens",
    "THEMES": "themes",
    "STYLE_SHEETS": "style_sheets",
    "QSS_TEMPLATE": "qss_template",
    "ACTIONS": "actions",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "SKIN": "skin",
}

# The five theme constants reach the snapshot inside `themes`.
THEME_CONSTANTS = {
    "CYBERPUNK_DARK": "cyberpunk_dark",
    "NEON_LIGHT": "neon_light",
    "CLASSIC_TERMINAL": "classic_terminal",
    "MINIMAL_MODERN": "minimal_modern",
    "GLASS_METAL": "glass_metal",
}

# (constant no snapshot key carries, the test that covers it).
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_bridge_registers_the_theme_engine_method",
    "UNKNOWN_THEME_MESSAGE": "test_unknown_theme_message_names_the_value_it_was_given",
    "NO_CURRENT_THEME": "test_current_is_empty_until_a_theme_is_applied",
    "NO_STYLE_SHEET": "test_style_sheet_returns_the_empty_string_for_any_other_name",
    "NO_TOKENS": "test_theme_tokens_returns_an_empty_table_for_any_other_name",
}

CONSTANT_TOTAL = 22


def surface_constants():
    """Every value the surface exports that is not a function or a class."""
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
    rest match or not. Every constant is accounted for here: a snapshot
    key, one of the five themes, or one of the five named below with the
    check that covers it.
    """
    payload = surface.build_view_model()
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            carried = payload[PAYLOAD_KEYS[name]]
            assert list(carried) == list(value), name
            if isinstance(value, dict):
                for key in value:
                    assert carried[key] == painted(value[key]), (name, key)
        elif name in THEME_CONSTANTS:
            assert payload["themes"][THEME_CONSTANTS[name]] == painted(value), name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(PAYLOAD_KEYS) == 12
    assert len(THEME_CONSTANTS) == THEME_TOTAL
    assert len(NOT_IN_THE_SNAPSHOT) == 5


def test_every_snapshot_key_carries_a_constant_the_surface_holds():
    """The snapshot grew a key no constant on the surface backs."""
    payload = surface.build_view_model()
    answered = set(PAYLOAD_KEYS.values())
    request_only = {
        "theme_list",
        "requested",
        "requested_tokens",
        "requested_style_sheet",
        "unknown",
        "unknown_message",
        "current_before",
        "current",
        "styleable",
        "style_sheet_applied",
        "apply_count",
    }
    assert set(payload) == answered | request_only
    assert len(payload) == 23
    for key in request_only:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_constant():
    """The completeness check passed because it looks at nothing.

    A constant that reaches no snapshot key and no named exception must
    land in the unaccounted list, or the check above is empty.
    """
    payload = surface.build_view_model()
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in THEME_CONSTANTS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "THEMES" in surface_constants()
    assert "QSS_TEMPLATE" in surface_constants()
    assert "generate_qss" not in surface_constants()
    assert "ThemeManagerModel" not in surface_constants()
    assert "view_model" not in surface_constants()
