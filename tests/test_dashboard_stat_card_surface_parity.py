"""The Qt header stat card and the Qt-free surface, side by side.

A failure means the view model describes a different caption, a different
amount, a different colour, a different privacy dot, a different tooltip,
a different cursor, a different layout number, a different signal or a
different branch than ``StatCard`` builds on the same steps.
"""

from __future__ import annotations

import ast
import functools
import hashlib
import inspect
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import dashboard_stat_card_surface as surface
from tests.fixtures.host_fonts import (
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
WIDGET_SOURCE = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (220, 70)

CONNECT_TOTAL = 0
SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 6
SHIPPED_SIGNAL_TOTAL = 1
PAYLOAD_KEY_TOTAL = 18
CONSTANT_TOTAL = 51
TRACE_KEY_TOTAL = 12
OUTER_ITEM_TOTAL = 2
LABEL_ROW_ITEM_TOTAL = 3

FIELD_ID = "kpi.locked"
OTHER_FIELD_ID = "kpi.mature"
UNKNOWN_FIELD_ID = "kpi.invented"
KPI_FIELD_IDS = ("kpi.spendable", "kpi.realised", FIELD_ID, OTHER_FIELD_ID, "kpi.exch")
OFF_REGISTER_FIELD_IDS = ("", UNKNOWN_FIELD_ID)

# The test owns these maps so neither side is named from the other.
ALIGN_NAMES = {0: "", 4: "hcenter", 36: "hcenter|top", 68: "hcenter|bottom"}
PROPERTY_NAMES = ("muted", "heading")
BUTTON_NAMES = {"left": "LeftButton", "right": "RightButton"}

OMITTED = object()


class NoText:
    """A value that refuses to become text, the way a broken object does."""

    def __str__(self) -> str:
        raise ValueError("this value has no text")


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


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


# The privacy registry is process-wide. Both sides read it, so every
# test is given a fresh one and the process singleton is put back.


@pytest.fixture(autouse=True)
def own_privacy_registry(tmp_path, monkeypatch):
    """Give this test its own registry and restore the process one after.

    ``get_privacy_mask_registry`` returns one object for the whole
    process, both sides reach it through that one function, and a dot
    click writes to it, so a mask a test leaves set would decide what a
    later test renders. Autosave is off and the path is a temporary one,
    so no test writes a settings file.
    """
    from src.core import privacy_mask_registry as registry_module

    fresh = registry_module.PrivacyMaskRegistry(
        settings_path=tmp_path / "settings.json", autosave=False
    )
    monkeypatch.setattr(registry_module, "_SINGLETON", fresh)
    fresh.set_all(False)
    yield fresh
    fresh.set_all(False)


def registry():
    """The registry both sides read, through the accessor both sides call."""
    from src.core.privacy_mask_registry import get_privacy_mask_registry

    return get_privacy_mask_registry()


def set_masks(field_ids) -> None:
    """Hide exactly `field_ids` and reveal every other field in play.

    ``set_all`` touches only the registry's own canonical ids, so a field
    the card was driven with that the registry does not know keeps
    whatever a previous drive left on it. Both drives must start from one
    state or the second one reads the first one's leftovers.
    """
    live = registry()
    live.set_all(False)
    for field_id in OFF_REGISTER_FIELD_IDS:
        live.set_masked(field_id, False)
    for field_id in field_ids:
        live.set_masked(field_id, True)


# The inputs. One scenario drives both sides.

LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "Ekthelius' venues"
WRONG_CAPITALS_TEXT = "cOINBASE"
BASE_TOOLTIP = "Error count across all bots since last reset."
CLICK_SUFFIX = "Click to open the error log."


def scenario(name, label="Scrummed", value="$0.00", steps=()):
    return {"name": name, "label": label, "value": value, "steps": tuple(steps)}


SCENARIOS = [
    scenario("built_only"),
    scenario("the_value_is_left_out", value=OMITTED),
    scenario("empty_label_and_empty_value", label="", value=""),
    scenario("no_label_and_no_value", label=None, value=None),
    scenario("zero", steps=[("value", 0)]),
    scenario("negative", steps=[("value", -500.25)]),
    scenario("a_thousand_million", steps=[("value", 1_000_000_000)]),
    scenario("one_billionth", steps=[("value", 1e-9)]),
    scenario("infinity", steps=[("value", math.inf)]),
    scenario("minus_infinity", steps=[("value", -math.inf)]),
    scenario("not_a_number", steps=[("value", math.nan)]),
    scenario(
        "a_whole_number_and_the_same_decimal", steps=[("value", 12), ("value", 12.0)]
    ),
    scenario("a_flag_where_a_number_belongs", steps=[("value", True)]),
    scenario("nothing_where_a_number_belongs", steps=[("value", None)]),
    scenario("text_where_a_number_belongs", steps=[("value", "lots")]),
    scenario("a_number_where_text_belongs", steps=[("value", 42)]),
    scenario("unicode", label=UNICODE_TEXT, steps=[("value", UNICODE_TEXT)]),
    scenario("two_hundred_characters", label=LONG_TEXT, steps=[("value", LONG_TEXT)]),
    scenario("markup", label=MARKUP_TEXT, steps=[("value", MARKUP_TEXT)]),
    scenario(
        "an_apostrophe", label=APOSTROPHE_TEXT, steps=[("value", APOSTROPHE_TEXT)]
    ),
    scenario("wrong_capitals", label=WRONG_CAPITALS_TEXT),
    scenario("a_newline_in_the_label", label=NEWLINE_TEXT),
    scenario("a_dot_attached", steps=[("dot", FIELD_ID)]),
    scenario(
        "a_dot_attached_while_masked",
        steps=[("mask", (FIELD_ID,)), ("dot", FIELD_ID)],
    ),
    scenario(
        "a_dot_attached_twice_keeps_the_first_field",
        steps=[("dot", FIELD_ID), ("dot", OTHER_FIELD_ID)],
    ),
    scenario(
        "a_dot_attached_to_a_card_built_with_no_value",
        label="Bots",
        value=None,
        steps=[("dot", FIELD_ID)],
    ),
    scenario("a_dot_attached_to_an_empty_field", steps=[("dot", "")]),
    scenario(
        "a_dot_attached_to_an_empty_field_while_masked",
        steps=[("mask", ("",)), ("dot", "")],
    ),
    scenario(
        "a_dot_attached_to_a_field_the_mask_helper_refuses",
        steps=[("mask", (UNKNOWN_FIELD_ID,)), ("dot", UNKNOWN_FIELD_ID)],
    ),
    scenario("a_value_set_after_a_dot", steps=[("dot", FIELD_ID), ("value", 1234.56)]),
    scenario(
        "a_value_set_after_a_dot_while_masked",
        steps=[("mask", (FIELD_ID,)), ("dot", FIELD_ID), ("value", 1234.56)],
    ),
    scenario(
        "a_mask_set_after_the_amount_was_rendered",
        steps=[("dot", FIELD_ID), ("value", 1234.56), ("mask", (FIELD_ID,))],
    ),
    scenario(
        "a_mask_set_after_the_amount_then_the_dot_refreshed",
        steps=[
            ("dot", FIELD_ID),
            ("value", 1234.56),
            ("mask", (FIELD_ID,)),
            ("refresh",),
        ],
    ),
    scenario("a_refresh_with_no_dot", steps=[("refresh",)]),
    scenario(
        "a_dot_clicked",
        steps=[("dot", FIELD_ID), ("value", 99.5), ("click_dot",)],
    ),
    scenario(
        "a_dot_clicked_twice",
        steps=[("dot", FIELD_ID), ("value", 99.5), ("click_dot",), ("click_dot",)],
    ),
    scenario(
        "a_dot_clicked_on_an_empty_field",
        steps=[("dot", ""), ("value", 99.5), ("click_dot",)],
    ),
    scenario("clickable_on", steps=[("clickable", True, "")]),
    scenario(
        "clickable_on_with_a_suffix",
        steps=[("tooltip", BASE_TOOLTIP), ("clickable", True, CLICK_SUFFIX)],
    ),
    scenario(
        "clickable_on_with_the_same_suffix_twice",
        steps=[
            ("tooltip", BASE_TOOLTIP),
            ("clickable", True, CLICK_SUFFIX),
            ("clickable", True, CLICK_SUFFIX),
        ],
    ),
    scenario(
        "clickable_on_with_a_suffix_and_no_tooltip",
        steps=[("clickable", True, CLICK_SUFFIX)],
    ),
    scenario(
        "clickable_then_off",
        steps=[("clickable", True, CLICK_SUFFIX), ("clickable", False, "")],
    ),
    scenario("clickable_off_first", steps=[("clickable", False, "")]),
    scenario(
        "a_unicode_suffix",
        steps=[("tooltip", BASE_TOOLTIP), ("clickable", True, UNICODE_TEXT)],
    ),
    scenario(
        "a_newline_suffix",
        steps=[("tooltip", BASE_TOOLTIP), ("clickable", True, NEWLINE_TEXT)],
    ),
    scenario(
        "a_markup_suffix",
        steps=[("tooltip", BASE_TOOLTIP), ("clickable", True, MARKUP_TEXT)],
    ),
    scenario(
        "a_two_hundred_character_suffix",
        steps=[("tooltip", BASE_TOOLTIP), ("clickable", True, LONG_TEXT)],
    ),
    scenario(
        "a_press_on_a_clickable_card",
        steps=[("clickable", True, ""), ("press", "left")],
    ),
    scenario("a_press_on_a_card_that_is_not_clickable", steps=[("press", "left")]),
    scenario(
        "a_right_press_on_a_clickable_card",
        steps=[("clickable", True, ""), ("press", "right")],
    ),
    scenario(
        "a_press_after_clicking_is_turned_off",
        steps=[
            ("clickable", True, ""),
            ("press", "left"),
            ("clickable", False, ""),
            ("press", "left"),
        ],
    ),
    scenario(
        "the_whole_card",
        label="Errors",
        value="0",
        steps=[
            ("tooltip", BASE_TOOLTIP),
            ("clickable", True, CLICK_SUFFIX),
            ("dot", FIELD_ID),
            ("value", 17),
            ("press", "left"),
            ("mask", (FIELD_ID,)),
            ("refresh",),
            ("click_dot",),
            ("press", "right"),
            ("value", 18),
        ],
    ),
    scenario("a_number_where_the_label_belongs", label=42),
    scenario("a_decimal_where_the_value_belongs", value=1.5),
    scenario("a_flag_where_the_label_belongs", label=True),
    scenario("a_number_where_the_suffix_belongs", steps=[("clickable", True, 42)]),
    scenario("a_value_that_refuses_to_become_text", steps=[("value", NoText())]),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}

# Refusals both sides word with the same Python message.
SHARED_WORDING = (
    "a_number_where_the_suffix_belongs",
    "a_value_that_refuses_to_become_text",
)

# Refusals each side words in its own way, both naming the type given.
TYPE_NAMED_WORDING = (
    "a_number_where_the_label_belongs",
    "a_decimal_where_the_value_belongs",
    "a_flag_where_the_label_belongs",
)

REFUSING_SCENARIOS = SHARED_WORDING + TYPE_NAMED_WORDING


# Driving the two sides


def press_event(button_name):
    """One real mouse-press event carrying the named button."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    button = getattr(Qt, BUTTON_NAMES[button_name])
    where = QPointF(1.0, 1.0)
    return QMouseEvent(
        QEvent.Type.MouseButtonPress, where, where, button, button, Qt.NoModifier
    )


def drive_old(spec):
    """The shipped Qt card, built and driven by one scenario."""
    from src.gui.widgets.dashboard_stat_card import StatCard

    app()
    set_masks(())
    if spec["value"] is OMITTED:
        card = StatCard(spec["label"])
    else:
        card = StatCard(spec["label"], spec["value"])
    clicks = []
    card.clicked.connect(lambda: clicks.append(1))
    for step in spec["steps"]:
        name = step[0]
        if name == "tooltip":
            card.setToolTip(step[1])
        elif name == "value":
            card.set_value(step[1])
        elif name == "dot":
            card.attach_privacy_dot(step[1])
        elif name == "refresh":
            card.refresh_privacy_dot()
        elif name == "click_dot":
            card._privacy_dot.click()
        elif name == "clickable":
            card.set_clickable(step[1], step[2])
        elif name == "press":
            card.mousePressEvent(press_event(step[1]))
        elif name == "mask":
            set_masks(step[1])
        else:
            raise AssertionError(f"unknown step {name!r}")
    return card, len(clicks)


def drive_new(spec):
    """The Qt-free model, built and driven by the same scenario."""
    set_masks(())
    if spec["value"] is OMITTED:
        card = surface.StatCardModel(spec["label"])
    else:
        card = surface.StatCardModel(spec["label"], spec["value"])
    for step in spec["steps"]:
        name = step[0]
        if name == "tooltip":
            card.tooltip = step[1]
        elif name == "value":
            card.set_value(step[1])
        elif name == "dot":
            card.attach_privacy_dot(step[1])
        elif name == "refresh":
            card.refresh_privacy_dot()
        elif name == "click_dot":
            flip_registry(card.dot["field_id"])
            card.dot_clicked()
        elif name == "clickable":
            card.set_clickable(step[1], step[2])
        elif name == "press":
            card.mouse_pressed(step[1])
        elif name == "mask":
            set_masks(step[1])
        else:
            raise AssertionError(f"unknown step {name!r}")
    return card


def flip_registry(field_id) -> None:
    """What the dot widget does to the registry when it is clicked.

    The flip belongs to the dot, not to the card, so the model side is
    given the same flip the shipped dot performs before it calls back.
    """
    live = registry()
    live.set_masked(field_id, not live.is_masked(field_id))


# Reading the two sides


def property_name(widget) -> str:
    """The one declared property this widget carries as true."""
    carried = [name for name in PROPERTY_NAMES if widget.property(name) is True]
    assert len(carried) == 1, (carried, widget.text())
    return carried[0]


def outer_item_from_qt(item):
    """One item of the card column, named by what the card put there."""
    if item.layout() is not None:
        return {"kind": "layout", "role": "label_row"}
    widget = item.widget()
    if type(widget).__name__ == "PrivacyDot":
        return {
            "kind": "widget",
            "role": "dot",
            "align": ALIGN_NAMES[int(item.alignment())],
        }
    return {"kind": "widget", "role": "value"}


def row_item_from_qt(item):
    """One item of the caption row, named by what the card put there."""
    if item.widget() is None:
        return {"kind": "stretch"}
    return {"kind": "widget", "role": "label"}


def dot_from_qt(dot):
    """The privacy dot, read off the widget the card attached."""
    return {
        "field_id": dot.field_id(),
        "masked": dot.text() == surface.DOT_MASKED_GLYPH,
        "text": dot.text(),
        "tooltip": dot.toolTip(),
        "style_sheet": dot.styleSheet(),
        "align": ALIGN_NAMES[4],
    }


def qt_signal_names() -> list:
    """Every signal the shipped class declares, read off the class object."""
    from PySide6.QtCore import Signal

    from src.gui.widgets.dashboard_stat_card import StatCard

    return sorted(
        name for name, value in vars(StatCard).items() if isinstance(value, Signal)
    )


def qt_default_value() -> str:
    """The amount the shipped card shows when a caller gives none."""
    from src.gui.widgets.dashboard_stat_card import StatCard

    return inspect.signature(StatCard.__init__).parameters["value"].default


def qt_trace(card, clicks):
    """Everything the shipped card shows, read off its own widgets."""
    outer = card.layout()
    row = outer.itemAt(0).layout()
    label = row.itemAt(1).widget()
    value = outer.itemAt(1).widget()
    dot = outer.itemAt(2).widget() if outer.count() > 2 else None
    return {
        "frame": {
            "style_sheet": card.styleSheet(),
            "frame_shape": card.frameShape().name,
        },
        "layout": {
            "margins_px": list(outer.getContentsMargins()),
            "spacing_px": outer.spacing(),
            "label_row_margins_px": list(row.getContentsMargins()),
            "label_row_spacing_px": row.spacing(),
        },
        "label": {
            "text": label.text(),
            "style_sheet": label.styleSheet(),
            "align": ALIGN_NAMES[int(label.alignment())],
            "property": property_name(label),
        },
        "value": {
            "text": value.text(),
            "style_sheet": value.styleSheet(),
            "align": ALIGN_NAMES[int(value.alignment())],
            "property": property_name(value),
            "default_text": qt_default_value(),
        },
        "dot": None if dot is None else dot_from_qt(dot),
        "items": [outer_item_from_qt(outer.itemAt(i)) for i in range(outer.count())],
        "label_row_items": [
            row_item_from_qt(row.itemAt(i)) for i in range(row.count())
        ],
        "tooltip": card.toolTip(),
        "clickable": {
            "is_clickable": card._is_clickable,
            "cursor": card.cursor().shape().name,
        },
        "privacy": {
            "field_id": None if dot is None else dot.field_id(),
            "raw_value": card._raw_value,
        },
        "clicks": clicks,
        "signals": qt_signal_names(),
    }


def surface_trace(payload_dict):
    """The same reading, taken off the view model alone."""
    layout = payload_dict["layout"]
    return {
        "frame": payload_dict["frame"],
        "layout": {
            "margins_px": layout["margins_px"],
            "spacing_px": layout["spacing_px"],
            "label_row_margins_px": layout["label_row_margins_px"],
            "label_row_spacing_px": layout["label_row_spacing_px"],
        },
        "label": payload_dict["label"],
        "value": payload_dict["value"],
        "dot": payload_dict["dot"],
        "items": payload_dict["items"],
        "label_row_items": payload_dict["label_row_items"],
        "tooltip": payload_dict["tooltip"],
        "clickable": {
            "is_clickable": payload_dict["clickable"]["is_clickable"],
            "cursor": payload_dict["clickable"]["cursor"],
        },
        "privacy": payload_dict["privacy"],
        "clicks": payload_dict["clicks"],
        "signals": payload_dict["signals"],
    }


def outcome(work):
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": str(exc),
        }


def old_outcome(spec):
    return outcome(lambda: qt_trace(*drive_old(spec)))


def new_outcome(spec):
    return outcome(lambda: surface_trace(surface.build_view_model(drive_new(spec))))


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_card(name):
    """A caption, amount, colour, dot, tooltip, cursor or number differs."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        if name in SHARED_WORDING:
            assert new["message"] == old["message"], (name, old, new)
        else:
            assert name in TYPE_NAMED_WORDING, name
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
def test_a_refusal_from_shared_code_is_worded_the_same_on_both_sides(name):
    """One side worded a refusal both sides raise from the same code."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["message"]) == (old["error"], old["message"])
    assert old["error"] in ("TypeError", "ValueError")


@pytest.mark.parametrize(
    "name,type_given,type_not_given",
    [
        ("a_number_where_the_label_belongs", "int", "float"),
        ("a_decimal_where_the_value_belongs", "float", "int"),
        ("a_flag_where_the_label_belongs", "bool", "float"),
    ],
)
def test_a_refusal_each_side_words_itself_still_names_the_type_given(
    name, type_given, type_not_given
):
    """A refusal names no type, so a caller cannot see what it gave.

    The Qt side words this refusal through its own label, the surface
    through its own check, so the two wordings are not one string. Both
    must still name the type they were handed and neither may name a type
    it was not.
    """
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused" and new["outcome"] == "refused", (old, new)
    assert old["error"] == new["error"] == "TypeError"
    headline = refusal_headline(old["message"])
    assert type_given in headline, headline
    assert type_given in new["message"], new["message"]
    assert type_not_given not in headline, headline
    assert type_not_given not in new["message"], new["message"]


def refusal_headline(message) -> str:
    """The one line of a Qt refusal that names the type it was given.

    The rest of a Qt refusal lists every supported signature, which names
    every type Qt accepts, so a check reading the whole message can never
    report a type as absent.
    """
    return message.splitlines()[1].strip()


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    plain = old_outcome(BY_NAME["built_only"])["value"]
    grown = old_outcome(BY_NAME["a_thousand_million"])["value"]
    assert canonical(plain) != canonical(grown)
    assert digest(plain) != digest(grown)
    assert digest(plain) == digest(old_outcome(BY_NAME["built_only"])["value"])
    assert len(digest(plain)) == 64


def test_the_hash_reads_a_whole_number_and_a_not_a_number_as_text():
    """A whole number and a decimal hash the same, or two blanks differ."""
    assert 12 == 12.0
    assert digest({"n": 12}) != digest({"n": 12.0})
    assert math.nan != math.nan
    assert digest({"n": math.nan}) == digest({"n": math.nan})
    assert canonical({"n": math.nan}) == canonical({"n": math.nan})


@pytest.mark.parametrize(
    "name",
    ["built_only", "a_dot_attached", "the_whole_card", "no_label_and_no_value"],
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == TRACE_KEY_TOTAL, sorted(value)
    assert len(value["label_row_items"]) == LABEL_ROW_ITEM_TOTAL
    assert len(value["items"]) >= OUTER_ITEM_TOTAL
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


def test_a_masked_field_hides_the_amount_on_both_sides():
    """The mask branch was never taken, so masking was never compared."""
    shown = old_outcome(BY_NAME["a_value_set_after_a_dot"])["value"]
    hidden = old_outcome(BY_NAME["a_value_set_after_a_dot_while_masked"])["value"]
    assert shown["value"]["text"] == "1234.56"
    assert hidden["value"]["text"] == "****"
    assert shown["value"]["text"] != hidden["value"]["text"]
    mine = new_outcome(BY_NAME["a_value_set_after_a_dot_while_masked"])["value"]
    assert mine["value"]["text"] == hidden["value"]["text"]
    assert mine["dot"]["text"] == surface.DOT_MASKED_GLYPH


def test_a_dot_click_masks_the_amount_and_re_renders_both_sides():
    """The shipped dot is wired to nothing, so a click changes no amount."""
    card, _ = drive_old(BY_NAME["a_value_set_after_a_dot"])
    before = qt_trace(card, 0)
    card._privacy_dot.click()
    after = qt_trace(card, 0)
    assert before["value"]["text"] == "1234.56"
    assert after["value"]["text"] == "****"
    assert after["dot"]["text"] == surface.DOT_MASKED_GLYPH
    assert registry().is_masked(FIELD_ID) is True
    model = surface.StatCardModel("Scrummed", "$0.00")
    model.attach_privacy_dot(FIELD_ID)
    model.set_value(1234.56)
    model.dot_clicked()
    mine = surface.build_view_model(model)
    assert mine["value"]["text"] == after["value"]["text"]
    assert mine["dot"]["text"] == after["dot"]["text"]


def test_a_left_press_fires_the_signal_and_a_right_press_does_not():
    """The card fires on a press it must ignore, or ignores one it must fire."""
    _, left = drive_old(BY_NAME["a_press_on_a_clickable_card"])
    _, right = drive_old(BY_NAME["a_right_press_on_a_clickable_card"])
    _, closed = drive_old(BY_NAME["a_press_on_a_card_that_is_not_clickable"])
    assert (left, right, closed) == (1, 0, 0)
    assert drive_new(BY_NAME["a_press_on_a_clickable_card"]).clicks == left
    assert drive_new(BY_NAME["a_right_press_on_a_clickable_card"]).clicks == right
    assert (
        drive_new(BY_NAME["a_press_on_a_card_that_is_not_clickable"]).clicks == closed
    )


# The enumeration: connect sites, classes, methods, signals, timers, bus


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


def test_the_card_connects_no_signal_and_the_counter_can_report():
    """The card connects a signal the surface names no action for.

    The card holds none, so the counter is pointed at the dot widget it
    attaches, which really does connect one. A counter that returned
    nothing on both would be no measurement.
    """
    sites = connect_sites(WIDGET_SOURCE)
    assert sites == [], sites
    assert len(sites) == CONNECT_TOTAL
    assert surface.ACTIONS == {}
    assert len(surface.ACTIONS) == CONNECT_TOTAL
    assert WIDGET_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    neighbour = connect_sites(CONNECT_NEIGHBOUR)
    assert neighbour == [("self.clicked", "self._on_click")], neighbour


SHIPPED_METHODS = {
    "__init__": "StatCardModel.__init__",
    "set_value": "StatCardModel.set_value",
    "attach_privacy_dot": "StatCardModel.attach_privacy_dot",
    "refresh_privacy_dot": "StatCardModel.refresh_privacy_dot",
    "set_clickable": "StatCardModel.set_clickable",
    "mousePressEvent": "StatCardModel.mouse_pressed",
}

SHIPPED_SIGNALS = {"clicked": "SIGNALS"}

SURFACE_CLASSES = {"StatCardModel": "StatCard"}

# Model methods the card owns through the dot it attaches, not as a
# method of its own, each with the shipped behaviour it stands for.
EXTRA_MODEL_METHODS = {
    "dot_toggled": "the callback attach_privacy_dot hands to the dot",
    "dot_clicked": "the dot's own click, which repaints it and calls back",
}


def shipped_methods() -> list:
    """Every method the shipped class declares, read off the class object.

    A signal is callable, so it is excluded by type rather than by
    whether it can be called.
    """
    from PySide6.QtCore import Signal

    from src.gui.widgets.dashboard_stat_card import StatCard

    return sorted(
        name
        for name, value in vars(StatCard).items()
        if callable(value) and not isinstance(value, Signal)
    )


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped card gained or lost a class or a method."""
    from src.gui.widgets import dashboard_stat_card as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == ["StatCard"], classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    found = shipped_methods()
    assert found == sorted(SHIPPED_METHODS), found
    assert len(found) == SHIPPED_METHOD_TOTAL
    for counterpart in SHIPPED_METHODS.values():
        holder, _, attribute = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), attribute)), counterpart


