"""``StoneTabletsRegistry`` — the in-process index over the stone tablet archive.

``_load_from_manifest`` reads MANIFEST into ``_entries`` at construction and
``_tablet`` loads candle bodies on demand. ``ingest_candles`` appends candles
and rewrites MANIFEST. ``get_candles`` serves ``NATIVE_TIMEFRAME`` directly and
sends every other timeframe through ``_rollup``.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .storage import (
    STONE_TABLETS_DIR,
    Tablet,
    TabletEntry,
    ensure_root,
    entry_from_tablet,
    read_manifest,
    read_tablet,
    tablet_path,
    write_manifest,
    write_tablet,
)

logger = logging.getLogger("acervator.stone_tablets.registry")

_BODY_CACHE_MAX = 64
"""Most tablet bodies ``_evict_if_needed`` leaves resident in ``_tablets``."""

NATIVE_TIMEFRAME: str = "5m"
"""Timeframe every tablet stores; ``_rollup`` derives all the others."""

_TF_SECONDS: dict[str, int] = {
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14_400,
    "6h": 21_600,
    "12h": 43_200,
    "1d": 86_400,
}

SUPPORTED_TIMEFRAMES: tuple[str, ...] = tuple(_TF_SECONDS.keys())


def _rollup_factor(tf: str) -> int:
    """Return the number of 5m candles that roll up into one `tf` candle."""
    if tf not in _TF_SECONDS:
        raise ValueError(
            f"unsupported timeframe {tf!r}; supported: " f"{SUPPORTED_TIMEFRAMES}"
        )
    return _TF_SECONDS[tf] // _TF_SECONDS[NATIVE_TIMEFRAME]


@dataclass
class CoverageSummary:
    """One row per (asset, ``exchange_id``) pair, built by ``coverage_summary``."""

    asset: str
    exchange_id: str
    tablet_count: int
    total_candles: int
    first_ts_ms: int
    last_ts_ms: int
    years: list[int] = field(default_factory=list)


class WindowStatus:
    """Coverage verdicts ``check_window_availability`` returns for a window."""

    FULL = "full"  # data spans entire requested window
    LATE_LISTING = "late_listing"  # tablet begins AFTER requested since_ms
    STALE = "stale"  # tablet ends BEFORE requested until_ms
    LATE_AND_STALE = "late_and_stale"  # both edges outside coverage
    EMPTY = "empty"  # no tablet at all


@dataclass
class AvailabilityInfo:
    """Listing and coverage extents for one (asset, ``exchange_id``) pair.

    ``get_asset_availability`` builds it from MANIFEST rows and
    ``listing_notice`` renders ``listed_at_iso`` for display.
    """

    asset: str
    exchange_id: str
    listed_at_ms: int  # first candle in tablet (0 if none)
    last_ts_ms: int  # last candle in tablet (0 if none)
    total_candles: int
    tablet_count: int

    @property
    def listed_at_iso(self) -> str:
        if self.listed_at_ms <= 0:
            return ""
        return datetime.fromtimestamp(
            self.listed_at_ms / 1000.0, tz=timezone.utc
        ).strftime("%Y-%m-%d")

    def is_listed_before(self, ts_ms: int) -> bool:
        """True when ``listed_at_ms`` is positive and at or before ``ts_ms``."""
        return self.listed_at_ms > 0 and self.listed_at_ms <= ts_ms

    def listing_notice(self, exchange_display: str = "Coinbase") -> str:
        """One line naming ``asset`` and ``listed_at_iso``, or reporting no data."""
        if self.listed_at_ms <= 0:
            return f"{self.asset}: no data in Stone Tablets on " f"{exchange_display}."
        return (
            f"{self.asset}: listed on {exchange_display} "
            f"{self.listed_at_iso} — no prior data exists."
        )


class StoneTabletsRegistry:
    """Index over the on-disk tablets, shared through ``get_registry``.

    ``_lock`` guards every read and mutation, ``_entries`` holds the MANIFEST
    metadata, and ``_tablets`` caches at most ``_BODY_CACHE_MAX`` candle bodies.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = root or STONE_TABLETS_DIR
        ensure_root(self._root)
        self._lock = threading.RLock()
        # Key order is (asset, exchange_id, timeframe, year).
        self._tablets: dict[tuple[str, str, str, int], Tablet] = {}
        self._entries: dict[tuple[str, str, str, int], TabletEntry] = {}
        # Key order is (asset, exchange_id); values are NATIVE_TIMEFRAME years.
        self._assets: dict[tuple[str, str], set[int]] = {}
        self._lru: list[tuple[str, str, str, int]] = []
        self._load_from_manifest()

    def _load_from_manifest(self) -> None:
        """Index every MANIFEST row into ``_entries`` and ``_assets``.

        A row whose tablet file is gone is logged and skipped, and no candle
        body is read here.
        """
        entries = read_manifest(self._root)
        missing = 0
        for e in entries:
            path = tablet_path(
                e.asset, e.timeframe, e.year, root=self._root, exchange_id=e.exchange_id
            )
            if not path.exists():
                logger.warning(
                    "stone_tablets: MANIFEST references %s but "
                    "file is missing — skipping",
                    path.name,
                )
                missing += 1
                continue
            key = (e.asset.upper(), e.exchange_id, e.timeframe, e.year)
            self._entries[key] = e
            if e.timeframe == NATIVE_TIMEFRAME:
                self._assets.setdefault((e.asset.upper(), e.exchange_id), set()).add(
                    e.year
                )
        logger.info(
            "stone_tablets: indexed %d tablet(s) covering %d "
            "(asset, exchange) pair(s); bodies load on demand%s",
            len(self._entries),
            len(self._assets),
            f"; {missing} manifest row(s) skipped" if missing else "",
        )

    def _tablet(self, key: tuple[str, str, str, int]) -> Optional[Tablet]:
        """Return the tablet body for ``key``, loading it into ``_tablets`` once.

        Caller must hold ``_lock``; an unreadable file drops the ``_entries``
        row and returns None.
        """
        tab = self._tablets.get(key)
        if tab is not None:
            self._touch(key)
            return tab
        entry = self._entries.get(key)
        if entry is None:
            return None
        path = tablet_path(
            entry.asset,
            entry.timeframe,
            entry.year,
            root=self._root,
            exchange_id=entry.exchange_id,
        )
        tab = read_tablet(path)
        if tab is None:
            logger.warning(
                "stone_tablets: %s is unreadable or corrupt — " "treating as absent",
                path.name,
            )
            self._entries.pop(key, None)
            return None
        self._tablets[key] = tab
        self._touch(key)
        self._evict_if_needed()
        return tab

    def _touch(self, key: tuple[str, str, str, int]) -> None:
        try:
            self._lru.remove(key)
        except ValueError:
            pass
        self._lru.append(key)

    def _evict_if_needed(self) -> None:
        """Drop the oldest ``_lru`` keys until ``_tablets`` fits ``_BODY_CACHE_MAX``."""
        while len(self._tablets) > _BODY_CACHE_MAX:
            oldest = self._lru.pop(0)
            self._tablets.pop(oldest, None)

    def _keys_for(
        self,
        asset_u: str,
        exchange_id: str,
        timeframe: str = NATIVE_TIMEFRAME,
    ) -> list[tuple[str, str, str, int]]:
        """Return the ``_entries`` keys matching ``asset_u``, ``exchange_id``
        and ``timeframe``, loading no tablet body."""
        return [
            k
            for k in self._entries
            if k[0] == asset_u and k[1] == exchange_id and k[2] == timeframe
        ]

    def _persist_manifest(self) -> None:
        """Write MANIFEST from ``_entries``, sorted by asset, timeframe and year.

        Each row reuses the checksum already stored on its ``TabletEntry``.
        """
        entries = sorted(
            self._entries.values(), key=lambda e: (e.asset, e.timeframe, e.year)
        )
        write_manifest(entries, root=self._root)

    def has_coverage(
        self,
        asset: str,
        since_ms: int,
        until_ms: int,
        timeframe: str = NATIVE_TIMEFRAME,
        exchange_id: str = "coinbase",
    ) -> bool:
        """True when ``_assets`` spans every year of the window and
        ``_native_ts_bounds`` encloses it; interior gaps are not checked, so
        ``missing_ranges`` still reports holes ``has_coverage`` accepts.

        ``timeframe`` is not read here.
        """
        with self._lock:
            asset_u = asset.upper()
            years = self._assets.get((asset_u, exchange_id), set())
            if not years:
                return False
            since_dt = datetime.fromtimestamp(since_ms / 1000.0, tz=timezone.utc)
            until_dt = datetime.fromtimestamp(until_ms / 1000.0, tz=timezone.utc)
            spans = set(range(since_dt.year, until_dt.year + 1))
            if not spans.issubset(years):
                return False
            first, last = self._native_ts_bounds(asset_u, exchange_id)
            if first is None or last is None:
                return False
            return first <= since_ms and last >= until_ms

    def _native_ts_bounds(
        self,
        asset_u: str,
        exchange_id: str,
    ) -> tuple[Optional[int], Optional[int]]:
        first: Optional[int] = None
        last: Optional[int] = None
        for key in self._keys_for(asset_u, exchange_id):
            e = self._entries[key]
            if e.candle_count <= 0:
                continue
            f, l = int(e.first_ts_ms), int(e.last_ts_ms)
            first = f if first is None or f < first else first
            last = l if last is None or l > last else last
        return first, last

    def missing_ranges(
        self,
        asset: str,
        since_ms: int,
        until_ms: int,
        timeframe: str = NATIVE_TIMEFRAME,
        exchange_id: str = "coinbase",
    ) -> list[tuple[int, int]]:
        """Return the ``[start_ms, end_ms]`` gaps in the window, stepped at
        ``NATIVE_TIMEFRAME``. An empty list means every step is covered."""
        with self._lock:
            asset_u = asset.upper()
            step_ms = _TF_SECONDS[NATIVE_TIMEFRAME] * 1000
            covered = self._native_ts_set(asset_u, exchange_id)
            gaps: list[tuple[int, int]] = []
            in_gap = False
            gap_start = 0
            ts = since_ms
            ts -= ts % step_ms
            while ts <= until_ms:
                if ts in covered:
                    if in_gap:
                        gaps.append((gap_start, ts - step_ms))
                        in_gap = False
                else:
                    if not in_gap:
                        gap_start = ts
                        in_gap = True
                ts += step_ms
            if in_gap:
                gaps.append((gap_start, until_ms))
            return gaps

    def _native_ts_set(
        self,
        asset_u: str,
        exchange_id: str,
    ) -> set[int]:
        out: set[int] = set()
        for key in self._keys_for(asset_u, exchange_id):
            tab = self._tablet(key)
            if tab is None:
                continue
            for row in tab.candles:
                out.add(int(row[0]))
        return out

    def get_candles(
        self,
        asset: str,
        since_ms: int,
        until_ms: int,
        timeframe: str = NATIVE_TIMEFRAME,
        exchange_id: str = "coinbase",
    ) -> list[list[float]]:
        """Return chronological ``[ts, o, h, l, c, v]`` rows inside the window.

        ``NATIVE_TIMEFRAME`` returns ``_native_slice`` unchanged; any other
        ``timeframe`` goes through ``_rollup``.
        """
        if timeframe not in _TF_SECONDS:
            raise ValueError(
                f"unsupported timeframe {timeframe!r}; "
                f"supported: {SUPPORTED_TIMEFRAMES}"
            )
        with self._lock:
            asset_u = asset.upper()
            native = self._native_slice(asset_u, exchange_id, since_ms, until_ms)
            if timeframe == NATIVE_TIMEFRAME:
                return native
            return _rollup(
                native, _rollup_factor(timeframe), _TF_SECONDS[timeframe] * 1000
            )

    def _native_slice(
        self,
        asset_u: str,
        exchange_id: str,
        since_ms: int,
        until_ms: int,
    ) -> list[list[float]]:
        out: list[list[float]] = []
        for key in self._keys_for(asset_u, exchange_id):
            tab = self._tablet(key)
            if tab is None:
                continue
            for row in tab.candles:
                ts = int(row[0])
                if since_ms <= ts <= until_ms:
                    out.append(list(row))
        out.sort(key=lambda r: r[0])
        return out

    def ingest_candles(
        self,
        asset: str,
        timeframe: str,
        rows: list[list[float]],
        source: str,
        exchange_id: str = "coinbase",
    ) -> int:
        """Append ``rows`` into the matching year tablets, dropping timestamps
        already present, then call ``write_tablet`` and ``_persist_manifest``.

        Returns the number of candles added and raises unless ``timeframe`` is
        ``NATIVE_TIMEFRAME``.
        """
        if timeframe != NATIVE_TIMEFRAME:
            raise ValueError(
                f"ingest requires native timeframe {NATIVE_TIMEFRAME!r}; "
                f"got {timeframe!r}. Rollup TFs are read-only."
            )
        if not rows:
            return 0
        with self._lock:
            asset_u = asset.upper()
            by_year: dict[int, list[list[float]]] = {}
            for row in rows:
                if len(row) < 6:
                    continue
                ts_ms = int(row[0])
                year = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).year
                by_year.setdefault(year, []).append(list(row))
            appended_total = 0
            fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for year, year_rows in by_year.items():
                key = (asset_u, exchange_id, timeframe, year)
                tab = self._tablet(key)
                if tab is None:
                    tab = Tablet(
                        asset=asset_u,
                        exchange_id=exchange_id,
                        timeframe=timeframe,
                        year=year,
                        source=source,
                        fetched_at=fetched_at,
                        candles=[],
                    )
                existing_ts = {int(r[0]) for r in tab.candles}
                new_rows = [r for r in year_rows if int(r[0]) not in existing_ts]
                if not new_rows:
                    continue
                merged = list(tab.candles) + new_rows
                merged.sort(key=lambda r: int(r[0]))
                tab.candles = merged
                tab.fetched_at = fetched_at
                self._tablets[key] = tab
                self._touch(key)
                # entry_from_tablet recomputes the checksum for this row alone.
                self._entries[key] = entry_from_tablet(tab)
                self._assets.setdefault((asset_u, exchange_id), set()).add(year)
                write_tablet(tab, root=self._root)
                appended_total += len(new_rows)
            if appended_total > 0:
                self._persist_manifest()
                self._evict_if_needed()
            return appended_total

    def coverage_summary(self) -> list[CoverageSummary]:
        """Return one ``CoverageSummary`` per (asset, exchange) pair in
        ``_assets``, totalled from ``_entries`` without loading a body."""
        with self._lock:
            out: list[CoverageSummary] = []
            for asset_u, eid in sorted(self._assets.keys()):
                first, last = self._native_ts_bounds(asset_u, eid)
                years = sorted(self._assets[(asset_u, eid)])
                keys = self._keys_for(asset_u, eid)
                total = sum(int(self._entries[k].candle_count) for k in keys)
                out.append(
                    CoverageSummary(
                        asset=asset_u,
                        exchange_id=eid,
                        tablet_count=len(keys),
                        total_candles=total,
                        first_ts_ms=first or 0,
                        last_ts_ms=last or 0,
                        years=years,
                    )
                )
            return out

    def get_asset_availability(
        self,
        asset: str,
        exchange_id: str = "coinbase",
    ) -> Optional[AvailabilityInfo]:
        """Return the ``AvailabilityInfo`` for this (asset, exchange) pair,
        folded from every ``_entries`` row the pair owns.

        None when ``_assets`` holds no entry for the pair.
        """
        with self._lock:
            asset_u = asset.upper()
            key = (asset_u, exchange_id)
            if key not in self._assets:
                return None
            keys = self._keys_for(asset_u, exchange_id)
            if not keys:
                return None
            rows = [self._entries[k] for k in keys]
            listed = min(
                (int(r.listed_at_ms) for r in rows if int(r.listed_at_ms) > 0),
                default=0,
            )
            last_ts = max(
                (int(r.last_ts_ms) for r in rows if int(r.last_ts_ms) > 0), default=0
            )
            total_candles = sum(int(r.candle_count) for r in rows)
            return AvailabilityInfo(
                asset=asset_u,
                exchange_id=exchange_id,
                listed_at_ms=listed,
                last_ts_ms=last_ts,
                total_candles=total_candles,
                tablet_count=len(rows),
            )

    def check_window_availability(
        self,
        asset: str,
        since_ms: int,
        until_ms: int,
        exchange_id: str = "coinbase",
        stale_threshold_ms: int = 86_400_000,
        listing_tolerance_ms: int = 86_400_000,
    ) -> str:
        """Return the ``WindowStatus`` for how ``get_asset_availability``
        covers [``since_ms``, ``until_ms``].

        ``stale_threshold_ms`` bounds how far ``last_ts_ms`` may trail
        ``until_ms``, and ``listing_tolerance_ms`` bounds how far
        ``listed_at_ms`` may follow ``since_ms``.
        """
        avail = self.get_asset_availability(asset, exchange_id)
        if avail is None or avail.total_candles == 0:
            return WindowStatus.EMPTY
        late = (avail.listed_at_ms - since_ms) > listing_tolerance_ms
        stale = (
            avail.last_ts_ms > 0 and (until_ms - avail.last_ts_ms) > stale_threshold_ms
        )
        if late and stale:
            return WindowStatus.LATE_AND_STALE
        if late:
            return WindowStatus.LATE_LISTING
        if stale:
            return WindowStatus.STALE
        return WindowStatus.FULL

    def stale_assets(
        self,
        now_ms: Optional[int] = None,
        threshold_days: int = 2,
        exchange_id: Optional[str] = None,
    ) -> list[str]:
        """Return the assets whose ``_native_ts_bounds`` end more than
        ``threshold_days`` before ``now_ms``.

        ``exchange_id`` restricts the scan to one exchange when given.
        """
        _now = (
            now_ms
            if now_ms is not None
            else int(datetime.now(timezone.utc).timestamp() * 1000)
        )
        threshold_ms = threshold_days * 86_400_000
        with self._lock:
            out: set[str] = set()
            for asset_u, eid in self._assets:
                if exchange_id is not None and eid != exchange_id:
                    continue
                _first, last = self._native_ts_bounds(asset_u, eid)
                if last is None or (_now - last) > threshold_ms:
                    out.add(asset_u)
            return sorted(out)


