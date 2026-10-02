#!/usr/bin/env python3
"""
acervator_watchdog.py — External crash watchdog for Acervator
=============================================================

Purpose
-------
Launches Acervator as a separate subprocess, monitors it from OUTSIDE
the Python process that can crash, and produces a complete post-mortem
when it dies — including thread dumps from py-spy if installed.

When Acervator silently vanishes (Qt qFatal → abort(), unhandled signal,
memory corruption, OS kill), the in-process crash hooks may not get a
chance to flush. The watchdog runs in its own Python process and writes
a detailed post-mortem to disk after the child dies.

What the watchdog does
----------------------
1. Launches `python main.py` as a subprocess.
2. Tees stdout+stderr to console AND to a watchdog-owned log.
3. Polls the heartbeat file (~/.acervator_logs/heartbeat.txt).
   If the mtime stops advancing for > STALL_SECONDS, considers
   the app hung and triggers the post-mortem pipeline.
4. When the child exits, captures:
     - Exit code (helpful: 0xC0000005 = access violation, etc.)
     - Any final stdout/stderr lines
     - Whatever crash log was being written
     - Whatever faulthandler log was being written
     - A py-spy dump of the child process's threads (if still alive)
5. Writes a post-mortem bundle to
   ~/.acervator_logs/postmortem_YYYYMMDD_HHMMSS/
   with all the above correlated.

Every error path records
-----------------------
Every ``except`` branch in this file calls ``_record``, which appends one
line naming the handler and the failure it caught to
``~/.acervator_logs/watchdog_errors.log``. The watchdog runs while the
application is failing, so recording never raises and never changes the
flow the handler already had. The per-handler counts are reported in
every post-mortem bundle.

Usage
-----
    python acervator_watchdog.py                        # run with defaults
    python acervator_watchdog.py --stall 30             # hung after 30s
    python acervator_watchdog.py --no-terminate-on-stall
    python acervator_watchdog.py --no-postmortem-on-stall
    python acervator_watchdog.py --python <interpreter>

Exit codes
----------
    0  — clean exit from child
    1  — child crashed, post-mortem written
    2  — watchdog itself failed
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TextIO

SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = Path.home() / ".acervator_logs"
HEARTBEAT_PATH = LOG_DIR / "heartbeat.txt"
ERROR_LOG_PATH = LOG_DIR / "watchdog_errors.log"

# Tunables (can be overridden via CLI flags)
DEFAULT_STALL_SECONDS = 60  # must match or exceed Acervator's longest sync call (CCXT: ~15s typical, 30s timeout)
HEARTBEAT_POLL_INTERVAL = 2.0
CAPTURE_TAIL_LINES = 200

# A handler inside a per-line or per-file loop can fire thousands of times
# in one run. Each site writes at most this many lines; the rest are
# counted only, so a repeating failure cannot regrow the log directory.
RECORD_LINES_PER_SITE = 20

_record_counts: dict[str, int] = {}
_lost_record_count = 0


# ─────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────


def _ts() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _isoformat_now() -> str:
    return _dt.datetime.now().isoformat(timespec="milliseconds")


def _log(msg: str) -> None:
    print(f"[watchdog {_isoformat_now()}] {msg}", flush=True)


def _format_record(site: str, exc: BaseException | None) -> str:
    """Build the one line that describes a caught failure.

    Returns usable text even when the exception cannot be rendered, so
    the caller never has to handle a formatting failure.
    """
    try:
        if exc is None:
            return f"[watchdog {_isoformat_now()}] {site}"
        return f"[watchdog {_isoformat_now()}] {site}: {type(exc).__name__}: {exc}"
    except Exception:
        return f"[watchdog] {site}: the failure could not be rendered"


def _append_record(text: str) -> bool:
    """Append one line to the watchdog error log.

    Returns whether the line reached disk. Never raises, so an ``except``
    branch can call it.
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(ERROR_LOG_PATH, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(text + "\n")
    except Exception:
        return False
    return True


def _echo_record(text: str) -> bool:
    """Print one line to the watchdog console.

    Returns whether the line reached the stream. Never raises, so an
    ``except`` branch can call it.
    """
    try:
        print(text, flush=True)
    except Exception:
        return False
    return True


def _record(site: str, exc: BaseException | None = None) -> None:
    """Write down a failure a handler in this file caught.

    ``site`` names the handler and what it was doing. Every ``except``
    branch in this module calls this instead of discarding the failure.

    Total by construction: the watchdog runs while the application is
    failing, so a record must never become a second crash. Both sinks
    report whether they took the line, and a line neither took is counted
    rather than raised. Per-site counts and the lost count are written
    into every post-mortem bundle.
    """
    global _lost_record_count
    seen = _record_counts.get(site, 0) + 1
    _record_counts[site] = seen
    if seen > RECORD_LINES_PER_SITE:
        return
    text = _format_record(site, exc)
    if seen == RECORD_LINES_PER_SITE:
        text += " (further repeats of this site are counted, not written)"
    on_disk = _append_record(text)
    on_console = _echo_record(text)
    if not (on_disk or on_console):
        _lost_record_count += 1


def _record_summary_lines() -> list[str]:
    """Return the per-handler record counts for a post-mortem bundle."""
    lines = ["--- Watchdog error records ---"]
    if _record_counts:
        lines.append(f"Error log: {ERROR_LOG_PATH}")
        for site in sorted(_record_counts):
            lines.append(f"{_record_counts[site]:>6}  {site}")
    else:
        lines.append("(no handler in the watchdog caught a failure this run)")
    if _lost_record_count:
        lines.append(
            f"{_lost_record_count} record(s) reached neither the error log "
            f"nor the console"
        )
    return lines


def _ensure_log_dir() -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        _record("_ensure_log_dir: could not create the log directory", exc)


# ─────────────────────────────────────────────────────────────────
# py-spy integration (optional)
# ─────────────────────────────────────────────────────────────────


def _pyspy_path() -> str | None:
    """Absolute path of the py-spy executable, or None when absent."""
    return shutil.which("py-spy")


def _pyspy_available() -> bool:
    return _pyspy_path() is not None


def _pyspy_dump(pid: int, out_path: Path) -> bool:
    """Run the resolved py-spy executable with ``dump --pid PID`` and save
    its output to out_path. Returns True on success."""
    exe = _pyspy_path()
    if exe is None:
        return False
    try:
        # --pid dumps the current stack of every thread in the target process
        with open(out_path, "w", encoding="utf-8") as f:
            proc = subprocess.run(
                [exe, "dump", "--pid", str(pid)],
                stdout=f,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )
    except Exception as exc:
        _record("_pyspy_dump: the py-spy dump command failed", exc)
        return False
    return proc.returncode == 0


# ─────────────────────────────────────────────────────────────────
# Process launch + stdout/stderr tail capture
# ─────────────────────────────────────────────────────────────────


class ChildRunner:
    """Launches the child Acervator process and captures its output
    to a log file AND a tail ring buffer the post-mortem can read.

    The console log rotates on size: when the active file passes
    ``ROTATE_BYTES`` it is renamed to ``<name>.1`` (existing .1 to .2 and
    so on, up to ``ROTATE_KEEP`` backups) and a fresh file is opened. A
    single ten-hour run once grew this log to 6.7 GB and took the host
    down with it.
    """

    # 100 MB x 3 backups = 400 MB maximum console log per run.
    ROTATE_BYTES: int = 100 * 1024 * 1024
    ROTATE_KEEP: int = 3  # active + 3 backups

    def __init__(
        self, cmd: list[str], log_path: Path, tail_size: int = CAPTURE_TAIL_LINES
    ) -> None:
        self.cmd = cmd
        self.log_path = log_path
        self.tail_size = tail_size
        self.tail: list[str] = []
        self._tail_lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self._reader_thread: threading.Thread | None = None
        self._log_fh: TextIO | None = None
        # Bytes written since the last rotation, so the threshold is
        # checked without stat()-ing the file every line.
        self._bytes_since_rotate: int = 0

    def start(self) -> None:
        self._start_internal(env=None)

    def start_with_env(self, env: dict[str, str]) -> None:
        """Like start() but passes a custom env dict to the subprocess.
        Used by run_self_watchdog to set ACERVATOR_CHILD=1 as a
        belt-and-suspenders child-mode marker in addition to --child."""
        self._start_internal(env=env)

    def _start_internal(self, env: dict[str, str] | None) -> None:
        _ensure_log_dir()
        # Open log file in line-buffered text mode
        self._log_fh = open(
            self.log_path, "w", buffering=1, encoding="utf-8", errors="replace"
        )
        self._log_fh.write(
            f"=== Acervator launched {_isoformat_now()} cmd={self.cmd} ===\n"
        )
        self._log_fh.flush()

        # Launch self.cmd — argv[0] is the interpreter or the frozen
        # executable, the rest are its arguments. stderr merges into
        # stdout so both are read on one stream. env=None inherits this
        # process's environment.
        self.proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True,
            cwd=str(SCRIPT_DIR),
            env=env,
        )

        self._reader_thread = threading.Thread(
            target=self._reader_loop, name="ChildStdoutReader", daemon=True
        )
        self._reader_thread.start()

    def _rotate_if_needed(self) -> None:
        """Rotate the console log once it exceeds ROTATE_BYTES.

        Closes the active file handle, renames it to ``.1`` (shifting any
        existing ``.1`` to ``.2`` and dropping the oldest beyond
        ``ROTATE_KEEP``), and opens a fresh file at the original path.
        Never raises: a rotation failure keeps logging to the existing
        file rather than losing the next line.
        """
        if self._bytes_since_rotate < self.ROTATE_BYTES:
            return
        try:
            # Close active file so the rename is safe on Windows.
            fh = self._log_fh
            if fh is not None:
                try:
                    fh.close()
                except Exception as exc:
                    _record(
                        "ChildRunner._rotate_if_needed: could not close the "
                        "console log before rotating",
                        exc,
                    )
            # Shift backups: .2 → .3, .1 → .2, active → .1
            for i in range(self.ROTATE_KEEP - 1, 0, -1):
                src = self.log_path.with_suffix(self.log_path.suffix + f".{i}")
                dst = self.log_path.with_suffix(self.log_path.suffix + f".{i + 1}")
                if src.exists():
                    try:
                        if dst.exists():
                            dst.unlink()
                        src.rename(dst)
                    except Exception as exc:
                        _record(
                            "ChildRunner._rotate_if_needed: could not shift a "
                            "console log backup",
                            exc,
                        )
            # active → .1
            try:
                first_backup = self.log_path.with_suffix(self.log_path.suffix + ".1")
                if first_backup.exists():
                    first_backup.unlink()
                self.log_path.rename(first_backup)
            except Exception as exc:
                _record(
                    "ChildRunner._rotate_if_needed: could not rename the active "
                    "console log to .1",
                    exc,
                )
            # Open fresh active log.
            self._log_fh = open(
                self.log_path, "w", buffering=1, encoding="utf-8", errors="replace"
            )
            self._log_fh.write(
                f"=== Acervator log continued {_isoformat_now()} "
                f"(rotated; previous chunk → {self.log_path.name}.1) ===\n"
            )
            self._log_fh.flush()
            self._bytes_since_rotate = 0
            _log(f"rotated console log at {self.ROTATE_BYTES // (1024 * 1024)} MB")
        except Exception as exc:
            _record(
                "ChildRunner._rotate_if_needed: rotation failed, continuing on "
                "the existing file",
                exc,
            )
            # If everything failed, try to recover by re-opening the original
            # in append mode so we don't lose the rest of the stream.
            try:
                self._log_fh = open(
                    self.log_path, "a", buffering=1, encoding="utf-8", errors="replace"
                )
            except Exception as reopen_exc:
                _record(
                    "ChildRunner._rotate_if_needed: could not reopen the console "
                    "log after a failed rotation",
                    reopen_exc,
                )

    def _reader_loop(self) -> None:
        stream = self.proc.stdout if self.proc is not None else None
        if stream is None:
            _record("ChildRunner._reader_loop: the child has no stdout to read")
            return
        try:
            for line in stream:
                # Tee: log file + ring buffer + our own stdout (so
                # operator sees live output).
                try:
                    fh = self._log_fh
                    if fh is None:
                        _record(
                            "ChildRunner._reader_loop: no console log is open for "
                            "the child's output"
                        )
                    else:
                        fh.write(line)
                        fh.flush()
                        # encode("utf-8") gives the on-disk byte count;
                        # cheap enough at line cadence.
                        self._bytes_since_rotate += len(
                            line.encode("utf-8", errors="replace")
                        )
                        if self._bytes_since_rotate >= self.ROTATE_BYTES:
                            self._rotate_if_needed()
                except Exception as exc:
                    _record(
                        "ChildRunner._reader_loop: could not write a child output "
                        "line to the console log",
                        exc,
                    )
                with self._tail_lock:
                    self.tail.append(line)
                    if len(self.tail) > self.tail_size:
                        self.tail = self.tail[-self.tail_size :]
                # Relay to watchdog's own stdout so user sees it live.
                try:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                except Exception as exc:
                    _record(
                        "ChildRunner._reader_loop: could not relay a child output "
                        "line to the watchdog console",
                        exc,
                    )
        except Exception as exc:
            _record(
                "ChildRunner._reader_loop: the reader thread stopped on a failure",
                exc,
            )

    def get_tail(self) -> str:
        with self._tail_lock:
            return "".join(self.tail)

    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    def wait(self, timeout: float | None = None) -> int | None:
        if self.proc is None:
            return None
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def terminate(self) -> None:
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception as exc:
                _record(
                    "ChildRunner.terminate: terminate did not stop the child, "
                    "killing it",
                    exc,
                )
                try:
                    self.proc.kill()
                except Exception as kill_exc:
                    _record(
                        "ChildRunner.terminate: could not kill the child",
                        kill_exc,
                    )

    def close(self) -> None:
        fh = self._log_fh
        if fh is None:
            return
        try:
            fh.close()
        except Exception as exc:
            _record("ChildRunner.close: could not close the console log", exc)


