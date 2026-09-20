"""The assets each ATA-SPM sector holds, and the venue that lists each one.

``listings_for`` answers one sector's ``AssetListing`` rows and ``venue_candles``
reads one listed name's candles through ``YahooChartAdapter``. A row carrying
``NO_VENUE`` is reported by ``ata_spm.evaluate`` and never scanned.
``screener_listings`` reads the stocks list at press time from Yahoo's
predefined screener, and ``MAPS[CLASS_STOCKS]`` holds the RA portfolio
equities the scan walks when that screener refuses. ``futures_listings``
reads the derivatives list at press time from Coinbase's public product list.
"""

from __future__ import annotations

import asyncio
import http.client
import json
import logging
import math
import threading
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Optional

from ..core.safe_url import SafeRequest, safe_urlopen
from ..exchange.api_logger import get_api_log
from ..exchange.market_inspector_fetcher import (
    DAILY_BARS,
    WEEKLY_BARS,
    weekly_rows_from_daily,
)
from ..simulator.portfolios import CRYPTO_SYMBOLS, SYMBOLS
from .ata_spm import (
    CLASS_CRYPTO,
    CLASS_DERIVATIVES,
    CLASS_ENERGY,
    CLASS_FOREX,
    CLASS_METALS,
    CLASS_STOCKS,
)
from .indicators.types import CandleDomainError, candles_from_raw
from .stone_tablets.ra_fetcher import (
    FUTURES_GRANULARITIES,
    RA_TIMEFRAME,
    DAY_MS,
    USER_AGENT,
    YAHOO_INTERVALS,
    CoinbaseFuturesCandles,
    YahooChartAdapter,
)

logger = logging.getLogger("acervator.ata_asset_maps")

VENUE_FETCH_FAILED_LOG = "ata asset map: %s answered no candles: %s"

#: The predefined Yahoo screener the stocks list is read from at press time.
SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
SCREENER_ID = "most_actives"
#: The screener serves at most 250 quotes per call.
SCREENER_COUNT = 100
SCREENER_TIMEOUT_S = 20.0
SCREENER_VOLUME_KEY = "regularMarketVolume"
SCREENER_SECTOR_KEY = "sector"
SCREENER_SYMBOL_KEY = "symbol"
SCREENER_QUOTE_TYPE_KEY = "quoteType"
SCREENER_EQUITY = "EQUITY"
SCREENER_SOURCE_TEXT = "yahoo most_actives volume"
SCREENER_EMPTY_TEXT = "the screener answered no quote"
SCREENER_REFUSED_LOG = "ata asset map: screener refused: %s"
SCREENER_ACTION = "FETCH_MARKETS"
SCREENER_REASON = "ATA-SPM scan: the most active US equities by volume"
SCREENER_RESULT_FORMAT = "{count} quotes received, {sectors} sector(s)"
VENUE_ACTION = "FETCH_OHLCV"
VENUE_REASON_FORMAT = "ATA-SPM scan: {timeframe} candles for {ticker}"
VENUE_RESULT_FORMAT = "{count} candles received"
VENUE_NO_CANDLES_RESULT = "No data"
API_LEVEL_SUCCESS = "success"
API_LEVEL_WARNING = "warning"
API_DATA_USAGE = "Fed into the ATA-SPM voters and the live trade gates"

_SCREENED: dict[str, "AssetListing"] = {}
"""The rows the last ``screener_listings`` read answered, by upper-case symbol."""

#: Coinbase Advanced Trade's public product list, no key; ``product_type``
#: FUTURE lists the venue's dated futures and its perpetuals.
FUTURES_PRODUCTS_URL = "https://api.coinbase.com/api/v3/brokerage/market/products"
FUTURES_PRODUCT_TYPE = "FUTURE"
FUTURES_TIMEOUT_S = 20.0
FUTURES_PRODUCTS_KEY = "products"
FUTURES_ID_KEY = "product_id"
FUTURES_QUOTE_KEY = "quote_currency_id"
FUTURES_STATUS_KEY = "status"
FUTURES_STATUS_ONLINE = "online"
FUTURES_DISABLED_KEY = "trading_disabled"
FUTURES_DETAILS_KEY = "future_product_details"
FUTURES_EXPIRY_KEY = "contract_expiry_type"
FUTURES_EXPIRING = "EXPIRING"
FUTURES_PERPETUAL = "PERPETUAL"
FUTURES_VOLUME_KEY = "volume_24h"
FUTURES_PRICE_KEY = "price"
FUTURES_SOURCE_TEXT = "coinbase futures and perpetuals, 24 h volume x price"
FUTURES_EMPTY_TEXT = "the product list answered no trading futures product"
FUTURES_REFUSED_LOG = "ata asset map: futures product list refused: %s"
FUTURES_ACTION = "FETCH_MARKETS"
FUTURES_REASON = "ATA-SPM scan: which futures and perpetual products the venue trades"
FUTURES_RESULT_FORMAT = (
    "{count} trading products received, {dead} not trading, "
    "{expiring} expiring, {perpetual} perpetual"
)

