"""The Qt spendable-profits strip and the Qt-free surface, side by side."""

from __future__ import annotations

import ast
import functools
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

from src.gui.main_tabs import spendable_profits_surface as surface
from tests.fixtures.host_fonts import (
    has_real_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.repo_tree import named
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WIDGET_SOURCE = REPO_ROOT / "src" / "gui" / "widgets" / "spendable_profits.py"
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

PIXEL_SIZE = (900, 110)

CONNECT_TOTAL = 0
SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 7
PAYLOAD_KEY_TOTAL = 17
CONSTANT_TOTAL = 49
TRACE_KEY_TOTAL = 5
OUTER_ITEM_TOTAL = 18

KPI_FIELD_IDS = (
    "kpi.spendable",
    "kpi.realised",
    "kpi.locked",
    "kpi.mature",
    "kpi.exch",
)

# The test owns this column key map so neither side names the other.
COLUMN_KEY_BY_FIELD_ID = {
    "kpi.spendable": "spendable",
    "kpi.realised": "total_realised",
    "kpi.locked": "locked",
    "kpi.mature": "mature",
    "kpi.exch": "exchanges",
}

ALIGN_NAMES = {0: "", 4: "hcenter", 128: "vcenter"}


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


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


# A fresh privacy registry per test, because the process one is shared.
@pytest.fixture(autouse=True)
def own_privacy_registry(tmp_path, monkeypatch):
    """Give this test its own registry and restore the process one after."""
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
    """Hide exactly `field_ids` and reveal every other KPI field."""
    live = registry()
    live.set_all(False)
    for field_id in field_ids:
        live.set_masked(field_id, True)


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "Ekthelius' venues"
WRONG_CAPITALS_TEXT = "cOINBASE"

HAPPY = {
    "spendable": 1234.56,
    "total_realised": 9876.54,
    "locked": 250.0,
    "mature": 42.5,
    "exchange_count": 3,
}


def payload(**named):
    """The happy payload with the named entries replaced."""
    built = dict(HAPPY)
    built.update(named)
    return built


def scenario(name, data, masked=(), masked_after=(), then="none", update=True):
    return {
        "name": name,
        "data": data,
        "masked": tuple(masked),
        "masked_after": tuple(masked_after),
        "then": then,
        "update": update,
    }


SCENARIOS = [
    scenario("happy", payload()),
    scenario("built_only", None, update=False),
    scenario("empty_payload", {}),
    scenario(
        "zero_everywhere",
        payload(
            spendable=0,
            total_realised=0,
            locked=0,
            mature=0,
            exchange_count=0,
        ),
    ),
    scenario(
        "negative_everywhere",
        payload(
            spendable=-500.25,
            total_realised=-1.0,
            locked=-2.0,
            mature=-3.0,
            exchange_count=0,
        ),
    ),
    scenario(
        "a_thousand_million",
        payload(
            spendable=1_000_000_000,
            total_realised=1_000_000_000,
            locked=1_000_000_000,
            mature=1_000_000_000,
            exchange_count=1_000_000_000,
        ),
    ),
    scenario(
        "one_billionth",
        payload(
            spendable=1e-9,
            total_realised=1e-9,
            locked=1e-9,
            mature=1e-9,
            exchange_count=1e-9,
        ),
    ),
    scenario(
        "unknown_amounts",
        payload(spendable=None, total_realised=None, locked=None, mature=None),
    ),
    scenario("unicode_in_the_count", payload(exchange_count=UNICODE_TEXT)),
    scenario("two_hundred_characters", payload(exchange_count=LONG_TEXT)),
    scenario("markup_in_the_count", payload(exchange_count=MARKUP_TEXT)),
    scenario("apostrophe_in_the_count", payload(exchange_count=APOSTROPHE_TEXT)),
    scenario(
        "wrong_capitals_in_the_count", payload(exchange_count=WRONG_CAPITALS_TEXT)
    ),
    scenario("newline_in_the_count", payload(exchange_count=NEWLINE_TEXT)),
    scenario("a_number_where_text_belongs", payload(exchange_count=42)),
    scenario("wrong_capitals_in_the_keys", {"Spendable": 5.0, "Locked": 6.0}),
    scenario("infinity_where_a_number_belongs", payload(spendable=math.inf)),
    scenario("negative_infinity_where_a_number_belongs", payload(spendable=-math.inf)),
    scenario("not_a_number_where_a_number_belongs", payload(spendable=math.nan)),
    scenario("a_flag_where_a_number_belongs", payload(spendable=True)),
    scenario("text_where_a_number_belongs", payload(spendable="lots")),
    scenario("text_where_the_realised_amount_belongs", payload(total_realised="lots")),
    scenario("text_where_the_locked_amount_belongs", payload(locked="lots")),
    scenario("text_where_the_mature_amount_belongs", payload(mature="lots")),
    scenario("the_payload_is_a_list", [("spendable", 1.0)]),
    scenario("the_payload_is_missing", None),
    scenario("every_field_masked", payload(), masked=KPI_FIELD_IDS),
    scenario("only_the_spendable_masked", payload(), masked=("kpi.spendable",)),
    scenario(
        "unknown_amount_masked",
        payload(spendable=None),
        masked=("kpi.spendable",),
    ),
    scenario(
        "a_mask_set_after_a_payload_then_toggled",
        payload(),
        masked_after=("kpi.spendable", "kpi.locked"),
        then="toggle",
    ),
    scenario(
        "a_toggle_with_no_payload_rendered",
        None,
        masked_after=("kpi.spendable",),
        then="toggle",
        update=False,
    ),
    scenario(
        "a_mask_set_after_a_payload_then_the_dots_refreshed",
        payload(),
        masked_after=KPI_FIELD_IDS,
        then="refresh",
    ),
    scenario(
        "the_dots_refreshed_with_no_payload_rendered",
        None,
        masked_after=("kpi.exch",),
        then="refresh",
        update=False,
    ),
]

SCENARIO_NAMES = [spec["name"] for spec in SCENARIOS]
BY_NAME = {spec["name"]: spec for spec in SCENARIOS}

#: Only a payload that is not a mapping refuses; every value renders.
REFUSING_SCENARIOS = (
    "the_payload_is_a_list",
    "the_payload_is_missing",
)


def drive_old(spec):
    """The shipped Qt strip, built and driven by one scenario."""
    from src.gui.widgets.spendable_profits import SpendableProfitsWidget

    app()
    set_masks(spec["masked"])
    widget = SpendableProfitsWidget()
    if spec["update"]:
        widget.update_profits(spec["data"])
    if spec["masked_after"]:
        set_masks(spec["masked_after"])
    if spec["then"] == "toggle":
        widget._on_privacy_toggle()
    elif spec["then"] == "refresh":
        widget.refresh_privacy_dots()
    return widget


def drive_new(spec):
    """The Qt-free model, built and driven by the same scenario."""
    set_masks(spec["masked"])
    model = surface.SpendableProfitsModel()
    if spec["update"]:
        model.update_profits(spec["data"])
    if spec["masked_after"]:
        set_masks(spec["masked_after"])
    if spec["then"] == "toggle":
        model.privacy_toggled()
    elif spec["then"] == "refresh":
        model.refresh_privacy_dots()
    return model


def column_from_qt(column_layout):
    """One stat column, read off the three widgets the strip put in it."""
    label = column_layout.itemAt(0).widget()
    value = column_layout.itemAt(1).widget()
    dot_item = column_layout.itemAt(2)
    dot = dot_item.widget()
    return {
        "key": COLUMN_KEY_BY_FIELD_ID[dot.field_id()],
        "label": label.text(),
        "label_style": label.styleSheet(),
        "label_tooltip": label.toolTip(),
        "text": value.text(),
        "style_sheet": value.styleSheet(),
        "tooltip": value.toolTip(),
        "margins_px": list(column_layout.getContentsMargins()),
        "spacing_px": column_layout.spacing(),
        "dot": {
            "field_id": dot.field_id(),
            "text": dot.text(),
            "tooltip": dot.toolTip(),
            "style_sheet": dot.styleSheet(),
            "align": ALIGN_NAMES[int(dot_item.alignment())],
        },
    }


def item_from_qt(item):
    """One outer-row item, named by what the strip put there."""
    if item.layout() is not None:
        return {"kind": "layout", "column": column_from_qt(item.layout())["key"]}
    if item.widget() is not None:
        return {"kind": "separator"}
    if item.expandingDirections():
        return {"kind": "stretch"}
    return {"kind": "spacing", "px": item.sizeHint().width()}


def qt_trace(widget):
    """Everything the shipped strip shows, read off its own widgets."""
    outer = widget.layout()
    separator = None
    columns = []
    items = []
    for index in range(outer.count()):
        item = outer.itemAt(index)
        items.append(item_from_qt(item))
        if item.layout() is not None:
            columns.append(column_from_qt(item.layout()))
        elif item.widget() is not None and separator is None:
            separator = {
                "text": item.widget().text(),
                "style_sheet": item.widget().styleSheet(),
                "align": ALIGN_NAMES[int(item.widget().alignment())],
            }
    return {
        "frame": {
            "style_sheet": widget.styleSheet(),
            "frame_shape": widget.frameShape().name,
        },
        "layout": {
            "margins_px": list(outer.getContentsMargins()),
            "spacing_px": outer.spacing(),
        },
        "separator": separator,
        "items": items,
        "columns": columns,
    }


def surface_trace(payload_dict):
    """The same reading, taken off the view model alone."""
    layout = payload_dict["layout"]
    return {
        "frame": payload_dict["frame"],
        "layout": {
            "margins_px": layout["margins_px"],
            "spacing_px": layout["spacing_px"],
        },
        "separator": payload_dict["separator"],
        "items": payload_dict["items"],
        "columns": [
            {
                "key": column["key"],
                "label": column["label"],
                "label_style": column["label_style"],
                "label_tooltip": column["label_tooltip"],
                "text": column["text"],
                "style_sheet": column["style_sheet"],
                "tooltip": column["tooltip"],
                "margins_px": layout["column_margins_px"],
                "spacing_px": layout["column_spacing_px"],
                "dot": {
                    "field_id": column["dot"]["field_id"],
                    "text": column["dot"]["text"],
                    "tooltip": column["dot"]["tooltip"],
                    "style_sheet": column["dot"]["style_sheet"],
                    "align": layout["dot_align"],
                },
            }
            for column in payload_dict["columns"]
        ],
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
    return outcome(lambda: qt_trace(drive_old(spec)))


def new_outcome(spec):
    return outcome(lambda: surface_trace(surface.build_view_model(drive_new(spec))))


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_the_two_sides_describe_the_same_strip(name):
    """A column, colour, amount, dot, tooltip or layout number differs."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        assert new["message"] == old["message"], (name, old, new)
        return
    assert new["value"] == old["value"], name
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
def test_a_refused_payload_names_the_same_error_on_both_sides(name):
    """One side refused a payload the other accepted, or named another error."""
    spec = BY_NAME[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["message"]) == (old["error"], old["message"])
    assert old["error"] in ("TypeError", "ValueError", "AttributeError")


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    happy = old_outcome(BY_NAME["happy"])["value"]
    grown = old_outcome(BY_NAME["a_thousand_million"])["value"]
    assert happy != grown
    assert digest(happy) != digest(grown)
    assert digest(happy) == digest(old_outcome(BY_NAME["happy"])["value"])
    assert len(digest(happy)) == 64


@pytest.mark.parametrize(
    "name", ["happy", "built_only", "empty_payload", "every_field_masked"]
)
def test_the_sample_hashes_are_reported(name):
    """The comparison passed on a trace that carries nothing."""
    value = old_outcome(BY_NAME[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == TRACE_KEY_TOTAL, sorted(value)
    assert len(value["columns"]) == len(KPI_FIELD_IDS)
    assert len(value["items"]) == OUTER_ITEM_TOTAL
    assert digest(value) == digest(new_outcome(BY_NAME[name])["value"])


def test_a_masked_field_hides_the_amount_on_both_sides():
    """The mask branch was never taken, so masking was never compared."""
    shown = old_outcome(BY_NAME["happy"])["value"]["columns"][0]["text"]
    hidden = old_outcome(BY_NAME["every_field_masked"])["value"]["columns"][0]["text"]
    assert shown == "$1,234.56"
    assert hidden == "****"
    assert shown != hidden
    mine = new_outcome(BY_NAME["every_field_masked"])["value"]["columns"]
    assert [column["text"] for column in mine] == ["****"] * len(KPI_FIELD_IDS)


def test_a_dot_click_masks_the_amount_and_re_renders_both_sides():
    """The shipped dot is wired to nothing, so a click changes no amount."""
    widget = drive_old(BY_NAME["happy"])
    before = qt_trace(widget)["columns"][0]
    widget._privacy_dots[0].click()
    after = qt_trace(widget)["columns"][0]
    assert before["text"] == "$1,234.56"
    assert after["text"] == "****"
    assert after["dot"]["text"] == surface.DOT_MASKED_GLYPH
    assert registry().is_masked("kpi.spendable") is True
    model = surface.SpendableProfitsModel()
    model.update_profits(HAPPY)
    model.privacy_toggled()
    mine = surface.build_view_model(model)["columns"][0]
    assert mine["text"] == after["text"]


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


SHIPPED_METHODS = {
    "__init__": "SpendableProfitsModel.__init__",
    "update_profits": "SpendableProfitsModel.update_profits",
    "_on_privacy_toggle": "SpendableProfitsModel.privacy_toggled",
    "refresh_privacy_dots": "SpendableProfitsModel.refresh_privacy_dots",
    "_amount_of": "money_amount",
    "_money_text": "money_text",
    "_count_text": "count_text",
}

SURFACE_CLASSES = {"SpendableProfitsModel": "SpendableProfitsWidget"}


def shipped_methods() -> list:
    """Every method the shipped class declares, read off the class object."""
    from src.gui.widgets.spendable_profits import SpendableProfitsWidget

    return sorted(
        name
        for name, value in vars(SpendableProfitsWidget).items()
        if callable(value) and not name.startswith("__") or name == "__init__"
    )


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped strip gained or lost a class or a method."""
    from src.gui.widgets import spendable_profits as shipped

    classes = [
        name
        for name, value in vars(shipped).items()
        if isinstance(value, type) and value.__module__ == shipped.__name__
    ]
    assert classes == ["SpendableProfitsWidget"], classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    found = shipped_methods()
    assert found == sorted(SHIPPED_METHODS), found
    assert len(found) == SHIPPED_METHOD_TOTAL
    for counterpart in SHIPPED_METHODS.values():
        owner, _, attribute = counterpart.partition(".")
        named = getattr(surface, owner)
        assert callable(getattr(named, attribute) if attribute else named), counterpart


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SURFACE_CLASSES), built
    assert SURFACE_CLASSES["SpendableProfitsModel"] == "SpendableProfitsWidget"


def test_the_method_reader_counts_no_signal_as_a_method():
    """A signal is callable, so the counter reports one method too many."""
    from src.gui.widgets.spendable_profits import SpendableProfitsWidget

    assert "customContextMenuRequested" not in shipped_methods()
    assert callable(SpendableProfitsWidget.customContextMenuRequested)
    assert len(dir(SpendableProfitsWidget)) > SHIPPED_METHOD_TOTAL * 10
    assert "InventedMethod" not in SHIPPED_METHODS
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


def test_the_strip_holds_no_timer_and_the_counter_can_report():
    """The strip runs a timer the surface declares no delay for."""
    assert timer_sites(WIDGET_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(timer_sites(TIMER_NEIGHBOUR)) >= 1, "the timer counter reports nothing"


def test_the_strip_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The strip listens on a topic the surface names none of."""
    assert bus_sites(WIDGET_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


def rendered(amounts) -> dict:
    """One view model, built from a model driven with ``amounts`` once."""
    model = surface.SpendableProfitsModel()
    model.update_profits(amounts)
    return surface.build_view_model(model)


def named_payloads() -> dict:
    """The six view models the completeness check reads."""
    built = surface.build_view_model()
    negative = rendered(payload(spendable=-5.0))
    unknown = rendered(payload(spendable=None))
    unreadable = rendered(payload(spendable="lots"))
    happy = rendered(payload())
    set_masks(KPI_FIELD_IDS)
    masked = rendered(payload())
    set_masks(())
    return {
        "built": built,
        "happy": happy,
        "negative": negative,
        "unknown": unknown,
        "unreadable": unreadable,
        "masked": masked,
    }


PAYLOAD_KEYS = {
    "ACTIONS": "built:actions",
    "ALPHA_SCALE": "built:alpha_scale",
    "BUS_TOPICS": "built:bus_topics",
    "CALL_NAMES": "built:call_names",
    "COLUMN_MARGINS_PX": "built:layout.column_margins_px",
    "COLUMN_ORDER": "built:order",
    "COLUMN_SPACING_PX": "built:layout.column_spacing_px",
    "DOT_ALIGN": "built:layout.dot_align",
    "DOT_MASKED_GLYPH": "masked:columns.0.dot.text",
    "DOT_REVEALED_GLYPH": "built:columns.0.dot.text",
    "DOT_STYLE": "built:columns.0.dot.style_sheet",
    "EMPTY_TEXT": "built:columns.1.initial_text",
    "EXCHANGE_COUNT_DEFAULT": "built:columns.4.default",
    "FIELD_ID_BY_KEY": "built:field_ids",
    "FRAME_SHAPE": "built:frame.frame_shape",
    "FRAME_STYLE": "built:frame.style_sheet",
    "LABEL_STYLE": "built:columns.1.label_style",
    "METHOD": "built:method",
    "OUTER_MARGINS_PX": "built:layout.margins_px",
    "OUTER_SPACING_PX": "built:layout.spacing_px",
    "REALISED_DEFAULT": "built:columns.1.default",
    "SEPARATOR_ALIGN": "built:separator.align",
    "SEPARATOR_GAP_PX": "built:layout.separator_gap_px",
    "SEPARATOR_STYLE": "built:separator.style_sheet",
    "SEPARATOR_TEXT": "built:separator.text",
    "SPENDABLE_LABEL_STYLE": "built:columns.0.label_style",
    "SPENDABLE_TOOLTIP": "built:columns.0.label_tooltip",
    "SPENDABLE_UNKNOWN_TOOLTIP": "unknown:columns.0.tooltip",
    "TIMERS": "built:timers",
    "TIMER_DELAYS_MS": "built:timer_delays_ms",
    "TRAILING_STRETCH": "built:layout.trailing_stretch",
    "UNREADABLE_TOOLTIP": "unreadable:columns.0.tooltip",
    "VALUE_STYLE_DEFAULT": "built:columns.1.initial_style",
    "VALUE_STYLE_HIGHLIGHT": "happy:columns.0.style_sheet",
    "VALUE_STYLE_MUTED": "built:columns.0.initial_style",
    "VALUE_STYLE_NEGATIVE": "negative:columns.0.style_sheet",
}

# Values a payload carries inside a longer string rather than alone.
TEXT_INSIDE = {
    "DOT_MASKED_STATE": "masked:columns.0.dot.tooltip",
    "DOT_REVEALED_STATE": "built:columns.0.dot.tooltip",
    "MONEY_PREFIX": "happy:columns.0.text",
}

# The eight call constants, each carried inside the published call names.
CALL_CONSTANTS = (
    "UPDATE",
    "SPENDABLE_UNKNOWN",
    "SPENDABLE_UNREADABLE",
    "SPENDABLE_POSITIVE",
    "SPENDABLE_NEGATIVE",
    "PRIVACY_TOGGLED",
    "PRIVACY_TOGGLE_SKIPPED",
    "DOTS_REFRESHED",
)

# The declared column table, compared entry by entry.
DECLARED_TABLE = {"COLUMNS": "columns"}

# The one value no snapshot key carries, with the check that covers it.
NOT_IN_THE_SNAPSHOT = {
    "MONEY_FORMAT": "test_the_money_format_gives_two_places_and_thousands_marks",
}

# The snapshot keys built from other values rather than carrying one.
DERIVED_KEYS = {
    "items": "test_the_two_sides_describe_the_same_strip",
    "column_count": "test_both_published_counts_match_the_lists_beside_them",
    "item_count": "test_both_published_counts_match_the_lists_beside_them",
    "calls": "test_every_branch_marker_fires_and_ties_to_what_the_operator_sees",
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
    if isinstance(value, tuple):
        return [as_json_shape(inner) for inner in value]
    if isinstance(value, list):
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
        elif name in DECLARED_TABLE:
            carried = payloads["built"][DECLARED_TABLE[name]]
            assert len(carried) == len(value), name
            for declared, shown in zip(value, carried):
                for key, inner in declared.items():
                    assert shown[key] == inner, (name, key)
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
    answered |= set(DECLARED_TABLE.values())
    return set(built) ^ (answered | set(DERIVED_KEYS))


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read."""
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    found = unaccounted_constants(named_payloads(), constants)
    assert found == [], found
    assert len(PAYLOAD_KEYS) == 36
    assert len(TEXT_INSIDE) == 3
    assert len(CALL_CONSTANTS) == 8
    assert len(DECLARED_TABLE) == 1
    assert len(NOT_IN_THE_SNAPSHOT) == 1


def test_both_published_counts_match_the_lists_beside_them():
    """A count and its list disagree, so a page pairing them would fail."""
    for name, built in named_payloads().items():
        assert built["column_count"] == len(built["columns"]), name
        assert built["item_count"] == len(built["items"]), name
        assert built["column_count"] == len(surface.COLUMNS), name
        assert built["item_count"] == OUTER_ITEM_TOTAL, name


def test_the_count_check_reads_a_list_one_entry_shorter():
    """A count check that never compares would pass on a shortened list."""
    built = surface.build_view_model()
    built["columns"] = built["columns"][:-1]
    assert built["column_count"] != len(built["columns"])


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
    shrunk = {
        key: value for key, value in payloads["built"].items() if key != "separator"
    }
    assert unbacked_keys(shrunk) == {"separator"}
    assert "build_view_model" not in surface_constants()
    assert "SpendableProfitsModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payloads, "built:frame.invented")


def test_the_money_format_gives_two_places_and_thousands_marks():
    """The money format lost its thousands mark or its two places."""
    assert surface.MONEY_FORMAT == ",.2f"
    assert surface.money_text(1234567.891) == "$1,234,567.89"
    assert surface.money_text(0) == "$0.00"
    assert surface.money_text(None) == surface.EMPTY_TEXT
    assert f"{surface.MONEY_PREFIX}{1234.5:{surface.MONEY_FORMAT}}" == "$1,234.50"


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        seen.update(drive_new(spec).calls)
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    unknown = drive_new(BY_NAME["unknown_amounts"])
    assert unknown.calls.count(surface.SPENDABLE_UNKNOWN) == 1
    assert unknown.cells["spendable"]["tooltip"] == surface.SPENDABLE_UNKNOWN_TOOLTIP
    unreadable = drive_new(BY_NAME["text_where_a_number_belongs"])
    assert unreadable.calls.count(surface.SPENDABLE_UNREADABLE) == 1
    assert unreadable.cells["spendable"]["tooltip"] == surface.UNREADABLE_TOOLTIP
    negative = drive_new(BY_NAME["negative_everywhere"])
    assert negative.calls.count(surface.SPENDABLE_NEGATIVE) == 1
    assert negative.cells["spendable"]["style_sheet"] == surface.VALUE_STYLE_NEGATIVE
    skipped = drive_new(BY_NAME["a_toggle_with_no_payload_rendered"])
    assert skipped.calls == [surface.PRIVACY_TOGGLE_SKIPPED]
    assert skipped.cells["spendable"]["text"] == surface.EMPTY_TEXT


def test_a_refused_payload_records_neither_a_marker_nor_the_payload():
    """A marker or figure kept for a render that never ran is a figure invented."""
    model = surface.SpendableProfitsModel()
    with pytest.raises(AttributeError):
        model.update_profits([("spendable", 1.0)])
    assert model.calls == [], model.calls
    assert model.last_data == {}, model.last_data
    assert model.cells == surface.initial_cells()


def test_the_refusal_check_sees_the_marker_a_rendered_payload_records():
    """The same reading after a payload the strip did render."""
    model = surface.SpendableProfitsModel()
    model.update_profits(payload())
    assert model.calls == [surface.UPDATE, surface.SPENDABLE_POSITIVE]
    assert model.last_data == payload()


FILE_SUFFIXES = ("md", "txt", "py", "js", "json", "html", "css", "yml", "toml", "log")


def named_files(text) -> list:
    """Every word in one shown string that reads as a document name."""
    found = []
    for word in str(text).replace("(", " ").replace(")", " ").split():
        stripped = word.strip(".,;:'\"")
        if "." in stripped and stripped.rsplit(".", 1)[-1] in FILE_SUFFIXES:
            found.append(stripped)
    return found


def shown_strings() -> list:
    """Every label, tooltip and cell text the strip can show an operator."""
    written = []
    for spec in SCENARIOS:
        if spec["name"] in REFUSING_SCENARIOS:
            continue
        model = surface.build_view_model(drive_new(spec))
        for column in model["columns"]:
            written.extend(
                [
                    column["label"],
                    column["label_tooltip"],
                    column["text"],
                    column["tooltip"],
                    column["dot"]["tooltip"],
                ]
            )
    return written


def test_no_string_the_strip_shows_names_a_file_that_is_not_there():
    """A tooltip pointing at a missing document sends the operator nowhere."""
    missing = []
    for text in shown_strings():
        for name in named_files(text):
            if not named(name):
                missing.append((name, text[:60]))
    assert missing == [], missing


def test_the_file_name_scan_reads_a_name_out_of_a_tooltip():
    """A scan that found no name at all would pass on any tooltip."""
    assert named_files("see P0a in NEXT_SESSION_ORDERS.md.") == [
        "NEXT_SESSION_ORDERS.md"
    ]
    assert not named("NEXT_SESSION_ORDERS.md")
    assert named_files("see the file main.py now") == ["main.py"]
    assert named("main.py")


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_strip(monkeypatch):
    """The surface read its values off the strip it replaces."""
    app()
    from src.gui.widgets import spendable_profits as shipped

    before = qt_trace(drive_old(BY_NAME["happy"]))
    monkeypatch.setattr(
        shipped.SpendableProfitsWidget,
        "_VALUE_STYLE_HIGHLIGHT",
        "color: #ff00ff; font-size: 99px;",
    )
    moved = qt_trace(drive_old(BY_NAME["happy"]))
    assert moved["columns"][0]["style_sheet"] == "color: #ff00ff; font-size: 99px;"
    assert before["columns"][0]["style_sheet"] != moved["columns"][0]["style_sheet"]
    mine = surface_trace(surface.build_view_model(drive_new(BY_NAME["happy"])))
    assert mine["columns"][0]["style_sheet"] == before["columns"][0]["style_sheet"]
    assert mine["columns"][0]["style_sheet"] == surface.VALUE_STYLE_HIGHLIGHT
    monkeypatch.undo()
    assert qt_trace(drive_old(BY_NAME["happy"])) == before


def test_the_surface_does_not_follow_a_strip_that_builds_nothing(monkeypatch):
    """The surface asked the shipped strip to build its columns."""
    app()
    from src.gui.widgets import spendable_profits as shipped

    payload_before = surface.build_view_model()
    monkeypatch.setattr(shipped.SpendableProfitsWidget, "__init__", _blank_init)
    stripped = shipped.SpendableProfitsWidget()
    assert stripped.layout() is None
    assert not hasattr(stripped, "_stats")
    again = surface.build_view_model()
    assert again == payload_before
    assert again["order"] == list(surface.COLUMN_ORDER)
    monkeypatch.undo()
    assert shipped.SpendableProfitsWidget().layout() is not None


def _blank_init(self, parent=None):
    """A strip constructor that builds no layout at all."""
    from PySide6.QtWidgets import QFrame

    QFrame.__init__(self, parent)


def test_the_field_ids_are_the_ones_the_privacy_registry_knows():
    """The surface names a field the privacy registry cannot mask."""
    from src.core.privacy_mask_registry import KPI_FIELD_IDS as registered

    assert set(surface.FIELD_ID_BY_KEY.values()) == set(registered)
    assert set(surface.FIELD_ID_BY_KEY.values()) == set(COLUMN_KEY_BY_FIELD_ID)
    inverted = {v: k for k, v in surface.FIELD_ID_BY_KEY.items()}
    assert inverted == COLUMN_KEY_BY_FIELD_ID


def canonical(colour):
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    app()
    return QColor(colour).name().lower()


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two declared colours become one when written in full."""
    from src.gui import design_system as ds

    written = {
        name: canonical(value)
        for name, value in {
            "label": ds.CARD_METRIC_LABEL,
            "neutral": ds.TEXT_NEUTRAL,
            "success": ds.SUCCESS,
            "error": ds.ERROR,
            "separator": ds.MAIN_SEPARATOR,
            "primary": ds.PRIMARY,
            "dot": ds.PRIMARY_BRIGHT,
        }.items()
    }
    assert len(set(written.values())) == len(written), written
    assert all(len(value) == 7 for value in written.values()), written


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour check passes a value with its channels swapped."""
    from src.gui import design_system as ds

    assert canonical(ds.SUCCESS) == "#00ff88"
    assert canonical("#0088ff") != canonical(ds.SUCCESS)
    assert canonical(ds.ERROR) == "#ff3366"
    assert canonical("#3366ff") != canonical(ds.ERROR)
    assert surface.VALUE_STYLE_HIGHLIGHT != surface.VALUE_STYLE_NEGATIVE


def test_the_muted_grey_is_compared_as_text_because_its_channels_are_equal():
    """A colour with three equal channels was left to a colour check."""
    from src.gui import design_system as ds

    assert canonical(ds.CARD_METRIC_LABEL) == "#888888"
    assert canonical("#888") == canonical(ds.CARD_METRIC_LABEL)
    assert ds.CARD_METRIC_LABEL in surface.LABEL_STYLE
    assert ds.CARD_METRIC_LABEL in surface.VALUE_STYLE_MUTED
    old = qt_trace(drive_old(BY_NAME["unknown_amounts"]))
    new = surface_trace(surface.build_view_model(drive_new(BY_NAME["unknown_amounts"])))
    assert new["columns"][0]["style_sheet"] == old["columns"][0]["style_sheet"]
    assert new["columns"][1]["label_style"] == old["columns"][1]["label_style"]


@functools.lru_cache(maxsize=1)
def rebuilt_types():
    """The two classes a rebuilt strip needs, named for the type selectors."""
    from PySide6.QtWidgets import QFrame, QPushButton

    class SpendableProfitsWidget(QFrame):
        """The rebuilt strip frame, named for the frame style selector."""

        def __init__(self, parent=None):
            QFrame.__init__(self, parent)
            self.setAccessibleName("Spendable Profits")

    class PrivacyDot(QPushButton):
        """The rebuilt privacy dot, named for the dot style selector."""

        def __init__(self, parent=None):
            QPushButton.__init__(self, parent)
            self.setAccessibleName("Privacy Dot")

    return {"frame": SpendableProfitsWidget, "dot": PrivacyDot}


def model_payload(spec=None):
    """The view model after the same driving, stamped."""
    return sealed(surface.build_view_model(drive_new(spec or BY_NAME["happy"])))


def widget_painted_by_the_strip(spec=None):
    """The strip the shipped Qt widget builds, after the same driving."""
    return drive_old(spec or BY_NAME["happy"])


def widget_painted_by_the_model(payload_dict, frame_type=None, dot_type=None):
    """A strip built only from the payload, never from the shipped widget."""
    payload_dict = unaltered(payload_dict)
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

    app()
    types_ = rebuilt_types()
    frame_type = frame_type or types_["frame"]
    dot_type = dot_type or types_["dot"]
    aligns = {"hcenter": Qt.AlignHCenter, "vcenter": Qt.AlignVCenter}
    shapes = {"StyledPanel": QFrame.StyledPanel}
    layout = payload_dict["layout"]

    strip = frame_type()
    strip.setFrameShape(shapes[payload_dict["frame"]["frame_shape"]])
    strip.setStyleSheet(payload_dict["frame"]["style_sheet"])
    outer = QHBoxLayout(strip)
    outer.setContentsMargins(*layout["margins_px"])
    outer.setSpacing(layout["spacing_px"])

    by_key = {column["key"]: column for column in payload_dict["columns"]}
    for item in payload_dict["items"]:
        if item["kind"] == "spacing":
            outer.addSpacing(item["px"])
        elif item["kind"] == "separator":
            separator = QLabel(payload_dict["separator"]["text"])
            separator.setStyleSheet(payload_dict["separator"]["style_sheet"])
            separator.setAlignment(aligns[payload_dict["separator"]["align"]])
            outer.addWidget(separator)
        elif item["kind"] == "stretch":
            outer.addStretch()
        else:
            column = by_key[item["column"]]
            box = QVBoxLayout()
            box.setSpacing(layout["column_spacing_px"])
            box.setContentsMargins(*layout["column_margins_px"])
            label = QLabel(column["label"])
            label.setStyleSheet(column["label_style"])
            label.setToolTip(column["label_tooltip"])
            box.addWidget(label)
            value = QLabel(column["text"])
            value.setStyleSheet(column["style_sheet"])
            value.setToolTip(column["tooltip"])
            box.addWidget(value)
            dot = dot_type()
            dot.setFlat(True)
            dot.setFocusPolicy(Qt.NoFocus)
            dot.setCursor(Qt.PointingHandCursor)
            dot.setText(column["dot"]["text"])
            dot.setStyleSheet(column["dot"]["style_sheet"])
            dot.setToolTip(column["dot"]["tooltip"])
            box.addWidget(dot, alignment=aligns[layout["dot_align"]])
            outer.addLayout(box)
    return strip


PICTURE_SCENARIOS = [
    "happy",
    "built_only",
    "zero_everywhere",
    "unknown_amounts",
    "every_field_masked",
]


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different strip than the shipped widget."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(
            widget_painted_by_the_strip(BY_NAME[name]), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
        note=note,
    )


def test_the_frame_chrome_reaches_the_picture_only_under_its_own_class_name():
    """A style sheet that selects by class name reaches no rebuilt element."""
    app()
    from PySide6.QtWidgets import QFrame, QPushButton

    assert "SpendableProfitsWidget {" in surface.FRAME_STYLE
    assert "PrivacyDot {" in surface.DOT_STYLE
    assert_pictures_differ(
        old_side=render_offscreen(
            widget_painted_by_the_model(model_payload()), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(
                model_payload(), frame_type=QFrame, dot_type=QPushButton
            ),
            PIXEL_SIZE,
        ),
        note="the named classes against the plain Qt ones",
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints."""
    app()
    assert HAPPY["spendable"] > 0
    assert BY_NAME["negative_everywhere"]["data"]["spendable"] < 0
    assert_pictures_differ(
        old_side=render_offscreen(
            widget_painted_by_the_strip(BY_NAME["happy"]), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME["negative_everywhere"])),
            PIXEL_SIZE,
        ),
        note="a positive amount against a negative one",
    )


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_painted_strip_shows_more_than_one_colour(name):
    """The two sides matched because the strip painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    for image in (
        render_offscreen(widget_painted_by_the_strip(BY_NAME[name]), PIXEL_SIZE),
        render_offscreen(
            widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
        ),
    ):
        assert image.width() == PIXEL_SIZE[0]
        assert image.height() == PIXEL_SIZE[1]
        seen = set()
        for x in range(0, image.width(), 4):
            for y in range(0, image.height(), 4):
                seen.add(QColor(image.pixelColor(x, y)).name())
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    stamped = model_payload()
    stamped["columns"][0]["text"] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(stamped)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(surface.build_view_model())


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
    """The mask marker and the column label it hides, both four characters."""
    set_masks(("kpi.exch",))
    model = surface.SpendableProfitsModel()
    model.update_profits(HAPPY)
    marker = surface.build_view_model(model)["columns"][4]["text"]
    label = surface.COLUMNS[4]["label"]
    assert len(marker) == len(label) and marker != label, (marker, label)
    return marker, label


@skip_unless_no_fonts
def test_the_mask_marker_and_its_label_measure_one_width():
    """With no font database a glyph still carries its own width."""
    app()
    from PySide6.QtWidgets import QLabel

    marker, label = masked_marker_and_label()
    assert QLabel(marker).sizeHint().width() == QLabel(label).sizeHint().width()


@skip_unless_real_fonts
def test_the_mask_marker_and_its_label_measure_different_widths():
    """With a font database every glyph still advances one em."""
    app()
    from PySide6.QtWidgets import QLabel

    marker, label = masked_marker_and_label()
    assert QLabel(marker).sizeHint().width() != QLabel(label).sizeHint().width()


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report."""
    app()
    spec = BY_NAME["unknown_amounts"]
    old = qt_trace(drive_old(spec))
    new = surface_trace(surface.build_view_model(drive_new(spec)))
    assert new["frame"]["frame_shape"] == old["frame"]["frame_shape"] == "StyledPanel"
    assert new["columns"][0]["tooltip"] == old["columns"][0]["tooltip"]
    assert old["columns"][0]["tooltip"] == surface.SPENDABLE_UNKNOWN_TOOLTIP
    assert new["columns"][0]["label_tooltip"] == old["columns"][0]["label_tooltip"]
    assert old["columns"][0]["label_tooltip"] == surface.SPENDABLE_TOOLTIP
    for index, field_id in enumerate(KPI_FIELD_IDS):
        assert new["columns"][index]["dot"]["field_id"] == field_id
        assert old["columns"][index]["dot"]["field_id"] == field_id
        assert new["columns"][index]["dot"]["tooltip"] == (
            old["columns"][index]["dot"]["tooltip"]
        )


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_the_bridge_registers_the_spendable_profits_method():
    """The renderer cannot reach the spendable strip over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "spendable_profits.state"
    answer = bridge_answer({})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["order"] == list(surface.COLUMN_ORDER)
    assert result["frame"]["style_sheet"] == surface.FRAME_STYLE


def test_the_bridge_renders_a_payload_it_is_given():
    """The bridge ignored the amounts the request carried."""
    result = bridge_answer({"profits": HAPPY})["result"]
    texts = [column["text"] for column in result["columns"]]
    assert texts == ["$1,234.56", "$9,876.54", "$250.00", "$42.50", "3"]
    blank = bridge_answer({})["result"]
    assert [column["text"] for column in blank["columns"]] == [surface.EMPTY_TEXT] * 5


def test_the_bridge_draws_no_money_before_a_payload_arrives():
    """A built strip showed a dollar figure nothing measured."""
    blank = bridge_answer({})["result"]
    written = [column["text"] for column in blank["columns"]]
    assert surface.MONEY_PREFIX not in "".join(written), written
    assert blank["columns"][0]["initial_style"] == surface.VALUE_STYLE_MUTED


def test_the_money_scan_reads_the_dollar_sign_a_rendered_strip_shows():
    """A scan that saw no dollar sign anywhere would pass on any strip."""
    drawn = bridge_answer({"profits": HAPPY})["result"]
    written = [column["text"] for column in drawn["columns"]]
    assert surface.MONEY_PREFIX in "".join(written), written


def test_a_payload_missing_a_key_draws_the_empty_marker_not_a_zero():
    """A key the caller never sent must not read as a measured zero."""
    result = bridge_answer({"profits": {}})["result"]
    written = [column["text"] for column in result["columns"]]
    assert written == [surface.EMPTY_TEXT] * len(surface.COLUMNS), written


def test_the_missing_key_check_reads_a_zero_the_caller_did_send():
    """A zero the caller did send is drawn, so the check is not looking away."""
    sent = {
        "spendable": 0,
        "total_realised": 0,
        "locked": 0,
        "mature": 0,
        "exchange_count": 0,
    }
    result = bridge_answer({"profits": sent})["result"]
    written = [column["text"] for column in result["columns"]]
    assert written == ["$0.00", "$0.00", "$0.00", "$0.00", "0"], written


def test_the_bridge_draws_an_unreadable_amount_rather_than_refusing():
    """A word where an amount belongs stopped the whole strip."""
    answer = bridge_answer({"profits": {"spendable": "lots"}})
    assert answer["ok"] is True, answer
    column = answer["result"]["columns"][0]
    assert column["text"] == surface.EMPTY_TEXT
    assert column["tooltip"] == surface.UNREADABLE_TOOLTIP


def test_the_bridge_reports_a_payload_it_cannot_render():
    """A payload the strip refuses came back as an answer."""
    answer = bridge_answer({"profits": [("spendable", 1.0)]})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "AttributeError"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"profits": HAPPY, "refresh_dots": True})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["method"] == surface.METHOD
    assert len(encoded["result"]["columns"]) == len(KPI_FIELD_IDS)


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'spendable_profits.state', 'params':"
    " {'profits': {'spendable': 12.5, 'total_realised': 3.5, 'locked': 1.0,"
    " 'mature': 2.0, 'exchange_count': 4}}}),"
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
    """Reaching the spendable strip pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    texts = [column["text"] for column in answered["frame"]["result"]["columns"]]
    assert texts == ["$12.50", "$3.50", "$1.00", "$2.00", "4"]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
