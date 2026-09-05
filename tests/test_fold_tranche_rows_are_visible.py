"""The Fold Tranches table paints whole rows, counted off the pixels.

Every row claim is counted from `widget.grab()` through `tests/qt_pixel.py`,
not from `viewport().height()`, which answered 30 and 409 on tables painting 8
and 25 pixels of row. `_ceiling_only` and `_old_chrome_constant` put each fault
back on its own, and `TestARefusedTrancheIsStillRefused` holds a record the
panel draws, counts, and still prices as em dashes.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Frozen clock. The tab reads the wall clock, so the age cell is only
#: expressible as an offset from a fixed instant.
NOW = 1_787_700_000.0

#: The theme `main.py:949` applies when the operator has chosen none.
DEFAULT_THEME = "cyberpunk_dark"

#: Painted row pixels the shipped panel gave the operator, counted off
#: the render under `DEFAULT_THEME` in a 640x720 dialog.
SHIPPED_ROW_PIXELS_AT_ONE_TRANCHE = 8

COL_INDEX = 0
COL_AGE = 1
COL_UNITS = 2
COL_USD = 3
COL_REF = 4
COL_COST = 5
COL_MIN_REBUY = 6
COL_STATUS = 7
COL_SOURCE = 8

DASH = "—"

#: One live CHIP/USD tranche. The two wire-credit members are what make its
#: shape differ from every other fixture in the suite.
LIVE_TRANCHE = {
    "usd": 3.3183661898345487,
    "units": 101.50000000000006,
    "ref": 0.02977,
    "initial_buy_price": 0.02957,
    "operator_initiated": True,
    "created_ts": 1_787_418_883.8538017,
    "wire_credits": [
        {
            "source": "cc18670d",
            "usd": 0.00035347435016010057,
            "ref": "scrum@0.47950000",
            "ts": 1_787_514_090.0207853,
        },
        {
            "source": "a8d95fed",
            "usd": 0.24951068117892278,
            "ref": "scrum@18.22880000",
            "ts": 1_787_669_823.6220682,
        },
    ],
    "wire_credits_rolled": {
        "count": 13,
        "total_usd": 0.020337,
        "by_source": {"695f39e1": 0.00175972, "ae2f02cf": 0.00826936},
        "first_ts": 1_787_446_059.0048451,
        "last_ts": 1_787_508_892.8608267,
    },
}


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Exchange:
    """The one attribute `ScrummingBot.__init__` reads off it."""

    exchange_id = "test"


def _tranche(i: int, *, usd: float = 1.0) -> dict:
    return {
        "usd": usd,
        "units": 2.0,
        "ref": 0.03,
        "initial_buy_price": 0.029,
        "created_ts": NOW - 86400.0 * (i + 1),
    }


class _Panel:
    """Dialog -> QTabWidget -> QScrollArea -> tab -> table, and shown.

    THE NESTING IS THE TEST. A tab built into a bare dialog gets its
    maximum height and paints its row; the same tab inside
    `_wrap_scrollable` inside a QTabWidget gets its `minimumSizeHint`
    and paints eight pixels. Only the second one is what opens.
    """

    def __init__(self, host, tabs, dialog, bot):
        self.host = host
        self.tabs = tabs
        self.dialog = dialog
        self.bot = bot

    @property
    def table(self):
        return self.dialog._fold_tranche_table

    def cell(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        return "" if item is None else item.text()

    def row_pixels(self) -> int:
        """Scanlines of the table render that carry the fold fill."""
        from PySide6.QtGui import QColor

        from qt_pixel import render_widget
        from src.gui.bot_live_settings import FOLD_TRANCHE_BG_HEX

        image = render_widget(self.table)
        want = QColor(FOLD_TRANCHE_BG_HEX).name().lower()
        width = min(image.width(), 400)
        return sum(
            1
            for y in range(image.height())
            if any(
                QColor(image.pixelColor(x, y)).name().lower() == want
                for x in range(width)
            )
        )

    def whole_rows(self) -> int:
        from src.gui.bot_live_settings import TRANCHE_ROW_HEIGHT_PX

        return self.row_pixels() // TRANCHE_ROW_HEIGHT_PX

    def health_row(self, label: str) -> str:
        from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel

        for box in self.dialog._fold_tab_page.findChildren(QGroupBox):
            if not box.title().startswith("Fold-Tranche"):
                continue
            form = box.layout()
            for r in range(form.rowCount()):
                left = form.itemAt(r, QFormLayout.LabelRole)
                right = form.itemAt(r, QFormLayout.FieldRole)
                lw = left.widget() if left is not None else None
                rw = right.widget() if right is not None else None
                if isinstance(lw, QLabel) and lw.text() == label:
                    return rw.text() if isinstance(rw, QLabel) else ""
        return "<<missing>>"


def _build(tranches, monkeypatch, *, theme=DEFAULT_THEME, price=0.0301) -> _Panel:
    app = _qt_or_skip()
    from PySide6.QtWidgets import QDialog, QTabWidget, QVBoxLayout, QWidget

    import time as _clock

    monkeypatch.setattr(_clock, "time", lambda: NOW)

    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.gui.theme_engine import THEMES, generate_qss
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    app.setStyleSheet(generate_qss(THEMES[theme]))

    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="CHIP",
        target_balance=100.0,
    )
    bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
    bot._fold_tranches = list(tranches)
    bot._current_holdings = 8193.0
    monkeypatch.setattr(
        type(bot),
        "get_status",
        lambda self: {"stats": {"current_price": price}},
    )

    dialog = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dialog)
    dialog._bot = bot
    dialog._bm = None
    dialog._changes = {}
    tabs = QTabWidget()
    dialog._tabs = tabs
    tabs.addTab(QWidget(), "Status")
    dialog._install_fold_tranches_tab(tabs)

    # `setMinimumSize(640, 720)` is the dialog's own line, so the panel
    # is measured at the smallest window the operator can be given.
    host = QDialog()
    layout = QVBoxLayout(host)
    layout.addWidget(tabs)
    host.setMinimumSize(640, 720)
    host.resize(640, 720)
    host.show()
    app.processEvents()
    return _Panel(host, tabs, dialog, bot)


def _destroy(panel: _Panel) -> None:
    """`setParent(None)` is a no-op on a widget that never had one.

    Queue the delete, then DELIVER it: `processEvents()` does not
    dispatch `DeferredDelete`, so a `deleteLater` on its own MAKES the
    leak the module-scoped guard in `tests/conftest.py` fails on.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    for widget in (panel.host, panel.tabs, panel.dialog):
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture(autouse=True)
def _restore_stylesheet():
    """Give the process back the stylesheet it had.

    An application stylesheet is global. Leaving a theme behind changes
    what every later GUI file in the session renders.
    """
    app = _qt_or_skip()
    before = app.styleSheet()
    yield
    app.setStyleSheet(before)


