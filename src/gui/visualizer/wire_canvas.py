"""Transparent overlay that paints the Smart Wires between bot nodes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..main_tabs.wire_canvas_surface import (
    ARROW_BACK_PERCENT,
    ARROW_PERCENT,
    BADGE_CORNER_PX,
    BADGE_FILL,
    CORE_WIDTH_PX,
    FONT_FAMILY,
    FONT_SIZE_PT,
    GLOW_ALPHA,
    GLOW_WIDTH_PX,
    MID_GLOW_ALPHA,
    MID_GLOW_WIDTH_PX,
    PULSE_ALPHA,
    PULSE_GRADIENT_RADIUS_PX,
    PULSE_RADIUS_PX,
    arrow_points,
    catenary_curve,
    label_text,
    place_badge,
    point_at,
    pulse_percent,
    slack_for_offset,
)
from .themes import THEMES

if TYPE_CHECKING:
    from ..bot_visualizer import BotVisualizationTab

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
        QPainterPath,
        QPolygonF,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # Wire Canvas Overlay — draws glowing wires between bots
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
            # _wire_opacity_pct is BotVisualizationTab's opacity slider, 0-100.
            _opacity = max(
                0, min(100, int(getattr(self._viz, "_wire_opacity_pct", 100)))
            )
            p.setOpacity(_opacity / 100.0)
            t = THEMES.get(self._viz._theme_key, THEMES["quantum"])

            # Every wire is measured first so place_badge keeps the badges apart.
            p.setFont(QFont(FONT_FAMILY, FONT_SIZE_PT, QFont.Bold))
            metrics = p.fontMetrics()
            hanging: list[tuple] = []
            badges: list[list] = []
            for wire in self._viz._wires:
                src = self._viz._get_bot_center(wire["source_id"])
                tgt = self._viz._get_bot_center(wire["target_id"])
                if not src or not tgt:
                    continue
                pct = wire.get("pct", 50)
                offset = self._viz._get_wire_offset(wire)
                curve = catenary_curve(
                    (src.x(), src.y()), (tgt.x(), tgt.y()), slack_for_offset(offset)
                )
                badge = place_badge(
                    curve["points"],
                    curve["flattest"],
                    metrics.horizontalAdvance(label_text(pct)),
                    badges,
                )
                badges.append(badge)
                hanging.append((wire, curve, badge))

            for wire, curve, badge in hanging:
                self._draw_glow_wire(
                    p,
                    curve["points"],
                    badge,
                    t["accent"],
                    t["accent2"],
                    wire.get("phase", 0),
                    wire.get("pct", 50),
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
            points: list,
            badge: list,
            color1: QColor,
            color2: QColor,
            phase: float,
            pct: int,
        ):
            """Draw one hanging wire, its travelling dot, arrow and badge.

            ``points`` is the catenary_curve sample list and ``badge`` the
            rectangle place_badge found room for.
            """
            path = QPainterPath()
            path.moveTo(QPointF(points[0][0], points[0][1]))
            for one in points[1:]:
                path.lineTo(QPointF(one[0], one[1]))

            glow = QColor(color1)
            glow.setAlpha(GLOW_ALPHA)
            p.setPen(QPen(glow, GLOW_WIDTH_PX))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

            glow2 = QColor(color1)
            glow2.setAlpha(MID_GLOW_ALPHA)
            p.setPen(QPen(glow2, MID_GLOW_WIDTH_PX))
            p.drawPath(path)

            p.setPen(QPen(color1, CORE_WIDTH_PX))
            p.drawPath(path)

            pulse_xy = point_at(points, pulse_percent(phase))
            pulse_pt = QPointF(pulse_xy[0], pulse_xy[1])
            pulse_color = QColor(color2)
            pulse_color.setAlpha(PULSE_ALPHA)
            glow_r = QRadialGradient(
                pulse_pt.x(), pulse_pt.y(), PULSE_GRADIENT_RADIUS_PX
            )
            glow_r.setColorAt(0, pulse_color)
            glow_r.setColorAt(1, QColor(0, 0, 0, 0))
            p.setBrush(QBrush(glow_r))
            p.setPen(Qt.NoPen)
            p.drawEllipse(pulse_pt, PULSE_RADIUS_PX, PULSE_RADIUS_PX)

            corners = arrow_points(
                point_at(points, ARROW_PERCENT),
                point_at(points, ARROW_BACK_PERCENT),
            )
            p.setPen(QPen(color1, 2))
            p.setBrush(QBrush(color1))
            p.drawPolygon(QPolygonF([QPointF(one[0], one[1]) for one in corners]))

            box = QRectF(badge[0], badge[1], badge[2], badge[3])
            p.setBrush(QBrush(QColor(*BADGE_FILL)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(box, BADGE_CORNER_PX, BADGE_CORNER_PX)
            p.setPen(QPen(color1))
            p.drawText(box, Qt.AlignCenter, label_text(pct))
