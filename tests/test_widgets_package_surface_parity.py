"""The shipped shared widgets and the Qt-free surface, side by side.

A failure means the view model carries a different card colour, a
different type size, a different padding, a different gap, a different
radius, a different frame rule, a different accessible name, a different
column header, a different column width, a different resize mode or a
different header tooltip than ``src.gui.widgets`` builds.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QFrame,
    QHeaderView,
    QLabel,
    QLayout,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.gui import design_system as ds
from src.gui.main_tabs import widgets_package_surface as surface
from src.gui.widgets import (
    METRIC_CARD,
    STOCK_CARD,
    CardStyle,
    ColumnarTableWidget,
    ColumnSpec,
    StatCard,
)
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    has_real_fonts,
    load_run_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

SHIPPED_PATH = REPO_ROOT / "src" / "gui" / "widgets" / "__init__.py"
SURFACE_PATH = REPO_ROOT / "src" / "gui" / "main_tabs" / "widgets_package_surface.py"

SHIPPED_SOURCE = SHIPPED_PATH.read_text(encoding="utf-8")
SURFACE_SOURCE = SURFACE_PATH.read_text(encoding="utf-8")

METHOD_NAME = "widgets_package.state"

CARD_SIZE = (240, 96)
TABLE_SIZE = (620, 200)

CONTROL_RULE = "QWidget { background: #7d1a4a; }"

LOOPBACK = {"127.0.0.1", "::1", "localhost"}

LONG_TEXT = "y" * 200
UNICODE_TEXT = "\u00e9\u4e2d\U0001f600 caf\u00e9"
MARKUP_TEXT = "<b>bold</b> & <i>x</i>"
APOSTROPHE_TEXT = "it's the operator's card"
NEWLINE_TEXT = "first\nsecond"
WRONG_CAPITALS_TEXT = "rEaLiSeD"
THOUSAND_MILLION = 1_000_000_000
ONE_BILLIONTH = 1e-09
NOT_A_NUMBER = float("nan")
INFINITY = float("inf")
MINUS_INFINITY = float("-inf")
TWO_TO_1023 = 2**1023
TWO_TO_1024 = 2**1024


@pytest.fixture(autouse=True, scope="module")
def app():
    """One application object for every render in this file."""
    load_run_fonts()
    return QApplication.instance() or QApplication([])


class SkinnedCard(StatCard):
    """A card under its own class name, so the frame rule is keyed on it."""


class ModelCard(QFrame):
    """The frame the payload paints, keyed on a class no QLabel shares.

    `QLabel` is itself a `QFrame`, so a frame rule written against
    `QFrame` draws the card border around every caption inside it. The
    shipped rule names the card own class, and this class restores that
    containment on the side built from the answer.
    """

    def __init__(self, accessible_name: str) -> None:
        super().__init__()
        self.setAccessibleName(accessible_name)


CARD_CLASSES = {"StatCard": StatCard, "SkinnedCard": SkinnedCard}

PRESET_STYLES = {
    None: None,
    "stock": STOCK_CARD,
    "metric": METRIC_CARD,
}


def digest(value) -> str:
    """SHA-256 over one answer, ordered so a swap changes it."""
    return hashlib.sha256(repr(canonical(value)).encode("utf-8")).hexdigest()


def canonical(value):
    """`value` as nested lists of text, ordered so a swap changes it.

    Every leaf becomes its printed form, so a whole number and a decimal
    of the same size are told apart and two not-a-numbers read alike.
    """
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: repr(item[0]))
        return [[repr(key), canonical(inner)] for key, inner in pairs]
    if isinstance(value, (list, tuple)):
        return [canonical(inner) for inner in value]
    return f"{type(value).__name__}:{value!r}"


# ---------------------------------------------------------------------
# The cases both sides are driven with
# ---------------------------------------------------------------------


def case(name, **named):
    """One drivable case, with the shipped defaults for everything unsaid."""
    spec = {
        "name": name,
        "label": "Realised",
        "value": "$1234.56",
        "preset": None,
        "skin": None,
        "class_name": "StatCard",
        "set_value": None,
        "set_colour": None,
        "labels": ("Bot ID", "Symbol", "Mode"),
        "tooltips": {},
        "fixed_widths": {},
        "table_name": "Demo Table",
    }
    spec.update(named)
    return spec


FULL_SKIN = {
    "label_color": "#6688aa",
    "value_color": "#e0e8f0",
    "label_size": 11,
    "value_size": 19,
    "padding": (3, 5, 7, 9),
    "spacing": 4,
    "surface": "#0e1428",
    "border": "#1a2a4f",
    "radius": 5,
    "accessible_name": "Every Field Set",
}

CASES = [
    case("happy"),
    case("stock_preset", preset="stock"),
    case("metric_preset", preset="metric"),
    case("subclass_name", preset="stock", class_name="SkinnedCard"),
    case(
        "every_field_default", skin={"label_color": "#abcdef", "value_color": "#123456"}
    ),
    case("every_field_set", skin=dict(FULL_SKIN)),
    case("set_value_plain", set_value="$99.00"),
    case("set_value_recoloured", set_value="$99.00", set_colour="#ff5577"),
    case("empty_text", label="", value="", table_name="", labels=()),
    case("zero_numbers", skin={**FULL_SKIN, "spacing": 0, "padding": (0, 0, 0, 0)}),
    case(
        "negative_numbers",
        skin={
            **FULL_SKIN,
            "spacing": -5,
            "padding": (-4, -5, -6, -7),
            "radius": -3,
            "label_size": -3,
        },
    ),
    case("negative_width", fixed_widths={2: -40}),
    case("zero_width", fixed_widths={2: 0}),
    case("thousand_million", skin={**FULL_SKIN, "spacing": THOUSAND_MILLION}),
    case("one_billionth_spacing", skin={**FULL_SKIN, "spacing": ONE_BILLIONTH}),
    case(
        "unicode_text",
        label=UNICODE_TEXT,
        value=UNICODE_TEXT,
        labels=(UNICODE_TEXT, "Symbol", "Mode"),
        table_name=UNICODE_TEXT,
    ),
    case(
        "two_hundred_characters",
        label=LONG_TEXT,
        value=LONG_TEXT,
        labels=(LONG_TEXT, "Symbol", "Mode"),
    ),
    case(
        "markup",
        label=MARKUP_TEXT,
        value=MARKUP_TEXT,
        labels=(MARKUP_TEXT, "Symbol", "Mode"),
    ),
    case(
        "apostrophe",
        label=APOSTROPHE_TEXT,
        value=APOSTROPHE_TEXT,
        table_name=APOSTROPHE_TEXT,
    ),
    case(
        "wrong_capitals", label=WRONG_CAPITALS_TEXT, labels=("bOt Id", "SYMBOL", "mode")
    ),
    case(
        "newline_in_a_name",
        label=NEWLINE_TEXT,
        labels=(NEWLINE_TEXT, "Symbol", "Mode"),
        table_name=NEWLINE_TEXT,
    ),
    case("number_printed_by_set_value", set_value=12.7),
    case("true_printed_by_set_value", set_value=True),
    case(
        "colour_that_is_not_a_colour",
        skin={**FULL_SKIN, "surface": "not-a-colour", "border": "also-not"},
    ),
    case("decimal_spacing", skin={**FULL_SKIN, "spacing": 12.7}),
    case("true_where_a_number_belongs", skin={**FULL_SKIN, "spacing": True}),
    case("largest_pixel", skin={**FULL_SKIN, "spacing": 2**31 - 1}),
    case(
        "tooltips_and_widths",
        tooltips={1: "what the symbol means"},
        fixed_widths={2: 70},
    ),
    case("tooltip_off_the_end", tooltips={9: "never shown"}),
    case("width_off_the_end", fixed_widths={9: 70}),
    case("falsy_table_name", table_name=0),
    case("unnamed_table", table_name=""),
    case("no_labels", labels=(), tooltips={}, fixed_widths={}),
    case("labels_from_text", labels="hello"),
    case("non_text_label", labels=(True, "Symbol", 12.7)),
]

REFUSING_CASES = [
    case("number_where_text_belongs", label=12.7),
    case("true_where_text_belongs", label=True),
    case("not_a_number_label", label=NOT_A_NUMBER),
    case("infinity_label", label=INFINITY),
    case("minus_infinity_label", label=MINUS_INFINITY),
    case("text_where_a_number_belongs", skin={**FULL_SKIN, "spacing": "12.7"}),
    case("not_a_number_spacing", skin={**FULL_SKIN, "spacing": NOT_A_NUMBER}),
    case("infinity_spacing", skin={**FULL_SKIN, "spacing": INFINITY}),
    case("minus_infinity_spacing", skin={**FULL_SKIN, "spacing": MINUS_INFINITY}),
    case("two_to_1023_spacing", skin={**FULL_SKIN, "spacing": TWO_TO_1023}),
    case("two_to_1024_spacing", skin={**FULL_SKIN, "spacing": TWO_TO_1024}),
    case("padding_too_short", skin={**FULL_SKIN, "padding": (1, 2, 3)}),
    case("padding_too_long", skin={**FULL_SKIN, "padding": (1, 2, 3, 4, 5)}),
    case("padding_empty", skin={**FULL_SKIN, "padding": ()}),
    case("padding_of_text", skin={**FULL_SKIN, "padding": ("1", "2", "3", "4")}),
    case("padding_beyond_qt", skin={**FULL_SKIN, "padding": (2**31, 0, 0, 0)}),
    case("card_name_is_a_number", skin={**FULL_SKIN, "accessible_name": 12.7}),
    case("card_name_is_zero", skin={**FULL_SKIN, "accessible_name": 0}),
    case("table_name_is_a_number", table_name=12.7),
    case("labels_cannot_be_counted", labels=None),
    case("width_beyond_qt", fixed_widths={2: 2**31}),
    case("width_is_text", fixed_widths={2: "70"}),
    case("tooltip_is_a_number", tooltips={1: 12.7}),
    case("tooltip_column_is_text", tooltips={"one": "x"}),
]

ALL_CASES = CASES + REFUSING_CASES
BY_NAME = {spec["name"]: spec for spec in ALL_CASES}


# ---------------------------------------------------------------------
# The shipped side
# ---------------------------------------------------------------------


class QtSeams:
    """Record what the shipped widgets ASK a layout and a table for.

    Qt rewrites a negative margin, a negative gap and an out-of-range
    column width before the getter reports them, so the read-back states
    the platform's default rather than the product's request. Every
    swapped name is put back on the way out, including after a refusal.
    """

    NAMES = (
        (QLayout, "setContentsMargins"),
        (QBoxLayout, "setSpacing"),
        (QTableView, "setColumnWidth"),
    )

    def __init__(self) -> None:
        self.saved: dict = {}
        self.margins: list = []
        self.spacing: list = []
        self.widths: list = []

    def __enter__(self) -> "QtSeams":
        for owner, name in self.NAMES:
            if name not in owner.__dict__:
                raise AssertionError(
                    f"{owner.__name__} does not carry {name!r}, so swapping "
                    "it would add a fresh name and record nothing"
                )
            self.saved[(owner, name)] = owner.__dict__[name]
        record = self

        real_margins = self.saved[(QLayout, "setContentsMargins")]
        real_spacing = self.saved[(QBoxLayout, "setSpacing")]
        real_width = self.saved[(QTableView, "setColumnWidth")]

        def watched_margins(layout, *found):
            record.margins.append(tuple(found))
            return real_margins(layout, *found)

        def watched_spacing(layout, value):
            record.spacing.append(value)
            return real_spacing(layout, value)

        def watched_width(table, column, width):
            record.widths.append((column, width))
            return real_width(table, column, width)

        setattr(QLayout, "setContentsMargins", watched_margins)
        setattr(QBoxLayout, "setSpacing", watched_spacing)
        setattr(QTableView, "setColumnWidth", watched_width)
        return self

    def __exit__(self, *_unused) -> None:
        for (owner, name), original in self.saved.items():
            setattr(owner, name, original)

    def restored(self) -> bool:
        """Whether every swapped name now holds what it held before."""
        return all(
            owner.__dict__.get(name) is original
            for (owner, name), original in self.saved.items()
        )


def style_of(spec):
    """The `CardStyle` one case asks the shipped card for."""
    if spec["skin"] is not None:
        return CardStyle(**spec["skin"])
    return PRESET_STYLES[spec["preset"]]


def shipped_card(spec, seams):
    """The shipped card one case builds, with its requests recorded."""
    before_margins = len(seams.margins)
    before_spacing = len(seams.spacing)
    card = CARD_CLASSES[spec["class_name"]](
        spec["label"], spec["value"], style=style_of(spec)
    )
    if spec["set_value"] is not None:
        card.set_value(spec["set_value"], spec["set_colour"])
    return card, seams.margins[before_margins:], seams.spacing[before_spacing:]


def shipped_table(spec, seams):
    """The shipped table one case builds, with its width requests kept."""
    before = len(seams.widths)
    table = ColumnarTableWidget(
        ColumnSpec(
            labels=spec["labels"],
            tooltips=spec["tooltips"],
            fixed_widths=spec["fixed_widths"],
            accessible_name=spec["table_name"],
        )
    )
    return table, seams.widths[before:]


def resize_mode_names(table):
    """The resize mode every built column carries, by name."""
    header = table.horizontalHeader()
    return [header.sectionResizeMode(at).name for at in range(table.columnCount())]


def header_texts(table):
    """The text every built header carries."""
    return [table.horizontalHeaderItem(at).text() for at in range(table.columnCount())]


def header_tooltips(table):
    """The tooltip every built header carries."""
    return [
        table.horizontalHeaderItem(at).toolTip() for at in range(table.columnCount())
    ]


def requested_widths(table, asked):
    """The width every in-range column was asked for, by column number."""
    return {
        str(column): width
        for column, width in asked
        if isinstance(column, int) and 0 <= column < table.columnCount()
    }


def drive_old(spec):
    """Build one case on the shipped widgets and read what they carry."""
    with QtSeams() as seams:
        card, margins, spacing = shipped_card(spec, seams)
        table, widths = shipped_table(spec, seams)
        state = {
            "card": {
                "accessible_name": card.accessibleName(),
                "frame_shape": card.frameShape().name,
                "frame_style_sheet": card.styleSheet(),
                "margins_asked": list(margins[-1]) if margins else [],
                "spacing_asked": spacing[-1] if spacing else None,
                "label_text": card._label.text(),
                "label_style_sheet": card._label.styleSheet(),
                "value_text": card._value.text(),
                "value_style_sheet": card._value.styleSheet(),
            },
            "table": {
                "accessible_name": table.accessibleName(),
                "column_count": table.columnCount(),
                "headers": header_texts(table),
                "resize_modes": resize_mode_names(table),
                "fixed_widths": requested_widths(table, widths),
                "tooltips": header_tooltips(table),
                "alternating_row_colours": table.alternatingRowColors(),
                "selection_behaviour": table.selectionBehavior().name,
                "edit_triggers": edit_trigger_name(table),
                "vertical_header_visible": table.verticalHeader().isVisible(),
            },
        }
        state["kept"] = (card, table)
        state["seams"] = seams
    return state


def edit_trigger_name(table) -> str:
    """The edit triggers a table carries, as the one name Qt gives them."""
    return str(table.editTriggers()).rsplit(".", 1)[-1]


# ---------------------------------------------------------------------
# The Qt-free side
# ---------------------------------------------------------------------


def surface_answer(spec) -> dict:
    """The surface's answer for one case, through the bridge handler."""
    asked = {
        "label": spec["label"],
        "value": spec["value"],
        "class_name": spec["class_name"],
        "spec": {
            "labels": spec["labels"],
            "tooltips": spec["tooltips"],
            "fixed_widths": spec["fixed_widths"],
            "accessible_name": spec["table_name"],
        },
    }
    if spec["skin"] is not None:
        asked["skin"] = spec["skin"]
    elif spec["preset"] is not None:
        asked["preset"] = spec["preset"]
    if spec["set_value"] is not None:
        asked["set_value"] = spec["set_value"]
        asked["set_colour"] = spec["set_colour"]
    return surface.view_model(asked)


