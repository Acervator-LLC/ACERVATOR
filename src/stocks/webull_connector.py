"""
webull_connector.py — Webull broker connector.

``WebullConnector`` answers ``BrokerBase`` for ``VENUE_ID``, so
``MainWindow._connect_broker_for_bot`` builds it and ``BotContainer`` reaches it
through ``BrokerExchange``. ``INSTRUMENT_TYPE_SECTORS``,
``FUTURES_CLASS_SECTORS``, ``FUTURES_PRODUCT_SECTORS`` and ``asset_sector``
carry the product vocabulary Webull's own OpenAPI documents and product pages
publish. ``ORDER_ROUTE`` names the one order route its own API host serves for
every sector, ``order_body`` composes the ticket that route's own schema
declares, and ``request_signature`` computes the digest every route requires.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import math
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from ..exchange.base import MarketRules
from ..trading.scrumming.sizing import (
    ORDER_TYPES_WITH_MARKET,
    SESSION_CONTINUOUS,
    SESSION_US_EQUITY,
)
from .broker_base import (
    AccountInfo,
    BrokerBase,
    OrderSide,
    OrderType,
    PositionSide,
    StockOrder,
    StockPosition,
    StockQuote,
    TimeInForce,
)

logger = logging.getLogger("acervator.stocks.webull")

#: The venue id this broker registers under, which ``BROKER_CONNECTORS`` keys,
#: ``WebullConnector.exchange_id`` answers and the sector tables in
#: ``trading.scrumming.sizing`` are keyed by.
VENUE_ID = "webull"

#: The two hosts Webull's own documentation names for the Trading API, read
#: 2026-10-11 from ``developer.webull.com/apis/llms.txt`` with no credential
#: sent: 223 indexed entries, each with a ``.md`` twin, and the order route's own
#: OpenAPI body at 57,236 bytes. The host joins the signature, so a request to
#: one host cannot be signed for the other.
API_BASE = "https://api.webull.com"
SANDBOX_BASE = "https://api.sandbox.webull.com"

#: The one order route the venue serves, which every sector's order takes. Its
#: own ``operationId`` is "Common Order Place" and its body carries one array of
#: order items under ``new_orders``.
ORDER_ROUTE = "/trading/orders/place"

#: The route each read this connector makes takes, each one named in the same
#: index. ``ORDERS_HISTORY_ROUTE`` is the fill ledger and ``ORDER_ITEM_ROUTE``
#: the only route carrying a fee.
ACCOUNTS_ROUTE = "/trading/accounts/list"
BALANCE_ROUTE = "/trading/assets/balances/get"
POSITIONS_ROUTE = "/trading/assets/positions/list"
CANCEL_ROUTE = "/trading/orders/cancel"
ORDER_ITEM_ROUTE = "/trading/orders/get"
ORDERS_OPEN_ROUTE = "/trading/orders/open-orders/list"
ORDERS_HISTORY_ROUTE = "/trading/orders/historical-orders/list"
STOCK_LIST_ROUTE = "/trading/instruments/stocks/profiles/list"
CRYPTO_LIST_ROUTE = "/trading/instruments/crypto/profiles/list"
FUTURES_LIST_ROUTE = "/trading/instruments/futures/contracts/list"
STOCK_SNAPSHOT_ROUTE = "/market-data/stocks/snapshots/list"
CRYPTO_SNAPSHOT_ROUTE = "/market-data/crypto/snapshots/list"
STOCK_BARS_ROUTE = "/market-data/stocks/bars/list"
CRYPTO_BARS_ROUTE = "/market-data/crypto/bars/list"
FUTURES_BARS_ROUTE = "/market-data/futures/bars/list"

#: The signature every route requires, off the venue's own Signature page. The
#: secret carries ``DIGEST_KEY_TRAILER`` before it keys the digest, and
#: ``SIGNING_HEADER_NAMES`` names the six headers that join the query parameters
#: in the signed string. Quoted whole: "``x-signature`` and ``x-version`` do
#: **not** participate in signing."
SIGNATURE_ALGORITHM = "HMAC-SHA1"
SIGNATURE_VERSION = "1.0"
API_VERSION = "v3"
DIGEST_KEY_TRAILER = "&"
SIGNED_PART_SEPARATOR = "&"
SIGNING_HEADER_NAMES = (
    "x-app-key",
    "x-signature-algorithm",
    "x-signature-version",
    "x-signature-nonce",
    "x-timestamp",
    "host",
)

#: The moment format ``x-timestamp`` takes. Quoted whole: "Request timestamp in
#: ISO 8601 format: ``YYYY-MM-DDThh:mm:ssZ`` (UTC only)."
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

#: The venue's own worked example and the digest it must produce, published on
#: the same page as the algorithm: "If your output matches
#: ``kvlS6opdZDhEBo5jq40nHYXaLvM=``, your implementation is correct." It is the
#: venue's own two-sided control on ``request_signature``, and it needs no
#: credential and no request.
SIGNATURE_PROOF_PATH = "/trade/place_order"
SIGNATURE_PROOF_QUERY = (("a1", "webull"), ("a2", "123"), ("a3", "xxx"), ("q1", "yyy"))
SIGNATURE_PROOF_BODY = (
    '{"k1":123,"k2":"this is the api request body","k3":true,"k4":{"foo":[1,2]}}'
)
SIGNATURE_PROOF_HEADERS = {
    "x-app-key": "776da210ab4a452795d74e726ebd74b6",
    "x-timestamp": "2022-01-04T03:55:31Z",
    "x-signature-version": "1.0",
    "x-signature-algorithm": "HMAC-SHA1",
    "x-signature-nonce": "48ef5afed43d4d91ae514aaeafbc29ba",
    "host": "api.webull.com",
}
SIGNATURE_PROOF_KEY = "0f50a2e853334a9aae1a783bee120c1f"
SIGNATURE_PROOF_DIGEST = "kvlS6opdZDhEBo5jq40nHYXaLvM="

#: The sector each ``instrument_type`` Webull names belongs to. Its own order
#: schema closes the vocabulary at five words — ``EQUITY``, ``OPTION``,
#: ``FUTURES``, ``CRYPTO``, ``EVENT``.
#:
#: Three are mapped here and two are not. ``OPTION`` names options, which is no
#: sector this platform draws, and ``EVENT`` names its own prediction market,
#: which is none either. ``order_body`` refuses a leg naming one, so a product
#: outside every sector this platform draws is refused and never sized.
INSTRUMENT_TYPE_SECTORS: dict[str, str] = {
    "crypto": "crypto",
    "equity": "stocks",
    "futures": "futures_perps",
}

#: The ``instrument_type`` word each order carries, keyed by the sector word the
#: recording holds. One route serves every sector, so the word is the only field
#: that changes between a share order and a contract order.
SECTOR_INSTRUMENT_TYPES: dict[str, str] = {
    "crypto": "CRYPTO",
    "stocks": "EQUITY",
    "commodities": "FUTURES",
    "forex": "FUTURES",
    "indices": "FUTURES",
    "futures_perps": "FUTURES",
}

#: The ``instrument_type`` words ``order_body`` may send, which are the three
#: ``INSTRUMENT_TYPE_SECTORS`` maps. A word outside this set raises rather than
#: reaching the venue.
ORDER_INSTRUMENT_TYPES = frozenset(SECTOR_INSTRUMENT_TYPES.values())

#: The ``category`` word each instrument route answers, mapped onto the
#: ``instrument_type`` word the order carries. The stock route's own enum holds
#: ``US_STOCK`` and its bar route's holds ``US_ETF``, and both file as an equity
#: order, which is why a fund share records under stocks and not under the
#: sector its holdings track.
CATEGORY_INSTRUMENT_TYPES: dict[str, str] = {
    "us_stock": "EQUITY",
    "us_etf": "EQUITY",
    "us_crypto": "CRYPTO",
    "us_futures": "FUTURES",
}

#: The ``category`` each instrument route requires. Quoted whole from the stock
#: route's own schema: "Category values are as shown in the enum; US_OPTION type
#: query is currently not supported."
STOCK_CATEGORY = "US_STOCK"
CRYPTO_CATEGORY = "US_CRYPTO"
FUTURES_CATEGORY = "US_FUTURES"

#: The sector each futures product class names, keyed on the
#: ``product_class_name`` every contract record carries. Webull's own futures
#: page names the ten groups it sells itself: "Nano Futures Micro Futures Equity
#: Index Futures FX Futures Metals Futures Energy Futures Interest Rates Futures
#: Agricultural Futures CME Crypto Futures CDE Crypto Futures", and its own
#: Trading API page names seven asset classes: "indices, interest rates,
#: currencies, agriculture, metals, energies, and crypto". Nano and Micro are
#: size groups whose products repeat a product in another group, so no symbol
#: takes its sector from either.
#:
#: Interest rates names no finer sector and takes ``FUTURES_DEFAULT_SECTOR``,
#: which is the contract form and a sector this platform does draw. That is the
#: reading ``ibkr_connector.FUTURES_FAMILY_SECTORS`` already takes for the same
#: family.
FUTURES_CLASS_SECTORS: dict[str, str] = {
    "agricultural": "commodities",
    "agriculture": "commodities",
    "crypto": "crypto",
    "cryptocurrency": "crypto",
    "currencies": "forex",
    "currency": "forex",
    "energies": "commodities",
    "energy": "commodities",
    "equities": "indices",
    "equity index": "indices",
    "fx": "forex",
    "metals": "commodities",
}

#: The sector each futures product code names, off the 22 contracts Webull's own
#: futures page serves in its product table with their multipliers and tick
#: sizes. A contract record whose ``product_class_name`` is absent still records
#: under its own sector through its ``code``.
#:
#: Four codes map to no finer sector — 10Y, 30Y, 2YY and 5YY, the Micro Yield
#: contracts — and take ``FUTURES_DEFAULT_SECTOR``.
FUTURES_PRODUCT_SECTORS: dict[str, str] = {
    "m2k": "indices",
    "mes": "indices",
    "mnq": "indices",
    "mym": "indices",
    "m6a": "forex",
    "m6b": "forex",
    "m6e": "forex",
    "mcd": "forex",
    "msf": "forex",
    "mcl": "commodities",
    "mgc": "commodities",
    "mhg": "commodities",
    "mng": "commodities",
    "sil": "commodities",
    "mbt": "crypto",
    "met": "crypto",
    "msl": "crypto",
    "mxp": "crypto",
}

#: The sector a contract record naming no class this table holds falls to: the
#: contract form, which is the sector this platform draws for a dated contract.
FUTURES_DEFAULT_SECTOR = "futures_perps"

#: The fields a futures contract record carries and no other instrument record
#: does, which name a record as a contract where it carries no ``category``.
#: The contract route's own schema names all three.
FUTURES_MARKER_FIELDS = ("contract_month", "product_class_name", "last_trading_date")

#: The field an equity record publishes its own fractional eligibility under,
#: and the ceiling the venue puts on a fraction. Quoted whole from its own Stock
#: Trading page: "Only ``MARKET`` orders are supported for fractional trading.
#: The quantity must be between 0 (exclusive) and 1 (inclusive), and the order
#: value must be at least $5." Its own ``total_cash_amount`` field agrees on the
#: other entry shape: "Amount must be less than the price of 1 share."
#:
#: So the fraction exists only below one share and this engine's scrum
#: arithmetic never produces one, which makes ``WHOLE_UNIT_INCREMENT`` the step
#: an equity order takes. Alpaca and Schwab are fractional venue-wide,
#: Interactive Brokers' API is not fractional at all and tastytrade is
#: fractional per equity down to a millionth; this venue is a fourth answer.
EQUITY_FRACTION_FIELD = "fractionable"
FRACTIONAL_QUANTITY_MAX = 1.0
FRACTIONAL_ORDER_USD_MIN = 5.0
WHOLE_UNIT_INCREMENT = 1.0

#: The field an equity record publishes its own night-session eligibility under.
#: Quoted whole from the venue's own Overnight Trading page: "You can now trade
#: Select Stocks (whole shares only) and ETFs anytime with Overnight Trading."
#: The night session is whole shares only and reaches only the symbols this
#: field marks, so ``SESSION_NIGHT`` is never composed from a size this engine
#: produces.
OVERNIGHT_FIELD = "overnight_trading_supported"

#: The trading sessions an equity order may name, off the field's own enum.
#: Quoted whole: "NIGHT: Only supports night trading. ALL: Include extended
#: trading hours. CORE: Only support regular trading hours."
#:
#: ``ORDER_TRADING_SESSION`` is what every equity order carries. ``ALL`` is the
#: widest session a size this engine produces can take: it covers pre-market,
#: regular and after-hours, and ``sizing.session_order_types`` already raises a
#: market order to a limit outside regular hours, which is the one restriction
#: the venue's own extended-hours example shows.
SESSION_ALL = "ALL"
SESSION_CORE = "CORE"
SESSION_NIGHT = "NIGHT"
ORDER_TRADING_SESSION = SESSION_ALL

#: The smallest crypto order and the floor a crypto sale may not cross, off the
#: venue's own Crypto Trading page. Quoted whole: "Minimum order amount $2.00",
#: "Smallest tradable amount 0.00000001", and "When selling crypto, your
#: remaining position must not fall below $2 after the order is placed."
#:
#: ``CRYPTO_MIN_ORDER_USD`` is $1.00 for a customer in New York, Guam or the
#: Northern Mariana Islands, where the venue names Bakkt as the provider. The
#: higher figure is carried, because an order above the lower floor is accepted
#: in both and an order below the higher one is not.
CRYPTO_QUANTITY_PRECISION = 8
CRYPTO_MIN_ORDER_SIZE = 1e-8
CRYPTO_MIN_ORDER_USD = 2.0
CRYPTO_POSITION_FLOOR_USD = 2.0

#: The order types each product takes, off the venue's own Trading API FAQ
#: table. Stocks and futures take MARKET, LIMIT, STOP_LOSS, STOP_LOSS_LIMIT and
#: TRAILING_STOP_LOSS; crypto takes MARKET, LIMIT and STOP_LOSS_LIMIT alone.
#: Every one of the three carries a market order, so every recorded market
#: answers ``ORDER_TYPES_WITH_MARKET``.
ORDER_TYPE_MARKET = "MARKET"
ORDER_TYPE_LIMIT = "LIMIT"
ORDER_TYPE_STOP = "STOP_LOSS"
ORDER_TYPE_STOP_LIMIT = "STOP_LOSS_LIMIT"
VENUE_ORDER_TYPES = {
    OrderType.MARKET: ORDER_TYPE_MARKET,
    OrderType.LIMIT: ORDER_TYPE_LIMIT,
    OrderType.STOP: ORDER_TYPE_STOP,
    OrderType.STOP_LIMIT: ORDER_TYPE_STOP_LIMIT,
}

#: The order side words the venue's own enum holds. ``SHORT`` opens a short
#: equity position and this engine accumulates, so it is never sent.
VENUE_SIDES = {OrderSide.BUY: "BUY", OrderSide.SELL: "SELL"}

#: The times in force each product takes, off the same table. Quoted whole:
#: "U.S. Stock, Futures, and Options trading support the following Time in Force
#: (TIF) values: DAY and GTC. Crypto trading supports the following Time in
#: Force (TIF) values: DAY, GTC, and IOC."
#:
#: A crypto market order takes one and only one. Quoted whole: "When the order
#: type is MARKET: time_in_force only supports IOC."
VENUE_TIMES_IN_FORCE = {
    TimeInForce.DAY: "DAY",
    TimeInForce.GTC: "GTC",
    TimeInForce.IOC: "IOC",
}
DEFAULT_TIME_IN_FORCE = TimeInForce.DAY
CRYPTO_MARKET_TIME_IN_FORCE = TimeInForce.IOC
CRYPTO_TIMES_IN_FORCE = (TimeInForce.DAY, TimeInForce.GTC, TimeInForce.IOC)
VENUE_PRODUCT_TIMES_IN_FORCE = (TimeInForce.DAY, TimeInForce.GTC)

#: The one combo type every sector this platform trades takes. Quoted whole:
#: "Futures、Crypto、Event trading currently supports only the NORMAL combo
#: type", and NORMAL "Indicates a standard single order".
COMBO_TYPE_NORMAL = "NORMAL"

#: The one market code the venue's own enum holds on every order and every
#: instrument record.
MARKET_CODE = "US"

#: The entrust types the venue publishes, and the one every order this engine
#: sends carries. Quoted whole: "QTY: Order specified by quantity of shares or
#: units", and on futures: "For futures, only quantity orders are supported."
#: ``ENTRUST_AMOUNT`` is named and never sent, its own field reading "Amount
#: must be less than the price of 1 share".
ENTRUST_QTY = "QTY"
ENTRUST_AMOUNT = "AMOUNT"

#: The characters a ``client_order_id`` may hold. Quoted whole: "Maximum length
#: is 32 characters and must be unique per account."
CLIENT_ORDER_ID_MAX = 32

#: The decimal places a figure is written with before it reaches the venue,
#: whose order schema types every price and every size as a string.
DECIMAL_PLACES = 10

#: The tradable status words every instrument record carries. Quoted whole: "OC
#: (Tradable), CO (Liquidate only), NT (Non-Tradable)". Only ``STATUS_TRADABLE``
#: takes an opening order, so the other two never become a recorded market.
STATUS_TRADABLE = "OC"

#: The order statuses the venue's own enum holds, and the two naming a fill.
#: Quoted whole: "PENDING, SUBMITTED, CANCELLED, FILLED, FAILED,
#: PARTIAL_FILLED".
STATUS_FILLED = "FILLED"
STATUS_PARTIAL_FILLED = "PARTIAL_FILLED"
FILL_STATUSES = frozenset({STATUS_FILLED, STATUS_PARTIAL_FILLED})

#: The side words an order record carries, mapped onto this platform's own.
FILL_SIDES = {
    "BUY": OrderSide.BUY.value,
    "SELL": OrderSide.SELL.value,
}

#: The currency every figure the venue publishes is read in, off the ``currency``
#: enum on its balance, position and activity records, which holds ``USD``
#: alone.
FEE_CURRENCY = "USD"

#: The continuation every paged route carries and the pages a walk takes before
#: it stops. Quoted whole from the route's own schema: "Pagination key for next
#: page. If absent, indicates this is the last page."
#:
#: No orders route publishes a page size, so there is no cap to mis-state and no
#: short page to misread, and the route states why a page length is never the
#: end test: "If orders are group orders, they will be returned together, and
#: the number of orders returned on one page may exceed the page_size."
PAGINATION_FIELD = "pagination_key"
ORDER_PAGES_MAX = 100
INSTRUMENT_PAGES_MAX = 100

#: The symbols one instrument or bar request names. The bar routes' own schema
#: caps a symbol list — "maximum 20 symbols per query" — and the profile routes
#: publish no cap, so the published cap is what every batch takes.
SYMBOL_BATCH = 20

#: The fee fields one order record carries and the route that carries them.
#: ``ORDER_ITEM_ROUTE`` publishes ``commission.actual_commission`` and
#: ``fees[].actual_value``; ``ORDERS_HISTORY_ROUTE`` publishes neither, so
#: ``list_fills`` reads the detail per fill to attach the venue's own figure.
#:
#: That route's own rate limit is 2 requests in 2 seconds, so the attachment is
#: bounded at ``FILL_FEE_READS_MAX`` and ``FILL_FEE_UNREAD_NOTE`` records every
#: fill left without one.
COMMISSION_FIELD = "commission"
COMMISSION_VALUE_FIELD = "actual_commission"
FEES_FIELD = "fees"
FEE_VALUE_FIELD = "actual_value"
FILL_FEE_READS_MAX = 50

#: What ``list_fills`` logs when the fee walk stopped before the fills did, so
#: no caller reads a zero fee as the venue's own figure.
FILL_FEE_UNREAD_NOTE = (
    "Webull publishes a fill's fee on %s alone, rate limited at 2 requests in 2 "
    "seconds, so %d of %d fill(s) carry the venue's own fee and %d carry none"
)

#: What ``list_fills`` logs after the walk, so a bounded walk is never read as a
#: whole history.
FILL_WALK_NOTE = (
    "Webull answered %d fill(s) over %d page(s) of %s, the walk stopping on the "
    "absent %s and at %d pages"
)

#: What ``list_assets`` logs for a record this platform can read and cannot
#: both size and order, so a refused record is visible and is not a silent gap.
NO_TRADABLE_MARKET = "Webull answered %d record(s) this platform does not trade: %s"

#: The only market-clock route Webull publishes and the API it belongs to. Of
#: the 223 entries its own documentation index lists, this one names a trading
#: calendar, and it sits under the Broker API behind a separate credential, so
#: the Trading API this connector holds reaches no clock.
TRADE_CALENDAR_ROUTE = "Broker API, List Trade Calendar"

#: What ``get_market_status`` logs so a closed answer is read as an absent route
#: and not as a closed market.
NO_CLOCK_ROUTE = (
    "Webull's Trading API publishes no market-clock route; %s is the only "
    "published calendar and takes a Broker API credential, so the session that "
    "reaches an order is the one asset_session records per market"
)

#: What ``order_body`` raises on, naming the product and the vocabulary that
#: closed it.
NO_ORDER_INSTRUMENT_TYPE = (
    "Webull publishes instrument type {word!r} for {symbol}, which is no sector "
    "this platform draws; the words an order may carry are {named}"
)
NO_INSTRUMENT_TYPE = (
    "Webull named no instrument type for {symbol}, so no order can be composed"
)

#: The bar width each timeframe takes on the venue's own bar routes, whose
#: ``timespan`` enum holds eleven words: M1, M5, M15, M30, M60, M120, M240, D,
#: W, M, Y.
BAR_WIDTHS = {
    "1Min": "M1",
    "5Min": "M5",
    "15Min": "M15",
    "30Min": "M30",
    "1H": "M60",
    "4H": "M240",
    "1D": "D",
    "1W": "W",
    "1m": "M1",
    "5m": "M5",
    "15m": "M15",
    "30m": "M30",
    "1h": "M60",
    "4h": "M240",
    "1d": "D",
    "1w": "W",
}
DEFAULT_BAR_WIDTH = "D"

#: The bars one bar request asks for. Quoted whole: "Number of bars, default
#: 200, maximum limit 1200 (M1 supports up to 1650)."
BAR_COUNT_MAX = 1200

#: The trading sessions a bar request asks for, off the bar route's own enum,
#: which holds ``PRE``, ``RTH``, ``ATH`` and ``OVN``. All four are asked so a
#: chart carries the hours an order may be placed in.
BAR_SESSIONS = "PRE,RTH,ATH,OVN"


def rule_number(value: Any) -> Optional[float]:
    """``value`` as a finite float, and None for anything that is not one.

    The venue types every rule, price and size as a decimal string, so a bool is
    refused, a blank is None and a non-finite figure is None.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        held = value.strip()
        if not held:
            return None
        try:
            held_number = float(held)
        except ValueError:
            return None
        return held_number if math.isfinite(held_number) else None
    if type(value) not in (int, float):
        return None
    held_number = float(value)
    return held_number if math.isfinite(held_number) else None


