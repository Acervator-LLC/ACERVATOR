"""The Fold-Tranche panel surface, driven through `_Panel` on a real `ScrummingBot`.

`TestTheFireDialogNamesTheClickedRow` asserts the confirmation names the row on
screen while the order goes to the resolved index. `TestTheHeightCap`,
`TestEveryColumnIsDocumented`, `TestTheAllotmentTotal` and
`TestThePersistedQuantities` cover the remaining rows. Each repair has a control
named `_without_...` that puts the tree back and reproduces the measured before
number. No `StateManager` is built and nothing writes outside `tmp_path`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: Frozen clock. The tab reads the wall clock, so every age below is an
#: offset from this and never from "now".
NOW = 1_800_000_000.0

#: TAO's live shape when the issue was filed: 58 open tranches, and the
#: oldest one 30.4 days old sitting well down the queue.
TAO_TRANCHES = 58
TAO_OLDEST_INDEX = 57
TAO_OLDEST_DAYS = 30.4

COL_INDEX = 0
COL_AGE = 1
COL_FIRE = 9

#: The audit's measured before/after for the visible-row count.
ROWS_VISIBLE_BEFORE = 8
OLD_MAX_HEIGHT_PX = 280


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


class _Exchange:
    """The one attribute ``ScrummingBot.__init__`` reads off it."""

    exchange_id = "test"


def _tranche(
    i: int, *, age_days: float, usd: float = 1.0, units: float = 0.001
) -> dict:
    return {
        "usd": usd,
        "units": units,
        "ref": 30000.0 + i,
        "initial_buy_price": 29000.0 + i,
        "created_ts": NOW - age_days * 86400.0,
    }


def _tao_tranches() -> list[dict]:
    """58 tranches. The OLDEST is last in the queue, as TAO's was.

    Rows one to three are the 2.7d, 2.7d and 3.6d the evaluation read
    off the shipped panel, so the fixture reproduces the exact reach
    problem rather than a convenient one.
    """
    rows = [
        _tranche(0, age_days=2.7),
        _tranche(1, age_days=2.7),
        _tranche(2, age_days=3.6),
    ]
    rows += [_tranche(i, age_days=4.0 + i * 0.1) for i in range(3, TAO_OLDEST_INDEX)]
    rows.append(_tranche(TAO_OLDEST_INDEX, age_days=TAO_OLDEST_DAYS))
    assert len(rows) == TAO_TRANCHES
    return rows


class _Panel:
    """Kept as an object so Qt does not collect the tree mid-test."""

    def __init__(self, bot, dialog, tabs):
        self.bot = bot
        self.dialog = dialog
        self.tabs = tabs

    @property
    def table(self):
        return self.dialog._fold_tranche_table

    def cell(self, row, col) -> str:
        item = self.table.item(row, col)
        return "" if item is None else item.text()

    def fire_buttons(self) -> list:
        from PySide6.QtWidgets import QPushButton

        return [
            b
            for b in self.dialog._fold_tab_page.findChildren(QPushButton)
            if b.text() == "Fire"
        ]

    def header_tooltips(self) -> list[str]:
        table = self.table
        return [
            (
                table.horizontalHeaderItem(c).toolTip()
                if table.horizontalHeaderItem(c) is not None
                else ""
            )
            for c in range(table.columnCount())
        ]

    def health_rows(self) -> list[tuple[str, str, str, str]]:
        """``(label, value, label_tooltip, value_tooltip)`` per row."""
        from PySide6.QtWidgets import QFormLayout, QGroupBox, QLabel

        for box in self.dialog._fold_tab_page.findChildren(QGroupBox):
            if not box.title().startswith("Fold-Tranche"):
                continue
            form = box.layout()
            out = []
            for r in range(form.rowCount()):
                li = form.itemAt(r, QFormLayout.LabelRole)
                fi = form.itemAt(r, QFormLayout.FieldRole)
                lw = li.widget() if li is not None else None
                fw = fi.widget() if fi is not None else None
                out.append(
                    (
                        lw.text() if isinstance(lw, QLabel) else "",
                        fw.text() if isinstance(fw, QLabel) else "",
                        lw.toolTip() if lw is not None else "",
                        fw.toolTip() if fw is not None else "",
                    )
                )
            return out
        return []

    def row_labelled(self, label: str):
        for row in self.health_rows():
            if row[0] == label:
                return row
        return None


def _make_panel(tranches, monkeypatch, **bot_attrs) -> _Panel:
    _qt_or_skip()
    from PySide6.QtWidgets import QDialog, QTabWidget, QWidget

    import time as _clock

    monkeypatch.setattr(_clock, "time", lambda: NOW)

    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.trading.bot_container import BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="BTC",
        target_balance=100.0,
    )
    bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
    bot._fold_tranches = list(tranches)
    for name, value in bot_attrs.items():
        setattr(bot, name, value)

    dialog = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dialog)
    dialog._bot = bot
    dialog._bm = None
    dialog._changes = {}
    tabs = QTabWidget()
    dialog._tabs = tabs
    tabs.addTab(QWidget(), "Status")
    dialog._install_fold_tranches_tab(tabs)
    return _Panel(bot, dialog, tabs)


def _painted_colours(widget) -> set[str]:
    """Return every colour actually PAINTED by `widget`.

    READ THE RENDER, NOT THE MODEL. `styleSheet()` reports what a
    widget was TOLD to paint. A stylesheet rule for the same element
    overrides it at paint time and the getter keeps returning the old
    value forever, so a colour test built on the getter passes on a
    panel the operator sees in a different colour. `tests/qt_pixel.py`
    exists for exactly this, and its docstring carries the 2026-08-11
    measurement that produced it.

    The whole render is scanned rather than one sample point, because
    the colour under test is a FOREGROUND: it lands on glyph pixels
    whose position depends on the font, and a fixed point would be a
    test of where the text happens to sit.
    """
    from PySide6.QtGui import QColor

    from qt_pixel import render_widget

    image = render_widget(widget, size=(640, 32))
    return {
        QColor(image.pixelColor(x, y)).name().lower()
        for y in range(image.height())
        for x in range(image.width())
    }


def _destroy(panel: _Panel) -> None:
    """Tear ``panel`` down and deliver the delete.

    ``setParent(None)`` is a no-op on a widget that never had a parent, and
    ``processEvents()`` does not deliver ``DeferredDelete`` on its own.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    for widget in (panel.tabs, panel.dialog):
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def panel(monkeypatch):
    built = _make_panel(_tao_tranches(), monkeypatch, _current_holdings=0.1)
    yield built
    _destroy(built)


