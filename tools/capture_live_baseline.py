"""Capture one diffable snapshot of the live runtime trees.

`capture` reads build identity, fleet state, gate-latch distribution, console
log classes and emitter coverage, and `write_snapshot` puts one JSON document
under `OUTPUT_DIR`. `compare` splits its findings into DRIFT for vocabularies
and identities, and MOVEMENT for counts, prices and timestamps. Every path
under `RUNTIME_DIR` and `LOG_DIR` is opened read-only.

    python -m tools.capture_live_baseline
    python -m tools.capture_live_baseline --compare BEFORE.json AFTER.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = Path.home() / ".acervator"
LOG_DIR = Path.home() / ".acervator_logs"
OUTPUT_DIR = REPO_ROOT / "_logs"

SCHEMA_VERSION = 2
ROTATION_SUFFIXES = ("", ".1", ".2", ".3", ".4", ".5")
TICKER_MIN_LEN = 2
TICKER_MAX_LEN = 10
DEFAULT_MOVEMENT_LIMIT = 40

_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_PAIR = re.compile(r"\b[A-Z0-9]{2,10}/[A-Z]{2,6}\b")
_BOT_ID = re.compile(r"\bBot [0-9a-f]{6,}\b")
_HEX_ID = re.compile(r"(?<![\w.])(?=[0-9a-f]*[a-f])[0-9a-f]{8,}(?![\w.])")
_WHITESPACE = re.compile(r"\s+")
_CONSOLE_LINE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d{1,6} \[([A-Z]+)\] (.*)$"
)

_HOME_FORMS = (
    str(Path.home()).replace("\\", "\\\\"),
    str(Path.home()),
    Path.home().as_posix(),
)

_PLACEHOLDER_TOKENS = frozenset({"SYM", "ID", "N"})
_SECRET_MARKERS = ("credential", "secret", "apikey", "api_key", "passphrase")

Json = dict[str, Any]


def as_number(value: object) -> float | None:
    """Coerce exact int and float to float; every other type returns None.

    Exact types, not isinstance: `bool` is a subclass of `int` and would
    otherwise be booked as 1.0.
    """
    if type(value) is int:
        return float(value)
    if type(value) is float:
        return value
    return None


def normalise_blocker(text: str) -> str:
    """Collapse every number in a gate blocker string to `#`.

    Direction and flag names survive; they are vocabulary, not measurement.
    """
    return _NUMBER.sub("#", text)


def build_symbol_pattern(assets: Iterable[str]) -> re.Pattern[str] | None:
    """Compile a whole-word alternation over the `assets` tickers, longest first.

    Returns None when no ticker between `TICKER_MIN_LEN` and `TICKER_MAX_LEN`
    is supplied.
    """
    usable = sorted(
        {
            a
            for a in assets
            if a
            and a.isupper()
            and TICKER_MIN_LEN <= len(a) <= TICKER_MAX_LEN
            and a not in _PLACEHOLDER_TOKENS
        },
        key=lambda a: (-len(a), a),
    )
    if not usable:
        return None
    alternation = "|".join(re.escape(a) for a in usable)
    return re.compile(rf"\b(?:{alternation})\b")


def normalise_message(text: str, symbols: re.Pattern[str] | None = None) -> str:
    """Collapse a log message to its class key.

    Pairs, bot ids, numbers and `_HOME_FORMS` become `_PLACEHOLDER_TOKENS`, and
    `symbols` collapses bare tickers as well.
    """
    out = text
    for form in _HOME_FORMS:
        out = out.replace(form, "~")
    out = _PAIR.sub("<SYM>", out)
    out = _BOT_ID.sub("Bot <ID>", out)
    out = _HEX_ID.sub("<ID>", out)
    if symbols is not None:
        out = symbols.sub("<SYM>", out)
    out = _NUMBER.sub("#", out)
    return _WHITESPACE.sub(" ", out).strip()


def extract_symbol(text: str, symbols: re.Pattern[str] | None = None) -> str:
    """Return the first trading pair or bare ticker in a message, or ''."""
    pair = _PAIR.search(text)
    if pair:
        return pair.group(0)
    if symbols is not None:
        bare = symbols.search(text)
        if bare:
            return bare.group(0)
    return ""


def extract_bot_id(text: str) -> str:
    """Return the bot id named in a message, or ''."""
    match = _BOT_ID.search(text)
    return match.group(0).split(" ", 1)[1] if match else ""


def display_path(path: Path) -> str:
    """Render a path home-relative so snapshots stay machine-independent."""
    resolved = path.resolve()
    try:
        return "~/" + resolved.relative_to(Path.home()).as_posix()
    except ValueError:
        pass
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return resolved.name


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


def _assert_not_secret(path: Path) -> None:
    """Refuse any path whose name looks like a credential store."""
    lowered = path.name.lower()
    for marker in _SECRET_MARKERS:
        if marker in lowered:
            message = f"refusing to read {path.name}: looks like a secret store"
            raise ValueError(message)


def rotation_members(base: Path) -> list[Path]:
    """Return the existing members of a `logging` rotation set, live file first."""
    candidates = (base.with_name(base.name + s) for s in ROTATION_SUFFIXES)
    return [p for p in candidates if p.is_file()]


def live_member_only(base: Path) -> list[Path]:
    """Return only the live member of a rotation set."""
    return [base] if base.is_file() else []


def _file_provenance(path: Path) -> Json:
    stat = path.stat()
    return {
        "path": display_path(path),
        "size_bytes": stat.st_size,
        "mtime_utc": _iso(stat.st_mtime),
        "lines": 0,
        "records": 0,
        "malformed": 0,
        "first_ts": None,
        "last_ts": None,
    }


def _widen(window: Json, stamp: object) -> None:
    """Extend a first_ts/last_ts pair to include one ISO timestamp."""
    if not isinstance(stamp, str) or not stamp:
        return
    first = window.get("first_ts")
    last = window.get("last_ts")
    if first is None or stamp < first:
        window["first_ts"] = stamp
    if last is None or stamp > last:
        window["last_ts"] = stamp


def _bump(bucket: Json, key: str, example: str) -> None:
    slot = bucket.get(key)
    if slot is None:
        bucket[key] = {"count": 1, "example": example}
    else:
        slot["count"] += 1


def _read_lines(path: Path) -> Iterator[str]:
    _assert_not_secret(path)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        yield from handle


def read_resolved_version(root: Path) -> str | None:
    """Version the tree at `root` resolves to, or None when nothing answers.

    Read from the git tag through `src._version`, never from a literal.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from src._version import UNKNOWN_VERSION, resolve_version
    except ImportError:
        return None
    version = resolve_version(root)
    return None if version == UNKNOWN_VERSION else version


