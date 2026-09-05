"""The operator can reset the lifetime tranche counters from the Fold Tranches tab.

``BotLiveSettingsDialog._on_clear_lifetime_counters`` drives
``ScrummingBot.clear_lifetime_tranche_counters``, which zeroes the four stored
counters, the ``stats`` mirror of the discarded count, and stamps
``_tranches_counters_reset_ts``. The stamp keeps ``_tick_initialise`` from
re-adopting the exchange balance on a bot whose counters were cleared, while a bot
that genuinely never scrummed is left unstamped. Open tranches, parked USD, the
wire-credit ledger, the stack counters, holdings, lots and target are untouched.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

#: The live CHIP/USD bot's counters, so the assertions carry real magnitudes.
OPENED = 4925
CLOSED = 4813
DISCARDED = 91
#: Non-zero, so the clear has to move it.
MALFORMED = 4

#: Standing inventory the clear must not touch. Three tranches, a parked
#: credit, and a wire-credit discard total from an earlier clear.
OPEN_TRANCHES = 3
PARKED_USD = 17.3130
WIRE_DISCARDED = 17.31301271

#: Frozen enough for the age column; the tab reads the wall clock.
NOW = 1_800_000_000.0


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
    return [
        {
            "usd": 1.0 + i,
            "units": 0.001 * (i + 1),
            "ref": 30000.0 + i,
            "initial_buy_price": 29000.0 + i,
            "created_ts": NOW - 3600.0 - i,
        }
        for i in range(n)
    ]


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
            f"{[e['kind'] for e in self.seen]}"
        )
        return found["text"]

    @property
    def confirm(self) -> str:
        found = self.of("confirm")
        assert found is not None, "the handler asked for no confirmation"
        return found["text"]


def _patch_message_box(monkeypatch, answer_yes: bool = True) -> _Messages:
    """Answer the confirmation and record every message.

    The handler imports ``QMessageBox`` from ``PySide6.QtWidgets`` inside
    its own body, so the module attribute is the binding it resolves.
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
            log.seen.append(
                {"kind": "confirm", "title": self._title, "text": self._text}
            )
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

    monkeypatch.setattr(_QtWidgets, "QMessageBox", _Box)
    return log


class _Panel:
    """The fixture, kept as an object so Qt does not collect it."""

    def __init__(self, bot, manager, state_manager, dialog, tabs):
        self.bot = bot
        self.manager = manager
        self.state_manager = state_manager
        self.dialog = dialog
        self.tabs = tabs

    def shows(self) -> dict:
        return self.dialog._fold_panel_shows()

    def saved(self) -> dict | None:
        """The bot's ``scrumming_state`` and ``stats`` off the FILE.

        ``None`` when no file exists, which is what an unsaved clear
        leaves behind and is a different answer from a record of zeroes.
        """
        path = self.state_manager._path
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        record = data.get("bots", {}).get(self.bot.bot_id)
        if record is None:
            return None
        return {
            "scrumming_state": record.get("scrumming_state", {}),
            "stats": record.get("stats", {}),
        }

    def saved_counters(self) -> dict | None:
        """The four counters and the ``stats`` mirror, off the FILE."""
        found = self.saved()
        if found is None:
            return None
        scr = found["scrumming_state"]
        return {
            "opened": scr.get("tranches_created_lifetime"),
            "closed": scr.get("tranches_closed_lifetime"),
            "discarded": scr.get("tranches_discarded_lifetime"),
            "malformed": scr.get("tranches_malformed_dropped"),
            "stats_discarded": found["stats"].get("tranches_discarded_lifetime"),
            "reset_ts": scr.get("tranches_counters_reset_ts"),
        }


