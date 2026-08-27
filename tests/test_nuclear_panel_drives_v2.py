"""The Nuclear panel drives the fleet controller, not the tape prototype (W3).

W3 in `docs/engineering-notes/2026-08-05_sim_nuclear_2point0_and_optimization_audit.md`:
"the tab labelled Nuclear Mode still drives the Phase-B single-tape prototype
the v2 module was written to replace." `simulator_tab.py` said the same in-tree:
"Nuclear panel still hosts the old tape-based prototype."

Operator, 2026-08-07: Nuclear "does not run on a single tape or stone tablet. It
runs stone tablets in a loop through the simulator bots."

FOUR THINGS THAT DIFFER, EACH ITS OWN FAILURE IF MISSED:

1. CONSTRUCTION. v1 needs a tape cache and a selected tape id. v2 takes none of
   that — it reads the fleet from bot_state itself.

2. LIFECYCLE. v1's `start(loop)` is SYNC and returns bool. v2's `start()` is a
   COROUTINE and must be scheduled on the app loop. Calling it like v1 produces
   an un-awaited coroutine: no soak runs, no exception, and the panel latches
   its buttons into the running state anyway.

3. GATING. v2 has `prepare()`, which returns False with an operator-readable
   reason (no bot_state, no scrumming bots, no tablets). Skipping it starts a
   run that cannot work.

4. VOCABULARY. The status readout asked v1 for `scout_state`, `tape_position`,
   `tape_wraps`… v2 emits `cycles_completed`, `load_multiplier`, `cooling`,
   `failed_cycles`, `noise_pct`. Only `running` and `uptime_seconds` overlap, so
   a repoint that forgets this leaves eleven rows permanently blank — the panel
   would look wired and report nothing, which is the shape this whole cascade
   keeps finding.

WHAT THESE PINS CANNOT DO. They cannot prove the operator sees a working panel.
Qt rendering, timer cadence and button state under a real event loop are not
covered here; this is the headless half. The soak itself needs a human click.
"""

from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PANEL = REPO_ROOT / "src/gui/simulator_tab/nuclear_mode_panel.py"


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel_parent(qapp):
    """A parent that OWNS every panel these tests build.

    Constructing `NuclearModePanel(parent=None)` makes an orphan
    top-level widget that owns a `QTimer`. Python then garbage-collects
    the wrapper at an arbitrary later moment, and under a real Qt
    platform (the release gate runs pytest WITHOUT
    QT_QPA_PLATFORM=offscreen) that lands mid-teardown in an unrelated
    test and takes the interpreter down with SIGSEGV — exit 139, no
    traceback, and the crash surfaces in whatever file happens to be
    running at the time. It first appeared in `test_suite_integrity.py`,
    which has nothing to do with this panel.

    Parenting hands lifetime to Qt, so destruction is deterministic and
    happens while the C++ side is still alive. `deleteLater()` alone is
    not enough — it needs an event loop turn that a headless test run
    does not guarantee.

    This is the shiboken ownership trap: a live Python wrapper does not
    imply a live C++ object, and the reverse is equally true.
    """
    from PySide6.QtWidgets import QWidget

    holder = QWidget()
    yield holder
    holder.setParent(None)
    holder.deleteLater()


def _panel(parent, said=None, loop_getter=None):
    from src.gui.simulator_tab.nuclear_mode_panel import NuclearModePanel

    return NuclearModePanel(
        activity_log_cb=(said.append if said is not None else (lambda _m: None)),
        perf_log_cb=lambda _m: None,
        async_loop_getter=(loop_getter or (lambda: None)),
        parent=parent,
    )


class TestItConstructsTheFleetController:
    def test_the_panel_imports_v2(self):
        names = set()
        for n in ast.walk(ast.parse(PANEL.read_text(encoding="utf-8"))):
            if isinstance(n, ast.ImportFrom):
                names.update(a.name for a in n.names)
        assert (
            "NuclearFleetController" in names
        ), "the panel still hosts only the single-tape prototype"

    def test_it_constructs_v2_not_v1(self):
        built = [
            getattr(n.func, "id", "")
            for n in ast.walk(ast.parse(PANEL.read_text(encoding="utf-8")))
            if isinstance(n, ast.Call)
        ]
        assert "NuclearFleetController" in built
        assert (
            "NuclearController" not in built
        ), "the tape prototype is still being constructed"


