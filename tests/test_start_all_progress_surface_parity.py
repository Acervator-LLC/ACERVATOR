"""The Qt Start All dialog and the Qt-free surface, side by side.

A failure means the view model writes a different headline, a different
bot line, a different button state, a different auto-close delay or a
different sequence of calls than ``StartAllProgressDialog`` does on the
same progress events.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.core.event_bus import Event
from src.gui import start_all_progress_dialog as qt_dialog
from src.gui.main_tabs import start_all_progress_surface as surface
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

LOGGER_NAME = surface.LOGGER_NAME

PROGRESS = "progress"
REPLACE = "replace"
CANCEL = "cancel"
CLOSE = "close"

MANAGER_OK = "manager_ok"
MANAGER_RAISES = "manager_raises"
MANAGER_NO_METHOD = "manager_no_method"
MANAGER_NONE = "manager_none"

UNSUB_OK = "unsub_ok"
UNSUB_RAISES = "unsub_raises"
UNSUB_NONE = "unsub_none"
UNSUB_NOT_CALLABLE = "unsub_not_callable"
UNSUB_BOOL_RAISES = "unsub_bool_raises"

PIXEL_SIZE = (520, 360)


def app():
    """The process application object every render and widget needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


class _Manager:
    def __init__(self):
        self.calls = 0

    def cancel_start_all(self):
        self.calls += 1


class _RaisingManager:
    def cancel_start_all(self):
        raise RuntimeError("manager refused the cancel")


def make_manager(spec):
    """Build the manager one step drives, fresh, so no step reuses state."""
    if spec == MANAGER_RAISES:
        return _RaisingManager()
    if spec == MANAGER_NO_METHOD:
        return object()
    if spec == MANAGER_NONE:
        return None
    return _Manager()


class _BoolRaises:
    def __bool__(self):
        raise RuntimeError("truthiness refused")


def make_unsubscriber(spec):
    """Build the unsubscribe callable one step drives, fresh."""
    if spec == UNSUB_RAISES:

        def refuse():
            raise RuntimeError("unsubscribe refused")

        return refuse
    if spec == UNSUB_NONE:
        return None
    if spec == UNSUB_NOT_CALLABLE:
        return 5
    if spec == UNSUB_BOOL_RAISES:
        return _BoolRaises()

    def drop():
        return None

    return drop


class _ItemProxy:
    """One list row, with the calls the dialog makes on it recorded."""

    def __init__(self, item, row, calls):
        self._item = item
        self._row = row
        self._calls = calls

    def text(self):
        return self._item.text()

    def setText(self, text):
        self._item.setText(text)
        self._calls.append(["list.setItemText", self._row, text])


def trace_dialog(dialog, monkeypatch):
    """Record every call the dialog makes on its own widgets and timer.

    The wrappers sit on the widget instances, so a snapshot reads the
    same widgets through their classes and adds nothing to the trace.
    """
    from PySide6 import QtWidgets

    calls: list[list] = []

    headline = dialog._headline
    listing = dialog._list
    cancel_btn = dialog._cancel_btn
    close_btn = dialog._close_btn

    def set_headline(text):
        QtWidgets.QLabel.setText(headline, text)
        calls.append(["headline.setText", text])

    def clear_items():
        QtWidgets.QListWidget.clear(listing)
        calls.append(["list.clear"])

    def add_item(text):
        QtWidgets.QListWidget.addItem(listing, text)
        calls.append(["list.addItem", text])

    def item_count():
        calls.append(["list.count"])
        return QtWidgets.QListWidget.count(listing)

    def item_at(row):
        calls.append(["list.item", row])
        found = QtWidgets.QListWidget.item(listing, row)
        return None if found is None else _ItemProxy(found, row, calls)

    def scroll_to_bottom():
        QtWidgets.QListWidget.scrollToBottom(listing)
        calls.append(["list.scrollToBottom"])

    def set_cancel_enabled(enabled):
        QtWidgets.QPushButton.setEnabled(cancel_btn, enabled)
        calls.append(["cancel.setEnabled", enabled])

    def set_close_enabled(enabled):
        QtWidgets.QPushButton.setEnabled(close_btn, enabled)
        calls.append(["close.setEnabled", enabled])

    def single_shot(delay_ms, _slot):
        calls.append(["closeAfter", delay_ms])

    headline.setText = set_headline
    listing.clear = clear_items
    listing.addItem = add_item
    listing.count = item_count
    listing.item = item_at
    listing.scrollToBottom = scroll_to_bottom
    cancel_btn.setEnabled = set_cancel_enabled
    close_btn.setEnabled = set_close_enabled
    monkeypatch.setattr(
        qt_dialog,
        "QtCore",
        SimpleNamespace(QTimer=SimpleNamespace(singleShot=single_shot)),
    )
    return calls


def snapshot_old(dialog, calls, error):
    """Every output the Qt dialog carries after one step."""
    from PySide6 import QtWidgets

    rows = QtWidgets.QListWidget.count(dialog._list)
    return {
        "error": error,
        "headline": dialog._headline.text(),
        "items": [
            QtWidgets.QListWidget.item(dialog._list, row).text() for row in range(rows)
        ],
        "item_count": rows,
        "cancel_enabled": dialog._cancel_btn.isEnabled(),
        "close_enabled": dialog._close_btn.isEnabled(),
        "calls": [list(call) for call in calls],
    }


def snapshot_new(model, error):
    """Every output the view model carries after the same step."""
    return {
        "error": error,
        "headline": model.headline,
        "items": list(model.items),
        "item_count": len(model.items),
        "cancel_enabled": model.cancel_enabled,
        "close_enabled": model.close_enabled,
        "calls": [list(call) for call in model.calls],
    }


def run_step_old(dialog, step):
    if step[0] == PROGRESS:
        dialog._handle_progress_main_thread(step[1], step[2], step[3], step[4])
    elif step[0] == REPLACE:
        dialog._replace_last_matching(step[1], step[2])
    elif step[0] == CANCEL:
        dialog._bot_manager = make_manager(step[1])
        dialog._on_cancel()
    elif step[0] == CLOSE:
        from PySide6.QtGui import QCloseEvent

        dialog._unsub = make_unsubscriber(step[1])
        dialog.closeEvent(QCloseEvent())


def run_step_new(model, step):
    if step[0] == PROGRESS:
        model.handle_progress(step[1], step[2], step[3], step[4])
    elif step[0] == REPLACE:
        model.replace_last_matching(step[1], step[2])
    elif step[0] == CANCEL:
        model.cancel(make_manager(step[1]))
    elif step[0] == CLOSE:
        surface.unsubscribe(make_unsubscriber(step[1]))


def fresh_dialog():
    """A dialog off the shipped constructor, with its bus handler dropped."""
    app()
    dialog = qt_dialog.StartAllProgressDialog(object())
    if callable(dialog._unsub):
        dialog._unsub()
    dialog._unsub = None
    return dialog


def build_dialog(monkeypatch):
    """A dialog whose bus handler is dropped as soon as it is built."""
    dialog = fresh_dialog()
    return dialog, trace_dialog(dialog, monkeypatch)


def run_old(script, monkeypatch):
    """Drive ``StartAllProgressDialog`` through the script, step by step."""
    dialog, calls = build_dialog(monkeypatch)
    trace = [snapshot_old(dialog, calls, None)]
    for step in script:
        error = None
        try:
            run_step_old(dialog, step)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        trace.append(snapshot_old(dialog, calls, error))
    return trace


def run_new(script):
    """Drive the view model through the same script, step by step."""
    model = surface.StartAllProgressModel()
    trace = [snapshot_new(model, None)]
    for step in script:
        error = None
        try:
            run_step_new(model, step)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        trace.append(snapshot_new(model, error))
    return trace


HAPPY_SCRIPT = [
    (PROGRESS, "begin", 3, 0, ""),
    (PROGRESS, "bot_starting", 3, 0, "bot-a"),
    (PROGRESS, "bot_started", 3, 1, "bot-a"),
    (PROGRESS, "bot_starting", 3, 1, "bot-b"),
    (PROGRESS, "bot_started", 3, 2, "bot-b"),
    (PROGRESS, "bot_starting", 3, 2, "bot-c"),
    (PROGRESS, "bot_started", 3, 3, "bot-c"),
    (PROGRESS, "done", 3, 3, ""),
]

