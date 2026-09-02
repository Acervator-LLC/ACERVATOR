"""sim_stat_strip_surface.py -- the Simulator's header stat strip as plain data.

Describes the inline strip at the top of the Simulator tab: the ten stat
cells, the caption and value each carries, the skins they paint in and the
layout numbers that place them. It also holds the behaviour the strip owns
rather than describes: the text one field shows for a value, the em-dash an
empty value falls back to, the refusal a value that is not text earns, the
silence a field name the strip does not carry earns, and the reset every
field takes.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for the
``sim_stat_strip.state`` method, which is how the Electron renderer reaches
it. Nothing here imports Qt, so the same code serves any frontend.
"""

from __future__ import annotations

from typing import Any, Optional

METHOD = "sim_stat_strip.state"

PLACEHOLDER_TEXT = "\u2014"
LABEL_SUFFIX = ":"

STRIP_OBJECT_NAME = "SimStatStrip"
STRIP_ACCESSIBLE_NAME = "Sim Stat Strip"
CELL_ACCESSIBLE_NAME = "Stat Cell"
CELL_FRAME_SHAPE = "NoFrame"

STRIP_MARGINS_PX = (6, 4, 6, 4)
STRIP_SPACING_PX = 4
CELL_MARGINS_PX = (8, 4, 8, 4)
CELL_SPACING_PX = 6
TRAILING_STRETCH = True

LABEL_COLOUR = "#88aaff"
VALUE_COLOUR = "#ffffff"
LABEL_FONT_SIZE_PX = 11
VALUE_FONT_SIZE_PX = 13

LABEL_STYLE = f"color: {LABEL_COLOUR}; font-size: {LABEL_FONT_SIZE_PX}px;"
VALUE_STYLE = (
    f"color: {VALUE_COLOUR}; font-size: {VALUE_FONT_SIZE_PX}px; font-weight: bold;"
)

FIELDS = (
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

ACTIONS: dict = {}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()

FIELD_SET = "field_set"
FIELD_BLANKED = "field_blanked"
FIELD_UNKNOWN = "field_unknown"
CLEARED = "cleared"

CALL_NAMES = (FIELD_SET, FIELD_BLANKED, FIELD_UNKNOWN, CLEARED)

NOT_TEXT_MESSAGE = "a stat value must be text, not {kind}"


def label_text(field: str) -> str:
    """The caption one cell shows for a field name."""
    return f"{field}{LABEL_SUFFIX}"


def value_text(value: Any) -> str:
    """The text one cell shows for `value`.

    An empty value shows the em-dash placeholder rather than nothing. A
    value that is not text and is not empty is refused, because the cell
    has no way to paint it.
    """
    if not value:
        return PLACEHOLDER_TEXT
    if not isinstance(value, str):
        raise TypeError(NOT_TEXT_MESSAGE.format(kind=type(value).__name__))
    return value


def cell(field: str, text: str) -> dict:
    """One stat cell: its caption, its value and the skins both paint in."""
    return {
        "field": field,
        "accessible_name": CELL_ACCESSIBLE_NAME,
        "frame_shape": CELL_FRAME_SHAPE,
        "label": label_text(field),
        "label_style": LABEL_STYLE,
        "text": text,
        "style_sheet": VALUE_STYLE,
    }


def initial_cells() -> dict:
    """Every cell as the strip is built, before any value arrives."""
    return {field: cell(field, PLACEHOLDER_TEXT) for field in FIELDS}


def layout_items() -> list:
    """The row, item by item, in the order the strip adds them."""
    items: list = [{"kind": "cell", "field": field} for field in FIELDS]
    if TRAILING_STRETCH:
        items.append({"kind": "stretch"})
    return items


class SimStatStripModel:
    """The strip's state between updates, with no Qt object behind it.

    Holds the rendered cell for every field and the branch markers the
    parity comparison reads.
    """

    def __init__(self) -> None:
        self.cells: dict = initial_cells()
        self.calls: list = []

    def set_field(self, field: Any, value: Any) -> None:
        """Write one field's value.

        A field name the strip does not carry is ignored, and is ignored
        before the value is read, so an unknown field never refuses a
        value. An empty value falls back to the placeholder.
        """
        if self.cells.get(field) is None:
            self.calls.append(FIELD_UNKNOWN)
            return
        text = value_text(value)
        self.calls.append(FIELD_BLANKED if text == PLACEHOLDER_TEXT else FIELD_SET)
        self.cells[field] = cell(field, text)

    def clear(self) -> None:
        """Reset every field to the em-dash placeholder."""
        self.calls.append(CLEARED)
        for field in list(self.cells):
            self.cells[field] = cell(field, PLACEHOLDER_TEXT)


def build_view_model(model: Optional[SimStatStripModel] = None) -> dict:
    """Return the whole strip state as one serialisable dict."""
    state = SimStatStripModel() if model is None else model
    return {
        "widget": {
            "object_name": STRIP_OBJECT_NAME,
            "accessible_name": STRIP_ACCESSIBLE_NAME,
        },
        "layout": {
            "margins_px": list(STRIP_MARGINS_PX),
            "spacing_px": STRIP_SPACING_PX,
            "cell_margins_px": list(CELL_MARGINS_PX),
            "cell_spacing_px": CELL_SPACING_PX,
            "trailing_stretch": TRAILING_STRETCH,
        },
        "items": layout_items(),
        "order": list(FIELDS),
        "cells": [state.cells[field] for field in FIELDS],
        "placeholder": PLACEHOLDER_TEXT,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "method": METHOD,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``sim_stat_strip.state``.

    Resets every field when the request asks for it, then writes the
    fields under ``values`` in the order the request lists them.
    """
    asked = params or {}
    state = SimStatStripModel()
    if asked.get("clear"):
        state.clear()
    values = asked.get("values")
    if values is not None:
        for field, value in values.items():
            state.set_field(field, value)
    return build_view_model(state)
