"""src/core/log_paths.py — Single-source-of-truth for log bucket roots.

Centralizes all log paths under ``~/.acervator_logs/`` per operator
directive 2026-06-09:

    "I would like a much cleaner, organized, centralized, and labeled
    log set for the platform. Keep everything under the user/ directory
    but rebuild the logs in a manner that all critical data is getting
    recorded and stored."

Three top-level buckets matching operator's stated concerns:

  * ``activity/``   PLATFORM FAULTS (subsystem activity NDJSON, 14d rotation)
  * ``console/``    CODE FAULTS    (stdout/stderr/tracebacks, existing autoprune)
  * ``trade/``      TRADE + TRADE LOGIC (parity-critical, persistent retention)

Status v3.23.0: SCAFFOLD-ONLY. Writers + handlers wired; runtime
verification (V1-V6 in DOCKET) pending. Sim does NOT consume these
paths until Phase C (boundary lockdown) ships in v3.23.x+.

Why centralize:
  The pre-v3.23.0 codebase used four different log roots:
    1. ``~/.acervator_logs/`` (console, crash, faulthandler, postmortem)
    2. ``~/.acervator/logs/``  (system.log + pnl/ — LogManager dev mode)
    3. ``<exe_dir>/logs/real_market/`` (system.log + trade.log + pnl/
       — LogManager frozen mode; where the live trade.log actually lived)
    4. ``~/.acervator/`` (operational state — NOT logs)

  The frozen-vs-source split hid the live trade.log in different places
  on dev vs production builds, complicating forensics. This module
  collapses (2) and (3) into a single canonical path under (1) so the
  log location is the same regardless of build mode.

The functions below each CREATE the bucket dir if missing
(``mkdir(parents=True, exist_ok=True)``) so callers can use them
unconditionally without separate "ensure exists" steps.
"""

from pathlib import Path

# Single canonical root — all log buckets live under here.
_LOG_ROOT = Path.home() / ".acervator_logs"


def get_log_root() -> Path:
    """Return the single canonical log root: ``~/.acervator_logs/``.

    All disk-writing log machinery resolves paths through this function
    rather than computing their own location. Replaces the dual-resolution
    in ``LogManager.__init__`` (frozen-vs-source split) that hid trade.log
    in different places on dev vs production builds.
    """
    _LOG_ROOT.mkdir(parents=True, exist_ok=True)
    return _LOG_ROOT


def get_activity_dir() -> Path:
    """``activity/`` bucket — platform faults (subsystem-level NDJSON).

    Reserved for the Step 5 ``log_activity()`` writer queued in v3.23.2+
    (after V1-V6 verify-loop closes). Dir created up front so the layout
    is observable from the operator's file browser the moment v3.23.0
    runs.
    """
    p = _LOG_ROOT / "activity"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_api_dir() -> Path:
    """``api/`` bucket — exchange + REST call NDJSON (subset of platform faults).

    Reserved for the Step 5 ``log_api()`` writer queued in v3.23.2+.
    Dir created up front for the same observability reason as
    ``activity/``.
    """
    p = _LOG_ROOT / "api"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_console_dir() -> Path:
    """``console/`` bucket — stdout/stderr/tracebacks/crash bundles.

    The auto-prune mechanism in ``acervator_watchdog.py::prune_postmortem_bundles``
    keeps this bucket bounded. Existing console-prune logic continues to
    handle this bucket unchanged.
    """
    p = _LOG_ROOT / "console"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_trade_dir() -> Path:
    """``trade/`` bucket — trade events + per-tick gate decisions (PERSISTENT).

    Treated as the long-term parity ground truth. Size-based rotation
    only; no age-prune to ensure long windows remain queryable by the
    sim parity tool and operator-facing dashboards.

    Sub-files written here in v3.23.0:
      * ``trade.log``        — every executed trade (existing pipeline)
      * ``gate.log``         — every gate decision (new in v3.23.0)
      * ``pnl/<day>.ndjson`` — daily PnL snapshots (existing PnLCascade)
    """
    p = _LOG_ROOT / "trade"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_pnl_dir() -> Path:
    """``pnl/`` subdir under ``trade/`` — PnL cascade.

    Sits under ``trade/`` because PnL snapshots are part of the trade
    evidence layer, not a separate concern. The existing PnLCascade
    schema is preserved verbatim.
    """
    p = get_trade_dir() / "pnl"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_exchange_history_dir() -> Path:
    """``exchange_history/`` bucket — YTD CSV auto-download landing zone.

    Reserved for the Step 6 24-hour-refresh CSV downloader queued in
    v3.23.2+. The ``history-tab-ytd-trades.log`` will be populated from
    here once the V1-V6 verify-loop closes.
    """
    p = _LOG_ROOT / "exchange_history"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_meta_dir() -> Path:
    """``_meta/`` bucket — startup markers + index.json discovery file.

    The pre-v3.23.0 markers ( ``~/.acervator_logs/<marker>`` ) move
    into this subdir to keep the top level clean. Existing marker
    consumers are unchanged in v3.23.0; the migration happens
    transparently when the marker is rewritten.
    """
    p = _LOG_ROOT / "_meta"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_reports_dir() -> Path:
    """``reports/`` bucket — machine-readable output of operator-run tools.

    Destination for ``src/core/version_sweep.py``'s JSON and PDF sweep
    reports. Generated output may not land in a tracked tree, so the
    sweep resolves its default through here instead of composing a path
    under the repo root.
    """
    p = _LOG_ROOT / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def layout_map() -> dict[str, Path]:
    """Return a ``{bucket_name -> Path}`` dict for diagnostics + audit tools.

    Every bucket this module exposes, for inventory renderers and for
    future ``index.json`` writers that surface the layout to operator
    dashboards.
    """
    return {
        "root": get_log_root(),
        "activity": get_activity_dir(),
        "api": get_api_dir(),
        "console": get_console_dir(),
        "trade": get_trade_dir(),
        "pnl": get_pnl_dir(),
        "exchange_history": get_exchange_history_dir(),
        "reports": get_reports_dir(),
        "_meta": get_meta_dir(),
    }
