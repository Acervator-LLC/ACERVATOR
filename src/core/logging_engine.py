"""Structured trade, gate-decision and P/L logging in NDJSON.

``LogManager`` routes each ``LogEntry`` to an ``NDJSONWriter``: ``trade.log``,
``gate.log``, ``voting.log`` and ``diagnostics.log`` under ``get_trade_dir()``,
with the ``acervator`` logger going to ``system.log`` under
``get_console_dir()``. ``PnLCascade`` writes one file per day under
``get_pnl_dir()``, and ``build_weekly``, ``build_monthly`` and ``build_yearly``
concatenate those days.
"""

from __future__ import annotations

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

    ``_note_internal_failure`` calls it when ``_sys_logger`` also raised, and a
    windowed launch leaves ``sys.stderr`` set to None.
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


class LogCategory(str, Enum):
    """The values the ``LogEntry.category`` field takes."""

    TRADE = "trade"
    PNL = "pnl"
    SYSTEM = "system"
    GATE = "gate"


@dataclass
class LogEntry:
    """One NDJSON record; ``to_json`` serialises it for an ``NDJSONWriter``."""

    timestamp: str = ""
    category: str = ""
    exchange: str = ""
    bot_id: str = ""
    data: dict = field(default_factory=dict)
    highlight: bool = False

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))


class NDJSONWriter:
    """Append-only NDJSON writer with size-based rotation.

    ``write`` rotates once the file reaches ``max_bytes`` and keeps
    ``backup_count`` numbered backups, so ``trade.log`` plus ``trade.log.1``
    through ``trade.log.5`` is the whole set.
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
        """Append one ``LogEntry`` under ``_lock``, rotating first when due."""
        line = entry.to_json() + "\n"
        with self._lock:
            self._rotate_if_needed()
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line)

    def read_all(self) -> list[dict]:
        """Return every parsed record in the current file, skipping bad lines."""
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
        # Path.rename raises WinError 183 on Windows when the destination exists.
        for i in range(self._backup_count - 1, 0, -1):
            src = self._path.parent / f"{self._path.name}.{i}"
            dst = self._path.parent / f"{self._path.name}.{i + 1}"
            if src.exists():
                src.replace(dst)
        backup = self._path.parent / f"{self._path.name}.1"
        self._path.replace(backup)


SYSTEM_LOG_MAX_BYTES = 50 * 1024 * 1024
"""Rotation threshold for ``system.log``, matching the ``NDJSONWriter`` default."""

SYSTEM_LOG_BACKUP_COUNT = 5
"""Backups kept for ``system.log``; six files bound it at 300 MiB."""


class SizeBoundedFileHandler(RotatingFileHandler):
    """``RotatingFileHandler`` whose backup shift cannot raise WinError 183.

    ``_shift`` moves each backup with ``Path.replace``, and ``doRollover``
    clears ``self.stream`` before the shift, which ``FileHandler.emit`` reopens
    on the next record.
    """

    def _shift(self, source: str, dest: str) -> None:
        """Move ``source`` onto ``dest``, overwriting, when ``source`` exists."""
        if callable(self.rotator):
            self.rotator(source, dest)
            return
        src = Path(source)
        if src.exists():
            src.replace(Path(dest))

    def doRollover(self) -> None:
        """Shift the backups and start a new current file.

        ``self.stream`` is cleared before the shift and reopened in a
        ``finally``, leaving the handler usable when ``_shift`` raises.
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


