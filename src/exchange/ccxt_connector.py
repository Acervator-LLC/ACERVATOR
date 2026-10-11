"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.

CCXT-backed :class:`ExchangeInterface` for the venues in ``SUPPORTED_EXCHANGES``.
"""

from __future__ import annotations

from ..core.encryption import unescape_pem_newlines
from ..core.fmt import fmt_price_coerced
from ..core.retry import linear_delay, retry_any, retry_sync, with_retry
from ..core.safe_url import SafeRequest, safe_urlopen
from ..trading.ta_engine import DEFAULT_WEIGHTS
import asyncio
import logging
import math
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from collections.abc import Callable, Mapping
from functools import lru_cache
from urllib.error import HTTPError, URLError
from concurrent.futures import ThreadPoolExecutor

from src.core.trade_historian import HistoryAnalysis, scan_on_connect
from typing import Any, Optional

# The historian thread calls it as cb(symbol, analysis) and discards the result.
HistoryCallback = Callable[[str, HistoryAnalysis], object]


# Submissions past this depth are refused rather than queued.
SYNC_QUEUE_CAP: int = 8

# Slots of SYNC_QUEUE_CAP a bulk read leaves free: one for its own call and one
# for the next reader, so its submission is never the one that fills the queue.
BULK_READ_RESERVE_SLOTS: int = 2

# Resident sync calls a bulk read submits at or below.
BULK_READ_ADMIT_DEPTH: int = SYNC_QUEUE_CAP - BULK_READ_RESERVE_SLOTS

# Longest await_bulk_read_slot waits before it submits regardless of depth.
BULK_READ_WAIT_BUDGET_SEC: float = 60.0

# Gap between two reads of _sync_queue_depth while a bulk read waits.
BULK_READ_WAIT_SLICE_SEC: float = 0.05

# sync_connect market-load budget: 3 tries, waiting 2s then 4s.
CONNECT_ATTEMPTS: int = 3
CONNECT_BACKOFF_STEP_S: float = 2.0

# Outer wait_for budget for one sync CCXT call.
SYNC_CALL_TIMEOUT_SEC: float = 25.0

# Gap between ccxt abandoning a request and the outer wait firing. It only has
# to cover the hand-off from the worker thread back to the loop, measured at
# 90ms, so a wider gap would refuse slow reads that still return a price.
CCXT_TIMEOUT_HEADROOM_SEC: float = 1.0

# ccxt's own per-request timeout, kept below the outer wait so ccxt gives up
# first and returns the single worker instead of leaking it.
CCXT_REQUEST_TIMEOUT_MS: int = int(
    (SYNC_CALL_TIMEOUT_SEC - CCXT_TIMEOUT_HEADROOM_SEC) * 1000
)


# ccxt caps a coinbase fetch_ohlcv page at this many candles.
EFFECTIVE_OHLCV_PAGE_SIZE = 300

# get_spot_positions answers from _spot_positions_cache within this many seconds.
SPOT_POSITIONS_CACHE_SEC: float = 60.0


class CCXTQueueFullError(RuntimeError):
    """Raised by ``_call_sync`` when the connector's queue is at capacity."""


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
from .api_logger import get_api_log
from .market_pairs_scout import row_quote_volume_24h
from .market_rules_store import record_venue

logger = logging.getLogger("acervator.exchange")

# Supported exchanges — maps exchange_id to the CCXT class name
SUPPORTED_EXCHANGES: dict[str, str] = {
    "binance": "binance",
    "coinbase": "coinbase",
    "kraken": "kraken",
    "kucoin": "kucoin",
    "bybit": "bybit",
    "okx": "okx",
    "gateio": "gateio",
    "bitget": "bitget",
    "huobi": "huobi",  # Renamed to 'htx' in newer CCXT — see CCXT_CLASS_ALIASES
    "mexc": "mexc",
    "bitfinex": "bitfinex",
    "gemini": "gemini",
    "poloniex": "poloniex",
    "bitstamp": "bitstamp",
    "cryptocom": "cryptocom",
}

# Historical registry ids mapped to the class names newer CCXT uses.
CCXT_CLASS_ALIASES: dict[str, str] = {
    "gateio": "gate",
    "huobi": "htx",
}


VENUE_LOST = "lost_connection"
VENUE_RATE_LIMITED = "rate_limited"
VENUE_CREDENTIAL_REJECTED = "credential_rejected"
VENUE_ANSWERED = "answered"


def _ccxt_error_types(names: tuple[str, ...]) -> tuple[type[BaseException], ...]:
    try:
        from ccxt.base import errors
    except ImportError:
        return ()
    found = []
    for name in names:
        held = getattr(errors, name, None)
        if isinstance(held, type) and issubclass(held, BaseException):
            found.append(held)
    return tuple(found)


@lru_cache(maxsize=1)
def _refusal_order() -> tuple[tuple[str, tuple[type[BaseException], ...]], ...]:
    """The four refusal classes with their ccxt types, in the order they are tested.

    The order is load-bearing. ccxt files every rate limit under ``NetworkError``
    in ``ccxt/base/errors.py``, so the classes its ``order_router`` names as the
    venue answering are matched before the transport class. That leaves
    ``RequestTimeout`` and a bare ``NetworkError`` as the only ccxt types meaning
    the call came back without an answer. The connect pre-flight runs on urllib
    rather than ccxt, so ``URLError`` joins the transport class and the
    ``HTTPError`` it parents joins the answering class, ahead of it.
    """
    return (
        (VENUE_CREDENTIAL_REJECTED, _ccxt_error_types(("AuthenticationError",))),
        (
            VENUE_RATE_LIMITED,
            _ccxt_error_types(("RateLimitExceeded", "DDoSProtection")),
        ),
        (
            VENUE_ANSWERED,
            _ccxt_error_types(("ExchangeNotAvailable", "InvalidNonce")) + (HTTPError,),
        ),
        (
            VENUE_LOST,
            _ccxt_error_types(("NetworkError",)) + (TimeoutError, URLError),
        ),
    )


def classify_venue_refusal(exc: BaseException) -> str:
    """Name which of the four refusal classes one venue's failure belongs to.

    The Exchange Status panel colours a venue from what this records, so a rate
    limit and a rejected credential must not read as a lost connection.
    """
    for label, types in _refusal_order():
        if types and isinstance(exc, types):
            return label
    return VENUE_ANSWERED


def _alert_venue(event_name: str, title: str, message: str) -> None:
    """Send one venue alert on its own thread, so no channel blocks a venue call.

    The Telegram channel places an HTTPS request, and the callers run on the
    asyncio loop thread.
    """

    def deliver() -> None:
        try:
            from ..core.notifications import AlertEvent, get_notification_manager

            event = getattr(AlertEvent, event_name, None)
            if event is not None:
                get_notification_manager().send(event, title, message)
        except Exception as exc:  # an alert channel must not fail a venue call
            logger.warning("Venue alert %s not sent: %s", event_name, exc)

    threading.Thread(target=deliver, daemon=True, name="venue-alert").start()


def note_venue_refusal(exchange_id: str, exc: BaseException) -> str:
    """Record one venue refusal where it changes the venue's state, and name its class.

    Called from the connector paths that already catch a venue refusing a call.
    A lost connection writes the record the Exchange Status panel draws red and
    sends the lost-connection alert. A rejected credential drops the record, so
    the panel draws the venue unchecked, which is the colour the manual labels
    "No valid credentials". A rate limit writes nothing, because the venue
    answered.
    """
    from .credential_state import (
        CONNECTION_LOST,
        forget,
        record_connection_lost,
        recorded_state,
    )

    kind = classify_venue_refusal(exc)
    if kind == VENUE_LOST:
        if recorded_state(exchange_id) != CONNECTION_LOST:
            record_connection_lost(exchange_id)
            _alert_venue(
                "CONNECTION_LOST",
                f"{exchange_id.capitalize()} connection lost",
                f"{type(exc).__name__} on an exchange call. "
                "The venue did not answer.",
            )
    elif kind == VENUE_CREDENTIAL_REJECTED:
        forget(exchange_id)
    return kind


def note_venue_answered(exchange_id: str) -> bool:
    """Record that one venue answered an authenticated call, and say whether it changed.

    Every call records validated and restamps the time, so a red left by a
    dropped connection clears once the venue answers again and an explicit check
    refreshes the stamp. The restored alert is sent only where the record being
    replaced was a lost connection.
    """
    from .credential_state import (
        CONNECTION_LOST,
        VALIDATED,
        record_validated,
        recorded_state,
    )

    was = recorded_state(exchange_id)
    record_validated(exchange_id)
    if was == CONNECTION_LOST:
        _alert_venue(
            "CONNECTION_RESTORED",
            f"{exchange_id.capitalize()} connection restored",
            "The venue answered an authenticated call again.",
        )
    return was != VALIDATED


def resolve_ccxt_class(ccxt_module: Any, ccxt_id: str) -> Any:
    """Return the CCXT class for ``ccxt_id``, trying its alias, or ``None``."""
    cls = getattr(ccxt_module, ccxt_id, None)
    if cls is None:
        alias = CCXT_CLASS_ALIASES.get(ccxt_id)
        if alias:
            cls = getattr(ccxt_module, alias, None)
    return cls


# Exchanges needing an API passphrase, passed to CCXT as 'password'.
PASSPHRASE_EXCHANGES: set[str] = {
    "kucoin",
    "okx",
    "bitget",
}

# Date the venue facts below were last measured.
VENUE_MEASUREMENT_DATE: str = "2026-08-28"

# Venues whose public endpoints refused a US IP at VENUE_MEASUREMENT_DATE.
US_IP_BLOCKED_EXCHANGES: set[str] = {
    "binance",
    "bybit",
}

# Venues reachable from a US IP whose terms refuse a US account. Gate.io's own
# user agreement clause 2.10 states it does not intend to provide services to
# "U.S. persons" and "expressly prohibit the same from using any of our
# Services", and its restricted-locations page names the United States first.
# Bitget's Terms of Use define "Prohibited Countries" in section 1 as a list
# "including ... the United States (including the following U.S. Territories:
# Puerto Rico, Guam, U.S. Virgin Islands, American Samoa and the Northern
# Mariana Islands ...)", section 2.8 requires the account holder to be "not a
# Restricted Person", which section 1 defines as one who "resides or is
# established, or has operations in any of the Prohibited Countries", and
# section 11.1(xvii) forbids anyone to "access, use, or attempt to access or
# use, Services directly or indirectly with (1) jurisdictions Bitget has deemed
# high risk, including but not limited to, the Prohibited Countries".
US_ACCOUNT_RESTRICTED_EXCHANGES: set[str] = {
    "bitget",
    "gateio",
    "poloniex",
    "huobi",
}

# Union of both refusals — the set the connect path warns on.
US_RESTRICTED_EXCHANGES: set[str] = (
    US_IP_BLOCKED_EXCHANGES | US_ACCOUNT_RESTRICTED_EXCHANGES
)

# Venues Acervator has actually traded on.
VERIFIED_EXCHANGES: set[str] = {
    "coinbase",
}

# The words exchange_label shows and sync_connect logs for each refusal.
US_IP_BLOCKED_NOTE: str = "US address refused"
US_ACCOUNT_RESTRICTED_NOTE: str = "US account restricted"

# Pre-flight test URLs — public endpoints requiring no auth
PREFLIGHT_URLS: dict[str, str] = {
    "binance": "https://api.binance.com/api/v3/ping",
    "coinbase": "https://api.coinbase.com/api/v3/brokerage/market/products?limit=1",
    "kraken": "https://api.kraken.com/0/public/SystemStatus",
    "kucoin": "https://api.kucoin.com/api/v1/timestamp",
    "bybit": "https://api.bybit.com/v5/market/time",
    "okx": "https://www.okx.com/api/v5/public/time",
    "gateio": "https://api.gateio.ws/api/v4/spot/currencies",
    "bitget": "https://api.bitget.com/api/v2/public/time",
    "huobi": "https://api.huobi.pro/v1/common/timestamp",
    "mexc": "https://api.mexc.com/api/v3/ping",
    "bitfinex": "https://api-pub.bitfinex.com/v2/platform/status",
    "gemini": "https://api.gemini.com/v1/symbols",
    "poloniex": "https://api.poloniex.com/markets",
    "bitstamp": "https://www.bitstamp.net/api/v2/ticker/btcusd/",
    "cryptocom": "https://api.crypto.com/exchange/v1/public/get-instruments",
}

