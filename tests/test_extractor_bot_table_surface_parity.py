"""The shipped Extractor bot table and the Qt-free surface, side by side.

A failure means the surface builds a different row, a different colour, a
different tooltip, a different button, a different highlight, a different
recorded call or a different refusal than ``ExtractorBotTable``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import extractor_bot_table_surface as surface
from src.gui.widgets import extractor_bot_table as shipped
from tests.fixtures.host_fonts import (
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

TABLE_PATH = REPO_ROOT / "src/gui/widgets/extractor_bot_table.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/extractor_bot_table_surface.py"
WIRING_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
TIMER_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/history_tab.py"
BUS_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"

PIXEL_SIZE = (700, 220)
SMALL_PIXEL_SIZE = (420, 140)

# The counts the shipped table carries. Each is measured off the file and
# compared with what the surface declares.
TABLE_CONNECT_SITES = 1
TABLE_TIMER_SITES = 0
TABLE_BUS_SITES = 0

# The design values the two colour maps are built from, typed out here
# rather than read from either side, so a re-valued token cannot move
# both together. `#888` is the one token written at three digits; the
# screen reports it at six.
RUNNING_COLOR = "#00ff88"
IDLE_SHORT_HEX = "#888"
IDLE_COLOR = "#888888"
PAUSED_COLOR = "#ffaa00"
ERROR_COLOR = "#ff3366"
COOLDOWN_COLOR = "#ff6600"
STOPPED_COLOR = "#666666"
STARTING_COLOR = "#00e6ff"
TEXT_HIGH_COLOR = "#e0e0f0"
TEXT_MED_COLOR = "#a8a8c5"
PLACEHOLDER_COLOR = "#555555"

FIRE_COLUMN_WIDTH = 70
DETAIL_COLUMN_WIDTH = 60

UNICODE_TEXT = "Δ_flip→⚡"
MARKUP_TEXT = "<b>bot</b>&nbsp;<script>x</script>"
APOSTROPHE_TEXT = "it's a 'quoted' name"
NEWLINE_TEXT = "two\nlines"
LONG_TEXT = "Z" * 200
THOUSAND_MILLION = 1_000_000_000
ONE_BILLIONTH = 1e-9
INFINITY = float("inf")
NOT_A_NUMBER = float("nan")

HELD: list = []


# ---------------------------------------------------------------------
# The fleet statuses both sides read
# ---------------------------------------------------------------------


def status(**over):
    """One Extractor fleet status, the shape the dashboard passes in."""
    found = {
        "bot_id": "bot-a",
        "state": "running",
        "chunk_size_usd": 100.0,
        "chunk_free_base": 1.0,
        "chunk_size_base": 2.0,
        "n_positions_open": 1,
        "n_positions_drawdown": 0,
        "pool_color": "yellow",
        "base_currency": "BTC",
        "stats": {"total_trades": 3},
    }
    found.update(over)
    return found


TWO_BOTS = [
    status(),
    status(bot_id="bot-b", state="paused", pool_color="red", base_currency="ETH"),
]
TWO_BOTS_SWAPPED = [
    status(bot_id="bot-b", state="paused", pool_color="red", base_currency="ETH"),
    status(),
]
THREE_BOTS = TWO_BOTS + [
    status(bot_id="bot-c", state="error", pool_color="green", base_currency="SOL")
]

CASES: dict = {
    "happy": [status()],
    "empty": [],
    "two_bots": TWO_BOTS,
    "two_bots_swapped": TWO_BOTS_SWAPPED,
    "three_bots": THREE_BOTS,
    "zero": [
        status(
            chunk_size_usd=0.0,
            chunk_free_base=0.0,
            chunk_size_base=0.0,
            n_positions_open=0,
            n_positions_drawdown=0,
            pool_color="green",
        )
    ],
    "negative": [
        status(
            chunk_size_usd=-5.0,
            chunk_free_base=-2.0,
            chunk_size_base=-1.0,
            n_positions_open=-3,
            n_positions_drawdown=-4,
        )
    ],
    "thousand_million": [
        status(
            chunk_size_usd=float(THOUSAND_MILLION),
            chunk_free_base=float(THOUSAND_MILLION),
            chunk_size_base=2.0 * THOUSAND_MILLION,
            n_positions_open=THOUSAND_MILLION,
        )
    ],
    "one_billionth": [
        status(
            chunk_size_usd=ONE_BILLIONTH,
            chunk_free_base=ONE_BILLIONTH,
            chunk_size_base=2 * ONE_BILLIONTH,
        )
    ],
    "unicode": [
        status(bot_id=UNICODE_TEXT, base_currency=UNICODE_TEXT, state=UNICODE_TEXT)
    ],
    "long_text": [status(bot_id=LONG_TEXT, base_currency=LONG_TEXT)],
    "markup": [status(bot_id=MARKUP_TEXT, base_currency=MARKUP_TEXT)],
    "apostrophe": [status(bot_id=APOSTROPHE_TEXT, base_currency=APOSTROPHE_TEXT)],
    "newline_name": [status(bot_id=NEWLINE_TEXT, base_currency=NEWLINE_TEXT)],
    "wrong_capitals_state": [status(state="RUNNING")],
    "wrong_capitals_pool": [status(pool_color="GREEN")],
    "number_where_text_belongs": [status(bot_id=7, base_currency=7, symbol=7)],
    "text_where_number_belongs": [status(chunk_size_usd="lots")],
    "text_where_count_belongs": [status(n_positions_open="many")],
    "infinity": [
        status(
            chunk_size_usd=INFINITY,
            chunk_free_base=INFINITY,
            chunk_size_base=INFINITY,
        )
    ],
    "minus_infinity": [
        status(
            chunk_size_usd=-INFINITY,
            chunk_free_base=-INFINITY,
            chunk_size_base=-INFINITY,
        )
    ],
    "not_a_number": [
        status(
            chunk_size_usd=NOT_A_NUMBER,
            chunk_free_base=NOT_A_NUMBER,
            chunk_size_base=NOT_A_NUMBER,
        )
    ],
    "infinity_count": [status(n_positions_open=INFINITY)],
    "not_a_number_count": [status(n_positions_drawdown=NOT_A_NUMBER)],
    "missing_keys": [{}],
    "none_values": [
        status(
            bot_id=None,
            state=None,
            chunk_size_usd=None,
            chunk_free_base=None,
            chunk_size_base=None,
            n_positions_open=None,
            n_positions_drawdown=None,
            base_currency=None,
        )
    ],
    "pool_color_number": [status(pool_color=7)],
    "pool_color_none": [status(pool_color=None)],
    "pool_color_unknown": [status(pool_color="purple")],
    "state_unknown": [status(state="melting")],
    "state_empty": [status(state="")],
    "stats_missing": [status(stats={})],
    "stats_not_a_dict": [status(stats=7)],
    "stats_none": [status(stats=None)],
    "symbol_fallback": [status(base_currency="", symbol="ETH")],
    "both_names_empty": [status(base_currency="", symbol="")],
    "statuses_not_a_list": 7,
    "status_not_a_dict": [7],
    "free_over_size": [status(chunk_free_base=9.0, chunk_size_base=2.0)],
    "all_states": [
        status(bot_id="s-%d" % index, state=name)
        for index, name in enumerate(sorted(surface.STATE_COLORS))
    ],
    "all_pool_colors": [
        status(bot_id="p-%d" % index, pool_color=name)
        for index, name in enumerate(sorted(surface.POOL_COLORS))
    ],
}

# Each step drives one of the table's three entry points on both sides.
STEP_CASES: dict = {
    "one_update": (("update", "happy"),),
    "empty_table": (("update", "empty"),),
    "select_then_reorder": (
        ("update", "two_bots"),
        ("select", 1),
        ("update", "two_bots_swapped"),
    ),
    "select_then_drop": (
        ("update", "two_bots"),
        ("select", 1),
        ("update", "happy"),
    ),
    "select_then_steady": (
        ("update", "two_bots"),
        ("select", 0),
        ("update", "two_bots"),
    ),
    "select_then_empty": (
        ("update", "two_bots"),
        ("select", 1),
        ("update", "empty"),
    ),
    "shrink_from_three": (
        ("update", "three_bots"),
        ("select", 2),
        ("update", "two_bots"),
    ),
    "grow_keeps_bot": (
        ("update", "two_bots"),
        ("select", 1),
        ("update", "three_bots"),
    ),
    "detail_on_row": (("update", "two_bots"), ("detail", "bot-b")),
    "detail_missing_bot": (("update", "two_bots"), ("detail", "gone")),
    "detail_blank": (("update", "two_bots"), ("detail", "")),
    "detail_before_rows": (("detail", "bot-a"),),
    "detail_then_reorder": (
        ("update", "two_bots"),
        ("detail", "bot-b"),
        ("update", "two_bots_swapped"),
    ),
    "detail_twice": (
        ("update", "two_bots"),
        ("detail", "bot-b"),
        ("detail", "bot-a"),
    ),
    "refusal_then_update": (
        ("update", "pool_color_none"),
        ("update", "two_bots"),
    ),
    "select_then_refusal": (
        ("update", "two_bots"),
        ("select", 1),
        ("update", "stats_none"),
    ),
}

PICTURE_CASES = ("happy", "two_bots", "three_bots", "all_states", "empty")

# The keys the widget can report for a button. The action a click runs is
# a wiring, not a property of the button, so it is compared where the
# wiring is compared.
COMPARED_BUTTON_KEYS = (
    "kind",
    "text",
    "enabled",
    "height",
    "style_sheet",
    "tooltip",
    "focus_policy",
)


# ---------------------------------------------------------------------
# The two shared registers the drive touches, each put back after
# ---------------------------------------------------------------------


class NoAssetManager:
    """An icon store that holds nothing, so no drive reaches a disk."""

    def get(self):
        """The store the icon builder asks for. Never built."""
        return None


@pytest.fixture(autouse=True)
def no_icon_store(monkeypatch):
    """Give this test its own icon store and put the shared one back.

    The real store builds a logo cache directory under the operator's
    home on first use. Every drive here paints the lettered circle the
    icon builder falls back to instead.
    """
    from src.gui import bot_wizard

    monkeypatch.setattr(bot_wizard, "_ASSET_MANAGER", NoAssetManager())


@pytest.fixture(autouse=True)
def own_bridge_model():
    """Give this test its own bridge model and put the shared one back."""
    original = surface.PANE_MODEL
    surface.PANE_MODEL = surface.ExtractorBotTableModel()
    yield
    surface.PANE_MODEL = original


# ---------------------------------------------------------------------
# Reading the two sides into one shape
# ---------------------------------------------------------------------


def app():
    """The process application object every render needs."""
    from qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


def guarded(run):
    """Run one drive, keeping either what it returned or how it refused."""
    try:
        return {"error": "", "message": "", "answer": run()}
    except Exception as exc:
        return {"error": type(exc).__name__, "message": str(exc), "answer": None}


def digest(body):
    """One case's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def picture_digest(image):
    """One render as a single hash, so a whole window compares in one line."""
    return hashlib.sha256(bytes(image.constBits())).hexdigest()


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def read_old_table(table):
    """The shipped table's whole state, read off the widget."""
    rows = []
    for row in range(table.rowCount()):
        cells = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                cells.append(None)
                continue
            cells.append(
                {
                    "text": item.text(),
                    "type": item.type(),
                    "align": int(item.textAlignment()),
                    "color": item.foreground().color().name(),
                    "brush": item.foreground().style().name,
                    "tooltip": item.toolTip(),
                    "icon": not item.icon().isNull(),
                }
            )
        buttons = {}
        for column in surface.BUTTON_COLUMNS:
            found = table.cellWidget(row, column)
            buttons[str(column)] = (
                None
                if found is None
                else {
                    "kind": found.metaObject().className(),
                    "text": found.text(),
                    "enabled": found.isEnabled(),
                    "height": found.minimumHeight(),
                    "style_sheet": found.styleSheet(),
                    "tooltip": found.toolTip(),
                    "focus_policy": found.focusPolicy().name,
                }
            )
        rows.append({"cells": cells, "buttons": buttons})
    return {
        "rows": rows,
        "row_count": table.rowCount(),
        "current_row": table.currentRow(),
        "selected_items": len(table.selectedItems()),
        "selected_bot_id": table.get_selected_bot_id(),
        "bot_ids": list(table._bot_ids),
        "column_count": table.columnCount(),
        "headers": [
            table.horizontalHeaderItem(column).text()
            for column in range(table.columnCount())
        ],
        "header_tooltips": [
            table.horizontalHeaderItem(column).toolTip()
            for column in range(table.columnCount())
        ],
        "fixed_column_widths": {
            str(column): table.columnWidth(column)
            for column in surface.COLUMN_FIXED_WIDTHS
        },
        "style_sheet": table.styleSheet(),
        "accessible_name": table.accessibleName(),
    }


