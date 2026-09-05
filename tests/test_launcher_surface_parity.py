"""The Qt Launcher screen and the Qt-free surface, driven side by side.

A failure means the view model describes a different card, a different
colour, a different text, a different layout number, a different button,
a different gradient or a different branch than ``LauncherWindow`` and
``ModeCard`` build on the same input.
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

from src.gui.main_tabs import launcher_surface as surface
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
LAUNCHER_SOURCE = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

WINDOW_SIZE = (surface.WINDOW_WIDTH_PX, surface.WINDOW_HEIGHT_PX)
CARD_SIZE = (surface.CARD_WIDTH_PX, surface.CARD_HEIGHT_PX)

CONNECT_TOTAL = 3
SHIPPED_CLASS_TOTAL = 2
SHIPPED_METHOD_TOTAL = 4
SIGNAL_TOTAL = 3
PAYLOAD_KEY_TOTAL = 33
CONSTANT_TOTAL = 99
WINDOW_CHILD_TOTAL = 5
CARD_CHILD_TOTAL = 12


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


# The inputs. One table for the card's five fields, one for the presses.


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "₿ éèê BTC 交易 \U0001f680"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "the operator's own card"


def fields(**named):
    """One set of the five values a card is built from."""
    spec = {
        "title": surface.CRYPTO_TITLE,
        "subtitle": surface.CRYPTO_SUBTITLE,
        "icon_char": surface.CRYPTO_ICON,
        "color": surface.CRYPTO_COLOR,
        "features": list(surface.CRYPTO_FEATURES),
    }
    spec.update(named)
    return spec


FIELD_SPECS = {
    "happy_crypto": fields(),
    "happy_stocks": fields(
        title=surface.STOCKS_TITLE,
        subtitle=surface.STOCKS_SUBTITLE,
        icon_char=surface.STOCKS_ICON,
        color=surface.STOCKS_COLOR,
        features=list(surface.STOCKS_FEATURES),
    ),
    "empty_everywhere": fields(title="", subtitle="", icon_char="", features=[]),
    "empty_colour": fields(color=""),
    "nothing_everywhere": fields(title=None, subtitle=None, icon_char=None, color=None),
    "one_feature": fields(features=["only one"]),
    "zero_as_a_feature": fields(features=[0]),
    "negative_as_a_feature": fields(features=[-42, -0.5]),
    "a_thousand_million_as_a_feature": fields(features=[1_000_000_000, 1e9]),
    "one_billionth_as_a_feature": fields(features=[1e-9]),
    "infinity_as_a_feature": fields(features=[math.inf, -math.inf]),
    "unicode": fields(
        title=UNICODE_TEXT,
        subtitle=UNICODE_TEXT,
        icon_char=UNICODE_TEXT,
        features=[UNICODE_TEXT],
    ),
    "two_hundred_characters": fields(
        title=LONG_TEXT, subtitle=LONG_TEXT, features=[LONG_TEXT]
    ),
    "markup_inside_a_text_field": fields(
        title=MARKUP_TEXT, subtitle=MARKUP_TEXT, features=[MARKUP_TEXT]
    ),
    "an_apostrophe": fields(
        title=APOSTROPHE_TEXT, subtitle=APOSTROPHE_TEXT, features=[APOSTROPHE_TEXT]
    ),
    "wrong_capitals": fields(
        title="crypto trading", subtitle="MULTI-EXCHANGE", features=["gRID bOT"]
    ),
    "a_name_with_a_newline": fields(
        title=NEWLINE_TEXT, subtitle=NEWLINE_TEXT, features=[NEWLINE_TEXT]
    ),
    "a_colour_written_in_full": fields(color="#00ffccff"),
    "a_colour_that_names_nothing": fields(color="notacolour"),
    "a_number_where_a_title_belongs": fields(title=42),
    "a_number_where_a_subtitle_belongs": fields(subtitle=42),
    "a_number_where_an_icon_belongs": fields(icon_char=42),
    "infinity_where_a_title_belongs": fields(title=math.inf),
    "a_number_where_a_colour_belongs": fields(color=42),
    "a_number_where_the_feature_list_belongs": fields(features=42),
    "nothing_where_the_feature_list_belongs": fields(features=None),
    "text_where_the_feature_list_belongs": fields(features="abc"),
}

FIELD_NAMES = sorted(FIELD_SPECS)

# Every case the shipped card refuses, and the surface with it.
REFUSING_FIELD_SPECS = (
    "a_number_where_a_title_belongs",
    "a_number_where_a_subtitle_belongs",
    "a_number_where_an_icon_belongs",
    "infinity_where_a_title_belongs",
    "a_number_where_the_feature_list_belongs",
    "nothing_where_the_feature_list_belongs",
)

# Qt words these refusals from its own signature list. Type and outcome are
# compared here; the wording is pinned apart.
QT_WORDED_REFUSALS = (
    "a_number_where_a_title_belongs",
    "a_number_where_a_subtitle_belongs",
    "a_number_where_an_icon_belongs",
    "infinity_where_a_title_belongs",
)

CARD_PRESS = surface.CARD_PRESS
BUTTON_PRESS = surface.BUTTON_PRESS

PRESS_SPECS = {
    "nothing_pressed": [],
    "crypto_card_pressed": [[CARD_PRESS, 0]],
    "stocks_card_pressed": [[CARD_PRESS, 1]],
    "crypto_button_pressed": [[BUTTON_PRESS, 0]],
    "stocks_button_pressed": [[BUTTON_PRESS, 1]],
    "both_cards_pressed": [[CARD_PRESS, 0], [CARD_PRESS, 1]],
    "one_card_pressed_twice": [[CARD_PRESS, 0], [CARD_PRESS, 0]],
    "card_then_button": [[CARD_PRESS, 1], [BUTTON_PRESS, 1]],
    "the_last_card": [[CARD_PRESS, -1]],
    "the_first_card_from_the_end": [[BUTTON_PRESS, -2]],
    "a_card_below_the_row": [[CARD_PRESS, -3]],
    "a_card_above_the_row": [[CARD_PRESS, 2]],
    "a_thousand_million": [[CARD_PRESS, 1_000_000_000]],
    "one_billionth": [[CARD_PRESS, 1e-9]],
    "infinity_where_a_position_belongs": [[CARD_PRESS, math.inf]],
    "text_where_a_position_belongs": [[CARD_PRESS, "one"]],
    "nothing_where_a_position_belongs": [[CARD_PRESS, None]],
    "a_press_after_a_bad_press": [[CARD_PRESS, 0], [CARD_PRESS, 9]],
}

PRESS_NAMES = sorted(PRESS_SPECS)

REFUSING_PRESS_SPECS = (
    "a_card_above_the_row",
    "a_card_below_the_row",
    "a_press_after_a_bad_press",
    "a_thousand_million",
    "infinity_where_a_position_belongs",
    "nothing_where_a_position_belongs",
    "one_billionth",
    "text_where_a_position_belongs",
)


# Reading the shipped side


def item_kind(item) -> str:
    """What one layout slot holds: a widget class, a layout class or a gap."""
    if item.widget() is not None:
        return type(item.widget()).__name__
    if item.layout() is not None:
        return type(item.layout()).__name__
    return "stretch" if item.expandingDirections().value else "spacing"


def layout_kinds(layout) -> list:
    """The kind of every slot the layout holds, in the order it was added."""
    return [item_kind(layout.itemAt(index)) for index in range(layout.count())]


def label_state(widget) -> dict:
    """Every value one Qt label can be asked for."""
    return {
        "text": widget.text(),
        "style_sheet": widget.styleSheet(),
        "alignment_value": int(widget.alignment().value),
        "word_wrap": widget.wordWrap(),
    }


def card_parts(card) -> dict:
    """The widgets one shipped card builds, found by walking its layout."""
    layout = card.layout()
    from PySide6.QtWidgets import QLabel, QPushButton

    held = [layout.itemAt(index).widget() for index in range(layout.count())]
    labels = [one for one in held if isinstance(one, QLabel)]
    buttons = [one for one in held if isinstance(one, QPushButton)]
    return {
        "layout": layout,
        "icon": labels[0],
        "title": labels[1],
        "subtitle": labels[2],
        "features": labels[3:],
        "button": buttons[0],
    }


def card_trace(card) -> dict:
    """Every value one built Qt card can be asked for, as plain data."""
    parts = card_parts(card)
    layout = parts["layout"]
    box = layout.contentsMargins()
    return {
        "accessible_name": card.accessibleName(),
        "type_name": card.metaObject().className(),
        "cursor": card.cursor().shape().name,
        "width_px": card.maximumWidth(),
        "height_px": card.maximumHeight(),
        "minimum_size_px": [card.minimumWidth(), card.minimumHeight()],
        "margins_px": [box.left(), box.top(), box.right(), box.bottom()],
        "spacing_px": layout.spacing(),
        "style_sheet": card.styleSheet(),
        "icon": label_state(parts["icon"]),
        "title": label_state(parts["title"]),
        "subtitle": label_state(parts["subtitle"]),
        "features": [label_state(one) for one in parts["features"]],
        "button": {
            "text": parts["button"].text(),
            "style_sheet": parts["button"].styleSheet(),
        },
        "child_kinds": layout_kinds(layout),
        "child_count": layout.count(),
        "gap_px": layout.itemAt(3).sizeHint().height(),
        "shadow_attached": card.graphicsEffect() is not None,
    }


CARD_SLOT_CLASS = {
    "icon": "QLabel",
    "title": "QLabel",
    "subtitle": "QLabel",
    "spacing": "spacing",
    "stretch": "stretch",
    "button": "QPushButton",
}


def slot_classes(order) -> list:
    """The card's child names read as the widget class each one is."""
    return [CARD_SLOT_CLASS.get(name, "QLabel") for name in order]