# Exchange-specific CCXT options applied during sync_connect
EXCHANGE_OPTIONS: dict[str, dict] = {
    "coinbase": {
        "advanced": True,
        "fetchMarkets": "fetchMarketsV3",
        "fetchTicker": "fetchTickerV3",
        "fetchTickers": "fetchTickersV3",
        "fetchAccounts": "fetchAccountsV3",
        "fetchBalance": "v3PrivateGetBrokerageAccounts",
    },
}

# Exchanges where fetchCurrencies must be disabled (deprecated v2 endpoints)
DISABLE_FETCH_CURRENCIES: set[str] = {
    "coinbase",  # v2/currencies deprecated for CDP keys
}

#: The products method each venue answers an extra asset class's products on,
#: and the method ``_sector_products`` calls. ccxt exposes it as an implicit
#: endpoint method on the exchange instance.
VENUE_PRODUCTS_METHOD: dict[str, str] = {
    "coinbase": "v3PublicGetBrokerageMarketProducts",
}

#: The ``product_type`` each venue serves one asset class under. ccxt's
#: ``fetch_markets_v3`` asks for the default set and for FUTURE twice, so a
#: type named here is one ``load_markets`` never requests.
VENUE_CLASS_PRODUCT_TYPES: dict[str, dict[str, str]] = {
    "coinbase": {"stocks": "EQUITY"},
}

#: The field an asset-category row names its code under.
ASSET_CODE_KEY = "currency"

#: The field an asset-category row names its sector list under.
ASSET_CATEGORY_KEY = "category"

#: The key an asset-sector response carries its rows under where the response
#: is a mapping rather than the row list itself.
ASSET_SECTOR_ROWS_KEY = "data"

#: The separator an instrument id puts between its base asset and the rest of
#: the id. A record naming it as its ``code_leg`` has ``_read_asset_sector_rows``
#: take the asset code off the text before the first one, which is the only
#: place a venue publishing no base-code field names the code.
ASSET_CODE_LEG = "-"


@dataclass(frozen=True)
class AssetSectorRecord:
    """How one venue publishes its own asset sectors.

    ``_published_asset_sectors`` calls ``method`` once per entry in
    ``requests``, reads each row's ``code_key`` as the asset code and its
    ``sector_key`` as the sector, narrowed by ``code_leg``, and translates that
    sector through ``words`` before ``asset_class_named`` resolves it.
    """

    method: str
    requests: tuple[dict[str, str], ...] = ()
    code_key: str = ASSET_CODE_KEY
    code_leg: str = ""
    sector_key: str = ASSET_CATEGORY_KEY
    words: Mapping[str, str] = MappingProxyType({})


#: What a ``words`` row maps a venue's own category word onto where that word
#: names no family outside crypto. ``market_asset_class`` then reads the sector
#: as published and empty, which leaves ``is_contract_market`` to tell a spot
#: pair from a perpetual, exactly as a venue omitting the word is read.
NO_PUBLISHED_FAMILY = ""


#: The public, credential-free asset-sector record each venue publishes, and
#: the record ``_published_asset_sectors`` reads. Gate.io's ``/spot/currencies``
#: carries a ``category`` list per asset code naming ``stocks``, ``indices``,
#: ``metals``, ``commodities`` or ``forex``, which is the platform's own
#: vocabulary with ``metals`` retired onto commodities. Bitget's
#: ``/v3/market/instruments`` carries a ``symbolType`` per market naming
#: ``crypto``, ``stock``, ``metal`` or ``commodity``, refuses a call with no
#: ``category``, and publishes no currency and no index family. Its ``crypto``
#: word names what Gate.io's empty list names, so it maps onto
#: ``NO_PUBLISHED_FAMILY`` and a crypto-underlying perpetual keeps the sector
#: ``is_contract_market`` gives it. OKX's ``/public/instruments`` carries an
#: ``instCategory`` per instrument, which its own documentation calls "the asset
#: category of the instrument's base asset (the first segment of the instrument
#: ID)" and numbers "1: Crypto 3: Stocks 4: Commodities 5: Forex 6: Bonds"
#: against "": Not available. It refuses a call with no ``instType``, publishes
#: no index value in the vocabulary at all, and publishes ``5`` on none of its
#: instruments. ``1`` names what Gate.io's empty list names, and ``6`` names a
#: sector ``ASSET_CLASSES`` does not draw, so both map onto
#: ``NO_PUBLISHED_FAMILY``.
VENUE_ASSET_SECTOR_RECORDS: dict[str, AssetSectorRecord] = {
    "gateio": AssetSectorRecord(method="publicSpotGetCurrencies"),
    "okx": AssetSectorRecord(
        method="publicGetPublicInstruments",
        requests=(
            {"instType": "SPOT"},
            {"instType": "MARGIN"},
            {"instType": "SWAP"},
            {"instType": "FUTURES"},
        ),
        code_key="instId",
        code_leg=ASSET_CODE_LEG,
        sector_key="instCategory",
        words=MappingProxyType(
            {
                "1": NO_PUBLISHED_FAMILY,
                "3": "stocks",
                "4": "commodities",
                "5": "forex",
                "6": NO_PUBLISHED_FAMILY,
            }
        ),
    ),
    "bitget": AssetSectorRecord(
        method="publicUtaGetV3MarketInstruments",
        requests=(
            {"category": "SPOT"},
            {"category": "USDT-FUTURES"},
            {"category": "COIN-FUTURES"},
            {"category": "USDC-FUTURES"},
            {"category": "MARGIN"},
        ),
        code_key="baseCoin",
        sector_key="symbolType",
        words=MappingProxyType(
            {
                "stock": "stocks",
                "metal": "metals",
                "commodity": "commodities",
                "crypto": NO_PUBLISHED_FAMILY,
            }
        ),
    ),
}

#: The key a products response carries its rows under.
PRODUCTS_KEY = "products"

#: Rows one products call asks for. Coinbase caps a page at 1000 and ignores
#: ``offset``, so a second page repeats the first and is not requested.
PRODUCTS_PAGE_LIMIT = 1000

#: The record a futures product carries its venue labels under.
FUTURES_DETAILS_KEY = "future_product_details"

#: The key ``FUTURES_DETAILS_KEY`` carries the base units one contract stands
#: for under. ccxt's own ``parse_contract_market`` reads it into
#: ``CONTRACT_SIZE_FIELD``, and ``parse_spot_market`` reads nothing into it.
CONTRACT_SIZE_KEY = "contract_size"

#: The ccxt market field a parsed contract record carries its contract size
#: under.
CONTRACT_SIZE_FIELD = "contractSize"

#: The key a product record carries the step a cash amount moves by under. ccxt
#: reads it into ``precision.price`` only where the product published no
#: ``price_increment``, so no parsed field names the quote step alone.
QUOTE_INCREMENT_KEY = "quote_increment"

#: The record a product carries the venue's own trading session under. Coinbase
#: publishes it on every product, holding a daily window on a dated contract and
#: nothing on a spot pair and a perpetual.
SESSION_DETAILS_KEY = "fcm_trading_session_details"

#: The record an equity product carries its own trading permissions under. ccxt's
#: ``parse_spot_market`` reads nothing out of it and keeps the whole raw product
#: row under ``info``, so the record survives the parse.
EQUITY_DETAILS_KEY = "equity_product_details"

#: The key ``EQUITY_DETAILS_KEY`` carries one permission flag per side and per
#: size shape under.
EQUITY_FLAGS_KEY = "equity_trading_flags"

#: The flag naming whether any buy or sell flow is enabled on the product.
EQUITY_TRADABLE_FLAG = "tradable"

#: The flag each buy shape is published under, read in ``equity_size_shapes``.
EQUITY_BUY_FLAGS = (
    "buy_whole_shares",
    "buy_fractional_shares",
    "buy_notional",
)

#: The flag each sell shape is published under, in the same shape order.
EQUITY_SELL_FLAGS = (
    "sell_whole_shares",
    "sell_fractional_shares",
    "sell_notional",
)

#: The ccxt market field set True on a tokenised equity record, which parses as
#: a spot market and carries no ``EQUITY_MARKET_TYPE`` type.
STOCK_MARKET_KEY = "stock"

#: The key a tokenised equity row names its permitted sides under. Binance
#: publishes ``BUY_SELL``, ``BUY``, ``SELL`` or ``NONE`` on
#: ``/sapi/v1/equity/market/exchangeInfo``.
TRADABILITY_KEY = "tradability"

#: The ``TRADABILITY_KEY`` value permitting each side.
TRADABILITY_BUY = frozenset({"BUY_SELL", "BUY"})
TRADABILITY_SELL = frozenset({"BUY_SELL", "SELL"})

#: The keys a tokenised equity row names fractional support under, one for the
#: regular session and one for extended hours.
FRACTIONABLE_KEY = "fractionable"
FRACTIONABLE_EXTENDED_KEY = "fractionableEh"

#: The keys a tokenised equity row names its sessions beyond the regular one
#: under. A row setting neither trades inside the regular session alone.
EXTENDED_SESSION_KEY = "extendedSession"
OVERNIGHT_SESSION_KEY = "overnightSupported"

#: The ccxt market field set True on a contract settled in its own base asset.
#: Binance publishes that contract's size in the quote currency, so no base-unit
#: contract size is read off such a record.
INVERSE_MARKET_KEY = "inverse"

#: The venue's own label for what a futures contract is written on.
FUTURES_ASSET_TYPE_KEY = "futures_asset_type"

#: The venue's own label list for what a futures contract is written on, held
#: beside the singular ``FUTURES_ASSET_TYPE_KEY``.
FUTURES_ASSET_TYPES_KEY = "futures_asset_types"

#: The ``futures_asset_type`` values naming a commodity underlying. Measured on
#: Coinbase's own product list: 12 metals, 5 energy and 4 commodities.
COMMODITY_FUTURES_ASSET_TYPES: frozenset = frozenset(
    {
        "FUTURES_ASSET_TYPE_COMMODITIES",
        "FUTURES_ASSET_TYPE_ENERGY",
        "FUTURES_ASSET_TYPE_METALS",
    }
)

#: The ``futures_asset_type`` values naming an index underlying.
INDEX_FUTURES_ASSET_TYPES: frozenset = frozenset({"FUTURES_ASSET_TYPE_INDICES"})

#: The ``futures_asset_type`` values naming an equity underlying.
EQUITY_FUTURES_ASSET_TYPES: frozenset = frozenset({"FUTURES_ASSET_TYPE_STOCKS"})

#: The ccxt market type an equity product parses as, off its own
#: ``product_type``.
EQUITY_MARKET_TYPE = "equity"

#: The ccxt market types a contract product parses as, a dated contract and a
#: perpetual.
CONTRACT_MARKET_TYPES: frozenset = frozenset({"future", "swap"})

#: The ccxt market type an option contract parses as, beside the ``option``
#: flag the same record sets.
OPTION_MARKET_TYPE = "option"

#: The ccxt market field set True on every option record.
OPTION_MARKET_KEY = "option"

#: The ccxt market field set True on every contract record.
CONTRACT_MARKET_KEY = "contract"

