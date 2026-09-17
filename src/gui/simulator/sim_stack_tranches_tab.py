"""Stack Tranches tab of the Simulator's Bot Settings window, forked from
``live_settings.stack_tranches_tab``; every write reaches ``SimBotView`` and is refused.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .. import design_system as ds

if TYPE_CHECKING:
    from .sim_bot_detail import SimBotDetailDialog

logger = logging.getLogger("acervator.gui")


class SimStackTranchesTabMixin:
    """The Stack Tranches tab of ``SimBotDetailDialog``.

    ``_create_stack_tranches_tab`` builds the ladder,
    ``_on_clear_stack_tranches`` discards the standing records and
    ``_on_clear_stack_lifetime_counters`` zeroes the two counters.
    """

    # SimBotDetailDialog supplies these; the annotations create no attribute.
    _bot: Any
    _configure_form: Callable[..., Any]
    _format_age: Callable[..., Any]
    _save_fleet_state_now: Callable[..., Any]
    _wrap_scrollable: Callable[..., Any]

    STACK_TRANCHES_TAB_LABEL = "Stack Tranches"

    def _install_stack_tranches_tab(self, tabs: QTabWidget) -> QWidget:
        """Build the Stack Tranches tab and add it to ``tabs``.

        ``_refresh_stack_tranches_tab`` swaps the page kept in
        ``_stack_tab_page``.
        """
        page = self._wrap_scrollable(self._create_stack_tranches_tab())
        tabs.addTab(page, self.STACK_TRANCHES_TAB_LABEL)
        self._stack_tab_page = page
        return page

    def _refresh_stack_tranches_tab(self) -> str:
        """Rebuild the Stack Tranches tab at the index ``indexOf`` reports.

        Returns ``"refreshed"``, or a sentence naming why it did not;
        ``removeTab`` reparents the old page and ``deleteLater`` drops it.
        """
        tabs = getattr(self, "_tabs", None)
        page = getattr(self, "_stack_tab_page", None)
        if tabs is None or page is None:
            return "not refreshed: this dialog has no Stack " "Tranches tab installed"
        try:
            index = tabs.indexOf(page)
        except Exception as exc:
            logger.warning(
                "Stack Tranches refresh could not locate its tab (%s: %s)",
                type(exc).__name__,
                exc,
            )
            return (
                f"not refreshed: the tab could not be located "
                f"({type(exc).__name__})"
            )
        if index < 0:
            return (
                "not refreshed: the Stack Tranches tab is no " "longer in this dialog"
            )
        label = tabs.tabText(index)
        was_current = tabs.currentIndex() == index
        try:
            fresh = self._wrap_scrollable(self._create_stack_tranches_tab())
        except Exception as exc:
            logger.exception("Stack Tranches refresh raised while rebuilding")
            return (
                f"not refreshed: rebuilding the tab raised "
                f"{type(exc).__name__}: {exc}"
            )
        tabs.removeTab(index)
        tabs.insertTab(index, fresh, label)
        self._stack_tab_page = fresh
        if was_current:
            tabs.setCurrentIndex(index)
        page.setParent(None)
        page.deleteLater()
        return "refreshed"

    def _settle_after_stack_clear(self, what: str) -> list[str]:
        """Save the fleet, rebuild the Stack tab, and return the two lines.

        ``_save_fleet_state_now`` runs before
        ``_refresh_stack_tranches_tab``, and this path emits no pin.
        """
        saved, why = self._save_fleet_state_now(what)
        refresh = self._refresh_stack_tranches_tab()
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

    def _on_clear_stack_tranches(self: SimBotDetailDialog) -> None:
        """Confirm, then call ``bot.clear_stack_tranches``.

        A pending tranche carrying an ``order_id`` is kept, and the
        confirm box states that count.
        """
        from PySide6.QtWidgets import QMessageBox

        bot = self._bot
        tranches = list(getattr(bot, "_stack_tranches", []) or [])
        _live = [
            _t
            for _t in tranches
            if _t.get("status") == "pending" and _t.get("order_id")
        ]
        _droppable = len(tranches) - len(_live)
        if not _droppable:
            QMessageBox.information(
                self,
                "Clear stack tranches",
                "This bot has no stack tranche this clear may "
                "discard."
                + (
                    f"\n\n{len(_live)} tranche(s) hold resting "
                    f"exchange orders and are never removed."
                    if _live
                    else ""
                ),
            )
            return
        if not hasattr(bot, "clear_stack_tranches"):
            QMessageBox.warning(
                self,
                "Clear stack tranches",
                "This bot type does not support clearing stack " "tranches.",
            )
            return

        body = [
            f"Discard {_droppable} stack tranche(s) for "
            f"{getattr(bot.config, 'symbol', '')}?",
            "",
            "This places NO order and cancels NO order. Holdings, "
            "cost basis and target balance are untouched - only the "
            "queued intent to sell is discarded.",
            "",
            "This cannot be undone.",
        ]
        if _live:
            body += [
                "",
                f"NOTE - {len(_live)} tranche(s) hold resting "
                f"exchange orders and are KEPT. Removing a record "
                f"that owns a live order would leave that order on "
                f"the book with nothing tracking it.",
            ]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Clear stack tranches")
        box.setText("\n".join(body))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            return

        try:
            report = bot.clear_stack_tranches(reason="operator (GUI)")
        except Exception as exc:
            logger.exception("clear_stack_tranches failed: %s", exc)
            QMessageBox.critical(
                self,
                "Clear stack tranches",
                f"Nothing was cleared - the call failed:\n\n{exc}",
            )
            return

        _settled = self._settle_after_stack_clear("Clear stack tranches")
        _kept = int(report.get("kept_live_order", 0))
        QMessageBox.information(
            self,
            "Clear stack tranches",
            "\n\n".join(
                [
                    f"Discarded {int(report.get('count', 0))} stack "
                    f"tranche(s) covering "
                    f"{float(report.get('size', 0.0)):.8f} base "
                    f"units.",
                    "\n".join(_settled),
                    f"No order was placed or cancelled. "
                    f"{_kept} tranche(s) holding resting exchange "
                    f"orders were kept, and every holding, cost "
                    f"basis and target balance is unchanged.",
                ]
            ),
        )

    def _on_clear_stack_lifetime_counters(self: SimBotDetailDialog) -> None:
        """Confirm, then call ``bot.clear_stack_lifetime_counters``.

        ``_stack_created`` and ``_stack_discarded`` are the only two
        counters the Stack ledger keeps.
        """
        from PySide6.QtWidgets import QMessageBox

        bot = self._bot
        _counts = {
            "opened": int(getattr(bot, "_stack_created", 0) or 0),
            "discarded": int(getattr(bot, "_stack_discarded", 0) or 0),
        }
        if not sum(_counts.values()):
            QMessageBox.information(
                self,
                "Clear stack lifetime counters",
                "This bot's lifetime stack counters already read " "zero.",
            )
            return
        if not hasattr(bot, "clear_stack_lifetime_counters"):
            QMessageBox.warning(
                self,
                "Clear stack lifetime counters",
                "This bot type does not support clearing stack " "lifetime counters.",
            )
            return

        open_now = len(getattr(bot, "_stack_tranches", []) or [])
        body = [
            f"Set the two lifetime stack counters for "
            f"{getattr(bot.config, 'symbol', '')} to zero?",
            "",
            f"    opened    {_counts['opened']}",
            f"    discarded {_counts['discarded']}",
            "",
            "This places NO order and removes NO tranche. Standing "
            "stack tranches, holdings, cost basis and target balance "
            "are all unchanged - this clears the record of what "
            "happened, not what the bot holds.",
            "",
            "This cannot be undone.",
        ]
        if open_now:
            body += [
                "",
                f"NOTE - this bot still holds {open_now} stack "
                f"tranche(s). The panel reconciles opened minus "
                f"discarded against that count, so it will read 0 "
                f"against {open_now} until the next stack opens. No "
                f"tranche is lost.",
            ]

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Clear stack lifetime counters")
        box.setText("\n".join(body))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Cancel)
        if box.exec() != QMessageBox.Yes:
            return

        try:
            report = bot.clear_stack_lifetime_counters(reason="operator (GUI)")
        except Exception as exc:
            logger.exception("clear_stack_lifetime_counters failed: %s", exc)
            QMessageBox.critical(
                self,
                "Clear stack lifetime counters",
                f"Nothing was cleared - the call failed:\n\n{exc}",
            )
            return

        _settled = self._settle_after_stack_clear("Clear stack lifetime counters")
        _before = report.get("before", {}) or {}
        QMessageBox.information(
            self,
            "Clear stack lifetime counters",
            "\n\n".join(
                [
                    f"Cleared {int(report.get('cleared', 0))} counted "
                    f"stack event(s): opened "
                    f"{int(_before.get('created', 0))} and discarded "
                    f"{int(_before.get('discarded', 0))}.",
                    "Both now read 0 for this bot.",
                    "\n".join(_settled),
                    "No order was placed and no tranche was removed. "
                    f"This bot still holds "
                    f"{len(getattr(bot, '_stack_tranches', []) or [])} "
                    f"stack tranche(s) and every holding it had.",
                ]
            ),
        )

    def _create_stack_tranches_tab(self) -> QWidget:
        import time as _time

        from ...trading.container.config import (
            as_finite_float as _as_finite_float,
        )

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        tranches = list(getattr(self._bot, "_stack_tranches", []) or [])
        now_ts = _time.time()
        created_lifetime = int(getattr(self._bot, "_stack_created", 0) or 0)
        discarded_lifetime = int(
            _as_finite_float(getattr(self._bot, "_stack_discarded", 0)) or 0.0
        )
        reset_ts = (
            _as_finite_float(getattr(self._bot, "_stack_counters_reset_ts", 0.0)) or 0.0
        )

        summary = QGroupBox("Stack-Tranche Cycle Health")
        sf = QFormLayout(summary)
        self._configure_form(sf)

        pending = [t for t in tranches if t.get("status") == "pending"]
        filled = [t for t in tranches if t.get("status") == "filled"]
        cancelled = [t for t in tranches if t.get("status") == "cancelled"]

        # A size `as_finite_float` refuses is counted in
        # `pending_size_unreadable`, never dropped.
        pending_size_total = 0.0
        pending_size_unreadable = 0
        for _pending in pending:
            _pending_size = _as_finite_float(_pending.get("size", 0))
            if _pending_size is None:
                pending_size_unreadable += 1
            else:
                pending_size_total += _pending_size
        filled_ratio_str = (
            f"{len(filled) / created_lifetime:.1%}  "
            f"({len(filled)}/{created_lifetime})"
            if created_lifetime > 0
            else (
                "—  (counters cleared)" if reset_ts > 0 else "—  (no stacks opened yet)"
            )
        )

        sf.addRow("Pending tranches:", QLabel(str(len(pending))))
        sf.addRow("Filled tranches:", QLabel(str(len(filled))))
        sf.addRow("Cancelled tranches:", QLabel(str(len(cancelled))))

        pending_size_str = f"{pending_size_total:,.6f} base units"
        if pending_size_unreadable:
            pending_size_str += f"  (+{pending_size_unreadable} unreadable)"
        pending_lbl = QLabel(pending_size_str)
        pending_lbl.setStyleSheet(
            f"font-weight: bold; font-size: 13px; color: {ds.FOLD_RATIO_AMBER};"
        )
        sf.addRow("Pending size (unfilled):", pending_lbl)

        ages_sec = []
        for t in pending:
            ots = _as_finite_float(t.get("opened_ts"))
            if ots is not None and ots > 0:
                ages_sec.append(now_ts - ots)
        if ages_sec:
            oldest_str = self._format_age(max(ages_sec))
        elif pending:
            oldest_str = "— (no timestamp)"
        else:
            oldest_str = "no pending tranches"
        sf.addRow("Oldest pending age:", QLabel(oldest_str))

        sf.addRow("Lifetime tranches opened:", QLabel(str(created_lifetime)))

        ratio_lbl = QLabel(filled_ratio_str)
        if created_lifetime >= 3 and len(pending) > 0:
            _ratio = len(filled) / created_lifetime
            if _ratio < 0.3:
                ratio_lbl.setStyleSheet(f"color: {ds.ERROR};")
            elif _ratio < 0.7:
                ratio_lbl.setStyleSheet(f"color: {ds.FOLD_RATIO_AMBER};")
            else:
                ratio_lbl.setStyleSheet(f"color: {ds.SUCCESS};")
        sf.addRow("Fill ratio (filled/opened):", ratio_lbl)

        # `discarded_lifetime` accounts for a fill ratio that a
        # despawn sweep pushed down.
        if discarded_lifetime:
            sf.addRow(
                "Lifetime tranches discarded (removed, not filled):",
                QLabel(str(discarded_lifetime)),
            )

        layout.addWidget(summary)

        # `_droppable` and both buttons are built above the
        # empty-ledger return below.
        _droppable = len(
            [
                _t
                for _t in tranches
                if not (_t.get("status") == "pending" and _t.get("order_id"))
            ]
        )
        stack_clear_btn = QPushButton(
            f"Clear {_droppable} Stack Tranche(s)"
            if _droppable
            else "Clear Stack Tranches"
        )
        stack_clear_btn.setEnabled(bool(_droppable))
        stack_clear_btn.setToolTip(
            "Discard this bot's standing stack tranches.\n\n"
            "Places NO order and cancels NO order. Holdings, cost "
            "basis and target balance are untouched. A tranche "
            "holding a resting exchange order is KEPT - removing "
            "it would leave that order on the book with nothing "
            "tracking it."
        )
        stack_clear_btn.setStyleSheet(
            f"QPushButton {{ background: {ds.SETTINGS_DANGER_SURFACE}; color: {ds.FOLD_RATIO_AMBER}; "
            f"border: 1px solid {ds.ERROR}; padding: 6px 12px; }} "
            f"QPushButton:disabled {{ color: {ds.TEXT_MUTED}; "
            f"border-color: {ds.BORDER_DISABLED}; }}"
        )
        stack_clear_btn.clicked.connect(self._on_clear_stack_tranches)
        self._stack_clear_btn = stack_clear_btn

        _stack_counter_total = created_lifetime + discarded_lifetime
        stack_counters_btn = QPushButton(
            f"Clear Lifetime Counters ({created_lifetime} opened)"
            if _stack_counter_total
            else "Clear Lifetime Counters"
        )
        stack_counters_btn.setEnabled(bool(_stack_counter_total))
        stack_counters_btn.setToolTip(
            "Set this bot's two stack lifetime counters to "
            "zero.\n\n"
            "Places NO order and removes NO tranche. Standing stack "
            "tranches, holdings, cost basis and target balance are "
            "all untouched - this clears the record of what "
            "happened, not what the bot holds."
        )
        stack_counters_btn.setStyleSheet(
            f"QPushButton {{ background: {ds.SETTINGS_DANGER_SURFACE}; color: {ds.FOLD_RATIO_AMBER}; "
            f"border: 1px solid {ds.ERROR}; padding: 6px 12px; }} "
            f"QPushButton:disabled {{ color: {ds.TEXT_MUTED}; "
            f"border-color: {ds.BORDER_DISABLED}; }}"
        )
        stack_counters_btn.clicked.connect(self._on_clear_stack_lifetime_counters)
        self._stack_counters_btn = stack_counters_btn

        stack_btn_row = QHBoxLayout()
        stack_btn_row.addWidget(stack_clear_btn)
        stack_btn_row.addWidget(stack_counters_btn)
        stack_btn_row.addStretch()
        layout.addLayout(stack_btn_row)

        if not tranches:
            empty_lbl = QLabel(
                "No stack tranches yet. When Stack Mode is enabled "
                "and a SCRUM fires, tranches will appear here."
            )
            empty_lbl.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL}; padding: 12px;")
            empty_lbl.setWordWrap(True)
            layout.addWidget(empty_lbl)
            layout.addStretch()
            return w

        detail_group = QGroupBox(f"Tranches ({len(tranches)})")
        dg = QVBoxLayout(detail_group)

        header = QLabel(
            "  #  |  Target Price  |    Size      |  Mode     |  "
            "Status     |  Fill Price   |  Age"
        )
        header.setStyleSheet(
            "font-family: monospace; font-weight: bold; "
            f"color: {ds.TEXT_INFO_SOFT}; padding: 2px;"
        )
        dg.addWidget(header)

        # A value `as_finite_float` refuses renders `no_value`,
        # padded to the width its valid rendering occupies.
        no_value = "—"
        for t in tranches:
            _idx = _as_finite_float(t.get("index", 0))
            idx_str = f"{int(_idx):>2}" if _idx is not None else f"{no_value:>2}"
            _price = _as_finite_float(t.get("price", 0))
            price_str = f"${_price:>10.8f}" if _price is not None else f"{no_value:>11}"
            _size = _as_finite_float(t.get("size", 0))
            size_str = f"{_size:>10.6f}" if _size is not None else f"{no_value:>10}"
            status = str(t.get("status", "unknown"))
            mode = "VISIBLE" if t.get("visible") else "INVISIBLE"
            # A stored 0.0 fill price is falsy here and renders `no_value`.
            fill = t.get("fill_price")
            _fill = _as_finite_float(fill) if fill else None
            fill_str = f"${_fill:.8f}" if _fill is not None else no_value
            ots = _as_finite_float(t.get("opened_ts"))
            age_str = (
                self._format_age(now_ts - ots) if ots is not None and ots > 0 else "—"
            )
            row = QLabel(
                f"  {idx_str} |  {price_str}  |  {size_str}  |  "
                f"{mode:<9}|  {status:<10} |  {fill_str:<12} |  {age_str}"
            )
            row.setStyleSheet(
                "font-family: monospace; padding: 1px;"
                + (
                    f" color: {ds.SUCCESS};"
                    if status == "filled"
                    else f" color: {ds.ERROR};" if status == "cancelled" else ""
                )
            )
            dg.addWidget(row)

        layout.addWidget(detail_group)
        layout.addStretch()
        return w
