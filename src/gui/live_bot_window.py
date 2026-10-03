"""
LiteLiveBotWindow — minimal single-window GUI for running ScrummingBot live.

Operator-approved (Session 23): real-money first-class, no paper-exchange
default, no typed-confirmation modal. The operator accepts responsibility
for the safety posture. Standard exchange-level auth/rate-limit hygiene
is preserved via CCXTConnector.

Layout:
    ┌─────────────────────────────────────────────────────────────┐
    │ Exchange: [▼ coinbase] Symbol: [▼ BTC/USDT] Target: [200.00]│
    │ API Key: [•••••••] Secret: [•••••••]  [START] [STOP]        │
    ├─────────────────────────────────────────────────────────────┤
    │ Console                    │ API              │ Activity    │
    │ bot.log stream             │ exchange calls   │ BUY/SELL/   │
    │                            │ & responses      │ FOLD events │
    │                            │                  │             │
    └─────────────────────────────────────────────────────────────┘

This window reuses:
  - src/exchange/ccxt_connector.CCXTConnector     (live exchange I/O)
  - src/exchange/api_logger                       (API pane stream)
  - src/trading/bot_container.BotConfig           (config dataclass)
  - src/trading/scrumming_bot.ScrummingBot        (actual engine)
  - src/core/event_bus.get_event_bus              (log/trade streams)

No new engine code. No paper-exchange mode. No feature flags. One window.
"""

from __future__ import annotations

import logging

import asyncio
import threading
from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QPlainTextEdit,
    QGroupBox,
    QDoubleSpinBox,
    QMessageBox,
)

# Reuse existing infrastructure — no re-invention
from ..core.event_bus import get_event_bus
from ..exchange.ccxt_connector import CCXTConnector, SUPPORTED_EXCHANGES
from ..trading.bot_container import (
    BotMode,
    make_bot_config,
)
from ..trading.scrumming_bot import ScrummingBot

logger = logging.getLogger("acervator.gui.live_bot")


# --- Supported pairs (minimal curated list — operator can extend) ----------
# Structure: {base_currency: [target_assets...]}
# The UI renders Symbol as "TARGET/BASE" following CCXT convention.
DEFAULT_PAIRS = {
    "USD": ["BTC", "ETH", "SOL", "ADA", "AVAX", "DOT", "BONK", "PEPE", "WIF"],
    "USDT": ["BTC", "ETH", "SOL", "ADA", "AVAX", "DOT", "MATIC", "LINK"],
    "USDC": ["BTC", "ETH", "SOL"],
    "EUR": ["BTC", "ETH"],
}


