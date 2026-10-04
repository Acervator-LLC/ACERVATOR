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

Status: SCAFFOLD-ONLY. Writers + handlers wired; runtime verification
pending. Sim does NOT consume these paths until the boundary lockdown
ships.

Why centralize:
  Four different log roots existed before this module:
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

    Reserved for a queued activity writer; nothing writes here yet. Dir
    created up front so the layout is observable from the operator's
    file browser the moment the platform runs.
    """
    p = _LOG_ROOT / "activity"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_api_dir() -> Path:
    """``api/`` bucket — exchange + REST call NDJSON (subset of platform faults).

    ``src.exchange.api_logger.APIFailureStore`` writes
    ``api_failures.ndjson`` here. Dir created up front for the same
    observability reason as ``activity/``.
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

    Sub-files written here:
      * ``trade.log``        — every executed trade (existing pipeline)
      * ``gate.log``         — every gate decision
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
    """``exchange_history/`` bucket — the YTD trade files.

    ``src.exchange.ytd_trade_store`` writes one JSON file per exchange,
    symbol and year here, beside its MANIFEST.json and GAPS.json, and
    ``src.exchange.ytd_csv_import`` fills them from a transactions CSV
    export. ``ytd_trade_store.get_ytd_root`` resolves this path and
    accepts the ``ACERVATOR_YTD_TRADES_ROOT`` override.
    """
    p = _LOG_ROOT / "exchange_history"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_meta_dir() -> Path:
    """``_meta/`` bucket — startup markers + index.json discovery file.

    Markers that sat directly under ``~/.acervator_logs/`` move into
    this subdir to keep the top level clean. Existing marker consumers
    are unchanged; the migration happens transparently when the marker
    is rewritten.
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


def get_sim_dir() -> Path:
    """``sim/`` bucket — every file the Simulator writes.

    ``src.simulator.fleet_source.FleetSource`` keeps the sim fleet file
    here; ``~/.acervator/bot_state.json`` is never written from the
    Simulator.
    """
    p = _LOG_ROOT / "sim"
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
        "sim": get_sim_dir(),
        "_meta": get_meta_dir(),
    }
