"""``TradeCalculatorDialog`` draws the ``Calculation.rows`` that ``src.trading.trade_calculator`` builds for one History row."""

from __future__ import annotations

from typing import Optional

from src.trading import trade_calculator as tc

try:
    from PySide6.QtGui import QColor, QFont
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QDialog,
        QHeaderView,
        QLabel,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
    )

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class TradeCalculatorDialog(QDialog):
        """The Trade Calculator window: ``tc.READING_TEXT`` until ``set_calculation``, then the fill's title and one table."""

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setAccessibleName(tc.ACCESSIBLE_NAME)
            self.setWindowTitle(tc.WINDOW_TITLE)
            self.setModal(False)
            self.resize(tc.WINDOW_WIDTH_PX, tc.WINDOW_HEIGHT_PX)
            self._calculation: Optional[tc.Calculation] = None
            layout = QVBoxLayout(self)
            self._title = QLabel(tc.READING_TEXT, self)
            self._title.setAccessibleName(tc.TITLE_NAME)
            self._title.setWordWrap(True)
            layout.addWidget(self._title)
            self._table = QTableWidget(0, len(tc.COLUMN_HEADERS), self)
            self._table.setAccessibleName(tc.TABLE_NAME)
            self._table.setHorizontalHeaderLabels(list(tc.COLUMN_HEADERS))
            self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self._table.setWordWrap(True)
            self._table.verticalHeader().setVisible(False)
            header = self._table.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeToContents)
            header.setSectionResizeMode(tc.INPUTS_COLUMN, QHeaderView.Stretch)
            layout.addWidget(self._table, 1)

        def calculation(self) -> Optional[tc.Calculation]:
            """The ``tc.Calculation`` drawn, or None while the trade record is read."""
            return self._calculation

        def cell_texts(self) -> list[list[str]]:
            """Every drawn row's cells, a section row as its one title cell."""
            rows = []
            for row in range(self._table.rowCount()):
                cells = []
                for column in range(self._table.columnCount()):
                    item = self._table.item(row, column)
                    cells.append(item.text() if item is not None else "")
                rows.append(cells)
            return rows

        def title_text(self) -> str:
            """The line above the table."""
            return self._title.text()

        def set_calculation(self, calculation: tc.Calculation) -> None:
            """Draw ``calculation``: its title, then each section's title row and its ``tc.Row`` cells."""
            self._calculation = calculation
            self._title.setText(calculation.title)
            self._table.setRowCount(0)
            section = None
            for row in calculation.rows:
                if row.section != section:
                    section = row.section
                    self._add_section(section)
                self._add_row(row)
            self._table.resizeRowsToContents()

        def _add_section(self, title: str) -> None:
            """One row holding ``title`` alone, spanning every column."""
            at = self._table.rowCount()
            self._table.insertRow(at)
            item = QTableWidgetItem(title)
            font = QFont(item.font())
            font.setBold(True)
            item.setFont(font)
            item.setForeground(QColor(tc.SECTION_COLOR))
            self._table.setItem(at, 0, item)
            self._table.setSpan(at, 0, 1, len(tc.COLUMN_HEADERS))

        def _add_row(self, row: tc.Row) -> None:
            """One ``tc.Row``, its check cell in ``tc.CHECK_COLORS``."""
            at = self._table.rowCount()
            self._table.insertRow(at)
            cells = (
                row.label,
                row.function,
                row.inputs,
                row.computed,
                row.recorded,
                row.check,
            )
            for column, text in enumerate(cells):
                self._table.setItem(at, column, QTableWidgetItem(text))
            colour = tc.CHECK_COLORS.get(row.check)
            if colour:
                check = self._table.item(at, len(cells) - 1)
                if check is not None:
                    check.setForeground(QColor(colour))