LABEL_KEYS = ("text", "style_sheet", "alignment_value", "word_wrap")


def surface_card_trace(state) -> dict:
    """The same card values, read from the Qt-free card state."""
    keys = LABEL_KEYS
    return {
        "accessible_name": state["accessible_name"],
        "type_name": state["type_name"],
        "cursor": state["cursor"],
        "width_px": state["width_px"],
        "height_px": state["height_px"],
        "minimum_size_px": [state["width_px"], state["height_px"]],
        "margins_px": state["margins_px"],
        "spacing_px": state["spacing_px"],
        "style_sheet": state["style_sheet"],
        "icon": {key: state["icon"][key] for key in keys},
        "title": {key: state["title"][key] for key in keys},
        "subtitle": {key: state["subtitle"][key] for key in keys},
        "features": [{key: one[key] for key in keys} for one in state["features"]],
        "button": dict(state["button"]),
        "child_kinds": slot_classes(state["child_order"]),
        "child_count": state["child_count"],
        "gap_px": state["gap_px"],
        "shadow_attached": state["shadow"]["attached"],
    }


class ClickCounter:
    """Counts how many times one card said it was clicked."""

    def __init__(self, name, tally):
        self.name = name
        self.tally = tally

    def __call__(self):
        self.tally[self.name] = self.tally[self.name] + 1


class SignalRecorder:
    """Records, in order, which mode the window said to open."""

    def __init__(self, name, fired):
        self.name = name
        self.fired = fired

    def __call__(self):
        self.fired.append(self.name)


def window_card_row(window) -> list:
    """The two shipped cards, in the order the row holds them."""
    row = window.layout().itemAt(3).layout()
    return [row.itemAt(index).widget() for index in range(row.count())]


def drive_old(presses):
    """Build the shipped window, run the presses, and hand it back."""
    from src.gui.launcher import LauncherWindow

    app()
    window = LauncherWindow()
    fired: list = []
    tally = {name: 0 for name in surface.CARD_ORDER}
    window.crypto_selected.connect(SignalRecorder(surface.CRYPTO_SIGNAL, fired))
    window.stocks_selected.connect(SignalRecorder(surface.STOCKS_SIGNAL, fired))
    row = window_card_row(window)
    for name, card in zip(surface.CARD_ORDER, row):
        card.clicked.connect(ClickCounter(name, tally))
    for kind, index in presses:
        card = row[index]
        if kind == BUTTON_PRESS:
            card_parts(card)["button"].click()
        else:
            card.mousePressEvent(None)
    return window, fired, tally


def drive_new(presses):
    """Build the surface model and run the same presses."""
    model = surface.LauncherModel()
    payload = surface.build_view_model(model, presses)
    return model, payload


def window_trace(window, fired, tally) -> dict:
    """Every value the built Qt window can be asked for, as plain data."""
    layout = window.layout()
    box = layout.contentsMargins()
    row = layout.itemAt(3).layout()
    heading = layout.itemAt(0).widget()
    prompt = layout.itemAt(1).widget()
    footer = layout.itemAt(4).widget()
    cards = window_card_row(window)
    return {
        "accessible_name": window.accessibleName(),
        "window": {
            "title": window.windowTitle(),
            "width_px": window.maximumWidth(),
            "height_px": window.maximumHeight(),
            "style_sheet": window.styleSheet(),
            "margins_px": [box.left(), box.top(), box.right(), box.bottom()],
            "spacing_px": layout.spacing(),
        },
        "window_kinds": layout_kinds(layout),
        "heading": label_state(heading),
        "prompt": label_state(prompt),
        "footer": label_state(footer),
        "heading_gap_px": layout.itemAt(2).sizeHint().height(),
        "cards_row": {"spacing_px": row.spacing(), "count": row.count()},
        "cards": {
            name: card_trace(card) for name, card in zip(surface.CARD_ORDER, cards)
        },
        "fired": list(fired),
        "clicks": dict(tally),
    }


WINDOW_SLOT_CLASS = {
    "heading": "QLabel",
    "prompt": "QLabel",
    "spacing": "spacing",
    "cards_row": "QHBoxLayout",
    "footer": "QLabel",
}

FIRED_NAMES = {
    surface.CRYPTO_SELECTED: surface.CRYPTO_SIGNAL,
    surface.STOCKS_SELECTED: surface.STOCKS_SIGNAL,
}


def fired_from(payload) -> list:
    """Which mode the surface said to open, in order."""
    return [FIRED_NAMES[call[0]] for call in payload["calls"] if call[0] in FIRED_NAMES]


