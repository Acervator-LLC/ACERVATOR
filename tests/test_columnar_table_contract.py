"""Column contract for the three tables built on `ColumnarTableWidget`.

Each table is compared against a reference `QTableWidget` configured
from literal column labels and literal widths, structurally and as a
rendered image. A failure means the base class, a preset or a token
changed what the operator sees in a bot table.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6.QtWidgets")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from tests.qt_pixel import render_widget  # noqa: E402

SIZE = (900, 220)

SCRUMMING_HEADERS = (
    "● Bot ID",
    "● Symbol",
    "● Mode",
    "● Trades",
    "● Target",
    "● Target BTC",
    "● Target ETH",
    "● Ammo",
    "● Fire",
    "",
)
SCRUMMING_FIXED = ((8, 70), (9, 60))

EXTRACTOR_HEADERS = (
    "Bot ID",
    "Symbol",
    "Mode",
    "Trades",
    "Pool",
    "Liquid",
    "Fire",
    "",
)
EXTRACTOR_FIXED = ((6, 70), (7, 60))

STOCK_HEADERS = (
    "Bot ID",
    "Symbol",
    "Mode",
    "State",
    "Position",
    "Entry $",
    "Current $",
    "P/L",
    "Trades",
    "Signals",
)
STOCK_FIXED = ()


class _AllRevealed:
    """Privacy registry stand-in. Reveals every field and refuses to
    persist, so no test can rewrite the operator's settings file."""

    def is_masked(self, _field_id):
        return False

    def set_masked(self, _field_id, _value):
        raise AssertionError("the contract test must never persist a mask")


@pytest.fixture(autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def revealed(monkeypatch):
    from src.gui import main_window as mw

    monkeypatch.setattr(mw, "get_privacy_mask_registry", lambda: _AllRevealed())


def _reference(headers, fixed, accessible_name=""):
    """A table built only from literals, for the widget under test to match."""
    table = QTableWidget()
    if accessible_name:
        table.setAccessibleName(accessible_name)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    for col, width in fixed:
        header.setSectionResizeMode(col, QHeaderView.Fixed)
        table.setColumnWidth(col, width)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    return table


def _populate(table):
    table.setRowCount(3)
    for row in range(3):
        for col in range(table.columnCount()):
            table.setItem(row, col, QTableWidgetItem(f"r{row}c{col}"))
    table.setCurrentCell(1, 0)
    table.selectRow(1)


def _assert_matches(table, headers, fixed, accessible_name=""):
    reference = _reference(headers, fixed, accessible_name)
    _populate(table)
    _populate(reference)
    painted = render_widget(table, size=SIZE)
    expected = render_widget(reference, size=SIZE)

    assert table.columnCount() == len(headers)
    assert [
        table.horizontalHeaderItem(c).text() for c in range(table.columnCount())
    ] == list(headers)
    assert [table.columnWidth(c) for c in range(table.columnCount())] == [
        reference.columnWidth(c) for c in range(reference.columnCount())
    ]
    header = table.horizontalHeader()
    ref_header = reference.horizontalHeader()
    assert [header.sectionResizeMode(c) for c in range(table.columnCount())] == [
        ref_header.sectionResizeMode(c) for c in range(reference.columnCount())
    ]
    for col, width in fixed:
        assert header.sectionResizeMode(col) == QHeaderView.Fixed
        assert table.columnWidth(col) == width
    assert table.isSortingEnabled() is False
    assert table.selectionMode() == QTableWidget.ExtendedSelection
    assert table.selectionBehavior() == QTableWidget.SelectRows
    assert table.editTriggers() == QTableWidget.NoEditTriggers
    assert table.alternatingRowColors() is True
    assert table.verticalHeader().isVisible() is False
    assert table.accessibleName() == accessible_name
    assert table.showGrid() == reference.showGrid()

    assert painted.size() == expected.size()
    differing = sum(
        1
        for y in range(expected.height())
        for x in range(expected.width())
        if painted.pixel(x, y) != expected.pixel(x, y)
    )
    assert differing == 0, (
        f"{type(table).__name__} paints {differing} pixels the literal "
        "column contract does not."
    )


@pytest.mark.usefixtures("revealed")
def test_bot_status_table_matches_the_literal_contract():
    from src.gui.main_window import BotStatusTable

    _assert_matches(BotStatusTable(), SCRUMMING_HEADERS, SCRUMMING_FIXED)


def test_extractor_bot_table_matches_the_literal_contract():
    from src.gui.main_window import ExtractorBotTable

    _assert_matches(ExtractorBotTable(), EXTRACTOR_HEADERS, EXTRACTOR_FIXED)


def test_stock_bot_table_matches_the_literal_contract():
    from src.gui.stock_main_window import StockBotTable

    _assert_matches(StockBotTable(), STOCK_HEADERS, STOCK_FIXED, "Stock Bot Table")


def test_extractor_header_tooltips_survive_the_base():
    from src.gui.main_window import ExtractorBotTable

    table = ExtractorBotTable()
    assert (
        table.horizontalHeaderItem(4).toolTip()
        == "Pool — operator-set chunk size in USD (the budget this "
        "Extractor owns and rotates through positions). Live-edit in the "
        "bot's Settings tab → Extractor → Pool size (USD)."
    )
    assert table.horizontalHeaderItem(7).toolTip() == (
        "Click for full bot detail and status explanation"
    )


@pytest.mark.usefixtures("revealed")
def test_bot_status_header_tooltips_carry_the_privacy_suffix():
    from src.gui.main_window import BotStatusTable

    table = BotStatusTable()
    assert table.horizontalHeaderItem(0).toolTip() == (
        "Unique identifier for this bot instance\n\n"
        "Privacy: REVEALED (field bot_table.bot_id).\n"
        "Click this header to toggle."
    )
    assert table.horizontalHeaderItem(9).toolTip() == ""


def test_stock_table_still_renders_rows_through_update_bots():
    from src.gui.stock_main_window import StockBotTable

    table = StockBotTable()
    table.update_bots(
        [
            {
                "bot_id": "abcdefgh1234",
                "symbol": "AAPL",
                "mode": "swing",
                "state": "running",
                "stats": {
                    "current_position": 4,
                    "avg_entry_price": 10.5,
                    "current_price": 12.25,
                    "total_pnl": 7.0,
                    "total_trades": 3,
                    "signals_received": 9,
                },
            }
        ]
    )
    assert table.rowCount() == 1
    assert table.columnCount() == 10
    assert table.item(0, 0).text() == "abcdefgh"
    assert table.item(0, 7).text() == "$+7.00"


def test_extractor_table_still_renders_rows_through_update_bots():
    from src.gui.main_window import ExtractorBotTable

    table = ExtractorBotTable()
    table.update_bots(
        [
            {
                "bot_id": "extractor-1",
                "base_currency": "BTC",
                "chunk_size_usd": 100.0,
                "chunk_size_base": 2.0,
                "chunk_free_base": 1.0,
                "n_positions_open": 1,
                "n_positions_drawdown": 0,
                "pool_color": "yellow",
                "stats": {"total_trades": 6},
            }
        ]
    )
    assert table.rowCount() == 1
    assert table.columnCount() == 8
    assert table.item(0, 4).text() == "$100.00"
    assert table.item(0, 5).text() == "$50.00"