def _git_identity() -> Json:
    """HEAD sha and tracked-dirty flag, via the gate wrapper that owns git."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from tools.gate import head_sha, tree_is_dirty
    except ImportError:
        return {"git_head": None, "git_dirty_tracked": None}
    return {"git_head": head_sha() or None, "git_dirty_tracked": tree_is_dirty()}


def capture_build(root: Path) -> Json:
    """Resolved version, git HEAD, tracked-dirty flag and the gate stamp."""
    stamp_path = root / ".gate_stamp.json"
    stamp: Any = None
    if stamp_path.is_file():
        try:
            stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            stamp = {"unreadable": type(exc).__name__}
    return {
        "version": read_resolved_version(root),
        **_git_identity(),
        "gate_stamp": stamp,
    }


def _lot_units(lots: object) -> float:
    if not isinstance(lots, list):
        return 0.0
    return sum(
        as_number(lot.get("units")) or 0.0 for lot in lots if isinstance(lot, dict)
    )


def _tranche_totals(tranches: object) -> tuple[int, float, float]:
    if not isinstance(tranches, list):
        return 0, 0.0, 0.0
    rows = [t for t in tranches if isinstance(t, dict)]
    usd = sum(as_number(t.get("usd")) or 0.0 for t in rows)
    units = sum(as_number(t.get("units")) or 0.0 for t in rows)
    return len(tranches), usd, units


def _accrued(state: Json) -> float | None:
    target = as_number(state.get("target_balance"))
    anchor = as_number(state.get("anchor_target_balance"))
    if target is None or anchor is None:
        return None
    return round(target - anchor, 8)


def _bot_row(bot: Json) -> Json:
    cfg = bot.get("config") or {}
    st = bot.get("scrumming_state") or {}
    stats = bot.get("stats") or {}
    fold_n, fold_usd, fold_units = _tranche_totals(st.get("fold_tranches"))
    stack_n, stack_usd, stack_units = _tranche_totals(st.get("stack_tranches"))
    lots = st.get("main_lots")
    return {
        "identity": {
            "symbol": cfg.get("symbol"),
            "target_asset": cfg.get("target_asset"),
            "base_currency": cfg.get("base_currency"),
            "exchange_id": cfg.get("exchange_id"),
            "mode": cfg.get("mode"),
            "anchor_target_balance": st.get("anchor_target_balance"),
            "max_target_growth_pct": cfg.get("max_target_growth_pct"),
            "state_when_saved": bot.get("state_when_saved"),
        },
        "position": {
            "target_balance": st.get("target_balance"),
            "accrued_growth_usd": _accrued(st),
            "position_value_usd": stats.get("position_value"),
            "position_units": round(_lot_units(lots), 8),
            "current_price": stats.get("current_price"),
            "lot_count": len(lots) if isinstance(lots, list) else 0,
            "fold_tranche_count": fold_n,
            "fold_tranche_usd": round(fold_usd, 8),
            "fold_tranche_units": round(fold_units, 8),
            "stack_tranche_count": stack_n,
            "stack_tranche_usd": round(stack_usd, 8),
            "stack_tranche_units": round(stack_units, 8),
            "fold_queue_usd": st.get("fold_queue_usd"),
            "cash_balance_usd": stats.get("cash_balance_usd"),
            "total_folded_usd": stats.get("total_folded_usd"),
            "tranches_created_lifetime": st.get("tranches_created_lifetime"),
            "tranches_closed_lifetime": st.get("tranches_closed_lifetime"),
            "last_trade_side": st.get("last_trade_side"),
            "last_trade_price": st.get("last_trade_price"),
        },
    }


def _wire_state(payload: Json) -> Json:
    wires = payload.get("smart_wires")
    ledgers = payload.get("smart_wire_ledgers")
    edges: list[Json] = []
    if isinstance(wires, list):
        edges = [
            {
                "source_id": w.get("source_id"),
                "target_id": w.get("target_id"),
                "pct": w.get("pct"),
            }
            for w in wires
            if isinstance(w, dict)
        ]
    ledger_rows: Json = {}
    if isinstance(ledgers, list):
        for row in ledgers:
            if not isinstance(row, dict):
                continue
            ledger_rows[str(row.get("bot_id"))] = {
                "asset": row.get("asset"),
                "wired_in": row.get("wired_in"),
                "wired_out": row.get("wired_out"),
                "starting_balance": row.get("starting_balance"),
                "total_profit": row.get("total_profit"),
            }
    return {
        "edge_count": len(edges),
        "edges": sorted(
            edges, key=lambda e: (str(e["source_id"]), str(e["target_id"]))
        ),
        "ledger_count": len(ledger_rows),
        "ledgers": ledger_rows,
    }


def _fleet_totals(rows: Json) -> Json:
    def total(section: str, field: str) -> float:
        return round(
            sum(as_number(r[section].get(field)) or 0.0 for r in rows.values()), 8
        )

    modes: dict[str, int] = {}
    for row in rows.values():
        mode = str(row["identity"].get("mode"))
        modes[mode] = modes.get(mode, 0) + 1
    return {
        "bot_count": len(rows),
        "symbols": sorted({str(r["identity"].get("symbol")) for r in rows.values()}),
        "modes": modes,
        "target_balance_usd": total("position", "target_balance"),
        "anchor_target_balance_usd": total("identity", "anchor_target_balance"),
        "accrued_growth_usd": total("position", "accrued_growth_usd"),
        "position_value_usd": total("position", "position_value_usd"),
        "cash_balance_usd": total("position", "cash_balance_usd"),
        "fold_tranche_count": int(total("position", "fold_tranche_count")),
        "fold_tranche_usd": total("position", "fold_tranche_usd"),
        "stack_tranche_count": int(total("position", "stack_tranche_count")),
        "stack_tranche_usd": total("position", "stack_tranche_usd"),
        "lot_count": int(total("position", "lot_count")),
        "fold_queue_usd": total("position", "fold_queue_usd"),
    }


def capture_fleet(state_path: Path) -> Json:
    """Read bot_state once, bracketed by stat calls to expose a mid-read write."""
    _assert_not_secret(state_path)
    if not state_path.is_file():
        return {"source": {"path": display_path(state_path), "present": False}}
    before = state_path.stat()
    raw = state_path.read_text(encoding="utf-8", errors="replace")
    after = state_path.stat()
    source: Json = {
        "path": display_path(state_path),
        "present": True,
        "size_before": before.st_size,
        "size_after": after.st_size,
        "mtime_before_utc": _iso(before.st_mtime),
        "mtime_after_utc": _iso(after.st_mtime),
        "changed_during_read": (
            before.st_mtime != after.st_mtime or before.st_size != after.st_size
        ),
    }
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        source["decode_error"] = f"{type(exc).__name__}: {exc}"
        return {"source": source}
    source["state_format_version"] = payload.get("version")
    source["saved_at_utc"] = _iso(as_number(payload.get("saved_at")))
    source["declared_bot_count"] = payload.get("bot_count")
    bots = payload.get("bots")
    rows: Json = {}
    if isinstance(bots, dict):
        for bot_id, bot in bots.items():
            if isinstance(bot, dict):
                rows[str(bot_id)] = _bot_row(bot)
    return {
        "source": source,
        "totals": _fleet_totals(rows),
        "bots": rows,
        "wires": _wire_state(payload),
    }


def _gate_bot_slot(bots: Json, bot_id: str) -> Json:
    slot = bots.get(bot_id)
    if slot is None:
        slot = {
            "symbol": None,
            "events": 0,
            "scrum_armed": 0,
            "fold_armed": 0,
            "scrum_blockers": {},
            "fold_blockers": {},
        }
        bots[bot_id] = slot
    return slot


def _gate_record(record: Json, bots: Json, totals: Json) -> bool:
    """Fold one gate record into the per-bot tallies. False when unusable."""
    data = record.get("data")
    if not isinstance(data, dict):
        return False
    slot = _gate_bot_slot(bots, str(record.get("bot_id")))
    slot["symbol"] = data.get("symbol") or slot["symbol"]
    slot["events"] += 1
    totals["events"] += 1
    for side in ("scrum", "fold"):
        if data.get(f"{side}_armed"):
            slot[f"{side}_armed"] += 1
            totals[f"{side}_armed"] += 1
        blockers = data.get(f"{side}_blockers")
        if isinstance(blockers, list):
            for blocker in blockers:
                if isinstance(blocker, str):
                    _bump(slot[f"{side}_blockers"], normalise_blocker(blocker), blocker)
    return True


def _blocker_vocabulary(bots: Json) -> Json:
    out: Json = {"scrum": {}, "fold": {}}
    for slot in bots.values():
        for side in ("scrum", "fold"):
            for key, entry in slot[f"{side}_blockers"].items():
                agg = out[side].get(key)
                if agg is None:
                    out[side][key] = {
                        "count": entry["count"],
                        "example": entry["example"],
                    }
                else:
                    agg["count"] += entry["count"]
    return out


def capture_gate(paths: list[Path], since: str | None = None) -> Json:
    """Latch counts and normalised blocker distributions over a rotation set."""
    files: list[Json] = []
    bots: Json = {}
    totals: Json = {
        "events": 0,
        "scrum_armed": 0,
        "fold_armed": 0,
        "malformed": 0,
        "skipped_by_since": 0,
        "first_ts": None,
        "last_ts": None,
    }
    for path in paths:
        prov = _file_provenance(path)
        for line in _read_lines(path):
            prov["lines"] += 1
            try:
                record = json.loads(line)
            except ValueError:
                prov["malformed"] += 1
                totals["malformed"] += 1
                continue
            if not isinstance(record, dict):
                prov["malformed"] += 1
                totals["malformed"] += 1
                continue
            stamp = record.get("timestamp")
            if since and isinstance(stamp, str) and stamp < since:
                totals["skipped_by_since"] += 1
                continue
            if not _gate_record(record, bots, totals):
                prov["malformed"] += 1
                totals["malformed"] += 1
                continue
            prov["records"] += 1
            _widen(prov, stamp)
            _widen(totals, stamp)
        files.append(prov)
    return {
        "source": "gate JSON lines",
        "since_filter": since,
        "files": files,
        "totals": totals,
        "bots": bots,
        "blocker_vocabulary": _blocker_vocabulary(bots),
    }


def _record_class(bucket: Json, message: str, symbols: re.Pattern[str] | None) -> None:
    key = normalise_message(message, symbols)
    slot = bucket.get(key)
    if slot is None:
        slot = {"count": 0, "example": message, "by_symbol": {}, "by_bot": {}}
        bucket[key] = slot
    slot["count"] += 1
    symbol = extract_symbol(message, symbols)
    if symbol:
        slot["by_symbol"][symbol] = slot["by_symbol"].get(symbol, 0) + 1
    bot_id = extract_bot_id(message)
    if bot_id:
        slot["by_bot"][bot_id] = slot["by_bot"].get(bot_id, 0) + 1


def capture_console(
    paths: list[Path],
    symbols: re.Pattern[str] | None = None,
    levels: tuple[str, ...] = ("ERROR", "CRITICAL", "WARNING"),
) -> Json:
    """Level counts plus normalised message classes for the named levels."""
    files: list[Json] = []
    level_counts: dict[str, int] = {}
    classes: Json = {level: {} for level in levels}
    totals = {"lines": 0, "records": 0, "continuations": 0}
    window: Json = {"first_ts": None, "last_ts": None}
    for path in paths:
        prov = _file_provenance(path)
        for line in _read_lines(path):
            prov["lines"] += 1
            totals["lines"] += 1
            match = _CONSOLE_LINE.match(line.rstrip("\n"))
            if match is None:
                prov["malformed"] += 1
                totals["continuations"] += 1
                continue
            stamp, level, message = match.groups()
            prov["records"] += 1
            totals["records"] += 1
            _widen(prov, stamp)
            _widen(window, stamp)
            level_counts[level] = level_counts.get(level, 0) + 1
            if level in classes:
                _record_class(classes[level], message, symbols)
        files.append(prov)
    return {
        "source": "console text lines",
        "files": files,
        "totals": totals,
        "window": window,
        "levels": level_counts,
        "classes": classes,
    }


def load_declared_pins() -> dict[str, str]:
    """Return the declared pin roster, or an empty map if it cannot load."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        from src.core.signal_contract import CADENCE_BY_NAME
    except ImportError:
        return {}
    return dict(CADENCE_BY_NAME)


