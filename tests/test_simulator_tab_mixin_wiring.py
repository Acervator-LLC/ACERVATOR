"""Drive every guard in ``SimulatorTabMixin._build_simulator_tab`` both ways.

Each ``hasattr`` guard gates one wiring call, so a renamed hook would skip that
call in silence. ``test_the_shipped_simulator_tab_answers_every_guard`` pins the
shipped class against the names the guards check.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from src.gui.main_tabs.simulator_tab import SimulatorTabMixin

GUARDED_SETTERS = (
    "set_connectors_getter",
    "set_bot_manager",
    "set_swarm_getter",
    "set_topology_getter",
)


class FakeTabWidget:
    """Record every ``insertTab`` call the mixin makes."""

    def __init__(self) -> None:
        self.inserted: list[tuple[int, Any, str]] = []

    def insertTab(self, index: int, widget: Any, label: str) -> int:
        self.inserted.append((index, widget, label))
        return index


class FakeInspector:
    """Answer ``current_topology_proposals`` with a fixed list."""

    def __init__(self, proposals: list) -> None:
        self._proposals = proposals

    def current_topology_proposals(self) -> list:
        return self._proposals


class MuteInspector:
    """A market inspector defining no ``current_topology_proposals``."""


class StandInSimulatorTab:
    """Record the guarded setters the mixin calls, and refuse the rest."""

    declares: tuple[str, ...] = GUARDED_SETTERS

    def __init__(self) -> None:
        self.calls: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        if name not in type(self).declares:
            raise AttributeError(name)

        def record(value: Any) -> None:
            self.calls[name] = value

        return record


def make_simulator_tab_class(present: tuple[str, ...]) -> type:
    """Build a ``StandInSimulatorTab`` subclass declaring only ``present``."""
    return type("PartialSimulatorTab", (StandInSimulatorTab,), {"declares": present})


def build_host(
    monkeypatch: pytest.MonkeyPatch,
    present: tuple[str, ...] = GUARDED_SETTERS,
    inspector: Any = None,
) -> Any:
    """Run the real ``_build_simulator_tab`` against a stand-in tab class."""
    module = types.ModuleType("src.gui.simulator_tab")
    module.SimulatorTab = make_simulator_tab_class(present)
    monkeypatch.setitem(sys.modules, "src.gui.simulator_tab", module)

    class Host(SimulatorTabMixin):
        pass

    host = Host()
    host._main_tabs = FakeTabWidget()
    host._bot_manager = object()
    host._market_inspector = FakeInspector([]) if inspector is None else inspector
    host._exchange_connectors = {"coinbase": object()}
    host._bot_viz = object()
    host._build_simulator_tab()
    return host


def test_every_guarded_setter_is_called_when_the_tab_declares_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = build_host(monkeypatch)
    assert sorted(host._simulator.calls) == sorted(GUARDED_SETTERS), (
        "all four hooks are declared, so all four must be wired; "
        f"wired: {sorted(host._simulator.calls)}"
    )


@pytest.mark.parametrize("missing", GUARDED_SETTERS)
def test_a_missing_hook_skips_only_its_own_wiring(
    monkeypatch: pytest.MonkeyPatch, missing: str
) -> None:
    present = tuple(n for n in GUARDED_SETTERS if n != missing)
    host = build_host(monkeypatch, present=present)
    assert missing not in host._simulator.calls, (
        f"{missing} is undeclared, so the guard must refuse it; "
        f"wired: {sorted(host._simulator.calls)}"
    )
    assert sorted(host._simulator.calls) == sorted(present), (
        "the other three hooks are declared and must still be wired; "
        f"wired: {sorted(host._simulator.calls)}"
    )


def test_the_connectors_getter_reads_the_live_connector_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = build_host(monkeypatch)
    getter = host._simulator.calls["set_connectors_getter"]
    assert getter() == host._exchange_connectors


def test_the_bot_manager_is_handed_over_by_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = build_host(monkeypatch)
    assert host._simulator.calls["set_bot_manager"] is host._bot_manager


def test_the_swarm_getter_resolves_the_bot_visualizer_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = build_host(monkeypatch)
    getter = host._simulator.calls["set_swarm_getter"]
    replacement = object()
    host._bot_viz = replacement
    assert getter() is replacement, "the getter must read _bot_viz when called"


def test_the_topology_getter_returns_the_inspector_proposals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposals = [{"name": "ring"}]
    host = build_host(monkeypatch, inspector=FakeInspector(proposals))
    assert host._simulator.calls["set_topology_getter"]() == proposals


def test_the_topology_getter_returns_empty_when_the_inspector_cannot_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = build_host(monkeypatch, inspector=MuteInspector())
    assert host._simulator.calls["set_topology_getter"]() == []


def test_the_tab_is_inserted_under_its_own_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = build_host(monkeypatch)
    assert host._main_tabs.inserted == [(1, host._simulator, "Simulator")]


def test_the_shipped_simulator_tab_answers_every_guard() -> None:
    from src.gui.simulator_tab import SimulatorTab

    missing = [n for n in GUARDED_SETTERS if not hasattr(SimulatorTab, n)]
    assert missing == [], (
        "a guard whose name the shipped class lacks skips its wiring in "
        f"silence; missing: {missing}"
    )
