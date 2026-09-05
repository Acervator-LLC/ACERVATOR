"""The shipped opacity pulse driver and the Qt-free surface, side by side.

A failure means the surface moves the phase differently, hands a widget a
different opacity, passes over a different widget, leaves the timer in a
different state or refuses differently than ``PulseManager`` does on the
same steps.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import pulse_manager_surface as surface

REPO_ROOT = Path(__file__).resolve().parents[1]
SHIPPED_SOURCE = REPO_ROOT / "src" / "gui" / "widgets" / "pulse_manager.py"
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
TIMER_NAMESAKE = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
WIDGET_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"

CONNECT_TOTAL = 1
TIMER_TOTAL = 1
BUS_TOTAL = 0
WIDGET_TOTAL = 0
SHIPPED_CLASS_TOTAL = 1
SHIPPED_SIGNAL_TOTAL = 0
SHIPPED_METHOD_TOTAL = 3
PAYLOAD_KEY_TOTAL = 28
CONSTANT_TOTAL = 31
TRACE_KEY_TOTAL = 6
CALL_NAME_TOTAL = 9

LONG_NAME = "L" * 200
MARKUP_NAME = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_NAME = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_NAME = "line one\nline two"
APOSTROPHE_NAME = "Ekthelius' accent button"
WRONG_CAPITALS_NAME = "aCCENT buttON"

PLAIN_TYPES = (str, bool, int, float, tuple, list, dict, type(None))


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


# The widgets both sides are handed. One set per side, same kinds.


class RecordingWidget:
    """A widget that takes every opacity it is handed."""

    def __init__(self, name) -> None:
        self.name = name
        self.opacities: list = []

    def setWindowOpacity(self, opacity) -> None:
        self.opacities.append(opacity)


class WidgetWithoutTheSetter:
    """A registered object with no opacity setter at all."""

    def __init__(self, name) -> None:
        self.name = name
        self.opacities: list = []


class WidgetThatIsGone(RecordingWidget):
    """A widget whose underlying object was thrown away.

    A real deleted Qt widget answers its setter attribute and then raises
    ``RuntimeError`` when the setter runs, which
    ``test_a_real_deleted_widget_raises_the_error_the_driver_swallows``
    measures on the interface library itself.
    """

    def setWindowOpacity(self, opacity) -> None:
        self.opacities.append(opacity)
        raise RuntimeError("this widget is gone")


class WidgetThatRefuses(RecordingWidget):
    """A widget whose setter refuses with an error nothing swallows."""

    def setWindowOpacity(self, opacity) -> None:
        self.opacities.append(opacity)
        raise ValueError("this widget refuses the opacity")


KINDS = {
    "records": RecordingWidget,
    "no_setter": WidgetWithoutTheSetter,
    "gone": WidgetThatIsGone,
    "refuses": WidgetThatRefuses,
}


def make_widget(name, kind):
    return KINDS[kind](name)


# The inputs. One scenario drives both sides.


def scenario(name, steps):
    return {"name": name, "steps": tuple(steps)}


def phase(value):
    return ("phase", value, None)


def reg(name, kind="records"):
    return ("register", name, kind)


def advance(elapsed_ms):
    return ("advance", elapsed_ms, None)


TICK = ("tick", None, None)
START = ("start", None, None)
STOP = ("stop", None, None)

SCENARIOS = [
    scenario("one_widget_one_fire", [reg("accent button"), TICK]),
    scenario("one_widget_three_fires", [reg("accent button"), TICK, TICK, TICK]),
    scenario("three_widgets_one_fire", [reg("a"), reg("b"), reg("c"), TICK]),
    scenario("no_widget_registered", [TICK]),
    scenario("no_fire_at_all", [reg("accent button")]),
    scenario("nothing_at_all", []),
    scenario("zero_elapsed_time", [reg("a"), advance(0)]),
    scenario("a_whole_number_zero_phase", [phase(0), reg("a"), TICK]),
    scenario("a_widget_with_no_opacity_setter", [reg("plain", "no_setter"), TICK]),
    scenario(
        "a_widget_whose_object_is_gone",
        [reg("gone", "gone"), reg("after it", "records"), TICK],
    ),
    scenario(
        "every_widget_is_gone",
        [reg("gone one", "gone"), reg("gone two", "gone"), TICK],
    ),
    scenario(
        "a_widget_that_refuses",
        [reg("rude", "refuses"), reg("after it", "records"), TICK],
    ),
    scenario(
        "a_good_widget_then_one_that_refuses",
        [reg("first"), reg("rude", "refuses"), TICK],
    ),
    scenario("negative_phase", [phase(-500.25), reg("a"), TICK]),
    scenario("a_thousand_million_phase", [phase(1_000_000_000), reg("a"), TICK]),
    scenario("one_billionth_phase", [phase(1e-9), reg("a"), TICK]),
    scenario("a_whole_number_phase", [phase(12), reg("a"), TICK]),
    scenario("the_same_phase_written_as_a_decimal", [phase(12.0), reg("a"), TICK]),
    scenario("infinity_phase", [phase(math.inf), reg("a"), TICK]),
    scenario("minus_infinity_phase", [phase(-math.inf), reg("a"), TICK]),
    scenario("not_a_number_phase", [phase(math.nan), reg("a"), TICK]),
    scenario("text_where_a_number_belongs", [phase("fifty"), reg("a"), TICK]),
    scenario("nothing_where_a_number_belongs", [phase(None), reg("a"), TICK]),
    scenario("a_flag_where_a_number_belongs", [phase(True), reg("a"), TICK]),
    scenario("one_delay_of_elapsed_time", [reg("a"), advance(50)]),
    scenario("ten_delays_of_elapsed_time", [reg("a"), advance(500)]),
    scenario("less_than_one_delay_of_elapsed_time", [reg("a"), advance(49)]),
    scenario("negative_elapsed_time", [reg("a"), advance(-500)]),
    scenario("one_billionth_of_elapsed_time", [reg("a"), advance(1e-9)]),
    scenario("infinite_elapsed_time", [reg("a"), advance(math.inf)]),
    scenario("minus_infinite_elapsed_time", [reg("a"), advance(-math.inf)]),
    scenario("not_a_number_elapsed_time", [reg("a"), advance(math.nan)]),
    scenario("text_where_an_elapsed_time_belongs", [reg("a"), advance("fifty")]),
    scenario("unicode_name", [reg(UNICODE_NAME), TICK]),
    scenario("a_two_hundred_character_name", [reg(LONG_NAME), TICK]),
    scenario("markup_in_the_name", [reg(MARKUP_NAME), TICK]),
    scenario("an_apostrophe_in_the_name", [reg(APOSTROPHE_NAME), TICK]),
    scenario("wrong_capitals_in_the_name", [reg(WRONG_CAPITALS_NAME), TICK]),
    scenario("a_newline_in_the_name", [reg(NEWLINE_NAME), TICK]),
    scenario("a_number_where_a_name_belongs", [reg(42), TICK]),
    scenario("nothing_where_a_name_belongs", [reg(None), TICK]),
    scenario("start_when_already_started", [START, reg("a"), TICK]),
    scenario("start_twice_more", [START, START, reg("a"), TICK]),
    scenario("stop", [STOP, reg("a"), TICK]),
    scenario("stop_when_already_stopped", [STOP, STOP, reg("a"), TICK]),
    scenario("start_after_stop", [STOP, START, reg("a"), TICK]),
    scenario("stop_fire_then_start_again", [STOP, reg("a"), TICK, START, TICK]),
    scenario(
        "the_whole_driver",
        [
            phase(0.0),
            reg("first"),
            reg("plain", "no_setter"),
            reg("gone", "gone"),
            reg("last"),
            TICK,
            advance(150),
            STOP,
            TICK,
            START,
        ],
    ),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}

# Refusals both sides raise from the same Python operation, so both word
# them with one string.
REFUSING_SCENARIOS = (
    "a_widget_that_refuses",
    "a_good_widget_then_one_that_refuses",
    "infinity_phase",
    "minus_infinity_phase",
    "text_where_a_number_belongs",
    "nothing_where_a_number_belongs",
    "infinite_elapsed_time",
    "minus_infinite_elapsed_time",
    "not_a_number_elapsed_time",
    "text_where_an_elapsed_time_belongs",
)


# Driving the two sides


def trace(phase_before, phase_after, seen, registered, active, interval, fires) -> dict:
    """The reading both sides answer, key for key."""
    return {
        "phase_before": phase_before,
        "phase": phase_after,
        "seen": seen,
        "registered": registered,
        "timer": {"active": active, "interval_ms": interval},
        "fires": fires,
    }


def elapsed_to_fires_old(manager, elapsed_ms) -> int:
    """How many times a real timer at its own delay fires in `elapsed_ms`.

    The shipped driver holds a live timer and no function that counts its
    fires, so the count is taken here from the delay read off that timer.
    No clock is read: `elapsed_ms` is a value the scenario hands in.
    """
    return int(elapsed_ms // manager._timer.interval())


def drive_old(spec) -> dict:
    """The shipped driver, driven by one scenario."""
    from src.gui.widgets.pulse_manager import PulseManager

    app()
    manager = PulseManager()
    widgets: list = []
    fires: list = []
    phase_before = manager._phase
    try:
        for kind, first, second in spec["steps"]:
            if kind == "phase":
                manager._phase = first
                phase_before = manager._phase
            elif kind == "register":
                widget = make_widget(first, second)
                widgets.append(widget)
                manager.register(widget)
            elif kind == "tick":
                manager._tick()
                fires.append(1)
            elif kind == "advance":
                run = elapsed_to_fires_old(manager, first)
                for _ in range(run):
                    manager._tick()
                fires.append(run)
            elif kind == "start":
                manager._timer.start(manager._timer.interval())
            else:
                manager._timer.stop()
        return trace(
            phase_before,
            manager._phase,
            [
                {"target": widget.name, "opacities": list(widget.opacities)}
                for widget in manager._widgets
            ],
            len(manager._widgets),
            manager._timer.isActive(),
            manager._timer.interval(),
            fires,
        )
    finally:
        manager._timer.stop()


def drive_new(spec):
    """The Qt-free model, driven by the same scenario."""
    model = surface.PulseModel()
    fires: list = []
    phase_before = model.phase
    for kind, first, second in spec["steps"]:
        if kind == "phase":
            model.phase = first
            phase_before = model.phase
        elif kind == "register":
            model.register(make_widget(first, second))
        elif kind == "tick":
            model.tick()
            fires.append(1)
        elif kind == "advance":
            fires.append(model.advance(first))
        elif kind == "start":
            model.start()
        else:
            model.stop()
    return model, phase_before, fires


def new_trace(spec) -> dict:
    model, phase_before, fires = drive_new(spec)
    payload = surface.build_view_model(model)
    return trace(
        phase_before,
        payload["phase"],
        payload["seen"],
        payload["registered"],
        payload["timer"]["active"],
        payload["timer"]["interval_ms"],
        fires,
    )


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
    return outcome(lambda: drive_old(spec))


def new_outcome(spec) -> dict:
    return outcome(lambda: new_trace(spec))


def refusal_headline(message) -> str:
    """The first line of a refusal, which is the one that names the cause."""
    return message.splitlines()[0].strip() if message else ""


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_run_the_same_pulse(name):
    """A phase, an opacity handed to a widget or the timer state differs."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert name in REFUSING_SCENARIOS, name
        assert new["error"] == old["error"], (name, old, new)
        assert refusal_headline(new["message"]) == refusal_headline(old["message"]), (
            name,
            old["message"],
            new["message"],
        )
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


