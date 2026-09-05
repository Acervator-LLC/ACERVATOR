"""The Qt splash screen and the Qt-free surface, side by side.

A failure means the view model describes a different phase, a different
time in a phase, a different colour, gradient stop, opacity, font,
rectangle, text or timer than the ``SplashScreen`` class declared inside
``main.main`` produces on the same elapsed time and the same window size.

The shipped class is declared inside a function body, so it cannot be
imported. It is rebuilt from the compiled code object ``main.main``
carries, with its seven free names bound to recorders. Every shipped
statement runs; only the painter it draws into is watched.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

import main
from src.gui.main_tabs import splash_screen_surface as surface
from tests.fixtures.host_fonts import (
    has_real_fonts,
    load_run_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_pictures_match,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

PIXEL_SIZE = (400, 400)

SHIPPED_METHOD_TOTAL = 5
SHIPPED_FREE_NAME_TOTAL = 7
ENTRY_THREAD_TOTAL = 0
SPLASH_CONNECT_TOTAL = 1
PAYLOAD_KEY_TOTAL = 24
CONSTANT_TOTAL = 132
TRACE_KEY_TOTAL = 8

TICK_S = 0.025


# Rebuilding the shipped class out of main's compiled code

SPLASH_BODY = next(
    const
    for const in main.main.__code__.co_consts
    if hasattr(const, "co_name") and const.co_name == "SplashScreen"
)

SHIPPED_METHOD_CODE = {
    const.co_name: const for const in SPLASH_BODY.co_consts if hasattr(const, "co_name")
}


def a_cell(value):
    """A closure cell holding `value`, for a free name of the class body."""
    return (lambda held: lambda: held)(value).__closure__[0]


def build_shipped(names: dict, base):
    """The shipped SplashScreen, with its free names bound to `names`."""
    cells = tuple(a_cell(names[free]) for free in SPLASH_BODY.co_freevars)
    body = types.FunctionType(
        SPLASH_BODY, dict(main.__dict__), "SplashScreen", None, cells
    )
    return __build_class__(body, "SplashScreen", base)


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    ensure_app()
    load_run_fonts()
    return ensure_app()


# The recorders. Each keeps the values it was BUILT with, so a value the
# platform clamps is still compared as the splash computed it.


def recorder_names():
    """The stand-ins the shipped class paints into, plus the real Qt names."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter

    align = {int(Qt.AlignCenter.value): surface.ALIGN_CENTRE}
    pen_styles = {int(Qt.NoPen.value): surface.NO_PEN}
    brush_styles = {int(Qt.NoBrush.value): surface.NO_BRUSH}
    weights = {int(QFont.Bold.value): surface.BOLD}

    class Colour(QColor):
        def __init__(self, *given):
            super().__init__(*given)
            self.given = list(given)

    class Rect(QRectF):
        def __init__(self, *given):
            super().__init__(*given)
            self.given = list(given)

    class Font(QFont):
        def __init__(self, *given):
            super().__init__(*given)
            self.given = ["font", given[0], given[1]]
            if len(given) > 2:
                self.given.append(weights[int(given[2].value)])

    class Gradient(QLinearGradient):
        def __init__(self, *given):
            super().__init__(*given)
            self.start_given = [given[0], given[1]]
            self.finish_given = [given[2], given[3]]
            self.stops_given: list = []

        def setColorAt(self, at, colour):
            self.stops_given.append([at, list(colour.given)])
            super().setColorAt(at, colour)

    class Pen(QPen_real()):
        def __init__(self, colour):
            super().__init__(colour)
            self.colour_given = list(colour.given)
            self.width_given = None

        def setColor(self, colour):
            self.colour_given = list(colour.given)
            super().setColor(colour)

        def setWidthF(self, width):
            self.width_given = width
            super().setWidthF(width)

    class Painter:
        """Records every call the shipped paintEvent makes, in order."""

        Antialiasing = QPainter.Antialiasing
        ops: list = []

        def __init__(self, device):
            if not isinstance(device, QWidget_real()):
                raise AssertionError(
                    "the recording painter was given "
                    f"{type(device).__name__}, not the splash it paints"
                )

        def setRenderHint(self, hint):
            if hint is not Painter.Antialiasing:
                raise AssertionError(f"unrecorded render hint {hint!r}")
            Painter.ops.append(["render_hint", surface.ANTIALIASING])

        def setPen(self, value):
            if isinstance(value, Pen):
                Painter.ops.append(["pen", list(value.colour_given), value.width_given])
            elif isinstance(value, Colour):
                Painter.ops.append(["pen_colour", list(value.given)])
            else:
                Painter.ops.append(["pen_style", pen_styles[int(value.value)]])

        def setBrush(self, value):
            if isinstance(value, Colour):
                Painter.ops.append(["brush_colour", list(value.given)])
            else:
                Painter.ops.append(["brush_style", brush_styles[int(value.value)]])

        def setFont(self, value):
            Painter.ops.append(list(value.given))

        def fillRect(self, x, y, width, height, gradient):
            Painter.ops.append(
                [
                    "fill_rect",
                    x,
                    y,
                    width,
                    height,
                    [
                        "gradient",
                        list(gradient.start_given),
                        list(gradient.finish_given),
                        [list(stop) for stop in gradient.stops_given],
                    ],
                ]
            )

        def drawLine(self, x1, y1, x2, y2):
            Painter.ops.append(["line", x1, y1, x2, y2])

        def drawEllipse(self, rect):
            Painter.ops.append(["ellipse", list(rect.given)])

        def drawText(self, rect, alignment, text):
            Painter.ops.append(
                ["text", list(rect.given), align[int(alignment.value)], text]
            )

        def save(self):
            Painter.ops.append(["save"])

        def restore(self):
            Painter.ops.append(["restore"])

        def translate(self, x, y):
            Painter.ops.append(["translate", x, y])

        def rotate(self, angle):
            Painter.ops.append(["rotate", angle])

        def end(self):
            Painter.ops.append(["end"])

    return Colour, Rect, Font, Gradient, Pen, Painter


def QPen_real():
    from PySide6.QtGui import QPen

    return QPen


def QWidget_real():
    from PySide6.QtWidgets import QWidget

    return QWidget


def watched_timer():
    """A stand-in for QTimer that records the delayed callbacks scheduled.

    Not a QTimer subclass: building one returns a real QTimer, so the
    splash gets the timer it asks for, and ``singleShot`` is this class's
    own name rather than an override of the platform's.
    """
    from PySide6.QtCore import QTimer

    class WatchedTimer:
        scheduled: list = []

        def __new__(cls, parent=None):
            if cls is not WatchedTimer:
                raise AssertionError("the timer stand-in was subclassed")
            return QTimer(parent)

        @staticmethod
        def singleShot(delay_ms, callback):
            if not callable(callback):
                raise AssertionError(
                    f"the splash scheduled {callback!r}, which cannot be called"
                )
            WatchedTimer.scheduled.append(delay_ms)

    return WatchedTimer


def watched_widget():
    """A QWidget that records the close the splash performs on itself."""
    from PySide6.QtWidgets import QWidget

    class WatchedWidget(QWidget):
        """A window that counts the closes performed on it."""

        def __init__(self, parent=None):
            QWidget.__init__(self, parent)
            self.setAccessibleName("Splash Parity Window")
            self.closes = 0

        def close(self):
            self.closes += 1
            return QWidget.close(self)

    return WatchedWidget


class SwappedQPen:
    """Bind PySide6.QtGui.QPen to the recorder for one drive, then put it back.

    ``paintEvent`` imports QPen inside its own body, so the name cannot be
    reached through a closure cell. The module attribute is the only seam,
    and it is process-wide, so it is put back even when the drive refuses.
    """

    def __init__(self, replacement):
        self.replacement = replacement
        self.original = None

    def __enter__(self):
        import PySide6.QtGui as qtgui

        self.original = qtgui.QPen
        qtgui.QPen = self.replacement
        return self

    def swapped(self) -> bool:
        import PySide6.QtGui as qtgui

        return qtgui.QPen is self.replacement

    def __exit__(self, *_unused):
        import PySide6.QtGui as qtgui

        qtgui.QPen = self.original
        return False


class SwappedVersion:
    """Bind ``src.__version__`` for one drive, then put it back."""

    def __init__(self, version):
        self.version = version
        self.original = None

    def __enter__(self):
        import src

        self.original = src.__version__
        if self.version is not None:
            src.__version__ = self.version
        return self

    def __exit__(self, *_unused):
        import src

        src.__version__ = self.original
        return False


