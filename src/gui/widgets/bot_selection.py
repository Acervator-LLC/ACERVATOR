"""Row-selection helpers shared by the two bot tables.

Both tables resolve these through module globals on every call, so a
falsifier monkeypatches the name on the table's own module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bot_status_table import BotStatusTable
    from .extractor_bot_table import ExtractorBotTable

try:
    from PySide6.QtCore import QSignalBlocker

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # Selection re-anchor (issue #51)
    # A Qt selection is anchored to a ROW INDEX, not to a row's
    # contents. Both bot tables below rewrite every row in place on the
    # 2000 ms dashboard timer, so a fleet list that arrives in a
    # different order -- which is what deleting one bot does to every
    # row beneath it -- leaves the operator's highlight exactly where
    # it was while a DIFFERENT bot is now underneath it. Measured on
    # the unrepaired tree: select `bot-AAA`, re-render with the two
    # statuses swapped, and the table answers `bot-BBB`; `_cmd("stop")`
    # then dispatched `('bot-BBB', 'stop')`. No operator action in
    # between and nothing on screen that changed.
    #
    # THE REPAIR LIVES ON THE TABLE, NOT ON THE TAB. Measured, not
    # assumed: `BotStatusTable` has two consumers -- `ExchangeTab`
    # below, and `SimulatorTab.mount_bot_status_table`, which resolves
    # THIS class by import and mounts it in the fleet-replay bot area.
    # `ExtractorBotTable` has one, `ExchangeTab`. Repairing the tab
    # would have left the Simulator's copy of the same widget holding
    # the same defect. One function, called by both classes, so the
    # two can never drift apart on a money path.
    #
    # THREE OTHER TABLES REWRITE THEIR ROWS THE SAME WAY AND ARE LEFT
    # ALONE, each for a measured reason. `bot_swarm_list.BotListView`
    # reads no selection at all -- no `selectedItems`, no `currentRow`,
    # no selection signal -- so it has no anchor to lose.
    # `stock_main_window.StockBotTable` sets `SelectRows` and nothing
    # ever reads it: `_start_bot`, `_stop_bot` and `_delete_bot` log
    # "select a bot first" and dispatch nothing, so no selection there
    # reaches a command. `history_tab.HistoryTab._render_page` paints
    # executed TRADES; it carries no bot id and drives no command.
    # Named here rather than repaired -- a repair to any of the three
    # would be a change nothing can observe.
    def _reanchor_bot_selection(
        table: BotStatusTable | ExtractorBotTable,
        previous_bot_id: str,
        bot_ids: list[str],
    ) -> None:
        """Put the highlight back on the BOT it was on, not on its row.

        `previous_bot_id` is read off the table BEFORE the rewrite;
        `bot_ids` is the row->bot map the rewrite just built.
        """
        if not previous_bot_id:
            # Nothing was selected. Selecting a row now would be the
            # timer choosing a bot on the operator's behalf.
            return
        # The steady state is the common case -- same fleet, same
        # order, every 2000 ms. Re-selecting there would re-run Qt's
        # auto-scroll on every tick and fight the operator's own
        # scrolling, so the restore runs only when the anchor moved.
        if table.get_selected_bot_id() == previous_bot_id:
            return
        target = None
        for _row, _bid in enumerate(bot_ids):
            if _bid == previous_bot_id:
                target = _row
                break
        # A row the render SKIPPED carries no column-0 item (the blank
        # row `exchange.15.002` counts). Highlighting one would put the
        # operator's eye on a row `get_selected_bot_id` answers "" for,
        # and `_cmd` would fall back to the OTHER table's selection --
        # MEM-408 in a new place. Treat it as absent.
        if target is not None and table.item(target, 0) is None:
            target = None
        # RE-SELECTING EMITS `itemSelectionChanged`. In `ExchangeTab`
        # that handler sets `_last_clicked_table` and clears the
        # sibling table's selection. That flag records an OPERATOR
        # CLICK; a 2000 ms timer moving it would be a second misroute
        # of the same family as the one this function repairs. The
        # restore is therefore silent, and the flag is asserted
        # unmoved across a refresh in the tests.
        #
        # `QSignalBlocker` and not `blockSignals(True)`: it restores
        # whatever the block state was BEFORE it rather than assuming
        # False, so a caller that had already blocked this table is
        # left blocked, and it cannot leak a blocked table if a line
        # inside raises.
        with QSignalBlocker(table):
            table.clearSelection()
            if target is None:
                # The selected bot left the fleet. Clearing is the safe
                # answer: `_cmd` already logs "Select a bot first."
                # when nothing is selected, so the operator is told.
                # Leaving the old ROW selected is the defect itself.
                table.setCurrentCell(-1, -1)
            else:
                table.setCurrentCell(target, 0)
                table.selectRow(target)

    def _select_row_for_bot(
        table: BotStatusTable | ExtractorBotTable, bot_id: str, bot_ids: list[str]
    ) -> None:
        """Put the highlight on the row whose Detail button was pressed.

        issue #52. The Detail button sits INSIDE A CELL, and a click on
        a cell widget changes no row selection. So the button was the
        one entry point that moved `ExchangeTab._last_clicked_table`
        without moving the selection that flag is supposed to describe:
        `_cmd` then preferred a table holding nothing, fell back, and
        sent Start / Pause / Stop / Restart / Delete to the bot selected
        on the OTHER table -- MEM-408, with real money on it.

        THE REPAIR IS TO MAKE THE BUTTON DO WHAT A ROW CLICK DOES, not
        to write the sibling-clearing rule out a second time.
        `ExchangeTab.__init__` already connects `itemSelectionChanged`
        on both tables to a handler that sets the flag AND clears the
        sibling, and that handler is the only place that rule may live.

        SO THE SIGNAL HERE IS DELIBERATELY NOT BLOCKED. That is the
        opposite of `_reanchor_bot_selection` above, and for the
        opposite reason: the 2000 ms refresh is not an operator and must
        not move the flag, while THIS call IS the operator's click and
        must. Blocking here would leave the sibling selected and the
        defect exactly where it was.

        `bot_ids` is the table's own row->bot map, passed in rather than
        read off the widget for the same reason `_reanchor_bot_selection`
        takes it: a row index means nothing without it.
        """
        if not bot_id:
            return
        target = None
        for _row, _bid in enumerate(bot_ids):
            if _bid == bot_id:
                target = _row
                break
        if target is None:
            # The button outlived its row. Not reachable through the
            # dashboard today -- `setCellWidget` rebuilds every button
            # on every render and each lambda captures that render's bot
            # id -- but selecting SOME row because the right one is gone
            # would be the misroute this repair exists to close.
            return
        if table.item(target, 0) is None:
            # A row the render SKIPPED carries no column-0 item, so
            # `selectedItems()` stays empty and `get_selected_bot_id`
            # answers "" for it -- the empty-preferred-table state that
            # `_cmd` falls back out of. `_reanchor_bot_selection`
            # refuses such a row for the same reason.
            return
        # NO already-on-this-bot EARLY RETURN. One was written here and
        # then taken out, because nothing could see it work: driven
        # against a 40-row table scrolled to the bottom, against an
        # emission counter on `itemSelectionChanged`, and against a
        # ctrl-click two-row selection, the repeat click read the same
        # scroll position, the same zero emissions and the same
        # selected rows with the guard and without it. Qt supplies the
        # idempotence -- it emits only when the selection really
        # changes -- and a branch no drive can tell apart from its own
        # absence is not a guard, it is a claim. The emission count is
        # asserted in the tests instead, where a change in that
        # behaviour would be read as a fact rather than assumed.
        #
        # THE PAIR, and it is the pair `_reanchor_bot_selection` above
        # uses. `get_selected_bot_id` reads TWO fields -- it gates on
        # `selectedItems()` and then INDEXES with `currentRow()` -- and
        # these two lines set one each, so neither is left to the other
        # one's side effects.
        #
        # MEASURED, because "both are needed" would have been a claim:
        # each line was dropped in turn and the whole file's tests
        # still passed, so on this Qt build either call alone moves
        # both fields. The pair is kept anyway -- it says which two
        # fields the operator's click has to move, which is the thing
        # the misroute was made of, and it matches the sibling
        # function. It is not kept on a necessity nothing could show.
        table.setCurrentCell(target, 0)
        table.selectRow(target)