@pytest.mark.parametrize("name", REFUSING_SCENARIOS)
def test_a_refusal_from_the_same_operation_is_worded_the_same(name):
    """One side worded a refusal both sides raise from the same operation."""
    old = old_outcome(BY_NAME[name])
    new = new_outcome(BY_NAME[name])
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["message"]) == (old["error"], old["message"]), name


REFUSAL_ERRORS = {
    "a_widget_that_refuses": "ValueError",
    "a_good_widget_then_one_that_refuses": "ValueError",
    "infinity_phase": "ValueError",
    "minus_infinity_phase": "ValueError",
    "text_where_a_number_belongs": "TypeError",
    "nothing_where_a_number_belongs": "TypeError",
    "infinite_elapsed_time": "ValueError",
    "minus_infinite_elapsed_time": "ValueError",
    "not_a_number_elapsed_time": "ValueError",
    "text_where_an_elapsed_time_belongs": "TypeError",
}


def test_each_refusal_carries_the_error_both_sides_measure():
    """A refusal changed which error it raises, on one side or on both."""
    for name, wanted in REFUSAL_ERRORS.items():
        assert old_outcome(BY_NAME[name])["error"] == wanted, name
        assert new_outcome(BY_NAME[name])["error"] == wanted, name
    assert set(REFUSAL_ERRORS) == set(REFUSING_SCENARIOS)
    assert len(set(REFUSAL_ERRORS.values())) == 2, "the refusals are all one error"


