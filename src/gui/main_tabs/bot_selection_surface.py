"""bot_selection_surface.py -- the bot-table selection view model.

Decides which row of a bot table carries the highlight, and hands the
answer back as plain data: the row to select, the calls the table is
told to make, and whether those calls run silently.

Two decisions live here, and they are the two the Qt helpers make. The
2000 ms dashboard refresh rewrites every row, so the highlight is put
back on the BOT it was on rather than on the row index it sat at, and
that restore is silent because a timer is not the operator. A Detail
button press selects the row the button sits in, and that one is not
silent because it IS the operator's click.

A row the render skipped carries no item in the anchor column, and the
table answers "" for it, so such a row is refused by both decisions.
``filled_rows`` names the rows whose anchor column carries an item.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``bot_selection.plan`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt, and it sits beside the other
surfaces rather than beside ``widgets/bot_selection.py`` because that
package imports Qt in its ``__init__``.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Iterable, Optional

logger = logging.getLogger("acervator.gui.bot_selection_surface")

TableCall = list[object]

METHOD = "bot_selection.plan"

REANCHOR = "reanchor"
SELECT_FOR_BOT = "select_for_bot"

ANCHOR_COLUMN = 0
CLEARED_ROW = -1
CLEARED_COLUMN = -1

REANCHOR_BLOCKS_SIGNALS = True
SELECT_FOR_BOT_BLOCKS_SIGNALS = False

READ_SELECTED_BOT_ID = "get_selected_bot_id"
READ_ANCHOR_ITEM = "item"

CLEAR_SELECTION = "clearSelection"
SET_CURRENT_CELL = "setCurrentCell"
SELECT_ROW = "selectRow"

SELECTION = {
    "anchor_column": ANCHOR_COLUMN,
    "cleared_row": CLEARED_ROW,
    "cleared_column": CLEARED_COLUMN,
    "reanchor_blocks_signals": REANCHOR_BLOCKS_SIGNALS,
    "select_for_bot_blocks_signals": SELECT_FOR_BOT_BLOCKS_SIGNALS,
}


def row_names(bot_ids: Any) -> list:
    """The fleet ids as a list, empty when bot_ids is not a list or tuple."""
    if isinstance(bot_ids, (list, tuple)):
        return list(bot_ids)
    return []


def row_indices(filled_rows: Any) -> list:
    """Every finite row number in filled_rows, sorted, without repeats or flags."""
    if not isinstance(filled_rows, (list, tuple)):
        return []
    found = set()
    for one in filled_rows:
        if isinstance(one, bool) or not isinstance(one, (int, float)):
            continue
        if not math.isfinite(one):
            continue
        found.add(one)
    return sorted(found)


def target_row(bot_id: Any, bot_ids: Iterable[Any]) -> Optional[int]:
    """The first row carrying ``bot_id``, or None when no row carries it.

    First match wins, so a fleet listing one bot twice answers the
    earlier row.
    """
    for row, row_bot_id in enumerate(bot_ids):
        if row_bot_id == bot_id:
            return row
    return None


def build_plan(
    action: str,
    row: Optional[int],
    block_signals: bool,
    reads: list[TableCall],
    calls: list[TableCall],
) -> dict:
    """One decision: the row chosen, the calls it makes, and its silence."""
    return {
        "action": action,
        "target_row": row,
        "block_signals": block_signals,
        "reads": reads,
        "calls": calls,
    }


def reanchor_plan(
    previous_bot_id: Any,
    bot_ids: Iterable[Any],
    selected_bot_id: Any = "",
    filled_rows: Optional[Iterable[int]] = None,
) -> dict:
    """Where the highlight goes after the refresh rewrote every row.

    An empty ``previous_bot_id`` means nothing was selected, and the
    table is left alone rather than the refresh choosing a bot. A table
    already on that bot is left alone too, so the restore cannot fight
    the operator's own scrolling every 2000 ms. A bot that left the
    fleet, and a bot on a row the render skipped, both clear the
    selection instead of leaving a stale row highlighted.
    """
    if not previous_bot_id:
        return build_plan(REANCHOR, None, REANCHOR_BLOCKS_SIGNALS, [], [])
    reads: list[TableCall] = [[READ_SELECTED_BOT_ID]]
    if selected_bot_id == previous_bot_id:
        return build_plan(REANCHOR, None, REANCHOR_BLOCKS_SIGNALS, reads, [])
    row = target_row(previous_bot_id, bot_ids)
    if row is not None:
        reads.append([READ_ANCHOR_ITEM, row, ANCHOR_COLUMN])
        if row not in set(row_indices(filled_rows)):
            row = None
    calls: list[TableCall] = [[CLEAR_SELECTION]]
    if row is None:
        calls.append([SET_CURRENT_CELL, CLEARED_ROW, CLEARED_COLUMN])
    else:
        calls.append([SET_CURRENT_CELL, row, ANCHOR_COLUMN])
        calls.append([SELECT_ROW, row])
    return build_plan(REANCHOR, row, REANCHOR_BLOCKS_SIGNALS, reads, calls)


def select_for_bot_plan(
    bot_id: Any,
    bot_ids: Iterable[Any],
    filled_rows: Optional[Iterable[int]] = None,
) -> dict:
    """Where the highlight goes when a row's Detail button is pressed.

    A click on a cell widget moves no row selection of its own, so the
    row is selected here to match what a row click does. An empty
    ``bot_id``, a bot the fleet no longer lists and a row the render
    skipped each leave the table alone rather than highlighting some
    other bot's row.
    """
    if not bot_id:
        return build_plan(SELECT_FOR_BOT, None, SELECT_FOR_BOT_BLOCKS_SIGNALS, [], [])
    row = target_row(bot_id, bot_ids)
    if row is None:
        return build_plan(SELECT_FOR_BOT, None, SELECT_FOR_BOT_BLOCKS_SIGNALS, [], [])
    reads: list[TableCall] = [[READ_ANCHOR_ITEM, row, ANCHOR_COLUMN]]
    if row not in set(row_indices(filled_rows)):
        return build_plan(
            SELECT_FOR_BOT, None, SELECT_FOR_BOT_BLOCKS_SIGNALS, reads, []
        )
    calls: list[TableCall] = [
        [SET_CURRENT_CELL, row, ANCHOR_COLUMN],
        [SELECT_ROW, row],
    ]
    return build_plan(SELECT_FOR_BOT, row, SELECT_FOR_BOT_BLOCKS_SIGNALS, reads, calls)


def build_view_model(
    action: str,
    bot_id: Any = "",
    bot_ids: Optional[Iterable[Any]] = None,
    selected_bot_id: Any = "",
    filled_rows: Optional[Iterable[int]] = None,
) -> dict:
    """Return the whole surface state as one serialisable dict.

    An action the surface does not name answers a plan with no calls, so
    an unknown request cannot move the highlight.
    """
    rows = row_names(bot_ids)
    filled = row_indices(filled_rows)
    if action == REANCHOR:
        plan = reanchor_plan(bot_id, rows, selected_bot_id, filled)
    elif action == SELECT_FOR_BOT:
        plan = select_for_bot_plan(bot_id, rows, filled)
    else:
        logger.warning("bot selection action not recognised: %r", action)
        plan = build_plan(action, None, False, [], [])
    return {
        "selection": dict(SELECTION),
        "bot_ids": rows,
        "filled_rows": filled,
        "plan": plan,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``bot_selection.plan``.

    Reads ``action``, ``bot_id``, ``bot_ids``, ``selected_bot_id`` and
    ``filled_rows`` from the request parameters. The surface holds no
    state between calls because the Qt helpers hold none.
    """
    asked = params if isinstance(params, dict) else {}
    return build_view_model(
        asked.get("action", ""),
        asked.get("bot_id", ""),
        asked.get("bot_ids"),
        asked.get("selected_bot_id", ""),
        asked.get("filled_rows"),
    )
