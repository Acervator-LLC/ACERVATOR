# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""history_qt_table.py -- the History table drawn by Qt widgets.

WHAT THIS IS
============
The Qt half of the History table variant. ``HistoryWebTable`` in
``src/gui/react_history_panel.py`` draws the same view model with React
inside ``QWebEngineView``; this draws it with ``QTableWidget``. The build
picks one, ``src/gui/history_table_variant.py`` hands it to
``HistoryTab``, and the two executables can then be run against each
other on the same data.

WHAT IT MAY NOT DO
==================
It computes nothing, the same prohibition the React panel carries. Every
string, colour and tooltip on screen is a field
``src.exchange.history_read_contract`` already produced and
``build_view_model`` already packed. A table that re-derived a cost, a
grade or a colour would be a third implementation of History, disagreeing
with the other two exactly where a comparison is supposed to be reading.

THE INTERFACE IS THE REACT PANEL'S, EXACTLY
===========================================
``HistoryTab`` holds the table through three calls and no others:
construction, ``set_model``, and ``row_count``. Both classes answer all
three with the same signatures and the same meanings, so the tab needs no
knowledge of which one it holds.

``row_count`` answers through a callback here as well, though this table
knows its count synchronously. The React panel has to ask a browser and
cannot answer inline; keeping the callback shape identical is what lets
the tab stay written once.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from ..trading.gate_vocabulary import (
    BANK_MARKER_COLOR,
    LIGHT_LABEL_COLOR,
    gate_light_row,
)

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    _HAS_QT = True
except ImportError:
    # No Qt means no widget class; the module still imports.
    _HAS_QT = False

logger = logging.getLogger("acervator.gui.history_qt_table")


def column_headers(model: dict) -> list[str]:
    """The header text for each column, in the model's own order."""
    return [str(col.get("header", "")) for col in model.get("columns", [])]


def column_tooltips(model: dict) -> list[str]:
    """The header tooltip for each column, in the model's own order."""
    return [str(col.get("header_tooltip") or "") for col in model.get("columns", [])]


def model_rows(model: dict) -> list:
    """The rows of the page the model carries, or none when it carries no page."""
    page = model.get("page") or {}
    rows = page.get("rows")
    return list(rows) if rows else []


GATES_COLUMN_KEY = "gates"

GATE_LIGHTS_NAME = "Gate lights"
GATE_TEXT_NAME = "Gate text"
GATE_ZONE_NAME = "Gate lights zone"

# Sizes taken from history_panel.css .light-dot, .light-label, .bank-marker.
LIGHT_DOT_PX = 7
LIGHT_LABEL_PX = 7
BANK_MARKER_PX = 8
LIGHT_SPACING_PX = 3
BANK_SPACING_PX = 10
TEXT_SPACING_PX = 8


def row_lights(row: dict) -> list:
    """The row's ``gate_lights`` entries, or empty when the row carries none."""
    lights = row.get("gate_lights") or {}
    entries = lights.get("lights") if isinstance(lights, dict) else None
    return list(entries) if isinstance(entries, list) and entries else []


def light_shape(lights: list) -> list:
    """The bank and label of each light, in the order given."""
    return [
        (str(light.get("bank", "")), str(light.get("label", ""))) for light in lights
    ]


def group_banks(lights: list) -> list:
    """Consecutive runs of lights sharing a ``bank``, in the order given."""
    banks: list = []
    for light in lights:
        name = str(light.get("bank", ""))
        if not banks or banks[-1][0] != name:
            banks.append((name, []))
        banks[-1][1].append(light)
    return banks