NO_BOTS_SCRIPT = [
    (PROGRESS, "begin", 0, 0, ""),
    (PROGRESS, "done", 0, 0, ""),
]

TIMEOUT_SCRIPT = [
    (PROGRESS, "begin", 2, 0, ""),
    (PROGRESS, "bot_starting", 2, 0, "slow-bot"),
    (PROGRESS, "bot_timeout", 2, 0, "slow-bot"),
    (PROGRESS, "bot_starting", 2, 0, "fast-bot"),
    (PROGRESS, "bot_started", 2, 1, "fast-bot"),
    (PROGRESS, "done", 2, 1, ""),
]

CANCELLED_SCRIPT = [
    (PROGRESS, "begin", 4, 0, ""),
    (PROGRESS, "bot_starting", 4, 0, "bot-a"),
    (PROGRESS, "bot_started", 4, 1, "bot-a"),
    (CANCEL, MANAGER_OK),
    (PROGRESS, "cancelled", 4, 1, ""),
]

CANCEL_REFUSED_SCRIPT = [
    (PROGRESS, "begin", 2, 0, ""),
    (CANCEL, MANAGER_RAISES),
    (CANCEL, MANAGER_NO_METHOD),
    (CANCEL, MANAGER_NONE),
    (CANCEL, MANAGER_OK),
]

EMPTY_BOT_ID_SCRIPT = [
    (PROGRESS, "begin", 2, 0, ""),
    (PROGRESS, "bot_starting", 2, 0, ""),
    (PROGRESS, "bot_started", 2, 1, ""),
    (PROGRESS, "bot_timeout", 2, 1, ""),
    (PROGRESS, "cancelled", 2, 1, ""),
]

NO_MATCH_SCRIPT = [
    (PROGRESS, "begin", 2, 0, ""),
    (PROGRESS, "bot_started", 2, 1, "never-listed"),
    (PROGRESS, "bot_timeout", 2, 1, "also-never-listed"),
]

SUBSTRING_SCRIPT = [
    (PROGRESS, "begin", 3, 0, ""),
    (PROGRESS, "bot_starting", 3, 0, "bot-1"),
    (PROGRESS, "bot_starting", 3, 0, "bot-10"),
    (PROGRESS, "bot_started", 3, 1, "bot-1"),
    (PROGRESS, "bot_started", 3, 2, "bot-10"),
    (PROGRESS, "bot_timeout", 3, 2, "bot-1"),
]

EARLIER_ROW_SCRIPT = [
    (PROGRESS, "begin", 3, 0, ""),
    (PROGRESS, "bot_starting", 3, 0, "alpha"),
    (PROGRESS, "bot_starting", 3, 0, "beta"),
    (PROGRESS, "bot_starting", 3, 0, "gamma"),
    (PROGRESS, "bot_started", 3, 1, "alpha"),
    (PROGRESS, "bot_timeout", 3, 1, "beta"),
]

UNKNOWN_PHASE_SCRIPT = [
    (PROGRESS, "begin", 2, 0, ""),
    (PROGRESS, "", 2, 0, "bot-a"),
    (PROGRESS, "started", 2, 0, "bot-a"),
    (PROGRESS, "BEGIN", 2, 0, "bot-a"),
    (PROGRESS, "bot_startin", 2, 0, "bot-a"),
    (PROGRESS, "done ", 2, 0, ""),
]

REPLACE_DIRECT_SCRIPT = [
    (PROGRESS, "begin", 2, 0, ""),
    (REPLACE, "orphan", "first line"),
    (REPLACE, "orphan", "second line"),
    (REPLACE, "", "empty id claims the last line"),
    (REPLACE, "line", "substring of an existing line"),
]

REPLACE_ON_EMPTY_SCRIPT = [
    (REPLACE, "nothing-here", "appended to an empty list"),
    (REPLACE, "nothing-here", "now it matches"),
]

RESTART_SCRIPT = [
    (PROGRESS, "begin", 2, 0, ""),
    (PROGRESS, "bot_starting", 2, 0, "bot-a"),
    (PROGRESS, "bot_started", 2, 1, "bot-a"),
    (PROGRESS, "begin", 5, 0, ""),
    (PROGRESS, "bot_starting", 5, 0, "bot-z"),
]

NUMBERS_SCRIPT = [
    (PROGRESS, "begin", -1, 0, ""),
    (PROGRESS, "bot_started", -1, -3, "bot-a"),
    (PROGRESS, "bot_starting", 1000000, 999999, "bot-b"),
    (PROGRESS, "cancelled", 0, 0, ""),
    (PROGRESS, "done", -1, -1, ""),
]

TEXT_SCRIPT = [
    (PROGRESS, "begin", 3, 0, ""),
    (PROGRESS, "bot_starting", 3, 0, "unicode-Δ→⚡"),
    (PROGRESS, "bot_started", 3, 1, "unicode-Δ→⚡"),
    (PROGRESS, "bot_starting", 3, 1, "x" * 200),
    (PROGRESS, "bot_timeout", 3, 1, "x" * 200),
    (PROGRESS, "bot_starting", 3, 1, "a b<c>&d"),
    (PROGRESS, "bot_started", 3, 2, "a b<c>&d"),
]

GLYPH_COLLISION_SCRIPT = [
    (PROGRESS, "begin", 2, 0, ""),
    (PROGRESS, "bot_starting", 2, 0, "⏳"),
    (PROGRESS, "bot_starting", 2, 0, "plain"),
    (PROGRESS, "bot_started", 2, 1, "⏳"),
]

CLOSE_SCRIPT = [
    (PROGRESS, "begin", 1, 0, ""),
    (CLOSE, UNSUB_OK),
    (CLOSE, UNSUB_RAISES),
    (CLOSE, UNSUB_NONE),
    (CLOSE, UNSUB_NOT_CALLABLE),
    (CLOSE, UNSUB_BOOL_RAISES),
]

EMPTY_SCRIPT: list[tuple] = []

SCRIPTS = {
    "cancel_refused": CANCEL_REFUSED_SCRIPT,
    "cancelled": CANCELLED_SCRIPT,
    "close": CLOSE_SCRIPT,
    "earlier_row": EARLIER_ROW_SCRIPT,
    "empty": EMPTY_SCRIPT,
    "empty_bot_id": EMPTY_BOT_ID_SCRIPT,
    "glyph_collision": GLYPH_COLLISION_SCRIPT,
    "happy": HAPPY_SCRIPT,
    "no_bots": NO_BOTS_SCRIPT,
    "no_match": NO_MATCH_SCRIPT,
    "numbers": NUMBERS_SCRIPT,
    "replace_direct": REPLACE_DIRECT_SCRIPT,
    "replace_on_empty": REPLACE_ON_EMPTY_SCRIPT,
    "restart": RESTART_SCRIPT,
    "substring": SUBSTRING_SCRIPT,
    "text": TEXT_SCRIPT,
    "timeout": TIMEOUT_SCRIPT,
    "unknown_phase": UNKNOWN_PHASE_SCRIPT,
}


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_old_and_new_traces_are_identical(name, monkeypatch):
    """A step of the script leaves the two sides in a different state."""
    old = run_old(SCRIPTS[name], monkeypatch)
    new = run_new(SCRIPTS[name])
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_the_trace_holds_the_whole_dialog(name, monkeypatch):
    """The comparison passed by measuring nothing."""
    old = run_old(SCRIPTS[name], monkeypatch)
    assert len(old) == len(SCRIPTS[name]) + 1
    first = old[0]
    assert first["headline"] == "Preparing to auto-start bots..."
    assert first["items"] == []
    assert first["cancel_enabled"] is True
    assert first["close_enabled"] is False
    assert first["calls"] == []
    for step in old:
        assert step["item_count"] == len(step["items"])
        assert isinstance(step["headline"], str)
    if SCRIPTS[name]:
        assert old[-1]["calls"] != []