# The two sides

LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê 3.25.8 交易 \U0001f680"
NEWLINE_TEXT = "3.25\n8"
APOSTROPHE_TEXT = "Ekthelius' build"
WRONG_CAPITALS_TEXT = "V3.25.8-DEV"


def shipped_tick_marks() -> dict:
    """The tick at which the SHIPPED splash first reaches each phase.

    Taken by driving the shipped class rather than by multiplying the
    interval: 0.025 added 80 times falls short of 2.0, so an arithmetic
    guess names the wrong tick.
    """
    from PySide6.QtCore import Qt

    app()
    colour, rect, font, gradient, _pen, painter = recorder_names()
    base = watched_widget()
    built = build_shipped(
        {
            "QColor": colour,
            "QFont": font,
            "QLinearGradient": gradient,
            "QPainter": painter,
            "QRectF": rect,
            "QTimer": watched_timer(),
            "Qt": Qt,
        },
        base,
    )
    target = base()
    splash = built(target)
    splash._on_finished_callback = lambda: None
    marks: dict = {}
    try:
        for step in range(1, 1000):
            before = splash._phase
            splash._tick()
            if splash._phase != before:
                marks[splash._phase] = step
            if splash.closes:
                marks["close"] = step
                break
    finally:
        splash._timer.stop()
        splash.setParent(None)
        splash.deleteLater()
        target.deleteLater()
    return marks


SHIPPED_TICK_MARKS = shipped_tick_marks()
TICKS_TO_GLOW = SHIPPED_TICK_MARKS[surface.GLOW]
TICKS_TO_FADEOUT = SHIPPED_TICK_MARKS[surface.FADEOUT]
TICKS_TO_CLOSE = SHIPPED_TICK_MARKS["close"]


def scenario(
    name,
    elapsed_s=3.0,
    width=400,
    height=400,
    version=None,
    steps=(),
    screen=True,
    target=(0, 0, 400, 300),
    handoff=True,
):
    return {
        "name": name,
        "elapsed_s": elapsed_s,
        "width": width,
        "height": height,
        "version": version,
        "steps": tuple(steps),
        "screen": screen,
        "target": target,
        "handoff": handoff,
    }


SCENARIOS = [
    scenario("fadein_start", elapsed_s=0.0),
    scenario("fadein_middle", elapsed_s=1.0),
    scenario("fadein_end", elapsed_s=1.999),
    scenario("glow_start", elapsed_s=2.0),
    scenario("glow_middle", elapsed_s=4.0),
    scenario("glow_end", elapsed_s=5.999),
    scenario("fadeout_start", elapsed_s=6.0),
    scenario("fadeout_middle", elapsed_s=7.25),
    scenario("fadeout_end", elapsed_s=8.5),
    scenario("one_step_past_the_end", elapsed_s=8.525),
    scenario("a_second_past_the_end", elapsed_s=9.5),
    scenario("the_master_fade_is_over", elapsed_s=8.6),
    scenario("the_hint_appears", elapsed_s=3.0),
    scenario("just_before_the_hint", elapsed_s=2.999),
    scenario("a_negative_elapsed_time", elapsed_s=-1.0),
    scenario("zero_elapsed_time", elapsed_s=0),
    scenario("a_whole_number_of_seconds", elapsed_s=4),
    scenario("a_decimal_number_of_seconds", elapsed_s=4.0),
    scenario("not_a_number_of_seconds", elapsed_s=math.nan),
    scenario("infinite_seconds", elapsed_s=math.inf),
    scenario("minus_infinite_seconds", elapsed_s=-math.inf),
    scenario("a_thousand_million_seconds", elapsed_s=1_000_000_000),
    scenario("one_billionth_of_a_second", elapsed_s=1e-9),
    scenario("a_flag_where_seconds_belong", elapsed_s=True),
    scenario("text_where_seconds_belong", elapsed_s="12.7"),
    scenario("a_decimal_where_seconds_belong", elapsed_s=12.7),
    scenario("two_to_the_1023_seconds", elapsed_s=2**1023),
    scenario("two_to_the_1024_seconds", elapsed_s=2**1024),
    scenario("ten_to_the_400_seconds", elapsed_s=10**400),
    scenario("nothing_where_seconds_belong", elapsed_s=None),
    scenario("a_zero_wide_window", width=0, height=0),
    scenario("a_one_pixel_window", width=1, height=1),
    scenario("a_negative_window", width=-40, height=-40),
    scenario("a_very_wide_window", width=1_000_000_000, height=40),
    scenario("a_fractional_window", width=12.7, height=12.7),
    scenario("a_whole_number_window", width=12, height=12),
    scenario("a_decimal_window", width=12.0, height=12.0),
    scenario("a_flag_where_a_width_belongs", width=True, height=True),
    scenario("text_where_a_width_belongs", width="12.7", height=8),
    scenario("not_a_number_where_a_width_belongs", width=math.nan, height=8),
    scenario("infinite_width", width=math.inf, height=8),
    scenario("minus_infinite_width", width=-math.inf, height=8),
    scenario("two_to_the_1024_wide", width=2**1024, height=8),
    scenario("ten_to_the_400_wide", width=10**400, height=8),
    scenario("nothing_where_a_width_belongs", width=None, height=8),
    scenario("a_huge_height_with_no_scanlines", elapsed_s=0.0, height=2**40),
    scenario("an_empty_version", version=""),
    scenario("a_unicode_version", version=UNICODE_TEXT),
    scenario("a_two_hundred_character_version", version=LONG_TEXT),
    scenario("markup_in_the_version", version=MARKUP_TEXT),
    scenario("an_apostrophe_in_the_version", version=APOSTROPHE_TEXT),
    scenario("wrong_capitals_in_the_version", version=WRONG_CAPITALS_TEXT),
    scenario("a_newline_in_the_version", version=NEWLINE_TEXT),
    scenario("one_tick", steps=("tick",)),
    scenario("the_tick_before_glow", steps=("tick",) * (TICKS_TO_GLOW - 1)),
    scenario("the_tick_that_enters_glow", steps=("tick",) * TICKS_TO_GLOW),
    scenario("the_tick_that_enters_fadeout", steps=("tick",) * TICKS_TO_FADEOUT),
    scenario("the_tick_that_closes", steps=("tick",) * TICKS_TO_CLOSE),
    scenario("a_tick_after_the_close", steps=("tick",) * (TICKS_TO_CLOSE + 4)),
    scenario("clicked_then_ticked", steps=("click", "tick")),
    scenario("clicked_twice", steps=("click", "click")),
    scenario("ticked_then_clicked", steps=("tick", "tick", "click")),
    scenario("closed_with_no_handoff", steps=("tick",) * TICKS_TO_CLOSE, handoff=False),
    scenario("no_screen_falls_back_to_the_window", screen=None),
    scenario("no_screen_and_a_wider_window", screen=None, target=(0, 0, 640, 480)),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}

REFUSING_SCENARIOS = (
    "a_decimal_window",
    "a_fractional_window",
    "infinite_seconds",
    "infinite_width",
    "minus_infinite_seconds",
    "minus_infinite_width",
    "not_a_number_of_seconds",
    "not_a_number_where_a_width_belongs",
    "nothing_where_a_width_belongs",
    "nothing_where_seconds_belong",
    "ten_to_the_400_seconds",
    "ten_to_the_400_wide",
    "text_where_a_width_belongs",
    "text_where_seconds_belong",
    "two_to_the_1023_seconds",
    "two_to_the_1024_seconds",
    "two_to_the_1024_wide",
)


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=repr).encode(
            "utf-8"
        )
    ).hexdigest()


def headline(message: str) -> str:
    """The first line of a refusal message.

    Qt names every signature it accepts under its first line, so a check
    reading the whole message compares a list of types, not the refusal.
    """
    return message.splitlines()[0] if message else message


def differences(old, new, prefix: str = "") -> list:
    """Every path at which two traces carry a different value."""
    found: list = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new), key=repr):
            found.extend(differences(old.get(key), new.get(key), f"{prefix}{key}."))
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for index, (left, right) in enumerate(zip(old, new)):
            found.extend(differences(left, right, f"{prefix}{index}."))
    elif repr(old) != repr(new):
        found.append(prefix.rstrip("."))
    return found