def drive_new(spec):
    """Build one case on the surface and read what it carries."""
    answered = surface_answer(spec)
    card = answered["card"]
    table = answered["table"]
    return {
        "card": {
            "accessible_name": card["accessible_name"],
            "frame_shape": card["frame_shape"],
            "frame_style_sheet": card["frame_style_sheet"],
            "margins_asked": list(card["layout"]["margins_asked"]),
            "spacing_asked": card["layout"]["spacing_asked"],
            "label_text": card["label"]["text"],
            "label_style_sheet": card["label"]["style_sheet"],
            "value_text": card["value"]["text"],
            "value_style_sheet": card["value"]["style_sheet"],
        },
        "table": {
            "accessible_name": table["accessible_name"],
            "column_count": table["column_count"],
            "headers": list(table["headers"]),
            "resize_modes": list(table["resize_modes"]),
            "fixed_widths": dict(table["fixed_widths"]),
            "tooltips": list(table["tooltips"]),
            "alternating_row_colours": table["alternating_row_colours"],
            "selection_behaviour": table["selection_behaviour"],
            "edit_triggers": table["edit_triggers"],
            "vertical_header_visible": table["vertical_header_visible"],
        },
        "answer": answered,
    }


def compared(driven) -> dict:
    """Only the part of a drive both sides are answerable for."""
    return {"card": driven["card"], "table": driven["table"]}


