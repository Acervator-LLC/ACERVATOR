"""C01: a save never removes a bot record.

Operator, 2026-08-05: "I do not want you removing a bot on disk because
its not in memory... Why modify long term storage based on what could be
a short term glitch?"

THE RULE
  A save never removes a bot record from bot_state.json. A record is
  removed only when the operator explicitly deletes that bot, and that
  removal is written at the moment of deletion — never inferred from a
  bot's absence from memory.

WHY ABSENCE PROVED NOTHING
  save_state rebuilt "bots" from the list it was handed, and
  save_all_state hands it only bots in BotManager._bots. So any
  transient in-memory condition became permanent loss on the next 60s
  tick. The sharpest case: register() returns (False, reason) on capital
  over-allocation (MEM-417) — a momentary allocation state — and one
  minute later that bot's per-lot cost basis is gone. The live file
  holds 1,949 lots and 829 fold tranches, none of it reconstructible
  from exchange fill history.

THE TRAP THIS FILE EXISTS TO CATCH
  Deletion was never implemented. unregister() touches no storage at
  all — no state manager, no save call, no file access. A deleted bot
  vanished from disk ONLY because the next save rebuilt the file from
  RAM. Deletion was a side effect of the bug, which is also why it was
  never logged: there was no delete operation to log.

  So "saves never delete", implemented naively, makes delete a no-op and
  deleted bots return forever. TestDeletedBotStaysDeleted is the pin for
  that, and it is the reason delete_bot() exists.

tmp_path only. Nothing here touches ~/.acervator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core import state_manager  # noqa: E402
from src.core.state_manager import StateManager  # noqa: E402


def _rec(bot_id: str, lots: int = 2, tranches: int = 1) -> dict:
    return {
        "bot_id": bot_id,
        "config": {"exchange_id": "coinbase", "symbol": "BTC/USD"},
        "scrumming_state": {
            "main_lots": [{"qty": 1.0, "price": 100.0}] * lots,
            "fold_tranches": [{"usd": 5.0}] * tranches,
        },
    }


@pytest.fixture
def sm(tmp_path, monkeypatch):
    mgr = StateManager()
    monkeypatch.setattr(mgr, "_path", tmp_path / "bot_state.json")
    monkeypatch.setattr(mgr, "_backup_path", tmp_path / "bot_state.backup.json")
    return mgr


def _bots(sm) -> dict:
    return json.loads(sm._path.read_text(encoding="utf-8"))["bots"]


class TestSaveNeverRemoves:
    def test_a_bot_absent_from_memory_survives_the_save(self, sm):
        """The headline. Before C01 this record was erased."""
        sm.save_state([_rec("keeps"), _rec("skipped-at-restore")])
        sm.save_state([_rec("keeps")])  # skipped bot not passed
        assert set(_bots(sm)) == {"keeps", "skipped-at-restore"}

    def test_the_carried_record_is_preserved_intact(self, sm):
        """Not merely present — its lots and tranches must be untouched."""
        sm.save_state([_rec("a"), _rec("rich", lots=164, tranches=37)])
        sm.save_state([_rec("a")])
        carried = _bots(sm)["rich"]["scrumming_state"]
        assert len(carried["main_lots"]) == 164
        assert len(carried["fold_tranches"]) == 37

    def test_memory_wins_for_a_bot_that_IS_loaded(self, sm):
        """Carry-forward must not resurrect stale data over live data."""
        sm.save_state([_rec("a", lots=2)])
        sm.save_state([_rec("a", lots=9)])
        assert len(_bots(sm)["a"]["scrumming_state"]["main_lots"]) == 9

    def test_bot_count_reflects_the_merged_total(self, sm):
        sm.save_state([_rec("a"), _rec("b")])
        sm.save_state([_rec("a")])
        state = json.loads(sm._path.read_text(encoding="utf-8"))
        assert state["bot_count"] == 2 == len(state["bots"])

    def test_repeated_saves_do_not_accumulate_duplicates(self, sm):
        sm.save_state([_rec("a"), _rec("b")])
        for _ in range(5):
            sm.save_state([_rec("a")])
        assert set(_bots(sm)) == {"a", "b"}


class TestDeletedBotStaysDeleted:
    """The trap. Without delete_bot(), 'saves never delete' means
    deleted bots return on every save, forever."""

    def test_delete_removes_the_record(self, sm):
        sm.save_state([_rec("a"), _rec("doomed")])
        assert sm.delete_bot("doomed") is True
        assert set(_bots(sm)) == {"a"}

    def test_a_deleted_bot_does_not_come_back_on_the_next_save(self, sm):
        """If this fails, the carry-forward is resurrecting deletions."""
        sm.save_state([_rec("a"), _rec("doomed")])
        sm.delete_bot("doomed")
        sm.save_state([_rec("a")])
        assert "doomed" not in _bots(sm)

    def test_delete_is_idempotent(self, sm):
        sm.save_state([_rec("a")])
        assert sm.delete_bot("never-existed") is False
        assert sm.delete_bot("never-existed") is False
        assert set(_bots(sm)) == {"a"}

    def test_delete_drops_the_ledger_row_and_wires(self, sm):
        """A delete must not leave the orphans the old path did — 13 of
        48 rows on the live file are exactly that."""
        sm.save_state(
            [_rec("a"), _rec("gone")],
            smart_wires=[
                {"source_id": "a", "target_id": "gone", "pct": 50},
                {"source_id": "gone", "target_id": "a", "pct": 10},
                {"source_id": "a", "target_id": "a2", "pct": 5},
            ],
            smart_wire_ledgers=[
                {"bot_id": "a", "wired_out": 1.0},
                {"bot_id": "gone", "wired_out": 2.0},
            ],
        )
        sm.delete_bot("gone")
        state = json.loads(sm._path.read_text(encoding="utf-8"))
        assert [r["bot_id"] for r in state["smart_wire_ledgers"]] == ["a"]
        assert len(state["smart_wires"]) == 1
        assert state["smart_wires"][0]["target_id"] == "a2"

    def test_delete_is_logged_at_error(self, sm, capture_log):
        """Irreversible and unreproducible from the exchange. It must be
        findable in the logs a year from now — today it is recorded
        NOWHERE, which is how the operator lost track of past deletes.

        `capture_log`, NOT `caplog`. `state_manager` logs on
        `acervator.state`, and `logging_engine` sets
        `acervator.propagate = False`, so the record never reaches the
        root handler `caplog` installs.
        """
        import logging

        sm.save_state([_rec("doomed", lots=7, tranches=3)])
        with capture_log("acervator.state") as records:
            sm.delete_bot("doomed")
        msg = " ".join(r.getMessage() for r in records if r.levelno >= logging.ERROR)
        assert "DELETED" in msg and "doomed" in msg
        assert "7 lot" in msg and "3 tranche" in msg


class TestUnregisterReachesDisk:
    """End to end. The unit tests above prove delete_bot() works; these
    prove the operator's Delete button actually calls it.

    Before C01, BotManager.unregister() referenced no state manager, no
    save call and no file access — the record went away only because the
    next save rebuilt the file from RAM.
    """

    @pytest.fixture
    def mgr(self, sm):
        from src.trading.bot_container import BotManager

        m = BotManager()
        m.set_state_manager(sm)
        return m

    def _state(self, ids):
        return {"bots": {b: _rec(b) for b in ids}}

    def test_unregister_removes_the_record_from_disk(self, mgr, sm):
        mgr.restore_bots_from_state(self._state(["keep", "doomed"]))
        mgr.save_all_state()
        assert set(_bots(sm)) == {"keep", "doomed"}
        mgr.unregister("doomed")
        assert set(_bots(sm)) == {"keep"}

    def test_the_deleted_bot_does_not_return_on_the_next_save(self, mgr, sm):
        """The regression that 'saves never delete' would introduce
        without delete_bot(): a delete that does not reach disk is
        undone by the very next carry-forward."""
        mgr.restore_bots_from_state(self._state(["keep", "doomed"]))
        mgr.save_all_state()
        mgr.unregister("doomed")
        mgr.save_all_state()
        mgr.save_all_state()
        assert "doomed" not in _bots(sm)

    def test_a_bot_that_failed_to_restore_is_NOT_deleted_by_a_save(self, mgr, sm):
        """The whole point of the cascade, end to end.

        A bot whose persisted config lacks exchange_id is skipped at
        restore, so it never enters _bots. Before C01 the next save
        erased it. It must now survive untouched.
        """
        state = self._state(["healthy"])
        broken = _rec("skipped", lots=41, tranches=9)
        broken["config"]["exchange_id"] = ""
        state["bots"]["skipped"] = broken
        sm.save_state([_rec("healthy"), broken])

        mgr.restore_bots_from_state(state)
        assert "skipped" not in mgr._bots
        mgr.save_all_state()
        mgr.save_all_state()

        survived = _bots(sm)["skipped"]["scrumming_state"]
        assert len(survived["main_lots"]) == 41
        assert len(survived["fold_tranches"]) == 9


class TestTheMergeCannotBreakSaving:
    def test_an_unreadable_file_does_not_abort_the_save(self, sm):
        """Falls back to memory-only contents — no worse than what
        shipped for the last year — rather than losing the save."""
        sm._path.parent.mkdir(parents=True, exist_ok=True)
        sm._path.write_text("{corrupt", encoding="utf-8")
        sm.save_state([_rec("a")])
        assert set(_bots(sm)) == {"a"}

    def test_a_failing_reader_does_not_abort_the_save(self, sm, monkeypatch):
        def boom(*_a, **_kw):
            raise RuntimeError("simulated")

        sm.save_state([_rec("a")])
        monkeypatch.setattr(sm, "_read_bot_records", boom)
        sm.save_state([_rec("b")])
        assert "b" in _bots(sm)

    def test_delete_failure_leaves_the_record_intact(self, sm, monkeypatch):
        """Better to keep a record that should have gone than to lose
        one that should have stayed.

        The failure is injected at the write boundary the module calls,
        not at a serialiser it happens to use, so this stays honest
        whichever serialiser sits behind it.
        """
        sm.save_state([_rec("a"), _rec("b")])

        def boom(*_a, **_kw):
            raise OSError("simulated")

        monkeypatch.setattr("src.core.state_manager.atomic_write_json", boom)
        assert sm.delete_bot("b") is False
        assert set(_bots(sm)) == {"a", "b"}

    def test_the_delete_injection_reaches_the_write(self, sm, monkeypatch):
        """Positive control for the test above. Without it, a delete that
        never reached the write would read as a preserved record."""
        sm.save_state([_rec("a"), _rec("b")])
        seen: list[str] = []

        def spy(path, *_a, **_kw):
            seen.append(str(path))
            raise OSError("simulated")

        monkeypatch.setattr(state_manager, "atomic_write_json", spy)
        sm.delete_bot("b")
        assert seen == [str(sm._path)]