_FUTURES: dict[str, "AssetListing"] = {}
"""The rows the last ``futures_listings`` read answered, by upper-case symbol."""

#: What a public product read raises: a transport or HTTP failure, a refused
#: scheme or a body that is not JSON, and a body of an unexpected shape.
VENUE_READ_ERRORS = (
    OSError,
    http.client.HTTPException,
    ValueError,
    TypeError,
    AttributeError,
)

#: The least gap between two venue reads, the interval the exchange
#: connector already keeps between its own calls.
VENUE_MIN_INTERVAL_S = 0.1
_VENUE_LOCK = threading.Lock()
_VENUE_LAST_CALL_MONO: float = 0.0


def _venue_wait() -> None:
    """Hold the venue route to one call per ``VENUE_MIN_INTERVAL_S``."""
    global _VENUE_LAST_CALL_MONO
    with _VENUE_LOCK:
        gap = VENUE_MIN_INTERVAL_S - (time.monotonic() - _VENUE_LAST_CALL_MONO)
        if gap > 0:
            time.sleep(gap)
        _VENUE_LAST_CALL_MONO = time.monotonic()


#: The refusals ``venue_candle_read`` names, one per reason it read nothing.
UNMAPPED_TEXT = "no map lists {symbol}"
NO_VENUE_TEXT = "no configured venue lists {symbol}"
UNSERVED_TEXT = "{venue} does not serve {timeframe}"
NO_ADAPTER_TEXT = "no fetcher serves {venue}"
UNVOLUMED_TEXT = "{venue} sends volume 0 on every bar of {symbol}"
NO_COMPLETE_BAR_TEXT = "{venue} sent no bar for {symbol}"
VENUE_ROWS_REFUSED_LOG = "ata asset map: %s kept %d row(s), refused %d: %s"

#: A listed name whose venue read no figure ranks with this one.
NO_VOLUME_FIGURE = 0.0

MS_PER_S = 1000
#: Seconds in one UTC day, the unit every ``AssetListing`` candle is stamped in.
DAY_S = DAY_MS // MS_PER_S

#: ``venue_quote_volume`` reads this timeframe over ``VOLUME_WINDOW_DAYS``,
#: the least window holding one complete session across a weekend.
VOLUME_TIMEFRAME = RA_TIMEFRAME
VOLUME_WINDOW_DAYS = 7

#: ``YahooChartAdapter.exchange_id``, the one non-crypto venue configured here.
VENUE_YAHOO = "yahoo"

#: The crypto exchange ``fetch_htf_universe`` ranked into its universe, whose
#: candles the shared analyzer keeps.
VENUE_EXCHANGE = "exchange"

#: ``CoinbaseFuturesCandles.exchange_id``, the venue of every derivatives row.
VENUE_FUTURES = CoinbaseFuturesCandles.exchange_id

#: The venue field of a name no configured venue lists.
NO_VENUE = ""

WEEKLY_TIMEFRAME = "1w"

#: The timeframes each venue answers. ``YahooChartAdapter.fetch_chunk`` refuses
#: every key outside ``YAHOO_INTERVALS``, and ``_fetch_one_symbol`` keys its
#: candles by the daily and weekly pair.
VENUE_TIMEFRAMES: dict[str, tuple[str, ...]] = {
    VENUE_YAHOO: tuple(YAHOO_INTERVALS),
    VENUE_EXCHANGE: (RA_TIMEFRAME, WEEKLY_TIMEFRAME),
    VENUE_FUTURES: tuple(FUTURES_GRANULARITIES) + (WEEKLY_TIMEFRAME,),
}

#: A timeframe a venue answers through another one: ``venue_candle_read``
#: reads the value and rolls it up through ``weekly_rows_from_daily``.
VENUE_ROLLED_TIMEFRAMES: dict[str, dict[str, str]] = {
    VENUE_FUTURES: {WEEKLY_TIMEFRAME: RA_TIMEFRAME},
}

#: The daily depth ``fetch_htf_universe`` reads for crypto, so both classes
#: vote over one window length.
VENUE_WINDOW_DAYS: int = DAILY_BARS

#: Days one bar of each ``VENUE_TIMEFRAMES`` key covers.
TIMEFRAME_BAR_DAYS: dict[str, float] = {
    "1h": 1.0 / 24.0,
    RA_TIMEFRAME: 1.0,
    "1w": 7.0,
    "1M": 30.0,
}

