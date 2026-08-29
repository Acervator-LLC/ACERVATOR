"""The Qt selection helpers and the Qt-free surface, side by side.

A failure means the view model chooses a different row, makes a
different sequence of calls on the table, leaves a different selection
behind or lets a different number of selection signals out than
``bot_selection`` does on the same table and the same input.
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

from src.gui.main_tabs import bot_selection_surface as surface
from src.gui.widgets import bot_selection
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

POPULATE = "populate"
SELECT = "select"
CLEAR = "clear"
BLOCK = "block"
REANCHOR = "reanchor"
SELECT_FOR_BOT = "select_for_bot"

PIXEL_SIZE = (1200, 220)


def app():
    """The process application object every render and widget needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def table_classes():
    """The two tables that call the helpers, by name."""
    from src.gui.widgets.bot_status_table import BotStatusTable
    from src.gui.widgets.extractor_bot_table import ExtractorBotTable

    return {"scrumming": BotStatusTable, "extractor": ExtractorBotTable}


TRACED_METHODS = (
    "get_selected_bot_id",
    "item",
    "clearSelection",
    "setCurrentCell",
    "selectRow",
)

_TRACED_CACHE: dict = {}


def traced_class(base):
    """A real bot table that records the calls the helpers make on it.

    The five recorded methods are the whole surface the helpers touch.
    Recording is off outside a driven step so that setup and snapshot
    calls never enter the trace.
    """
    if base in _TRACED_CACHE:
        return _TRACED_CACHE[base]

    class _Traced(base):
        def __init__(self):
            super().__init__()
            self.trace: list = []
            self.emissions = 0
            self.recording = False
            self.itemSelectionChanged.connect(self._count_emission)

        def _count_emission(self):
            self.emissions += 1

        def _record(self, name, *args):
            if self.recording:
                self.trace.append([name, *args])

        def get_selected_bot_id(self):
            self._record("get_selected_bot_id")
            return super().get_selected_bot_id()

        def item(self, row, col):
            self._record("item", row, col)
            return super().item(row, col)

        def clearSelection(self):
            self._record("clearSelection")
            return super().clearSelection()

        def setCurrentCell(self, row, col):
            self._record("setCurrentCell", row, col)
            return super().setCurrentCell(row, col)

        def selectRow(self, row):
            self._record("selectRow", row)
            return super().selectRow(row)

    _TRACED_CACHE[base] = _Traced
    return _Traced


def populate(table, bot_ids, filled_rows, row_count=None):
    """Fill the table exactly, so which rows carry an anchor item is chosen."""
    from PySide6.QtWidgets import QTableWidgetItem

    rows = len(bot_ids) if row_count is None else row_count
    table.setRowCount(0)
    table.setRowCount(rows)
    table._bot_ids = list(bot_ids)
    for row in range(rows):
        if row not in filled_rows:
            continue
        for col in range(table.columnCount()):
            table.setItem(row, col, QTableWidgetItem(f"r{row}c{col}"))


def anchor_filled_rows(table):
    """The rows whose anchor column carries an item, read off the table."""
    return [
        row
        for row in range(table.rowCount())
        if table.item(row, surface.ANCHOR_COLUMN) is not None
    ]


def apply_plan(table, plan):
    """Make the calls the plan names, and only those."""
    from PySide6.QtCore import QSignalBlocker

    for entry in plan["reads"]:
        getattr(table, entry[0])(*entry[1:])
    if plan["block_signals"]:
        with QSignalBlocker(table):
            for entry in plan["calls"]:
                getattr(table, entry[0])(*entry[1:])
        return
    for entry in plan["calls"]:
        getattr(table, entry[0])(*entry[1:])


def snapshot(table, error):
    """Every output one step leaves on the table."""
    return {
        "error": error,
        "trace": [list(entry) for entry in table.trace],
        "row_count": table.rowCount(),
        "current_row": table.currentRow(),
        "current_column": table.currentColumn(),
        "selected_bot_id": table.get_selected_bot_id(),
        "selected_rows": sorted(
            index.row() for index in table.selectionModel().selectedRows()
        ),
        "selected_texts": [item.text() for item in table.selectedItems()],
        "signals_blocked": table.signalsBlocked(),
        "emissions": table.emissions,
    }


def run_step(table, step, use_surface):
    """One scripted step against one table. Only the two decisions trace."""
    table.trace = []
    kind = step[0]
    if kind == POPULATE:
        populate(table, step[1], step[2], step[3] if len(step) > 3 else None)
        return None
    if kind == SELECT:
        table.setCurrentCell(step[1], surface.ANCHOR_COLUMN)
        table.selectRow(step[1])
        return None
    if kind == CLEAR:
        table.clearSelection()
        table.setCurrentCell(surface.CLEARED_ROW, surface.CLEARED_COLUMN)
        return None
    if kind == BLOCK:
        table.blockSignals(step[1])
        return None
    bot_ids = list(table._bot_ids)
    filled = anchor_filled_rows(table)
    selected = table.get_selected_bot_id()
    error = None
    table.recording = True
    try:
        if kind == REANCHOR:
            if use_surface:
                apply_plan(
                    table,
                    surface.reanchor_plan(step[1], bot_ids, selected, filled),
                )
            else:
                bot_selection._reanchor_bot_selection(table, step[1], bot_ids)
        else:
            if use_surface:
                apply_plan(table, surface.select_for_bot_plan(step[1], bot_ids, filled))
            else:
                bot_selection._select_row_for_bot(table, step[1], bot_ids)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        table.recording = False
    return error


