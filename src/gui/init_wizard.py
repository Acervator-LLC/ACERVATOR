"""
init_wizard.py - First-run initialization wizard
"""

from __future__ import annotations

import logging

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QWizard,
        QWizardPage,
        QVBoxLayout,
        QLabel,
        QLineEdit,
        QComboBox,
        QCheckBox,
        QMessageBox,
        QPushButton,
        QHBoxLayout,
        QTextEdit,
    )
    from PySide6.QtCore import Qt

    _HAS_QT = True
except ImportError:
    _HAS_QT = False
from src.gui.qt_safe_events import safe_process_events  # v3.15.99 P4.1

if _HAS_QT:

    class InitWizard(QWizard):
        """
        First-run or version-upgrade setup wizard.

        Features:
          - Skip button on first page to bypass entire setup
          - Fresh Start checkbox on upgrades to clear old settings
          - Exchange selection with passphrase awareness
          - API credential entry with Test Connection
          - Passphrase field shown only for exchanges that need it
        """

        def __init__(self, is_upgrade: bool = False, parent=None):
            super().__init__(parent)
            self.setWindowTitle("Acervator - Setup")
            self.setMinimumSize(600, 450)
            self.setWizardStyle(QWizard.ModernStyle)
            self._skipped = False
            self._is_upgrade = is_upgrade

            # --- Page 1: Username + Skip ---
            page1 = QWizardPage()
            if is_upgrade:
                page1.setTitle("Acervator - New Version")
                page1.setSubTitle(
                    "A new version has been detected. You can reconfigure "
                    "your setup or skip to keep existing settings."
                )
            else:
                page1.setTitle("Welcome to Acervator")
                page1.setSubTitle(
                    "Set up your trading environment. You can skip this entirely."
                )
            p1_layout = QVBoxLayout(page1)

            p1_layout.addWidget(QLabel("Username:"))
            self._username = QLineEdit()
            self._username.setPlaceholderText("Enter your display name")
            self._username.setText("User")
            p1_layout.addWidget(self._username)

            if is_upgrade:
                self._fresh_start = QCheckBox(
                    "Start fresh (clear all previous settings and exchanges)"
                )
                self._fresh_start.setToolTip(
                    "Check this to remove all saved exchanges, credentials, and settings "
                    "from the previous version. Useful if you're seeing stale data."
                )
                p1_layout.addWidget(self._fresh_start)
            else:
                self._fresh_start = None

            p1_layout.addSpacing(20)

            skip_btn = QPushButton("Skip Setup")
            skip_btn.setToolTip(
                "Skip the setup wizard entirely. No exchanges will be configured."
            )
            skip_btn.clicked.connect(self._on_skip)
            skip_btn.setStyleSheet("color: #888; padding: 8px;")
            p1_layout.addWidget(skip_btn)

            # --- Page 2: Exchange ---
            page2 = QWizardPage()
            page2.setTitle("Select Your Exchange")
            page2.setSubTitle(
                "Choose your primary exchange. You can add more later in Settings."
            )
            p2_layout = QVBoxLayout(page2)
            p2_layout.addWidget(QLabel("Exchange:"))
            self._exchange_combo = QComboBox()
            from ..exchange.ccxt_connector import (
                SUPPORTED_EXCHANGES,
                PASSPHRASE_EXCHANGES,
            )

            self._passphrase_exchanges = PASSPHRASE_EXCHANGES
            for eid in sorted(SUPPORTED_EXCHANGES.keys()):
                label = eid.capitalize()
                if eid in PASSPHRASE_EXCHANGES:
                    label += " (requires passphrase)"
                self._exchange_combo.addItem(label, eid)
            p2_layout.addWidget(self._exchange_combo)

            # --- Page 3: API Keys ---
            page3 = QWizardPage()
            page3.setTitle("API Credentials")
            page3.setSubTitle(
                "Enter your API key and secret, or check Skip to add them later."
            )
            page3.setFinalPage(True)
            p3_layout = QVBoxLayout(page3)

            p3_layout.addWidget(QLabel("API Key:"))
            self._api_key = QLineEdit()
            self._api_key.setPlaceholderText(
                "API key or organizations/.../apiKeys/... (CDP)"
            )
            self._api_key.setEchoMode(QLineEdit.Password)
            p3_layout.addWidget(self._api_key)

            self._show_key = QCheckBox("Show credentials")
            self._show_key.toggled.connect(self._toggle_visibility)
            p3_layout.addWidget(self._show_key)

            p3_layout.addWidget(QLabel("API Secret:"))
            self._api_secret = QTextEdit()
            self._api_secret.setMaximumHeight(60)
            self._api_secret.setPlaceholderText(
                "API secret or EC private key (PEM with \\n is OK)"
            )
            self._api_secret.setToolTip(
                "For Coinbase CDP keys, paste the full PEM key.\n"
                "Literal \\n characters will be auto-converted."
            )
            p3_layout.addWidget(self._api_secret)

            # Passphrase
            self._passphrase_label = QLabel("API Passphrase:")
            p3_layout.addWidget(self._passphrase_label)
            self._passphrase = QLineEdit()
            self._passphrase.setPlaceholderText(
                "Passphrase you chose when creating the API key"
            )
            self._passphrase.setEchoMode(QLineEdit.Password)
            p3_layout.addWidget(self._passphrase)

            self._passphrase_hint = QLabel("This exchange requires an API passphrase.")
            self._passphrase_hint.setWordWrap(True)
            self._passphrase_hint.setProperty("muted", True)
            p3_layout.addWidget(self._passphrase_hint)

            self._skip_creds = QCheckBox("Skip - add credentials later in Settings")
            p3_layout.addWidget(self._skip_creds)

            # Test Connection
            self._test_btn = QPushButton("Test Connection")
            self._test_btn.clicked.connect(self._test_api)
            p3_layout.addWidget(self._test_btn)

            self._feedback = QLabel("")
            self._feedback.setWordWrap(True)
            p3_layout.addWidget(self._feedback)

            self._page3 = page3

            # Add pages
            self.addPage(page1)
            self.addPage(page2)
            self.addPage(page3)

            self.currentIdChanged.connect(self._on_page_changed)

        def _on_skip(self) -> None:
            """Skip the entire setup process."""
            self._skipped = True
            self.reject()

        def was_skipped(self) -> bool:
            return self._skipped

        def _toggle_visibility(self, show: bool) -> None:
            mode = QLineEdit.Normal if show else QLineEdit.Password
            self._api_key.setEchoMode(mode)
            self._passphrase.setEchoMode(mode)
            # QTextEdit doesn't have echo mode - use font color trick
            if show:
                self._api_secret.setStyleSheet("")
            else:
                self._api_secret.setStyleSheet(
                    "color: transparent; background-selection-color: transparent;"
                )

        def _on_page_changed(self, page_id: int) -> None:
            if page_id == 2:
                eid = self._exchange_combo.currentData()
                needs_pp = eid in self._passphrase_exchanges
                self._passphrase_label.setVisible(needs_pp)
                self._passphrase.setVisible(needs_pp)
                self._passphrase_hint.setVisible(needs_pp)
                self._feedback.setText("")

        def _test_api(self) -> None:
            eid = self._exchange_combo.currentData()
            key = self._api_key.text().strip()
            secret = self._api_secret.toPlainText().strip()
            passphrase = self._passphrase.text().strip()

            if not key or not secret:
                self._feedback.setText("Enter API key and secret first.")
                self._feedback.setStyleSheet("color: #ff3366;")
                return

            self._feedback.setText(f"Testing connection to {eid.capitalize()}...")
            self._feedback.setStyleSheet("color: #00aaff;")
            self._test_btn.setEnabled(False)
            from PySide6.QtWidgets import QApplication

            safe_process_events("legacy P4.1 site")

            try:
                from ..exchange.api_validator import validate_credentials

                result = validate_credentials(eid, key, secret, passphrase)
                if result.success:
                    self._feedback.setText(result.message)
                    self._feedback.setStyleSheet("color: #00ff88;")
                else:
                    self._feedback.setText(result.message)
                    self._feedback.setStyleSheet("color: #ff3366;")
            except Exception as exc:
                self._feedback.setText(f"Test failed: {exc}")
                self._feedback.setStyleSheet("color: #ff3366;")
            finally:
                self._test_btn.setEnabled(True)

        def validateCurrentPage(self) -> bool:
            page_id = self.currentId()
            if page_id == 0:
                name = self._username.text().strip()
                if not name:
                    QMessageBox.warning(
                        self, "Username Required", "Please enter a username."
                    )
                    return False
            return True

        def get_results(self) -> dict:
            skip = self._skip_creds.isChecked()
            return {
                "username": self._username.text().strip() or "User",
                "exchange_id": self._exchange_combo.currentData(),
                "api_key": "" if skip else self._api_key.text().strip(),
                "api_secret": "" if skip else self._api_secret.toPlainText().strip(),
                "passphrase": "" if skip else self._passphrase.text().strip(),
                "fresh_start": (
                    self._fresh_start.isChecked() if self._fresh_start else False
                ),
            }
