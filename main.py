"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
main.py — Acervator entry point
==========================================
# ┌─────────────────────────────────────────────────────────────┐
# │ AI DEVELOPER NOTE                                           │
# │                                                             │
# │ This is the application entry point. Run: python main.py    │
# │                                                             │
# │ IMPORTANT: this file DECLARES no version. THE VERSION IS    │
# │ DERIVED, NEVER WRITTEN — see src/_version.py. Do not add a  │
# │ literal here or anywhere else.                              │
# │                                                             │
# │ The app has TWO modes:                                      │
# │   - Crypto mode: main_window.py (CCXT exchanges)           │
# │   - Stock mode: stock_main_window.py (Alpaca broker)        │
# │                                                             │
# │ BUILD: Use BUILD.py with PyInstaller, NOT this file.        │
# │ TEST:  python -m dev_harness.harness.check_release_readiness│
# │ DOCS:  README.md and CONTRIBUTING.md are the front door.    │
# │        Issue #69 cut three pointers to absent files.        │
# └─────────────────────────────────────────────────────────────┘

Orchestrates application startup:
  1. Load or create settings.
  2. If first run, launch the Init Wizard.
  3. Initialise core services (logging, encryption, event bus).
  4. Launch the main window with the selected exchange tab.
  5. Start the async event loop for bot execution.
"""

from __future__ import annotations

# ruff: noqa: SLF001
# v3.23.88 justification: main.py is the boot script — it deliberately
# reaches into BotManager / bot / bus internals (_bots, _bus,
# _status_log, _start_all_cancel, _on_bot_command, _on_finished_callback)
# to wire together subsystems that don't yet expose public wiring APIs.
# Refactoring 14 sites to public accessors is a separate, larger
# design change (v3.24.x candidate). Module-level noqa keeps this
# cascade tightly scoped to the safety/hygiene fixes.

from typing import Optional, TYPE_CHECKING  # v3.23.88: _CRASH_LOG_PATH sentinel

# Purge bytecache to ensure fresh source is always loaded
import os, shutil

for _root, _dirs, _ in os.walk(os.path.dirname(os.path.abspath(__file__))):
    for _d in _dirs:
        if _d == "__pycache__":
            shutil.rmtree(os.path.join(_root, _d), ignore_errors=True)

# Type-checker-only import. PySide6 is imported lazily everywhere else in
# this file so a missing toolkit produces the friendly message at the Qt
# setup block instead of an ImportError at module load; the guard keeps
# that true while still giving _make_async_pump_timer a real return type.
if TYPE_CHECKING:
    from PySide6.QtCore import QTimer


# ---------------------------------------------------------------------------
# v3.15.97 — STALE BINARY DETECTOR
# ---------------------------------------------------------------------------
# Operator-reported 2026-04-28: persistent UnboundLocalError on bb_result and
# NameError on _phantom_locked were traced to a stale PyInstaller .exe in
# dist/Acervator/_internal/ (built at v3.15.43). The operator believed they
# were running v3.15.95 because the latest extracted source titled v3.15.95,
# but the running binary was v3.15.43. Three sessions of doc-sweep + code
# fixes had no effect on what they were actually executing.
#
# Detection: compare the version the live tree resolves from git against the
# version the build baked into dist/Acervator/_internal/. If they differ,
# emit a LOUD warning to stderr AND to a marker file in ~/.acervator_logs/
# so the operator sees the mismatch before the GUI hides the stderr stream.
# ---------------------------------------------------------------------------
def _early_debug(msg: str, *args: object) -> None:
    """Best-effort debug output for code running BEFORE logging exists.

    v3.24.34 (C43 step 7 / NF-154). `logger` is not bound until
    main.py:329, but `_check_stale_dist_binary()` is invoked at :226.
    Its three diagnostic calls therefore referenced an unbound name, and
    the failure chain made that a boot crash rather than a lost log
    line:

      1. an inner `except` fires and calls logger.debug -> NameError
      2. that propagates to the OUTER `except Exception` guard
      3. the outer handler calls logger.debug -> NameError again
      4. nothing catches this one; it escapes the function, reaches
         module level, and kills the process before the GUI starts

    The guard's own comment reads "Guard must NEVER raise - it's purely
    informational." Only the happy path honoured that, which is why it
    never fired: the guard returns early unless BOTH src/__init__.py and
    dist/Acervator/_internal/src/__init__.py exist with differing
    versions -- i.e. it was armed only for an operator running a source
    tree beside a stale build, exactly when the warning should help.

    Quiet unless ACERVATOR_DEBUG_BOOT=1, and swallows everything: a
    diagnostic helper that can raise reintroduces the defect it fixes.
    """
    try:
        import os as _o
        import sys as _s

        if _o.environ.get("ACERVATOR_DEBUG_BOOT") != "1":
            return
        _s.stderr.write("[boot] " + (msg % args if args else msg) + "\n")
    except Exception:  # noqa: BLE001,S110 - must never raise; see docstring
        pass  # noqa: S110 - swallowing is the contract, not an oversight


# ---------------------------------------------------------------------------
# The crash-diagnostic log root, and the single override that moves it
# ---------------------------------------------------------------------------
# v3.24.xx — the crash logger was the last writer into the operator's
# runtime tree with no redirect. Every other one already has this hook
# (SIM_LOG_ROOT_ENV, ACERVATOR_TELEMETRY_ROOT, ACERVATOR_SETTINGS_ROOT);
# this one resolved straight to Path.home() and so appended to a REAL
# crash log whenever the suite tripped an excepthook. Caught by
# tests/conftest.py's live-tree guard on 2026-08-07, which named the
# exact file it had modified.
#
# v3.25.6 (C43) — declared HERE, above _setup_faulthandler, rather
# than beside _get_crash_log_path further down. faulthandler is armed
# at module exec, well before that point, so the constant has to
# exist first. The faulthandler log reads the SAME variable: both
# files are per-run crash diagnostics written to one directory and
# correlated by timestamp, so a second variable would be a second
# thing to keep in sync and a second way to half-apply the redirect.
#
# v3.25.7 (C43) — moved EARLIER STILL, above _check_stale_dist_binary.
# That guard is the THIRD writer on the same variable, and it is
# CALLED earlier than the faulthandler arming -- far earlier than the
# position this constant used to hold. A name read before it is bound
# raises NameError, and that one would be caught by the guard's own
# best-effort except and reported as a failed marker write, so the
# redirect would read as applied while silently doing nothing. The
# declaration therefore sits above EVERY reader, and
# tests/test_stale_dist_marker_redirect.py pins that order.
#
# MEASURED 2026-08-14, before this change: 2,154 faulthandler_*.log
# files stood in ~/.acervator_logs, 2,127 of them header-only. The
# writer was `import main` at pytest COLLECTION time, which arms
# faulthandler as a module-level side effect. crash_* was redirected
# by the override below and faulthandler_* was not, so the leak
# survived a guard whose own comment names the file.
CRASH_LOG_ROOT_ENV = "ACERVATOR_CRASH_LOG_ROOT"


def _check_stale_dist_binary() -> None:
    """Warn loudly if dist/Acervator/_internal/ contains a stale binary,
    and remove that warning once the staleness is gone.

    The marker file goes to CRASH_LOG_ROOT_ENV when that variable is
    set, and to the operator's ~/.acervator_logs otherwise -- the same
    resolution _setup_faulthandler uses, because it is the same
    directory. The default is the real runtime behaviour and is
    conditional on nothing: a stale dist on the operator's machine
    still drops the marker where they look for it, with the same name
    and the same contents.

    v3.25.8 (C43) -- the marker is now cleared when, and only when,
    both versions are readable and EQUAL. It used to be write-only, so
    a rebuild that fixed the mismatch left a file behind still naming
    the old pair. Everything the guard DETECTS, and every condition
    under which it WARNS, is unchanged.

    The source tree states no version literal, so the live side is the
    version src/_version.py resolves from git and the dist side is the
    value the build baked into the bundle. A bundle built before the
    bake still carries a __version__ literal, and is read that way.
    """
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        live_init = os.path.join(here, "src", "__init__.py")
        bundle_root = os.path.join(here, "dist", "Acervator", "_internal")
        dist_init = os.path.join(bundle_root, "src", "__init__.py")
        dist_baked = os.path.join(bundle_root, "src", "_baked_version.txt")
        if not os.path.isfile(live_init):
            return
        if not os.path.isfile(dist_baked) and not os.path.isfile(dist_init):
            return

        def _read_version(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        s = line.strip()
                        if s.startswith("__version__"):
                            # __version__ = "3.15.97"
                            parts = s.split("=", 1)
                            if len(parts) == 2:
                                return parts[1].strip().strip('"').strip("'")
            except Exception as _ver_exc:  # noqa: BLE001 - version parse best-effort
                _early_debug("stale-binary version parse skipped %s: %s", p, _ver_exc)
            return None

        def _live_version():
            """Resolve the source tree's version, or None when it cannot be."""
            try:
                from src._version import UNKNOWN_VERSION, resolve_version

                resolved = resolve_version(here)
            except Exception as _live_exc:  # noqa: BLE001 - best-effort
                _early_debug("stale-binary live version skipped: %s", _live_exc)
                return None
            return None if resolved == UNKNOWN_VERSION else resolved

        def _baked_or_literal_version():
            """Read the bundle's baked version, falling back to its literal."""
            try:
                from src._version import read_baked_version

                baked = read_baked_version(bundle_root)
            except Exception as _baked_exc:  # noqa: BLE001 - best-effort
                _early_debug("stale-binary baked version skipped: %s", _baked_exc)
                baked = ""
            return baked or _read_version(dist_init)

        # ONE resolution of the marker directory, used by BOTH the write
        # and the clear.
        #
        # v3.25.8 (C43) — the unit before this one taught the guard to
        # honour CRASH_LOG_ROOT_ENV, which turned a second spelling of
        # this directory from untidy into dangerous: the marker can now
        # land in a temp root OR in the operator's home, so a clear that
        # resolved the path its own way could remove one copy and leave
        # the other latched. The write path still calls this INSIDE its
        # own `try`, so a resolution failure cannot suppress the stderr
        # banner that runs above it.
        def _marker_path():
            from pathlib import Path as _P

            _override = os.environ.get(CRASH_LOG_ROOT_ENV)
            marker_dir = _P(_override) if _override else _P.home() / ".acervator_logs"
            return marker_dir / "STALE_DIST_WARNING.txt"

        def _report_clear_failure(path, exc):
            """Say out loud that a stale marker could NOT be removed.

            _early_debug is quiet unless ACERVATOR_DEBUG_BOOT=1, so it
            alone would make a failed clear invisible forever — and a
            marker that outlives its own mismatch is precisely the
            "which code am I running" confusion the marker exists to
            end. This fires ONLY on a failed removal, never on the
            ordinary silent path, and it cannot raise: an absent or
            closed stderr returns instead of propagating.
            """
            try:
                stream = getattr(sys, "stderr", None)
                if stream is None:
                    return
                stream.write(
                    "ACERVATOR: the stale-binary marker could not be "
                    f"removed: {path or '<unresolved>'} ({exc}). The "
                    "source and dist versions now AGREE, so that file "
                    "names versions that are no longer current. Delete "
                    "it by hand.\n"
                )
                stream.flush()
            except (OSError, ValueError, AttributeError) as _rep_exc:
                _early_debug("stale-binary clear notice failed: %s", _rep_exc)

        live_ver = _live_version()
        dist_ver = _baked_or_literal_version()
        if live_ver and dist_ver and live_ver != dist_ver:
            msg = (
                "\n"
                "============================================================\n"
                "  ACERVATOR STALE BINARY WARNING (v3.15.97 guard)           \n"
                "============================================================\n"
                f"  Live source version : {live_ver}\n"
                f"  dist/.exe version   : {dist_ver}\n"
                "                                                            \n"
                "  The PyInstaller binary in dist/Acervator/Acervator.exe   \n"
                "  is OUT OF DATE relative to the source code in src/.       \n"
                "  If you double-click the .exe, you are running OLD code   \n"
                "  with bugs that have since been fixed.                     \n"
                "                                                            \n"
                "  ACTION: either run `python main.py` from this source     \n"
                "  tree, or rebuild the .exe via BUILD.py before launching.  \n"
                "============================================================\n"
            )
            sys.stderr.write(msg)
            sys.stderr.flush()
            try:
                # mkdir stays HERE, on the write path only. The clear
                # below must never build a tree in order to delete from
                # it — that would put an empty .acervator_logs in every
                # temp root and on every developer machine that has none.
                marker_path = _marker_path()
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                with open(marker_path, "w", encoding="utf-8") as f:
                    f.write(msg)
            except Exception as _mk_exc:  # noqa: BLE001 - marker write best-effort
                _early_debug("stale-binary marker write failed: %s", _mk_exc)
        elif live_ver and dist_ver:
            # THE LATCH RESET (v3.25.8, C43).
            #
            # The stderr banner is EDGE-correct: it fires on the run
            # where the versions disagree and is silent afterwards. The
            # marker file was LEVEL-latched with no clear — written on
            # the mismatch and then left behind by the matched path,
            # which returned before the directory was even resolved. A
            # marker naming 3.25.7 vs 3.25.6 survived the rebuild that
            # made both 3.25.7, so the one artefact whose whole job is
            # to answer "which code am I running" answered it wrongly.
            #
            # ARMED BY THE SAME EVIDENCE AS THE WARNING, INVERTED. Both
            # version files present, both parsed, and equal. An
            # unreadable version (_read_version -> None) and a missing
            # dist both mean "cannot tell", not "the mismatch is gone",
            # and clearing on either would delete a TRUE warning: a
            # rebuild in flight can make dist momentarily unreadable,
            # and a stale dist moved aside is still a stale dist.
            #
            # No mkdir, and no unconditional unlink: probe for the file,
            # so a tree that has no log directory keeps not having one.
            marker_path = None
            try:
                marker_path = _marker_path()
                if marker_path.is_file():
                    marker_path.unlink()
            except (OSError, ValueError, RuntimeError) as _rm_exc:
                _early_debug("stale-binary marker clear failed: %s", _rm_exc)
                _report_clear_failure(marker_path, _rm_exc)
    except Exception as _guard_exc:  # noqa: BLE001 - guard must never raise
        # Guard must NEVER raise — it's purely informational.
        _early_debug("stale-binary guard suppressed exception: %s", _guard_exc)


