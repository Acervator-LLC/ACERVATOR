"""Progress dialog for ``BotManager.start_all``.

``StartAllProgressDialog`` subscribes to ``start_all_progress_surface.TOPIC``
and re-emits each event on ``_progress_signal`` for the GUI thread.
``_handle_progress_main_thread`` answers the phases begin, bot_starting,
bot_started, bot_timeout, done and cancelled, and ``_on_cancel`` calls
``cancel_start_all``. Every word, colour, size and delay it paints is read
from ``start_all_progress_surface`` at the moment it paints it.
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6 import QtCore, QtWidgets

from .main_tabs import start_all_progress_surface as surface

logger = logging.getLogger(surface.LOGGER_NAME)


class StartAllProgressDialog(QtWidgets.QDialog):
    """Progress dialog for BotManager.start_all() staggered runs."""

    def __init__(self, bot_manager, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._bot_manager = bot_manager
        self._setup_ui()

        try:
            from src.core.event_bus import get_event_bus

            self._bus = get_event_bus()
            self._unsub = self._bus.subscribe(surface.TOPIC, self._on_progress_event)
        except Exception as _sub_exc:
            logger.exception(surface.SUBSCRIBE_FAILED_LOG, _sub_exc)
            self._bus = None
            self._unsub = None

        self._progress_signal.connect(self._handle_progress_main_thread)

    def _setup_ui(self) -> None:
        """Build the headline, the subline, the bot list and the two buttons."""
        self.setAccessibleName(surface.ACCESSIBLE_NAME)
        self.setWindowTitle(surface.WINDOW_TITLE)
        self.setModal(surface.MODAL)  # operator can keep using the rest of the GUI
        self.setMinimumWidth(surface.MINIMUM_WIDTH_PX)
        self.resize(*surface.SIZE_PX)
        self.setStyleSheet(surface.STYLE_SHEET)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(*surface.MARGINS_PX)
        layout.setSpacing(surface.SPACING_PX)

        self._headline = QtWidgets.QLabel(surface.HEADLINE_INITIAL_TEXT)
        f = self._headline.font()
        f.setPointSize(surface.HEADLINE_POINT_SIZE)
        f.setBold(surface.HEADLINE_BOLD)
        self._headline.setFont(f)
        layout.addWidget(self._headline)

        self._subline = QtWidgets.QLabel(surface.SUBLINE_TEXT)
        self._subline.setWordWrap(surface.SUBLINE_WORD_WRAP)
        self._subline.setStyleSheet(surface.SUBLINE_STYLE)
        layout.addWidget(self._subline)

        self._list = QtWidgets.QListWidget()
        layout.addWidget(self._list, surface.LIST_STRETCH)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addStretch(surface.BUTTON_ROW_LEADING_STRETCH)

        self._cancel_btn = QtWidgets.QPushButton(surface.CANCEL_TEXT)
        self._cancel_btn.setEnabled(surface.CANCEL_ENABLED_AT_START)
        self._cancel_btn.clicked.connect(self._on_cancel)
        button_row.addWidget(self._cancel_btn)

        self._close_btn = QtWidgets.QPushButton(surface.CLOSE_TEXT)
        self._close_btn.setEnabled(surface.CLOSE_ENABLED_AT_START)
        self._close_btn.clicked.connect(self.accept)
        button_row.addWidget(self._close_btn)

        layout.addLayout(button_row)

    # Signal carries (phase, total, started, bot_id)
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
            logger.exception(surface.EVENT_DROPPED_LOG, type(_pe_exc).__name__, _pe_exc)

    @QtCore.Slot(str, int, int, str)
    def _handle_progress_main_thread(
        self, phase: str, total: int, started: int, bot_id: str
    ) -> None:
        if phase == surface.BEGIN:
            if total == 0:
                self._headline.setText(surface.HEADLINE_NO_BOTS)
                self._cancel_btn.setEnabled(False)
                self._close_btn.setEnabled(True)
                QtCore.QTimer.singleShot(surface.NO_BOTS_CLOSE_DELAY_MS, self.accept)
                return
            self._headline.setText(surface.HEADLINE_BEGIN.format(total=total))
            self._list.clear()
        elif phase == surface.BOT_STARTING:
            self._headline.setText(
                surface.HEADLINE_BOT_STARTING.format(
                    total=total, started=started, bot_id=bot_id
                )
            )
            if bot_id:
                self._list.addItem(surface.ITEM_BOT_STARTING.format(bot_id=bot_id))
                self._list.scrollToBottom()
        elif phase == surface.BOT_STARTED:
            self._headline.setText(
                surface.HEADLINE_BOT_STARTED.format(total=total, started=started)
            )
            if bot_id:
                self._replace_last_matching(
                    bot_id, surface.ITEM_BOT_STARTED.format(bot_id=bot_id)
                )
        elif phase == surface.BOT_TIMEOUT:
            if bot_id:
                self._replace_last_matching(
                    bot_id, surface.ITEM_BOT_TIMEOUT.format(bot_id=bot_id)
                )
        elif phase == surface.DONE:
            self._headline.setText(surface.HEADLINE_DONE.format(total=total))
            self._cancel_btn.setEnabled(False)
            self._close_btn.setEnabled(True)
            QtCore.QTimer.singleShot(surface.DONE_CLOSE_DELAY_MS, self.accept)
        elif phase == surface.CANCELLED:
            self._headline.setText(
                surface.HEADLINE_CANCELLED.format(started=started, total=total)
            )
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
            logger.exception(surface.CANCEL_FAILED_LOG, _c_exc)
            self._headline.setText(surface.HEADLINE_CANCEL_FAILED)
            self._cancel_btn.setEnabled(False)
            return
        self._cancel_btn.setEnabled(False)
        self._headline.setText(surface.HEADLINE_CANCELLING)

    def closeEvent(self, event):
        """Call ``_unsub``, then hand ``event`` to ``QDialog.closeEvent``."""
        try:
            if self._unsub and callable(self._unsub):
                self._unsub()
        except Exception as _u_exc:
            logger.exception(surface.UNSUBSCRIBE_FAILED_LOG, _u_exc)
        super().closeEvent(event)
