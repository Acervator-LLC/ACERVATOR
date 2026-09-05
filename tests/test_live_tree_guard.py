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

import contextlib
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFTEST = REPO_ROOT / "tests" / "conftest.py"


def _load_conftest():
    spec = importlib.util.spec_from_file_location("conftest_under_test", CONFTEST)
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


def _drive_guard(monkeypatch, roots, tablet_root, mutate, *, live_app=False):
    """Run ``_assert_no_live_tree_writes`` over `roots`, calling `mutate` inside it.

    ``TEST_HOME_ENV`` is cleared, so `live_app` alone decides what the guard
    treats as unattributable.
    """
    monkeypatch.delenv(cf.TEST_HOME_ENV, raising=False)
    monkeypatch.setattr(cf, "_live_roots", lambda: roots)
    monkeypatch.setattr(cf, "_stone_tablet_root", lambda: tablet_root)
    monkeypatch.setattr(cf, "_live_app_running", lambda: live_app)
    gen = _fixture_func(cf._assert_no_live_tree_writes)(None)
    next(gen)  # before-snapshot
    mutate()
    with contextlib.suppress(StopIteration):
        next(gen)  # after-snapshot + assertions


class TestFixtureIsActuallyArmed:
    """End-to-end, not just the pure helpers.

    A green suite proves the guard did not FIRE; it does not prove the
    guard is WIRED. These drive the session fixture's generator directly
    against a fake root, so a future refactor that leaves _classify
    perfect but stops calling it still fails here.
    """

    def _drive(self, monkeypatch, roots, tablet_root, mutate):
        # No live app, so modifications are strict.
        _drive_guard(monkeypatch, roots, tablet_root, mutate, live_app=False)

    def test_created_file_fails_the_session(self, monkeypatch, tmp_path):
        root = tmp_path / "acervator"
        root.mkdir()
        with pytest.raises(AssertionError, match="created"):
            self._drive(
                monkeypatch,
                (root,),
                tmp_path / "tablets",
                lambda: (root / "leaked.json").write_text("{}", encoding="utf-8"),
            )

    def test_touched_tablet_fails_the_session(self, monkeypatch, tmp_path):
        root = tmp_path / "acervator"
        tablets = root / "stone_tablets"
        tablets.mkdir(parents=True)
        tab = tablets / "BTC_5m_2026.json"
        tab.write_text("[]", encoding="utf-8")
        with pytest.raises(AssertionError, match="immutable"):
            self._drive(
                monkeypatch,
                (root,),
                tablets,
                lambda: tab.write_text("[1]", encoding="utf-8"),
            )

    def test_clean_session_passes(self, monkeypatch, tmp_path):
        root = tmp_path / "acervator"
        root.mkdir()
        (root / "untouched.json").write_text("{}", encoding="utf-8")
        self._drive(
            monkeypatch, (root,), tmp_path / "tablets", lambda: None
        )  # must not raise

    def test_modification_is_tolerated_when_live_app_is_up(self, monkeypatch, tmp_path):
        """Rule 3: the operator running Acervator must not fail the suite."""
        root = tmp_path / "acervator"
        root.mkdir()
        f = root / "bot_state.json"
        f.write_text("{}", encoding="utf-8")
        monkeypatch.delenv(cf.TEST_HOME_ENV, raising=False)
        monkeypatch.setattr(cf, "_live_roots", lambda: (root,))
        monkeypatch.setattr(cf, "_stone_tablet_root", lambda: tmp_path / "tablets")
        monkeypatch.setattr(cf, "_live_app_running", lambda: True)
        gen = _fixture_func(cf._assert_no_live_tree_writes)(None)
        next(gen)
        f.write_text('{"bots": {}}', encoding="utf-8")
        try:
            next(gen)  # must NOT raise
        except StopIteration:
            pass

    def test_a_redirected_home_fails_a_modification_with_the_app_up(
        self, monkeypatch, tmp_path
    ):
        """The same modification the test above excuses must fail here.

        A live Acervator writes only the operator's real home, so under
        ACERVATOR_TEST_HOME the suite is the only possible author.
        """
        root = tmp_path / "acervator"
        root.mkdir()
        f = root / "bot_state.json"
        f.write_text("{}", encoding="utf-8")
        monkeypatch.setenv(cf.TEST_HOME_ENV, str(tmp_path))
        monkeypatch.setattr(cf, "_live_roots", lambda: (root,))
        monkeypatch.setattr(cf, "_stone_tablet_root", lambda: tmp_path / "tablets")
        monkeypatch.setattr(cf, "_live_app_running", lambda: True)
        gen = _fixture_func(cf._assert_no_live_tree_writes)(None)
        next(gen)
        f.write_text('{"bots": {}}', encoding="utf-8")
        with pytest.raises(AssertionError, match="modified"):
            next(gen)


# ── redirected home ─────────────────────────────────────────────────


