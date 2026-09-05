"""Progress dialog for ``BotManager.start_all``.

``StartAllProgressDialog`` subscribes to ``bot_manager.start_all_progress``
and re-emits each event on ``_progress_signal`` for the GUI thread.
``_handle_progress_main_thread`` answers the phases begin, bot_starting,
bot_started, bot_timeout, done and cancelled. ``_on_cancel`` calls
``cancel_start_all``.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6 import QtCore, QtWidgets
from . import design_system as ds

logger = logging.getLogger("acervator.gui.start_all")


class StartAllProgressDialog(QtWidgets.QDialog):
    """Progress dialog for BotManager.start_all() staggered runs."""

    def __init__(self, bot_manager, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Start All Progress Dialog")
        self._bot_manager = bot_manager
        self.setWindowTitle("Auto-starting bots")
        self.setModal(False)  # operator can keep using the rest of the GUI
        self.setMinimumWidth(420)
        self.resize(520, 360)
        self.setStyleSheet(
            f"QDialog {{ background: {ds.MAIN_TOOLBAR_SURFACE}; color: {ds.TEXT_CONSOLE}; }}"
            f"QLabel {{ color: {ds.TEXT_CONSOLE}; font-family: Consolas; font-size: 11px; }}"
            f"QListWidget {{ background: {ds.SURFACE_CHART}; color: {ds.TEXT_CONSOLE}; "
            f"border: 1px solid {ds.MAIN_SEPARATOR}; font-family: Consolas; font-size: 10px; }}"
            f"QPushButton {{ background: {ds.MAIN_BUTTON_SURFACE}; color: {ds.TEXT_CONSOLE}; "
            f"border: 1px solid {ds.MAIN_BUTTON_BORDER}; padding: 6px 18px; "
            "font-family: Consolas; font-size: 10px; }"
            f"QPushButton:hover {{ background: {ds.MAIN_BUTTON_HOVER}; }}"
            f"QPushButton:disabled {{ color: {ds.TEXT_PLACEHOLDER}; "
            f"border-color: {ds.MAIN_SEPARATOR}; }}"
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self._headline = QtWidgets.QLabel("Preparing to auto-start bots...")
        f = self._headline.font()
        f.setPointSize(12)
        f.setBold(True)
        self._headline.setFont(f)
        layout.addWidget(self._headline)

        self._subline = QtWidgets.QLabel(
            "Bots are started one at a time with a ~2.5-second pause "
            "between each (verify-then-next + a 2s minimum gap so the "
            "per-exchange CCXT call queue has time to drain). Click "
            "Cancel to abort the remaining bots — bots already started "
            "will keep running."
        )
        self._subline.setWordWrap(True)
        self._subline.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL};")
        layout.addWidget(self._subline)

        self._list = QtWidgets.QListWidget()
        layout.addWidget(self._list, 1)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(1)

        self._cancel_btn = QtWidgets.QPushButton("Cancel remaining")
        self._cancel_btn.clicked.connect(self._on_cancel)
        button_row.addWidget(self._cancel_btn)

        self._close_btn = QtWidgets.QPushButton("Close")
        self._close_btn.setEnabled(False)
        self._close_btn.clicked.connect(self.accept)
        button_row.addWidget(self._close_btn)

        layout.addLayout(button_row)

        try:
            from src.core.event_bus import get_event_bus

            self._bus = get_event_bus()
            self._unsub = self._bus.subscribe(
                "bot_manager.start_all_progress", self._on_progress_event
            )
        except Exception as _sub_exc:
            logger.exception(
                "Start All progress subscribe failed, no progress will show: %s",
                _sub_exc,
            )
            self._bus = None
            self._unsub = None

        self._progress_signal.connect(self._handle_progress_main_thread)

    # Signal carries (phase, total, started, bot_id_or_empty)
    _progress_signal = QtCore.Signal(str, int, int, str)

    def _on_progress_event(self, event) -> None:
        """Read ``phase``, ``total``, ``started`` and ``bot_id`` off
        ``event.data``. Re-emits them on ``_progress_signal``."""
        # EventBus.emit puts its kwargs in Event.data; there is no payload field.
        try:
            data = event.data
            phase = data.get("phase", "")
            total = int(data.get("total", 0))
            started = int(data.get("started", 0))
            bot_id = str(data.get("bot_id", "") or "")
            self._progress_signal.emit(phase, total, started, bot_id)
        except (AttributeError, TypeError, ValueError) as _pe_exc:
            logger.exception(
                "Start All progress event dropped (%s): %s",
                type(_pe_exc).__name__,
                _pe_exc,
            )

    @QtCore.Slot(str, int, int, str)
    def _handle_progress_main_thread(
        self, phase: str, total: int, started: int, bot_id: str
    ) -> None:
        if phase == "begin":
            if total == 0:
                self._headline.setText("No bots to auto-start.")
                self._cancel_btn.setEnabled(False)
                self._close_btn.setEnabled(True)
                QtCore.QTimer.singleShot(800, self.accept)
                return
            self._headline.setText(f"Auto-starting {total} bots (0/{total} verified)")
            self._list.clear()
        elif phase == "bot_starting":
            self._headline.setText(
                f"Auto-starting {total} bots "
                f"({started}/{total} verified, starting {bot_id}...)"
            )
            if bot_id:
                self._list.addItem(f"⏳ {bot_id} (starting...)")
                self._list.scrollToBottom()
        elif phase == "bot_started":
            self._headline.setText(
                f"Auto-starting {total} bots ({started}/{total} verified)"
            )
            if bot_id:
                self._replace_last_matching(bot_id, f"✓ {bot_id}")
        elif phase == "bot_timeout":
            if bot_id:
                self._replace_last_matching(
                    bot_id, f"⚠ {bot_id} (start verify timed out — may still come up)"
                )
        elif phase == "done":
            self._headline.setText(f"Done — {total} bot(s) processed.")
            self._cancel_btn.setEnabled(False)
            self._close_btn.setEnabled(True)
            QtCore.QTimer.singleShot(2000, self.accept)
        elif phase == "cancelled":
            self._headline.setText(f"Cancelled — {started}/{total} bots had started.")
            self._cancel_btn.setEnabled(False)
            self._close_btn.setEnabled(True)

    def _replace_last_matching(self, bot_id: str, new_text: str) -> None:
        """Replace the newest ``_list`` item holding ``bot_id`` with
        ``new_text``. Appends ``new_text`` when no item matches."""
        for i in range(self._list.count() - 1, -1, -1):
            item = self._list.item(i)
            if item is None:
                continue
            if bot_id in item.text():
                item.setText(new_text)
                self._list.scrollToBottom()
                return
        self._list.addItem(new_text)
        self._list.scrollToBottom()

    def _on_cancel(self) -> None:
        try:
            self._bot_manager.cancel_start_all()
        except Exception as _c_exc:
            logger.exception("cancel_start_all failed: %s", _c_exc)
            self._headline.setText("Cancel FAILED — bots may still be starting")
            self._cancel_btn.setEnabled(False)
            return
        self._cancel_btn.setEnabled(False)
        self._headline.setText("Cancelling...")

    def closeEvent(self, event):
        """Call ``_unsub``, then hand ``event`` to ``QDialog.closeEvent``."""
        try:
            if self._unsub and callable(self._unsub):
                self._unsub()
        except Exception as _u_exc:
            logger.exception(
                "Start All progress unsubscribe failed, handler leaked: " "%s", _u_exc
            )
        super().closeEvent(event)