class _Messages:
    def __init__(self):
        self.seen: list[dict] = []

    def of(self, kind: str) -> dict | None:
        for event in self.seen:
            if event["kind"] == kind:
                return event
        return None

    @property
    def confirm(self) -> str:
        found = self.of("question")
        assert found is not None, (
            f"no confirmation was offered; the handler raised "
            f"{[e['kind'] for e in self.seen]}"
        )
        return found["text"]


def _patch_message_box(monkeypatch, answer_yes: bool = True) -> _Messages:
    """Answer the confirmation and record every message.

    ``_on_fire_tranche_clicked`` imports ``QMessageBox`` from
    ``PySide6.QtWidgets`` inside its own body, so the module attribute
    is the binding it resolves and the one worth replacing.
    """
    import PySide6.QtWidgets as _QtWidgets

    log = _Messages()

    class _Box:
        Yes = 0x4000
        No = 0x10000

        @classmethod
        def _record(cls, kind, title, text):
            log.seen.append({"kind": kind, "title": title, "text": text})

        @classmethod
        def information(cls, _p, title, text, *_a, **_k):
            cls._record("information", title, text)

        @classmethod
        def warning(cls, _p, title, text, *_a, **_k):
            cls._record("warning", title, text)

        @classmethod
        def critical(cls, _p, title, text, *_a, **_k):
            cls._record("critical", title, text)

        @classmethod
        def question(cls, _p, title, text, *_a, **_k):
            cls._record("question", title, text)
            return _Box.Yes if answer_yes else _Box.No

    monkeypatch.setattr(_QtWidgets, "QMessageBox", _Box)
    return log


class _Dispatch:
    """Records the index the ORDER was sized against."""

    def __init__(self):
        self.indices: list[int] = []


def _patch_dispatch(monkeypatch, panel: _Panel) -> _Dispatch:
    """Catch ``manual_fire_tranche(idx)`` without touching a real loop.

    The handler schedules onto ``self._bm._async_loop``. A stub loop and
    a stub ``run_coroutine_threadsafe`` keep the whole dispatch inside
    this process: no coroutine is ever awaited and no order exists.
    """
    import asyncio

    record = _Dispatch()

    async def _fake_fire(idx):
        return None

    def _capture(idx):
        record.indices.append(idx)
        return _fake_fire(idx)

    monkeypatch.setattr(panel.bot, "manual_fire_tranche", _capture, raising=False)

    class _Future:
        def done(self):
            return False

        def cancel(self):
            return True

    def _schedule(coro, _loop):
        coro.close()  # never awaited; close it so Qt stays quiet
        return _Future()

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", _schedule)

    class _BM:
        _async_loop = object()

    panel.dialog._bm = _BM()
    return record


def _without_the_click_time_capture(tranche, panel, monkeypatch):
    """Call the handler exactly as the pre-repair button called it.

    The repair added a second argument to the button's closure. The
    control drops it, which is byte-for-byte the shipped call before
    this unit, and the handler's documented fallback then prints the
    re-resolved index — the defect.
    """
    panel.dialog._on_fire_tranche_clicked(tranche)


def _without_the_header_tooltips(monkeypatch):
    """Restore the measured BEFORE: no per-column documentation."""
    import src.gui.live_settings.fold_tranches_tab as mod

    assert len(mod.FOLD_COLUMN_TOOLTIPS) == 11, (
        "the control must patch a name that carries the repair; "
        "an empty tuple here would prove nothing"
    )
    monkeypatch.setattr(mod, "FOLD_COLUMN_TOOLTIPS", ())


def _without_the_row_order(monkeypatch):
    """Restore the measured BEFORE: insertion order, always."""
    import src.gui.live_settings.fold_tranches_tab as mod

    assert callable(mod.fold_display_order)
    monkeypatch.setattr(
        mod,
        "fold_display_order",
        lambda tranches, order: list(enumerate(list(tranches or []))),
    )


def _coerce_refused_to_zero(tranches, field, descending):
    """The sorter this unit did NOT write: refused values priced at 0.0.

    Kept here so the difference between the two is asserted rather than
    described. A corrupt record sorted to the top of "Smallest USD
    first" would have told the operator it was the smallest tranche
    they own.
    """
    from src.trading.bot_container import as_finite_float

    rows = []
    for index, tranche in enumerate(tranches):
        value = as_finite_float(tranche.get(field))
        rows.append((index, tranche, 0.0 if value is None else value))
    rows.sort(key=lambda r: (-r[2], r[0]) if descending else (r[2], r[0]))
    return [(i, t) for i, t, _ in rows]


def test_the_panel_starts_by_showing_all_58(panel):
    assert panel.table is not None
    assert panel.table.rowCount() == TAO_TRANCHES
    assert len(panel.fire_buttons()) == TAO_TRANCHES
    assert panel.cell(0, COL_INDEX) == "1"


