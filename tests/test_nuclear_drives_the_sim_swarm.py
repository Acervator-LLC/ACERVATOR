"""Nuclear must actually drive the Simulator Swarm (operator directive).

OPERATOR, 2026-08-07: "Nuclear Mode is expected to use and abuse the Simulator
Bot Swarm."

TWO INDEPENDENT REASONS IT NEVER DID.

1. SIGNATURE MISMATCH. `BotVisualizationTab.register_sim_run(sim_id, label,
   cfg)` takes THREE arguments. Nuclear called its hook with TWO —
   `self._swarm_register(sim_id, {...})` — passing the config dict where
   `label` goes and omitting `cfg` entirely. That is a TypeError on the first
   cycle, swallowed to `logger.debug`, so the rows simply never appeared and
   nothing said why. `nuclear_verification.py:19` recorded the symptom without
   the cause: "register_sim_run() zero callers -> swarm rows never driven".

2. NOBODY CALLED `set_swarm_hooks`. Zero callers repo-wide, so all three hooks
   stayed None and every call site was a no-op regardless of shape. The
   Simulator Swarm and the Nuclear controller live in different top-level tabs
   (`BotVisualizationTab` vs `SimulatorTab`), and nothing connected them.

A THIRD THING, WHICH IS A REPORTING DEFECT NOT A WIRING ONE. Nuclear passed
`float(progress.trades_fired)` as the row's **PnL**, so the swarm would have
displayed a trade count formatted as dollars — "PnL +37.00" for 37 trades.
Nuclear does not measure P&L; it measures coverage and survival. Reporting a
count in a currency field is inventing a number, so it now reports 0.0 and
says so at the call site.

NOTE ON NUMBERS. Every fixture here is synthetic and small. The operator's
real fleet is 35 bots / 40 persisted wires; nothing below touches it.
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

# The mixin that builds the Simulator tab, composed into MainWindow.
SIM_TAB_BUILDER = REPO_ROOT / "src/gui/main_tabs/simulator_tab.py"

from src.simulator.nuclear_fleet_controller import (  # noqa: E402
    NuclearFleetController,
)


class TestTheHookShapesMatchTheRealApi:
    """The consumer is `BotVisualizationTab`. Its signatures are the contract;
    the hooks must fit them or every call is a swallowed TypeError."""

    @staticmethod
    def _sig(name):
        src = (REPO_ROOT / "src/gui/bot_visualizer.py").read_text(encoding="utf-8")
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.FunctionDef) and n.name == name:
                args = [a.arg for a in n.args.args if a.arg != "self"]
                required = len(args) - len(n.args.defaults)
                return args, required
        pytest.fail(f"{name} not found in bot_visualizer.py")

    def test_register_takes_three_arguments(self):
        """POSITIVE CONTROL for the mismatch claim — if the real API ever
        becomes 2-arg, the fix below would be wrong and this says so."""
        args, required = self._sig("register_sim_run")
        assert args == ["sim_id", "label", "cfg"]
        assert required == 3

    def test_nuclear_calls_register_with_three_arguments(self):
        seen = []
        ctl = NuclearFleetController()
        ctl.set_swarm_hooks(
            register=lambda *a, **kw: seen.append(("register", a, kw)),
            update=lambda *a, **kw: None,
            stop=lambda *a, **kw: None,
        )
        ctl._swarm_register("nuclear-c0-w0", "label", {"asset": "x"})
        assert seen and len(seen[0][1]) == 3

    def test_the_call_site_in_source_passes_three(self):
        """The assertion above only proves the hook is callable. This checks
        what `_run_cycle` ACTUALLY passes — read as AST, because counting
        source text has produced a false reading three times on this project.
        """
        src = (REPO_ROOT / "src/simulator/nuclear_fleet_controller.py").read_text(
            encoding="utf-8"
        )
        calls = [
            n
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
            and getattr(n.func, "attr", "") == "_swarm_register"
        ]
        assert calls, "no _swarm_register call site found"
        for c in calls:
            assert len(c.args) == 3, (
                f"line {c.lineno} passes {len(c.args)} positional args; "
                "register_sim_run(sim_id, label, cfg) needs 3 — a 2-arg call "
                "is a TypeError swallowed to debug, which is why swarm rows "
                "never appeared"
            )

    def test_update_and_stop_already_fit(self):
        u_args, u_req = self._sig("update_sim_run")
        s_args, s_req = self._sig("stop_sim_run")
        assert u_args[:3] == ["sim_id", "pnl", "trades"]
        assert s_args[:3] == ["sim_id", "pnl", "trades"]
        assert (u_req, s_req) == (3, 1)


class TestPnlIsNotATradeCount:
    def test_no_call_site_passes_trades_fired_as_pnl(self):
        """Nuclear does not measure P&L. A trade count rendered as
        "PnL +37.00" is an invented number in a currency field."""
        src = (REPO_ROOT / "src/simulator/nuclear_fleet_controller.py").read_text(
            encoding="utf-8"
        )
        for n in ast.walk(ast.parse(src)):
            if not isinstance(n, ast.Call):
                continue
            if getattr(n.func, "attr", "") not in ("_swarm_update", "_swarm_stop"):
                continue
            pnl = n.args[1] if len(n.args) > 1 else None
            rendered = ast.dump(pnl) if pnl is not None else ""
            assert (
                "trades_fired" not in rendered
            ), f"line {n.lineno} passes trades_fired as the PnL argument"


class TestTheSeamIsActuallyWired:
    """`set_swarm_hooks` had zero callers, so shape correctness was moot."""

    def test_simulator_tab_can_receive_a_swarm_reference(self):
        from src.gui.simulator_tab.simulator_tab import SimulatorTab

        assert hasattr(
            SimulatorTab, "set_swarm_getter"
        ), "nothing can hand the Simulator Swarm to the Nuclear panel"

    def test_main_window_wires_it(self):
        """AST pin on the production caller. Without this the method exists
        and is never called — the exact class of defect C58 is being queued
        to catch."""
        src = SIM_TAB_BUILDER.read_text(encoding="utf-8")
        names = {
            getattr(n.func, "attr", None)
            for n in ast.walk(ast.parse(src))
            if isinstance(n, ast.Call)
        }
        assert (
            "set_swarm_getter" in names
        ), "MainWindow never hands the swarm to SimulatorTab"

    def test_the_panel_forwards_hooks_to_the_controller(self):
        from src.gui.simulator_tab.simulator_tab import SimulatorTab

        sig = inspect.signature(SimulatorTab.set_swarm_getter)
        assert "getter" in sig.parameters


class TestTheInstrumentWorks:
    def test_hooks_default_to_none_and_are_settable(self):
        """POSITIVE CONTROL — if the hooks could not be set at all, every
        assertion above would be measuring the wrong thing."""
        ctl = NuclearFleetController()
        assert ctl._swarm_register is None
        ctl.set_swarm_hooks(register=lambda *a: None)
        assert ctl._swarm_register is not None