def surface_window_trace(payload) -> dict:
    """The same window values, read from the Qt-free view model."""
    keys = ("text", "style_sheet", "alignment_value", "word_wrap")
    return {
        "accessible_name": payload["accessible_name"],
        "window": dict(payload["window"]),
        "window_kinds": [WINDOW_SLOT_CLASS[name] for name in payload["window_order"]],
        "heading": {key: payload["heading"][key] for key in keys},
        "prompt": {key: payload["prompt"][key] for key in keys},
        "footer": {key: payload["footer"][key] for key in keys},
        "heading_gap_px": payload["heading_gap_px"],
        "cards_row": {
            "spacing_px": payload["cards_row"]["spacing_px"],
            "count": len(payload["cards_row"]["order"]),
        },
        "cards": {
            name: surface_card_trace(payload["cards"][name])
            for name in surface.CARD_ORDER
        },
        "fired": fired_from(payload),
        "clicks": {
            name: payload["cards"][name]["clicks"] for name in surface.CARD_ORDER
        },
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


def old_card_outcome(spec) -> dict:
    def read():
        from src.gui.launcher import ModeCard

        app()
        return card_trace(ModeCard(**spec))

    return outcome(read)


def new_card_outcome(spec) -> dict:
    def read():
        return surface_card_trace(surface.ModeCardModel(**spec).state())

    return outcome(read)


def old_window_outcome(presses) -> dict:
    return outcome(lambda: window_trace(*drive_old(presses)))


def new_window_outcome(presses) -> dict:
    return outcome(lambda: surface_window_trace(drive_new(presses)[1]))


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", FIELD_NAMES)
def test_the_two_sides_build_the_same_card(name):
    """A text, colour, style, alignment or child of one card differs."""
    spec = FIELD_SPECS[name]
    old = old_card_outcome(spec)
    new = new_card_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    assert new["value"] == old["value"], name
    assert digest(new["value"]) == digest(old["value"]), name


@pytest.mark.parametrize("name", PRESS_NAMES)
def test_the_two_sides_describe_the_same_screen(name):
    """A text, layout number, card or fired signal differs between them."""
    presses = PRESS_SPECS[name]
    old = old_window_outcome(presses)
    new = new_window_outcome(presses)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        assert new["message"] == old["message"], (name, old, new)
        return
    assert new["value"] == old["value"], name
    assert digest(new["value"]) == digest(old["value"]), name


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever it is given, so it proves nothing."""
    crypto = old_card_outcome(FIELD_SPECS["happy_crypto"])["value"]
    stocks = old_card_outcome(FIELD_SPECS["happy_stocks"])["value"]
    assert crypto != stocks
    assert digest(crypto) != digest(stocks)
    assert digest(crypto) == digest(
        old_card_outcome(FIELD_SPECS["happy_crypto"])["value"]
    )
    assert len(digest(crypto)) == 64


def test_the_hash_tells_two_different_screens_apart():
    """The screen hash returns one value whatever was pressed."""
    quiet = old_window_outcome(PRESS_SPECS["nothing_pressed"])["value"]
    pressed = old_window_outcome(PRESS_SPECS["both_cards_pressed"])["value"]
    assert quiet != pressed
    assert digest(quiet) != digest(pressed)
    assert digest(quiet) == digest(old_window_outcome([])["value"])


@pytest.mark.parametrize(
    "name", ["happy_crypto", "empty_everywhere", "nothing_everywhere"]
)
def test_the_sample_card_hashes_are_reported(name):
    """The comparison passed on a card trace that carries nothing."""
    value = old_card_outcome(FIELD_SPECS[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == 18, sorted(value)
    assert digest(value) == digest(new_card_outcome(FIELD_SPECS[name])["value"])


@pytest.mark.parametrize("name", ["nothing_pressed", "card_then_button"])
def test_the_sample_screen_hashes_are_reported(name):
    """The comparison passed on a screen trace that carries nothing."""
    value = old_window_outcome(PRESS_SPECS[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == 11, sorted(value)
    assert digest(value) == digest(new_window_outcome(PRESS_SPECS[name])["value"])


# Answers and refusals


def test_both_answers_and_refusals_are_in_the_measured_card_set():
    """Every card input was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for name in FIELD_NAMES:
        old = old_card_outcome(FIELD_SPECS[name])
        (answered if old["outcome"] == "answered" else refused).append(name)
    assert answered, "no card input was answered"
    assert refused, "no card input was refused"
    assert set(refused) == set(REFUSING_FIELD_SPECS), sorted(refused)
    assert len(answered) + len(refused) == len(FIELD_SPECS)


def test_both_answers_and_refusals_are_in_the_measured_press_set():
    """Every press was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for name in PRESS_NAMES:
        old = old_window_outcome(PRESS_SPECS[name])
        (answered if old["outcome"] == "answered" else refused).append(name)
    assert answered, "no press was answered"
    assert refused, "no press was refused"
    assert set(refused) == set(REFUSING_PRESS_SPECS), sorted(refused)
    assert len(answered) + len(refused) == len(PRESS_SPECS)


@pytest.mark.parametrize("name", REFUSING_FIELD_SPECS)
def test_a_refused_card_input_names_the_same_error_on_both_sides(name):
    """One side refused a card input the other accepted, or named another error."""
    spec = FIELD_SPECS[name]
    old = old_card_outcome(spec)
    new = new_card_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert new["error"] == old["error"], (name, old, new)
    assert old["error"] == "TypeError"


@pytest.mark.parametrize("name", REFUSING_PRESS_SPECS)
def test_a_refused_press_names_the_same_error_and_wording_on_both_sides(name):
    """One side refused a press the other accepted, or worded it differently."""
    presses = PRESS_SPECS[name]
    old = old_window_outcome(presses)
    new = new_window_outcome(presses)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert (new["error"], new["message"]) == (old["error"], old["message"])
    assert old["error"] in ("IndexError", "TypeError")


@pytest.mark.parametrize("name", QT_WORDED_REFUSALS)
def test_the_two_sides_word_a_text_refusal_differently(name):
    """The two wordings became one, so the pin below states nothing.

    Qt answers a value that is not text with its own list of accepted
    signatures. That wording belongs to the installed Qt build, not to
    the product, so it is not compared. The refusal itself is.
    """
    spec = FIELD_SPECS[name]
    old = old_card_outcome(spec)
    new = new_card_outcome(spec)
    assert old["error"] == new["error"] == "TypeError"
    assert old["message"] != new["message"]
    assert "QLabel" in old["message"]
    assert "QLabel" not in new["message"]
    refused_kind = new["message"].rsplit(" ", 1)[-1]
    assert new["message"] == surface.TEXT_REFUSAL.format(kind=refused_kind)
    assert refused_kind in ("int", "float"), (name, spec, new["message"])


def test_the_feature_list_is_refused_with_the_same_wording_on_both_sides():
    """The feature list refusal is Python's own, so the wording must match."""
    for name in (
        "a_number_where_the_feature_list_belongs",
        "nothing_where_the_feature_list_belongs",
    ):
        old = old_card_outcome(FIELD_SPECS[name])
        new = new_card_outcome(FIELD_SPECS[name])
        assert (old["error"], old["message"]) == (new["error"], new["message"]), name
        assert old["error"] == "TypeError", (name, old)
        assert old["message"], (name, old)


def test_a_text_feature_list_is_read_letter_by_letter_on_both_sides():
    """Text handed in place of a list makes one feature line per letter."""
    old = old_card_outcome(FIELD_SPECS["text_where_the_feature_list_belongs"])
    new = new_card_outcome(FIELD_SPECS["text_where_the_feature_list_belongs"])
    assert old["outcome"] == "answered", old
    assert [one["text"] for one in old["value"]["features"]] == ["  a", "  b", "  c"]
    assert new["value"]["features"] == old["value"]["features"]


# The enumeration: signals, classes, methods, timers, bus topics


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


QT_CONNECT_NAMES = {
    ("btn.clicked", "self.clicked.emit"): (
        "launch_button.clicked",
        "ModeCardModel.emit_clicked",
    ),
    ("crypto_card.clicked", "self.crypto_selected.emit"): (
        "crypto_card.clicked",
        "LauncherModel.crypto_selected",
    ),
    ("stocks_card.clicked", "self.stocks_selected.emit"): (
        "stocks_card.clicked",
        "LauncherModel.stocks_selected",
    ),
}


def test_the_connect_sets_match():
    """The shipped screen connects a signal the surface names no action for."""
    sites = connect_sites(LAUNCHER_SOURCE)
    assert len(sites) == CONNECT_TOTAL, sites
    translated = dict(QT_CONNECT_NAMES[site] for site in sites)
    assert translated == surface.ACTIONS
    assert len(surface.ACTIONS) == CONNECT_TOTAL


def test_the_connect_reader_finds_the_real_sites():
    """The connect reader returns an empty set whatever the source holds."""
    sites = connect_sites(LAUNCHER_SOURCE)
    assert ("btn.clicked", "self.clicked.emit") in sites
    assert LAUNCHER_SOURCE.read_text(encoding="utf-8").count(".connect(") == len(sites)
    assert len(connect_sites(BUS_NEIGHBOUR)) > CONNECT_TOTAL


def test_the_two_sides_hold_the_same_number_of_children():
    """The screen or a card gained or lost a child on one side only."""
    app()
    old = old_window_outcome([])["value"]
    new = new_window_outcome([])["value"]
    assert len(old["window_kinds"]) == WINDOW_CHILD_TOTAL, old["window_kinds"]
    assert len(new["window_kinds"]) == len(old["window_kinds"])
    assert new["window_kinds"] == old["window_kinds"]
    assert old["cards_row"]["count"] == new["cards_row"]["count"] == 2
    for name in surface.CARD_ORDER:
        assert old["cards"][name]["child_count"] == CARD_CHILD_TOTAL, name
        assert new["cards"][name]["child_count"] == old["cards"][name]["child_count"]
        assert new["cards"][name]["child_kinds"] == old["cards"][name]["child_kinds"]
        assert len(new["cards"][name]["features"]) == len(
            old["cards"][name]["features"]
        )


def test_the_child_counter_moves_with_the_feature_list():
    """The child counter reports one number whatever a card holds."""
    app()
    one = old_card_outcome(FIELD_SPECS["one_feature"])["value"]
    six = old_card_outcome(FIELD_SPECS["happy_crypto"])["value"]
    none = old_card_outcome(FIELD_SPECS["empty_everywhere"])["value"]
    assert none["child_count"] < one["child_count"] < six["child_count"]
    assert six["child_count"] == CARD_CHILD_TOTAL
    assert (
        one["child_count"]
        == new_card_outcome(FIELD_SPECS["one_feature"])["value"]["child_count"]
    )
    assert none["child_count"] == len(surface.card_child_order(0))


SHIPPED_METHODS = {
    "ModeCard.__init__": "ModeCardModel.__init__",
    "ModeCard.mousePressEvent": "ModeCardModel.press",
    "LauncherWindow.__init__": "LauncherModel.__init__",
    "LauncherWindow.paintEvent": "gradient",
}

SHIPPED_CLASSES = {
    "ModeCard": "ModeCardModel",
    "LauncherWindow": "LauncherModel",
}

SHIPPED_SIGNALS = {
    "ModeCard.clicked": "ModeCardModel.emit_clicked",
    "LauncherWindow.crypto_selected": "LauncherModel.crypto_selected",
    "LauncherWindow.stocks_selected": "LauncherModel.stocks_selected",
}


def shipped_classes() -> list:
    """Every class the shipped module declares, read off the module object."""
    from src.gui import launcher

    return sorted(
        name
        for name, value in vars(launcher).items()
        if isinstance(value, type) and value.__module__ == launcher.__name__
    )


def shipped_methods() -> list:
    """Every method the shipped classes declare, read off the class objects.

    A declared signal is callable too, so only real functions are
    counted here; the signals are enumerated by ``signal_sites``.
    """
    import types

    from src.gui import launcher

    found = []
    for class_name in shipped_classes():
        held = getattr(launcher, class_name)
        for name, value in vars(held).items():
            if isinstance(value, types.FunctionType) and (
                not name.startswith("__") or name == "__init__"
            ):
                found.append(f"{class_name}.{name}")
    return sorted(found)


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped screen gained or lost a class or a method."""
    classes = shipped_classes()
    assert classes == sorted(SHIPPED_CLASSES), classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    methods = shipped_methods()
    assert methods == sorted(SHIPPED_METHODS), methods
    assert len(methods) == SHIPPED_METHOD_TOTAL
    for counterpart in list(SHIPPED_CLASSES.values()) + list(SHIPPED_METHODS.values()):
        holder, _, attribute = counterpart.partition(".")
        target = getattr(surface, holder)
        assert callable(
            getattr(target, attribute) if attribute else target
        ), counterpart


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing on the Qt side."""
    built = sorted(
        name
        for name, value in vars(surface).items()
        if isinstance(value, type) and value.__module__ == surface.__name__
    )
    assert built == sorted(SHIPPED_CLASSES.values()), built
    assert SHIPPED_CLASSES["LauncherWindow"] == "LauncherModel"


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "LauncherWindow.paintEvent" in SHIPPED_METHODS
    assert not hasattr(surface, "InventedModel")
    assert "InventedModel" not in SHIPPED_CLASSES.values()
    with pytest.raises(AttributeError):
        getattr(surface, "InventedModel")


def signal_sites(path) -> list:
    """Every ``Signal()`` a class in `path` declares, as class and name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            value = statement.value
            if isinstance(value, ast.Call) and dotted(value.func).endswith("Signal"):
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        found.append(f"{node.name}.{target.id}")
    return sorted(found)


def test_every_shipped_signal_has_a_counterpart():
    """The shipped screen declares a signal the surface answers with nothing."""
    declared = signal_sites(LAUNCHER_SOURCE)
    assert declared == sorted(SHIPPED_SIGNALS), declared
    assert len(declared) == SIGNAL_TOTAL
    assert sorted(surface.SIGNALS) == declared
    for counterpart in SHIPPED_SIGNALS.values():
        holder, _, attribute = counterpart.partition(".")
        assert callable(getattr(getattr(surface, holder), attribute)), counterpart


def test_the_signal_reader_finds_the_real_declarations():
    """The signal reader returns an empty set whatever the source holds."""
    assert "ModeCard.clicked" in signal_sites(LAUNCHER_SOURCE)
    assert (
        LAUNCHER_SOURCE.read_text(encoding="utf-8").count("= Signal()") == SIGNAL_TOTAL
    )
    assert signal_sites(TIMER_NEIGHBOUR) != signal_sites(LAUNCHER_SOURCE)


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


def test_the_screen_holds_no_timer_and_the_counter_can_report():
    """The screen runs a timer the surface declares no delay for.

    The shipped screen holds none, so the counter is pointed at a
    neighbouring screen that really does run one. A counter that
    returned nothing on both would be no measurement.
    """
    assert timer_sites(LAUNCHER_SOURCE) == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(timer_sites(TIMER_NEIGHBOUR)) >= 1, "the timer counter reports nothing"


def test_the_screen_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The screen listens on a topic the surface names none of.

    The shipped screen listens on none, so the counter is pointed at a
    neighbouring screen that really does subscribe.
    """
    assert bus_sites(LAUNCHER_SOURCE) == []
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter reports nothing"
    assert "wire.created" in neighbour


# The completeness check


PAYLOAD_KEYS = {
    "ACTIONS": "actions",
    "ALIGN_CENTER": "alignments.center",
    "ALIGN_CENTER_VALUE": "alignments.center_value",
    "BUS_TOPICS": "bus_topics",
    "BUTTON_STYLE_FORMAT": "formats.button_style",
    "BUTTON_TEXT_COLOR": "colors.button_text",
    "BUTTON_TEXT_FORMAT": "formats.button_text",
    "CALL_NAMES": "call_names",
    "CARDS_ROW_SPACING_PX": "cards_row.spacing_px",
    "CARD_ACCESSIBLE_NAME": "cards.crypto_card.accessible_name",
    "CARD_BACKGROUND": "colors.card_background",
    "CARD_BORDER": "colors.card_border",
    "CARD_CURSOR": "cards.crypto_card.cursor",
    "CARD_GAP_PX": "cards.crypto_card.gap_px",
    "CARD_HEAD_ORDER": "card_head_order",
    "CARD_HEIGHT_PX": "cards.crypto_card.height_px",
    "CARD_MARGINS_PX": "cards.crypto_card.margins_px",
    "CARD_ORDER": "cards_row.order",
    "CARD_SIGNAL": "card_signal",
    "CARD_SIGNALS": "card_signals",
    "CARD_SPACING_PX": "cards.crypto_card.spacing_px",
    "CARD_TYPE_NAME": "cards.crypto_card.type_name",
    "CARD_STYLE_FORMAT": "formats.card_style",
    "CARD_TAIL_ORDER": "card_tail_order",
    "CARD_WIDTH_PX": "cards.crypto_card.width_px",
    "COLORS": "colors",
    "CRYPTO_COLOR": "colors.crypto",
    "CRYPTO_FEATURES": "modes.crypto_card.features",
    "CRYPTO_ICON": "modes.crypto_card.icon_char",
    "CRYPTO_SIGNAL": "card_signals.crypto_card",
    "CRYPTO_SUBTITLE": "modes.crypto_card.subtitle",
    "CRYPTO_TITLE": "modes.crypto_card.title",
    "FEATURE_ALIGNMENT_VALUE": "alignments.feature_value",
    "FEATURE_COLOR": "colors.feature",
    "FEATURE_SLOT_FORMAT": "feature_slot_format",
    "FEATURE_STYLE": "styles.feature",
    "FEATURE_TEXT_FORMAT": "formats.feature_text",
    "FIRST_CLICK_COUNT": "first_click_count",
    "FOOTER_COLOR": "colors.footer",
    "FOOTER_STYLE": "styles.footer",
    "FOOTER_TEXT": "footer.text",
    "GRADIENT_BOTTOM_COLOR": "colors.gradient_bottom",
    "GRADIENT_MIDDLE_COLOR": "colors.gradient_middle",
    "GRADIENT_START_PX": "background.gradient.start_px",
    "GRADIENT_STOPS": "background.gradient.stops",
    "GRADIENT_TOP_COLOR": "colors.gradient_top",
    "HEADING_COLOR": "colors.heading",
    "HEADING_GAP_PX": "heading_gap_px",
    "HEADING_STYLE": "heading.style_sheet",
    "HEADING_TEXT": "heading.text",
    "HOVER_COLOR_FORMAT": "formats.hover_color",
    "HOVER_COLOR_SUFFIX": "hover_color_suffix",
    "ICON_STYLE_FORMAT": "formats.icon_style",
    "NO_PRESSES": "no_presses",
    "NO_TEXT": "no_text",
    "PRESS_KINDS": "press_kinds",
    "PROMPT_COLOR": "colors.prompt",
    "PROMPT_STYLE": "prompt.style_sheet",
    "PROMPT_TEXT": "prompt.text",
    "SHADOW_ATTACHED": "cards.crypto_card.shadow.attached",
    "SHADOW_BLUR_RADIUS_PX": "cards.crypto_card.shadow.blur_radius_px",
    "SHADOW_OFFSET_PX": "cards.crypto_card.shadow.offset_px",
    "SIGNALS": "signals",
    "STOCKS_COLOR": "colors.stocks",
    "STOCKS_FEATURES": "modes.stocks_card.features",
    "STOCKS_ICON": "modes.stocks_card.icon_char",
    "STOCKS_SIGNAL": "card_signals.stocks_card",
    "STOCKS_SUBTITLE": "modes.stocks_card.subtitle",
    "STOCKS_TITLE": "modes.stocks_card.title",
    "SUBTITLE_COLOR": "colors.subtitle",
    "SUBTITLE_STYLE": "styles.subtitle",
    "TEXT_REFUSAL": "formats.text_refusal",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TITLE_STYLE_FORMAT": "formats.title_style",
    "WINDOW_ACCESSIBLE_NAME": "accessible_name",
    "WINDOW_BACKGROUND": "colors.window_background",
    "WINDOW_HEIGHT_PX": "window.height_px",
    "WINDOW_MARGINS_PX": "window.margins_px",
    "WINDOW_ORDER": "window_order",
    "WINDOW_SPACING_PX": "window.spacing_px",
    "WINDOW_STYLE": "window.style_sheet",
    "WINDOW_TITLE": "window.title",
    "WINDOW_WIDTH_PX": "window.width_px",
    "WORD_WRAP_OFF": "word_wrap.off",
    "WORD_WRAP_ON": "word_wrap.on",
}

# Values the payload carries inside a list, not at a path of their own.
LIST_MEMBERS = {
    "BUTTON_PRESS": "press_kinds",
    "CARD_PRESS": "press_kinds",
    "CRYPTO_CARD": "cards_row.order",
    "STOCKS_CARD": "cards_row.order",
    "GRADIENT_END_X_PX": "background.gradient.end_px",
}

# The five branch markers, each carried inside call_names.
CALL_CONSTANTS = (
    "PRESS_CARD",
    "PRESS_BUTTON",
    "CARD_CLICKED",
    "CRYPTO_SELECTED",
    "STOCKS_SELECTED",
)

# (constant no payload key carries, the test that covers it).
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_launcher_method",
    "LOGGER_NAME": "test_the_surface_names_the_same_logger_as_the_screen",
    "SCREEN_MODEL": "test_the_bridge_resets_the_screen_state_on_request",
}

