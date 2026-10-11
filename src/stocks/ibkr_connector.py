"""
ibkr_connector.py — Interactive Brokers broker connector.

``IbkrConnector`` answers ``BrokerBase`` for ``VENUE_ID``, so
``MainWindow._connect_broker_for_bot`` builds it and ``BotContainer`` reaches it
through ``BrokerExchange``. ``ASSET_CLASS_SECTORS``, ``FUTURES_FAMILY_SECTORS``,
``CURRENCY_LEGS`` and ``asset_sector`` carry the product vocabulary Interactive
Brokers' own OpenAPI document and contract pages publish. ``ORDER_ROUTE`` names
the one order route its own API host serves for every sector, and ``order_body``
composes the ticket that route's own schema declares.
"""

from __future__ import annotations

import json
import logging
import math
import time
from typing import Any, Optional

from ..exchange.base import MarketRules
from ..trading.scrumming.sizing import (
    ORDER_TYPES_LIMIT_ONLY,
    ORDER_TYPES_WITH_MARKET,
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

logger = logging.getLogger("acervator.stocks.ibkr")

#: The venue id this broker registers under, which ``BROKER_CONNECTORS`` keys,
#: ``IbkrConnector.exchange_id`` answers and the sector tables in
#: ``trading.scrumming.sizing`` are keyed by. ``www.ibkr.com`` redirects to
#: ``www.interactivebrokers.com`` and serves the same 240,678 bytes, so the two
#: venue ids ``EQUITY_VENUES`` holds name one firm. This is the id the rest of
#: the tree reads — six sectors against one — and the firm's own API host name.
VENUE_ID = "ibkr"

#: The host and the base path Interactive Brokers' own OpenAPI document names as
#: its production server, read 2026-10-11 from
#: ``api.ibkr.com/gw/api/v3/api-docs`` with no credential sent: openapi 3.0.0,
#: "IB REST API", version 2.41.0, 179 paths, 939,918 bytes.
API_BASE = "https://api.ibkr.com"
API_PREFIX = "/v1/api"

#: The one order route the venue serves, which every sector's order takes. Its
#: own ``operationId`` is ``submitNewOrder`` and its body is a JSON array of
#: order tickets under ``orders``.
ORDER_ROUTE = "/iserver/account/{account}/orders"

#: The route each read this connector makes takes, each one named in the same
#: document. ``TRADES_ROUTE`` is the only fill ledger the venue publishes.
ACCOUNTS_ROUTE = "/iserver/accounts"
LEDGER_ROUTE = "/portfolio/{account}/ledger"
POSITIONS_ROUTE = "/portfolio/{account}/positions/{page}"
POSITION_ROUTE = "/portfolio/{account}/position/{conid}"
ORDERS_ROUTE = "/iserver/account/orders"
ORDER_STATUS_ROUTE = "/iserver/account/order/status/{order_id}"
CANCEL_ROUTE = "/iserver/account/{account}/order/{order_id}"
TRADES_ROUTE = "/iserver/account/trades"
SNAPSHOT_ROUTE = "/iserver/marketdata/snapshot"
HISTORY_ROUTE = "/iserver/marketdata/history"
SECDEF_ROUTE = "/trsrv/secdef"
CONIDS_ROUTE = "/trsrv/all-conids"
CURRENCY_PAIRS_ROUTE = "/iserver/currency/pairs"

#: The rows one page of ``POSITIONS_ROUTE`` answers, which its own position
#: record carries as ``pageSize``. A shorter page is the end of the list.
POSITION_PAGE_SIZE = 100

#: The pages ``get_positions`` reads before it stops, bounding that walk at
#: 10,000 positions.
POSITION_PAGES_MAX = 100

#: The sector each security type Interactive Brokers names belongs to. The
#: order-status schema closes the vocabulary at nine words — ``STK``, ``OPT``,
#: ``FUT``, ``FOP``, ``CASH``, ``CRYPTO``, ``BOND``, ``WAR``, ``FUND`` — and its
#: own contract pages add ``CMDTY`` for spot metals and ``IND`` for an index.
#: Six are mapped here and five are not: ``OPT`` and ``FOP`` name options, which
#: is no sector this platform draws, ``BOND`` names a bond, ``WAR`` a warrant and
#: ``BAG`` a combo. ``IND`` maps to indices for the recording and takes no order
#: — it names no row on the venue's own market-order or limit-order product
#: lists, and the sector's order is the index future.
ASSET_CLASS_SECTORS: dict[str, str] = {
    "cash": "forex",
    "cmdty": "commodities",
    "crypto": "crypto",
    "fund": "stocks",
    "ind": "indices",
    "stk": "stocks",
}

#: The sector each futures family Interactive Brokers' own futures page names
#: belongs to, read off that page on 2026-10-11. It names eleven families
#: itself. Fixed Income and Interest Rates map to no sector this platform draws,
#: and "E-mini and Micro E-mini Futures" is a size family whose products each
#: repeat a product in another family, so no symbol takes its sector from it.
FUTURES_FAMILY_SECTORS: dict[str, str] = {
    "agriculture": "commodities",
    "cryptocurrency": "crypto",
    "currencies": "forex",
    "energy": "commodities",
    "equity indices": "indices",
    "metals": "commodities",
    "softs": "commodities",
    "volatility indices": "indices",
}

#: The sector a ``FUT`` record naming no family falls to: the contract form,
#: which is the sector this platform draws for a dated contract.
FUTURES_SECTOR = "futures_perps"

#: The security types naming a dated contract, whose sector is its family.
CONTRACT_ASSET_CLASSES = ("fut", "fop")

#: The separator Interactive Brokers' own currency list puts between a pair's
#: two legs, as in ``USD.SGD``. Its own
#: ``GET /iserver/currency/pairs?currency=USD`` answers ``USD.SGD``,
#: ``USD.RON`` and ``USD.CZK``, and no equity symbol carries it.
CURRENCY_SYMBOL_SEPARATOR = "."

#: Every currency leg Interactive Brokers' own Spot Currencies page names under
#: its headline "IBKR Offers 100+ Currency Pairs On 28 Currencies", read
#: 2026-10-11. A pair with a leg of this set on both sides holds two
#: currencies, which places it in the forex sector. ``NOK`` is here and is also
#: Nokia's listed equity, and ``SGD`` is here and bases no equity;
#: ``currency_pair_symbol`` separates both, since the venue writes a currency
#: market as two codes joined by a dot and a company as a bare code. ``AMD`` and
#: ``COP`` are absent, so each stays the equity its own ``STK`` word names.
CURRENCY_LEGS: frozenset[str] = frozenset(
    {
        "AED",
        "AUD",
        "BRL",
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
        "KRW",
        "MXN",
        "MYR",
        "NOK",
        "NZD",
        "PLN",
        "RON",
        "SAR",
        "SEK",
        "SGD",
        "TRY",
        "TWD",
        "USD",
        "ZAR",
    }
)

#: The order types this connector composes, spelled as Interactive Brokers' own
#: order-type pages spell them. Its Market Order page lists the products a
#: market order reaches — "BOND, CFD, EFP, CASH, FUND, FUT, FOP, OPT, STK, WAR"
#: — and its Limit Order page lists "BOND, CASH, CFD, CMDTY, FUT, FOP, OPT, STK,
#: WAR", so ``CMDTY`` takes a limit order and no market order.
ORDER_TYPE_MARKET = "MKT"
ORDER_TYPE_LIMIT = "LMT"
ORDER_TYPE_STOP = "STP"
ORDER_TYPE_STOP_LIMIT = "STP LMT"

#: The order type each ``OrderType`` composes on this venue's own route.
#: ``TRAILING_STOP`` is absent: a trailing order takes ``trailingAmt`` and
#: ``trailingType`` in place of a price, and no path in this tree sizes one.
VENUE_ORDER_TYPES: dict[Any, str] = {
    OrderType.MARKET: ORDER_TYPE_MARKET,
    OrderType.LIMIT: ORDER_TYPE_LIMIT,
    OrderType.STOP: ORDER_TYPE_STOP,
    OrderType.STOP_LIMIT: ORDER_TYPE_STOP_LIMIT,
}

#: The side each ``OrderSide`` composes, off the ``side`` field's own enum
#: ``["BUY", "SELL"]``.
VENUE_SIDES: dict[Any, str] = {OrderSide.BUY: "BUY", OrderSide.SELL: "SELL"}

#: The times in force the ``tif`` field's own enum holds:
#: ``["DAY", "IOC", "GTC", "OPG", "PAX"]``. ``TimeInForce.FOK`` and
#: ``TimeInForce.CLS`` are in neither, so an order composed with one of those
#: would carry a value the venue does not take.
VENUE_TIMES_IN_FORCE: dict[Any, str] = {
    TimeInForce.DAY: "DAY",
    TimeInForce.GTC: "GTC",
    TimeInForce.IOC: "IOC",
    TimeInForce.OPG: "OPG",
}

#: The time in force an order carrying one this venue does not publish falls to.
DEFAULT_TIME_IN_FORCE = TimeInForce.DAY

#: The one time in force a crypto market order takes. Interactive Brokers' own
#: Cryptocurrency Trading page states it on both sides: "MKT Orders only support
#: 'IOC'." A crypto limit order takes "DAY", "GTC", "IOC".
CRYPTO_MARKET_TIME_IN_FORCE = TimeInForce.IOC
CRYPTO_TIMES_IN_FORCE = (TimeInForce.DAY, TimeInForce.GTC, TimeInForce.IOC)

#: The size step a market takes where the venue publishes no finer one. Quoted
#: whole from Interactive Brokers' own order-type Notes & Limitations page:
#: "Interacive Brokers APIs do not support fractional or cash quantity trading
#: with exception to Cryptocurrencies and Forex trading." Its own minimum-order
#: FAQ agrees: "You can place trades with an order size as low as 1 share, 1
#: contract, 1 unit of currency." Its Fractional Trading page offers a fraction
#: of a share and lists the six platforms reaching one — Trader Workstation,
#: IBKR Mobile on four devices, and Client Portal — and the API is not among
#: them, so the fraction is a platform feature and this route takes whole units.
WHOLE_UNIT_INCREMENT = 1.0

#: The security types the venue excepts from the whole-unit rule above, which
#: are its own ``CRYPTO`` and ``CASH``, and the smallest crypto order its own
#: FAQ publishes: "The minimum order size is .00000001." The security type is
#: the grain and the sector is not: ``PAXG`` is on the venue's own crypto table
#: and redeems for gold, so its sector is commodities while its order still
#: takes the crypto route's own fraction.
FRACTIONAL_ASSET_CLASSES = frozenset({"cash", "crypto"})
CRYPTO_ASSET_CLASS = "crypto"
CRYPTO_MIN_ORDER_SIZE = 1e-8

#: The security types whose own market order this platform cannot compose. The
#: venue's Limit Order page lists ``CMDTY`` among its products and its Market
#: Order page does not, and its Cryptocurrency Trading page gives a ``CRYPTO``
#: market buy the cash unit alone: "MKT Orders using 'cashQty' value." for a
#: BUY, against "LMT Order Using 'quantity' or 'totalQuantity' values." This
#: platform sizes a unit count, so a unit-count buy into a crypto market can
#: only be a limit order.
LIMIT_ONLY_ASSET_CLASSES = frozenset({"cmdty", CRYPTO_ASSET_CLASS})

#: The ``manualIndicator`` value every futures order carries. Quoted whole from
#: the field's own description: "Orders for USFUT products that do not include
#: this field will be rejected." This platform transmits with no human
#: intervention, so the flag reads False.
MANUAL_ORDER = False
MANUAL_INDICATOR_SECTORS = frozenset({"commodities", "indices", "futures_perps"})

#: The days of fills ``GET /iserver/account/trades`` serves. Quoted whole from
#: its own description: "The number of prior days prior to include in response,
#: up to a maximum of 7." The route declares that one parameter and no page
#: token, no page size and no cursor, so the ledger is a window and not a walk.
FILL_DAYS_MAX = 7

#: The milliseconds one day holds, which ``fill_days`` divides a floor by.
DAY_MS = 86_400_000.0

#: What ``list_fills`` logs so no caller reads a short answer as a whole ledger.
FILL_WINDOW_NOTE = (
    "Interactive Brokers serves at most %d days of fills on its own trade "
    "route and publishes no page token, so %d record(s) is that window and not "
    "the whole history"
)

#: The side word Interactive Brokers' own execution record carries, off the
#: ``side`` field's own enum. ``N`` nets an event contract and ``X`` expires
#: one, and neither is a buy or a sell this platform places.
FILL_SIDE_SELL = "S"
FILL_SIDES = {"B": OrderSide.BUY.value, FILL_SIDE_SELL: OrderSide.SELL.value}

#: The currency a fill's own ``commission`` figure is read in, which
#: ``BrokerBase.CASH_CURRENCY`` also names for the ledger row.
FEE_CURRENCY = "USD"

#: The snapshot fields ``get_quote`` asks for, off the venue's own field
#: numbers: 31 last, 84 bid, 86 ask.
QUOTE_FIELD_LAST = "31"
QUOTE_FIELD_BID = "84"
QUOTE_FIELD_ASK = "86"

#: The timeframe each bar width takes on ``GET /iserver/marketdata/history``,
#: whose own ``bar`` parameter spells them.
BAR_WIDTHS = {
    "1Min": "1min",
    "5Min": "5min",
    "15Min": "15min",
    "1H": "1h",
    "1D": "1d",
    "1W": "1w",
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "1h": "1h",
    "1d": "1d",
    "1w": "1w",
}
DEFAULT_BAR_WIDTH = "1d"


def rule_number(value: Any) -> Optional[float]:
    """``value`` as a positive finite float where the record published a number
    or a decimal string, else None.

    A contract record writes its ``multiplier`` and its ``incrementRules`` as
    numbers and a snapshot field as a string, so both forms are a rule.
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


def asset_class_word(asset: Any) -> str:
    """The security type one record names, lowercased, and "" for a record
    naming none.

    ``assetClass`` is the field every contract and position record carries, and
    ``sec_type`` is the same word on an execution record and an order status.
    """
    if not isinstance(asset, dict):
        return ""
    for field in ("assetClass", "sec_type", "secType"):
        held = asset.get(field)
        if isinstance(held, str) and held.strip():
            return held.strip().lower()
    return ""


def currency_pair_symbol(symbol: Any) -> bool:
    """Whether ``symbol`` names one of this venue's currency pairs.

    A pair carries ``CURRENCY_SYMBOL_SEPARATOR`` with a member of
    ``CURRENCY_LEGS`` on each side, and a bare equity code answers False.
    """
    held = str(symbol or "")
    if CURRENCY_SYMBOL_SEPARATOR not in held:
        return False
    base, _, quote = held.partition(CURRENCY_SYMBOL_SEPARATOR)
    return base.strip().upper() in CURRENCY_LEGS and (
        quote.strip().upper() in CURRENCY_LEGS
    )


def asset_sector(asset: Any) -> Optional[str]:
    """The sector one Interactive Brokers record names, and None where its own
    fields name none.

    ``venue_market_sector`` is read first and ``venue_base_sector`` second, then
    ``FUTURES_FAMILY_SECTORS``, then ``ASSET_CLASS_SECTORS``, then
    ``currency_pair_symbol``.
    """
    from ..trading.scrumming.sizing import venue_base_sector, venue_market_sector

    if not isinstance(asset, dict):
        return None
    symbol = str(asset.get("symbol") or "")
    named = venue_market_sector(VENUE_ID, symbol)
    if named:
        return str(named)
    base = symbol.partition(CURRENCY_SYMBOL_SEPARATOR)[0]
    cited = venue_base_sector(VENUE_ID, base)
    if cited:
        return str(cited)
    word = asset_class_word(asset)
    family = FUTURES_FAMILY_SECTORS.get(str(asset.get("family") or "").strip().lower())
    if word in CONTRACT_ASSET_CLASSES:
        return family or FUTURES_SECTOR
    if family and not word:
        return family
    held = ASSET_CLASS_SECTORS.get(word)
    if held:
        return held
    if currency_pair_symbol(symbol):
        return "forex"
    return None


def asset_expiry_ms(asset: Any) -> Optional[float]:
    """The epoch milliseconds one contract record expires on, off its own
    ``expirationDate``, ``expiry`` or ``lastTradingDay``.

    Each is written ``YYYYMMDD``, which this reads as local midnight, and None
    answers a record whose fields name no eight-digit date.
    """
    if not isinstance(asset, dict):
        return None
    for field in ("expirationDate", "expiry", "lastTradingDay"):
        held = asset.get(field)
        if held is None:
            continue
        stamp = str(held).strip()
        if len(stamp) != 8 or not stamp.isdigit():
            continue
        try:
            moment = time.strptime(stamp, "%Y%m%d")
        except ValueError:
            continue
        return float(time.mktime(moment)) * 1000.0
    return None


def increment_rule(asset: Any) -> Optional[float]:
    """The price step one contract record publishes, off the first entry of its
    own ``incrementRules`` array or its own ``price_increment``.

    ``increment_rule`` gives None for a record publishing neither, never a step
    of zero.
    """
    if not isinstance(asset, dict):
        return None
    rules = asset.get("incrementRules")
    if isinstance(rules, list):
        for row in rules:
            if isinstance(row, dict):
                held = rule_number(row.get("increment"))
                if held is not None:
                    return held
    return rule_number(asset.get("price_increment"))


def size_increment(asset: Any) -> Optional[float]:
    """The size step one record publishes: ``CRYPTO_MIN_ORDER_SIZE`` on a
    ``CRYPTO`` record, None on a ``CASH`` record, and ``WHOLE_UNIT_INCREMENT``
    on every record naming a sector.

    ``FRACTIONAL_ASSET_CLASSES`` names the two security types the venue's own
    API page excepts from its whole-unit rule.
    """
    word = asset_class_word(asset)
    if word == CRYPTO_ASSET_CLASS:
        return CRYPTO_MIN_ORDER_SIZE
    if word in FRACTIONAL_ASSET_CLASSES or asset_sector(asset) is None:
        return None
    return WHOLE_UNIT_INCREMENT


def asset_order_types(asset: Any) -> Optional[str]:
    """The order types one record's own security type and sector declare.

    ``ORDER_TYPES_LIMIT_ONLY`` for ``LIMIT_ONLY_ASSET_CLASSES``,
    ``ORDER_TYPES_WITH_MARKET`` for every other recorded market, and None for a
    record ``asset_sector`` answers None for.
    """
    if asset_sector(asset) is None:
        return None
    if asset_class_word(asset) in LIMIT_ONLY_ASSET_CLASSES:
        return ORDER_TYPES_LIMIT_ONLY
    return ORDER_TYPES_WITH_MARKET


# Interactive Brokers answers both halves of this itself, on its own Trading
# Outside Regular Trading Hours page: "Futures are available outside RTH. US
# stocks are not." A market listed outside the US keeps neither of the two names
# ``SESSIONS_DECLARED`` holds, so its record names no session at all.
def asset_session(asset: Any) -> Optional[str]:
    """``SESSION_US_EQUITY`` for a record naming a US-listed equity or fund
    share, and None for every other market.

    A record whose own ``isUS`` is not True names no session.
    """
    if not isinstance(asset, dict):
        return None
    if asset_sector(asset) != "stocks":
        return None
    if asset.get("isUS") is not True:
        return None
    return SESSION_US_EQUITY


def asset_rules(asset: Any) -> MarketRules:
    """The ``MarketRules`` one Interactive Brokers record publishes.

    ``read`` is False for anything that is not a record, an unnamed rule is
    None, ``contract_size`` carries the record's own ``multiplier`` and
    ``expiry_ms`` the date ``asset_expiry_ms`` reads.
    """
    if not isinstance(asset, dict):
        return MarketRules(read=False)
    return MarketRules(
        min_amount=rule_number(asset.get("min_amount")) or size_increment(asset),
        amount_increment=size_increment(asset),
        price_increment=increment_rule(asset),
        contract_size=rule_number(asset.get("multiplier")),
        session=asset_session(asset),
        order_types=asset_order_types(asset),
        expiry_ms=asset_expiry_ms(asset),
    )


def published_time_in_force(asset: Any, order_type: Any, time_in_force: Any) -> Any:
    """The time in force Interactive Brokers publishes for one order into
    ``asset``.

    ``CRYPTO_MARKET_TIME_IN_FORCE`` for a market order into a
    ``CRYPTO_ASSET_CLASS`` record, ``DEFAULT_TIME_IN_FORCE`` for a value outside
    ``CRYPTO_TIMES_IN_FORCE`` or ``VENUE_TIMES_IN_FORCE``, and ``time_in_force``
    for every other order.
    """
    crypto = asset_class_word(asset) == CRYPTO_ASSET_CLASS
    if crypto and order_type == OrderType.MARKET:
        return CRYPTO_MARKET_TIME_IN_FORCE
    if crypto and time_in_force not in CRYPTO_TIMES_IN_FORCE:
        return DEFAULT_TIME_IN_FORCE
    if time_in_force in VENUE_TIMES_IN_FORCE:
        return time_in_force
    return DEFAULT_TIME_IN_FORCE


def order_body(
    asset: Any,
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

    The five its schema marks required are always written — ``conid``,
    ``orderType``, ``quantity``, ``side``, ``tif`` — ``price`` and ``auxPrice``
    follow ``order_type``, ``manualIndicator`` rides on every
    ``MANUAL_INDICATOR_SECTORS`` order, and ``ValueError`` names a ``side`` or an
    ``order_type`` this venue does not publish.
    """
    held = asset if isinstance(asset, dict) else {}
    venue_side = VENUE_SIDES.get(side)
    if venue_side is None:
        raise ValueError(f"order side {side!r} is not one of {tuple(VENUE_SIDES)}")
    venue_type = VENUE_ORDER_TYPES.get(order_type)
    if venue_type is None:
        raise ValueError(
            f"order type {order_type!r} is not one of {tuple(VENUE_ORDER_TYPES)}"
        )
    tif = published_time_in_force(held, order_type, time_in_force)
    body: dict[str, Any] = {
        "conid": int(rule_number(held.get("conid")) or 0),
        "orderType": venue_type,
        "side": venue_side,
        "tif": VENUE_TIMES_IN_FORCE[tif],
        "quantity": float(quantity),
    }
    word = asset_class_word(held)
    if word:
        body["secType"] = word.upper()
    if client_order_id:
        body["cOID"] = str(client_order_id)[:64]
    if order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and limit_price > 0:
        body["price"] = float(limit_price)
    if order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and stop_price > 0:
        body["auxPrice"] = float(stop_price)
    if asset_sector(held) in MANUAL_INDICATOR_SECTORS:
        body["manualIndicator"] = MANUAL_ORDER
    return body


def fill_moment(moment_ms: Any) -> str:
    """``moment_ms`` as the ISO 8601 UTC moment ``bar_epoch_ms`` reads, and ""
    where it is no finite positive number.

    The venue's own execution record carries ``trade_time_r`` in epoch
    milliseconds, and ``broker_trade`` reads a string alone.
    """
    held = rule_number(moment_ms)
    if held is None:
        return ""
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(held / 1000.0))


