"""
src/gui/start_all_progress_dialog.py — v3.16.7

Progress dialog for staggered bulk bot starts. Operator directive
2026-04-28: "need to stagger auto-start bots with a pop-up notice.
Tired of starting them one by one with each new build."

Behavior:
  - Modeless QDialog with a count "{started}/{total} bots started"
  - List of bots already started (live-updates as each comes online)
  - Cancel button (calls bot_manager.cancel_start_all())
  - Auto-closes when phase=='done' or phase=='cancelled'

The dialog subscribes to the event bus's
'bot_manager.start_all_progress' topic. The engine emits these
events from BotManager.start_all() with phase ∈
{begin, bot_started, done, cancelled}.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6 import QtCore, QtWidgets

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
            "QDialog { background: #14141e; color: #c0c0c0; }"
            "QLabel { color: #c0c0c0; font-family: Consolas; font-size: 11px; }"
            "QListWidget { background: #0a0a12; color: #c0c0c0; "
            "border: 1px solid #2a2a3a; font-family: Consolas; font-size: 10px; }"
            "QPushButton { background: #1a1a26; color: #c0c0c0; "
            "border: 1px solid #3a3a4a; padding: 6px 18px; "
            "font-family: Consolas; font-size: 10px; }"
            "QPushButton:hover { background: #22222e; }"
            "QPushButton:disabled { color: #555; border-color: #2a2a3a; }"
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
        self._subline.setStyleSheet("color: #888888;")
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

        # Subscribe to engine events
        try:
            from src.core.event_bus import get_event_bus

            self._bus = get_event_bus()
            self._unsub = self._bus.subscribe(
                "bot_manager.start_all_progress", self._on_progress_event
            )
        except Exception:
            self._bus = None
            self._unsub = None

        # Bridge cross-thread events to the GUI thread via Qt signal
        self._progress_signal.connect(self._handle_progress_main_thread)

    # Signal carries (phase, total, started, bot_id_or_empty)
    _progress_signal = QtCore.Signal(str, int, int, str)

    def _on_progress_event(self, event) -> None:
        """Subscriber callback. Runs on whatever thread emitted the event.
        Re-emit as a Qt signal so the actual UI update runs on the GUI thread."""
        # v3.24.21 — `event.payload` never existed. EventBus.emit builds
        # `Event(topic=topic, data=kwargs)` (event_bus.py:136), and
        # Event.__getattr__ raises AttributeError("Event has no data
        # field 'payload'") for anything not in `data`. Every one of the
        # six emits in BotManager.start_all passes its fields as kwargs,
        # so they land in `.data`.
        #
        # The bare `except Exception: pass` below swallowed that
        # AttributeError on every single event, so _progress_signal never
        # fired and _handle_progress_main_thread was unreachable. The
        # operator-visible symptom: Start All opens a dialog stuck on
        # "Preparing to auto-start bots..." with an empty list and a
        # disabled Close button for the entire staggered start, which
        # then never auto-dismisses.
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
                # Nothing to do — close immediately so the dialog
                # doesn't linger over an idle screen.
                self._headline.setText("No bots to auto-start.")
                self._cancel_btn.setEnabled(False)
                self._close_btn.setEnabled(True)
                QtCore.QTimer.singleShot(800, self.accept)
                return
            self._headline.setText(f"Auto-starting {total} bots (0/{total} verified)")
            self._list.clear()
        elif phase == "bot_starting":
            # v3.16.11 — show the bot is currently being verified
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
                # Replace the "starting..." line with a verified line
                self._replace_last_matching(bot_id, f"✓ {bot_id}")
        elif phase == "bot_timeout":
            # v3.16.11 — verify timeout; bot may still come up but we
            # moved on. Mark as a warning so operator can review.
            if bot_id:
                self._replace_last_matching(
                    bot_id, f"⚠ {bot_id} (start verify timed out — may still come up)"
                )
        elif phase == "done":
            self._headline.setText(f"Done — {total} bot(s) processed.")
            self._cancel_btn.setEnabled(False)
            self._close_btn.setEnabled(True)
            # Auto-dismiss after 2 seconds so it doesn't linger
            QtCore.QTimer.singleShot(2000, self.accept)
        elif phase == "cancelled":
            self._headline.setText(f"Cancelled — {started}/{total} bots had started.")
            self._cancel_btn.setEnabled(False)
            self._close_btn.setEnabled(True)

    def _replace_last_matching(self, bot_id: str, new_text: str) -> None:
        """Find the most-recent list item containing `bot_id` and replace
        its text with `new_text`. Used to flip 'starting...' → 'verified'."""
        for i in range(self._list.count() - 1, -1, -1):
            item = self._list.item(i)
            if item is None:
                continue
            if bot_id in item.text():
                item.setText(new_text)
                self._list.scrollToBottom()
                return
        # Not found — append a new line
        self._list.addItem(new_text)
        self._list.scrollToBottom()

    def _on_cancel(self) -> None:
        # v3.24.21 — was a bare swallow. If cancellation fails the UI
        # still says "Cancelling..." while bots keep starting, so the
        # operator is told the opposite of what is happening.
        try:
            self._bot_manager.cancel_start_all()
        except Exception as _c_exc:  # noqa: BLE001 - UI must still respond
            logger.exception("cancel_start_all failed: %s", _c_exc)
            self._headline.setText("Cancel FAILED — bots may still be starting")
            self._cancel_btn.setEnabled(False)
            return
        self._cancel_btn.setEnabled(False)
        self._headline.setText("Cancelling...")

    def closeEvent(self, event):
        """Unsubscribe on close to avoid leaking handlers."""
        # v3.24.21 — was a bare swallow. A failed unsubscribe leaks this
        # dialog's handler onto the bus for the process lifetime; the
        # next Start All then drives a destroyed widget.
        try:
            if self._unsub and callable(self._unsub):
                self._unsub()
        except Exception as _u_exc:  # noqa: BLE001 - close must proceed
            logger.exception(
                "Start All progress unsubscribe failed, handler leaked: " "%s", _u_exc
            )
        super().closeEvent(event)
