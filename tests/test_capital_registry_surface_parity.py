"""The Qt Capital Registry panel and the Qt-free surface, side by side.

A failure means the view model builds a different grid, a different
cell, a different header, a different row count or a different record of
each bot's first reservation than ``CapitalRegistryPanel`` does on the
same input.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import capital_registry_surface as surface
from src.gui.widgets.capital_registry_panel import CapitalRegistryPanel

REPO_ROOT = Path(__file__).resolve().parents[1]

UPDATE = "update"
CLEAR = "clear"

NO_REGISTRY = "no_registry"
PROBE_RAISES = "probe_raises"
NO_PROBE_METHOD = "no_probe_method"
PROBE_RETURNS_GENERATOR = "probe_returns_generator"
PROBE_RETURNS_A_NUMBER = "probe_returns_a_number"

RESERVATION_FIELDS = (
    "bot_id",
    "exchange_id",
    "base_currency",
    "reserved_usd",
    "reserved_base",
    "bot_mode",
    "last_rate_usd_per_base",
)


def reservation(
    bot_id,
    exchange_id="coinbase",
    base_currency="USD",
    reserved_usd=100.0,
    reserved_base=0.5,
    bot_mode="scrumming",
    last_rate_usd_per_base=1000.0,
):
    """One reservation as the registry hands it to the panel."""
    return SimpleNamespace(
        bot_id=bot_id,
        exchange_id=exchange_id,
        base_currency=base_currency,
        reserved_usd=reserved_usd,
        reserved_base=reserved_base,
        bot_mode=bot_mode,
        last_rate_usd_per_base=last_rate_usd_per_base,
    )


class _Registry:
    def __init__(self, reservations):
        self.reservations = reservations

    def get_reservations(self):
        return list(self.reservations)


class _RaisingRegistry:
    def get_reservations(self):
        raise RuntimeError("registry refused the probe")


class _GeneratorRegistry:
    def __init__(self, reservations):
        self.reservations = reservations

    def get_reservations(self):
        return (item for item in self.reservations)


class _NumberRegistry:
    def get_reservations(self):
        return 7


def make_registry(spec):
    """Build the registry one step drives, fresh, so no step reuses state."""
    if spec == NO_REGISTRY:
        return None
    if spec == PROBE_RAISES:
        return _RaisingRegistry()
    if spec == NO_PROBE_METHOD:
        return object()
    if spec == PROBE_RETURNS_A_NUMBER:
        return _NumberRegistry()
    if isinstance(spec, tuple) and spec and spec[0] == PROBE_RETURNS_GENERATOR:
        return _GeneratorRegistry([reservation(**fields) for fields in spec[1]])
    return _Registry([reservation(**fields) for fields in spec])


def app():
    """The process application object every render and widget needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def _pairs(mapping):
    """Key order and value survive the trace; a dict compare loses order."""
    return [[str(key), repr(value)] for key, value in mapping.items()]


def snapshot_old(widget, error):
    """Every output the Qt panel carries after one step."""
    columns = widget.columnCount()
    headers = []
    tooltips = []
    for col in range(columns):
        header_item = widget.horizontalHeaderItem(col)
        headers.append(None if header_item is None else header_item.text())
        tooltips.append(None if header_item is None else header_item.toolTip())
    grid = []
    for row in range(widget.rowCount()):
        cells = []
        for col in range(columns):
            cell_item = widget.item(row, col)
            cells.append(None if cell_item is None else cell_item.text())
        grid.append(cells)
    return {
        "error": error,
        "row_count": widget.rowCount(),
        "column_count": columns,
        "headers": headers,
        "header_tooltips": tooltips,
        "grid": grid,
        "initial_usd_by_bot": _pairs(widget._initial_usd_by_bot),
    }


def snapshot_new(model, error):
    """Every output the view model carries after the same step."""
    return {
        "error": error,
        "row_count": model.row_count(),
        "column_count": surface.COLUMN_COUNT,
        "headers": list(surface.COLUMNS),
        "header_tooltips": [
            surface.COLUMN_TOOLTIPS.get(label, "") for label in surface.COLUMNS
        ],
        "grid": [list(row) for row in model.rows],
        "initial_usd_by_bot": _pairs(model.initial_usd_by_bot),
    }


def run_old(script):
    """Drive ``CapitalRegistryPanel`` through the script, tracing every step."""
    app()
    widget = CapitalRegistryPanel()
    trace = [snapshot_old(widget, None)]
    for step in script:
        error = None
        try:
            if step[0] == CLEAR:
                widget.clear_table()
            else:
                widget.update_from_registry(make_registry(step[1]))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        trace.append(snapshot_old(widget, error))
    return trace


def run_new(script):
    """Drive the view model through the same script, tracing every step."""
    model = surface.CapitalRegistryModel()
    trace = [snapshot_new(model, None)]
    for step in script:
        error = None
        try:
            if step[0] == CLEAR:
                model.clear_table()
            else:
                model.update_from_registry(make_registry(step[1]))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        trace.append(snapshot_new(model, error))
    return trace


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


THREE_BOTS = [
    {"bot_id": "bot-0", "reserved_usd": 100.0, "reserved_base": 0.5},
    {"bot_id": "bot-1", "reserved_usd": 101.0, "reserved_base": 1.5},
    {"bot_id": "bot-2", "reserved_usd": 102.0, "reserved_base": 2.5},
]

