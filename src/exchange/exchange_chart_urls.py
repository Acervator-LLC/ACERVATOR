"""exchange_chart_urls.py — build a per-exchange price-chart URL for
a given trading symbol.

Operator directive 2026-07-28: clicking a symbol cell in the main
BotStatusTable should open the correct chart on that bot's exchange
in the operator's default browser. Table-driven so adding a new
exchange = adding one row.

Returns ``None`` when the exchange is unknown or the symbol shape
isn't parseable — the caller renders a non-clickable cell rather
than opening a broken link.

sadp: R28 SSS
"""

from __future__ import annotations

from typing import Callable, Optional

# Each entry: exchange_id (lowercase) -> URL builder taking
# (base, quote) already uppercased.
_URL_BUILDERS: dict[str, Callable[[str, str], str]] = {
    "coinbase": lambda b, q: (f"https://www.coinbase.com/advanced-trade/spot/{b}-{q}"),
    "coinbaseexchange": lambda b, q: (
        f"https://www.coinbase.com/advanced-trade/spot/{b}-{q}"
    ),
    "coinbasepro": lambda b, q: (
        f"https://www.coinbase.com/advanced-trade/spot/{b}-{q}"
    ),
    "kraken": lambda b, q: (
        f"https://pro.kraken.com/app/trade/{b.lower()}-{q.lower()}"
    ),
    "binance": lambda b, q: (f"https://www.binance.com/en/trade/{b}_{q}"),
    "binanceus": lambda b, q: (f"https://www.binance.us/en/trade/{b}_{q}"),
    "gemini": lambda b, q: (f"https://exchange.gemini.com/trade/{b}{q}"),
    "bitstamp": lambda b, q: (
        f"https://www.bitstamp.net/markets/{b.lower()}/{q.lower()}/"
    ),
    "kucoin": lambda b, q: (f"https://www.kucoin.com/trade/{b}-{q}"),
    "okx": lambda b, q: (f"https://www.okx.com/trade-spot/{b.lower()}-{q.lower()}"),
    "bybit": lambda b, q: (f"https://www.bybit.com/en/trade/spot/{b}/{q}"),
    "bitfinex": lambda b, q: (f"https://trading.bitfinex.com/t/{b}:{q}"),
    "gate": lambda b, q: (f"https://www.gate.io/trade/{b}_{q}"),
    "gateio": lambda b, q: (f"https://www.gate.io/trade/{b}_{q}"),
}


def chart_url(
    exchange_id: str,
    symbol: str,
) -> Optional[str]:
    """Return a chart URL string for ``symbol`` on ``exchange_id``,
    or ``None`` when the exchange isn't in the mapping or the symbol
    can't be split into base/quote.

    Args:
        exchange_id: connector id from bot config
            (e.g., "coinbase", "kraken"). Case-insensitive.
        symbol: trading pair like "BTC/USD" or "ETH-BTC".
    """
    if not exchange_id or not symbol:
        return None
    _eid = str(exchange_id).lower().strip()
    builder = _URL_BUILDERS.get(_eid)
    if builder is None:
        return None
    # Accept "/" or "-" as pair separator.
    for sep in ("/", "-", "_"):
        if sep in symbol:
            parts = symbol.split(sep, 1)
            if len(parts) == 2 and parts[0] and parts[1]:
                base = parts[0].upper().strip()
                quote = parts[1].upper().strip()
                try:
                    return builder(base, quote)
                except Exception:  # noqa: BLE001 - defensive
                    return None
    return None


def supported_exchanges() -> tuple[str, ...]:
    """Return the sorted tuple of exchange ids the module knows."""
    return tuple(sorted(_URL_BUILDERS.keys()))
