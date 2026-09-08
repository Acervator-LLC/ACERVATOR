"""YTD trade files under the exchange_history root.

``YtdTradeFile`` holds one ``exchange_id``, ``symbol`` and ``year`` of
``YtdTrade`` rows, written by ``write_trade_file`` at the name
``ytd_filename`` builds. ``merge_trades`` dedupes on ``YtdTrade.id`` so a later
import appends without duplicating a row, ``read_manifest`` and
``write_manifest`` carry the ``YtdFileEntry`` index, and ``write_gaps`` records
every ``TradeGap`` period no row covers.
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

from src.core.io_utils import atomic_write_json
from src.core.log_paths import get_exchange_history_dir

logger = logging.getLogger("acervator.exchange.ytd_trade_store")

YTD_TRADES_ROOT_ENV = "ACERVATOR_YTD_TRADES_ROOT"
"""Environment key redirecting ``get_ytd_root`` away from the live tree."""

SCHEMA_VERSION: int = 1

MANIFEST_NAME: str = "MANIFEST.json"
GAPS_NAME: str = "GAPS.json"

SIDE_BUY: str = "BUY"
SIDE_SELL: str = "SELL"
SIDES: frozenset[str] = frozenset({SIDE_BUY, SIDE_SELL})


def get_ytd_root(root: Optional[Path] = None) -> Path:
    """Return ``root``, the ``YTD_TRADES_ROOT_ENV`` path, or
    ``get_exchange_history_dir()``, created."""
    if root is not None:
        resolved = Path(root)
    else:
        override = os.environ.get(YTD_TRADES_ROOT_ENV)
        resolved = Path(override) if override else get_exchange_history_dir()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def symbol_slug(symbol: str) -> str:
    """Return ``symbol`` upper-cased with ``/`` replaced by ``-`` for a filename."""
    return symbol.upper().replace("/", "-")


def ytd_filename(exchange_id: str, symbol: str, year: int) -> str:
    """Return ``SYMBOL-QUOTE_year_exchangeid.json``."""
    return f"{symbol_slug(symbol)}_{int(year)}_{exchange_id}.json"


def ytd_path(
    exchange_id: str,
    symbol: str,
    year: int,
    root: Optional[Path] = None,
) -> Path:
    """Return the path ``ytd_filename`` names under ``get_ytd_root(root)``."""
    return get_ytd_root(root) / ytd_filename(exchange_id, symbol, year)


@dataclass
class YtdTrade:
    """One fill: ``id``, ``ts_ms``, ``side``, ``amount``, ``price``, ``cost``
    and ``fee``."""

    id: str
    ts_ms: int
    side: str
    amount: float
    price: float
    cost: float
    fee: float
    fee_currency: str

    def sort_key(self) -> tuple[int, str]:
        """Return ``(ts_ms, id)``, the order rows are stored in."""
        return (self.ts_ms, self.id)


@dataclass
class ImportSource:
    """One import that contributed rows: ``file``, ``sha256`` and ``rows_added``."""

    file: str
    sha256: str
    imported_at: str
    rows_added: int


@dataclass
class YtdTradeFile:
    """One ``exchange_id``, ``symbol`` and ``year`` of ``trades``, with its
    ``sources``."""

    exchange_id: str
    symbol: str
    year: int
    imported_at: str
    trades: list[YtdTrade] = field(default_factory=list)
    sources: list[ImportSource] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    @property
    def trade_count(self) -> int:
        return len(self.trades)

    @property
    def first_ts_ms(self) -> int:
        return int(self.trades[0].ts_ms) if self.trades else 0

    @property
    def last_ts_ms(self) -> int:
        return int(self.trades[-1].ts_ms) if self.trades else 0

    def compute_checksum(self) -> str:
        """SHA-256 over ``trades`` alone; ``imported_at`` and ``sources`` do not
        change it."""
        payload = json.dumps(
            [asdict(t) for t in self.trades], sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        """Return the stored form, adding the counts and ``checksum_sha256``."""
        return {
            "schema_version": self.schema_version,
            "exchange_id": self.exchange_id,
            "symbol": self.symbol,
            "year": self.year,
            "imported_at": self.imported_at,
            "trade_count": self.trade_count,
            "first_ts_ms": self.first_ts_ms,
            "last_ts_ms": self.last_ts_ms,
            "checksum_sha256": self.compute_checksum(),
            "sources": [asdict(s) for s in self.sources],
            "trades": [asdict(t) for t in self.trades],
        }


@dataclass
class YtdFileEntry:
    """One MANIFEST row indexing the trade file named by ``file``."""

    exchange_id: str
    symbol: str
    year: int
    file: str
    checksum_sha256: str
    trade_count: int
    first_ts_ms: int
    last_ts_ms: int
    imported_at: str
    source_files: list[str] = field(default_factory=list)


@dataclass
class TradeGap:
    """One period between ``since_ms`` and ``until_ms`` that no row covers."""

    exchange_id: str
    symbol: str
    year: int
    since_ms: int
    until_ms: int
    reason: str
    checked_at: str


def entry_from_file(trade_file: YtdTradeFile) -> YtdFileEntry:
    """Return the ``YtdFileEntry`` indexing ``trade_file``."""
    return YtdFileEntry(
        exchange_id=trade_file.exchange_id,
        symbol=trade_file.symbol,
        year=trade_file.year,
        file=ytd_filename(trade_file.exchange_id, trade_file.symbol, trade_file.year),
        checksum_sha256=trade_file.compute_checksum(),
        trade_count=trade_file.trade_count,
        first_ts_ms=trade_file.first_ts_ms,
        last_ts_ms=trade_file.last_ts_ms,
        imported_at=trade_file.imported_at,
        source_files=[s.file for s in trade_file.sources],
    )


def merge_trades(
    held: list[YtdTrade],
    incoming: list[YtdTrade],
) -> tuple[list[YtdTrade], int]:
    """Return ``held`` plus the ``incoming`` rows whose ``id`` is new, sorted,
    and how many were added."""
    by_id = {t.id: t for t in held}
    added = 0
    for trade in incoming:
        if trade.id in by_id:
            continue
        by_id[trade.id] = trade
        added += 1
    return sorted(by_id.values(), key=lambda t: t.sort_key()), added


def read_trade_file(path: Path) -> Optional[YtdTradeFile]:
    """Return the ``YtdTradeFile`` stored at ``path``, or None when it is absent
    or unreadable."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("ytd_trade_store: %s unreadable: %s", path.name, exc)
        return None
    try:
        return YtdTradeFile(
            exchange_id=str(data["exchange_id"]),
            symbol=str(data["symbol"]),
            year=int(data["year"]),
            imported_at=str(data.get("imported_at", "")),
            trades=[YtdTrade(**row) for row in data.get("trades", [])],
            sources=[ImportSource(**row) for row in data.get("sources", [])],
            schema_version=int(data.get("schema_version", SCHEMA_VERSION)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("ytd_trade_store: %s has no readable rows: %s", path.name, exc)
        return None


def write_trade_file(trade_file: YtdTradeFile, root: Optional[Path] = None) -> Path:
    """Write ``trade_file`` under ``get_ytd_root(root)`` and return its path."""
    path = ytd_path(
        trade_file.exchange_id, trade_file.symbol, trade_file.year, root=root
    )
    atomic_write_json(path, trade_file.to_dict(), indent=2)
    return path


def read_manifest(root: Optional[Path] = None) -> list[YtdFileEntry]:
    """Return the ``YtdFileEntry`` rows under ``root``, empty when MANIFEST.json
    is absent."""
    path = get_ytd_root(root) / MANIFEST_NAME
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("ytd_trade_store: MANIFEST.json unreadable: %s", exc)
        return []
    out: list[YtdFileEntry] = []
    for row in data.get("files", []):
        try:
            out.append(YtdFileEntry(**row))
        except TypeError:
            continue
    return out


def write_manifest(entries: list[YtdFileEntry], root: Optional[Path] = None) -> Path:
    """Write ``entries`` to MANIFEST.json under ``root`` and return that path."""
    path = get_ytd_root(root) / MANIFEST_NAME
    atomic_write_json(
        path,
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now_iso(),
            "files": [asdict(e) for e in entries],
        },
        indent=2,
    )
    return path


def read_gaps(root: Optional[Path] = None) -> list[TradeGap]:
    """Return the ``TradeGap`` rows under ``root``, empty when GAPS.json is
    absent."""
    path = get_ytd_root(root) / GAPS_NAME
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("ytd_trade_store: GAPS.json unreadable: %s", exc)
        return []
    out: list[TradeGap] = []
    for row in data.get("gaps", []):
        try:
            out.append(TradeGap(**row))
        except TypeError:
            continue
    return out


def write_gaps(gaps: list[TradeGap], root: Optional[Path] = None) -> Path:
    """Write ``gaps`` to GAPS.json under ``root`` and return that path."""
    path = get_ytd_root(root) / GAPS_NAME
    atomic_write_json(
        path,
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": utc_now_iso(),
            "gaps": [asdict(g) for g in gaps],
        },
        indent=2,
    )
    return path


def utc_now_iso() -> str:
    """Return the current UTC time as ``YYYY-MM-DDTHH:MM:SS+00:00``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "GAPS_NAME",
    "MANIFEST_NAME",
    "SCHEMA_VERSION",
    "SIDES",
    "SIDE_BUY",
    "SIDE_SELL",
    "YTD_TRADES_ROOT_ENV",
    "ImportSource",
    "TradeGap",
    "YtdFileEntry",
    "YtdTrade",
    "YtdTradeFile",
    "entry_from_file",
    "get_ytd_root",
    "merge_trades",
    "read_gaps",
    "read_manifest",
    "read_trade_file",
    "symbol_slug",
    "utc_now_iso",
    "write_gaps",
    "write_manifest",
    "write_trade_file",
    "ytd_filename",
    "ytd_path",
]