def read_new_model(model):
    """The surface model's whole state in the same shape."""
    rows = []
    for built in model.rows:
        if built is None:
            rows.append(
                {
                    "cells": [None] * surface.COLUMN_COUNT,
                    "buttons": {str(column): None for column in surface.BUTTON_COLUMNS},
                }
            )
            continue
        cells = []
        for column in range(surface.COLUMN_COUNT):
            if column in surface.BUTTON_COLUMNS:
                cells.append(None)
                continue
            cells.append(
                {
                    "text": built["texts"][column],
                    "type": built["types"][column],
                    "align": built["alignments"][column],
                    "color": built["colors"][column],
                    "brush": built["brushes"][column],
                    "tooltip": built["tooltips"][column],
                    "icon": built["icons"][column],
                }
            )
        buttons = {
            key: {name: spec[name] for name in COMPARED_BUTTON_KEYS}
            for key, spec in built["buttons"].items()
        }
        rows.append({"cells": cells, "buttons": buttons})
    return {
        "rows": rows,
        "row_count": model.row_count,
        "current_row": model.current_row,
        "selected_items": model.selected_item_count,
        "selected_bot_id": model.get_selected_bot_id(),
        "bot_ids": model.bot_ids,
        "column_count": surface.COLUMN_COUNT,
        "headers": list(surface.COLUMN_LABELS),
        "header_tooltips": [
            surface.COLUMN_TOOLTIPS[column] for column in range(surface.COLUMN_COUNT)
        ],
        "fixed_column_widths": {
            str(column): width for column, width in surface.COLUMN_FIXED_WIDTHS.items()
        },
        "style_sheet": surface.TABLE_STYLE_SHEET,
        "accessible_name": surface.ACCESSIBLE_NAME,
    }


# ---------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------


def old_table(clicks=None):
    """One real ExtractorBotTable, held so no later read reaches a
    collected widget."""
    app()
    table = shipped.ExtractorBotTable(
        on_bot_clicked=None if clicks is None else clicks.append
    )
    HELD.append(table)
    return table


def new_model(clicks=None):
    """One surface model, wired to the same callback."""
    return surface.ExtractorBotTableModel(
        on_bot_clicked=None if clicks is None else clicks.append
    )


def run_steps(host, steps, is_old):
    """Drive one case's steps through either side's table."""
    seen = []
    for step in steps:
        name = step[0]
        if name == "update":
            seen.append(guarded(lambda case=step[1]: host.update_bots(CASES[case])))
        elif name == "select":
            if is_old:
                host.selectRow(step[1])
            else:
                host.selected_row = step[1]
                host.current_row = step[1]
            seen.append({"error": "", "message": "", "answer": None})
        elif name == "detail":
            seen.append(guarded(lambda bot=step[1]: host._on_detail(bot)))
    return seen


def old_side(name):
    """The shipped table driven over one case, and what it holds after."""
    clicks: list = []
    table = old_table(clicks)
    run = guarded(lambda: table.update_bots(CASES[name]))
    return {"run": run, "state": read_old_table(table), "clicks": clicks}


def new_side(name):
    """The surface model driven over the same case."""
    clicks: list = []
    model = new_model(clicks)
    run = guarded(lambda: model.update_bots(CASES[name]))
    return {"run": run, "state": read_new_model(model), "clicks": clicks}


def old_steps(name):
    """The shipped table driven over one sequence of steps."""
    clicks: list = []
    table = old_table(clicks)
    return {
        "runs": run_steps(table, STEP_CASES[name], is_old=True),
        "state": read_old_table(table),
        "clicks": clicks,
    }


def new_steps(name):
    """The surface model driven over the same sequence of steps."""
    clicks: list = []
    model = new_model(clicks)
    return {
        "runs": run_steps(model, STEP_CASES[name], is_old=False),
        "state": read_new_model(model),
        "clicks": clicks,
    }


# ---------------------------------------------------------------------
# Side by side
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_row_state_is_the_shipped_tables(name):
    """The surface builds a different row than the shipped table."""
    old = old_side(name)
    new = new_side(name)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(STEP_CASES))
def test_the_driven_state_is_the_shipped_tables(name):
    """The surface holds a different state after the same steps."""
    old = old_steps(name)
    new = new_steps(name)
    assert new == old, name
    assert digest(new) == digest(old), name


def test_the_sample_hashes_are_reported():
    """The reported sample hashes are not the hashes the run produced."""
    samples = {
        "case_happy": digest(new_side("happy")),
        "case_all_states": digest(new_side("all_states")),
        "steps_reorder": digest(new_steps("select_then_reorder")),
        "steps_detail": digest(new_steps("detail_on_row")),
    }
    assert samples["case_happy"] == digest(old_side("happy"))
    assert samples["case_all_states"] == digest(old_side("all_states"))
    assert samples["steps_reorder"] == digest(old_steps("select_then_reorder"))
    assert samples["steps_detail"] == digest(old_steps("detail_on_row"))
    assert all(len(value) == 64 for value in samples.values()), samples
    assert len(set(samples.values())) == 4, samples


def test_two_genuinely_different_cases_hash_apart():
    """The hash reports one value for every case, so a match means
    nothing."""
    assert digest(old_side("happy")) != digest(new_side("two_bots"))
    assert digest(old_side("zero")) != digest(new_side("negative"))
    assert digest(old_side("all_states")) != digest(new_side("all_pool_colors"))
    assert digest(old_steps("detail_on_row")) != digest(new_steps("detail_missing_bot"))
    assert digest(new_side("happy")) == digest(old_side("happy"))


def test_one_case_hashes_the_same_twice():
    """The hash moves between two runs of one input, so no match means
    anything."""
    assert digest(new_side("two_bots")) == digest(new_side("two_bots"))
    assert digest(old_side("two_bots")) == digest(old_side("two_bots"))
    assert digest(new_steps("shrink_from_three")) == digest(
        new_steps("shrink_from_three")
    )


# ---------------------------------------------------------------------
# Answered or refused
# ---------------------------------------------------------------------


REFUSED_CASES = {
    "infinity_count": "OverflowError",
    "not_a_number_count": "ValueError",
    "pool_color_none": "AttributeError",
    "pool_color_number": "AttributeError",
    "stats_none": "AttributeError",
    "stats_not_a_dict": "AttributeError",
    "status_not_a_dict": "AttributeError",
    "statuses_not_a_list": "TypeError",
    "text_where_count_belongs": "ValueError",
    "text_where_number_belongs": "ValueError",
}


def test_the_outcome_set_holds_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the input table
    exercises one outcome and proves nothing about the other."""
    outcomes = {name: new_side(name)["run"]["error"] for name in CASES}
    assert outcomes == {name: old_side(name)["run"]["error"] for name in CASES}
    answered = sorted(name for name, error in outcomes.items() if not error)
    refused = sorted(name for name, error in outcomes.items() if error)
    assert answered, outcomes
    assert refused, outcomes
    assert set(refused) == set(REFUSED_CASES), refused
    assert len(refused) == 10
    assert len(answered) == 31
    assert len(answered) + len(refused) == len(CASES)
    assert {outcomes[name] for name in refused} == {
        "AttributeError",
        "OverflowError",
        "TypeError",
        "ValueError",
    }
    assert outcomes["infinity"] == ""
    assert outcomes["not_a_number"] == ""
    assert outcomes["minus_infinity"] == ""


@pytest.mark.parametrize("name", sorted(REFUSED_CASES))
def test_every_refusal_carries_the_shipped_tables_own_words(name):
    """A refusal reads differently on the two sides."""
    old = old_side(name)["run"]
    new = new_side(name)["run"]
    assert new["error"] == old["error"] == REFUSED_CASES[name], name
    assert new["message"] == old["message"], name
    assert new["message"], name


def test_a_refusal_leaves_the_same_half_written_table_on_both_sides():
    """A refusal part way through a rewrite leaves a different table."""
    statuses = [status(), status(bot_id="bot-b", pool_color=None)]
    old = old_table()
    new = new_model()
    old_run = guarded(lambda: old.update_bots(statuses))
    new_run = guarded(lambda: new.update_bots(statuses))
    assert old_run["error"] == new_run["error"] == "AttributeError"
    assert old.rowCount() == new.row_count == 2
    assert old.item(0, 0).text() == "bot-a"
    assert old.item(1, 0) is None
    assert new.rows[1] is None
    assert new.built_row_count == 1
    assert read_new_model(new) == read_old_table(old)
    assert list(old._bot_ids) == new.bot_ids == ["bot-a", "bot-b"]


def test_a_refused_row_carries_no_highlight_on_either_side():
    """A row with no cell took the highlight, which reads as no bot."""
    old = old_table()
    new = new_model()
    statuses = [status(bot_id="bot-a", pool_color=None)]
    guarded(lambda: old.update_bots(statuses))
    guarded(lambda: new.update_bots(statuses))
    old.selectRow(0)
    new.selected_row = 0
    new.current_row = 0
    assert old.get_selected_bot_id() == ""
    assert new.get_selected_bot_id() == ""
    assert len(old.selectedItems()) == 0
    assert new.selected_item_count == 0


# ---------------------------------------------------------------------
# What the two sides do, value by value
# ---------------------------------------------------------------------


def test_the_headers_and_their_tooltips_are_the_shipped_tables():
    """A header label or its tooltip moved on one side."""
    table = old_table()
    assert list(surface.COLUMN_LABELS) == list(shipped.EXTRACTOR_COLUMNS.labels)
    assert surface.COLUMN_TOOLTIPS == dict(shipped.EXTRACTOR_COLUMNS.tooltips)
    assert surface.COLUMN_FIXED_WIDTHS == dict(shipped.EXTRACTOR_COLUMNS.fixed_widths)
    assert surface.COLUMN_COUNT == table.columnCount() == 8
    assert surface.COLUMN_LABELS[surface.COL_POOL] == "Pool"
    assert surface.COLUMN_LABELS[surface.COL_LIQUID] == "Liquid"
    assert surface.COLUMN_LABELS[surface.COL_DETAIL] == ""
    for column in range(surface.COLUMN_COUNT):
        assert table.horizontalHeaderItem(column).text() == (
            surface.COLUMN_LABELS[column]
        ), column
        assert table.horizontalHeaderItem(column).toolTip() == (
            surface.COLUMN_TOOLTIPS[column]
        ), column


def test_the_fixed_column_widths_are_the_shipped_tables():
    """A fixed column width moved on one side."""
    table = old_table()
    assert surface.COLUMN_FIXED_WIDTHS[surface.COL_FIRE] == FIRE_COLUMN_WIDTH
    assert surface.COLUMN_FIXED_WIDTHS[surface.COL_DETAIL] == DETAIL_COLUMN_WIDTH
    assert table.columnWidth(surface.COL_FIRE) == FIRE_COLUMN_WIDTH
    assert table.columnWidth(surface.COL_DETAIL) == DETAIL_COLUMN_WIDTH
    assert surface.STRETCH_COLUMNS == (0, 1, 2, 3, 4, 5)
    assert set(surface.STRETCH_COLUMNS) & set(surface.COLUMN_FIXED_WIDTHS) == set()
    stretched = [table.columnWidth(column) for column in surface.STRETCH_COLUMNS]
    assert max(stretched) - min(stretched) <= 1, stretched
    assert min(stretched) > max(surface.COLUMN_FIXED_WIDTHS.values()), stretched
    assert sum(stretched) + sum(surface.COLUMN_FIXED_WIDTHS.values()) == (
        sum(table.columnWidth(column) for column in range(surface.COLUMN_COUNT))
    )


def test_every_state_colour_is_the_shipped_tables():
    """A state paints in another state's colour."""
    from PySide6.QtGui import QColor

    app()
    assert sorted(surface.STATE_COLORS) == sorted(
        shipped.ExtractorBotTable.STATE_COLORS
    )
    for name, colour in shipped.ExtractorBotTable.STATE_COLORS.items():
        assert surface.STATE_COLORS[name] == colour.name(), name
    assert surface.STATE_COLORS["running"] == RUNNING_COLOR
    assert surface.STATE_COLORS["idle"] == IDLE_COLOR
    assert surface.STATE_COLORS["paused"] == PAUSED_COLOR
    assert surface.STATE_COLORS["error"] == ERROR_COLOR
    assert surface.STATE_COLORS["cooldown"] == COOLDOWN_COLOR
    assert surface.STATE_COLORS["stopped"] == STOPPED_COLOR
    assert surface.STATE_COLORS["starting"] == STARTING_COLOR
    assert len(surface.STATE_COLORS) == 7
    assert surface.state_color("melting") == surface.STATE_FALLBACK_COLOR
    assert surface.STATE_FALLBACK_COLOR == TEXT_HIGH_COLOR
    assert QColor(TEXT_HIGH_COLOR).name() == TEXT_HIGH_COLOR


