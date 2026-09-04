"""The shipped Bot Swarm list and the Qt-free surface, side by side.

A failure means the surface builds a different row, a different cell, a
different colour, a different lane, a different drawing call, a
different log line or a different refusal than ``BotListView`` and
``LaneWireCanvas``.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import bot_swarm_list as shipped
from src.gui.main_tabs import bot_swarm_list_surface as surface
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

LIST_PATH = REPO_ROOT / "src" / "gui" / "bot_swarm_list.py"
SURFACE_PATH = REPO_ROOT / "src" / "gui" / "main_tabs" / "bot_swarm_list_surface.py"
BRIDGE_PATH = REPO_ROOT / "src" / "core" / "desktop_bridge.py"

WIRING_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
TIMER_WRONG_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "main_tabs" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
ELEMENT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
NESTED_CLASS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "stock_main_window.py"

# The counts measured off the shipped list. Each is compared with what
# the surface declares.
LIST_CONNECT_SITES = 0
LIST_SIGNAL_SITES = 0
LIST_TIMER_SITES = 0
LIST_BUS_SITES = 0
LIST_ELEMENT_BUILDS = 32
LIST_LAYOUT_BUILDS = 0

WIRING_NEIGHBOUR_SITES = 1
SIGNAL_NEIGHBOUR_SITES = 3
TIMER_NEIGHBOUR_SITES = 1
BUS_NEIGHBOUR_SITES = 2
ELEMENT_NEIGHBOUR_BUILDS = 3

LIST_SIZE = (600, 200)
SMALL_SIZE = (420, 140)
PAINT_SIZE = (600, 200)

TEST_SKIN = "border: 5px solid #ff00ff;"

# The design values both colour sets are built from, typed out here
# rather than read from either side, so a re-valued token cannot move
# both together.
INFLOW_GREEN = "#00ff88"
OUTFLOW_RED = "#ff3366"
NEAR_CAP_AMBER = "#ffaa00"
HEADROOM_CYAN = "#00ffee"
NO_EXPORT_GREY = "#666666"
UNSET_BLACK = "#000000"
SHORT_HEX_SAMPLE = "#888"
SHORT_HEX_LONG_FORM = "#888888"

UNICODE_TEXT = "\u0394_flip\u2192\u26a1"
MARKUP_TEXT = "<b>bot</b>&nbsp;<script>x</script>"
APOSTROPHE_TEXT = "it's a 'quoted' name"
NEWLINE_TEXT = "two\nlines"
LONG_TEXT = "Z" * 200
THOUSAND_MILLION = 1_000_000_000
ONE_BILLIONTH = 1e-9
INFINITY = float("inf")
NOT_A_NUMBER = float("nan")

HELD: list = []


# The bot readings both sides are driven with


def reading(**over):
    """One bot reading, the shape the Bot Swarm screen passes in."""
    found = {
        "bot_id": "bot-a",
        "symbol": "BTC",
        "inflow_usd": 12.5,
        "outflow_usd": 3.25,
        "outflow_pct": 40.0,
    }
    found.update(over)
    return found


TWO_BOTS = [
    reading(),
    reading(bot_id="bot-b", symbol="ETH", inflow_usd=1.0, outflow_pct=95.0),
]
THREE_BOTS = TWO_BOTS + [
    reading(bot_id="bot-c", symbol="SOL", outflow_usd=0.0, outflow_pct=0.0)
]
FOUR_BOTS = THREE_BOTS + [
    reading(bot_id="bot-d", symbol="XRP", inflow_usd=999.99, outflow_pct=100.0)
]

CASES: dict = {
    "happy": [reading()],
    "empty": [],
    "two_bots": TWO_BOTS,
    "three_bots": THREE_BOTS,
    "four_bots": FOUR_BOTS,
    "zero": [reading(inflow_usd=0.0, outflow_usd=0.0, outflow_pct=0.0)],
    "negative": [reading(inflow_usd=-5.5, outflow_usd=-1.0, outflow_pct=-3.0)],
    "thousand_million": [
        reading(
            inflow_usd=float(THOUSAND_MILLION),
            outflow_usd=float(THOUSAND_MILLION),
            outflow_pct=float(THOUSAND_MILLION),
        )
    ],
    "one_billionth": [
        reading(
            inflow_usd=ONE_BILLIONTH,
            outflow_usd=ONE_BILLIONTH,
            outflow_pct=ONE_BILLIONTH,
        )
    ],
    "unicode": [reading(bot_id=UNICODE_TEXT, symbol=UNICODE_TEXT)],
    "long_text": [reading(bot_id=LONG_TEXT, symbol=LONG_TEXT)],
    "markup": [reading(bot_id=MARKUP_TEXT, symbol=MARKUP_TEXT)],
    "apostrophe": [reading(bot_id=APOSTROPHE_TEXT, symbol=APOSTROPHE_TEXT)],
    "newline_name": [reading(bot_id=NEWLINE_TEXT, symbol=NEWLINE_TEXT)],
    "wrong_capitals": [reading(bot_id="BOT-A", symbol="btc")],
    "number_where_text_belongs": [reading(bot_id=7, symbol=7)],
    "text_where_number_belongs": [reading(inflow_usd="lots")],
    "text_where_outflow_belongs": [reading(outflow_usd="lots")],
    "text_where_pct_belongs": [reading(outflow_pct="many")],
    "infinity": [
        reading(inflow_usd=INFINITY, outflow_usd=INFINITY, outflow_pct=INFINITY)
    ],
    "minus_infinity": [
        reading(inflow_usd=-INFINITY, outflow_usd=-INFINITY, outflow_pct=-INFINITY)
    ],
    "not_a_number": [
        reading(
            inflow_usd=NOT_A_NUMBER, outflow_usd=NOT_A_NUMBER, outflow_pct=NOT_A_NUMBER
        )
    ],
    "missing_keys": [{}],
    "none_values": [
        reading(
            bot_id=None,
            symbol=None,
            inflow_usd=None,
            outflow_usd=None,
            outflow_pct=None,
        )
    ],
    "whole_number_amount": [reading(inflow_usd=12, outflow_usd=12, outflow_pct=12)],
    "decimal_amount": [reading(inflow_usd=12.0, outflow_usd=12.0, outflow_pct=12.0)],
    "true_where_number_belongs": [
        reading(inflow_usd=True, outflow_usd=True, outflow_pct=True)
    ],
    "pct_just_over_nothing": [reading(outflow_pct=1.0)],
    "pct_at_headroom_edge": [reading(outflow_pct=80.0)],
    "pct_over_headroom_edge": [reading(outflow_pct=81.0)],
    "pct_under_cap": [reading(outflow_pct=99.0)],
    "pct_at_cap": [reading(outflow_pct=100.0)],
    "pct_over_cap": [reading(outflow_pct=101.0)],
    "readings_not_a_list": 7,
    "reading_not_a_dict": [7],
    "all_pct_bands": [
        reading(bot_id="p-0", symbol="AAA", outflow_pct=0.0),
        reading(bot_id="p-1", symbol="BBB", outflow_pct=40.0),
        reading(bot_id="p-2", symbol="CCC", outflow_pct=90.0),
        reading(bot_id="p-3", symbol="DDD", outflow_pct=120.0),
    ],
    "nine_bots": [
        reading(bot_id="n-%d" % index, symbol="N%d" % index, outflow_pct=index * 12.0)
        for index in range(9)
    ],
}

REFUSED_CASES = {
    "text_where_number_belongs": "ValueError",
    "text_where_outflow_belongs": "ValueError",
    "text_where_pct_belongs": "ValueError",
    "readings_not_a_list": "TypeError",
    "reading_not_a_dict": "AttributeError",
}


# The wires both sheets are driven with


def wire(**over):
    """One wire, the shape the visualizer tab passes in."""
    found = {
        "id": "w-1",
        "source_id": "n-0",
        "target_id": "n-2",
        "phase": 0.25,
    }
    found.update(over)
    return found


WIRE_CASES: dict = {
    "one_wire": ("nine_bots", [wire()]),
    "no_wires": ("nine_bots", []),
    "same_row_both_ends": ("nine_bots", [wire(target_id="n-0")]),
    "reversed_ends": ("nine_bots", [wire(source_id="n-2", target_id="n-0")]),
    "two_overlapping": (
        "nine_bots",
        [wire(), wire(id="w-2", source_id="n-1", target_id="n-3")],
    ),
    "two_disjoint": (
        "nine_bots",
        [wire(), wire(id="w-2", source_id="n-4", target_id="n-6")],
    ),
    "nine_wires_exhaust_the_lanes": (
        "nine_bots",
        [
            wire(id="w-%d" % index, source_id="n-0", target_id="n-8")
            for index in range(9)
        ],
    ),
    "unlisted_source": ("nine_bots", [wire(source_id="gone")]),
    "unlisted_target": ("nine_bots", [wire(target_id="gone")]),
    "both_ends_unlisted": ("nine_bots", [wire(source_id="x", target_id="y")]),
    "unnamed_wire": ("nine_bots", [{"source_id": "n-0", "target_id": "n-1"}]),
    "unnamed_and_unlisted": ("nine_bots", [{"source_id": "n-0", "target_id": "z"}]),
    "wire_with_no_ends": ("nine_bots", [{}]),
    "empty_list_with_wires": ("empty", [wire()]),
    "phase_zero": ("nine_bots", [wire(phase=0.0)]),
    "phase_at_pulse_width": ("nine_bots", [wire(phase=0.12)]),
    "phase_near_end": ("nine_bots", [wire(phase=0.88)]),
    "phase_just_under_one": ("nine_bots", [wire(phase=0.999)]),
    "phase_one": ("nine_bots", [wire(phase=1.0)]),
    "phase_over_one": ("nine_bots", [wire(phase=1.5)]),
    "phase_negative": ("nine_bots", [wire(phase=-0.3)]),
    "phase_missing": (
        "nine_bots",
        [{"id": "w-1", "source_id": "n-0", "target_id": "n-2"}],
    ),
    "phase_none": ("nine_bots", [wire(phase=None)]),
    "phase_true": ("nine_bots", [wire(phase=True)]),
    "phase_thousand_million": ("nine_bots", [wire(phase=float(THOUSAND_MILLION))]),
    "phase_one_billionth": ("nine_bots", [wire(phase=ONE_BILLIONTH)]),
    "phase_infinity": ("nine_bots", [wire(phase=INFINITY)]),
    "phase_minus_infinity": ("nine_bots", [wire(phase=-INFINITY)]),
    "phase_not_a_number": ("nine_bots", [wire(phase=NOT_A_NUMBER)]),
    "phase_text": ("nine_bots", [wire(phase="fast")]),
    "unicode_id": ("nine_bots", [wire(id=UNICODE_TEXT)]),
    "long_id": ("nine_bots", [wire(id=LONG_TEXT)]),
    "markup_id": ("nine_bots", [wire(id=MARKUP_TEXT)]),
    "apostrophe_id": ("nine_bots", [wire(id=APOSTROPHE_TEXT)]),
    "newline_id": ("nine_bots", [wire(id=NEWLINE_TEXT)]),
    "number_id": ("nine_bots", [wire(id=7)]),
    "wires_not_a_list": ("nine_bots", 7),
    "wire_not_a_dict": ("nine_bots", [7]),
}

REFUSED_WIRE_CASES = {
    "phase_text": "ValueError",
    "wires_not_a_list": "TypeError",
    "wire_not_a_dict": "AttributeError",
}

PAINT_PICTURE_CASES = (
    "one_wire",
    "two_overlapping",
    "two_disjoint",
    "phase_zero",
    "phase_near_end",
)

LIST_PICTURE_CASES = ("happy", "four_bots", "all_pct_bands", "empty", "nine_bots")


# Step sequences, so a rewrite that refuses part way is caught


STEP_CASES: dict = {
    "one_rewrite": (("bots", "four_bots"),),
    "shrink_then_refuse_keeps_the_old_row": (
        ("bots", "three_bots"),
        ("bots", "text_where_number_belongs"),
    ),
    "grow_then_refuse_leaves_a_blank_row": (
        ("bots", "happy"),
        ("bots", "text_where_pct_belongs"),
    ),
    "refuse_then_rewrite_clean": (
        ("bots", "text_where_pct_belongs"),
        ("bots", "two_bots"),
    ),
    "readings_not_a_list_keeps_the_rows": (
        ("bots", "three_bots"),
        ("bots", "readings_not_a_list"),
    ),
    "reading_not_a_dict_keeps_the_row_count": (
        ("bots", "three_bots"),
        ("bots", "reading_not_a_dict"),
    ),
    "shrink_to_empty": (("bots", "four_bots"), ("bots", "empty")),
    "empty_then_grow": (("bots", "empty"), ("bots", "four_bots")),
    "wires_then_rows_change": (
        ("bots", "nine_bots"),
        ("wires", "one_wire"),
        ("paint",),
        ("bots", "happy"),
        ("paint",),
    ),
    "drop_then_recover_logs_twice": (
        ("bots", "nine_bots"),
        ("wires", "unlisted_target"),
        ("paint",),
        ("paint",),
        ("wires", "one_wire"),
        ("paint",),
        ("paint",),
    ),
    "paint_before_any_wire": (("bots", "nine_bots"), ("paint",)),
    "paint_twice_with_no_wires": (
        ("bots", "nine_bots"),
        ("wires", "no_wires"),
        ("paint",),
        ("paint",),
    ),
    "opacity_then_paint": (
        ("bots", "nine_bots"),
        ("wires", "one_wire"),
        ("opacity", 40),
        ("paint",),
    ),
    "opacity_over_range": (
        ("bots", "nine_bots"),
        ("wires", "one_wire"),
        ("opacity", 150),
        ("paint",),
    ),
    "opacity_under_range": (
        ("bots", "nine_bots"),
        ("wires", "one_wire"),
        ("opacity", -20),
        ("paint",),
    ),
    "opacity_fraction": (
        ("bots", "nine_bots"),
        ("wires", "one_wire"),
        ("opacity", 55.9),
        ("paint",),
    ),
    "opacity_endless": (
        ("bots", "nine_bots"),
        ("wires", "one_wire"),
        ("opacity", INFINITY),
        ("paint",),
    ),
    "opacity_not_a_number": (
        ("bots", "nine_bots"),
        ("wires", "one_wire"),
        ("opacity", NOT_A_NUMBER),
        ("paint",),
    ),
    "opacity_text": (
        ("bots", "nine_bots"),
        ("wires", "one_wire"),
        ("opacity", "half"),
        ("paint",),
    ),
    "exhausted_lanes_then_fewer_wires": (
        ("bots", "nine_bots"),
        ("wires", "nine_wires_exhaust_the_lanes"),
        ("paint",),
        ("wires", "one_wire"),
        ("paint",),
    ),
    "wires_refused_then_good": (
        ("bots", "nine_bots"),
        ("wires", "wire_not_a_dict"),
        ("wires", "one_wire"),
        ("paint",),
    ),
    "paint_refused_then_good": (
        ("bots", "nine_bots"),
        ("wires", "phase_text"),
        ("paint",),
        ("wires", "one_wire"),
        ("paint",),
    ),
}

REFUSED_STEP_CASES = {
    "shrink_then_refuse_keeps_the_old_row",
    "grow_then_refuse_leaves_a_blank_row",
    "refuse_then_rewrite_clean",
    "readings_not_a_list_keeps_the_rows",
    "reading_not_a_dict_keeps_the_row_count",
    "wires_refused_then_good",
    "paint_refused_then_good",
    "opacity_endless",
    "opacity_not_a_number",
    "opacity_text",
}


# The shared registers this file touches, each put back after


@pytest.fixture(autouse=True)
def own_bridge_model():
    """Give this test its own bridge model and put the shared one back."""
    original = surface.PANE_MODEL
    surface.PANE_MODEL = surface.BotSwarmListModel()
    yield
    surface.PANE_MODEL = original


@pytest.fixture(autouse=True)
def own_logger_level():
    """Let this test read the sheet's own log and put the level back."""
    log = logging.getLogger(surface.LOGGER_NAME)
    original = log.level
    log.setLevel(logging.INFO)
    yield
    log.setLevel(original)


class LineCatcher(logging.Handler):
    """Keeps every record the sheet's logger emits, as level and text.

    The caller may hand in the list to fill, so lines written before a
    refusal survive the refusal.
    """

    def __init__(self, lines=None):
        super().__init__(level=logging.NOTSET)
        self.lines: list = [] if lines is None else lines

    def emit(self, record):
        """Keep one record. A failure here loses a log line, not a test."""
        self.lines.append([record.levelname, record.getMessage()])


# Reading a value the same way on both sides


SHORT_HEX_LENGTH = 4
HEX_MARK = "#"


def long_hex(colour):
    """One colour as six hex digits, whatever width it is written in.

    A three-digit token names the same colour with each digit doubled,
    and six is the width the screen reports, so both sides of a colour
    comparison read one spelling.
    """
    if (
        isinstance(colour, str)
        and len(colour) == SHORT_HEX_LENGTH
        and colour.startswith(HEX_MARK)
    ):
        return HEX_MARK + "".join(digit * 2 for digit in colour[1:])
    return colour


