"""The Qt Simulator stat strip and the Qt-free surface, side by side.

A failure means the view model describes a different field, a different
caption, a different value, a different colour, a different layout number
or a different branch than ``SimStatStrip`` builds on the same steps.
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

from src.gui.main_tabs import sim_stat_strip_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
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
WIDGET_SOURCE = REPO_ROOT / "src" / "gui" / "simulator_tab" / "sim_stat_strip.py"
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
QUIET_TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (1400, 60)

CONNECT_TOTAL = 0
SHIPPED_CLASS_TOTAL = 2
SHIPPED_METHOD_TOTAL = 5
PAYLOAD_KEY_TOTAL = 12
CONSTANT_TOTAL = 29
TRACE_KEY_TOTAL = 4
OUTER_ITEM_TOTAL = 11

# The test owns the field list, so neither side is named from the other.
FIELD_ORDER = (
    "Spendable",
    "Realised",
    "Locked",
    "Mature",
    "Exch",
    "Scrummed",
    "Folded",
    "Trades",
    "Bots",
    "Errors",
)

CAPTION_SUFFIX = ":"
PLACEHOLDER = "—"

# The shipped strip hands a value that is not text to a Qt label, which
# names the call it refused. The surface has no label and names the value.
QT_REFUSAL_HEADLINE = (
    "'PySide6.QtWidgets.QLabel.setText' called with wrong argument types:"
)

_MISSING = object()


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def fonts_ready() -> bool:
    """Whether this run holds a font database, asked after it is applied.

    ``has_real_fonts`` reads the database as it stands, so a caller that
    asks before the run's font choice is applied reads the state the run
    is leaving rather than the one it is in.
    """
    load_run_fonts()
    return has_real_fonts()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=repr).encode(
            "utf-8"
        )
    ).hexdigest()


def differing_paths(old, new, prefix: str = "") -> list:
    """Every dotted path at which two traces hold a different value."""
    if isinstance(old, dict) and isinstance(new, dict):
        found = []
        for key in sorted(set(old) | set(new), key=repr):
            found.extend(
                differing_paths(
                    old.get(key, _MISSING), new.get(key, _MISSING), f"{prefix}{key}."
                )
            )
        return found
    if isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        found = []
        for index, (left, right) in enumerate(zip(old, new)):
            found.extend(differing_paths(left, right, f"{prefix}{index}."))
        return found
    return [] if old == new else [prefix.rstrip(".")]


# The inputs. One table of step sequences drives both sides.

LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "Ekthelius' venues"
WRONG_CAPITALS_TEXT = "cOINBASE"

HAPPY_VALUES = (
    "1,234.56",
    "9,876.54",
    "250.00",
    "42.50",
    "3",
    "77.10",
    "5.05",
    "19",
    "38",
    "0",
)


def fill(values=HAPPY_VALUES) -> list:
    """One step per field, writing the values in the strip's own order."""
    return [("set", field, value) for field, value in zip(FIELD_ORDER, values)]


SCENARIOS = {
    "built_only": [],
    "happy": fill(),
    "cleared_only": [("clear",)],
    "set_then_cleared": fill() + [("clear",)],
    "set_cleared_and_set_again": fill() + [("clear",)] + fill(),
    "one_field_written_three_times": [
        ("set", "Trades", "1"),
        ("set", "Trades", "22"),
        ("set", "Trades", "333"),
    ],
    "every_field_blanked": [("set", field, "") for field in FIELD_ORDER],
    "empty_text": [("set", "Trades", "")],
    "zero_the_number": [("set", "Trades", 0)],
    "zero_the_text": [("set", "Trades", "0")],
    "none_value": [("set", "Trades", None)],
    "negative_text": [("set", "Scrummed", "-500.25")],
    "negative_number": [("set", "Scrummed", -500.25)],
    "a_thousand_million_text": [("set", "Folded", "1,000,000,000")],
    "a_thousand_million_number": [("set", "Folded", 1_000_000_000)],
    "one_billionth_text": [("set", "Folded", "0.000000001")],
    "one_billionth_number": [("set", "Folded", 1e-9)],
    "twelve": [("set", "Bots", "12")],
    "twelve_point_zero": [("set", "Bots", "12.0")],
    "unicode_value": [("set", "Exch", UNICODE_TEXT)],
    "two_hundred_characters": [("set", "Exch", LONG_TEXT)],
    "markup_value": [("set", "Exch", MARKUP_TEXT)],
    "apostrophe_value": [("set", "Exch", APOSTROPHE_TEXT)],
    "wrong_capitals_value": [("set", "Exch", WRONG_CAPITALS_TEXT)],
    "newline_in_the_value": [("set", "Exch", NEWLINE_TEXT)],
    "wrong_capitals_in_the_field": [("set", "spendable", "5.00")],
    "newline_in_the_field": [("set", "Spend\nable", "5.00")],
    "unknown_field": [("set", "Nope", "5.00")],
    "unknown_field_with_a_value_that_is_not_text": [("set", "Nope", 42)],
    "the_field_is_a_number": [("set", 42, "5.00")],
    "text_where_a_number_belongs": [("set", "Trades", "forty two")],
    "a_number_where_text_belongs": [("set", "Trades", 42)],
    "a_flag_where_text_belongs": [("set", "Trades", True)],
    "infinity_where_text_belongs": [("set", "Trades", math.inf)],
    "minus_infinity_where_text_belongs": [("set", "Trades", -math.inf)],
    "not_a_number_where_text_belongs": [("set", "Trades", math.nan)],
    "a_refusal_after_a_good_value": [
        ("set", "Trades", "7"),
        ("set", "Trades", math.nan),
    ],
    "the_field_is_not_hashable": [("set", ["Spendable"], "5.00")],
}