def test_the_scripts_reach_every_documented_state():
    """A named state was never driven, so its parity was never compared."""
    phases = {step[1] for script in SCRIPTS.values() for step in script}
    for phase in surface.PHASES:
        assert phase in phases, phase
    reached = {
        "empty_list": False,
        "part_way": False,
        "complete": False,
        "cancelled": False,
        "cancel_failed": False,
        "no_bots": False,
        "timeout_line": False,
        "close_scheduled": False,
    }
    for script in SCRIPTS.values():
        for step in run_new(script):
            if not step["items"] and step["calls"]:
                reached["empty_list"] = True
            if step["items"] and step["cancel_enabled"]:
                reached["part_way"] = True
            if step["headline"].startswith("Done — "):
                reached["complete"] = True
            if step["headline"].startswith("Cancelled — "):
                reached["cancelled"] = True
            if step["headline"] == surface.HEADLINE_CANCEL_FAILED:
                reached["cancel_failed"] = True
            if step["headline"] == surface.HEADLINE_NO_BOTS:
                reached["no_bots"] = True
            if any("⚠" in text for text in step["items"]):
                reached["timeout_line"] = True
            if any(call[0] == "closeAfter" for call in step["calls"]):
                reached["close_scheduled"] = True
    assert all(reached.values()), reached


def test_every_headline_the_dialog_can_write_is_reached(monkeypatch):
    """A headline string was never produced, so it was never compared."""
    written = set()
    for name in SCRIPTS:
        for step in run_old(SCRIPTS[name], monkeypatch):
            for call in step["calls"]:
                if call[0] == "headline.setText":
                    written.add(call[1])
    assert surface.HEADLINE_NO_BOTS in written
    assert surface.HEADLINE_CANCELLING in written
    assert surface.HEADLINE_CANCEL_FAILED in written
    assert "Auto-starting 3 bots (0/3 verified)" in written
    assert "Auto-starting 3 bots (1/3 verified)" in written
    assert "Auto-starting 3 bots (0/3 verified, starting bot-a...)" in written
    assert "Done — 3 bot(s) processed." in written
    assert "Cancelled — 1/4 bots had started." in written


def test_the_auto_close_delays_match(monkeypatch):
    """An auto-close delay drifted from the dialog's own."""
    old = run_old(NO_BOTS_SCRIPT, monkeypatch)
    new = run_new(NO_BOTS_SCRIPT)
    assert old[1]["calls"][-1] == ["closeAfter", 800]
    assert old[2]["calls"][-1] == ["closeAfter", 2000]
    assert new[1]["calls"] == old[1]["calls"]
    assert new[2]["calls"] == old[2]["calls"]
    assert surface.NO_BOTS_CLOSE_DELAY_MS == 800
    assert surface.DONE_CLOSE_DELAY_MS == 2000
    assert surface.NO_BOTS_CLOSE_DELAY_MS != surface.DONE_CLOSE_DELAY_MS


def test_a_longer_bot_id_claims_the_line_of_a_shorter_one(monkeypatch):
    """The substring match picked a different line on the two sides."""
    old = run_old(SUBSTRING_SCRIPT, monkeypatch)
    new = run_new(SUBSTRING_SCRIPT)
    assert old[3]["items"] == [
        "⏳ bot-1 (starting...)",
        "⏳ bot-10 (starting...)",
    ]
    assert old[4]["items"] == ["⏳ bot-1 (starting...)", "✓ bot-1"]
    assert old[5]["items"] == ["⏳ bot-1 (starting...)", "✓ bot-1", "✓ bot-10"]
    assert old[6]["items"] == [
        "⏳ bot-1 (starting...)",
        "✓ bot-1",
        "⚠ bot-1 (start verify timed out — may still come up)",
    ]
    assert [step["items"] for step in new] == [step["items"] for step in old]


def test_a_bot_with_no_line_gains_one(monkeypatch):
    """A bot the list never showed was lost instead of appended."""
    old = run_old(NO_MATCH_SCRIPT, monkeypatch)
    new = run_new(NO_MATCH_SCRIPT)
    assert old[2]["items"] == ["✓ never-listed"]
    assert old[3]["items"] == [
        "✓ never-listed",
        "⚠ also-never-listed (start verify timed out — may still come up)",
    ]
    assert new[2]["items"] == old[2]["items"]
    assert new[3]["items"] == old[3]["items"]


def test_begin_clears_the_list_and_bot_timeout_leaves_the_headline(monkeypatch):
    """A restart kept old lines, or a timeout rewrote the headline."""
    old = run_old(RESTART_SCRIPT, monkeypatch)
    new = run_new(RESTART_SCRIPT)
    assert old[3]["items"] == ["✓ bot-a"]
    assert old[4]["items"] == []
    assert old[4]["headline"] == "Auto-starting 5 bots (0/5 verified)"
    assert new[4] == old[4]
    timed_out = run_old(TIMEOUT_SCRIPT, monkeypatch)
    assert timed_out[2]["headline"] == timed_out[3]["headline"]
    assert timed_out[3]["items"] == [
        "⚠ slow-bot (start verify timed out — may still come up)"
    ]
    assert run_new(TIMEOUT_SCRIPT)[3] == timed_out[3]


def test_a_phase_the_dialog_does_not_name_changes_nothing(monkeypatch):
    """An unnamed phase moved the dialog on one of the two sides."""
    old = run_old(UNKNOWN_PHASE_SCRIPT, monkeypatch)
    new = run_new(UNKNOWN_PHASE_SCRIPT)
    for index in range(2, len(old)):
        assert old[index] == old[1], index
    assert new == old


def test_a_refused_cancel_says_so(monkeypatch):
    """A refused cancel left the dialog claiming it was cancelling."""
    old = run_old(CANCEL_REFUSED_SCRIPT, monkeypatch)
    new = run_new(CANCEL_REFUSED_SCRIPT)
    for index in (2, 3, 4):
        assert old[index]["headline"] == surface.HEADLINE_CANCEL_FAILED
        assert old[index]["cancel_enabled"] is False
    assert old[5]["headline"] == surface.HEADLINE_CANCELLING
    assert old[5]["cancel_enabled"] is False
    assert new == old


DROPPED_EVENTS = {
    "plain": {"phase": "begin", "total": 3, "started": 0, "bot_id": "bot-a"},
    "missing_all": {},
    "missing_bot_id": {"phase": "done", "total": 2, "started": 2},
    "bot_id_none": {"phase": "bot_started", "total": 1, "started": 1, "bot_id": None},
    "bot_id_zero": {"phase": "bot_started", "total": 1, "started": 1, "bot_id": 0},
    "bot_id_number": {"phase": "bot_started", "total": 1, "started": 1, "bot_id": 77},
    "numeric_strings": {"phase": "begin", "total": "5", "started": "2", "bot_id": ""},
    "float_total": {"phase": "begin", "total": 3.7, "started": -2.9, "bot_id": ""},
    "boolean_total": {"phase": "begin", "total": True, "started": False, "bot_id": ""},
    "total_not_a_number": {"phase": "begin", "total": "not-a-number"},
    "total_none": {"phase": "begin", "total": None},
    "started_none": {"phase": "begin", "total": 1, "started": None},
    "total_is_a_list": {"phase": "begin", "total": [1]},
}


class _NoGet:
    pass


class _GetRaisesValueError:
    def get(self, _key, _default=None):
        raise ValueError("payload refused the read")


class _GetRaisesTypeError:
    def get(self, _key, _default=None):
        raise TypeError("payload refused the read")


class _GetRaisesKeyError:
    def get(self, _key, _default=None):
        raise KeyError("payload refused the read")


UNREADABLE_EVENTS = {
    "no_get": _NoGet(),
    "get_raises_value": _GetRaisesValueError(),
    "get_raises_type": _GetRaisesTypeError(),
}


class _SignalRecorder:
    """Stands in for the Qt signal so the read is compared, not the emit."""

    def __init__(self):
        self.emitted: list[tuple] = []

    def emit(self, *args):
        self.emitted.append(args)


def read_old(payload, capture_log):
    """Drive ``_on_progress_event`` on a duck-typed dialog."""
    recorder = _SignalRecorder()
    host = type("Host", (), {"_progress_signal": recorder})()
    with capture_log(LOGGER_NAME) as records:
        qt_dialog.StartAllProgressDialog._on_progress_event(
            host, Event(topic=surface.TOPIC, data=payload)
        )
    return recorder.emitted, [record.getMessage() for record in records]


def read_new(payload, capture_log):
    """Drive ``progress_fields`` on the same payload."""
    with capture_log(LOGGER_NAME) as records:
        fields = surface.progress_fields(payload)
    emitted = [] if fields is None else [fields]
    return emitted, [record.getMessage() for record in records]


