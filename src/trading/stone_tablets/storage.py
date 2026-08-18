"""storage.py — read/write per-tablet JSON files + MANIFEST.

Isolated pure module — no async, no exchange, no runtime state.
Consumers: registry.py + fetcher.py.

Storage layout (per operator directive 2026-08-01):

    ~/.acervator/stone_tablets/
    ├── MANIFEST.json
    ├── BTC_5m_2026.json         # canonical tablet
    ├── ETH_5m_2026.json
    └── _scratch/                # pre-verified fetches
        └── SOL_5m_2026.json

sadp: R28 SSS + R70 RCN
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("acervator.stone_tablets.storage")

# --------------------------------------------------------------------- #
# Paths                                                                 #
# --------------------------------------------------------------------- #

STONE_TABLETS_DIR: Path = Path(
    os.path.expanduser("~/.acervator/stone_tablets"))
MANIFEST_PATH: Path = STONE_TABLETS_DIR / "MANIFEST.json"
SCRATCH_DIR: Path = STONE_TABLETS_DIR / "_scratch"

SCHEMA_VERSION: int = 2


# --------------------------------------------------------------------- #
# Dataclasses                                                            #
# --------------------------------------------------------------------- #


@dataclass
class TabletEntry:
    """One row in the manifest — index of a tablet on disk.

    v3.23.98: added ``exchange_id`` per operator directive 2026-08-01:
    "some stone tablets are exchange specific ... will come into play
    as soon as we get to feature-complete, multi-exchange verification
    phase." Coinbase is the only exchange today; the field is
    scaffolded now so multi-exchange doesn't require a schema
    migration later.
    """
    asset: str
    exchange_id: str
    timeframe: str
    year: int
    file: str
    checksum_sha256: str
    candle_count: int
    first_ts_ms: int
    last_ts_ms: int
    fetched_at: str
    source: str
    # v3.24.6 — explicit platform-level listing marker per operator
    # directive 2026-08-01: "Add stone tablet level flags that the
    # platform will recognize." For coverage that starts at YTD_START
    # this equals first_ts_ms; for assets Coinbase listed AFTER
    # YTD_START, this is the actual listing date (first candle) so
    # consumers can emit "This asset was listed on Coinbase mm/dd/yyyy
    # and no prior data exists." Reads with old manifests fall back
    # to first_ts_ms in read_manifest().
    listed_at_ms: int = 0

    @property
    def listed_at_iso(self) -> str:
        """UTC ISO date string derived from listed_at_ms (or first_ts
        as fallback for old manifests). Empty when neither is set."""
        ts = self.listed_at_ms or self.first_ts_ms
        if ts <= 0:
            return ""
        return datetime.fromtimestamp(
            ts / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


@dataclass
class Tablet:
    """Full tablet contents — schema v2 (v3.23.98 adds exchange_id,
    v3.24.6 adds listed_at_ms as a computed property)."""
    asset: str
    exchange_id: str
    timeframe: str
    year: int
    source: str
    fetched_at: str
    candles: list[list[float]] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    @property
    def candle_count(self) -> int:
        return len(self.candles)

    @property
    def first_ts_ms(self) -> int:
        return int(self.candles[0][0]) if self.candles else 0

    @property
    def last_ts_ms(self) -> int:
        return int(self.candles[-1][0]) if self.candles else 0

    @property
    def listed_at_ms(self) -> int:
        """v3.24.6 — the timestamp of this tablet's earliest candle.
        Equals ``first_ts_ms``; kept as a semantic alias so platform
        code that asks 'when was this asset listed?' reads naturally.
        Zero when the tablet has no candles."""
        return self.first_ts_ms

    @property
    def listed_at_iso(self) -> str:
        if self.listed_at_ms <= 0:
            return ""
        return datetime.fromtimestamp(
            self.listed_at_ms / 1000.0, tz=timezone.utc
        ).strftime("%Y-%m-%d")

    def compute_checksum(self) -> str:
        """SHA-256 over the candles list only — deterministic
        regardless of fetched_at / source metadata drift."""
        payload = json.dumps(
            self.candles, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["candle_count"] = self.candle_count
        d["first_ts_ms"] = self.first_ts_ms
        d["last_ts_ms"] = self.last_ts_ms
        # v3.24.6 — persist listing marker so consumers reading the
        # raw JSON file (not just the MANIFEST index) see it too.
        d["listed_at_ms"] = self.listed_at_ms
        d["checksum_sha256"] = self.compute_checksum()
        return d


# --------------------------------------------------------------------- #
# Filename convention                                                    #
# --------------------------------------------------------------------- #


def tablet_filename(
    asset: str, timeframe: str, year: int,
    exchange_id: str = "coinbase",
) -> str:
    # v3.23.98: exchange_id in filename so multi-exchange tablets
    # co-exist without collision when that phase lands.
    return f"{asset.upper()}_{timeframe}_{int(year)}_{exchange_id}.json"


def tablet_path(
    asset: str, timeframe: str, year: int,
    root: Optional[Path] = None,
    exchange_id: str = "coinbase",
) -> Path:
    return (root or STONE_TABLETS_DIR) / tablet_filename(
        asset, timeframe, year, exchange_id=exchange_id)


# --------------------------------------------------------------------- #
# I/O                                                                    #
# --------------------------------------------------------------------- #


def ensure_root(root: Optional[Path] = None) -> Path:
    r = root or STONE_TABLETS_DIR
    r.mkdir(parents=True, exist_ok=True)
    (r / "_scratch").mkdir(parents=True, exist_ok=True)
    return r


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via tempfile + rename so a crash mid-write doesn't
    leave a half-written tablet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent), prefix=".tmp_",
        suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def read_tablet(path: Path) -> Optional[Tablet]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "stone_tablets: failed to read %s: %s", path, exc)
        return None
    tab = Tablet(
        asset=str(data.get("asset", "")),
        exchange_id=str(data.get("exchange_id", "coinbase")),
        timeframe=str(data.get("timeframe", "")),
        year=int(data.get("year", 0)),
        source=str(data.get("source", "unknown")),
        fetched_at=str(data.get("fetched_at", "")),
        candles=list(data.get("candles", [])),
        schema_version=int(data.get(
            "schema_version", SCHEMA_VERSION)),
    )
    # Checksum audit — log if drift detected
    on_disk = str(data.get("checksum_sha256", ""))
    computed = tab.compute_checksum()
    if on_disk and on_disk != computed:
        logger.warning(
            "stone_tablets: checksum drift in %s "
            "(on_disk=%s, computed=%s) — tablet may be tampered",
            path, on_disk[:12], computed[:12])
    return tab


def write_tablet(tab: Tablet, root: Optional[Path] = None) -> Path:
    r = ensure_root(root)
    path = tablet_path(
        tab.asset, tab.timeframe, tab.year, root=r,
        exchange_id=tab.exchange_id)
    text = json.dumps(tab.to_dict(), separators=(",", ":"))
    _atomic_write_text(path, text)
    return path


# --------------------------------------------------------------------- #
# Manifest                                                              #
# --------------------------------------------------------------------- #


def read_manifest(
    root: Optional[Path] = None,
) -> list[TabletEntry]:
    r = root or STONE_TABLETS_DIR
    p = r / "MANIFEST.json"
    if not p.exists():
        return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "stone_tablets: MANIFEST read failed: %s", exc)
        return []
    out: list[TabletEntry] = []
    for row in data.get("tablets", []):
        if not isinstance(row, dict):
            continue
        try:
            # v3.24.6 — listed_at_ms with backward-compat fallback to
            # first_ts_ms so the 406 tablets from the v3.24.5 backfill
            # (pre-field manifests) still expose the semantic marker
            # without a migration step.
            _first_ts = int(row["first_ts_ms"])
            _listed_at = int(row.get("listed_at_ms", 0) or _first_ts)
            out.append(TabletEntry(
                asset=str(row["asset"]),
                exchange_id=str(row.get("exchange_id", "coinbase")),
                timeframe=str(row["timeframe"]),
                year=int(row["year"]),
                file=str(row["file"]),
                checksum_sha256=str(row["checksum_sha256"]),
                candle_count=int(row["candle_count"]),
                first_ts_ms=_first_ts,
                last_ts_ms=int(row["last_ts_ms"]),
                fetched_at=str(row["fetched_at"]),
                source=str(row["source"]),
                listed_at_ms=_listed_at,
            ))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def write_manifest(
    entries: list[TabletEntry],
    root: Optional[Path] = None,
) -> Path:
    r = ensure_root(root)
    p = r / "MANIFEST.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(
            timespec="seconds"),
        "tablets": [asdict(e) for e in entries],
    }
    _atomic_write_text(p, json.dumps(payload, indent=2))
    return p


def entry_from_tablet(tab: Tablet) -> TabletEntry:
    return TabletEntry(
        asset=tab.asset,
        exchange_id=tab.exchange_id,
        timeframe=tab.timeframe,
        year=tab.year,
        file=tablet_filename(
            tab.asset, tab.timeframe, tab.year,
            exchange_id=tab.exchange_id),
        checksum_sha256=tab.compute_checksum(),
        candle_count=tab.candle_count,
        first_ts_ms=tab.first_ts_ms,
        last_ts_ms=tab.last_ts_ms,
        fetched_at=tab.fetched_at,
        source=tab.source,
        listed_at_ms=tab.listed_at_ms,
    )


__all__ = [
    "MANIFEST_PATH",
    "SCHEMA_VERSION",
    "SCRATCH_DIR",
    "STONE_TABLETS_DIR",
    "Tablet",
    "TabletEntry",
    "ensure_root",
    "entry_from_tablet",
    "read_manifest",
    "read_tablet",
    "tablet_filename",
    "tablet_path",
    "write_manifest",
    "write_tablet",
]