#: Bars each key is asked for, the two depths ``_fetch_one_symbol`` already reads.
TIMEFRAME_BARS_ASKED: dict[str, int] = {
    "1h": DAILY_BARS,
    RA_TIMEFRAME: DAILY_BARS,
    "1w": WEEKLY_BARS,
    "1M": WEEKLY_BARS,
}

MIN_WINDOW_DAYS: int = 1

SECTOR_MAJOR = "major"
SECTOR_MINOR = "minor"
SECTOR_EXOTIC = "exotic"
SECTOR_SPOT = "spot"
SECTOR_BASE = "base"
SECTOR_EXPIRING = "expiring"
SECTOR_PERPETUAL = "perpetual"
SECTOR_PETROLEUM = "petroleum"
SECTOR_GAS = "gas"
SECTOR_PORTFOLIO = "portfolio"

USD = "USD"


@dataclass(frozen=True)
class AssetListing:
    """One asset a sector holds, with the venue and ticker carrying it.

    ``quote`` is the currency the venue prices ``ticker`` in, which
    ``YahooChartAdapter.fetch_chunk`` checks its answer against; ``volumed``
    says whether ``venue`` sends a volume figure on ``ticker``'s bars;
    ``served`` is the venue's own timeframe table when the row was read off
    one, and ``sector`` the sector the venue's quote named.
    """

    symbol: str
    quote: str = USD
    venue: str = NO_VENUE
    ticker: str = ""
    volumed: bool = True
    served: tuple = ()
    sector: str = ""

    @property
    def listed(self) -> bool:
        """True when ``venue`` and ``ticker`` both name something."""
        return bool(self.venue) and bool(self.ticker)

    def serves(self, timeframe: Any) -> bool:
        """True when ``venue`` answers candles on ``timeframe``: ``served``
        while the row carries a table, else ``VENUE_TIMEFRAMES``."""
        if self.served:
            return str(timeframe) in self.served
        return str(timeframe) in VENUE_TIMEFRAMES.get(self.venue, ())


def _yahoo_fx(symbol: str) -> AssetListing:
    """One currency pair as the ``VENUE_YAHOO`` ticker spelling it.

    ``volumed`` is False: ``MAP_SOURCES`` records volume 0 on every bar.
    """
    base, _, quote = symbol.partition("/")
    return AssetListing(
        symbol=symbol,
        quote=quote,
        venue=VENUE_YAHOO,
        ticker=f"{base}{quote}=X",
        volumed=False,
    )


#: The seven pairs holding USD, the highest liquidity tier.
FOREX_MAJOR: tuple[AssetListing, ...] = tuple(
    _yahoo_fx(one)
    for one in (
        "EUR/USD",
        "USD/JPY",
        "GBP/USD",
        "USD/CHF",
        "AUD/USD",
        "NZD/USD",
        "USD/CAD",
    )
)

#: The major currencies other than USD, in the order a cross names them.
CROSS_ORDER: tuple[str, ...] = ("EUR", "GBP", "AUD", "NZD", "CAD", "CHF", "JPY")

#: Every cross of two ``CROSS_ORDER`` currencies, the tier holding no USD.
FOREX_MINOR: tuple[AssetListing, ...] = tuple(
    _yahoo_fx(f"{base}/{quote}")
    for at, base in enumerate(CROSS_ORDER)
    for quote in CROSS_ORDER[at + 1 :]
)

#: A major against a smaller economy. No pair is named for this tier yet.
FOREX_EXOTIC: tuple[AssetListing, ...] = ()

#: The four spot pairs, quoted per troy ounce. ``VENUE_YAHOO`` answers 404
#: for every spelling of all four, measured 2026-09-09.
METALS_SPOT: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD)
    for one in ("XAU/USD", "XAG/USD", "XPT/USD", "XPD/USD")
)

#: The listed instrument for each ``METALS_SPOT`` metal: a fund holding the
#: metal, priced in dollars, with no expiry and no contract roll.
METALS_PHYSICAL: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in ("GLD", "SLV", "PPLT", "PALL")
)

#: The listed instrument for each base metal, a fund of the same kind: CPER
#: for copper and DBB for aluminium, zinc and copper together.
METALS_BASE: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in ("CPER", "DBB")
)

#: The listed instrument for each petroleum product: a fund priced in
#: dollars whose shares carry no expiry, so its chart is one series.
ENERGY_PETROLEUM: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in ("USO", "BNO", "UGA")
)

#: The listed instrument for natural gas, a fund of the same kind.
ENERGY_GAS: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in ("UNG",)
)

#: The names the metals and energy maps already carry, kept off the stocks map.
_MAPPED_FUNDS: frozenset[str] = frozenset(
    one.symbol for one in METALS_PHYSICAL + METALS_BASE + ENERGY_PETROLEUM + ENERGY_GAS
)

