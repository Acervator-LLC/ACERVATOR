"""Pins for the C01 restore ledger — PR-0 (observation only).

The ambiguity this cascade exists to resolve: a bot absent from
``BotManager._bots`` might have been DELETED by the operator, or might
have FAILED to restore. ``save_state`` rebuilds ``"bots"`` from the
registered set, so today both resolve the same way — the record is
erased by the 60-second save timer.

Absence cannot distinguish them, so the ledger does not try. It is
written ONLY by code that OBSERVED a bot fail to load. A bot in the
ledger definitely was not deleted on purpose.

Six exits write to it, enumerated by AST rather than by reading the
brief (which said four):

    no exchange_id in persisted config      (was entirely SILENT)
    legacy grid mode (unrestorable)
    mode-shape violation in persisted config
    no construction branch for mode
    construction failed
    registration refused                    (register()'s return was
                                             being DISCARDED)

PR-0 records and reports. Nothing carries forward yet.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.trading.bot_container import BotManager  # noqa: E402


def _record(bot_id: str, **cfg) -> dict:
    base = {"exchange_id": "coinbase", "symbol": "BTC/USD", "mode": "scrumming"}
    base.update(cfg)
    return {
        "bot_id": bot_id,
        "config": base,
        "state_when_saved": "idle",
        "scrumming_state": {"main_lots": [{"qty": 1.0, "price": 100.0}],
                            "fold_tranches": [{"usd": 5.0}]},
    }


@pytest.fixture
def mgr():
    return BotManager()


class TestLedgerRecordsObservedFailures:
    def test_missing_exchange_id_is_recorded(self, mgr):
        """The exit that used to be completely silent."""
        state = {"bots": {"bot-broken": _record("bot-broken", exchange_id="")}}
        mgr.restore_bots_from_state(state)
        assert "bot-broken" in mgr._restore_ledger
        assert "exchange_id" in mgr._restore_ledger["bot-broken"]

    def test_a_healthy_bot_is_not_in_the_ledger(self, mgr):
        state = {"bots": {"bot-ok": _record("bot-ok")}}
        mgr.restore_bots_from_state(state)
        assert "bot-ok" not in mgr._restore_ledger

    def test_ledger_is_reset_per_restore(self, mgr):
        """A stale entry from a previous restore would carry a record
        the operator has since legitimately removed."""
        mgr._restore_ledger = {"ghost": "from a previous session"}
        mgr.restore_bots_from_state({"bots": {}})
        assert "ghost" not in mgr._restore_ledger


class TestBootRecordsAreHeldInRam:
    def test_records_are_captured(self, mgr):
        state = {"bots": {"bot-a": _record("bot-a")}}
        mgr.restore_bots_from_state(state)
        assert "bot-a" in mgr._boot_state_records

    def test_capture_is_a_deep_copy(self, mgr):
        """PR-1 hands these to save_state by value. If they aliased the
        live dict, a mutation during restore would silently rewrite what
        gets carried forward."""
        rec = _record("bot-a")
        state = {"bots": {"bot-a": rec}}
        mgr.restore_bots_from_state(state)
        rec["scrumming_state"]["main_lots"].append({"qty": 99.0})
        carried = mgr._boot_state_records["bot-a"]["scrumming_state"]["main_lots"]
        assert len(carried) == 1, "boot snapshot aliased the live record"


class TestRestoreCompletion:
    def test_flag_set_when_restore_reaches_the_end(self, mgr):
        mgr.restore_bots_from_state({"bots": {"bot-a": _record("bot-a")}})
        assert mgr._restore_completed is True

    def test_flag_starts_false(self, mgr):
        assert mgr._restore_completed is False


class TestExplicitDeleteClearsTheLedger:
    def test_unregister_removes_a_ledger_entry(self, mgr):
        """Deleting a bot must mean deleting it.

        The ledger protects the UNOBSERVED case; it must never override
        an explicit instruction, or a bot that failed to restore and was
        then deliberately removed would be resurrected by PR-1's carry.
        """
        mgr._restore_ledger["bot-x"] = "construction failed"
        mgr._boot_state_records["bot-x"] = _record("bot-x")
        mgr.unregister("bot-x")
        assert "bot-x" not in mgr._restore_ledger
        assert "bot-x" not in mgr._boot_state_records

    def test_unregister_of_an_unknown_id_is_a_noop(self, mgr):
        mgr.unregister("never-existed")   # must not raise


class TestLedgerHelperIsSafe:
    def test_ledger_skip_never_raises(self, mgr):
        """It is called from inside except-handlers that are already
        dealing with a failure; it must not add a second one."""
        mgr._restore_ledger = None
        mgr._ledger_skip("bot-a", "reason")   # must not raise


class TestImportFailureIsWorseThanASkip:
    """RESOLVED in v3.24.48 (Phase 1 Step 5). This class documented the
    defect; the fix has now landed and these assertions track it.

    What it documented: control fell through to register(), so the bot
    landed in ``self._bots`` holding DEFAULT state — and because
    save_state rebuilds ``"bots"`` from the registered set, the next 60s
    save wrote those defaults over the good persisted record. A skipped
    bot is merely absent; that one actively overwrote.

    ``test_failed_import_is_recorded_in_the_ledger`` asserted
    ``"bot-a" in mgr._bots`` with the note *"PR-0 does not change
    registration"* — the fix was explicitly deferred, not endorsed.
    Step 5 is that deferred change, so the registration assertions are
    inverted here rather than deleted: the bot must now be ABSENT, which
    is exactly what lets state_manager's absence-keyed carry-forward
    preserve the on-disk record.

    The class name is kept. A failed import IS still worse than a skip —
    that is why it is now made into one.
    """

    def test_healthy_import_leaves_the_flag_false(self, mgr):
        mgr.restore_bots_from_state({"bots": {"bot-a": _record("bot-a")}})
        c = mgr._bots["bot-a"]
        inner = getattr(c, "bot", None) or c
        assert getattr(inner, "_state_import_failed", None) is False

    def test_a_failed_import_does_not_register_the_bot(self, mgr,
                                                       monkeypatch):
        """v3.24.48 — was `test_failed_scrumming_import_sets_the_flag`,
        which reached into `mgr._bots["bot-a"]` to read the flag. The bot
        is deliberately no longer there.

        Absence IS the protection: save_state rebuilds "bots" from the
        registered set, and state_manager carries forward every on-disk
        record absent from it. A registered bot holding defaults is what
        overwrote the record."""
        from src.trading.scrumming_bot import ScrummingBot

        def boom(self, _state):
            raise ValueError("simulated corrupt scrumming_state")

        monkeypatch.setattr(ScrummingBot, "import_scrumming_state", boom)
        mgr.restore_bots_from_state({"bots": {"bot-a": _record("bot-a")}})
        assert "bot-a" not in mgr._bots, (
            "a bot whose state failed to import is registered with "
            "DEFAULT state; the next save will overwrite its record")

    def test_failed_import_is_recorded_in_the_ledger(self, mgr, monkeypatch):
        """The ledger is now the ONLY in-memory trace of the failure,
        since the bot is not registered. It is what tells the boot
        report the bot was skipped rather than deleted."""
        from src.trading.scrumming_bot import ScrummingBot

        def boom(self, _state):
            raise ValueError("simulated corrupt scrumming_state")

        monkeypatch.setattr(ScrummingBot, "import_scrumming_state", boom)
        mgr.restore_bots_from_state({"bots": {"bot-a": _record("bot-a")}})
        assert "bot-a" in mgr._restore_ledger
        assert "import_scrumming_state" in mgr._restore_ledger["bot-a"]

    def test_a_healthy_bot_is_still_registered(self, mgr):
        """NEGATIVE CONTROL. Skipping on failure must not skip always —
        that would empty the fleet."""
        mgr.restore_bots_from_state({"bots": {"bot-a": _record("bot-a")}})
        assert "bot-a" in mgr._bots

    def test_the_boot_record_is_still_available_to_carry(self, mgr,
                                                         monkeypatch):
        """PR-1 needs the ORIGINAL record, not the defaults now in
        memory. Prove the boot snapshot still holds the real lots."""
        from src.trading.scrumming_bot import ScrummingBot

        def boom(self, _state):
            raise ValueError("simulated corrupt scrumming_state")

        monkeypatch.setattr(ScrummingBot, "import_scrumming_state", boom)
        mgr.restore_bots_from_state({"bots": {"bot-a": _record("bot-a")}})
        carried = mgr._boot_state_records["bot-a"]["scrumming_state"]
        assert len(carried["main_lots"]) == 1
        assert len(carried["fold_tranches"]) == 1
