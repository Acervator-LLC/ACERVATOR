"""market_inspector_fetcher.py — Exchange-based HTF OHLC fetcher.

v3.23.38 retooled per operator directive 2026-07-27 ("Reconfigure it to
use active exchange APIs. We do not need to look anywhere we are not
farming or not already configured to farm."). CoinGecko was gated by
free-tier rate limits and only surfaced ~4 markets on live testing.

Sourcing strategy:
  Tier 1 — connected exchange bulk tickers (single call → filter to
           */base pairs, drop stablecoins, sort by 24 h volume).
  Tier 2 — per-symbol daily OHLCV via ``connector.get_ohlcv``.
  Tier 3 — per-symbol weekly OHLCV where the exchange supports the
           1 w timeframe; otherwise resample from daily on the client.

All exchange calls route through the connector's serialised executor
(MEM-220), so they compose safely with other CCXT traffic (bot ticks,
dashboard refreshes).

Universe cap: default 100 top-volume markets. Active-bot target
symbols are always included even if outside the top-100. Monthly is
deferred (365-day daily gives ~12 monthly bars, below the
20-period BB minimum).

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, Optional

logger = logging.getLogger("acervator.market_inspector_fetcher")


DEFAULT_TOP_N = 100
DEFAULT_MIN_REFRESH_S = 15 * 60           # 15 minutes
"""Minimum seconds between NETWORK fetches, unless the caller forces one.

This constant was declared on the first implementation and never read, so no
cadence was enforced and every Refresh hit the venue. `meta["source"]` and
`meta["age_seconds"]` were already carried for a cache path that did not
exist -- `source` was hardcoded "exchange" and `age_seconds` hardcoded 0.0.
This is that path.

WHY A CADENCE AT ALL: the Market Inspector scans the top-N universe across
every connected exchange. Paper and Live compete for the same API budget, so
an unbounded refresh here is taken out of their allowance.
"""

_LAST_RESULT: Optional["FetchResult"] = None
_LAST_FETCH_MONO: float = 0.0
"""Last successful NETWORK result and when it landed, on the monotonic clock.

Monotonic, not wall clock: a wall clock can step backwards and would then
report a negative age, which reads as "just fetched" and defeats the cadence.
"""
DAILY_BARS = 365
WEEKLY_BARS = 200

STABLECOIN_DENYLIST = {
    "USD", "USDT", "USDC", "DAI", "BUSD", "TUSD", "USDP", "USDD",
    "FRAX", "GUSD", "LUSD", "USDE", "USDS", "PYUSD", "FDUSD",
    "EUR", "GBP", "JPY", "CAD", "AUD", "CHF",
}
DEFAULT_QUOTES = ("USD", "USDC", "USDT")  # accept these as USD-equivalent


@dataclass
class _Candle:
    """Minimal OHLC candle used by the analyzer + tightening detector."""
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


# ---------------------------------------------------------------------
# Universe selection
# ---------------------------------------------------------------------

def _pick_universe(
    tickers: dict,
    top_n: int,
    active_symbols: set,
    accepted_quotes: Iterable[str] = DEFAULT_QUOTES,
) -> list[str]:
    """Filter a bulk tickers dict to top-N */base symbols by 24 h volume.

    Always keeps active bot targets even if they fall outside top-N.
    Returns fully-qualified CCXT symbol strings (e.g. ``"BTC/USD"``).
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
        # 24 h quote volume is the useful ranking signal
        vol = 0.0
        try:
            vol = float(
                tk.get("quoteVolume")
                or tk.get("baseVolume", 0)
                or 0)
        except (TypeError, ValueError):
            vol = 0.0
        scored.append((vol, base_u, sym))
    scored.sort(key=lambda t: -t[0])
    top = [sym for _v, _b, sym in scored[:top_n]]
    # Ensure every active-bot symbol is present.
    seen_bases = {sym.split("/", 1)[0].upper() for sym in top}
    for _v, base_u, sym in scored:
        if base_u in active_symbols and base_u not in seen_bases:
            top.append(sym)
            seen_bases.add(base_u)
    return top


# ---------------------------------------------------------------------
# OHLCV fetch + resample
# ---------------------------------------------------------------------

def _ohlcv_to_candles(rows: list) -> list[_Candle]:
    out: list[_Candle] = []
    for r in rows or []:
        if not (isinstance(r, (list, tuple)) and len(r) >= 5):
            continue
        try:
            out.append(_Candle(
                timestamp=int(r[0]) // 1000,
                open=float(r[1]),
                high=float(r[2]),
                low=float(r[3]),
                close=float(r[4]),
                volume=float(r[5]) if len(r) > 5 else 0.0,
            ))
        except (TypeError, ValueError):
            continue
    return out


def _resample_daily_to_weekly(daily: list[_Candle]) -> list[_Candle]:
    """7-day rolling chunks. Not calendar-aligned — fine for BB."""
    if len(daily) < 7:
        return []
    out: list[_Candle] = []
    for i in range(0, len(daily) - 6, 7):
        window = daily[i:i + 7]
        if len(window) < 7:
            break
        out.append(_Candle(
            timestamp=window[-1].timestamp,
            open=window[0].open,
            high=max(c.high for c in window),
            low=min(c.low for c in window),
            close=window[-1].close,
            volume=sum(c.volume for c in window)))
    return out


