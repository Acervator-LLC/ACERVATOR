"""
tastytrade_connector.py — tastytrade broker connector.

``TastytradeConnector`` answers ``BrokerBase`` for ``VENUE_ID``, so
``MainWindow._connect_broker_for_bot`` builds it and ``BotContainer`` reaches it
through ``BrokerExchange``. ``INSTRUMENT_TYPE_SECTORS``,
``FUTURES_PRODUCT_SECTORS``, ``MARKET_SECTOR_SECTORS`` and ``asset_sector``
carry the product vocabulary tastytrade's own OpenAPI documents and product
pages publish. ``ORDER_ROUTE`` names the one order route its own API host serves
for every sector, and ``order_body`` composes the ticket that route's own schema
declares.
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Optional

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

logger = logging.getLogger("acervator.stocks.tastytrade")

#: The venue id this broker registers under, which ``BROKER_CONNECTORS`` keys,
#: ``TastytradeConnector.exchange_id`` answers and the sector tables in
#: ``trading.scrumming.sizing`` are keyed by.
VENUE_ID = "tastytrade"

#: The two hosts tastytrade's own OpenAPI documents name as their servers, read
#: 2026-10-11 from ``developer.tastytrade.com/openapi/orders.json`` with no
#: credential sent: 16 documents, openapi 3.1.0, 1,372,922 bytes, 84 paths. A
#: client registered in one environment does not work in the other.
API_BASE = "https://api.tastyworks.com"
SANDBOX_BASE = "https://api.cert.tastyworks.com"

#: The header every request carries, in the ``product/version`` form the venue
#: requires. Quoted whole from its own error-handling page: "tastytrade requires
#: a ``User-Agent`` header in the format ``product/version``... If it is missing
#: or malformed you get a 401 -- even when your token is valid -- and the body is
#: an HTML nginx page rather than the JSON envelope."
USER_AGENT = "acervator/1.0"

#: The route that exchanges a refresh token for an access token. Its own page
#: names the three fields it requires: ``grant_type``, ``refresh_token`` and
#: ``client_secret``.
GRANT_ROUTE = "/oauth/token"
GRANT_TYPE_WORD = "refresh_token"

#: The seconds an access token is valid for, and the margin ``_held_bearer``
#: refreshes inside. Quoted whole: "Access tokens are signed JWTs valid for 15
#: minutes. An expired token returns HTTP 401."
BEARER_SECONDS = 900.0
BEARER_MARGIN_SECONDS = 60.0

#: The one order route the venue serves, which every sector's order takes. Its
#: own ``operationId`` is ``postAccountsAccountNumberOrders`` and its summary is
#: "Submit Order".
ORDER_ROUTE = "/accounts/{account}/orders"

#: The route each read this connector makes takes, each one named in the same
#: document set. ``TRANSACTIONS_ROUTE`` is the fill ledger and
#: ``TOTAL_FEES_ROUTE`` the venue's own fee total for one day.
ACCOUNTS_ROUTE = "/customers/me/accounts"
BALANCES_ROUTE = "/accounts/{account}/balances"
POSITIONS_ROUTE = "/accounts/{account}/positions"
ORDERS_LIVE_ROUTE = "/accounts/{account}/orders/live"
ORDER_ITEM_ROUTE = "/accounts/{account}/orders/{order_id}"
TRANSACTIONS_ROUTE = "/accounts/{account}/transactions"
TOTAL_FEES_ROUTE = "/accounts/{account}/transactions/total-fees"
MARKET_DATA_ROUTE = "/market-data/by-type"
SYMBOL_SEARCH_ROUTE = "/symbols/search/{symbol}"
EQUITY_SESSION_ROUTE = "/market-time/equities/sessions/current"
CRYPTO_LIST_ROUTE = "/instruments/cryptocurrencies"
EQUITY_LIST_ROUTE = "/instruments/equities"
FUTURES_LIST_ROUTE = "/instruments/futures"
PRECISION_ROUTE = "/instruments/quantity-decimal-precisions"

#: The rows one page of ``TRANSACTIONS_ROUTE`` answers and the page the walk
#: stops at. The route's own schema gives ``per-page`` a default of 250 and a
#: maximum of 2000, and its own pagination guide states the rate discipline:
#: "Keep ``per-page`` modest and page steadily rather than hammering the
#: endpoint -- a burst of rapid requests can earn an HTTP 429." So the walk asks
#: the venue's own default and not its maximum.
TRANSACTION_PAGE_SIZE = 250
TRANSACTION_PAGES_MAX = 100

#: The rows one page of ``ORDERS_LIVE_ROUTE`` answers. That route's own schema
#: defaults ``per-page`` to 100 and caps it at 200, and the searchable orders
#: route defaults to 10, so a reader taking a default reads ten orders and reads
#: a fleet's book as ten rows. This asks the published maximum.
ORDER_PAGE_SIZE = 200

#: The reply block and field that end the walk. The venue's own pagination guide
#: states the condition word for word: "you are on the last page when
#: ``page-offset + 1 >= pagination.total-pages``".
PAGINATION_FIELD = "pagination"
TOTAL_PAGES_FIELD = "total-pages"

#: The sector each instrument type tastytrade names belongs to. Its own order
#: schema closes the order-leg vocabulary at eight words and its own condition
#: schema holds fourteen; the six in the wide list and not the narrow one --
#: ``Bond``, ``Currency Pair``, ``Equity Offering``, ``Index``, ``Unknown`` and
#: ``Warrant`` -- can trigger a condition and cannot be an order leg. Its own
#: Instruments & Symbology page says the same in prose: "An instrument is any
#: single tradeable security at tastytrade: an equity, equity option, future,
#: future option, or cryptocurrency."
#:
#: Five types are mapped here and the rest are not. ``Equity Option`` and
#: ``Future Option`` name options, which is no sector this platform draws;
#: ``Event Contract`` names its own Prediction Markets product; and
#: ``Fixed Income Security``, ``Bond``, ``Warrant``, ``Equity Offering`` and
#: ``Liquidity Pool`` name no sector either. ``Index`` and ``Currency Pair`` map
#: to a sector for the recording and take no order, and ``order_body`` refuses a
#: leg naming one; the index future and the currency future carry those two
#: sectors.
INSTRUMENT_TYPE_SECTORS: dict[str, str] = {
    "cryptocurrency": "crypto",
    "currency pair": "forex",
    "equity": "stocks",
    "future": "futures_perps",
    "index": "indices",
}

#: The eight words the order route's own ``legs[].instrument-type`` enum holds.
#: A record whose type is outside this set records its market and takes no
#: order.
ORDER_LEG_INSTRUMENT_TYPES: frozenset[str] = frozenset(
    {
        "cryptocurrency",
        "equity",
        "equity option",
        "event contract",
        "fixed income security",
        "future",
        "future option",
        "liquidity pool",
    }
)

#: The sector each futures product code belongs to, off the nine families
#: tastytrade's own Available Futures Products page names, read 2026-10-11. The
#: page names 68 product codes and every one answers live on its own
#: credential-free ``/symbols/search/`` route as ``instrument-type`` ``Future``,
#: where two invented codes answer nothing. Per sector: commodities 27, indices
#: 14, forex 11, crypto 5, and the 11 Interest Rate contracts absent, their
#: family naming no sector this platform draws. An absent code is a dated
#: contract still, so ``futures_sector`` reads it as ``FUTURES_SECTOR``.
FUTURES_PRODUCT_SECTORS: dict[str, str] = {
    "ES": "indices",
    "MES": "indices",
    "NES": "indices",
    "NQ": "indices",
    "MNQ": "indices",
    "NNQ": "indices",
    "YM": "indices",
    "MYM": "indices",
    "NDOW": "indices",
    "RTY": "indices",
    "M2K": "indices",
    "N2K": "indices",
    "VX": "indices",
    "VXM": "indices",
    "6E": "forex",
    "M6E": "forex",
    "6J": "forex",
    "6B": "forex",
    "M6B": "forex",
    "6C": "forex",
    "MCD": "forex",
    "6A": "forex",
    "M6A": "forex",
    "6M": "forex",
    "6S": "forex",
    "CL": "commodities",
    "MCL": "commodities",
    "QM": "commodities",
    "NG": "commodities",
    "MNG": "commodities",
    "QG": "commodities",
    "RB": "commodities",
    "HO": "commodities",
    "BZ": "commodities",
    "GC": "commodities",
    "MGC": "commodities",
    "1OZ": "commodities",
    "HG": "commodities",
    "MHG": "commodities",
    "SI": "commodities",
    "SIL": "commodities",
    "SIC": "commodities",
    "PL": "commodities",
    "PA": "commodities",
    "ZC": "commodities",
    "XC": "commodities",
    "ZS": "commodities",
    "XK": "commodities",
    "ZW": "commodities",
    "XW": "commodities",
    "LE": "commodities",
    "HE": "commodities",
    "BTC": "crypto",
    "MBT": "crypto",
    "ETH": "crypto",
    "MET": "crypto",
    "MXP": "crypto",
}

#: The sector each word ``FutureProduct.market-sector`` carries belongs to. That
#: field is the record's own answer -- "Market sector classification", whose
#: published example is "Equity Index" -- and these are the nine family names its
#: own product page publishes, lowercased. ``futures_sector`` reads the record's
#: own word ahead of ``FUTURES_PRODUCT_SECTORS``, so a product code the page does
#: not name still records under the sector the venue assigns it.
MARKET_SECTOR_SECTORS: dict[str, str] = {
    "agriculture": "commodities",
    "cryptocurrency": "crypto",
    "energy": "commodities",
    "equity index": "indices",
    "foreign currency": "forex",
    "livestock": "commodities",
    "metals": "commodities",
    "volatility": "indices",
}

#: The sector a dated contract naming no family falls to: the contract form,
#: which is the sector this platform draws for a dated contract.
FUTURES_SECTOR = "futures_perps"

#: The instrument type naming a dated contract, whose sector is its family.
FUTURE_INSTRUMENT_TYPE = "future"

#: The instrument type whose own market records under ``SESSION_CONTINUOUS``.
CRYPTO_INSTRUMENT_TYPE = "cryptocurrency"

#: The instrument type whose own market records under ``SESSION_US_EQUITY``.
EQUITY_INSTRUMENT_TYPE = "equity"

#: The leading character tastytrade puts before a futures symbol, which every
#: one of its 68 product codes carries and no equity symbol does. Its own
#: symbology page: "Futures symbols start with a ``/`` followed by a contract
#: code".
FUTURES_SYMBOL_PREFIX = "/"

#: The leading pair tastytrade puts before a future option symbol, which its own
#: symbology page spells ``./``. No sector this platform draws holds one.
FUTURE_OPTION_SYMBOL_PREFIX = "./"

#: The separator tastytrade puts between the two legs of a currency pair and of
#: a crypto pair, as in ``EUR/USD`` and ``BTC/USD``. The instrument type tells
#: the two apart on every record, and ``currency_pair_symbol`` tells them apart
#: on a bare symbol.
PAIR_SYMBOL_SEPARATOR = "/"

#: Every currency leg tastytrade's own Available Currency Pairs page names, read
#: 2026-10-11 under its headline "Forex trading offered through tastyfx includes
#: 20 US dollar pairs and 60+ non-USD pairs". A pair carrying a leg of this set
#: on both sides holds two currencies, which places it in the forex sector.
#: ``NOK`` is here and is also Nokia's listed equity, and ``SGD`` is here and
#: bases no equity; the venue's own symbology separates both, writing a currency
#: market as two codes joined by a slash and a company as a bare code. ``AMD``
#: and ``COP`` are absent, so each stays the equity its own ``Equity`` word
#: names.
CURRENCY_LEGS: frozenset[str] = frozenset(
    {
        "AUD",
        "CAD",
        "CHF",
        "CNH",
        "CZK",
        "DKK",
        "EUR",
        "GBP",
        "HKD",
        "HUF",
        "ILS",
        "JPY",
        "MXN",
        "NOK",
        "NZD",
        "PLN",
        "SEK",
        "SGD",
        "TRY",
        "USD",
        "ZAR",
    }
)

#: The order type each ``OrderType`` composes, spelled as the order route's own
#: ``order-type`` enum spells it: ``Limit``, ``Market``, ``Marketable Limit``,
#: ``Notional Market``, ``Stop`` and ``Stop Limit``. ``TRAILING_STOP`` is
#: absent, the enum holding no trailing word.
ORDER_TYPE_MARKET = "Market"
ORDER_TYPE_LIMIT = "Limit"
VENUE_ORDER_TYPES: dict[Any, str] = {
    OrderType.MARKET: ORDER_TYPE_MARKET,
    OrderType.LIMIT: ORDER_TYPE_LIMIT,
    OrderType.STOP: "Stop",
    OrderType.STOP_LIMIT: "Stop Limit",
}

#: The leg action each side composes. ``Buy`` and ``Sell`` are the words the
#: venue reserves for a contract -- its own schema says so: "Note: ``Buy`` and
#: ``Sell`` are only applicable to Futures orders" -- and every other market
#: opens with ``Buy to Open`` and reduces with ``Sell to Close``, the shape a
#: scrum and a fold take.
FUTURES_LEG_ACTIONS: dict[Any, str] = {OrderSide.BUY: "Buy", OrderSide.SELL: "Sell"}
LEG_ACTIONS: dict[Any, str] = {
    OrderSide.BUY: "Buy to Open",
    OrderSide.SELL: "Sell to Close",
}

#: The direction each side writes into ``price-effect``, whose own enum holds
#: ``Credit`` and ``Debit``. A price on this venue is a magnitude and its
#: direction is a separate word, so a buy pays and a sell receives.
PRICE_EFFECTS: dict[Any, str] = {OrderSide.BUY: "Debit", OrderSide.SELL: "Credit"}

#: The times in force the ``time-in-force`` field's own enum holds: ``Day``,
#: ``Ext``, ``Ext Overnight``, ``GTC``, ``GTC Ext``, ``GTC Ext Overnight``,
#: ``GTD`` and ``IOC``. ``TimeInForce.FOK``, ``TimeInForce.OPG`` and
#: ``TimeInForce.CLS`` are in none of them, so an order composed with one of
#: those would carry a value the venue does not take. The four ``Ext`` words
#: reach the extended and overnight sessions and this platform sends none of
#: them, so an order it composes works inside the regular session alone.
VENUE_TIMES_IN_FORCE: dict[Any, str] = {
    TimeInForce.DAY: "Day",
    TimeInForce.GTC: "GTC",
    TimeInForce.IOC: "IOC",
}

#: The time in force an order carrying one this venue does not publish falls to.
DEFAULT_TIME_IN_FORCE = TimeInForce.DAY

#: The ``automated-source`` value every order carries. Quoted whole from the
#: field's own description: "If the order was placed from an automated source",
#: with a default of false. This platform transmits with no human intervention,
#: so the flag reads True; Interactive Brokers' ``manualIndicator`` reads the
#: same fact the other way round, and carrying either from the other's habit
#: would mis-declare every order.
AUTOMATED_SOURCE = True

#: The decimal places a figure serialises to. Every money and size field on this
#: venue is a string: its own schema says "Decimal value serialized as a JSON
#: string (e.g. 150.25)" on each one, and ``decimal_text`` writes a plain decimal
#: so a step of 1e-08 never reaches the venue in exponent form.
DECIMAL_PLACES = 10

#: The size step a crypto market takes. Quoted whole from
#: ``/instruments/quantity-decimal-precisions``' own description: "The ``value``
#: defines how many decimal places a quantity may use; for example BTC/USD has a
#: precision of 8, so ``0.12345678`` is valid but ``0.123456789`` is not. A value
#: of 0 means the instrument must trade in whole numbers."
CRYPTO_QUANTITY_PRECISION = 8
CRYPTO_MIN_ORDER_SIZE = 1e-8

#: The size step a market takes where the venue publishes no finer one: one
#: whole unit, which is a share, a contract or a fund share.
WHOLE_UNIT_INCREMENT = 1.0

#: The field and the step an equity whose own record flags it takes. The grain is
#: the market and not the venue:
#: ``Equity.is-fractional-quantity-eligible`` is "Whether the equity can be
#: traded in fractional share quantities", and the venue's own pricing table
#: names "Fractional Shares" as a product line at $0 to open and $0 to close. An
#: equity the recording holds no flag for keeps ``WHOLE_UNIT_INCREMENT``.
EQUITY_FRACTION_FIELD = "is-fractional-quantity-eligible"
EQUITY_FRACTION_INCREMENT = 1e-6

#: The collection word ``Equity.market-time-instrument-collection`` carries for a
#: market whose hours are the US equity session. Its own
#: ``/market-time/equities/sessions/current`` route publishes those hours without
#: a credential: a pre-market ``start-at`` at 12:15 UTC, an ``open-at`` at 13:30
#: UTC, a ``close-at`` at 20:00 UTC and a ``close-at-ext`` at 00:00 UTC, which is
#: 08:15, 09:30, 16:00 and 20:00 Eastern.
EQUITY_SESSION_COLLECTION = "equity"

#: The transaction type naming a fill. ``Transaction.transaction-type`` holds
#: four words -- ``Administrative Transfer``, ``Money Movement``,
#: ``Receive Deliver`` and ``Trade`` -- and only the last is a trade.
FILL_TRANSACTION_TYPE = "trade"

#: Every fee field one transaction record carries, each paired with its own
#: ``-effect``. Interactive Brokers publishes one ``commission``; this venue
#: publishes six components and the fee on one fill is their sum.
FEE_FIELDS = (
    "commission",
    "clearing-fees",
    "regulatory-fees",
    "proprietary-index-option-fees",
    "currency-conversion-fees",
    "other-charge",
)

#: The ``-effect`` word that makes a fee component a charge against the account,
#: and the word that makes it a credit back.
EFFECT_DEBIT = "debit"
EFFECT_CREDIT = "credit"

#: The currency a fee figure is read in where the record names none, which
#: ``BrokerBase.CASH_CURRENCY`` also names for the ledger row.
FEE_CURRENCY = "USD"

#: The side each ``Transaction.action`` word names. ``Allocate`` is in the enum
#: and is neither a buy nor a sell this platform places.
FILL_SIDES = {
    "buy": OrderSide.BUY.value,
    "buy to close": OrderSide.BUY.value,
    "buy to open": OrderSide.BUY.value,
    "sell": OrderSide.SELL.value,
    "sell to close": OrderSide.SELL.value,
    "sell to open": OrderSide.SELL.value,
}

#: What ``get_bars`` logs so no caller reads an empty answer as a venue with no
#: price history. Over all 84 published paths the names holding ``candle``,
#: ``bar`` and ``ohlc`` number 0 each, where ``quote`` names 3; the venue's
#: candles are Candle events on its DXLink streamer, which takes an API quote
#: token and a WebSocket this connector does not open.
NO_BAR_ROUTE = (
    "tastytrade publishes no REST bar route for %s; its candles are Candle "
    "events on its DXLink streamer behind %s, which this connector does not open"
)

#: What ``order_body`` refuses with. The venue's own order-leg enum holds eight
#: instrument types and its condition enum holds fourteen, so an ``Index`` or a
#: ``Currency Pair`` market is read and charted and takes no order.
NO_ORDER_LEG_TYPE = (
    "tastytrade publishes no order leg for instrument type {word!r}; the "
    "route's own enum holds {published}"
)

#: What ``order_body`` refuses a symbol it holds no record for with. Every leg
#: the order route takes names an ``instrument-type``, and there is no safe
#: default: an equity word on a futures symbol would name a contract as a share,
#: so no order is sent for a market this connector did not read.
NO_INSTRUMENT_TYPE = (
    "tastytrade named no instrument type for {symbol!r}, so no order is sent; "
    "its own record carries the type each order leg requires"
)

#: What ``list_assets`` logs for each held symbol ``tradable_market`` refuses, so
#: the operator reads which market was dropped and which type dropped it. An
#: ``Index`` and a ``Currency Pair`` are each in the venue's own condition enum
#: and in neither the order-leg enum nor its own five tradeable kinds, so
#: recording one would let a cited order-type row claim a market order for a
#: market that takes no order at all.
NO_TRADABLE_MARKET = (
    "tastytrade takes no order in %d held symbol(s), so none is recorded as a "
    "market: %s"
)

#: The query parameter ``MARKET_DATA_ROUTE`` takes per instrument type, whose own
#: description names its gate: "The combined number of symbols across all type
#: parameters is capped at 100 per request... Available to funded account holders
#: only; no delayed quotes are served over REST."
QUOTE_TYPE_PARAMETERS = {
    "cryptocurrency": "cryptocurrency",
    "equity": "equity",
    "future": "future",
    "index": "index",
}
DEFAULT_QUOTE_TYPE_PARAMETER = "equity"


def rule_number(value: Any) -> Optional[float]:
    """``value`` as a positive finite float where the record published a number
    or a decimal string, else None.

    Every money and size field on this venue is a decimal string, so a string is
    a published rule and a step of zero is not one.
    """
    if type(value) not in (int, float, str):
        return None
    try:
        parsed = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0.0:
        return None
    return parsed


def decimal_text(value: Any) -> str:
    """``value`` as the plain decimal string every field on this order route
    takes, and "" where it is no finite number.

    A step of 1e-08 formats as ``0.00000001`` and never as ``1e-08``, which the
    schema's own ``type: string, format: decimal`` requires.
    """
    if type(value) not in (int, float):
        return ""
    held = float(value)
    if not math.isfinite(held):
        return ""
    written = f"{held:.{DECIMAL_PLACES}f}".rstrip("0").rstrip(".")
    return written or "0"


def instrument_word(asset: Any) -> str:
    """The instrument type one record names, lowercased, and "" for a record
    naming none.

    ``instrument-type`` is the field every instrument, position, order and
    transaction record carries, and ``underlying-instrument-type`` is the same
    word on an order.
    """
    if not isinstance(asset, dict):
        return ""
    for field in ("instrument-type", "underlying-instrument-type"):
        held = asset.get(field)
        if isinstance(held, str) and held.strip():
            return held.strip().lower()
    return ""


def product_code(asset: Any) -> str:
    """The futures product code one record names, off its own ``product-code``
    or parsed from its contract symbol.

    ``Future.product-code`` is published, and a symbol alone is read by dropping
    ``FUTURES_SYMBOL_PREFIX`` and the trailing month and year digits, as in
    ``/ESZ6`` to ``ES``.
    """
    if not isinstance(asset, dict):
        return ""
    named = asset.get("product-code") or asset.get("normalized-symbol")
    if isinstance(named, str) and named.strip():
        return named.strip().upper()
    symbol = str(asset.get("symbol") or "").strip().upper()
    if not symbol.startswith(FUTURES_SYMBOL_PREFIX):
        return ""
    held = symbol[len(FUTURES_SYMBOL_PREFIX) :]
    stripped = held.rstrip("0123456789")
    if stripped == held or not stripped:
        return held
    return stripped[:-1] or stripped


def currency_pair_symbol(symbol: Any) -> bool:
    """Whether ``symbol`` names one of this venue's currency pairs.

    A pair carries ``PAIR_SYMBOL_SEPARATOR`` with a member of ``CURRENCY_LEGS``
    on each side, so a crypto pair quoted in dollars answers False on its base
    leg and a bare equity code answers False outright.
    """
    held = str(symbol or "")
    if held.startswith(FUTURES_SYMBOL_PREFIX) or PAIR_SYMBOL_SEPARATOR not in held:
        return False
    base, _, quote = held.partition(PAIR_SYMBOL_SEPARATOR)
    return base.strip().upper() in CURRENCY_LEGS and (
        quote.strip().upper() in CURRENCY_LEGS
    )


def futures_sector(asset: Any) -> str:
    """The sector one dated contract belongs to.

    ``MARKET_SECTOR_SECTORS`` reads the record's own ``market-sector`` first,
    nested under ``future-product`` or written flat, then
    ``FUTURES_PRODUCT_SECTORS`` reads its ``product_code`` and a contract neither
    names falls to ``FUTURES_SECTOR``.
    """
    held = asset if isinstance(asset, dict) else {}
    nested = held.get("future-product")
    sources = (nested if isinstance(nested, dict) else {}, held)
    for source in sources:
        word = str(source.get("market-sector") or "").strip().lower()
        named = MARKET_SECTOR_SECTORS.get(word)
        if named:
            return named
    return FUTURES_PRODUCT_SECTORS.get(product_code(held), FUTURES_SECTOR)


def asset_sector(asset: Any) -> Optional[str]:
    """The sector one tastytrade record names, and None where its own fields
    name none.

    ``venue_market_sector`` is read first and ``venue_base_sector`` second, then
    ``futures_sector`` for a dated contract, then ``INSTRUMENT_TYPE_SECTORS``,
    then ``currency_pair_symbol``.
    """
    from ..trading.scrumming.sizing import venue_base_sector, venue_market_sector

    if not isinstance(asset, dict):
        return None
    symbol = str(asset.get("symbol") or "")
    named = venue_market_sector(VENUE_ID, symbol)
    if named:
        return str(named)
    base = symbol.lstrip(FUTURES_SYMBOL_PREFIX).partition(PAIR_SYMBOL_SEPARATOR)[0]
    cited = venue_base_sector(VENUE_ID, base)
    if cited:
        return str(cited)
    word = instrument_word(asset)
    if word == FUTURE_INSTRUMENT_TYPE:
        return futures_sector(asset)
    held = INSTRUMENT_TYPE_SECTORS.get(word)
    if held:
        return held
    if word:
        return None
    if symbol.startswith(FUTURE_OPTION_SYMBOL_PREFIX):
        return None
    if symbol.startswith(FUTURES_SYMBOL_PREFIX):
        return futures_sector(asset)
    if currency_pair_symbol(symbol):
        return "forex"
    return None


def asset_expiry_ms(asset: Any) -> Optional[float]:
    """The epoch milliseconds one contract record expires on, off its own
    ``expires-at``, ``expiration-date`` or ``last-trade-date``.

    Each is ISO 8601 -- a full moment on the first and a calendar date on the
    other two -- and None answers a record whose fields name no date.
    """
    if not isinstance(asset, dict):
        return None
    for field in ("expires-at", "expiration-date", "last-trade-date"):
        held = asset.get(field)
        if not isinstance(held, str) or not held.strip():
            continue
        try:
            read = datetime.fromisoformat(held.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        if read.tzinfo is None:
            read = read.replace(tzinfo=timezone.utc)
        return read.timestamp() * 1000.0
    return None


def increment_rule(asset: Any) -> Optional[float]:
    """The price step one record publishes, off its own ``tick-size``, the
    smallest value of its own ``tick-sizes`` array, or its own
    ``price-increments``.

    ``price-increments`` is the search route's own form, written "0.0001 1;
    0.01", whose last field is the step above every ``threshold``.
    """
    if not isinstance(asset, dict):
        return None
    named = rule_number(asset.get("tick-size"))
    if named is not None:
        return named
    rows = asset.get("tick-sizes")
    if isinstance(rows, list):
        found = [
            held
            for held in (
                rule_number(row.get("value")) for row in rows if isinstance(row, dict)
            )
            if held is not None
        ]
        if found:
            return min(found)
    written = asset.get("price-increments")
    if isinstance(written, str) and written.strip():
        tail = written.split(";")[-1].strip().split()
        if tail:
            return rule_number(tail[0])
    return None


def size_increment(asset: Any) -> Optional[float]:
    """The size step one record publishes.

    ``CRYPTO_MIN_ORDER_SIZE`` on a ``CRYPTO_INSTRUMENT_TYPE`` record,
    ``EQUITY_FRACTION_INCREMENT`` on an equity whose own
    ``EQUITY_FRACTION_FIELD`` is True, ``WHOLE_UNIT_INCREMENT`` on every other
    record naming a sector, and None where ``asset_sector`` names none.
    """
    word = instrument_word(asset)
    if word == CRYPTO_INSTRUMENT_TYPE:
        return CRYPTO_MIN_ORDER_SIZE
    if asset_sector(asset) is None:
        return None
    held = asset if isinstance(asset, dict) else {}
    if word == EQUITY_INSTRUMENT_TYPE and held.get(EQUITY_FRACTION_FIELD) is True:
        return EQUITY_FRACTION_INCREMENT
    return WHOLE_UNIT_INCREMENT


def asset_order_types(asset: Any) -> Optional[str]:
    """The order types one record's own instrument type declares.

    ``ORDER_TYPES_WITH_MARKET`` for a record whose type
    ``ORDER_LEG_INSTRUMENT_TYPES`` holds, and None for every other record: the
    venue's own ``order-type`` enum carries ``Market`` and its pages name no
    per-type restriction, and a type outside that set takes no order at all.
    """
    if asset_sector(asset) is None:
        return None
    if instrument_word(asset) not in ORDER_LEG_INSTRUMENT_TYPES:
        return None
    return ORDER_TYPES_WITH_MARKET


def tradable_market(asset: Any) -> bool:
    """Whether one record names a market this platform can both size and order.

    ``asset_sector`` must name a sector and ``ORDER_LEG_INSTRUMENT_TYPES`` must
    hold the record's own instrument type, so an ``Index``, a ``Currency Pair``,
    an option and a bond each answer False.
    """
    if asset_sector(asset) is None:
        return False
    return instrument_word(asset) in ORDER_LEG_INSTRUMENT_TYPES


def asset_session(asset: Any) -> Optional[str]:
    """``SESSION_US_EQUITY`` for an equity whose own
    ``EQUITY_SESSION_COLLECTION`` it names, ``SESSION_CONTINUOUS`` for a crypto
    market, and None for every other market.

    A dated contract names neither: its own session opens at 22:00 UTC and
    closes at 21:00 UTC, which is neither word, and citing either would claim
    hours the venue does not publish.
    """
    if not isinstance(asset, dict):
        return None
    word = instrument_word(asset)
    if word == CRYPTO_INSTRUMENT_TYPE:
        return SESSION_CONTINUOUS
    if word != EQUITY_INSTRUMENT_TYPE:
        return None
    collection = str(asset.get("market-time-instrument-collection") or "").strip()
    if collection.lower() != EQUITY_SESSION_COLLECTION:
        return None
    return SESSION_US_EQUITY


def asset_rules(asset: Any) -> MarketRules:
    """The ``MarketRules`` one tastytrade record publishes.

    ``read`` is False for anything that is not a record, an unnamed rule is
    None, ``contract_size`` carries the record's own ``contract-size`` or its
    ``notional-multiplier``, and ``expiry_ms`` the date ``asset_expiry_ms``
    reads.
    """
    if not isinstance(asset, dict):
        return MarketRules(read=False)
    nested = asset.get("future-product")
    product = nested if isinstance(nested, dict) else {}
    return MarketRules(
        min_amount=size_increment(asset),
        amount_increment=size_increment(asset),
        price_increment=increment_rule(asset) or increment_rule(product),
        contract_size=(
            rule_number(asset.get("contract-size"))
            or rule_number(asset.get("notional-multiplier"))
            or rule_number(product.get("notional-multiplier"))
        ),
        session=asset_session(asset),
        order_types=asset_order_types(asset),
        expiry_ms=asset_expiry_ms(asset),
    )


def published_time_in_force(time_in_force: Any) -> Any:
    """The time in force tastytrade publishes for one order.

    ``VENUE_TIMES_IN_FORCE`` holds the three words this platform composes, and a
    value outside it falls to ``DEFAULT_TIME_IN_FORCE``.
    """
    if time_in_force in VENUE_TIMES_IN_FORCE:
        return time_in_force
    return DEFAULT_TIME_IN_FORCE


def fee_total(transaction: Any) -> float:
    """The fee one transaction record carries, summed over ``FEE_FIELDS`` with
    each component's own ``-effect`` applied.

    An ``EFFECT_DEBIT`` component is a charge and adds, an ``EFFECT_CREDIT``
    component returns money and subtracts, and a component whose effect reads
    neither contributes nothing.
    """
    held = transaction if isinstance(transaction, dict) else {}
    total = 0.0
    for field in FEE_FIELDS:
        amount = rule_number(held.get(field))
        if amount is None:
            continue
        effect = str(held.get(f"{field}-effect") or "").strip().lower()
        if effect == EFFECT_DEBIT:
            total += amount
        elif effect == EFFECT_CREDIT:
            total -= amount
    return total


def fill_record(transaction: Any) -> dict:
    """One tastytrade transaction as the record ``broker_trade`` reads.

    ``fee`` carries ``fee_total`` of the record's own six fee components and
    ``transaction_time`` its own ``executed-at``, which is ISO 8601 and the form
    ``bar_epoch_ms`` reads.
    """
    held = transaction if isinstance(transaction, dict) else {}
    action = str(held.get("action") or "").strip().lower()
    return {
        "id": str(held.get("id") or ""),
        "symbol": str(held.get("symbol") or ""),
        "side": FILL_SIDES.get(action, ""),
        "qty": held.get("quantity"),
        "price": held.get("price"),
        "fee": fee_total(held),
        "fee_currency": str(held.get("currency") or FEE_CURRENCY),
        "transaction_time": str(held.get("executed-at") or ""),
        "instrument_type": held.get("instrument-type"),
        "transaction_type": held.get("transaction-type"),
        "order_id": held.get("order-id"),
    }


def is_fill(transaction: Any) -> bool:
    """Whether one transaction record is a trade fill.

    ``transaction-type`` holds four words and only ``FILL_TRANSACTION_TYPE`` is
    a fill, and a record whose ``action`` ``FILL_SIDES`` does not name is not one
    either.
    """
    held = transaction if isinstance(transaction, dict) else {}
    word = str(held.get("transaction-type") or "").strip().lower()
    if word != FILL_TRANSACTION_TYPE:
        return False
    return str(held.get("action") or "").strip().lower() in FILL_SIDES


def total_pages(answered: Any) -> int:
    """The page count one paginated reply publishes, and 0 where it carries no
    ``PAGINATION_FIELD`` block.

    The venue's own pagination guide states the condition this serves: "you are
    on the last page when ``page-offset + 1 >= pagination.total-pages``".
    """
    held = answered if isinstance(answered, dict) else {}
    block = held.get(PAGINATION_FIELD)
    if not isinstance(block, dict):
        return 0
    named = block.get(TOTAL_PAGES_FIELD)
    return int(named) if type(named) is int and named > 0 else 0


def walked_pages(page: int, rows: int) -> int:
    """The page count ``list_fills`` walks to where the reply published no
    ``PAGINATION_FIELD`` block.

    The venue's own pagination guide gives the fallback: "if a response has no
    pagination block, stop when `items` comes back with fewer than `per-page`
    entries (or empty)", so a full page asks for one more and a short page ends
    the walk.
    """
    if rows >= TRANSACTION_PAGE_SIZE:
        return page + 2
    return page + 1 if rows else page


def reply_items(answered: Any) -> list:
    """Every row one reply carries under its own ``data.items``, and [] where it
    carries none.

    Every list route on this venue wraps its rows that way, and a single-record
    route answers ``data`` alone.
    """
    held = answered if isinstance(answered, dict) else {}
    data = held.get("data")
    if not isinstance(data, dict):
        return []
    rows = data.get("items")
    return [row for row in rows or [] if isinstance(row, dict)]


def order_body(
    asset: Any,
    symbol: str,
    side: Any,
    quantity: float,
    order_type: Any = OrderType.MARKET,
    limit_price: float = 0.0,
    stop_price: float = 0.0,
    time_in_force: Any = TimeInForce.DAY,
    client_order_id: str = "",
) -> dict:
    """One order ticket for ``ORDER_ROUTE``, composed from the fields its own
    schema names.

    The six its schema marks required are always written -- ``order-type``,
    ``time-in-force``, ``legs``, and each leg's ``action``, ``instrument-type``
    and ``symbol`` -- ``price`` rides with ``price-effect``, ``stop-trigger``
    follows a stop, ``automated-source`` reads ``AUTOMATED_SOURCE``, and
    ``ValueError`` names a ``side``, an ``order_type`` or an instrument type this
    venue does not publish.
    """
    held = asset if isinstance(asset, dict) else {}
    word = instrument_word(held)
    if not word:
        raise ValueError(NO_INSTRUMENT_TYPE.format(symbol=symbol))
    if word not in ORDER_LEG_INSTRUMENT_TYPES:
        raise ValueError(
            NO_ORDER_LEG_TYPE.format(
                word=word, published=tuple(sorted(ORDER_LEG_INSTRUMENT_TYPES))
            )
        )
    actions = FUTURES_LEG_ACTIONS if word == FUTURE_INSTRUMENT_TYPE else LEG_ACTIONS
    action = actions.get(side)
    if action is None:
        raise ValueError(f"order side {side!r} is not one of {tuple(actions)}")
    venue_type = VENUE_ORDER_TYPES.get(order_type)
    if venue_type is None:
        raise ValueError(
            f"order type {order_type!r} is not one of {tuple(VENUE_ORDER_TYPES)}"
        )
    leg: dict[str, Any] = {
        "action": action,
        "instrument-type": str(held.get("instrument-type") or "").strip()
        or EQUITY_INSTRUMENT_TYPE.title(),
        "symbol": str(held.get("symbol") or symbol),
        "quantity": decimal_text(quantity),
    }
    body: dict[str, Any] = {
        "order-type": venue_type,
        "time-in-force": VENUE_TIMES_IN_FORCE[published_time_in_force(time_in_force)],
        "legs": [leg],
        "automated-source": AUTOMATED_SOURCE,
    }
    if order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and limit_price > 0:
        body["price"] = decimal_text(limit_price)
        body["price-effect"] = PRICE_EFFECTS[side]
    if order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and stop_price > 0:
        body["stop-trigger"] = decimal_text(stop_price)
    if client_order_id:
        body["external-identifier"] = str(client_order_id)
    return body


class TastytradeConnector(BrokerBase):
    """tastytrade broker connector.

    ``SECTORS_SERVED`` names the six sectors its own product pages list a market
    in, and ``place_order`` composes the body ``order_body`` builds for
    ``ORDER_ROUTE``.
    """

    #: The six sectors the venue's own pages list a market in: stocks from "full
    #: or fractional shares, it's your choice" on its own stocks page, crypto
    #: from the 26 coins its own Available Cryptocurrencies page names,
    #: commodities from 27 contracts over its Energy, Metals, Agriculture and
    #: Livestock families, forex from its 11 Foreign Currency contracts, indices
    #: from its 12 Equity Index and 2 Volatility contracts, and futures_perps
    #: from all 68 contracts. No perpetual: the word names 0 of the 29 venue
    #: files read, where "futures" names 725, "currency" 327 and "crypto" 325,
    #: and an invented word names 0.
    SECTORS_SERVED: tuple = (
        "crypto",
        "stocks",
        "commodities",
        "forex",
        "indices",
        "futures_perps",
    )

    #: The venue publishes a sandbox and names what it is: "a full copy of the
    #: tastytrade API backed by simulated money", where "Orders placed in the
    #: sandbox never reach a real market". So ``broker_paper_route`` opens the
    #: paper session. Its own page states the cost: "Fill behaviour is derived
    #: from the order type and price, and nothing else", and "Market data is not
    #: served. /market-data and /market-metrics return HTTP 502 on every route".
    HAS_PAPER_ROUTE: bool = True

    #: The venue publishes its own fills on ``TRANSACTIONS_ROUTE``, which pages
    #: and carries its own ``total-pages``, so ``get_my_trades`` reads
    #: ``list_fills`` and never refuses.
    PUBLISHES_FILL_HISTORY: bool = True

    def __init__(self):
        super().__init__(VENUE_ID)
        self._base_url = API_BASE
        self._bearer = ""
        self._bearer_expires_at = 0.0
        self._grant = ""
        self._client_key = ""
        self._account = ""
        self._session = None

    @property
    def account(self) -> str:
        """The account number ``connect`` read off ``ACCOUNTS_ROUTE``, which
        ``ORDER_ROUTE`` clears an order to."""
        return self._account

    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Exchange ``api_key`` as the grant's refresh token and ``api_secret``
        as the application's client secret for an access token, read
        ``ACCOUNTS_ROUTE``, and answer whether it named an account.

        ``paper`` picks ``SANDBOX_BASE`` over ``API_BASE``; a client registered
        in one environment does not work in the other, which the venue states
        itself.
        """
        self._base_url = SANDBOX_BASE if paper else API_BASE
        self._grant = str(api_key or "")
        self._client_key = str(api_secret or "")
        if not self._grant or not self._client_key:
            self._session_refusal = "no refresh token and client secret are stored"
            return False
        try:
            await self._mint_bearer()
            answered = await self._request("GET", ACCOUNTS_ROUTE)
        except Exception as exc:
            logger.error("tastytrade connection failed: %s", exc)
            self._session_refusal = str(exc)
            return False
        named = []
        for row in reply_items(answered):
            account = row.get("account")
            number = str(
                (account if isinstance(account, dict) else {}).get("account-number")
                or ""
            )
            if number:
                named.append(number)
        if not named:
            self._session_refusal = "the venue named no account on this grant"
            return False
        self._account = named[0]
        self._connected = True
        logger.info(
            "Connected to tastytrade (%s): account=%s of %d",
            "sandbox" if paper else "LIVE",
            self._account,
            len(named),
        )
        return True

    async def disconnect(self):
        """Drop the held token, the held credentials and the held ``account``,
        and mark this broker disconnected."""
        self._bearer = ""
        self._bearer_expires_at = 0.0
        self._grant = ""
        self._client_key = ""
        self._account = ""
        self._connected = False
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as exc:
                logger.warning("tastytrade session already closed: %s", exc)
            self._session = None

    async def get_account(self) -> AccountInfo:
        """The account summary ``BALANCES_ROUTE`` publishes for the held
        ``account``.

        ``cash`` carries the venue's own ``cash-balance``, which its schema names
        "Settled cash in the account", and ``buying_power`` its own
        ``equity-buying-power``.
        """
        if not self._account:
            return AccountInfo()
        answered = await self._request(
            "GET", BALANCES_ROUTE.format(account=self._account)
        )
        held = answered.get("data") if isinstance(answered, dict) else None
        row = held if isinstance(held, dict) else {}
        equity = rule_number(row.get("net-liquidating-value")) or 0.0
        return AccountInfo(
            account_id=self._account,
            equity=equity,
            cash=rule_number(row.get("cash-balance")) or 0.0,
            buying_power=rule_number(row.get("equity-buying-power")) or 0.0,
            portfolio_value=equity,
        )

    async def get_positions(self) -> list[StockPosition]:
        """Every open position the held ``account`` carries, read off
        ``POSITIONS_ROUTE``.

        That route declares no page parameter, so one call answers the whole
        list, and ``include-marks`` asks for the mark the venue leaves out by
        default.
        """
        if not self._account:
            return []
        answered = await self._request(
            "GET",
            f"{POSITIONS_ROUTE.format(account=self._account)}?include-marks=true",
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
        count its own leg schema names.

        ``order_body`` composes the ticket and raises on an instrument type
        ``ORDER_LEG_INSTRUMENT_TYPES`` does not hold, so an index or a currency
        pair is refused here and reaches no venue.
        """
        asset = self._asset(symbol)
        ticket = order_body(
            asset,
            str(symbol),
            side,
            quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
        )
        held_tif = published_time_in_force(time_in_force)
        if held_tif is not time_in_force:
            logger.info(
                "tastytrade publishes no %s time in force; sending %s for %s",
                getattr(time_in_force, "value", time_in_force),
                held_tif.value,
                symbol,
            )
        answered = await self._request(
            "POST", ORDER_ROUTE.format(account=self._account), ticket
        )
        return self._parse_order(answered, symbol=str(symbol), ticket=ticket)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel one working order on ``ORDER_ITEM_ROUTE``, and answer False
        where the venue refused it or no ``account`` is held."""
        if not self._account or not order_id:
            return False
        try:
            await self._request(
                "DELETE",
                ORDER_ITEM_ROUTE.format(account=self._account, order_id=str(order_id)),
            )
        except Exception as exc:
            logger.warning("tastytrade cancel refused: %s", exc)
            return False
        return True

    async def get_order(self, order_id: str) -> StockOrder:
        """The status of one order, read off ``ORDER_ITEM_ROUTE`` through
        ``_status_order``."""
        if not self._account or not order_id:
            return StockOrder()
        answered = await self._request(
            "GET",
            ORDER_ITEM_ROUTE.format(account=self._account, order_id=str(order_id)),
        )
        held = answered.get("data") if isinstance(answered, dict) else None
        return self._status_order(held, order_id=str(order_id))

    async def get_open_orders(self) -> list[StockOrder]:
        """Every order ``ORDERS_LIVE_ROUTE`` publishes for today.

        That route's own schema defaults ``per-page`` to 100 and caps it at 200,
        and the searchable orders route defaults to 10, so ``ORDER_PAGE_SIZE``
        asks the published maximum and no default reads a fleet's book as ten
        rows.
        """
        if not self._account:
            return []
        answered = await self._request(
            "GET",
            f"{ORDERS_LIVE_ROUTE.format(account=self._account)}"
            f"?per-page={ORDER_PAGE_SIZE}",
        )
        return [self._status_order(row) for row in reply_items(answered)]

    async def get_quote(self, symbol: str) -> StockQuote:
        """The top of book ``MARKET_DATA_ROUTE`` publishes for ``symbol``.

        That route takes one query parameter per instrument type, so the held
        record's own type names the parameter through ``QUOTE_TYPE_PARAMETERS``.
        """
        asset = self._asset(symbol)
        word = instrument_word(asset)
        parameter = QUOTE_TYPE_PARAMETERS.get(word, DEFAULT_QUOTE_TYPE_PARAMETER)
        answered = await self._request(
            "GET", f"{MARKET_DATA_ROUTE}?{parameter}={self._quoted(str(symbol))}"
        )
        rows = reply_items(answered)
        row = rows[0] if rows else {}
        return StockQuote(
            symbol=str(symbol),
            bid=rule_number(row.get("bid")) or 0.0,
            ask=rule_number(row.get("ask")) or 0.0,
            last=rule_number(row.get("last")) or rule_number(row.get("mark")) or 0.0,
            timestamp=time.time(),
        )

    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int = 100
    ) -> list[dict]:
        """No bar for ``symbol``, and ``NO_BAR_ROUTE`` naming the route this
        connector does not open.

        Over all 84 paths the venue's own 16 OpenAPI documents publish, the names
        holding ``candle``, ``bar`` and ``ohlc`` number 0 each, and its candles
        are Candle events on its DXLink streamer.
        """
        del timeframe, limit
        logger.info(NO_BAR_ROUTE, str(symbol), "/api-quote-tokens")
        return []

    async def get_market_status(self) -> dict:
        """The equity session state ``EQUITY_SESSION_ROUTE`` publishes.

        That route answers without a credential and carries a ``state`` word
        beside the next session's ``open-at`` and ``close-at``, so the reading is
        the venue's own and not this machine's clock.
        """
        try:
            answered = await self._request("GET", EQUITY_SESSION_ROUTE)
        except Exception as exc:
            logger.warning("tastytrade session state unread: %s", exc)
            return {"is_open": False, "next_open": "", "next_close": ""}
        held = answered.get("data") if isinstance(answered, dict) else None
        row = held if isinstance(held, dict) else {}
        upcoming = row.get("next-session")
        session = upcoming if isinstance(upcoming, dict) else {}
        return {
            "is_open": str(row.get("state") or "").strip().lower() == "open",
            "next_open": str(session.get("open-at") or ""),
            "next_close": str(session.get("close-at") or ""),
        }

    async def list_assets(self, status: str = "active") -> list[dict]:
        """Every instrument record the venue publishes for the held
        ``scan_symbols``, kept for ``held_assets`` and ``record_markets``.

        ``_search`` is read per held symbol and ``tradable_market`` keeps the
        exact match, so a record this platform cannot both size and order never
        becomes a recorded market.
        """
        del status
        found: list[dict] = []
        refused: list[str] = []
        for name in sorted(self._scan_symbols):
            record = await self._search(name)
            if record is None:
                continue
            if tradable_market(record):
                found.append(record)
                continue
            refused.append(f"{name} ({instrument_word(record) or 'no type'})")
        self._assets = found
        if refused:
            logger.info(NO_TRADABLE_MARKET, len(refused), ", ".join(refused))
        return list(self._assets)

    async def list_fills(
        self,
        symbol: str = "",
        since_ms: Optional[float] = None,
        until_ms: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Every fill ``TRANSACTIONS_ROUTE`` publishes for ``symbol``, walked
        page by page on the venue's own ``total-pages``.

        A short page is not the end here: the reply publishes its own page count,
        the walk stops on that count and at ``TRANSACTION_PAGES_MAX``, and
        ``is_fill`` keeps the trade rows alone.
        """
        if not self._account:
            return []
        found: list[dict] = []
        page = 0
        pages = 1
        while page < min(pages, TRANSACTION_PAGES_MAX):
            query = (
                f"?per-page={TRANSACTION_PAGE_SIZE}&page-offset={page}"
                f"&sort=Asc&types[]=Trade"
            )
            if symbol:
                query += f"&symbol={self._quoted(str(symbol))}"
            answered = await self._request(
                "GET", f"{TRANSACTIONS_ROUTE.format(account=self._account)}{query}"
            )
            rows = reply_items(answered)
            pages = total_pages(answered) or walked_pages(page, len(rows))
            for row in rows:
                if not is_fill(row):
                    continue
                built = fill_record(row)
                moment = self._fill_moment_ms(built)
                if (
                    moment is not None
                    and until_ms is not None
                    and (moment > float(until_ms))
                ):
                    continue
                if (
                    moment is not None
                    and since_ms is not None
                    and (moment < float(since_ms))
                ):
                    continue
                found.append(built)
            if not rows:
                break
            page += 1
        logger.info(
            "tastytrade answered %d fill(s) over %d page(s) of %d",
            len(found),
            page,
            pages,
        )
        if limit is None:
            return found
        return found[: max(int(limit), 1)]

    def market_rules(self, asset: Any) -> MarketRules:
        """The ``MarketRules`` one of this broker's own instrument records
        publishes, read through ``asset_rules`` with no broker contacted."""
        return asset_rules(asset)

    def asset_sector(self, asset: Any) -> Optional[str]:
        """The sector one of this broker's own instrument records names, read
        through ``asset_sector`` with no broker contacted."""
        return asset_sector(asset)

    @staticmethod
    def _fill_moment_ms(built: Any) -> Optional[float]:
        """The epoch milliseconds one built fill record executed at, and None
        where its moment cannot be read.

        ``transaction_time`` is ISO 8601 and a moment carrying no offset is read
        as UTC, which keeps the reading off this machine's own zone.
        """
        held = built if isinstance(built, dict) else {}
        stamp = str(held.get("transaction_time") or "")
        if not stamp:
            return None
        try:
            read = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            return None
        if read.tzinfo is None:
            read = read.replace(tzinfo=timezone.utc)
        return read.timestamp() * 1000.0

    def _asset(self, symbol: Any) -> dict:
        """The held instrument record naming ``symbol``, and {} where no record
        does."""
        name = str(symbol or "")
        for held in self._assets:
            if isinstance(held, dict) and str(held.get("symbol") or "") == name:
                return held
        return {}

    async def _search(self, symbol: str) -> Optional[dict]:
        """The instrument record ``SYMBOL_SEARCH_ROUTE`` publishes for the exact
        ``symbol``, and None where it names no record for it.

        That route answers every instrument kind in one call and carries
        ``instrument-type``, ``price-increments`` and the dated
        ``contract-codes`` of a futures product.
        """
        name = str(symbol or "")
        if not name:
            return None
        try:
            answered = await self._request(
                "GET", SYMBOL_SEARCH_ROUTE.format(symbol=self._quoted(name))
            )
        except Exception as exc:
            logger.warning("tastytrade search refused for %s: %s", name, exc)
            return None
        for row in reply_items(answered):
            if str(row.get("symbol") or "") == name:
                return row
        return None

    @staticmethod
    def _quoted(symbol: str) -> str:
        """``symbol`` with the characters the venue requires encoded in a path.

        Its own symbology page: "Symbols that contain a ``/`` (futures, future
        options, crypto) or whitespace (OCC options) must be URL-encoded when
        placed in a path or query string."
        """
        from urllib.parse import quote

        return quote(str(symbol), safe="")

    @staticmethod
    def _position(row: Any) -> Optional[StockPosition]:
        """One position record as a ``StockPosition``, and None for a row naming
        no symbol.

        The venue publishes no unrealised figure -- its own page states "The API
        does not return a live profit/loss figure" -- so ``unrealized_pnl`` is
        computed from its own ``mark`` against its own ``average-open-price``,
        the arithmetic that page gives.
        """
        if not isinstance(row, dict):
            return None
        symbol = str(row.get("symbol") or "")
        if not symbol:
            return None
        units = rule_number(row.get("quantity")) or 0.0
        if str(row.get("quantity-direction") or "").strip().lower() == "short":
            units = -units
        basis = rule_number(row.get("average-open-price")) or 0.0
        mark = (
            rule_number(row.get("mark-price"))
            or rule_number(row.get("mark"))
            or rule_number(row.get("close-price"))
            or 0.0
        )
        multiplier = rule_number(row.get("multiplier")) or 1.0
        value = mark * units * multiplier
        unrealised = (mark - basis) * units * multiplier
        cost = abs(basis * units * multiplier)
        return StockPosition(
            symbol=symbol,
            quantity=units,
            avg_entry_price=basis,
            current_price=mark,
            market_value=value,
            unrealized_pnl=unrealised,
            unrealized_pnl_pct=0.0 if cost <= 0.0 else unrealised / cost * 100.0,
            side=PositionSide.LONG if units >= 0 else PositionSide.SHORT,
        )

    @staticmethod
    def _parse_order(answered: Any, symbol: str, ticket: dict) -> StockOrder:
        """The ``StockOrder`` one ``ORDER_ROUTE`` submission answers.

        That route answers 201 with its own ``PlacedOrderResponse`` under
        ``data``, carrying ``order``, ``errors`` and ``warnings``, and
        ``ValueError`` names a reply whose order carries no id.
        """
        held = answered.get("data") if isinstance(answered, dict) else None
        data = held if isinstance(held, dict) else {}
        placed = data.get("order")
        row = placed if isinstance(placed, dict) else {}
        order_id = str(row.get("id") or "")
        if not order_id:
            raise ValueError(
                f"tastytrade answered no order id for {symbol}: "
                f"{data.get('errors') or data}"
            )
        leg = (ticket.get("legs") or [{}])[0]
        return StockOrder(
            order_id=order_id,
            symbol=symbol,
            side=(
                OrderSide.SELL
                if str(leg.get("action") or "").lower().startswith("sell")
                else OrderSide.BUY
            ),
            order_type=(
                OrderType.LIMIT
                if str(ticket.get("order-type")) == ORDER_TYPE_LIMIT
                else OrderType.MARKET
            ),
            quantity=rule_number(leg.get("quantity")) or 0.0,
            limit_price=rule_number(ticket.get("price")) or 0.0,
            stop_price=rule_number(ticket.get("stop-trigger")) or 0.0,
            status=str(row.get("status") or "new"),
            submitted_at=time.time(),
        )

    @staticmethod
    def _status_order(answered: Any, order_id: str = "") -> StockOrder:
        """One order record as a ``StockOrder``, with ``order_id`` standing in
        where the record names none.

        A leg's own ``fills`` carry the filled size and the fill price, and the
        venue's own status words are the words
        ``BrokerExchange.exchange_order_status`` reads.
        """
        held = answered if isinstance(answered, dict) else {}
        legs = held.get("legs")
        leg = next((one for one in legs or [] if isinstance(one, dict)), {})
        fills = [one for one in leg.get("fills") or [] if isinstance(one, dict)]
        filled = sum(rule_number(one.get("quantity")) or 0.0 for one in fills)
        paid = sum(
            (rule_number(one.get("quantity")) or 0.0)
            * (rule_number(one.get("fill-price")) or 0.0)
            for one in fills
        )
        return StockOrder(
            order_id=str(held.get("id") or order_id),
            symbol=str(leg.get("symbol") or held.get("underlying-symbol") or ""),
            side=(
                OrderSide.SELL
                if str(leg.get("action") or "").lower().startswith("sell")
                else OrderSide.BUY
            ),
            order_type=(
                OrderType.LIMIT
                if str(held.get("order-type") or "") == ORDER_TYPE_LIMIT
                else OrderType.MARKET
            ),
            quantity=rule_number(held.get("size"))
            or rule_number(leg.get("quantity"))
            or 0.0,
            limit_price=rule_number(held.get("price")) or 0.0,
            stop_price=rule_number(held.get("stop-trigger")) or 0.0,
            status=str(held.get("status") or "new"),
            filled_qty=filled,
            avg_fill_price=0.0 if filled <= 0.0 else paid / filled,
        )

    async def _mint_bearer(self) -> None:
        """Exchange the held refresh token and client secret for an access token
        on ``GRANT_ROUTE``.

        The token is valid for ``BEARER_SECONDS`` and refreshing does not rotate
        the refresh token, which the venue states itself, so the held one stays.
        """
        answered = await self._post_json(
            GRANT_ROUTE,
            {
                "grant_type": GRANT_TYPE_WORD,
                "refresh_token": self._grant,
                "client_secret": self._client_key,
            },
        )
        held = answered if isinstance(answered, dict) else {}
        token = str(held.get("access_token") or "")
        if not token:
            raise ValueError("tastytrade answered no access token on the grant")
        self._bearer = token
        self._bearer_expires_at = time.time() + (
            rule_number(held.get("expires_in")) or BEARER_SECONDS
        )

    async def _held_bearer(self) -> str:
        """The held access token, minted again where it is absent or inside
        ``BEARER_MARGIN_SECONDS`` of expiry."""
        if (
            not self._bearer
            or time.time() >= self._bearer_expires_at - BEARER_MARGIN_SECONDS
        ):
            await self._mint_bearer()
        return self._bearer

    async def _post_json(self, path: str, body: dict) -> Any:
        """One POST to ``_base_url`` carrying ``USER_AGENT`` and no bearer token,
        which is the shape ``GRANT_ROUTE`` takes."""
        return await self._send("POST", path, body, authorise=False)

    async def _request(
        self, method: str, path: str, body: Optional[dict] = None
    ) -> Any:
        """One request to ``_base_url`` carrying the held bearer token and
        ``USER_AGENT``.

        A status of 204 answers {}, a status outside 200 and 201 raises with the
        body the venue answered, and a body that is no JSON raises as well.
        """
        return await self._send(method, path, body, authorise=True)

    async def _send(
        self, method: str, path: str, body: Optional[dict], authorise: bool
    ) -> Any:
        """One request to ``_base_url``, with the bearer token where
        ``authorise`` asks for it.

        ``USER_AGENT`` rides on every request: the venue answers 401 with an HTML
        body and no error code when the header is missing or malformed, even on a
        valid token.
        """
        import aiohttp

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if authorise:
            headers["Authorization"] = f"Bearer {await self._held_bearer()}"
        if self._session is None:
            self._session = aiohttp.ClientSession()
        async with self._session.request(
            method, self._base_url + path, headers=headers, json=body
        ) as resp:
            if resp.status == 204:
                return {}
            text = await resp.text()
            if resp.status not in (200, 201):
                raise ValueError(f"tastytrade API {resp.status}: {text}")
            try:
                return json.loads(text) if text else {}
            except ValueError as exc:
                raise ValueError(
                    f"tastytrade answered no JSON on {path}: {exc}"
                ) from exc


__all__ = [
    "ACCOUNTS_ROUTE",
    "API_BASE",
    "AUTOMATED_SOURCE",
    "BALANCES_ROUTE",
    "BEARER_MARGIN_SECONDS",
    "BEARER_SECONDS",
    "CRYPTO_INSTRUMENT_TYPE",
    "CRYPTO_LIST_ROUTE",
    "CRYPTO_MIN_ORDER_SIZE",
    "CRYPTO_QUANTITY_PRECISION",
    "CURRENCY_LEGS",
    "DECIMAL_PLACES",
    "DEFAULT_QUOTE_TYPE_PARAMETER",
    "DEFAULT_TIME_IN_FORCE",
    "EFFECT_CREDIT",
    "EFFECT_DEBIT",
    "EQUITY_FRACTION_FIELD",
    "EQUITY_FRACTION_INCREMENT",
    "EQUITY_INSTRUMENT_TYPE",
    "EQUITY_LIST_ROUTE",
    "EQUITY_SESSION_COLLECTION",
    "EQUITY_SESSION_ROUTE",
    "FEE_CURRENCY",
    "FEE_FIELDS",
    "FILL_SIDES",
    "FILL_TRANSACTION_TYPE",
    "FUTURES_LEG_ACTIONS",
    "FUTURES_LIST_ROUTE",
    "FUTURES_PRODUCT_SECTORS",
    "FUTURES_SECTOR",
    "FUTURES_SYMBOL_PREFIX",
    "FUTURE_INSTRUMENT_TYPE",
    "FUTURE_OPTION_SYMBOL_PREFIX",
    "GRANT_ROUTE",
    "GRANT_TYPE_WORD",
    "INSTRUMENT_TYPE_SECTORS",
    "LEG_ACTIONS",
    "MARKET_DATA_ROUTE",
    "MARKET_SECTOR_SECTORS",
    "NO_BAR_ROUTE",
    "NO_INSTRUMENT_TYPE",
    "NO_ORDER_LEG_TYPE",
    "NO_TRADABLE_MARKET",
    "ORDERS_LIVE_ROUTE",
    "ORDER_ITEM_ROUTE",
    "ORDER_LEG_INSTRUMENT_TYPES",
    "ORDER_PAGE_SIZE",
    "ORDER_ROUTE",
    "ORDER_TYPE_LIMIT",
    "ORDER_TYPE_MARKET",
    "PAGINATION_FIELD",
    "PAIR_SYMBOL_SEPARATOR",
    "POSITIONS_ROUTE",
    "PRECISION_ROUTE",
    "PRICE_EFFECTS",
    "QUOTE_TYPE_PARAMETERS",
    "SANDBOX_BASE",
    "SYMBOL_SEARCH_ROUTE",
    "TOTAL_FEES_ROUTE",
    "TOTAL_PAGES_FIELD",
    "TRANSACTIONS_ROUTE",
    "TRANSACTION_PAGES_MAX",
    "TRANSACTION_PAGE_SIZE",
    "USER_AGENT",
    "VENUE_ID",
    "VENUE_ORDER_TYPES",
    "VENUE_TIMES_IN_FORCE",
    "WHOLE_UNIT_INCREMENT",
    "TastytradeConnector",
    "asset_expiry_ms",
    "asset_order_types",
    "asset_rules",
    "asset_sector",
    "asset_session",
    "currency_pair_symbol",
    "decimal_text",
    "fee_total",
    "fill_record",
    "futures_sector",
    "increment_rule",
    "instrument_word",
    "is_fill",
    "order_body",
    "product_code",
    "published_time_in_force",
    "reply_items",
    "rule_number",
    "size_increment",
    "total_pages",
    "walked_pages",
    "tradable_market",
]
