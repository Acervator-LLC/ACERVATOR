"""BotNodeWidget paints one bot as a locust card in the swarm grid."""

from __future__ import annotations

import math
import secrets

from .growth_stage import (
    BODY_SCALE_RATIO,
    CROWN_SPINE_COUNT,
    DEFAULT_THEME_NAME,
    STAGE_INITIALS,
    STAGE_LABELS,
    TERGITE_COUNT,
    WING_SPREAD_RATIO,
    growth_pct_from_stats,
    growth_text,
    id_text_color,
    stage_colors,
    stage_for,
)
from .particle import Particle
from .privacy import _mask_or
from .themes import THEMES

# _RNG draws the start phase and the Particle spawn values, nothing else.
_RNG = secrets.SystemRandom()

CARD_WIDTH_PX = 88
CARD_HEIGHT_PX = 78
# animate repaints every 4th frame of the tab's 33 ms timer, which is 7.5 Hz.
REPAINT_INTERVAL_S = 0.125
CROWN_SPINE_LENGTH_U = 3.0
CROWN_SPINE_SPREAD_U = 2.4
STAGE_BADGE_FONT_PT = 6
STAGE_BADGE_INSET_PX = 2
STAGE_BADGE_WIDTH_PX = 10
STAGE_BADGE_HEIGHT_PX = 9

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

    class BotNodeWidget(QWidget):
        """Paint one bot as a locust, fed by set_bot_data and animate.

        paintEvent reads stage_for, draws the wings, abdomen, thorax and head
        in that stage's colours, then the symbol, the P/L, the growth_text
        figure and the bot_id as text.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumSize(CARD_WIDTH_PX, CARD_HEIGHT_PX)
            self._theme = THEMES["quantum"]
            self._phase = _RNG.uniform(0, math.pi * 2)
            self._trade_pulses: list[float] = []
            self._particles: list[Particle] = []
            self._bot_data: dict = {}
            # set_bot_data raises this to 1.0 when a nonzero price changes.
            self._antenna_drive: float = 0.0
            self._since_repaint: float = 0.0
            # The app theme the stage body and trim colours are read from.
            self._app_theme_name: str = DEFAULT_THEME_NAME

        def set_theme(self, theme_key: str):
            self._theme = THEMES.get(theme_key, THEMES["quantum"])
            self.update()

        def set_app_theme(self, theme_name: str) -> None:
            """Read the stage colours from theme_name and redraw the card."""
            self._app_theme_name = str(theme_name or DEFAULT_THEME_NAME)
            self.update()

        def set_bot_data(self, data: dict):
            # A rise in total_trades spawns one pulse and five Particles.
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
            old_price = self._bot_data.get("stats", {}).get("current_price", 0)
            new_price = data.get("stats", {}).get("current_price", 0)
            if old_price and new_price and old_price != new_price:
                self._antenna_drive = 1.0
            self._bot_data = data

        def animate(self, dt: float) -> bool:
            """Move the card on by dt seconds; return whether it repainted.

            A card holding a trade pulse or a particle repaints on every call,
            and an otherwise idle card repaints every REPAINT_INTERVAL_S.
            """
            self._phase += dt * 1.5
            self._trade_pulses = [
                p - dt * 0.8 for p in self._trade_pulses if p - dt * 0.8 > 0
            ]
            for p in self._particles:
                p.update(dt)
            self._particles = [p for p in self._particles if p.life > 0]
            # _antenna_drive falls from 1.0 to 0.0 in one second.
            self._antenna_drive = max(0.0, self._antenna_drive - dt * 1.0)
            self._since_repaint += dt
            busy = bool(self._trade_pulses or self._particles)
            if not busy and self._since_repaint < REPAINT_INTERVAL_S:
                return False
            self._since_repaint = 0.0
            self.update()
            return True

        def _locust_body_path(
            self,
            cx: float,
            cy: float,
            scale: float,
            wing_open: float,
            wing_ratio: float = 1.0,
        ) -> dict:
            """Return the locust body as QPainterPath parts keyed head,
            thorax, abdomen, wing_l and wing_r.

            wing_open runs 0.0 folded to 1.0 spread, wing_ratio shortens the
            wing to the stage's share of full spread, and scale sets the unit u.
            """
            u = scale

            parts: dict = {}

            head = QPainterPath()
            head.moveTo(cx - 4 * u, cy - 16 * u)
            head.quadTo(cx - 5 * u, cy - 19 * u, cx, cy - 20 * u)
            head.quadTo(cx + 5 * u, cy - 19 * u, cx + 4 * u, cy - 16 * u)
            head.lineTo(cx + 3.5 * u, cy - 13 * u)
            head.lineTo(cx - 3.5 * u, cy - 13 * u)
            head.closeSubpath()
            parts["head"] = head

            # thorax is a six-point plate centred on cx, cy.
            thorax = QPainterPath()
            thorax.moveTo(cx - 6 * u, cy - 12 * u)
            thorax.lineTo(cx + 6 * u, cy - 12 * u)
            thorax.lineTo(cx + 7 * u, cy - 4 * u)
            thorax.lineTo(cx + 6 * u, cy + 2 * u)
            thorax.lineTo(cx - 6 * u, cy + 2 * u)
            thorax.lineTo(cx - 7 * u, cy - 4 * u)
            thorax.closeSubpath()
            parts["thorax"] = thorax

            abdomen = QPainterPath()
            abdomen.moveTo(cx - 5.5 * u, cy + 2 * u)
            abdomen.lineTo(cx + 5.5 * u, cy + 2 * u)
            abdomen.quadTo(cx + 5 * u, cy + 10 * u, cx + 2.5 * u, cy + 16 * u)
            abdomen.quadTo(cx, cy + 18 * u, cx - 2.5 * u, cy + 16 * u)
            abdomen.quadTo(cx - 5 * u, cy + 10 * u, cx - 5.5 * u, cy + 2 * u)
            abdomen.closeSubpath()
            parts["abdomen"] = abdomen

            wing_spread = (4.5 * u + wing_open * 6 * u) * wing_ratio
            wing_lift = wing_open * 2 * u * wing_ratio
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

            p.fillRect(0, 0, w, h, t["bg"])

            data = self._bot_data
            stats = data.get("stats", {})
            state = data.get("state", "idle")
            symbol = data.get("symbol", "???")
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

            growth_pct = growth_pct_from_stats(stats)
            stage = stage_for(growth_pct)
            body_hex, trim_hex = stage_colors(stage, self._app_theme_name)
            body_color = QColor(body_hex)
            trim_color = QColor(trim_hex)

            scale = min(w, h) / 52.0 * BODY_SCALE_RATIO[stage]

            wing_open = 0.35
            if state == "running":
                wing_open = 0.55 + 0.15 * math.sin(self._phase * 3)
            elif state in ("stopped", "idle"):
                wing_open = 0.15
            if self._trade_pulses:
                wing_open = min(1.0, wing_open + 0.3 * self._trade_pulses[0])

            # Each ring grows and fades as its pulse decays toward zero.
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

            for pt in self._particles:
                pc = QColor(t["particle"])
                pc.setAlpha(int(255 * pt.alpha))
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(pc))
                p.drawEllipse(QPointF(pt.x, pt.y), pt.size, pt.size)

            parts = self._locust_body_path(
                cx, cy, scale, wing_open, WING_SPREAD_RATIO[stage]
            )

            # state_color glow, painted before every body part.
            glow = QRadialGradient(cx, cy, 18 * scale)
            gc = QColor(state_color)
            gc.setAlpha(55)
            glow.setColorAt(0, gc)
            glow.setColorAt(1, QColor(0, 0, 0, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(glow))
            p.drawEllipse(QPointF(cx, cy), 18 * scale, 18 * scale)

            # Wings paint first and sit behind the body.
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

            abdomen_grad = QLinearGradient(cx, cy + 2 * scale, cx, cy + 18 * scale)
            base_ab = QColor(body_color)
            # mag reaches its 1.0 ceiling at a pnl near $10,000.
            mag = min(1.0, math.log10(max(abs(pnl), 0.1) + 1.0) / 4.0)
            base_ab.setAlpha(int(150 + 105 * mag))
            tip = QColor(trim_color)
            tip.setAlpha(int(90 + 90 * mag))
            abdomen_grad.setColorAt(0, base_ab)
            abdomen_grad.setColorAt(1, tip)
            p.setBrush(QBrush(abdomen_grad))
            ab_pen = QPen(trim_color)
            ab_pen.setWidth(1)
            p.setPen(ab_pen)
            p.drawPath(parts["abdomen"])

            # One divider fewer than the stage's tergite count.
            seg_pen = QPen(QColor(0, 0, 0, 120))
            seg_pen.setWidth(1)
            p.setPen(seg_pen)
            for i in range(1, TERGITE_COUNT[stage]):
                y_seg = cy + (2 + i * 4) * scale
                taper = 5.5 - i * 0.8
                p.drawLine(
                    QPointF(cx - taper * scale, y_seg),
                    QPointF(cx + taper * scale, y_seg),
                )

            # Crown spines stand on the thorax and belong to the mature stage.
            if CROWN_SPINE_COUNT[stage]:
                crown_pen = QPen(trim_color)
                crown_pen.setWidth(1)
                p.setPen(crown_pen)
                spines = CROWN_SPINE_COUNT[stage]
                for index in range(spines):
                    share = (index / (spines - 1)) if spines > 1 else 0.5
                    spine_x = cx + (share - 0.5) * 2 * CROWN_SPINE_SPREAD_U * scale
                    p.drawLine(
                        QPointF(spine_x, cy - 12 * scale),
                        QPointF(spine_x, cy - (12 + CROWN_SPINE_LENGTH_U) * scale),
                    )

            thorax_grad = QRadialGradient(cx, cy - 5 * scale, 10 * scale)
            tc1 = QColor(body_color)
            tc1.setAlpha(150)
            tc2 = QColor(state_color)
            tc2.setAlpha(60)
            thorax_grad.setColorAt(0, tc1)
            thorax_grad.setColorAt(1, tc2)
            p.setBrush(QBrush(thorax_grad))
            th_pen = QPen(state_color)
            th_pen.setWidth(2)
            p.setPen(th_pen)
            p.drawPath(parts["thorax"])

            head_fill = QColor(t["bg"]).lighter(120)
            p.setBrush(QBrush(head_fill))
            head_pen = QPen(state_color)
            head_pen.setWidth(2)
            p.setPen(head_pen)
            p.drawPath(parts["head"])

            eye_radius = 1.8 * scale + 0.6 * scale * math.sin(self._phase * 3)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(state_color))
            p.drawEllipse(QPointF(cx, cy - 16.5 * scale), eye_radius, eye_radius)

            # sway sums an ambient _phase term and an _antenna_drive term.
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
                p.setPen(Qt.NoPen)
                tip_col = QColor(t["accent2"])
                tip_col.setAlpha(180)
                p.setBrush(QBrush(tip_col))
                p.drawEllipse(
                    QPointF(cx + sign * (5 + sway) * scale, cy - 28 * scale), 1.2, 1.2
                )
                p.setPen(ant_pen)

            # Three leg pairs; leg_pen widens to 3 for the hind pair only.
            leg_pen = QPen(QColor(state_color).darker(120))
            leg_pen.setWidth(2)
            p.setPen(leg_pen)
            for sign in (-1, 1):
                p1_base = (cx + sign * 5.5 * scale, cy - 8 * scale)
                p1_knee = (cx + sign * 8 * scale, cy - 4 * scale)
                p1_foot = (cx + sign * 9 * scale, cy + 3 * scale)
                p.drawLine(QPointF(*p1_base), QPointF(*p1_knee))
                p.drawLine(QPointF(*p1_knee), QPointF(*p1_foot))

                p2_base = (cx + sign * 6.5 * scale, cy - 3 * scale)
                p2_knee = (cx + sign * 9.5 * scale, cy + 1 * scale)
                p2_foot = (cx + sign * 10 * scale, cy + 8 * scale)
                p.drawLine(QPointF(*p2_base), QPointF(*p2_knee))
                p.drawLine(QPointF(*p2_knee), QPointF(*p2_foot))

                leg_pen.setWidth(3)
                p.setPen(leg_pen)
                p3_base = (cx + sign * 6 * scale, cy + 1 * scale)
                p3_knee = (cx + sign * 11 * scale, cy - 4 * scale)
                p3_foot = (cx + sign * 10 * scale, cy + 10 * scale)
                p.drawLine(QPointF(*p3_base), QPointF(*p3_knee))
                p.drawLine(QPointF(*p3_knee), QPointF(*p3_foot))
                leg_pen.setWidth(2)
                p.setPen(leg_pen)

            # Four corner brackets, each two lines of blen pixels.
            bracket_col = QColor(t["accent2"])
            bracket_col.setAlpha(140)
            bpen = QPen(bracket_col)
            bpen.setWidth(1)
            p.setPen(bpen)
            blen = 6  # pixels, unlike the scale-relative offsets above
            for bx, by, dx, dy in (
                (1, 1, 1, 1),  # top-left
                (w - 2, 1, -1, 1),  # top-right
                (1, h - 2, 1, -1),  # bottom-left
                (w - 2, h - 2, -1, -1),  # bottom-right
            ):
                p.drawLine(QPointF(bx, by), QPointF(bx + dx * blen, by))
                p.drawLine(QPointF(bx, by), QPointF(bx, by + dy * blen))

            # Two traces across the thorax, at cy - 6 * scale and cy - 8 * scale.
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
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(circ_col))
            for dx_u in (-4, 4):
                p.drawEllipse(QPointF(cx + dx_u * scale, cy - 7 * scale), 1.2, 1.2)

            # The iris ring sits outside the eye dot.
            iris_col = QColor(t["accent2"])
            iris_col.setAlpha(200)
            ipen = QPen(iris_col)
            ipen.setWidth(1)
            p.setPen(ipen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(
                QPointF(cx, cy - 16.5 * scale), eye_radius * 1.5, eye_radius * 1.5
            )

            from ...core.fmt import fmt_pnl as _fpnl

            # One field id masks the symbol, the bot_id and the tooltip.
            font = QFont("Consolas", 7, QFont.Bold)
            p.setFont(font)
            p.setPen(t["text"])
            p.drawText(
                QRectF(0, 2, w, 11),
                Qt.AlignCenter,
                _mask_or(symbol, "bot_swarm.identifiers"),
            )

            font.setPointSize(7)
            p.setFont(font)
            p.setPen(pnl_color)
            p.drawText(QRectF(0, h - 22, w, 11), Qt.AlignCenter, _fpnl(pnl))

            # The growth figure that placed this card in its stage.
            font.setPointSize(STAGE_BADGE_FONT_PT)
            p.setFont(font)
            p.setPen(trim_color)
            p.drawText(
                QRectF(
                    w - STAGE_BADGE_INSET_PX - STAGE_BADGE_WIDTH_PX,
                    STAGE_BADGE_INSET_PX,
                    STAGE_BADGE_WIDTH_PX,
                    STAGE_BADGE_HEIGHT_PX,
                ),
                Qt.AlignCenter,
                STAGE_INITIALS[stage],
            )
            p.drawText(
                QRectF(0, h - 31, w, 9),
                Qt.AlignCenter,
                growth_text(growth_pct),
            )

            font.setPointSize(5)
            font.setBold(False)
            p.setFont(font)
            p.setPen(QColor(id_text_color(self._app_theme_name)))
            bot_id_short = data.get("bot_id", "")[:8]
            p.drawText(
                QRectF(0, h - 10, w, 9),
                Qt.AlignCenter,
                _mask_or(bot_id_short, "bot_swarm.identifiers"),
            )

            # setToolTip runs on every paint, from the current _bot_data.
            from ...core.fmt import fmt_price as _fp

            vol_str = (
                f"${volume/1e6:.1f}M"
                if volume >= 1e6
                else f"${volume/1e3:.1f}K" if volume >= 1e3 else f"${volume:.0f}"
            )
            self.setToolTip(
                f"{_mask_or(symbol, 'bot_swarm.identifiers')}\n"
                f"State: {state.upper()}\n"
                f"Mode: {mode.upper()}\n"
                f"Trades: {trades}\n"
                f"Price: {_fp(price) if price > 0 else '—'}\n"
                f"Volume: {vol_str}\n"
                f"P/L: {_fpnl(pnl)}\n"
                f"Stage: {STAGE_LABELS[stage]}\n"
                f"Realised growth: {growth_text(growth_pct)}\n"
                f"Bot: {_mask_or(str(data.get('bot_id', ''))[:12], 'bot_swarm.identifiers', mask='********')}"
            )

            p.end()
