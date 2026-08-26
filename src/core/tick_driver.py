"""The call that advances the asyncio loop, with no Qt in it.

Every coroutine in this application runs on one asyncio loop, and that
loop does not run itself. Something must call it. In the shipped
application that caller is the ``QTimer`` built by
``main._make_async_pump_timer``, and nothing else reaches
``ScrummingBot.tick``. Measured with a real ``QApplication`` running and
the pump stopped: 0 coroutine steps in 1000 ms. With the pump started:
10.

This module holds the call itself and the interval it runs at, so the
caller can be replaced without the trading loop noticing. It imports no
Qt, directly or transitively.

TWO SCHEDULERS, ONE BODY. Measured over the same 5 s window, driving the
same started bot:

    Qt        ``main._make_async_pump_timer`` connects ``pump_once`` to a
              PreciseTimer QTimer.  99 pumps, 101 ticks, median 50.043 ms
    Qt-free   ``AsyncioTickDriver.run`` calls ``pump_once`` on the
              calling thread.       100 pumps, 102 ticks, median 50.000 ms

Both call the same ``pump_once`` at the same ``PUMP_INTERVAL_MS``, so a
change to either is a change to both.

NO NEW THREAD. ``AsyncioTickDriver.run`` blocks the thread that calls it,
the way ``QApplication.exec`` does. Every coroutine keeps running on the
caller's thread, so no shared trading state changes hands.
"""

from __future__ import annotations

import asyncio
import threading
import time
from typing import Optional, Protocol, runtime_checkable

# The cadence of the whole application. A coroutine resumes only when the
# loop is advanced, so this is the resolution of every ``asyncio.sleep``
# in the trading path. ``main.ASYNC_PUMP_INTERVAL_MS`` must equal it;
# tests/test_tick_driver_is_qt_free.py fails when they differ.
PUMP_INTERVAL_MS = 50


def pump_once(loop: asyncio.AbstractEventLoop) -> None:
    """Run one iteration of ``loop``, then return to the caller.

    ``call_soon`` is queued BEFORE ``run_forever`` so the loop already
    holds a ready callback and stops after draining that one batch.
    Without it ``run_forever`` never returns and the caller never runs
    again.

    One iteration is not one coroutine step. A task waiting on
    ``asyncio.sleep`` needs two: the timer handle resolves the future,
    then the task resumes. Measured under a 50 ms pump, a coroutine
    awaiting ``sleep(0.01)`` advances every 100 ms, and one awaiting
    ``sleep(0)`` every 50.132 ms.
    """
    loop.call_soon(loop.stop)
    loop.run_forever()


# Loops with a driver already on them, by id(). A loop advanced twice per
# interval halves every asyncio.sleep in the trading path and reports
# nothing, so the second driver is refused rather than logged.
#
# A QTimer schedule does not register here. main.py builds one and only
# one, so the reachable case is two AsyncioTickDrivers; a driver added
# beside main's QTimer would not be caught.
_DRIVEN_LOOPS: set[int] = set()
_DRIVEN_LOOPS_LOCK = threading.Lock()


@runtime_checkable
class TickDriver(Protocol):
    """What ``main`` needs from whatever advances the loop."""

    # True between the first pump and the last.
    is_running: bool
    # Pumps completed over the driver's life. Zero means the bots never
    # ticked, which every rate assertion must rule out before it runs.
    pump_count: int

    def stop(self) -> None:
        """Ask the driver to stop. Safe to call from another thread."""


class AsyncioTickDriver:
    """Advance ``loop`` every ``interval_ms`` on the calling thread.

    The Qt-free half of the seam. ``run`` blocks; ``stop`` releases it.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        interval_ms: int = PUMP_INTERVAL_MS,
    ) -> None:
        if interval_ms <= 0:
            raise ValueError(f"interval_ms must be positive, got {interval_ms!r}")
        self._loop = loop
        self._interval_s = interval_ms / 1000.0
        self._interval_ms = interval_ms
        self._stop_requested = False
        self._running = False
        self._pumps = 0

    @property
    def interval_ms(self) -> int:
        return self._interval_ms

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def pump_count(self) -> int:
        return self._pumps

    def stop(self) -> None:
        """Set the stop flag. ``run`` returns within one interval.

        One bool assignment, so another thread may call it. The flag is
        read after each pump, never mid-pump.
        """
        self._stop_requested = True

    def run(self, max_seconds: Optional[float] = None) -> int:
        """Pump until ``stop``, or until ``max_seconds`` elapses.

        Returns the pumps made by THIS call; ``pump_count`` is the
        lifetime total. A second concurrent ``run`` on the same driver
        raises: two drivers on one loop advance it twice per interval,
        which halves every ``asyncio.sleep`` in the trading path and
        leaves no other symptom.

        The first pump lands at ``interval_ms``, not at zero, matching
        ``QTimer.start``. Deadlines accumulate from a single monotonic
        origin so the pump body's own duration does not push the cadence
        out; a deadline already in the past is reset to now rather than
        replayed, so a stalled thread does not fire a backlog.
        """
        key = id(self._loop)
        with _DRIVEN_LOOPS_LOCK:
            if self._running:
                raise RuntimeError(
                    "this AsyncioTickDriver is already running; a second "
                    "driver on the same loop advances it twice per interval"
                )
            if key in _DRIVEN_LOOPS:
                raise RuntimeError(
                    "another AsyncioTickDriver is already advancing this "
                    "loop; two drivers halve every asyncio.sleep in the "
                    "trading path and report nothing"
                )
            _DRIVEN_LOOPS.add(key)
            self._running = True
        self._stop_requested = False
        began = time.monotonic()
        next_at = began
        made = 0
        try:
            while not self._stop_requested:
                next_at += self._interval_s
                now = time.monotonic()
                if next_at < now:
                    next_at = now
                time.sleep(next_at - now)
                if self._stop_requested:
                    break
                self._pump()
                made += 1
                self._pumps += 1
                if max_seconds is not None:
                    if time.monotonic() - began >= max_seconds:
                        break
        finally:
            with _DRIVEN_LOOPS_LOCK:
                _DRIVEN_LOOPS.discard(key)
                self._running = False
        return made

    def _pump(self) -> None:
        """One pump. A raising callback must not stop the driver.

        A QTimer whose slot raises keeps firing: measured 11 firings in
        600 ms with the slot raising every time. A driver that stopped
        instead would stop all 38 bots on one bad callback, so the
        exception goes to the loop's handler, which main.py points at the
        crash log.
        """
        try:
            pump_once(self._loop)
        except Exception as exc:
            self._loop.call_exception_handler(
                {
                    "message": "tick driver pump raised; the driver continues",
                    "exception": exc,
                }
            )