def run(script, table_name, use_surface):
    """Drive one table through the script, tracing every step."""
    app()
    table = traced_class(table_classes()[table_name])()
    trace = [snapshot(table, None)]
    for step in script:
        error = run_step(table, step, use_surface)
        trace.append(snapshot(table, error))
    return trace


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


THREE = ["bot-a", "bot-b", "bot-c"]
THREE_REORDERED = ["bot-c", "bot-b", "bot-a"]
EIGHT = [f"bot-{index}" for index in range(8)]

NOTHING_SELECTED_SCRIPT = [
    (POPULATE, THREE, (0, 1, 2)),
    (REANCHOR, ""),
    (REANCHOR, None),
    (REANCHOR, 0),
    (SELECT_FOR_BOT, ""),
    (SELECT_FOR_BOT, None),
    (SELECT_FOR_BOT, 0),
]

STEADY_STATE_SCRIPT = [
    (POPULATE, THREE, (0, 1, 2)),
    (SELECT, 1),
    (REANCHOR, "bot-b"),
    (REANCHOR, "bot-b"),
    (REANCHOR, "bot-b"),
]

REORDER_SCRIPT = [
    (POPULATE, THREE, (0, 1, 2)),
    (SELECT, 0),
    (POPULATE, THREE_REORDERED, (0, 1, 2)),
    (REANCHOR, "bot-a"),
    (POPULATE, THREE, (0, 1, 2)),
    (REANCHOR, "bot-a"),
]

BOT_LEFT_THE_FLEET_SCRIPT = [
    (POPULATE, THREE, (0, 1, 2)),
    (SELECT, 2),
    (POPULATE, ["bot-a", "bot-b"], (0, 1)),
    (REANCHOR, "bot-c"),
    (REANCHOR, "bot-c"),
]

SKIPPED_ROW_SCRIPT = [
    (POPULATE, THREE, (0, 2)),
    (SELECT, 0),
    (REANCHOR, "bot-b"),
    (SELECT_FOR_BOT, "bot-b"),
    (SELECT_FOR_BOT, "bot-c"),
    (SELECT_FOR_BOT, "bot-b"),
]

EVERY_ROW_SKIPPED_SCRIPT = [
    (POPULATE, THREE, ()),
    (REANCHOR, "bot-a"),
    (SELECT_FOR_BOT, "bot-a"),
    (SELECT, 1),
    (REANCHOR, "bot-a"),
]

EMPTY_FLEET_SCRIPT: list[tuple] = [
    (POPULATE, [], ()),
    (REANCHOR, "bot-a"),
    (SELECT_FOR_BOT, "bot-a"),
    (REANCHOR, ""),
]

SINGLE_BOT_SCRIPT = [
    (POPULATE, ["only"], (0,)),
    (REANCHOR, "only"),
    (SELECT_FOR_BOT, "only"),
    (REANCHOR, "only"),
    (SELECT, 0),
    (REANCHOR, "only"),
]

MANY_BOTS_SCRIPT = [
    (POPULATE, EIGHT, tuple(range(8))),
    (SELECT, 7),
    (POPULATE, list(reversed(EIGHT)), tuple(range(8))),
    (REANCHOR, "bot-7"),
    (SELECT_FOR_BOT, "bot-3"),
    (SELECT_FOR_BOT, "bot-0"),
    (POPULATE, EIGHT, tuple(range(8))),
    (REANCHOR, "bot-0"),
]

DUPLICATE_SCRIPT = [
    (POPULATE, ["twin", "twin", "other"], (0, 1, 2)),
    (SELECT, 2),
    (REANCHOR, "twin"),
    (SELECT, 1),
    (REANCHOR, "twin"),
    (SELECT_FOR_BOT, "twin"),
]

DUPLICATE_FIRST_ROW_SKIPPED_SCRIPT = [
    (POPULATE, ["twin", "twin", "other"], (1, 2)),
    (SELECT, 2),
    (REANCHOR, "twin"),
    (SELECT_FOR_BOT, "twin"),
]

MORE_IDS_THAN_ROWS_SCRIPT = [
    (POPULATE, THREE, (0, 1), 2),
    (SELECT, 0),
    (REANCHOR, "bot-c"),
    (SELECT_FOR_BOT, "bot-c"),
    (SELECT_FOR_BOT, "bot-b"),
]

