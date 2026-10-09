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

import os
from pathlib import Path
from typing import Optional

# Set to a directory and the nine buckets below, plus main.py's four writers, follow it.
LOG_ROOT_ENV = "ACERVATOR_CRASH_LOG_ROOT"


def resolve_log_root() -> Path:
    """Return the log root ``LOG_ROOT_ENV`` names, else ``~/.acervator_logs``.

    An empty ``LOG_ROOT_ENV`` counts as unset, and ``resolve_log_root``
    creates nothing.
    """
    override = os.environ.get(LOG_ROOT_ENV)
    return Path(override) if override else Path.home() / ".acervator_logs"


def get_log_root() -> Path:
    """Return the root ``resolve_log_root`` names, created by ``mkdir`` when missing."""
    root = resolve_log_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_activity_dir() -> Path:
    """``activity/`` bucket — platform faults (subsystem-level NDJSON).

    Reserved for a queued activity writer; nothing writes here yet. Dir
    created up front so the layout is observable from the operator's
    file browser the moment the platform runs.
    """
    p = resolve_log_root() / "activity"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_api_dir() -> Path:
    """``api/`` bucket — exchange + REST call NDJSON (subset of platform faults).

    ``src.exchange.api_logger.APIFailureStore`` writes
    ``api_failures.ndjson`` here. Dir created up front for the same
    observability reason as ``activity/``.
    """
    p = resolve_log_root() / "api"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_console_dir() -> Path:
    """``console/`` bucket — stdout/stderr/tracebacks/crash bundles.

    The auto-prune mechanism in ``acervator_watchdog.py::prune_postmortem_bundles``
    keeps this bucket bounded. Existing console-prune logic continues to
    handle this bucket unchanged.
    """
    p = resolve_log_root() / "console"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_trade_dir() -> Path:
    """``trade/`` bucket — trade events + per-tick gate decisions (PERSISTENT).

    Treated as the long-term parity ground truth. Size-based rotation
    only; no age-prune to ensure long windows remain queryable by the
    sim parity tool and operator-facing dashboards.

    Sub-files written here:
      * ``trade.log``        — every executed trade (existing pipeline)
      * ``gate/<exchange>/<sector>/gate.log`` — every gate decision
      * ``pnl/<day>.ndjson`` — daily PnL snapshots (existing PnLCascade)
    """
    p = resolve_log_root() / "trade"
    p.mkdir(parents=True, exist_ok=True)
    return p


GATE_DIR_NAME = "gate"
"""The ``trade/`` subdir holding one directory per exchange."""

GATE_LOG_NAME = "gate.log"
"""The active gate log inside one exchange-and-sector directory."""

GATE_ARCHIVE_DIR_NAME = "archive"
"""The subdir holding gate records carried over from the pre-split layout.

``NDJSONWriter`` never rotates these files and nothing prunes them, because
they are recorded decisions behind real fills rather than a running stream.
"""

UNNAMED_SEGMENT = "unnamed"
"""The path segment a gate record with no exchange or no sector lands under."""

_SEGMENT_KEEP = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_")

SEGMENT_MAX_CHARS = 64
"""Characters ``path_segment`` keeps, well inside the 255 a directory name takes.

The longest sector name is thirteen characters and the longest venue id is under
twenty, so no name the platform holds reaches this.
"""


def path_segment(value: object) -> str:
    """``value`` as one lowercase directory name, or ``UNNAMED_SEGMENT``.

    Every character outside ``_SEGMENT_KEEP`` becomes an underscore and
    ``SEGMENT_MAX_CHARS`` bounds the length, so a venue id or a sector name
    cannot reach a parent directory, a drive, or a name the filesystem refuses.
    """
    text = str(value or "").strip().lower()
    folded = "".join(one if one in _SEGMENT_KEEP else "_" for one in text)
    return folded.strip("_")[:SEGMENT_MAX_CHARS].strip("_") or UNNAMED_SEGMENT


def gate_root(trade_dir: Optional[Path] = None) -> Path:
    """The ``gate/`` directory under ``trade_dir``, or under ``get_trade_dir()``.

    Creates nothing, so a reader can enumerate a layout no bot has written
    into yet.
    """
    base = Path(trade_dir) if trade_dir is not None else get_trade_dir()
    return base / GATE_DIR_NAME


def gate_log_dir(
    exchange: object,
    asset_class: object,
    trade_dir: Optional[Path] = None,
) -> Path:
    """The directory one exchange-and-sector's gate records live in, created.

    ``LogManager._gate_writer_for`` resolves a writer through this, so every
    bot on one venue trading one sector appends to a single file.
    """
    p = gate_root(trade_dir) / path_segment(exchange) / path_segment(asset_class)
    p.mkdir(parents=True, exist_ok=True)
    return p