#: The codes Coinbase's own public currency list answers for a currency, held
#: here so the classifier reads a label and calls no venue.
FIAT_CURRENCY_CODES: frozenset = frozenset("""
    AED AFN ALL AMD ANG AOA ARS ARSMEP AUD AWG AZN BAM BBD BDT
    BGN BHD BIF BMD BND BOB BRL BSD BTN BWP BYN BYR BZD CAD
    CDF CHF CLF CLP CNH CNY COP CRC CUC CUP CVE CZK DJF DKK
    DOP DZD EGP ETB EUR FJD FKP GBP GEL GGP GHS GIP GMD GNF
    GTQ GYD HKD HNL HRK HTG HUF IDR ILS IMP INR IQD IRR ISK
    JEP JMD JOD JPY KES KGS KHR KMF KRW KWD KYD KZT LAK LBP
    LKR LRD LSL LTL LVL LYD MAD MDL MGA MKD MMK MNT MOP MRO
    MRU MUR MVR MWK MXN MYR MZN NAD NGN NIO NOK NPR NZD OMR
    PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD
    SCR SDG SEK SGD SHP SKK SLL SOS SRD SSP STD SVC SYP SZL
    THB TJS TMM TMT TND TOP TRY TTD TWD TZS UAH UGX USD UYU
    UZS VEF VES VND VUV WST XAF XCD XDR XOF XPF YER ZAR ZMK
    ZMW ZWD
    """.split())

#: The codes that same list answers for a precious metal by the troy ounce.
PRECIOUS_METAL_CODES: frozenset = frozenset({"XAG", "XAU", "XPD", "XPT"})

#: The code each tokenised asset Coinbase lists redeems for. A product record
#: carries no asset-level label, so each entry names the issuer's redemption.
# OVERTAKEN, "each tokenised asset Coinbase lists": ``XAUT`` is a Gate.io spot
# listing, so this map holds a redemption no Coinbase market names.
TOKEN_UNDERLYING_CODES: dict[str, str] = {
    "AUDD": "AUD",
    "EURC": "EUR",
    "PAXG": "XAU",
    "TGBP": "GBP",
    "USD1": "USD",
    "USDC": "USD",
    "USDS": "USD",
    "USDT": "USD",
    "XAUT": "XAU",
    "XSGD": "SGD",
}

# CCXT precisionMode values — precision means a different thing under each.
CCXT_DECIMAL_PLACES: int = 2
CCXT_SIGNIFICANT_DIGITS: int = 3
CCXT_TICK_SIZE: int = 4

DEFAULT_PRECISION_DECIMALS: int = 8


def precision_to_decimals(
    value: Any,
    precision_mode: int,
    default: int = DEFAULT_PRECISION_DECIMALS,
) -> int:
    """Convert one CCXT market ``precision`` entry to a count of decimal places.

    Returns ``default`` when the value is missing, unparseable, or in
    ``SIGNIFICANT_DIGITS`` mode, where no decimal-place count exists.
    """
    if value is None:
        return default
    if precision_mode == CCXT_SIGNIFICANT_DIGITS:
        return default
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default
    if not dec.is_finite():
        return default
    if precision_mode == CCXT_DECIMAL_PLACES:
        return max(0, int(dec))
    if precision_mode != CCXT_TICK_SIZE:
        return default
    if dec <= 0:
        return default
    return max(0, -dec.normalize().as_tuple().exponent)


def precision_to_increment(value: Any, precision_mode: int) -> Optional[float]:
    """One CCXT market ``precision`` entry as the step a value moves by, None
    where the venue published none and under ``SIGNIFICANT_DIGITS``, which names
    no step."""
    if value is None:
        return None
    if precision_mode == CCXT_SIGNIFICANT_DIGITS:
        return None
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not dec.is_finite() or dec <= 0:
        return None
    if precision_mode == CCXT_TICK_SIZE:
        return float(dec)
    if precision_mode == CCXT_DECIMAL_PLACES:
        return float(Decimal(1).scaleb(-int(dec)))
    return None


def limit_to_float(value: Any) -> Optional[float]:
    """One CCXT market ``limits`` bound as a float, None where the venue
    published none."""
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def declared_order_types(exchange: Any) -> Optional[str]:
    """The order types one CCXT exchange's own ``has`` map declares, None where
    ``createMarketOrder`` or ``createLimitOrder`` is no bool."""
    from ..trading.scrumming.sizing import (
        ORDER_TYPES_LIMIT_ONLY,
        ORDER_TYPES_WITH_MARKET,
    )

    has = getattr(exchange, "has", None)
    if not isinstance(has, dict):
        return None
    if has.get("createLimitOrder") is not True:
        return None
    # Across the 104 installed classes both keys carry only True or False, so
    # any other value is a map this reader does not recognise.
    if has.get("createMarketOrder") is True:
        return ORDER_TYPES_WITH_MARKET
    if has.get("createMarketOrder") is False:
        return ORDER_TYPES_LIMIT_ONLY
    return None


def quote_step(market: Any) -> Optional[float]:
    """The step a cash amount moves by on one loaded market record.

    ``QUOTE_INCREMENT_KEY`` under ``info`` answers it, and ``precision.price``
    does not, which carries a product's own price step. None where the venue
    published no ``QUOTE_INCREMENT_KEY``.
    """
    raw = (market or {}).get("info") or {}
    if not isinstance(raw, dict):
        return None
    return limit_to_float(raw.get(QUOTE_INCREMENT_KEY))


def contract_units(market: Any) -> Optional[float]:
    """The base units one contract stands for on one loaded market record.

    ccxt's own ``CONTRACT_SIZE_FIELD`` answers first, and ``FUTURES_DETAILS_KEY``
    answers where the record came through ``parse_spot_market``, which sets no
    contract size. None for a product carrying no contract size and None for an
    ``INVERSE_MARKET_KEY`` record, whose size is a quote-currency amount.
    """
    held = market or {}
    if held.get(INVERSE_MARKET_KEY):
        return None
    parsed = limit_to_float(held.get(CONTRACT_SIZE_FIELD))
    if parsed is not None:
        return parsed
    raw = held.get("info") or {}
    if not isinstance(raw, dict):
        return None
    detail = raw.get(FUTURES_DETAILS_KEY) or {}
    if not isinstance(detail, dict):
        return None
    return limit_to_float(detail.get(CONTRACT_SIZE_KEY))


def equity_trades_outside_regular(market: Any) -> bool:
    """Whether one tokenised equity record publishes a session beyond the
    regular one, off ``EXTENDED_SESSION_KEY`` or ``OVERNIGHT_SESSION_KEY``."""
    raw = (market or {}).get("info") or {}
    if not isinstance(raw, dict):
        return False
    return (
        raw.get(EXTENDED_SESSION_KEY) is True or raw.get(OVERNIGHT_SESSION_KEY) is True
    )


def market_session(market: Any) -> Optional[str]:
    """The session name one loaded market record publishes.

    ``SESSION_US_EQUITY`` for an ``EQUITY_MARKET_TYPE`` product and for a
    ``STOCK_MARKET_KEY`` record ``equity_trades_outside_regular`` reads False
    for, and ``SESSION_CONTINUOUS`` for every other ``STOCK_MARKET_KEY`` record
    and where ``SESSION_DETAILS_KEY`` holds no window. None where the record
    carries neither key and None where ``SESSION_DETAILS_KEY`` holds a daily
    window, which neither name states.
    """
    from ..trading.scrumming.sizing import SESSION_CONTINUOUS, SESSION_US_EQUITY

    held = market or {}
    if held.get(STOCK_MARKET_KEY):
        return (
            SESSION_CONTINUOUS
            if equity_trades_outside_regular(held)
            else SESSION_US_EQUITY
        )
    if str(held.get("type") or "").lower() == EQUITY_MARKET_TYPE:
        return SESSION_US_EQUITY
    raw = held.get("info") or {}
    if not isinstance(raw, dict) or SESSION_DETAILS_KEY not in raw:
        return None
    if isinstance(raw.get(SESSION_DETAILS_KEY), dict):
        return None
    return SESSION_CONTINUOUS


def equity_size_shapes(market: Any) -> tuple:
    """The size shapes one loaded market record permits on a buy and on a sell,
    off ``EQUITY_FLAGS_KEY`` under ``EQUITY_DETAILS_KEY``.

    Two Nones where the record carries no permission set, and two empty
    frozensets where ``EQUITY_TRADABLE_FLAG`` reads False.
    """
    from ..trading.scrumming.sizing import (
        SHAPE_CASH_AMOUNT,
        SHAPE_FRACTIONAL_UNITS,
        SHAPE_WHOLE_UNITS,
    )

    raw = (market or {}).get("info") or {}
    if not isinstance(raw, dict):
        return (None, None)
    detail = raw.get(EQUITY_DETAILS_KEY) or {}
    if not isinstance(detail, dict):
        return (None, None)
    flags = detail.get(EQUITY_FLAGS_KEY)
    if not isinstance(flags, dict):
        return (None, None)
    if flags.get(EQUITY_TRADABLE_FLAG) is False:
        return (frozenset(), frozenset())
    shapes = (SHAPE_WHOLE_UNITS, SHAPE_FRACTIONAL_UNITS, SHAPE_CASH_AMOUNT)
    # Each flag carries only a bool, so any other value is a record this reader
    # does not recognise and names no shape.
    return tuple(
        frozenset(
            shape for flag, shape in zip(side_flags, shapes) if flags.get(flag) is True
        )
        for side_flags in (EQUITY_BUY_FLAGS, EQUITY_SELL_FLAGS)
    )


def stock_size_shapes(market: Any) -> tuple:
    """The size shapes one tokenised equity record permits on a buy and on a
    sell, off ``TRADABILITY_KEY``, ``FRACTIONABLE_KEY`` and
    ``FRACTIONABLE_EXTENDED_KEY``.

    Two Nones for a record carrying no ``TRADABILITY_KEY``, and an empty
    frozenset on a side ``TRADABILITY_KEY`` does not name.
    """
    from ..trading.scrumming.sizing import (
        SHAPE_CASH_AMOUNT,
        SHAPE_FRACTIONAL_UNITS,
        SHAPE_WHOLE_UNITS,
    )

    raw = (market or {}).get("info") or {}
    if not isinstance(raw, dict):
        return (None, None)
    tradability = str(raw.get(TRADABILITY_KEY) or "").strip().upper()
    if not tradability:
        return (None, None)
    counted = {SHAPE_WHOLE_UNITS}
    if raw.get(FRACTIONABLE_KEY) is True or raw.get(FRACTIONABLE_EXTENDED_KEY) is True:
        counted.add(SHAPE_FRACTIONAL_UNITS)
    # A market buy names a notional and a market sell names a quantity, so the
    # cash amount is a buy shape alone.
    buy = frozenset(counted | {SHAPE_CASH_AMOUNT})
    sell = frozenset(counted)
    return (
        buy if tradability in TRADABILITY_BUY else frozenset(),
        sell if tradability in TRADABILITY_SELL else frozenset(),
    )


def quote_contract_size_shapes(market: Any) -> tuple:
    """``SHAPE_CASH_AMOUNT`` on both sides of an ``INVERSE_MARKET_KEY`` record,
    whose size field counts fixed quote-currency amounts.

    Two Nones for every other record.
    """
    from ..trading.scrumming.sizing import SHAPE_CASH_AMOUNT

    if not (market or {}).get(INVERSE_MARKET_KEY):
        return (None, None)
    cash = frozenset({SHAPE_CASH_AMOUNT})
    return (cash, cash)


def size_shapes_published(market: Any) -> tuple:
    """The size shapes one loaded market record publishes per side, reading
    ``equity_size_shapes``, then ``stock_size_shapes``, then
    ``quote_contract_size_shapes``.

    Two Nones where no reader answers, which ``permits_size_shapes`` tells from
    a set naming no shape.
    """
    for reader in (
        equity_size_shapes,
        stock_size_shapes,
        quote_contract_size_shapes,
    ):
        buy, sell = reader(market)
        if buy is not None or sell is not None:
            return (buy, sell)
    return (None, None)


