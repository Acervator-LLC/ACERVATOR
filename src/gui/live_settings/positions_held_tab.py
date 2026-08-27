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

    # Supplied by BotLiveSettingsDialog at runtime; declared so a
    # type checker can resolve them. Annotations only: no attribute
    # is created and the runtime base stays `object`.
    _bm: Any
    _bot: Any
    _configure_form: Callable[..., Any]

    def _create_positions_held_tab(self) -> QWidget:
        """v3.19.3 — Positions Held tab for Extractor bots.

        Renders one row per open ExtractorPosition with the columns
        from design doc §10: Pair | State | Tier | Alt units |
        Entry (USD) | Current (USD) | Δ% (USD) | Corrections |
        Manual Fire (button).

        Per operator decision #7, the Manual Fire button is
        per-position only — NO global fire on the bot row. Clicking
        a row's button immediately closes that specific position at
        market via ``ExtractorBot.manual_fire_position(pair)``.

        Position values reported here use the position's stored
        avg-buy price as a fallback; live ticker refresh happens
        asynchronously by the bot's tick loop. Operator can re-open
        the dialog (or rely on the bot table's pool color) for
        up-to-date status.

        sadp: R28 R55  # manual override per-position + non-blocking dispatch
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
        import asyncio as _asyncio

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        # --- Summary section ---
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
        except Exception:  # R28-OK: snapshot read; UI doesn't crash on bot lookup
            pool_color = "green"
        color_hex = {
            "green": ds.SUCCESS,
            "yellow": ds.WARNING,
            "red": ds.ERROR,
        }.get(pool_color, ds.TEXT_MED)
        pool_lbl = QLabel(f"<b>{pool_color.upper()}</b>")
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

        # --- Positions table ---
        try:
            positions = self._bot.positions_for_gui()
        except Exception:  # R28-OK: snapshot read; UI doesn't crash
            positions = []

        if not positions:
            empty_lbl = QLabel(
                "<i>No open positions. Bot is watching its top-N "
                "watch list for bearish signals. Pool color is "
                "<b>GREEN</b> (fully in base currency).</i>"
            )
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

        for row, p in enumerate(positions):
            pair = str(p.get("pair", ""))
            state = str(p.get("state", ""))
            tier = int(p.get("tier", 1))
            alt_units = float(p.get("alt_units", 0.0))
            entry_usd = float(p.get("entry_usd", 0.0))
            current_usd = float(p.get("current_usd_approx", 0.0))
            delta_pct = float(p.get("delta_pct_usd_approx", 0.0))
            corrections = int(p.get("corrections_fired", 0))

            cells = [
                pair,
                state.upper(),
                str(tier),
                f"{alt_units:.6f}",
                f"${entry_usd:,.4f}",
                f"${current_usd:,.4f}",
                f"{delta_pct:+.2f}%",
                str(corrections),
            ]
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
                    if delta_pct > 0:
                        item.setForeground(Qt.green)
                    elif delta_pct < 0:
                        item.setForeground(Qt.red)
                table.setItem(row, col, item)

            # Manual Fire button — operator decision #7
            fire_btn = QPushButton("Fire")
            fire_btn.setFixedHeight(24)
            fire_btn.setStyleSheet(
                f"QPushButton {{ background: {ds.WARNING_STRONG}; color: white; "
                "border: none; border-radius: 4px; padding: 4px 12px; "
                "font-weight: bold; }"
                f"QPushButton:hover {{ background: {ds.SETTINGS_WARNING_HOVER}; }}"
            )

            def _make_fire_handler(pair_to_fire: str):
                def _on_fire():
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
                        f"operator-sovereignty (v3.18.15 invariant).<br>"
                        f"<br>MEM-257 fail-closed still applies.",
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

                    # Non-blocking dispatch — same pattern as
                    # manual_fire_tranche (v3.16.55). The bot.log
                    # event subscription on the main window surfaces
                    # the outcome via "EXTRACTOR MANUAL FIRE COMPLETE"
                    # / refusal log lines.
                    QMessageBox.information(
                        self,
                        "Manual Fire dispatched",
                        f"Close dispatched for <b>{pair_to_fire}</b>. "
                        f"Watch the Activity Log for the completion "
                        f"line. Re-open this dialog after the order "
                        f"settles to see updated state.",
                    )

                return _on_fire

            fire_btn.clicked.connect(_make_fire_handler(pair))
            table.setCellWidget(row, 8, fire_btn)

        layout.addWidget(table, stretch=1)

        # --- Footer explainer ---
        footer = QLabel(
            "<b>Per-position Manual Fire</b> (operator decision #7): "
            "each button closes ITS position at current market "
            "price. Bypasses the auto path's base-unit-profitability "
            "gate per operator-sovereignty invariant (v3.18.15). "
            "MEM-257 FAIL-CLOSED still applies to any new buys the "
            "bot subsequently initiates (artillery, correction) on "
            "behalf of the pool."
        )
        footer.setWordWrap(True)
        footer.setStyleSheet(
            f"color: {ds.TEXT_EMPTY_STATE}; padding: 8px; " "font-size: 11px;"
        )
        layout.addWidget(footer)
        return w