STATE_ONLY_KEYS = {"calls"}


def at_path(payload, path):
    """The payload value one dotted path names."""
    found = payload
    for step in path.split("."):
        found = found[step]
    return found


def as_lists(value):
    """`value` with every tuple turned into a list, at every depth."""
    if isinstance(value, tuple):
        return [as_lists(inner) for inner in value]
    return value


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


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read.

    A comparison that reads some of the values passes whether the rest
    match or not. Every value is accounted for here: a payload path, a
    member of a list the payload carries, one of the branch markers, or
    one of the three named with the check that covers it.
    """
    payload = surface.build_view_model(surface.LauncherModel())
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payload, PAYLOAD_KEYS[name]) == as_lists(value), name
        elif name in LIST_MEMBERS:
            assert value in at_path(payload, LIST_MEMBERS[name]), name
        elif name in CALL_CONSTANTS:
            assert value in payload["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(PAYLOAD_KEYS) == 86
    assert len(LIST_MEMBERS) == 5
    assert len(CALL_CONSTANTS) == 5
    assert len(NOT_IN_THE_SNAPSHOT) == 3


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.LauncherModel())
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {path.split(".")[0] for path in LIST_MEMBERS.values()}
    answered.add("call_names")
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    assert len(payload) == PAYLOAD_KEY_TOTAL
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing.

    A value that reaches no payload path and no named exception must
    land in the unaccounted list, or the check above is empty.
    """
    payload = surface.build_view_model(surface.LauncherModel())
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in LIST_MEMBERS
    assert invented not in CALL_CONSTANTS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "HEADING_TEXT" in surface_constants()
    assert "CARD_STYLE_FORMAT" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "LauncherModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "colors.invented")


