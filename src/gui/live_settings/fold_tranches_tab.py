"""Fold Tranches tab of the Live Bot Settings dialog."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor

from .. import design_system as ds
from .fold_tokens import (
    ARBITER_COLUMN_HEADER,
    ARBITER_COLUMN_INDEX,
    ARBITER_NOT_APPLICABLE,
    EXTRACTOR_TRANCHE_BG_HEX,
    EXTRACTOR_TRANCHE_FG_HEX,
    FOLD_CLOSED_TOOLTIP,
    FOLD_CLOSE_RATIO_TOOLTIP,
    FOLD_COLUMN_TOOLTIPS,
    FOLD_COUNTERS_RESET_TOOLTIP,
    FOLD_CYCLE_CAP_TOOLTIP,
    FOLD_DISCARDED_TOOLTIP,
    FOLD_MALFORMED_TOOLTIP,
    FOLD_OLDEST_AGE_TOOLTIP,
    FOLD_OPENED_TOOLTIP,
    FOLD_OPEN_COUNT_TOOLTIP,
    FOLD_OVER_ALLOTMENT_FG_HEX,
    FOLD_PARKED_USD_TOOLTIP,
    FOLD_SOURCE_MANUAL_FG_HEX,
    FOLD_SOURCE_MANUAL_SCRUM,
    FOLD_SOURCE_TOOLTIPS,
    FOLD_TRANCHE_BG_HEX,
    FOLD_TRANCHE_FG_HEX,
    FOLD_UNITS_MARKED_TOOLTIP,
    FOLD_WIRE_DISCARDED_TOOLTIP,
    TRANCHE_FIRE_BTN_INSET_PX,
    TRANCHE_ROW_HEIGHT_PX,
    _arbiter_label,
    _compose_arbiter_tooltip,
    _compose_extractor_tranche_cells,
    _compose_extractor_tranche_tooltip,
    _fold_tranche_source_label,
    compose_cycle_close_ratio,
    compose_units_marked_row,
    fold_display_order,
    fold_table_chrome_px,
    fold_table_max_height_px,
    fold_table_natural_width_px,
    install_health_row,
)
from .fold_chrome import (
    _TrancheRowBorderDelegate,
    build_fold_row_controls,
    fold_sort_order,
    install_despawn_rows,
)

if TYPE_CHECKING:
    from ..bot_live_settings import BotLiveSettingsDialog

logger = logging.getLogger("acervator.gui")


class FoldTranchesTabMixin:
    """The fold queue, its clear controls and Manual Fire."""

    # Supplied by BotLiveSettingsDialog at runtime; declared so a
    # type checker can resolve them. Annotations only: no attribute
    # is created and the runtime base stays `object`.
    _bm: Any
    _bot: Any
    _configure_form: Callable[..., Any]
    _format_age: Callable[..., Any]
    _save_fleet_state_now: Callable[..., Any]
    _wrap_scrollable: Callable[..., Any]

    # ---------------------------------------------------------------
    # Tab 3: Fold Tranches (v3.16.39 P2-VIS, scrumming-only)
    # ---------------------------------------------------------------
    # Surfaces the bot's two-leg cycle machinery per MEM-171 /
    # ADR-004. A SCRUM consumes _main_lots highest-initial_buy_price-
    # first and parks proceeds in _fold_tranches with TWO recorded
    # prices: ref (the SCRUM's sell price) and initial_buy_price
    # (the original buy cost — patent CEILING for re-acquisition,
    # NOT a floor). Leg-2 (FOLD-BACK) fires when current price is
    # BELOW BOTH the ref (binding gate; ensures unit-surplus) AND
    # the initial_buy_price ceiling (patent invariant). Until then,
    # the tranche sits in queue.
    #
    # Operator's pre-2026-05-08 visibility: none. Could only see the
    # cumulative state by pulling persisted state JSON manually.
    # This tab makes the queue first-class.
    def _on_clear_fold_tranches(self: BotLiveSettingsDialog) -> None:
        """Discard this bot's queued fold tranches, after confirming.

        v3.24.44 — operator directive 2026-08-06. Destructive to
        queued INTENT only: no order is placed, and holdings, cost
        basis and target balance are untouched.

        The dialog states the parked-wire-credit consequence because
        clearing opens the absorb window (it is gated on the bot
        holding zero tranches), and the absorb dumps the whole pool
        into a single tranche with no split and no cap reference. On
        a bot with several hundred dollars parked against a
        single-digit cycle cap that mints one permanently un-foldable
        tranche. The operator has to see the number before deciding.
        """
        from PySide6.QtWidgets import QMessageBox

        bot = self._bot
        tranches = list(getattr(bot, "_fold_tranches", []) or [])
        if not tranches:
            QMessageBox.information(
                self, "Clear fold tranches", "This bot has no queued fold tranches."
            )
            return
        if not hasattr(bot, "clear_fold_tranches"):
            QMessageBox.warning(
                self,
                "Clear fold tranches",
                "This bot type does not support clearing tranches.",
            )
            return

        n = len(tranches)
        usd = sum(float(t.get("usd", 0) or 0) for t in tranches)
        units = sum(float(t.get("units", 0) or 0) for t in tranches)
        parked = float(getattr(bot, "_pending_wire_credits", 0.0) or 0.0)

        body = [
            f"Discard {n} queued fold tranche(s) for "
            f"{getattr(bot.config, 'symbol', '')}?",
            "",
            f"    queued USD   ${usd:,.4f}",
            f"    units        {units:.8f}",
            "",
            "This places NO order. Holdings, cost basis and target "
            "balance are unchanged — only the queued intent to buy "
            "back is discarded. The next SCRUM creates fresh "
            "tranches.",
            "",
            "This cannot be undone.",
        ]
        if parked > 1e-9:
            body += [
                "",
                f"WARNING — this bot also holds ${parked:,.4f} in "
                f"pending wire credits. Clearing opens the absorb "
                f"window, and the next SCRUM will move that entire "
                f"amount into a SINGLE tranche. If it exceeds the "
                f"per-cycle cap, that tranche cannot be folded.",
            ]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Clear fold tranches")
        box.setText("\n".join(body))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            return

        try:
            report = bot.clear_fold_tranches(reason="operator (GUI)")
        except Exception as exc:  # noqa: BLE001 - operator surface
            logger.exception("clear_fold_tranches failed: %s", exc)
            QMessageBox.critical(
                self,
                "Clear fold tranches",
                f"Nothing was cleared — the call failed:\n\n{exc}",
            )
            return

        # issue #98 defects 1, 2 and 3.
        #
        # THE RESULT LEADS. The message used to open with
        # "Discarded N tranche(s)" and then say "No order was
        # placed", which is REASSURANCE standing where a RESULT
        # belongs - after a button that appeared to have done
        # nothing, beside a table that had not changed. Read in
        # that position it reads as a failure. The order is now
        # what happened, what the panel shows, whether it reached
        # disk, and only then what did NOT happen.
        #
        # EVERY LINE REPORTS THE STEP THAT ACTUALLY RAN. The panel
        # line and the save line come back from `_settle_after_clear`
        # carrying the real outcome of each, so a refresh that could
        # not run or a save that raised is named here rather than
        # papered over.
        _settled = self._settle_after_clear("Clear fold tranches")
        _now_open = len(getattr(bot, "_fold_tranches", []) or [])
        QMessageBox.information(
            self,
            "Clear fold tranches",
            "\n\n".join(
                [
                    f"Cleared {report.get('count', 0)} fold tranche(s) "
                    f"holding "
                    f"${float(report.get('usd', 0)):,.4f}.",
                    f"This bot now holds {_now_open} open fold " f"tranche(s).",
                    "\n".join(_settled),
                    "No order was placed. Holdings, cost basis and "
                    "target balance are unchanged — only the queued "
                    "intent to buy back is gone.",
                ]
            ),
        )

    def _on_clear_wire_credits(self: BotLiveSettingsDialog) -> None:
        """Discard this bot's parked Smart Wire credits, after
        confirming.

        v3.24.45 — operator directive 2026-08-06. The dialog states
        that this releases an EARMARK rather than moving funds,
        because that is the fact that makes it safe and it is not
        obvious from the label: `_pending_wire_credits` has no order
        or transfer site anywhere in src/, and all bots share one
        exchange wallet, so the cash returns to spendable balance.
        """
        from PySide6.QtWidgets import QMessageBox

        bot = self._bot
        parked = float(getattr(bot, "_pending_wire_credits", 0.0) or 0.0)
        entries = len(getattr(bot, "_pending_wire_ledger", []) or [])
        if parked <= 1e-9 and not entries:
            QMessageBox.information(
                self, "Clear wire credits", "This bot has no parked wire credits."
            )
            return
        if not hasattr(bot, "clear_pending_wire_credits"):
            QMessageBox.warning(
                self,
                "Clear wire credits",
                "This bot type does not support clearing wire credits.",
            )
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Clear wire credits")
        box.setText(
            "\n".join(
                [
                    f"Discard ${parked:,.4f} of parked Smart Wire credit for "
                    f"{getattr(bot.config, 'symbol', '')}?",
                    "",
                    f"    ledger entries   {entries}",
                    "",
                    "This releases an EARMARK, it does not move money. No "
                    "order is placed. All bots share one exchange wallet, so "
                    "the cash simply returns to ordinary spendable balance "
                    "instead of being reserved for a future fold tranche.",
                    "",
                    "This cannot be undone.",
                ]
            )
        )
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            return

        try:
            report = bot.clear_pending_wire_credits(reason="operator (GUI)")
        except Exception as exc:  # noqa: BLE001 - operator surface
            logger.exception("clear_pending_wire_credits failed: %s", exc)
            QMessageBox.critical(
                self,
                "Clear wire credits",
                f"Nothing was cleared — the call failed:\n\n{exc}",
            )
            return

        # issue #98 defects 1, 2 and 3, on the sibling button.
        # Same three steps and the same message order as the fold
        # clear above; see the comment there for why the result
        # leads and the reassurance follows.
        _settled = self._settle_after_clear("Clear wire credits")
        _now_parked = float(getattr(bot, "_pending_wire_credits", 0.0) or 0.0)
        QMessageBox.information(
            self,
            "Clear wire credits",
            "\n\n".join(
                [
                    f"Cleared ${float(report.get('usd', 0)):,.4f} of "
                    f"parked Smart Wire credit.",
                    f"This bot now has ${_now_parked:,.4f} parked.",
                    "\n".join(_settled),
                    "No funds moved. This released an EARMARK only, so "
                    "the cash returns to ordinary spendable balance.",
                ]
            ),
        )

    def _on_clear_lifetime_counters(self: BotLiveSettingsDialog) -> None:
        """Zero this bot's four lifetime tranche counters, after
        confirming.

        issue #133 unit 3, operator directive 2026-08-25: "Lifetime
        tranche counts can be cleared since we are resetting to the
        new standard."

        THE DIALOG STATES THE RECONCILIATION IT BREAKS. The panel
        keeps `opened - closed - discarded == open tranches`, and
        zeroing the three terms while the queue still holds N
        tranches makes that read `0 - 0 - 0 = 0` against N until the
        next scrum opens one. It is a display consequence, not a
        lost tranche, and the operator sees the number before
        deciding.
        """
        from PySide6.QtWidgets import QMessageBox

        bot = self._bot
        _counts = {
            "opened": int(getattr(bot, "_tranches_created_lifetime", 0) or 0),
            "closed": int(getattr(bot, "_tranches_closed_lifetime", 0) or 0),
            "discarded": int(getattr(bot, "_tranches_discarded_lifetime", 0) or 0),
            "malformed": int(getattr(bot, "_tranches_malformed_dropped", 0) or 0),
        }
        if not sum(_counts.values()):
            QMessageBox.information(
                self,
                "Clear lifetime counters",
                "This bot's lifetime tranche counters already read zero.",
            )
            return
        if not hasattr(bot, "clear_lifetime_tranche_counters"):
            QMessageBox.warning(
                self,
                "Clear lifetime counters",
                "This bot type does not support clearing lifetime counters.",
            )
            return

        open_now = len(getattr(bot, "_fold_tranches", []) or [])
        body = [
            f"Set the four lifetime tranche counters for "
            f"{getattr(bot.config, 'symbol', '')} to zero?",
            "",
            f"    opened               {_counts['opened']}",
            f"    closed               {_counts['closed']}",
            f"    discarded            {_counts['discarded']}",
            f"    dropped as malformed {_counts['malformed']}",
            "",
            "This places NO order and removes NO tranche. Open "
            "tranches, parked wire credits, holdings, cost basis and "
            "target balance are all unchanged - this clears the "
            "record of what happened, not what the bot holds.",
            "",
            "This cannot be undone.",
        ]
        if open_now:
            body += [
                "",
                f"NOTE - this bot still holds {open_now} open fold "
                f"tranche(s). The panel reconciles opened minus "
                f"closed minus discarded against that count, so it "
                f"will read 0 against {open_now} until the next "
                f"SCRUM opens one. No tranche is lost.",
            ]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Clear lifetime counters")
        box.setText("\n".join(body))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            return

        try:
            report = bot.clear_lifetime_tranche_counters(reason="operator (GUI)")
        except Exception as exc:  # noqa: BLE001 - operator surface
            logger.exception("clear_lifetime_tranche_counters failed: %s", exc)
            QMessageBox.critical(
                self,
                "Clear lifetime counters",
                f"Nothing was cleared - the call failed:\n\n{exc}",
            )
            return

        # The result leads, then what the panel shows, then whether
        # it reached disk, then what did NOT happen. Same order and
        # the same three steps as the two clears above; see
        # `_on_clear_fold_tranches` for why.
        _settled = self._settle_after_clear("Clear lifetime counters")
        _before = report.get("before", {}) or {}
        QMessageBox.information(
            self,
            "Clear lifetime counters",
            "\n\n".join(
                [
                    f"Cleared {int(report.get('cleared', 0))} counted "
                    f"tranche event(s): opened "
                    f"{int(_before.get('created', 0))}, closed "
                    f"{int(_before.get('closed', 0))}, discarded "
                    f"{int(_before.get('discarded', 0))} and "
                    f"{int(_before.get('malformed', 0))} dropped as "
                    f"malformed.",
                    "All four now read 0 for this bot.",
                    "\n".join(_settled),
                    "No order was placed and no tranche was removed. "
                    f"This bot still holds "
                    f"{len(getattr(bot, '_fold_tranches', []) or [])} "
                    f"open fold tranche(s), its parked wire credits "
                    f"and every holding it had.",
                ]
            ),
        )

    def _paint_fold_tranche_row(self, table: QTableWidget, row: int) -> None:
        """Paint one fold tranche row blue, after its cells exist.

        Operator spec 2026-08-11: the existing tranches are the
        blue ones. Before this, "blue" was only two per-cell
        foregrounds; the row background was the theme's
        alternating brush. This paints the actual row.

        Called AFTER the row's items are set, because it reads
        each item to decide whether that cell already owns a
        foreground.

        SEMANTIC FOREGROUNDS ARE NEVER OVERWRITTEN. The Status
        cell carries green for "price gate open" and amber for
        "price gate shut"; the Source cell carries `#00ccff` on a
        manual-scrum tranche -- one an operator's own Manual Fire
        SOLD into being (issue #98 defect 5 corrected the word on
        that cell; the colour and the rows carrying it are the
        same ones). Those colours are trading meaning,
        not decoration, and this is a visual change, so they are
        left exactly as they are. All three were measured against
        this fill and clear WCAG AA — 8.65:1, 5.42:1 and 6.12:1 —
        so none of them needed re-tuning either.

        Detection is by brush style rather than by a hard-coded
        column list. `QTableWidgetItem.foreground()` returns a
        NoBrush brush when nothing was set, so a cell that later
        gains a semantic colour is respected automatically instead
        of silently losing it to a stale column number here.
        """
        bg = QBrush(QColor(FOLD_TRANCHE_BG_HEX))
        fg = QBrush(QColor(FOLD_TRANCHE_FG_HEX))
        for col in range(table.columnCount()):
            cell = table.item(row, col)
            if cell is None:
                # Column 9 holds the Fire button as a cell WIDGET
                # and has no item. It still gets a background-only
                # item: the widget is drawn on top of the cell, so
                # this fills the margin around the button and, more
                # importantly, gives the delegate a fill to read so
                # the container edge does not stop one cell short
                # of the row's end.
                cell = QTableWidgetItem("")
                table.setItem(row, col, cell)
            cell.setBackground(bg)
            if cell.foreground().style() == Qt.BrushStyle.NoBrush:
                cell.setForeground(fg)

    def _paint_extractor_tranche_rows(
        self,
        table: QTableWidget,
        ext_rows: list[dict],
        start_row: int,
        now_ts: float,
    ) -> None:
        """Fill and paint the Extractor Tranche rows of the table.

        Operator spec 2026-08-11: "It will be denoted in with a red
        background and white text since existing tranches are blue."

        PER-CELL, BECAUSE THAT IS THE MECHANISM ALREADY HERE. The
        Source column sets a per-cell foreground on operator-
        initiated tranches, and the only `setBackground` precedent
        in this GUI pairs a per-cell background brush with a
        per-cell foreground brush. There is no item delegate and no
        background role anywhere in this repository, so there is no
        row-wide mechanism to reuse and no second mechanism is
        introduced here.

        Per-cell means EVERY column gets painted. Column 9 matters
        most: on a fold row it holds a widget and has no item at
        all, so leaving it out would end the red band one cell
        short and show a blue Fire button on a red row.

        The blue rows are not touched. This only ever writes rows at
        `start_row` and beyond, which is where the caller has
        already reserved space past the last fold tranche.
        """
        bg = QBrush(QColor(EXTRACTOR_TRANCHE_BG_HEX))
        fg = QBrush(QColor(EXTRACTOR_TRANCHE_FG_HEX))
        for offset, row_data in enumerate(ext_rows):
            target_row = start_row + offset
            texts = _compose_extractor_tranche_cells(row_data, now_ts)
            tip = _compose_extractor_tranche_tooltip(row_data)
            for col, text in enumerate(texts):
                cell = QTableWidgetItem(text)
                cell.setBackground(bg)
                cell.setForeground(fg)
                cell.setToolTip(tip)
                table.setItem(target_row, col, cell)

            # Item 5 — the Arbiter cell, at column 10.
            #
            # NOT FROM THE CELL COMPOSER, AND THE SPLIT IS
            # DELIBERATE. `_compose_extractor_tranche_cells` is a
            # pure text formatter and its ten strings are pinned by
            # a test that counts them. This cell is not a piece of
            # text: it is a CONTROL that has to carry the tranche's
            # identity to a click handler, which a list of strings
            # cannot do. Growing that composer to eleven would have
            # changed a settled contract to smuggle in something
            # that is not its kind of thing, and the button would
            # still have had to be built here.
            #
            # THE ITEM AND THE BUTTON ARE BOTH REAL. The item
            # carries the same word the button shows, so the model
            # states the stored value and a reader is not forced to
            # interrogate a widget; and the row's red band reaches
            # the end of the table instead of stopping one cell
            # short — the exact defect the Fire column caused on
            # fold rows. The button is painted on top of it.
            arb_value = row_data.get("arbiter")
            arb_cell = QTableWidgetItem(_arbiter_label(arb_value))
            arb_cell.setBackground(bg)
            arb_cell.setForeground(fg)
            arb_cell.setToolTip(_compose_arbiter_tooltip(arb_value))
            table.setItem(target_row, ARBITER_COLUMN_INDEX, arb_cell)

            arb_btn = QPushButton(_arbiter_label(arb_value))
            arb_btn.setToolTip(_compose_arbiter_tooltip(arb_value))
            # Same margin mechanism as the Fire button, and for the
            # same measured reason: `setCellWidget` sizes a widget
            # to the whole cell rect and paints it over the
            # delegate, so a full-height button hides the container
            # edge at its own column and the row reads as an
            # open-ended strip. The fill matches the row so the red
            # band stays continuous; the border and text are white
            # on `#b3261e`, the pair item 4 measured at 6.54:1.
            _arb_inset = TRANCHE_FIRE_BTN_INSET_PX // 2
            arb_btn.setStyleSheet(
                f"QPushButton {{ background: "
                f"{EXTRACTOR_TRANCHE_BG_HEX}; color: "
                f"{EXTRACTOR_TRANCHE_FG_HEX}; border: 1px solid "
                f"{EXTRACTOR_TRANCHE_FG_HEX}; padding: 2px 8px; "
                f"margin: {_arb_inset}px 0px; }} "
                f"QPushButton:hover {{ background: "
                f"{EXTRACTOR_TRANCHE_FG_HEX}; color: "
                f"{EXTRACTOR_TRANCHE_BG_HEX}; }}"
            )

            # CAPTURE IDENTITY, NEVER THE ROW INDEX — the Fire
            # button's own rule, and it matters more here. This
            # table is built once and never refreshed, while the
            # child Extractors keep ticking behind it on the same
            # thread's timers, so a position can close and another
            # open while this snapshot sits on screen. `tranche_id`
            # is `bot_id|pair|opened_at`: it does not depend on any
            # list position, and `opened_at` stops a reopened
            # position on the same pair from inheriting the row.
            # `child_bot_id` is captured too, because rows from
            # several Extractors are merged into one list and the
            # write must reach the child that owns this one.
            _arb_id = str(row_data.get("tranche_id", "") or "")
            _arb_child = str(row_data.get("child_bot_id", "") or "")
            _arb_item = arb_cell
            arb_btn.clicked.connect(
                lambda _checked=False, tid=_arb_id, cid=_arb_child, btn=arb_btn, item=_arb_item: self._on_arbiter_toggle_clicked(
                    tid, cid, btn, item
                )
            )
            table.setCellWidget(target_row, ARBITER_COLUMN_INDEX, arb_btn)

            # NO FIRE BUTTON, DELIBERATELY. `manual_fire_tranche`
            # indexes `_fold_tranches`; a button here would dispatch
            # a real fold-back against whichever fold tranche
            # happened to occupy that index. The parent does not
            # close a child's position — the Extractor's own bullish
            # exit does, and item 1 books the return. Column 9 holds
            # a painted em dash instead, set in the loop above.

    # -- issue #98 defects 1 and 3 - the operator can SEE the clear --
    #
    # WHAT WAS WRONG. Both Clear buttons worked. The trade log
    # proves it on BTC bot `7c39c7a2`: "WIRE CREDITS CLEARED ...
    # $343.6824" and "FOLD TRANCHES CLEARED ... 42 tranche(s)".
    # What the operator SAW was a panel that had not moved. Driven
    # offscreen against a stub bot, with the confirmation accepted:
    #
    #     BEFORE  table rows 58   bot tranches 58   label "58"
    #     AFTER   table rows 58   bot tranches  0   label "58"
    #             clear button still "Clear 58 Fold Tranche(s)",
    #             still enabled, 58 Fire buttons still live
    #
    # and neither clear reached disk. Both bot methods mutate memory
    # and leave the write to the 60-second rolling save
    # (`periodic_save`, nested inside `main()` in `main.py`), so a
    # clear followed by a close inside that
    # window restored every record the operator had just destroyed.
    #
    # NEITHER REPAIR TOUCHES `scrumming_bot.py`. The clear itself is
    # correct and is not changed. The refresh is this dialog's own
    # widget tree, and the save is a call the CALLER can make - the
    # precedent is Reset-all-errors, which calls `save_all_state()`
    # inside its click in `MainWindow._reset_all_errors`
    # (`src/gui/main_window.py`) and states the same
    # reason.
    FOLD_TRANCHES_TAB_LABEL = "Fold Tranches"

    def _install_fold_tranches_tab(self, tabs: QTabWidget) -> QWidget:
        """Build the Fold Tranches tab, add it, and remember it.

        ONE INSTALL SITE, so the handle a later refresh swaps is
        never a second bookkeeping step somebody can forget. The
        tests drive this method rather than re-implementing the two
        lines, which is what makes them a test of the shipped
        wiring.
        """
        page = self._wrap_scrollable(self._create_fold_tranches_tab())
        tabs.addTab(page, self.FOLD_TRANCHES_TAB_LABEL)
        self._fold_tab_page = page
        return page

    def _refresh_fold_tranches_tab(self) -> str:
        """Rebuild the Fold Tranches tab in place. Return a status.

        Returns "refreshed", or a sentence naming why it did not.
        THE STRING IS LOAD-BEARING: the message the operator reads
        after a clear quotes it, so a rebuild that could not run
        says so instead of the panel quietly lying twice.

        THE TAB IS FOUND BY WIDGET IDENTITY, NOT BY A STORED INDEX.
        `indexOf` asks the tab bar where the page actually is, so a
        tab added, hidden or reordered anywhere else in this dialog
        cannot make the refresh rebuild somebody else's tab. A
        stored integer could.

        `removeTab` + `insertTab` AT THE SAME INDEX, so no other tab
        renumbers and the operator keeps their place in the dialog.
        `removeTab` does not delete the page - it reparents it to
        nothing - so the old page is deleted here explicitly.
        Without that, every clear would leak a whole tab's widget
        tree for the life of the dialog.

        THE DELEGATE SURVIVES BECAUSE THE BUILDER REBINDS IT.
        `setItemDelegate` does not take ownership, so the table's
        delegate is held on `self`; the rebuild overwrites that
        attribute with the new table's delegate, and the old one
        goes with the old page.
        """
        tabs = getattr(self, "_tabs", None)
        page = getattr(self, "_fold_tab_page", None)
        if tabs is None or page is None:
            return "not refreshed: this dialog has no Fold " "Tranches tab installed"
        try:
            index = tabs.indexOf(page)
        except Exception as exc:  # R28-OK: display-only rebuild
            logger.warning(
                "Fold Tranches refresh could not locate its tab " "(%s: %s)",
                type(exc).__name__,
                exc,
            )
            return (
                f"not refreshed: the tab could not be located "
                f"({type(exc).__name__})"
            )
        if index < 0:
            return "not refreshed: the Fold Tranches tab is no " "longer in this dialog"
        label = tabs.tabText(index)
        was_current = tabs.currentIndex() == index
        try:
            fresh = self._wrap_scrollable(self._create_fold_tranches_tab())
        except Exception as exc:  # R28-OK: display-only rebuild
            logger.exception("Fold Tranches refresh raised while rebuilding " "the tab")
            return (
                f"not refreshed: rebuilding the tab raised "
                f"{type(exc).__name__}: {exc}"
            )
        tabs.removeTab(index)
        tabs.insertTab(index, fresh, label)
        self._fold_tab_page = fresh
        if was_current:
            tabs.setCurrentIndex(index)
        page.setParent(None)
        page.deleteLater()
        return "refreshed"

    def _fold_panel_shows(self) -> dict:
        """Report what the Fold Tranches tab shows RIGHT NOW.

        Read off the widgets, never off the bot. That is the whole
        value of it: the pin below compares this dict against the
        bot's own numbers, and two reads of one expression would
        agree whatever the panel displayed.

        `fold_rows` subtracts the Extractor rows. Those are appended
        after every fold tranche and are a child's lease, not this
        bot's inventory.
        """
        table = getattr(self, "_fold_tranche_table", None)
        lbl = getattr(self, "_fold_open_count_lbl", None)
        btn = getattr(self, "_fold_clear_btn", None)
        wire = getattr(self, "_fold_wire_btn", None)
        timer = getattr(self, "_fold_despawn_timer_lbl", None)
        preview = getattr(self, "_fold_despawn_preview_lbl", None)
        # issue #98 defects 7 and 9 - the three surfaces this unit
        # added, reported the same way as the six above: read off
        # the WIDGET, never off the bot or off a stored key. The
        # order is asked of the combo box rather than of
        # `fold_sort_order`, because a reporter that read the state
        # both controls are supposed to reflect would agree with
        # itself whatever the panel displayed.
        units = getattr(self, "_fold_units_marked_lbl", None)
        sort_box = getattr(self, "_fold_sort_combo", None)
        filter_box = getattr(self, "_fold_filter_edit", None)
        # issue #133 unit 3 - the five counter figures and the button
        # that clears them. `discarded` and `reset` are None when the
        # panel renders no such row, which is a DIFFERENT answer from
        # "0": the discarded row is hidden at zero, and the reset row
        # is hidden until an operator has cleared.
        opened = getattr(self, "_fold_opened_lbl", None)
        closed = getattr(self, "_fold_closed_lbl", None)
        # NAMED `ratio_row`, NOT `ratio`. The TA archetype reads a
        # local called `ratio` as a dimensionless quantity and
        # flagged the `is not None` beside it as a units mismatch.
        # This binding is a QLabel.
        ratio_row = getattr(self, "_fold_ratio_lbl", None)
        discarded = getattr(self, "_fold_discarded_lbl", None)
        malformed = getattr(self, "_fold_malformed_lbl", None)
        reset = getattr(self, "_fold_counters_reset_lbl", None)
        counters = getattr(self, "_fold_counters_btn", None)
        rows = None
        if table is not None:
            rows = max(
                0,
                table.rowCount() - int(getattr(self, "_fold_ext_row_count", 0) or 0),
            )
        elif lbl is not None:
            # No table means the builder took its empty-queue
            # branch, which renders the "fold queue is empty" note
            # and no rows at all. That is zero rows, not "unknown".
            rows = 0
        return {
            "fold_rows": rows,
            "open_tranches_label": (lbl.text() if lbl is not None else None),
            "clear_button_text": (btn.text() if btn is not None else None),
            "clear_button_enabled": (
                bool(btn.isEnabled()) if btn is not None else None
            ),
            "wire_button_enabled": (
                bool(wire.isEnabled()) if wire is not None else None
            ),
            "despawn_timer_text": (timer.text() if timer is not None else None),
            "despawn_preview_text": (preview.text() if preview is not None else None),
            "units_marked_text": (units.text() if units is not None else None),
            "row_order": (sort_box.currentText() if sort_box is not None else None),
            "row_filter": (filter_box.text() if filter_box is not None else None),
            "lifetime_opened_text": (opened.text() if opened is not None else None),
            "lifetime_closed_text": (closed.text() if closed is not None else None),
            "cycle_ratio_text": (ratio_row.text() if ratio_row is not None else None),
            "lifetime_discarded_text": (
                discarded.text() if discarded is not None else None
            ),
            "malformed_text": (malformed.text() if malformed is not None else None),
            "counters_reset_text": (reset.text() if reset is not None else None),
            "counters_button_text": (counters.text() if counters is not None else None),
            "counters_button_enabled": (
                bool(counters.isEnabled()) if counters is not None else None
            ),
        }

    def _settle_after_clear(self, what: str) -> list[str]:
        """Save, rebuild the tab, pin the result, report the lines.

        ONE PATH FOR BOTH CLEAR BUTTONS. They discard different
        things and their confirmations differ, but what has to
        happen AFTER an accepted clear is the same three steps, and
        two copies of them would drift the first time either moved.

        THE ORDER IS SAVE, THEN REFRESH. The durable write is the
        one a crash can take away; the rebuild only reads memory
        that is already correct. Saving first means a crash between
        the two costs a stale panel, not a restored tranche.
        """
        import contextlib
        import time as _clock

        _t0 = _clock.monotonic()
        saved, why = self._save_fleet_state_now(what)
        refresh = self._refresh_fold_tranches_tab()
        _elapsed = _clock.monotonic() - _t0

        shows = self._fold_panel_shows()
        _open = len(getattr(self._bot, "_fold_tranches", []) or [])
        _parked = float(getattr(self._bot, "_pending_wire_credits", 0.0) or 0.0)
        with contextlib.suppress(Exception):
            from src.core.signal_contract import emit as _fold_emit

            _fold_emit(
                "gui.04.002.postcondition.clear_settled",
                actual={
                    "fold_rows": shows["fold_rows"],
                    "open_tranches_label": shows["open_tranches_label"],
                    "clear_button_enabled": shows["clear_button_enabled"],
                    "wire_button_enabled": shows["wire_button_enabled"],
                    "saved": saved,
                },
                expected={
                    "fold_rows": _open,
                    "open_tranches_label": str(_open),
                    "clear_button_enabled": bool(_open),
                    "wire_button_enabled": _parked > 1e-9,
                    "saved": True,
                },
                duration=_elapsed,
                context={
                    "bot_id": getattr(self._bot, "bot_id", "?"),
                    "cleared": what,
                    "refresh": refresh,
                    "save_reason": why,
                    "clear_button_text": shows["clear_button_text"],
                },
            )

        lines = []
        if refresh == "refreshed":
            lines.append(
                "The panel behind this message has been rebuilt "
                "and now shows the new state."
            )
        else:
            lines.append(
                f"The panel was {refresh}. Close and reopen this "
                f"dialog to see the new state."
            )
        if saved:
            lines.append("Saved to disk.")
        else:
            lines.append(
                f"NOT SAVED TO DISK - {why}. The change holds in "
                f"memory, and the platform's rolling save should "
                f"write it within 60 seconds; a restart before "
                f"that would bring it back."
            )
        return lines

    def _create_fold_tranches_tab(self) -> QWidget:
        import time as _time

        # The repo's ONE admission rule, imported the way this
        # module imports every other trading symbol: locally,
        # so building a tab never drags the trading package in
        # at module import time. The Stack Tranches tab reads
        # its own ledger through this same helper.
        from ...trading.bot_container import (
            as_finite_float as _as_finite_float,
        )

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        # issue #98 defect 1 — THE READ-BACK HANDLES, CLEARED FIRST.
        # `_refresh_fold_tranches_tab` rebuilds this whole widget
        # and then asks the REBUILT surface what it shows, so the
        # pin compares the panel against the bot rather than
        # comparing a local variable to itself. Cleared here rather
        # than only assigned below, because a rebuild that takes the
        # empty-queue branch builds no table at all and a stale
        # handle from the previous build would answer for it.
        self._fold_tranche_table = None
        self._fold_open_count_lbl = None
        self._fold_clear_btn = None
        self._fold_wire_btn = None
        self._fold_ext_row_count = 0
        # The two despawn rows, cleared here for the same reason as
        # the four handles above: a rebuild that raised before the
        # rows were built would otherwise leave the previous
        # build's labels answering for the new panel.
        self._fold_despawn_timer_lbl = None
        self._fold_despawn_preview_lbl = None
        # issue #98 defects 7 and 9 - same reason again. The
        # allotment label, the two reach controls and the filter's
        # source text are all rebuilt below, and a stale handle
        # from the previous build would answer for the new panel.
        self._fold_units_marked_lbl: QLabel | None = None
        self._fold_sort_combo: QComboBox | None = None
        self._fold_filter_edit: QLineEdit | None = None
        self._fold_row_texts: list[list[str]] = []
        # issue #133 unit 3 - the five counter surfaces and the
        # button that clears them, cleared first for the reason the
        # handles above are: two of these rows are CONDITIONAL, so a
        # rebuild that stops rendering one would otherwise leave the
        # previous build's label answering for the new panel.
        self._fold_opened_lbl: QLabel | None = None
        self._fold_closed_lbl: QLabel | None = None
        self._fold_ratio_lbl: QLabel | None = None
        self._fold_discarded_lbl: QLabel | None = None
        self._fold_malformed_lbl: QLabel | None = None
        self._fold_counters_reset_lbl: QLabel | None = None
        self._fold_counters_btn: QPushButton | None = None

        tranches = list(getattr(self._bot, "_fold_tranches", []) or [])
        # Item 4 (2026-08-11) — Extractor Tranches leased against
        # this bot's asset, read from the child that owns them.
        # A COMPUTED VIEW, kept deliberately separate from
        # `tranches` above: these are NOT in `_fold_tranches` and
        # must never be merged into it, because that list is read by
        # the fold gate, the fold buy set, the per-cycle cap packing
        # loop and the manual-fire index. They are rendered in the
        # same table and nowhere else.
        ext_rows: list[dict] = []
        try:
            _reader = getattr(self._bot, "open_extractor_tranches", None)
            if callable(_reader):
                _raw = _reader()
                if isinstance(_raw, list):
                    ext_rows = [r for r in _raw if isinstance(r, dict)]
        except Exception as _ext_exc:  # R28-OK: display-only listing
            logger.warning(
                "Extractor Tranche listing failed for bot %s: %s: "
                "%s — fold tranches still shown.",
                getattr(self._bot, "bot_id", "?"),
                type(_ext_exc).__name__,
                _ext_exc,
            )
            ext_rows = []
        now_ts = _time.time()
        created_lifetime = int(getattr(self._bot, "_tranches_created_lifetime", 0) or 0)
        closed_lifetime = int(getattr(self._bot, "_tranches_closed_lifetime", 0) or 0)

        # --- Summary section ---
        summary = QGroupBox("Fold-Tranche Cycle Health")
        sf = QFormLayout(summary)
        self._configure_form(sf)

        open_count = len(tranches)

        # A REFUSED CONTRIBUTOR IS COUNTED, NOT DROPPED.
        # Silently skipping an unreadable tranche reports a
        # parked total LOWER than the truth with nothing on
        # the panel saying so, which is the shape of the
        # claim-total defect of 2026-08-10: $2,000 reported
        # against a true $3,000, with zero log lines. The
        # count rides beside the number instead.
        #
        # ONE BAD ENTRY USED TO POISON THE WHOLE TOTAL. This
        # was a `sum`, so a single `nan` or `inf` took the
        # parked figure to "$nan"/"$inf", and an int above
        # the float maximum raised OverflowError out of the
        # sum itself, with no `try` on the path to the click.
        #
        # `or 0` IS GONE. It mapped None, "" and False onto
        # the int 0 before any guard could see them, so an
        # ABSENCE was priced at a confident $0.0000.
        # `t.get("usd", 0)` still defaults an ABSENT key to
        # 0, which is what it rendered before and still
        # renders.
        parked_usd = 0.0
        parked_unreadable = 0
        for _pt in tranches:
            _pt_usd = _as_finite_float(_pt.get("usd", 0))
            if _pt_usd is None:
                parked_unreadable += 1
            else:
                parked_usd += _pt_usd

        # Oldest tranche age — handle missing created_ts
        # (pre-v3.16.39 tranches) by skipping them in the
        # max() and reporting "—".
        #
        # A TYPE IS NOT A DOMAIN, AND THIS GUARD WAS THE
        # EXAMPLE THAT PROVED IT. Exact type closed the TYPE
        # and stopped `True` being arithmetic'd as 1.0, which
        # dated a tranche to the epoch and reported an age of
        # about 56 years. It did NOT close the VALUE:
        # `type(inf) is float` is True and `inf > 0` is True,
        # so `inf` was admitted, and `int(seconds)` inside
        # `_format_age` then raised OverflowError. An int
        # above the float maximum was admitted the same way
        # and raised from `float()`. Neither site sits inside
        # a `try`, so the Bot Settings dialog would not open.
        #
        # `as_finite_float` closes both. It bounds huge ints
        # with an INTEGER comparison rather than
        # `math.isfinite`, which raises on the very input it
        # would be added to reject.
        ages_sec = []
        for t in tranches:
            cts = _as_finite_float(t.get("created_ts"))
            if cts is not None and cts > 0:
                ages_sec.append(now_ts - cts)
        if ages_sec:
            oldest = max(ages_sec)
            oldest_str = self._format_age(oldest)
        elif tranches:
            oldest_str = "— (pre-v3.16.39 tranches, no timestamp)"
        else:
            oldest_str = "no open tranches"

        # Cycle close ratio — issue #98 defect 4. The arithmetic,
        # the "nothing left to fold back" case and the colour band
        # all live in `compose_cycle_close_ratio`, which is pure and
        # carries the definition it implements. Read there first.
        discarded_lifetime = int(
            getattr(self._bot, "_tranches_discarded_lifetime", 0) or 0
        )
        ratio_str, ratio_colour = compose_cycle_close_ratio(
            created_lifetime, closed_lifetime, discarded_lifetime
        )

        # issue #98 defect 6 - every row this unit owns now carries
        # the operator's own tooltip standard, on BOTH the words and
        # the number. `install_health_row` is the one call that puts
        # it on both; a tooltip on the value alone leaves the label
        # the operator points at bare.
        open_count_lbl = QLabel(str(open_count))
        self._fold_open_count_lbl = open_count_lbl
        install_health_row(
            sf, "Open tranches:", open_count_lbl, FOLD_OPEN_COUNT_TOOLTIP
        )

        parked_str = f"${parked_usd:,.4f}"
        if parked_unreadable:
            parked_str += f"  (+{parked_unreadable} unreadable)"
        parked_lbl = QLabel(parked_str)
        parked_lbl.setStyleSheet(
            "font-weight: bold; font-size: 13px; " f"color: {ds.FOLD_RATIO_AMBER};"
        )
        install_health_row(
            sf, "Parked USD (in fold queue):", parked_lbl, FOLD_PARKED_USD_TOOLTIP
        )

        install_health_row(
            sf, "Oldest tranche age:", QLabel(oldest_str), FOLD_OLDEST_AGE_TOOLTIP
        )

        # issue #98 defect 9 - THE ALLOTMENT TOTAL. The panel
        # printed per-row Units and nothing else, so a queue that
        # had marked 1.99x the units the bot holds (PUMP/USD,
        # 2026-08-23) looked exactly like one that had marked half.
        # Both quantities are stored: the sum of tranche `units`,
        # and `_current_holdings` on the bot. The row states them
        # and their ratio, and attributes nothing.
        _units_text, _units_colour = compose_units_marked_row(
            tranches, getattr(self._bot, "_current_holdings", None)
        )
        _units_lbl = QLabel(_units_text)
        if _units_colour:
            # The same red the close-ratio verdict on this form and
            # the over-cap row on the Settings tab already use.
            _units_lbl.setStyleSheet(f"color: {_units_colour};")
        self._fold_units_marked_lbl = _units_lbl
        install_health_row(
            sf,
            "Units marked (queue vs held):",
            _units_lbl,
            FOLD_UNITS_MARKED_TOOLTIP,
        )

        # issue #103 - the despawn window is usable. The count is
        # already on this tab; the control that acts on it was two
        # tabs away with nothing naming it. These two rows name the
        # setting and print what it would remove BEFORE it is
        # armed. They add no button: despawn is the age-driven
        # removal, clear is the manual one, and the operator's
        # model has exactly three verbs.
        install_despawn_rows(self, sf, tranches, now_ts)

        # issue #133 unit 3 - HELD, not built inline. The Clear
        # Lifetime Counters button rebuilds this tab in its own
        # click, and `_fold_panel_shows` has to read the rebuilt
        # LABEL rather than re-read the bot; two reads of one
        # expression would agree whatever the panel displayed.
        self._fold_opened_lbl = QLabel(str(created_lifetime))
        install_health_row(
            sf,
            "Lifetime tranches opened:",
            self._fold_opened_lbl,
            FOLD_OPENED_TOOLTIP,
        )
        self._fold_closed_lbl = QLabel(str(closed_lifetime))
        install_health_row(
            sf,
            "Lifetime tranches closed (fold-back fired):",
            self._fold_closed_lbl,
            FOLD_CLOSED_TOOLTIP,
        )

        ratio_lbl = QLabel(ratio_str)
        self._fold_ratio_lbl = ratio_lbl
        # THE COLOUR IS NOT DECIDED HERE ANY MORE. It used to be a
        # second arithmetic beside the text's, over `created` rather
        # than the denominator the text printed, so the words and
        # the colour could describe different quantities. One
        # composer now answers both.
        if ratio_colour:
            ratio_lbl.setStyleSheet(f"color: {ratio_colour};")
        install_health_row(
            sf,
            "Cycle close ratio (folded / opened minus discarded):",
            ratio_lbl,
            FOLD_CLOSE_RATIO_TOOLTIP,
        )

        # v3.24.44 — discarded tranches are counted separately from
        # closed ones, because a discard did NOT fold. Shown only
        # once non-zero so the panel stays quiet on bots that have
        # never been cleared.
        #
        # THE LABEL NO LONGER SAYS "cleared". Issue #98 defect 4: a
        # clear is one of four ways a tranche is discarded. The
        # despawn sweep, a detonation and the fold guard's
        # unreadable-record drop write this same counter, so naming
        # one of the four made the other three read as missing.
        if discarded_lifetime:
            self._fold_discarded_lbl = QLabel(str(discarded_lifetime))
            install_health_row(
                sf,
                "Lifetime tranches discarded (not folded back):",
                self._fold_discarded_lbl,
                FOLD_DISCARDED_TOOLTIP,
            )

        # -- issue #98 defect 10 - three persisted quantities the
        # panel never showed ------------------------------------
        #
        # All three are written to the state file and read back on
        # restore, and none of them had a row on the surface that
        # owns them.
        #
        # 1. `_wire_credits_discarded_lifetime`. The Clear Wire
        #    Credits button on THIS tab writes it, and the tranche
        #    clear's own lifetime row sits four lines above. The
        #    two buttons were not symmetric in what they reported:
        #    BTC carried $343.68 and ETH $213.90 with nothing on
        #    screen saying so. It follows the tranche row's
        #    convention exactly - shown once it is non-zero, so a
        #    bot that has never cleared stays quiet.
        #
        # 2. `_tranches_malformed_dropped`. ALWAYS SHOWN, and that
        #    departs from the convention above on purpose. A zero
        #    here is a positive statement - no stored tranche was
        #    ever unreadable - and hiding it makes "none were
        #    dropped" indistinguishable from "this panel does not
        #    count drops". It was 0 on all 38 bots when the panel
        #    was evaluated, which is exactly the reading a hidden
        #    row would have thrown away.
        #
        # 3. `_fold_cycle_cap_consumed`, beside the budget it is
        #    spent from. It decides how much of this queue one
        #    cycle may take, so consumed alone is half a number:
        #    the Settings tab already prints the pair, and this row
        #    reads those same two fields rather than a second
        #    arithmetic of its own.
        _wire_discarded = _as_finite_float(
            getattr(self._bot, "_wire_credits_discarded_lifetime", 0.0)
        )
        if _wire_discarded is not None and _wire_discarded > 1e-9:
            install_health_row(
                sf,
                "Lifetime wire credits discarded (cleared):",
                QLabel(f"${_wire_discarded:,.4f}"),
                FOLD_WIRE_DISCARDED_TOOLTIP,
            )

        _malformed = int(getattr(self._bot, "_tranches_malformed_dropped", 0) or 0)
        _malformed_lbl = QLabel(str(_malformed))
        if _malformed:
            # Same red the close-ratio verdict uses on this form. A
            # dropped tranche is a record the bot could not read,
            # which is a data fault rather than a trading outcome.
            _malformed_lbl.setStyleSheet(f"color: {FOLD_OVER_ALLOTMENT_FG_HEX};")
        self._fold_malformed_lbl = _malformed_lbl
        install_health_row(
            sf,
            "Tranches dropped as malformed:",
            _malformed_lbl,
            FOLD_MALFORMED_TOOLTIP,
        )

        # issue #133 unit 3 - THE RESET IS ON THE PANEL, not only in
        # the log. Four counters reading zero look identical whether
        # the bot has never traded or an operator cleared 4,925
        # opens, and the row that tells them apart is this one. Shown
        # once non-zero, the convention the discarded row above and
        # the wire-discarded row already keep.
        _reset_ts = _as_finite_float(
            getattr(self._bot, "_tranches_counters_reset_ts", 0.0)
        )
        if _reset_ts is not None and _reset_ts > 0:
            self._fold_counters_reset_lbl = QLabel(
                _time.strftime("%Y-%m-%d %H:%M", _time.localtime(_reset_ts))
            )
            install_health_row(
                sf,
                "Lifetime counters last cleared:",
                self._fold_counters_reset_lbl,
                FOLD_COUNTERS_RESET_TOOLTIP,
            )

        _cap_budget = _as_finite_float(getattr(self._bot, "cycle_growth_cap_usd", 0.0))
        _cap_consumed = _as_finite_float(
            getattr(self._bot, "_fold_cycle_cap_consumed", 0.0)
        )
        _cap_text = (
            f"${_cap_consumed:,.4f} spent of ${_cap_budget:,.4f}"
            if _cap_budget is not None and _cap_consumed is not None
            else "- (unreadable)"
        )
        install_health_row(
            sf, "Fold budget this cycle:", QLabel(_cap_text), FOLD_CYCLE_CAP_TOOLTIP
        )

        layout.addWidget(summary)

        # --- Clear tranches (operator directive 2026-08-06) ---
        # "let's just clear the existing tranche values and assume
        # them as invalid. They were calculated without any outgoing
        # safety rate math, have languished for weeks in some cases,
        # and just need to be produced fresh."
        clear_btn = QPushButton(
            f"Clear {open_count} Fold Tranche(s)"
            if open_count
            else "Clear Fold Tranches"
        )
        clear_btn.setEnabled(bool(open_count))
        clear_btn.setToolTip(
            "Discard every queued fold tranche for this bot.\n\n"
            "Places NO order. Holdings, cost basis and target balance "
            "are untouched — only the queued intent to buy back is "
            "discarded. New tranches are created by the next SCRUM."
        )
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {ds.SETTINGS_DANGER_SURFACE}; color: {ds.FOLD_RATIO_AMBER}; "
            f"border: 1px solid {ds.ERROR}; padding: 6px 12px; }} "
            f"QPushButton:disabled {{ color: {ds.TEXT_MUTED}; "
            f"border-color: {ds.BORDER_DISABLED}; }}"
        )
        clear_btn.clicked.connect(self._on_clear_fold_tranches)
        self._fold_clear_btn = clear_btn

        # v3.24.45 — operator directive 2026-08-06: "Languishing wire
        # credits can also be cleared. These too were not calculated
        # using outgoing safety rate math." Parked credit is x% of
        # GROSS scrum proceeds, so it is derived off principal rather
        # than profit; the figure is not meaningful to preserve.
        #
        # Deliberately a SEPARATE button, not folded into the tranche
        # clear: they are independent decisions, and a bot can want
        # one without the other.
        parked = float(getattr(self._bot, "_pending_wire_credits", 0.0) or 0.0)
        wire_btn = QPushButton(
            f"Clear ${parked:,.2f} Wire Credits"
            if parked > 1e-9
            else "Clear Wire Credits"
        )
        wire_btn.setEnabled(parked > 1e-9)
        wire_btn.setToolTip(
            "Discard this bot's parked Smart Wire credits.\n\n"
            "Releases an EARMARK only. No order is placed and no "
            "funds move — all bots share one exchange wallet, so the "
            "cash simply returns to ordinary spendable balance."
        )
        wire_btn.setStyleSheet(
            f"QPushButton {{ background: {ds.SETTINGS_DANGER_SURFACE}; color: {ds.FOLD_RATIO_AMBER}; "
            f"border: 1px solid {ds.ERROR}; padding: 6px 12px; }} "
            f"QPushButton:disabled {{ color: {ds.TEXT_MUTED}; "
            f"border-color: {ds.BORDER_DISABLED}; }}"
        )
        wire_btn.clicked.connect(self._on_clear_wire_credits)
        self._fold_wire_btn = wire_btn

        # issue #133 unit 3 - operator directive 2026-08-25:
        # "Lifetime tranche counts can be cleared since we are
        # resetting to the new standard." The live CHIP bot carried
        # 4925 opened / 4813 closed / 91 discarded, all accumulated
        # under rules that no longer apply.
        #
        # A THIRD BUTTON, not a third job for either of the two
        # above. Those discard INVENTORY - queued tranches, parked
        # credit - and this discards a RECORD OF THE PAST. A bot can
        # want its history reset with its queue intact, and folding
        # the two together would make one click do both.
        #
        # THE LABEL CARRIES THE OPENED TOTAL, the way the tranche
        # button carries its count and the wire button its dollars.
        # It is the largest of the four and the one the operator
        # quoted.
        _counter_total = (
            created_lifetime + closed_lifetime + discarded_lifetime + _malformed
        )
        counters_btn = QPushButton(
            f"Clear Lifetime Counters ({created_lifetime} opened)"
            if _counter_total
            else "Clear Lifetime Counters"
        )
        counters_btn.setEnabled(bool(_counter_total))
        counters_btn.setToolTip(
            "Set this bot's four fold-tranche lifetime counters to "
            "zero.\n\n"
            "Places NO order and removes NO tranche. Open tranches, "
            "parked wire credits, holdings, cost basis and target "
            "balance are all untouched - this clears the record of "
            "what happened, not what the bot holds."
        )
        counters_btn.setStyleSheet(
            f"QPushButton {{ background: {ds.SETTINGS_DANGER_SURFACE}; color: {ds.FOLD_RATIO_AMBER}; "
            f"border: 1px solid {ds.ERROR}; padding: 6px 12px; }} "
            f"QPushButton:disabled {{ color: {ds.TEXT_MUTED}; "
            f"border-color: {ds.BORDER_DISABLED}; }}"
        )
        counters_btn.clicked.connect(self._on_clear_lifetime_counters)
        self._fold_counters_btn = counters_btn

        btn_row = QHBoxLayout()
        btn_row.addWidget(clear_btn)
        btn_row.addWidget(wire_btn)
        btn_row.addWidget(counters_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # v3.23.34 — retired the "How this works" prose explainer
        # per operator directive 2026-07-26 ("remove the
        # hallucinatory descriptive text inside of the window").
        # Column headers + per-column tooltips are the authoritative
        # per-tranche documentation; the meta-prose drifted out of
        # sync with runtime.

        # --- Per-tranche detail table ---
        if tranches or ext_rows:
            # The two counts are named separately and never added
            # together. A fold tranche is this bot's own parked
            # intent to buy back; an Extractor Tranche is a child's
            # lease on this bot's asset. One number covering both
            # would invite reading a lease as fold inventory, which
            # is the exact confusion item 4 has to avoid.
            if ext_rows:
                _detail_title = (
                    f"Open Tranches ({open_count} fold, " f"{len(ext_rows)} extractor)"
                )
            else:
                _detail_title = f"Open Tranches ({open_count})"
            detail_group = QGroupBox(_detail_title)
            dl = QVBoxLayout(detail_group)

            # v3.16.43 — Column labels updated for architectural
            # redesign. Per-tranche initial_buy_price is no longer
            # the binding fold-back gate (compound governance shifted
            # to position-level smart ceiling). Renamed
            # "Patent ceiling $" → "Original cost $" to reflect its
            # now-informational role. The OTD threshold ("Min rebuy")
            # IS the binding per-tranche price gate.
            #
            # v3.26.0 (issue #97) — THE PANEL ASKS THE CODE THAT
            # DECIDES. This read was
            #     float(getattr(cfg, 'scrumming_interval_pct', 0) or 0)
            # — the scrumming interval ALONE. The executor's
            # per-tranche fold filter
            # (`ExecutionEngineMixin._execute_manual_rebalance` in
            # `src/trading/scrumming/execution.py`) uses
            # the Minimum Opposing Trade Distance, which is
            # interval + TRADING FEE, defined in `otd_math`.
            #
            # MEASURED ON THE LIVE FLEET, 2026-08-23, not argued: 24
            # of 38 bots run a 1.6% fee, so the "Min rebuy $" column
            # printed a price 1.71% ABOVE the gate the executor
            # applies. Over the 1,707 open fold tranches at their
            # stored price the panel showed Price-OK on 17 where the
            # executor accepts 11. Six green rows for a buy the
            # executor refuses, all on ALLO/USDC.
            #
            # ADDING A FEE TERM TO THE ARITHMETIC HERE WOULD BE THE
            # SAME DEFECT AGAIN. Two implementations that agree
            # today drift the next time either one moves, which is
            # exactly how this one was born: the fee entered the
            # executor in v3.25.8 and this surface never heard about
            # it. The call below is the call `scrumming_bot` makes,
            # the config read included, so nothing is left here to
            # drift. `_otd_factor` is bound ONCE and both consumers
            # below read it — the Min rebuy cell and the Status
            # verdict must never be able to disagree.
            #
            # Imported locally, matching the executor's own pattern
            # and keeping this GUI module importable without
            # `src.trading`.
            _otd_pct = 0.0
            _otd_factor = 1.0
            try:
                from ...trading.otd_math import (
                    fold_rebuy_factor_from_pct,
                    minimum_opposing_trade_distance_pct_from_config,
                )

                _otd_pct = minimum_opposing_trade_distance_pct_from_config(
                    self._bot.config
                )
                _otd_factor = fold_rebuy_factor_from_pct(_otd_pct)
            except Exception:  # R28-OK: best-effort config read
                _otd_pct = 0.0
                _otd_factor = 1.0

            table = QTableWidget()
            # v3.16.53 — added "Fire" column for per-tranche
            # operator-initiated fold-back (column 9).
            #
            # Item 5 (2026-08-10) — "Arbiter" APPENDED at column
            # 10, after Fire. See ARBITER_COLUMN_INDEX for why the
            # position is load-bearing rather than cosmetic.
            table.setColumnCount(ARBITER_COLUMN_INDEX + 1)
            table.setHorizontalHeaderLabels(
                [
                    "#",
                    "Age",
                    "Units",
                    "USD parked",
                    "Sell ref $",
                    "Original cost $",
                    "Min rebuy $",
                    "Status",
                    "Source",
                    "Fire",
                    ARBITER_COLUMN_HEADER,
                ]
            )

            # issue #98 defect 6 - THE AUTHORITY THE COMMENT NAMED
            # NOW EXISTS. Zero of the eleven headers carried a
            # tooltip while the comment below this table said header
            # tooltips were the authoritative per-column
            # documentation. `setHorizontalHeaderLabels` creates one
            # item per column, so each is asked for by index rather
            # than built a second time here.
            for _col, _tip in enumerate(FOLD_COLUMN_TOOLTIPS):
                _head = table.horizontalHeaderItem(_col)
                if _head is not None:
                    _head.setToolTip(_tip)

            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            # Extractor Tranche rows are appended AFTER every fold
            # tranche, never interleaved. This is load-bearing: the
            # Fire button resolves its target with
            # `tranches.index(tranche)` against `_fold_tranches`, so
            # fold row number must stay equal to fold list index. An
            # Extractor Tranche placed among them would shift that
            # mapping and fire an unrelated tranche.
            table.setRowCount(len(tranches) + len(ext_rows))
            # issue #98 defect 7 - the cap was a flat 280px over
            # 30px rows, so about EIGHT of up to 230 rows were on
            # screen. The height now follows the row count up to
            # `TRANCHE_TABLE_VISIBLE_ROWS`, and the header is
            # MEASURED rather than assumed: `ResizeToContents` below
            # sizes it to its own labels, so a hard-coded header
            # height would clip the last row on any theme with a
            # different font.
            #
            # issue #133 unit 1 - A CEILING IS NOT A PROMISE THAT
            # ANYTHING IS SHOWN. `setMaximumHeight` left the tab's
            # trailing `addStretch()` free to hand this table its
            # 86px `minimumSizeHint`, so under `cyberpunk_dark` in
            # a 640x720 dialog the render carried 8 of a row's 30
            # pixels at one tranche and 25 at fifty-eight - zero
            # whole rows either way. `setFixedHeight` makes the
            # number a floor too; `_wrap_scrollable` scrolls a
            # table taller than its tab.
            #
            # `fold_table_chrome_px` polishes the table and reads
            # what it spends: 36px, against the 4px fallback that
            # `fold_table_max_height_px` assumes without one.
            _chrome_px = fold_table_chrome_px(table)
            table.setFixedHeight(
                fold_table_max_height_px(
                    len(tranches) + len(ext_rows),
                    table.horizontalHeader().sizeHint().height(),
                    _chrome_px,
                )
            )
            table.setAlternatingRowColors(True)
            table.setEditTriggers(QTableWidget.NoEditTriggers)

            # Operator spec 2026-08-11 — "stronger borders so they
            # appear like proper containers". The delegate is
            # scoped to THIS table; the QSS in `theme_engine.py`
            # is one shared `QTableWidget, QTableView` block used
            # by twenty-odd tables across the app, so the border
            # work must never go there.
            #
            # Kept on `self` because `setItemDelegate` does NOT
            # take ownership. A delegate held only by this local
            # frame would be garbage-collected when the tab
            # finished building, and Qt would paint through a
            # dangling pointer.
            self._tranche_row_delegate = _TrancheRowBorderDelegate(table)
            table.setItemDelegate(self._tranche_row_delegate)

            # `setAlternatingRowColors` above stays ON deliberately.
            # An explicit item background beats the alternating
            # brush, so once every row is painted the alternating
            # colour has no visible surface left in the populated
            # area. Turning it off would change nothing and would
            # be an edit for its own sake.

            # Vertical mass — a fill only reads as a container when
            # the band has height.
            table.verticalHeader().setDefaultSectionSize(TRANCHE_ROW_HEIGHT_PX)

            # Qt's default grid draws BOTH axes at the same weight,
            # so a row boundary looked exactly like a column
            # boundary and each row read as ten separate cells
            # rather than one container. The delegate above now
            # draws the horizontal edges, so the grid is no longer
            # carrying any row separation and only the vertical
            # segmentation is left to remove.
            #
            # Safe ONLY because the delegate exists. Measured
            # without it, two adjacent painted rows butt together
            # with no separator at all and merge into one slab.
            table.setShowGrid(False)

            # Try to fetch current price for status determination.
            # Falls back to "—" if unavailable.
            cur_price = 0.0
            try:
                stats = self._bot.get_status().get("stats", {})
                cur_price = float(stats.get("current_price", 0) or 0)
            except Exception:  # R28-OK: best-effort price fetch for display only
                cur_price = 0.0

            # issue #98 defect 7 - the operator chooses the order,
            # and the QUEUE INDEX travels with the row rather than
            # being re-derived from the visual position. `row` is
            # where the row is drawn; `queue_index` is where the
            # tranche sits in `_fold_tranches`. Only the second one
            # is printed, and only the second one is quoted back by
            # the Fire confirmation.
            _ordered = fold_display_order(tranches, fold_sort_order(self))
            for row, (queue_index, t) in enumerate(_ordered):
                table.setItem(row, 0, QTableWidgetItem(str(queue_index + 1)))

                # THE SAME ADMISSION AS THE SUMMARY ROW ABOVE,
                # and it has to stay the same one. Both render
                # the age of the SAME tranche from the SAME
                # key, so closing one without the other gives
                # a panel that contradicts itself, which is
                # worse than the defect. Every refused shape
                # prints the "—" this column already used for
                # a tranche with no created_ts.
                cts = _as_finite_float(t.get("created_ts"))
                if cts is not None and cts > 0:
                    age_str = self._format_age(now_ts - cts)
                else:
                    age_str = "—"
                table.setItem(row, 1, QTableWidgetItem(age_str))

                # THE FOUR MONEY CELLS — four sibling keys off
                # the same dict the age above came from, read
                # with no guard at all. Measured on live
                # before this: `True` priced a stored flag at
                # one dollar and `False` at zero; None and ""
                # priced an ABSENCE at zero; `nan` and `inf`
                # printed "$nan" and "$inf"; an int above the
                # float maximum raised OverflowError out of
                # the row builder, and a list or a dict raised
                # TypeError. None of the four sits inside a
                # `try` — the chain runs to
                # `BotLiveSettingsDialog.__init__` and on to
                # `MainWindow._on_bot_clicked` with no handler
                # at any step — so a raise means Bot Settings
                # does not open for that bot at all.
                #
                # A REFUSED MONEY VALUE MUST NOT RENDER AS
                # ZERO. That would be a new defect rather than
                # a fix: the operator would read a real dollar
                # figure where there is none. The em dash is
                # what the Age cell beside it already prints
                # when it cannot read its key, and what an
                # Extractor row already prints in these same
                # price columns.
                units = _as_finite_float(t.get("units", 0))
                table.setItem(
                    row,
                    2,
                    QTableWidgetItem(f"{units:.6f}" if units is not None else "—"),
                )

                usd_v = _as_finite_float(t.get("usd", 0))
                table.setItem(
                    row,
                    3,
                    QTableWidgetItem(f"${usd_v:,.4f}" if usd_v is not None else "—"),
                )

                # `ref_v` is read by three cells, not one: the
                # Min-rebuy column and the Status column below
                # both derive from it. A refused ref therefore
                # takes the SAME no-ref branch those two
                # already had for a ref of 0 or an absent key,
                # which is why every `ref_v > 0` test below
                # now asks `is not None` first.
                ref_v = _as_finite_float(t.get("ref", 0))
                table.setItem(
                    row,
                    4,
                    QTableWidgetItem(f"${ref_v:.8f}" if ref_v is not None else "—"),
                )

                ceiling_v = _as_finite_float(t.get("initial_buy_price", 0))
                table.setItem(
                    row,
                    5,
                    QTableWidgetItem(
                        f"${ceiling_v:.8f}" if ceiling_v is not None else "—"
                    ),
                )

                # v3.16.42 — Min rebuy estimate (operator directive).
                # OTD-derived guide ONLY — actual fold-back
                # additionally requires TA validation in the GEP
                # (Gating Evaluation Protocol). This column does NOT
                # bypass TA; it shows where OTD's hysteresis gate
                # would clear for this tranche IF TA confirms.
                #
                # v3.26.0 (issue #97) — `_otd_factor` comes from
                # `otd_math`, the module the executor calls. The
                # expression here was `ref_v * (1.0 - _otd_pct /
                # 100.0)` over an interval-only `_otd_pct`, which is
                # a second implementation of the executor's gate and
                # printed a price the executor refuses.
                if ref_v is not None and ref_v > 0 and _otd_pct > 0:
                    min_rebuy_v = ref_v * _otd_factor
                    mr_item = QTableWidgetItem(f"≤${min_rebuy_v:.8f}")
                    mr_item.setToolTip(
                        f"OTD-derived guide only (ref × (1 − "
                        f"{_otd_pct:.2f}%), the Minimum Opposing "
                        f"Trade Distance = scrumming interval + "
                        f"trading fee, read from the same otd_math "
                        f"the executor uses). Fold-back requires TA "
                        f"validation in the GEP regardless. This is "
                        f"NOT a trigger price."
                    )
                    table.setItem(row, 6, mr_item)
                elif ref_v is not None and ref_v > 0:
                    table.setItem(row, 6, QTableWidgetItem(f"<${ref_v:.8f}"))
                else:
                    table.setItem(row, 6, QTableWidgetItem("—"))

                # v3.16.43 — Status reflects the new architectural
                # design: OTD-threshold gate per tranche (binding),
                # plus TA validation in GEP (mandatory, separate).
                # The original-cost field is informational — does
                # not gate fold-back. Compound saturation is governed
                # by position-level smart ceiling (visible in Bot
                # Settings, not per-tranche).
                #
                # v3.26.0 (issue #97) — the threshold is
                # `ref_v * _otd_factor`, the SAME binding the Min
                # rebuy cell above reads, from the SAME `otd_math`
                # call the executor makes. It was a second copy of
                # `ref_v * (1.0 - _otd_pct / 100.0)` over an
                # interval-only percentage, so a row could show a
                # green "Price-OK" for a buy the executor refuses.
                if cur_price > 0 and ref_v is not None and ref_v > 0 and _otd_pct > 0:
                    otd_thresh = ref_v * _otd_factor
                    otd_factor_diff_pct = (cur_price - otd_thresh) / otd_thresh * 100.0
                    if cur_price <= otd_thresh:
                        status_str = f"Price-OK ({otd_factor_diff_pct:+.2f}% vs OTD)"
                        status_color = ds.SUCCESS
                    else:
                        status_str = f"Need price ≤ OTD ({otd_factor_diff_pct:+.2f}%)"
                        status_color = ds.FOLD_RATIO_AMBER
                    si_status = QTableWidgetItem(status_str)
                    si_status.setForeground(QColor(status_color))
                    si_status.setToolTip(
                        "Price-gate status only (OTD threshold per "
                        "tranche). Actual fold-back additionally "
                        "requires TA validation in the GEP (bearish "
                        "+ midline + lower-DT) AND the bot's position "
                        "must be below its smart ceiling. "
                        "'Price-OK' means the per-tranche OTD gate "
                        "would pass IF TA confirms this tick AND the "
                        "position has not saturated."
                    )
                    table.setItem(row, 7, si_status)
                elif cur_price > 0 and ref_v is not None and ref_v > 0:
                    # OTD == 0 → no per-tranche price gate; rely on
                    # TA + position ceiling only. Show ref-relative.
                    ref_diff_pct = (cur_price - ref_v) / ref_v * 100.0
                    below_ref = cur_price < ref_v
                    status_str = (
                        f"Below ref ({ref_diff_pct:+.2f}%)"
                        if below_ref
                        else f"Above ref ({ref_diff_pct:+.2f}%)"
                    )
                    si_status = QTableWidgetItem(status_str)
                    si_status.setForeground(
                        QColor(ds.SUCCESS if below_ref else ds.FOLD_RATIO_AMBER)
                    )
                    table.setItem(row, 7, si_status)
                else:
                    table.setItem(row, 7, QTableWidgetItem("—"))

                # issue #98 defect 5 — THE COLUMN NAMES THE ACTION
                # THAT CREATED THE ROW. It used to print "manual
                # fire", a BUY, which is the action that REMOVES a
                # tranche. The mapping and the live counts behind
                # the three labels are at the top of this module.
                src_str = _fold_tranche_source_label(t)
                si = QTableWidgetItem(src_str)
                si.setToolTip(FOLD_SOURCE_TOOLTIPS[src_str])
                if src_str == FOLD_SOURCE_MANUAL_SCRUM:
                    # The one semantic foreground on this column,
                    # unchanged. `_paint_fold_tranche_row` measured
                    # it at 6.12:1 against the fold fill and leaves
                    # any cell that already owns a foreground alone.
                    si.setForeground(QColor(FOLD_SOURCE_MANUAL_FG_HEX))
                table.setItem(row, 8, si)

                # v3.16.53 — Fire button for per-tranche operator-
                # initiated fold-back. Captures the tranche dict by
                # identity so post-click index lookups stay correct
                # even if other ops mutate the list in the meantime.
                fire_btn = QPushButton("Fire")
                fire_btn.setToolTip(
                    "Operator-initiated fold-back of THIS tranche. "
                    "Bypasses TA / OTD / Target-Delta gates. Smart "
                    "Ceiling + MEM-257 fail-closed still apply. "
                    "Bot must be RUNNING."
                )
                # The inset is a stylesheet MARGIN, and it works by
                # a different mechanism than it looks. The margin
                # does NOT resize the widget: the button still
                # occupies the whole cell rect and still reports
                # the full row height. What it changes is where the
                # button's frame is PAINTED inside that rect. The
                # margin strip at the top and bottom is left
                # untouched, so the delegate's rule -- drawn
                # underneath -- shows through it.
                #
                # `setFixedHeight` was tried first and is wrong
                # here: `setCellWidget` TOP-aligns a short widget,
                # so the clearance all landed at the bottom.
                # Measured on the render, that freed the bottom
                # rule to its full 890px while the top rule stayed
                # broken at 849px. The margin insets both ends.
                # Background matches the row fill so the blue band
                # reads as CONTINUOUS across all ten columns.
                # `setCellWidget` sizes the button to the whole
                # cell rect — measured — so the old `#2a3a4a` grey
                # would punch a hole in the container at its last
                # column and read as a separate chip sitting
                # outside the row. Its `#00ccff` border and text
                # are unchanged and measure 6.12:1 against the new
                # fill, so the control stays clearly a control.
                _inset = TRANCHE_FIRE_BTN_INSET_PX // 2
                fire_btn.setStyleSheet(
                    f"QPushButton {{ background: "
                    f"{FOLD_TRANCHE_BG_HEX}; color: "
                    f"{ds.FOLD_SOURCE_MANUAL}; border: 1px solid {ds.FOLD_SOURCE_MANUAL}; padding: "
                    f"2px 8px; margin: {_inset}px 0px; }} "
                    f"QPushButton:hover {{ background: {ds.FOLD_SOURCE_MANUAL}; "
                    f"color: {ds.SETTINGS_ON_INFO}; }} "
                    f"QPushButton:disabled {{ background: {ds.SETTINGS_DISABLED_SURFACE}; "
                    f"color: {ds.TEXT_PLACEHOLDER}; border-color: {ds.TEXT_PLACEHOLDER}; }}"
                )
                # Capture tranche IDENTITY (not row index) so we
                # can resolve the current index at click time.
                #
                # issue #98 defect 8 - THE NUMBER ON THE ROW IS
                # CAPTURED TOO, and it is a different thing from the
                # identity. The confirmation used to print the index
                # it re-resolved at click time, so a fold landing
                # between the panel being built and the button being
                # pressed shifted every later index and the dialog
                # named a tranche the operator had not clicked. The
                # BUY was always correct - identity capture saw to
                # that - but the number authorising it was not. This
                # is the same capture-at-build-time mechanism the
                # Arbiter button already uses for `tranche_id`, and
                # it is one mechanism rather than a second: what is
                # captured is what the operator can see.
                _captured = t
                _captured_number = queue_index + 1
                fire_btn.clicked.connect(
                    lambda _checked=False, tr=_captured, shown=_captured_number: self._on_fire_tranche_clicked(
                        tr, shown
                    )
                )
                table.setCellWidget(row, 9, fire_btn)

                # Item 5 — a fold tranche has NO Arbiter, and the
                # cell says so in words rather than being left
                # blank. There is no child holding this tranche and
                # no second party who could close it: this bot's
                # own fold-back does, and the Fire button beside it
                # is how the operator asks for that. An em dash is
                # the same answer item 4 gives on the other side of
                # the table, where an Extractor row prints one
                # under Fire.
                #
                # A REAL ITEM, NOT AN EMPTY CELL. The row painter
                # would manufacture a background-only item here
                # anyway, so the choice is between an explained
                # dash and a silent blank; and both row-styling
                # tests walk every column demanding a painted item,
                # which an empty cell would satisfy while telling
                # the operator nothing.
                arb_na = QTableWidgetItem(ARBITER_NOT_APPLICABLE)
                arb_na.setToolTip(
                    "Arbiter applies to Extractor Tranches only. "
                    "This is one of this bot's own fold tranches — "
                    "no child holds it, and its Fire button is how "
                    "you close it."
                )
                table.setItem(row, ARBITER_COLUMN_INDEX, arb_na)

                # LAST in the row, so every semantic foreground set
                # above is already on its item and is preserved.
                self._paint_fold_tranche_row(table, row)

            self._paint_extractor_tranche_rows(table, ext_rows, len(tranches), now_ts)

            # The two counts stay named apart here for the same
            # reason the group title names them apart: an Extractor
            # row is a child's lease, not this bot's fold
            # inventory, and the refresh pin subtracts one from the
            # other rather than reporting their sum.
            self._fold_tranche_table = table
            self._fold_ext_row_count = len(ext_rows)

            # issue #98 defect 7 - WHAT THE FILTER SEARCHES, read
            # off the built table and nowhere else. Every string
            # here is a cell this panel composed from a stored
            # field, so the filter can never match a quantity the
            # operator cannot see, and there is no second reading of
            # the tranche dict that could disagree with the first.
            # Harvested AFTER the Extractor rows, so a lease row is
            # filtered by the same rule as a fold row.
            # `table.item` returns `QTableWidgetItem | None`, so
            # the item is bound ONCE and narrowed before `.text()`
            # is asked for. A comprehension that called `item`
            # twice would read a different object on each call and
            # both type checkers would be right to refuse it.
            _harvested: list[list[str]] = []
            for _r in range(table.rowCount()):
                _cells: list[str] = []
                for _c in range(table.columnCount()):
                    _item = table.item(_r, _c)
                    _cells.append("" if _item is None else _item.text())
                _harvested.append(_cells)
            self._fold_row_texts = _harvested

            # issue #133 unit 12 - the table declares the width of
            # a whole row. Set before the layout first activates;
            # QWidgetItem.sizeHint expands to minimumSize, so the
            # tab's hint carries the columns from here up.
            table.setMinimumWidth(fold_table_natural_width_px(table))

            dl.addLayout(build_fold_row_controls(self))
            dl.addWidget(table)
            layout.addWidget(detail_group)
        else:
            empty = QLabel(
                "No open tranches. The fold queue is empty — either "
                "the bot has not yet executed a SCRUM, or every "
                "previous SCRUM has been closed by a FOLD-BACK."
            )
            empty.setStyleSheet(
                f"color: {ds.CARD_METRIC_LABEL}; font-style: italic; " "padding: 10px;"
            )
            empty.setWordWrap(True)
            layout.addWidget(empty)

        layout.addStretch()
        return w

    def _on_arbiter_toggle_clicked(
        self,
        tranche_id: str,
        child_bot_id: str,
        button: QPushButton,
        item: QTableWidgetItem,
    ) -> None:
        """Flip ONE Extractor Tranche's Arbiter. Moves no money.

        WHAT THIS DOES: resolves the child Extractor that owns the
        tranche, asks it to flip one stored string, and relabels
        the button. That is the whole of it.

        WHAT THIS MUST NEVER DO, stated because the control sits
        one column from a live Fire button: no order is placed or
        cancelled, no balance and no Target Balance is touched,
        nothing is scheduled onto the async loop and nothing is
        awaited. There is no `run_coroutine_threadsafe` here, and
        there must never be one — the Fire handler beside it needs
        that machinery precisely because it spends money.

        NO SAVE IS FORCED EITHER. Writing the value is a memory
        write; the fleet's 60-second periodic save and its shutdown
        save persist it through the path everything else uses.
        Calling `save_all_state()` from inside a click would
        serialise the whole fleet and copy a backup file ON THE GUI
        THREAD, which is the freeze class the operator has already
        been bitten by. The cost is stated rather than hidden: a
        toggle set and then a crash inside 60 seconds is lost,
        exactly as it is for every other runtime field.

        THE MANAGER COMES FROM THE BOT, NOT FROM `self._bm`. The
        Simulator constructs this dialog with no manager at all,
        and the listing tests do the same, so `self._bm` is None on
        real paths. The parent bot's own `_bot_manager` is the
        object that produced these rows in the first place.

        A TRANCHE THAT CLOSED WHILE THE TABLE SAT THERE IS REFUSED,
        NOT GUESSED. The child matches the full identity string, so
        an id belonging to a closed position matches nothing and
        returns None. This then leaves the button exactly as it
        was, which is the truth: nothing was written.
        """
        from PySide6.QtWidgets import QMessageBox

        # EACH MESSAGE REPORTS THE STEP THAT ACTUALLY RAN, not a
        # blanket claim about a state nobody checked. The lookup is
        # the operation on this path, so its own result is what the
        # operator is told, and every one of these says outright
        # that nothing was written.
        manager = getattr(self._bot, "_bot_manager", None)
        getter = getattr(manager, "get_bot", None)
        if not callable(getter):
            QMessageBox.warning(
                self,
                "Arbiter not changed",
                "Nothing was written. This panel has no bot "
                "registry attached, so the Extractor holding this "
                "tranche could not be looked up. Reopen the panel "
                "once the platform has finished starting.",
            )
            return
        child = getter(child_bot_id)
        toggler = getattr(child, "toggle_tranche_arbiter", None)
        if not callable(toggler):
            # The lookup RAN, and what it produced is named, so the
            # operator is reading an observation rather than a
            # guess. `type(None).__name__` prints "NoneType", which
            # is itself the fact that the id matched no bot.
            QMessageBox.warning(
                self,
                "Arbiter not changed",
                f"Nothing was written. The Arbiter is set by the "
                f"Extractor that holds the tranche; asking the "
                f"registry for bot id '{child_bot_id or '?'}' "
                f"produced a {type(child).__name__}, which cannot "
                f"set one. Reopen the panel to rebuild the list "
                f"from the running fleet.",
            )
            return

        try:
            new_value = toggler(tranche_id)
        except Exception as exc:  # R28-OK: operator surface
            logger.exception(
                "Arbiter toggle failed for tranche %s on child %s",
                tranche_id,
                child_bot_id,
            )
            QMessageBox.critical(
                self,
                "Arbiter not changed",
                f"Nothing was changed — the call failed:\n\n"
                f"{type(exc).__name__}: {exc}",
            )
            return

        if new_value is None:
            # The write WAS attempted: the child was asked, and it
            # answered that no open position carries this identity.
            # That answer is what gets reported, rather than a
            # guess at why.
            QMessageBox.warning(
                self,
                "Arbiter not changed",
                "Nothing was written. The Extractor reports no "
                "open position with this tranche's identity — it "
                "has most likely exited the position since this "
                "panel was opened. Reopen the panel to see the "
                "tranches it holds now.",
            )
            return

        label = _arbiter_label(new_value)
        tip = _compose_arbiter_tooltip(new_value)
        # Both surfaces, so the model and the widget cannot
        # disagree about what is stored. Neither object can have
        # been destroyed: this tab is built once and never
        # repopulated, and a deleted button could not have emitted
        # the click that got us here.
        button.setText(label)
        button.setToolTip(tip)
        item.setText(label)
        item.setToolTip(tip)

    def _on_fire_tranche_clicked(
        self, tranche: dict, clicked_number: int | None = None
    ) -> None:
        """v3.16.53 — operator-initiated per-tranche fold-back.

        Resolves the tranche's current index (in case the list
        mutated since the table was built), confirms with the
        operator, then schedules bot.manual_fire_tranche on the
        bot manager's async loop.

        issue #98 defect 8 - THE DIALOG NAMES THE ROW THAT WAS
        CLICKED. `clicked_number` is the `#` printed on that row,
        captured in the button's own closure when the row was
        built, beside the identity capture that was already there.

        WHAT WAS MEASURED. Every operator-facing string in this
        method printed `idx + 1`, the index re-resolved HERE at
        click time. The panel is a snapshot and the bot keeps
        trading behind it, so a fold that consumes an earlier
        tranche shifts every later index down by one: the operator
        clicks the row printed 7 and the confirmation offers to
        fire tranche 6. The BUY was never wrong - `tranches.index`
        finds the captured dict wherever it moved to - but a
        confirmation for a market buy named a tranche the operator
        had not pointed at, at the one moment the action cannot be
        undone.

        TWO NUMBERS, AND THEY ARE NOT INTERCHANGEABLE. `idx` is
        what the ORDER needs: `manual_fire_tranche(idx)` indexes
        the live list, so it stays the resolved one and is not
        touched. `_row_no` is what the OPERATOR needs: the number
        they read. When the two disagree the confirmation says so
        in a line of its own rather than picking one and hiding the
        other, because a queue that moved under the panel is
        something the operator should know before authorising a
        buy.

        `clicked_number` DEFAULTS TO None, and the fallback is the
        resolved index. A caller with no row number - a test
        driving this handler directly, or any future caller - gets
        exactly the pre-repair strings rather than a blank.
        """
        from PySide6.QtWidgets import QMessageBox
        import asyncio as _asyncio

        # The repo's ONE admission rule, imported the way this
        # module imports every other trading symbol: locally,
        # so this dialog never drags the trading package in at
        # module import time. The fold-row builder that made
        # the Fire button reads the SAME dict through this
        # SAME helper -- the row and its confirmation must not
        # disagree about whether a value is readable.
        from ...trading.bot_container import (
            as_finite_float as _as_finite_float,
        )

        try:
            tranches = list(getattr(self._bot, "_fold_tranches", []))
            # Resolve current index by identity
            try:
                idx = tranches.index(tranche)
            except ValueError:
                # The clicked number is the ONLY number available
                # here: there is no index to resolve, because the
                # tranche is gone. Naming the row the operator
                # pressed is what tells them WHICH one vanished.
                _gone = (
                    "This tranche"
                    if clicked_number is None
                    else f"Tranche #{clicked_number}"
                )
                QMessageBox.warning(
                    self,
                    "Tranche unavailable",
                    f"{_gone} is no longer in the fold queue "
                    f"(it may have just been consumed by an "
                    f"auto-fold or another manual action). Refresh "
                    f"the tab.",
                )
                return

            # issue #98 defect 8 - the number the operator READ.
            # Everything they are shown from here down quotes
            # `_row_no`. `idx` is kept for the order alone.
            _row_no = idx + 1 if clicked_number is None else int(clicked_number)
            _moved = _row_no != idx + 1

            # Confirm
            #
            # THE THREE MONEY VALUES BELOW ARE DISPLAY-ONLY IN
            # THIS METHOD. The only thing that crosses to the
            # order is `idx`, an int, at the
            # `manual_fire_tranche(idx)` call further down.
            #
            # THAT IS NOT A REASON TO ONLY FIX THE DISPLAY.
            # Each one is a MIRROR of a value the order path
            # re-derives from THIS SAME dict -- captured by
            # identity where the row was built -- using a
            # character-identical expression:
            #
            #   ScrummingBot.manual_fire_tranche
            #     cost = float(tranche.get("usd", 0) or 0)
            #     ...
            #     await self._execute_buy(cost=cost, ...)
            #
            # So a value this dialog cannot read honestly is a
            # value the MARKET BUY IS STILL SIZED FROM. Driven
            # against both live expressions, not predicted:
            # a stored `nan` renders "$nan" here and arrives as
            # `_execute_buy(cost=nan)` intact, because the
            # order's only guard is `cost <= 0` and `nan <= 0`
            # is False. `inf` does the same. A stored `True`
            # renders "$1.0000" and buys one dollar; the string
            # "20.0" renders "$20.0000" and buys twenty.
            #
            # BLANKING THE LABEL ALONE WOULD BE THE WORSE
            # OUTCOME. An em dash beside a Confirm button that
            # still buys reads as handled. So the fire is
            # REFUSED here, BEFORE the confirmation is offered,
            # and the refusal names the field and its stored
            # value so the operator can go and look at it. No
            # dash is ever rendered next to a live Confirm.
            #
            # `_as_finite_float` is the settled reader already
            # used by the fold-row builder above: EXACT type
            # (so a stored `True` is not the number 1), finite
            # (so `nan` and `inf` are not numbers), and an
            # INTEGER bound check (so `10**400` is refused
            # rather than raising, which `float()` does and
            # `math.isfinite()` also does).
            #
            # The trailing `or 0.0` is NOT redundant. It keeps
            # the live normalisation for every value the helper
            # ACCEPTS: live computed `float(x or 0)`, which maps
            # a stored `-0.0` to positive `0.0`. The helper
            # returns `-0.0` unchanged, and `"$%.4f" % -0.0` is
            # "$-0.0000". A readable value is not this unit's to
            # restyle, so it is normalised exactly as before.
            _reads = (
                ("USD parked", "usd", tranche.get("usd", 0)),
                ("Sell ref", "ref", tranche.get("ref", 0)),
                (
                    "Original cost",
                    "initial_buy_price",
                    tranche.get("initial_buy_price", tranche.get("ref", 0)),
                ),
            )
            _clean: dict = {}
            _unreadable: list = []
            for _field, _key, _raw in _reads:
                _val = _as_finite_float(_raw)
                if _val is None:
                    # Bound the echo: a refused value can be a
                    # 309-digit int, and the point of the echo
                    # is to identify the bad field, not to
                    # reprint it.
                    _shown = repr(_raw)
                    if len(_shown) > 40:
                        _shown = _shown[:40] + "..."
                    _unreadable.append(
                        f"  {_field} (key {_key!r}): stored "
                        f"{type(_raw).__name__} {_shown}"
                    )
                    continue
                _clean[_field] = _val or 0.0
            if _unreadable:
                _bad = "\n".join(_unreadable)
                logger.error(
                    "Bot %s manual fire REFUSED on tranche #%d "
                    "(queue index %d): unreadable stored "
                    "value(s): %s",
                    getattr(self._bot, "bot_id", "?")[:8],
                    _row_no,
                    idx + 1,
                    "; ".join(_unreadable),
                )
                QMessageBox.critical(
                    self,
                    "Manual Fire refused — unreadable value",
                    f"Tranche #{_row_no} was NOT fired. NO ORDER "
                    f"WAS PLACED.\n\n"
                    f"This tranche stores a value that is not a "
                    f"usable number:\n\n{_bad}\n\n"
                    f"The confirmation is not being offered "
                    f"because the market buy would be sized from "
                    f"that same stored value, and you would be "
                    f"authorising an amount this dialog cannot "
                    f"show you honestly.\n\n"
                    f"Nothing has changed. The tranche is still "
                    f"in the fold queue. Check this bot's saved "
                    f"state before firing it.",
                )
                return
            _usd = _clean["USD parked"]
            _ref = _clean["Sell ref"]
            _ibp = _clean["Original cost"]
            # issue #98 defect 8 - the confirmation names the
            # row that was clicked. When the queue has moved
            # under the panel the shift gets a line of its own:
            # the operator is told the record they pointed at
            # has slid, rather than being shown one of the two
            # numbers with no way to tell which.
            # `manual_fire_tranche` still receives `idx`, so
            # the buy is unchanged either way.
            _moved_note = (
                f"THE QUEUE HAS MOVED. You clicked the row "
                f"printed #{_row_no}. That same tranche now "
                f"sits at #{idx + 1} in the fold queue, "
                f"because tranches before it were folded or "
                f"cleared after this panel was built. This "
                f"fires the tranche you clicked.\n\n"
                if _moved
                else ""
            )
            _confirm_msg = (
                f"Fire tranche #{_row_no}?\n\n"
                f"  USD parked:    ${_usd:.4f}\n"
                f"  Sell ref:      ${_ref:.8f}\n"
                f"  Original cost: ${_ibp:.8f}\n\n"
                f"{_moved_note}"
                f"This will execute a MARKET buy at the current "
                f"price, bypassing TA / OTD / Target-Delta gates. "
                f"Smart Ceiling and MEM-257 fail-closed still apply."
            )
            btn = QMessageBox.question(
                self,
                "Manual Tranche Fire — confirm",
                _confirm_msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if btn != QMessageBox.Yes:
                return

            # Schedule on the bot manager's async loop
            _loop = getattr(self._bm, "_async_loop", None) if self._bm else None
            if _loop is None:
                QMessageBox.warning(
                    self,
                    "Async loop unavailable",
                    "Bot manager async loop not running. Is the "
                    "trading platform fully started? Try again "
                    "after launch completes.",
                )
                return

            _coro = self._bot.manual_fire_tranche(idx)
            try:
                _future = _asyncio.run_coroutine_threadsafe(_coro, _loop)
            except Exception as _sched_exc:
                QMessageBox.warning(
                    self,
                    "Schedule failed",
                    f"Could not schedule the fold-back:\n\n"
                    f"{type(_sched_exc).__name__}: {_sched_exc}",
                )
                return

            # v3.16.55 — TRUE non-blocking dispatch. The v3.16.54
            # implementation used `_future.result(timeout=5.0)` which
            # FROZE the GUI thread waiting up to 5 seconds, then
            # presented a misleading TimeoutError dialog even when
            # the underlying buy was simply mid-flight. Operator
            # report 2026-05-12: "I should not be getting a time out
            # on the manual fire regardless... There are bugs here."
            #
            # Correct pattern: return immediately. The bot.log event
            # subscription on the main window already shows the
            # outcome via "MANUAL TRANCHE FIRE COMPLETE" / refusal
            # log lines. A QTimer polls the future periodically and
            # surfaces the result dialog when it lands, without ever
            # blocking the event loop.
            QMessageBox.information(
                self,
                "Manual Fire dispatched",
                f"Fold-back dispatched on tranche #{_row_no}.\n\n"
                f"Watch the Activity Log for the outcome. The "
                f"result dialog will appear here when the buy "
                f"completes (no time limit — Coinbase market "
                f"orders may take several seconds during busy "
                f"windows; this is normal).",
            )

            # Spawn a non-blocking poller via QTimer. Fires every
            # 500ms; gives up after 120 seconds (the Activity Log
            # is still authoritative regardless).
            from PySide6.QtCore import QTimer as _QTimer

            _start_ts = __import__("time").monotonic()
            _poll_timer = _QTimer(self)
            _poll_timer.setInterval(500)

            def _check_future():
                try:
                    if _future.done():
                        _poll_timer.stop()
                        try:
                            result = _future.result(timeout=0.1)
                        except Exception as _rx:
                            # Future errored (e.g. coroutine raised).
                            QMessageBox.warning(
                                self,
                                "Manual Fire raised",
                                f"Tranche #{_row_no} fold-back "
                                f"raised:\n\n"
                                f"{type(_rx).__name__}: {_rx}\n\n"
                                f"See Activity Log for full trace.",
                            )
                            return
                        if isinstance(result, dict) and result.get("applied"):
                            _fill = result.get("fill_price", 0.0)
                            _units = result.get("units_returned", 0.0)
                            _remaining = result.get("remaining_tranches", 0)
                            # issue #98 defect 1 - THE SIBLING
                            # HOLE. A filled fold-back removes the
                            # tranche it fired, so this panel is
                            # stale for exactly the reason a clear
                            # leaves it stale, and it used to say
                            # so instead of fixing it. No save is
                            # forced here: the fill itself is a
                            # TRADE, and the trade path owns its
                            # own persistence.
                            _r = self._refresh_fold_tranches_tab()
                            QMessageBox.information(
                                self,
                                "Manual Fire complete",
                                f"Tranche #{_row_no} fold-back "
                                f"filled.\n\n"
                                f"  Fill price:   ${_fill:.8f}\n"
                                f"  Units back:   {_units:.6f}\n"
                                f"  Remaining:    {_remaining} "
                                f"tranche(s)\n\n"
                                + (
                                    "The panel behind this message "
                                    "has been rebuilt and now shows "
                                    "the new state."
                                    if _r == "refreshed"
                                    else f"The panel was {_r}. Close and "
                                    f"reopen this dialog to see the "
                                    f"new state."
                                ),
                            )
                        else:
                            _reason = (
                                result.get("reason", "unknown")
                                if isinstance(result, dict)
                                else "unknown"
                            )
                            QMessageBox.warning(
                                self,
                                "Manual Fire refused",
                                f"Tranche #{_row_no} fold-back "
                                f"NOT applied.\n\n"
                                f"Reason: {_reason}",
                            )
                        return
                    # Not done yet — give up after 120s. The bus log
                    # will still show the eventual outcome; we just
                    # stop polling so the dialog isn't haunted.
                    if __import__("time").monotonic() - _start_ts > 120.0:
                        _poll_timer.stop()
                except Exception:  # R28-OK: poll probe; best-effort
                    _poll_timer.stop()

            _poll_timer.timeout.connect(_check_future)
            _poll_timer.start()
        except Exception as exc:
            logger.exception(
                "Bot %s _on_fire_tranche_clicked raised: %s",
                getattr(self._bot, "bot_id", "?")[:8],
                exc,
            )
            try:
                QMessageBox.critical(
                    self,
                    "Manual Fire error",
                    f"Unexpected error:\n\n" f"{type(exc).__name__}: {exc}",
                )
            except Exception as _dlg_exc:  # noqa: BLE001 - error-dialog best-effort
                logger.debug("critical error dialog failed to display: %s", _dlg_exc)
