"""Stack Tranches tab of the Live Bot Settings dialog."""

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
    from ..bot_live_settings import BotLiveSettingsDialog

logger = logging.getLogger("acervator.gui")


class StackTranchesTabMixin:
    """The stack ladder and its clear controls."""

    # Supplied by BotLiveSettingsDialog at runtime; declared so a
    # type checker can resolve them. Annotations only: no attribute
    # is created and the runtime base stays `object`.
    _bot: Any
    _configure_form: Callable[..., Any]
    _format_age: Callable[..., Any]
    _save_fleet_state_now: Callable[..., Any]
    _wrap_scrollable: Callable[..., Any]

    # --- issue #133 unit 7: the Stack side gets the Fold side's
    # controls ---------------------------------------------------
    #
    # The Fold Tranches tab carries three clear buttons, a rebuild
    # that runs inside the click and a save that reaches disk. The
    # Stack Tranches tab carried none of the three, so one side of
    # the ladder could be emptied and reset by the operator and the
    # other could not. These four methods are that mirror.
    STACK_TRANCHES_TAB_LABEL = "Stack Tranches"

    def _install_stack_tranches_tab(self, tabs: QTabWidget) -> QWidget:
        """Build the Stack Tranches tab, add it, and remember it.

        ONE INSTALL SITE, so the handle a later refresh swaps is
        never a second bookkeeping step somebody can forget.
        """
        page = self._wrap_scrollable(self._create_stack_tranches_tab())
        tabs.addTab(page, self.STACK_TRANCHES_TAB_LABEL)
        self._stack_tab_page = page
        return page

    def _refresh_stack_tranches_tab(self) -> str:
        """Rebuild the Stack Tranches tab in place. Return a status.

        Returns "refreshed", or a sentence naming why it did not.
        THE STRING IS LOAD-BEARING: the message the operator reads
        after a clear quotes it, so a rebuild that could not run
        says so instead of the panel quietly lying twice.

        THE TAB IS FOUND BY WIDGET IDENTITY, NOT BY A STORED INDEX,
        and `removeTab` + `insertTab` land it at the same index, so
        no other tab renumbers. `removeTab` reparents the old page
        rather than deleting it, so the page is deleted here; without
        that every clear leaks a whole tab's widget tree for the life
        of the dialog. All three points are `_refresh_fold_tranches_
        tab`'s, and this is that method pointed at the other ledger.
        """
        tabs = getattr(self, "_tabs", None)
        page = getattr(self, "_stack_tab_page", None)
        if tabs is None or page is None:
            return "not refreshed: this dialog has no Stack " "Tranches tab installed"
        try:
            index = tabs.indexOf(page)
        except Exception as exc:  # R28-OK: display-only rebuild
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
        except Exception as exc:  # R28-OK: display-only rebuild
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
        """Save, rebuild the Stack tab, report the lines.

        THE ORDER IS SAVE, THEN REFRESH, for `_settle_after_clear`'s
        reason: the durable write is the one a crash can take away,
        so a crash between the two costs a stale panel and not a
        restored tranche.

        IT EMITS NO PIN, AND THAT IS DELIBERATE.
        `gui.04.002.postcondition.clear_settled` carries fold_rows,
        open_tranches_label and two fold button states; firing it
        from here would put stack numbers under a fold pin's name and
        make its record mean two things. The emitter network is not
        this unit's to extend, so this path stays unpinned and says
        so.
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

    def _on_clear_stack_tranches(self: BotLiveSettingsDialog) -> None:
        """Discard this bot's standing Stack tranches, after
        confirming.

        THE DIALOG STATES THE ONE REFUSAL. A Visible-mode tranche
        holding a resting exchange order is KEPT, because delisting a
        record that owns a live order would strand it. The operator
        sees that count before deciding, so a clear that leaves rows
        on screen is expected rather than a surprise.
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
                    f"exchange orders and are never delisted."
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
                f"exchange orders and are KEPT. Delisting a record "
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
        except Exception as exc:  # noqa: BLE001 - operator surface
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

    def _on_clear_stack_lifetime_counters(self: BotLiveSettingsDialog) -> None:
        """Zero this bot's two stack lifetime counters, after
        confirming.

        TWO COUNTERS, NOT FOUR. The Stack ledger has no closed count
        and no malformed count: filling a stack tranche sets its
        status and leaves the record listed, so `opened - discarded`
        against the standing ledger is the whole reconciliation this
        clear breaks until the next stack opens.
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
        except Exception as exc:  # noqa: BLE001 - operator surface
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

    # ---------------------------------------------------------------
    # Tab 3.5: Stack Tranches (v3.23.28, scrumming + stack_mode only)
    # ---------------------------------------------------------------
    # Mirrors Fold Tranches styling. Reads `_bot._stack_tranches` +
    # `_bot._stack_created`. Surfaces per-tranche state (target
    # price, size, mode Visible/Invisible, status, fill price, age)
    # so operator can see Stack lifecycle without needing a log dump.
    def _create_stack_tranches_tab(self) -> QWidget:
        import time as _time

        # Item 9 (2026-08-13) — the same admission rule the despawn
        # sweep and the Settings spinbox use, imported here the way
        # this module imports every other trading symbol: locally,
        # so building a tab never drags the trading package in at
        # module import time.
        from ...trading.bot_container import (
            as_finite_float as _as_finite_float,
        )

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        tranches = list(getattr(self._bot, "_stack_tranches", []) or [])
        now_ts = _time.time()
        created_lifetime = int(getattr(self._bot, "_stack_created", 0) or 0)
        # HOISTED ABOVE THE SUMMARY ROWS because the clear
        # buttons below read it too. Read through
        # `as_finite_float` rather than the Fold panel's bare
        # `int(... or 0)`: `int(float("nan"))` raises
        # ValueError, and this runs while the tab is being
        # built, so the operator would get a traceback
        # instead of a panel.
        discarded_lifetime = int(
            _as_finite_float(getattr(self._bot, "_stack_discarded", 0)) or 0.0
        )
        # issue #133 unit 7 -- the epoch second an operator
        # cleared the two counters, 0.0 when none has. It
        # tells a bot that never opened a stack apart from
        # one whose record was reset, which a bare 0 cannot.
        reset_ts = (
            _as_finite_float(getattr(self._bot, "_stack_counters_reset_ts", 0.0)) or 0.0
        )

        # --- Summary ---
        summary = QGroupBox("Stack-Tranche Cycle Health")
        sf = QFormLayout(summary)
        self._configure_form(sf)

        pending = [t for t in tranches if t.get("status") == "pending"]
        filled = [t for t in tranches if t.get("status") == "filled"]
        cancelled = [t for t in tranches if t.get("status") == "cancelled"]

        # Item 10 (2026-08-14) — the same admission rule
        # the two age rows already use, applied to the money keys
        # on the same dict. `size` is read here and again on the
        # detail row below, so both must refuse the same shapes
        # or the panel contradicts itself.
        #
        # A REFUSED MEMBER IS COUNTED, NOT DROPPED. Silently
        # skipping an unreadable entry reports a total lower
        # than the truth with nothing on the panel saying so.
        # That is the shape of the claim-total defect of
        # 2026-08-10, which reported $2,000 against a true
        # $3,000 and logged nothing. The count rides beside the
        # number instead.
        #
        # `or 0` IS GONE. It mapped None, "" and False onto the
        # int 0 before any guard could see them, so a missing
        # size printed a confident 0.000000 into a base-unit
        # total. `t.get("size", 0)` still defaults an ABSENT key
        # to 0, which is what it rendered before and still
        # renders.
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

        # Oldest pending age
        # EXACT type AND finite, mirroring the Fold panel's own
        # summary row. `isinstance` admits bool, so a stored
        # `True` was arithmetic'd as 1.0 — dating the tranche to
        # the epoch and reporting an age near 57 years on the
        # row the operator reads to judge whether Stack Mode has
        # stalled. `inf` was worse than wrong: it passed the
        # `> 0` test, and `int(-inf)` inside `_format_age` then
        # raised OverflowError with no `try` between here and
        # the click, so the dialog would not open at all.
        # `as_finite_float` bounds huge ints with an integer
        # comparison rather than `math.isfinite`, which raises
        # on the very input it would be added to reject.
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

        # Item 9 (2026-08-13) — the mirror of the Fold panel's own
        # discarded row. `filled` counts only STANDING filled
        # tranches, `created_lifetime` counts every one ever opened,
        # and the despawn sweep removes records from the first while
        # leaving the second alone. Without this row the ratio above
        # simply falls after every sweep — into the red under 30% —
        # with nothing on the panel saying where the tranches went.
        # Shown only once non-zero, exactly as the Fold panel does,
        # so a bot that has never been swept sees no extra row.
        #
        # Read through `as_finite_float` rather than the Fold
        # panel's bare `int(... or 0)`. Same reason as the state
        # export: `int(float("nan"))` raises ValueError, and this
        # runs while the Stack tab is being built, so the operator
        # would get a traceback instead of a panel. The Fold panel's
        # line is unchanged — putting both on one rule is a separate
        # unit.
        if discarded_lifetime:
            sf.addRow(
                "Lifetime tranches discarded (delisted, not filled):",
                QLabel(str(discarded_lifetime)),
            )

        layout.addWidget(summary)

        # --- issue #133 unit 7: the Fold tab's clear controls,
        # mirrored ----------------------------------------------
        # Same two verbs the Fold tab carries and the same order:
        # the INVENTORY clear first, the RECORD clear second. A bot
        # can want its ledger emptied with its history intact, or
        # the reverse, so they stay two buttons.
        #
        # BUILT BEFORE THE EMPTY-LEDGER RETURN BELOW, so a bot with
        # counters and no standing tranche can still reset its
        # counters. The Fold tab's buttons sit in the same place for
        # the same reason.
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
            "holding a resting exchange order is KEPT - delisting "
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

        # --- Detail ---
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

        # Header row
        header = QLabel(
            "  #  |  Target Price  |    Size      |  Mode     |  "
            "Status     |  Fill Price   |  Age"
        )
        header.setStyleSheet(
            "font-family: monospace; font-weight: bold; "
            f"color: {ds.TEXT_INFO_SOFT}; padding: 2px;"
        )
        dg.addWidget(header)

        # Item 10 (2026-08-14) — every numeric key on
        # the row, on the one rule. NONE of these had a guard,
        # and NONE of them sits inside a `try`: the path from
        # here is `_create_stack_tranches_tab` -> `__init__` ->
        # `MainWindow._on_bot_clicked`, with no handler at any
        # step, so a raise means Bot Settings does not open for
        # that bot at all.
        #
        # Measured on live before this change: `index` of `inf`
        # raised OverflowError, of `nan` ValueError, and of None
        # or a string TypeError and ValueError; `price`, `size`
        # and `fill_price` of 10**400 raised OverflowError from
        # `float()`. `nan` and `inf` did not raise, which was
        # worse: they printed `$nan` and `$inf` into a money
        # column. `as_finite_float` bounds huge ints with an
        # integer comparison, because `math.isfinite(10**400)`
        # raises the very error it would be added to prevent.
        #
        # WHY A REFUSAL IS AN EM DASH AND NEVER A ZERO. These
        # columns carry money and size. A refused value that
        # renders 0.00000000 is a confident wrong number, which
        # is a new defect rather than a fix. The em dash is what
        # this table already prints for an absent fill price and
        # an unusable timestamp, so a refusal lands on a path
        # the panel already had. Each is padded to the minimum
        # width its valid rendering occupies, so the column
        # stays aligned.
        #
        # `index` is an ordinal, so it takes the em dash too,
        # and an accepted value goes through `int()` exactly as
        # the discarded-count row above does.
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
            # The truthiness gate is KEPT. A stored 0.0 fill
            # price printed the em dash before this change and
            # must keep printing it; admitting it here would
            # change a valid rendering, which this unit may not
            # do.
            fill = t.get("fill_price")
            _fill = _as_finite_float(fill) if fill else None
            fill_str = f"${_fill:.8f}" if _fill is not None else no_value
            # The same rule as the summary row above, which
            # this column must agree with: both render the age
            # of the same tranche from the same key. The bare
            # `float(ots)` here was the wider hole of the two —
            # it also admitted Decimal, Fraction, a numeric
            # string and any object with `__float__` — so
            # closing the summary alone would have left this row
            # printing an age directly beneath a summary
            # reporting no timestamp for that same tranche.
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