def test_an_endless_elapsed_time_is_refused_as_no_number_at_all():
    """An endless elapsed time is refused for a reason nobody measured.

    Dividing an endless time by the delay gives not-a-number, not an
    endless number, so the refusal names a value that is no number rather
    than one too large to hold.
    """
    assert math.isnan(math.inf // surface.TIMER_INTERVAL_MS)
    assert math.isnan(math.nan // surface.TIMER_INTERVAL_MS)
    refused = old_outcome(BY_NAME["infinite_elapsed_time"])
    assert refused["error"] == "ValueError"
    assert "NaN" in refused["message"] or "nan" in refused["message"].lower()
    assert refusal_headline(
        new_outcome(BY_NAME["infinite_elapsed_time"])["message"]
    ) == refusal_headline(refused["message"])


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    quiet = old_outcome(BY_NAME["no_fire_at_all"])["value"]
    busy = old_outcome(BY_NAME["one_widget_three_fires"])["value"]
    assert canonical(quiet) != canonical(busy)
    assert digest(quiet) != digest(busy)
    assert digest(quiet) == digest(old_outcome(BY_NAME["no_fire_at_all"])["value"])
    assert len(digest(quiet)) == 64


def test_the_two_control_inputs_really_end_in_different_states():
    """The difference control pair settles alike, so it can never report."""
    quiet = old_outcome(BY_NAME["no_fire_at_all"])["value"]
    busy = old_outcome(BY_NAME["one_widget_three_fires"])["value"]
    assert quiet["seen"][0]["opacities"] == []
    assert len(busy["seen"][0]["opacities"]) == 3
    assert quiet["phase"] == 0.0
    assert busy["phase"] != quiet["phase"]


def test_the_hash_reads_a_whole_number_and_a_not_a_number_as_text():
    """A whole number and a decimal hash the same, or two blanks differ."""
    assert 12 == 12.0
    assert digest({"n": 12}) != digest({"n": 12.0})
    assert math.nan != math.nan
    assert digest({"n": math.nan}) == digest({"n": math.nan})
    assert canonical({"n": math.nan}) == canonical({"n": math.nan})


def test_a_whole_number_phase_and_the_same_decimal_are_told_apart():
    """Two starting phases one number apart read as one, so a change hides."""
    whole = old_outcome(BY_NAME["a_whole_number_phase"])["value"]
    written = old_outcome(BY_NAME["the_same_phase_written_as_a_decimal"])["value"]
    assert whole["phase_before"] == written["phase_before"]
    assert repr(whole["phase_before"]) == "12"
    assert repr(written["phase_before"]) == "12.0"
    assert digest(whole) != digest(written)
    assert digest(new_outcome(BY_NAME["a_whole_number_phase"])["value"]) == digest(
        whole
    )


@pytest.mark.parametrize(
    "name",
    [
        "one_widget_one_fire",
        "the_whole_driver",
        "a_widget_whose_object_is_gone",
        "unicode_name",
    ],
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a reading that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == TRACE_KEY_TOTAL, sorted(value)
    assert value["seen"], name
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


# What one fire does


def test_the_first_fire_hands_out_the_opacity_the_shipped_driver_computes():
    """The two sides hand a widget different numbers on the first fire."""
    old = old_outcome(BY_NAME["one_widget_one_fire"])["value"]
    handed = old["seen"][0]["opacities"]
    assert len(handed) == 1
    assert handed[0] == surface.opacity_at(surface.PHASE_START + surface.PHASE_STEP)
    assert old["phase"] == surface.PHASE_START + surface.PHASE_STEP
    assert new_outcome(BY_NAME["one_widget_one_fire"])["value"] == old


def test_every_widget_gets_the_same_one_value_on_one_fire():
    """One fire hands different widgets different numbers."""
    old = old_outcome(BY_NAME["three_widgets_one_fire"])["value"]
    handed = [entry["opacities"] for entry in old["seen"]]
    assert len(handed) == 3
    assert handed[0] == handed[1] == handed[2]
    assert len(handed[0]) == 1
    assert new_outcome(BY_NAME["three_widgets_one_fire"])["value"] == old


def test_three_fires_hand_out_three_rising_values():
    """The fires hand out one repeated value, so the phase never moved."""
    old = old_outcome(BY_NAME["one_widget_three_fires"])["value"]
    handed = old["seen"][0]["opacities"]
    assert len(handed) == 3
    assert handed[0] < handed[1] < handed[2]
    assert len(set(handed)) == 3
    assert new_outcome(BY_NAME["one_widget_three_fires"])["value"] == old


def test_the_floor_and_the_ceiling_are_the_midpoint_either_side_of_the_swing():
    """The declared range is not the midpoint plus and minus the swing.

    The sum lands on the ceiling exactly. The difference lands one part in
    ten thousand million million above the floor, because a computer holds
    these numbers in binary, so the floor is read to that closeness.
    """
    assert surface.OPACITY_MID + surface.OPACITY_SWING == surface.OPACITY_CEILING
    assert surface.OPACITY_MID - surface.OPACITY_SWING != surface.OPACITY_FLOOR
    assert surface.OPACITY_MID - surface.OPACITY_SWING == pytest.approx(
        surface.OPACITY_FLOOR
    )
    assert surface.OPACITY_MID - surface.OPACITY_SWING > surface.OPACITY_FLOOR
    assert surface.OPACITY_FLOOR < surface.OPACITY_MID < surface.OPACITY_CEILING


def test_every_opacity_handed_out_sits_between_the_floor_and_the_ceiling():
    """A fire hands out a number outside the range the driver declares."""
    model = surface.PulseModel()
    widget = make_widget("range", "records")
    model.register(widget)
    for _ in range(400):
        model.tick()
    assert len(widget.opacities) == 400
    assert min(widget.opacities) >= surface.OPACITY_FLOOR
    assert max(widget.opacities) <= surface.OPACITY_CEILING
    assert min(widget.opacities) < surface.OPACITY_MID < max(widget.opacities)


def test_the_opacity_the_surface_computes_is_the_published_sine_wave():
    """The opacity is not the midpoint plus the swing times the sine."""
    for value in (0.0, 0.05, 1.5, -2.25, 100.0):
        assert surface.opacity_at(value) == (
            surface.OPACITY_MID + surface.OPACITY_SWING * math.sin(value)
        )
    assert surface.opacity_at(0.0) == surface.OPACITY_MID
    assert surface.opacity_at(math.pi / 2) == pytest.approx(surface.OPACITY_CEILING)
    assert surface.opacity_at(-math.pi / 2) == pytest.approx(surface.OPACITY_FLOOR)


def test_a_widget_with_no_setter_is_passed_over_and_the_rest_still_run():
    """A widget with no opacity setter stopped the fire or took a value."""
    old = old_outcome(BY_NAME["a_widget_with_no_opacity_setter"])["value"]
    assert old["seen"][0]["opacities"] == []
    assert old["phase"] == surface.PHASE_START + surface.PHASE_STEP
    assert new_outcome(BY_NAME["a_widget_with_no_opacity_setter"])["value"] == old
    model = drive_new(BY_NAME["a_widget_with_no_opacity_setter"])[0]
    assert model.skipped == [0]
    assert model.applied == []
    running = drive_new(BY_NAME["one_widget_one_fire"])[0]
    assert running.skipped == []
    assert len(running.applied) == 1


def test_a_widget_whose_object_is_gone_is_passed_over_and_the_rest_still_run():
    """A dead widget stopped the fire, so the ones after it lost the value."""
    old = old_outcome(BY_NAME["a_widget_whose_object_is_gone"])["value"]
    assert len(old["seen"][0]["opacities"]) == 1
    assert len(old["seen"][1]["opacities"]) == 1
    assert old["seen"][0]["opacities"] == old["seen"][1]["opacities"]
    assert new_outcome(BY_NAME["a_widget_whose_object_is_gone"])["value"] == old
    model = drive_new(BY_NAME["a_widget_whose_object_is_gone"])[0]
    assert model.failed == [0]
    assert len(model.applied) == 1


def test_a_widget_that_refuses_with_another_error_ends_the_fire_on_both_sides():
    """A refusal nothing swallows was swallowed, so a fault would stay hidden."""
    old = old_outcome(BY_NAME["a_widget_that_refuses"])
    new = new_outcome(BY_NAME["a_widget_that_refuses"])
    assert old["outcome"] == "refused"
    assert new["outcome"] == "refused"
    assert old["error"] == new["error"] == "ValueError"
    swallowed = old_outcome(BY_NAME["a_widget_whose_object_is_gone"])
    assert swallowed["outcome"] == "answered"
    assert surface.SWALLOWED_ERROR == "RuntimeError"


def test_a_real_deleted_widget_raises_the_error_the_driver_swallows():
    """A dead Qt widget refuses with an error the driver does not swallow.

    The compared drives use a stand-in that raises ``RuntimeError``. This
    reads the interface library itself, so the stand-in is measured and
    not assumed.
    """
    import shiboken6
    from PySide6.QtWidgets import QWidget

    app()
    doomed = QWidget()
    shiboken6.delete(doomed)
    assert hasattr(doomed, surface.OPACITY_SETTER)
    with pytest.raises(RuntimeError):
        doomed.setWindowOpacity(0.9)
    live = QWidget()
    live.setWindowOpacity(0.9)
    assert type(live).__name__ == "QWidget"


def test_the_shipped_driver_reaches_a_real_widget_and_the_platform_rewrites_it():
    """The shipped driver never reaches a real widget at all.

    The read-back is not the request: the platform stores the opacity in
    eight bits. The request is what both sides are compared on, and it is
    pinned here rather than the number the platform hands back.
    """
    from PySide6.QtWidgets import QWidget
    from src.gui.widgets.pulse_manager import PulseManager

    app()
    manager = PulseManager()
    window = QWidget()
    manager.register(window)
    try:
        manager._tick()
    finally:
        manager._timer.stop()
    requested = surface.opacity_at(surface.PHASE_START + surface.PHASE_STEP)
    assert window.windowOpacity() != requested
    assert abs(window.windowOpacity() - requested) < 0.01
    assert requested == surface.opacity_at(surface.PHASE_STEP)


def test_a_real_widget_refuses_a_text_opacity_in_the_librarys_own_words():
    """A real widget takes text as an opacity.

    The wording is the interface library's. The surface's own widget
    stand-in takes whatever it is handed and cannot produce that wording,
    so the two are pinned apart rather than compared.
    """
    from PySide6.QtWidgets import QWidget

    app()
    window = QWidget()
    with pytest.raises(TypeError) as reported:
        window.setWindowOpacity("0.5")
    assert "setWindowOpacity" in refusal_headline(str(reported.value))
    taker = surface.OpacityTarget("plain")
    taker.setWindowOpacity("0.5")
    assert taker.opacities == ["0.5"]


# The clock is a value handed in


def test_the_elapsed_time_handed_in_decides_how_many_fires_run():
    """An elapsed time buys a different number of fires on the two sides."""
    for name, wanted in (
        ("zero_elapsed_time", 0),
        ("less_than_one_delay_of_elapsed_time", 0),
        ("one_delay_of_elapsed_time", 1),
        ("ten_delays_of_elapsed_time", 10),
        ("negative_elapsed_time", -10),
        ("one_billionth_of_elapsed_time", 0),
    ):
        old = old_outcome(BY_NAME[name])["value"]
        assert old["fires"] == [wanted], name
        assert new_outcome(BY_NAME[name])["value"]["fires"] == [wanted], name


def test_a_negative_elapsed_time_runs_no_fire_at_all():
    """A negative elapsed time ran fires, so time went backwards."""
    old = old_outcome(BY_NAME["negative_elapsed_time"])["value"]
    assert old["fires"] == [-10]
    assert old["seen"][0]["opacities"] == []
    assert old["phase"] == surface.PHASE_START
    assert new_outcome(BY_NAME["negative_elapsed_time"])["value"] == old
    model = surface.PulseModel()
    assert model.advance(-500) == -10
    assert model.phase == surface.PHASE_START


def test_no_drive_on_either_side_reads_a_clock():
    """A drive waits on real time, which makes the run answer differently.

    The same scenario is driven twice in a row and must answer the same.
    A drive keyed on the wall clock would answer differently the second
    time.
    """
    once = old_outcome(BY_NAME["the_whole_driver"])["value"]
    twice = old_outcome(BY_NAME["the_whole_driver"])["value"]
    assert digest(once) == digest(twice)
    assert digest(new_trace(BY_NAME["the_whole_driver"])) == digest(once)
    assert digest(new_trace(BY_NAME["the_whole_driver"])) == digest(
        new_trace(BY_NAME["the_whole_driver"])
    )


def test_the_shipped_timer_never_fires_on_its_own_inside_a_test():
    """The shipped timer fires by itself, so a drive counts unasked fires.

    A timer needs the interface library's own loop to fire, which no test
    here runs. The positive control is the same driver's ``_tick`` called
    by hand, which does move the phase.
    """
    from src.gui.widgets.pulse_manager import PulseManager

    app()
    manager = PulseManager()
    widget = make_widget("unasked", "records")
    manager.register(widget)
    try:
        assert manager._timer.isActive() is True
        assert widget.opacities == []
        assert manager._phase == 0.0
        manager._tick()
        assert len(widget.opacities) == 1
    finally:
        manager._timer.stop()


def test_the_surface_delay_is_the_delay_the_shipped_timer_runs_at():
    """The surface names a delay the shipped timer does not run at."""
    from src.gui.widgets.pulse_manager import PulseManager

    app()
    manager = PulseManager()
    try:
        assert manager._timer.interval() == surface.TIMER_INTERVAL_MS
        assert surface.TIMER_INTERVAL_MS == 50
        assert surface.TIMERS == {surface.TIMER_NAME: 50}
        assert surface.TIMER_DELAYS_MS == (50,)
    finally:
        manager._timer.stop()


def test_the_library_rewrites_an_odd_delay_and_the_surface_never_asks_for_one():
    """The delay read back is the delay asked for, whatever is asked.

    The shipped driver asks for fifty, which the library keeps. Other
    values it rewrites, so a read-back is pinned here as a fact about the
    library and never compared against the surface.
    """
    from PySide6.QtCore import QTimer

    app()
    timer = QTimer()
    try:
        timer.start(-1)
        assert timer.interval() == 1
        timer.start(50.7)
        assert timer.interval() == 50
        timer.start(50)
        assert timer.interval() == 50
    finally:
        timer.stop()


# Start and stop, in sequence


@pytest.mark.parametrize(
    "name,active",
    [
        ("one_widget_one_fire", True),
        ("start_when_already_started", True),
        ("start_twice_more", True),
        ("stop", False),
        ("stop_when_already_stopped", False),
        ("start_after_stop", True),
        ("stop_fire_then_start_again", True),
    ],
)
def test_the_timer_state_follows_start_and_stop_on_both_sides(name, active):
    """A start or a stop leaves the two sides in different states."""
    old = old_outcome(BY_NAME[name])["value"]
    new = new_outcome(BY_NAME[name])["value"]
    assert old["timer"]["active"] is active, name
    assert new["timer"]["active"] is active, name
    assert digest(old) == digest(new), name


def test_a_stopped_timer_does_not_stop_a_fire_driven_by_hand():
    """A fire is refused once the timer is stopped, on one side only."""
    stopped = old_outcome(BY_NAME["stop"])["value"]
    assert stopped["timer"]["active"] is False
    assert len(stopped["seen"][0]["opacities"]) == 1
    assert new_outcome(BY_NAME["stop"])["value"] == stopped


def test_the_start_and_stop_counts_are_kept_on_the_surface():
    """The surface loses count of the starts and stops it was asked for."""
    model = drive_new(BY_NAME["stop_fire_then_start_again"])[0]
    assert model.starts == 2
    assert model.stops == 1
    fresh = surface.PulseModel()
    assert fresh.starts == 1
    assert fresh.stops == 0
    assert fresh.timer_active is True
    payload = surface.build_view_model(model)
    assert payload["timer"]["starts"] == 2
    assert payload["timer"]["stops"] == 1


# The enumeration


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    found = []
    for node in ast.walk(parsed(path)):
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
    """Every ``QTimer(`` construction in `path`, never the import of the name."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path) -> list:
    """Every ``subscribe(`` site in `path`, as the topic it names."""
    found = []
    for node in ast.walk(parsed(path)):
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
    return sorted(
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and dotted(node.func).split(".")[-1] in WIDGET_NAMES
    )


def test_the_one_wiring_site_has_one_named_action_and_the_counter_can_report():
    """The driver wires a signal the surface names no action for."""
    sites = connect_sites(SHIPPED_SOURCE)
    assert sites == [("self._timer.timeout", "self._tick")], sites
    assert len(sites) == CONNECT_TOTAL
    assert surface.ACTIONS == {"opacity_pulse.timeout": "tick"}
    assert len(surface.ACTIONS) == CONNECT_TOTAL
    neighbour = connect_sites(CONNECT_NEIGHBOUR)
    assert neighbour == [("self.clicked", "self._on_click")], neighbour
    assert len(neighbour) == 1


def test_the_driver_builds_one_timer_and_the_counter_can_report():
    """The driver builds a timer the surface declares no delay for.

    This file is itself the positive control for the timer counter, so
    the counter is also pointed at a file that builds none and at the
    file that shares a name with the neighbour but builds none either.
    """
    built = timer_sites(SHIPPED_SOURCE)
    assert built == ["QTimer"], built
    assert len(built) == TIMER_TOTAL
    assert len(surface.TIMERS) == TIMER_TOTAL
    assert len(surface.TIMER_DELAYS_MS) == TIMER_TOTAL
    assert len(timer_sites(TIMER_NEIGHBOUR)) == 1
    assert timer_sites(TIMER_NAMESAKE) == []
    assert timer_sites(CONNECT_NEIGHBOUR) == []


def test_the_timer_counter_counts_the_construction_and_not_the_name():
    """The counter counts the word, so an import would read as a timer."""
    text = SHIPPED_SOURCE.read_text(encoding="utf-8")
    assert text.count("QTimer") == 3
    assert len(timer_sites(SHIPPED_SOURCE)) == 1
    assert TIMER_NAMESAKE.read_text(encoding="utf-8").count("QTimer") == 0


def test_the_driver_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The driver listens on a topic the surface names none of."""
    assert bus_sites(SHIPPED_SOURCE) == []
    assert len(bus_sites(SHIPPED_SOURCE)) == BUS_TOTAL
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) == 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


def test_the_driver_builds_no_interface_element_and_the_counter_can_report():
    """The driver builds something on screen the surface describes nothing of.

    This is what proves the file has no visible part of its own. The same
    counter is pointed at a file that really builds elements and reports
    three there.
    """
    assert widget_sites(SHIPPED_SOURCE) == []
    assert len(widget_sites(SHIPPED_SOURCE)) == WIDGET_TOTAL
    assert surface.WIDGETS == ()
    assert surface.PAINTS is False
    neighbour = widget_sites(WIDGET_NEIGHBOUR)
    assert len(neighbour) == 3, "the element counter reports nothing"
    assert "QLabel" in neighbour


def test_nothing_either_side_answers_is_something_that_can_be_painted():
    """A side hands back something with a picture, which a render would need."""
    from src.gui.widgets.pulse_manager import PulseManager

    app()
    manager = PulseManager()
    try:
        assert manager.register(make_widget("a", "records")) is None
        assert manager._tick() is None
    finally:
        manager._timer.stop()
    model = surface.PulseModel()
    assert model.register(surface.OpacityTarget("a")) is None
    assert model.tick() is None
    assert model.start() is None
    assert model.stop() is None
    for value in surface.build_view_model(model).values():
        assert isinstance(value, PLAIN_TYPES), value


SHIPPED_METHODS = {
    "__init__": "PulseModel.__init__",
    "register": "PulseModel.register",
    "_tick": "PulseModel.tick",
}

# Names the surface holds that the shipped driver gets from the interface
# library rather than declaring, each with the shipped thing it stands for.
EXTRA_MODEL_METHODS = {
    "start": "the timer's own start, which __init__ calls with the delay",
    "stop": "the timer's own stop",
    "ticks_for": "how many times a timer at that delay fires in an elapsed time",
    "advance": "the timer firing over an elapsed time handed in",
}
EXTRA_SURFACE_FUNCTIONS = {
    "opacity_at": "the arithmetic _tick runs inline on every fire",
    "seen_by_targets": "what each registered widget received",
    "build_view_model": "the whole state as one dict for the renderer",
    "view_model": "the bridge handler",
    "runs_in": "how many runs one window of milliseconds covers",
    "as_count": "the count a request carries, refused when it is not a number",
    "as_targets": "the widgets a request names, refused when it is not a list",
    "runs_asked": "how many runs a request asks for, refused above the cap",
}
EXTRA_SURFACE_CLASSES = {
    "OpacityTarget": "the widget the shipped driver is handed",
}


def shipped_methods() -> list:
    """Every method the shipped class declares, read off the class.

    A signal is callable and is not a method, so the reader excludes by
    type rather than by whether a name can be called.
    """
    from PySide6.QtCore import Signal

    from src.gui.widgets.pulse_manager import PulseManager

    return sorted(
        name
        for name, value in vars(PulseManager).items()
        if callable(value) and not isinstance(value, Signal)
    )


def test_every_shipped_method_has_a_counterpart():
    """The shipped driver gained or lost a method."""
    found = shipped_methods()
    assert found == sorted(SHIPPED_METHODS), found
    assert len(found) == SHIPPED_METHOD_TOTAL
    for counterpart in SHIPPED_METHODS.values():
        holder, _, attribute = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), attribute)), counterpart