def _build(tmp_path, *, opened=OPENED, closed=CLOSED, discarded=DISCARDED):
    _qt_or_skip()
    from PySide6.QtWidgets import QDialog, QTabWidget, QWidget

    from src.core.event_bus import EventBus
    from src.core.state_manager import StateManager
    from src.gui.bot_live_settings import BotLiveSettingsDialog
    from src.trading.bot_container import BotManager, BotMode, make_bot_config
    from src.trading.scrumming_bot import ScrummingBot

    cfg = make_bot_config(
        BotMode.SCRUMMING,
        exchange_id="test",
        base_currency="USD",
        target_asset="CHIP",
        target_balance=100.0,
    )
    bot = ScrummingBot(cfg, _Exchange(), enable_phantoms=False)
    bot._fold_tranches = _tranches(OPEN_TRANCHES)
    bot._fold_queue_usd = sum(t["usd"] for t in bot._fold_tranches)
    bot._pending_wire_credits = PARKED_USD
    bot._pending_wire_ledger = [{"usd": PARKED_USD, "from": "seed"}]
    bot._wire_credits_discarded_lifetime = WIRE_DISCARDED
    bot._tranches_created_lifetime = opened
    bot._tranches_closed_lifetime = closed
    bot._tranches_discarded_lifetime = discarded
    bot._tranches_malformed_dropped = MALFORMED
    bot.stats.tranches_discarded_lifetime = discarded
    bot._stack_created = 7
    bot._stack_discarded = 2
    bot._main_lots = [{"units": 0.5, "initial_buy_price": 200.0}]
    bot._current_holdings = 0.5

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
    tabs.addTab(QWidget(), "Status")
    dialog._install_fold_tranches_tab(tabs)
    tabs.addTab(QWidget(), "Bot Swarm")
    return _Panel(bot, manager, state_manager, dialog, tabs)