def test_every_branch_marker_fires_and_ties_to_what_the_operator_sees():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for name in PRESS_NAMES:
        if name in REFUSING_PRESS_SPECS:
            continue
        model, payload = drive_new(PRESS_SPECS[name])
        seen.update(call[0] for call in payload["calls"])
    assert seen == set(surface.CALL_NAMES), sorted(set(surface.CALL_NAMES) - seen)
    quiet, quiet_payload = drive_new(PRESS_SPECS["nothing_pressed"])
    assert quiet_payload["calls"] == []
    assert quiet_payload["cards"]["crypto_card"]["clicks"] == 0
    loud, loud_payload = drive_new(PRESS_SPECS["one_card_pressed_twice"])
    assert [call[0] for call in loud_payload["calls"]].count(surface.PRESS_CARD) == 2
    assert loud_payload["cards"]["crypto_card"]["clicks"] == 2
    assert loud_payload["cards"]["stocks_card"]["clicks"] == 0


# The surface carries its own values


def moved_label_class():
    """A label class that puts MOVED in front of every text it is given."""
    from PySide6.QtWidgets import QLabel

    class MovedLabel(QLabel):
        """A label that reports a text no product value can produce."""

        def __init__(self, text=None, parent=None):
            super().__init__("MOVED" if text is None else "MOVED %s" % text, parent)
            self.setAccessibleName("Moved Label")

    return MovedLabel


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_screen(monkeypatch):
    """The surface read its values off the screen it replaces.

    A surface that read the shipped screen would follow it, and the
    whole comparison above would be one side read twice. The label class
    the shipped screen looks up is moved and the surface must not move
    with it.
    """
    app()
    from src.gui import launcher as shipped

    before = old_card_outcome(FIELD_SPECS["happy_crypto"])["value"]
    monkeypatch.setattr(shipped, "QLabel", moved_label_class())
    moved = old_card_outcome(FIELD_SPECS["happy_crypto"])["value"]
    assert moved["title"]["text"] == "MOVED %s" % surface.CRYPTO_TITLE
    assert before["title"]["text"] == surface.CRYPTO_TITLE
    mine = new_card_outcome(FIELD_SPECS["happy_crypto"])["value"]
    assert mine["title"]["text"] == surface.CRYPTO_TITLE
    assert mine == before
    monkeypatch.undo()
    assert old_card_outcome(FIELD_SPECS["happy_crypto"])["value"] == before