class HiddenPrimaryScreen:
    """Hide the primary screen for one construction, then put it back.

    A machine's screen is not a product fact, so the fallback branch is
    reached by taking the screen away rather than by asserting a size.
    """

    def __init__(self, hide: bool):
        self.hide = hide
        self.original = None

    def __enter__(self):
        if self.hide:
            from PySide6.QtWidgets import QApplication

            self.original = QApplication.primaryScreen
            QApplication.primaryScreen = staticmethod(lambda: None)
        return self

    def __exit__(self, *_unused):
        if self.hide and self.original is not None:
            from PySide6.QtWidgets import QApplication

            QApplication.primaryScreen = self.original
        return False


def screen_rectangle() -> list:
    """The rectangle this machine's primary screen reports, read at drive time."""
    from PySide6.QtWidgets import QApplication

    app()
    found = QApplication.primaryScreen().geometry()
    return [found.x(), found.y(), found.width(), found.height()]


def drive_old(spec) -> dict:
    """The shipped SplashScreen, built and driven by one scenario.

    Its widget is destroyed before the trace is returned, so no drive
    holds a widget past its own reading.
    """
    from PySide6.QtCore import Qt

    app()
    colour, rect, font, gradient, pen, painter = recorder_names()
    timer = watched_timer()
    timer.scheduled = []
    painter.ops = []
    base = watched_widget()
    names = {
        "QColor": colour,
        "QFont": font,
        "QLinearGradient": gradient,
        "QPainter": painter,
        "QRectF": rect,
        "QTimer": timer,
        "Qt": Qt,
    }
    target = base()
    target.setGeometry(*spec["target"])
    swap = SwappedQPen(pen)
    with swap, SwappedVersion(spec["version"]):
        built = build_shipped(names, base)
        with HiddenPrimaryScreen(spec["screen"] is None):
            splash = built(target)
        if spec["handoff"]:
            splash._on_finished_callback = lambda: None
        trace = {"swapped_during": swap.swapped()}
        try:
            for step in spec["steps"]:
                splash._tick() if step == "tick" else splash.mousePressEvent(None)
            if not spec["steps"]:
                splash._t = spec["elapsed_s"]
                paint_at_named_size(splash, spec)
            splash.paintEvent(None)
            trace.update(reading_from_widget(splash, painter, timer))
        finally:
            splash._timer.stop()
            splash.setParent(None)
            splash.deleteLater()
            target.deleteLater()
    return trace


def paint_at_named_size(splash, spec) -> None:
    """Make the splash read the width and height the scenario names.

    Qt refuses a size it cannot hold, so the two readers the shipped
    arithmetic calls are answered directly and the arithmetic sees the
    value the scenario named rather than one Qt clamped.
    """
    splash.width = lambda: spec["width"]
    splash.height = lambda: spec["height"]


def reading_from_widget(splash, painter, timer) -> dict:
    """Everything the shipped splash shows, read off the widget."""
    return {
        "phase": splash._phase,
        "elapsed_s": repr(splash._t),
        "geometry": list(splash.geometry().getRect()),
        "closes": splash.closes,
        "timer_running": splash._timer.isActive(),
        "handoff_delays_ms": list(timer.scheduled),
        "paint_ops": list(painter.ops),
    }


def drive_new(spec) -> dict:
    """The Qt-free model, built and driven by the same scenario."""
    with SwappedVersion(spec["version"]):
        model = surface.SplashScreenModel(
            screen_geometry=screen_rectangle() if spec["screen"] else None,
            target_geometry=spec["target"],
            on_finished=(lambda: None) if spec["handoff"] else None,
        )
        for step in spec["steps"]:
            model.tick() if step == "tick" else model.clicked()
        if spec["steps"]:
            painted = model.paint_ops()
        else:
            model.elapsed_s = spec["elapsed_s"]
            painted = surface.paint_ops(model.elapsed_s, spec["width"], spec["height"])
        return {
            "swapped_during": True,
            "phase": model.phase,
            "elapsed_s": repr(model.elapsed_s),
            "geometry": list(model.geometry),
            "closes": model.closes,
            "timer_running": model.timer_running,
            "handoff_delays_ms": list(model.handoff_delays_ms),
            "paint_ops": painted,
        }


def outcome(work) -> dict:
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "headline": headline(str(exc)),
        }


def old_outcome(spec) -> dict:
    return outcome(lambda: drive_old(spec))


def new_outcome(spec) -> dict:
    return outcome(lambda: drive_new(spec))


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_one_splash(name):
    """A phase, time, colour, gradient stop, font, rectangle or text differs."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    moved = differences(old["value"], new["value"])
    assert moved == [], (name, moved[:6], len(moved))
    assert digest(new["value"]) == digest(old["value"]), name


def test_every_input_is_either_answered_or_refused_and_both_happen():
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
def test_a_refused_input_names_the_same_error_type_on_both_sides(name):
    """One side refused an input the other accepted, or named another error."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert new["error"] == old["error"], (name, old, new)


def test_the_refusals_name_more_than_one_error_type():
    """Every refusal names one error, so the error check compares nothing."""
    named = {name: old_outcome(BY_NAME[name])["error"] for name in REFUSING_SCENARIOS}
    assert len(set(named.values())) > 1, named
    assert set(named.values()) == {"TypeError", "OverflowError", "ValueError"}, named


def test_the_comparison_reports_two_different_real_inputs_each_way():
    """The comparison passes whatever the second side produced.

    Two real inputs, one through each side, in both directions.
    """
    early = BY_NAME["fadein_middle"]
    late = BY_NAME["glow_middle"]
    forward = differences(drive_old(early), drive_new(late))
    assert forward != [], "the fade-in and the glow compared as one picture"
    backward = differences(drive_old(late), drive_new(early))
    assert backward != [], "the glow and the fade-in compared as one picture"
    assert digest(drive_old(early)) != digest(drive_new(late))
    assert digest(drive_old(late)) != digest(drive_new(early))


def test_the_same_input_twice_compares_equal_on_both_sides():
    """A drive carries state into the next, so no two drives agree."""
    spec = BY_NAME["glow_middle"]
    assert differences(drive_old(spec), drive_old(spec)) == []
    assert differences(drive_new(spec), drive_new(spec)) == []
    assert digest(drive_old(spec)) == digest(drive_new(spec))


def test_a_whole_number_of_seconds_and_a_decimal_hash_apart():
    """Four seconds and four-point-zero hash the same, so a change hides.

    The two compare equal as numbers. The trace carries each as its own
    text, so the hash tells them apart.
    """
    whole = drive_old(BY_NAME["a_whole_number_of_seconds"])
    decimal = drive_old(BY_NAME["a_decimal_number_of_seconds"])
    assert whole["elapsed_s"] == "4"
    assert decimal["elapsed_s"] == "4.0"
    assert digest(whole) != digest(decimal)
    assert differences(whole, drive_new(BY_NAME["a_whole_number_of_seconds"])) == []


def test_two_not_a_numbers_compare_as_text_and_not_as_numbers():
    """Two not-a-numbers were compared as numbers, which is never equal.

    A not-a-number is never equal to itself, so a plain comparison of two
    traces carrying one would report a difference that is not one. The
    trace carries the time as its own text instead.
    """
    left = {"elapsed_s": repr(math.nan), "phase": surface.FADEIN}
    assert differences({"t": math.nan}, {"t": math.nan}) == [], (
        "the comparison read the times as numbers, so two equal traces "
        "report a difference"
    )
    assert differences(left, dict(left)) == []
    assert differences(left, {"elapsed_s": repr(1.0), "phase": surface.FADEIN}) == [
        "elapsed_s"
    ]


def test_a_not_a_number_elapsed_time_stops_the_splash_painting():
    """A not-a-number time paints, so the splash survives one.

    Neither comparison in the shipped master-opacity ladder is true for a
    not-a-number, so the master alpha holds full -- and then the title
    glow reaches ``int`` on a not-a-number and the paint refuses. Both
    sides refuse with the same error. Reported, not repaired.
    """
    spec = BY_NAME["not_a_number_of_seconds"]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert surface.master_alpha(math.nan) == surface.FULL_ALPHA
    assert old["outcome"] == "refused", old
    assert old["error"] == "ValueError", old
    assert new["error"] == old["error"], (old, new)
    assert old_outcome(BY_NAME["glow_middle"])["outcome"] == "answered"


# Step sequences, including ones that refuse part way

