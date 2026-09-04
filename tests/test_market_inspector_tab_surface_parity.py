"""The Qt Market Inspector tab and the Qt-free surface, side by side.

A failure means the view model describes a different screen, a different
message, a different colour, a different log line, a different branch or
a different delegation than ``MarketInspectorTabMixin`` performs on the
same input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import market_inspector_tab_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
TAB_SOURCE = REPO_ROOT / "src" / "gui" / "live_settings" / "market_inspector_tab.py"
WIRING_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
ELEMENT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"

PIXEL_SIZE = (900, 260)

CONNECT_TOTAL = 0
WIRING_NEIGHBOUR_CONNECT_TOTAL = 1
TIMER_NEIGHBOUR_BUILD_TOTAL = 1
BUS_NEIGHBOUR_TOPIC_TOTAL = 2
ELEMENT_NEIGHBOUR_BUILD_TOTAL = 3
SHIPPED_ELEMENT_TOTAL = 2
SHIPPED_LAYOUT_TOTAL = 1
SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 1
SHIPPED_FUNCTION_TOTAL = 1
PAYLOAD_KEY_TOTAL = 23
CONSTANT_TOTAL = 43

MISSING = object()


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def as_text(value):
    """`value` with every number written as its own text.

    ``12`` and ``12.0`` are one value to a comparison and two different
    numbers to a reader, and two not-a-numbers are never equal to each
    other. Both are settled here before anything is compared.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, dict):
        return {key: as_text(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_text(inner) for inner in value]
    return value


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(
            as_text(value), sort_keys=True, ensure_ascii=True, default=repr
        ).encode("utf-8")
    ).hexdigest()


# The view builder the tab delegates to, as the test owns it. The Qt tab
# is driven with one stand-in and the surface with its own. Neither side
# reads the other's.


class QtDelegate:
    """The per-bot view builder the shipped tab imports and calls.

    Answers with a label carrying `mark`, or throws `raises`. `answer`
    holds what it handed back, so the tab can be asked whether the view
    it returned is the one this builder made.
    """

    def __init__(self, mark=None, raises=None, answers_none=False):
        self.mark = mark
        self.raises = raises
        self.answers_none = answers_none
        self.seen = []
        self.answer = MISSING

    def __call__(self, bot):
        from PySide6.QtWidgets import QLabel

        self.seen.append(bot)
        if self.raises is not None:
            raise self.raises
        self.answer = None if self.answers_none else QLabel(self.mark)
        return self.answer


class SurfaceDelegate(surface.MarketInspectorSource):
    """The surface's own view builder, recording what it answered."""

    def __init__(self, view=None, raises=None):
        super().__init__(view=view, raises=raises)
        self.answer = MISSING

    def build_per_bot_view(self, bot):
        self.answer = super().build_per_bot_view(bot)
        return self.answer


class InstalledDelegate:
    """Put `delegate` in place of the shipped view builder, then restore.

    `absent` removes the name instead, which is the failure the tab meets
    when the analyzer module carries no per-bot view.
    """

    def __init__(self, delegate=None, absent=False):
        self.delegate = delegate
        self.absent = absent
        self.module = None
        self.first = None

    def __enter__(self):
        from src.gui import market_inspector

        self.module = market_inspector
        self.first = market_inspector.build_per_bot_view
        if self.absent:
            del market_inspector.build_per_bot_view
        else:
            market_inspector.build_per_bot_view = self.delegate
        return self

    def __exit__(self, _kind, _value, _trace):
        self.module.build_per_bot_view = self.first
        return False


class CollectingHandler(logging.Handler):
    """Holds every line written through the logger it is attached to."""

    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class CapturedLog:
    """Every line the tab's own logger writes while the block runs.

    The logger is set to WARNING for the block and put back after, so the
    reading does not depend on a level another test left behind.
    """

    def __init__(self, name=surface.LOGGER_NAME):
        self.logger = logging.getLogger(name)
        self.handler = CollectingHandler()
        self.first_level = None

    def __enter__(self):
        self.first_level = self.logger.level
        self.logger.setLevel(logging.WARNING)
        self.logger.addHandler(self.handler)
        return self

    def __exit__(self, _kind, _value, _trace):
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self.first_level)
        return False

    @property
    def lines(self):
        return list(self.handler.lines)


HOST_ACCESSIBLE_NAME = "Live Bot Settings"


def host_class():
    """The window the tab lives in, holding only what the mixin declares."""
    from PySide6.QtWidgets import QWidget

    from src.gui.live_settings.market_inspector_tab import MarketInspectorTabMixin

    class Host(MarketInspectorTabMixin, QWidget):
        """The Live Bot Settings window, holding only the bot the tab reads."""

        def __init__(self, bot):
            super().__init__()
            self.setAccessibleName(HOST_ACCESSIBLE_NAME)
            self._bot = bot

    return Host


# The inputs. One scenario drives both sides.


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "O'Brien's venue said no"
REFUSAL_TEXT = "venue refused the order"

VIEW_MARK = "PER BOT VIEW"


def scenario(name, **named):
    """One driving set: the bot, and what the view builder does with it."""
    spec = {
        "name": name,
        "bot": "BTC/USD",
        "answers": True,
        "answers_none": False,
        "mark": VIEW_MARK,
        "error_type": "RuntimeError",
        "error_text": REFUSAL_TEXT,
        "base_exception": False,
    }
    spec.update(named)
    return spec


def failing(name, **named):
    """One driving set whose view builder throws instead of answering."""
    return scenario(name, answers=False, **named)


