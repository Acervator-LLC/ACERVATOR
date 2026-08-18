"""Pins for the live-tree isolation guard — CV1.

The guard in tests/conftest.py protects the operator's runtime tree
(~/.acervator, ~/.acervator_logs, and the Stone Tablet archive) from
suite writes. Before CV1 it watched ONE directory
(~/.acervator_logs/sim/runs) and compared only the names of its
immediate children, so it could not see:

  * anything under ~/.acervator at all
  * modification or deletion of an existing file
  * the Stone Tablet archive

Both isolation breaches this project has shipped landed in
~/.acervator, and BOTH happened while that guard was green.

Testing a guard is awkward: the thing it detects is damage to the
operator's data, and a test must never cause that. So the guard is
built in two testable pieces --

  _snapshot(roots)              stat-only walk, runs against tmp_path
  _classify(before, after, tr)  pure function over two dicts

-- and every test here uses synthetic roots. Nothing in this file
touches the real tree.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFTEST = REPO_ROOT / "tests" / "conftest.py"


def _load_conftest():
    spec = importlib.util.spec_from_file_location(
        "conftest_under_test", CONFTEST)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cf = _load_conftest()


# ── _snapshot ───────────────────────────────────────────────────────

class TestSnapshot:
    def test_maps_files_to_size_and_mtime(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
        snap = cf._snapshot((tmp_path,))
        assert len(snap) == 1
        size, mtime = next(iter(snap.values()))
        assert size == 5
        assert mtime > 0

    def test_walks_recursively(self, tmp_path):
        deep = tmp_path / "x" / "y" / "z"
        deep.mkdir(parents=True)
        (deep / "f.json").write_text("{}", encoding="utf-8")
        assert len(cf._snapshot((tmp_path,))) == 1

    def test_absent_root_is_not_an_error(self, tmp_path):
        assert cf._snapshot((tmp_path / "does-not-exist",)) == {}

    def test_directories_are_not_entries(self, tmp_path):
        (tmp_path / "emptydir").mkdir()
        assert cf._snapshot((tmp_path,)) == {}


# ── _classify ───────────────────────────────────────────────────────

TR = str(Path("/live/.acervator/stone_tablets"))


def _p(name: str) -> str:
    return str(Path("/live/.acervator") / name)


class TestClassify:
    def test_no_change_is_clean(self):
        s = {_p("bot_state.json"): (10, 100)}
        created, tablets, modified = cf._classify(s, dict(s), TR)
        assert (created, tablets, modified) == ([], [], [])

    def test_new_file_is_created(self):
        before = {}
        after = {_p("feature_telemetry.json"): (10, 100)}
        created, tablets, modified = cf._classify(before, after, TR)
        assert created == [_p("feature_telemetry.json")]
        assert not tablets and not modified

    def test_changed_size_is_modified(self):
        before = {_p("bot_state.json"): (10, 100)}
        after = {_p("bot_state.json"): (99, 100)}
        _c, _t, modified = cf._classify(before, after, TR)
        assert modified == [_p("bot_state.json")]

    def test_changed_mtime_alone_is_modified(self):
        """Same size, rewritten content -- the reservation_state.json
        autosave shape."""
        before = {_p("reservation_state.json"): (10, 100)}
        after = {_p("reservation_state.json"): (10, 200)}
        _c, _t, modified = cf._classify(before, after, TR)
        assert modified == [_p("reservation_state.json")]

    def test_removal_is_reported(self):
        before = {_p("gone.json"): (1, 1)}
        _c, _t, modified = cf._classify(before, {}, TR)
        assert modified == [f"{_p('gone.json')} (REMOVED)"]

    @pytest.mark.parametrize("kind", ["created", "modified", "removed"])
    def test_any_stone_tablet_change_is_segregated(self, kind):
        """The archive is immutable: create, modify and delete must all
        land in tablet_touched, never in the softer buckets."""
        tab = str(Path(TR) / "BTC_5m_2026.json")
        if kind == "created":
            before, after = {}, {tab: (1, 1)}
        elif kind == "modified":
            before, after = {tab: (1, 1)}, {tab: (2, 2)}
        else:
            before, after = {tab: (1, 1)}, {}
        created, tablets, modified = cf._classify(before, after, TR)
        assert tablets == [tab], f"{kind} tablet change not segregated"
        assert not created and not modified

    def test_tablet_and_ordinary_changes_do_not_bleed(self):
        tab = str(Path(TR) / "ETH_5m_2026.json")
        before = {}
        after = {tab: (1, 1), _p("new.json"): (1, 1)}
        created, tablets, modified = cf._classify(before, after, TR)
        assert tablets == [tab]
        assert created == [_p("new.json")]


# ── the two real breaches, replayed ─────────────────────────────────

class TestRegressionOfRealBreaches:
    """Both shipped defects, expressed as snapshot diffs. The pre-CV1
    guard reported neither, because both are under ~/.acervator."""

    def test_feature_telemetry_creation_is_caught(self):
        before = {}
        after = {_p("feature_telemetry.json"): (512, 1)}
        created, _t, _m = cf._classify(before, after, TR)
        assert created, "the feature_telemetry breach must be detected"

    def test_reservation_state_autosave_is_caught(self):
        before = {_p("reservation_state.json"): (6_500_000, 1)}
        after = {_p("reservation_state.json"): (6_600_000, 2)}
        _c, _t, modified = cf._classify(before, after, TR)
        assert modified, "the sim capital-registry autosave must be detected"


# ── injectability ───────────────────────────────────────────────────

def test_live_roots_is_injectable(monkeypatch, tmp_path):
    """The guard must be redirectable, or it can only be exercised by
    damaging the thing it protects."""
    fake = (tmp_path / "a", tmp_path / "b")
    monkeypatch.setattr(cf, "_live_roots", lambda: fake)
    assert cf._live_roots() == fake


def _fixture_func(fix):
    """Unwrap a pytest fixture back to the plain generator function."""
    for attr in ("__wrapped__", "__pytest_wrapped__"):
        obj = getattr(fix, attr, None)
        if obj is not None:
            return getattr(obj, "obj", obj)
    return fix


class TestFixtureIsActuallyArmed:
    """End-to-end, not just the pure helpers.

    A green suite proves the guard did not FIRE; it does not prove the
    guard is WIRED. These drive the session fixture's generator directly
    against a fake root, so a future refactor that leaves _classify
    perfect but stops calling it still fails here.
    """

    def _drive(self, monkeypatch, roots, tablet_root, mutate):
        monkeypatch.setattr(cf, "_live_roots", lambda: roots)
        monkeypatch.setattr(cf, "_stone_tablet_root", lambda: tablet_root)
        # No live app, so modifications are strict.
        monkeypatch.setattr(cf, "_live_app_running", lambda: False)
        gen = _fixture_func(cf._assert_no_live_tree_writes)(None)
        next(gen)                 # before-snapshot
        mutate()
        try:
            next(gen)             # after-snapshot + assertions
        except StopIteration:
            return None           # fixture completed without complaint
        return None

    def test_created_file_fails_the_session(self, monkeypatch, tmp_path):
        root = tmp_path / "acervator"
        root.mkdir()
        with pytest.raises(AssertionError, match="created"):
            self._drive(monkeypatch, (root,), tmp_path / "tablets",
                        lambda: (root / "leaked.json").write_text(
                            "{}", encoding="utf-8"))

    def test_touched_tablet_fails_the_session(self, monkeypatch, tmp_path):
        root = tmp_path / "acervator"
        tablets = root / "stone_tablets"
        tablets.mkdir(parents=True)
        tab = tablets / "BTC_5m_2026.json"
        tab.write_text("[]", encoding="utf-8")
        with pytest.raises(AssertionError, match="immutable"):
            self._drive(monkeypatch, (root,), tablets,
                        lambda: tab.write_text("[1]", encoding="utf-8"))

    def test_clean_session_passes(self, monkeypatch, tmp_path):
        root = tmp_path / "acervator"
        root.mkdir()
        (root / "untouched.json").write_text("{}", encoding="utf-8")
        self._drive(monkeypatch, (root,), tmp_path / "tablets",
                    lambda: None)      # must not raise

    def test_modification_is_tolerated_when_live_app_is_up(
            self, monkeypatch, tmp_path):
        """Rule 3: the operator running Acervator must not fail the suite."""
        root = tmp_path / "acervator"
        root.mkdir()
        f = root / "bot_state.json"
        f.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(cf, "_live_roots", lambda: (root,))
        monkeypatch.setattr(cf, "_stone_tablet_root",
                            lambda: tmp_path / "tablets")
        monkeypatch.setattr(cf, "_live_app_running", lambda: True)
        gen = _fixture_func(cf._assert_no_live_tree_writes)(None)
        next(gen)
        f.write_text('{"bots": {}}', encoding="utf-8")
        try:
            next(gen)              # must NOT raise
        except StopIteration:
            pass


def test_live_app_detection_never_raises(monkeypatch):
    """psutil is optional; its absence must not fail a suite run."""
    import builtins
    real_import = builtins.__import__

    def no_psutil(name, *a, **kw):
        if name == "psutil":
            raise ImportError("simulated: psutil not installed")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_psutil)
    assert cf._live_app_running() is False