def test_every_pool_colour_is_the_shipped_tables():
    """A pool colour name paints in another name's colour."""
    assert sorted(surface.POOL_COLORS) == sorted(shipped.ExtractorBotTable.POOL_COLORS)
    for name, colour in shipped.ExtractorBotTable.POOL_COLORS.items():
        assert surface.POOL_COLORS[name] == colour.name(), name
    assert surface.POOL_COLORS == {
        "green": RUNNING_COLOR,
        "yellow": PAUSED_COLOR,
        "red": ERROR_COLOR,
    }
    assert surface.pool_color("purple") == surface.POOL_FALLBACK_COLOR
    assert surface.POOL_FALLBACK_COLOR == TEXT_MED_COLOR
    assert surface.pool_color(surface.DEFAULT_POOL_COLOR_NAME) == RUNNING_COLOR


def test_the_three_digit_colour_token_is_read_at_the_width_the_screen_shows():
    """A three-digit token compares as a different colour than the screen
    paints, so the idle colour would read as a mismatch."""
    from PySide6.QtGui import QColor

    app()
    assert shipped.ExtractorBotTable.STATE_COLORS["idle"].name() == IDLE_COLOR
    assert QColor(IDLE_SHORT_HEX).name() == IDLE_COLOR
    assert IDLE_SHORT_HEX != IDLE_COLOR
    assert surface.long_hex(IDLE_SHORT_HEX) == IDLE_COLOR
    assert surface.long_hex(IDLE_COLOR) == IDLE_COLOR
    assert surface.long_hex(RUNNING_COLOR) == RUNNING_COLOR
    assert surface.long_hex("") == ""
    assert surface.long_hex("red") == "red"
    assert surface.STATE_COLORS["idle"] == IDLE_COLOR


def test_the_idle_colour_carries_three_equal_channels():
    """The idle colour has an unequal channel, so a swap of two of its
    channels would move a pixel and the picture would carry the claim."""
    from PySide6.QtGui import QColor

    app()
    found = QColor(surface.STATE_COLORS["idle"])
    assert found.red() == found.green() == found.blue()
    other = QColor(surface.STATE_COLORS["running"])
    assert len({other.red(), other.green(), other.blue()}) > 1


def test_the_pool_and_liquid_texts_are_the_shipped_tables():
    """A dollar figure is written differently on one side."""
    driven = new_side("happy")["state"]["rows"][0]["cells"]
    assert driven[surface.COL_POOL]["text"] == "$100.00"
    assert driven[surface.COL_LIQUID]["text"] == "$50.00"
    assert surface.pool_amount_text(100.0, 100.0) == "$100.00"
    assert surface.pool_amount_text(1234567.5, 1.0) == "$1,234,567.50"
    assert surface.pool_amount_text(5.0, 0.0) == surface.NO_VALUE_TEXT
    assert surface.pool_amount_text(5.0, -1.0) == surface.NO_VALUE_TEXT
    assert surface.NO_VALUE_TEXT == "---"
    zero = old_side("zero")["state"]["rows"][0]["cells"]
    assert zero[surface.COL_POOL]["text"] == "---"
    assert zero[surface.COL_LIQUID]["text"] == "---"


def test_the_deployment_split_is_the_shipped_tables():
    """The undeployed dollars are priced differently on one side."""
    assert surface.deployment_split(100.0, 1.0, 2.0) == (1.0, 50.0, 50.0)
    assert surface.deployment_split(100.0, 9.0, 2.0) == (0.0, 450.0, 0.0)
    assert surface.deployment_split(100.0, 1.0, 0.0) == (0.0, 0.0, 0.0)
    assert surface.deployment_split(100.0, 1.0, -2.0) == (0.0, 0.0, 0.0)
    driven = new_side("free_over_size")["state"]["rows"][0]["cells"]
    assert driven[surface.COL_LIQUID]["text"] == "$450.00"
    assert old_side("free_over_size")["state"]["rows"][0]["cells"] == driven


def test_the_mode_cell_is_the_shipped_tables():
    """The Mode cell text, colour or tooltip moved on one side."""
    for name in ("happy", "all_states", "state_empty", "state_unknown"):
        old = old_side(name)["state"]["rows"]
        new = new_side(name)["state"]["rows"]
        assert new == old, name
    driven = new_side("happy")["state"]["rows"][0]["cells"][surface.COL_MODE]
    assert driven["text"] == surface.MODE_TEXT == "extractor"
    assert driven["color"] == RUNNING_COLOR
    assert driven["brush"] == surface.SET_BRUSH
    assert "State: RUNNING" in driven["tooltip"]
    assert surface.mode_tooltip("") == surface.mode_tooltip(None)
    assert surface.UNKNOWN_STATE_TEXT in surface.mode_tooltip("")


def test_the_liquid_tooltip_is_the_shipped_tables():
    """The Liquid tooltip lost a line or a figure on one side."""
    driven = new_side("happy")["state"]["rows"][0]["cells"][surface.COL_LIQUID]
    assert driven["tooltip"].splitlines() == [
        "Extractor pool: YELLOW",
        "  • 1 position(s) open",
        "  • 0 in drawdown",
        "  • BTC base currency",
        "  • 1.00000000 BTC free (50.00 USD)",
        "  • 1.00000000 BTC deployed (50.00 USD)",
    ]
    assert driven["color"] == PAUSED_COLOR
    assert old_side("happy")["state"]["rows"][0]["cells"][surface.COL_LIQUID] == driven


def test_only_the_mode_and_liquid_cells_carry_a_colour():
    """A cell was painted a colour the shipped table leaves alone."""
    for row in new_side("two_bots")["state"]["rows"]:
        for column in range(surface.COLUMN_COUNT):
            cell = row["cells"][column]
            if cell is None:
                assert column in surface.BUTTON_COLUMNS, column
                continue
            if column in surface.COLOURED_COLUMNS:
                assert cell["brush"] == surface.SET_BRUSH, column
                assert cell["color"] != surface.UNSET_COLOR, column
            else:
                assert cell["brush"] == surface.UNSET_BRUSH, column
                assert cell["color"] == surface.UNSET_COLOR, column
                assert cell["tooltip"] == surface.EMPTY_TIP, column
    assert surface.COLOURED_COLUMNS == (surface.COL_MODE, surface.COL_LIQUID)


def test_the_symbol_cell_carries_the_coin_icon_on_both_sides():
    """The coin icon appeared on one side and not the other."""
    old = old_side("happy")["state"]["rows"][0]["cells"]
    new = new_side("happy")["state"]["rows"][0]["cells"]
    assert old[surface.COL_SYMBOL]["icon"] is True
    assert new[surface.COL_SYMBOL]["icon"] is True
    assert old[surface.COL_BOT_ID]["icon"] is False
    for name in ("both_names_empty", "number_where_text_belongs"):
        assert (
            old_side(name)["state"]["rows"][0]["cells"][surface.COL_SYMBOL]["icon"]
            is False
        ), name
        assert (
            new_side(name)["state"]["rows"][0]["cells"][surface.COL_SYMBOL]["icon"]
            is False
        ), name
    assert surface.ICON_COLUMN == surface.COL_SYMBOL == 1
    assert surface.icon_shown("BTC") is True
    assert surface.icon_shown("") is False
    assert surface.icon_shown(7) is False


def test_the_icon_watcher_sees_an_icon_the_store_would_have_built():
    """The icon store stub blinded the icon check, so every cell reads
    as carrying no icon whatever the table painted."""
    from src.gui.bot_wizard import _get_coin_icon

    app()
    assert _get_coin_icon("BTC", 18, download=False) is not None
    assert _get_coin_icon("BTC", 18, download=False).isNull() is False
    assert old_side("happy")["state"]["rows"][0]["cells"][1]["icon"] is True


def test_a_number_written_into_a_text_column_shows_nothing_on_both_sides():
    """A number in a text column shows as a number on one side."""
    old = old_side("number_where_text_belongs")["state"]["rows"][0]["cells"]
    new = new_side("number_where_text_belongs")["state"]["rows"][0]["cells"]
    assert old == new
    assert old[surface.COL_BOT_ID]["text"] == ""
    assert old[surface.COL_BOT_ID]["type"] == 7
    assert surface.cell_text(7) == ""
    assert surface.cell_text("BTC") == "BTC"
    assert surface.cell_type(7) == 7
    assert surface.cell_type("BTC") == surface.UNSET_ITEM_TYPE == 0
    assert surface.cell_type(None) == 0
    assert old[surface.COL_MODE]["text"] == surface.MODE_TEXT