MORE_ROWS_THAN_IDS_SCRIPT = [
    (POPULATE, ["bot-a"], (0, 1, 2), 3),
    (SELECT, 2),
    (REANCHOR, "bot-a"),
    (SELECT_FOR_BOT, "bot-a"),
]

ALREADY_BLOCKED_SCRIPT = [
    (POPULATE, THREE, (0, 1, 2)),
    (SELECT, 0),
    (BLOCK, True),
    (REANCHOR, "bot-c"),
    (SELECT_FOR_BOT, "bot-b"),
    (BLOCK, False),
    (REANCHOR, "bot-a"),
]

CLEARED_THEN_REANCHOR_SCRIPT = [
    (POPULATE, THREE, (0, 1, 2)),
    (SELECT, 1),
    (CLEAR,),
    (REANCHOR, "bot-b"),
    (REANCHOR, "bot-b"),
]

ODD_BOT_ID_SCRIPT = [
    (POPULATE, ["", "unicode-Δ→⚡", "a" * 200, "7"], (0, 1, 2, 3)),
    (REANCHOR, ""),
    (REANCHOR, "unicode-Δ→⚡"),
    (SELECT_FOR_BOT, "a" * 200),
    (SELECT_FOR_BOT, "7"),
    (REANCHOR, "7"),
]

DETAIL_THEN_REFRESH_SCRIPT = [
    (POPULATE, THREE, (0, 1, 2)),
    (SELECT_FOR_BOT, "bot-c"),
    (POPULATE, THREE_REORDERED, (0, 1, 2)),
    (REANCHOR, "bot-c"),
    (SELECT_FOR_BOT, "bot-a"),
    (POPULATE, ["bot-b"], (0,)),
    (REANCHOR, "bot-a"),
]

SCRIPTS = {
    "already_blocked": ALREADY_BLOCKED_SCRIPT,
    "bot_left_the_fleet": BOT_LEFT_THE_FLEET_SCRIPT,
    "cleared_then_reanchor": CLEARED_THEN_REANCHOR_SCRIPT,
    "detail_then_refresh": DETAIL_THEN_REFRESH_SCRIPT,
    "duplicates": DUPLICATE_SCRIPT,
    "duplicates_first_row_skipped": DUPLICATE_FIRST_ROW_SKIPPED_SCRIPT,
    "empty_fleet": EMPTY_FLEET_SCRIPT,
    "every_row_skipped": EVERY_ROW_SKIPPED_SCRIPT,
    "many_bots": MANY_BOTS_SCRIPT,
    "more_ids_than_rows": MORE_IDS_THAN_ROWS_SCRIPT,
    "more_rows_than_ids": MORE_ROWS_THAN_IDS_SCRIPT,
    "nothing_selected": NOTHING_SELECTED_SCRIPT,
    "odd_bot_ids": ODD_BOT_ID_SCRIPT,
    "reorder": REORDER_SCRIPT,
    "single_bot": SINGLE_BOT_SCRIPT,
    "skipped_row": SKIPPED_ROW_SCRIPT,
    "steady_state": STEADY_STATE_SCRIPT,
}

TABLE_NAMES = ("extractor", "scrumming")


@pytest.mark.parametrize("table_name", TABLE_NAMES)
@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_old_and_new_traces_are_identical(name, table_name):
    """A step of the script leaves the two tables in different states."""
    old = run(SCRIPTS[name], table_name, use_surface=False)
    new = run(SCRIPTS[name], table_name, use_surface=True)
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_the_trace_holds_the_whole_step(name):
    """The comparison passed by measuring nothing."""
    old = run(SCRIPTS[name], "scrumming", use_surface=False)
    assert len(old) == len(SCRIPTS[name]) + 1
    for step in old:
        assert set(step) == {
            "error",
            "trace",
            "row_count",
            "current_row",
            "current_column",
            "selected_bot_id",
            "selected_rows",
            "selected_texts",
            "signals_blocked",
            "emissions",
        }
    driven = [step for step in SCRIPTS[name] if step[0] in (REANCHOR, SELECT_FOR_BOT)]
    assert driven
    if name != "nothing_selected":
        assert any(step["trace"] for step in old)


def test_a_no_op_branch_touches_the_table_not_at_all():
    """A branch that must leave the table alone made a call on it."""
    old = run(NOTHING_SELECTED_SCRIPT, "scrumming", use_surface=False)
    new = run(NOTHING_SELECTED_SCRIPT, "scrumming", use_surface=True)
    assert [step["trace"] for step in old] == [[]] * len(old)
    assert [step["trace"] for step in new] == [[]] * len(old)
    assert {step["emissions"] for step in old} == {0}
    assert {step["current_row"] for step in old} == {-1}