STEP_SEQUENCES = [
    ("ticks_only", ("tick", "tick", "tick"), None),
    ("a_click_between_ticks", ("tick", "click", "tick"), None),
    ("a_refusal_on_the_second_step", ("tick", "boom", "tick"), 1),
    ("a_refusal_on_the_first_step", ("boom", "tick"), 0),
    ("a_refusal_on_the_last_step", ("tick", "tick", "boom"), 2),
]


def run_sequence(model, steps) -> dict:
    """Drive one step sequence, reporting where it stopped and why."""
    done: list = []
    for index, step in enumerate(steps):
        try:
            if step == "tick":
                model.tick()
            elif step == "click":
                model.clicked()
            else:
                raise ValueError(f"no step named {step}")
        except Exception as exc:
            return {
                "steps_done": done,
                "stopped_at": index,
                "stopped_on": step,
                "refusal": type(exc).__name__,
                "calls": list(model.calls),
            }
        done.append(step)
    return {
        "steps_done": done,
        "stopped_at": None,
        "stopped_on": None,
        "refusal": None,
        "calls": list(model.calls),
    }


@pytest.mark.parametrize("name,steps,stops_at", STEP_SEQUENCES)
def test_a_sequence_that_refuses_part_way_keeps_what_it_recorded(name, steps, stops_at):
    """A refusal mid-sequence threw away the steps taken before it."""
    model = surface.SplashScreenModel(screen_geometry=(0, 0, 800, 800))
    ran = run_sequence(model, steps)
    assert ran["stopped_at"] == stops_at, (name, ran)
    if stops_at is None:
        assert ran["refusal"] is None, (name, ran)
        assert len(ran["steps_done"]) == len(steps)
    else:
        assert ran["refusal"] == "ValueError", (name, ran)
        assert ran["steps_done"] == list(steps[:stops_at]), (name, ran)
    expected_ticks = ran["steps_done"].count("tick")
    assert ran["calls"].count(surface.TICKED) == expected_ticks, (name, ran)
    assert ran["calls"][0] == surface.BUILT
    assert model.calls == ran["calls"], "the recorder lost what it held"


def test_the_sequence_recorder_reports_a_refusal_and_a_clean_run():
    """The sequence recorder reports the same thing whatever happens."""
    clean = run_sequence(
        surface.SplashScreenModel(screen_geometry=(0, 0, 8, 8)), ("tick",)
    )
    broken = run_sequence(
        surface.SplashScreenModel(screen_geometry=(0, 0, 8, 8)), ("boom",)
    )
    assert clean["refusal"] is None and broken["refusal"] == "ValueError"
    assert clean["stopped_at"] is None and broken["stopped_at"] == 0


def test_the_shipped_splash_takes_one_phase_step_per_tick():
    """One tick moved the splash through two phases at once."""
    spec = BY_NAME["the_tick_that_enters_glow"]
    old = drive_old(spec)
    new = drive_new(spec)
    assert old["phase"] == surface.GLOW, old["phase"]
    assert new["phase"] == surface.GLOW
    assert differences(old, new) == []


def test_the_tick_that_closes_stops_the_timer_and_schedules_the_handoff():
    """The close step left the timer running or dropped the hand-off."""
    old = drive_old(BY_NAME["the_tick_that_closes"])
    new = drive_new(BY_NAME["the_tick_that_closes"])
    assert old["timer_running"] is False, old
    assert old["closes"] == 1, old
    assert old["handoff_delays_ms"] == [surface.HANDOFF_DELAY_MS], old
    assert differences(old, new) == []


def test_a_close_with_no_callback_schedules_nothing():
    """The splash scheduled a hand-off nobody asked for."""
    old = drive_old(BY_NAME["closed_with_no_handoff"])
    new = drive_new(BY_NAME["closed_with_no_handoff"])
    assert old["handoff_delays_ms"] == [], old
    assert old["closes"] == 1, old
    assert differences(old, new) == []
    assert surface.HANDOFF_SKIPPED in surface.CALL_NAMES


def test_a_click_jumps_the_clock_to_the_start_of_the_fade_out():
    """A click left the splash in the phase it was already in."""
    old = drive_old(BY_NAME["ticked_then_clicked"])
    new = drive_new(BY_NAME["ticked_then_clicked"])
    assert old["phase"] == surface.FADEOUT
    assert old["elapsed_s"] == repr(surface.CLICK_JUMPS_TO_S)
    assert differences(old, new) == []


def test_the_shipped_class_declares_five_methods_and_no_signal():
    """The shipped splash gained or lost a method.

    The methods are read off the compiled class body, so a method the
    platform adds to the class object cannot be counted as one of them.
    """
    assert sorted(SHIPPED_METHOD_CODE) == [
        "__init__",
        "_ease",
        "_tick",
        "mousePressEvent",
        "paintEvent",
    ]
    assert len(SHIPPED_METHOD_CODE) == SHIPPED_METHOD_TOTAL
    from PySide6.QtCore import Qt

    colour, rect, font, gradient, pen, painter = recorder_names()
    built = build_shipped(
        {
            "QColor": colour,
            "QFont": font,
            "QLinearGradient": gradient,
            "QPainter": painter,
            "QRectF": rect,
            "QTimer": watched_timer(),
            "Qt": Qt,
        },
        watched_widget(),
    )
    on_the_class = set(vars(built))
    assert "staticMetaObject" in on_the_class, (
        "the platform adds nothing to the class object, so reading it "
        "would be the same measurement"
    )
    assert set(SHIPPED_METHOD_CODE) < on_the_class
    signals = [
        name for name, value in vars(built).items() if type(value).__name__ == "Signal"
    ]
    assert signals == [], signals


def test_the_method_reader_reports_a_method_that_is_there():
    """The method reader returns the same names whatever the body holds."""
    scratch = compile(
        "class Scratch:\n    def only(self):\n        return 1\n",
        "<scratch>",
        "exec",
    )
    body = next(
        const
        for const in scratch.co_consts
        if hasattr(const, "co_name") and const.co_name == "Scratch"
    )
    named = [c.co_name for c in body.co_consts if hasattr(c, "co_name")]
    assert named == ["only"], named
    assert "only" not in SHIPPED_METHOD_CODE


def test_the_shipped_class_binds_seven_names_from_the_entry_point():
    """The splash reaches for a Qt name the rebuild does not supply."""
    assert sorted(SPLASH_BODY.co_freevars) == [
        "QColor",
        "QFont",
        "QLinearGradient",
        "QPainter",
        "QRectF",
        "QTimer",
        "Qt",
    ]
    assert len(SPLASH_BODY.co_freevars) == SHIPPED_FREE_NAME_TOTAL


def _built_splash():
    """The shipped SplashScreen, built on a watched timer and widget."""
    from PySide6.QtCore import Qt

    app()
    colour, rect, font, gradient, pen, painter = recorder_names()
    del pen
    built = build_shipped(
        {
            "QColor": colour,
            "QFont": font,
            "QLinearGradient": gradient,
            "QPainter": painter,
            "QRectF": rect,
            "QTimer": watched_timer(),
            "Qt": Qt,
        },
        watched_widget(),
    )
    target = watched_widget()()
    return built(target), target


def test_the_splash_starts_exactly_one_timer():
    """The splash runs its own clock and nothing else's."""
    from PySide6.QtCore import QObject, QTimer

    app()
    started: list = []
    original_start = QTimer.start
    original_start_timer = QObject.startTimer

    def watch_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return original_start(self, *args, **kwargs)

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return original_start_timer(self, *args, **kwargs)

    QTimer.start = watch_start
    QObject.startTimer = watch_start_timer
    try:
        splash, target = _built_splash()
        observed = list(started)
        started.clear()
        QTimer().start(400)
    finally:
        QTimer.start = original_start
        QObject.startTimer = original_start_timer
    splash._timer.stop()
    splash.setParent(None)
    splash.deleteLater()
    target.deleteLater()
    assert started == [("QTimer.start", (400,))], "the watcher is blind"
    assert [name for name, _args in observed] == ["QTimer.start"], observed
    assert surface.TIMERS == {"tick": surface.TIMER_INTERVAL_MS}
    assert splash._timer.interval() == surface.TIMER_INTERVAL_MS


def test_the_splash_stands_on_qwidget():
    """The shipped class is a QWidget, whatever name the entry point
    imported it under."""
    from PySide6.QtWidgets import QLabel, QWidget

    app()
    built = painting_class()
    assert issubclass(built, QWidget)
    assert not issubclass(built, QLabel), "the base widened without notice"