def decimal_text(value: Any) -> str:
    """``value`` as the decimal string the venue's own order schema types every
    price and every size as, with no exponent and no trailing zeros."""
    held = rule_number(value)
    if held is None:
        return ""
    written = f"{held:.{DECIMAL_PLACES}f}".rstrip("0").rstrip(".")
    return written or "0"


def signed_timestamp(moment_s: Any = None) -> str:
    """``moment_s`` as the UTC ``x-timestamp`` the venue requires, and the
    current moment where none is given."""
    held = rule_number(moment_s)
    when = time.time() if held is None else held
    return datetime.fromtimestamp(when, tz=timezone.utc).strftime(TIMESTAMP_FORMAT)


def signature_string(
    path: str,
    query: Iterable[tuple[str, str]],
    body_text: str,
    signing_headers: dict,
) -> str:
    """The string the venue's own algorithm signs, before it is URL-encoded.

    Every query parameter and every ``SIGNING_HEADER_NAMES`` header is merged,
    sorted by name and joined as ``name=value`` pairs; a body contributes the
    uppercase MD5 of its own text as a final part; and the path leads.
    """
    parts = [(str(name), str(value)) for name, value in query]
    for name in SIGNING_HEADER_NAMES:
        if name in signing_headers:
            parts.append((name, str(signing_headers[name])))
    joined = SIGNED_PART_SEPARATOR.join(
        f"{name}={value}" for name, value in sorted(parts)
    )
    built = f"{path}{SIGNED_PART_SEPARATOR}{joined}"
    if body_text:
        digest = (
            hashlib.md5(body_text.encode("utf-8"), usedforsecurity=False)
            .hexdigest()
            .upper()
        )
        built = f"{built}{SIGNED_PART_SEPARATOR}{digest}"
    return built


