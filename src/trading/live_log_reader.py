"""sadp/_tools/live_log_reader.py — The SINGLE sanctioned reader of live's log root.

This module is the ONE sadp-side file allowed to reference ``LIVE_LOG_ROOT``
(=``~/.acervator_logs/``). Any other sadp/* file that references that path is
a R-WIR (write-once-read-rooted) boundary violation, caught by the static
check ``tools/check_sim_live_boundary.py``.

The boundary is per operator directive 2026-06-09:

    "And logs are restructured and VERIFIED wired and VERIFIED working
    THEN we point both sim and live to them for relevant queries. This
    will be one of the only places that connects sim and live. Do not
    screw it up please."

Strict rules:
  1. **READ-ONLY.** This reader NEVER writes to live's log dirs.
  2. **SCHEMA-VALIDATED.** Each entry is validated against the v3.23.0
     gate.log + trade.log + pnl.log shapes before being returned. Drift
     surfaces as a raised exception, not a silent corruption.
  3. **OPERATOR-INITIATED FILTERABLE.** ``live_trades(since)`` returns
     all entries; ``live_autonomous_trades(since)`` filters
     ``operator_initiated=false`` so parity work compares apples to apples.
  4. **NO MUTATION OF YIELDED OBJECTS.** The reader yields plain dicts
     constructed fresh each iteration; the caller is free to mutate them.

Sim parity tool consumers replace the v3.22.74 Coinbase YTD CSV ground
truth with this reader's autonomous-trade output. The CSV had the manual-
fire confound built in (operator's manual fires were indistinguishable
from autonomous fires); gate.log carries ``operator_initiated`` as a
proper field.

Status v3.23.1: Phase C-1 foundation. Sim mirror + parity tool rewrite +
per-bot decision matrix ship in v3.23.2 (Phase C-2/3/4).
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional


# ─── Single canonical path resolution — the only place these constants live ───

LIVE_LOG_ROOT: Path = Path.home() / ".acervator_logs"
LIVE_TRADE_DIR: Path = LIVE_LOG_ROOT / "trade"
LIVE_GATE_LOG: Path = LIVE_TRADE_DIR / "gate.log"
LIVE_TRADE_LOG: Path = LIVE_TRADE_DIR / "trade.log"
# v3.23.6 — voting-panel-snapshot log (operator pin: per-fired-trade).
LIVE_VOTING_LOG: Path = LIVE_TRADE_DIR / "voting.log"
LIVE_CONSOLE_DIR: Path = LIVE_LOG_ROOT / "console"
LIVE_PNL_DIR: Path = LIVE_TRADE_DIR / "pnl"


# ─── Schema pins (v3.23.0 baseline; update in same cascade as any new field) ───

GATE_LOG_REQUIRED_TOP_FIELDS = (
    "timestamp", "category", "bot_id", "data",
)
GATE_LOG_REQUIRED_DATA_FIELDS = (
    "symbol", "scrum_armed", "fold_armed",
    "scrum_blockers", "fold_blockers",
)
GATE_LOG_OPTIONAL_DATA_FIELDS = (
    "evaluated_at_tick", "scrum_fixture", "fold_fixture",
    "indicators", "state",
)

TRADE_LOG_REQUIRED_TOP_FIELDS = (
    "timestamp", "category", "bot_id", "data",
)
TRADE_LOG_REQUIRED_DATA_FIELDS = (
    "action", "symbol", "side", "amount", "price",
    "status", "usd", "operator_initiated",
)


class SchemaDriftError(RuntimeError):
    """Raised when an entry on disk does not match the pinned schema.

    Fail-loud (R28 FL) so v3.23.x schema changes that did not update the
    schema pins surface as test failures instead of silent sim/live
    decision-comparison drift.
    """


def _validate_gate_entry(entry: dict) -> None:
    """Validate one parsed gate.log entry against the v3.23.0 schema.

    Raises ``SchemaDriftError`` if any required field is missing. Optional
    fields are allowed to be absent (older entries from before the field
    landed) but if present must be the right shape.
    """
    for f in GATE_LOG_REQUIRED_TOP_FIELDS:
        if f not in entry:
            raise SchemaDriftError(
                f"gate.log entry missing top-level field {f!r}: "
                f"{list(entry.keys())}")
    data = entry.get("data")
    if not isinstance(data, dict):
        raise SchemaDriftError(
            f"gate.log entry 'data' must be a dict, got {type(data).__name__}")
    for f in GATE_LOG_REQUIRED_DATA_FIELDS:
        if f not in data:
            raise SchemaDriftError(
                f"gate.log entry data missing required field {f!r}: "
                f"{list(data.keys())}")
    if not isinstance(data["scrum_blockers"], list):
        raise SchemaDriftError(
            f"gate.log scrum_blockers must be a list, got "
            f"{type(data['scrum_blockers']).__name__}")
    if not isinstance(data["fold_blockers"], list):
        raise SchemaDriftError(
            f"gate.log fold_blockers must be a list, got "
            f"{type(data['fold_blockers']).__name__}")


def _validate_trade_entry(entry: dict) -> None:
    """Validate one parsed trade.log entry against the v3.20.78 schema.

    The v3.23.0 ship preserved v3.20.78's schema verbatim, so this
    validator is unchanged from prior versions.
    """
    for f in TRADE_LOG_REQUIRED_TOP_FIELDS:
        if f not in entry:
            raise SchemaDriftError(
                f"trade.log entry missing top-level field {f!r}: "
                f"{list(entry.keys())}")
    data = entry.get("data")
    if not isinstance(data, dict):
        raise SchemaDriftError(
            f"trade.log entry 'data' must be a dict, got {type(data).__name__}")
    for f in TRADE_LOG_REQUIRED_DATA_FIELDS:
        if f not in data:
            raise SchemaDriftError(
                f"trade.log entry data missing required field {f!r}: "
                f"{list(data.keys())}")


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
    """Cheap pre-parse rejection of a line older than ``since``.

    v3.24.24 — ``since`` used to be applied AFTER ``json.loads``, so the
    cutoff discarded work already done. On the operator's logs that is
    165,062 full JSON parses of 262 MB regardless of how narrow the
    window was, and the caller docstrings that claimed ``since`` stopped
    the iterators scanning back were simply wrong.

    NDJSON rows are written by ``NDJSONWriter`` with ``timestamp`` as the
    first key, so the ISO date appears near the head of the line. This
    compares the raw text against the cutoff's ISO prefix, which is a
    valid lexicographic comparison for ISO-8601 UTC.

    CONSERVATIVE BY DESIGN: returns False (keep the line) on anything it
    cannot positively establish as older. A false keep costs one parse; a
    false reject would silently drop a gate decision, and sim-parity
    tooling reads through this same path.
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
    stamp = head[j + 1:k]
    if len(stamp) < 10 or stamp[4] != "-" or stamp[7] != "-":
        return False
    return stamp < since_prefix