SCENARIO_NAMES = sorted(SCENARIOS)

# Both sides refuse these. The strip is refused by the Qt label it writes
# to, the surface by its own check, so the two wordings differ.
LIBRARY_REFUSALS = (
    "a_flag_where_text_belongs",
    "a_number_where_text_belongs",
    "a_refusal_after_a_good_value",
    "a_thousand_million_number",
    "infinity_where_text_belongs",
    "minus_infinity_where_text_belongs",
    "negative_number",
    "not_a_number_where_text_belongs",
    "one_billionth_number",
)

# Both sides refuse this from the same Python operation, so the wording
# is compared exactly.
SHARED_REFUSALS = ("the_field_is_not_hashable",)

REFUSING_SCENARIOS = tuple(sorted(LIBRARY_REFUSALS + SHARED_REFUSALS))


# Driving the two sides


def drive_old(name):
    """The shipped Qt strip, built and driven by one step sequence."""
    from src.gui.simulator_tab.sim_stat_strip import SimStatStrip

    app()
    strip = SimStatStrip()
    for step in SCENARIOS[name]:
        if step[0] == "clear":
            strip.clear()
        else:
            strip.set(step[1], step[2])
    return strip


def drive_new(name):
    """The Qt-free model, built and driven by the same step sequence."""
    model = surface.SimStatStripModel()
    for step in SCENARIOS[name]:
        if step[0] == "clear":
            model.clear()
        else:
            model.set_field(step[1], step[2])
    return model


# Reading the two sides


def field_from_qt(cell_widget) -> str:
    """The field name a cell carries, read off its caption."""
    caption = cell_widget.layout().itemAt(0).widget().text()
    assert caption.endswith(CAPTION_SUFFIX), caption
    return caption[: -len(CAPTION_SUFFIX)]


def cell_from_qt(cell_widget) -> dict:
    """One stat cell, read off the objects the strip put in it."""
    inner = cell_widget.layout()
    caption = inner.itemAt(0).widget()
    value = inner.itemAt(1).widget()
    return {
        "field": field_from_qt(cell_widget),
        "accessible_name": cell_widget.accessibleName(),
        "frame_shape": cell_widget.frameShape().name,
        "label": caption.text(),
        "label_style": caption.styleSheet(),
        "text": value.text(),
        "style_sheet": value.styleSheet(),
        "margins_px": list(inner.getContentsMargins()),
        "spacing_px": inner.spacing(),
    }


def item_from_qt(item) -> dict:
    """One row item, named by what the strip put there."""
    if item.widget() is not None:
        return {"kind": "cell", "field": field_from_qt(item.widget())}
    if item.expandingDirections():
        return {"kind": "stretch"}
    return {"kind": "spacing", "px": item.sizeHint().width()}


def qt_trace(strip) -> dict:
    """Everything the shipped strip shows, read off its own widgets."""
    outer = strip.layout()
    cells = []
    items = []
    for index in range(outer.count()):
        item = outer.itemAt(index)
        items.append(item_from_qt(item))
        if item.widget() is not None:
            cells.append(cell_from_qt(item.widget()))
    return {
        "widget": {
            "object_name": strip.objectName(),
            "accessible_name": strip.accessibleName(),
        },
        "layout": {
            "margins_px": list(outer.getContentsMargins()),
            "spacing_px": outer.spacing(),
        },
        "items": items,
        "cells": cells,
    }


def surface_trace(payload) -> dict:
    """The same reading, taken off the view model alone."""
    layout = payload["layout"]
    return {
        "widget": payload["widget"],
        "layout": {
            "margins_px": layout["margins_px"],
            "spacing_px": layout["spacing_px"],
        },
        "items": payload["items"],
        "cells": [
            {
                "field": entry["field"],
                "accessible_name": entry["accessible_name"],
                "frame_shape": entry["frame_shape"],
                "label": entry["label"],
                "label_style": entry["label_style"],
                "text": entry["text"],
                "style_sheet": entry["style_sheet"],
                "margins_px": layout["cell_margins_px"],
                "spacing_px": layout["cell_spacing_px"],
            }
            for entry in payload["cells"]
        ],
    }


def outcome(work) -> dict:
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": str(exc).splitlines()[0],
        }


def old_outcome(name) -> dict:
    return outcome(lambda: qt_trace(drive_old(name)))


def new_outcome(name) -> dict:
    return outcome(lambda: surface_trace(surface.build_view_model(drive_new(name))))


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_strip(name):
    """A field, caption, value, colour or layout number differs."""
    old = old_outcome(name)
    new = new_outcome(name)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    moved = differing_paths(old["value"], new["value"])
    assert moved == [], (name, moved)
    assert new["value"] == old["value"], name
    assert digest(new["value"]) == digest(old["value"]), name