# ─────────────────────────────────────────────────────────────────
# Heartbeat monitor
# ─────────────────────────────────────────────────────────────────


class HeartbeatMonitor:
    """Polls the heartbeat file's mtime. Reports stall when mtime
    stops advancing for longer than stall_seconds."""

    def __init__(self, path: Path, stall_seconds: float) -> None:
        self.path = path
        self.stall_seconds = stall_seconds
        self._last_mtime: float | None = None
        self._last_observed_at: float = time.monotonic()

    def check(self) -> tuple[bool, float]:
        """Returns (is_stalled, seconds_since_last_update).
        If the file doesn't exist yet, returns (False, 0) — we give
        the app startup time to create it.
        """
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            # Heartbeat not written yet — app is still starting up.
            # Don't flag stall; just track time since we started watching.
            return (False, 0.0)
        except Exception as exc:
            _record("HeartbeatMonitor.check: could not read the heartbeat time", exc)
            return (False, 0.0)

        now = time.monotonic()
        if self._last_mtime is None or mtime != self._last_mtime:
            self._last_mtime = mtime
            self._last_observed_at = now
            return (False, 0.0)

        # File mtime unchanged since last check
        age = now - self._last_observed_at
        return (age > self.stall_seconds, age)


# ─────────────────────────────────────────────────────────────────
# Post-mortem bundle
# ─────────────────────────────────────────────────────────────────