#: The operator's RA portfolio equities, every non-crypto ``SYMBOLS`` name
#: no other map carries, on ``VENUE_YAHOO`` in ``SYMBOLS`` order.
STOCKS_PORTFOLIO: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD, venue=VENUE_YAHOO, ticker=one)
    for one in SYMBOLS
    if one not in CRYPTO_SYMBOLS and one not in _MAPPED_FUNDS
)

MAPS: dict[str, dict[str, tuple[AssetListing, ...]]] = {
    CLASS_FOREX: {
        SECTOR_MAJOR: FOREX_MAJOR,
        SECTOR_MINOR: FOREX_MINOR,
        SECTOR_EXOTIC: FOREX_EXOTIC,
    },
    CLASS_METALS: {
        SECTOR_SPOT: METALS_SPOT + METALS_PHYSICAL,
        SECTOR_BASE: METALS_BASE,
    },
    CLASS_ENERGY: {
        SECTOR_PETROLEUM: ENERGY_PETROLEUM,
        SECTOR_GAS: ENERGY_GAS,
    },
    CLASS_STOCKS: {SECTOR_PORTFOLIO: STOCKS_PORTFOLIO},
}

#: What each class's map was built from, and when its tickers were measured.
MAP_SOURCES: dict[str, str] = {
    CLASS_CRYPTO: (
        "Hand-curated asset tags in sector_map.json, read by load_sector_map. "
        "Candles come from the Market Inspector universe scan, or from the "
        "connector's candle call. The market list at press time keeps the "
        "products the venue's market table says it trades: status online and "
        "trading_disabled false; the rest are named on the order line and "
        "never fetched."
    ),
    CLASS_FOREX: (
        "Liquidity tiers: major holds USD, minor crosses two majors, exotic "
        "pairs a major with a smaller economy. 28 tickers measured on the "
        "yahoo chart endpoint 2026-09-08, 283 daily rows each. Every daily "
        "bar carries volume 0, so VolumeAnalysis abstains on every pair: "
        "0 of 2,676 bars over 10 pairs, measured 2026-09-09."
    ),
    CLASS_METALS: (
        "Spot pairs against the dollar, quoted per troy ounce. No configured "
        "venue lists any of the four, measured 2026-09-09. The listed "
        "instrument for each metal is the fund holding it, measured the same "
        "day: GLD SLV PPLT PALL, 274 daily rows each, every bar carrying "
        "volume. The futures GC=F SI=F PL=F PA=F answer the same window and "
        "are not carried: a chart of them joins contracts at a price nobody "
        "traded, and PL=F sends 132 of 275 bars with volume 0. The base "
        "metals under the same rule, measured 2026-09-20: CPER for copper and "
        "DBB for aluminium, zinc and copper together, 250 daily rows each, "
        "the last complete daily bar carrying volume; the notes JJN JJU JJT "
        "LD for nickel, aluminium, tin and lead answered HTTP 404, so no "
        "listed instrument carries any of those four alone."
    ),
    CLASS_STOCKS: (
        "GICS names 11 sectors over 25 industry groups, 74 industries and 163 "
        "sub-industries; the company membership is licensed by MSCI and S&P. "
        "At press time the list is Yahoo's predefined most_actives screener, "
        "unauthenticated, up to 250 US equities ranked by regularMarketVolume, "
        "each quote naming its sector; screener_listings reads it. When that "
        "screener refuses or answers no quote, the list is STOCKS_PORTFOLIO: "
        "the operator's RA portfolio equities from src/simulator/portfolios.py, "
        "every non-crypto SYMBOLS name the metals and energy maps do not carry, "
        "on the yahoo chart endpoint in SYMBOLS order."
    ),
    CLASS_DERIVATIVES: (
        "Coinbase Advanced Trade's public product list, read at press time by "
        "futures_listings: GET /api/v3/brokerage/market/products with "
        "product_type FUTURE, unauthenticated, the venue's dated futures "
        "(contract_expiry_type EXPIRING) and perpetuals (PERPETUAL, the "
        "-PERP-INTX suffix). The list keeps the products whose status is "
        "online and trading_disabled is not set, ranked by volume_24h x price. "
        "Candles come from the same route's candles endpoint on ONE_HOUR and "
        "ONE_DAY, 350 a request, and 1w from the daily rollup. Measured "
        "2026-09-20: 117 trading products, every one EXPIRING on the CDE "
        "venue and none carrying the -PERP-INTX suffix; 57 of them carried no "
        "24 h volume, and 43 answered no candle on any granularity."
    ),
    CLASS_ENERGY: (
        "S&P GSCI groups energy as petroleum and natural gas. The listed "
        "instrument for each product is the fund holding it, measured on the "
        "yahoo chart endpoint 2026-09-15: USO for WTI crude, BNO for Brent "
        "crude, UGA for gasoline, UNG for natural gas, 252 daily rows each, "
        "every bar carrying volume. The futures CL=F BZ=F NG=F answer the same "
        "window and are not carried: a chart of them joins contracts at a "
        "price nobody traded. UHN, the heating oil fund, answered 0 rows, so "
        "no listed instrument carries heating oil; read again 2026-09-20 it "
        "answered HTTP 404 on every timeframe, and no fund holding gasoil is "
        "listed, so the class stays at the four funds."
    ),
}


