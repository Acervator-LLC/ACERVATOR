"""The thing that reaches `bot.tick()` must not need Qt.

WHAT WAS TRUE BEFORE THIS FILE
==============================
`main._make_async_pump_timer` built a QTimer whose slot held the pump
body inline. That QTimer was the ONLY caller advancing the asyncio loop,
so it was the only path to `BotContainer.tick`. Measured with a real
QApplication running and the pump stopped: 0 coroutine steps in 1000 ms.
Started: 10. Deleting Qt therefore stopped all 38 bots trading, and the
first symptom would have been silence, not a crash.

WHAT CHANGED
============
The pump body and its interval moved to `src/core/tick_driver.py`, which
imports no Qt. `main` still supplies the Qt schedule; `AsyncioTickDriver`
supplies a Qt-free one. Both call the same `pump_once` at the same
`PUMP_INTERVAL_MS`, so the cadence cannot drift between them.

The trading work did NOT move to another thread. `AsyncioTickDriver.run`
blocks its caller, the way `QApplication.exec` does, so every coroutine
still runs on one thread and no shared state changes hands.

WHAT EACH TEST WOULD MEAN IF IT FAILED
======================================
`test_the_driver_module_imports_no_qt`
    A Qt import reached the module, directly or through a helper. The
    headless path then needs PySide6 present and the unit bought nothing.

`test_main_and_the_driver_agree_on_the_interval`
    The two constants drifted. One scheduler now advances the loop at a
    different rate than the other, which is a change in trading cadence
    with no other symptom.

`test_a_real_bot_ticks_with_no_qt_event_loop`
    The Qt-free driver does not reach `tick()`. Headless, every bot is
    silent.

`test_a_real_bot_ticks_under_the_qt_pump`
    THE OPERATOR'S LIVE PATH. If this fails, the running application has
    stopped trading. Nothing else in this file matters.

`test_both_drivers_reach_the_same_tick_count`
    The two schedulers disagree about cadence. Whichever is wrong is
    running the fleet at the wrong rate.

`test_one_driver_pumps_once_per_interval`
    The pump count over a known window is not what one driver produces.
    Above the expected count means something advances the loop twice --
    every `asyncio.sleep` in the trading path then completes early.

`test_a_second_run_on_one_driver_is_refused`
`test_a_second_driver_on_the_same_loop_is_refused`
    Two drivers can share a loop undetected. That is the silent
    catastrophe: no error, no log, twice the tick rate. The first reads
    one object run twice; the second reads two objects, which is the
    case a per-object flag cannot see.

`test_stop_releases_run`
    The driver will not stop, so the process hangs on exit and the
    operator's shutdown never completes.

`test_a_raising_pump_does_not_stop_the_driver`
    One bad callback stops all 38 bots. A QTimer does not behave this
    way: measured 11 firings in 600 ms with the slot raising every time.
"""

from __future__ import annotations

import ast
import asyncio
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import cast

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import main  # noqa: E402
from src.core.tick_driver import (  # noqa: E402
    PUMP_INTERVAL_MS,
    AsyncioTickDriver,
    TickDriver,
    pump_once,
)
from src.exchange.base import ExchangeInterface  # noqa: E402
from src.trading.bot_container import BotConfig, BotContainer  # noqa: E402

# A one-second window at 50 ms is 20 pumps, so a doubled driver reads as 40.
_WINDOW_S = 1.0
_EXPECTED_PUMPS = int(_WINDOW_S * 1000 / PUMP_INTERVAL_MS)

# One pump is lost to the last partial interval, and a loaded machine may
# lose a second. Above the count, not below, is the dangerous side.
_PUMP_FLOOR = _EXPECTED_PUMPS - 2
_PUMP_CEILING = _EXPECTED_PUMPS + 1


class _CountingBot(BotContainer):
    """A real BotContainer. Only `tick` is replaced, with a counter."""

    def __init__(self) -> None:
        super().__init__(
            config=BotConfig(
                exchange_id="test",
                base_currency="USD",
                target_asset="TICK",
                symbol="TICK/USD",
            ),
            exchange=cast(ExchangeInterface, None),
        )
        self.ticks = 0
        self.tick_threads: set[int] = set()

    @property
    def tick_interval(self) -> float:
        """0 s, so the bot ticks as fast as the driver advances the loop."""
        return 0.0

    async def tick(self) -> None:
        self.ticks += 1
        self.tick_threads.add(threading.get_ident())