def outcome(drive, spec):
    """One drive's answer, or the type of the refusal it raised."""
    try:
        return ("built", compared(drive(spec)))
    except Exception as exc:
        return ("refused", type(exc).__name__)


# ---------------------------------------------------------------------
# Both sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", [spec["name"] for spec in CASES])
def test_the_two_sides_describe_the_same_card_and_table(name):
    """The surface carries a different value than the shipped widgets."""
    spec = BY_NAME[name]
    old = compared(drive_old(spec))
    new = compared(drive_new(spec))
    assert new == old, f"{name}: surface {new!r} against shipped {old!r}"


@pytest.mark.parametrize("name", [spec["name"] for spec in CASES])
def test_the_two_sides_hash_alike(name):
    """One value moved without changing what a reader compares."""
    spec = BY_NAME[name]
    old = digest(compared(drive_old(spec)))
    new = digest(compared(drive_new(spec)))
    assert new == old, f"{name}: surface {new}, shipped {old}"


@pytest.mark.qt_no_exception_capture
@pytest.mark.parametrize("name", [spec["name"] for spec in REFUSING_CASES])
def test_a_refused_input_names_the_same_error_on_both_sides(name):
    """The surface accepts what the shipped widgets refuse, or the reverse."""
    spec = BY_NAME[name]
    old = outcome(drive_old, spec)
    new = outcome(drive_new, spec)
    assert old[0] == "refused", f"{name}: the shipped side built {old!r}"
    assert new == old, f"{name}: surface {new!r}, shipped {old!r}"


def test_the_sample_hashes_are_reported():
    """The hashes a reader can compare against a later run."""
    sampled = {
        name: digest(compared(drive_old(BY_NAME[name])))
        for name in ("happy", "stock_preset", "metric_preset", "every_field_set")
    }
    assert len(set(sampled.values())) == len(sampled), sampled
    for name, value in sampled.items():
        assert digest(compared(drive_new(BY_NAME[name]))) == value, name


def test_two_different_real_inputs_are_told_apart_in_both_directions():
    """The hash reports one answer whatever a side was driven with."""
    old_stock = digest(compared(drive_old(BY_NAME["stock_preset"])))
    new_metric = digest(compared(drive_new(BY_NAME["metric_preset"])))
    assert old_stock != new_metric
    new_stock = digest(compared(drive_new(BY_NAME["stock_preset"])))
    old_metric = digest(compared(drive_old(BY_NAME["metric_preset"])))
    assert new_stock != old_metric
    assert new_stock == old_stock
    assert new_metric == old_metric


def test_the_same_input_twice_describes_one_card():
    """A drive depends on something other than the case it was given."""
    first = digest(compared(drive_new(BY_NAME["stock_preset"])))
    assert digest(compared(drive_new(BY_NAME["stock_preset"]))) == first
    assert digest(compared(drive_old(BY_NAME["stock_preset"]))) == first