# OVERTAKEN in market_rules's docstring below: "The ``MarketRules`` one loaded
# CCXT market record publishes."
# ``order_types`` comes from the exchange's own ``has`` map through
# ``declared_order_types``; no market record carries it.
def market_rules(
    market: Any, precision_mode: int, order_types: Optional[str] = None
) -> MarketRules:
    """The ``MarketRules`` one loaded CCXT market record publishes.

    ``get_markets`` and ``market_inspector_fetcher.trading_rules`` both read a
    record through this, so one record maps to one rule set.
    """
    limits = (market or {}).get("limits") or {}
    precision = (market or {}).get("precision") or {}
    buy_shapes, sell_shapes = size_shapes_published(market)
    return MarketRules(
        order_types=order_types,
        min_amount=limit_to_float((limits.get("amount") or {}).get("min")),
        min_cost=limit_to_float((limits.get("cost") or {}).get("min")),
        amount_increment=precision_to_increment(
            precision.get("amount"), precision_mode
        ),
        # CCXT maps Coinbase's price_increment, else its quote_increment, here.
        price_increment=precision_to_increment(precision.get("price"), precision_mode),
        quote_increment=quote_step(market),
        contract_size=contract_units(market),
        session=market_session(market),
        buy_size_shapes=buy_shapes,
        sell_size_shapes=sell_shapes,
        # CCXT parses Coinbase's future_product_details.contract_expiry here; a
        # spot record and a perpetual both carry None.
        expiry_ms=limit_to_float((market or {}).get("expiry")),
    )


def futures_asset_type(market: Any) -> str:
    """The venue's own ``futures_asset_type`` label off one loaded market record.

    Empty for a record carrying no ``future_product_details``, which every spot
    and equity product is.
    """
    raw = (market or {}).get("info") or {}
    detail = raw.get(FUTURES_DETAILS_KEY) or {}
    if not isinstance(detail, dict):
        return ""
    return str(detail.get(FUTURES_ASSET_TYPE_KEY) or "").strip().upper()


def futures_asset_types(market: Any) -> frozenset:
    """Every ``futures_asset_type`` label one loaded market record carries.

    ``FUTURES_ASSET_TYPES_KEY`` is read before ``FUTURES_ASSET_TYPE_KEY``, and
    a record carrying no ``FUTURES_DETAILS_KEY`` answers an empty frozenset.
    """
    raw = (market or {}).get("info") or {}
    detail = raw.get(FUTURES_DETAILS_KEY) or {}
    if not isinstance(detail, dict):
        return frozenset()
    listed = detail.get(FUTURES_ASSET_TYPES_KEY)
    if isinstance(listed, (list, tuple, set, frozenset)):
        held = {str(name or "").strip().upper() for name in listed}
        held.discard("")
        if held:
            return frozenset(held)
    single = futures_asset_type(market)
    return frozenset({single}) if single else frozenset()


def is_contract_market(market: Any) -> bool:
    """Whether one loaded market record sets ``CONTRACT_MARKET_KEY`` or carries
    a type ``CONTRACT_MARKET_TYPES`` holds."""
    held = market or {}
    if held.get(CONTRACT_MARKET_KEY):
        return True
    return str(held.get("type") or "").lower() in CONTRACT_MARKET_TYPES


def underlying_code(code: Any) -> str:
    """The ``FIAT_CURRENCY_CODES`` or ``PRECIOUS_METAL_CODES`` code one asset
    code stands for, upper case.

    ``TOKEN_UNDERLYING_CODES`` answers for a tokenised asset, and a code
    neither holds answers an empty string.
    """
    held = str(code or "").strip().upper()
    if held in FIAT_CURRENCY_CODES or held in PRECIOUS_METAL_CODES:
        return held
    return TOKEN_UNDERLYING_CODES.get(held, "")


def is_option_market(market: Any) -> bool:
    """Whether one loaded market record sets ``OPTION_MARKET_KEY`` or carries
    ``OPTION_MARKET_TYPE``."""
    held = market or {}
    if held.get(OPTION_MARKET_KEY):
        return True
    return str(held.get("type") or "").lower() == OPTION_MARKET_TYPE


def _published_sector(published: Any, market: Any) -> Any:
    """The sector ``published`` names for one market's base code, None where
    ``published`` is None.

    ``market_asset_class`` reads None as the venue publishing no sector list
    and an empty string as that list naming no sector for this base.
    """
    if not isinstance(published, dict):
        return None
    return published.get(str((market or {}).get("base") or "").strip().upper(), "")


def market_asset_class(market: Any, published: Any = None) -> str:
    """The asset class one loaded market record belongs to, read off
    ``futures_asset_types`` first, off ``published`` second, and off ``base``
    and ``quote`` only where ``published`` is None.

    ``record_venue`` writes this beside the market's rules, and
    ``_published_asset_sectors`` supplies ``published`` as the sector the
    venue's own asset record names, empty where that record names none.
    """
    from ..trading.ata_spm import (
        CLASS_COMMODITIES,
        CLASS_CRYPTO,
        CLASS_FOREX,
        CLASS_FUTURES_PERPS,
        CLASS_INDICES,
        CLASS_OPTIONS,
        CLASS_STOCKS,
    )

    labels = futures_asset_types(market)
    if labels & COMMODITY_FUTURES_ASSET_TYPES:
        return CLASS_COMMODITIES
    if labels & INDEX_FUTURES_ASSET_TYPES:
        return CLASS_INDICES
    if labels & EQUITY_FUTURES_ASSET_TYPES:
        return CLASS_STOCKS
    if str((market or {}).get("type") or "").lower() == EQUITY_MARKET_TYPE:
        return CLASS_STOCKS
    if (market or {}).get(STOCK_MARKET_KEY):
        return CLASS_STOCKS
    if is_option_market(market):
        return CLASS_OPTIONS
    if published is None:
        base = underlying_code((market or {}).get("base"))
        if base in PRECIOUS_METAL_CODES:
            return CLASS_COMMODITIES
        if base and underlying_code((market or {}).get("quote")):
            return CLASS_FOREX
    elif str(published or ""):
        return str(published)
    if is_contract_market(market):
        return CLASS_FUTURES_PERPS
    return CLASS_CRYPTO


def asset_info(
    symbol: Any,
    market: Any,
    precision_mode: int,
    order_types: Optional[str] = None,
) -> AssetInfo:
    """One ``AssetInfo`` from a loaded CCXT market record.

    ``get_markets`` builds every market it answers through this, so a spot
    pair, a futures contract and an equity product carry one record shape.
    """
    held = market or {}
    return AssetInfo(
        symbol=str(symbol),
        base=held.get("base", ""),
        quote=held.get("quote", ""),
        rules=market_rules(held, precision_mode, order_types),
        maker_fee=float(held.get("maker", 0.001) or 0.001),
        taker_fee=float(held.get("taker", 0.001) or 0.001),
        active=held.get("active", True),
    )


def record_price(market: Any) -> Optional[float]:
    """The last price the venue's own product record carries under ``info``,
    None where the record carries none; no venue is asked."""
    raw = (market or {}).get("info") or {}
    parsed = limit_to_float(raw.get("price"))
    if parsed is None or parsed <= 0.0:
        return None
    return parsed


def ohlcv_data_usage() -> str:
    """The Data usage line a candle fetch writes, naming every voter
    ``DEFAULT_WEIGHTS`` declares."""
    voters = ", ".join(DEFAULT_WEIGHTS)
    return f"Fed into {len(DEFAULT_WEIGHTS)}-indicator TA engine ({voters}) for voting"


_LOGO_CDN = "https://assets.coingecko.com/coins/images/{id}/small/{symbol}.png"
_LOGO_FALLBACK = "https://www.cryptocompare.com/media/img/cc_icons/{symbol}.png"


# Retry decorator for transient failures
def _with_retry(max_retries: int = 3, base_delay: float = 1.0):
    """Bind :func:`src.core.retry.with_retry` to this module's logger."""
    return with_retry(max_retries=max_retries, base_delay=base_delay, log=logger)


