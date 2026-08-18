"""
timeframes.py — Per-exchange timeframe availability map (v3.15.61)
==================================================================
Operator directive 2026-04-26:
  "TF choices for given exchanges should change based on availability.
   For example, 4h should be disabled for Coinbase."

Coinbase Advanced Trade only ships eight candle granularities through
its public API (ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, THIRTY_MINUTE,
ONE_HOUR, TWO_HOUR, SIX_HOUR, ONE_DAY). 4h, 12h, 1w are NOT available
— if the bot requests them, ccxt either rejects the call or silently
returns an empty candle array, the TA engine sees < 30 candles and
holds. The result is "phantom 4h does nothing on Coinbase" — silent
failure that operators have to debug.

This module exposes one function — ``available_timeframes(exchange_id)``
— that the GUI can call to filter dropdown items so the operator
cannot pick an unsupported TF in the first place.

Default (unknown exchange) returns the union of all rooms in the
codebase's ``TIMEFRAME_ORDER``; we are permissive when we don't have
a confident allowlist.
"""

from __future__ import annotations

from typing import Iterable

# Master ordered list — matches phantom_balance.TIMEFRAME_ORDER
ALL_TIMEFRAMES: tuple[str, ...] = (
    "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w",
)

# Per-exchange explicit allow-lists. Keys are normalized to lowercase
# (use ``available_timeframes`` rather than reading this directly).
_AVAILABILITY: dict[str, frozenset[str]] = {
    # Coinbase Advanced Trade — fixed eight granularities. NOT 4h.
    # Source: Coinbase Advanced Trade API CandleGranularity enum.
    "coinbase":      frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "6h", "1d"}),
    "coinbasepro":   frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "6h", "1d"}),
    "cb":            frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "6h", "1d"}),

    # Binance / Binance.US — supports 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h,
    # 6h, 8h, 12h, 1d, 3d, 1w, 1M. Acervator only uses the standard set.
    "binance":       frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "4h",
                                "6h", "12h", "1d", "1w"}),
    "binanceus":     frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "4h",
                                "6h", "12h", "1d", "1w"}),

    # Kraken — supports 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w (no 2h/6h/12h).
    "kraken":        frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}),

    # Kucoin — supports a similar superset to Binance.
    "kucoin":        frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "4h",
                                "6h", "12h", "1d", "1w"}),

    # Bybit, OKX — comprehensive coverage. Use full standard set.
    "bybit":         frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "4h",
                                "6h", "12h", "1d", "1w"}),
    "okx":           frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "4h",
                                "6h", "12h", "1d", "1w"}),
}


def available_timeframes(exchange_id: str | None) -> tuple[str, ...]:
    """Return the ordered tuple of timeframes the given exchange supports.

    Unknown exchange → the full ``ALL_TIMEFRAMES`` tuple (permissive
    fallback so we never wrongly hide a TF an exchange actually
    supports). Empty/None exchange → same fallback.
    """
    if not exchange_id:
        return ALL_TIMEFRAMES
    key = exchange_id.strip().lower()
    allow = _AVAILABILITY.get(key)
    if allow is None:
        return ALL_TIMEFRAMES
    return tuple(tf for tf in ALL_TIMEFRAMES if tf in allow)


def is_supported(exchange_id: str | None, timeframe: str) -> bool:
    """Quick check: is a single timeframe supported on this exchange?"""
    return timeframe in available_timeframes(exchange_id)


def filter_timeframes(
    exchange_id: str | None, requested: Iterable[str]
) -> list[str]:
    """Filter a list of requested timeframes down to the ones the
    exchange supports. Order-preserving."""
    allow = set(available_timeframes(exchange_id))
    return [tf for tf in requested if tf in allow]
