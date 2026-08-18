"""Nuclear Mode must abort NAMED, not with a bare traceback (C15 step 2).

`_make_sim_capital_registry` raises as of v3.24.35 (CV1).
`nuclear_controller.py:355` called it unguarded, inline in a
`ScrummingBot(...)` argument list, from inside a Qt slot. A mkdtemp
failure therefore aborted Nuclear Mode start with a bare traceback: the
operator sees the panel do nothing and is told nothing.

The methodology's own correction note flagged this exact site — "a
second production caller the plan's file list omits" — and warned that
making the factory raise without handling it "would abort Nuclear Mode
with a bare traceback, the opposite of the goal".

Aborting remains correct. Losing a Nuclear run is cheap; corrupting the
operator's live reservation state is not. What this pins is that the
abort NAMES its cause.

Also pinned here: the replay-start isolation assertion (C15 step 5),
which verifies the OUTCOME the three upstream guards exist to produce
rather than any one of their paths.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

NUCLEAR = (REPO_ROOT / "src" / "gui" / "simulator_tab"
           / "nuclear_controller.py")
REPLAY = (REPO_ROOT / "src" / "gui" / "simulator_tab" / "fleet"
          / "fleet_replay_controller.py")


def _fn(path: Path, name: str):
    src = path.read_text(encoding="utf-8")
    return next(n for n in ast.walk(ast.parse(src))
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == name), src


class TestTheNuclearCallSiteIsGuarded:
    def test_the_factory_is_not_called_inline_in_the_constructor(self):
        """POSITIVE CONTROL for the shape of the fix: the raising call
        must not sit in a `ScrummingBot(...)` argument list, where no
        handler can reach it."""
        fn, src = _fn(NUCLEAR, "_construct_scout")
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call):
                continue
            if getattr(call.func, "id", "") != "ScrummingBot":
                continue
            for kw in call.keywords:
                if kw.arg == "capital_registry":
                    seg = ast.get_source_segment(src, kw.value) or ""
                    assert "_make_sim_capital_registry" not in seg, (
                        "the raising factory is still called inline in "
                        "the ScrummingBot argument list")

    def test_the_factory_call_is_inside_a_try(self):
        fn, _ = _fn(NUCLEAR, "_construct_scout")
        guarded = []
        for node in ast.walk(fn):
            if isinstance(node, ast.Try):
                for inner in ast.walk(node):
                    if (isinstance(inner, ast.Call)
                            and getattr(inner.func, "id", "")
                            == "_make_sim_capital_registry"):
                        guarded.append(inner.lineno)
        assert guarded, "_make_sim_capital_registry is called unguarded"

    def test_the_abort_names_the_cause(self):
        """A RuntimeError whose message says nothing is a traceback with
        extra steps."""
        fn, src = _fn(NUCLEAR, "_construct_scout")
        raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
        assert raises, "the guard swallows the failure instead of aborting"
        blob = " ".join((ast.get_source_segment(src, r) or "")
                        for r in raises).lower()
        assert "nuclear" in blob, "the abort does not say what failed"
        assert "reservation_state" in blob or "registry" in blob, (
            "the abort does not say WHY it refuses to continue")

    def test_it_still_aborts_rather_than_continuing(self):
        """NEGATIVE CONTROL. Catching the error and carrying on with the
        process-wide registry would be strictly worse than the bare
        traceback this replaces."""
        fn, src = _fn(NUCLEAR, "_construct_scout")
        seg = ast.get_source_segment(src, fn) or ""
        assert "get_registry()" not in seg, (
            "Nuclear must never fall back to the process-wide registry")


class TestReplayAssertsIsolationBeforeRunning:
    def test_the_assertion_exists(self):
        fn, _ = _fn(REPLAY, "_assert_capital_isolation")
        assert fn is not None

    def test_it_is_called_from_the_construction_path(self):
        """An assertion nothing invokes verifies nothing."""
        src = REPLAY.read_text(encoding="utf-8")
        calls = [n for n in ast.walk(ast.parse(src))
                 if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "") == "_assert_capital_isolation"]
        assert calls, "_assert_capital_isolation is never called"

    def test_it_flags_a_bot_on_the_live_registry(self):
        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            FleetReplayController)
        from src.trading.capital_reservation import get_registry

        ctl = object.__new__(FleetReplayController)
        leaked = type("B", (), {"bot_id": "leak",
                                "_capital_registry": get_registry()})()
        ctl._bots = [leaked]
        ctl._activity = lambda *a, **k: None
        with pytest.raises(RuntimeError) as ei:
            ctl._assert_capital_isolation()
        assert "isolation breached" in str(ei.value)
        assert "leak" in str(ei.value), "the offending bot is not named"

    def test_it_flags_a_bot_with_no_registry_at_all(self):
        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            FleetReplayController)

        ctl = object.__new__(FleetReplayController)
        ctl._bots = [type("B", (), {"bot_id": "none",
                                    "_capital_registry": None})()]
        ctl._activity = lambda *a, **k: None
        with pytest.raises(RuntimeError):
            ctl._assert_capital_isolation()

    def test_it_passes_on_properly_isolated_bots(self):
        """NEGATIVE CONTROL: a guard that always fires blocks every
        replay and would be removed within a day."""
        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            FleetReplayController, _make_sim_capital_registry)

        ctl = object.__new__(FleetReplayController)
        ctl._bots = [type("B", (), {
            "bot_id": f"ok{i}",
            "_capital_registry": _make_sim_capital_registry()})()
            for i in range(3)]
        seen = []
        ctl._activity = lambda msg, *a, **k: seen.append(msg)
        ctl._assert_capital_isolation()
        assert any("isolation verified" in s for s in seen), (
            "a clean run should say so; silence reads as 'not checked'")

    def test_an_empty_fleet_does_not_raise(self):
        from src.gui.simulator_tab.fleet.fleet_replay_controller import (
            FleetReplayController)

        ctl = object.__new__(FleetReplayController)
        ctl._bots = []
        ctl._activity = lambda *a, **k: None
        ctl._assert_capital_isolation()