def test_the_splash_wires_one_signal_and_no_more():
    """The splash's own timer carries one receiver, counted on it."""
    from PySide6.QtCore import QTimer

    splash, target = _built_splash()
    splash._timer.stop()
    timeout = "2timeout()"
    live = splash._timer.receivers(timeout)
    bare = QTimer().receivers(timeout)
    splash.setParent(None)
    splash.deleteLater()
    target.deleteLater()
    assert bare == 0, "a bare QTimer already carries a receiver"
    assert live == SPLASH_CONNECT_TOTAL == 1
    assert len(surface.ACTIONS) == live


def test_one_emit_of_the_wired_signal_advances_the_clock_exactly_one_tick():
    """The splash wires no receiver, or wires the same one twice.

    Counted on the running widget by the product's own effect: one emit
    moves the clock one step. A bare timer moves nothing, and a second
    wire moves it twice, so the counter reports in both directions.
    """
    from PySide6.QtCore import Qt

    app()
    colour, rect, font, gradient, pen, painter = recorder_names()
    built = build_shipped(
        {
            "QColor": colour,
            "QFont": font,
            "QLinearGradient": gradient,
            "QPainter": painter,
            "QRectF": rect,
            "QTimer": watched_timer(),
            "Qt": Qt,
        },
        watched_widget(),
    )
    target = watched_widget()()
    splash = built(target)
    splash._timer.stop()
    before = splash._t
    splash._timer.timeout.emit()
    assert splash._t - before == pytest.approx(TICK_S), splash._t

    from PySide6.QtCore import QTimer

    bare = QTimer()
    moved = splash._t
    bare.timeout.emit()
    assert splash._t == moved, "a bare timer reached the splash"

    splash._timer.timeout.connect(splash._tick)
    twice = splash._t
    splash._timer.timeout.emit()
    assert splash._t - twice == pytest.approx(TICK_S * 2), splash._t
    splash.setParent(None)
    splash.deleteLater()
    target.deleteLater()


def test_neither_side_starts_a_thread():
    """A thread the splash starts outlives the window that started it."""
    before = threading.active_count()
    drive_old(BY_NAME["glow_middle"])
    drive_new(BY_NAME["glow_middle"])
    assert threading.active_count() == before, "a drive left a thread running"
    assert ENTRY_THREAD_TOTAL == 0


def test_the_thread_counter_sees_a_thread_that_is_started():
    """POSITIVE CONTROL: ``threading.active_count`` rises for a thread
    the test starts itself."""
    started = threading.Event()
    holding = threading.Event()
    before = threading.active_count()

    def _wait():
        started.set()
        holding.wait(5.0)

    worker = threading.Thread(target=_wait, daemon=True)
    worker.start()
    started.wait(5.0)
    try:
        assert threading.active_count() > before
    finally:
        holding.set()
        worker.join(5.0)


def test_the_splash_emits_no_signal_of_its_own():
    """The shipped class declares no Signal, so the surface names no
    topic for one."""
    from PySide6.QtCore import Signal

    app()
    built = painting_class()
    declared = [
        name for name, value in vars(built).items() if isinstance(value, Signal)
    ]
    assert declared == [], declared
    assert surface.BUS_TOPICS == ()


def test_the_signal_reader_sees_a_declared_signal():
    """POSITIVE CONTROL: the same reader names a Signal on a class that
    declares one."""
    from PySide6.QtCore import QObject, Signal

    class _Declaring(QObject):
        moved = Signal(int)

    declared = [
        name for name, value in vars(_Declaring).items() if isinstance(value, Signal)
    ]
    assert declared == ["moved"]


def _eased_calls_during_a_paint():
    """``_ease`` calls and paints one splash makes over three frames."""
    from tests.qt_pixel import render_widget

    app()
    built = painting_class()
    reached: list = []
    painted: list = []
    built._ease = lambda *args, **kwargs: reached.append(args) or 0.0
    shipped_paint = built.paintEvent
    built.paintEvent = lambda self, event: painted.append(self._t) or shipped_paint(
        self, event
    )
    splash = built(None)
    splash._timer.stop()
    for name in PICTURE_FRAMES:
        splash._t = BY_NAME[name]["elapsed_s"]
        render_widget(splash, PIXEL_SIZE)
    splash._t = 0.0
    splash._tick()
    splash.deleteLater()
    return built, reached, painted


def test_the_shipped_easing_helper_is_called_nowhere():
    """Three painted frames and a tick never reach ``_ease``, so removing
    it would change no pixel. Named here, not removed."""
    _built, reached, painted = _eased_calls_during_a_paint()
    assert painted == [
        BY_NAME[name]["elapsed_s"] for name in PICTURE_FRAMES
    ], "the drive painted nothing, so the empty list below means nothing"
    assert reached == [], reached


def test_the_easing_tripwire_fires_when_the_helper_is_called():
    """POSITIVE CONTROL: the same tripwire, on the same class, records a
    direct call."""
    built, reached, _painted = _eased_calls_during_a_paint()
    built._ease(None, 0.0, 0.0, 1.0, 1.0)
    assert len(reached) == 1


# Completeness


def surface_constants() -> dict:
    """Every value the surface exports that is not a function or a class."""
    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def leaves(value, prefix: str = "") -> dict:
    """Every leaf inside `value`, keyed by the path that reaches it."""
    found: dict = {}
    if isinstance(value, dict):
        for key, inner in value.items():
            found.update(leaves(inner, f"{prefix}{key}."))
    elif isinstance(value, (list, tuple)):
        for index, inner in enumerate(value):
            found.update(leaves(inner, f"{prefix}{index}."))
    else:
        found[prefix.rstrip(".")] = repr(value)
    return found


def named_payload() -> dict:
    """The view model the completeness check reads."""
    return surface.build_view_model(version="3.25.8")


def unaccounted_constants(payload, constants) -> list:
    """The exported values whose leaves reach no leaf of the snapshot."""
    carried = set(leaves(payload).values())
    return sorted(
        name
        for name, value in constants.items()
        if not set(leaves(value).values()) <= carried
    )


PAYLOAD_KEYS = (
    "actions",
    "bus_topics",
    "call_names",
    "calls",
    "closes",
    "delete_on_close",
    "elapsed_s",
    "element_fades",
    "geometry",
    "handoff_delays_ms",
    "is_open",
    "labels",
    "method",
    "paint_ops",
    "phase",
    "phase_boundaries_s",
    "phases",
    "repaints",
    "texts",
    "timer_delays_ms",
    "timers",
    "timer_running",
    "translucent_background",
    "window_flags",
)


# Values the painter reads rather than carries, so no leaf holds them.
READ_BY_THE_PAINTER = {
    "BUILDER_RECT",
    "DESIGNER_ALIAS_RECT",
    "DESIGNER_RECT",
    "HINT_AT_S",
    "HINT_GROW_S",
    "HINT_OFFSET_Y",
    "HINT_RGB",
    "INNER_RING_RADIUS",
    "LOGO_GLOW_MIN_ALPHA",
    "LOGO_GLOW_RADIUS",
    "LOGO_OFFSET_Y",
    "MASTER_FALL_S",
    "MONOGRAM_RECT",
    "ORBIT_ALPHA_SHARE",
    "ORBIT_ANGLES",
    "PARTICLE_ANGLES",
    "PARTICLE_SPIN_SHARE",
    "PULSE_DEPTH",
    "PULSE_RATE",
    "RULE_GROW_S",
    "RULE_MIN_WIDTH",
    "SCANLINE_MIN_ALPHA",
    "SPIN_DEGREES_PER_S",
    "SUBTITLE_RECT",
    "TITLE_GLOW_BASE",
    "TITLE_GLOW_DEPTH",
    "TITLE_RECT",
    "VERSION_PREFIX",
    "VERSION_RECT",
}

# Values the clock reads, with the check that drives each.
READ_BY_THE_CLOCK = {
    "TICK_SECONDS": "test_the_tick_that_closes_stops_the_timer_and_schedules_the_handoff"
}

PERTURBATION_TIMES = [round(step * 0.01, 2) for step in range(0, 161)] + [
    round(1.6 + step * 0.05, 2) for step in range(0, 149)
]


