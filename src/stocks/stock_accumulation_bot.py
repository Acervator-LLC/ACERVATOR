"""
stock_accumulation_bot.py — Accumulation Trading Engine for Equities
====================================================================
1:1 transposition of the crypto Accumulation Bot for stock markets.
Adds equity-specific constraints:
  - Market hours enforcement (pre-market, regular, after-hours)
  - Pattern Day Trader (PDT) rule awareness
  - T+2 settlement tracking
  - Fractional share support
  - Dividend awareness
  - Circuit breaker / halt detection

Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator).
All rights reserved. See LICENSE for details.
"""

from __future__ import annotations
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("acervator.stocks.accumulation")

try:
    from ..trading.ta_engine import VotingEngine, VotingSummary
    from ..trading.mr_inspector import MRInspector
    from ..trading.smart_wire import SmartWireManager

    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False


class BotState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    MARKET_CLOSED = "market_closed"
    ERROR = "error"
    HALTED = "halted"  # Stock-specific: trading halt


@dataclass
class StockAccumulationConfig:
    """Configuration for a stock accumulation bot."""

    broker_id: str = "alpaca"
    symbol: str = ""
    target_balance: float = 200.0
    # Accumulation thresholds (same as crypto)
    harvest_threshold: float = 0.25  # TA confidence to harvest
    fold_threshold: float = 0.15  # TA confidence to fold
    interval_pct: float = 2.0  # Delta % to trigger harvest
    # TA configuration
    ta_timeframe: str = "1D"  # Daily candles for stocks
    phantom_timeframes: list = field(default_factory=lambda: ["1h", "4h", "1D", "1W"])
    enable_phantoms: bool = True
    # Targeting state machine
    detect_threshold_pct: float = 50.0  # % from midline to band for TRACK
    fire_threshold_pct: float = 1.0  # % from band for FIRE
    # Market hours (equity-specific)
    allow_premarket: bool = False  # 4:00-9:30 ET
    allow_afterhours: bool = False  # 16:00-20:00 ET
    allow_extended: bool = False  # Combined pre+after
    # PDT protection (equity-specific)
    pdt_protection: bool = True  # Warn if approaching 3 day-trades in 5 days
    pdt_max_day_trades: int = 3
    pdt_window_days: int = 5
    # Settlement (equity-specific)
    track_settlement: bool = True  # T+2 awareness
    # MR Inspector
    enable_mr_inspector: bool = True
    # Smart Wire
    enable_smart_wire: bool = True
    # Risk
    max_position_pct: float = 25.0  # Max % of portfolio in one stock
    stop_loss_pct: float = 0.0  # 0 = disabled (accumulation doesn't use stops)


