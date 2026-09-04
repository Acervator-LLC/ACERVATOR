"""The shipped reentrancy guard and the Qt-free surface, side by side.

A failure means the surface answers a different value, writes a different
record, dispatches different work, consults the application object a
different number of times, leaves the guard in a different state or
refuses differently than ``safe_process_events`` does on the same steps.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import inspect
import json
import logging
import math
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import qt_safe_events_surface as surface

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SOURCE = REPO_ROOT / "src" / "gui" / "qt_safe_events.py"
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
TIMER_NAMESAKE = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
WIDGET_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"

CONNECT_TOTAL = 0
SHIPPED_CLASS_TOTAL = 0
SHIPPED_FUNCTION_TOTAL = 3
SHIPPED_SIGNAL_TOTAL = 0
WIDGET_TOTAL = 0
PAYLOAD_KEY_TOTAL = 21
CONSTANT_TOTAL = 33
TRACE_KEY_TOTAL = 7
CALL_NAME_TOTAL = 12
ENDING_TOTAL = 4

LOGGER_NAME = "src.gui.qt_safe_events"

LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "Ekthelius' venues"
WRONG_CAPITALS_TEXT = "pAINT connection STATUS"
PLAIN_REASON = "paint connection status"


class NoText:
    """A value that refuses to become text, the way a broken object does."""

    def __str__(self) -> str:
        raise ValueError("this value has no text")


class NoTruth:
    """A value that refuses to be read as true or false."""

    def __bool__(self) -> bool:
        raise ValueError("this value has no truth")


def canonical(value):
    """`value` as nested text, so a whole number and a decimal differ.

    ``12`` and ``12.0`` compare equal as numbers and must not, and two
    not-a-numbers never compare equal and must. Reading every leaf as its
    own text settles both.
    """
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: repr(item[0]))
        return [[repr(key), canonical(inner)] for key, inner in pairs]
    if isinstance(value, (list, tuple)):
        return [canonical(inner) for inner in value]
    return repr(value)


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth, as text."""
    return hashlib.sha256(repr(canonical(value)).encode("utf-8")).hexdigest()


