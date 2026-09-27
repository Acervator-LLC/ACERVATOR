"""The logo library, one folder per asset class and sector, filled ahead of any bot.

``library_targets`` names every asset the recorded venues list and every asset
the maps hold, each carrying the folder ``library_folder`` files it under.
``fill_library`` walks those targets through ``asset_logo`` and answers a
``FillReport`` naming every asset that resolved nothing. A kept file or an
``unresolved.json`` entry is skipped, so a stopped fill resumes where it stopped,
and ``lock_is_held`` refuses the whole fill while the application is running.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

from ..core.asset_logos import (
    LOGO_CACHE_DIR,
    LogoBudgetSpent,
    LogoCache,
    kept_folder,
)
from ..core.instance_guard import lock_is_held
from ..core.io_utils import atomic_write_json
from ..exchange.market_rules_store import load_document, store_path
from .ata_asset_maps import CLASS_CRYPTO, MAPS, asset_logo, listing_of
from .ata_spm import YAHOO_PACE_S, YAHOO_RATE_LIMIT_WAIT_S, ReadPace
from .topology_proposals import load_sector_map

logger = logging.getLogger("acervator.logo_library")

#: The library root, the same directory ``LogoCache`` keeps a logo in.
LIBRARY_DIR = LOGO_CACHE_DIR

#: The file under ``LIBRARY_DIR`` naming every asset a fill resolved nothing for.
UNRESOLVED_NAME = "unresolved.json"
UNRESOLVED_VERSION = 1
UNRESOLVED_VERSION_KEY = "version"
UNRESOLVED_ASSETS_KEY = "assets"
UNRESOLVED_REASON_KEY = "reason"
UNRESOLVED_CLASS_KEY = "asset_class"
UNRESOLVED_SECTOR_KEY = "sector"

#: The one ``ReadPace`` key every logo address is paced under. A logo comes from
#: an organisation's own site or a coin data source, never from a venue, so one
#: clock covers the whole walk.
LOGO_HOST = "logo"

#: The least gap the fill keeps between two reads, and the hold it keeps after a
#: 429 naming no Retry-After. Both are the figures ``ata_spm`` already uses for a
#: host that publishes no limit.
LOGO_PACE_S = YAHOO_PACE_S
LOGO_HOLD_S = YAHOO_RATE_LIMIT_WAIT_S

#: The reads one fill takes when the caller names no figure.
DEFAULT_READ_LIMIT = 40

#: Where a target came from: a venue's own recorded market list, or the maps.
VENUE_SOURCE = "venue"
MAP_SOURCE = "map"

#: Why ``fill_library`` read nothing: the application holds the instance lock.
TRADING_REFUSAL = (
    "the application is running and holds the instance lock; close it first"
)

#: The digits a venue puts in front of a perpetual's base to name its multiplier.
MULTIPLIER_DIGITS = "0123456789"

#: What one asset with no resolved mark is recorded as when the walk named nothing.
NO_REASON_TEXT = "no logo address answered an image for {symbol}"

FILL_REFUSED_LOG = "logo library: fill refused, %s"
FILL_DONE_LOG = "logo library: %d target(s), %d skipped, %d read, %d kept, %d failed"
UNRESOLVED_READ_LOG = "logo library: %s will not parse: %s"

#: What ``FillReport.line`` reads.
REPORT_FORMAT = (
    "{targets} target(s), {skipped} already held, {read} read, {kept} kept, "
    "{failed} failed, {remaining} left, at {pace_s} s a read"
)
STOPPED_TEXT = " (stopped)"


def runtime_dir() -> Path:
    """``store_path``'s own directory, which holds the instance lock, resolved on every call."""
    return store_path().parent


def library_folder(asset_class: Any, sector: Any = "") -> str:
    """``asset_class`` over ``sector`` as a ``kept_folder`` path, the class alone for an untagged asset."""
    return kept_folder(f"{asset_class}/{sector}")


@dataclass(frozen=True)
class LogoTarget:
    """One asset a fill resolves, placed by ``library_folder`` under its class and sector."""

    symbol: str
    asset_class: str = ""
    sector: str = ""
    source: str = MAP_SOURCE

    @property
    def folder(self) -> str:
        """The path under ``LIBRARY_DIR`` this asset's kept file sits in."""
        return library_folder(self.asset_class, self.sector)


def underlying_base(base: Any, known: Iterable[str]) -> str:
    """``base`` without its leading ``MULTIPLIER_DIGITS`` when the rest names a ``known`` asset.

    A base whose remainder no source lists keeps every character, so
    ``MULTIPLIER_DIGITS`` never shortens a name that stands on its own.
    """
    asked = str(base).strip().upper()
    stripped = asked.lstrip(MULTIPLIER_DIGITS)
    if stripped and stripped != asked and stripped in set(known):
        return stripped
    return asked