def test_both_answers_and_refusals_are_in_the_measured_set():
    """Every input was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for name in SCENARIO_NAMES:
        old = old_outcome(name)
        (answered if old["outcome"] == "answered" else refused).append(name)
    assert answered, "no input was answered"
    assert refused, "no input was refused"
    assert sorted(refused) == sorted(REFUSING_SCENARIOS), sorted(refused)
    assert len(answered) + len(refused) == len(SCENARIOS)


@pytest.mark.parametrize("name", SHARED_REFUSALS)
def test_a_shared_refusal_carries_one_wording_on_both_sides(name):
    """The two sides refused the same input with different words."""
    old = old_outcome(name)
    new = new_outcome(name)
    assert (old["outcome"], new["outcome"]) == ("refused", "refused"), (old, new)
    assert new["error"] == old["error"] == "TypeError", (old, new)
    assert new["message"] == old["message"], (old, new)
    assert "unhashable" in old["message"], old
    assert old["message"] != QT_REFUSAL_HEADLINE, old


@pytest.mark.parametrize("name", LIBRARY_REFUSALS)
def test_a_library_refusal_names_the_qt_call_and_the_surface_names_the_value(name):
    """A refusal moved: the strip or the surface changed what it says.

    The strip is refused by the Qt label it writes to; the surface has no
    label and refuses the value itself. Both headlines are pinned, so a
    change on either side is reported.
    """
    old = old_outcome(name)
    new = new_outcome(name)
    assert (old["outcome"], new["outcome"]) == ("refused", "refused"), (old, new)
    assert new["error"] == old["error"] == "TypeError", (old, new)
    assert old["message"] == QT_REFUSAL_HEADLINE, old
    refused = [step[2] for step in SCENARIOS[name] if step[0] == "set"][-1]
    expected = surface.NOT_TEXT_MESSAGE.format(kind=type(refused).__name__)
    assert new["message"] == expected, (new, expected)
    assert new["message"] != old["message"], (old, new)


def test_a_value_that_is_not_text_is_refused_by_both_sides():
    """A value the strip cannot paint was accepted by one of the sides."""
    assert surface.NOT_TEXT_MESSAGE.format(kind="int") == (
        "a stat value must be text, not int"
    )
    assert surface.value_text("kept") == "kept"
    assert surface.value_text("") == PLACEHOLDER
    assert surface.value_text(None) == PLACEHOLDER
    assert surface.value_text(0) == PLACEHOLDER
    with pytest.raises(TypeError) as reported:
        surface.value_text(42)
    assert str(reported.value) == "a stat value must be text, not int"


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    plain = old_outcome("built_only")["value"]
    filled = old_outcome("happy")["value"]
    assert plain != filled
    assert digest(plain) != digest(filled)
    assert digest(plain) == digest(old_outcome("built_only")["value"])
    assert len(digest(plain)) == 64


def test_two_inputs_that_end_the_same_way_hash_the_same():
    """A control pair that ends in one state would report no difference.

    Filling every field and then clearing ends where a strip that was
    never driven ends, so that pair can never show a comparison working.
    The difference controls use a filled strip against a plain one.
    """
    plain = old_outcome("built_only")["value"]
    wiped = old_outcome("set_then_cleared")["value"]
    assert digest(plain) == digest(wiped)
    assert differing_paths(plain, wiped) == []
    filled = old_outcome("happy")["value"]
    assert differing_paths(plain, filled) != []


def test_a_number_and_its_decimal_are_read_as_their_own_text():
    """Two values that a number check calls equal reached one cell text."""
    assert 12 == 12.0
    twelve = new_outcome("twelve")["value"]["cells"]
    decimal = new_outcome("twelve_point_zero")["value"]["cells"]
    assert twelve[8]["text"] == "12"
    assert decimal[8]["text"] == "12.0"
    assert digest(twelve) != digest(decimal)
    assert differing_paths(twelve, decimal) == ["8.text"]


def test_a_not_a_number_never_reaches_a_compared_value():
    """A not-a-number landed in a cell, where no comparison can report it."""
    assert math.nan != math.nan
    for name in ("not_a_number_where_text_belongs", "a_refusal_after_a_good_value"):
        assert old_outcome(name)["outcome"] == "refused", name
        assert new_outcome(name)["outcome"] == "refused", name
    kept = drive_new("one_field_written_three_times")
    assert kept.cells["Trades"]["text"] == "333"


def test_a_refusal_leaves_the_last_good_value_in_place_on_both_sides():
    """A refused value wiped the cell it could not be written to."""
    from src.gui.simulator_tab.sim_stat_strip import SimStatStrip

    app()
    strip = SimStatStrip()
    strip.set("Trades", "7")
    model = surface.SimStatStripModel()
    model.set_field("Trades", "7")
    with pytest.raises(TypeError):
        strip.set("Trades", math.nan)
    with pytest.raises(TypeError):
        model.set_field("Trades", math.nan)
    assert qt_trace(strip)["cells"][7]["text"] == "7"
    assert model.cells["Trades"]["text"] == "7"


@pytest.mark.parametrize(
    "name", ["built_only", "happy", "set_then_cleared", "every_field_blanked"]
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(name)["value"]
    mine = new_outcome(name)["value"]
    assert isinstance(value, dict)
    assert len(value) == TRACE_KEY_TOTAL, sorted(value)
    assert len(value["cells"]) == len(FIELD_ORDER)
    assert len(value["items"]) == OUTER_ITEM_TOTAL
    assert digest(value) == digest(mine), (name, digest(value), digest(mine))


def test_the_fields_are_the_ones_the_test_names_in_the_order_it_names_them():
    """A field was renamed, dropped or moved on one of the sides."""
    old = old_outcome("built_only")["value"]
    new = new_outcome("built_only")["value"]
    assert [entry["field"] for entry in old["cells"]] == list(FIELD_ORDER)
    assert [entry["field"] for entry in new["cells"]] == list(FIELD_ORDER)
    assert [entry["label"] for entry in old["cells"]] == [
        f"{field}{CAPTION_SUFFIX}" for field in FIELD_ORDER
    ]
    assert surface.build_view_model()["order"] == list(FIELD_ORDER)
    assert len(FIELD_ORDER) == len(set(FIELD_ORDER)) == 10


def test_the_row_ends_with_one_stretch_after_ten_cells():
    """The trailing stretch was lost, so the cells spread across the row."""
    old = old_outcome("built_only")["value"]["items"]
    new = new_outcome("built_only")["value"]["items"]
    assert old == new
    assert [entry["kind"] for entry in old] == ["cell"] * 10 + ["stretch"]
    assert surface.TRAILING_STRETCH is True


def test_the_outer_spacing_is_not_the_spacing_a_fresh_layout_already_has():
    """A spacing equal to the host default reads the same set or unset.

    A fresh row on this host already spaces its items by six, so the cell
    spacing of six cannot tell a set value from an unset one. The outer
    spacing of four can, and it is the control that the strip really does
    set its own numbers.
    """
    app()
    from PySide6.QtWidgets import QHBoxLayout, QWidget

    holder = QWidget()
    unset = QHBoxLayout(holder).spacing()
    told = {surface.STRIP_SPACING_PX, surface.CELL_SPACING_PX}
    assert told - {unset}, (
        "every spacing the strip sets equals this host's default of "
        f"{unset}, so no spacing read-back tells a set value from an unset one"
    )
    old = old_outcome("built_only")["value"]
    assert old["layout"]["spacing_px"] == surface.STRIP_SPACING_PX
    assert old["layout"]["margins_px"] == list(surface.STRIP_MARGINS_PX)
    assert old["cells"][0]["spacing_px"] == surface.CELL_SPACING_PX
    assert old["cells"][0]["margins_px"] == list(surface.CELL_MARGINS_PX)


# The enumeration: connect sites, classes, methods, timers, bus topics


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


def test_the_strip_connects_no_signal_and_the_counter_can_report():
    """The strip connects a signal the surface names no action for."""
    sites = connect_sites(WIDGET_SOURCE)
    assert sites == [], sites
    assert len(sites) == CONNECT_TOTAL
    assert surface.ACTIONS == {}
    assert len(surface.ACTIONS) == CONNECT_TOTAL
    assert WIDGET_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    neighbour = connect_sites(CONNECT_NEIGHBOUR)
    assert neighbour == [("self.clicked", "self._on_click")], neighbour


def test_the_strip_holds_no_timer_and_the_counter_can_report():
    """The strip runs a timer the surface declares no delay for."""
    assert timer_sites(WIDGET_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(timer_sites(TIMER_NEIGHBOUR)) == 1, "the timer counter reports nothing"


def test_the_timer_counter_counts_a_construction_and_not_a_name():
    """The counter counts the word, so an import reads as a timer."""
    named = TIMER_NEIGHBOUR.read_text(encoding="utf-8").count("QTimer")
    built = len(timer_sites(TIMER_NEIGHBOUR))
    assert built == 1, built
    assert named > built, (named, built)
    assert len(timer_sites(QUIET_TIMER_NEIGHBOUR)) == 0
    assert TIMER_NEIGHBOUR != QUIET_TIMER_NEIGHBOUR
    assert TIMER_NEIGHBOUR.name == QUIET_TIMER_NEIGHBOUR.name


def test_the_strip_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The strip listens on a topic the surface names none of."""
    assert bus_sites(WIDGET_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) == 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