def test_a_whole_number_and_a_decimal_are_told_apart_by_the_hash():
    """`12` and `12.0` read alike, so a type change passes unreported."""
    assert digest({"spacing": 12}) != digest({"spacing": 12.0})


def test_two_not_a_numbers_hash_alike_and_apart_from_an_infinity():
    """Two not-a-numbers read as different, so every answer holding one fails."""
    first = float("nan")
    second = float("nan")
    assert first is not second
    assert first != second
    assert digest({"px": first}) == digest({"px": second})
    assert digest({"px": first}) != digest({"px": float("inf")})


def test_the_true_stored_where_a_number_belongs_prints_as_one_pixel():
    """A stored true reaches the layout as something other than one pixel."""
    spec = BY_NAME["true_where_a_number_belongs"]
    assert compared(drive_old(spec))["card"]["spacing_asked"] is True
    assert compared(drive_new(spec))["card"]["spacing_asked"] is True
    assert surface_answer(spec)["card"]["layout"]["spacing_px"] == 1


# ---------------------------------------------------------------------
# Step sequences, including one that refuses part way
# ---------------------------------------------------------------------


SEQUENCE = (
    "happy",
    "stock_preset",
    "set_value_recoloured",
    "metric_preset",
)

REFUSING_SEQUENCE = (
    "happy",
    "stock_preset",
    "padding_too_short",
    "metric_preset",
)


def drive_sequence(drive, names):
    """Build each named case in turn, stopping at the first refusal."""
    kept: list = []
    for at, name in enumerate(names):
        try:
            kept.append(digest(compared(drive(BY_NAME[name]))))
        except Exception as exc:
            return {
                "kept": kept,
                "stopped_at": at,
                "step_name": name,
                "refusal": type(exc).__name__,
            }
    return {"kept": kept, "stopped_at": None, "step_name": None, "refusal": None}


def test_a_step_sequence_takes_the_same_path_on_both_sides():
    """A sequence of builds reaches a different place on the two sides."""
    old = drive_sequence(drive_old, SEQUENCE)
    new = drive_sequence(drive_new, SEQUENCE)
    assert old["stopped_at"] is None, old
    assert len(old["kept"]) == len(SEQUENCE), old
    assert new == old, f"surface {new!r}, shipped {old!r}"


def test_a_sequence_that_refuses_part_way_keeps_what_it_recorded():
    """A refusal part way through loses the steps that already ran."""
    old = drive_sequence(drive_old, REFUSING_SEQUENCE)
    new = drive_sequence(drive_new, REFUSING_SEQUENCE)
    assert old["stopped_at"] == 2, old
    assert old["step_name"] == "padding_too_short", old
    assert old["refusal"] == "TypeError", old
    assert len(old["kept"]) == 2, old
    assert new == old, f"surface {new!r}, shipped {old!r}"


def test_the_sequence_recorder_reports_a_sequence_that_finishes():
    """The recorder reports a refusal whatever a sequence does."""
    finished = drive_sequence(drive_new, SEQUENCE)
    assert finished["refusal"] is None, finished
    assert finished["stopped_at"] is None, finished


# ---------------------------------------------------------------------
# Enumerating the shipped file
# ---------------------------------------------------------------------


def parsed(source: str):
    return ast.parse(source)


def declared_classes(source: str) -> dict:
    """Every class the file declares, with the bases it names."""
    return {
        node.name: [ast.unparse(base) for base in node.bases]
        for node in ast.walk(parsed(source))
        if isinstance(node, ast.ClassDef)
    }