# Bundle retention. Each crash or restart cycle writes a new
# postmortem_YYYYMMDD_HHMMSS/ directory holding the console log, the
# crash log, the faulthandler log and the py-spy dump, so an uncapped
# count once reached ~400 GB and crashed the host. The count cap and the
# age cap both apply, at startup and after every bundle write.
POSTMORTEM_KEEP_LATEST: int = 20  # most-recent N bundles preserved
POSTMORTEM_MAX_AGE_DAYS: int = 30  # anything older is dropped
POSTMORTEM_SIZE_WARN_BYTES: int = 5 * 1024 * 1024 * 1024  # 5 GB warning threshold


def _recent_file(pattern: str) -> Path | None:
    """Most recent file in LOG_DIR matching pattern (glob)."""
    try:
        files = sorted(
            LOG_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True
        )
    except Exception as exc:
        _record(f"_recent_file: could not list {pattern} in the log directory", exc)
        return None
    return files[0] if files else None


def _dir_size_bytes(path: Path) -> int:
    """Sum file sizes recursively under path. Returns 0 on any error
    (never raises — this is a diagnostic helper, not a hot path)."""
    total = 0
    try:
        for f in path.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except Exception as exc:
                _record("_dir_size_bytes: could not size a file", exc)
                continue
    except Exception as exc:
        _record("_dir_size_bytes: could not walk the directory", exc)
    return total