def test_the_fixture_reproduces_taos_reach_problem(panel):
    """Rows one to three are 2.7d, 2.7d and 3.6d, as measured on TAO,
    and the 30.4-day tranche the summary names is not among them."""
    assert [panel.cell(r, COL_AGE) for r in range(3)] == ["2.7d", "2.7d", "3.6d"]
    assert panel.row_labelled("Oldest tranche age:")[1] == "30.4d"


class TestTheFireDialogNamesTheClickedRow:

    #: The row the operator presses, one-based, as printed on screen.
    CLICKED_ROW = 7

    def _diverge(self, panel):
        """Consume the FIRST tranche after the panel was built.

        This is the live mechanism, not a contrivance: an auto-fold
        takes a tranche off the front of ``_fold_tranches`` while the
        snapshot sits on screen, and every later index drops by one.
        Returns the clicked tranche and the index it now resolves to.
        """
        clicked = panel.bot._fold_tranches[self.CLICKED_ROW - 1]
        panel.bot._fold_tranches.pop(0)
        resolved = panel.bot._fold_tranches.index(clicked)
        assert resolved + 1 != self.CLICKED_ROW, (
            "the fixture must DIVERGE; a case where the row and the "
            "index coincide passes before and after the repair"
        )
        return clicked, resolved

    def test_the_row_and_the_index_really_do_diverge(self, panel):
        """The calibration itself. If this stops holding, every
        assertion below is testing the easy case by accident."""
        _, resolved = self._diverge(panel)
        assert resolved + 1 == self.CLICKED_ROW - 1 == 6

    def test_the_confirmation_names_the_clicked_row(self, panel, monkeypatch):
        clicked, resolved = self._diverge(panel)
        messages = _patch_message_box(monkeypatch, answer_yes=False)
        _patch_dispatch(monkeypatch, panel)

        panel.dialog._on_fire_tranche_clicked(clicked, self.CLICKED_ROW)

        assert f"Fire tranche #{self.CLICKED_ROW}?" in messages.confirm
        assert f"Fire tranche #{resolved + 1}?" not in messages.confirm

    def test_the_confirmation_says_the_queue_moved(self, panel, monkeypatch):
        """Naming the clicked row is not enough on its own. The operator
        is about to authorise a buy against a queue that shifted under
        the panel, and that is something they should be told."""
        clicked, resolved = self._diverge(panel)
        messages = _patch_message_box(monkeypatch, answer_yes=False)
        _patch_dispatch(monkeypatch, panel)

        panel.dialog._on_fire_tranche_clicked(clicked, self.CLICKED_ROW)

        text = messages.confirm
        assert "THE QUEUE HAS MOVED" in text
        assert f"printed #{self.CLICKED_ROW}" in text
        assert f"sits at #{resolved + 1}" in text

    def test_the_order_still_goes_to_the_resolved_index(self, panel, monkeypatch):
        """THE OTHER HALF. Naming the right row must not cost firing the
        right tranche. ``manual_fire_tranche`` indexes the LIVE list, so
        it keeps the resolved index and not the printed one."""
        clicked, resolved = self._diverge(panel)
        _patch_message_box(monkeypatch, answer_yes=True)
        dispatch = _patch_dispatch(monkeypatch, panel)

        panel.dialog._on_fire_tranche_clicked(clicked, self.CLICKED_ROW)

        assert dispatch.indices == [resolved]
        assert resolved != self.CLICKED_ROW - 1

    def test_the_dispatch_message_names_the_clicked_row(self, panel, monkeypatch):
        clicked, resolved = self._diverge(panel)
        messages = _patch_message_box(monkeypatch, answer_yes=True)
        _patch_dispatch(monkeypatch, panel)

        panel.dialog._on_fire_tranche_clicked(clicked, self.CLICKED_ROW)

        text = messages.of("information")["text"]
        assert f"tranche #{self.CLICKED_ROW}." in text
        assert f"tranche #{resolved + 1}." not in text

    def test_the_control_reproduces_the_defect(self, panel, monkeypatch):
        """WITHOUT the click-time capture the dialog names the resolved
        index — the measured BEFORE. A repair whose control cannot
        reproduce the defect proves nothing about the repair."""
        clicked, resolved = self._diverge(panel)
        messages = _patch_message_box(monkeypatch, answer_yes=False)
        _patch_dispatch(monkeypatch, panel)

        _without_the_click_time_capture(clicked, panel, monkeypatch)

        assert f"Fire tranche #{resolved + 1}?" in messages.confirm
        assert f"Fire tranche #{self.CLICKED_ROW}?" not in messages.confirm

    def test_nothing_is_said_about_a_queue_that_did_not_move(self, panel, monkeypatch):
        """The note is a VERDICT, not a constant. A panel nobody has
        raced against says nothing about a shift."""
        clicked = panel.bot._fold_tranches[self.CLICKED_ROW - 1]
        messages = _patch_message_box(monkeypatch, answer_yes=False)
        _patch_dispatch(monkeypatch, panel)

        panel.dialog._on_fire_tranche_clicked(clicked, self.CLICKED_ROW)

        assert f"Fire tranche #{self.CLICKED_ROW}?" in messages.confirm
        assert "THE QUEUE HAS MOVED" not in messages.confirm

    def test_a_vanished_tranche_names_the_row_that_was_pressed(
        self, panel, monkeypatch
    ):
        """There is no index to resolve when the tranche is gone, so the
        clicked number is the only thing that can say WHICH row the
        operator lost."""
        clicked = panel.bot._fold_tranches[self.CLICKED_ROW - 1]
        panel.bot._fold_tranches.remove(clicked)
        messages = _patch_message_box(monkeypatch)

        panel.dialog._on_fire_tranche_clicked(clicked, self.CLICKED_ROW)

        warning = messages.of("warning")
        assert warning is not None
        assert f"Tranche #{self.CLICKED_ROW} is no longer" in warning["text"]

    def test_the_refusal_names_the_clicked_row_and_logs_both(
        self, panel, monkeypatch, capture_log
    ):
        """A tranche this panel cannot read is refused BEFORE the
        confirmation. That refusal is operator-facing too, so it names
        the clicked row; the log line carries both numbers, because a
        reader chasing the record needs the queue index."""
        clicked, resolved = self._diverge(panel)
        clicked["usd"] = float("nan")
        messages = _patch_message_box(monkeypatch)

        with capture_log("acervator.gui") as records:
            panel.dialog._on_fire_tranche_clicked(clicked, self.CLICKED_ROW)

        critical = messages.of("critical")
        assert critical is not None
        assert f"Tranche #{self.CLICKED_ROW} was NOT fired" in critical["text"]
        assert messages.of("question") is None

        lines = [r.getMessage() for r in records]
        assert any(
            f"tranche #{self.CLICKED_ROW} (queue index " f"{resolved + 1})" in line
            for line in lines
        ), lines


