"""The Details dialog opens at its content size.

``BotLiveSettingsDialog.open_at_content_size`` sizes the dialog from each
tab's own content, not from the ``QScrollArea`` wrapper whose ``sizeHint`` Qt
bounds to ``SCROLLAREA_CAP_CELLS_W`` by ``SCROLLAREA_CAP_CELLS_H`` character
cells. ``dialog_open_size_px`` then clamps that between the ``SHIPPED_MIN_W``
by ``SHIPPED_MIN_H`` floor and the display. ``TestWhatStillDoesNotFit``
records the Settings tab height no real display holds.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: The dialog's own line in `bot_live_settings.py`, and the size the
#: operator was opening at.
SHIPPED_MIN_W = 640
SHIPPED_MIN_H = 720

#: Character cells `QScrollArea::sizeHint` bounds every wrapper to.
SCROLLAREA_CAP_CELLS_W = 36
SCROLLAREA_CAP_CELLS_H = 24

#: Font height every exact pixel count here was measured against.
MEASURED_FONT_HEIGHT_PX = 13

#: A display no tab can exhaust, used to measure what the dialog asks
#: for when nothing constrains it.
UNBOUNDED_SCREEN = (4000, 4000)

#: The most the dialog may exceed its biggest tab's demand by, in pixels.
CHROME_CEILING_PX = 400

#: Which tabs the shipped minimum cuts off, as `(across, down)`.
CUT_AT_SHIPPED_MINIMUM: dict[str, tuple[bool, bool]] = {
    "Settings": (True, True),
    "Fold Tranches": (True, True),
    "Stack Tranches": (True, False),
    "Phantom Bots": (True, True),
}

#: Tabs light enough to fit the shipped dialog. Named so the check below
#: compares two populated sets rather than two empty ones.
FITS_AT_SHIPPED_MINIMUM: tuple[str, ...] = (
    "Status",
    "Bot Swarm",
    "Market Inspector",
)

#: Fold tranches in the fixture, filling the Fold tab's 18-row table cap.
FIXTURE_TRANCHES = 58

#: Said when the host measures a different character cell, so the exact
#: pixel counts below describe a layout this machine does not produce.
_OTHER_FONT = (
    "the character cell is {height}px, not the "
    f"{MEASURED_FONT_HEIGHT_PX}px these pixel counts were measured "
    "against"
)


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Exchange:
    """The one attribute `ScrummingBot.__init__` reads off it."""

    exchange_id = "test"


class _Dialog:
    """The dialog the operator opens, and what each tab asks for."""

    def __init__(self, dialog, app):
        self.dialog = dialog
        self.app = app

    @property
    def tabs(self):
        return self.dialog._tabs

    def labels(self) -> list[str]:
        return [self.tabs.tabText(i) for i in range(self.tabs.count())]

    def _content(self, index):
        from PySide6.QtWidgets import QScrollArea

        page = self.tabs.widget(index)
        page.ensurePolished()
        content = page.widget() if isinstance(page, QScrollArea) else None
        if content is None:
            content = page
        content.ensurePolished()
        return page, content

    def demand(self) -> dict:
        """What each tab's content wants, in pixels."""
        out = {}
        for i in range(self.tabs.count()):
            _page, content = self._content(i)
            hint = content.sizeHint()
            out[self.tabs.tabText(i)] = (hint.width(), hint.height())
        return out

    def wrapper_hint(self) -> dict:
        """What each tab's QScrollArea reports on that tab's behalf."""
        out = {}
        for i in range(self.tabs.count()):
            page, _content = self._content(i)
            hint = page.sizeHint()
            out[self.tabs.tabText(i)] = (hint.width(), hint.height())
        return out

    def wrapper_cap(self) -> tuple[int, int]:
        """The 36x24 character cells every wrapper is bounded to.

        Read off the wrapper's own font, because the cell is the font
        height and that is a property of the machine.
        """
        page, _content = self._content(0)
        cell = page.fontMetrics().height()
        return SCROLLAREA_CAP_CELLS_W * cell, SCROLLAREA_CAP_CELLS_H * cell

    def font_height(self) -> int:
        """The character cell the wrapper cap is built from."""
        page, _content = self._content(0)
        return page.fontMetrics().height()

    def cutoff(self) -> dict:
        """Pixels of each tab the operator cannot see without scrolling.

        Every tab is made current first: a QTabWidget lays out only the
        page on screen, so a page read while another tab is showing
        reports the geometry it had when it was last visible.
        """
        from PySide6.QtWidgets import QScrollArea

        out = {}
        for i in range(self.tabs.count()):
            self.tabs.setCurrentIndex(i)
            self.app.processEvents()
            page, content = self._content(i)
            hint = content.sizeHint()
            if isinstance(page, QScrollArea):
                view_w = page.viewport().width()
                view_h = page.viewport().height()
            else:
                view_w, view_h = page.width(), page.height()
            out[self.tabs.tabText(i)] = (
                max(0, hint.width() - view_w),
                max(0, hint.height() - view_h),
            )
        return out

    def destroy(self) -> None:
        """`deleteLater` alone IS the leak: deliver the event too."""
        from PySide6.QtCore import QCoreApplication, QEvent

        self.dialog.close()
        self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _build(app, screen=UNBOUNDED_SCREEN, tranches=FIXTURE_TRANCHES) -> _Dialog:
    """Open the dialog the way `main_window._on_bot_clicked` opens it.

    `screen` replaces the display the clamp reads, so a small-display
    case does not need a small display. `None` leaves the shipped path
    alone and lets it find the real one.
    """
    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

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
            "usd": 3.31,
            "units": 101.5,
            "ref": 0.02977,
            "initial_buy_price": 0.02957,
            "created_ts": 1_787_418_883.0 - 900.0 * i,
        }
        for i in range(tranches)
    ]
    bot._current_holdings = 8193.0
    dialog = BotLiveSettingsDialog(bot, None, None)
    if screen is not None:
        dialog.open_at_content_size(available=screen)
    dialog.show()
    app.processEvents()
    return _Dialog(dialog, app)