class _RaisingLoop:
    """A loop stand-in whose `run_forever` always raises.

    Used to drive the driver's real error handling. Nothing else in
    `AsyncioTickDriver` is replaced.
    """

    def __init__(self) -> None:
        self.attempts = 0
        self.handled: list[dict] = []

    def call_soon(self, _callback) -> None:
        return None

    def stop(self) -> None:
        return None

    def run_forever(self) -> None:
        self.attempts += 1
        raise RuntimeError("planted: the pump body raised")

    def call_exception_handler(self, context: dict) -> None:
        self.handled.append(context)


def _new_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.new_event_loop()
    loop.set_exception_handler(lambda _loop, _ctx: None)
    return loop


def _started_bot(loop: asyncio.AbstractEventLoop) -> _CountingBot:
    """Build a real bot and run its real `start()` on `loop`."""
    bot = _CountingBot()
    loop.run_until_complete(bot.start())
    return bot


def _stop_bot(loop: asyncio.AbstractEventLoop, bot: _CountingBot) -> None:
    loop.run_until_complete(bot.stop())


@pytest.fixture
def qt_app():
    qtwidgets = pytest.importorskip("PySide6.QtWidgets")
    return qtwidgets.QApplication.instance() or qtwidgets.QApplication([])


_QT_ROOTS = ("PySide6", "PyQt5", "PyQt6", "shiboken6")


def _module_path(dotted: str) -> Path | None:
    """Return the file for a first-party `src.*` module, or None."""
    if not dotted.startswith("src."):
        return None
    candidate = REPO / Path(*dotted.split("."))
    if candidate.with_suffix(".py").is_file():
        return candidate.with_suffix(".py")
    if (candidate / "__init__.py").is_file():
        return candidate / "__init__.py"
    return None


def _imports_of(path: Path, package: str) -> set[str]:
    """Every dotted name this file imports, including inside functions.

    Relative forms are resolved against `package`, so `from ..gui import x`
    is followed like an absolute import rather than skipped.
    """
    names: set[str] = set()
    parts = package.split(".")
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = parts[: len(parts) - node.level + 1]
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            if not prefix:
                continue
            names.add(prefix)
            names.update(f"{prefix}.{a.name}" for a in node.names)
    return names


def _qt_reached_from(start: str) -> set[str]:
    """Qt modules reachable from `start` through first-party imports."""
    seen: set[str] = set()
    found: set[str] = set()
    queue = [start]
    while queue:
        dotted = queue.pop()
        if dotted in seen:
            continue
        seen.add(dotted)
        path = _module_path(dotted)
        if path is None:
            continue
        package = dotted if path.name == "__init__.py" else dotted.rsplit(".", 1)[0]
        for name in _imports_of(path, package):
            if name.split(".")[0] in _QT_ROOTS:
                found.add(f"{dotted} -> {name}")
            elif name.startswith("src."):
                queue.append(name)
    return found


# The seam itself
def test_the_driver_module_imports_no_qt():
    """No Qt anywhere in the module's first-party import closure.

    Static rather than a trial import: a Qt import inside a function body
    never executes at import time, so a runtime probe cannot see it.
    """
    found = _qt_reached_from("src.core.tick_driver")
    assert found == set(), (
        f"src/core/tick_driver.py reaches Qt: {sorted(found)}. The "
        f"headless tick path still needs PySide6 installed, so the unit "
        f"bought nothing."
    )


def test_the_control_for_the_qt_scan_above():
    """The scan must SEE Qt where Qt is. Otherwise it proves nothing."""
    found = _qt_reached_from("src.gui.alerts_tab")
    assert found, (
        "the Qt detector found nothing in src/gui/alerts_tab.py, which "
        "imports PySide6. It is blind, and the test above proves nothing."
    )


def test_main_and_the_driver_agree_on_the_interval():
    """One cadence, restated in two files. They must not drift."""
    assert main.ASYNC_PUMP_INTERVAL_MS == PUMP_INTERVAL_MS, (
        f"main.ASYNC_PUMP_INTERVAL_MS is {main.ASYNC_PUMP_INTERVAL_MS} ms "
        f"and tick_driver.PUMP_INTERVAL_MS is {PUMP_INTERVAL_MS} ms. The Qt "
        f"schedule and the headless schedule now advance the loop at "
        f"different rates, which changes trading cadence and shows no "
        f"other symptom."
    )


def test_the_qt_factory_uses_the_shared_pump_body():
    """main's timer must call `pump_once`, not a private copy of it."""
    import inspect

    source = inspect.getsource(main._make_async_pump_timer)
    assert "pump_once" in source, (
        "main._make_async_pump_timer no longer calls "
        "src.core.tick_driver.pump_once. The Qt path and the headless "
        "path can now diverge without any test noticing."
    )