@pytest.fixture
def panel(monkeypatch):
    built = _build([dict(LIVE_TRANCHE)], monkeypatch)
    try:
        yield built
    finally:
        _destroy(built)


class TestTheRowReachesTheScreen:

    def test_the_summary_counts_the_tranche(self, panel):
        """FAILURE MEANS: the fixture is not the operator's bot, and
        every row claim below is about some other queue."""
        assert panel.health_row("Open tranches:") == "1"
        assert panel.health_row("Parked USD (in fold queue):") == "$3.3184"
        assert panel.health_row("Units marked (queue vs held):").startswith(
            "101.500000 marked / 8,193.000000 held"
        )

    def test_the_table_holds_exactly_one_built_row(self, panel):
        """FAILURE MEANS: the row was never built, and the defect is
        admission rather than the height this file repairs."""
        assert panel.table.rowCount() == 1
        assert not panel.table.isRowHidden(0)
        assert panel.cell(0, COL_INDEX) == "1"

    def test_a_whole_row_is_painted(self, panel):
        """FAILURE MEANS: Open tranches says 1 and the operator sees a
        header over an empty box — issue #133 unit 1 itself."""
        from src.gui.bot_live_settings import TRANCHE_ROW_HEIGHT_PX

        assert panel.row_pixels() >= TRANCHE_ROW_HEIGHT_PX

    @pytest.mark.parametrize(
        "theme",
        [
            "cyberpunk_dark",
            "neon_light",
            "classic_terminal",
            "minimal_modern",
            "glass_metal",
        ],
    )
    def test_every_shipped_theme_paints_the_row(self, theme, monkeypatch):
        """FAILURE MEANS: the panel is readable only on the theme it was
        measured against, and the chrome is still being assumed."""
        from src.gui.bot_live_settings import TRANCHE_ROW_HEIGHT_PX

        built = _build([dict(LIVE_TRANCHE)], monkeypatch, theme=theme)
        try:
            assert built.row_pixels() >= TRANCHE_ROW_HEIGHT_PX
        finally:
            _destroy(built)

    def test_a_long_queue_paints_the_full_eighteen(self, monkeypatch):
        """FAILURE MEANS: #98's 18-row cap is still arithmetic nobody
        can see — 58 tranches painted 25 pixels before this."""
        from src.gui.bot_live_settings import TRANCHE_TABLE_VISIBLE_ROWS

        built = _build([_tranche(i) for i in range(58)], monkeypatch)
        try:
            assert built.table.rowCount() == 58
            assert built.whole_rows() == TRANCHE_TABLE_VISIBLE_ROWS
        finally:
            _destroy(built)