def perturbed(value):
    """`value` moved far enough that anything reading it paints differently."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value * 2 + 1
    if isinstance(value, str):
        return value + "X"
    if isinstance(value, tuple):
        return tuple(perturbed(inner) for inner in value)
    if isinstance(value, list):
        return [perturbed(inner) for inner in value]
    if isinstance(value, dict):
        return {key: perturbed(inner) for key, inner in value.items()}
    return value


def ops_across_time() -> list:
    """The op lists the surface paints across the whole splash lifetime."""
    return [surface.paint_ops(when, 60, 60, "3.25.8") for when in PERTURBATION_TIMES]


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read."""
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = set(unaccounted_constants(named_payload(), constants))
    assert unaccounted - READ_BY_THE_PAINTER - set(READ_BY_THE_CLOCK) == set(), sorted(
        unaccounted - READ_BY_THE_PAINTER - set(READ_BY_THE_CLOCK)
    )
    assert READ_BY_THE_PAINTER <= unaccounted, sorted(READ_BY_THE_PAINTER - unaccounted)
    for covered_by in READ_BY_THE_CLOCK.values():
        assert callable(globals()[covered_by]), covered_by


@pytest.mark.parametrize("name", sorted(READ_BY_THE_PAINTER))
def test_a_value_the_painter_reads_changes_what_the_painter_paints(name):
    """A value the surface exports reaches no snapshot and no painted op.

    The value is moved, the whole lifetime is repainted, and at least one
    frame must differ. A value nothing reads changes nothing and is caught
    here rather than by a comparison that never looked at it.
    """
    before = ops_across_time()
    original = getattr(surface, name)
    try:
        setattr(surface, name, perturbed(original))
        after = ops_across_time()
    finally:
        setattr(surface, name, original)
    assert after != before, name
    assert getattr(surface, name) == original, "the perturbation was not put back"
    assert ops_across_time() == before, "the perturbation outlived the test"


def test_the_perturbation_check_reports_nothing_for_a_value_nobody_reads():
    """The perturbation check reports a difference whatever it moves."""
    before = ops_across_time()
    surface.INVENTED_CONSTANT = 1
    try:
        surface.INVENTED_CONSTANT = 99
        assert ops_across_time() == before, (
            "a value nothing reads changed the painted ops, so the check "
            "reports a difference that is not one"
        )
    finally:
        del surface.INVENTED_CONSTANT
    assert perturbed(30) == 61
    assert perturbed((30, -30)) == (61, -59)
    assert perturbed("v") == "vX"
    assert perturbed(True) is False


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    built = named_payload()
    assert sorted(built) == sorted(PAYLOAD_KEYS), sorted(built)
    assert len(built) == PAYLOAD_KEY_TOTAL
    assert len(PAYLOAD_KEYS) == PAYLOAD_KEY_TOTAL


def test_both_completeness_checks_report_what_they_are_given():
    """Both completeness checks passed because they look at nothing."""
    payload = named_payload()
    accounted = READ_BY_THE_PAINTER | set(READ_BY_THE_CLOCK)
    constants = dict(surface_constants())
    plain = set(unaccounted_constants(payload, constants)) - accounted
    assert plain == set(), sorted(plain)
    constants["INVENTED_CONSTANT"] = "never in any snapshot"
    grown_names = set(unaccounted_constants(payload, constants)) - accounted
    assert grown_names == {"INVENTED_CONSTANT"}, sorted(grown_names)
    grown = dict(payload)
    grown["invented_key"] = 1
    assert sorted(grown) != sorted(PAYLOAD_KEYS)
    shrunk = {key: value for key, value in payload.items() if key != "phases"}
    assert sorted(shrunk) != sorted(PAYLOAD_KEYS)
    assert "build_view_model" not in surface_constants()
    assert "SplashScreenModel" not in surface_constants()


def test_the_leaf_reader_compares_leaves_and_not_containers():
    """The leaf reader compares whole containers, so an order change hides."""
    assert leaves([1, 2]) == {"0": "1", "1": "2"}
    assert leaves([2, 1]) != leaves([1, 2])
    assert leaves({"a": [1]}) == {"a.0": "1"}
    assert leaves(True) == {"": "True"}
    assert leaves(1) == {"": "1"}
    assert leaves(True) != leaves(1), "a flag and a one read as one value"


def test_no_expected_value_is_held_in_a_set_beside_its_boolean_twin():
    """A flag and a one were held in one set, so one of them vanished.

    The surface exports a flag and several ones. Every holder in this file
    keys by name or by path, so the two never share a slot.
    """
    hazard = {True, 1, surface.DELETE_ON_CLOSE, surface.PARTICLE_TRAILS}
    assert len(hazard) < 4, "a set is the hazard this test describes"
    kept = leaves({"flag": True, "count": 1})
    assert kept == {"flag": "True", "count": "1"}, kept
    assert len(PAYLOAD_KEYS) == len(set(PAYLOAD_KEYS))
    assert all(isinstance(name, str) for name in PAYLOAD_KEYS)
    assert all(isinstance(name, str) for name in surface_constants())


# The pictures

PICTURE_FRAMES = ("fadein_middle", "glow_middle", "fadeout_middle")


def painting_class():
    """The shipped class with every free name bound to the real Qt one."""
    from PySide6.QtCore import QRectF, QTimer, Qt
    from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter
    from PySide6.QtWidgets import QWidget

    return build_shipped(
        {
            "QColor": QColor,
            "QFont": QFont,
            "QLinearGradient": QLinearGradient,
            "QPainter": QPainter,
            "QRectF": QRectF,
            "QTimer": QTimer,
            "Qt": Qt,
        },
        QWidget,
    )


def widget_painted_by_the_splash(name, rule=None):
    """The shipped splash at one frame, ready to render."""
    app()
    splash = painting_class()(None)
    splash._timer.stop()
    splash._t = BY_NAME[name]["elapsed_s"]
    if rule:
        splash.setStyleSheet(rule)
    return splash


def ops_payload(name):
    """The op list the surface produces for one frame, stamped."""
    from src import __version__

    return sealed(
        surface.paint_ops(
            BY_NAME[name]["elapsed_s"], PIXEL_SIZE[0], PIXEL_SIZE[1], str(__version__)
        )
    )


def widget_painted_by_the_model(payload, rule=None):
    """A window that replays a payload's ops, built from no shipped widget."""
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
    from PySide6.QtWidgets import QWidget

    ops = unaltered(payload)
    app()

    class Replay(QWidget):
        """The splash picture, painted only from the surface's op list."""

        def __init__(self):
            QWidget.__init__(self, None)
            self.setAccessibleName("Splash Screen")

        def paintEvent(self, _event):
            painter = QPainter(self)
            pen = QPen()
            for op in ops:
                head = op[0]
                if head == "render_hint":
                    painter.setRenderHint(QPainter.Antialiasing)
                elif head == "pen_style":
                    painter.setPen(Qt.NoPen)
                elif head == "brush_style":
                    painter.setBrush(Qt.NoBrush)
                elif head == "pen_colour":
                    painter.setPen(QColor(*op[1]))
                elif head == "brush_colour":
                    painter.setBrush(QColor(*op[1]))
                elif head == "pen":
                    pen = QPen(QColor(*op[1]))
                    pen.setWidthF(op[2])
                    painter.setPen(pen)
                elif head == "font":
                    painter.setFont(
                        QFont(op[1], op[2], QFont.Bold)
                        if len(op) > 3
                        else QFont(op[1], op[2])
                    )
                elif head == "fill_rect":
                    gradient = QLinearGradient(
                        op[5][1][0], op[5][1][1], op[5][2][0], op[5][2][1]
                    )
                    for at, rgba in op[5][3]:
                        gradient.setColorAt(at, QColor(*rgba))
                    painter.fillRect(op[1], op[2], op[3], op[4], gradient)
                elif head == "line":
                    painter.drawLine(op[1], op[2], op[3], op[4])
                elif head == "ellipse":
                    painter.drawEllipse(QRectF(*op[1]))
                elif head == "text":
                    painter.drawText(QRectF(*op[1]), Qt.AlignCenter, op[3])
                elif head == "save":
                    painter.save()
                elif head == "restore":
                    painter.restore()
                elif head == "translate":
                    painter.translate(op[1], op[2])
                elif head == "rotate":
                    painter.rotate(op[1])
                elif head == "end":
                    painter.end()
                else:
                    raise AssertionError(f"the replay cannot paint {head!r}")

    built = Replay()
    if rule:
        built.setStyleSheet(rule)
    return built