def _content_size(app) -> tuple[int, int]:
    """The size the dialog asks for when no display constrains it.

    Measured off a dialog built on `UNBOUNDED_SCREEN` rather than
    written down, because it is the sum of every tab's content and
    moves whenever a tab gains a widget. A caller that needs the
    UNCLAMPED demand -- to work out what a real display would do to it
    -- gets it from here.
    """
    panel = _build(app)
    try:
        return panel.dialog.width(), panel.dialog.height()
    finally:
        panel.destroy()


@pytest.fixture(autouse=True)
def themed():
    """Render under the theme `main.py` applies when none is chosen.

    An application stylesheet is global, so it is put back: a theme left
    behind changes what every later GUI file in the session renders.
    """
    app = _qt_or_skip()
    from src.gui.theme_engine import THEMES, generate_qss

    before = app.styleSheet()
    app.setStyleSheet(generate_qss(THEMES["cyberpunk_dark"]))
    yield app
    app.setStyleSheet(before)


class TestTheWrapperHidesTheTab:

    def test_every_wrapper_is_capped(self, themed):
        """FAILURE MEANS: Qt no longer caps QScrollArea.sizeHint, so the
        mechanism this fix is built on has moved and every number in
        this file describes a different Qt."""
        panel = _build(themed)
        try:
            cap_w, cap_h = panel.wrapper_cap()
            hints = panel.wrapper_hint()
            assert hints, "the dialog built no tabs"
            for label, (width, height) in hints.items():
                assert width <= cap_w, (label, width, cap_w)
                assert height <= cap_h, (label, height, cap_h)
        finally:
            panel.destroy()

    def test_the_cap_understates_the_biggest_tabs(self, themed):
        """FAILURE MEANS: the tabs now fit inside the wrapper cap, so
        there was never anything for the dialog to be too small for."""
        panel = _build(themed)
        try:
            cap_w, cap_h = panel.wrapper_cap()
            demand = panel.demand()
            wrapper = panel.wrapper_hint()
            assert demand["Settings"][1] > cap_h
            assert demand["Fold Tranches"][0] > cap_w
            assert wrapper["Settings"][1] <= cap_h
            assert wrapper["Fold Tranches"][0] <= cap_w
        finally:
            panel.destroy()

    def test_the_cap_is_the_measured_one_on_the_operators_display(self, themed):
        """FAILURE MEANS: the 13px character cell every exact pixel
        count in this file was measured against has moved, and the
        guarded sections below are recording a different machine."""
        panel = _build(themed)
        try:
            if panel.font_height() != MEASURED_FONT_HEIGHT_PX:
                pytest.skip(_OTHER_FONT.format(height=panel.font_height()))
            assert panel.wrapper_cap() == (468, 312)
        finally:
            panel.destroy()