def prune_postmortem_bundles(
    keep_latest: int = POSTMORTEM_KEEP_LATEST,
    max_age_days: int = POSTMORTEM_MAX_AGE_DAYS,
    log_dir: Path | None = None,
) -> tuple[int, int]:
    """Prune accumulated post-mortem bundles to bound disk usage.

    Policy:
      • Keep the ``keep_latest`` most-recently-modified ``postmortem_*``
        directories regardless of age.
      • Drop any beyond that count.
      • Additionally drop any ``postmortem_*`` directory whose mtime is
        older than ``max_age_days``, even if it would have survived the
        count-based cut.
      • Never raises — pruning is best-effort. Failure to delete one
        bundle (e.g., file locked by another process) does not abort
        the rest. Each failure is recorded.

    Args:
        keep_latest: minimum number of recent bundles to preserve.
        max_age_days: bundles older than this are pruned even if within
            the keep_latest count.
        log_dir: override the directory scanned. Defaults to ``LOG_DIR``
            (``~/.acervator_logs``).

    Returns:
        (pruned_count, bytes_freed) — both are zero if nothing was
        eligible or the log dir does not exist.
    """
    base = log_dir if log_dir is not None else LOG_DIR
    if not base.exists():
        return (0, 0)

    try:
        bundles = [
            p for p in base.iterdir() if p.is_dir() and p.name.startswith("postmortem_")
        ]
    except Exception as exc:
        _record("prune_postmortem_bundles: could not enumerate the log directory", exc)
        return (0, 0)

    if not bundles:
        return (0, 0)

    # Sort newest first by mtime
    try:
        bundles.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception as exc:
        # Sort failure — fall back to filename order (timestamp suffix
        # makes alphabetical ≈ chronological)
        _record(
            "prune_postmortem_bundles: could not sort bundles by time, using "
            "the name order",
            exc,
        )
        bundles.sort(key=lambda p: p.name, reverse=True)

    cutoff_mtime = time.time() - (max_age_days * 86400)
    to_delete: list[Path] = []

    for idx, bundle in enumerate(bundles):
        # Rule 1: drop anything beyond the keep_latest count
        if idx >= keep_latest:
            to_delete.append(bundle)
            continue
        # Rule 2: drop anything older than max_age_days regardless of position
        try:
            if bundle.stat().st_mtime < cutoff_mtime:
                to_delete.append(bundle)
        except Exception as exc:
            _record("prune_postmortem_bundles: could not read a bundle timestamp", exc)
            continue

    pruned = 0
    freed = 0
    for bundle in to_delete:
        sz = _dir_size_bytes(bundle)
        try:
            shutil.rmtree(bundle)
        except Exception as exc:
            _record("prune_postmortem_bundles: could not delete a bundle", exc)
            continue
        pruned += 1
        freed += sz

    if pruned:
        _log(
            f"prune: dropped {pruned} old post-mortem bundle(s), "
            f"freed {freed / 1024 / 1024:.1f} MB"
        )
    return (pruned, freed)


