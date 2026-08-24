"""The operator can SEE the clear — issue #98 defects 1, 2 and 3.

WHAT WAS MEASURED, AND WHY IT IS NOT A BROKEN BUTTON
====================================================
Both Clear buttons on the Fold Tranches tab already worked. The trade
log records them on BTC bot ``7c39c7a2`` — ``WIRE CREDITS CLEARED ...
$343.6824`` and ``FOLD TRANCHES CLEARED ... 42 tranche(s) holding
$29.4268`` — and the state file agrees. Nothing here makes them clear
harder.

What the operator SAW was a panel that had not moved. Driven offscreen
against a stub bot, with the confirmation accepted::

    BEFORE  table rows 58   bot tranches 58   "Open tranches: 58"
    AFTER   table rows 58   bot tranches  0   "Open tranches: 58"
            clear button still "Clear 58 Fold Tranche(s)", enabled True
            58 Fire buttons still live

The dialog built its tabs once in ``__init__`` and had no refresh path,
so the handler printed a disclaimer instead — and the disclaimer opened
with "No order was placed", which is REASSURANCE standing where a
RESULT belongs, after a button that appeared to have done nothing.

Neither clear reached disk. ``clear_fold_tranches`` and
``clear_pending_wire_credits`` both write memory only
(``scrumming_bot.py:13273`` and ``:13350``) and leave the write to the
60-second rolling save at ``main.py:1343``. Clear, then close inside
that window, and every record the operator destroyed came back.

WHAT THIS FILE PROVES
=====================
1. The panel is rebuilt: rows, count label, both button labels and both
   button enabled states all follow the bot, and every Fire button is
   gone.
2. The message names the RESULT first and the reassurance last.
3. The clear is on DISK before the handler returns — asserted by
   reading the state file back, not by asserting that a timer exists.
4. A stale Fire button was already safe, and it is now unreachable.

EVERY ASSERTION DRIVES SHIPPED CODE. A real ``ScrummingBot``, its real
``clear_fold_tranches``, a real ``BotManager``, a real ``StateManager``
pointed at ``tmp_path``, and the real
``BotLiveSettingsDialog._on_clear_fold_tranches`` bound to a real
dialog holding a real ``QTabWidget``. Nothing here re-implements a line
of the panel.

NOTHING WRITES UNDER ``~/.acervator``. The ``StateManager`` is
constructed with ``config_dir=tmp_path``, so the operator's live state
file is never opened, let alone written. No Clear or Fire button is
pressed anywhere but on this fixture.

TWO-SIDED BY CONSTRUCTION
=========================
``_without_the_refresh`` and ``_without_the_in_click_save`` put the
tree back the way it was and reproduce the measured BEFORE numbers on
demand. A repair test that cannot reproduce the defect is a test that
proves nothing about the repair.

FALSIFICATION: this file is wrong if (a) the panel agrees with the bot
while the refresh is disabled, (b) the state file holds zero tranches
while the in-click save is disabled, or (c) the "result first" test
passes on a message that opens with "No order was placed".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: The evaluation's own fixture size, so the numbers this file prints
#: are the numbers the issue reports.
TRANCHE_COUNT = 58

#: The parked credit the live BTC bot carried when the issue was filed.
PARKED_USD = 343.6824

#: Frozen enough for the age column; the tab reads the wall clock.
NOW = 1_800_000_000.0

COL_SOURCE = 8
COL_FIRE = 9


def _qt_or_skip():
    pytest.importorskip("PySide6.QtWidgets")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class _Exchange:
    """The one attribute ``ScrummingBot.__init__`` reads off it."""

    exchange_id = "test"


def _tranches(n: int) -> list[dict]:
    """``n`` fold tranches, priced so the row builder renders every
    cell rather than falling to its em dash."""
    return [
        {"usd": 1.0 + i, "units": 0.001 * (i + 1), "ref": 30000.0 + i,
         "initial_buy_price": 29000.0 + i, "created_ts": NOW - 3600.0 - i}
        for i in range(n)
    ]


class _Panel:
    """The fixture, kept as an object so Qt does not collect it."""

    def __init__(self, bot, manager, state_manager, dialog, tabs):
        self.bot = bot
        self.manager = manager
        self.state_manager = state_manager
        self.dialog = dialog
        self.tabs = tabs

    # -- what the operator's eye can reach -------------------------- #
    def shows(self) -> dict:
        return self.dialog._fold_panel_shows()

    def fire_buttons(self) -> list:
        from PySide6.QtWidgets import QPushButton
        page = self.dialog._fold_tab_page
        return [b for b in page.findChildren(QPushButton)
                if b.text() == "Fire"]

    def saved_tranches(self) -> int | None:
        """How many fold tranches the STATE FILE holds for this bot.

        ``None`` when no file exists yet, which is what an unsaved
        clear leaves behind and is a different answer from zero.
        """
        path = self.state_manager._path
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        record = data.get("bots", {}).get(self.bot.bot_id, {})
        return len(record.get("scrumming_state", {}).get(
            "fold_tranches", []))

    def saved_wire_credits(self) -> float | None:
        path = self.state_manager._path
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        record = data.get("bots", {}).get(self.bot.bot_id, {})
        return record.get("scrumming_state", {}).get(
            "pending_wire_credits")


class _Messages:
    """Every dialog the handler raised, in order."""

    def __init__(self):
        self.seen: list[dict] = []

    def of(self, kind: str) -> dict | None:
        for event in self.seen:
            if event["kind"] == kind:
                return event
        return None

    @property
    def result(self) -> str:
        found = self.of("information")
        assert found is not None, (
            f"the handler raised no result dialog; it raised "
            f"{[e['kind'] for e in self.seen]}")
        return found["text"]


def _patch_message_box(monkeypatch, answer_yes: bool = True) -> _Messages:
    """Answer both confirmations and record every message.

    The handlers import ``QMessageBox`` from ``PySide6.QtWidgets``
    inside the function body, so the module attribute is the binding
    they resolve and the one worth replacing.
    """
    import PySide6.QtWidgets as _QtWidgets

    log = _Messages()

    class _Box:
        Yes = 0x4000
        Cancel = 0x400000
        Warning = 2
        No = 0x10000

        def __init__(self, *_a, **_k):
            self._title = ""
            self._text = ""

        def setIcon(self, *_a, **_k):
            pass

        def setWindowTitle(self, title):
            self._title = title

        def setText(self, text):
            self._text = text

        def setStandardButtons(self, *_a, **_k):
            pass

        def setDefaultButton(self, *_a, **_k):
            pass

        def exec(self):
            log.seen.append({"kind": "confirm", "title": self._title,
                             "text": self._text})
            return _Box.Yes if answer_yes else _Box.Cancel

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


@pytest.fixture
def panel(tmp_path):
    """A real bot, a real manager, a real state file, a real dialog."""
    _qt_or_skip()
    from PySide6.QtWidgets import QDialog, QTabWidget

    from src.core.event_bus import EventBus
    from src.core.state_manager import StateManager
    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.trading.bot_container import BotManager, BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    cfg = make_bot_config(
        BotMode.SCRUMMING, exchange_id="test", base_currency="USD",
        target_asset="BTC", target_balance=100.0)
    bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
    bot._fold_tranches = _tranches(TRANCHE_COUNT)
    bot._pending_wire_credits = PARKED_USD
    bot._pending_wire_ledger = [{"usd": PARKED_USD, "from": "seed"}]
    bot._tranches_created_lifetime = TRANCHE_COUNT
    bot._tranches_closed_lifetime = 0

    manager = BotManager(bus=EventBus())
    manager._bots[bot.bot_id] = bot
    state_manager = StateManager(config_dir=tmp_path)
    manager.set_state_manager(state_manager)
    bot._bot_manager = manager

    dialog = BotLiveSettingsDialog.__new__(BotLiveSettingsDialog)
    QDialog.__init__(dialog)
    dialog._bot = bot
    dialog._bm = manager
    dialog._changes = {}
    tabs = QTabWidget()
    dialog._tabs = tabs
    # A sibling on each side, so a rebuild that renumbered the tab bar
    # would be visible rather than invisible at index 0.
    from PySide6.QtWidgets import QWidget
    tabs.addTab(QWidget(), "Status")
    dialog._install_fold_tranches_tab(tabs)
    tabs.addTab(QWidget(), "Bot Swarm")

    # YIELD so every object above stays referenced for the whole test.
    yield _Panel(bot, manager, state_manager, dialog, tabs)


# ══════════════════════════════════════════════════════════════════════
# THE CONTROLS. Each one puts the tree back and must reproduce the
# measured BEFORE numbers.
# ══════════════════════════════════════════════════════════════════════
def _without_the_refresh(monkeypatch) -> None:
    """Restore the pre-repair behaviour: no refresh path at all.

    The name is asserted to exist and to be callable FIRST.
    ``monkeypatch.setattr`` raises on a name that has been renamed
    away, but a control that quietly patches nothing would report the
    repair's own numbers and call them the defect's.
    """
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    assert callable(BotLiveSettingsDialog._refresh_fold_tranches_tab)
    monkeypatch.setattr(
        BotLiveSettingsDialog, "_refresh_fold_tranches_tab",
        lambda self: "not refreshed: control disabled the rebuild")


def _without_the_in_click_save(monkeypatch) -> None:
    """Restore the pre-repair behaviour: no save inside the click."""
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    assert callable(BotLiveSettingsDialog._save_fleet_state_now)
    monkeypatch.setattr(
        BotLiveSettingsDialog, "_save_fleet_state_now",
        lambda self, _what: (False, "control disabled the in-click save"))


# ══════════════════════════════════════════════════════════════════════
# A. THE STARTING STATE. Without these the "after" numbers below could
#    be produced by a panel that never showed anything.
# ══════════════════════════════════════════════════════════════════════
def test_the_panel_starts_by_showing_all_58(panel):
    shows = panel.shows()
    assert shows["fold_rows"] == TRANCHE_COUNT
    assert shows["open_tranches_label"] == str(TRANCHE_COUNT)
    assert shows["clear_button_text"] == (
        f"Clear {TRANCHE_COUNT} Fold Tranche(s)")
    assert shows["clear_button_enabled"] is True
    assert shows["wire_button_enabled"] is True
    assert len(panel.fire_buttons()) == TRANCHE_COUNT
    assert len(panel.bot._fold_tranches) == TRANCHE_COUNT


# ══════════════════════════════════════════════════════════════════════
# B. DEFECT 1 — THE PANEL REFRESHES. The evaluation's measurement is
#    the falsifier: each of its four stale readings gets its own test.
# ══════════════════════════════════════════════════════════════════════
class TestThePanelFollowsTheClear:

    def test_the_bot_holds_nothing(self, panel, monkeypatch):
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert panel.bot._fold_tranches == []

    def test_the_table_shows_no_rows(self, panel, monkeypatch):
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert panel.shows()["fold_rows"] == 0

    def test_the_count_label_reads_zero(self, panel, monkeypatch):
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert panel.shows()["open_tranches_label"] == "0"

    def test_the_clear_button_is_disabled_and_renamed(
            self, panel, monkeypatch):
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        shows = panel.shows()
        assert shows["clear_button_enabled"] is False
        assert shows["clear_button_text"] == "Clear Fold Tranches"

    def test_every_fire_button_is_gone(self, panel, monkeypatch):
        """58 live Fire buttons over an empty queue was the reading
        that made the panel dangerous to read, not dangerous to use."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert panel.fire_buttons() == []

    def test_the_tab_keeps_its_place_and_its_name(self, panel,
                                                  monkeypatch):
        """`removeTab` + `insertTab` at the same index, so the sibling
        tabs do not renumber under the operator."""
        _patch_message_box(monkeypatch)
        before = [panel.tabs.tabText(i)
                  for i in range(panel.tabs.count())]
        panel.dialog._on_clear_fold_tranches()
        after = [panel.tabs.tabText(i)
                 for i in range(panel.tabs.count())]
        assert before == after == ["Status", "Fold Tranches", "Bot Swarm"]
        assert panel.tabs.indexOf(panel.dialog._fold_tab_page) == 1

    def test_the_wire_clear_moves_its_own_two_readings(
            self, panel, monkeypatch):
        """The sibling button, which had the same hole."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_wire_credits()
        assert panel.bot._pending_wire_credits == 0.0
        assert panel.shows()["wire_button_enabled"] is False

    # -- the control ------------------------------------------------ #
    def test_without_the_refresh_the_measured_defect_returns(
            self, panel, monkeypatch):
        """Reproduce the evaluation's AFTER row, exactly.

        If this ever goes green in the repaired tree, the tests above
        are measuring something other than the refresh.
        """
        _patch_message_box(monkeypatch)
        _without_the_refresh(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        shows = panel.shows()
        assert panel.bot._fold_tranches == []
        assert shows["fold_rows"] == TRANCHE_COUNT
        assert shows["open_tranches_label"] == str(TRANCHE_COUNT)
        assert shows["clear_button_text"] == (
            f"Clear {TRANCHE_COUNT} Fold Tranche(s)")
        assert shows["clear_button_enabled"] is True
        assert len(panel.fire_buttons()) == TRANCHE_COUNT


# ══════════════════════════════════════════════════════════════════════
# C. DEFECT 2 — THE MESSAGE NAMES THE RESULT FIRST.
# ══════════════════════════════════════════════════════════════════════
class TestTheMessageLeadsWithTheResult:

    def test_the_first_line_is_what_happened(self, panel, monkeypatch):
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        first = log.result.split("\n")[0]
        assert first.startswith(f"Cleared {TRANCHE_COUNT} fold tranche(s)")
        assert "No order was placed" not in first

    def test_the_reassurance_comes_last(self, panel, monkeypatch):
        """'No order was placed' is true and worth saying. It is
        reassurance, so it stands after the result, not on top of it."""
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        text = log.result
        assert "No order was placed" in text
        assert text.index("Cleared") < text.index("No order was placed")

    def test_the_message_states_what_the_bot_now_holds(
            self, panel, monkeypatch):
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert "This bot now holds 0 open fold tranche(s)." in log.result

    def test_the_message_says_the_panel_was_rebuilt(
            self, panel, monkeypatch):
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert "has been rebuilt" in log.result
        assert "reopen it to see the new state" not in log.result

    def test_the_message_says_it_reached_disk(self, panel, monkeypatch):
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert "Saved to disk." in log.result

    def test_the_wire_message_leads_with_its_own_result(
            self, panel, monkeypatch):
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_wire_credits()
        first = log.result.split("\n")[0]
        assert first.startswith("Cleared $343.6824 of parked")
        assert "No funds moved" not in first
        assert "No funds moved" in log.result

    # -- the controls ----------------------------------------------- #
    def test_a_failed_refresh_is_named_not_hidden(self, panel,
                                                  monkeypatch):
        log = _patch_message_box(monkeypatch)
        _without_the_refresh(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert "control disabled the rebuild" in log.result
        assert "Close and reopen this dialog" in log.result
        assert "has been rebuilt" not in log.result

    def test_a_failed_save_is_named_not_hidden(self, panel, monkeypatch):
        log = _patch_message_box(monkeypatch)
        _without_the_in_click_save(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert "NOT SAVED TO DISK" in log.result
        assert "control disabled the in-click save" in log.result

    def test_a_cancelled_clear_reports_nothing_and_changes_nothing(
            self, panel, monkeypatch):
        """The negative control for the whole class: a guard that
        cleared on Cancel would pass every test above."""
        log = _patch_message_box(monkeypatch, answer_yes=False)
        panel.dialog._on_clear_fold_tranches()
        assert log.of("information") is None
        assert len(panel.bot._fold_tranches) == TRANCHE_COUNT
        assert panel.shows()["fold_rows"] == TRANCHE_COUNT
        assert panel.saved_tranches() is None


# ══════════════════════════════════════════════════════════════════════
# D. DEFECT 3 — THE CLEAR SURVIVES AN IMMEDIATE CLOSE.
#    Read off the state FILE. "A timer would have fired" is not a
#    measurement of anything.
# ══════════════════════════════════════════════════════════════════════
class TestTheClearIsOnDiskBeforeTheHandlerReturns:

    def test_no_state_file_exists_before_the_click(self, panel):
        """Positive control for the file read below: the assertions
        after the clear would pass on a file that was already there."""
        assert panel.saved_tranches() is None

    def test_the_file_reader_can_tell_58_from_0(self, panel):
        """POSITIVE CONTROL for every file assertion in this class.

        `saved_tranches` returns `len(...)` over a key that may simply
        be absent, so a reader that found nothing at all would answer
        0 and every "the clear reached disk" test would pass over a
        file that recorded nothing. Save the fixture UNCLEARED first
        and the same reader must answer 58.
        """
        panel.manager.save_all_state()
        assert panel.saved_tranches() == TRANCHE_COUNT
        assert panel.saved_wire_credits() == pytest.approx(PARKED_USD)

    def test_the_state_file_holds_zero_tranches(self, panel, monkeypatch):
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert panel.saved_tranches() == 0

    def test_the_state_file_holds_zero_wire_credits(self, panel,
                                                    monkeypatch):
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_wire_credits()
        assert panel.saved_wire_credits() == 0.0

    def test_the_bot_method_itself_still_saves_nothing(self, panel):
        """WHERE THE REPAIR IS, STATED AS A TEST.

        `scrumming_bot.py` is untouched by this unit: its clear is
        still a memory write and still leaves persistence to its
        caller. That is what makes the caller-side save the repair
        rather than a duplicate of one.
        """
        panel.bot.clear_fold_tranches(reason="test")
        assert panel.bot._fold_tranches == []
        assert panel.saved_tranches() is None

    # -- the control ------------------------------------------------ #
    def test_without_the_in_click_save_the_clear_never_reaches_disk(
            self, panel, monkeypatch):
        _patch_message_box(monkeypatch)
        _without_the_in_click_save(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert panel.bot._fold_tranches == []
        assert panel.saved_tranches() is None


# ══════════════════════════════════════════════════════════════════════
# E2. THE PIN CARRIES THE PREDICTION.
#     An island proof is a HYPOTHESIS. `gui.04.002` ships the expected
#     result beside the observed one, so the operator's own machine
#     answers it instead of this file standing in for it.
# ══════════════════════════════════════════════════════════════════════
@pytest.fixture
def sink():
    """Install a signal sink for one test and take it out again."""
    from src.core import signal_contract as sc

    previous = sc.get_sink()
    fresh = sc.SignalSink()
    sc.set_sink(fresh)
    try:
        yield fresh
    finally:
        sc.set_sink(previous)


PIN = "gui.04.002.postcondition.clear_settled"


class TestThePinCarriesThePrediction:

    def test_the_pin_fires_once_per_clear_and_is_green(
            self, panel, sink, monkeypatch):
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        records = sink.records(PIN)
        assert len(records) == 1
        assert records[0].ok is True
        assert records[0].context["refresh"] == "refreshed"
        assert records[0].context["cleared"] == "Clear fold tranches"

    def test_the_pin_measures_the_cost_it_declares(self, panel, sink,
                                                   monkeypatch):
        """The registry row declares `measured: the in-click save and
        the tab rebuild`. A postcondition that declares a duration and
        passes none is E11; a duration of None here would mean the
        bracket is gone."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        duration = sink.records(PIN)[0].duration
        assert duration is not None
        assert duration >= 0.0

    def test_the_pin_goes_RED_on_a_stale_panel(self, panel, sink,
                                               monkeypatch):
        """THE CONTROL. A pin whose verdict cannot vary is evidence of
        nothing, so the defect is reproduced and read back off the
        record."""
        _patch_message_box(monkeypatch)
        _without_the_refresh(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        record = sink.records(PIN)[0]
        assert record.ok is False
        assert record.actual["fold_rows"] == TRANCHE_COUNT
        assert record.expected["fold_rows"] == 0

    def test_the_pin_goes_RED_on_an_unsaved_clear(self, panel, sink,
                                                  monkeypatch):
        _patch_message_box(monkeypatch)
        _without_the_in_click_save(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        record = sink.records(PIN)[0]
        assert record.ok is False
        assert record.actual["saved"] is False
        assert record.expected["saved"] is True


# ══════════════════════════════════════════════════════════════════════
# E. FIRE AFTER A CLEAR. The issue says it is safe. Verified rather
#    than repeated, because it decides how urgent the button state is.
# ══════════════════════════════════════════════════════════════════════
class TestFiringAfterAClear:

    def test_a_stale_fire_refuses_and_places_no_order(self, panel,
                                                      monkeypatch):
        """The pre-repair safety claim, driven.

        The Fire button captures its tranche by IDENTITY and resolves
        the index at click time. `clear_fold_tranches` assigns a NEW
        empty list, so `list.index` finds nothing and the handler
        refuses before it reaches `manual_fire_tranche`.
        """
        stale = panel.bot._fold_tranches[0]
        fired: list = []
        monkeypatch.setattr(
            type(panel.bot), "manual_fire_tranche",
            lambda self, idx: fired.append(idx), raising=False)
        log = _patch_message_box(monkeypatch)
        _without_the_refresh(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert len(panel.fire_buttons()) == TRANCHE_COUNT

        log.seen.clear()
        panel.dialog._on_fire_tranche_clicked(stale)
        refusal = log.of("warning")
        assert refusal is not None, "the stale fire raised no refusal"
        assert "no longer in the fold queue" in refusal["text"]
        assert fired == [], "a stale Fire reached the order path"

    def test_the_repair_removes_the_button_rather_than_relying_on_that(
            self, panel, monkeypatch):
        """Safe is not the same as honest. The refusal above is the
        floor; the refresh is what stops the operator meeting it."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_fold_tranches()
        assert panel.fire_buttons() == []