def test_the_trace_records_more_than_one_answer():
    """Every step traced the same thing, so a difference could not show."""
    seen_traces = set()
    seen_rows = set()
    seen_blocked = set()
    seen_emissions = set()
    for name in SCRIPTS:
        for step in run(SCRIPTS[name], "scrumming", use_surface=False):
            seen_traces.add(json.dumps(step["trace"]))
            seen_rows.add(step["current_row"])
            seen_blocked.add(step["signals_blocked"])
            seen_emissions.add(step["emissions"])
    assert len(seen_traces) > 5
    assert len(seen_rows) > 3
    assert seen_blocked == {False, True}
    assert len(seen_emissions) > 2


def test_the_scripts_reach_every_branch_of_both_helpers():
    """A named branch was never driven, so its parity was never compared."""
    reached = {
        "reanchor_no_previous_bot": False,
        "reanchor_already_on_the_bot": False,
        "reanchor_bot_left_the_fleet": False,
        "reanchor_row_was_skipped": False,
        "reanchor_selects_the_row": False,
        "select_for_bot_no_bot_id": False,
        "select_for_bot_left_the_fleet": False,
        "select_for_bot_row_was_skipped": False,
        "select_for_bot_selects_the_row": False,
    }
    for script in SCRIPTS.values():
        for branch in branches_reached(script):
            reached[branch] = True
    assert reached == {name: True for name in reached}


def branches_reached(script):
    """Every plan branch the script drives, named."""
    app()
    table = traced_class(table_classes()["scrumming"])()
    found = []
    for step in script:
        if step[0] in (REANCHOR, SELECT_FOR_BOT):
            bot_ids = list(table._bot_ids)
            filled = anchor_filled_rows(table)
            if step[0] == REANCHOR:
                plan = surface.reanchor_plan(
                    step[1], bot_ids, table.get_selected_bot_id(), filled
                )
                found.append("reanchor_" + reanchor_branch(plan, step[1], bot_ids))
            else:
                plan = surface.select_for_bot_plan(step[1], bot_ids, filled)
                found.append("select_for_bot_" + select_branch(plan, step[1], bot_ids))
        run_step(table, step, use_surface=False)
    return found


def reanchor_branch(plan, previous_bot_id, bot_ids):
    if not plan["reads"]:
        return "no_previous_bot"
    if not plan["calls"]:
        return "already_on_the_bot"
    if plan["target_row"] is not None:
        return "selects_the_row"
    if surface.target_row(previous_bot_id, bot_ids) is None:
        return "bot_left_the_fleet"
    return "row_was_skipped"


def select_branch(plan, bot_id, bot_ids):
    if plan["target_row"] is not None:
        return "selects_the_row"
    if not bot_id:
        return "no_bot_id"
    if surface.target_row(bot_id, bot_ids) is None:
        return "left_the_fleet"
    return "row_was_skipped"


def test_the_refresh_lets_no_selection_signal_out():
    """The 2000 ms refresh moved the operator's last-clicked table flag.

    The refresh step moves the highlight two rows and emits nothing.
    """
    for table_name in TABLE_NAMES:
        old = run(REORDER_SCRIPT, table_name, use_surface=False)
        new = run(REORDER_SCRIPT, table_name, use_surface=True)
        assert old[3]["current_row"] == -1
        assert old[4]["current_row"] == 2
        assert old[4]["selected_bot_id"] == "bot-a"
        assert old[4]["emissions"] == old[3]["emissions"]
        assert old[6]["current_row"] == 0
        assert old[6]["emissions"] == old[5]["emissions"]
        assert [step["emissions"] for step in new] == [
            step["emissions"] for step in old
        ]
        assert [step["current_row"] for step in new] == [
            step["current_row"] for step in old
        ]
        assert surface.REANCHOR_BLOCKS_SIGNALS is True


def test_the_detail_button_lets_a_selection_signal_out():
    """The Detail button stopped moving the selection the flag describes.

    The button step moves the highlight and emits once.
    """
    for table_name in TABLE_NAMES:
        old = run(DETAIL_THEN_REFRESH_SCRIPT, table_name, use_surface=False)
        new = run(DETAIL_THEN_REFRESH_SCRIPT, table_name, use_surface=True)
        assert old[2]["current_row"] == 2
        assert old[2]["selected_bot_id"] == "bot-c"
        assert old[2]["emissions"] == old[1]["emissions"] + 1
        assert old[5]["current_row"] == 2
        assert old[5]["emissions"] == old[4]["emissions"] + 1
        assert [step["emissions"] for step in new] == [
            step["emissions"] for step in old
        ]
        assert [step["current_row"] for step in new] == [
            step["current_row"] for step in old
        ]
        assert surface.SELECT_FOR_BOT_BLOCKS_SIGNALS is False


def test_a_table_already_blocked_is_left_blocked():
    """The refresh unblocked a table its caller had blocked."""
    for table_name in TABLE_NAMES:
        old = run(ALREADY_BLOCKED_SCRIPT, table_name, use_surface=False)
        new = run(ALREADY_BLOCKED_SCRIPT, table_name, use_surface=True)
        assert old[3]["signals_blocked"] is True
        assert old[4]["signals_blocked"] is True
        assert old[5]["signals_blocked"] is True
        assert old[6]["signals_blocked"] is False
        assert [step["signals_blocked"] for step in new] == [
            step["signals_blocked"] for step in old
        ]