# Defer the import of `sys` until we have it; this guard runs after the
# stdlib imports below — but we need stderr now, so do a minimal import.
import sys  # noqa: E402

_check_stale_dist_binary()

import asyncio
import faulthandler
import logging
import os
import threading
import traceback
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# MEM-217 (Session 24 Phase 3a) — faulthandler
# ---------------------------------------------------------------------------
# Native-level crash handler. Python's stdlib faulthandler catches
# SIGSEGV, SIGFPE, SIGILL, SIGABRT, and fatal Python errors BEFORE the
# process dies, dumping the Python traceback of every thread to a file.
#
# This complements MEM-216's Python-level hooks:
#   - MEM-216 hooks catch Python exceptions that would otherwise be
#     silently discarded (Qt app stderr never reaches the user).
#   - MEM-217 faulthandler catches NATIVE crashes (Qt qFatal → abort(),
#     memory corruption, stack overflow, etc.) that MEM-216 cannot see
#     because the Python interpreter is dead by the time they fire.
#
# Registered FIRST, before any imports that might touch C extensions,
# so that if any of those imports itself crashes, we still get a trace.
# ---------------------------------------------------------------------------


def _setup_faulthandler():
    """Open a per-run faulthandler log and register it. Returns the open
    file handle so the caller keeps it alive for the process lifetime.

    The directory is CRASH_LOG_ROOT_ENV when that variable is set,
    and the operator's ~/.acervator_logs otherwise. The default is
    the real runtime behaviour and is conditional on nothing: a
    native crash on the operator's machine still dumps where they
    look for it, with the same name and the same header.
    """
    _override = os.environ.get(CRASH_LOG_ROOT_ENV)
    log_dir = Path(_override) if _override else Path.home() / ".acervator_logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_dir = Path.cwd()
    fh_path = log_dir / f"faulthandler_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    try:
        # v3.23.88 noqa justification: this file handle is passed to
        # faulthandler.enable(file=fh_file) and must remain open for
        # the entire process lifetime as the destination for fatal-
        # signal dumps. A `with` block would close it on exit, which
        # defeats the purpose. Deliberate long-lived handle.
        fh_file = open(
            fh_path, "a", buffering=1
        )  # noqa: SIM115 - line-buffered lifetime handle
        # Write a header so we can correlate with crash_*.log entries
        fh_file.write(
            f"=== faulthandler started {datetime.now().isoformat()} "
            f"pid={os.getpid()} py={sys.version.split()[0]} "
            f"platform={sys.platform} ===\n"
        )
        fh_file.flush()
        faulthandler.enable(file=fh_file, all_threads=True)
        # On Unix, register SIGUSR1 to dump all threads on demand.
        # On Windows, faulthandler.register is not available for signals,
        # but faulthandler.enable() already covers the fatal signals.
        if hasattr(faulthandler, "register") and hasattr(
            __import__("signal"), "SIGUSR1"
        ):
            try:
                import signal

                faulthandler.register(
                    signal.SIGUSR1, file=fh_file, all_threads=True, chain=False
                )
            except (AttributeError, ValueError, OSError):
                pass
        return fh_file, fh_path
    except Exception as exc:
        # If faulthandler can't be set up, log and continue. We still
        # have MEM-216's Python-level hooks.
        sys.stderr.write(f"MEM-217: faulthandler setup failed: {exc}\n")
        return None, None


_FH_FILE, _FH_PATH = _setup_faulthandler()