@pytest.mark.parametrize("name", sorted(DROPPED_EVENTS))
def test_the_two_sides_read_one_event_the_same_way(name, capture_log):
    """The surface read a different value off the event than the dialog."""
    payload = DROPPED_EVENTS[name]
    old_fields, old_logs = read_old(payload, capture_log)
    new_fields, new_logs = read_new(payload, capture_log)
    assert new_fields == old_fields
    assert new_logs == old_logs


@pytest.mark.parametrize("name", sorted(UNREADABLE_EVENTS))
def test_an_event_neither_side_can_read_is_logged_and_dropped(name, capture_log):
    """An unreadable event raised, or was dropped without a trace."""
    payload = UNREADABLE_EVENTS[name]
    old_fields, old_logs = read_old(payload, capture_log)
    new_fields, new_logs = read_new(payload, capture_log)
    assert old_fields == []
    assert new_fields == old_fields
    assert new_logs == old_logs
    assert len(new_logs) == 1
    assert new_logs[0].startswith("Start All progress event dropped (")


def test_a_key_error_reaches_the_caller_on_both_sides(capture_log):
    """One side swallowed an exception the other let out."""
    payload = _GetRaisesKeyError()
    with pytest.raises(KeyError):
        read_old(payload, capture_log)
    with pytest.raises(KeyError):
        read_new(payload, capture_log)


def test_the_read_reaches_every_field_default(capture_log):
    """A default was never exercised, so a drift in it would not show."""
    fields, logs = read_new({}, capture_log)
    assert fields == [("", 0, 0, "")]
    assert logs == []
    kept, _ = read_new(DROPPED_EVENTS["plain"], capture_log)
    assert kept == [("begin", 3, 0, "bot-a")]
    zero, _ = read_new(DROPPED_EVENTS["bot_id_zero"], capture_log)
    assert zero == [("bot_started", 1, 1, "")]
    number, _ = read_new(DROPPED_EVENTS["bot_id_number"], capture_log)
    assert number == [("bot_started", 1, 1, "77")]
    truncated, _ = read_new(DROPPED_EVENTS["float_total"], capture_log)
    assert truncated == [("begin", 3, -2, "")]


CLOSE_SPECS = (UNSUB_OK, UNSUB_RAISES, UNSUB_NONE, UNSUB_NOT_CALLABLE)


@pytest.mark.parametrize("spec", CLOSE_SPECS + (UNSUB_BOOL_RAISES,))
def test_closing_drops_the_handler_the_same_way(spec, capture_log, monkeypatch):
    """A close leaked the handler on one side, or logged differently."""
    from PySide6.QtGui import QCloseEvent

    dialog, _ = build_dialog(monkeypatch)
    ran: list[str] = []

    def watched():
        ran.append("old")

    dialog._unsub = watched if spec == UNSUB_OK else make_unsubscriber(spec)
    with capture_log(LOGGER_NAME) as old_records:
        dialog.closeEvent(QCloseEvent())
    old_logs = [record.getMessage() for record in old_records]

    def watched_new():
        ran.append("new")

    with capture_log(LOGGER_NAME) as new_records:
        surface.unsubscribe(
            watched_new if spec == UNSUB_OK else make_unsubscriber(spec)
        )
    new_logs = [record.getMessage() for record in new_records]
    assert new_logs == old_logs
    if spec == UNSUB_OK:
        assert ran == ["old", "new"]
    else:
        assert ran == []
    if spec in (UNSUB_RAISES, UNSUB_BOOL_RAISES):
        assert len(old_logs) == 1
        assert old_logs[0].startswith(
            "Start All progress unsubscribe failed, handler leaked: "
        )
    else:
        assert old_logs == []


@pytest.mark.parametrize("spec", (MANAGER_OK, MANAGER_RAISES, MANAGER_NO_METHOD))
def test_cancelling_logs_the_same_way(spec, capture_log, monkeypatch):
    """A refused cancel logged on one side and stayed silent on the other."""
    dialog, _ = build_dialog(monkeypatch)
    dialog._bot_manager = make_manager(spec)
    with capture_log(LOGGER_NAME) as old_records:
        dialog._on_cancel()
    old_logs = [record.getMessage() for record in old_records]
    model = surface.StartAllProgressModel()
    with capture_log(LOGGER_NAME) as new_records:
        model.cancel(make_manager(spec))
    new_logs = [record.getMessage() for record in new_records]
    assert new_logs == old_logs
    if spec == MANAGER_OK:
        assert old_logs == []
    else:
        assert len(old_logs) == 1
        assert old_logs[0].startswith("cancel_start_all failed: ")


def test_the_manager_is_asked_exactly_once(monkeypatch):
    """The cancel reached the manager a different number of times."""
    dialog, _ = build_dialog(monkeypatch)
    old_manager = _Manager()
    dialog._bot_manager = old_manager
    dialog._on_cancel()
    new_manager = _Manager()
    surface.StartAllProgressModel().cancel(new_manager)
    assert old_manager.calls == 1
    assert new_manager.calls == old_manager.calls


def test_widget_properties_match_the_dialog(monkeypatch):
    """A dialog property drifted from the value the surface reports."""
    dialog, _ = build_dialog(monkeypatch)
    assert surface.WIDGET == {
        "accessible_name": dialog.accessibleName(),
        "window_title": dialog.windowTitle(),
        "modal": dialog.isModal(),
        "minimum_width_px": dialog.minimumWidth(),
        "size_px": [dialog.width(), dialog.height()],
        "style_sheet": dialog.styleSheet(),
    }
    assert surface.ACCESSIBLE_NAME == "Start All Progress Dialog"
    assert surface.WINDOW_TITLE == "Auto-starting bots"
    assert surface.MODAL is False
    assert surface.MINIMUM_WIDTH_PX == 420
    assert surface.SIZE_PX == (520, 360)
    from qt_pixel import render_widget

    assert_pictures_match(
        old_side=render_widget(dialog, PIXEL_SIZE),
        new_side=render_widget(
            dialog_painted_by_the_model(model_payload(PIXEL_SCRIPTS["fresh"])),
            PIXEL_SIZE,
        ),
    )
    from PySide6.QtWidgets import QDialog

    bare = QDialog()
    assert bare.accessibleName() != surface.ACCESSIBLE_NAME
    assert bare.windowTitle() != surface.WINDOW_TITLE
    assert bare.isModal() is False
    assert bare.minimumWidth() != surface.MINIMUM_WIDTH_PX
    assert bare.styleSheet() != surface.STYLE_SHEET


def test_layout_matches_the_dialog(monkeypatch):
    """A margin, a spacing or a stretch drifted from the dialog's own."""
    dialog, _ = build_dialog(monkeypatch)
    layout = dialog.layout()
    margins = layout.contentsMargins()
    assert surface.LAYOUT["margins_px"] == [
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ]
    assert surface.LAYOUT["spacing_px"] == layout.spacing()
    assert surface.LAYOUT["child_stretch"] == [
        layout.stretch(index) for index in range(layout.count())
    ]
    assert len(surface.LAYOUT["order"]) == layout.count() == 4
    row = layout.itemAt(3).layout()
    assert surface.BUTTON_ROW["leading_stretch"] == row.stretch(0)
    assert len(surface.BUTTON_ROW["order"]) == row.count() == 3
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    holder = QWidget()
    bare = QVBoxLayout(holder)
    bare_margins = bare.contentsMargins()
    assert [
        bare_margins.left(),
        bare_margins.top(),
        bare_margins.right(),
        bare_margins.bottom(),
    ] != surface.LAYOUT["margins_px"]
    assert bare.spacing() != surface.LAYOUT["spacing_px"]


def test_the_headline_and_subline_match_the_dialog(monkeypatch):
    """A label's text, font or skin drifted from the dialog's own."""
    dialog, _ = build_dialog(monkeypatch)
    headline_font = dialog._headline.font()
    assert surface.HEADLINE == {
        "initial_text": dialog._headline.text(),
        "point_size": headline_font.pointSize(),
        "bold": headline_font.bold(),
    }
    assert surface.SUBLINE == {
        "text": dialog._subline.text(),
        "word_wrap": dialog._subline.wordWrap(),
        "style_sheet": dialog._subline.styleSheet(),
    }
    from PySide6.QtWidgets import QLabel

    bare = QLabel("")
    assert bare.font().pointSize() != surface.HEADLINE["point_size"]
    assert bare.font().bold() != surface.HEADLINE["bold"]
    assert bare.wordWrap() != surface.SUBLINE["word_wrap"]
    assert bare.styleSheet() != surface.SUBLINE["style_sheet"]
    assert "~2.5-second" in surface.SUBLINE_TEXT
    assert "Cancel to abort the remaining bots" in surface.SUBLINE_TEXT
    from qt_pixel import render_widget

    assert_pictures_match(
        old_side=render_widget(dialog, PIXEL_SIZE),
        new_side=render_widget(
            dialog_painted_by_the_model(model_payload(PIXEL_SCRIPTS["fresh"])),
            PIXEL_SIZE,
        ),
    )


