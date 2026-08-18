"""Pins for the C01 preflight snapshot — PR-0.

Method rule M11: back up before the first destructive run.

The existing safety net is exactly one cycle deep. ``bot_state.backup``
is refreshed immediately before every save, so it holds the previous 60
seconds and nothing older — enough to survive one bad save and no more.
If a boot goes wrong and the save timer ticks twice, both copies are
gone, and with them 35 bots / 1,949 per-lot cost-basis entries / 829
fold tranches that exchange history cannot rebuild.

``preflight_snapshot()`` takes a dated copy of BOTH files at boot,
before restore runs and before the timer starts, giving a known-good
pre-session copy that the rolling backup cannot clobber.

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


def _write(path: Path, bot_ids) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "bot_count": len(bot_ids),
        "bots": {b: {"bot_id": b} for b in bot_ids},
    }), encoding="utf-8")


@pytest.fixture
def sm(tmp_path, monkeypatch):
    mgr = StateManager()
    monkeypatch.setattr(mgr, "_path", tmp_path / "bot_state.json")
    monkeypatch.setattr(mgr, "_backup_path",
                        tmp_path / "bot_state.backup.json")
    return mgr


def _snapshots(sm) -> list:
    return sorted((sm._path.parent / "preflight").glob("*.json"))


class TestItCopiesBothFiles:
    def test_both_files_are_snapshotted(self, sm):
        _write(sm._path, ["bot-a"])
        _write(sm._backup_path, ["bot-a"])
        written = sm.preflight_snapshot()
        assert len(written) == 2
        assert len(_snapshots(sm)) == 2

    def test_snapshots_go_in_a_subdirectory(self, sm):
        """Not scattered through the operator's runtime root."""
        _write(sm._path, ["bot-a"])
        sm.preflight_snapshot()
        assert (sm._path.parent / "preflight").is_dir()
        assert not list(sm._path.parent.glob("*.preflight.*"))

    def test_content_is_byte_identical(self, sm):
        _write(sm._path, ["bot-a", "bot-b"])
        sm.preflight_snapshot()
        snap = _snapshots(sm)[0]
        assert snap.read_bytes() == sm._path.read_bytes()

    def test_primary_only_is_fine(self, sm):
        """A fresh install has no backup yet."""
        _write(sm._path, ["bot-a"])
        assert len(sm.preflight_snapshot()) == 1

    def test_no_files_writes_nothing(self, sm):
        assert sm.preflight_snapshot() == []


@pytest.fixture
def tick(sm, monkeypatch):
    """Advance the snapshot timestamp on demand.

    Filenames are stamped to 1-second resolution, so exercising
    retention used to mean sleeping past the granularity — 10.6 seconds
    of wall clock across this file. `_preflight_stamp` exists to be
    overridden here: the tests are now deterministic AND instant, and no
    longer depend on real time, which is what made them flaky by
    construction.
    """
    counter = {"n": 0}

    def stamp(_self=None):
        counter["n"] += 1
        return f"20260805_00{counter['n']:04d}"

    monkeypatch.setattr(StateManager, "_preflight_stamp", stamp)
    return counter


class TestRepeatedBootsDoNotMultiplyCopies:
    def test_unchanged_state_is_skipped(self, sm, tick):
        """Restarting three times must not leave three identical pairs."""
        _write(sm._path, ["bot-a"])
        assert sm.preflight_snapshot()
        assert sm.preflight_snapshot() == []
        assert sm.preflight_snapshot() == []
        assert len(_snapshots(sm)) == 1

    def test_changed_state_is_snapshotted_again(self, sm, tick):
        """Negative control: skip-if-identical must not become
        skip-always, which would silently stop backing up."""
        _write(sm._path, ["bot-a"])
        sm.preflight_snapshot()
        _write(sm._path, ["bot-a", "bot-b"])
        assert sm.preflight_snapshot()
        assert len(_snapshots(sm)) == 2