def test_every_shipped_signal_has_a_counterpart():
    """The shipped card declares a signal the surface names nowhere."""
    declared = qt_signal_names()
    assert declared == sorted(SHIPPED_SIGNALS), declared
    assert len(declared) == SHIPPED_SIGNAL_TOTAL
    assert list(surface.SIGNALS) == declared
    assert surface.SIGNAL_NAME == declared[0]


def test_every_surface_class_and_extra_method_names_what_it_replaces():
    """The surface grew a class or a method that stands in for nothing."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["StatCardModel"] == "StatCard"
    named = set(SHIPPED_METHODS.values()) | {
        f"StatCardModel.{name}" for name in EXTRA_MODEL_METHODS
    }
    mine = {
        f"StatCardModel.{name}"
        for name, value in vars(surface.StatCardModel).items()
        if callable(value) and not name.startswith("__") or name == "__init__"
    }
    assert mine == named, sorted(mine ^ named)


def test_the_method_reader_counts_no_signal_as_a_method():
    """A signal is callable, so the counter reports one method too many.

    The shipped card declares its own ``clicked`` signal and inherits
    every Qt signal it uses, so a reader that counted callables would
    report seven where six are methods, and a reader that walked the
    whole type would report far more.
    """
    from PySide6.QtCore import Signal

    from src.gui.launcher import ModeCard
    from src.gui.widgets.dashboard_stat_card import StatCard

    callables = [name for name, value in vars(StatCard).items() if callable(value)]
    assert "clicked" in callables
    assert "clicked" not in shipped_methods()
    assert len(callables) == SHIPPED_METHOD_TOTAL + SHIPPED_SIGNAL_TOTAL
    neighbour = [
        name for name, value in vars(ModeCard).items() if isinstance(value, Signal)
    ]
    assert neighbour == ["clicked"], neighbour
    assert "clicked" not in [
        name
        for name, value in vars(ModeCard).items()
        if callable(value) and not isinstance(value, Signal)
    ]
    assert "customContextMenuRequested" not in shipped_methods()
    assert callable(StatCard.customContextMenuRequested)
    assert len(dir(StatCard)) > SHIPPED_METHOD_TOTAL * 10
    with pytest.raises(AttributeError):
        getattr(surface, "InventedModel")


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


def test_the_card_holds_no_timer_and_the_counter_can_report():
    """The card runs a timer the surface declares no delay for."""
    assert timer_sites(WIDGET_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    neighbour = timer_sites(TIMER_NEIGHBOUR)
    assert len(neighbour) >= 1, "the timer counter reports nothing"
    assert timer_sites(REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py") == []


def test_the_card_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The card listens on a topic the surface names none of."""
    assert bus_sites(WIDGET_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


# The completeness check


def named_payloads() -> dict:
    """The four view models the completeness check reads."""
    blank = surface.StatCardModel(None, None)
    built = surface.StatCardModel("Scrummed", "$0.00")
    dotted_card = surface.StatCardModel("Locked", "$1.00")
    dotted_card.attach_privacy_dot(FIELD_ID)
    set_masks((FIELD_ID,))
    masked = surface.StatCardModel("Locked", "$1.00")
    masked.attach_privacy_dot(FIELD_ID)
    masked_model = surface.build_view_model(masked)
    set_masks(())
    clickable = surface.StatCardModel("Errors", "0")
    clickable.set_clickable(True, CLICK_SUFFIX)
    return {
        "blank": surface.build_view_model(blank),
        "built": surface.build_view_model(built),
        "dotted": surface.build_view_model(dotted_card),
        "masked": masked_model,
        "clickable": surface.build_view_model(clickable),
    }


PAYLOAD_KEYS = {
    "ACTIONS": "built:actions",
    "BUS_TOPICS": "built:bus_topics",
    "CALL_NAMES": "built:call_names",
    "CLICKABLE_CURSOR": "clickable:clickable.cursor",
    "DEFAULT_CURSOR": "built:clickable.cursor",
    "DEFAULT_VALUE": "built:value.default_text",
    "DOT_ALIGN": "built:layout.dot_align",
    "DOT_MASKED_GLYPH": "masked:dot.text",
    "DOT_REVEALED_GLYPH": "dotted:dot.text",
    "DOT_STYLE": "dotted:dot.style_sheet",
    "EMPTY_TEXT": "blank:label.text",
    "FRAME_SHAPE": "built:frame.frame_shape",
    "FRAME_STYLE": "built:frame.style_sheet",
    "LABEL_ALIGN": "built:label.align",
    "LABEL_LEADING_STRETCH": "built:layout.label_leading_stretch",
    "LABEL_PROPERTY": "built:label.property",
    "LABEL_ROW_MARGINS_PX": "built:layout.label_row_margins_px",
    "LABEL_ROW_SPACING_PX": "built:layout.label_row_spacing_px",
    "LABEL_STYLE": "built:label.style_sheet",
    "LABEL_TRAILING_STRETCH": "built:layout.label_trailing_stretch",
    "LEFT_BUTTON": "built:clickable.button",
    "METHOD": "built:method",
    "OUTER_MARGINS_PX": "built:layout.margins_px",
    "OUTER_SPACING_PX": "built:layout.spacing_px",
    "SIGNALS": "built:signals",
    "TIMERS": "built:timers",
    "TIMER_DELAYS_MS": "built:timer_delays_ms",
    "TOOLTIP_JOIN": "built:clickable.tooltip_join",
    "VALUE_ALIGN": "built:value.align",
    "VALUE_PROPERTY": "built:value.property",
    "VALUE_STYLE": "built:value.style_sheet",
}

# Values a payload carries inside a longer string or list rather than alone.
TEXT_INSIDE = {
    "DOT_MASKED_STATE": "masked:dot.tooltip",
    "DOT_REVEALED_STATE": "dotted:dot.tooltip",
    "SIGNAL_NAME": "built:signals",
}

# The seventeen branch markers, each carried inside call_names.
CALL_CONSTANTS = (
    "VALUE_SET",
    "VALUE_MASKED",
    "VALUE_PLAIN",
    "VALUE_REMASKED",
    "DOT_ATTACHED",
    "DOT_REUSED",
    "DOT_TOGGLED",
    "DOT_CLICKED",
    "DOT_REFRESHED",
    "DOT_REPAINTED",
    "CLICKABLE_ON",
    "CLICKABLE_OFF",
    "TOOLTIP_APPENDED",
    "TOOLTIP_KEPT",
    "CLICK_EMITTED",
    "CLICK_IGNORED",
    "DEFAULT_HANDLED",
)

# Snapshot keys built from other values rather than carrying one.
DERIVED_KEYS = {
    "items": "test_the_two_sides_describe_the_same_card",
    "label_row_items": "test_the_two_sides_describe_the_same_card",
    "tooltip": "test_the_two_sides_describe_the_same_card",
    "privacy": "test_the_two_sides_describe_the_same_card",
    "clicks": "test_a_left_press_fires_the_signal_and_a_right_press_does_not",
}

# Snapshot keys the Qt trace cannot answer, each with its own check.
OUTSIDE_THE_QT_TRACE = {
    "actions": "test_the_card_connects_no_signal_and_the_counter_can_report",
    "timers": "test_the_card_holds_no_timer_and_the_counter_can_report",
    "timer_delays_ms": "test_the_card_holds_no_timer_and_the_counter_can_report",
    "bus_topics": "test_the_card_subscribes_to_no_bus_topic_and_the_counter_can_report",
    "call_names": "test_every_branch_marker_fires_and_ties_to_what_the_operator_sees",
    "method": "test_the_bridge_registers_the_stat_card_method",
}


def at_path(payloads, path):
    """The value one ``name:dotted.path`` names."""
    name, _, dotted_path = path.partition(":")
    found = payloads[name]
    for step in dotted_path.split("."):
        found = found[int(step)] if step.isdigit() else found[step]
    return found


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


def as_json_shape(value):
    """`value` with every tuple turned into the list a payload carries."""
    if isinstance(value, (tuple, list)):
        return [as_json_shape(inner) for inner in value]
    if isinstance(value, dict):
        return {key: as_json_shape(inner) for key, inner in value.items()}
    return value


def unaccounted_constants(payloads, constants) -> list:
    """The exported values that reach no snapshot and no named check.

    A value counts as accounted when a snapshot path holds it, when a
    snapshot path contains it, or when it is a branch marker.
    """
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payloads, PAYLOAD_KEYS[name]) == as_json_shape(value), name
        elif name in TEXT_INSIDE:
            assert value in at_path(payloads, TEXT_INSIDE[name]), name
        elif name in CALL_CONSTANTS:
            assert value in payloads["built"]["call_names"], name
        else:
            unaccounted.append(name)
    return unaccounted


