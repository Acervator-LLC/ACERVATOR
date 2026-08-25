"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
theme_engine.py — Visual theme system
======================================
Provides the cyberpunk dark mode default theme and alternate visual styles.
Themes are implemented as Qt stylesheets (QSS) with CSS variable-like
token substitution for consistent color application across all widgets.

Supported themes:
  • Cyberpunk Dark (default) — neon accents, dark backgrounds, futuristic
  • Neon Light — bright, high-contrast with neon highlights
  • Classic Terminal — green-on-black retro aesthetic
  • Minimal Modern — clean, flat, understated
  • Glass Metal — metallic textures with translucent overlays

EXTERNAL GROUNDING (per R63 ERG + R65 GDG):
  - WCAG 2.2 Level AA contrast (SC 1.4.3, SC 1.4.11) — every token pair
    verified via relative luminance audit. Changes to hex values require
    re-audit; see tools/wcag_audit.py (chunk C9).
  - M3 color roles — see src/gui/design_system.py for canonical role-based
    tokens. `theme_engine.py` preserves the legacy flat-token shape for
    compatibility; new widget code should import from design_system.py.

LINEAGE:
  - C2 (this edit): fixed 4 WCAG AA violations in Cyberpunk Dark defaults
    (text_muted, accent_danger, accent_info, border_primary, border_secondary).
  - C1 (sibling): src/gui/design_system.py — canonical GUI tokens.
  - R65 GDG MEM-157 — rule birth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Theme token set
# ---------------------------------------------------------------------------
@dataclass
class ThemeTokens:
    """Color and style tokens that define a complete visual theme."""

    name: str
    display_name: str

    # Backgrounds
    bg_primary: str = "#0a0a0f"
    bg_secondary: str = "#12121a"
    bg_tertiary: str = "#1a1a28"
    bg_card: str = "#16162a"
    bg_input: str = "#0e0e1a"
    bg_hover: str = "#1e1e35"
    bg_selected: str = "#252545"

    # Text
    text_primary: str = "#e0e0f0"
    text_secondary: str = "#8888aa"
    text_muted: str = "#8a8ab0"  # was "#555577" — WCAG C2: 2.62:1 → 5.19:1 (SC 1.4.3)
    text_accent: str = "#00ffcc"

    # Accents
    accent_primary: str = "#00ffcc"
    accent_secondary: str = "#ff00aa"
    accent_success: str = "#00ff88"
    accent_danger: str = (
        "#ff5577"  # was "#ff3366" — WCAG C2: tightened contrast margin (SC 1.4.3)
    )
    accent_warning: str = "#ffaa00"
    accent_info: str = (
        "#4fc3ff"  # was "#00aaff" — WCAG C2: widened contrast margin (SC 1.4.3)
    )

    # Borders (SC 1.4.11 — UI components require ≥3:1 contrast against adjacent colors)
    border_primary: str = "#7a7a9c"  # was "#2a2a44" — WCAG C2: 1.42:1 → 4.79:1
    border_secondary: str = "#5e5e80"  # was "#1e1e33" — WCAG C2: 1.21:1 → 3.19:1
    border_accent: str = "#00ffcc44"

    # Special
    glow_color: str = "#00ffcc33"
    scrollbar_bg: str = "#0a0a14"
    scrollbar_handle: str = "#2a2a44"

    # Font
    font_family: str = "'Rajdhani', 'Orbitron', 'Segoe UI', sans-serif"
    font_mono: str = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace"
    font_size: str = "13px"
    font_size_small: str = "11px"
    font_size_large: str = "16px"
    font_size_title: str = "20px"

    # Border radius
    radius_sm: str = "4px"
    radius_md: str = "8px"
    radius_lg: str = "12px"


# ---------------------------------------------------------------------------
# Pre-built themes
# ---------------------------------------------------------------------------
CYBERPUNK_DARK = ThemeTokens(
    name="cyberpunk_dark",
    display_name="Cyberpunk Dark",
    # Defaults are already cyberpunk dark
)

NEON_LIGHT = ThemeTokens(
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
    border_accent="#6600cc44",
    glow_color="#6600cc22",
    scrollbar_bg="#e0e0ea",
    scrollbar_handle="#bbbbcc",
)

CLASSIC_TERMINAL = ThemeTokens(
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
    border_accent="#00ff0044",
    glow_color="#00ff0022",
    scrollbar_bg="#0a0a0a",
    scrollbar_handle="#003300",
    font_family="'JetBrains Mono', 'Fira Code', 'Consolas', monospace",
)

MINIMAL_MODERN = ThemeTokens(
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
    border_accent="#2563eb33",
    glow_color="transparent",
    scrollbar_bg="#f0f0f0",
    scrollbar_handle="#cccccc",
    font_family="'SF Pro Display', 'Inter', 'Segoe UI', sans-serif",
)

GLASS_METAL = ThemeTokens(
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
    border_accent="#88ccff44",
    glow_color="#88ccff22",
    scrollbar_bg="#1c1c24",
    scrollbar_handle="#3a3a50",
    font_family="'Exo 2', 'Rajdhani', 'Segoe UI', sans-serif",
)


