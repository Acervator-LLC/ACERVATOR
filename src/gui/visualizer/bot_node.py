"""The per-bot locust card painted in the swarm grid."""

from __future__ import annotations

import math
import secrets

from .particle import Particle
from .privacy import _mask_or
from .themes import THEMES

# Visual jitter only: the swarm canvas draws a start phase and particle
# velocities. This module reads from secrets.SystemRandom, which draws
# from the OS entropy source, so no non-cryptographic generator is
# reachable here. SystemRandom inherits uniform() from random.Random,
# so the distribution of every draw below is unchanged. No call site
# in this module seeds or replays a draw.
_RNG = secrets.SystemRandom()

try:
    from PySide6.QtWidgets import QWidget
    from PySide6.QtCore import Qt, QRectF, QPointF
    from PySide6.QtGui import (
        QPainter,
        QPen,
        QBrush,
        QColor,
        QFont,
        QRadialGradient,
        QLinearGradient,
        QPainterPath,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

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

        def paintEvent(self, _event):
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
            from ...core.fmt import fmt_pnl as _fpnl

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
            from ...core.fmt import fmt_price as _fp

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
