"""Imports every Portfolio Battery symbol as an RA-StoneTablet and reports coverage.

``RA_YEARS`` is every calendar year the archive's ``PERIODS`` touch, and
``route_for`` sends a symbol to the crypto or the non-crypto source.
``import_symbols`` writes one tablet per symbol and year through
``RaTabletBuilder``; ``coverage`` reads the RA MANIFEST and GAPS.json back and
``format_coverage`` renders them.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from src.simulator.portfolios import PERIODS, SYMBOLS, is_crypto

from .ra_fetcher import (
    RA_STONE_TABLETS_DIR,
    RA_TIMEFRAME,
    CoinbasePublicCandles,
    RaCoinbaseAdapter,
    RaTabletBuilder,
    TabletGap,
    YahooChartAdapter,
    YearBuild,
    read_gaps,
)
from .storage import TabletEntry, read_manifest

logger = logging.getLogger("acervator.stone_tablets.ra_import")

COINBASE_SOURCE: str = "coinbase"
YAHOO_SOURCE: str = "yahoo"
YAHOO_CRYPTO_SOURCE: str = "yahoo_crypto"

CRYPTO_TICKER_SUFFIX: str = "-USD"
"""Yahoo spells a coin ``BTC-USD``; Coinbase does not list every archive coin."""

INTER_BUILD_SLEEP_S: float = 0.5
"""Pause between two ``build_year`` calls, on top of each adapter's chunk sleep."""


def _archive_years() -> tuple[int, ...]:
    """Return every calendar year ``PERIODS`` touches, ascending."""
    years: set[int] = set()
    for start, end in PERIODS.values():
        years.update(range(int(start[:4]), int(end[:4]) + 1))
    return tuple(sorted(years))


RA_YEARS: tuple[int, ...] = _archive_years()
"""2020 to 2026 — no portfolio names its own period, so every period applies."""


@dataclass(frozen=True)
class SymbolRoute:
    """One symbol's primary source and the fallback tried when it serves nothing."""

    symbol: str
    primary: str
    fallback: str = ""


def route_for(symbol: str) -> SymbolRoute:
    """Return ``symbol``'s route, crypto to Coinbase and everything else to Yahoo."""
    upper = symbol.upper()
    if is_crypto(upper):
        return SymbolRoute(upper, COINBASE_SOURCE, YAHOO_CRYPTO_SOURCE)
    return SymbolRoute(upper, YAHOO_SOURCE)


def builders(root: Optional[Path] = None) -> dict[str, RaTabletBuilder]:
    """Return one ``RaTabletBuilder`` per source name, all writing under ``root``."""
    return {
        COINBASE_SOURCE: RaTabletBuilder(
            RaCoinbaseAdapter(connector=CoinbasePublicCandles()),
            source=CoinbasePublicCandles.SOURCE,
            root=root,
        ),
        YAHOO_SOURCE: RaTabletBuilder(YahooChartAdapter(), root=root),
        YAHOO_CRYPTO_SOURCE: RaTabletBuilder(
            YahooChartAdapter(ticker_suffix=CRYPTO_TICKER_SUFFIX), root=root
        ),
    }


async def import_symbols(
    symbols: Sequence[str] = SYMBOLS,
    years: Sequence[int] = RA_YEARS,
    root: Optional[Path] = None,
    sleep_s: float = INTER_BUILD_SLEEP_S,
) -> list[YearBuild]:
    """Build every ``symbols`` by ``years`` tablet and return each ``YearBuild``.

    A crypto year the primary source serves no rows for is re-asked of the
    fallback source before it is left as a gap.
    """
    made = builders(root)
    out: list[YearBuild] = []
    for symbol in symbols:
        route = route_for(symbol)
        for year in years:
            build = await made[route.primary].build_year(route.symbol, year)
            if not build.candles_written and route.fallback:
                await asyncio.sleep(sleep_s)
                build = await made[route.fallback].build_year(route.symbol, year)
            out.append(build)
            logger.info(
                "ra_import %s %d via %s: %d candles, %d gaps",
                route.symbol,
                year,
                build.exchange_id,
                build.candles_written,
                len(build.gaps),
            )
            await asyncio.sleep(sleep_s)
    return out


def _iso_day(ts_ms: int) -> str:
    """Return ``ts_ms`` as a ``YYYY-MM-DD`` UTC date, or an empty string for zero."""
    if ts_ms <= 0:
        return ""
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def gap_kind(reason: str) -> str:
    """Return the coarse class of a gap ``reason``, for counting like with like."""
    if reason.startswith("no rows before"):
        return "market shut at the start of the window"
    if reason.startswith("no rows after"):
        return "market shut at the end of the window"
    if "404" in reason:
        return "endpoint 404 - ticker not found"
    if "400" in reason:
        return "endpoint 400 - outside the ticker's traded range"
    if "chart returned no result" in reason or "chart error" in reason:
        return "endpoint served no series"
    if "quoted in" in reason:
        return "series quoted in another currency"
    if "year has not started" in reason:
        return "year has not started"
    return reason


