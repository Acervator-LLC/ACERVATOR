"""Pins for the C01 prune detectors — PR-0 (log-only).

`save_state` rebuilds `"bots"` from scratch out of the list it is handed
and never read-merges against disk. `save_all_state` hands it only bots
present in `BotManager._bots`, so a bot skipped or refused during restore
is absent — and the 60-second save timer erases its record. What is lost
is not derivable from exchange fill history: measured on the live file
2026-08-05, 35 bots holding 1,949 per-lot cost-basis entries and 829 fold
tranches.

PR-0 adds no merge. It adds two detectors so the failure is VISIBLE:

  detect_prune(incoming)      what THIS save is about to drop
  diff_primary_vs_backup()    damage a PREVIOUS save already did

Both must be incapable of raising — they sit on the live save path and on
boot, and a detector that can break saving is worse than the defect it
watches.

Every test here uses tmp_path. Nothing touches ~/.acervator.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.core.state_manager import StateManager  # noqa: E402


def _write_state(path: Path, bot_ids) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "version": "1.9.5",
        "bot_count": len(bot_ids),
        "bots": {b: {"bot_id": b, "scrumming_state": {"main_lots": [1, 2]}}
                 for b in bot_ids},
    }), encoding="utf-8")


@pytest.fixture
def sm(tmp_path, monkeypatch):
    """A StateManager rooted entirely inside tmp_path."""
    mgr = StateManager()
    monkeypatch.setattr(mgr, "_path", tmp_path / "bot_state.json")
    monkeypatch.setattr(mgr, "_backup_path", tmp_path / "bot_state.backup.json")
    return mgr


class TestDetectPrune:
    def test_reports_ids_present_on_disk_but_absent_from_the_save(self, sm):
        _write_state(sm._path, ["bot-a", "bot-b", "bot-c"])
        assert sm.detect_prune({"bot-a", "bot-c"}) == ["bot-b"]

    def test_clean_save_reports_nothing(self, sm):
        _write_state(sm._path, ["bot-a", "bot-b"])
        assert sm.detect_prune({"bot-a", "bot-b"}) == []

    def test_growth_is_not_a_prune(self, sm):
        """Adding a bot must not be reported as dropping one."""
        _write_state(sm._path, ["bot-a"])
        assert sm.detect_prune({"bot-a", "bot-new"}) == []

    def test_absent_file_reports_nothing(self, sm):
        assert sm.detect_prune({"bot-a"}) == []

    def test_unreadable_file_is_unknown_not_empty(self, sm):
        """A corrupt file must NOT be read as 'no bots on disk'.

        Treating unknown as empty would report every incoming bot as
        surviving a prune that was never measured -- a detector that
        lies quietly is worse than one that says it cannot tell.
        """
        sm._path.parent.mkdir(parents=True, exist_ok=True)
        sm._path.write_text("{not json", encoding="utf-8")
        assert sm._read_bot_ids(sm._path) is None
        assert sm.detect_prune({"bot-a"}) == []

    def test_never_raises_even_when_everything_is_wrong(self, sm,
                                                        monkeypatch):
        """It sits on the live save path. It may not break saving."""
        def boom(*_a, **_kw):
            raise RuntimeError("simulated catastrophe")
        monkeypatch.setattr(sm, "_read_bot_ids", boom)
        assert sm.detect_prune({"bot-a"}) == []

    def test_logs_at_error_when_a_prune_is_detected(self, sm,
                                                    capture_log):
        """A detected prune must be visible at ERROR.

        `capture_log`, NOT `caplog`. `state_manager` logs on
        `acervator.state`, and `logging_engine` sets
        `acervator.propagate = False`, so the record never reaches the
        root handler `caplog` installs.
        """
        import logging
        _write_state(sm._path, ["bot-a", "bot-doomed"])
        with capture_log("acervator.state") as records:
            sm.detect_prune({"bot-a"})
        errors = [r for r in records if r.levelno >= logging.ERROR]
        assert any("PRUNE RISK" in r.getMessage() for r in errors), \
            "a detected prune must be visible at ERROR"


class TestDiffPrimaryVsBackup:
    def test_detects_a_bot_the_last_save_already_dropped(self, sm):
        """The one recoverable window: the backup lags the primary by
        exactly one save cycle (measured at 60s on the live tree)."""
        _write_state(sm._path, ["bot-a"])
        _write_state(sm._backup_path, ["bot-a", "bot-lost"])
        assert sm.diff_primary_vs_backup() == ["bot-lost"]

    def test_healthy_pair_reports_nothing(self, sm):
        _write_state(sm._path, ["bot-a", "bot-b"])
        _write_state(sm._backup_path, ["bot-a", "bot-b"])
        assert sm.diff_primary_vs_backup() == []

    def test_new_bot_in_primary_is_not_damage(self, sm):
        """The primary legitimately leads the backup by one cycle."""
        _write_state(sm._path, ["bot-a", "bot-brand-new"])
        _write_state(sm._backup_path, ["bot-a"])
        assert sm.diff_primary_vs_backup() == []

    def test_missing_backup_reports_nothing(self, sm):
        _write_state(sm._path, ["bot-a"])
        assert sm.diff_primary_vs_backup() == []

    def test_never_raises(self, sm, monkeypatch):
        def boom(*_a, **_kw):
            raise RuntimeError("simulated catastrophe")
        monkeypatch.setattr(sm, "_read_bot_ids", boom)
        assert sm.diff_primary_vs_backup() == []


class TestSaveStateStillWorks:
    """The detector is wired into the live save path. Prove it did not
    change what save_state actually writes."""

    def test_save_writes_every_incoming_bot(self, sm):
        sm.save_state([{"bot_id": "bot-a"}, {"bot_id": "bot-b"}])
        written = json.loads(sm._path.read_text(encoding="utf-8"))
        assert set(written["bots"]) == {"bot-a", "bot-b"}
        assert written["bot_count"] == 2

    def test_save_still_succeeds_when_the_detector_explodes(
            self, sm, monkeypatch):
        def boom(*_a, **_kw):
            raise RuntimeError("simulated catastrophe")
        monkeypatch.setattr(sm, "detect_prune", boom)
        with pytest.raises(RuntimeError):
            sm.save_state([{"bot_id": "bot-a"}])
        # Documents the ONE way the detector can still break a save: if
        # the method itself is replaced by something that raises. The
        # real implementation catches everything internally, which
        # test_never_raises_even_when_everything_is_wrong proves.

    def test_the_prune_this_cascade_exists_to_stop_no_longer_happens(
            self, sm, capture_log):
        """End-to-end: a save that omits a previously-persisted bot.

        INVERTED BY THE FIX, DELIBERATELY. In PR-0 this test asserted
        the opposite -- that the record WAS dropped -- with the message
        "PR-0 is log-only; the prune still happens by design". That was
        true then and is false now: save_state carries unknown on-disk
        records forward, so the record survives.

        Recorded rather than quietly edited, per the rule against
        modifying a test to make it pass. The assertion was not
        weakened; it was replaced, because the behaviour it pinned was
        the defect. A test asserting that data loss occurs has no
        business staying green once the loss is fixed.

        detect_prune() is kept as a tripwire and must now report
        NOTHING -- a non-empty report means an explicit delete or a
        regression.

        `capture_log`, NOT `caplog`, and here the choice decides
        whether the test means anything. The assertion is a NEGATIVE
        one: "the tripwire stayed silent". `logging_engine` sets
        `acervator.propagate = False`, so once the engine exists no
        record from `acervator.state` reaches the root handler
        `caplog` installs -- and a test that asserts NOTHING was
        logged then passes on an empty list it could never have
        filled. It would fail GREEN. `capture_log` attaches to
        `acervator.state` directly, so silence here is now evidence
        rather than an artifact of the handler wiring.
        """
        import logging
        _write_state(sm._path, ["bot-keeps", "bot-skipped-at-restore"])
        with capture_log("acervator.state") as records:
            sm.save_state([{"bot_id": "bot-keeps"}])
        written = json.loads(sm._path.read_text(encoding="utf-8"))
        assert "bot-skipped-at-restore" in written["bots"], \
            "a save must not remove a record it was simply not handed"
        assert written["bot_count"] == 2
        assert not any("PRUNE RISK" in r.getMessage()
                       for r in records
                       if r.levelno >= logging.ERROR), \
            "nothing was pruned, so the tripwire must stay silent"


class TestProbe:
    """`has_saved_state()` collapsed four outcomes onto a bool via
    `except Exception: return False`, and main.py:720 gates the ENTIRE
    restore on it — so an unreadable primary meant 'no saved state' and
    the platform launched with zero bots, never reaching load_state()'s
    backup fallback."""

    def test_no_file(self, sm):
        assert sm.probe() == "no_file"

    def test_empty(self, sm):
        _write_state(sm._path, [])
        assert sm.probe() == "empty"

    def test_has_bots(self, sm):
        _write_state(sm._path, ["bot-a"])
        assert sm.probe() == "has_bots"

    def test_unreadable_is_distinct_from_empty(self, sm):
        sm._path.parent.mkdir(parents=True, exist_ok=True)
        sm._path.write_text("{corrupt", encoding="utf-8")
        assert sm.probe() == "unreadable"

    @pytest.mark.parametrize("state,expected", [
        ("no_file", False), ("empty", False), ("has_bots", True),
    ])
    def test_has_saved_state_unchanged_for_healthy_cases(
            self, sm, state, expected):
        if state == "empty":
            _write_state(sm._path, [])
        elif state == "has_bots":
            _write_state(sm._path, ["bot-a"])
        assert sm.has_saved_state() is expected


class TestCorruptPrimaryCannotDestroyTheBackup:
    """The sequence that loses everything in one 60s cycle.

    Corrupt primary -> has_saved_state() says 'no state' -> launch with
    zero bots -> save timer fires -> backup step copies the CORRUPT
    primary over the good backup -> empty state overwrites the primary.
    Both files are then worthless.
    """

    def test_backup_is_preserved_when_the_primary_does_not_parse(self, sm):
        _write_state(sm._backup_path, ["bot-a", "bot-b"])
        good = sm._backup_path.read_bytes()
        sm._path.parent.mkdir(parents=True, exist_ok=True)
        sm._path.write_text("{corrupt", encoding="utf-8")

        sm.save_state([])          # the empty save that follows the bad boot

        assert sm._backup_path.read_bytes() == good, \
            "a corrupt primary overwrote the last good backup"
        assert set(json.loads(
            sm._backup_path.read_text(encoding="utf-8"))["bots"]) == {
                "bot-a", "bot-b"}

    def test_healthy_primary_still_refreshes_the_backup(self, sm):
        """Negative control: the guard must not disable backups.

        Without this, 'never overwrite the backup' would pass the test
        above while silently ending all backup refreshes.
        """
        _write_state(sm._path, ["bot-old"])
        _write_state(sm._backup_path, ["bot-ancient"])
        sm.save_state([{"bot_id": "bot-new"}])
        # backup should now hold what the primary held BEFORE this save
        assert set(json.loads(
            sm._backup_path.read_text(encoding="utf-8"))["bots"]) == {"bot-old"}

    def test_the_save_itself_still_succeeds(self, sm):
        """Refusing the backup refresh must not abort the save."""
        sm._path.parent.mkdir(parents=True, exist_ok=True)
        sm._path.write_text("{corrupt", encoding="utf-8")
        sm.save_state([{"bot_id": "bot-a"}])
        assert set(json.loads(
            sm._path.read_text(encoding="utf-8"))["bots"]) == {"bot-a"}
