"""Market Inspector proposals reach Nuclear for stress testing.

OPERATOR, 2026-08-07: Nuclear "is supposed to be able to receive strategy
injections from the Market Inspector to test the strategy propagation function
and swarm topologies under cycling load."

`NuclearFleetController.set_topologies` has existed with ZERO callers, so the
proposal branch of `_topology_pairs` never ran — which is precisely why the
fabricated circular fallback below it survived for so long (deleted v3.24.76).

THE SAFETY LINE THIS FILE DEFENDS.

Market Inspector already has an ADOPT path: `_PreviewDialog.adoptClicked` →
`TopologyPane.adoptRequested` → `MainWindow._adopt_topology_proposal`, which
creates REAL BOTS and REAL WIRES on the live fleet.

Stressing a proposal in Nuclear must be a completely separate journey. Nuclear
is a simulator mode: it may READ a proposal and wire it across SIM bots, and it
must never reach the adopt orchestrator. A stress run that quietly created live
bots would be the worst defect this cascade could ship — so the pins below
assert the separation, not just the connection.

NOTE ON NUMBERS. Fixtures here are small synthetic proposals. The operator's
real fleet is 35 bots / 40 persisted wires; nothing here touches it.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PANEL = REPO_ROOT / "src/gui/simulator_tab/nuclear_mode_panel.py"
MAIN = REPO_ROOT / "src/gui/main_window.py"

PROPOSAL = {
    "id": "ring:BTC-ETH",
    "archetype": "ring",
    "title": "test fixture proposal",
    "score": 71.0,
    "assets": ["BTC", "ETH"],
    "bots": [],
    "wires": [{"source_asset": "BTC", "target_asset": "ETH", "pct": 15.0}],
}


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel_parent(qapp):
    """Owns every panel built here — see test_nuclear_panel_drives_v2 for the
    SIGSEGV this prevents."""
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    yield holder
    holder.setParent(None)
    holder.deleteLater()


def _panel(parent, topo_getter=None):
    from src.gui.simulator_tab.nuclear_mode_panel import NuclearModePanel

    p = NuclearModePanel(
        activity_log_cb=lambda _m: None,
        perf_log_cb=lambda _m: None,
        async_loop_getter=lambda: None,
        parent=parent,
    )
    if topo_getter is not None:
        p.set_topology_getter(topo_getter)
    return p


class TestTheProposalsAreReadableWithoutAdopting:
    def test_the_pane_exposes_its_current_proposals(self, qapp):
        from src.gui.market_inspector_topologies import MarketInspectorTopologies

        pane = MarketInspectorTopologies()
        pane.set_proposal_source(lambda: [dict(PROPOSAL)])
        pane.refresh()
        assert pane.current_proposals() == [PROPOSAL]

    def test_the_accessor_hands_back_a_copy(self, qapp):
        """A consumer must not be able to mutate the pane's list — the
        Nuclear path reads it every Start."""
        from src.gui.market_inspector_topologies import MarketInspectorTopologies

        pane = MarketInspectorTopologies()
        pane.set_proposal_source(lambda: [dict(PROPOSAL)])
        pane.refresh()
        got = pane.current_proposals()
        got.clear()
        assert len(pane.current_proposals()) == 1

    def test_it_is_empty_before_a_refresh(self, qapp):
        """POSITIVE CONTROL — if it returned proposals unconditionally the
        assertions above would pass without the wiring working."""
        from src.gui.market_inspector_topologies import MarketInspectorTopologies

        assert MarketInspectorTopologies().current_proposals() == []


class TestTheSeamReachesNuclear:
    def test_the_panel_accepts_a_topology_getter(self, panel_parent):
        panel = _panel(panel_parent, topo_getter=lambda: [dict(PROPOSAL)])
        assert panel._topology_getter is not None

    def test_it_resolves_proposals_at_start(self, panel_parent):
        panel = _panel(panel_parent, topo_getter=lambda: [dict(PROPOSAL)])
        assert panel._resolve_topologies() == [PROPOSAL]

    def test_a_failing_getter_degrades_to_none(self, panel_parent):
        """A broken Market Inspector must cost the soak its injection, not
        its ability to run."""

        def _boom():
            raise RuntimeError("inspector exploded")

        panel = _panel(panel_parent, topo_getter=_boom)
        assert panel._resolve_topologies() == []

    def test_no_getter_means_no_injection(self, panel_parent):
        assert _panel(panel_parent)._resolve_topologies() == []

    def test_set_topologies_has_a_production_caller(self):
        names = {
            getattr(n.func, "attr", None)
            for n in ast.walk(ast.parse(PANEL.read_text(encoding="utf-8")))
            if isinstance(n, ast.Call)
        }
        assert (
            "set_topologies" in names
        ), "the injection seam is still unwired at the panel"

    def test_main_window_supplies_the_getter(self):
        names = {
            getattr(n.func, "attr", None)
            for n in ast.walk(ast.parse(MAIN.read_text(encoding="utf-8")))
            if isinstance(n, ast.Call)
        }
        assert "set_topology_getter" in names, (
            "MainWindow never hands Market Inspector proposals to the " "Simulator tab"
        )


class TestTheInjectionRoutesTheProposalsWires:
    def test_an_injected_proposal_supplies_the_pairs(self):
        from src.simulator.nuclear_fleet_controller import (
            NuclearFleetController,
        )

        ctl = NuclearFleetController()
        ctl._configs = [
            {
                "mode": "scrumming",
                "symbol": "BTC/USD",
                "target_asset": "BTC",
                "_src_bot_id": "aaaa1111",
            },
            {
                "mode": "scrumming",
                "symbol": "ETH/USD",
                "target_asset": "ETH",
                "_src_bot_id": "bbbb2222",
            },
        ]
        ctl.set_topologies([dict(PROPOSAL)])
        assert ctl._topology_pairs(["aaaa1111", "bbbb2222"]) == [
            ("aaaa1111", "bbbb2222", 15.0)
        ]


class TestTheStressPathNeverAdoptsLiveBots:
    """THE SAFETY PINS. Adopting creates real bots on the live fleet."""

    def test_the_panel_never_references_the_adopt_orchestrator(self):
        src = PANEL.read_text(encoding="utf-8")
        names = {
            getattr(n.func, "attr", None)
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
        }
        forbidden = names & {
            "_adopt_topology_proposal",
            "set_adopt_handler",
            "adoptRequested",
            "create_bot",
            "add_bot",
        }
        assert (
            not forbidden
        ), f"the Nuclear stress path can reach live bot creation: {forbidden}"

    def test_the_adopt_handler_still_points_at_main_window(self):
        """NEGATIVE CONTROL — the live adopt journey must remain intact and
        separate. If this breaks, the separation was achieved by removing
        adoption rather than by keeping the two apart."""
        src = MAIN.read_text(encoding="utf-8")
        found = [
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == "set_adopt_handler"
        ]
        assert found, "the live adopt wiring disappeared"

    def test_the_controller_only_reads_wires_from_a_proposal(self):
        """`_topology_pairs` may consume `wires`. It must not consume
        `bots` — that key is the adopt path's instruction to CREATE bots,
        and a stress run instantiates only the fleet from bot_state."""
        from src.simulator.nuclear_fleet_controller import (
            NuclearFleetController,
        )

        src = ast.parse(
            (REPO_ROOT / "src/simulator/nuclear_fleet_controller.py").read_text(
                encoding="utf-8"
            )
        )
        fn = next(
            n
            for n in ast.walk(src)
            if isinstance(n, ast.FunctionDef) and n.name == "_topology_pairs"
        )
        keys = {
            n.args[0].value
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == "get"
            and n.args
            and isinstance(n.args[0], ast.Constant)
        }
        assert "bots" not in keys, (
            "the stress path reads the proposal's `bots` key, which is the "
            "adopt path's create-these-bots instruction"
        )
        assert NuclearFleetController is not None
