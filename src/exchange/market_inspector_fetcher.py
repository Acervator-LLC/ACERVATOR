"""fetch_htf_universe serves the Market Inspector its daily and weekly OHLC.

_pick_universe ranks each connector's bulk tickers by 24 h quote volume.
_fetch_one_symbol then pulls per-symbol OHLCV from connector.get_ohlcv on
the connector's single-worker executor. _resample_daily_to_weekly derives
the weekly series on the client when the venue does not list the 1w
timeframe. fetch_quote_volumes serves the 24 h quote volume per base symbol
those same ticker rows carry, over the same cache window.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from .market_pairs_scout import row_quote_volume_24h

logger = logging.getLogger("acervator.market_inspector_fetcher")


DEFAULT_TOP_N = 100
DEFAULT_MIN_REFRESH_S = 15 * 60
"""Default for the min_refresh_s argument of fetch_htf_universe, in seconds."""

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


def _resample_daily_to_weekly(daily: list[_Candle]) -> list[_Candle]:
    """Group daily into non-overlapping 7-bar windows, not calendar aligned.

    Returns an empty list when daily holds under 7 bars.
    """
    if len(daily) < 7:
        return []
    out: list[_Candle] = []
    for i in range(0, len(daily) - 6, 7):
        window = daily[i : i + 7]
        if len(window) < 7:
            break
        out.append(
            _Candle(
                timestamp=window[-1].timestamp,
                open=window[0].open,
                high=max(c.high for c in window),
                low=min(c.low for c in window),
                close=window[-1].close,
                volume=sum(c.volume for c in window),
            )
        )
    return out


def _exchange_supports_tf(connector, tf: str) -> bool:
    """Return True when connector._ex lists tf in its timeframes map."""
    try:
        ex = getattr(connector, "_ex", None)
        tfs = getattr(ex, "timeframes", None) or {}
        return tf in tfs
    except Exception as _tf_exc:  # noqa: BLE001 - defensive probe
        logger.debug("timeframe probe failed: %s", _tf_exc)
        return False


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
        weekly = _resample_daily_to_weekly(daily)
        if len(weekly) >= 20:
            tf_map["1w"] = weekly
    return tf_map


async def fetch_symbol_timeframe(
    exchange_connectors: dict,
    symbol: str,
    timeframe: str,
    bars: int = DAILY_BARS,
) -> list:
    """Fetch bars candles for one base symbol on one timeframe, now.

    Asks each connector in exchange_connectors for symbol against every quote
    in DEFAULT_QUOTES and answers the first pair that returns rows, so a
    caller reaches the market through the connectors the Market Inspector
    already holds rather than opening a second route to a venue.
    """
    base = str(symbol).strip().upper()
    if not base or not exchange_connectors:
        return []
    for eid, connector in exchange_connectors.items():
        for quote in DEFAULT_QUOTES:
            pair = f"{base}/{quote}"
            try:
                rows = await connector.get_ohlcv(pair, str(timeframe), int(bars))
            except Exception as _exc:  # noqa: BLE001 - per-pair best-effort
                logger.debug("OHLCV fetch failed on %s %s: %s", eid, pair, _exc)
                continue
            candles = _ohlcv_to_candles(rows)
            if candles:
                return candles
    return []


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
