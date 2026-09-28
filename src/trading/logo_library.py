"""The logo library, one folder per asset class and sector, filled ahead of any bot.

``library_targets`` names every asset the recorded venues list and every asset
the maps hold, each carrying the folder ``library_folder`` files it under.
``fill_library`` walks those targets through ``asset_logo`` and answers a
``FillReport`` naming every asset that resolved nothing. A kept file or an
``unresolved.json`` entry is skipped, so a stopped fill resumes where it stopped,
and ``lock_is_held`` refuses the whole fill while the application is running.
``build_coin_index`` looks every crypto ticker up through the coin list and the
market records its ids name, and writes one picture address per ticker to
``coin_index_path``, with the site ``coin_site`` reads off that coin's own
record beside it; ``choose_coin`` settles a ticker several coins carry by the
project name ``recorded_name`` answers, then by market rank, and writes down the
candidates of one it cannot settle. ``coin_candidates`` looks a coin id up under
that project name as well as under the ticker, ``--name TICKER=NAME`` supplies one
the records do not hold, and ``_clear_unresolved`` drops a ticker from
``unresolved.json`` once its index row carries an address.
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
    LOGO_READ_ERRORS,
    LOGO_USER_AGENT,
    LogoBudgetSpent,
    LogoCache,
    kept_folder,
)
from ..core.instance_guard import lock_is_held
from ..core.io_utils import atomic_write_json
from ..core.safe_url import SafeRequest, openable_url, safe_urlopen
from ..exchange.crypto_assets import (
    ASSETS,
    COIN_DETAIL_URL,
    COIN_INDEX_ASSETS_KEY,
    COIN_INDEX_CHOSEN_KEY,
    COIN_INDEX_ID_KEY,
    COIN_INDEX_IMAGE_KEY,
    COIN_INDEX_NAME_KEY,
    COIN_INDEX_REASON_KEY,
    COIN_INDEX_SITE_KEY,
    COIN_INDEX_SITE_REASON_KEY,
    COIN_INDEX_VERSION,
    COIN_INDEX_VERSION_KEY,
    COIN_LIST_URL,
    COIN_MARKETS_PAGE,
    COIN_MARKETS_URL,
    COIN_SITE_SCHEMES,
    coin_index_path,
    load_coin_index,
)
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


#: The host every coin lookup is paced under, with the gap it keeps between two
#: reads and the hold a 429 leaves. One read answers up to ``COIN_MARKETS_PAGE``
#: coins, so a whole fleet costs a handful of reads.
COIN_API_HOST = "coin-api"
COIN_API_PACE_S = 8.0
COIN_API_HOLD_S = 70.0
COIN_API_TRIES = 4
COIN_TIMEOUT_S = 30.0

#: How much better the best candidate's market rank must be than the next one's
#: before a ticker several coins carry is settled on rank alone. A ticker the
#: margin cannot settle is written down with its candidates and no address.
COIN_RANK_MARGIN = 10.0

COIN_ID_KEY = "id"
COIN_SYMBOL_KEY = "symbol"
COIN_NAME_KEY = "name"
COIN_RANK_KEY = "market_cap_rank"
COIN_IMAGE_KEY = "image"

COIN_AMBIGUOUS_REASON = (
    "{count} coins carry the ticker {symbol} at comparable market rank, {candidates}"
)
COIN_UNRANKED_REASON = (
    "{count} coins carry the ticker {symbol} and none carries a market rank, "
    "{candidates}"
)
COIN_ABSENT_REASON = "no coin record carries the ticker {symbol}, or its name"
COIN_NO_IMAGE_REASON = "the coin record for {symbol} carries no picture address"

#: The coin record's own links block, and the field inside it naming the
#: project's front door. ``COIN_MARKETS_URL`` carries neither.
COIN_LINKS_KEY = "links"
COIN_HOMEPAGE_KEY = "homepage"

COIN_NO_SITE_REASON = "the coin record for {symbol} names no https web address"
COIN_UNSETTLED_SITE_REASON = "no coin is settled for {symbol}, so no site is looked up"

COIN_SITE_LOG = "logo library: %d site(s) looked up, %d named, %d without one"

COIN_LIST_LOG = "logo library: the coin list names %d coin(s)"
COIN_RECORD_LOG = "logo library: %d coin record(s) read over %d page(s)"
COIN_INDEX_LOG = "logo library: coin index holds %d address(es) and %d refusal(s)"
COIN_CLEARED_LOG = "logo library: %d ticker(s) dropped from unresolved, %d left"
COIN_READ_REFUSED_LOG = "logo library: %s answered nothing: %s"
COIN_RATE_LOG = "logo library: %s refused for rate, holding %.0f s"

#: What ``CoinIndexReport.line`` reads.
COIN_REPORT_FORMAT = (
    "{tickers} ticker(s) looked up, {listed} coin(s) listed, {records} record(s) "
    "read over {reads} read(s), {addressed} address(es) indexed, {refused} unsettled, "
    "{cleared} refusal(s) dropped"
)


def coin_folded(text: Any) -> str:
    """``text`` lowered with every character outside ASCII letters and digits removed."""
    return "".join(one for one in str(text).lower() if one.isascii() and one.isalnum())


def coin_site(record: Any) -> str:
    """The first web address ``record``'s links block names, empty for a record naming none.

    ``openable_url`` decides it, so a homepage outside ``COIN_SITE_SCHEMES``
    answers empty exactly as a refused ``website`` does.
    """
    links = record.get(COIN_LINKS_KEY) if isinstance(record, dict) else None
    named = links.get(COIN_HOMEPAGE_KEY) if isinstance(links, dict) else None
    for one in named if isinstance(named, list) else [named]:
        address, _ = openable_url(
            str(one or "").strip(), allowed_schemes=COIN_SITE_SCHEMES
        )
        if address:
            return address
    return ""


def _coin_read(address: str, clock: Any) -> Optional[Any]:
    """The parsed body one coin address answers, None for one that answers nothing.

    A refusal naming a 429 holds through ``clock`` and is read again, never
    recorded as an absence.
    """
    for attempt in range(COIN_API_TRIES):
        clock.wait(COIN_API_HOST)
        try:
            request = SafeRequest(address)
            request.add_header("User-Agent", LOGO_USER_AGENT)
            with safe_urlopen(request, timeout=COIN_TIMEOUT_S) as response:
                body = response.read()
        except LOGO_READ_ERRORS as exc:
            hold = clock.take(COIN_API_HOST, exc)
            if hold and attempt < COIN_API_TRIES - 1:
                logger.warning(COIN_RATE_LOG, address, hold)
                continue
            logger.warning(COIN_READ_REFUSED_LOG, address, exc)
            return None
        clock.take(COIN_API_HOST)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            logger.warning(COIN_READ_REFUSED_LOG, address, exc)
            return None
    return None


def recorded_name(symbol: Any, kept: Optional[dict] = None) -> str:
    """The project name recorded for one ticker, empty for a ticker no record names.

    ``kept`` is the coin index as ``load_coin_index`` answers it, and its own
    ``COIN_INDEX_NAME_KEY`` decides before the ``ASSETS`` record's name, so a name
    one walk settled is the name the next walk reads.
    """
    asked = str(symbol).strip().upper()
    row = (kept or {}).get(asked) or {}
    named = str(row.get(COIN_INDEX_NAME_KEY) or "").strip()
    if named:
        return named
    return ASSETS[asked].name if asked in ASSETS else ""


def coin_candidates(
    symbol: Any, by_symbol: dict, by_name: dict, name: Any = ""
) -> tuple[str, ...]:
    """Every coin id one ticker may name: the ticker, then ``name``, then the folded ticker.

    ``by_name`` is keyed on each coin's own project name, so a project whose name
    is not its ticker answers only under ``name``.
    """
    found = by_symbol.get(str(symbol).strip().upper(), ())
    if found:
        return tuple(str(one[COIN_ID_KEY]) for one in found)
    for key in (coin_folded(name), coin_folded(symbol)):
        named = by_name.get(key, ()) if key else ()
        if named:
            return tuple(str(one[COIN_ID_KEY]) for one in named)
    return ()


def coin_rank(record: Any) -> float:
    """The market rank one coin record carries, infinity for a record carrying none."""
    value = (record or {}).get(COIN_RANK_KEY)
    return float(value) if type(value) in (int, float) else float("inf")


def _coin_named(candidates: Sequence[str], records: dict) -> str:
    """``candidates`` as a list of each coin's own name beside its id."""
    return ", ".join(
        f"{(records.get(one) or {}).get(COIN_NAME_KEY, one)} ({one})"
        for one in candidates
    )


