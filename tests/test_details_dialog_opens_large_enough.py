"""The Details dialog opens big enough to hold its tabs — issue #133, unit 4.

WHAT THE OPERATOR SAID, VERBATIM
================================
    "The Details panel that houses the Tranches Tab opens too small. It
     needs to be able to fully contain all tabs contents without rubber
     banding or having to be tweaked to see critical elements or data."

`Bot Settings — CHIP/USD [c8e5c5db]`, seven tabs, opened at its shipped
`setMinimumSize(640, 720)`. Content demand against the viewport it was
given, in pixels, under `cyberpunk_dark` with 58 fold tranches::

    tab                need         viewport      cut off
    Status              477x 194     616x584      none
    Settings           1036x2652     606x574      430 across, 2078 down
    Fold Tranches      1907x1053     606x574     1301 across,  479 down
    Stack Tranches      724x 275     616x574      108 across
    Bot Swarm           471x 252     616x584      none
    Market Inspector    406x 222     616x584      none
    Phantom Bots        731x 604     606x574      125 across,   30 down

THE MECHANISM, AND IT IS ONE LINE OF QT
=======================================
`QScrollArea::sizeHint` ends in `boundedTo(QSize(36 * h, 24 * h))`,
where `h` is the font height — 13px here, so **468x312**. MEM-240
wrapped every tab in one, so the dialog's layout asks each tab how big
it is and is told 432x288 by a wrapper standing in front of a
1036x2652 tab. The dialog then sizes itself to that answer. Reading the
wrapper is the defect; reading its CHILD is the repair.

WHAT THE FIX IS, AND WHAT IT IS NOT
===================================
`open_at_content_size` sets the size the dialog OPENS at. It does not
raise `setMinimumSize`, which would hand the operator a window he
cannot shrink and, below the content size, cannot fully see either. The
640x720 floor MEM-240 put there is untouched, and
`test_the_dialog_can_still_be_shrunk` is what holds that open.

It also does not make anything scroll. The scroll areas were already
there; the dialog now opens past them.

THE SCREEN IS A CEILING, NOT A TARGET
=====================================
A dialog sized to the whole display contains everything and is
unusable, so `TestTheScreenIsNotTheTarget` asserts an UPPER bound as
well as a lower one: given a 4000x4000 display the dialog is 1977x2789
— its content — and not 4000x4000.

WHAT THIS UNIT DOES NOT FIX, MEASURED
=====================================
The Settings tab wants 2652 vertical pixels of content. No clamp can
put that on a display that does not have it: at 2560x1400 it is 1460px
short, at 1920x1040 it is 1820px short. The tests in
`TestWhatStillDoesNotFit` record that, so it is a known residual rather
than a silent one. Fitting it needs the tab's ten group boxes laid out
in columns, which is a different unit and a different verb.

NOTHING WRITES UNDER `~/.acervator`. No StateManager, no clear, no
order.

FALSIFICATION: this file is wrong if (a) the shipped 640x720 dialog
cuts nothing off, (b) the repaired dialog still cuts a tab off on a
display large enough for it, (c) the dialog grows to the size of any
display handed to it, (d) it opens larger than the display, or (e) its
minimum size moved.
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

#: `QScrollArea::sizeHint` bounds itself to 36x24 character cells, so
#: no tab wrapper can report more than this however big the tab behind
#: it is. The cell is the font height, which is 13px under
#: `cyberpunk_dark` on the operator's display and is read off the
#: wrapper rather than assumed.
SCROLLAREA_CAP_CELLS_W = 36
SCROLLAREA_CAP_CELLS_H = 24

#: Font height the pixel numbers in this file were measured against.
#: Section B, D and G state exact pixel counts, and a font of another
#: height gives different ones.
MEASURED_FONT_HEIGHT_PX = 13

#: A display no tab can exhaust, used to measure what the dialog asks
#: for when nothing constrains it.
UNBOUNDED_SCREEN = (4000, 4000)

#: The size the dialog asks for on that display: every tab's content
#: plus the chrome the layout draws around it.
CONTENT_W = 1977
CONTENT_H = 2789

#: Fold tranches in the fixture. 58 is a long queue that still fits the
#: 18-row table cap unit 1 installed, so the Fold tab is at its tallest.
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


# ══════════════════════════════════════════════════════════════════════
# A. THE DEFECT — the wrapper answers for a tab it is smaller than
# ══════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════
# B. THE REPRODUCTION — what 640x720 cut off, per tab
# ══════════════════════════════════════════════════════════════════════
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
            assert cut["Settings"] == (430, 2078), cut
            assert cut["Fold Tranches"] == (1301, 479), cut
            assert cut["Stack Tranches"][0] == 108, cut
            assert cut["Phantom Bots"] == (125, 30), cut
            assert sorted(k for k, v in cut.items() if v != (0, 0)) == [
                "Fold Tranches",
                "Phantom Bots",
                "Settings",
                "Stack Tranches",
            ], cut
        finally:
            panel.destroy()


# ══════════════════════════════════════════════════════════════════════
# C. CONTAINED AFTER — no tab is cut off on a display that has room
# ══════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════
# D. THE UPPER BOUND — a dialog the size of the screen is not the fix
# ══════════════════════════════════════════════════════════════════════
class TestTheScreenIsNotTheTarget:

    def test_the_dialog_is_the_content_size_not_the_display(self, themed):
        """FAILURE MEANS: the dialog was sized to whatever display it
        found. That contains every tab, is unusable, and would pass
        every containment check above."""
        panel = _build(themed)
        try:
            assert panel.dialog.width() < UNBOUNDED_SCREEN[0]
            assert panel.dialog.height() < UNBOUNDED_SCREEN[1]
            if panel.font_height() != MEASURED_FONT_HEIGHT_PX:
                pytest.skip(_OTHER_FONT.format(height=panel.font_height()))
            assert (panel.dialog.width(), panel.dialog.height()) == (
                CONTENT_W,
                CONTENT_H,
            )
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


# ══════════════════════════════════════════════════════════════════════
# E. THE CLAMP — driven on displays that cannot hold the content
# ══════════════════════════════════════════════════════════════════════
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
            # Height is bounded by the display OR by the 640x720 floor
            # MEM-240 set, whichever is larger. Qt enforces that floor
            # whatever this code returns.
            assert panel.dialog.height() <= max(screen[1], SHIPPED_MIN_H)
        finally:
            panel.destroy()

    def test_a_display_smaller_than_the_minimum_gets_the_minimum(self, themed):
        """FAILURE MEANS: this unit moved the floor. It did not — Qt has
        enforced 640x720 since MEM-240 and still does."""
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
        """FAILURE MEANS: the dialog opens at its 640x720 minimum. Every
        other test here calls `open_at_content_size` itself, so nothing
        else in this file can tell a wired fix from an unwired one.

        Measured: deleting the call from `__init__` left all 25 other
        tests green.
        """
        from src.gui.bot_live_settings import dialog_open_size_px
        from PySide6.QtGui import QGuiApplication

        available = QGuiApplication.primaryScreen().availableGeometry()
        expected = dialog_open_size_px(
            CONTENT_W,
            CONTENT_H,
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


# ══════════════════════════════════════════════════════════════════════
# F. THE ARITHMETIC — closed table, no QApplication needed
# ══════════════════════════════════════════════════════════════════════
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


# ══════════════════════════════════════════════════════════════════════
# G. THE RESIDUAL — stated, so it is known rather than silent
# ══════════════════════════════════════════════════════════════════════
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