class TestTheAsyncLifecycleIsHonoured:
    """v2's start() is a coroutine. Calling it like v1's sync start() creates
    an un-awaited coroutine: nothing runs, nothing raises, and the panel
    latches into 'running' anyway."""

    def test_v2_start_is_a_coroutine(self):
        """POSITIVE CONTROL — if v2's start ever became sync, the scheduling
        pin below would be enforcing a stale contract."""
        from src.simulator.nuclear_fleet_controller import (
            NuclearFleetController,
        )

        assert inspect.iscoroutinefunction(NuclearFleetController.start)

    def test_v1_start_is_not(self):
        """The asymmetry that makes the repoint dangerous, pinned so the
        reason for the scheduling code stays legible."""
        from src.simulator.nuclear_controller import NuclearController

        assert not inspect.iscoroutinefunction(NuclearController.start)

    def test_the_panel_schedules_the_coroutine(self):
        src = PANEL.read_text(encoding="utf-8")
        calls = {
            getattr(n.func, "attr", None)
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
        }
        assert "run_coroutine_threadsafe" in calls, (
            "v2's start() is a coroutine and must be scheduled on the app "
            "loop; a bare call leaves it un-awaited and silently does nothing"
        )

    def test_prepare_is_called_before_start(self):
        src = PANEL.read_text(encoding="utf-8")
        tree = ast.parse(src)
        prepare_lines = [
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "prepare"
        ]
        sched_lines = [
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == "run_coroutine_threadsafe"
        ]
        assert prepare_lines, "prepare() is never called; v2 gates on it"
        assert sched_lines
        assert min(prepare_lines) < min(
            sched_lines
        ), "start is scheduled before prepare() has a chance to refuse"


class TestTheSwarmHooksAreHandedOverBeforeStart:
    def test_set_swarm_hooks_has_a_production_caller(self):
        src = PANEL.read_text(encoding="utf-8")
        names = {
            getattr(n.func, "attr", None)
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
        }
        assert (
            "set_swarm_hooks" in names
        ), "the swarm seam is still unwired at the panel"


class TestTheStatusReadoutSpeaksV2:
    """The vocabulary pin. Every field the panel asks for must be a key v2
    actually emits, or the row is permanently blank."""

    @staticmethod
    def _v2_snapshot_keys():
        from src.simulator.nuclear_fleet_controller import (
            NuclearFleetController,
        )

        ctl = NuclearFleetController()
        return set(ctl.snapshot().keys())

    def test_the_snapshot_is_not_empty(self):
        """POSITIVE CONTROL for the pin below — an empty key set would make
        every subset assertion pass or fail for the wrong reason."""
        assert len(self._v2_snapshot_keys()) > 5

    def test_every_status_field_exists_in_the_snapshot(self):
        from src.gui.simulator_tab.nuclear_mode_panel import _STATUS_FIELDS

        keys = self._v2_snapshot_keys()
        missing = [k for _label, k in _STATUS_FIELDS if k not in keys]
        assert not missing, (
            f"the readout asks for {missing}, which v2 never emits — those "
            "rows would render permanently blank"
        )

    def test_the_tape_vocabulary_is_gone(self):
        from src.gui.simulator_tab.nuclear_mode_panel import _STATUS_FIELDS

        keys = {k for _l, k in _STATUS_FIELDS}
        stale = keys & {
            "scout_state",
            "scout_holdings",
            "scout_target",
            "tape_position",
            "tape_direction",
            "tape_wraps",
            "world_clock_ticks",
            "trade_count",
            "scrum_fold",
            "error_count",
            "exception_count",
        }
        assert not stale, f"single-tape fields remain in the readout: {stale}"

    def test_the_market_noise_is_visible(self):
        """C23's headline feature. A varied market structure the operator
        cannot see is indistinguishable from an unvaried one."""
        from src.gui.simulator_tab.nuclear_mode_panel import _STATUS_FIELDS

        assert "noise_pct" in {k for _l, k in _STATUS_FIELDS}

    def test_the_fleet_topology_is_visible(self):
        """The operator's rule: the fleet imports from bot_state, wires
        included. A run that silently loaded zero wires must be readable off
        the panel, not just the activity log."""
        from src.gui.simulator_tab.nuclear_mode_panel import _STATUS_FIELDS

        assert "wires_loaded" in {k for _l, k in _STATUS_FIELDS}


