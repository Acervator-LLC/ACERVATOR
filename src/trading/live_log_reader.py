"""The read-only reader of the live log root at ``LIVE_LOG_ROOT``.

``live_gate_decisions``, ``live_trades`` and ``live_voting_panel_snapshots``
yield a fresh dict per entry and write nothing. ``_validate_gate_entry`` and
``_validate_trade_entry`` raise ``SchemaDriftError`` on an entry that does
not match the pinned field lists. ``live_autonomous_trades`` drops the rows
whose ``operator_initiated`` is true.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

LIVE_LOG_ROOT: Path = Path.home() / ".acervator_logs"
LIVE_TRADE_DIR: Path = LIVE_LOG_ROOT / "trade"
LIVE_GATE_LOG: Path = LIVE_TRADE_DIR / "gate.log"
LIVE_TRADE_LOG: Path = LIVE_TRADE_DIR / "trade.log"
# One voting-panel snapshot per fired trade.
LIVE_VOTING_LOG: Path = LIVE_TRADE_DIR / "voting.log"
LIVE_CONSOLE_DIR: Path = LIVE_LOG_ROOT / "console"
LIVE_PNL_DIR: Path = LIVE_TRADE_DIR / "pnl"


# Schema pins. A new log field is added here in the same change.

GATE_LOG_REQUIRED_TOP_FIELDS = (
    "timestamp",
    "category",
    "bot_id",
    "data",
)
GATE_LOG_REQUIRED_DATA_FIELDS = (
    "symbol",
    "scrum_armed",
    "fold_armed",
    "scrum_blockers",
    "fold_blockers",
)
GATE_LOG_OPTIONAL_DATA_FIELDS = (
    "evaluated_at_tick",
    "scrum_fixture",
    "fold_fixture",
    "indicators",
    "state",
)

TRADE_LOG_REQUIRED_TOP_FIELDS = (
    "timestamp",
    "category",
    "bot_id",
    "data",
)
TRADE_LOG_REQUIRED_DATA_FIELDS = (
    "action",
    "symbol",
    "side",
    "amount",
    "price",
    "status",
    "usd",
    "operator_initiated",
)


class SchemaDriftError(RuntimeError):
    """Raised when an entry on disk does not match the pinned schema."""


def _validate_gate_entry(entry: dict) -> None:
    """Validate one parsed gate.log entry against the pinned field lists.

    Raises ``SchemaDriftError`` if any required field is missing. Optional
    fields may be absent, and must be the right shape when present.
    """
    for f in GATE_LOG_REQUIRED_TOP_FIELDS:
        if f not in entry:
            raise SchemaDriftError(
                f"gate.log entry missing top-level field {f!r}: "
                f"{list(entry.keys())}"
            )
    data = entry.get("data")
    if not isinstance(data, dict):
        raise SchemaDriftError(
            f"gate.log entry 'data' must be a dict, got {type(data).__name__}"
        )
    for f in GATE_LOG_REQUIRED_DATA_FIELDS:
        if f not in data:
            raise SchemaDriftError(
                f"gate.log entry data missing required field {f!r}: "
                f"{list(data.keys())}"
            )
    if not isinstance(data["scrum_blockers"], list):
        raise SchemaDriftError(
            f"gate.log scrum_blockers must be a list, got "
            f"{type(data['scrum_blockers']).__name__}"
        )
    if not isinstance(data["fold_blockers"], list):
        raise SchemaDriftError(
            f"gate.log fold_blockers must be a list, got "
            f"{type(data['fold_blockers']).__name__}"
        )


def _validate_trade_entry(entry: dict) -> None:
    """Validate one parsed trade.log entry against the pinned field lists."""
    for f in TRADE_LOG_REQUIRED_TOP_FIELDS:
        if f not in entry:
            raise SchemaDriftError(
                f"trade.log entry missing top-level field {f!r}: "
                f"{list(entry.keys())}"
            )
    data = entry.get("data")
    if not isinstance(data, dict):
        raise SchemaDriftError(
            f"trade.log entry 'data' must be a dict, got {type(data).__name__}"
        )
    for f in TRADE_LOG_REQUIRED_DATA_FIELDS:
        if f not in data:
            raise SchemaDriftError(
                f"trade.log entry data missing required field {f!r}: "
                f"{list(data.keys())}"
            )


def _parse_ts(s: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp from a log entry.

    Returns ``None`` on parse failure so the caller can filter the entry
    out rather than the whole iteration aborting.
    """
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _iter_ndjson(path: Path) -> Iterator[dict]:
    """Yield parsed JSON dicts from an NDJSON file, one per line.

    Skips blank lines and malformed-JSON lines silently — gate.log
    rotation can briefly produce truncated trailing lines under high
    write load, and aborting the whole read on one bad line would
    block downstream sim parity work.
    """
    if not path.is_file():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _iter_ndjson_lines(path: Path) -> Iterator[str]:
    """Yield non-empty raw lines. Splitting this out from
    ``_iter_ndjson`` lets callers reject a line before paying for
    ``json.loads``."""
    if not path.is_file():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield line