class TestTheShippedSizeCutsTabsOff:

    def test_four_of_seven_tabs_are_cut_off_at_the_shipped_minimum(self, themed):
        """FAILURE MEANS: the panel no longer reproduces what the
        operator reported, so nothing below is measuring his defect."""
        panel = _build(themed, screen=None)
        try:
            if panel.font_height() != MEASURED_FONT_HEIGHT_PX:
                pytest.skip(_OTHER_FONT.format(height=panel.font_height()))
            panel.dialog.resize(SHIPPED_MIN_W, SHIPPED_MIN_H)
            themed.processEvents()
            cut = panel.cutoff()
            assert sorted(k for k, v in cut.items() if v != (0, 0)) == sorted(
                CUT_AT_SHIPPED_MINIMUM
            ), cut
            assert sorted(k for k, v in cut.items() if v == (0, 0)) == sorted(
                FITS_AT_SHIPPED_MINIMUM
            ), cut
            for label, (across, down) in CUT_AT_SHIPPED_MINIMUM.items():
                assert (cut[label][0] > 0) is across, (label, cut[label])
                assert (cut[label][1] > 0) is down, (label, cut[label])
            demand = panel.demand()
            assert cut["Settings"][1] > demand["Settings"][1] / 2, (cut, demand)
            assert cut["Fold Tranches"][0] > demand["Fold Tranches"][0] / 2, (
                cut,
                demand,
            )
        finally:
            panel.destroy()


class TestEveryTabIsContained:

    def test_nothing_is_cut_off(self, themed):
        """FAILURE MEANS: a tab still needs scrolling on a display big
        enough for it, which is exactly what the operator reported."""
        panel = _build(themed)
        try:
            cut = panel.cutoff()
            assert len(cut) == 7, panel.labels()
            assert all(v == (0, 0) for v in cut.values()), cut
        finally:
            panel.destroy()

    def test_an_empty_queue_is_contained_too(self, themed):
        """FAILURE MEANS: the size was fitted to one queue length, and a
        bot with no tranches opens wrong."""
        panel = _build(themed, tranches=0)
        try:
            assert all(v == (0, 0) for v in panel.cutoff().values())
        finally:
            panel.destroy()


class TestTheScreenIsNotTheTarget:

    def test_the_dialog_is_the_content_size_not_the_display(self, themed):
        """FAILURE MEANS: the dialog was sized to whatever display it
        found. That contains every tab, is unusable, and would pass
        every containment check above."""
        panel = _build(themed)
        try:
            assert panel.dialog.width() < UNBOUNDED_SCREEN[0]
            assert panel.dialog.height() < UNBOUNDED_SCREEN[1]
            demand = panel.demand()
            assert demand, "the dialog built no tabs"
            widest = max(width for width, _ in demand.values())
            tallest = max(height for _, height in demand.values())
            surplus_w = panel.dialog.width() - widest
            surplus_h = panel.dialog.height() - tallest
            assert surplus_w >= 0, (panel.dialog.width(), widest)
            assert surplus_h >= 0, (panel.dialog.height(), tallest)
            assert surplus_w < CHROME_CEILING_PX, (surplus_w, demand)
            assert surplus_h < CHROME_CEILING_PX, (surplus_h, demand)
        finally:
            panel.destroy()

    def test_a_bigger_display_does_not_make_a_bigger_dialog(self, themed):
        """FAILURE MEANS: the size tracks the display rather than the
        content, so the operator's window grows when he plugs in a
        monitor."""
        small = _build(themed, screen=(4000, 4000))
        big = _build(themed, screen=(9000, 9000))
        try:
            assert small.dialog.size() == big.dialog.size()
        finally:
            small.destroy()
            big.destroy()


