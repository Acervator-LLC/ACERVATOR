"""Persist a Fleet Replay run under ~/.acervator_logs/sim/ in the live schema."""

from __future__ import annotations

import json
import logging
import os
import stat
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("acervator.sim_run_log")

SIM_LOG_ROOT_ENV = "ACERVATOR_SIM_LOG_ROOT"
"""Sim log root override; tests/conftest.py sets it away from ~/.acervator_logs."""


def _default_sim_log_root() -> Path:
    override = os.environ.get(SIM_LOG_ROOT_ENV)
    if override:
        return Path(override)
    return Path.home() / ".acervator_logs" / "sim"


SIM_LOG_ROOT: Path = Path.home() / ".acervator_logs" / "sim"
ORIGIN_SIM = "sim"
SCHEMA_VERSION = 1

DEFAULT_FLUSH_EVERY = 200
MAX_ROWS_PER_FILE = 2_000_000
"""Row ceiling across trades and gates; _push warns once then drops rows."""


# ── retention ────────────────────────────────────────────────────

BULK_FILENAMES: tuple[str, ...] = ("signals.jsonl",)
"""Filenames _demote unlinks from a run outside the verbatim window."""

KEEP_VERBATIM_RUNS = 10
"""Newest runs that keep BULK_FILENAMES; _decide demotes every run past this."""

KEEP_RUNS = 200
"""Directory cap for runs/; _decide evicts whole runs past this count."""

MAX_TOTAL_BYTES = 192_000_000
"""Byte budget for runs/ in decimal MB, matching the 1e6 divisor in summary()."""

INDEX_MAX_ENTRIES = 500
"""Entry cap for index.json, applied by _append_index and _rewrite_index."""

MAX_TREE_ENTRIES = 10_000
"""Entry ceiling per run directory; _measure_plain_tree raises past it."""

PROTECTED_TREE_NAME = ".acervator"
"""_resolve_runs_root refuses any target resolving inside ~/.acervator."""


def _utc_iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(
        ts if ts is not None else time.time(), tz=timezone.utc
    ).isoformat()


