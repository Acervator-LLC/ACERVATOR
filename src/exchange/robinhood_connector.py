"""Hand-written :class:`ExchangeInterface` for Robinhood's crypto markets.

``order_body`` builds the venue's own order shape and ``signed_headers`` signs
it with an Ed25519 key. ``get_markets`` reads the published Get Crypto Trading
Pairs path, follows every page of it and hands the records to ``record_pairs``,
and ``pair_rules`` turns one record into the ``MarketRules``
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

#: Why a read refuses: Robinhood names the endpoint and publishes no path.
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

    ``RobinhoodResponseUnexpected`` names the key and the type where the page
    is not an object, where it carries no array under ``PAGE_RESULTS_KEY``, or
    where ``pair_record_refusal`` reads a member.
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
        refusal = pair_record_refusal(record, index, path)
        if refusal:
            raise RobinhoodResponseUnexpected(refusal)
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

    Every ``ORDER_CONFIG_KEYS`` object takes ``SIZE_FIELD_UNITS`` or a quote
    amount, and neither side permits one of the two alone.
    """
    from ..trading.scrumming.sizing import SHAPE_CASH_AMOUNT, SHAPE_FRACTIONAL_UNITS

    return frozenset({SHAPE_FRACTIONAL_UNITS, SHAPE_CASH_AMOUNT})


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
    ``get_markets`` reads ``trading_pairs_path`` through the same transport.
    Every other read method raises ``RobinhoodPathUnpublished``.
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
        path = first
        held: list[dict] = []
        for page in range(MAX_PAIR_PAGES):
            raw = await self._read(path)
            records = page_records(raw, path)
            held.extend(records)
            following = page_next_path(raw, path, records)
            if not following:
                if not held:
                    raise RobinhoodResponseUnexpected(
                        NO_PAIR_SERVED_FORMAT.format(path=first)
                    )
                get_api_log().record(
                    exchange=self._exchange_id,
                    action="GET_MARKETS",
                    reason=f"Read the {VENUE_LABEL} trading pairs",
                    endpoint=first,
                    params={"pages": page + 1},
                    result=f"{len(held)} trading pair record(s)",
                    level="info",
                    data_usage=(
                        "Recorded market rules size every later order on this " "venue"
                    ),
                )
                return held
            path = following
        raise RobinhoodResponseUnexpected(
            PAGES_EXHAUSTED_FORMAT.format(
                path=first, pages=MAX_PAIR_PAGES, key=PAGE_NEXT_KEY
            )
        )

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
    "EMPTY_PROMISED_PAGE_FORMAT",
    "FOREIGN_NEXT_HOST_FORMAT",
    "HEADER_API_KEY",
    "HEADER_SIGNATURE",
    "HEADER_TIMESTAMP",
    "MAX_PAIR_PAGES",
    "MISSING_PAIR_KEY_FORMAT",
    "NOT_API_TRADABLE_FORMAT",
    "NO_API_KEY",
    "NO_CREDENTIAL",
    "NO_CREDENTIAL_FOR_READ",
    "NO_IMMEDIATE_OR_CANCEL",
    "NO_PAIR_SERVED_FORMAT",
    "ORDERS_PATH",
    "ORDERS_PATH_FEE_TIERS",
    "ORDER_CONFIG_KEYS",
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
    "TIMED_ORDER_TYPES",
    "TIME_IN_FORCE_GTC",
    "TRADING_HOST",
    "TRADING_PAIRS_PATH",
    "TRADING_PAIRS_PATH_FEE_TIERS",
    "UNEXPECTED_RESPONSE_FORMAT",
    "UNIFIED_PAIR_SEPARATOR",
    "UNLISTED_MARKET_FORMAT",
    "UNPARSED_PAIR_NUMBER_FORMAT",
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
    "body_text",
    "client_order_uuid",
    "crypto_connector_class",
    "decimal_text",
    "hand_written_crypto_venues",
    "order_body",
    "orders_path",
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
    "signature",
    "signed_headers",
    "signed_message",
    "status_order_refusal",
    "trading_pairs_path",
    "unified_symbol",
    "venue_order_type",
    "venue_symbol",
]
