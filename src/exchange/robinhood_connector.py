"""Hand-written :class:`ExchangeInterface` for Robinhood's crypto markets.

``order_body`` builds the venue's own order shape and ``signed_headers`` signs
it with an Ed25519 key. ``pair_rules`` turns one published trading-pair record
into the ``MarketRules`` ``BotContainer.guarded_place_order`` sizes against.
``crypto_connector_class`` answers this class for ``VENUE_ID``, and ccxt 4.5.85
carries no robinhood entry for ``CCXTConnector`` to reach.
"""

from __future__ import annotations

import base64
import json
import logging
import math
import time
import uuid
from collections import deque
from decimal import Decimal
from typing import Any, Iterable, Optional

from .base import (
    AssetInfo,
    Balance,
    ExchangeInterface,
    MarketRules,
    Order,
    OrderBook,
    OrderSide,
    OrderStatus,
    OrderType,
    Ticker,
)
from .market_rules_store import record_venue

logger = logging.getLogger("acervator.exchange.robinhood")

#: The venue id this connector answers and a ``BotConfig`` carries.
VENUE_ID = "robinhood"

#: The label the window writes to the log for ``VENUE_ID``.
VENUE_LABEL = "Robinhood"

#: The host Robinhood publishes its crypto trading paths under.
TRADING_HOST = "https://trading.robinhood.com"

#: The order path carrying no fee tier, which takes no account number.
ORDERS_PATH = "/api/v1/crypto/trading/orders/"

#: The order path carrying fee tiers, whose volume alone counts toward a tier.
ORDERS_PATH_FEE_TIERS = "/api/v2/crypto/trading/orders/"

#: The query parameter ``ORDERS_PATH_FEE_TIERS`` names the account under.
ACCOUNT_QUERY_KEY = "account_number"

#: The three headers Robinhood requires on an authenticated request.
HEADER_API_KEY = "x-api-key"
HEADER_SIGNATURE = "x-signature"
HEADER_TIMESTAMP = "x-timestamp"

#: Robinhood names a Get Crypto Trading Pairs endpoint and publishes no path
#: for it, so none is held.
TRADING_PAIRS_PATH: Optional[str] = None

#: The four order types Robinhood publishes for a crypto order.
ORDER_TYPE_MARKET = "market"
ORDER_TYPE_LIMIT = "limit"
ORDER_TYPE_STOP_LOSS = "stop_loss"
ORDER_TYPE_STOP_LIMIT = "stop_limit"
VENUE_ORDER_TYPES = (
    ORDER_TYPE_MARKET,
    ORDER_TYPE_LIMIT,
    ORDER_TYPE_STOP_LOSS,
    ORDER_TYPE_STOP_LIMIT,
)

#: The configuration object each order type carries its own fields in.
ORDER_CONFIG_KEYS: dict[str, str] = {
    ORDER_TYPE_MARKET: "market_order_config",
    ORDER_TYPE_LIMIT: "limit_order_config",
    ORDER_TYPE_STOP_LOSS: "stop_loss_order_config",
    ORDER_TYPE_STOP_LIMIT: "stop_limit_order_config",
}

#: The order types whose configuration carries a time in force.
TIMED_ORDER_TYPES = (ORDER_TYPE_LIMIT, ORDER_TYPE_STOP_LOSS, ORDER_TYPE_STOP_LIMIT)

#: The size field naming a count of the base currency. Robinhood permits
#: ``quote_amount`` instead, which no built variant selects.
SIZE_FIELD_UNITS = "asset_quantity"

#: The four times in force Robinhood publishes. None is immediate-or-cancel.
TIME_IN_FORCE_GTC = "gtc"
VENUE_TIMES_IN_FORCE = (TIME_IN_FORCE_GTC, "gfd", "gfw", "gfm")

#: The decimal places ``asset_increment`` and ``quote_increment`` reach.
VENUE_DECIMAL_PLACES = 18

#: The separator Robinhood puts between a pair's two legs, and the slash a
#: unified symbol carries.
VENUE_PAIR_SEPARATOR = "-"
UNIFIED_PAIR_SEPARATOR = "/"