def app():
    """The one application object every Qt-side drive runs against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


# The world the shipped rule runs in


class ApplicationCounter:
    """A stand-in for the application class that counts every look-up.

    ``instance`` is the only member the rule reaches for. It counts the
    look-up and hands back the real application object, or nothing when
    this drive says no application exists. Any other member is an
    AttributeError, so a misuse reports rather than passing.
    """

    def __init__(self, real, present: bool) -> None:
        self.real = real
        self.present = present
        self.consulted = 0

    def instance(self):
        self.consulted += 1
        return self.real.instance() if self.present else None


@contextlib.contextmanager
def toolkit_absent():
    """Make the shipped module's own import of the library fail.

    ``None`` in the module table is what the import machinery reads as a
    halted import, so the shipped ``except ImportError`` branch runs on
    its own code rather than on a rewritten function.
    """
    name = "PySide6.QtWidgets"
    held = sys.modules.get(name, KeyError)
    sys.modules[name] = None
    try:
        yield
    finally:
        if held is KeyError:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = held


@contextlib.contextmanager
def counted_application(counter_box, present: bool):
    """Put the counting stand-in where the shipped rule looks it up."""
    import PySide6.QtWidgets as widgets

    real = widgets.QApplication
    counter = ApplicationCounter(real, present)
    counter_box.append(counter)
    widgets.QApplication = counter
    try:
        yield counter
    finally:
        widgets.QApplication = real


class RecordSink(logging.Handler):
    """Every record the shipped logger writes, kept unformatted.

    Attached to the logger object itself rather than through the root,
    so a module that turns propagation off cannot blind it.
    """

    def __init__(self) -> None:
        logging.Handler.__init__(self, level=logging.DEBUG)
        self.records: list = []

    def emit(self, record) -> None:
        self.records.append(record)


@contextlib.contextmanager
def captured_records():
    """Read every record the shipped logger writes during this block."""
    logger = logging.getLogger(LOGGER_NAME)
    sink = RecordSink()
    held_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(sink)
    try:
        yield sink
    finally:
        logger.removeHandler(sink)
        logger.setLevel(held_level)


# The queue both sides drain


def work_event_type():
    """One event type this file owns, registered once per process."""
    from PySide6.QtCore import QEvent

    global _WORK_TYPE
    if _WORK_TYPE is None:
        _WORK_TYPE = QEvent.Type(QEvent.registerEventType())
    return _WORK_TYPE


_WORK_TYPE = None


def work_event(name, work):
    """One posted event carrying a name and the work it stands for."""
    from PySide6.QtCore import QEvent

    class WorkEvent(QEvent):
        def __init__(self) -> None:
            QEvent.__init__(self, work_event_type())
            self.name = name
            self.work = work

    return WorkEvent()


def work_receiver(sink):
    """One live object that records every piece of work handed to it."""
    from PySide6.QtCore import QObject

    class WorkReceiver(QObject):
        def event(self, incoming):
            if incoming.type() == work_event_type():
                sink["dispatched"].append(incoming.name)
                if incoming.work is not None:
                    incoming.work()
                return True
            return QObject.event(self, incoming)

    return WorkReceiver()


# The inputs. One scenario drives both sides.


def scenario(name, steps):
    return {"name": name, "steps": tuple(steps)}


def call(
    reason=surface.DEFAULT_REASON,
    force=surface.DEFAULT_FORCE,
    toolkit=True,
    has_app=True,
):
    return ("call", reason, force, toolkit, has_app)


def post(name):
    return ("post", name, None, None)


def nest(name, reason=surface.DEFAULT_REASON, force=surface.DEFAULT_FORCE):
    return ("post", name, reason, force)


RESET = ("reset",)

SCENARIOS = [
    scenario("nothing_queued", [call()]),
    scenario("one_piece_of_work", [post("paint"), call(PLAIN_REASON)]),
    scenario(
        "three_pieces_of_work",
        [post("paint"), post("layout"), post("timer"), call(PLAIN_REASON)],
    ),
    scenario("two_calls_in_a_row", [post("a"), call(), post("b"), call()]),
    scenario("the_queue_is_left_empty", [post("a"), call(), call()]),
    scenario("no_reason_given", [call("")]),
    scenario("the_library_is_absent", [post("a"), call(PLAIN_REASON, toolkit=False)]),
    scenario(
        "the_library_is_absent_then_present",
        [post("a"), call(PLAIN_REASON, toolkit=False), call(PLAIN_REASON)],
    ),
    scenario("no_application_object", [post("a"), call(PLAIN_REASON, has_app=False)]),
    scenario(
        "no_application_object_then_one",
        [post("a"), call(PLAIN_REASON, has_app=False), call(PLAIN_REASON)],
    ),
    scenario("a_nested_call_with_a_reason", [nest("inner", PLAIN_REASON), call()]),
    scenario("a_nested_call_with_no_reason", [nest("inner", ""), call()]),
    scenario(
        "a_nested_call_that_forces_past_the_guard",
        [nest("inner", PLAIN_REASON, True), call()],
    ),
    scenario(
        "a_forced_nested_call_then_an_unforced_one",
        [nest("first", PLAIN_REASON, True), nest("second", PLAIN_REASON), call()],
    ),
    scenario(
        "two_nested_calls_are_both_blocked",
        [nest("first", "one"), nest("second", "two"), call()],
    ),
    scenario("a_reset_before_a_call", [RESET, post("a"), call()]),
    scenario("a_reset_after_a_call", [post("a"), call(), RESET]),
    scenario("zero", [nest("inner", 0), call()]),
    scenario("negative", [nest("inner", -500.25), call()]),
    scenario("a_thousand_million", [nest("inner", 1_000_000_000), call()]),
    scenario("one_billionth", [nest("inner", 1e-9), call()]),
    scenario("infinity", [nest("inner", math.inf), call()]),
    scenario("minus_infinity", [nest("inner", -math.inf), call()]),
    scenario("not_a_number", [nest("inner", math.nan), call()]),
    scenario(
        "a_whole_number_and_the_same_decimal",
        [nest("first", 12), nest("second", 12.0), call()],
    ),
    scenario("unicode", [nest("inner", UNICODE_TEXT), call()]),
    scenario("two_hundred_characters", [nest("inner", LONG_TEXT), call()]),
    scenario("markup", [nest("inner", MARKUP_TEXT), call()]),
    scenario("an_apostrophe", [nest("inner", APOSTROPHE_TEXT), call()]),
    scenario("wrong_capitals", [nest("inner", WRONG_CAPITALS_TEXT), call()]),
    scenario("a_newline_in_the_reason", [nest("inner", NEWLINE_TEXT), call()]),
    scenario("a_number_where_text_belongs", [nest("inner", 42), call()]),
    scenario("nothing_where_text_belongs", [nest("inner", None), call()]),
    scenario("a_flag_where_text_belongs", [nest("inner", True), call()]),
    scenario("text_where_a_flag_belongs", [nest("inner", PLAIN_REASON, "no"), call()]),
    scenario("a_number_where_a_flag_belongs", [nest("inner", PLAIN_REASON, 0), call()]),
    scenario("the_reason_refuses_to_become_text", [nest("inner", NoText()), call()]),
    scenario("an_unguarded_reason_that_refuses_text", [call(NoText())]),
    scenario(
        "the_flag_refuses_to_be_read", [nest("inner", PLAIN_REASON, NoTruth()), call()]
    ),
    scenario(
        "an_unguarded_flag_that_refuses_to_be_read", [call(PLAIN_REASON, NoTruth())]
    ),
    scenario(
        "the_whole_rule",
        [
            post("paint"),
            nest("blocked", PLAIN_REASON),
            nest("forced", "recursive redraw", True),
            post("layout"),
            call(PLAIN_REASON),
            call(PLAIN_REASON, toolkit=False),
            call(PLAIN_REASON, has_app=False),
            RESET,
            post("late"),
            call(),
        ],
    ),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}

# Refusals both sides raise from the same Python operation, so both word
# them with one string.
SHARED_WORDING = (
    "the_reason_refuses_to_become_text",
    "the_flag_refuses_to_be_read",
)

REFUSING_SCENARIOS = SHARED_WORDING


# Driving the two sides


def capture(sink, work):
    """Run `work`, keeping its answer or the refusal it raised.

    A nested call runs inside the library's own dispatch on the shipped
    side. A refusal let out of there would leave the dispatcher, not the
    rule, deciding what happens, so both sides keep it here and the
    reader raises it again.
    """
    try:
        sink["returned"].append(work())
    except Exception as exc:
        sink["raised"].append(exc)


def drive_old(spec) -> dict:
    """The shipped guard, driven by one scenario."""
    from PySide6.QtCore import QCoreApplication

    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    sink: dict = {"returned": [], "dispatched": [], "raised": []}
    counters: list = []
    receiver = work_receiver(sink)
    posted = 0
    try:
        with captured_records() as records:
            for step in spec["steps"]:
                if step[0] == "reset":
                    shipped.reset_for_test()
                    continue
                if step[0] == "post":
                    _, name, reason, force = step
                    inner = None
                    if reason is not None or force is not None:
                        inner = _nested_old(sink, shipped, reason, force)
                    QCoreApplication.postEvent(receiver, work_event(name, inner))
                    posted += 1
                    continue
                _, reason, force, toolkit, has_app = step
                with contextlib.ExitStack() as world:
                    if not toolkit:
                        world.enter_context(toolkit_absent())
                    else:
                        world.enter_context(counted_application(counters, has_app))
                    capture(sink, lambda: shipped.safe_process_events(reason, force))
            return {
                "returned": list(sink["returned"]),
                "records": [record_from_logging(r) for r in records.records],
                "dispatched": list(sink["dispatched"]),
                "app_consulted": sum(c.consulted for c in counters),
                "guard": {"in_call": shipped._is_in_call()},
                "pending": posted - len(sink["dispatched"]),
                "defaults": shipped_defaults(),
                "raised": list(sink["raised"]),
            }
    finally:
        receiver.deleteLater()
        shipped.reset_for_test()


def _nested_old(sink, shipped, reason, force):
    """The work a queued event runs: one more call into the shipped rule."""

    def run() -> None:
        capture(sink, lambda: shipped.safe_process_events(reason, force))

    return run


def drive_new(spec):
    """The Qt-free model, driven by the same scenario."""
    model = surface.SafeEventsModel()
    sink = {"returned": model.returned, "raised": []}
    for step in spec["steps"]:
        if step[0] == "reset":
            model.reset_for_test()
            continue
        if step[0] == "post":
            _, name, reason, force = step
            inner = None
            if reason is not None or force is not None:
                inner = _nested_new(sink, model, reason, force)
            model.post(name, inner)
            continue
        _, reason, force, toolkit, has_app = step
        try:
            model.process_events(reason, force, toolkit, has_app)
        except Exception as exc:
            sink["raised"].append(exc)
    return model, sink["raised"]


def _nested_new(sink, model, reason, force):
    """The work a queued piece runs: one more call into the model."""

    def run() -> None:
        try:
            model.process_events(reason, force)
        except Exception as exc:
            sink["raised"].append(exc)

    return run


def shipped_defaults() -> dict:
    """The reason and the flag the shipped rule uses when given neither."""
    from src.gui.qt_safe_events import safe_process_events

    given = inspect.signature(safe_process_events).parameters
    return {"reason": given["reason"].default, "force": given["force"].default}


def record_from_logging(record) -> dict:
    """One written record, kept as its parts rather than as one line."""
    return {
        "level": record.levelname,
        "template": record.msg,
        "args": list(record.args or ()),
    }


# Reading the two sides


def read_records(records) -> list:
    """Every record with its one line read out, which a bad reason refuses."""
    return [dict(record, text=surface.record_text(record)) for record in records]


def old_trace(spec) -> dict:
    driven = drive_old(spec)
    if driven["raised"]:
        raise driven["raised"][0]
    return {
        "returned": driven["returned"],
        "records": read_records(driven["records"]),
        "dispatched": driven["dispatched"],
        "app_consulted": driven["app_consulted"],
        "guard": driven["guard"],
        "pending": driven["pending"],
        "defaults": driven["defaults"],
    }


def new_trace(spec) -> dict:
    model, raised = drive_new(spec)
    if raised:
        raise raised[0]
    payload = surface.build_view_model(model)
    return {
        "returned": payload["returned"],
        "records": read_records(payload["records"]),
        "dispatched": payload["dispatched"],
        "app_consulted": payload["app_consulted"],
        "guard": {"in_call": payload["guard"]["in_call"]},
        "pending": payload["pending"],
        "defaults": payload["defaults"],
    }


def outcome(work) -> dict:
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": str(exc),
        }


def old_outcome(spec) -> dict:
    return outcome(lambda: old_trace(spec))


def new_outcome(spec) -> dict:
    return outcome(lambda: new_trace(spec))


def refusal_headline(message) -> str:
    """The first line of a refusal, which is the one that names the cause."""
    return message.splitlines()[0].strip()


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_apply_the_same_rule(name):
    """An answer, a written record, a dispatch or the guard state differs."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        assert name in SHARED_WORDING, name
        assert refusal_headline(new["message"]) == refusal_headline(old["message"])
        return
    assert canonical(new["value"]) == canonical(old["value"]), name
    assert digest(new["value"]) == digest(old["value"]), name


