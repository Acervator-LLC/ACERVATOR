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

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QHeaderView,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    _HAS_QT = True
except ImportError:
    # Same form as react_history_panel.py: no Qt means no widget class,
    # the module still imports, and asking for the widget fails by name
    # at the import site.
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


if _HAS_QT:

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
            for row_index, row in enumerate(rows):
                for cell_index, cell in enumerate(row.get("cells", [])):
                    self._table.setItem(row_index, cell_index, self._cell_item(cell))

        def _cell_item(self, cell: dict) -> "QTableWidgetItem":
            """One table item carrying the cell's own text, colour and tooltip."""
            item = QTableWidgetItem(str(cell.get("text", "")))
            colour = cell.get("color")
            if colour:
                item.setForeground(QColor(str(colour)))
            tooltip = cell.get("tooltip")
            if tooltip:
                item.setToolTip(str(tooltip))
            item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            return item
