"""Load then Start must work (v3.25.1).

`_on_start_clicked` refuses when `_controller is not None and
_run_in_flight()`. `_run_in_flight` read `not progress.finished`, and a
fresh `ReplayProgress` has `finished = False`.

That was harmless while only Start built a controller. Load now builds
one too, so after Load the guard reported a run in flight for a fleet
that had never ticked, and Start answered "A replay is already
running."

These tests drive `_run_in_flight` through the four states that matter.
No fleet, no tablets, no Qt event loop: the guard is a pure function of
the controller it is given.
"""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from src.gui.simulator_tab.fleet.fleet_replay_panel import (  # noqa: E402
    FleetReplayPanel)


class _Progress:
    def __init__(self, started_at_wall=0.0, finished=False):
        self.started_at_wall = started_at_wall
        self.finished = finished
        self.candles_played = 0


class _Task:
    def __init__(self, done: bool):
        self._done = done

    def done(self) -> bool:
        return self._done


class _Ctl:
    def __init__(self, progress, task=None):
        self.progress = progress
        self._task = task


def _guard(ctl) -> bool:
    """Call the real method with a stand-in `self`.

    `_run_in_flight` reads only `self._controller`, so binding it to a
    plain object exercises the shipped code without building a widget.
    """
    class _Panel:
        pass
    p = _Panel()
    p._controller = ctl
    return FleetReplayPanel._run_in_flight(p)


def test_no_controller_is_not_in_flight():
    assert _guard(None) is False


def test_loaded_but_never_started_is_not_in_flight():
    """THE REGRESSION. Load builds a controller; nothing has run.

    `finished` is False here, which is exactly what made the old guard
    say True and refuse Start.
    """
    ctl = _Ctl(_Progress(started_at_wall=0.0, finished=False))
    assert _guard(ctl) is False, "a fleet that never ticked is not running"


def test_running_task_is_in_flight():
    """POSITIVE CONTROL for the test above.

    Without this, a guard hardwired to False would pass and Reset would
    silently discard a live run.
    """
    ctl = _Ctl(_Progress(started_at_wall=1.0), task=_Task(done=False))
    assert _guard(ctl) is True


def test_completed_task_is_not_in_flight():
    ctl = _Ctl(_Progress(started_at_wall=1.0, finished=True),
               task=_Task(done=True))
    assert _guard(ctl) is False


def test_started_run_without_a_task_reference_is_in_flight():
    """Task reference gone, run started and not finished: still work."""
    ctl = _Ctl(_Progress(started_at_wall=1.0, finished=False), task=None)
    assert _guard(ctl) is True


def test_unreadable_progress_assumes_in_flight():
    """Failing safe means never discarding a run we cannot read."""
    class _Bad:
        _task = None

        @property
        def progress(self):
            raise RuntimeError("unreadable")

    assert _guard(_Bad()) is True


def test_start_guard_condition_allows_start_after_load():
    """The exact expression at the top of `_on_start_clicked`."""
    ctl = _Ctl(_Progress(started_at_wall=0.0, finished=False))
    refused = ctl is not None and _guard(ctl)
    assert refused is False, "Load then Start must not be refused"
