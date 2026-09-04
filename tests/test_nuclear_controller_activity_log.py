"""`NuclearController._log_activity` reports which call actually failed.

The handler named teardown while the failure was the caller's activity
callback, so an operator reading the log looked at the wrong lifecycle
stage.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.simulator.nuclear_controller import NuclearController  # noqa: E402

LOGGER = "acervator.nuclear_sim"


class _StubSource:
    """Enough candle source for the constructor's tape check."""

    def list_tapes(self):
        return ["A"]


def _boom(_msg):
    raise RuntimeError("callback exploded")


def _controller(callback):
    return NuclearController(
        candle_source=_StubSource(), tape_id="A", activity_cb=callback
    )


def test_a_raising_activity_callback_is_reported_as_the_callback(capture_log):
    with capture_log(LOGGER) as records:
        _controller(_boom)._log_activity("anything")
    warnings = [r.getMessage() for r in records if r.levelno >= logging.WARNING]
    assert warnings, "a raising activity callback produced no warning at all"
    assert any(
        "activity callback" in m for m in warnings
    ), f"the warning does not name the activity callback: {warnings}"
    assert not any("teardown" in m for m in warnings), (
        f"the warning blames teardown for an activity-callback failure: " f"{warnings}"
    )


def test_a_working_activity_callback_logs_no_warning(capture_log):
    """POSITIVE CONTROL: a handler that warned on every call would pass
    the assertions above while telling the operator nothing."""
    seen = []
    with capture_log(LOGGER) as records:
        _controller(seen.append)._log_activity("anything")
    assert seen == ["anything"], f"the callback did not receive the line: {seen}"
    warnings = [r.getMessage() for r in records if r.levelno >= logging.WARNING]
    assert not warnings, f"a successful activity callback warned anyway: {warnings}"


def test_a_raising_activity_callback_does_not_propagate():
    """Every lifecycle method calls this; a raise here would abort start
    and stop."""
    _controller(_boom)._log_activity("anything")