def test_both_answers_and_refusals_are_in_the_measured_set():
    """Every input was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for spec in SCENARIOS:
        old = old_outcome(spec)
        (answered if old["outcome"] == "answered" else refused).append(spec["name"])
    assert answered, "no input was answered"
    assert refused, "no input was refused"
    assert set(refused) == set(REFUSING_SCENARIOS), sorted(refused)
    assert len(answered) + len(refused) == len(SCENARIOS)


@pytest.mark.parametrize("name", SHARED_WORDING)
def test_a_refusal_from_the_same_operation_is_worded_the_same(name):
    """One side worded a refusal both sides raise from the same operation."""
    old = old_outcome(BY_NAME[name])
    new = new_outcome(BY_NAME[name])
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["message"]) == (old["error"], old["message"])
    assert old["error"] == "ValueError"


def test_a_reason_that_refuses_text_still_answers_when_the_guard_is_down():
    """A bad reason refuses on a call that never writes a record.

    The rule reads the reason only after the guard fires, so a value that
    cannot become text passes straight through an ordinary call. Both
    sides answer, and the same value refuses when the guard does fire.
    """
    quiet = BY_NAME["an_unguarded_reason_that_refuses_text"]
    assert old_outcome(quiet)["outcome"] == "answered"
    assert new_outcome(quiet)["outcome"] == "answered"
    loud = BY_NAME["the_reason_refuses_to_become_text"]
    assert old_outcome(loud)["outcome"] == "refused"
    assert new_outcome(loud)["outcome"] == "refused"


def test_a_flag_that_refuses_to_be_read_is_never_read_with_the_guard_down():
    """The flag is read on a call the guard never stops.

    The rule reads the flag only after finding the guard already up, so a
    value that cannot be read as true or false passes an ordinary call.
    """
    quiet = BY_NAME["an_unguarded_flag_that_refuses_to_be_read"]
    assert old_outcome(quiet)["outcome"] == "answered"
    assert new_outcome(quiet)["outcome"] == "answered"
    loud = BY_NAME["the_flag_refuses_to_be_read"]
    assert old_outcome(loud)["outcome"] == "refused"
    assert new_outcome(loud)["outcome"] == "refused"


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    quiet = old_outcome(BY_NAME["nothing_queued"])["value"]
    busy = old_outcome(BY_NAME["three_pieces_of_work"])["value"]
    assert canonical(quiet) != canonical(busy)
    assert digest(quiet) != digest(busy)
    assert digest(quiet) == digest(old_outcome(BY_NAME["nothing_queued"])["value"])
    assert len(digest(quiet)) == 64


def test_the_two_control_inputs_really_end_in_different_states():
    """The difference control pair settles alike, so it can never report."""
    quiet = old_outcome(BY_NAME["nothing_queued"])["value"]
    busy = old_outcome(BY_NAME["three_pieces_of_work"])["value"]
    assert quiet["dispatched"] == []
    assert busy["dispatched"] == ["paint", "layout", "timer"]
    assert quiet["dispatched"] != busy["dispatched"]


def test_the_hash_reads_a_whole_number_and_a_not_a_number_as_text():
    """A whole number and a decimal hash the same, or two blanks differ."""
    assert 12 == 12.0
    assert digest({"n": 12}) != digest({"n": 12.0})
    assert math.nan != math.nan
    assert digest({"n": math.nan}) == digest({"n": math.nan})
    assert canonical({"n": math.nan}) == canonical({"n": math.nan})


def test_a_whole_number_reason_and_the_same_decimal_are_told_apart():
    """Two records one number apart read as one, so a change would hide."""
    old = old_outcome(BY_NAME["a_whole_number_and_the_same_decimal"])["value"]
    written = [record["args"][0] for record in old["records"]]
    assert written == [12, 12.0]
    assert digest(written[0]) != digest(written[1])
    assert new_outcome(BY_NAME["a_whole_number_and_the_same_decimal"])["value"] == old


@pytest.mark.parametrize(
    "name",
    [
        "nothing_queued",
        "the_whole_rule",
        "a_nested_call_with_a_reason",
        "wrong_capitals",
    ],
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == TRACE_KEY_TOTAL, sorted(value)
    assert value["returned"], name
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


# The four endings, each told apart from the others


def test_the_four_endings_are_told_apart_on_both_sides():
    """Two endings read alike, so the comparison cannot separate them."""
    seen = {}
    for name, spec in (
        ("processed", BY_NAME["one_piece_of_work"]),
        ("no_toolkit", BY_NAME["the_library_is_absent"]),
        ("reentrant", BY_NAME["a_nested_call_with_a_reason"]),
        ("no_app", BY_NAME["no_application_object"]),
    ):
        seen[name] = old_outcome(spec)["value"]
    assert seen["processed"]["returned"] == [True]
    assert seen["no_toolkit"]["returned"] == [False]
    assert seen["reentrant"]["returned"] == [False, True]
    assert seen["no_app"]["returned"] == [False]
    assert seen["no_toolkit"]["app_consulted"] == 0
    assert seen["no_app"]["app_consulted"] == 1
    assert seen["no_toolkit"]["dispatched"] == []
    assert seen["no_app"]["dispatched"] == []
    assert len({digest(value) for value in seen.values()}) == ENDING_TOTAL
    model_endings = {
        name: drive_new(spec)[0].outcomes
        for name, spec in (
            ("processed", BY_NAME["one_piece_of_work"]),
            ("no_toolkit", BY_NAME["the_library_is_absent"]),
            ("reentrant", BY_NAME["a_nested_call_with_a_reason"]),
            ("no_app", BY_NAME["no_application_object"]),
        )
    }
    assert model_endings["processed"] == [surface.PROCESSED]
    assert model_endings["no_toolkit"] == [surface.NO_TOOLKIT]
    assert model_endings["reentrant"] == [surface.REENTRANT, surface.PROCESSED]
    assert model_endings["no_app"] == [surface.NO_APP]


def test_a_forced_call_drains_the_queue_the_call_around_it_was_draining():
    """A forced call takes no waiting work, so the guard never nests.

    A forced call runs the library's own dispatch a second time, and that
    dispatch takes what is still waiting. The waiting piece then calls in
    with the guard up and is blocked, so its answer arrives before the
    forced call's own. Both sides do this.
    """
    spec = BY_NAME["a_forced_nested_call_then_an_unforced_one"]
    old = old_outcome(spec)["value"]
    assert old["returned"] == [False, True, True]
    assert old["dispatched"] == ["first", "second"]
    assert old["app_consulted"] == 2
    blocked = old_outcome(BY_NAME["two_nested_calls_are_both_blocked"])["value"]
    assert blocked["returned"] == [False, False, True]
    assert blocked["app_consulted"] == 1
    assert new_outcome(spec)["value"] == old
    assert new_outcome(BY_NAME["two_nested_calls_are_both_blocked"])["value"] == blocked


def test_the_counting_stand_in_changes_nothing_the_rule_does():
    """The look-up counter answers a different application object.

    Every drive above reaches the application object through a counter,
    so the same steps are run once without it and the two answers are
    compared. A counter that changed the answer would make every count
    above a reading of the counter rather than of the rule.
    """
    from PySide6.QtCore import QCoreApplication

    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    sink: dict = {"dispatched": []}
    receiver = work_receiver(sink)
    QCoreApplication.postEvent(receiver, work_event("paint", None))
    assert shipped.safe_process_events(PLAIN_REASON) is True
    assert sink["dispatched"] == ["paint"]
    counted = old_outcome(BY_NAME["one_piece_of_work"])["value"]
    assert counted["returned"] == [True]
    assert counted["dispatched"] == ["paint"]
    assert counted["app_consulted"] == 1
    receiver.deleteLater()


def test_the_guard_writes_a_record_only_when_it_is_given_a_reason():
    """The guard writes when told nothing, or stays quiet when told why."""
    told = old_outcome(BY_NAME["a_nested_call_with_a_reason"])["value"]
    silent = old_outcome(BY_NAME["a_nested_call_with_no_reason"])["value"]
    assert len(told["records"]) == 1
    assert told["records"][0]["level"] == surface.SKIP_LOG_LEVEL
    assert told["records"][0]["text"].endswith(PLAIN_REASON)
    assert silent["records"] == []
    assert new_outcome(BY_NAME["a_nested_call_with_a_reason"])["value"] == told
    assert new_outcome(BY_NAME["a_nested_call_with_no_reason"])["value"] == silent


def test_the_record_sink_reports_a_record_and_stays_quiet_without_one():
    """The sink sees nothing whatever the rule writes."""
    from src.gui import qt_safe_events as shipped

    with captured_records() as sink:
        logging.getLogger(LOGGER_NAME).debug("a plain line")
        assert len(sink.records) == 1
        assert sink.records[0].getMessage() == "a plain line"
    with captured_records() as quiet:
        app()
        shipped.reset_for_test()
        assert shipped.safe_process_events(PLAIN_REASON) is True
        assert quiet.records == []


def test_the_shipped_logger_carries_the_name_and_level_the_surface_names():
    """The surface names a logger or a level the shipped rule never uses."""
    logger = logging.getLogger(LOGGER_NAME)
    assert logger.name == surface.LOGGER_NAME
    written = old_outcome(BY_NAME["a_nested_call_with_a_reason"])["value"]["records"]
    assert written[0]["level"] == surface.SKIP_LOG_LEVEL
    assert written[0]["template"] == surface.SKIP_LOG_TEMPLATE
    assert surface.SKIP_LOG_LEVEL == logging.getLevelName(logging.DEBUG)


# Real events, and things that are not events


def test_the_rule_dispatches_a_real_posted_event():
    """The call answered true without the library dispatching anything."""
    from PySide6.QtCore import QCoreApplication

    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    sink = {"dispatched": []}
    receiver = work_receiver(sink)
    QCoreApplication.postEvent(receiver, work_event("posted", None))
    assert sink["dispatched"] == []
    assert shipped.safe_process_events("a real posted event") is True
    assert sink["dispatched"] == ["posted"]
    receiver.deleteLater()


def test_the_rule_dispatches_a_real_timer_event():
    """A timer event waits past the call, so the rule delivered nothing."""
    from PySide6.QtCore import QObject, QTimer

    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    fired = []
    holder = QObject()
    timer = QTimer(holder)
    timer.setSingleShot(True)
    timer.setInterval(0)
    timer.timeout.connect(lambda: fired.append("timer"))
    timer.start()
    assert fired == []
    assert shipped.safe_process_events("a real timer event") is True
    assert fired == ["timer"]
    holder.deleteLater()


def test_the_rule_does_not_collect_an_object_marked_for_deferred_delete():
    """An object marked for deletion was collected, or never marked at all.

    A deferred delete is one of the events the library keeps back for its
    own loop, so a call to this rule does not collect it. The sweep that
    does collect it is run afterwards, which is what proves the reading
    would have seen a collection had one happened.
    """
    from PySide6.QtCore import QCoreApplication, QEvent, QObject

    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    holder = QObject()
    child = QObject(holder)
    assert len(holder.children()) == 1
    child.deleteLater()
    assert shipped.safe_process_events("a deferred delete") is True
    assert len(holder.children()) == 1
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert holder.children() == []


def test_an_event_whose_owner_was_thrown_away_is_dropped_without_a_crash():
    """A queued event for a dead owner reached its handler, or crashed."""
    from PySide6.QtCore import QCoreApplication

    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    import shiboken6

    sink: dict = {"dispatched": []}
    doomed = work_receiver(sink)
    QCoreApplication.postEvent(doomed, work_event("for a dead owner", None))
    shiboken6.delete(doomed)
    assert shipped.safe_process_events("owner thrown away") is True
    assert sink["dispatched"] == []
    live = work_receiver(sink)
    QCoreApplication.postEvent(live, work_event("for a live owner", None))
    assert shipped.safe_process_events("owner still alive") is True
    assert sink["dispatched"] == ["for a live owner"]
    live.deleteLater()


def test_an_object_that_is_not_an_event_is_refused_by_the_library():
    """A value that is not an event was queued, so the rule would dispatch it.

    The refusal is worded by the interface library. The surface queues
    plain work and has no posting of its own, so it cannot word this one;
    both are pinned here rather than compared.
    """
    from PySide6.QtCore import QCoreApplication

    app()
    sink = {"dispatched": []}
    receiver = work_receiver(sink)
    with pytest.raises(TypeError) as reported:
        QCoreApplication.postEvent(receiver, "not an event")
    headline = refusal_headline(str(reported.value))
    assert "postEvent" in headline, headline
    assert sink["dispatched"] == []
    receiver.deleteLater()
    with pytest.raises(AttributeError):
        surface.SafeEventsModel().postEvent


def test_an_event_carrying_nothing_the_handler_reads_is_still_dispatched():
    """An event with no payload was dropped rather than delivered."""
    from PySide6.QtCore import QCoreApplication, QEvent, QObject

    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    seen = []

    class BareReceiver(QObject):
        def event(self, incoming):
            seen.append(int(incoming.type()))
            return QObject.event(self, incoming)

    receiver = BareReceiver()
    QCoreApplication.postEvent(receiver, QEvent(QEvent.Type.User))
    assert seen == []
    assert shipped.safe_process_events("a bare event") is True
    assert int(QEvent.Type.User) in seen
    receiver.deleteLater()


def test_the_rule_reads_neither_argument_when_it_is_given_neither():
    """The rule needs a reason or a flag, so a bare call breaks."""
    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    assert shipped.safe_process_events() is True
    assert surface.SafeEventsModel().process_events() is True
    assert (
        shipped_defaults()
        == surface.build_view_model(surface.SafeEventsModel())["defaults"]
    )


# The guard is per thread


def test_the_guard_one_thread_raises_is_down_in_another_on_both_sides():
    """A worker thread is blocked by the interface thread's own guard."""
    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    answers: dict = {}

    def read_shipped() -> None:
        answers["shipped"] = shipped._is_in_call()

    def read_model(model) -> None:
        answers["model"] = model.is_in_call()

    sink = {"dispatched": []}
    receiver = work_receiver(sink)
    from PySide6.QtCore import QCoreApplication

    def inside() -> None:
        worker = threading.Thread(target=read_shipped)
        worker.start()
        worker.join()
        answers["here"] = shipped._is_in_call()

    QCoreApplication.postEvent(receiver, work_event("inside", inside))
    assert shipped.safe_process_events("per thread") is True
    assert answers["here"] is True
    assert answers["shipped"] is False
    model = surface.SafeEventsModel()

    def inside_model() -> None:
        worker = threading.Thread(target=lambda: read_model(model))
        worker.start()
        worker.join()
        answers["model_here"] = model.is_in_call()

    model.post("inside", inside_model)
    assert model.process_events("per thread") is True
    assert answers["model_here"] is True
    assert answers["model"] is False
    assert surface.GUARD_IS_PER_THREAD is True
    receiver.deleteLater()


