"""Import an exchange's transactions CSV into the YTD trade files.

``import_ytd_csv`` chooses the ``ExportColumnMap`` registered for its
``exchange_id`` in ``EXPORT_MAPS``, reads that map's columns off the header
``find_header`` locates, keeps the map's buy and sell rows as ``YtdTrade``, and
writes one file per symbol and year through ``write_trade_file``.
``COINBASE_MAP`` is the one map registered; ``export_map_for`` refuses every
other ``exchange_id`` by name. ``YtdImportRefused`` names a missing column or an
unreadable row, and ``ImportResult`` carries the kept and dropped counts and
every ``TradeGap``.
"""

from __future__ import annotations

import csv
import hashlib
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .ytd_trade_store import (
    SIDE_BUY,
    SIDE_SELL,
    ImportSource,
    TradeGap,
    YtdTrade,
    YtdTradeFile,
    entry_from_file,
    get_ytd_root,
    merge_trades,
    read_gaps,
    read_manifest,
    read_trade_file,
    utc_now_iso,
    write_gaps,
    write_manifest,
    write_trade_file,
    ytd_path,
)

logger = logging.getLogger("acervator.exchange.ytd_csv_import")

COL_ID = "ID"
COL_TIMESTAMP = "Timestamp"
COL_TYPE = "Transaction Type"
COL_ASSET = "Asset"
COL_QUANTITY = "Quantity Transacted"
COL_PRICE_CURRENCY = "Price Currency"
COL_PRICE = "Price at Transaction"
COL_SUBTOTAL = "Subtotal"
COL_FEES = "Fees and/or Spread"

REQUIRED_COLUMNS: tuple[str, ...] = (
    COL_ID,
    COL_TIMESTAMP,
    COL_TYPE,
    COL_ASSET,
    COL_QUANTITY,
    COL_PRICE_CURRENCY,
    COL_PRICE,
    COL_SUBTOTAL,
    COL_FEES,
)
"""Every column ``import_ytd_csv`` reads; a file missing one is refused."""

DROPPED_COLUMNS: tuple[str, ...] = ("Notes", "Sender Address", "Recipient Address")
"""Columns present in the export that no ``YtdTrade`` field carries."""

BUY_TYPES: frozenset[str] = frozenset({"advanced trade buy", "buy"})
SELL_TYPES: frozenset[str] = frozenset({"advanced trade sell", "sell"})

HEADER_SCAN_LINES: int = 20
"""Rows ``find_header`` reads before refusing; the export carries a preamble."""

TIMESTAMP_SUFFIX_UTC = " UTC"

TIMESTAMP_FORMAT_UTC: str = "%Y-%m-%d %H:%M:%S"
"""The ``strptime`` form ``parse_timestamp_ms`` reads under
``TIMESTAMP_SUFFIX_UTC``."""

MONEY_PREFIXES: str = "$€£¥"
"""Currency marks stripped by ``parse_money``; the export writes amounts as
``$1.23``."""

CellReader = Callable[[str], str]
"""Reads one named column out of the CSV row ``_cell_reader`` was given."""


class YtdImportRefused(ValueError):
    """Raised when a column is missing or a kept row carries an unreadable
    field."""


@dataclass(frozen=True)
class ExportColumnMap:
    """The columns, type strings and text forms of one exchange's CSV export,
    each column named for the ``YtdTrade`` field it fills."""

    exchange_id: str
    export_name: str
    id_column: str
    timestamp_column: str
    type_column: str
    asset_column: str
    quote_column: str
    quantity_column: str
    price_column: str
    cost_column: str
    fee_column: str
    buy_types: frozenset[str]
    sell_types: frozenset[str]
    header_scan_lines: int
    timestamp_suffix_utc: str
    timestamp_format: str
    money_prefixes: str
    dropped_columns: tuple[str, ...] = ()

    @property
    def required_columns(self) -> tuple[str, ...]:
        """Return the nine column names ``find_header`` requires, in
        ``REQUIRED_COLUMNS`` order."""
        return (
            self.id_column,
            self.timestamp_column,
            self.type_column,
            self.asset_column,
            self.quantity_column,
            self.quote_column,
            self.price_column,
            self.cost_column,
            self.fee_column,
        )