def declared_pin_for(name: str, declared: dict[str, str]) -> str | None:
    """Resolve an emitted name to its declared pin, template names included."""
    if name in declared:
        return name
    for pattern in declared:
        if pattern.count("{}") != 1:
            continue
        head, _, tail = pattern.partition("{}")
        if (
            name.startswith(head)
            and name.endswith(tail)
            and len(name) > len(head) + len(tail)
        ):
            return pattern
    return None


def _window_hours(first: str | None, last: str | None) -> float:
    if not first or not last:
        return 0.0
    try:
        start = datetime.fromisoformat(first)
        end = datetime.fromisoformat(last)
    except ValueError:
        return 0.0
    return max((end - start).total_seconds() / 3600.0, 0.0)


def _emitter_report(
    files: list[Json], totals: Json, seen: Json, declared: dict[str, str]
) -> Json:
    hours = _window_hours(totals["first_ts"], totals["last_ts"])
    resolved: dict[str, int] = {}
    undeclared: list[str] = []
    for name, slot in seen.items():
        pin = declared_pin_for(name, declared)
        slot["declared_pin"] = pin
        slot["cadence"] = declared.get(pin) if pin else None
        slot["per_hour"] = round(slot["count"] / hours, 3) if hours else None
        if pin is None:
            undeclared.append(name)
        else:
            resolved[pin] = resolved.get(pin, 0) + slot["count"]
    silent = sorted(pin for pin in declared if pin not in resolved)
    return {
        "source": "signal JSON lines",
        "files": files,
        "totals": totals,
        "window_hours": round(hours, 4) if hours else None,
        "declared_count": len(declared),
        "seen_names": dict(sorted(seen.items())),
        "seen_declared_pins": dict(sorted(resolved.items())),
        "silent_declared_pins": silent,
        "silent_by_cadence": {pin: declared[pin] for pin in silent},
        "undeclared_names": sorted(undeclared),
    }


