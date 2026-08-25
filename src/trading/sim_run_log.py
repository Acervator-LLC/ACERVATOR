"""sim_run_log.py — persist a Fleet Replay run to disk.

Operator directive 2026-08-02, after v3.24.12 isolated the sim's
event bus:

    "Yes, let's implement the persistent log before I build and
    test."

WHY THIS IS NEEDED NOW
======================
v3.24.12 gave sim bots a private EventBus so their fills stop
landing in the live ``trade.log`` (136 rows of measured
contamination). That fixed the pollution but left the sim with no
durable record at all — its trades lived only in
``FleetSimExchange._trades`` for the lifetime of the process, so a
replay's output vanished the moment the run ended and could not be
compared against anything later.

This module gives the sim its own log tree, physically separate
from live:

    ~/.acervator_logs/sim/
        index.json                  every run, newest first
        runs/<run_id>/meta.json     config + summary
        runs/<run_id>/trades.log    NDJSON
        runs/<run_id>/gates.log     NDJSON

SCHEMA PARITY, PHYSICAL SEPARATION
==================================
Rows mirror the LIVE schema field-for-field so the same parsing and
comparison code reads both, with two additions: ``run_id`` and
``origin: "sim"``. The directory split is what guarantees the two
sets can never merge by accident; the ``origin`` field means that
even if a row is copied out of context, it still identifies itself.

A sim row must never be mistaken for a live trade — that is the
whole failure this log exists downstream of.

WRITE DISCIPLINE
================
Appends are buffered and flushed every ``flush_every`` rows (default
200) so a 60k-candle replay does not pay a syscall per tick. The
buffer is flushed on ``finish_run`` and by an explicit ``flush()``.
A crash mid-run loses at most one buffer, and the rows already on
disk stay valid NDJSON because each line is written whole.

sadp: R28 SSS + R70 RCN
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("acervator.sim_run_log")

SIM_LOG_ROOT_ENV = "ACERVATOR_SIM_LOG_ROOT"
"""Override the sim log root.

Set by ``tests/conftest.py`` so the suite never writes into the
operator's runtime tree. This is not a convenience: before v3.24.19
the pin tests wrote real run directories into
``~/.acervator_logs/sim/runs``, and 54 of the 62 directories there
were 4-to-59-candle test artifacts. Diagnosing the GUI slowdown meant
first filtering them back out of the operator's own performance
record. Test output does not belong in a production log tree.
"""


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
"""Hard stop so a runaway replay cannot fill the disk. Reaching it
is itself reported rather than silently truncating."""


def _utc_iso(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(
        ts if ts is not None else time.time(), tz=timezone.utc
    ).isoformat()


@dataclass
class SimRunLog:
    """Durable record of one Fleet Replay run.

    Not thread-safe by design: the replay controller drives it from
    a single asyncio task. If that ever changes, wrap the append
    paths in a lock rather than relying on GIL atomicity.
    """

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

    # ── lifecycle ────────────────────────────────────────────────

    def start_run(self, config: Optional[dict] = None) -> str:
        """Create the run directory and write meta. Returns run_id.

        Never raises: if the directory cannot be created the log
        degrades to a no-op and says so, because losing a sim record
        must not take down the replay itself.
        """
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
        """Flush buffers and stamp the summary. Idempotent."""
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
        """Append one sim fill.

        ``sim_ts_ms`` is MASTER-CLOCK time, not wall clock. Using
        wall clock here would make the row uncomparable to live
        history — the same defect v3.24.5 fixed inside the sim
        exchange.
        """
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
        """Append one sim gate decision, shaped like live gate.log."""
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
        """Subscribe to a sim bot's PRIVATE bus to capture gates.

        v3.24.12 gave each sim bot its own EventBus, which makes this
        safe: subscribing here cannot receive live events, and these
        handlers cannot reach live subscribers. Returns True when the
        subscription was established.
        """
        bus = getattr(bot, "_bus", None)
        if bus is None or not hasattr(bus, "subscribe"):
            return False
        if not getattr(bot, "_sim_mode", False):
            # Refuse to attach to a LIVE bot's bus — that would mean
            # writing live decisions into the sim log.
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
        """Write buffered rows. Safe to call at any time."""
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
                json.dumps(entries[:500], indent=2, default=str), encoding="utf-8"
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
    """Runs on disk, newest first. Empty when none exist."""
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


__all__ = [
    "DEFAULT_FLUSH_EVERY",
    "MAX_ROWS_PER_FILE",
    "ORIGIN_SIM",
    "SIM_LOG_ROOT",
    "SimRunLog",
    "list_runs",
    "load_run_gates",
    "load_run_trades",
]
