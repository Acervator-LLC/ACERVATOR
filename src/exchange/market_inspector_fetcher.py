"""fetch_htf_universe serves the Market Inspector its daily and weekly OHLC.

_pick_universe ranks each connector's bulk tickers by 24 h quote volume.
_fetch_one_symbol then pulls per-symbol OHLCV from connector.get_ohlcv on
the connector's single-worker executor. weekly_from_daily derives the weekly
series through the stone tablets' _rollup when the venue does not list the 1w
timeframe; exchange_timeframes reads what each connector's own table lists.
fetch_quote_volumes serves the 24 h quote volume per base symbol those same
ticker rows carry, over the same cache window. trading_products reads which
bases the venue trades off the connector's loaded market table, and
public_products and public_candles read the same two things through
CoinbasePublicCandles while no connector is in reach. trading_rules reads each
base's published order rules and the venue's own last price off that same loaded
table, which is what the ticker rows measure a scrum's excess against.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable, Optional
from urllib.error import HTTPError

from ..trading.stone_tablets.ra_fetcher import (
    RA_CHUNK_DAYS,
    RATE_LIMIT_HTTP_CODE,
    CoinbasePublicCandles,
    _get_json,
)
from ..trading.stone_tablets.registry import _rollup
from .api_logger import get_api_log
from .market_pairs_scout import row_quote_volume_24h

logger = logging.getLogger("acervator.market_inspector_fetcher")


DEFAULT_TOP_N = 100
DEFAULT_MIN_REFRESH_S = 15 * 60
"""Default for the min_refresh_s argument of fetch_htf_universe, in seconds."""

DAILY_TIMEFRAME = "1d"
WEEKLY_TIMEFRAME = "1w"
DAYS_PER_WEEK = 7
DAY_MS = 86_400_000
WEEK_MS = DAYS_PER_WEEK * DAY_MS
#: 1970-01-01 is a Thursday; the first Monday, 1970-01-05, is four days on.
MONDAY_OFFSET_MS = 4 * DAY_MS

#: The venue name the public route's API blocks carry.
PUBLIC_EXCHANGE = "coinbase"
#: The public route waits this long between calls, the connector's own interval.
PUBLIC_MIN_INTERVAL_S = 0.1
FETCH_OHLCV_ACTION = "FETCH_OHLCV"
FETCH_MARKETS_ACTION = "FETCH_MARKETS"
SCAN_REASON_FORMAT = "ATA-SPM scan: {bars} candles ({timeframe}) for {symbol}"
PRODUCTS_REASON = "ATA-SPM scan: which products the venue trades"
CANDLES_RESULT_FORMAT = "{count} candles received"
NO_CANDLES_RESULT = "No data"
PRODUCTS_RESULT_FORMAT = "{trading} trading, {dead} not trading"
PRODUCTS_PATH = "products"
PRODUCT_ONLINE = "online"
API_LEVEL_SUCCESS = "success"
API_LEVEL_WARNING = "warning"
API_LEVEL_ERROR = "error"
SCAN_DATA_USAGE = "Fed into the ATA-SPM voters and the live trade gates"
#: What a read names when the venue could not be reached, and when it answered.
VENUE_UNREACHABLE_FORMAT = "{venue} unreachable: {error}"
VENUE_REFUSED_FORMAT = "{venue} refused: {error}"
#: ccxt's transport failures, matched by class name so ccxt is not imported here.
UNREACHABLE_ERROR_NAMES = frozenset(
    {"NetworkError", "RequestTimeout", "ExchangeNotAvailable", "DDoSProtection"}
)
#: ccxt's answer to a 429, matched the same way.
RATE_LIMIT_ERROR_NAMES = frozenset({"RateLimitExceeded"})

_PUBLIC_LOCK = threading.Lock()
_PUBLIC_LAST_CALL_MONO: float = 0.0

_LAST_RESULT: Optional["FetchResult"] = None
_LAST_FETCH_MONO: float = 0.0
"""The last network FetchResult and the time.monotonic() reading it landed at."""

_LAST_VOLUMES: dict = {}
_LAST_VOLUMES_MONO: float = 0.0
"""The last 24 h quote volumes by base symbol and the time.monotonic() they landed at."""
NO_VOLUME_AGE = float("inf")
DAILY_BARS = 365
WEEKLY_BARS = 200

STABLECOIN_DENYLIST = {
    "USD",
    "USDT",
    "USDC",
    "DAI",
    "BUSD",
    "TUSD",
    "USDP",
    "USDD",
    "FRAX",
    "GUSD",
    "LUSD",
    "USDE",
    "USDS",
    "PYUSD",
    "FDUSD",
    "EURC",
    "EUR",
    "GBP",
    "JPY",
    "CAD",
    "AUD",
    "CHF",
}
DEFAULT_QUOTES = ("USD", "USDC", "USDT")  # accept these as USD-equivalent


@dataclass
class _Candle:
    """One OHLC bar built by _ohlcv_to_candles, with timestamp in seconds."""

    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def _pick_universe(
    tickers: dict,
    top_n: int,
    active_symbols: set,
    accepted_quotes: Iterable[str] = DEFAULT_QUOTES,
) -> list[str]:
    """Rank tickers by 24 h quote volume and return the top_n CCXT symbols
    whose quote is in accepted_quotes.

    A base in active_symbols is appended even when it falls outside top_n,
    and a base in STABLECOIN_DENYLIST is dropped.
    """
    quotes = tuple(accepted_quotes)
    scored: list[tuple[float, str, str]] = []
    for sym, tk in (tickers or {}).items():
        if not isinstance(sym, str) or "/" not in sym:
            continue
        base, quote = sym.split("/", 1)
        base_u = base.upper()
        quote_u = quote.upper()
        if quote_u not in quotes:
            continue
        if base_u in STABLECOIN_DENYLIST:
            continue
        scored.append((row_quote_volume_24h(tk), base_u, sym))
    scored.sort(key=lambda t: -t[0])
    top = [sym for _v, _b, sym in scored[:top_n]]
    seen_bases = {sym.split("/", 1)[0].upper() for sym in top}
    for _v, base_u, sym in scored:
        if base_u in active_symbols and base_u not in seen_bases:
            top.append(sym)
            seen_bases.add(base_u)
    return top


def _quote_volumes(
    tickers: dict, accepted_quotes: Iterable[str] = DEFAULT_QUOTES
) -> dict[str, float]:
    """Each base symbol's largest 24 h quote volume across accepted_quotes.

    Reads the same rows and the same row_quote_volume_24h as _pick_universe,
    and drops a base in STABLECOIN_DENYLIST the same way.
    """
    quotes = tuple(accepted_quotes)
    found: dict[str, float] = {}
    for sym, tk in (tickers or {}).items():
        if not isinstance(sym, str) or "/" not in sym:
            continue
        base, quote = sym.split("/", 1)
        base_u = base.upper()
        if quote.upper() not in quotes or base_u in STABLECOIN_DENYLIST:
            continue
        volume = row_quote_volume_24h(tk)
        if volume > found.get(base_u, 0.0):
            found[base_u] = volume
    return found


def _record_quote_volumes(volumes: dict) -> None:
    """Keep volumes as _LAST_VOLUMES and stamp _LAST_VOLUMES_MONO now."""
    global _LAST_VOLUMES, _LAST_VOLUMES_MONO
    _LAST_VOLUMES = dict(volumes)
    _LAST_VOLUMES_MONO = time.monotonic()


def quote_volume_age_s() -> float:
    """Seconds since _LAST_VOLUMES landed, NO_VOLUME_AGE before any did."""
    if not _LAST_VOLUMES:
        return NO_VOLUME_AGE
    return max(0.0, time.monotonic() - _LAST_VOLUMES_MONO)


def cached_quote_volumes() -> dict[str, float]:
    """A copy of _LAST_VOLUMES, whatever its age; asks no connector."""
    return dict(_LAST_VOLUMES)


async def fetch_quote_volumes(
    exchange_connectors: dict,
    min_refresh_s: float = DEFAULT_MIN_REFRESH_S,
) -> dict[str, float]:
    """The 24 h quote volume per base symbol across every connector, now.

    Serves _LAST_VOLUMES while it is younger than min_refresh_s, which the
    Refresh press also fills, and asks connector.get_all_tickers otherwise.
    """
    if quote_volume_age_s() < float(min_refresh_s):
        return dict(_LAST_VOLUMES)
    volumes: dict[str, float] = {}
    for eid, connector in (exchange_connectors or {}).items():
        try:
            tickers = await connector.get_all_tickers()
        except Exception as _tex:  # noqa: BLE001 - per-connector best-effort
            logger.warning("tickers fetch failed on %s: %s", eid, _tex)
            continue
        for base_u, volume in _quote_volumes(tickers).items():
            if volume > volumes.get(base_u, 0.0):
                volumes[base_u] = volume
    if volumes:
        _record_quote_volumes(volumes)
    return volumes


def _ohlcv_to_candles(rows: list) -> list[_Candle]:
    out: list[_Candle] = []
    for r in rows or []:
        if not (isinstance(r, (list, tuple)) and len(r) >= 5):
            continue
        try:
            out.append(
                _Candle(
                    timestamp=int(r[0]) // 1000,
                    open=float(r[1]),
                    high=float(r[2]),
                    low=float(r[3]),
                    close=float(r[4]),
                    volume=float(r[5]) if len(r) > 5 else 0.0,
                )
            )
        except (TypeError, ValueError):
            continue
    return out


def weekly_rows_from_daily(rows: list) -> list:
    """One weekly OHLCV row per calendar week of daily rows, through the
    tablets' _rollup; each row is [ts_ms, open, high, low, close, volume].

    Each timestamp is moved back by MONDAY_OFFSET_MS before _rollup and forward
    after it, so every bucket starts on a Monday 00:00 UTC.
    """
    shifted = [[int(row[0]) - MONDAY_OFFSET_MS, *row[1:6]] for row in rows]
    return [
        [int(row[0]) + MONDAY_OFFSET_MS, *row[1:]]
        for row in _rollup(shifted, DAYS_PER_WEEK, WEEK_MS)
    ]


def weekly_from_daily(daily: list[_Candle]) -> list[_Candle]:
    """One weekly _Candle per calendar week of daily, through weekly_rows_from_daily."""
    rows = [
        [one.timestamp * 1000, one.open, one.high, one.low, one.close, one.volume]
        for one in daily
    ]
    return [
        _Candle(
            timestamp=int(row[0]) // 1000,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
        for row in weekly_rows_from_daily(rows)
    ]


def _exchange_supports_tf(connector, tf: str) -> bool:
    """Return True when connector._ex lists tf in its timeframes map."""
    try:
        ex = getattr(connector, "_ex", None)
        tfs = getattr(ex, "timeframes", None) or {}
        return tf in tfs
    except Exception as _tf_exc:  # noqa: BLE001 - defensive probe
        logger.debug("timeframe probe failed: %s", _tf_exc)
        return False


def exchange_timeframes(exchange_connectors: Any) -> tuple[str, ...]:
    """Every timeframe key any connector's _ex.timeframes table lists, plus
    WEEKLY_TIMEFRAME while DAILY_TIMEFRAME is listed, the key weekly_from_daily
    serves.

    No connector reads CoinbasePublicCandles.GRANULARITY_S, the table
    public_candles reads by.
    """
    found: list[str] = []
    tables = [
        getattr(getattr(one, "_ex", None), "timeframes", None) or {}
        for one in (exchange_connectors or {}).values()
    ] or [CoinbasePublicCandles.GRANULARITY_S]
    for table in tables:
        for key in table:
            if str(key) not in found:
                found.append(str(key))
    if DAILY_TIMEFRAME in found and WEEKLY_TIMEFRAME not in found:
        found.append(WEEKLY_TIMEFRAME)
    return tuple(found)


def _product_trades(status: Any, trading_disabled: Any, active: Any) -> bool:
    """True while status is PRODUCT_ONLINE and trading_disabled is not set.

    A row carrying neither field reads active, the flag ccxt derives from
    trading_disabled.
    """
    if status is None and trading_disabled is None:
        return bool(active)
    online = status is None or str(status).lower() == PRODUCT_ONLINE
    return online and not bool(trading_disabled)


def trading_products(
    exchange_connectors: Any, accepted_quotes: Iterable[str] = DEFAULT_QUOTES
) -> dict[str, bool]:
    """Each base the connectors' loaded _ex.markets tables list against one of
    accepted_quotes, True while _product_trades answers so on any such pair.

    An empty answer says no connector holds a table; no venue is asked.
    """
    quotes = tuple(accepted_quotes)
    found: dict[str, bool] = {}
    for connector in (exchange_connectors or {}).values():
        markets = getattr(getattr(connector, "_ex", None), "markets", None) or {}
        for symbol, market in markets.items():
            if not isinstance(symbol, str) or "/" not in symbol:
                continue
            base, quote = symbol.split("/", 1)
            if quote.upper() not in quotes:
                continue
            info = market.get("info") or {}
            trades = _product_trades(
                info.get("status"),
                info.get("trading_disabled"),
                market.get("active", True),
            )
            base_u = base.upper()
            found[base_u] = found.get(base_u, False) or trades
    return found


def trading_rules(
    exchange_connectors: Any, accepted_quotes: Iterable[str] = DEFAULT_QUOTES
) -> dict[str, tuple]:
    """Each base's published order rules and the venue's own last price, off
    the same loaded _ex.markets tables trading_products walks.

    The value is (MarketRules, price or None). An empty answer says no
    connector holds a table; no venue is asked.
    """
    from .ccxt_connector import CCXT_DECIMAL_PLACES, market_rules, record_price

    quotes = tuple(accepted_quotes)
    found: dict[str, tuple] = {}
    for connector in (exchange_connectors or {}).values():
        holder = getattr(connector, "_ex", None)
        markets = getattr(holder, "markets", None) or {}
        mode = getattr(holder, "precisionMode", CCXT_DECIMAL_PLACES)
        for symbol, market in markets.items():
            if not isinstance(symbol, str) or "/" not in symbol:
                continue
            base, quote = symbol.split("/", 1)
            if quote.upper() not in quotes:
                continue
            base_u = base.upper()
            if base_u in found:
                continue
            found[base_u] = (market_rules(market, mode), record_price(market))
    return found


def _record_api(
    exchange: str,
    action: str,
    reason: str,
    endpoint: str,
    params: dict,
    result: str,
    elapsed_ms: float,
    level: str,
) -> None:
    """One get_api_log record for a public-route call, with SCAN_DATA_USAGE."""
    get_api_log().record(
        exchange=exchange,
        action=action,
        reason=reason,
        endpoint=endpoint,
        params=params,
        result=result,
        elapsed_ms=elapsed_ms,
        level=level,
        data_usage=SCAN_DATA_USAGE,
    )


def _public_wait() -> None:
    """Hold the public route to one call per PUBLIC_MIN_INTERVAL_S."""
    global _PUBLIC_LAST_CALL_MONO
    with _PUBLIC_LOCK:
        gap = PUBLIC_MIN_INTERVAL_S - (time.monotonic() - _PUBLIC_LAST_CALL_MONO)
        if gap > 0:
            time.sleep(gap)
        _PUBLIC_LAST_CALL_MONO = time.monotonic()


def public_products(
    accepted_quotes: Iterable[str] = DEFAULT_QUOTES, timeout_s: float = 20.0
) -> dict[str, bool]:
    """Each base CoinbasePublicCandles.BASE_URL lists against one of
    accepted_quotes, True while _product_trades answers so.

    One FETCH_MARKETS_ACTION block is recorded through _record_api.
    """
    quotes = tuple(accepted_quotes)
    _public_wait()
    start = time.monotonic()
    try:
        rows = _get_json(CoinbasePublicCandles.BASE_URL, {}, timeout_s)
    except Exception as exc:  # noqa: BLE001 - the venue is off-process
        _record_api(
            PUBLIC_EXCHANGE,
            FETCH_MARKETS_ACTION,
            PRODUCTS_REASON,
            PRODUCTS_PATH,
            {},
            f"{type(exc).__name__}: {exc}",
            (time.monotonic() - start) * 1000,
            API_LEVEL_ERROR,
        )
        return {}
    found: dict[str, bool] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        base = str(row.get("base_currency") or "").upper()
        quote = str(row.get("quote_currency") or "").upper()
        if not base or quote not in quotes:
            continue
        trades = _product_trades(
            row.get("status"), row.get("trading_disabled"), row.get("status") is None
        )
        found[base] = found.get(base, False) or trades
    trading = sum(1 for one in found.values() if one)
    _record_api(
        PUBLIC_EXCHANGE,
        FETCH_MARKETS_ACTION,
        PRODUCTS_REASON,
        PRODUCTS_PATH,
        {},
        PRODUCTS_RESULT_FORMAT.format(trading=trading, dead=len(found) - trading),
        (time.monotonic() - start) * 1000,
        API_LEVEL_SUCCESS,
    )
    return found


def rate_limited(exc: BaseException) -> bool:
    """True when ``exc`` is the venue's 429: an ``HTTPError`` with that code, or
    the ``RateLimitExceeded`` ccxt raises. The refusal such an answer leaves
    carries the code or the name, which ``ata_spm.is_rate_limited`` reads."""
    if isinstance(exc, HTTPError):
        return exc.code == RATE_LIMIT_HTTP_CODE
    names = {one.__name__ for one in type(exc).__mro__}
    return bool(names & RATE_LIMIT_ERROR_NAMES)


def venue_refusal(venue: str, exc: BaseException) -> str:
    """VENUE_UNREACHABLE_FORMAT for a transport failure, VENUE_REFUSED_FORMAT
    for an answer the venue gave; HTTPError is an answer."""
    error = f"{type(exc).__name__}: {exc}"
    if isinstance(exc, HTTPError):
        return VENUE_REFUSED_FORMAT.format(venue=venue, error=error)
    names = {one.__name__ for one in type(exc).__mro__}
    if isinstance(exc, (OSError, TimeoutError)) or names & UNREACHABLE_ERROR_NAMES:
        return VENUE_UNREACHABLE_FORMAT.format(venue=venue, error=error)
    return VENUE_REFUSED_FORMAT.format(venue=venue, error=error)


def public_candle_read(
    symbol: str,
    timeframe: str,
    bars: int = DAILY_BARS,
    accepted_quotes: Iterable[str] = DEFAULT_QUOTES,
) -> tuple[list, str]:
    """bars candles for symbol on timeframe through CoinbasePublicCandles, and
    the venue_refusal the last failed call left, with WEEKLY_TIMEFRAME read as
    DAILY_TIMEFRAME and passed through weekly_from_daily.

    A timeframe outside CoinbasePublicCandles.GRANULARITY_S answers no candles
    with no call, and each call records one FETCH_OHLCV_ACTION block. bars is
    held to RA_CHUNK_DAYS, the route's one-request ceiling, so the window it
    asks for ends now rather than bars minus RA_CHUNK_DAYS candles ago.
    """
    base = str(symbol).strip().upper()
    asked = str(timeframe)
    table = CoinbasePublicCandles.GRANULARITY_S
    weekly = asked == WEEKLY_TIMEFRAME and asked not in table
    venue_timeframe = DAILY_TIMEFRAME if weekly else asked
    if not base or venue_timeframe not in table:
        return [], ""
    route = CoinbasePublicCandles()
    count = min(int(bars), RA_CHUNK_DAYS)
    step_ms = table[venue_timeframe] * 1000
    refusal = ""
    for quote in accepted_quotes:
        pair = f"{base}/{quote}"
        reason = SCAN_REASON_FORMAT.format(
            bars=count, timeframe=venue_timeframe, symbol=pair
        )
        params = {"symbol": pair, "timeframe": venue_timeframe, "limit": count}
        _public_wait()
        start = time.monotonic()
        try:
            rows = asyncio.run(
                route.get_ohlcv(
                    pair,
                    venue_timeframe,
                    count,
                    since=int(time.time() * 1000) - count * step_ms,
                )
            )
        except Exception as exc:  # noqa: BLE001 - per-pair best-effort
            refusal = venue_refusal(PUBLIC_EXCHANGE, exc)
            _record_api(
                PUBLIC_EXCHANGE,
                FETCH_OHLCV_ACTION,
                reason,
                "candles",
                params,
                refusal,
                (time.monotonic() - start) * 1000,
                API_LEVEL_WARNING,
            )
            if rate_limited(exc):
                break
            continue
        candles = _ohlcv_to_candles(rows)
        _record_api(
            PUBLIC_EXCHANGE,
            FETCH_OHLCV_ACTION,
            reason,
            "candles",
            params,
            (
                CANDLES_RESULT_FORMAT.format(count=len(candles))
                if candles
                else NO_CANDLES_RESULT
            ),
            (time.monotonic() - start) * 1000,
            API_LEVEL_SUCCESS if candles else API_LEVEL_WARNING,
        )
        if candles:
            return (weekly_from_daily(candles) if weekly else candles), ""
    return [], refusal


def public_candles(
    symbol: str,
    timeframe: str,
    bars: int = DAILY_BARS,
    accepted_quotes: Iterable[str] = DEFAULT_QUOTES,
) -> list:
    """The candles public_candle_read answers."""
    return public_candle_read(symbol, timeframe, bars, accepted_quotes)[0]


async def _fetch_one_symbol(
    connector,
    symbol: str,
    weekly_native: bool,
) -> Optional[dict]:
    """Fetch DAILY_BARS daily candles for symbol, and WEEKLY_BARS weekly
    ones when weekly_native is set.

    Returns a map holding "1d", carrying "1w" only with 20 or more weekly
    bars, or None with under 20 daily bars.
    """
    try:
        daily_raw = await connector.get_ohlcv(symbol, "1d", DAILY_BARS)
    except Exception as _exc:  # noqa: BLE001 - per-symbol best-effort
        logger.debug("daily OHLCV fetch failed for %s: %s", symbol, _exc)
        return None
    daily = _ohlcv_to_candles(daily_raw)
    if len(daily) < 20:
        return None
    tf_map: dict = {"1d": daily}
    if weekly_native:
        try:
            weekly_raw = await connector.get_ohlcv(symbol, "1w", WEEKLY_BARS)
            weekly = _ohlcv_to_candles(weekly_raw)
            if len(weekly) >= 20:
                tf_map["1w"] = weekly
        except Exception as _wexc:  # noqa: BLE001 - fallback to resample
            logger.debug(
                "weekly OHLCV fetch failed for %s (fallback resample): %s",
                symbol,
                _wexc,
            )
    if "1w" not in tf_map:
        weekly = weekly_from_daily(daily)
        if len(weekly) >= 20:
            tf_map["1w"] = weekly
    return tf_map


async def fetch_symbol_timeframe_read(
    exchange_connectors: dict,
    symbol: str,
    timeframe: str,
    bars: int = DAILY_BARS,
) -> tuple[list, str]:
    """bars candles for one base symbol on one timeframe from the first pair in
    DEFAULT_QUOTES any connector in exchange_connectors answers rows for, and
    the venue_refusal the last failed call left.

    A connector whose _ex.timeframes table lacks WEEKLY_TIMEFRAME is asked for
    DAILY_TIMEFRAME and the answer goes through weekly_from_daily, and a
    connector whose table lacks the timeframe asked is not asked. A 429 ends
    the read at once; the other quotes are not asked.
    """
    base = str(symbol).strip().upper()
    asked = str(timeframe)
    refusal = ""
    if not base or not exchange_connectors:
        return [], refusal
    for eid, connector in exchange_connectors.items():
        weekly = asked == WEEKLY_TIMEFRAME and not _exchange_supports_tf(
            connector, asked
        )
        venue_timeframe = DAILY_TIMEFRAME if weekly else asked
        if not _exchange_supports_tf(connector, venue_timeframe):
            logger.debug("OHLCV fetch skipped on %s: %s serves no %s", eid, base, asked)
            continue
        for quote in DEFAULT_QUOTES:
            pair = f"{base}/{quote}"
            try:
                rows = await connector.get_ohlcv(pair, venue_timeframe, int(bars))
            except Exception as _exc:  # noqa: BLE001 - per-pair best-effort
                logger.debug("OHLCV fetch failed on %s %s: %s", eid, pair, _exc)
                refusal = venue_refusal(str(eid), _exc)
                if rate_limited(_exc):
                    return [], refusal
                continue
            candles = _ohlcv_to_candles(rows)
            if candles:
                return (weekly_from_daily(candles) if weekly else candles), ""
    return [], refusal


async def fetch_symbol_timeframe(
    exchange_connectors: dict,
    symbol: str,
    timeframe: str,
    bars: int = DAILY_BARS,
) -> list:
    """The candles fetch_symbol_timeframe_read answers."""
    candles, _refusal = await fetch_symbol_timeframe_read(
        exchange_connectors, symbol, timeframe, bars
    )
    return candles


@dataclass
class FetchResult:
    candles_by_symbol_by_tf: dict  # {base_sym: {"1d": [_Candle], "1w": [_Candle]}}
    closes_by_symbol: dict  # {base_sym: [daily close float, ...]}
    universe: list  # full CCXT symbols scanned
    # source, age_seconds, error, symbol_count, plus elapsed_seconds once a
    # scan has run
    meta: dict


async def fetch_htf_universe(
    exchange_connectors: dict,
    active_symbols: Optional[set] = None,
    top_n: int = DEFAULT_TOP_N,
    progress_cb=None,
    force_network: bool = False,
    min_refresh_s: float = DEFAULT_MIN_REFRESH_S,
) -> FetchResult:
    """Fetch daily and weekly OHLC for the top_n markets plus active_symbols
    across every connector in exchange_connectors.

    Serves _LAST_RESULT while it is younger than min_refresh_s unless
    force_network is set, and skips a base an earlier connector covered.
    """
    active = set(active_symbols or set())
    if not exchange_connectors:
        return FetchResult(
            candles_by_symbol_by_tf={},
            closes_by_symbol={},
            universe=[],
            meta={
                "source": "no-exchange",
                "age_seconds": 0.0,
                "error": "no exchange connectors attached",
                "symbol_count": 0,
            },
        )

    global _LAST_RESULT, _LAST_FETCH_MONO
    # On this path age_seconds is measured and source reads "cache".
    if not force_network and _LAST_RESULT is not None:
        age = time.monotonic() - _LAST_FETCH_MONO
        if 0.0 <= age < float(min_refresh_s):
            cached = FetchResult(
                candles_by_symbol_by_tf=_LAST_RESULT.candles_by_symbol_by_tf,
                closes_by_symbol=_LAST_RESULT.closes_by_symbol,
                universe=_LAST_RESULT.universe,
                meta={
                    **dict(_LAST_RESULT.meta or {}),
                    "source": "cache",
                    "age_seconds": round(age, 3),
                },
            )
            if progress_cb:
                progress_cb(
                    f"Using cached scan ({int(age)}s old; "
                    f"refresh forces a new fetch)"
                )
            return cached

    candles_by_symbol_by_tf: dict = {}
    closes_by_symbol: dict = {}
    universe: list = []
    volumes: dict[str, float] = {}
    fetch_start = time.time()
    combined_error: Optional[str] = None

    for eid, connector in exchange_connectors.items():
        try:
            tickers = await connector.get_all_tickers()
        except Exception as _tex:  # noqa: BLE001 - per-connector best-effort
            logger.warning("tickers fetch failed on %s: %s", eid, _tex)
            combined_error = f"{eid}: {_tex}"
            continue
        for base_u, volume in _quote_volumes(tickers).items():
            if volume > volumes.get(base_u, 0.0):
                volumes[base_u] = volume
        sub_universe = _pick_universe(tickers, top_n, active)
        if not sub_universe:
            continue
        weekly_native = _exchange_supports_tf(connector, "1w")
        for i, symbol in enumerate(sub_universe):
            base_u = symbol.split("/", 1)[0].upper()
            if base_u in candles_by_symbol_by_tf:
                continue  # already covered by an earlier connector
            tf_map = await _fetch_one_symbol(connector, symbol, weekly_native)
            if tf_map is None:
                continue
            candles_by_symbol_by_tf[base_u] = tf_map
            closes_by_symbol[base_u] = [c.close for c in tf_map["1d"]]
            universe.append(symbol)
            if progress_cb is not None:
                try:
                    progress_cb(
                        f"[{eid}] fetched {i + 1}/{len(sub_universe)}: " f"{base_u}"
                    )
                except Exception as _cb_exc:  # noqa: BLE001
                    logger.debug(
                        "market inspector progress callback failed: %s", _cb_exc
                    )

    elapsed = time.time() - fetch_start
    if volumes:
        _record_quote_volumes(volumes)
    # An empty scan returns here, so _LAST_RESULT only ever holds data.
    if not candles_by_symbol_by_tf:
        return FetchResult(
            candles_by_symbol_by_tf={},
            closes_by_symbol={},
            universe=[],
            meta={
                "source": "exchange",
                "age_seconds": 0.0,
                "error": combined_error or "no OHLCV data returned",
                "symbol_count": 0,
                "elapsed_seconds": elapsed,
            },
        )

    result = FetchResult(
        candles_by_symbol_by_tf=candles_by_symbol_by_tf,
        closes_by_symbol=closes_by_symbol,
        universe=universe,
        meta={
            "source": "exchange",
            "age_seconds": 0.0,
            "error": combined_error,
            "symbol_count": len(candles_by_symbol_by_tf),
            "elapsed_seconds": elapsed,
        },
    )
    _LAST_RESULT = result
    _LAST_FETCH_MONO = time.monotonic()
    return result
