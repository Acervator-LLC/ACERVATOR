"""The assets each ATA-SPM sector holds, and the venue that lists each one.

``listings_for`` answers one sector's ``AssetListing`` rows and ``venue_candles``
reads one listed name's candles through ``YahooChartAdapter``. A row carrying
``NO_VENUE`` is reported by ``ata_spm.evaluate`` and never scanned.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..exchange.market_inspector_fetcher import DAILY_BARS, WEEKLY_BARS
from .ata_spm import (
    CLASS_CRYPTO,
    CLASS_DERIVATIVES,
    CLASS_FOREX,
    CLASS_METALS,
    CLASS_STOCKS,
)
from .indicators.types import CandleDomainError, candles_from_raw
from .stone_tablets.ra_fetcher import (
    RA_TIMEFRAME,
    DAY_MS,
    YAHOO_INTERVALS,
    YahooChartAdapter,
)

logger = logging.getLogger("acervator.ata_asset_maps")

VENUE_FETCH_FAILED_LOG = "ata asset map: %s answered no candles: %s"
VENUE_ROWS_REFUSED_LOG = "ata asset map: %s kept %d row(s), refused %d: %s"

#: ``YahooChartAdapter.exchange_id``, the one non-crypto venue configured here.
VENUE_YAHOO = "yahoo"

#: The crypto exchange ``fetch_htf_universe`` ranked into its universe, whose
#: candles the shared analyzer keeps.
VENUE_EXCHANGE = "exchange"

#: The venue field of a name no configured venue lists.
NO_VENUE = ""

#: The timeframes each venue answers. ``YahooChartAdapter.fetch_chunk`` refuses
#: every key outside ``YAHOO_INTERVALS``, and ``_fetch_one_symbol`` keys its
#: candles by the daily and weekly pair.
VENUE_TIMEFRAMES: dict[str, tuple[str, ...]] = {
    VENUE_YAHOO: tuple(YAHOO_INTERVALS),
    VENUE_EXCHANGE: (RA_TIMEFRAME, "1w"),
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

USD = "USD"


@dataclass(frozen=True)
class AssetListing:
    """One asset a sector holds, with the venue and ticker carrying it.

    ``quote`` is the currency the venue prices ``ticker`` in, which
    ``YahooChartAdapter.fetch_chunk`` checks its answer against.
    """

    symbol: str
    quote: str = USD
    venue: str = NO_VENUE
    ticker: str = ""

    @property
    def listed(self) -> bool:
        """True when ``venue`` and ``ticker`` both name something."""
        return bool(self.venue) and bool(self.ticker)

    def serves(self, timeframe: Any) -> bool:
        """True when ``venue`` answers candles on ``timeframe``."""
        return str(timeframe) in VENUE_TIMEFRAMES.get(self.venue, ())


def _yahoo_fx(symbol: str) -> AssetListing:
    """One currency pair as the ``VENUE_YAHOO`` ticker spelling it."""
    base, _, quote = symbol.partition("/")
    return AssetListing(
        symbol=symbol,
        quote=quote,
        venue=VENUE_YAHOO,
        ticker=f"{base}{quote}=X",
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
#: for every spelling of all four, measured 2026-09-08.
METALS_SPOT: tuple[AssetListing, ...] = tuple(
    AssetListing(symbol=one, quote=USD)
    for one in ("XAU/USD", "XAG/USD", "XPT/USD", "XPD/USD")
)

MAPS: dict[str, dict[str, tuple[AssetListing, ...]]] = {
    CLASS_FOREX: {
        SECTOR_MAJOR: FOREX_MAJOR,
        SECTOR_MINOR: FOREX_MINOR,
        SECTOR_EXOTIC: FOREX_EXOTIC,
    },
    CLASS_METALS: {SECTOR_SPOT: METALS_SPOT},
}

#: What each class's map was built from, and when its tickers were measured.
MAP_SOURCES: dict[str, str] = {
    CLASS_CRYPTO: (
        "Hand-curated asset tags in sector_map.json, read by load_sector_map. "
        "Candles come from the Market Inspector universe scan."
    ),
    CLASS_FOREX: (
        "Liquidity tiers: major holds USD, minor crosses two majors, exotic "
        "pairs a major with a smaller economy. 28 tickers measured on the "
        "yahoo chart endpoint 2026-09-08, 283 daily rows each."
    ),
    CLASS_METALS: (
        "Spot pairs against the dollar, quoted per troy ounce. No configured "
        "venue lists any of the four, measured 2026-09-08."
    ),
    CLASS_STOCKS: (
        "GICS names 11 sectors over 25 industry groups, 74 industries and 163 "
        "sub-industries. The company membership is licensed by MSCI and S&P "
        "and no list of it sits in this tree."
    ),
    CLASS_DERIVATIVES: "No classification is named for this class yet.",
}


def exchange_listing(symbol: Any) -> AssetListing:
    """One crypto name as the row ``VENUE_EXCHANGE`` charts it under."""
    name = str(symbol)
    return AssetListing(symbol=name, quote=USD, venue=VENUE_EXCHANGE, ticker=name)


def sectors_for(asset_class: Any) -> tuple[str, ...]:
    """The sector names one class carries a map for."""
    return tuple(MAPS.get(str(asset_class), {}))


def listings_for(sector: Any, asset_class: Any) -> tuple[AssetListing, ...]:
    """The rows one named sector holds, matched without regard to case."""
    held = MAPS.get(str(asset_class), {})
    return held.get(str(sector).strip().lower(), ())


def listing_of(symbol: Any) -> Optional[AssetListing]:
    """The row every map holds for one symbol, or None when none names it."""
    asked = str(symbol).strip().upper()
    for sectors in MAPS.values():
        for rows in sectors.values():
            for one in rows:
                if one.symbol.upper() == asked:
                    return one
    return None


def _adapter_for(venue: str) -> Optional[YahooChartAdapter]:
    """The fetcher one venue name is served by, or None for an unknown name."""
    if venue == VENUE_YAHOO:
        return YahooChartAdapter()
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


def venue_candles(symbol: Any, timeframe: Any, days: int = 0) -> list:
    """The candles the venue listing ``symbol`` answers over the last ``days``.

    A ``days`` of zero reads ``venue_window_days``; a symbol no map names, a
    row carrying ``NO_VENUE`` and an unserved timeframe answer no candles.
    """
    found = listing_of(symbol)
    if found is None or not found.listed or not found.serves(timeframe):
        return []
    adapter = _adapter_for(found.venue)
    if adapter is None:
        return []
    window = int(days) or venue_window_days(timeframe)
    now_ms = int(time.time() * 1000)
    attempt = asyncio.run(
        adapter.fetch_chunk(
            found.ticker,
            found.quote,
            now_ms - window * DAY_MS,
            now_ms,
            timeframe=str(timeframe),
        )
    )
    if attempt.error:
        logger.debug(VENUE_FETCH_FAILED_LOG, found.ticker, attempt.error)
        return []
    return _candles_of(found.ticker, attempt.candles)


def _candles_of(ticker: str, rows: Any) -> list:
    """Every row ``candles_from_raw`` accepts, one row at a time.

    A venue row whose open or close sits outside its own high and low is not
    a candle, and it is counted into ``VENUE_ROWS_REFUSED_LOG``.
    """
    kept: list = []
    refused: list = []
    for row in list(rows or []):
        try:
            kept.extend(candles_from_raw([row]))
        except (CandleDomainError, IndexError) as exc:
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
    "MAPS",
    "MAP_SOURCES",
    "METALS_SPOT",
    "MIN_WINDOW_DAYS",
    "NO_VENUE",
    "SECTOR_EXOTIC",
    "SECTOR_MAJOR",
    "SECTOR_MINOR",
    "SECTOR_SPOT",
    "TIMEFRAME_BARS_ASKED",
    "TIMEFRAME_BAR_DAYS",
    "VENUE_EXCHANGE",
    "VENUE_TIMEFRAMES",
    "VENUE_WINDOW_DAYS",
    "VENUE_YAHOO",
    "exchange_listing",
    "listing_of",
    "listings_for",
    "sectors_for",
    "venue_candles",
    "venue_window_days",
]
