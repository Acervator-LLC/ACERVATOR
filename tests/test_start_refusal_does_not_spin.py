"""A refused start() must not hot-spin the shared event loop (C23 step 4).

THE DEFECT, AND WHY IT IS WORSE THAN "SPINS FOREVER".

`FleetReplayController.start()` creates `stopped_event` and SETS it at
construction — "not-yet-started = already stopped" — and only `.clear()`s it
*after* both early returns. So on a refusal the event is still set while
`progress.finished` is still False.

Nuclear's worker then runs:

    while not ctl.progress.finished:
        ...
        await asyncio.wait_for(ctl.stopped_event.wait(), timeout=0.5)

`wait()` on an ALREADY-SET Event completes without ever suspending, so
`wait_for` never times out and the loop never yields. The `timeout=0.5` reads
like the mitigation and is exactly why this is dangerous — it looks throttled.

MEASURED on this repo's interpreter before the fix: 477,043 iterations in one
second with a competing coroutine advancing **zero**. Not a busy poll — a
complete starvation of the loop.

BLAST RADIUS. `main.py:1085-1092` pumps ONE asyncio loop from the Qt GUI thread
(`loop.call_soon(loop.stop)` / `loop.run_forever()`, 50 ms QTimer). Every live
coroutine in the process shares it. A coroutine that never suspends means
`run_forever()` never returns: the GUI thread and live trading both freeze.

Latent only because `NuclearFleetController` has no production caller. It ships
the moment the panel is repointed at it, which is why this lands FIRST.

A CORRECTION TO THE COLD READ THAT PRODUCED THIS. The report prescribed setting
`progress.finished = True` on BOTH refusal paths. That is wrong for the first
one. "Controller already running" means another replay owns `self.progress` and
is mid-flight; marking it finished would tell the panel at
`fleet_replay_panel.py:1532` to stop the progress timer and drain the final
frame for a run still in progress. Only the second refusal — nothing launched —
may touch it.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E402
    FleetReplayController,
)

BASE = 1_700_000_000_000
STEP = 300_000
BUDGET_S = 2.0
"""Wall-clock bound for anything that could hang. pytest-timeout is NOT
installed in this environment, so every await below carries its own bound —
a hang must FAIL, never wedge the suite."""


def _candles(n=8, px=100.0):
    return [[BASE + i * STEP, px, px * 1.01, px * 0.99, px, 10.0] for i in range(n)]


def _cfg(sym="BTC/USD", src="aaaa1111"):
    return {
        "mode": "scrumming",
        "symbol": sym,
        "target_balance": 100.0,
        "target_asset": sym.split("/")[0],
        "base_currency": sym.split("/")[1],
        "_src_bot_id": src,
    }


def _refusing_controller():
    """A controller that CANNOT instantiate bots — configs reference a
    symbol with no candle series, so `_build_sim` produces an empty fleet
    and `start()` takes its second refusal path."""
    return FleetReplayController(
        configs=[_cfg("NOTAPE/USD")], candles_by_symbol={"BTC/USD": _candles()}
    )


class TestTheProbeItself:
    """POSITIVE CONTROL for the starvation measurement. If the competing
    coroutine cannot advance even when the loop is healthy, every
    'competitor advanced' assertion below would pass vacuously."""

    def test_a_competitor_advances_on_a_healthy_loop(self):
        async def go():
            n = {"i": 0}

            async def other():
                while True:
                    n["i"] += 1
                    await asyncio.sleep(0)

            t = asyncio.create_task(other())
            await asyncio.sleep(0.05)
            t.cancel()
            return n["i"]

        assert asyncio.run(go()) > 0


class TestARefusedStartReportsRefusal:
    def test_start_returns_false_when_no_bots_instantiate(self):
        ctl = _refusing_controller()
        assert asyncio.run(asyncio.wait_for(ctl.start(), BUDGET_S)) is False

    def test_start_returns_true_on_a_real_run(self):
        ctl = FleetReplayController(
            configs=[_cfg()], candles_by_symbol={"BTC/USD": _candles()}
        )

        async def go():
            ok = await asyncio.wait_for(ctl.start(), BUDGET_S)
            ctl.request_stop()
            await asyncio.wait_for(ctl.stopped_event.wait(), BUDGET_S)
            return ok

        assert asyncio.run(go()) is True

    def test_a_refused_start_leaves_progress_finished(self):
        """The condition the nuclear worker loops on. Without this the
        loop has no exit."""
        ctl = _refusing_controller()
        asyncio.run(asyncio.wait_for(ctl.start(), BUDGET_S))
        assert ctl.progress.finished is True
        assert ctl.stopped_event.is_set()


class TestTheAlreadyRunningRefusalDoesNotLie:
    """THE CORRECTION. A second start() while one is in flight must NOT
    mark the RUNNING replay finished — `fleet_replay_panel.py:1532` reads
    that to stop the progress timer and drain the final frame."""

    def test_a_second_start_does_not_mark_the_live_run_finished(self):
        ctl = FleetReplayController(
            configs=[_cfg()], candles_by_symbol={"BTC/USD": _candles(n=4000)}
        )

        async def go():
            assert await asyncio.wait_for(ctl.start(), BUDGET_S) is True
            second = await asyncio.wait_for(ctl.start(), BUDGET_S)
            finished_during = ctl.progress.finished
            ctl.request_stop()
            await asyncio.wait_for(ctl.stopped_event.wait(), BUDGET_S)
            return second, finished_during

        second, finished_during = asyncio.run(go())
        assert second is False, "a second start must report refusal"
        assert finished_during is False, (
            "the in-flight replay was marked finished by a REFUSED second "
            "start; the panel would stop its progress timer mid-run"
        )


class TestTheLoopYieldsToTheRestOfTheProcess:
    """The defect that freezes live trading, measured rather than argued."""

    @staticmethod
    async def _starvation_probe(ctl, seconds=0.4):
        """Run the nuclear worker's wait shape against `ctl` and report how
        far a competing coroutine got. Returns (iterations, competitor)."""
        comp = {"n": 0}

        async def other():
            while True:
                comp["n"] += 1
                await asyncio.sleep(0)

        t = asyncio.create_task(other())
        await asyncio.sleep(0.05)
        assert comp["n"] > 0, "probe is dead before it starts"
        base, iters, t0 = comp["n"], 0, time.monotonic()
        while not ctl.progress.finished:
            try:
                await asyncio.wait_for(ctl.stopped_event.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
            iters += 1
            if time.monotonic() - t0 > seconds:
                break
        during = comp["n"] - base
        t.cancel()
        return iters, during

    def test_a_refused_start_does_not_starve_the_loop(self):
        """THE PROPERTY: a refused start must never starve the loop.

        Two ways to satisfy it — exit immediately, or yield while looping.
        An earlier version of this test demanded the competitor advance,
        which is only meaningful IF the loop iterates. The fix makes it
        exit on the first check, so the competitor legitimately gets no
        window, and that assertion failed on CORRECT code. Asserting a
        symptom's signature instead of the property is how a test ends up
        arguing against its own fix.

        Both branches are checked below, so this stays honest whichever
        way a future implementation satisfies it.
        """

        async def go():
            ctl = _refusing_controller()
            await asyncio.wait_for(ctl.start(), BUDGET_S)
            return await self._starvation_probe(ctl)

        iters, competitor = asyncio.run(asyncio.wait_for(go(), BUDGET_S * 3))

        assert iters < 1000, (
            f"{iters} iterations on a refused start is a hot spin, not an "
            "exit — `progress.finished` never became True"
        )

        if iters > 0:
            # It chose to loop rather than exit; then it MUST yield.
            assert competitor > 0, (
                f"the loop ran {iters} times and nothing else on the event "
                "loop advanced. main.py pumps one loop from the Qt GUI "
                "thread, so this freezes the GUI and every live coroutine"
            )

    def test_the_probe_still_detects_a_spin(self):
        """NEGATIVE CONTROL for the test above. Its `iters < 1000` bound is
        only meaningful if the probe can still observe an unbounded spin —
        so drive it with a controller left in the pre-fix state."""

        async def go():
            ctl = _refusing_controller()
            await asyncio.wait_for(ctl.start(), BUDGET_S)
            ctl.progress.finished = False  # re-create the old condition
            return await self._starvation_probe(ctl, seconds=0.2)

        iters, competitor = asyncio.run(asyncio.wait_for(go(), BUDGET_S * 3))
        assert iters > 1000, (
            "the probe no longer detects a hot spin, so the bound in the "
            "test above proves nothing"
        )
        assert competitor == 0, (
            "expected total starvation in the pre-fix shape; if the loop "
            "now yields, this file's premise needs re-deriving"
        )


class TestExistingCallersStillWork:
    """`start()` gained a return value. Nothing may depend on it being None."""

    def test_awaiting_start_and_ignoring_the_result_still_runs(self):
        ctl = FleetReplayController(
            configs=[_cfg()], candles_by_symbol={"BTC/USD": _candles()}
        )

        async def go():
            await asyncio.wait_for(ctl.start(), BUDGET_S)  # result ignored
            ctl.request_stop()
            await asyncio.wait_for(ctl.stopped_event.wait(), BUDGET_S)
            return ctl.progress.finished

        assert asyncio.run(go()) is True

    def test_a_fresh_controller_is_not_born_finished(self):
        """`finished` must stay False by default — `_run_in_flight` at
        fleet_replay_panel.py:487 reads `not finished`, so a True default
        would make Reset silently discard a live replay."""
        ctl = FleetReplayController(configs=[], candles_by_symbol={})
        assert ctl.progress.finished is False