def venue_bases(document: Optional[dict] = None) -> tuple[str, ...]:
    """Every base asset the recorded venues list, sorted, each folded by ``underlying_base``."""
    held = document if document is not None else load_document()
    raw: set[str] = set()
    for markets in held.values():
        if not isinstance(markets, dict):
            continue
        for symbol in markets:
            base = str(symbol).split("/")[0].split(":")[0].strip().upper()
            if base:
                raw.add(base)
    return tuple(sorted({underlying_base(one, raw) for one in raw}))


def map_placements() -> dict[str, tuple[str, str]]:
    """Every symbol ``MAPS`` holds, each answering the asset class and sector holding it."""
    placed: dict[str, tuple[str, str]] = {}
    for asset_class, sectors in MAPS.items():
        for sector, rows in sectors.items():
            for row in rows:
                placed.setdefault(row.symbol.strip().upper(), (asset_class, sector))
    return placed


def placement(
    symbol: Any,
    placed: Optional[dict] = None,
    tags: Optional[dict] = None,
) -> tuple[str, str]:
    """One asset's class and sector: ``map_placements`` first, then ``listing_of``, then the sector tags."""
    asked = str(symbol).strip().upper()
    held = placed if placed is not None else map_placements()
    if asked in held:
        return held[asked]
    found = listing_of(asked)
    if found is not None and found.asset_class:
        return str(found.asset_class), str(found.sector)
    marks = tags if tags is not None else load_sector_map()
    return CLASS_CRYPTO, str(marks.get(asked, "")).strip().lower()


def library_targets(document: Optional[dict] = None) -> tuple[LogoTarget, ...]:
    """Every asset the library covers, one ``LogoTarget`` per asset, ``MAPS`` and the venues merged.

    An asset both sources name answers one ``LogoTarget``, carrying the
    ``map_placements`` class and sector.
    """
    placed = map_placements()
    tags = load_sector_map()
    rows: dict[str, LogoTarget] = {}
    for symbol, (asset_class, sector) in sorted(placed.items()):
        rows[symbol] = LogoTarget(
            symbol=symbol,
            asset_class=asset_class,
            sector=sector,
            source=MAP_SOURCE,
        )
    for base in venue_bases(document):
        if base in rows:
            continue
        asset_class, sector = placement(base, placed, tags)
        rows[base] = LogoTarget(
            symbol=base,
            asset_class=asset_class,
            sector=sector,
            source=VENUE_SOURCE,
        )
    return tuple(rows[name] for name in sorted(rows))


def unresolved_path(library_dir: Optional[Path] = None) -> Path:
    """``UNRESOLVED_NAME`` under ``library_dir``, defaulting to ``LIBRARY_DIR``."""
    return (Path(library_dir) if library_dir else LIBRARY_DIR) / UNRESOLVED_NAME


def read_unresolved(library_dir: Optional[Path] = None) -> dict[str, dict]:
    """Every asset a past fill resolved nothing for, keyed on the symbol, empty for none."""
    path = unresolved_path(library_dir)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning(UNRESOLVED_READ_LOG, path, exc)
        return {}
    assets = raw.get(UNRESOLVED_ASSETS_KEY) if isinstance(raw, dict) else None
    if not isinstance(assets, dict):
        return {}
    return {
        str(name).strip().upper(): row
        for name, row in assets.items()
        if isinstance(row, dict)
    }