SCENARIOS = [
    scenario("happy"),
    scenario("view_is_none", answers_none=True),
    scenario("view_mark_is_empty", mark=""),
    scenario("view_mark_is_unicode", mark=UNICODE_TEXT),
    scenario("view_mark_is_two_hundred_characters", mark=LONG_TEXT),
    scenario("bot_is_none", bot=None),
    scenario("bot_is_zero", bot=0),
    scenario("bot_is_a_number", bot=12345),
    scenario("bot_is_negative", bot=-1),
    scenario("bot_is_text_where_a_bot_belongs", bot="not a bot"),
    scenario("bot_is_two_hundred_characters", bot=LONG_TEXT),
    scenario("bot_is_unicode", bot=UNICODE_TEXT),
    failing("view_builder_failed"),
    failing("import_failed", error_type="ImportError", error_text="no such name"),
    failing("value_failed", error_type="ValueError", error_text="bad reading"),
    failing("type_failed", error_type="TypeError", error_text="wrong kind"),
    failing("attribute_failed", error_type="AttributeError", error_text="no symbol"),
    failing("key_failed", error_type="KeyError", error_text="symbol"),
    failing("divided_by_zero", error_type="ZeroDivisionError", error_text="by zero"),
    failing("plain_exception", error_type="Exception", error_text="something"),
    failing("error_type_is_invented", error_type="AnalyzerGone", error_text="gone"),
    failing("error_type_in_wrong_capitals", error_type="runtimeerror"),
    failing("error_type_has_a_newline", error_type="Runtime\nError"),
    failing("error_text_is_empty", error_text=""),
    failing("error_text_is_zero", error_text=0),
    failing("error_text_is_negative", error_text=-1),
    failing("error_text_is_a_thousand_million", error_text=1e9),
    failing("error_text_is_one_billionth", error_text=1e-9),
    failing("error_text_is_infinite", error_text=math.inf),
    failing("error_text_is_minus_infinity", error_text=-math.inf),
    failing("error_text_is_not_a_number", error_text=math.nan),
    failing("error_text_is_a_number_where_text_belongs", error_text=12345),
    failing("error_text_is_a_number_written_as_text", error_text="12345"),
    failing("error_text_is_unicode", error_text=UNICODE_TEXT),
    failing("error_text_is_two_hundred_characters", error_text=LONG_TEXT),
    failing("error_text_is_markup", error_text=MARKUP_TEXT),
    failing("error_text_has_an_apostrophe", error_text=APOSTROPHE_TEXT),
    failing("error_text_has_a_newline", error_text=NEWLINE_TEXT),
    failing("error_text_in_wrong_capitals", error_text="VENUE REFUSED THE ORDER"),
    failing("error_text_is_none", error_text=None),
    failing("stopped_by_the_operator", base_exception=True),
    failing("asked_to_exit", base_exception=True, error_type="SystemExit"),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}

BASE_EXCEPTIONS = {
    "RuntimeError": KeyboardInterrupt,
    "SystemExit": SystemExit,
}


def spec_error(spec):
    """The exception the view builder throws for `spec`, or None."""
    if spec["answers"]:
        return None
    if spec["base_exception"]:
        return BASE_EXCEPTIONS[spec["error_type"]](spec["error_text"])
    return surface.error_from(spec["error_type"], spec["error_text"])


def old_delegate(spec):
    return QtDelegate(
        mark=spec["mark"],
        raises=spec_error(spec),
        answers_none=spec["answers_none"],
    )


def new_delegate(spec):
    view = None if spec["answers_none"] else spec["mark"]
    return SurfaceDelegate(view=view, raises=spec_error(spec))


def drive_old(spec, delegate=None):
    """Build the Qt tab with the scenario's view builder installed."""
    app()
    delegate = delegate or old_delegate(spec)
    host = host_class()(spec["bot"])
    with CapturedLog() as log, InstalledDelegate(delegate):
        tab = host._create_market_inspector_tab()
    return {"tab": tab, "delegate": delegate, "host": host, "log": log.lines}


def drive_new(spec, delegate=None):
    """Build the surface model with the scenario's view builder."""
    delegate = delegate or new_delegate(spec)
    model = surface.MarketInspectorTabModel(spec["bot"], delegate)
    model.build()
    return {"model": model, "delegate": delegate}


# Reading the two sides


def layout_order(layout):
    """The class of each item the layout holds, in the order it was added."""
    order = []
    for index in range(layout.count()):
        widget = layout.itemAt(index).widget()
        order.append(
            surface.FALLBACK_STRETCH if widget is None else type(widget).__name__
        )
    return order


def delegated_trace(view_mark, view_is_none):
    """The reading of a tab that handed back the builder's own view."""
    return {
        "delegated": True,
        "view_mark": view_mark,
        "view_is_none": view_is_none,
        "accessible_name": surface.NO_MESSAGE,
        "message": surface.NO_MESSAGE,
        "style_sheet": surface.NO_STYLE,
        "word_wrap": surface.NO_WORD_WRAP,
        "order": [],
    }


def qt_trace(driven):
    """Every value the built Qt tab can be asked for, as plain data."""
    tab = driven["tab"]
    reading = {"warnings": list(driven["log"])}
    if tab is driven["delegate"].answer:
        reading.update(
            delegated_trace(
                surface.NO_MESSAGE if tab is None else tab.text(), tab is None
            )
        )
        return reading
    outer = tab.layout()
    label = outer.itemAt(0).widget()
    reading.update(
        {
            "delegated": False,
            "view_mark": surface.NO_MESSAGE,
            "view_is_none": False,
            "accessible_name": tab.accessibleName(),
            "message": label.text(),
            "style_sheet": label.styleSheet(),
            "word_wrap": label.wordWrap(),
            "order": layout_order(outer),
        }
    )
    return reading


def surface_trace(driven):
    """The same values, read from the Qt-free view model."""
    model = driven["model"]
    payload = surface.build_view_model(model)
    reading = {"warnings": list(payload["warnings"])}
    if payload["view"] is driven["delegate"].answer:
        view = payload["view"]
        reading.update(
            delegated_trace(surface.NO_MESSAGE if view is None else view, view is None)
        )
        return reading
    reading.update(
        {
            "delegated": False,
            "view_mark": surface.NO_MESSAGE,
            "view_is_none": False,
            "accessible_name": payload["accessible_name"],
            "message": payload["message"],
            "style_sheet": payload["style_sheet"],
            "word_wrap": payload["word_wrap"],
            "order": list(payload["order"]),
        }
    )
    return reading


def headline(text: str) -> str:
    """The first line of an error message.

    A message that goes on to list every type it accepts would make a
    comparison of the whole text pass on wording alone.
    """
    lines = str(text).splitlines()
    return lines[0] if lines else ""


def outcome(work):
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except BaseException as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": headline(exc),
        }


def old_outcome(spec):
    return outcome(lambda: qt_trace(drive_old(spec)))


def new_outcome(spec):
    return outcome(lambda: surface_trace(drive_new(spec)))


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_tab(name):
    """A message, colour, log line, branch or delegation differs between them."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        assert new["message"] == old["message"], (name, old, new)
        return
    assert as_text(new["value"]) == as_text(old["value"]), name
    assert digest(new["value"]) == digest(old["value"]), name


REFUSING_SCENARIOS = ("stopped_by_the_operator", "asked_to_exit")


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
    assert len(answered) == len(SCENARIOS) - len(REFUSING_SCENARIOS)


@pytest.mark.parametrize("name", REFUSING_SCENARIOS)
def test_a_refused_input_names_the_same_error_on_both_sides(name):
    """One side swallowed a stop the other let through, or named another error."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["message"]) == (old["error"], old["message"])
    assert old["error"] in ("KeyboardInterrupt", "SystemExit")
    assert old["message"], name


