"""
base.py — Abstract exchange interface
======================================
Defines the contract that every exchange connector must implement.
The trading engine interacts only with this interface, making it
trivial to add new exchanges or swap implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Data models shared by all exchange implementations
# ---------------------------------------------------------------------------
class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    # v3.23.28 — Immediate-or-Cancel limit. Behaves as a taker-forcing
    # limit: fills what's available immediately at limit-price or better,
    # cancels the rest. Used by Aggressive Trading mode (operator
    # directive 2026-07-25) to guarantee taker execution with a
    # slippage cap. Connectors that don't natively support IOC map to
    # LIMIT + timeInForce=IOC via extra params (see ccxt_connector).
    IOC_LIMIT = "ioc_limit"


class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    # v3.13.8 MEM-191 / Chunk 7 — CLOSED referenced by bot_container.py's
    # VolumeGuard path but was missing from the enum. Result: any guarded
    # order would AttributeError on construction. Latent production bug
    # until Chunk 7 harness exercised the trade path.
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Ticker:
    """Current price snapshot for a symbol."""
    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float
    timestamp: float


@dataclass
class OrderBook:
    """Top-of-book orderbook snapshot."""
    symbol: str
    bids: list[tuple[float, float]]   # [(price, amount), ...]
    asks: list[tuple[float, float]]
    timestamp: float


@dataclass
class Order:
    """Represents a placed or historical order."""
    id: str
    symbol: str
    side: OrderSide
    type: OrderType
    amount: float
    price: float
    filled: float = 0.0
    remaining: float = 0.0
    status: OrderStatus = OrderStatus.OPEN
    timestamp: float = 0.0
    fee: float = 0.0
    fee_currency: str = ""
    # v3.13.8 MEM-191 / Chunk 7 — avg fill price from exchange response.
    # Referenced by bot_container.py:239 (VolumeGuard path) and by
    # ScrummingBot's Chunk 6 slip-capture logic (_execute_buy /
    # _execute_sell extract order.average as the primary fill price).
    # Was missing from the dataclass — caught by Chunk 7 harness.
    average: float = 0.0
    raw: dict = field(default_factory=dict)  # Original exchange response


@dataclass
class Trade:
    """Historical trade record from the exchange.

    v3.16.46 — added for exchange-truth migration. Bot stats /
    SpendableWidget previously derived cost basis and realized P/L
    from internal accumulators that diverge from exchange reality.
    Fetching trade history from the exchange and aggregating it
    locally produces avg_entry and realized P/L that match the
    Coinbase Avg Entry / Returns numbers the operator sees.
    """
    id: str
    symbol: str           # e.g., "CHIP/USD"
    side: OrderSide       # BUY or SELL
    amount: float         # base asset units
    price: float          # quote per base
    fee: float = 0.0      # in fee_currency
    fee_currency: str = ""
    timestamp: float = 0.0  # unix seconds
    raw: dict = field(default_factory=dict)


@dataclass
class Balance:
    """Wallet balance for a single currency.

    The `absent` flag lets callers distinguish "exchange explicitly reported
    zero for this currency" from "exchange omitted this currency from the
    response entirely." Before this flag, ccxt_connector.get_balance
    fabricated Balance(free=0.0) for both cases, which hid a class of
    connector-response gaps from the handshake layer. Defense-in-depth
    alongside the MEM-259 VolumeGuard-disable fix for phantom-rebuy.
    """
    currency: str
    free: float
    used: float
    total: float
    absent: bool = False  # True iff the exchange response omitted this currency


@dataclass
class AssetInfo:
    """Metadata for a tradeable asset."""
    symbol: str             # e.g. "BTC/USDT"
    base: str               # e.g. "BTC"
    quote: str              # e.g. "USDT"
    min_amount: float       # Minimum order size
    min_cost: float         # Minimum order cost (in quote)
    price_precision: int    # Decimal places for price
    amount_precision: int   # Decimal places for amount
    maker_fee: float
    taker_fee: float
    active: bool = True
    logo_url: str = ""


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------
class ExchangeInterface(ABC):
    """
    Unified exchange API.  Every exchange connector (CCXT-based or custom)
    must implement these methods.
    """

    @property
    @abstractmethod
    def exchange_id(self) -> str:
        """Short identifier, e.g. ``'binance'``, ``'kraken'``."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name, e.g. ``'Binance'``."""

    @abstractmethod
    async def connect(self, api_key: str, api_secret: str, passphrase: str = "") -> None:
        """Authenticate and establish a connection."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connections and clean up resources."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Whether the exchange session is active."""

    # -- Market data ----------------------------------------------------
    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """Fetch current price for *symbol*."""

    @abstractmethod
    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """Fetch orderbook for *symbol*."""

    @abstractmethod
    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> list[list[float]]:
        """Fetch OHLCV candles: [[timestamp, O, H, L, C, V], ...]."""

    # -- Account --------------------------------------------------------
    @abstractmethod
    async def get_balances(self) -> dict[str, Balance]:
        """Fetch all non-zero balances."""

    @abstractmethod
    async def get_balance(self, currency: str) -> Balance:
        """Fetch balance for a specific currency."""

    # -- Orders ---------------------------------------------------------
    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Order:
        """Place an order. *price* is required for LIMIT orders.

        ``client_order_id`` (added v3.15.98 / TD-004 closure) is the
        idempotency key. ``BotContainer.guarded_place_order`` derives
        a deterministic coid from the trade intent
        (symbol+side+amount+price+bot_id+purpose+session-nonce) so
        that a retry of the same intent within TTL reuses the same id
        and the exchange refuses the duplicate (Coinbase 409, Binance
        -2010), preventing double-fills from network-timeout retry
        storms. See src/exchange/idempotency.py for the full design.
        Implementations may ignore the id (paper/sim exchanges that
        synthesize fills locally) but MUST accept the kwarg.
        """

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        """Cancel an open order."""

    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> Order:
        """Fetch status of a specific order."""

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        """Fetch all open orders, optionally filtered by *symbol*."""

    # v3.16.46 — Trade history fetch for exchange-truth migration.
    # Used by cost-basis derivation (replacing ticker.last seeding) and
    # realized P/L computation (replacing internal accumulators).
    async def get_my_trades(self, symbol: str,
                             since: Optional[float] = None,
                             limit: Optional[int] = None) -> list:
        """Fetch historical trade fills for ``symbol``.

        Returns a list of ``Trade`` records ordered chronologically.
        Default implementation raises NotImplementedError; concrete
        connectors override (ccxt_connector implements via ccxt's
        fetch_my_trades).

        Args:
            symbol: market symbol (e.g., "CHIP/USD")
            since: optional unix-seconds timestamp; only return trades at
                or after this time. None = all available.
            limit: optional max number of trades to return.
                None = exchange default (typically 100-500).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement get_my_trades")

    # -- Asset discovery ------------------------------------------------
    @abstractmethod
    async def get_markets(self) -> list[AssetInfo]:
        """Return metadata for all tradeable markets."""

    @abstractmethod
    async def get_asset_logo_url(self, currency: str) -> str:
        """Return a URL for the asset's logo/icon."""