def empty_card_class():
    """A card class that builds none of the children a card holds."""
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QFrame

    class EmptyCard(QFrame):
        """A card with its signal and nothing inside it."""

        clicked = Signal()

        def __init__(self, *_args, **named):
            super().__init__(named.get("parent"))
            self.setAccessibleName("Empty Card")

    return EmptyCard


def test_the_surface_does_not_follow_a_screen_that_builds_nothing(monkeypatch):
    """The surface asked the shipped screen to build its controls."""
    app()
    from src.gui import launcher as shipped

    payload = surface.build_view_model(surface.LauncherModel())
    monkeypatch.setattr(shipped, "ModeCard", empty_card_class())
    stripped = shipped.LauncherWindow()
    for card in window_card_row(stripped):
        assert card.layout() is None
        assert card.accessibleName() == "Empty Card"
    again = surface.build_view_model(surface.LauncherModel())
    assert again == payload
    assert again["cards"]["crypto_card"]["accessible_name"] == "Mode Card"
    assert again["heading"]["text"] == surface.HEADING_TEXT
    monkeypatch.undo()
    restored = shipped.LauncherWindow()
    assert window_card_row(restored)[0].layout() is not None


def test_the_surface_names_the_same_logger_as_the_screen():
    """The surface names a logger the shipped screen does not use."""
    from src.gui import launcher as shipped

    assert surface.LOGGER_NAME == shipped.logger.name
    assert surface.LOGGER_NAME == "acervator.gui"


# The colours


def canonical(colour):
    """One colour as a full six-digit value, so short forms compare."""
    from PySide6.QtGui import QColor

    return QColor(colour).name().lower()


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two declared colours become one when written in full."""
    app()
    written = {name: canonical(value) for name, value in surface.COLORS.items()}
    assert len(set(written.values())) == len(surface.COLORS), written
    assert written["crypto"] == "#00ffcc"
    assert all(len(value) == 7 for value in written.values()), written


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour check passes a value with its channels swapped."""
    app()
    assert canonical(surface.CRYPTO_COLOR) == "#00ffcc"
    assert canonical("#00ccff") != canonical(surface.CRYPTO_COLOR)
    assert canonical(surface.STOCKS_COLOR) != canonical("#00ffaa")


EQUAL_CHANNEL_COLORS = (
    "PROMPT_COLOR",
    "SUBTITLE_COLOR",
    "FEATURE_COLOR",
    "FOOTER_COLOR",
)


@pytest.mark.parametrize("name", EQUAL_CHANNEL_COLORS)
def test_an_equal_channel_grey_is_compared_as_text(name):
    """A colour with three equal channels was left to a colour check.

    ``#666`` reads the same with any two channels swapped, so no colour
    check can report a swap in it. Each is compared as exact text inside
    the style sheet that carries it, which the side-by-side comparison
    covers.
    """
    app()
    value = getattr(surface, name)
    red, green, blue = value[1], value[2], value[3]
    assert red == green == blue, value
    assert canonical(value) == canonical("#" + red * 6)
    carrier = {
        "PROMPT_COLOR": surface.PROMPT_STYLE,
        "SUBTITLE_COLOR": surface.SUBTITLE_STYLE,
        "FEATURE_COLOR": surface.FEATURE_STYLE,
        "FOOTER_COLOR": surface.FOOTER_STYLE,
    }[name]
    assert value in carrier


