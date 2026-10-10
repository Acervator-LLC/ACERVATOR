"""Hand-written :class:`ExchangeInterface` for Robinhood's crypto markets.

``order_body`` builds the venue's own order shape and ``signed_headers`` signs
it with an Ed25519 key. Robinhood's published OpenAPI document names 14 paths
on two API versions, and every read here but ``get_ohlcv`` reads one of them;
``pair_rules`` turns one trading-pair record into the ``MarketRules``
``BotContainer.guarded_place_order`` sizes against.
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

#: The trading-pair path carrying no fee tier, which Robinhood's OpenAPI
#: document names under Get Crypto Trading Pairs.
TRADING_PAIRS_PATH = "/api/v1/crypto/trading/trading_pairs/"

#: The trading-pair path carrying fee tiers, whose records alone name
#: ``PAIR_API_TRADABLE_KEY``.
TRADING_PAIRS_PATH_FEE_TIERS = "/api/v2/crypto/trading/trading_pairs/"

#: The best-price paths, published under Get Best Price on both versions. The
#: first answers a mid price with its two spreads and the second answers a bid
#: and an ask.
BEST_PRICE_PATH = "/api/v1/crypto/marketdata/best_bid_ask/"
BEST_PRICE_PATH_FEE_TIERS = "/api/v2/crypto/marketdata/best_bid_ask/"

#: The holdings paths, published under Get Crypto Holdings and Get Holdings.
HOLDINGS_PATH = "/api/v1/crypto/trading/holdings/"
HOLDINGS_PATH_FEE_TIERS = "/api/v2/crypto/trading/holdings/"

#: The cancel paths, which take the order id in the path and answer a string.
CANCEL_PATH_FORMAT = "/api/v1/crypto/trading/orders/{order_id}/cancel/"
CANCEL_PATH_FEE_TIERS_FORMAT = "/api/v2/crypto/trading/orders/{order_id}/cancel/"

#: The query parameters the read paths publish.
SYMBOL_QUERY_KEY = "symbol"
ASSET_CODE_QUERY_KEY = "asset_code"
ORDER_ID_QUERY_KEY = "id"
ORDER_STATE_QUERY_KEY = "state"

#: The order state the order list filters an open order under.
ORDER_STATE_OPEN = "open"

#: The keys one published holdings record carries.
HOLDING_ASSET_CODE_KEY = "asset_code"
HOLDING_TOTAL_KEY = "total_quantity"
HOLDING_AVAILABLE_KEY = "quantity_available_for_trading"

#: The keys the first version's best-price record carries. It publishes a mid
#: price and the two spread-inclusive prices, and no plain bid or ask.
PRICE_SYMBOL_KEY = "symbol"
PRICE_MID_KEY = "price"
PRICE_BID_INCLUSIVE_KEY = "bid_inclusive_of_sell_spread"
PRICE_ASK_INCLUSIVE_KEY = "ask_inclusive_of_buy_spread"

#: The keys the fee-tier version's best-price record carries.
PRICE_BID_KEY = "bid"
PRICE_ASK_KEY = "ask"

#: The quantity one level of a book built from a best-price record carries.
#: Robinhood defines a QuoteBook schema and publishes no path that answers one,
#: so no depth is published and a level carries no size.
BOOK_LEVEL_QUANTITY = 0.0


#: The keys one page of a paginated Robinhood list response carries.
PAGE_RESULTS_KEY = "results"
PAGE_NEXT_KEY = "next"

#: The pages one market read follows. Robinhood publishes no maximum page
#: size, so this is this reader's own loop guard and not a venue figure.
MAX_PAIR_PAGES = 50

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

#: Every order-configuration field the ``AddOrder`` request schema names, which
#: is the body ``ORDERS_PATH`` takes. Its limit configuration names no time in
#: force.
ADD_ORDER_CONFIG_FIELDS: dict[str, frozenset] = {
    ORDER_TYPE_MARKET: frozenset({"asset_quantity"}),
    ORDER_TYPE_LIMIT: frozenset({"quote_amount", "asset_quantity", "limit_price"}),
    ORDER_TYPE_STOP_LOSS: frozenset(
        {"quote_amount", "asset_quantity", "stop_price", "time_in_force"}
    ),
    ORDER_TYPE_STOP_LIMIT: frozenset(
        {"quote_amount", "asset_quantity", "limit_price", "stop_price", "time_in_force"}
    ),
}

#: Every order-configuration field the ``AddOrderV2`` request schema names,
#: which is the body ``ORDERS_PATH_FEE_TIERS`` takes. Its limit configuration
#: names a time in force where ``ADD_ORDER_CONFIG_FIELDS`` does not.
ADD_ORDER_V2_CONFIG_FIELDS: dict[str, frozenset] = {
    **ADD_ORDER_CONFIG_FIELDS,
    ORDER_TYPE_LIMIT: frozenset(
        {"quote_amount", "asset_quantity", "limit_price", "time_in_force"}
    ),
}

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
PAIR_ASSET_CODE_KEY = "asset_code"
PAIR_QUOTE_CODE_KEY = "quote_code"
PAIR_ASSET_INCREMENT_KEY = "asset_increment"
PAIR_QUOTE_INCREMENT_KEY = "quote_increment"
PAIR_MAX_ORDER_SIZE_KEY = "max_order_size"
PAIR_STATUS_KEY = "status"

#: The minimum the ``TRADING_PAIRS_PATH`` record names, in the base currency.
PAIR_MIN_ORDER_SIZE_KEY = "min_order_size"

#: The minimum the ``TRADING_PAIRS_PATH_FEE_TIERS`` record names, in the quote
#: currency.
PAIR_MIN_ORDER_AMOUNT_KEY = "min_order_amount"

#: Read only on a ``TRADING_PAIRS_PATH_FEE_TIERS`` record, whose publication
#: names it the flag for support on the fee-tier order path.
PAIR_API_TRADABLE_KEY = "is_api_tradable"

#: The keys both published trading-pair schemas name on every record, each as
#: a string.
PAIR_REQUIRED_KEYS = (
    PAIR_SYMBOL_KEY,
    PAIR_ASSET_CODE_KEY,
    PAIR_QUOTE_CODE_KEY,
    PAIR_ASSET_INCREMENT_KEY,
    PAIR_QUOTE_INCREMENT_KEY,
    PAIR_MAX_ORDER_SIZE_KEY,
    PAIR_STATUS_KEY,
)

#: The required keys carrying a decimal string an order is sized against.
PAIR_NUMERIC_KEYS = (
    PAIR_ASSET_INCREMENT_KEY,
    PAIR_QUOTE_INCREMENT_KEY,
    PAIR_MAX_ORDER_SIZE_KEY,
)

#: The three tradability statuses ``TRADING_PAIRS_PATH`` publishes as its
#: ``PAIR_STATUS_KEY`` enum. ``TRADING_PAIRS_PATH_FEE_TIERS`` names the same
#: field and publishes no enum for it.
STATUS_TRADABLE = "tradable"
STATUS_UNTRADABLE = "untradable"
STATUS_SELL_ONLY = "sellonly"
VENUE_PAIR_STATUSES = (STATUS_TRADABLE, STATUS_UNTRADABLE, STATUS_SELL_ONLY)

#: The requests a minute Robinhood publishes per account, and its burst figure.
RATE_LIMIT_PER_MINUTE = 100
RATE_LIMIT_BURST_PER_MINUTE = 300

#: The window ``RATE_LIMIT_PER_MINUTE`` is published over, in seconds.
RATE_LIMIT_WINDOW_S = 60.0

#: The namespace ``client_order_uuid`` derives a UUID under, so one trade
#: intent names one UUID.
CLIENT_ORDER_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")

#: Why a read refuses where Robinhood names an endpoint and publishes no path
#: for it. ``NO_CANDLE_PATH_FORMAT`` is the one case still reached.
PATH_UNPUBLISHED_FORMAT = (
    "Robinhood names a {endpoint} endpoint for crypto and publishes no path for "
    "it, so {asked} is not fetched and nothing is sent"
)

#: Why ``credential_refusal`` refuses with no API key typed.
NO_API_KEY = "no Robinhood API key is typed, so no request can be signed"

#: Why ``credential_refusal`` refuses a signing key ``signature`` cannot load.
SIGNING_KEY_REFUSED_FORMAT = (
    "the typed Robinhood private key is not an Ed25519 signing key: {error}"
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

#: Why an order refuses on a pair the venue takes no order on, which is still
#: read and still charted.
NOT_API_TRADABLE_FORMAT = (
    "Robinhood reads {key} False for {symbol}, and its order endpoint takes an "
    "order only on a symbol reading True"
)

#: Why an order refuses on a status the venue publishes as taking no order.
STATUS_UNTRADABLE_FORMAT = (
    "Robinhood reads {key} {status!r} for {symbol}, and a pair at that status "
    "takes no order on either side"
)

#: Why a buy refuses on the status the venue publishes as selling only.
STATUS_SELL_ONLY_FORMAT = (
    "Robinhood reads {key} {status!r} for {symbol}, so a sell is taken and a "
    "buy is not"
)

#: Why an order refuses on a status no published value names.
STATUS_UNNAMED_FORMAT = (
    "Robinhood reads {key} {status!r} for {symbol}, which is none of the "
    "published statuses {published}, so nothing published says what it permits"
)

#: Why a market read refuses with no credential stored.
NO_CREDENTIAL_FOR_READ = (
    "no Robinhood API key and no Ed25519 private key are stored, so the "
    "trading-pair request cannot be signed and no market list is read"
)

#: Why a market read refuses on a reply departing from the published shape.
UNEXPECTED_RESPONSE_FORMAT = (
    "{path} is published to answer {expected} and answered {got}, so no "
    "market list is built from it"
)

#: Why a market read refuses on a page naming a next page and serving nothing.
EMPTY_PROMISED_PAGE_FORMAT = (
    "{path} answered 0 record(s) beside a {key} naming a further page, so a "
    "page the venue promised served none"
)

#: Why a market read refuses on a next page outside ``TRADING_HOST``.
FOREIGN_NEXT_HOST_FORMAT = (
    "{path} answered a {key} of {held!r}, which does not begin with "
    "{host}, and a signed request is sent to no other host"
)

#: Why a market read refuses where the pages outrun ``MAX_PAIR_PAGES``.
PAGES_EXHAUSTED_FORMAT = (
    "{path} served {pages} page(s) and still named a {key}, so the read stops "
    "short of an unbounded chain"
)

#: Why a market read refuses on an unfiltered reply serving no record.
NO_PAIR_SERVED_FORMAT = (
    "{path} is published to answer all tradable currency pairs where no "
    "symbol filter is sent, and answered 0 record(s)"
)

#: Why a market read refuses on a record missing a published key.
MISSING_PAIR_KEY_FORMAT = (
    "{path} record {index} names no {key} as a string, and every published "
    "trading-pair schema carries one; the record names {held}"
)

#: Why a market read refuses on a published decimal that is not a number.
UNPARSED_PAIR_NUMBER_FORMAT = (
    "{path} record {index} for {symbol} reads {key} {held!r}, which is not a "
    "positive decimal an order can be sized against"
)

#: Why a read refuses on a reply naming no record for the symbol asked for.
NO_RECORD_FOR_SYMBOL_FORMAT = (
    "{path} answered {held} record(s) and none names {symbol}, so no {asked} "
    "is read for it"
)

#: Why a read refuses on a record missing a key its published schema names.
MISSING_RECORD_KEY_FORMAT = (
    "{path} record for {symbol} names no {key}, and its published schema "
    "carries one; the record names {names}"
)

#: Why a candle read refuses. Robinhood's published document names 14 paths
#: and no candle path, and the public reader behind this serves three
#: granularities.
NO_CANDLE_PATH_FORMAT = (
    "Robinhood publishes no candle path, and the public candle reader behind "
    "this serves {served} and not {timeframe}"
)

#: Why an order refuses on a body naming a field its path's schema omits.
UNPUBLISHED_ORDER_FIELD_FORMAT = (
    "a {kind} order body for {path} names {fields}, which its published "
    "request schema does not carry, so the body is not sent"
)


class RobinhoodPathUnpublished(RuntimeError):
    """Raised where Robinhood names an endpoint and publishes no path for it."""


class RobinhoodOrderRefused(RuntimeError):
    """Raised where this connector refuses an order before any request."""


class RobinhoodReadRefused(RuntimeError):
    """Raised where this connector refuses a read before any request."""


class RobinhoodResponseUnexpected(RuntimeError):
    """Raised where a Robinhood reply departs from its published shape.

    ``get_markets`` raises this in place of answering a market whose size
    rule the reply did not carry.
    """


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


def trading_pairs_path(account_number: Any = None) -> str:
    """The trading-pair path one market read takes.

    ``TRADING_PAIRS_PATH_FEE_TIERS`` where an account number is held, matching
    the path ``orders_path`` then submits on, and ``TRADING_PAIRS_PATH`` where
    none is.
    """
    if not str(account_number or "").strip():
        return TRADING_PAIRS_PATH
    return TRADING_PAIRS_PATH_FEE_TIERS


def query_string(pairs: Any) -> str:
    """One query string from ``pairs``, and empty for no pair.

    A repeated key rides once per value, the shape Robinhood publishes for
    ``SYMBOL_QUERY_KEY`` and ``ASSET_CODE_QUERY_KEY``.
    """
    held = [
        f"{key}={value}"
        for key, value in (pairs or ())
        if str(value or "").strip() != ""
    ]
    return f"?{'&'.join(held)}" if held else ""


def best_price_path(account_number: Any = None, symbols: Any = ()) -> str:
    """The best-price path one price read takes, with every symbol of
    ``symbols`` under ``SYMBOL_QUERY_KEY``.

    The fee-tier version where an account number is held, matching the version
    ``orders_path`` submits on.
    """
    base = (
        BEST_PRICE_PATH_FEE_TIERS
        if str(account_number or "").strip()
        else BEST_PRICE_PATH
    )
    return base + query_string(
        [(SYMBOL_QUERY_KEY, venue_symbol(one)) for one in symbols or ()]
    )


def holdings_path(account_number: Any = None, asset_codes: Any = ()) -> str:
    """The holdings path one balance read takes, with every code of
    ``asset_codes`` under ``ASSET_CODE_QUERY_KEY``.

    The fee-tier version takes ``ACCOUNT_QUERY_KEY`` as a published required
    parameter, and the first version takes none.
    """
    held = str(account_number or "").strip()
    pairs = [
        (ASSET_CODE_QUERY_KEY, str(one or "").upper()) for one in asset_codes or ()
    ]
    if not held:
        return HOLDINGS_PATH + query_string(pairs)
    return HOLDINGS_PATH_FEE_TIERS + query_string([(ACCOUNT_QUERY_KEY, held), *pairs])


def order_list_path(account_number: Any = None, filters: Any = ()) -> str:
    """The order-list path one order read takes, with each pair of ``filters``
    as a published query parameter.

    The same two paths ``orders_path`` submits on, read with ``GET``.
    """
    held = str(account_number or "").strip()
    if not held:
        return ORDERS_PATH + query_string(filters)
    return ORDERS_PATH_FEE_TIERS + query_string(
        [(ACCOUNT_QUERY_KEY, held), *(filters or ())]
    )


def cancel_path(order_id: Any, account_number: Any = None) -> str:
    """The cancel path for ``order_id``, which the venue takes in the path.

    The fee-tier version where an account number is held, matching the version
    ``orders_path`` submits on.
    """
    held = str(account_number or "").strip()
    chosen = CANCEL_PATH_FEE_TIERS_FORMAT if held else CANCEL_PATH_FORMAT
    return chosen.format(order_id=str(order_id or "").strip())


def published_order_config_fields(path: Any, kind: Any) -> frozenset:
    """Every configuration field the request schema of ``path`` names for
    ``kind``.

    ``ADD_ORDER_V2_CONFIG_FIELDS`` for the fee-tier path and
    ``ADD_ORDER_CONFIG_FIELDS`` for the first version.
    """
    held = str(path or "")
    source = (
        ADD_ORDER_V2_CONFIG_FIELDS
        if held.startswith(ORDERS_PATH_FEE_TIERS)
        else ADD_ORDER_CONFIG_FIELDS
    )
    return source.get(str(kind), frozenset())


def order_body_refusal(body: Any, path: Any) -> str:
    """Why ``body`` names a configuration field the request schema of ``path``
    does not publish, and empty where every field is published.

    ``ORDERS_PATH`` takes ``AddOrder``, whose limit configuration names no time
    in force, and ``ORDERS_PATH_FEE_TIERS`` takes ``AddOrderV2``, whose limit
    configuration does.
    """
    if not isinstance(body, dict):
        return ""
    kind = str(body.get("type") or "")
    config = body.get(ORDER_CONFIG_KEYS.get(kind, ""), None)
    if not isinstance(config, dict):
        return ""
    unpublished = set(config) - set(published_order_config_fields(path, kind))
    if not unpublished:
        return ""
    return UNPUBLISHED_ORDER_FIELD_FORMAT.format(
        kind=kind, path=path, fields=sorted(unpublished)
    )


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


def price_bid_ask(record: Any) -> tuple:
    """The bid and the ask one published best-price record names.

    The fee-tier record names ``PRICE_BID_KEY`` and ``PRICE_ASK_KEY``, and the
    first version's record names the two spread-inclusive prices instead.
    """
    if not isinstance(record, dict):
        return (None, None)
    bid = pair_number(record.get(PRICE_BID_KEY))
    ask = pair_number(record.get(PRICE_ASK_KEY))
    if bid is None:
        bid = pair_number(record.get(PRICE_BID_INCLUSIVE_KEY))
    if ask is None:
        ask = pair_number(record.get(PRICE_ASK_INCLUSIVE_KEY))
    return (bid, ask)


def price_ticker(record: Any, symbol: str, moment_s: float) -> Ticker:
    """One ``Ticker`` from one published best-price record.

    ``last`` is ``PRICE_MID_KEY`` where the record names it and the midpoint of
    the bid and the ask otherwise, and ``volume_24h`` is zero because neither
    best-price schema publishes a volume.
    """
    bid, ask = price_bid_ask(record)
    if bid is None or ask is None:
        raise RobinhoodResponseUnexpected(
            MISSING_RECORD_KEY_FORMAT.format(
                path=BEST_PRICE_PATH,
                symbol=symbol,
                key=f"{PRICE_BID_KEY}/{PRICE_ASK_KEY} nor "
                f"{PRICE_BID_INCLUSIVE_KEY}/{PRICE_ASK_INCLUSIVE_KEY}",
                names=sorted(record) if isinstance(record, dict) else record,
            )
        )
    mid = pair_number(record.get(PRICE_MID_KEY)) or (bid + ask) / 2.0
    return Ticker(
        symbol=symbol,
        bid=bid,
        ask=ask,
        last=mid,
        volume_24h=0.0,
        timestamp=moment_s,
    )


def price_orderbook(record: Any, symbol: str, moment_s: float) -> OrderBook:
    """One ``OrderBook`` of one level from one published best-price record.

    Robinhood defines a ``QuoteBook`` schema and publishes no path that answers
    one, so each level carries ``BOOK_LEVEL_QUANTITY`` and no depth.
    """
    bid, ask = price_bid_ask(record)
    held = price_ticker(record, symbol, moment_s)
    return OrderBook(
        symbol=symbol,
        bids=[(held.bid, BOOK_LEVEL_QUANTITY)] if bid is not None else [],
        asks=[(held.ask, BOOK_LEVEL_QUANTITY)] if ask is not None else [],
        timestamp=moment_s,
    )


def holding_balance(record: Any) -> Optional[Balance]:
    """One ``Balance`` from one published holdings record.

    None for a record naming no ``HOLDING_ASSET_CODE_KEY``, and ``used`` is the
    total less the quantity the venue publishes as available for trading.
    """
    if not isinstance(record, dict):
        return None
    currency = str(record.get(HOLDING_ASSET_CODE_KEY) or "").strip().upper()
    if not currency:
        return None
    total = pair_number(record.get(HOLDING_TOTAL_KEY)) or 0.0
    free = pair_number(record.get(HOLDING_AVAILABLE_KEY)) or 0.0
    return Balance(
        currency=currency,
        free=free,
        used=max(total - free, 0.0),
        total=total,
        absent=False,
    )


def pair_status(pair: Any) -> str:
    """The tradability status one published trading-pair record names, lower
    case.

    Empty for a record naming no ``PAIR_STATUS_KEY`` string.
    """
    if not isinstance(pair, dict):
        return ""
    held = pair.get(PAIR_STATUS_KEY)
    if type(held) is not str:
        return ""
    return held.strip().lower()


def status_order_refusal(pair: Any, side: Any) -> str:
    """Why the published ``PAIR_STATUS_KEY`` refuses one order on ``pair``.

    ``STATUS_TRADABLE`` refuses nothing, ``STATUS_SELL_ONLY`` refuses a buy,
    ``STATUS_UNTRADABLE`` refuses both sides, and a status outside
    ``VENUE_PAIR_STATUSES`` refuses both sides.
    """
    status = pair_status(pair)
    symbol = pair_symbol(pair) or str(pair)
    if status == STATUS_TRADABLE:
        return ""
    fields = {"key": PAIR_STATUS_KEY, "status": status, "symbol": symbol}
    if status == STATUS_SELL_ONLY:
        if OrderSide(side) == OrderSide.SELL:
            return ""
        return STATUS_SELL_ONLY_FORMAT.format(**fields)
    if status == STATUS_UNTRADABLE:
        return STATUS_UNTRADABLE_FORMAT.format(**fields)
    return STATUS_UNNAMED_FORMAT.format(published=VENUE_PAIR_STATUSES, **fields)


def pair_record_refusal(record: Any, index: Any, path: str) -> str:
    """Why one record of ``path`` departs from the published trading-pair
    schema.

    Empty where every ``PAIR_REQUIRED_KEYS`` key carries a string and every
    ``PAIR_NUMERIC_KEYS`` key carries a positive decimal.
    """
    if not isinstance(record, dict):
        return UNEXPECTED_RESPONSE_FORMAT.format(
            path=path,
            expected=f"{PAGE_RESULTS_KEY}[{index}] as an object",
            got=type(record).__name__,
        )
    for key in PAIR_REQUIRED_KEYS:
        if type(record.get(key)) is not str:
            return MISSING_PAIR_KEY_FORMAT.format(
                path=path, index=index, key=key, held=sorted(record)
            )
    for key in PAIR_NUMERIC_KEYS:
        if pair_number(record.get(key)) is None:
            return UNPARSED_PAIR_NUMBER_FORMAT.format(
                path=path,
                index=index,
                symbol=pair_symbol(record),
                key=key,
                held=record.get(key),
            )
    return ""


def page_records(raw: Any, path: str) -> list[dict]:
    """Every trading-pair record one page of ``path`` carries under
    ``PAGE_RESULTS_KEY``.

    ``RobinhoodResponseUnexpected`` names the key and the type where
    ``page_list`` refuses the page or where ``pair_record_refusal`` reads a
    member.
    """
    held = page_list(raw, path)
    for index, record in enumerate(held):
        refusal = pair_record_refusal(record, index, path)
        if refusal:
            raise RobinhoodResponseUnexpected(refusal)
    return held


def order_from_record(record: Any) -> Order:
    """One ``Order`` from one published order record.

    The amount rides inside the configuration object the record's type names,
    and a state outside the published enum reads ``OrderStatus.OPEN``.
    """
    held = record if isinstance(record, dict) else {}
    status_map = {
        "open": OrderStatus.OPEN,
        "filled": OrderStatus.FILLED,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "canceled": OrderStatus.CANCELLED,
        "cancelled": OrderStatus.CANCELLED,
        "failed": OrderStatus.FAILED,
        "rejected": OrderStatus.FAILED,
    }
    kind = str(held.get("type") or ORDER_TYPE_LIMIT)
    config = held.get(ORDER_CONFIG_KEYS.get(kind, ""), None)
    config = config if isinstance(config, dict) else {}
    amount = pair_number(config.get(SIZE_FIELD_UNITS)) or 0.0
    filled = pair_number(held.get("filled_asset_quantity")) or 0.0
    return Order(
        id=str(held.get("id") or ""),
        symbol=unified_symbol(held.get("symbol")),
        side=OrderSide(str(held.get("side") or OrderSide.BUY.value)),
        type=OrderType.MARKET if kind == ORDER_TYPE_MARKET else OrderType.LIMIT,
        amount=amount,
        price=pair_number(config.get("limit_price")) or 0.0,
        filled=filled,
        remaining=max(amount - filled, 0.0),
        status=status_map.get(str(held.get("state") or ""), OrderStatus.OPEN),
        average=pair_number(held.get("average_price")) or 0.0,
        raw=held,
    )


def page_list(raw: Any, path: str) -> list[dict]:
    """Every record one page of ``path`` carries under ``PAGE_RESULTS_KEY``.

    ``RobinhoodResponseUnexpected`` names the key and the type where the page
    is not an object, where it carries no array under ``PAGE_RESULTS_KEY``, or
    where a member is not an object.
    """
    if not isinstance(raw, dict):
        raise RobinhoodResponseUnexpected(
            UNEXPECTED_RESPONSE_FORMAT.format(
                path=path,
                expected=f"an object naming {PAGE_RESULTS_KEY!r}",
                got=type(raw).__name__,
            )
        )
    held = raw.get(PAGE_RESULTS_KEY)
    if not isinstance(held, list):
        raise RobinhoodResponseUnexpected(
            UNEXPECTED_RESPONSE_FORMAT.format(
                path=path,
                expected=f"{PAGE_RESULTS_KEY!r} as an array",
                got=(
                    f"the keys {sorted(raw)}"
                    if PAGE_RESULTS_KEY not in raw
                    else type(held).__name__
                ),
            )
        )
    for index, record in enumerate(held):
        if not isinstance(record, dict):
            raise RobinhoodResponseUnexpected(
                UNEXPECTED_RESPONSE_FORMAT.format(
                    path=path,
                    expected=f"{PAGE_RESULTS_KEY}[{index}] as an object",
                    got=type(record).__name__,
                )
            )
    return list(held)


def page_next_path(raw: Any, path: str, records: Any) -> str:
    """The path the published ``PAGE_NEXT_KEY`` URI of one page names.

    Empty where the page names no further page, and
    ``RobinhoodResponseUnexpected`` where ``PAGE_NEXT_KEY`` is neither null nor
    a ``TRADING_HOST`` URI, or where a page naming one served no record.
    """
    held = raw.get(PAGE_NEXT_KEY) if isinstance(raw, dict) else None
    if held is None or held == "":
        return ""
    if type(held) is not str:
        raise RobinhoodResponseUnexpected(
            UNEXPECTED_RESPONSE_FORMAT.format(
                path=path,
                expected=f"{PAGE_NEXT_KEY!r} as a URI or null",
                got=type(held).__name__,
            )
        )
    if not held.startswith(TRADING_HOST):
        raise RobinhoodResponseUnexpected(
            FOREIGN_NEXT_HOST_FORMAT.format(
                path=path, key=PAGE_NEXT_KEY, held=held, host=TRADING_HOST
            )
        )
    if not records:
        raise RobinhoodResponseUnexpected(
            EMPTY_PROMISED_PAGE_FORMAT.format(path=path, key=PAGE_NEXT_KEY)
        )
    return held[len(TRADING_HOST) :]


def pair_declared_order_types() -> str:
    """The order types Robinhood declares for every crypto pair.

    ``VENUE_ORDER_TYPES`` holds ``ORDER_TYPE_MARKET`` beside
    ``ORDER_TYPE_LIMIT``, and no pair record narrows it.
    """
    from ..trading.scrumming.sizing import ORDER_TYPES_WITH_MARKET

    return ORDER_TYPES_WITH_MARKET


def pair_size_shapes() -> frozenset:
    """The size shapes a Robinhood crypto order may name on either side.

    The market configuration of ``ADD_ORDER_CONFIG_FIELDS`` names
    ``SIZE_FIELD_UNITS`` alone and carries no quote amount, so units is the one
    shape every type of ``pair_declared_order_types`` publishes.
    """
    from ..trading.scrumming.sizing import SHAPE_FRACTIONAL_UNITS

    return frozenset({SHAPE_FRACTIONAL_UNITS})


def pair_rules(pair: Any) -> MarketRules:
    """The ``MarketRules`` one published trading-pair record publishes.

    ``read`` is False for a non-record, for a pair ``PAIR_API_TRADABLE_KEY``
    reads False on, and for a status ``STATUS_TRADABLE`` and
    ``STATUS_SELL_ONLY`` do not name; a rule the record does not name is None.
    """
    if not isinstance(pair, dict):
        return MarketRules(read=False)
    if pair.get(PAIR_API_TRADABLE_KEY) is False:
        return MarketRules(read=False)
    if pair_status(pair) not in (STATUS_TRADABLE, STATUS_SELL_ONLY):
        return MarketRules(read=False)
    shapes = pair_size_shapes()
    return MarketRules(
        amount_increment=pair_number(pair.get(PAIR_ASSET_INCREMENT_KEY)),
        # Published as the minimum price increment of the quote currency, which
        # a limit price steps by and a cash amount steps by alike.
        price_increment=pair_number(pair.get(PAIR_QUOTE_INCREMENT_KEY)),
        quote_increment=pair_number(pair.get(PAIR_QUOTE_INCREMENT_KEY)),
        # TRADING_PAIRS_PATH publishes a minimum in the base currency and
        # TRADING_PAIRS_PATH_FEE_TIERS one in the quote currency, and no record
        # carries both.
        min_amount=pair_number(pair.get(PAIR_MIN_ORDER_SIZE_KEY)),
        min_cost=pair_number(pair.get(PAIR_MIN_ORDER_AMOUNT_KEY)),
        order_types=pair_declared_order_types(),
        buy_size_shapes=shapes,
        sell_size_shapes=shapes,
    )


def pair_asset_class(pair: Any = None) -> str:
    """The sector one published trading-pair record belongs to.

    Every pair ``record_pairs`` holds is a crypto pair. Robinhood's equity
    route is the Trading MCP at ``agent.robinhood.com/mcp/trading``, which
    takes an OAuth bearer token issued for a Robinhood MCP account, and no
    module in this tree holds one.
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
    split_base, _, split_quote = symbol.partition(UNIFIED_PAIR_SEPARATOR)
    return AssetInfo(
        symbol=symbol,
        base=venue_symbol(pair.get(PAIR_ASSET_CODE_KEY)) or split_base,
        quote=venue_symbol(pair.get(PAIR_QUOTE_CODE_KEY)) or split_quote,
        rules=pair_rules(pair),
        # A pair record publishes no fee, so AssetInfo carries zero.
        maker_fee=0.0,
        taker_fee=0.0,
        active=(
            pair.get(PAIR_API_TRADABLE_KEY) is not False
            and pair_status(pair) != STATUS_UNTRADABLE
        ),
    )