def test_the_shipped_module_declares_one_class_and_no_signal():
    """The shipped module declares a class or a signal nothing stands for."""
    from PySide6.QtCore import Signal

    from src.gui.widgets import pulse_manager as shipped

    classes = sorted(
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    )
    assert classes == ["PulseManager"], classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    signals = [
        name
        for name, value in vars(shipped.PulseManager).items()
        if isinstance(value, Signal)
    ]
    assert signals == [], signals
    assert len(signals) == SHIPPED_SIGNAL_TOTAL
    assert surface.SIGNALS == ()


def test_the_method_reader_counts_no_signal_as_a_method():
    """A signal is callable, so the counter would report one too many.

    The shipped class declares none, so the reader is pointed at a class
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
    assert len(counted) >= 1, "the method counter reports nothing"


def test_every_surface_class_and_extra_name_stands_for_something_shipped():
    """The surface grew a class, a method or a function for nothing."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(["PulseModel"] + list(EXTRA_SURFACE_CLASSES)), built
    named = {counterpart.partition(".")[2] for counterpart in SHIPPED_METHODS.values()}
    named |= set(EXTRA_MODEL_METHODS)
    mine = {
        name
        for name, value in vars(surface.PulseModel).items()
        if callable(value) and not name.startswith("__")
    }
    assert mine == named - {"__init__"}, sorted(mine ^ (named - {"__init__"}))
    functions = {
        name
        for name, value in vars(surface).items()
        if callable(value)
        and not isinstance(value, type)
        and getattr(value, "__module__", None) == surface.__name__
    }
    assert functions == set(EXTRA_SURFACE_FUNCTIONS), sorted(functions)


