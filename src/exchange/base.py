"""Abstract exchange interface.

``ExchangeInterface`` declares the methods a connector class implements.
``Ticker``, ``OrderBook``, ``Order``, ``Trade``, ``Balance`` and ``AssetInfo``
are the records those methods return, and ``MarketRules`` carries the order
rules ``AssetInfo`` reports for one market.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import (
    Decimal,
    InvalidOperation,
    ROUND_CEILING,
    ROUND_FLOOR,
    ROUND_HALF_UP,
)
from enum import Enum
from typing import Optional

#: Seconds in one day, the grain ``MarketRules.days_to_expiry`` answers in and
#: the grain a venue's ``settlement_days`` is stated in.
SETTLEMENT_DAY_SECONDS = 86400.0


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


@dataclass(frozen=True)
class MarketRules:
    """The order rules a venue publishes for one market.

    ``None`` is a rule the venue did not publish, never a rule of zero, and
    ``read`` is False when no market record was obtained at all.
    """

    min_amount: Optional[float] = None  # base units
    min_cost: Optional[float] = None  # quote units
    amount_increment: Optional[float] = None  # base units a size steps by
    price_increment: Optional[float] = None  # quote units a price steps by
    quote_increment: Optional[float] = None  # quote units a cash amount steps by
    contract_size: Optional[float] = None  # base units one contract stands for
    session: Optional[str] = None  # the session name the venue publishes
    buy_size_shapes: Optional[frozenset] = None  # size shapes a buy may name
    sell_size_shapes: Optional[frozenset] = None  # size shapes a sell may name
    order_types: Optional[str] = None  # the order types the venue declares
    expiry_ms: Optional[float] = None  # epoch ms the venue closes the contract on
    settlement_days: Optional[float] = None  # days the venue takes to settle a sale
    read: bool = True

    @property
    def expires(self) -> bool:
        """True while ``expiry_ms`` is a finite positive epoch, and False for the
        None a venue publishing no expiry carries."""
        if self.expiry_ms is None:
            return False
        try:
            held = float(self.expiry_ms)
        except (TypeError, ValueError):
            return False
        return math.isfinite(held) and held > 0.0

    def days_to_expiry(self, moment_s: float) -> Optional[float]:
        """Days from ``moment_s`` to ``expiry_ms``, negative once it has passed.

        None while ``expires`` is False or ``moment_s`` is not a finite number.
        """
        held = self.expiry_ms
        if held is None or not self.expires:
            return None
        if type(moment_s) not in (int, float):
            return None
        moment = float(moment_s)
        if not math.isfinite(moment):
            return None
        return (float(held) / 1000.0 - moment) / SETTLEMENT_DAY_SECONDS

    def price_on_tick(self, price: float) -> Optional[float]:
        """``price`` moved to the nearest ``price_increment`` step, and None
        while the venue published no tick or ``price`` is not finite."""
        increment = self.price_increment
        if increment is None or not math.isfinite(increment) or increment <= 0.0:
            return None
        try:
            if not math.isfinite(price):
                return None
            step = Decimal(repr(increment))
            steps = (Decimal(repr(price)) / step).to_integral_value(
                rounding=ROUND_HALF_UP
            )
            return float(steps * step)
        except (ArithmeticError, InvalidOperation, TypeError, ValueError):
            return None

    @property
    def smallest_amount(self) -> Optional[float]:
        """The smallest amount the venue accepts: ``min_amount`` ceiled onto
        ``amount_increment``, whichever of the two it published alone, or None
        when it published neither."""
        increment = self.amount_increment
        stepped = increment is not None and math.isfinite(increment) and increment > 0.0
        if self.min_amount is None:
            return increment if stepped else None
        if not stepped:
            return self.min_amount
        try:
            step = Decimal(repr(increment))
            steps = (Decimal(repr(self.min_amount)) / step).to_integral_value(
                rounding=ROUND_CEILING
            )
            return float(steps * step)
        except (ArithmeticError, InvalidOperation, TypeError, ValueError):
            return self.min_amount

    def steps_below_minimum(self, amount: float) -> bool:
        """True when ``amount`` floored onto ``amount_increment`` falls under
        ``min_amount`` ceiled to the same step, and False when the venue
        published no minimum."""
        if self.min_amount is None:
            return False
        increment = self.amount_increment
        if increment is None or not math.isfinite(increment) or increment <= 0.0:
            return amount < self.min_amount
        try:
            step = Decimal(repr(increment))
            amount_steps = (Decimal(repr(amount)) / step).to_integral_value(
                rounding=ROUND_FLOOR
            )
            minimum_steps = (Decimal(repr(self.min_amount)) / step).to_integral_value(
                rounding=ROUND_CEILING
            )
        except (ArithmeticError, InvalidOperation, TypeError, ValueError):
            return amount < self.min_amount
        return amount_steps < minimum_steps


@dataclass
class AssetInfo:
    """Market metadata, as ``get_markets`` returns it."""

    symbol: str  # e.g. "BTC/USDT"
    base: str  # e.g. "BTC"
    quote: str  # e.g. "USDT"
    rules: MarketRules
    maker_fee: float
    taker_fee: float
    active: bool = True
    logo_url: str = ""


@dataclass
class SpotPosition:
    """One open spot position as the venue reports it.

    ``ExchangeInterface.get_spot_positions`` returns these keyed by ``asset``;
    ``cost_basis_usd``, ``avg_entry_price`` and ``unrealized_pnl_usd`` are the
    venue's own figures, never derived here.
    """

    asset: str
    cost_basis_usd: float
    avg_entry_price: float
    unrealized_pnl_usd: float
    balance: float = 0.0
    raw: dict = field(default_factory=dict)


class ExchangeInterface(ABC):
    """The contract a connector class implements.

    Every method is abstract except ``get_my_trades``, which raises
    ``NotImplementedError`` unless a subclass overrides it,
    ``get_spot_positions``, which returns None until a subclass overrides it,
    and ``await_bulk_read_slot``, which waits for nothing until a subclass
    overrides it.
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
        del api_key, api_secret, passphrase

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
        del symbol
        raise NotImplementedError

    @abstractmethod
    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """Return an ``OrderBook`` for ``symbol`` with ``limit`` levels a side."""
        del symbol, limit
        raise NotImplementedError

    @abstractmethod
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: Optional[int] = None,
    ) -> list[list[float]]:
        """Return rows ``[timestamp_ms, open, high, low, close, volume]``.

        ``timeframe`` names the candle interval, ``limit`` the row count, and
        ``since`` the epoch milliseconds the rows start at.
        """
        del symbol, timeframe, limit, since
        raise NotImplementedError

    @abstractmethod
    async def get_balances(self) -> dict[str, Balance]:
        """Return one ``Balance`` per currency the exchange reports."""

    @abstractmethod
    async def get_balance(self, currency: str) -> Balance:
        """Return the ``Balance`` for ``currency``.

        A currency the exchange does not report gives a zeroed ``Balance``
        with ``absent`` True.
        """
        del currency
        raise NotImplementedError

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
        del symbol, side, order_type, amount, price, client_order_id
        raise NotImplementedError

    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        """Cancel the order ``order_id`` and return it."""
        del order_id, symbol
        raise NotImplementedError

    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> Order:
        """Return the ``Order`` for ``order_id``."""
        del order_id, symbol
        raise NotImplementedError

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        """Return the ``OrderStatus.OPEN`` orders, narrowed by ``symbol``."""
        del symbol
        raise NotImplementedError

    async def get_my_trades(
        self, symbol: str, since: Optional[float] = None, limit: Optional[int] = None
    ) -> list:
        """Return the ``Trade`` fills for ``symbol``.

        ``since`` is a unix-seconds floor and ``limit`` caps the count; this
        body raises ``NotImplementedError`` until a subclass overrides it.
        """
        del symbol, since, limit
        raise NotImplementedError(
            f"{type(self).__name__} does not implement get_my_trades"
        )

    async def await_bulk_read_slot(self, budget_sec: float = 0.0) -> float:
        """Yield until this venue's call queue has room for a bulk read.

        A bulk reader such as ``fetch_all_history_chunked`` awaits this before
        each venue call so its run does not starve the venue's other readers.
        This body waits for nothing and answers 0.0; a connector that
        serialises its calls overrides it.
        """
        del budget_sec
        return 0.0

    async def get_spot_positions(self) -> Optional[dict[str, "SpotPosition"]]:
        """Return the venue's open spot positions keyed by asset, or None.

        None means the venue reports no position figures; this body returns
        None until a subclass overrides it.
        """
        return None

    @abstractmethod
    async def get_markets(self) -> list[AssetInfo]:
        """Return one ``AssetInfo`` per tradeable market."""

    @abstractmethod
    async def get_asset_logo_url(self, currency: str) -> str:
        """Return a logo URL for ``currency``, or an empty string."""
        del currency
        raise NotImplementedError