def rendered(widget):
    from tests.qt_pixel import render_widget

    return render_widget(widget, PIXEL_SIZE)


@pytest.mark.parametrize("name", PICTURE_FRAMES)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different frame than the shipped splash."""
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    old = rendered(widget_painted_by_the_splash(name))
    assert_picture_can_report(old, note=note)
    new = rendered(widget_painted_by_the_model(ops_payload(name)))
    assert_picture_can_report(new, note=note)
    assert_pictures_match(old_side=old, new_side=new, note=note)


@pytest.mark.parametrize("name", PICTURE_FRAMES)
def test_the_colour_count_of_each_frame_is_reported(name):
    """A frame painted one colour, so its comparison reports nothing."""
    found = colour_count(rendered(widget_painted_by_the_splash(name)))
    assert found > 100, (name, found)
    assert found == colour_count(
        rendered(widget_painted_by_the_model(ops_payload(name)))
    ), name


def test_the_picture_comparison_reports_two_different_frames():
    """The picture check passes whatever the second side paints."""
    assert_cases_paint_differently(
        old_side=rendered(widget_painted_by_the_splash("fadein_middle")),
        new_side=rendered(widget_painted_by_the_model(ops_payload("glow_middle"))),
        note="the fade-in against the glow",
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    payload = ops_payload("glow_middle")
    payload.append(["end"])
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(surface.paint_ops(4.0, 40, 40, "3.25.8"))


SKIN_RULE = "QWidget { background: #3a1414; } * { background: #3a1414; }"


@pytest.mark.parametrize("name", ("fadein_middle", "glow_middle"))
def test_no_style_rule_reaches_a_pixel_while_the_splash_is_opaque(name):
    """A style rule moves a pixel here, so a skin check could report.

    ``paintEvent`` fills the whole rectangle, and while the master fade
    holds the fill is opaque, so nothing the style resolves survives. The
    skin control is pinned as unable to report rather than written as a
    check that cannot fail.
    """
    plain = rendered(widget_painted_by_the_splash(name))
    skinned = rendered(widget_painted_by_the_splash(name, rule=SKIN_RULE))
    assert_picture_can_report(plain, note=name)
    assert_pictures_match(old_side=plain, new_side=skinned, note=f"{name}, skinned")


def test_the_skin_control_reports_once_the_fade_out_makes_the_fill_translucent():
    """The style rule reaches no pixel at any time, so no skin check can run.

    In the fade-out the whole picture is painted at a reduced alpha, so the
    window's own background shows through and a style rule does move a
    pixel. That is the one frame at which the two sides can be compared
    for their skin.
    """
    assert_same_skin(
        build_old_side=lambda: widget_painted_by_the_splash("fadeout_middle"),
        build_new_side=lambda: widget_painted_by_the_model(
            ops_payload("fadeout_middle")
        ),
        size=PIXEL_SIZE,
        control_rule=SKIN_RULE,
        note="the fade-out frame",
    )


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report."""
    for name in ("fadein_middle", "glow_middle", "fadeout_middle"):
        old = drive_old(BY_NAME[name])
        new = drive_new(BY_NAME[name])
        for key in ("phase", "timer_running", "handoff_delays_ms", "geometry"):
            assert new[key] == old[key], (name, key, old[key], new[key])
    assert drive_old(BY_NAME["fadein_middle"])["phase"] == surface.FADEIN


# The bridge


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_splash_screen_method():
    """The renderer cannot reach the splash over the bridge."""
    from src.core import desktop_bridge

    assert surface.METHOD in desktop_bridge.build_registry()
    assert surface.METHOD == "splash_screen.state"
    answer = bridge_answer({})
    assert answer["ok"] is True, answer
    assert answer["result"]["phase"] == surface.FADEIN
    assert answer["result"]["geometry"] == list(surface.DEFAULT_GEOMETRY)


def test_the_bridge_ticks_the_splash_as_many_times_as_it_is_asked():
    """The bridge dropped the ticks the request carried."""
    asked = {"ticks": TICKS_TO_GLOW, "screen_geometry": [0, 0, 40, 40]}
    result = bridge_answer(asked)["result"]
    assert result["phase"] == surface.GLOW
    assert result["calls"].count(surface.TICKED) == TICKS_TO_GLOW
    assert result["geometry"] == [0, 0, 40, 40]
    before = bridge_answer({"ticks": TICKS_TO_GLOW - 1})["result"]
    assert before["phase"] == surface.FADEIN, before["phase"]


def test_the_bridge_paints_the_version_the_request_names():
    """The bridge ignored the version the request carried."""
    result = bridge_answer({"version": UNICODE_TEXT, "ticks": 1})["result"]
    texts = [op[3] for op in result["paint_ops"] if op[0] == "text"]
    assert surface.VERSION_PREFIX + UNICODE_TEXT in texts, texts


def test_the_bridge_reports_a_request_it_cannot_render():
    """A request the splash refuses came back as an answer."""
    answer = bridge_answer({"ticks": "lots"})
    assert answer["ok"] is False, answer
    assert answer["error"]["type"] == "ValueError"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    encoded = json.loads(json.dumps(bridge_answer({"click": True, "ticks": 3})))
    assert encoded["ok"] is True
    assert encoded["result"]["method"] == surface.METHOD


# Nothing at import, and no Qt behind the bridge

BRIDGE_PROBE = (
    "import json, sys\n"
    "from src.core import desktop_bridge\n"
    "frame = desktop_bridge.handle_line(json.dumps("
    "{'id': 1, 'method': 'splash_screen.state', 'params': {'ticks': 2}}),"
    " desktop_bridge.build_registry())\n"
    "print(json.dumps({'frame': frame, 'qt': [n for n in sys.modules"
    " if n.startswith('PySide6')]}))\n"
)

NOTHING_AT_IMPORT_PROBE = """
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-splash-probe-'))
os.environ['HOME'] = str(root)
os.environ['USERPROFILE'] = str(root)

opened = []
real_open = open


def watched_open(file, *found, **named):
    opened.append(str(file))
    return real_open(file, *found, **named)


import builtins
builtins.open = watched_open

import time
clock = []
real_time = time.time
real_monotonic = time.monotonic
real_localtime = time.localtime
time.time = lambda: clock.append('time') or real_time()
time.monotonic = lambda: clock.append('monotonic') or real_monotonic()
time.localtime = lambda *a: clock.append('localtime') or real_localtime(*a)

import socket
reached = []


def refuse(address, *found, **named):
    reached.append(str(address))
    raise OSError('the probe may not reach outside')


socket.create_connection = refuse
socket.socket.connect = lambda self, address, *_f, **_n: refuse(address)

import src
opened_before = len(opened)
clock_before = len(clock)
threads_before = threading.active_count()
from src.gui.main_tabs import splash_screen_surface as s

opened_at_import = opened[opened_before:]
clock_at_import = clock[clock_before:]
threads_at_import = threading.active_count() - threads_before
built = s.view_model({'ticks': 1})
answer = {'interval': s.TIMER_INTERVAL_MS,
          'built_on_request': built['paint_ops'] != [],
          'method': s.METHOD,
          'qt': [name for name in sys.modules if name.startswith('PySide6')],
          'opened_at_import': opened_at_import,
          'clock_at_import': clock_at_import,
          'threads_at_import': threads_at_import,
          'reached_at_import': list(reached),
          'made_under_home': sorted(str(p) for p in root.rglob('*'))}
builtins.open = real_open
print(json.dumps(answer))
"""


def run_script(source, env=None):
    """Run one probe in a fresh process and return what it printed."""
    where = dict(os.environ)
    where.pop("ACERVATOR_TEST_HOME", None)
    if env:
        where.update(env)
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
        env=where,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the splash pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] == [], answered["qt"]
    assert answered["frame"]["ok"] is True, answered["frame"]
    assert answered["frame"]["result"]["phase"] == surface.FADEIN


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore\n" + BRIDGE_PROBE)
    assert loaded["qt"] != []
    assert loaded["frame"]["ok"] is True


