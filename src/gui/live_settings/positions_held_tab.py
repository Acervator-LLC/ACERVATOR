"""Positions Held tab of the Live Bot Settings dialog."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QVBoxLayout,
    QWidget,
)

from .. import design_system as ds


class PositionsHeldTabMixin:
    """One row per open ExtractorPosition."""

    # Supplied by BotLiveSettingsDialog at runtime; annotation only, so
    # no attribute is created here.
    _bm: Any
    _bot: Any
    _configure_form: Callable[..., Any]

    def _create_positions_held_tab(self) -> QWidget:
        """Positions Held tab for Extractor bots.

        Draws one row per open ExtractorPosition with the columns Pair,
        State, Tier, Alt units, Entry (USD), Current (USD), Δ% (USD),
        Corrections and a per-position Manual Fire button.

        Per operator decision #7 the Manual Fire button is per-position
        only. Its handler is bound to the position's pair and opening
        stamp, so two rows on one pair stay apart, and it closes that
        position at market via ``ExtractorBot.manual_fire_position``.

        A reading the position does not carry, and one that cannot be
        read, are both drawn as an em dash in the warning colour. No
        number is invented here: the bot applies its own average-buy
        fallback when it builds the row. One unreadable position costs
        no other row.
        """
        from PySide6.QtWidgets import (
            QGroupBox,
            QFormLayout,
            QLabel,
            QPushButton,
            QTableWidget,
            QTableWidgetItem,
            QHeaderView,
            QMessageBox,
        )
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QColor
        import asyncio as _asyncio

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        summary = QGroupBox("Extractor Pool Status")
        sf = QFormLayout(summary)
        self._configure_form(sf)
        chunk_size_usd = float(getattr(self._bot, "_chunk_size_usd", 0.0) or 0.0)
        chunk_free_base = float(getattr(self._bot, "_chunk_free_base", 0.0) or 0.0)
        chunk_size_base = float(getattr(self._bot, "_chunk_size_base", 0.0) or 0.0)
        extracted_total = float(
            getattr(self._bot, "_chunk_extracted_total", 0.0) or 0.0
        )
        base_currency = self._bot.config.base_currency
        try:
            pool_color = self._bot.pool_color()
        except Exception:
            pool_color = "green"
        pool_name = str(pool_color).upper()
        color_hex = {
            "green": ds.SUCCESS,
            "yellow": ds.WARNING,
            "red": ds.ERROR,
        }.get(pool_color, ds.TEXT_MED)
        pool_lbl = QLabel(f"<b>{pool_name}</b>")
        pool_lbl.setStyleSheet(f"color: {color_hex}; font-size: 14px;")
        sf.addRow("Pool color:", pool_lbl)
        sf.addRow(
            f"Chunk size ({base_currency} / USD):",
            QLabel(f"{chunk_size_base:.8f} / ${chunk_size_usd:,.2f}"),
        )
        sf.addRow(f"Chunk free ({base_currency}):", QLabel(f"{chunk_free_base:.8f}"))
        sf.addRow(
            f"Lifetime extracted ({base_currency}):",
            QLabel(f"{extracted_total:+.8f}"),
        )
        layout.addWidget(summary)

        read_failed = False
        try:
            positions = self._bot.positions_for_gui()
        except Exception:
            positions = []
            read_failed = True

        if not positions:
            if read_failed:
                empty_text = (
                    "<i>Could not read the open positions from the bot. "
                    "This tab shows <b>no position data</b> and makes no "
                    "claim about the pool. Re-open the dialog to read "
                    "again.</i>"
                )
            else:
                empty_text = (
                    "<i>No open positions. Bot is watching its top-N "
                    "watch list for bearish signals. Pool color is "
                    f"<b>{pool_name}</b> (fully in base currency).</i>"
                )
            empty_lbl = QLabel(empty_text)
            empty_lbl.setWordWrap(True)
            empty_lbl.setStyleSheet(f"color: {ds.TEXT_EMPTY_STATE}; padding: 16px;")
            layout.addWidget(empty_lbl)
            layout.addStretch()
            return w

        table = QTableWidget()
        columns = [
            "Pair",
            "State",
            "Tier",
            "Alt units",
            "Entry (USD)",
            "Current (USD)",
            "Δ% (USD)",
            "Corrections",
            "Manual Fire",
        ]
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setRowCount(len(positions))
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)

        # The column each reading fills, matching the map the surface holds.
        unreadable_columns = {
            "tier": 2,
            "alt_units": 3,
            "entry_usd": 4,
            "current_usd": 5,
            "delta_pct": 6,
            "corrections": 7,
        }
        number_plan = (
            ("tier", "tier", 1, True),
            ("alt_units", "alt_units", 0.0, False),
            ("entry_usd", "entry_usd", 0.0, False),
            ("current_usd", "current_usd_approx", 0.0, False),
            ("delta_pct", "delta_pct_usd_approx", 0.0, False),
            ("corrections", "corrections_fired", 0, True),
        )

        for row, p in enumerate(positions):
            pair = str(p.get("pair", ""))
            state = str(p.get("state", ""))
            opened_at = str(p.get("opened_at", ""))
            read: dict = {}
            unreadable = []
            for name, key, fallback, whole in number_plan:
                if key not in p:
                    read[name] = fallback
                    unreadable.append(name)
                    continue
                try:
                    read[name] = int(p[key]) if whole else float(p[key])
                except (TypeError, ValueError, OverflowError):
                    read[name] = fallback
                    unreadable.append(name)

            cells = [
                pair,
                state.upper(),
                str(read["tier"]),
                f"{read['alt_units']:.6f}",
                f"${read['entry_usd']:,.4f}",
                f"${read['current_usd']:,.4f}",
                f"{read['delta_pct']:+.2f}%",
                str(read["corrections"]),
            ]
            painted = sorted(unreadable_columns[name] for name in unreadable)
            for col in painted:
                cells[col] = "—"

            for col, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                item.setTextAlignment(Qt.AlignCenter)
                # State cell color: red on drawdown, amber on
                # bullish_exit-pending, green on in_flight
                if col == 1:
                    if state == "drawdown":
                        item.setForeground(Qt.red)
                    elif state == "bullish_exit":
                        item.setForeground(Qt.yellow)
                    else:
                        item.setForeground(Qt.green)
                # Δ% color: green if positive, red if negative
                if col == 6:
                    if read["delta_pct"] > 0:
                        item.setForeground(Qt.green)
                    elif read["delta_pct"] < 0:
                        item.setForeground(Qt.red)
                # A reading nobody could take is drawn in the warning
                # colour, over whatever the two rules above painted.
                if col in painted:
                    item.setForeground(QColor(ds.WARNING))
                table.setItem(row, col, item)

            fire_btn = QPushButton("Fire")
            fire_btn.setFixedHeight(24)
            fire_btn.setStyleSheet(
                f"QPushButton {{ background: {ds.WARNING_STRONG}; color: white; "
                "border: none; border-radius: 4px; padding: 4px 12px; "
                "font-weight: bold; }"
                f"QPushButton:hover {{ background: {ds.SETTINGS_WARNING_HOVER}; }}"
            )

            def _make_fire_handler(identity: list):
                def _on_fire():
                    pair_to_fire = identity[0]
                    # Confirmation dialog — operator-initiated
                    # release is irreversible at the exchange.
                    confirm = QMessageBox.question(
                        self,
                        "Manual Fire — confirm position close",
                        f"Close position on <b>{pair_to_fire}</b> "
                        f"at current market price?<br><br>"
                        f"This will fire a 100% market SELL on the "
                        f"alt units, returning base currency to the "
                        f"pool. Bypasses the auto path's "
                        f"base-unit-profitability gate per "
                        f"operator-sovereignty invariant.<br>"
                        f"<br>Fail-closed buy safety still applies.",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if confirm != QMessageBox.Yes:
                        return

                    # Schedule the close on the bot manager's loop
                    loop = getattr(self._bm, "_async_loop", None) if self._bm else None
                    if loop is None:
                        QMessageBox.warning(
                            self,
                            "Async loop unavailable",
                            "Bot manager async loop not running. "
                            "Try again after platform launch completes.",
                        )
                        return

                    coro = self._bot.manual_fire_position(pair_to_fire)
                    try:
                        _asyncio.run_coroutine_threadsafe(coro, loop)
                    except Exception as exc:
                        QMessageBox.warning(
                            self,
                            "Schedule failed",
                            f"Could not schedule the close:\n\n"
                            f"{type(exc).__name__}: {exc}",
                        )
                        return

                    # Non-blocking: the completion or refusal line arrives
                    # later on the main window's bot.log subscription.
                    QMessageBox.information(
                        self,
                        "Manual Fire dispatched",
                        f"Close dispatched for <b>{pair_to_fire}</b>. "
                        f"Watch the Activity Log for the completion "
                        f"line. Re-open this dialog after the order "
                        f"settles to see updated state.",
                    )

                return _on_fire

            fire_btn.clicked.connect(_make_fire_handler([pair, opened_at]))
            table.setCellWidget(row, 8, fire_btn)

        layout.addWidget(table, stretch=1)

        # The footer explains the per-row Fire button, so the branch
        # that draws no button leaves it out.
        footer = QLabel(
            "<b>Per-position Manual Fire</b> (operator decision #7): "
            "each button closes ITS position at current market "
            "price. Bypasses the auto path's base-unit-profitability "
            "gate per operator-sovereignty invariant. "
            "FAIL-CLOSED BUY SAFETY still applies to any new buys the "
            "bot subsequently initiates (artillery, correction) on "
            "behalf of the pool."
        )
        footer.setWordWrap(True)
        footer.setStyleSheet(
            f"color: {ds.TEXT_EMPTY_STATE}; padding: 8px; " "font-size: 11px;"
        )
        layout.addWidget(footer)
        return w