# The completeness check


def named_payloads() -> dict:
    """The payloads the completeness check reads."""
    return {
        name: surface.build_view_model(drive_new(BY_NAME[name])[0])
        for name in (
            "one_widget_one_fire",
            "stop",
            "a_widget_with_no_opacity_setter",
            "a_widget_whose_object_is_gone",
            "the_whole_driver",
        )
    }


BUILT = "one_widget_one_fire"

PAYLOAD_KEYS = {
    "METHOD": f"{BUILT}:method",
    "PULSE_CSS": f"{BUILT}:css",
    "STYLE_SHEET_APPLIED": f"{BUILT}:style_sheet_applied",
    "TIMER_NAME": f"{BUILT}:timer.name",
    "TIMER_INTERVAL_MS": f"{BUILT}:timer.interval_ms",
    "TIMERS": f"{BUILT}:timers",
    "TIMER_DELAYS_MS": f"{BUILT}:timer_delays_ms",
    "ACTIONS": f"{BUILT}:actions",
    "SIGNALS": f"{BUILT}:signals",
    "BUS_TOPICS": f"{BUILT}:bus_topics",
    "WIDGETS": f"{BUILT}:widgets",
    "PAINTS": f"{BUILT}:paints",
    "PHASE_START": f"{BUILT}:phase_start",
    "PHASE_STEP": f"{BUILT}:phase_step",
    "OPACITY_MID": f"{BUILT}:opacity_mid",
    "OPACITY_SWING": f"{BUILT}:opacity_swing",
    "OPACITY_FLOOR": f"{BUILT}:opacity_floor",
    "OPACITY_CEILING": f"{BUILT}:opacity_ceiling",
    "OPACITY_SETTER": f"{BUILT}:setter",
    "SWALLOWED_ERROR": f"{BUILT}:swallows",
    "RUN_CAP": f"{BUILT}:run_cap",
    "CALL_NAMES": f"{BUILT}:call_names",
}