def _destroy(panel) -> None:
    """Queue the delete, then deliver the event.

    ``processEvents()`` does not deliver ``DeferredDelete``, and a widget
    left alive here fails a stranger's test — ``_open_dialogs(app)``
    takes the first top-level ``QDialog`` in the process.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    for widget in (panel.tabs, panel.dialog):
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def panel(tmp_path):
    built = _build(tmp_path)
    yield built
    _destroy(built)


def _without_the_in_click_save(monkeypatch) -> None:
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    assert callable(BotLiveSettingsDialog._save_fleet_state_now)
    monkeypatch.setattr(
        BotLiveSettingsDialog,
        "_save_fleet_state_now",
        lambda self, _what: (False, "control disabled the in-click save"),
    )


def _without_the_refresh(monkeypatch) -> None:
    from src.gui.bot_live_settings import BotLiveSettingsDialog

    assert callable(BotLiveSettingsDialog._refresh_fold_tranches_tab)
    monkeypatch.setattr(
        BotLiveSettingsDialog,
        "_refresh_fold_tranches_tab",
        lambda self: "not refreshed: control disabled the rebuild",
    )


def _without_the_stats_mirror(monkeypatch) -> None:
    """Clear the four counters and leave ``stats`` alone.

    The shipped method with one line removed, so a green run against it
    means the mirror is not being asserted anywhere.
    """
    from src.trading.scrumming_bot import ScrummingBot

    assert callable(ScrummingBot.clear_lifetime_tranche_counters)

    def _no_mirror(self, reason: str = "operator") -> dict:
        before = {
            "created": int(getattr(self, "_tranches_created_lifetime", 0) or 0),
            "closed": int(getattr(self, "_tranches_closed_lifetime", 0) or 0),
            "discarded": int(getattr(self, "_tranches_discarded_lifetime", 0) or 0),
            "malformed": int(getattr(self, "_tranches_malformed_dropped", 0) or 0),
        }
        self._tranches_created_lifetime = 0
        self._tranches_closed_lifetime = 0
        self._tranches_discarded_lifetime = 0
        self._tranches_malformed_dropped = 0
        self._tranches_counters_reset_ts = 1.0
        return {
            "before": before,
            "cleared": sum(before.values()),
            "reset_ts": 1.0,
            "open_tranches": len(self._fold_tranches or []),
            "reason": str(reason),
        }

    monkeypatch.setattr(ScrummingBot, "clear_lifetime_tranche_counters", _no_mirror)


def _without_the_reset_stamp(monkeypatch) -> None:
    """Clear the four counters and record nothing about having done so."""
    from src.trading.scrumming_bot import ScrummingBot

    assert callable(ScrummingBot.clear_lifetime_tranche_counters)

    def _no_stamp(self, reason: str = "operator") -> dict:
        before = {
            "created": int(getattr(self, "_tranches_created_lifetime", 0) or 0),
            "closed": int(getattr(self, "_tranches_closed_lifetime", 0) or 0),
            "discarded": int(getattr(self, "_tranches_discarded_lifetime", 0) or 0),
            "malformed": int(getattr(self, "_tranches_malformed_dropped", 0) or 0),
        }
        self._tranches_created_lifetime = 0
        self._tranches_closed_lifetime = 0
        self._tranches_discarded_lifetime = 0
        self._tranches_malformed_dropped = 0
        self.stats.tranches_discarded_lifetime = 0
        return {
            "before": before,
            "cleared": sum(before.values()),
            "reset_ts": 0.0,
            "open_tranches": len(self._fold_tranches or []),
            "reason": str(reason),
        }

    monkeypatch.setattr(ScrummingBot, "clear_lifetime_tranche_counters", _no_stamp)


def test_POSITIVE_CONTROL_the_reader_finds_the_uncleared_counters(panel):
    """A file reader that cannot see a counter must not pass as a zero."""
    panel.manager.save_all_state()
    found = panel.saved_counters()
    assert found is not None, "the reader found no record for this bot at all"
    assert found["opened"] == OPENED
    assert found["closed"] == CLOSED
    assert found["discarded"] == DISCARDED
    assert found["malformed"] == MALFORMED
    assert found["stats_discarded"] == DISCARDED
    assert found["reset_ts"] == 0.0


def test_POSITIVE_CONTROL_the_reader_returns_none_with_no_file(panel):
    """The reader must distinguish "no file" from "a file of zeroes"."""
    assert panel.saved_counters() is None


def test_the_panel_starts_by_showing_the_operators_numbers(panel):
    """A panel that showed nothing would make every "after" reading free."""
    shows = panel.shows()
    assert shows["lifetime_opened_text"] == str(OPENED)
    assert shows["lifetime_closed_text"] == str(CLOSED)
    assert shows["lifetime_discarded_text"] == str(DISCARDED)
    assert shows["malformed_text"] == str(MALFORMED)
    assert shows["cycle_ratio_text"].startswith("99.5")
    assert shows["counters_button_text"] == (
        f"Clear Lifetime Counters ({OPENED} opened)"
    )
    assert shows["counters_button_enabled"] is True
    assert shows["counters_reset_text"] is None


class TestTheStateFileHoldsZero:

    def test_all_four_counters_are_zero_in_the_file(self, panel, monkeypatch):
        """A clear that only ran in memory is undone by the next restart."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        found = panel.saved_counters()
        assert found is not None, "the clear never reached the state file"
        assert found["opened"] == 0
        assert found["closed"] == 0
        assert found["discarded"] == 0
        assert found["malformed"] == 0

    def test_the_stats_mirror_is_zero_in_the_file(self, panel, monkeypatch):
        """A mirror left behind publishes 0 and 91 for one quantity."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.saved_counters()["stats_discarded"] == 0

    def test_the_file_records_when_the_reset_happened(self, panel, monkeypatch):
        """Without the stamp the file cannot tell a reset from a new bot."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.saved_counters()["reset_ts"] > 0.0

    def test_CONTROL_without_the_in_click_save_the_file_is_untouched(
        self, panel, monkeypatch
    ):
        """The defect: cleared in memory, restored by the next launch."""
        _without_the_in_click_save(monkeypatch)
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.bot._tranches_created_lifetime == 0
        assert panel.saved_counters() is None

    def test_CONTROL_without_the_stats_mirror_the_file_disagrees(
        self, panel, monkeypatch
    ):
        """The defect: 0 under scrumming_state, 91 under stats."""
        _without_the_stats_mirror(monkeypatch)
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        found = panel.saved_counters()
        assert found["discarded"] == 0
        assert found["stats_discarded"] == DISCARDED