class TestTheControlsReproduceTheDefect:
    """Both halves of the repair are load-bearing, so both are blinded
    separately. A control that only ever restored the pair could not
    tell which one mattered."""

    def test_a_ceiling_alone_paints_no_whole_row(self, monkeypatch):
        """FAILURE MEANS: `setMaximumHeight` was enough all along and
        the floor added nothing — the check cannot fail, so it is not
        evidence."""
        from PySide6.QtWidgets import QTableWidget

        from src.gui.bot_live_settings import TRANCHE_ROW_HEIGHT_PX

        monkeypatch.setattr(
            QTableWidget,
            "setFixedHeight",
            lambda self, px: QTableWidget.setMaximumHeight(self, px),
        )
        built = _build([dict(LIVE_TRANCHE)], monkeypatch)
        try:
            assert built.row_pixels() < TRANCHE_ROW_HEIGHT_PX
        finally:
            _destroy(built)

    def test_the_old_chrome_constant_paints_no_whole_row(self, monkeypatch):
        """FAILURE MEANS: the 4px chrome constant was never short, and
        measuring the widget bought nothing."""
        import src.gui.live_settings.fold_tokens as tokens
        import src.gui.live_settings.fold_tranches_tab as tab

        monkeypatch.setattr(
            tab,
            "fold_table_chrome_px",
            lambda table: tokens.TRANCHE_TABLE_FRAME_PX,
        )
        built = _build([dict(LIVE_TRANCHE)], monkeypatch)
        try:
            assert built.row_pixels() == SHIPPED_ROW_PIXELS_AT_ONE_TRANCHE
        finally:
            _destroy(built)


class TestTheRowPrintsTheStoredRecord:

    def test_the_four_stored_quantities(self, panel):
        """FAILURE MEANS: the row on screen is not this tranche, and a
        visible row showing another tranche's money is worse than no
        row."""
        assert panel.cell(0, COL_UNITS) == f"{LIVE_TRANCHE['units']:.6f}"
        assert panel.cell(0, COL_USD) == f"${LIVE_TRANCHE['usd']:,.4f}"
        assert panel.cell(0, COL_REF) == f"${LIVE_TRANCHE['ref']:.8f}"
        assert panel.cell(0, COL_COST) == f"${LIVE_TRANCHE['initial_buy_price']:.8f}"

    def test_the_age_is_this_record_s_own_timestamp(self, panel):
        """FAILURE MEANS: the Age cell is reading a different key or a
        different clock than `created_ts`."""
        from src.gui.bot_live_settings import BotLiveSettingsDialog

        expected = BotLiveSettingsDialog._format_age(NOW - LIVE_TRANCHE["created_ts"])
        assert panel.cell(0, COL_AGE) == expected

    def test_the_source_names_the_operator_scrum(self, panel):
        """FAILURE MEANS: `operator_initiated` is not reaching the
        Source column of the row that is now visible."""
        from src.gui.bot_live_settings import FOLD_SOURCE_MANUAL_SCRUM

        assert panel.cell(0, COL_SOURCE) == FOLD_SOURCE_MANUAL_SCRUM

    def test_min_rebuy_sits_below_the_sell_reference(self, panel):
        """FAILURE MEANS: the OTD guide is not a discount off `ref`.
        The relation is asserted and not the number, because copying
        the executor's factor here would be the second implementation
        issue #97 removed."""
        text = panel.cell(0, COL_MIN_REBUY)
        assert text.startswith("≤$")
        assert float(text.lstrip("≤$")) < LIVE_TRANCHE["ref"]

    def test_the_status_cell_answers(self, panel):
        """FAILURE MEANS: the price gate verdict is blank on a row the
        operator can now see and might fire."""
        assert panel.cell(0, COL_STATUS) not in ("", DASH)
        assert "OTD" in panel.cell(0, COL_STATUS)

    def test_the_row_carries_its_own_fire_button(self, panel):
        """FAILURE MEANS: a visible row with no way to act on it, or a
        button that outlived the row it was drawn on."""
        from PySide6.QtWidgets import QPushButton

        button = panel.table.cellWidget(0, 9)
        assert isinstance(button, QPushButton)
        assert button.text() == "Fire"