def real_methods(cls) -> list:
    """Every method a class declares. A Qt signal is callable, not a method."""
    from PySide6.QtCore import Signal, SignalInstance

    return sorted(
        name
        for name, value in vars(cls).items()
        if callable(value)
        and not isinstance(value, (Signal, SignalInstance))
        and (not name.startswith("__") or name == "__init__")
    )


SHIPPED_METHODS = {
    "_StatCell.__init__": "cell",
    "_StatCell.set_value": "value_text",
    "SimStatStrip.__init__": "SimStatStripModel.__init__",
    "SimStatStrip.set": "SimStatStripModel.set_field",
    "SimStatStrip.clear": "SimStatStripModel.clear",
}

SHIPPED_CLASSES = {"_StatCell": "cell", "SimStatStrip": "SimStatStripModel"}

SURFACE_CLASSES = {"SimStatStripModel": "SimStatStrip"}


def surface_counterpart(name):
    """The surface object one counterpart name points at."""
    holder, _, attribute = name.partition(".")
    target = getattr(surface, holder)
    return getattr(target, attribute) if attribute else target


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped strip gained or lost a class or a method."""
    from src.gui.simulator_tab import sim_stat_strip as shipped

    classes = sorted(
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    )
    assert classes == sorted(SHIPPED_CLASSES), classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    found = []
    for class_name in classes:
        found.extend(
            f"{class_name}.{name}"
            for name in real_methods(getattr(shipped, class_name))
        )
    assert sorted(found) == sorted(SHIPPED_METHODS), sorted(found)
    assert len(found) == SHIPPED_METHOD_TOTAL
    for counterpart in list(SHIPPED_METHODS.values()) + list(SHIPPED_CLASSES.values()):
        assert callable(surface_counterpart(counterpart)), counterpart


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["SimStatStripModel"] == "SimStatStrip"


def test_the_method_reader_counts_no_signal_as_a_method():
    """A signal is callable, so the counter reports one method too many."""
    from src.gui.launcher import ModeCard
    from src.gui.simulator_tab.sim_stat_strip import SimStatStrip

    declared = vars(ModeCard)
    assert "clicked" in declared, sorted(declared)
    assert callable(declared["clicked"]), "the signal is not callable, so no proof"
    assert real_methods(ModeCard) == ["__init__", "mousePressEvent"]
    assert "customContextMenuRequested" not in real_methods(SimStatStrip)
    assert callable(SimStatStrip.customContextMenuRequested)
    assert len(dir(SimStatStrip)) > SHIPPED_METHOD_TOTAL * 10
    with pytest.raises(AttributeError):
        surface_counterpart("InventedModel")


# The completeness check


def named_payloads() -> dict:
    """The view models the completeness check reads."""
    filled = surface.SimStatStripModel()
    for field, value in zip(FIELD_ORDER, HAPPY_VALUES):
        filled.set_field(field, value)
    return {
        "built": surface.build_view_model(),
        "filled": surface.build_view_model(filled),
    }


PAYLOAD_KEYS = {
    "ACTIONS": "built:actions",
    "BUS_TOPICS": "built:bus_topics",
    "CALL_NAMES": "built:call_names",
    "CELL_ACCESSIBLE_NAME": "built:cells.0.accessible_name",
    "CELL_FRAME_SHAPE": "built:cells.0.frame_shape",
    "CELL_MARGINS_PX": "built:layout.cell_margins_px",
    "CELL_SPACING_PX": "built:layout.cell_spacing_px",
    "FIELDS": "built:order",
    "LABEL_STYLE": "built:cells.0.label_style",
    "METHOD": "built:method",
    "PLACEHOLDER_TEXT": "built:placeholder",
    "STRIP_ACCESSIBLE_NAME": "built:widget.accessible_name",
    "STRIP_MARGINS_PX": "built:layout.margins_px",
    "STRIP_OBJECT_NAME": "built:widget.object_name",
    "STRIP_SPACING_PX": "built:layout.spacing_px",
    "TIMERS": "built:timers",
    "TIMER_DELAYS_MS": "built:timer_delays_ms",
    "TRAILING_STRETCH": "built:layout.trailing_stretch",
    "VALUE_STYLE": "built:cells.0.style_sheet",
}

# Values a payload carries inside a longer string rather than alone.
TEXT_INSIDE = {
    "LABEL_COLOUR": "built:cells.0.label_style",
    "LABEL_SUFFIX": "built:cells.0.label",
    "VALUE_COLOUR": "built:cells.0.style_sheet",
}

# The four branch markers, each carried inside call_names.
CALL_CONSTANTS = ("CLEARED", "FIELD_BLANKED", "FIELD_SET", "FIELD_UNKNOWN")

# The values no snapshot key carries, with the check that covers each.
NOT_IN_THE_SNAPSHOT = {
    "LABEL_FONT_SIZE_PX": "test_the_declared_font_sizes_reach_the_two_skins",
    "VALUE_FONT_SIZE_PX": "test_the_declared_font_sizes_reach_the_two_skins",
    "NOT_TEXT_MESSAGE": "test_a_value_that_is_not_text_is_refused_by_both_sides",
}

# The one snapshot key built from other values rather than carrying one.
DERIVED_KEYS = {"items": "test_the_row_ends_with_one_stretch_after_ten_cells"}


def at_path(payloads, path):
    """The value one ``name:dotted.path`` names."""
    name, _, dotted_path = path.partition(":")
    found = payloads[name]
    for step in dotted_path.split("."):
        found = found[int(step)] if step.isdigit() else found[step]
    return found


def surface_constants() -> dict:
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
    if isinstance(value, (list, tuple)):
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
            assert value in payloads["built"]["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
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
    """A value the surface exports is in no snapshot the tests read."""
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    found = unaccounted_constants(named_payloads(), constants)
    assert found == [], found
    assert len(PAYLOAD_KEYS) == 19
    assert len(TEXT_INSIDE) == 3
    assert len(CALL_CONSTANTS) == 4
    assert len(NOT_IN_THE_SNAPSHOT) == 3
    counted = (
        len(PAYLOAD_KEYS)
        + len(TEXT_INSIDE)
        + len(CALL_CONSTANTS)
        + len(NOT_IN_THE_SNAPSHOT)
    )
    assert counted == CONSTANT_TOTAL


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    built = surface.build_view_model()
    assert unbacked_keys(built) == set(), sorted(unbacked_keys(built))
    assert len(built) == PAYLOAD_KEY_TOTAL
    for key, covered_by in DERIVED_KEYS.items():
        assert key in built
        assert callable(globals()[covered_by]), (key, covered_by)


def test_both_completeness_checks_report_what_they_are_given():
    """Both completeness checks passed because they look at nothing."""
    payloads = named_payloads()
    constants = dict(surface_constants())
    constants["INVENTED_CONSTANT"] = "never in any snapshot"
    assert unaccounted_constants(payloads, constants) == ["INVENTED_CONSTANT"]
    assert unaccounted_constants(payloads, surface_constants()) == []
    grown = dict(payloads["built"])
    grown["invented_key"] = 1
    assert unbacked_keys(grown) == {"invented_key"}
    assert unbacked_keys(payloads["built"]) == set()
    shrunk = {key: value for key, value in payloads["built"].items() if key != "order"}
    assert unbacked_keys(shrunk) == {"order"}
    assert "build_view_model" not in surface_constants()
    assert "SimStatStripModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payloads, "built:widget.invented")


def test_the_declared_font_sizes_reach_the_two_skins():
    """A font size moved without the skin that carries it moving."""
    assert surface.LABEL_FONT_SIZE_PX == 11
    assert surface.VALUE_FONT_SIZE_PX == 13
    assert surface.LABEL_FONT_SIZE_PX != surface.VALUE_FONT_SIZE_PX
    assert f"font-size: {surface.LABEL_FONT_SIZE_PX}px;" in surface.LABEL_STYLE
    assert f"font-size: {surface.VALUE_FONT_SIZE_PX}px;" in surface.VALUE_STYLE
    old = old_outcome("built_only")["value"]["cells"][0]
    assert old["label_style"] == surface.LABEL_STYLE
    assert old["style_sheet"] == surface.VALUE_STYLE


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for name in SCENARIO_NAMES:
        if name in REFUSING_SCENARIOS:
            continue
        seen.update(drive_new(name).calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    written = drive_new("happy")
    assert written.calls == [surface.FIELD_SET] * len(FIELD_ORDER)
    assert written.cells["Spendable"]["text"] == HAPPY_VALUES[0]
    blanked = drive_new("every_field_blanked")
    assert blanked.calls == [surface.FIELD_BLANKED] * len(FIELD_ORDER)
    assert blanked.cells["Spendable"]["text"] == PLACEHOLDER
    ignored = drive_new("unknown_field")
    assert ignored.calls == [surface.FIELD_UNKNOWN]
    assert ignored.cells["Spendable"]["text"] == PLACEHOLDER
    wiped = drive_new("set_then_cleared")
    assert wiped.calls[-1] == surface.CLEARED
    assert wiped.cells["Errors"]["text"] == PLACEHOLDER


# The surface carries its own values


def test_the_surface_does_not_follow_a_placeholder_moved_in_the_strip(monkeypatch):
    """The surface read its values off the strip it replaces."""
    app()
    from src.gui.simulator_tab import sim_stat_strip as shipped

    before = qt_trace(drive_old("built_only"))
    monkeypatch.setattr(shipped, "_PLACEHOLDER", "MOVED")
    moved = qt_trace(drive_old("built_only"))
    assert moved["cells"][0]["text"] == "MOVED"
    assert differing_paths(before, moved) == [
        f"cells.{index}.text" for index in range(len(FIELD_ORDER))
    ]
    mine = surface_trace(surface.build_view_model(drive_new("built_only")))
    assert differing_paths(before, mine) == []
    assert mine["cells"][0]["text"] == PLACEHOLDER
    monkeypatch.undo()
    assert qt_trace(drive_old("built_only")) == before


def test_the_surface_does_not_follow_a_field_list_moved_in_the_strip(monkeypatch):
    """The surface read its field list off the strip it replaces."""
    app()
    from src.gui.simulator_tab.sim_stat_strip import SimStatStrip

    before = qt_trace(drive_old("built_only"))
    monkeypatch.setattr(SimStatStrip, "FIELDS", ("Alpha", "Beta"))
    moved = qt_trace(drive_old("built_only"))
    assert [entry["field"] for entry in moved["cells"]] == ["Alpha", "Beta"]
    assert len(moved["items"]) == 3
    mine = surface.build_view_model()
    assert mine["order"] == list(FIELD_ORDER)
    assert len(mine["cells"]) == len(FIELD_ORDER)
    monkeypatch.undo()
    assert qt_trace(drive_old("built_only")) == before


# The colours


def canonical(colour) -> str:
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    app()
    return QColor(colour).name().lower()


def test_a_channel_swap_is_reported_in_the_caption_colour():
    """The colour check passes a caption colour with its channels swapped."""
    assert canonical(surface.LABEL_COLOUR) == "#88aaff"
    assert canonical("#ffaa88") != canonical(surface.LABEL_COLOUR)
    assert canonical("#aa88ff") != canonical(surface.LABEL_COLOUR)
    assert canonical("#8af") == canonical(surface.LABEL_COLOUR)


def test_the_value_colour_is_compared_as_text_because_its_channels_are_equal():
    """A colour with three equal channels was left to a colour check."""
    assert canonical(surface.VALUE_COLOUR) == "#ffffff"
    assert canonical("#fff") == canonical(surface.VALUE_COLOUR)
    assert surface.VALUE_COLOUR == "#ffffff"
    old = old_outcome("built_only")["value"]["cells"][0]
    new = new_outcome("built_only")["value"]["cells"][0]
    assert new["style_sheet"] == old["style_sheet"]
    assert surface.VALUE_COLOUR in old["style_sheet"]
    assert surface.LABEL_COLOUR != surface.VALUE_COLOUR


# The pictures

FRAME_SHAPES = {"NoFrame": 0}


def model_payload(name="happy"):
    """The view model after the same driving, stamped."""
    return sealed(surface.build_view_model(drive_new(name)))


def strip_painted_by_the_widget(name="happy"):
    """The strip the shipped Qt widget builds, after the same driving."""
    return drive_old(name)


def strip_painted_by_the_model(payload):
    """A strip built only from the payload, never from the shipped widget."""
    payload = unaltered(payload)
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

    app()
    layout = payload["layout"]
    strip = QWidget()
    strip.setObjectName(payload["widget"]["object_name"])
    strip.setAccessibleName(payload["widget"]["accessible_name"])
    outer = QHBoxLayout(strip)
    outer.setContentsMargins(*layout["margins_px"])
    outer.setSpacing(layout["spacing_px"])
    by_field = {entry["field"]: entry for entry in payload["cells"]}
    for item in payload["items"]:
        if item["kind"] == "stretch":
            outer.addStretch()
            continue
        entry = by_field[item["field"]]
        frame = QFrame()
        frame.setAccessibleName(entry["accessible_name"])
        frame.setFrameShape(QFrame.Shape(FRAME_SHAPES[entry["frame_shape"]]))
        inner = QHBoxLayout(frame)
        inner.setContentsMargins(*layout["cell_margins_px"])
        inner.setSpacing(layout["cell_spacing_px"])
        caption = QLabel(entry["label"])
        caption.setStyleSheet(entry["label_style"])
        inner.addWidget(caption)
        value = QLabel(entry["text"])
        value.setStyleSheet(entry["style_sheet"])
        inner.addWidget(value)
        outer.addWidget(frame)
    return strip


PICTURE_SCENARIOS = [
    "built_only",
    "happy",
    "set_then_cleared",
    "every_field_blanked",
    "unicode_value",
    "markup_value",
]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different strip than the shipped widget."""
    app()
    note = "%s, %s" % (name, "real fonts" if fonts_ready() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(strip_painted_by_the_widget(name), PIXEL_SIZE),
        new_side=render_offscreen(
            strip_painted_by_the_model(model_payload(name)), PIXEL_SIZE
        ),
        note=note,
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real inputs, one driven into each side. The filled strip shows ten
    amounts and the plain one ten placeholders, and the two really do end
    in different states.
    """
    app()
    assert old_outcome("happy")["value"] != old_outcome("built_only")["value"]
    assert_pictures_differ(
        old_side=render_offscreen(strip_painted_by_the_widget("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            strip_painted_by_the_model(model_payload("built_only")), PIXEL_SIZE
        ),
        note="ten written amounts against ten placeholders",
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_strip_shows_more_than_one_colour(name):
    """The two sides matched because the strip painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    for image in (
        render_offscreen(strip_painted_by_the_widget(name), PIXEL_SIZE),
        render_offscreen(strip_painted_by_the_model(model_payload(name)), PIXEL_SIZE),
    ):
        seen = set()
        for x in range(0, image.width(), 3):
            for y in range(0, image.height(), 3):
                seen.add(QColor(image.pixelColor(x, y)).name())
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    stamped = model_payload()
    stamped["cells"][0]["text"] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        strip_painted_by_the_model(stamped)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        strip_painted_by_the_model(surface.build_view_model())


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on."""
    app()
    assert len(NARROW_LABEL) == len(WIDE_LABEL)
    if fonts_ready():
        assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)
    else:
        assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_no_fonts
def test_two_values_of_one_length_measure_one_width_with_no_font_database():
    """With no font database a glyph still carries its own width."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_two_values_of_one_length_measure_apart_with_a_font_database():
    """With a font database every glyph still advances one em."""
    app()
    assert app_font_advance_px(NARROW_LABEL) != app_font_advance_px(WIDE_LABEL)


def test_two_values_of_one_length_are_compared_as_text_whatever_the_fonts():
    """Two same-length values were left to the picture to tell apart."""
    narrow = surface.SimStatStripModel()
    narrow.set_field("Exch", NARROW_LABEL)
    wide = surface.SimStatStripModel()
    wide.set_field("Exch", WIDE_LABEL)
    assert narrow.cells["Exch"]["text"] == NARROW_LABEL
    assert wide.cells["Exch"]["text"] == WIDE_LABEL
    moved = differing_paths(
        surface.build_view_model(narrow), surface.build_view_model(wide)
    )
    assert moved == ["cells.4.text"], moved


# What a picture cannot see, read off both sides instead


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report.

    The object name, the two accessible names and the cell frame shape
    paint nothing. Each is read off the shipped strip and off the surface
    directly, not through a picture.
    """
    app()
    old = old_outcome("built_only")["value"]
    new = new_outcome("built_only")["value"]
    assert new["widget"]["object_name"] == old["widget"]["object_name"]
    assert old["widget"]["object_name"] == "SimStatStrip"
    assert new["widget"]["accessible_name"] == old["widget"]["accessible_name"]
    assert old["widget"]["accessible_name"] == "Sim Stat Strip"
    for index in range(len(FIELD_ORDER)):
        assert new["cells"][index]["accessible_name"] == (
            old["cells"][index]["accessible_name"]
        )
        assert old["cells"][index]["accessible_name"] == "Stat Cell"
        assert new["cells"][index]["frame_shape"] == old["cells"][index]["frame_shape"]
        assert old["cells"][index]["frame_shape"] == "NoFrame"


# Values that reach no pixel, with the check that reads each off both sides.
INVISIBLE_TO_A_PICTURE = {
    "widget.object_name": "test_the_values_no_picture_carries_are_read_off_both_sides",
    "widget.accessible_name": (
        "test_the_values_no_picture_carries_are_read_off_both_sides"
    ),
    "cells.accessible_name": (
        "test_the_values_no_picture_carries_are_read_off_both_sides"
    ),
    "cells.frame_shape": "test_the_values_no_picture_carries_are_read_off_both_sides",
    "cells.field": "test_the_fields_are_the_ones_the_test_names_in_the_order_it_names_them",
    "order": "test_the_fields_are_the_ones_the_test_names_in_the_order_it_names_them",
    "method": "test_the_bridge_registers_the_sim_stat_strip_method",
    "actions": "test_the_strip_connects_no_signal_and_the_counter_can_report",
    "timers": "test_the_strip_holds_no_timer_and_the_counter_can_report",
    "timer_delays_ms": "test_the_strip_holds_no_timer_and_the_counter_can_report",
    "bus_topics": "test_the_strip_subscribes_to_no_bus_topic_and_the_counter_can_report",
    "call_names": "test_every_branch_marker_fires_and_ties_to_what_the_operator_sees",
}


def test_every_value_a_picture_cannot_carry_names_the_check_that_reads_it():
    """A value no pixel carries was left to the render to report."""
    for value, covered_by in INVISIBLE_TO_A_PICTURE.items():
        assert covered_by in globals(), (value, covered_by)
        assert callable(globals()[covered_by]), (value, covered_by)
    assert len(INVISIBLE_TO_A_PICTURE) == 12


def test_the_two_skins_select_no_class_so_a_rebuilt_cell_keeps_them():
    """A skin that selects by class name reaches no rebuilt element.

    The strip sets both skins straight onto the widget with no selector,
    so the rebuilt row uses plain Qt classes and still paints them.
    """
    assert "{" not in surface.LABEL_STYLE
    assert "{" not in surface.VALUE_STYLE
    assert surface.LABEL_STYLE.startswith("color:")
    assert surface.VALUE_STYLE.startswith("color:")


# Shared state and run order


def test_the_shipped_strip_writes_no_shared_table():
    """Driving one strip changed a value a later strip would read."""
    from src.gui.simulator_tab import sim_stat_strip as shipped

    app()
    before_placeholder = shipped._PLACEHOLDER
    before_fields = shipped.SimStatStrip.FIELDS
    drive_old("set_cleared_and_set_again")
    assert shipped._PLACEHOLDER == before_placeholder
    assert shipped.SimStatStrip.FIELDS == before_fields
    assert qt_trace(drive_old("built_only"))["cells"][0]["text"] == PLACEHOLDER


def test_the_shared_state_reader_would_report_a_change(monkeypatch):
    """The reader reports no change whatever the module holds."""
    from src.gui.simulator_tab import sim_stat_strip as shipped

    app()
    monkeypatch.setattr(shipped, "_PLACEHOLDER", "MOVED")
    assert qt_trace(drive_old("built_only"))["cells"][0]["text"] == "MOVED"
    monkeypatch.undo()
    assert qt_trace(drive_old("built_only"))["cells"][0]["text"] == PLACEHOLDER


def test_two_models_share_no_cells():
    """Two models share one table, so one run decides what a later one shows."""
    first = surface.SimStatStripModel()
    second = surface.SimStatStripModel()
    first.set_field("Trades", "99")
    assert second.cells["Trades"]["text"] == PLACEHOLDER
    assert first.cells is not second.cells
    assert first.calls == [surface.FIELD_SET]
    assert second.calls == []
    one = surface.build_view_model()
    other = surface.build_view_model()
    assert one == other
    assert one is not other
    assert one["cells"][0] is not other["cells"][0]


# The bridge


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_sim_stat_strip_method():
    """The renderer cannot reach the Simulator stat strip over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "sim_stat_strip.state"
    answer = bridge_answer({})
    assert answer["ok"] is True
    assert answer["result"]["order"] == list(FIELD_ORDER)
    assert answer["result"]["widget"]["object_name"] == surface.STRIP_OBJECT_NAME


def test_the_bridge_writes_the_values_a_request_carries():
    """The bridge ignored the values the request carried."""
    asked = dict(zip(FIELD_ORDER, HAPPY_VALUES))
    result = bridge_answer({"values": asked})["result"]
    assert [entry["text"] for entry in result["cells"]] == list(HAPPY_VALUES)
    blank = bridge_answer({})["result"]
    assert [entry["text"] for entry in blank["cells"]] == [PLACEHOLDER] * len(
        FIELD_ORDER
    )
    wiped = bridge_answer({"values": asked, "clear": True})["result"]
    assert [entry["text"] for entry in wiped["cells"]] == list(HAPPY_VALUES)


def test_the_bridge_reports_a_value_it_cannot_render():
    """A value the strip refuses came back as an answer."""
    answer = bridge_answer({"values": {"Trades": 42}})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "TypeError"
    assert answer["error"]["message"] == "a stat value must be text, not int"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"values": {"Exch": UNICODE_TEXT}})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["method"] == surface.METHOD
    assert len(encoded["result"]["cells"]) == len(FIELD_ORDER)
    assert encoded["result"]["cells"][4]["text"] == UNICODE_TEXT


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'sim_stat_strip.state', 'params':"
    " {'values': {'Spendable': '12.50', 'Trades': '19'}}}),"
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
    """Reaching the Simulator stat strip pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    texts = [entry["text"] for entry in answered["frame"]["result"]["cells"]]
    assert texts[0] == "12.50"
    assert texts[7] == "19"
    assert texts[1] == PLACEHOLDER


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