class PnLCascade:
    """P/L snapshots in one directory per key of ``PERIODS``.

    ``record_daily`` writes ``daily/<date>.ndjson``, and ``build_weekly``,
    ``build_monthly`` and ``build_yearly`` each read ``daily/`` through
    ``_concat_days``, never one another's output.
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
        """Append ``entry`` to ``daily/<today>.ndjson``."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self._base / "daily" / f"{today}.ndjson"
        with open(path, "a", encoding="utf-8") as f:
            f.write(entry.to_json() + "\n")

    def build_weekly(self, week_start: str) -> list[dict]:
        """Concatenate 7 daily files from ``week_start``, formatted YYYY-MM-DD."""
        return self._concat_days(week_start, 7, "weekly")

    def build_monthly(self, month_start: str) -> list[dict]:
        """Concatenate 30 daily files from ``month_start``, formatted YYYY-MM-DD."""
        return self._concat_days(month_start, 30, "monthly")

    def build_yearly(self, year_start: str) -> list[dict]:
        """Concatenate 365 daily files from ``year_start``, formatted YYYY-MM-DD."""
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
        out_path = self._base / output_dir / f"{start}_{count}d.ndjson"
        with open(out_path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
        return entries


class LogManager:
    """Routes every log call in this module to its ``NDJSONWriter``.

    ``log_trade``, ``log_gate_decision``, ``log_voting_panel_snapshot`` and
    ``log_pnl`` are callable from any thread, and ``__init__`` also attaches
    ``SizeBoundedFileHandler`` to the ``acervator`` logger.
    """

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        # _note_internal_failure writes here from inside its own except blocks.
        self._internal_failures: dict[str, int] = {}

        # log_dir is test injection; production resolves through log_paths.
        if log_dir is not None:
            self._dir = log_dir
            self._dir.mkdir(parents=True, exist_ok=True)
            self._trade_dir = self._dir
            self._console_dir = self._dir
            self._pnl_root = self._dir / "pnl"
            self._pnl_root.mkdir(parents=True, exist_ok=True)
        else:
            # The three helpers resolve under ~/.acervator_logs.
            self._trade_dir = get_trade_dir()
            self._console_dir = get_console_dir()
            self._pnl_root = get_pnl_dir()
            self._dir = self._trade_dir

        self._trade_writer = NDJSONWriter(self._trade_dir / "trade.log")
        self._gate_writer = NDJSONWriter(self._trade_dir / "gate.log")
        # _on_bot_log_bus routes the bot.log topic here unfiltered.
        self._diag_writer = NDJSONWriter(self._trade_dir / "diagnostics.log")
        # One entry per fired trade, not per tick.
        self._voting_writer = NDJSONWriter(self._trade_dir / "voting.log")
        self._pnl_cascade = PnLCascade(self._pnl_root)

        # Maps bot_id to symbol for the bus handlers below.
        self._symbol_resolver: Optional[Callable[[str], str]] = None

        self._sys_logger = logging.getLogger("acervator")
        self._sys_logger.setLevel(logging.DEBUG)
        self._sys_logger.propagate = False
        if not self._sys_logger.handlers:
            # cp1252 raises on the arrow and em-dash glyphs, dropping the record.
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

    def _note_internal_failure(self, where: str, exc: BaseException) -> None:
        """Record a fault inside this module's own plumbing, raising nothing.

        It counts ``where`` in ``_internal_failures``, then tries
        ``_sys_logger``, then ``_emergency_stderr``.
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
        """Return a copy of ``_internal_failures``.

        The keys ``_sys_logger`` and ``_stderr`` count report-channel failures;
        every other key is a ``_note_internal_failure`` call site.
        """
        return dict(self._internal_failures)

    def set_symbol_resolver(self, resolver: "Callable[[str], str]") -> None:
        """Store ``resolver`` on ``_symbol_resolver`` as a bot_id to symbol lookup.

        ``_on_trade_filled_bus``, ``_on_gate_decision_bus``,
        ``_on_voting_panel_snapshot_bus`` and ``_on_bot_log_bus`` call it when
        the event carries no symbol; ``_on_pnl_event_bus`` does not.
        """
        self._symbol_resolver = resolver

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
        """Write one ``LogCategory.TRADE`` entry through ``_trade_writer``."""
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
        """Write one ``LogCategory.GATE`` entry to ``gate.log``.

        ``ScrummingBot._emit_gate_decision_at_fire`` reaches this once per fired
        trade through ``_on_gate_decision_bus``.

        Args:
            exchange:           Source exchange tag.
            bot_id:             Bot identifier.
            symbol:             Asset symbol.
            scrum_armed:        True when the scrum chain decided to fire.
            fold_armed:         True when the fold chain decided to fire.
            scrum_blockers:     Names that blocked the scrum chain.
            fold_blockers:      Names that blocked the fold chain.
            evaluated_at_tick:  Loop-tick counter or wall-clock proxy.
            scrum_fixture:      Per-stage pass or block record for scrum.
            fold_fixture:       Per-stage pass or block record for fold.
            indicators:         Indicator values behind the decision.
            state_snapshot:     Holdings, target and fold_tranches.
            extra:              Free-form passthrough merged into data.
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
        """Write one entry with category "voting" to ``voting.log``.

        ``ScrummingBot._emit_voting_panel_snapshot_at_fire`` reaches this once
        per fired trade, not per tick.

        Args:
            exchange:     Source exchange tag.
            bot_id:       Bot identifier.
            symbol:       Asset symbol.
            side:         BUY or SELL.
            trade_action: SCRUM, FOLD, ENTRY, HEDGE, DIST and the rest.
            panel:        VotingSummary asdict snapshot, or {} when none.
            extra:        Free-form passthrough merged into data.
        """
        data: dict = {
            "symbol": symbol,
            "side": str(side or "").upper(),
            "trade_action": str(trade_action or "") or "",
            "panel": panel if isinstance(panel, dict) else {},
        }
        if extra:
            data.update(extra)
        # The category is "voting", never LogCategory.GATE.
        entry = LogEntry(
            category="voting",
            exchange=exchange,
            bot_id=bot_id,
            data=data,
        )
        self._voting_writer.write(entry)

    def log_pnl(
        self,
        exchange: str,
        bot_id: str,
        realised_pnl: float,
        unrealised_pnl: float,
        total_trades: int,
        extra: Optional[dict] = None,
    ) -> None:
        """Write one ``LogCategory.PNL`` entry via ``PnLCascade.record_daily``."""
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

    def attach_to_bus(self, bus) -> None:
        """Subscribe ``trade.filled``, ``pnl.event``, ``bot.gate_decision``,
        ``bot.voting_panel_snapshot`` and ``bot.log`` to their handlers.

        A second call unsubscribes the previous handlers first, and each
        handler catches its own exceptions.
        """
        if getattr(self, "_bus_attached", False):
            # A failed unsubscribe leaves the old handler on the bus, logging twice.
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
            # ScrummingBot emits pnl.event at the SCRUM and FOLD success sites.
            bus.subscribe("pnl.event", self._on_pnl_event_bus)
            # ScrummingBot emits bot.gate_decision at fire time, once per trade.
            bus.subscribe("bot.gate_decision", self._on_gate_decision_bus)
            # ScrummingBot emits bot.voting_panel_snapshot at fire time too.
            bus.subscribe(
                "bot.voting_panel_snapshot", self._on_voting_panel_snapshot_bus
            )
            bus.subscribe("bot.log", self._on_bot_log_bus)
            self._bus_attached = True
            self.info(
                "LogManager attached to bus: trade.filled → trade.log, "
                "pnl.event → pnl/daily/<day>.ndjson, "
                "bot.gate_decision → gate.log, "
                "bot.voting_panel_snapshot → voting.log, "
                "bot.log → diagnostics.log"
            )
        except Exception as exc:
            self._sys_logger.warning("LogManager.attach_to_bus failed: %s", exc)

    def _on_bot_log_bus(self, event_obj) -> None:
        """Route every ``bot.log`` event to ``_diag_writer`` unfiltered.

        An entry needs a ``message``; ``_symbol_resolver`` supplies the symbol.
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
                except Exception:
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
        """Route one ``bot.gate_decision`` event into ``log_gate_decision``.

        An inner ``data`` dict is merged before the fields are read, and any
        exception reaches ``_note_internal_failure``.
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
                except Exception:
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
        """Route one ``bot.voting_panel_snapshot`` event into
        ``log_voting_panel_snapshot``.

        A ``panel`` that is not a dict becomes {}, and any exception reaches
        ``_note_internal_failure``.
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
                except Exception:
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
        """Route one ``pnl.event`` with a SCRUM or FOLD ``kind`` into ``log_pnl``.

        SCRUM reads ``usd_captured`` and FOLD reads ``growth_applied_usd``; any
        other kind returns without writing.
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

            if kind == "SCRUM":
                realised = float(merged.get("usd_captured", 0.0) or 0.0)
            else:
                realised = float(merged.get("growth_applied_usd", 0.0) or 0.0)

            extra: dict = {"kind": kind}
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
        """Route one ``trade.filled`` event into ``log_trade``.

        ``side`` is normalised to BUY or SELL, ``usd`` falls back to ``amount``
        times ``price``, and the row carries whichever of ``fee_usd`` or
        ``fee_refusal`` the fill supplied.
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
            if "fee_usd" in merged:
                try:
                    extra["fee_usd"] = float(merged["fee_usd"])
                except (TypeError, ValueError):
                    pass
            elif "fee_refusal" in merged:
                extra["fee_refusal"] = str(merged["fee_refusal"])
            if "confidence" in merged:
                try:
                    extra["confidence"] = float(merged["confidence"])
                except (TypeError, ValueError):
                    pass

            _symbol = str(merged.get("symbol", "") or "")
            if not _symbol and self._symbol_resolver and bot_id:
                try:
                    _symbol = str(self._symbol_resolver(bot_id) or "")
                except Exception:
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

    # args reach logging's deferred formatting: info("count=%d", n).
    def info(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.error(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.debug(msg, *args, **kwargs)