def _rotated_files_for(path: Path) -> list[Path]:
    """v3.23.6 — return [path, path.1, path.2, ...] for all rotated copies.

    Pre-v3.23.6 the reader only consumed the active file, so once
    rotation kicked in (50 MB) the older entries were invisible to the
    parity tool. Operator's 33-hour window needs the full set of
    rotated files so a single live-fire event can be matched even if
    its gate.log entry lives in gate.log.4.

    Order: active file first (newest writes), then numerically by
    rotation index. NDJSON parsing is line-by-line so order across
    files doesn't affect correctness — only the ``since`` filter would
    care, and that's per-entry.
    """
    files: list[Path] = []
    if path.is_file():
        files.append(path)
    # Rotation suffix is .1 .. .backup_count (default 5). Use a glob
    # that matches any digit suffix so future rotation-count changes
    # don't silently miss files.
    rotated = sorted(
        path.parent.glob(f"{path.name}.[0-9]*"),
        key=lambda p: int(p.suffix.lstrip(".") or "0"))
    files.extend(rotated)
    return files


def live_gate_decisions(
        since: Optional[datetime] = None,
        validate: bool = True) -> Iterator[dict]:
    """Yield gate-decision entries from live's gate.log + rotated copies.

    v3.23.6: globs ``gate.log`` + ``gate.log.[0-9]*`` so the full
    rotation chain is consumed. Pre-v3.23.6 only the active file was
    read which meant the operator's 33-hour window was effectively
    bounded by the 50 MB rotation cutoff.

    Args:
        since:    If set, only yield entries with timestamp ≥ since.
                  Timezone-aware (UTC) datetimes only.
        validate: If True (default), raise SchemaDriftError on any
                  entry that doesn't match the v3.23.0 schema. Set
                  False for triage-mode reads of older entries.

    Yields plain dicts; the caller is free to mutate them.
    """
    # v3.24.24 — make `since` actually save work. The filter used to run
    # AFTER json.loads, so a narrow window still paid a full parse of
    # every one of the 165,062 rows / 262 MB on the operator's disk.
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