# The enumeration


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            target = node.args[0]
            found.append(
                (
                    dotted(node.func.value),
                    "lambda" if isinstance(target, ast.Lambda) else dotted(target),
                )
            )
    return sorted(found)


def timer_sites(path) -> list:
    """Every ``QTimer(`` construction in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path) -> list:
    """Every ``subscribe(`` site in `path`, as the topic it names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


WIDGET_NAMES = ("QLabel", "QFrame", "QPushButton", "QWidget", "QVBoxLayout")


def widget_sites(path) -> list:
    """Every construction of a named interface element in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sorted(
        dotted(node.func)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and dotted(node.func).split(".")[-1] in WIDGET_NAMES
    )


def test_the_rule_connects_no_signal_and_the_counter_can_report():
    """The rule connects a signal the surface names no action for."""
    sites = connect_sites(SHIPPED_SOURCE)
    assert sites == [], sites
    assert len(sites) == CONNECT_TOTAL
    assert surface.ACTIONS == {}
    assert len(surface.ACTIONS) == CONNECT_TOTAL
    assert SHIPPED_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    neighbour = connect_sites(CONNECT_NEIGHBOUR)
    assert neighbour == [("self.clicked", "self._on_click")], neighbour
    assert len(neighbour) == 1


def test_the_rule_holds_no_timer_and_the_counter_can_report():
    """The rule runs a timer the surface declares no delay for."""
    assert timer_sites(SHIPPED_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    neighbour = timer_sites(TIMER_NEIGHBOUR)
    assert len(neighbour) >= 1, "the timer counter reports nothing"
    assert timer_sites(TIMER_NAMESAKE) == []


def test_the_rule_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The rule listens on a topic the surface names none of."""
    assert bus_sites(SHIPPED_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


def test_the_rule_builds_no_interface_element_and_the_counter_can_report():
    """The rule builds something on screen the surface describes nothing of.

    This is what proves the file has no visible part. The same counter is
    pointed at a file that really builds elements and reports there.
    """
    assert widget_sites(SHIPPED_SOURCE) == []
    assert len(widget_sites(SHIPPED_SOURCE)) == WIDGET_TOTAL
    assert surface.WIDGETS == ()
    assert surface.PAINTS is False
    neighbour = widget_sites(WIDGET_NEIGHBOUR)
    assert len(neighbour) >= 2, "the element counter reports nothing"
    assert "QLabel" in neighbour


def test_nothing_the_rule_answers_is_something_that_can_be_painted():
    """The rule hands back something with a picture, which a render would need."""
    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    assert shipped.safe_process_events(PLAIN_REASON) is True
    assert isinstance(shipped.safe_process_events(PLAIN_REASON), bool)
    assert shipped.reset_for_test() is None
    assert isinstance(shipped._is_in_call(), bool)
    model = surface.SafeEventsModel()
    assert isinstance(model.process_events(PLAIN_REASON), bool)
    assert model.reset_for_test() is None
    for value in surface.build_view_model(model).values():
        assert isinstance(value, (bool, int, str, list, dict)), value


SHIPPED_FUNCTIONS = {
    "_is_in_call": "SafeEventsModel.is_in_call",
    "safe_process_events": "SafeEventsModel.process_events",
    "reset_for_test": "SafeEventsModel.reset_for_test",
}

# What the surface holds that the shipped rule reads from the world
# rather than declaring, each with the shipped behaviour it stands for.
EXTRA_MODEL_METHODS = {
    "post": "the library's own queue, which processEvents is what empties",
}
EXTRA_PARAMETERS = {
    "has_toolkit": "whether the import of the library succeeded",
    "has_app": "whether QApplication.instance() answered an object",
}


def shipped_functions() -> list:
    """Every function the shipped module declares, read off the module.

    A signal is callable and is not a function, so the reader excludes by
    type rather than by whether a name can be called.
    """
    from PySide6.QtCore import Signal

    from src.gui import qt_safe_events as shipped

    return sorted(
        name
        for name, value in vars(shipped).items()
        if callable(value)
        and not isinstance(value, Signal)
        and getattr(value, "__module__", None) == shipped.__name__
    )


def test_every_shipped_function_has_a_counterpart():
    """The shipped rule gained or lost a function."""
    found = shipped_functions()
    assert found == sorted(SHIPPED_FUNCTIONS), found
    assert len(found) == SHIPPED_FUNCTION_TOTAL
    for counterpart in SHIPPED_FUNCTIONS.values():
        holder, _, attribute = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), attribute)), counterpart