def capture_emitters(paths: list[Path], declared: dict[str, str]) -> Json:
    """Per-pin emission counts and rates, plus the declared pins never seen."""
    files: list[Json] = []
    seen: Json = {}
    totals: Json = {
        "records": 0,
        "malformed": 0,
        "first_ts": None,
        "last_ts": None,
    }
    for path in paths:
        prov = _file_provenance(path)
        for line in _read_lines(path):
            prov["lines"] += 1
            try:
                record = json.loads(line)
            except ValueError:
                prov["malformed"] += 1
                totals["malformed"] += 1
                continue
            name = record.get("name") if isinstance(record, dict) else None
            if not isinstance(name, str):
                prov["malformed"] += 1
                totals["malformed"] += 1
                continue
            stamp = record.get("ts")
            prov["records"] += 1
            totals["records"] += 1
            _widen(prov, stamp)
            _widen(totals, stamp)
            slot = seen.get(name)
            if slot is None:
                slot = {
                    "count": 0,
                    "first_ts": None,
                    "last_ts": None,
                    "module": record.get("module"),
                }
                seen[name] = slot
            slot["count"] += 1
            _widen(slot, stamp)
        files.append(prov)
    return _emitter_report(files, totals, seen, declared)


def capture(*, rotations: bool = True, since: str | None = None) -> Json:
    """Build the whole snapshot document."""
    started = time.time()
    fleet = capture_fleet(RUNTIME_DIR / "bot_state.json")
    assets = [
        str(row["identity"].get("target_asset"))
        for row in fleet.get("bots", {}).values()
    ]
    symbols = build_symbol_pattern(assets)
    picker: Callable[[Path], list[Path]] = (
        rotation_members if rotations else live_member_only
    )
    gate = capture_gate(picker(LOG_DIR / "trade" / "gate.log"), since=since)
    console = capture_console(picker(LOG_DIR / "console" / "system.log"), symbols)
    declared = load_declared_pins()
    emitters = capture_emitters(picker(LOG_DIR / "signals" / "session.jsonl"), declared)
    return {
        "schema_version": SCHEMA_VERSION,
        "capture": {
            "captured_at_utc": _iso(started),
            "duration_s": round(time.time() - started, 3),
            "runtime_dir": display_path(RUNTIME_DIR),
            "log_dir": display_path(LOG_DIR),
            "rotations": rotations,
            "since": since,
        },
        "build": capture_build(REPO_ROOT),
        "fleet": fleet,
        "gate_latch": gate,
        "console_classes": console,
        "emitters": emitters,
    }