def test_the_two_buttons_are_the_shipped_tables():
    """A button lost its label, its look, its tooltip or its focus."""
    old = old_side("happy")["state"]["rows"][0]["buttons"]
    new = new_side("happy")["state"]["rows"][0]["buttons"]
    assert new == old
    assert old["6"]["text"] == surface.FIRE_LABEL == "Fire"
    assert old["6"]["enabled"] is False
    assert old["6"]["focus_policy"] == surface.FIRE_FOCUS_POLICY == "NoFocus"
    assert old["6"]["style_sheet"] == surface.FIRE_STYLE_SHEET
    assert PLACEHOLDER_COLOR in surface.FIRE_STYLE_SHEET
    assert old["7"]["text"] == surface.DETAIL_LABEL == "Detail"
    assert old["7"]["enabled"] is True
    assert old["7"]["focus_policy"] == surface.DETAIL_FOCUS_POLICY == "StrongFocus"
    assert old["7"]["style_sheet"] == surface.DETAIL_STYLE_SHEET
    assert old["6"]["height"] == old["7"]["height"] == surface.BUTTON_HEIGHT == 22
    assert surface.buttons()["7"]["action"] == "_on_detail"
    assert surface.buttons()["6"]["action"] == ""


def test_the_fire_button_is_disabled_on_every_row_of_both_sides():
    """A Fire button came up live on a row of one side."""
    old = old_side("three_bots")["state"]["rows"]
    new = new_side("three_bots")["state"]["rows"]
    assert len(old) == len(new) == 3
    for row in range(3):
        assert old[row]["buttons"]["6"]["enabled"] is False, row
        assert new[row]["buttons"]["6"]["enabled"] is False, row
        assert old[row]["buttons"]["7"]["enabled"] is True, row
        assert new[row]["buttons"]["7"]["enabled"] is True, row
    assert surface.FIRE_ENABLED is False
    assert surface.DETAIL_ENABLED is True


def test_the_highlight_follows_the_bot_and_not_the_row():
    """The highlight stayed on a row while another bot moved under it."""
    old = old_table()
    new = new_model()
    old.update_bots(TWO_BOTS)
    new.update_bots(TWO_BOTS)
    old.selectRow(1)
    new.selected_row = 1
    new.current_row = 1
    assert old.get_selected_bot_id() == new.get_selected_bot_id() == "bot-b"
    old.update_bots(TWO_BOTS_SWAPPED)
    new.update_bots(TWO_BOTS_SWAPPED)
    assert old.get_selected_bot_id() == "bot-b"
    assert new.get_selected_bot_id() == "bot-b"
    assert old.currentRow() == new.current_row == 0
    assert new.select_path == surface.SELECT_PATH_MOVED


def test_a_bot_that_left_the_fleet_clears_the_highlight_on_both_sides():
    """The highlight stayed on a row whose bot is gone."""
    old = old_table()
    new = new_model()
    old.update_bots(TWO_BOTS)
    new.update_bots(TWO_BOTS)
    old.selectRow(1)
    new.selected_row = 1
    new.current_row = 1
    old.update_bots(CASES["happy"])
    new.update_bots(CASES["happy"])
    assert old.get_selected_bot_id() == new.get_selected_bot_id() == ""
    assert old.currentRow() == new.current_row == surface.NO_ROW == -1
    assert len(old.selectedItems()) == new.selected_item_count == 0
    assert new.select_path == surface.SELECT_PATH_CLEARED


def test_a_steady_fleet_leaves_the_highlight_untouched_on_both_sides():
    """The steady refresh moved the highlight the operator set."""
    old = old_table()
    new = new_model()
    old.update_bots(TWO_BOTS)
    new.update_bots(TWO_BOTS)
    old.selectRow(0)
    new.selected_row = 0
    new.current_row = 0
    old.update_bots(TWO_BOTS)
    new.update_bots(TWO_BOTS)
    assert old.get_selected_bot_id() == new.get_selected_bot_id() == "bot-a"
    assert old.currentRow() == new.current_row == 0
    assert new.select_path == surface.SELECT_PATH_KEPT
    assert len(old.selectedItems()) == new.selected_item_count
    assert new.selected_item_count == surface.ITEMS_PER_SELECTED_ROW == 6


def test_nothing_selected_stays_nothing_selected_on_both_sides():
    """The refresh chose a bot on the operator's behalf."""
    old = old_table()
    new = new_model()
    old.update_bots(TWO_BOTS)
    new.update_bots(TWO_BOTS)
    assert old.get_selected_bot_id() == new.get_selected_bot_id() == ""
    assert old.currentRow() == new.current_row
    assert len(old.selectedItems()) == new.selected_item_count == 0
    assert new.select_path == surface.SELECT_PATH_NONE
    old.selectRow(0)
    assert old.get_selected_bot_id() == "bot-a"


def test_the_detail_button_selects_its_own_row_on_both_sides():
    """A Detail click left the highlight on another bot's row."""
    old_clicks: list = []
    new_clicks: list = []
    old = old_table(old_clicks)
    new = new_model(new_clicks)
    old.update_bots(TWO_BOTS)
    new.update_bots(TWO_BOTS)
    old._on_detail("bot-b")
    new._on_detail("bot-b")
    assert old.get_selected_bot_id() == new.get_selected_bot_id() == "bot-b"
    assert old.currentRow() == new.current_row == 1
    assert old_clicks == new_clicks == ["bot-b"]
    assert new.detail_path == surface.DETAIL_PATH_SELECTED


def test_a_detail_click_for_a_bot_that_is_gone_still_reaches_the_tab():
    """The tab was never told about a click on a row that moved."""
    old_clicks: list = []
    new_clicks: list = []
    old = old_table(old_clicks)
    new = new_model(new_clicks)
    old.update_bots(TWO_BOTS)
    new.update_bots(TWO_BOTS)
    old._on_detail("gone")
    new._on_detail("gone")
    assert old_clicks == new_clicks == ["gone"]
    assert old.get_selected_bot_id() == new.get_selected_bot_id() == ""
    assert new.detail_path == surface.DETAIL_PATH_ABSENT


def test_a_detail_click_with_no_bot_named_moves_no_highlight():
    """A blank bot name moved the highlight to some row."""
    old_clicks: list = []
    new_clicks: list = []
    old = old_table(old_clicks)
    new = new_model(new_clicks)
    old.update_bots(TWO_BOTS)
    new.update_bots(TWO_BOTS)
    old._on_detail("")
    new._on_detail("")
    assert old.get_selected_bot_id() == new.get_selected_bot_id() == ""
    assert old_clicks == new_clicks == [""]
    assert new.detail_path == surface.DETAIL_PATH_BLANK


def test_a_table_with_no_callback_wired_still_moves_its_highlight():
    """A table with no tab behind it stopped selecting its own row."""
    old = old_table()
    new = new_model()
    old.update_bots(TWO_BOTS)
    new.update_bots(TWO_BOTS)
    old._on_detail("bot-b")
    new._on_detail("bot-b")
    assert old.get_selected_bot_id() == new.get_selected_bot_id() == "bot-b"
    assert new.detail_calls == []


def test_every_step_case_reaches_a_path_the_surface_names():
    """A path the surface names is never the branch that ran."""
    reached = {"select": set(), "detail": set()}
    for name in STEP_CASES:
        model = new_model([])
        run_steps(model, STEP_CASES[name], is_old=False)
        reached["select"].add(model.select_path)
        if model.detail_path:
            reached["detail"].add(model.detail_path)
    assert reached["select"] == set(surface.SELECT_PATHS)
    assert reached["detail"] == set(surface.DETAIL_PATHS)
    assert len(surface.SELECT_PATHS) == 4
    assert len(surface.DETAIL_PATHS) == 3


def test_the_recorded_calls_are_compared_as_values():
    """A step the table takes stopped being recorded, or moved in
    order."""
    clicks: list = []
    model = new_model(clicks)
    model.update_bots(TWO_BOTS)
    assert model.calls[0] == [surface.UPDATE_START, ""]
    assert model.calls[1] == [surface.UPDATE_ROW, 0, "bot-a"]
    assert model.calls[2] == [surface.UPDATE_ROW, 1, "bot-b"]
    assert model.calls[3] == [
        surface.UPDATE_REANCHOR,
        surface.SELECT_PATH_NONE,
        surface.NO_ROW,
    ]
    assert model.calls[4] == [surface.UPDATE_RETURN, surface.SELECT_PATH_NONE, 2]
    model._on_detail("bot-b")
    assert model.calls[5] == [surface.DETAIL_START, "bot-b"]
    assert model.calls[6] == [surface.DETAIL_SELECT, surface.DETAIL_PATH_SELECTED, 1]
    assert model.calls[7] == [surface.DETAIL_CALLBACK, "bot-b"]
    assert model.calls[8] == [
        surface.DETAIL_RETURN,
        surface.DETAIL_PATH_SELECTED,
        "bot-b",
    ]
    model.update_bots(TWO_BOTS_SWAPPED)
    assert model.calls[9] == [surface.UPDATE_START, "bot-b"]
    assert model.calls[-2] == [
        surface.UPDATE_REANCHOR,
        surface.SELECT_PATH_MOVED,
        0,
    ]
    assert model.calls[-1] == [surface.UPDATE_RETURN, surface.SELECT_PATH_MOVED, 2]
    assert len(model.calls) == 14


def test_the_row_map_is_read_back_as_a_copy():
    """Changing the answer changes the map the table holds."""
    model = new_model()
    model.update_bots(TWO_BOTS)
    copy = model.bot_ids
    copy.append("changed")
    assert model.bot_ids == ["bot-a", "bot-b"]
    assert len(model.bot_ids) == 2


def test_the_payload_rows_are_read_back_as_copies():
    """Changing a payload row changes the row the model holds."""
    model = new_model()
    model.update_bots(TWO_BOTS)
    payload = surface.build_payload(model)
    payload["rows"][0]["bot_id"] = "changed"
    payload["bot_ids"].append("changed")
    assert surface.build_payload(model)["rows"][0]["bot_id"] == "bot-a"
    assert surface.build_payload(model)["bot_ids"] == ["bot-a", "bot-b"]


def test_a_two_hundred_character_name_survives_whole_on_both_sides():
    """A long name was cut short on one side."""
    old = old_side("long_text")["state"]["rows"][0]["cells"]
    new = new_side("long_text")["state"]["rows"][0]["cells"]
    assert old == new
    assert len(old[surface.COL_BOT_ID]["text"]) == 200
    assert old[surface.COL_BOT_ID]["text"] == LONG_TEXT


def test_markup_and_an_apostrophe_reach_the_cell_unchanged_on_both_sides():
    """Markup or an apostrophe was rewritten on one side."""
    for name, text in (("markup", MARKUP_TEXT), ("apostrophe", APOSTROPHE_TEXT)):
        old = old_side(name)["state"]["rows"][0]["cells"]
        new = new_side(name)["state"]["rows"][0]["cells"]
        assert old == new, name
        assert old[surface.COL_BOT_ID]["text"] == text, name
    assert "<script>" in MARKUP_TEXT
    assert "'" in APOSTROPHE_TEXT


def test_a_newline_inside_a_name_reaches_the_cell_on_both_sides():
    """A name holding a line break was flattened on one side."""
    old = old_side("newline_name")["state"]["rows"][0]["cells"]
    new = new_side("newline_name")["state"]["rows"][0]["cells"]
    assert old == new
    assert old[surface.COL_BOT_ID]["text"] == NEWLINE_TEXT
    assert "\n" in old[surface.COL_BOT_ID]["text"]