def _parse_line(line: str) -> Optional[dict]:
    """Parse one NDJSON line, or None when malformed.

    A partially-flushed final line is expected under concurrent write
    load; aborting the whole read on one bad line would block sim
    parity work.
    """
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _file_predates(path: Path, since: datetime) -> bool:
    """True when an entire rotated file is older than ``since``.

    Uses mtime only — a file last written before the cutoff cannot
    contain an entry at or after it. Never inspects content: sim parity
    tooling reads through this path, and a content heuristic that
    guessed wrong would silently drop gate decisions.

    The ACTIVE log is never skipped (it is still being appended to, so
    its mtime says nothing about its oldest row); only rotated files,
    which are closed and immutable, are eligible.
    """
    if not path.suffix.lstrip(".").isdigit():
        return False
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    return mtime < since.timestamp()


def _line_predates(line: str, since_prefix: str) -> bool:
    """Reject a line older than ``since`` without parsing it.

    ``timestamp`` is the first key an NDJSON row carries, so its ISO text
    is compared lexicographically against ``since_prefix``. Returns False,
    keeping the line, for anything this cannot read as older.
    """
    head = line[:64]
    i = head.find('"timestamp"')
    if i < 0:
        return False
    j = head.find('"', i + 11)
    if j < 0:
        return False
    k = head.find('"', j + 1)
    if k < 0:
        return False
    stamp = head[j + 1 : k]
    if len(stamp) < 10 or stamp[4] != "-" or stamp[7] != "-":
        return False
    return stamp < since_prefix


def _rotated_files_for(path: Path) -> list[Path]:
    """Return ``[path, path.1, path.2, ...]`` for every rotated copy.

    The active file comes first, then the rotated ones in numeric order.
    """
    files: list[Path] = []
    if path.is_file():
        files.append(path)
    # Any digit suffix matches, so a changed backup count still resolves.
    rotated = sorted(
        path.parent.glob(f"{path.name}.[0-9]*"),
        key=lambda p: int(p.suffix.lstrip(".") or "0"),
    )
    files.extend(rotated)
    return files


def live_gate_decisions(
    since: Optional[datetime] = None, validate: bool = True
) -> Iterator[dict]:
    """Yield gate-decision entries from ``LIVE_GATE_LOG`` and its rotations.

    Args:
        since:    If set, only yield entries with timestamp >= since.
                  Timezone-aware (UTC) datetimes only.
        validate: If True, raise ``SchemaDriftError`` on an entry that does
                  not match the pinned field lists.

    Yields a fresh dict per entry; the caller is free to mutate it.
    """
    since_prefix = since.isoformat()[:19] if since is not None else ""
    for path in _rotated_files_for(LIVE_GATE_LOG):
        if since is not None and _file_predates(path, since):
            continue
        for line in _iter_ndjson_lines(path):
            if since_prefix and _line_predates(line, since_prefix):
                continue
            entry = _parse_line(line)
            if entry is None:
                continue
            if validate:
                _validate_gate_entry(entry)
            # Authoritative check — the raw-text test above is a cheap
            # conservative pre-filter, not a replacement for it.
            if since is not None:
                ts = _parse_ts(entry.get("timestamp", ""))
                if ts is None or ts < since:
                    continue
            yield entry


def live_voting_panel_snapshots(since: Optional[datetime] = None) -> Iterator[dict]:
    """Yield the per-fired-trade snapshots from ``LIVE_VOTING_LOG``.

    Each entry is ``{timestamp, category, bot_id, data}`` with
    ``data.panel`` holding the VotingSummary at fire time; no validator is
    pinned for this shape.

    Args:
        since: If set, only yield entries with timestamp >= since.

    Yields a fresh dict per entry, over the rotated copies as well.
    """
    for path in _rotated_files_for(LIVE_VOTING_LOG):
        for entry in _iter_ndjson(path):
            if since is not None:
                ts = _parse_ts(entry.get("timestamp", ""))
                if ts is None or ts < since:
                    continue
            yield entry


