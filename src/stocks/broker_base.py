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

#: The route one ``open_session`` call opened on, which ``session_mode``
#: answers. ``SESSION_MODE_NONE`` is a broker with no session open.
SESSION_MODE_PAPER = "paper"
SESSION_MODE_LIVE = "live"
SESSION_MODE_NONE = ""
SESSION_MODES = (SESSION_MODE_PAPER, SESSION_MODE_LIVE)

#: What each route reads as on the operator's screen, so he sees which one a
#: venue opened on before any order is sized.
SESSION_MODE_WORDS = {
    SESSION_MODE_PAPER: (
        "on the venue's PAPER route, where no order reaches a real market"
    ),
    SESSION_MODE_LIVE: (
        "on the venue's LIVE route, where a filled order moves real money"
    ),
    SESSION_MODE_NONE: "on no route this broker names",
}

#: Why ``open_session`` closed a session whose broker named no route for it.
NO_SESSION_MODE = (
    "the broker opened a session and names no route for it, so no order is sized"
)


def session_mode_words(mode: Any) -> str:
    """The sentence the operator's screen carries for one session route.

    ``SESSION_MODE_WORDS`` holds the three readings, and a route outside them
    reads as ``SESSION_MODE_NONE`` does.
    """
    return SESSION_MODE_WORDS.get(
        str(mode or ""), SESSION_MODE_WORDS[SESSION_MODE_NONE]
    )