def test_the_shipped_rule_declares_no_class_and_no_signal():
    """The shipped rule declares a class or a signal nothing stands for."""
    from PySide6.QtCore import Signal

    from src.gui import qt_safe_events as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == [], classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    signals = [
        name for name, value in vars(shipped).items() if isinstance(value, Signal)
    ]
    assert signals == [], signals
    assert len(signals) == SHIPPED_SIGNAL_TOTAL
    assert surface.SIGNALS == ()


def test_the_function_reader_counts_no_signal_as_a_function():
    """A signal is callable, so the counter would report one too many.

    The shipped rule declares none, so the reader is pointed at a class
    that does. Its ``clicked`` is a signal, is callable, and must not be
    counted as a method.
    """
    from PySide6.QtCore import Signal

    from src.gui.launcher import ModeCard

    assert SIGNAL_NEIGHBOUR.is_file()
    assert ModeCard.__module__ == "src.gui.launcher"
    declared = [
        name for name, value in vars(ModeCard).items() if isinstance(value, Signal)
    ]
    assert declared == ["clicked"], declared
    assert callable(ModeCard.clicked)
    counted = [
        name
        for name, value in vars(ModeCard).items()
        if callable(value) and not isinstance(value, Signal)
    ]
    assert "clicked" not in counted
    assert len(counted) >= 1, "the function counter reports nothing"