def test_the_shipped_fire_button_passes_the_queue_index(panel, monkeypatch):
    """THE WIRING, not a hand-made call.

    The assertions above drive the handler directly. This one presses
    the button the builder actually made, so the closure that carries
    the number is the shipped one.
    """
    seen: list[tuple] = []
    monkeypatch.setattr(
        type(panel.dialog),
        "_on_fire_tranche_clicked",
        lambda self, tranche, number=None: seen.append((tranche, number)),
    )

    panel.fire_buttons()[6].click()

    assert seen and seen[0][1] == 7
    assert seen[0][0] is panel.bot._fold_tranches[6]


def test_the_button_carries_the_queue_index_under_a_sort(monkeypatch):
    """The number captured is the QUEUE index, never the visual row.

    Under "Oldest first" the oldest tranche is drawn at visual row 0
    while it still sits at queue position 58. Pressing the top button
    must carry 58, because 58 is what the `#` cell beside it prints and
    what the operator reads.
    """
    built = _make_panel(_tao_tranches(), monkeypatch, _current_holdings=0.1)
    try:
        from src.gui.bot_live_settings import FOLD_SORT_OLDEST_FIRST

        built.dialog._fold_sort_key = FOLD_SORT_OLDEST_FIRST
        assert built.dialog._refresh_fold_tranches_tab() == "refreshed"

        assert built.cell(0, COL_INDEX) == str(TAO_OLDEST_INDEX + 1)

        seen: list[tuple] = []
        monkeypatch.setattr(
            type(built.dialog),
            "_on_fire_tranche_clicked",
            lambda self, tranche, number=None: seen.append((tranche, number)),
        )
        built.fire_buttons()[0].click()

        assert seen and seen[0][1] == TAO_OLDEST_INDEX + 1
        assert seen[0][0] is built.bot._fold_tranches[TAO_OLDEST_INDEX]
    finally:
        _destroy(built)


class TestTheHeightCap:

    def test_the_old_cap_really_did_show_about_eight_rows(self):
        """The BEFORE number, computed rather than quoted. 280px over
        30px rows and a header leaves room for eight."""
        from src.gui.bot_live_settings import (
            TRANCHE_ROW_HEIGHT_PX,
            TRANCHE_TABLE_HEADER_PX,
        )

        room = OLD_MAX_HEIGHT_PX - TRANCHE_TABLE_HEADER_PX
        assert room // TRANCHE_ROW_HEIGHT_PX == ROWS_VISIBLE_BEFORE

    def test_a_long_queue_now_shows_far_more(self):
        from src.gui.bot_live_settings import (
            TRANCHE_ROW_HEIGHT_PX,
            TRANCHE_TABLE_VISIBLE_ROWS,
            fold_table_max_height_px,
        )

        tall = fold_table_max_height_px(230)
        assert tall > OLD_MAX_HEIGHT_PX
        assert TRANCHE_TABLE_VISIBLE_ROWS > ROWS_VISIBLE_BEFORE
        assert tall >= TRANCHE_TABLE_VISIBLE_ROWS * TRANCHE_ROW_HEIGHT_PX

    def test_a_short_queue_does_not_get_a_tall_empty_box(self):
        from src.gui.bot_live_settings import fold_table_max_height_px

        assert fold_table_max_height_px(3) < fold_table_max_height_px(30)

    def test_an_empty_or_refused_count_still_returns_one_row(self):
        from src.gui.bot_live_settings import fold_table_max_height_px

        assert fold_table_max_height_px(0) == fold_table_max_height_px(1)
        assert fold_table_max_height_px(None) > 0

    def test_the_built_table_carries_the_new_cap(self, panel):
        assert panel.table.maximumHeight() > OLD_MAX_HEIGHT_PX