GROWN_BOTS = [
    {"bot_id": "bot-0", "reserved_usd": 137.55, "reserved_base": 0.5},
    {"bot_id": "bot-1", "reserved_usd": 101.0, "reserved_base": 1.5},
    {"bot_id": "bot-2", "reserved_usd": 42.25, "reserved_base": 2.5},
]

PROFIT_SCRIPT = [
    (UPDATE, THREE_BOTS),
    (UPDATE, GROWN_BOTS),
    (UPDATE, THREE_BOTS),
]

SHRINK_SCRIPT = [
    (UPDATE, THREE_BOTS),
    (UPDATE, [THREE_BOTS[0]]),
    (UPDATE, THREE_BOTS + [{"bot_id": "bot-3", "reserved_usd": 7.0}]),
    (UPDATE, []),
]

CLEAR_SCRIPT = [
    (UPDATE, THREE_BOTS),
    (UPDATE, GROWN_BOTS),
    (CLEAR,),
    (UPDATE, GROWN_BOTS),
]

ABSENT_SCRIPT = [
    (UPDATE, THREE_BOTS),
    (UPDATE, NO_REGISTRY),
    (UPDATE, THREE_BOTS),
    (UPDATE, PROBE_RAISES),
    (UPDATE, THREE_BOTS),
    (UPDATE, NO_PROBE_METHOD),
    (UPDATE, GROWN_BOTS),
]

ROUNDING_SCRIPT = [
    (UPDATE, [{"bot_id": "edge", "reserved_usd": 100.0}]),
    (UPDATE, [{"bot_id": "edge", "reserved_usd": 99.999}]),
    (UPDATE, [{"bot_id": "edge", "reserved_usd": 100.001}]),
    (UPDATE, [{"bot_id": "edge", "reserved_usd": 100.005}]),
    (UPDATE, [{"bot_id": "edge", "reserved_usd": 99.995}]),
    (UPDATE, [{"bot_id": "edge", "reserved_usd": 100.006}]),
    (UPDATE, [{"bot_id": "edge", "reserved_usd": 99.994}]),
    (UPDATE, [{"bot_id": "edge", "reserved_usd": 100.015}]),
    (UPDATE, [{"bot_id": "edge", "reserved_usd": 100.025}]),
]

FORMAT_SCRIPT = [
    (
        UPDATE,
        [
            {
                "bot_id": "thousands",
                "reserved_usd": 1234567.891,
                "reserved_base": 1234.5678915,
                "last_rate_usd_per_base": 64123.45678,
            },
            {
                "bot_id": "tiny",
                "reserved_usd": 0.004,
                "reserved_base": 0.0000005,
                "last_rate_usd_per_base": 0.00005,
            },
            {
                "bot_id": "negative",
                "reserved_usd": -50.5,
                "reserved_base": -0.25,
                "last_rate_usd_per_base": -1.5,
            },
            {
                "bot_id": "zero",
                "reserved_usd": 0.0,
                "reserved_base": 0.0,
                "last_rate_usd_per_base": 0.0,
            },
            {
                "bot_id": "integers",
                "reserved_usd": 42,
                "reserved_base": 3,
                "last_rate_usd_per_base": 9,
            },
            {
                "bot_id": "decimal",
                "reserved_usd": Decimal("1.005"),
                "reserved_base": Decimal("2.0000005"),
                "last_rate_usd_per_base": Decimal("3.00005"),
            },
            {
                "bot_id": "boolean",
                "reserved_usd": True,
                "reserved_base": False,
                "last_rate_usd_per_base": True,
            },
        ],
    ),
]

EXTREME_SCRIPT = [
    (
        UPDATE,
        [
            {
                "bot_id": "infinite",
                "reserved_usd": float("inf"),
                "reserved_base": float("-inf"),
                "last_rate_usd_per_base": float("inf"),
            },
            {
                "bot_id": "not-a-number",
                "reserved_usd": float("nan"),
                "reserved_base": float("nan"),
                "last_rate_usd_per_base": float("nan"),
            },
            {
                "bot_id": "huge",
                "reserved_usd": 1e20,
                "reserved_base": 1e-20,
                "last_rate_usd_per_base": 1e20,
            },
        ],
    ),
    (
        UPDATE,
        [
            {
                "bot_id": "infinite",
                "reserved_usd": float("inf"),
                "reserved_base": 1.0,
                "last_rate_usd_per_base": 1.0,
            },
        ],
    ),
]

TEXT_SCRIPT = [
    (
        UPDATE,
        [
            {"bot_id": "", "exchange_id": "", "base_currency": "", "bot_mode": ""},
            {
                "bot_id": "unicode-Δ→⚡",
                "exchange_id": "kraken",
                "base_currency": "usd",
                "bot_mode": "extractor",
            },
            {
                "bot_id": "a" * 200,
                "exchange_id": "co<in>base",
                "base_currency": "US&D",
                "bot_mode": "scrum ming",
            },
            {
                "bot_id": 7,
                "exchange_id": None,
                "base_currency": 12.5,
                "bot_mode": ("tuple",),
            },
        ],
    ),
]

DUPLICATE_SCRIPT = [
    (
        UPDATE,
        [
            {"bot_id": "twin", "reserved_usd": 10.0},
            {"bot_id": "twin", "reserved_usd": 30.0},
            {"bot_id": "twin", "reserved_usd": 20.0},
        ],
    ),
    (
        UPDATE,
        [
            {"bot_id": "twin", "reserved_usd": 30.0},
            {"bot_id": "twin", "reserved_usd": 10.0},
        ],
    ),
]