def test_the_driver_satisfies_the_protocol():
    loop = _new_loop()
    driver = AsyncioTickDriver(loop)
    loop.close()
    assert isinstance(driver, TickDriver)


def test_pump_once_advances_a_real_loop():
    """The body itself, driven. An AST scan cannot see a no-op."""
    loop = _new_loop()
    ran = {"n": 0}
    loop.call_soon(lambda: ran.__setitem__("n", ran["n"] + 1))
    assert ran["n"] == 0, "the callback ran before anything advanced the loop"
    pump_once(loop)
    loop.close()
    assert ran["n"] == 1, (
        "pump_once did not run a queued callback. It is not advancing the "
        "loop, so nothing reaches bot.tick()."
    )


# Does a real bot tick?
def _qt_canary() -> tuple[object, dict]:
    """A 10 ms QTimer that fires only while a Qt event loop dispatches.

    Reading `QApplication.instance()` would not do: an instance can exist
    with nothing dispatching, and other tests in the session create one.
    This reads what actually matters -- whether Qt ran anything.
    """
    from PySide6.QtCore import Qt, QTimer

    seen = {"n": 0}
    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.setInterval(10)
    timer.timeout.connect(lambda: seen.__setitem__("n", seen["n"] + 1))
    return timer, seen


def test_a_real_bot_ticks_with_no_qt_event_loop():
    """Nothing Qt dispatches for a whole second. The bot must still trade."""
    pytest.importorskip("PySide6.QtCore")
    canary, seen = _qt_canary()

    loop = _new_loop()
    bot = _started_bot(loop)
    driver = AsyncioTickDriver(loop)
    began = time.perf_counter()
    canary.start()
    pumps = driver.run(max_seconds=_WINDOW_S)
    canary.stop()
    elapsed = time.perf_counter() - began
    _stop_bot(loop, bot)
    loop.close()

    assert elapsed >= _WINDOW_S * 0.9, (
        f"the run returned after {elapsed * 1000:.0f} ms, short of the "
        f"{_WINDOW_S * 1000:.0f} ms window. Nothing below is measuring a "
        f"real interval."
    )
    assert seen["n"] == 0, (
        f"a 10 ms Qt timer fired {seen['n']} times during the run, so a Qt "
        f"event loop WAS dispatching. This test is not measuring the "
        f"headless case."
    )
    assert pumps > 0, "the driver never pumped"
    assert bot.ticks > 0, (
        f"{pumps} pumps in {elapsed * 1000:.0f} ms reached the loop and "
        f"bot.tick() ran 0 times with no Qt dispatch. The driver is not "
        f"Qt-free after all."
    )
    assert len(bot.tick_threads) == 1, (
        f"bot.tick() ran on {len(bot.tick_threads)} threads. The driver "
        f"must not move trading work off the calling thread."
    )


def test_a_real_bot_ticks_under_the_qt_pump(qt_app):
    """The operator's live path, unchanged. This one is the fleet."""
    from PySide6.QtCore import QEventLoop, QTimer

    qt_app.processEvents()
    canary, seen = _qt_canary()
    loop = _new_loop()
    bot = _started_bot(loop)
    timer = main._make_async_pump_timer(loop)
    fires = {"n": 0}
    timer.timeout.connect(lambda: fires.__setitem__("n", fires["n"] + 1))

    qloop = QEventLoop()
    QTimer.singleShot(int(_WINDOW_S * 1000), qloop.quit)
    began = time.perf_counter()
    canary.start()
    timer.start()
    qloop.exec()
    timer.stop()
    canary.stop()
    elapsed = time.perf_counter() - began
    _stop_bot(loop, bot)
    loop.close()

    assert seen["n"] > 0, (
        "the Qt dispatch canary fired 0 times while a Qt event loop was "
        "running. It is blind, and the headless test's zero proves "
        "nothing."
    )

    assert elapsed >= _WINDOW_S * 0.9, (
        f"the Qt window closed after {elapsed * 1000:.0f} ms; nothing "
        f"below measures a real interval."
    )
    assert fires["n"] > 0, "the Qt pump timer never fired"
    assert bot.ticks > 0, (
        f"the pump fired {fires['n']} times in {elapsed * 1000:.0f} ms and "
        f"bot.tick() ran 0 times. THE RUNNING APPLICATION HAS STOPPED "
        f"TRADING."
    )