def test_the_buttons_match_the_dialog(monkeypatch):
    """A button's text or its starting state drifted from the dialog."""
    dialog, _ = build_dialog(monkeypatch)
    assert surface.BUTTONS == {
        "cancel": {
            "text": dialog._cancel_btn.text(),
            "enabled": dialog._cancel_btn.isEnabled(),
        },
        "close": {
            "text": dialog._close_btn.text(),
            "enabled": dialog._close_btn.isEnabled(),
        },
    }
    assert surface.CANCEL_TEXT == "Cancel remaining"
    assert surface.CLOSE_TEXT == "Close"
    assert surface.CANCEL_ENABLED_AT_START is True
    assert surface.CLOSE_ENABLED_AT_START is False


METHOD_MAP = {
    "_setup_ui": "WIDGET",
    "_on_progress_event": "progress_fields",
    "_handle_progress_main_thread": "handle_progress",
    "_replace_last_matching": "replace_last_matching",
    "_on_cancel": "cancel",
    "closeEvent": "unsubscribe",
}


CALL_NAMES = {
    "HEADLINE_SET_TEXT": "headline.setText",
    "LIST_CLEAR": "list.clear",
    "LIST_ADD_ITEM": "list.addItem",
    "LIST_COUNT": "list.count",
    "LIST_ITEM": "list.item",
    "LIST_SET_ITEM_TEXT": "list.setItemText",
    "LIST_SCROLL_TO_BOTTOM": "list.scrollToBottom",
    "CANCEL_SET_ENABLED": "cancel.setEnabled",
    "CLOSE_SET_ENABLED": "close.setEnabled",
    "CLOSE_AFTER": "closeAfter",
}


def test_the_call_names_are_the_ones_the_trace_writes():
    """The trace and the surface stopped agreeing on what to call a call.

    The Qt side of the trace writes these ten labels as literals, so a
    label read out of the surface cannot make both sides agree by
    definition.
    """
    for constant, literal in CALL_NAMES.items():
        assert getattr(surface, constant) == literal, constant
    assert len(set(CALL_NAMES.values())) == 10


def test_every_dialog_method_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    dialog_methods = {
        name
        for name, value in vars(qt_dialog.StartAllProgressDialog).items()
        if callable(value) and name not in ("__init__", "_progress_signal")
    }
    assert dialog_methods == set(METHOD_MAP)
    assert callable(surface.progress_fields)
    assert callable(surface.unsubscribe)
    for target in ("handle_progress", "replace_last_matching", "cancel"):
        assert callable(getattr(surface.StartAllProgressModel, target))


CLICKED_SIGNAL = "2clicked()"
PROGRESS_SIGNAL = "2_progress_signal(QString,int,int,QString)"


def test_the_connect_sites_match_the_actions(monkeypatch):
    """A signal wiring appeared on one side and not the other."""
    from PySide6.QtWidgets import QPushButton

    dialog, _ = build_dialog(monkeypatch)
    live = (
        dialog._cancel_btn.receivers(CLICKED_SIGNAL)
        + dialog._close_btn.receivers(CLICKED_SIGNAL)
        + dialog.receivers(PROGRESS_SIGNAL)
    )
    assert dialog._cancel_btn.receivers(CLICKED_SIGNAL) == 1
    assert dialog._close_btn.receivers(CLICKED_SIGNAL) == 1
    assert dialog.receivers(PROGRESS_SIGNAL) == 1
    assert QPushButton("bare").receivers(CLICKED_SIGNAL) == 0
    assert live == len(surface.ACTIONS) == 3
    assert set(surface.ACTIONS) == {
        "cancel.clicked",
        "close.clicked",
        "progress.received",
    }
    assert surface.ACTIONS["cancel.clicked"] == "cancel"
    assert surface.ACTIONS["close.clicked"] == "accept"
    assert surface.ACTIONS["progress.received"] == "handle_progress"


def test_clicking_cancel_reaches_the_bot_manager(monkeypatch):
    """The button reading ``CANCEL_TEXT`` reaches ``cancel_start_all``."""
    dialog, _ = build_dialog(monkeypatch)
    manager = _Manager()
    dialog._bot_manager = manager
    assert dialog._cancel_btn.text() == surface.CANCEL_TEXT
    assert manager.calls == 0
    dialog._cancel_btn.click()
    assert manager.calls == 1


def test_clicking_close_accepts_the_dialog(monkeypatch):
    """The button reading ``CLOSE_TEXT`` reaches ``accept``."""
    dialog, _ = build_dialog(monkeypatch)
    dialog._close_btn.setEnabled(True)
    assert dialog._close_btn.text() == surface.CLOSE_TEXT
    accepted = []
    monkeypatch.setattr(type(dialog), "accept", lambda _self: accepted.append(True))
    assert accepted == []
    dialog._close_btn.click()
    assert accepted == [True]


def test_the_progress_signal_reaches_the_main_thread_handler(monkeypatch):
    """``_progress_signal`` carries one event to ``_handle_progress_main_thread``."""
    dialog, _ = build_dialog(monkeypatch)
    assert dialog._headline.text() == surface.HEADLINE_INITIAL_TEXT
    dialog._progress_signal.emit("begin", 3, 0, "")
    assert dialog._headline.text() == surface.HEADLINE_BEGIN.format(total=3)


class _RecordingBus:
    """A bus that records what subscribes and what is emitted."""

    def __init__(self):
        self.subscribed: list[str] = []
        self.emitted: list[tuple[str, dict]] = []

    def subscribe(self, topic, handler):
        self.subscribed.append(topic)
        del handler
        return lambda: None

    def emit(self, topic, **kwargs):
        self.emitted.append((topic, dict(kwargs)))


def test_the_dialog_subscribes_to_the_topic_the_surface_names(monkeypatch):
    """``StartAllProgressDialog`` listens on ``surface.TOPIC``."""
    from src.core import event_bus

    app()
    bus = _RecordingBus()
    monkeypatch.setattr(event_bus, "get_event_bus", lambda: bus)
    dialog = qt_dialog.StartAllProgressDialog(object())
    assert dialog.windowTitle() == surface.WINDOW_TITLE
    assert bus.subscribed == [surface.TOPIC]
    assert surface.TOPIC == "bot_manager.start_all_progress"


class _StartableBot:
    """A bot that reaches RUNNING as soon as ``start`` is awaited."""

    def __init__(self, bot_id, verifies=True):
        from src.trading.bot_container import BotState

        self.bot_id = bot_id
        self.state = BotState.IDLE
        self._verifies = verifies
        self._running = BotState.RUNNING

    async def start(self):
        if self._verifies:
            self.state = self._running


def _phases_emitted(bots, verify_timeout_seconds=10.0):
    """Topics and phases the real ``BotManager.start_all`` emits."""
    import asyncio

    from src.trading.bot_container import BotManager

    bus = _RecordingBus()
    manager = BotManager(bus=bus)
    manager._bots = {bot.bot_id: bot for bot in bots}
    bus.emitted.clear()
    asyncio.run(
        manager.start_all(
            verify_timeout_seconds=verify_timeout_seconds, min_gap_seconds=0.0
        )
    )
    return bus.emitted


def test_the_engine_emits_the_topic_the_surface_names():
    """The fleet's own ``start_all`` publishes on ``surface.TOPIC``."""
    emitted = _phases_emitted([_StartableBot("bot-a")])
    assert emitted, "start_all emitted nothing at all"
    assert {topic for topic, _ in emitted} == {surface.TOPIC}


def test_the_engine_emits_every_phase_the_surface_answers():
    """Each phase the surface handles is one the engine really sends."""
    verified = [
        phase
        for _t, data in _phases_emitted([_StartableBot("bot-a")])
        for phase in [data.get("phase")]
    ]
    timed_out = [
        phase
        for _t, data in _phases_emitted(
            [_StartableBot("slow", verifies=False)], verify_timeout_seconds=0.0
        )
        for phase in [data.get("phase")]
    ]
    seen = set(verified) | set(timed_out)
    for phase in ("begin", "bot_starting", "bot_started", "bot_timeout", "done"):
        assert phase in seen, f"start_all never emitted {phase!r}; it sent {seen}"


