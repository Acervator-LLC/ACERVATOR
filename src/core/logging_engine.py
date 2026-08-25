from __future__ import annotations

"""
logging_engine.py — Structured trade & gate-decision logging
============================================================

Provides three log categories in v3.23.0:

  1. **Trade log** — every order placed, filled, cancelled, or failed.
     (Existing pipeline preserved verbatim; only the on-disk path moves
     to the centralized ``trade/`` bucket.)
  2. **Gate-decision log** — every gate evaluation, whether the
     decision was to fire or to block. SCAFFOLD-ONLY in v3.23.0:
     writer + bus subscriber are wired but the V1-V6 runtime
     verification (see ``sadp/DOCKET.md``) has not closed yet.
  3. **P/L log** — periodic profit/loss snapshots at configurable
     intervals (24 h → 1 week → 1 month → 1 year), where larger
     windows are built by concatenating smaller ones rather than
     generating in parallel. (Existing PnLCascade preserved verbatim.)

All logs are newline-delimited JSON (NDJSON) for easy parsing and
rotation. A ``LogManager`` orchestrates writers and handles rotation.

v3.23.0 centralization — what changed and why:

  Pre-v3.23.0 the LogManager resolved its log root via a frozen-vs-source
  conditional that put trade.log in two different places depending on
  build mode. The R-CLN'd ``log_ta_signal`` writer was created but had
  ZERO callers in the codebase (verified by grep audit at session 26
  close). The ``TA_SIGNAL`` LogCategory was the same — produced no
  consumer code-path.

  v3.23.0 deletes all three (writer, method, enum value) and routes
  trade.log + system.log + pnl/ through the bucket helpers in
  ``src/core/log_paths.py`` so the path is the same regardless of build
  mode. The new ``gate.log`` writer is added at the same time so the
  ``trade/`` bucket carries both ``trade.log`` and ``gate.log`` for the
  sim parity tool to consume in v3.23.x+ Phase C.
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
    """Write one line to ``sys.stderr``; report whether it landed.

    Last-resort channel for a fault in the logging engine's own
    machinery, used only when the system logger is itself the
    casualty. Reporting a logger fault through that same logger is
    the recursion this function exists to avoid.

    Returns a bool rather than swallowing, so the caller can record
    that even this channel is dead. ``sys.stderr`` is ``None`` under
    a windowed (pythonw / frozen) launch, which is how this platform
    runs for the operator, so the stream is probed with ``getattr``
    instead of assumed.
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
    """Universal log-entry category enum.

    v3.23.0 R-CLN: ``TA_SIGNAL`` removed — the corresponding writer +
    method had ZERO consumers in the codebase (verified by grep audit
    at session 26 close). Per operator standing rule "we do not leave
    dead or slop", the dead enum value goes too.
    """

    TRADE = "trade"
    PNL = "pnl"
    SYSTEM = "system"
    GATE = "gate"  # v3.23.0 NEW — per-tick gate decision events.


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
        # Shift existing backups.
        #
        # v3.23.5 — Path.rename() raises WinError 183 on Windows when the
        # destination exists (POSIX silently overwrites; Windows refuses).
        # Empirically 350,470 'gate.log.4 -> gate.log.5' warnings in
        # ~/.acervator_logs/console/system.log between 2026-06-10T22:29:42
        # and 2026-06-13T13:12:42 — gate.log writer completely stalled
        # because the rotate-then-append flow can't get past the .4->.5
        # shift. Path.replace() is the documented cross-platform overwrite
        # primitive (MoveFileExW with MOVEFILE_REPLACE_EXISTING on Windows,
        # silent overwrite on POSIX). Same writer class drives trade.log
        # + pnl/<day>.log; this fix is global.
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
"""Rotation threshold for ``console/system.log``.

The same 50 MB every other writer in this file has used since v3.23.5.
Measured on the operator's disk 2026-08-13: ``diagnostics.log.1``
through ``.5`` and ``gate.log.1`` through ``.5`` all sit at
52,428,9xx bytes, so the threshold is not a guess — it is the value
this platform has been rotating on, on this filesystem, for months.
"""