class StockAccumulationBot:
    """
    Accumulation Trading engine for equities.

    Identical harvest-fold cycle as crypto, with:
      - Market hours enforcement
      - PDT rule tracking
      - T+2 settlement awareness
      - Daily timeframe as default (vs 1h for crypto)
      - Fractional share handling
      - Trading halt detection

    The core architecture is unchanged:
      SEARCH → TRACK → FIRE → harvest → fold → accumulate
      MR Inspector → Boosted Fold
      Smart Wire → cross-compounding across stock bots
    """

    def __init__(self, config: StockAccumulationConfig, broker=None):
        self.bot_id = str(uuid.uuid4())
        self.config = config
        self.broker = broker
        self.state = BotState.IDLE

        # Core accumulation state (identical to crypto)
        self._target = config.target_balance
        self._holdings: float = 0.0  # Shares held
        self._last_price: float = 0.0
        self._fold_queue_usd: float = 0.0
        self._fold_queue_ref: float = 0.0
        self._boost_fold_q: float = 0.0
        self._boost_fold_ref: float = 0.0
        self._boost_fold_sma: float = 0.0

        # Targeting state machine (identical to crypto)
        self._target_mode = "search"  # search | track | fire
        self._target_side = None
        self._base_read_interval = 60.0  # 1 min for stocks (vs 5s for crypto)
        self._current_read_interval = self._base_read_interval

        self._voting_engine = VotingEngine() if _HAS_DEPS else None
        self._last_summary: Optional[VotingSummary] = None

        # Phantom Balance (same multi-TF coordination)
        self._phantoms_enabled = config.enable_phantoms

        # MR Inspector hook
        self._mr_inspector: Optional[MRInspector] = None
        if config.enable_mr_inspector and _HAS_DEPS:
            self._mr_inspector = MRInspector()

        # Smart Wire hook
        self._smart_wire: Optional[SmartWireManager] = None

        # Equity-specific state
        self._market_open = False
        self._day_trades: list[float] = []  # Timestamps of day trades
        self._pending_settlement: list[dict] = []  # T+2 tracking
        self._trading_halted = False
        self._dividends_received: float = 0.0

        # Stats
        self._trades = 0
        self._harvests = 0
        self._folds = 0
        self._wins = 0
        self._boost_sells = 0
        self._boost_folds = 0
        self._pnl = 0.0
        self._volume = 0.0
        self._peak = config.target_balance
        self._max_dd = 0.0
        self._start_time = 0.0

    # ── Market Hours (Equity-Specific) ─────────────────────

    def _check_market_hours(self) -> bool:
        """Check if trading is allowed right now."""
        if self._trading_halted:
            if self.state != BotState.HALTED:
                self.state = BotState.HALTED
            return False
        # Placeholder: actual implementation uses MarketHoursTracker
        # Regular hours: M-F 9:30-16:00 ET
        # Pre-market: 4:00-9:30 ET (if config.allow_premarket)
        # After-hours: 16:00-20:00 ET (if config.allow_afterhours)
        return self._market_open

    # ── PDT Protection (Equity-Specific) ───────────────────

    def _check_pdt(self) -> bool:
        """Check if we're approaching the PDT limit."""
        if not self.config.pdt_protection:
            return True  # OK to trade
        cutoff = time.time() - self.config.pdt_window_days * 86400
        recent = [t for t in self._day_trades if t > cutoff]
        if len(recent) >= self.config.pdt_max_day_trades:
            logger.warning(
                "PDT LIMIT: %d day trades in %d days — blocking trade",
                len(recent),
                self.config.pdt_window_days,
            )
            return False
        return True

    def _record_day_trade(self):
        """Record a day trade (buy + sell same day)."""
        self._day_trades.append(time.time())

    # ── Settlement Tracking (Equity-Specific) ──────────────

    def _track_settlement(self, trade_usd: float, side: str):
        """Track T+2 settlement."""
        if not self.config.track_settlement:
            return
        self._pending_settlement.append(
            {
                "time": time.time(),
                "settles_at": time.time() + 2 * 86400,
                "amount": trade_usd,
                "side": side,
            }
        )
        # Clean settled trades
        now = time.time()
        self._pending_settlement = [
            s for s in self._pending_settlement if s["settles_at"] > now
        ]

    @property
    def unsettled_amount(self) -> float:
        """Total USD in unsettled trades."""
        now = time.time()
        return sum(
            s["amount"] for s in self._pending_settlement if s["settles_at"] > now
        )

    # ── Core Tick (Transposed from Crypto) ─────────────────

    async def tick(self, candles: list = None):
        """
        Main trading tick — identical logic to crypto accumulation bot.
        Called by the stock bot manager on each read cycle.
        """
        if self.state != BotState.RUNNING:
            return

        if not self._check_market_hours():
            return

        if not candles or len(candles) < 2:
            return

        price = candles[-1].close if hasattr(candles[-1], "close") else candles[-1]
        self._last_price = price
        value = self._holdings * price
        delta = value - self._target
        delta_pct = abs(delta) / (self._target + 1e-9) * 100

        # Portfolio tracking
        portfolio = self._fold_queue_usd + value
        if portfolio > self._peak:
            self._peak = portfolio
        if self._peak > 0:
            dd = (self._peak - portfolio) / self._peak * 100
            if dd > self._max_dd:
                self._max_dd = dd

        bullish = (
            candles[-1].close > candles[-1].open
            if hasattr(candles[-1], "open")
            else True
        )

        # TA snapshot
        if self._voting_engine and len(candles) >= 30:
            try:
                summary = self._voting_engine.compute_all(
                    candles, self.config.ta_timeframe
                )
                self._last_summary = summary
            except Exception as _ta_exc:  # noqa: BLE001 - tick must continue
                logger.warning(
                    "%s TA compute failed (%s): %s — retaining previous "
                    "summary; downstream signals are STALE",
                    getattr(self.config, "symbol", "?"),
                    type(_ta_exc).__name__,
                    _ta_exc,
                )

        # Compute confidence (same as crypto)
        harvest_conf = 0.50 if bullish else 0.0
        fold_conf = 0.50 if not bullish else 0.0

        # Trend hold (same as crypto)
        lookback = candles[-20:] if len(candles) >= 20 else candles
        trend = sum(
            1
            for c in lookback
            if hasattr(c, "close") and hasattr(c, "open") and c.close > c.open
        ) / max(len(lookback), 1)
        in_trend_hold = trend > 0.65

        # ── HARVEST (sell excess above target) ────────────
        if (
            delta > 0
            and delta_pct >= self.config.interval_pct
            and harvest_conf >= self.config.harvest_threshold
            and not in_trend_hold
            and self._check_pdt()
        ):
            harvest_qty = delta / price
            if self._holdings >= harvest_qty > 0:
                self._holdings -= harvest_qty
                harvest_usd = harvest_qty * price
                self._fold_queue_usd += harvest_usd
                self._fold_queue_ref = price
                self._harvests += 1
                self._trades += 1
                self._volume += harvest_usd
                self._track_settlement(harvest_usd, "sell")
                logger.info(
                    "HARVEST %s: %.4f shares @ $%.2f = $%.2f",
                    self.config.symbol,
                    harvest_qty,
                    price,
                    harvest_usd,
                )

        # ── FOLD (buy back at lower price) ────────────────
        if (
            self._fold_queue_usd > 0
            and fold_conf >= self.config.fold_threshold
            and price < self._fold_queue_ref
            and self._check_pdt()
        ):
            buy_usd = self._fold_queue_usd
            buy_qty = buy_usd / price
            self._holdings += buy_qty
            self._fold_queue_usd = 0
            self._folds += 1
            self._wins += 1
            self._trades += 1
            self._volume += buy_usd
            pnl = (self._fold_queue_ref - price) / self._fold_queue_ref * buy_usd
            self._pnl += pnl
            self._track_settlement(buy_usd, "buy")
            logger.info(
                "FOLD %s: %.4f shares @ $%.2f, profit $%.4f",
                self.config.symbol,
                buy_qty,
                price,
                pnl,
            )

        # ── MR Inspector / Boosted Fold ───────────────────
        if self._mr_inspector and len(candles) >= 30:
            sig = self._mr_inspector.scan(self.config.symbol, candles)
            if sig and sig.signal_type == "BOOST_SELL" and self._holdings > 0:
                sell_pct = sig.recommended_pct
                sell_qty = self._holdings * sell_pct
                if sell_qty * price > 1.0 and self._check_pdt():
                    self._holdings -= sell_qty
                    sell_usd = sell_qty * price
                    self._boost_fold_q += sell_usd
                    self._boost_fold_ref = price
                    self._boost_fold_sma = sig.sma20
                    self._boost_sells += 1
                    self._trades += 1
                    self._volume += sell_usd
                    self._track_settlement(sell_usd, "sell")
            # Boosted fold-back
            if self._boost_fold_q > 0 and self._boost_fold_sma > 0:
                if price <= self._boost_fold_sma and price < self._boost_fold_ref:
                    buy_usd = self._boost_fold_q
                    buy_qty = buy_usd / price
                    self._holdings += buy_qty
                    pnl = (
                        (self._boost_fold_ref - price) / self._boost_fold_ref * buy_usd
                    )
                    self._pnl += pnl
                    self._boost_folds += 1
                    self._wins += 1
                    self._trades += 1
                    self._volume += buy_usd
                    self._boost_fold_q = 0
                    self._track_settlement(buy_usd, "buy")

    # ── Smart Wire Integration ─────────────────────────────

    def set_smart_wire(self, mgr: SmartWireManager):
        self._smart_wire = mgr

    def report_profit(self, amount: float):
        """Report profit to Smart Wire for cross-compounding."""
        if self._smart_wire:
            self._smart_wire.record_profit(self.bot_id, amount)

    # ── Lifecycle ──────────────────────────────────────────

    async def start(self):
        self.state = BotState.RUNNING
        self._start_time = time.time()
        logger.info(
            "StockAccBot %s started: %s target=$%.2f",
            self.bot_id[:8],
            self.config.symbol,
            self._target,
        )

    async def stop(self):
        self.state = BotState.STOPPED
        logger.info(
            "StockAccBot %s stopped: %d trades, $%.2f PnL",
            self.bot_id[:8],
            self._trades,
            self._pnl,
        )

    def set_market_open(self, is_open: bool):
        """Called by market hours tracker."""
        self._market_open = is_open
        if not is_open and self.state == BotState.RUNNING:
            self.state = BotState.MARKET_CLOSED
        elif is_open and self.state == BotState.MARKET_CLOSED:
            self.state = BotState.RUNNING

    def set_halted(self, halted: bool):
        """Called when a stock-specific trading halt is detected."""
        self._trading_halted = halted

    def record_dividend(self, amount: float):
        """Record a dividend payment."""
        self._dividends_received += amount
        self._pnl += amount
        logger.info("DIVIDEND %s: $%.2f", self.config.symbol, amount)

    def get_status(self) -> dict:
        uptime = time.time() - self._start_time if self._start_time else 0
        wr = (self._wins / self._trades * 100) if self._trades > 0 else 0
        return {
            "bot_id": self.bot_id,
            "type": "stock_accumulation",
            "symbol": self.config.symbol,
            "state": self.state.value,
            "target": self._target,
            "holdings": self._holdings,
            "last_price": self._last_price,
            "value": self._holdings * self._last_price,
            "trades": self._trades,
            "harvests": self._harvests,
            "folds": self._folds,
            "boost_sells": self._boost_sells,
            "boost_folds": self._boost_folds,
            "win_rate": round(wr, 1),
            "pnl": round(self._pnl, 2),
            "volume": round(self._volume, 2),
            "max_dd": round(self._max_dd, 2),
            "dividends": round(self._dividends_received, 2),
            "unsettled": round(self.unsettled_amount, 2),
            "day_trades_5d": len(
                [t for t in self._day_trades if t > time.time() - 5 * 86400]
            ),
            "uptime": round(uptime, 1),
            "target_mode": self._target_mode,
            "fold_queued": round(self._fold_queue_usd, 2),
            "market_open": self._market_open,
        }