def test_the_dialog_paints_the_headline_each_phase_names(monkeypatch):
    """A phase wrote a headline the operator does not read on screen."""
    dialog, _ = build_dialog(monkeypatch)
    assert dialog._headline.text() == "Preparing to auto-start bots..."
    dialog._handle_progress_main_thread(surface.BEGIN, 3, 0, "")
    assert dialog._headline.text() == "Auto-starting 3 bots (0/3 verified)"
    dialog._handle_progress_main_thread(surface.BOT_STARTING, 3, 0, "bot-a")
    assert dialog._headline.text() == (
        "Auto-starting 3 bots (0/3 verified, starting bot-a...)"
    )
    dialog._handle_progress_main_thread(surface.BOT_STARTED, 3, 1, "bot-a")
    assert dialog._headline.text() == "Auto-starting 3 bots (1/3 verified)"
    dialog._handle_progress_main_thread(surface.DONE, 3, 3, "")
    assert dialog._headline.text() == "Done — 3 bot(s) processed."
    dialog._handle_progress_main_thread(surface.CANCELLED, 3, 2, "")
    assert dialog._headline.text() == "Cancelled — 2/3 bots had started."
    empty, _ = build_dialog(monkeypatch)
    empty._handle_progress_main_thread(surface.BEGIN, 0, 0, "")
    assert empty._headline.text() == "No bots to auto-start."


def test_the_dialog_paints_the_bot_line_each_phase_names(monkeypatch):
    """A bot line reached the list reading something else."""
    dialog, _ = build_dialog(monkeypatch)
    dialog._handle_progress_main_thread(surface.BEGIN, 2, 0, "")
    assert dialog._list.count() == 0
    dialog._handle_progress_main_thread(surface.BOT_STARTING, 2, 0, "bot-a")
    assert dialog._list.item(0).text() == "⏳ bot-a (starting...)"
    dialog._handle_progress_main_thread(surface.BOT_STARTED, 2, 1, "bot-a")
    assert dialog._list.item(0).text() == "✓ bot-a"
    dialog._handle_progress_main_thread(surface.BOT_TIMEOUT, 2, 1, "bot-a")
    assert dialog._list.item(0).text() == (
        "⚠ bot-a (start verify timed out — may still come up)"
    )


SENTINEL_WORDS = {
    "ACCESSIBLE_NAME": "sentinel accessible name",
    "WINDOW_TITLE": "sentinel window title",
    "HEADLINE_INITIAL_TEXT": "sentinel headline",
    "CANCEL_TEXT": "sentinel cancel",
    "CLOSE_TEXT": "sentinel close",
}


def words_the_dialog_paints(dialog):
    """The five words a fresh dialog puts on screen, keyed by surface name."""
    return {
        "ACCESSIBLE_NAME": dialog.accessibleName(),
        "WINDOW_TITLE": dialog.windowTitle(),
        "HEADLINE_INITIAL_TEXT": dialog._headline.text(),
        "CANCEL_TEXT": dialog._cancel_btn.text(),
        "CLOSE_TEXT": dialog._close_btn.text(),
    }


def test_a_fresh_dialog_paints_the_surfaces_five_words():
    """The dialog put a word on screen the surface does not declare."""
    painted = words_the_dialog_paints(fresh_dialog())
    assert painted == {name: getattr(surface, name) for name in SENTINEL_WORDS}
    assert painted["WINDOW_TITLE"] == "Auto-starting bots"


def test_rewriting_a_surface_word_rewrites_what_the_dialog_paints(monkeypatch):
    """A word rewritten on the surface never reached the dialog."""
    before = words_the_dialog_paints(fresh_dialog())
    assert not set(before.values()) & set(SENTINEL_WORDS.values())
    for name, sentinel in SENTINEL_WORDS.items():
        monkeypatch.setattr(surface, name, sentinel)
    assert words_the_dialog_paints(fresh_dialog()) == SENTINEL_WORDS


def test_rewriting_a_surface_format_rewrites_what_the_dialog_paints(monkeypatch):
    """A headline or bot-line format rewritten on the surface never arrived."""
    dialog, _ = build_dialog(monkeypatch)
    dialog._handle_progress_main_thread(surface.DONE, 3, 3, "")
    assert dialog._headline.text() == "Done — 3 bot(s) processed."
    monkeypatch.setattr(surface, "HEADLINE_DONE", "sentinel done {total}")
    monkeypatch.setattr(surface, "ITEM_BOT_STARTED", "sentinel line {bot_id}")
    dialog._handle_progress_main_thread(surface.DONE, 3, 3, "")
    assert dialog._headline.text() == "sentinel done 3"
    dialog._handle_progress_main_thread(surface.BOT_STARTED, 3, 1, "bot-a")
    assert dialog._list.item(0).text() == "sentinel line bot-a"


def test_rewriting_a_surface_log_rewrites_what_the_dialog_logs(
    capture_log, monkeypatch
):
    """A log line rewritten on the surface never reached the dialog."""
    dialog, _ = build_dialog(monkeypatch)
    dialog._bot_manager = _RaisingManager()
    with capture_log(LOGGER_NAME) as before:
        dialog._on_cancel()
    assert [record.msg for record in before] == [surface.CANCEL_FAILED_LOG]
    monkeypatch.setattr(surface, "CANCEL_FAILED_LOG", "sentinel cancel log: %s")
    monkeypatch.setattr(surface, "UNSUBSCRIBE_FAILED_LOG", "sentinel unsub log: %s")
    with capture_log(LOGGER_NAME) as after:
        dialog._on_cancel()
    assert [record.msg for record in after] == ["sentinel cancel log: %s"]
    from PySide6.QtGui import QCloseEvent

    dialog._unsub = make_unsubscriber(UNSUB_RAISES)
    with capture_log(LOGGER_NAME) as closed:
        dialog.closeEvent(QCloseEvent())
    assert [record.msg for record in closed] == ["sentinel unsub log: %s"]


class _RefusingBus:
    """A bus whose subscribe refuses, so the dialog logs and carries on."""

    def subscribe(self, topic, handler):
        del topic, handler
        raise RuntimeError("bus refused the subscribe")


def test_a_refused_subscribe_is_logged_and_the_dialog_still_builds(
    capture_log, monkeypatch
):
    """A bus that refuses the subscribe left no trace, or lost the dialog."""
    from src.core import event_bus

    app()
    monkeypatch.setattr(event_bus, "get_event_bus", lambda: _RefusingBus())
    with capture_log(LOGGER_NAME) as records:
        dialog = qt_dialog.StartAllProgressDialog(object())
    assert [record.msg for record in records] == [surface.SUBSCRIBE_FAILED_LOG]
    assert dialog._bus is None
    assert dialog._unsub is None
    assert dialog._cancel_btn.text() == surface.CANCEL_TEXT
    monkeypatch.undo()
    with capture_log(LOGGER_NAME) as quiet:
        fresh_dialog()
    assert [record.msg for record in quiet] == []


COLOUR_TOKENS = (
    ("dialog_surface", surface.DIALOG_SURFACE, "#14141e"),
    ("text_color", surface.TEXT_COLOR, "#c0c0c0"),
    ("list_surface", surface.LIST_SURFACE, "#0a0a12"),
    ("list_border", surface.LIST_BORDER, "#2a2a3a"),
    ("button_surface", surface.BUTTON_SURFACE, "#1a1a26"),
    ("button_border", surface.BUTTON_BORDER, "#3a3a4a"),
    ("button_hover", surface.BUTTON_HOVER, "#22222e"),
    ("disabled_text", surface.DISABLED_TEXT, "#555555"),
    ("subline_color", surface.SUBLINE_COLOR, "#888"),
)


def test_rgb_matches_qcolor_on_every_token():
    """The Qt-free colour split disagrees with QColor on a token."""
    from PySide6.QtGui import QColor

    assert surface.rgb("#123456") == (18, 52, 86)
    assert surface.rgb("#abc") == (170, 187, 204)
    assert surface.rgb("#ff8000") == (255, 128, 0)
    assert surface.rgb("#ff8000") != surface.rgb("#0080ff")
    for _name, token, expected in COLOUR_TOKENS:
        assert token == expected, token
        painted = QColor(token)
        assert surface.rgb(token) == (
            painted.red(),
            painted.green(),
            painted.blue(),
        )