SYSTEM_LOG_BACKUP_COUNT = 5
"""Backups kept for ``console/system.log``.

Five, matching ``NDJSONWriter``. Total footprint is therefore bounded
at 6 x 50 MB = 300 MB, against the 9,146,281,918 bytes measured in
``~/.acervator_logs/console/system.log`` on 2026-08-13 — the file this
class exists to stop.
"""


class SizeBoundedFileHandler(RotatingFileHandler):
    """``RotatingFileHandler`` whose backup shift cannot raise WinError 183.

    WHY NOT THE STDLIB HANDLER AS SHIPPED
    -------------------------------------
    ``logging.handlers.RotatingFileHandler.doRollover`` was read at
    ``Lib/logging/handlers.py`` on the interpreter this platform runs
    (3.14.4, Windows 11). It shifts ``.4 -> .5`` with a bare
    ``os.rename``, guarded by an ``os.remove`` of the destination on
    the line before. Driven with all five backups present it does NOT
    reproduce the WinError 183 stall — the remove is what saves it. So
    the stdlib handler is defensible, and this subclass is not
    correcting a bug in it.

    What the subclass buys is the removal of a crash window and one
    fewer primitive to reason about:

      * ``remove`` then ``rename`` leaves an interval in which the
        destination does not exist. A crash inside that interval loses
        a backup outright. ``Path.replace`` is a single MoveFileExW
        with MOVEFILE_REPLACE_EXISTING — there is no interval.
      * This file already fixed exactly this rotation in v3.23.5 and
        wrote down why (``NDJSONWriter._rotate_if_needed``): 350,470
        'gate.log.4 -> gate.log.5' warnings, writer stalled for three
        days. Two rotators in one module using two different primitives
        is how that lesson gets un-learned.

    The stdlib's ``rotator`` hook CANNOT deliver this. ``rotate()`` is
    consulted only for ``base -> .1``; the ``.4 -> .5`` loop calls
    ``os.rename`` directly and never goes through it. Overriding
    ``doRollover`` is the only place the dangerous step is reachable.
    A caller-supplied ``self.rotator`` is still honoured, for every
    step, so the hook becomes MORE useful here rather than less.

    HONEST LIMIT, measured rather than assumed: if the destination is
    held open by another process, ``replace`` fails WinError 5 and
    ``remove``+``rename`` fails WinError 32. NEITHER survives that.
    This class does not claim to.

    WHY THE ROLLOVER REOPENS IN A ``finally``
    -----------------------------------------
    The stdlib closes the stream, shifts, and reopens. If a shift
    raises, the reopen never runs: ``emit`` routes the exception to
    ``handleError`` and the handler is left holding a CLOSED stream, so
    every later record raises too and the log goes permanently silent.
    That is the gate.log failure shape again, one layer up. Here the
    reopen is in a ``finally``, so a failed rotation costs the bound
    for one cycle and nothing else — the next record still lands, and
    the exception still reaches ``handleError`` so the failure is
    visible instead of swallowed.

    WHY THE CLOSE ALSO CLEARS ``self.stream``
    -----------------------------------------
    The ``finally`` above closed the shift hole and opened a WIDER one,
    because ``self._open()`` can raise too. MEASURED on this
    interpreter, both handlers driven through the identical transient —
    one ``OSError(28)`` out of ``_open`` which then clears:

        OURS    stream_is_None=False stream_closed=True
                SELF-HEALED=False handleError=3
                current file ABSENT, disk holds only ``system.log.1``
                flush() and close() both raise ValueError
        STDLIB  stream_is_None=False stream_closed=False
                SELF-HEALED=True  handleError=1
                current file holds every record after the transient

    The reopen was the LAST statement, so a raise inside it left
    ``self.stream`` still bound to the closed object it was never
    unbound from. ``shouldRollover`` reopens only ``if self.stream is
    None``, so it never reopened; it called ``.tell()`` on a closed
    file, raised, and ``handleError`` absorbed it. Every subsequent
    record took the same path. THE LOG WAS SILENT FOR THE LIFE OF THE
    PROCESS, and because the shift had already moved the current file
    to ``.1``, there was no file on disk to show the operator that
    anything had stopped.

    The fix is one line and it is the stdlib's ordering: unbind the
    stream at the moment it is closed, not at the moment a new one
    succeeds. ``self.stream = self._open()`` evaluates the call before
    it assigns, so a raise leaves the attribute at ``None`` and both
    ``shouldRollover`` and ``FileHandler.emit`` reopen on the next
    record. A transient costs one record, not the run.

    The replace-based shift above is UNTOUCHED by this. The stdlib's
    ordering is right; its ``os.remove``+``os.rename`` primitive is
    not, and only the ordering is adopted.
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

        Deliberate difference from the stdlib: the stream is reopened
        unconditionally rather than only when ``delay`` is false.
        ``shouldRollover`` has already opened it before this method can
        be reached, so a delayed handler is open by now anyway, and
        leaving ``self.stream`` closed is the silent-death case
        described in the class docstring.

        ``self.stream`` is cleared AT THE CLOSE, before anything that
        can raise. Between here and the reopen the only honest value
        for the attribute is ``None``: there is no usable stream. A
        closed file object left in the slot is a lie that
        ``shouldRollover``, ``FileHandler.emit``, ``flush`` and
        ``close`` all believe, and believing it is what made a
        one-record disk hiccup permanent. See the class docstring for
        the measurement.
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
    Maintains P/L snapshots at multiple periodicities.  The 24-hour log
    is the atomic unit; weekly/monthly/yearly logs are assembled from it
    rather than generated independently.

    Directory layout::

        logs/pnl/
          daily/    ← one NDJSON per day
          weekly/   ← concatenated from daily/
          monthly/  ← concatenated from weekly/
          yearly/   ← concatenated from monthly/
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
    Central logging orchestrator.  Call ``log_trade()``, ``log_ta_signal()``,
    or ``log_pnl()`` from any thread; the manager routes to the correct
    writer and handles rotation.

    Also configures Python's ``logging`` module for system-level messages.
    """

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        # Internal-failure counters. FIRST statement in __init__ on
        # purpose: _note_internal_failure runs from except blocks that
        # must not raise, so its storage has to exist before anything
        # below here can fail.
        self._internal_failures: dict[str, int] = {}

        # v3.23.0 — single-canonical-root resolution via log_paths bucket
        # helpers. The legacy frozen-vs-source conditional that put
        # trade.log in two different places depending on build mode is
        # gone (R-CLN). All log buckets sit under ~/.acervator_logs/
        # so the path is the same regardless of how the platform is
        # launched.
        #
        # The ``log_dir`` arg is preserved for test injection only
        # (tests can pass a tmp_path); production code paths always use
        # the bucket helpers.
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
            # Back-compat: existing code reads ``self._dir`` for
            # diagnostics. Point it at the trade bucket since that is
            # where the operator-visible trade.log + gate.log + pnl/
            # all land.
            self._dir = self._trade_dir

        self._trade_writer = NDJSONWriter(self._trade_dir / "trade.log")
        # v3.23.0 NEW: gate.log NDJSON writer. Scaffold-only — runtime
        # verification (V1-V6 in DOCKET) pending. Operator must launch a
        # v3.23.0 build and observe gate.log populating before this
        # writer is considered "verified working" per the verify-before-
        # ship discipline ("logs are restructured and VERIFIED wired
        # and VERIFIED working THEN we point both sim and live to them
        # for relevant queries").
        self._gate_writer = NDJSONWriter(self._trade_dir / "gate.log")
        # v3.24.35 (C39g) — bot.log diagnostics to DISK.
        #
        # ScrummingBot emits its entire diagnostic vocabulary over the
        # `bot.log` bus topic: [COMPOUND SKIPPED], TARGET GROWN,
        # TARGET-GROW HELD, FOLD_DIAG_SURPLUS_CHECK, [WIRE FIRE]. Those
        # messages were written expressly to be searched — the source
        # says so, e.g. "Grep for '[COMPOUND SKIPPED]' in the log to
        # spot fold events that had no compounding effect."
        #
        # That was impossible. `bot.log` had exactly two subscribers,
        # both GUI windows, and both terminate at
        # `StatusLog.log()` (main_window.py:256-268) which contains no
        # open(), no write(), no logger call. The messages reached a
        # scrollback panel and died with the session.
        #
        # Consequence, measured 2026-08-06: zero occurrences of every
        # one of those markers across the whole log tree including the
        # 7.4 GB console/system.log — not because compounding never ran,
        # but because the channel never touched a file. The operator has
        # been unable to diagnose compounding for the entire development
        # history, and the instrument built to explain it was writing to
        # a widget.
        #
        # Bounded like its siblings: 50 MB x 5 backups.
        self._diag_writer = NDJSONWriter(self._trade_dir / "diagnostics.log")
        # v3.23.6 NEW — voting.log NDJSON writer for per-trade voting-panel
        # snapshots. Per operator pin 2026-06-13: snapshot panel outputs
        # ONLY at trade execution (not per-tick), so this log fires once
        # per fired trade, not once per tick. Lives in trade/ bucket
        # alongside trade.log + gate.log.
        self._voting_writer = NDJSONWriter(self._trade_dir / "voting.log")
        self._pnl_cascade = PnLCascade(self._pnl_root)

        # v3.16.60 — Symbol resolver callback. Operator-reported 2026-05-15:
        # trade.log entries all had empty "symbol" field because the bot
        # emits trade.filled with kwargs or data={} but never includes
        # symbol explicitly. Rather than touch 8 emit sites, main.py
        # wires a resolver that maps bot_id → bot.config.symbol via the
        # BotManager. Handler uses it as fallback when symbol is empty.
        self._symbol_resolver: Optional[Callable[[str], str]] = None

        # System logger (Python standard logging)
        self._sys_logger = logging.getLogger("acervator")
        self._sys_logger.setLevel(logging.DEBUG)
        self._sys_logger.propagate = False  # Don't duplicate to root logger
        if not self._sys_logger.handlers:
            # v3.23.0 — system.log moves into console/ bucket per
            # operator directive (console bucket = "code faults"
            # category). Pre-v3.23.0 this lived alongside trade.log,
            # forcing operators to scan two log dirs for two distinct
            # concerns. Now: code-fault logs all under console/.
            # v3.24.53 — encoding + errors are NOT optional here.
            #
            # `logging.FileHandler` with no encoding opens the file with
            # the locale codec: cp1252 on Windows. This codebase logs
            # arrow, em-dash, multiplication and comparison glyphs
            # freely, and every record containing one raised
            # UnicodeEncodeError inside the handler. Python's logging
            # swallows that into `--- Logging error ---` plus a
            # traceback and DROPS the record.
            #
            # Measured on the operator's 2026-08-07 08:18 boot: 825
            # such blocks, 15,616 lines of file, and exactly THREE
            # surviving log records. The system log had been almost
            # entirely noise — found while trying to read it to
            # diagnose something else, which is how a broken instrument
            # usually surfaces.
            #
            # `errors="replace"` as well as utf-8: a genuinely
            # undecodable byte must degrade to a marker, never cost the
            # whole record. This is the same class as the archetype
            # subprocess defect fixed in 3.24.51 — that one was reading,
            # this one is writing.
            #
            # v3.24.9x — BOUNDED. This handler had no maxBytes and no
            # backupCount, so system.log was the one writer in this
            # module that could grow without limit while trade.log,
            # gate.log, diagnostics.log and voting.log were all capped
            # at 50 MB x 5 by NDJSONWriter. Measured on the operator's
            # disk 2026-08-13: console/system.log 9,146,281,918 bytes
            # and still climbing, against 6 x ~52.4 MB for each of its
            # bounded siblings.
            #
            # The legacy file rolls to system.log.1 on the first record
            # of the next launch. That is one same-volume rename, which
            # NTFS resolves as metadata and does not copy 9 GB.
            #
            # MEASURED 2026-08-13 on a scratch file of exactly
            # 9,146,281,918 bytes, on C:, driving this class through a
            # real LogManager: __init__ 2.0 ms, first record 0.7 ms,
            # 2.7 ms added to boot in total. The startup does not hang.
            # A full ladder roll with all five backups occupied is
            # 8.9 ms. The one slow step arrives later: six rolls in,
            # the 9 GB file reaches .5 and is overwritten, and that
            # single replace costs 938 ms — a one-off, hundreds of MB
            # of logging after boot, and it is the cost of deleting
            # 9 GB by any means.
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

        Total by construction. Every caller is an ``except`` block whose
        whole job is to keep a logging fault out of the trading loop, so
        this method must not raise for any input. Nothing here formats
        the exception object eagerly: a hostile ``__repr__`` or
        ``__str__`` would otherwise escape from the recovery path. Only
        ``type(exc).__name__`` is read directly, which is a ``str`` on
        every exception class.

        Three channels, least failure-prone first:

        1. ``self._internal_failures`` — a counter keyed by call site.
           A dict lookup and an integer add against a ``str`` key; no
           operation here can raise, so the fault is recorded even when
           every output channel is dead. Read it with
           ``internal_failure_counts()``.
        2. ``self._sys_logger`` — the operator-facing report, for the
           common case where the failing subsystem is not the logger.
        3. ``sys.stderr`` — reached only when channel 2 raised, i.e.
           when the system logger is the casualty. If that write also
           fails it is counted under ``_stderr`` rather than lost.
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
        """v3.16.60 — register a bot_id → symbol lookup function. Used
        by _on_trade_filled_bus and _on_pnl_event_bus as fallback when
        the emitter didn't include `symbol` in the payload (which is
        every existing emit site as of v3.16.59).
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

    # v3.23.0 R-CLN: ``log_ta_signal`` method + ``_ta_writer`` attribute
    # + ``LogCategory.TA_SIGNAL`` enum value all removed. Zero callers
    # were ever wired (verified by grep audit at session 26 close).
    # Operator standing rule 2026-06-09: "we do not leave dead or slop."
    # The codebase tells the truth about what runs.

    # -- Gate-decision logging (v3.23.0 NEW) ----------------------------
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
        """Log one gate-decision event per bot per tick.

        v3.23.0 SCAFFOLD-ONLY. Field schema chosen to satisfy V1-V6
        runtime verification criteria in ``sadp/DOCKET.md`` once the
        operator launches a v3.23.0 build and observes gate.log
        populating end-to-end.

        Designed as the **single sanctioned sim↔live connection point**
        per operator directive 2026-06-09 ("logs are restructured and
        VERIFIED wired and VERIFIED working THEN we point both sim and
        live to them for relevant queries"). Sim does NOT consume this
        log until Phase C of the verify-then-ship pass closes.

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

    # -- Voting-panel-snapshot logging (v3.23.6 NEW) --------------------
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
        """Log one voting-panel snapshot at trade-execution time.

        v3.23.6: Operator pin 2026-06-13: cadence is "snapshot panel
        outputs ONLY at trade execution (not per-tick)". ScrummingBot
        emits ``bot.voting_panel_snapshot`` immediately AFTER each
        ``trade.filled`` emit at every trade-execution site so the panel
        state that drove the decision is captured at the exact moment
        the decision became action.

        Args:
            exchange:     Source exchange tag.
            bot_id:       Bot identifier.
            symbol:       Asset symbol.
            side:         BUY / SELL.
            trade_action: SCRUM / FOLD / ENTRY / HEDGE / DIST / etc.
            panel:        VotingSummary asdict snapshot. May be {} for
                          early ticks when ``self._last_summary is None``
                          per the fail-soft pin in the spec.
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
        # Reuse the GATE enum value or introduce a new one? Operator's
        # architecture pin: "separate streams (trade.log + gate.log +
        # voting.log)" — separate writer, separate stream. Category tag
        # uses literal "voting" so downstream consumers can filter.
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
        """v3.15.78 — Wire ``trade.filled`` events to ``log_trade()`` so
        every executed trade lands in ``logs/real_market/trade.log`` as
        NDJSON.

        Operator-reported 2026-04-27: "The platform is not producing
        any trade logs. I am seeing the logs sub directories remain
        empty across iterations."

        Root cause: ``LogManager.log_trade`` was defined and the
        ``NDJSONWriter`` for ``trade.log`` was created in ``__init__``,
        but no caller ever invoked ``log_trade`` — the engine was
        wired to nothing. Trades emit on the in-process event bus
        as ``trade.filled`` events; the GUI tabs and the in-memory
        ledger consumed them, but the on-disk writer did not.

        This method subscribes a handler that:
          • Normalizes both ``trade.filled`` shapes (kwargs and
            ``data={...}``) into a canonical dict.
          • Calls ``log_trade()`` with extracted fields.
          • Fail-soft: any exception in the handler is logged at
            warning level and swallowed so a logging glitch never
            breaks the trading loop.

        Idempotent: calling twice replaces the prior subscription
        rather than double-writing each trade.
        """
        if getattr(self, "_bus_attached", False):
            # A failed unsubscribe is not cosmetic: the previous handler
            # stays on the bus and every trade is then written twice.
            # ``EventBus.unsubscribe`` documents "Never raises", so a
            # raise here means ``bus`` is a foreign object without that
            # contract — which is exactly the case an operator needs to
            # see. The system logger is a separate mechanism from the
            # bus, so reporting a bus fault through it cannot recurse.
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
            # v3.23.6 — voting.log unsubscribe symmetric with gate.log
            try:
                bus.unsubscribe(
                    "bot.voting_panel_snapshot", self._on_voting_panel_snapshot_bus
                )
            except Exception as exc:
                self._note_internal_failure(
                    "attach_to_bus/unsubscribe " "bot.voting_panel_snapshot", exc
                )
            # v3.24.35 (C39g) — symmetric with the bot.log subscribe
            # below. An asymmetric teardown leaks a subscription on the
            # global bus, which is the exact shape of the Nuclear
            # BotManager leak found in the Bot Swarm audit.
            try:
                bus.unsubscribe("bot.log", self._on_bot_log_bus)
            except Exception as exc:
                self._note_internal_failure("attach_to_bus/unsubscribe bot.log", exc)
        try:
            bus.subscribe("trade.filled", self._on_trade_filled_bus)
            # v3.16.59 — Wire pnl.event → log_pnl. Operator directive
            # 2026-05-14: "the pnl folder and all of its sub directories
            # have continue to remain unpopulated. Suggests that proper
            # PnL logging is not being pulled from the exchange when a
            # Scrum or Fold is occurring." Root cause: PnLCascade was
            # initialized but log_pnl() was never called from anywhere.
            # ScrummingBot now emits pnl.event at SCRUM (USD-side gain)
            # and FOLD (token-side gain) success sites; this handler
            # routes those events into the daily PnL cascade.
            bus.subscribe("pnl.event", self._on_pnl_event_bus)
            # v3.23.0 NEW — Wire bot.gate_decision → log_gate_decision.
            # ScrummingBot emits one event per bot per tick after
            # gate-fixture finalization (scrum_armed/fold_armed +
            # blockers + indicators + state snapshot). This handler
            # routes those events into ~/.acervator_logs/trade/gate.log
            # as NDJSON. SCAFFOLD-ONLY: V1-V6 verify-loop in DOCKET
            # closes the verified-wired-and-working gate before sim
            # consumes this stream.
            bus.subscribe("bot.gate_decision", self._on_gate_decision_bus)
            # v3.23.6 NEW — bot.voting_panel_snapshot → voting.log.
            # ScrummingBot emits this at trade-execution sites only
            # (operator pin: cadence is per-fired-trade, not per-tick).
            # Routes the VotingSummary asdict snapshot that drove the
            # decision into ~/.acervator_logs/trade/voting.log as NDJSON.
            bus.subscribe(
                "bot.voting_panel_snapshot", self._on_voting_panel_snapshot_bus
            )
            # v3.24.35 (C39g) — bot.log → diagnostics.log. Before this,
            # `bot.log` had only GUI subscribers and every diagnostic
            # ScrummingBot emits died in a scrollback panel.
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
        """v3.24.35 (C39g) — route ``bot.log`` to disk.

        Deliberately UNFILTERED. The temptation is to capture only the
        known markers ([COMPOUND SKIPPED], TARGET GROWN, ...), but that
        pre-judges which line will turn out to matter, and the whole
        reason this handler exists is that nobody could see any of them.
        A filter would reproduce the original defect for every message
        not on the list.

        Volume is bounded by rotation (50 MB x 5), not by selection. If
        the rotation window turns out to be too short to hold a session,
        that is a measurable follow-up — and a visible one, since the
        backups will show it.

        Fail-soft, matching its siblings: a diagnostic writer must never
        break the trading loop it is observing.
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
                except Exception:  # R28-OK: resolver probe
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
        """v3.23.0 NEW — handler for ``bot.gate_decision`` bus events.

        ScrummingBot emits one event per bot per tick after the gate
        chains (scrum + fold) finalize. This handler routes the payload
        into the centralized ``gate.log`` writer.

        Payload normalization mirrors ``_on_trade_filled_bus`` /
        ``_on_pnl_event_bus``: the bus may wrap kwargs as
        ``Event.data = {"data": {...}}`` depending on emit form, so we
        merge any inner dict before reading fields.

        Fail-soft: any exception is logged at warning level and
        swallowed so a gate-logging hiccup never breaks the trading
        loop. Per the verify-before-ship discipline, runtime failures
        here are diagnostic targets for the V1-V6 verification gate.
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
                except Exception:  # R28-OK: resolver probe; empty fallback
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
        """v3.23.6 NEW — handler for ``bot.voting_panel_snapshot`` events.

        ScrummingBot emits one event per fired trade (operator pin
        2026-06-13: "snapshot panel outputs ONLY at trade execution
        (not per-tick)"). This handler routes the VotingSummary asdict
        payload into the centralized ``voting.log`` writer.

        Payload normalization mirrors ``_on_gate_decision_bus``: the
        bus may wrap kwargs under ``Event.data = {"data": {...}}`` so
        we merge any inner dict before reading fields.

        Fail-soft: any exception is logged at warning level and
        swallowed so a logging hiccup never breaks the trading loop.
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
                except Exception:  # R28-OK: resolver probe; empty fallback
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
        """v3.16.59 — handler for ``pnl.event`` bus events. Routes
        ScrummingBot's two-channel profit signals (SCRUM USD gain,
        FOLD token gain) into the daily PnL cascade.

        Fail-soft: any exception swallowed so a PnL telemetry hiccup
        never breaks the trading loop.
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
        """Internal handler for ``trade.filled`` bus events. Wired by
        ``attach_to_bus``. Mirrors the normalization in
        ``trade_history_tab._normalize_trade_event`` so both code paths
        agree on field semantics."""
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
            # Best-effort confidence carry-through if present.
            if "confidence" in merged:
                try:
                    extra["confidence"] = float(merged["confidence"])
                except (TypeError, ValueError):
                    pass

            # v3.16.60 — Symbol fallback via resolver. Existing emit
            # sites don't include symbol in the payload; resolver looks
            # it up by bot_id via the BotManager.
            _symbol = str(merged.get("symbol", "") or "")
            if not _symbol and self._symbol_resolver and bot_id:
                try:
                    _symbol = str(self._symbol_resolver(bot_id) or "")
                except Exception:  # R28-OK: resolver probe; empty fallback
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
    # v3.23.70 — accept `*args, **kwargs` so callers can use printf-style
    # deferred formatting (`log_manager.info("count=%d", n)`) exactly
    # like Python's stdlib `logging.Logger.info`. The prior single-arg
    # signature crashed the shutdown path added in v3.23.59
    # (main.py:1103 / 1111 pass a format string + one arg).
    def info(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.error(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._sys_logger.debug(msg, *args, **kwargs)