def test_the_endless_and_the_not_a_number_figures_read_alike_on_both_sides():
    """An endless or a not-a-number figure is written differently on one
    side."""
    endless = new_side("infinity")["state"]["rows"][0]["cells"]
    assert endless == old_side("infinity")["state"]["rows"][0]["cells"]
    assert endless[surface.COL_POOL]["text"] == "$inf"
    assert endless[surface.COL_LIQUID]["text"] == "$nan"
    minus = new_side("minus_infinity")["state"]["rows"][0]["cells"]
    assert minus == old_side("minus_infinity")["state"]["rows"][0]["cells"]
    assert minus[surface.COL_POOL]["text"] == surface.NO_VALUE_TEXT
    blank = new_side("not_a_number")["state"]["rows"][0]["cells"]
    assert blank == old_side("not_a_number")["state"]["rows"][0]["cells"]
    assert blank[surface.COL_POOL]["text"] == surface.NO_VALUE_TEXT


def test_a_thousand_million_and_one_billionth_read_alike_on_both_sides():
    """A very large or a very small figure is written differently on one
    side."""
    big = new_side("thousand_million")["state"]["rows"][0]["cells"]
    assert big == old_side("thousand_million")["state"]["rows"][0]["cells"]
    assert big[surface.COL_POOL]["text"] == "$1,000,000,000.00"
    assert "1000000000" in big[surface.COL_LIQUID]["tooltip"]
    small = new_side("one_billionth")["state"]["rows"][0]["cells"]
    assert small == old_side("one_billionth")["state"]["rows"][0]["cells"]
    assert small[surface.COL_POOL]["text"] == "$0.00"
    assert "0.00000000" in small[surface.COL_LIQUID]["tooltip"]


def test_the_wrong_capitals_take_the_fallback_colour_on_both_sides():
    """A state or pool name in the wrong capitals still found its
    colour, so the lookup is not the exact-match one the table has."""
    state_row = new_side("wrong_capitals_state")["state"]["rows"][0]["cells"]
    assert state_row == old_side("wrong_capitals_state")["state"]["rows"][0]["cells"]
    assert state_row[surface.COL_MODE]["color"] == surface.STATE_FALLBACK_COLOR
    pool_row = new_side("wrong_capitals_pool")["state"]["rows"][0]["cells"]
    assert pool_row == old_side("wrong_capitals_pool")["state"]["rows"][0]["cells"]
    assert pool_row[surface.COL_LIQUID]["color"] == surface.POOL_FALLBACK_COLOR
    assert surface.state_color("running") != surface.STATE_FALLBACK_COLOR


def test_a_missing_status_key_takes_the_shipped_tables_own_default():
    """A missing key reads as a different default on one side."""
    old = old_side("missing_keys")["state"]["rows"][0]["cells"]
    new = new_side("missing_keys")["state"]["rows"][0]["cells"]
    assert old == new
    assert old[surface.COL_BOT_ID]["text"] == surface.MISSING_TEXT == ""
    assert old[surface.COL_TRADES]["text"] == "0"
    assert old[surface.COL_POOL]["text"] == surface.NO_VALUE_TEXT
    assert old[surface.COL_LIQUID]["color"] == surface.POOL_COLORS["green"]
    assert surface.DEFAULT_POOL_COLOR_NAME == "green"


def test_the_symbol_stands_in_when_there_is_no_base_currency():
    """The Symbol cell fell back to the wrong value on one side."""
    old = old_side("symbol_fallback")["state"]["rows"][0]["cells"]
    new = new_side("symbol_fallback")["state"]["rows"][0]["cells"]
    assert old == new
    assert old[surface.COL_SYMBOL]["text"] == "ETH"
    both_empty = new_side("both_names_empty")["state"]["rows"][0]["cells"]
    assert both_empty[surface.COL_SYMBOL]["text"] == ""


def test_the_table_takes_the_parent_the_caller_gives_it():
    """A parent the caller passed was dropped."""
    from PySide6.QtWidgets import QWidget

    app()
    owner = QWidget()
    HELD.append(owner)
    table = shipped.ExtractorBotTable(parent=owner)
    HELD.append(table)
    model = surface.ExtractorBotTableModel(parent=owner)
    assert table.parent() is owner
    assert model.parent is owner
    assert surface.ExtractorBotTableModel().parent is None
    assert old_table().parent() is None


# ---------------------------------------------------------------------
# The window the table paints
# ---------------------------------------------------------------------


def sealed_payload(name):
    """One case's payload, stamped as it comes off the surface."""
    model = surface.ExtractorBotTableModel()
    model.update_bots(CASES[name])
    return sealed(surface.build_payload(model))


def table_painted_by_the_payload(payload):
    """A table built only from the surface's payload, ready to render."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QHeaderView,
        QPushButton,
        QTableWidget,
        QTableWidgetItem,
    )

    from src.gui.bot_wizard import _get_coin_icon

    payload = unaltered(payload)
    app()
    table = QTableWidget()
    HELD.append(table)
    table.setColumnCount(payload["column_count"])
    table.setHorizontalHeaderLabels(payload["column_labels"])
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    for column, width in payload["column_fixed_widths"].items():
        header.setSectionResizeMode(int(column), QHeaderView.Fixed)
        table.setColumnWidth(int(column), width)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    for column, tip in payload["column_tooltips"].items():
        found = table.horizontalHeaderItem(int(column))
        if found:
            found.setToolTip(tip)
    table.setRowCount(payload["row_count"])
    for row, built in enumerate(payload["rows"]):
        if built is None:
            continue
        for column in payload["text_columns"]:
            item = QTableWidgetItem(built["texts"][column])
            item.setTextAlignment(Qt.AlignmentFlag(payload["alignment_value"]))
            if built["icons"][column]:
                icon = _get_coin_icon(built["texts"][column], 18, download=False)
                if icon:
                    item.setIcon(icon)
            if built["brushes"][column] == payload["set_brush"]:
                item.setForeground(QColor(built["colors"][column]))
            if built["tooltips"][column]:
                item.setToolTip(built["tooltips"][column])
            table.setItem(row, column, item)
        for column in payload["button_columns"]:
            spec = built["buttons"][str(column)]
            button = QPushButton(spec["text"])
            button.setFixedHeight(spec["height"])
            if spec["focus_policy"] == surface.FIRE_FOCUS_POLICY:
                button.setFocusPolicy(Qt.NoFocus)
            button.setEnabled(spec["enabled"])
            button.setStyleSheet(spec["style_sheet"])
            button.setToolTip(spec["tooltip"])
            table.setCellWidget(row, column, button)
    return table


def real_table(name):
    """The shipped table driven over one case, ready to render."""
    table = old_table()
    table.update_bots(CASES[name])
    return table


def render(widget, size=PIXEL_SIZE):
    """One offscreen render of a widget at one size."""
    from qt_pixel import render_widget

    app()
    return render_widget(widget, size)


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_paint_the_same_window(name):
    """The surface paints a different window than the shipped table."""
    assert_pictures_match(
        old_side=render(real_table(name)),
        new_side=render(table_painted_by_the_payload(sealed_payload(name))),
        note=name,
    )


def test_the_picture_check_reports_two_real_inputs_that_really_differ():
    """The picture comparison passes whatever the second side painted."""
    old = render(real_table("happy"))
    new = render(table_painted_by_the_payload(sealed_payload("three_bots")))
    assert colour_count(old) > 1, colour_count(old)
    assert colour_count(new) > 1, colour_count(new)
    assert_pictures_differ(old_side=old, new_side=new, note="one row against three")
    with pytest.raises(AssertionError) as reported:
        assert_pictures_match(old_side=old, new_side=new, note="one row against three")
    assert "different picture" in str(reported.value)
    assert_pictures_match(
        old_side=render(real_table("happy")),
        new_side=render(table_painted_by_the_payload(sealed_payload("happy"))),
        note="one case, both sides",
    )


def test_the_window_carries_more_than_one_colour_so_a_picture_can_report():
    """The table paints one flat colour, so no picture comparison here
    could ever fail and every value must be read instead."""
    painted = colour_count(render(real_table("all_states")))
    assert painted > 1, painted
    assert colour_count(render(real_table("empty"))) > 1
    assert (
        colour_count(render(table_painted_by_the_payload(sealed_payload("all_states"))))
        == painted
    )


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's
    fonts rather than the product."""
    payload = sealed_payload("happy")
    payload["rows"][0]["texts"][surface.COL_BOT_ID] = "changed"
    with pytest.raises(AssertionError) as reported:
        table_painted_by_the_payload(payload)
    assert "altered after it came off" in str(reported.value)
    payload["rows"][0]["texts"][surface.COL_BOT_ID] = "bot-a"
    assert table_painted_by_the_payload(payload) is not None


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves
    nothing."""
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    app()
    metrics = QFontMetrics(QApplication.font())
    narrow = metrics.horizontalAdvance("iiiiiiii")
    wide = metrics.horizontalAdvance("WWWWWWWW")
    if has_real_fonts():
        assert wide > narrow
    else:
        assert wide == narrow


@skip_unless_no_fonts
def test_with_no_font_database_two_equal_length_names_paint_alike():
    """Two different names of one length painted different windows with
    no font database, so the box font is not what this run is drawing."""
    app()
    first = render(real_table("happy"), SMALL_PIXEL_SIZE)
    second = render(
        real_table_with_name("bot-z"),
        SMALL_PIXEL_SIZE,
    )
    assert picture_digest(first) == picture_digest(second)


@skip_unless_real_fonts
def test_with_a_font_database_two_equal_length_names_paint_apart():
    """Two different names of one length painted one window on a run
    holding fonts, so the glyphs are not deciding their own shape."""
    app()
    first = render(real_table("happy"), SMALL_PIXEL_SIZE)
    second = render(real_table_with_name("bot-z"), SMALL_PIXEL_SIZE)
    assert picture_digest(first) != picture_digest(second)


def real_table_with_name(bot_id):
    """The shipped table holding one bot under a given name."""
    table = old_table()
    table.update_bots([status(bot_id=bot_id)])
    return table


# ---------------------------------------------------------------------
# What a picture cannot see
# ---------------------------------------------------------------------


BLIND_TO_THE_PICTURE = {
    "header_tooltips": "test_the_headers_and_their_tooltips_are_the_shipped_tables",
    "mode_tooltip": "test_the_mode_cell_is_the_shipped_tables",
    "liquid_tooltip": "test_the_liquid_tooltip_is_the_shipped_tables",
    "fire_tooltip": "test_the_two_buttons_are_the_shipped_tables",
    "detail_tooltip": "test_the_two_buttons_are_the_shipped_tables",
    "item_type": "test_a_number_written_into_a_text_column_shows_nothing_on_both_sides",
    "focus_policy": "test_the_two_buttons_are_the_shipped_tables",
    "button_action": "test_the_wired_click_runs_the_method_the_surface_names",
    "row_to_bot_map": "test_the_row_map_is_read_back_as_a_copy",
    "selected_bot_id": "test_the_highlight_follows_the_bot_and_not_the_row",
    "cleared_highlight": (
        "test_a_bot_that_left_the_fleet_clears_the_highlight_on_both_sides"
    ),
    "kept_highlight": (
        "test_a_steady_fleet_leaves_the_highlight_untouched_on_both_sides"
    ),
    "detail_callback": "test_the_detail_button_selects_its_own_row_on_both_sides",
    "detail_absent": "test_a_detail_click_for_a_bot_that_is_gone_still_reaches_the_tab",
    "refusal_words": "test_every_refusal_carries_the_shipped_tables_own_words",
    "half_written_table": (
        "test_a_refusal_leaves_the_same_half_written_table_on_both_sides"
    ),
    "recorded_calls": "test_the_recorded_calls_are_compared_as_values",
    "connect_sites": "test_the_connect_sites_match_the_actions",
    "timers": "test_the_table_starts_no_timer",
    "bus_topics": "test_the_table_subscribes_to_no_bus_topic",
    "skin": "test_the_table_declares_no_skin_of_its_own",
    "accessible_name": "test_the_accessible_name_is_compared_as_a_string",
    "bridge_method": "test_bridge_registers_the_extractor_bot_table_method",
    "qt_free_import": "test_the_surface_loads_no_qt_module",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 24
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert colour_count(render(real_table("happy"))) > 1


def test_the_covering_test_names_are_read_from_this_module():
    """A covering name that resolves nowhere reads as covered."""
    assert "test_a_name_this_module_never_defines" not in globals()
    assert "test_the_two_buttons_are_the_shipped_tables" in globals()
    assert callable(globals()["test_the_recorded_calls_are_compared_as_values"])


def test_the_accessible_name_is_compared_as_a_string():
    """The name a screen reader announces moved on one side."""
    assert old_table().accessibleName() == surface.ACCESSIBLE_NAME == ""
    assert shipped.EXTRACTOR_COLUMNS.accessible_name == surface.ACCESSIBLE_NAME


# ---------------------------------------------------------------------
# The counterpart map
# ---------------------------------------------------------------------


CLASS_MAP = {"ExtractorBotTable": "ExtractorBotTableModel"}

METHOD_MAP = {
    "ExtractorBotTable.__init__": "ExtractorBotTableModel.__init__",
    "ExtractorBotTable.update_bots": "ExtractorBotTableModel.update_bots",
    "ExtractorBotTable._on_detail": "ExtractorBotTableModel._on_detail",
    "ExtractorBotTable.get_selected_bot_id": (
        "ExtractorBotTableModel.get_selected_bot_id"
    ),
}

MODEL_MEMBERS = {
    "__init__",
    "bot_ids",
    "built_row_count",
    "selected_item_count",
    "_set_row_count",
    "_resized_rows",
    "_row_has_cell",
    "_row_of_bot",
    "update_bots",
    "_reanchor",
    "_select_row_for_bot",
    "_on_detail",
    "get_selected_bot_id",
}

SURFACE_FUNCTIONS = {
    "long_hex",
    "cell_text",
    "cell_type",
    "icon_shown",
    "state_color",
    "pool_color",
    "pool_amount_text",
    "deployment_split",
    "mode_tooltip",
    "liquid_tooltip",
    "buttons",
    "row_values",
    "build_payload",
    "view_model",
}

VALUE_MAP = {
    "EXTRACTOR_COLUMNS.labels": "COLUMN_LABELS",
    "EXTRACTOR_COLUMNS.tooltips": "COLUMN_TOOLTIPS",
    "EXTRACTOR_COLUMNS.fixed_widths": "COLUMN_FIXED_WIDTHS",
    "ExtractorBotTable.STATE_COLORS": "STATE_COLORS",
    "ExtractorBotTable.POOL_COLORS": "POOL_COLORS",
}


def members(owner):
    """Every method and property a class defines, by name.

    A signal is callable and is not a method, so only a function and a
    property are counted.
    """
    import inspect

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if inspect.isfunction(value) or isinstance(value, property):
            found.add(name)
    return found


def module_classes(module):
    """Every class a module defines, by name."""
    import inspect

    return {
        name
        for name, value in vars(module).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == module.__name__
    }


def module_functions(module):
    """Every function a module defines at its top level, by name."""
    import inspect

    return {
        name
        for name, value in vars(module).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == module.__name__
    }


def resolve(dotted):
    """The member a dotted name in the map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def test_every_shipped_class_and_method_has_a_counterpart():
    """A class or a method exists on one side and nowhere on the other."""
    assert module_classes(shipped) == {"ExtractorBotTable"}
    assert len(module_classes(shipped)) == 1 == len(CLASS_MAP)
    assert set(CLASS_MAP) == module_classes(shipped)
    for target in CLASS_MAP.values():
        assert callable(getattr(surface, target)), target
    assert members(shipped.ExtractorBotTable) == {
        "__init__",
        "update_bots",
        "_on_detail",
        "get_selected_bot_id",
    }
    assert len(members(shipped.ExtractorBotTable)) == 4
    assert {name.split(".")[-1] for name in METHOD_MAP} == members(
        shipped.ExtractorBotTable
    )
    assert len(METHOD_MAP) == 4
    for target in METHOD_MAP.values():
        assert resolve(target) is not None, target
    assert members(surface.ExtractorBotTableModel) == MODEL_MEMBERS
    assert len(MODEL_MEMBERS) == 13
    assert {target.split(".")[-1] for target in METHOD_MAP.values()} < MODEL_MEMBERS
    assert module_functions(shipped) == set()
    assert module_functions(surface) == SURFACE_FUNCTIONS
    assert len(SURFACE_FUNCTIONS) == 14