def test_every_named_colour_reaches_the_style_that_carries_it():
    """A named colour and the style beside it drifted apart."""
    assert surface.WINDOW_BACKGROUND in surface.WINDOW_STYLE
    assert surface.HEADING_COLOR in surface.HEADING_STYLE
    assert surface.CARD_BACKGROUND in surface.CARD_STYLE_FORMAT
    assert surface.CARD_BORDER in surface.CARD_STYLE_FORMAT
    assert surface.BUTTON_TEXT_COLOR in surface.BUTTON_STYLE_FORMAT
    for _stop, colour in surface.GRADIENT_STOPS:
        assert colour in surface.COLORS.values()


# The pictures


def model_payload(presses=None):
    """The view model after the same driving, stamped."""
    return sealed(surface.build_view_model(surface.LauncherModel(), presses))


def card_payload(name):
    """One card's state, taken off the surface and stamped."""
    return sealed(surface.ModeCardModel(**FIELD_SPECS[name]).state())


def widget_painted_by_the_screen(presses=None):
    """The screen the shipped Qt window builds, after the same driving."""
    window, _fired, _tally = drive_old(presses or [])
    return window


def card_painted_by_the_screen(name):
    """The card the shipped Qt class builds from one field set."""
    from src.gui.launcher import ModeCard

    app()
    return ModeCard(**FIELD_SPECS[name])


def card_painted_by_the_model(state):
    """A card built only from the card state, never from the shipped class.

    A state the caller changed after it came off the surface is refused.
    """
    state = unaltered(state)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QFrame,
        QGraphicsDropShadowEffect,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    app()

    def styled_label(declared):
        label = QLabel(declared["text"])
        label.setAlignment(Qt.AlignmentFlag(declared["alignment_value"]))
        label.setStyleSheet(declared["style_sheet"])
        label.setWordWrap(declared["word_wrap"])
        return label

    card = type(state["type_name"], (QFrame,), {})()
    card.setAccessibleName(state["accessible_name"])
    card.setCursor(getattr(Qt.CursorShape, state["cursor"]))
    card.setFixedSize(state["width_px"], state["height_px"])
    card.setStyleSheet(state["style_sheet"])
    layout = QVBoxLayout(card)
    layout.setContentsMargins(*state["margins_px"])
    layout.setSpacing(state["spacing_px"])
    layout.addWidget(styled_label(state["icon"]))
    layout.addWidget(styled_label(state["title"]))
    layout.addWidget(styled_label(state["subtitle"]))
    layout.addSpacing(state["gap_px"])
    for declared in state["features"]:
        layout.addWidget(styled_label(declared))
    layout.addStretch()
    button = QPushButton(state["button"]["text"])
    button.setStyleSheet(state["button"]["style_sheet"])
    layout.addWidget(button)
    if state["shadow"]["attached"]:
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(state["shadow"]["blur_radius_px"])
        shadow.setColor(QColor(state["shadow"]["color"]))
        shadow.setOffset(*state["shadow"]["offset_px"])
        card.setGraphicsEffect(shadow)
        card.setProperty("kept_shadow", shadow)
    return card


def widget_painted_by_the_model(payload):
    """A screen built only from the payload, never from the shipped window."""
    payload = unaltered(payload)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QLinearGradient, QPainter
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

    app()

    class PaintedScreen(QWidget):
        """A window whose background is the wash the payload declares."""

        def __init__(self, declared, accessible_name):
            super().__init__()
            self.declared = declared
            self.setAccessibleName(accessible_name)

        def paintEvent(self, _event):
            painter = QPainter(self)
            wash = QLinearGradient(
                self.declared["start_px"][0],
                self.declared["start_px"][1],
                self.declared["end_px"][0],
                self.height(),
            )
            for stop, colour in self.declared["stops"]:
                wash.setColorAt(stop, QColor(colour))
            painter.fillRect(self.rect(), wash)
            painter.end()

    def styled_label(declared):
        label = QLabel(declared["text"])
        label.setAlignment(Qt.AlignmentFlag(declared["alignment_value"]))
        label.setStyleSheet(declared["style_sheet"])
        label.setWordWrap(declared["word_wrap"])
        return label

    screen = PaintedScreen(
        payload["background"]["gradient"], payload["accessible_name"]
    )
    screen.setWindowTitle(payload["window"]["title"])
    screen.setFixedSize(payload["window"]["width_px"], payload["window"]["height_px"])
    screen.setStyleSheet(payload["window"]["style_sheet"])
    layout = QVBoxLayout(screen)
    layout.setContentsMargins(*payload["window"]["margins_px"])
    layout.setSpacing(payload["window"]["spacing_px"])
    layout.addWidget(styled_label(payload["heading"]))
    layout.addWidget(styled_label(payload["prompt"]))
    layout.addSpacing(payload["heading_gap_px"])
    row = QHBoxLayout()
    row.setSpacing(payload["cards_row"]["spacing_px"])
    for name in payload["cards_row"]["order"]:
        row.addWidget(card_painted_by_the_model(sealed(payload["cards"][name])))
    layout.addLayout(row)
    layout.addWidget(styled_label(payload["footer"]))
    return screen


PICTURE_PRESSES = ["nothing_pressed", "both_cards_pressed"]