def choose_coin(
    symbol: str, candidates: Sequence[str], records: dict, name: Any = ""
) -> tuple[str, str]:
    """One coin id for ``symbol`` and how it was chosen, or an empty id and the refusal.

    ``name`` is the project name ``recorded_name`` answers and it decides first,
    then a lone ranked candidate, then a rank ``COIN_RANK_MARGIN`` better than the
    next. A ticker no name settles is refused with its candidates rather than
    guessed at.
    """
    present = [one for one in candidates if one in records]
    if not present:
        return "", COIN_ABSENT_REASON.format(symbol=symbol)
    if len(present) == 1:
        return present[0], "the only coin carrying this ticker"

    recorded = str(name).strip()
    if recorded:
        matched = [
            one
            for one in present
            if coin_folded(records[one].get(COIN_NAME_KEY)) == coin_folded(recorded)
        ]
        if len(matched) == 1:
            return matched[0], f"its recorded name {recorded}"

    ranked = sorted(present, key=lambda one: coin_rank(records.get(one)))
    carried = [one for one in present if coin_rank(records.get(one)) != float("inf")]
    if len(carried) == 1:
        return carried[0], "the only candidate carrying a market rank"
    if not carried:
        return "", COIN_UNRANKED_REASON.format(
            count=len(present), symbol=symbol, candidates=_coin_named(ranked, records)
        )

    best, second = ranked[0], ranked[1]
    if coin_rank(records[second]) >= COIN_RANK_MARGIN * coin_rank(records[best]):
        return best, (
            f"market rank {int(coin_rank(records[best]))} against "
            f"{int(coin_rank(records[second]))} for the next"
        )
    return "", COIN_AMBIGUOUS_REASON.format(
        count=len(present), symbol=symbol, candidates=_coin_named(ranked[:4], records)
    )