def test_the_redirect_reads_the_variable_on_every_call(monkeypatch, tmp_path):
    """The guard bound the variable once instead of reading it live."""
    monkeypatch.delenv(cf.TEST_HOME_ENV, raising=False)
    assert cf._home_is_redirected() is False
    monkeypatch.setenv(cf.TEST_HOME_ENV, str(tmp_path))
    assert cf._home_is_redirected() is True


def test_the_variable_moves_the_home_directory(monkeypatch, tmp_path):
    """conftest read ACERVATOR_TEST_HOME and left Path.home() alone."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("USERPROFILE", str(elsewhere))
    monkeypatch.setenv("HOME", str(elsewhere))
    assert Path.home() == elsewhere
    throwaway = tmp_path / "throwaway"
    monkeypatch.setenv(cf.TEST_HOME_ENV, str(throwaway))
    _load_conftest()
    assert Path.home() == throwaway


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


# ── the three rules, with a live application up ─────────────────────


def _redirected_root(tmp_path):
    """A throwaway ``.acervator`` root, named as the live one so the
    ``_LIVE_APP_CREATES`` keys resolve against it."""
    root = tmp_path / ".acervator"
    root.mkdir()
    return root


class TestCreationAndTabletsCarryNoLiveAppExcuse:
    """Rules 1 and 2 fail whether or not Acervator is running.

    Every test drives the session fixture with ``_live_app_running`` true and
    the watched roots redirected into ``tmp_path``.
    """

    def test_a_created_path_fails_while_the_app_runs(self, monkeypatch, tmp_path):
        root = _redirected_root(tmp_path)
        with pytest.raises(AssertionError, match="created"):
            _drive_guard(
                monkeypatch,
                (root,),
                root / "stone_tablets",
                lambda: (root / "leaked.json").write_text("{}", encoding="utf-8"),
                live_app=True,
            )

    def test_a_topology_snapshot_fails_while_the_app_runs(self, monkeypatch, tmp_path):
        """The shape that got through: an adopt test wrote two files into
        ``topology_snapshots`` and the suite stayed green."""
        root = _redirected_root(tmp_path)
        snaps = root / "topology_snapshots"
        snaps.mkdir()
        with pytest.raises(AssertionError, match="created"):
            _drive_guard(
                monkeypatch,
                (root,),
                root / "stone_tablets",
                lambda: (snaps / "wires_before_adopt.20260905_073313.json").write_text(
                    "{}", encoding="utf-8"
                ),
                live_app=True,
            )

    def test_a_touched_tablet_fails_while_the_app_runs(self, monkeypatch, tmp_path):
        root = _redirected_root(tmp_path)
        tablets = root / "stone_tablets"
        tablets.mkdir()
        tab = tablets / "BTC_5m_2026.json"
        tab.write_text("[]", encoding="utf-8")
        with pytest.raises(AssertionError, match="immutable"):
            _drive_guard(
                monkeypatch,
                (root,),
                tablets,
                lambda: tab.write_text("[1]", encoding="utf-8"),
                live_app=True,
            )

    def test_a_new_tablet_fails_while_the_app_runs(self, monkeypatch, tmp_path):
        root = _redirected_root(tmp_path)
        tablets = root / "stone_tablets"
        tablets.mkdir()
        with pytest.raises(AssertionError, match="immutable"):
            _drive_guard(
                monkeypatch,
                (root,),
                tablets,
                lambda: (tablets / "ETH_5m_2026.json").write_text(
                    "[]", encoding="utf-8"
                ),
                live_app=True,
            )


class TestModificationKeepsTheLiveAppExcuse:
    """Rule 3 is the one exception, and it still prints."""

    def _state_file(self, tmp_path):
        root = _redirected_root(tmp_path)
        state = root / "bot_state.json"
        state.write_text("{}", encoding="utf-8")
        return root, state

    def test_a_modification_only_prints_while_the_app_runs(
        self, monkeypatch, tmp_path, capsys
    ):
        root, state = self._state_file(tmp_path)
        _drive_guard(
            monkeypatch,
            (root,),
            root / "stone_tablets",
            lambda: state.write_text('{"bots": {}}', encoding="utf-8"),
            live_app=True,
        )
        out = capsys.readouterr().out
        assert "DEGRADED" in out, f"the excused modification was not reported: {out!r}"
        assert state.name in out, f"the report named no file: {out!r}"

    def test_the_same_modification_fails_with_no_app_running(
        self, monkeypatch, tmp_path
    ):
        """Positive control for the test above: the instrument does fail here."""
        root, state = self._state_file(tmp_path)
        with pytest.raises(AssertionError, match="modified"):
            _drive_guard(
                monkeypatch,
                (root,),
                root / "stone_tablets",
                lambda: state.write_text('{"bots": {}}', encoding="utf-8"),
                live_app=False,
            )


class TestTheLiveAppExcuseIsNamedAndConditional:
    """``_LIVE_APP_CREATES`` covers the listed locations and nothing else."""

    def test_a_listed_path_is_excused_while_the_app_runs(
        self, monkeypatch, tmp_path, capsys
    ):
        root = _redirected_root(tmp_path)
        snaps = root / "ta_snapshots"
        snaps.mkdir()
        _drive_guard(
            monkeypatch,
            (root,),
            root / "stone_tablets",
            lambda: (snaps / "7c39c7a2.ff6d62e7.json").write_text(
                "{}", encoding="utf-8"
            ),
            live_app=True,
        )
        out = capsys.readouterr().out
        assert "EXCUSED" in out, f"an excused creation went unreported: {out!r}"
        assert "indicator_panel" in out, f"the report named no writer: {out!r}"

    def test_the_same_listed_path_fails_with_no_app_running(
        self, monkeypatch, tmp_path
    ):
        """Positive control: nothing is excused once the application is closed."""
        root = _redirected_root(tmp_path)
        snaps = root / "ta_snapshots"
        snaps.mkdir()
        with pytest.raises(AssertionError, match="created"):
            _drive_guard(
                monkeypatch,
                (root,),
                root / "stone_tablets",
                lambda: (snaps / "7c39c7a2.ff6d62e7.json").write_text(
                    "{}", encoding="utf-8"
                ),
                live_app=False,
            )

    def test_a_listed_directory_answers_with_its_writer(self, tmp_path):
        root = tmp_path / ".acervator"
        reason = cf._excused_by_the_live_app(
            str(root / "ta_snapshots" / "a.b.json"), (root,)
        )
        assert "indicator_panel" in reason, reason

    @pytest.mark.parametrize(
        ("root_name", "rest"),
        [
            (".acervator", "preflight/20260904_160358.stamp"),
            (".acervator", "preflight/bot_state.20260904_160358.json"),
            (".acervator", "ta_snapshots/7c39c7a2.ff6d62e7.json"),
            (".acervator_logs", "trade/pnl/daily/2026-09-05.ndjson"),
            (".acervator_logs", "console_20260904_160357.log"),
            (".acervator_logs", "crash_20260904_160357.log"),
            (".acervator_logs", "faulthandler_20260904_160357.log"),
            (".acervator_logs", "postmortem_20260903_120921/SUMMARY.txt"),
            (".acervator_logs", "postmortem_20260903_120921/crash_20260831_153128.log"),
            (".acervator_logs", "thread_violation_20260627.log"),
        ],
    )
    def test_every_shape_the_running_app_creates_is_covered(
        self, tmp_path, root_name, rest
    ):
        """Each case is a path a running Acervator was measured creating."""
        root = tmp_path / root_name
        path = root.joinpath(*rest.split("/"))
        assert cf._excused_by_the_live_app(str(path), (root,)), rest

    @pytest.mark.parametrize(
        ("root_name", "rest"),
        [
            (".acervator", "bot_state.json"),
            (".acervator", "topology_snapshots/wires_before_adopt.json"),
            (".acervator", "stone_tablets/BTC_5m_2026.json"),
            (".acervator", "reservation_state.json"),
            (".acervator_logs", "trade/gate.log"),
            (".acervator_logs", "sim/runs/run_1/candles.json"),
        ],
    )
    def test_the_rest_of_the_tree_is_never_excused(self, tmp_path, root_name, rest):
        """Negative control for the case above: nothing else matches a key."""
        root = tmp_path / root_name
        path = root.joinpath(*rest.split("/"))
        assert cf._excused_by_the_live_app(str(path), (root,)) == "", rest

    def test_an_unlisted_directory_is_never_excused(self, tmp_path):
        root = tmp_path / ".acervator"
        assert (
            cf._excused_by_the_live_app(
                str(root / "topology_snapshots" / "wires.json"), (root,)
            )
            == ""
        )

    def test_a_name_that_only_starts_like_a_listed_one_is_not_excused(self, tmp_path):
        root = tmp_path / ".acervator"
        assert cf._excused_by_the_live_app(str(root / "preflight.json"), (root,)) == ""

    def test_an_unlisted_path_still_fails_beside_a_listed_one(
        self, monkeypatch, tmp_path, capsys
    ):
        """One excused creation must not carry an unexcused one through."""
        root = _redirected_root(tmp_path)
        snaps = root / "ta_snapshots"
        snaps.mkdir()

        def mutate():
            (snaps / "7c39c7a2.ff6d62e7.json").write_text("{}", encoding="utf-8")
            (root / "leaked.json").write_text("{}", encoding="utf-8")

        with pytest.raises(AssertionError) as caught:
            _drive_guard(
                monkeypatch, (root,), root / "stone_tablets", mutate, live_app=True
            )
        message = str(caught.value)
        assert "leaked.json" in message, message
        assert "created 1 path" in message, message
        assert "EXCUSED" in capsys.readouterr().out


def test_a_clean_run_stays_green_and_silent(monkeypatch, tmp_path, capsys):
    root = _redirected_root(tmp_path)
    (root / "untouched.json").write_text("{}", encoding="utf-8")
    _drive_guard(
        monkeypatch, (root,), root / "stone_tablets", lambda: None, live_app=True
    )
    assert capsys.readouterr().out == ""