UNFORMATTABLE_BOTS = [
    {"bot_id": "good", "reserved_usd": 1.0},
    {"bot_id": "bad", "reserved_usd": 2.0, "reserved_base": "not a number"},
    {"bot_id": "never-reached", "reserved_usd": 3.0},
]

FORMAT_RAISES_SCRIPT = [
    (UPDATE, [THREE_BOTS[0]]),
    (UPDATE, UNFORMATTABLE_BOTS),
    (UPDATE, THREE_BOTS),
    (UPDATE, UNFORMATTABLE_BOTS),
    (UPDATE, THREE_BOTS),
]

CAPTURE_RAISES_SCRIPT = [
    (UPDATE, THREE_BOTS),
    (UPDATE, [{"bot_id": "bad", "reserved_usd": "not a number"}]),
    (UPDATE, THREE_BOTS),
]

SHRINK_THEN_RAISE_SCRIPT = [
    (UPDATE, THREE_BOTS),
    (
        UPDATE,
        [{"bot_id": "bad", "reserved_usd": 5.0, "reserved_base": "not a number"}],
    ),
]

NOT_ITERABLE_SCRIPT = [
    (UPDATE, THREE_BOTS),
    (UPDATE, PROBE_RETURNS_A_NUMBER),
    (UPDATE, THREE_BOTS),
]

GENERATOR_SCRIPT = [
    (UPDATE, THREE_BOTS),
    (UPDATE, (PROBE_RETURNS_GENERATOR, GROWN_BOTS)),
    (UPDATE, THREE_BOTS),
]

EMPTY_SCRIPT: list[tuple] = []

SINGLE_SCRIPT = [(UPDATE, [THREE_BOTS[0]])]

CLEAR_FIRST_SCRIPT = [(CLEAR,), (UPDATE, THREE_BOTS), (CLEAR,), (CLEAR,)]

SCRIPTS = {
    "absent_registry": ABSENT_SCRIPT,
    "capture_raises": CAPTURE_RAISES_SCRIPT,
    "clear": CLEAR_SCRIPT,
    "clear_first": CLEAR_FIRST_SCRIPT,
    "duplicates": DUPLICATE_SCRIPT,
    "empty": EMPTY_SCRIPT,
    "extremes": EXTREME_SCRIPT,
    "format_raises": FORMAT_RAISES_SCRIPT,
    "formats": FORMAT_SCRIPT,
    "generator": GENERATOR_SCRIPT,
    "not_iterable": NOT_ITERABLE_SCRIPT,
    "profit": PROFIT_SCRIPT,
    "rounding": ROUNDING_SCRIPT,
    "shrink_and_grow": SHRINK_SCRIPT,
    "shrink_then_raise": SHRINK_THEN_RAISE_SCRIPT,
    "single": SINGLE_SCRIPT,
    "text": TEXT_SCRIPT,
}


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_old_and_new_traces_are_identical(name):
    """A step of the script builds something the other side does not."""
    old = run_old(SCRIPTS[name])
    new = run_new(SCRIPTS[name])
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_the_trace_holds_the_whole_grid(name):
    """The comparison passed by measuring nothing."""
    old = run_old(SCRIPTS[name])
    assert len(old) == len(SCRIPTS[name]) + 1
    assert old[0]["row_count"] == 0
    for step in old:
        assert step["column_count"] == 9
        assert len(step["headers"]) == 9
        assert len(step["grid"]) == step["row_count"]
        for row in step["grid"]:
            assert len(row) == 9
    if SCRIPTS[name]:
        assert any(step["grid"] for step in old)


def test_the_scripts_reach_every_documented_state():
    """A named state was never driven, so its parity was never compared."""
    reached = {"populated": False, "empty": False, "error": False, "blank_row": False}
    for name in SCRIPTS:
        for step in run_old(SCRIPTS[name]):
            if step["grid"]:
                reached["populated"] = True
            if step["row_count"] == 0:
                reached["empty"] = True
            if step["error"] is not None:
                reached["error"] = True
            for row in step["grid"]:
                if all(cell is None for cell in row):
                    reached["blank_row"] = True
    assert reached == {
        "populated": True,
        "empty": True,
        "error": True,
        "blank_row": True,
    }


def test_a_row_the_panel_could_not_format_stays_blank_or_stale():
    """A half-filled refresh left a different grid on the two sides."""
    old = run_old(FORMAT_RAISES_SCRIPT)
    new = run_new(FORMAT_RAISES_SCRIPT)
    grown = old[2]
    assert grown["error"] == (
        "ValueError: Unknown format code 'f' for object of type 'str'"
    )
    assert grown["row_count"] == 3
    assert grown["grid"][0][0] == "good"
    assert grown["grid"][1] == [None] * 9
    assert grown["grid"][2] == [None] * 9
    stale = old[4]
    assert stale["error"] == grown["error"]
    assert stale["row_count"] == 3
    assert stale["grid"][0][0] == "good"
    assert stale["grid"][1][0] == "bot-1"
    assert stale["grid"][2][0] == "bot-2"
    assert new[2]["grid"] == grown["grid"]
    assert new[4]["grid"] == stale["grid"]