COINBASE_MAP = ExportColumnMap(
    exchange_id="coinbase",
    export_name="Coinbase transactions export",
    id_column=COL_ID,
    timestamp_column=COL_TIMESTAMP,
    type_column=COL_TYPE,
    asset_column=COL_ASSET,
    quote_column=COL_PRICE_CURRENCY,
    quantity_column=COL_QUANTITY,
    price_column=COL_PRICE,
    cost_column=COL_SUBTOTAL,
    fee_column=COL_FEES,
    buy_types=BUY_TYPES,
    sell_types=SELL_TYPES,
    header_scan_lines=HEADER_SCAN_LINES,
    timestamp_suffix_utc=TIMESTAMP_SUFFIX_UTC,
    timestamp_format=TIMESTAMP_FORMAT_UTC,
    money_prefixes=MONEY_PREFIXES,
    dropped_columns=DROPPED_COLUMNS,
)
"""The Coinbase transactions export: ``REQUIRED_COLUMNS``, ``BUY_TYPES``,
``SELL_TYPES`` and the text forms above."""

EXPORT_MAPS: dict[str, ExportColumnMap] = {COINBASE_MAP.exchange_id: COINBASE_MAP}
"""Every ``ExportColumnMap`` by ``exchange_id``; a map is written from a sample
export on disk."""


def export_map_for(exchange_id: str) -> ExportColumnMap:
    """Return ``EXPORT_MAPS[exchange_id]``, refusing an ``exchange_id`` with no
    map by name."""
    column_map = EXPORT_MAPS.get(exchange_id)
    if column_map is None:
        message = (
            f"no column map for exchange {exchange_id!r}: a sample {exchange_id} "
            f"export is needed before its map is written. Maps exist for: "
            f"{sorted(EXPORT_MAPS)}."
        )
        raise YtdImportRefused(message)
    return column_map


@dataclass
class ImportResult:
    """What one ``import_ytd_csv`` run read, kept, dropped and wrote."""

    source_file: str
    source_sha256: str
    exchange_id: str
    rows_read: int = 0
    rows_kept: int = 0
    trades_written: int = 0
    trades_added: int = 0
    files_written: list[str] = field(default_factory=list)
    files_unchanged: list[str] = field(default_factory=list)
    dropped_by_type: dict[str, int] = field(default_factory=dict)
    symbols: list[str] = field(default_factory=list)
    first_ts_ms: int = 0
    last_ts_ms: int = 0
    gaps: list[TradeGap] = field(default_factory=list)


def file_sha256(path: Path) -> str:
    """Return the SHA-256 of ``path``'s bytes."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def find_header(rows: list[list[str]], column_map: ExportColumnMap) -> int:
    """Return the index of the first row holding every ``column_map``
    ``required_columns`` name."""
    required = column_map.required_columns
    best_index = -1
    best_missing: list[str] = list(required)
    for index, row in enumerate(rows[: column_map.header_scan_lines]):
        cells = {cell.strip() for cell in row}
        missing = [name for name in required if name not in cells]
        if not missing:
            return index
        if len(missing) < len(best_missing):
            best_index = index
            best_missing = missing
    message = (
        f"no header in the first {column_map.header_scan_lines} rows carries every "
        f"required column. Closest is row {best_index + 1}, missing "
        f"{best_missing}. Required: {list(required)}."
    )
    raise YtdImportRefused(message)


def blank_column(column: str, row_number: int) -> str:
    """Return the refusal message naming an empty ``column`` at ``row_number``."""
    return f"row {row_number}: column {column!r} is empty"


def parse_money(text: str, column: str, row_number: int, money_prefixes: str) -> float:
    """Return ``text`` as a float, reading a sign on either side of its
    ``money_prefixes`` mark."""
    cleaned = text.strip().replace(",", "")
    negative = False
    while cleaned and (cleaned[0] in money_prefixes or cleaned[0] in "+-"):
        if cleaned[0] == "-":
            negative = not negative
        cleaned = cleaned[1:].strip()
    if not cleaned:
        raise YtdImportRefused(blank_column(column, row_number))
    try:
        value = float(cleaned)
    except ValueError as exc:
        message = f"row {row_number}: column {column!r} is not a number"
        raise YtdImportRefused(message) from exc
    return -value if negative else value


def parse_optional_money(
    text: str, column: str, row_number: int, money_prefixes: str
) -> float:
    """Return ``parse_money`` of ``text``, or 0.0 when it is blank."""
    if not text.strip():
        return 0.0
    return parse_money(text, column, row_number, money_prefixes)


def parse_timestamp_ms(text: str, row_number: int, column_map: ExportColumnMap) -> int:
    """Return ``text`` as epoch milliseconds, reading ``column_map``'s
    ``timestamp_suffix_utc`` and ``timestamp_format``, else ISO 8601."""
    column = column_map.timestamp_column
    suffix = column_map.timestamp_suffix_utc
    raw = text.strip()
    if not raw:
        raise YtdImportRefused(blank_column(column, row_number))
    if raw.endswith(suffix):
        raw = raw[: len(raw) - len(suffix)].strip()
        try:
            moment = datetime.strptime(raw, column_map.timestamp_format).replace(
                tzinfo=timezone.utc
            )
        except ValueError as exc:
            message = (
                f"row {row_number}: column {column!r} is not "
                f"'{column_map.timestamp_format}{suffix}'"
            )
            raise YtdImportRefused(message) from exc
    else:
        try:
            moment = datetime.fromisoformat(raw)
        except ValueError as exc:
            message = (
                f"row {row_number}: column {column!r} is not an ISO 8601 timestamp"
            )
            raise YtdImportRefused(message) from exc
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def sign_matches_side(quantity: float, side: str) -> bool:
    """True when a ``SIDE_SELL`` ``quantity`` is not positive and a ``SIDE_BUY``
    one is not negative."""
    if side == SIDE_SELL:
        return quantity <= 0.0
    return quantity >= 0.0


def side_for(transaction_type: str, column_map: ExportColumnMap) -> str:
    """Return ``SIDE_BUY``, ``SIDE_SELL`` or '' for a ``transaction_type``
    outside ``column_map``'s ``buy_types`` and ``sell_types``."""
    normalized = transaction_type.strip().lower()
    if normalized in column_map.buy_types:
        return SIDE_BUY
    if normalized in column_map.sell_types:
        return SIDE_SELL
    return ""