class TestARefusedTrancheIsStillRefused:
    """A record whose `usd` is `nan` — which `json.load` produces from a
    stored `NaN`. It must be DRAWN, COUNTED and REFUSED, all three."""

    @pytest.fixture
    def mixed(self, monkeypatch):
        bad = _tranche(1, usd=float("nan"))
        built = _build([dict(LIVE_TRANCHE), bad], monkeypatch)
        try:
            yield built
        finally:
            _destroy(built)

    def test_both_rows_are_drawn(self, mixed):
        """FAILURE MEANS: the panel hides what it cannot price, which is
        the $2,000-against-$3,000 shape of 2026-08-10."""
        assert mixed.table.rowCount() == 2
        assert mixed.whole_rows() == 2

    def test_the_refused_cell_prints_no_dollar_figure(self, mixed):
        """FAILURE MEANS: an unreadable amount was priced, and the
        operator is reading a number the record does not hold."""
        assert mixed.cell(1, COL_USD) == DASH

    def test_the_refusal_rides_beside_the_total(self, mixed):
        """FAILURE MEANS: the parked total is quietly short with nothing
        on the panel saying so."""
        assert mixed.health_row("Parked USD (in fold queue):") == (
            f"${LIVE_TRANCHE['usd']:,.4f}  (+1 unreadable)"
        )

    def test_the_refused_row_still_counts_as_open(self, mixed):
        """FAILURE MEANS: a tranche the bot holds left the queue count
        because the panel could not read one of its keys."""
        assert mixed.health_row("Open tranches:") == "2"

    def test_the_refused_row_is_not_sorted_to_the_smallest(self, mixed):
        """FAILURE MEANS: a corrupt record is presented as the smallest
        tranche the operator owns."""
        from src.gui.bot_live_settings import FOLD_SORT_SMALLEST_FIRST

        mixed.dialog._fold_sort_key = FOLD_SORT_SMALLEST_FIRST
        assert mixed.dialog._refresh_fold_tranches_tab() == "refreshed"
        assert mixed.cell(0, COL_USD) == f"${LIVE_TRANCHE['usd']:,.4f}"
        assert mixed.cell(1, COL_USD) == DASH


class TestTheChromeHelper:

    def test_it_reports_what_the_widget_spends(self, panel):
        """FAILURE MEANS: the helper is another constant wearing a
        function's name."""
        from src.gui.bot_live_settings import fold_table_chrome_px

        table = panel.table
        assert fold_table_chrome_px(table) == (
            2 * table.frameWidth() + table.horizontalScrollBar().sizeHint().height()
        )

    def test_the_measured_chrome_beats_the_fallback(self, panel):
        """FAILURE MEANS: 4px was the right budget and this unit is
        repairing nothing."""
        from src.gui.bot_live_settings import (
            TRANCHE_TABLE_FRAME_PX,
            fold_table_chrome_px,
        )

        assert fold_table_chrome_px(panel.table) > TRANCHE_TABLE_FRAME_PX

    def test_polishing_is_what_makes_the_frame_readable(self, monkeypatch):
        """FAILURE MEANS: `ensurePolished` can be dropped. Under the
        shipped theme an unpolished table answers 1 where the same
        table answers 13, and reading it early loses 24px."""
        from PySide6.QtWidgets import QTableWidget

        from src.gui.bot_live_settings import fold_table_chrome_px
        from src.gui.theme_engine import THEMES, generate_qss

        app = _qt_or_skip()
        app.setStyleSheet(generate_qss(THEMES[DEFAULT_THEME]))
        table = QTableWidget()
        try:
            unpolished = table.frameWidth()
            assert fold_table_chrome_px(table) > 2 * unpolished
            assert table.frameWidth() > unpolished
        finally:
            table.close()
            table.deleteLater()
            from PySide6.QtCore import QCoreApplication, QEvent

            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_the_cap_adds_the_chrome_it_is_given(self):
        """FAILURE MEANS: the measured chrome is computed and then
        dropped on the floor."""
        from src.gui.bot_live_settings import (
            TRANCHE_ROW_HEIGHT_PX,
            fold_table_max_height_px,
        )

        assert fold_table_max_height_px(1, 35, 36) == TRANCHE_ROW_HEIGHT_PX + 71
        assert (
            fold_table_max_height_px(1, 35, 36) - fold_table_max_height_px(1, 35, 4)
            == 32
        )

    def test_the_fallback_still_answers_a_caller_with_no_widget(self):
        """FAILURE MEANS: the pure arithmetic stopped being callable
        without a QApplication, which is why it is at module scope."""
        from src.gui.bot_live_settings import (
            TRANCHE_TABLE_FRAME_PX,
            TRANCHE_TABLE_HEADER_PX,
            fold_table_max_height_px,
        )

        assert fold_table_max_height_px(1) == fold_table_max_height_px(
            1, TRANCHE_TABLE_HEADER_PX, TRANCHE_TABLE_FRAME_PX
        )
