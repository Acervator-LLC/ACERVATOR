"""One in-flight task per pump, and none left when the loop closes.

``MainWindow._cancel_if_pending`` drops a future that is still running and
``_schedule_coalesced`` puts the next one in its place, so the chart-fetch
and scout-refresh pumps never stack. ``main.drain_pending_tasks`` clears
whatever is left before ``loop.close()``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


class TestCancelIfPendingHelper:
    """``_cancel_if_pending`` is a staticmethod, driven off the class."""

    def _get_helper(self):
        pytest.importorskip("PySide6.QtWidgets")
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication

        QApplication.instance() or QApplication([])
        from src.gui.main_window import MainWindow

        return MainWindow._cancel_if_pending

    def test_none_is_safe(self):
        h = self._get_helper()
        h(None)  # must not raise

    def test_done_future_left_alone(self):
        h = self._get_helper()
        fut = SimpleNamespace(
            done=lambda: True,
            cancel=lambda: (_ for _ in ()).throw(
                AssertionError("cancel called on done future")
            ),
        )
        h(fut)  # must not call cancel

    def test_pending_future_is_cancelled(self):
        h = self._get_helper()
        state = {"cancelled": False}

        def _cancel():
            state["cancelled"] = True
            return True

        fut = SimpleNamespace(done=lambda: False, cancel=_cancel)
        h(fut)
        assert state["cancelled"] is True

    def test_exception_swallowed(self):
        h = self._get_helper()
        fut = SimpleNamespace(
            done=lambda: False,
            cancel=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        h(fut)  # must swallow


class _Future:
    """A future the coalescing seam can cancel, recording that it was."""

    def __init__(self, name: str):
        self.name = name
        self.cancelled = False

    def done(self) -> bool:
        return False

    def cancel(self) -> bool:
        self.cancelled = True
        return True


class _Window:
    """A host the REAL coalescing seam runs against, recording futures.

    ``_cancel_if_pending`` and ``_coalesce_impl`` are MainWindow's own
    functions; ``_schedule_async`` is the one outward edge stubbed.
    """

    def __init__(self, cancel_if_pending, coalesce_impl):
        self.scheduled: list = []
        self.futures: list[_Future] = []
        self._cancel_if_pending = cancel_if_pending
        self._coalesce_impl = coalesce_impl

    def _schedule_async(self, coro):
        found = _Future(str(coro))
        self.scheduled.append(coro)
        self.futures.append(found)
        return found

    def _schedule_coalesced(self, slot, coro):
        return self._coalesce_impl(self, slot, coro)


def _main_window_class():
    """The shipped MainWindow, with a QApplication in place."""
    pytest.importorskip("PySide6.QtWidgets")
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from src.gui.main_window import MainWindow

    return MainWindow


def _window():
    """A ``_Window`` carrying MainWindow's real coalescing functions."""
    shipped = _main_window_class()
    return _Window(shipped._cancel_if_pending, shipped._schedule_coalesced)


def _coalesce(window, slot, coro):
    """Drive the shipped ``_schedule_coalesced`` against ``window``."""
    return window._schedule_coalesced(slot, coro)


class TestTheCoalescingSeam:
    """One in-flight task per slot: a second schedule cancels the first."""

    def test_the_first_schedule_cancels_nothing(self):
        window = _window()
        _coalesce(window, "_pending_chart_fetch", "first")
        assert [f.cancelled for f in window.futures] == [False]

    def test_the_second_schedule_cancels_the_first(self):
        window = _window()
        _coalesce(window, "_pending_chart_fetch", "first")
        _coalesce(window, "_pending_chart_fetch", "second")
        assert [f.cancelled for f in window.futures] == [True, False], (
            "the second schedule left the first task in flight — the "
            "'Task was destroyed but pending' warnings return"
        )

    def test_the_slot_holds_the_newest_future(self):
        window = _window()
        _coalesce(window, "_pending_scout_refresh", "first")
        _coalesce(window, "_pending_scout_refresh", "second")
        assert window._pending_scout_refresh is window.futures[-1]

    def test_two_slots_do_not_cancel_one_another(self):
        """NEGATIVE CONTROL: the chart pump and the scout pump coalesce
        separately."""
        window = _window()
        _coalesce(window, "_pending_chart_fetch", "chart")
        _coalesce(window, "_pending_scout_refresh", "scout")
        assert [f.cancelled for f in window.futures] == [False, False]


def _raise_pump_fault(exc):
    """Fail loudly: _pump_market_pairs_scout swallows what it hits."""
    raise AssertionError(f"_pump_market_pairs_scout raised {exc!r}")


class _Scout:
    def __init__(self):
        self.calls: list = []

    def refresh_from_connectors(self, connectors):
        self.calls.append(connectors)
        return f"refresh-{len(self.calls)}"


class TestTheScoutPumpCoalesces:
    """The real ``_pump_market_pairs_scout``, driven twice."""

    def _pump_twice(self, monkeypatch):
        from src.exchange import market_pairs_scout

        window = _window()
        main_window = _main_window_class()

        scout = _Scout()
        monkeypatch.setattr(market_pairs_scout, "get_scout", lambda: scout)
        window._exchange_connectors = {"binance": object()}
        window._scout_pump_fault = SimpleNamespace(
            note_success=lambda: None, note_failure=_raise_pump_fault
        )
        main_window._pump_market_pairs_scout(window)
        main_window._pump_market_pairs_scout(window)
        return window, scout

    def test_the_pump_reaches_the_scout_twice(self, monkeypatch):
        """POSITIVE CONTROL for the cancellation below: the pump really
        scheduled two refreshes."""
        window, scout = self._pump_twice(monkeypatch)
        assert len(scout.calls) == 2
        assert len(window.futures) == 2

    def test_the_second_pump_cancels_the_first_refresh(self, monkeypatch):
        window, _scout = self._pump_twice(monkeypatch)
        assert [f.cancelled for f in window.futures] == [True, False], (
            "MarketPairsScout.refresh_from_connectors stacked a second "
            "in-flight task on top of the first"
        )


class TestShutdownDrain:
    """``main.drain_pending_tasks`` leaves nothing for ``loop.close()``."""

    @staticmethod
    def _loop_with_a_sleeper():
        """A stopped loop holding one started, unfinished task.

        The sleep is short so a drain that forgets to cancel finishes and
        reports a wrong answer instead of blocking the run.
        """
        import asyncio

        loop = asyncio.new_event_loop()
        loop.set_exception_handler(lambda _loop, _ctx: None)
        task = loop.create_task(asyncio.sleep(0.05))
        loop.run_until_complete(asyncio.sleep(0))
        return loop, task

    def test_a_pending_task_survives_an_undrained_loop(self):
        """POSITIVE CONTROL: without the drain the task is still pending
        when the loop stops."""
        loop, task = self._loop_with_a_sleeper()
        assert not task.done()
        task.cancel()
        loop.close()

    def test_the_drain_cancels_and_awaits_every_pending_task(self):
        import main

        loop, task = self._loop_with_a_sleeper()
        drained = main.drain_pending_tasks(loop)
        loop.close()
        assert drained == 1, f"drain_pending_tasks reported {drained}"
        assert task.done()
        assert task.cancelled()

    def test_the_drain_on_a_quiet_loop_reports_nothing(self):
        import asyncio

        import main

        loop = asyncio.new_event_loop()
        assert main.drain_pending_tasks(loop) == 0
        loop.close()
