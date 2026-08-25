"""
usb_auth_widget.py — USB Hardware Key Management UI
=====================================================
Provides the GUI panel for:
  1. Detecting USB drives
  2. Exporting API credentials to a USB hardware key
  3. Verifying an exported key
  4. Enabling/disabling hardware mode per exchange
  5. Status indicator showing hardware key presence at startup
"""

from __future__ import annotations

import logging

import threading

from PySide6.QtCore import QTimer, Signal, QObject
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QGroupBox,
    QFrame,
    QMessageBox,
    QProgressBar,
    QScrollArea,
)

logger = logging.getLogger("acervator.gui.usb_auth")


# ---------------------------------------------------------------------------
# Colours (matches Acervator dark palette)
# ---------------------------------------------------------------------------
_C_BG = "#0A0A14"
_C_PANEL = "#0D0D20"
_C_BORDER = "#1a1a3f"
_C_CYAN = "#00CCAA"
_C_BLUE = "#4488FF"
_C_GOLD = "#FFB800"
_C_RED = "#FF4444"
_C_GREY = "#667799"
_C_TEXT = "#C8D8F0"
_C_LOCKED = "#FF6666"
_C_UNLOCKED = "#00FF88"


# ---------------------------------------------------------------------------
# Worker thread for async USB operations
# ---------------------------------------------------------------------------


class _USBWorker(QObject):
    """Runs USB scan / export / verify off the main thread."""

    scan_complete = Signal(list)  # list[USBVolume]
    export_complete = Signal(bool, str)
    verify_complete = Signal(bool, str)

    def scan(self):
        threading.Thread(
            target=self._do_scan, daemon=True, name="usb-auth-scan"
        ).start()

    def export(self, volume, vault, passphrase):
        threading.Thread(
            target=self._do_export,
            args=(volume, vault, passphrase),
            name="usb-auth-export",
            daemon=True,
        ).start()

    def _do_scan(self):
        try:
            from ..core.usb_auth import list_usb_volumes

            vols = list_usb_volumes()
        except Exception as e:
            vols = []
        self.scan_complete.emit(vols)

    def _do_export(self, volume, vault, passphrase):
        try:
            from ..core.usb_auth import export_credentials_to_usb

            ok, msg = export_credentials_to_usb(volume, vault, passphrase)
            self.export_complete.emit(ok, msg)
        except Exception as e:
            self.export_complete.emit(False, str(e))


# ---------------------------------------------------------------------------
# USB Status Indicator (compact, for toolbar/status bar)
# ---------------------------------------------------------------------------