@dataclass(frozen=True)
class YearRows:
    """One symbol-year's stored rows, span and source."""

    year: int
    rows: int
    first_iso: str
    last_iso: str
    source: str


@dataclass(frozen=True)
class SymbolCoverage:
    """Every stored year for one symbol, and the years that hold nothing."""

    symbol: str
    years: tuple[YearRows, ...]
    years_missing: tuple[int, ...]

    @property
    def rows(self) -> int:
        """Return the symbol's stored rows across every year."""
        return sum(y.rows for y in self.years)

    @property
    def has_rows(self) -> bool:
        """True when at least one year holds a candle."""
        return self.rows > 0


@dataclass(frozen=True)
class Coverage:
    """What the RA root holds, measured against the symbols and years asked for."""

    symbols_asked: int
    symbols_with_rows: int
    tablets: int
    rows: int
    per_symbol: tuple[SymbolCoverage, ...]
    source_tablets: dict[str, int]
    source_fetch_span: dict[str, tuple[str, str]]
    gaps: tuple[TabletGap, ...]
    superseded: tuple[TabletGap, ...]
    gap_kinds: dict[str, int]

    @property
    def standing(self) -> tuple[TabletGap, ...]:
        """Return the gaps no other source covered."""
        beaten = {id(g) for g in self.superseded}
        return tuple(g for g in self.gaps if id(g) not in beaten)


def _entries_by_symbol(
    entries: Sequence[TabletEntry],
    symbols: Sequence[str],
    years: Sequence[int],
) -> dict[str, list[TabletEntry]]:
    """Group the manifest rows inside ``symbols`` and ``years`` by asset."""
    wanted_symbols = {s.upper() for s in symbols}
    wanted_years = set(years)
    grouped: dict[str, list[TabletEntry]] = {s.upper(): [] for s in symbols}
    for entry in entries:
        if entry.timeframe != RA_TIMEFRAME:
            continue
        if entry.asset in wanted_symbols and entry.year in wanted_years:
            grouped[entry.asset].append(entry)
    return grouped


def _symbol_coverage(
    symbol: str,
    entries: Sequence[TabletEntry],
    years: Sequence[int],
) -> SymbolCoverage:
    """Turn one asset's manifest rows into a ``SymbolCoverage``."""
    rows = tuple(
        YearRows(
            year=e.year,
            rows=e.candle_count,
            first_iso=_iso_day(e.first_ts_ms),
            last_iso=_iso_day(e.last_ts_ms),
            source=e.source,
        )
        for e in sorted(entries, key=lambda e: (e.year, e.exchange_id))
        if e.candle_count > 0
    )
    held = {y.year for y in rows}
    return SymbolCoverage(
        symbol=symbol.upper(),
        years=rows,
        years_missing=tuple(y for y in sorted(years) if y not in held),
    )


def coverage(
    symbols: Sequence[str] = SYMBOLS,
    years: Sequence[int] = RA_YEARS,
    root: Optional[Path] = None,
) -> Coverage:
    """Read the RA MANIFEST and GAPS.json back and measure what is on disk.

    ``root`` defaults to ``RA_STONE_TABLETS_DIR``; ``read_manifest`` would
    otherwise fall back to the live fleet's tree.
    """
    base = root or RA_STONE_TABLETS_DIR
    entries = read_manifest(base)
    grouped = _entries_by_symbol(entries, symbols, years)
    per_symbol = tuple(
        _symbol_coverage(symbol, grouped[symbol.upper()], years)
        for symbol in sorted({s.upper() for s in symbols})
    )
    source_tablets: dict[str, int] = {}
    source_span: dict[str, tuple[str, str]] = {}
    tablets = 0
    for entry in entries:
        if entry.asset not in grouped or entry.year not in set(years):
            continue
        tablets += 1
        source_tablets[entry.source] = source_tablets.get(entry.source, 0) + 1
        first, last = source_span.get(entry.source, (entry.fetched_at, entry.fetched_at))
        source_span[entry.source] = (
            min(first, entry.fetched_at),
            max(last, entry.fetched_at),
        )
    wanted = {s.upper() for s in symbols}
    gaps = tuple(
        g for g in read_gaps(root) if g.asset in wanted and g.year in set(years)
    )
    served = {
        (e.asset, e.year, e.exchange_id) for e in entries if e.candle_count > 0
    }
    superseded = tuple(
        g
        for g in gaps
        if any(
            asset == g.asset and year == g.year and exchange != g.exchange_id
            for asset, year, exchange in served
        )
    )
    beaten = {id(g) for g in superseded}
    kinds: dict[str, int] = {}
    for gap in gaps:
        if id(gap) in beaten:
            continue
        kind = gap_kind(gap.reason)
        kinds[kind] = kinds.get(kind, 0) + 1
    return Coverage(
        symbols_asked=len(wanted),
        symbols_with_rows=sum(1 for s in per_symbol if s.has_rows),
        tablets=tablets,
        rows=sum(s.rows for s in per_symbol),
        per_symbol=per_symbol,
        source_tablets=source_tablets,
        source_fetch_span=source_span,
        gaps=gaps,
        superseded=superseded,
        gap_kinds=kinds,
    )


