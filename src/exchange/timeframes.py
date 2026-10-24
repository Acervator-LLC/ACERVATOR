"""
timeframes.py — Per-exchange timeframe availability map
=======================================================
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
a confident allowlist. Every id in ``SUPPORTED_EXCHANGES`` now has one,
so the fallback no longer covers a venue an operator can select.
"""

from __future__ import annotations

from typing import Iterable

# Master ordered list — matches phantom_balance.TIMEFRAME_ORDER
ALL_TIMEFRAMES: tuple[str, ...] = (
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "2h",
    "4h",
    "6h",
    "12h",
    "1d",
    "1w",
)

# Per-exchange explicit allow-lists. Keys are normalized to lowercase
# (use ``available_timeframes`` rather than reading this directly).
_AVAILABILITY: dict[str, frozenset[str]] = {
    # Coinbase Advanced Trade — fixed eight granularities. NOT 4h.
    # Source: Coinbase Advanced Trade API CandleGranularity enum.
    "coinbase": frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "6h", "1d"}),
    "coinbasepro": frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "6h", "1d"}),
    "cb": frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "6h", "1d"}),
    # Binance / Binance.US — supports 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h,
    # 6h, 8h, 12h, 1d, 3d, 1w, 1M. Acervator only uses the standard set.
    "binance": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
    ),
    "binanceus": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
    ),
    # Kraken — supports 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w (no 2h/6h/12h).
    "kraken": frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}),
    # Read from ccxt 4.5.85 `exchange.timeframes` after a public
    # `load_markets()`: kucoin publishes fourteen granularities and
    # ALL_TIMEFRAMES draws eleven of them, which is this row. The three it
    # leaves are 3m, 8h and 1M.
    "kucoin": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
    ),
    # Bybit, OKX — comprehensive coverage. Use full standard set.
    "bybit": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
    ),
    "okx": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
    ),
    # OKX US subclasses OKX in ccxt and publishes the same fourteen
    # granularities, eleven of which ALL_TIMEFRAMES draws.
    "okxus": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
    ),
    # Read from ccxt 4.5.76 `exchange.timeframes` after a public
    # `load_markets()`.
    "bitfinex": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "4h", "6h", "12h", "1d", "1w"}
    ),
    "bitget": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
    ),
    # Read from ccxt 4.5.85 `exchange.timeframes` after a public
    # `load_markets()`: bitstamp publishes twelve granularities and
    # ALL_TIMEFRAMES draws eleven of them, which is this row. The one it leaves
    # is 3m.
    "bitstamp": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
    ),
    # Read from ccxt 4.5.85 `exchange.timeframes` after a public
    # `load_markets()`: cryptocom publishes twelve granularities and
    # ALL_TIMEFRAMES draws ten of them, which is this row. The two it leaves are
    # 2w and 1M, and 2h is the one ALL_TIMEFRAMES holds that cryptocom does not
    # publish.
    "cryptocom": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "4h", "6h", "12h", "1d", "1w"}
    ),
    "gateio": frozenset({"1m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1w"}),
    "gemini": frozenset({"1m", "5m", "15m", "30m", "1h", "6h", "1d"}),
    "huobi": frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}),
    # Read from ccxt 4.5.85 ``options['timeframes']``, which mexc keys by market
    # kind. Its spot map publishes nine granularities and its swap map ten, the
    # swap's extra one being 8h. ALL_TIMEFRAMES draws eight of the nine both
    # maps share, which is this row, so one row serves a spot pair and a
    # perpetual alike. The one both publish and ALL_TIMEFRAMES leaves is 1M, and
    # 2h, 6h and 12h are the three ALL_TIMEFRAMES holds that mexc publishes on
    # neither map.
    "mexc": frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}),
    "poloniex": frozenset(
        {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"}
    ),
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


UNSERVED_TIMEFRAME_FORMAT = (
    "{exchange} does not serve the {chosen} candle. This picker now shows {used}."
)
"""The wording ``unserved_timeframe_notice`` fills in."""


def unserved_timeframe_notice(exchange_id: str | None, chosen: str, used: str) -> str:
    """The ``UNSERVED_TIMEFRAME_FORMAT`` sentence for a candle length
    ``exchange_id`` does not serve, naming ``chosen`` and ``used``.

    Empty where ``is_supported`` holds for ``chosen``, where ``exchange_id`` is
    unnamed, and where ``used`` equals ``chosen``.
    """
    name = (exchange_id or "").strip()
    if not name or not chosen or not used or chosen == used:
        return ""
    if is_supported(name, chosen):
        return ""
    return UNSERVED_TIMEFRAME_FORMAT.format(exchange=name, chosen=chosen, used=used)


def filter_timeframes(exchange_id: str | None, requested: Iterable[str]) -> list[str]:
    """Filter a list of requested timeframes down to the ones the
    exchange supports. Order-preserving."""
    allow = set(available_timeframes(exchange_id))
    return [tf for tf in requested if tf in allow]