def gate_log_path(
    exchange: object,
    asset_class: object,
    trade_dir: Optional[Path] = None,
) -> Path:
    """The active gate log one exchange-and-sector's decisions append to."""
    return gate_log_dir(exchange, asset_class, trade_dir) / GATE_LOG_NAME


def gate_archive_dir(
    exchange: object,
    asset_class: object,
    trade_dir: Optional[Path] = None,
) -> Path:
    """The archive directory of one exchange-and-sector bucket, created."""
    p = gate_log_dir(exchange, asset_class, trade_dir) / GATE_ARCHIVE_DIR_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def legacy_gate_logs(trade_dir: Optional[Path] = None) -> list[Path]:
    """The pre-split ``trade/gate.log`` and its rotations, oldest first.

    ``migrate_legacy_gate_logs`` empties this list on the first run of a
    build carrying the split layout; until then every reader still reads
    these files, so a decision recorded before the split stays readable.
    """
    base = Path(trade_dir) if trade_dir is not None else get_trade_dir()
    active = base / GATE_LOG_NAME
    return _rotations_in(base) + ([active] if active.is_file() else [])


def _rotations_in(where: Path) -> list[Path]:
    """``GATE_LOG_NAME`` rotations in ``where``, the highest number first.

    A name whose suffix is not a number is left out, so an archive member and
    a carry marker are never read as a rotation.
    """
    if not where.is_dir():
        return []
    found = [
        one
        for one in where.iterdir()
        if one.is_file()
        and one.name.startswith(GATE_LOG_NAME + ".")
        and one.suffix.lstrip(".").isdigit()
    ]
    return sorted(found, key=lambda one: int(one.suffix.lstrip(".")), reverse=True)


def _archive_members(archive: Path) -> list[Path]:
    """Every promoted member of one ``GATE_ARCHIVE_DIR_NAME`` directory.

    A name starting with a dot is a carry still in flight and is left out, so
    a reader never sees a decision twice.
    """
    if not archive.is_dir():
        return []
    found = [
        one
        for one in archive.iterdir()
        if one.is_file() and not one.name.startswith(".")
    ]
    return sorted(found, key=lambda one: one.name)


def _bucket_gate_logs(bucket: Path) -> list[Path]:
    """One bucket's archive members, rotations and active file, oldest first."""
    found = _archive_members(bucket / GATE_ARCHIVE_DIR_NAME)
    found.extend(_rotations_in(bucket))
    active = bucket / GATE_LOG_NAME
    if active.is_file():
        found.append(active)
    return found


def gate_log_buckets(trade_dir: Optional[Path] = None) -> list[tuple[str, str, Path]]:
    """Every ``(exchange, sector, directory)`` the gate layout holds, sorted."""
    root = gate_root(trade_dir)
    if not root.is_dir():
        return []
    found: list[tuple[str, str, Path]] = []
    for venue in sorted(one for one in root.iterdir() if one.is_dir()):
        for sector in sorted(one for one in venue.iterdir() if one.is_dir()):
            found.append((venue.name, sector.name, sector))
    return found


def gate_log_files(trade_dir: Optional[Path] = None) -> list[Path]:
    """Every gate log a reader must read to see all recorded decisions.

    The pre-split files come first, then each bucket in sorted order with its
    archive members, rotations and active file oldest first. Nothing is listed
    twice, so a reader joining a fill to its decision finds exactly one row.
    """
    found = legacy_gate_logs(trade_dir)
    for _venue, _sector, bucket in gate_log_buckets(trade_dir):
        found.extend(_bucket_gate_logs(bucket))
    return found


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
    p = resolve_log_root() / "exchange_history"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_meta_dir() -> Path:
    """``_meta/`` bucket — startup markers + index.json discovery file.

    Markers that sat directly under ``~/.acervator_logs/`` move into
    this subdir to keep the top level clean. Existing marker consumers
    are unchanged; the migration happens transparently when the marker
    is rewritten.
    """
    p = resolve_log_root() / "_meta"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_reports_dir() -> Path:
    """``reports/`` bucket — machine-readable output of operator-run tools.

    Destination for ``src/core/version_sweep.py``'s JSON and PDF sweep
    reports. Generated output may not land in a tracked tree, so the
    sweep resolves its default through here instead of composing a path
    under the repo root.
    """
    p = resolve_log_root() / "reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_sim_dir() -> Path:
    """``sim/`` bucket — every file the Simulator writes.

    ``src.simulator.fleet_source.FleetSource`` keeps the sim fleet file
    here; ``~/.acervator/bot_state.json`` is never written from the
    Simulator.
    """
    p = resolve_log_root() / "sim"
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
