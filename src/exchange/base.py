"""Abstract exchange interface.

``ExchangeInterface`` declares the methods a connector class implements.
``Ticker``, ``OrderBook``, ``Order``, ``Trade``, ``Balance`` and ``AssetInfo``
are the records those methods return.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    # CCXTConnector sends IOC_LIMIT as a limit order with timeInForce=IOC.
    IOC_LIMIT = "ioc_limit"


class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    # guarded_place_order returns CLOSED for a VolumeGuard order that filled.
    CLOSED = "closed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class Ticker:
    """Price snapshot, as ``get_ticker`` returns it."""

    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float
    timestamp: float


@dataclass
class OrderBook:
    """Orderbook levels for ``symbol``."""

    symbol: str
    bids: list[tuple[float, float]]  # [(price, amount), ...]
    asks: list[tuple[float, float]]
    timestamp: float


@dataclass
class Order:
    """A placed or historical order, as ``place_order`` returns it."""

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
    # _execute_buy and _execute_sell read average first as the fill price.
    average: float = 0.0
    raw: dict = field(default_factory=dict)  # Original exchange response


@dataclass
class Trade:
    """Historical trade record from the exchange.

    ``ExchangeInterface.get_my_trades`` returns a list of these records.
    """

    id: str
    symbol: str  # e.g., "CHIP/USD"
    side: OrderSide
    amount: float  # base asset units
    price: float  # quote per base
    fee: float = 0.0  # in fee_currency
    fee_currency: str = ""
    timestamp: float = 0.0  # unix seconds
    raw: dict = field(default_factory=dict)


@dataclass
class Balance:
    """Wallet balance for a single currency.

    ``absent`` is True only when the exchange response omitted ``currency``,
    and False when the exchange reported it as zero.
    """

    currency: str
    free: float
    used: float
    total: float
    absent: bool = False


@dataclass
class AssetInfo:
    """Market metadata, as ``get_markets`` returns it."""

    symbol: str  # e.g. "BTC/USDT"
    base: str  # e.g. "BTC"
    quote: str  # e.g. "USDT"
    min_amount: float  # Minimum order size
    min_cost: float  # Minimum order cost (in quote)
    price_precision: int  # Decimal places for price
    amount_precision: int  # Decimal places for amount
    maker_fee: float
    taker_fee: float
    active: bool = True
    logo_url: str = ""


class ExchangeInterface(ABC):
    """The contract a connector class implements.

    Every method is abstract except ``get_my_trades``, which raises
    ``NotImplementedError`` unless a subclass overrides it.
    """

    @property
    @abstractmethod
    def exchange_id(self) -> str:
        """Short venue id, e.g. ``'binance'``, paired with ``display_name``."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Readable venue name for ``exchange_id``, e.g. ``'Binance'``."""

    @abstractmethod
    async def connect(
        self, api_key: str, api_secret: str, passphrase: str = ""
    ) -> None:
        """Open the exchange session and make ``is_connected`` True."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the exchange session and make ``is_connected`` False."""

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """True after ``connect`` and False after ``disconnect``."""

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """Return the current ``Ticker`` for ``symbol``."""

    @abstractmethod
    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """Return an ``OrderBook`` for ``symbol`` with ``limit`` levels a side."""

    @abstractmethod
    async def get_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 100
    ) -> list[list[float]]:
        """Return rows ``[timestamp_ms, open, high, low, close, volume]``.

        ``timeframe`` names the candle interval and ``limit`` the row count.
        """

    @abstractmethod
    async def get_balances(self) -> dict[str, Balance]:
        """Return one ``Balance`` per currency the exchange reports."""

    @abstractmethod
    async def get_balance(self, currency: str) -> Balance:
        """Return the ``Balance`` for ``currency``.

        A currency the exchange does not report gives a zeroed ``Balance``
        with ``absent`` True.
        """

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
        """Submit an order and return the resulting ``Order``.

        ``price`` is required for ``OrderType.LIMIT`` and ``OrderType.IOC_LIMIT``;
        an implementation may ignore ``client_order_id`` but must accept it.
        """

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        """Cancel the order ``order_id`` and return it."""

    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> Order:
        """Return the ``Order`` for ``order_id``."""

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        """Return the ``OrderStatus.OPEN`` orders, narrowed by ``symbol``."""

    async def get_my_trades(
        self, symbol: str, since: Optional[float] = None, limit: Optional[int] = None
    ) -> list:
        """Return the ``Trade`` fills for ``symbol``.

        ``since`` is a unix-seconds floor and ``limit`` caps the count; this
        body raises ``NotImplementedError`` until a subclass overrides it.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement get_my_trades"
        )

    @abstractmethod
    async def get_markets(self) -> list[AssetInfo]:
        """Return one ``AssetInfo`` per tradeable market."""

    @abstractmethod
    async def get_asset_logo_url(self, currency: str) -> str:
        """Return a logo URL for ``currency``, or an empty string."""