def _clear_unresolved(assets: dict, library: Path) -> tuple[str, ...]:
    """Every ticker dropped from ``unresolved_path`` whose ``assets`` row now carries an address.

    ``fill_library`` skips a ticker ``read_unresolved`` names.
    """
    held = read_unresolved(library)
    dropped = tuple(
        one
        for one, row in assets.items()
        if one in held and str(row.get(COIN_INDEX_IMAGE_KEY) or "").strip()
    )
    if not dropped:
        return ()
    for one in dropped:
        held.pop(one, None)
    write_unresolved(held, library)
    logger.info(COIN_CLEARED_LOG, len(dropped), len(held))
    return dropped


@dataclass(frozen=True)
class CoinIndexReport:
    """What one ``build_coin_index`` walk wrote, with every unsettled ticker in ``refused``."""

    tickers: int = 0
    listed: int = 0
    records: int = 0
    reads: int = 0
    addressed: int = 0
    refused: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    cleared: int = 0
    path: Optional[Path] = None

    @property
    def line(self) -> str:
        """``COIN_REPORT_FORMAT`` filled from this report."""
        return COIN_REPORT_FORMAT.format(
            tickers=self.tickers,
            listed=self.listed,
            records=self.records,
            reads=self.reads,
            addressed=self.addressed,
            refused=len(self.refused),
            cleared=self.cleared,
        )