def report_log_dir_footprint(log_dir: Path | None = None) -> int:
    """Print total log-dir size + warning if over threshold.

    Called once at watchdog startup so a runaway log dir is visible
    in the operator's terminal before the next run can add to it.
    """
    base = log_dir if log_dir is not None else LOG_DIR
    if not base.exists():
        return 0
    total = _dir_size_bytes(base)
    gb = total / 1024 / 1024 / 1024
    if total >= POSTMORTEM_SIZE_WARN_BYTES:
        _log(
            f"WARNING: {base} is {gb:.2f} GB — exceeds "
            f"{POSTMORTEM_SIZE_WARN_BYTES / 1024 / 1024 / 1024:.1f} GB "
            f"threshold. Run prune_postmortem_bundles() or clear "
            f"manually. (Background: 2026-05-20 incident where the dir "
            f"hit ~400 GB and crashed the host.)"
        )
    else:
        _log(f"log dir footprint: {base} = {gb:.3f} GB")
    return total


def write_postmortem(runner: ChildRunner, exit_code: int | None, cause: str) -> Path:
    """Assemble a post-mortem directory. cause is a human-readable
    description of why the child died (or was terminated by us)."""
    bundle = LOG_DIR / f"postmortem_{_ts()}"
    try:
        bundle.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        _record("write_postmortem: could not create the post-mortem directory", exc)
        return bundle

    summary_lines: list[str] = []
    summary_lines.append("=== Acervator post-mortem ===")
    summary_lines.append(f"Generated:       {_isoformat_now()}")
    summary_lines.append(f"Cause:           {cause}")
    summary_lines.append(f"Child exit code: {exit_code}")
    if exit_code is not None and exit_code < 0:
        try:
            sig = signal.Signals(-exit_code)
        except Exception as exc:
            _record("write_postmortem: could not name the exit signal", exc)
        else:
            summary_lines.append(f"Exit signal:     {sig.name} ({sig.value})")
    if exit_code is not None and exit_code > 0:
        # Decode known Windows exception codes for the common cases
        known_codes = {
            0xC0000005: "ACCESS_VIOLATION (memory / Qt cross-thread)",
            0xC0000409: "STACK_BUFFER_OVERRUN",
            0xC000013A: "CONTROL_C_EXIT",
            0xC0000374: "HEAP_CORRUPTION",
            3: "Python unhandled exception or sys.exit(3)",
        }
        hint = known_codes.get(exit_code, None)
        if hint:
            summary_lines.append(f"Exit code hint:  {hint}")

    summary_lines.append(f"Child pid:       {runner.pid}")
    summary_lines.append(f"Python:          {sys.version.split()[0]}")
    summary_lines.append(f"Platform:        {sys.platform}")
    summary_lines.append("")
    summary_lines.append(f"--- Last {CAPTURE_TAIL_LINES} lines of console output ---")
    summary_lines.append(runner.get_tail())

    # Try to find most recent crash log + faulthandler log
    for pattern, label in [
        ("crash_*.log", "crash log"),
        ("faulthandler_*.log", "faulthandler log"),
        ("thread_violation_*.log", "thread violation log"),
    ]:
        recent = _recent_file(pattern)
        summary_lines.append("")
        summary_lines.append(f"--- {label}: {recent} ---")
        if recent is not None:
            try:
                # Copy for the post-mortem bundle + include in summary
                shutil.copy2(recent, bundle / recent.name)
                with open(recent, encoding="utf-8", errors="replace") as f:
                    content = f.read()
                summary_lines.append(content)
            except Exception as exc:
                _record(f"write_postmortem: could not read the {label}", exc)
                summary_lines.append(f"(could not read: {exc})")
        else:
            summary_lines.append("(none found)")

    # Copy the watchdog's own console log
    try:
        console_log = runner.log_path
        if console_log.exists():
            shutil.copy2(console_log, bundle / console_log.name)
    except Exception as exc:
        _record("write_postmortem: could not copy the console log into the bundle", exc)

    # py-spy dump if child is still alive (hung case)
    if runner.is_alive() and runner.pid is not None:
        dump_path = bundle / "pyspy_thread_dump.txt"
        if _pyspy_dump(runner.pid, dump_path):
            summary_lines.append("")
            summary_lines.append(f"--- py-spy thread dump: {dump_path} ---")
            try:
                with open(dump_path, encoding="utf-8", errors="replace") as f:
                    summary_lines.append(f.read())
            except Exception as exc:
                _record("write_postmortem: could not read the py-spy dump back", exc)
        else:
            summary_lines.append("")
            summary_lines.append("--- py-spy thread dump: not captured ---")
            summary_lines.append(
                "Install py-spy via `pip install py-spy` for thread dumps "
                "on hung processes (STRONGLY recommended — it shows "
                "exactly which line every thread was on when the app froze)."
            )

    summary_lines.append("")
    summary_lines.extend(_record_summary_lines())

    # Write the summary
    summary_path = bundle / "SUMMARY.txt"
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(summary_lines))
    except Exception as exc:
        _record("write_postmortem: could not write the summary", exc)

    _log(f"Post-mortem bundle written to: {bundle}")

    # Prune any bundle that now exceeds the retention policy. The startup
    # prune handles bloat carried in from prior runs; this one handles
    # bloat built up inside one long-running session.
    try:
        prune_postmortem_bundles()
    except Exception as exc:
        _record("write_postmortem: the post-write prune failed", exc)

    return bundle


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(description="Acervator external crash watchdog")
    parser.add_argument(
        "--stall",
        type=float,
        default=DEFAULT_STALL_SECONDS,
        help=f"Stall threshold in seconds (default: {DEFAULT_STALL_SECONDS})",
    )
    parser.add_argument(
        "--no-postmortem-on-stall",
        action="store_true",
        help="Don't write post-mortem on stall (only on exit)",
    )
    parser.add_argument(
        "--no-terminate-on-stall",
        action="store_true",
        help="Don't terminate the child if it stalls (just post-mortem)",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter to use for the child (default: same as watchdog)",
    )
    args = parser.parse_args()

    cmd = [args.python, "main.py"]
    return _run_watchdog(
        cmd,
        args.stall,
        postmortem_on_stall=not args.no_postmortem_on_stall,
        terminate_on_stall=not args.no_terminate_on_stall,
    )