def exchange_listing(symbol: Any, served: Any = ()) -> AssetListing:
    """One crypto name as the row ``VENUE_EXCHANGE`` charts it under, carrying
    ``served``, the venue's own timeframe table, when the caller read one."""
    name = str(symbol)
    return AssetListing(
        symbol=name,
        quote=USD,
        venue=VENUE_EXCHANGE,
        ticker=name,
        served=tuple(str(one) for one in served or ()),
    )


def sectors_for(asset_class: Any) -> tuple[str, ...]:
    """The sector names one class carries a map for."""
    return tuple(MAPS.get(str(asset_class), {}))


def listings_for(sector: Any, asset_class: Any) -> tuple[AssetListing, ...]:
    """The rows one named sector holds, matched without regard to case."""
    held = MAPS.get(str(asset_class), {})
    return held.get(str(sector).strip().lower(), ())


def listing_of(symbol: Any) -> Optional[AssetListing]:
    """The row every map holds for one symbol, else the row the last
    ``screener_listings`` or ``futures_listings`` read holds for it, else None."""
    asked = str(symbol).strip().upper()
    for sectors in MAPS.values():
        for rows in sectors.values():
            for one in rows:
                if one.symbol.upper() == asked:
                    return one
    return _SCREENED.get(asked) or _FUTURES.get(asked)


def screened_listings() -> tuple[AssetListing, ...]:
    """The rows the last ``screener_listings`` read answered, in its order."""
    return tuple(_SCREENED.values())


def futures_tickers() -> list:
    """The symbols the last ``futures_listings`` read answered, sorted."""
    return sorted(_FUTURES)