#: The keys one published trading-pair record carries its rules under.
PAIR_SYMBOL_KEY = "symbol"
PAIR_ASSET_INCREMENT_KEY = "asset_increment"
PAIR_QUOTE_INCREMENT_KEY = "quote_increment"
PAIR_MAX_ORDER_SIZE_KEY = "max_order_size"
PAIR_MIN_ORDER_AMOUNT_KEY = "min_order_amount"
PAIR_API_TRADABLE_KEY = "is_api_tradable"

#: The requests a minute Robinhood publishes per account, and its burst figure.
RATE_LIMIT_PER_MINUTE = 100
RATE_LIMIT_BURST_PER_MINUTE = 300

#: The window ``RATE_LIMIT_PER_MINUTE`` is published over, in seconds.
RATE_LIMIT_WINDOW_S = 60.0

#: The namespace ``client_order_uuid`` derives a UUID under, so one trade
#: intent names one UUID.
CLIENT_ORDER_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")

#: Why a read refuses: Robinhood names the endpoint and publishes no path.
PATH_UNPUBLISHED_FORMAT = (
    "Robinhood names a {endpoint} endpoint for crypto and publishes no path for "
    "it, so {asked} is not fetched and nothing is sent"
)

#: Why an order refuses with nothing stored.
NO_CREDENTIAL = (
    "no Robinhood API key and no Ed25519 private key are stored, so no request "
    "can be signed"
)

#: Why an order refuses on a symbol holding no trading-pair record.
UNLISTED_MARKET_FORMAT = (
    "Robinhood lists no trading pair for {symbol}; {held} pair record(s) are "
    "held and a market with no record has no size rule to size against"
)

#: Why an order refuses on an immediate-or-cancel type.
NO_IMMEDIATE_OR_CANCEL = (
    "Robinhood publishes four times in force, gtc, gfd, gfw and gfm, and no "
    "immediate-or-cancel, so an IOC order names a field the venue has none of"
)


class RobinhoodPathUnpublished(RuntimeError):
    """Raised where Robinhood names an endpoint and publishes no path for it."""


class RobinhoodOrderRefused(RuntimeError):
    """Raised where this connector refuses an order before any request."""


def pair_number(value: Any) -> Optional[float]:
    """``value`` as a positive finite float where a pair record published a
    number or a decimal string, else None.

    ``PAIR_ASSET_INCREMENT_KEY`` arrives as a decimal string of up to
    ``VENUE_DECIMAL_PLACES`` places.
    """
    if type(value) not in (int, float, str):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0.0:
        return None
    return parsed


def decimal_text(value: Any) -> str:
    """``value`` as a plain decimal string carrying no exponent.

    ``Decimal`` reads the shortest repr, so a count of 116.63 reaches the venue
    as 116.63 and not as the binary expansion a fixed width prints.
    """
    try:
        held = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{value!r} is not a number Robinhood can be sent")
    if not math.isfinite(held):
        raise ValueError(f"{value!r} is not a finite number Robinhood can be sent")
    return format(Decimal(repr(held)).normalize(), "f")


def venue_symbol(symbol: Any) -> str:
    """One unified symbol as Robinhood spells it, upper case on
    ``VENUE_PAIR_SEPARATOR``.

    Empty for anything that is not a non-empty ``str``.
    """
    if type(symbol) is not str or not symbol:
        return ""
    return symbol.strip().upper().replace(UNIFIED_PAIR_SEPARATOR, VENUE_PAIR_SEPARATOR)


def unified_symbol(symbol: Any) -> str:
    """One Robinhood pair symbol as this platform spells it, upper case on
    ``UNIFIED_PAIR_SEPARATOR``.

    Empty for anything that is not a non-empty ``str``.
    """
    if type(symbol) is not str or not symbol:
        return ""
    return symbol.strip().upper().replace(VENUE_PAIR_SEPARATOR, UNIFIED_PAIR_SEPARATOR)


def client_order_uuid(client_order_id: Any) -> str:
    """One client order id as the valid UUID Robinhood requires.

    ``IdempotencyLayer.derive_coid`` answers ``acrv-`` and sixteen hex
    characters, and one id always derives one UUID under
    ``CLIENT_ORDER_NAMESPACE``.
    """
    held = str(client_order_id or "")
    if not held:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(held))
    except (AttributeError, TypeError, ValueError):
        return str(uuid.uuid5(CLIENT_ORDER_NAMESPACE, held))