def test_the_first_of_two_equal_bot_ids_wins():
    """A fleet listing one bot twice highlighted the later row."""
    old = run(DUPLICATE_SCRIPT, "scrumming", use_surface=False)
    new = run(DUPLICATE_SCRIPT, "scrumming", use_surface=True)
    assert old[3]["current_row"] == 0
    assert old[6]["current_row"] == 0
    assert new[3]["current_row"] == old[3]["current_row"]
    assert surface.target_row("twin", ["twin", "twin", "other"]) == 0
    assert surface.target_row("other", ["twin", "twin", "other"]) == 2
    assert surface.target_row("gone", ["twin", "twin", "other"]) is None


def test_a_row_the_render_skipped_is_refused():
    """A row with no anchor item was highlighted, so the table answers ''."""
    old = run(SKIPPED_ROW_SCRIPT, "scrumming", use_surface=False)
    new = run(SKIPPED_ROW_SCRIPT, "scrumming", use_surface=True)
    assert old[3]["current_row"] == -1
    assert old[3]["selected_bot_id"] == ""
    assert old[4]["current_row"] == -1
    assert old[5]["current_row"] == 2
    assert old[5]["selected_bot_id"] == "bot-c"
    assert old[6]["current_row"] == 2
    assert new == old


def test_a_bot_id_beyond_the_last_row_is_refused():
    """A bot id past the last row highlighted a row that is not there."""
    old = run(MORE_IDS_THAN_ROWS_SCRIPT, "scrumming", use_surface=False)
    new = run(MORE_IDS_THAN_ROWS_SCRIPT, "scrumming", use_surface=True)
    assert old[3]["current_row"] == -1
    assert old[4]["current_row"] == -1
    assert old[5]["current_row"] == 1
    assert new == old
    plan = surface.reanchor_plan("bot-c", THREE, "bot-a", [0, 1])
    assert plan["target_row"] is None
    assert plan["reads"] == [["get_selected_bot_id"], ["item", 2, 0]]
    assert plan["calls"] == [["clearSelection"], ["setCurrentCell", -1, -1]]


def test_the_plan_names_the_reads_the_helper_makes():
    """The plan dropped a read, so the call sequence stopped matching."""
    assert surface.reanchor_plan("", THREE, "", [0, 1, 2])["reads"] == []
    assert surface.reanchor_plan("bot-a", THREE, "bot-a", [0, 1, 2])["reads"] == [
        ["get_selected_bot_id"]
    ]
    assert surface.reanchor_plan("bot-a", THREE, "bot-b", [0, 1, 2])["reads"] == [
        ["get_selected_bot_id"],
        ["item", 0, 0],
    ]
    assert surface.reanchor_plan("gone", THREE, "bot-b", [0, 1, 2])["reads"] == [
        ["get_selected_bot_id"]
    ]
    assert surface.select_for_bot_plan("", THREE, [0, 1, 2])["reads"] == []
    assert surface.select_for_bot_plan("gone", THREE, [0, 1, 2])["reads"] == []
    assert surface.select_for_bot_plan("bot-c", THREE, [0, 1, 2])["reads"] == [
        ["item", 2, 0]
    ]


def test_the_plan_names_every_call_the_helper_makes():
    """The plan dropped a call, or made one the helper never makes."""
    assert surface.reanchor_plan("bot-b", THREE, "bot-a", [0, 1, 2])["calls"] == [
        ["clearSelection"],
        ["setCurrentCell", 1, 0],
        ["selectRow", 1],
    ]
    assert surface.reanchor_plan("bot-b", THREE, "bot-a", [0, 2])["calls"] == [
        ["clearSelection"],
        ["setCurrentCell", -1, -1],
    ]
    assert surface.reanchor_plan("bot-b", THREE, "bot-b", [0, 1, 2])["calls"] == []
    assert surface.reanchor_plan("", THREE, "bot-b", [0, 1, 2])["calls"] == []
    assert surface.select_for_bot_plan("bot-b", THREE, [0, 1, 2])["calls"] == [
        ["setCurrentCell", 1, 0],
        ["selectRow", 1],
    ]
    assert surface.select_for_bot_plan("bot-b", THREE, [0, 2])["calls"] == []
    assert surface.select_for_bot_plan("gone", THREE, [0, 1, 2])["calls"] == []
    assert surface.select_for_bot_plan("", THREE, [0, 1, 2])["calls"] == []


def driven_table(script, table_name, use_surface):
    """The table left behind after the script, ready to render."""
    app()
    table = traced_class(table_classes()[table_name])()
    for step in script:
        run_step(table, step, use_surface)
    return table


