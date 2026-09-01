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
# The boot script reaches private members on BotManager, the bus and
# the main window at 14 sites.

from typing import Optional, TYPE_CHECKING

# Drops every __pycache__ under the repo root on import.
import os, shutil

for _root, _dirs, _ in os.walk(os.path.dirname(os.path.abspath(__file__))):
    for _d in _dirs:
        if _d == "__pycache__":
            shutil.rmtree(os.path.join(_root, _d), ignore_errors=True)

# PySide6 is imported lazily everywhere else in this file, so a missing
# toolkit reports at the Qt setup block rather than at module load.
if TYPE_CHECKING:
    from PySide6.QtCore import QTimer


def _early_debug(msg: str, *args: object) -> None:
    """Best-effort debug output for code running BEFORE logging exists.

    `logger` is not bound until
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


# The crash-diagnostic log root. Declared above every reader: the
# stale-binary guard, the faulthandler arming and the crash logger.
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

    The marker is cleared when, and only when,
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

        # One resolution of the marker directory, used by both the write
        # and the clear, so a redirect cannot be half-applied.
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
                # mkdir stays on the write path. The clear must not
                # build the tree it deletes from.
                marker_path = _marker_path()
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                with open(marker_path, "w", encoding="utf-8") as f:
                    f.write(msg)
            except Exception as _mk_exc:  # noqa: BLE001 - marker write best-effort
                _early_debug("stale-binary marker write failed: %s", _mk_exc)
        elif live_ver and dist_ver:
            # Cleared only when both versions are readable and equal. An
            # unreadable version means "cannot tell", and clearing on it
            # would drop a true warning.
            marker_path = None
            try:
                marker_path = _marker_path()
                if marker_path.is_file():
                    marker_path.unlink()
            except (OSError, ValueError, RuntimeError) as _rm_exc:
                _early_debug("stale-binary marker clear failed: %s", _rm_exc)
                _report_clear_failure(marker_path, _rm_exc)
    except Exception as _guard_exc:  # noqa: BLE001 - guard must never raise
        _early_debug("stale-binary guard suppressed exception: %s", _guard_exc)


# sys is imported here because the guard below writes to stderr.
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
        # The handle stays open for the process lifetime: it is the
        # destination for fatal-signal dumps.
        fh_file = open(
            fh_path, "a", buffering=1
        )  # noqa: SIM115 - line-buffered lifetime handle
        # Header line, so a dump correlates with the run's crash log.
        fh_file.write(
            f"=== faulthandler started {datetime.now().isoformat()} "
            f"pid={os.getpid()} py={sys.version.split()[0]} "
            f"platform={sys.platform} ===\n"
        )
        fh_file.flush()
        faulthandler.enable(file=fh_file, all_threads=True)
        # faulthandler.register takes signals on Unix only. enable()
        # already covers the fatal signals on Windows.
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
        sys.stderr.write(f"MEM-217: faulthandler setup failed: {exc}\n")
        return None, None


_FH_FILE, _FH_PATH = _setup_faulthandler()


# ProactorEventLoop, the Windows default, is incompatible with aiohttp.
# set_event_loop_policy is deprecated, so the loop is set directly.
if sys.platform == "win32":
    asyncio.set_event_loop(asyncio.SelectorEventLoop())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("acervator")

# ccxt and urllib3 log every API call at DEBUG with full response
# headers: one ten-hour run reached 6.7 GB of console log.
for _noisy in (
    "ccxt",
    "ccxt.base",
    "ccxt.base.exchange",
    "urllib3",
    "urllib3.connectionpool",
    "urllib3.util.retry",
):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


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
        logger.debug("crash log write suppressed exception: %s", _crash_exc)


def _install_diagnostic_hooks() -> None:
    """Install sys, threading, asyncio, and Qt exception handlers.
    Each handler writes to the crash log before delegating to any
    original handler. Idempotent — safe to call more than once."""

    _original_excepthook = sys.excepthook

    def _sys_excepthook(exc_type, exc_value, tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, tb))
        _crash_log("SYS_EXCEPTHOOK", f"{exc_type.__name__}: {exc_value}\n{tb_text}")
        logger.error("UNCAUGHT EXCEPTION: %s: %s", exc_type.__name__, exc_value)
        import contextlib

        with contextlib.suppress(Exception):
            _original_excepthook(exc_type, exc_value, tb)

    sys.excepthook = _sys_excepthook

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


# Installed at module load, so they catch a failure in the rest of this file.
_install_diagnostic_hooks()


# Heartbeat file. acervator_watchdog.py polls its mtime. Written from the
# GUI thread, so a frozen GUI thread stops it.
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


# Every coroutine in this application runs on the Qt GUI thread. This
# timer is the only thing that advances the loop, so its cadence is the
# loop's. Must equal src.core.tick_driver.PUMP_INTERVAL_MS.
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

    # Undocumented test hook: proves main() was entered without building
    # the GUI.
    import os as _os

    if _os.environ.get("_ACERVATOR_TEST_EXIT_IMMEDIATELY") == "1":
        sys.stderr.write("MEM-219 test hook: main() entered, exiting 0\n")
        return 0

    # Imported lazily inside main(): the bootstrap above runs before src/
    # is guaranteed importable at module scope.
    from src import __version__ as _acervator_version

    # --- Dependency check ------------------------------------------
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

    # --- psutil auto-install ---------------------------------------
    # Targets sys.executable, so it cannot land in another interpreter.
    # Nuclear mode keeps an in-app installer as the fallback.
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

    # --- Stone Tablets registry ------------------------------------
    # Reads MANIFEST at boot. Never fetches.
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
    )
    from src.core.event_bus import get_event_bus
    from src.trading.bot_container import BotManager

    settings = SettingsManager()
    log_manager = LogManager()
    KeyringManager()  # constructed for its keyring-backend probe side effect
    bus = get_event_bus()
    bot_manager = BotManager()

    # Trade fills reach logs/real_market/trade.log as NDJSON only through
    # this wiring.
    log_manager.attach_to_bus(bus)

    # Emit sites carry no symbol, so a trade.log entry would have an empty
    # symbol field without this resolver.
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

    # Without a process sink, every emit() outside the Simulator is inert.
    # A sink that cannot open its file returns None and launch continues.
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

    # qFatal kills the process with no stderr on Windows.
    _install_qt_message_handler()

    # CPython's automatic GC can fire on any thread, including a CCXT
    # worker holding C-extension state. Collecting on a GUI-thread timer
    # instead removes the race with a widget painting.
    import gc as _gc

    _gc.disable()
    _gc_timer = QTimer()
    _gc_timer.timeout.connect(lambda: _gc.collect())
    _gc_timer.start(5000)
    log_manager.info(
        "MEM-263: automatic GC disabled; periodic gc.collect() "
        "scheduled on GUI thread (5s cadence). Mitigates CCXT-worker-"
        "thread access violation pattern observed v3.18.1."
    )
    # Module-level reference: the timer has no parent to keep it alive.
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
        settings.set("username", "User")
        settings.set("app_version", current_version)
        username = "User"
        log_manager.info("First run — default user created, no wizard")

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

    # Runs after StateManager exists and before all three writers: the
    # restore read, the 60s rolling save and the shutdown save. The rolling
    # backup is one cycle deep; this copy survives more.
    _preflight = state_mgr.preflight_snapshot()
    if _preflight:
        log_manager.info(
            f"Preflight: {len(_preflight)} state file(s) copied aside "
            f"before restore"
        )
    # The backup lags the primary by one save cycle, so a bot in the backup
    # and not in the primary was pruned by the last save.
    _damaged = state_mgr.diff_primary_vs_backup()
    if _damaged:
        log_manager.warning(
            f"Preflight: {len(_damaged)} bot(s) exist in the backup but "
            f"NOT in the primary state file: {', '.join(_damaged[:5])}"
        )

    from src.trading.volume_guard import VolumeGuard, VolumeGuardConfig

    volume_guard = VolumeGuard(config=VolumeGuardConfig())
    bot_manager.set_volume_guard(volume_guard)

    # One API call per timeframe, not per bot.
    from src.exchange.data_pool import get_data_pool

    data_pool = get_data_pool()
    bot_manager.set_data_pool(data_pool)

    # Constructed for their side effects. The handles are not wired into
    # MainWindow here.
    RiskManager(bot_manager)
    AnalyticsEngine()
    get_notification_manager()

    # --- Create main window directly (no launcher) ----------------------
    crypto_window = MainWindow(
        bot_manager=bot_manager,
        settings_manager=settings,
    )
    for exch in settings.list_exchanges():
        crypto_window.add_exchange_tab(
            exch.get("exchange_id", "unknown"),
            exch.get("display_name", "Unknown"),
        )
    # Bound before the conditional: assigned only inside the branch below,
    # read unconditionally at the auto-start hand-off.
    _autostart_bot_count = 0
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
        # After the bots, so register-by-id lookups find them.
        try:
            wire_count = bot_manager.restore_smart_wires_from_state(saved)
            if wire_count:
                crypto_window._status_log.log(
                    f"Restored {wire_count} Smart Wire(s) from previous " f"session",
                    "info",
                )
        except Exception as _wexc:
            log_manager.warning(f"Smart Wire restore raised: {_wexc}")

        # Counted here. The dialog and the start fire from a timer once the
        # splash has closed and the async loop is alive.
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

    # --- Single-instance guard ---------------------------------------
    # Placed after the restore: the verdict carries the bot count into the
    # dialog. The directory comes from the state manager, never a second
    # Path.home() derivation.
    from src.core.instance_guard import InstanceGuard

    instance_guard = InstanceGuard(state_mgr.config_dir, app_version=current_version)
    instance_decision = instance_guard.evaluate(_autostart_bot_count)
    if instance_decision.permits_auto_start:
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
            # Set by main(). The splash schedules it after its own close,
            # so auto-start never runs while the painter is mid-frame.
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
                # 750ms gap: the last splash frame finishes before the
                # callback adds load to the event loop.
                cb = self._on_finished_callback
                if cb is not None:
                    QTimer.singleShot(750, cb)
                return
            self.update()

        def _ease(self, t, start, end, duration):
            x = max(0, min(1, (self._t - start) / duration))
            return x * x * (3 - 2 * x)

        def paintEvent(self, _event):
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

        def mousePressEvent(self, _event):
            self._t = 6.0
            self._phase = "fadeout"

    crypto_window.showMaximized()
    crypto_window.raise_()

    # Covers the primary screen, falling back to the window's frame.
    _splash = SplashScreen(crypto_window)
    _splash.show()

    # --- Async integration (run asyncio alongside Qt) ------------------
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    crypto_window.set_async_loop(loop)
    # bootstrap_exchange_state must run on the same loop as bot.tick().
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

    # Warms the shared ticker cache from one bulk call per exchange.
    # Measured before this: 18 of 35 bots refreshed their price at 60s or
    # slower, worst 300s, against a 2s dashboard repaint. 5.0s matches the
    # pool's own ticker TTL.
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

    # Windows GUI apps discard stderr, so an unhandled coroutine exception
    # goes to the crash log instead.
    _install_asyncio_handler(loop)

    async_timer = _make_async_pump_timer(loop)
    async_timer.start()

    # Runs on the GUI thread. acervator_watchdog.py polls the file's mtime.
    _write_heartbeat()
    heartbeat_timer = QTimer()
    heartbeat_timer.timeout.connect(_write_heartbeat)
    heartbeat_timer.start(2000)

    def periodic_save():
        bot_manager.save_all_state()

    save_timer = QTimer()
    save_timer.timeout.connect(periodic_save)
    save_timer.start(60000)

    # Routes through the GUI's per-bot start path, which connects the
    # exchange first: a restored bot holds a placeholder exchange until
    # then. Staggering polls on a GUI-thread timer because _on_bot_command
    # is synchronous GUI code.
    def _trigger_auto_restart():
        try:
            # The splash carries WindowStaysOnTopHint and covers anything
            # opened before it fades, so this is the first moment a modal is
            # visible. Every auto-start in the product passes through here.
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
            # 500ms gave a ~1.5s typical inter-start cadence and produced
            # CCXTQueueFullError on one bot. 2000ms gives ~2.5s.
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

                # _on_bot_command schedules the start coroutine rather than
                # running it, so the first poll waits.
                QTimer.singleShot(POLL_INTERVAL_MS, _verify_or_next)

            _start_one(0)
        except Exception as exc:
            log_manager.warning(
                f"Auto-restart trigger raised: {exc}. "
                f"Bots remain in IDLE; operator can start manually via "
                f"Start All button."
            )

    if _autostart_bot_count > 0:
        # The splash schedules this itself once it closes. The fixed timer
        # below is the fallback when the splash is already gone.
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
    # A crash skips this. The operating system drops every handle a dead
    # process held, so a crashed fleet still resumes with no prompt.
    try:
        instance_guard.release()
    except Exception as _lock_exc:  # noqa: BLE001 - shutdown must not fail here
        log_manager.warning(f"Instance handle release raised: {_lock_exc}")
    loop.run_until_complete(bot_manager.stop_all())
    # Drains pending tasks so loop.close() emits no "Task was destroyed
    # but pending" warnings.
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
    _is_child = ("--child" in sys.argv) or (os.environ.get("ACERVATOR_CHILD") == "1")
    _no_watchdog = "--no-watchdog" in sys.argv
    _force_watchdog = "--watchdog" in sys.argv
    _is_frozen = getattr(sys, "frozen", False)

    if _is_child:
        if "--child" in sys.argv:
            sys.argv.remove("--child")
        sys.exit(main())
    elif _no_watchdog:
        sys.exit(main())
    elif _force_watchdog or _is_frozen:
        try:
            import acervator_watchdog as _wd

            sys.exit(_wd.run_self_watchdog(frozen=_is_frozen))
        except Exception as _exc:
            # Run the app directly rather than exiting, so a watchdog that
            # cannot start never blocks the operator.
            sys.stderr.write(
                f"MEM-219: watchdog failed ({_exc}); " f"running app directly.\n"
            )
            sys.exit(main())
    else:
        sys.exit(main())