# The nine branch markers, each carried inside the calls one drive left.
CALL_CONSTANTS = {
    "TIMER_STARTED": BUILT,
    "TIMER_STOPPED": "stop",
    "TARGET_REGISTERED": BUILT,
    "PHASE_ADVANCED": BUILT,
    "OPACITY_COMPUTED": BUILT,
    "TARGET_HAS_SETTER": BUILT,
    "TARGET_SET": BUILT,
    "TARGET_SKIPPED": "a_widget_with_no_opacity_setter",
    "TARGET_FAILED": "a_widget_whose_object_is_gone",
}

# Snapshot keys built from what a drive did rather than carrying a value.
DERIVED_KEYS = {
    "phase": "test_the_two_sides_run_the_same_pulse",
    "registered": "test_the_two_sides_run_the_same_pulse",
    "seen": "test_the_two_sides_run_the_same_pulse",
    "timer": "test_the_timer_state_follows_start_and_stop_on_both_sides",
    "applied": "test_a_widget_whose_object_is_gone_is_passed_over_and_the_rest_still_run",
    "skipped": "test_a_widget_with_no_setter_is_passed_over_and_the_rest_still_run",
    "failed": "test_a_widget_whose_object_is_gone_is_passed_over_and_the_rest_still_run",
    "calls": "test_every_branch_marker_fires_on_a_drive_of_the_surface",
}

# Snapshot keys no side-by-side reading covers, each with its own check.
OUTSIDE_THE_QT_TRACE = {
    "css": "test_the_surface_carries_the_shipped_stylesheet_text",
    "style_sheet_applied": "test_the_shipped_stylesheet_is_read_by_nothing_that_imports_it",
    "phase_start": "test_both_sides_start_at_the_same_phase",
    "phase_step": "test_the_first_fire_hands_out_the_opacity_the_shipped_driver_computes",
    "opacity_mid": "test_the_opacity_the_surface_computes_is_the_published_sine_wave",
    "opacity_swing": "test_the_opacity_the_surface_computes_is_the_published_sine_wave",
    "opacity_floor": "test_the_floor_and_the_ceiling_are_the_midpoint_either_side_of_the_swing",
    "opacity_ceiling": "test_the_floor_and_the_ceiling_are_the_midpoint_either_side_of_the_swing",
    "setter": "test_a_real_deleted_widget_raises_the_error_the_driver_swallows",
    "swallows": "test_a_widget_that_refuses_with_another_error_ends_the_fire_on_both_sides",
    "run_cap": "test_the_cap_is_one_minute_of_the_delay_the_timer_runs_at",
    "applied": "test_a_widget_with_no_setter_is_passed_over_and_the_rest_still_run",
    "skipped": "test_a_widget_with_no_setter_is_passed_over_and_the_rest_still_run",
    "failed": "test_a_widget_whose_object_is_gone_is_passed_over_and_the_rest_still_run",
    "paints": "test_the_driver_builds_no_interface_element_and_the_counter_can_report",
    "widgets": "test_the_driver_builds_no_interface_element_and_the_counter_can_report",
    "signals": "test_the_shipped_module_declares_one_class_and_no_signal",
    "actions": "test_the_one_wiring_site_has_one_named_action_and_the_counter_can_report",
    "timers": "test_the_driver_builds_one_timer_and_the_counter_can_report",
    "timer_delays_ms": "test_the_driver_builds_one_timer_and_the_counter_can_report",
    "bus_topics": "test_the_driver_subscribes_to_no_bus_topic_and_the_counter_can_report",
    "call_names": "test_every_branch_marker_fires_on_a_drive_of_the_surface",
    "calls": "test_every_branch_marker_fires_on_a_drive_of_the_surface",
    "method": "test_the_bridge_registers_the_pulse_method",
}

# Reading keys the driver builds that no snapshot key carries.
DRIVER_KEYS = {
    "phase_before": "test_a_whole_number_phase_and_the_same_decimal_are_told_apart",
    "fires": "test_the_elapsed_time_handed_in_decides_how_many_fires_run",
}


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
        elif name in CALL_CONSTANTS:
            assert value in payloads[CALL_CONSTANTS[name]]["calls"], name
        else:
            unaccounted.append(name)
    return unaccounted