# Fix Windows asyncio: ProactorEventLoop (default on Win 3.10+) is
# incompatible with aiohttp. Force SelectorEventLoop.
#
# v3.19.9 (Python 3.14+) — asyncio.set_event_loop_policy and
# asyncio.WindowsSelectorEventLoopPolicy are BOTH deprecated; both
# slated for removal in Python 3.16. Migrated to the modern
# asyncio.set_event_loop(SelectorEventLoop()) pattern, which sets
# the loop for the current thread directly without the policy
# indirection. For a single-threaded GUI entry point this is
# semantically equivalent.
if sys.platform == "win32":
    asyncio.set_event_loop(asyncio.SelectorEventLoop())

# ---------------------------------------------------------------------------
# Bootstrap logging before anything else
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("acervator")

# ---------------------------------------------------------------------------
# MEM-263 (v3.18.5) — Silence chatty 3rd-party loggers to prevent the
# unbounded-log-growth incident observed 2026-05-19 (v3.18.1):
# ~/.acervator_logs/postmortem_20260519_191924/console_20260519_085307.log
# reached 6.7 GB in a single ~10-hour run. Root cause: ccxt.base.exchange
# and urllib3.connectionpool were logging every API call at DEBUG level
# including full HTTP response headers (~3KB per request × ~20 bots
# polling every few seconds = unbounded growth).
#
# WARNING level keeps the diagnostically-useful messages (failures,
# rate-limit hits, retries) while dropping the per-request chatter.
# Acervator's own loggers stay at INFO (the operator-facing event stream
# the dashboards consume).
# ---------------------------------------------------------------------------
for _noisy in (
    "ccxt",
    "ccxt.base",
    "ccxt.base.exchange",
    "urllib3",
    "urllib3.connectionpool",
    "urllib3.util.retry",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# MEM-216 (Session 24) — Crash diagnostic hooks
# ---------------------------------------------------------------------------
# Three live-run attempts in Session 23 shipped "fixes" for silent app
# crashes that could not be root-caused because the app produced no
# diagnostic output when it died. Qt's qFatal, uncaught Python exceptions
# in threads, and unhandled asyncio Future exceptions all exit the
# process with NO stderr output on Windows, leaving the developer with
# nothing to debug.
#
# These hooks catch and persist every class of failure BEFORE the
# process is killed, writing to a dedicated crash log that survives
# termination. On the next crash, look in ~/.acervator_logs/ for
# crash_YYYYMMDD_HHMMSS.log.
#
# Hooks installed:
#   sys.excepthook         — uncaught exceptions in main thread
#   threading.excepthook   — uncaught exceptions in any Thread
#   asyncio exception handler — unhandled Future exceptions
#   qInstallMessageHandler — Qt C++ warnings/critical/fatal messages
# ---------------------------------------------------------------------------

# v3.23.88: explicit module-level sentinel replaces the prior NameError
# dance. Pyright can now see the type flow; behaviour is identical
# (first call resolves the path + caches it, subsequent calls return
# the cached value).
_CRASH_LOG_PATH: Optional[Path] = None


def _get_crash_log_path() -> Path:
    """Per-run crash log path. Stable within a single run, unique per launch."""
    global _CRASH_LOG_PATH
    if _CRASH_LOG_PATH is not None:
        return _CRASH_LOG_PATH
    _override = os.environ.get(CRASH_LOG_ROOT_ENV)
    log_dir = Path(_override) if _override else Path.home() / ".acervator_logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as _mk_exc:  # noqa: BLE001 - fall back to cwd
        logger.debug("crash log dir mkdir fell back to cwd: %s", _mk_exc)
        log_dir = Path.cwd()
    _CRASH_LOG_PATH = log_dir / f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    return _CRASH_LOG_PATH


def _crash_log(category: str, message: str) -> None:
    """Append a diagnostic entry to the crash log file. Best-effort;
    never raises. Flushes immediately because the process may be
    about to die."""
    try:
        ts = datetime.now().isoformat(timespec="milliseconds")
        line = f"[{ts}] [{category}] [thread={threading.current_thread().name}] {message}\n"
        with open(_get_crash_log_path(), "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception as _crash_exc:  # noqa: BLE001 - diagnostic of last resort
        # We are the diagnostic of last resort; log to logger but do not raise.
        logger.debug("crash log write suppressed exception: %s", _crash_exc)


def _install_diagnostic_hooks() -> None:
    """Install sys, threading, asyncio, and Qt exception handlers.
    Each handler writes to the crash log before delegating to any
    original handler. Idempotent — safe to call more than once."""

    # --- sys.excepthook — uncaught exceptions in main thread ---
    _original_excepthook = sys.excepthook

    def _sys_excepthook(exc_type, exc_value, tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, tb))
        _crash_log("SYS_EXCEPTHOOK", f"{exc_type.__name__}: {exc_value}\n{tb_text}")
        logger.error("UNCAUGHT EXCEPTION: %s: %s", exc_type.__name__, exc_value)
        import contextlib

        with contextlib.suppress(Exception):
            _original_excepthook(exc_type, exc_value, tb)

    sys.excepthook = _sys_excepthook

    # --- threading.excepthook — uncaught exceptions in any Thread ---
    def _thread_excepthook(args):
        tb_text = "".join(
            traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback
            )
        )
        thread_name = args.thread.name if args.thread else "unknown"
        _crash_log(
            "THREAD_EXCEPTHOOK",
            f"thread={thread_name} {args.exc_type.__name__}: "
            f"{args.exc_value}\n{tb_text}",
        )
        logger.error(
            "UNCAUGHT EXCEPTION in thread %s: %s: %s",
            thread_name,
            args.exc_type.__name__,
            args.exc_value,
        )

    threading.excepthook = _thread_excepthook

    _crash_log(
        "BOOT",
        f"Diagnostic hooks installed. Python {sys.version.split()[0]} on {sys.platform}.",
    )


def _install_asyncio_handler(loop) -> None:
    """Install an asyncio exception handler on the given loop.
    Must be called AFTER the loop is created (see pump_async setup)."""

    def _asyncio_exception_handler(loop, context):
        msg = context.get("message", "")
        exc = context.get("exception")
        if exc:
            tb_text = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
            _crash_log(
                "ASYNCIO", f"{type(exc).__name__}: {exc} | message={msg}\n{tb_text}"
            )
            logger.error(
                "UNHANDLED ASYNCIO EXCEPTION: %s: %s | message=%s",
                type(exc).__name__,
                exc,
                msg,
            )
        else:
            _crash_log("ASYNCIO", f"message={msg} | context={context}")
            logger.error("ASYNCIO ERROR: %s", msg)

    loop.set_exception_handler(_asyncio_exception_handler)


def _install_qt_message_handler() -> None:
    """Install Qt's message handler to capture C++ warnings, criticals,
    and fatals. Called AFTER QApplication is constructed."""
    try:
        from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    except ImportError:
        return

    _level_names = {
        QtMsgType.QtDebugMsg: "QT_DEBUG",
        QtMsgType.QtInfoMsg: "QT_INFO",
        QtMsgType.QtWarningMsg: "QT_WARNING",
        QtMsgType.QtCriticalMsg: "QT_CRITICAL",
        QtMsgType.QtFatalMsg: "QT_FATAL",
        QtMsgType.QtSystemMsg: "QT_SYSTEM",
    }

    def _qt_message_handler(msg_type, context, message):
        level = _level_names.get(msg_type, "QT_UNKNOWN")
        loc = f"{context.file}:{context.line}" if context.file else ""
        _crash_log(level, f"{message} | {loc}")
        if msg_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            logger.error("%s: %s", level, message)

    qInstallMessageHandler(_qt_message_handler)
    _crash_log("BOOT", "Qt message handler installed.")


# Install the Python-level hooks IMMEDIATELY on module load so they
# catch any failure during the rest of main.py.
_install_diagnostic_hooks()


# ---------------------------------------------------------------------------
# MEM-217 — heartbeat file. External watchdog polls this file's mtime;
# if it stops advancing the app is presumed hung or crashed. Written to
# the same log dir as crash logs for easy correlation. Must be written
# from the main thread (via QTimer below) so that GUI-thread freezes
# stop the heartbeat, which is exactly what we want to detect.
# ---------------------------------------------------------------------------
def _heartbeat_path() -> Path:
    log_dir = Path.home() / ".acervator_logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_dir = Path.cwd()
    return log_dir / "heartbeat.txt"


def _write_heartbeat():
    """Best-effort write of the current timestamp + pid. Never raises."""
    try:
        with open(_heartbeat_path(), "w", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} pid={os.getpid()}\n")
    except Exception as _hb_exc:  # noqa: BLE001 - heartbeat best-effort
        logger.debug("heartbeat write suppressed exception: %s", _hb_exc)


