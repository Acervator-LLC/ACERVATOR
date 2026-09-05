"""Transparent overlay that paints the Smart Wires between bot nodes."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

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