def live_trades(
    since: Optional[datetime] = None, validate: bool = True
) -> Iterator[dict]:
    """Yield trade-fill entries from live's trade.log (ALL trades).

    Args:
        since:    If set, only yield entries with timestamp ≥ since.
        validate: If True (default), raise SchemaDriftError on any
                  entry that does not match the pinned field lists.

    Yields plain dicts. To filter to autonomous fires only, use
    ``live_autonomous_trades`` which adds the
    ``operator_initiated=False`` filter.
    """
    for path in _rotated_files_for(LIVE_TRADE_LOG):
        for entry in _iter_ndjson(path):
            if validate:
                _validate_trade_entry(entry)
            if since is not None:
                ts = _parse_ts(entry.get("timestamp", ""))
                if ts is None or ts < since:
                    continue
            yield entry


def live_autonomous_trades(
    since: Optional[datetime] = None, validate: bool = True
) -> Iterator[dict]:
    """Yield ONLY autonomous (non-operator-initiated) trade fills.

    Args:
        since:    If set, only yield entries with timestamp ≥ since.
        validate: If True (default), raise SchemaDriftError on schema
                  drift.

    Yields plain dicts where ``data.operator_initiated == False``.
    """
    for entry in live_trades(since=since, validate=validate):
        data = entry.get("data", {})
        if not data.get("operator_initiated", False):
            yield entry


def autonomous_fire_count_by_bot(since: Optional[datetime] = None) -> dict[str, int]:
    """Count autonomous fires per bot_id since the given cutoff.

    Convenience helper for the most common parity-tool query: how many
    times did each live bot autonomously fire in the window? The sim
    parity tool compares this to the sim's per-bot fire count from the
    same dataset.
    """
    counts: dict[str, int] = {}
    for entry in live_autonomous_trades(since=since):
        bot_id = str(entry.get("bot_id", "") or "")
        if bot_id:
            counts[bot_id] = counts.get(bot_id, 0) + 1
    return counts


def gate_decision_count_by_bot(since: Optional[datetime] = None) -> dict[str, dict]:
    """Aggregate gate.log per-bot: fire-count + block-count.

    Returns a dict keyed by bot_id with values:
        {
            "scrum_armed": N,
            "fold_armed": N,
            "scrum_blocked": N,
            "fold_blocked": N,
        }

    The sim parity tool compares these against the sim's per-bot
    aggregate to produce the (sim_armed, live_armed) decision matrix
    per-bot aggregate.
    """
    out: dict[str, dict] = {}
    for entry in live_gate_decisions(since=since):
        bot_id = str(entry.get("bot_id", "") or "")
        if not bot_id:
            continue
        data = entry.get("data", {})
        bucket = out.setdefault(
            bot_id,
            {"scrum_armed": 0, "fold_armed": 0, "scrum_blocked": 0, "fold_blocked": 0},
        )
        if data.get("scrum_armed"):
            bucket["scrum_armed"] += 1
        else:
            bucket["scrum_blocked"] += 1
        if data.get("fold_armed"):
            bucket["fold_armed"] += 1
        else:
            bucket["fold_blocked"] += 1
    return out


def layout_summary() -> dict[str, Any]:
    """Return a snapshot of the live log layout for diagnostics.

    Used by parity tools to surface "are the logs where we expect?"
    state to operators before they spawn a comparison run that would
    fail later for trivial path reasons.
    """
    return {
        "live_log_root": str(LIVE_LOG_ROOT),
        "live_log_root_exists": LIVE_LOG_ROOT.is_dir(),
        "gate_log": str(LIVE_GATE_LOG),
        "gate_log_exists": LIVE_GATE_LOG.is_file(),
        "gate_log_size_bytes": (
            LIVE_GATE_LOG.stat().st_size if LIVE_GATE_LOG.is_file() else 0
        ),
        "trade_log": str(LIVE_TRADE_LOG),
        "trade_log_exists": LIVE_TRADE_LOG.is_file(),
        "trade_log_size_bytes": (
            LIVE_TRADE_LOG.stat().st_size if LIVE_TRADE_LOG.is_file() else 0
        ),
    }
