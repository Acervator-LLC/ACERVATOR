"""theme_engine_surface.py -- the five visual themes and the style sheet each one makes.

Describes the theme table the whole window draws from. Five themes
carry 61 named values each: two names, 50 colours, two font stacks,
four text sizes and three corner roundings. Six of the colours are the
main-window tab grounds and the text each ground carries. A theme that
does not name a value takes the default written in ``DEFAULT_TOKENS``.

``generate_qss`` turns one theme into the style-sheet text the window
applies. The template is written out here in full, so the two sides
build the same 7670 characters from their own copies of the values.

``ThemeManagerModel`` holds the selected theme. ``list_themes``
returns the name and display name of each. ``get_theme`` returns one
theme's values and raises for a name the table does not hold.
``get_qss`` returns one theme's style-sheet text. ``apply_theme``
hands that text to an application object that accepts one, and
records the theme as current. ``current`` is ``None`` until a theme
is applied.

``src.core.desktop_bridge`` registers ``view_model`` as the handler
for the ``theme_engine.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather
than read from ``src.gui.theme_engine``, so a value changed on one
side alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

from ..color_alpha import css_colours

METHOD = "theme_engine.state"

REQUIRED_FIELD_NAMES = ("name", "display_name")

DEFAULT_TOKENS: dict[str, str] = {
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
    "font_family": "'Rajdhani', 'Orbitron', 'Segoe UI', sans-serif",
    "font_mono": "'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
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

FIELD_NAMES = REQUIRED_FIELD_NAMES + tuple(DEFAULT_TOKENS)


def build_theme(name: str, display_name: str, **named: str) -> dict[str, str]:
    """One theme's 61 values: its two names, then a default for each it does not name.

    Field order follows the dataclass the surface replaces, so the two
    sides hand the frontend their values in one order.
    """
    return dict(name=name, display_name=display_name, **{**DEFAULT_TOKENS, **named})


CYBERPUNK_DARK: dict[str, str] = build_theme(
    name="cyberpunk_dark",
    display_name="Cyberpunk Dark",
)

NEON_LIGHT: dict[str, str] = build_theme(
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
)

CLASSIC_TERMINAL: dict[str, str] = build_theme(
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
    font_family="'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
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
)

MINIMAL_MODERN: dict[str, str] = build_theme(
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
)

GLASS_METAL: dict[str, str] = build_theme(
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
)

THEMES: dict[str, dict[str, str]] = {
    theme["name"]: theme
    for theme in (
        CYBERPUNK_DARK,
        NEON_LIGHT,
        CLASSIC_TERMINAL,
        MINIMAL_MODERN,
        GLASS_METAL,
    )
}

THEME_NAMES = tuple(THEMES)

DISPLAY_NAMES: dict[str, str] = {
    name: theme["display_name"] for name, theme in THEMES.items()
}

QSS_TEMPLATE = """
/* ===== Acervator — {display_name} ===== */

/* --- Global --- */
QWidget {{
    background-color: {bg_primary};
    color: {text_primary};
    font-family: {font_family};
    font-size: {font_size};
    selection-background-color: {accent_primary};
    selection-color: {bg_primary};
}}

QMainWindow {{
    background-color: {bg_primary};
}}

/* --- Tab widget --- */
QTabWidget::pane {{
    border: 1px solid {border_primary};
    border-radius: {radius_md};
    background-color: {bg_secondary};
}}

QTabBar::tab {{
    background-color: {bg_tertiary};
    color: {text_secondary};
    border: 1px solid {border_secondary};
    border-bottom: none;
    padding: 8px 14px;
    margin-right: 2px;
    border-top-left-radius: {radius_sm};
    border-top-right-radius: {radius_sm};
}}

QTabBar QToolButton {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border_secondary};
    border-radius: 3px;
    padding: 2px 4px;
}}
QTabBar QToolButton:hover {{
    background-color: {bg_hover};
    color: {text_accent};
}}

QTabBar::tab:selected {{
    background-color: {bg_card};
    color: {text_accent};
    border-bottom: 2px solid {accent_primary};
}}