def test_a_reservation_the_panel_cannot_read_leaves_the_grid_alone():
    """A refusal in the first pass resized the grid on one side only."""
    old = run_old(CAPTURE_RAISES_SCRIPT)
    new = run_new(CAPTURE_RAISES_SCRIPT)
    refused = old[2]
    assert refused["error"] == (
        "ValueError: could not convert string to float: 'not a number'"
    )
    assert refused["row_count"] == 3
    assert [row[0] for row in refused["grid"]] == ["bot-0", "bot-1", "bot-2"]
    assert refused["initial_usd_by_bot"] == [
        ["bot-0", "100.0"],
        ["bot-1", "101.0"],
        ["bot-2", "102.0"],
    ]
    assert new[2] == refused


def test_a_shorter_list_drops_the_rows_off_the_end():
    """The grid kept the wrong rows when the reservation list shrank."""
    old = run_old(SHRINK_SCRIPT)
    new = run_new(SHRINK_SCRIPT)
    assert [row[0] for row in old[1]["grid"]] == ["bot-0", "bot-1", "bot-2"]
    assert [row[0] for row in old[2]["grid"]] == ["bot-0"]
    assert [row[0] for row in old[3]["grid"]] == [
        "bot-0",
        "bot-1",
        "bot-2",
        "bot-3",
    ]
    assert old[4]["grid"] == []
    assert [step["row_count"] for step in old] == [0, 3, 1, 4, 0]
    assert [step["grid"] for step in new] == [step["grid"] for step in old]


def test_a_shrink_keeps_the_rows_at_the_top_of_the_grid():
    """The grid dropped rows off the front, so the wrong rows survived.

    Every surviving row is normally rewritten in the same pass, which
    hides which end was cut. Here the rewrite raises on the first row, so
    the row left behind is the one the resize chose.
    """
    old = run_old(SHRINK_THEN_RAISE_SCRIPT)
    new = run_new(SHRINK_THEN_RAISE_SCRIPT)
    assert [row[0] for row in old[1]["grid"]] == ["bot-0", "bot-1", "bot-2"]
    assert old[2]["error"] == (
        "ValueError: Unknown format code 'f' for object of type 'str'"
    )
    assert old[2]["row_count"] == 1
    assert old[2]["grid"][0][0] == "bot-0"
    assert old[2]["grid"][0][3] == "$100.00"
    assert new[2]["grid"] == old[2]["grid"]


def test_the_first_reservation_seen_wins_for_a_repeated_bot():
    """A repeated bot recorded a different starting reservation."""
    old = run_old(DUPLICATE_SCRIPT)
    new = run_new(DUPLICATE_SCRIPT)
    assert old[1]["initial_usd_by_bot"] == [["twin", "10.0"]]
    assert [row[7] for row in old[1]["grid"]] == ["$10.00", "$10.00", "$10.00"]
    assert [row[8] for row in old[1]["grid"]] == ["$+0.00", "$+20.00", "$+10.00"]
    assert old[2]["initial_usd_by_bot"] == [["twin", "10.0"]]
    assert new[1] == old[1]
    assert new[2] == old[2]


def test_clearing_forgets_every_starting_reservation():
    """A clear left a starting reservation behind on one of the two sides."""
    old = run_old(CLEAR_SCRIPT)
    new = run_new(CLEAR_SCRIPT)
    assert old[2]["initial_usd_by_bot"] == [
        ["bot-0", "100.0"],
        ["bot-1", "101.0"],
        ["bot-2", "102.0"],
    ]
    assert old[3]["initial_usd_by_bot"] == []
    assert old[3]["row_count"] == 0
    assert old[4]["initial_usd_by_bot"] == [
        ["bot-0", "137.55"],
        ["bot-1", "101.0"],
        ["bot-2", "42.25"],
    ]
    assert [row[8] for row in old[4]["grid"]] == ["$+0.00", "$+0.00", "$+0.00"]
    assert new == old


def test_the_profit_delta_column_carries_its_sign():
    """The Profit Delta column lost a sign, a zero or a rounded zero."""
    old = run_old(PROFIT_SCRIPT)
    new = run_new(PROFIT_SCRIPT)
    assert [row[8] for row in old[1]["grid"]] == ["$+0.00", "$+0.00", "$+0.00"]
    assert [row[8] for row in old[2]["grid"]] == ["$+37.55", "$+0.00", "$-59.75"]
    assert [row[8] for row in old[3]["grid"]] == ["$+0.00", "$+0.00", "$+0.00"]
    assert [row[8] for row in new[2]["grid"]] == [row[8] for row in old[2]["grid"]]
    rounded = run_old(ROUNDING_SCRIPT)
    assert [step["grid"][0][8] for step in rounded[1:]] == [
        "$+0.00",
        "$-0.00",
        "$+0.00",
        "$+0.00",
        "$-0.00",
        "$+0.01",
        "$-0.01",
        "$+0.02",
        "$+0.03",
    ]
    assert [step["grid"][0][3] for step in rounded[1:]] == [
        "$100.00",
        "$100.00",
        "$100.00",
        "$100.00",
        "$100.00",
        "$100.01",
        "$99.99",
        "$100.02",
        "$100.03",
    ]