class TestThePanelStillBuilds:
    def test_it_constructs_headlessly(self, panel_parent):
        """NEGATIVE CONTROL for the boot armour shipped in v3.24.75: that
        guard must never be the reason this passes. The panel has to build
        for real."""
        assert _panel(panel_parent) is not None

    def test_it_reads_the_real_fleet(self, panel_parent):
        """The fleet readout must reflect bot_state, not a placeholder —
        a panel that renders '—' forever looks wired and reports nothing."""
        panel = _panel(panel_parent)
        assert panel._fleet_detail.text() != ""

    def test_start_without_a_loop_refuses_cleanly(self, panel_parent):
        """The app pumps ONE loop from the Qt GUI thread. No loop means no
        soak — and it must say so rather than raise into the click handler."""
        said: list[str] = []
        _panel(panel_parent, said=said)._on_start_clicked()
        assert any("loop" in m.lower() for m in said), said

    def test_stop_and_refresh_are_safe_without_a_controller(self, panel_parent):
        """Both are reachable before any soak has run — Stop is clickable
        and the 500 ms timer can fire. Neither may raise into Qt."""
        panel = _panel(panel_parent)
        panel._refresh_status()
        panel._on_stop_clicked()


class TestTheStatusRowsActuallyGetFilled:
    """v3.24.80 — the pin the earlier one should have been.

    `TestTheStatusReadoutSpeaksV2` asserted every `_STATUS_FIELDS` key
    exists in `snapshot()`. It passed while the panel rendered thirteen
    blank rows, because `_refresh_status` was still writing v1's keys
    and raising KeyError on the third one. That pin checked a
    DECLARATION; this one drives the function and reads the widgets.
    """

    @staticmethod
    def _driven(parent):
        from src.simulator.nuclear_fleet_controller import (
            NuclearFleetController,
        )

        panel = _panel(parent)
        ctl = NuclearFleetController()
        ctl.state.running = True
        ctl.state.fleet_size = 35
        ctl.state.symbols = 35
        ctl.state.cycles_completed = 3
        ctl.state.current_cycle = 4
        ctl.state.noise_pct = 0.1734
        ctl.state.load_multiplier = 1.11
        ctl.state.total_candles = 9000
        ctl.state.total_trades = 627
        ctl._smart_wires = [{}] * 40
        panel._controller = ctl
        panel._refresh_status()
        return panel

    def test_every_declared_row_is_populated(self, panel_parent):
        from src.gui.simulator_tab.nuclear_mode_panel import _STATUS_FIELDS

        panel = self._driven(panel_parent)
        blank = [
            k
            for _l, k in _STATUS_FIELDS
            if k != "last_error"
            and panel._status_labels[k].text() in ("", "-", "\u2014")
        ]
        assert not blank, f"rows never filled by _refresh_status: {blank}"

    def test_the_market_noise_is_shown_as_a_percentage(self, panel_parent):
        """The operator's directive is written in percent (10-25%); the
        state carries a fraction. A row reading '0.17' is not the
        directive's unit."""
        panel = self._driven(panel_parent)
        assert panel._status_labels["noise_pct"].text() == "17.3%"

    def test_the_wire_count_is_the_real_one(self, panel_parent):
        panel = self._driven(panel_parent)
        assert panel._status_labels["wires_loaded"].text() == "40"

    def test_a_missing_key_does_not_blank_the_panel(self, panel_parent):
        """One absent snapshot key must cost one row, never the timer."""
        panel = self._driven(panel_parent)
        panel._controller.snapshot = lambda: {"running": True}
        panel._refresh_status()
        assert panel._status_labels["running"].text() == "RUNNING"
