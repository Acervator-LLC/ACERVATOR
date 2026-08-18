"""The asyncio pump timer must receive the interval it asks for.

Every coroutine in this application runs on the Qt GUI thread. Nothing
else advances the asyncio loop: `main._make_async_pump_timer` builds the
one QTimer whose `timeout` runs `loop.call_soon(loop.stop);
loop.run_forever()`, so the timer's real cadence IS the loop's cadence.

The timer asked for 50 ms and did not get it. A QTimer whose timer type
is never set reports `Qt.TimerType.CoarseTimer`, and Qt's coarse timers
are documented to drift up to 5% and to coalesce with other timers.
Measured on this machine, 240 firings per configuration with the first
20 discarded:

    CoarseTimer   median 62.63 ms
    PreciseTimer  median 49.96 ms

The Windows system-tick explanation was tested and refuted: calling
`timeBeginPeriod(1)` around the coarse run left the median at 62.30 ms.

SCOPE, stated so nobody mistakes this for the freeze fix: this recovers
about 12.6 ms per pump cycle. It does not explain a 3-4 second button
delay, and it is not offered as an explanation of one.

WHAT EACH TEST WOULD MEAN IF IT FAILED
======================================
`test_pump_timer_receives_its_nominal_interval`
    The loop is being advanced slower than the code asks for. Either the
    timer type regressed, or something else on the GUI thread is holding
    the event loop -- both are real defects, and the failure message
    prints the measured median so the two can be told apart.

`test_pump_timer_asks_for_a_precise_timer`
    The configuration regressed. This is the cheap, deterministic pin;
    the timing test above is the one that proves it matters.

`test_a_plain_qtimer_defaults_to_coarse_on_this_build`
    THE CONTROL. If a bare QTimer ever reported PreciseTimer by default,
    the two tests above would pass without the fix doing anything, and
    they would be measuring nothing. A failure here does not mean the
    application broke; it means these tests stopped discriminating and
    the timing numbers in this docstring must be re-measured.

`test_main_wires_the_factory_in`
    The factory became dead code and main() went back to building its
    own timer. Every assertion above would still pass while the running
    application kept the defect.
"""
from __future__ import annotations

import asyncio
import statistics
import time
from pathlib import Path

import main
import pytest

# tests/conftest.py puts the repo root on sys.path at import time, and
# pytest imports conftest before any test module, so `import main` is a
# plain top-level import here. The sys.path insertion other test files
# perform before importing main pushes that import below a statement,
# which is what forces them to carry a lint directive. This file needs
# none, and adding one would be the thing the harness forbids.
REPO_ROOT = Path(__file__).resolve().parent.parent

# 100 firings at the nominal 50 ms is ~5 s of wall clock. The first 20
# are discarded: the process is still warming up its timer machinery,
# and a startup transient is not what this measures.
_FIRINGS = 100
_DISCARD = 20

# The nominal interval, plus 10%. CoarseTimer measured 25% over, so this
# threshold separates the two configurations with margin on both sides.
# The statistic is the MEDIAN, which is why a single scheduling stall on
# a loaded machine cannot turn this red.
_TOLERANCE_MS = main.ASYNC_PUMP_INTERVAL_MS * 1.10

# If the Qt event loop never quits, fail the test rather than hang the
# suite. Generous: 4x the expected 5 s.
_WATCHDOG_MS = 20_000


@pytest.fixture
def qt_app():
    """A real QApplication. No window is ever shown."""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.fixture
def asyncio_loop():
    """A real asyncio loop for the pump body to drive."""
    loop = asyncio.new_event_loop()
    try:
        yield loop
    finally:
        loop.close()


def _measure_intervals(app, timer, firings: int) -> list[float]:
    """Run `timer` under real Qt event dispatch; return ms between firings."""
    from PySide6.QtCore import QEventLoop, QTimer

    qt_loop = QEventLoop()
    samples: list[float] = []
    state = {"last": 0.0}

    def on_timeout() -> None:
        now = time.perf_counter()
        if state["last"]:
            samples.append((now - state["last"]) * 1000.0)
        state["last"] = now
        if len(samples) >= firings:
            qt_loop.quit()

    timer.timeout.connect(on_timeout)
    QTimer.singleShot(_WATCHDOG_MS, qt_loop.quit)
    timer.start()
    try:
        qt_loop.exec()
    finally:
        timer.stop()
        timer.timeout.disconnect(on_timeout)
    app.processEvents()
    return samples


def test_pump_timer_receives_its_nominal_interval(qt_app, asyncio_loop):
    """Drive the real factory's timer with the real pump body attached."""
    timer = main._make_async_pump_timer(asyncio_loop)
    samples = _measure_intervals(qt_app, timer, _FIRINGS)

    assert len(samples) >= _FIRINGS, (
        f"the timer fired only {len(samples)} times in {_WATCHDOG_MS} ms; "
        f"expected {_FIRINGS}. The pump is not running at all.")

    kept = samples[_DISCARD:]
    median = statistics.median(kept)
    p95 = sorted(kept)[int(len(kept) * 0.95) - 1]

    assert median <= _TOLERANCE_MS, (
        f"the pump timer asked for {main.ASYNC_PUMP_INTERVAL_MS} ms and "
        f"received a median of {median:.2f} ms (p95 {p95:.2f} ms) over "
        f"{len(kept)} firings, above the {_TOLERANCE_MS:.2f} ms ceiling. "
        f"Timer type in effect: {timer.timerType()!r}. Every coroutine in "
        f"the application advances only when this fires.")


def test_pump_timer_asks_for_a_precise_timer(asyncio_loop):
    """The deterministic pin behind the timing measurement above."""
    from PySide6.QtCore import Qt

    timer = main._make_async_pump_timer(asyncio_loop)
    assert timer.interval() == main.ASYNC_PUMP_INTERVAL_MS
    assert timer.timerType() == Qt.TimerType.PreciseTimer, (
        f"the pump timer is a {timer.timerType()!r}; Qt permits a coarse "
        f"timer 5% drift and lets it coalesce with other timers.")


def test_a_plain_qtimer_defaults_to_coarse_on_this_build(qt_app):
    """The control. Proves the two tests above discriminate."""
    from PySide6.QtCore import Qt, QTimer

    bare = QTimer()
    assert bare.timerType() == Qt.TimerType.CoarseTimer, (
        f"a QTimer with no setTimerType call reports "
        f"{bare.timerType()!r} on this build, not CoarseTimer. The pump "
        f"fix is then a no-op and the tests above prove nothing; "
        f"re-measure before trusting them.")


def test_main_wires_the_factory_in():
    """main() must USE the factory, or all of the above is theatre."""
    import ast

    src = (REPO_ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    factory = next(
        (n for n in tree.body
         if isinstance(n, ast.FunctionDef) and n.name == "_make_async_pump_timer"),
        None)
    assert factory is not None, (
        "main.py no longer defines _make_async_pump_timer at module level")

    # The pump body must live INSIDE the factory, not beside it.
    body_names = {
        n.attr for n in ast.walk(factory)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
        and n.value.id == "loop"}
    assert {"call_soon", "stop", "run_forever"} <= body_names, (
        f"_make_async_pump_timer no longer drives the asyncio loop; it "
        f"touches only {sorted(body_names)}")

    entry = next(n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "main")
    called = {n.func.id for n in ast.walk(entry)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_make_async_pump_timer" in called, (
        "main() does not call _make_async_pump_timer; the factory is dead "
        "code and the running application builds its own pump timer")