class USBStatusIndicator(QWidget):
    """
    Compact LED-style USB key status indicator.
    Green = hardware key present and authenticated.
    Red   = hardware mode active but key not found.
    Grey  = hardware mode not active (software credentials).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = "inactive"  # "inactive" | "present" | "missing"
        self._exchange_label = ""
        self.setFixedSize(22, 22)
        self.setToolTip("USB Hardware Key: inactive")

    def set_state(self, state: str, label: str = ""):
        self._state = state
        self._exchange_label = label
        tips = {
            "inactive": "USB Hardware Key: software credentials",
            "present": f"USB Hardware Key: authenticated ({label})",
            "missing": f"USB Hardware Key: REQUIRED but not found ({label})",
        }
        self.setToolTip(tips.get(state, "USB Hardware Key"))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colours = {
            "inactive": QColor(_C_GREY),
            "present": QColor(_C_UNLOCKED),
            "missing": QColor(_C_LOCKED),
        }
        colour = colours.get(self._state, QColor(_C_GREY))
        p.setPen(QPen(colour.darker(150), 1))
        p.setBrush(QBrush(colour))
        p.drawEllipse(3, 3, 16, 16)


# ---------------------------------------------------------------------------
# Per-exchange hardware mode status row
# ---------------------------------------------------------------------------


class _ExchangeHWRow(QFrame):
    """One row in the exchange hardware-mode list."""

    mode_changed = Signal(str, bool)  # (exchange_id, hardware_mode)

    def __init__(
        self,
        exchange_id: str,
        display_name: str,
        hardware_mode: bool,
        volume_serial: str,
        parent=None,
    ):
        super().__init__(parent)
        self.setAccessibleName("Exchange H W Row")
        self.exchange_id = exchange_id
        self._hw_mode = hardware_mode
        self._serial = volume_serial

        self.setStyleSheet(f"""
            QFrame {{
                background: {_C_PANEL};
                border: 1px solid {_C_BORDER};
                border-radius: 4px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        # Exchange name
        self._name_lbl = QLabel(display_name or exchange_id.title())
        self._name_lbl.setStyleSheet(
            f"color: {_C_TEXT}; font-weight: bold; font-size: 12px;"
        )
        layout.addWidget(self._name_lbl)

        # Serial display
        self._serial_lbl = QLabel(
            f"Key: {volume_serial[:8]}..." if volume_serial else "No key assigned"
        )
        self._serial_lbl.setStyleSheet(f"color: {_C_GREY}; font-size: 10px;")
        layout.addWidget(self._serial_lbl)

        layout.addStretch()

        # Status LED
        self._led = USBStatusIndicator()
        self._led.set_state(
            "present"
            if hardware_mode and volume_serial
            else "missing" if hardware_mode else "inactive"
        )
        layout.addWidget(self._led)

        # Toggle button
        self._toggle_btn = QPushButton(
            "Hardware Mode: ON" if hardware_mode else "Hardware Mode: OFF"
        )
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(hardware_mode)
        self._toggle_btn.setFixedWidth(160)
        self._apply_toggle_style(hardware_mode)
        self._toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._toggle_btn)

    def _apply_toggle_style(self, on: bool):
        if on:
            self._toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(0, 204, 170, 40);
                    color: {_C_CYAN}; border: 1px solid {_C_CYAN};
                    border-radius: 4px; font-weight: bold; font-size: 10px;
                }}
            """)
        else:
            self._toggle_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(102, 119, 153, 20);
                    color: {_C_GREY}; border: 1px solid {_C_BORDER};
                    border-radius: 4px; font-size: 10px;
                }}
            """)

    def _on_toggle(self, checked: bool):
        if checked and not self._serial:
            QMessageBox.warning(
                self,
                "No Key Assigned",
                "Export credentials to a USB drive first to assign a hardware key.\n\n"
                "Use the 'Export to USB Key' section above.",
            )
            self._toggle_btn.setChecked(False)
            return
        self._hw_mode = checked
        self._toggle_btn.setText(
            "Hardware Mode: ON" if checked else "Hardware Mode: OFF"
        )
        self._apply_toggle_style(checked)
        self._led.set_state(
            "present"
            if checked and self._serial
            else "missing" if checked else "inactive"
        )
        self.mode_changed.emit(self.exchange_id, checked)

    def update_serial(self, serial: str):
        self._serial = serial
        self._serial_lbl.setText(
            f"Key: {serial[:8]}..." if serial else "No key assigned"
        )


# ---------------------------------------------------------------------------
# Main USB Auth Management Widget
# ---------------------------------------------------------------------------