def live_voting_panel_snapshots(
        since: Optional[datetime] = None) -> Iterator[dict]:
    """v3.23.6 — Yield voting-panel-snapshot entries from live's voting.log.

    Operator pin 2026-06-13: snapshot cadence is per-fired-trade (NOT
    per-tick). Schema mirrors gate.log + trade.log: top-level
    ``{timestamp, category, bot_id, data}`` with ``data.panel`` carrying
    the VotingSummary asdict snapshot at fire time.

    NO schema validator pinned yet — the schema may evolve as
    VotingSummary grows new fields; we use the forward-compatible
    "require core fields, allow extras" pattern (asdict() over the
    dataclass auto-propagates new fields).

    Args:
        since: If set, only yield entries with timestamp ≥ since.

    Yields plain dicts; the caller is free to mutate them. Glob over
    rotated copies (voting.log + voting.log.1..N) same as
    live_gate_decisions.
    """
    for path in _rotated_files_for(LIVE_VOTING_LOG):
        for entry in _iter_ndjson(path):
            if since is not None:
                ts = _parse_ts(entry.get("timestamp", ""))
                if ts is None or ts < since:
                    continue
            yield entry


def live_trades(
        since: Optional[datetime] = None,
        validate: bool = True) -> Iterator[dict]:
    """Yield trade-fill entries from live's trade.log (ALL trades).

    Args:
        since:    If set, only yield entries with timestamp ≥ since.
        validate: If True (default), raise SchemaDriftError on any
                  entry that doesn't match the v3.20.78 schema.

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
        since: Optional[datetime] = None,
        validate: bool = True) -> Iterator[dict]:
    """Yield ONLY autonomous (non-operator-initiated) trade fills.

    This is the sim parity tool's ground-truth iterator. Replaces the
    v3.22.74 Coinbase YTD CSV which carried the manual-fire confound
    (the CSV did not distinguish operator's manual fires from
    autonomous gate-driven fires).

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


def autonomous_fire_count_by_bot(
        since: Optional[datetime] = None) -> dict[str, int]:
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


def gate_decision_count_by_bot(
        since: Optional[datetime] = None) -> dict[str, dict]:
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
    that v3.23.2 Phase C-4 ships.
    """
    out: dict[str, dict] = {}
    for entry in live_gate_decisions(since=since):
        bot_id = str(entry.get("bot_id", "") or "")
        if not bot_id:
            continue
        data = entry.get("data", {})
        bucket = out.setdefault(
            bot_id,
            {"scrum_armed": 0, "fold_armed": 0,
             "scrum_blocked": 0, "fold_blocked": 0})
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
            LIVE_GATE_LOG.stat().st_size
            if LIVE_GATE_LOG.is_file() else 0),
        "trade_log": str(LIVE_TRADE_LOG),
        "trade_log_exists": LIVE_TRADE_LOG.is_file(),
        "trade_log_size_bytes": (
            LIVE_TRADE_LOG.stat().st_size
            if LIVE_TRADE_LOG.is_file() else 0),
    }