class CCXTConnector(ExchangeInterface):
    """Exchange connector for live trading on ``ccxt.async_support``.

    Usage::

        conn = CCXTConnector("coinbase")
        await conn.connect(api_key="...", api_secret="...")
        ticker = await conn.get_ticker("BTC/USD")
        await conn.disconnect()
    """

    def __init__(self, exchange_id: str) -> None:
        if exchange_id not in SUPPORTED_EXCHANGES:
            raise ValueError(
                f"Unsupported exchange '{exchange_id}'. "
                f"Supported: {list(SUPPORTED_EXCHANGES.keys())}"
            )
        self._exchange_id = exchange_id
        self._ccxt_id = SUPPORTED_EXCHANGES[exchange_id]
        # Set only when a backend is attached; live leaves it None.
        self._injected_ex: Any = None
        self._ccxt: Any = None  # ccxt.async_support exchange instance
        self._ccxt_sync: Any = None  # ccxt (sync) exchange instance
        self._connected = False
        self._markets_cache: list[AssetInfo] | None = None
        self._spot_positions_cache: tuple[float, dict] | None = None
        self._last_request_time: float = 0.0
        self._min_request_interval: float = 0.1

        # fetch_ticker serves no volume on coinbase; get_all_tickers fills this.
        self._quote_volumes: dict[str, float] = {}

        self._scan_symbols: set[str] = set()
        self._history_analyses: dict = {}
        self._on_history_ready: Optional[HistoryCallback] = None

        # One worker serialises every sync CCXT call on this connector.
        self._sync_executor: Optional[ThreadPoolExecutor] = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"ccxt-{exchange_id}",
        )
        # In-flight plus queued calls; touched only on the asyncio loop thread.
        self._sync_queue_depth: int = 0
        # The one task await_bulk_read_slot admitted, until its call finishes.
        self._bulk_read_admitted: Optional[asyncio.Task] = None
        # Set once this connector has recorded the venue as validated, so a
        # steady stream of balance fetches reads the store no further.
        self._venue_answer_noted: bool = False
        # disconnect() may run on a different thread than _call_sync.
        self._sync_executor_lock = threading.Lock()
        # Serialises history scans; add_scan_symbol spawns one thread per symbol.
        self._history_scan_lock = threading.Lock()

    # -- Properties -----------------------------------------------------
    @property
    def exchange_id(self) -> str:
        return self._exchange_id

    @property
    def display_name(self) -> str:
        return self._exchange_id.capitalize()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # -- Connection lifecycle -------------------------------------------
    async def connect(
        self, api_key: str, api_secret: str, passphrase: str = ""
    ) -> None:
        """Run ``sync_connect`` on the single-worker executor, off the caller's thread.

        ``sync_connect`` blocks for up to about 111 s: a 15 s pre-flight plus
        three 30 s ``load_markets`` attempts spaced 2 s and 4 s apart. It does
        not use :meth:`_call_sync`, whose 25 s budget is shorter than a
        legitimate connect, and does not count against ``_sync_queue_depth``.
        """
        # Under the lock so disconnect() cannot close the executor before the
        # submit.
        with self._sync_executor_lock:
            executor = self._sync_executor
            if executor is None:
                raise RuntimeError(
                    f"CCXTConnector({self._exchange_id}) has been "
                    f"disconnected; cannot open a new connection."
                )

        import functools

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            executor,
            functools.partial(self.sync_connect, api_key, api_secret, passphrase),
        )

    def sync_connect(
        self,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None,
    ) -> None:
        """Connect with synchronous CCXT, which uses requests rather than aiohttp."""
        if self._injected_ex is not None:
            # A backend serves this connector: no session to open, no credentials.
            self._connected = True
            return
        try:
            import ccxt as ccxt_sync
        except ImportError:
            raise ImportError(
                "The 'ccxt' package is required. Install via: "
                "pip install ccxt --break-system-packages"
            )

        exchange_class = resolve_ccxt_class(ccxt_sync, self._ccxt_id)
        if exchange_class is None:
            raise ValueError(f"CCXT does not have class '{self._ccxt_id}'")

        config = {
            "apiKey": api_key,
            "secret": api_secret,
            "enableRateLimit": True,
            "timeout": CCXT_REQUEST_TIMEOUT_MS,
            "options": {"defaultType": "spot"},
        }

        _log = get_api_log()

        # --- Coinbase CDP key PEM newline fix ---
        # A secret stored before the dialog converted on the way in still
        # arrives escaped, so this repeats the conversion and changes nothing
        # when the stored secret already carries real newlines.
        if self._exchange_id == "coinbase" and api_secret:
            api_secret = unescape_pem_newlines(api_secret)
            config["secret"] = api_secret

            is_cdp = api_key.startswith("organizations/")
            # Log the last four characters only, never the key prefix.
            _key_tail = api_key[-4:] if len(api_key) >= 4 else "****"
            _log.record(
                exchange=self._exchange_id,
                action="KEY_TYPE_DETECTED",
                reason=f"{'CDP (JWT/ECDSA)' if is_cdp else 'Legacy (HMAC)'} API key format",
                result=f"Key ...{_key_tail} (prefix redacted per TD-013)",
                level="info",
                data_usage="CDP keys use JWT auth with EC signing. Legacy keys use HMAC-SHA256.",
            )

        # --- Apply exchange-specific options ---
        exch_opts = EXCHANGE_OPTIONS.get(self._exchange_id)
        if exch_opts:
            config["options"].update(exch_opts)

        # --- Passphrase ---
        if self._exchange_id in PASSPHRASE_EXCHANGES:
            if not passphrase:
                raise ValueError(
                    f"{self.display_name} requires an API passphrase. "
                    f"This is set when you create the API key on the exchange."
                )
            config["password"] = passphrase

        # --- US restriction warning ---
        if self._exchange_id in US_RESTRICTED_EXCHANGES:
            _log.record(
                exchange=self._exchange_id,
                action="US_RESTRICTION_WARNING",
                reason=f"{self.display_name}: {restriction_note(self._exchange_id)}",
                result="Proceeding with connection attempt. A 403 or Forbidden from "
                "the venue confirms it. This reading was taken on "
                f"{VENUE_MEASUREMENT_DATE}, quotes no page the venue publishes, and "
                "the venue's own answer decides.",
                level="warning",
                data_usage="Check exchange terms of service for your region.",
            )

        # --- Pre-flight connectivity check ---
        preflight_url = PREFLIGHT_URLS.get(self._exchange_id)
        if preflight_url:
            _log.record(
                exchange=self._exchange_id,
                action="PREFLIGHT_CHECK",
                reason=f"Testing connectivity to {preflight_url}",
                result="Checking...",
                level="info",
                data_usage="Direct HTTP request to verify endpoint is reachable",
            )
            import ssl as _ssl

            try:
                ssl_ctx = _ssl.create_default_context()
                try:
                    import certifi

                    ssl_ctx = _ssl.create_default_context(cafile=certifi.where())
                except ImportError:
                    pass
                req = SafeRequest(preflight_url)
                req.add_header("User-Agent", "Acervator/1.8")
                req.add_header("Accept", "application/json")
                start = time.monotonic()
                with safe_urlopen(req, timeout=15, context=ssl_ctx) as resp:
                    elapsed = (time.monotonic() - start) * 1000
                    _log.record(
                        exchange=self._exchange_id,
                        action="PREFLIGHT_OK",
                        reason=f"HTTP {resp.status} from {preflight_url}",
                        result=f"Endpoint reachable ({elapsed:.0f}ms)",
                        elapsed_ms=elapsed,
                        level="success",
                        data_usage="Pre-flight passed. Proceeding with CCXT.",
                    )
            except Exception as pf_exc:
                _log.record(
                    exchange=self._exchange_id,
                    action="PREFLIGHT_FAILED",
                    reason=f"Cannot reach {preflight_url}",
                    result=f"{type(pf_exc).__name__}: {pf_exc}",
                    level="error",
                    data_usage="Network/SSL issue. Check firewall and internet connection.",
                )
                # Classified here because this exit never reaches the
                # load-markets path below.
                self._note_venue_refusal(pf_exc)
                raise ConnectionError(
                    f"Cannot reach {self._exchange_id} API. "
                    f"Pre-flight check failed: {type(pf_exc).__name__}: {pf_exc} | "
                    f"URL: {preflight_url}"
                )

        # --- Create SYNC CCXT exchange and load markets ---
        _log.record(
            exchange=self._exchange_id,
            action="CONNECTING",
            reason="Creating synchronous CCXT connection",
            endpoint="load_markets",
            params={"exchange": self._exchange_id},
            result="Connecting...",
            level="info",
            data_usage="Sync CCXT (requests library, not aiohttp)",
        )

        sync_exchange = exchange_class(config)

        # Disable fetchCurrencies for exchanges with deprecated endpoints
        if self._exchange_id in DISABLE_FETCH_CURRENCIES:
            sync_exchange.has["fetchCurrencies"] = False

        attempt_count = 0

        def _load_markets_once() -> None:
            nonlocal attempt_count
            attempt_count += 1
            start = time.monotonic()
            sync_exchange.load_markets()
            elapsed = (time.monotonic() - start) * 1000
            market_count = len(sync_exchange.markets) if sync_exchange.markets else 0
            self._connected = True
            self._ccxt_sync = sync_exchange

            # Prepare async exchange for trading loop (shares loaded markets)
            try:
                import ccxt.async_support as ccxt_async

                async_class = resolve_ccxt_class(ccxt_async, self._ccxt_id)
                if async_class is None:
                    raise RuntimeError(f"CCXT async has no class for '{self._ccxt_id}'")
                self._ccxt = async_class(config)
                if self._exchange_id in DISABLE_FETCH_CURRENCIES:
                    self._ccxt.has["fetchCurrencies"] = False
                self._ccxt.markets = sync_exchange.markets
                self._ccxt.markets_by_id = sync_exchange.markets_by_id
                self._ccxt.currencies = sync_exchange.currencies
                self._ccxt.symbols = sync_exchange.symbols
            except Exception:  # Fall back to the sync exchange when async fails
                self._ccxt = sync_exchange

            _log.record(
                exchange=self._exchange_id,
                action="CONNECTED",
                reason="Markets loaded successfully",
                endpoint="load_markets",
                params={"attempt": attempt_count},
                result=f"Connected to {self.display_name}. {market_count} trading pairs.",
                elapsed_ms=elapsed,
                level="success",
                data_usage="Market metadata cached for trading.",
            )
            logger.info("Connected to %s (%d markets)", self.display_name, market_count)

            # Background thread so the scan never delays startup.
            import threading

            threading.Thread(
                target=self._scan_trade_history,
                daemon=True,
                name="trade-historian",
            ).start()

        def _note_load_failure(
            exc: BaseException, attempt: int, will_retry: bool, delay: float
        ) -> None:
            del delay
            _log.record(
                exchange=self._exchange_id,
                action="CONNECT_RETRY",
                reason=f"Attempt {attempt + 1}/{CONNECT_ATTEMPTS} failed",
                endpoint="load_markets",
                params={"attempt": attempt + 1},
                result=self._format_exchange_error(exc),
                level="warning" if will_retry else "error",
                data_usage=("Retrying..." if will_retry else "All attempts exhausted"),
            )

        try:
            retry_sync(
                _load_markets_once,
                attempts=CONNECT_ATTEMPTS,
                delay_for=linear_delay(CONNECT_BACKOFF_STEP_S),
                is_retryable=retry_any,
                on_failure=_note_load_failure,
            )
        except Exception as exc:
            # Classified here because the wrap below drops the ccxt type.
            self._note_venue_refusal(exc)
            # `from None` keeps the traceback single-frame.
            raise ConnectionError(self._format_exchange_error(exc)) from None

    # ── Venue state ─────────────────────────────────────────────────────────

    def _note_venue_refusal(self, exc: BaseException) -> str:
        """Record one refusal of this connector's venue and name its class."""
        kind = note_venue_refusal(self._exchange_id, exc)
        if kind in (VENUE_LOST, VENUE_CREDENTIAL_REJECTED):
            self._venue_answer_noted = False
        return kind

    def _note_venue_answer(self) -> None:
        """Record that this connector's venue answered an authenticated call."""
        if self._venue_answer_noted:
            return
        note_venue_answered(self._exchange_id)
        self._venue_answer_noted = True

    # ── Sync CCXT serialization ─────────────────────────────────────────────

    async def await_bulk_read_slot(
        self, budget_sec: float = BULK_READ_WAIT_BUDGET_SEC
    ) -> float:
        """Yield until the call queue has room for a bulk read, then answer seconds waited.

        A bulk read awaits this before each of its venue calls, so a 39-symbol
        History refresh cannot hold the connector's single worker against the
        balance, ticker, portfolio and OHLCV calls that share
        ``SYNC_QUEUE_CAP``. One bulk read holds admission at a time and the
        depth it waits on is ``BULK_READ_ADMIT_DEPTH``, so 39 bots walking at
        once add one call to the queue rather than 39. Past ``budget_sec`` it
        submits regardless and takes the queue cap's own answer.
        """
        asking = asyncio.current_task()
        start = time.monotonic()
        while True:
            held = self._bulk_read_admitted
            free = held is None or held.done() or held is asking
            if free and self._sync_queue_depth <= BULK_READ_ADMIT_DEPTH:
                break
            if time.monotonic() - start >= budget_sec:
                break
            await asyncio.sleep(BULK_READ_WAIT_SLICE_SEC)
        if asking is not None:
            self._bulk_read_admitted = asking
        return time.monotonic() - start

    def _release_bulk_read_slot(self) -> None:
        """Clear ``_bulk_read_admitted`` when this task is the one holding it."""
        held = self._bulk_read_admitted
        if held is not None and held is asyncio.current_task():
            self._bulk_read_admitted = None

    async def _call_sync(self, fn, *args, **kwargs):
        """Run one sync CCXT call on the single worker, with a queue cap and a timeout.

        Raises:
            CCXTQueueFullError: queue depth is at ``SYNC_QUEUE_CAP``.
            TimeoutError: the call exceeded ``SYNC_CALL_TIMEOUT_SEC``.
            asyncio.CancelledError: the awaiter was cancelled; the worker runs on.
            Any CCXT exception: propagated unchanged.
        """
        # Read and written only on the asyncio loop thread, so no lock.
        if self._sync_queue_depth >= SYNC_QUEUE_CAP:
            self._release_bulk_read_slot()
            raise CCXTQueueFullError(
                f"CCXT call queue at capacity ({self._sync_queue_depth}/"
                f"{SYNC_QUEUE_CAP}) for {self._exchange_id}; "
                f"exchange is likely rate-limited or network is degraded. "
                f"Call: {getattr(fn, '__name__', repr(fn))}"
            )

        # Under the lock so disconnect() cannot close the executor before the
        # submit.
        with self._sync_executor_lock:
            executor = self._sync_executor
            if executor is None:
                self._release_bulk_read_slot()
                raise RuntimeError(
                    f"CCXTConnector({self._exchange_id}) has been disconnected; "
                    f"cannot submit new sync calls."
                )

        self._sync_queue_depth += 1
        try:
            loop = asyncio.get_event_loop()
            # Submit to single-worker executor → serialized by construction
            if kwargs:
                # run_in_executor doesn't accept kwargs — wrap in functools.partial
                import functools

                fut = loop.run_in_executor(
                    executor, functools.partial(fn, *args, **kwargs)
                )
            else:
                fut = loop.run_in_executor(executor, fn, *args)

            try:
                result = await asyncio.wait_for(fut, timeout=SYNC_CALL_TIMEOUT_SEC)
                return result
            except asyncio.TimeoutError as timed_out:
                # The worker thread runs on until CCXT returns; log the leak.
                logger.warning(
                    "sync CCXT call exceeded the outer wait (%ss) for %s on %s; "
                    "ccxt's own %sms timeout did not return, so the worker "
                    "thread is leaked",
                    SYNC_CALL_TIMEOUT_SEC,
                    getattr(fn, "__name__", repr(fn)),
                    self._exchange_id,
                    CCXT_REQUEST_TIMEOUT_MS,
                )
                self._note_venue_refusal(timed_out)
                raise
            except asyncio.CancelledError:
                # The worker keeps running until CCXT returns.
                raise
            except Exception as refused:
                self._note_venue_refusal(refused)
                raise
        finally:
            self._sync_queue_depth = max(0, self._sync_queue_depth - 1)
            self._release_bulk_read_slot()

    # ── Trade history scanning ───────────────────────────────────────────────

    def set_history_callback(self, callback: HistoryCallback) -> None:
        """Register a callback the historian thread calls as ``(symbol, analysis)``."""
        self._on_history_ready = callback

    def _scan_trade_history(self, symbols=None) -> None:
        """Scan trade history for *symbols*, or for the registered set when None."""
        if not self._ccxt_sync:
            return

        symbols = (
            [str(x) for x in symbols]
            if symbols is not None
            else (list(self._scan_symbols) if self._scan_symbols else [])
        )
        if not symbols:
            logger.info("TradeHistorian: no symbols registered — skipping auto-scan")
            return

        logger.info(
            "TradeHistorian: starting post-connect history scan "
            "for %d symbol(s): %s",
            len(symbols),
            symbols,
        )
        # The lock queues concurrent scans; pace_s is this connector's own interval.
        with self._history_scan_lock:
            try:
                # Timed inside the lock so the duration excludes waiting for a turn.
                _dur_t0 = time.monotonic()
                results = scan_on_connect(
                    exchange=self._ccxt_sync,
                    symbols=symbols,
                    on_result=self._on_history_result,
                    pace_s=float(getattr(self, "_min_request_interval", 0.1) or 0.0),
                )
                _dur_elapsed = time.monotonic() - _dur_t0
                self._history_analyses.update(results)
                logger.info(
                    "TradeHistorian: scan complete — %d symbol(s) analysed",
                    len(results),
                )
                try:
                    from src.core.signal_contract import emit as _hs_emit

                    _hs_emit(
                        "history.05.001.postcondition.scan_complete",
                        actual=len(results),
                        expected=len(symbols),
                        duration=_dur_elapsed,
                        context={"symbols": len(symbols)},
                    )
                except Exception:  # noqa: BLE001,S110
                    pass
            except Exception as e:
                logger.error("TradeHistorian: scan failed: %s", e)

    def _on_history_result(
        self,
        symbol: str,
        analysis: HistoryAnalysis,
    ) -> None:
        """Called by scan_on_connect for each symbol as it completes."""
        self._history_analyses[symbol] = analysis
        if self._on_history_ready:
            try:
                self._on_history_ready(symbol, analysis)
            except Exception as e:
                logger.warning("history callback error: %s", e)

    def add_scan_symbol(self, symbol: str):
        """Register *symbol* for history scans, scanning it now if already connected."""
        if symbol in self._scan_symbols:
            return  # idempotent — already registered
        self._scan_symbols.add(symbol)
        # Scan now rather than waiting for the next connect.
        if self._ccxt_sync is not None:
            try:
                import threading

                threading.Thread(
                    target=self.refresh_history,
                    kwargs={"symbol": symbol},
                    daemon=True,
                    name=f"trade-historian-late-{symbol}",
                ).start()
                logger.info(
                    "TradeHistorian: late registration for %s — "
                    "spawning targeted scan in background",
                    symbol,
                )
            except Exception as exc:
                logger.warning(
                    "TradeHistorian: late-scan spawn failed for %s: %s", symbol, exc
                )

    def remove_scan_symbol(self, symbol: str):
        self._scan_symbols.discard(symbol)

    def get_history(self, symbol: str) -> HistoryAnalysis | None:
        """Return the most recent history analysis for a symbol."""
        return self._history_analyses.get(symbol)

    def refresh_history(self, symbol: str | None = None):
        """Re-scan *symbol*, or every registered symbol when None."""
        if symbol:
            self._scan_trade_history(symbols=[symbol])
        else:
            self._scan_trade_history()

    @staticmethod
    def _format_exchange_error(exc: Exception) -> str:
        """Extract every available detail from a CCXT exception."""
        parts = [f"{type(exc).__name__}: {exc}"]

        # CCXT puts HTTP details under different attribute names per version.
        http_code = None
        for attr in ("http_status", "http_code", "status_code", "code"):
            val = getattr(exc, attr, None)
            if val is not None:
                http_code = val
                parts.append(f"HTTP Status: {val}")
                break

        url = getattr(exc, "url", None)
        if url:
            parts.append(f"URL: {url}")

        method = getattr(exc, "method", None)
        if method:
            parts.append(f"Method: {method}")

        # Raw response body - the actual server reply
        body = None
        for attr in ("http_response", "body", "response_body", "message"):
            val = getattr(exc, attr, None)
            if val and isinstance(val, str) and val != str(exc):
                body = val[:500]
                break

        # Parsed JSON response
        parsed = getattr(exc, "response", None)
        if parsed and isinstance(parsed, dict):
            import json

            body = json.dumps(parsed, indent=2)[:500]

        if body:
            parts.append(f"Response Body: {body}")

        # Build diagnosis from actual data
        exc_name = type(exc).__name__
        exc_str = str(exc)
        code = http_code or ""
        code_str = str(code)

        if "ExchangeNotAvailable" in exc_name:
            if (
                code_str.startswith("5")
                or "503" in exc_str
                or "502" in exc_str
                or "500" in exc_str
            ):
                parts.append(
                    f"DIAGNOSIS: Server error (HTTP {code or '5xx'}). Exchange is likely under maintenance."
                )
            elif code_str == "403" or "403" in exc_str:
                parts.append(
                    "DIAGNOSIS: HTTP 403 Forbidden. Your API key may lack permissions, or your IP may be blocked by the exchange."
                )
            elif code_str == "429" or "429" in exc_str:
                parts.append(
                    "DIAGNOSIS: HTTP 429 Rate Limited. Too many requests. Wait 60 seconds."
                )
            elif code_str == "401" or "401" in exc_str:
                parts.append(
                    "DIAGNOSIS: HTTP 401 Unauthorized. API credentials are invalid or expired."
                )
            elif "cloudflare" in exc_str.lower() or "ddos" in exc_str.lower():
                parts.append(
                    "DIAGNOSIS: DDoS protection triggered. Wait 30 seconds and retry."
                )
            elif not code:
                parts.append(
                    "DIAGNOSIS: No HTTP status received. Likely causes: "
                    "DNS resolution failure, network timeout, firewall blocking outbound HTTPS, "
                    "or the exchange domain is unreachable from your network. "
                    "Try: 1) Open https://api.coinbase.com in a browser to verify connectivity. "
                    "2) Check if a VPN or corporate firewall is active. "
                    "3) Try again in 60 seconds (transient outage)."
                )
            else:
                parts.append(
                    f"DIAGNOSIS: HTTP {code}. Unexpected status. Check Response Body above for details."
                )
        elif "AuthenticationError" in exc_name:
            parts.append(
                "DIAGNOSIS: API credentials rejected. Verify key, secret, and passphrase. Ensure trading permissions are enabled on the exchange website."
            )
        elif "RateLimitExceeded" in exc_name or "429" in exc_str:
            parts.append("DIAGNOSIS: Rate limited. Application will retry after delay.")
        elif "NetworkError" in exc_name or "Timeout" in exc_name:
            parts.append(
                "DIAGNOSIS: Network connectivity issue. Check internet connection and firewall."
            )
        elif "PermissionDenied" in exc_name or "403" in exc_str:
            parts.append("DIAGNOSIS: API key lacks required permissions.")
        elif "BadRequest" in exc_name or "400" in exc_str:
            parts.append(
                "DIAGNOSIS: Malformed request. May indicate CCXT version mismatch. Try: pip install ccxt --upgrade"
            )

        return " | ".join(parts)

    async def disconnect(self) -> None:
        if self._ccxt:
            await self._ccxt.close()
            self._ccxt = None
        self._connected = False
        self._markets_cache = None

        # Shut the executor down under the lock; in-flight calls run to completion.
        with self._sync_executor_lock:
            executor = self._sync_executor
            self._sync_executor = None
        if executor is not None:
            try:
                executor.shutdown(wait=True)
            except Exception as exc:
                logger.warning("sync executor shutdown failed: %s", exc)
        logger.info("Disconnected from %s", self.display_name)

    def release(self) -> int:
        """Clear the scan set, drop both ccxt handles and shut the sync executor.

        Returns the number of scan symbols cleared; `_scan_trade_history` reads
        `_ccxt_sync`, so a scan already running returns at its next guard.
        """
        cleared = len(self._scan_symbols)
        self._scan_symbols.clear()
        self._injected_ex = None
        self._ccxt_sync = None
        self._ccxt = None
        self._connected = False
        self._markets_cache = None
        with self._sync_executor_lock:
            executor = self._sync_executor
            self._sync_executor = None
        if executor is not None:
            try:
                executor.shutdown(wait=False)
            except Exception as exc:
                logger.warning("sync executor shutdown failed: %s", exc)
        logger.info(
            "Released %s connector — %d scan symbol(s) dropped",
            self.display_name,
            cleared,
        )
        return cleared

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise RuntimeError(f"Not connected to {self.display_name}")
        # Through `_ex`, so an attached backend is not rejected.
        if self._ex is None:
            raise RuntimeError(f"No exchange instance for {self.display_name}")

    @property
    def _ex(self):
        """Return the attached backend, else the sync CCXT instance, else the async."""
        injected = getattr(self, "_injected_ex", None)
        if injected is not None:
            return injected
        return getattr(self, "_ccxt_sync", None) or self._ccxt

    def attach_backend(self, backend: Any) -> None:
        """Serve every ccxt call from *backend* and mark the connector connected.

        *backend* must provide the fifteen ccxt members reached through ``_ex``:
        fetch_ohlcv, fetch_ticker, fetch_tickers, fetch_balance, create_order,
        cancel_order, fetch_order, fetch_open_orders, fetch_my_trades,
        fetch_order_book, markets, market, precisionMode, amount_to_precision
        and price_to_precision.
        """
        self._injected_ex = backend
        self._connected = True
        # A backend has no venue to throttle, so no interval is enforced.
        self._min_request_interval = 0.0

    # -- Rate limiting --------------------------------------------------
    async def _rate_limit(self) -> None:
        """Enforce minimum interval between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.monotonic()

    # -- Market data (all methods use sync CCXT via self._call_sync) ----
    def _quote_volume_for(self, symbol: str, raw: dict) -> float:
        """Return ``symbol``'s 24h quote volume from ``raw``, else the recorded one.

        Coinbase's ``fetch_ticker`` serves neither ``quoteVolume`` nor
        ``baseVolume``, so ``get_ticker`` falls back to what the last
        ``get_all_tickers`` recorded for that symbol, and 0.0 before the first.
        """
        served = row_quote_volume_24h(raw)
        if served > 0:
            return served
        return float(self._quote_volumes.get(symbol, 0.0))

    @_with_retry()
    async def get_ticker(self, symbol: str) -> Ticker:
        self._ensure_connected()
        await self._rate_limit()
        _log = get_api_log()
        start = time.monotonic()
        raw = await self._call_sync(self._ex.fetch_ticker, symbol)
        elapsed = (time.monotonic() - start) * 1000
        ticker = Ticker(
            symbol=symbol,
            bid=float(raw.get("bid", 0) or 0),
            ask=float(raw.get("ask", 0) or 0),
            last=float(raw.get("last", 0) or 0),
            volume_24h=self._quote_volume_for(symbol, raw),
            timestamp=float(raw.get("timestamp", 0) or 0) / 1000,
        )
        _log.record(
            exchange=self._exchange_id,
            action="FETCH_TICKER",
            reason=f"Get current price for {symbol}",
            endpoint="fetch_ticker",
            params={"symbol": symbol},
            result=f"last={fmt_price_coerced(ticker.last)} bid={fmt_price_coerced(ticker.bid)} ask={fmt_price_coerced(ticker.ask)} vol24h={ticker.volume_24h:.0f}",
            elapsed_ms=elapsed,
            level="success",
            data_usage="Used by bots for delta calculation, grid level checks, and P/L computation",
        )
        return ticker

    async def get_all_tickers(self) -> dict:
        """Return the raw CCXT tickers dict for every symbol in one call.

        Not normalised into :class:`Ticker`, which does not carry the 24h
        percentage change callers need. Each row's quote volume is recorded for
        ``get_ticker``, whose own call serves none on coinbase.
        """
        self._ensure_connected()
        await self._rate_limit()
        rows = await self._call_sync(self._ex.fetch_tickers)
        for symbol, row in (rows or {}).items():
            volume = row_quote_volume_24h(row)
            if volume > 0:
                self._quote_volumes[symbol] = volume
        return rows

    @_with_retry()
    async def get_orderbook(self, symbol: str, limit: int = 20) -> OrderBook:
        self._ensure_connected()
        await self._rate_limit()
        raw = await self._call_sync(self._ex.fetch_order_book, symbol, limit)
        return OrderBook(
            symbol=symbol,
            bids=[(float(p), float(a)) for p, a in raw.get("bids", [])],
            asks=[(float(p), float(a)) for p, a in raw.get("asks", [])],
            timestamp=float(raw.get("timestamp", 0) or 0) / 1000,
        )

    @_with_retry()
    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        limit: int = 100,
        since: Optional[int] = None,
    ) -> list[list[float]]:
        """Fetch ``limit`` OHLCV candles ending at the newest bar, or starting
        at ``since`` epoch milliseconds."""
        self._ensure_connected()
        await self._rate_limit()
        _log = get_api_log()
        start = time.monotonic()
        data = await self._call_sync(
            self._ex.fetch_ohlcv,
            symbol,
            timeframe,
            None if since is None else int(since),
            int(limit),
        )
        elapsed = (time.monotonic() - start) * 1000
        _log.record(
            exchange=self._exchange_id,
            action="FETCH_OHLCV",
            reason=f"Get {limit} candles ({timeframe}) for {symbol} - needed for TA indicator computation",
            endpoint="fetch_ohlcv",
            params={"symbol": symbol, "timeframe": timeframe, "limit": limit},
            result=(
                f"{len(data)} candles received, latest close={fmt_price_coerced(data[-1][4])}"
                if data
                else "No data"
            ),
            elapsed_ms=elapsed,
            level="success",
            data_usage=ohlcv_data_usage(),
        )
        return data

    # -- Account --------------------------------------------------------
    @_with_retry()
    async def get_balances(self) -> dict[str, Balance]:
        self._ensure_connected()
        await self._rate_limit()
        _log = get_api_log()
        start = time.monotonic()
        raw = await self._call_sync(self._ex.fetch_balance)
        self._note_venue_answer()
        elapsed = (time.monotonic() - start) * 1000
        result: dict[str, Balance] = {}
        for currency, info in raw.get("total", {}).items():
            total = float(info or 0)
            if total > 0:
                free = float(raw.get("free", {}).get(currency, 0) or 0)
                used = float(raw.get("used", {}).get(currency, 0) or 0)
                result[currency] = Balance(
                    currency=currency,
                    free=free,
                    used=used,
                    total=total,
                )
        bal_summary = ", ".join(
            f"{c}: {b.total:.6g}" for c, b in list(result.items())[:8]
        )
        _log.record(
            exchange=self._exchange_id,
            action="FETCH_BALANCES",
            reason="Retrieve account balances to verify funds and calculate position values",
            endpoint="fetch_balance",
            params={},
            result=f"{len(result)} assets with balance. {bal_summary}",
            elapsed_ms=elapsed,
            level="success",
            data_usage="Compared against bot target balances to determine available resources and P/L",
        )
        return result

    @_with_retry()
    async def get_balance(self, currency: str) -> Balance:
        # Tell "exchange said zero" apart from "exchange omitted this currency".
        balances = await self.get_balances()
        if currency in balances:
            return balances[currency]

        # get_balances drops totals <= 0, so re-read raw to tell the two apart.
        self._ensure_connected()
        await self._rate_limit()
        raw = await self._call_sync(self._ex.fetch_balance)
        total_map = raw.get("total", {}) or {}
        if currency in total_map:
            # The exchange reported it as zero.
            return Balance(
                currency=currency, free=0.0, used=0.0, total=0.0, absent=False
            )

        # The exchange did not report this currency at all.
        return Balance(currency=currency, free=0.0, used=0.0, total=0.0, absent=True)

    # -- Orders ---------------------------------------------------------

    # Submission is never retried: create_order is not idempotent without a
    # client_order_id.
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        amount: float,
        price: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Order:
        self._ensure_connected()
        await self._rate_limit()

        # Per-(exchange, symbol) breaker short-circuits while a venue is failing.
        from .circuit_breaker import get_breaker_registry, CircuitBreakerOpenError

        _breaker_key = f"{self._exchange_id}:{symbol}"
        _breaker = get_breaker_registry().get(_breaker_key)
        if not _breaker.is_call_allowed():
            _breaker.record_short_circuit()
            raise CircuitBreakerOpenError(_breaker_key, _breaker.cooldown_remaining())
        _log = get_api_log()

        self._ex.market(symbol)
        amount = self._ex.amount_to_precision(symbol, amount)

        # Coinbase needs a price on a spot market BUY to compute total cost.
        exec_price = price
        if (
            order_type == OrderType.MARKET
            and side == OrderSide.BUY
            and exec_price is None
        ):
            no_price_cause = ""
            try:
                ticker = await self._call_sync(self._ex.fetch_ticker, symbol)
                exec_price = float(ticker.get("last", 0) or ticker.get("ask", 0) or 0)
                if exec_price <= 0:
                    exec_price = None
                    no_price_cause = "fetch_ticker served no last and no ask price"
            except Exception as exc:
                exec_price = None
                no_price_cause = f"fetch_ticker raised {type(exc).__name__}: {exc}"
            # create_order raises InvalidOrder on a MARKET BUY priced None.
            if exec_price is None:
                from ccxt.base.errors import InvalidOrder

                refusal = (
                    f"{self._exchange_id} refuses a MARKET BUY on {symbol} with "
                    f"no price: {no_price_cause}"
                )
                _log.record(
                    exchange=self._exchange_id,
                    action="ORDER_REFUSED",
                    reason=refusal,
                    endpoint="create_order",
                    params={
                        "symbol": symbol,
                        "side": side.value,
                        "type": order_type.value,
                        "amount": float(amount),
                        "price": None,
                    },
                    result="Not sent. The venue prices a MARKET BUY as amount * price.",
                    level="error",
                    data_usage="No order reaches the venue and no fill is booked.",
                )
                refusal_error = InvalidOrder(refusal)
                _breaker.record_failure(refusal_error)
                raise refusal_error

        if exec_price is not None:
            exec_price = float(self._ex.price_to_precision(symbol, exec_price))

        _log.record(
            exchange=self._exchange_id,
            action="PLACE_ORDER",
            reason=f"Execute {side.value.upper()} {order_type.value} order for {symbol}",
            endpoint="create_order",
            params={
                "symbol": symbol,
                "side": side.value,
                "type": order_type.value,
                "amount": float(amount),
                "price": exec_price,
            },
            result="Sending to exchange...",
            elapsed_ms=0,
            level="info",
            data_usage="Order will be tracked for fill status; fills trigger profit folding or grid cycling",
        )

        # Coinbase Advanced Trade is protobuf-strict: send only its own field name.
        # ccxt maps clientOrderId onto Kraken's cl_ord_id; its userref takes digits only.
        extra_params: dict = {}
        if client_order_id:
            _eid = (self._exchange_id or "").lower()
            if "coinbase" in _eid:
                # Coinbase Advanced Trade
                extra_params["client_order_id"] = client_order_id
            elif "binance" in _eid or "binanceus" in _eid:
                extra_params["newClientOrderId"] = client_order_id
            else:
                # Default to ccxt canonical; CCXT translates per-exchange
                extra_params["clientOrderId"] = client_order_id

        # ccxt has no ioc_limit type: send limit with timeInForce=IOC.
        _ccxt_type = order_type.value
        if order_type == OrderType.IOC_LIMIT:
            _ccxt_type = "limit"
            extra_params["timeInForce"] = "IOC"

        start = time.monotonic()
        try:
            if extra_params:
                raw = await self._call_sync(
                    self._ex.create_order,
                    symbol,
                    _ccxt_type,
                    side.value,
                    float(amount),
                    exec_price,
                    extra_params,
                )
            else:
                raw = await self._call_sync(
                    self._ex.create_order,
                    symbol,
                    _ccxt_type,
                    side.value,
                    float(amount),
                    exec_price,
                )
        except Exception as _exc:
            _venue_said = f"{type(_exc).__name__}: {_exc}"
            _log.record(
                exchange=self._exchange_id,
                action="ORDER_REFUSED",
                reason=(
                    f"{self._exchange_id} refused {side.value.upper()} "
                    f"{order_type.value} on {symbol}: {_venue_said}"
                ),
                endpoint="create_order",
                params={
                    "symbol": symbol,
                    "side": side.value,
                    "type": order_type.value,
                    "amount": float(amount),
                    "price": exec_price,
                },
                result=f"ERROR: {_venue_said}",
                elapsed_ms=(time.monotonic() - start) * 1000,
                level="error",
                data_usage="No fill is booked. The breaker counts this failure.",
            )
            # The breaker opens after enough consecutive failures.
            _breaker.record_failure(_exc)
            raise
        elapsed = (time.monotonic() - start) * 1000
        _breaker.record_success()  # Successful round-trip → reset failure run
        order = self._parse_order(raw)

        _log.record(
            exchange=self._exchange_id,
            action="ORDER_PLACED",
            reason=f"{side.value.upper()} order accepted by exchange",
            endpoint="create_order",
            params={"order_id": order.id},
            result=f"ID={order.id} status={order.status.value} filled={order.filled}/{float(amount)}",
            elapsed_ms=elapsed,
            level="success",
            data_usage="Order ID stored for fill monitoring. Bot will check status each tick cycle.",
        )
        return order

    @_with_retry()
    async def cancel_order(self, order_id: str, symbol: str) -> Order:
        self._ensure_connected()
        await self._rate_limit()
        raw = await self._call_sync(self._ex.cancel_order, order_id, symbol)
        return self._parse_order(raw)

    @_with_retry()
    async def get_order(self, order_id: str, symbol: str) -> Order:
        self._ensure_connected()
        await self._rate_limit()
        raw = await self._call_sync(self._ex.fetch_order, order_id, symbol)
        return self._parse_order(raw)

    @_with_retry()
    async def get_open_orders(self, symbol: Optional[str] = None) -> list[Order]:
        self._ensure_connected()
        await self._rate_limit()
        raw_list = await self._call_sync(self._ex.fetch_open_orders, symbol)
        return [self._parse_order(r) for r in raw_list]

    @_with_retry()
    async def get_my_trades(
        self,
        symbol: str,
        since: Optional[float] = None,
        limit: Optional[int] = None,
        params: Optional[dict] = None,
    ) -> list:
        """Fetch executed trades; ``params`` forwards per-exchange overrides to ccxt."""
        from .base import Trade, OrderSide

        self._ensure_connected()
        await self._rate_limit()
        # ccxt's `since` is millisecond unix; convert from seconds
        _since_ms = int(since * 1000) if since else None
        _params = params if params is not None else {}
        raw_list = await self._call_sync(
            self._ex.fetch_my_trades, symbol, _since_ms, limit, _params
        )
        result: list = []
        for r in raw_list or []:
            try:
                _side_str = str(r.get("side", "buy")).lower()
                _side = OrderSide.BUY if _side_str == "buy" else OrderSide.SELL
                _ts = float(r.get("timestamp", 0) or 0) / 1000.0
                _fee_dict = r.get("fee") or {}
                _fee_amt = float(_fee_dict.get("cost", 0) or 0)
                _fee_cur = str(_fee_dict.get("currency", "") or "")
                result.append(
                    Trade(
                        id=str(r.get("id", "") or ""),
                        symbol=str(r.get("symbol", symbol) or symbol),
                        side=_side,
                        amount=float(r.get("amount", 0) or 0),
                        price=float(r.get("price", 0) or 0),
                        fee=_fee_amt,
                        fee_currency=_fee_cur,
                        timestamp=_ts,
                        raw=r,
                    )
                )
            except (TypeError, ValueError, KeyError) as _exc:
                logger.warning(
                    "get_my_trades: skipping malformed trade %s: %s",
                    r.get("id", "?"),
                    _exc,
                )
                continue
        return result

    async def get_spot_positions(self) -> Optional[dict]:
        """The venue's open spot positions keyed by asset, from ccxt ``fetch_portfolio_details``.

        None when the ccxt exchange has no ``fetch_portfolios``, when a call
        raises, or when no portfolio answers; a positive answer is held for
        ``SPOT_POSITIONS_CACHE_SEC``. Positions for one asset across several
        portfolios sum, and ``avg_entry_price`` is that sum's cost over balance.
        """
        from .base import SpotPosition

        self._ensure_connected()
        if not hasattr(self._ex, "fetch_portfolios") or not hasattr(
            self._ex, "fetch_portfolio_details"
        ):
            return None
        cached = self._spot_positions_cache
        if cached is not None and time.time() - cached[0] < SPOT_POSITIONS_CACHE_SEC:
            return cached[1]
        try:
            await self._rate_limit()
            portfolios = await self._call_sync(self._ex.fetch_portfolios)
            positions: dict = {}
            answered = 0
            for entry in portfolios or []:
                uuid = str(entry.get("id", "") or "")
                if not uuid:
                    continue
                await self._rate_limit()
                rows = await self._call_sync(self._ex.fetch_portfolio_details, uuid)
                answered += 1
                for row in rows or []:
                    if row.get("is_cash"):
                        continue
                    asset = str(row.get("currency", "") or "")
                    if not asset:
                        continue
                    basis = float(row.get("cost_basis", 0) or 0)
                    balance = float(row.get("total_balance_crypto", 0) or 0)
                    unrealized = float(row.get("unrealized_pnl", 0) or 0)
                    avg = float(row.get("average_entry_price", 0) or 0)
                    held = positions.get(asset)
                    if held is None:
                        positions[asset] = SpotPosition(
                            asset=asset,
                            cost_basis_usd=basis,
                            avg_entry_price=avg,
                            unrealized_pnl_usd=unrealized,
                            balance=balance,
                            raw=dict(row),
                        )
                        continue
                    held.cost_basis_usd += basis
                    held.unrealized_pnl_usd += unrealized
                    held.balance += balance
                    if held.balance > 0:
                        held.avg_entry_price = held.cost_basis_usd / held.balance
        except Exception as exc:
            logger.warning(
                "get_spot_positions: %s portfolio breakdown failed: %s",
                self._exchange_id,
                exc,
            )
            return None
        if answered == 0:
            return None
        self._spot_positions_cache = (time.time(), positions)
        return positions

    # -- Asset discovery ------------------------------------------------
    def _sector_products(self) -> dict[str, dict]:
        """Every market record this venue serves an extra asset class under.

        ``VENUE_CLASS_PRODUCT_TYPES`` names the ``product_type`` per class, and
        each row is parsed by the ccxt exchange's own ``parse_spot_market`` so
        a product carries the same record shape ``load_markets`` builds. The
        call is the venue's public products endpoint and reads no credential.
        """
        asked = VENUE_CLASS_PRODUCT_TYPES.get(self._exchange_id) or {}
        method_name = VENUE_PRODUCTS_METHOD.get(self._exchange_id, "")
        method = getattr(self._ex, method_name, None) if method_name else None
        parse = getattr(self._ex, "parse_spot_market", None)
        if not asked or not callable(method) or not callable(parse):
            return {}
        found: dict[str, dict] = {}
        for product_type in sorted(set(asked.values())):
            try:
                body = method(
                    {"product_type": product_type, "limit": PRODUCTS_PAGE_LIMIT}
                )
                rows = (body or {}).get(PRODUCTS_KEY) or []
            except Exception as exc:
                logger.warning(
                    "%s served no %s products: %s",
                    self._exchange_id,
                    product_type,
                    exc,
                )
                continue
            admitted = 0
            for row in rows:
                record = parse(row, {})
                symbol = str((record or {}).get("symbol") or "")
                if not symbol or not (record or {}).get("active", True):
                    continue
                found[symbol] = record
                admitted += 1
            logger.info(
                "%s served %d %s products, %d active",
                self._exchange_id,
                len(rows),
                product_type,
                admitted,
            )
        return found

    def _published_asset_sectors(self) -> Optional[dict[str, str]]:
        """Every asset code this venue publishes a sector for, mapped onto the
        platform's own class name, and None where the venue publishes none.

        ``VENUE_ASSET_SECTOR_RECORDS`` names the public, credential-free method
        and the requests it takes, and ``asset_class_named`` resolves each
        published category once the record's own ``words`` have translated it.
        """
        record = VENUE_ASSET_SECTOR_RECORDS.get(self._exchange_id)
        method = getattr(self._ex, record.method, None) if record else None
        if record is None or not callable(method):
            return None
        found: dict[str, str] = {}
        served = 0
        for request in record.requests or ({},):
            rows = self._asset_sector_rows(method, request)
            if rows is None:
                return None
            served += len(rows)
            self._read_asset_sector_rows(rows, record, found)
        logger.info(
            "%s published a sector for %d of its %d asset codes, over %d rows",
            self._exchange_id,
            sum(1 for one in found.values() if one),
            len(found),
            served,
        )
        return found

    def _asset_sector_rows(self, method: Any, request: Any) -> Optional[list]:
        """The rows one asset-sector call serves, taking the response itself
        where it is a list and ``ASSET_SECTOR_ROWS_KEY`` where it is a mapping.

        None where the call raised or served neither shape, which
        ``_published_asset_sectors`` reads as the venue publishing no record.
        """
        try:
            served = method(request) if request else method()
        except Exception as exc:
            logger.warning(
                "%s served no asset sector list for %s: %s",
                self._exchange_id,
                request or "no request",
                exc,
            )
            return None
        if isinstance(served, dict):
            served = served.get(ASSET_SECTOR_ROWS_KEY)
        if not isinstance(served, list):
            logger.warning(
                "%s served an asset sector list of %s, so no sector is read",
                self._exchange_id,
                type(served).__name__,
            )
            return None
        return served

    def _read_asset_sector_rows(
        self, rows: Any, record: AssetSectorRecord, found: dict[str, str]
    ) -> None:
        """Each row's own sector written into ``found`` under its asset code,
        leaving a code a previous row already named untouched.

        A venue naming one code over several product types therefore answers the
        first sector it published for it, which ``record.requests`` orders.
        """
        from ..trading.ata_spm import asset_class_named

        for row in rows:
            if not isinstance(row, dict):
                continue
            published_code = str(row.get(record.code_key) or "")
            if record.code_leg:
                published_code = published_code.split(record.code_leg)[0]
            code = published_code.strip().upper()
            if not code or found.get(code):
                continue
            named = row.get(record.sector_key)
            listed = named if isinstance(named, (list, tuple)) else [named]
            found[code] = ""
            for one in listed:
                word = record.words.get(str(one), str(one or ""))
                held = asset_class_named(word)
                if held:
                    found[code] = held
                    break

    @_with_retry()
    async def get_markets(self) -> list[AssetInfo]:
        self._ensure_connected()
        if self._markets_cache is not None:
            return self._markets_cache

        markets = []
        classes: dict[str, str] = {}
        published = self._published_asset_sectors()
        precision_mode = getattr(self._ex, "precisionMode", CCXT_DECIMAL_PLACES)
        # The capability map belongs to the exchange, not to a market record, so
        # it is read once here and stamped onto every market of this venue.
        declared = declared_order_types(self._ex)
        for sym, info in self._ex.markets.items():
            if not info.get("active", True):
                continue

            markets.append(asset_info(sym, info, precision_mode, declared))
            classes[str(sym)] = market_asset_class(
                info, _published_sector(published, info)
            )

        # A symbol load_markets already answered is kept, so no crypto market is
        # replaced by a product another class serves under the same pair.
        for sym, info in self._sector_products().items():
            if sym in classes:
                continue
            markets.append(asset_info(sym, info, precision_mode, declared))
            classes[sym] = market_asset_class(info, _published_sector(published, info))

        self._markets_cache = markets
        if not markets:
            # The count tells an empty market map from one whose every market
            # is inactive.
            logger.warning(
                "%s served no active market out of %d market records, so no "
                "market rule row is recorded",
                self._exchange_id,
                len(getattr(self._ex, "markets", None) or {}),
            )
        # The Simulator and the Paper Trader reach no venue, so the rules read
        # here are recorded once per read for them to size an order by.
        try:
            record_venue(self._exchange_id, markets, classes=classes)
        except OSError as exc:
            logger.warning(
                "market rules for %s not recorded: %s", self._exchange_id, exc
            )
        return markets

    async def get_asset_logo_url(self, currency: str) -> str:
        """Return a CDN URL for the asset's logo."""
        return _LOGO_FALLBACK.format(symbol=currency.upper())

    # -- Helpers --------------------------------------------------------
    @staticmethod
    def _parse_order(raw: dict) -> Order:
        """Convert a CCXT order dict to an :class:`Order`.

        Side, type and status use ``or`` rather than a ``get`` default: CCXT
        returns an explicit ``None`` for them, which a default never replaces.
        """
        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "rejected": OrderStatus.FAILED,
        }
        fee_info = raw.get("fee") or {}
        # CCXT omits `average` on some venues; derive it from cost / filled.
        _avg = raw.get("average")
        _filled = float(raw.get("filled", 0) or 0)
        if _avg in (None, "", 0) and _filled > 0:
            _cost = float(raw.get("cost", 0) or 0)
            _avg = (_cost / _filled) if _cost > 0 else 0.0
        return Order(
            id=str(raw.get("id") or ""),
            symbol=str(raw.get("symbol") or ""),
            side=OrderSide(raw.get("side") or "buy"),
            type=OrderType(raw.get("type") or "limit"),
            amount=float(raw.get("amount", 0) or 0),
            price=float(raw.get("price", 0) or 0),
            filled=_filled,
            remaining=float(raw.get("remaining", 0) or 0),
            status=status_map.get(raw.get("status") or "", OrderStatus.OPEN),
            timestamp=float(raw.get("timestamp", 0) or 0) / 1000,
            fee=float(fee_info.get("cost", 0) or 0),
            fee_currency=str(fee_info.get("currency") or ""),
            average=float(_avg or 0),
            raw=raw,
        )