def test_the_money_columns_carry_no_thousands_separator():
    """A money cell grew a separator the panel never wrote."""
    old = run_old(FORMAT_SCRIPT)[1]["grid"]
    assert old[0][3] == "$1234567.89"
    assert old[0][4] == "1234.567892"
    assert old[0][6] == "$64123.4568"
    assert old[1][3] == "$0.00"
    assert old[1][4] == "0.000000"
    assert old[1][6] == "$0.0001"
    assert old[3][3] == "$0.00"
    assert run_new(FORMAT_SCRIPT)[1]["grid"] == old


def test_the_two_format_spellings_agree_on_every_edge_value():
    """The surface's format constants drifted from the panel's f-strings."""
    values = [
        0.0,
        -0.0,
        1.0,
        -1.0,
        0.005,
        -0.005,
        99.995,
        100.005,
        1234567.891,
        1e20,
        1e-20,
        float("inf"),
        float("-inf"),
        float("nan"),
        42,
        True,
        Decimal("1.005"),
    ]
    for value in values:
        assert surface.USD_FORMAT.format(value) == f"${value:.2f}"
        assert surface.BASE_FORMAT.format(value) == f"{value:.6f}"
        assert surface.RATE_FORMAT.format(value) == f"${value:.4f}"
        assert surface.DELTA_FORMAT.format(value) == f"${value:+.2f}"
    assert surface.USD_FORMAT.format(1.0) != surface.DELTA_FORMAT.format(1.0)


def test_the_headers_match_the_panels_own_headers():
    """A column header, its order or its count drifted from the panel."""
    app()
    widget = CapitalRegistryPanel()
    painted = [
        widget.horizontalHeaderItem(col).text() for col in range(widget.columnCount())
    ]
    assert list(surface.COLUMNS) == painted
    assert painted == [
        "Bot ID",
        "Exchange",
        "Base",
        "Reserved USD",
        "Reserved Base",
        "Mode",
        "Last Rate USD/Base",
        "Initial USD",
        "Profit Δ",
    ]
    assert surface.COLUMN_COUNT == widget.columnCount() == 9


def test_widget_properties_match_the_panel():
    """A panel property drifted from the value the surface reports."""
    from PySide6.QtWidgets import QAbstractItemView, QTableWidget

    app()
    widget = CapitalRegistryPanel()
    assert surface.WIDGET == {
        "accessible_name": widget.accessibleName(),
        "column_count": widget.columnCount(),
        "initial_row_count": widget.rowCount(),
        "edit_triggers": "none",
        "selection_behavior": "rows",
        "alternating_row_colors": widget.alternatingRowColors(),
        "vertical_header_visible": not widget.verticalHeader().isHidden(),
        "stretch_last_section": widget.horizontalHeader().stretchLastSection(),
    }
    assert widget.editTriggers() == QAbstractItemView.NoEditTriggers
    assert widget.selectionBehavior() == QAbstractItemView.SelectRows
    assert surface.ACCESSIBLE_NAME == "Capital Registry Panel"
    assert surface.ALTERNATING_ROW_COLORS is True
    assert surface.VERTICAL_HEADER_VISIBLE is False
    assert surface.STRETCH_LAST_SECTION is True
    assert surface.INITIAL_ROW_COUNT == 0
    bare = QTableWidget(0, 9)
    assert bare.verticalHeader().isHidden() is False
    assert bare.alternatingRowColors() is False
    assert bare.editTriggers() != QAbstractItemView.NoEditTriggers
    assert bare.selectionBehavior() != QAbstractItemView.SelectRows
    assert bare.horizontalHeader().stretchLastSection() is False


def test_the_panel_sets_no_column_width_and_no_tooltip():
    """A width or a tooltip the panel sets was dropped from the surface."""
    from PySide6.QtWidgets import QTableWidget

    app()
    widget = CapitalRegistryPanel()
    bare = QTableWidget(0, 9)
    bare.horizontalHeader().setStretchLastSection(True)
    widget.resize(900, 240)
    bare.resize(900, 240)
    widget.ensurePolished()
    bare.ensurePolished()
    assert [widget.columnWidth(col) for col in range(9)] == [
        bare.columnWidth(col) for col in range(9)
    ]
    assert [widget.horizontalHeaderItem(col).toolTip() for col in range(9)] == [""] * 9
    assert surface.COLUMN_WIDTHS_PX == {}
    assert surface.COLUMN_TOOLTIPS == {}
    narrowed = QTableWidget(0, 9)
    narrowed.setColumnWidth(0, 31)
    assert narrowed.columnWidth(0) != bare.columnWidth(0)


METHOD_MAP = {
    "update_from_registry": "update_from_registry",
    "clear_table": "clear_table",
}


def test_every_panel_method_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    panel_methods = {
        name
        for name, value in vars(CapitalRegistryPanel).items()
        if callable(value) and name != "__init__"
    }
    assert panel_methods == set(METHOD_MAP)
    for target in METHOD_MAP.values():
        assert callable(getattr(surface.CapitalRegistryModel, target))


def test_neither_file_connects_a_signal():
    """A signal connection appeared on one side and not the other."""
    panel_text = (REPO_ROOT / "src/gui/widgets/capital_registry_panel.py").read_text(
        encoding="utf-8"
    )
    surface_text = (
        REPO_ROOT / "src/gui/main_tabs/capital_registry_surface.py"
    ).read_text(encoding="utf-8")
    assert panel_text.count(".connect(") == 0
    assert surface_text.count(".connect(") == 0
    assert panel_text.count("setToolTip") == 0
    assert surface_text.count("setToolTip") == 0
    wired = (REPO_ROOT / "src/gui/main_window.py").read_text(encoding="utf-8")
    assert wired.count(".connect(") > 0
    assert wired.count("setToolTip") > 0


