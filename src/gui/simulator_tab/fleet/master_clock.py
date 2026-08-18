"""master_clock.py — union-timestamp clock so every Stone Tablet
series ticks synchronously.

v3.24.3 fix for scaffolding-scan finding SC8. Prior
FleetSimExchange.step() advanced every series by ONE INDEX per
tick — but Stone Tablets from the migrated session-71 archive
have different lengths (BTC 45,598 vs SPK 32,950 vs ALLO 8,406
YTD candles) and different first-candle timestamps (BTC starts
2026-04-01 00:00Z, SPK starts 2026-04-01 00:20Z). Index-based
stepping produced desynchronized playback: BTC's bar at index 10
is 50 min after start, but SPK's bar at index 10 is 70 min after
start. Bots ticked on the same "candle index" saw prices from
DIFFERENT wall-clock times.

MasterClock fixes this by:
    1. Computing the UNION of all timestamps across all series
       at init time (sorted ascending).
    2. Exposing ``step()`` that advances to the next master
       timestamp.
    3. Exposing ``current_ts_ms()`` so the sim exchange can call
       ``series.step_to_ts(ts)`` on every series simultaneously,
       moving each cursor to the candle whose timestamp is
       <= master's current timestamp.

Consequences:
    * Bots tick synchronized to real wall-clock (5-min grid).
    * A series with no candle at the master's current ts holds
       its previous candle price (last-seen, no future data).
    * Total ticks = size of the union set (typical 34-tablet YTD
       replay ≈ 19,000 timestamps once April 1 → June 8 is fully
       covered; grows to ~35,000 once the June 8 → today gap is
       filled).

Sim ↔ Live parity guarantee: bot receives the same tick cadence
in sim as in live (both 5-min bars), so gate evaluation is
comparable candle-for-candle.

sadp: R28 SSS + R70 RCN
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


@dataclass
class MasterClock:
    """Union-timestamp clock across N CandleSeries.

    Construction:
        clock = MasterClock.from_series(series_iterable)
    Advance:
        while clock.step():
            ts = clock.current_ts_ms()
            for series in series_iterable:
                series.step_to_ts(ts)
    """

    timestamps: list[int] = field(default_factory=list)
    cursor: int = 0

    @classmethod
    def from_series(cls, series_iterable: Iterable) -> "MasterClock":
        """Build a clock whose timestamps are the sorted union of
        every provided series's timestamps. Empty series are skipped."""
        union: set[int] = set()
        for series in series_iterable:
            rows = getattr(series, "rows", None)
            if not rows:
                continue
            for row in rows:
                try:
                    union.add(int(row[0]))
                except (TypeError, ValueError, IndexError):
                    continue
        return cls(timestamps=sorted(union), cursor=0)

    def __len__(self) -> int:
        return len(self.timestamps)

    @property
    def total(self) -> int:
        return len(self.timestamps)

    @property
    def at_end(self) -> bool:
        return self.cursor >= len(self.timestamps) - 1

    def current_ts_ms(self) -> Optional[int]:
        """Timestamp at the current cursor, or None when empty."""
        if not self.timestamps:
            return None
        if self.cursor >= len(self.timestamps):
            return None
        return self.timestamps[self.cursor]

    def step(self) -> bool:
        """Advance cursor by one master timestamp. Returns False when
        already at the last timestamp (replay done)."""
        if self.at_end:
            return False
        self.cursor += 1
        return True

    def reset(self) -> None:
        self.cursor = 0


__all__ = ["MasterClock"]