def test_the_refusal_wording_is_read_one_line_at_a_time():
    """A refusal is compared whole, so its wording carries the check."""
    assert headline("only one line") == "only one line"
    assert headline("first line\nsecond line") == "first line"
    assert headline("") == ""
    spoken = old_outcome(BY_NAME["stopped_by_the_operator"])["message"]
    assert "\n" not in spoken
    assert spoken == REFUSAL_TEXT


DIFFERENT_INPUT_PAIR = ("happy", "view_builder_failed")


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    first, second = DIFFERENT_INPUT_PAIR
    one = old_outcome(BY_NAME[first])["value"]
    other = old_outcome(BY_NAME[second])["value"]
    assert one["delegated"] is True
    assert other["delegated"] is False
    assert one["message"] != other["message"]
    assert digest(one) != digest(other)
    assert digest(one) == digest(old_outcome(BY_NAME[first])["value"])
    assert len(digest(one)) == 64


def test_the_hash_tells_a_whole_number_from_a_decimal():
    """A whole number and a decimal of one value hash the same."""
    assert 12 == 12.0
    assert digest({"padding_px": 12}) != digest({"padding_px": 12.0})
    assert as_text(12) == "12"
    assert as_text(12.0) == "12.0"


def test_two_not_a_numbers_read_as_one_value_before_comparing():
    """Two not-a-numbers compared directly report a difference that is none."""
    assert math.nan != math.nan
    assert as_text(math.nan) == as_text(math.nan)
    assert digest({"reading": math.nan}) == digest({"reading": math.nan})
    assert digest({"reading": math.nan}) != digest({"reading": math.inf})


def test_a_swapped_order_is_reported_by_the_hash():
    """The label and the stretch changed places and the hash said nothing."""
    straight = {"order": [surface.FALLBACK_LABEL_CLASS, surface.FALLBACK_STRETCH]}
    swapped = {"order": [surface.FALLBACK_STRETCH, surface.FALLBACK_LABEL_CLASS]}
    assert sorted(straight["order"]) == sorted(swapped["order"])
    assert digest(straight) != digest(swapped)