class TestTheRowOrder:

    def test_queue_order_is_the_default_and_changes_nothing(self, panel):
        from src.gui.bot_live_settings import fold_sort_order

        assert fold_sort_order(panel.dialog) == "Queue order"
        assert [panel.cell(r, COL_INDEX) for r in range(3)] == ["1", "2", "3"]

    def test_oldest_first_brings_the_headline_row_to_the_top(self, panel):
        """THE DEFECT, ANSWERED. The summary names a 30.4-day tranche;
        before this the operator had to scroll 58 rows to find it."""
        from src.gui.bot_live_settings import FOLD_SORT_OLDEST_FIRST

        panel.dialog._fold_sort_key = FOLD_SORT_OLDEST_FIRST
        assert panel.dialog._refresh_fold_tranches_tab() == "refreshed"

        assert panel.cell(0, COL_AGE) == "30.4d"
        assert panel.cell(0, COL_AGE) == panel.row_labelled("Oldest tranche age:")[1]

    def test_the_index_column_still_names_the_queue_position(self, panel):
        """Re-ordering the DISPLAY must never renumber a tranche."""
        from src.gui.bot_live_settings import FOLD_SORT_OLDEST_FIRST

        panel.dialog._fold_sort_key = FOLD_SORT_OLDEST_FIRST
        panel.dialog._refresh_fold_tranches_tab()

        assert panel.cell(0, COL_INDEX) == str(TAO_OLDEST_INDEX + 1)

    def test_the_control_reproduces_the_defect(self, panel, monkeypatch):
        """WITHOUT the order the headline row stays out of reach."""
        from src.gui.bot_live_settings import FOLD_SORT_OLDEST_FIRST

        _without_the_row_order(monkeypatch)
        panel.dialog._fold_sort_key = FOLD_SORT_OLDEST_FIRST
        panel.dialog._refresh_fold_tranches_tab()

        assert panel.cell(0, COL_AGE) == "2.7d"

    def test_qt_sorting_stays_off_because_it_would_orphan_the_buttons(self, panel):
        """``QTableWidget`` sorting moves ITEMS and leaves
        ``setCellWidget`` widgets behind. On this table that would slide
        every row's text out from under its own Fire button."""
        assert panel.table.isSortingEnabled() is False


class TestTheSorterAdmission:

    def _mixed(self):
        good = _tranche(0, age_days=1.0, usd=5.0)
        refused = dict(_tranche(1, age_days=2.0), usd=float("nan"))
        other = _tranche(2, age_days=3.0, usd=9.0)
        return [good, refused, other]

    def test_a_refused_value_goes_last_and_keeps_queue_order(self):
        from src.gui.bot_live_settings import (
            FOLD_SORT_SMALLEST_FIRST,
            fold_display_order,
        )

        rows = self._mixed()
        order = fold_display_order(rows, FOLD_SORT_SMALLEST_FIRST)

        assert [i for i, _ in order] == [0, 2, 1]

    def test_the_control_would_have_sorted_the_corrupt_row_first(self):
        """The sorter this unit did NOT write. Priced at 0.0 the ``nan``
        row becomes the smallest tranche the operator owns."""
        rows = self._mixed()
        wrong = _coerce_refused_to_zero(rows, "usd", descending=False)

        assert [i for i, _ in wrong][0] == 1

    def test_an_unknown_order_returns_the_queue_untouched(self):
        from src.gui.bot_live_settings import fold_display_order

        rows = self._mixed()
        assert fold_display_order(rows, "Nonsense") == list(enumerate(rows))

    def test_ties_keep_the_queue_order_in_both_directions(self):
        from src.gui.bot_live_settings import (
            FOLD_SORT_LARGEST_FIRST,
            FOLD_SORT_SMALLEST_FIRST,
            fold_display_order,
        )

        rows = [_tranche(i, age_days=1.0, usd=4.0) for i in range(4)]
        for order in (FOLD_SORT_SMALLEST_FIRST, FOLD_SORT_LARGEST_FIRST):
            assert [i for i, _ in fold_display_order(rows, order)] == [
                0,
                1,
                2,
                3,
            ], order

    def test_every_offered_order_is_reachable_and_reads_a_real_field(self):
        from src.gui.bot_live_settings import (
            FOLD_SORT_KEYS,
            FOLD_SORT_ORDERS,
            fold_display_order,
        )

        rows = self._mixed()
        for order in FOLD_SORT_ORDERS:
            assert len(fold_display_order(rows, order)) == len(rows)
        for field, _ in FOLD_SORT_KEYS.values():
            assert field in rows[0], field

    def test_an_order_this_panel_does_not_offer_is_refused(self, panel):
        """A bad order must not blank the table or start a rebuild."""
        from src.gui.bot_live_settings import fold_sort_order, on_fold_sort_changed

        on_fold_sort_changed(panel.dialog, "Cheapest first")
        assert fold_sort_order(panel.dialog) == "Queue order"


class TestTheFilter:

    def test_a_blank_needle_matches_everything(self):
        from src.gui.bot_live_settings import fold_row_matches_filter

        for needle in ("", "   ", None):
            assert fold_row_matches_filter(["a", "b"], needle) is True

    def test_it_matches_any_cell_and_ignores_case(self):
        from src.gui.bot_live_settings import fold_row_matches_filter

        cells = ["7", "30.4d", "auto scrum"]
        assert fold_row_matches_filter(cells, "AUTO") is True
        assert fold_row_matches_filter(cells, "30.4") is True
        assert fold_row_matches_filter(cells, "manual") is False

    def test_the_built_table_hides_only_the_rows_that_miss(self, panel):
        from src.gui.bot_live_settings import on_fold_filter_changed

        on_fold_filter_changed(panel.dialog, "30.4d")

        shown = [
            r for r in range(panel.table.rowCount()) if not panel.table.isRowHidden(r)
        ]
        assert shown == [TAO_OLDEST_INDEX]

    def test_clearing_the_box_restores_every_row(self, panel):
        from src.gui.bot_live_settings import on_fold_filter_changed

        on_fold_filter_changed(panel.dialog, "30.4d")
        on_fold_filter_changed(panel.dialog, "")

        assert not any(
            panel.table.isRowHidden(r) for r in range(panel.table.rowCount())
        )

    def test_a_needle_that_matches_nothing_hides_everything(self, panel):
        """The other side of the same control. A filter that could only
        ever show rows would pass the two tests above."""
        from src.gui.bot_live_settings import on_fold_filter_changed

        on_fold_filter_changed(panel.dialog, "zzz-no-such-row")

        assert all(panel.table.isRowHidden(r) for r in range(panel.table.rowCount()))

    def test_the_shipped_box_is_wired_to_the_table(self, panel):
        """The widget the builder made, not a hand call."""
        panel.dialog._fold_filter_edit.setText("30.4d")

        shown = [
            r for r in range(panel.table.rowCount()) if not panel.table.isRowHidden(r)
        ]
        assert shown == [TAO_OLDEST_INDEX]