def fill_record(execution: Any) -> dict:
    """One Interactive Brokers execution as the record ``broker_trade`` reads.

    The venue's own trade route names 28 fields per execution, ``fee`` carries
    its own ``commission`` figure in ``FEE_CURRENCY`` and ``transaction_time``
    carries ``fill_moment`` of its own ``trade_time_r``.
    """
    held = execution if isinstance(execution, dict) else {}
    return {
        "id": str(held.get("execution_id") or ""),
        "symbol": str(held.get("symbol") or ""),
        "side": FILL_SIDES.get(str(held.get("side") or "").strip().upper(), ""),
        "qty": held.get("size"),
        "price": held.get("price"),
        "fee": held.get("commission"),
        "fee_currency": FEE_CURRENCY,
        "transaction_time": fill_moment(held.get("trade_time_r")),
        "trade_time_r": held.get("trade_time_r"),
        "sec_type": held.get("sec_type"),
        "conid": held.get("conid"),
    }


def fill_days(since_ms: Any, now_ms: Any) -> int:
    """The ``days`` value ``TRADES_ROUTE`` takes for a floor of ``since_ms``,
    clamped to ``FILL_DAYS_MAX``.

    A ``since_ms`` or a ``now_ms`` that is no number asks for the whole window,
    and a floor inside one day asks for one day.
    """
    if type(since_ms) not in (int, float) or type(now_ms) not in (int, float):
        return FILL_DAYS_MAX
    span = float(now_ms) - float(since_ms)
    if not math.isfinite(span) or span <= 0.0:
        return 1
    return min(max(int(span // DAY_MS) + 1, 1), FILL_DAYS_MAX)


class IbkrConnector(BrokerBase):
    """Interactive Brokers broker connector.

    ``SECTORS_SERVED`` names the six sectors its own product pages list a market
    in, and ``place_order`` composes the body ``order_body`` builds for
    ``ORDER_ROUTE``.
    """

    #: The six sectors the venue's own pages list a market in: stocks from "over
    #: 10,000 US-listed stocks and ETFs" across "170+ markets worldwide", crypto
    #: from the 20 tokens its own FAQ table names, commodities from US Spot Gold
    #: beside its Metals, Agriculture, Energy and Softs futures families, forex
    #: from "100+ Currency Pairs On 28 Currencies", indices from its Equity
    #: Indices and Volatility Indices futures families, and futures_perps from
    #: every dated contract. No perpetual: the word names 0 of the 13 pages
    #: read, where "futures" names 265 and "currency" 137.
    SECTORS_SERVED: tuple = (
        "crypto",
        "stocks",
        "commodities",
        "forex",
        "indices",
        "futures_perps",
    )

    #: The venue publishes a paper route and names its own account record's
    #: ``type`` ``DEMO``, so ``broker_paper_route`` opens the paper session. Its
    #: own order-type page states what that session is: "Paper Trading Accounts
    #: are based on a simulated environment, and as a result, order execution
    #: behavior is not indicative of real world trading conditions."
    HAS_PAPER_ROUTE: bool = True

    #: The venue publishes its own executions on ``TRADES_ROUTE``, so
    #: ``get_my_trades`` reads ``list_fills`` and never refuses.
    PUBLISHES_FILL_HISTORY: bool = True

    def __init__(self):
        super().__init__(VENUE_ID)
        self._auth_headers: dict[str, str] = {}
        self._base_url = API_BASE + API_PREFIX
        self._account = ""
        self._session = None

    @property
    def account(self) -> str:
        """The account id ``connect`` read off ``ACCOUNTS_ROUTE``, which
        ``ORDER_ROUTE`` clears an order to."""
        return self._account

    async def connect(self, api_key: str, api_secret: str, paper: bool = True) -> bool:
        """Hold ``api_key`` as the bearer token the venue's own ``ssoBearer``
        scheme takes, read ``ACCOUNTS_ROUTE``, and answer whether it named an
        account.

        ``api_secret`` is unused, every route in the venue's own document
        declaring that one security scheme, and ``paper`` reaches the status log
        alone.
        """
        del api_secret
        self._auth_headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        if not self._auth_headers:
            self._session_refusal = "no API key is stored"
            return False
        try:
            answered = await self._request("GET", ACCOUNTS_ROUTE)
        except Exception as exc:
            logger.error("Interactive Brokers connection failed: %s", exc)
            self._session_refusal = str(exc)
            return False
        accounts = answered.get("accounts") if isinstance(answered, dict) else None
        named = [str(one) for one in accounts or [] if str(one)]
        if not named:
            self._session_refusal = "the venue named no tradable account"
            return False
        self._account = named[0]
        self._connected = True
        logger.info(
            "Connected to Interactive Brokers (%s): account=%s of %d",
            "paper" if paper else "LIVE",
            self._account,
            len(named),
        )
        return True

    async def disconnect(self):
        """Drop the held token and the held ``account``, and mark this broker
        disconnected."""
        self._auth_headers = {}
        self._account = ""
        self._connected = False
        if self._session is not None:
            try:
                await self._session.close()
            except Exception as exc:
                logger.warning("Interactive Brokers session already closed: %s", exc)
            self._session = None

    async def get_account(self) -> AccountInfo:
        """The account summary ``LEDGER_ROUTE`` publishes for the held
        ``account``.

        That route is keyed by currency and ``CASH_CURRENCY`` names the row this
        reads.
        """
        if not self._account:
            return AccountInfo()
        data = await self._request("GET", LEDGER_ROUTE.format(account=self._account))
        row = data.get(self.CASH_CURRENCY) if isinstance(data, dict) else None
        held = row if isinstance(row, dict) else {}
        return AccountInfo(
            account_id=self._account,
            equity=float(held.get("netliquidationvalue", 0) or 0),
            cash=float(held.get("settledcash", 0) or 0),
            buying_power=float(held.get("cashbalance", 0) or 0),
            portfolio_value=float(held.get("netliquidationvalue", 0) or 0),
        )

    async def get_positions(self) -> list[StockPosition]:
        """Every open position the held ``account`` carries, read page by page
        off ``POSITIONS_ROUTE``.

        A page shorter than ``POSITION_PAGE_SIZE`` ends the list, and the walk
        stops at ``POSITION_PAGES_MAX``.
        """
        if not self._account:
            return []
        found: list[StockPosition] = []
        page = 0
        while page < POSITION_PAGES_MAX:
            answered = await self._request(
                "GET", POSITIONS_ROUTE.format(account=self._account, page=page)
            )
            rows = answered if isinstance(answered, list) else []
            for row in rows:
                built = self._position(row)
                if built is not None:
                    found.append(built)
            if len(rows) < POSITION_PAGE_SIZE:
                return found
            page += 1
        logger.warning(
            "Interactive Brokers positions stopped at %d pages with %d row(s)",
            page,
            len(found),
        )
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

        ``order_body`` composes the ticket and ``published_time_in_force`` names
        the time in force the venue publishes for ``symbol``.
        """
        asset = self._asset(symbol)
        held_tif = published_time_in_force(asset, order_type, time_in_force)
        if held_tif is not time_in_force:
            logger.info(
                "Interactive Brokers %s takes no %s time in force on a %s "
                "order; sending %s",
                symbol,
                getattr(time_in_force, "value", time_in_force),
                getattr(order_type, "value", order_type),
                held_tif.value,
            )
        ticket = order_body(
            asset,
            side,
            quantity,
            order_type=order_type,
            limit_price=limit_price,
            stop_price=stop_price,
            time_in_force=time_in_force,
        )
        answered = await self._request(
            "POST",
            ORDER_ROUTE.format(account=self._account),
            {"orders": [ticket]},
        )
        return self._parse_order(answered, symbol=symbol, ticket=ticket)

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel one working order on ``CANCEL_ROUTE``, and answer False where
        the venue refused it or no ``account`` is held."""
        if not self._account or not order_id:
            return False
        try:
            answered = await self._request(
                "DELETE",
                CANCEL_ROUTE.format(account=self._account, order_id=str(order_id)),
            )
        except Exception as exc:
            logger.warning("Interactive Brokers cancel refused: %s", exc)
            return False
        held = answered if isinstance(answered, dict) else {}
        return str(held.get("msg") or "").strip().lower() != "error"

    async def get_order(self, order_id: str) -> StockOrder:
        """The status of one order, read off ``ORDER_STATUS_ROUTE`` through
        ``_status_order``."""
        if not order_id:
            return StockOrder()
        answered = await self._request(
            "GET", ORDER_STATUS_ROUTE.format(order_id=str(order_id))
        )
        return self._status_order(answered, order_id=str(order_id))

    async def get_open_orders(self) -> list[StockOrder]:
        """Every order ``ORDERS_ROUTE`` publishes for this brokerage session.

        That route answers the session's orders, filled and cancelled ones
        included, under its own ``orders`` key.
        """
        answered = await self._request("GET", ORDERS_ROUTE)
        rows = answered.get("orders") if isinstance(answered, dict) else None
        return [self._status_order(row) for row in rows or [] if isinstance(row, dict)]

    async def get_quote(self, symbol: str) -> StockQuote:
        """The top of book ``SNAPSHOT_ROUTE`` publishes for ``symbol``.

        The venue keys market data by ``conid``, and a ``symbol`` the held asset
        list names no contract for answers an empty ``StockQuote``.
        """
        asset = self._asset(symbol)
        conid = rule_number(asset.get("conid")) if asset else None
        if conid is None:
            return StockQuote(symbol=symbol)
        answered = await self._request(
            "GET",
            f"{SNAPSHOT_ROUTE}?conids={int(conid)}"
            f"&fields={QUOTE_FIELD_LAST},{QUOTE_FIELD_BID},{QUOTE_FIELD_ASK}",
        )
        rows = answered if isinstance(answered, list) else []
        row = rows[0] if rows and isinstance(rows[0], dict) else {}
        return StockQuote(
            symbol=symbol,
            bid=rule_number(row.get(QUOTE_FIELD_BID)) or 0.0,
            ask=rule_number(row.get(QUOTE_FIELD_ASK)) or 0.0,
            last=rule_number(row.get(QUOTE_FIELD_LAST)) or 0.0,
            timestamp=time.time(),
        )

    async def get_bars(
        self, symbol: str, timeframe: str = "1D", limit: int = 100
    ) -> list[dict]:
        """The bars ``HISTORY_ROUTE`` publishes for ``symbol`` at ``timeframe``.

        That route takes a ``conid``, a ``period`` and a ``bar`` off
        ``BAR_WIDTHS``, and answers each bar under ``t``, ``o``, ``h``, ``l``,
        ``c`` and ``v``.
        """
        asset = self._asset(symbol)
        conid = rule_number(asset.get("conid")) if asset else None
        if conid is None:
            return []
        width = BAR_WIDTHS.get(str(timeframe), DEFAULT_BAR_WIDTH)
        answered = await self._request(
            "GET",
            f"{HISTORY_ROUTE}?conid={int(conid)}&bar={width}"
            f"&period={max(int(limit), 1)}{width[-1]}",
        )
        rows = answered.get("data") if isinstance(answered, dict) else None
        built: list[dict] = []
        for bar in rows or []:
            if not isinstance(bar, dict):
                continue
            built.append(
                {
                    "timestamp": bar.get("t", ""),
                    "open": float(bar.get("o", 0) or 0),
                    "high": float(bar.get("h", 0) or 0),
                    "low": float(bar.get("l", 0) or 0),
                    "close": float(bar.get("c", 0) or 0),
                    "volume": int(float(bar.get("v", 0) or 0)),
                }
            )
        return built

    async def get_market_status(self) -> dict:
        """A closed market, which is the answer with no venue-wide clock.

        The venue publishes ``GET /contract/trading-schedule`` per contract and
        no account-wide clock, so no one reading names the whole venue.
        """
        return {"is_open": False, "next_open": "", "next_close": ""}

    async def list_assets(self, status: str = "active") -> list[dict]:
        """Every contract record ``SECDEF_ROUTE`` publishes for the held
        ``scan_symbols``, kept for ``held_assets`` and ``record_markets``.

        The venue publishes no one route listing every market it serves — its own
        document names a per-exchange stock route, a per-symbol futures route and
        a per-currency pairs route — and ``scan_symbols`` is the contract id set
        this connector is given.
        """
        del status
        names = sorted(self._scan_symbols)
        if not names:
            self._assets = []
            return []
        answered = await self._request(
            "GET", f"{SECDEF_ROUTE}?conids={','.join(names)}"
        )
        rows = answered.get("secdef") if isinstance(answered, dict) else None
        self._assets = [row for row in rows or [] if isinstance(row, dict)]
        return list(self._assets)

    async def list_fills(
        self,
        symbol: str = "",
        since_ms: Optional[float] = None,
        until_ms: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> list[dict]:
        """Every execution ``TRADES_ROUTE`` publishes for ``symbol`` inside its
        own ``FILL_DAYS_MAX`` window.

        That route declares the one ``days`` parameter ``fill_days`` sets and no
        page token, no page size and no cursor, and ``FILL_WINDOW_NOTE`` records
        that the answer is a window.
        """
        days = fill_days(since_ms, time.time() * 1000.0)
        answered = await self._request("GET", f"{TRADES_ROUTE}?days={days}")
        rows = answered if isinstance(answered, list) else []
        name = str(symbol or "")
        found: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            built = fill_record(row)
            if name and built["symbol"] != name:
                continue
            moment = rule_number(built.get("trade_time_r"))
            if moment is not None and until_ms is not None and moment > float(until_ms):
                continue
            if moment is not None and since_ms is not None and moment < float(since_ms):
                continue
            found.append(built)
        logger.info(FILL_WINDOW_NOTE, days, len(found))
        if limit is None:
            return found
        return found[: max(int(limit), 1)]

    def market_rules(self, asset: Any) -> MarketRules:
        """The ``MarketRules`` one of this broker's own contract records
        publishes, read through ``asset_rules`` with no broker contacted."""
        return asset_rules(asset)

    def asset_sector(self, asset: Any) -> Optional[str]:
        """The sector one of this broker's own contract records names, read
        through ``asset_sector`` with no broker contacted."""
        return asset_sector(asset)

    def _asset(self, symbol: Any) -> dict:
        """The held contract record naming ``symbol``, and {} where no record
        does."""
        name = str(symbol or "")
        for held in self._assets:
            if isinstance(held, dict) and str(held.get("symbol") or "") == name:
                return held
        return {}

    @staticmethod
    def _position(row: Any) -> Optional[StockPosition]:
        """One position record as a ``StockPosition``, and None for a row naming
        no symbol.

        ``unrealized_pnl_pct`` is read off the record's own ``mktValue`` less its
        ``unrealizedPnl``, which is the cost the venue published.
        """
        if not isinstance(row, dict):
            return None
        symbol = str(row.get("ticker") or row.get("contractDesc") or "")
        if not symbol:
            return None
        units = float(row.get("position", 0) or 0)
        value = float(row.get("mktValue", 0) or 0)
        unrealised = float(row.get("unrealizedPnl", 0) or 0)
        basis = abs(value) - unrealised
        return StockPosition(
            symbol=symbol,
            quantity=units,
            avg_entry_price=float(row.get("avgPrice", 0) or 0),
            current_price=float(row.get("mktPrice", 0) or 0),
            market_value=value,
            unrealized_pnl=unrealised,
            unrealized_pnl_pct=0.0 if basis <= 0.0 else unrealised / basis * 100.0,
            side=PositionSide.LONG if units >= 0 else PositionSide.SHORT,
        )

    @staticmethod
    def _parse_order(answered: Any, symbol: str, ticket: dict) -> StockOrder:
        """The ``StockOrder`` one ``ORDER_ROUTE`` submission answers.

        That route answers an array whose first element carries ``order_id`` and
        ``order_status``, and ``ValueError`` names a reply message or a reject
        carrying neither.
        """
        rows = answered if isinstance(answered, list) else [answered]
        row = rows[0] if rows and isinstance(rows[0], dict) else {}
        order_id = str(row.get("order_id") or "")
        if not order_id:
            raise ValueError(
                f"Interactive Brokers answered no order id for {symbol}: {row}"
            )
        return StockOrder(
            order_id=order_id,
            symbol=symbol,
            side=(
                OrderSide.SELL
                if str(ticket.get("side")) == VENUE_SIDES[OrderSide.SELL]
                else OrderSide.BUY
            ),
            order_type=(
                OrderType.LIMIT
                if str(ticket.get("orderType")) == ORDER_TYPE_LIMIT
                else OrderType.MARKET
            ),
            quantity=float(ticket.get("quantity", 0) or 0),
            limit_price=float(ticket.get("price", 0) or 0),
            stop_price=float(ticket.get("auxPrice", 0) or 0),
            status=str(row.get("order_status") or "new"),
            submitted_at=time.time(),
        )

    @staticmethod
    def _status_order(answered: Any, order_id: str = "") -> StockOrder:
        """One order-status record as a ``StockOrder``, with ``order_id``
        standing in where the record names none."""
        held = answered if isinstance(answered, dict) else {}
        side_word = str(held.get("side") or "").strip().upper()
        type_word = str(held.get("orderType") or "").strip().upper()
        return StockOrder(
            order_id=str(held.get("order_id") or held.get("orderId") or order_id),
            symbol=str(held.get("ticker") or held.get("symbol") or ""),
            side=(
                OrderSide.SELL
                if side_word in (FILL_SIDE_SELL, VENUE_SIDES[OrderSide.SELL])
                else OrderSide.BUY
            ),
            order_type=(
                OrderType.LIMIT
                if type_word in (ORDER_TYPE_LIMIT, "LIMIT")
                else OrderType.MARKET
            ),
            quantity=float(held.get("totalSize", 0) or held.get("total_size", 0) or 0),
            limit_price=float(held.get("limit_price", 0) or held.get("price", 0) or 0),
            stop_price=float(held.get("stop_price", 0) or 0),
            status=str(held.get("order_status") or held.get("status") or "new"),
            filled_qty=float(
                held.get("filledQuantity", 0) or held.get("cumFill", 0) or 0
            ),
            avg_fill_price=float(
                held.get("avgPrice", 0) or held.get("average_price", 0) or 0
            ),
        )

    async def _request(
        self, method: str, path: str, body: Optional[dict] = None
    ) -> Any:
        """One request to ``API_BASE`` carrying the held bearer token.

        A status of 204 answers {}, a status outside 200 raises with the body the
        venue answered, and a body that is no JSON raises as well.
        """
        import aiohttp

        url = self._base_url + path
        if self._session is None:
            self._session = aiohttp.ClientSession()
        async with self._session.request(
            method, url, headers=dict(self._auth_headers), json=body
        ) as resp:
            if resp.status == 204:
                return {}
            text = await resp.text()
            if resp.status != 200:
                raise Exception(f"Interactive Brokers API {resp.status}: {text}")
            try:
                return json.loads(text) if text else {}
            except ValueError as exc:
                raise Exception(
                    f"Interactive Brokers answered no JSON on {path}: {exc}"
                ) from exc


__all__ = [
    "ACCOUNTS_ROUTE",
    "API_BASE",
    "API_PREFIX",
    "ASSET_CLASS_SECTORS",
    "BAR_WIDTHS",
    "CANCEL_ROUTE",
    "CONIDS_ROUTE",
    "CONTRACT_ASSET_CLASSES",
    "CRYPTO_ASSET_CLASS",
    "CRYPTO_MARKET_TIME_IN_FORCE",
    "CRYPTO_MIN_ORDER_SIZE",
    "CRYPTO_TIMES_IN_FORCE",
    "CURRENCY_LEGS",
    "CURRENCY_PAIRS_ROUTE",
    "CURRENCY_SYMBOL_SEPARATOR",
    "DAY_MS",
    "DEFAULT_BAR_WIDTH",
    "DEFAULT_TIME_IN_FORCE",
    "FEE_CURRENCY",
    "FILL_DAYS_MAX",
    "FILL_SIDES",
    "FILL_SIDE_SELL",
    "FILL_WINDOW_NOTE",
    "FRACTIONAL_ASSET_CLASSES",
    "FUTURES_FAMILY_SECTORS",
    "FUTURES_SECTOR",
    "HISTORY_ROUTE",
    "LEDGER_ROUTE",
    "LIMIT_ONLY_ASSET_CLASSES",
    "MANUAL_INDICATOR_SECTORS",
    "MANUAL_ORDER",
    "ORDERS_ROUTE",
    "ORDER_ROUTE",
    "ORDER_STATUS_ROUTE",
    "ORDER_TYPE_LIMIT",
    "ORDER_TYPE_MARKET",
    "ORDER_TYPE_STOP",
    "ORDER_TYPE_STOP_LIMIT",
    "POSITIONS_ROUTE",
    "POSITION_PAGES_MAX",
    "POSITION_PAGE_SIZE",
    "POSITION_ROUTE",
    "QUOTE_FIELD_ASK",
    "QUOTE_FIELD_BID",
    "QUOTE_FIELD_LAST",
    "SECDEF_ROUTE",
    "SNAPSHOT_ROUTE",
    "TRADES_ROUTE",
    "VENUE_ID",
    "VENUE_ORDER_TYPES",
    "VENUE_SIDES",
    "VENUE_TIMES_IN_FORCE",
    "WHOLE_UNIT_INCREMENT",
    "IbkrConnector",
    "asset_class_word",
    "asset_expiry_ms",
    "asset_order_types",
    "asset_rules",
    "asset_sector",
    "asset_session",
    "currency_pair_symbol",
    "fill_days",
    "fill_moment",
    "fill_record",
    "increment_rule",
    "order_body",
    "published_time_in_force",
    "rule_number",
    "size_increment",
]