QTabBar::tab:hover {{
    background-color: {bg_hover};
    color: {text_primary};
}}

/* --- Main-window tab grounds --- */
QTabBar#mainWindowTabBar {{
    qproperty-tab_black_bg: {tab_black_bg};
    qproperty-tab_black_text: {tab_black_text};
    qproperty-tab_white_bg: {tab_white_bg};
    qproperty-tab_white_text: {tab_white_text};
    qproperty-tab_gold_bg: {tab_gold_bg};
    qproperty-tab_gold_text: {tab_gold_text};
}}

/* --- Cards / Frames --- */
QFrame[frameShape="6"] {{
    background-color: {bg_card};
    border: 1px solid {border_primary};
    border-radius: {radius_md};
    padding: 12px;
}}

QGroupBox {{
    background-color: {bg_card};
    border: 1px solid {border_primary};
    border-radius: {radius_md};
    margin-top: 16px;
    padding-top: 24px;
    font-weight: bold;
    color: {text_accent};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    color: {text_accent};
}}

/* --- Buttons --- */
QPushButton {{
    background-color: {bg_tertiary};
    color: {text_primary};
    border: 1px solid {border_primary};
    border-radius: {radius_sm};
    padding: 8px 20px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: {bg_hover};
    border-color: {accent_primary};
    color: {text_accent};
}}

QPushButton:pressed {{
    background-color: {accent_primary};
    color: {bg_primary};
}}

QPushButton[accent="true"] {{
    background-color: {accent_primary};
    color: {bg_primary};
    border: none;
}}

QPushButton[accent="true"]:hover {{
    background-color: {accent_secondary};
}}

QPushButton[danger="true"] {{
    border-color: {accent_danger};
    color: {accent_danger};
}}

/* --- Inputs --- */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {bg_input};
    color: {text_primary};
    border: 1px solid {border_primary};
    border-radius: {radius_sm};
    padding: 8px 12px;
}}

/* ======================================================================
   GLOBAL FOCUS INDICATOR — WCAG 2.2 SC 2.4.7
   ======================================================================
   Applies to every focusable widget. Visible across dark surfaces.
   Grounded in R65 GDG; source WCAG 2.2 §2.4.7 Focus Visible, SC level AA.
   Token values: FOCUS_RING_WIDTH=2px, FOCUS_RING_COLOR=OUTLINE_STRONG
   (7.79:1 on SURFACE_0 — well above the 3:1 floor).
   QSS note: Qt accepts `:focus` on all widgets; `outline` is supported
   for QLineEdit/QAbstractButton/QComboBox and cascades through stylesheet.
*/

*:focus {{
    outline: 2px solid {border_primary};
    outline-offset: 2px;
}}

QPushButton:focus, QToolButton:focus, QCheckBox:focus, QRadioButton:focus,
QComboBox:focus, QTabBar::tab:focus, QListView:focus, QTreeView:focus,
QTableView:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus,
QTextEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus, QSlider:focus {{
    outline: 2px solid {border_primary};
    outline-offset: 2px;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {accent_primary};
    background-color: {bg_secondary};
}}

QComboBox {{
    background-color: {bg_input};
    color: {text_primary};
    border: 1px solid {border_primary};
    border-radius: {radius_sm};
    padding: 8px 12px;
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border_primary};
    selection-background-color: {accent_primary};
    selection-color: {bg_primary};
}}

/* --- Labels --- */
QLabel {{
    color: {text_primary};
    background: transparent;
}}

QLabel[heading="true"] {{
    font-size: {font_size_title};
    font-weight: bold;
    color: {text_accent};
}}

QLabel[muted="true"] {{
    color: {text_muted};
    font-size: {font_size_small};
}}

/* --- Tables --- */
QTableWidget, QTableView {{
    background-color: {bg_secondary};
    alternate-background-color: {bg_tertiary};
    gridline-color: {border_secondary};
    border: 1px solid {border_primary};
    border-radius: {radius_md};
    selection-background-color: {bg_selected};
}}