PAINTING_FILES = {
    "setBackground": "src/gui/indicator_panel.py",
    "setForeground": "src/gui/indicator_panel.py",
    "setStyleSheet": "src/gui/indicator_panel.py",
    "QColor": "src/gui/indicator_panel.py",
    "design_system": "src/gui/widgets/bot_status_table.py",
}


def test_the_panel_declares_no_colour_of_its_own():
    """The panel grew a colour rule the surface does not carry."""
    panel_text = (REPO_ROOT / "src/gui/widgets/capital_registry_panel.py").read_text(
        encoding="utf-8"
    )
    assert "setBackground" not in panel_text
    assert "setForeground" not in panel_text
    assert "setStyleSheet" not in panel_text
    assert "design_system" not in panel_text
    assert "QColor" not in panel_text
    for marker, path in PAINTING_FILES.items():
        assert marker in (REPO_ROOT / path).read_text(encoding="utf-8"), marker


def test_rgb_matches_qcolor_on_every_token():
    """The Qt-free colour split disagrees with QColor on a token."""
    from PySide6.QtGui import QColor

    assert surface.rgb("#123456") == (18, 52, 86)
    assert surface.rgb("#abc") == (170, 187, 204)
    assert surface.rgb("#ff8000") == (255, 128, 0)
    assert surface.rgb("#ff8000") != surface.rgb("#0080ff")
    for token in (surface.ROW_COLOR, surface.ALT_ROW_COLOR, surface.TEXT_COLOR):
        painted = QColor(token)
        assert surface.rgb(token) == (
            painted.red(),
            painted.green(),
            painted.blue(),
        )


def image_digest(image):
    return hashlib.sha256(bytes(image.constBits())).hexdigest()


def colour_count(image, hex_colour):
    from PySide6.QtGui import QColor

    target = QColor(hex_colour).rgb()
    return sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixel(x, y) == target
    )


def _full(bot_id, reserved_usd, reserved_base, rate):
    """Every field the panel reads, so both sides start from one input."""
    return {
        "bot_id": bot_id,
        "exchange_id": "coinbase",
        "base_currency": "USD",
        "reserved_usd": reserved_usd,
        "reserved_base": reserved_base,
        "bot_mode": "scrumming",
        "last_rate_usd_per_base": rate,
    }


PIXEL_RESERVATIONS = [
    _full("bot-0", 100.0, 0.5, 1000.0),
    _full("bot-1", 101.0, 1.5, 1001.0),
    _full("bot-2", 102.0, 2.5, 1002.0),
]
PIXEL_GROWN = [
    _full("bot-0", 137.55, 0.5, 1000.0),
    _full("bot-1", 101.0, 1.5, 1001.0),
    _full("bot-2", 42.25, 2.5, 1002.0),
]
PIXEL_SIZE = (1200, 260)

EDIT_TRIGGER_VALUES = {"none": "NoEditTriggers"}
SELECTION_BEHAVIOR_VALUES = {"rows": "SelectRows"}


def widget_painted_by_the_panel():
    widget = CapitalRegistryPanel()
    widget.update_from_registry(make_registry(PIXEL_RESERVATIONS))
    widget.update_from_registry(make_registry(PIXEL_GROWN))
    return widget


def model_payload():
    model = surface.CapitalRegistryModel()
    surface.build_view_model(model, PIXEL_RESERVATIONS)
    return surface.build_view_model(model, PIXEL_GROWN)


def widget_painted_by_the_model(payload):
    """A bare table filled only from the payload, never from the panel."""
    from PySide6.QtWidgets import QAbstractItemView, QTableWidget, QTableWidgetItem

    properties = payload["widget"]
    widget = QTableWidget(properties["initial_row_count"], properties["column_count"])
    widget.setAccessibleName(properties["accessible_name"])
    widget.setHorizontalHeaderLabels(payload["columns"])
    widget.setEditTriggers(
        getattr(QAbstractItemView, EDIT_TRIGGER_VALUES[properties["edit_triggers"]])
    )
    widget.setSelectionBehavior(
        getattr(
            QAbstractItemView,
            SELECTION_BEHAVIOR_VALUES[properties["selection_behavior"]],
        )
    )
    widget.setAlternatingRowColors(properties["alternating_row_colors"])
    widget.verticalHeader().setVisible(properties["vertical_header_visible"])
    widget.horizontalHeader().setStretchLastSection(properties["stretch_last_section"])
    widget.setRowCount(payload["row_count"])
    for row, cells in enumerate(payload["rows"]):
        for col, text in enumerate(cells):
            if text is not None:
                widget.setItem(row, col, QTableWidgetItem(text))
    return widget


def test_the_two_sides_render_the_same_pixels():
    """The page paints a value, a colour or a position the panel does not."""
    app()
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_model = render_offscreen(
        widget_painted_by_the_model(model_payload()), PIXEL_SIZE
    )
    assert from_panel.size() == from_model.size()
    assert image_digest(from_panel) == image_digest(from_model)


def has_real_fonts():
    """True when the platform exposes a font database.

    Offscreen takes its database from the host: none under
    QT_QPA_PLATFORM=offscreen on Windows, populated on a Linux host with
    fontconfig. With none every family resolves to a box font advancing
    one em per character.
    """
    from PySide6.QtGui import QFontDatabase

    return len(QFontDatabase.families()) > 0


