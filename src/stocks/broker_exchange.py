"""
broker_exchange.py — one broker published under the exchange contract.

``BrokerExchange`` holds a ``BrokerBase`` and answers ``ExchangeInterface``, so
``BotContainer`` takes a broker venue's connector through the one order path
every venue uses. ``MainWindow._connect_broker_for_bot`` builds one per broker
and hands it to the bot. The two classes publish five members under one name
with different contracts — ``connect``, ``place_order``, ``get_order``,
``get_open_orders`` and ``cancel_order`` — so one object cannot publish both and
a holder is what reconciles them.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone
from typing import Any, Optional

from ..exchange.base import (
    AssetInfo,
    Balance,
    ExchangeInterface,
    Order,
    OrderBook,
    OrderSide,
    OrderStatus,
    OrderType,
    Ticker,
)
from .broker_base import (
    BrokerBase,
    OrderSide as BrokerOrderSide,
    OrderType as BrokerOrderType,
    TimeInForce,
    broker_paper_route,
)

logger = logging.getLogger("acervator.stocks")

#: The broker side each exchange side names, mapped by member and not by
#: spelling: the two vocabularies are separate enums.
BROKER_SIDES = {
    OrderSide.BUY: BrokerOrderSide.BUY,
    OrderSide.SELL: BrokerOrderSide.SELL,
}

#: The broker order type and time in force each exchange order type names.
#: ``IOC_LIMIT`` is the limit order a venue cancels on the spot, which is what
#: ``ExchangeInterface.place_order`` declares it to be. A plain limit order
#: names ``TimeInForce.GTC``, so a resting ladder rung does not die at a session
#: close, and a market order names ``TimeInForce.DAY``, the default
#: ``BrokerBase.place_order`` already carries.
BROKER_ORDER_TYPES = {
    OrderType.MARKET: (BrokerOrderType.MARKET, TimeInForce.DAY),
    OrderType.LIMIT: (BrokerOrderType.LIMIT, TimeInForce.GTC),
    OrderType.IOC_LIMIT: (BrokerOrderType.LIMIT, TimeInForce.IOC),
}

#: The exchange order type a broker's own reply reads back as. The three broker
#: types with no exchange member are absent, and ``exchange_order_type`` reads
#: those from whether the reply named a limit price.
EXCHANGE_ORDER_TYPES = {
    BrokerOrderType.MARKET: OrderType.MARKET,
    BrokerOrderType.LIMIT: OrderType.LIMIT,
}

#: The exchange status each status word a broker publishes reads as. A word no
#: row holds reads ``OrderStatus.OPEN``, so an unrecognised state is still
#: waited on and no fill is booked that the venue never reported.
ORDER_STATUSES = {
    "new": OrderStatus.OPEN,
    "open": OrderStatus.OPEN,
    "accepted": OrderStatus.OPEN,
    "pending_new": OrderStatus.OPEN,
    "queued": OrderStatus.OPEN,
    "confirmed": OrderStatus.OPEN,
    "held": OrderStatus.OPEN,
    "partially_filled": OrderStatus.PARTIALLY_FILLED,
    "partial": OrderStatus.PARTIALLY_FILLED,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "rejected": OrderStatus.FAILED,
    "expired": OrderStatus.FAILED,
    "failed": OrderStatus.FAILED,
}

#: Why an order was not sent. Each names the venue and what it could not shape,
#: and each reads the way ``BotContainer.guarded_place_order``'s own refusals do.
NO_ORDER_TYPE = (
    "{venue} publishes no order type for {order_type!r}, so no order is sent"
)
NO_ORDER_SIDE = "{venue} publishes no order side for {side!r}, so no order is sent"
NO_ORDER_SIZE = (
    "{venue} {side} {symbol} size is not a finite positive number: {amount!r}, "
    "so no order is sent"
)
NO_LIMIT_PRICE = (
    "{venue} {side} {symbol} is a limit order and no finite positive price was "
    "named, so no order is sent"
)

#: Why a reading an exchange takes has no broker answer at all. Each is raised
#: and never answered, so nothing reads a figure the venue never published.
NO_ORDERBOOK = "{venue} publishes no orderbook, so no depth is read for {symbol}"
NO_FILL_HISTORY = "{venue} publishes no filled-trade history"

#: Why a session did not open, carrying the broker's own refusal word for word.
SESSION_REFUSED = "{venue} session did not open: {refusal}"


def finite_number(value: Any) -> float:
    """``value`` as a float when it is a finite int or float, else 0.0.

    Every figure a broker reply carries passes through here, and a missing or
    unreadable one answers 0.0.
    """
    if type(value) not in (int, float):
        return 0.0
    held = float(value)
    return held if math.isfinite(held) else 0.0


def order_size(value: Any) -> Optional[float]:
    """``value`` as a finite positive float, and None for anything else.

    ``BrokerExchange.place_order`` refuses on None and sends no order.
    """
    if type(value) not in (int, float):
        return None
    held = float(value)
    if not math.isfinite(held) or held <= 0.0:
        return None
    return held


def bar_epoch_ms(stamp: Any) -> Optional[float]:
    """One broker bar's ISO 8601 moment as epoch milliseconds, and None where
    ``stamp`` cannot be read.

    A moment carrying no offset is read as UTC, which keeps every candle off
    this machine's own zone.
    """
    if isinstance(stamp, str) and stamp:
        try:
            read = datetime.fromisoformat(stamp)
        except ValueError:
            return None
        if read.tzinfo is None:
            read = read.replace(tzinfo=timezone.utc)
        return read.timestamp() * 1000.0
    return None


def candle_rows(bars: Any) -> list[list[float]]:
    """Every bar of ``bars`` as one ``[timestamp_ms, open, high, low, close,
    volume]`` row, in the order the broker answered them.

    A bar whose moment ``bar_epoch_ms`` cannot read is dropped, and the dropped
    count is logged.
    """
    rows: list[list[float]] = []
    dropped = 0
    for bar in bars or []:
        if not isinstance(bar, dict):
            dropped += 1
            continue
        moment = bar_epoch_ms(bar.get("timestamp"))
        if moment is None:
            dropped += 1
            continue
        rows.append(
            [
                moment,
                finite_number(bar.get("open")),
                finite_number(bar.get("high")),
                finite_number(bar.get("low")),
                finite_number(bar.get("close")),
                finite_number(bar.get("volume")),
            ]
        )
    if dropped:
        logger.warning(
            "dropped %d of %d broker bar(s) whose moment could not be read",
            dropped,
            dropped + len(rows),
        )
    return rows


def exchange_order_type(order_type: Any, limit_price: Any) -> OrderType:
    """The ``OrderType`` one broker order reply reads back as, from
    ``EXCHANGE_ORDER_TYPES``.

    A stop, stop-limit or trailing-stop reply holds no ``OrderType`` member and
    reads as ``OrderType.LIMIT`` where it named a limit price and
    ``OrderType.MARKET`` where it named none.
    """
    held = EXCHANGE_ORDER_TYPES.get(order_type)
    if held is not None:
        return held
    return OrderType.LIMIT if finite_number(limit_price) > 0.0 else OrderType.MARKET


def exchange_order_status(status: Any) -> OrderStatus:
    """The ``OrderStatus`` one broker status word reads as, and
    ``OrderStatus.OPEN`` for a word ``ORDER_STATUSES`` does not hold."""
    return ORDER_STATUSES.get(str(status or "").strip().lower(), OrderStatus.OPEN)


def exchange_order(placed: Any, symbol: str = "") -> Order:
    """One broker ``StockOrder`` as an ``Order``, with ``symbol`` naming the
    market where the reply named none.

    A broker publishes no fee on an order, so ``fee`` is 0.0 and
    ``fee_currency`` is empty, and the reply's own fields ride in ``raw``.
    """
    quantity = finite_number(getattr(placed, "quantity", 0.0))
    filled = finite_number(getattr(placed, "filled_qty", 0.0))
    remaining = quantity - filled
    side_word = (
        str(getattr(getattr(placed, "side", None), "value", "")) or OrderSide.BUY.value
    )
    return Order(
        id=str(getattr(placed, "order_id", "") or ""),
        symbol=str(getattr(placed, "symbol", "") or symbol),
        side=OrderSide(side_word),
        type=exchange_order_type(
            getattr(placed, "order_type", None), getattr(placed, "limit_price", 0.0)
        ),
        amount=quantity,
        price=finite_number(getattr(placed, "limit_price", 0.0)),
        filled=filled,
        remaining=remaining if remaining > 0.0 else 0.0,
        status=exchange_order_status(getattr(placed, "status", "")),
        timestamp=finite_number(getattr(placed, "submitted_at", 0.0)),
        average=finite_number(getattr(placed, "avg_fill_price", 0.0)),
        raw={
            "order_type": str(
                getattr(getattr(placed, "order_type", None), "value", "")
            ),
            "time_in_force": str(
                getattr(getattr(placed, "time_in_force", None), "value", "")
            ),
            "status": str(getattr(placed, "status", "") or ""),
            "stop_price": finite_number(getattr(placed, "stop_price", 0.0)),
            "filled_at": finite_number(getattr(placed, "filled_at", 0.0)),
        },
    )


class BrokerExchange(ExchangeInterface):
    """One ``BrokerBase`` answering ``ExchangeInterface``.

    ``broker`` is the held connector, which keeps the members no exchange
    publishes — ``open_session``, ``list_assets``, ``record_markets`` and
    ``session_mode`` — so ``MainWindow`` opens the session on the broker and the
    bot trades through this object.
    """

    def __init__(self, broker: BrokerBase) -> None:
        self._broker = broker

    @property
    def broker(self) -> BrokerBase:
        """The held ``BrokerBase``, which the window opens the session on."""
        return self._broker

    @property
    def exchange_id(self) -> str:
        """The broker's own venue id, which ``BotManager.set_connector`` reads
        to skip a bot on another venue."""
        return self._broker.exchange_id

    @property
    def display_name(self) -> str:
        """The broker's own readable venue name."""
        return self._broker.display_name

    @property
    def is_connected(self) -> bool:
        """Whether the broker's session is open, which
        ``MainWindow._live_connector`` reads."""
        return self._broker.is_connected

    @property
    def scan_symbols(self) -> set:
        """Every symbol the broker holds for scanning."""
        return self._broker.scan_symbols

    def add_scan_symbol(self, symbol: str) -> None:
        """Hold ``symbol`` on the broker."""
        self._broker.add_scan_symbol(symbol)

    def remove_scan_symbol(self, symbol: str) -> None:
        """Drop ``symbol`` from the broker."""
        self._broker.remove_scan_symbol(symbol)

    def set_history_callback(self, callback: Any) -> None:
        """Hold ``callback`` on the broker for the trade history pane."""
        self._broker.set_history_callback(callback)

    def release(self) -> int:
        """Release the broker and answer how many scan symbols it cleared."""
        return self._broker.release()

    def held_assets(self) -> list[dict]:
        """Every asset record the broker last read."""
        return self._broker.held_assets()

    async def connect(
        self, api_key: str, api_secret: str, passphrase: str = ""
    ) -> None:
        """Open the broker's session through ``BrokerBase.open_session`` on the
        route ``broker_paper_route`` names, making ``is_connected`` True.

        ``passphrase`` is accepted and not sent, and a refused session raises
        ``ConnectionError`` carrying ``BrokerBase.session_refusal``.
        """
        del passphrase
        opened = await self._broker.open_session(
            api_key, api_secret, broker_paper_route(self._broker)
        )
        if not opened:
            raise ConnectionError(
                SESSION_REFUSED.format(
                    venue=self.display_name,
                    refusal=self._broker.session_refusal or "refused",
                )
            )

    async def disconnect(self) -> None:
        """Close the broker's session, making ``is_connected`` False."""
        await self._broker.disconnect()

    async def get_ticker(self, symbol: str) -> Ticker:
        """The broker's ``get_quote`` reading for ``symbol`` as a ``Ticker``.

        A broker publishes no 24-hour figure on a quote, so ``volume_24h``
        carries the quote's own volume.
        """
        quote = await self._broker.get_quote(str(symbol))
        return Ticker(
            symbol=str(getattr(quote, "symbol", "") or symbol),
            bid=finite_number(getattr(quote, "bid", 0.0)),
            ask=finite_number(getattr(quote, "ask", 0.0)),
            last=finite_number(getattr(quote, "last", 0.0)),
            volume_24h=finite_number(getattr(quote, "volume", 0.0)),
            timestamp=finite_number(getattr(quote, "timestamp", 0.0)),
        )

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """Raises ``NotImplementedError``: a broker publishes no depth tool, and
        no level is read for ``symbol``."""
        del limit
        raise NotImplementedError(
            NO_ORDERBOOK.format(venue=self.display_name, symbol=symbol)
        )

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: Optional[int] = None,
    ) -> list[list[float]]:
        """The broker's ``get_bars`` candles for ``symbol`` as
        ``[timestamp_ms, open, high, low, close, volume]`` rows.

        ``BrokerBase.get_bars`` takes no floor, so ``since`` narrows the rows it
        answered.
        """
        bars = await self._broker.get_bars(str(symbol), str(timeframe), int(limit))
        rows = candle_rows(bars)
        if since is None:
            return rows
        floor = finite_number(since)
        return [row for row in rows if row[0] >= floor]

    async def get_balances(self) -> dict[str, Balance]:
        """One ``Balance`` per position the broker holds, plus the account's
        cash under ``BrokerBase.CASH_CURRENCY``."""
        found: dict[str, Balance] = {}
        for position in await self._broker.get_positions() or []:
            name = str(getattr(position, "symbol", "") or "")
            if not name:
                continue
            found[name] = self._position_balance(name, position)
        cash_name = str(getattr(self._broker, "CASH_CURRENCY", "") or "")
        if cash_name:
            found[cash_name] = await self._cash_balance(cash_name)
        return found

    async def get_balance(self, currency: str) -> Balance:
        """The broker's figure for ``currency``: ``BrokerBase.CASH_CURRENCY``
        answers from ``get_account``'s cash, and every other name from the
        quantity of the position held under it.

        A currency the broker reports neither for gives a zeroed ``Balance``
        with ``absent`` True.
        """
        name = str(currency or "")
        if name and name == str(getattr(self._broker, "CASH_CURRENCY", "") or ""):
            return await self._cash_balance(name)
        position = await self._broker.get_position(name)
        if position is None:
            return Balance(currency=name, free=0.0, used=0.0, total=0.0, absent=True)
        return self._position_balance(name, position)

    async def _cash_balance(self, currency: str) -> Balance:
        """The account's cash as a ``Balance`` for ``currency``.

        A broker publishes no held-against-orders figure on an account, so
        ``used`` is 0.0 and ``free`` carries the whole cash figure.
        """
        account = await self._broker.get_account()
        cash = finite_number(getattr(account, "cash", 0.0))
        return Balance(currency=currency, free=cash, used=0.0, total=cash)

    @staticmethod
    def _position_balance(currency: str, position: Any) -> Balance:
        """One ``StockPosition`` as a ``Balance`` for ``currency``.

        A broker publishes no locked figure on a position, so ``used`` is 0.0
        and ``free`` carries the whole quantity.
        """
        held = finite_number(getattr(position, "quantity", 0.0))
        return Balance(currency=currency, free=held, used=0.0, total=held)

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Order:
        """Submit one order through ``BrokerBase.place_order``, shaped by
        ``BROKER_ORDER_TYPES``, and answer the resulting ``Order``.

        A side or order type no table row holds, a size that is not a finite
        positive number, and a limit order naming no finite positive price each
        raise ``ValueError`` before the broker is reached; ``client_order_id``
        is accepted and not sent.
        """
        del client_order_id
        shape = BROKER_ORDER_TYPES.get(order_type)
        if shape is None:
            raise ValueError(
                NO_ORDER_TYPE.format(venue=self.display_name, order_type=order_type)
            )
        broker_side = BROKER_SIDES.get(side)
        if broker_side is None:
            raise ValueError(NO_ORDER_SIDE.format(venue=self.display_name, side=side))
        broker_type, time_in_force = shape
        size = order_size(amount)
        if size is None:
            raise ValueError(
                NO_ORDER_SIZE.format(
                    venue=self.display_name,
                    side=broker_side.value,
                    symbol=symbol,
                    amount=amount,
                )
            )
        limit_price = 0.0
        if broker_type is BrokerOrderType.LIMIT:
            limit_price = finite_number(price)
            if limit_price <= 0.0:
                raise ValueError(
                    NO_LIMIT_PRICE.format(
                        venue=self.display_name,
                        side=broker_side.value,
                        symbol=symbol,
                    )
                )
        placed = await self._broker.place_order(
            str(symbol),
            broker_side,
            size,
            broker_type,
            limit_price=limit_price,
            time_in_force=time_in_force,
        )
        return exchange_order(placed, symbol=str(symbol))

    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        """Cancel ``order_id`` through the broker and answer the result as an
        ``Order``.

        ``BrokerBase.cancel_order`` answers a boolean alone, so the ``Order``
        carries the id, the market and the status; ``side``, ``type``,
        ``amount`` and ``price`` are placeholders the reply named none of, and
        ``raw`` carries the boolean.
        """
        accepted = bool(await self._broker.cancel_order(str(order_id)))
        return Order(
            id=str(order_id),
            symbol=str(symbol),
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            amount=0.0,
            price=0.0,
            status=OrderStatus.CANCELLED if accepted else OrderStatus.FAILED,
            raw={"cancelled": accepted},
        )

    async def get_order(self, order_id: str, symbol: str) -> Order:
        """The broker's own record of ``order_id`` as an ``Order``.

        ``BrokerBase.get_order`` takes no market, so ``symbol`` names the market
        only where the reply named none.
        """
        placed = await self._broker.get_order(str(order_id))
        return exchange_order(placed, symbol=str(symbol))

    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        """Every open order the broker holds as an ``Order``, narrowed to
        ``symbol``.

        ``BrokerBase.get_open_orders`` takes no market and answers the whole
        book, so the narrowing happens here.
        """
        placed = await self._broker.get_open_orders()
        held = [exchange_order(one) for one in placed or []]
        if symbol is None:
            return held
        name = str(symbol)
        return [one for one in held if one.symbol == name]

    async def get_my_trades(
        self, symbol: str, since: Optional[float] = None, limit: Optional[int] = None
    ) -> list:
        """Raises ``NotImplementedError``: a broker publishes no filled-trade
        history, so ``FillHistory`` has no page to read."""
        del symbol, since, limit
        raise NotImplementedError(NO_FILL_HISTORY.format(venue=self.display_name))

    async def get_markets(self) -> list[AssetInfo]:
        """Every market the broker's held asset list publishes, as
        ``AssetInfo``, read through ``BrokerBase.asset_infos``.

        No broker is contacted and the recording is not rewritten; an empty held
        list answers no market.
        """
        return self._broker.asset_infos(self._broker.held_assets())

    async def get_asset_logo_url(self, currency: str) -> str:
        """An empty string: a broker publishes no logo path for ``currency``."""
        del currency
        return ""


__all__ = [
    "BROKER_ORDER_TYPES",
    "BROKER_SIDES",
    "EXCHANGE_ORDER_TYPES",
    "NO_FILL_HISTORY",
    "NO_LIMIT_PRICE",
    "NO_ORDERBOOK",
    "NO_ORDER_SIDE",
    "NO_ORDER_SIZE",
    "NO_ORDER_TYPE",
    "ORDER_STATUSES",
    "SESSION_REFUSED",
    "BrokerExchange",
    "bar_epoch_ms",
    "candle_rows",
    "exchange_order",
    "exchange_order_status",
    "exchange_order_type",
    "finite_number",
    "order_size",
]