def build_coin_index(
    symbols: Iterable[str],
    library_dir: Optional[Path] = None,
    pace: Optional[Any] = None,
    names: Optional[dict] = None,
) -> CoinIndexReport:
    """Look every ticker up through the coin list and its market records, and write the index.

    ``names`` maps a ticker to the project name ``coin_candidates`` and
    ``choose_coin`` read, and a ticker whose row gains an address is dropped from
    ``unresolved_path``.
    """
    library = Path(library_dir) if library_dir else LIBRARY_DIR
    clock = (
        pace
        if pace is not None
        else ReadPace(
            {COIN_API_HOST: COIN_API_PACE_S}, {COIN_API_HOST: COIN_API_HOLD_S}
        )
    )
    asked = tuple(
        sorted({str(one).strip().upper() for one in symbols if str(one).strip()})
    )
    # A walk over part of the roster keeps every ticker it did not ask about,
    # and reuses a site already kept for the same coin rather than reading again.
    held = {one: dict(row) for one, row in load_coin_index(library).items()}
    given = {
        str(one).strip().upper(): str(text).strip()
        for one, text in (names or {}).items()
        if str(one).strip() and str(text).strip()
    }
    project_names = {one: given.get(one) or recorded_name(one, held) for one in asked}

    listed = _coin_read(COIN_LIST_URL, clock)
    reads = 1
    if not isinstance(listed, list):
        return CoinIndexReport(tickers=len(asked), reads=reads)
    logger.info(COIN_LIST_LOG, len(listed))

    by_symbol: dict[str, list[dict]] = {}
    by_name: dict[str, list[dict]] = {}
    for coin in listed:
        if not isinstance(coin, dict) or COIN_ID_KEY not in coin:
            continue
        key = str(coin.get(COIN_SYMBOL_KEY, "")).strip().upper()
        by_symbol.setdefault(key, []).append(coin)
        by_name.setdefault(coin_folded(coin.get(COIN_NAME_KEY)), []).append(coin)

    wanted = {
        one: coin_candidates(one, by_symbol, by_name, project_names.get(one, ""))
        for one in asked
    }
    every = sorted({one for ids in wanted.values() for one in ids})

    records: dict[str, dict] = {}
    pages = 0
    for start in range(0, len(every), COIN_MARKETS_PAGE):
        page = every[start : start + COIN_MARKETS_PAGE]
        rows = _coin_read(
            COIN_MARKETS_URL.format(size=COIN_MARKETS_PAGE, ids=",".join(page)), clock
        )
        reads += 1
        pages += 1
        for row in rows if isinstance(rows, list) else ():
            if isinstance(row, dict) and COIN_ID_KEY in row:
                records[str(row[COIN_ID_KEY])] = row
    logger.info(COIN_RECORD_LOG, len(records), pages)

    assets: dict[str, dict] = {}
    refused: list[tuple[str, str]] = []
    sited = 0
    siteless = 0
    for symbol in asked:
        named = project_names.get(symbol, "")
        chosen, why = choose_coin(symbol, wanted[symbol], records, named)
        address = (
            str((records.get(chosen) or {}).get(COIN_IMAGE_KEY) or "").strip()
            if chosen
            else ""
        )
        if chosen and not address:
            why = COIN_NO_IMAGE_REASON.format(symbol=symbol)
        if address:
            row = {
                COIN_INDEX_IMAGE_KEY: address,
                COIN_INDEX_ID_KEY: chosen,
                COIN_INDEX_CHOSEN_KEY: why,
            }
            settled = str((records.get(chosen) or {}).get(COIN_NAME_KEY) or "").strip()
            if settled or named:
                row[COIN_INDEX_NAME_KEY] = settled or named
            kept = held.get(symbol) or {}
            site = (
                str(kept.get(COIN_INDEX_SITE_KEY) or "").strip()
                if kept.get(COIN_INDEX_ID_KEY) == chosen
                else ""
            )
            if not site:
                site = coin_site(_coin_read(COIN_DETAIL_URL.format(id=chosen), clock))
                reads += 1
            if site:
                row[COIN_INDEX_SITE_KEY] = site
                sited += 1
            else:
                row[COIN_INDEX_SITE_REASON_KEY] = COIN_NO_SITE_REASON.format(
                    symbol=symbol
                )
                siteless += 1
            assets[symbol] = row
            continue
        unsettled = {
            COIN_INDEX_REASON_KEY: why,
            COIN_INDEX_SITE_REASON_KEY: COIN_UNSETTLED_SITE_REASON.format(
                symbol=symbol
            ),
        }
        if named:
            unsettled[COIN_INDEX_NAME_KEY] = named
        assets[symbol] = unsettled
        siteless += 1
        refused.append((symbol, why))
    logger.info(COIN_SITE_LOG, sited + siteless, sited, siteless)

    path = coin_index_path(library)
    path.parent.mkdir(parents=True, exist_ok=True)
    held.update(assets)
    atomic_write_json(
        path,
        {
            COIN_INDEX_VERSION_KEY: COIN_INDEX_VERSION,
            COIN_INDEX_ASSETS_KEY: {name: held[name] for name in sorted(held)},
        },
        indent=2,
    )
    addressed = len(assets) - len(refused)
    logger.info(COIN_INDEX_LOG, addressed, len(refused))
    cleared = _clear_unresolved(assets, library)
    return CoinIndexReport(
        tickers=len(asked),
        listed=len(listed),
        records=len(records),
        reads=reads,
        addressed=addressed,
        refused=tuple(refused),
        cleared=len(cleared),
        path=path,
    )


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
    """The arguments ``main`` reads: the read budget, the library, the runtime directory.

    ``--coin-index`` rebuilds the coin index, and ``--name TICKER=NAME`` names the
    project one ticker is settled under; either rebuilds it, as does a
    ``coin_index_path`` naming no file.
    """
    parser = argparse.ArgumentParser(description="Fill the logo library.")
    parser.add_argument("--reads", type=int, default=DEFAULT_READ_LIMIT)
    parser.add_argument("--library", type=Path, default=None)
    parser.add_argument("--config-dir", type=Path, default=None)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--coin-index", action="store_true")
    parser.add_argument("--name", action="append", default=[], metavar="TICKER=NAME")
    return parser