def test_the_style_sheet_is_the_dialogs_own(monkeypatch):
    """The surface ships a skin the dialog does not paint."""
    dialog, _ = build_dialog(monkeypatch)
    assert surface.STYLE_SHEET == dialog.styleSheet()
    for _name, token, _expected in COLOUR_TOKENS:
        if token == surface.SUBLINE_COLOR:
            assert token in surface.SUBLINE_STYLE
        else:
            assert token in surface.STYLE_SHEET, token
    assert surface.SUBLINE_STYLE == dialog._subline.styleSheet()
    assert "font-family: Consolas" in surface.STYLE_SHEET
    assert "padding: 6px 18px" in surface.STYLE_SHEET
    assert "font-size: 11px" in surface.STYLE_SHEET
    assert "font-size: 10px" in surface.STYLE_SHEET
    assert surface.STYLE_SHEET.count("font-size: 10px") == 2
    from qt_pixel import render_widget

    assert_pictures_match(
        old_side=render_widget(dialog, PIXEL_SIZE),
        new_side=render_widget(
            dialog_painted_by_the_model(model_payload(PIXEL_SCRIPTS["fresh"])),
            PIXEL_SIZE,
        ),
    )
    for token in PAINTED_TOKENS:
        assert token in surface.STYLE_SHEET + surface.SUBLINE_STYLE, token
    assert surface.BUTTON_HOVER in surface.STYLE_SHEET
    assert ":hover" in surface.STYLE_SHEET


def dialog_painted_by_the_dialog(script, monkeypatch):
    """The shipped dialog, driven through the script."""
    dialog, _ = build_dialog(monkeypatch)
    for step in script:
        run_step_old(dialog, step)
    return dialog


def model_payload(script):
    """The surface payload for the same script, stamped."""
    model = surface.StartAllProgressModel()
    for step in script:
        run_step_new(model, step)
    return sealed(surface.build_view_model(model))


def dialog_painted_by_the_model(payload):
    """A bare dialog filled only from the payload, never from the dialog.

    A payload the caller changed after it came off the surface is
    refused.
    """
    unaltered(payload)
    from PySide6 import QtWidgets

    properties = payload["widget"]
    dialog = QtWidgets.QDialog()
    dialog.setAccessibleName(properties["accessible_name"])
    dialog.setWindowTitle(properties["window_title"])
    dialog.setModal(properties["modal"])
    dialog.setMinimumWidth(properties["minimum_width_px"])
    dialog.resize(properties["size_px"][0], properties["size_px"][1])
    dialog.setStyleSheet(properties["style_sheet"])

    layout = QtWidgets.QVBoxLayout(dialog)
    layout.setContentsMargins(*payload["layout"]["margins_px"])
    layout.setSpacing(payload["layout"]["spacing_px"])

    headline = QtWidgets.QLabel(payload["headline_text"])
    font = headline.font()
    font.setPointSize(payload["headline"]["point_size"])
    font.setBold(payload["headline"]["bold"])
    headline.setFont(font)

    subline = QtWidgets.QLabel(payload["subline"]["text"])
    subline.setWordWrap(payload["subline"]["word_wrap"])
    subline.setStyleSheet(payload["subline"]["style_sheet"])

    listing = QtWidgets.QListWidget()
    for text in payload["items"]:
        listing.addItem(text)

    row = QtWidgets.QHBoxLayout()
    row.setContentsMargins(*payload["button_row"]["margins_px"])
    labelled = {"headline": headline, "subline": subline, "list": listing}
    for index, name in enumerate(payload["layout"]["order"]):
        if name == "button_row":
            layout.addLayout(row)
        else:
            layout.addWidget(labelled[name], payload["layout"]["child_stretch"][index])

    cancel = QtWidgets.QPushButton(payload["buttons"]["cancel"]["text"])
    cancel.setEnabled(payload["cancel_enabled"])
    close = QtWidgets.QPushButton(payload["buttons"]["close"]["text"])
    close.setEnabled(payload["close_enabled"])
    pressable = {"cancel": cancel, "close": close}
    for name in payload["button_row"]["order"]:
        if name == "stretch":
            row.addStretch(payload["button_row"]["leading_stretch"])
        else:
            row.addWidget(pressable[name])
    return dialog


PIXEL_SCRIPTS = {
    "fresh": [],
    "happy": HAPPY_SCRIPT[:-1],
    "finished": HAPPY_SCRIPT,
    "no_bots": NO_BOTS_SCRIPT[:1],
    "cancelled": CANCELLED_SCRIPT,
    "timeout": TIMEOUT_SCRIPT,
}


@pytest.mark.parametrize("name", sorted(PIXEL_SCRIPTS))
def test_the_two_sides_render_the_same_pixels(name, monkeypatch):
    """The page paints a value, a colour or a position the dialog does not."""
    app()
    script = PIXEL_SCRIPTS[name]
    assert_pictures_match(
        old_side=render_offscreen(
            dialog_painted_by_the_dialog(script, monkeypatch), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            dialog_painted_by_the_model(model_payload(script)), PIXEL_SIZE
        ),
        note=name,
    )


def test_the_pixel_check_reports_a_different_script(monkeypatch):
    """The image comparison passes whatever the second side paints.

    Two real scripts, one driven into each side. One ends with every bot
    started and the Close button live; the other has started nothing, so
    a pass proves the comparison reports a dialog painted differently.
    """
    app()
    assert PIXEL_SCRIPTS["finished"] != PIXEL_SCRIPTS["fresh"]
    assert_pictures_differ(
        old_side=render_offscreen(
            dialog_painted_by_the_dialog(PIXEL_SCRIPTS["finished"], monkeypatch),
            PIXEL_SIZE,
        ),
        new_side=render_offscreen(
            dialog_painted_by_the_model(model_payload(PIXEL_SCRIPTS["fresh"])),
            PIXEL_SIZE,
        ),
        note="finished from the dialog against fresh from the surface",
    )


def test_the_swapped_lines_the_pixel_check_cannot_see_are_compared_as_text():
    """Two lines of one length swap places and the render may not tell.

    Whether a swap of equal length moves a pixel depends on the fonts
    the host installs, so the line text is compared as exact strings in
    the trace above, which reports that swap on every machine.
    """
    finished = model_payload(PIXEL_SCRIPTS["finished"])["items"]
    assert len(set(len(text) for text in finished)) == 1
    swapped = list(reversed(finished))
    assert swapped != finished
    timed_out = model_payload(PIXEL_SCRIPTS["timeout"])["items"]
    assert len(set(len(text) for text in timed_out)) == len(timed_out)


SILENT_IN_THE_RENDER = {
    "headline_point_size": "point_size",
    "headline_bold": "bold",
}


def test_the_font_the_pixel_check_cannot_see_is_compared_as_a_number(monkeypatch):
    """The headline's size and weight were left to the render to report.

    Whether a point size or a weight moves a pixel depends on the faces
    the host installs, so no render carries this proof on every machine.
    Both values are read off the dialog's own font and off the surface
    as numbers, here and in
    ``test_the_headline_and_subline_match_the_dialog``.
    """
    for token in SILENT_IN_THE_RENDER.values():
        assert token in surface.HEADLINE
    dialog, _ = build_dialog(monkeypatch)
    font = dialog._headline.font()
    assert surface.HEADLINE["point_size"] == font.pointSize() == 12
    assert surface.HEADLINE["bold"] == font.bold() is True
    for size in (8, 20):
        assert surface.HEADLINE["point_size"] != size


def test_the_stretch_the_pixel_check_cannot_see_is_compared_as_a_number(monkeypatch):
    """A stretch of 0 on the list paints the same as the shipped 1.

    The list already expands on its own size policy, and the spacer in
    the button row already absorbs the leftover width, so dropping
    either stretch factor to 0 changes no pixel. Both factors are
    compared against the dialog's own layout in
    ``test_layout_matches_the_dialog``.
    """
    dialog, _ = build_dialog(monkeypatch)
    layout = dialog.layout()
    assert surface.LAYOUT["child_stretch"] == [
        layout.stretch(index) for index in range(layout.count())
    ]
    assert surface.LAYOUT["child_stretch"][2] == 1
    assert surface.BUTTON_ROW["leading_stretch"] == layout.itemAt(3).layout().stretch(0)
    assert surface.BUTTON_ROW["leading_stretch"] == 1


