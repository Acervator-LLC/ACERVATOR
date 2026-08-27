"""Colour palettes for the bot visualizer widgets.

``TIER_PALETTES`` keys off a bot's target balance; ``THEMES`` holds the
four canvas themes every visualizer widget paints from.
"""

from __future__ import annotations

try:
    from PySide6.QtGui import QColor

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # -------------------------------------------------------------------
    # Visual Themes
    # -------------------------------------------------------------------
    # ─────────────────────────────────────────────────────────────────
    # Tier palettes (Scope A locust refresh, post-Session-26).
    #
    # Grounded in sadp/VISUAL_CRAFT.md:
    #   - Pillar 1 (DawnBringer): limited palettes produce consistency;
    #     hue-shifted ramps, NOT luminance-only, are the highest-value
    #     lesson in small-palette work. Shadow shifts toward cool/warm
    #     opposite of the light direction, not just darker base.
    #   - Pillar 5 (ACRV tier hierarchy): four tiers each carry a visual
    #     family so bot cards differentiate by a glance, not just by
    #     reading the symbol label.
    #
    # Tier assignment is by target_balance bucket (operator can override
    # later). Harvest: <$100, Great: <$1k, Bumper: <$10k, Ekthelius: >=$10k.
    #
    # Each tier's `base` is the main insect-body tone; `shadow` and
    # `highlight` are the hue-shifted ramp stops; `glow` is the ambient
    # aura color. `accent` is the wing-vein / detail stroke color.
    # ─────────────────────────────────────────────────────────────────
    TIER_PALETTES = {
        "harvest": {
            # DB32-family green (base) with cool-blue shadow, warm-yellow
            # highlight. The workaday locust — most bots live here.
            "name": "Harvest",
            "base": QColor(80, 180, 110),
            "shadow": QColor(40, 100, 140),  # hue-shifted toward blue/cool
            "highlight": QColor(180, 220, 130),  # hue-shifted toward yellow/warm
            "accent": QColor(210, 240, 160),
            "glow": QColor(120, 220, 150),
        },
        "great": {
            # Cyan-jade tier — cleaner, cooler, slightly richer than Harvest.
            # Hue-shift: shadow toward deep teal, highlight toward pale mint.
            "name": "Great",
            "base": QColor(60, 200, 180),
            "shadow": QColor(20, 100, 130),
            "highlight": QColor(150, 240, 210),
            "accent": QColor(200, 250, 230),
            "glow": QColor(90, 230, 200),
        },
        "bumper": {
            # Amber-rust tier — cool-to-warm shift per VISUAL_CRAFT Pillar 5.
            # Shadow toward violet (complementary of amber), highlight toward
            # pale gold.
            "name": "Bumper",
            "base": QColor(220, 150, 70),
            "shadow": QColor(110, 60, 120),
            "highlight": QColor(250, 220, 140),
            "accent": QColor(255, 235, 170),
            "glow": QColor(240, 180, 90),
        },
        "ekthelius": {
            # Gold + purple, custom per VISUAL_CRAFT Pillar 5 — rare
            # trophy tier. Shadow deep indigo, highlight pale gold.
            "name": "Ekthelius",
            "base": QColor(200, 170, 80),
            "shadow": QColor(70, 40, 130),
            "highlight": QColor(250, 230, 160),
            "accent": QColor(220, 180, 255),
            "glow": QColor(230, 200, 120),
        },
    }

    def _tier_from_target_balance(target_usd: float) -> str:
        """Map a bot's target balance to a tier palette key.
        Thresholds are a first-pass mapping; operator may override later."""
        if target_usd < 100:
            return "harvest"
        if target_usd < 1_000:
            return "great"
        if target_usd < 10_000:
            return "bumper"
        return "ekthelius"

    THEMES = {
        "nebula": {
            "name": "Nebula",
            "bg": QColor(8, 4, 20),
            "accent": QColor(120, 80, 255),
            "accent2": QColor(255, 60, 180),
            "success": QColor(0, 255, 160),
            "warning": QColor(255, 200, 0),
            "error": QColor(255, 40, 80),
            "text": QColor(200, 200, 240),
            "grid": QColor(60, 40, 120, 40),
            "particle": QColor(180, 120, 255, 80),
        },
        "matrix": {
            "name": "Matrix",
            "bg": QColor(0, 8, 0),
            "accent": QColor(0, 255, 65),
            "accent2": QColor(0, 180, 45),
            "success": QColor(0, 255, 100),
            "warning": QColor(200, 255, 0),
            "error": QColor(255, 0, 0),
            "text": QColor(0, 220, 55),
            "grid": QColor(0, 60, 15, 40),
            "particle": QColor(0, 255, 65, 60),
        },
        "quantum": {
            "name": "Quantum Circuit",
            "bg": QColor(10, 15, 25),
            "accent": QColor(0, 200, 255),
            "accent2": QColor(0, 255, 200),
            "success": QColor(0, 255, 136),
            "warning": QColor(255, 180, 0),
            "error": QColor(255, 50, 80),
            "text": QColor(180, 220, 255),
            "grid": QColor(0, 60, 90, 40),
            "particle": QColor(0, 200, 255, 60),
        },
        "ocean": {
            "name": "Deep Ocean",
            "bg": QColor(5, 10, 30),
            "accent": QColor(0, 150, 255),
            "accent2": QColor(0, 220, 180),
            "success": QColor(0, 230, 170),
            "warning": QColor(255, 200, 50),
            "error": QColor(255, 60, 90),
            "text": QColor(160, 200, 240),
            "grid": QColor(0, 40, 80, 40),
            "particle": QColor(0, 120, 200, 50),
        },
    }
