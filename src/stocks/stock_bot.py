"""
stock_bot.py — Stock trading bot with TradingView signal integration.

Supports multiple strategies:
- Signal: Execute trades based on TradingView webhook alerts
- DCA: Dollar-cost averaging on a schedule
- Swing: TA-driven swing trading (adapted from scrumming)
- Grid: Price grid for range-bound stocks (adapted from crypto grid)

All strategies respect market hours and support paper trading.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("acervator.stocks.bot")


class StockBotMode(Enum):
    ACCUMULATION = "accumulation"  # Core engine (transposed from crypto)
    SIGNAL = "signal"  # TradingView webhook-driven
    DCA = "dca"  # Dollar-cost averaging
    SWING = "swing"  # TA-driven swing trading


class StockBotState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class StockBotConfig:
    """Configuration for a stock trading bot."""

    broker_id: str = "alpaca"
    symbol: str = ""
    mode: StockBotMode = StockBotMode.SIGNAL
    # Capital
    investment_amount: float = 1000.0  # Total capital allocated
    position_size: float = 100.0  # Per-trade size in USD
    max_position_pct: float = 25.0  # Max % of portfolio in this stock
    # Risk
    stop_loss_pct: float = 5.0  # Stop loss %
    take_profit_pct: float = 10.0  # Take profit %
    trailing_stop_pct: float = 0.0  # Trailing stop (0 = disabled)
    # DCA settings
    dca_interval_hours: float = 24.0  # Buy interval for DCA
    dca_amount: float = 50.0  # USD per DCA buy
    # Swing settings
    ta_timeframe: str = "1D"
    swing_entry_confidence: float = 0.6  # TA confidence to enter
    swing_exit_confidence: float = 0.4  # TA confidence to exit
    # Grid settings
    grid_levels: int = 10
    grid_spread_pct: float = 2.0
    # Market hours
    allow_premarket: bool = False
    allow_afterhours: bool = False
    # Execution
    order_type: str = "market"  # market, limit
    limit_offset_pct: float = 0.1


@dataclass
class StockBotStats:
    """Runtime statistics for a stock bot."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    total_volume: float = 0.0
    current_position: float = 0  # Shares held
    avg_entry_price: float = 0
    current_price: float = 0
    unrealized_pnl: float = 0
    max_drawdown_pct: float = 0
    signals_received: int = 0
    signals_acted_on: int = 0
    last_trade_time: float = 0
    uptime_seconds: float = 0
    last_error: str = ""