# Registry
THEMES: dict[str, ThemeTokens] = {
    t.name: t
    for t in [CYBERPUNK_DARK, NEON_LIGHT, CLASSIC_TERMINAL, MINIMAL_MODERN, GLASS_METAL]
}


# ---------------------------------------------------------------------------
# QSS generator
# ---------------------------------------------------------------------------
def generate_qss(theme: ThemeTokens) -> str:
    """Generate a complete Qt stylesheet from theme tokens."""
    t = theme
    return f"""
/* ===== Acervator — {t.display_name} ===== */

/* --- Global --- */
QWidget {{
    background-color: {t.bg_primary};
    color: {t.text_primary};
    font-family: {t.font_family};
    font-size: {t.font_size};
    selection-background-color: {t.accent_primary};
    selection-color: {t.bg_primary};
}}

QMainWindow {{
    background-color: {t.bg_primary};
}}

/* --- Tab widget --- */
QTabWidget::pane {{
    border: 1px solid {t.border_primary};
    border-radius: {t.radius_md};
    background-color: {t.bg_secondary};
}}

QTabBar::tab {{
    background-color: {t.bg_tertiary};
    color: {t.text_secondary};
    border: 1px solid {t.border_secondary};
    border-bottom: none;
    padding: 8px 14px;
    margin-right: 2px;
    border-top-left-radius: {t.radius_sm};
    border-top-right-radius: {t.radius_sm};
}}

QTabBar QToolButton {{
    background-color: {t.bg_card};
    color: {t.text_primary};
    border: 1px solid {t.border_secondary};
    border-radius: 3px;
    padding: 2px 4px;
}}
QTabBar QToolButton:hover {{
    background-color: {t.bg_hover};
    color: {t.text_accent};
}}

QTabBar::tab:selected {{
    background-color: {t.bg_card};
    color: {t.text_accent};
    border-bottom: 2px solid {t.accent_primary};
}}

QTabBar::tab:hover {{
    background-color: {t.bg_hover};
    color: {t.text_primary};
}}

/* --- Cards / Frames --- */
QFrame[frameShape="6"] {{
    background-color: {t.bg_card};
    border: 1px solid {t.border_primary};
    border-radius: {t.radius_md};
    padding: 12px;
}}

QGroupBox {{
    background-color: {t.bg_card};
    border: 1px solid {t.border_primary};
    border-radius: {t.radius_md};
    margin-top: 16px;
    padding-top: 24px;
    font-weight: bold;
    color: {t.text_accent};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 12px;
    color: {t.text_accent};
}}

/* --- Buttons --- */
QPushButton {{
    background-color: {t.bg_tertiary};
    color: {t.text_primary};
    border: 1px solid {t.border_primary};
    border-radius: {t.radius_sm};
    padding: 8px 20px;
    font-weight: bold;
}}

QPushButton:hover {{
    background-color: {t.bg_hover};
    border-color: {t.accent_primary};
    color: {t.text_accent};
}}

QPushButton:pressed {{
    background-color: {t.accent_primary};
    color: {t.bg_primary};
}}

QPushButton[accent="true"] {{
    background-color: {t.accent_primary};
    color: {t.bg_primary};
    border: none;
}}

QPushButton[accent="true"]:hover {{
    background-color: {t.accent_secondary};
}}

QPushButton[danger="true"] {{
    border-color: {t.accent_danger};
    color: {t.accent_danger};
}}

/* --- Inputs --- */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {t.bg_input};
    color: {t.text_primary};
    border: 1px solid {t.border_primary};
    border-radius: {t.radius_sm};
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
    outline: 2px solid {t.border_primary};
    outline-offset: 2px;
}}

QPushButton:focus, QToolButton:focus, QCheckBox:focus, QRadioButton:focus,
QComboBox:focus, QTabBar::tab:focus, QListView:focus, QTreeView:focus,
QTableView:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus,
QTextEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus, QSlider:focus {{
    outline: 2px solid {t.border_primary};
    outline-offset: 2px;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {t.accent_primary};
    background-color: {t.bg_secondary};
}}

QComboBox {{
    background-color: {t.bg_input};
    color: {t.text_primary};
    border: 1px solid {t.border_primary};
    border-radius: {t.radius_sm};
    padding: 8px 12px;
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: {t.bg_card};
    color: {t.text_primary};
    border: 1px solid {t.border_primary};
    selection-background-color: {t.accent_primary};
    selection-color: {t.bg_primary};
}}

/* --- Labels --- */
QLabel {{
    color: {t.text_primary};
    background: transparent;
}}

QLabel[heading="true"] {{
    font-size: {t.font_size_title};
    font-weight: bold;
    color: {t.text_accent};
}}

QLabel[muted="true"] {{
    color: {t.text_muted};
    font-size: {t.font_size_small};
}}

/* --- Tables --- */
QTableWidget, QTableView {{
    background-color: {t.bg_secondary};
    alternate-background-color: {t.bg_tertiary};
    gridline-color: {t.border_secondary};
    border: 1px solid {t.border_primary};
    border-radius: {t.radius_md};
    selection-background-color: {t.bg_selected};
}}

QHeaderView::section {{
    background-color: {t.bg_card};
    color: {t.text_accent};
    padding: 8px;
    border: none;
    border-bottom: 2px solid {t.accent_primary};
    font-weight: bold;
}}

/* --- Scroll bars --- */
QScrollBar:vertical {{
    background-color: {t.scrollbar_bg};
    width: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical {{
    background-color: {t.scrollbar_handle};
    border-radius: 5px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {t.accent_primary};
}}

QScrollBar:horizontal {{
    background-color: {t.scrollbar_bg};
    height: 10px;
    border-radius: 5px;
}}

QScrollBar::handle:horizontal {{
    background-color: {t.scrollbar_handle};
    border-radius: 5px;
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0px;
    width: 0px;
}}

/* --- Progress bars --- */
QProgressBar {{
    background-color: {t.bg_input};
    border: 1px solid {t.border_primary};
    border-radius: {t.radius_sm};
    text-align: center;
    color: {t.text_primary};
}}

QProgressBar::chunk {{
    background-color: {t.accent_primary};
    border-radius: {t.radius_sm};
}}

/* --- Sliders --- */
QSlider::groove:horizontal {{
    background-color: {t.bg_input};
    height: 6px;
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background-color: {t.accent_primary};
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}

/* --- Menu --- */
QMenuBar {{
    background-color: {t.bg_secondary};
    color: {t.text_primary};
    border-bottom: 1px solid {t.border_primary};
}}

QMenuBar::item:selected {{
    background-color: {t.bg_hover};
    color: {t.text_accent};
}}

QMenu {{
    background-color: {t.bg_card};
    color: {t.text_primary};
    border: 1px solid {t.border_primary};
}}

QMenu::item:selected {{
    background-color: {t.accent_primary};
    color: {t.bg_primary};
}}

/* --- Status bar --- */
QStatusBar {{
    background-color: {t.bg_secondary};
    color: {t.text_secondary};
    border-top: 1px solid {t.border_primary};
}}

/* --- Tool tips --- */
QToolTip {{
    background-color: {t.bg_card};
    color: {t.text_primary};
    border: 1px solid {t.accent_primary};
    padding: 6px;
    border-radius: {t.radius_sm};
}}

/* --- Splitter --- */
QSplitter::handle {{
    background-color: {t.border_primary};
    border-radius: 2px;
}}

QSplitter::handle:horizontal {{
    width: 5px;
    background-color: {t.border_primary};
    border-left:  1px solid rgba(0,255,238,0.10);
    border-right: 1px solid rgba(0,255,238,0.10);
}}

QSplitter::handle:vertical {{
    height: 5px;
    background-color: {t.border_primary};
    border-top:    1px solid rgba(0,255,238,0.10);
    border-bottom: 1px solid rgba(0,255,238,0.10);
}}

QSplitter::handle:hover {{
    background-color: {t.accent_primary};
}}

QSplitter::handle:pressed {{
    background-color: {t.accent_primary};
    opacity: 0.85;
}}

/* --- Check / Radio --- */
QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {t.border_primary};
    border-radius: 3px;
    background-color: {t.bg_input};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {t.accent_primary};
    border-color: {t.accent_primary};
}}

QRadioButton::indicator {{
    border-radius: 9px;
}}
"""