def declared_functions(source: str) -> list:
    """Every function and method the file declares, in file order."""
    return sorted(
        node.name
        for node in ast.walk(parsed(source))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def import_aliases(source: str) -> dict:
    """Every imported name mapped to the name the file calls it by."""
    found: dict = {}
    for node in ast.walk(parsed(source)):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                found[alias.asname or alias.name] = alias.name
    return found


def constructor_calls(source: str) -> list:
    """Every call by a plain name, resolved through its import alias."""
    aliases = import_aliases(source)
    return sorted(
        aliases.get(node.func.id, node.func.id)
        for node in ast.walk(parsed(source))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    )


def method_calls(source: str, name: str) -> list:
    """Every line calling one method by name, from the parsed file."""
    return [
        node.lineno
        for node in ast.walk(parsed(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    ]


def test_the_shipped_file_declares_four_classes_and_four_methods():
    """A class or a method was added to the shipped file and not carried."""
    classes = declared_classes(SHIPPED_SOURCE)
    assert classes == {
        "CardStyle": [],
        "StatCard": ["QFrame"],
        "ColumnSpec": [],
        "ColumnarTableWidget": ["QTableWidget"],
    }, classes
    assert declared_functions(SHIPPED_SOURCE) == [
        "__init__",
        "__init__",
        "_apply_value_style",
        "set_value",
    ], declared_functions(SHIPPED_SOURCE)


def test_the_class_counter_finds_a_class_it_is_shown():
    """The class counter reports nothing whatever a file declares."""
    found = declared_classes("class Inner(Base):\n    pass\n")
    assert found == {"Inner": ["Base"]}, found


def test_the_function_counter_finds_a_method_inside_a_class():
    """The function counter reads module level only."""
    found = declared_functions("class A:\n    def b(self):\n        pass\n")
    assert found == ["b"], found


def test_the_shipped_file_connects_nothing_and_starts_nothing():
    """The shipped package grew a signal, a timer or a thread."""
    for name in ("connect", "emit", "start", "subscribe", "publish"):
        assert method_calls(SHIPPED_SOURCE, name) == [], name
    assert surface.SIGNALS == ()
    assert surface.ACTIONS == {}
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert surface.BUS_TOPICS == ()
    assert surface.THREADS == ()


def test_the_connect_reader_counts_a_site_a_text_search_also_finds():
    """The connect reader reports nothing whatever a file wires."""
    wired = "b.clicked.connect(self.go)\nfor x in y:\n    x.moved.connect(self.go)\n"
    assert method_calls(wired, "connect") == [1, 3]
    assert SHIPPED_SOURCE.count(".connect(") == 0


def test_the_connect_reader_ignores_a_call_written_in_a_comment():
    """A construction inside prose inflates a text count."""
    prose = "# a.clicked.connect(self.go)\nb.moved.connect(self.go)\n"
    assert method_calls(prose, "connect") == [2]
    assert prose.count(".connect(") == 2


def test_the_constructor_counter_resolves_an_import_alias():
    """An aliased import reads as a name the counter never counts."""
    aliased = "from x import Widget as W\nW()\nW()\n"
    assert constructor_calls(aliased) == ["Widget", "Widget"]


def test_the_shipped_file_builds_the_widgets_the_surface_describes():
    """The shipped file builds something the surface does not carry."""
    built = constructor_calls(SHIPPED_SOURCE)
    assert built.count("CardStyle") == 3, built
    assert built.count("ColumnSpec") == 1, built
    assert built.count("QLabel") == 2, built
    assert built.count("QVBoxLayout") == 1, built
    assert built.count("MappingProxyType") == 2, built


def test_the_shipped_file_builds_no_timer_and_no_thread():
    """A timer or a thread built and never started reads as none.

    `.start(` finds a timer that was started. One built and left alone
    reaches no such call, so the whole constructor set is listed here
    instead: a new name has to be added on purpose.
    """
    assert sorted(set(constructor_calls(SHIPPED_SOURCE))) == [
        "CardStyle",
        "ColumnSpec",
        "MappingProxyType",
        "QLabel",
        "QVBoxLayout",
        "dataclass",
        "len",
        "list",
        "str",
        "super",
        "type",
    ], sorted(set(constructor_calls(SHIPPED_SOURCE)))


def test_the_constructor_set_reports_a_timer_a_file_builds():
    """The constructor set reports nothing whatever a file builds."""
    built = "from PySide6.QtCore import QTimer\nt = QTimer()\n"
    assert constructor_calls(built) == ["QTimer"]


def test_the_shipped_file_sets_five_style_sheets_and_two_names():
    """A style sheet or an accessible name was added or lost."""
    assert len(method_calls(SHIPPED_SOURCE, "setStyleSheet")) == 3
    assert len(method_calls(SHIPPED_SOURCE, "setAccessibleName")) == 2


def count_style_sheet_calls(build):
    """How many times `build` reaches `setStyleSheet` while it runs."""
    real = QWidget.__dict__["setStyleSheet"]
    calls: list = []

    def watched(widget, sheet):
        calls.append(type(widget).__name__)
        return real(widget, sheet)

    setattr(QWidget, "setStyleSheet", watched)
    try:
        kept = build()
    finally:
        setattr(QWidget, "setStyleSheet", real)
    return kept, calls


def test_a_skinned_card_sets_three_style_sheets_at_run_time():
    """A source line inside a helper sets more sheets than it reads as.

    Three source lines write a sheet. A skinned card runs all three
    while it is built, and every later amount runs the value line again,
    so the run-time count is higher than the count of lines.
    """
    card, built = count_style_sheet_calls(lambda: StatCard("L", "V", style=STOCK_CARD))
    assert built == ["StatCard", "QLabel", "QLabel"], built
    _again, after = count_style_sheet_calls(lambda: card.set_value("V2", "#ff0000"))
    assert after == ["QLabel"], after


def test_an_unskinned_card_sets_two_style_sheets_at_run_time():
    """A skin with no surface writes the frame rule anyway."""
    _card, built = count_style_sheet_calls(lambda: StatCard("L", "V"))
    assert built == ["QLabel", "QLabel"], built


def test_the_style_sheet_counter_reports_a_call_it_is_shown():
    """The style sheet counter reports nothing whatever a build does."""
    _widget, built = count_style_sheet_calls(
        lambda: QLabel("x").setStyleSheet("color: #ff0000;")
    )
    assert built == ["QLabel"], built
    _quiet, none = count_style_sheet_calls(lambda: QLabel("x"))
    assert none == [], none


# ---------------------------------------------------------------------
# The comparison is complete
# ---------------------------------------------------------------------


def leaves(value) -> set:
    """Every leaf inside one value, as the text a comparison reads.

    Containers are walked to the bottom: comparing a dict as one string
    reads every constant inside it as missing.
    """
    found: set = set()
    if isinstance(value, dict):
        for key, inner in value.items():
            found.add(repr(key))
            found |= leaves(inner)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for inner in value:
            found |= leaves(inner)
    else:
        found.add(repr(value))
    return found


def values_of(payload) -> set:
    """Every value inside one answer, with the answer own keys left out."""
    found: set = set()
    if isinstance(payload, dict):
        for inner in payload.values():
            found |= values_of(inner)
    elif isinstance(payload, (list, tuple, set, frozenset)):
        for inner in payload:
            found |= values_of(inner)
    else:
        found.add(repr(payload))
    return found


def surface_constants() -> dict:
    """Every value the surface declares at module level."""
    return {
        name: getattr(surface, name)
        for name in dir(surface)
        if name.isupper() and not name.startswith("_")
    }


def snapshot() -> dict:
    """One answer wide enough to carry every value the surface exports."""
    return surface.view_model(
        {
            "label": "Realised",
            "value": "$1234.56",
            "skin": dict(FULL_SKIN),
            "set_value": "$99.00",
            "set_colour": "#ff5577",
            "spec": {
                "labels": ("Bot ID", "Symbol", "Mode"),
                "tooltips": {1: "what the symbol means"},
                "fixed_widths": {2: 70},
                "accessible_name": "Demo Table",
            },
            "stretched": True,
        }
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A constant the comparison never reads passes whatever it holds."""
    carried = leaves(snapshot())
    missing = sorted(
        name
        for name, value in surface_constants().items()
        if not leaves(value) <= carried
    )
    assert missing == [], missing


DRIVEN_INTO_THE_SNAPSHOT = {
    "Realised",
    "$1234.56",
    "$99.00",
    "#ff5577",
    "Bot ID",
    "Symbol",
    "Mode",
    "Demo Table",
    "what the symbol means",
    "Every Field Set",
    "StatCard { background: #0e1428; border: 1px solid #1a2a4f; "
    "border-radius: 5px; }",
    "color: #6688aa; font-size: 11px;",
    "color: #ff5577; font-size: 19px; font-weight: bold;",
    0,
    1,
    2,
    3,
    5,
    7,
    9,
    11,
    19,
    70,
}


def test_every_value_in_the_snapshot_is_backed_by_a_declared_one():
    """A value in the answer is backed by nothing the surface declares."""
    declared = set()
    for value in surface_constants().values():
        declared |= leaves(value)
    declared |= {repr(one) for one in DRIVEN_INTO_THE_SNAPSHOT}
    unbacked = sorted(values_of(snapshot()) - declared)
    assert unbacked == [], unbacked


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check reports nothing whatever the answer drops."""
    carried = leaves({"card": {"radius": 5}})
    assert not leaves({"radius": 6}) <= carried
    assert leaves({"radius": 5}) <= carried


def test_the_unbacked_value_check_can_report_an_invented_value():
    """The unbacked-value check reports nothing whatever an answer invents."""
    declared = values_of({"a": 1})
    assert sorted(values_of({"a": 1, "b": 2}) - declared) == ["2"]
    assert sorted(values_of({"a": 1}) - declared) == []


def test_the_value_reader_leaves_the_answer_own_key_names_out():
    """The value reader counts a key name as a value the surface must hold."""
    assert values_of({"radius": 5}) == {"5"}
    assert leaves({"radius": 5}) == {"'radius'", "5"}


def test_the_leaf_reader_walks_into_a_dictionary():
    """The leaf reader compares a container as text, so a value inside it
    reads as missing whatever it holds."""
    assert leaves({"skin": {"radius": 5}}) == {"'skin'", "'radius'", "5"}


def test_the_surface_grew_no_name_the_file_does_not_declare():
    """A name reached the module without being written in the file."""
    written = {
        node.targets[0].id
        for node in parsed(SURFACE_SOURCE).body
        if isinstance(node, ast.Assign)
        and node.targets
        and isinstance(node.targets[0], ast.Name)
    }
    written |= {
        node.target.id
        for node in parsed(SURFACE_SOURCE).body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    imported = set(surface_constants())
    assert imported - written == set(), sorted(imported - written)
    assert {name for name in written if name.isupper()} - imported == set()


# ---------------------------------------------------------------------
# Pictures
# ---------------------------------------------------------------------


def card_payload(spec):
    """The card half of one case's answer, stamped as it comes off."""
    return sealed(surface_answer(spec)["card"])


def table_payload(spec):
    """The table half of one case's answer, stamped as it comes off."""
    return sealed(surface_answer(spec)["table"])


def card_painted_by_the_widget(spec):
    """The shipped card for one case."""
    with QtSeams():
        card = CARD_CLASSES[spec["class_name"]](
            spec["label"], spec["value"], style=style_of(spec)
        )
    return card


def card_painted_by_the_model(payload):
    """A card built only from the surface's answer, with no shipped class."""
    payload = unaltered(payload)
    frame = ModelCard(payload["accessible_name"])
    frame.setFrameShape(QFrame.StyledPanel)
    if payload["frame_style_sheet"]:
        frame.setStyleSheet(
            payload["frame_style_sheet"].replace(
                payload["class_name"], ModelCard.__name__, 1
            )
        )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(*payload["layout"]["margins_px"])
    layout.setSpacing(payload["layout"]["spacing_px"])
    label = QLabel(payload["label"]["text"])
    label.setStyleSheet(payload["label"]["style_sheet"])
    value = QLabel(payload["value"]["text"])
    value.setStyleSheet(payload["value"]["style_sheet"])
    layout.addWidget(label)
    layout.addWidget(value)
    return frame


def fill_table(table, rows):
    """Put the same cells into either side's table."""
    table.setRowCount(rows)
    for row in range(rows):
        for column in range(table.columnCount()):
            table.setItem(row, column, QTableWidgetItem(f"r{row}c{column}"))
    return table


def table_painted_by_the_widget(spec, rows=2):
    """The shipped table for one case, with cells in it."""
    with QtSeams() as seams:
        table, _asked = shipped_table(spec, seams)
    return fill_table(table, rows)


def table_painted_by_the_model(payload, rows=2):
    """A table built only from the surface's answer, with no shipped class."""
    payload = unaltered(payload)
    table = QTableWidget()
    if payload["accessible_name"]:
        table.setAccessibleName(payload["accessible_name"])
    table.setColumnCount(payload["column_count"])
    table.setHorizontalHeaderLabels(list(payload["headers"]))
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    for at, mode in enumerate(payload["resize_modes"]):
        if mode == surface.RESIZE_FIXED:
            header.setSectionResizeMode(at, QHeaderView.Fixed)
            table.setColumnWidth(at, payload["fixed_widths"][str(at)])
    table.setAlternatingRowColors(payload["alternating_row_colours"])
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.verticalHeader().setVisible(payload["vertical_header_visible"])
    for at, tip in enumerate(payload["tooltips"]):
        if tip:
            table.horizontalHeaderItem(at).setToolTip(tip)
    return fill_table(table, rows)


PICTURE_CASES = ("happy", "stock_preset", "metric_preset", "every_field_set")


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_paint_one_card_and_carry_one_skin(name):
    """The surface's card paints a different picture than the shipped one."""
    spec = BY_NAME[name]
    assert_same_skin(
        build_old_side=lambda: card_painted_by_the_widget(spec),
        build_new_side=lambda: card_painted_by_the_model(card_payload(spec)),
        size=CARD_SIZE,
        control_rule=CONTROL_RULE,
        note=f"card {name}",
    )


@pytest.mark.parametrize("name", ("happy", "tooltips_and_widths"))
def test_the_two_sides_paint_one_table_and_carry_one_skin(name):
    """The surface's table paints a different picture than the shipped one."""
    spec = BY_NAME[name]
    assert_same_skin(
        build_old_side=lambda: table_painted_by_the_widget(spec),
        build_new_side=lambda: table_painted_by_the_model(table_payload(spec)),
        size=TABLE_SIZE,
        control_rule=CONTROL_RULE,
        note=f"table {name}",
    )


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_painted_card_shows_more_than_one_colour(name):
    """A card painting one colour compares alike whatever it was told."""
    from tests.qt_pixel import render_widget

    spec = BY_NAME[name]
    found = assert_picture_can_report(
        render_widget(card_painted_by_the_widget(spec), CARD_SIZE), note=name
    )
    assert found > 1, found


def test_the_picture_comparison_can_report_a_difference():
    """Two different real inputs paint one picture, so no render reports."""
    from tests.qt_pixel import render_widget

    assert_cases_paint_differently(
        old_side=render_widget(
            card_painted_by_the_widget(BY_NAME["stock_preset"]), CARD_SIZE
        ),
        new_side=render_widget(
            card_painted_by_the_model(card_payload(BY_NAME["metric_preset"])),
            CARD_SIZE,
        ),
        note="stock against metric",
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reaches a render and measures the host's fonts."""
    payload = card_payload(BY_NAME["stock_preset"])
    payload["accessible_name"] = "moved"
    with pytest.raises(AssertionError):
        card_painted_by_the_model(payload)


def test_the_host_font_question_is_asked_and_not_assumed():
    """A fixed answer about this host's fonts pins the machine it ran on."""
    assert has_real_fonts() in (True, False)


def test_two_equal_length_labels_paint_one_card_without_fonts():
    """Without fonts the card's picture proves the skin, not the text."""
    from tests.qt_pixel import render_widget
    from tests.fixtures.surface_pictures import (
        assert_pictures_differ,
        assert_pictures_match,
    )

    narrow = card_painted_by_the_widget(
        case("narrow", label=NARROW_LABEL, value=NARROW_LABEL, preset="stock")
    )
    wide = card_painted_by_the_widget(
        case("wide", label=WIDE_LABEL, value=WIDE_LABEL, preset="stock")
    )
    first = render_widget(narrow, CARD_SIZE)
    second = render_widget(wide, CARD_SIZE)
    if has_real_fonts():
        assert_pictures_differ(old_side=first, new_side=second, note="with fonts")
    else:
        assert_pictures_match(old_side=first, new_side=second, note="no fonts")


def test_the_card_and_table_colour_counts_are_reported():
    """A render painting too few colours reports nothing it is compared to."""
    from tests.qt_pixel import render_widget
    from tests.fixtures.surface_pictures import colour_count

    counts = {
        "default card": colour_count(
            render_widget(card_painted_by_the_widget(BY_NAME["happy"]), CARD_SIZE)
        ),
        "stock card": colour_count(
            render_widget(
                card_painted_by_the_widget(BY_NAME["stock_preset"]), CARD_SIZE
            )
        ),
        "table": colour_count(
            render_widget(table_painted_by_the_widget(BY_NAME["happy"]), TABLE_SIZE)
        ),
    }
    assert all(found > 1 for found in counts.values()), counts


# ---------------------------------------------------------------------
# Order, shared state, the home directory and the world
# ---------------------------------------------------------------------


def test_every_swapped_name_is_put_back_after_a_drive_and_after_a_refusal():
    """A swapped name outlived its drive and reached the next test."""
    plain = drive_old(BY_NAME["happy"])
    assert plain["seams"].restored() is True
    with pytest.raises(TypeError):
        drive_old(BY_NAME["padding_too_short"])
    assert (
        QLayout.__dict__["setContentsMargins"]
        is plain["seams"].saved[(QLayout, "setContentsMargins")]
    )
    assert (
        QBoxLayout.__dict__["setSpacing"]
        is plain["seams"].saved[(QBoxLayout, "setSpacing")]
    )
    assert (
        QTableView.__dict__["setColumnWidth"]
        is plain["seams"].saved[(QTableView, "setColumnWidth")]
    )


def test_the_swap_watcher_reports_a_name_that_was_not_put_back():
    """The swap watcher answers restored whatever the names hold."""
    seams = QtSeams()
    with seams:
        assert seams.restored() is False
    assert seams.restored() is True
    saved = seams.saved[(QBoxLayout, "setSpacing")]
    setattr(QBoxLayout, "setSpacing", lambda layout, value: None)
    try:
        assert seams.restored() is False
    finally:
        setattr(QBoxLayout, "setSpacing", saved)
    assert seams.restored() is True


def test_a_case_reads_the_same_whatever_ran_before_it():
    """A driven case depends on what another case left behind."""
    first = digest(compared(drive_new(BY_NAME["happy"])))
    for name in ("stock_preset", "metric_preset", "every_field_set"):
        drive_new(BY_NAME[name])
    assert digest(compared(drive_new(BY_NAME["happy"]))) == first


def test_the_shipped_presets_are_the_same_objects_after_every_drive():
    """A drive edited a preset every widget in the folder shares."""
    before = (repr(STOCK_CARD), repr(METRIC_CARD), repr(StatCard.STYLE))
    for spec in CASES:
        drive_old(spec)
        drive_new(spec)
    assert (repr(STOCK_CARD), repr(METRIC_CARD), repr(StatCard.STYLE)) == before


def test_the_surface_hands_out_a_copy_of_each_preset():
    """A caller editing one answer changed the preset the next one reads."""
    first = surface.view_model({})["presets"]["stock"]
    first["radius"] = 999
    assert surface.view_model({})["presets"]["stock"]["radius"] == ds.RADIUS_SM
    model = surface.CardModel("L", "V", surface.STOCK_CARD)
    model.skin["radius"] = 999
    assert surface.STOCK_CARD["radius"] == ds.RADIUS_SM


@pytest.fixture
def refuse_outside_connections(monkeypatch):
    """Count and refuse every outward connection this test attempts.

    The counter watches this process only. A child process opens its own
    sockets and is never seen here; the subprocess probes below carry
    their own refusal.
    """
    attempted: list = []
    real_connect = socket.socket.connect

    def outside(address) -> bool:
        host = address[0] if isinstance(address, tuple) else address
        return str(host) not in LOOPBACK

    def refuse(address):
        attempted.append(address)
        raise OSError("this test may not reach outside the process")

    def watched_connect(self, address, *found, **named):
        if outside(address):
            return refuse(address)
        return real_connect(self, address, *found, **named)

    monkeypatch.setattr(socket.socket, "connect", watched_connect)
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda address, *_found, **_named: refuse(address),
    )
    yield attempted


def test_no_driven_case_reaches_outside_the_process(refuse_outside_connections):
    """A driven case opened a socket to a host."""
    for spec in CASES:
        drive_new(spec)
        drive_old(spec)
    assert refuse_outside_connections == [], refuse_outside_connections


def test_the_connection_counter_reports_two_real_outside_addresses(
    refuse_outside_connections,
):
    """The connection counter reports nothing whatever a test reaches for."""
    first = ("api.exchange.coinbase.com", 443)
    second = ("api.alpaca.markets", 443)
    with pytest.raises(OSError):
        socket.create_connection(first, timeout=1)
    with pytest.raises(OSError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(second)
    assert len(refuse_outside_connections) == 2, refuse_outside_connections
    assert first in refuse_outside_connections


def test_no_driven_case_writes_a_file_under_a_throwaway_home(tmp_path, monkeypatch):
    """A driven case wrote into the operator's own tree."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACERVATOR_TEST_HOME", str(home))
    for spec in CASES:
        drive_new(spec)
        drive_old(spec)
    assert sorted(home.rglob("*")) == [], sorted(home.rglob("*"))


def test_the_throwaway_home_check_reports_a_file_that_was_written(tmp_path):
    """The throwaway-home check reports nothing whatever a run writes."""
    home = tmp_path / "home"
    home.mkdir()
    assert sorted(home.rglob("*")) == []
    (home / "seeded.json").write_text("{}", encoding="utf-8", newline="\n")
    assert sorted(home.rglob("*")) == [home / "seeded.json"]


# ---------------------------------------------------------------------
# The bridge, and a process that never loads Qt
# ---------------------------------------------------------------------


def test_the_bridge_registers_the_widgets_package_method():
    """The Electron renderer cannot reach the shared widget skins."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD == METHOD_NAME
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model


def test_the_bridge_import_list_is_in_order():
    """A surface added out of order in the bridge's import list."""
    from src.core import desktop_bridge

    source = Path(desktop_bridge.__file__).read_text(encoding="utf-8")
    named = [
        [alias.name for alias in node.names]
        for node in ast.walk(parsed(source))
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs"
    ]
    assert len(named) == 1, named
    assert named[0] == sorted(named[0]), named[0]
    assert "widgets_package_surface" in named[0]


def test_the_bridge_answer_is_json_serialisable():
    """A value in the answer cannot cross the bridge."""
    answered = surface.view_model(
        {
            "label": "Realised",
            "value": "$1234.56",
            "preset": "stock",
            "spec": {
                "labels": ["Bot ID", "Symbol"],
                "fixed_widths": {1: 70},
                "tooltips": {0: "the id"},
                "accessible_name": "Demo Table",
            },
        }
    )
    text = json.dumps(answered)
    assert json.loads(text)["table"]["column_count"] == 2


def test_an_unknown_preset_is_refused():
    """A preset the package never carries builds a card anyway."""
    with pytest.raises(KeyError):
        surface.view_model({"preset": "no_such_preset"})


BRIDGE_PROBE = (
    "import json, sys\n"
    "from src.core import desktop_bridge\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1, 'method':"
    " 'widgets_package.state', 'params': {'preset': 'stock', 'label':"
    " 'Realised', 'value': '$1234.56', 'spec': {'labels': ['Bot ID',"
    " 'Symbol', 'Mode'], 'fixed_widths': {'2': 70}}}}),"
    " desktop_bridge.build_registry())\n"
    "print(json.dumps({'frame': frame, 'qt': [name for name in sys.modules"
    " if name.startswith('PySide6')]}))\n"
)

NOTHING_AT_IMPORT_PROBE = """
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-widgets-probe-'))
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

opened_before = len(opened)
clock_before = len(clock)
threads_before = threading.active_count()
from src.gui.main_tabs import widgets_package_surface as s

opened_at_import = opened[opened_before:]
clock_at_import = clock[clock_before:]
threads_at_import = threading.active_count() - threads_before
built = s.view_model({'preset': 'stock'})
answer = {'radius': s.STOCK_CARD['radius'],
          'built_on_request': built['card']['frame_style_sheet'] != '',
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
    """Reaching the shared skins pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] == [], answered["qt"]
    assert answered["frame"]["ok"] is True, answered["frame"]
    result = answered["frame"]["result"]
    assert result["card"]["frame_style_sheet"] == (
        "StatCard { background: #0e1428; border: 1px solid #1a2a4f; "
        "border-radius: 8px; }"
    )
    assert result["table"]["headers"] == ["Bot ID", "Symbol", "Mode"]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore\n" + BRIDGE_PROBE)
    assert loaded["qt"] != []
    assert loaded["frame"]["ok"] is True


def test_importing_the_surface_reads_no_file_and_no_clock():
    """Loading the surface read a file, read the clock or started a thread."""
    answered = run_script(NOTHING_AT_IMPORT_PROBE)
    assert answered["qt"] == [], answered["qt"]
    assert answered["clock_at_import"] == [], answered
    assert answered["threads_at_import"] == 0, answered
    assert answered["reached_at_import"] == [], answered
    assert answered["made_under_home"] == [], answered
    assert [
        one for one in answered["opened_at_import"] if "widgets_package" in one
    ] == [], answered
    assert answered["radius"] == ds.RADIUS_SM
    assert answered["built_on_request"] is True
    assert answered["method"] == METHOD_NAME


def test_the_import_probe_can_report_a_file_a_clock_and_a_connection():
    """The import probe reports nothing whatever the module does."""
    probe = NOTHING_AT_IMPORT_PROBE.replace(
        "from src.gui.main_tabs import widgets_package_surface as s",
        "time.time()\n"
        "with open(root / 'widgets_package-seeded.json', 'w') as fh:\n"
        "    fh.write('{}')\n"
        "try:\n"
        "    socket.create_connection(('example.invalid', 443))\n"
        "except OSError:\n"
        "    pass\n"
        "threading.Thread(target=lambda: None).start()\n"
        "from src.gui.main_tabs import widgets_package_surface as s",
    )
    answered = run_script(probe)
    assert answered["clock_at_import"] == ["time"], answered
    assert answered["reached_at_import"] != [], answered
    assert answered["made_under_home"] != [], answered
    assert [
        one for one in answered["opened_at_import"] if "widgets_package" in one
    ] != [], answered


def test_the_surface_loads_no_qt_module_and_reaches_for_nothing():
    """The surface grew an import that pulls Qt into the backend."""
    tree = parsed(SURFACE_SOURCE)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    reached = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in ("read_text", "write_text", "mkdir", "urlopen", "monotonic"):
        assert forbidden not in reached, forbidden


def test_the_import_scan_reports_a_module_the_shipped_file_does_load():
    """The import scan reports nothing whatever a file imports."""
    imported = {
        node.module or ""
        for node in ast.walk(parsed(SHIPPED_SOURCE))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in imported), imported


def test_the_surface_reads_no_value_out_of_the_shipped_file():
    """The surface copies the shipped file rather than carrying its own."""
    named = {
        node.module or ""
        for node in ast.walk(parsed(SURFACE_SOURCE))
        if isinstance(node, ast.ImportFrom)
    }
    assert "src.gui.widgets" not in named, named
    assert not any(name.endswith("widgets") for name in named), named


def test_the_tokens_the_two_sides_read_come_from_design_system():
    """A token was copied instead of read, so the two sides can drift."""
    assert surface.DEFAULT_CARD["label_size"] == ds.TYPE_CAPTION
    assert surface.DEFAULT_CARD["value_size"] == ds.TYPE_CARD_VALUE
    assert surface.STOCK_CARD["surface"] == ds.CARD_STOCK_SURFACE
    assert surface.STOCK_CARD["border"] == ds.CARD_STOCK_BORDER
    assert surface.METRIC_CARD["surface"] == ds.CARD_METRIC_SURFACE
    assert surface.METRIC_CARD["radius"] == ds.RADIUS_CARD
    assert CardStyle.label_size == ds.TYPE_CAPTION
    assert STOCK_CARD.surface == ds.CARD_STOCK_SURFACE


def flat_colours(skins) -> list:
    """Every colour whose channels all match, which a swap cannot report."""
    return sorted(
        f"{name}={value}"
        for skin in skins.values()
        for name, value in skin.items()
        if isinstance(value, str) and value.startswith("#") and len(set(value[1:])) == 1
    )


def test_only_the_metric_caption_colour_has_three_equal_channels():
    """A card colour a channel swap cannot report was added or removed.

    `#888` is the shipped metric caption colour. Swapping its channels
    paints the same pixel, so no picture proves that one; every other
    card colour is proved by the swap check below.
    """
    assert flat_colours(surface.PRESETS) == ["label_color=#888"]
    assert ds.CARD_METRIC_LABEL == "#888"


def test_the_channel_reader_reports_a_colour_whose_channels_match():
    """The channel reader reports nothing whatever a colour holds."""
    assert flat_colours({"a": {"c": "#888"}}) == ["c=#888"]
    assert flat_colours({"a": {"c": "#0e1428"}}) == []


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """A swapped colour channel reaches no comparison."""
    swapped = dict(surface.STOCK_CARD)
    swapped["surface"] = "#28140e"
    assert digest(swapped) != digest(surface.STOCK_CARD)


def test_this_file_imports_only_what_the_fast_lane_installs():
    """This file needs a package the CI fast lane never installs."""
    from tests.test_ci_fast_lane_packages import offending_imports

    offences = [
        line
        for line in offending_imports(REPO_ROOT / "tests")
        if Path(__file__).name in line
    ]
    assert offences == [], offences