def test_every_surface_class_and_extra_name_stands_for_something_shipped():
    """The surface grew a class, a method or an argument for nothing."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == ["SafeEventsModel"], built
    named = {
        counterpart.partition(".")[2] for counterpart in SHIPPED_FUNCTIONS.values()
    }
    named |= set(EXTRA_MODEL_METHODS)
    mine = {
        name
        for name in vars(surface.SafeEventsModel)
        if callable(vars(surface.SafeEventsModel)[name]) and not name.startswith("_")
    }
    assert mine == named, sorted(mine ^ named)
    given = set(inspect.signature(surface.SafeEventsModel.process_events).parameters)
    shipped_given = set(shipped_defaults())
    assert given - {"self"} - shipped_given == set(EXTRA_PARAMETERS)


# The completeness check


def named_payloads() -> dict:
    """The payloads the completeness check reads."""
    return {
        name: surface.build_view_model(drive_new(BY_NAME[name])[0])
        for name in (
            "nothing_queued",
            "the_library_is_absent",
            "a_nested_call_with_a_reason",
            "a_nested_call_with_no_reason",
            "no_application_object",
            "a_reset_after_a_call",
            "a_nested_call_that_forces_past_the_guard",
        )
    }


BUILT = "nothing_queued"

PAYLOAD_KEYS = {
    "METHOD": f"{BUILT}:method",
    "LOGGER_NAME": f"{BUILT}:logger.name",
    "SKIP_LOG_LEVEL": f"{BUILT}:logger.level",
    "SKIP_LOG_TEMPLATE": f"{BUILT}:logger.template",
    "DEFAULT_REASON": f"{BUILT}:defaults.reason",
    "DEFAULT_FORCE": f"{BUILT}:defaults.force",
    "GUARD_IS_PER_THREAD": f"{BUILT}:guard.per_thread",
    "OUTCOMES": f"{BUILT}:endings",
    "RETURNS_TRUE": f"{BUILT}:answers_true",
    "CALL_NAMES": f"{BUILT}:call_names",
    "SIGNALS": f"{BUILT}:signals",
    "ACTIONS": f"{BUILT}:actions",
    "TIMERS": f"{BUILT}:timers",
    "TIMER_DELAYS_MS": f"{BUILT}:timer_delays_ms",
    "BUS_TOPICS": f"{BUILT}:bus_topics",
    "WIDGETS": f"{BUILT}:widgets",
    "PAINTS": f"{BUILT}:paints",
}

# Values a payload carries inside a longer list rather than alone.
TEXT_INSIDE = {
    "PROCESSED": f"{BUILT}:outcomes",
    "NO_TOOLKIT": "the_library_is_absent:outcomes",
    "REENTRANT": "a_nested_call_with_a_reason:outcomes",
    "NO_APP": "no_application_object:outcomes",
}

# The twelve branch markers, each carried inside the calls one drive left.
CALL_CONSTANTS = {
    "TOOLKIT_MISSING": "the_library_is_absent",
    "GUARD_READ": BUILT,
    "GUARD_FIRED": "a_nested_call_with_a_reason",
    "GUARD_FORCED": "a_nested_call_that_forces_past_the_guard",
    "SKIP_LOGGED": "a_nested_call_with_a_reason",
    "SKIP_SILENT": "a_nested_call_with_no_reason",
    "GUARD_SET": BUILT,
    "APP_CHECKED": BUILT,
    "APP_MISSING": "no_application_object",
    "EVENTS_PROCESSED": BUILT,
    "GUARD_CLEARED": BUILT,
    "GUARD_RESET": "a_reset_after_a_call",
}

# Snapshot keys built from what a drive did rather than carrying a value.
DERIVED_KEYS = {
    "returned": "test_the_two_sides_apply_the_same_rule",
    "records": "test_the_guard_writes_a_record_only_when_it_is_given_a_reason",
    "dispatched": "test_the_rule_dispatches_a_real_posted_event",
    "app_consulted": "test_a_forced_call_drains_the_queue_the_call_around_it_was_draining",
    "pending": "test_the_two_sides_apply_the_same_rule",
}

# Snapshot keys no side-by-side reading covers, each with its own check.
OUTSIDE_THE_QT_TRACE = {
    "logger": "test_the_shipped_logger_carries_the_name_and_level_the_surface_names",
    "outcomes": "test_the_four_endings_are_told_apart_on_both_sides",
    "endings": "test_the_four_endings_are_told_apart_on_both_sides",
    "answers_true": "test_every_ending_answers_what_the_shipped_rule_answers",
    "paints": "test_the_rule_builds_no_interface_element_and_the_counter_can_report",
    "widgets": "test_the_rule_builds_no_interface_element_and_the_counter_can_report",
    "signals": "test_the_shipped_rule_declares_no_class_and_no_signal",
    "actions": "test_the_rule_connects_no_signal_and_the_counter_can_report",
    "timers": "test_the_rule_holds_no_timer_and_the_counter_can_report",
    "timer_delays_ms": "test_the_rule_holds_no_timer_and_the_counter_can_report",
    "bus_topics": "test_the_rule_subscribes_to_no_bus_topic_and_the_counter_can_report",
    "call_names": "test_every_branch_marker_fires_on_a_drive_of_the_shipped_rule",
    "calls": "test_every_branch_marker_fires_on_a_drive_of_the_shipped_rule",
    "method": "test_the_bridge_registers_the_safe_events_method",
}

PLAIN_TYPES = (str, bool, int, float, tuple, list, dict, type(None))

IMPORTED_NAMES = {"annotations", "threading", "Any", "Callable", "Optional"}


def at_path(payloads, path):
    """The value one ``name:dotted.path`` names."""
    name, _, dotted_path = path.partition(":")
    found = payloads[name]
    for step in dotted_path.split("."):
        found = found[int(step)] if step.isdigit() else found[step]
    return found


def surface_constants() -> dict:
    """Every plain value the surface exports."""
    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and isinstance(value, PLAIN_TYPES)
    }


def as_json_shape(value):
    """`value` with every tuple turned into the list a payload carries."""
    if isinstance(value, (tuple, list)):
        return [as_json_shape(inner) for inner in value]
    if isinstance(value, dict):
        return {key: as_json_shape(inner) for key, inner in value.items()}
    return value


def unaccounted_constants(payloads, constants) -> list:
    """The exported values that reach no snapshot and no named check."""
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payloads, PAYLOAD_KEYS[name]) == as_json_shape(value), name
        elif name in TEXT_INSIDE:
            assert value in at_path(payloads, TEXT_INSIDE[name]), name
        elif name in CALL_CONSTANTS:
            assert value in payloads[CALL_CONSTANTS[name]]["calls"], name
        else:
            unaccounted.append(name)
    return unaccounted


def unbacked_keys(built) -> set:
    """The snapshot keys no exported value and no named check backs."""
    answered = {path.partition(":")[2].split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {path.partition(":")[2].split(".")[0] for path in TEXT_INSIDE.values()}
    answered.add("calls")
    return set(built) ^ (answered | set(DERIVED_KEYS))


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read."""
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    found = unaccounted_constants(named_payloads(), constants)
    assert found == [], found
    assert len(PAYLOAD_KEYS) == 17
    assert len(TEXT_INSIDE) == 4
    assert len(CALL_CONSTANTS) == CALL_NAME_TOTAL
    assert len(CALL_CONSTANTS) == len(surface.CALL_NAMES)


