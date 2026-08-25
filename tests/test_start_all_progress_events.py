"""v3.24.21 — pin tests for Start All progress events.

THE DEFECT
==========
``_on_progress_event`` read ``event.payload``. That attribute never
existed. ``EventBus.emit`` builds ``Event(topic=topic, data=kwargs)``
(``event_bus.py:136``) and ``Event.__getattr__`` raises
``AttributeError("Event has no data field 'payload'")`` for any name not
in ``data``.

Every one of the six emits in ``BotManager.start_all`` passes its fields
as kwargs, so they land in ``.data``. The handler therefore raised on
*every* event — and a bare ``except Exception: pass`` swallowed it.

Operator-visible symptom: Start All opens a dialog stuck on "Preparing to
auto-start bots..." with an empty list and a disabled Close button for the
whole staggered start, which then never auto-dismisses.

The bug was invisible for its entire lifetime because the swallow removed
the only evidence. That is the pattern these tests defend against: the
assertion is that events actually reach the signal, not merely that
nothing raised.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.core.event_bus import Event, EventBus  # noqa: E402

pytest.importorskip("PySide6")

from src.gui.start_all_progress_dialog import (  # noqa: E402
    StartAllProgressDialog,
)

TOPIC = "bot_manager.start_all_progress"


class _Recorder:
    """Stands in for the Qt signal so no QApplication is needed."""

    def __init__(self):
        self.emitted: list[tuple] = []

    def emit(self, *args):
        self.emitted.append(args)


def _handle(event):
    """Drive the real handler against a duck-typed self."""
    rec = _Recorder()
    panel = type("P", (), {"_progress_signal": rec})()
    StartAllProgressDialog._on_progress_event(panel, event)
    return rec.emitted


# ── the contract ─────────────────────────────────────────────────


def test_event_exposes_data_not_payload():
    """Pins the contract the handler got wrong."""
    e = Event(topic=TOPIC, data={"phase": "begin"})
    assert e.data["phase"] == "begin"
    with pytest.raises(AttributeError):
        _ = e.payload


def test_emit_puts_kwargs_into_data():
    bus = EventBus()
    seen = []
    bus.subscribe(TOPIC, seen.append)
    bus.emit(TOPIC, phase="begin", total=3, started=0, bot_id="")
    assert seen[0].data["phase"] == "begin"
    assert seen[0].data["total"] == 3


# ── the handler actually forwards ────────────────────────────────


def test_begin_event_reaches_the_signal():
    """The regression. Before the fix this emitted nothing at all."""
    out = _handle(
        Event(
            topic=TOPIC, data={"phase": "begin", "total": 5, "started": 0, "bot_id": ""}
        )
    )
    assert out == [("begin", 5, 0, "")]


def test_bot_started_event_reaches_the_signal():
    out = _handle(
        Event(
            topic=TOPIC,
            data={"phase": "bot_started", "total": 5, "started": 2, "bot_id": "abc123"},
        )
    )
    assert out == [("bot_started", 5, 2, "abc123")]


def test_done_event_reaches_the_signal():
    """Auto-dismiss depends on this arriving; without it the dialog
    stays open forever."""
    out = _handle(
        Event(
            topic=TOPIC, data={"phase": "done", "total": 5, "started": 5, "bot_id": ""}
        )
    )
    assert out == [("done", 5, 5, "")]


def test_cancelled_event_reaches_the_signal():
    out = _handle(
        Event(
            topic=TOPIC,
            data={"phase": "cancelled", "total": 5, "started": 1, "bot_id": ""},
        )
    )
    assert out == [("cancelled", 5, 1, "")]


def test_end_to_end_through_a_real_bus():
    """Wire the real handler to a real EventBus and emit as the engine
    does — kwargs, not a dict."""
    bus = EventBus()
    rec = _Recorder()
    panel = type("P", (), {"_progress_signal": rec})()
    bus.subscribe(
        TOPIC, lambda ev: StartAllProgressDialog._on_progress_event(panel, ev)
    )
    bus.emit(TOPIC, phase="begin", total=2, started=0, bot_id="")
    bus.emit(TOPIC, phase="bot_started", total=2, started=1, bot_id="x")
    bus.emit(TOPIC, phase="done", total=2, started=2, bot_id="")
    assert [a[0] for a in rec.emitted] == ["begin", "bot_started", "done"]


# ── tolerance without silence ────────────────────────────────────


def test_missing_fields_fall_back_to_defaults():
    out = _handle(Event(topic=TOPIC, data={"phase": "begin"}))
    assert out == [("begin", 0, 0, "")]


def test_malformed_event_is_logged_not_swallowed(capture_log):
    """A dropped event must leave a trace. The original defect survived
    precisely because it did not.

    Uses the capture_log fixture rather than caplog: logging_engine sets
    ``acervator.propagate = False``, so caplog sees nothing from these
    loggers once that engine has been constructed by any earlier test.
    """

    class _Bad:
        @property
        def data(self):
            raise AttributeError("no data")

    with capture_log("acervator.gui.start_all") as records:
        out = _handle(_Bad())
    assert out == []
    assert records, "dropped event produced no log record"


def test_non_numeric_total_is_reported(capture_log):
    with capture_log("acervator.gui.start_all") as records:
        out = _handle(
            Event(topic=TOPIC, data={"phase": "begin", "total": "not-a-number"})
        )
    assert out == []
    assert records