def read_trade_rows(
    csv_path: Path,
    column_map: ExportColumnMap,
) -> tuple[list[tuple[str, YtdTrade]], int, dict[str, int]]:
    """Return the ``(symbol, YtdTrade)`` pairs ``column_map`` reads out of
    ``csv_path`` with the row count and the dropped counts by transaction type."""
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    header_index = find_header(rows, column_map)
    header = [cell.strip() for cell in rows[header_index]]
    column_of = {name: header.index(name) for name in column_map.required_columns}

    pairs: list[tuple[str, YtdTrade]] = []
    dropped: dict[str, int] = defaultdict(int)
    rows_read = 0
    for offset, row in enumerate(rows[header_index + 1 :]):
        if not any(cell.strip() for cell in row):
            continue
        rows_read += 1
        row_number = header_index + 2 + offset
        cell = _cell_reader(row, column_of, row_number)
        transaction_type = cell(column_map.type_column)
        side = side_for(transaction_type, column_map)
        if not side:
            dropped[transaction_type.strip() or "(blank)"] += 1
            continue
        pairs.append(
            (
                _symbol_of(cell, row_number, column_map),
                _trade_of(cell, side, row_number, column_map),
            )
        )
    return pairs, rows_read, dict(dropped)


def _cell_reader(
    row: list[str], column_of: dict[str, int], row_number: int
) -> CellReader:
    """Return a function giving ``row``'s value for a ``column_of`` name."""

    def read(name: str) -> str:
        index = column_of[name]
        if index >= len(row):
            message = f"row {row_number}: column {name!r} is missing"
            raise YtdImportRefused(message)
        return row[index]

    return read


def _symbol_of(cell: CellReader, row_number: int, column_map: ExportColumnMap) -> str:
    """Return ``ASSET/QUOTE`` from the row's ``asset_column`` and
    ``quote_column``."""
    asset = cell(column_map.asset_column).strip().upper()
    quote = cell(column_map.quote_column).strip().upper()
    if not asset:
        raise YtdImportRefused(blank_column(column_map.asset_column, row_number))
    if not quote:
        raise YtdImportRefused(blank_column(column_map.quote_column, row_number))
    return f"{asset}/{quote}"