def test_the_font_database_decides_what_the_pixel_check_can_read():
    """The pixel check is trusted to compare the text in a cell.

    Both halves are driven: with no font database two cells of equal
    length render identically whatever they say, and with one they do
    not. Cell text is compared as exact strings in the trace above; the
    pixel check covers layout, colour and how many characters a cell
    carries.
    """
    app()
    same_length = model_payload()
    same_length["rows"][0][8] = "$-37.55"
    assert same_length["rows"][0][8] != model_payload()["rows"][0][8]
    assert len(same_length["rows"][0][8]) == len(model_payload()["rows"][0][8])
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_same_length = render_offscreen(
        widget_painted_by_the_model(same_length), PIXEL_SIZE
    )
    if has_real_fonts():
        assert image_digest(from_panel) != image_digest(from_same_length)
    else:
        assert image_digest(from_panel) == image_digest(from_same_length)


def test_the_pixel_check_reports_a_cell_of_a_different_length():
    """The image comparison passes whatever the second side paints."""
    app()
    payload = model_payload()
    payload["rows"][0][8] = "$+3.10"
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_altered = render_offscreen(widget_painted_by_the_model(payload), PIXEL_SIZE)
    assert image_digest(from_panel) != image_digest(from_altered)


def test_the_pixel_check_reports_an_empty_cell():
    """The image comparison cannot see a cell lose its value."""
    app()
    payload = model_payload()
    payload["rows"][1][3] = None
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_altered = render_offscreen(widget_painted_by_the_model(payload), PIXEL_SIZE)
    assert image_digest(from_panel) != image_digest(from_altered)


def test_the_pixel_check_reports_a_dropped_row():
    """The image comparison cannot see a row disappear."""
    app()
    payload = model_payload()
    payload["rows"] = payload["rows"][:2]
    payload["row_count"] = 2
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_altered = render_offscreen(widget_painted_by_the_model(payload), PIXEL_SIZE)
    assert image_digest(from_panel) != image_digest(from_altered)


def test_the_pixel_check_reports_two_swapped_headers():
    """The image comparison cannot see two columns change places."""
    app()
    payload = model_payload()
    payload["columns"][0], payload["columns"][1] = (
        payload["columns"][1],
        payload["columns"][0],
    )
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_altered = render_offscreen(widget_painted_by_the_model(payload), PIXEL_SIZE)
    assert image_digest(from_panel) != image_digest(from_altered)


def test_the_pixel_check_reports_two_swapped_rows():
    """The image comparison cannot see two rows change places."""
    app()
    payload = model_payload()
    payload["rows"][0], payload["rows"][2] = payload["rows"][2], payload["rows"][0]
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_swapped = render_offscreen(widget_painted_by_the_model(payload), PIXEL_SIZE)
    assert image_digest(from_panel) != image_digest(from_swapped)


def test_the_pixel_check_reports_a_changed_header():
    """The image comparison cannot see a column header change."""
    app()
    payload = model_payload()
    payload["columns"][8] = "Profit"
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_altered = render_offscreen(widget_painted_by_the_model(payload), PIXEL_SIZE)
    assert image_digest(from_panel) != image_digest(from_altered)


def test_the_pixel_check_reports_the_alternating_rows_turned_off():
    """The image comparison cannot see the alternating row colour go."""
    app()
    payload = model_payload()
    payload["widget"]["alternating_row_colors"] = False
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_altered = render_offscreen(widget_painted_by_the_model(payload), PIXEL_SIZE)
    assert image_digest(from_panel) != image_digest(from_altered)


def test_the_pixel_check_reports_the_row_numbers_coming_back():
    """The image comparison cannot see the hidden row-number column return."""
    app()
    payload = model_payload()
    payload["widget"]["vertical_header_visible"] = True
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_altered = render_offscreen(widget_painted_by_the_model(payload), PIXEL_SIZE)
    assert image_digest(from_panel) != image_digest(from_altered)


def test_the_pixel_check_reports_the_last_column_no_longer_stretching():
    """The image comparison cannot see the last column stop stretching."""
    app()
    payload = model_payload()
    payload["widget"]["stretch_last_section"] = False
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_altered = render_offscreen(widget_painted_by_the_model(payload), PIXEL_SIZE)
    assert image_digest(from_panel) != image_digest(from_altered)


def test_the_three_declared_colours_reach_the_panels_pixels():
    """A declared colour is painted by neither side, or by only one."""
    app()
    from_panel = render_offscreen(widget_painted_by_the_panel(), PIXEL_SIZE)
    from_model = render_offscreen(
        widget_painted_by_the_model(model_payload()), PIXEL_SIZE
    )
    for token in (surface.ROW_COLOR, surface.ALT_ROW_COLOR, surface.TEXT_COLOR):
        assert colour_count(from_panel, token) > 0, token
        assert colour_count(from_model, token) == colour_count(from_panel, token)
    assert colour_count(from_panel, "#ff00ff") == 0
    assert surface.ROW_COLOR != surface.ALT_ROW_COLOR != surface.TEXT_COLOR


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model = surface.CapitalRegistryModel()
    surface.build_view_model(model, PIXEL_RESERVATIONS)
    payload = surface.build_view_model(model, PIXEL_GROWN)
    encoded = json.loads(json.dumps(payload))
    assert encoded["columns"] == list(surface.COLUMNS)
    assert encoded["row_count"] == 3
    assert [row[0] for row in encoded["rows"]] == ["bot-0", "bot-1", "bot-2"]
    assert [row[3] for row in encoded["rows"]] == ["$137.55", "$101.00", "$42.25"]
    assert [row[7] for row in encoded["rows"]] == ["$100.00", "$101.00", "$102.00"]
    assert [row[8] for row in encoded["rows"]] == ["$+37.55", "$+0.00", "$-59.75"]
    assert encoded["row_color"] == [255, 255, 255]
    assert encoded["alt_row_color"] == [247, 247, 247]
    assert encoded["text_color"] == [0, 0, 0]
    assert encoded["widget"]["accessible_name"] == "Capital Registry Panel"
    assert encoded["initial_usd_by_bot"] == {
        "bot-0": 100.0,
        "bot-1": 101.0,
        "bot-2": 102.0,
    }