class USBAuthWidget(QWidget):
    """
    Full USB hardware key management panel.
    Placed inside the Settings tab under a 'Hardware Key' section.
    """

    hardware_mode_changed = Signal(str, bool, str)
    # (exchange_id, hardware_mode, volume_serial)

    def __init__(self, settings_manager, vault=None, parent=None):
        super().__init__(parent)
        self.setAccessibleName("U S B Auth Widget")
        self._settings = settings_manager
        self._vault = vault
        self._usb_vols = []
        self._worker = _USBWorker()
        self._worker.scan_complete.connect(self._on_scan_complete)
        self._worker.export_complete.connect(self._on_export_complete)

        self._build_ui()

        # Auto-scan on open
        QTimer.singleShot(300, self._worker.scan)

    # ── Build UI ─────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ── Header ──────────────────────────────────────────────────────
        hdr = QLabel("🔐  USB Hardware Authentication Keys")
        hdr.setStyleSheet(f"color: {_C_CYAN}; font-size: 14px; font-weight: bold;")
        root.addWidget(hdr)

        desc = QLabel(
            "Convert a USB drive into a hardware authentication key. "
            "API credentials are encrypted with a key unique to your Acervator "
            "installation + the USB drive's serial number. "
            "Once exported, you can enable Hardware Mode per exchange — the app "
            "will then require the USB to be present to access those credentials."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {_C_GREY}; font-size: 10px;")
        root.addWidget(desc)

        # ── Export Section ───────────────────────────────────────────────
        export_group = QGroupBox("Export Credentials to USB Key")
        export_group.setStyleSheet(f"""
            QGroupBox {{
                color: {_C_TEXT}; font-weight: bold; font-size: 11px;
                border: 1px solid {_C_BORDER}; border-radius: 6px;
                margin-top: 8px; padding-top: 8px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; }}
        """)
        exp_layout = QVBoxLayout(export_group)

        # USB drive selector row
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("USB Drive:"))
        self._drive_combo = QComboBox()
        self._drive_combo.setMinimumWidth(240)
        self._drive_combo.setStyleSheet(f"""
            QComboBox {{
                background: {_C_BG}; color: {_C_TEXT};
                border: 1px solid {_C_BORDER}; border-radius: 4px;
                padding: 4px 8px;
            }}
        """)
        sel_row.addWidget(self._drive_combo)

        self._refresh_btn = QPushButton("🔄 Refresh")
        self._refresh_btn.setFixedWidth(90)
        self._refresh_btn.setStyleSheet(self._btn_style(_C_GREY))
        self._refresh_btn.clicked.connect(self._on_refresh)
        sel_row.addWidget(self._refresh_btn)
        sel_row.addStretch()
        exp_layout.addLayout(sel_row)

        # Drive info
        self._drive_info = QLabel("Select a drive and click Export.")
        self._drive_info.setStyleSheet(f"color: {_C_GREY}; font-size: 10px;")
        self._drive_combo.currentIndexChanged.connect(self._update_drive_info)
        exp_layout.addWidget(self._drive_info)

        # Export button + progress
        btn_row = QHBoxLayout()
        self._export_btn = QPushButton("🔑  Export API Keys to USB Key")
        self._export_btn.setStyleSheet(self._btn_style(_C_CYAN))
        self._export_btn.clicked.connect(self._on_export)
        btn_row.addWidget(self._export_btn)

        self._verify_btn = QPushButton("✓ Verify")
        self._verify_btn.setFixedWidth(90)
        self._verify_btn.setStyleSheet(self._btn_style(_C_BLUE))
        self._verify_btn.clicked.connect(self._on_verify)
        btn_row.addWidget(self._verify_btn)
        exp_layout.addLayout(btn_row)

        self._progress = QProgressBar()
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(f"""
            QProgressBar {{ background: {_C_BG}; border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background: {_C_CYAN}; }}
        """)
        exp_layout.addWidget(self._progress)

        self._export_status = QLabel("")
        self._export_status.setWordWrap(True)
        self._export_status.setStyleSheet(f"color: {_C_GREY}; font-size: 10px;")
        exp_layout.addWidget(self._export_status)

        root.addWidget(export_group)

        # ── Exchange Hardware Mode ───────────────────────────────────────
        mode_group = QGroupBox("Exchange Hardware Mode")
        mode_group.setStyleSheet(export_group.styleSheet())
        mode_layout = QVBoxLayout(mode_group)

        mode_desc = QLabel(
            "After exporting and verifying your USB key, enable Hardware Mode "
            "per exchange. The app will then refuse to use software credentials "
            "for that exchange — the USB drive must be present."
        )
        mode_desc.setWordWrap(True)
        mode_desc.setStyleSheet(f"color: {_C_GREY}; font-size: 10px;")
        mode_layout.addWidget(mode_desc)

        # Scroll area for exchange rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
        )
        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(4)
        scroll.setWidget(self._rows_container)
        mode_layout.addWidget(scroll)

        root.addWidget(mode_group)
        root.addStretch()

        self._rebuild_exchange_rows()

    # ── Exchange rows ─────────────────────────────────────────────────────

    def _rebuild_exchange_rows(self):
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        exchanges = self._settings._settings.exchanges if self._settings else []
        if not exchanges:
            lbl = QLabel(
                "No exchanges configured. Add exchanges in the API Keys settings."
            )
            lbl.setStyleSheet(f"color: {_C_GREY}; font-size: 10px;")
            self._rows_layout.addWidget(lbl)
            return

        for ex_dict in exchanges:
            row = _ExchangeHWRow(
                exchange_id=ex_dict.get("exchange_id", ""),
                display_name=ex_dict.get("display_name", ""),
                hardware_mode=ex_dict.get("hardware_mode", False),
                volume_serial=ex_dict.get("hw_volume_serial", ""),
            )
            row.mode_changed.connect(self._on_mode_changed)
            self._rows_layout.addWidget(row)

        self._rows_layout.addStretch()

    def _on_mode_changed(self, exchange_id: str, hw_mode: bool):
        # Persist to settings
        exchanges = self._settings._settings.exchanges
        for i, ex in enumerate(exchanges):
            if ex.get("exchange_id") == exchange_id:
                exchanges[i]["hardware_mode"] = hw_mode
                serial = exchanges[i].get("hw_volume_serial", "")
                self.hardware_mode_changed.emit(exchange_id, hw_mode, serial)
                break
        try:
            self._settings.save()
        except Exception as _sf_exc:  # noqa: BLE001
            logger.warning("USB auth widget refresh failed: %s", _sf_exc)

    # ── USB scan ──────────────────────────────────────────────────────────

    def _on_refresh(self):
        self._drive_combo.clear()
        self._drive_combo.addItem("Scanning...")
        self._refresh_btn.setEnabled(False)
        self._worker.scan()

    def _on_scan_complete(self, volumes: list):
        self._usb_vols = volumes
        self._drive_combo.clear()
        self._refresh_btn.setEnabled(True)

        if not volumes:
            self._drive_combo.addItem("No USB drives detected")
            self._export_btn.setEnabled(False)
        else:
            for vol in volumes:
                label = f"{vol.label} ({vol.size_gb:.1f} GB) — {vol.serial}"
                if vol.has_auth_file:
                    label += " ✓ Key present"
                self._drive_combo.addItem(label, userData=vol)
            self._export_btn.setEnabled(True)

        self._update_drive_info()

    def _update_drive_info(self):
        vol = self._selected_volume()
        if vol is None:
            self._drive_info.setText("No drive selected.")
            return
        parts = [
            f"Mount: {vol.mount_point}",
            f"Serial: {vol.serial}",
            f"Size: {vol.size_gb:.1f} GB",
        ]
        if vol.has_auth_file:
            parts.append(f"Auth file: present — {vol.auth_file}")
        else:
            parts.append("Auth file: not present")
        self._drive_info.setText("  |  ".join(parts))

    def _selected_volume(self):
        idx = self._drive_combo.currentIndex()
        if idx < 0 or not self._usb_vols:
            return None
        return self._drive_combo.currentData()

    # ── Export / Verify ───────────────────────────────────────────────────

    def _on_export(self):
        vol = self._selected_volume()
        if vol is None:
            QMessageBox.warning(self, "No Drive", "Select a USB drive first.")
            return
        if self._vault is None:
            QMessageBox.warning(
                self,
                "No Vault",
                "Credential vault not available. "
                "Please add exchange API keys in Settings first.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Export API Keys",
            f"This will encrypt ALL exchange API keys to:\n\n"
            f"  {vol.mount_point / '.acervator_auth'}\n\n"
            f"Drive:  {vol.label}\n"
            f"Serial: {vol.serial}\n\n"
            f"The encrypted file can only be read by this Acervator installation.\n"
            f"After export, enable Hardware Mode per exchange below.\n\n"
            f"Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._export_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._export_status.setText("Exporting and encrypting credentials...")
        self._export_status.setStyleSheet(f"color: {_C_GREY}; font-size: 10px;")
        self._worker.export(vol, self._vault, "")

    def _on_export_complete(self, success: bool, message: str):
        self._progress.setVisible(False)
        self._export_btn.setEnabled(True)
        self._export_status.setText(message)

        colour = _C_UNLOCKED if success else _C_RED
        self._export_status.setStyleSheet(f"color: {colour}; font-size: 10px;")

        if success:
            vol = self._selected_volume()
            if vol:
                # Save the serial to all exchanges that don't have one yet
                exchanges = self._settings._settings.exchanges
                for ex in exchanges:
                    if not ex.get("hw_volume_serial"):
                        ex["hw_volume_serial"] = vol.serial
                try:
                    self._settings.save()
                except Exception as _sf_exc:  # noqa: BLE001
                    logger.warning("USB auth widget refresh failed: %s", _sf_exc)
                self._rebuild_exchange_rows()
            QMessageBox.information(
                self,
                "Export Successful",
                f"{message}\n\nYou can now enable Hardware Mode for each exchange below.",
            )

    def _on_verify(self):
        vol = self._selected_volume()
        if vol is None:
            QMessageBox.warning(self, "No Drive", "Select a USB drive first.")
            return
        if not vol.has_auth_file:
            QMessageBox.warning(
                self,
                "No Auth File",
                f"No .acervator_auth file found on {vol.label}.\n"
                "Export credentials first.",
            )
            return

        from ..core.usb_auth import verify_auth_file

        ok = verify_auth_file(vol.auth_file, vol.serial)
        if ok:
            QMessageBox.information(
                self,
                "Verification Passed",
                f"✓ Auth file on {vol.label} decrypts successfully.\n"
                f"Serial: {vol.serial}\n"
                "This USB is a valid Acervator hardware key.",
            )
        else:
            QMessageBox.critical(
                self,
                "Verification Failed",
                f"✗ Auth file on {vol.label} could not be verified.\n"
                "It may be corrupted or from a different installation.\n"
                "Try re-exporting.",
            )

    # ── Helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _btn_style(colour: str) -> str:
        return f"""
            QPushButton {{
                background: rgba(0,0,0,0);
                color: {colour};
                border: 1px solid {colour};
                border-radius: 4px;
                padding: 5px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: rgba(255,255,255,8); }}
            QPushButton:disabled {{ color: #333355; border-color: #222244; }}
        """

    def set_vault(self, vault):
        """Inject credential vault after construction."""
        self._vault = vault

    def refresh_exchanges(self):
        """Called when exchange list changes externally."""
        self._rebuild_exchange_rows()