def _trade_of(
    cell: CellReader, side: str, row_number: int, column_map: ExportColumnMap
) -> YtdTrade:
    """Return the ``YtdTrade`` the row holds under ``column_map``, refusing an
    unreadable field."""
    prefixes = column_map.money_prefixes
    quantity_column = column_map.quantity_column
    price_column = column_map.price_column
    trade_id = cell(column_map.id_column).strip()
    if not trade_id:
        raise YtdImportRefused(blank_column(column_map.id_column, row_number))
    quantity = parse_money(cell(quantity_column), quantity_column, row_number, prefixes)
    price = parse_money(cell(price_column), price_column, row_number, prefixes)
    if not sign_matches_side(quantity, side):
        message = (
            f"row {row_number}: column {quantity_column!r} sign disagrees with "
            f"column {column_map.type_column!r} side {side}"
        )
        raise YtdImportRefused(message)
    amount = abs(quantity)
    if amount <= 0:
        message = f"row {row_number}: column {quantity_column!r} is zero"
        raise YtdImportRefused(message)
    if price <= 0:
        message = f"row {row_number}: column {price_column!r} is not above zero"
        raise YtdImportRefused(message)
    cost_column = column_map.cost_column
    fee_column = column_map.fee_column
    return YtdTrade(
        id=trade_id,
        ts_ms=parse_timestamp_ms(
            cell(column_map.timestamp_column), row_number, column_map
        ),
        side=side,
        amount=amount,
        price=price,
        cost=abs(
            parse_optional_money(cell(cost_column), cost_column, row_number, prefixes)
        ),
        fee=parse_optional_money(cell(fee_column), fee_column, row_number, prefixes),
        fee_currency=cell(column_map.quote_column).strip().upper(),
    )


def year_of(ts_ms: int) -> int:
    """Return the UTC year holding ``ts_ms``."""
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).year


def iso_day(ts_ms: int) -> str:
    """Return ``ts_ms`` as a ``YYYY-MM-DD`` UTC date."""
    return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")


def year_window_ms(year: int) -> tuple[int, int]:
    """Return the first and last millisecond of ``year`` in UTC."""
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000) - 1


def import_ytd_csv(
    csv_path: Path,
    exchange_id: str,
    root: Optional[Path] = None,
) -> ImportResult:
    """Read ``csv_path`` and write ``exchange_id``'s trade files under
    ``get_ytd_root(root)``."""
    column_map = export_map_for(exchange_id)
    csv_path = Path(csv_path)
    if not csv_path.exists():
        message = f"no file at {csv_path.name}"
        raise YtdImportRefused(message)
    base = get_ytd_root(root)
    digest = file_sha256(csv_path)
    imported_at = utc_now_iso()
    result = ImportResult(
        source_file=csv_path.name, source_sha256=digest, exchange_id=exchange_id
    )

    pairs, result.rows_read, result.dropped_by_type = read_trade_rows(
        csv_path, column_map
    )
    result.rows_kept = len(pairs)
    if not pairs:
        logger.warning("ytd_csv_import: %s carried no trade rows", csv_path.name)
        return result

    by_key: dict[tuple[str, int], list[YtdTrade]] = defaultdict(list)
    for symbol, trade in pairs:
        by_key[(symbol, year_of(trade.ts_ms))].append(trade)
    result.first_ts_ms = min(t.ts_ms for _, t in pairs)
    result.last_ts_ms = max(t.ts_ms for _, t in pairs)
    result.symbols = sorted({symbol for symbol, _ in pairs})

    entries = {e.file: e for e in read_manifest(base)}
    gaps: list[TradeGap] = []
    for symbol in result.symbols:
        for year in range(year_of(result.first_ts_ms), year_of(result.last_ts_ms) + 1):
            gaps.extend(
                _store_year(
                    result,
                    entries,
                    base,
                    exchange_id,
                    symbol,
                    year,
                    by_key.get((symbol, year), []),
                    imported_at,
                )
            )

    write_manifest(
        sorted(entries.values(), key=lambda e: (e.exchange_id, e.symbol, e.year)),
        root=base,
    )
    result.gaps = gaps
    write_gaps(_gaps_kept(base, exchange_id, result) + gaps, root=base)
    return result