def _futures_products(timeout_s: float) -> list:
    """The product dicts ``FUTURES_PRODUCTS_URL`` answers for ``FUTURES_PRODUCT_TYPE``."""
    params = {"product_type": FUTURES_PRODUCT_TYPE}
    request = SafeRequest(f"{FUTURES_PRODUCTS_URL}?{urllib.parse.urlencode(params)}")
    request.add_header("User-Agent", USER_AGENT)
    with safe_urlopen(request, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return list((payload or {}).get(FUTURES_PRODUCTS_KEY) or [])


def _product_trades(product: dict) -> bool:
    """True while ``FUTURES_STATUS_KEY`` reads online and ``FUTURES_DISABLED_KEY`` is not set."""
    status = str(product.get(FUTURES_STATUS_KEY) or FUTURES_STATUS_ONLINE).lower()
    return status == FUTURES_STATUS_ONLINE and not bool(
        product.get(FUTURES_DISABLED_KEY)
    )


def _expiry_type(product: dict) -> str:
    """``FUTURES_EXPIRY_KEY`` off the product or its ``FUTURES_DETAILS_KEY``, upper case."""
    details = product.get(FUTURES_DETAILS_KEY) or {}
    held = product.get(FUTURES_EXPIRY_KEY) or (
        details.get(FUTURES_EXPIRY_KEY) if isinstance(details, dict) else ""
    )
    return str(held or "").upper()


def _figure_of(product: dict) -> float:
    """``FUTURES_VOLUME_KEY`` times ``FUTURES_PRICE_KEY``, or ``NO_VOLUME_FIGURE``."""
    try:
        volume = float(product.get(FUTURES_VOLUME_KEY) or 0.0)
        price = float(product.get(FUTURES_PRICE_KEY) or 0.0)
    except (TypeError, ValueError):
        return NO_VOLUME_FIGURE
    figure = volume * price
    return figure if figure > NO_VOLUME_FIGURE else NO_VOLUME_FIGURE


def futures_listings(timeout_s: float = FUTURES_TIMEOUT_S) -> tuple[list, dict, str]:
    """The derivatives rows ``FUTURES_PRODUCTS_URL`` lists as trading, their
    figures by symbol, and the refusal when it answered none.

    Each product is one ``AssetListing`` on ``VENUE_FUTURES`` under
    ``SECTOR_EXPIRING`` or ``SECTOR_PERPETUAL``, and the rows fill ``_FUTURES``.
    """
    start = time.monotonic()
    try:
        products = _futures_products(timeout_s)
    except VENUE_READ_ERRORS as exc:
        refusal = f"{type(exc).__name__}: {exc}"
        logger.debug(FUTURES_REFUSED_LOG, refusal)
        get_api_log().record(
            exchange=VENUE_FUTURES,
            action=FUTURES_ACTION,
            reason=FUTURES_REASON,
            endpoint=FUTURES_PRODUCT_TYPE,
            params={"product_type": FUTURES_PRODUCT_TYPE},
            result=refusal,
            elapsed_ms=(time.monotonic() - start) * 1000,
            level=API_LEVEL_WARNING,
            data_usage=API_DATA_USAGE,
        )
        return [], {}, refusal
    rows: list = []
    figures: dict = {}
    dead = 0
    for product in products:
        if not isinstance(product, dict):
            continue
        symbol = str(product.get(FUTURES_ID_KEY) or "").strip().upper()
        if not symbol or any(one.symbol == symbol for one in rows):
            continue
        if not _product_trades(product):
            dead += 1
            continue
        expiry = _expiry_type(product)
        rows.append(
            AssetListing(
                symbol=symbol,
                quote=str(product.get(FUTURES_QUOTE_KEY) or USD).upper(),
                venue=VENUE_FUTURES,
                ticker=symbol,
                served=VENUE_TIMEFRAMES[VENUE_FUTURES],
                sector=(
                    SECTOR_PERPETUAL if expiry == FUTURES_PERPETUAL else SECTOR_EXPIRING
                ),
            )
        )
        figure = _figure_of(product)
        if figure > NO_VOLUME_FIGURE:
            figures[symbol] = figure
    get_api_log().record(
        exchange=VENUE_FUTURES,
        action=FUTURES_ACTION,
        reason=FUTURES_REASON,
        endpoint=FUTURES_PRODUCT_TYPE,
        params={"product_type": FUTURES_PRODUCT_TYPE},
        result=FUTURES_RESULT_FORMAT.format(
            count=len(rows),
            dead=dead,
            expiring=sum(1 for one in rows if one.sector == SECTOR_EXPIRING),
            perpetual=sum(1 for one in rows if one.sector == SECTOR_PERPETUAL),
        ),
        elapsed_ms=(time.monotonic() - start) * 1000,
        level=API_LEVEL_SUCCESS if rows else API_LEVEL_WARNING,
        data_usage=API_DATA_USAGE,
    )
    if not rows:
        return [], {}, FUTURES_EMPTY_TEXT
    _FUTURES.clear()
    _FUTURES.update({one.symbol: one for one in rows})
    return rows, figures, ""


def _screener_quotes(count: int, timeout_s: float) -> list:
    """The quote dicts ``SCREENER_URL`` answers for ``SCREENER_ID``."""
    params = {"scrIds": SCREENER_ID, "count": int(count)}
    request = SafeRequest(f"{SCREENER_URL}?{urllib.parse.urlencode(params)}")
    request.add_header("User-Agent", USER_AGENT)
    with safe_urlopen(request, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))
    results = ((payload or {}).get("finance") or {}).get("result") or []
    return list((results[0] or {}).get("quotes") or []) if results else []


def screener_listings(
    count: int = SCREENER_COUNT, timeout_s: float = SCREENER_TIMEOUT_S
) -> tuple[list, dict, str]:
    """The stocks rows ``SCREENER_URL`` ranks by ``SCREENER_VOLUME_KEY``, their
    figures by symbol, and the refusal when it answered none.

    Each quote becomes one ``AssetListing`` on ``VENUE_YAHOO`` carrying its
    ``SCREENER_SECTOR_KEY``; the rows also fill ``_SCREENED`` for ``listing_of``.
    """
    start = time.monotonic()
    try:
        quotes = _screener_quotes(count, timeout_s)
    except Exception as exc:  # noqa: BLE001 - the venue is off-process
        refusal = f"{type(exc).__name__}: {exc}"
        logger.debug(SCREENER_REFUSED_LOG, refusal)
        get_api_log().record(
            exchange=VENUE_YAHOO,
            action=SCREENER_ACTION,
            reason=SCREENER_REASON,
            endpoint=SCREENER_ID,
            params={"count": int(count)},
            result=refusal,
            elapsed_ms=(time.monotonic() - start) * 1000,
            level=API_LEVEL_WARNING,
            data_usage=API_DATA_USAGE,
        )
        return [], {}, refusal
    rows: list = []
    figures: dict = {}
    for quote in quotes:
        if not isinstance(quote, dict):
            continue
        symbol = str(quote.get(SCREENER_SYMBOL_KEY) or "").strip().upper()
        kind = str(quote.get(SCREENER_QUOTE_TYPE_KEY) or SCREENER_EQUITY).upper()
        if not symbol or kind != SCREENER_EQUITY or symbol in figures:
            continue
        try:
            volume = float(quote.get(SCREENER_VOLUME_KEY) or 0.0)
        except (TypeError, ValueError):
            volume = 0.0
        rows.append(
            AssetListing(
                symbol=symbol,
                quote=USD,
                venue=VENUE_YAHOO,
                ticker=symbol,
                sector=str(quote.get(SCREENER_SECTOR_KEY) or ""),
            )
        )
        if volume > NO_VOLUME_FIGURE:
            figures[symbol] = volume
    sectors = {one.sector for one in rows if one.sector}
    get_api_log().record(
        exchange=VENUE_YAHOO,
        action=SCREENER_ACTION,
        reason=SCREENER_REASON,
        endpoint=SCREENER_ID,
        params={"count": int(count)},
        result=SCREENER_RESULT_FORMAT.format(count=len(rows), sectors=len(sectors)),
        elapsed_ms=(time.monotonic() - start) * 1000,
        level=API_LEVEL_SUCCESS if rows else API_LEVEL_WARNING,
        data_usage=API_DATA_USAGE,
    )
    if not rows:
        return [], {}, SCREENER_EMPTY_TEXT
    _SCREENED.clear()
    _SCREENED.update({one.symbol: one for one in rows})
    return rows, figures, ""