class TestThePanelFollowsTheClear:

    def test_the_opened_row_reads_zero(self, panel, monkeypatch):
        """A stale row makes a working button look like a broken one."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.shows()["lifetime_opened_text"] == "0"

    def test_the_closed_row_reads_zero(self, panel, monkeypatch):
        """A stale row makes a working button look like a broken one."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.shows()["lifetime_closed_text"] == "0"

    def test_the_discarded_row_is_gone(self, panel, monkeypatch):
        """The row is hidden at zero; a row still printing 91 is stale."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.shows()["lifetime_discarded_text"] is None

    def test_the_malformed_row_reads_zero(self, panel, monkeypatch):
        """This row is always shown, so a stale 4 stays on the panel."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.shows()["malformed_text"] == "0"

    def test_the_ratio_row_says_there_is_nothing_left_to_fold(self, panel, monkeypatch):
        """With no denominator the ratio must refuse to print a number."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert "nothing left to fold back" in panel.shows()["cycle_ratio_text"]

    def test_the_button_names_nothing_and_is_disabled(self, panel, monkeypatch):
        """A live button on four zeroes invites a click that does nothing."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        shows = panel.shows()
        assert shows["counters_button_text"] == "Clear Lifetime Counters"
        assert shows["counters_button_enabled"] is False

    def test_the_panel_says_when_it_was_cleared(self, panel, monkeypatch):
        """Four zeroes look the same on a new bot and on a cleared one."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.shows()["counters_reset_text"] is not None

    def test_CONTROL_without_the_refresh_the_panel_is_stale(self, panel, monkeypatch):
        """The defect: the bot reads zero and the panel still reads 4925."""
        _without_the_refresh(monkeypatch)
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.bot._tranches_created_lifetime == 0
        assert panel.shows()["lifetime_opened_text"] == str(OPENED)


class TestTheClearTouchesNothingElse:

    def test_the_open_tranches_are_still_there(self, panel, monkeypatch):
        """A counter reset that removed a tranche removes queued money."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert len(panel.bot._fold_tranches) == OPEN_TRANCHES
        assert panel.shows()["fold_rows"] == OPEN_TRANCHES
        assert panel.shows()["open_tranches_label"] == str(OPEN_TRANCHES)

    def test_the_parked_usd_is_unchanged(self, panel, monkeypatch):
        """The parked total is the queue's money; a reset must not spend it."""
        _patch_message_box(monkeypatch)
        before = panel.bot._fold_queue_usd
        panel.dialog._on_clear_lifetime_counters()
        assert panel.bot._fold_queue_usd == pytest.approx(before)

    def test_the_wire_credits_are_unchanged(self, panel, monkeypatch):
        """Parked wire credit belongs to the other button, not this one."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.bot._pending_wire_credits == pytest.approx(PARKED_USD)
        assert len(panel.bot._pending_wire_ledger) == 1
        assert panel.bot._wire_credits_discarded_lifetime == pytest.approx(
            WIRE_DISCARDED
        )

    def test_the_stack_counters_are_unchanged(self, panel, monkeypatch):
        """The Stack tab keeps its own two counters and its own reset."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.bot._stack_created == 7
        assert panel.bot._stack_discarded == 2

    def test_the_position_is_unchanged(self, panel, monkeypatch):
        """A reset that moved a lot moves cost basis, and so moves trades."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.bot._main_lots == [{"units": 0.5, "initial_buy_price": 200.0}]
        assert panel.bot._current_holdings == pytest.approx(0.5)
        assert panel.bot._target_balance == pytest.approx(100.0)

    def test_the_file_keeps_everything_but_the_four_counters(self, panel, monkeypatch):
        """On disk is where a restart reads it; memory alone is not enough."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        scr = panel.saved()["scrumming_state"]
        assert len(scr["fold_tranches"]) == OPEN_TRANCHES
        assert scr["pending_wire_credits"] == pytest.approx(PARKED_USD)
        assert scr["wire_credits_discarded_lifetime"] == pytest.approx(WIRE_DISCARDED)
        assert scr["stack_created"] == 7
        assert scr["stack_discarded"] == 2
        assert len(scr["main_lots"]) == 1


