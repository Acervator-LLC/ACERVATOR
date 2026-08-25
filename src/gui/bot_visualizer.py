"""
bot_visualizer.py - Futuristic Bot Visualization Engine
========================================================
Custom-painted animated visualizations for active trading bots.
Combines art, auto-trading data, and technical analysis into
an immersive visual experience.

Themes: Nebula, Matrix, Quantum Circuit, Deep Ocean
"""

from __future__ import annotations

import logging
import math
import sys
import secrets
import time
from typing import Optional

# v3.24.36 (C06b) — this module used `logger.debug` at one site with no
# module-level binding and no `import logging`, so that line was a latent
# NameError: it sits inside an `except` handler, so firing it would have
# raised OUT of the handler rather than being swallowed. Identical shape
# to NF-154 in main.py, found earlier in this cascade series.
#
# Caught here because C02 and C06b each added a `logger.error` call to
# this file, and verifying the binding before shipping is now standing
# practice. Two of the three call sites were mine.
logger = logging.getLogger("acervator.gui.bot_visualizer")

# Visual jitter only: the swarm canvas draws a start phase and particle
# velocities. This module reads from secrets.SystemRandom, which draws
# from the OS entropy source, so no non-cryptographic generator is
# reachable here. SystemRandom inherits uniform() from random.Random,
# so the distribution of every draw below is unchanged. No call site
# in this module seeds or replays a draw.
_RNG = secrets.SystemRandom()

# v3.23.9 — Shared Privacy Mask Registry. The Bot Swarm tab joins the
# Trading tab on the same singleton so toggling either flips both
# (operator-pinned Q1 (a) — SHARED registry, not a separate instance).
try:
    from ..core.privacy_mask_registry import (
        get_privacy_mask_registry as _get_privacy_mask_registry,
        mask_or as _mask_or,
    )
except Exception:  # R28-OK: defensive — bot_visualizer must import even
    # if the registry module fails to load; render falls back to plain
    # strings (no masking) and the GUI continues to function.
    _get_privacy_mask_registry = None  # type: ignore[assignment]

    def _mask_or(value, field_id: str, mask: str = "****") -> str:
        # Signature parity with the real mask_or is load-bearing:
        # callers pass mask= by keyword. This fallback masks nothing,
        # so it discards both masking parameters rather than reading
        # them.
        del field_id, mask
        return str(value)