def painted_colour(colour, brush):
    """The colour a cell was seeded with, or the unset one.

    A cell the code never gave a colour still reports one, because the
    drawing library fills in its own. That is a value the platform
    chose, not a value the product set, and it is hidden here.
    """
    if brush != surface.SET_BRUSH:
        return surface.UNSET_COLOR
    return long_hex(colour)


def numbers_as_text(value):
    """One value with every number read as its own text.

    ``12`` and ``12.0`` are different figures and must not compare
    alike. Two not-a-numbers are the same figure and must, which a
    plain comparison never reports because a not-a-number equals
    nothing, itself included.
    """
    if isinstance(value, dict):
        return {str(key): numbers_as_text(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [numbers_as_text(item) for item in value]
    if isinstance(value, (bool, int, float)):
        return repr(value)
    return value


def digest(body):
    """One side's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(numbers_as_text(body), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def guarded(run):
    """Run one drive, keeping either what it returned or how it refused."""
    try:
        return {"error": "", "message": "", "answer": run()}
    except Exception as exc:
        return {"error": type(exc).__name__, "message": str(exc), "answer": None}


def app():
    """The process application object every render needs."""
    from tests.qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


# Reading the two sides into one shape


def requested_widths(module):
    """The width each column is asked for, from one module's own values.

    The width a column ends up with is the header's business: a header
    lifts a column narrower than its own smallest section. The request
    is what each side declares, so the request is what compares.
    """
    return [
        module.TICKER_COL_WIDTH,
        module.FLOW_COL_WIDTH,
        module.FLOW_COL_WIDTH,
        module.OUTFLOW_PCT_COL_WIDTH,
    ] + [module.LANE_COL_WIDTH] * module.LANE_COUNT


_SCREEN_WIDTHS: list = []


def screen_column_widths():
    """The width the screen actually gives each column of the list.

    Read once off a real list, then handed to the surface, so both
    sides place their lanes from one set of widths rather than two.
    """
    if not _SCREEN_WIDTHS:
        view = old_list()
        _SCREEN_WIDTHS.extend(
            view.columnWidth(column) for column in range(view.columnCount())
        )
    return list(_SCREEN_WIDTHS)


def read_old_list(view):
    """The shipped list's whole state, read off the widget."""
    from PySide6.QtCore import Qt

    rows = []
    for row in range(view.rowCount()):
        cells = []
        for column in range(view.columnCount()):
            item = view.item(row, column)
            if item is None:
                cells.append(None)
                continue
            brush = item.foreground().style().name
            cells.append(
                {
                    "kind": type(item).__name__,
                    "text": item.text(),
                    "alignment": int(item.textAlignment()),
                    "color": painted_colour(item.foreground().color().name(), brush),
                    "brush": brush,
                    "bot_id": item.data(Qt.UserRole),
                }
            )
        rows.append(cells)
    return {
        "rows": rows,
        "row_count": view.rowCount(),
        "column_count": view.columnCount(),
        "bot_ids": view.bot_ids(),
        "row_index_map": view.row_index_map(),
        "headers": [
            view.horizontalHeaderItem(column).text()
            for column in range(view.columnCount())
        ],
        "requested_widths": requested_widths(shipped),
        "accessible_name": view.accessibleName(),
        "style_sheet": view.styleSheet(),
        "row_y_centers": [view.row_y_center(row) for row in range(view.rowCount())],
    }


def read_new_list(model):
    """The surface list's whole state in the same shape."""
    rows = []
    for row in model.rows:
        cells = []
        for found in row:
            if found is None:
                cells.append(None)
                continue
            cells.append(
                {
                    "kind": found["kind"],
                    "text": found["text"],
                    "alignment": found["alignment"],
                    "color": painted_colour(found["color"], found["brush"]),
                    "brush": found["brush"],
                    "bot_id": found["bot_id"],
                }
            )
        rows.append(cells)
    return {
        "rows": rows,
        "row_count": model.row_count,
        "column_count": surface.TOTAL_COLS,
        "bot_ids": model.bot_ids(),
        "row_index_map": model.row_index_map(),
        "headers": list(surface.COLUMN_HEADERS),
        "requested_widths": requested_widths(surface),
        "accessible_name": model.accessible_name,
        "style_sheet": surface.LIST_STYLE_SHEET,
        "row_y_centers": [model.row_y_center(row) for row in range(model.row_count)],
    }


def read_old_canvas(canvas, calls, lines):
    """The shipped sheet's whole state, read off the widget."""
    return {
        "calls": calls,
        "undrawable": [list(found) for found in canvas.undrawable_wires()],
        "undrawable_count": canvas.undrawable_wire_count(),
        "opacity_pct": canvas._opacity_pct,
        "lane_assignments": dict(canvas._lane_assignments),
        "wire_count": len(canvas._wires),
        "accessible_name": canvas.accessibleName(),
        "style_sheet": canvas.styleSheet(),
        "log_lines": lines,
    }


def read_new_canvas(model):
    """The surface sheet's whole state in the same shape."""
    return {
        "calls": [list(call) for call in model.calls],
        "undrawable": [list(found) for found in model.undrawable_wires()],
        "undrawable_count": model.undrawable_wire_count(),
        "opacity_pct": model.opacity_pct,
        "lane_assignments": model.lane_assignments,
        "wire_count": model.wire_count,
        "accessible_name": model.accessible_name,
        "style_sheet": model.style_sheet,
        "log_lines": [list(line) for line in model.log_lines],
    }


# Drivers


def recording_painter(image, calls):
    """A stand-in painter that keeps every drawing call and forwards it.

    Everything the sheet works out reaches this unchanged. A pen given
    as a bare style carries no colour and no width, which is recorded
    as the style alone.
    """
    from PySide6.QtGui import QPainter, QPen

    def colour_of(found):
        return [found.red(), found.green(), found.blue(), found.alpha()]

    class Catcher:
        """Records the drawing calls the sheet makes and forwards them."""

        Antialiasing = QPainter.RenderHint.Antialiasing

        def __init__(self, _device):
            self.painter = QPainter(image)
            calls.append([surface.BEGIN_PAINTER])

        def setRenderHint(self, hint):
            """Keep the hint by name and value, then set it."""
            calls.append([surface.SET_RENDER_HINT, hint.name, int(hint.value)])
            self.painter.setRenderHint(hint)

        def setOpacity(self, value):
            """Keep the brightness, then set it."""
            calls.append([surface.SET_OPACITY, value])
            self.painter.setOpacity(value)

        def setPen(self, pen):
            """Keep the pen, unwrapping a gradient into its stops."""
            if isinstance(pen, QPen):
                found = pen.brush().gradient()
                calls.append(
                    [
                        surface.SET_GRADIENT_PEN,
                        [found.start().x(), found.start().y()],
                        [found.finalStop().x(), found.finalStop().y()],
                        [
                            [position, colour_of(colour)]
                            for position, colour in found.stops()
                        ],
                        pen.width(),
                        pen.style().name,
                    ]
                )
            else:
                calls.append([surface.SET_PEN_STYLE, pen.name])
            self.painter.setPen(pen)

        def setBrush(self, brush):
            """Keep the fill colour and pattern, then set it."""
            calls.append(
                [surface.SET_BRUSH_CALL, colour_of(brush.color()), brush.style().name]
            )
            self.painter.setBrush(brush)

        def drawLine(self, *found):
            """Keep the line's four coordinates, then draw it."""
            calls.append([surface.DRAW_LINE, list(found)])
            self.painter.drawLine(*found)

        def drawEllipse(self, centre, radius_x, radius_y):
            """Keep the dot's centre and radii, then draw it."""
            calls.append(
                [
                    surface.DRAW_ELLIPSE,
                    [centre.x(), centre.y()],
                    radius_x,
                    radius_y,
                ]
            )
            self.painter.drawEllipse(centre, radius_x, radius_y)

        def end(self):
            """Keep the close, then close."""
            calls.append([surface.END_PAINTER])
            self.painter.end()

    return Catcher


def old_list(case=None):
    """One real BotListView, held so no later read reaches a gone widget."""
    app()
    view = shipped.BotListView()
    HELD.append(view)
    if case is not None:
        view.set_bots(CASES[case])
    return view


def new_list(case=None, widths=None):
    """One surface list, driven over the same case.

    `widths` is the width the screen gives each column, which the
    lane coordinates follow.
    """
    model = surface.BotListModel()
    if widths is not None:
        model.set_column_widths(widths)
    if case is not None:
        model.set_bots(CASES[case])
    return model


def old_canvas(view):
    """One real LaneWireCanvas over a given list."""
    app()
    canvas = shipped.LaneWireCanvas(view)
    HELD.append(canvas)
    return canvas


def old_paint_into(canvas, calls, lines, event=None):
    """Drive the shipped sheet's paint into `calls` and `lines`.

    Both lists keep what the paint managed before a refusal, so a paint
    that stops part way is compared as it left the sheet.
    """
    from PySide6.QtGui import QImage

    image = QImage(PAINT_SIZE[0], PAINT_SIZE[1], QImage.Format_ARGB32)
    HELD.append(image)
    log = logging.getLogger(surface.LOGGER_NAME)
    catcher = LineCatcher(lines)
    log.addHandler(catcher)
    was = shipped.QPainter
    shipped.QPainter = recording_painter(image, calls)
    try:
        canvas.paintEvent(event)
    finally:
        shipped.QPainter = was
        log.removeHandler(catcher)


def old_paint(canvas, event=None):
    """One paint of the shipped sheet: its calls, its lines, its outcome."""
    calls: list = []
    lines: list = []
    outcome = guarded(lambda: old_paint_into(canvas, calls, lines, event))
    return calls, lines, outcome


def old_side(case):
    """The shipped list driven over one case, and what it holds after."""
    view = old_list()
    run = guarded(lambda: view.set_bots(CASES[case]))
    return {"run": run, "state": read_old_list(view)}


def new_side(case):
    """The surface list driven over the same case."""
    model = new_list()
    run = guarded(lambda: model.set_bots(CASES[case]))
    return {"run": run, "state": read_new_list(model)}


def old_wire_side(name):
    """The shipped sheet driven over one wire case, painted once."""
    rows, wires = WIRE_CASES[name]
    view = old_list(rows)
    canvas = old_canvas(view)
    run = guarded(lambda: canvas.set_wires(wires))
    calls, lines, painted = old_paint(canvas)
    return {
        "run": run,
        "paint": {"error": painted["error"], "message": painted["message"]},
        "state": read_old_canvas(canvas, calls, lines),
    }


def new_wire_side(name):
    """The surface sheet driven over the same wire case."""
    rows, wires = WIRE_CASES[name]
    listing = new_list(rows, screen_column_widths())
    model = surface.LaneWireModel(listing)
    run = guarded(lambda: model.set_wires(wires))
    painted = guarded(model.paint)
    return {
        "run": run,
        "paint": {"error": painted["error"], "message": painted["message"]},
        "state": read_new_canvas(model),
    }


def run_steps(host, canvas, steps, is_old):
    """Drive one sequence through either side, keeping each outcome."""
    seen = []
    for step in steps:
        name = step[0]
        if name == "bots":
            seen.append(guarded(lambda case=step[1]: host.set_bots(CASES[case])))
        elif name == "wires":
            wires = WIRE_CASES[step[1]][1]
            seen.append(guarded(lambda found=wires: canvas.set_wires(found)))
        elif name == "opacity":
            seen.append(guarded(lambda value=step[1]: canvas.set_opacity_pct(value)))
        elif name == "paint":
            if is_old:
                found = old_paint(canvas)[2]
            else:
                found = guarded(canvas.paint)
            seen.append({"error": found["error"], "message": found["message"]})
    return seen


def old_steps(name):
    """The shipped pair driven over one sequence of steps."""
    view = old_list()
    canvas = old_canvas(view)
    runs = run_steps(view, canvas, STEP_CASES[name], is_old=True)
    calls, lines, _ = old_paint(canvas)
    return {
        "runs": runs,
        "list": read_old_list(view),
        "canvas": read_old_canvas(canvas, calls, lines),
    }


def new_steps(name):
    """The surface pair driven over the same sequence of steps."""
    listing = new_list(widths=screen_column_widths())
    canvas = surface.LaneWireModel(listing)
    runs = run_steps(listing, canvas, STEP_CASES[name], is_old=False)
    canvas.paint()
    return {
        "runs": runs,
        "list": read_new_list(listing),
        "canvas": read_new_canvas(canvas),
    }


def same(new, old, note):
    """Fail unless the two sides carry the same values and the same hash."""
    assert numbers_as_text(new) == numbers_as_text(old), note
    assert digest(new) == digest(old), note


# Side by side


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_row_state_is_the_shipped_lists(name):
    """The surface builds a different row than the shipped list."""
    same(new_side(name), old_side(name), name)


@pytest.mark.parametrize("name", sorted(WIRE_CASES))
def test_the_sheet_state_is_the_shipped_sheets(name):
    """The surface draws a different sheet than the shipped canvas."""
    same(new_wire_side(name), old_wire_side(name), name)


@pytest.mark.parametrize("name", sorted(STEP_CASES))
def test_the_driven_state_is_the_shipped_pairs(name):
    """The surface holds a different state after the same steps."""
    same(new_steps(name), old_steps(name), name)


def test_the_sample_hashes_are_reported():
    """The reported sample hashes are not the hashes the run produced."""
    samples = {
        "rows_happy": digest(new_side("happy")),
        "rows_all_pct_bands": digest(new_side("all_pct_bands")),
        "wires_one": digest(new_wire_side("one_wire")),
        "wires_exhausted": digest(new_wire_side("nine_wires_exhaust_the_lanes")),
        "steps_recover": digest(new_steps("drop_then_recover_logs_twice")),
    }
    assert samples["rows_happy"] == digest(old_side("happy"))
    assert samples["rows_all_pct_bands"] == digest(old_side("all_pct_bands"))
    assert samples["wires_one"] == digest(old_wire_side("one_wire"))
    assert samples["wires_exhausted"] == digest(
        old_wire_side("nine_wires_exhaust_the_lanes")
    )
    assert samples["steps_recover"] == digest(old_steps("drop_then_recover_logs_twice"))
    assert all(len(found) == 64 for found in samples.values()), samples
    assert len(set(samples.values())) == len(samples), samples


def test_two_genuinely_different_inputs_hash_apart_in_both_directions():
    """The hash reports one value for every input, so a match means
    nothing."""
    assert digest(old_side("happy")) != digest(new_side("two_bots"))
    assert digest(new_side("happy")) != digest(old_side("two_bots"))
    assert digest(old_side("zero")) != digest(new_side("negative"))
    assert digest(new_side("zero")) != digest(old_side("negative"))
    assert digest(old_wire_side("one_wire")) != digest(new_wire_side("two_disjoint"))
    assert digest(new_wire_side("one_wire")) != digest(old_wire_side("two_disjoint"))
    assert digest(old_steps("shrink_to_empty")) != digest(new_steps("empty_then_grow"))
    assert digest(new_steps("shrink_to_empty")) != digest(old_steps("empty_then_grow"))


def test_one_input_hashes_the_same_twice():
    """The hash moves between two runs of one input, so no match means
    anything."""
    assert digest(new_side("four_bots")) == digest(new_side("four_bots"))
    assert digest(old_side("four_bots")) == digest(old_side("four_bots"))
    assert digest(new_wire_side("two_overlapping")) == digest(
        new_wire_side("two_overlapping")
    )
    assert digest(old_steps("opacity_then_paint")) == digest(
        old_steps("opacity_then_paint")
    )


def test_a_whole_number_and_a_decimal_hash_apart():
    """A whole number and a decimal read alike, so a figure that changed
    kind would pass."""
    assert digest(12) != digest(12.0)
    assert numbers_as_text(12) != numbers_as_text(12.0)
    assert numbers_as_text([12]) != numbers_as_text([12.0])
    assert numbers_as_text({"a": 12}) != numbers_as_text({"a": 12.0})
    assert numbers_as_text(True) != numbers_as_text(1)
    same(new_side("whole_number_amount"), old_side("whole_number_amount"), "whole")
    same(new_side("decimal_amount"), old_side("decimal_amount"), "decimal")


def test_two_separately_built_not_a_numbers_read_alike():
    """Two not-a-numbers read apart, so every case carrying one would
    report a difference that is not one."""
    first = float("nan")
    second = float("inf") - float("inf")
    assert first != second
    assert first != first
    assert numbers_as_text(first) == numbers_as_text(second)
    assert digest([first]) == digest([second])
    assert numbers_as_text(first) != numbers_as_text(0.0)


# Answered or refused


def test_the_row_outcomes_hold_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the input table
    exercises one outcome and proves nothing about the other."""
    outcomes = {name: new_side(name)["run"]["error"] for name in CASES}
    assert outcomes == {name: old_side(name)["run"]["error"] for name in CASES}
    answered = sorted(name for name, error in outcomes.items() if not error)
    refused = sorted(name for name, error in outcomes.items() if error)
    assert answered, outcomes
    assert refused, outcomes
    assert set(refused) == set(REFUSED_CASES), refused
    assert len(answered) + len(refused) == len(CASES)
    assert {outcomes[name] for name in refused} == {
        "AttributeError",
        "TypeError",
        "ValueError",
    }
    assert outcomes["infinity"] == ""
    assert outcomes["not_a_number"] == ""
    assert outcomes["minus_infinity"] == ""


def test_the_wire_outcomes_hold_both_an_answer_and_a_refusal():
    """Every wire case answered, or every one refused."""
    outcomes = {}
    for name in WIRE_CASES:
        new = new_wire_side(name)
        old = old_wire_side(name)
        assert new["run"]["error"] == old["run"]["error"], name
        assert new["paint"]["error"] == old["paint"]["error"], name
        outcomes[name] = new["run"]["error"] or new["paint"]["error"]
    answered = sorted(name for name, error in outcomes.items() if not error)
    refused = sorted(name for name, error in outcomes.items() if error)
    assert answered, outcomes
    assert refused, outcomes
    assert set(refused) == set(REFUSED_WIRE_CASES), refused
    assert {outcomes[name] for name in refused} == {
        "AttributeError",
        "TypeError",
        "ValueError",
    }


@pytest.mark.parametrize("name", sorted(REFUSED_CASES))
def test_every_row_refusal_carries_the_shipped_lists_own_words(name):
    """A refusal reads differently on the two sides."""
    old = old_side(name)["run"]
    new = new_side(name)["run"]
    assert new["error"] == old["error"] == REFUSED_CASES[name], name
    assert new["message"] == old["message"], name
    assert new["message"], name
    assert new["message"].splitlines()[0] == old["message"].splitlines()[0], name


@pytest.mark.parametrize("name", sorted(REFUSED_WIRE_CASES))
def test_every_wire_refusal_carries_the_shipped_sheets_own_words(name):
    """A wire refusal reads differently on the two sides."""
    old = old_wire_side(name)
    new = new_wire_side(name)
    for part in ("run", "paint"):
        assert new[part]["error"] == old[part]["error"], (name, part)
        assert new[part]["message"] == old[part]["message"], (name, part)
    assert (old["run"]["error"] or old["paint"]["error"]) == REFUSED_WIRE_CASES[name]


def test_the_refusal_words_come_from_the_platform_and_are_read_off_both():
    """The two sides refuse in different words, and the comparison of
    those words would not report it."""
    old = old_side("text_where_number_belongs")["run"]["message"]
    new = new_side("text_where_number_belongs")["run"]["message"]
    assert old == new
    assert old != "a different refusal than either side wrote"
    changed = dict(new_side("text_where_number_belongs")["run"])
    changed["message"] = "a different refusal than either side wrote"
    assert changed["message"] != old
    assert digest(changed) != digest(new_side("text_where_number_belongs")["run"])


def test_a_refusal_leaves_the_same_half_written_row_on_both_sides():
    """A refusal part way through a row leaves a different table."""
    readings = [reading(), reading(bot_id="bot-b", outflow_pct="many")]
    view = old_list()
    model = new_list()
    old_run = guarded(lambda: view.set_bots(readings))
    new_run = guarded(lambda: model.set_bots(readings))
    assert old_run["error"] == new_run["error"] == "ValueError"
    assert view.rowCount() == model.row_count == 2
    assert view.item(1, surface.COL_TICKER) is not None
    assert view.item(1, surface.COL_OUTFLOW_PCT) is None
    assert model.rows[1][surface.COL_OUTFLOW_PCT] is None
    assert model.rows[1][surface.COL_TICKER] is not None
    assert model.written_cell_count == 12 + 3
    same(read_new_list(model), read_old_list(view), "half written row")


def test_a_refusal_after_a_shrink_leaves_the_earlier_paint_on_both_sides():
    """A rewrite that refuses part way through wiped a row the operator
    could still see, or kept one the shipped list dropped."""
    view = old_list("three_bots")
    model = new_list("three_bots")
    first = view.item(1, surface.COL_TICKER).text()
    readings = [reading(bot_id="d", symbol="DDD"), reading(bot_id="e", inflow_usd="no")]
    assert guarded(lambda: view.set_bots(readings))["error"] == "ValueError"
    assert guarded(lambda: model.set_bots(readings))["error"] == "ValueError"
    assert view.rowCount() == model.row_count == 2
    assert view.item(1, surface.COL_TICKER).text() == first
    assert model.rows[1][surface.COL_TICKER]["text"] == first
    assert first == "ETH"
    same(read_new_list(model), read_old_list(view), "shrink then refuse")


# What the two sides do, value by value


def test_the_headers_are_the_shipped_lists():
    """A column header moved on one side."""
    view = old_list()
    assert list(surface.COLUMN_HEADERS) == list(shipped.COLUMN_HEADERS)
    assert surface.COLUMN_HEADERS[:4] == ["Ticker", "Inflow", "Outflow", "% Out"]
    assert surface.COLUMN_HEADERS[surface.COL_LANE_0] == "L1"
    assert surface.COLUMN_HEADERS[surface.COL_LANE_LAST] == "L8"
    assert surface.TOTAL_COLS == view.columnCount() == 12
    for column in range(view.columnCount()):
        assert view.horizontalHeaderItem(column).text() == (
            surface.COLUMN_HEADERS[column]
        ), column


def test_the_requested_column_widths_are_the_shipped_lists():
    """A column width asked for moved on one side."""
    assert requested_widths(surface) == requested_widths(shipped)
    assert list(surface.COLUMN_WIDTHS) == requested_widths(surface)
    assert surface.TICKER_COL_WIDTH == 90
    assert surface.FLOW_COL_WIDTH == 90
    assert surface.OUTFLOW_PCT_COL_WIDTH == 60
    assert surface.LANE_COL_WIDTH == 20
    assert len(surface.COLUMN_WIDTHS) == surface.TOTAL_COLS


def test_the_header_lifts_a_column_narrower_than_its_smallest_section():
    """A width read back off the header is taken as the width asked
    for, which on a host holding fonts is a different number."""
    view = old_list()
    header = view.horizontalHeader()
    asked = requested_widths(shipped)
    in_use = [view.columnWidth(column) for column in range(view.columnCount())]
    smallest = header.minimumSectionSize()
    for column, width in enumerate(asked):
        assert in_use[column] >= width, column
        assert in_use[column] == max(width, smallest), column
    for column in surface.READOUT_COLUMNS:
        assert in_use[column] == asked[column], column
    assert in_use == screen_column_widths()
    assert (in_use == asked) is (smallest <= surface.LANE_COL_WIDTH)


def test_the_lane_and_row_coordinates_are_the_shipped_lists():
    """A wire would be drawn down a different column or across a
    different row.

    Both sides are given the widths the screen gave the columns,
    which is the input the shipped list reads its coordinates from.
    """
    view = old_list("four_bots")
    in_use = screen_column_widths()
    model = new_list("four_bots", in_use)
    for lane in range(-1, surface.LANE_COUNT + 1):
        assert model.lane_col_x(lane) == view.lane_col_x(lane), lane
    for row in range(-1, 6):
        assert model.row_y_center(row) == view.row_y_center(row), row
    assert model.lane_col_x(-1) == model.lane_col_x(surface.LANE_COUNT) == 0
    assert model.row_y_center(0) == 15
    assert model.row_y_center(3) == 105
    assert model.row_y_center(4) == 0
    assert model.lane_col_x(1) - model.lane_col_x(0) == in_use[surface.COL_LANE_0]
    assert model.row_y_center(1) - model.row_y_center(0) == surface.ROW_HEIGHT


def test_the_lane_coordinates_move_when_the_widths_do():
    """The lane coordinate ignores the widths it is given, so giving
    both sides one set of widths would compare a value to itself."""
    model = new_list("four_bots")
    assert model.column_widths == list(surface.COLUMN_WIDTHS)
    assert model.lane_col_x(0) == 340
    assert model.lane_col_x(surface.LANE_COUNT - 1) == 480
    wider = list(surface.COLUMN_WIDTHS)
    wider[surface.COL_LANE_0] = 100
    model.set_column_widths(wider)
    assert model.lane_col_x(0) == 380
    assert model.lane_col_x(1) == 440
    assert surface.lane_column_x(0) == 340
    assert surface.lane_column_x(0, wider) == 380
    assert new_list("four_bots").lane_col_x(0) == 340


def test_the_money_cells_are_the_shipped_lists():
    """A dollar figure is written differently on one side."""
    cells = new_side("happy")["state"]["rows"][0]
    assert cells[surface.COL_INFLOW]["text"] == "$12.50"
    assert cells[surface.COL_OUTFLOW]["text"] == "$3.25"
    assert cells[surface.COL_INFLOW]["color"] == INFLOW_GREEN
    assert cells[surface.COL_OUTFLOW]["color"] == OUTFLOW_RED
    assert surface.amount_text(1234567.5) == "$1,234,567.50"
    assert surface.amount_text(0.0) == "$0.00"
    assert surface.amount_text(-5.5) == "$-5.50"
    negative = old_side("negative")["state"]["rows"][0]
    assert negative[surface.COL_INFLOW]["text"] == "$-5.50"
    assert negative[surface.COL_OUTFLOW]["text"] == "$-1.00"
    assert new_side("negative")["state"]["rows"][0] == negative


def test_every_export_share_colour_is_the_shipped_lists():
    """An export share paints in another band's colour."""
    bands = {
        "zero": NO_EXPORT_GREY,
        "negative": NO_EXPORT_GREY,
        "pct_just_over_nothing": HEADROOM_CYAN,
        "pct_at_headroom_edge": HEADROOM_CYAN,
        "pct_over_headroom_edge": NEAR_CAP_AMBER,
        "pct_under_cap": NEAR_CAP_AMBER,
        "pct_at_cap": OUTFLOW_RED,
        "pct_over_cap": OUTFLOW_RED,
    }
    for name, colour in bands.items():
        old = old_side(name)["state"]["rows"][0][surface.COL_OUTFLOW_PCT]
        new = new_side(name)["state"]["rows"][0][surface.COL_OUTFLOW_PCT]
        assert old == new, name
        assert old["color"] == colour, name
    assert surface.pct_color(0) == NO_EXPORT_GREY
    assert surface.pct_color(80) == HEADROOM_CYAN
    assert surface.pct_color(81) == NEAR_CAP_AMBER
    assert surface.pct_color(100) == OUTFLOW_RED
    assert len(set(bands.values())) == 4


def test_an_export_share_that_is_not_a_number_paints_red_on_both_sides():
    """A share that is not a number takes another band's colour, which
    would tell the operator a broken figure is safe."""
    old = old_side("not_a_number")["state"]["rows"][0][surface.COL_OUTFLOW_PCT]
    new = new_side("not_a_number")["state"]["rows"][0][surface.COL_OUTFLOW_PCT]
    assert old == new
    assert old["text"] == "nan%"
    assert old["color"] == OUTFLOW_RED
    assert surface.pct_color(NOT_A_NUMBER) == surface.PCT_COMMITTED_COLOR
    assert not (NOT_A_NUMBER <= 0)
    assert not (NOT_A_NUMBER < surface.PCT_HEADROOM_LIMIT)


def test_the_endless_shares_paint_the_two_far_bands_on_both_sides():
    """An endless share reads as one band on one side."""
    endless = old_side("infinity")["state"]["rows"][0]
    assert new_side("infinity")["state"]["rows"][0] == endless
    assert endless[surface.COL_INFLOW]["text"] == "$inf"
    assert endless[surface.COL_OUTFLOW_PCT]["text"] == "inf%"
    assert endless[surface.COL_OUTFLOW_PCT]["color"] == OUTFLOW_RED
    backwards = old_side("minus_infinity")["state"]["rows"][0]
    assert new_side("minus_infinity")["state"]["rows"][0] == backwards
    assert backwards[surface.COL_INFLOW]["text"] == "$-inf"
    assert backwards[surface.COL_OUTFLOW_PCT]["text"] == "-inf%"
    assert backwards[surface.COL_OUTFLOW_PCT]["color"] == NO_EXPORT_GREY


def test_a_very_large_and_a_very_small_figure_read_alike_on_both_sides():
    """A very large or very small figure is written differently on one
    side."""
    big = old_side("thousand_million")["state"]["rows"][0]
    assert new_side("thousand_million")["state"]["rows"][0] == big
    assert big[surface.COL_INFLOW]["text"] == "$1,000,000,000.00"
    assert big[surface.COL_OUTFLOW_PCT]["text"] == "1000000000%"
    small = old_side("one_billionth")["state"]["rows"][0]
    assert new_side("one_billionth")["state"]["rows"][0] == small
    assert small[surface.COL_INFLOW]["text"] == "$0.00"
    assert small[surface.COL_OUTFLOW_PCT]["text"] == "0%"
    assert small[surface.COL_OUTFLOW_PCT]["color"] == HEADROOM_CYAN


def test_the_ticker_cell_carries_the_bot_it_belongs_to_on_both_sides():
    """The row lost the bot it stands for, so a click would name the
    wrong one."""
    old = old_side("two_bots")["state"]
    new = new_side("two_bots")["state"]
    assert old["rows"][0][surface.COL_TICKER]["bot_id"] == "bot-a"
    assert old["rows"][1][surface.COL_TICKER]["bot_id"] == "bot-b"
    assert new["rows"] == old["rows"]
    assert old["bot_ids"] == new["bot_ids"] == ["bot-a", "bot-b"]
    assert old["row_index_map"] == new["row_index_map"] == {"bot-a": 0, "bot-b": 1}
    for row in old["rows"]:
        for column in surface.LANE_COLUMNS:
            assert row[column]["bot_id"] is None, column
        assert row[surface.COL_INFLOW]["bot_id"] is None


def test_the_row_lookup_answers_alike_on_both_sides():
    """A bot resolves to a different row on one side."""
    view = old_list("three_bots")
    model = new_list("three_bots")
    for bot in ("bot-a", "bot-b", "bot-c", "gone", ""):
        assert model.row_of_bot(bot) == view.row_of_bot(bot), bot
    assert model.row_of_bot("bot-c") == 2
    assert model.row_of_bot("gone") == surface.NO_ROW == -1
    assert model.row_index_map() == view.row_index_map()


def test_the_lane_cells_hold_no_text_and_no_colour_on_both_sides():
    """A lane cell grew text or a colour, which would sit under a wire."""
    for name in ("happy", "four_bots", "all_pct_bands"):
        old = old_side(name)["state"]["rows"]
        new = new_side(name)["state"]["rows"]
        assert new == old, name
        for row in old:
            for column in surface.LANE_COLUMNS:
                assert row[column]["text"] == surface.LANE_CELL_TEXT == "", column
                assert row[column]["brush"] == surface.UNSET_BRUSH, column
                assert row[column]["color"] == surface.UNSET_COLOR, column
                assert row[column]["alignment"] == surface.LANE_ALIGNMENT_VALUE == 0
    assert len(surface.LANE_COLUMNS) == surface.LANE_COUNT == 8


def test_only_the_three_money_cells_carry_a_colour_on_both_sides():
    """A cell was painted a colour the shipped list leaves alone."""
    for row in old_side("four_bots")["state"]["rows"]:
        for column in range(surface.TOTAL_COLS):
            if column in surface.COLOURED_COLUMNS:
                assert row[column]["brush"] == surface.SET_BRUSH, column
                assert row[column]["color"] != surface.UNSET_COLOR, column
            else:
                assert row[column]["brush"] == surface.UNSET_BRUSH, column
                assert row[column]["color"] == surface.UNSET_COLOR, column
    assert surface.COLOURED_COLUMNS == (
        surface.COL_INFLOW,
        surface.COL_OUTFLOW,
        surface.COL_OUTFLOW_PCT,
    )
    assert surface.COL_TICKER not in surface.COLOURED_COLUMNS


def test_the_readout_cells_are_centred_on_both_sides():
    """A readout cell sits differently in its column on one side."""
    for row in old_side("four_bots")["state"]["rows"]:
        for column in surface.READOUT_COLUMNS:
            assert row[column]["alignment"] == surface.CENTRED_ALIGNMENT_VALUE, column
    assert surface.CENTRED_ALIGNMENT_VALUE == 132
    assert surface.CENTRED_ALIGNMENT == "AlignCenter"
    assert new_side("four_bots")["state"]["rows"] == (
        old_side("four_bots")["state"]["rows"]
    )


def test_the_centred_alignment_value_is_the_drawing_librarys_own():
    """The centred alignment number is not the one the library uses, so
    every cell would sit in the wrong place."""
    from PySide6.QtCore import Qt

    app()
    assert int(Qt.AlignCenter) == surface.CENTRED_ALIGNMENT_VALUE
    assert Qt.AlignmentFlag(surface.CENTRED_ALIGNMENT_VALUE).name == (
        surface.CENTRED_ALIGNMENT
    )
    assert int(Qt.UserRole) == surface.BOT_ID_ROLE_VALUE == 256
    assert Qt.ItemDataRole(surface.BOT_ID_ROLE_VALUE).name == surface.BOT_ID_ROLE


def test_a_two_hundred_character_name_survives_whole_on_both_sides():
    """A long name was cut short on one side."""
    old = old_side("long_text")["state"]["rows"][0]
    new = new_side("long_text")["state"]["rows"][0]
    assert old == new
    assert len(old[surface.COL_TICKER]["text"]) == 200
    assert old[surface.COL_TICKER]["text"] == LONG_TEXT


def test_markup_and_an_apostrophe_reach_the_cell_unchanged_on_both_sides():
    """Markup or an apostrophe was rewritten on one side."""
    for name, text in (("markup", MARKUP_TEXT), ("apostrophe", APOSTROPHE_TEXT)):
        old = old_side(name)["state"]["rows"][0]
        new = new_side(name)["state"]["rows"][0]
        assert old == new, name
        assert old[surface.COL_TICKER]["text"] == text, name
    assert "<script>" in MARKUP_TEXT
    assert "'" in APOSTROPHE_TEXT


def test_a_newline_and_unicode_reach_the_cell_on_both_sides():
    """A line break or a foreign letter was flattened on one side."""
    broken = old_side("newline_name")["state"]["rows"][0]
    assert new_side("newline_name")["state"]["rows"][0] == broken
    assert broken[surface.COL_TICKER]["text"] == NEWLINE_TEXT
    assert "\n" in broken[surface.COL_TICKER]["text"]
    foreign = old_side("unicode")["state"]["rows"][0]
    assert new_side("unicode")["state"]["rows"][0] == foreign
    assert foreign[surface.COL_TICKER]["text"] == UNICODE_TEXT


def test_the_capitals_of_a_name_are_left_alone_on_both_sides():
    """A name came back in different capitals on one side."""
    old = old_side("wrong_capitals")["state"]
    new = new_side("wrong_capitals")["state"]
    assert old == new
    assert old["rows"][0][surface.COL_TICKER]["text"] == "btc"
    assert old["bot_ids"] == ["BOT-A"]
    assert old["rows"][0][surface.COL_TICKER]["text"] != "BTC"


def test_a_number_where_text_belongs_reads_as_its_digits_on_both_sides():
    """A number in a text column reads differently on one side."""
    old = old_side("number_where_text_belongs")["state"]
    new = new_side("number_where_text_belongs")["state"]
    assert old == new
    assert old["rows"][0][surface.COL_TICKER]["text"] == "7"
    assert old["bot_ids"] == ["7"]


def test_a_missing_key_and_a_none_take_the_shipped_lists_own_default():
    """A missing key or an empty value reads differently on one side."""
    missing = old_side("missing_keys")["state"]
    assert new_side("missing_keys")["state"] == missing
    assert missing["rows"][0][surface.COL_TICKER]["text"] == surface.MISSING_TEXT == ""
    assert missing["rows"][0][surface.COL_INFLOW]["text"] == "$0.00"
    assert missing["rows"][0][surface.COL_OUTFLOW_PCT]["color"] == NO_EXPORT_GREY
    assert missing["bot_ids"] == [""]
    empty = old_side("none_values")["state"]
    assert new_side("none_values")["state"] == empty
    assert empty["rows"][0][surface.COL_TICKER]["text"] == "None"
    assert empty["rows"][0][surface.COL_INFLOW]["text"] == "$0.00"


def test_the_accessible_names_are_the_shipped_widgets():
    """The name a screen reader announces moved on one side."""
    view = old_list()
    canvas = old_canvas(view)
    assert view.accessibleName() == surface.LIST_ACCESSIBLE_NAME == "Bot Swarm List"
    assert canvas.accessibleName() == surface.CANVAS_ACCESSIBLE_NAME
    assert surface.CANVAS_ACCESSIBLE_NAME == "Bot Swarm Lane Wire Canvas"
    assert surface.LIST_ACCESSIBLE_NAME != surface.CANVAS_ACCESSIBLE_NAME


def test_the_list_settings_are_the_shipped_lists():
    """A list setting the operator relies on moved on one side."""
    view = old_list()
    header = view.horizontalHeader()
    assert view.alternatingRowColors() is surface.ALTERNATING_ROW_COLORS is False
    assert view.selectionBehavior().name == surface.SELECTION_BEHAVIOR
    assert view.editTriggers().name == surface.EDIT_TRIGGERS
    assert view.verticalHeader().isVisible() is surface.VERTICAL_HEADER_VISIBLE
    assert view.verticalHeader().defaultSectionSize() == surface.ROW_HEIGHT
    assert view.verticalHeader().minimumSectionSize() == surface.ROW_HEIGHT
    assert view.horizontalScrollBarPolicy().name == surface.HORIZONTAL_SCROLL_POLICY
    assert view.sizePolicy().horizontalPolicy().name == surface.SIZE_POLICY
    assert view.sizePolicy().verticalPolicy().name == surface.SIZE_POLICY
    for column in range(view.columnCount()):
        assert header.sectionResizeMode(column).name == surface.RESIZE_MODE, column


def test_the_sheet_settings_are_the_shipped_sheets():
    """A sheet setting the operator relies on moved on one side."""
    from PySide6.QtCore import Qt

    view = old_list()
    canvas = old_canvas(view)
    assert canvas.testAttribute(Qt.WA_TransparentForMouseEvents) is True
    assert canvas.testAttribute(Qt.WA_TranslucentBackground) is True
    assert canvas.styleSheet() == surface.CANVAS_STYLE_SHEET
    assert surface.CANVAS_STYLE_SHEET == "background: transparent;"
    assert view.styleSheet() == surface.LIST_STYLE_SHEET == ""
    assert_pictures_match(
        old_side=render(real_sheet("one_wire"), PAINT_SIZE),
        new_side=render(
            sheet_painted_by_the_payload(sealed_sheet_payload("one_wire")), PAINT_SIZE
        ),
        note="the settings both sheets carry",
    )


# The lane allocator


ALLOCATOR_CASES = (
    (),
    (("w", 0, 0),),
    (("w", 3, 0),),
    (("a", 0, 2), ("b", 1, 3)),
    (("a", 0, 2), ("b", 3, 5)),
    (("a", 0, 2), ("b", 2, 4)),
    (("a", 0, 8), ("b", 0, 8), ("c", 0, 8)),
    tuple(("w-%d" % index, 0, 8) for index in range(9)),
    tuple(("w-%d" % index, index, index) for index in range(9)),
    (("a", -3, -1),),
    (("a", 0, 2), ("a", 3, 5)),
)


@pytest.mark.parametrize("wires", ALLOCATOR_CASES)
def test_the_lane_allocator_answers_the_shipped_ones_lanes(wires):
    """The surface puts a wire in a different lane than the shipped
    allocator."""
    old = shipped.BotSwarmLaneAllocator().assign(list(wires))
    new = surface.BotSwarmLaneAllocator().assign(list(wires))
    assert new == old, wires


def test_the_lane_allocator_shares_a_lane_only_where_the_rows_do_not_meet():
    """Two wires that cross the same rows were put in one lane, so one
    would be drawn over the other."""
    allocator = surface.BotSwarmLaneAllocator()
    assert allocator.assign([("a", 0, 2), ("b", 1, 3)]) == {"a": 0, "b": 1}
    assert allocator.assign([("a", 0, 2), ("b", 3, 5)]) == {"a": 0, "b": 0}
    assert allocator.assign([("a", 0, 2), ("b", 2, 4)]) == {"a": 0, "b": 1}
    assert allocator.assign([("a", 2, 0), ("b", 1, 3)]) == {"a": 0, "b": 1}
    assert shipped.BotSwarmLaneAllocator().assign([("a", 0, 2), ("b", 3, 5)]) == {
        "a": 0,
        "b": 0,
    }


def test_a_wire_that_fits_no_lane_is_answered_with_nothing_on_both_sides():
    """A ninth wire over the same rows took a lane it does not have."""
    wires = [("w-%d" % index, 0, 8) for index in range(9)]
    old = shipped.BotSwarmLaneAllocator().assign(wires)
    new = surface.BotSwarmLaneAllocator().assign(wires)
    assert new == old
    assert new["w-8"] is None
    assert sorted(value for value in new.values() if value is not None) == list(
        range(surface.LANE_COUNT)
    )
    assert surface.BotSwarmLaneAllocator(1).assign([("a", 0, 1), ("b", 0, 1)]) == {
        "a": 0,
        "b": None,
    }
    assert shipped.BotSwarmLaneAllocator(1).assign([("a", 0, 1), ("b", 0, 1)]) == {
        "a": 0,
        "b": None,
    }


# The sheet the wires are drawn on


def test_the_drawing_calls_are_the_shipped_sheets():
    """The sheet draws a different line, dot or colour than the shipped
    one."""
    old = old_wire_side("one_wire")["state"]
    new = new_wire_side("one_wire")["state"]
    assert new["calls"] == old["calls"]
    names = [call[0] for call in old["calls"]]
    assert names == [
        surface.BEGIN_PAINTER,
        surface.SET_RENDER_HINT,
        surface.SET_OPACITY,
        surface.SET_GRADIENT_PEN,
        surface.DRAW_LINE,
        surface.SET_PEN_STYLE,
        surface.SET_BRUSH_CALL,
        surface.DRAW_ELLIPSE,
        surface.SET_BRUSH_CALL,
        surface.DRAW_ELLIPSE,
        surface.END_PAINTER,
    ]
    lane_x = surface.lane_column_x(0, screen_column_widths())
    assert old["calls"][1] == [surface.SET_RENDER_HINT, "Antialiasing", 1]
    assert old["calls"][2] == [surface.SET_OPACITY, 1.0]
    assert old["calls"][4] == [surface.DRAW_LINE, [lane_x, 15, lane_x, 75]]
    assert old["calls"][5] == [surface.SET_PEN_STYLE, "NoPen"]


def test_the_wire_line_and_dots_carry_the_shipped_colours():
    """A wire end lost its colour or its size on one side."""
    old = old_wire_side("one_wire")["state"]["calls"]
    new = new_wire_side("one_wire")["state"]["calls"]
    assert new == old
    lane_x = float(surface.lane_column_x(0, screen_column_widths()))
    pen = old[3]
    assert pen[1] == [lane_x, 15.0]
    assert pen[2] == [lane_x, 75.0]
    assert pen[4] == surface.WIRE_PEN_WIDTH_PX == 3
    assert pen[5] == surface.WIRE_PEN_STYLE == "SolidLine"
    assert old[6] == [surface.SET_BRUSH_CALL, surface.SOURCE_DOT_COLOR, "SolidPattern"]
    assert old[7] == [
        surface.DRAW_ELLIPSE,
        [lane_x, 15.0],
        surface.LANE_DOT_RADIUS,
        surface.LANE_DOT_RADIUS,
    ]
    assert old[8] == [surface.SET_BRUSH_CALL, surface.TARGET_DOT_COLOR, "SolidPattern"]
    assert surface.SOURCE_DOT_COLOR != surface.TARGET_DOT_COLOR
    assert surface.LANE_DOT_RADIUS == 4


@pytest.mark.parametrize(
    "name",
    [
        "phase_zero",
        "phase_at_pulse_width",
        "phase_near_end",
        "phase_just_under_one",
        "phase_one",
        "phase_over_one",
        "phase_negative",
        "phase_missing",
        "phase_none",
        "phase_true",
        "phase_infinity",
        "phase_minus_infinity",
        "phase_not_a_number",
        "phase_thousand_million",
        "phase_one_billionth",
    ],
)
def test_the_pulse_sits_where_the_shipped_sheet_puts_it(name):
    """The bright pulse travels differently on one side."""
    old = old_wire_side(name)["state"]["calls"]
    new = new_wire_side(name)["state"]["calls"]
    assert numbers_as_text(new) == numbers_as_text(old), name
    assert [call[0] for call in old].count(surface.SET_GRADIENT_PEN) == 1, name


def test_a_pulse_on_the_wires_start_replaces_the_base_colour_there():
    """The pulse was drawn beside the base colour rather than over it,
    so the wire would show two colours at its start."""
    stops = surface.wire_gradient_stops(0.0)
    assert stops[0] == [0.0, surface.PULSE_COLOR]
    assert stops == [
        [0.0, surface.PULSE_COLOR],
        [0.12, surface.BASE_END_COLOR],
        [1.0, surface.BASE_END_COLOR],
    ]
    old = old_wire_side("phase_zero")["state"]["calls"][3][3]
    assert old == stops
    later = surface.wire_gradient_stops(0.25)
    assert [position for position, _ in later] == [0.0, 0.13, 0.25, 0.37, 1.0]
    assert later[2] == [0.25, surface.PULSE_COLOR]


def test_a_pulse_that_is_not_a_number_lands_before_every_other_stop():
    """A pulse with no place on the wire moved another stop, or the two
    sides put it in different places."""
    stops = surface.wire_gradient_stops(INFINITY)
    assert len(stops) == 3
    assert numbers_as_text(stops[0][0]) == numbers_as_text(NOT_A_NUMBER)
    assert stops[0][1] == surface.PULSE_COLOR
    assert stops[1] == [0.0, surface.BASE_START_COLOR]
    assert stops[2] == [1.0, surface.BASE_END_COLOR]
    old = old_wire_side("phase_infinity")["state"]["calls"][3][3]
    assert numbers_as_text(old) == numbers_as_text(stops)


def test_the_stop_placer_reports_a_stop_moved_or_replaced():
    """The stop placer puts every stop in one place, so a moved pulse
    would read as unchanged."""
    stops: list = []
    surface.insert_stop(stops, 0.0, [1, 1, 1, 1])
    surface.insert_stop(stops, 1.0, [2, 2, 2, 2])
    assert stops == [[0.0, [1, 1, 1, 1]], [1.0, [2, 2, 2, 2]]]
    surface.insert_stop(stops, 0.5, [3, 3, 3, 3])
    assert [position for position, _ in stops] == [0.0, 0.5, 1.0]
    surface.insert_stop(stops, 0.5, [4, 4, 4, 4])
    assert len(stops) == 3
    assert stops[1] == [0.5, [4, 4, 4, 4]]
    surface.insert_stop(stops, NOT_A_NUMBER, [5, 5, 5, 5])
    assert len(stops) == 4
    assert stops[0][1] == [5, 5, 5, 5]


def test_the_brightness_slider_reaches_the_paint_on_both_sides():
    """The operator's wire brightness reached the screen on one side
    only."""
    view = old_list("nine_bots")
    canvas = old_canvas(view)
    listing = new_list("nine_bots", screen_column_widths())
    model = surface.LaneWireModel(listing)
    for value, expected in ((40, 0.4), (0, 0.0), (100, 1.0), (150, 1.0), (-20, 0.0)):
        canvas.set_opacity_pct(value)
        model.set_opacity_pct(value)
        canvas.set_wires([wire()])
        model.set_wires([wire()])
        old_calls = old_paint(canvas)[0]
        model.paint()
        assert model.opacity_pct == canvas._opacity_pct, value
        assert [call for call in model.calls if call[0] == surface.SET_OPACITY] == [
            [surface.SET_OPACITY, expected]
        ], value
        assert model.calls == old_calls, value


@pytest.mark.parametrize(
    "value", [40, 0, 100, 150, -20, 55.9, True, INFINITY, -INFINITY, NOT_A_NUMBER, "x"]
)
def test_the_brightness_setter_answers_or_refuses_alike(value):
    """The two sides take a different brightness, or refuse it
    differently."""
    canvas = old_canvas(old_list())
    model = surface.LaneWireModel(new_list())
    old = guarded(lambda: canvas.set_opacity_pct(value))
    new = guarded(lambda: model.set_opacity_pct(value))
    assert new["error"] == old["error"], value
    assert new["message"] == old["message"], value
    assert model.opacity_pct == canvas._opacity_pct, value


def test_the_brightness_outcomes_hold_both_an_answer_and_a_refusal():
    """Every brightness answered, or every one refused."""
    outcomes = {}
    for value in (40, 150, -20, 55.9, INFINITY, NOT_A_NUMBER, "x", None):
        model = surface.LaneWireModel(new_list())
        outcomes[repr(value)] = guarded(lambda: model.set_opacity_pct(value))["error"]
    assert sorted(set(outcomes.values())) == [
        "",
        "OverflowError",
        "TypeError",
        "ValueError",
    ]
    assert outcomes[repr(INFINITY)] == "OverflowError"
    assert outcomes[repr(NOT_A_NUMBER)] == "ValueError"
    assert outcomes[repr(None)] == "TypeError"
    assert outcomes[repr(40)] == ""


def test_an_undrawable_wire_names_the_true_reason_on_both_sides():
    """A wire missing from the sheet blames lane capacity when the row
    set is what is stale, or the other way round."""
    unlisted = old_wire_side("unlisted_target")
    assert new_wire_side("unlisted_target") == unlisted
    assert unlisted["state"]["undrawable"] == [["w-1", surface.REASON_UNLISTED]]
    exhausted = old_wire_side("nine_wires_exhaust_the_lanes")
    assert new_wire_side("nine_wires_exhaust_the_lanes") == exhausted
    assert exhausted["state"]["undrawable"] == [["w-8", surface.REASON_NO_LANE]]
    assert exhausted["state"]["undrawable_count"] == 1
    assert surface.REASON_NO_LANE != surface.REASON_UNLISTED
    assert set(surface.UNDRAWABLE_REASONS) == {"no-lane", "unlisted-bot"}


def test_the_sheet_writes_the_shipped_log_line_when_a_wire_is_dropped():
    """The operator is told something different when the sheet shows
    fewer wires than exist."""
    old = old_wire_side("unlisted_target")["state"]["log_lines"]
    new = new_wire_side("unlisted_target")["state"]["log_lines"]
    assert new == old
    assert len(old) == 1
    assert old[0][0] == surface.WARNING_LEVEL == "WARNING"
    assert "1 wire(s) configured but not drawn" in old[0][1]
    assert "w-1 (unlisted-bot)" in old[0][1]
    assert old[0][1].endswith("The canvas is showing fewer wires than exist.")


def test_the_sheet_writes_one_log_line_per_change_not_per_frame():
    """The sheet writes a line on every frame, which would bury the log,
    or writes none when the drop clears."""
    view = old_list("nine_bots")
    canvas = old_canvas(view)
    listing = new_list("nine_bots", screen_column_widths())
    model = surface.LaneWireModel(listing)
    old_lines: list = []
    new_lines: list = []
    for wires in (
        [wire(target_id="gone")],
        [wire(target_id="gone")],
        [wire()],
        [wire()],
    ):
        canvas.set_wires(wires)
        model.set_wires(wires)
        lines = old_paint(canvas)[1]
        model.paint()
        old_lines.append(lines)
        new_lines.append([list(line) for line in model.log_lines])
    assert new_lines == old_lines
    assert [len(found) for found in old_lines] == [1, 0, 1, 0]
    assert old_lines[0][0][0] == "WARNING"
    assert old_lines[2][0][0] == surface.INFO_LEVEL == "INFO"
    assert old_lines[2][0][1] == surface.ALL_DRAWN_INFO


def test_the_log_watcher_reports_a_line_and_stays_quiet_without_one():
    """The log watcher sees nothing whatever the sheet writes, so every
    log comparison would pass empty."""
    log = logging.getLogger(surface.LOGGER_NAME)
    catcher = LineCatcher()
    log.addHandler(catcher)
    try:
        log.warning("a line the watcher must see")
        log.info("a quieter line the watcher must see")
        seen = list(catcher.lines)
    finally:
        log.removeHandler(catcher)
    assert seen == [
        ["WARNING", "a line the watcher must see"],
        ["INFO", "a quieter line the watcher must see"],
    ]
    quiet = LineCatcher()
    log.addHandler(quiet)
    try:
        old_wire_side("no_wires")
        assert quiet.lines == []
        old_wire_side("one_wire")
        assert quiet.lines == [["INFO", surface.ALL_DRAWN_INFO]]
    finally:
        log.removeHandler(quiet)
    assert log.level == logging.INFO


def test_the_sheet_with_no_wires_draws_nothing_on_both_sides():
    """The sheet opened a painter with nothing to draw."""
    old = old_wire_side("no_wires")["state"]
    new = new_wire_side("no_wires")["state"]
    assert new == old
    assert old["calls"] == []
    assert old["undrawable"] == []
    assert old["log_lines"] == []
    assert new_wire_side("no_wires")["state"]["wire_count"] == 0


def test_every_paint_branch_the_surface_names_is_reached():
    """A branch the surface names is never the one that runs."""
    reached = set()
    for name in WIRE_CASES:
        rows, wires = WIRE_CASES[name]
        listing = new_list(rows, screen_column_widths())
        model = surface.LaneWireModel(listing)
        if guarded(lambda: model.set_wires(wires))["error"]:
            continue
        guarded(model.paint)
        reached.update(model.branches)
    assert reached == set(surface.PAINT_BRANCHES)
    assert len(surface.PAINT_BRANCHES) == 3


def test_the_branch_record_matches_what_the_shipped_sheet_drew():
    """The branch record says a wire was drawn that the shipped sheet
    skipped."""
    for name in (
        "one_wire",
        "two_disjoint",
        "nine_wires_exhaust_the_lanes",
        "unlisted_source",
        "no_wires",
    ):
        old = old_wire_side(name)["state"]
        rows, wires = WIRE_CASES[name]
        listing = new_list(rows, screen_column_widths())
        model = surface.LaneWireModel(listing)
        model.set_wires(wires)
        model.paint()
        drawn = [call[0] for call in old["calls"]].count(surface.DRAW_LINE)
        assert model.branches.count(surface.PAINT_WIRE) == drawn, name
        assert model.branches.count(surface.PAINT_SKIP) == len(old["undrawable"]), name
        assert (model.branches == [surface.PAINT_NOTHING]) is (old["calls"] == []), name


def test_an_unnamed_wire_takes_the_name_built_from_its_ends():
    """An unnamed wire is known by a different name on one side, so its
    lane and its drop report would not line up."""
    old = old_wire_side("unnamed_wire")["state"]
    new = new_wire_side("unnamed_wire")["state"]
    assert new == old
    assert list(old["lane_assignments"]) == ["n-0->n-1"]
    assert surface.wire_id({"source_id": "a", "target_id": "b"}) == "a->b"
    assert surface.wire_id({"id": "w", "source_id": "a", "target_id": "b"}) == "w"
    assert surface.wire_id({"id": "", "source_id": "a", "target_id": "b"}) == "a->b"
    assert surface.wire_id({}) == "->"
    assert surface.wire_id({"id": 7}) == "7"


# The enumeration: every class, method, value and wiring


def parsed(path):
    """The parsed source of one file."""
    return ast.parse(path.read_text(encoding="utf-8"))


def dotted(node):
    """The full name a call names, or nothing when it names none."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return dotted(node.value) + "." + node.attr
    return ""


def imported_names(tree):
    """Every name a file imports, by the name it uses."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(
                (alias.asname or alias.name).split(".")[0] for alias in node.names
            )
    return found


def connect_sites(path):
    """Every signal wiring one file makes, counted as a call."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith(".connect")
    ]


def signal_sites(path):
    """Every signal one file declares, by name."""
    return sorted(
        node.targets[0].id
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and isinstance(node.value, ast.Call)
        and dotted(node.value.func).endswith("Signal")
    )


def timer_sites(path):
    """Every wait one file starts, counted as a construction."""
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path):
    """Every bus topic one file subscribes to, by name."""
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


def built_classes(path, layouts):
    """Every imported class one file constructs, counted as a call.

    `layouts` picks the arrangers, whose names end in ``Layout``; False
    picks the screen elements the operator sees. A name counts only
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


def source_classes(path):
    """Every class one file declares, a nested one included."""
    return sorted(
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    )


def module_functions(module):
    """Every function a module declares at its top level, by name."""
    import inspect

    return {
        name
        for name, value in vars(module).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == module.__name__
    }


def source_functions(path):
    """Every function one file declares, a nested one included."""
    return sorted(
        node.name
        for node in ast.walk(parsed(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def members(owner):
    """Every method, factory and read-only value a class declares.

    A signal can be called and is not a method. Neither a factory nor a
    read-only value can be called, so the counter reads the kind each
    name was declared as rather than asking whether it can be called.
    """
    import inspect

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if inspect.isfunction(value) or isinstance(
            value, (property, staticmethod, classmethod)
        ):
            found.add(name)
    return found


CLASS_MAP = {
    "BotSwarmLaneAllocator": "BotSwarmLaneAllocator",
    "BotListView": "BotListModel",
    "LaneWireCanvas": "LaneWireModel",
}

METHOD_MAP = {
    "BotSwarmLaneAllocator.__init__": "BotSwarmLaneAllocator.__init__",
    "BotSwarmLaneAllocator.assign": "BotSwarmLaneAllocator.assign",
    "BotListView.__init__": "BotListModel.__init__",
    "BotListView.set_bots": "BotListModel.set_bots",
    "BotListView.bot_ids": "BotListModel.bot_ids",
    "BotListView.row_of_bot": "BotListModel.row_of_bot",
    "BotListView.row_index_map": "BotListModel.row_index_map",
    "BotListView.lane_col_x": "BotListModel.lane_col_x",
    "BotListView.row_y_center": "BotListModel.row_y_center",
    "LaneWireCanvas.__init__": "LaneWireModel.__init__",
    "LaneWireCanvas.undrawable_wire_count": "LaneWireModel.undrawable_wire_count",
    "LaneWireCanvas.undrawable_wires": "LaneWireModel.undrawable_wires",
    "LaneWireCanvas.set_opacity_pct": "LaneWireModel.set_opacity_pct",
    "LaneWireCanvas.set_wires": "LaneWireModel.set_wires",
    "LaneWireCanvas.paintEvent": "LaneWireModel.paint",
}

ALLOCATOR_MEMBERS = {"__init__", "assign"}

LIST_MODEL_MEMBERS = {
    "__init__",
    "row_count",
    "written_cell_count",
    "_resized_rows",
    "set_bots",
    "set_column_widths",
    "bot_ids",
    "row_of_bot",
    "row_index_map",
    "lane_col_x",
    "row_y_center",
}

SHEET_MODEL_MEMBERS = {
    "__init__",
    "opacity_pct",
    "lane_assignments",
    "wire_count",
    "wire_order",
    "undrawable_wire_count",
    "undrawable_wires",
    "set_opacity_pct",
    "set_wires",
    "paint",
    "_record_change",
}

SURFACE_FUNCTIONS = {
    "amount_text",
    "pct_text",
    "pct_color",
    "cell",
    "ticker_cell",
    "amount_cell",
    "pct_cell",
    "lane_cell",
    "empty_row",
    "lane_column_x",
    "row_y",
    "wire_id",
    "insert_stop",
    "wire_gradient_stops",
    "wire_calls",
    "undrawn_detail",
    "build_payload",
    "view_model",
}

VALUE_MAP = {
    "LANE_COUNT": "LANE_COUNT",
    "LANE_COL_WIDTH": "LANE_COL_WIDTH",
    "LANE_DOT_RADIUS": "LANE_DOT_RADIUS",
    "ROW_HEIGHT": "ROW_HEIGHT",
    "TICKER_COL_WIDTH": "TICKER_COL_WIDTH",
    "FLOW_COL_WIDTH": "FLOW_COL_WIDTH",
    "OUTFLOW_PCT_COL_WIDTH": "OUTFLOW_PCT_COL_WIDTH",
    "COL_TICKER": "COL_TICKER",
    "COL_INFLOW": "COL_INFLOW",
    "COL_OUTFLOW": "COL_OUTFLOW",
    "COL_OUTFLOW_PCT": "COL_OUTFLOW_PCT",
    "COL_LANE_0": "COL_LANE_0",
    "COL_LANE_LAST": "COL_LANE_LAST",
    "TOTAL_COLS": "TOTAL_COLS",
    "COLUMN_HEADERS": "COLUMN_HEADERS",
}


def test_every_shipped_class_has_a_counterpart():
    """A class exists on one side and nowhere on the other."""
    assert source_classes(LIST_PATH) == [
        "BotListView",
        "BotSwarmLaneAllocator",
        "LaneWireCanvas",
    ]
    assert set(CLASS_MAP) == set(source_classes(LIST_PATH))
    assert len(CLASS_MAP) == 3
    for target in CLASS_MAP.values():
        assert isinstance(getattr(surface, target), type), target
    assert source_classes(SURFACE_PATH) == [
        "BotListModel",
        "BotSwarmLaneAllocator",
        "BotSwarmListModel",
        "LaneWireModel",
    ]


def test_every_function_the_surface_declares_is_named():
    """The surface grew or lost a top-level function nobody named."""
    assert module_functions(surface) == SURFACE_FUNCTIONS
    assert len(SURFACE_FUNCTIONS) == 18
    assert module_functions(shipped) == set()
    assert "view_model" in SURFACE_FUNCTIONS
    assert "build_payload" in SURFACE_FUNCTIONS
    assert module_functions(surface) - {"row_y"} != SURFACE_FUNCTIONS
    assert "BotListModel" not in module_functions(surface)


def test_the_step_sequences_that_refuse_are_the_same_on_both_sides():
    """A sequence refuses on one side and answers on the other, or
    the named set of refusing sequences is not the set that runs."""
    refused = set()
    for name in STEP_CASES:
        old = old_steps(name)["runs"]
        new = new_steps(name)["runs"]
        assert [step["error"] for step in new] == [step["error"] for step in old], name
        if any(step["error"] for step in old):
            refused.add(name)
    assert refused == REFUSED_STEP_CASES, sorted(refused ^ REFUSED_STEP_CASES)
    assert refused
    assert set(STEP_CASES) - refused


def test_the_class_counter_finds_a_class_declared_inside_another():
    """A class declared inside another reads as no class, so a file
    could lose one without the count moving."""
    found = source_classes(NESTED_CLASS_NEIGHBOUR)
    assert "StockMainWindow" in found
    assert "_StockLogHandler" in found
    assert found.index("_StockLogHandler") != found.index("StockMainWindow")
    assert "_StockLogHandler" not in [
        node.name
        for node in parsed(NESTED_CLASS_NEIGHBOUR).body
        if isinstance(node, ast.ClassDef)
    ]


def test_every_shipped_method_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    assert members(shipped.BotSwarmLaneAllocator) == ALLOCATOR_MEMBERS
    assert members(shipped.BotListView) == {
        "__init__",
        "set_bots",
        "bot_ids",
        "row_of_bot",
        "row_index_map",
        "lane_col_x",
        "row_y_center",
    }
    assert members(shipped.LaneWireCanvas) == {
        "__init__",
        "undrawable_wire_count",
        "undrawable_wires",
        "set_opacity_pct",
        "set_wires",
        "paintEvent",
    }
    declared = (
        members(shipped.BotSwarmLaneAllocator)
        | members(shipped.BotListView)
        | members(shipped.LaneWireCanvas)
    )
    assert len(source_functions(LIST_PATH)) == 15
    assert {name.split(".")[-1] for name in METHOD_MAP} == declared
    assert len(METHOD_MAP) == 15
    assert members(surface.BotSwarmLaneAllocator) == ALLOCATOR_MEMBERS
    assert members(surface.BotListModel) == LIST_MODEL_MEMBERS
    assert members(surface.LaneWireModel) == SHEET_MODEL_MEMBERS
    for target in METHOD_MAP.values():
        holder, name = target.split(".")
        assert name in members(getattr(surface, holder)), target


def test_the_method_counter_leaves_a_signal_out_and_finds_the_two_it_would_miss():
    """A signal counts as a method, or a factory and a read-only value
    do not, so a class that traded one for another reads as unchanged."""
    from PySide6.QtCore import QObject, Signal

    from src.gui.launcher import ModeCard

    app()

    class Declares(QObject):
        """One of each kind, so the counter has all four to sort."""

        fired = Signal(bool)

        def a_method(self):
            """A plain method."""
            return True

        @property
        def a_read_only_value(self):
            """A value read without a call."""
            return 1

        @staticmethod
        def a_maker():
            """A maker that takes no owner."""
            return 2

        @classmethod
        def a_factory(cls):
            """A factory that takes the class."""
            return cls

    assert callable(vars(Declares)["fired"])
    assert callable(vars(Declares)["a_read_only_value"]) is False
    assert callable(vars(Declares)["a_factory"]) is False
    assert members(Declares) == {
        "a_method",
        "a_read_only_value",
        "a_maker",
        "a_factory",
    }
    assert "fired" not in members(Declares)
    assert isinstance(vars(ModeCard)["clicked"], Signal)
    assert "clicked" not in members(ModeCard)
    assert "mousePressEvent" in members(ModeCard)


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the screen passes it."""
    import inspect

    for old_name, new_name in METHOD_MAP.items():
        old_holder, old_method = old_name.split(".")
        new_holder, new_method = new_name.split(".")
        old = list(
            inspect.signature(
                getattr(getattr(shipped, old_holder), old_method)
            ).parameters
        )
        new = list(
            inspect.signature(
                getattr(getattr(surface, new_holder), new_method)
            ).parameters
        )
        if old_name == "LaneWireCanvas.paintEvent":
            assert old == ["self", "event"], old
            assert new == ["self"], new
            continue
        if old_name == "BotListView.__init__":
            assert old == ["self", "parent"], old
            assert new == ["self"], new
            continue
        if old_name == "LaneWireCanvas.__init__":
            assert old == ["self", "bot_list", "parent"], old
            assert new == ["self", "bot_list"], new
            continue
        assert new == old, old_name


def test_the_shipped_paint_never_reads_the_event_it_is_handed():
    """The shipped paint reads its event, so the surface dropping it
    loses something."""
    view = old_list("nine_bots")
    canvas = old_canvas(view)
    canvas.set_wires([wire()])
    with_none = old_paint(canvas)[0]
    canvas.set_wires([wire()])

    class Refuses:
        """An event that fails loudly if the sheet touches it."""

        def __getattr__(self, name):
            """Any read is a defect, so it raises rather than answers."""
            raise AssertionError("the shipped paint read event.%s" % name)

    calls, _, outcome = old_paint(canvas, Refuses())
    assert outcome["error"] == "", outcome["message"]
    assert calls == with_none
    assert calls


def test_every_shipped_value_has_a_counterpart():
    """A value the shipped list carries reaches nothing on the surface."""
    assert len(VALUE_MAP) == 15
    for old_name, new_name in VALUE_MAP.items():
        assert getattr(surface, new_name) == getattr(shipped, old_name), old_name
    assert surface.TOTAL_COLS == shipped.TOTAL_COLS == 12
    assert list(surface.COLUMN_HEADERS) == list(shipped.COLUMN_HEADERS)


def test_the_wiring_count_matches_the_actions_and_the_counter_reports():
    """A signal wiring appeared on one side and not the other."""
    assert connect_sites(LIST_PATH) == []
    assert len(connect_sites(LIST_PATH)) == LIST_CONNECT_SITES == 0
    assert connect_sites(SURFACE_PATH) == []
    assert len(surface.ACTIONS) == len(connect_sites(LIST_PATH))
    neighbour = connect_sites(WIRING_NEIGHBOUR)
    assert len(neighbour) == WIRING_NEIGHBOUR_SITES == 1, neighbour
    assert neighbour == ["self.clicked.connect"]


def test_the_signal_count_matches_and_the_counter_reports():
    """A signal appeared on one side and not the other."""
    assert signal_sites(LIST_PATH) == []
    assert len(signal_sites(LIST_PATH)) == LIST_SIGNAL_SITES == 0
    assert signal_sites(SURFACE_PATH) == []
    neighbour = signal_sites(SIGNAL_NEIGHBOUR)
    assert len(neighbour) == SIGNAL_NEIGHBOUR_SITES == 3, neighbour
    assert "clicked" in neighbour


def test_the_timer_count_matches_and_the_counter_reports():
    """A wait appeared on one side and not the other."""
    assert timer_sites(LIST_PATH) == []
    assert len(timer_sites(LIST_PATH)) == LIST_TIMER_SITES == 0
    assert timer_sites(SURFACE_PATH) == []
    neighbour = timer_sites(TIMER_NEIGHBOUR)
    assert len(neighbour) == TIMER_NEIGHBOUR_SITES == 1, neighbour
    assert timer_sites(TIMER_WRONG_NEIGHBOUR) == []
    assert TIMER_NEIGHBOUR != TIMER_WRONG_NEIGHBOUR
    assert TIMER_NEIGHBOUR.name == TIMER_WRONG_NEIGHBOUR.name
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    named = LIST_PATH.read_text(encoding="utf-8").count("QTimer")
    assert named == 0


def test_no_wait_starts_while_either_side_is_driven():
    """A wait started under the drive that the source count cannot see."""
    from PySide6.QtCore import QObject, QTimer

    app()
    started: list = []
    original_start_timer = QObject.startTimer
    original_timer_start = QTimer.start
    original_single_shot = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        """Keep the wait, then start it."""
        started.append(("startTimer", args))
        return original_start_timer(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        """Keep the wait, then start it."""
        started.append(("QTimer.start", args))
        return original_timer_start(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        """Keep the one-off wait, then start it."""
        started.append(("singleShot", args))
        return original_single_shot(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        for name in ("happy", "four_bots"):
            old_side(name)
            new_side(name)
        old_wire_side("one_wire")
        new_wire_side("one_wire")
        observed = list(started)
        started.clear()
        QTimer().start(250)
    finally:
        QObject.startTimer = original_start_timer
        QTimer.start = original_timer_start
        QTimer.singleShot = original_single_shot
    assert started == [("QTimer.start", (250,))]
    assert observed == []


def test_the_bus_count_matches_and_the_counter_reports():
    """A bus wiring appeared on one side and not the other."""
    assert bus_sites(LIST_PATH) == []
    assert len(bus_sites(LIST_PATH)) == LIST_BUS_SITES == 0
    assert bus_sites(SURFACE_PATH) == []
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) == BUS_NEIGHBOUR_SITES == 2, neighbour
    assert neighbour == ["wire.created", "wire.removed"]
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == len(bus_sites(LIST_PATH))


def test_the_screen_element_count_matches_and_the_counter_reports():
    """A screen element the shipped list builds reaches nothing on the
    surface."""
    built = built_classes(LIST_PATH, layouts=False)
    assert len(built) == LIST_ELEMENT_BUILDS == 32, built
    assert set(built) == {
        "QBrush",
        "QColor",
        "QLinearGradient",
        "QPainter",
        "QPen",
        "QPointF",
        "QTableWidgetItem",
    }
    assert built.count("QTableWidgetItem") == 5
    assert built_classes(LIST_PATH, layouts=True) == []
    assert len(built_classes(LIST_PATH, layouts=True)) == LIST_LAYOUT_BUILDS
    assert built_classes(SURFACE_PATH, layouts=False) == []
    neighbour = built_classes(ELEMENT_NEIGHBOUR, layouts=False)
    assert len(neighbour) == ELEMENT_NEIGHBOUR_BUILDS == 3, neighbour
    assert neighbour == ["PrivacyDot", "QLabel", "QLabel"]
    named = LIST_PATH.read_text(encoding="utf-8").count("QTableWidgetItem")
    assert named > built.count("QTableWidgetItem"), named


def test_the_neighbouring_controls_are_six_different_files():
    """Two controls read one file, so one of the two was never
    measured."""
    named = [
        WIRING_NEIGHBOUR,
        SIGNAL_NEIGHBOUR,
        TIMER_NEIGHBOUR,
        BUS_NEIGHBOUR,
        ELEMENT_NEIGHBOUR,
        NESTED_CLASS_NEIGHBOUR,
    ]
    assert len(set(named)) == len(named) == 6, named
    for path in named:
        assert path.is_file(), path
        assert path != LIST_PATH
        assert path != SURFACE_PATH


# Every value the surface exports reaches the compared snapshot


def freeze(value):
    """One value as a single comparable string."""
    return json.dumps(numbers_as_text(value), sort_keys=True, default=str)


def surface_constants():
    """Every value the surface exports, by name."""
    import inspect

    found = {}
    for name, value in vars(surface).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) or inspect.isclass(value):
            continue
        if inspect.ismodule(value):
            continue
        if isinstance(value, surface.BotSwarmListModel):
            continue
        if getattr(value, "__module__", "") in ("typing", "__future__"):
            continue
        found[name] = value
    return found


def payload_values(payloads):
    """Every value any of these payloads carries, frozen for comparison."""
    found = set()

    def walk(value):
        found.add(freeze(value))
        if isinstance(value, dict):
            for key, item in value.items():
                found.add(freeze(key))
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for payload in payloads:
        walk(payload)
    return found


def compared_payloads():
    """The payloads the completeness check reads, one per driven path."""
    payloads = []
    for name in ("happy", "empty", "all_pct_bands", "nine_bots", "missing_keys"):
        model = surface.BotSwarmListModel()
        model.bot_list.set_bots(CASES[name])
        payloads.append(surface.build_payload(model))
    for name in (
        "one_wire",
        "no_wires",
        "unlisted_target",
        "nine_wires_exhaust_the_lanes",
        "unnamed_wire",
        "two_disjoint",
    ):
        rows, wires = WIRE_CASES[name]
        model = surface.BotSwarmListModel()
        model.bot_list.set_column_widths(screen_column_widths())
        model.bot_list.set_bots(CASES[rows])
        model.lane_canvas.set_wires(wires)
        model.lane_canvas.paint()
        payloads.append(surface.build_payload(model))
    recovered = surface.BotSwarmListModel()
    recovered.bot_list.set_bots(CASES["nine_bots"])
    recovered.lane_canvas.set_wires(WIRE_CASES["unlisted_target"][1])
    recovered.lane_canvas.paint()
    recovered.lane_canvas.set_wires(WIRE_CASES["one_wire"][1])
    recovered.lane_canvas.paint()
    payloads.append(surface.build_payload(recovered))
    dimmed = surface.BotSwarmListModel()
    dimmed.bot_list.set_bots(CASES["nine_bots"])
    dimmed.lane_canvas.set_opacity_pct(surface.OPACITY_MIN_PCT)
    dimmed.lane_canvas.set_wires(WIRE_CASES["one_wire"][1])
    dimmed.lane_canvas.paint()
    payloads.append(surface.build_payload(dimmed))
    refused = surface.BotSwarmListModel()
    guarded(lambda: refused.bot_list.set_bots(CASES["text_where_pct_belongs"]))
    payloads.append(surface.build_payload(refused))
    return payloads


COVERED_ELSEWHERE = {
    "OPACITY_MAX_PCT": "test_the_brightness_setter_answers_or_refuses_alike",
    "PHASE_PERIOD": "test_the_pulse_sits_where_the_shipped_sheet_puts_it",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped
    list."""
    constants = surface_constants()
    assert len(constants) > 70, len(constants)
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops
    exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    slipped = missing_from_payload(surface_constants(), thinned)
    assert "COLUMN_HEADERS" in slipped
    assert "BASE_START_COLOR" in slipped
    assert "UNDRAWN_WARNING" in slipped
    assert "METHOD" not in slipped


def test_the_compared_payload_list_is_built_before_it_is_read():
    """The completeness check reads a list of payloads it never built,
    so an empty list would pass."""
    payloads = compared_payloads()
    assert len(payloads) == 14
    assert all(isinstance(found, dict) for found in payloads)
    assert {found["method"] for found in payloads} == {surface.METHOD}
    assert max(found["row_count"] for found in payloads) == 9
    assert min(found["row_count"] for found in payloads) == 0
    assert any(found["undrawable"] for found in payloads)
    assert any(found["calls"] for found in payloads)
    assert any(found["log_lines"] for found in payloads)
    assert len(payload_values(payloads)) > len(payload_values(payloads[:1]))


PAYLOAD_KEY_SOURCES = {
    "method": "surface.METHOD",
    "logger_name": "surface.LOGGER_NAME",
    "list_accessible_name": "surface.LIST_ACCESSIBLE_NAME",
    "canvas_accessible_name": "surface.CANVAS_ACCESSIBLE_NAME",
    "list_kind": "surface.LIST_KIND",
    "list_base_kind": "surface.LIST_BASE_KIND",
    "canvas_kind": "surface.CANVAS_KIND",
    "canvas_base_kind": "surface.CANVAS_BASE_KIND",
    "cell_kind": "surface.CELL_KIND",
    "list_style_sheet": "surface.LIST_STYLE_SHEET",
    "canvas_style_sheet": "surface.CANVAS_STYLE_SHEET",
    "skin": "surface.SKIN",
    "lane_count": "surface.LANE_COUNT",
    "lane_col_width": "surface.LANE_COL_WIDTH",
    "lane_dot_radius": "surface.LANE_DOT_RADIUS",
    "row_height": "surface.ROW_HEIGHT",
    "ticker_col_width": "surface.TICKER_COL_WIDTH",
    "flow_col_width": "surface.FLOW_COL_WIDTH",
    "outflow_pct_col_width": "surface.OUTFLOW_PCT_COL_WIDTH",
    "col_ticker": "surface.COL_TICKER",
    "col_inflow": "surface.COL_INFLOW",
    "col_outflow": "surface.COL_OUTFLOW",
    "col_outflow_pct": "surface.COL_OUTFLOW_PCT",
    "col_lane_0": "surface.COL_LANE_0",
    "col_lane_last": "surface.COL_LANE_LAST",
    "total_cols": "surface.TOTAL_COLS",
    "lane_header_format": "surface.LANE_HEADER_FORMAT",
    "column_headers": "surface.COLUMN_HEADERS",
    "column_widths": "surface.COLUMN_WIDTHS",
    "lane_columns": "surface.LANE_COLUMNS",
    "readout_columns": "surface.READOUT_COLUMNS",
    "coloured_columns": "surface.COLOURED_COLUMNS",
    "resize_mode": "surface.RESIZE_MODE",
    "selection_behavior": "surface.SELECTION_BEHAVIOR",
    "edit_triggers": "surface.EDIT_TRIGGERS",
    "horizontal_scroll_policy": "surface.HORIZONTAL_SCROLL_POLICY",
    "size_policy": "surface.SIZE_POLICY",
    "alternating_row_colors": "surface.ALTERNATING_ROW_COLORS",
    "vertical_header_visible": "surface.VERTICAL_HEADER_VISIBLE",
    "text_elide_mode": "surface.TEXT_ELIDE_MODE",
    "focus_policy": "surface.FOCUS_POLICY",
    "focus_policy_value": "surface.FOCUS_POLICY_VALUE",
    "word_wrap": "surface.WORD_WRAP",
    "show_grid": "surface.SHOW_GRID",
    "cell_text_selectable": "surface.CELL_TEXT_SELECTABLE",
    "canvas_transparent_for_mouse": "surface.CANVAS_TRANSPARENT_FOR_MOUSE",
    "centred_alignment": "surface.CENTRED_ALIGNMENT",
    "centred_alignment_value": "surface.CENTRED_ALIGNMENT_VALUE",
    "lane_alignment_value": "surface.LANE_ALIGNMENT_VALUE",
    "bot_id_role": "surface.BOT_ID_ROLE",
    "bot_id_role_value": "surface.BOT_ID_ROLE_VALUE",
    "success_color": "surface.SUCCESS_COLOR",
    "error_color": "surface.ERROR_COLOR",
    "warning_color": "surface.WARNING_COLOR",
    "primary_bright_color": "surface.PRIMARY_BRIGHT_COLOR",
    "text_muted_color": "surface.TEXT_MUTED_COLOR",
    "unset_color": "surface.UNSET_COLOR",
    "unset_brush": "surface.UNSET_BRUSH",
    "set_brush": "surface.SET_BRUSH",
    "inflow_color": "surface.INFLOW_COLOR",
    "outflow_color": "surface.OUTFLOW_COLOR",
    "pct_no_export_color": "surface.PCT_NO_EXPORT_COLOR",
    "pct_headroom_color": "surface.PCT_HEADROOM_COLOR",
    "pct_near_cap_color": "surface.PCT_NEAR_CAP_COLOR",
    "pct_committed_color": "surface.PCT_COMMITTED_COLOR",
    "pct_headroom_limit": "surface.PCT_HEADROOM_LIMIT",
    "pct_near_cap_limit": "surface.PCT_NEAR_CAP_LIMIT",
    "amount_text_format": "surface.AMOUNT_TEXT_FORMAT",
    "pct_text_format": "surface.PCT_TEXT_FORMAT",
    "lane_cell_text": "surface.LANE_CELL_TEXT",
    "missing_text": "surface.MISSING_TEXT",
    "missing_amount": "surface.MISSING_AMOUNT",
    "no_row": "surface.NO_ROW",
    "no_coordinate": "surface.NO_COORDINATE",
    "row_keys": "surface.ROW_KEYS",
    "wire_keys": "surface.WIRE_KEYS",
    "wire_id_format": "surface.WIRE_ID_FORMAT",
    "opacity_min_pct": "surface.OPACITY_MIN_PCT",
    "opacity_max_pct": "surface.OPACITY_MAX_PCT",
    "opacity_full_pct": "surface.OPACITY_FULL_PCT",
    "opacity_scale": "surface.OPACITY_SCALE",
    "alpha_scale": "surface.ALPHA_SCALE",
    "alpha_unit": "surface.ALPHA_UNIT",
    "base_start_color": "surface.BASE_START_COLOR",
    "base_end_color": "surface.BASE_END_COLOR",
    "pulse_color": "surface.PULSE_COLOR",
    "source_dot_color": "surface.SOURCE_DOT_COLOR",
    "target_dot_color": "surface.TARGET_DOT_COLOR",
    "pulse_half_width": "surface.PULSE_HALF_WIDTH",
    "phase_period": "surface.PHASE_PERIOD",
    "gradient_start_stop": "surface.GRADIENT_START_STOP",
    "gradient_end_stop": "surface.GRADIENT_END_STOP",
    "wire_pen_width_px": "surface.WIRE_PEN_WIDTH_PX",
    "wire_pen_style": "surface.WIRE_PEN_STYLE",
    "no_pen_style": "surface.NO_PEN_STYLE",
    "render_hint": "surface.RENDER_HINT",
    "render_hint_value": "surface.RENDER_HINT_VALUE",
    "begin_painter": "surface.BEGIN_PAINTER",
    "set_render_hint": "surface.SET_RENDER_HINT",
    "set_opacity": "surface.SET_OPACITY",
    "set_gradient_pen": "surface.SET_GRADIENT_PEN",
    "set_pen_style": "surface.SET_PEN_STYLE",
    "set_brush_call": "surface.SET_BRUSH_CALL",
    "draw_line": "surface.DRAW_LINE",
    "draw_ellipse": "surface.DRAW_ELLIPSE",
    "end_painter": "surface.END_PAINTER",
    "reason_no_lane": "surface.REASON_NO_LANE",
    "reason_unlisted": "surface.REASON_UNLISTED",
    "undrawable_reasons": "surface.UNDRAWABLE_REASONS",
    "paint_nothing": "surface.PAINT_NOTHING",
    "paint_wire": "surface.PAINT_WIRE",
    "paint_skip": "surface.PAINT_SKIP",
    "paint_branches": "surface.PAINT_BRANCHES",
    "warning_level": "surface.WARNING_LEVEL",
    "info_level": "surface.INFO_LEVEL",
    "undrawn_warning": "surface.UNDRAWN_WARNING",
    "all_drawn_info": "surface.ALL_DRAWN_INFO",
    "undrawn_detail_format": "surface.UNDRAWN_DETAIL_FORMAT",
    "undrawn_detail_join": "surface.UNDRAWN_DETAIL_JOIN",
    "actions": "surface.ACTIONS",
    "bridge_actions": "surface.BRIDGE_ACTIONS",
    "timers": "surface.TIMERS",
    "timer_delays_ms": "surface.TIMER_DELAYS_MS",
    "bus_topics": "surface.BUS_TOPICS",
    "rows": "model.bot_list.rows",
    "row_count": "model.bot_list.row_count",
    "written_cell_count": "model.bot_list.written_cell_count",
    "bot_ids": "model.bot_list.bot_ids",
    "row_index_map": "model.bot_list.row_index_map",
    "column_widths_in_use": "model.bot_list.column_widths",
    "lane_column_x": "computed.lane_column_x",
    "row_y_centers": "computed.row_y_centers",
    "wire_count": "model.lane_canvas.wire_count",
    "wire_order": "model.lane_canvas.wire_order",
    "lane_assignments": "model.lane_canvas.lane_assignments",
    "opacity_pct": "model.lane_canvas.opacity_pct",
    "undrawable": "model.lane_canvas.undrawable_wires",
    "undrawable_wire_count": "model.lane_canvas.undrawable_wire_count",
    "calls": "model.lane_canvas.calls",
    "branches": "model.lane_canvas.branches",
    "log_lines": "model.lane_canvas.log_lines",
}

COMPUTED_SOURCES = {
    "lane_column_x": lambda model: [
        model.bot_list.lane_col_x(lane) for lane in range(surface.LANE_COUNT)
    ],
    "row_y_centers": lambda model: [
        model.bot_list.row_y_center(row) for row in range(model.bot_list.row_count)
    ],
}


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("computed."):
        return COMPUTED_SOURCES[name.split(".", 1)[1]](model)
    if name.startswith("surface."):
        return getattr(surface, name.split(".", 1)[1])
    found = model
    for part in name.split(".")[1:]:
        found = getattr(found, part)
    return found() if callable(found) else found


def backed(key, value, source, model):
    """Whether one payload key carries exactly what its named source
    holds."""
    return freeze(value) == freeze(resolve_source(source, model))


def driven_payload_model():
    """One model driven down every path the payload reports."""
    model = surface.BotSwarmListModel()
    model.bot_list.set_column_widths(screen_column_widths())
    model.bot_list.set_bots(CASES["nine_bots"])
    model.lane_canvas.set_opacity_pct(60)
    model.lane_canvas.set_wires(WIRE_CASES["nine_wires_exhaust_the_lanes"][1])
    model.lane_canvas.paint()
    return model


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model = driven_payload_model()
    payload = surface.build_payload(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES)
    assert len(payload) == len(PAYLOAD_KEY_SOURCES)
    assert len(payload) > 120, len(payload)
    for key, source in PAYLOAD_KEY_SOURCES.items():
        assert backed(key, payload[key], source, model), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = driven_payload_model()
    payload = surface.build_payload(model)
    assert backed(
        "column_headers", payload["column_headers"], "surface.COLUMN_HEADERS", model
    )
    assert not backed("column_headers", ["one"], "surface.COLUMN_HEADERS", model)
    assert not backed("skin", {"a": "b"}, "surface.SKIN", model)
    assert not backed("row_count", 99, "model.bot_list.row_count", model)
    assert not backed("bot_ids", ["nobody"], "model.bot_list.bot_ids", model)
    assert not backed("opacity_pct", 1, "model.lane_canvas.opacity_pct", model)
    assert not backed("lane_column_x", [0] * 8, "computed.lane_column_x", model)
    assert not backed("undrawable", [], "model.lane_canvas.undrawable_wires", model)


def test_the_payload_rows_are_read_back_as_copies():
    """Changing a payload row changes the row the model holds."""
    model = driven_payload_model()
    payload = surface.build_payload(model)
    payload["rows"][0][0]["text"] = "changed"
    payload["bot_ids"].append("changed")
    payload["calls"].append(["changed"])
    assert surface.build_payload(model)["rows"][0][0]["text"] == "N0"
    assert surface.build_payload(model)["bot_ids"][-1] == "n-8"
    assert len(surface.build_payload(model)["calls"]) == len(model.lane_canvas.calls)


def test_the_read_back_lists_are_copies_on_both_models():
    """Changing the answer changes the state the model holds."""
    model = new_list("three_bots")
    copy = model.bot_ids()
    copy.append("changed")
    assert model.bot_ids() == ["bot-a", "bot-b", "bot-c"]
    sheet = surface.LaneWireModel(model)
    sheet.set_wires([wire(source_id="bot-a", target_id="bot-b")])
    lanes = sheet.lane_assignments
    lanes["changed"] = 7
    assert "changed" not in sheet.lane_assignments
    dropped = sheet.undrawable_wires()
    dropped.append(("changed", "no-lane"))
    assert sheet.undrawable_wires() == []


# The colours, read one way on both sides


def test_a_colour_written_short_is_reported_long_by_the_canonical_form():
    """A three-digit colour compares as a different colour than the
    screen paints."""
    from PySide6.QtGui import QColor

    app()
    assert QColor(SHORT_HEX_SAMPLE).name() == SHORT_HEX_LONG_FORM
    assert SHORT_HEX_SAMPLE != SHORT_HEX_LONG_FORM
    assert long_hex(SHORT_HEX_SAMPLE) == SHORT_HEX_LONG_FORM
    assert long_hex(SHORT_HEX_LONG_FORM) == SHORT_HEX_LONG_FORM
    assert long_hex(INFLOW_GREEN) == INFLOW_GREEN
    assert long_hex("") == ""
    assert long_hex(None) is None
    for colour in (
        surface.SUCCESS_COLOR,
        surface.ERROR_COLOR,
        surface.WARNING_COLOR,
        surface.PRIMARY_BRIGHT_COLOR,
        surface.TEXT_MUTED_COLOR,
        surface.UNSET_COLOR,
    ):
        assert long_hex(colour) == colour, colour
        assert QColor(colour).name() == colour, colour


def test_the_grey_and_the_black_carry_equal_channels_and_compare_as_text():
    """A colour with three equal channels shows no channel swap, so a
    picture cannot carry the claim and the text must."""
    from PySide6.QtGui import QColor

    app()
    for flat in (surface.TEXT_MUTED_COLOR, surface.UNSET_COLOR):
        found = QColor(flat)
        assert found.red() == found.green() == found.blue(), flat
    lively = QColor(surface.SUCCESS_COLOR)
    assert len({lively.red(), lively.green(), lively.blue()}) > 1
    assert surface.TEXT_MUTED_COLOR == NO_EXPORT_GREY == "#666666"
    assert surface.UNSET_COLOR == UNSET_BLACK == "#000000"
    assert surface.TEXT_MUTED_COLOR != surface.UNSET_COLOR


def test_the_hiding_rule_keeps_a_seeded_colour_and_hides_an_unseeded_one():
    """The rule that hides a colour the platform chose hides one the
    product set, or keeps one the platform invented."""
    assert painted_colour(INFLOW_GREEN, surface.SET_BRUSH) == INFLOW_GREEN
    assert painted_colour("#123456", surface.UNSET_BRUSH) == surface.UNSET_COLOR
    assert painted_colour(SHORT_HEX_SAMPLE, surface.SET_BRUSH) == SHORT_HEX_LONG_FORM
    assert painted_colour(UNSET_BLACK, surface.UNSET_BRUSH) == surface.UNSET_COLOR
    assert painted_colour("#123456", surface.SET_BRUSH) != surface.UNSET_COLOR


def painted_pixels(image):
    """Every colour a render actually put on the screen, as #rrggbb."""
    data = bytes(image.constBits())
    return {
        "#%02x%02x%02x" % (data[index + 2], data[index + 1], data[index])
        for index in range(0, len(data), 4)
    }


def test_every_colour_the_surface_paints_is_the_colour_the_screen_shows():
    """A colour the surface names reaches no pixel, so the value read
    back off a cell says one thing and the screen shows another."""
    view = old_list("all_pct_bands")
    told = {
        view.item(row, surface.COL_OUTFLOW_PCT).foreground().color().name()
        for row in range(view.rowCount())
    }
    bands = {
        surface.PCT_NO_EXPORT_COLOR,
        surface.PCT_HEADROOM_COLOR,
        surface.PCT_NEAR_CAP_COLOR,
        surface.PCT_COMMITTED_COLOR,
    }
    assert told == bands
    shown = painted_pixels(render(view))
    assert bands <= shown, sorted(bands - shown)
    assert surface.INFLOW_COLOR in shown
    assert surface.OUTFLOW_COLOR in shown
    assert "#123456" not in shown
    assert view.item(0, surface.COL_INFLOW).foreground().color().name() == (
        surface.INFLOW_COLOR
    )


# The windows the two sides paint


def sealed_list_payload(name):
    """One case's payload, stamped as it comes off the surface."""
    model = surface.BotSwarmListModel()
    model.bot_list.set_bots(CASES[name])
    return sealed(surface.build_payload(model))


def sealed_sheet_payload(name):
    """One wire case's payload, stamped as it comes off the surface."""
    rows, wires = WIRE_CASES[name]
    model = surface.BotSwarmListModel()
    model.bot_list.set_column_widths(screen_column_widths())
    model.bot_list.set_bots(CASES[rows])
    model.lane_canvas.set_wires(wires)
    model.lane_canvas.paint()
    return sealed(surface.build_payload(model))


def list_painted_by_the_payload(payload):
    """A table built only from the surface's payload, ready to render."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QBrush, QColor
    from PySide6.QtWidgets import (
        QAbstractItemView,
        QHeaderView,
        QSizePolicy,
        QTableWidget,
        QTableWidgetItem,
    )

    payload = unaltered(payload)
    app()
    table = QTableWidget()
    HELD.append(table)
    table.setAlternatingRowColors(payload["alternating_row_colors"])
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(payload["vertical_header_visible"])
    table.verticalHeader().setDefaultSectionSize(payload["row_height"])
    table.verticalHeader().setMinimumSectionSize(payload["row_height"])
    table.setColumnCount(payload["total_cols"])
    table.setHorizontalHeaderLabels(payload["column_headers"])
    header = table.horizontalHeader()
    for column, width in enumerate(payload["column_widths"]):
        header.setSectionResizeMode(column, QHeaderView.Fixed)
        table.setColumnWidth(column, width)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    table.setStyleSheet(payload["list_style_sheet"])
    table.setRowCount(payload["row_count"])
    for row, cells in enumerate(payload["rows"]):
        for column, built in enumerate(cells):
            if built is None:
                continue
            item = QTableWidgetItem(built["text"])
            item.setTextAlignment(Qt.AlignmentFlag(built["alignment"]))
            if built["bot_id"] is not None:
                item.setData(Qt.UserRole, built["bot_id"])
            if built["brush"] == payload["set_brush"]:
                item.setForeground(QBrush(QColor(built["color"])))
            table.setItem(row, column, item)
    return table


def sheet_painted_by_the_payload(payload):
    """A sheet that paints only the calls the surface's payload names."""
    from PySide6.QtCore import Qt, QPointF
    from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
    from PySide6.QtWidgets import QWidget

    payload = unaltered(payload)
    app()
    calls = payload["calls"]

    class ReplaySheet(QWidget):
        """Replays the drawing calls the surface handed over."""

        def __init__(self):
            super().__init__()
            self.setAccessibleName(payload["canvas_accessible_name"])

        def paintEvent(self, event):
            """Run the calls in order. Nothing to draw paints nothing."""
            del event
            painter = None
            for call in calls:
                name = call[0]
                if name == payload["begin_painter"]:
                    painter = QPainter(self)
                elif name == payload["set_render_hint"]:
                    painter.setRenderHint(getattr(QPainter.RenderHint, call[1]))
                elif name == payload["set_opacity"]:
                    painter.setOpacity(call[1])
                elif name == payload["set_gradient_pen"]:
                    gradient = QLinearGradient(
                        call[1][0], call[1][1], call[2][0], call[2][1]
                    )
                    for position, colour in call[3]:
                        gradient.setColorAt(position, QColor(*colour))
                    painter.setPen(
                        QPen(
                            QBrush(gradient),
                            call[4],
                            getattr(Qt.PenStyle, call[5]),
                        )
                    )
                elif name == payload["set_pen_style"]:
                    painter.setPen(getattr(Qt.PenStyle, call[1]))
                elif name == payload["set_brush_call"]:
                    painter.setBrush(
                        QBrush(QColor(*call[1]), getattr(Qt.BrushStyle, call[2]))
                    )
                elif name == payload["draw_line"]:
                    painter.drawLine(*call[1])
                elif name == payload["draw_ellipse"]:
                    painter.drawEllipse(
                        QPointF(call[1][0], call[1][1]), call[2], call[3]
                    )
                elif name == payload["end_painter"]:
                    painter.end()

    sheet = ReplaySheet()
    HELD.append(sheet)
    sheet.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    sheet.setAttribute(Qt.WA_TranslucentBackground)
    sheet.setStyleSheet(payload["canvas_style_sheet"])
    return sheet


def real_list(name):
    """The shipped list driven over one case, ready to render."""
    return old_list(name)


def real_sheet(name):
    """The shipped sheet driven over one wire case, ready to render."""
    rows, wires = WIRE_CASES[name]
    view = old_list(rows)
    canvas = old_canvas(view)
    canvas.set_wires(wires)
    return canvas


def render(widget, size=LIST_SIZE):
    """One offscreen render of a widget at one size."""
    from tests.qt_pixel import render_widget

    app()
    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def picture_digest(image):
    """One render as a single hash, so a whole window compares in one
    line."""
    return hashlib.sha256(bytes(image.constBits())).hexdigest()


@pytest.mark.parametrize("name", LIST_PICTURE_CASES)
def test_the_two_sides_paint_the_same_list(name):
    """The surface paints a different list than the shipped one."""
    assert_pictures_match(
        old_side=render(real_list(name)),
        new_side=render(list_painted_by_the_payload(sealed_list_payload(name))),
        note=name,
    )


@pytest.mark.parametrize("name", PAINT_PICTURE_CASES)
def test_the_two_sides_paint_the_same_sheet(name):
    """The surface paints a different sheet than the shipped one."""
    assert_pictures_match(
        old_side=render(real_sheet(name), PAINT_SIZE),
        new_side=render(
            sheet_painted_by_the_payload(sealed_sheet_payload(name)), PAINT_SIZE
        ),
        note=name,
    )


def test_the_picture_check_reports_two_real_inputs_that_really_differ():
    """The picture comparison passes whatever the second side painted."""
    old = render(real_list("happy"))
    new = render(list_painted_by_the_payload(sealed_list_payload("four_bots")))
    assert colour_count(old) > 1, colour_count(old)
    assert colour_count(new) > 1, colour_count(new)
    assert_pictures_differ(old_side=old, new_side=new, note="one row against four")
    with pytest.raises(AssertionError) as reported:
        assert_pictures_match(old_side=old, new_side=new, note="one row against four")
    assert "different picture" in str(reported.value)
    assert_pictures_match(
        old_side=render(real_list("happy")),
        new_side=render(list_painted_by_the_payload(sealed_list_payload("happy"))),
        note="one case, both sides",
    )


def test_the_sheet_picture_check_reports_two_real_inputs_that_differ():
    """The sheet picture comparison passes whatever the second side
    painted."""
    old = render(real_sheet("one_wire"), PAINT_SIZE)
    new = render(
        sheet_painted_by_the_payload(sealed_sheet_payload("two_disjoint")), PAINT_SIZE
    )
    assert colour_count(old) > 1, colour_count(old)
    assert colour_count(new) > 1, colour_count(new)
    assert_pictures_differ(old_side=old, new_side=new, note="one wire against two")
    assert_pictures_match(
        old_side=render(real_sheet("one_wire"), PAINT_SIZE),
        new_side=render(
            sheet_painted_by_the_payload(sealed_sheet_payload("one_wire")), PAINT_SIZE
        ),
        note="one wire, both sides",
    )


def test_a_sheet_with_no_wires_paints_one_flat_colour():
    """The empty sheet paints something, so its picture could report and
    every empty-sheet claim need not be read as a value."""
    empty = render(real_sheet("no_wires"), PAINT_SIZE)
    assert colour_count(empty) == 1, colour_count(empty)
    assert colour_count(render(real_sheet("one_wire"), PAINT_SIZE)) > 1
    assert_pictures_match(
        old_side=empty,
        new_side=render(
            sheet_painted_by_the_payload(sealed_sheet_payload("no_wires")), PAINT_SIZE
        ),
        note="no wires, both sides",
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's
    fonts rather than the product."""
    payload = sealed_list_payload("happy")
    payload["rows"][0][surface.COL_TICKER]["text"] = "changed"
    with pytest.raises(AssertionError) as reported:
        list_painted_by_the_payload(payload)
    assert "altered after it came off" in str(reported.value)
    payload["rows"][0][surface.COL_TICKER]["text"] = "BTC"
    assert list_painted_by_the_payload(payload) is not None
    sheet = sealed_sheet_payload("one_wire")
    sheet["calls"][4][1][0] = 1
    with pytest.raises(AssertionError):
        sheet_painted_by_the_payload(sheet)


def test_a_skin_the_list_does_not_already_wear_moves_its_picture():
    """The picture cannot report a look, so the two sides could wear
    different ones and match."""
    plain = render(real_list("four_bots"))
    skinned_view = real_list("four_bots")
    skinned_view.setStyleSheet(TEST_SKIN)
    skinned = render(skinned_view)
    assert picture_digest(plain) != picture_digest(skinned)
    assert "border" not in surface.LIST_STYLE_SHEET
    assert surface.LIST_STYLE_SHEET == ""
    assert surface.SKIN == {}


def test_the_sheets_look_is_read_as_text_because_no_skin_reaches_its_pixels():
    """The sheet's look reaches its pixels after all, so reading it as
    text alone would miss a change."""
    plain = render(real_sheet("one_wire"), PAINT_SIZE)
    skinned_canvas = real_sheet("one_wire")
    skinned_canvas.setStyleSheet(skinned_canvas.styleSheet() + TEST_SKIN)
    skinned = render(skinned_canvas, PAINT_SIZE)
    assert picture_digest(plain) == picture_digest(skinned)
    assert skinned_canvas.styleSheet() != surface.CANVAS_STYLE_SHEET
    assert real_sheet("one_wire").styleSheet() == surface.CANVAS_STYLE_SHEET


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves
    nothing."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert wide > narrow, (narrow, wide)
    else:
        assert wide == narrow, (narrow, wide)


@skip_unless_no_fonts
def test_with_no_font_database_two_equal_length_names_paint_alike():
    """Two different names of one length painted different windows with
    no font database, so the box font is not what this run is drawing."""
    app()
    first = render(real_list_named(NARROW_LABEL), SMALL_SIZE)
    second = render(real_list_named(WIDE_LABEL), SMALL_SIZE)
    assert picture_digest(first) == picture_digest(second)


@skip_unless_real_fonts
def test_with_a_font_database_two_equal_length_names_paint_apart():
    """Two different names of one length painted one window on a run
    holding fonts, so the glyphs are not deciding their own shape."""
    app()
    first = render(real_list_named(NARROW_LABEL), SMALL_SIZE)
    second = render(real_list_named(WIDE_LABEL), SMALL_SIZE)
    assert picture_digest(first) != picture_digest(second)


def real_list_named(symbol):
    """The shipped list holding one bot under a given ticker."""
    view = old_list()
    view.set_bots([reading(symbol=symbol)])
    return view


# What a picture cannot see


BLIND_TO_THE_PICTURE = {
    "bot_id_behind_a_row": "test_the_ticker_cell_carries_the_bot_it_belongs_to_on_both_sides",
    "row_lookup": "test_the_row_lookup_answers_alike_on_both_sides",
    "lane_coordinates": "test_the_lane_and_row_coordinates_are_the_shipped_lists",
    "lane_assignment": "test_the_lane_allocator_answers_the_shipped_ones_lanes",
    "exhausted_lanes": "test_a_wire_that_fits_no_lane_is_answered_with_nothing_on_both_sides",
    "drop_reason": "test_an_undrawable_wire_names_the_true_reason_on_both_sides",
    "log_line": "test_the_sheet_writes_the_shipped_log_line_when_a_wire_is_dropped",
    "log_once_per_change": "test_the_sheet_writes_one_log_line_per_change_not_per_frame",
    "refusal_words": "test_every_row_refusal_carries_the_shipped_lists_own_words",
    "half_written_row": "test_a_refusal_leaves_the_same_half_written_row_on_both_sides",
    "earlier_paint_kept": (
        "test_a_refusal_after_a_shrink_leaves_the_earlier_paint_on_both_sides"
    ),
    "brightness_refusals": "test_the_brightness_setter_answers_or_refuses_alike",
    "accessible_names": "test_the_accessible_names_are_the_shipped_widgets",
    "list_settings": "test_the_list_settings_are_the_shipped_lists",
    "sheet_settings": "test_the_sheet_settings_are_the_shipped_sheets",
    "sheet_skin": "test_the_sheets_look_is_read_as_text_because_no_skin_reaches_its_pixels",
    "drawing_call_order": "test_the_drawing_calls_are_the_shipped_sheets",
    "paint_branches": "test_the_branch_record_matches_what_the_shipped_sheet_drew",
    "wire_naming": "test_an_unnamed_wire_takes_the_name_built_from_its_ends",
    "wiring_count": "test_the_wiring_count_matches_the_actions_and_the_counter_reports",
    "timers": "test_the_timer_count_matches_and_the_counter_reports",
    "bus_topics": "test_the_bus_count_matches_and_the_counter_reports",
    "bridge_method": "test_the_bridge_registers_the_bot_swarm_list_method",
    "qt_free_import": "test_the_surface_loads_no_qt_module",
    "equal_channel_colours": (
        "test_the_grey_and_the_black_carry_equal_channels_and_compare_as_text"
    ),
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 25
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert colour_count(render(real_list("four_bots"))) > 1


def test_the_covering_test_names_are_read_from_this_module():
    """A covering name that resolves nowhere reads as covered."""
    assert "test_a_name_this_module_never_defines" not in globals()
    assert "test_the_list_settings_are_the_shipped_lists" in globals()
    assert callable(globals()["test_the_drawing_calls_are_the_shipped_sheets"])


# The values are the surface's own, not the shipped list's


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_list():
    """The surface reads the shipped list, so the two can never
    disagree.

    The change is proved to have reached the screen by a render, because
    a value read back off a widget is what the widget was told to paint
    and not what it painted.
    """
    app()
    from_the_surface = render(list_painted_by_the_payload(sealed_list_payload("happy")))
    assert_pictures_match(
        old_side=render(real_list("happy")),
        new_side=from_the_surface,
        note="before the shipped list is changed",
    )
    original_headers = shipped.COLUMN_HEADERS
    original_row_height = shipped.ROW_HEIGHT
    original_ticker_width = shipped.TICKER_COL_WIDTH
    original_lane_width = shipped.LANE_COL_WIDTH
    original_dot = shipped.LANE_DOT_RADIUS
    try:
        shipped.COLUMN_HEADERS = [
            "A",
            "B",
            "C",
            "D",
            "E",
            "F",
            "G",
            "H",
            "I",
            "J",
            "K",
            "L",
        ]
        shipped.ROW_HEIGHT = 44
        shipped.TICKER_COL_WIDTH = 150
        shipped.LANE_COL_WIDTH = 33
        shipped.LANE_DOT_RADIUS = 9
        changed = shipped.BotListView()
        HELD.append(changed)
        changed.set_bots(CASES["happy"])
        assert changed.horizontalHeaderItem(0).text() == "A"
        assert changed.columnWidth(surface.COL_TICKER) == 150
        assert changed.verticalHeader().defaultSectionSize() == 44
        assert_pictures_differ(
            old_side=render(changed),
            new_side=from_the_surface,
            note="the shipped list changed and the surface did not",
        )
        assert surface.COLUMN_HEADERS[0] == "Ticker"
        assert surface.COLUMN_HEADERS[surface.COL_LANE_0] == "L1"
        assert surface.ROW_HEIGHT == 30
        assert surface.TICKER_COL_WIDTH == 90
        assert surface.LANE_COL_WIDTH == 20
        assert surface.LANE_DOT_RADIUS == 4
        assert surface.lane_column_x(0) == 340
        assert surface.row_y(1, 4) == 45
        unmoved = new_side("happy")["state"]
        assert unmoved["headers"][0] == "Ticker"
        assert unmoved["requested_widths"][surface.COL_TICKER] == 90
        assert unmoved["row_y_centers"] == [15]
    finally:
        shipped.COLUMN_HEADERS = original_headers
        shipped.ROW_HEIGHT = original_row_height
        shipped.TICKER_COL_WIDTH = original_ticker_width
        shipped.LANE_COL_WIDTH = original_lane_width
        shipped.LANE_DOT_RADIUS = original_dot
    assert shipped.COLUMN_HEADERS == surface.COLUMN_HEADERS
    same(new_side("happy"), old_side("happy"), "after the shipped list is put back")
    assert_pictures_match(
        old_side=render(real_list("happy")),
        new_side=from_the_surface,
        note="after the shipped list is put back",
    )


def test_the_comparison_names_exactly_what_moved_and_nothing_else():
    """The comparison reports a difference in a value that did not
    change, or hides one in a value that did."""
    before = read_new_list(new_list("happy"))
    after = json.loads(json.dumps(numbers_as_text(before)))
    after["headers"][0] = "A"
    moved = [key for key in before if numbers_as_text(before[key]) != after[key]]
    assert moved == ["headers"], moved
    assert after["requested_widths"] == numbers_as_text(before["requested_widths"])
    assert after["rows"] == numbers_as_text(before["rows"])
    assert digest(before) != digest(after)


def test_the_surface_never_reads_the_shipped_module():
    """The surface imports the shipped list, so it could follow it."""
    tree = parsed(SURFACE_PATH)
    named = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                named.add(node.module)
            else:
                named.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
    assert "bot_swarm_list" not in named
    assert not any("design_system" in name for name in named), named
    assert not any("gui" in name for name in named), named
    assert named == {"__future__", "typing"}


# The bridge


def call_bridge(params):
    """One request through the real bridge, returning the whole frame."""
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": 1, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model = driven_payload_model()
    encoded = json.loads(json.dumps(surface.build_payload(model)))
    assert encoded["method"] == "bot_swarm_list.state"
    assert encoded["column_headers"] == list(surface.COLUMN_HEADERS)
    assert encoded["rows"][0][surface.COL_TICKER]["text"] == "N0"
    assert encoded["undrawable"] == [["w-8", "no-lane"]]
    assert encoded["opacity_pct"] == 60


def test_the_bridge_registers_the_bot_swarm_list_method():
    """The frontend cannot reach the Bot Swarm list."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model
    assert "bot_swarm_list.state" in registry
    frame = call_bridge({"reset": True})
    assert frame["ok"] is True
    assert frame["result"]["method"] == surface.METHOD
    assert frame["result"]["row_count"] == 0
    unknown = desktop_bridge.handle_line(
        json.dumps({"id": 2, "method": "bot_swarm_list.no_such"}), registry
    )
    assert unknown["ok"] is False


def test_the_bridge_carries_every_action():
    """An action the bridge names does nothing when it is asked for."""
    call_bridge({"reset": True})
    written = call_bridge({"action": "set_bots", "rows": CASES["nine_bots"]})
    assert written["result"]["row_count"] == 9
    assert written["result"]["bot_ids"][0] == "n-0"
    wired = call_bridge({"action": "set_wires", "wires": WIRE_CASES["one_wire"][1]})
    assert wired["result"]["lane_assignments"] == {"w-1": 0}
    dimmed = call_bridge({"action": "set_opacity", "pct": 40})
    assert dimmed["result"]["opacity_pct"] == 40
    painted = call_bridge({"action": "paint"})
    assert painted["result"]["calls"][2] == [surface.SET_OPACITY, 0.4]
    assert painted["result"]["branches"] == [surface.PAINT_WIRE]
    widened = call_bridge({"action": "set_column_widths", "widths": [7] * 12})
    assert widened["result"]["column_widths_in_use"] == [7] * 12
    assert widened["result"]["lane_column_x"][0] == 31
    put_back = call_bridge({"action": "set_column_widths"})
    assert put_back["result"]["column_widths_in_use"] == list(surface.COLUMN_WIDTHS)
    assert set(surface.BRIDGE_ACTIONS) == {
        "set_bots",
        "set_column_widths",
        "set_wires",
        "set_opacity",
        "paint",
    }


def test_the_bridge_keeps_the_list_until_a_reset():
    """A second request forgot the rows the first one wrote."""
    call_bridge({"reset": True})
    call_bridge({"action": "set_bots", "rows": CASES["two_bots"]})
    assert call_bridge({})["result"]["row_count"] == 2
    assert call_bridge({})["result"]["bot_ids"] == ["bot-a", "bot-b"]
    fresh = call_bridge({"reset": True})
    assert fresh["result"]["row_count"] == 0
    assert fresh["result"]["bot_ids"] == []
    assert fresh["result"]["opacity_pct"] == surface.OPACITY_FULL_PCT


def test_the_bridge_reports_a_request_it_cannot_serve():
    """A bad request ends the session instead of answering."""
    call_bridge({"reset": True})
    frame = call_bridge({"action": "set_bots", "rows": [{"inflow_usd": "lots"}]})
    assert frame["ok"] is False
    assert frame["error"]["type"] == "ValueError"
    assert call_bridge({"reset": True})["ok"] is True


def test_the_bridge_import_list_stays_in_order():
    """The bridge's import list drifted out of order, so the next
    surface lands somewhere a reader will not look."""
    named: list = []
    for node in ast.walk(parsed(BRIDGE_PATH)):
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs":
            named = [alias.name for alias in node.names]
    assert named == sorted(named), named
    assert "bot_swarm_list_surface" in named


# Without Qt at all


BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

BRIDGE_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'bot_swarm_list.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = (
    BLOCK_QT + "import json, sys\n"
    "from src.gui.main_tabs import bot_swarm_list_surface as s\n"
    "model = s.BotSwarmListModel()\n"
    "model.bot_list.set_bots([\n"
    "    {'bot_id': 'b-0', 'symbol': 'BTC', 'inflow_usd': 12.5,\n"
    "     'outflow_usd': 3.25, 'outflow_pct': 40.0},\n"
    "    {'bot_id': 'it\\u2019s <b>x</b>', 'symbol': '\\u0394',\n"
    "     'inflow_usd': 0.0, 'outflow_usd': 0.0, 'outflow_pct': 100.0},\n"
    "])\n"
    "model.lane_canvas.set_opacity_pct(40)\n"
    "model.lane_canvas.set_wires([\n"
    "    {'id': 'w-1', 'source_id': 'b-0', 'target_id': 'it\\u2019s <b>x</b>',\n"
    "     'phase': 0.25},\n"
    "    {'id': 'w-2', 'source_id': 'b-0', 'target_id': 'gone'},\n"
    "])\n"
    "model.lane_canvas.paint()\n"
    "payload = s.build_payload(model)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'row_count': payload['row_count'],\n"
    "    'bot_ids': payload['bot_ids'],\n"
    "    'texts': [[None if c is None else c['text'] for c in row]\n"
    "              for row in payload['rows']],\n"
    "    'colors': [[None if c is None else c['color'] for c in row]\n"
    "               for row in payload['rows']],\n"
    "    'headers': payload['column_headers'],\n"
    "    'undrawable': payload['undrawable'],\n"
    "    'log_lines': payload['log_lines'],\n"
    "    'branches': payload['branches'],\n"
    "    'calls': len(payload['calls'])}))\n"
)


def run_script(source):
    """Run one probe in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the Bot Swarm list pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == "bot_swarm_list.state"
    assert result["column_headers"] == list(surface.COLUMN_HEADERS)
    assert result["total_cols"] == 12
    assert result["inflow_color"] == INFLOW_GREEN
    assert result["pct_committed_color"] == OUTFLOW_RED
    assert result["rows"] == []
    assert result["opacity_pct"] == 100


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_the_list_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["row_count"] == 2
    assert answered["bot_ids"] == ["b-0", "it\u2019s <b>x</b>"]
    assert answered["texts"][0][surface.COL_INFLOW] == "$12.50"
    assert answered["texts"][1][surface.COL_TICKER] == "\u0394"
    assert answered["texts"][1][surface.COL_OUTFLOW_PCT] == "100%"
    assert answered["colors"][0][surface.COL_OUTFLOW_PCT] == HEADROOM_CYAN
    assert answered["colors"][1][surface.COL_OUTFLOW_PCT] == OUTFLOW_RED
    assert answered["headers"] == list(surface.COLUMN_HEADERS)
    assert answered["undrawable"] == [["w-2", "unlisted-bot"]]
    assert answered["branches"] == [surface.PAINT_WIRE, surface.PAINT_SKIP]
    assert answered["log_lines"][0][0] == "WARNING"
    assert answered["calls"] == 11


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process
    imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_hosts_the_shipped_list():
    """The Qt block let the shipped list through, so a run without Qt
    proves nothing about which side the frontend can reach."""
    probe = BLOCK_QT + (
        "import json, sys\n"
        "answer = {}\n"
        "try:\n"
        "    from src.gui import bot_swarm_list as t\n"
        "    answer['error'] = ''\n"
        "    answer['built'] = hasattr(t, 'BotListView')\n"
        "except Exception as exc:\n"
        "    answer['error'] = type(exc).__name__\n"
        "    answer['built'] = False\n"
        "from src.gui.main_tabs import bot_swarm_list_surface as s\n"
        "answer['headers'] = len(s.COLUMN_HEADERS)\n"
        "answer['qt'] = 'PySide6' in sys.modules\n"
        "print(json.dumps(answer))\n"
    )
    answered = run_script(probe)
    assert answered["built"] is False
    assert answered["headers"] == surface.TOTAL_COLS == 12
    assert answered["qt"] is False


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    tree = parsed(SURFACE_PATH)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            else:
                imported.update(alias.name for alias in node.names)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    assert imported == {"__future__", "typing"}
    list_imports = {
        (node.module or "")
        for node in ast.walk(parsed(LIST_PATH))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in list_imports), list_imports


# The shipped list is left alone


def test_the_surface_file_carries_no_carriage_return():
    """A carriage return reached the file, counted as bytes rather than
    by a line pattern."""
    assert SURFACE_PATH.read_bytes().count(b"\r") == 0
    assert Path(__file__).read_bytes().count(b"\r") == 0
    assert SURFACE_PATH.read_bytes().count(b"\n") > 0


def test_the_shipped_list_is_left_as_it_was():
    """The shipped list was edited, so the two sides are one side."""
    body = LIST_PATH.read_bytes()
    assert body.count(b"\r") == 0
    assert source_classes(LIST_PATH) == [
        "BotListView",
        "BotSwarmLaneAllocator",
        "LaneWireCanvas",
    ]
    assert len(source_functions(LIST_PATH)) == 15
    assert shipped.TOTAL_COLS == 12