TOOLTIP_WORD_LIMIT = 12

BANNED_TOOLTIP_TOKENS = ("MEM-", "v3.", "_", "()")


class TestEveryColumnIsDocumented:

    def test_all_eleven_headers_carry_a_tooltip(self, panel):
        tips = panel.header_tooltips()
        assert len(tips) == 11
        assert all(t.strip() for t in tips), tips

    def test_the_control_reproduces_zero_of_eleven(self, monkeypatch):
        """The measured BEFORE: not one header carried a tooltip."""
        _without_the_header_tooltips(monkeypatch)
        built = _make_panel(_tao_tranches(), monkeypatch, _current_holdings=0.1)
        try:
            assert not any(t.strip() for t in built.header_tooltips())
        finally:
            _destroy(built)

    def test_the_tooltips_match_the_columns_they_document(self, panel):
        from src.gui.bot_live_settings import FOLD_COLUMN_TOOLTIPS

        assert len(FOLD_COLUMN_TOOLTIPS) == panel.table.columnCount()
        assert panel.header_tooltips() == list(FOLD_COLUMN_TOOLTIPS)

    def test_every_tooltip_this_unit_wrote_meets_the_standard(self):
        from src.gui.bot_live_settings import (
            FOLD_CLOSE_RATIO_TOOLTIP,
            FOLD_CLOSED_TOOLTIP,
            FOLD_COLUMN_TOOLTIPS,
            FOLD_CYCLE_CAP_TOOLTIP,
            FOLD_DISCARDED_TOOLTIP,
            FOLD_FILTER_TOOLTIP,
            FOLD_MALFORMED_TOOLTIP,
            FOLD_OLDEST_AGE_TOOLTIP,
            FOLD_OPEN_COUNT_TOOLTIP,
            FOLD_OPENED_TOOLTIP,
            FOLD_PARKED_USD_TOOLTIP,
            FOLD_SORT_TOOLTIP,
            FOLD_UNITS_MARKED_TOOLTIP,
            FOLD_WIRE_DISCARDED_TOOLTIP,
        )

        written = list(FOLD_COLUMN_TOOLTIPS) + [
            FOLD_OPEN_COUNT_TOOLTIP,
            FOLD_PARKED_USD_TOOLTIP,
            FOLD_OLDEST_AGE_TOOLTIP,
            FOLD_UNITS_MARKED_TOOLTIP,
            FOLD_WIRE_DISCARDED_TOOLTIP,
            FOLD_MALFORMED_TOOLTIP,
            FOLD_CYCLE_CAP_TOOLTIP,
            FOLD_SORT_TOOLTIP,
            FOLD_FILTER_TOOLTIP,
            FOLD_OPENED_TOOLTIP,
            FOLD_CLOSED_TOOLTIP,
            FOLD_CLOSE_RATIO_TOOLTIP,
            FOLD_DISCARDED_TOOLTIP,
        ]
        for tip in written:
            assert "\n" not in tip, tip
            assert len(tip.split()) <= TOOLTIP_WORD_LIMIT, tip
            assert tip.endswith("."), tip
            for token in BANNED_TOOLTIP_TOKENS:
                assert token not in tip, (token, tip)

    def test_the_word_limit_can_fail(self):
        """The check above is worthless if the limit admits anything."""
        long_tip = " ".join(["word"] * (TOOLTIP_WORD_LIMIT + 1))
        assert len(long_tip.split()) > TOOLTIP_WORD_LIMIT


class TestTheSummaryRowsAreDocumented:

    #: The rows this unit owns. Both halves of each must carry the tip.
    OWNED = (
        "Open tranches:",
        "Parked USD (in fold queue):",
        "Oldest tranche age:",
        "Units marked (queue vs held):",
        "Tranches dropped as malformed:",
        "Fold budget this cycle:",
    )

    COUNTERS = (
        "Lifetime tranches opened:",
        "Lifetime tranches closed (fold-back fired):",
        "Cycle close ratio (folded / opened minus discarded):",
    )

    def test_both_halves_of_every_owned_row_carry_the_tooltip(self, panel):
        for label in self.OWNED:
            row = panel.row_labelled(label)
            assert row is not None, label
            _, _, label_tip, value_tip = row
            assert label_tip.strip(), label
            assert label_tip == value_tip, label

    def test_the_counter_rows_took_the_handoff(self, panel) -> None:
        """Both halves of every row in `COUNTERS` carry the same tooltip."""
        for label in self.COUNTERS:
            row = panel.row_labelled(label)
            assert row is not None, label
            _, _, label_tip, value_tip = row
            assert label_tip.strip(), label
            assert label_tip == value_tip, label

    DISCARDED_ROW = "Lifetime tranches discarded (not folded back):"

    def test_the_discard_row_carries_the_tooltip_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`DISCARDED_ROW` appears only once the bot has discarded something.

        A clear, the despawn sweep, a detonation and the unreadable-record drop
        all write the one counter this row reads.
        """
        built = _make_panel(
            [_tranche(0, age_days=1.0)],
            monkeypatch,
            _current_holdings=1.0,
            _tranches_discarded_lifetime=7,
        )
        try:
            row = built.row_labelled(self.DISCARDED_ROW)
            assert row is not None
            assert row[1] == "7"
            assert row[2].strip()
            assert row[2] == row[3]
        finally:
            _destroy(built)

    def test_a_bot_that_has_discarded_nothing_stays_quiet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The row's own convention, unchanged by this unit."""
        built = _make_panel(
            [_tranche(0, age_days=1.0)],
            monkeypatch,
            _current_holdings=1.0,
            _tranches_discarded_lifetime=0,
        )
        try:
            assert built.row_labelled(self.DISCARDED_ROW) is None
        finally:
            _destroy(built)

    def test_the_despawn_rows_gained_their_label_half(self, panel):
        """The label half of each despawn row carries the value half's tooltip."""
        for label in ("Tranche despawn timer:", "Despawn would remove:"):
            row = panel.row_labelled(label)
            assert row is not None, label
            assert row[2].strip(), label
            assert row[2] == row[3], label


