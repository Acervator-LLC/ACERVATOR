"""One Stone Tablet retrieved or updated through ``back_test.download_missing``.

``retrieval_span`` names the candles a press asks for: from ``YTD_START_MS``
when no tablet holds the market, or from the entry's last candle when one does,
up to ``closed_until_ms``, the newest closed candle. ``retrieve`` walks that
span one adapter chunk at a time, each chunk one ``download_missing`` call over
a ``StoneTabletsRegistry`` on the tablet root, and stops at the first
``FillReport`` carrying an error, so a refusing venue costs one chunk and not
the whole span. ``RetrievalOutcome`` is what the tab writes on the Activity
Log when the walk ends.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..trading.stone_tablets.fetcher import STEP_5M_MS, YTD_START_MS
from ..trading.stone_tablets.registry import NATIVE_TIMEFRAME, StoneTabletsRegistry
from .back_test import adapter_for, download_missing

#: Every retrieval walks and writes this timeframe; the registry stores no other.
TIMEFRAME = NATIVE_TIMEFRAME

NO_ADAPTER_FORMAT = "no adapter for exchange {exchange_id!r}"


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
    "NO_ADAPTER_FORMAT",
    "TIMEFRAME",
    "RetrievalOutcome",
    "closed_until_ms",
    "retrieval_span",
    "retrieve",
]
