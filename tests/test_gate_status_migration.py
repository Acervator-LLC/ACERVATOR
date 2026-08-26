"""The gate status display lives in its own pane, and loses no rows.

Operator task 2026-08-08 (screenshot area 2): "Migrate the gate status
display to where the Simulator Performance Log currently lives."

WHY AN EMITTER FIRST. The render path had only `feature_telemetry`,
which counts calls and skips and carries no expected-vs-actual. A
migration that silently painted FEWER rows would have looked identical
to one that worked. `sim.06.012.postcondition.gate_status.rendered` carries `expected` (bots
reporting gate state), `actual` (rows painted) and `host` (where they
painted) -- so the move is checkable and so is its completeness.

The display was column 3 of the fleet table, one `GateLightsCell` per
row. A ten-LED labelled row inside a table cell is bounded by the column
width, which is why the labels stayed cramped even after v3.24.18
measured the pitch correctly. This is a MOVE: the same `GateLightsCell`
draws, and `update_gates` keeps its signature, so the colour semantics
the operator reads are untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def _destroy_widgets():
    """Delete every top-level widget after each test.

    These tests build whole SimulatorTab / FleetReplayPanel trees. Qt
    keeps a parentless widget alive for the life of the process, so
    without this they accumulate across the suite until the run dies
    with a segfault (exit 139, and once 127) partway through -- no
    failure summary, just truncated output. The crash point moved
    between runs, which is what identified it as accumulation rather
    than one bad test.
    """
    yield
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        return
    app = QApplication.instance()
    if app is None:
        return
    for w in list(app.topLevelWidgets()):
        w.hide()
        w.setParent(None)
        w.deleteLater()
    app.processEvents()


SYMS = ["CHIP/USD", "SPK/USD", "XRP/USD"]


def _qapp():
    """A QApplication, or skip. A plain helper rather than a fixture:
    a fixture consumed only by name-injection reads as dead code to the
    archetype's vulture pass, and a real dead-symbol finding in this
    file would then be lost in the noise."""
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:  # pragma: no cover
        pytest.skip("PySide6 unavailable")
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel():
    _qapp()
    from src.gui.simulator_tab.fleet.sim_visuals import GateStatusPanel

    p = GateStatusPanel()
    p.set_symbols(SYMS)
    return p


class TestThePanelHoldsOneRowPerBot:
    def test_a_row_exists_for_every_symbol(self, panel):
        assert panel.symbols() == sorted(SYMS)

    def test_each_row_is_a_real_gate_cell(self, panel):
        from src.gui.simulator_tab.fleet.sim_visuals import GateLightsCell

        for sym in SYMS:
            assert isinstance(panel.cell_for(sym), GateLightsCell)

    def test_an_unknown_symbol_has_no_cell(self, panel):
        assert panel.cell_for("NOPE/USD") is None

    def test_reload_replaces_rows_rather_than_stacking(self, panel):
        """A second fleet load must not leave the first load's rows
        behind -- the panel would grow without bound across reloads."""
        panel.set_symbols(["BTC/USD"])
        assert panel.symbols() == ["BTC/USD"]
        assert panel.cell_for("CHIP/USD") is None

    def test_an_empty_fleet_clears_the_panel(self, panel):
        panel.set_symbols([])
        assert panel.symbols() == []


class TestTheCellContractIsUnchanged:
    def test_update_gates_still_accepts_the_same_arguments(self, panel):
        """The move must not change how a gate row is driven; the
        snapshot dispatcher calls this exact signature."""
        cell = panel.cell_for("CHIP/USD")
        cell.update_gates(
            scrum_armed=True,
            fold_armed=False,
            scrum_blockers=["TA"],
            fold_blockers=[],
            landing_strip_side=None,
        )
        assert cell is panel.cell_for("CHIP/USD")


class TestTheRenderPathReportsWhereItPainted:
    def test_the_render_path_reads_through_the_accessor(self):
        """`_gate_cell_for` is the single point that decides where a
        gate row comes from. If the loop went back to reading
        `_gate_cells` directly, the panel would be bypassed silently."""
        src = (
            REPO_ROOT / "src/gui/simulator_tab/fleet" / "fleet_replay_panel.py"
        ).read_text(encoding="utf-8")
        assert "cell = self._gate_cell_for(sym)" in src

    def test_the_accessor_prefers_the_panel(self):
        """MIGRATION PIN. With a panel attached the accessor must serve
        its cells, not the table's."""
        _qapp()
        from src.gui.simulator_tab.fleet.sim_visuals import GateStatusPanel
        from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

        p = FleetReplayPanel()
        gp = GateStatusPanel()
        gp.set_symbols(SYMS)
        p._gate_panel = gp
        assert p._gate_cell_for("CHIP/USD") is gp.cell_for("CHIP/USD")

    def test_the_host_is_the_panel(self):
        """MIGRATION PIN. `host` is what proves the display moved."""
        _qapp()
        from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

        p = FleetReplayPanel()
        assert getattr(p, "_gate_host_kind", "table") == "panel"


class TestTheGatesColumnIsGone:
    def test_the_table_no_longer_carries_a_gates_column(self):
        """MIGRATION PIN. Leaving the column in place would mean the
        display was duplicated, not moved."""
        from src.gui.simulator_tab.fleet.fleet_replay_panel import FleetReplayPanel

        assert "Gates" not in FleetReplayPanel.COLUMNS