def venue_order_type(order_type: Any) -> str:
    """The Robinhood order type one ``OrderType`` names.

    ``OrderType.IOC_LIMIT`` raises ``RobinhoodOrderRefused``, and
    ``VENUE_TIMES_IN_FORCE`` holds no immediate-or-cancel member.
    """
    if order_type == OrderType.MARKET:
        return ORDER_TYPE_MARKET
    if order_type == OrderType.LIMIT:
        return ORDER_TYPE_LIMIT
    if order_type == OrderType.IOC_LIMIT:
        raise RobinhoodOrderRefused(NO_IMMEDIATE_OR_CANCEL)
    raise RobinhoodOrderRefused(
        f"order type {order_type!r} is not one of {VENUE_ORDER_TYPES}"
    )


def orders_path(account_number: Any = None) -> str:
    """The order path one submission takes.

    ``ORDERS_PATH_FEE_TIERS`` with ``ACCOUNT_QUERY_KEY`` where an account
    number is held, and ``ORDERS_PATH`` where none is.
    """
    held = str(account_number or "").strip()
    if not held:
        return ORDERS_PATH
    return f"{ORDERS_PATH_FEE_TIERS}?{ACCOUNT_QUERY_KEY}={held}"


def order_body(
    symbol: Any,
    side: Any,
    order_type: Any,
    amount: Any,
    price: Any = None,
    client_order_id: Any = None,
    time_in_force: str = TIME_IN_FORCE_GTC,
) -> dict:
    """The order body Robinhood publishes for a crypto order.

    Four fields and the ``ORDER_CONFIG_KEYS`` object the type requires, with
    the size riding as ``SIZE_FIELD_UNITS``.
    """
    named = venue_symbol(symbol)
    if not named:
        raise RobinhoodOrderRefused(f"symbol {symbol!r} names no Robinhood pair")
    if time_in_force not in VENUE_TIMES_IN_FORCE:
        raise RobinhoodOrderRefused(
            f"time in force {time_in_force!r} is not one of {VENUE_TIMES_IN_FORCE}"
        )
    kind = venue_order_type(order_type)
    config: dict[str, str] = {SIZE_FIELD_UNITS: decimal_text(amount)}
    if kind in (ORDER_TYPE_LIMIT, ORDER_TYPE_STOP_LIMIT):
        if price is None:
            raise RobinhoodOrderRefused(f"a {kind} order carries no limit price")
        config["limit_price"] = decimal_text(price)
    if kind in (ORDER_TYPE_STOP_LOSS, ORDER_TYPE_STOP_LIMIT):
        if price is None:
            raise RobinhoodOrderRefused(f"a {kind} order carries no stop price")
        config["stop_price"] = decimal_text(price)
    if kind in TIMED_ORDER_TYPES:
        config["time_in_force"] = time_in_force
    return {
        "symbol": named,
        "client_order_id": client_order_uuid(client_order_id),
        "side": OrderSide(side).value,
        "type": kind,
        ORDER_CONFIG_KEYS[kind]: config,
    }


def body_text(body: Any) -> str:
    """One order body as the request carries it, and empty for no body.

    ``signed_message`` holds the same characters ``_send`` sends.
    """
    if body is None:
        return ""
    return json.dumps(body, separators=(",", ":"))


def signed_message(
    api_key: Any, timestamp: Any, path: Any, method: Any, body: Any = ""
) -> str:
    """The message Robinhood signs: ``api_key``, ``timestamp``, ``path``,
    ``method`` and ``body``, in that order and with no separator.

    A request with no ``body`` omits it from the message.
    """
    return f"{api_key}{timestamp}{path}{str(method).upper()}{body or ''}"