@pytest.mark.parametrize(
    "name",
    ["happy", "view_builder_failed", "error_text_is_unicode", "view_is_none"],
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == 9, sorted(value)
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


# The log line, and the instrument that reads it


def test_the_log_reader_reports_a_line_the_tab_writes():
    """The log reader stays silent whatever the tab writes, so it sees nothing."""
    with CapturedLog() as log:
        assert log.lines == []
        logging.getLogger(surface.LOGGER_NAME).warning("a control line")
        assert log.lines == ["a control line"]
    logging.getLogger(surface.LOGGER_NAME).warning("after the block")
    assert log.lines == ["a control line"]


def test_the_fallback_writes_one_warning_on_both_sides():
    """The operator got no log line when the per-bot view could not be built."""
    spec = BY_NAME["view_builder_failed"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    assert old["warnings"] == new["warnings"]
    assert len(old["warnings"]) == 1, old["warnings"]
    assert old["warnings"][0] == surface.warning_line(spec_error(spec))
    assert REFUSAL_TEXT in old["warnings"][0]


def test_a_delegated_view_writes_no_warning_on_either_side():
    """A working per-bot view still wrote a failure line to the log."""
    old = qt_trace(drive_old(BY_NAME["happy"]))
    new = surface_trace(drive_new(BY_NAME["happy"]))
    assert old["warnings"] == new["warnings"] == []


# Step sequences


def test_a_second_build_carries_the_same_screen_on_both_sides():
    """The second paint of the tab shows something other than the first."""
    spec = BY_NAME["view_builder_failed"]
    app()
    delegate = old_delegate(spec)
    host = host_class()(spec["bot"])
    with CapturedLog() as log, InstalledDelegate(delegate):
        first_tab = host._create_market_inspector_tab()
        second_tab = host._create_market_inspector_tab()
    assert first_tab is not second_tab
    first_text = first_tab.layout().itemAt(0).widget().text()
    assert first_text == second_tab.layout().itemAt(0).widget().text()
    assert len(log.lines) == 2

    model = surface.MarketInspectorTabModel(spec["bot"], new_delegate(spec))
    model.build()
    one = [model.message, list(model.order), list(model.warnings)]
    model.build()
    assert one == [model.message, list(model.order), list(model.warnings)]
    assert model.message == first_text


def test_a_failure_after_a_working_view_clears_the_view_on_both_sides():
    """A view from an earlier paint stayed on the tab after a failure."""
    good = BY_NAME["happy"]
    bad = BY_NAME["view_builder_failed"]
    old_good = qt_trace(drive_old(good))
    old_bad = qt_trace(drive_old(bad))
    assert old_good["delegated"] is True
    assert old_bad["delegated"] is False

    model = surface.MarketInspectorTabModel(good["bot"], new_delegate(good))
    model.build()
    assert model.delegated is True
    assert model.view == VIEW_MARK
    model.source = new_delegate(bad)
    model.build()
    assert model.delegated is False
    assert model.view is surface.NO_VIEW
    assert model.message == old_bad["message"]
    assert [call[0] for call in model.calls].count(surface.BUILD_START) == 1


def test_a_working_view_after_a_failure_clears_the_message_on_both_sides():
    """A failure line from an earlier paint stayed under a working view."""
    bad = BY_NAME["view_builder_failed"]
    good = BY_NAME["happy"]
    model = surface.MarketInspectorTabModel(bad["bot"], new_delegate(bad))
    model.build()
    assert model.message
    assert model.order == [surface.FALLBACK_LABEL_CLASS, surface.FALLBACK_STRETCH]
    model.source = new_delegate(good)
    model.build()
    assert model.message == surface.NO_MESSAGE
    assert model.style_sheet == surface.NO_STYLE
    assert model.word_wrap is surface.NO_WORD_WRAP
    assert model.order == []
    assert model.warnings == []

    old_good = qt_trace(drive_old(good))
    assert old_good["message"] == surface.NO_MESSAGE
    assert old_good["order"] == []


def test_a_stop_after_a_working_view_leaves_the_last_screen_on_the_surface():
    """A stop mid-build left a half-filled screen the operator would read."""
    good = BY_NAME["happy"]
    model = surface.MarketInspectorTabModel(good["bot"], new_delegate(good))
    model.build()
    assert model.view == VIEW_MARK
    model.source = new_delegate(BY_NAME["stopped_by_the_operator"])
    with pytest.raises(KeyboardInterrupt):
        model.build()
    assert model.view is surface.NO_VIEW
    assert model.message == surface.NO_MESSAGE
    assert model.order == []
    assert model.calls == [[surface.BUILD_START]]


def test_the_bot_reaches_the_view_builder_unchanged_on_both_sides():
    """The tab handed the builder something other than the bot it holds."""
    for name in ("happy", "bot_is_none", "bot_is_a_number", "bot_is_unicode"):
        spec = BY_NAME[name]
        old = drive_old(spec)
        new = drive_new(spec)
        assert old["delegate"].seen == [spec["bot"]], name
        assert new["delegate"].seen == [spec["bot"]], name
        assert len(old["delegate"].seen) == len(new["delegate"].seen) == 1, name


# The import failure the renderer cannot manufacture


def spoken_error_text(message: str) -> str:
    """The error text inside a fallback message, with the headline removed."""
    tail = message[len(surface.FALLBACK_HEADLINE) :]
    return tail.split(surface.ERROR_SEPARATOR, 1)[1]


def test_an_absent_view_builder_paints_the_same_screen_on_both_sides():
    """The absent-name failure was never driven, so its screen is untested.

    The wording comes from the Python import machinery and names the
    module's own file, which the surface cannot manufacture. It is taken
    off the Qt side and driven into the surface, so one input reaches
    both sides.
    """
    app()
    host = host_class()("BTC/USD")
    with CapturedLog() as log, InstalledDelegate(absent=True):
        tab = host._create_market_inspector_tab()
    label = tab.layout().itemAt(0).widget()
    spoken = spoken_error_text(label.text())
    assert spoken.startswith("cannot import name 'build_per_bot_view'")

    delegate = SurfaceDelegate(raises=ImportError(spoken))
    model = surface.MarketInspectorTabModel("BTC/USD", delegate)
    model.build()
    assert model.message == label.text()
    assert model.word_wrap == label.wordWrap()
    assert model.warnings == log.lines
    assert len(log.lines) == 1
    assert_pictures_match(
        old_side=render_offscreen(tab, PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(sealed(surface.build_view_model(model))),
            PIXEL_SIZE,
        ),
        note="the view builder is absent from the analyzer module",
    )


def test_the_absent_builder_comparison_can_report_a_different_wording():
    """The comparison feeds one text to both sides, so it compares nothing."""
    first = SurfaceDelegate(raises=ImportError("cannot import name 'a'"))
    other = SurfaceDelegate(raises=ImportError("cannot import name 'b'"))
    one = surface.MarketInspectorTabModel("BTC/USD", first)
    two = surface.MarketInspectorTabModel("BTC/USD", other)
    one.build()
    two.build()
    assert one.message != two.message
    assert one.warnings != two.warnings
    assert digest(one.message) != digest(two.message)


# The enumeration: wiring, signals, classes, methods, timers, topics


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


def imported_names(tree) -> set:
    """Every name a module binds through an import."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                found.add(alias.asname or alias.name.split(".")[0])
    return found


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
                    (
                        "lambda"
                        if isinstance(target, ast.Lambda)
                        else dotted(
                            target.func if isinstance(target, ast.Call) else target
                        )
                    ),
                )
            )
    return sorted(found)


def timer_sites(path) -> list:
    """Every ``QTimer(`` construction in `path`, counted as a call."""
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


def built_classes(path, layouts: bool) -> list:
    """Every imported class `path` constructs, counted as a call.

    `layouts` picks the arrangers, whose names end in ``Layout``; False
    picks the screen elements the operator sees. A name is counted only
    where it is CONSTRUCTED, so an import line alone is not a build.
    """
    tree = parsed(path)
    names = imported_names(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        made = dotted(node.func)
        if made not in names or not made[:1].isupper() or made == "Signal":
            continue
        if made.endswith("Layout") is layouts:
            found.append(made)
    return sorted(found)


def source_functions(path) -> list:
    """Every function the source declares, nested ones included."""
    return sorted(
        node.name
        for node in ast.walk(parsed(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def declared_methods(holder) -> list:
    """Every real method `holder` declares. A signal is not a method."""
    from PySide6.QtCore import Signal

    return sorted(
        name
        for name, value in vars(holder).items()
        if callable(value)
        and not name.startswith("__")
        and not isinstance(value, Signal)
    )


def loose_methods(holder) -> list:
    """Every callable `holder` declares, signals counted as methods."""
    return sorted(
        name
        for name, value in vars(holder).items()
        if callable(value) and not name.startswith("__")
    )


def test_the_tab_connects_nothing_and_the_wiring_counter_can_report():
    """The tab wires an action the surface names none of.

    The tab wires nothing, so the counter is pointed at a neighbouring
    control that really does wire one. A counter returning nothing on
    both would be no measurement.
    """
    assert connect_sites(TAB_SOURCE) == []
    assert TAB_SOURCE.read_text(encoding="utf-8").count(".connect(") == CONNECT_TOTAL
    assert surface.ACTIONS == {}
    assert len(surface.ACTIONS) == CONNECT_TOTAL
    neighbour = connect_sites(WIRING_NEIGHBOUR)
    assert len(neighbour) == WIRING_NEIGHBOUR_CONNECT_TOTAL, neighbour
    assert neighbour[0][0] == "self.clicked"


def test_every_shipped_class_method_and_function_has_a_counterpart():
    """The shipped tab gained or lost a class, a method or a function."""
    from src.gui.live_settings import market_inspector_tab as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == ["MarketInspectorTabMixin"], classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    methods = declared_methods(shipped.MarketInspectorTabMixin)
    assert methods == ["_create_market_inspector_tab"], methods
    assert len(methods) == SHIPPED_METHOD_TOTAL
    functions = source_functions(TAB_SOURCE)
    assert functions == ["_create_market_inspector_tab"], functions
    assert len(functions) == SHIPPED_FUNCTION_TOTAL
    assert callable(surface.MarketInspectorTabModel.build)


def test_a_signal_is_not_counted_as_a_method():
    """A signal is callable, so a loose counter reads it as a method.

    The shipped class declares one method and one annotation. The counter
    is pointed at a neighbouring card that really does declare a signal,
    and must leave it out while the loose counter takes it in.
    """
    from PySide6.QtCore import Signal

    from src.gui.launcher import ModeCard
    from src.gui.live_settings.market_inspector_tab import MarketInspectorTabMixin

    assert isinstance(vars(ModeCard)["clicked"], Signal)
    assert callable(vars(ModeCard)["clicked"])
    assert "clicked" in loose_methods(ModeCard)
    assert "clicked" not in declared_methods(ModeCard)
    assert "mousePressEvent" in declared_methods(ModeCard)
    assert declared_methods(MarketInspectorTabMixin) == ["_create_market_inspector_tab"]
    assert loose_methods(MarketInspectorTabMixin) == ["_create_market_inspector_tab"]
    assert "_bot" not in vars(MarketInspectorTabMixin)
    assert MarketInspectorTabMixin.__annotations__ == {"_bot": "Any"}


SURFACE_CLASSES = {
    "MarketInspectorTabModel": "MarketInspectorTabMixin",
    "MarketInspectorSource": "the per-bot view builder the mixin imports",
}

SURFACE_MODEL_METHODS = ("__init__", "build")
SURFACE_SOURCE_METHODS = ("__init__", "build_per_bot_view")


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["MarketInspectorTabModel"] == "MarketInspectorTabMixin"
    model_methods = sorted(
        name
        for name, value in vars(surface.MarketInspectorTabModel).items()
        if callable(value) and (not name.startswith("__") or name == "__init__")
    )
    assert model_methods == sorted(SURFACE_MODEL_METHODS), model_methods
    source_methods = sorted(
        name
        for name, value in vars(surface.MarketInspectorSource).items()
        if callable(value) and (not name.startswith("__") or name == "__init__")
    )
    assert source_methods == sorted(SURFACE_SOURCE_METHODS), source_methods


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "InventedModel" not in SURFACE_CLASSES
    assert not hasattr(surface, "InventedModel")
    with pytest.raises(AttributeError):
        getattr(surface.MarketInspectorTabModel, "invented_method")


def test_the_tab_holds_no_timer_and_the_counter_can_report():
    """The tab runs a timer the surface declares no delay for.

    The shipped tab builds none, so the counter is pointed at the screen
    that really does build one. The counter reads a construction and not
    a name, so an import line alone is not a timer.
    """
    assert timer_sites(TAB_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    built = timer_sites(TIMER_NEIGHBOUR)
    assert len(built) == TIMER_NEIGHBOUR_BUILD_TOTAL, built
    named = TIMER_NEIGHBOUR.read_text(encoding="utf-8").count("QTimer")
    assert named > len(built), (named, built)


def test_the_tab_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The tab listens on a topic the surface names none of."""
    assert bus_sites(TAB_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) == BUS_NEIGHBOUR_TOPIC_TOTAL, neighbour
    assert neighbour == ["wire.created", "wire.removed"]


def test_the_tab_builds_two_screen_elements_and_the_counter_can_report():
    """The tab builds a control the surface's screen order names none of.

    The counter reads a construction, so an import line alone is not a
    build. It is proved on a neighbouring card that builds three.
    """
    built = built_classes(TAB_SOURCE, layouts=False)
    assert built == ["QLabel", "QWidget"], built
    assert len(built) == SHIPPED_ELEMENT_TOTAL
    arrangers = built_classes(TAB_SOURCE, layouts=True)
    assert arrangers == ["QVBoxLayout"], arrangers
    assert len(arrangers) == SHIPPED_LAYOUT_TOTAL
    neighbour = built_classes(ELEMENT_NEIGHBOUR, layouts=False)
    assert len(neighbour) == ELEMENT_NEIGHBOUR_BUILD_TOTAL, neighbour
    assert neighbour == ["PrivacyDot", "QLabel", "QLabel"]
    named = TAB_SOURCE.read_text(encoding="utf-8").count("QWidget")
    assert named > built.count("QWidget"), named


def test_the_neighbouring_controls_are_five_different_files():
    """Two controls read one file, so one of the two was never measured."""
    named = [
        WIRING_NEIGHBOUR,
        SIGNAL_NEIGHBOUR,
        TIMER_NEIGHBOUR,
        BUS_NEIGHBOUR,
        ELEMENT_NEIGHBOUR,
    ]
    assert len(set(named)) == len(named), named
    assert TIMER_NEIGHBOUR != REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
    assert timer_sites(REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py") == []
    assert timer_sites(TIMER_NEIGHBOUR) != []


# The completeness check


PAYLOAD_KEYS = {
    "ACCESSIBLE_NAME": "accessible_name",
    "ACTIONS": "actions",
    "BOT_ATTRIBUTE": "delegate.bot_attribute",
    "BUS_TOPICS": "bus_topics",
    "CALL_NAMES": "call_names",
    "DEFAULT_ERROR_TYPE": "defaults.error_type",
    "DELEGATE_FUNCTION": "delegate.function",
    "DELEGATE_MODULE": "delegate.module",
    "ERROR_SEPARATOR": "fallback.error_separator",
    "ERROR_TYPES": "error_types",
    "FALLBACK_COLOR": "fallback.color",
    "FALLBACK_DETAIL_FORMAT": "fallback.detail_format",
    "FALLBACK_HEADLINE_BREAKS": "fallback.headline_breaks",
    "FALLBACK_HEADLINE_TEXT": "fallback.headline_text",
    "FALLBACK_HEADLINE_WEIGHT": "fallback.headline_weight",
    "FALLBACK_HEADLINE": "fallback.headline",
    "FALLBACK_LABEL_CLASS": "fallback.label_class",
    "FALLBACK_MARGINS_SET": "fallback.margins_set",
    "FALLBACK_PADDING_PX": "fallback.padding_px",
    "FALLBACK_SPACING_SET": "fallback.spacing_set",
    "FALLBACK_STRETCH": "fallback.stretch",
    "FALLBACK_STYLE_FORMAT": "fallback.style_format",
    "FALLBACK_TEXT_FORMAT": "fallback.text_format",
    "FALLBACK_WORD_WRAP": "fallback.word_wrap",
    "LOGGER_NAME": "logger.name",
    "NO_MESSAGE": "texts.no_message",
    "NO_STYLE": "texts.no_style",
    "NO_VIEW": "defaults.no_view",
    "NO_WORD_WRAP": "defaults.no_word_wrap",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "WARNING_FORMAT": "logger.warning_format",
}

# The branch markers, each carried inside call_names.
CALL_CONSTANTS = (
    "BUILD_START",
    "BUILD_DELEGATED",
    "BUILD_VIEW",
    "BUILD_FAILED",
    "BUILD_WARNED",
    "BUILD_MESSAGE",
    "BUILD_LABEL",
    "BUILD_STRETCH",
    "BUILD_RETURN",
)

# The two values no snapshot key carries, each with the check that
# covers it. METHOD is the name the bridge registers under and
# PANE_MODEL is the tab state the bridge keeps between calls.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_market_inspector_method",
    "PANE_MODEL": "test_the_bridge_resets_the_tab_state_on_request",
}

STATE_ONLY_KEYS = {
    "delegated",
    "view",
    "message",
    "error_type",
    "error_text",
    "detail",
    "style_sheet",
    "word_wrap",
    "order",
    "warnings",
    "calls",
}

# A constant whose payload shape is not the constant itself.
PAYLOAD_READERS = {"ERROR_TYPES": sorted}


def at_path(payload, path):
    """The payload value one dotted path names."""
    found = payload
    for step in path.split("."):
        found = found[step]
    return found


def as_carried(name, value):
    """`value` in the shape the payload carries it."""
    reader = PAYLOAD_READERS.get(name)
    if reader is not None:
        return reader(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def surface_constants():
    """Every value the surface exports that is not a function or a class."""
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read.

    A comparison that reads some of the values passes whether the rest
    match or not. Every value is accounted for here: a snapshot path, one
    of the branch markers, or one of the two named with the check that
    covers it.
    """
    payload = surface.build_view_model(surface.MarketInspectorTabModel())
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payload, PAYLOAD_KEYS[name]) == as_carried(name, value), name
        elif name in CALL_CONSTANTS:
            assert value in payload["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(PAYLOAD_KEYS) == 32
    assert len(CALL_CONSTANTS) == 9
    assert len(NOT_IN_THE_SNAPSHOT) == 2


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.MarketInspectorTabModel())
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    assert len(payload) == PAYLOAD_KEY_TOTAL
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing.

    A value that reaches no snapshot path and no named exception must
    land in the unaccounted list, or the check above is empty.
    """
    payload = surface.build_view_model(surface.MarketInspectorTabModel())
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in CALL_CONSTANTS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "FALLBACK_COLOR" in surface_constants()
    assert "WARNING_FORMAT" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "MarketInspectorTabModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "fallback.invented")


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        seen.update(call[0] for call in drive_new(spec)["model"].calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    failed = drive_new(BY_NAME["view_builder_failed"])["model"]
    marks = [call[0] for call in failed.calls]
    assert marks.count(surface.BUILD_WARNED) == 1
    assert surface.BUILD_DELEGATED not in marks
    assert marks.index(surface.BUILD_LABEL) < marks.index(surface.BUILD_STRETCH)
    answered = drive_new(BY_NAME["happy"])["model"]
    answered_marks = [call[0] for call in answered.calls]
    assert surface.BUILD_WARNED not in answered_marks
    assert answered_marks.count(surface.BUILD_DELEGATED) == 1


# The surface carries its own values


class MovedTokens:
    """A token table whose colour is unlike any the design system holds."""

    FOLD_RATIO_AMBER = "#123456"


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_tab(monkeypatch):
    """The surface read its values off the tab it replaces.

    A surface that read the shipped tab would follow it, and the whole
    comparison above would be one side read twice. The shipped tab's
    token is moved and the surface must not move with it.
    """
    app()
    from src.gui.live_settings import market_inspector_tab as shipped

    first = shipped.ds
    spec = BY_NAME["view_builder_failed"]
    before = qt_trace(drive_old(spec))
    monkeypatch.setattr(shipped, "ds", MovedTokens)
    moved = qt_trace(drive_old(spec))
    assert MovedTokens.FOLD_RATIO_AMBER in moved["style_sheet"], moved["style_sheet"]
    assert MovedTokens.FOLD_RATIO_AMBER not in before["style_sheet"]
    new = surface_trace(drive_new(spec))
    assert MovedTokens.FOLD_RATIO_AMBER not in new["style_sheet"], new["style_sheet"]
    assert new["style_sheet"] == before["style_sheet"]
    assert new == before
    monkeypatch.undo()
    assert shipped.ds is first
    assert qt_trace(drive_old(spec))["style_sheet"] == before["style_sheet"]


def test_the_comparison_names_exactly_which_value_moved(monkeypatch):
    """The comparison reports that something moved without saying what."""
    app()
    from src.gui.live_settings import market_inspector_tab as shipped

    spec = BY_NAME["view_builder_failed"]
    before = qt_trace(drive_old(spec))
    monkeypatch.setattr(shipped, "ds", MovedTokens)
    moved = qt_trace(drive_old(spec))
    monkeypatch.undo()
    apart = sorted(key for key in before if before[key] != moved[key])
    assert apart == ["style_sheet"], apart
    assert before["message"] == moved["message"], "the message moved with the colour"
    assert before["warnings"] == moved["warnings"]
    assert moved["style_sheet"] == surface.fallback_style(
        color_hex=MovedTokens.FOLD_RATIO_AMBER
    )


def test_the_surface_does_not_follow_a_tab_that_builds_nothing(monkeypatch):
    """The surface asked the shipped tab to build its screen."""
    app()
    from src.gui.live_settings import market_inspector_tab as shipped

    first = shipped.MarketInspectorTabMixin._create_market_inspector_tab
    payload = surface.build_view_model(surface.MarketInspectorTabModel())
    monkeypatch.setattr(
        shipped.MarketInspectorTabMixin,
        "_create_market_inspector_tab",
        lambda self: None,
    )
    host = host_class()("BTC/USD")
    assert host._create_market_inspector_tab() is None
    again = surface.build_view_model(surface.MarketInspectorTabModel())
    assert again == payload
    assert again["fallback"]["color"] == surface.FALLBACK_COLOR
    assert again["logger"]["warning_format"] == surface.WARNING_FORMAT
    monkeypatch.undo()
    assert shipped.MarketInspectorTabMixin._create_market_inspector_tab is first
    with InstalledDelegate(old_delegate(BY_NAME["happy"])):
        assert host_class()("BTC/USD")._create_market_inspector_tab() is not None


def test_the_shipped_tab_writes_to_no_shared_table():
    """The shipped tab changed something every later test would inherit.

    The tab reads the design tokens and imports the analyzer module. It
    writes no module value of its own, so two builds leave the token
    table and both modules exactly as they were.
    """
    app()
    from src.gui import design_system, market_inspector
    from src.gui.live_settings import market_inspector_tab as shipped

    before_token = design_system.FOLD_RATIO_AMBER
    before_module = sorted(vars(shipped))
    before_analyzer = sorted(vars(market_inspector))
    before_builder = market_inspector.build_per_bot_view
    drive_old(BY_NAME["happy"])
    drive_old(BY_NAME["view_builder_failed"])
    assert design_system.FOLD_RATIO_AMBER == before_token
    assert sorted(vars(shipped)) == before_module
    assert sorted(vars(market_inspector)) == before_analyzer
    assert market_inspector.build_per_bot_view is before_builder
    assert shipped.ds is design_system


def test_the_surface_writes_to_no_shared_table():
    """The surface changed a module value every later test would inherit."""
    before = sorted(vars(surface))
    before_actions = dict(surface.ACTIONS)
    before_timers = dict(surface.TIMERS)
    before_errors = dict(surface.ERROR_TYPES)
    drive_new(BY_NAME["happy"])
    drive_new(BY_NAME["view_builder_failed"])
    assert sorted(vars(surface)) == before
    assert surface.ACTIONS == before_actions == {}
    assert surface.TIMERS == before_timers == {}
    assert surface.BUS_TOPICS == ()
    assert surface.ERROR_TYPES == before_errors


def test_the_installed_builder_is_put_back_after_every_drive():
    """A stand-in left in place would drive every later test in the run."""
    from src.gui import market_inspector

    first = market_inspector.build_per_bot_view
    stand_in = old_delegate(BY_NAME["happy"])
    with InstalledDelegate(stand_in):
        assert market_inspector.build_per_bot_view is stand_in
    assert market_inspector.build_per_bot_view is first
    with InstalledDelegate(absent=True):
        assert not hasattr(market_inspector, "build_per_bot_view")
    assert market_inspector.build_per_bot_view is first


# The colour and the message


def canonical(colour):
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    return QColor(colour).name().lower()


def test_the_fallback_colour_is_the_token_the_shipped_tab_reads():
    """The surface picked a colour the shipped tab never paints."""
    app()
    from src.gui import design_system

    assert surface.FALLBACK_COLOR == design_system.FOLD_RATIO_AMBER
    assert canonical(surface.FALLBACK_COLOR) == "#ff9900"
    written = canonical(surface.FALLBACK_COLOR)
    assert not written[1:3] == written[3:5] == written[5:7], written
    assert canonical(surface.FALLBACK_COLOR) != canonical("#99ff00")
    assert canonical(surface.FALLBACK_COLOR) != canonical("#0099ff")


def test_the_style_sheet_names_the_colour_and_the_padding():
    """The failure line lost its colour or its padding."""
    assert surface.fallback_style() == "color: #ff9900; padding: 12px;"
    assert surface.fallback_style(color_hex="#000000") != surface.fallback_style()
    assert surface.fallback_style(padding_px=13) != surface.fallback_style()
    assert str(surface.FALLBACK_PADDING_PX) in surface.fallback_style()


@pytest.mark.parametrize(
    "error_type,error_text,expected",
    [
        ("RuntimeError", "boom", "RuntimeError: boom"),
        ("ImportError", "", "ImportError: "),
        ("ValueError", 0, "ValueError: 0"),
        ("ValueError", 12, "ValueError: 12"),
        ("ValueError", 12.0, "ValueError: 12.0"),
        ("ValueError", math.inf, "ValueError: inf"),
        ("ValueError", -math.inf, "ValueError: -inf"),
        ("ValueError", math.nan, "ValueError: nan"),
    ],
)
def test_the_failure_line_names_the_error_and_its_text(
    error_type, error_text, expected
):
    """The failure line dropped the error name or its reading."""
    built = surface.fallback_text(error_type, error_text)
    assert built == surface.FALLBACK_HEADLINE + expected
    assert built.startswith(surface.FALLBACK_HEADLINE)


def test_the_warning_line_carries_the_error_text_alone():
    """The log line named something other than the failure."""
    assert surface.warning_line(RuntimeError("boom")) == (
        "Market Inspector per-bot view unavailable: boom"
    )
    assert surface.warning_line(KeyError("symbol")) == (
        "Market Inspector per-bot view unavailable: 'symbol'"
    )
    assert surface.warning_line(RuntimeError("boom")) != surface.warning_line(
        RuntimeError("bang")
    )


def test_an_invented_error_name_reaches_the_screen_under_its_own_name():
    """A failure the renderer reports arrived under another name."""
    built = surface.error_from("AnalyzerGone", "the scan never ran")
    assert type(built).__name__ == "AnalyzerGone"
    assert isinstance(built, Exception)
    assert str(built) == "the scan never ran"
    known = surface.error_from("ValueError", "bad reading")
    assert type(known) is ValueError
    assert surface.error_from("valueerror", "x").__class__ is not ValueError


# The pictures


PICTURE_SCENARIOS = [
    "view_builder_failed",
    "error_text_is_empty",
    "error_text_is_unicode",
    "error_text_is_two_hundred_characters",
    "error_text_is_markup",
    "error_text_has_a_newline",
    "import_failed",
]


def model_payload(spec):
    """The view model after the same driving, stamped."""
    return sealed(surface.build_view_model(drive_new(spec)["model"]))


def widget_painted_by_the_tab(spec):
    """The screen the shipped Qt mixin builds, after the same driving."""
    return drive_old(spec)["tab"]


def widget_painted_by_the_model(payload):
    """A screen built only from the payload, never from the shipped mixin.

    A payload the caller changed after it came off the surface is refused.
    """
    payload = unaltered(payload)
    from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

    app()
    screen = QWidget()
    screen.setAccessibleName(payload["accessible_name"])
    outer = QVBoxLayout(screen)
    for element in payload["order"]:
        if element == payload["fallback"]["stretch"]:
            outer.addStretch()
            continue
        label = QLabel(payload["message"])
        label.setStyleSheet(payload["style_sheet"])
        label.setWordWrap(payload["word_wrap"])
        outer.addWidget(label)
    return screen


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different screen than the shipped mixin."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(widget_painted_by_the_tab(BY_NAME[name]), PIXEL_SIZE),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
        note=note,
    )


PICTURE_DIFFERENT_PAIR = ("view_builder_failed", "error_text_is_two_hundred_characters")


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real failures, one driven into each side. One error text is 23
    characters and the other 200, so the two end in different states
    whatever fonts the host holds.
    """
    app()
    first, second = PICTURE_DIFFERENT_PAIR
    one = qt_trace(drive_old(BY_NAME[first]))
    other = surface_trace(drive_new(BY_NAME[second]))
    assert one["message"] != other["message"]
    assert len(other["message"]) - len(one["message"]) == len(LONG_TEXT) - len(
        REFUSAL_TEXT
    )
    assert_pictures_differ(
        old_side=render_offscreen(
            widget_painted_by_the_tab(BY_NAME[first]), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[second])), PIXEL_SIZE
        ),
        note="a short failure line against a two-hundred character one",
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_screen_shows_more_than_one_colour(name):
    """The two sides matched because the screen painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    for image in (
        render_offscreen(widget_painted_by_the_tab(BY_NAME[name]), PIXEL_SIZE),
        render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
    ):
        assert image.width() > 0 and image.height() > 0, name
        seen = set()
        for x in range(0, image.width(), 5):
            for y in range(0, image.height(), 5):
                seen.add(QColor(image.pixelColor(x, y)).name())
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload(BY_NAME["view_builder_failed"])
    payload["message"] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(
            surface.build_view_model(surface.MarketInspectorTabModel())
        )


def test_the_delegated_screen_is_the_builders_own_and_this_tab_paints_none():
    """The tab painted a screen of its own over a working per-bot view."""
    old = qt_trace(drive_old(BY_NAME["happy"]))
    new = surface_trace(drive_new(BY_NAME["happy"]))
    assert old["order"] == new["order"] == []
    assert old["message"] == new["message"] == surface.NO_MESSAGE
    assert old["style_sheet"] == new["style_sheet"] == surface.NO_STYLE
    failed = qt_trace(drive_old(BY_NAME["view_builder_failed"]))
    assert failed["order"] == [surface.FALLBACK_LABEL_CLASS, surface.FALLBACK_STRETCH]


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on.

    With no font database every family resolves to a box advancing one em
    per character, so two strings of equal length need equal width. With
    a font database the glyphs decide the width. Both answers are handled
    here and the file is run both ways.
    """
    app()
    assert len(NARROW_LABEL) == len(WIDE_LABEL)
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert narrow != wide, "the host reports fonts and every glyph has one width"
    else:
        assert narrow == wide, "the host reports no fonts and the glyphs differ"


@skip_unless_no_fonts
def test_two_equal_length_failure_lines_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length lines still differ."""
    app()
    assert app_font_advance_px("RuntimeError") == app_font_advance_px("ImportErrorX")


@skip_unless_real_fonts
def test_the_two_marker_strings_measure_apart_with_fonts():
    """The glyphs decide their own width, and the marker pair measures alike."""
    app()
    assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)


# What a picture cannot see, read off both sides instead


def test_the_word_wrap_is_read_off_both_sides():
    """The failure line wraps on one side and runs off the tab on the other."""
    app()
    for name in ("view_builder_failed", "error_text_is_two_hundred_characters"):
        old = qt_trace(drive_old(BY_NAME[name]))
        new = surface_trace(drive_new(BY_NAME[name]))
        assert old["word_wrap"] == new["word_wrap"] is surface.FALLBACK_WORD_WRAP, name


def test_the_accessible_name_is_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report."""
    app()
    spec = BY_NAME["view_builder_failed"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    assert new["accessible_name"] == old["accessible_name"] == surface.ACCESSIBLE_NAME


def box_of(layout) -> list:
    """One layout's four margins, as plain numbers."""
    margins = layout.contentsMargins()
    return [margins.left(), margins.top(), margins.right(), margins.bottom()]


def untouched_layout_reading():
    """The margins and spacing a fresh column layout starts with.

    The holder widget is kept alive for the read: a layout whose owner is
    collected raises rather than reporting.
    """
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    holder = QWidget()
    plain = QVBoxLayout(holder)
    reading = (box_of(plain), plain.spacing())
    assert holder.layout() is plain
    return reading


def test_the_fallback_layout_sets_no_spacing_and_no_margins_on_either_side():
    """The failure screen set its own spacing on one side and not the other."""
    app()
    untouched_box, untouched_spacing = untouched_layout_reading()
    tab = widget_painted_by_the_tab(BY_NAME["view_builder_failed"])
    built = widget_painted_by_the_model(model_payload(BY_NAME["view_builder_failed"]))
    for layout in (tab.layout(), built.layout()):
        assert box_of(layout) == untouched_box
        assert layout.spacing() == untouched_spacing
    assert surface.FALLBACK_SPACING_SET is False
    assert surface.FALLBACK_MARGINS_SET is False


def test_the_layout_reader_reports_a_spacing_and_a_margin_that_moved():
    """The layout reader returns one answer whatever the layout holds.

    A fresh column layout on this host already carries the numbers the
    fallback screen leaves alone, so an unset layout cannot be told from
    a set one by those numbers. The reader is proved on a layout given a
    spacing and margins of its own instead.
    """
    app()
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    untouched_box, untouched_spacing = untouched_layout_reading()
    holder = QWidget()
    moved = QVBoxLayout(holder)
    moved.setSpacing(untouched_spacing + 7)
    moved.setContentsMargins(3, 5, 7, 11)
    assert holder.layout() is moved
    assert moved.spacing() == untouched_spacing + 7
    assert box_of(moved) == [3, 5, 7, 11]
    assert box_of(moved) != untouched_box


def test_the_layout_order_is_read_off_both_sides():
    """The stretch that holds the line at the top sits somewhere else."""
    app()
    spec = BY_NAME["view_builder_failed"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(drive_new(spec))
    assert old["order"] == new["order"] == ["QLabel", "stretch"]


# The bridge


@pytest.fixture
def fresh_pane_model():
    """Put the tab state the bridge keeps back exactly as it was found.

    A brand-new model is handed to the test, never a cleared one: a
    cleared model keeps any field the clearing does not name.
    """
    first = surface.PANE_MODEL
    surface.PANE_MODEL = surface.MarketInspectorTabModel()
    yield
    surface.PANE_MODEL = first


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


BRIDGE_FAILURE = {
    "reset": True,
    "bot": "BTC/USD",
    "error": {"type": "RuntimeError", "text": REFUSAL_TEXT},
}


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_registers_the_market_inspector_method():
    """The renderer cannot reach the Market Inspector tab over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "market_inspector_tab.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["fallback"]["color"] == surface.FALLBACK_COLOR
    assert result["delegate"]["function"] == surface.DELEGATE_FUNCTION


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_resets_the_tab_state_on_request():
    """The tab state the bridge keeps was never cleared."""
    filled = bridge_answer(BRIDGE_FAILURE)["result"]
    assert filled["delegated"] is False
    assert filled["order"] == ["QLabel", "stretch"]
    assert filled["message"].endswith("RuntimeError: " + REFUSAL_TEXT)
    kept = bridge_answer({})["result"]
    assert kept["message"] == filled["message"]
    assert kept["order"] == filled["order"]
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["message"] == surface.NO_MESSAGE
    assert cleared["order"] == []
    assert cleared["warnings"] == []
    assert cleared["calls"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_delegates_when_the_view_builder_answers():
    """A working per-bot view was reported as a failure."""
    result = bridge_answer({"reset": True, "bot": "BTC/USD", "view": VIEW_MARK})[
        "result"
    ]
    assert result["delegated"] is True
    assert result["view"] == VIEW_MARK
    assert result["message"] == surface.NO_MESSAGE
    assert result["warnings"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer(BRIDGE_FAILURE)
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["order"] == ["QLabel", "stretch"]
    assert encoded["result"]["warnings"] == [
        "Market Inspector per-bot view unavailable: " + REFUSAL_TEXT
    ]


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_reports_a_request_it_cannot_use():
    """A bad request ended the session instead of answering with an error."""
    answer = bridge_answer({"reset": True, "error": "not a mapping"})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "AttributeError"
    assert answer["error"]["message"]


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'market_inspector_tab.state', 'params':"
    " {'reset': True, 'bot': 'BTC/USD', 'error': {'type': 'RuntimeError',"
    " 'text': 'venue refused the order'}}}),"
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
    """Reaching the Market Inspector tab pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["delegated"] is False
    assert result["message"] == (
        "<b>Market Inspector unavailable.</b><br><br>"
        "RuntimeError: venue refused the order"
    )
    assert result["style_sheet"] == "color: #ff9900; padding: 12px;"
    assert result["word_wrap"] is True
    assert result["order"] == ["QLabel", "stretch"]
    assert result["warnings"] == [
        "Market Inspector per-bot view unavailable: venue refused the order"
    ]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
