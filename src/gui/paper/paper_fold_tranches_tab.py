"""Fold Tranches tab of the Paper Trader's Bot Settings window, forked from
``live_settings.fold_tranches_tab``; every write reaches ``PaperBotView`` and is refused.
"""

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

from ...paper.fleet_source import SendRefused
from .. import design_system as ds
from ..live_settings.fold_tokens import (
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
from ..live_settings.fold_chrome import (
    _TrancheRowBorderDelegate,
    build_fold_row_controls,
    fold_sort_order,
    install_despawn_rows,
)

if TYPE_CHECKING:
    from .paper_bot_detail import PaperBotDetailDialog

logger = logging.getLogger("acervator.gui")


class PaperFoldTranchesTabMixin:
    """The fold queue, its clear controls and Manual Fire."""

    # `_bm`, `_bot`, and the four callables below are supplied by
    # PaperBotDetailDialog at runtime; annotations only.
    _bm: Any
    _bot: Any
    _configure_form: Callable[..., Any]
    _format_age: Callable[..., Any]
    _save_fleet_state_now: Callable[..., Any]
    _wrap_scrollable: Callable[..., Any]

    def _on_clear_fold_tranches(self: PaperBotDetailDialog) -> None:
        """Discard this bot's queued fold tranches, after confirming.

        Removes queued intent only: no order is placed, and
        holdings, cost basis and target balance are unchanged.

        Clearing to zero tranches opens the absorb window, so the
        next SCRUM parks its whole proceeds into one uncapped
        tranche. The confirmation states that consequence before
        the operator acts.
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
        except Exception as exc:
            logger.exception("clear_fold_tranches failed: %s", exc)
            QMessageBox.critical(
                self,
                "Clear fold tranches",
                f"Nothing was cleared — the call failed:\n\n{exc}",
            )
            return

        # `_settle_after_clear` reports what refresh and save
        # actually did, ahead of the "no order" reassurance below.
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

    def _on_clear_wire_credits(self: PaperBotDetailDialog) -> None:
        """Discard this bot's parked Smart Wire credits, after confirming.

        Releases an earmark rather than moving funds:
        `_pending_wire_credits` has no order or transfer site in
        src/, and all bots share one exchange wallet, so the
        amount returns to spendable balance.
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
        except Exception as exc:
            logger.exception("clear_pending_wire_credits failed: %s", exc)
            QMessageBox.critical(
                self,
                "Clear wire credits",
                f"Nothing was cleared — the call failed:\n\n{exc}",
            )
            return

        # Same three steps as `_on_clear_fold_tranches`, then
        # `_settle_after_clear` reports the outcome.
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

    def _on_clear_lifetime_counters(self: PaperBotDetailDialog) -> None:
        """Zero this bot's four lifetime tranche counters, after confirming.

        The panel keeps `opened - closed - discarded == open
        tranches`; zeroing the three terms while N tranches are
        still open makes that read 0 against N until the next
        SCRUM. No tranche is removed. The confirmation states this
        before the operator acts.
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
        except Exception as exc:
            logger.exception("clear_lifetime_tranche_counters failed: %s", exc)
            QMessageBox.critical(
                self,
                "Clear lifetime counters",
                f"Nothing was cleared - the call failed:\n\n{exc}",
            )
            return

        # Same three steps as `_on_clear_fold_tranches`, then
        # `_settle_after_clear` reports the outcome.
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
        """Paint one fold tranche row's background and foreground.

        Called after the row's items exist. Skips any cell that
        already carries a foreground brush — the Status and Source
        columns set colour for OTD-clear and manual-scrum states —
        so this never overwrites a semantic colour with the default.
        """
        bg = QBrush(QColor(FOLD_TRANCHE_BG_HEX))
        fg = QBrush(QColor(FOLD_TRANCHE_FG_HEX))
        for col in range(table.columnCount()):
            cell = table.item(row, col)
            if cell is None:
                # Column 9 (Fire) has no item; add a background-only
                # one so the border delegate has a fill to paint.
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

        Paints every column, including column 9, red-on-white per
        cell — there is no row-wide background mechanism in this
        GUI. Writes only rows at `start_row` and beyond; fold rows
        before it are untouched.
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

            arb_value = row_data.get("arbiter")
            arb_cell = QTableWidgetItem(_arbiter_label(arb_value))
            arb_cell.setBackground(bg)
            arb_cell.setForeground(fg)
            arb_cell.setToolTip(_compose_arbiter_tooltip(arb_value))
            table.setItem(target_row, ARBITER_COLUMN_INDEX, arb_cell)

            arb_btn = QPushButton(_arbiter_label(arb_value))
            arb_btn.setToolTip(_compose_arbiter_tooltip(arb_value))
            # The inset leaves the row border delegate visible under the button.
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

            _arb_id = str(row_data.get("tranche_id", "") or "")
            _arb_child = str(row_data.get("child_bot_id", "") or "")
            _arb_item = arb_cell
            arb_btn.clicked.connect(
                lambda _checked=False, tid=_arb_id, cid=_arb_child, btn=arb_btn, item=_arb_item: self._on_arbiter_toggle_clicked(
                    tid, cid, btn, item
                )
            )
            table.setCellWidget(target_row, ARBITER_COLUMN_INDEX, arb_btn)

    FOLD_TRANCHES_TAB_LABEL = "Fold Tranches"

    def _install_fold_tranches_tab(self, tabs: QTabWidget) -> QWidget:
        """Build the Fold Tranches tab and add it to `tabs`.

        Stores the page on `self._fold_tab_page` for later refresh.
        """
        page = self._wrap_scrollable(self._create_fold_tranches_tab())
        tabs.addTab(page, self.FOLD_TRANCHES_TAB_LABEL)
        self._fold_tab_page = page
        return page

    def _refresh_fold_tranches_tab(self) -> str:
        """Rebuild the Fold Tranches tab in place. Return a status.

        Returns "refreshed", or a sentence naming why it did not;
        the post-clear dialogs quote this string. Finds the tab by
        widget identity via `indexOf`, not a stored index, and
        replaces it at the same position. `page.deleteLater()`
        frees the old widget tree explicitly, since `removeTab`
        only reparents it.
        """
        tabs = getattr(self, "_tabs", None)
        page = getattr(self, "_fold_tab_page", None)
        if tabs is None or page is None:
            return "not refreshed: this dialog has no Fold " "Tranches tab installed"
        try:
            index = tabs.indexOf(page)
        except Exception as exc:
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
        except Exception as exc:
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
        """Report what the Fold Tranches tab shows, read off the widgets.

        `fold_rows` subtracts the Extractor rows, which are appended
        after every fold tranche and are a child's lease, not this
        bot's own inventory.
        """
        table = getattr(self, "_fold_tranche_table", None)
        lbl = getattr(self, "_fold_open_count_lbl", None)
        btn = getattr(self, "_fold_clear_btn", None)
        wire = getattr(self, "_fold_wire_btn", None)
        timer = getattr(self, "_fold_despawn_timer_lbl", None)
        preview = getattr(self, "_fold_despawn_preview_lbl", None)
        units = getattr(self, "_fold_units_marked_lbl", None)
        sort_box = getattr(self, "_fold_sort_combo", None)
        filter_box = getattr(self, "_fold_filter_edit", None)
        # `discarded` and `reset` are None, not "0", when the panel
        # renders no such row (hidden until non-zero / until cleared).
        opened = getattr(self, "_fold_opened_lbl", None)
        closed = getattr(self, "_fold_closed_lbl", None)
        # Named `ratio_row`: `ratio` alone reads to the TA archetype
        # as a dimensionless quantity, not a QLabel.
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
            # branch: zero rows, not "unknown".
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
        """Save, rebuild the tab, and return status lines describing the outcome.

        Shared by both Clear buttons. Saves before refreshing: the
        save is the durable write, so a crash between the two steps
        costs a stale panel, not a restored tranche.
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

        # Imported locally so building a tab never drags
        # `src.trading` in at module import time.
        from ...trading.container.config import (
            as_finite_float as _as_finite_float,
        )

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        self._fold_tranche_table = None
        self._fold_open_count_lbl = None
        self._fold_clear_btn = None
        self._fold_wire_btn = None
        self._fold_ext_row_count = 0
        self._fold_despawn_timer_lbl = None
        self._fold_despawn_preview_lbl = None
        self._fold_units_marked_lbl: QLabel | None = None
        self._fold_sort_combo: QComboBox | None = None
        self._fold_filter_edit: QLineEdit | None = None
        self._fold_row_texts: list[list[str]] = []
        self._fold_opened_lbl: QLabel | None = None
        self._fold_closed_lbl: QLabel | None = None
        self._fold_ratio_lbl: QLabel | None = None
        self._fold_discarded_lbl: QLabel | None = None
        self._fold_malformed_lbl: QLabel | None = None
        self._fold_counters_reset_lbl: QLabel | None = None
        self._fold_counters_btn: QPushButton | None = None

        tranches = list(getattr(self._bot, "_fold_tranches", []) or [])
        # ext_rows is display-only; only tranches feeds trading logic.
        ext_rows: list[dict] = []
        try:
            _reader = getattr(self._bot, "open_extractor_tranches", None)
            if callable(_reader):
                _raw = _reader()
                if isinstance(_raw, list):
                    ext_rows = [r for r in _raw if isinstance(r, dict)]
        except Exception as _ext_exc:
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

        parked_usd = 0.0
        parked_unreadable = 0
        for _pt in tranches:
            _pt_usd = _as_finite_float(_pt.get("usd", 0))
            if _pt_usd is None:
                parked_unreadable += 1
            else:
                parked_usd += _pt_usd

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

        # The arithmetic, the empty-queue case and the colour band
        # all live in `compose_cycle_close_ratio`.
        discarded_lifetime = int(
            getattr(self._bot, "_tranches_discarded_lifetime", 0) or 0
        )
        ratio_str, ratio_colour = compose_cycle_close_ratio(
            created_lifetime, closed_lifetime, discarded_lifetime
        )

        # `install_health_row` sets the tooltip on both the label
        # and the value, so pointing at either shows it.
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

        # Despawn is age-driven and separate from the manual Clear button.
        install_despawn_rows(self, sf, tranches, now_ts)

        # Held on `self` so `_fold_panel_shows` reads the rebuilt
        # label rather than re-deriving it from the bot.
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
        # `compose_cycle_close_ratio` supplies both the text and its
        # colour, so the two cannot describe different quantities.
        if ratio_colour:
            ratio_lbl.setStyleSheet(f"color: {ratio_colour};")
        install_health_row(
            sf,
            "Cycle close ratio (folded / opened minus discarded):",
            ratio_lbl,
            FOLD_CLOSE_RATIO_TOOLTIP,
        )

        if discarded_lifetime:
            self._fold_discarded_lbl = QLabel(str(discarded_lifetime))
            install_health_row(
                sf,
                "Lifetime tranches discarded (not folded back):",
                self._fold_discarded_lbl,
                FOLD_DISCARDED_TOOLTIP,
            )

        # `_wire_credits_discarded_lifetime` is shown once non-zero,
        # matching the tranche-discarded row's convention.
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

        # `_tranches_malformed_dropped` is always shown; zero is a
        # positive statement that no stored tranche was unreadable.
        _malformed = int(getattr(self._bot, "_tranches_malformed_dropped", 0) or 0)
        _malformed_lbl = QLabel(str(_malformed))
        if _malformed:
            # A dropped tranche is a data fault, not a trading
            # outcome; same red as the close-ratio verdict.
            _malformed_lbl.setStyleSheet(f"color: {FOLD_OVER_ALLOTMENT_FG_HEX};")
        self._fold_malformed_lbl = _malformed_lbl
        install_health_row(
            sf,
            "Tranches dropped as malformed:",
            _malformed_lbl,
            FOLD_MALFORMED_TOOLTIP,
        )

        # Shown once non-zero, so a never-traded bot reads
        # differently from one whose counters were cleared.
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

        # `_fold_cycle_cap_consumed` is shown beside its budget;
        # the Settings tab already prints this same pair.
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

        # --- Clear tranches ---
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

        # Parked credit is a percent of gross proceeds, not profit,
        # cleared by its own button, not the tranche clear.
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

        # Separate button: the other two discard inventory; this
        # discards the lifetime record, resettable alone.
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

        # Column headers and per-column tooltips are the
        # authoritative per-tranche documentation, not prose text.

        # --- Per-tranche detail table ---
        if tranches or ext_rows:
            if ext_rows:
                _detail_title = (
                    f"Open Tranches ({open_count} fold, " f"{len(ext_rows)} extractor)"
                )
            else:
                _detail_title = f"Open Tranches ({open_count})"
            detail_group = QGroupBox(_detail_title)
            dl = QVBoxLayout(detail_group)

            # "Original cost $" is informational; "Min rebuy $" is
            # the binding per-tranche threshold.
            _otd_pct = 0.0
            _otd_factor = 1.0
            try:
                # Same otd_math call as `ScrummingBot.tick`, so this
                # cannot drift from the executor's own threshold.
                from ...trading.otd_math import (
                    fold_rebuy_factor_from_pct,
                    minimum_opposing_trade_distance_pct_from_config,
                )

                _otd_pct = minimum_opposing_trade_distance_pct_from_config(
                    self._bot.config
                )
                _otd_factor = fold_rebuy_factor_from_pct(_otd_pct)
            except Exception:
                _otd_pct = 0.0
                _otd_factor = 1.0

            table = QTableWidget()
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

            for _col, _tip in enumerate(FOLD_COLUMN_TOOLTIPS):
                _head = table.horizontalHeaderItem(_col)
                if _head is not None:
                    _head.setToolTip(_tip)

            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            # Extractor rows come last, so a fold row number is its tranches index.
            table.setRowCount(len(tranches) + len(ext_rows))
            # setFixedHeight makes the height a floor; _wrap_scrollable scrolls a taller table.
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

            # Held on self: setItemDelegate does not take ownership of the delegate.
            self._tranche_row_delegate = _TrancheRowBorderDelegate(table)
            table.setItemDelegate(self._tranche_row_delegate)

            # `setAlternatingRowColors` stays on: an explicit item
            # background always beats it, so painted rows hide it.

            # Vertical mass — a fill only reads as a container when
            # the band has height.
            table.verticalHeader().setDefaultSectionSize(TRANCHE_ROW_HEIGHT_PX)

            # _TrancheRowBorderDelegate draws the row edges the grid would.
            table.setShowGrid(False)

            # Try to fetch current price for status determination.
            # Falls back to "—" if unavailable.
            cur_price = 0.0
            try:
                stats = self._bot.get_status().get("stats", {})
                cur_price = float(stats.get("current_price", 0) or 0)
            except Exception:
                cur_price = 0.0

            # queue_index is the position in _fold_tranches, not the display row.
            _ordered = fold_display_order(tranches, fold_sort_order(self))
            for row, (queue_index, t) in enumerate(_ordered):
                table.setItem(row, 0, QTableWidgetItem(str(queue_index + 1)))

                # Same `created_ts` guard as the summary row above,
                # so both cannot disagree about one tranche's age.
                cts = _as_finite_float(t.get("created_ts"))
                if cts is not None and cts > 0:
                    age_str = self._format_age(now_ts - cts)
                else:
                    age_str = "—"
                table.setItem(row, 1, QTableWidgetItem(age_str))

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
                    # OTD == 0: no per-tranche threshold; shows
                    # ref-relative status instead.
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

                # The Source label names the action that CREATED
                # this row, not what a fold-back removes it with.
                src_str = _fold_tranche_source_label(t)
                si = QTableWidgetItem(src_str)
                si.setToolTip(FOLD_SOURCE_TOOLTIPS[src_str])
                if src_str == FOLD_SOURCE_MANUAL_SCRUM:
                    # `_paint_fold_tranche_row` never overwrites a
                    # cell that already owns a foreground brush.
                    si.setForeground(QColor(FOLD_SOURCE_MANUAL_FG_HEX))
                table.setItem(row, 8, si)

                # Captures the tranche dict by identity, so a
                # post-click index lookup survives list mutation.
                fire_btn = QPushButton("Fire")
                fire_btn.setToolTip(
                    "Operator-initiated fold-back of THIS tranche. "
                    "Bypasses TA / OTD / Target-Delta gates. Smart "
                    "Ceiling + MEM-257 fail-closed still apply. "
                    "Bot must be RUNNING."
                )
                # The inset leaves the row border delegate visible under the button.
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
                _captured = t
                _captured_number = queue_index + 1
                fire_btn.clicked.connect(
                    lambda _checked=False, tr=_captured, shown=_captured_number: self._on_fire_tranche_clicked(
                        tr, shown
                    )
                )
                table.setCellWidget(row, 9, fire_btn)

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

            # `_fold_panel_shows` subtracts `_fold_ext_row_count`
            # from the table's row count rather than reporting a sum.
            self._fold_tranche_table = table
            self._fold_ext_row_count = len(ext_rows)

            # Harvested from the built table, so the filter matches on-screen text.
            _harvested: list[list[str]] = []
            for _r in range(table.rowCount()):
                _cells: list[str] = []
                for _c in range(table.columnCount()):
                    _item = table.item(_r, _c)
                    _cells.append("" if _item is None else _item.text())
                _harvested.append(_cells)
            self._fold_row_texts = _harvested

            # Set before the layout first activates, so the tab's
            # own size hint carries the table's full row width.
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
        """Flip one Extractor Tranche's Arbiter. Moves no money.

        Resolves the child Extractor that owns the tranche via
        `self._bot._bot_manager` (not `self._bm`, which is None in
        the Paper Trader and in tests), asks it to flip one stored
        string, and relabels the button.

        Places no order, touches no balance, and schedules nothing
        onto the async loop — this sits one column from Fire and
        must stay display-only. No save is forced: the write is
        memory-only and persisted by the fleet's periodic save.

        If the tranche closed since the table was built, the child
        returns None and the button is left unchanged; nothing is
        written.
        """
        from PySide6.QtWidgets import QMessageBox

        # Each warning below names the check that actually ran and
        # states plainly that nothing was written.
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
            # `type(None).__name__` prints "NoneType", stating the
            # id matched no bot rather than guessing why.
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
        except Exception as exc:
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
        # Sets both the item and the button, so the stored value and
        # the widget cannot disagree.
        button.setText(label)
        button.setToolTip(tip)
        item.setText(label)
        item.setToolTip(tip)

    def _on_fire_tranche_clicked(
        self, tranche: dict, clicked_number: int | None = None
    ) -> None:
        """Confirm as Live confirms, then ask ``PaperBotView.manual_fire_tranche``.

        `idx` is the tranche's index resolved by identity and `_row_no` the
        number the operator clicked. The view raises ``SendRefused``, shown
        in Live's own refused box; no loop, no future and no timer.
        """
        from PySide6.QtWidgets import QMessageBox

        # Same `as_finite_float` helper the row builder used, so
        # the row and this confirmation cannot disagree.
        from ...trading.container.config import (
            as_finite_float as _as_finite_float,
        )

        try:
            tranches = list(getattr(self._bot, "_fold_tranches", []))
            # Resolve current index by identity
            try:
                idx = tranches.index(tranche)
            except ValueError:
                # No index to resolve: the tranche is gone. Naming
                # the clicked row tells the operator which one.
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

            # Every message below quotes `_row_no`; `idx` is kept
            # for the order alone.
            _row_no = idx + 1 if clicked_number is None else int(clicked_number)
            _moved = _row_no != idx + 1

            # ScrummingBot.manual_fire_tranche sizes the buy from the usd field.
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
                    # A refused value can be a 309-digit int, so the repr is bounded.
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

            try:
                self._bot.manual_fire_tranche(idx)
            except SendRefused as _refused:
                QMessageBox.warning(
                    self,
                    "Manual Fire refused",
                    f"Tranche #{_row_no} fold-back NOT applied.\n\n"
                    f"Reason: {_refused}",
                )
                return
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