def signature(
    private_key_b64: Any,
    api_key: Any,
    timestamp: Any,
    path: Any,
    method: Any,
    body: Any = "",
) -> str:
    """The base64 Ed25519 signature over ``signed_message``.

    ``private_key_b64`` is the base64 seed Robinhood's own generator writes,
    and ``ValueError`` names a seed this reader cannot load.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    try:
        seed = base64.b64decode(str(private_key_b64), validate=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"the stored Robinhood private key is not base64: {exc}")
    # A 64-byte export carries the public half after the 32-byte seed.
    if len(seed) == 64:
        seed = seed[:32]
    if len(seed) != 32:
        raise ValueError(
            f"an Ed25519 seed is 32 bytes and the stored key decodes to {len(seed)}"
        )
    held = Ed25519PrivateKey.from_private_bytes(seed)
    message = signed_message(api_key, timestamp, path, method, body)
    return base64.b64encode(held.sign(message.encode("utf-8"))).decode("ascii")


def signed_headers(
    api_key: Any,
    private_key_b64: Any,
    path: Any,
    method: Any,
    body: Any = "",
    timestamp: Any = None,
) -> dict[str, str]:
    """The three headers Robinhood requires, signed over ``signed_message``.

    ``timestamp`` is the current Unix timestamp in seconds where none is given.
    """
    stamp = int(time.time()) if timestamp is None else int(timestamp)
    return {
        HEADER_API_KEY: str(api_key),
        HEADER_SIGNATURE: signature(
            private_key_b64, api_key, stamp, path, method, body
        ),
        HEADER_TIMESTAMP: str(stamp),
    }


def pair_symbol(pair: Any) -> str:
    """The unified symbol one published trading-pair record names.

    Empty for anything that is not a record naming ``PAIR_SYMBOL_KEY``.
    """
    if not isinstance(pair, dict):
        return ""
    return unified_symbol(pair.get(PAIR_SYMBOL_KEY))


def pair_declared_order_types() -> str:
    """The order types Robinhood declares for every crypto pair.

    ``VENUE_ORDER_TYPES`` holds ``ORDER_TYPE_MARKET`` beside
    ``ORDER_TYPE_LIMIT``, and no pair record narrows it.
    """
    from ..trading.scrumming.sizing import ORDER_TYPES_WITH_MARKET

    return ORDER_TYPES_WITH_MARKET


def pair_size_shapes() -> frozenset:
    """The size shapes a Robinhood crypto order may name on either side.

    Every ``ORDER_CONFIG_KEYS`` object takes ``SIZE_FIELD_UNITS`` or a quote
    amount, and neither side permits one of the two alone.
    """
    from ..trading.scrumming.sizing import SHAPE_CASH_AMOUNT, SHAPE_FRACTIONAL_UNITS

    return frozenset({SHAPE_FRACTIONAL_UNITS, SHAPE_CASH_AMOUNT})


def pair_rules(pair: Any) -> MarketRules:
    """The ``MarketRules`` one published trading-pair record publishes.

    ``read`` is False for a non-record and for a pair ``PAIR_API_TRADABLE_KEY``
    reads False on, and a rule the record does not name is None.
    """
    if not isinstance(pair, dict):
        return MarketRules(read=False)
    if pair.get(PAIR_API_TRADABLE_KEY) is False:
        return MarketRules(read=False)
    shapes = pair_size_shapes()
    return MarketRules(
        amount_increment=pair_number(pair.get(PAIR_ASSET_INCREMENT_KEY)),
        quote_increment=pair_number(pair.get(PAIR_QUOTE_INCREMENT_KEY)),
        # Robinhood publishes a minimum in the quote currency and none in the
        # asset currency.
        min_cost=pair_number(pair.get(PAIR_MIN_ORDER_AMOUNT_KEY)),
        order_types=pair_declared_order_types(),
        buy_size_shapes=shapes,
        sell_size_shapes=shapes,
    )


def pair_asset_class(pair: Any = None) -> str:
    """The sector one published trading-pair record belongs to.

    Every pair ``record_pairs`` holds is a crypto pair, and Robinhood's equity
    route is a Model Context Protocol server this connector does not reach.
    """
    del pair
    from ..trading.scrumming.sizing import CLASS_CRYPTO

    return CLASS_CRYPTO


def pair_asset_info(pair: Any) -> Optional[AssetInfo]:
    """One ``AssetInfo`` from one published trading-pair record.

    None for a record ``pair_symbol`` answers empty for.
    """
    symbol = pair_symbol(pair)
    if not symbol:
        return None
    base, _, quote = symbol.partition(UNIFIED_PAIR_SEPARATOR)
    return AssetInfo(
        symbol=symbol,
        base=base,
        quote=quote,
        rules=pair_rules(pair),
        # A pair record publishes no fee, so AssetInfo carries zero.
        maker_fee=0.0,
        taker_fee=0.0,
        active=pair.get(PAIR_API_TRADABLE_KEY) is not False,
    )


class RobinhoodCryptoConnector(ExchangeInterface):
    """Robinhood's crypto markets behind the contract every bot's order path
    reads.

    ``place_order`` signs the venue's own body and hands it to ``_send``, and
    every read method raises ``RobinhoodPathUnpublished``.
    """

    def __init__(self, exchange_id: str = VENUE_ID) -> None:
        self._exchange_id = str(exchange_id or VENUE_ID)
        self._api_key = ""
        self._private_key_b64 = ""
        self._account_number = ""
        self._connected = False
        self._pairs: dict[str, dict] = {}
        self._scan_symbols: set[str] = set()
        self._history_callback: Any = None
        self._sent_at_s: deque = deque()
        self._session: Any = None

    @property
    def exchange_id(self) -> str:
        """``VENUE_ID``, the id ``BotManager.set_connector`` reads."""
        return self._exchange_id

    @property
    def display_name(self) -> str:
        """``VENUE_LABEL``, the label the window writes to the log."""
        return VENUE_LABEL

    @property
    def is_connected(self) -> bool:
        """True while ``connect`` held both halves of a credential."""
        return self._connected

    @property
    def scan_symbols(self) -> set[str]:
        """Every symbol ``add_scan_symbol`` holds."""
        return set(self._scan_symbols)

    @property
    def held_pairs(self) -> dict[str, dict]:
        """Every record ``record_pairs`` holds, keyed by unified symbol."""
        return dict(self._pairs)

    def add_scan_symbol(self, symbol: str) -> None:
        """Hold ``symbol`` in ``scan_symbols``.

        No history scan thread starts, so ``scan_symbols`` is the whole effect.
        """
        if symbol:
            self._scan_symbols.add(str(symbol))

    def set_history_callback(self, callback: Any) -> None:
        """Hold ``callback`` for the trade history pane."""
        self._history_callback = callback

    def release(self) -> int:
        """Clear ``scan_symbols`` and the history callback, mark this connector
        disconnected, and answer how many scan symbols were cleared."""
        cleared = len(self._scan_symbols)
        self._scan_symbols.clear()
        self._history_callback = None
        self._connected = False
        logger.info(
            "Released %s connector — %d scan symbol(s) dropped",
            VENUE_LABEL,
            cleared,
        )
        return cleared

    async def connect(
        self, api_key: str, api_secret: str, passphrase: str = ""
    ) -> None:
        """Hold the API key and the base64 Ed25519 private key and make
        ``is_connected`` True.

        ``api_secret`` is the private key, ``passphrase`` is the account number
        ``orders_path`` takes, and no request is sent.
        """
        self._api_key = str(api_key or "")
        self._private_key_b64 = str(api_secret or "")
        self._account_number = str(passphrase or "")
        self._connected = bool(self._api_key and self._private_key_b64)
        logger.info(
            "%s connector holds a credential: %s",
            VENUE_LABEL,
            "yes" if self._connected else "no",
        )

    async def disconnect(self) -> None:
        """Drop the credential, close any session, and make ``is_connected``
        False."""
        self._connected = False
        self._api_key = ""
        self._private_key_b64 = ""
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as exc:
                logger.warning("%s session already closed: %s", VENUE_LABEL, exc)
            self._session = None

    def record_pairs(self, pairs: Iterable[Any]) -> list[AssetInfo]:
        """Hold every published trading-pair record of ``pairs`` and record its
        rules under ``exchange_id``, answering one ``AssetInfo`` per market.

        No venue is contacted, a record naming no symbol is skipped, and an
        empty ``pairs`` keeps the rows already recorded.
        """
        built: list[AssetInfo] = []
        held: dict[str, dict] = {}
        classes: dict[str, str] = {}
        for pair in pairs:
            info = pair_asset_info(pair)
            if info is None:
                continue
            held[info.symbol] = dict(pair)
            classes[info.symbol] = pair_asset_class(pair)
            built.append(info)
        if built:
            self._pairs.update(held)
            record_venue(self._exchange_id, built, classes=classes)
        return built

    async def get_markets(self) -> list[AssetInfo]:
        """One ``AssetInfo`` per trading pair this connector holds.

        ``RobinhoodPathUnpublished`` while ``held_pairs`` is empty, and
        Robinhood publishes no path for its Get Crypto Trading Pairs endpoint.
        """
        if not self._pairs:
            raise RobinhoodPathUnpublished(
                PATH_UNPUBLISHED_FORMAT.format(
                    endpoint="Get Crypto Trading Pairs", asked="the market list"
                )
            )
        answered = [pair_asset_info(pair) for pair in self._pairs.values()]
        return [info for info in answered if info is not None]

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Order:
        """Build, sign and submit Robinhood's own order body, answering the
        ``Order`` the venue's reply names.

        ``RobinhoodOrderRefused`` with no credential stored, on a symbol
        ``held_pairs`` lacks, and on a type ``VENUE_ORDER_TYPES`` lacks.
        """
        from .api_logger import get_api_log

        log = get_api_log()
        named = unified_symbol(symbol)
        if not self._api_key or not self._private_key_b64:
            self._record_refusal(log, symbol, side, order_type, amount, NO_CREDENTIAL)
            raise RobinhoodOrderRefused(NO_CREDENTIAL)
        if named not in self._pairs:
            refusal = UNLISTED_MARKET_FORMAT.format(
                symbol=named or symbol, held=len(self._pairs)
            )
            self._record_refusal(log, symbol, side, order_type, amount, refusal)
            raise RobinhoodOrderRefused(refusal)
        try:
            body = order_body(symbol, side, order_type, amount, price, client_order_id)
        except (RobinhoodOrderRefused, ValueError) as exc:
            self._record_refusal(log, symbol, side, order_type, amount, str(exc))
            raise
        path = orders_path(self._account_number)
        text = body_text(body)
        headers = signed_headers(
            self._api_key, self._private_key_b64, path, "POST", text
        )
        log.record(
            exchange=self._exchange_id,
            action="PLACE_ORDER",
            reason=(
                f"Execute {OrderSide(side).value.upper()} {body['type']} order "
                f"for {body['symbol']}"
            ),
            endpoint=path,
            params={
                "symbol": body["symbol"],
                "side": body["side"],
                "type": body["type"],
                "amount": float(amount),
                "price": price,
            },
            result="Sending to Robinhood...",
            level="info",
            data_usage=(
                "Order will be tracked for fill status; fills trigger profit "
                "folding or grid cycling"
            ),
        )
        await self._pace()
        raw = await self._send("POST", path, text, headers)
        return self._parse_order(raw, body, amount, price)

    def _record_refusal(
        self,
        log: Any,
        symbol: Any,
        side: Any,
        order_type: Any,
        amount: Any,
        refusal: str,
    ) -> None:
        """Write one ORDER_REFUSED line naming what stopped the submission."""
        log.record(
            exchange=self._exchange_id,
            action="ORDER_REFUSED",
            reason=f"{VENUE_LABEL} order not sent for {symbol}: {refusal}",
            endpoint=orders_path(self._account_number),
            params={
                "symbol": str(symbol),
                "side": getattr(side, "value", str(side)),
                "type": getattr(order_type, "value", str(order_type)),
                "amount": amount,
            },
            result="Not sent. No request was signed.",
            level="error",
            data_usage="No order reaches the venue and no fill is booked.",
        )

    def _parse_order(self, raw: Any, body: dict, amount: Any, price: Any) -> Order:
        """The ``Order`` one Robinhood order reply names.

        Every field the reply omits falls back to the submitted ``body``.
        """
        held = raw if isinstance(raw, dict) else {}
        status_map = {
            "open": OrderStatus.OPEN,
            "filled": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "failed": OrderStatus.FAILED,
            "rejected": OrderStatus.FAILED,
        }
        filled = pair_number(held.get("filled_asset_quantity")) or 0.0
        average = pair_number(held.get("average_price")) or 0.0
        asked = float(amount)
        return Order(
            id=str(held.get("id") or body["client_order_id"]),
            symbol=unified_symbol(held.get("symbol") or body["symbol"]),
            side=OrderSide(str(held.get("side") or body["side"])),
            type=(
                OrderType.MARKET
                if str(held.get("type") or body["type"]) == ORDER_TYPE_MARKET
                else OrderType.LIMIT
            ),
            amount=asked,
            price=float(price or 0.0),
            filled=filled,
            remaining=max(asked - filled, 0.0),
            status=status_map.get(str(held.get("state") or ""), OrderStatus.OPEN),
            average=average,
            raw=held,
        )

    async def _pace(self) -> None:
        """Hold the next request until fewer than ``RATE_LIMIT_PER_MINUTE``
        submissions sit inside ``RATE_LIMIT_WINDOW_S``.

        Robinhood publishes a token bucket, so ``_sent_at_s`` counts the window
        and leaves the published burst reachable.
        """
        import asyncio

        while True:
            now_s = time.monotonic()
            while self._sent_at_s and now_s - self._sent_at_s[0] >= RATE_LIMIT_WINDOW_S:
                self._sent_at_s.popleft()
            if len(self._sent_at_s) < RATE_LIMIT_PER_MINUTE:
                self._sent_at_s.append(now_s)
                return
            await asyncio.sleep(RATE_LIMIT_WINDOW_S - (now_s - self._sent_at_s[0]))

    async def _send(
        self, method: str, path: str, body: str, headers: dict[str, str]
    ) -> dict:
        """Send one signed request to ``TRADING_HOST`` and answer its JSON.

        The one method here that reaches the network, which a caller that must
        not reach Robinhood replaces.
        """
        import aiohttp

        if self._session is None:
            self._session = aiohttp.ClientSession()
        sent = dict(headers)
        sent["Content-Type"] = "application/json"
        async with self._session.request(
            method, TRADING_HOST + path, headers=sent, data=body or None
        ) as reply:
            text = await reply.text()
            if reply.status not in (200, 201):
                raise RuntimeError(f"{VENUE_LABEL} {reply.status}: {text}")
            return json.loads(text) if text else {}

    def _read_refused(self, endpoint: str, asked: str) -> RobinhoodPathUnpublished:
        """The ``RobinhoodPathUnpublished`` every read method raises.

        ``PATH_UNPUBLISHED_FORMAT`` names the ``endpoint`` and the ``asked``.
        """
        return RobinhoodPathUnpublished(
            PATH_UNPUBLISHED_FORMAT.format(endpoint=endpoint, asked=asked)
        )

    async def get_ticker(self, symbol: str) -> Ticker:
        """``RobinhoodPathUnpublished`` for ``symbol``."""
        raise self._read_refused("Get Crypto Best Bid Ask", f"a price for {symbol}")

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """``RobinhoodPathUnpublished`` for ``symbol``."""
        del limit
        raise self._read_refused("Get Crypto Best Bid Ask", f"a book for {symbol}")

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: Optional[int] = None,
    ) -> list[list[float]]:
        """``RobinhoodPathUnpublished`` for ``symbol``."""
        del timeframe, limit, since
        raise self._read_refused("crypto candle", f"candles for {symbol}")

    async def get_balances(self) -> dict[str, Balance]:
        """``RobinhoodPathUnpublished`` for every currency."""
        raise self._read_refused("Get Crypto Holdings", "a balance")

    async def get_balance(self, currency: str) -> Balance:
        """``RobinhoodPathUnpublished`` for ``currency``."""
        raise self._read_refused("Get Crypto Holdings", f"a balance for {currency}")

    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        """``RobinhoodPathUnpublished`` for ``order_id``."""
        del symbol
        raise self._read_refused("Cancel Crypto Order", f"a cancel of {order_id}")

    async def get_order(self, order_id: str, symbol: str) -> Order:
        """``RobinhoodPathUnpublished`` for ``order_id``."""
        del symbol
        raise self._read_refused("Get Crypto Order", f"order {order_id}")

    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        """``RobinhoodPathUnpublished`` for every open order."""
        del symbol
        raise self._read_refused("Get Crypto Orders", "the open orders")

    async def get_asset_logo_url(self, currency: str) -> str:
        """Empty, and Robinhood publishes no asset logo endpoint."""
        del currency
        return ""


#: Each venue id holding a hand-written ``ExchangeInterface`` subclass, read as
#: ``BROKER_CONNECTORS`` is read for the broker path.
CRYPTO_CONNECTORS: dict[str, type[ExchangeInterface]] = {
    VENUE_ID: RobinhoodCryptoConnector,
}


def crypto_connector_class(venue_id: Any) -> Optional[type[ExchangeInterface]]:
    """The ``ExchangeInterface`` subclass ``CRYPTO_CONNECTORS`` holds for
    ``venue_id``, and None for a venue ccxt already reaches.

    A venue answering None takes ``CCXTConnector``, so no id here may also sit
    in ``SUPPORTED_EXCHANGES``.
    """
    if not isinstance(venue_id, str):
        return None
    return CRYPTO_CONNECTORS.get(venue_id.strip().lower())


def hand_written_crypto_venues() -> frozenset:
    """Every venue id ``CRYPTO_CONNECTORS`` holds a class for.

    ``asset_class_surface.crypto_venues`` reads this beside
    ``SUPPORTED_EXCHANGES``.
    """
    return frozenset(CRYPTO_CONNECTORS)


__all__ = [
    "ACCOUNT_QUERY_KEY",
    "CLIENT_ORDER_NAMESPACE",
    "CRYPTO_CONNECTORS",
    "HEADER_API_KEY",
    "HEADER_SIGNATURE",
    "HEADER_TIMESTAMP",
    "NO_CREDENTIAL",
    "NO_IMMEDIATE_OR_CANCEL",
    "ORDERS_PATH",
    "ORDERS_PATH_FEE_TIERS",
    "ORDER_CONFIG_KEYS",
    "ORDER_TYPE_LIMIT",
    "ORDER_TYPE_MARKET",
    "ORDER_TYPE_STOP_LIMIT",
    "ORDER_TYPE_STOP_LOSS",
    "PAIR_API_TRADABLE_KEY",
    "PAIR_ASSET_INCREMENT_KEY",
    "PAIR_MAX_ORDER_SIZE_KEY",
    "PAIR_MIN_ORDER_AMOUNT_KEY",
    "PAIR_QUOTE_INCREMENT_KEY",
    "PAIR_SYMBOL_KEY",
    "PATH_UNPUBLISHED_FORMAT",
    "RATE_LIMIT_BURST_PER_MINUTE",
    "RATE_LIMIT_PER_MINUTE",
    "RATE_LIMIT_WINDOW_S",
    "SIZE_FIELD_UNITS",
    "TIMED_ORDER_TYPES",
    "TIME_IN_FORCE_GTC",
    "TRADING_HOST",
    "TRADING_PAIRS_PATH",
    "UNIFIED_PAIR_SEPARATOR",
    "UNLISTED_MARKET_FORMAT",
    "VENUE_DECIMAL_PLACES",
    "VENUE_ID",
    "VENUE_LABEL",
    "VENUE_ORDER_TYPES",
    "VENUE_PAIR_SEPARATOR",
    "VENUE_TIMES_IN_FORCE",
    "RobinhoodCryptoConnector",
    "RobinhoodOrderRefused",
    "RobinhoodPathUnpublished",
    "body_text",
    "client_order_uuid",
    "crypto_connector_class",
    "decimal_text",
    "hand_written_crypto_venues",
    "order_body",
    "orders_path",
    "pair_asset_class",
    "pair_asset_info",
    "pair_declared_order_types",
    "pair_number",
    "pair_rules",
    "pair_size_shapes",
    "pair_symbol",
    "signature",
    "signed_headers",
    "signed_message",
    "unified_symbol",
    "venue_order_type",
    "venue_symbol",
]