def given_names(pairs: Iterable[str]) -> dict[str, str]:
    """Each ``TICKER=NAME`` pair as an upper-case ticker answering its project name.

    A pair naming no ticker or no name is dropped.
    """
    found: dict[str, str] = {}
    for one in pairs:
        ticker, _, named = str(one).partition("=")
        key = ticker.strip().upper()
        if key and named.strip():
            found[key] = named.strip()
    return found


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
    library = Path(args.library) if args.library else LIBRARY_DIR
    names = given_names(args.name)
    if args.coin_index or names or not coin_index_path(library).is_file():
        looked = build_coin_index(
            [one.symbol for one in rows if one.asset_class == CLASS_CRYPTO],
            library_dir=library,
            names=names,
        )
        print(looked.line)
        for symbol, reason in looked.refused:
            print(FAILURE_FORMAT.format(symbol=symbol, reason=reason))
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
    "COIN_API_HOST",
    "COIN_API_PACE_S",
    "COIN_RANK_MARGIN",
    "CoinIndexReport",
    "DEFAULT_READ_LIMIT",
    "LIBRARY_DIR",
    "LOGO_HOST",
    "build_coin_index",
    "choose_coin",
    "coin_candidates",
    "coin_folded",
    "coin_rank",
    "coin_site",
    "given_names",
    "recorded_name",
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