def test_both_drivers_reach_the_same_tick_count(qt_app):
    """Qt and no-Qt must move the same bot the same distance."""
    from PySide6.QtCore import QEventLoop, QTimer

    qt_app.processEvents()
    qt_loop = _new_loop()
    qt_bot = _started_bot(qt_loop)
    timer = main._make_async_pump_timer(qt_loop)
    qloop = QEventLoop()
    QTimer.singleShot(int(_WINDOW_S * 1000), qloop.quit)
    timer.start()
    qloop.exec()
    timer.stop()
    _stop_bot(qt_loop, qt_bot)
    qt_loop.close()

    free_loop = _new_loop()
    free_bot = _started_bot(free_loop)
    AsyncioTickDriver(free_loop).run(max_seconds=_WINDOW_S)
    _stop_bot(free_loop, free_bot)
    free_loop.close()

    assert qt_bot.ticks > 0 and free_bot.ticks > 0, (
        f"one side never ticked: qt={qt_bot.ticks} free={free_bot.ticks}. "
        f"A comparison of two zeroes proves nothing."
    )
    drift = abs(qt_bot.ticks - free_bot.ticks) / max(qt_bot.ticks, 1)
    assert drift <= 0.25, (
        f"Qt drove the bot {qt_bot.ticks} ticks and the Qt-free driver "
        f"{free_bot.ticks} over {_WINDOW_S:.1f} s, a {drift * 100:.1f}% "
        f"difference. The two schedulers do not agree on cadence."
    )


# Exactly one driver
def test_one_driver_pumps_once_per_interval():
    """The count over a known window is what ONE driver produces.

    The bounds derive from PUMP_INTERVAL_MS, so this cannot see a WRONG
    interval -- the expectation moves with it. That is
    `test_main_and_the_driver_agree_on_the_interval`'s job. This one sees
    a driver that pumps more or fewer times than its own interval asks.
    """
    loop = _new_loop()
    driver = AsyncioTickDriver(loop)
    began = time.perf_counter()
    pumps = driver.run(max_seconds=_WINDOW_S)
    elapsed = time.perf_counter() - began
    loop.close()

    assert (
        elapsed >= _WINDOW_S * 0.9
    ), f"window was {elapsed * 1000:.0f} ms, not {_WINDOW_S * 1000:.0f}"
    assert pumps >= _PUMP_FLOOR, (
        f"{pumps} pumps in {elapsed * 1000:.0f} ms, below the "
        f"{_PUMP_FLOOR} floor. The loop is being advanced slower than "
        f"{PUMP_INTERVAL_MS} ms, so every bot ticks late."
    )
    assert pumps <= _PUMP_CEILING, (
        f"{pumps} pumps in {elapsed * 1000:.0f} ms, above the "
        f"{_PUMP_CEILING} ceiling for one driver at {PUMP_INTERVAL_MS} ms. "
        f"Something is advancing the loop twice; every asyncio.sleep in "
        f"the trading path then completes early."
    )
    assert driver.pump_count == pumps


def test_a_second_run_on_one_driver_is_refused():
    """Two drivers on one loop is the failure with no symptom."""
    loop = _new_loop()
    driver = AsyncioTickDriver(loop)
    raised: list[BaseException] = []
    started = threading.Event()

    def second() -> None:
        started.wait(3.0)
        time.sleep(0.15)
        try:
            driver.run(max_seconds=0.1)
        except RuntimeError as exc:
            raised.append(exc)

    worker = threading.Thread(target=second, daemon=True)
    worker.start()
    started.set()
    driver.run(max_seconds=0.6)
    worker.join(5.0)
    loop.close()

    assert raised, (
        "a second concurrent run() was accepted. Two drivers on one loop "
        "advance it twice per interval and nothing reports it."
    )
    assert "already running" in str(raised[0]), (
        f"the refusal came from the loop registry, not from this driver's "
        f"own state: {raised[0]}. The per-object guard is gone, so the "
        f"same-object case now depends on a second mechanism."
    )