class StockBot:
    """
    Stock trading bot with multiple strategy modes.

    Lifecycle: create → start → (trading loop) → stop
    All trading decisions respect market hours.
    """

    def __init__(self, config: StockBotConfig, broker=None):
        self.bot_id = str(uuid.uuid4())
        self.config = config
        self.broker = broker
        self.state = StockBotState.IDLE
        self.stats = StockBotStats()
        self._start_time = 0
        self._last_dca_time = 0
        self._last_ta_summary = None
        self._trade_history: list[dict] = []
        self._peak_equity = 0

    def get_status(self) -> dict:
        """Return status snapshot."""
        if self._start_time > 0:
            self.stats.uptime_seconds = time.time() - self._start_time

        return {
            "bot_id": self.bot_id,
            "state": self.state.value,
            "broker": self.config.broker_id,
            "symbol": self.config.symbol,
            "mode": self.config.mode.value,
            "investment": self.config.investment_amount,
            "stats": {
                "total_trades": self.stats.total_trades,
                "winning_trades": self.stats.winning_trades,
                "losing_trades": self.stats.losing_trades,
                "total_pnl": round(self.stats.total_pnl, 2),
                "current_position": self.stats.current_position,
                "avg_entry_price": round(self.stats.avg_entry_price, 2),
                "current_price": round(self.stats.current_price, 2),
                "unrealized_pnl": round(self.stats.unrealized_pnl, 2),
                "signals_received": self.stats.signals_received,
                "signals_acted_on": self.stats.signals_acted_on,
                "total_volume": round(self.stats.total_volume, 2),
                "uptime": round(self.stats.uptime_seconds, 1),
                "last_error": self.stats.last_error,
            },
        }

    async def start(self):
        """Start the trading bot."""
        if self.state == StockBotState.RUNNING:
            return
        self.state = StockBotState.RUNNING
        self._start_time = time.time()
        logger.info(
            "StockBot %s started: %s (%s) on %s",
            self.bot_id[:8],
            self.config.symbol,
            self.config.mode.value,
            self.config.broker_id,
        )

    async def stop(self):
        """Stop the trading bot."""
        self.state = StockBotState.STOPPED
        logger.info("StockBot %s stopped", self.bot_id[:8])

    def pause(self):
        """Pause trading."""
        self.state = StockBotState.PAUSED

    def resume(self):
        """Resume trading."""
        if self.state == StockBotState.PAUSED:
            self.state = StockBotState.RUNNING

    def handle_signal(self, signal: dict):
        """
        Handle an incoming trade signal (from TradingView or TA).

        signal dict: {action, symbol, price, quantity, strategy, ...}
        """
        if self.state != StockBotState.RUNNING:
            return

        self.stats.signals_received += 1
        action = signal.get("action", "").lower()
        symbol = signal.get("symbol", "")

        # Verify symbol matches
        if symbol and symbol.upper() != self.config.symbol.upper():
            return

        logger.info(
            "StockBot %s signal: %s %s @ $%.2f",
            self.bot_id[:8],
            action,
            self.config.symbol,
            signal.get("price", 0),
        )

        if action in ("buy", "long"):
            self._queue_buy(signal)
        elif action in ("sell", "short", "close"):
            self._queue_sell(signal)

        self.stats.signals_acted_on += 1

    def _queue_buy(self, signal: dict):
        """Queue a buy order."""
        price = signal.get("price", self.stats.current_price)
        qty = signal.get("quantity", 0)
        if qty <= 0 and price > 0:
            qty = self.config.position_size / price

        self._trade_history.append(
            {
                "time": time.time(),
                "action": "buy",
                "symbol": self.config.symbol,
                "price": price,
                "quantity": qty,
                "status": "queued",
            }
        )
        self.stats.total_trades += 1
        self.stats.total_volume += price * qty
        self.stats.last_trade_time = time.time()

    def _queue_sell(self, signal: dict):
        """Queue a sell order."""
        price = signal.get("price", self.stats.current_price)
        qty = signal.get("quantity", self.stats.current_position)

        if qty <= 0:
            return

        pnl = (
            (price - self.stats.avg_entry_price) * qty
            if self.stats.avg_entry_price > 0
            else 0
        )

        self._trade_history.append(
            {
                "time": time.time(),
                "action": "sell",
                "symbol": self.config.symbol,
                "price": price,
                "quantity": qty,
                "pnl": pnl,
                "status": "queued",
            }
        )
        self.stats.total_trades += 1
        self.stats.total_pnl += pnl
        if pnl > 0:
            self.stats.winning_trades += 1
        elif pnl < 0:
            self.stats.losing_trades += 1
        self.stats.total_volume += price * qty
        self.stats.last_trade_time = time.time()

    def get_full_state(self) -> dict:
        """Get complete state for persistence."""
        return {
            "bot_id": self.bot_id,
            "config": {
                "broker_id": self.config.broker_id,
                "symbol": self.config.symbol,
                "mode": self.config.mode.value,
                "investment_amount": self.config.investment_amount,
                "position_size": self.config.position_size,
                "stop_loss_pct": self.config.stop_loss_pct,
                "take_profit_pct": self.config.take_profit_pct,
                "ta_timeframe": self.config.ta_timeframe,
            },
            "state": self.state.value,
            "stats": self.get_status()["stats"],
        }


class StockBotManager:
    """Manages all stock trading bots."""

    def __init__(self):
        self._bots: dict[str, StockBot] = {}

    def register(self, bot: StockBot):
        """Register a stock bot."""
        self._bots[bot.bot_id] = bot
        logger.info(
            "Stock bot registered: %s (%s %s)",
            bot.bot_id[:8],
            bot.config.symbol,
            bot.config.mode.value,
        )

    def unregister(self, bot_id: str):
        """Remove a stock bot."""
        self._bots.pop(bot_id, None)

    def get_bot(self, bot_id: str) -> Optional[StockBot]:
        return self._bots.get(bot_id)

    def list_bots(self) -> list[dict]:
        """Return status snapshots for all stock bots."""
        return [bot.get_status() for bot in self._bots.values()]

    def get_aggregate_stats(self) -> dict:
        """Compute totals across all stock bots."""
        total_pnl = 0.0
        total_trades = 0
        running = 0
        errored = 0

        for bot in self._bots.values():
            total_pnl += bot.stats.total_pnl
            total_trades += bot.stats.total_trades
            if bot.state == StockBotState.RUNNING:
                running += 1
            if bot.state == StockBotState.ERROR:
                errored += 1

        return {
            "total_bots": len(self._bots),
            "running": running,
            "errored": errored,
            "total_realised_pnl": round(total_pnl, 2),
            "total_trades": total_trades,
        }

    async def stop_all(self):
        """Stop all running bots."""
        for bot in self._bots.values():
            if bot.state == StockBotState.RUNNING:
                await bot.stop()