def default_output_path(snapshot: Json, out_dir: Path) -> Path:
    """Name the file so two captures sort chronologically and diff cleanly."""
    stamp = (snapshot["capture"]["captured_at_utc"] or "")[:19]
    stamp = stamp.replace("-", "").replace(":", "")
    version = snapshot["build"].get("version") or "unknown"
    return out_dir / f"live_baseline_{stamp}Z_v{version}.json"


def write_snapshot(snapshot: Json, path: Path) -> Path:
    """Write a snapshot as sorted, indented JSON and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


_BOT_IDENTITY_FIELDS = (
    "symbol",
    "target_asset",
    "base_currency",
    "exchange_id",
    "mode",
    "anchor_target_balance",
    "max_target_growth_pct",
)

_BOT_POSITION_FIELDS = (
    "target_balance",
    "accrued_growth_usd",
    "position_value_usd",
    "position_units",
    "lot_count",
    "fold_tranche_count",
    "fold_tranche_usd",
    "stack_tranche_count",
    "stack_tranche_usd",
    "fold_queue_usd",
)


def _delta(label: str, left: object, right: object) -> str | None:
    lnum, rnum = as_number(left), as_number(right)
    if lnum is None or rnum is None:
        return f"{label} {left!r} -> {right!r}" if left != right else None
    if lnum == rnum:
        return None
    return f"{label} {lnum:.8g} -> {rnum:.8g} ({rnum - lnum:+.8g})"


def _cmp_map(left: Json, right: Json, prefix: str, sink: list[str]) -> None:
    for key in sorted(set(left) | set(right)):
        line = _delta(f"{prefix}.{key}", left.get(key), right.get(key))
        if line:
            sink.append(line)


def _cmp_build(a: Json, b: Json, out: Json) -> None:
    left, right = a.get("build", {}), b.get("build", {})
    for field in ("version", "git_head", "git_dirty_tracked", "gate_stamp"):
        if left.get(field) != right.get(field):
            out["identity"].append(
                f"build.{field}: {left.get(field)!r} -> {right.get(field)!r}"
            )


def _symbol_of(row: Json) -> object:
    return row.get("identity", {}).get("symbol")


def _cmp_fleet(a: Json, b: Json, out: Json) -> None:
    left = a.get("fleet", {}).get("bots", {}) or {}
    right = b.get("fleet", {}).get("bots", {}) or {}
    for bot_id in sorted(set(left) - set(right)):
        out["drift"].append(f"fleet: bot {bot_id} REMOVED ({_symbol_of(left[bot_id])})")
    for bot_id in sorted(set(right) - set(left)):
        out["drift"].append(f"fleet: bot {bot_id} ADDED ({_symbol_of(right[bot_id])})")
    for bot_id in sorted(set(left) & set(right)):
        li, ri = left[bot_id]["identity"], right[bot_id]["identity"]
        for field in _BOT_IDENTITY_FIELDS:
            if li.get(field) != ri.get(field):
                out["drift"].append(
                    f"fleet: bot {bot_id} {field} "
                    f"{li.get(field)!r} -> {ri.get(field)!r}"
                )
        lp, rp = left[bot_id]["position"], right[bot_id]["position"]
        for field in _BOT_POSITION_FIELDS:
            line = _delta(f"fleet: bot {bot_id} {field}", lp.get(field), rp.get(field))
            if line:
                out["movement"].append(line)
    _cmp_map(
        a.get("fleet", {}).get("totals", {}) or {},
        b.get("fleet", {}).get("totals", {}) or {},
        "fleet.totals",
        out["movement"],
    )
    lw = (a.get("fleet", {}).get("wires") or {}).get("edges") or []
    rw = (b.get("fleet", {}).get("wires") or {}).get("edges") or []
    if lw != rw:
        out["drift"].append(
            f"fleet: smart wire topology changed ({len(lw)} -> {len(rw)} edges)"
        )


def _cmp_gate(a: Json, b: Json, out: Json) -> None:
    left, right = a.get("gate_latch", {}), b.get("gate_latch", {})
    for side in ("scrum", "fold"):
        lv = (left.get("blocker_vocabulary") or {}).get(side) or {}
        rv = (right.get("blocker_vocabulary") or {}).get(side) or {}
        for key in sorted(set(lv) - set(rv)):
            out["drift"].append(
                f"gate: {side} blocker class GONE {key!r} (was {lv[key]['count']})"
            )
        for key in sorted(set(rv) - set(lv)):
            out["drift"].append(
                f"gate: {side} blocker class NEW {key!r} (now {rv[key]['count']})"
            )
        for key in sorted(set(lv) & set(rv)):
            line = _delta(
                f"gate: {side} blocker {key!r}", lv[key]["count"], rv[key]["count"]
            )
            if line:
                out["movement"].append(line)
    _cmp_map(
        left.get("totals") or {},
        right.get("totals") or {},
        "gate.totals",
        out["movement"],
    )
    lb, rb = left.get("bots") or {}, right.get("bots") or {}
    for bot_id in sorted(set(lb) - set(rb)):
        out["drift"].append(f"gate: bot {bot_id} no longer latching")
    for bot_id in sorted(set(rb) - set(lb)):
        out["drift"].append(f"gate: bot {bot_id} newly latching")


def _cmp_console(a: Json, b: Json, out: Json) -> None:
    left, right = a.get("console_classes", {}), b.get("console_classes", {})
    _cmp_map(
        left.get("levels") or {},
        right.get("levels") or {},
        "console.levels",
        out["movement"],
    )
    lc, rc = left.get("classes") or {}, right.get("classes") or {}
    for level in sorted(set(lc) | set(rc)):
        lm, rm = lc.get(level) or {}, rc.get(level) or {}
        for key in sorted(set(lm) - set(rm)):
            out["drift"].append(
                f"console: {level} class GONE {key!r} (was {lm[key]['count']})"
            )
        for key in sorted(set(rm) - set(lm)):
            out["drift"].append(
                f"console: {level} class NEW {key!r} (now {rm[key]['count']})"
            )
        for key in sorted(set(lm) & set(rm)):
            line = _delta(
                f"console: {level} {key!r}", lm[key]["count"], rm[key]["count"]
            )
            if line:
                out["movement"].append(line)


def _cmp_emitters(a: Json, b: Json, out: Json) -> None:
    left, right = a.get("emitters", {}), b.get("emitters", {})
    ls = set(left.get("silent_declared_pins") or [])
    rs = set(right.get("silent_declared_pins") or [])
    for pin in sorted(rs - ls):
        out["drift"].append(f"emitters: pin WENT SILENT {pin}")
    for pin in sorted(ls - rs):
        out["drift"].append(f"emitters: pin CAME ALIVE {pin}")
    lu = set(left.get("undeclared_names") or [])
    ru = set(right.get("undeclared_names") or [])
    for name in sorted(ru - lu):
        out["drift"].append(f"emitters: undeclared name NEW {name}")
    for name in sorted(lu - ru):
        out["drift"].append(f"emitters: undeclared name GONE {name}")
    _cmp_map(
        left.get("seen_declared_pins") or {},
        right.get("seen_declared_pins") or {},
        "emitters.count",
        out["movement"],
    )


def compare(a: Json, b: Json) -> dict[str, list[str]]:
    """Diff two snapshots into identity, drift and movement findings."""
    out: dict[str, list[str]] = {"identity": [], "drift": [], "movement": []}
    _cmp_build(a, b, out)
    _cmp_fleet(a, b, out)
    _cmp_gate(a, b, out)
    _cmp_console(a, b, out)
    _cmp_emitters(a, b, out)
    return out


def _stamp_line(label: str, snapshot: Json) -> str:
    cap = snapshot.get("capture", {})
    build = snapshot.get("build", {})
    head = (build.get("git_head") or "?")[:8]
    dirty = "dirty" if build.get("git_dirty_tracked") else "clean"
    return (
        f"  {label}  captured {cap.get('captured_at_utc')}"
        f"  v{build.get('version')}  head {head} {dirty}"
    )


def format_comparison(
    a: Json,
    b: Json,
    findings: dict[str, list[str]],
    movement_limit: int = DEFAULT_MOVEMENT_LIMIT,
) -> str:
    """Render a comparison as text, with movement truncated to a limit."""
    lines = ["BASELINE COMPARISON", _stamp_line("A", a), _stamp_line("B", b), ""]
    for title, key in (("BUILD IDENTITY", "identity"), ("DRIFT", "drift")):
        rows = findings[key]
        lines.append(f"{title} ({len(rows)})")
        if rows:
            lines.extend(f"  {row}" for row in rows)
        else:
            lines.append("  none")
        lines.append("")
    rows = findings["movement"]
    lines.append(f"MOVEMENT ({len(rows)})")
    if not rows:
        lines.append("  none")
        return "\n".join(lines)
    shown = rows if movement_limit <= 0 else rows[:movement_limit]
    lines.extend(f"  {row}" for row in shown)
    if len(rows) > len(shown):
        lines.append(f"  ... {len(rows) - len(shown)} further moved values")
    return "\n".join(lines)


def load_snapshot(path: str | Path) -> Json:
    """Read one snapshot document off disk."""
    loaded = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        message = f"{path} is not a snapshot document"
        raise TypeError(message)
    return loaded


def build_parser() -> argparse.ArgumentParser:
    """Return the command line parser for capture and compare modes."""
    parser = argparse.ArgumentParser(
        prog="capture_live_baseline",
        description="Capture or compare a live runtime baseline snapshot.",
    )
    parser.add_argument("--out", help="write the snapshot here instead of _logs/")
    parser.add_argument(
        "--no-rotations",
        action="store_true",
        help="read only the live log of each set, not its rotated members",
    )
    parser.add_argument("--since", help="drop gate records with a timestamp below this")
    parser.add_argument(
        "--compare", nargs=2, metavar=("A", "B"), help="diff two snapshot files"
    )
    parser.add_argument(
        "--movement-limit",
        type=int,
        default=DEFAULT_MOVEMENT_LIMIT,
        help="movement lines to print before truncating; 0 prints all",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="exit 1 when a comparison reports drift",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Capture a snapshot, or compare two. Returns the process exit code."""
    args = build_parser().parse_args(argv)
    if args.compare:
        left = load_snapshot(args.compare[0])
        right = load_snapshot(args.compare[1])
        findings = compare(left, right)
        print(format_comparison(left, right, findings, args.movement_limit))
        return 1 if (args.fail_on_drift and findings["drift"]) else 0
    snapshot = capture(rotations=not args.no_rotations, since=args.since)
    target = Path(args.out) if args.out else default_output_path(snapshot, OUTPUT_DIR)
    write_snapshot(snapshot, target)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
