"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.

Acervator entry point: loads settings, starts core services, shows the crypto
MainWindow and runs the Qt event loop.
"""

from __future__ import annotations

# ruff: noqa: SLF001

from typing import Optional, TYPE_CHECKING

# Drops every __pycache__ under the repo root on import.
import os, shutil

for _root, _dirs, _ in os.walk(os.path.dirname(os.path.abspath(__file__))):
    for _d in _dirs:
        if _d == "__pycache__":
            shutil.rmtree(os.path.join(_root, _d), ignore_errors=True)

# Imported for the QTimer annotation only; PySide6 is imported lazily at run time.
if TYPE_CHECKING:
    from PySide6.QtCore import QTimer


def _early_debug(msg: str, *args: object) -> None:
    """Write msg to stderr when ACERVATOR_DEBUG_BOOT=1, before logging exists; never raises."""
    try:
        import os as _o
        import sys as _s

        if _o.environ.get("ACERVATOR_DEBUG_BOOT") != "1":
            return
        _s.stderr.write("[boot] " + (msg % args if args else msg) + "\n")
    except Exception:  # noqa: BLE001,S110
        pass  # noqa: S110


# Overrides ~/.acervator_logs for the crash log, faulthandler log and stale marker.
CRASH_LOG_ROOT_ENV = "ACERVATOR_CRASH_LOG_ROOT"


def _check_stale_dist_binary() -> None:
    """Write STALE_DIST_WARNING.txt when dist holds bundles and none carries the source version, and delete it when one does."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        live_init = os.path.join(here, "src", "__init__.py")
        dist_root = os.path.join(here, "dist")
        if not os.path.isfile(live_init):
            return

        def _read_version(p):
            """Return the quoted ``__version__`` literal in the file at p, or None."""
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        s = line.strip()
                        if not s.startswith("__version__"):
                            continue
                        _, _, raw = s.partition("=")
                        raw = raw.strip()
                        quote = raw[:1]
                        if quote in ('"', "'") and raw[1:].endswith(quote):
                            return raw[1:-1]
            except Exception as _ver_exc:  # noqa: BLE001
                _early_debug("stale-binary version parse skipped %s: %s", p, _ver_exc)
            return None

        def _live_version():
            """Resolve the source tree's version, or None when it cannot be."""
            try:
                from src._version import UNKNOWN_VERSION, resolve_version

                resolved = resolve_version(here)
            except Exception as _live_exc:  # noqa: BLE001
                _early_debug("stale-binary live version skipped: %s", _live_exc)
                return None
            return None if resolved == UNKNOWN_VERSION else resolved

        def _bundle_version(internal):
            """Read a bundle's baked version, falling back to its literal."""
            try:
                from src._version import read_baked_version

                baked = read_baked_version(internal)
            except Exception as _baked_exc:  # noqa: BLE001
                _early_debug("stale-binary baked version skipped: %s", _baked_exc)
                baked = ""
            return baked or _read_version(os.path.join(internal, "src", "__init__.py"))

        def _dist_bundles():
            """Return each bundle directory name under dist and the version it holds."""
            try:
                names = sorted(os.listdir(dist_root))
            except OSError as _ls_exc:
                _early_debug("stale-binary dist listing skipped: %s", _ls_exc)
                return []
            found = []
            for name in names:
                internal = os.path.join(dist_root, name, "_internal")
                if not os.path.isdir(os.path.join(internal, "src")):
                    continue
                found.append((name, _bundle_version(internal)))
            return found

        def _marker_path():
            from pathlib import Path as _P

            _override = os.environ.get(CRASH_LOG_ROOT_ENV)
            marker_dir = _P(_override) if _override else _P.home() / ".acervator_logs"
            return marker_dir / "STALE_DIST_WARNING.txt"

        def _report_clear_failure(path, exc):
            """Write a stderr notice naming the stale marker file that could not be removed."""
            try:
                stream = getattr(sys, "stderr", None)
                if stream is None:
                    return
                stream.write(
                    "ACERVATOR: the stale-binary marker could not be "
                    f"removed: {path or '<unresolved>'} ({exc}). A bundle "
                    "in dist now carries the source version, so that file "
                    "names versions that are no longer current. Delete "
                    "it by hand.\n"
                )
                stream.flush()
            except (OSError, ValueError, AttributeError) as _rep_exc:
                _early_debug("stale-binary clear notice failed: %s", _rep_exc)

        live_ver = _live_version()
        dated = [(name, ver) for name, ver in _dist_bundles() if ver]
        if not live_ver or not dated:
            return
        if not any(ver == live_ver for _name, ver in dated):
            listing = "".join(f"    dist/{n}  (built from {v})\n" for n, v in dated)
            msg = (
                "\n"
                "============================================================\n"
                "  ACERVATOR STALE BINARY WARNING\n"
                "============================================================\n"
                f"  Live source version : {live_ver}\n"
                "\n"
                "  No bundle in dist was built from this source. Launching\n"
                "  any of the bundles below runs OLD code with bugs that\n"
                "  have since been fixed:\n"
                "\n"
                f"{listing}"
                "\n"
                "  ACTION: run `python main.py` from this source tree, or\n"
                "  rebuild with BUILD.py before launching a bundle.\n"
                "============================================================\n"
            )
            sys.stderr.write(msg)
            sys.stderr.flush()
            try:
                marker_path = _marker_path()
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                with open(marker_path, "w", encoding="utf-8") as f:
                    f.write(msg)
            except Exception as _mk_exc:  # noqa: BLE001
                _early_debug("stale-binary marker write failed: %s", _mk_exc)
        else:
            marker_path = None
            try:
                marker_path = _marker_path()
                if marker_path.is_file():
                    marker_path.unlink()
            except (OSError, ValueError, RuntimeError) as _rm_exc:
                _early_debug("stale-binary marker clear failed: %s", _rm_exc)
                _report_clear_failure(marker_path, _rm_exc)
    except Exception as _guard_exc:  # noqa: BLE001
        _early_debug("stale-binary guard suppressed exception: %s", _guard_exc)


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
    """Enable faulthandler into a per-run log and return its open handle and path."""
    _override = os.environ.get(CRASH_LOG_ROOT_ENV)
    log_dir = Path(_override) if _override else Path.home() / ".acervator_logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_dir = Path.cwd()
    fh_path = log_dir / f"faulthandler_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    try:
        fh_file = open(
            fh_path, "a", buffering=1
        )  # noqa: SIM115 - open for the process lifetime
        fh_file.write(
            f"=== faulthandler started {datetime.now().isoformat()} "
            f"pid={os.getpid()} py={sys.version.split()[0]} "
            f"platform={sys.platform} ===\n"
        )
        fh_file.flush()
        faulthandler.enable(file=fh_file, all_threads=True)
        # faulthandler.register needs signal.SIGUSR1, which exists on Unix only.
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
if sys.platform == "win32":
    asyncio.set_event_loop(asyncio.SelectorEventLoop())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s — %(message)s",
)
logger = logging.getLogger("acervator")

