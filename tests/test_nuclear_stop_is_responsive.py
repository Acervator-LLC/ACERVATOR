"""Stop must reach the running fleets, not wait out the cycle (C23 step 3).

TWO DEFECTS, ONE OF WHICH IS A LIFECYCLE-API GAP THE REPOINT WOULD HIT.

1. API GAP. The Nuclear panel calls `self._controller.is_running()` and
   `self._controller.stop()`. `NuclearController` (v1, what the panel drives
   today) has both. `NuclearFleetController` (v2, the repoint target) has
   NEITHER — it has `request_stop()`. Repointing the panel without these is an
   AttributeError on the operator's first Stop click.

2. STOP IS NOT RESPONSIVE, and this is the one that matters. `stop_requested`
   is written in `request_stop()` and read in exactly ONE place: the
   between-cycles `while not self.state.stop_requested:` in `_run`. Nothing
   inside a cycle reads it, and the child `FleetReplayController` — which DOES
   have a working `request_stop()` — is a local inside the `_one()` closure, so
   nothing outside can reach it to ask.

   A cycle is `DEFAULT_CYCLE_CANDLES = 3000` candles across up to 6 gathered
   worker fleets. At the measured ~25.8 candles/s that is minutes, during which
   Stop does nothing — on the single asyncio loop `main.py` pumps from the Qt
   GUI thread, shared with live trading.

   That is the realistic failure of "it must launch AND RUN": not a crash, an
   application that ignores the operator.

WHAT THIS FILE DOES NOT TEST. Nothing here compares Nuclear output to YTD or
live. Nuclear is an abuse instrument, not a validator.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.simulator.nuclear_fleet_controller import (  # noqa: E402
    NuclearFleetController,
)

BUDGET_S = 5.0
"""Every await is individually bounded — pytest-timeout is not installed, so a
hang must FAIL rather than wedge the suite. This is the shape v3.24.74 used."""


class _StubProgress:
    def __init__(self):
        self.finished = False
        self.candles_played = 0
        self.trades_fired = 0
        self.stop_requested = False


class _StubFleet:
    """A child fleet that runs until asked to stop — the case a real 3000-candle
    cycle approximates, and the only case where responsiveness is observable."""

    instances: list = []

    def __init__(self, *a, **kw):
        self.progress = _StubProgress()
        self.stopped_event = asyncio.Event()
        self.stop_calls = 0
        self._bots = []
        _StubFleet.instances.append(self)

    async def start(self):
        return True

    def request_stop(self):
        self.stop_calls += 1
        self.progress.finished = True
        self.stopped_event.set()


@pytest.fixture(autouse=True)
def _clear_instances():
    _StubFleet.instances.clear()
    yield
    _StubFleet.instances.clear()


class TestTheLifecycleApiThePanelCalls:
    """The panel already calls these. Repointing without them is an
    AttributeError on the first Stop click."""

    def test_is_running_exists_and_reports_state(self):
        ctl = NuclearFleetController()
        assert ctl.is_running() is False
        ctl.state.running = True
        assert ctl.is_running() is True

    def test_stop_exists(self):
        ctl = NuclearFleetController()
        ctl.stop()
        assert ctl.state.stop_requested is True

    def test_stop_and_request_stop_agree(self):
        """`stop()` is the panel's vocabulary, `request_stop()` is the
        controller's. They must not drift into meaning different things."""
        a, b = NuclearFleetController(), NuclearFleetController()
        a.stop()
        b.request_stop()
        assert a.state.stop_requested == b.state.stop_requested is True

    def test_the_v1_surface_is_matched(self):
        """The repoint swaps one class for another behind the same panel. Any
        method the panel calls must exist on BOTH, or Stop breaks after the
        swap and nothing catches it until the operator clicks."""
        import ast

        v1 = REPO_ROOT / "src/simulator/nuclear_controller.py"
        tree = ast.parse(v1.read_text(encoding="utf-8"))
        v1_methods = {
            n.name
            for c in ast.walk(tree)
            if isinstance(c, ast.ClassDef)
            for n in c.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in ("is_running", "stop"):
            assert name in v1_methods, f"premise changed: v1 lost {name}"
            assert hasattr(
                NuclearFleetController, name
            ), f"v2 has no {name}(); the panel calls it"


class TestStopReachesTheRunningFleets:
    @staticmethod
    def _controller(monkeypatch):
        import src.simulator.fleet.fleet_replay_controller as frc

        monkeypatch.setattr(frc, "FleetReplayController", _StubFleet)
        ctl = NuclearFleetController(cycle_candles=120, max_cycles=1)
        ctl._configs = [
            {"mode": "scrumming", "symbol": "BTC/USD", "_src_bot_id": "aaaa1111"}
        ]
        ctl._candles = {"BTC/USD": [[1, 1, 1, 1, 1, 1]] * 8}
        return ctl

    def test_a_child_fleet_is_asked_to_stop(self, monkeypatch):
        ctl = self._controller(monkeypatch)

        async def go():
            task = asyncio.create_task(ctl._run())
            for _ in range(200):  # let a cycle get going
                await asyncio.sleep(0)
                if _StubFleet.instances:
                    break
            ctl.request_stop()
            await asyncio.wait_for(task, BUDGET_S)

        asyncio.run(asyncio.wait_for(go(), BUDGET_S * 2))
        assert _StubFleet.instances, "no child fleet was ever constructed"
        assert any(f.stop_calls > 0 for f in _StubFleet.instances), (
            "request_stop() never reached any child fleet — `ctl` is a local "
            "inside _one(), so nothing outside can ask it to stop, and Stop "
            "waits out the whole cycle"
        )

    def test_the_controller_stops_running(self, monkeypatch):
        ctl = self._controller(monkeypatch)

        async def go():
            task = asyncio.create_task(ctl._run())
            for _ in range(200):
                await asyncio.sleep(0)
                if _StubFleet.instances:
                    break
            ctl.stop()
            await asyncio.wait_for(task, BUDGET_S)

        asyncio.run(asyncio.wait_for(go(), BUDGET_S * 2))
        assert ctl.is_running() is False


class TestTheInstrumentWorks:
    def test_the_stub_records_stop_calls(self):
        """POSITIVE CONTROL. If the stub cannot record a stop, the assertions
        above pass or fail for reasons unrelated to the controller."""
        f = _StubFleet()
        assert f.stop_calls == 0
        f.request_stop()
        assert f.stop_calls == 1
        assert f.progress.finished is True