def create_connector(exchange_id: str) -> CCXTConnector:
    """Return a connector for *exchange_id*."""
    return CCXTConnector(exchange_id)


def list_supported_exchanges() -> list[dict[str, str | bool]]:
    """Return every registry entry with its name, credential shape and status."""
    return [
        {
            "id": eid,
            "name": eid.capitalize(),
            "requires_passphrase": eid in PASSPHRASE_EXCHANGES,
            "verified": eid in VERIFIED_EXCHANGES,
            "us_ip_blocked": eid in US_IP_BLOCKED_EXCHANGES,
            "label": exchange_label(eid),
        }
        for eid in SUPPORTED_EXCHANGES
    ]


def restriction_note(exchange_id: str) -> str:
    """Name the refusal *exchange_id* carries, which exchange_label and sync_connect read."""
    if exchange_id in US_IP_BLOCKED_EXCHANGES:
        return US_IP_BLOCKED_NOTE
    if exchange_id in US_ACCOUNT_RESTRICTED_EXCHANGES:
        return US_ACCOUNT_RESTRICTED_NOTE
    return ""


def exchange_label(exchange_id: str) -> str:
    """Return the picker label for *exchange_id*, carrying its status notes."""
    label = exchange_id.capitalize()
    notes: list[str] = []
    refusal = restriction_note(exchange_id)
    if refusal:
        notes.append(refusal)
    elif exchange_id not in VERIFIED_EXCHANGES:
        notes.append("untested")
    if exchange_id in PASSPHRASE_EXCHANGES:
        notes.append("passphrase required")
    if notes:
        label += f" ({', '.join(notes)})"
    return label


def requires_passphrase(exchange_id: str) -> bool:
    """Return True if the exchange requires an API passphrase."""
    return exchange_id in PASSPHRASE_EXCHANGES