# ---------------------------------------------------------------------------
# The asyncio pump timer.
# ---------------------------------------------------------------------------
# Every coroutine in this application runs on the Qt GUI thread. There is
# no separate asyncio thread: this timer is the ONLY thing that advances
# the loop, so its cadence is the loop's cadence.
#
# Built here rather than inline in main() so the timer's configuration is
# reachable from a test. Asserting on the text of main() would pin the
# source, not the object Qt actually schedules.
#
# The QTimer is the SCHEDULER. The call it makes lives in
# src/core/tick_driver.py, which imports no Qt, so the same call runs
# headless through AsyncioTickDriver at the same cadence.
# ---------------------------------------------------------------------------
# Must equal src.core.tick_driver.PUMP_INTERVAL_MS. Restated here rather
# than imported: every src import in this file is inside a function,
# because the bootstrap above runs before src/ is guaranteed importable.
# tests/test_tick_driver_is_qt_free.py fails when the two differ.
ASYNC_PUMP_INTERVAL_MS = 50


def _make_async_pump_timer(
    loop: asyncio.AbstractEventLoop, interval_ms: int = ASYNC_PUMP_INTERVAL_MS
) -> QTimer:
    """Return the QTimer that drains `loop`'s ready callbacks.

    PreciseTimer is not decoration. A QTimer whose type is never set
    reports Qt.TimerType.CoarseTimer, and Qt gives a coarse timer 5%
    of drift and permission to coalesce with other timers so it can
    wake the process less often. Measured on the operator's machine,
    240 firings per configuration with the first 20 discarded:

        CoarseTimer   median 62.63 ms   for a 50 ms request
        PreciseTimer  median 49.96 ms

    The Windows system-tick explanation was tested and refuted --
    timeBeginPeriod(1) left the coarse median at 62.30 ms. The timer
    type is the whole difference.

    Scope, so this is not mistaken for the freeze fix: it recovers
    about 12.6 ms per pump cycle. It does not explain a multi-second
    button delay, and it is not offered as an explanation of one.

    The pump body is src.core.tick_driver.pump_once, which holds no Qt.
    This function supplies only the schedule.
    """
    from PySide6.QtCore import Qt, QTimer

    from src.core.tick_driver import pump_once

    def pump_async():
        """Run pending async callbacks."""
        pump_once(loop)

    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.setInterval(interval_ms)
    timer.timeout.connect(pump_async)
    return timer


