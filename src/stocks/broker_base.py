"""
broker_base.py — Abstract base class for stock broker connectors.

Defines the interface that all broker implementations must follow.
Mirrors the crypto exchange base but adapted for equities.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Optional

from ..exchange.base import AssetInfo, MarketRules
from ..exchange.market_rules_store import record_venue

logger = logging.getLogger("acervator.stocks")


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class TimeInForce(Enum):
    DAY = "day"  # Cancel at market close
    GTC = "gtc"  # Good 'til cancelled
    IOC = "ioc"  # Immediate or cancel
    FOK = "fok"  # Fill or kill
    OPG = "opg"  # Market on open
    CLS = "cls"  # Market on close


class PositionSide(Enum):
    LONG = "long"
    SHORT = "short"


@dataclass
class StockOrder:
    """Represents a stock order."""

    order_id: str = ""
    symbol: str = ""
    side: OrderSide = OrderSide.BUY
    order_type: OrderType = OrderType.MARKET
    quantity: float = 0
    limit_price: float = 0
    stop_price: float = 0
    time_in_force: TimeInForce = TimeInForce.DAY
    status: str = "new"
    filled_qty: float = 0
    avg_fill_price: float = 0
    submitted_at: float = 0
    filled_at: float = 0


@dataclass
class StockPosition:
    """Current position in a stock."""

    symbol: str
    quantity: float  # Positive = long, negative = short
    avg_entry_price: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    side: PositionSide = PositionSide.LONG


@dataclass
class AccountInfo:
    """Broker account summary."""

    account_id: str = ""
    equity: float = 0
    cash: float = 0
    buying_power: float = 0
    portfolio_value: float = 0
    day_trade_count: int = 0
    pattern_day_trader: bool = False
    account_blocked: bool = False
    trading_blocked: bool = False


@dataclass
class StockQuote:
    """Real-time stock quote."""

    symbol: str
    bid: float = 0
    ask: float = 0
    last: float = 0
    volume: int = 0
    timestamp: float = 0
    prev_close: float = 0
    change_pct: float = 0


class BrokerBase(ABC):
    """Abstract broker interface for stock trading."""

    def __init__(self, broker_id: str):
        self.broker_id = broker_id
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    @abstractmethod
    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Connect to broker. paper=True for paper trading."""
        del api_key, api_secret, paper
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self):
        """Disconnect from broker."""
        ...

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Get account information."""
        ...

    @abstractmethod
    async def get_positions(self) -> list[StockPosition]:
        """Get all open positions."""
        ...

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[StockPosition]:
        """Get position for a specific symbol."""
        del symbol
        raise NotImplementedError

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        limit_price: float = 0,
        stop_price: float = 0,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> StockOrder:
        """Place an order."""
        del symbol, side, quantity, order_type
        del limit_price, stop_price, time_in_force
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        del order_id
        raise NotImplementedError

    @abstractmethod
    async def get_order(self, order_id: str) -> StockOrder:
        """Get order status."""
        del order_id
        raise NotImplementedError

    @abstractmethod
    async def get_open_orders(self) -> list[StockOrder]:
        """Get all open orders."""
        ...

    @abstractmethod
    async def get_quote(self, symbol: str) -> StockQuote:
        """Get real-time quote for a symbol."""
        del symbol
        raise NotImplementedError

    @abstractmethod
    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int = 100
    ) -> list[dict]:
        """Get OHLCV bars. timeframe: 1Min, 5Min, 15Min, 1H, 1D, 1W."""
        del symbol, timeframe, limit
        raise NotImplementedError

    @abstractmethod
    async def get_market_status(self) -> dict:
        """Get current market status (open/closed/pre/post)."""
        ...

    @abstractmethod
    def market_rules(self, asset: Any) -> MarketRules:
        """The ``MarketRules`` one of this broker's own asset records publishes.

        An unpublished rule is None, and ``read`` is False for a record this
        broker did not obtain.
        """
        del asset
        raise NotImplementedError

    def record_markets(self, assets: Iterable[Any]) -> list[AssetInfo]:
        """Every asset record of ``assets`` as an ``AssetInfo``, recorded under
        ``broker_id`` so ``recorded_rules`` answers each market's rules.

        Each record is read as handed in and no broker is contacted; a record
        naming no symbol is skipped.
        """
        built: list[AssetInfo] = []
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            symbol = str(asset.get("symbol") or "")
            if not symbol:
                continue
            base, _, quote = symbol.partition("/")
            built.append(
                AssetInfo(
                    symbol=symbol,
                    base=base,
                    quote=quote,
                    rules=self.market_rules(asset),
                    # An asset record publishes no fee, so AssetInfo carries zero.
                    maker_fee=0.0,
                    taker_fee=0.0,
                )
            )
        try:
            record_venue(self.broker_id, built)
        except OSError as exc:
            logger.warning("market rules for %s not recorded: %s", self.broker_id, exc)
        return built