def write_unresolved(held: dict, library_dir: Optional[Path] = None) -> Path:
    """Write ``held`` to ``unresolved_path`` through ``atomic_write_json``, making the directory first."""
    path = unresolved_path(library_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(
        path,
        {
            UNRESOLVED_VERSION_KEY: UNRESOLVED_VERSION,
            UNRESOLVED_ASSETS_KEY: {name: held[name] for name in sorted(held)},
        },
        indent=2,
    )
    return path


@dataclass(frozen=True)
class FillReport:
    """What one ``fill_library`` walk did, with every unresolved asset named in ``failures``."""

    targets: int = 0
    skipped: int = 0
    read: int = 0
    kept: int = 0
    failed: int = 0
    stopped: bool = False
    refused: str = ""
    pace_s: float = LOGO_PACE_S
    slept_s: float = 0.0
    failures: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def remaining(self) -> int:
        """The ``targets`` this walk neither skipped, kept nor counted in ``failed``."""
        return max(self.targets - self.skipped - self.kept - self.failed, 0)

    @property
    def line(self) -> str:
        """``REPORT_FORMAT`` filled from this report, with ``STOPPED_TEXT`` on a stopped walk."""
        text = REPORT_FORMAT.format(
            targets=self.targets,
            skipped=self.skipped,
            read=self.read,
            kept=self.kept,
            failed=self.failed,
            remaining=self.remaining,
            pace_s=self.pace_s,
        )
        return text + (STOPPED_TEXT if self.stopped else "")


def fill_library(
    targets: Optional[Iterable[LogoTarget]] = None,
    library_dir: Optional[Path] = None,
    read_limit: int = DEFAULT_READ_LIMIT,
    config_dir: Optional[Path] = None,
    should_stop: Optional[Callable[[], bool]] = None,
    cache: Optional[LogoCache] = None,
    pace: Optional[Any] = None,
) -> FillReport:
    """Resolve each target's mark into its own folder, ``read_limit`` reads at most, and report.

    The walk refuses while ``lock_is_held``, skips every asset ``kept_path`` or
    ``read_unresolved`` already answers, and records each failure by name.
    """
    library = Path(library_dir) if library_dir else LIBRARY_DIR
    directory = Path(config_dir) if config_dir else runtime_dir()
    if lock_is_held(directory):
        logger.warning(FILL_REFUSED_LOG, TRADING_REFUSAL)
        return FillReport(refused=TRADING_REFUSAL, pace_s=LOGO_PACE_S)

    rows = tuple(targets) if targets is not None else library_targets()
    held = read_unresolved(library)
    store = cache if cache is not None else LogoCache(library, read_budget=read_limit)
    clock = (
        pace
        if pace is not None
        else ReadPace({LOGO_HOST: LOGO_PACE_S}, {LOGO_HOST: LOGO_HOLD_S})
    )

    skipped = 0
    kept = 0
    failures: list[tuple[str, str]] = []
    slept = 0.0
    stopped = False
    for row in rows:
        if store.kept_path(row.symbol) is not None or row.symbol in held:
            skipped += 1
            continue
        if store.reads_left == 0 or (should_stop is not None and should_stop()):
            stopped = True
            break
        slept += clock.wait(LOGO_HOST)
        try:
            answer = asset_logo(
                row.symbol, row.asset_class, cache=store, folder=row.folder
            )
        except LogoBudgetSpent:
            stopped = True
            clock.take(LOGO_HOST)
            break
        clock.take(LOGO_HOST)
        if answer.has_logo:
            kept += 1
            continue
        reason = answer.reason or NO_REASON_TEXT.format(symbol=row.symbol)
        failures.append((row.symbol, reason))
        held[row.symbol] = {
            UNRESOLVED_REASON_KEY: reason,
            UNRESOLVED_CLASS_KEY: row.asset_class,
            UNRESOLVED_SECTOR_KEY: row.sector,
        }

    if failures:
        write_unresolved(held, library)
    logger.info(FILL_DONE_LOG, len(rows), skipped, store.reads, kept, len(failures))
    return FillReport(
        targets=len(rows),
        skipped=skipped,
        read=store.reads,
        kept=kept,
        failed=len(failures),
        stopped=stopped,
        pace_s=LOGO_PACE_S,
        slept_s=slept,
        failures=tuple(failures),
    )


#: What ``main`` prints before it reads anything, and for each unresolved asset.
COVER_FORMAT = "{count} target(s) the library covers, {held} already unresolved"
FOLDERS_HEAD = "folders the targets fall under:"
FOLDER_FORMAT = "  {folder}: {count}"
FAILURE_FORMAT = "  {symbol}: {reason}"
REFUSED_FORMAT = "refused: {reason}"
MAIN_LOG_FORMAT = "%(asctime)s %(message)s"


def _parser() -> argparse.ArgumentParser:
    """The arguments ``main`` reads: the read budget, the library, the runtime directory."""
    parser = argparse.ArgumentParser(description="Fill the logo library.")
    parser.add_argument("--reads", type=int, default=DEFAULT_READ_LIMIT)
    parser.add_argument("--library", type=Path, default=None)
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument("--list", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Fill the library, or list what ``library_targets`` covers, answering 1 on a refusal."""
    args = _parser().parse_args(argv)
    rows = library_targets()
    held = read_unresolved(args.library)
    print(COVER_FORMAT.format(count=len(rows), held=len(held)))
    if args.list:
        counts: dict[str, int] = {}
        for one in rows:
            counts[one.folder] = counts.get(one.folder, 0) + 1
        print(FOLDERS_HEAD)
        for folder in sorted(counts):
            print(FOLDER_FORMAT.format(folder=folder, count=counts[folder]))
        return 0
    report = fill_library(
        targets=rows,
        library_dir=args.library,
        read_limit=args.reads,
        config_dir=args.config_dir,
    )
    if report.refused:
        print(REFUSED_FORMAT.format(reason=report.refused), file=sys.stderr)
        return 1
    print(report.line)
    for symbol, reason in report.failures:
        print(FAILURE_FORMAT.format(symbol=symbol, reason=reason))
    return 0


if __name__ == "__main__":  # pragma: no cover - console entry
    logging.basicConfig(level=logging.INFO, format=MAIN_LOG_FORMAT)
    sys.exit(main())


__all__ = [
    "DEFAULT_READ_LIMIT",
    "LIBRARY_DIR",
    "LOGO_HOST",
    "LOGO_PACE_S",
    "MAP_SOURCE",
    "TRADING_REFUSAL",
    "UNRESOLVED_NAME",
    "VENUE_SOURCE",
    "FillReport",
    "LogoTarget",
    "fill_library",
    "library_folder",
    "library_targets",
    "main",
    "map_placements",
    "placement",
    "read_unresolved",
    "runtime_dir",
    "underlying_base",
    "unresolved_path",
    "venue_bases",
    "write_unresolved",
]