class TestTheDialogStaysOnTheScreen:

    @pytest.mark.parametrize(
        "screen", [(2560, 1400), (1920, 1040), (1366, 768), (1024, 768)]
    )
    def test_it_never_opens_wider_or_taller_than_the_display(self, themed, screen):
        """FAILURE MEANS: part of the dialog hangs off the display, and
        the operator cannot drag back what he cannot grab."""
        panel = _build(themed, screen=screen)
        try:
            assert panel.dialog.width() <= screen[0]
            # Qt enforces `SHIPPED_MIN_H` whatever the clamp returns.
            assert panel.dialog.height() <= max(screen[1], SHIPPED_MIN_H)
        finally:
            panel.destroy()

    def test_a_display_smaller_than_the_minimum_gets_the_minimum(self, themed):
        """A display under the floor still opens at ``SHIPPED_MIN_W`` by
        ``SHIPPED_MIN_H``."""
        panel = _build(themed, screen=(640, 480))
        try:
            assert panel.dialog.width() == SHIPPED_MIN_W
            assert panel.dialog.height() == SHIPPED_MIN_H
        finally:
            panel.destroy()

    def test_the_dialog_can_still_be_shrunk(self, themed):
        """FAILURE MEANS: the fix raised the MINIMUM instead of the
        opening size, and the operator now has a window he cannot make
        smaller than his screen."""
        panel = _build(themed)
        try:
            assert panel.dialog.minimumWidth() == SHIPPED_MIN_W
            assert panel.dialog.minimumHeight() == SHIPPED_MIN_H
            panel.dialog.resize(SHIPPED_MIN_W, SHIPPED_MIN_H)
            themed.processEvents()
            assert panel.dialog.width() == SHIPPED_MIN_W
            assert panel.dialog.height() == SHIPPED_MIN_H
        finally:
            panel.destroy()

    def test_the_constructor_is_what_applies_the_size(self, themed):
        """``BotLiveSettingsDialog.__init__`` itself applies the open size.

        Every other test here calls ``open_at_content_size`` directly, so this
        is the only one that sees the constructor's own call.
        """
        from src.gui.bot_live_settings import dialog_open_size_px
        from PySide6.QtGui import QGuiApplication

        available = QGuiApplication.primaryScreen().availableGeometry()
        content_w, content_h = _content_size(themed)
        expected = dialog_open_size_px(
            content_w,
            content_h,
            available.width(),
            available.height(),
            SHIPPED_MIN_W,
            SHIPPED_MIN_H,
        )
        if expected == (SHIPPED_MIN_W, SHIPPED_MIN_H):
            pytest.skip(
                f"a {available.width()}x{available.height()} display clamps "
                "back to the minimum, so this host cannot tell the fix from "
                "its absence"
            )
        panel = _build(themed, screen=None)
        try:
            assert (panel.dialog.width(), panel.dialog.height()) == expected
        finally:
            panel.destroy()

    def test_the_real_display_is_what_the_dialog_reads(self, themed):
        """FAILURE MEANS: the shipped path consults no screen, so every
        clamp proved above is proved about a test argument and about
        nothing the operator will ever run."""
        from PySide6.QtGui import QGuiApplication

        available = QGuiApplication.primaryScreen().availableGeometry()
        panel = _build(themed, screen=None)
        try:
            assert panel.dialog.width() <= max(available.width(), SHIPPED_MIN_W)
            assert panel.dialog.height() <= max(available.height(), SHIPPED_MIN_H)
        finally:
            panel.destroy()


class TestTheClampArithmetic:

    @pytest.mark.parametrize(
        "needed,available,expected",
        [
            # content smaller than the display: the content wins
            ((900, 900), (4000, 4000), (900, 900)),
            # content bigger than the display: the display wins, less
            # the window-frame allowance
            ((5000, 5000), (1920, 1040), (1888, 968)),
            # exactly at the ceiling
            ((1888, 968), (1920, 1040), (1888, 968)),
            # one pixel over it
            ((1889, 969), (1920, 1040), (1888, 968)),
            # below the dialog's own floor: the floor wins
            ((100, 100), (4000, 4000), (640, 720)),
            # a display below the floor: the floor still wins, because
            # Qt enforces it whatever this returns
            ((5000, 5000), (640, 480), (640, 720)),
            # a zero display, which is what a headless host reports
            ((5000, 5000), (0, 0), (640, 720)),
        ],
    )
    def test_the_table(self, needed, available, expected):
        """FAILURE MEANS: the clamp admits a size outside the band
        between the dialog's floor and the display's ceiling."""
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

    def test_the_chrome_is_added_to_the_content(self):
        """FAILURE MEANS: the dialog is sized to its tab content with no
        room for the header, tab bar and button row, so the bottom of
        every tab sits under the Close button."""
        from src.gui.bot_live_settings import dialog_content_size_px

        # A 538x449 dialog hint around a 468x312 page hint is 70 across
        # and 137 down of chrome, added to a 1907x2652 tab.
        assert dialog_content_size_px(538, 449, 468, 312, 1907, 2652) == (1977, 2789)


class TestWhatStillDoesNotFit:

    @pytest.mark.parametrize(
        "screen,short_by", [((2560, 1400), 1460), ((1920, 1040), 1820)]
    )
    def test_the_settings_tab_is_taller_than_a_real_display(
        self, themed, screen, short_by
    ):
        """FAILURE MEANS: the Settings tab now fits a real display and
        this recorded residual is stale — delete it, do not widen it.

        2652px of content in ten group boxes cannot be put on a display
        1400px tall. Laying them out in columns is a different unit;
        this records the shortfall so nobody reads the fix as covering
        it.
        """
        panel = _build(themed, screen=screen)
        try:
            across, down = panel.cutoff()["Settings"]
            assert across == 0, across
            assert down > 0, down
            if panel.font_height() != MEASURED_FONT_HEIGHT_PX:
                pytest.skip(_OTHER_FONT.format(height=panel.font_height()))
            assert (across, down) == (0, short_by)
        finally:
            panel.destroy()

    def test_no_other_tab_is_cut_off_at_wqhd(self, themed):
        """FAILURE MEANS: the residual is wider than Settings, and the
        sentence above understates what the operator still has to
        scroll."""
        panel = _build(themed, screen=(2560, 1400))
        try:
            cut = panel.cutoff()
            assert [k for k, v in cut.items() if v != (0, 0)] == ["Settings"], cut
        finally:
            panel.destroy()