def test_importing_the_surface_reads_no_file_no_clock_and_starts_no_thread():
    """Loading the surface read a file, read the clock or started a thread.

    The counters start AFTER ``import src``, which resolves the version by
    running git. That cost belongs to the package, not to this module.
    """
    answered = run_script(NOTHING_AT_IMPORT_PROBE)
    assert answered["qt"] == [], answered["qt"]
    assert answered["clock_at_import"] == [], answered["clock_at_import"]
    assert answered["threads_at_import"] == 0, answered["threads_at_import"]
    assert answered["reached_at_import"] == [], answered["reached_at_import"]
    assert answered["made_under_home"] == [], answered["made_under_home"]
    assert [one for one in answered["opened_at_import"] if "splash" in one] == []
    assert answered["interval"] == surface.TIMER_INTERVAL_MS
    assert answered["built_on_request"] is True
    assert answered["method"] == surface.METHOD


def test_the_import_probe_can_report_a_file_a_clock_a_thread_and_a_connection():
    """The import probe reports nothing whatever the module does."""
    probe = NOTHING_AT_IMPORT_PROBE.replace(
        "from src.gui.main_tabs import splash_screen_surface as s",
        "time.time()\n"
        "with open(root / 'splash-seeded.json', 'w') as fh:\n"
        "    fh.write('{}')\n"
        "try:\n"
        "    socket.create_connection(('example.invalid', 443))\n"
        "except OSError:\n"
        "    pass\n"
        "planted = threading.Thread(target=lambda: __import__('time').sleep(5))\n"
        "planted.start()\n"
        "from src.gui.main_tabs import splash_screen_surface as s",
    )
    answered = run_script(probe)
    assert answered["clock_at_import"] == ["time"], answered
    assert answered["threads_at_import"] == 1, answered
    assert answered["reached_at_import"] != [], answered
    assert answered["made_under_home"] != [], answered
    assert [one for one in answered["opened_at_import"] if "splash" in one] != []


# Shared state


def test_the_qpen_swap_is_in_place_during_a_drive_and_gone_after():
    """The swap outlived the drive, or never happened at all."""
    import PySide6.QtGui as qtgui

    before = qtgui.QPen
    assert drive_old(BY_NAME["glow_middle"])["swapped_during"] is True
    assert qtgui.QPen is before
    refused = old_outcome(BY_NAME["text_where_seconds_belong"])
    assert refused["outcome"] == "refused", refused
    assert qtgui.QPen is before, "a refusal left the swap in place"


def test_the_version_swap_is_put_back_after_a_drive_and_after_a_refusal():
    """A drive left its version on the package for the next test to read."""
    import src

    before = src.__version__
    drive_old(BY_NAME["a_unicode_version"])
    assert src.__version__ == before
    drive_new(BY_NAME["a_unicode_version"])
    assert src.__version__ == before
    old_outcome(BY_NAME["text_where_seconds_belong"])
    assert src.__version__ == before


def test_the_primary_screen_swap_is_put_back():
    """The hidden screen outlived the drive that hid it."""
    from PySide6.QtWidgets import QApplication

    app()
    before = QApplication.primaryScreen
    drive_old(BY_NAME["no_screen_falls_back_to_the_window"])
    assert QApplication.primaryScreen is before
    assert QApplication.primaryScreen() is not None


def test_the_entry_point_edits_process_wide_state_at_import():
    """The entry point changes no shared handler, so nothing needs restoring.

    ``main`` installs its own uncaught-exception handlers when it is
    imported. Named here so a reader knows what importing it costs; the
    surface installs none.
    """
    assert sys.excepthook is not sys.__excepthook__
    assert threading.excepthook is not threading.__excepthook__
    assert main._CRASH_LOG_PATH is not None, (
        "importing the entry point wrote no boot line, so the crash log "
        "path was never resolved"
    )
    assert main.CRASH_LOG_ROOT_ENV == "ACERVATOR_CRASH_LOG_ROOT"
    assert os.environ.get(main.CRASH_LOG_ROOT_ENV), (
        "the crash log is not redirected, so a drive would write the "
        "operator's own tree"
    )


def test_a_drive_writes_no_file_under_a_throwaway_home(tmp_path):
    """A drive wrote a file into the home directory it was given."""
    home = tmp_path / "home"
    home.mkdir()
    before = sorted(str(p) for p in home.rglob("*"))
    assert before == []
    drive_old(BY_NAME["glow_middle"])
    drive_new(BY_NAME["glow_middle"])
    assert sorted(str(p) for p in home.rglob("*")) == []
    (home / "planted.txt").write_text("planted", encoding="utf-8")
    assert (
        sorted(str(p) for p in home.rglob("*")) != []
    ), "the home watcher reports nothing whatever lands there"


# What the splash reads out of stored state

BARE_READINGS = (
    True,
    math.nan,
    math.inf,
    -math.inf,
    "twelve",
    "12.7",
    12.7,
    10**400,
)


@pytest.mark.parametrize("stored", BARE_READINGS, ids=repr)
def test_the_version_the_splash_paints_is_taken_as_it_is_stored(stored):
    """The splash guards the version it paints, so a stored value is checked.

    Every value reaches the painted string through ``str``. Nothing is
    refused and nothing is substituted; the reading is reported, not fixed.
    """
    import src

    before = src.__version__
    try:
        src.__version__ = stored
        painted = [op[3] for op in surface.paint_ops(4.0, 400, 400) if op[0] == "text"]
        assert surface.VERSION_PREFIX + str(stored) in painted, painted
    finally:
        src.__version__ = before
    assert src.__version__ == before


@pytest.mark.parametrize("stored", BARE_READINGS, ids=repr)
def test_a_stored_geometry_reaches_the_splash_arithmetic_unchecked(stored):
    """The splash guards the rectangle it is given, so a bad one is refused.

    A stored width goes straight into the arithmetic on both sides. The
    two sides agree on every one, including the ones that refuse.
    """
    spec = scenario("audit", elapsed_s=0.0, width=stored, height=8)
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (stored, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (stored, old, new)
    else:
        assert differences(old["value"], new["value"]) == []


@pytest.mark.parametrize("stored", BARE_READINGS, ids=repr)
def test_a_stored_elapsed_time_reaches_the_splash_arithmetic_unchecked(stored):
    """The splash guards its own clock, so a stored time is refused."""
    spec = scenario("audit", elapsed_s=stored, width=40, height=40)
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (stored, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (stored, old, new)
    else:
        assert differences(old["value"], new["value"]) == []


def test_the_bare_reading_audit_covers_both_answers_and_refusals():
    """Every audited value was accepted, so the audit measures one path."""
    verdicts = {}
    for stored in BARE_READINGS:
        spec = scenario("audit", elapsed_s=stored, width=40, height=40)
        verdicts[repr(stored)] = old_outcome(spec)["outcome"]
    assert "answered" in verdicts.values(), verdicts
    assert "refused" in verdicts.values(), verdicts


# What the bootstrap reads out of stored settings

BOOTSTRAP_SETTINGS_KEYS = ("theme", "username", "app_version")


def settings_in(where):
    """A settings manager pointed at a throwaway directory."""
    from src.core.settings import SettingsManager

    return SettingsManager(config_dir=where)


@pytest.mark.parametrize("key", BOOTSTRAP_SETTINGS_KEYS)
@pytest.mark.parametrize("stored", BARE_READINGS, ids=repr)
def test_a_stored_setting_reaches_the_bootstrap_as_it_was_stored(key, stored, tmp_path):
    """The bootstrap guards a stored setting, so a bad one never reaches it.

    ``get`` returns whatever the file holds and substitutes its default
    only when the key is missing, so every value above reaches the
    bootstrap unchanged. Reported, not repaired.
    """
    settings = settings_in(tmp_path)
    settings.set(key, stored)
    read = settings.get(key, "a default nobody stored")
    assert repr(read) == repr(stored), (key, read, stored)
    assert settings.get("a key nobody stored", "the default") == "the default"


@pytest.mark.parametrize("stored", BARE_READINGS, ids=repr)
def test_a_stored_theme_name_the_engine_does_not_know_stops_the_boot(stored):
    """A stored theme name is checked before it reaches the theme engine.

    ``settings.get("theme", "cyberpunk_dark")`` substitutes its default
    only when the key is absent. A key holding any of these values is read
    as stored, handed to ``apply_theme``, and the engine refuses it. The
    entry point catches nothing here, so the boot ends before the splash.
    Reported, not repaired.
    """
    from src.gui.theme_engine import ThemeManager

    app()
    engine = ThemeManager()
    with pytest.raises(ValueError):
        engine.get_qss(stored)
    assert isinstance(engine.get_qss("cyberpunk_dark"), str), (
        "the theme engine refuses every name, so the refusal above says "
        "nothing about the stored value"
    )