if _HAS_QT:

    def paint_dot(dot: "QLabel", light: dict) -> None:
        """Put one light's state and colour on ``dot``."""
        colour = str(light.get("color", ""))
        dot.setProperty("lightState", str(light.get("state", "")))
        dot.setProperty("lightColor", colour)
        dot.setStyleSheet(
            f"background: {colour}; border-radius: {LIGHT_DOT_PX // 2}px;"
        )

    def build_dot(parent: "QWidget", light: dict) -> "QLabel":
        """The dot, whose fill and ``lightColor`` both read the one colour."""
        dot = QLabel(parent)
        dot.setFixedSize(LIGHT_DOT_PX, LIGHT_DOT_PX)
        paint_dot(dot, light)
        return dot

    def build_light(parent: "QWidget", light: dict, dots: list) -> "QWidget":
        """One light: its label above its dot. Appends that dot to ``dots``."""
        holder = QWidget(parent)
        text = str(light.get("label", ""))
        holder.setAccessibleName(f"Gate {light.get('bank', '')} {text}")
        box = QVBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(1)
        box.setAlignment(Qt.AlignHCenter)
        label = QLabel(text, holder)
        label.setStyleSheet(
            f"color: {LIGHT_LABEL_COLOR}; font-size: {LIGHT_LABEL_PX}px;"
        )
        box.addWidget(label)
        dot = build_dot(holder, light)
        dots.append(dot)
        box.addWidget(dot)
        return holder

    def build_marker(parent: "QWidget", bank: str) -> "QLabel":
        """The marker that closes a bank, carrying the bank's own name."""
        marker = QLabel(bank, parent)
        marker.setAccessibleName(f"Gate bank marker {bank}")
        marker.setStyleSheet(
            f"color: {BANK_MARKER_COLOR}; font-size: {BANK_MARKER_PX}px;"
        )
        return marker

    def build_bank(parent: "QWidget", bank: str, items: list, dots: list) -> "QWidget":
        """One bank's lights, closed by its own marker."""
        holder = QWidget(parent)
        holder.setAccessibleName(f"Gate bank {bank}")
        box = QHBoxLayout(holder)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(LIGHT_SPACING_PX)
        box.setAlignment(Qt.AlignBottom)
        for light in items:
            box.addWidget(build_light(holder, light, dots))
        box.addWidget(build_marker(holder, bank))
        return holder

    def build_lights_zone(parent: "QWidget", lights: list) -> tuple:
        """The Gates cell's indicator zone and its dots, in draw order.

        An empty ``lights`` still builds a zone, which ``lights_zone_width``
        sizes exactly as it sizes a full one.
        """
        zone = QWidget(parent)
        zone.setAccessibleName(GATE_ZONE_NAME)
        box = QHBoxLayout(zone)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(BANK_SPACING_PX)
        dots: list = []
        for bank, items in group_banks(lights):
            box.addWidget(build_bank(zone, bank, items, dots))
        box.addStretch(1)
        return zone, dots

    _ZONE_WIDTH = 0

    def lights_zone_width(parent: "QWidget") -> int:
        """Pixels every ``GateLightsCell`` reserves for its indicator zone.

        Measured once off a zone holding ``gate_light_row``'s full nineteen
        lights, built under ``parent`` to carry the table's own font.
        """
        global _ZONE_WIDTH
        if not _ZONE_WIDTH:
            reference, _ = build_lights_zone(parent, gate_light_row(False, False))
            reference.hide()
            _ZONE_WIDTH = reference.sizeHint().width()
            reference.setParent(None)
            reference.deleteLater()
        return _ZONE_WIDTH

    class GateLightsCell(QWidget):
        """The Gates cell: the row's lights on the left, its text on the right.

        ``build_lights_zone`` gives every cell the same fixed-width indicator
        zone, which opens both zones at one x down the whole column.
        """

        def __init__(self, cell: dict, lights: list, parent=None) -> None:
            super().__init__(parent)
            self.setAccessibleName(GATE_LIGHTS_NAME)
            self._lights = [dict(light) for light in lights]
            self._text = str(cell.get("text", ""))
            self._color = str(cell.get("color") or "")
            self._tooltip = str(cell.get("tooltip") or "")
            box = QHBoxLayout(self)
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(TEXT_SPACING_PX)
            self._zone, self._dots = build_lights_zone(self, self._lights)
            self._zone.setFixedWidth(lights_zone_width(self))
            box.addWidget(self._zone)
            self._label = self._text_widget(cell)
            box.addWidget(self._label)
            box.addStretch(1)
            if self._tooltip:
                self.setToolTip(self._tooltip)

        def lights(self) -> list:
            """The light records this cell drew, in draw order."""
            return [dict(light) for light in self._lights]

        def draws(self, cell: dict, lights: list) -> bool:
            """True when ``cell`` and ``lights`` are what this widget already drew."""
            return (
                self._text == str(cell.get("text", ""))
                and self._color == str(cell.get("color") or "")
                and self._tooltip == str(cell.get("tooltip") or "")
                and self._lights == [dict(light) for light in lights]
            )

        def redraw(self, cell: dict, lights: list) -> bool:
            """Take ``cell`` and ``lights`` into the widgets already built.

            Answers False when ``lights`` names a different run of banks and
            labels, which is the one case needing the widgets built again.
            """
            if light_shape(lights) != light_shape(self._lights):
                return False
            self._text = str(cell.get("text", ""))
            self._color = str(cell.get("color") or "")
            self._tooltip = str(cell.get("tooltip") or "")
            self._label.setText(self._text)
            self._label.setStyleSheet(f"color: {self._color};" if self._color else "")
            self.setToolTip(self._tooltip)
            for dot, drawn, wanted in zip(self._dots, self._lights, lights):
                if drawn != wanted:
                    paint_dot(dot, wanted)
            self._lights = [dict(light) for light in lights]
            return True

        def _text_widget(self, cell: dict) -> "QLabel":
            """The blocker text, in the colour the cell carries."""
            label = QLabel(str(cell.get("text", "")), self)
            label.setAccessibleName(GATE_TEXT_NAME)
            colour = cell.get("color")
            if colour:
                label.setStyleSheet(f"color: {colour};")
            return label

    class HistoryQtTable(QWidget):
        """The History table, drawn by QTableWidget.

        Public surface, matching ``HistoryWebTable`` call for call:
          * set_model(model)      -- draw one view model
          * page_ready            -- True once the table exists
          * model()               -- what the last draw carried
          * row_count(callback)   -- the rows drawn, through a callback
        """

        def __init__(self, parent=None, theme: str = "cyberpunk_dark") -> None:
            super().__init__(parent)
            self.setAccessibleName("Qt History Table")
            self._theme = theme
            self._last_model: dict = {}
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)
            self._table = QTableWidget()
            self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
            self._table.setAlternatingRowColors(True)
            self._table.verticalHeader().setVisible(False)
            layout.addWidget(self._table, 1)

        # -- public ---------------------------------------------------
        @property
        def page_ready(self) -> bool:
            """True once the table exists and can be drawn into.

            The React panel has to wait for a document load; this one is
            ready as soon as it is constructed.
            """
            return True

        def model(self) -> dict:
            """The payload of the most recent draw. Empty before the first."""
            return dict(self._last_model)

        def set_model(self, model: dict) -> None:
            """Draw ``model``. Every value comes from the model as given."""
            self._last_model = model
            self._draw_headers(model)
            self._draw_rows(model)

        def row_count(self, callback: Callable[[Any], None]) -> bool:
            """Report how many rows are drawn, through ``callback``.

            Always answers, and returns True, because the table is always
            ready. The React panel returns False when its document is not
            up; the tab treats that as "no count available" and this class
            never produces it.
            """
            callback(self._table.rowCount())
            return True

        # -- internals ------------------------------------------------
        def _draw_headers(self, model: dict) -> None:
            headers = column_headers(model)
            tooltips = column_tooltips(model)
            self._table.setColumnCount(len(headers))
            self._table.setHorizontalHeaderLabels(headers)
            for index, tooltip in enumerate(tooltips):
                item = self._table.horizontalHeaderItem(index)
                if item is not None and tooltip:
                    item.setToolTip(tooltip)
            header = self._table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setStretchLastSection(False)

        def _draw_rows(self, model: dict) -> None:
            rows = model_rows(model)
            self._table.setRowCount(len(rows))
            header = self._table.horizontalHeader()
            # ResizeToContents re-measures every column on each cell write.
            header.setSectionResizeMode(QHeaderView.Interactive)
            regrew = False
            for row_index, row in enumerate(rows):
                lights = row_lights(row)
                for cell_index, cell in enumerate(row.get("cells", [])):
                    gates = cell.get("key") == GATES_COLUMN_KEY
                    # GateLightsCell draws the Gates text; its item stays blank.
                    text = "" if gates else str(cell.get("text", ""))
                    self._draw_cell(row_index, cell_index, cell, text)
                    if not gates:
                        continue
                    if self._draw_gates(row_index, cell_index, cell, lights):
                        regrew = True
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            if regrew:
                self._table.resizeRowsToContents()

        def _draw_cell(
            self, row_index: int, cell_index: int, cell: dict, text: str
        ) -> None:
            """Write one cell, keeping an item that already carries these values."""
            held = self._table.item(row_index, cell_index)
            if held is not None and self._item_draws(held, cell, text):
                return
            self._table.setItem(row_index, cell_index, self._cell_item(cell, text))

        def _item_draws(self, item: "QTableWidgetItem", cell: dict, text: str) -> bool:
            """True when ``item`` already carries ``text`` and the cell's own
            colour and tooltip."""
            if item.text() != text:
                return False
            tooltip = cell.get("tooltip")
            if item.toolTip() != (str(tooltip) if tooltip else ""):
                return False
            colour = cell.get("color")
            if not colour:
                return True
            return item.foreground().color() == QColor(str(colour))

        def _draw_gates(
            self, row_index: int, cell_index: int, cell: dict, lights: list
        ) -> bool:
            """Put a ``GateLightsCell`` on the Gates cell, and say whether it is new.

            Every Gates cell gets one, lights or none, which is what keeps a
            lightless row's zones at the same x as a lit row's.
            """
            held = self._table.cellWidget(row_index, cell_index)
            if isinstance(held, GateLightsCell):
                if held.draws(cell, lights):
                    return False
                if held.redraw(cell, lights):
                    return False
            self._table.setCellWidget(
                row_index, cell_index, GateLightsCell(cell, lights, self._table)
            )
            return True

        # Overtaken: "One table item carrying the cell's own text, colour and tooltip."
        # True: the caller supplies ``text``, blank where GateLightsCell draws it.
        def _cell_item(self, cell: dict, text: str) -> "QTableWidgetItem":
            """One table item carrying the cell's own text, colour and tooltip."""
            item = QTableWidgetItem(text)
            colour = cell.get("color")
            if colour:
                item.setForeground(QColor(str(colour)))
            tooltip = cell.get("tooltip")
            if tooltip:
                item.setToolTip(str(tooltip))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            return item