def _store_year(
    result: ImportResult,
    entries: dict,
    base: Path,
    exchange_id: str,
    symbol: str,
    year: int,
    incoming: list[YtdTrade],
    imported_at: str,
) -> list[TradeGap]:
    """Merge ``incoming`` into ``symbol``'s ``year`` file and return that year's
    gaps."""
    window_start, window_end = year_window_ms(year)
    covered_start = max(window_start, result.first_ts_ms)
    covered_end = min(window_end, result.last_ts_ms)
    if not incoming:
        return [
            _gap(
                exchange_id,
                symbol,
                year,
                covered_start,
                covered_end,
                f"{result.source_file} carries no {symbol} trade in {year}",
                imported_at,
            )
        ]

    path = ytd_path(exchange_id, symbol, year, root=base)
    stored = read_trade_file(path)
    held = list(stored.trades) if stored else []
    merged, added = merge_trades(held, incoming)
    trade_file = YtdTradeFile(
        exchange_id=exchange_id,
        symbol=symbol,
        year=year,
        imported_at=imported_at if added else (stored.imported_at if stored else ""),
        trades=merged,
        sources=list(stored.sources) if stored else [],
    )
    if added:
        trade_file.sources.append(
            ImportSource(
                file=result.source_file,
                sha256=result.source_sha256,
                imported_at=imported_at,
                rows_added=added,
            )
        )
        write_trade_file(trade_file, root=base)
        result.files_written.append(path.name)
    else:
        result.files_unchanged.append(path.name)
    result.trades_written += len(merged)
    result.trades_added += added
    entries[path.name] = entry_from_file(trade_file)
    return _edge_gaps(
        exchange_id,
        symbol,
        year,
        covered_start,
        covered_end,
        merged[0].ts_ms,
        merged[-1].ts_ms,
        result.source_file,
        imported_at,
    )


def _edge_gaps(
    exchange_id: str,
    symbol: str,
    year: int,
    covered_start: int,
    covered_end: int,
    first_ts_ms: int,
    last_ts_ms: int,
    source_file: str,
    checked_at: str,
) -> list[TradeGap]:
    """Return the covered days outside the span the stored rows reach."""
    out: list[TradeGap] = []
    if covered_start < first_ts_ms:
        out.append(
            _gap(
                exchange_id,
                symbol,
                year,
                covered_start,
                first_ts_ms - 1,
                f"{source_file} carries no {symbol} trade before "
                f"{iso_day(first_ts_ms)}",
                checked_at,
            )
        )
    if last_ts_ms < covered_end:
        out.append(
            _gap(
                exchange_id,
                symbol,
                year,
                last_ts_ms + 1,
                covered_end,
                f"{source_file} carries no {symbol} trade after "
                f"{iso_day(last_ts_ms)}",
                checked_at,
            )
        )
    return out


def _gap(
    exchange_id: str,
    symbol: str,
    year: int,
    since_ms: int,
    until_ms: int,
    reason: str,
    checked_at: str,
) -> TradeGap:
    """Return one ``TradeGap`` for ``symbol`` and ``year``."""
    return TradeGap(
        exchange_id=exchange_id,
        symbol=symbol,
        year=year,
        since_ms=since_ms,
        until_ms=until_ms,
        reason=reason,
        checked_at=checked_at,
    )


def _gaps_kept(base: Path, exchange_id: str, result: ImportResult) -> list[TradeGap]:
    """Return the stored gaps this run did not re-measure."""
    touched = {
        (exchange_id, symbol, year)
        for symbol in result.symbols
        for year in range(year_of(result.first_ts_ms), year_of(result.last_ts_ms) + 1)
    }
    return [
        g for g in read_gaps(base) if (g.exchange_id, g.symbol, g.year) not in touched
    ]


__all__ = [
    "BUY_TYPES",
    "COINBASE_MAP",
    "COL_ASSET",
    "COL_FEES",
    "COL_ID",
    "COL_PRICE",
    "COL_PRICE_CURRENCY",
    "COL_QUANTITY",
    "COL_SUBTOTAL",
    "COL_TIMESTAMP",
    "COL_TYPE",
    "DROPPED_COLUMNS",
    "EXPORT_MAPS",
    "HEADER_SCAN_LINES",
    "MONEY_PREFIXES",
    "REQUIRED_COLUMNS",
    "SELL_TYPES",
    "TIMESTAMP_FORMAT_UTC",
    "TIMESTAMP_SUFFIX_UTC",
    "ExportColumnMap",
    "ImportResult",
    "YtdImportRefused",
    "export_map_for",
    "file_sha256",
    "find_header",
    "import_ytd_csv",
    "iso_day",
    "parse_money",
    "parse_optional_money",
    "parse_timestamp_ms",
    "read_trade_rows",
    "side_for",
    "sign_matches_side",
    "year_of",
    "year_window_ms",
]