def table_with_plan(script, table_name, plan):
    """The table left behind after the setup steps and one hand-made plan."""
    app()
    table = traced_class(table_classes()[table_name])()
    for step in script:
        run_step(table, step, use_surface=False)
    apply_plan(table, plan)
    return table


PIXEL_SETUP = [
    (POPULATE, THREE, (0, 1, 2)),
    (SELECT, 0),
    (POPULATE, THREE_REORDERED, (0, 1, 2)),
]
PIXEL_SCRIPT = PIXEL_SETUP + [(REANCHOR, "bot-a")]


@pytest.mark.parametrize("table_name", TABLE_NAMES)
def test_the_two_sides_render_the_same_pixels(table_name):
    """The table paints a different highlight than the helper leaves."""
    assert_pictures_match(
        old_side=render_offscreen(
            driven_table(PIXEL_SCRIPT, table_name, use_surface=False), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            driven_table(PIXEL_SCRIPT, table_name, use_surface=True), PIXEL_SIZE
        ),
        note=table_name,
    )


@pytest.mark.parametrize("table_name", TABLE_NAMES)
def test_the_pixel_check_reports_the_highlight_on_another_row(table_name):
    """The image comparison cannot see the highlight move one row."""
    moved = surface.reanchor_plan("bot-a", THREE_REORDERED, "", [0, 1, 2])
    moved["calls"] = [
        ["clearSelection"],
        ["setCurrentCell", 1, 0],
        ["selectRow", 1],
    ]
    from_helper = render_offscreen(
        driven_table(PIXEL_SCRIPT, table_name, use_surface=False), PIXEL_SIZE
    )
    from_moved = render_offscreen(
        table_with_plan(PIXEL_SETUP, table_name, moved), PIXEL_SIZE
    )
    assert_pictures_differ(old_side=from_helper, new_side=from_moved, note=table_name)


@pytest.mark.parametrize("table_name", TABLE_NAMES)
def test_the_pixel_check_reports_a_plan_that_does_nothing(table_name):
    """The image comparison cannot see the highlight fail to arrive."""
    silent = surface.reanchor_plan("bot-a", THREE_REORDERED, "", [0, 1, 2])
    silent["calls"] = []
    from_helper = render_offscreen(
        driven_table(PIXEL_SCRIPT, table_name, use_surface=False), PIXEL_SIZE
    )
    from_silent = render_offscreen(
        table_with_plan(PIXEL_SETUP, table_name, silent), PIXEL_SIZE
    )
    assert_pictures_differ(old_side=from_helper, new_side=from_silent, note=table_name)


@pytest.mark.parametrize("table_name", TABLE_NAMES)
def test_the_pixel_check_reports_a_cleared_selection(table_name):
    """The image comparison cannot see the highlight disappear."""
    cleared = surface.reanchor_plan("gone", THREE_REORDERED, "", [0, 1, 2])
    from_helper = render_offscreen(
        driven_table(PIXEL_SCRIPT, table_name, use_surface=False), PIXEL_SIZE
    )
    from_cleared = render_offscreen(
        table_with_plan(PIXEL_SETUP, table_name, cleared), PIXEL_SIZE
    )
    assert_pictures_differ(old_side=from_helper, new_side=from_cleared, note=table_name)
    assert cleared["calls"] == [["clearSelection"], ["setCurrentCell", -1, -1]]


@pytest.mark.parametrize("table_name", TABLE_NAMES)
def test_a_same_length_cell_is_compared_as_an_exact_string(table_name):
    """A same-length cell swap was left to the render to report.

    Whether a swap of equal length moves a pixel depends on the fonts
    the host installs, so no render carries this proof on every machine.
    Every cell is read off the table the helper drives and off the table
    the plan drives, and compared character for character.
    """
    app()
    from_helper = driven_table(PIXEL_SCRIPT, table_name, use_surface=False)
    from_plan = driven_table(PIXEL_SCRIPT, table_name, use_surface=True)
    assert from_helper.rowCount() == from_plan.rowCount() > 0
    assert from_helper.columnCount() == from_plan.columnCount() > 0
    for row in range(from_helper.rowCount()):
        for col in range(from_helper.columnCount()):
            helper_cell = from_helper.item(row, col)
            plan_cell = from_plan.item(row, col)
            assert (helper_cell is None) is (plan_cell is None), (row, col)
            if helper_cell is not None:
                assert helper_cell.text() == plan_cell.text(), (row, col)
    original = from_helper.item(0, 0).text()
    disguised = "r0c9"
    assert len(disguised) == len(original)
    assert disguised != original


HELPER_PATH = REPO_ROOT / "src/gui/widgets/bot_selection.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/bot_selection_surface.py"

MARKERS_ABSENT_FROM_BOTH = (
    ".connect(",
    "setToolTip",
    "setStyleSheet",
    "setBackground",
    "setForeground",
    "QColor",
    "design_system",
    "setColumnWidth",
    "setHorizontalHeaderLabels",
    "horizontalHeader",
    "{:",
)