def _headline_lines(cov: Coverage) -> list[str]:
    """Return the counts, the sources and the gap classes as report lines."""
    out = [
        "SYMBOLS",
        f"  asked for ......... {cov.symbols_asked}",
        f"  returned data ..... {cov.symbols_with_rows}",
        f"  tablets ........... {cov.tablets}",
        f"  candles ........... {cov.rows}",
        "",
        "SOURCES",
    ]
    for source in sorted(cov.source_tablets):
        first, last = cov.source_fetch_span[source]
        out.append(f"  {source}: {cov.source_tablets[source]} tablets, {first}..{last}")
    out += [
        "",
        f"GAPS ({len(cov.gaps)} recorded, {len(cov.superseded)} of them covered "
        f"by the other source, {len(cov.standing)} standing)",
    ]
    for kind, count in sorted(cov.gap_kinds.items(), key=lambda kv: -kv[1]):
        out.append(f"  {count:5d}  {kind}")
    return out


def _symbol_lines(cov: Coverage) -> list[str]:
    """Return one block per symbol, a line per stored year."""
    out = ["", "ROWS PER SYMBOL PER YEAR"]
    for entry in cov.per_symbol:
        missing = (
            f"  missing: {', '.join(str(y) for y in entry.years_missing)}"
            if entry.years_missing
            else ""
        )
        out.append(f"  {entry.symbol}{missing}")
        for year in entry.years:
            out.append(
                f"    {year.year}  {year.rows:5d} rows  "
                f"{year.first_iso}..{year.last_iso}  {year.source}"
            )
    return out


def _gap_lines(cov: Coverage) -> list[str]:
    """Return one line per recorded gap, naming its symbol, period and reason."""
    beaten = {id(g) for g in cov.superseded}
    out = ["", "EVERY GAP"]
    for gap in sorted(cov.gaps, key=lambda g: (g.asset, g.year, g.since_ms)):
        mark = "covered-elsewhere" if id(gap) in beaten else "standing"
        out.append(
            f"  {gap.asset:6s} {gap.year} {gap.exchange_id:9s} {mark:17s} "
            f"[{_iso_day(gap.since_ms)}..{_iso_day(gap.until_ms)}] {gap.reason}"
        )
    return out


def format_coverage(cov: Coverage, detail: bool = True) -> str:
    """Render ``cov`` as the coverage statement, with per-symbol blocks in ``detail``."""
    lines = _headline_lines(cov)
    if detail:
        lines += _symbol_lines(cov)
        lines += _gap_lines(cov)
    return "\n".join(lines)


def _parse_list(raw: str, default: Sequence[str]) -> list[str]:
    """Split a comma-separated argument, falling back to ``default`` when empty."""
    if not raw.strip():
        return [str(item) for item in default]
    return [part.strip().upper() for part in raw.split(",") if part.strip()]


def _build_parser() -> argparse.ArgumentParser:
    """Return the ``import`` and ``coverage`` subcommand parser."""
    parser = argparse.ArgumentParser(
        prog="ra_import",
        description="Fetch and report the Portfolio Battery's RA-StoneTablets.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("import", "fetch and store every tablet the RA root does not hold"),
        ("coverage", "read the stored tablets back and print the coverage statement"),
    ):
        part = sub.add_parser(name, help=help_text)
        part.add_argument("--symbols", default="", help="comma-separated subset")
        part.add_argument("--years", default="", help="comma-separated subset")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run one subcommand and print its coverage statement."""
    args = _build_parser().parse_args(argv)
    symbols = _parse_list(args.symbols, SYMBOLS)
    years = [int(y) for y in _parse_list(args.years, [str(y) for y in RA_YEARS])]
    if args.command == "import":
        asyncio.run(import_symbols(symbols, years))
    print(format_coverage(coverage(symbols, years)))
    return 0


if __name__ == "__main__":  # pragma: no cover - console entry
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    sys.exit(main())


__all__ = [
    "CRYPTO_TICKER_SUFFIX",
    "RA_YEARS",
    "Coverage",
    "SymbolCoverage",
    "SymbolRoute",
    "YearRows",
    "builders",
    "coverage",
    "format_coverage",
    "gap_kind",
    "import_symbols",
    "main",
    "route_for",
]