def _adapter_for(venue: str) -> Any:
    """The fetcher one venue name is served by, or None for an unknown name."""
    if venue == VENUE_YAHOO:
        return YahooChartAdapter()
    if venue == VENUE_FUTURES:
        return CoinbaseFuturesCandles()
    return None


def venue_window_days(timeframe: Any) -> int:
    """The days one timeframe is asked over, from its bar target and bar length.

    ``TIMEFRAME_BARS_ASKED`` bars of ``TIMEFRAME_BAR_DAYS`` each, never under
    ``MIN_WINDOW_DAYS``; a key neither map names reads ``VENUE_WINDOW_DAYS``.
    """
    key = str(timeframe)
    if key not in TIMEFRAME_BARS_ASKED or key not in TIMEFRAME_BAR_DAYS:
        return VENUE_WINDOW_DAYS
    asked = TIMEFRAME_BARS_ASKED[key] * TIMEFRAME_BAR_DAYS[key]
    return max(MIN_WINDOW_DAYS, math.ceil(asked))


def venue_candle_read(symbol: Any, timeframe: Any, days: int = 0) -> tuple:
    """The candles and the refusal the venue listing ``symbol`` answers.

    A ``days`` of zero reads ``venue_window_days``; a symbol no map names, a
    row carrying ``NO_VENUE``, an unserved timeframe and a venue error each
    answer no candles and name the refusal.
    """
    found = listing_of(symbol)
    if found is None:
        return [], UNMAPPED_TEXT.format(symbol=symbol)
    if not found.listed:
        return [], NO_VENUE_TEXT.format(symbol=symbol)
    if not found.serves(timeframe):
        return [], UNSERVED_TEXT.format(venue=found.venue, timeframe=timeframe)
    adapter = _adapter_for(found.venue)
    if adapter is None:
        return [], NO_ADAPTER_TEXT.format(venue=found.venue)
    window = int(days) or venue_window_days(timeframe)
    now_ms = int(time.time() * 1000)
    rolled = VENUE_ROLLED_TIMEFRAMES.get(found.venue, {}).get(str(timeframe))
    _venue_wait()
    start = time.monotonic()
    attempt = asyncio.run(
        adapter.fetch_chunk(
            found.ticker,
            found.quote,
            now_ms - window * DAY_MS,
            now_ms,
            timeframe=rolled or str(timeframe),
        )
    )
    rows = weekly_rows_from_daily(attempt.candles) if rolled else attempt.candles
    candles = [] if attempt.error else _candles_of(found.ticker, rows)
    get_api_log().record(
        exchange=found.venue,
        action=VENUE_ACTION,
        reason=VENUE_REASON_FORMAT.format(timeframe=timeframe, ticker=found.ticker),
        endpoint=str(timeframe),
        params={"symbol": found.ticker, "timeframe": str(timeframe), "days": window},
        result=(
            str(attempt.error)
            if attempt.error
            else (
                VENUE_RESULT_FORMAT.format(count=len(candles))
                if candles
                else VENUE_NO_CANDLES_RESULT
            )
        ),
        elapsed_ms=(time.monotonic() - start) * 1000,
        level=API_LEVEL_SUCCESS if candles else API_LEVEL_WARNING,
        data_usage=API_DATA_USAGE,
    )
    if attempt.error:
        logger.debug(VENUE_FETCH_FAILED_LOG, found.ticker, attempt.error)
        return [], str(attempt.error)
    return candles, ""


def venue_candles(symbol: Any, timeframe: Any, days: int = 0) -> list:
    """The candles ``venue_candle_read`` answers over the last ``days``."""
    return venue_candle_read(symbol, timeframe, days)[0]