def unbacked_keys(built) -> set:
    """The snapshot keys no exported value and no named check backs."""
    answered = {path.partition(":")[2].split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {path.partition(":")[2].split(".")[0] for path in TEXT_INSIDE.values()}
    answered.add("call_names")
    return set(built) ^ (answered | set(DERIVED_KEYS))


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read.

    A comparison that reads some of the values passes whether the rest
    match or not.
    """
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    found = unaccounted_constants(named_payloads(), constants)
    assert found == [], found
    assert len(PAYLOAD_KEYS) == 31
    assert len(TEXT_INSIDE) == 3
    assert len(CALL_CONSTANTS) == 17
    assert len(CALL_CONSTANTS) == len(surface.CALL_NAMES)


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    built = named_payloads()["built"]
    assert unbacked_keys(built) == set(), sorted(unbacked_keys(built))
    assert len(built) == PAYLOAD_KEY_TOTAL
    for key, covered_by in DERIVED_KEYS.items():
        assert key in built
        assert callable(globals()[covered_by]), (key, covered_by)


def test_every_snapshot_key_the_qt_trace_cannot_answer_names_its_check():
    """A key no side-by-side reading covers is covered by nothing at all."""
    built = named_payloads()["built"]
    compared = set(surface_trace(built))
    assert compared == set(built) - set(OUTSIDE_THE_QT_TRACE), sorted(compared)
    assert len(compared) == TRACE_KEY_TOTAL
    for key, covered_by in OUTSIDE_THE_QT_TRACE.items():
        assert key in built, key
        assert callable(globals()[covered_by]), (key, covered_by)


def test_both_completeness_checks_report_what_they_are_given():
    """Both completeness checks passed because they look at nothing.

    A value the surface exports that reaches no snapshot must land in the
    unaccounted list, and a snapshot key no value backs must land in the
    unbacked set. Neither is shown by removing anything from the product:
    an invented value and an invented key are handed to the same two
    readers the checks above call.
    """
    payloads = named_payloads()
    constants = dict(surface_constants())
    constants["INVENTED_CONSTANT"] = "never in any snapshot"
    assert unaccounted_constants(payloads, constants) == ["INVENTED_CONSTANT"]
    assert unaccounted_constants(payloads, surface_constants()) == []
    grown = dict(payloads["built"])
    grown["invented_key"] = 1
    assert unbacked_keys(grown) == {"invented_key"}
    assert unbacked_keys(payloads["built"]) == set()
    shrunk = {key: value for key, value in payloads["built"].items() if key != "dot"}
    assert unbacked_keys(shrunk) == {"dot"}
    assert "build_view_model" not in surface_constants()
    assert "StatCardModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payloads, "built:frame.invented")


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        seen.update(drive_new(spec).calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    reused = drive_new(BY_NAME["a_dot_attached_twice_keeps_the_first_field"])
    assert reused.calls.count(surface.DOT_REUSED) == 1
    assert reused.dot["field_id"] == FIELD_ID
    kept = drive_new(BY_NAME["clickable_on_with_the_same_suffix_twice"])
    assert kept.calls.count(surface.TOOLTIP_KEPT) == 1
    assert kept.tooltip == f"{BASE_TOOLTIP}{surface.TOOLTIP_JOIN}{CLICK_SUFFIX}"
    ignored = drive_new(BY_NAME["a_right_press_on_a_clickable_card"])
    assert ignored.calls.count(surface.CLICK_IGNORED) == 1
    assert ignored.calls.count(surface.DEFAULT_HANDLED) == 1
    assert ignored.clicks == 0


# The surface carries its own values


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_card(monkeypatch):
    """The surface read its values off the card it replaces.

    A surface that read the shipped card would follow it, and the whole
    comparison above would be one side read twice. The two colours the
    shipped card paints with are moved where the shipped card reads them,
    and the surface must not move with them.
    """
    app()
    import types

    from src.gui import design_system as ds
    from src.gui.widgets import dashboard_stat_card as shipped

    before = qt_trace(*drive_old(BY_NAME["built_only"]))
    moved_tokens = types.SimpleNamespace(MAIN_CAPTION="#123456", PRIMARY="#ff00ff")
    monkeypatch.setattr(shipped, "ds", moved_tokens)
    moved = qt_trace(*drive_old(BY_NAME["built_only"]))
    assert "#ff00ff" in moved["value"]["style_sheet"]
    assert "#123456" in moved["label"]["style_sheet"]
    assert before["value"]["style_sheet"] != moved["value"]["style_sheet"]
    assert before["label"]["style_sheet"] != moved["label"]["style_sheet"]
    mine = surface_trace(surface.build_view_model(drive_new(BY_NAME["built_only"])))
    assert mine["value"]["style_sheet"] == before["value"]["style_sheet"]
    assert mine["label"]["style_sheet"] == before["label"]["style_sheet"]
    assert mine["value"]["style_sheet"] == surface.VALUE_STYLE
    assert mine["label"]["style_sheet"] == surface.LABEL_STYLE
    assert ds.PRIMARY in surface.VALUE_STYLE
    monkeypatch.undo()
    assert qt_trace(*drive_old(BY_NAME["built_only"])) == before


def test_the_shipped_card_holds_no_module_level_table_to_be_left_dirty():
    """The card writes a module-level table a later test would read.

    Nothing in the shipped module is a list, a dict or a set, so no run
    can leave one dirty for the next. The one shared thing the card
    reaches is the process-wide privacy register, which the dot it
    attaches writes, which is why every test here is given its own.
    """
    from src.gui.widgets import dashboard_stat_card as shipped

    containers = sorted(
        name
        for name, value in vars(shipped).items()
        if not name.startswith("__") and isinstance(value, (list, dict, set))
    )
    assert containers == [], containers
    mine = sorted(
        name
        for name, value in vars(surface).items()
        if not name.startswith("__") and isinstance(value, (list, dict, set))
    )
    assert mine, "the container counter reports nothing"
    assert registry().is_masked(FIELD_ID) is False
    card, _ = drive_old(BY_NAME["a_dot_attached"])
    card._privacy_dot.click()
    assert registry().is_masked(FIELD_ID) is True


def test_the_surface_does_not_follow_a_card_that_builds_nothing(monkeypatch):
    """The surface asked the shipped card to build its parts."""
    app()
    from src.gui.widgets import dashboard_stat_card as shipped

    payload_before = surface.build_view_model(surface.StatCardModel("Scrummed"))
    monkeypatch.setattr(shipped.StatCard, "__init__", _blank_init)
    stripped = shipped.StatCard("Scrummed")
    assert stripped.layout() is None
    assert not hasattr(stripped, "_value")
    again = surface.build_view_model(surface.StatCardModel("Scrummed"))
    assert again == payload_before
    assert again["value"]["text"] == surface.DEFAULT_VALUE
    monkeypatch.undo()
    assert shipped.StatCard("Scrummed").layout() is not None


def _blank_init(self, label, value="---", parent=None):
    """A card constructor that builds no layout at all."""
    from PySide6.QtWidgets import QFrame

    QFrame.__init__(self, parent)


def test_the_field_ids_this_card_carries_are_ones_the_registry_knows():
    """The card is driven with a field the privacy registry cannot mask."""
    from src.core.privacy_mask_registry import KPI_FIELD_IDS as registered

    assert set(KPI_FIELD_IDS) == set(registered)
    assert FIELD_ID in registered
    assert UNKNOWN_FIELD_ID not in registered


# The colours


def canonical_colour(colour):
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    app()
    return QColor(colour).name().lower()


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two declared colours become one when written in full."""
    from src.gui import design_system as ds

    written = {
        name: canonical_colour(value)
        for name, value in {
            "caption": ds.MAIN_CAPTION,
            "primary": ds.PRIMARY,
            "dot": ds.PRIMARY_BRIGHT,
            "hover": ds.TEXT_MAX,
        }.items()
    }
    assert len(set(written.values())) == len(written), written
    assert all(len(value) == 7 for value in written.values()), written


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour check passes a value with its channels swapped."""
    from src.gui import design_system as ds

    assert canonical_colour(ds.PRIMARY) == "#00ffcc"
    assert canonical_colour("#cc00ff") != canonical_colour(ds.PRIMARY)
    assert canonical_colour(ds.MAIN_CAPTION) == "#7a7d99"
    assert canonical_colour("#997a7d") != canonical_colour(ds.MAIN_CAPTION)
    assert surface.LABEL_STYLE != surface.VALUE_STYLE


def test_the_white_hover_colour_is_compared_as_text_because_its_channels_match():
    """A colour with three equal channels was left to a colour check.

    ``#ffffff`` reads the same with any two channels swapped, so no
    colour check can report a swap in it. The dot's hover colour carries
    it, and it is compared as exact text on both sides.
    """
    from src.gui import design_system as ds

    assert canonical_colour(ds.TEXT_MAX) == "#ffffff"
    assert canonical_colour("#fff") == canonical_colour(ds.TEXT_MAX)
    assert ds.TEXT_MAX in surface.DOT_STYLE
    old = qt_trace(*drive_old(BY_NAME["a_dot_attached"]))
    new = surface_trace(surface.build_view_model(drive_new(BY_NAME["a_dot_attached"])))
    assert new["dot"]["style_sheet"] == old["dot"]["style_sheet"]
    assert ds.TEXT_MAX in old["dot"]["style_sheet"]


# The pictures


@functools.lru_cache(maxsize=1)
def rebuilt_types():
    """The two classes a rebuilt card needs, named for the type selectors.

    The dot's style sheet selects by class name, so a dot of any other
    class is painted without its skin.
    """
    from PySide6.QtWidgets import QFrame, QPushButton

    class StatCard(QFrame):
        """The rebuilt card frame, carrying the shipped card's own name."""

        def __init__(self, parent=None):
            QFrame.__init__(self, parent)
            self.setAccessibleName("Stat Card")

    class PrivacyDot(QPushButton):
        """The rebuilt privacy dot, named for the dot style selector."""

        def __init__(self, parent=None):
            QPushButton.__init__(self, parent)
            self.setAccessibleName("Privacy Dot")

    return {"frame": StatCard, "dot": PrivacyDot}


def model_payload(spec=None):
    """The view model after the same driving, stamped."""
    return sealed(surface.build_view_model(drive_new(spec or BY_NAME["built_only"])))


def card_painted_by_the_widget(spec=None):
    """The card the shipped Qt widget builds, after the same driving."""
    return drive_old(spec or BY_NAME["built_only"])[0]


def card_painted_by_the_model(payload_dict, frame_type=None, dot_type=None):
    """A card built only from the payload, never from the shipped widget."""
    payload_dict = unaltered(payload_dict)
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

    app()
    types_ = rebuilt_types()
    frame_type = frame_type or types_["frame"]
    dot_type = dot_type or types_["dot"]
    aligns = {
        "hcenter": Qt.AlignHCenter,
        "hcenter|top": Qt.AlignHCenter | Qt.AlignTop,
        "hcenter|bottom": Qt.AlignHCenter | Qt.AlignBottom,
    }
    shapes = {"StyledPanel": QFrame.StyledPanel}
    layout_numbers = payload_dict["layout"]

    card = frame_type()
    card.setFrameShape(shapes[payload_dict["frame"]["frame_shape"]])
    card.setStyleSheet(payload_dict["frame"]["style_sheet"])
    card.setToolTip(payload_dict["tooltip"])
    if payload_dict["clickable"]["is_clickable"]:
        card.setCursor(Qt.PointingHandCursor)
    outer = QVBoxLayout(card)
    outer.setContentsMargins(*layout_numbers["margins_px"])
    outer.setSpacing(layout_numbers["spacing_px"])

    row = QHBoxLayout()
    row.setContentsMargins(*layout_numbers["label_row_margins_px"])
    row.setSpacing(layout_numbers["label_row_spacing_px"])
    for item in payload_dict["label_row_items"]:
        if item["kind"] == "stretch":
            row.addStretch()
        else:
            declared = payload_dict["label"]
            label = QLabel(declared["text"])
            label.setProperty(declared["property"], True)
            label.setAlignment(aligns[declared["align"]])
            label.setStyleSheet(declared["style_sheet"])
            row.addWidget(label)

    for item in payload_dict["items"]:
        if item["kind"] == "layout":
            outer.addLayout(row)
        elif item["role"] == "value":
            declared = payload_dict["value"]
            value = QLabel(declared["text"])
            value.setProperty(declared["property"], True)
            value.setAlignment(aligns[declared["align"]])
            value.setStyleSheet(declared["style_sheet"])
            outer.addWidget(value)
        else:
            declared = payload_dict["dot"]
            dot = dot_type()
            dot.setFlat(True)
            dot.setFocusPolicy(Qt.NoFocus)
            dot.setCursor(Qt.PointingHandCursor)
            dot.setText(declared["text"])
            dot.setStyleSheet(declared["style_sheet"])
            dot.setToolTip(declared["tooltip"])
            outer.addWidget(dot, alignment=aligns[item["align"]])
    return card


PICTURE_SCENARIOS = [
    "built_only",
    "a_dot_attached",
    "a_dot_attached_while_masked",
    "clickable_on_with_a_suffix",
    "the_whole_card",
]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different card than the shipped widget."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(
            card_painted_by_the_widget(BY_NAME[name]), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            card_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
        note=note,
    )


