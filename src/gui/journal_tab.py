"""
journal_tab.py — Trade Journal & Recovery tab.

Shows trade journal entries with TA context, reconciliation results,
and crash recovery tools.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QComboBox,
        QPushButton, QGroupBox, QSplitter, QTextEdit,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:

    class JournalTab(QWidget):
        """Trade Journal & Recovery tab."""

        def __init__(self, journal=None, reconciliation=None,
                     crash_recovery=None, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Journal Tab")
            self._journal = journal
            self._recon = reconciliation
            self._recovery = crash_recovery
            self._setup_ui()

        def _setup_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            # Header with stats and controls
            header = QHBoxLayout()

            self._lbl_stats = QLabel("Journal: 0 entries")
            self._lbl_stats.setStyleSheet("color: #00ffcc; font-size: 13px; font-weight: bold;")
            header.addWidget(self._lbl_stats)

            header.addStretch()

            self._filter_bot = QComboBox()
            self._filter_bot.addItem("All Bots", "")
            self._filter_bot.setMinimumWidth(150)
            self._filter_bot.currentIndexChanged.connect(lambda: self.refresh())
            header.addWidget(QLabel("Bot:"))
            header.addWidget(self._filter_bot)

            self._filter_hours = QComboBox()
            for label, hours in [("1 Hour", 1), ("6 Hours", 6), ("24 Hours", 24),
                                  ("7 Days", 168), ("30 Days", 720)]:
                self._filter_hours.addItem(label, hours)
            self._filter_hours.setCurrentIndex(2)  # Default 24h
            self._filter_hours.currentIndexChanged.connect(lambda: self.refresh())
            header.addWidget(QLabel("Period:"))
            header.addWidget(self._filter_hours)

            layout.addLayout(header)

            # Main content
            splitter = QSplitter(Qt.Vertical)
            splitter.setHandleWidth(5)
            splitter.setChildrenCollapsible(False)

            # Trade journal table
            journal_group = QGroupBox("Trade Journal")
            journal_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }")
            journal_layout = QVBoxLayout(journal_group)

            self._journal_table = QTableWidget()
            self._journal_table.setColumnCount(10)
            self._journal_table.setHorizontalHeaderLabels([
                "Time", "Bot", "Symbol", "Action", "Side", "Price",
                "Qty", "P/L", "TA Dir", "Reason"])
            self._journal_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            self._journal_table.setAlternatingRowColors(True)
            self._journal_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._journal_table.verticalHeader().setVisible(False)
            self._journal_table.setSelectionBehavior(QTableWidget.SelectRows)
            self._journal_table.currentCellChanged.connect(self._on_entry_selected)
            journal_layout.addWidget(self._journal_table)
            splitter.addWidget(journal_group)

            # Bottom: entry detail + recovery
            bottom = QSplitter(Qt.Horizontal)
            bottom.setHandleWidth(5)
            bottom.setChildrenCollapsible(False)

            # Entry detail view
            detail_group = QGroupBox("Entry Detail")
            detail_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }")
            detail_layout = QVBoxLayout(detail_group)
            self._detail_view = QTextEdit()
            self._detail_view.setReadOnly(True)
            self._detail_view.setFont(QFont("Consolas", 9))
            self._detail_view.setStyleSheet(
                "QTextEdit { background: #0a0a12; color: #c0c0c0; border: none; }")
            detail_layout.addWidget(self._detail_view)
            bottom.addWidget(detail_group)

            # Recovery panel
            recovery_group = QGroupBox("State Recovery")
            recovery_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }")
            recovery_layout = QVBoxLayout(recovery_group)

            self._lbl_snapshot = QLabel("Last Snapshot: None")
            self._lbl_snapshot.setStyleSheet("color: #aaa;")
            recovery_layout.addWidget(self._lbl_snapshot)

            self._lbl_recon = QLabel("Last Reconciliation: None")
            self._lbl_recon.setStyleSheet("color: #aaa;")
            recovery_layout.addWidget(self._lbl_recon)

            self._lbl_orphans = QLabel("Orphaned Orders: 0")
            self._lbl_orphans.setStyleSheet("color: #aaa;")
            recovery_layout.addWidget(self._lbl_orphans)

            self._lbl_journal_files = QLabel("Journal Files: 0")
            self._lbl_journal_files.setStyleSheet("color: #aaa;")
            recovery_layout.addWidget(self._lbl_journal_files)

            btn_row = QHBoxLayout()
            self._btn_recon = QPushButton("Run Reconciliation")
            self._btn_recon.setStyleSheet(
                "QPushButton { background: #1a1a3f; color: #00ffcc; "
                "border: 1px solid #00ffcc; border-radius: 4px; padding: 6px 12px; }"
                "QPushButton:hover { background: #2a2a5f; }")
            btn_row.addWidget(self._btn_recon)

            self._btn_snapshot = QPushButton("Save Snapshot")
            self._btn_snapshot.setStyleSheet(
                "QPushButton { background: #1a1a3f; color: #00aaff; "
                "border: 1px solid #00aaff; border-radius: 4px; padding: 6px 12px; }"
                "QPushButton:hover { background: #2a2a5f; }")
            btn_row.addWidget(self._btn_snapshot)
            recovery_layout.addLayout(btn_row)

            recovery_layout.addStretch()
            bottom.addWidget(recovery_group)

            bottom.setSizes([500, 300])
            splitter.addWidget(bottom)
            splitter.setSizes([350, 250])
            layout.addWidget(splitter)

            # Store entries for detail view
            self._current_entries: list[dict] = []

        def _on_entry_selected(self, row, col, prev_row, prev_col):
            """Show detail for selected journal entry."""
            if row < 0 or row >= len(self._current_entries):
                return
            entry = self._current_entries[row]
            lines = [
                f'<span style="color:#00ffcc; font-weight:bold">Trade Detail</span>',
                f'<span style="color:#888">Time:</span> {time.ctime(entry.get("timestamp", 0))}',
                f'<span style="color:#888">Bot:</span> {entry.get("bot_id", "")[:12]}',
                f'<span style="color:#888">Symbol:</span> {entry.get("symbol", "")}',
                f'<span style="color:#888">Action:</span> {entry.get("action", "")}',
                f'<span style="color:#888">Side:</span> {entry.get("side", "")}',
                f'<span style="color:#888">Price:</span> ${entry.get("price", 0):.8f}',
                f'<span style="color:#888">Quantity:</span> {entry.get("quantity", 0):.8f}',
                f'<span style="color:#888">Cost:</span> ${entry.get("cost", 0):.4f}',
                f'<span style="color:#888">P/L:</span> '
                f'<span style="color:{"#00ff88" if entry.get("pnl", 0) >= 0 else "#ff3366"}">'
                f'${entry.get("pnl", 0):+.4f}</span>',
                "",
                f'<span style="color:#00aaff; font-weight:bold">TA Context</span>',
                f'<span style="color:#888">Direction:</span> {entry.get("ta_direction", "N/A")}',
                f'<span style="color:#888">Confidence:</span> {entry.get("ta_confidence", 0):.0%}',
                f'<span style="color:#888">Timeframe:</span> {entry.get("ta_timeframe", "N/A")}',
            ]

            # TA signals
            sigs = entry.get("ta_signals", {})
            if sigs:
                lines.append("")
                lines.append('<span style="color:#ffaa00; font-weight:bold">Indicator Votes</span>')
                for ind, direction in sigs.items():
                    color = "#00ff88" if direction == "BULLISH" else "#ff3366" if direction == "BEARISH" else "#888"
                    lines.append(f'  <span style="color:{color}">{ind}: {direction}</span>')

            # Execution
            lines.extend([
                "",
                f'<span style="color:#888">Exchange:</span> {entry.get("exchange_id", "")}',
                f'<span style="color:#888">Order ID:</span> {entry.get("order_id", "N/A")}',
                f'<span style="color:#888">Strategy:</span> {entry.get("execution_strategy", "market")}',
                f'<span style="color:#888">Slippage:</span> {entry.get("slippage_pct", 0):.4f}%',
                f'<span style="color:#888">Reason:</span> {entry.get("reason", "N/A")}',
            ])

            self._detail_view.setHtml("<br>".join(lines))

        def refresh(self, journal=None, reconciliation=None,
                    crash_recovery=None):
            """Refresh journal display."""
            j = journal or self._journal
            if not j:
                return

            # Update stats
            stats = j.get_statistics()
            self._lbl_stats.setText(
                f"Journal: {stats.get('total_entries', 0)} entries | "
                f"{stats.get('unique_bots', 0)} bots | "
                f"P/L: ${stats.get('total_pnl', 0):+,.4f}")

            # Get filtered entries
            bot_id = self._filter_bot.currentData() or ""
            hours = self._filter_hours.currentData() or 24

            entries = j.get_entries(bot_id=bot_id, hours=hours, limit=500)
            self._current_entries = entries

            self._journal_table.setRowCount(len(entries))
            for row, entry in enumerate(entries):
                ts = time.strftime("%H:%M:%S", time.localtime(entry.get("timestamp", 0)))
                pnl = entry.get("pnl", 0)
                items = [
                    ts,
                    entry.get("bot_id", "")[:8],
                    entry.get("symbol", ""),
                    entry.get("action", ""),
                    entry.get("side", ""),
                    f"${entry.get('price', 0):.4f}",
                    f"{entry.get('quantity', 0):.6f}",
                    f"${pnl:+.4f}",
                    entry.get("ta_direction", ""),
                    entry.get("reason", "")[:30],
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col == 7:  # P/L
                        color = QColor("#00ff88") if pnl >= 0 else QColor("#ff3366")
                        item.setForeground(color)
                    elif col == 8:  # TA direction
                        d = entry.get("ta_direction", "")
                        if d == "BULLISH":
                            item.setForeground(QColor("#00ff88"))
                        elif d == "BEARISH":
                            item.setForeground(QColor("#ff3366"))
                    self._journal_table.setItem(row, col, item)

            # Recovery info
            cr = crash_recovery or self._recovery
            if cr:
                info = cr.get_recovery_info()
                if info.get("has_snapshot"):
                    age = info.get("snapshot_age", 0)
                    age_str = f"{age:.0f}s ago" if age < 60 else f"{age / 60:.1f}m ago"
                    self._lbl_snapshot.setText(
                        f"Last Snapshot: {age_str} ({info.get('snapshot_bots', 0)} bots)")
                self._lbl_journal_files.setText(
                    f"Journal Files: {info.get('journal_files', 0)}")

            # Reconciliation info
            rc = reconciliation or self._recon
            if rc:
                latest = rc.get_latest_result()
                if latest:
                    ts = time.strftime("%H:%M:%S", time.localtime(latest["timestamp"]))
                    self._lbl_recon.setText(
                        f"Last Reconciliation: {ts} ({latest['exchange']})")
                    self._lbl_orphans.setText(
                        f"Orphaned Orders: {latest.get('orphaned_count', 0)}")

        def update_bot_filter(self, bot_statuses: list[dict]):
            """Update the bot filter dropdown."""
            current = self._filter_bot.currentData()
            self._filter_bot.blockSignals(True)
            self._filter_bot.clear()
            self._filter_bot.addItem("All Bots", "")
            for s in bot_statuses:
                bid = s.get("bot_id", "")
                sym = s.get("symbol", "???")
                self._filter_bot.addItem(f"{sym} [{bid[:8]}]", bid)
            idx = self._filter_bot.findData(current)
            if idx >= 0:
                self._filter_bot.setCurrentIndex(idx)
            self._filter_bot.blockSignals(False)