# ─────────────────────────────────────────────────────────────────
# Self-supervision mode
# ─────────────────────────────────────────────────────────────────
#
# Called from main.py's __main__ dispatch when Acervator is launched
# without a --child flag (typically because the user double-clicked
# the frozen .exe). Re-launches the current executable with --child
# and supervises it.
#
# Frozen (.exe) vs dev (python main.py) is auto-detected. In frozen
# mode the executable IS the app — sys.executable points to
# Acervator.exe, which re-entered with --child just runs main().
# In dev mode we spawn `python main.py --child`.


def run_self_watchdog(
    frozen: bool = False, stall_seconds: float = DEFAULT_STALL_SECONDS
) -> int:
    """Launch the current Acervator executable with --child and supervise it.

    frozen: True when running from a PyInstaller .exe (sys.frozen set).
            In that case sys.executable is the .exe itself.
            In dev mode sys.executable is python; we pass main.py explicitly.
    """
    if frozen:
        # Frozen build — sys.executable is Acervator.exe; reinvoke self
        cmd = [sys.executable, "--child"]
    else:
        # Dev mode — run python main.py --child
        main_py = str(SCRIPT_DIR / "main.py")
        cmd = [sys.executable, main_py, "--child"]

    return _run_watchdog(
        cmd, stall_seconds, postmortem_on_stall=True, terminate_on_stall=True
    )