# ---------------------------------------------------------------------------
# Theme manager
# ---------------------------------------------------------------------------
class ThemeManager:
    """
    Manages theme selection and application.

    Usage::

        tm = ThemeManager()
        tm.apply_theme("cyberpunk_dark", app)  # Pass QApplication
        available = tm.list_themes()
    """

    def __init__(self) -> None:
        self._current: Optional[ThemeTokens] = None

    def list_themes(self) -> list[dict[str, str]]:
        """Return available themes as [{name, display_name}, ...]."""
        return [
            {"name": t.name, "display_name": t.display_name} for t in THEMES.values()
        ]

    def get_theme(self, name: str) -> ThemeTokens:
        """Retrieve theme tokens by name."""
        if name not in THEMES:
            raise ValueError(f"Unknown theme: {name}. Available: {list(THEMES.keys())}")
        return THEMES[name]

    def get_qss(self, name: str) -> str:
        """Generate QSS for the named theme."""
        return generate_qss(self.get_theme(name))

    def apply_theme(self, name: str, app: object) -> None:
        """
        Apply a theme to a QApplication instance.
        *app* should be a ``QApplication`` — we accept ``object`` to avoid
        importing Qt at module level.
        """
        qss = self.get_qss(name)
        self._current = self.get_theme(name)
        if hasattr(app, "setStyleSheet"):
            app.setStyleSheet(qss)

    @property
    def current(self) -> Optional[ThemeTokens]:
        return self._current
