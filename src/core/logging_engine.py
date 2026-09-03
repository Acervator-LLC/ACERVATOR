from __future__ import annotations

"""
logging_engine.py — Structured trade & gate-decision logging
============================================================

Provides three log categories:

  1. **Trade log** — every order placed, filled, cancelled, or failed.
  2. **Gate-decision log** — one entry per bot per tick recording
     whether the scrum and fold chains armed or which blockers held
     them back.
  3. **P/L log** — periodic profit/loss snapshots at configurable
     intervals (24 h to 1 year). Weekly, monthly and yearly windows
     each concatenate the daily NDJSON files under their date range.

All logs are newline-delimited JSON (NDJSON). A ``LogManager``
orchestrates the writers and their rotation, and resolves every
bucket path through ``src/core/log_paths.py`` so the location is the
same regardless of build mode.
"""

import json
import logging
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Callable, Optional

from src.core.log_paths import (
    get_trade_dir,
    get_console_dir,
    get_pnl_dir,
)


def _emergency_stderr(text: str) -> bool:
    """Write one line to ``sys.stderr``; return whether it landed.

    Last-resort channel for a fault inside the logging engine itself,
    used only when the system logger is the one that failed. Probes
    ``sys.stderr`` with ``getattr`` rather than assuming it exists,
    since a windowed launch runs with ``sys.stderr`` set to ``None``.
    """
    stream = getattr(sys, "stderr", None)
    write = getattr(stream, "write", None)
    if write is None:
        return False
    try:
        write(text + "\n")
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Log entry types
# ---------------------------------------------------------------------------
class LogCategory(str, Enum):
    """Universal log-entry category enum."""

    TRADE = "trade"
    PNL = "pnl"
    SYSTEM = "system"
    GATE = "gate"  # One entry per bot per tick.


@dataclass
class LogEntry:
    """Universal log entry — serialisable to JSON."""

    timestamp: str = ""
    category: str = ""
    exchange: str = ""
    bot_id: str = ""
    data: dict = field(default_factory=dict)
    highlight: bool = False  # True if entry is near a scrumming trade

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


