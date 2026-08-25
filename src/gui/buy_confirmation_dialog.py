"""
buy_confirmation_dialog.py — MEM-228 (Session 24, 2026-04-22)

Modal confirmation dialog for buy orders that meet operator-defined
risk criteria. Two trigger paths:
    1. Initial entry (bot thinks it holds zero)
    2. Any buy where (holdings × price + buy_cost) > target_balance × 1.01

Design contract:
- Bot's _execute_buy calls await request_buy_confirmation(...)
- That returns "yes" | "no" | "skip"  (or "timeout")
- Dialog runs on GUI main thread via Qt Signal (MEM-221 pattern)
- Bot thread awaits an asyncio.Future resolved by the button click
- 60s timeout: if operator doesn't answer, refuse the buy (bot retries next tick)

Organic target-balance growth from fold surplus is NOT gated — fold_rebuy
path skips the confirmation entirely. Hedge replenish is gated only if
its projected total would exceed target (structurally should not, but
belt-and-suspenders).

This module is pure UI plumbing. The gate decision (what paths prompt,
what the target ceiling is) lives in scrumming_bot.py._execute_buy.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

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

logger = logging.getLogger("acervator.buy_confirmation")


# Global broker: bot threads emit through this; GUI subscribes on init.
# Singleton-ish: one per process. Created lazily.
_broker: Optional["_BuyConfirmationBroker"] = None


def get_broker() -> "_BuyConfirmationBroker":
    """Return the process-wide broker. Creates on first call."""
    global _broker
    if _broker is None:
        if not _QT_AVAILABLE:
            raise RuntimeError(
                "PySide6 not available; buy confirmation dialog "
                "cannot be used in this environment."
            )
        _broker = _BuyConfirmationBroker()
    return _broker


if _QT_AVAILABLE:

    class _BuyConfirmationBroker(QObject):
        """
        Bridge between bot async tasks and the GUI main thread.

        Bot thread calls request_confirmation(...) from within an async
        context. That method:
          1. creates an asyncio.Future on the bot's event loop
          2. emits a Qt Signal carrying the request payload
          3. awaits the Future
          4. returns the resolved value ("yes"/"no"/"skip"/"timeout")

        GUI main thread receives the signal (Qt.AutoConnection queues
        it onto the main thread because the broker was constructed
        there), shows the modal, and resolves the Future via
        run_coroutine_threadsafe.
        """

        # Carries: (request_id, payload_dict) — payload has everything
        # the dialog needs to render plus the bot's event loop reference
        # so we can resolve the future back on that loop.
        _request_signal = Signal(str, object)

        def __init__(self, parent=None):
            QObject.__init__(self, parent)
            self._pending: dict[str, dict] = {}
            # Connect to our own slot with AutoConnection so cross-thread
            # emissions queue to the main thread.
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
            timeout_sec: float = 60.0,
        ) -> str:
            """
            Called from bot's async context. Blocks (awaits) until the
            operator answers or timeout expires. Returns one of:
              - "yes"     → proceed with buy
              - "no"      → refuse this buy
              - "skip"    → refuse this tick's cycle
              - "timeout" → no answer in `timeout_sec`; refuse to be safe
            """
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()

            request_id = f"{bot_id}_{int(asyncio.get_running_loop().time()*1000)}"
            payload = {
                "request_id": request_id,
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
            self._pending[request_id] = payload
            # Emit signal — will queue to GUI thread if different
            self._request_signal.emit(request_id, payload)

            try:
                result = await asyncio.wait_for(fut, timeout=timeout_sec)
                return result
            except asyncio.TimeoutError:
                # Clean up if dialog hasn't resolved
                self._pending.pop(request_id, None)
                logger.warning(
                    "Buy confirmation timed out after %ss for bot %s",
                    timeout_sec,
                    bot_id,
                )
                return "timeout"

        @Slot(str, object)
        def _on_request_received(self, request_id: str, payload: dict):
            """Runs on the GUI main thread. Show the modal."""
            dlg = BuyConfirmationDialog(
                symbol=payload["symbol"],
                reason=payload["reason"],
                cost_usd=payload["cost_usd"],
                price=payload["price"],
                amount_asset=payload["amount_asset"],
                holdings_before=payload["holdings_before"],
                target_balance=payload["target_balance"],
            )
            # Bring to front aggressively — this is a safety-critical prompt
            dlg.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            dlg.raise_()
            dlg.activateWindow()

            result = dlg.exec()
            if result == QDialog.Accepted:
                answer = dlg.result_value  # "yes" | "no" | "skip"
            else:
                answer = "no"  # close-button counts as No

            # Resolve the future on the bot's event loop
            loop = payload["loop"]
            fut = payload["future"]
            if not fut.done():
                loop.call_soon_threadsafe(fut.set_result, answer)
            self._pending.pop(request_id, None)

    class BuyConfirmationDialog(QDialog):
        """The modal itself. Shows buy details + three action buttons."""

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
            self.setAccessibleName("Buy Confirmation Dialog")
            self.result_value = "no"  # default if closed
            self.setWindowTitle("Confirm Buy Order")
            self.setModal(True)
            self.setMinimumWidth(420)

            layout = QVBoxLayout(self)

            # Reason banner — the alert line the operator reads first
            reason_lbl = QLabel(reason)
            rf = QFont()
            rf.setBold(True)
            rf.setPointSize(12)
            reason_lbl.setFont(rf)
            reason_lbl.setStyleSheet("color: #ffaa00; padding: 8px;")
            reason_lbl.setWordWrap(True)
            layout.addWidget(reason_lbl)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            layout.addWidget(sep)

            # Transaction details
            details = QLabel(
                f"<b>Symbol:</b>   {symbol}<br>"
                f"<b>Cost:</b>     ${cost_usd:.4f} USD<br>"
                f"<b>Price:</b>    ${price:.8f}<br>"
                f"<b>Amount:</b>   {amount_asset:.6f} "
                f"{symbol.split('/')[0]}<br>"
                f"<b>Current holdings:</b> {holdings_before:.6f} "
                f"(~${holdings_before * price:.4f})<br>"
                f"<b>Target balance:</b>   ${target_balance:.2f}<br>"
                f"<b>After this buy:</b>   "
                f"${(holdings_before * price) + cost_usd:.4f}"
            )
            details.setTextFormat(Qt.RichText)
            details.setStyleSheet("padding: 8px;")
            layout.addWidget(details)

            # Buttons
            btn_row = QHBoxLayout()
            btn_yes = QPushButton("Yes — place the buy")
            btn_no = QPushButton("No — refuse this buy")
            btn_skip = QPushButton("Skip this cycle")
            btn_yes.setStyleSheet(
                "padding: 8px 16px; background-color: #225522; "
                "color: white; font-weight: bold;"
            )
            btn_no.setStyleSheet(
                "padding: 8px 16px; background-color: #552222; "
                "color: white; font-weight: bold;"
            )
            btn_skip.setStyleSheet("padding: 8px 16px;")
            btn_yes.clicked.connect(lambda: self._answer("yes"))
            btn_no.clicked.connect(lambda: self._answer("no"))
            btn_skip.clicked.connect(lambda: self._answer("skip"))
            btn_row.addWidget(btn_yes)
            btn_row.addWidget(btn_no)
            btn_row.addWidget(btn_skip)
            layout.addLayout(btn_row)

        def _answer(self, value: str):
            self.result_value = value
            self.accept()

else:
    # Headless / no-Qt environments: stub so imports don't break.
    class _BuyConfirmationBroker:  # type: ignore[no-redef]
        async def request_confirmation(self, **kwargs) -> str:
            logger.warning(
                "Buy confirmation requested in headless environment; "
                "returning 'no' (safe default)."
            )
            return "no"

    class BuyConfirmationDialog:  # type: ignore[no-redef]
        pass
