"""The Details window opens wide enough for a whole tranche row.

The Fold Tranches table declares ``fold_table_natural_width_px`` as its
minimum width, so ``QWidgetItem.sizeHint`` carries the columns up to the tab.
``QAbstractScrollArea::sizeHint`` does not sum columns, which is why the
wrapper hint alone is too narrow. ``skip_unless_real_fonts`` guards the checks
that need a measured string.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

TESTS_DIR = str(Path(__file__).resolve().parent)
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)

from tests.fixtures.host_fonts import has_real_fonts, skip_unless_real_fonts

#: The dialog's minimum size, which Qt enforces on every open.
SHIPPED_MIN_W = 640
SHIPPED_MIN_H = 720

#: Read off `Screen.WorkingArea`: a 1920x1200 panel at 125% reports
#: 1536x960 logical pixels.
OPERATOR_SCREEN = (1536, 960)

#: A display no tab can exhaust, used for the upper-bound check.
UNBOUNDED_SCREEN = (4000, 4000)

#: Row fill painted by `_paint_fold_tranche_row`. Sampled at the
#: Arbiter cell, so the check reads a painted row.
FOLD_ROW_FILL = "#123a63"

#: The CHIP/USD tranche in the operator's `bot_state.json`, field for
#: field.
CHIP_LIVE = {
    "usd": 8.507375859675001,
    "units": 236.50000000000003,
    "ref": 0.03376,
    "initial_buy_price": 0.031107932666502684,
    "price": 0.03467,
}

#: 58 tranches: past the 18-row table cap, so the table is at its
#: widest.
FIXTURE_TRANCHES = 58


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Exchange:
    """The one attribute `ScrummingBot.__init__` reads off it."""

    exchange_id = "test"


class _Panel:
    """The dialog, and where its tranche row ends."""

    def __init__(self, dialog, app):
        self.dialog = dialog
        self.app = app

    @property
    def fold_index(self) -> int:
        tabs = self.dialog._tabs
        for index in range(tabs.count()):
            if tabs.tabText(index) == "Fold Tranches":
                return index
        raise AssertionError("the dialog built no Fold Tranches tab")

    def show_fold_tab(self):
        """Make the Fold tab current; return `(page, content, table)`.

        QTabWidget lays out only the current page.
        """
        from PySide6.QtWidgets import QScrollArea

        tabs = self.dialog._tabs
        tabs.setCurrentIndex(self.fold_index)
        self.app.processEvents()
        page = tabs.widget(self.fold_index)
        page.ensurePolished()
        content = page.widget() if isinstance(page, QScrollArea) else page
        content.ensurePolished()
        table = self.dialog._fold_tranche_table
        assert table is not None, "the fold queue built no table"
        table.ensurePolished()
        self.app.processEvents()
        return page, content, table

    def arbiter_sample_point(self):
        """A point inside row 0's last cell, in the tab page's render.

        A quarter into the cell, clear of the centred glyph. The
        returned point is in IMAGE coordinates: `grab()` renders at the
        screen's devicePixelRatio - 1.25 on the operator's display -
        while widget geometry is in logical pixels.
        """
        from PySide6.QtCore import QPoint

        page, _content, table = self.show_fold_tab()
        last = table.columnCount() - 1
        rect = table.visualRect(table.model().index(0, last))
        inside = QPoint(rect.left() + rect.width() // 4, rect.center().y())
        point = table.viewport().mapTo(page, inside)
        ratio = page.devicePixelRatio()
        return page, QPoint(int(point.x() * ratio), int(point.y() * ratio))

    def row_cut_px(self) -> int:
        """Pixels of the row that fall outside the tab viewport."""
        page, _content, table = self.show_fold_tab()
        last = table.columnCount() - 1
        rect = table.visualRect(table.model().index(0, last))
        right = table.viewport().mapTo(page.viewport(), rect.topRight())
        return max(0, right.x() - page.viewport().width())

    def destroy(self) -> None:
        """Close, delete, and deliver the DeferredDelete event."""
        from PySide6.QtCore import QCoreApplication, QEvent

        self.dialog.close()
        self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _build(app, screen=UNBOUNDED_SCREEN, tranches=FIXTURE_TRANCHES, data=None):
    """Open the dialog the way `main_window._on_bot_clicked` opens it.

    `WA_DontShowOnScreen` lays the dialog out and maps no window.
    """
    from PySide6.QtCore import Qt
    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    values = dict(data or CHIP_LIVE)
    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="CHIP",
        target_balance=100.0,
    )
    bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
    bot._fold_tranches = [
        {
            "usd": values["usd"],
            "units": values["units"],
            "ref": values["ref"],
            "initial_buy_price": values["initial_buy_price"],
            "created_ts": 1_787_418_883.0 - 900.0 * i,
        }
        for i in range(tranches)
    ]
    bot._current_holdings = 8193.0
    bot.stats.current_price = values["price"]
    dialog = BotLiveSettingsDialog(bot, None, None)
    if screen is not None:
        dialog.open_at_content_size(available=screen)
    dialog.setAttribute(Qt.WA_DontShowOnScreen, True)
    dialog.show()
    app.processEvents()
    return _Panel(dialog, app)


@pytest.fixture(autouse=True)
def themed():
    """Apply `cyberpunk_dark`, the theme `main.py` defaults to.

    The application stylesheet is global and is restored on teardown.
    """
    app = _qt_or_skip()
    from src.gui.theme_engine import THEMES, generate_qss

    before = app.styleSheet()
    app.setStyleSheet(generate_qss(THEMES["cyberpunk_dark"]))
    yield app
    app.setStyleSheet(before)


@pytest.fixture(autouse=True)
def no_leaked_dialog():
    """Fail the test that leaves a Bot Settings dialog alive."""
    yield
    from PySide6.QtCore import QCoreApplication, QEvent
    from PySide6.QtWidgets import QApplication

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    leaked = [
        w
        for w in QApplication.topLevelWidgets()
        if type(w).__name__ == "BotLiveSettingsDialog"
    ]
    assert not leaked, f"{len(leaked)} dialog(s) left alive"


class TestTheRowDemandReadsTheColumns:

    def test_the_table_hint_does_not_answer_for_a_row(self, themed):
        """FAILURE MEANS: QTableWidget now sums its columns in
        `sizeHint`, and the demand helper is redundant."""
        panel = _build(themed)
        try:
            _page, _content, table = panel.show_fold_tab()
            columns = table.horizontalHeader().length()
            assert columns > 0
            assert table.sizeHint().width() < columns, (
                table.sizeHint().width(),
                columns,
            )
        finally:
            panel.destroy()

    def test_the_demand_covers_every_column(self, themed):
        """FAILURE MEANS: the demand is narrower than the columns, so
        the last column is cut at the width reported as sufficient."""
        from src.gui.bot_live_settings import fold_table_natural_width_px

        panel = _build(themed)
        try:
            _page, _content, table = panel.show_fold_tab()
            demand = fold_table_natural_width_px(table)
            assert demand > table.horizontalHeader().length()
            assert demand > table.sizeHint().width()
        finally:
            panel.destroy()

    def test_the_table_is_given_the_demand(self, themed):
        """FAILURE MEANS: the demand is computed and never applied, so
        nothing downstream can see it."""
        from src.gui.bot_live_settings import fold_table_natural_width_px

        panel = _build(themed)
        try:
            _page, _content, table = panel.show_fold_tab()
            assert table.minimumWidth() == fold_table_natural_width_px(table)
        finally:
            panel.destroy()

    def test_the_tab_hint_carries_the_demand(self, themed):
        """FAILURE MEANS: the minimum stops at the table and the tab
        still hints narrower than a row, so `open_at_content_size`
        never sees it."""
        panel = _build(themed)
        try:
            _page, content, table = panel.show_fold_tab()
            assert content.minimumSizeHint().width() >= table.minimumWidth()
            assert content.sizeHint().width() >= table.minimumWidth()
        finally:
            panel.destroy()

    def test_the_columns_all_fit_the_table_viewport(self, themed):
        """FAILURE MEANS: the row is cut inside the table itself,
        whatever width the tab around it was given."""
        panel = _build(themed, screen=OPERATOR_SCREEN)
        try:
            _page, _content, table = panel.show_fold_tab()
            assert table.viewport().width() >= table.horizontalHeader().length()
        finally:
            panel.destroy()

    def test_a_wider_row_demands_more(self, themed):
        """FAILURE MEANS: the demand ignores the data and cannot track
        a column that grows.

        Positive control: 1234567.8912 USD parked against 8.5074.
        """
        from src.gui.bot_live_settings import fold_table_natural_width_px

        wide = dict(CHIP_LIVE)
        wide["usd"] = 1_234_567.8912
        wide["units"] = 123_456_789.5
        narrow = _build(themed)
        try:
            _page, _content, table = narrow.show_fold_tab()
            small = fold_table_natural_width_px(table)
        finally:
            narrow.destroy()
        broad = _build(themed, data=wide)
        try:
            _page, _content, table = broad.show_fold_tab()
            large = fold_table_natural_width_px(table)
        finally:
            broad.destroy()
        assert large > small, (small, large)

    def test_an_empty_queue_demands_nothing(self, themed):
        """FAILURE MEANS: an absent table widens the dialog, or raises
        out of the sizing pass so Bot Settings does not open."""
        panel = _build(themed, tranches=0)
        try:
            assert panel.dialog._fold_tranche_table is None
            assert panel.dialog.width() >= SHIPPED_MIN_W
        finally:
            panel.destroy()


def _unclamped_width(app, **kw) -> int:
    """Width the dialog wants with no display constraining it."""
    panel = _build(app, screen=UNBOUNDED_SCREEN, **kw)
    try:
        return panel.dialog.width()
    finally:
        panel.destroy()


def _assert_clamped_or_whole(app, screen, **kw) -> None:
    """Either the display clamped the dialog, or the row is whole.

    Both halves are asserted. A clamped dialog must sit exactly on the
    display ceiling; an unclamped one must show every column.
    """
    wanted = _unclamped_width(app, **kw)
    panel = _build(app, screen=screen, **kw)
    try:
        opened = panel.dialog.width()
        cut = panel.row_cut_px()
        if opened < wanted:
            assert opened == max(SHIPPED_MIN_W, screen[0] - 32), (
                opened,
                wanted,
                screen,
            )
        else:
            assert cut == 0, (
                f"{cut}px of the row is off the viewport; the dialog "
                f"opened {opened} wide on a {screen[0]}x{screen[1]} display"
            )
    finally:
        panel.destroy()


class TestTheRowIsWhole:

    @skip_unless_real_fonts
    def test_the_row_is_whole_at_the_operators_display(self, themed):
        """FAILURE MEANS: the row's last column is off the tab viewport
        at the opening width, and the Fire button is unreachable.

        Red before the fix at 1536x960 with real fonts: 138px cut.
        """
        panel = _build(themed, screen=OPERATOR_SCREEN)
        try:
            cut = panel.row_cut_px()
            assert cut == 0, (
                f"{cut}px of the row is off the viewport at a "
                f"{OPERATOR_SCREEN[0]}x{OPERATOR_SCREEN[1]} display; the "
                f"dialog opened {panel.dialog.width()} wide"
            )
        finally:
            panel.destroy()

    def test_the_row_is_whole_wherever_the_display_allows(self, themed):
        """FAILURE MEANS: the dialog opened at the width it asked for
        and the row is still cut, so the width it asks for is wrong."""
        _assert_clamped_or_whole(themed, OPERATOR_SCREEN)

    def test_the_last_cell_is_painted_inside_the_render(self, themed):
        """FAILURE MEANS: the Arbiter cell is outside the render, or
        inside it carrying the tab background instead of the row fill.

        Sampled off `grab()`, not off a size hint.
        """
        from qt_pixel import pixel_at, render_widget

        panel = _build(themed, screen=UNBOUNDED_SCREEN)
        try:
            page, point = panel.arbiter_sample_point()
            image = render_widget(page)
            assert point.x() < image.width(), (
                f"the Arbiter cell is at x={point.x()} in a "
                f"{image.width()}px render: the column is off the tab"
            )
            assert pixel_at(image, point) == FOLD_ROW_FILL
        finally:
            panel.destroy()

    def test_a_wider_row_is_whole_too(self, themed):
        """FAILURE MEANS: the width was fitted to one queue's numbers
        and a wider-columned bot opens cut off."""
        wide = dict(CHIP_LIVE)
        wide["usd"] = 1_234_567.8912
        wide["units"] = 123_456_789.5
        wide["ref"] = 78752.96123456
        wide["initial_buy_price"] = 71234.56789012
        wide["price"] = 78752.96
        _assert_clamped_or_whole(themed, OPERATOR_SCREEN, data=wide)

    def test_one_tranche_is_whole_too(self, themed):
        """FAILURE MEANS: the demand needs a long queue to be right; a
        one-tranche bot opens cut off."""
        _assert_clamped_or_whole(themed, OPERATOR_SCREEN, tranches=1)


class TestTheScreenIsNotTheTarget:

    def test_it_does_not_fill_the_operators_display(self, themed):
        """FAILURE MEANS: the dialog was widened to the display, which
        passes every containment check in section B and is unusable."""
        panel = _build(themed, screen=OPERATOR_SCREEN)
        try:
            assert panel.dialog.width() < OPERATOR_SCREEN[0]
            assert panel.dialog.width() <= OPERATOR_SCREEN[0] - 32
        finally:
            panel.destroy()

    def test_it_is_no_wider_than_what_it_holds(self, themed):
        """FAILURE MEANS: the opening width is tied to neither demand
        it is built from.

        Upper bound: the tab's own demand plus 120px of layout chrome.
        Chrome measures 28px with a font database, 70px without.
        """
        from src.gui.bot_live_settings import tab_content_demand_px

        panel = _build(themed)
        try:
            panel.show_fold_tab()
            tab_w, _h, _pw, _ph = tab_content_demand_px(panel.dialog._tabs)
            assert panel.dialog.width() <= tab_w + 120, (
                panel.dialog.width(),
                tab_w,
            )
        finally:
            panel.destroy()

    def test_a_bigger_display_does_not_make_a_bigger_dialog(self, themed):
        """FAILURE MEANS: the size tracks the display, not the
        content."""
        small = _build(themed, screen=(4000, 4000))
        big = _build(themed, screen=(9000, 9000))
        try:
            assert small.dialog.size() == big.dialog.size()
        finally:
            small.destroy()
            big.destroy()


class TestTheDisplayStillWins:

    @pytest.mark.parametrize(
        "screen",
        [(2560, 1400), (1920, 1040), (1536, 960), (1366, 768), (1024, 768)],
    )
    def test_it_never_opens_wider_than_the_display(self, themed, screen):
        """FAILURE MEANS: the row demand pushed the dialog past the
        display edge, where its own corner cannot be grabbed."""
        panel = _build(themed, screen=screen)
        try:
            assert panel.dialog.width() <= screen[0]
            assert panel.dialog.height() <= max(screen[1], SHIPPED_MIN_H)
        finally:
            panel.destroy()

    def test_a_display_smaller_than_the_minimum_gets_the_minimum(self, themed):
        """A display under the floor opens at ``SHIPPED_MIN_W`` by
        ``SHIPPED_MIN_H``."""
        panel = _build(themed, screen=(640, 480))
        try:
            assert panel.dialog.width() == SHIPPED_MIN_W
            assert panel.dialog.height() == SHIPPED_MIN_H
        finally:
            panel.destroy()

    def test_the_dialog_can_still_be_shrunk(self, themed):
        """FAILURE MEANS: the row demand was applied as a minimum, and
        the window cannot be shrunk."""
        panel = _build(themed, screen=OPERATOR_SCREEN)
        try:
            assert panel.dialog.minimumWidth() == SHIPPED_MIN_W
            assert panel.dialog.minimumHeight() == SHIPPED_MIN_H
            panel.dialog.resize(SHIPPED_MIN_W, SHIPPED_MIN_H)
            themed.processEvents()
            assert panel.dialog.width() == SHIPPED_MIN_W
        finally:
            panel.destroy()


class TestTheWidthArithmetic:

    @pytest.mark.parametrize(
        "needed,available,expected",
        [
            # a row demand inside the display: the row wins
            ((1004, 880), (1536, 960), (1004, 880)),
            # a row demand past the display: the display wins
            ((1700, 880), (1536, 960), (1504, 880)),
            # exactly at the ceiling, which is the display less the
            # 32x72 window-frame allowance
            ((1504, 888), (1536, 960), (1504, 888)),
            # one pixel over it, on both axes
            ((1505, 889), (1536, 960), (1504, 888)),
            # below the dialog's own floor: the floor wins
            ((100, 100), (4000, 4000), (640, 720)),
            # a zero display, which is what a headless host reports
            ((5000, 5000), (0, 0), (640, 720)),
        ],
    )
    def test_the_clamp_still_bounds_the_row(self, needed, available, expected):
        """FAILURE MEANS: a row demand escapes the screen clamp."""
        from src.gui.bot_live_settings import dialog_open_size_px

        assert (
            dialog_open_size_px(
                needed[0],
                needed[1],
                available[0],
                available[1],
                SHIPPED_MIN_W,
                SHIPPED_MIN_H,
            )
            == expected
        )


class TestWhatStillDoesNotFit:

    def test_a_display_too_narrow_for_a_row_still_clamps(self, themed):
        """FAILURE MEANS: the recorded residual is stale.

        1024x768 leaves 992 usable pixels. A whole row needs 1034 to
        1124, so it stays cut - 5px, 37px and 95px across the three
        shapes - and the dialog stays on the display. Delete this test
        when a row fits 992px.
        """
        panel = _build(themed, screen=(1024, 768))
        try:
            assert panel.dialog.width() <= 1024 - 32
            if has_real_fonts():
                assert panel.row_cut_px() > 0
        finally:
            panel.destroy()

    def test_the_font_database_decides_what_a_string_measures(self, themed):
        """FAILURE MEANS: the box-font premise this module's guarded
        checks rest on is stale, or `has_real_fonts` no longer tells
        the two hosts apart.

        Both halves are driven: a font database gives a proportional
        advance, and none gives one em per character whatever the
        characters are.
        """
        from PySide6.QtGui import QFontMetrics

        metrics = QFontMetrics(themed.font())
        narrow = metrics.horizontalAdvance("iiiiiiii")
        wide = metrics.horizontalAdvance("WWWWWWWW")
        if has_real_fonts():
            assert narrow < wide, (narrow, wide)
        else:
            assert narrow == wide, (narrow, wide)