def test_view_model_matches_the_panel_on_the_same_reservations():
    """The bridge payload disagrees with the grid the panel builds."""
    app()
    widget = CapitalRegistryPanel()
    widget.update_from_registry(make_registry(PIXEL_RESERVATIONS))
    widget.update_from_registry(make_registry(PIXEL_GROWN))
    payload = model_payload()
    assert payload["rows"] == [
        [widget.item(row, col).text() for col in range(widget.columnCount())]
        for row in range(widget.rowCount())
    ]
    assert payload["row_count"] == widget.rowCount()


def test_an_absent_reservations_key_empties_the_grid():
    """The absent registry stopped emptying the grid."""
    model = surface.CapitalRegistryModel()
    surface.build_view_model(model, PIXEL_RESERVATIONS)
    payload = surface.build_view_model(model, None)
    assert payload["rows"] == []
    assert payload["row_count"] == 0
    assert payload["initial_usd_by_bot"] == {
        "bot-0": 100.0,
        "bot-1": 101.0,
        "bot-2": 102.0,
    }
    cleared = surface.build_view_model(model, None, clear=True)
    assert cleared["initial_usd_by_bot"] == {}


def test_view_model_defaults_a_missing_field():
    """A partial entry raised instead of painting its defaults."""
    model = surface.CapitalRegistryModel()
    payload = surface.build_view_model(model, [{"bot_id": "sparse"}])
    assert payload["rows"] == [
        ["sparse", "", "", "$0.00", "0.000000", "", "$0.0000", "$0.00", "$+0.00"]
    ]


def test_view_model_skips_an_entry_it_cannot_read(capture_log):
    """An entry that cannot be read raised instead of being skipped."""

    class _Raising:
        def get(self, _key, _default=None):
            raise ValueError("unreadable reservation")

    model = surface.CapitalRegistryModel()
    with capture_log(surface.logger.name) as records:
        payload = surface.build_view_model(
            model, [_Raising(), {"bot_id": "survivor", "reserved_usd": 5.0}]
        )
    assert [row[0] for row in payload["rows"]] == ["survivor"]
    assert [record.getMessage() for record in records] == [
        "capital registry reservation skipped: unreadable reservation"
    ]


def test_bridge_registers_the_capital_registry_method():
    """The renderer cannot reach the Capital Registry through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 21,
                "method": surface.METHOD,
                "params": {
                    "clear": True,
                    "reservations": [
                        {
                            "bot_id": "bridge-bot",
                            "exchange_id": "coinbase",
                            "base_currency": "USD",
                            "reserved_usd": 250.5,
                            "reserved_base": 0.004,
                            "bot_mode": "scrumming",
                            "last_rate_usd_per_base": 64123.45678,
                        }
                    ],
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["rows"] == [
        [
            "bridge-bot",
            "coinbase",
            "USD",
            "$250.50",
            "0.004000",
            "scrumming",
            "$64123.4568",
            "$250.50",
            "$+0.00",
        ]
    ]


def test_a_cell_the_bridge_cannot_format_becomes_an_error_frame():
    """A value the table cannot format took the bridge session down."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 22,
                "method": surface.METHOD,
                "params": {
                    "clear": True,
                    "reservations": [{"bot_id": "bad", "reserved_usd": "not a number"}],
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"
    surface.build_view_model(surface.PANE_MODEL, None, clear=True)


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'capital_registry.rows', 'params':"
    " {'reservations': [{'bot_id': 'probe-bot', 'reserved_usd': 250.5,"
    " 'reserved_base': 0.004, 'last_rate_usd_per_base': 64123.45678}]}}),"
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
    """Reaching the Capital Registry pulled Qt into the backend process."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    row = answered["frame"]["result"]["rows"][0]
    assert row[0] == "probe-bot"
    assert row[3] == "$250.50"
    assert row[6] == "$64123.4568"
    assert answered["frame"]["result"]["text_color"] == [0, 0, 0]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_reservation_fields_are_the_seven_the_panel_reads():
    """The surface reads a field the panel does not, or misses one."""
    panel_text = (REPO_ROOT / "src/gui/widgets/capital_registry_panel.py").read_text(
        encoding="utf-8"
    )
    for field in RESERVATION_FIELDS:
        assert f"r.{field}" in panel_text, field
    assert "reserved_at_ts" not in panel_text
    assert "last_refreshed_ts" not in panel_text
    assert set(surface.Reservation.__dataclass_fields__) == set(RESERVATION_FIELDS)