def _rollup(
    native_rows: list[list[float]],
    factor: int,
    bucket_ms: int,
) -> list[list[float]]:
    """Group ``native_rows`` into ``bucket_ms`` buckets and emit one OHLCV row
    per bucket, ordered by bucket start.

    A partial trailing bucket is emitted with the rows it holds.
    """
    if factor <= 1 or not native_rows:
        return list(native_rows)
    buckets: dict[int, list[list[float]]] = {}
    for row in native_rows:
        ts = int(row[0])
        bkey = (ts // bucket_ms) * bucket_ms
        buckets.setdefault(bkey, []).append(row)
    out: list[list[float]] = []
    for bkey in sorted(buckets.keys()):
        rows = buckets[bkey]
        opens = rows[0][1]
        closes = rows[-1][4]
        highs = max(r[2] for r in rows)
        lows = min(r[3] for r in rows)
        vols = sum(r[5] for r in rows)
        out.append([bkey, opens, highs, lows, closes, vols])
    return out


_REGISTRY: Optional[StoneTabletsRegistry] = None
_REGISTRY_LOCK = threading.Lock()


def get_registry() -> StoneTabletsRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        with _REGISTRY_LOCK:
            if _REGISTRY is None:
                _REGISTRY = StoneTabletsRegistry()
    return _REGISTRY


def reset_registry_for_tests() -> None:
    """Clear ``_REGISTRY``; the next ``get_registry`` call builds a new one."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        _REGISTRY = None


__all__ = [
    "NATIVE_TIMEFRAME",
    "SUPPORTED_TIMEFRAMES",
    "CoverageSummary",
    "StoneTabletsRegistry",
    "get_registry",
    "reset_registry_for_tests",
]