def test_a_same_length_line_is_compared_as_an_exact_string(monkeypatch):
    """A same-length line swap was left to the render to report.

    Whether a swap of equal length moves a pixel depends on the fonts
    the host installs, so no render carries this proof on every machine.
    Every line is read off the dialog's own list and off the surface and
    compared character for character.
    """
    app()
    script = PIXEL_SCRIPTS["finished"]
    painted = run_old(script, monkeypatch)[-1]
    declared = model_payload(script)
    assert declared["items"] == painted["items"]
    assert declared["headline_text"] == painted["headline"]
    assert declared["item_count"] == painted["item_count"]
    first = declared["items"][0]
    same_length = "X " + "y" * (len(first) - 2)
    assert same_length != first
    assert len(same_length) == len(first)
    assert same_length not in painted["items"]


PAINTED_TOKENS = (
    surface.DIALOG_SURFACE,
    surface.TEXT_COLOR,
    surface.LIST_SURFACE,
    surface.LIST_BORDER,
    surface.BUTTON_SURFACE,
    surface.BUTTON_BORDER,
    surface.DISABLED_TEXT,
    surface.SUBLINE_COLOR,
)


def test_the_declared_colours_are_the_dialogs_own(monkeypatch):
    """A declared colour is carried by neither side, or by only one."""
    from qt_pixel import render_widget

    app()
    script = PIXEL_SCRIPTS["finished"]
    dialog = dialog_painted_by_the_dialog(script, monkeypatch)
    declared = dialog.styleSheet() + dialog._subline.styleSheet()
    payload = model_payload(script)
    for token in PAINTED_TOKENS:
        assert token in declared, token
        assert token in surface.STYLE_SHEET + surface.SUBLINE_STYLE, token
    assert_pictures_match(
        old_side=render_widget(dialog, PIXEL_SIZE),
        new_side=render_widget(dialog_painted_by_the_model(payload), PIXEL_SIZE),
    )
    assert len(set(PAINTED_TOKENS)) == len(PAINTED_TOKENS)


GREY_TOKENS = (surface.TEXT_COLOR, surface.DISABLED_TEXT, surface.SUBLINE_COLOR)


def test_a_channel_swap_is_reported_on_every_colour_that_can_show_one():
    """A colour check a swapped red and blue would pass proves nothing.

    Three of the nine tokens are greys, so their channels are equal and
    no swap can change them. They are named here rather than left to
    look like coverage; the six that carry a hue are checked.
    """
    swappable = 0
    for _name, token, _expected in COLOUR_TOKENS:
        red, green, blue = surface.rgb(token)
        if token in GREY_TOKENS:
            assert red == green == blue, token
            continue
        assert (red, green, blue) != (blue, green, red), token
        swappable += 1
    assert swappable == 6
    assert len(GREY_TOKENS) == 3
    assert surface.rgb("#888") == surface.rgb("#888888")


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = model_payload(HAPPY_SCRIPT)
    encoded = json.loads(json.dumps(payload))
    assert encoded["headline_text"] == "Done — 3 bot(s) processed."
    assert encoded["items"] == ["✓ bot-a", "✓ bot-b", "✓ bot-c"]
    assert encoded["item_count"] == 3
    assert encoded["cancel_enabled"] is False
    assert encoded["close_enabled"] is True
    assert encoded["calls"][-1] == ["closeAfter", 2000]
    assert encoded["topic"] == "bot_manager.start_all_progress"
    assert encoded["phases"] == [
        "begin",
        "bot_starting",
        "bot_started",
        "bot_timeout",
        "done",
        "cancelled",
    ]
    assert encoded["event_fields"] == ["phase", "total", "started", "bot_id"]
    assert encoded["dialog_surface"] == [20, 20, 30]
    assert encoded["text_color"] == [192, 192, 192]
    assert encoded["list_surface"] == [10, 10, 18]
    assert encoded["subline_color"] == [136, 136, 136]
    assert encoded["widget"]["accessible_name"] == "Start All Progress Dialog"


def test_view_model_matches_the_dialog_on_the_same_events(monkeypatch):
    """The bridge payload disagrees with the dialog on the same run."""
    from PySide6 import QtWidgets

    dialog = dialog_painted_by_the_dialog(HAPPY_SCRIPT, monkeypatch)
    payload = model_payload(HAPPY_SCRIPT)
    rows = QtWidgets.QListWidget.count(dialog._list)
    assert payload["headline_text"] == dialog._headline.text()
    assert payload["items"] == [
        QtWidgets.QListWidget.item(dialog._list, row).text() for row in range(rows)
    ]
    assert payload["item_count"] == rows
    assert payload["cancel_enabled"] == dialog._cancel_btn.isEnabled()
    assert payload["close_enabled"] == dialog._close_btn.isEnabled()


def test_bridge_registers_the_start_all_method():
    """The renderer cannot reach the Start All dialog through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 31,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "events": [
                        {"phase": "begin", "total": 2, "started": 0, "bot_id": ""},
                        {
                            "phase": "bot_starting",
                            "total": 2,
                            "started": 0,
                            "bot_id": "bridge-bot",
                        },
                        {
                            "phase": "bot_started",
                            "total": 2,
                            "started": 1,
                            "bot_id": "bridge-bot",
                        },
                    ],
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["items"] == ["✓ bridge-bot"]
    assert answer["result"]["headline_text"] == "Auto-starting 2 bots (1/2 verified)"


def test_the_bridge_carries_the_cancel_and_the_close():
    """A Cancel press or a close over the bridge changed nothing."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 32, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    started = call({"reset": True, "events": [{"phase": "begin", "total": 2}]})
    assert started["cancel_enabled"] is True
    cancelled = call({"cancel": True})
    assert cancelled["headline_text"] == surface.HEADLINE_CANCELLING
    assert cancelled["cancel_enabled"] is False
    refused = call({"reset": True, "cancel": True, "cancel_refused": True})
    assert refused["headline_text"] == surface.HEADLINE_CANCEL_FAILED
    assert call({"close": True})["headline_text"] == surface.HEADLINE_CANCEL_FAILED
    assert call({"close": True, "unsubscribe_refused": True})["close_enabled"] is False
    call({"reset": True})


def test_the_bridge_keeps_the_state_until_a_reset():
    """The dialog forgot its lines between two bridge calls."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 33, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    call({"reset": True, "events": [{"phase": "begin", "total": 2}]})
    call({"events": [{"phase": "bot_starting", "total": 2, "bot_id": "kept"}]})
    assert call({})["items"] == ["⏳ kept (starting...)"]
    assert call({"reset": True})["items"] == []
    assert call({})["headline_text"] == surface.HEADLINE_INITIAL_TEXT


def test_a_bad_event_over_the_bridge_loses_only_itself(capture_log):
    """One unreadable event took the whole batch down."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    with capture_log(LOGGER_NAME) as records:
        answer = desktop_bridge.handle_line(
            json.dumps(
                {
                    "id": 34,
                    "method": surface.METHOD,
                    "params": {
                        "reset": True,
                        "events": [
                            {"phase": "begin", "total": 2},
                            {"phase": "begin", "total": "not-a-number"},
                            {
                                "phase": "bot_starting",
                                "total": 2,
                                "bot_id": "survivor",
                            },
                        ],
                    },
                }
            ),
            registry,
        )
    assert answer["ok"] is True
    assert answer["result"]["items"] == ["⏳ survivor (starting...)"]
    assert len(records) == 1
    desktop_bridge.handle_line(
        json.dumps({"id": 35, "method": surface.METHOD, "params": {"reset": True}}),
        registry,
    )


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'start_all_progress.state', 'params':"
    " {'reset': True, 'events': [{'phase': 'begin', 'total': 2},"
    " {'phase': 'bot_starting', 'total': 2, 'bot_id': 'probe-bot'}]}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def run_probe(prelude):
    done = subprocess.run(
        [sys.executable, "-"],
        input=(prelude + QT_PROBE).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the Start All dialog pulled Qt into the backend process."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["items"] == ["⏳ probe-bot (starting...)"]
    assert result["headline_text"] == (
        "Auto-starting 2 bots (0/2 verified, starting probe-bot...)"
    )
    assert result["widget"]["style_sheet"].startswith("QDialog { background: #14141e;")


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