def main() -> int:
    """Application entry point."""

    # TD-023: test hook — MEM-219 child-mode regression test needs to prove it
    # reached this function, not exercise the full GUI bootstrap. If set, exit
    # successfully as a positive child-path signal. The env var is NOT
    # documented and is gated to test harness use only.
    import os as _os

    if _os.environ.get("_ACERVATOR_TEST_EXIT_IMMEDIATELY") == "1":
        sys.stderr.write("MEM-219 test hook: main() entered, exiting 0\n")
        return 0

    # v3.24.34 (C43/NF-133) — single source of truth for the banner.
    # These three literals were hardcoded and drifted: the boot log and
    # setApplicationVersion both still read "3.1.26" at build v3.24.32,
    # 23 minor versions stale, so every log the operator collected was
    # stamped with the wrong build. The release gate never opened this
    # file, so nothing caught it. Pinned by
    # tests/test_check_release_readiness.py::TestMainPyVersionLiterals.
    # Imported lazily inside main(), matching this module's idiom — the
    # bootstrap runs before src/ is guaranteed importable at module scope.
    from src import __version__ as _acervator_version

    # --- Dependency check (non-blocking — warn only) ---------------------
    import importlib.util

    _missing = []
    for _mod, _pip in [
        ("ccxt", "ccxt"),
        ("cryptography", "cryptography"),
        ("aiohttp", "aiohttp"),
        ("numpy", "numpy"),
    ]:
        if importlib.util.find_spec(_mod) is None:
            _missing.append(_pip)
    if _missing:
        logger.warning(
            "Missing packages: %s — install via: pip install %s",
            ", ".join(_missing),
            " ".join(_missing),
        )

    # --- psutil auto-install (silent, best-effort) ----------------------
    # psutil is required for Nuclear mode. Rather than block the user
    # with a dialog, we try to install it at startup via
    # `{sys.executable} -m pip install psutil`. This targets the SAME
    # Python running Acervator by construction, so install cannot
    # land in the wrong interpreter.
    # If this fails (no internet, proxy, permissions), the Nuclear
    # mode entry point still has an in-app installer dialog as
    # fallback. But 95% of users will never see that — the auto-
    # install succeeds and Nuclear mode just works on first click.
    # sadp: R28 FL — we log loudly on failure so nothing is masked
    if importlib.util.find_spec("psutil") is None:
        import sys as _sys
        import subprocess as _sp

        logger.info(
            "psutil not found — attempting silent install via "
            "`%s -m pip install psutil>=5.9.0`",
            _sys.executable,
        )
        try:
            r = _sp.run(
                [_sys.executable, "-m", "pip", "install", "--quiet", "psutil>=5.9.0"],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if r.returncode == 0:
                importlib.invalidate_caches()
                if importlib.util.find_spec("psutil") is not None:
                    logger.info("psutil installed successfully at startup.")
                else:
                    logger.warning(
                        "pip reported success but psutil still not "
                        "importable — Nuclear mode will offer in-app "
                        "install dialog on first use."
                    )
            else:
                logger.warning(
                    "Silent psutil install failed (rc=%d). Nuclear mode "
                    "will offer in-app install dialog on first use. "
                    "stderr: %s",
                    r.returncode,
                    (r.stderr or "")[:400],
                )
        except Exception as _e:
            logger.warning(
                "Silent psutil install errored (%s: %s). Nuclear mode "
                "will offer in-app install dialog on first use.",
                type(_e).__name__,
                _e,
            )

    # --- Stone Tablets registry (v3.23.97) -----------------------------
    # Operator directive 2026-08-01: Stone Tablets are a core part of
    # the program. Load MANIFEST at boot so coverage state is visible
    # from the first tick. Never fetches — pure index read.
    try:
        from src.trading.stone_tablets import get_registry as _get_st_reg

        _st = _get_st_reg()
        _cov = _st.coverage_summary()
        logger.info(
            "Stone Tablets: %d tablet(s) covering %d asset(s)",
            sum(c.tablet_count for c in _cov),
            len(_cov),
        )
        _stale = _st.stale_assets(threshold_days=2)
        if _stale:
            logger.info(
                "Stone Tablets: %d asset(s) stale (last candle " ">2d old): %s",
                len(_stale),
                ", ".join(_stale[:10]),
            )
    except Exception as _st_exc:  # noqa: BLE001 - boot-diagnostic best-effort
        logger.warning(
            "Stone Tablets registry init failed at boot: %s "
            "(sim replay will need to fetch on demand)",
            _st_exc,
        )

    # --- Core services --------------------------------------------------
    from src.core.settings import SettingsManager
    from src.core.logging_engine import LogManager
    from src.core.encryption import (
        KeyringManager,
    )  # v3.23.88: CredentialVault import retired (unused)
    from src.core.event_bus import get_event_bus
    from src.trading.bot_container import BotManager

    settings = SettingsManager()
    log_manager = LogManager()
    KeyringManager()  # constructed for its keyring-backend probe side effect
    bus = get_event_bus()
    bot_manager = BotManager()

    # v3.15.78 — Wire LogManager to the event bus so executed trades
    # land in logs/real_market/trade.log as NDJSON. Operator-reported
    # 2026-04-27: "The platform is not producing any trade logs. I am
    # seeing the logs sub directories remain empty across iterations."
    # Pre-fix: log_trade() was defined but never called by anyone.
    log_manager.attach_to_bus(bus)

    # v3.16.60 — Symbol resolver. Operator-reported 2026-05-15: every
    # trade.log entry had empty "symbol" field because emit sites don't
    # include it. Resolver looks up bot.config.symbol by bot_id via
    # the BotManager so trade.log entries can be audited by asset.
    def _resolve_bot_symbol(bot_id: str) -> str:
        try:
            bot = (
                bot_manager.get_bot(bot_id) if hasattr(bot_manager, "get_bot") else None
            )
            if bot is None:
                bot = (
                    bot_manager._bots.get(bot_id)
                    if hasattr(bot_manager, "_bots")
                    else None
                )
            if bot is not None and hasattr(bot, "config"):
                return str(getattr(bot.config, "symbol", "") or "")
        except Exception as _res_exc:  # noqa: BLE001 - R28-OK: resolver fail-soft
            logger.debug("symbol resolver skipped bot_id %r: %s", bot_id, _res_exc)
        return ""

    if hasattr(log_manager, "set_symbol_resolver"):
        log_manager.set_symbol_resolver(_resolve_bot_symbol)

    log_manager.info(f"Acervator v{_acervator_version} starting")

    # v3.24.88 - START COLLECTING SIGNALS.
    #
    # Operator, 2026-08-08: "Emitters don't work unless program is
    # running or a debug is performed." Until now the only caller of
    # `set_sink` was a Fleet Replay run, so outside the Simulator every
    # emit() in the platform was inert and the expected-vs-actual
    # network reported nothing about live operation.
    #
    # Best-effort: a sink that cannot open its file returns None and the
    # application starts normally. Instrumentation never blocks launch.
    try:
        from src.core.signal_contract import install_process_sink

        _sig_sink = install_process_sink()
        if _sig_sink is not None:
            log_manager.info(f"Signal collection active -> {_sig_sink.path}")
    except Exception as _sig_exc:  # noqa: BLE001 - advisory
        log_manager.warning(f"Signal collection unavailable: {_sig_exc}")

    # --- Qt application -------------------------------------------------
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
    except ImportError:
        logger.error(
            "PySide6 is required for the GUI. "
            "Install via: pip install PySide6 --break-system-packages"
        )
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("Acervator")
    app.setApplicationVersion(_acervator_version)

    # MEM-216 — install Qt message handler now that QApplication exists.
    # This catches Qt C++ warnings, criticals, and fatals (including
    # qFatal that otherwise kills the process silently on Windows).
    _install_qt_message_handler()

    # ---------------------------------------------------------------------
    # MEM-263 (v3.18.5) — Centralize garbage collection on the GUI thread
    # ---------------------------------------------------------------------
    # Operator-observed crash 2026-05-19 08:53 (v3.18.1): Windows
    # STATUS_ACCESS_VIOLATION (0xC0000005) on a CCXT worker thread mid-
    # JSON-parse, during automatic garbage collection. Faulthandler trace
    # at ~/.acervator_logs/faulthandler_20260519_085308.log showed:
    #   Crashing thread (ccxt-coinbase_0):
    #     Garbage-collecting
    #     json/decoder.py:361 raw_decode
    #     ccxt/base/exchange.py:592 on_json_response
    #     ccxt/coinbase.py:3672 fetch_ohlcv
    #   Main thread (incidentally) in indicator_panel.py:264 paintEvent
    #
    # Root cause: CPython's automatic GC scheduler can fire on ANY
    # thread, including CCXT worker threads holding C-extension state
    # from urllib3 / OpenSSL / lxml. When a Qt widget happens to be
    # painting on the main thread at the same time, the access-violation
    # window opens.
    #
    # Standard mitigation: disable automatic GC, run gc.collect()
    # manually on a QTimer from the GUI thread. GC pauses become
    # predictable + always happen on a known-safe thread. Removes the
    # race surface entirely. Verified mitigation for this exact pattern
    # in heavy PySide6 + multi-threaded JSON-parsing applications.
    # ---------------------------------------------------------------------
    import gc as _gc

    _gc.disable()
    _gc_timer = QTimer()
    _gc_timer.timeout.connect(lambda: _gc.collect())
    _gc_timer.start(5000)  # every 5 seconds on the GUI thread
    log_manager.info(
        "MEM-263: automatic GC disabled; periodic gc.collect() "
        "scheduled on GUI thread (5s cadence). Mitigates CCXT-worker-"
        "thread access violation pattern observed v3.18.1."
    )
    # Keep the timer alive for the process lifetime by holding a
    # module-level reference (QTimer is garbage-collected normally
    # otherwise; we just disabled the only thing that would collect it
    # but operator's QObject parent chain would too — still belt+suspenders).
    globals()["_persistent_gc_timer"] = _gc_timer

    # --- Apply theme ----------------------------------------------------
    from src.gui.theme_engine import ThemeManager

    theme_mgr = ThemeManager()
    theme_name = settings.get("theme", "cyberpunk_dark")
    theme_mgr.apply_theme(theme_name, app)

    # --- First-run wizard OR version change ----------------------------
    username = settings.get("username", "")
    stored_version = settings.get("app_version", "")
    current_version = _acervator_version

    if not username:
        # First run — set default username, skip wizard
        settings.set("username", "User")
        settings.set("app_version", current_version)
        username = "User"
        log_manager.info("First run — default user created, no wizard")

    # Update stored version silently on upgrade
    if stored_version != current_version:
        settings.set("app_version", current_version)
        log_manager.info(f"Version updated {stored_version} -> {current_version}")

    # --- Direct launch to Crypto MainWindow (no launcher) ----------------
    from src.gui.main_window import MainWindow
    from src.core.state_manager import StateManager
    from src.trading.risk_manager import RiskManager
    from src.trading.analytics_engine import AnalyticsEngine
    from src.core.notifications import get_notification_manager

    state_mgr = StateManager()
    bot_manager.set_state_manager(state_mgr)

    # v3.24.35 (C01 PR-0 / E2) — take a pre-session copy of the state
    # files BEFORE anything can overwrite them.
    #
    # Placement is the whole point. This runs after StateManager exists
    # but before all three writers:
    #   :720  has_saved_state() / restore  — the read that decides
    #                                        whether bots come back
    #   :1035 save_timer.start(60000)      — the 60s rolling save
    #   :1190 save_all_state() on shutdown
    #
    # The rolling backup is only one cycle deep: bot_state.backup holds
    # the previous 60 seconds and nothing older, which survives exactly
    # one bad save. This copy survives more than one, and nothing in the
    # normal save path can reach it.
    #
    # Bounded (StateManager.PREFLIGHT_KEEP) and skipped entirely when
    # the state is byte-identical to the newest existing snapshot, so
    # repeated restarts do not accumulate copies. Cannot raise.
    _preflight = state_mgr.preflight_snapshot()
    if _preflight:
        log_manager.info(
            f"Preflight: {len(_preflight)} state file(s) copied aside "
            f"before restore"
        )
    # v3.24.35 — surface pre-existing C01 damage while it is still
    # recoverable. The backup lags the primary by one save cycle, so a
    # bot present there and missing from the primary was pruned by the
    # LAST save and has one cycle left before the copy is overwritten.
    _damaged = state_mgr.diff_primary_vs_backup()
    if _damaged:
        log_manager.warning(
            f"Preflight: {len(_damaged)} bot(s) exist in the backup but "
            f"NOT in the primary state file: {', '.join(_damaged[:5])}"
        )

    # Volume-aware trade execution guard
    from src.trading.volume_guard import VolumeGuard, VolumeGuardConfig

    volume_guard = VolumeGuard(config=VolumeGuardConfig())
    bot_manager.set_volume_guard(volume_guard)

    # Shared market data pool (one API call per timeframe, not per bot)
    from src.exchange.data_pool import get_data_pool

    data_pool = get_data_pool()
    bot_manager.set_data_pool(data_pool)

    # Shared subsystems
    # NOTE: constructed for their side effects; the returned handles are not
    # wired into MainWindow here (they were unused bindings — flagged for
    # review in case this is incomplete wiring rather than dead setup).
    RiskManager(bot_manager)
    AnalyticsEngine()
    get_notification_manager()

    # --- Create main window directly (no launcher) ----------------------
    crypto_window = MainWindow(
        bot_manager=bot_manager,
        settings_manager=settings,
    )
    # Add exchange tabs from settings
    for exch in settings.list_exchanges():
        crypto_window.add_exchange_tab(
            exch.get("exchange_id", "unknown"),
            exch.get("display_name", "Unknown"),
        )
    # v3.24.20 — bind BEFORE the conditional. This is only assigned
    # inside the has_saved_state() branch below, but it is read
    # unconditionally at the auto-start hand-off further down. On any
    # machine with no saved state — a fresh install, or after the
    # operator deletes every bot, or when load_state() hits a parse
    # error — that read raised UnboundLocalError and killed startup
    # before app.exec(). The visible symptom was the splash appearing
    # and the app vanishing, with the traceback going to a crash log
    # nobody thinks to open.
    _autostart_bot_count = 0
    # Restore bots from saved state
    if state_mgr.has_saved_state():
        saved = state_mgr.load_state()
        bot_count = len(saved.get("bots", {}))
        if bot_count > 0:
            log_manager.info(f"Restoring {bot_count} bots from saved state...")
            restored = bot_manager.restore_bots_from_state(saved)
            if restored:
                crypto_window._status_log.log(
                    f"Restored {len(restored)} bot(s) from previous session", "info"
                )
        # v3.15.68 — Bot Swarm state preservation: rehydrate Smart Wires
        # AFTER bots so register-by-id lookups succeed. Operator directive
        # 2026-04-26: "Bot swarm state is not being preserved."
        try:
            wire_count = bot_manager.restore_smart_wires_from_state(saved)
            if wire_count:
                crypto_window._status_log.log(
                    f"Restored {wire_count} Smart Wire(s) from previous " f"session",
                    "info",
                )
        except Exception as _wexc:
            log_manager.warning(f"Smart Wire restore raised: {_wexc}")

        # v3.16.12 — auto-restart ALL restored bots with a progress dialog.
        # v3.16.11 had THREE problems compounding:
        #   1. Async loop wasn't ready (created ~250 lines below)
        #   2. Splash screen has WindowStaysOnTopHint and covered any
        #      dialog opened during this window
        #   3. `_was_running` filter excluded bots saved as STOPPED
        #      (the normal graceful-exit case)
        #
        # New flow: count eligible bots NOW, capture for later. The
        # actual dialog + start_all() trigger fires from a QTimer
        # singleShot scheduled AFTER the splash fades AND the async
        # loop is alive. See line ~820 below.
        _autostart_bot_count = len(
            [
                b
                for b in bot_manager._bots.values()
                if b.state.value in ("idle", "stopped")
            ]
        )
        if _autostart_bot_count > 0:
            log_manager.info(
                f"Will auto-start {_autostart_bot_count} bot(s) "
                f"after splash screen completes..."
            )

    # --- Issue #96 — SINGLE-INSTANCE GUARD --------------------------------
    #
    # A second copy of Acervator on one Coinbase account is the hazard
    # this evaluation exists to stop. Both copies read the same wallet,
    # both act on it, and each reads the other's fills as unexplained
    # drift — the Target Delta condition of #65, made continuous.
    #
    # PLACEMENT. Here, and not earlier, because the verdict has to carry
    # the bot count into the dialog: "start 37 bots" is the sentence the
    # operator judges, and the count is only known after the restore
    # above. Here, and not later, because `_trigger_auto_restart` must
    # already hold the answer when the splash hands over.
    #
    # THIS CALL WRITES NOTHING except on the permitted path. A refusal
    # leaves the previous owner's record exactly as it was, so a second
    # look reaches the same verdict and nothing is lost by refusing.
    #
    # THE DIRECTORY COMES FROM THE STATE MANAGER, never from a second
    # `Path.home()` derivation. The guard must claim the directory the
    # fleet was actually loaded from.
    from src.core.instance_guard import InstanceGuard

    instance_guard = InstanceGuard(state_mgr.config_dir, app_version=current_version)
    instance_decision = instance_guard.evaluate(_autostart_bot_count)
    if instance_decision.permits_auto_start:
        # The ordinary path: this machine resuming its own fleet after a
        # crash, a reboot or a clean exit. Refresh the record and say
        # nothing — a prompt here would be the regression that matters.
        instance_guard.take_ownership()
    else:
        log_manager.warning(
            f"Instance guard: auto-start WITHHELD ({instance_decision.verdict}). "
            f"{instance_decision.detail}"
        )

    # --- Animated splash screen (frameless top-level window) ----------------
    from PySide6.QtWidgets import QWidget as _QW
    from PySide6.QtGui import QFont, QColor, QPainter, QLinearGradient
    from PySide6.QtCore import Qt, QRectF

    class SplashScreen(_QW):
        """Frameless splash with phased fade-in, glow, and fade-out."""

        def __init__(self, target_window):
            super().__init__(None)
            self.setWindowFlags(
                Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SplashScreen
            )
            self.setAttribute(Qt.WA_DeleteOnClose)
            self.setAttribute(Qt.WA_TranslucentBackground, False)
            self._target = target_window
            self._t = 0.0
            self._phase = "fadein"
            # v3.16.18 — operator-reported frame stutter when the
            # splash fade-out and the auto-start sequence run
            # concurrently. Splash close now triggers a strict-after
            # callback (set by main()) so auto-start can be deferred
            # until after the splash painter is fully done. Avoids
            # the previous QTimer.singleShot(9000, ...) race where
            # both timers were active in the last 0.5s.
            self._on_finished_callback = None

            from PySide6.QtWidgets import QApplication

            screen = QApplication.primaryScreen()
            if screen:
                self.setGeometry(screen.geometry())
            else:
                geo = target_window.frameGeometry()
                self.setGeometry(geo)

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._tick)
            self._timer.start(25)

        def _tick(self):
            self._t += 0.025
            if self._phase == "fadein" and self._t >= 2.0:
                self._phase = "glow"
            elif self._phase == "glow" and self._t >= 6.0:
                self._phase = "fadeout"
            elif self._phase == "fadeout" and self._t >= 8.5:
                self._timer.stop()
                self.close()
                # v3.16.18 — strict-after auto-start hand-off.
                # Once the splash is fully closed, schedule the
                # caller-supplied callback (the auto-restart
                # trigger) on the GUI event loop with a small
                # grace gap so any frame finalization Qt is still
                # doing for the splash has time to complete before
                # we add load to the event loop. Operator-flagged
                # stutter root cause was the previous fixed 9s
                # singleShot racing with the splash fade — under
                # frame-rate pressure that singleShot could fire
                # while the splash painter was mid-frame, causing
                # visible jank.
                cb = self._on_finished_callback
                if cb is not None:
                    QTimer.singleShot(750, cb)
                return
            self.update()

        def _ease(self, t, start, end, duration):
            x = max(0, min(1, (self._t - start) / duration))
            return x * x * (3 - 2 * x)

        def paintEvent(
            self, _event
        ):  # v3.23.88: Qt-required signature; body doesn't use event
            import math
            from src import __version__
            from PySide6.QtGui import QPen

            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            t = self._t

            if t < 1.0:
                master = t
            elif t > 6.0:
                master = max(0, 1.0 - (t - 6.0) / 2.5)
            else:
                master = 1.0
            a = int(master * 255)

            p.setPen(Qt.NoPen)
            bg = QLinearGradient(0, 0, w * 0.3, h)
            bg.setColorAt(0.0, QColor(8, 8, 18, a))
            bg.setColorAt(0.3, QColor(6, 6, 14, a))
            bg.setColorAt(0.7, QColor(8, 8, 20, a))
            bg.setColorAt(1.0, QColor(6, 6, 14, a))
            p.fillRect(0, 0, w, h, bg)

            if a > 30:
                p.setPen(QColor(255, 255, 255, min(8, a // 20)))
                for y in range(0, h, 3):
                    p.drawLine(0, y, w, y)

            cx, cy = w / 2, h / 2

            logo_a = int(min(1, max(0, (t - 0.2) / 1.0)) * a)
            title_a = int(min(1, max(0, (t - 0.8) / 0.7)) * a)
            sub_a = int(min(1, max(0, (t - 1.2) / 0.6)) * a)
            cred_a = int(min(1, max(0, (t - 1.5) / 0.8)) * a)

            logo_y = cy - 110
            spin = t * 15
            pulse = 1.0 + 0.05 * math.sin(t * 2.5)

            if logo_a > 10:
                glow_r = int(60 * pulse)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0, 255, 238, logo_a // 8))
                p.drawEllipse(
                    QRectF(cx - glow_r, logo_y - glow_r, glow_r * 2, glow_r * 2)
                )

            pen = QPen(QColor(0, 255, 238, logo_a))
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            r = 45 * pulse
            p.drawEllipse(QRectF(cx - r, logo_y - r, r * 2, r * 2))

            pen.setColor(QColor(0, 170, 255, int(logo_a * 0.6)))
            pen.setWidthF(1.5)
            p.setPen(pen)
            ri = 28 * pulse
            p.drawEllipse(QRectF(cx - ri, logo_y - ri, ri * 2, ri * 2))

            pen.setColor(QColor(0, 255, 136, int(logo_a * 0.5)))
            pen.setWidthF(1.2)
            p.setPen(pen)
            for rot_angle in [30 + spin, -30 - spin * 0.7]:
                p.save()
                p.translate(cx, logo_y)
                p.rotate(rot_angle)
                p.drawEllipse(QRectF(-52, -17, 104, 34))
                p.restore()

            p.setPen(QColor(0, 255, 238, logo_a))
            p.setFont(QFont("Helvetica", 26, QFont.Bold))
            p.drawText(QRectF(cx - 20, logo_y - 16, 40, 32), Qt.AlignCenter, "A")

            p.setPen(Qt.NoPen)
            for i, base_angle in enumerate([60, 200, 320]):
                ea = base_angle + spin * (1.2 if i % 2 == 0 else -0.8)
                ex = cx + 45 * pulse * math.cos(math.radians(ea))
                ey = logo_y + 45 * pulse * math.sin(math.radians(ea))
                p.setBrush(QColor(0, 255, 136, logo_a))
                p.drawEllipse(QRectF(ex - 3, ey - 3, 6, 6))
                for trail in range(1, 4):
                    ta = ea - trail * 8
                    tx = cx + 45 * pulse * math.cos(math.radians(ta))
                    ty = logo_y + 45 * pulse * math.sin(math.radians(ta))
                    p.setBrush(QColor(0, 255, 136, max(0, logo_a // (trail * 3))))
                    p.drawEllipse(QRectF(tx - 1.5, ty - 1.5, 3, 3))

            glow_i = int(60 + 30 * math.sin(t * 2.0))
            p.setPen(QColor(0, 255, 210, min(title_a, glow_i + 140)))
            p.setFont(QFont("Segoe UI", 32, QFont.Bold))
            p.drawText(QRectF(0, cy - 25, w, 45), Qt.AlignCenter, "ACERVATOR")

            line_w = min(200, int(200 * min(1, max(0, (t - 1.0) / 0.5))))
            if line_w > 5:
                pen2 = QPen(QColor(0, 255, 238, sub_a))
                pen2.setWidthF(1.5)
                p.setPen(pen2)
                p.drawLine(
                    int(cx - line_w / 2),
                    int(cy + 22),
                    int(cx + line_w / 2),
                    int(cy + 22),
                )

            p.setPen(QColor(140, 155, 210, sub_a))
            p.setFont(QFont("Segoe UI", 12))
            p.drawText(
                QRectF(0, cy + 30, w, 22),
                Qt.AlignCenter,
                "An Accumulation Trading Platform",
            )

            p.setPen(QColor(90, 150, 255, sub_a))
            p.setFont(QFont("Consolas", 9))
            p.drawText(QRectF(0, cy + 55, w, 16), Qt.AlignCenter, f"v{__version__}")

            p.setPen(QColor(140, 140, 170, cred_a))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(
                QRectF(0, cy + 90, w, 16),
                Qt.AlignCenter,
                "Designed, prompted, and engineered by",
            )
            p.setPen(QColor(255, 200, 80, cred_a))
            p.setFont(QFont("Segoe UI", 13, QFont.Bold))
            p.drawText(
                QRectF(0, cy + 108, w, 24), Qt.AlignCenter, "Ekthelius the Accumulator"
            )
            p.setPen(QColor(180, 170, 140, int(cred_a * 0.7)))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(
                QRectF(0, cy + 132, w, 16), Qt.AlignCenter, "a.k.a. Anthony L. Brown"
            )

            p.setPen(QColor(140, 140, 170, cred_a))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(
                QRectF(0, cy + 160, w, 16),
                Qt.AlignCenter,
                "Built, simulated, tested, and verified by",
            )
            p.setPen(QColor(120, 160, 255, cred_a))
            p.setFont(QFont("Segoe UI", 12, QFont.Bold))
            p.drawText(
                QRectF(0, cy + 178, w, 20), Qt.AlignCenter, "Claude of Anthropic"
            )

            if t > 3.0:
                hint_a = int(min(1, (t - 3.0) / 0.5) * 80)
                p.setPen(QColor(80, 80, 110, hint_a))
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(
                    QRectF(0, h - 30, w, 16),
                    Qt.AlignCenter,
                    "click anywhere to continue",
                )

            p.end()

        def mousePressEvent(
            self, _event
        ):  # v3.23.88: Qt-required signature; body doesn't use event
            self._t = 6.0
            self._phase = "fadeout"

    crypto_window.showMaximized()
    crypto_window.raise_()

    # Launch splash positioned over the main window
    _splash = SplashScreen(crypto_window)
    _splash.show()

    # --- Async integration (run asyncio alongside Qt) ------------------
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    crypto_window.set_async_loop(loop)
    # v3.16.19 — wire the persistent loop into BotManager so
    # bootstrap_exchange_state runs on the SAME loop bot.tick()
    # uses, instead of spawning a throwaway loop in a daemon
    # thread. The throwaway pattern was poisoning v3.16.17's
    # data_pool ticker-coalescing locks (operator-reported
    # 2026-05-01 RuntimeError on BONK after creating a 15th bot).
    try:
        bot_manager.set_async_loop(loop)
    except (
        Exception
    ) as _bm_loop_exc:  # R28-OK: defensive — bot_manager may pre-date set_async_loop in older builds
        log_manager.warning(
            f"BotManager.set_async_loop wiring failed: "
            f"{_bm_loop_exc}. Falling back to legacy throwaway-loop "
            f"bootstrap pattern (cross-loop Lock risk)."
        )

    # v3.24.xx — bulk ticker refresher (operator item 1, 2026-08-06:
    # "the Ammo read out is not updating often enough").
    #
    # A bot's displayed price refreshed at its DECISION cadence because
    # stats.current_price is written after the read-rate gate: measured
    # at 60s or slower for 18 of 35 bots, worst 300s, against a 2s
    # dashboard repaint. This warms the SHARED ticker cache from one
    # bulk call per exchange, so bots take the fast path in
    # get_or_fetch_ticker instead of each issuing their own request.
    # It REPLACES per-bot traffic rather than adding to it — projected
    # 10,272 fetches/hour to ~720 at the 5s default — and leaves every
    # bot's decision cadence untouched.
    #
    # Must run after set_async_loop: the refresher needs that loop.
    #
    # 5.0s matches the pool's own ticker TTL (TickerEntry.is_stale), so
    # the cache is rewarmed exactly as it expires — refreshing faster
    # would spend calls on entries that are still fresh to every reader.
    TICKER_REFRESH_SECONDS = 5.0
    try:
        if bot_manager.start_ticker_refresher(TICKER_REFRESH_SECONDS):
            log_manager.info(
                f"Bulk ticker refresher started "
                f"(every {TICKER_REFRESH_SECONDS:.1f}s)."
            )
    except (
        Exception
    ) as _tr_exc:  # R28-OK: display-freshness optimisation must never block startup
        log_manager.warning(
            f"Bulk ticker refresher not started: {_tr_exc}. Bots keep "
            f"their individual fetch path; Ammo refreshes at each bot's "
            f"read-rate cadence."
        )

    # MEM-216 — install exception handler on the loop. Unhandled
    # exceptions in scheduled coroutines (e.g., bot.start() raising
    # before hitting its guard, or Future-based callbacks failing)
    # were previously logged by asyncio's default handler to stderr,
    # which Windows GUI apps discard. Persist to crash log instead.
    _install_asyncio_handler(loop)

    async_timer = _make_async_pump_timer(loop)
    async_timer.start()

    # MEM-217 — heartbeat QTimer. Runs on the main GUI thread; if the
    # main thread is blocked or the app has frozen (e.g., in a sync
    # CCXT call), the heartbeat file stops updating. External watchdog
    # (acervator_watchdog.py) polls this file's mtime.
    _write_heartbeat()
    heartbeat_timer = QTimer()
    heartbeat_timer.timeout.connect(_write_heartbeat)
    heartbeat_timer.start(2000)  # 2 seconds

    # Periodic state save (every 60 seconds)
    def periodic_save():
        bot_manager.save_all_state()

    save_timer = QTimer()
    save_timer.timeout.connect(periodic_save)
    save_timer.start(60000)

    # v3.16.13 — auto-restart trigger using the GUI-thread per-bot
    # start path. v3.16.12's `BotManager.start_all()` called
    # `bot.start()` directly — but the bot was constructed with a
    # `_PlaceholderExchangeForRestore` placeholder during restore. The
    # first tick called `self.exchange.get_ticker(...)` which the
    # placeholder doesn't implement → AttributeError, the bot's
    # consecutive-error counter climbed, and after 5 errors the bot
    # entered cooldown. Real bug, operator-reported v3.16.12.
    #
    # Fix: route through `crypto_window._on_bot_command(bot_id, "start")`
    # for each bot. That's the path the GUI's manual "Start" button uses
    # — it calls `_connect_exchange_for_bot()` FIRST (decrypts API
    # credentials, creates a real CCXTConnector, sync_connect's), then
    # schedules `bot.start()`. This is the proven, working start path.
    #
    # Verify-then-next staggering uses a GUI-thread QTimer.singleShot
    # poll loop instead of `await asyncio.sleep()` since
    # `_on_bot_command` is GUI-thread synchronous code.
    def _trigger_auto_restart():
        try:
            # Issue #96 — the consent gate sits at the TOP of the
            # existing trigger, and that placement is the design.
            #
            # This function is what the splash hands control to. Every
            # auto-start in the product goes through it, so one check
            # here covers the whole silent path and no second mechanism
            # is needed. It is also the only moment at which a modal
            # dialog is safe: the splash carries WindowStaysOnTopHint
            # and covers anything opened before it fades.
            #
            # An operator who says no leaves every bot IDLE. He can
            # still start any bot by hand, which is an explicit act and
            # therefore already the consent this issue asks for.
            from src.core.instance_guard import (
                AUTHORISED_ALREADY_OWNER,
                authorise_auto_start,
            )
            from src.gui.instance_consent_dialog import ask_for_consent

            _authorised, _why = authorise_auto_start(
                instance_guard,
                instance_decision,
                lambda d: ask_for_consent(d, parent=crypto_window),
            )
            if not _authorised:
                log_manager.warning(
                    f"Auto-start WITHHELD ({_why}, verdict "
                    f"{instance_decision.verdict}). "
                    f"{_autostart_bot_count} bot(s) stay IDLE."
                )
                crypto_window._status_log.log(
                    f"Auto-start withheld: {instance_decision.headline} "
                    f"Bots remain idle; start them from the Start All "
                    f"button when this machine should own the fleet.",
                    "warning",
                )
                return
            if _why != AUTHORISED_ALREADY_OWNER:
                log_manager.warning(
                    f"Instance guard: ownership granted to this machine "
                    f"({instance_decision.identity.label}) by {_why}. "
                    f"Auto-start proceeds."
                )
            eligible = [
                b
                for b in bot_manager._bots.values()
                if b.state.value in ("idle", "stopped")
            ]
            if not eligible:
                log_manager.info("Auto-restart: no eligible bots, skipping.")
                return
            log_manager.info(
                f"Auto-restart firing for {len(eligible)} bot(s) "
                f"(verify-then-next staggered, GUI-thread)..."
            )
            from src.gui.start_all_progress_dialog import StartAllProgressDialog

            dlg = StartAllProgressDialog(bot_manager, parent=crypto_window)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

            total = len(eligible)
            bot_manager._start_all_cancel = False
            bot_manager._bus.emit(
                "bot_manager.start_all_progress", phase="begin", total=total, started=0
            )

            VERIFY_TIMEOUT_S = 8.0
            POLL_INTERVAL_MS = 250
            # v3.16.18 — operator-observed CCXTQueueFullError on
            # multi-bot startup (P0e). Previous MIN_GAP_MS=500 gave
            # ~1.5s typical inter-start cadence, which the operator
            # flagged as too compressed. Operator's follow-up
            # observation: only the SOL bot saw the error on a
            # subsequent run — so the saturation is mild, not
            # swarm-wide. Doubled (not tripled) to 2000ms so typical
            # cadence is ~2.5s — operator's "double" guidance, leaving
            # the "triple" headroom queued in the docket if SOL-style
            # incidents recur on additional symbols. Combined with
            # v3.16.17 ticker coalescing, this should be sufficient
            # for the observed 1-bot-of-N outage pattern.
            MIN_GAP_MS = 2000

            def _start_one(idx: int) -> None:
                if idx >= total:
                    bot_manager._bus.emit(
                        "bot_manager.start_all_progress",
                        phase="done",
                        total=total,
                        started=total,
                    )
                    return
                if getattr(bot_manager, "_start_all_cancel", False):
                    bot_manager._bus.emit(
                        "bot_manager.start_all_progress",
                        phase="cancelled",
                        total=total,
                        started=idx,
                    )
                    return
                bot = eligible[idx]
                bot_manager._bus.emit(
                    "bot_manager.start_all_progress",
                    phase="bot_starting",
                    total=total,
                    started=idx,
                    bot_id=bot.bot_id,
                )
                # Use the GUI's full-start flow (decrypts creds,
                # connects exchange, then schedules bot.start()).
                try:
                    crypto_window._on_bot_command(bot.bot_id, "start")
                except Exception as _start_exc:
                    log_manager.warning(
                        f"Auto-start of bot {bot.bot_id} via "
                        f"_on_bot_command raised: {_start_exc}"
                    )

                import time as _t

                _start_at = _t.monotonic()

                def _verify_or_next() -> None:
                    elapsed = _t.monotonic() - _start_at
                    if getattr(bot_manager, "_start_all_cancel", False):
                        bot_manager._bus.emit(
                            "bot_manager.start_all_progress",
                            phase="cancelled",
                            total=total,
                            started=idx,
                        )
                        return
                    if bot.state.value == "running":
                        bot_manager._bus.emit(
                            "bot_manager.start_all_progress",
                            phase="bot_started",
                            total=total,
                            started=idx + 1,
                            bot_id=bot.bot_id,
                        )
                        QTimer.singleShot(MIN_GAP_MS, lambda: _start_one(idx + 1))
                    elif elapsed >= VERIFY_TIMEOUT_S:
                        bot_manager._bus.emit(
                            "bot_manager.start_all_progress",
                            phase="bot_timeout",
                            total=total,
                            started=idx + 1,
                            bot_id=bot.bot_id,
                            timeout_seconds=VERIFY_TIMEOUT_S,
                        )
                        QTimer.singleShot(MIN_GAP_MS, lambda: _start_one(idx + 1))
                    else:
                        QTimer.singleShot(POLL_INTERVAL_MS, _verify_or_next)

                # Initial poll after a small delay so the GUI's start
                # path has time to schedule the start coroutine.
                QTimer.singleShot(POLL_INTERVAL_MS, _verify_or_next)

            _start_one(0)
        except Exception as exc:
            log_manager.warning(
                f"Auto-restart trigger raised: {exc}. "
                f"Bots remain in IDLE; operator can start manually via "
                f"Start All button."
            )

    if _autostart_bot_count > 0:
        # v3.16.18 — splash-strict auto-start hand-off (operator
        # 2026-05-01: "let's have the auto start sequence begin
        # AFTER the logo screen fades out. The simultaneous bot
        # auto start and the screen fade is causing frame stutter
        # and lag.")
        #
        # Previously a fixed `QTimer.singleShot(9000, ...)` could
        # race with the splash's own 25ms paint timer in the last
        # ~500ms of fade-out. Under frame-rate pressure the auto-
        # start trigger fired while the splash painter was mid-
        # frame, causing visible jank. The splash now exposes
        # `_on_finished_callback`; when fade-out completes and
        # the splash closes, it schedules the callback with a
        # 750ms grace gap (set inside SplashScreen._tick). Total
        # delay from app start is ~9.25s — a touch longer than
        # before, but STRICTLY after the splash painter is done.
        try:
            _splash._on_finished_callback = _trigger_auto_restart
        except (
            Exception
        ):  # R28-OK: splash may have been torn down early; fall back to fixed timer
            QTimer.singleShot(9500, _trigger_auto_restart)

    log_manager.info("Application ready — main window displayed")
    result = app.exec()

    # --- Cleanup: save state and stop all bots -------------------------
    log_manager.info("Saving state before shutdown...")
    bot_manager.save_all_state()
    # Issue #96 — drop the exclusive handle so the next launch on this
    # machine finds it free. A crash skips this line, and that is
    # correct: the operating system drops every handle a dead process
    # held, so a crashed fleet still resumes with no prompt.
    try:
        instance_guard.release()
    except Exception as _lock_exc:  # noqa: BLE001 - shutdown must not fail here
        log_manager.warning(f"Instance handle release raised: {_lock_exc}")
    # v3.18.2 — Paper trader shutdown removed (tab itself deleted per
    # operator directive 2026-05-19).
    loop.run_until_complete(bot_manager.stop_all())
    # v3.23.59 — cancel any still-pending tasks (chart fetches,
    # scout refreshes, per-bot ticks) and drain them cleanly so
    # loop.close() below doesn't emit "Task was destroyed but
    # pending" warnings. Best-effort; never blocks shutdown longer
    # than a few seconds.
    try:
        _pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
        if _pending:
            log_manager.info(
                "Cancelling %d still-pending asyncio tasks before " "loop.close()",
                len(_pending),
            )
            for _t in _pending:
                _t.cancel()
            loop.run_until_complete(asyncio.gather(*_pending, return_exceptions=True))
    except Exception as _cancel_exc:  # noqa: BLE001 - shutdown best-effort
        log_manager.warning("pending-task drain at shutdown raised: %s", _cancel_exc)
    loop.close()
    log_manager.info("Application shutdown complete")

    return result


if __name__ == "__main__":
    # ---------------------------------------------------------------------
    # MEM-219 (Session 24) — Self-supervising entry dispatch
    # ---------------------------------------------------------------------
    # Operator wanted the watchdog to launch automatically from the
    # built Acervator.exe, not as a separate command. Rather than ship
    # a second exe, we make the single binary supervise itself:
    #
    #   User runs Acervator.exe
    #     → watchdog mode: spawn Acervator.exe --child, monitor it
    #     → on child crash: write post-mortem bundle
    #
    #   Acervator.exe --child
    #     → run the actual app (main())
    #
    # Detection of mode:
    #   - `--child` or ACERVATOR_CHILD=1 env → child mode (run app)
    #   - `--no-watchdog` → bypass watchdog even in frozen build
    #   - Otherwise, if frozen (PyInstaller .exe): watchdog mode
    #   - Otherwise (dev, `python main.py`): default to app (no watchdog)
    #     unless --watchdog is passed
    #
    # The watchdog code lives in acervator_watchdog.py. We import
    # lazily only when in watchdog mode so the child process doesn't
    # pay the cost.
    _is_child = ("--child" in sys.argv) or (os.environ.get("ACERVATOR_CHILD") == "1")
    _no_watchdog = "--no-watchdog" in sys.argv
    _force_watchdog = "--watchdog" in sys.argv
    _is_frozen = getattr(sys, "frozen", False)

    if _is_child:
        # Child mode — strip the marker flag and run the app normally.
        if "--child" in sys.argv:
            sys.argv.remove("--child")
        sys.exit(main())
    elif _no_watchdog:
        # Explicit opt-out — run app directly, old behaviour.
        sys.exit(main())
    elif _force_watchdog or _is_frozen:
        # Watchdog mode — spawn self as child, supervise from outside.
        try:
            import acervator_watchdog as _wd

            sys.exit(_wd.run_self_watchdog(frozen=_is_frozen))
        except Exception as _exc:
            # If the watchdog itself cannot start (e.g., bundled spec
            # missed acervator_watchdog.py), fall back to running the
            # app directly so the operator is never blocked.
            sys.stderr.write(
                f"MEM-219: watchdog failed ({_exc}); " f"running app directly.\n"
            )
            sys.exit(main())
    else:
        # Dev default — run app directly. Pass --watchdog to supervise.
        sys.exit(main())