def complete_bar(candles: Any, now_ms: Any) -> Any:
    """The newest candle stamped before the UTC day holding ``now_ms``.

    A candle's ``timestamp`` is in seconds, as ``_candles_of`` writes it; a
    window holding no such candle answers its newest one, and an empty
    window answers None.
    """
    held = list(candles or [])
    if not held:
        return None
    now_s = int(now_ms) // MS_PER_S
    day_floor_s = now_s - now_s % DAY_S
    closed = [one for one in held if float(one.timestamp) < day_floor_s]
    return closed[-1] if closed else held[-1]


def venue_quote_volume(symbol: Any, now_ms: Any = None) -> tuple:
    """One listed name's quote volume, and the refusal when none was read.

    The figure is ``complete_bar``'s volume times its close over
    ``VOLUME_TIMEFRAME`` candles of the last ``VOLUME_WINDOW_DAYS``; a row
    whose ``volumed`` is False, and a venue that refused, answer
    ``NO_VOLUME_FIGURE`` with the refusal named.
    """
    found = listing_of(symbol)
    if found is None:
        return NO_VOLUME_FIGURE, UNMAPPED_TEXT.format(symbol=symbol)
    if not found.listed:
        return NO_VOLUME_FIGURE, NO_VENUE_TEXT.format(symbol=symbol)
    if not found.volumed:
        return NO_VOLUME_FIGURE, UNVOLUMED_TEXT.format(venue=found.venue, symbol=symbol)
    candles, refusal = venue_candle_read(symbol, VOLUME_TIMEFRAME, VOLUME_WINDOW_DAYS)
    if refusal:
        return NO_VOLUME_FIGURE, refusal
    stamp = int(time.time() * 1000) if now_ms is None else int(now_ms)
    bar = complete_bar(candles, stamp)
    if bar is None:
        return NO_VOLUME_FIGURE, NO_COMPLETE_BAR_TEXT.format(
            venue=found.venue, symbol=symbol
        )
    return float(bar.volume) * float(bar.close), ""


def _candles_of(ticker: str, rows: Any) -> list:
    """Every row ``candles_from_raw`` accepts, one row at a time, its
    millisecond stamp written in seconds, the unit the connector's candles carry.

    A venue row whose open or close sits outside its own high and low is not
    a candle, and it is counted into ``VENUE_ROWS_REFUSED_LOG``.
    """
    kept: list = []
    refused: list = []
    for row in list(rows or []):
        try:
            stamped = [float(row[0]) / MS_PER_S, *row[1:]]
            kept.extend(candles_from_raw([stamped]))
        except (CandleDomainError, IndexError, TypeError, ValueError) as exc:
            refused.append(str(exc))
    if refused:
        logger.debug(
            VENUE_ROWS_REFUSED_LOG, ticker, len(kept), len(refused), refused[0]
        )
    return kept


__all__ = [
    "AssetListing",
    "CROSS_ORDER",
    "FOREX_EXOTIC",
    "FOREX_MAJOR",
    "FOREX_MINOR",
    "FUTURES_PRODUCTS_URL",
    "FUTURES_SOURCE_TEXT",
    "MAPS",
    "MAP_SOURCES",
    "METALS_BASE",
    "METALS_PHYSICAL",
    "METALS_SPOT",
    "MIN_WINDOW_DAYS",
    "NO_VENUE",
    "NO_VOLUME_FIGURE",
    "SECTOR_BASE",
    "SECTOR_EXOTIC",
    "SECTOR_EXPIRING",
    "SECTOR_MAJOR",
    "SECTOR_MINOR",
    "SECTOR_PERPETUAL",
    "SECTOR_PORTFOLIO",
    "SECTOR_SPOT",
    "SCREENER_COUNT",
    "SCREENER_SOURCE_TEXT",
    "SCREENER_URL",
    "STOCKS_PORTFOLIO",
    "TIMEFRAME_BARS_ASKED",
    "TIMEFRAME_BAR_DAYS",
    "VENUE_EXCHANGE",
    "VENUE_FUTURES",
    "VENUE_ROLLED_TIMEFRAMES",
    "VENUE_TIMEFRAMES",
    "VENUE_WINDOW_DAYS",
    "VENUE_YAHOO",
    "VOLUME_TIMEFRAME",
    "VOLUME_WINDOW_DAYS",
    "WEEKLY_TIMEFRAME",
    "complete_bar",
    "exchange_listing",
    "futures_listings",
    "futures_tickers",
    "listing_of",
    "listings_for",
    "screened_listings",
    "screener_listings",
    "sectors_for",
    "venue_candle_read",
    "venue_candles",
    "venue_quote_volume",
    "venue_window_days",
]