def test_no_exported_name_slips_past_the_value_reader():
    """A value of an unexpected type is read by nothing at all."""
    import types

    everything = {
        name
        for name, value in vars(surface).items()
        if not name.startswith("__")
        and not isinstance(value, types.ModuleType)
        or name == "threading"
    }
    functions = {
        name
        for name, value in vars(surface).items()
        if callable(value) and getattr(value, "__module__", None) == surface.__name__
    }
    leftover = everything - functions - set(surface_constants())
    assert leftover == IMPORTED_NAMES, sorted(leftover ^ IMPORTED_NAMES)


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    built = named_payloads()[BUILT]
    assert unbacked_keys(built) == set(), sorted(unbacked_keys(built))
    assert len(built) == PAYLOAD_KEY_TOTAL
    for key, covered_by in DERIVED_KEYS.items():
        assert key in built
        assert callable(globals()[covered_by]), (key, covered_by)


def test_every_snapshot_key_the_shipped_reading_cannot_answer_names_its_check():
    """A key no side-by-side reading covers is covered by nothing at all."""
    built = named_payloads()[BUILT]
    compared = set(new_trace(BY_NAME[BUILT]))
    assert compared == set(built) - set(OUTSIDE_THE_QT_TRACE), sorted(compared)
    assert len(compared) == TRACE_KEY_TOTAL
    for key, covered_by in OUTSIDE_THE_QT_TRACE.items():
        assert key in built, key
        assert callable(globals()[covered_by]), (key, covered_by)


def test_both_completeness_checks_report_what_they_are_given():
    """Both completeness checks passed because they look at nothing."""
    payloads = named_payloads()
    constants = dict(surface_constants())
    constants["INVENTED_CONSTANT"] = "never in any snapshot"
    assert unaccounted_constants(payloads, constants) == ["INVENTED_CONSTANT"]
    assert unaccounted_constants(payloads, surface_constants()) == []
    grown = dict(payloads[BUILT])
    grown["invented_key"] = 1
    assert unbacked_keys(grown) == {"invented_key"}
    assert unbacked_keys(payloads[BUILT]) == set()
    shrunk = {key: value for key, value in payloads[BUILT].items() if key != "guard"}
    assert unbacked_keys(shrunk) == {"guard"}
    assert "build_view_model" not in surface_constants()
    assert "SafeEventsModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payloads, f"{BUILT}:logger.invented")