def test_the_method_counter_leaves_a_signal_out():
    """A signal counts as a method, so a class that trades a method for a
    signal reads as unchanged."""
    from PySide6.QtCore import QObject, Signal

    app()

    class WithSignal(QObject):
        """One signal and one method, so the counter has both to sort."""

        fired = Signal(bool)

        def a_real_method(self):
            """The one member the counter is meant to see."""
            return True

    assert callable(WithSignal.fired)
    assert "fired" in vars(WithSignal)
    assert members(WithSignal) == {"a_real_method"}
    assert "fired" not in members(WithSignal)
    assert len(members(WithSignal)) == 1


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "update_bots" in members(shipped.ExtractorBotTable)
    assert "_on_detail" in members(shipped.ExtractorBotTable)
    assert "QPushButton" not in module_classes(shipped)
    assert "ColumnarTableWidget" not in module_classes(shipped)
    with pytest.raises(AttributeError):
        resolve("ExtractorBotTableModel.no_such_member")
    assert MODEL_MEMBERS - {"update_bots"} != MODEL_MEMBERS
    assert members(surface.ExtractorBotTableModel) - {"_reanchor"} != MODEL_MEMBERS
    assert set(METHOD_MAP) - {"ExtractorBotTable.update_bots"} != set(METHOD_MAP)
    assert SURFACE_FUNCTIONS - {"row_values"} != SURFACE_FUNCTIONS
    assert module_functions(surface) - {"long_hex"} != SURFACE_FUNCTIONS


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the dashboard passes it."""
    import inspect

    for name in sorted(members(shipped.ExtractorBotTable)):
        old = list(
            inspect.signature(getattr(shipped.ExtractorBotTable, name)).parameters
        )
        new = list(
            inspect.signature(getattr(surface.ExtractorBotTableModel, name)).parameters
        )
        assert new == old, name
    assert list(inspect.signature(shipped.ExtractorBotTable.__init__).parameters) == [
        "self",
        "on_bot_clicked",
        "parent",
    ]
    assert list(
        inspect.signature(shipped.ExtractorBotTable.update_bots).parameters
    ) == ["self", "bot_statuses"]
    assert list(inspect.signature(shipped.ExtractorBotTable._on_detail).parameters) == [
        "self",
        "bot_id",
    ]


def test_every_shipped_value_has_a_counterpart():
    """A value the shipped table carries reaches nothing on the surface."""
    assert len(VALUE_MAP) == 5
    for old_name, new_name in VALUE_MAP.items():
        found = shipped
        for part in old_name.split("."):
            found = getattr(found, part)
        assert getattr(surface, new_name) is not None, new_name
    assert list(shipped.EXTRACTOR_COLUMNS.labels) == list(surface.COLUMN_LABELS)
    assert dict(shipped.EXTRACTOR_COLUMNS.tooltips) == surface.COLUMN_TOOLTIPS
    assert len(shipped.ExtractorBotTable.STATE_COLORS) == len(surface.STATE_COLORS)
    assert len(shipped.ExtractorBotTable.POOL_COLORS) == len(surface.POOL_COLORS)
    assert shipped.ExtractorBotTable.COLUMNS == surface.COLUMN_LABELS
    assert shipped.ExtractorBotTable.COLUMN_TOOLTIPS == surface.COLUMN_TOOLTIPS


def count_sites(path, needle):
    """How many times one wiring call appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    assert count_sites(TABLE_PATH, ".connect(") == TABLE_CONNECT_SITES == 1
    assert count_sites(SURFACE_PATH, ".connect(") == 0
    assert len(surface.ACTIONS) == count_sites(TABLE_PATH, ".connect(")
    assert set(surface.ACTIONS) == {"detail.clicked"}
    assert count_sites(TABLE_PATH, "clicked.connect(") == 1
    assert count_sites(TABLE_PATH, "a-call-this-table-never-makes") == 0
    assert count_sites(WIRING_NEIGHBOUR_PATH, ".connect(") > 0


def test_the_wired_click_runs_the_method_the_surface_names():
    """The click the surface names is wired to nothing."""
    clicks: list = []
    table = old_table(clicks)
    table.update_bots(TWO_BOTS)
    assert surface.ACTIONS["detail.clicked"] == "_on_detail"
    assert callable(getattr(shipped.ExtractorBotTable, "_on_detail"))
    assert callable(getattr(surface.ExtractorBotTableModel, "_on_detail"))
    table.cellWidget(1, surface.COL_DETAIL).click()
    assert clicks == ["bot-b"]
    assert table.get_selected_bot_id() == "bot-b"
    model = new_model([])
    model.update_bots(TWO_BOTS)
    model._on_detail("bot-b")
    assert model.get_selected_bot_id() == "bot-b"
    assert surface.buttons()["7"]["action"] == surface.ACTIONS["detail.clicked"]


def test_the_fire_button_is_wired_to_nothing_on_both_sides():
    """The Fire button reached a handler on one side."""
    clicks: list = []
    table = old_table(clicks)
    table.update_bots(TWO_BOTS)
    table.cellWidget(0, surface.COL_FIRE).click()
    assert clicks == []
    assert surface.buttons()["6"]["action"] == ""
    table.cellWidget(0, surface.COL_DETAIL).click()
    assert clicks == ["bot-a"]