try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QComboBox,
        QLabel,
        QScrollArea,
        QFrame,
        QMenu,
        QTabWidget,
        QGroupBox,
        QPushButton,
        QDoubleSpinBox,
        QSizePolicy,
        QGridLayout,
        QMessageBox,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
    )
    from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
    from PySide6.QtGui import (
        QPainter,
        QPen,
        QBrush,
        QColor,
        QFont,
        QRadialGradient,
        QLinearGradient,
        QPainterPath,
        QPolygonF,
    )  # v3.19.12 removed unused QConicalGradient

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

    # -------------------------------------------------------------------
    # Particle system for ambient animation
    # -------------------------------------------------------------------
    class Particle:
        def __init__(self, x, y, vx, vy, life, size):
            self.x, self.y = x, y
            self.vx, self.vy = vx, vy
            self.life = life
            self.max_life = life
            self.size = size

        def update(self, dt):
            self.x += self.vx * dt
            self.y += self.vy * dt
            self.life -= dt

        @property
        def alpha(self):
            return max(0, self.life / self.max_life)

    # -------------------------------------------------------------------
    # Bot Node - single bot visualization
    #
    # MEM-233 (2026-04-22) — Locust redesign.
    # Operator directive: "make insectoid with a focus toward them
    # looking locusts. Should also be about 30% smaller. Do not leave
    # all of the functionality dangling like Smart Wire when redoing
    # these!"
    #
    # Design grounding (R63 ERG / R65 GDG):
    #   - Gunpei Yokoi — "lateral thinking with withered technology":
    #     smaller canvas forces stronger silhouette.
    #   - Adam Saltsman — silhouette-first: locust outline must read
    #     as LOCUST before any color. The thorax-abdomen-head profile
    #     does that job.
    #   - Pedro Medeiros — idle as home-base pose; other states
    #     (running wings open, paused wings half-fold) transition
    #     from the same root geometry.
    #   - Toby Fox — personality-through-silhouette: state changes
    #     the wing/leg posture, not the palette alone.
    #   - Cole Knaflic — one preattentive focus: the compound eye
    #     (state color) is the single strongest cue. Everything
    #     else recedes.
    #   - WCAG 2.2 AA — all text on bg is min 4.5:1 in the default
    #     quantum theme; state-color ring is 3:1 graphical minimum.
    #
    # Preserved functionality (NONE of this regresses):
    #   - symbol, state (6 states + color map), mode badge, P/L value,
    #     P/L gauge, trades count, current price, trade volume (K/M),
    #     bot_id tag, trade pulses, trade-event particles.
    #   - set_theme(key), set_bot_data(data), animate(dt), paintEvent.
    #   - Widget center (w/2, h/2) = locust thorax center, so Smart
    #     Wire's _get_bot_center keeps working without changes.
    # -------------------------------------------------------------------
    class BotNodeWidget(QWidget):
        """Locust-themed bot card. Insectoid silhouette with functional
        elements mapped to anatomy: head/compound-eye = state;
        thorax = symbol + mode; abdomen = P/L gauge; wings = trade
        pulse; legs + antennae = ambient animation."""

        def __init__(self, parent=None):
            super().__init__(parent)
            # Session 26 (2026-04-24) operator directive: "50% smaller" from
            # the MEM-233 224x196 baseline → 112x98. Grid layout wraps many
            # locusts into a compact swarm so Smart Wires are short and
            # reachable. Label density was trimmed (dropped mode badge,
            # trades, price, volume) to fit the smaller canvas without
            # overflowing; bot_id + symbol + P/L remain. The stats that
            # were dropped remain queryable via hover-tooltip (queued for
            # Session 27 per PLAN_LOCUST_REFRESH.md Scope A).
            # sadp: R17 (operator explicit override authorises dim change)
            #       R65 GDG (WCAG 2.2 SC 2.5.8 — pointer target ≥24x24 CSS;
            #                112x98 far exceeds that for drag)
            self.setMinimumSize(112, 98)
            self._theme = THEMES["quantum"]
            self._phase = _RNG.uniform(0, math.pi * 2)
            self._trade_pulses: list[float] = []
            self._particles: list[Particle] = []
            self._bot_data: dict = {}
            # Antenna sway driven by price ticks (ambient life).
            self._antenna_drive: float = 0.0

        def set_theme(self, theme_key: str):
            self._theme = THEMES.get(theme_key, THEMES["quantum"])
            self.update()

        def set_bot_data(self, data: dict):
            # Trade pulse — same contract as before: new trade count
            # spawns a pulse + a handful of particles.
            old_trades = self._bot_data.get("stats", {}).get("total_trades", 0)
            new_trades = data.get("stats", {}).get("total_trades", 0)
            if new_trades > old_trades:
                self._trade_pulses.append(1.0)
                cx, cy = self.width() / 2, self.height() / 2
                for _ in range(5):
                    self._particles.append(
                        Particle(
                            cx,
                            cy,
                            _RNG.uniform(-30, 30),
                            _RNG.uniform(-30, 30),
                            _RNG.uniform(0.5, 1.5),
                            _RNG.uniform(1.5, 3.5),
                        )
                    )
            # Antenna sway on any price change.
            old_price = self._bot_data.get("stats", {}).get("current_price", 0)
            new_price = data.get("stats", {}).get("current_price", 0)
            if old_price and new_price and old_price != new_price:
                self._antenna_drive = 1.0
            self._bot_data = data

        def animate(self, dt: float):
            self._phase += dt * 1.5
            self._trade_pulses = [
                p - dt * 0.8 for p in self._trade_pulses if p - dt * 0.8 > 0
            ]
            for p in self._particles:
                p.update(dt)
            self._particles = [p for p in self._particles if p.life > 0]
            # Antenna drive decays over ~1s
            self._antenna_drive = max(0.0, self._antenna_drive - dt * 1.0)
            self.update()

        # -- Locust anatomy helpers ----------------------------------

        def _locust_body_path(
            self, cx: float, cy: float, scale: float, wing_open: float
        ) -> dict:
            """Build the locust body geometry. Returns a dict of
            QPainterPath parts so the paint method can style each
            segment independently.

            wing_open: 0.0 fully folded (idle/stopped) → 1.0 fully
                      spread (running with recent trade)."""
            # Scale is relative to a 32-unit grid; everything below
            # is expressed in unit terms and then multiplied.
            u = scale

            parts: dict = {}

            # HEAD — a rounded trapezoid up top.
            head = QPainterPath()
            head.moveTo(cx - 4 * u, cy - 16 * u)
            head.quadTo(cx - 5 * u, cy - 19 * u, cx, cy - 20 * u)
            head.quadTo(cx + 5 * u, cy - 19 * u, cx + 4 * u, cy - 16 * u)
            head.lineTo(cx + 3.5 * u, cy - 13 * u)
            head.lineTo(cx - 3.5 * u, cy - 13 * u)
            head.closeSubpath()
            parts["head"] = head

            # THORAX — the "chest" segment. Elongated hexagonal plate
            # that visually reads as an armoured pronotum. This is the
            # widget's geometric center — symbol label lands here.
            thorax = QPainterPath()
            thorax.moveTo(cx - 6 * u, cy - 12 * u)
            thorax.lineTo(cx + 6 * u, cy - 12 * u)
            thorax.lineTo(cx + 7 * u, cy - 4 * u)
            thorax.lineTo(cx + 6 * u, cy + 2 * u)
            thorax.lineTo(cx - 6 * u, cy + 2 * u)
            thorax.lineTo(cx - 7 * u, cy - 4 * u)
            thorax.closeSubpath()
            parts["thorax"] = thorax

            # ABDOMEN — tapered tail with segment markers. Segment
            # count is fixed (4) — coloration reflects P/L.
            abdomen = QPainterPath()
            abdomen.moveTo(cx - 5.5 * u, cy + 2 * u)
            abdomen.lineTo(cx + 5.5 * u, cy + 2 * u)
            abdomen.quadTo(cx + 5 * u, cy + 10 * u, cx + 2.5 * u, cy + 16 * u)
            abdomen.quadTo(cx, cy + 18 * u, cx - 2.5 * u, cy + 16 * u)
            abdomen.quadTo(cx - 5 * u, cy + 10 * u, cx - 5.5 * u, cy + 2 * u)
            abdomen.closeSubpath()
            parts["abdomen"] = abdomen

            # WINGS — two elongated teardrops folded along the thorax.
            # wing_open 0 → tight to body; 1 → spread wide.
            wing_spread = 4.5 * u + wing_open * 6 * u
            wing_lift = wing_open * 2 * u
            wing_l = QPainterPath()
            wing_l.moveTo(cx - 4 * u, cy - 10 * u)
            wing_l.quadTo(
                cx - wing_spread,
                cy - 6 * u - wing_lift,
                cx - wing_spread * 0.85,
                cy + 4 * u - wing_lift,
            )
            wing_l.quadTo(
                cx - 4 * u,
                cy + 2 * u,
                cx - 3 * u,
                cy - 10 * u,
            )
            wing_l.closeSubpath()
            parts["wing_l"] = wing_l

            wing_r = QPainterPath()
            wing_r.moveTo(cx + 4 * u, cy - 10 * u)
            wing_r.quadTo(
                cx + wing_spread,
                cy - 6 * u - wing_lift,
                cx + wing_spread * 0.85,
                cy + 4 * u - wing_lift,
            )
            wing_r.quadTo(
                cx + 4 * u,
                cy + 2 * u,
                cx + 3 * u,
                cy - 10 * u,
            )
            wing_r.closeSubpath()
            parts["wing_r"] = wing_r

            return parts

        def paintEvent(self, event):
            if not self._bot_data:
                return
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            t = self._theme
            w, h = self.width(), self.height()
            cx, cy = w / 2, h / 2

            # Background — same base as before.
            p.fillRect(0, 0, w, h, t["bg"])

            data = self._bot_data
            stats = data.get("stats", {})
            state = data.get("state", "idle")
            symbol = data.get("symbol", "???")
            # v3.20.4 — default changed from "grid" to "scrumming"
            # (grid_bot deleted v3.16.0; "grid" is no longer a valid
            # BotMode value).
            mode = data.get("mode", "scrumming")
            pnl = stats.get("realised_pnl", 0)
            trades = stats.get("total_trades", 0)
            price = stats.get("current_price", 0)
            volume = stats.get("trade_volume", 0)

            state_color = {
                "running": t["success"],
                "idle": QColor(100, 100, 100),
                "paused": t["warning"],
                "error": t["error"],
                "stopped": QColor(80, 80, 80),
                "cooldown": t["warning"],
            }.get(state, t["text"])
            pnl_color = t["success"] if pnl >= 0 else t["error"]

            # Locust is rendered at body scale = min_dim / 52 approx.
            # At 224x196 that gives a ~3.7u scale — tight but readable.
            scale = min(w, h) / 52.0

            # Wing openness: running with trade pulse → open;
            # idle/stopped → tight closed; paused/error/cooldown → half.
            wing_open = 0.35
            if state == "running":
                wing_open = 0.55 + 0.15 * math.sin(self._phase * 3)
            elif state in ("stopped", "idle"):
                wing_open = 0.15
            # Any active trade pulse adds a flick of wing extension.
            if self._trade_pulses:
                wing_open = min(1.0, wing_open + 0.3 * self._trade_pulses[0])

            # --- Trade pulse rings (shock wave from the thorax) -----
            # Keep this as the insect-analogue of "the bot just struck"
            # so trade events remain visible from a glance.
            for pulse in self._trade_pulses:
                radius = 20 * scale + (1 - pulse) * 40
                alpha = int(180 * pulse)
                pc = QColor(t["success"])
                pc.setAlpha(alpha)
                pen = QPen(pc)
                pen.setWidth(2)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(cx, cy), radius, radius)

            # --- Particles -----------------------------------------
            for pt in self._particles:
                pc = QColor(t["particle"])
                pc.setAlpha(int(255 * pt.alpha))
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(pc))
                p.drawEllipse(QPointF(pt.x, pt.y), pt.size, pt.size)

            # --- Build the locust ----------------------------------
            parts = self._locust_body_path(cx, cy, scale, wing_open)

            # Ambient outer glow around the thorax in state_color.
            # Knaflic: the single preattentive focus is the state.
            glow = QRadialGradient(cx, cy, 18 * scale)
            gc = QColor(state_color)
            gc.setAlpha(55)
            glow.setColorAt(0, gc)
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(cx, cy), 18 * scale, 18 * scale)

            # WINGS — drawn first (behind body). Translucent with a
            # subtle inner accent line so they read as insect wings,
            # not paper flaps.
            wing_color = QColor(t["accent"])
            wing_color.setAlpha(50 + int(40 * wing_open))
            p.setBrush(QBrush(wing_color))
            wing_pen = QPen(QColor(t["accent2"]))
            wing_pen.setWidth(1)
            wing_pen.setStyle(Qt.DashLine)
            wc = QColor(t["accent2"])
            wc.setAlpha(100)
            wing_pen.setColor(wc)
            p.setPen(wing_pen)
            p.drawPath(parts["wing_l"])
            p.drawPath(parts["wing_r"])

            # ABDOMEN — segmented, P/L-colored segments from head-side
            # outward. Positive P/L = success color intensity rises
            # with magnitude; negative = error. 4 segments = 4 ticks
            # of gradient (Bulkowski's empirical: discrete bins read
            # better than continuous gradients at small size).
            abdomen_grad = QLinearGradient(cx, cy + 2 * scale, cx, cy + 18 * scale)
            base_ab = QColor(pnl_color)
            # Magnitude-to-saturation mapping: tiny P/L barely tints;
            # larger P/L saturates. Log-compressed so $10,000 is visible
            # but $0.10 doesn't look the same as $10.
            mag = min(1.0, math.log10(max(abs(pnl), 0.1) + 1.0) / 4.0)
            base_ab.setAlpha(int(90 + 120 * mag))
            tip = QColor(pnl_color)
            tip.setAlpha(int(40 + 60 * mag))
            abdomen_grad.setColorAt(0, base_ab)
            abdomen_grad.setColorAt(1, tip)
            p.setBrush(QBrush(abdomen_grad))
            ab_pen = QPen(pnl_color)
            ab_pen.setWidth(1)
            p.setPen(ab_pen)
            p.drawPath(parts["abdomen"])

            # Segment dividers — three thin lines across the abdomen.
            seg_pen = QPen(QColor(0, 0, 0, 120))
            seg_pen.setWidth(1)
            p.setPen(seg_pen)
            for i in range(1, 4):
                y_seg = cy + (2 + i * 4) * scale
                # Width of abdomen tapers as we go down.
                taper = 5.5 - i * 0.8
                p.drawLine(
                    QPointF(cx - taper * scale, y_seg),
                    QPointF(cx + taper * scale, y_seg),
                )

            # THORAX — armored plate in state color.
            thorax_grad = QRadialGradient(cx, cy - 5 * scale, 10 * scale)
            tc1 = QColor(state_color)
            tc1.setAlpha(90)
            tc2 = QColor(state_color)
            tc2.setAlpha(30)
            thorax_grad.setColorAt(0, tc1)
            thorax_grad.setColorAt(1, tc2)
            p.setBrush(QBrush(thorax_grad))
            th_pen = QPen(state_color)
            th_pen.setWidth(2)
            p.setPen(th_pen)
            p.drawPath(parts["thorax"])

            # HEAD — solid outline with a compound-eye dot (state
            # color, pulsing). This is THE preattentive cue.
            head_fill = QColor(t["bg"]).lighter(120)
            p.setBrush(QBrush(head_fill))
            head_pen = QPen(state_color)
            head_pen.setWidth(2)
            p.setPen(head_pen)
            p.drawPath(parts["head"])

            # Compound eye (single large dot; pulses with phase).
            eye_radius = 1.8 * scale + 0.6 * scale * math.sin(self._phase * 3)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(state_color))
            p.drawEllipse(QPointF(cx, cy - 16.5 * scale), eye_radius, eye_radius)

            # ANTENNAE — two thin curved lines. Sway driven by
            # antenna_drive (price tick) plus ambient phase.
            ant_pen = QPen(QColor(t["accent2"]))
            ant_pen.setWidth(1)
            p.setPen(ant_pen)
            p.setBrush(Qt.NoBrush)
            for sign in (-1, 1):
                sway = 0.4 * math.sin(
                    self._phase * 2 + sign * 1.0
                ) + 0.8 * self._antenna_drive * math.sin(self._phase * 6 + sign * 0.5)
                ant = QPainterPath()
                ant.moveTo(cx + sign * 2 * scale, cy - 19 * scale)
                ant.quadTo(
                    cx + sign * (4 + sway) * scale,
                    cy - 24 * scale,
                    cx + sign * (5 + sway) * scale,
                    cy - 28 * scale,
                )
                p.drawPath(ant)
                # Antenna tip dot.
                p.setPen(Qt.NoPen)
                tip_col = QColor(t["accent2"])
                tip_col.setAlpha(180)
                p.setBrush(QBrush(tip_col))
                p.drawEllipse(
                    QPointF(cx + sign * (5 + sway) * scale, cy - 28 * scale), 1.2, 1.2
                )
                p.setPen(ant_pen)

            # LEGS — 3 pairs, mounted at the thorax. Hind leg (pair 3)
            # is the characteristic locust jumping leg (bent, thicker).
            leg_pen = QPen(QColor(state_color).darker(120))
            leg_pen.setWidth(2)
            p.setPen(leg_pen)
            for sign in (-1, 1):
                # Pair 1 — foreleg (thin, forward).
                p1_base = (cx + sign * 5.5 * scale, cy - 8 * scale)
                p1_knee = (cx + sign * 8 * scale, cy - 4 * scale)
                p1_foot = (cx + sign * 9 * scale, cy + 3 * scale)
                p.drawLine(QPointF(*p1_base), QPointF(*p1_knee))
                p.drawLine(QPointF(*p1_knee), QPointF(*p1_foot))

                # Pair 2 — midleg (thin, lateral).
                p2_base = (cx + sign * 6.5 * scale, cy - 3 * scale)
                p2_knee = (cx + sign * 9.5 * scale, cy + 1 * scale)
                p2_foot = (cx + sign * 10 * scale, cy + 8 * scale)
                p.drawLine(QPointF(*p2_base), QPointF(*p2_knee))
                p.drawLine(QPointF(*p2_knee), QPointF(*p2_foot))

                # Pair 3 — hind (thick, strongly bent — the locust
                # signature).
                leg_pen.setWidth(3)
                p.setPen(leg_pen)
                p3_base = (cx + sign * 6 * scale, cy + 1 * scale)
                p3_knee = (cx + sign * 11 * scale, cy - 4 * scale)
                p3_foot = (cx + sign * 10 * scale, cy + 10 * scale)
                p.drawLine(QPointF(*p3_base), QPointF(*p3_knee))
                p.drawLine(QPointF(*p3_knee), QPointF(*p3_foot))
                leg_pen.setWidth(2)
                p.setPen(leg_pen)

            # -------------------------------------------------------
            # Cybernetic detail — small circuit accent lines on the
            # thorax, corner brackets at widget bounds, and an inner
            # iris ring on the compound eye. Session 26 (2026-04-24)
            # operator directive: "cybernetic locusts". Kept lightweight
            # so the insect silhouette still reads (Saltsman Pillar 2).
            # -------------------------------------------------------
            QColor(t["accent2"])
            # Corner brackets — 4 small L-shapes at widget corners.
            # Subtle; read as HUD frame. WCAG: accent2 on bg ≥ 3:1 in
            # shipped themes.
            bracket_col = QColor(t["accent2"])
            bracket_col.setAlpha(140)
            bpen = QPen(bracket_col)
            bpen.setWidth(1)
            p.setPen(bpen)
            blen = 6  # bracket leg length in px
            for bx, by, dx, dy in (
                (1, 1, 1, 1),  # top-left
                (w - 2, 1, -1, 1),  # top-right
                (1, h - 2, 1, -1),  # bottom-left
                (w - 2, h - 2, -1, -1),  # bottom-right
            ):
                p.drawLine(QPointF(bx, by), QPointF(bx + dx * blen, by))
                p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * blen))

            # Thorax circuit traces — 2 thin horizontal lines across
            # the pronotum, with a small tap-node dot. Reads as chip-
            # like detail at 112x98.
            circ_col = QColor(t["accent"])
            circ_col.setAlpha(110)
            cpen = QPen(circ_col)
            cpen.setWidth(1)
            p.setPen(cpen)
            for dy_u in (-6, -8):
                y_line = cy + dy_u * scale
                p.drawLine(
                    QPointF(cx - 4 * scale, y_line), QPointF(cx + 4 * scale, y_line)
                )
            # Two small circuit-tap dots
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(circ_col))
            for dx_u in (-4, 4):
                p.drawEllipse(QPointF(cx + dx_u * scale, cy - 7 * scale), 1.2, 1.2)

            # Compound-eye iris — inner ring in accent2 over the
            # state-color dot rendered above. Gives the eye depth.
            iris_col = QColor(t["accent2"])
            iris_col.setAlpha(200)
            ipen = QPen(iris_col)
            ipen.setWidth(1)
            p.setPen(ipen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(
                QPointF(cx, cy - 16.5 * scale), eye_radius * 1.5, eye_radius * 1.5
            )

            # -------------------------------------------------------
            # Text labels — minimal set for the 112x98 canvas.
            # Kept: symbol (top), P/L (below abdomen), bot_id (bottom).
            # Dropped for space: mode badge, state text, trades, price,
            # volume. State is conveyed by the head/thorax color ring.
            # Dropped stats remain queryable via hover-tooltip (Session
            # 27 queued per PLAN_LOCUST_REFRESH.md).
            # WCAG: all text uses t["text"] or pnl_color, ≥4.5:1 on bg.
            # -------------------------------------------------------
            from ..core.fmt import fmt_pnl as _fpnl

            # Symbol — top center, above the head (between antennae).
            # v3.23.9 Q2 (c): symbol label is privacy-masked via the
            # shared bot_swarm.identifiers field id (one toggle masks
            # both symbol + bot_id).
            font = QFont("Consolas", 7, QFont.Bold)
            p.setFont(font)
            p.setPen(t["text"])
            p.drawText(
                QRectF(0, 2, w, 11),
                Qt.AlignCenter,
                _mask_or(symbol, "bot_swarm.identifiers"),
            )

            # P/L — below the abdomen, color-coded.
            font.setPointSize(7)
            p.setFont(font)
            p.setPen(pnl_color)
            p.drawText(QRectF(0, h - 22, w, 11), Qt.AlignCenter, _fpnl(pnl))

            # bot_id — bottom, muted.
            # v3.23.9 Q2 (c): same field id as symbol — single red-dot
            # button hides BOTH at once.
            font.setPointSize(5)
            font.setBold(False)
            p.setFont(font)
            p.setPen(QColor(110, 110, 140))
            bot_id_short = data.get("bot_id", "")[:8]
            p.drawText(
                QRectF(0, h - 10, w, 9),
                Qt.AlignCenter,
                _mask_or(bot_id_short, "bot_swarm.identifiers"),
            )

            # Set tooltip with the dropped stats so they're still
            # recoverable. Rebuilt each paint from the latest data.
            from ..core.fmt import fmt_price as _fp

            vol_str = (
                f"${volume/1e6:.1f}M"
                if volume >= 1e6
                else f"${volume/1e3:.1f}K" if volume >= 1e3 else f"${volume:.0f}"
            )
            # v3.24.41 (C03 / SWARM-4.7) — the tooltip leaked what the
            # labels above were masking. Lines painting the symbol and
            # the bot_id both route through _mask_or, but this string
            # interpolated the RAW symbol and a RAW 12-char bot_id —
            # four characters MORE than the label ever showed. With
            # privacy mode on, the locust displayed **** and a hover
            # gave the real values back. Same field id as the labels, so
            # the one red-dot button governs all three.
            self.setToolTip(
                f"{_mask_or(symbol, 'bot_swarm.identifiers')}\n"
                f"State: {state.upper()}\n"
                f"Mode: {mode.upper()}\n"
                f"Trades: {trades}\n"
                f"Price: {_fp(price) if price > 0 else '—'}\n"
                f"Volume: {vol_str}\n"
                f"P/L: {_fpnl(pnl)}\n"
                f"Bot: {_mask_or(str(data.get('bot_id', ''))[:12], 'bot_swarm.identifiers', mask='********')}"
            )

            p.end()

    # -------------------------------------------------------------------
    # v3.23.9 — Quick Routing Matrix
    # -------------------------------------------------------------------
    # Operator-pinned Q3: pick 1+ Source bots, 1+ Destination bots, an
    # Amount %, and Connect wires every Source → every Destination at
    # N% of source's profit-per-trade. Disconnect removes wires in the
    # current selection. Disconnect All clears every wire globally.
    #
    # Persistence (Q5 (a)): wires live on each source bot's
    # ``scrumming_state.smart_wire_routes`` list — `{dest_bot_id, pct}`
    # dicts — inside ``~/.acervator/bot_state.json``. Saved immediately
    # on every Connect / Disconnect / Disconnect All action.
    #
    # Exchange filter (Q4 (c)): the Source/Destination checkbox lists
    # rebuild themselves from the parent tab's current exchange selector
    # scope. Bots outside the scope are hidden from the matrix entirely.
    # -------------------------------------------------------------------
    class QuickRoutingMatrix(QWidget):
        """v3.23.18 — Three side-by-side Source | Rate | Destination zones,
        each a single-bordered widget (no nested window-in-window), with
        the three Connect / Disconnect / Disconnect All buttons horizontally
        centered below them. Lives in the void to the right of the bot grid
        per operator 2026-06-16 verbatim spec."""

        def __init__(self, viz_tab: "BotVisualizationTab"):
            super().__init__(viz_tab)
            self._viz = viz_tab
            # v3.23.18 layout per operator 2026-06-16:
            #   outer = QVBoxLayout
            #     col_row = QHBoxLayout(Source, Rate, Destination) — equal stretch=1
            #     btn_row = QHBoxLayout(stretch, Connect, Disconnect, DisconnectAll, stretch)
            # Source / Destination = QListWidget directly with frameShape=Box for
            # the SINGLE rectangle border (no outer QGroupBox wrapping). Rate
            # zone = QWidget containing label "Rate" + QLineEdit (no spinner).
            # All three zones get equal stretch so they have equal width.
            outer = QVBoxLayout(self)
            outer.setContentsMargins(4, 0, 4, 0)
            outer.setSpacing(4)

            col_row = QHBoxLayout()
            col_row.setSpacing(0)
            col_row.setContentsMargins(0, 0, 0, 0)

            # v3.23.18 — Bare-QListWidget dark theme matching the
            # v3.23.15 in-QGroupBox appearance (the QGroupBox is gone
            # per single-rectangle spec, so the dark theme must be
            # applied directly to the list).
            _list_style = (
                "QListWidget{background:#0a0a18;color:#aaccff;"
                "border:1px solid #1a2a4a;font-family:Consolas;"
                "font-size:11px;}"
                "QListWidget::item{padding:3px 4px;}"
                "QListWidget::item:hover{background:#142244;}"
            )

            # ── Source zone — single-rectangle QListWidget ────────────
            self._source_list = QListWidget()
            self._source_list.setSelectionMode(QListWidget.NoSelection)
            self._source_list.setSizePolicy(
                QSizePolicy.Expanding, QSizePolicy.Expanding
            )
            self._source_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._source_list.setStyleSheet(_list_style)
            self._source_list.setToolTip(
                "Source Bots — check one or more; Connect wires every "
                "checked source → every checked destination at the Rate."
            )
            col_row.addWidget(self._source_list, stretch=1)

            # ── Rate zone — single-rectangle QWidget with QLineEdit ───
            rate_zone = QFrame()
            rate_zone.setFrameShape(QFrame.Box)
            rate_zone.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            rate_zone.setStyleSheet(
                "QFrame{background:#0a0a18;border:1px solid #1a2a4a;}"
            )
            rate_lay = QVBoxLayout(rate_zone)
            rate_lay.setContentsMargins(8, 8, 8, 8)
            self._rate_label = QLabel("Rate")
            self._rate_label.setAlignment(Qt.AlignCenter)
            self._rate_label.setStyleSheet(
                "color:#aaccff;font-family:Consolas;font-size:11px;"
                "font-weight:bold;border:none;"
            )
            rate_lay.addWidget(self._rate_label)
            self._rate_input = QLineEdit("25")
            self._rate_input.setAlignment(Qt.AlignCenter)
            self._rate_input.setStyleSheet(
                "QLineEdit{background:#142244;color:#aaccff;"
                "border:1px solid #2244aa;padding:3px 6px;"
                "font-family:Consolas;font-size:11px;}"
            )
            self._rate_input.setToolTip(
                "Percent of each source's profit-per-trade routed to "
                "each destination."
            )
            rate_lay.addWidget(self._rate_input)
            rate_lay.addStretch()
            col_row.addWidget(rate_zone, stretch=1)

            # ── Destination zone — single-rectangle QListWidget ───────
            self._dest_list = QListWidget()
            self._dest_list.setSelectionMode(QListWidget.NoSelection)
            self._dest_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self._dest_list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self._dest_list.setStyleSheet(_list_style)
            self._dest_list.setToolTip(
                "Destination Bots — wires terminate at every checked " "destination."
            )
            col_row.addWidget(self._dest_list, stretch=1)

            outer.addLayout(col_row, stretch=1)

            # ── Button row — centered horizontal Connect/Disconnect/DisconnectAll ─
            btn_row = QHBoxLayout()
            btn_row.setSpacing(8)
            btn_row.setContentsMargins(0, 4, 0, 4)
            btn_row.addStretch()
            self._connect_btn = QPushButton("Connect")
            self._connect_btn.setToolTip(
                "Wire every checked Source → every checked Destination "
                "at the current Rate %."
            )
            self._connect_btn.clicked.connect(self._on_connect_clicked)
            btn_row.addWidget(self._connect_btn)

            self._disconnect_btn = QPushButton("Disconnect")
            self._disconnect_btn.setToolTip(
                "Remove wires for every checked (Source, Destination) "
                "pair in the current selection."
            )
            self._disconnect_btn.clicked.connect(self._on_disconnect_clicked)
            btn_row.addWidget(self._disconnect_btn)

            self._disconnect_all_btn = QPushButton("Disconnect All")
            self._disconnect_all_btn.setToolTip(
                "Clear ALL Smart Wires across the entire swarm "
                "(asks for confirmation)."
            )
            self._disconnect_all_btn.clicked.connect(self._on_disconnect_all_clicked)
            btn_row.addWidget(self._disconnect_all_btn)
            btn_row.addStretch()
            outer.addLayout(btn_row)

        # ----------------------------------------------------------
        # Scope rebuild — called when exchange filter changes
        # ----------------------------------------------------------
        def rebuild_scope(self, bot_ids: list[str]) -> None:
            """v3.23.13: Repopulate source + destination checkbox lists
            from the current filtered set of bot_ids. Preserves which
            bots were checked across the rebuild so the operator's
            in-progress selection survives an exchange-filter change."""
            prior_src = self._selected_sources()
            prior_dst = self._selected_destinations()
            # v3.24.36 (C05) � scroll offset. clear() collapses the
            # scrollbar range, which clamps its value to 0. That clamp
            # only lands on the next relayout, so today the offset
            # survives purely because nothing turns the event loop
            # between the clear and the refill below � measured: force
            # one processEvents() in between and a 35-row scroll goes
            # to 0. Save and restore it so the operator's position is
            # guaranteed rather than incidental.
            prior_src_scroll = self._source_list.verticalScrollBar().value()
            prior_dst_scroll = self._dest_list.verticalScrollBar().value()
            self._source_list.clear()
            self._dest_list.clear()
            # v3.23.20 — Operator 2026-06-16 directive Q2.a: when
            # bot_swarm.identifiers is masked, render BOTH symbol AND
            # hash as ****. Same field-id the locust labels consult.
            self._last_scope_ids = list(bot_ids)
            for bid in bot_ids:
                sym = self._symbol_for(bid)
                short = bid[:8] if bid else ""
                label = (
                    f"{_mask_or(sym, 'bot_swarm.identifiers')} "
                    f"[{_mask_or(short, 'bot_swarm.identifiers', mask='********')}]"
                )

                si = QListWidgetItem(label)
                si.setData(Qt.UserRole, bid)
                si.setFlags(si.flags() | Qt.ItemIsUserCheckable)
                si.setCheckState(Qt.Checked if bid in prior_src else Qt.Unchecked)
                self._source_list.addItem(si)

                di = QListWidgetItem(label)
                di.setData(Qt.UserRole, bid)
                di.setFlags(di.flags() | Qt.ItemIsUserCheckable)
                di.setCheckState(Qt.Checked if bid in prior_dst else Qt.Unchecked)
                self._dest_list.addItem(di)

            # v3.24.36 (C05) � restore the offsets saved above. The
            # range is recomputed lazily, so a synchronous setValue can
            # be clamped against a range that is still 0..0; the
            # deferred pass runs after the relayout that fixes it.
            # Both are needed � neither alone covers both orderings.
            for lst, val in (
                (self._source_list, prior_src_scroll),
                (self._dest_list, prior_dst_scroll),
            ):
                if not val:
                    continue
                lst.verticalScrollBar().setValue(val)
                QTimer.singleShot(
                    0, lambda b=lst.verticalScrollBar(), v=val: b.setValue(v)
                )

        def _symbol_for(self, bot_id: str) -> str:
            """Best-effort lookup of a bot's symbol for display."""
            try:
                w = self._viz._bot_widgets.get(bot_id)
                if w is not None:
                    sym = (
                        w._bot_data.get("symbol", "") if hasattr(w, "_bot_data") else ""
                    )
                    if sym:
                        return str(sym)
            except Exception:  # noqa: S110
                pass
            try:
                from ..core.state_manager import StateManager

                st = StateManager().load_state()
                cfg = (st.get("bots", {}) or {}).get(bot_id, {}).get("config", {}) or {}
                return str(cfg.get("symbol", "") or "?")
            except Exception:
                return "?"

        # ----------------------------------------------------------
        # Selected ids — v3.23.13: iterate checked items from
        # multi-select QListWidget panels. Returns every checked bot_id
        # so the (sources × destinations) cartesian product in
        # _on_connect_clicked produces N×M wires from one click.
        # ----------------------------------------------------------
        def _selected_sources(self) -> list[str]:
            """All currently-checked source bot_ids (empty list if
            none checked)."""
            out: list[str] = []
            for i in range(self._source_list.count()):
                it = self._source_list.item(i)
                if it.checkState() == Qt.Checked:
                    bid = it.data(Qt.UserRole) or ""
                    if bid:
                        out.append(str(bid))
            return out

        def _selected_destinations(self) -> list[str]:
            """All currently-checked destination bot_ids (empty list if
            none checked)."""
            out: list[str] = []
            for i in range(self._dest_list.count()):
                it = self._dest_list.item(i)
                if it.checkState() == Qt.Checked:
                    bid = it.data(Qt.UserRole) or ""
                    if bid:
                        out.append(str(bid))
            return out

        # ----------------------------------------------------------
        # Button handlers
        # ----------------------------------------------------------
        def _reject(self, why: str) -> None:
            """Tell the operator why a Quick Routing click did nothing.

            v3.24.36 (C05). Every rejection path below used to be a bare
            `return`: an empty rate box, a stray character, nothing
            checked, or 0% all produced exactly the same visible result
            as success — nothing. In List view even the success case
            draws nothing, so there was no way to distinguish "it
            worked" from "it silently refused".
            """
            try:
                QMessageBox.warning(self, "Quick Routing", why)
            except Exception as exc:  # noqa: BLE001
                logger.warning("quick-routing rejection unshowable: %s", exc)

        def _confirm_mass(self, verb: str, n: int, detail: str) -> bool:
            """Confirm an N x M wire operation. True to proceed.

            v3.24.36 (C05). `_selected_sources` / `_selected_destinations`
            return EVERY checked item, and `rebuild_scope` populates both
            columns with the entire in-scope swarm. On the operator's
            35-bot fleet, checking both columns and clicking Connect is
            1,190 wires from ONE unconfirmed click, each overwriting any
            hand-tuned rate. Disconnect is the symmetric mass-destroy.

            Only the THIRD button — Disconnect All — asked, and it is the
            one nobody presses by accident. Defaults to No, matching it.
            """
            try:
                reply = QMessageBox.question(
                    self,
                    f"{verb} {n} Smart Wire" + ("s" if n != 1 else "") + "?",
                    f"{verb} {n} wire"
                    + ("s" if n != 1 else "")
                    + f" across the selected bots?\n\n{detail}\n\n"
                    + (
                        "Existing rates on these pairs will be OVERWRITTEN."
                        if verb == "Create"
                        else "This stops profit routing on every pair listed."
                    )
                    + "\n\nThis cannot be undone.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                return reply == QMessageBox.Yes
            except Exception as exc:  # noqa: BLE001
                # Unconfirmable destructive/bulk action must not proceed.
                logger.error(
                    "quick-routing confirmation unshowable (%s); refusing", exc
                )
                return False

        def _on_connect_clicked(self) -> None:
            sources = self._selected_sources()
            dests = self._selected_destinations()
            # v3.23.18 — Rate input is QLineEdit (no spinner); parse string.
            raw = ""
            try:
                raw = self._rate_input.text().strip().rstrip("%").strip()
                pct = float(raw)
            except (ValueError, AttributeError):
                self._reject(
                    f"Rate {raw!r} is not a number. Enter a percentage "
                    f"between 0 and 100."
                )
                return
            if not (0.0 <= pct <= 100.0):
                self._reject(f"Rate {pct} is outside 0–100%.")
                return
            if not sources:
                self._reject("No SOURCE bots are checked.")
                return
            if not dests:
                self._reject("No DESTINATION bots are checked.")
                return
            if pct <= 0:
                self._reject(
                    "Rate is 0% — that would create wires that route " "nothing."
                )
                return
            wires_created: list[tuple[str, str, float]] = []
            for src in sources:
                for dst in dests:
                    if src == dst:
                        continue
                    wires_created.append((src, dst, pct))
            if not wires_created:
                self._reject(
                    "Every selected pair is the same bot — a bot cannot "
                    "wire to itself."
                )
                return
            if not self._confirm_mass(
                "Create",
                len(wires_created),
                f"{len(sources)} source(s) x {len(dests)} destination(s) "
                f"at {pct}% each.",
            ):
                return
            try:
                self._viz._apply_routes_to_state(add=wires_created, remove=[])
            except Exception as exc:  # noqa: BLE001
                # _apply_routes_to_state reloads a fresh dict from disk
                # and its save is the ONLY durable effect, so a raise
                # here means no wire was created anywhere. Emitting the
                # bus events regardless would paint the canvas with
                # wires that exist in no state at all.
                logger.error(
                    "quick-routing connect: persisting %d wire(s) FAILED "
                    "(%s); no wire was created",
                    len(wires_created),
                    exc,
                )
                self._reject(
                    f"Nothing was changed — saving the routing table "
                    f"failed:\n\n{exc}"
                )
                return
            # Emit bus events so the canvas redraws
            try:
                from ..core.event_bus import get_event_bus

                bus = get_event_bus()
                for src, dst, p in wires_created:
                    bus.emit("wire.created", source_id=src, target_id=dst, pct=p)
            except Exception as exc:  # noqa: BLE001
                # v3.24.36 (C05) — was a silent pass. The wires are
                # already persisted at this point, so swallowing this
                # leaves the operator looking at a canvas that never
                # redrew after a confirmed bulk operation, with no way
                # to tell whether anything happened.
                logger.error(
                    "quick-routing connect: %d wire(s) were saved but "
                    "the redraw events FAILED (%s) — the canvas is stale, "
                    "not empty",
                    len(wires_created),
                    exc,
                )

        def _on_disconnect_clicked(self) -> None:
            sources = self._selected_sources()
            dests = self._selected_destinations()
            if not sources:
                self._reject("No SOURCE bots are checked.")
                return
            if not dests:
                self._reject("No DESTINATION bots are checked.")
                return
            pairs: list[tuple[str, str]] = []
            for src in sources:
                for dst in dests:
                    if src == dst:
                        continue
                    pairs.append((src, dst))
            if not pairs:
                self._reject(
                    "Every selected pair is the same bot — nothing to " "disconnect."
                )
                return
            # v3.24.36 (C05) — the symmetric mass-destroy. Same
            # cardinality as Connect: on a 35-bot swarm with both columns
            # checked this is 1,190 removals from one click.
            if not self._confirm_mass(
                "Disconnect",
                len(pairs),
                f"{len(sources)} source(s) x {len(dests)} " f"destination(s).",
            ):
                return
            try:
                self._viz._apply_routes_to_state(add=[], remove=pairs)
            except Exception as exc:  # noqa: BLE001
                # _apply_routes_to_state reloads a fresh dict from disk
                # and its save is the ONLY durable effect, so a raise
                # here means nothing was removed anywhere. Emitting the
                # bus events regardless would erase wires from the
                # canvas that are still live in the state file.
                logger.error(
                    "quick-routing disconnect: persisting %d removal(s) "
                    "FAILED (%s); no wire was removed",
                    len(pairs),
                    exc,
                )
                self._reject(
                    f"Nothing was changed — saving the routing table "
                    f"failed:\n\n{exc}"
                )
                return
            try:
                from ..core.event_bus import get_event_bus

                bus = get_event_bus()
                for src, dst in pairs:
                    bus.emit("wire.removed", source_id=src, target_id=dst)
            except Exception as exc:  # noqa: BLE001
                # v3.24.36 (C05) — was a silent pass. The removals are
                # already persisted, so swallowing this leaves a canvas
                # still drawing wires the state file no longer has.
                logger.error(
                    "quick-routing disconnect: %d removal(s) were saved "
                    "but the redraw events FAILED (%s) — the canvas is "
                    "stale, not wrong",
                    len(pairs),
                    exc,
                )

        def _on_disconnect_all_clicked(self) -> None:
            # Confirm
            reply = QMessageBox.question(
                self,
                "Disconnect All Wires?",
                "Disconnect ALL Smart Wires across the entire swarm? "
                "This cannot be undone.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            try:
                removed = self._viz._clear_all_routes_in_state()
            except Exception:
                removed = []
            try:
                from ..core.event_bus import get_event_bus

                bus = get_event_bus()
                for src, dst in removed:
                    bus.emit("wire.removed", source_id=src, target_id=dst)
            except Exception:  # noqa: S110
                pass

    # -------------------------------------------------------------------
    # Bot Visualization Tab
    # -------------------------------------------------------------------
    class BotVisualizationTab(QWidget):
        """Main tab containing animated bot visualizations with wire connections."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self._theme_key = "quantum"
            self._bot_widgets: dict[str, BotNodeWidget] = {}
            self._last_time = time.monotonic()
            self._wires: list[dict] = []  # [{source_id, target_id, pct, phase}]
            self._dragging_wire = False
            self._wire_start_id: str = ""
            self._wire_mouse_pos: Optional[QPointF] = None
            # v3.23.61 — Bot Swarm list-view refactor.
            #   _view_mode: "list" (default) shows the row-per-bot
            #     list with vertical-lane wires; "grid" shows the
            #     original locust grid (kept one cascade as fallback,
            #     retired in v3.23.62).
            #   _wire_opacity_pct: 0–100. Applied as an alpha
            #     multiplier in both wire canvases. Operator directive
            #     2026-07-31 mid-turn: 'We could also add a wire
            #     opacity slider.'
            self._view_mode: str = "list"
            self._wire_opacity_pct: int = 100

            # v3.15.68 — subscribe to wire.created so externally-emitted
            # wires (e.g. BotManager.restore_smart_wires_from_state on
            # startup) appear in the visualizer's internal list and get
            # drawn on the canvas. Bot creation drag-events also fire
            # wire.created so this subscription unifies both paths.
            try:
                from ..core.event_bus import get_event_bus

                _bus = get_event_bus()
                _bus.subscribe("wire.created", self._on_external_wire_created)
                _bus.subscribe("wire.removed", self._on_external_wire_removed)
            except Exception:  # noqa: S110
                pass

            layout = QVBoxLayout(self)
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(0)

            # ── Tab container ──────────────────────────────────────
            self._tabs = QTabWidget()
            self._tabs.setStyleSheet(
                "QTabWidget::pane{border:1px solid #1a1a3f;background:#070710;}"
                "QTabBar::tab{background:#0c0c1a;color:#667;border:1px solid #1a1a3f;"
                "padding:4px 12px;font-size:9px;}"
                "QTabBar::tab:selected{background:#0a0a20;color:#00FFEE;"
                "border-bottom:2px solid #00FFEE;}"
                "QTabBar::tab:hover{color:#aaa;}"
            )

            # ── TAB 1: Bot Swarm visualization ────────────────────
            viz_tab = QWidget()
            viz_lay = QVBoxLayout(viz_tab)
            viz_lay.setContentsMargins(4, 4, 4, 4)
            viz_lay.setSpacing(4)

            header = QHBoxLayout()
            header.addWidget(QLabel("Bot Swarm"))
            header.addWidget(
                QLabel(
                    "   Drag between bots to connect  •  "
                    "Right-click wire to disconnect"
                )
            )

            # v3.23.20 — Operator 2026-06-16 directive: match the Scrumming
            # Bots column-header dot style EXACTLY (main_window.py:1318):
            # Unicode '●' (revealed) / '○' (masked) glyph in a QLabel,
            # theme-cyan text color, same font as the column-header. No
            # QFrame, no border-radius, no square corners. Toggles the
            # shared bot_swarm.identifiers field id covering BOTH bot hash
            # IDs AND symbol labels.
            self._bot_swarm_privacy_dot = QLabel("●")
            self._bot_swarm_privacy_dot.setCursor(Qt.PointingHandCursor)
            self._bot_swarm_privacy_dot.setToolTip(
                "Bot Swarm identifier privacy — masks bot hash IDs + "
                "symbol labels (● revealed / ○ masked)."
            )
            self._bot_swarm_privacy_dot.mousePressEvent = (
                lambda _e: self._toggle_bot_swarm_identifier_mask()
            )
            self._refresh_bot_swarm_privacy_dot()
            header.addWidget(self._bot_swarm_privacy_dot)

            header.addStretch()

            # v3.23.18 — Privacy Mode button RESTORED to v3.23.15
            # QPushButton form per operator directive 2026-06-16:
            # "Do not move the privacy and exchange selection buttons.
            # Do not cover them up. Verify they work." The v3.23.17
            # QFrame conversion was unauthorized (no annotation on the
            # operator's spec screenshot pointed at this widget).
            # Operates on the SHARED PrivacyMaskRegistry singleton.
            self._privacy_mode_btn = QPushButton("Privacy Mode: OFF")
            self._privacy_mode_btn.setToolTip(
                "Toggle ALL privacy masks across Trading + Bot Swarm "
                "tabs (shared singleton)."
            )
            self._privacy_mode_btn.clicked.connect(self._on_privacy_mode_btn_clicked)
            self._refresh_privacy_mode_btn()
            header.addWidget(self._privacy_mode_btn)

            # v3.23.9 — Exchange selector (Q4 (c)). Filters BOTH the
            # visible swarm AND the Quick Routing checkbox scope.
            header.addWidget(QLabel("Exchange:"))
            self._exchange_combo = QComboBox()
            self._exchange_combo.addItem("All", "")
            self._exchange_combo.setToolTip(
                "Filter Bot Swarm visualizer + Quick Routing scope by "
                "exchange (Q4 (c)). Default: All."
            )
            self._exchange_combo.currentIndexChanged.connect(
                self._on_exchange_filter_changed
            )
            header.addWidget(self._exchange_combo)

            header.addWidget(QLabel("Theme:"))
            self._theme_combo = QComboBox()
            for key, theme in THEMES.items():
                self._theme_combo.addItem(theme["name"], key)
            self._theme_combo.setCurrentIndex(2)
            self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
            header.addWidget(self._theme_combo)

            # v3.23.61 — View toggle (List / Grid) + wire opacity slider.
            header.addWidget(QLabel("View:"))
            self._view_combo = QComboBox()
            self._view_combo.addItem("List", "list")
            self._view_combo.addItem("Grid", "grid")
            self._view_combo.setCurrentIndex(0)  # default: List
            self._view_combo.setToolTip(
                "List: dense row-per-bot table with vertical-lane "
                "wires (default v3.23.61).\n"
                "Grid: locust-avatar swarm view (legacy fallback)."
            )
            self._view_combo.currentIndexChanged.connect(self._on_view_mode_changed)
            header.addWidget(self._view_combo)

            header.addWidget(QLabel("Wires:"))
            from PySide6.QtWidgets import QSlider

            self._wire_opacity_slider = QSlider(Qt.Horizontal)
            self._wire_opacity_slider.setRange(0, 100)
            self._wire_opacity_slider.setValue(100)
            self._wire_opacity_slider.setFixedWidth(90)
            self._wire_opacity_slider.setToolTip(
                "Wire opacity 0–100 %. Lower for more contrast on "
                "underlying readouts; 100 = fully opaque."
            )
            self._wire_opacity_slider.valueChanged.connect(
                self._on_wire_opacity_changed
            )
            header.addWidget(self._wire_opacity_slider)

            viz_lay.addLayout(header)

            # Session 26 (2026-04-24) operator directive: the old ACTIVE BOTS
            # row-list was blocking Smart Wire drags on all but the first ~3
            # bots (operator screenshot with red X across the section).
            # Locust grid is now the single swarm view — removed the row
            # section and the redundant "VISUALIZATION" header.
            # _live_bot_rows dict kept as empty shim so legacy update paths
            # (register_live_run / update_live_run / _remove_live_bot_row)
            # remain safe no-ops; they will be deleted in Session 27.
            self._live_bot_rows: dict = {}

            # v3.23.16 — SPLIT layout: outer viz_lay has header (top) +
            # inner_hbox (below). inner_hbox holds bot grid LEFT (stretch=3)
            # + Quick Routing matrix RIGHT (stretch=2) for a 60/40 split.
            # Replaces v3.23.13 horizontal-strip layout (matrix above
            # grid full-width) which mis-read operator's annotated
            # geometry showing A/B/C as three vertical strips in the
            # upper-right zone alongside the grid.
            #
            # Bot grid: still no QScrollArea wrapper (operator 2026-06-14
            # standing directive). QGridLayout wraps locusts across rows.
            # sadp: R65 GDG (M3 visual hierarchy), R17 (operator explicit
            # override authorising layout change), R83 STM, R84 CPF.
            self._grid_widget = QWidget()
            self._grid_layout = QGridLayout(self._grid_widget)
            self._grid_layout.setSpacing(10)
            self._grid_layout.setContentsMargins(6, 6, 6, 6)
            self._grid_layout.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            # Column count — 6 is a clean fit for 112px locust + 10px spacing
            # inside the LEFT 60% of the viz tab. Grid wraps automatically
            # via index → (row, col) mapping in update_bots.
            self._grid_cols = 6
            self._empty_label = QLabel(
                "No active bots. Start bots to see visualizations."
            )
            self._empty_label.setStyleSheet("color:#555;padding:40px;")
            self._empty_label.setAlignment(Qt.AlignCenter)
            self._grid_layout.addWidget(self._empty_label, 0, 0, 1, self._grid_cols)

            # v3.23.61 — List view sibling to the grid. Both are
            # stacked in a QStackedWidget; the header View combo
            # switches which page is shown. Default page is the LIST
            # (index 0) per operator directive 2026-07-31.
            from .bot_swarm_list import BotListView, LaneWireCanvas
            from PySide6.QtWidgets import QStackedWidget

            self._bot_list = BotListView()
            # LaneWireCanvas overlays the list viewport so wire paint
            # coords map cleanly to row-Y/lane-X positions.
            self._lane_canvas = LaneWireCanvas(
                self._bot_list, parent=self._bot_list.viewport()
            )
            self._lane_canvas.setGeometry(
                0,
                0,
                self._bot_list.viewport().width(),
                self._bot_list.viewport().height(),
            )
            # Repaint the overlay whenever the list viewport resizes
            # OR scrolls (wire coords change with scroll position).
            _orig_resize = self._bot_list.viewport().resizeEvent

            def _list_viewport_resized(ev):
                self._lane_canvas.setGeometry(
                    0, 0, ev.size().width(), ev.size().height()
                )
                self._lane_canvas.raise_()
                _orig_resize(ev)

            self._bot_list.viewport().resizeEvent = _list_viewport_resized
            self._bot_list.verticalScrollBar().valueChanged.connect(
                lambda *_: self._lane_canvas.update()
            )

            self._view_stack = QStackedWidget()
            self._view_stack.addWidget(self._bot_list)  # idx 0 = List
            self._view_stack.addWidget(self._grid_widget)  # idx 1 = Grid
            self._view_stack.setCurrentIndex(0)  # default List

            self._quick_routing_matrix = QuickRoutingMatrix(self)

            inner_hbox = QHBoxLayout()
            # v3.23.17 — operator 2026-06-15: "left a void space between
            # the bot grid and the quick connection module. There is not
            # supposed to be one." spacing(0) makes matrix butt against
            # the bot grid.
            inner_hbox.setSpacing(0)
            # v3.23.18 operator 2026-06-16: "Make A wide enough to abut B"
            # = widen Quick Connect leftward to abut bot grid right edge AND
            # extend its right edge to tab right edge. Achieved by giving
            # the grid no stretch (it takes its natural sizeHint) and the
            # matrix all remaining horizontal space (stretch=1). Bot grid
            # is NOT modified — it keeps its current width via sizeHint.
            # v3.23.61 — was addWidget(self._grid_widget); now the
            # stacked view (list default, grid fallback) sits here.
            inner_hbox.addWidget(self._view_stack)
            inner_hbox.addWidget(self._quick_routing_matrix, stretch=1)
            viz_lay.addLayout(inner_hbox, stretch=1)

            self._viz_tab = viz_tab  # keep ref for wire canvas geometry
            # v3.23.12: expose Bot Swarm sub-tab for runtime-click pins
            # so QScrollArea-count assertions scope to JUST this sub-tab
            # (sibling sim_swarm + paper_swarm have legitimate scrollareas).
            self._bot_swarm_tab = viz_tab
            self._tabs.addTab(viz_tab, "⚡ Bot Swarm")

            # v3.23.9 — Hydrate Quick Routing wires from bot_state.json
            # on init. Each bot's scrumming_state.smart_wire_routes list
            # is re-emitted as a wire.created event so the existing
            # canvas redraw machinery paints them. This is parallel to
            # the v3.15.68 BotManager.restore_smart_wires_from_state
            # rehydration path at L714-717 — both paths converge in
            # _on_external_wire_created.
            try:
                painted = self._hydrate_smart_wire_routes_from_disk()
            except Exception:
                logger.exception(
                    "wire hydration failed; the wire overlay may show"
                    " fewer wires than bot_state.json holds"
                )
            else:
                logger.info(
                    "wire hydration: %d wire.created event(s) " "emitted", painted
                )

            # ── TAB 2: Simulator Swarm ─────────────────────────────
            sim_tab = QWidget()
            sim_lay = QVBoxLayout(sim_tab)
            sim_lay.setContentsMargins(8, 8, 8, 8)
            sim_lay.setSpacing(6)

            sim_hdr = QHBoxLayout()
            sim_hdr_lbl = QLabel("SIMULATOR SWARM")
            sim_hdr_lbl.setStyleSheet(
                "color:#00FFEE;font-weight:bold;font-size:10px;font-family:Consolas;"
            )
            sim_hdr.addWidget(sim_hdr_lbl)
            sim_hdr.addStretch()

            sim_add_btn = QPushButton("+ Add Sim Bot")
            sim_add_btn.setStyleSheet(
                "QPushButton{background:#0c0c1a;color:#00ff88;border:1px solid #00ff88;"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                "QPushButton:hover{background:#001a0a;}"
            )
            sim_hdr.addWidget(sim_add_btn)

            sim_run_all = QPushButton("▶ Run All")
            sim_run_all.setStyleSheet(
                "QPushButton{background:#0c0c1a;color:#00ffee;border:1px solid #00ffee;"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                "QPushButton:hover{background:#001a18;}"
            )
            sim_hdr.addWidget(sim_run_all)

            sim_stop_all = QPushButton("■ Stop All")
            sim_stop_all.setStyleSheet(
                "QPushButton{background:#0c0c1a;color:#ff3366;border:1px solid #ff3366;"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                "QPushButton:hover{background:#1a0011;}"
            )
            sim_hdr.addWidget(sim_stop_all)
            sim_lay.addLayout(sim_hdr)

            sim_desc = QLabel(
                "Run multiple simultaneous simulators. Each bot runs independently "
                "on its own asset/timeframe. Results aggregate in the summary row."
            )
            sim_desc.setStyleSheet("color:#445566;font-size:8px;")
            sim_desc.setWordWrap(True)
            sim_lay.addWidget(sim_desc)

            # Sim bot grid — scrollable
            sim_scroll = QScrollArea()
            sim_scroll.setWidgetResizable(True)
            sim_scroll.setStyleSheet(
                "QScrollArea{border:1px solid #1a1a3f;background:#070710;}"
            )
            self._sim_swarm_widget = QWidget()
            self._sim_swarm_widget.setStyleSheet("background:#070710;")
            self._sim_swarm_layout = QVBoxLayout(self._sim_swarm_widget)
            self._sim_swarm_layout.setSpacing(4)
            self._sim_swarm_layout.setContentsMargins(4, 4, 4, 4)
            self._sim_swarm_layout.addStretch()
            sim_scroll.setWidget(self._sim_swarm_widget)
            sim_lay.addWidget(sim_scroll, stretch=1)

            # Summary bar
            sim_summary = QGroupBox("SWARM SUMMARY")
            sim_summary.setStyleSheet(
                "QGroupBox{border:1px solid #1a1a3f;color:#00FFEE;"
                "font-size:8px;font-weight:bold;margin-top:6px;padding-top:6px;}"
                "QGroupBox::title{subcontrol-origin:margin;left:8px;}"
            )
            sim_sum_lay = QHBoxLayout(sim_summary)
            sim_sum_lay.setSpacing(12)
            self._sim_swarm_wins = QLabel("Wins: —")
            self._sim_swarm_pnl = QLabel("Total PnL: —")
            self._sim_swarm_trades = QLabel("Trades: —")
            for lbl in (
                self._sim_swarm_wins,
                self._sim_swarm_pnl,
                self._sim_swarm_trades,
            ):
                lbl.setStyleSheet(
                    "color:#C8D8F0;font-size:9px;font-family:Consolas;font-weight:bold;"
                )
                sim_sum_lay.addWidget(lbl)
            sim_sum_lay.addStretch()
            sim_lay.addWidget(sim_summary)

            self._sim_bots: list[dict] = []
            self._live_sim_rows: dict = {}  # sim_id → handle
            self._tabs.addTab(sim_tab, "🖥 Simulator Swarm")

            def _add_sim_bot():
                self._create_sim_bot_row()

            sim_add_btn.clicked.connect(_add_sim_bot)

            def _run_all_sims():
                for bot in self._sim_bots:
                    if not bot.get("running"):
                        btn = bot.get("run_btn")
                        if btn:
                            btn.click()

            sim_run_all.clicked.connect(_run_all_sims)

            def _stop_all_sims():
                for bot in self._sim_bots:
                    if bot.get("running"):
                        btn = bot.get("run_btn")
                        if btn:
                            btn.click()

            sim_stop_all.clicked.connect(_stop_all_sims)

            # ── TAB 3: Paper Trader Swarm ──────────────────────────
            paper_tab = QWidget()
            paper_lay = QVBoxLayout(paper_tab)
            paper_lay.setContentsMargins(8, 8, 8, 8)
            paper_lay.setSpacing(6)

            paper_hdr = QHBoxLayout()
            paper_hdr_lbl = QLabel("PAPER TRADER SWARM")
            paper_hdr_lbl.setStyleSheet(
                "color:#FFD700;font-weight:bold;font-size:10px;font-family:Consolas;"
            )
            paper_hdr.addWidget(paper_hdr_lbl)
            paper_hdr.addStretch()

            paper_add_btn = QPushButton("+ Add Paper Bot")
            paper_add_btn.setStyleSheet(
                "QPushButton{background:#0c0c1a;color:#FFD700;border:1px solid #FFD700;"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                "QPushButton:hover{background:#1a1400;}"
            )
            paper_hdr.addWidget(paper_add_btn)

            paper_start_all = QPushButton("▶ Start All")
            paper_start_all.setStyleSheet(
                "QPushButton{background:#0c0c1a;color:#00ff88;border:1px solid #00ff88;"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                "QPushButton:hover{background:#001a0a;}"
            )
            paper_hdr.addWidget(paper_start_all)

            paper_stop_all = QPushButton("■ Stop All")
            paper_stop_all.setStyleSheet(
                "QPushButton{background:#0c0c1a;color:#ff3366;border:1px solid #ff3366;"
                "border-radius:3px;padding:3px 10px;font-size:9px;font-weight:bold;}"
                "QPushButton:hover{background:#1a0011;}"
            )
            paper_hdr.addWidget(paper_stop_all)
            paper_lay.addLayout(paper_hdr)

            paper_desc = QLabel(
                "Run multiple live paper trading bots simultaneously. "
                "Each bot trades a different asset with virtual capital against real market data. "
                "Source: CoinGecko (crypto) or Yahoo Finance (equities). No geographic restrictions."
            )
            paper_desc.setStyleSheet("color:#445566;font-size:8px;")
            paper_desc.setWordWrap(True)
            paper_lay.addWidget(paper_desc)

            paper_scroll = QScrollArea()
            paper_scroll.setWidgetResizable(True)
            paper_scroll.setStyleSheet(
                "QScrollArea{border:1px solid #1a1a3f;background:#070710;}"
            )
            self._paper_swarm_widget = QWidget()
            self._paper_swarm_widget.setStyleSheet("background:#070710;")
            self._paper_swarm_layout = QVBoxLayout(self._paper_swarm_widget)
            self._paper_swarm_layout.setSpacing(4)
            self._paper_swarm_layout.setContentsMargins(4, 4, 4, 4)
            self._paper_swarm_layout.addStretch()
            paper_scroll.setWidget(self._paper_swarm_widget)
            paper_lay.addWidget(paper_scroll, stretch=1)

            # Portfolio summary
            paper_summary = QGroupBox("PORTFOLIO SUMMARY")
            paper_summary.setStyleSheet(
                "QGroupBox{border:1px solid #1a1a3f;color:#FFD700;"
                "font-size:8px;font-weight:bold;margin-top:6px;padding-top:6px;}"
                "QGroupBox::title{subcontrol-origin:margin;left:8px;}"
            )
            paper_sum_lay = QHBoxLayout(paper_summary)
            paper_sum_lay.setSpacing(12)
            self._paper_swarm_total = QLabel("Total Capital: —")
            self._paper_swarm_pnl = QLabel("Net PnL: —")
            self._paper_swarm_active = QLabel("Active Bots: 0")
            for lbl in (
                self._paper_swarm_total,
                self._paper_swarm_pnl,
                self._paper_swarm_active,
            ):
                lbl.setStyleSheet(
                    "color:#C8D8F0;font-size:9px;font-family:Consolas;font-weight:bold;"
                )
                paper_sum_lay.addWidget(lbl)
            paper_sum_lay.addStretch()
            paper_lay.addWidget(paper_summary)

            self._paper_bots: list[dict] = []
            self._live_paper_rows: dict = {}  # paper_id → handle
            self._tabs.addTab(paper_tab, "📄 Paper Swarm")

            def _add_paper_bot():
                self._create_paper_bot_row()

            paper_add_btn.clicked.connect(_add_paper_bot)

            def _start_all_paper():
                for bot in self._paper_bots:
                    if not bot.get("running"):
                        btn = bot.get("start_btn")
                        if btn:
                            btn.click()

            paper_start_all.clicked.connect(_start_all_paper)

            def _stop_all_paper():
                for bot in self._paper_bots:
                    if bot.get("running"):
                        btn = bot.get("start_btn")
                        if btn:
                            btn.click()

            paper_stop_all.clicked.connect(_stop_all_paper)

            layout.addWidget(self._tabs)

            # Wire overlay — floats above the viz sub-tab only.
            # Hidden on Simulator/Paper tabs so they receive mouse events normally.
            self._wire_canvas = _WireCanvas(self)
            self._wire_canvas.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._wire_canvas.setMouseTracking(True)
            self._wire_canvas.hide()  # starts hidden; shown only on viz tab

            def _on_tab_changed(idx):
                # v3.24.36 (C04) — the overlay belongs to GRID mode only.
                #
                # This used to call show() whenever the Bot Swarm tab was
                # active, ignoring which VIEW was showing. The call below
                # fires at construction, and the default view is List
                # (_view_stack.setCurrentIndex(0)), so the canvas was
                # shown over the list on every launch.
                #
                # It then took its geometry from _grid_widget — the
                # HIDDEN stacked page, which QStackedLayout never
                # geometries in StackOne mode — so it sat at a stale
                # 640x480 over the list's top ~452 px and 93% of its
                # width. _WireCanvas is not transparent for mouse events
                # and defines no wheelEvent, so clicks and scrolls in the
                # first ~15 rows of the DEFAULT view were swallowed.
                #
                # This is the same failure the module's own comment at
                # _reposition_wire_canvas records ("7 broken
                # interactions"): the v3.23.19 fix scoped the canvas to
                # the grid, then v3.23.61 made the grid the hidden page
                # without revisiting it. Touching the View combo once
                # fixed it and it never came back.
                #
                # _on_view_mode_changed already applies exactly this
                # rule; construction simply never did.
                _is_grid = str(getattr(self, "_view_mode", "list")) == "grid"
                if idx == 0 and _is_grid:  # Bot Swarm viz tab, Grid view
                    self._wire_canvas.show()
                    self._wire_canvas.raise_()
                    self._reposition_wire_canvas()
                else:
                    self._wire_canvas.hide()

            self._tabs.currentChanged.connect(_on_tab_changed)
            # Qt does NOT fire currentChanged for the initial tab selection.
            # Without this call, the wire overlay stays hidden at startup
            # and users cannot drag wires on the default Bot Swarm tab.
            _on_tab_changed(self._tabs.currentIndex())

            # Animation timer (30 FPS)
            self._anim_timer = QTimer(self)
            self._anim_timer.timeout.connect(self._animate)
            self._anim_timer.start(33)

        def _create_sim_bot_row(self):
            """Add a new simulator bot row to the Simulator Swarm tab."""
            idx = len(self._sim_bots) + 1
            row = QFrame()
            row.setStyleSheet(
                "QFrame{background:#0c0c1a;border:1px solid #1a1a3f;"
                "border-radius:4px;padding:2px;}"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(6)

            # Bot ID badge
            id_lbl = QLabel(f"SIM-{idx:02d}")
            id_lbl.setFixedWidth(48)
            id_lbl.setStyleSheet(
                "color:#00FFEE;font-size:9px;font-weight:bold;font-family:Consolas;"
            )
            rl.addWidget(id_lbl)

            # Asset selector
            asset_combo = QComboBox()
            asset_combo.setEditable(True)
            asset_combo.addItems(
                [
                    "BTC/USDT",
                    "ETH/USDT",
                    "SOL/USDT",
                    "XRP/USDT",
                    "BNB/USDT",
                    "ADA/USDT",
                    "DOGE/USDT",
                ]
            )
            asset_combo.setFixedWidth(110)
            asset_combo.setToolTip("Trading pair — type any symbol")
            rl.addWidget(asset_combo)

            # Preset
            preset_combo = QComboBox()
            preset_combo.addItems(
                [
                    "btc_bull",
                    "btc_range",
                    "eth_volatile",
                    "dust_coin_pump",
                    "dust_coin_sideways",
                    "high_volatility",
                    "crash_recovery",
                ]
            )
            preset_combo.setFixedWidth(120)
            rl.addWidget(preset_combo)

            # Capital
            cap_spin = QDoubleSpinBox()
            cap_spin.setRange(10, 999999)
            cap_spin.setValue(400)
            cap_spin.setPrefix("$")
            cap_spin.setFixedWidth(80)
            rl.addWidget(cap_spin)

            # Status display
            status_lbl = QLabel("IDLE")
            status_lbl.setFixedWidth(90)
            status_lbl.setStyleSheet(
                "color:#445566;font-size:8px;font-family:Consolas;font-weight:bold;"
            )
            rl.addWidget(status_lbl)

            pnl_lbl = QLabel("PnL: —")
            pnl_lbl.setFixedWidth(80)
            pnl_lbl.setStyleSheet("color:#445566;font-size:8px;font-family:Consolas;")
            rl.addWidget(pnl_lbl)

            rl.addStretch()

            # Run button
            run_btn = QPushButton("▶ Run")
            run_btn.setFixedSize(58, 22)
            run_btn.setStyleSheet(
                "QPushButton{background:#001a0a;color:#00ff88;border:1px solid #00ff88;"
                "border-radius:3px;font-size:9px;font-weight:bold;}"
                "QPushButton:hover{background:#00290f;}"
            )
            rl.addWidget(run_btn)

            # Remove button
            rem_btn = QPushButton("✕")
            rem_btn.setFixedSize(22, 22)
            rem_btn.setStyleSheet(
                "QPushButton{background:#1a0011;color:#ff3366;border:1px solid #ff3366;"
                "border-radius:3px;font-size:9px;}"
                "QPushButton:hover{background:#2a0018;}"
            )
            rl.addWidget(rem_btn)

            bot_data = {
                "widget": row,
                "idx": idx,
                "asset_combo": asset_combo,
                "preset_combo": preset_combo,
                "cap_spin": cap_spin,
                "status_lbl": status_lbl,
                "pnl_lbl": pnl_lbl,
                "run_btn": run_btn,
                "running": False,
            }
            self._sim_bots.append(bot_data)

            # Insert before the stretch
            insert_pos = self._sim_swarm_layout.count() - 1
            self._sim_swarm_layout.insertWidget(insert_pos, row)

            def _toggle_run():
                if bot_data["running"]:
                    bot_data["running"] = False
                    run_btn.setText("▶ Run")
                    run_btn.setStyleSheet(
                        "QPushButton{background:#001a0a;color:#00ff88;border:1px solid #00ff88;"
                        "border-radius:3px;font-size:9px;font-weight:bold;}"
                        "QPushButton:hover{background:#00290f;}"
                    )
                    status_lbl.setText("STOPPED")
                    status_lbl.setStyleSheet(
                        "color:#445566;font-size:8px;font-family:Consolas;font-weight:bold;"
                    )
                else:
                    bot_data["running"] = True
                    run_btn.setText("■ Stop")
                    run_btn.setStyleSheet(
                        "QPushButton{background:#1a0011;color:#ff3366;border:1px solid #ff3366;"
                        "border-radius:3px;font-size:9px;font-weight:bold;}"
                        "QPushButton:hover{background:#2a0018;}"
                    )
                    status_lbl.setText("RUNNING")
                    status_lbl.setStyleSheet(
                        "color:#00ff88;font-size:8px;font-family:Consolas;font-weight:bold;"
                    )
                self._update_sim_summary()

            run_btn.clicked.connect(_toggle_run)

            def _remove():
                self._sim_bots.remove(bot_data)
                row.setParent(None)
                row.deleteLater()
                self._update_sim_summary()

            rem_btn.clicked.connect(_remove)

        def _create_paper_bot_row(self):
            """Add a new paper trading bot row to the Paper Swarm tab."""
            idx = len(self._paper_bots) + 1
            row = QFrame()
            row.setStyleSheet(
                "QFrame{background:#0c0c1a;border:1px solid #1a1a2f;"
                "border-radius:4px;padding:2px;}"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(6)

            # ID
            id_lbl = QLabel(f"PAP-{idx:02d}")
            id_lbl.setFixedWidth(48)
            id_lbl.setStyleSheet(
                "color:#FFD700;font-size:9px;font-weight:bold;font-family:Consolas;"
            )
            rl.addWidget(id_lbl)

            # Pair / ticker entry
            pair_edit = QComboBox()
            pair_edit.setEditable(True)
            pair_edit.addItems(
                [
                    "BTC/USDT",
                    "ETH/USDT",
                    "SOL/USDT",
                    "SPY",
                    "QQQ",
                    "GLD",
                    "AAPL",
                    "NVDA",
                ]
            )
            pair_edit.setFixedWidth(110)
            pair_edit.setToolTip(
                "Crypto: any CoinGecko pair (BTC/USDT, SHIB/USDT …)\n"
                "Equity: any Yahoo Finance ticker (SPY, AAPL, TLT …)"
            )
            rl.addWidget(pair_edit)

            # Source
            src_combo = QComboBox()
            src_combo.addItems(["CoinGecko", "Kraken", "Yahoo"])
            src_combo.setFixedWidth(88)
            rl.addWidget(src_combo)

            # Capital
            cap_spin = QDoubleSpinBox()
            cap_spin.setRange(10, 999999)
            cap_spin.setValue(400)
            cap_spin.setPrefix("$")
            cap_spin.setFixedWidth(80)
            rl.addWidget(cap_spin)

            # Live status
            price_lbl = QLabel("—")
            price_lbl.setFixedWidth(72)
            price_lbl.setStyleSheet(
                "color:#00FFEE;font-size:8px;font-family:Consolas;font-weight:bold;"
            )
            rl.addWidget(price_lbl)

            pnl_lbl = QLabel("PnL: —")
            pnl_lbl.setFixedWidth(80)
            pnl_lbl.setStyleSheet("color:#445566;font-size:8px;font-family:Consolas;")
            rl.addWidget(pnl_lbl)

            status_lbl = QLabel("IDLE")
            status_lbl.setFixedWidth(56)
            status_lbl.setStyleSheet(
                "color:#445566;font-size:8px;font-family:Consolas;font-weight:bold;"
            )
            rl.addWidget(status_lbl)

            rl.addStretch()

            start_btn = QPushButton("▶ Start")
            start_btn.setFixedSize(62, 22)
            start_btn.setStyleSheet(
                "QPushButton{background:#001a0a;color:#00ff88;border:1px solid #00ff88;"
                "border-radius:3px;font-size:9px;font-weight:bold;}"
                "QPushButton:hover{background:#00290f;}"
            )
            rl.addWidget(start_btn)

            rem_btn = QPushButton("✕")
            rem_btn.setFixedSize(22, 22)
            rem_btn.setStyleSheet(
                "QPushButton{background:#1a0011;color:#ff3366;border:1px solid #ff3366;"
                "border-radius:3px;font-size:9px;}"
                "QPushButton:hover{background:#2a0018;}"
            )
            rl.addWidget(rem_btn)

            bot_data = {
                "widget": row,
                "idx": idx,
                "pair_edit": pair_edit,
                "src_combo": src_combo,
                "cap_spin": cap_spin,
                "price_lbl": price_lbl,
                "pnl_lbl": pnl_lbl,
                "status_lbl": status_lbl,
                "start_btn": start_btn,
                "running": False,
                "paper_exch": None,
            }
            self._paper_bots.append(bot_data)

            insert_pos = self._paper_swarm_layout.count() - 1
            self._paper_swarm_layout.insertWidget(insert_pos, row)

            def _toggle():
                if bot_data["running"]:
                    bot_data["running"] = False
                    start_btn.setText("▶ Start")
                    start_btn.setStyleSheet(
                        "QPushButton{background:#001a0a;color:#00ff88;border:1px solid #00ff88;"
                        "border-radius:3px;font-size:9px;font-weight:bold;}"
                        "QPushButton:hover{background:#00290f;}"
                    )
                    status_lbl.setText("STOPPED")
                    status_lbl.setStyleSheet(
                        "color:#445566;font-size:8px;font-family:Consolas;font-weight:bold;"
                    )
                else:
                    bot_data["running"] = True
                    start_btn.setText("■ Stop")
                    start_btn.setStyleSheet(
                        "QPushButton{background:#1a0011;color:#ff3366;border:1px solid #ff3366;"
                        "border-radius:3px;font-size:9px;font-weight:bold;}"
                        "QPushButton:hover{background:#2a0018;}"
                    )
                    status_lbl.setText("LIVE")
                    status_lbl.setStyleSheet(
                        "color:#FFD700;font-size:8px;font-family:Consolas;font-weight:bold;"
                    )
                self._update_paper_summary()

            start_btn.clicked.connect(_toggle)

            def _remove():
                bot_data["running"] = False
                self._paper_bots.remove(bot_data)
                row.setParent(None)
                row.deleteLater()
                self._update_paper_summary()

            rem_btn.clicked.connect(_remove)

        # ── Public live-link API ───────────────────────────────────────────────
        # Called by Simulator and PaperTraderTab to spawn / update / remove
        # their live status rows in the respective swarm tabs.

        # ════════════════════════════════════════════════════════════════
        # UNIFIED SWARM ROW FACTORY — v3.13.4
        #
        # User invariant (Session 18, Hop 4): "Paper and Sim should match
        # live exactly and always. The data feeds are what differentiate
        # them; not visuals; not function."
        #
        # This factory produces a row widget with the SAME structure and
        # SAME field semantics for all three swarm tabs (Live / Sim /
        # Paper). Only the accent color differs per tab type, matching
        # the established palette:
        #   - Live:  neon-green #00ff88  (wire/provenance color family)
        #   - Sim:   teal      #00FFEE   (simulator / cool cyan)
        #   - Paper: gold      #FFD700   (paper / warm gold)
        #
        # The factory also returns a handle dict with the same key set
        # regardless of tab type, so update_* / stop_* functions can be
        # symmetric. No test locks this invariant today; issue #69:
        # the file pyproject.toml excluded for it is not in the tree.
        #
        # Unified field schema (left → right):
        #   dot     ·  live indicator (filled when running, hollow/grey stopped)
        #   label   ·  bot/sim/paper identifier (e.g. "SIM-01", "BTC/USDT")
        #   context ·  asset descriptor (e.g. "XRP-2021", "TLT/USDT")
        #   mode    ·  engine mode (NUCLEAR, PAPER, LIVE, MEAN_REV)
        #   feed    ·  timeframe (sim) OR data source (paper/live)
        #   capital ·  "$200"
        #   status  ·  RUNNING / STOPPED / DONE
        #   metric  ·  progress% (bounded sim) OR price (live/paper)
        #   pnl     ·  "PnL +12.45"  green/red
        #   trades  ·  "42 trades"
        #
        # sadp: R60 — older P1 work (Bot Swarm sub-tab unification)

        # Tab-type accent colors: (border, label, dot)
        _SWARM_ACCENTS = {
            "live": ("#00ff88", "#00ff88", "#00ff88"),
            "sim": ("#00ff88", "#00FFEE", "#00ff88"),
            "paper": ("#FFD700", "#FFD700", "#FFD700"),
        }

        def _create_swarm_row(self, kind: str, label: str, cfg: dict):
            """Build a unified swarm row widget for kind ∈ {live,sim,paper}.

            Returns a handle dict with the SAME keys regardless of kind:
              widget, dot, id_lbl, context_lbl, mode_lbl, feed_lbl,
              cap_lbl, status_lbl, metric_lbl, pnl_lbl, trades_lbl, kind.

            This symmetry is what enables the parity invariant: any
            code that updates one tab's row works on any tab's row.
            """
            border, label_color, dot_color = self._SWARM_ACCENTS.get(
                kind, self._SWARM_ACCENTS["sim"]
            )

            # Background tint matches accent family but dark
            bg_tint = {
                "live": "#091a0e",
                "sim": "#091a0e",
                "paper": "#0e0e09",
            }.get(kind, "#0c0c1a")

            row = QFrame()
            row.setStyleSheet(
                f"QFrame{{background:{bg_tint};border:1px solid {border};"
                f"border-radius:4px;}}"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(8, 4, 8, 4)
            rl.setSpacing(6)

            # ── Field 1: live dot ──
            dot = QLabel("●")
            dot.setFixedWidth(12)
            dot.setStyleSheet(
                f"color:{dot_color};font-size:10px;font-weight:bold;"
                f"background:transparent;"
            )
            rl.addWidget(dot)

            # ── Field 2: identifier ──
            id_lbl = QLabel(label)
            id_lbl.setFixedWidth(80)
            id_lbl.setStyleSheet(
                f"color:{label_color};font-size:9px;font-weight:bold;"
                f"font-family:Consolas;background:transparent;"
            )
            rl.addWidget(id_lbl)

            # ── Field 3: context (asset-period, pair, etc.) ──
            context_lbl = QLabel(
                cfg.get("context", cfg.get("pair", cfg.get("asset", "—")))
            )
            context_lbl.setFixedWidth(88)
            context_lbl.setStyleSheet(
                "color:#00FFEE;font-size:9px;font-weight:bold;"
                "font-family:Consolas;background:transparent;"
            )
            rl.addWidget(context_lbl)

            # ── Field 4: engine mode ──
            mode_lbl = QLabel(cfg.get("mode", "—"))
            mode_lbl.setFixedWidth(72)
            mode_lbl.setStyleSheet(
                "color:#888;font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(mode_lbl)

            # ── Field 5: feed (timeframe for sim; source for paper/live) ──
            feed_lbl = QLabel(
                cfg.get("feed", cfg.get("timeframe", cfg.get("source", "—")))
            )
            feed_lbl.setFixedWidth(60)
            feed_lbl.setStyleSheet(
                "color:#556677;font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(feed_lbl)

            # ── Field 6: capital ──
            cap_lbl = QLabel(f"${cfg.get('capital', 0):,.0f}")
            cap_lbl.setFixedWidth(58)
            cap_lbl.setStyleSheet(
                "color:#556677;font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(cap_lbl)

            # ── Field 7: status ──
            initial_status = cfg.get("status", "RUNNING")
            status_lbl = QLabel(initial_status)
            status_lbl.setFixedWidth(60)
            status_lbl.setStyleSheet(
                f"color:{label_color};font-size:8px;font-family:Consolas;"
                f"font-weight:bold;background:transparent;"
            )
            rl.addWidget(status_lbl)

            # ── Field 8: metric (progress% for sim; price for live/paper) ──
            metric_lbl = QLabel(cfg.get("metric_init", "—"))
            metric_lbl.setFixedWidth(58)
            metric_lbl.setStyleSheet(
                "color:#445566;font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(metric_lbl)

            # ── Field 9: PnL ──
            pnl_lbl = QLabel("PnL —")
            pnl_lbl.setFixedWidth(88)
            pnl_lbl.setStyleSheet(
                "color:#445566;font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(pnl_lbl)

            # ── Field 10: trade count ──
            trades_lbl = QLabel("0 trades")
            trades_lbl.setFixedWidth(68)
            trades_lbl.setStyleSheet(
                "color:#445566;font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            rl.addWidget(trades_lbl)

            rl.addStretch()

            # Accent border color for later styling (stopped state)
            return {
                "kind": kind,
                "widget": row,
                "dot": dot,
                "id_lbl": id_lbl,
                "context_lbl": context_lbl,
                "mode_lbl": mode_lbl,
                "feed_lbl": feed_lbl,
                "cap_lbl": cap_lbl,
                "status_lbl": status_lbl,
                "metric_lbl": metric_lbl,
                "pnl_lbl": pnl_lbl,
                "trades_lbl": trades_lbl,
                "_accent": label_color,
                "running": True,
                "total_candles": cfg.get("candle_total", 0),
            }

        def _apply_stopped_style(self, handle: dict):
            """Apply stopped/done visual state. Shared across kinds."""
            handle["running"] = False
            handle["dot"].setStyleSheet(
                "color:#445566;font-size:10px;font-weight:bold;"
                "background:transparent;"
            )
            handle["widget"].setStyleSheet(
                "QFrame{background:#0c0c1a;border:1px solid #1a1a3f;"
                "border-radius:4px;}"
            )
            handle["status_lbl"].setStyleSheet(
                "color:#445566;font-size:8px;font-family:Consolas;"
                "font-weight:bold;background:transparent;"
            )

        def _apply_pnl_color(self, handle: dict, pnl: float):
            """PnL coloring is identical across all three kinds."""
            col = "#00ff88" if pnl >= 0 else "#ff3366"
            handle["pnl_lbl"].setText(f"PnL {pnl:+,.2f}")
            handle["pnl_lbl"].setStyleSheet(
                f"color:{col};font-size:8px;font-family:Consolas;"
                f"background:transparent;"
            )

        def register_sim_run(self, sim_id: str, label: str, cfg: dict):
            """Spawn a live-linked row in Simulator Swarm for an active sim.
            Returns a handle with .update() and .stop() methods.

            v3.13.4 — delegates layout to _create_swarm_row so Sim rows
            are structurally identical to Paper and Live rows. User
            invariant: 'data feeds differentiate; not visuals.'
            sadp: R60
            """
            # 10.5 — the registration starts here.
            _dur_t0 = time.monotonic()
            self._remove_live_sim(sim_id)

            # Translate sim-specific cfg into the unified schema
            unified_cfg = {
                "context": cfg.get("asset", cfg.get("label", label)),
                "mode": cfg.get("mode", "SIM"),
                "feed": cfg.get("timeframe", "—"),
                "capital": cfg.get("capital", 0),
                "status": "RUNNING",
                "metric_init": "0%",
                "candle_total": cfg.get("candle_total", 1),
            }
            handle = self._create_swarm_row("sim", label, unified_cfg)
            handle["sim_id"] = sim_id

            insert_pos = self._sim_swarm_layout.count() - 1
            self._sim_swarm_layout.insertWidget(insert_pos, handle["widget"])

            # The row exists and is in this layer's layout; stop
            # before the emitter block so instrumentation is not
            # billed to the registration.
            _dur_elapsed = time.monotonic() - _dur_t0
            self._live_sim_rows[sim_id] = handle
            # 10.5 — SWARM SIM REGISTRATION.
            #
            # Reads the row back OUT of this layer's store and reports its
            # `kind`, not the argument that went in. A registration that
            # lands in the wrong layer returns just as cleanly as a correct
            # one, and with three symmetric entry points taking the same
            # shape of argument that is an easy mistake to write.
            #
            # `actual` is what the store now holds; `expected` is the layer
            # this function is for. They are different expressions, so the
            # check can fail (S9).
            try:
                from src.core.signal_contract import emit as _sw_emit

                _sw_emit(
                    "swarm.11.001.postcondition.sim_run_registered",
                    actual=(self._live_sim_rows.get(sim_id, {}) or {}).get("kind"),
                    expected="sim",
                    duration=_dur_elapsed,
                    context={
                        "layer": "sim",
                        "id": str(sim_id),
                        "rows_in_layer": len(self._live_sim_rows),
                    },
                )
            except Exception:  # noqa: BLE001,S110 - advisory
                pass
            self._update_sim_summary()
            return handle

        def update_sim_run(
            self, sim_id: str, pnl: float, trades: int, candle_idx: int = 0
        ):
            """Update the live sim row. Uses shared PnL coloring."""
            h = self._live_sim_rows.get(sim_id)
            if h is None:
                return
            total = max(1, h.get("total_candles", 1))
            pct = min(100, int(candle_idx / total * 100))
            h["metric_lbl"].setText(f"{pct}%")
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            h["_pnl"] = pnl
            self._update_sim_summary()

        def stop_sim_run(self, sim_id: str, pnl: float = 0.0, trades: int = 0):
            """Mark a live sim row as stopped/complete."""
            h = self._live_sim_rows.get(sim_id)
            if h is None:
                return
            self._apply_stopped_style(h)
            h["status_lbl"].setText("DONE")
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            h["metric_lbl"].setText("100%")
            self._update_sim_summary()

        def _remove_live_sim(self, sim_id: str):
            h = self._live_sim_rows.pop(sim_id, None)
            if h:
                h["widget"].setParent(None)
                h["widget"].deleteLater()

        def register_paper_run(self, paper_id: str, label: str, cfg: dict):
            """Spawn a live-linked row in Paper Swarm for a paper session.

            v3.13.4 — uses unified _create_swarm_row so Paper rows are
            structurally identical to Sim and Live rows. Paper-specific
            fields (source, price) map to the unified schema (feed,
            metric).
            sadp: R60
            """
            # 10.5 — the registration starts here.
            _dur_t0 = time.monotonic()
            self._remove_live_paper(paper_id)

            unified_cfg = {
                "context": cfg.get("pair", "—"),
                "mode": cfg.get("mode", "PAPER"),
                "feed": cfg.get("source", "—"),
                "capital": cfg.get("capital", 0),
                "status": "LIVE",
                "metric_init": "—",
            }
            handle = self._create_swarm_row("paper", label, unified_cfg)
            handle["paper_id"] = paper_id

            insert_pos = self._paper_swarm_layout.count() - 1
            self._paper_swarm_layout.insertWidget(insert_pos, handle["widget"])

            # The row exists and is in this layer's layout; stop
            # before the emitter block so instrumentation is not
            # billed to the registration.
            _dur_elapsed = time.monotonic() - _dur_t0
            self._live_paper_rows[paper_id] = handle
            # 10.5 — SWARM PAPER REGISTRATION.
            #
            # Reads the row back OUT of this layer's store and reports its
            # `kind`, not the argument that went in. A registration that
            # lands in the wrong layer returns just as cleanly as a correct
            # one, and with three symmetric entry points taking the same
            # shape of argument that is an easy mistake to write.
            #
            # `actual` is what the store now holds; `expected` is the layer
            # this function is for. They are different expressions, so the
            # check can fail (S9).
            try:
                from src.core.signal_contract import emit as _sw_emit

                _sw_emit(
                    "swarm.11.002.postcondition.paper_run_registered",
                    actual=(self._live_paper_rows.get(paper_id, {}) or {}).get("kind"),
                    expected="paper",
                    duration=_dur_elapsed,
                    context={
                        "layer": "paper",
                        "id": str(paper_id),
                        "rows_in_layer": len(self._live_paper_rows),
                    },
                )
            except Exception:  # noqa: BLE001,S110 - advisory
                pass
            self._update_paper_summary()
            return handle

        def update_paper_run(
            self, paper_id: str, price: float, pnl: float, trades: int
        ):
            """Update the live paper row with current tick state."""
            h = self._live_paper_rows.get(paper_id)
            if h is None:
                return
            p_str = f"${price:,.4f}" if price < 1000 else f"${price:,.2f}"
            h["metric_lbl"].setText(p_str)
            h["metric_lbl"].setStyleSheet(
                "color:#00FFEE;font-size:8px;font-family:Consolas;"
                "background:transparent;"
            )
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            h["_pnl"] = pnl
            self._update_paper_summary()

        def stop_paper_run(self, paper_id: str, pnl: float = 0.0, trades: int = 0):
            """Mark a live paper row as stopped."""
            h = self._live_paper_rows.get(paper_id)
            if h is None:
                return
            self._apply_stopped_style(h)
            h["status_lbl"].setText("STOPPED")
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            self._update_paper_summary()

        def _remove_live_paper(self, paper_id: str):
            h = self._live_paper_rows.pop(paper_id, None)
            if h:
                h["widget"].setParent(None)
                h["widget"].deleteLater()

        # ── v3.13.4 — Live bot row management (Tab 1) ─────────────
        # Mirrors register_sim_run / register_paper_run exactly.
        # Same factory, same update/stop symmetry. Keeps parity
        # invariant enforceable. sadp: R60 P1

        def register_live_run(self, bot_id: str, label: str, cfg: dict):
            """Spawn a live-linked row in Bot Swarm Tab 1 for an active
            real-exchange bot. Structurally identical to Sim/Paper rows.
            cfg keys: pair|asset, mode, timeframe|source, capital
            """
            self._remove_live_bot_row(bot_id)

            unified_cfg = {
                "context": cfg.get("pair", cfg.get("asset", "—")),
                "mode": cfg.get("mode", "LIVE"),
                "feed": cfg.get("timeframe", cfg.get("source", "—")),
                "capital": cfg.get("capital", 0),
                "status": "RUNNING",
                "metric_init": cfg.get("metric_init", "—"),
            }
            handle = self._create_swarm_row("live", label, unified_cfg)
            handle["bot_id"] = bot_id

            # Hide empty-state label on first row
            if hasattr(self, "_live_rows_empty"):
                self._live_rows_empty.setVisible(False)
            insert_pos = self._live_rows_layout.count() - 1
            self._live_rows_layout.insertWidget(insert_pos, handle["widget"])

            self._live_bot_rows[bot_id] = handle
            return handle

        def update_live_run(
            self,
            bot_id: str,
            price: float = 0.0,
            pnl: float = 0.0,
            trades: int = 0,
            status: str = None,
        ):
            """Update a live bot row with current tick state.
            Symmetrical to update_sim_run / update_paper_run."""
            h = self._live_bot_rows.get(bot_id)
            if h is None:
                return
            if status is not None:
                h["status_lbl"].setText(status)
            if price > 0:
                p_str = f"${price:,.4f}" if price < 1000 else f"${price:,.2f}"
                h["metric_lbl"].setText(p_str)
                h["metric_lbl"].setStyleSheet(
                    "color:#00FFEE;font-size:8px;font-family:Consolas;"
                    "background:transparent;"
                )
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")
            h["_pnl"] = pnl

        def stop_live_run(self, bot_id: str, pnl: float = 0.0, trades: int = 0):
            """Mark a live bot row as stopped. Symmetrical to
            stop_sim_run / stop_paper_run."""
            h = self._live_bot_rows.get(bot_id)
            if h is None:
                return
            self._apply_stopped_style(h)
            h["status_lbl"].setText("STOPPED")
            self._apply_pnl_color(h, pnl)
            h["trades_lbl"].setText(f"{trades} trades")

        def _remove_live_bot_row(self, bot_id: str):
            h = self._live_bot_rows.pop(bot_id, None)
            if h:
                h["widget"].setParent(None)
                h["widget"].deleteLater()
            # Restore empty label if now empty
            if not self._live_bot_rows and hasattr(self, "_live_rows_empty"):
                self._live_rows_empty.setVisible(True)

        def _update_sim_summary(self):
            running = sum(1 for b in self._sim_bots if b.get("running"))
            running += sum(1 for h in self._live_sim_rows.values() if h.get("running"))
            total = len(self._sim_bots) + len(self._live_sim_rows)
            self._sim_swarm_wins.setText(f"Bots: {running}/{total} running")
            pnls = [h.get("_pnl", 0) for h in self._live_sim_rows.values()]
            if pnls:
                self._sim_swarm_pnl.setText(f"Total PnL: ${sum(pnls):+,.2f}")
            else:
                self._sim_swarm_pnl.setText("Total PnL: —")
            self._sim_swarm_trades.setText("Aggregate trades: —")

        def _update_paper_summary(self):
            running = sum(1 for b in self._paper_bots if b.get("running"))
            total_cap = sum(b["cap_spin"].value() for b in self._paper_bots)
            self._paper_swarm_active.setText(
                f"Active: {running}/{len(self._paper_bots)}"
            )
            self._paper_swarm_total.setText(f"Total Capital: ${total_cap:,.0f}")
            self._paper_swarm_pnl.setText("Net PnL: —")

        def _reposition_wire_canvas(self):
            """v3.23.19 — Position wire canvas over the BOT GRID area only,
            not the entire viz_tab. Operator 2026-06-16 reported 7 broken
            interactions (Privacy Mode + Exchange + Theme + Source/Dest
            checkboxes + scrollbars + Connect/Disconnect/Disconnect All +
            Rate field) on what was the 6th iteration. Root cause was this
            overlay: WA_TransparentForMouseEvents=False + covering the whole
            viz_tab + mousePressEvent only handling bot-clicks/wire right-
            click meant every other click fell through to super() which
            silently consumed it. Wires render only between bots inside the
            bot grid; the canvas only needs to overlay the grid widget.
            Wire-drag continues to work because Qt's mouse-grab keeps drag
            events on the canvas once started, even if the cursor leaves."""
            from PySide6.QtCore import QRect

            if hasattr(self, "_grid_widget") and self._grid_widget is not None:
                rect = self._grid_widget.rect()
                origin = self._grid_widget.mapTo(self, rect.topLeft())
                self._wire_canvas.setGeometry(QRect(origin, rect.size()))
            elif hasattr(self, "_viz_tab") and self._viz_tab is not None:
                rect = self._viz_tab.rect()
                origin = self._viz_tab.mapTo(self, rect.topLeft())
                self._wire_canvas.setGeometry(QRect(origin, rect.size()))
            else:
                self._wire_canvas.setGeometry(self.rect())

        def resizeEvent(self, event):
            super().resizeEvent(event)
            # v3.24.36 (C04) — reposition even while HIDDEN.
            #
            # This used to skip entirely unless the canvas was visible.
            # List is the default view and hides the canvas, so every
            # window resize, splitter drag and maximise while in List
            # mode was dropped — and switching to Grid then showed an
            # overlay carrying geometry from whenever it was last
            # visible. Nothing self-healed: _animate() calls raise_()
            # and update() each frame but never repositions.
            #
            # Keeping the geometry current costs one setGeometry on a
            # hidden widget; getting it wrong put a mouse-opaque overlay
            # in the wrong place, which is the defect this cascade is
            # about.
            self._reposition_wire_canvas()
            if self._wire_canvas.isVisible():
                self._wire_canvas.raise_()

        def _on_theme_changed(self):
            self._theme_key = self._theme_combo.currentData()
            for widget in self._bot_widgets.values():
                widget.set_theme(self._theme_key)

        # ----------------------------------------------------------
        # v3.23.9 — Privacy + Exchange selector wiring
        # ----------------------------------------------------------
        def _refresh_bot_swarm_privacy_dot(self) -> None:
            """v3.23.20 — Render Unicode '●' (revealed) / '○' (masked)
            glyph in cyan theme accent color matching Scrumming Bots
            column-header dot style (main_window.py:1318)."""
            try:
                if _get_privacy_mask_registry is None:
                    self._bot_swarm_privacy_dot.setText("●")
                    return
                reg = _get_privacy_mask_registry()
                masked = reg.is_masked("bot_swarm.identifiers")
            except Exception:  # R28-OK: defensive — never break the paint
                masked = False
            glyph = "○" if masked else "●"
            self._bot_swarm_privacy_dot.setText(glyph)
            self._bot_swarm_privacy_dot.setStyleSheet(
                "QLabel{color:#00FFEE;background:transparent;"
                "padding:0 4px;font-size:14px;}"
            )

        def _toggle_bot_swarm_identifier_mask(self) -> None:
            """Flip the shared bot_swarm.identifiers mask state. Repaints
            both the dot indicator and every locust node so the symbol +
            bot_id labels respond immediately.

            v3.23.12: replaced bare `except: return` with explicit stderr
            log + visible style change so a registry failure surfaces to
            the operator instead of silently NO-OPping the click."""
            try:
                if _get_privacy_mask_registry is None:
                    sys.stderr.write(
                        "[bot_swarm] WARNING: privacy_mask_registry "
                        "import unavailable — click NO-OP\n"
                    )
                    self._bot_swarm_privacy_dot.setStyleSheet(
                        "QFrame{background:#ff0000;border:1px solid "
                        "#cc0000;border-radius:3px;}"
                        "/* wiring-broken indicator (v3.23.12) */"
                    )
                    return
                reg = _get_privacy_mask_registry()
                cur = reg.is_masked("bot_swarm.identifiers")
                reg.set_masked("bot_swarm.identifiers", not cur)
            except Exception as exc:
                sys.stderr.write(
                    f"[bot_swarm] WARNING: identifier mask toggle "
                    f"failed: {type(exc).__name__}: {exc}\n"
                )
                self._bot_swarm_privacy_dot.setStyleSheet(
                    "QFrame{background:#ff0000;border:1px solid "
                    "#cc0000;border-radius:3px;}"
                    "/* wiring-broken indicator (v3.23.12) */"
                )
                return
            self._refresh_bot_swarm_privacy_dot()
            for w in self._bot_widgets.values():
                w.update()
            # v3.23.20 — re-render Source/Destination list items so their
            # mask state follows the toggle immediately.
            self._rebuild_quick_routing_scope_in_place()

        def _refresh_privacy_mode_btn(self) -> None:
            """v3.23.18 — Restored v3.23.15 QPushButton label + style.
            ON = green text on dark green; OFF = muted text on dark."""
            try:
                if _get_privacy_mask_registry is None:
                    self._privacy_mode_btn.setText("Privacy Mode: OFF")
                    return
                reg = _get_privacy_mask_registry()
                snap = reg.to_dict()
                any_on = any(bool(v) for v in snap.values())
            except Exception:
                any_on = False
            if any_on:
                self._privacy_mode_btn.setText("Privacy Mode: ON")
                self._privacy_mode_btn.setStyleSheet(
                    "QPushButton{background:#003822;color:#00ff88;"
                    "border:1px solid #00ff88;border-radius:3px;"
                    "padding:3px 12px;font-weight:bold;}"
                )
            else:
                self._privacy_mode_btn.setText("Privacy Mode: OFF")
                self._privacy_mode_btn.setStyleSheet(
                    "QPushButton{background:#0c0c1a;color:#aaa;"
                    "border:1px solid #2a2a3f;border-radius:3px;"
                    "padding:3px 12px;}"
                )

        def _on_privacy_mode_btn_clicked(self) -> None:
            """Toggle ALL fields globally. Operator-pinned Q1 (a):
            SHARED singleton — flip propagates to Trading tab too.

            v3.23.12: replaced bare `except: return` with explicit
            stderr log + visible style change. Per claim
            ``bot_swarm_implementation_failure_v3_23_9_postmortem``
            silent-swallow at this site contributed to the operator
            symptom 'Privacy Mode button does not work'."""
            try:
                if _get_privacy_mask_registry is None:
                    sys.stderr.write(
                        "[bot_swarm] WARNING: privacy_mask_registry "
                        "import unavailable — Privacy Mode click "
                        "NO-OP\n"
                    )
                    self._privacy_mode_btn.setStyleSheet(
                        "QPushButton{background:#ff0000;color:white;"
                        "border:1px solid #cc0000;padding:3px 12px;}"
                        "/* wiring-broken (v3.23.18) */"
                    )
                    return
                reg = _get_privacy_mask_registry()
                snap = reg.to_dict()
                any_on = any(bool(v) for v in snap.values())
                reg.set_all(not any_on)
            except Exception as exc:
                sys.stderr.write(
                    f"[bot_swarm] WARNING: Privacy Mode toggle "
                    f"failed: {type(exc).__name__}: {exc}\n"
                )
                self._privacy_mode_btn.setStyleSheet(
                    "QPushButton{background:#ff0000;color:white;"
                    "border:1px solid #cc0000;padding:3px 12px;}"
                    "/* wiring-broken (v3.23.18) */"
                )
                return
            self._refresh_privacy_mode_btn()
            self._refresh_bot_swarm_privacy_dot()
            for w in self._bot_widgets.values():
                w.update()
            # v3.23.20 — re-render Source/Destination list items so their
            # mask state follows the global Privacy Mode toggle.
            self._rebuild_quick_routing_scope_in_place()

        def _rebuild_quick_routing_scope_in_place(self) -> None:
            """v3.23.20 — Re-call rebuild_scope on the matrix with the
            currently-displayed bot_id set so list-item labels re-render
            against the latest registry mask state. No-op if the matrix
            has not yet been populated."""
            mx = getattr(self, "_quick_routing_matrix", None)
            if mx is None:
                return
            ids = list(getattr(mx, "_last_scope_ids", []) or [])
            if not ids:
                # No prior scope tracked — read the QListWidget items
                # to rebuild from current state.
                ids = [
                    mx._source_list.item(i).data(Qt.UserRole) or ""
                    for i in range(mx._source_list.count())
                ]
                ids = [b for b in ids if b]
            mx.rebuild_scope(ids)

        def _bot_exchange_id(self, bot_id: str) -> str:
            """This bot's exchange id, from the status data it was
            rendered with. Returns "" if unknown.

            v3.24.41 (C03 / SWARM-4.4). The previous implementation
            imported ``get_bot_container`` from ..trading.bot_container.
            That symbol DOES NOT EXIST — zero definitions, zero
            references anywhere in src/. So the first branch raised
            ImportError on every single call, was swallowed by a bare
            ``except Exception: pass``, and every lookup fell through to
            the fallback: a full StateManager().load_state() parse of
            the entire bot_state.json to retrieve one string.

            _refresh_visible_bots calls this once per bot, so changing
            the exchange filter on a 35-bot swarm was 35 complete
            re-reads of the state file. The value it wanted was already
            in memory: get_status() emits "exchange", and the widget
            keeps that dict as _bot_data.
            """
            w = self._bot_widgets.get(bot_id)
            data = getattr(w, "_bot_data", None) if w is not None else None
            if isinstance(data, dict):
                return str(data.get("exchange", "") or "")
            return ""

        def _all_bot_ids_in_scope(self) -> list[str]:
            """Set of bot_ids that should be considered by the Quick
            Routing matrix. Filters by the current Exchange selector."""
            sel = ""
            try:
                sel = str(self._exchange_combo.currentData() or "")
            except Exception:
                sel = ""
            ids = list(self._bot_widgets.keys())
            if not sel:
                return ids
            return [bid for bid in ids if self._bot_exchange_id(bid) == sel]

        def _rebuild_exchange_selector_items(self) -> None:
            """Repopulate Exchange combo from distinct bot.config
            exchange_ids across the current swarm + an "All" entry."""
            try:
                combo = self._exchange_combo
            except AttributeError:
                return
            current = ""
            try:
                current = str(combo.currentData() or "")
            except Exception:
                current = ""
            distinct = set()
            for bid in self._bot_widgets.keys():
                eid = self._bot_exchange_id(bid)
                if eid:
                    distinct.add(eid)
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("All", "")
            for eid in sorted(distinct):
                combo.addItem(eid, eid)
            # Restore prior selection if still present
            if current:
                for i in range(combo.count()):
                    if str(combo.itemData(i) or "") == current:
                        combo.setCurrentIndex(i)
                        break
            combo.blockSignals(False)

        def _refresh_visible_bots(self) -> None:
            """Q4 (c): visibility filter by Exchange. Bots not matching
            the current selector are hidden (their widgets stay alive so
            wire endpoints don't dangle when filter changes)."""
            sel = ""
            try:
                sel = str(self._exchange_combo.currentData() or "")
            except Exception:
                sel = ""
            for bid, w in self._bot_widgets.items():
                if not sel:
                    w.setVisible(True)
                    continue
                w.setVisible(self._bot_exchange_id(bid) == sel)

        def _refresh_quick_routing_scope(self) -> None:
            """Q4 (c): the Quick Routing matrix re-syncs its checkbox
            lists to the currently-filtered set."""
            mx = getattr(self, "_quick_routing_matrix", None)
            if mx is not None and hasattr(mx, "rebuild_scope"):
                try:  # noqa: SIM105
                    mx.rebuild_scope(self._all_bot_ids_in_scope())
                except Exception:  # noqa: S110
                    pass

        def _on_exchange_filter_changed(self, *_a) -> None:
            self._refresh_visible_bots()
            self._refresh_quick_routing_scope()
            if hasattr(self, "_wire_canvas") and self._wire_canvas:
                self._wire_canvas.update()

        # v3.23.61 — View mode + wire opacity handlers -------------
        def _on_view_mode_changed(self, *_a) -> None:
            try:
                mode = str(self._view_combo.currentData() or "list")
            except Exception:  # noqa: BLE001
                mode = "list"
            self._view_mode = mode
            _idx = 0 if mode == "list" else 1
            self._view_stack.setCurrentIndex(_idx)
            # The old top-level wire canvas is only meaningful in
            # grid mode (its geometry lives in tab coordinates over
            # the locust grid); hide it when list is active so it
            # doesn't paint stale wires over the list.
            if hasattr(self, "_wire_canvas") and self._wire_canvas:
                self._wire_canvas.setVisible(mode == "grid")
                # v3.24.36 (C04) — reposition ON SHOW. Switching to Grid
                # used to reveal the canvas with whatever geometry it
                # last had, which after any resize in List mode was
                # wrong. The stacked page has just become visible, so
                # this is the first moment its real rect exists.
                if mode == "grid":
                    self._reposition_wire_canvas()
                    self._wire_canvas.raise_()
            # LaneWireCanvas is a child of the list viewport, so
            # it stays put; just repaint.
            if hasattr(self, "_lane_canvas") and self._lane_canvas:
                self._lane_canvas.update()

        def _on_wire_opacity_changed(self, value: int) -> None:
            self._wire_opacity_pct = int(value)
            if hasattr(self, "_wire_canvas") and self._wire_canvas:
                self._wire_canvas.update()
            if hasattr(self, "_lane_canvas") and self._lane_canvas:
                self._lane_canvas.set_opacity_pct(self._wire_opacity_pct)

        def _refresh_bot_list_rows(self) -> None:
            """Rebuild the BotListView from _bot_widgets. Called in
            update_bots after the grid populate finishes so the two
            views stay in sync. Inflow/Outflow default to $0.00
            pending the v3.23.62 SWOS integration."""
            if not hasattr(self, "_bot_list"):
                return
            # v3.23.62 — pre-compute per-bot outbound wire rate sum
            # so the % Out column shows "how much profit this bot is
            # exporting". A bot with two 25 % outbound wires reads
            # 50 %; four 30 % reads 120 % (over-committed, red).
            _outflow_pct_by_bot: dict[str, float] = {}
            for _wire in self._wires:
                _sid = str(_wire.get("source_id", "") or "")
                if not _sid:
                    continue
                _outflow_pct_by_bot[_sid] = _outflow_pct_by_bot.get(_sid, 0.0) + float(
                    _wire.get("pct", 0) or 0
                )
            rows: list[dict] = []
            for bid in self._bot_widgets:
                _w = self._bot_widgets[bid]
                _data = getattr(_w, "_bot_data", {}) or {}
                _sym = str(_data.get("symbol", "") or "")
                # v3.23.60 — read YTD sums when the exchange sync has
                # populated them. Real per-wire attribution lands
                # with v3.23.62 SWOS design cascade.
                _stats = _data.get("stats", {}) or {}
                _in = float(
                    _stats.get("ytd_folded_usd", 0.0)
                    or _data.get("ytd_folded_usd", 0.0)
                    or 0.0
                )
                _out = float(
                    _stats.get("ytd_scrummed_usd", 0.0)
                    or _data.get("ytd_scrummed_usd", 0.0)
                    or 0.0
                )
                rows.append(
                    {
                        # v3.24.41 (C03 / SWARM-4.11) — mask at the producer.
                        # bot_swarm_list.py has ZERO mask_or references, so
                        # whatever is handed to set_bots is rendered
                        # verbatim: the list view showed real symbols while
                        # the grid beside it showed ****. Same field id as
                        # the locust labels.
                        "bot_id": bid,
                        "symbol": _mask_or(_sym, "bot_swarm.identifiers"),
                        "inflow_usd": _in,
                        "outflow_usd": _out,
                        "outflow_pct": _outflow_pct_by_bot.get(bid, 0.0),
                    }
                )
            self._bot_list.set_bots(rows)
            # Feed wires to the lane canvas so vertical segments
            # align with row positions after the populate.
            self._lane_canvas.set_wires(self._wires)

        # ----------------------------------------------------------
        # v3.23.9 — Persistence helpers for smart_wire_routes
        # ----------------------------------------------------------
        # Q5 (a): routing state lives on each source bot's
        # scrumming_state.smart_wire_routes list in bot_state.json.
        # We read and write the file directly here so the matrix
        # works even when no live BotContainer is attached (e.g.
        # GUI smoke-test with paused bots).
        # ----------------------------------------------------------
        def _load_bot_state_dict(self) -> dict:
            try:
                from ..core.state_manager import StateManager

                return StateManager().load_state() or {}
            except Exception:
                return {}

        def _save_bot_state_dict(self, state: dict) -> None:
            """Atomic write back to bot_state.json.

            SECOND WRITER WARNING (v3.24.36, C02). This is not the
            primary persistence path — ``StateManager.save_state`` is —
            and the two have never been reconciled:

            * **Shared staging file.** Both stage through
              ``bot_state.tmp`` (``self._path.with_suffix(".tmp")`` in
              StateManager, ``p.with_suffix(".tmp")`` here). Two writers,
              one temp name. No interleaving has been demonstrated today
              (asyncio is pumped on the Qt main thread and no nested loop
              opens between load and write), but the collision is
              structural, and it becomes corruption of the live position
              file the moment either writer moves off the GUI thread.
            * **What it exists for does not survive.** Its only purpose
              is maintaining ``scrumming_state.smart_wire_routes``, and
              ``export_scrumming_state`` does not emit that key — so the
              next 60-second save rebuilds scrumming_state without it.
              Measured on the live file 2026-08-06: 0 of 35 bots carry
              the key, while the durable channel (top-level
              ``smart_wires``) holds all 40 wires.

            The silent ``except: pass`` is gone: a failed write to the
            operator's position file is not a cosmetic miss, and this
            one could fail for weeks with no signal.
            """
            try:
                from pathlib import Path
                import json
                import os

                p = Path.home() / ".acervator" / "bot_state.json"
                p.parent.mkdir(parents=True, exist_ok=True)
                # v3.24.36 (C02) — DISTINCT staging file. This used to
                # be p.with_suffix(".tmp"), i.e. bot_state.tmp, which is
                # byte-for-byte the same path StateManager.save_state
                # stages through. Two independent writers sharing one
                # temp name means either can rename the other's partial
                # write over the live position file. The pid suffix
                # makes that impossible without changing any behaviour.
                tmp = p.with_suffix(f".gui.{os.getpid()}.tmp")
                tmp.write_text(
                    json.dumps(state, indent=2, default=str), encoding="utf-8"
                )
                tmp.replace(p)
            except Exception as exc:  # noqa: BLE001 - GUI must not die
                logger.error(
                    "bot_visualizer: direct write to bot_state.json "
                    "FAILED (%s: %s). Wire routing changes made in the "
                    "GUI were not persisted by this path; the durable "
                    "smart_wires channel is unaffected.",
                    type(exc).__name__,
                    exc,
                )

        def _apply_routes_to_state(
            self, add: list[tuple[str, str, float]], remove: list[tuple[str, str]]
        ) -> None:
            """Mutate bot_state.json — for each source bot, update its
            scrumming_state.smart_wire_routes list. ``add`` entries are
            deduped by dest_bot_id (replace pct if dest already wired).
            Saves immediately."""
            state = self._load_bot_state_dict()
            bots = state.setdefault("bots", {})

            def _ensure_routes(bid: str) -> list:
                bot = bots.setdefault(bid, {})
                scr = bot.setdefault("scrumming_state", {})
                routes = scr.setdefault("smart_wire_routes", [])
                if not isinstance(routes, list):
                    routes = []
                    scr["smart_wire_routes"] = routes
                return routes

            for src, dst, pct in add:
                routes = _ensure_routes(src)
                # Dedupe by dest_bot_id
                replaced = False
                for entry in routes:
                    if isinstance(entry, dict) and (entry.get("dest_bot_id") == dst):
                        entry["pct"] = float(pct)
                        replaced = True
                        break
                if not replaced:
                    routes.append({"dest_bot_id": dst, "pct": float(pct)})

            for src, dst in remove:
                if src not in bots:
                    continue
                routes = _ensure_routes(src)
                new_routes = [
                    e
                    for e in routes
                    if not (isinstance(e, dict) and e.get("dest_bot_id") == dst)
                ]
                bots[src]["scrumming_state"]["smart_wire_routes"] = new_routes

            self._save_bot_state_dict(state)

        def _clear_all_routes_in_state(self) -> list[tuple[str, str]]:
            """Disconnect All: zero out every bot's smart_wire_routes
            list. Returns the (source, dest) pairs that existed before
            so the caller can emit wire.removed events for each."""
            state = self._load_bot_state_dict()
            bots = state.get("bots", {}) if isinstance(state, dict) else {}
            removed_pairs: list[tuple[str, str]] = []
            for bid, bot in bots.items():
                if not isinstance(bot, dict):
                    continue
                scr = bot.get("scrumming_state", {})
                if not isinstance(scr, dict):
                    continue
                routes = scr.get("smart_wire_routes", [])
                if isinstance(routes, list):
                    for entry in routes:
                        if isinstance(entry, dict):
                            dst = entry.get("dest_bot_id", "")
                            if dst:
                                removed_pairs.append((bid, str(dst)))
                scr["smart_wire_routes"] = []
            self._save_bot_state_dict(state)
            return removed_pairs

        def _report_wire_hydration_shortfall(
            self,
            painted: int,
            seen: int,
            rejected: int,
        ) -> None:
            """Record any route on disk that did not reach the canvas.

            Silent when every route was painted, so the record
            always means a real shortfall and never just that
            hydration ran.
            """
            if painted == seen:
                return
            logger.warning(
                "wire hydration: %d of %d route(s) in"
                " bot_state.json painted -- %d rejected by the"
                " bus, %d unusable; the wire overlay"
                " under-reports the state file",
                painted,
                seen,
                rejected,
                seen - painted - rejected,
            )

        def _hydrate_smart_wire_routes_from_disk(self) -> int:
            """B.6: on init, replay each bot's smart_wire_routes as
            wire.created bus events so the canvas redraw machinery
            paints them. Returns count of events emitted. Parallel to
            v3.15.68 BotManager.restore_smart_wires_from_state at
            L714-717 — both converge in _on_external_wire_created.

            H4: every route on disk that does not reach the canvas
            is counted and recorded before this returns. A
            shortfall with no record anywhere is the "40 wires,
            $0.00 routed" failure smart_wire.py:490 already
            names."""
            state = self._load_bot_state_dict()
            bots = state.get("bots", {}) if isinstance(state, dict) else {}
            n = 0
            seen = 0
            rejected = 0
            try:
                from ..core.event_bus import get_event_bus

                bus = get_event_bus()
            except Exception:
                logger.exception(
                    "wire hydration: no event bus, so no route in"
                    " bot_state.json reaches the canvas"
                )
                return 0
            for bid, bot in bots.items():
                if not isinstance(bot, dict):
                    continue
                scr = bot.get("scrumming_state", {})
                routes = (
                    scr.get("smart_wire_routes", []) if isinstance(scr, dict) else []
                )
                if not isinstance(routes, list):
                    continue
                for entry in routes:
                    seen += 1
                    if not isinstance(entry, dict):
                        continue
                    dst = str(entry.get("dest_bot_id", "") or "")
                    try:
                        pct = float(entry.get("pct", 0) or 0)
                    except Exception:
                        pct = 0.0
                    if not dst or pct <= 0:
                        continue
                    try:
                        bus.emit(
                            "wire.created", source_id=str(bid), target_id=dst, pct=pct
                        )
                        n += 1
                    except Exception:
                        rejected += 1
                        logger.warning(
                            "wire hydration: the bus rejected route"
                            " %s -> %s (%s%%), so that wire is not"
                            " painted",
                            bid,
                            dst,
                            pct,
                            exc_info=True,
                        )
            self._report_wire_hydration_shortfall(n, seen, rejected)
            return n

        def _animate(self):
            now = time.monotonic()
            dt = now - self._last_time
            self._last_time = now
            for widget in self._bot_widgets.values():
                widget.animate(dt)
            # Animate wire glow
            for wire in self._wires:
                wire["phase"] = wire.get("phase", 0) + dt * 2.5
            if self._wires or self._dragging_wire:
                # Session 26 fix: operator reported wires were not visible.
                # Keep the overlay on top of the grid widgets every frame
                # so Z-order cannot drift as bots are added/removed or as
                # Qt re-stacks during scroll events. raise_() is idempotent
                # and cheap (no-op if already on top).
                if self._wire_canvas.isVisible():
                    self._wire_canvas.raise_()
                self._wire_canvas.update()
                # v3.23.62 — also repaint the list-view lane canvas
                # so its pulses animate at the same 30 fps cadence.
                if hasattr(self, "_lane_canvas") and self._lane_canvas:
                    self._lane_canvas.raise_()
                    self._lane_canvas.update()

        def _get_bot_center(self, bot_id: str) -> Optional[QPointF]:
            """Get the center of a bot widget in canvas coordinates."""
            w = self._bot_widgets.get(bot_id)
            if not w:
                return None
            # Map widget center to the canvas coordinate space
            center = QPointF(w.width() / 2, w.height() / 2)
            global_pt = w.mapToGlobal(center.toPoint())
            local_pt = self._wire_canvas.mapFromGlobal(global_pt)
            return QPointF(local_pt)

        def _bot_at_pos(self, pos: QPointF) -> str:
            """Find which bot widget is at a canvas position."""
            for bid, w in self._bot_widgets.items():
                global_pt = self._wire_canvas.mapToGlobal(pos.toPoint())
                local_pt = w.mapFromGlobal(global_pt)
                if w.rect().contains(local_pt):
                    return bid
            return ""

        def _start_wire_drag(self, bot_id: str, pos: QPointF):
            self._dragging_wire = True
            self._wire_start_id = bot_id
            self._wire_mouse_pos = pos

        def _update_wire_drag(self, pos: QPointF):
            self._wire_mouse_pos = pos
            self._wire_canvas.update()

        def _confirm_wire_removal(self, pairs: list, why: str = "") -> bool:
            """Ask before destroying live Smart Wire(s). True to proceed.

            v3.24.36 (C06b). ``remove_wire`` emits ``wire.removed``,
            which reaches ``SmartWireManager.unregister_wire`` — engine
            state, not a drawing. There is no undo.

            The confirmation gap this closes was inverted: the button
            nobody presses by accident (Disconnect All) already asked,
            while the two paths reachable from an ordinary mouse slip
            did not. This mirrors that dialog deliberately, including
            defaulting to No, so a stray Return keypress cannot destroy
            a wire either.

            The percentage is shown because it is the part that cannot
            be reconstructed from memory: the operator knows which bots
            were wired, rarely at what rate.
            """
            if not pairs:
                return False
            lines = []
            for src, dst in pairs:
                pct = next(
                    (
                        w.get("pct")
                        for w in self._wires
                        if w.get("source_id") == src and w.get("target_id") == dst
                    ),
                    None,
                )
                pct_txt = f" at {pct}%" if pct is not None else ""
                lines.append(f"  • {src[:8]} → {dst[:8]}{pct_txt}")
            body = (
                f"{why}\n\n" if why else ""
            ) + f"Disconnect {len(pairs)} Smart Wire" + (
                "s" if len(pairs) != 1 else ""
            ) + "?\n\n" + "\n".join(
                lines
            ) + "\n\nThis stops profit routing between these bots and " "cannot be undone."
            try:
                reply = QMessageBox.question(
                    self,
                    "Disconnect Smart Wire?",
                    body,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                return reply == QMessageBox.Yes
            except Exception as exc:  # noqa: BLE001
                # If the dialog cannot be shown, REFUSE. An unconfirmable
                # destructive action must not proceed unconfirmed.
                logger.error(
                    "wire-removal confirmation could not be shown (%s); "
                    "refusing the removal",
                    exc,
                )
                return False

        def _finish_wire_drag(self, pos: QPointF):
            target_id = self._bot_at_pos(pos)
            start_id = self._wire_start_id
            self._dragging_wire = False
            self._wire_mouse_pos = None

            if not start_id:
                self._wire_canvas.update()
                return

            if target_id and target_id != start_id:
                # Check for duplicate — if exists, this is a disconnect drag
                existing = [
                    w
                    for w in self._wires
                    if w["source_id"] == start_id and w["target_id"] == target_id
                ]
                if existing:
                    # Dragging between already-connected bots = disconnect.
                    #
                    # v3.24.36 (C06b) — now confirmed. The header
                    # advertises "Drag between bots to connect", so this
                    # is the ADVERTISED gesture silently destroying an
                    # existing wire when the pair happens to be wired
                    # already. remove_wire emits wire.removed, which
                    # reaches SmartWireManager.unregister_wire — real
                    # engine state, no undo.
                    if not self._confirm_wire_removal(
                        [(start_id, target_id)],
                        "Dragging between two already-connected bots "
                        "disconnects them.",
                    ):
                        self._wire_start_id = ""
                        self._wire_canvas.update()
                        return
                    self.remove_wire(start_id, target_id)
                else:
                    self._show_wire_config(start_id, target_id)
            elif not target_id:
                # Dragged to empty space — check if start bot has any wires to disconnect
                # Find the wire closest to the drag start point and remove it
                wire_from_start = [w for w in self._wires if w["source_id"] == start_id]
                if len(wire_from_start) == 1:
                    # v3.24.36 (C06b) — the sharpest edge in this file.
                    #
                    # mousePressEvent starts a drag on ANY left-press
                    # landing on a locust — no handle, no hotspot, no
                    # modifier — and mouseReleaseEvent calls this
                    # unconditionally. So a press that slips 2-3 px off
                    # the locust edge counts as "dragged to empty space"
                    # and, if that bot has exactly one outgoing wire,
                    # deleted it outright.
                    #
                    # Note the asymmetry that made this easy to miss:
                    # with MORE than one wire the operator gets a picker
                    # (below). With exactly one, there was nothing.
                    # Having fewer wires was more dangerous.
                    if not self._confirm_wire_removal(
                        [
                            (
                                wire_from_start[0]["source_id"],
                                wire_from_start[0]["target_id"],
                            )
                        ],
                        "Releasing a drag on empty space disconnects "
                        "the source bot's only outgoing wire.",
                    ):
                        self._wire_start_id = ""
                        self._wire_canvas.update()
                        return
                    self.remove_wire(
                        wire_from_start[0]["source_id"], wire_from_start[0]["target_id"]
                    )
                elif len(wire_from_start) > 1:
                    # Multiple wires — show disconnect picker
                    self._show_disconnect_picker(start_id, pos)

            self._wire_start_id = ""
            self._wire_canvas.update()

        def _show_disconnect_picker(self, bot_id: str, pos: QPointF):
            """Show menu to pick which wire to disconnect when bot has multiple."""
            menu = QMenu(self)
            menu.setStyleSheet(
                "QMenu { background: #1a1a2f; color: #e0e0f0; border: 1px solid #3a3a5f; }"
                "QMenu::item:selected { background: #2a2a4f; }"
            )

            outgoing = [w for w in self._wires if w["source_id"] == bot_id]
            incoming = [w for w in self._wires if w["target_id"] == bot_id]

            if outgoing:
                header = menu.addAction("Disconnect outgoing wire:")
                header.setEnabled(False)
                for w in outgoing:
                    tgt = w["target_id"][:8]
                    act = menu.addAction(f"  → {tgt} ({w['pct']}%)")
                    act.setData(("out", w["source_id"], w["target_id"]))

            if incoming:
                if outgoing:
                    menu.addSeparator()
                header = menu.addAction("Disconnect incoming wire:")
                header.setEnabled(False)
                for w in incoming:
                    src = w["source_id"][:8]
                    act = menu.addAction(f"  ← {src} ({w['pct']}%)")
                    act.setData(("in", w["source_id"], w["target_id"]))

            menu.addSeparator()
            menu.addAction("Cancel")

            global_pos = self._wire_canvas.mapToGlobal(pos.toPoint())
            result = menu.exec(global_pos)

            if result and result.data():
                _, src, tgt = result.data()
                self.remove_wire(src, tgt)

        def _show_wire_config(self, source_id: str, target_id: str):
            """Show popup to configure wire percentage."""
            from PySide6.QtWidgets import (
                QDialog,
                QFormLayout,
                QSpinBox,
                QDialogButtonBox,
            )

            dlg = QDialog(self)
            dlg.setWindowTitle("Configure Profit Wire")
            dlg.setMinimumWidth(350)
            form = QVBoxLayout(dlg)

            form.addWidget(
                QLabel(
                    f"Route profits from bot {source_id[:8]}\n"
                    f"to bot {target_id[:8]}"
                )
            )

            params = QFormLayout()
            pct_spin = QSpinBox()
            pct_spin.setRange(1, 100)
            pct_spin.setValue(50)
            pct_spin.setSuffix("% of realized profit")
            params.addRow("Routing:", pct_spin)
            form.addLayout(params)

            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            form.addWidget(btns)

            if dlg.exec() == QDialog.Accepted:
                pct = pct_spin.value()
                self._wires.append(
                    {
                        "source_id": source_id,
                        "target_id": target_id,
                        "pct": pct,
                        "phase": 0.0,
                    }
                )
                # Update source bot config
                from ..core.event_bus import get_event_bus

                bus = get_event_bus()
                bus.emit(
                    "bot.log",
                    bot_id=source_id,
                    message=f"WIRE CONNECTED: {pct}% of profit → bot {target_id[:8]}",
                )
                bus.emit(
                    "wire.created", source_id=source_id, target_id=target_id, pct=pct
                )

        def _on_external_wire_created(self, event) -> None:
            """v3.15.68 — handler for wire.created bus events. Adds
            the wire to ``self._wires`` if not already present
            (idempotent). Used by BotManager state restore to
            rehydrate the Bot Swarm view on startup."""
            try:
                data = getattr(event, "data", None) or {}
                src = str(data.get("source_id", "") or "")
                tgt = str(data.get("target_id", "") or "")
                pct = float(data.get("pct", 0) or 0)
                if not src or not tgt or pct <= 0:
                    return
                # Skip if this wire is already in the visualizer's list
                # (avoids double-add when the user just dragged it —
                # the drag path also emits wire.created).
                for w in self._wires:
                    if w.get("source_id") == src and w.get("target_id") == tgt:
                        # Update pct if it changed
                        w["pct"] = pct
                        return
                self._wires.append(
                    {
                        "source_id": src,
                        "target_id": tgt,
                        "pct": pct,
                        "phase": 0.0,
                    }
                )
                # Trigger a canvas repaint so the wire is visible.
                if hasattr(self, "_wire_canvas") and self._wire_canvas:
                    self._wire_canvas.update()
            except Exception:  # noqa: S110
                pass

        def _on_external_wire_removed(self, event) -> None:
            """v3.15.68 — handler for wire.removed bus events. Removes
            matching wires from ``self._wires`` (idempotent)."""
            try:
                data = getattr(event, "data", None) or {}
                src = str(data.get("source_id", "") or "")
                tgt = str(data.get("target_id", "") or "")
                if not src or not tgt:
                    return
                self._wires = [
                    w
                    for w in self._wires
                    if not (w.get("source_id") == src and w.get("target_id") == tgt)
                ]
                if hasattr(self, "_wire_canvas") and self._wire_canvas:
                    self._wire_canvas.update()
            except Exception:  # noqa: S110
                pass

        def remove_wire(self, source_id: str, target_id: str):
            self._wires = [
                w
                for w in self._wires
                if not (w["source_id"] == source_id and w["target_id"] == target_id)
            ]
            self._wire_canvas.update()
            from ..core.event_bus import get_event_bus

            get_event_bus().emit(
                "bot.log",
                bot_id=source_id,
                message=f"WIRE DISCONNECTED from bot {target_id[:8]}",
            )
            get_event_bus().emit(
                "wire.removed", source_id=source_id, target_id=target_id
            )

        def _wire_at_pos(self, pos: QPointF, threshold: float = 12.0) -> dict | None:
            """Find the wire closest to a canvas position, within threshold."""
            best_wire = None
            best_dist = threshold

            for wire in self._wires:
                src = self._get_bot_center(wire["source_id"])
                tgt = self._get_bot_center(wire["target_id"])
                if not src or not tgt:
                    continue

                # Get offset for this wire (bidirectional routing)
                offset = self._get_wire_offset(wire)

                # Point-to-segment distance (with offset applied to midpoint)
                mid_y_shift = offset
                # Approximate: check distance to a few sample points along the wire
                for t in [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]:
                    px = src.x() + (tgt.x() - src.x()) * t
                    py = src.y() + (tgt.y() - src.y()) * t
                    # Add bezier offset at midpoint (max at t=0.5)
                    curve_offset = mid_y_shift * 4 * t * (1 - t)
                    py += curve_offset
                    dist = math.sqrt((pos.x() - px) ** 2 + (pos.y() - py) ** 2)
                    if dist < best_dist:
                        best_dist = dist
                        best_wire = wire

            return best_wire

        def _is_bidirectional(self, source_id: str, target_id: str) -> bool:
            """Check if a reverse wire exists (target→source)."""
            return any(
                w["source_id"] == target_id and w["target_id"] == source_id
                for w in self._wires
            )

        def _get_wire_offset(self, wire: dict) -> float:
            """
            Get vertical offset for a wire to prevent bidirectional overlap.
            Left-to-right = lower slot (positive offset), right-to-left = upper slot (negative).
            Only offsets if the reverse wire also exists.
            """
            src_center = self._get_bot_center(wire["source_id"])
            tgt_center = self._get_bot_center(wire["target_id"])
            if not src_center or not tgt_center:
                return 0.0

            if not self._is_bidirectional(wire["source_id"], wire["target_id"]):
                return 0.0  # No offset needed for unidirectional

            # Determine direction: source left of target = "left to right"
            if src_center.x() <= tgt_center.x():
                return 25.0  # Lower slot
            else:
                return -25.0  # Upper slot

        def _show_disconnect_menu(self, pos: QPointF, wire: dict):
            """Show right-click context menu to disconnect a wire."""
            menu = QMenu(self)
            menu.setStyleSheet(
                "QMenu { background: #1a1a2f; color: #e0e0f0; border: 1px solid #3a3a5f; }"
                "QMenu::item:selected { background: #2a2a4f; }"
                "QMenu::separator { background: #3a3a5f; height: 1px; }"
            )

            src_short = wire["source_id"][:8]
            tgt_short = wire["target_id"][:8]
            pct = wire.get("pct", 0)

            header = menu.addAction(f"Wire: {src_short} → {tgt_short} ({pct}%)")
            header.setEnabled(False)
            menu.addSeparator()

            disconnect_action = menu.addAction("Disconnect Wire")
            disconnect_action.setIcon(
                self.style().standardIcon(
                    self.style().StandardPixmap.SP_DialogCloseButton
                )
            )

            # If bidirectional, offer to disconnect both
            if self._is_bidirectional(wire["source_id"], wire["target_id"]):
                disconnect_both = menu.addAction("Disconnect Both Directions")
            else:
                disconnect_both = None

            menu.addSeparator()
            menu.addAction("Cancel")

            global_pos = self._wire_canvas.mapToGlobal(pos.toPoint())
            result = menu.exec(global_pos)

            if result == disconnect_action:
                self.remove_wire(wire["source_id"], wire["target_id"])
            elif result == disconnect_both and disconnect_both:
                self.remove_wire(wire["source_id"], wire["target_id"])
                self.remove_wire(wire["target_id"], wire["source_id"])

        def update_bots(self, bot_statuses: list[dict]):
            """Update visualizations from bot status data.

            v3.13.4 — in addition to the animated bot node grid,
            maintain the unified row section so Tab 1 mirrors the
            Sim/Paper structure. Same data feeds both views; user
            gets row summary + animated detail side-by-side.
            """
            current_ids = set()

            # Session 26 (2026-04-24): unified row section removed; locusts
            # now live only in the wrap-grid below. Grid position is derived
            # from insertion order so bot layout is stable across updates.
            # Wire overlay geometry depends on bot centers; a stable grid
            # prevents wires from jumping when bots are added/removed.
            for status in bot_statuses:
                bid = status.get("bot_id", "")
                if not bid:
                    continue
                current_ids.add(bid)

                if bid not in self._bot_widgets:
                    self._empty_label.setVisible(False)
                    node = BotNodeWidget()
                    node.set_theme(self._theme_key)
                    self._bot_widgets[bid] = node
                    idx = len(self._bot_widgets) - 1
                    row = idx // self._grid_cols
                    col = idx % self._grid_cols
                    self._grid_layout.addWidget(node, row, col)

                self._bot_widgets[bid].set_bot_data(status)

            # ── Removal pass ──
            for bid in list(self._bot_widgets.keys()):
                if bid not in current_ids:
                    widget = self._bot_widgets.pop(bid)
                    self._grid_layout.removeWidget(widget)
                    widget.deleteLater()
                    # Remove wires involving this bot
                    self._wires = [
                        w
                        for w in self._wires
                        if w["source_id"] != bid and w["target_id"] != bid
                    ]

            # v3.23.61 — mirror to list view.
            try:
                self._refresh_bot_list_rows()
            except Exception as _rl_exc:  # noqa: BLE001 - list mirror best-effort
                logger.debug("list-view row refresh raised: %s", _rl_exc)

            # Re-layout after any removal so grid stays compact (no holes).
            if self._bot_widgets:
                widgets_in_order = list(self._bot_widgets.values())
                # Clear all items from the grid
                while self._grid_layout.count():
                    self._grid_layout.takeAt(0)
                    # don't deleteLater — we own the widgets in _bot_widgets
                for idx, w in enumerate(widgets_in_order):
                    row = idx // self._grid_cols
                    col = idx % self._grid_cols
                    self._grid_layout.addWidget(w, row, col)
                # Re-add the empty label at bottom (hidden) so it survives
                self._grid_layout.addWidget(
                    self._empty_label,
                    (len(widgets_in_order) // self._grid_cols) + 1,
                    0,
                    1,
                    self._grid_cols,
                )

            if not self._bot_widgets:
                self._empty_label.setVisible(True)

            # Keep the wire overlay on top of the bot widgets after any
            # layout change; otherwise newly-added widgets stack above the
            # overlay and eat mouse events + occlude wires.
            if self._wire_canvas.isVisible():
                self._reposition_wire_canvas()
                self._wire_canvas.raise_()

            # v3.23.9 — repopulate Exchange selector + Quick Routing
            # scope every time the swarm changes. Cheap and idempotent.
            try:
                self._rebuild_exchange_selector_items()
                self._refresh_visible_bots()
                self._refresh_quick_routing_scope()
            except Exception:  # noqa: S110
                pass

    # -------------------------------------------------------------------
    # Wire Canvas Overlay — draws glowing wires between bots
    # -------------------------------------------------------------------
    class _WireCanvas(QWidget):
        """Transparent overlay that renders glowing profit wires."""

        def __init__(self, viz_tab: BotVisualizationTab):
            super().__init__(viz_tab)
            self.setAccessibleName("Wire Canvas")
            self._viz = viz_tab
            self.setAttribute(Qt.WA_TranslucentBackground)
            self.setStyleSheet("background: transparent;")

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                bid = self._viz._bot_at_pos(QPointF(event.position()))
                if bid:
                    self._viz._start_wire_drag(bid, QPointF(event.position()))
                    return
            elif event.button() == Qt.RightButton:
                # Right-click on a wire → disconnect menu
                wire = self._viz._wire_at_pos(QPointF(event.position()))
                if wire:
                    self._viz._show_disconnect_menu(QPointF(event.position()), wire)
                    return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event):
            if self._viz._dragging_wire:
                self._viz._update_wire_drag(QPointF(event.position()))
                return
            # Change cursor when hovering over a wire
            wire = self._viz._wire_at_pos(QPointF(event.position()))
            if wire:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.LeftButton and self._viz._dragging_wire:
                self._viz._finish_wire_drag(QPointF(event.position()))
                return
            super().mouseReleaseEvent(event)

        def paintEvent(self, event):
            if not self._viz._wires and not self._viz._dragging_wire:
                return

            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            # v3.23.61 — respect operator's wire-opacity slider.
            _opacity = max(
                0, min(100, int(getattr(self._viz, "_wire_opacity_pct", 100)))
            )
            p.setOpacity(_opacity / 100.0)
            t = THEMES.get(self._viz._theme_key, THEMES["quantum"])

            # --- Draw existing wires ---
            for wire in self._viz._wires:
                src = self._viz._get_bot_center(wire["source_id"])
                tgt = self._viz._get_bot_center(wire["target_id"])
                if not src or not tgt:
                    continue
                phase = wire.get("phase", 0)
                pct = wire.get("pct", 50)
                offset = self._viz._get_wire_offset(wire)
                self._draw_glow_wire(
                    p, src, tgt, t["accent"], t["accent2"], phase, pct, offset
                )

            # --- Draw dragging wire ---
            if self._viz._dragging_wire and self._viz._wire_mouse_pos:
                src = self._viz._get_bot_center(self._viz._wire_start_id)
                if src:
                    hover_id = self._viz._bot_at_pos(self._viz._wire_mouse_pos)
                    # Check if this would be a disconnect (re-drag between connected bots)
                    is_disconnect = False
                    if hover_id and hover_id != self._viz._wire_start_id:
                        is_disconnect = any(
                            w["source_id"] == self._viz._wire_start_id
                            and w["target_id"] == hover_id
                            for w in self._viz._wires
                        )

                    if is_disconnect:
                        color = t["error"]  # Red for disconnect
                    elif hover_id and hover_id != self._viz._wire_start_id:
                        color = t["success"]  # Green for new connection
                    else:
                        color = t["warning"]  # Yellow while dragging

                    dim = QColor(color)
                    dim.setAlpha(120)
                    pen = QPen(dim, 2, Qt.DashLine)
                    p.setPen(pen)
                    p.drawLine(src, self._viz._wire_mouse_pos)

            p.end()

        def _draw_glow_wire(
            self,
            p: QPainter,
            src: QPointF,
            tgt: QPointF,
            color1: QColor,
            color2: QColor,
            phase: float,
            pct: int,
            offset: float = 0,
        ):
            """Draw a glowing animated wire with bezier curve offset."""
            # Compute control point for bezier curve
            mid_x = (src.x() + tgt.x()) / 2
            mid_y = (src.y() + tgt.y()) / 2 + offset

            # Build bezier path
            path = QPainterPath()
            path.moveTo(src)
            path.quadTo(QPointF(mid_x, mid_y), tgt)

            # Outer glow (wide, transparent)
            glow = QColor(color1)
            glow.setAlpha(25)
            p.setPen(QPen(glow, 8))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

            # Mid glow
            glow2 = QColor(color1)
            glow2.setAlpha(50)
            p.setPen(QPen(glow2, 4))
            p.drawPath(path)

            # Core wire
            p.setPen(QPen(color1, 2))
            p.drawPath(path)

            # Traveling pulse along bezier curve
            t_pos = math.sin(phase) * 0.5 + 0.5  # 0..1 oscillation
            pulse_pt = path.pointAtPercent(t_pos)

            pulse_color = QColor(color2)
            pulse_color.setAlpha(200)
            glow_r = QRadialGradient(pulse_pt.x(), pulse_pt.y(), 12)
            glow_r.setColorAt(0, pulse_color)
            glow_r.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(glow_r))
            p.setPen(Qt.NoPen)
            p.drawEllipse(pulse_pt, 8, 8)

            # Direction arrow at 70% along the path
            arrow_pt = path.pointAtPercent(0.7)
            arrow_prev = path.pointAtPercent(0.65)
            dx = arrow_pt.x() - arrow_prev.x()
            dy = arrow_pt.y() - arrow_prev.y()
            length = math.sqrt(dx * dx + dy * dy) or 1
            dx /= length
            dy /= length
            # Arrow head
            arrow_size = 6
            p.setPen(QPen(color1, 2))
            p.setBrush(QBrush(color1))
            arrow = QPolygonF(
                [
                    arrow_pt,
                    QPointF(
                        arrow_pt.x() - arrow_size * dx + arrow_size * 0.5 * dy,
                        arrow_pt.y() - arrow_size * dy - arrow_size * 0.5 * dx,
                    ),
                    QPointF(
                        arrow_pt.x() - arrow_size * dx - arrow_size * 0.5 * dy,
                        arrow_pt.y() - arrow_size * dy + arrow_size * 0.5 * dx,
                    ),
                ]
            )
            p.drawPolygon(arrow)

            # Percentage label at curve midpoint
            label_pt = path.pointAtPercent(0.5)
            label = f"{pct}%"
            font = QFont("Consolas", 8, QFont.Bold)
            p.setFont(font)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(label) + 8
            badge = QRectF(label_pt.x() - tw / 2, label_pt.y() - 9, tw, 18)
            p.setBrush(QBrush(QColor(0, 0, 0, 160)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(badge, 4, 4)
            p.setPen(QPen(color1))
            p.drawText(badge, Qt.AlignCenter, label)