# ---------------------------------------------------------------------------
# NDJSON file writer with rotation
# ---------------------------------------------------------------------------
class NDJSONWriter:
    """
    Append-only NDJSON writer with size-based rotation.

    Files rotate at *max_bytes* (default 50 MB).  Rotated files get a
    numeric suffix: ``trade.log``, ``trade.log.1``, ``trade.log.2`` …
    up to *backup_count* backups.
    """

    def __init__(
        self,
        path: Path,
        max_bytes: int = 50 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        self._path = path
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._lock = Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, entry: LogEntry) -> None:
        """Append one log entry (thread-safe)."""
        line = entry.to_json() + "\n"
        with self._lock:
            self._rotate_if_needed()
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)

    def read_all(self) -> list[dict]:
        """Read all entries from the current log file."""
        if not self._path.exists():
            return []
        entries = []
        with open(self._path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return entries

    def _rotate_if_needed(self) -> None:
        if not self._path.exists():
            return
        if self._path.stat().st_size < self._max_bytes:
            return
        # Uses Path.replace(), not Path.rename(), which raises WinError
        # 183 on Windows when the destination already exists.
        for i in range(self._backup_count - 1, 0, -1):
            src = self._path.parent / f"{self._path.name}.{i}"
            dst = self._path.parent / f"{self._path.name}.{i + 1}"
            if src.exists():
                src.replace(dst)
        # Current → .1
        backup = self._path.parent / f"{self._path.name}.1"
        self._path.replace(backup)


# ---------------------------------------------------------------------------
# Bounded handler for the standard-library "acervator" logger
# ---------------------------------------------------------------------------
SYSTEM_LOG_MAX_BYTES = 50 * 1024 * 1024
"""Rotation threshold for ``console/system.log``, matching every
``NDJSONWriter`` bucket in this module."""

SYSTEM_LOG_BACKUP_COUNT = 5
"""Backups kept for ``console/system.log``. Bounds its footprint at
6 x 50 MB = 300 MB total."""


class SizeBoundedFileHandler(RotatingFileHandler):
    """``RotatingFileHandler`` whose backup shift cannot raise WinError 183.

    Overrides ``doRollover`` to shift backups with ``Path.replace()``
    instead of the stdlib's ``os.rename``, which raises WinError 183
    on Windows when the destination already exists. If ``replace()``
    or a reopen still fails — the destination held open by another
    process raises WinError 5, a stale one WinError 32 — the stream is
    cleared to ``None`` before the shift runs rather than left bound
    to a closed file object. ``shouldRollover`` and
    ``FileHandler.emit`` both reopen whenever ``self.stream is None``,
    so a failed rollover costs one record instead of leaving the
    handler silently closed for the rest of the process.
    """

    def _shift(self, source: str, dest: str) -> None:
        """Move `source` onto `dest`, overwriting, if `source` exists."""
        if callable(self.rotator):
            self.rotator(source, dest)
            return
        src = Path(source)
        if src.exists():
            src.replace(Path(dest))

    def doRollover(self) -> None:
        """Shift the backups and start a new current file.

        Clears ``self.stream`` to ``None`` before the shift, then
        reopens unconditionally in a ``finally`` — so a raise during
        the shift or the reopen still leaves the handler able to
        retry on the next record instead of holding a closed stream.
        """
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        try:
            if self.backupCount > 0:
                for i in range(self.backupCount - 1, 0, -1):
                    self._shift(
                        self.rotation_filename("%s.%d" % (self.baseFilename, i)),
                        self.rotation_filename("%s.%d" % (self.baseFilename, i + 1)),
                    )
                self._shift(
                    self.baseFilename, self.rotation_filename(self.baseFilename + ".1")
                )
        finally:
            self.stream = self._open()


# ---------------------------------------------------------------------------
# P/L log cascade — larger periods concatenate smaller ones
# ---------------------------------------------------------------------------
class PnLCascade:
    """
    Maintains P/L snapshots at multiple periodicities. The daily log is
    the atomic unit; weekly, monthly and yearly logs each concatenate
    the daily files under their own date range directly, not each other.

    Directory layout, under ``trade/pnl/``::

        daily/    ← one NDJSON per day
        weekly/   ← 7 daily files concatenated
        monthly/  ← 30 daily files concatenated
        yearly/   ← 365 daily files concatenated
    """

    PERIODS = {
        "daily": 1,
        "weekly": 7,
        "monthly": 30,
        "yearly": 365,
    }

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        for period in self.PERIODS:
            (self._base / period).mkdir(parents=True, exist_ok=True)

    def record_daily(self, entry: LogEntry) -> None:
        """Append a P/L entry to today's daily log."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._base / "daily" / f"{today}.ndjson"
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")

    def build_weekly(self, week_start: str) -> list[dict]:
        """Concatenate 7 daily logs starting from *week_start* (YYYY-MM-DD)."""
        return self._concat_days(week_start, 7, "weekly")

    def build_monthly(self, month_start: str) -> list[dict]:
        """Concatenate ~30 daily logs starting from *month_start*."""
        return self._concat_days(month_start, 30, "monthly")

    def build_yearly(self, year_start: str) -> list[dict]:
        """Concatenate ~365 daily logs starting from *year_start*."""
        return self._concat_days(year_start, 365, "yearly")

    def _concat_days(self, start: str, count: int, output_dir: str) -> list[dict]:
        from datetime import timedelta

        start_date = datetime.strptime(start, "%Y-%m-%d")
        entries: list[dict] = []
        for i in range(count):
            day = (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
            path = self._base / "daily" / f"{day}.ndjson"
            if path.exists():
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
        # Save the concatenated result
        out_path = self._base / output_dir / f"{start}_{count}d.ndjson"
        with open(out_path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
        return entries


# ---------------------------------------------------------------------------
# Log manager — orchestrates all writers
# ---------------------------------------------------------------------------
class LogManager:
    """
    Central logging orchestrator. Call ``log_trade()``,
    ``log_gate_decision()``, ``log_voting_panel_snapshot()`` or
    ``log_pnl()`` from any thread; the manager routes to the correct
    writer and handles rotation.

    Also configures Python's ``logging`` module for system-level messages.
    """

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        # Set before anything else can fail: _note_internal_failure's
        # except blocks assume this already exists.
        self._internal_failures: dict[str, int] = {}

        # ``log_dir`` is for test injection only (a tmp_path); production
        # always resolves paths through the log_paths bucket helpers.
        if log_dir is not None:
            # Test-injection path: place trade.log + pnl/ + system.log
            # under the supplied dir to keep the existing test surface.
            self._dir = log_dir
            self._dir.mkdir(parents=True, exist_ok=True)
            self._trade_dir = self._dir
            self._console_dir = self._dir
            self._pnl_root = self._dir / "pnl"
            self._pnl_root.mkdir(parents=True, exist_ok=True)
        else:
            # Production path: bucket helpers resolve everything under
            # ~/.acervator_logs/{trade,console,trade/pnl}.
            self._trade_dir = get_trade_dir()
            self._console_dir = get_console_dir()
            self._pnl_root = get_pnl_dir()
            # self._dir points at the trade bucket, where trade.log,
            # gate.log and pnl/ all land.
            self._dir = self._trade_dir

        self._trade_writer = NDJSONWriter(self._trade_dir / "trade.log")
        self._gate_writer = NDJSONWriter(self._trade_dir / "gate.log")
        # Routes the `bot.log` bus topic to disk, unfiltered, bounded
        # the same as every writer here: 50 MB x 5 backups.
        self._diag_writer = NDJSONWriter(self._trade_dir / "diagnostics.log")
        # One entry per fired trade, not per tick.
        self._voting_writer = NDJSONWriter(self._trade_dir / "voting.log")
        self._pnl_cascade = PnLCascade(self._pnl_root)

        # Maps bot_id -> symbol, used by the bus handlers below when
        # an event carries none.
        self._symbol_resolver: Optional[Callable[[str], str]] = None

        # System logger (Python standard logging)
        self._sys_logger = logging.getLogger("acervator")
        self._sys_logger.setLevel(logging.DEBUG)
        self._sys_logger.propagate = False  # Don't duplicate to root logger
        if not self._sys_logger.handlers:
            # errors="replace": the default Windows codec (cp1252) raises
            # on this codebase's arrow and em-dash glyphs, dropping the record.
            handler = SizeBoundedFileHandler(
                self._console_dir / "system.log",
                maxBytes=SYSTEM_LOG_MAX_BYTES,
                backupCount=SYSTEM_LOG_BACKUP_COUNT,
                encoding="utf-8",
                errors="replace",
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
            )
            self._sys_logger.addHandler(handler)

    # -- Internal-failure reporting -------------------------------------
    def _note_internal_failure(self, where: str, exc: BaseException) -> None:
        """Record a fault inside the logging engine's own plumbing.

        Must not raise for any input, since every caller is an
        ``except`` block guarding the trading loop. Tries three
        channels in order: the ``_internal_failures`` counter (read via
        ``internal_failure_counts()``), then ``self._sys_logger``, then
        ``sys.stderr`` if the system logger itself is the casualty.
        """
        kind = type(exc).__name__
        self._internal_failures[where] = self._internal_failures.get(where, 0) + 1
        try:
            self._sys_logger.warning(
                "LogManager internal failure at %s: %s: %s", where, kind, exc
            )
        except Exception as log_exc:
            self._internal_failures["_sys_logger"] = (
                self._internal_failures.get("_sys_logger", 0) + 1
            )
            landed = _emergency_stderr(
                f"[LogManager] internal failure at {where}: {kind} "
                f"(system logger also failed: "
                f"{type(log_exc).__name__})"
            )
            if not landed:
                self._internal_failures["_stderr"] = (
                    self._internal_failures.get("_stderr", 0) + 1
                )

    def internal_failure_counts(self) -> dict[str, int]:
        """Return a copy of the per-site internal-failure counters.

        A non-empty result means the logging engine swallowed at least
        one fault to protect the trading loop. The two reserved keys
        ``_sys_logger`` and ``_stderr`` count failures of the report
        channels themselves; every other key is a call site.
        """
        return dict(self._internal_failures)

    def set_symbol_resolver(self, resolver: "Callable[[str], str]") -> None:
        """Register a bot_id -> symbol lookup function.

        Used as a fallback by ``_on_trade_filled_bus``,
        ``_on_gate_decision_bus``, ``_on_voting_panel_snapshot_bus`` and
        ``_on_bot_log_bus`` whenever the bus event carries no symbol of
        its own. ``_on_pnl_event_bus`` does not call it.
        """
        self._symbol_resolver = resolver

    # -- Trade logging --------------------------------------------------
    def log_trade(
        self,
        exchange: str,
        bot_id: str,
        action: str,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        status: str = "filled",
        extra: Optional[dict] = None,
    ) -> None:
        """Log a trade event."""
        data = {
            "action": action,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "status": status,
        }
        if extra:
            data.update(extra)
        entry = LogEntry(
            category=LogCategory.TRADE.value,
            exchange=exchange,
            bot_id=bot_id,
            data=data,
        )
        self._trade_writer.write(entry)

    # -- Gate-decision logging -------------------------------------------
    def log_gate_decision(
        self,
        exchange: str,
        bot_id: str,
        symbol: str,
        scrum_armed: bool,
        fold_armed: bool,
        scrum_blockers: Optional[list] = None,
        fold_blockers: Optional[list] = None,
        evaluated_at_tick: Optional[int] = None,
        scrum_fixture: Optional[dict] = None,
        fold_fixture: Optional[dict] = None,
        indicators: Optional[dict] = None,
        state_snapshot: Optional[dict] = None,
        extra: Optional[dict] = None,
    ) -> None:
        """Log one gate-decision event per bot per tick, written to
        ``gate.log``. The sanctioned connection point for sim and live
        to read the same decision data.

        Args:
            exchange:           Source exchange tag.
            bot_id:             Bot identifier.
            symbol:             Asset symbol.
            scrum_armed:        True if scrum chain decided to fire.
            fold_armed:         True if fold chain decided to fire.
            scrum_blockers:     Ordered list of gate names that blocked
                                the scrum chain (empty when armed=True).
            fold_blockers:      Same for fold chain.
            evaluated_at_tick:  Loop-tick counter or wall-clock proxy.
            scrum_fixture:      The full chain-result fixture for scrum
                                (gate names + pass/block per stage).
            fold_fixture:       Same for fold chain.
            indicators:         Snapshot of indicator values that drove
                                the decision (bb_pos, delta_pct, etc.).
            state_snapshot:     Bot state (holdings, target, fold_tranches).
            extra:              Free-form passthrough for forensic context.
        """
        data: dict = {
            "symbol": symbol,
            "scrum_armed": bool(scrum_armed),
            "fold_armed": bool(fold_armed),
            "scrum_blockers": list(scrum_blockers or []),
            "fold_blockers": list(fold_blockers or []),
        }
        if evaluated_at_tick is not None:
            data["evaluated_at_tick"] = int(evaluated_at_tick)
        if scrum_fixture is not None:
            data["scrum_fixture"] = scrum_fixture
        if fold_fixture is not None:
            data["fold_fixture"] = fold_fixture
        if indicators is not None:
            data["indicators"] = indicators
        if state_snapshot is not None:
            data["state"] = state_snapshot
        if extra:
            data.update(extra)
        entry = LogEntry(
            category=LogCategory.GATE.value,
            exchange=exchange,
            bot_id=bot_id,
            data=data,
        )
        self._gate_writer.write(entry)

    # -- Voting-panel-snapshot logging ------------------------------------
    def log_voting_panel_snapshot(
        self,
        exchange: str,
        bot_id: str,
        symbol: str,
        side: str,
        trade_action: str,
        panel: Optional[dict] = None,
        extra: Optional[dict] = None,
    ) -> None:
        """Log one voting-panel snapshot at trade-execution time, not
        per tick. ScrummingBot emits ``bot.voting_panel_snapshot``
        immediately after each ``trade.filled`` so the panel state that
        drove the decision is captured at the moment it became action.

        Args:
            exchange:     Source exchange tag.
            bot_id:       Bot identifier.
            symbol:       Asset symbol.
            side:         BUY / SELL.
            trade_action: SCRUM / FOLD / ENTRY / HEDGE / DIST / etc.
            panel:        VotingSummary asdict snapshot. May be {} for
                          early ticks with no summary yet.
            extra:        Free-form forensic context.
        """
        data: dict = {
            "symbol": symbol,
            "side": str(side or "").upper(),
            "trade_action": str(trade_action or "") or "",
            "panel": panel if isinstance(panel, dict) else {},
        }
        if extra:
            data.update(extra)
        # Own writer and stream, not the GATE category, so consumers
        # can filter on category="voting" alone.
        entry = LogEntry(
            category="voting",
            exchange=exchange,
            bot_id=bot_id,
            data=data,
        )
        self._voting_writer.write(entry)

    # -- P/L logging ----------------------------------------------------
    def log_pnl(
        self,
        exchange: str,
        bot_id: str,
        realised_pnl: float,
        unrealised_pnl: float,
        total_trades: int,
        extra: Optional[dict] = None,
    ) -> None:
        """Record a P/L snapshot (goes into the daily cascade)."""
        data = {
            "realised_pnl": realised_pnl,
            "unrealised_pnl": unrealised_pnl,
            "total_trades": total_trades,
        }
        if extra:
            data.update(extra)
        entry = LogEntry(
            category=LogCategory.PNL.value,
            exchange=exchange,
            bot_id=bot_id,
            data=data,
        )
        self._pnl_cascade.record_daily(entry)

    # -- Event-bus attachment ------------------------------------------
    def attach_to_bus(self, bus) -> None:
        """Subscribe every bus-fed writer in this module: trade fills,
        P/L events, gate decisions, voting-panel snapshots and bot.log
        diagnostics, so each lands in its own NDJSON file under
        ``trade/`` (``trade.log`` for fills, via ``get_trade_dir()``).

        Each handler normalizes both ``Event.data`` shapes (flat kwargs
        and ``data={"data": {...}}``) into one dict before logging, and
        is fail-soft: any exception is caught and logged, never raised,
        so a logging fault cannot break the trading loop.

        Idempotent: calling twice replaces the prior subscriptions
        rather than double-writing every event.
        """
        if getattr(self, "_bus_attached", False):
            # A failed unsubscribe leaves the previous handler on the
            # bus, so every event is then logged twice.
            try:
                bus.unsubscribe("trade.filled", self._on_trade_filled_bus)
            except Exception as exc:
                self._note_internal_failure(
                    "attach_to_bus/unsubscribe trade.filled", exc
                )
            try:
                bus.unsubscribe("pnl.event", self._on_pnl_event_bus)
            except Exception as exc:
                self._note_internal_failure("attach_to_bus/unsubscribe pnl.event", exc)
            try:
                bus.unsubscribe("bot.gate_decision", self._on_gate_decision_bus)
            except Exception as exc:
                self._note_internal_failure(
                    "attach_to_bus/unsubscribe bot.gate_decision", exc
                )
            try:
                bus.unsubscribe(
                    "bot.voting_panel_snapshot", self._on_voting_panel_snapshot_bus
                )
            except Exception as exc:
                self._note_internal_failure(
                    "attach_to_bus/unsubscribe " "bot.voting_panel_snapshot", exc
                )
            try:
                bus.unsubscribe("bot.log", self._on_bot_log_bus)
            except Exception as exc:
                self._note_internal_failure("attach_to_bus/unsubscribe bot.log", exc)
        try:
            bus.subscribe("trade.filled", self._on_trade_filled_bus)
            # ScrummingBot emits pnl.event at SCRUM (USD-side gain) and
            # FOLD (token-side gain) success sites.
            bus.subscribe("pnl.event", self._on_pnl_event_bus)
            # ScrummingBot emits bot.gate_decision once per bot per tick
            # after the scrum and fold chains finalize.
            bus.subscribe("bot.gate_decision", self._on_gate_decision_bus)
            # ScrummingBot emits bot.voting_panel_snapshot only at
            # trade-execution sites, per fired trade rather than per tick.
            bus.subscribe(
                "bot.voting_panel_snapshot", self._on_voting_panel_snapshot_bus
            )
            bus.subscribe("bot.log", self._on_bot_log_bus)
            self._bus_attached = True
            self.info(
                "LogManager attached to bus: trade.filled → trade.log, "
                "pnl.event → pnl/<day>.log, "
                "bot.gate_decision → gate.log (v3.23.0 scaffold), "
                "bot.voting_panel_snapshot → voting.log (v3.23.6)"
            )
        except Exception as exc:
            self._sys_logger.warning("LogManager.attach_to_bus failed: %s", exc)

    def _on_bot_log_bus(self, event_obj) -> None:
        """Route the ``bot.log`` bus topic to ``diagnostics.log``,
        unfiltered — every message, not only known markers. Fail-soft:
        an exception here is caught and logged, never raised, so this
        diagnostic writer cannot break the trading loop it observes.
        """
        try:
            data = getattr(event_obj, "data", None)
            if not isinstance(data, dict) or not data:
                return
            inner = data.get("data") if isinstance(data.get("data"), dict) else None
            merged = dict(data)
            if inner is not None:
                merged.update(inner)

            message = str(merged.get("message", "") or "")
            if not message:
                return
            bot_id = str(merged.get("bot_id", "") or "")
            symbol = ""
            if self._symbol_resolver and bot_id:
                try:
                    symbol = str(self._symbol_resolver(bot_id) or "")
                except Exception:  # resolver failure falls back to empty string
                    symbol = ""

            self._diag_writer.write(
                LogEntry(
                    category="bot_log",
                    bot_id=bot_id,
                    data={"symbol": symbol, "message": message},
                )
            )
        except Exception as exc:  # noqa: BLE001 - never break the loop
            self._sys_logger.warning("LogManager._on_bot_log_bus failed: %s", exc)

    def _on_gate_decision_bus(self, event_obj) -> None:
        """Handler for ``bot.gate_decision`` bus events, one per bot per
        tick after the scrum and fold chains finalize. Routes the
        payload into ``log_gate_decision()``.

        Payload normalization mirrors ``_on_trade_filled_bus``: the bus
        may wrap kwargs as ``Event.data = {"data": {...}}``, so any
        inner dict is merged before reading fields.

        Fail-soft: any exception is caught and logged, never raised.
        """
        try:
            data = getattr(event_obj, "data", None)
            if not isinstance(data, dict) or not data:
                return
            inner = data.get("data") if isinstance(data.get("data"), dict) else None
            merged = dict(data)
            if inner is not None:
                merged.update(inner)

            bot_id = str(merged.get("bot_id", "") or "")
            symbol = str(merged.get("symbol", "") or "")
            if not symbol and self._symbol_resolver and bot_id:
                try:
                    symbol = str(self._symbol_resolver(bot_id) or "")
                except Exception:  # resolver failure falls back to empty string
                    symbol = ""

            self.log_gate_decision(
                exchange=str(merged.get("exchange", "") or ""),
                bot_id=bot_id,
                symbol=symbol,
                scrum_armed=bool(merged.get("scrum_armed", False)),
                fold_armed=bool(merged.get("fold_armed", False)),
                scrum_blockers=merged.get("scrum_blockers"),
                fold_blockers=merged.get("fold_blockers"),
                evaluated_at_tick=merged.get("evaluated_at_tick"),
                scrum_fixture=merged.get("scrum_fixture"),
                fold_fixture=merged.get("fold_fixture"),
                indicators=merged.get("indicators"),
                state_snapshot=merged.get("state"),
                extra={
                    k: v
                    for k, v in merged.items()
                    if k
                    not in {
                        "bot_id",
                        "exchange",
                        "symbol",
                        "scrum_armed",
                        "fold_armed",
                        "scrum_blockers",
                        "fold_blockers",
                        "evaluated_at_tick",
                        "scrum_fixture",
                        "fold_fixture",
                        "indicators",
                        "state",
                        "data",
                    }
                }
                or None,
            )
        except Exception as exc:
            self._note_internal_failure("_on_gate_decision_bus", exc)

    def _on_voting_panel_snapshot_bus(self, event_obj) -> None:
        """Handler for ``bot.voting_panel_snapshot`` events, one per
        fired trade, not per tick. Routes the VotingSummary asdict
        payload into ``log_voting_panel_snapshot()``.

        Payload normalization mirrors ``_on_gate_decision_bus``.
        Fail-soft: any exception is caught and logged, never raised.
        """
        try:
            data = getattr(event_obj, "data", None)
            if not isinstance(data, dict) or not data:
                return
            inner = data.get("data") if isinstance(data.get("data"), dict) else None
            merged = dict(data)
            if inner is not None:
                merged.update(inner)

            bot_id = str(merged.get("bot_id", "") or "")
            symbol = str(merged.get("symbol", "") or "")
            if not symbol and self._symbol_resolver and bot_id:
                try:
                    symbol = str(self._symbol_resolver(bot_id) or "")
                except Exception:  # resolver failure falls back to empty string
                    symbol = ""

            panel = merged.get("panel")
            if not isinstance(panel, dict):
                panel = {}

            self.log_voting_panel_snapshot(
                exchange=str(merged.get("exchange", "") or ""),
                bot_id=bot_id,
                symbol=symbol,
                side=str(merged.get("side", "") or ""),
                trade_action=str(merged.get("trade_action", "") or ""),
                panel=panel,
                extra={
                    k: v
                    for k, v in merged.items()
                    if k
                    not in {
                        "bot_id",
                        "exchange",
                        "symbol",
                        "side",
                        "trade_action",
                        "panel",
                        "data",
                    }
                }
                or None,
            )
        except Exception as exc:
            self._note_internal_failure("_on_voting_panel_snapshot_bus", exc)

    def _on_pnl_event_bus(self, event_obj) -> None:
        """Handler for ``pnl.event`` bus events.

        Routes ScrummingBot's two-channel profit signals (SCRUM USD
        gain, FOLD token gain) into the daily PnL cascade. Fail-soft:
        any exception is caught and logged, never raised.
        """
        try:
            data = getattr(event_obj, "data", None)
            if not isinstance(data, dict) or not data:
                return
            inner = data.get("data") if isinstance(data.get("data"), dict) else None
            merged = dict(data)
            if inner is not None:
                merged.update(inner)

            bot_id = str(merged.get("bot_id", "") or "")
            kind = str(merged.get("kind", "") or "").upper()
            if kind not in ("SCRUM", "FOLD"):
                return

            # Realised PnL semantic differs by kind:
            #   SCRUM → usd_captured (USD value of the sell event)
            #   FOLD  → growth_applied_usd (the realised target growth
            #           from this fold-back; the token-side gain is
            #           also recorded as extra_asset in extras)
            if kind == "SCRUM":
                realised = float(merged.get("usd_captured", 0.0) or 0.0)
            else:
                realised = float(merged.get("growth_applied_usd", 0.0) or 0.0)

            extra: dict = {"kind": kind}
            # Forward the per-kind details so the daily cascade preserves
            # the full picture of each event.
            for k in (
                "asset",
                "symbol",
                "units",
                "units_rebought",
                "units_at_scrum_refs",
                "extra_asset",
                "pct_token_gain",
                "fill_price",
                "min_ref",
                "pct_cheaper_vs_ref",
                "usd_spent",
                "usd_captured",
                "avg_entry",
                "pct_vs_avg_entry",
                "growth_applied_usd",
            ):
                if k in merged:
                    try:
                        extra[k] = float(merged[k])
                    except (TypeError, ValueError):
                        extra[k] = merged[k]

            self.log_pnl(
                exchange=str(merged.get("exchange", "") or ""),
                bot_id=bot_id,
                realised_pnl=realised,
                unrealised_pnl=0.0,
                total_trades=int(merged.get("total_trades", 0) or 0),
                extra=extra,
            )
        except Exception as exc:
            self._sys_logger.warning("LogManager._on_pnl_event_bus raised: %s", exc)

    def _on_trade_filled_bus(self, event_obj) -> None:
        """Handler for ``trade.filled`` bus events, wired by
        ``attach_to_bus``. Normalizes the payload and calls
        ``log_trade()``."""
        try:
            data = getattr(event_obj, "data", None)
            if not isinstance(data, dict) or not data:
                return
            inner = data.get("data") if isinstance(data.get("data"), dict) else None
            merged = dict(data)
            if inner is not None:
                merged.update(inner)

            bot_id = str(merged.get("bot_id", "") or "")
            raw_side = str(merged.get("side", "") or "").upper()
            if raw_side in ("BUY", "B"):
                side = "BUY"
            elif raw_side in ("SELL", "S"):
                side = "SELL"
            else:
                side = raw_side or ""
            role = str(merged.get("type", "") or merged.get("role", "") or "").upper()
            try:
                amount = float(merged.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amount = 0.0
            try:
                price = float(merged.get("price", 0) or 0)
            except (TypeError, ValueError):
                price = 0.0
            try:
                usd = float(merged.get("usd", merged.get("size", 0)) or 0)
            except (TypeError, ValueError):
                usd = 0.0
            if usd <= 0 and amount > 0 and price > 0:
                usd = amount * price
            try:
                profit = float(merged.get("profit", 0) or 0)
            except (TypeError, ValueError):
                profit = 0.0

            extra = {
                "usd": usd,
                "profit": profit,
                "operator_initiated": bool(merged.get("operator_initiated", False)),
            }
            if "confidence" in merged:
                try:
                    extra["confidence"] = float(merged["confidence"])
                except (TypeError, ValueError):
                    pass

            # Falls back to the resolver when the payload has no symbol.
            _symbol = str(merged.get("symbol", "") or "")
            if not _symbol and self._symbol_resolver and bot_id:
                try:
                    _symbol = str(self._symbol_resolver(bot_id) or "")
                except Exception:  # resolver failure falls back to empty string
                    _symbol = ""

            self.log_trade(
                exchange=str(merged.get("exchange", "") or ""),
                bot_id=bot_id,
                action=role
                or ("SELL" if side == "SELL" else "BUY" if side == "BUY" else "TRADE"),
                symbol=_symbol,
                side=side,
                amount=amount,
                price=price,
                status=str(merged.get("status", "filled") or "filled"),
                extra=extra,
            )
        except Exception as exc:
            self._note_internal_failure("_on_trade_filled_bus", exc)

    # -- System logging -------------------------------------------------
    # Accepts `*args, **kwargs` so callers can use stdlib-style deferred
    # formatting, e.g. `log_manager.info("count=%d", n)`.
    def info(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.error(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.debug(msg, *args, **kwargs)