PUMP_MARKED, PUMP_HELD, PUMP_RATIO = 19870.72, 9987.78, "1.99x"
CAP_MARKED, CAP_HELD, CAP_RATIO = 1075.61, 800.42, "1.34x"
ZEC_MARKED, ZEC_HELD, ZEC_RATIO = 0.1598, 0.1762, "0.91x"


class TestTheAllotmentTotal:

    def _row(self, marked, held):
        from src.gui.bot_live_settings import compose_units_marked_row

        return compose_units_marked_row([{"units": marked}], held)

    def test_pump_reads_as_the_evaluation_measured_it(self):
        from src.gui.bot_live_settings import FOLD_OVER_ALLOTMENT_FG_HEX

        text, colour = self._row(PUMP_MARKED, PUMP_HELD)
        assert PUMP_RATIO in text
        assert colour == FOLD_OVER_ALLOTMENT_FG_HEX

    def test_cap_reads_as_the_evaluation_measured_it(self):
        text, colour = self._row(CAP_MARKED, CAP_HELD)
        assert CAP_RATIO in text
        assert colour is not None

    def test_a_healthy_bot_gets_no_colour(self):
        """THE OTHER SIDE. The red is a verdict about the ledger, not a
        decoration every row wears."""
        text, colour = self._row(ZEC_MARKED, ZEC_HELD)
        assert ZEC_RATIO in text
        assert colour is None

    def test_exactly_one_to_one_is_not_over(self):
        """The threshold is not a taste: above 1.00x the queue claims
        more asset than the bot owns. At 1.00x it does not."""
        _, colour = self._row(5.0, 5.0)
        assert colour is None
        _, over = self._row(5.000001, 5.0)
        assert over is not None

    def test_an_unreadable_unit_is_counted_and_never_added_as_zero(self):
        from src.gui.bot_live_settings import compose_units_marked_row

        text, _ = compose_units_marked_row(
            [{"units": 2.0}, {"units": float("nan")}, {"units": 3.0}], 10.0
        )
        assert "5.000000 marked" in text
        assert "+1 unreadable" in text

    def test_no_ratio_is_printed_against_holdings_it_cannot_read(self):
        from src.gui.bot_live_settings import compose_units_marked_row

        for holdings in (None, float("nan"), float("inf"), True, "9"):
            text, colour = compose_units_marked_row([{"units": 1.0}], holdings)
            assert "x)" not in text, holdings
            assert colour is None, holdings

    def test_zero_holdings_is_stated_and_not_divided_by(self):
        text, colour = self._row(1.0, 0.0)
        assert "0.000000 held" in text
        assert "x)" not in text
        assert colour is None

    def test_the_row_is_on_the_panel_and_carries_the_colour(self, monkeypatch):
        from src.gui.bot_live_settings import FOLD_OVER_ALLOTMENT_FG_HEX

        built = _make_panel(
            [_tranche(0, age_days=1.0, units=PUMP_MARKED)],
            monkeypatch,
            _current_holdings=PUMP_HELD,
        )
        try:
            row = built.row_labelled("Units marked (queue vs held):")
            assert row is not None
            assert PUMP_RATIO in row[1]
            painted = _painted_colours(built.dialog._fold_units_marked_lbl)
            assert FOLD_OVER_ALLOTMENT_FG_HEX in painted
        finally:
            _destroy(built)

    def test_a_healthy_panel_paints_no_warning(self, monkeypatch):
        """THE OTHER SIDE, off the same render. Without this the check
        above would pass on a panel that painted the warning on every
        row, which is a decoration and not a verdict."""
        from src.gui.bot_live_settings import FOLD_OVER_ALLOTMENT_FG_HEX

        built = _make_panel(
            [_tranche(0, age_days=1.0, units=ZEC_MARKED)],
            monkeypatch,
            _current_holdings=ZEC_HELD,
        )
        try:
            painted = _painted_colours(built.dialog._fold_units_marked_lbl)
            assert FOLD_OVER_ALLOTMENT_FG_HEX not in painted
            assert len(painted) > 1, (
                "an all-one-colour render means the label never "
                "painted its text and the check above cannot fail"
            )
        finally:
            _destroy(built)


BTC_WIRE_DISCARDED = 343.68244206
ETH_WIRE_DISCARDED = 213.90