def request_signature(
    app_signing_key: str,
    path: str,
    query: Iterable[tuple[str, str]],
    body_text: str,
    signing_headers: dict,
) -> str:
    """The ``x-signature`` value one request carries, computed the way the
    venue's own Signature page spells it.

    The signed string is URL-encoded, the key is the app secret with
    ``DIGEST_KEY_TRAILER`` appended, and the digest is base64 of HMAC-SHA1.
    ``SIGNATURE_PROOF_DIGEST`` is the venue's own published output for
    ``SIGNATURE_PROOF_*``, so this function can be checked with no credential
    and no request.
    """
    encoded = urllib.parse.quote(
        signature_string(path, query, body_text, signing_headers), safe=""
    )
    digest = hmac.new(
        f"{app_signing_key}{DIGEST_KEY_TRAILER}".encode(),
        encoded.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def signature_self_proof() -> bool:
    """Whether ``request_signature`` reproduces the digest the venue publishes
    for its own worked example.

    ``connect`` reads this before it sends anything, so a signature that cannot
    match the venue's own vector refuses the session instead of earning a 401.
    """
    return (
        request_signature(
            SIGNATURE_PROOF_KEY,
            SIGNATURE_PROOF_PATH,
            SIGNATURE_PROOF_QUERY,
            SIGNATURE_PROOF_BODY,
            dict(SIGNATURE_PROOF_HEADERS),
        )
        == SIGNATURE_PROOF_DIGEST
    )


def instrument_word(asset: Any) -> str:
    """The uppercase ``instrument_type`` word one record names, read off its own
    ``instrument_type`` first, its ``category`` second and its contract fields
    third.

    A futures contract record carries no ``category``, so
    ``FUTURES_MARKER_FIELDS`` names it, and a record naming none answers "".
    """
    if not isinstance(asset, dict):
        return ""
    named = str(asset.get("instrument_type") or "").strip().upper()
    if named:
        return named
    category = str(asset.get("category") or "").strip().lower()
    held = CATEGORY_INSTRUMENT_TYPES.get(category)
    if held:
        return held
    if any(asset.get(field) for field in FUTURES_MARKER_FIELDS):
        return CATEGORY_INSTRUMENT_TYPES["us_futures"]
    return ""


def product_code(asset: Any) -> str:
    """The futures product code one contract record names, lowercased.

    The record's own ``code`` leads; where it names none, the symbol's leading
    letters are taken, because the venue's own symbology writes a contract
    symbol as the product code plus a month letter and a year digit, or plus
    "main".
    """
    if not isinstance(asset, dict):
        return ""
    named = str(asset.get("code") or "").strip().lower()
    if named:
        return named
    symbol = str(asset.get("symbol") or "").strip().lower()
    if symbol.endswith("main"):
        return symbol[: -len("main")]
    return symbol[:3]


def futures_sector(asset: Any) -> str:
    """The sector one futures contract record names.

    ``FUTURES_CLASS_SECTORS`` answers off the record's own
    ``product_class_name``, ``FUTURES_PRODUCT_SECTORS`` answers off its own
    ``code``, and ``FUTURES_DEFAULT_SECTOR`` answers for a class and a code
    naming no finer sector.
    """
    if not isinstance(asset, dict):
        return FUTURES_DEFAULT_SECTOR
    named = str(asset.get("product_class_name") or "").strip().lower()
    held = FUTURES_CLASS_SECTORS.get(named)
    if held:
        return held
    return FUTURES_PRODUCT_SECTORS.get(product_code(asset), FUTURES_DEFAULT_SECTOR)


def asset_sector(asset: Any) -> Optional[str]:
    """The sector one Webull record belongs to, and None where the record names
    a product outside every sector this platform draws.

    ``INSTRUMENT_TYPE_SECTORS`` answers the three order-bearing words, a
    ``FUTURES`` record is narrowed by ``futures_sector``, and ``OPTION`` and
    ``EVENT`` answer None.
    """
    word = instrument_word(asset).lower()
    sector = INSTRUMENT_TYPE_SECTORS.get(word)
    if sector is None:
        return None
    if sector == FUTURES_DEFAULT_SECTOR:
        return futures_sector(asset)
    return sector


def asset_expiry_ms(asset: Any) -> Optional[float]:
    """The epoch milliseconds one contract record closes on, read off its own
    ``last_trading_date``, and None for a record naming none.

    The venue refuses delivery itself — "Physical delivery is **not permitted**
    through Webull — you must close or roll your position before expiration" —
    so the last trading date and not the settlement date is the moment a
    position must be out by.
    """
    if not isinstance(asset, dict):
        return None
    named = str(asset.get("last_trading_date") or "").strip()
    if not named:
        return None
    try:
        when = datetime.strptime(named[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return when.timestamp() * 1000.0


def increment_rule(asset: Any) -> Optional[float]:
    """The price step one record publishes: a crypto record's own
    ``price_step``, a contract record's own ``min_tick``, and None for an equity
    record, whose profile route publishes no price increment."""
    if not isinstance(asset, dict):
        return None
    held = rule_number(asset.get("price_step"))
    if held is not None and held > 0.0:
        return held
    held = rule_number(asset.get("min_tick"))
    if held is not None and held > 0.0:
        return held
    return None


def size_increment(asset: Any) -> Optional[float]:
    """The size step one record publishes.

    ``CRYPTO_MIN_ORDER_SIZE`` on a crypto record, or its own ``min_trade_qty``
    where that is finer; ``WHOLE_UNIT_INCREMENT`` on an equity record, because
    the venue's own fraction is capped at one share and a scrum never produces
    one; ``WHOLE_UNIT_INCREMENT`` on a contract record; and None where
    ``asset_sector`` names no sector.
    """
    word = instrument_word(asset)
    if asset_sector(asset) is None:
        return None
    if word == "CRYPTO":
        held = rule_number((asset or {}).get("min_trade_qty"))
        if held is not None and held > 0.0:
            return held
        return CRYPTO_MIN_ORDER_SIZE
    return WHOLE_UNIT_INCREMENT


def minimum_cost(asset: Any) -> Optional[float]:
    """The smallest cash an order may name, which the venue publishes for crypto
    alone.

    A crypto record's own ``min_trade_amt`` leads and ``CRYPTO_MIN_ORDER_USD``
    answers where it names none. An equity and a contract record publish no cash
    minimum, so both answer None.
    """
    if instrument_word(asset) != "CRYPTO":
        return None
    held = rule_number((asset or {}).get("min_trade_amt"))
    if held is not None and held > 0.0:
        return held
    return CRYPTO_MIN_ORDER_USD


def contract_size(asset: Any) -> Optional[float]:
    """The base units one contract stands for, read off a contract record's own
    ``size``, and None for every other record.

    Quoted whole from the field's own schema: "Contract size (multiplier). The
    notional value of one contract equals futures price multiplied by this
    size."
    """
    if instrument_word(asset) != "FUTURES":
        return None
    held = rule_number((asset or {}).get("size"))
    return held if held is not None and held > 0.0 else None


def asset_order_types(asset: Any) -> Optional[str]:
    """The order types one record's own product declares, and None where
    ``asset_sector`` names no sector.

    Every one of the venue's three order-bearing products carries a market
    order, which its own FAQ table states per asset class, so every recorded
    market answers ``ORDER_TYPES_WITH_MARKET``.
    """
    if asset_sector(asset) is None:
        return None
    return ORDER_TYPES_WITH_MARKET


def asset_session(asset: Any) -> Optional[str]:
    """``SESSION_US_EQUITY`` for an equity record, ``SESSION_CONTINUOUS`` for a
    crypto record and for a contract record, and None where ``asset_sector``
    names no sector.

    The venue answers all three itself: a US equity order carries a
    ``support_trading_session``, "Crypto trading is available 24 hours a day, 7
    days a week", and "Futures markets are open virtually 24 hours a day, 6 days
    a week".
    """
    if asset_sector(asset) is None:
        return None
    if instrument_word(asset) == "EQUITY":
        return SESSION_US_EQUITY
    return SESSION_CONTINUOUS


def asset_rules(asset: Any) -> MarketRules:
    """The ``MarketRules`` one Webull record publishes.

    ``read`` is False for anything that is not a record, an unpublished rule is
    None, ``contract_size`` carries a contract's own ``size`` and ``expiry_ms``
    the date ``asset_expiry_ms`` reads.
    """
    if not isinstance(asset, dict):
        return MarketRules(read=False)
    return MarketRules(
        min_amount=size_increment(asset),
        min_cost=minimum_cost(asset),
        amount_increment=size_increment(asset),
        price_increment=increment_rule(asset),
        contract_size=contract_size(asset),
        session=asset_session(asset),
        order_types=asset_order_types(asset),
        expiry_ms=asset_expiry_ms(asset),
    )


def tradable_market(asset: Any) -> bool:
    """Whether one record names a market this platform can both size and order.

    ``asset_sector`` must name a sector, and the record's own ``status`` must be
    ``STATUS_TRADABLE``: the other two words its enum holds are "Liquidate only"
    and "Non-Tradable", neither of which takes an opening order.
    """
    if asset_sector(asset) is None:
        return False
    named = str((asset or {}).get("status") or "").strip().upper()
    return named in ("", STATUS_TRADABLE)


def published_time_in_force(asset: Any, order_type: Any, time_in_force: Any) -> Any:
    """The time in force Webull publishes for one order into ``asset``.

    ``CRYPTO_MARKET_TIME_IN_FORCE`` for a market order into a crypto market,
    because the venue takes one and only one there; ``DEFAULT_TIME_IN_FORCE``
    for a value the product does not publish; and ``time_in_force`` otherwise.
    """
    crypto = instrument_word(asset) == "CRYPTO"
    if crypto and order_type == OrderType.MARKET:
        return CRYPTO_MARKET_TIME_IN_FORCE
    if crypto:
        if time_in_force in CRYPTO_TIMES_IN_FORCE:
            return time_in_force
        return DEFAULT_TIME_IN_FORCE
    if time_in_force in VENUE_PRODUCT_TIMES_IN_FORCE:
        return time_in_force
    return DEFAULT_TIME_IN_FORCE


def order_type_named(word: Any) -> OrderType:
    """The ``OrderType`` one venue order-type word names, and ``OrderType.MARKET``
    for a word outside ``VENUE_ORDER_TYPES``."""
    named = str(word or "").strip().upper()
    for held, venue_word in VENUE_ORDER_TYPES.items():
        if venue_word == named:
            return held
    return OrderType.MARKET


def time_in_force_named(word: Any) -> TimeInForce:
    """The ``TimeInForce`` one venue word names, and ``DEFAULT_TIME_IN_FORCE``
    for a word outside ``VENUE_TIMES_IN_FORCE``."""
    named = str(word or "").strip().upper()
    for held, venue_word in VENUE_TIMES_IN_FORCE.items():
        if venue_word == named:
            return held
    return DEFAULT_TIME_IN_FORCE


def client_order_id(given: Any = "") -> str:
    """One ``client_order_id`` inside the 32 characters the venue allows, taking
    ``given`` where it is named and a fresh hex id otherwise."""
    named = str(given or "").strip()
    if named:
        return named[:CLIENT_ORDER_ID_MAX]
    return uuid.uuid4().hex[:CLIENT_ORDER_ID_MAX]


def order_body(
    asset: Any,
    symbol: Any,
    side: Any,
    quantity: float,
    order_type: Any = OrderType.MARKET,
    limit_price: float = 0.0,
    stop_price: float = 0.0,
    time_in_force: Any = TimeInForce.DAY,
    account_id: str = "",
    given_order_id: str = "",
) -> dict:
    """One request body for ``ORDER_ROUTE``, composed from the fields its own
    schema names.

    The nine its schema marks required are always written —
    ``client_order_id``, ``combo_type``, ``entrust_type``, ``instrument_type``,
    ``market``, ``order_type``, ``side``, ``symbol`` and ``time_in_force`` —
    ``support_trading_session`` rides on every equity order, ``limit_price`` and
    ``stop_price`` follow ``order_type``, and ``ValueError`` names an
    ``instrument_type`` outside ``ORDER_INSTRUMENT_TYPES``, a ``side`` or an
    ``order_type`` this venue does not publish.
    """
    held = asset if isinstance(asset, dict) else {}
    word = instrument_word(held)
    if not word:
        raise ValueError(NO_INSTRUMENT_TYPE.format(symbol=symbol))
    if word not in ORDER_INSTRUMENT_TYPES:
        raise ValueError(
            NO_ORDER_INSTRUMENT_TYPE.format(
                word=word, symbol=symbol, named=tuple(sorted(ORDER_INSTRUMENT_TYPES))
            )
        )
    venue_side = VENUE_SIDES.get(side)
    if venue_side is None:
        raise ValueError(f"order side {side!r} is not one of {tuple(VENUE_SIDES)}")
    venue_type = VENUE_ORDER_TYPES.get(order_type)
    if venue_type is None:
        raise ValueError(
            f"order type {order_type!r} is not one of {tuple(VENUE_ORDER_TYPES)}"
        )
    tif = published_time_in_force(held, order_type, time_in_force)
    item: dict[str, Any] = {
        "client_order_id": client_order_id(given_order_id),
        "combo_type": COMBO_TYPE_NORMAL,
        "entrust_type": ENTRUST_QTY,
        "instrument_type": word,
        "market": MARKET_CODE,
        "order_type": venue_type,
        "side": venue_side,
        "symbol": str(symbol),
        "time_in_force": VENUE_TIMES_IN_FORCE[tif],
        "quantity": decimal_text(quantity),
    }
    if word == "EQUITY":
        item["support_trading_session"] = ORDER_TRADING_SESSION
    if order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and limit_price > 0:
        item["limit_price"] = decimal_text(limit_price)
    if order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and stop_price > 0:
        item["stop_price"] = decimal_text(stop_price)
    return {"account_id": str(account_id), "new_orders": [item]}


def reply_items(answered: Any) -> list:
    """The rows one reply carries, whether the route answers a bare array or
    wraps it in its own ``data`` list."""
    if isinstance(answered, list):
        return [row for row in answered if isinstance(row, dict)]
    if isinstance(answered, dict):
        held = answered.get("data")
        if isinstance(held, list):
            return [row for row in held if isinstance(row, dict)]
        if isinstance(held, dict):
            return [held]
    return []


def next_page_key(answered: Any) -> str:
    """The continuation one paged reply carries, and "" where it carries none.

    Quoted whole from the field's own schema: "Pagination key for next page. If
    absent, indicates this is the last page." So "" is the end of the walk and a
    page length never is.
    """
    if not isinstance(answered, dict):
        return ""
    return str(answered.get(PAGINATION_FIELD) or "")


def order_items(answered: Any) -> list:
    """Every order record one orders reply carries, from the ``data`` list
    ``ORDERS_HISTORY_ROUTE`` and ``ORDERS_OPEN_ROUTE`` answer and from the
    top-level ``orders`` array ``ORDER_ITEM_ROUTE`` answers.

    Each combo row nests its own ``orders`` array, so a reader taking the outer
    row alone reads a combo and a reader taking ``reply_items`` alone reads
    nothing from ``ORDER_ITEM_ROUTE``.
    """
    found: list[dict] = []
    rows = reply_items(answered)
    if not rows and isinstance(answered, dict):
        if isinstance(answered.get("orders"), list):
            rows = [answered]
    for row in rows:
        nested = row.get("orders")
        if isinstance(nested, list):
            found.extend(one for one in nested if isinstance(one, dict))
            continue
        found.append(row)
    return found


def fee_total(order: Any) -> Optional[float]:
    """The fee one order record publishes, summing its own
    ``commission.actual_commission`` and every ``fees[].actual_value``.

    None where the record carries neither block, which is every row
    ``ORDERS_HISTORY_ROUTE`` serves, so a zero is never written as though the
    venue had published one.
    """
    if not isinstance(order, dict):
        return None
    found = False
    total = 0.0
    commission = order.get(COMMISSION_FIELD)
    if isinstance(commission, dict):
        held = rule_number(commission.get(COMMISSION_VALUE_FIELD))
        if held is not None:
            found = True
            total += abs(held)
    fees = order.get(FEES_FIELD)
    if isinstance(fees, list):
        for row in fees:
            if not isinstance(row, dict):
                continue
            held = rule_number(row.get(FEE_VALUE_FIELD))
            if held is not None:
                found = True
                total += abs(held)
    return total if found else None


def is_fill(order: Any) -> bool:
    """Whether one order record names a fill, off the two words of its own
    status enum that do: ``FILLED`` and ``PARTIAL_FILLED``."""
    if not isinstance(order, dict):
        return False
    if str(order.get("status") or "").strip().upper() not in FILL_STATUSES:
        return False
    return (rule_number(order.get("filled_quantity")) or 0.0) > 0.0


def fill_record(order: Any) -> dict:
    """One Webull order record as the record ``broker_trade`` reads.

    ``qty`` and ``price`` carry the record's own ``filled_quantity`` and
    ``filled_price``, ``transaction_time`` carries ``iso_moment`` of its own
    ``filled_time`` because ``broker_trade`` reads a string alone, and ``fee``
    carries the figure ``fee_total`` reads, which is None on every row
    ``ORDERS_HISTORY_ROUTE`` serves.
    """
    held = order if isinstance(order, dict) else {}
    fee = fee_total(held)
    moment = rule_number(held.get("filled_time"))
    return {
        "id": str(held.get("order_id") or held.get("client_order_id") or ""),
        "symbol": str(held.get("symbol") or ""),
        "side": FILL_SIDES.get(str(held.get("side") or "").strip().upper(), ""),
        "qty": held.get("filled_quantity"),
        "price": held.get("filled_price"),
        "fee": fee,
        "fee_currency": FEE_CURRENCY if fee is not None else "",
        "transaction_time": iso_moment(moment),
        "filled_time_ms": moment,
        "client_order_id": str(held.get("client_order_id") or ""),
        "instrument_type": str(held.get("instrument_type") or ""),
    }


def bar_width(timeframe: Any) -> str:
    """The ``timespan`` word one timeframe takes, and ``DEFAULT_BAR_WIDTH`` for a
    timeframe outside ``BAR_WIDTHS``."""
    return BAR_WIDTHS.get(str(timeframe or ""), DEFAULT_BAR_WIDTH)


def bar_count(limit: Any) -> int:
    """The ``count`` one bar request asks for, inside the 1 to
    ``BAR_COUNT_MAX`` range the route's own schema publishes."""
    held = rule_number(limit)
    if held is None:
        return BAR_COUNT_MAX
    return min(max(int(held), 1), BAR_COUNT_MAX)


def bar_rows(answered: Any) -> list[dict]:
    """Every candle one bar reply carries, read off the ``result`` array each
    symbol's own row nests them under.

    ``STOCK_BARS_ROUTE`` wraps that row array in a second ``result`` and the
    crypto and futures routes answer it bare, so both shapes unwrap here.
    """
    rows = reply_items(answered)
    if not rows and isinstance(answered, dict):
        outer = answered.get("result")
        if isinstance(outer, list):
            rows = [one for one in outer if isinstance(one, dict)]
    found: list[dict] = []
    for row in rows:
        candles = row.get("result")
        if isinstance(candles, list):
            found.extend(one for one in candles if isinstance(one, dict))
    return found


def iso_moment(moment_ms: Any) -> str:
    """``moment_ms`` as the ISO 8601 UTC moment ``broker_exchange.bar_epoch_ms``
    reads, and "" where it is no finite number.

    ``broker_trade`` and ``candle_rows`` both read a string alone, so a figure
    in epoch milliseconds is written as one here.
    """
    held = rule_number(moment_ms)
    if held is None:
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(held / 1000.0))


def bar_stamp(value: Any) -> str:
    """One bar's own ``time`` as the ISO 8601 UTC moment ``candle_rows`` reads.

    Quoted whole from the field's own schema: "Bar timestamp in ISO-8601 or Unix
    time format", so a digit string is read as an epoch in seconds or in
    milliseconds and an ISO moment is normalised through ``iso_moment``.
    """
    named = str(value or "").strip()
    if not named:
        return ""
    held = rule_number(named)
    if held is not None:
        return iso_moment(held * 1000.0 if held < 1e11 else held)
    try:
        when = datetime.fromisoformat(named.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return iso_moment(when.timestamp() * 1000.0)


def symbol_batches(symbols: Iterable[str]) -> list[list[str]]:
    """``symbols`` cut into lists of at most ``SYMBOL_BATCH``, which is the cap
    the venue's own bar routes publish for a symbol list."""
    held = [str(one) for one in symbols if str(one)]
    return [held[i : i + SYMBOL_BATCH] for i in range(0, len(held), SYMBOL_BATCH)]


class WebullConnector(BrokerBase):
    """Webull broker connector.

    ``SECTORS_SERVED`` names the six sectors its own pages list a market in, and
    ``place_order`` composes the body ``order_body`` builds for ``ORDER_ROUTE``.
    """

    #: The six sectors the venue's own pages list a market in: stocks and crypto
    #: from "We support stocks, options, futures, crypto, and event contracts",
    #: and commodities, forex, indices and futures_perps from its own futures
    #: product groups — "Equity Index Futures FX Futures Metals Futures Energy
    #: Futures Interest Rates Futures Agricultural Futures CME Crypto Futures
    #: CDE Crypto Futures". Forex is the sector the screen did not offer: five of
    #: the 22 contracts its own futures table serves are currency futures — M6E
    #: Micro EUR/USD, M6A Micro AUD/USD, MCD Micro CAD/USD, M6B Micro GBP/USD and
    #: MSF Micro CHF/USD. No perpetual: the word names 0 of the 223 entries its
    #: own documentation index lists, where "futures" names 9.
    SECTORS_SERVED: tuple = (
        "crypto",
        "stocks",
        "commodities",
        "forex",
        "indices",
        "futures_perps",
    )

    #: The venue publishes a sandbox host for every one of its three APIs, so
    #: ``broker_paper_route`` opens the paper session. Its own Token page states
    #: what that environment costs and spares: "Tokens created in the test
    #: environment are valid by default — no 2FA verification is needed."
    HAS_PAPER_ROUTE: bool = True

    #: The venue publishes its own filled orders on ``ORDERS_HISTORY_ROUTE``,
    #: which pages on its own ``pagination_key``, so ``get_my_trades`` reads
    #: ``list_fills`` and never refuses.
    PUBLISHES_FILL_HISTORY: bool = True

    def __init__(self) -> None:
        super().__init__(VENUE_ID)
        self._base_url = API_BASE
        self._app_key = ""
        self._app_signing_key = ""
        self._access_grant = ""
        self._account = ""
        self._session = None

    @property
    def account(self) -> str:
        """The account id ``connect`` read off ``ACCOUNTS_ROUTE``, which
        ``ORDER_ROUTE`` clears an order to."""
        return self._account

    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Hold ``api_key`` as the app key and ``api_secret`` as the app secret,
        read ``ACCOUNTS_ROUTE``, and answer whether it named an account.

        ``signature_self_proof`` runs first and refuses the session when this
        machine cannot reproduce the digest the venue publishes for its own
        worked example, so a signature defect is named here rather than read as
        a bad credential. ``paper`` picks ``SANDBOX_BASE`` over ``API_BASE``; the
        host joins the signature, so one host's signature does not work on the
        other.
        """
        self._base_url = SANDBOX_BASE if paper else API_BASE
        self._app_key = str(api_key or "")
        self._app_signing_key = str(api_secret or "")
        if not self._app_key or not self._app_signing_key:
            self._session_refusal = "no app key and app secret are stored"
            return False
        if not signature_self_proof():
            self._session_refusal = (
                "this build does not reproduce Webull's own published signature"
            )
            return False
        try:
            answered = await self._request("GET", ACCOUNTS_ROUTE)
        except Exception as exc:
            logger.error("Webull connection failed: %s", exc)
            self._session_refusal = str(exc)
            return False
        named = [
            str(row.get("account_id") or "")
            for row in reply_items(answered)
            if str(row.get("account_id") or "")
        ]
        if not named:
            self._session_refusal = "the venue named no account on this app key"
            return False
        self._account = named[0]
        self._connected = True
        logger.info(
            "Connected to Webull (%s): account=%s of %d",
            "sandbox" if paper else "LIVE",
            self._account,
            len(named),
        )
        return True

    async def disconnect(self) -> None:
        """Drop the held credentials, the held token and the held ``account``,
        and mark this broker disconnected."""
        self._app_key = ""
        self._app_signing_key = ""
        self._access_grant = ""
        self._account = ""
        self._connected = False
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as exc:
                logger.warning("Webull session already closed: %s", exc)
            self._session = None

    async def get_account(self) -> AccountInfo:
        """The account summary ``BALANCE_ROUTE`` publishes for the held
        ``account``.

        ``cash`` carries the venue's own ``total_cash_balance`` and
        ``buying_power`` the ``buying_power`` of its first currency block, which
        is the figure its own schema names "Buying Power".
        """
        if not self._account:
            return AccountInfo()
        answered = await self._request(
            "GET", BALANCE_ROUTE, query=(("account_id", self._account),)
        )
        row = answered if isinstance(answered, dict) else {}
        nested = row.get("data")
        held: dict = nested if isinstance(nested, dict) else row
        blocks = held.get("account_currency_assets")
        block = blocks[0] if isinstance(blocks, list) and blocks else {}
        if not isinstance(block, dict):
            block = {}
        equity = rule_number(held.get("total_net_liquidation_value")) or 0.0
        return AccountInfo(
            account_id=self._account,
            equity=equity,
            cash=rule_number(held.get("total_cash_balance")) or 0.0,
            buying_power=rule_number(block.get("buying_power")) or 0.0,
            portfolio_value=rule_number(held.get("total_market_value")) or equity,
        )

    async def get_positions(self) -> list[StockPosition]:
        """Every open position the held ``account`` carries, read off
        ``POSITIONS_ROUTE``.

        That route declares one query parameter and no page token, so one call
        answers the whole list.
        """
        if not self._account:
            return []
        answered = await self._request(
            "GET", POSITIONS_ROUTE, query=(("account_id", self._account),)
        )
        found: list[StockPosition] = []
        for row in reply_items(answered):
            built = self._position(row)
            if built is not None:
                found.append(built)
        return found

    async def get_position(self, symbol: str) -> Optional[StockPosition]:
        """The held account's position in ``symbol``, and None where
        ``get_positions`` answers none for it."""
        name = str(symbol or "")
        for held in await self.get_positions():
            if held.symbol == name:
                return held
        return None

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
        """Place one order on ``ORDER_ROUTE``, sized as the ``quantity`` unit
        count its own schema names.

        ``order_body`` composes the ticket and raises on an instrument type
        outside ``ORDER_INSTRUMENT_TYPES``, so an option and an event contract
        are refused here and reach no venue.
        """
        asset = self._asset(symbol)
        body = order_body(
            asset,
            str(symbol),
            side,
            quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
            account_id=self._account,
        )
        held_tif = published_time_in_force(asset, order_type, time_in_force)
        if held_tif is not time_in_force:
            logger.info(
                "Webull publishes no %s time in force for this product; sending "
                "%s for %s",
                getattr(time_in_force, "value", time_in_force),
                held_tif.value,
                symbol,
            )
        answered = await self._request("POST", ORDER_ROUTE, body=body)
        return self._parse_order(answered, symbol=str(symbol), body=body)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel one working order on ``CANCEL_ROUTE``, and answer False where
        the venue refused it or no ``account`` is held.

        That route takes the order's own ``client_order_id`` in its body, which
        is the id ``place_order`` wrote and ``_parse_order`` returned.
        """
        if not self._account or not order_id:
            return False
        try:
            await self._request(
                "POST",
                CANCEL_ROUTE,
                body={
                    "account_id": self._account,
                    "client_order_id": str(order_id),
                },
            )
        except Exception as exc:
            logger.warning("Webull cancel refused: %s", exc)
            return False
        return True

    async def get_order(self, order_id: str) -> StockOrder:
        """The status of one order, read off ``ORDER_ITEM_ROUTE`` by its own
        ``client_order_id``.

        The venue names this route the one that answers in real time: "This
        endpoint may not return the most recent order data in real time due to
        processing delays. To ensure you get the latest order status, please
        query the Order Detail endpoint by client_order_id."
        """
        if not self._account or not order_id:
            return StockOrder()
        answered = await self._request(
            "GET",
            ORDER_ITEM_ROUTE,
            query=(
                ("account_id", self._account),
                ("client_order_id", str(order_id)),
            ),
        )
        rows = order_items(answered)
        return self._status_order(rows[0] if rows else {}, order_id=str(order_id))

    async def get_open_orders(self) -> list[StockOrder]:
        """Every order ``ORDERS_OPEN_ROUTE`` publishes for the held account,
        walked on its own ``pagination_key``.

        That route publishes no page size, so the walk stops on the absent key
        and at ``ORDER_PAGES_MAX`` and never on a page length.
        """
        if not self._account:
            return []
        found: list[StockOrder] = []
        key = ""
        for _page in range(ORDER_PAGES_MAX):
            query = [("account_id", self._account)]
            if key:
                query.append((PAGINATION_FIELD, key))
            answered = await self._request("GET", ORDERS_OPEN_ROUTE, query=query)
            found.extend(self._status_order(row) for row in order_items(answered))
            key = next_page_key(answered)
            if not key:
                break
        return found

    async def get_quote(self, symbol: str) -> StockQuote:
        """The top of book one snapshot route publishes for ``symbol``.

        A crypto market takes ``CRYPTO_SNAPSHOT_ROUTE`` and every other market
        ``STOCK_SNAPSHOT_ROUTE``, each one keyed by the ``category`` its own
        schema requires.
        """
        asset = self._asset(symbol)
        crypto = instrument_word(asset) == "CRYPTO"
        route = CRYPTO_SNAPSHOT_ROUTE if crypto else STOCK_SNAPSHOT_ROUTE
        query = [("symbols", str(symbol))]
        query.append(("category", CRYPTO_CATEGORY if crypto else STOCK_CATEGORY))
        if not crypto:
            query.append(("extend_hour_required", "true"))
        answered = await self._request("GET", route, query=query)
        rows = reply_items(answered)
        row = rows[0] if rows else {}
        return StockQuote(
            symbol=str(symbol),
            bid=rule_number(row.get("bid")) or 0.0,
            ask=rule_number(row.get("ask")) or 0.0,
            last=rule_number(row.get("price")) or rule_number(row.get("close")) or 0.0,
            volume=int(rule_number(row.get("volume")) or 0.0),
            timestamp=time.time(),
            prev_close=rule_number(row.get("pre_close")) or 0.0,
        )

    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int = 100
    ) -> list[dict]:
        """The bars one bar route publishes for ``symbol``.

        A crypto market takes ``CRYPTO_BARS_ROUTE`` and a contract
        ``FUTURES_BARS_ROUTE``, both GET; an equity takes
        ``STOCK_BARS_ROUTE``, which its own schema declares as a POST with the
        same three required fields in a body. Futures bars need a paid
        subscription, which the venue states itself, so an unreadable answer
        logs and returns no bar.
        """
        asset = self._asset(symbol)
        word = instrument_word(asset)
        width = bar_width(timeframe)
        count = bar_count(limit)
        try:
            if word == "CRYPTO":
                answered = await self._request(
                    "GET",
                    CRYPTO_BARS_ROUTE,
                    query=(
                        ("symbols", str(symbol)),
                        ("category", CRYPTO_CATEGORY),
                        ("timespan", width),
                        ("count", str(count)),
                    ),
                )
            elif word == "FUTURES":
                answered = await self._request(
                    "GET",
                    FUTURES_BARS_ROUTE,
                    query=(
                        ("symbols", str(symbol)),
                        ("category", FUTURES_CATEGORY),
                        ("timespan", width),
                        ("count", str(count)),
                    ),
                )
            else:
                answered = await self._request(
                    "POST",
                    STOCK_BARS_ROUTE,
                    body={
                        "symbols": [str(symbol)],
                        "category": STOCK_CATEGORY,
                        "timespan": width,
                        "count": count,
                        "trading_sessions": BAR_SESSIONS,
                    },
                )
        except Exception as exc:
            logger.warning("Webull served no bar for %s: %s", symbol, exc)
            return []
        return self._bars(answered)

    async def get_market_status(self) -> dict:
        """A closed market, with ``NO_CLOCK_ROUTE`` naming the route this
        connector cannot open.

        The session that reaches an order is the one ``asset_session`` writes
        onto every recorded market, which ``sizing.outside_session`` and
        ``sizing.session_unit_rule`` read, so no caller needs this figure.
        """
        logger.info(NO_CLOCK_ROUTE, TRADE_CALENDAR_ROUTE)
        return {"is_open": False, "next_open": "", "next_close": ""}

    async def list_assets(self, status: str = "active") -> list[dict]:
        """Every instrument record the venue publishes for the held
        ``scan_symbols``, kept for ``held_assets`` and ``record_markets``.

        The three instrument routes are each read in ``SYMBOL_BATCH`` batches
        and each walked on its own ``pagination_key``, and ``tradable_market``
        keeps the records this platform can both size and order, so a record
        naming no sector or naming "Liquidate only" never becomes a recorded
        market.
        """
        del status
        names = sorted(self._scan_symbols)
        found: list[dict] = []
        refused: list[str] = []
        for route, category in (
            (STOCK_LIST_ROUTE, STOCK_CATEGORY),
            (CRYPTO_LIST_ROUTE, CRYPTO_CATEGORY),
            (FUTURES_LIST_ROUTE, FUTURES_CATEGORY),
        ):
            for batch in symbol_batches(names):
                for row in await self._instruments(route, category, batch):
                    symbol = str(row.get("symbol") or "")
                    if not symbol or symbol not in self._scan_symbols:
                        continue
                    if tradable_market(row):
                        found.append(row)
                        continue
                    refused.append(f"{symbol} ({instrument_word(row) or 'no type'})")
        self._assets = found
        if refused:
            logger.info(NO_TRADABLE_MARKET, len(refused), ", ".join(sorted(refused)))
        return list(self._assets)

    async def list_fills(
        self,
        symbol: str = "",
        since_ms: Optional[float] = None,
        until_ms: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Every fill ``ORDERS_HISTORY_ROUTE`` publishes for ``symbol``, walked
        on the venue's own ``pagination_key``.

        A short page is not the end here: the route publishes no page size at
        all, the walk stops when the key is absent and at ``ORDER_PAGES_MAX``,
        and ``is_fill`` keeps the filled and partly filled orders alone. The fee
        is attached from ``ORDER_ITEM_ROUTE``, bounded by ``FILL_FEE_READS_MAX``,
        because the history route publishes none.
        """
        if not self._account:
            return []
        found: list[dict] = []
        key = ""
        pages = 0
        for _page in range(ORDER_PAGES_MAX):
            query: list[tuple[str, str]] = [("account_id", self._account)]
            if since_ms is not None:
                query.append(("start_time", self._iso_moment(since_ms)))
            if until_ms is not None:
                query.append(("end_time", self._iso_moment(until_ms)))
            if key:
                query.append((PAGINATION_FIELD, key))
            answered = await self._request("GET", ORDERS_HISTORY_ROUTE, query=query)
            pages += 1
            name = str(symbol or "")
            for row in order_items(answered):
                if not is_fill(row):
                    continue
                built = fill_record(row)
                if name and built["symbol"] != name:
                    continue
                moment = rule_number(built.get("filled_time_ms"))
                if moment is not None and until_ms is not None and moment > until_ms:
                    continue
                if moment is not None and since_ms is not None and moment < since_ms:
                    continue
                found.append(built)
            key = next_page_key(answered)
            if not key:
                break
        logger.info(
            FILL_WALK_NOTE,
            len(found),
            pages,
            key or "the last",
            PAGINATION_FIELD,
            ORDER_PAGES_MAX,
        )
        kept = found if limit is None else found[: max(int(limit), 1)]
        await self._attach_fees(kept)
        return kept

    def market_rules(self, asset: Any) -> MarketRules:
        """The ``MarketRules`` one of this broker's own instrument records
        publishes, read through ``asset_rules`` with no broker contacted."""
        return asset_rules(asset)

    def asset_sector(self, asset: Any) -> Optional[str]:
        """The sector one of this broker's own instrument records names, read
        through ``asset_sector`` with no broker contacted."""
        return asset_sector(asset)

    async def _attach_fees(self, fills: list) -> None:
        """Read ``ORDER_ITEM_ROUTE`` per fill and write the venue's own fee onto
        each record, bounded by ``FILL_FEE_READS_MAX``.

        The history route publishes no fee, so a fill left unread keeps the None
        ``fill_record`` wrote and ``FILL_FEE_UNREAD_NOTE`` names how many, which
        keeps a zero from reading as the venue's own figure.
        """
        read = 0
        for held in fills:
            if read >= FILL_FEE_READS_MAX:
                break
            order_id = str(held.get("client_order_id") or "")
            if not order_id:
                continue
            try:
                answered = await self._request(
                    "GET",
                    ORDER_ITEM_ROUTE,
                    query=(
                        ("account_id", self._account),
                        ("client_order_id", order_id),
                    ),
                )
            except Exception as exc:
                logger.warning("Webull served no fee for order %s: %s", order_id, exc)
                continue
            read += 1
            rows = order_items(answered)
            fee = fee_total(rows[0]) if rows else None
            if fee is None:
                continue
            held["fee"] = fee
            held["fee_currency"] = FEE_CURRENCY
        carried = sum(1 for one in fills if one.get("fee") is not None)
        if len(fills) != carried:
            logger.info(
                FILL_FEE_UNREAD_NOTE,
                ORDER_ITEM_ROUTE,
                carried,
                len(fills),
                len(fills) - carried,
            )

    async def _instruments(self, route: str, category: str, names: list) -> list:
        """Every instrument record one route publishes for ``names``, walked on
        its own ``pagination_key``.

        A route that refuses the batch logs and answers no record, so one
        product the account has no permission for does not stop the other two.
        """
        found: list[dict] = []
        key = ""
        for _page in range(INSTRUMENT_PAGES_MAX):
            query = [("category", category)]
            if names:
                query.append(("symbols", ",".join(names)))
            if key:
                query.append((PAGINATION_FIELD, key))
            try:
                answered = await self._request("GET", route, query=query)
            except Exception as exc:
                logger.info("Webull served no record on %s: %s", route, exc)
                return found
            found.extend(reply_items(answered))
            key = next_page_key(answered)
            if not key:
                break
        return found

    def _asset(self, symbol: Any) -> dict:
        """The held instrument record naming ``symbol``, and {} where no record
        does."""
        name = str(symbol or "")
        for held in self._assets:
            if isinstance(held, dict) and str(held.get("symbol") or "") == name:
                return held
        return {}

    @staticmethod
    def _iso_moment(moment_ms: Any) -> str:
        """``moment_ms`` as the ISO 8601 UTC moment the orders routes take.

        Quoted whole from the route's own schema: "Format:
        yyyy-MM-dd'T'HH:mm:ss.SSS'Z'."
        """
        held = rule_number(moment_ms)
        if held is None:
            return ""
        when = datetime.fromtimestamp(held / 1000.0, tz=timezone.utc)
        return when.strftime("%Y-%m-%dT%H:%M:%S.") + f"{when.microsecond // 1000:03d}Z"

    @staticmethod
    def _bars(answered: Any) -> list[dict]:
        """Every bar one bar reply carries, read off the ``result`` array each
        symbol's own row nests its candles under.

        ``bar_rows`` unwraps the one shape ``CRYPTO_BARS_ROUTE`` answers and the
        doubly nested one ``STOCK_BARS_ROUTE`` answers, and each row carries the
        six names ``broker_exchange.candle_rows`` reads.
        """
        found: list[dict] = []
        for one in bar_rows(answered):
            found.append(
                {
                    "timestamp": bar_stamp(one.get("time")),
                    "open": rule_number(one.get("open")) or 0.0,
                    "high": rule_number(one.get("high")) or 0.0,
                    "low": rule_number(one.get("low")) or 0.0,
                    "close": rule_number(one.get("close")) or 0.0,
                    "volume": rule_number(one.get("volume")) or 0.0,
                }
            )
        return found

    @staticmethod
    def _position(row: Any) -> Optional[StockPosition]:
        """One position record as a ``StockPosition``, and None for a row naming
        no symbol.

        ``cost_basis`` carries the record's own ``cost_price`` and
        ``unrealized_pnl`` its own ``unrealized_profit_loss``, which are two of
        the four figures this venue publishes.
        """
        if not isinstance(row, dict):
            return None
        symbol = str(row.get("symbol") or "")
        if not symbol:
            return None
        units = rule_number(row.get("quantity")) or 0.0
        cost = rule_number(row.get("cost_price")) or 0.0
        last = rule_number(row.get("last_price")) or 0.0
        unrealised = rule_number(row.get("unrealized_profit_loss")) or 0.0
        basis = abs(cost * units)
        return StockPosition(
            symbol=symbol,
            quantity=units,
            avg_entry_price=cost,
            current_price=last,
            market_value=units * last,
            unrealized_pnl=unrealised,
            unrealized_pnl_pct=0.0 if basis <= 0.0 else unrealised / basis * 100.0,
            side=PositionSide.LONG if units >= 0.0 else PositionSide.SHORT,
        )

    @staticmethod
    def _parse_order(answered: Any, symbol: str, body: dict) -> StockOrder:
        """The order ``ORDER_ROUTE`` acknowledged, read off its own flat reply of
        ``client_order_id``, ``client_combo_order_id``, ``combo_order_id`` and
        ``order_id``.

        That reply names those four ids and no status and no size, so the ticket
        ``order_body`` composed carries the side, the type, the size and the
        price.
        """
        row = answered if isinstance(answered, dict) else {}
        items = body.get("new_orders") if isinstance(body, dict) else None
        item = items[0] if isinstance(items, list) and items else {}
        if not isinstance(item, dict):
            item = {}
        return StockOrder(
            order_id=str(
                row.get("client_order_id")
                or row.get("order_id")
                or item.get("client_order_id")
                or ""
            ),
            symbol=symbol,
            side=(
                OrderSide.SELL
                if str(item.get("side") or "") == VENUE_SIDES[OrderSide.SELL]
                else OrderSide.BUY
            ),
            order_type=order_type_named(item.get("order_type")),
            quantity=rule_number(item.get("quantity")) or 0.0,
            limit_price=rule_number(item.get("limit_price")) or 0.0,
            stop_price=rule_number(item.get("stop_price")) or 0.0,
            time_in_force=time_in_force_named(item.get("time_in_force")),
            status=str(row.get("status") or "new"),
            filled_qty=rule_number(row.get("filled_quantity")) or 0.0,
            avg_fill_price=rule_number(row.get("filled_price")) or 0.0,
            submitted_at=time.time(),
        )

    @staticmethod
    def _status_order(answered: Any, order_id: str = "") -> StockOrder:
        """One order record as a ``StockOrder``, carrying the venue's own status
        and filled figures."""
        row = answered if isinstance(answered, dict) else {}
        return StockOrder(
            order_id=str(row.get("client_order_id") or row.get("order_id") or order_id),
            symbol=str(row.get("symbol") or ""),
            side=(
                OrderSide.SELL
                if str(row.get("side") or "").strip().upper()
                == VENUE_SIDES[OrderSide.SELL]
                else OrderSide.BUY
            ),
            order_type=order_type_named(row.get("order_type")),
            quantity=rule_number(row.get("total_quantity")) or 0.0,
            limit_price=rule_number(row.get("limit_price")) or 0.0,
            stop_price=rule_number(row.get("stop_price")) or 0.0,
            time_in_force=time_in_force_named(row.get("time_in_force")),
            status=str(row.get("status") or "new"),
            filled_qty=rule_number(row.get("filled_quantity")) or 0.0,
            avg_fill_price=rule_number(row.get("filled_price")) or 0.0,
        )

    async def _request(
        self,
        method: str,
        path: str,
        query: Iterable[tuple[str, str]] = (),
        body: Optional[dict] = None,
    ) -> Any:
        """One signed request to ``_base_url``.

        The body is serialised once and that one text both signs and sends: the
        venue's own FAQ names the alternative as the cause of a misleading
        error, "The JSON body used for MD5 computation differs from what's
        actually sent in the request". A status of 204 answers {}, a status
        outside 200 and 201 raises with the body the venue answered, and a body
        that is no JSON raises as well.
        """
        import aiohttp

        held_query = [(str(name), str(value)) for name, value in query]
        body_text = json.dumps(body, separators=(",", ":")) if body is not None else ""
        host = urllib.parse.urlsplit(self._base_url).netloc
        signing = {
            "x-app-key": self._app_key,
            "x-timestamp": signed_timestamp(),
            "x-signature-algorithm": SIGNATURE_ALGORITHM,
            "x-signature-version": SIGNATURE_VERSION,
            "x-signature-nonce": uuid.uuid4().hex,
            "host": host,
        }
        headers = dict(signing)
        headers["x-version"] = API_VERSION
        headers["x-signature"] = request_signature(
            self._app_signing_key, path, held_query, body_text, signing
        )
        headers["Accept"] = "application/json"
        headers["Content-Type"] = "application/json"
        if self._access_grant:
            headers["x-access-token"] = self._access_grant
        if self._session is None:
            self._session = aiohttp.ClientSession()
        url = self._base_url + path
        if held_query:
            url = f"{url}?{urllib.parse.urlencode(held_query)}"
        async with self._session.request(
            method, url, headers=headers, data=body_text or None
        ) as resp:
            if resp.status == 204:
                return {}
            text = await resp.text()
            if resp.status not in (200, 201):
                raise ValueError(f"Webull API {resp.status}: {text}")
            try:
                return json.loads(text) if text else {}
            except ValueError as exc:
                raise ValueError(f"Webull answered no JSON on {path}: {exc}") from exc


__all__ = [
    "ACCOUNTS_ROUTE",
    "API_BASE",
    "API_VERSION",
    "BALANCE_ROUTE",
    "BAR_COUNT_MAX",
    "BAR_SESSIONS",
    "BAR_WIDTHS",
    "CANCEL_ROUTE",
    "CATEGORY_INSTRUMENT_TYPES",
    "CLIENT_ORDER_ID_MAX",
    "COMBO_TYPE_NORMAL",
    "COMMISSION_FIELD",
    "COMMISSION_VALUE_FIELD",
    "CRYPTO_BARS_ROUTE",
    "CRYPTO_CATEGORY",
    "CRYPTO_LIST_ROUTE",
    "CRYPTO_MARKET_TIME_IN_FORCE",
    "CRYPTO_MIN_ORDER_SIZE",
    "CRYPTO_MIN_ORDER_USD",
    "CRYPTO_POSITION_FLOOR_USD",
    "CRYPTO_QUANTITY_PRECISION",
    "CRYPTO_SNAPSHOT_ROUTE",
    "CRYPTO_TIMES_IN_FORCE",
    "DECIMAL_PLACES",
    "DEFAULT_BAR_WIDTH",
    "DEFAULT_TIME_IN_FORCE",
    "DIGEST_KEY_TRAILER",
    "ENTRUST_AMOUNT",
    "ENTRUST_QTY",
    "EQUITY_FRACTION_FIELD",
    "FEES_FIELD",
    "FEE_CURRENCY",
    "FEE_VALUE_FIELD",
    "FILL_FEE_READS_MAX",
    "FILL_FEE_UNREAD_NOTE",
    "FILL_SIDES",
    "FILL_STATUSES",
    "FILL_WALK_NOTE",
    "FRACTIONAL_ORDER_USD_MIN",
    "FRACTIONAL_QUANTITY_MAX",
    "FUTURES_BARS_ROUTE",
    "FUTURES_CATEGORY",
    "FUTURES_CLASS_SECTORS",
    "FUTURES_DEFAULT_SECTOR",
    "FUTURES_LIST_ROUTE",
    "FUTURES_MARKER_FIELDS",
    "FUTURES_PRODUCT_SECTORS",
    "INSTRUMENT_PAGES_MAX",
    "INSTRUMENT_TYPE_SECTORS",
    "MARKET_CODE",
    "NO_CLOCK_ROUTE",
    "NO_INSTRUMENT_TYPE",
    "NO_ORDER_INSTRUMENT_TYPE",
    "NO_TRADABLE_MARKET",
    "ORDERS_HISTORY_ROUTE",
    "ORDERS_OPEN_ROUTE",
    "ORDER_INSTRUMENT_TYPES",
    "ORDER_ITEM_ROUTE",
    "ORDER_PAGES_MAX",
    "ORDER_ROUTE",
    "ORDER_TRADING_SESSION",
    "ORDER_TYPE_LIMIT",
    "ORDER_TYPE_MARKET",
    "ORDER_TYPE_STOP",
    "ORDER_TYPE_STOP_LIMIT",
    "OVERNIGHT_FIELD",
    "PAGINATION_FIELD",
    "POSITIONS_ROUTE",
    "SANDBOX_BASE",
    "SECTOR_INSTRUMENT_TYPES",
    "SESSION_ALL",
    "SESSION_CORE",
    "SESSION_NIGHT",
    "SIGNATURE_ALGORITHM",
    "SIGNATURE_PROOF_BODY",
    "SIGNATURE_PROOF_DIGEST",
    "SIGNATURE_PROOF_HEADERS",
    "SIGNATURE_PROOF_KEY",
    "SIGNATURE_PROOF_PATH",
    "SIGNATURE_PROOF_QUERY",
    "SIGNATURE_VERSION",
    "SIGNED_PART_SEPARATOR",
    "SIGNING_HEADER_NAMES",
    "STATUS_FILLED",
    "STATUS_PARTIAL_FILLED",
    "STATUS_TRADABLE",
    "STOCK_BARS_ROUTE",
    "STOCK_CATEGORY",
    "STOCK_LIST_ROUTE",
    "STOCK_SNAPSHOT_ROUTE",
    "SYMBOL_BATCH",
    "TIMESTAMP_FORMAT",
    "TRADE_CALENDAR_ROUTE",
    "VENUE_ID",
    "VENUE_ORDER_TYPES",
    "VENUE_PRODUCT_TIMES_IN_FORCE",
    "VENUE_SIDES",
    "VENUE_TIMES_IN_FORCE",
    "WHOLE_UNIT_INCREMENT",
    "WebullConnector",
    "asset_expiry_ms",
    "asset_order_types",
    "asset_rules",
    "asset_sector",
    "asset_session",
    "bar_count",
    "bar_rows",
    "bar_stamp",
    "bar_width",
    "client_order_id",
    "contract_size",
    "decimal_text",
    "fee_total",
    "fill_record",
    "futures_sector",
    "increment_rule",
    "instrument_word",
    "is_fill",
    "iso_moment",
    "minimum_cost",
    "next_page_key",
    "order_body",
    "order_items",
    "order_type_named",
    "product_code",
    "published_time_in_force",
    "reply_items",
    "request_signature",
    "rule_number",
    "signature_self_proof",
    "signature_string",
    "signed_timestamp",
    "size_increment",
    "symbol_batches",
    "time_in_force_named",
    "tradable_market",
]