class RobinhoodCryptoConnector(ExchangeInterface):
    """Robinhood's crypto markets behind the contract every bot's order path
    reads.

    ``place_order`` signs the venue's own body and hands it to ``_send``, and
    every read but ``get_ohlcv`` signs a published path through the same
    transport. ``get_ohlcv`` reads ``CoinbasePublicCandles``, because
    Robinhood's published document names no candle path.
    """

    def __init__(self, exchange_id: str = VENUE_ID) -> None:
        self._exchange_id = str(exchange_id or VENUE_ID)
        self._api_key = ""
        self._private_key_b64 = ""
        self._account_number = ""
        self._connected = False
        self._pairs: dict[str, dict] = {}
        self._markets_cache: Optional[list[AssetInfo]] = None
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
        self._markets_cache = None
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

    @staticmethod
    def credential_refusal(api_key: str, api_secret: str, phrase: str) -> str:
        """Why these credentials cannot sign a Robinhood request, empty where
        they can.

        ``signature`` loads ``api_secret`` as the base64 Ed25519 seed and names
        a seed it refuses, and no venue is contacted.
        """
        del phrase
        if not api_key:
            return NO_API_KEY
        try:
            signature(api_secret, api_key, 0, ORDERS_PATH, "GET")
        except ValueError as exc:
            return str(exc)
        except Exception as exc:  # the reader names what it could not load
            return SIGNING_KEY_REFUSED_FORMAT.format(error=exc)
        return ""

    async def disconnect(self) -> None:
        """Drop the credential, close any session, and make ``is_connected``
        False."""
        self._connected = False
        self._api_key = ""
        self._private_key_b64 = ""
        self._markets_cache = None
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as exc:
                logger.warning("%s session already closed: %s", VENUE_LABEL, exc)
            self._session = None

    def record_pairs(self, pairs: Iterable[Any]) -> list[AssetInfo]:
        """Hold every published trading-pair record of ``pairs`` and record its
        rules under ``exchange_id``, answering one ``AssetInfo`` per market.

        No venue is contacted, a record naming no symbol or a status outside
        ``STATUS_TRADABLE`` and ``STATUS_SELL_ONLY`` is skipped, and only a
        market whose ``MarketRules`` ``read`` is True reaches ``record_venue``.
        """
        built: list[AssetInfo] = []
        held: dict[str, dict] = {}
        classes: dict[str, str] = {}
        skipped: list[str] = []
        for pair in pairs:
            info = pair_asset_info(pair)
            if info is None:
                continue
            status = pair_status(pair)
            if status not in (STATUS_TRADABLE, STATUS_SELL_ONLY):
                skipped.append(f"{info.symbol} {status!r}")
                continue
            held[info.symbol] = dict(pair)
            classes[info.symbol] = pair_asset_class(pair)
            built.append(info)
        if skipped:
            # A skipped symbol holds no record, so place_order refuses it under
            # UNLISTED_MARKET_FORMAT.
            logger.warning(
                "%s named %d pair(s) at a %s outside %s, which are not listed: " "%s",
                VENUE_LABEL,
                len(skipped),
                PAIR_STATUS_KEY,
                (STATUS_TRADABLE, STATUS_SELL_ONLY),
                ", ".join(skipped),
            )
        if not built:
            logger.warning(
                "%s served no tradable trading-pair record, so no market rule "
                "row is recorded",
                VENUE_LABEL,
            )
            return built
        self._pairs.update(held)
        self._markets_cache = list(built)
        # The Simulator and the Paper Trader reach no venue, so the rules read
        # here are recorded once per read for them to size an order by. A
        # market whose rules went unread records no row, because a recorded row
        # reads back as read=True whatever it holds.
        recorded = [info for info in built if info.rules.read]
        try:
            record_venue(self._exchange_id, recorded, classes=classes)
        except OSError as exc:
            logger.warning(
                "market rules for %s not recorded: %s", self._exchange_id, exc
            )
        return built

    async def get_markets(self) -> list[AssetInfo]:
        """One ``AssetInfo`` per trading pair Robinhood publishes for this
        venue.

        ``trading_pairs_path`` is read once and every page of it followed, the
        records reach ``record_pairs``, and a later call answers the list it
        built.
        """
        if self._markets_cache is not None:
            return self._markets_cache
        if self._pairs:
            return self.record_pairs(list(self._pairs.values()))
        if not self._api_key or not self._private_key_b64:
            raise RobinhoodReadRefused(NO_CREDENTIAL_FOR_READ)
        return self.record_pairs(await self._fetch_pairs())

    async def _fetch_pairs(self) -> list[dict]:
        """Every trading-pair record ``trading_pairs_path`` serves, following
        each page the published ``PAGE_NEXT_KEY`` names.

        ``RobinhoodResponseUnexpected`` names what was expected and what
        arrived where a page departs from the published shape, where the first
        page serves no record, and where the chain outruns ``MAX_PAIR_PAGES``.
        """
        from .api_logger import get_api_log

        first = trading_pairs_path(self._account_number)
        held = await self._read_pages(first, reader=page_records)
        if not held:
            raise RobinhoodResponseUnexpected(NO_PAIR_SERVED_FORMAT.format(path=first))
        get_api_log().record(
            exchange=self._exchange_id,
            action="GET_MARKETS",
            reason=f"Read the {VENUE_LABEL} trading pairs",
            endpoint=first,
            params={"records": len(held)},
            result=f"{len(held)} trading pair record(s)",
            level="info",
            data_usage="Recorded market rules size every later order on this venue",
        )
        return held

    async def _read(self, path: str) -> Any:
        """Send one signed GET to ``path`` and answer the JSON it replies.

        ``signed_headers`` signs the path with its query string and no body,
        the shape Robinhood's own published sample signs a read under.
        """
        headers = signed_headers(self._api_key, self._private_key_b64, path, "GET", "")
        await self._pace()
        return await self._send("GET", path, "", headers)

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
        if self._pairs[named].get(PAIR_API_TRADABLE_KEY) is False:
            refusal = NOT_API_TRADABLE_FORMAT.format(
                key=PAIR_API_TRADABLE_KEY, symbol=named
            )
            self._record_refusal(log, symbol, side, order_type, amount, refusal)
            raise RobinhoodOrderRefused(refusal)
        refusal = status_order_refusal(self._pairs[named], side)
        if refusal:
            self._record_refusal(log, symbol, side, order_type, amount, refusal)
            raise RobinhoodOrderRefused(refusal)
        try:
            body = order_body(symbol, side, order_type, amount, price, client_order_id)
        except (RobinhoodOrderRefused, ValueError) as exc:
            self._record_refusal(log, symbol, side, order_type, amount, str(exc))
            raise
        path = orders_path(self._account_number)
        unpublished = order_body_refusal(body, path)
        if unpublished:
            self._record_refusal(log, symbol, side, order_type, amount, unpublished)
            raise RobinhoodOrderRefused(unpublished)
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

    async def _read_pages(
        self, path: str, reader: Any = None, cap: int = MAX_PAIR_PAGES
    ) -> list[dict]:
        """Every record ``path`` serves, following each page the published
        ``PAGE_NEXT_KEY`` names.

        ``reader`` reads one page's records and defaults to ``page_list``, and
        ``RobinhoodResponseUnexpected`` names what was expected where a page
        departs from the published shape or the chain outruns ``cap``.
        """
        read_page = reader or page_list
        first = path
        held: list[dict] = []
        for _ in range(cap):
            raw = await self._read(path)
            records = read_page(raw, path)
            held.extend(records)
            following = page_next_path(raw, path, records)
            if not following:
                return held
            path = following
        raise RobinhoodResponseUnexpected(
            PAGES_EXHAUSTED_FORMAT.format(path=first, pages=cap, key=PAGE_NEXT_KEY)
        )

    def _signing_refusal(self, asked: str) -> str:
        """Why no request can be signed, and empty where one can."""
        if self._api_key and self._private_key_b64:
            return ""
        return f"{NO_CREDENTIAL} and {asked} is not read"

    async def _best_price_record(self, symbol: str) -> dict:
        """The published best-price record ``symbol`` names.

        ``RobinhoodReadRefused`` with no credential stored, and
        ``RobinhoodResponseUnexpected`` where the reply names no record for it.
        """
        named = unified_symbol(symbol)
        refusal = self._signing_refusal(f"a price for {named or symbol}")
        if refusal:
            raise RobinhoodReadRefused(refusal)
        path = best_price_path(self._account_number, [named])
        records = await self._read_pages(path)
        for record in records:
            if unified_symbol(record.get(PRICE_SYMBOL_KEY)) == named:
                return record
        raise RobinhoodResponseUnexpected(
            NO_RECORD_FOR_SYMBOL_FORMAT.format(
                path=path, held=len(records), symbol=named, asked="price"
            )
        )

    async def get_ticker(self, symbol: str) -> Ticker:
        """The ``Ticker`` Robinhood's published best-price path answers for
        ``symbol``.

        ``volume_24h`` is zero because neither published best-price schema
        names a volume.
        """
        record = await self._best_price_record(symbol)
        return price_ticker(record, unified_symbol(symbol), time.time())

    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        """The one-level ``OrderBook`` Robinhood's published best-price path
        answers for ``symbol``.

        ``limit`` is unread, and Robinhood publishes no path answering its own
        ``QuoteBook`` depth schema.
        """
        del limit
        record = await self._best_price_record(symbol)
        return price_orderbook(record, unified_symbol(symbol), time.time())

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: Optional[int] = None,
    ) -> list[list[float]]:
        """The candle rows the public Coinbase reader answers for ``symbol``.

        Robinhood's published document names 14 paths and no candle path, so
        ``CoinbasePublicCandles`` is the source and a timeframe it does not
        serve raises ``RobinhoodPathUnpublished``.
        """
        from ..trading.stone_tablets.ra_fetcher import CoinbasePublicCandles

        reader = CoinbasePublicCandles()
        if timeframe not in reader.GRANULARITY_S:
            raise RobinhoodPathUnpublished(
                NO_CANDLE_PATH_FORMAT.format(
                    served=sorted(reader.GRANULARITY_S), timeframe=timeframe
                )
            )
        return await reader.get_ohlcv(symbol, timeframe, limit, since)

    async def get_balances(self) -> dict[str, Balance]:
        """Every ``Balance`` Robinhood's published holdings path answers,
        keyed by currency.

        ``RobinhoodReadRefused`` with no credential stored, and a record naming
        no asset code is skipped.
        """
        refusal = self._signing_refusal("a balance")
        if refusal:
            raise RobinhoodReadRefused(refusal)
        records = await self._read_pages(holdings_path(self._account_number))
        held: dict[str, Balance] = {}
        for record in records:
            balance = holding_balance(record)
            if balance is not None:
                held[balance.currency] = balance
        return held

    async def get_balance(self, currency: str) -> Balance:
        """The ``Balance`` Robinhood's published holdings path answers for
        ``currency``.

        ``absent`` is True where the reply names no record for it, the same
        unknown ``Balance`` carries for a currency the venue omitted.
        """
        refusal = self._signing_refusal(f"a balance for {currency}")
        if refusal:
            raise RobinhoodReadRefused(refusal)
        named = str(currency or "").strip().upper()
        records = await self._read_pages(holdings_path(self._account_number, [named]))
        for record in records:
            balance = holding_balance(record)
            if balance is not None and balance.currency == named:
                return balance
        return Balance(currency=named, free=0.0, used=0.0, total=0.0, absent=True)

    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        """Cancel ``order_id`` through Robinhood's published cancel path and
        answer the order it then reads.

        The cancel answers a string naming the order, so the ``Order`` comes
        from ``get_order`` after it.
        """
        refusal = self._signing_refusal(f"a cancel of {order_id}")
        if refusal:
            raise RobinhoodReadRefused(refusal)
        path = cancel_path(order_id, self._account_number)
        headers = signed_headers(self._api_key, self._private_key_b64, path, "POST", "")
        await self._pace()
        await self._send("POST", path, "", headers)
        return await self.get_order(order_id, symbol)

    async def get_order(self, order_id: str, symbol: str) -> Order:
        """The ``Order`` Robinhood's published order list answers for
        ``order_id``.

        The list takes ``ORDER_ID_QUERY_KEY`` as a published filter, and
        ``RobinhoodResponseUnexpected`` where the reply names no record for it.
        """
        del symbol
        refusal = self._signing_refusal(f"order {order_id}")
        if refusal:
            raise RobinhoodReadRefused(refusal)
        named = str(order_id or "").strip()
        path = order_list_path(self._account_number, [(ORDER_ID_QUERY_KEY, named)])
        records = await self._read_pages(path)
        for record in records:
            if str(record.get("id") or "") == named:
                return order_from_record(record)
        raise RobinhoodResponseUnexpected(
            NO_RECORD_FOR_SYMBOL_FORMAT.format(
                path=path, held=len(records), symbol=named, asked="order"
            )
        )

    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        """Every open ``Order`` Robinhood's published order list answers.

        The list takes ``ORDER_STATE_QUERY_KEY`` and ``SYMBOL_QUERY_KEY`` as
        published filters, and ``symbol`` rides as the second where it is held.
        """
        refusal = self._signing_refusal("the open orders")
        if refusal:
            raise RobinhoodReadRefused(refusal)
        filters = [(ORDER_STATE_QUERY_KEY, ORDER_STATE_OPEN)]
        named = venue_symbol(symbol)
        if named:
            filters.append((SYMBOL_QUERY_KEY, named))
        records = await self._read_pages(order_list_path(self._account_number, filters))
        return [order_from_record(record) for record in records]

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
    "ADD_ORDER_CONFIG_FIELDS",
    "ADD_ORDER_V2_CONFIG_FIELDS",
    "ASSET_CODE_QUERY_KEY",
    "BEST_PRICE_PATH",
    "BEST_PRICE_PATH_FEE_TIERS",
    "BOOK_LEVEL_QUANTITY",
    "CANCEL_PATH_FEE_TIERS_FORMAT",
    "CANCEL_PATH_FORMAT",
    "CLIENT_ORDER_NAMESPACE",
    "CRYPTO_CONNECTORS",
    "EMPTY_PROMISED_PAGE_FORMAT",
    "FOREIGN_NEXT_HOST_FORMAT",
    "HEADER_API_KEY",
    "HEADER_SIGNATURE",
    "HEADER_TIMESTAMP",
    "HOLDINGS_PATH",
    "HOLDINGS_PATH_FEE_TIERS",
    "HOLDING_ASSET_CODE_KEY",
    "HOLDING_AVAILABLE_KEY",
    "HOLDING_TOTAL_KEY",
    "MAX_PAIR_PAGES",
    "MISSING_PAIR_KEY_FORMAT",
    "MISSING_RECORD_KEY_FORMAT",
    "NOT_API_TRADABLE_FORMAT",
    "NO_API_KEY",
    "NO_CANDLE_PATH_FORMAT",
    "NO_CREDENTIAL",
    "NO_CREDENTIAL_FOR_READ",
    "NO_IMMEDIATE_OR_CANCEL",
    "NO_PAIR_SERVED_FORMAT",
    "NO_RECORD_FOR_SYMBOL_FORMAT",
    "ORDERS_PATH",
    "ORDERS_PATH_FEE_TIERS",
    "ORDER_CONFIG_KEYS",
    "ORDER_ID_QUERY_KEY",
    "ORDER_STATE_OPEN",
    "ORDER_STATE_QUERY_KEY",
    "ORDER_TYPE_LIMIT",
    "ORDER_TYPE_MARKET",
    "ORDER_TYPE_STOP_LIMIT",
    "ORDER_TYPE_STOP_LOSS",
    "PAGES_EXHAUSTED_FORMAT",
    "PAGE_NEXT_KEY",
    "PAGE_RESULTS_KEY",
    "PAIR_API_TRADABLE_KEY",
    "PAIR_ASSET_CODE_KEY",
    "PAIR_ASSET_INCREMENT_KEY",
    "PAIR_MAX_ORDER_SIZE_KEY",
    "PAIR_MIN_ORDER_AMOUNT_KEY",
    "PAIR_MIN_ORDER_SIZE_KEY",
    "PAIR_NUMERIC_KEYS",
    "PAIR_QUOTE_CODE_KEY",
    "PAIR_QUOTE_INCREMENT_KEY",
    "PAIR_REQUIRED_KEYS",
    "PAIR_STATUS_KEY",
    "PAIR_SYMBOL_KEY",
    "PATH_UNPUBLISHED_FORMAT",
    "PRICE_ASK_INCLUSIVE_KEY",
    "PRICE_ASK_KEY",
    "PRICE_BID_INCLUSIVE_KEY",
    "PRICE_BID_KEY",
    "PRICE_MID_KEY",
    "PRICE_SYMBOL_KEY",
    "RATE_LIMIT_BURST_PER_MINUTE",
    "RATE_LIMIT_PER_MINUTE",
    "RATE_LIMIT_WINDOW_S",
    "SIGNING_KEY_REFUSED_FORMAT",
    "SIZE_FIELD_UNITS",
    "STATUS_SELL_ONLY",
    "STATUS_SELL_ONLY_FORMAT",
    "STATUS_TRADABLE",
    "STATUS_UNNAMED_FORMAT",
    "STATUS_UNTRADABLE",
    "STATUS_UNTRADABLE_FORMAT",
    "SYMBOL_QUERY_KEY",
    "TIMED_ORDER_TYPES",
    "TIME_IN_FORCE_GTC",
    "TRADING_HOST",
    "TRADING_PAIRS_PATH",
    "TRADING_PAIRS_PATH_FEE_TIERS",
    "UNEXPECTED_RESPONSE_FORMAT",
    "UNIFIED_PAIR_SEPARATOR",
    "UNLISTED_MARKET_FORMAT",
    "UNPARSED_PAIR_NUMBER_FORMAT",
    "UNPUBLISHED_ORDER_FIELD_FORMAT",
    "VENUE_DECIMAL_PLACES",
    "VENUE_ID",
    "VENUE_LABEL",
    "VENUE_ORDER_TYPES",
    "VENUE_PAIR_SEPARATOR",
    "VENUE_PAIR_STATUSES",
    "VENUE_TIMES_IN_FORCE",
    "RobinhoodCryptoConnector",
    "RobinhoodOrderRefused",
    "RobinhoodPathUnpublished",
    "RobinhoodReadRefused",
    "RobinhoodResponseUnexpected",
    "best_price_path",
    "body_text",
    "cancel_path",
    "client_order_uuid",
    "crypto_connector_class",
    "decimal_text",
    "hand_written_crypto_venues",
    "holding_balance",
    "holdings_path",
    "order_body",
    "order_body_refusal",
    "order_from_record",
    "order_list_path",
    "orders_path",
    "page_list",
    "page_next_path",
    "page_records",
    "pair_asset_class",
    "pair_asset_info",
    "pair_declared_order_types",
    "pair_number",
    "pair_record_refusal",
    "pair_rules",
    "pair_size_shapes",
    "pair_status",
    "pair_symbol",
    "price_bid_ask",
    "price_orderbook",
    "price_ticker",
    "published_order_config_fields",
    "query_string",
    "signature",
    "signed_headers",
    "signed_message",
    "status_order_refusal",
    "trading_pairs_path",
    "unified_symbol",
    "venue_order_type",
    "venue_symbol",
]