ADOPTION_PRICE = 10.0
ADOPTION_HOLDINGS = 4.0


class _Ticker:
    last = ADOPTION_PRICE
    bid = ADOPTION_PRICE - 0.1
    ask = ADOPTION_PRICE + 0.1


class _Balance:
    absent = False

    def __init__(self, total: float) -> None:
        self.total = total
        self.free = total


def _adopts_the_exchange_balance(bot, holdings: float = ADOPTION_HOLDINGS) -> bool:
    """Run the shipped ``_tick_initialise`` and report whether it took `_main_lots`.

    Stubs only the outward reads — ticker, balance and the quote refresh — so the
    adoption branch under test is the one the bot runs at launch.
    """
    import asyncio

    async def _ticker(_symbol):
        return _Ticker()

    async def _balance(_asset):
        return _Balance(holdings)

    async def _quote():
        return None

    before = [dict(lot) for lot in bot._main_lots]
    bot._get_ticker = _ticker
    bot._get_balance = _balance
    bot._refresh_quote_to_usd = _quote
    asyncio.run(bot._tick_initialise(f"{bot.config.target_asset}/USD"))
    return [dict(lot) for lot in bot._main_lots] != before


class TestTheOpeningPositionAdoptionIsNotReArmed:

    def test_a_cleared_bot_keeps_the_lots_it_earned(self, panel, monkeypatch):
        """Adoption would replace `_main_lots` with one lot at a derived basis."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.bot._tranches_created_lifetime == 0
        assert _adopts_the_exchange_balance(panel.bot) is False

    def test_it_survives_an_export_import_round_trip(self, panel, monkeypatch):
        """The launch AFTER the reset is the one the adoption fires on."""
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        twin = _build(panel.state_manager._path.parent / "twin")
        try:
            twin.bot.import_scrumming_state(panel.bot.export_scrumming_state())
            assert twin.bot._tranches_created_lifetime == 0
            assert twin.bot._tranches_closed_lifetime == 0
            assert twin.bot._tranches_discarded_lifetime == 0
            assert twin.bot._tranches_malformed_dropped == 0
            assert _adopts_the_exchange_balance(twin.bot) is False
        finally:
            _destroy(twin)

    def test_CONTROL_without_the_stamp_the_adoption_is_re_armed(
        self, panel, monkeypatch
    ):
        """The defect: a 4,925-scrum bot reads as brand new at next launch."""
        _without_the_reset_stamp(monkeypatch)
        _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert _adopts_the_exchange_balance(panel.bot) is True
        assert panel.bot._main_lots == [
            {"units": ADOPTION_HOLDINGS, "initial_buy_price": ADOPTION_PRICE}
        ]

    def test_a_bot_that_never_scrummed_is_left_alone(self, tmp_path):
        """Clearing a bot with nothing to clear leaves its adoption armed."""
        fresh = _build(tmp_path, opened=0, closed=0, discarded=0)
        try:
            fresh.bot._tranches_malformed_dropped = 0
            fresh.bot.stats.tranches_discarded_lifetime = 0
            report = fresh.bot.clear_lifetime_tranche_counters(reason="test")
            assert report["cleared"] == 0
            assert fresh.bot._tranches_counters_reset_ts == 0.0
            assert _adopts_the_exchange_balance(fresh.bot) is True
        finally:
            _destroy(fresh)


class TestWhatTheOperatorIsTold:

    def test_the_confirmation_names_all_four_numbers(self, panel, monkeypatch):
        """A confirmation that hides a number asks for blind consent."""
        log = _patch_message_box(monkeypatch, answer_yes=False)
        panel.dialog._on_clear_lifetime_counters()
        text = log.confirm
        for number in (OPENED, CLOSED, DISCARDED, MALFORMED):
            assert str(number) in text

    def test_the_confirmation_names_the_reconciliation_it_breaks(
        self, panel, monkeypatch
    ):
        """Zeroing three terms against 3 standing tranches is visible."""
        log = _patch_message_box(monkeypatch, answer_yes=False)
        panel.dialog._on_clear_lifetime_counters()
        assert f"{OPEN_TRANCHES} open fold" in log.confirm

    def test_cancel_clears_nothing(self, panel, monkeypatch):
        """A refused confirmation that still mutates is the worst defect."""
        _patch_message_box(monkeypatch, answer_yes=False)
        panel.dialog._on_clear_lifetime_counters()
        assert panel.bot._tranches_created_lifetime == OPENED
        assert panel.bot._tranches_counters_reset_ts == 0.0
        assert panel.saved_counters() is None

    def test_the_result_leads_with_the_result(self, panel, monkeypatch):
        """Reassurance in the first line reads as "nothing happened"."""
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        first = log.result.split("\n\n")[0]
        assert first.startswith("Cleared ")
        assert "No order was placed" not in first

    def test_the_result_says_it_reached_disk(self, panel, monkeypatch):
        """A clear that did not save must say so, not imply it did."""
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert "Saved to disk." in log.result

    def test_the_result_says_the_panel_was_rebuilt(self, panel, monkeypatch):
        """The operator must not be told to reopen a panel that refreshed."""
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert "has been rebuilt" in log.result

    def test_CONTROL_without_the_in_click_save_the_result_says_so(
        self, panel, monkeypatch
    ):
        """A failed save reported as success is the gap this button closes."""
        _without_the_in_click_save(monkeypatch)
        log = _patch_message_box(monkeypatch)
        panel.dialog._on_clear_lifetime_counters()
        assert "NOT SAVED TO DISK" in log.result

    def test_an_already_zero_bot_is_told_so_and_nothing_runs(
        self, tmp_path, monkeypatch
    ):
        """A no-op that raises a confirmation asks about nothing."""
        import PySide6.QtWidgets as _QtWidgets

        fresh = _build(tmp_path, opened=0, closed=0, discarded=0)
        try:
            fresh.bot._tranches_malformed_dropped = 0
            seen: list[str] = []

            class _Recorder:
                @staticmethod
                def information(_p, _t, text, *_a, **_k):
                    seen.append(text)

            monkeypatch.setattr(_QtWidgets, "QMessageBox", _Recorder)
            fresh.dialog._on_clear_lifetime_counters()
            assert seen == ["This bot's lifetime tranche counters already read zero."]
            assert fresh.bot._tranches_counters_reset_ts == 0.0
        finally:
            _destroy(fresh)


class TestTheBotMethod:

    def test_it_reports_what_it_destroyed(self, panel):
        """A clear that reports nothing leaves no record of the numbers."""
        report = panel.bot.clear_lifetime_tranche_counters(reason="test")
        assert report["before"] == {
            "created": OPENED,
            "closed": CLOSED,
            "discarded": DISCARDED,
            "malformed": MALFORMED,
        }
        assert report["cleared"] == OPENED + CLOSED + DISCARDED + MALFORMED
        assert report["open_tranches"] == OPEN_TRANCHES

    def test_it_logs_the_four_numbers(self, panel, capture_log):
        """A destructive act with no log line cannot be reconstructed."""
        with capture_log("acervator.scrumming") as records:
            panel.bot.clear_lifetime_tranche_counters(reason="test")
        text = " ".join(r.getMessage() for r in records)
        assert "cleared lifetime tranche counters" in text
        assert str(OPENED) in text and str(CLOSED) in text

    def test_a_non_finite_counter_does_not_raise(self, panel):
        """`int(nan)` raises, and this runs inside an operator's click."""
        panel.bot._tranches_discarded_lifetime = float("nan")
        report = panel.bot.clear_lifetime_tranche_counters(reason="test")
        assert report["before"]["discarded"] == 0
        assert panel.bot._tranches_discarded_lifetime == 0