def unbacked_keys(built) -> set:
    """The snapshot keys no exported value and no named check backs."""
    answered = {path.partition(":")[2].split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered.add("calls")
    return set(built) ^ (answered | set(DERIVED_KEYS))


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read."""
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    found = unaccounted_constants(named_payloads(), constants)
    assert found == [], found
    assert len(PAYLOAD_KEYS) == 22
    assert len(CALL_CONSTANTS) == CALL_NAME_TOTAL
    assert len(CALL_CONSTANTS) == len(surface.CALL_NAMES)


def test_no_exported_name_slips_past_the_value_reader():
    """A value of an unexpected type is read by nothing at all."""
    import types

    everything = {
        name
        for name, value in vars(surface).items()
        if not name.startswith("__") and not isinstance(value, types.ModuleType)
    }
    functions = {
        name
        for name, value in vars(surface).items()
        if callable(value) and getattr(value, "__module__", None) == surface.__name__
    }
    leftover = everything - functions - set(surface_constants())
    assert leftover == {"annotations"}, sorted(leftover)


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
    assert len(compared) == TRACE_KEY_TOTAL
    assert compared - set(DRIVER_KEYS) == set(built) - set(OUTSIDE_THE_QT_TRACE)
    for key, covered_by in OUTSIDE_THE_QT_TRACE.items():
        assert key in built, key
        assert callable(globals()[covered_by]), (key, covered_by)
    for key, covered_by in DRIVER_KEYS.items():
        assert key in compared, key
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
    shrunk = {key: value for key, value in payloads[BUILT].items() if key != "timer"}
    assert unbacked_keys(shrunk) == {"timer"}
    assert "build_view_model" not in surface_constants()
    assert "PulseModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payloads, f"{BUILT}:timer.invented")


def test_every_branch_marker_fires_on_a_drive_of_the_surface():
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
    quiet = drive_new(BY_NAME["no_widget_registered"])[0]
    assert surface.PHASE_ADVANCED in quiet.calls
    assert surface.TARGET_SET not in quiet.calls
    assert len(surface.CALL_NAMES) == len(set(surface.CALL_NAMES))


def test_both_sides_start_at_the_same_phase():
    """The two sides start the phase at different numbers."""
    from src.gui.widgets.pulse_manager import PulseManager

    app()
    manager = PulseManager()
    try:
        assert manager._phase == surface.PHASE_START
        assert manager._phase == 0.0
    finally:
        manager._timer.stop()
    assert surface.PulseModel().phase == surface.PHASE_START
    assert surface.PulseModel().phase_start == surface.PHASE_START


def test_the_surface_carries_the_shipped_stylesheet_text():
    """The surface carries a different stylesheet than the shipped driver."""
    from src.gui.widgets.pulse_manager import PULSE_CSS

    assert surface.PULSE_CSS == PULSE_CSS
    assert len(surface.PULSE_CSS) == 285
    assert surface.PULSE_CSS.count("\r") == 0
    assert "@keyframes pulse" in surface.PULSE_CSS
    assert 'QPushButton[accent="true"]' in surface.PULSE_CSS
    assert "animation: pulse 2s ease-in-out infinite;" in surface.PULSE_CSS


def importers_of(name) -> list:
    """Every file under ``src`` that imports `name` from the shipped module.

    The new surface writes out its own copy of the stylesheet and never
    imports the shipped one, so counting it as a reader would make this
    reading go green on the conversion itself.
    """
    found = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path.name == "pulse_manager_surface.py":
            continue
        for node in ast.walk(parsed(path)):
            if isinstance(node, ast.ImportFrom) and "pulse_manager" in (
                node.module or ""
            ):
                if any(alias.name == name for alias in node.names):
                    found.append(path)
    return found


def loaded_names(path) -> list:
    """Every name `path` reads, which an import binding alone is not."""
    return [
        node.id
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    ]


def test_the_shipped_stylesheet_is_read_by_nothing_that_imports_it():
    """The stylesheet is read somewhere, so the surface says the wrong thing.

    One file imports the text and one imports the driver. Neither reads
    either name again, so no widget is ever given this stylesheet and no
    driver is ever built. The counter is pointed at a name in the same
    file that IS read, so a zero here is not a zero everywhere.
    """
    for name in ("PULSE_CSS", "PulseManager"):
        importers = importers_of(name)
        assert [path.name for path in importers] == ["main_window.py"], name
        for path in importers:
            assert name not in loaded_names(path), (name, path.name)
            assert "MainWindow" in loaded_names(
                path
            ), "the name counter reports nothing"
    assert surface.STYLE_SHEET_APPLIED is False


def test_the_reading_reports_two_widgets_registered_in_the_other_order():
    """A swap of two registered widgets reads the same, so order is unchecked."""
    forwards = scenario("forwards", [reg("first"), reg("second", "no_setter"), TICK])
    backwards = scenario("backwards", [reg("second", "no_setter"), reg("first"), TICK])
    one = drive_old(forwards)
    other = drive_old(backwards)
    assert [entry["target"] for entry in one["seen"]] == ["first", "second"]
    assert [entry["target"] for entry in other["seen"]] == ["second", "first"]
    assert digest(one) != digest(other)
    assert digest(new_trace(forwards)) == digest(one)
    assert digest(new_trace(backwards)) == digest(other)


# The surface carries its own values


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_driver(monkeypatch):
    """The surface read its values off the driver it replaces.

    A surface that read the shipped module would follow it, and the whole
    comparison above would be one side read twice. The stylesheet text is
    moved in the shipped module, and the surface must not move with it.
    """
    from src.gui.widgets import pulse_manager as shipped

    before = shipped.PULSE_CSS
    assert surface.PULSE_CSS == before

    app()
    reading = old_outcome(BY_NAME["one_widget_one_fire"])["value"]
    moved = "MOVED STYLESHEET { opacity: 0.1; }"
    monkeypatch.setattr(shipped, "PULSE_CSS", moved)
    assert shipped.PULSE_CSS == moved
    assert surface.PULSE_CSS != moved
    assert surface.PULSE_CSS == before

    after = old_outcome(BY_NAME["one_widget_one_fire"])["value"]
    difference = [
        key for key in reading if canonical(reading[key]) != canonical(after[key])
    ]
    assert difference == [], difference
    monkeypatch.undo()
    assert shipped.PULSE_CSS == before


def test_the_surface_does_not_follow_a_step_moved_in_the_shipped_driver(monkeypatch):
    """The surface read the phase step off the driver it replaces."""
    from src.gui.widgets import pulse_manager as shipped

    app()
    before = old_outcome(BY_NAME["one_widget_three_fires"])["value"]
    held = shipped.PulseManager._tick

    def with_a_bigger_step(self):
        self._phase += 0.5
        for widget in self._widgets:
            widget.setWindowOpacity(surface.opacity_at(self._phase))

    monkeypatch.setattr(shipped.PulseManager, "_tick", with_a_bigger_step)
    after = old_outcome(BY_NAME["one_widget_three_fires"])["value"]
    assert after["phase"] != before["phase"]
    assert digest(after) != digest(before)
    difference = [
        key for key in before if canonical(before[key]) != canonical(after[key])
    ]
    assert difference == ["phase", "seen"], difference

    mine = new_outcome(BY_NAME["one_widget_three_fires"])["value"]
    assert digest(mine) == digest(before)
    assert surface.PHASE_STEP == 0.05
    monkeypatch.undo()
    assert shipped.PulseManager._tick is held
    assert digest(old_outcome(BY_NAME["one_widget_three_fires"])["value"]) == digest(
        before
    )


def test_the_surface_does_not_follow_a_driver_that_hands_out_nothing(monkeypatch):
    """The surface asked the shipped driver for its numbers."""
    from src.gui.widgets import pulse_manager as shipped

    before = new_outcome(BY_NAME["one_widget_one_fire"])["value"]
    monkeypatch.setattr(shipped.PulseManager, "_tick", lambda self: None)
    app()
    quiet = shipped.PulseManager()
    widget = make_widget("nothing at all", "records")
    quiet.register(widget)
    try:
        quiet._tick()
        assert widget.opacities == []
    finally:
        quiet._timer.stop()
    assert new_outcome(BY_NAME["one_widget_one_fire"])["value"] == before
    monkeypatch.undo()


def test_the_shipped_module_holds_no_shared_container():
    """The module writes a shared table a later test would read.

    Every list the driver holds is on the instance, so two drives in one
    process cannot reach each other's widgets.
    """
    from src.gui.widgets import pulse_manager as shipped

    containers = sorted(
        name
        for name, value in vars(shipped).items()
        if not name.startswith("__") and isinstance(value, (list, dict, set))
    )
    assert containers == [], containers
    app()
    first = shipped.PulseManager()
    second = shipped.PulseManager()
    try:
        first.register(make_widget("only first", "records"))
        assert second._widgets == []
        assert first._widgets is not second._widgets
    finally:
        first._timer.stop()
        second._timer.stop()
    mine = sorted(
        name
        for name, value in vars(surface).items()
        if not name.startswith("__") and isinstance(value, (list, dict, set))
    )
    assert mine, "the container counter reports nothing"


def test_no_value_either_side_answers_can_be_moved_by_a_font():
    """A value in either reading is a picture, which the host's fonts move.

    The font state is read through the shared helper after this run has
    applied its font choice, and the two sides must agree in either state.
    """
    from tests.fixtures.host_fonts import has_real_fonts, load_run_fonts

    app()
    load_run_fonts()
    state = has_real_fonts()
    old = old_outcome(BY_NAME["the_whole_driver"])["value"]
    new = new_outcome(BY_NAME["the_whole_driver"])["value"]
    assert digest(old) == digest(new), state
    for value in surface.build_view_model(drive_new(BY_NAME[BUILT])[0]).values():
        assert isinstance(value, PLAIN_TYPES), (value, state)


# The bridge


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_pulse_method():
    """The renderer cannot reach the pulse driver over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "pulse_manager.state"
    answer = bridge_answer({})
    assert answer["ok"] is True
    assert answer["result"]["method"] == surface.METHOD
    assert answer["result"]["timer"]["interval_ms"] == 50


def test_the_bridge_runs_the_fires_a_request_asks_for():
    """The bridge ignored the widgets, the fires or the stop a request named."""
    two = bridge_answer({"targets": ["a", "b"], "ticks": 2})["result"]
    assert two["registered"] == 2
    assert [entry["target"] for entry in two["seen"]] == ["a", "b"]
    assert len(two["seen"][0]["opacities"]) == 2
    elapsed = bridge_answer({"targets": ["a"], "elapsed_ms": 500})["result"]
    assert len(elapsed["seen"][0]["opacities"]) == 10
    stopped = bridge_answer({"stop": True})["result"]
    assert stopped["timer"]["active"] is False
    assert stopped["timer"]["stops"] == 1


def test_the_bridge_reports_a_request_the_surface_cannot_run():
    """A request the surface refuses came back as an answer."""
    answer = bridge_answer({"ticks": "three"})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "TypeError"
    looks_like_a_number = bridge_answer({"ticks": "3"})
    assert looks_like_a_number["ok"] is False
    assert looks_like_a_number["error"]["type"] == "TypeError"
    bad_time = bridge_answer({"elapsed_ms": "later"})
    assert bad_time["ok"] is False
    assert bad_time["error"]["type"] == "TypeError"
    assert bridge_answer({"ticks": 3})["ok"] is True


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"targets": ["accent"], "ticks": 1})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["css"] == surface.PULSE_CSS
    assert encoded["result"]["seen"][0]["target"] == "accent"


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'pulse_manager.state', 'params':"
    " {'targets': ['accent button'], 'ticks': 2}}),"
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
    """Reaching the pulse driver pulled the interface library into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["registered"] == 1
    assert len(result["seen"][0]["opacities"]) == 2
    assert result["seen"][0]["target"] == "accent button"


def test_the_qt_probe_can_report_qt():
    """The probe reports the library absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