def test_the_dot_skin_reaches_the_picture_only_under_its_own_class_name():
    """A style sheet that selects by class name reaches no rebuilt element.

    The dot's style sheet selects by class name, so a dot of any other
    class is painted with none of its skin, and the picture check is what
    reports it. Two real classes, one payload.
    """
    app()
    from PySide6.QtWidgets import QPushButton

    assert "PrivacyDot {" in surface.DOT_STYLE
    payload_dict = model_payload(BY_NAME["a_dot_attached"])
    assert_pictures_differ(
        old_side=render_offscreen(card_painted_by_the_model(payload_dict), PIXEL_SIZE),
        new_side=render_offscreen(
            card_painted_by_the_model(payload_dict, dot_type=QPushButton), PIXEL_SIZE
        ),
        note="the named dot class against the plain Qt one",
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real scenarios, one driven into each side. One shows the amount,
    the other hides it behind the mask and paints a hollow dot, so a pass
    proves the comparison reports a card painted differently.
    """
    app()
    shown = BY_NAME["a_value_set_after_a_dot"]
    hidden = BY_NAME["a_value_set_after_a_dot_while_masked"]
    assert new_outcome(shown)["value"]["value"]["text"] == "1234.56"
    assert new_outcome(hidden)["value"]["value"]["text"] == "****"
    assert_pictures_differ(
        old_side=render_offscreen(card_painted_by_the_widget(shown), PIXEL_SIZE),
        new_side=render_offscreen(
            card_painted_by_the_model(model_payload(hidden)), PIXEL_SIZE
        ),
        note="a shown amount against a masked one",
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_card_shows_more_than_one_colour(name):
    """The two sides matched because the card painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    for image in (
        render_offscreen(card_painted_by_the_widget(BY_NAME[name]), PIXEL_SIZE),
        render_offscreen(
            card_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
    ):
        assert image.width() == PIXEL_SIZE[0]
        assert image.height() == PIXEL_SIZE[1]
        seen = set()
        for x in range(0, image.width(), 2):
            for y in range(0, image.height(), 2):
                seen.add(QColor(image.pixelColor(x, y)).name())
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    stamped = model_payload()
    stamped["value"]["text"] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        card_painted_by_the_model(stamped)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        card_painted_by_the_model(
            surface.build_view_model(surface.StatCardModel("Scrummed"))
        )


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on."""
    app()
    from PySide6.QtWidgets import QLabel

    narrow = QLabel("iiii")
    wide = QLabel("WWWW")
    if has_real_fonts():
        assert (
            narrow.sizeHint().width() != wide.sizeHint().width()
        ), "the host reports fonts and every glyph still has one width"
    else:
        assert (
            narrow.sizeHint().width() == wide.sizeHint().width()
        ), "the host reports no fonts and the glyphs still have their own widths"


def masked_marker_and_label():
    """The mask marker and a card label, both four characters."""
    set_masks((FIELD_ID,))
    model = surface.StatCardModel("Bots", "$0.00")
    model.attach_privacy_dot(FIELD_ID)
    model.set_value(1234.56)
    marker = surface.build_view_model(model)["value"]["text"]
    label = model.label_text
    assert len(marker) == len(label) and marker != label, (marker, label)
    return marker, label


@skip_unless_no_fonts
def test_the_mask_marker_and_a_label_measure_one_width():
    """With no font database a glyph still carries its own width."""
    app()
    from PySide6.QtWidgets import QLabel

    marker, label = masked_marker_and_label()
    assert QLabel(marker).sizeHint().width() == QLabel(label).sizeHint().width()


@skip_unless_real_fonts
def test_the_mask_marker_and_a_label_measure_different_widths():
    """With a font database every glyph still advances one em."""
    app()
    from PySide6.QtWidgets import QLabel

    marker, label = masked_marker_and_label()
    assert QLabel(marker).sizeHint().width() != QLabel(label).sizeHint().width()


# What a picture cannot see, read off both sides instead


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report.

    The tooltip, the pointer cursor, the privacy field id, the frame
    shape, the declared properties, the signal name and the default
    amount paint nothing. Each is read off the shipped card and off the
    surface directly, not through a picture.
    """
    app()
    spec = BY_NAME["the_whole_card"]
    old = qt_trace(*drive_old(spec))
    new = surface_trace(surface.build_view_model(drive_new(spec)))
    assert new["frame"]["frame_shape"] == old["frame"]["frame_shape"] == "StyledPanel"
    assert new["tooltip"] == old["tooltip"]
    assert old["tooltip"] == f"{BASE_TOOLTIP}{surface.TOOLTIP_JOIN}{CLICK_SUFFIX}"
    assert new["clickable"]["cursor"] == old["clickable"]["cursor"]
    assert old["clickable"]["cursor"] == surface.CLICKABLE_CURSOR
    assert new["clickable"]["is_clickable"] == old["clickable"]["is_clickable"] is True
    assert new["privacy"]["field_id"] == old["privacy"]["field_id"] == FIELD_ID
    assert (
        new["label"]["property"] == old["label"]["property"] == surface.LABEL_PROPERTY
    )
    assert (
        new["value"]["property"] == old["value"]["property"] == surface.VALUE_PROPERTY
    )
    assert new["signals"] == old["signals"] == [surface.SIGNAL_NAME]
    assert new["value"]["default_text"] == old["value"]["default_text"]
    assert old["value"]["default_text"] == surface.DEFAULT_VALUE
    closed = qt_trace(*drive_old(BY_NAME["clickable_then_off"]))
    assert closed["clickable"]["cursor"] == surface.DEFAULT_CURSOR
    assert closed["clickable"]["cursor"] != old["clickable"]["cursor"]


def test_the_property_reader_tells_the_two_declared_properties_apart():
    """The property reader answers the same name for both labels."""
    app()
    card, _ = drive_old(BY_NAME["built_only"])
    row = card.layout().itemAt(0).layout()
    label = row.itemAt(1).widget()
    value = card.layout().itemAt(1).widget()
    assert property_name(label) == "muted"
    assert property_name(value) == "heading"
    assert label.property("heading") is None
    assert value.property("muted") is None


# The bridge


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_stat_card_method():
    """The renderer cannot reach the stat card over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "dashboard_stat_card.state"
    answer = bridge_answer({"label": "Scrummed"})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["label"]["text"] == "Scrummed"
    assert result["value"]["text"] == surface.DEFAULT_VALUE


def test_the_bridge_builds_the_card_a_request_asks_for():
    """The bridge ignored the label, amount, dot or click a request named."""
    result = bridge_answer(
        {
            "label": "Errors",
            "value": "17",
            "field_id": FIELD_ID,
            "clickable": True,
            "tooltip_suffix": CLICK_SUFFIX,
        }
    )["result"]
    assert result["label"]["text"] == "Errors"
    assert result["value"]["text"] == "17"
    assert result["dot"]["field_id"] == FIELD_ID
    assert result["clickable"]["is_clickable"] is True
    assert result["tooltip"] == CLICK_SUFFIX
    blank = bridge_answer({"label": "Bots"})["result"]
    assert blank["dot"] is None
    assert blank["clickable"]["is_clickable"] is False


def test_the_bridge_reports_a_card_it_cannot_build():
    """A label the card refuses came back as an answer."""
    answer = bridge_answer({"label": 42})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "TypeError"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer(
        {"label": "Errors", "value": "17", "field_id": FIELD_ID, "refresh_dot": True}
    )
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["method"] == surface.METHOD
    assert encoded["result"]["dot"]["field_id"] == FIELD_ID


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'dashboard_stat_card.state', 'params':"
    " {'label': 'Scrummed', 'value': '$12.50', 'field_id': 'kpi.locked'}}),"
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
    """Reaching the stat card pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["label"]["text"] == "Scrummed"
    assert result["value"]["text"] == "$12.50"
    assert result["dot"]["field_id"] == "kpi.locked"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
