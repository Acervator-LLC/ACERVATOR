"""candle_series.py — OHLCV window container + cursor.

Backing store for the Fleet-Replay ``FleetSimExchange``. Each series
holds one symbol's chronological candle sequence and a "current cursor"
index — ``get_ticker`` / ``get_ohlcv`` operate on the cursor's slice of
the series so bot ticks see prices as of a specific point in the
replay timeline (never future data — replay is causal).

Row shape follows the ccxt OHLCV convention:
    [timestamp_ms, open, high, low, close, volume]

Isolated pure module — no Qt, no exchange, no live-side coupling.

sadp: R28 SSS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass
class CandleSeries:
    """One symbol's OHLCV history with a replay cursor.

    The cursor starts at 0 (first candle) and advances via ``step()``.
    ``get_current()`` returns the candle at the cursor;
    ``get_history(limit)`` returns the last N candles up to and including
    the cursor (never future).

    All timestamps are unix milliseconds (matches ccxt output +
    NuclearSimExchange's ``_candle_to_ohlcv_row`` convention).
    """

    symbol: str
    rows: list[list[float]] = field(default_factory=list)
    cursor: int = 0

    def __post_init__(self) -> None:
        if not self.rows:
            return
        # Enforce chronological order so cursor semantics are stable.
        # Ties (equal ts) are allowed and kept in input order.
        self.rows = sorted(self.rows, key=lambda r: r[0])

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def length(self) -> int:
        return len(self.rows)

    @property
    def at_end(self) -> bool:
        return self.cursor >= len(self.rows) - 1

    def reset(self) -> None:
        self.cursor = 0

    def set_cursor(self, cursor: int) -> None:
        if len(self.rows) == 0:
            self.cursor = 0
            return
        self.cursor = max(0, min(len(self.rows) - 1, int(cursor)))

    def step(self) -> bool:
        """Advance cursor by one candle. Returns False when already at
        the last candle (replay done)."""
        if self.at_end:
            return False
        self.cursor += 1
        return True

    def step_to_ts(self, target_ts_ms: int) -> bool:
        """v3.24.3 (master-clock) — move cursor to the candle whose
        timestamp is <= target_ts_ms. Returns True if the cursor
        advanced (or is already at the correct spot with a valid
        candle at or before the target), False if target is before
        the first candle of this series or the series is empty.

        Bisects so cost is O(log N) even on 45k-candle tablets.
        """
        if len(self.rows) == 0:
            return False
        target = int(target_ts_ms)
        # If target is before this series's first candle, we can't
        # advance to a legitimate cursor — leave cursor at 0 but
        # signal "not advanced yet"
        if target < int(self.rows[0][0]):
            return False
        # Binary search for the rightmost index with ts <= target
        lo, hi = 0, len(self.rows) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if int(self.rows[mid][0]) <= target:
                lo = mid
            else:
                hi = mid - 1
        self.cursor = lo
        return True

    def get_current(self) -> Optional[list[float]]:
        """Return the candle at the current cursor, or None if empty."""
        if len(self.rows) == 0:
            return None
        return list(self.rows[self.cursor])

    def get_history(self, limit: int = 100) -> list[list[float]]:
        """Return up to ``limit`` candles ending at the cursor. Never
        exposes future candles (causal replay guarantee)."""
        if len(self.rows) == 0 or limit <= 0:
            return []
        end = self.cursor + 1
        start = max(0, end - int(limit))
        return [list(r) for r in self.rows[start:end]]

    def iter_ts(self) -> Iterator[int]:
        """Tablet timestamps, unaltered. See the note in
        `build_candle_series_from_rows` — these are exact int ms
        addresses, not measurements."""
        for r in self.rows:
            yield int(r[0])


def build_candle_series_from_rows(
    symbol: str,
    rows: list[list[float]],
) -> CandleSeries:
    """Construct a series with input validation.

    Rows with wrong length / non-numeric fields are silently dropped
    (per R28 fail-soft on ingest; the series is a display/replay
    surface, not a decision authority).
    """
    clean: list[list[float]] = []
    for r in rows or []:
        try:
            if len(r) < 6:
                continue
            # v3.24.83 — the TIMESTAMP STAYS AS THE TABLET WROTE IT.
            #
            # This floated the timestamp alongside the OHLCV values, as
            # though a timestamp were a price. It is not: Stone Tablets
            # store an exact int millisecond epoch on a fixed 5m grid
            # (verified — CHIP row 0 is 1776778500000, delta 300000ms),
            # and it is the ADDRESS a trade, a gate decision and a raw
            # indicator value are keyed by.
            #
            # Floating it forced every consumer that joins back to the
            # tablet to cast, and put a value that must be exact into a
            # type that only happens to be exact below 2^53.
            ts = int(r[0])
            o, h, l, c, v = (
                float(r[1]),
                float(r[2]),
                float(r[3]),
                float(r[4]),
                float(r[5]),
            )
            if ts <= 0 or c <= 0:
                continue
            clean.append([ts, o, h, l, c, v])
        except (TypeError, ValueError):
            continue
    return CandleSeries(symbol=symbol, rows=clean, cursor=0)


__all__ = ["CandleSeries", "build_candle_series_from_rows"]