@pytest.mark.parametrize("name", PICTURE_PRESSES)
def test_the_two_sides_paint_one_screen(name):
    """The surface painted a different screen than the shipped window."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(
            widget_painted_by_the_screen(PRESS_SPECS[name]), WINDOW_SIZE
        ),
        new_side=render_offscreen(
            widget_painted_by_the_model(model_payload(PRESS_SPECS[name])), WINDOW_SIZE
        ),
        note=note,
    )


PICTURE_CARDS = [
    "happy_crypto",
    "happy_stocks",
    "empty_everywhere",
    "unicode",
    "two_hundred_characters",
]


@pytest.mark.parametrize("name", PICTURE_CARDS)
def test_the_two_sides_paint_one_card(name):
    """The surface painted a different card than the shipped class."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=render_offscreen(card_painted_by_the_screen(name), CARD_SIZE),
        new_side=render_offscreen(
            card_painted_by_the_model(card_payload(name)), CARD_SIZE
        ),
        note=note,
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    The crypto card off the shipped class against the stocks card off
    the surface. Both are real product cards and they carry different
    colours, icons and wording, so a pass proves the comparison reports
    a card painted differently.
    """
    app()
    assert FIELD_SPECS["happy_crypto"] != FIELD_SPECS["happy_stocks"]
    assert_pictures_differ(
        old_side=render_offscreen(
            card_painted_by_the_screen("happy_crypto"), CARD_SIZE
        ),
        new_side=render_offscreen(
            card_painted_by_the_model(card_payload("happy_stocks")), CARD_SIZE
        ),
        note="the crypto card against the stocks card",
    )


def colours_in(image) -> set:
    """Every colour the render painted, sampled every fifth pixel."""
    from PySide6.QtGui import QColor

    seen = set()
    for x in range(0, image.width(), 5):
        for y in range(0, image.height(), 5):
            seen.add(QColor(image.pixelColor(x, y)).name())
    return seen


@pytest.mark.parametrize("name", PICTURE_CARDS)
def test_the_painted_card_shows_more_than_one_colour(name):
    """The two sides matched because the card painted one flat colour."""
    app()
    for image in (
        render_offscreen(card_painted_by_the_screen(name), CARD_SIZE),
        render_offscreen(card_painted_by_the_model(card_payload(name)), CARD_SIZE),
    ):
        assert image.width() == CARD_SIZE[0]
        assert image.height() == CARD_SIZE[1]
        seen = colours_in(image)
        assert len(seen) > 1, f"{name} painted one colour, so no change could show"


def test_the_painted_screen_shows_more_than_one_colour():
    """The two sides matched because the screen painted one flat colour."""
    app()
    for image in (
        render_offscreen(widget_painted_by_the_screen([]), WINDOW_SIZE),
        render_offscreen(widget_painted_by_the_model(model_payload()), WINDOW_SIZE),
    ):
        seen = colours_in(image)
        assert len(seen) > 1, "the screen painted one colour, so no change could show"
        assert surface.CRYPTO_COLOR in seen
        assert surface.STOCKS_COLOR in seen


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload()
    payload["heading"]["text"] = "MOVED"
    with pytest.raises(AssertionError) as reported:
        widget_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(surface.build_view_model(surface.LauncherModel()))


@skip_unless_no_fonts
def test_two_feature_lines_of_equal_length_measure_the_same_width():
    """The host reports no fonts and the glyphs still have their own widths."""
    app()
    from PySide6.QtWidgets import QLabel

    narrow = QLabel(surface.feature_text("iiiiiiii"))
    wide = QLabel(surface.feature_text("WWWWWWWW"))
    assert narrow.sizeHint().width() == wide.sizeHint().width()


@skip_unless_real_fonts
def test_two_feature_lines_of_equal_length_measure_different_widths():
    """The host reports fonts and every glyph still has one width."""
    app()
    from PySide6.QtWidgets import QLabel

    narrow = QLabel(surface.feature_text("iiiiiiii"))
    wide = QLabel(surface.feature_text("WWWWWWWW"))
    assert narrow.sizeHint().width() != wide.sizeHint().width()


# What a picture cannot see, read off both sides instead


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report.

    The accessible names, the window title, the mouse cursor, the word
    wrap setting and the fixed sizes paint nothing of their own. Each is
    read off the shipped screen and off the surface directly.
    """
    app()
    old = old_window_outcome([])["value"]
    new = new_window_outcome([])["value"]
    assert new["accessible_name"] == old["accessible_name"]
    assert new["window"]["title"] == old["window"]["title"]
    for name in surface.CARD_ORDER:
        assert (
            new["cards"][name]["accessible_name"]
            == old["cards"][name]["accessible_name"]
        )
        assert new["cards"][name]["cursor"] == old["cards"][name]["cursor"]
        assert new["cards"][name]["subtitle"]["word_wrap"] == (
            old["cards"][name]["subtitle"]["word_wrap"]
        )
        assert new["cards"][name]["minimum_size_px"] == (
            old["cards"][name]["minimum_size_px"]
        )
    assert old["accessible_name"] == "Launcher Window"
    assert old["window"]["title"] == "Acervator"
    assert old["cards"]["crypto_card"]["cursor"] == "PointingHandCursor"
    assert old["cards"]["crypto_card"]["subtitle"]["word_wrap"] is True
    assert old["cards"]["crypto_card"]["minimum_size_px"] == [380, 420]


def test_the_click_counts_are_read_off_both_sides():
    """A press reaches no pixel, so the count must be read off both sides."""
    app()
    presses = PRESS_SPECS["card_then_button"]
    old = old_window_outcome(presses)["value"]
    new = new_window_outcome(presses)["value"]
    assert new["clicks"] == old["clicks"]
    assert new["fired"] == old["fired"]
    assert old["clicks"] == {"crypto_card": 0, "stocks_card": 2}
    assert old["fired"] == [surface.STOCKS_SIGNAL, surface.STOCKS_SIGNAL]
    quiet = old_window_outcome([])["value"]
    assert quiet["clicks"] == {"crypto_card": 0, "stocks_card": 0}
    assert quiet["fired"] == []


def test_the_glow_the_card_asks_for_never_reaches_the_screen():
    """The shipped card carries the glow it asks for, so the surface lost one.

    ``ModeCard.__init__`` builds a drop shadow and hands it to the card,
    but nothing keeps the shadow, so it is thrown away as soon as the
    card is built. Every shipped card is drawn without its glow. The
    surface records what the card asks for and records that it does not
    land.
    """
    app()
    from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect

    card = card_painted_by_the_screen("happy_crypto")
    assert card.graphicsEffect() is None
    assert surface.SHADOW_ATTACHED is False
    state = surface.ModeCardModel(**FIELD_SPECS["happy_crypto"]).state()
    assert state["shadow"] == {
        "blur_radius_px": 30,
        "offset_px": [0, 0],
        "color": surface.CRYPTO_COLOR,
        "attached": False,
    }
    kept = QFrame()
    shadow = QGraphicsDropShadowEffect()
    kept.setGraphicsEffect(shadow)
    assert kept.graphicsEffect() is not None, "a kept shadow does not attach either"


# The bridge


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


def test_the_bridge_registers_the_launcher_method():
    """The renderer cannot reach the Launcher screen over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "launcher.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["heading"]["text"] == surface.HEADING_TEXT
    assert result["cards"]["crypto_card"]["button"]["text"] == "Launch Crypto Trading"


def test_the_bridge_resets_the_screen_state_on_request():
    """The screen state the bridge keeps was never cleared."""
    filled = bridge_answer(
        {"reset": True, "presses": [[CARD_PRESS, 0], [BUTTON_PRESS, 1]]}
    )["result"]
    assert filled["cards"]["crypto_card"]["clicks"] == 1
    assert filled["cards"]["stocks_card"]["clicks"] == 1
    assert len(filled["calls"]) == 6
    kept = bridge_answer({})["result"]
    assert kept["cards"]["crypto_card"]["clicks"] == 1
    assert kept["calls"] == filled["calls"]
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["cards"]["crypto_card"]["clicks"] == 0
    assert cleared["calls"] == []


def test_the_bridge_reports_a_press_the_screen_refuses():
    """A press outside the row ended the session instead of answering."""
    answer = bridge_answer({"reset": True, "presses": [[CARD_PRESS, 9]]})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "IndexError"
    assert answer["error"]["message"], answer


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"reset": True, "presses": [[BUTTON_PRESS, 0]]})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["cards"]["crypto_card"]["clicks"] == 1
    assert encoded["result"]["window_order"] == list(surface.WINDOW_ORDER)


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'launcher.state', 'params':"
    " {'reset': True, 'presses': [['card', 0], ['button', 1]]}}),"
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
    """Reaching the Launcher screen pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["cards"]["crypto_card"]["clicks"] == 1
    assert result["cards"]["stocks_card"]["clicks"] == 1
    assert result["heading"]["text"] == "QUANTUM AUTO TRADER"


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