def test_the_table_starts_no_timer():
    """A wait appeared on one side and not the other.

    The counter is proved able to report by counting a neighbouring file
    that really does start one, and by starting one under the watcher.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
    assert count_sites(TABLE_PATH, "QTimer") == TABLE_TIMER_SITES == 0
    assert count_sites(SURFACE_PATH, "QTimer") == 0
    assert count_sites(TIMER_NEIGHBOUR_PATH, "QTimer") > 0
    started: list = []
    original_start_timer = QObject.startTimer
    original_timer_start = QTimer.start
    original_single_shot = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return original_start_timer(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return original_timer_start(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", args))
        return original_single_shot(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        for name in ("happy", "three_bots"):
            old_side(name)
            new_side(name)
        observed = list(started)
        started.clear()
        QTimer().start(250)
    finally:
        QObject.startTimer = original_start_timer
        QTimer.start = original_timer_start
        QTimer.singleShot = original_single_shot
    assert started == [("QTimer.start", (250,))]
    assert observed == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(surface.TIMERS) == len(observed) == 0


def test_the_table_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_sites(TABLE_PATH, ".subscribe(") == TABLE_BUS_SITES == 0
    assert count_sites(SURFACE_PATH, ".subscribe(") == 0
    assert count_sites(BUS_NEIGHBOUR_PATH, ".subscribe(") > 0
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_sites(TABLE_PATH, ".subscribe(")


def test_the_table_declares_no_skin_of_its_own():
    """A look the surface ships is one the table never wears."""
    app()
    table = old_table()
    table.update_bots(TWO_BOTS)
    assert surface.SKIN == {}
    assert surface.TABLE_STYLE_SHEET == ""
    assert table.styleSheet() == ""
    assert count_sites(TABLE_PATH, "setStyleSheet(") == 2
    assert table.cellWidget(0, surface.COL_FIRE).styleSheet() == (
        surface.FIRE_STYLE_SHEET
    )
    assert table.cellWidget(0, surface.COL_DETAIL).styleSheet() == (
        surface.DETAIL_STYLE_SHEET
    )
    assert colour_count(render(table)) > 1


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    import ast

    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
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
    assert imported == {"__future__", "typing", "design_system"}
    table_tree = ast.parse(TABLE_PATH.read_text(encoding="utf-8"))
    table_imports = {
        (node.module or "")
        for node in ast.walk(table_tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in table_imports), table_imports


def test_the_surface_file_carries_no_carriage_return():
    """A carriage return reached the file, counted as bytes rather than
    by a line pattern."""
    assert SURFACE_PATH.read_bytes().count(b"\r") == 0
    assert Path(__file__).read_bytes().count(b"\r") == 0
    assert SURFACE_PATH.read_bytes().count(b"\n") > 0


def test_the_shipped_table_is_left_byte_for_byte_alone():
    """The shipped table was edited, so the two sides are one side."""
    body = TABLE_PATH.read_bytes()
    assert len(body.splitlines()) == 278
    assert b"class ExtractorBotTable(ColumnarTableWidget):" in body
    assert b"detail_btn.clicked.connect(" in body
    assert body.count(b"\r") == 0


# ---------------------------------------------------------------------
# Every value reaches the compared snapshot
# ---------------------------------------------------------------------


def normalise(value):
    """One value with every tuple turned into a list."""
    if isinstance(value, (list, tuple)):
        return [normalise(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalise(item) for key, item in value.items()}
    return value


def freeze(value):
    """One value as a single comparable string."""
    return json.dumps(normalise(value), sort_keys=True, default=str)


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
        if isinstance(value, surface.ExtractorBotTableModel):
            continue
        if getattr(value, "__module__", "") in ("typing", "__future__"):
            continue
        if name == "ModelCall":
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
    for name in (
        "happy",
        "empty",
        "all_states",
        "all_pool_colors",
        "zero",
        "missing_keys",
        "number_where_text_belongs",
    ):
        model = surface.ExtractorBotTableModel()
        model.update_bots(CASES[name])
        payloads.append(surface.build_payload(model))
    moved = surface.ExtractorBotTableModel()
    moved.update_bots(TWO_BOTS)
    moved.selected_row = 1
    moved.current_row = 1
    moved.update_bots(TWO_BOTS_SWAPPED)
    payloads.append(surface.build_payload(moved))
    cleared = surface.ExtractorBotTableModel()
    cleared.update_bots(TWO_BOTS)
    cleared.selected_row = 1
    cleared.current_row = 1
    cleared.update_bots(CASES["happy"])
    payloads.append(surface.build_payload(cleared))
    kept = surface.ExtractorBotTableModel()
    kept.update_bots(TWO_BOTS)
    kept.selected_row = 0
    kept.current_row = 0
    kept.update_bots(TWO_BOTS)
    payloads.append(surface.build_payload(kept))
    for bot in ("bot-b", "gone", ""):
        clicked = surface.ExtractorBotTableModel(on_bot_clicked=lambda _bot: None)
        clicked.update_bots(TWO_BOTS)
        clicked._on_detail(bot)
        payloads.append(surface.build_payload(clicked))
    refused = surface.ExtractorBotTableModel()
    guarded(lambda: refused.update_bots(CASES["pool_color_none"]))
    payloads.append(surface.build_payload(refused))
    parented = surface.ExtractorBotTableModel(parent=object())
    payloads.append(surface.build_payload(parented))
    return payloads


COVERED_ELSEWHERE = {
    "SHORT_HEX_LENGTH": (
        "test_the_three_digit_colour_token_is_read_at_the_width_the_screen_shows"
    ),
    "HEX_MARK": (
        "test_the_three_digit_colour_token_is_read_at_the_width_the_screen_shows"
    ),
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
    table."""
    constants = surface_constants()
    assert len(constants) > 55
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
    assert "STATE_COLORS" in slipped
    assert "COLUMN_TOOLTIPS" in slipped
    assert "FIRE_STYLE_SHEET" in slipped
    assert "METHOD" not in slipped


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "logger_name": ("LOGGER_NAME",),
    "accessible_name": ("ACCESSIBLE_NAME",),
    "table_kind": ("TABLE_KIND",),
    "base_kind": ("BASE_KIND",),
    "button_kind": ("BUTTON_KIND",),
    "column_labels": ("COLUMN_LABELS",),
    "column_tooltips": ("COLUMN_TOOLTIPS",),
    "column_fixed_widths": ("COLUMN_FIXED_WIDTHS",),
    "column_count": ("COLUMN_COUNT",),
    "text_columns": ("TEXT_COLUMNS",),
    "button_columns": ("BUTTON_COLUMNS",),
    "coloured_columns": ("COLOURED_COLUMNS",),
    "stretch_columns": ("STRETCH_COLUMNS",),
    "icon_column": ("ICON_COLUMN",),
    "items_per_selected_row": ("ITEMS_PER_SELECTED_ROW",),
    "state_colors": ("STATE_COLORS",),
    "pool_colors": ("POOL_COLORS",),
    "state_fallback_color": ("STATE_FALLBACK_COLOR",),
    "pool_fallback_color": ("POOL_FALLBACK_COLOR",),
    "unset_color": ("UNSET_COLOR",),
    "unset_brush": ("UNSET_BRUSH",),
    "set_brush": ("SET_BRUSH",),
    "unset_item_type": ("UNSET_ITEM_TYPE",),
    "alignment": ("ALIGNMENT",),
    "alignment_value": ("ALIGNMENT_VALUE",),
    "mode_text": ("MODE_TEXT",),
    "unknown_state_text": ("UNKNOWN_STATE_TEXT",),
    "no_value_text": ("NO_VALUE_TEXT",),
    "empty_tip": ("EMPTY_TIP",),
    "default_pool_color_name": ("DEFAULT_POOL_COLOR_NAME",),
    "pool_text_format": ("POOL_TEXT_FORMAT",),
    "mode_tip_format": ("MODE_TIP_FORMAT",),
    "liquid_tip_format": ("LIQUID_TIP_FORMAT",),
    "buttons": ("buttons",),
    "fire_label": ("FIRE_LABEL",),
    "detail_label": ("DETAIL_LABEL",),
    "button_height": ("BUTTON_HEIGHT",),
    "fire_enabled": ("FIRE_ENABLED",),
    "detail_enabled": ("DETAIL_ENABLED",),
    "fire_focus_policy": ("FIRE_FOCUS_POLICY",),
    "detail_focus_policy": ("DETAIL_FOCUS_POLICY",),
    "fire_style_sheet": ("FIRE_STYLE_SHEET",),
    "detail_style_sheet": ("DETAIL_STYLE_SHEET",),
    "fire_tooltip": ("FIRE_TOOLTIP",),
    "detail_tooltip": ("DETAIL_TOOLTIP",),
    "table_style_sheet": ("TABLE_STYLE_SHEET",),
    "skin": ("SKIN",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "bus_topics": ("BUS_TOPICS",),
    "actions": ("ACTIONS",),
    "bridge_actions": ("BRIDGE_ACTIONS",),
    "status_keys": ("STATUS_KEYS",),
    "trades_key": ("TRADES_KEY",),
    "missing_text": ("MISSING_TEXT",),
    "missing_amount": ("MISSING_AMOUNT",),
    "missing_count": ("MISSING_COUNT",),
    "no_deployment": ("NO_DEPLOYMENT",),
    "no_row": ("NO_ROW",),
    "no_bot": ("NO_BOT",),
    "first_column": ("FIRST_COLUMN",),
    "select_paths": ("SELECT_PATHS",),
    "detail_paths": ("DETAIL_PATHS",),
    "rows": ("model.rows",),
    "built_row_count": ("model.built_row_count",),
    "bot_ids": ("model.bot_ids",),
    "row_count": ("model.row_count",),
    "current_row": ("model.current_row",),
    "selected_row": ("model.selected_row",),
    "selected_item_count": ("model.selected_item_count",),
    "selected_bot_id": ("model.get_selected_bot_id",),
    "select_path": ("model.select_path",),
    "detail_path": ("model.detail_path",),
    "detail_calls": ("model.detail_calls",),
    "has_parent": ("model.parent",),
    "calls": ("model.calls",),
}


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("model."):
        found = getattr(model, name.split(".", 1)[1])
    else:
        found = getattr(surface, name)
    return found() if callable(found) else found