def _exchange_supports_tf(connector, tf: str) -> bool:
    """Best-effort check that the wrapped CCXT exchange lists ``tf``."""
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
    """Fetch daily (+ optional native weekly) OHLCV for one symbol.
    Returns ``{"1d": [_Candle], "1w": [_Candle]}`` or ``None``."""
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
            weekly_raw = await connector.get_ohlcv(
                symbol, "1w", WEEKLY_BARS)
            weekly = _ohlcv_to_candles(weekly_raw)
            if len(weekly) >= 20:
                tf_map["1w"] = weekly
        except Exception as _wexc:  # noqa: BLE001 - fallback to resample
            logger.debug(
                "weekly OHLCV fetch failed for %s (fallback resample): %s",
                symbol, _wexc)
    if "1w" not in tf_map:
        weekly = _resample_daily_to_weekly(daily)
        if len(weekly) >= 20:
            tf_map["1w"] = weekly
    return tf_map


# ---------------------------------------------------------------------
# FetchResult
# ---------------------------------------------------------------------

@dataclass
class FetchResult:
    candles_by_symbol_by_tf: dict  # {base_sym: {"1d": [_Candle], "1w": [_Candle]}}
    closes_by_symbol: dict         # {base_sym: [close_float, ...]}
    universe: list                 # list of full CCXT symbols scanned
    meta: dict                     # source, age_seconds, error, symbol_count


# ---------------------------------------------------------------------
# Public coroutine — invoked by the tab, scheduled onto the app loop
# ---------------------------------------------------------------------

async def fetch_htf_universe(
    exchange_connectors: dict,
    active_symbols: Optional[set] = None,
    top_n: int = DEFAULT_TOP_N,
    progress_cb=None,
    force_network: bool = False,
    min_refresh_s: float = DEFAULT_MIN_REFRESH_S,
) -> FetchResult:
    """Fetch HTF OHLC for the top-N (+ active) markets on any connected
    exchange.

    Iterates all connectors and unions their offerings. Per-symbol
    OHLCV goes through the connector's serialised executor (MEM-220).
    """
    active = set(active_symbols or set())
    if not exchange_connectors:
        return FetchResult(
            candles_by_symbol_by_tf={},
            closes_by_symbol={},
            universe=[],
            meta={
                "source": "no-exchange", "age_seconds": 0.0,
                "error": "no exchange connectors attached",
                "symbol_count": 0,
            })

    # ── CADENCE GATE ────────────────────────────────────────────────
    # Serve the last network result while it is younger than
    # `min_refresh_s`, unless the caller forces a network fetch. The
    # Refresh button forces; the periodic path does not.
    #
    # `age_seconds` is now a MEASUREMENT rather than a hardcoded 0.0, and
    # `source` says which path answered, so a reader can tell a cached
    # answer from a fresh one instead of assuming.
    global _LAST_RESULT, _LAST_FETCH_MONO
    if not force_network and _LAST_RESULT is not None:
        age = time.monotonic() - _LAST_FETCH_MONO
        if 0.0 <= age < float(min_refresh_s):
            cached = FetchResult(
                candles_by_symbol_by_tf=_LAST_RESULT.candles_by_symbol_by_tf,
                closes_by_symbol=_LAST_RESULT.closes_by_symbol,
                universe=_LAST_RESULT.universe,
                meta={**dict(_LAST_RESULT.meta or {}),
                      "source": "cache",
                      "age_seconds": round(age, 3)})
            if progress_cb:
                progress_cb(
                    f"Using cached scan ({int(age)}s old; "
                    f"refresh forces a new fetch)")
            return cached

    candles_by_symbol_by_tf: dict = {}
    closes_by_symbol: dict = {}
    universe: list = []
    fetch_start = time.time()
    combined_error: Optional[str] = None

    for eid, connector in exchange_connectors.items():
        try:
            tickers = await connector.get_all_tickers()
        except Exception as _tex:  # noqa: BLE001 - per-connector best-effort
            logger.warning(
                "tickers fetch failed on %s: %s", eid, _tex)
            combined_error = f"{eid}: {_tex}"
            continue
        sub_universe = _pick_universe(tickers, top_n, active)
        if not sub_universe:
            continue
        weekly_native = _exchange_supports_tf(connector, "1w")
        for i, symbol in enumerate(sub_universe):
            base_u = symbol.split("/", 1)[0].upper()
            if base_u in candles_by_symbol_by_tf:
                continue  # already covered by an earlier connector
            tf_map = await _fetch_one_symbol(
                connector, symbol, weekly_native)
            if tf_map is None:
                continue
            candles_by_symbol_by_tf[base_u] = tf_map
            closes_by_symbol[base_u] = [
                c.close for c in tf_map["1d"]]
            universe.append(symbol)
            if progress_cb is not None:
                try:
                    progress_cb(
                        f"[{eid}] fetched {i + 1}/{len(sub_universe)}: "
                        f"{base_u}")
                except Exception as _cb_exc:  # noqa: BLE001
                    # Progress reporting is best-effort and must never
                    # break a fetch, but swallowing it silently is the
                    # exact shape this project removes elsewhere: a
                    # callback that stops working looks identical to one
                    # that never fired. Record it at debug and move on.
                    logger.debug(
                        "market inspector progress callback failed: %s",
                        _cb_exc)

    elapsed = time.time() - fetch_start
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
            })

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
        })
    # Only a result WITH DATA becomes the cache. Caching an empty scan
    # would serve nothing for 15 minutes and look like a working feed.
    if candles_by_symbol_by_tf:
        _LAST_RESULT = result
        _LAST_FETCH_MONO = time.monotonic()
    return result