QHeaderView::section {{
    background-color: {bg_card};
    color: {text_accent};
    padding: 8px;
    border: none;
    border-bottom: 2px solid {accent_primary};
    font-weight: bold;
}}

/* --- Scroll bars --- */
QScrollBar:vertical {{
    background-color: {scrollbar_bg};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background-color: {scrollbar_handle};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {accent_primary};
}}

QScrollBar:horizontal {{
    background-color: {scrollbar_bg};
    height: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal {{
    background-color: {scrollbar_handle};
    border-radius: 5px;
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}

/* --- Progress bars --- */
QProgressBar {{
    background-color: {bg_input};
    border: 1px solid {border_primary};
    border-radius: {radius_sm};
    text-align: center;
    color: {text_primary};
}}

QProgressBar::chunk {{
    background-color: {accent_primary};
    border-radius: {radius_sm};
}}

/* --- Sliders --- */
QSlider::groove:horizontal {{
    background-color: {bg_input};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background-color: {accent_primary};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}

/* --- Menu --- */
QMenuBar {{
    background-color: {bg_secondary};
    color: {text_primary};
    border-bottom: 1px solid {border_primary};
}}

QMenuBar::item:selected {{
    background-color: {bg_hover};
    color: {text_accent};
}}

QMenu {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border_primary};
}}

QMenu::item:selected {{
    background-color: {accent_primary};
    color: {bg_primary};
}}

/* --- Status bar --- */
QStatusBar {{
    background-color: {bg_secondary};
    color: {text_secondary};
    border-top: 1px solid {border_primary};
}}

/* --- Tool tips --- */
QToolTip {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {accent_primary};
    padding: 6px;
    border-radius: {radius_sm};
}}

/* --- Splitter --- */
QSplitter::handle {{
    background-color: {border_primary};
    border-radius: 2px;
}}

QSplitter::handle:horizontal {{
    width: 5px;
    background-color: {border_primary};
    border-left:  1px solid rgba(0,255,238,0.10);
    border-right: 1px solid rgba(0,255,238,0.10);
}}

QSplitter::handle:vertical {{
    height: 5px;
    background-color: {border_primary};
    border-top:    1px solid rgba(0,255,238,0.10);
    border-bottom: 1px solid rgba(0,255,238,0.10);
}}

QSplitter::handle:hover {{
    background-color: {accent_primary};
}}

QSplitter::handle:pressed {{
    background-color: {accent_primary};
    opacity: 0.85;
}}

/* --- Check / Radio --- */
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {border_primary};
    border-radius: 3px;
    background-color: {bg_input};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {accent_primary};
    border-color: {accent_primary};
}}

QRadioButton::indicator {{
    border-radius: 9px;
}}
"""


def generate_qss(tokens: dict) -> str:
    """The complete style-sheet text one theme's values produce."""
    return QSS_TEMPLATE.format(**tokens)


STYLE_SHEETS: dict[str, str] = {
    name: generate_qss(theme) for name, theme in THEMES.items()
}

UNKNOWN_THEME_MESSAGE = "Unknown theme: {name}. Available: {available}"

NO_CURRENT_THEME = None
NO_STYLE_SHEET = ""
NO_TOKENS: dict[str, str] = {}

ACTIONS: dict[str, str] = {}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
SKIN: dict[str, str] = {}


def has_theme(name: str) -> bool:
    """Whether the table holds a theme under `name`."""
    return name in THEMES


def unknown_theme_message(name: Any) -> str:
    """The refusal text `get_theme` raises for a name the table lacks."""
    return UNKNOWN_THEME_MESSAGE.format(name=name, available=list(THEME_NAMES))


def theme_tokens(name: str) -> dict:
    """One theme's 34 values, or an empty table for any other name."""
    return dict(THEMES.get(name, NO_TOKENS))


def style_sheet(name: str) -> str:
    """One theme's style-sheet text, or the empty string for any other name."""
    return STYLE_SHEETS.get(name, NO_STYLE_SHEET)


def requested_theme(name: Any) -> str:
    """The theme name a caller asked for, and the empty string for anything else.

    A caller sending a number, a list or nothing asks for no theme
    rather than for the text of that value.
    """
    if isinstance(name, str):
        return name
    return ""


