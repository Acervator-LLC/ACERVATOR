"""Stone Tablet files and the MANIFEST index.

``read_tablet`` and ``write_tablet`` move one ``Tablet`` between JSON and
memory under ``STONE_TABLETS_DIR``, at the name ``tablet_filename`` builds from
``asset``, ``timeframe``, ``year`` and ``exchange_id``. ``read_manifest`` and
``write_manifest`` carry the ``TabletEntry`` index that ``entry_from_tablet``
fills in from a ``Tablet``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ..._version import is_frozen, project_root
from ...core.io_utils import atomic_write_json

logger = logging.getLogger("acervator.stone_tablets.storage")

HOME_TABLETS_DIR: Path = Path(os.path.expanduser("~/.acervator/stone_tablets"))


def _tablet_root() -> Path:
    """Return the tracked ``stone_tablets`` directory, or ``HOME_TABLETS_DIR``
    when ``is_frozen``.

    A bundle carries no ``stone_tablets`` directory, so ``project_root`` there
    names the unpacked bundle and the home tree answers instead.
    """
    if is_frozen():
        return HOME_TABLETS_DIR
    return project_root() / "stone_tablets"


STONE_TABLETS_DIR: Path = _tablet_root()
MANIFEST_PATH: Path = STONE_TABLETS_DIR / "MANIFEST.json"
SCRATCH_DIR: Path = STONE_TABLETS_DIR / "_scratch"

SCHEMA_VERSION: int = 2


@dataclass
class TabletEntry:
    """One MANIFEST row indexing the tablet named by ``file``.

    ``read_manifest`` falls back to ``first_ts_ms`` for a row carrying no
    ``listed_at_ms``.
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
    # Timestamp of the asset's earliest candle on the exchange; 0 when unknown.
    listed_at_ms: int = 0

    @property
    def listed_at_iso(self) -> str:
        """``YYYY-MM-DD`` in UTC from ``listed_at_ms``, or ``first_ts_ms`` when
        that is zero.

        Returns an empty string when both are zero or negative.
        """
        ts = self.listed_at_ms or self.first_ts_ms
        if ts <= 0:
            return ""
        return datetime.fromtimestamp(ts / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


@dataclass
class Tablet:
    """One asset's ``candles`` with the metadata written beside them.

    ``to_dict`` adds ``candle_count``, ``first_ts_ms``, ``last_ts_ms``,
    ``listed_at_ms`` and ``checksum_sha256`` to the stored form.
    """

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
        """Timestamp of the earliest row in ``candles``, equal to
        ``first_ts_ms``.

        Zero when ``candles`` is empty.
        """
        return self.first_ts_ms

    @property
    def listed_at_iso(self) -> str:
        if self.listed_at_ms <= 0:
            return ""
        return datetime.fromtimestamp(
            self.listed_at_ms / 1000.0, tz=timezone.utc
        ).strftime("%Y-%m-%d")

    def compute_checksum(self) -> str:
        """SHA-256 over ``candles`` alone.

        ``fetched_at`` and ``source`` do not change the digest.
        """
        payload = json.dumps(self.candles, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["candle_count"] = self.candle_count
        d["first_ts_ms"] = self.first_ts_ms
        d["last_ts_ms"] = self.last_ts_ms
        d["listed_at_ms"] = self.listed_at_ms
        d["checksum_sha256"] = self.compute_checksum()
        return d


def tablet_filename(
    asset: str,
    timeframe: str,
    year: int,
    exchange_id: str = "coinbase",
) -> str:
    """Return ``ASSET_timeframe_year_exchangeid.json``.

    ``asset`` is upper-cased and ``year`` is coerced to ``int``.
    """
    return f"{asset.upper()}_{timeframe}_{int(year)}_{exchange_id}.json"


def tablet_path(
    asset: str,
    timeframe: str,
    year: int,
    root: Optional[Path] = None,
    exchange_id: str = "coinbase",
) -> Path:
    return (root or STONE_TABLETS_DIR) / tablet_filename(
        asset, timeframe, year, exchange_id=exchange_id
    )


def ensure_root(root: Optional[Path] = None) -> Path:
    """Create ``root`` and its ``_scratch`` subdirectory, then return ``root``.

    ``STONE_TABLETS_DIR`` is used when ``root`` is None.
    """
    r = root or STONE_TABLETS_DIR
    r.mkdir(parents=True, exist_ok=True)
    (r / "_scratch").mkdir(parents=True, exist_ok=True)
    return r


def read_tablet(path: Path) -> Optional[Tablet]:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("stone_tablets: failed to read %s: %s", path, exc)
        return None
    tab = Tablet(
        asset=str(data.get("asset", "")),
        exchange_id=str(data.get("exchange_id", "coinbase")),
        timeframe=str(data.get("timeframe", "")),
        year=int(data.get("year", 0)),
        source=str(data.get("source", "unknown")),
        fetched_at=str(data.get("fetched_at", "")),
        candles=list(data.get("candles", [])),
        schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
    )
    on_disk = str(data.get("checksum_sha256", ""))
    computed = tab.compute_checksum()
    if on_disk and on_disk != computed:
        logger.warning(
            "stone_tablets: checksum drift in %s "
            "(on_disk=%s, computed=%s) — tablet may be tampered",
            path,
            on_disk[:12],
            computed[:12],
        )
    return tab


def write_tablet(tab: Tablet, root: Optional[Path] = None) -> Path:
    r = ensure_root(root)
    path = tablet_path(
        tab.asset, tab.timeframe, tab.year, root=r, exchange_id=tab.exchange_id
    )
    atomic_write_json(path, tab.to_dict(), indent=None, separators=(",", ":"))
    return path


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
        logger.warning("stone_tablets: MANIFEST read failed: %s", exc)
        return []
    out: list[TabletEntry] = []
    for row in data.get("tablets", []):
        if not isinstance(row, dict):
            continue
        try:
            _first_ts = int(row["first_ts_ms"])
            _listed_at = int(row.get("listed_at_ms", 0) or _first_ts)
            out.append(
                TabletEntry(
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
                )
            )
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
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tablets": [asdict(e) for e in entries],
    }
    atomic_write_json(p, payload, indent=2)
    return p


def entry_from_tablet(tab: Tablet) -> TabletEntry:
    return TabletEntry(
        asset=tab.asset,
        exchange_id=tab.exchange_id,
        timeframe=tab.timeframe,
        year=tab.year,
        file=tablet_filename(
            tab.asset, tab.timeframe, tab.year, exchange_id=tab.exchange_id
        ),
        checksum_sha256=tab.compute_checksum(),
        candle_count=tab.candle_count,
        first_ts_ms=tab.first_ts_ms,
        last_ts_ms=tab.last_ts_ms,
        fetched_at=tab.fetched_at,
        source=tab.source,
        listed_at_ms=tab.listed_at_ms,
    )


__all__ = [
    "HOME_TABLETS_DIR",
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
