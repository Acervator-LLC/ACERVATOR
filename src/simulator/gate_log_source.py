"""The Simulator's gate-log path: the recorded gate decisions, read only.

``GateLogSource`` answers ``root``, ``path``, ``files``, ``rows``, ``bot_ids``
and ``span`` from ``gate.log`` and its rotations. It holds no venue and defines
no write, and ``__getattr__`` raises ``SendRefused`` for every other name.
``GateRow`` carries one recorded decision: the two armed flags, the two blocker
lists and the two fixtures ``ScrummingBot`` wrote.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from ..trading.live_log_reader import (
    GATE_LOG_REQUIRED_DATA_FIELDS,
    GATE_LOG_REQUIRED_TOP_FIELDS,
    LIVE_LOG_ROOT,
    SchemaDriftError,
)
from .tablet_source import SendRefused

logger = logging.getLogger("acervator.simulator.gate_log")

GATE_LOG_NAME = "gate.log"
TRADE_DIR_NAME = "trade"

#: Every name ``GateLogSource`` answers. ``__getattr__`` refuses the rest.
READ_NAMES = ("root", "path", "files", "rows", "bot_ids", "span")


@dataclass(frozen=True)
class GateRow:
    """One recorded gate decision, as ``gate.log`` stored it."""

    ts_ms: int
    bot_id: str
    symbol: str
    exchange_id: str
    scrum_armed: bool
    fold_armed: bool
    scrum_blockers: tuple[str, ...] = ()
    fold_blockers: tuple[str, ...] = ()
    scrum_fixture: dict = field(default_factory=dict)
    fold_fixture: dict = field(default_factory=dict)


def parse_ts_ms(stamp: str) -> int:
    """``stamp`` as milliseconds since the epoch, or 0 when it will not
    parse."""
    text = str(stamp or "")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return 0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000.0)


def row_from_entry(entry: dict) -> Optional[GateRow]:
    """One ``GateRow`` from a parsed ``gate.log`` entry, or None when it is
    dateless."""
    data = entry.get("data") or {}
    ts_ms = parse_ts_ms(entry.get("timestamp", ""))
    if ts_ms <= 0:
        return None
    return GateRow(
        ts_ms=ts_ms,
        bot_id=str(entry.get("bot_id") or ""),
        symbol=str(data.get("symbol") or ""),
        exchange_id=str(entry.get("exchange") or ""),
        scrum_armed=bool(data.get("scrum_armed")),
        fold_armed=bool(data.get("fold_armed")),
        scrum_blockers=tuple(str(one) for one in data.get("scrum_blockers") or []),
        fold_blockers=tuple(str(one) for one in data.get("fold_blockers") or []),
        scrum_fixture=dict(data.get("scrum_fixture") or {}),
        fold_fixture=dict(data.get("fold_fixture") or {}),
    )


def validate_entry(entry: dict) -> None:
    """Raise ``SchemaDriftError`` when ``entry`` misses a pinned gate.log
    field."""
    for name in GATE_LOG_REQUIRED_TOP_FIELDS:
        if name not in entry:
            raise SchemaDriftError(f"gate.log entry misses {name!r}")
    data = entry.get("data")
    if not isinstance(data, dict):
        raise SchemaDriftError("gate.log entry 'data' is not a dict")
    for name in GATE_LOG_REQUIRED_DATA_FIELDS:
        if name not in data:
            raise SchemaDriftError(f"gate.log data misses {name!r}")


class GateLogSource:
    """The recorded gate decisions on disk, as ``GateRow`` records."""

    def __init__(self, root: Optional[Path] = None) -> None:
        """Read from ``root``, or from ``LIVE_LOG_ROOT`` when it is None."""
        self._root = Path(root) if root is not None else LIVE_LOG_ROOT

    def root(self) -> Path:
        """The log root ``files`` enumerates."""
        return self._root

    def path(self) -> Path:
        """The active ``gate.log``."""
        return self._root / TRADE_DIR_NAME / GATE_LOG_NAME

    def files(self) -> list[Path]:
        """``gate.log`` and its rotations, oldest rotation first."""
        active = self.path()
        found = sorted(
            (one for one in active.parent.glob(GATE_LOG_NAME + ".*") if one.is_file()),
            key=lambda one: one.name,
            reverse=True,
        )
        if active.is_file():
            found.append(active)
        return found

    def rows(
        self,
        bot_ids: Optional[set[str]] = None,
        symbols: Optional[set[str]] = None,
        since_ms: int = 0,
        until_ms: int = 0,
        validate: bool = True,
    ) -> Iterator[GateRow]:
        """Yield every ``GateRow`` naming ``bot_ids`` or ``symbols``, between
        ``since_ms`` and ``until_ms``.

        A raw-text check skips a line before it is parsed; zero for either
        bound leaves that side open, and None for both narrows nothing.
        """
        by_id = {str(one) for one in bot_ids} if bot_ids else set()
        by_symbol = {str(one) for one in symbols} if symbols else set()
        marks = by_id | by_symbol
        for path in self.files():
            for line in _iter_lines(path):
                if marks and not any(one in line for one in marks):
                    continue
                entry = _parse_line(line)
                if entry is None:
                    continue
                if validate:
                    validate_entry(entry)
                row = row_from_entry(entry)
                if row is None:
                    continue
                if marks and row.bot_id not in by_id and row.symbol not in by_symbol:
                    continue
                if since_ms and row.ts_ms < since_ms:
                    continue
                if until_ms and row.ts_ms > until_ms:
                    continue
                yield row

    def bot_ids(self, limit_lines: int = 0) -> list[str]:
        """Every bot id the log names, over ``limit_lines`` lines when
        positive."""
        seen: set[str] = set()
        read = 0
        for path in self.files():
            for line in _iter_lines(path):
                read += 1
                if limit_lines and read > limit_lines:
                    return sorted(seen)
                entry = _parse_line(line)
                if entry is not None and entry.get("bot_id"):
                    seen.add(str(entry["bot_id"]))
        return sorted(seen)

    def span(self, bot_ids: Optional[set[str]] = None) -> dict:
        """The oldest and newest ``ts_ms`` the rows for ``bot_ids`` carry."""
        first = 0
        last = 0
        count = 0
        for row in self.rows(bot_ids=bot_ids, validate=False):
            count += 1
            first = row.ts_ms if first == 0 else min(first, row.ts_ms)
            last = max(last, row.ts_ms)
        return {"first_ts_ms": first, "last_ts_ms": last, "row_count": count}

    def __getattr__(self, name: str):
        """Refuse every name outside ``READ_NAMES``."""
        raise SendRefused(
            f"GateLogSource answers {READ_NAMES} and cannot {name!r}. "
            "The Simulator receives and asks; it sends nothing."
        )


def _iter_lines(path: Path) -> Iterator[str]:
    """Yield every non-empty line of ``path``."""
    if not path.is_file():
        return
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                yield stripped


def _parse_line(line: str) -> Optional[dict]:
    """One parsed NDJSON object, or None when the line will not parse.

    A rotation leaves a truncated trailing line, and one bad line is skipped.
    """
    try:
        loaded = json.loads(line)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


__all__ = [
    "GATE_LOG_NAME",
    "READ_NAMES",
    "TRADE_DIR_NAME",
    "GateLogSource",
    "GateRow",
    "SchemaDriftError",
    "SendRefused",
    "parse_ts_ms",
    "row_from_entry",
    "validate_entry",
]
