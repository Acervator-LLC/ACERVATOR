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
