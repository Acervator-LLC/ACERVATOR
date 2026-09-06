"""The modal that confirms a gated buy order.

``_BuyConfirmationBroker.request_confirmation`` files a request from a bot's
async context and waits for ``yes``, ``no``, ``skip`` or ``timeout``.
``_on_request_received`` raises the class ``variant_surface`` names for
``BUY_CONFIRMATION`` and resolves the waiting future with its answer.
``BuyConfirmationDialog`` reads every word, colour, size and figure it paints
from ``buy_confirmation_surface``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from .main_tabs import buy_confirmation_surface as surface

try:
    from PySide6.QtCore import Qt, QObject, Signal, Slot
    from PySide6.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QFrame,
    )
    from PySide6.QtGui import QFont

    _QT_AVAILABLE = True
except ImportError:  # pragma: no cover
    _QT_AVAILABLE = False

logger = logging.getLogger(surface.LOGGER_NAME)


_broker: Optional["_BuyConfirmationBroker"] = None


def get_broker() -> "_BuyConfirmationBroker":
    """Return the process-wide broker. Creates on first call."""
    global _broker
    if _broker is None:
        if not _QT_AVAILABLE:
            raise RuntimeError(surface.NO_QT_ERROR)
        _broker = _BuyConfirmationBroker()
    return _broker


def dialog_class() -> type:
    """The confirmation dialog class the running build variant draws."""
    from .variant_surface import BUY_CONFIRMATION, surface_class

    return surface_class(BUY_CONFIRMATION)


class _HeadlessBroker:
    """The broker a process with no Qt gets, which refuses every buy."""

    async def request_confirmation(self, **_request) -> str:
        """Log the refusal and answer ``surface.HEADLESS_ANSWER``."""
        return surface.headless_answer()


class _HeadlessDialog:
    """The dialog name a process with no Qt imports, which builds no window."""


_HEADLESS_NAMES: dict[str, type] = {
    "_BuyConfirmationBroker": _HeadlessBroker,
    "BuyConfirmationDialog": _HeadlessDialog,
}


def __getattr__(name: str) -> type:
    """Answer the stand-in for a name only the Qt block defines."""
    stand_in = _HEADLESS_NAMES.get(name)
    if stand_in is None:
        raise AttributeError(name)
    return stand_in


if _QT_AVAILABLE:

    class _BuyConfirmationBroker(QObject):
        """Carries one buy confirmation between a bot task and the GUI thread.

        ``request_confirmation`` emits ``_request_signal`` and awaits the
        future ``_on_request_received`` resolves on the bot's own loop.
        """

        _request_signal = Signal(str, object)

        def __init__(self, parent=None):
            QObject.__init__(self, parent)
            self._pending: dict[str, dict] = {}
            self._request_signal.connect(self._on_request_received, Qt.AutoConnection)

        async def request_confirmation(
            self,
            *,
            bot_id: str,
            symbol: str,
            reason: str,
            cost_usd: float,
            price: float,
            amount_asset: float,
            holdings_before: float,
            target_balance: float,
            timeout_sec: float = surface.TIMEOUT_SEC,
        ) -> str:
            """Await the operator's answer to one buy, or refuse on timeout.

            Returns ``yes`` to proceed, ``no`` to refuse this buy, ``skip``
            to refuse the tick, and ``timeout`` when nobody answered.
            """
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()

            key = surface.request_id(bot_id, surface.millis_of(loop.time()))
            payload = {
                "request_id": key,
                "bot_id": bot_id,
                "symbol": symbol,
                "reason": reason,
                "cost_usd": cost_usd,
                "price": price,
                "amount_asset": amount_asset,
                "holdings_before": holdings_before,
                "target_balance": target_balance,
                "loop": loop,
                "future": fut,
            }
            self._pending[key] = payload
            self._request_signal.emit(key, payload)

            try:
                result = await asyncio.wait_for(fut, timeout=timeout_sec)
                return result
            except asyncio.TimeoutError:
                self._pending.pop(key, None)
                logger.warning(surface.TIMEOUT_LOG, timeout_sec, bot_id)
                return surface.ANSWER_TIMEOUT

        @Slot(str, object)
        def _on_request_received(self, request_id: str, payload: dict):
            """Raise the modal on the GUI thread and resolve the bot's future."""
            dlg = dialog_class()(
                symbol=payload["symbol"],
                reason=payload["reason"],
                cost_usd=payload["cost_usd"],
                price=payload["price"],
                amount_asset=payload["amount_asset"],
                holdings_before=payload["holdings_before"],
                target_balance=payload["target_balance"],
            )
            dlg.setWindowFlag(Qt.WindowStaysOnTopHint, surface.STAYS_ON_TOP)
            dlg.raise_()
            dlg.activateWindow()

            result = dlg.exec()
            if result == QDialog.Accepted:
                answer = dlg.result_value
            else:
                answer = surface.CLOSED_ANSWER

            loop = payload["loop"]
            fut = payload["future"]
            if not fut.done():
                loop.call_soon_threadsafe(fut.set_result, answer)
            self._pending.pop(request_id, None)

    class BuyConfirmationDialog(QDialog):
        """The modal itself: a banner, seven detail rows and three answers.

        ``result_value`` opens at ``surface.DEFAULT_ANSWER`` and ``_answer``
        replaces it with the answer of the button that was pressed.
        """

        def __init__(
            self,
            *,
            symbol: str,
            reason: str,
            cost_usd: float,
            price: float,
            amount_asset: float,
            holdings_before: float,
            target_balance: float,
            parent=None,
        ):
            super().__init__(parent)
            self._symbol = symbol
            self._reason = reason
            self._cost_usd = cost_usd
            self._price = price
            self._amount_asset = amount_asset
            self._holdings_before = holdings_before
            self._target_balance = target_balance
            self._setup_ui()

        def _setup_ui(self) -> None:
            """Build the banner, the separator, the detail block and the buttons."""
            self.setAccessibleName(surface.ACCESSIBLE_NAME)
            self.result_value = surface.DEFAULT_ANSWER
            self.setWindowTitle(surface.WINDOW_TITLE)
            self.setModal(surface.MODAL)
            self.setMinimumWidth(surface.MINIMUM_WIDTH_PX)

            layout = QVBoxLayout(self)

            reason_lbl = QLabel(self._reason)
            rf = QFont()
            rf.setBold(surface.REASON_BOLD)
            rf.setPointSize(surface.REASON_POINT_SIZE)
            reason_lbl.setFont(rf)
            reason_lbl.setStyleSheet(surface.REASON_STYLE)
            reason_lbl.setWordWrap(surface.REASON_WORD_WRAP)
            layout.addWidget(reason_lbl)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            layout.addWidget(sep)

            details = QLabel(
                surface.details_text(
                    self._symbol,
                    self._cost_usd,
                    self._price,
                    self._amount_asset,
                    self._holdings_before,
                    self._target_balance,
                )
            )
            details.setTextFormat(Qt.RichText)
            details.setStyleSheet(surface.DETAILS_STYLE)
            layout.addWidget(details)

            btn_row = QHBoxLayout()
            btn_yes = QPushButton(surface.YES_TEXT)
            btn_no = QPushButton(surface.NO_TEXT)
            btn_skip = QPushButton(surface.SKIP_TEXT)
            btn_yes.setStyleSheet(surface.YES_STYLE)
            btn_no.setStyleSheet(surface.NO_STYLE)
            btn_skip.setStyleSheet(surface.SKIP_STYLE)
            btn_yes.clicked.connect(lambda: self._answer(surface.ANSWER_YES))
            btn_no.clicked.connect(lambda: self._answer(surface.ANSWER_NO))
            btn_skip.clicked.connect(lambda: self._answer(surface.ANSWER_SKIP))
            btn_row.addWidget(btn_yes)
            btn_row.addWidget(btn_no)
            btn_row.addWidget(btn_skip)
            layout.addLayout(btn_row)

        def _answer(self, value: str):
            """Keep ``value`` as the answer and accept the dialog."""
            self.result_value = value
            self.accept()