class LiteLiveBotWindow(QMainWindow):
    """Single-window live bot runner — console + API + trading activity."""

    # Thread-safe signals for pushing log lines from the bus callbacks
    # back to the Qt main thread (the event bus runs in bot thread).
    _sig_console = Signal(str)
    _sig_api = Signal(str)
    _sig_activity = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAccessibleName("Lite Live Bot Window")
        self.setWindowTitle("Acervator — Lite Live Bot")
        self.resize(1400, 700)

        self._bus = get_event_bus()
        self._bot: Optional[ScrummingBot] = None
        self._exchange: Optional[CCXTConnector] = None
        self._bot_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._unsubs: list = []

        self._build_ui()
        self._wire_signals()

    # ─── UI construction ───────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.addWidget(self._build_controls())
        root.addWidget(self._build_panes(), stretch=1)
        self.setCentralWidget(central)

    def _build_controls(self) -> QGroupBox:
        box = QGroupBox("Bot Configuration")
        g = QGridLayout(box)

        # Row 0: exchange + symbol selectors
        g.addWidget(QLabel("Exchange:"), 0, 0)
        self.cb_exchange = QComboBox()
        self.cb_exchange.addItems(sorted(SUPPORTED_EXCHANGES.keys()))
        self.cb_exchange.setCurrentText("coinbase")
        g.addWidget(self.cb_exchange, 0, 1)

        g.addWidget(QLabel("Base (quote):"), 0, 2)
        self.cb_base = QComboBox()
        self.cb_base.addItems(list(DEFAULT_PAIRS.keys()))
        self.cb_base.currentTextChanged.connect(self._on_base_changed)
        g.addWidget(self.cb_base, 0, 3)

        g.addWidget(QLabel("Target asset:"), 0, 4)
        self.cb_target = QComboBox()
        g.addWidget(self.cb_target, 0, 5)
        self._on_base_changed(self.cb_base.currentText())  # populate

        g.addWidget(QLabel("Target $:"), 0, 6)
        self.sp_target = QDoubleSpinBox()
        self.sp_target.setRange(1.0, 1_000_000.0)
        self.sp_target.setDecimals(2)
        self.sp_target.setValue(200.00)
        self.sp_target.setSingleStep(10.0)
        g.addWidget(self.sp_target, 0, 7)

        # Row 1: API credentials (echo mode = password)
        g.addWidget(QLabel("API key:"), 1, 0)
        self.ed_api_key = QLineEdit()
        self.ed_api_key.setEchoMode(QLineEdit.Password)
        g.addWidget(self.ed_api_key, 1, 1, 1, 3)

        g.addWidget(QLabel("Secret:"), 1, 4)
        self.ed_api_secret = QLineEdit()
        self.ed_api_secret.setEchoMode(QLineEdit.Password)
        g.addWidget(self.ed_api_secret, 1, 5, 1, 3)

        # Row 2: Start / Stop
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("START")
        self.btn_stop = QPushButton("STOP")
        self.btn_stop.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_stop.clicked.connect(self._on_stop)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        self.lbl_status = QLabel("Status: idle")
        btn_row.addWidget(self.lbl_status)

        container = QWidget()
        cv = QVBoxLayout(container)
        cv.addLayout(g)
        cv.addLayout(btn_row)
        wrapper = QGroupBox("Bot Configuration")
        wl = QVBoxLayout(wrapper)
        wl.addWidget(container)
        return wrapper

    def _build_panes(self) -> QWidget:
        """Three side-by-side monospace text panes."""
        row = QHBoxLayout()

        def _pane(title: str) -> tuple[QGroupBox, QPlainTextEdit]:
            g = QGroupBox(title)
            v = QVBoxLayout(g)
            edit = QPlainTextEdit()
            edit.setReadOnly(True)
            edit.setLineWrapMode(QPlainTextEdit.NoWrap)
            edit.setStyleSheet(
                "QPlainTextEdit { font-family: 'Menlo','Consolas',monospace; "
                "font-size: 11pt; background: #0e1420; color: #c8d4e3; }"
            )
            edit.setMaximumBlockCount(5000)  # cap buffer
            v.addWidget(edit)
            return g, edit

        console_box, self.txt_console = _pane("Console")
        api_box, self.txt_api = _pane("API")
        activity_box, self.txt_activity = _pane("Trading Activity")

        row.addWidget(console_box, 2)
        row.addWidget(api_box, 2)
        row.addWidget(activity_box, 1)

        wrapper = QWidget()
        wrapper.setLayout(row)
        return wrapper

    def _wire_signals(self) -> None:
        # Main-thread signals → pane append
        self._sig_console.connect(lambda s: self.txt_console.appendPlainText(s))
        self._sig_api.connect(lambda s: self.txt_api.appendPlainText(s))
        self._sig_activity.connect(lambda s: self.txt_activity.appendPlainText(s))

    def _on_base_changed(self, base: str) -> None:
        self.cb_target.clear()
        self.cb_target.addItems(DEFAULT_PAIRS.get(base, []))

    # ─── Event bus bridge (bot thread → GUI thread) ────────────────────

    def _on_bot_log(self, event) -> None:
        msg = event.data.get("message", "")
        self._sig_console.emit(msg)
        # Separate trade events to Activity pane too
        lower = msg.lower()
        if any(
            kw in lower
            for kw in (
                "buy ",
                "sell ",
                "fold ",
                "scrum ",
                "initial entry",
                "fire-window",
                "fold rebuy",
                "executed",
            )
        ):
            self._sig_activity.emit(msg)

    def _on_trade_filled(self, event) -> None:
        d = event.data
        side = d.get("side", "?")
        symbol = d.get("symbol", "?")
        amount = d.get("amount", 0.0)
        price = d.get("price", 0.0)
        self._sig_activity.emit(
            f"FILL: {side.upper()} {amount:.6f} {symbol} @ ${price:.8f}"
        )

    def _on_api_event(self, event) -> None:
        topic = event.topic
        self._sig_api.emit(f"[{topic}] {event.data}")

    # ─── Lifecycle ─────────────────────────────────────────────────────

    def _on_start(self) -> None:
        if self._bot is not None:
            self._sig_console.emit("Bot already running — STOP first")
            return

        exchange_id = self.cb_exchange.currentText()
        base = self.cb_base.currentText()
        target_asset = self.cb_target.currentText()
        if not target_asset:
            QMessageBox.warning(
                self, "Select pair", "Pick a target asset before starting."
            )
            return
        symbol = f"{target_asset}/{base}"
        target_dollars = float(self.sp_target.value())
        api_key = self.ed_api_key.text().strip()
        api_secret = self.ed_api_secret.text().strip()

        if not api_key or not api_secret:
            QMessageBox.warning(
                self,
                "API credentials required",
                "Both API key and secret are required for " "live trading.",
            )
            return

        # Subscribe to streams BEFORE starting bot so nothing is missed
        self._unsubs = [
            self._bus.subscribe("bot.log", self._on_bot_log),
            self._bus.subscribe("trade.filled", self._on_trade_filled),
            self._bus.subscribe("exchange.request", self._on_api_event),
            self._bus.subscribe("exchange.response", self._on_api_event),
        ]

        self._sig_console.emit(
            f"Starting: {exchange_id} {symbol} target=${target_dollars:.2f}"
        )

        # Run bot in a dedicated thread with its own asyncio loop
        self._bot_thread = threading.Thread(
            target=self._run_bot,
            args=(
                exchange_id,
                base,
                target_asset,
                symbol,
                target_dollars,
                api_key,
                api_secret,
            ),
            name="live-bot-window",
            daemon=True,
        )
        self._bot_thread.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.lbl_status.setText(f"Status: running {symbol}")

    def _run_bot(
        self,
        exchange_id: str,
        base: str,
        target_asset: str,
        symbol: str,
        target_dollars: float,
        api_key: str,
        api_secret: str,
    ) -> None:
        """Bot worker — runs on its own thread with its own event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        async def _main():
            # Connect to exchange
            self._exchange = CCXTConnector(exchange_id)
            try:
                await self._exchange.connect(api_key, api_secret)
            except Exception as e:
                self._sig_console.emit(f"CONNECT FAILED: {e}")
                return
            self._sig_console.emit(f"Connected to {exchange_id}")

            # make_bot_config raises on a kwarg that is foreign to the mode.
            cfg = make_bot_config(
                BotMode.SCRUMMING,
                exchange_id=exchange_id,
                base_currency=base,
                target_asset=target_asset,
                symbol=symbol,
                target_balance=target_dollars,
            )

            # Instantiate and start bot
            self._bot = ScrummingBot(cfg, self._exchange)
            try:
                await self._bot.start()
                # ScrummingBot.start() returns a coroutine — but bot runs
                # its internal loop. Keep this task alive until stop.
                while self._bot is not None and not self._bot._stop_event.is_set():
                    await asyncio.sleep(1.0)
            except Exception as e:
                self._sig_console.emit(f"BOT CRASHED: {e}")
            finally:
                if self._exchange:
                    try:
                        await self._exchange.disconnect()
                    except Exception as _sf_exc:  # noqa: BLE001
                        logger.warning(
                            "Lite Live Bot status refresh failed: %s", _sf_exc
                        )

        try:
            loop.run_until_complete(_main())
        finally:
            loop.close()

    def _on_stop(self) -> None:
        if self._bot is None:
            return
        self._sig_console.emit("Stopping bot (graceful shutdown)...")

        # Schedule stop on the bot's loop
        if self._loop is not None and self._loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self._bot.stop(), self._loop)
            try:
                fut.result(timeout=10)
            except Exception as e:
                self._sig_console.emit(f"STOP ERROR: {e}")

        # Tear down subscriptions
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception as exc:
                logger.warning(
                    "Lite Live Bot unsubscribe failed on stop: %s: %s",
                    type(exc).__name__,
                    exc,
                )
        self._unsubs = []

        self._bot = None
        self._exchange = None
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText("Status: idle")
        self._sig_console.emit("Stopped.")

    def closeEvent(self, ev) -> None:
        """Ensure bot is stopped before window closes."""
        if self._bot is not None:
            self._on_stop()
        super().closeEvent(ev)


def main() -> int:
    """Entry point — launch the lite window as a standalone app."""
    import sys

    app = QApplication(sys.argv)
    w = LiteLiveBotWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    import sys

    sys.exit(main())