MARKER_HOMES = {
    ".connect(": "src/gui/widgets/bot_status_table.py",
    "setToolTip": "src/gui/widgets/bot_status_table.py",
    "setStyleSheet": "src/gui/widgets/bot_status_table.py",
    "setBackground": "src/gui/indicator_panel.py",
    "setForeground": "src/gui/indicator_panel.py",
    "QColor": "src/gui/widgets/bot_status_table.py",
    "design_system": "src/gui/widgets/bot_status_table.py",
    "setColumnWidth": "src/gui/widgets/__init__.py",
    "setHorizontalHeaderLabels": "src/gui/indicator_panel.py",
    "horizontalHeader": "src/gui/widgets/bot_status_table.py",
    "{:": "src/gui/main_tabs/capital_registry_surface.py",
}


def test_neither_file_paints_a_colour_a_header_or_a_signal():
    """A colour, a header, a width or a signal appeared on one side only."""
    helper_text = HELPER_PATH.read_text(encoding="utf-8")
    surface_text = SURFACE_PATH.read_text(encoding="utf-8")
    for marker in MARKERS_ABSENT_FROM_BOTH:
        assert marker not in helper_text, marker
        assert marker not in surface_text, marker
    for marker, path in MARKER_HOMES.items():
        assert marker in (REPO_ROOT / path).read_text(encoding="utf-8"), marker


def test_the_surface_imports_no_qt():
    """The surface grew a Qt import, so the backend would load Qt."""
    surface_text = SURFACE_PATH.read_text(encoding="utf-8")
    assert "PySide6" not in surface_text
    assert "QSignalBlocker" not in surface_text
    assert "PySide6" in HELPER_PATH.read_text(encoding="utf-8")


FUNCTION_MAP = {
    "_reanchor_bot_selection": "reanchor_plan",
    "_select_row_for_bot": "select_for_bot_plan",
}


def helper_functions():
    """Every function ``bot_selection`` itself defines."""
    import inspect

    return {
        name
        for name, value in vars(bot_selection).items()
        if inspect.isfunction(value) and value.__module__ == bot_selection.__name__
    }


def test_every_helper_function_has_a_counterpart():
    """A function exists on one side and nowhere on the other."""
    assert helper_functions() == set(FUNCTION_MAP)
    for target in FUNCTION_MAP.values():
        assert callable(getattr(surface, target))


def test_the_two_sides_take_the_same_inputs():
    """A parameter was dropped, renamed or reordered."""
    import inspect

    reanchor = inspect.signature(bot_selection._reanchor_bot_selection)
    assert list(reanchor.parameters) == ["table", "previous_bot_id", "bot_ids"]
    select = inspect.signature(bot_selection._select_row_for_bot)
    assert list(select.parameters) == ["table", "bot_id", "bot_ids"]
    assert list(inspect.signature(surface.reanchor_plan).parameters) == [
        "previous_bot_id",
        "bot_ids",
        "selected_bot_id",
        "filled_rows",
    ]
    assert list(inspect.signature(surface.select_for_bot_plan).parameters) == [
        "bot_id",
        "bot_ids",
        "filled_rows",
    ]


def test_the_helper_is_defined_only_when_qt_is_present():
    """The Qt guard went, so importing the helper without Qt would raise."""
    helper_text = HELPER_PATH.read_text(encoding="utf-8")
    assert "_HAS_QT = True" in helper_text
    assert "if _HAS_QT:" in helper_text
    assert "_HAS_QT" not in SURFACE_PATH.read_text(encoding="utf-8")


def test_the_two_sides_agree_on_the_anchor_column_and_the_cleared_cell():
    """A column index or the cleared cell drifted from the helper."""
    helper_text = HELPER_PATH.read_text(encoding="utf-8")
    assert "setCurrentCell(-1, -1)" in helper_text
    assert "setCurrentCell(target, 0)" in helper_text
    assert "table.item(target, 0)" in helper_text
    assert surface.ANCHOR_COLUMN == 0
    assert surface.CLEARED_ROW == -1
    assert surface.CLEARED_COLUMN == -1
    assert surface.SELECTION == {
        "anchor_column": 0,
        "cleared_row": -1,
        "cleared_column": -1,
        "reanchor_blocks_signals": True,
        "select_for_bot_blocks_signals": False,
    }