def broker_paper_route(broker: Any) -> bool:
    """Whether ``broker`` — a ``BrokerBase`` class or one of its instances —
    publishes a paper route.

    ``MainWindow._open_broker_session`` reads this to pick the route it opens
    on, so a venue publishing no paper route opens a live session instead of
    being refused. A broker declaring nothing reads True, the paper route every
    broker before this one had.
    """
    return bool(getattr(broker, "HAS_PAPER_ROUTE", True))


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

    #: The sectors this broker route serves, read by
    #: ``alpaca_connector.broker_serves_sector`` with no instance built. An empty
    #: tuple narrows nothing, which is every sector the venue is offered for.
    SECTORS_SERVED: tuple = ()

    #: Whether this broker publishes a paper route, read by
    #: ``broker_paper_route`` with no instance built. A broker declaring False
    #: opens a live session, because the paper one does not exist.
    HAS_PAPER_ROUTE: bool = True

    #: The currency ``get_account``'s ``cash`` figure is denominated in, which
    #: ``BrokerExchange.get_balance`` answers that currency's balance from. A
    #: broker holding accounts in another currency names its own.
    CASH_CURRENCY: str = "USD"

    def __init__(self, broker_id: str):
        self.broker_id = broker_id
        self._connected = False
        self._scan_symbols: set[str] = set()
        self._history_callback: Any = None
        self._assets: list[dict] = []
        self._session_refusal = ""
        self._session_mode = SESSION_MODE_NONE

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def exchange_id(self) -> str:
        """``broker_id`` under the name every fleet site reads to tell one
        venue's connector from another's.

        ``BotManager.set_connector`` skips a bot whose ``config.exchange_id``
        differs from this, so a broker connector never reaches a crypto bot.
        """
        return self.broker_id

    @property
    def display_name(self) -> str:
        """``broker_id`` capitalised, the label the window writes to the log."""
        return self.broker_id.capitalize()

    @property
    def is_connected(self) -> bool:
        """``_connected`` under the name ``_live_connector`` reads."""
        return self._connected

    @property
    def session_refusal(self) -> str:
        """Why the last ``open_session`` call left this broker disconnected, and
        "" where a session opened or none was tried."""
        return self._session_refusal

    @property
    def session_mode(self) -> str:
        """The route this broker's open session runs on: ``SESSION_MODE_PAPER``,
        ``SESSION_MODE_LIVE``, or ``SESSION_MODE_NONE`` with no session open.

        ``MainWindow._connect_broker_for_bot`` writes it to the status log, so
        the operator reads which route a venue is on before an order is sized.
        """
        return self._session_mode if self._connected else SESSION_MODE_NONE

    @property
    def session_mode_words(self) -> str:
        """The sentence the operator's screen carries for ``session_mode``."""
        return session_mode_words(self.session_mode)

    @property
    def scan_symbols(self) -> set[str]:
        """Every symbol ``add_scan_symbol`` holds."""
        return set(self._scan_symbols)

    def add_scan_symbol(self, symbol: str) -> None:
        """Hold ``symbol`` in ``scan_symbols``; a broker runs no history scan
        thread, so nothing is started."""
        if symbol:
            self._scan_symbols.add(str(symbol))

    def remove_scan_symbol(self, symbol: str) -> None:
        """Drop ``symbol`` from ``scan_symbols``, and leave the set alone where
        it never held it.

        ``BotManager.unregister`` calls this on the connector it holds when the
        last bot naming a symbol goes, so a deleted bot's symbol stops being
        read.
        """
        self._scan_symbols.discard(str(symbol))

    def set_history_callback(self, callback: Any) -> None:
        """Hold ``callback`` for the trade history pane."""
        self._history_callback = callback

    def release(self) -> int:
        """Clear the scan set and the history callback, mark this broker
        disconnected, and answer how many scan symbols were cleared."""
        cleared = len(self._scan_symbols)
        self._scan_symbols.clear()
        self._history_callback = None
        self._connected = False
        logger.info(
            "Released %s connector — %d scan symbol(s) dropped",
            self.display_name,
            cleared,
        )
        return cleared

    def held_assets(self) -> list[dict]:
        """Every asset record this broker last read, which ``record_markets``
        writes to the recording."""
        return list(self._assets)

    @abstractmethod
    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Connect to broker. paper=True for paper trading."""
        del api_key, api_secret, paper
        raise NotImplementedError

    async def open_session(self, api_key: str, api_secret: str, paper: bool) -> bool:
        """Open this broker's session through ``connect``, record the route it
        opened on in ``session_mode``, and answer whether it opened, holding any
        refusal in ``session_refusal``.

        An empty ``api_key`` or ``api_secret`` calls ``connect`` on no broker, and
        a refusal ``connect`` wrote itself is kept word for word. A broker whose
        session opens and names no route is closed again with
        ``NO_SESSION_MODE``, so no order is sized on a route nobody can read.
        """
        self._session_refusal = ""
        self._session_mode = SESSION_MODE_NONE
        if not api_key or not api_secret:
            self._session_refusal = "no API key and secret are stored"
            return False
        opened = bool(await self.connect(api_key, api_secret, paper))
        if not opened:
            if not self._session_refusal:
                self._session_refusal = (
                    "the connect attempt failed; the cause is in system.log"
                )
            return False
        self._session_mode = SESSION_MODE_PAPER if paper else SESSION_MODE_LIVE
        if self.session_mode not in SESSION_MODES:
            self._session_refusal = NO_SESSION_MODE
            self._connected = False
            return False
        return True

    @abstractmethod
    async def list_assets(self, status: str = "active") -> list[dict]:
        """Every asset record this broker publishes for ``status``, held so
        ``held_assets`` answers them and ``record_markets`` can write them."""
        del status
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

    def asset_infos(self, assets: Iterable[Any]) -> list[AssetInfo]:
        """Every asset record of ``assets`` as an ``AssetInfo``, writing
        nothing.

        No broker is contacted, a record naming no symbol is skipped,
        ``record_markets`` writes what this builds, and
        ``BrokerExchange.get_markets`` answers it with the recording untouched.
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
        return built

    def record_markets(self, assets: Iterable[Any]) -> list[AssetInfo]:
        """Every asset record of ``assets`` as an ``AssetInfo``, recorded under
        ``broker_id`` so ``recorded_rules`` answers each market's rules.

        No broker is contacted, a record naming no symbol is skipped, an empty
        ``assets`` keeps the rows already recorded, and a failed write raises
        ``OSError``.
        """
        built = self.asset_infos(assets)
        if built:
            record_venue(self.broker_id, built)
        return built