def test_every_branch_marker_fires_on_a_drive_of_the_shipped_rule():
    """A branch the surface declares is never taken on any real drive."""
    seen = set()
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        seen.update(drive_new(spec)[0].calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    for marker, scenario_name in CALL_CONSTANTS.items():
        value = getattr(surface, marker)
        assert value in drive_new(BY_NAME[scenario_name])[0].calls, marker
    quiet = drive_new(BY_NAME["a_nested_call_with_no_reason"])[0]
    assert surface.SKIP_SILENT in quiet.calls
    assert surface.SKIP_LOGGED not in quiet.calls
    assert quiet.records == []


def test_every_ending_answers_what_the_shipped_rule_answers():
    """An ending answers true where the shipped rule answers false."""
    for ending in surface.OUTCOMES:
        assert surface.outcome_returns(ending) is (ending in surface.RETURNS_TRUE)
    assert surface.RETURNS_TRUE == (surface.PROCESSED,)
    assert len(surface.OUTCOMES) == ENDING_TOTAL
    assert len(set(surface.OUTCOMES)) == ENDING_TOTAL
    from src.gui import qt_safe_events as shipped

    app()
    shipped.reset_for_test()
    assert shipped.safe_process_events(PLAIN_REASON) is True
    with toolkit_absent():
        assert shipped.safe_process_events(PLAIN_REASON) is False


# The surface carries its own values


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_rule(monkeypatch):
    """The surface read its values off the rule it replaces.

    A surface that read the shipped module would follow it, and the whole
    comparison above would be one side read twice. The message template
    is moved where the shipped rule reads it, and the surface must not
    move with it.
    """
    from src.gui import qt_safe_events as shipped

    before = old_outcome(BY_NAME["a_nested_call_with_a_reason"])["value"]
    assert before["records"][0]["template"] == surface.SKIP_LOG_TEMPLATE

    moved = "MOVED TEMPLATE: %s"
    held = shipped.safe_process_events

    def with_moved_template(reason="", force=False):
        if shipped._is_in_call() and not force:
            if reason:
                shipped.logger.debug(moved, reason)
            return False
        return held(reason, force)

    monkeypatch.setattr(shipped, "safe_process_events", with_moved_template)
    after = old_outcome(BY_NAME["a_nested_call_with_a_reason"])["value"]
    assert after["records"][0]["template"] == moved
    assert after["records"][0]["template"] != before["records"][0]["template"]
    assert digest(after) != digest(before)
    difference = [
        key for key in before if canonical(before[key]) != canonical(after[key])
    ]
    assert difference == ["records"], difference

    mine = new_outcome(BY_NAME["a_nested_call_with_a_reason"])["value"]
    assert mine["records"][0]["template"] == surface.SKIP_LOG_TEMPLATE
    assert mine["records"][0]["template"] == before["records"][0]["template"]
    assert surface.SKIP_LOG_TEMPLATE != moved
    monkeypatch.undo()
    assert digest(
        old_outcome(BY_NAME["a_nested_call_with_a_reason"])["value"]
    ) == digest(before)


def answers_nothing(reason="", force=False):
    """A shipped rule that answers nothing at all."""
    return None


def test_the_surface_does_not_follow_a_rule_that_answers_nothing(monkeypatch):
    """The surface asked the shipped rule for its answers."""
    from src.gui import qt_safe_events as shipped

    before = new_outcome(BY_NAME["one_piece_of_work"])["value"]
    monkeypatch.setattr(shipped, "safe_process_events", answers_nothing)
    assert shipped.safe_process_events("nothing at all") is None
    assert new_outcome(BY_NAME["one_piece_of_work"])["value"] == before
    monkeypatch.undo()
    app()
    shipped.reset_for_test()
    assert shipped.safe_process_events(PLAIN_REASON) is True


def test_the_shipped_rule_holds_one_piece_of_shared_state_and_it_is_per_thread():
    """The rule writes a shared table a later test would read.

    The one shared thing is the per-thread flag, which every drive here
    puts down before and after it runs. Nothing else in the module is a
    list, a dict or a set.
    """
    from src.gui import qt_safe_events as shipped

    containers = sorted(
        name
        for name, value in vars(shipped).items()
        if not name.startswith("__") and isinstance(value, (list, dict, set))
    )
    assert containers == [], containers
    assert isinstance(shipped._local, threading.local)
    shipped.reset_for_test()
    assert shipped._is_in_call() is False
    mine = sorted(
        name
        for name, value in vars(surface).items()
        if not name.startswith("__") and isinstance(value, (list, dict, set))
    )
    assert mine, "the container counter reports nothing"


# The bridge


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_safe_events_method():
    """The renderer cannot reach the guard over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "qt_safe_events.state"
    answer = bridge_answer({})
    assert answer["ok"] is True
    assert answer["result"]["outcomes"] == [surface.PROCESSED]
    assert answer["result"]["method"] == surface.METHOD


def test_the_bridge_runs_the_call_a_request_asks_for():
    """The bridge ignored the reason, the flag or the world a request named."""
    absent = bridge_answer({"reason": PLAIN_REASON, "has_toolkit": False})["result"]
    assert absent["outcomes"] == [surface.NO_TOOLKIT]
    assert absent["returned"] == [False]
    no_app = bridge_answer({"reason": PLAIN_REASON, "has_app": False})["result"]
    assert no_app["outcomes"] == [surface.NO_APP]
    busy = bridge_answer({"pending": 3})["result"]
    assert busy["dispatched"] == ["work 0", "work 1", "work 2"]
    assert busy["pending"] == 0


def test_the_bridge_reports_a_request_the_surface_cannot_run():
    """A request the surface refuses came back as an answer."""
    answer = bridge_answer({"pending": "three"})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"reason": PLAIN_REASON, "pending": 2})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["method"] == surface.METHOD
    assert encoded["result"]["dispatched"] == ["work 0", "work 1"]


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'qt_safe_events.state', 'params':"
    " {'reason': 'paint connection status', 'pending': 2}}),"
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
    """Reaching the guard pulled the interface library into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["outcomes"] == [surface.PROCESSED]
    assert result["dispatched"] == ["work 0", "work 1"]


def test_the_qt_probe_can_report_qt():
    """The probe reports the library absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