class TestRetentionIsBounded:
    def test_old_snapshots_are_pruned(self, sm, monkeypatch, tick):
        """An unbounded copy pile inside the operator's own tree is not
        a kindness."""
        monkeypatch.setattr(StateManager, "PREFLIGHT_KEEP", 3)
        for i in range(5):
            _write(sm._path, [f"bot-{i}"])
            sm.preflight_snapshot()
        stamps = list((sm._path.parent / "preflight").glob("*.stamp"))
        assert len(stamps) == 3, f"expected 3 retained, got {len(stamps)}"
        assert len(_snapshots(sm)) == 3

    def test_the_newest_survives_pruning(self, sm, monkeypatch, tick):
        monkeypatch.setattr(StateManager, "PREFLIGHT_KEEP", 2)
        for i in range(4):
            _write(sm._path, [f"bot-{i}"])
            sm.preflight_snapshot()
        newest = max(_snapshots(sm), key=lambda p: p.name)
        assert json.loads(newest.read_text(encoding="utf-8"))["bots"] == {
            "bot-3": {"bot_id": "bot-3"}}


class TestBootOrdering:
    """The snapshot is worthless if it runs after a writer.

    Structural, not behavioural: re-entering main()'s boot in-process is
    not feasible, and an ordering guarantee is exactly the kind of thing
    a later refactor breaks silently. Parsing main.py catches a moved
    call; running the app would not.
    """

    @staticmethod
    def _call_lines(name: str) -> list:
        import ast
        src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        out = []
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.Call):
                fn = n.func
                if getattr(fn, "attr", None) == name or \
                        getattr(fn, "id", None) == name:
                    out.append(n.lineno)
        return sorted(out)

    def test_main_calls_preflight_snapshot(self):
        assert self._call_lines("preflight_snapshot"), \
            "main.py never takes a preflight snapshot"

    @pytest.mark.parametrize("writer", [
        "has_saved_state",   # the read that decides whether bots return
        "save_all_state",    # the 60s rolling save AND the shutdown save
    ])
    def test_preflight_runs_before_every_writer(self, writer):
        pre = self._call_lines("preflight_snapshot")
        later = self._call_lines(writer)
        assert later, f"expected main.py to call {writer}"
        assert min(pre) < min(later), (
            f"preflight_snapshot() at line {min(pre)} runs AFTER "
            f"{writer}() at line {min(later)} — the snapshot would be "
            f"taken from state that had already been modified")

    def test_preflight_runs_before_the_save_timer_starts(self):
        import ast
        src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
        starts = [n.lineno for n in ast.walk(ast.parse(src))
                  if isinstance(n, ast.Call)
                  and getattr(n.func, "attr", None) == "start"
                  and any(getattr(a, "value", None) == 60000
                          for a in n.args)]
        assert starts, "could not find save_timer.start(60000)"
        assert min(self._call_lines("preflight_snapshot")) < min(starts)

    def test_damage_detector_also_runs_at_boot(self):
        """diff_primary_vs_backup surfaces a bot the LAST save already
        pruned, while the backup copy still holds it — one cycle before
        it is overwritten."""
        assert self._call_lines("diff_primary_vs_backup"), \
            "main.py never checks for pre-existing C01 damage"


class TestItCannotAbortBoot:
    def test_never_raises_on_a_broken_filesystem(self, sm, monkeypatch):
        """A backup step that can kill startup is worse than none."""
        import shutil

        def boom(*_a, **_kw):
            raise OSError("simulated disk failure")

        _write(sm._path, ["bot-a"])
        monkeypatch.setattr(shutil, "copy2", boom)
        assert sm.preflight_snapshot() == []      # must not raise

    def test_never_raises_when_the_directory_cannot_be_made(
            self, sm, monkeypatch):
        _write(sm._path, ["bot-a"])
        monkeypatch.setattr(Path, "mkdir", lambda *_a, **_kw: (_ for _ in ()).throw(
            OSError("simulated permission denied")))
        assert sm.preflight_snapshot() == []      # must not raise