def backed(key, value, sources, model):
    """Whether one payload key carries exactly what its named sources
    hold."""
    if key == "has_parent":
        return value is (model.parent is not None)
    resolved = [resolve_source(name, model) for name in sources]
    if len(sources) == 1:
        return freeze(value) == freeze(resolved[0])
    return [freeze(item) for item in value] == [freeze(item) for item in resolved]


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model = surface.ExtractorBotTableModel()
    model.update_bots(TWO_BOTS)
    model._on_detail("bot-b")
    payload = surface.build_payload(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES)
    assert len(payload) == 77
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(model, name.split(".", 1)[1]), name
            else:
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, model), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = surface.ExtractorBotTableModel()
    model.update_bots(TWO_BOTS)
    payload = surface.build_payload(model)
    assert backed("state_colors", payload["state_colors"], ("STATE_COLORS",), model)
    assert not backed("state_colors", {"running": "#000000"}, ("STATE_COLORS",), model)
    assert not backed("column_labels", ["one"], ("COLUMN_LABELS",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("row_count", 99, ("model.row_count",), model)
    assert not backed("bot_ids", ["nobody"], ("model.bot_ids",), model)
    assert not backed("has_parent", True, ("model.parent",), model)


# ---------------------------------------------------------------------
# The values are the surface's own, not the shipped table's
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_table():
    """The surface reads the shipped table, so the two can never
    disagree.

    The change is proved to have reached the screen by a render, because
    a colour read back off a cell is what the cell was told to paint and
    not what it painted.
    """
    from PySide6.QtGui import QColor

    from src.gui.widgets import ColumnSpec

    app()
    from_the_surface = render(table_painted_by_the_payload(sealed_payload("happy")))
    assert_pictures_match(
        old_side=render(real_table("happy")),
        new_side=from_the_surface,
        note="before the shipped table is changed",
    )
    original_columns = shipped.EXTRACTOR_COLUMNS
    original_spec = shipped.ExtractorBotTable.COLUMN_SPEC
    original_labels = shipped.ExtractorBotTable.COLUMNS
    original_tooltips = shipped.ExtractorBotTable.COLUMN_TOOLTIPS
    original_states = shipped.ExtractorBotTable.STATE_COLORS
    original_pools = shipped.ExtractorBotTable.POOL_COLORS
    try:
        shipped.ExtractorBotTable.STATE_COLORS = {"running": QColor("#111111")}
        shipped.ExtractorBotTable.POOL_COLORS = {"yellow": QColor("#222222")}
        recoloured = shipped.ExtractorBotTable()
        HELD.append(recoloured)
        recoloured.update_bots(CASES["happy"])
        assert_pictures_differ(
            old_side=render(recoloured),
            new_side=from_the_surface,
            note="the shipped colours changed and the surface did not",
        )
        assert surface.STATE_COLORS["running"] == RUNNING_COLOR
        assert surface.POOL_COLORS["yellow"] == PAUSED_COLOR
        assert len(surface.STATE_COLORS) == 7
        assert len(surface.POOL_COLORS) == 3
        unmoved = new_side("happy")["state"]["rows"][0]["cells"]
        assert unmoved[surface.COL_MODE]["color"] == RUNNING_COLOR
        assert unmoved[surface.COL_LIQUID]["color"] == PAUSED_COLOR

        changed = ColumnSpec(
            labels=("A", "B", "C", "D", "E", "F", "G", "H"),
            tooltips={0: "a changed tooltip"},
            fixed_widths={6: 999, 7: 998},
        )
        shipped.EXTRACTOR_COLUMNS = changed
        shipped.ExtractorBotTable.COLUMN_SPEC = changed
        shipped.ExtractorBotTable.COLUMNS = changed.labels
        shipped.ExtractorBotTable.COLUMN_TOOLTIPS = changed.tooltips
        relabelled = shipped.ExtractorBotTable()
        HELD.append(relabelled)
        relabelled.update_bots(CASES["happy"])
        assert relabelled.horizontalHeaderItem(0).text() == "A"
        assert relabelled.horizontalHeaderItem(0).toolTip() == "a changed tooltip"
        assert relabelled.columnWidth(surface.COL_FIRE) == 999
        assert_pictures_differ(
            old_side=render(relabelled),
            new_side=from_the_surface,
            note="the shipped columns changed and the surface did not",
        )
        assert surface.COLUMN_LABELS[0] == "Bot ID"
        assert surface.COLUMN_TOOLTIPS[0] != "a changed tooltip"
        assert surface.COLUMN_FIXED_WIDTHS[surface.COL_FIRE] == FIRE_COLUMN_WIDTH
    finally:
        shipped.EXTRACTOR_COLUMNS = original_columns
        shipped.ExtractorBotTable.COLUMN_SPEC = original_spec
        shipped.ExtractorBotTable.COLUMNS = original_labels
        shipped.ExtractorBotTable.COLUMN_TOOLTIPS = original_tooltips
        shipped.ExtractorBotTable.STATE_COLORS = original_states
        shipped.ExtractorBotTable.POOL_COLORS = original_pools
    assert old_side("happy") == new_side("happy")
    assert shipped.ExtractorBotTable.COLUMNS == surface.COLUMN_LABELS
    assert_pictures_match(
        old_side=render(real_table("happy")),
        new_side=from_the_surface,
        note="after the shipped table is put back",
    )


def test_the_surface_never_reads_the_shipped_module():
    """The surface imports the shipped table, so it could follow it."""
    import ast

    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    named = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                named.add(node.module)
            else:
                named.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
    assert "extractor_bot_table" not in named
    assert not any("widgets" in name for name in named), named
    assert "design_system" in named


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def call_bridge(params):
    """One request through the real bridge, returning the whole frame."""
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": 1, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model = surface.ExtractorBotTableModel()
    model.update_bots(TWO_BOTS)
    encoded = json.loads(json.dumps(surface.build_payload(model)))
    assert encoded["method"] == "extractor_bot_table.state"
    assert encoded["column_labels"] == list(surface.COLUMN_LABELS)
    assert encoded["rows"][0]["texts"][surface.COL_BOT_ID] == "bot-a"
    assert encoded["state_colors"]["running"] == RUNNING_COLOR
    assert encoded["buttons"]["7"]["text"] == "Detail"


def test_bridge_registers_the_extractor_bot_table_method():
    """The frontend cannot reach the Extractor table."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model
    assert "extractor_bot_table.state" in registry
    frame = call_bridge({"reset": True})
    assert frame["ok"] is True
    assert frame["result"]["method"] == surface.METHOD
    assert frame["result"]["row_count"] == 0
    unknown = desktop_bridge.handle_line(
        json.dumps({"id": 2, "method": "extractor_bot_table.no_such"}), registry
    )
    assert unknown["ok"] is False


def test_the_bridge_carries_every_action():
    """An action the bridge names does nothing when it is asked for."""
    call_bridge({"reset": True})
    written = call_bridge({"action": "update_bots", "bot_statuses": TWO_BOTS})
    assert written["result"]["row_count"] == 2
    assert written["result"]["bot_ids"] == ["bot-a", "bot-b"]
    assert written["result"]["rows"][1]["texts"][surface.COL_SYMBOL] == "ETH"
    clicked = call_bridge({"action": "detail", "bot_id": "bot-b"})
    assert clicked["result"]["selected_bot_id"] == "bot-b"
    assert clicked["result"]["detail_path"] == surface.DETAIL_PATH_SELECTED
    call_bridge({"reset": True})
    call_bridge({"action": "update_bots", "bot_statuses": TWO_BOTS})
    picked = call_bridge({"action": "select_row", "bot_id": "bot-a"})
    assert picked["result"]["selected_bot_id"] == "bot-a"
    assert picked["result"]["current_row"] == 0
    assert set(surface.BRIDGE_ACTIONS) == {"update_bots", "detail", "select_row"}


def test_the_bridge_keeps_the_table_until_a_reset():
    """A second request forgot the rows the first one wrote."""
    call_bridge({"reset": True})
    call_bridge({"action": "update_bots", "bot_statuses": TWO_BOTS})
    assert call_bridge({})["result"]["row_count"] == 2
    assert call_bridge({})["result"]["bot_ids"] == ["bot-a", "bot-b"]
    fresh = call_bridge({"reset": True})
    assert fresh["result"]["row_count"] == 0
    assert fresh["result"]["bot_ids"] == []
    assert fresh["result"]["selected_bot_id"] == ""


def test_the_bridge_reports_a_request_it_cannot_serve():
    """A bad request ends the session instead of answering."""
    call_bridge({"reset": True})
    frame = call_bridge(
        {"action": "update_bots", "bot_statuses": [{"pool_color": None}]}
    )
    assert frame["ok"] is False
    assert frame["error"]["type"] == "AttributeError"
    assert call_bridge({"reset": True})["ok"] is True


def test_the_bridge_import_list_stays_in_order():
    """The bridge's import list drifted out of order, so the next surface
    lands somewhere a reader will not look."""
    import ast

    bridge_path = REPO_ROOT / "src/core/desktop_bridge.py"
    tree = ast.parse(bridge_path.read_text(encoding="utf-8"))
    named: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs":
            named = [alias.name for alias in node.names]
    assert named == sorted(named), named
    assert "extractor_bot_table_surface" in named


# ---------------------------------------------------------------------
# Without Qt at all
# ---------------------------------------------------------------------

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
    "json.dumps({'id': 1, 'method': 'extractor_bot_table.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = (
    BLOCK_QT + "import json, sys\n"
    "from src.gui.main_tabs import extractor_bot_table_surface as s\n"
    "model = s.ExtractorBotTableModel(on_bot_clicked=lambda bot: None)\n"
    "model.update_bots([\n"
    "    {'bot_id': 'bot-a', 'state': 'running', 'chunk_size_usd': 100.0,\n"
    "     'chunk_free_base': 1.0, 'chunk_size_base': 2.0,\n"
    "     'n_positions_open': 1, 'n_positions_drawdown': 0,\n"
    "     'pool_color': 'yellow', 'base_currency': 'BTC',\n"
    "     'stats': {'total_trades': 3}},\n"
    "    {'bot_id': 'it\\u2019s <b>x</b>', 'state': 'paused',\n"
    "     'chunk_size_usd': 0.0, 'chunk_free_base': 0.0,\n"
    "     'chunk_size_base': 0.0, 'n_positions_open': 0,\n"
    "     'n_positions_drawdown': 0, 'pool_color': 'red',\n"
    "     'base_currency': '\\u0394', 'stats': {'total_trades': 0}},\n"
    "])\n"
    "model._on_detail('bot-a')\n"
    "payload = s.build_payload(model)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'row_count': payload['row_count'],\n"
    "    'bot_ids': payload['bot_ids'],\n"
    "    'texts': [row['texts'] for row in payload['rows']],\n"
    "    'colors': [row['colors'] for row in payload['rows']],\n"
    "    'selected_bot_id': payload['selected_bot_id'],\n"
    "    'detail_path': payload['detail_path'],\n"
    "    'detail_calls': payload['detail_calls'],\n"
    "    'labels': payload['column_labels'],\n"
    "    'buttons': payload['buttons'],\n"
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
    """Reaching the Extractor table pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == "extractor_bot_table.state"
    assert result["column_labels"] == list(surface.COLUMN_LABELS)
    assert result["column_count"] == 8
    assert result["state_colors"]["idle"] == IDLE_COLOR
    assert result["pool_colors"]["red"] == ERROR_COLOR
    assert result["buttons"]["6"]["enabled"] is False
    assert result["buttons"]["7"]["action"] == "_on_detail"
    assert result["rows"] == []
    assert result["selected_bot_id"] == ""


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_the_table_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["row_count"] == 2
    assert answered["bot_ids"] == ["bot-a", "it’s <b>x</b>"]
    assert answered["texts"][0][surface.COL_POOL] == "$100.00"
    assert answered["texts"][1][surface.COL_POOL] == surface.NO_VALUE_TEXT
    assert answered["texts"][1][surface.COL_SYMBOL] == "Δ"
    assert answered["colors"][0][surface.COL_MODE] == RUNNING_COLOR
    assert answered["colors"][1][surface.COL_LIQUID] == ERROR_COLOR
    assert answered["selected_bot_id"] == "bot-a"
    assert answered["detail_path"] == surface.DETAIL_PATH_SELECTED
    assert answered["detail_calls"] == ["bot-a"]
    assert answered["labels"] == list(surface.COLUMN_LABELS)
    assert answered["buttons"]["7"]["tooltip"] == surface.DETAIL_TOOLTIP
    assert answered["calls"] == 9


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process
    imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_hosts_the_table():
    """The Qt block let the shipped table through, so a run without Qt
    proves nothing about which side the frontend can reach."""
    probe = BLOCK_QT + (
        "import json, sys\n"
        "answer = {}\n"
        "try:\n"
        "    from src.gui.widgets import extractor_bot_table as t\n"
        "    answer['error'] = ''\n"
        "    answer['built'] = hasattr(t, 'ExtractorBotTable')\n"
        "except Exception as exc:\n"
        "    answer['error'] = type(exc).__name__\n"
        "    answer['built'] = False\n"
        "from src.gui.main_tabs import extractor_bot_table_surface as s\n"
        "answer['labels'] = len(s.COLUMN_LABELS)\n"
        "answer['qt'] = 'PySide6' in sys.modules\n"
        "print(json.dumps(answer))\n"
    )
    answered = run_script(probe)
    assert answered["error"] == "ImportError"
    assert answered["built"] is False
    assert answered["labels"] == surface.COLUMN_COUNT == 8
    assert answered["qt"] is False


def test_the_widget_package_needs_qt_and_the_surface_package_does_not():
    """The surface sits where importing it pulls Qt into the backend."""
    assert SURFACE_PATH.parent.name == "main_tabs"
    assert TABLE_PATH.parent.name == "widgets"
    package = REPO_ROOT / "src/gui/widgets/__init__.py"
    assert "PySide6" in package.read_text(encoding="utf-8")
    probe = BLOCK_QT + (
        "import json\n"
        "answer = {}\n"
        "for name in ('src.gui.widgets', 'src.gui.main_tabs'):\n"
        "    try:\n"
        "        __import__(name)\n"
        "        answer[name] = ''\n"
        "    except Exception as exc:\n"
        "        answer[name] = type(exc).__name__\n"
        "print(json.dumps(answer))\n"
    )
    answered = run_script(probe)
    assert answered["src.gui.widgets"] == "ImportError"
    assert answered["src.gui.main_tabs"] == ""