class TestThePersistedQuantities:

    WIRE_ROW = "Lifetime wire credits discarded (cleared):"
    MALFORMED_ROW = "Tranches dropped as malformed:"
    BUDGET_ROW = "Fold budget this cycle:"

    def test_the_wire_discard_appears_once_it_is_non_zero(self, monkeypatch):
        built = _make_panel(
            [_tranche(0, age_days=1.0)],
            monkeypatch,
            _current_holdings=1.0,
            _wire_credits_discarded_lifetime=BTC_WIRE_DISCARDED,
        )
        try:
            row = built.row_labelled(self.WIRE_ROW)
            assert row is not None
            assert row[1] == "$343.6824"
        finally:
            _destroy(built)

    def test_a_bot_that_has_never_cleared_stays_quiet(self, monkeypatch):
        """THE OTHER SIDE, and it is the tranche-discard row's own
        convention. A row that appeared at zero would prove nothing
        about reading the field."""
        built = _make_panel(
            [_tranche(0, age_days=1.0)],
            monkeypatch,
            _current_holdings=1.0,
            _wire_credits_discarded_lifetime=0.0,
        )
        try:
            assert built.row_labelled(self.WIRE_ROW) is None
        finally:
            _destroy(built)

    def test_the_eth_figure_reads_the_same_way(self, monkeypatch):
        built = _make_panel(
            [_tranche(0, age_days=1.0)],
            monkeypatch,
            _current_holdings=1.0,
            _wire_credits_discarded_lifetime=ETH_WIRE_DISCARDED,
        )
        try:
            assert built.row_labelled(self.WIRE_ROW)[1] == "$213.9000"
        finally:
            _destroy(built)

    def test_malformed_is_shown_even_at_zero(self, panel):
        """0 on all 38 bots is a POSITIVE statement — no stored tranche
        was ever unreadable. Hiding it would make that reading
        indistinguishable from a panel that does not count drops."""
        row = panel.row_labelled(self.MALFORMED_ROW)
        assert row is not None
        assert row[1] == "0"

    def test_a_non_zero_malformed_count_is_marked(self, monkeypatch):
        from src.gui.bot_live_settings import FOLD_OVER_ALLOTMENT_FG_HEX
        from PySide6.QtWidgets import QLabel

        built = _make_panel(
            [_tranche(0, age_days=1.0)],
            monkeypatch,
            _current_holdings=1.0,
            _tranches_malformed_dropped=4,
        )
        try:
            row = built.row_labelled(self.MALFORMED_ROW)
            assert row[1] == "4"
            marked = [
                w
                for w in built.dialog._fold_tab_page.findChildren(QLabel)
                if w.text() == "4"
            ]
            assert marked
            assert any(
                FOLD_OVER_ALLOTMENT_FG_HEX in _painted_colours(w) for w in marked
            )
        finally:
            _destroy(built)

    def test_a_zero_malformed_count_is_not_marked(self, monkeypatch):
        """The other side. A zero is a correct, quiet state and marking
        it would teach the operator to ignore the row."""
        from src.gui.bot_live_settings import FOLD_OVER_ALLOTMENT_FG_HEX
        from PySide6.QtWidgets import QLabel

        built = _make_panel(
            [_tranche(0, age_days=1.0)],
            monkeypatch,
            _current_holdings=1.0,
            _tranches_malformed_dropped=0,
        )
        try:
            quiet = [
                w
                for w in built.dialog._fold_tab_page.findChildren(QLabel)
                if w.text() == "0"
            ]
            assert quiet
            assert all(
                FOLD_OVER_ALLOTMENT_FG_HEX not in _painted_colours(w) for w in quiet
            )
        finally:
            _destroy(built)

    def test_the_cycle_budget_names_both_halves(self, monkeypatch):
        """Consumed alone is half a number: it decides how much of the
        queue one cycle may take, so it is printed against the budget it
        is spent from."""
        built = _make_panel(
            [_tranche(0, age_days=1.0)],
            monkeypatch,
            _current_holdings=1.0,
            _fold_cycle_cap_consumed=1.25,
        )
        try:
            row = built.row_labelled(self.BUDGET_ROW)
            assert row is not None
            assert row[1].startswith("$1.2500 spent of $")
        finally:
            _destroy(built)

    def test_all_three_survive_a_real_export_and_import(self):
        """NO INVENTED FIELD. Each name this unit reads is written by
        `export_scrumming_state` and read back by
        `import_scrumming_state`, so the panel is showing a quantity the
        bot really persists rather than one it happens to hold in
        memory until the next launch.

        A FRESH BOT DOES NOT CARRY TWO OF THEM.
        `_wire_credits_discarded_lifetime` and
        `_tranches_malformed_dropped` are set by the restore and by
        their write sites, not by `__init__` - measured here, which is
        why the panel reads all three through `getattr` with a default
        and shows the wire row only once it is non-zero.
        """
        from src.trading.bot_container import BotMode, make_bot_config
        from src.trading.scrumming_bot import ScrummingBot

        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="test",
            base_currency="USD",
            target_asset="BTC",
            target_balance=100.0,
        )
        source = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
        source._wire_credits_discarded_lifetime = BTC_WIRE_DISCARDED
        source._tranches_malformed_dropped = 4
        source._fold_cycle_cap_consumed = 1.25

        state = source.export_scrumming_state()
        assert state["wire_credits_discarded_lifetime"] == BTC_WIRE_DISCARDED
        assert state["tranches_malformed_dropped"] == 4
        assert state["fold_cycle_cap_consumed"] == 1.25

        target = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
        target.import_scrumming_state(state)
        assert target._wire_credits_discarded_lifetime == BTC_WIRE_DISCARDED
        assert target._tranches_malformed_dropped == 4
        assert target._fold_cycle_cap_consumed == 1.25

    def test_a_fresh_bot_carries_neither_lifetime_attribute(self):
        """The reason the panel uses `getattr` with a default. If this
        starts failing the defaults are dead code and can go."""
        from src.trading.bot_container import BotMode, make_bot_config
        from src.trading.scrumming_bot import ScrummingBot

        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="test",
            base_currency="USD",
            target_asset="BTC",
            target_balance=100.0,
        )
        bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
        assert not hasattr(bot, "_wire_credits_discarded_lifetime")
        assert hasattr(bot, "_tranches_malformed_dropped")
        assert hasattr(bot, "_fold_cycle_cap_consumed")
        assert hasattr(bot, "_current_holdings")