class StyleSheetSink:
    """An application stand-in that accepts a style sheet and keeps the last one.

    `ThemeManagerModel.apply_theme` probes its target for
    ``setStyleSheet`` exactly as the module it replaces does, so the
    sink carries that name and records what the window would receive.
    """

    def __init__(self) -> None:
        self.style_sheet = NO_STYLE_SHEET
        self.call_count = 0

    def setStyleSheet(self, qss: str) -> None:
        self.style_sheet = qss
        self.call_count += 1


class ThemeManagerModel:
    """Holds the selected theme and the style-sheet text each theme makes."""

    def __init__(self) -> None:
        self._current: Optional[dict] = NO_CURRENT_THEME

    def list_themes(self) -> list[dict[str, str]]:
        """Every theme as [{name, display_name}, ...]."""
        return [
            {"name": theme["name"], "display_name": theme["display_name"]}
            for theme in THEMES.values()
        ]

    def get_theme(self, name: str) -> dict:
        """One theme's values by name; raises ValueError for any other name."""
        if not has_theme(name):
            raise ValueError(unknown_theme_message(name))
        return THEMES[name]

    def get_qss(self, name: str) -> str:
        """The style-sheet text for the named theme."""
        return generate_qss(self.get_theme(name))

    def apply_theme(self, name: str, app: object) -> None:
        """Hand the named theme's style sheet to `app` and record it as current.

        `app` is left untyped because the target is the running
        application object. A target with no ``setStyleSheet`` still
        becomes the current theme.
        """
        qss = self.get_qss(name)
        self._current = self.get_theme(name)
        if hasattr(app, "setStyleSheet"):
            app.setStyleSheet(qss)

    @property
    def current(self) -> Optional[dict]:
        return self._current


def build_view_model(name: Any = None, styleable: Any = True) -> dict:
    """Return every theme, every value and every style sheet as one dict.

    `name` carries the theme a caller asked for. A name the table does
    not hold comes back under `unknown` with the refusal text the
    module it replaces raises, and no theme becomes current.
    `styleable` says whether the target application accepts a style
    sheet; a target that does not still records the theme as current.

    The theme table itself carries the alpha byte Qt reads. The payload
    leaves under `src.gui.color_alpha.css_colours`, so the renderer
    receives the share a browser reads and no colour is copied twice.
    """
    asked = requested_theme(name)
    known = has_theme(asked)
    takes_style = bool(styleable)
    manager = ThemeManagerModel()
    before = manager.current
    sink = StyleSheetSink() if takes_style else object()
    if known:
        manager.apply_theme(asked, sink)
    current = manager.current
    payload = {
        "theme_names": list(THEME_NAMES),
        "display_names": dict(DISPLAY_NAMES),
        "field_names": list(FIELD_NAMES),
        "required_field_names": list(REQUIRED_FIELD_NAMES),
        "default_tokens": dict(DEFAULT_TOKENS),
        "themes": {found: dict(theme) for found, theme in THEMES.items()},
        "theme_list": manager.list_themes(),
        "style_sheets": dict(STYLE_SHEETS),
        "qss_template": QSS_TEMPLATE,
        "requested": asked,
        "requested_tokens": theme_tokens(asked),
        "requested_style_sheet": style_sheet(asked),
        "unknown": [] if known else [asked],
        "unknown_message": "" if known else unknown_theme_message(asked),
        "current_before": before,
        "current": current["name"] if current else NO_CURRENT_THEME,
        "styleable": takes_style,
        "style_sheet_applied": getattr(sink, "style_sheet", NO_STYLE_SHEET),
        "apply_count": getattr(sink, "call_count", 0),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "skin": dict(SKIN),
    }
    return css_colours(payload)


def view_model(params: dict) -> dict:
    """Bridge handler for ``theme_engine.state``.

    Reads ``name`` and ``styleable`` from the request parameters. The
    theme table is the same on every call, so there is no state to
    reset.
    """
    return build_view_model(params.get("name"), params.get("styleable", True))
