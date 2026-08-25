"""
alerts_tab.py — Notifications & Alerts configuration tab.

Configure Telegram, SMS, per-event routing, and view notification history.
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QFrame,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QCheckBox,
        QPushButton,
        QGroupBox,
        QSplitter,
        QLineEdit,
        QFormLayout,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont

    _HAS_QT = True
except ImportError:
    _HAS_QT = False

if _HAS_QT:

    class AlertsTab(QWidget):
        """Notifications & Alerts tab."""

        def __init__(self, notification_manager=None, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Notifications and Alerts tab")
            self._notif = notification_manager
            self._setup_ui()

        def _setup_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)

            main_split = QSplitter(Qt.Horizontal)
            main_split.setHandleWidth(5)
            main_split.setChildrenCollapsible(False)

            # Left: channel configuration
            left = QWidget()
            left_layout = QVBoxLayout(left)
            left_layout.setContentsMargins(0, 0, 0, 0)

            # Status
            self._lbl_status = QLabel("Notifications: Active")
            self._lbl_status.setStyleSheet(
                "color: #00ffcc; font-size: 14px; font-weight: bold;"
            )
            left_layout.addWidget(self._lbl_status)

            self._lbl_unread = QLabel("Unread: 0")
            self._lbl_unread.setStyleSheet("color: #ffaa00; font-size: 12px;")
            left_layout.addWidget(self._lbl_unread)

            # Telegram config
            tg_group = QGroupBox("Telegram Bot")
            tg_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }"
            )
            tg_form = QFormLayout(tg_group)

            self._tg_token = QLineEdit()
            self._tg_token.setPlaceholderText("Bot token from @BotFather")
            self._tg_token.setEchoMode(QLineEdit.Password)
            tg_form.addRow("Bot Token:", self._tg_token)

            self._tg_chat = QLineEdit()
            self._tg_chat.setPlaceholderText("Chat ID (use @userinfobot)")
            tg_form.addRow("Chat ID:", self._tg_chat)

            self._tg_test = QPushButton("Test Telegram")
            self._tg_test.setStyleSheet(
                "QPushButton { background: #1a1a3f; color: #00aaff; "
                "border: 1px solid #00aaff; border-radius: 4px; padding: 6px; }"
            )
            self._tg_test.clicked.connect(self._test_telegram)
            tg_form.addRow(self._tg_test)

            self._tg_status = QLabel("")
            tg_form.addRow(self._tg_status)
            left_layout.addWidget(tg_group)

            # SMS config
            sms_group = QGroupBox("SMS Alerts")
            sms_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }"
            )
            sms_form = QFormLayout(sms_group)

            self._sms_phone = QLineEdit()
            self._sms_phone.setPlaceholderText("+1234567890")
            sms_form.addRow("Phone:", self._sms_phone)

            self._sms_status = QLabel("Not configured")
            self._sms_status.setStyleSheet("color: #888;")
            sms_form.addRow(self._sms_status)
            left_layout.addWidget(sms_group)

            # Save button
            self._btn_save = QPushButton("Save Configuration")
            self._btn_save.setStyleSheet(
                "QPushButton { background: #00ffcc; color: #0a0a12; "
                "border: none; border-radius: 4px; padding: 8px; "
                "font-weight: bold; }"
                "QPushButton:hover { background: #00ddaa; }"
            )
            self._btn_save.clicked.connect(self._save_config)
            left_layout.addWidget(self._btn_save)

            left_layout.addStretch()
            main_split.addWidget(left)

            # Right: event rules + notification history
            right = QWidget()
            right_layout = QVBoxLayout(right)
            right_layout.setContentsMargins(0, 0, 0, 0)

            # Event routing table
            rules_group = QGroupBox("Event Routing")
            rules_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }"
            )
            rules_layout = QVBoxLayout(rules_group)

            self._rules_table = QTableWidget()
            self._rules_table.setColumnCount(5)
            self._rules_table.setHorizontalHeaderLabels(
                ["Event", "Priority", "In-App", "Telegram", "Sound"]
            )
            self._rules_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.Stretch
            )
            self._rules_table.setAlternatingRowColors(True)
            self._rules_table.verticalHeader().setVisible(False)
            rules_layout.addWidget(self._rules_table)
            right_layout.addWidget(rules_group, stretch=1)

            # Notification history
            history_group = QGroupBox("Notification History")
            history_group.setStyleSheet(
                "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
                "border-radius: 6px; color: #00ffcc; }"
            )
            history_layout = QVBoxLayout(history_group)

            ack_row = QHBoxLayout()
            ack_row.addStretch()
            self._btn_ack = QPushButton("Acknowledge All")
            self._btn_ack.setStyleSheet(
                "QPushButton { background: #1a1a3f; color: #ffaa00; "
                "border: 1px solid #ffaa00; border-radius: 4px; padding: 4px 10px; }"
            )
            self._btn_ack.clicked.connect(self._acknowledge_all)
            ack_row.addWidget(self._btn_ack)
            history_layout.addLayout(ack_row)

            self._history_table = QTableWidget()
            self._history_table.setColumnCount(5)
            self._history_table.setHorizontalHeaderLabels(
                ["Time", "Priority", "Title", "Message", "Channels"]
            )
            self._history_table.horizontalHeader().setSectionResizeMode(
                QHeaderView.Stretch
            )
            self._history_table.setAlternatingRowColors(True)
            self._history_table.setEditTriggers(QTableWidget.NoEditTriggers)
            self._history_table.verticalHeader().setVisible(False)
            history_layout.addWidget(self._history_table)
            right_layout.addWidget(history_group, stretch=1)

            main_split.addWidget(right)
            main_split.setSizes([350, 550])
            layout.addWidget(main_split)

        def _test_telegram(self):
            """Send a test message to Telegram."""
            if not self._notif:
                return
            token = self._tg_token.text().strip()
            chat_id = self._tg_chat.text().strip()
            if not token or not chat_id:
                self._tg_status.setText("Enter bot token and chat ID first")
                self._tg_status.setStyleSheet("color: #ff3366;")
                return

            self._notif.configure_telegram(token, chat_id)
            try:
                self._notif._send_telegram(
                    "Acervator",
                    "Test notification — Telegram is configured correctly!",
                    None,
                )
                self._tg_status.setText("Test sent successfully!")
                self._tg_status.setStyleSheet("color: #00ff88;")
            except Exception as e:
                self._tg_status.setText(f"Failed: {e}")
                self._tg_status.setStyleSheet("color: #ff3366;")

        def _save_config(self):
            """Save notification configuration."""
            if not self._notif:
                return

            token = self._tg_token.text().strip()
            chat_id = self._tg_chat.text().strip()
            if token and chat_id:
                self._notif.configure_telegram(token, chat_id)

            phone = self._sms_phone.text().strip()
            if phone:
                self._notif.configure_sms(phone)

            self._lbl_status.setText("Configuration saved!")

        def _acknowledge_all(self):
            """Acknowledge all notifications."""
            if self._notif:
                self._notif.acknowledge_all()
                self.refresh()

        def refresh(self, notification_manager=None):
            """Refresh alerts display."""
            nm = notification_manager or self._notif
            if not nm:
                return

            config = nm.get_config()

            # Status
            unread = nm.unacknowledged_count
            self._lbl_unread.setText(f"Unread: {unread}")
            if unread > 0:
                self._lbl_unread.setStyleSheet("color: #ffaa00; font-size: 12px;")
            else:
                self._lbl_unread.setStyleSheet("color: #888; font-size: 12px;")

            tg_ok = config.get("telegram_configured", False)
            sms_ok = config.get("sms_configured", False)
            parts = ["Notifications: Active"]
            if tg_ok:
                parts.append("TG: Connected")
            if sms_ok:
                parts.append("SMS: Connected")
            self._lbl_status.setText(" | ".join(parts))

            # Event routing table
            rules = config.get("rules", {})
            self._rules_table.setRowCount(len(rules))
            for row, (event, rule) in enumerate(rules.items()):
                channels = rule.get("channels", [])
                items = [
                    event.replace("_", " ").title(),
                    rule.get("priority", "medium"),
                    "Yes" if "IN_APP" in channels else "No",
                    "Yes" if "TELEGRAM" in channels else "No",
                    "Yes" if "SOUND" in channels else "No",
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col >= 2:
                        color = QColor("#00ff88") if text == "Yes" else QColor("#555")
                        item.setForeground(color)
                    self._rules_table.setItem(row, col, item)

            # Notification history
            history = nm.history
            recent = history[-100:]  # Last 100
            self._history_table.setRowCount(len(recent))
            for row, notif in enumerate(reversed(recent)):
                ts = time.strftime("%H:%M:%S", time.localtime(notif.timestamp))
                items = [
                    ts,
                    notif.priority.value,
                    notif.title,
                    notif.message[:60],
                    ", ".join(notif.channels_sent),
                ]
                for col, text in enumerate(items):
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col == 1:
                        pcolors = {
                            "low": "#888",
                            "medium": "#00aaff",
                            "high": "#ffaa00",
                            "critical": "#ff3366",
                        }
                        item.setForeground(QColor(pcolors.get(text, "#888")))
                    if not notif.acknowledged:
                        item.setForeground(QColor("#e0e0f0"))
                    self._history_table.setItem(row, col, item)