class WidgetWhoseSetterIsNothing:
    """A registered object whose opacity setter answers as nothing at all."""

    setWindowOpacity = None

    def __init__(self, name) -> None:
        self.name = name
        self.opacities: list = []


def test_a_widget_whose_setter_is_nothing_is_passed_over_on_both_sides():
    """One side stopped the whole pulse where the other passed the widget over."""
    app()
    from src.gui.widgets.pulse_manager import PulseManager

    shipped = PulseManager()
    shipped._timer.stop()
    shipped.register(WidgetWhoseSetterIsNothing("no setter of its own"))
    shipped.register(RecordingWidget("after it"))
    shipped._tick()
    assert shipped._widgets[1].opacities == [
        surface.opacity_at(surface.PHASE_START + surface.PHASE_STEP)
    ], shipped._widgets[1].opacities

    model = surface.PulseModel()
    model.stop()
    model.register(WidgetWhoseSetterIsNothing("no setter of its own"))
    model.register(RecordingWidget("after it"))
    model.tick()
    assert model.skipped == [0], model.skipped
    assert len(model.applied) == 1, model.applied

    healthy = PulseManager()
    healthy._timer.stop()
    healthy.register(RecordingWidget("takes the value"))
    healthy._tick()
    assert len(healthy._widgets[0].opacities) == 1, healthy._widgets[0].opacities


def test_a_request_naming_its_targets_as_text_is_refused():
    """Text where a list of widgets belongs was read one letter per widget."""
    with pytest.raises(TypeError) as refused:
        surface.view_model({"targets": "BTC"})
    assert "targets" in str(refused.value), str(refused.value)
    with pytest.raises(TypeError):
        surface.view_model({"targets": {"a": 1, "b": 2}})
    answered = surface.view_model({"targets": ["BTC"]})
    assert answered["registered"] == 1
    assert [one["target"] for one in answered["seen"]] == ["BTC"]


def test_a_count_written_as_text_is_refused_rather_than_read_as_a_number():
    """Text that looks like a number was read as that many ticks."""
    for asked in ({"ticks": "3"}, {"ticks": "three"}, {"ticks": True}):
        with pytest.raises(TypeError):
            surface.view_model(asked)
    with pytest.raises(TypeError):
        surface.view_model({"elapsed_ms": "500"})
    answered = surface.view_model({"targets": ["a"], "ticks": 3})
    assert len(answered["seen"][0]["opacities"]) == 3


def test_a_request_asking_for_more_runs_than_a_minute_of_the_timer_is_refused():
    """A request asked for more runs than any caller can wait for."""
    for asked in ({"ticks": 10**24}, {"elapsed_ms": 10**24}):
        with pytest.raises(ValueError) as refused:
            surface.view_model(asked)
        assert str(surface.RUN_CAP) in str(refused.value), str(refused.value)
    at_the_cap = surface.view_model({"ticks": surface.RUN_CAP})
    assert at_the_cap["phase"] == pytest.approx(
        surface.PHASE_START + surface.RUN_CAP * surface.PHASE_STEP
    )
    assert at_the_cap["run_cap"] == surface.RUN_CAP


def test_the_cap_is_one_minute_of_the_delay_the_timer_runs_at():
    """The cap stopped naming the delay it is counted in."""
    assert surface.RUN_CAP * surface.TIMER_INTERVAL_MS == 60_000
    assert surface.view_model({})["run_cap"] == surface.RUN_CAP
