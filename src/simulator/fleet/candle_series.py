"""OHLCV window with a replay cursor.

``CandleSeries`` holds one symbol's ``rows`` in ascending timestamp order,
each ``[timestamp_ms, open, high, low, close, volume]`` as ccxt returns them.
``get_current`` and ``get_history`` read at or before ``cursor``, never past
it. ``build_candle_series_from_rows`` drops malformed rows and keeps the
timestamp an ``int``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional


@dataclass
class CandleSeries:
    """One symbol's OHLCV history with a replay cursor.

    ``cursor`` starts at 0 and moves through ``step`` or ``step_to_ts``.
    ``rows`` carry unix-millisecond timestamps and are sorted on construction.
    """

    symbol: str
    rows: list[list[float]] = field(default_factory=list)
    cursor: int = 0

    def __post_init__(self) -> None:
        if not self.rows:
            return
        # ``sorted`` is stable: ``rows`` with equal timestamps keep input order.
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
        """Advance ``cursor`` by one row.

        Returns False when ``at_end`` is already True.
        """
        if self.at_end:
            return False
        self.cursor += 1
        return True

    def step_to_ts(self, target_ts_ms: int) -> bool:
        """Set ``cursor`` to the last row timestamped at or before ``target_ts_ms``.

        Bisects ``rows``, returning False and leaving ``cursor`` untouched when
        ``rows`` is empty or ``target_ts_ms`` precedes the first row.
        """
        if len(self.rows) == 0:
            return False
        target = int(target_ts_ms)
        if target < int(self.rows[0][0]):
            return False
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
        """Return a copy of the row at ``cursor``, None when ``rows`` is empty."""
        if len(self.rows) == 0:
            return None
        return list(self.rows[self.cursor])

    def get_history(self, limit: int = 100) -> list[list[float]]:
        """Return copies of up to ``limit`` rows ending at ``cursor``.

        Returns an empty list when ``rows`` is empty or ``limit`` is not
        positive.
        """
        if len(self.rows) == 0 or limit <= 0:
            return []
        end = self.cursor + 1
        start = max(0, end - int(limit))
        return [list(r) for r in self.rows[start:end]]

    def iter_ts(self) -> Iterator[int]:
        """Yield each row's timestamp from ``rows`` as an ``int``."""
        for r in self.rows:
            yield int(r[0])


def build_candle_series_from_rows(
    symbol: str,
    rows: list[list[float]],
) -> CandleSeries:
    """Build a ``CandleSeries`` from ``rows``, dropping malformed entries.

    A row is dropped when it has fewer than six fields, a non-numeric field, or
    a non-positive ``ts`` or ``c``; ``ts`` stays an ``int`` and ``o``, ``h``,
    ``l``, ``c`` and ``v`` become floats.
    """
    clean: list[list[float]] = []
    for r in rows or []:
        try:
            if len(r) < 6:
                continue
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