def test_the_helper_blocks_one_signal_and_not_the_other():
    """The two decisions stopped differing on whether they are silent."""
    helper_text = HELPER_PATH.read_text(encoding="utf-8")
    assert helper_text.count("QSignalBlocker(table)") == 1
    assert "table.blockSignals(" not in helper_text
    reanchor_body = helper_text.split("def _reanchor_bot_selection")[1].split(
        "def _select_row_for_bot"
    )[0]
    select_body = helper_text.split("def _select_row_for_bot")[1]
    assert "QSignalBlocker(table)" in reanchor_body
    assert "QSignalBlocker" not in select_body
    assert surface.REANCHOR_BLOCKS_SIGNALS is True
    assert surface.SELECT_FOR_BOT_BLOCKS_SIGNALS is False


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = surface.build_view_model(
        surface.REANCHOR, "bot-a", THREE_REORDERED, "bot-b", [0, 1, 2]
    )
    encoded = json.loads(json.dumps(payload))
    assert encoded["bot_ids"] == THREE_REORDERED
    assert encoded["filled_rows"] == [0, 1, 2]
    assert encoded["selection"] == surface.SELECTION
    assert encoded["plan"] == {
        "action": "reanchor",
        "target_row": 2,
        "block_signals": True,
        "reads": [["get_selected_bot_id"], ["item", 2, 0]],
        "calls": [
            ["clearSelection"],
            ["setCurrentCell", 2, 0],
            ["selectRow", 2],
        ],
    }


def test_view_model_answers_the_detail_button_action():
    """The Detail button action stopped reaching the surface."""
    payload = surface.build_view_model(
        surface.SELECT_FOR_BOT, "bot-b", THREE, "", [0, 1, 2]
    )
    assert payload["plan"] == {
        "action": "select_for_bot",
        "target_row": 1,
        "block_signals": False,
        "reads": [["item", 1, 0]],
        "calls": [["setCurrentCell", 1, 0], ["selectRow", 1]],
    }


def test_an_action_the_surface_does_not_name_touches_nothing(capture_log):
    """An unknown action moved the highlight instead of doing nothing."""
    with capture_log(surface.logger.name) as records:
        payload = surface.build_view_model("scroll", "bot-b", THREE, "", [0, 1, 2])
    assert payload["plan"] == {
        "action": "scroll",
        "target_row": None,
        "block_signals": False,
        "reads": [],
        "calls": [],
    }
    assert [record.getMessage() for record in records] == [
        "bot selection action not recognised: 'scroll'"
    ]


def test_view_model_defaults_every_missing_parameter():
    """A request missing a parameter raised instead of doing nothing."""
    assert surface.view_model({})["plan"] == {
        "action": "",
        "target_row": None,
        "block_signals": False,
        "reads": [],
        "calls": [],
    }
    assert surface.view_model({"action": surface.REANCHOR})["plan"]["calls"] == []
    assert surface.view_model({"action": surface.SELECT_FOR_BOT})["plan"]["calls"] == []
    empty_fleet = surface.view_model(
        {"action": surface.REANCHOR, "bot_id": "bot-a", "selected_bot_id": "bot-b"}
    )
    assert empty_fleet["plan"]["calls"] == [
        ["clearSelection"],
        ["setCurrentCell", -1, -1],
    ]


def test_a_bot_ids_value_the_surface_cannot_read_becomes_an_error_frame():
    """A malformed fleet list took the bridge session down."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 31,
                "method": surface.METHOD,
                "params": {
                    "action": surface.REANCHOR,
                    "bot_id": "bot-a",
                    "bot_ids": 7,
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "TypeError"


def test_the_helper_raises_on_the_same_malformed_fleet_list():
    """The helper and the surface stopped agreeing on a bad fleet list."""
    app()
    table = traced_class(table_classes()["scrumming"])()
    populate(table, THREE, (0, 1, 2))
    with pytest.raises(TypeError):
        bot_selection._reanchor_bot_selection(table, "bot-a", 7)
    with pytest.raises(TypeError):
        surface.reanchor_plan("bot-a", 7, "bot-b", [0, 1, 2])
    with pytest.raises(TypeError):
        bot_selection._select_row_for_bot(table, "bot-a", 7)
    with pytest.raises(TypeError):
        surface.select_for_bot_plan("bot-a", 7, [0, 1, 2])


def test_bridge_registers_the_bot_selection_method():
    """The renderer cannot reach the selection decision through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 30,
                "method": surface.METHOD,
                "params": {
                    "action": surface.REANCHOR,
                    "bot_id": "bridge-bot",
                    "bot_ids": ["other", "bridge-bot"],
                    "selected_bot_id": "other",
                    "filled_rows": [0, 1],
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["plan"]["target_row"] == 1
    assert answer["result"]["plan"]["calls"] == [
        ["clearSelection"],
        ["setCurrentCell", 1, 0],
        ["selectRow", 1],
    ]


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'bot_selection.plan', 'params':"
    " {'action': 'reanchor', 'bot_id': 'probe-bot',"
    " 'bot_ids': ['other', 'probe-bot'], 'selected_bot_id': 'other',"
    " 'filled_rows': [0, 1]}}),"
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
    """Reaching the selection decision pulled Qt into the backend process."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    plan = answered["frame"]["result"]["plan"]
    assert plan["target_row"] == 1
    assert plan["block_signals"] is True
    assert plan["reads"] == [["get_selected_bot_id"], ["item", 1, 0]]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