# ccxt and urllib3 log every API call at DEBUG with full response headers.
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
    """Return the per-run crash log path, resolved once and cached in _CRASH_LOG_PATH."""
    global _CRASH_LOG_PATH
    if _CRASH_LOG_PATH is not None:
        return _CRASH_LOG_PATH
    _override = os.environ.get(CRASH_LOG_ROOT_ENV)
    log_dir = Path(_override) if _override else Path.home() / ".acervator_logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception as _mk_exc:  # noqa: BLE001
        logger.debug("crash log dir mkdir fell back to cwd: %s", _mk_exc)
        log_dir = Path.cwd()
    _CRASH_LOG_PATH = log_dir / f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    return _CRASH_LOG_PATH


def _crash_log(category: str, message: str) -> None:
    """Append one timestamped line to the crash log and flush; never raises."""
    try:
        ts = datetime.now().isoformat(timespec="milliseconds")
        line = f"[{ts}] [{category}] [thread={threading.current_thread().name}] {message}\n"
        with open(_get_crash_log_path(), "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception as _crash_exc:  # noqa: BLE001
        logger.debug("crash log write suppressed exception: %s", _crash_exc)


def _install_diagnostic_hooks() -> None:
    """Install sys and threading excepthooks that write the crash log before the original sys hook."""

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
    """Route unhandled exceptions on loop to the crash log and logger.error."""

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
    """Send every Qt message to the crash log, and criticals and fatals to logger.error."""
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


_install_diagnostic_hooks()


def _heartbeat_path() -> Path:
    log_dir = Path.home() / ".acervator_logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_dir = Path.cwd()
    return log_dir / "heartbeat.txt"


def _write_heartbeat():
    """Write the current timestamp and pid to heartbeat.txt; never raises."""
    try:
        with open(_heartbeat_path(), "w", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()} pid={os.getpid()}\n")
    except Exception as _hb_exc:  # noqa: BLE001
        logger.debug("heartbeat write suppressed exception: %s", _hb_exc)


# Must equal src.core.tick_driver.PUMP_INTERVAL_MS.
ASYNC_PUMP_INTERVAL_MS = 50


def _make_async_pump_timer(
    loop: asyncio.AbstractEventLoop, interval_ms: int = ASYNC_PUMP_INTERVAL_MS
) -> QTimer:
    """Return a PreciseTimer QTimer calling tick_driver.pump_once(loop) every interval_ms."""
    from PySide6.QtCore import Qt, QTimer

    from src.core.tick_driver import pump_once

    def pump_async():
        pump_once(loop)

    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.setInterval(interval_ms)
    timer.timeout.connect(pump_async)
    return timer


def build_instance_guard(state_mgr, app_version: str):
    """Return an InstanceGuard pointed at ``state_mgr.config_dir``.

    The fleet and the guard read one directory, so no caller derives a
    second location of its own.
    """
    from src.core.instance_guard import InstanceGuard

    return InstanceGuard(state_mgr.config_dir, app_version=app_version)


def autostart_gate(guard, decision, ask_consent, on_withheld, on_granted) -> bool:
    """Answer whether the fleet may auto-start, and never start it here.

    ``on_withheld`` takes the refusal reason and ``on_granted`` the grant
    reason; a False answer means no bot may be started.
    """
    from src.core.instance_guard import AUTHORISED_ALREADY_OWNER, authorise_auto_start

    authorised, why = authorise_auto_start(guard, decision, ask_consent)
    if not authorised:
        on_withheld(why)
        return False
    if why != AUTHORISED_ALREADY_OWNER:
        on_granted(why)
    return True


def drain_pending_tasks(loop: asyncio.AbstractEventLoop) -> int:
    """Cancel every unfinished task on ``loop`` and await it, returning the count.

    Called before ``loop.close()`` so no task is destroyed while pending.
    """
    pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
    if not pending:
        return 0
    for task in pending:
        task.cancel()
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    return len(pending)


BRIDGE_FLAG = "--bridge"


def bridge_requested(argv) -> bool:
    """Answer whether ``argv`` carries ``BRIDGE_FLAG``."""
    return BRIDGE_FLAG in list(argv or [])


def build_live_system(bot_manager, settings_manager=None):
    """Return the ``LiveSystem`` the bridge surfaces read this process through."""
    from src.core.desktop_bridge import LiveSystem

    return LiveSystem(bot_manager=bot_manager, settings_manager=settings_manager)


def wire_history_publisher(live, window):
    """Publish the History tab's trades into ``live`` on every refresh.

    Returns the connected slot, or None when ``window`` has no
    ``_history_tab`` carrying ``history_refreshed``.
    """
    tab = getattr(window, "_history_tab", None)
    signal = getattr(tab, "history_refreshed", None)
    if signal is None:
        return None

    def publish_history(trades) -> None:
        live.publish(
            "history",
            trades=list(trades or []),
            last_fetched_ts=float(getattr(tab, "_last_fetched_ts", 0.0) or 0.0),
        )

    signal.connect(publish_history)
    return publish_history


def start_bridge(live):
    """Serve the desktop bridge on this process's own stdin and stdout.

    ``sys.stdout`` is rebound to ``sys.stderr`` before the first request is
    read. ``serve_and_push`` returns the thread answering requests and gives
    ``live`` the channel that writes each later ``publish`` down the same pipe.
    """
    from src.core.desktop_bridge import build_registry, serve_and_push

    channel = sys.stdout.buffer
    sys.stdout = sys.stderr
    return serve_and_push(sys.stdin.buffer, channel, build_registry(live), live)


def main() -> int:
    """Build the Qt application, show the window, run the event loop and return its exit code."""

    # _ACERVATOR_TEST_EXIT_IMMEDIATELY=1 returns 0 before any GUI is built.
    import os as _os

    if _os.environ.get("_ACERVATOR_TEST_EXIT_IMMEDIATELY") == "1":
        sys.stderr.write("MEM-219 test hook: main() entered, exiting 0\n")
        return 0

    from src import __version__ as _acervator_version

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
    except Exception as _st_exc:  # noqa: BLE001
        logger.warning(
            "Stone Tablets registry init failed at boot: %s "
            "(sim replay will need to fetch on demand)",
            _st_exc,
        )

    from src.core.settings import SettingsManager
    from src.core.logging_engine import LogManager
    from src.core.encryption import (
        KeyringManager,
    )
    from src.core.event_bus import get_event_bus
    from src.trading.bot_container import BotManager

    settings = SettingsManager()
    log_manager = LogManager()
    KeyringManager()  # constructed for its side effect
    bus = get_event_bus()
    bot_manager = BotManager()

    # Trade fills reach trade.log only through this wiring.
    log_manager.attach_to_bus(bus)

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
        except Exception as _res_exc:  # noqa: BLE001
            logger.debug("symbol resolver skipped bot_id %r: %s", bot_id, _res_exc)
        return ""

    if hasattr(log_manager, "set_symbol_resolver"):
        log_manager.set_symbol_resolver(_resolve_bot_symbol)

    log_manager.info(f"Acervator v{_acervator_version} starting")

    try:
        from src.core.signal_contract import install_process_sink

        _sig_sink = install_process_sink()
        if _sig_sink is not None:
            log_manager.info(f"Signal collection active -> {_sig_sink.path}")
    except Exception as _sig_exc:  # noqa: BLE001
        log_manager.warning(f"Signal collection unavailable: {_sig_exc}")

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

    _install_qt_message_handler()

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
    # A parentless timer needs a module-level reference to stay alive.
    globals()["_persistent_gc_timer"] = _gc_timer

    from src.gui.theme_engine import (
        DEFAULT_THEME_NAME,
        THEME_ACCENT,
        ThemeManager,
        stored_accent,
        stored_theme,
    )

    theme_mgr = ThemeManager()
    stored_name = settings.get("theme", DEFAULT_THEME_NAME)
    theme_name = stored_theme(stored_name)
    if theme_name != stored_name:
        log_manager.warning(
            f"Stored theme {stored_name!r} is not a known theme; "
            f"painting {theme_name}"
        )
    stored_hex = settings.get("accent_color", THEME_ACCENT)
    accent = stored_accent(stored_hex)
    if not accent and str(stored_hex).strip():
        log_manager.warning(
            f"Stored accent colour {stored_hex!r} is not a hex colour; "
            f"painting the {theme_name} accent"
        )
    theme_mgr.apply_theme(theme_name, app, accent)

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

    from src.gui.main_window import MainWindow
    from src.core.state_manager import StateManager
    from src.trading.risk_manager import RiskManager
    from src.trading.analytics_engine import AnalyticsEngine
    from src.core.notifications import get_notification_manager

    state_mgr = StateManager()
    bot_manager.set_state_manager(state_mgr)

    # Before restore, so a restored bot votes with the stored weights.
    from src.trading.ta_engine import weights_from_settings

    bot_manager.set_ta_weights(
        weights_from_settings(settings.get("ta_indicator_weights", {}))
    )

    # Before the first fill: get_sound_engine holds SoundConfig defaults until
    # something pushes the stored group.
    from src.core.sound_engine import get_sound_engine, sound_config_from_settings

    get_sound_engine().update_config(
        sound_config_from_settings(settings.get("sound", {}))
    )

    _preflight = state_mgr.preflight_snapshot()
    if _preflight:
        log_manager.info(
            f"Preflight: {len(_preflight)} state file(s) copied aside "
            f"before restore"
        )
    _damaged = state_mgr.diff_primary_vs_backup()
    if _damaged:
        log_manager.warning(
            f"Preflight: {len(_damaged)} bot(s) exist in the backup but "
            f"NOT in the primary state file: {', '.join(_damaged[:5])}"
        )

    from src.trading.volume_guard import VolumeGuard, VolumeGuardConfig

    volume_guard = VolumeGuard(config=VolumeGuardConfig())
    bot_manager.set_volume_guard(volume_guard)

    from src.exchange.data_pool import get_data_pool

    data_pool = get_data_pool()
    bot_manager.set_data_pool(data_pool)

    # Constructed for their side effects.
    RiskManager(bot_manager)
    AnalyticsEngine()
    get_notification_manager()

    crypto_window = MainWindow(
        bot_manager=bot_manager,
        settings_manager=settings,
    )
    from src.gui.main_tabs.trading_tab_surface import exchange_display_name

    for exch in settings.list_exchanges():
        exchange_id = exch.get("exchange_id", "")
        if not exchange_id:
            continue
        crypto_window.add_exchange_tab(exchange_id, exchange_display_name(exch))

    live_system = build_live_system(bot_manager, settings)
    if wire_history_publisher(live_system, crypto_window) is None:
        log_manager.warning(
            "History tab exposed no history_refreshed signal; the desktop "
            "bridge serves this process's bots and no live trades."
        )
    if bridge_requested(sys.argv):
        try:
            start_bridge(live_system)
            log_manager.info(
                "Desktop bridge serving on this process's stdin and stdout."
            )
        except Exception as _bridge_exc:  # noqa: BLE001
            log_manager.warning(
                f"Desktop bridge not started: {_bridge_exc}. The GUI runs "
                f"unchanged and the shell reaches no backend."
            )
    # Read unconditionally below; assigned only inside the restore branch.
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
        try:
            wire_count = bot_manager.restore_smart_wires_from_state(saved)
            if wire_count:
                crypto_window._status_log.log(
                    f"Restored {wire_count} Smart Wire(s) from previous " f"session",
                    "info",
                )
        except Exception as _wexc:
            log_manager.warning(f"Smart Wire restore raised: {_wexc}")

        # The start runs from the splash callback below, not here.
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

    instance_guard = build_instance_guard(state_mgr, current_version)
    instance_decision = instance_guard.evaluate(_autostart_bot_count)
    if instance_decision.permits_auto_start:
        instance_guard.take_ownership()
    else:
        log_manager.warning(
            f"Instance guard: auto-start WITHHELD ({instance_decision.verdict}). "
            f"{instance_decision.detail}"
        )

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
            # Set by main(); called 750 ms after the splash closes.
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

    _splash = SplashScreen(crypto_window)
    _splash.show()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    crypto_window.set_async_loop(loop)
    try:
        bot_manager.set_async_loop(loop)
    except Exception as _bm_loop_exc:
        log_manager.warning(
            f"BotManager.set_async_loop wiring failed: "
            f"{_bm_loop_exc}. Falling back to legacy throwaway-loop "
            f"bootstrap pattern (cross-loop Lock risk)."
        )

    TICKER_REFRESH_SECONDS = 5.0
    try:
        if bot_manager.start_ticker_refresher(TICKER_REFRESH_SECONDS):
            log_manager.info(
                f"Bulk ticker refresher started "
                f"(every {TICKER_REFRESH_SECONDS:.1f}s)."
            )
    except Exception as _tr_exc:
        log_manager.warning(
            f"Bulk ticker refresher not started: {_tr_exc}. Bots keep "
            f"their individual fetch path; Ammo refreshes at each bot's "
            f"read-rate cadence."
        )

    _install_asyncio_handler(loop)

    async_timer = _make_async_pump_timer(loop)
    async_timer.start()

    # acervator_watchdog.py polls this file's mtime.
    _write_heartbeat()
    heartbeat_timer = QTimer()
    heartbeat_timer.timeout.connect(_write_heartbeat)
    heartbeat_timer.start(2000)

    def periodic_save():
        bot_manager.save_all_state()

    save_timer = QTimer()
    save_timer.timeout.connect(periodic_save)
    save_timer.start(60000)

    def _trigger_auto_restart():
        try:
            from src.gui.instance_consent_dialog import ask_for_consent

            def _log_withheld(why: str) -> None:
                log_manager.warning(
                    f"Auto-start WITHHELD ({why}, verdict "
                    f"{instance_decision.verdict}). "
                    f"{_autostart_bot_count} bot(s) stay IDLE."
                )
                crypto_window._status_log.log(
                    f"Auto-start withheld: {instance_decision.headline} "
                    f"Bots remain idle; start them from the Start All "
                    f"button when this machine should own the fleet.",
                    "warning",
                )

            def _log_granted(why: str) -> None:
                log_manager.warning(
                    f"Instance guard: ownership granted to this machine "
                    f"({instance_decision.identity.label}) by {why}. "
                    f"Auto-start proceeds."
                )

            if not autostart_gate(
                instance_guard,
                instance_decision,
                lambda d: ask_for_consent(d, parent=crypto_window),
                _log_withheld,
                _log_granted,
            ):
                return
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
            from src.gui.variant_surface import START_ALL_PROGRESS, surface_class

            dlg = surface_class(START_ALL_PROGRESS)(bot_manager, parent=crypto_window)
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

                QTimer.singleShot(POLL_INTERVAL_MS, _verify_or_next)

            _start_one(0)
        except Exception as exc:
            log_manager.warning(
                f"Auto-restart trigger raised: {exc}. "
                f"Bots remain in IDLE; operator can start manually via "
                f"Start All button."
            )

    if _autostart_bot_count > 0:
        # The splash schedules this on close; the timer is the fallback.
        try:
            _splash._on_finished_callback = _trigger_auto_restart
        except Exception:
            QTimer.singleShot(9500, _trigger_auto_restart)

    log_manager.info("Application ready — main window displayed")
    result = app.exec()

    log_manager.info("Saving state before shutdown...")
    bot_manager.save_all_state()
    try:
        instance_guard.release()
    except Exception as _lock_exc:  # noqa: BLE001
        log_manager.warning(f"Instance handle release raised: {_lock_exc}")
    loop.run_until_complete(bot_manager.stop_all())
    try:
        _drained = drain_pending_tasks(loop)
        if _drained:
            log_manager.info(
                "Cancelled %d still-pending asyncio tasks before loop.close()",
                _drained,
            )
    except Exception as _cancel_exc:  # noqa: BLE001
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
            sys.stderr.write(
                f"MEM-219: watchdog failed ({_exc}); " f"running app directly.\n"
            )
            sys.exit(main())
    else:
        sys.exit(main())
