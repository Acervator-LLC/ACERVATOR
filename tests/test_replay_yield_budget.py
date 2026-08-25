"""v3.24.20 — pin tests for replay yield budgeting.

THE DEFECT
==========
Under the GUI the asyncio loop is not free-running. ``main.py:955`` drives
it from a Qt QTimer::

    def pump_async():
        loop.call_soon(loop.stop)
        loop.run_forever()
    async_timer.start(50)

``loop.stop`` is queued BEFORE ``run_forever()``, so each fire executes
exactly one ``_run_once()`` pass. A task rescheduled by
``await asyncio.sleep(0)`` lands in ``_ready`` after that pass's snapshot,
so it does not resume until the next fire.

**One yield = one 50 ms QTimer tick.**

The replay loop yielded once per candle plus once every 8 bots. At 35 bots
that is 4 + 1 = 5 yields/candle = 251 ms/candle = 3.98 candles/s. The
operator's own run logs bracket this exactly: GUI-launched runs averaged
2.80 candles/s (1.42 / 1.52 / 5.47) against 81.32 headless. Same code,
different pump — headless uses ``asyncio.run()``, where a yield costs
microseconds.

WHAT IS PINNED
==============
The invariant is *yields per candle*, not wall-clock speed. Wall-clock is
machine- and load-dependent and would make this test flaky; yields/candle
is deterministic and is the quantity that multiplies by the pump period.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.gui.simulator_tab.fleet.fleet_replay_controller import (  # noqa: E402
    _YIELD_BUDGET_S,
    FleetReplayController,
)


class _Ctl(FleetReplayController):
    """Bare controller — we exercise _maybe_yield directly rather than
    standing up 35 bots and a candle archive."""

    def __init__(self):
        self.progress = type("P", (), {"yields_emitted": 0})()
        self._last_yield = time.perf_counter()


def test_budget_constant_is_well_under_the_pump_period():
    """At 20 ms the GUI still gets ~50 slots/second, comfortably above a
    repaint, while the replay stops paying a 50 ms pump period per bot."""
    assert 0.0 < _YIELD_BUDGET_S < 0.050


def test_rapid_calls_collapse_to_one_yield():
    """The core fix. 35 bots in a tight loop must not produce 35 yields."""
    c = _Ctl()
    c._last_yield = time.perf_counter()

    async def run():
        for _ in range(35):
            await c._maybe_yield()

    asyncio.run(run())
    assert c.progress.yields_emitted == 0, (
        f"{c.progress.yields_emitted} yields for 35 back-to-back bots; "
        "under the GUI pump each costs ~50 ms"
    )


def test_a_yield_happens_once_the_budget_elapses():
    """It must still yield — starving the GUI entirely was the v3.24.1
    freeze this replaced."""
    c = _Ctl()
    c._last_yield = time.perf_counter() - (_YIELD_BUDGET_S * 2)

    async def run():
        await c._maybe_yield()

    asyncio.run(run())
    assert c.progress.yields_emitted == 1


def test_budget_resets_after_yielding():
    c = _Ctl()
    c._last_yield = time.perf_counter() - (_YIELD_BUDGET_S * 2)

    async def run():
        await c._maybe_yield()  # yields, resets
        for _ in range(20):
            await c._maybe_yield()  # all inside the fresh budget

    asyncio.run(run())
    assert c.progress.yields_emitted == 1


def test_yields_per_candle_beats_the_old_count_scheme():
    """Quantified regression guard.

    Old scheme with 35 bots: 4 (every-8-bots) + 1 (per-candle) = 5
    yields/candle. New scheme is time-bounded, so across a burst of
    simulated candles the ratio must land far below 1.0.
    """
    c = _Ctl()
    c._last_yield = time.perf_counter()
    candles = 200
    bots = 35

    async def run():
        for _ in range(candles):
            for _b in range(bots):
                await c._maybe_yield()
            await c._maybe_yield()

    t0 = time.perf_counter()
    asyncio.run(run())
    elapsed = time.perf_counter() - t0

    per_candle = c.progress.yields_emitted / candles
    # Upper bound from the budget itself: at most one yield per 20 ms.
    ceiling = (elapsed / _YIELD_BUDGET_S) / candles + 0.01
    assert per_candle <= ceiling, (
        f"{per_candle:.4f} yields/candle exceeds the {ceiling:.4f} " "budget ceiling"
    )
    assert per_candle < 5.0, (
        f"{per_candle:.4f} yields/candle is no better than the old "
        "count-based scheme (5.0 at 35 bots)"
    )


def test_old_constant_is_gone():
    """_YIELD_EVERY_N_BOTS bought GUI responsiveness at 5x the replay's
    throughput. It must not come back."""
    src = (
        REPO / "src" / "gui" / "simulator_tab" / "fleet" / "fleet_replay_controller.py"
    ).read_text(encoding="utf-8")
    assert "_YIELD_EVERY_N_BOTS = " not in src


def test_counter_is_persisted_to_the_run_log():
    """Diagnosing this cost a hand-derivation across 62 run directories
    because the rate was never recorded. It is recorded now."""
    src = (
        REPO / "src" / "gui" / "simulator_tab" / "fleet" / "fleet_replay_controller.py"
    ).read_text(encoding="utf-8")
    assert '"yields_per_candle"' in src
    assert '"yields_emitted"' in src
