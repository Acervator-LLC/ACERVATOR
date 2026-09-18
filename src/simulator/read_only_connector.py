"""The Simulator's one venue path: public candles, read only.

``ReadOnlyConnector`` answers ``get_ohlcv`` over ``CoinbasePublicCandles``,
the venue's public candle endpoint, which carries no key. ``READ_NAMES`` holds
that one name and ``__getattr__`` raises ``SendRefused`` for every other, so
an order, a cancellation, a balance read or a venue write cannot be expressed
through it. ``get_ohlcv`` pages the reader by ``PAGE_ROWS`` so ``limit`` rows
come back whole, and reports every venue call through ``on_call`` as a
``VenueCall`` the tab records on its API log.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..trading.stone_tablets.ra_fetcher import RA_CHUNK_DAYS, CoinbasePublicCandles
from ..trading.stone_tablets.registry import NATIVE_TIMEFRAME

#: Every name ``ReadOnlyConnector`` answers. ``__getattr__`` refuses the rest.
READ_NAMES = ("get_ohlcv",)

#: Rows one venue page answers; ``get_ohlcv`` asks again past it.
PAGE_ROWS = RA_CHUNK_DAYS

EXCHANGE_ID = "coinbase"

#: The endpoint path recorded for one call, the venue's own product spelling.
ENDPOINT_FORMAT = "/products/{product}/candles"


class SendRefused(AttributeError):
    """Raised when a name outside ``READ_NAMES`` is asked of ``ReadOnlyConnector``."""


@dataclass
class VenueCall:
    """One ``get_ohlcv`` call as ``on_call`` reports it: what was asked, what
    came back, how long it took, and the error when the venue refused."""

    symbol: str
    timeframe: str
    limit: int
    since_ms: int
    endpoint: str
    rows: list = field(default_factory=list)
    elapsed_ms: float = 0.0
    error: str = ""


def error_text(exc: BaseException) -> str:
    """``exc`` as one line: its class and its ``reason`` where a URL error
    carries one, else its own text."""
    reason = getattr(exc, "reason", None)
    return f"{type(exc).__name__}: {reason if reason is not None else exc}"


def product_of(symbol: str) -> str:
    """``BTC/USD`` as the venue spells it, ``BTC-USD``."""
    return str(symbol).replace("/", "-").upper()


class ReadOnlyConnector:
    """``get_ohlcv`` over the venue's public candles, and nothing else."""

    def __init__(
        self,
        reader: Optional[CoinbasePublicCandles] = None,
        on_call: Optional[Callable[[VenueCall], None]] = None,
    ) -> None:
        """Read through ``reader``, or a fresh ``CoinbasePublicCandles`` when it
        is None; hand every call to ``on_call`` when one is given."""
        self._reader = reader if reader is not None else CoinbasePublicCandles()
        self._on_call = on_call

    def _report(self, call: VenueCall) -> None:
        if self._on_call is not None:
            self._on_call(call)

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = NATIVE_TIMEFRAME,
        limit: int = PAGE_ROWS,
        since: Optional[int] = None,
    ) -> list[list[float]]:
        """``limit`` rows of ``[ts_ms, open, high, low, close, volume]`` from
        ``since`` in epoch milliseconds, oldest first, paged by ``PAGE_ROWS``.

        A venue refusal is reported through ``on_call`` and then raised.
        """
        step_ms = int(self._reader.GRANULARITY_S[timeframe]) * 1000
        call = VenueCall(
            symbol=str(symbol),
            timeframe=str(timeframe),
            limit=int(limit),
            since_ms=int(since or 0),
            endpoint=ENDPOINT_FORMAT.format(product=product_of(symbol)),
        )
        started = time.monotonic()
        rows: list[list[float]] = []
        cursor = None if since is None else int(since)
        remaining = int(limit)
        try:
            while remaining > 0:
                asked = min(remaining, PAGE_ROWS)
                page = await self._reader.get_ohlcv(
                    symbol, timeframe, limit=asked, since=cursor
                )
                rows.extend([list(row) for row in page])
                remaining -= asked
                if cursor is None:
                    break
                cursor += asked * step_ms
        except Exception as exc:
            call.elapsed_ms = (time.monotonic() - started) * 1000.0
            call.rows = rows
            call.error = error_text(exc)
            self._report(call)
            raise
        call.elapsed_ms = (time.monotonic() - started) * 1000.0
        call.rows = rows
        self._report(call)
        return rows

    def __getattr__(self, name: str) -> Any:
        """Refuse every name outside ``READ_NAMES``."""
        raise SendRefused(
            f"ReadOnlyConnector answers {READ_NAMES} and cannot {name!r}. "
            "The Simulator receives and asks; it sends nothing."
        )


__all__ = [
    "ENDPOINT_FORMAT",
    "EXCHANGE_ID",
    "PAGE_ROWS",
    "READ_NAMES",
    "ReadOnlyConnector",
    "SendRefused",
    "VenueCall",
    "error_text",
    "product_of",
]
