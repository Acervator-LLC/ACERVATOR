"""One Stone Tablet retrieved or updated through ``back_test.download_missing``.

``retrieval_span`` names the candles a press asks for: from ``YTD_START_MS``
when no tablet holds the market, or from the entry's last candle when one does,
up to ``closed_until_ms``, the newest closed candle. ``retrieve`` walks that
span one adapter chunk at a time, each chunk one ``download_missing`` call over
a ``StoneTabletsRegistry`` on the tablet root, and stops at the first
``FillReport`` carrying an error, so a refusing venue costs one chunk and not
the whole span. ``RetrievalOutcome`` is what the tab writes on the Activity
Log when the walk ends. ``retrieval_cost`` states, before a press, what one
walk over a span would ask the venue for: the candles ``missing_ranges`` reports,
the chunks and venue calls ``call_count`` derives from the adapter's
``chunk_limit`` and ``PAGE_ROWS``, and the bytes at ``BYTES_PER_CANDLE``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..trading.stone_tablets.fetcher import STEP_5M_MS, YTD_START_MS
from ..trading.stone_tablets.registry import NATIVE_TIMEFRAME, StoneTabletsRegistry
from .back_test import adapter_for, download_missing
from .read_only_connector import PAGE_ROWS

#: Every retrieval walks and writes this timeframe; the registry stores no other.
TIMEFRAME = NATIVE_TIMEFRAME

#: Bytes one stored ``TIMEFRAME`` candle takes on disk, measured on
#: ``BTC_5m_2026_coinbase.json``: 3,851,966 bytes over 61,200 candles.
BYTES_PER_CANDLE = 63

NO_ADAPTER_FORMAT = "no adapter for exchange {exchange_id!r}"


@dataclass(frozen=True)
class RetrievalCost:
    """What one walk over ``[since_ms, until_ms]`` would ask the venue for:
    the ``candles`` the registry does not hold, in ``chunks`` of the adapter's
    ``chunk_limit`` and ``calls`` pages of ``PAGE_ROWS``."""

    asset: str
    exchange_id: str
    since_ms: int
    until_ms: int
    candles: int
    chunks: int
    calls: int

    @property
    def bytes(self) -> int:
        """``candles`` at ``BYTES_PER_CANDLE``."""
        return self.candles * BYTES_PER_CANDLE

    @property
    def needed(self) -> bool:
        """True when the registry lacks at least one candle of the span."""
        return self.candles > 0


def venue_pages(call: Any, page_rows: int = PAGE_ROWS) -> int:
    """The pages of ``page_rows`` one ``VenueCall`` sent the venue: every page
    of ``limit`` when it answered, else the pages its ``rows`` filled and the
    one that raised."""
    if getattr(call, "error", ""):
        return len(getattr(call, "rows", None) or []) // page_rows + 1
    return -(-int(getattr(call, "limit", 0) or 0) // page_rows)


def call_count(candles: int, chunk_limit: int, page_rows: int) -> tuple[int, int]:
    """``(chunks, calls)`` to fetch ``candles``: chunks of ``chunk_limit``
    rows, each answered in pages of ``page_rows``, the last chunk partial."""
    if candles <= 0 or chunk_limit <= 0 or page_rows <= 0:
        return 0, 0
    chunks = -(-candles // chunk_limit)
    whole = chunks - 1
    last = candles - whole * chunk_limit
    calls = whole * (-(-chunk_limit // page_rows)) + (-(-last // page_rows))
    return chunks, calls


def retrieval_cost(
    registry: StoneTabletsRegistry,
    asset: str,
    exchange_id: str,
    since_ms: int,
    until_ms: int,
) -> RetrievalCost:
    """The ``RetrievalCost`` of ``asset`` on ``exchange_id`` over
    ``[since_ms, until_ms]``: every ``TIMEFRAME`` step ``registry.missing_ranges``
    reports, through ``adapter_for``'s ``chunk_limit`` and ``PAGE_ROWS``; an
    exchange with no adapter costs nothing and is refused at the press."""
    asset_u = str(asset).upper()
    candles = 0
    if int(until_ms) >= int(since_ms):
        gaps = registry.missing_ranges(
            asset_u, int(since_ms), int(until_ms), TIMEFRAME, exchange_id=exchange_id
        )
        candles = sum((int(end) - int(start)) // STEP_5M_MS + 1 for start, end in gaps)
    adapter = adapter_for(exchange_id, None)
    chunk_limit = int(getattr(adapter, "chunk_limit", 0) or 0)
    chunks, calls = call_count(candles, chunk_limit, PAGE_ROWS)
    return RetrievalCost(
        asset=asset_u,
        exchange_id=str(exchange_id),
        since_ms=int(since_ms),
        until_ms=int(until_ms),
        candles=candles,
        chunks=chunks,
        calls=calls,
    )


@dataclass
class RetrievalOutcome:
    """What one walk did: the span asked, the chunks walked, the candles the
    registry appended, and the first venue error when the walk stopped."""

    asset: str
    exchange_id: str
    since_ms: int
    until_ms: int
    chunks: int = 0
    chunks_ok: int = 0
    candles_appended: int = 0
    error: str = ""
    reports: list = field(default_factory=list)

    @property
    def refused(self) -> bool:
        """True when the walk stopped on a venue error."""
        return bool(self.error)


def closed_until_ms(now_ms: Optional[int] = None) -> int:
    """The open time of the newest closed ``TIMEFRAME`` candle at ``now_ms``,
    epoch milliseconds; the candle now forming is left out."""
    now = int(time.time() * 1000) if now_ms is None else int(now_ms)
    return (now // STEP_5M_MS) * STEP_5M_MS - STEP_5M_MS


def retrieval_span(entry: Any, now_ms: Optional[int] = None) -> tuple[int, int]:
    """``(since_ms, until_ms)`` for one press: ``YTD_START_MS`` with no
    ``entry``, else one step past ``entry.last_ts_ms``; up to
    ``closed_until_ms``."""
    until = closed_until_ms(now_ms)
    if entry is None:
        return int(YTD_START_MS), until
    return int(entry.last_ts_ms) + STEP_5M_MS, until


async def retrieve(
    root: Any,
    connector: Any,
    asset: str,
    exchange_id: str,
    since_ms: int,
    until_ms: int,
    on_report: Optional[Callable[[Any], None]] = None,
) -> RetrievalOutcome:
    """Walk ``since_ms`` to ``until_ms`` for ``asset`` on ``exchange_id`` in
    chunks of the adapter's ``chunk_span_ms``, each through
    ``download_missing`` over a registry on ``root``.

    Each chunk's ``FillReport`` reaches ``on_report``; the walk stops at the
    first report carrying an error, and the outcome names it.
    """
    outcome = RetrievalOutcome(
        asset=str(asset).upper(),
        exchange_id=str(exchange_id),
        since_ms=int(since_ms),
        until_ms=int(until_ms),
    )
    adapter = adapter_for(exchange_id, connector)
    if adapter is None:
        outcome.error = NO_ADAPTER_FORMAT.format(exchange_id=exchange_id)
        return outcome
    registry = StoneTabletsRegistry(root)
    span = int(adapter.chunk_span_ms)
    cursor = int(since_ms)
    while cursor <= int(until_ms):
        chunk_end = min(cursor + span - STEP_5M_MS, int(until_ms))
        reports = await download_missing(
            [(outcome.asset, outcome.exchange_id)],
            connector,
            cursor,
            chunk_end,
            registry=registry,
        )
        outcome.chunks += 1
        for report in reports:
            outcome.reports.append(report)
            outcome.chunks_ok += int(report.chunks_ok)
            outcome.candles_appended += int(report.candles_appended)
            if on_report is not None:
                on_report(report)
            if report.errors:
                outcome.error = str(report.errors[0])
        if outcome.error:
            break
        cursor = chunk_end + STEP_5M_MS
    return outcome


__all__ = [
    "BYTES_PER_CANDLE",
    "NO_ADAPTER_FORMAT",
    "TIMEFRAME",
    "RetrievalCost",
    "RetrievalOutcome",
    "call_count",
    "closed_until_ms",
    "retrieval_cost",
    "retrieval_span",
    "retrieve",
    "venue_pages",
]
