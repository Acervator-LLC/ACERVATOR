"""The Paper Trader's data path: the venue's public market feed, read only.

``LiveFeedSource`` answers ``venue``, ``product_id``, ``granularity``,
``candles``, ``ticker`` and ``asked_at`` from the Coinbase Advanced Trade
public market endpoints, which carry no key and no signature. It holds no
credential and defines no write, and ``__getattr__`` raises ``SendRefused``
for every other name, so an order, a cancellation or a venue write cannot be
expressed through it.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from ..core.safe_url import SafeRequest, safe_urlopen

logger = logging.getLogger("acervator.paper.feed")

VENUE = "coinbase"

#: The venue's unauthenticated market root. Every path below hangs off it.
MARKET_BASE_URL = "https://api.coinbase.com/api/v3/brokerage/market/products"

REQUEST_TIMEOUT_S = 15.0
REQUEST_HEADERS = (("Accept", "application/json"),)

#: Every name ``LiveFeedSource`` answers. ``__getattr__`` refuses the rest.
READ_NAMES = (
    "venue",
    "product_id",
    "granularity",
    "candles",
    "ticker",
    "asked_at",
)

#: The venue's candle granularity for each timeframe the platform offers.
#: Coinbase ships these eight and no others.
GRANULARITY = {
    "1m": "ONE_MINUTE",
    "5m": "FIVE_MINUTE",
    "15m": "FIFTEEN_MINUTE",
    "30m": "THIRTY_MINUTE",
    "1h": "ONE_HOUR",
    "2h": "TWO_HOUR",
    "6h": "SIX_HOUR",
    "1d": "ONE_DAY",
}

DEFAULT_TIMEFRAME = "5m"

#: Seconds one bar of each timeframe covers, sizing the ``start`` stamp.
BAR_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "6h": 21600,
    "1d": 86400,
}

#: How many bars one ask covers. ``VotingEngine`` reads a 100-bar window.
WINDOW_CANDLES = 100

#: The venue caps one candle response at this many bars.
MAX_CANDLES = 350


class SendRefused(AttributeError):
    """Raised when a name outside ``READ_NAMES`` is asked of ``LiveFeedSource``."""


def product_id_for(symbol: str) -> str:
    """``symbol`` as the venue's product id, ``BTC/USD`` giving ``BTC-USD``."""
    return str(symbol or "").replace("/", "-").upper()


def granularity_for(timeframe: str) -> str:
    """The venue's ``GRANULARITY`` name for ``timeframe``, ``5m`` when unknown."""
    return GRANULARITY.get(str(timeframe or ""), GRANULARITY[DEFAULT_TIMEFRAME])


def bar_seconds(timeframe: str) -> int:
    """How many seconds one ``timeframe`` bar covers, 300 when unknown."""
    return BAR_SECONDS.get(str(timeframe or ""), BAR_SECONDS[DEFAULT_TIMEFRAME])


def candle_row(raw: dict) -> Optional[list[float]]:
    """One venue candle as ``[ts_ms, open, high, low, close, volume]``.

    A ``raw`` missing a field, or holding one that is not a number, gives None.
    """
    try:
        return [
            float(int(raw["start"]) * 1000),
            float(raw["open"]),
            float(raw["high"]),
            float(raw["low"]),
            float(raw["close"]),
            float(raw["volume"]),
        ]
    except (KeyError, TypeError, ValueError):
        return None


class LiveFeedSource:
    """The venue's public candles and last trade price, as plain rows."""

    def __init__(
        self, base_url: str = MARKET_BASE_URL, timeout_s: float = REQUEST_TIMEOUT_S
    ) -> None:
        """Read from ``base_url``, giving up on one ask after ``timeout_s``."""
        self._base_url = str(base_url)
        self._timeout_s = float(timeout_s)
        self._asked_at_ms = 0

    def venue(self) -> str:
        """The exchange id every row here comes from."""
        return VENUE

    def product_id(self, symbol: str) -> str:
        """``symbol`` as the venue's product id."""
        return product_id_for(symbol)

    def granularity(self, timeframe: str) -> str:
        """The venue's granularity name for ``timeframe``."""
        return granularity_for(timeframe)

    def asked_at(self) -> int:
        """Wall-clock milliseconds of the last answered ask, zero before one."""
        return self._asked_at_ms

    def _read(self, path: str) -> dict:
        """The JSON body ``path`` answers, empty when the ask fails."""
        request = SafeRequest(f"{self._base_url}/{path}")
        for name, value in REQUEST_HEADERS:
            request.add_header(name, value)
        try:
            with safe_urlopen(request, timeout=self._timeout_s) as answer:
                body = json.loads(answer.read().decode("utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("paper feed: %s refused the ask: %s", path, exc)
            return {}
        self._asked_at_ms = int(time.time() * 1000)
        return body if isinstance(body, dict) else {}

    def candles(
        self,
        symbol: str,
        timeframe: str = DEFAULT_TIMEFRAME,
        count: int = WINDOW_CANDLES,
    ) -> list[list[float]]:
        """The newest ``count`` bars of ``symbol`` at ``timeframe``, oldest first.

        An unreadable or empty answer gives an empty list.
        """
        bars = max(1, min(int(count), MAX_CANDLES))
        end_s = int(time.time())
        start_s = end_s - bar_seconds(timeframe) * bars
        body = self._read(
            f"{product_id_for(symbol)}/candles"
            f"?start={start_s}&end={end_s}"
            f"&granularity={granularity_for(timeframe)}&limit={bars}"
        )
        answered = [one for one in body.get("candles") or [] if isinstance(one, dict)]
        kept = [row for row in map(candle_row, answered) if row is not None]
        kept.sort(key=lambda row: row[0])
        return kept[-bars:]

    def ticker(self, symbol: str) -> Optional[float]:
        """``symbol``'s last public trade price, None when none is answered."""
        body = self._read(f"{product_id_for(symbol)}/ticker?limit=1")
        trades = body.get("trades") or []
        if not trades or not isinstance(trades[0], dict):
            return None
        try:
            return float(trades[0]["price"])
        except (KeyError, TypeError, ValueError):
            return None

    def __getattr__(self, name: str):
        """Refuse every name outside ``READ_NAMES``."""
        raise SendRefused(
            f"LiveFeedSource answers {READ_NAMES} and cannot {name!r}. "
            "The Paper Trader receives and asks; it sends nothing."
        )


__all__ = [
    "BAR_SECONDS",
    "GRANULARITY",
    "MARKET_BASE_URL",
    "MAX_CANDLES",
    "READ_NAMES",
    "VENUE",
    "WINDOW_CANDLES",
    "LiveFeedSource",
    "SendRefused",
    "bar_seconds",
    "candle_row",
    "granularity_for",
    "product_id_for",
]