def test_a_second_driver_on_the_same_loop_is_refused():
    """The guard above only sees ONE object. Two objects is the real case."""
    loop = _new_loop()
    first = AsyncioTickDriver(loop)
    second = AsyncioTickDriver(loop)
    raised: list[BaseException] = []
    started = threading.Event()

    def rival() -> None:
        started.wait(3.0)
        time.sleep(0.15)
        try:
            second.run(max_seconds=0.1)
        except RuntimeError as exc:
            raised.append(exc)

    worker = threading.Thread(target=rival, daemon=True)
    worker.start()
    started.set()
    first.run(max_seconds=0.6)
    worker.join(5.0)
    loop.close()

    assert raised, (
        "a second AsyncioTickDriver object was allowed onto a loop another "
        "driver was already advancing. The loop then moves twice per "
        "interval and every asyncio.sleep in the trading path completes "
        "early, with nothing logged."
    )
    assert "another AsyncioTickDriver" in str(
        raised[0]
    ), f"the refusal did not come from the loop registry: {raised[0]}"
    assert second.pump_count == 0, (
        f"the refused driver pumped {second.pump_count} times before being " f"refused."
    )


def test_the_refusal_lifts_after_the_run_ends():
    """The control for the refusal above: it must not refuse forever."""
    loop = _new_loop()
    driver = AsyncioTickDriver(loop)
    first = driver.run(max_seconds=0.2)
    second = driver.run(max_seconds=0.2)
    loop.close()
    assert first > 0 and second > 0, (
        f"a driver that has stopped will not restart: first={first} "
        f"second={second}. Restart after a UI reload would be impossible."
    )
    assert driver.pump_count == first + second, (
        f"pump_count is {driver.pump_count}; run() reported {first} then "
        f"{second}. The lifetime counter and the per-run counts disagree."
    )


# Cadence
def test_the_headless_cadence_matches_the_nominal_interval():
    """Median gap between pumps, read at the loop, not at the driver."""
    loop = _new_loop()
    stamps: list[float] = []

    def stamp() -> None:
        stamps.append(time.perf_counter())
        loop.call_soon(stamp)

    loop.call_soon(stamp)
    AsyncioTickDriver(loop).run(max_seconds=3.0)
    loop.close()

    gaps = [(b - a) * 1000.0 for a, b in zip(stamps, stamps[1:])]
    assert len(gaps) >= 20, (
        f"only {len(gaps)} intervals measured in 3 s; expected about "
        f"{int(3000 / PUMP_INTERVAL_MS)}. The driver is barely running."
    )
    median = statistics.median(gaps)
    ceiling = PUMP_INTERVAL_MS * 1.10
    assert median <= ceiling, (
        f"the Qt-free driver asked for {PUMP_INTERVAL_MS} ms and held a "
        f"median of {median:.2f} ms over {len(gaps)} intervals, above the "
        f"{ceiling:.2f} ms ceiling. Every bot ticks slower headless than "
        f"it does under Qt."
    )


# Shutdown, and a pump that raises
def test_stop_releases_run():
    """A driver that will not stop is how a process hangs on exit."""
    loop = _new_loop()
    driver = AsyncioTickDriver(loop)
    done = threading.Event()

    def drive() -> None:
        driver.run()
        done.set()

    worker = threading.Thread(target=drive, daemon=True)
    worker.start()
    time.sleep(0.4)
    assert driver.is_running, "the driver never started"
    began = time.perf_counter()
    driver.stop()
    released = done.wait(3.0)
    latency = (time.perf_counter() - began) * 1000.0
    worker.join(3.0)
    loop.close()

    assert released, (
        "run() did not return within 3 s of stop(). Shutdown would hang "
        "and the operator's process would have to be killed."
    )
    assert latency <= PUMP_INTERVAL_MS * 3, (
        f"stop() took {latency:.0f} ms to release run(); one interval is "
        f"{PUMP_INTERVAL_MS} ms."
    )
    assert not driver.is_running


def test_a_raising_pump_does_not_stop_the_driver():
    """A QTimer keeps firing when its slot raises. So must this."""
    loop = _RaisingLoop()
    driver = AsyncioTickDriver(cast("asyncio.AbstractEventLoop", loop))
    pumps = driver.run(max_seconds=0.6)

    assert loop.attempts >= 2, (
        f"the pump body raised and the driver stopped after "
        f"{loop.attempts} attempt(s). One bad callback would silence all "
        f"38 bots; a QTimer fired 11 times in 600 ms under the same fault."
    )
    assert pumps >= 2
    assert len(loop.handled) == loop.attempts, (
        f"{loop.attempts} raises reached the pump and "
        f"{len(loop.handled)} reached the loop's exception handler. A "
        f"swallowed failure is invisible in the crash log."
    )


def test_a_non_positive_interval_is_refused():
    loop = _new_loop()
    with pytest.raises(ValueError):
        AsyncioTickDriver(loop, interval_ms=0)
    with pytest.raises(ValueError):
        AsyncioTickDriver(loop, interval_ms=-50)
    loop.close()
