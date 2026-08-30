"""qt_safe_events_surface.py -- the reentrancy rule as plain data.

Describes the guard ``safe_process_events`` applies before it lets the
interface library dispatch the events waiting in its queue: the
per-thread flag it reads, the four ways one call ends, the message it
writes when the guard fires, the level it writes at, and the order the
branches run in.

The rule needs two facts about the world it runs in -- whether the
interface library loaded, and whether an application object exists --
and one queue of waiting work. Those arrive as arguments here rather
than as imports, so the same rule serves any frontend.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``qt_safe_events.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, Optional

METHOD = "qt_safe_events.state"

LOGGER_NAME = "src.gui.qt_safe_events"
SKIP_LOG_LEVEL = "DEBUG"
SKIP_LOG_TEMPLATE = "safe_process_events skipped (reentrancy guard): %s"

DEFAULT_REASON = ""
DEFAULT_FORCE = False

GUARD_IS_PER_THREAD = True

PROCESSED = "processed"
NO_TOOLKIT = "no_toolkit"
REENTRANT = "reentrant"
NO_APP = "no_app"
OUTCOMES = (PROCESSED, NO_TOOLKIT, REENTRANT, NO_APP)

RETURNS_TRUE = (PROCESSED,)

SIGNALS: tuple = ()
ACTIONS: dict = {}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
WIDGETS: tuple = ()
PAINTS = False

TOOLKIT_MISSING = "toolkit_missing"
GUARD_READ = "guard_read"
GUARD_FIRED = "guard_fired"
GUARD_FORCED = "guard_forced"
SKIP_LOGGED = "skip_logged"
SKIP_SILENT = "skip_silent"
GUARD_SET = "guard_set"
APP_CHECKED = "app_checked"
APP_MISSING = "app_missing"
EVENTS_PROCESSED = "events_processed"
GUARD_CLEARED = "guard_cleared"
GUARD_RESET = "guard_reset"

CALL_NAMES = (
    TOOLKIT_MISSING,
    GUARD_READ,
    GUARD_FIRED,
    GUARD_FORCED,
    SKIP_LOGGED,
    SKIP_SILENT,
    GUARD_SET,
    APP_CHECKED,
    APP_MISSING,
    EVENTS_PROCESSED,
    GUARD_CLEARED,
    GUARD_RESET,
)


def skip_record(reason: Any) -> dict:
    """The message the guard writes when it fires, unformatted.

    The interface library's logger keeps the template and its argument
    apart and joins them only when something reads the message, so a
    reason that refuses to become text refuses at reading time and not
    at call time. This carries the same two pieces.
    """
    return {
        "level": SKIP_LOG_LEVEL,
        "template": SKIP_LOG_TEMPLATE,
        "args": [reason],
    }


def record_text(record: dict) -> str:
    """The one line a written record reads as."""
    return record["template"] % tuple(record["args"])


def outcome_returns(outcome: str) -> bool:
    """What one ending answers to the caller."""
    return outcome in RETURNS_TRUE


class SafeEventsModel:
    """One process's reentrancy guard, with no Qt object behind it.

    Holds the per-thread flag the rule reads, the work waiting to be
    dispatched, the records the guard wrote, the endings each call
    reached and the branch markers each call passed.
    """

    def __init__(self) -> None:
        self._guard = threading.local()
        self.pending: list = []
        self.records: list = []
        self.outcomes: list = []
        self.returned: list = []
        self.dispatched: list = []
        self.app_consulted: int = 0
        self.calls: list = []

    def is_in_call(self) -> bool:
        """Whether this thread is already inside a call."""
        return getattr(self._guard, "in_call", False)

    def post(self, name: Any, work: Optional[Callable[[], None]] = None) -> None:
        """Put one piece of work in the queue the next call drains.

        Stands for the interface library's own queue, which the one
        action this rule guards is what empties.
        """
        self.pending.append((name, work))

    def process_events(
        self,
        reason: Any = DEFAULT_REASON,
        force: Any = DEFAULT_FORCE,
        has_toolkit: bool = True,
        has_app: bool = True,
    ) -> bool:
        """Drain the queue once unless the guard, the library or the
        application object stops it.

        Answers True when the queue was drained, False on every other
        ending. ``has_toolkit`` is whether the interface library loaded
        and ``has_app`` whether an application object exists.
        """
        if not has_toolkit:
            self.calls.append(TOOLKIT_MISSING)
            return self._ended(NO_TOOLKIT)

        self.calls.append(GUARD_READ)
        if self.is_in_call():
            if not force:
                self.calls.append(GUARD_FIRED)
                if reason:
                    self.calls.append(SKIP_LOGGED)
                    self.records.append(skip_record(reason))
                else:
                    self.calls.append(SKIP_SILENT)
                return self._ended(REENTRANT)
            self.calls.append(GUARD_FORCED)

        self._guard.in_call = True
        self.calls.append(GUARD_SET)
        try:
            self.app_consulted += 1
            self.calls.append(APP_CHECKED)
            if not has_app:
                self.calls.append(APP_MISSING)
                return self._ended(NO_APP)
            self._drain()
            self.calls.append(EVENTS_PROCESSED)
            return self._ended(PROCESSED)
        finally:
            self._guard.in_call = False
            self.calls.append(GUARD_CLEARED)

    def reset_for_test(self) -> None:
        """Put this thread's flag down."""
        self._guard.in_call = False
        self.calls.append(GUARD_RESET)

    def _drain(self) -> None:
        """Run queued work oldest first until the queue is empty.

        Each piece is taken off before it runs, so work that calls back
        into this rule takes what is still waiting rather than a copy.
        """
        while self.pending:
            name, work = self.pending.pop(0)
            self.dispatched.append(name)
            if work is not None:
                work()

    def _ended(self, outcome: str) -> bool:
        self.outcomes.append(outcome)
        answer = outcome_returns(outcome)
        self.returned.append(answer)
        return answer


def build_view_model(model: SafeEventsModel) -> dict:
    """Return the whole guard state as one serialisable dict."""
    return {
        "logger": {
            "name": LOGGER_NAME,
            "level": SKIP_LOG_LEVEL,
            "template": SKIP_LOG_TEMPLATE,
        },
        "guard": {
            "in_call": model.is_in_call(),
            "per_thread": GUARD_IS_PER_THREAD,
        },
        "defaults": {"reason": DEFAULT_REASON, "force": DEFAULT_FORCE},
        "outcomes": list(model.outcomes),
        "returned": list(model.returned),
        "records": [dict(record) for record in model.records],
        "dispatched": list(model.dispatched),
        "app_consulted": model.app_consulted,
        "pending": len(model.pending),
        "endings": list(OUTCOMES),
        "answers_true": list(RETURNS_TRUE),
        "paints": PAINTS,
        "widgets": list(WIDGETS),
        "signals": list(SIGNALS),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "calls": list(model.calls),
        "method": METHOD,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``qt_safe_events.state``.

    Runs one guarded call with the reason, the force flag and the two
    world facts the request names, after queueing the number of pieces
    of work it asks for, and returns the guard state that call left.
    """
    asked = params or {}
    model = SafeEventsModel()
    for index in range(int(asked.get("pending", 0))):
        model.post(f"work {index}")
    model.process_events(
        reason=asked.get("reason", DEFAULT_REASON),
        force=asked.get("force", DEFAULT_FORCE),
        has_toolkit=bool(asked.get("has_toolkit", True)),
        has_app=bool(asked.get("has_app", True)),
    )
    return build_view_model(model)