def _run_watchdog(
    cmd: list[str],
    stall_seconds: float,
    postmortem_on_stall: bool,
    terminate_on_stall: bool,
) -> int:
    """Core watchdog loop, factored out so both `main()` CLI invocation
    and `run_self_watchdog()` (from main.py) share the same pipeline."""
    _ensure_log_dir()

    # Prune old post-mortem bundles on startup, then report the log dir
    # footprint, so unbounded accumulation cannot fill the disk again.
    try:
        prune_postmortem_bundles()
    except Exception as exc:
        _record("_run_watchdog: the startup prune failed", exc)
    try:
        report_log_dir_footprint()
    except Exception as exc:
        _record("_run_watchdog: could not report the log directory footprint", exc)

    # Clear any stale heartbeat from a previous run
    try:
        if HEARTBEAT_PATH.exists():
            HEARTBEAT_PATH.unlink()
    except Exception as exc:
        _record("_run_watchdog: could not remove the stale heartbeat file", exc)

    console_log = LOG_DIR / f"console_{_ts()}.log"
    _log(f"launching: {cmd}")
    _log(f"console log: {console_log}")
    _log(f"heartbeat:   {HEARTBEAT_PATH}")
    _log(f"error log:   {ERROR_LOG_PATH}")
    _log(f"stall limit: {stall_seconds}s")
    _log(
        "py-spy:      "
        + (
            "available"
            if _pyspy_available()
            else "NOT installed — run `pip install py-spy` for thread dumps"
        )
    )

    # Pass ACERVATOR_CHILD=1 to the subprocess so that even if --child
    # is stripped somewhere, the env var still identifies child mode.
    child_env = os.environ.copy()
    child_env["ACERVATOR_CHILD"] = "1"

    runner = ChildRunner(cmd, console_log)
    try:
        runner.start_with_env(child_env)
    except AttributeError as exc:
        _record(
            "_run_watchdog: start_with_env is unavailable, starting without the "
            "child environment",
            exc,
        )
        runner.start()
    except Exception as exc:
        _record("_run_watchdog: FATAL, could not launch the child", exc)
        return 2

    monitor = HeartbeatMonitor(HEARTBEAT_PATH, stall_seconds)
    startup_grace = 10.0
    start_time = time.monotonic()

    exit_code: int | None = None
    termination_cause = "clean exit"

    try:
        while True:
            rc = runner.wait(timeout=HEARTBEAT_POLL_INTERVAL)
            if rc is not None:
                exit_code = rc
                if rc == 0:
                    termination_cause = "clean exit"
                    _log(f"child exited cleanly (code {rc})")
                else:
                    termination_cause = f"child died (exit code {rc})"
                    _log(f"child died with exit code {rc}")
                break

            if time.monotonic() - start_time < startup_grace:
                continue

            stalled, age = monitor.check()
            if stalled:
                _log(f"HEARTBEAT STALLED ({age:.1f}s since last update)")
                termination_cause = f"heartbeat stalled for {age:.1f}s"
                if postmortem_on_stall:
                    bundle = write_postmortem(runner, None, termination_cause)
                    _log(f"stall post-mortem at {bundle}")
                if terminate_on_stall:
                    _log("terminating hung child")
                    runner.terminate()
                    exit_code = runner.wait(timeout=10) or -999
                    break
                else:
                    monitor._last_observed_at = time.monotonic()

    except KeyboardInterrupt:
        _log("watchdog interrupted — terminating child")
        termination_cause = "KeyboardInterrupt from watchdog"
        runner.terminate()
        exit_code = runner.wait(timeout=5)

    finally:
        if (
            exit_code is not None
            and exit_code != 0
            and termination_cause != "clean exit"
        ):
            bundle = write_postmortem(runner, exit_code, termination_cause)
            _log(f"crash post-mortem at {bundle}")
        runner.close()

    return 0 if exit_code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
