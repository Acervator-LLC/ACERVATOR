"""registry.py — StoneTabletsRegistry singleton.

Public API — the surface v3.23.98 fetcher + v3.23.99 sim replay
consume. Design:
`docs/audits/2026-08-01_stone_tablets_rebuild_design.md`.

Runtime state lives at `~/.acervator/stone_tablets/`. This module
NEVER fetches — that's the fetcher's job. This module reads MANIFEST
on init, holds tablets in memory, appends candles when ingested,
persists atomically.

sadp: R28 SSS + R70 RCN
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
"""Ceiling on resident tablet bodies.

The archive is 406 tablets / 7,230,993 candles and holding all of them
costs ~2.3 GB (each candle is a 6-element list of boxed floats, ~331
bytes). A 35-bot fleet replay touches ~35 tablets, so 64 covers real
workloads with headroom while stopping a 406-asset sweep from
re-accumulating the whole archive.
"""

# --------------------------------------------------------------------- #
# Timeframe support                                                      #
# --------------------------------------------------------------------- #

NATIVE_TIMEFRAME: str = "5m"
"""Everything is stored at 5m natively per operator directive
2026-08-01. Higher TFs are derived via rollup."""

_TF_SECONDS: dict[str, int] = {
    "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14_400,
    "6h": 21_600, "12h": 43_200, "1d": 86_400,
}

SUPPORTED_TIMEFRAMES: tuple[str, ...] = tuple(_TF_SECONDS.keys())


def _rollup_factor(tf: str) -> int:
    """Return the number of 5m candles that roll up into one `tf` candle."""
    if tf not in _TF_SECONDS:
        raise ValueError(
            f"unsupported timeframe {tf!r}; supported: "
            f"{SUPPORTED_TIMEFRAMES}")
    return _TF_SECONDS[tf] // _TF_SECONDS[NATIVE_TIMEFRAME]


# --------------------------------------------------------------------- #
# Coverage helpers                                                       #
# --------------------------------------------------------------------- #


@dataclass
class CoverageSummary:
    """Per-(asset, exchange) coverage snapshot for GUI status display.
    v3.23.98 added ``exchange_id`` — one row per (asset, exchange)
    pair covered by the registry."""
    asset: str
    exchange_id: str
    tablet_count: int
    total_candles: int
    first_ts_ms: int
    last_ts_ms: int
    years: list[int] = field(default_factory=list)


# --------------------------------------------------------------------- #
# v3.24.6 — availability metadata + window status                        #
# --------------------------------------------------------------------- #


class WindowStatus:
    """Enum of what a caller learns when they ask 'is this window
    covered?' Used by the fleet-replay panel + backtest harness to
    emit precise notifications instead of silently returning short
    tapes.
    """
    FULL = "full"                # data spans entire requested window
    LATE_LISTING = "late_listing"  # tablet begins AFTER requested since_ms
    STALE = "stale"              # tablet ends BEFORE requested until_ms
    LATE_AND_STALE = "late_and_stale"  # both edges outside coverage
    EMPTY = "empty"              # no tablet at all


@dataclass
class AvailabilityInfo:
    """v3.24.6 — platform-level flags per operator directive 2026-08-01:
    'Add stone tablet level flags that the platform will recognize.'

    Populated from the tablet's ``listed_at_ms`` + coverage extents.
    Consumers (fleet replay, backtest harness, chart widgets) read
    this to emit the operator's requested notification:
        'This asset was listed on Coinbase mm/dd/yyyy and no prior
        data exists.'
    """
    asset: str
    exchange_id: str
    listed_at_ms: int          # first candle in tablet (0 if none)
    last_ts_ms: int            # last candle in tablet (0 if none)
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
        """True when a candle at (or before) ts_ms exists in the
        tablet — i.e., the asset had data BEFORE that timestamp."""
        return self.listed_at_ms > 0 and self.listed_at_ms <= ts_ms

    def listing_notice(self, exchange_display: str = "Coinbase") -> str:
        """Human-readable notice for the Simulator Activity Log."""
        if self.listed_at_ms <= 0:
            return (f"{self.asset}: no data in Stone Tablets on "
                    f"{exchange_display}.")
        return (f"{self.asset}: listed on {exchange_display} "
                f"{self.listed_at_iso} — no prior data exists.")


# --------------------------------------------------------------------- #
# Registry                                                              #
# --------------------------------------------------------------------- #


class StoneTabletsRegistry:
    """Singleton (via get_registry()) that owns the on-disk tablets.

    Thread-safety: a single lock guards mutation. Reads are done
    under the lock too since ingest can happen concurrently with
    sim reads. Cheap since tablets fit in memory.
    """

    def __init__(self, root: Optional[Path] = None) -> None:
        self._root = root or STONE_TABLETS_DIR
        ensure_root(self._root)
        self._lock = threading.RLock()
        # v3.23.98: key includes exchange_id per operator directive
        # 2026-08-01 ("some stone tablets are exchange specific").
        # (asset, exchange_id, timeframe, year) -> Tablet
        # v3.24.23 — LAZY BODIES. `_tablets` is now a bounded cache of
        # candle bodies loaded on demand, not the authoritative index.
        # `_entries` (manifest metadata) is the index.
        self._tablets: dict[tuple[str, str, str, int], Tablet] = {}
        self._entries: dict[tuple[str, str, str, int], TabletEntry] = {}
        # (asset, exchange_id) -> set of years at NATIVE_TIMEFRAME
        self._assets: dict[tuple[str, str], set[int]] = {}
        self._lru: list[tuple[str, str, str, int]] = []
        self._load_from_manifest()

    # ── init / load ─────────────────────────────────────────────────

    def _load_from_manifest(self) -> None:
        """Index the archive from MANIFEST metadata only.

        v3.24.23 — this used to call ``read_tablet()`` on every manifest
        row, fully parsing all 406 tablet files at construction.
        Measured on the live archive:

            construction      13.15 s
            resident memory   +2,282 MB  (19.9 -> 2,301.9 MB)

        ``main.py`` builds the registry at app boot, so that was a 13 s
        blocking stall and 2.3 GB held for the life of the process that
        executes real trades — for candle bodies boot never reads.

        Everything the boot-path consumers need is already in MANIFEST:
        asset, exchange_id, year, candle_count, first_ts_ms, last_ts_ms,
        listed_at_ms. Verified against the live archive — summing
        ``candle_count`` over the manifest alone gives 7,230,993, the
        exact total. Reading it costs 0.0021 s and ~0.2 MB.

        Bodies now load on first real need (``get_candles``,
        ``missing_ranges``, ``ingest_candles``) via ``_tablet()``.
        """
        entries = read_manifest(self._root)
        missing = 0
        for e in entries:
            path = tablet_path(
                e.asset, e.timeframe, e.year, root=self._root,
                exchange_id=e.exchange_id)
            # Preserve the old warn-and-skip semantics for a MANIFEST row
            # whose file is gone, without paying a full parse for it.
            # os.stat is ~406 syscalls against 406 JSON parses.
            if not path.exists():
                logger.warning(
                    "stone_tablets: MANIFEST references %s but "
                    "file is missing — skipping", path.name)
                missing += 1
                continue
            key = (e.asset.upper(), e.exchange_id, e.timeframe, e.year)
            self._entries[key] = e
            if e.timeframe == NATIVE_TIMEFRAME:
                self._assets.setdefault(
                    (e.asset.upper(), e.exchange_id),
                    set()).add(e.year)
        logger.info(
            "stone_tablets: indexed %d tablet(s) covering %d "
            "(asset, exchange) pair(s); bodies load on demand%s",
            len(self._entries), len(self._assets),
            f"; {missing} manifest row(s) skipped" if missing else "")

    def _tablet(self, key: tuple[str, str, str, int]) -> Optional[Tablet]:
        """Return the tablet body for ``key``, loading it on first use.

        Caller must hold ``self._lock``. Corrupt-file semantics match the
        old eager loader: warn once and treat as absent.
        """
        tab = self._tablets.get(key)
        if tab is not None:
            self._touch(key)
            return tab
        entry = self._entries.get(key)
        if entry is None:
            return None
        path = tablet_path(
            entry.asset, entry.timeframe, entry.year, root=self._root,
            exchange_id=entry.exchange_id)
        tab = read_tablet(path)
        if tab is None:
            logger.warning(
                "stone_tablets: %s is unreadable or corrupt — "
                "treating as absent", path.name)
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
        """Bound the body cache.

        Without this, a 406-asset universe sweep re-accumulates the same
        2.4 GB the lazy load exists to avoid. A 35-bot fleet replay
        touches ~35 tablets, so the cap is set well above that.
        """
        while len(self._tablets) > _BODY_CACHE_MAX:
            oldest = self._lru.pop(0)
            self._tablets.pop(oldest, None)

    def _keys_for(
        self, asset_u: str, exchange_id: str,
        timeframe: str = NATIVE_TIMEFRAME,
    ) -> list[tuple[str, str, str, int]]:
        """Index lookup for one (asset, exchange, timeframe).

        Folds in audit finding #15 — several methods linear-scanned the
        whole tablet dict for this. Reads metadata only, so it never
        forces a body load.
        """
        return [k for k in self._entries
                if k[0] == asset_u and k[1] == exchange_id
                and k[2] == timeframe]

    def _persist_manifest(self) -> None:
        """Write MANIFEST from the metadata index.

        v3.24.23 — this used to rebuild every row via
        ``entry_from_tablet()``, which calls ``Tablet.compute_checksum()``
        on all 406 tablets. Measured at 7.46 s per call, and
        ``ingest_candles`` calls it once per 350-candle chunk — roughly
        103 chunks per asset for a YTD window.

        Rebuilding from ``self._entries`` reuses each tablet's stored
        checksum and recomputes only the row that actually changed
        (``ingest_candles`` refreshes its dirty entry before calling
        this). Writing MANIFEST every chunk is deliberate — the fetcher
        relies on it so a crash mid-fetch loses at most one chunk — so
        the fix is to make the write cheap, not less frequent.
        """
        entries = sorted(
            self._entries.values(),
            key=lambda e: (e.asset, e.timeframe, e.year))
        write_manifest(entries, root=self._root)

    # ── coverage queries ────────────────────────────────────────────

    def has_coverage(
        self, asset: str, since_ms: int, until_ms: int,
        timeframe: str = NATIVE_TIMEFRAME,
        exchange_id: str = "coinbase",
    ) -> bool:
        """True when the registry has continuous 5m candles across
        the [since, until] window for the (asset, exchange). Rollup
        happens at read time regardless of the requested timeframe."""
        with self._lock:
            asset_u = asset.upper()
            years = self._assets.get((asset_u, exchange_id), set())
            if not years:
                return False
            since_dt = datetime.fromtimestamp(
                since_ms / 1000.0, tz=timezone.utc)
            until_dt = datetime.fromtimestamp(
                until_ms / 1000.0, tz=timezone.utc)
            spans = set(range(since_dt.year, until_dt.year + 1))
            if not spans.issubset(years):
                return False
            first, last = self._native_ts_bounds(asset_u, exchange_id)
            if first is None or last is None:
                return False
            return first <= since_ms and last >= until_ms

    def _native_ts_bounds(
        self, asset_u: str, exchange_id: str,
    ) -> tuple[Optional[int], Optional[int]]:
        # v3.24.23 — reads MANIFEST metadata, never candle bodies.
        # first_ts_ms / last_ts_ms are stored per row, so this answers
        # from the index without touching disk.
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
        self, asset: str, since_ms: int, until_ms: int,
        timeframe: str = NATIVE_TIMEFRAME,
        exchange_id: str = "coinbase",
    ) -> list[tuple[int, int]]:
        """Return list of [start_ms, end_ms] gaps in the requested
        window at 5m granularity. Empty list = fully covered."""
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
        self, asset_u: str, exchange_id: str,
    ) -> set[int]:
        # v3.24.23 — genuinely needs candle bodies, so it loads them
        # on demand rather than relying on an eager whole-archive load.
        out: set[int] = set()
        for key in self._keys_for(asset_u, exchange_id):
            tab = self._tablet(key)
            if tab is None:
                continue
            for row in tab.candles:
                out.add(int(row[0]))
        return out

    # ── read ────────────────────────────────────────────────────────

    def get_candles(
        self, asset: str, since_ms: int, until_ms: int,
        timeframe: str = NATIVE_TIMEFRAME,
        exchange_id: str = "coinbase",
    ) -> list[list[float]]:
        """Return chronological candles [[ts, o, h, l, c, v], ...]
        within the window at the requested timeframe. Native (5m)
        reads slice directly; higher TFs are rolled up on the fly."""
        if timeframe not in _TF_SECONDS:
            raise ValueError(
                f"unsupported timeframe {timeframe!r}; "
                f"supported: {SUPPORTED_TIMEFRAMES}")
        with self._lock:
            asset_u = asset.upper()
            native = self._native_slice(
                asset_u, exchange_id, since_ms, until_ms)
            if timeframe == NATIVE_TIMEFRAME:
                return native
            return _rollup(native, _rollup_factor(timeframe),
                           _TF_SECONDS[timeframe] * 1000)

    def _native_slice(
        self, asset_u: str, exchange_id: str,
        since_ms: int, until_ms: int,
    ) -> list[list[float]]:
        # v3.24.23 — body read; loads on demand.
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

    # ── ingest ──────────────────────────────────────────────────────

    def ingest_candles(
        self, asset: str, timeframe: str,
        rows: list[list[float]], source: str,
        exchange_id: str = "coinbase",
    ) -> int:
        """Append candles into the appropriate
        (asset, exchange, tf, year) tablet(s), dedupe by ts, persist
        to disk, update MANIFEST. Returns count of NEW candles
        written."""
        if timeframe != NATIVE_TIMEFRAME:
            raise ValueError(
                f"ingest requires native timeframe {NATIVE_TIMEFRAME!r}; "
                f"got {timeframe!r}. Rollup TFs are read-only.")
        if not rows:
            return 0
        with self._lock:
            asset_u = asset.upper()
            by_year: dict[int, list[list[float]]] = {}
            for row in rows:
                if len(row) < 6:
                    continue
                ts_ms = int(row[0])
                year = datetime.fromtimestamp(
                    ts_ms / 1000.0, tz=timezone.utc).year
                by_year.setdefault(year, []).append(list(row))
            appended_total = 0
            fetched_at = datetime.now(timezone.utc).isoformat(
                timespec="seconds")
            for year, year_rows in by_year.items():
                key = (asset_u, exchange_id, timeframe, year)
                # v3.24.23 — _tablet() loads the body on demand. A brand
                # new (asset, year) has no manifest row, so this returns
                # None and we create the tablet, exactly as before.
                tab = self._tablet(key)
                if tab is None:
                    tab = Tablet(
                        asset=asset_u, exchange_id=exchange_id,
                        timeframe=timeframe, year=year, source=source,
                        fetched_at=fetched_at, candles=[])
                existing_ts = {int(r[0]) for r in tab.candles}
                new_rows = [r for r in year_rows
                            if int(r[0]) not in existing_ts]
                if not new_rows:
                    continue
                merged = list(tab.candles) + new_rows
                merged.sort(key=lambda r: int(r[0]))
                tab.candles = merged
                tab.fetched_at = fetched_at
                self._tablets[key] = tab
                self._touch(key)
                # Refresh ONLY this row's manifest entry. This is the
                # single checksum recomputation per ingest; previously
                # _persist_manifest re-checksummed all 406 tablets on
                # every 350-candle chunk (7.46 s each, ~103 chunks per
                # asset for a YTD fill).
                self._entries[key] = entry_from_tablet(tab)
                self._assets.setdefault(
                    (asset_u, exchange_id), set()).add(year)
                write_tablet(tab, root=self._root)
                appended_total += len(new_rows)
            if appended_total > 0:
                self._persist_manifest()
                self._evict_if_needed()
            return appended_total

    # ── summary / diagnostics ───────────────────────────────────────

    def coverage_summary(self) -> list[CoverageSummary]:
        with self._lock:
            # v3.24.23 — answered entirely from MANIFEST metadata.
            # candle_count is stored per row; summing it over the live
            # manifest reproduces the archive total (7,230,993) exactly,
            # so no candle body is needed here.
            out: list[CoverageSummary] = []
            for (asset_u, eid) in sorted(self._assets.keys()):
                first, last = self._native_ts_bounds(asset_u, eid)
                years = sorted(self._assets[(asset_u, eid)])
                keys = self._keys_for(asset_u, eid)
                total = sum(int(self._entries[k].candle_count)
                            for k in keys)
                out.append(CoverageSummary(
                    asset=asset_u,
                    exchange_id=eid,
                    tablet_count=len(keys),
                    total_candles=total,
                    first_ts_ms=first or 0,
                    last_ts_ms=last or 0,
                    years=years,
                ))
            return out

    # ── v3.24.6 — availability metadata + window check ─────────────

    def get_asset_availability(
        self, asset: str, exchange_id: str = "coinbase",
    ) -> Optional[AvailabilityInfo]:
        """Return the platform-level availability flag block for
        this (asset, exchange). None when no tablets exist for the
        pair. Consumers use this to emit the operator's requested
        listing notice."""
        with self._lock:
            asset_u = asset.upper()
            key = (asset_u, exchange_id)
            if key not in self._assets:
                return None
            # v3.24.23 — metadata only. MANIFEST rows carry
            # listed_at_ms, last_ts_ms and candle_count directly.
            keys = self._keys_for(asset_u, exchange_id)
            if not keys:
                return None
            rows = [self._entries[k] for k in keys]
            # listed_at_ms = min first_ts across all year-tablets for
            # the (asset, exchange). Zero-guard for empty tablets.
            listed = min(
                (int(r.listed_at_ms) for r in rows
                 if int(r.listed_at_ms) > 0), default=0)
            last_ts = max(
                (int(r.last_ts_ms) for r in rows
                 if int(r.last_ts_ms) > 0), default=0)
            total_candles = sum(int(r.candle_count) for r in rows)
            return AvailabilityInfo(
                asset=asset_u,
                exchange_id=exchange_id,
                listed_at_ms=listed,
                last_ts_ms=last_ts,
                total_candles=total_candles,
                tablet_count=len(rows))

    def check_window_availability(
        self, asset: str, since_ms: int, until_ms: int,
        exchange_id: str = "coinbase",
        stale_threshold_ms: int = 86_400_000,
        listing_tolerance_ms: int = 86_400_000,
    ) -> str:
        """Return a ``WindowStatus`` string classifying how well the
        tablets cover the requested [since_ms, until_ms] window.

        stale_threshold_ms (default 24h) — a tablet ending within
        this window of until_ms is still considered fresh; older
        than that = STALE.
        listing_tolerance_ms (default 24h) — an asset listed within
        24h of since_ms still counts as FULL. Losing <288 candles
        of a 35k-candle YTD (=0.8%) is not meaningful "lateness."
        Assets flagged LATE_LISTING are the ones a backtest would
        truly miss significant history for.
        """
        avail = self.get_asset_availability(asset, exchange_id)
        if avail is None or avail.total_candles == 0:
            return WindowStatus.EMPTY
        late = (avail.listed_at_ms - since_ms) > listing_tolerance_ms
        stale = (avail.last_ts_ms > 0
                 and (until_ms - avail.last_ts_ms) > stale_threshold_ms)
        if late and stale:
            return WindowStatus.LATE_AND_STALE
        if late:
            return WindowStatus.LATE_LISTING
        if stale:
            return WindowStatus.STALE
        return WindowStatus.FULL

    def stale_assets(
        self, now_ms: Optional[int] = None,
        threshold_days: int = 2,
        exchange_id: Optional[str] = None,
    ) -> list[str]:
        """Assets whose latest candle is older than threshold_days.
        If exchange_id is given, restrict to that exchange; else
        report any asset stale on any exchange."""
        _now = (now_ms if now_ms is not None
                else int(datetime.now(timezone.utc).timestamp() * 1000))
        threshold_ms = threshold_days * 86_400_000
        with self._lock:
            out: set[str] = set()
            for (asset_u, eid) in self._assets:
                if exchange_id is not None and eid != exchange_id:
                    continue
                _first, last = self._native_ts_bounds(asset_u, eid)
                if last is None or (_now - last) > threshold_ms:
                    out.add(asset_u)
            return sorted(out)


# --------------------------------------------------------------------- #
# 5m → higher-TF rollup                                                 #
# --------------------------------------------------------------------- #


def _rollup(
    native_rows: list[list[float]],
    factor: int,
    bucket_ms: int,
) -> list[list[float]]:
    """Deterministic OHLCV rollup. Groups by (ts // bucket_ms) so
    incomplete tail buckets are still emitted (with whatever 5m
    candles landed in them). Order preserved.
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


# --------------------------------------------------------------------- #
# Singleton                                                             #
# --------------------------------------------------------------------- #

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
    """Test-only helper. Never call from production code."""
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
