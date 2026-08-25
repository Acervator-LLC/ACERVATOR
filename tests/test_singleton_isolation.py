"""Sim paths must fail CLOSED on isolation — CV1 (part 3).

Method rule M10: any sim path that cannot obtain its private bus,
registry or telemetry sink must ABORT with an operator-visible reason.
Silent fallback to a process-wide singleton is the failure mode that has
shipped twice.

`_make_sim_capital_registry()` did the opposite. It caught every
exception, logged a warning, and returned None — and its own comment
said so plainly:

    # a replay; falling back to None means the bot resolves the
    # global singleton, which is the pre-v3.24.31 behaviour.

`ScrummingBot._crr` then resolves the process-wide registry, which
autosaves to ~/.acervator/reservation_state.json. So one
`tempfile.mkdtemp` failure silently reinstated the exact defect
v3.24.31 removed. The documented cost is recorded at
scrumming_bot.py:1053-1063: 16,558 bot_ids against 35 real ones, 16,523
orphans, 6.5 MB of sim residue feeding live allocation decisions.

The existing tests/test_sim_reservation_isolation.py covers the happy
path — not the singleton, not autosaving, path outside the runtime
tree, independent per replay. None of them exercise the failure branch,
which is why a fail-open sat there unnoticed.
"""

from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E402
    _make_sim_capital_registry,
)

SIM_DIRS = [
    REPO_ROOT / "src" / "gui" / "simulator_tab",
]

# Resolvers that hand back process-wide, LIVE-PERSISTING state, keyed by
# the module they come from.
#
# The module matters. A first draft keyed on the bare name `get_registry`
# and immediately flagged two false positives --
# fleet_replay_panel.py:690 and nuclear_fleet_controller.py:305 -- both
# of which import `get_registry` from `stone_tablets`, whose registry is
# a READ-ONLY tablet index and entirely legitimate for sim. A guard that
# cannot tell those apart gets switched off.
LIVE_SINGLETONS = {
    ("event_bus", "get_event_bus"),
    ("capital_reservation", "get_registry"),
    ("state_manager", "StateManager"),
}
_LIVE_NAMES = {name for _mod, name in LIVE_SINGLETONS}


class TestFailsClosed:
    """M10. The whole point of this file."""

    def test_raises_rather_than_returning_none_when_isolation_fails(self, monkeypatch):
        """Force the private-registry construction to fail.

        Before the fix this returned None, and None means the bot
        resolves the live autosaving registry.
        """

        def boom(*_a, **_kw):
            raise OSError("simulated: cannot create temp dir")

        monkeypatch.setattr(tempfile, "mkdtemp", boom)
        with pytest.raises(Exception) as exc:
            _make_sim_capital_registry()
        assert (
            "isolation" in str(exc.value).lower()
            or "registry" in str(exc.value).lower()
        ), f"the abort must say WHY, got: {exc.value!r}"

    def test_never_returns_none_on_the_happy_path(self):
        assert _make_sim_capital_registry() is not None


class TestInjectedRegistryWins:
    def test_crr_returns_the_injected_registry(self):
        """The positive half: when a private registry IS supplied, the
        bot must use it rather than the singleton."""
        import inspect
        from src.trading import scrumming_bot as sb

        src = inspect.getsource(
            sb.ScrummingBot._crr.fget
            if isinstance(sb.ScrummingBot._crr, property)
            else sb.ScrummingBot._crr
        )
        assert (
            "_capital_registry is not None" in src
        ), "_crr no longer prefers the injected registry"


class TestNoSimPathResolvesALiveSingleton:
    """Structural guard.

    Currently passing — grep for get_event_bus / get_registry /
    StateManager under src/gui/simulator_tab/ returns nothing. Pinned so
    it stays that way: the leaks this project has shipped were INDIRECT
    (constructing a live class whose __init__ subscribes to the global
    bus), and a direct call would be the easy version of the same
    mistake.
    """

    def _sim_modules(self) -> list[Path]:
        out: list[Path] = []
        for d in SIM_DIRS:
            out.extend(p for p in d.rglob("*.py") if "__pycache__" not in p.parts)
        return sorted(out)

    def test_sim_modules_exist(self):
        """Positive control: an empty file list would make the guard
        below pass by finding nothing to check."""
        mods = self._sim_modules()
        assert len(mods) >= 5, f"expected the sim package, found {mods}"

    @staticmethod
    def _live_bindings(tree: ast.AST) -> dict[str, str]:
        """Local name -> live module it was imported from.

        Only names imported from a module in LIVE_SINGLETONS count, so
        `from stone_tablets import get_registry` is correctly ignored.
        """
        found: dict[str, str] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            tail = (node.module or "").rsplit(".", 1)[-1]
            for alias in node.names:
                for mod, name in LIVE_SINGLETONS:
                    if tail == mod and alias.name == name:
                        found[alias.asname or alias.name] = mod
        return found

    def test_no_sim_module_calls_a_live_singleton_resolver(self):
        offenders: list[str] = []
        for p in self._sim_modules():
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except (SyntaxError, OSError):
                continue
            bindings = self._live_bindings(tree)
            if not bindings:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None)
                if name in bindings:
                    offenders.append(
                        f"{p.relative_to(REPO_ROOT)}:{node.lineno} -> "
                        f"{name}() from {bindings[name]}"
                    )
        assert not offenders, (
            "sim path(s) resolve process-wide live state:\n  "
            + "\n  ".join(offenders)
            + "\n\nSim must construct its own private instance and abort "
            "if it cannot (M10)."
        )

    def test_the_guard_can_actually_see_an_offender(self, tmp_path):
        """Positive control.

        The test above passes today. Without this, an import-matching bug
        that made `_live_bindings` always return {} would look identical
        to a clean tree -- which is precisely how the first draft's
        false positives got traded for silent blindness.
        """
        bad = tmp_path / "leaky_sim_module.py"
        bad.write_text(
            "from src.trading.capital_reservation import get_registry\n"
            "def go():\n"
            "    return get_registry()\n",
            encoding="utf-8",
        )
        tree = ast.parse(bad.read_text(encoding="utf-8"))
        bindings = self._live_bindings(tree)
        assert bindings == {"get_registry": "capital_reservation"}
        calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) in bindings
        ]
        assert calls, "guard failed to flag a deliberately leaky module"

    def test_the_guard_ignores_the_stone_tablet_registry(self, tmp_path):
        """Negative control: the read-only tablet index must not trip it.

        This is the exact shape of the two real false positives --
        fleet_replay_panel.py:690 and nuclear_fleet_controller.py:305.
        """
        ok = tmp_path / "tablet_reader.py"
        ok.write_text(
            "from src.trading.stone_tablets import get_registry\n"
            "def go():\n"
            "    return get_registry()\n",
            encoding="utf-8",
        )
        tree = ast.parse(ok.read_text(encoding="utf-8"))
        assert self._live_bindings(tree) == {}