@dataclass
class SimRunLog:
    """Durable record of one Fleet Replay run, not safe for concurrent callers."""

    run_id: str = ""
    root: Path = field(default_factory=_default_sim_log_root)
    flush_every: int = DEFAULT_FLUSH_EVERY

    _dir: Optional[Path] = None
    _trade_buf: list[str] = field(default_factory=list)
    _gate_buf: list[str] = field(default_factory=list)
    _trade_count: int = 0
    _gate_count: int = 0
    _started_at: float = 0.0
    _meta: dict = field(default_factory=dict)
    _capped: bool = False
    _open: bool = False

    retention: Optional[RetentionResult] = None
    """What _apply_retention returned, or None until finish_run completes."""

    # ── lifecycle ────────────────────────────────────────────────

    def start_run(self, config: Optional[dict] = None) -> str:
        """Create the run directory, write meta.json, and return the run_id."""
        self._started_at = time.time()
        if not self.run_id:
            self.run_id = (
                datetime.fromtimestamp(self._started_at, tz=timezone.utc).strftime(
                    "%Y%m%dT%H%M%S"
                )
                + "_"
                + uuid.uuid4().hex[:6]
            )
        self._meta = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "origin": ORIGIN_SIM,
            "started_at": _utc_iso(self._started_at),
            "config": dict(config or {}),
            "finished_at": None,
            "summary": {},
        }
        try:
            self._dir = self.root / "runs" / self.run_id
            self._dir.mkdir(parents=True, exist_ok=True)
            self._write_meta()
            self._open = True
            logger.info("sim run log opened: %s", self._dir)
        except OSError as exc:
            self._dir = None
            self._open = False
            logger.warning(
                "sim run log unavailable (%s) — run will not be " "persisted", exc
            )
        return self.run_id

    def finish_run(self, summary: Optional[dict] = None) -> None:
        """Flush buffers, stamp the summary, index the run, and apply retention."""
        if not self._open:
            return
        self.flush()
        self._meta["finished_at"] = _utc_iso()
        self._meta["summary"] = dict(summary or {})
        self._meta["summary"].update(
            {
                "trades_logged": self._trade_count,
                "gates_logged": self._gate_count,
                "row_cap_reached": self._capped,
                "duration_s": round(time.time() - self._started_at, 3),
            }
        )
        self._write_meta()
        self._append_index()
        self._open = False
        logger.info(
            "sim run log closed: %s (%d trades, %d gates)",
            self.run_id,
            self._trade_count,
            self._gate_count,
        )
        self.retention = self._apply_retention()

    def _apply_retention(self) -> RetentionResult:
        """Run apply_retention over self.root, protecting this run's id."""
        try:
            return apply_retention(self.root, protect=frozenset({self.run_id}))
        except (
            OSError,
            ValueError,
            TypeError,
            AttributeError,
            KeyError,
            IndexError,
            RuntimeError,
        ) as exc:
            logger.warning("sim retention pass failed: %s", exc)
            return RetentionResult(refused=f"pass raised: {exc}")

    # ── recording ────────────────────────────────────────────────

    def record_trade(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        bot_id: str = "",
        action: str = "",
        usd: float = 0.0,
        sim_ts_ms: Optional[int] = None,
        candle_address: str = "",
        extra: Optional[dict] = None,
    ) -> None:
        """Append one sim fill, timestamped from sim_ts_ms or from wall clock."""
        if not self._open:
            return
        ts_s = (sim_ts_ms / 1000.0) if sim_ts_ms else time.time()
        row = {
            "timestamp": _utc_iso(ts_s),
            "category": "trade.executed",
            "origin": ORIGIN_SIM,
            "run_id": self.run_id,
            "bot_id": bot_id,
            "candle_address": candle_address,
            "data": {
                "action": action or "",
                "symbol": symbol,
                "side": str(side or "").upper(),
                "amount": float(amount or 0.0),
                "price": float(price or 0.0),
                "status": "filled",
                "usd": float(usd or 0.0),
                "operator_initiated": False,
            },
        }
        if extra:
            row["data"].update(extra)
        self._push(self._trade_buf, row, is_trade=True)

    def record_gate(
        self,
        bot_id: str,
        symbol: str,
        gate_state: dict,
        sim_ts_ms: Optional[int] = None,
        candle_address: str = "",
    ) -> None:
        """Append one gate.decision row shaped like the live gate.log schema."""
        if not self._open:
            return
        ts_s = (sim_ts_ms / 1000.0) if sim_ts_ms else time.time()
        gs = gate_state or {}
        row = {
            "timestamp": _utc_iso(ts_s),
            "category": "gate.decision",
            "origin": ORIGIN_SIM,
            "run_id": self.run_id,
            "bot_id": bot_id,
            "candle_address": candle_address,
            "data": {
                "symbol": symbol,
                "scrum_armed": bool(gs.get("scrum_armed", False)),
                "fold_armed": bool(gs.get("fold_armed", False)),
                "scrum_blockers": list(gs.get("scrum_blockers") or []),
                "fold_blockers": list(gs.get("fold_blockers") or []),
                "scrum_fixture": gs.get("scrum_fixture"),
                "fold_fixture": gs.get("fold_fixture"),
            },
        }
        self._push(self._gate_buf, row, is_trade=False)

    def attach_to_bot_bus(self, bot: Any) -> bool:
        """Subscribe _on_bus_gate to a sim bot's private _bus and report success."""
        bus = getattr(bot, "_bus", None)
        if bus is None or not hasattr(bus, "subscribe"):
            return False
        if not getattr(bot, "_sim_mode", False):
            logger.warning(
                "sim_run_log: refusing to attach to non-sim bot %s",
                getattr(bot, "bot_id", "?"),
            )
            return False
        try:
            bus.subscribe("bot.gate_decision", self._on_bus_gate)
        except Exception as exc:  # noqa: BLE001 - bus surface
            logger.debug("sim_run_log: gate subscribe failed: %s", exc)
            return False
        return True

    def _on_bus_gate(self, event: Any) -> None:
        data = getattr(event, "data", None) or {}
        self.record_gate(
            bot_id=str(data.get("bot_id", "") or ""),
            symbol=str(data.get("symbol", "") or ""),
            gate_state=data,
        )

    # ── internals ────────────────────────────────────────────────

    def _push(self, buf: list[str], row: dict, is_trade: bool) -> None:
        total = self._trade_count + self._gate_count
        if total >= MAX_ROWS_PER_FILE:
            if not self._capped:
                self._capped = True
                logger.warning(
                    "sim run log hit the %d-row cap; further rows "
                    "are dropped for run %s",
                    MAX_ROWS_PER_FILE,
                    self.run_id,
                )
            return
        try:
            buf.append(json.dumps(row, separators=(",", ":"), default=str))
        except (TypeError, ValueError) as exc:
            logger.debug("sim_run_log: unserialisable row: %s", exc)
            return
        if is_trade:
            self._trade_count += 1
        else:
            self._gate_count += 1
        if len(buf) >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        """Append buffered trade and gate rows to their files, clearing them."""
        if self._dir is None:
            self._trade_buf.clear()
            self._gate_buf.clear()
            return
        for buf, name in (
            (self._trade_buf, "trades.log"),
            (self._gate_buf, "gates.log"),
        ):
            if not buf:
                continue
            try:
                with (self._dir / name).open("a", encoding="utf-8") as f:
                    f.write("\n".join(buf) + "\n")
                buf.clear()
            except OSError as exc:
                logger.warning("sim_run_log: flush to %s failed: %s", name, exc)
                buf.clear()  # drop rather than grow unbounded

    def _write_meta(self) -> None:
        if self._dir is None:
            return
        try:
            (self._dir / "meta.json").write_text(
                json.dumps(self._meta, indent=2, default=str), encoding="utf-8"
            )
        except OSError as exc:
            logger.debug("sim_run_log: meta write failed: %s", exc)

    def _append_index(self) -> None:
        """Add this run to the discovery index, newest first."""
        idx_path = self.root / "index.json"
        entries: list = []
        try:
            if idx_path.exists():
                loaded = json.loads(idx_path.read_text(encoding="utf-8"))
                if isinstance(loaded, list):
                    entries = loaded
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("sim_run_log: index unreadable, recreating: %s", exc)
            entries = []
        entries = [
            e for e in entries if isinstance(e, dict) and e.get("run_id") != self.run_id
        ]
        entries.insert(
            0,
            {
                "run_id": self.run_id,
                "started_at": self._meta.get("started_at"),
                "finished_at": self._meta.get("finished_at"),
                "trades": self._trade_count,
                "gates": self._gate_count,
            },
        )
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            idx_path.write_text(
                json.dumps(entries[:INDEX_MAX_ENTRIES], indent=2, default=str),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.debug("sim_run_log: index write failed: %s", exc)

    # ── read-back ────────────────────────────────────────────────

    @property
    def directory(self) -> Optional[Path]:
        return self._dir

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def gate_count(self) -> int:
        return self._gate_count


def list_runs(root: Optional[Path] = None) -> list[dict]:
    """Every dict entry in index.json, tombstones included, or empty on error."""
    idx = (root or _default_sim_log_root()) / "index.json"
    try:
        loaded = json.loads(idx.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [e for e in loaded if isinstance(e, dict)]


def load_run_trades(
    run_id: str,
    root: Optional[Path] = None,
) -> list[dict]:
    """Read back one run's sim trades as dicts."""
    return _read_ndjson(
        (root or _default_sim_log_root()) / "runs" / run_id / "trades.log"
    )


def load_run_gates(
    run_id: str,
    root: Optional[Path] = None,
) -> list[dict]:
    """Read back one run's sim gate decisions as dicts."""
    return _read_ndjson(
        (root or _default_sim_log_root()) / "runs" / run_id / "gates.log"
    )


def _read_ndjson(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return out


# -- retention machinery -----------------------------------------


@dataclass(frozen=True)
class RetentionPolicy:
    """The three retention bounds plus enabled, which makes apply_retention refuse."""

    enabled: bool = True
    keep_verbatim: int = KEEP_VERBATIM_RUNS
    keep_runs: int = KEEP_RUNS
    max_total_bytes: int = MAX_TOTAL_BYTES
    bulk_filenames: tuple[str, ...] = BULK_FILENAMES
    index_max_entries: int = INDEX_MAX_ENTRIES


@dataclass
class RetentionResult:
    """What one pass did; a non-empty refused means nothing on disk was touched."""

    scanned: int = 0
    demoted: int = 0
    evicted: int = 0
    skipped: int = 0
    bytes_reclaimed: int = 0
    bytes_total_after: int = 0
    verbatim_kept: int = 0
    index_dropped: int = 0
    floor_held: bool = False
    refused: str = ""
    demoted_run_ids: list[str] = field(default_factory=list)
    evicted_run_ids: list[str] = field(default_factory=list)
    skipped_reasons: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Build one log line of run counts, bytes reclaimed and the window."""
        if self.refused:
            return f"sim retention refused: {self.refused}"
        return (
            f"sim retention: {self.scanned} runs, "
            f"{self.demoted} demoted, {self.evicted} evicted, "
            f"{self.skipped} skipped, "
            f"{self.bytes_reclaimed / 1e6:.1f} MB reclaimed, "
            f"{self.bytes_total_after / 1e6:.1f} MB left, "
            f"verbatim window {self.verbatim_kept}"
            + (" (floor held)" if self.floor_held else "")
        )


class _UnsafeTreeError(Exception):
    """Raised for a reparse point, an unreadable directory, or a failed rmdir."""


@dataclass
class _RunFacts:
    name: str
    path: Path
    key: tuple
    total_bytes: int
    bulk_bytes: int


_RUN_ID_LEN = 15
"""Characters in the %Y%m%dT%H%M%S run-id prefix: 8 date, T, 6 time."""


def _is_reparse(path: Path) -> bool:
    """Report whether path is a symlink, a reparse point, or unclassifiable."""
    try:
        st = path.lstat()
    except OSError:
        return True
    if stat.S_ISLNK(st.st_mode):
        return True
    return bool(getattr(st, "st_reparse_tag", 0))


def _resolve_runs_root(root: Path) -> tuple[Optional[Path], str]:
    """Return (<root>/runs, "") or (None, reason) for any target it refuses."""
    runs = Path(root) / "runs"
    try:
        real = runs.resolve(strict=True)
    except OSError:
        return None, f"no runs directory under {root}"
    if not real.is_dir():
        return None, f"{real} is not a directory"
    if real.name != "runs":
        return None, f"{runs} resolves to {real}, which is not 'runs'"
    try:
        protected = (Path.home() / PROTECTED_TREE_NAME).resolve()
    except OSError:  # pragma: no cover
        protected = Path.home() / PROTECTED_TREE_NAME
    if real == protected or protected in real.parents:
        return None, f"{real} is inside the protected tree {protected}"
    return real, ""


def _safe_run_dir(runs_root: Path, name: str) -> Optional[Path]:
    """Return runs_root/name when it is a plain, real, direct child directory."""
    if not name or name in (".", ".."):
        return None
    if name != Path(name).name:
        return None
    if any(ch in name for ch in ("/", "\\", ":", "\0")):
        return None
    cand = runs_root / name
    if _is_reparse(cand):
        return None
    try:
        real = cand.resolve(strict=True)
    except OSError:
        return None
    if real.parent != runs_root:
        return None
    if not real.is_dir():
        return None
    return cand


def _measure_plain_tree(path: Path) -> int:
    """Measure bytes under path, raising _UnsafeTreeError on any unsafe entry."""
    total = 0
    seen = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            entries = list(os.scandir(current))
        except OSError as exc:
            msg = f"{path.name}: unreadable ({exc})"
            raise _UnsafeTreeError(msg) from exc
        for entry in entries:
            seen += 1
            if seen > MAX_TREE_ENTRIES:
                msg = f"{path.name}: over {MAX_TREE_ENTRIES} entries"
                raise _UnsafeTreeError(msg)
            child = Path(entry.path)
            if _is_reparse(child):
                msg = f"{path.name}: reparse point at {entry.name}"
                raise _UnsafeTreeError(msg)
            if entry.is_dir(follow_symlinks=False):
                stack.append(child)
            else:
                try:
                    total += int(entry.stat(follow_symlinks=False).st_size)
                except OSError:
                    continue
    return total


def _remove_plain_tree(path: Path) -> int:
    """Delete path and contents, refusing any reparse point, and return bytes freed."""
    freed = 0
    try:
        entries = list(os.scandir(path))
    except OSError as exc:
        msg = f"{path.name}: unreadable ({exc})"
        raise _UnsafeTreeError(msg) from exc
    for entry in entries:
        child = Path(entry.path)
        if _is_reparse(child):
            msg = f"{path.name}: reparse point at {entry.name}"
            raise _UnsafeTreeError(msg)
        if entry.is_dir(follow_symlinks=False):
            freed += _remove_plain_tree(child)
        else:
            try:
                freed += int(entry.stat(follow_symlinks=False).st_size)
                child.unlink()
            except OSError:
                continue
    try:
        path.rmdir()
    except OSError as exc:
        msg = f"{path.name}: rmdir failed ({exc})"
        raise _UnsafeTreeError(msg) from exc
    return freed


def _looks_like_run_id(name: str) -> bool:
    """Report whether name opens with the %Y%m%dT%H%M%S prefix start_run builds."""
    head = name[:_RUN_ID_LEN]
    if len(head) != _RUN_ID_LEN or head[8] != "T":
        return False
    return head[:8].isdigit() and head[9:].isdigit()


def _sort_key(run_dir: Path) -> tuple:
    """Build a newest-first key, reading meta.json when the name lacks the prefix."""
    name = run_dir.name
    if _looks_like_run_id(name):
        return (name[:_RUN_ID_LEN], name)
    started = ""
    try:
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        if isinstance(meta, dict):
            started = str(meta.get("started_at") or "")
    except (OSError, json.JSONDecodeError, ValueError):
        started = ""
    return (started, name)


def _stamp_demotion(
    run_dir: Path,
    removed: list[str],
    freed: int,
) -> None:
    """Write a retention block into the run's meta.json before the unlink."""
    meta_path = run_dir / "meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if not isinstance(meta, dict):
            return
    except (OSError, json.JSONDecodeError, ValueError):
        return
    meta["retention"] = {
        "demoted_at": _utc_iso(),
        "removed": sorted(removed),
        "bytes_removed": int(freed),
        "digest_retained": (run_dir / "signals.digest.jsonl").exists(),
    }
    try:
        meta_path.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    except OSError as exc:
        logger.debug("sim retention: meta stamp failed: %s", exc)


def _rewrite_index(
    root: Path,
    runs_root: Path,
    on_disk: set,
    evicting: set,
    demoting: set,
    max_entries: int,
) -> int:
    """Tombstone evicting runs, mark demoting ones, and return entries dropped."""
    idx_path = Path(root) / "index.json"
    entries: list = []
    try:
        loaded = json.loads(idx_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            entries = [e for e in loaded if isinstance(e, dict)]
    except (OSError, json.JSONDecodeError, ValueError):
        entries = []

    now = _utc_iso()
    seen: set = set()
    for entry in entries:
        run_id = str(entry.get("run_id") or "")
        seen.add(run_id)
        # run_id is a label here; no filesystem path is built from it.
        if run_id in evicting:
            entry["pruned"] = True
            entry["pruned_at"] = now
            entry["pruned_reason"] = "retention"
        elif run_id not in on_disk and not entry.get("pruned"):
            entry["pruned"] = True
            entry["pruned_at"] = now
            entry["pruned_reason"] = "missing"
        if run_id in demoting:
            entry["verbatim"] = False

    for name in sorted(on_disk - seen, reverse=True):
        run_dir = runs_root / name
        started = ""
        finished = None
        try:
            meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                started = str(meta.get("started_at") or "")
                finished = meta.get("finished_at")
        except (OSError, json.JSONDecodeError, ValueError):
            started = ""
        entries.append(
            {
                "run_id": name,
                "started_at": started,
                "finished_at": finished,
                "trades": None,
                "gates": None,
                "recovered": True,
            }
        )

    # start_run derives run_id from started_at, so both sort chronologically.
    entries.sort(
        key=lambda e: str(e.get("started_at") or e.get("run_id") or ""), reverse=True
    )
    dropped = max(0, len(entries) - max_entries)
    entries = entries[:max_entries]
    try:
        Path(root).mkdir(parents=True, exist_ok=True)
        idx_path.write_text(
            json.dumps(entries, indent=2, default=str), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("sim retention: index rewrite failed: %s", exc)
    return dropped


def _scan(
    runs_root: Path,
    pol: RetentionPolicy,
    res: RetentionResult,
) -> Optional[list[_RunFacts]]:
    """Measure every run directory newest-first, or None when the listing failed."""
    facts: list[_RunFacts] = []
    try:
        names = [e.name for e in os.scandir(runs_root)]
    except OSError as exc:
        res.refused = f"cannot list {runs_root}: {exc}"
        logger.warning("sim retention: %s", res.refused)
        return None
    for name in names:
        run_dir = _safe_run_dir(runs_root, name)
        if run_dir is None:
            res.skipped += 1
            res.skipped_reasons.append(f"{name}: not a plain run directory")
            continue
        try:
            total = _measure_plain_tree(run_dir)
        except _UnsafeTreeError as exc:
            res.skipped += 1
            res.skipped_reasons.append(str(exc))
            continue
        bulk = 0
        for fname in pol.bulk_filenames:
            fpath = run_dir / fname
            if _is_reparse(fpath):
                continue
            try:
                bulk += fpath.stat().st_size
            except OSError:
                continue
        facts.append(
            _RunFacts(
                name=name,
                path=run_dir,
                key=_sort_key(run_dir),
                total_bytes=total,
                bulk_bytes=bulk,
            )
        )
    facts.sort(key=lambda f: f.key, reverse=True)  # newest first
    return facts


def _evict(
    facts: list[_RunFacts],
    evict_idx: set,
    res: RetentionResult,
) -> None:
    """Remove whole run directories, recording an unsafe tree in skipped_reasons."""
    for i in sorted(evict_idx):
        fact = facts[i]
        try:
            freed = _remove_plain_tree(fact.path)
        except _UnsafeTreeError as exc:
            res.skipped += 1
            res.skipped_reasons.append(str(exc))
            res.errors.append(str(exc))
            continue
        res.evicted += 1
        res.bytes_reclaimed += freed
        res.evicted_run_ids.append(fact.name)


def _demote(
    facts: list[_RunFacts],
    demote_idx: set,
    pol: RetentionPolicy,
    res: RetentionResult,
) -> None:
    """Unlink pol.bulk_filenames from runs outside the verbatim window."""
    for i in sorted(demote_idx):
        fact = facts[i]
        planned: list = []
        freed = 0
        for fname in pol.bulk_filenames:
            fpath = fact.path / fname
            if _is_reparse(fpath):
                res.skipped_reasons.append(
                    f"{fact.name}/{fname}: reparse point, left alone"
                )
                continue
            try:
                freed += fpath.stat().st_size
            except OSError:
                continue
            planned.append(fname)
        if not planned:
            continue
        _stamp_demotion(fact.path, planned, freed)
        removed: list = []
        for fname in planned:
            try:
                (fact.path / fname).unlink()
            except OSError as exc:
                res.errors.append(f"{fact.name}/{fname}: {exc}")
                continue
            removed.append(fname)
        if not removed:
            continue
        res.demoted += 1
        res.bytes_reclaimed += freed
        res.demoted_run_ids.append(fact.name)


def _decide(
    facts: list[_RunFacts],
    pol: RetentionPolicy,
    keep_ids: frozenset,
    live_bytes: int,
) -> tuple[set, set, int, bool]:
    """Choose (demote_idx, evict_idx, verbatim_kept, floor_held), writing nothing."""
    n = len(facts)

    # 1. DEMOTE everything outside the verbatim window.
    window = max(1, int(pol.keep_verbatim))
    demote_idx = {i for i in range(window, n) if facts[i].bulk_bytes > 0}

    def _projected() -> int:
        return live_bytes - sum(facts[i].bulk_bytes for i in demote_idx)

    # 2. Over budget: demote inward from min(window, n) - 1 before evicting.
    i = min(window, n) - 1
    while _projected() > pol.max_total_bytes and i >= 1:
        if facts[i].bulk_bytes > 0:
            demote_idx.add(i)
        i -= 1
    verbatim_kept = sum(
        1 for j in range(n) if j not in demote_idx and facts[j].bulk_bytes > 0
    )

    # 3. COUNT CAP. Oldest first, never the newest, never protected.
    cap = max(1, int(pol.keep_runs))
    evict_idx: set = {
        i for i in range(n - 1, cap - 1, -1) if i != 0 and facts[i].name not in keep_ids
    }

    # 4. BYTE CAP. Last resort: whole runs, oldest first.
    def _after_evictions() -> int:
        gone = sum(facts[i].bulk_bytes for i in demote_idx if i not in evict_idx)
        gone += sum(facts[i].total_bytes for i in evict_idx)
        return live_bytes - gone

    i = n - 1
    while _after_evictions() > pol.max_total_bytes and i >= 1:
        if i not in evict_idx and facts[i].name not in keep_ids:
            evict_idx.add(i)
        i -= 1

    # floor_held: the newest run alone exceeds max_total_bytes.
    floor_held = _after_evictions() > pol.max_total_bytes
    return demote_idx, evict_idx, verbatim_kept, floor_held


def apply_retention(
    root: Optional[Path] = None,
    *,
    policy: Optional[RetentionPolicy] = None,
    protect: Optional[frozenset] = None,
) -> RetentionResult:
    """Bound <root>/runs/; protect names run_ids that must survive the bounds."""
    pol = policy or RetentionPolicy()
    res = RetentionResult()
    if not pol.enabled:
        res.refused = "policy disabled"
        return res
    base = Path(root) if root is not None else _default_sim_log_root()
    runs_root, reason = _resolve_runs_root(base)
    if runs_root is None:
        res.refused = reason
        logger.warning("sim retention: %s", reason)
        return res

    keep_ids = frozenset(protect or ())

    # -- phase A: measure. Nothing is written. ---------------------
    facts = _scan(runs_root, pol, res)
    if facts is None:
        return res
    res.scanned = len(facts)
    on_disk = {f.name for f in facts}
    if not facts:
        res.index_dropped = _rewrite_index(
            base, runs_root, on_disk, set(), set(), pol.index_max_entries
        )
        logger.info("%s", res.summary())
        return res

    live_bytes = sum(f.total_bytes for f in facts)
    demote_idx, evict_idx, res.verbatim_kept, res.floor_held = _decide(
        facts, pol, keep_ids, live_bytes
    )
    evicting = {facts[i].name for i in evict_idx}
    demoting = {facts[i].name for i in demote_idx if i not in evict_idx}

    # -- phase B: the record, BEFORE the removal. -----------------
    res.index_dropped = _rewrite_index(
        base, runs_root, on_disk - evicting, evicting, demoting, pol.index_max_entries
    )

    # -- phase C: the removal. ------------------------------------
    _evict(facts, evict_idx, res)
    _demote(facts, demote_idx - evict_idx, pol, res)

    res.bytes_total_after = max(0, live_bytes - res.bytes_reclaimed)
    logger.info("%s", res.summary())
    return res


__all__ = [
    "BULK_FILENAMES",
    "DEFAULT_FLUSH_EVERY",
    "INDEX_MAX_ENTRIES",
    "KEEP_RUNS",
    "KEEP_VERBATIM_RUNS",
    "MAX_ROWS_PER_FILE",
    "MAX_TOTAL_BYTES",
    "MAX_TREE_ENTRIES",
    "ORIGIN_SIM",
    "PROTECTED_TREE_NAME",
    "SIM_LOG_ROOT",
    "RetentionPolicy",
    "RetentionResult",
    "SimRunLog",
    "apply_retention",
    "list_runs",
    "load_run_gates",
    "load_run_trades",
]
