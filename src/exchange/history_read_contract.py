"""history_read_contract.py -- the read-only backend contract for History.

Issue #128 unit R3. ADDITIVE: nothing that already exists changes
behaviour. ``src/gui/history_tab.py`` is not wired to this module in this
unit -- wiring it is a later unit, and doing both at once would put a
behaviour change and a structural change in one blast radius.

WHAT THIS SERVES

Everything the History tab puts on screen, as plain serialisable values:
``str``, ``int``, ``float``, ``bool``, ``None``, ``list`` and ``dict`` of
those. No Qt type, no widget and no ``datetime`` object crosses the
boundary -- a trade row's instant is served as a unix ``float`` and as
the exact string the table shows.

THE UNIT OF THE CONTRACT IS THE CELL, NOT THE ROW. Each of the thirteen
columns yields a ``HistoryCell`` carrying four things:

    value    the raw serialisable datum, for a client that formats
    text     the exact string ``history_tab.py`` puts in that cell
    color    the "#rrggbb" foreground the tab sets, or None
    tooltip  the hover text the tab attaches, or None

``text`` and ``color`` exist because a contract that served only raw
values could not be proved to agree with the screen. They are what
``tests/test_history_read_contract.py`` compares, cell for cell, against
the real Qt widget driven on the same input.

WHAT IT DOES NOT DO

It never writes. It reads ``bot_manager._bots`` through ``getattr``,
reads the gate and voting logs through ``src.trading.live_log_reader``,
and returns new lists. ``tests/test_history_read_contract.py`` drives it
against a bot and asserts the bot's state is byte-identical afterwards.

It emits nothing. The seven ``history.05.*`` pins stay where they are and
the census stays at 78.

THE ROW ORDER IS THE FETCH ORDER AND THERE IS NO USER SORT.
``history_helpers.fetch_all_history_chunked`` sorts newest-first
(``reverse=True``) and nothing re-sorts downstream. ``history_tab.py``
never calls ``setSortingEnabled``, so no column header sorts anything.
``ROW_ORDER`` states that rather than leaving a client to infer it, and
``sort_trades`` is the only ordering this subsystem has.

KNOWN DEFECT SERVED AS-IS -- the "Cost USD" column.
``history_helpers.py:146`` writes ``amount * price`` and discards the
venue's own cost field; the header says "Cost USD" and the cell carries a
dollar sign whatever the quote currency is. This contract serves that
number unchanged, because a contract that disagreed with the screen would
be a second implementation. Repairing it is its own unit -- see
``docs/audits/2026-08-26_qt_to_react_boundary.md`` section 6.2.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from src.trading.gate_vocabulary import gate_light_row
from src.exchange.history_helpers import (
    build_page_gate_index,
    build_page_voting_index,
    fetch_all_history_chunked,
    gate_cell_text,
    gate_cell_tooltip,
    grade_tooltip,
    lookup_gate_entry,
    lookup_voting_entry,
    resolve_bot_id_for_row,
    resolve_bot_label,
    voting_cell_text,
    voting_cell_tooltip,
)

# --------------------------------------------------------------------- #
# Contract constants                                                     #
# --------------------------------------------------------------------- #

PAGE_SIZE = 100
"""Rows per page. Mirrors ``history_tab.py:174``."""

ALL = "(all)"
"""The sentinel the three dropdowns carry at index 0. It is chrome, not a
value: no exchange, symbol or side is ever named ``(all)``."""

SIDES = ("BUY", "SELL")
"""The only two sides the normalizer emits (``history_helpers.py:110``)."""

ROW_ORDER = "timestamp_desc"
"""Newest first. The fetch sorts ``reverse=True`` and nothing re-sorts.
The tab enables no column sort, so this is the whole ordering contract."""

DEFAULT_FROM_LOCAL = (2026, 4, 1, 0, 0, 0)
"""The From date the tab opens and resets to, as LOCAL wall-clock parts.

It is local, not UTC, and the difference is real. ``history_tab.py:235``
builds ``QDateTime(QDate(2026, 4, 1), QTime(0, 0, 0))`` with no timezone,
which Qt reads as local time, and ``:412`` converts it with
``toSecsSinceEpoch()``. ``history_helpers.DEFAULT_START_DATE`` is the
same wall clock in UTC and is a different instant everywhere but UTC."""

FETCH_POLL_INTERVAL_S = 0.4
"""The tab observes the fetch future on a 400 ms timer
(``history_tab.py:443``), so an observed fetch latency is the true
latency plus up to one interval."""

FETCH_TIMEOUT_S = 60.0
"""The tab gives up on a fetch after 60 s (``history_tab.py:540``)."""

STATUS_TEXT = {
    "idle": "No history loaded yet — click Refresh.",
    "no_bot_manager": "Bot manager unavailable — cannot fetch history.",
    "no_async_loop": "Async loop not ready — try again after platform starts.",
    "fetching": "Fetching trade history from exchanges…",
    "timeout": "Fetch timeout (60s). Exchange may be rate-limited; try again.",
}
"""The five fixed status strings the summary line shows before any row
exists. The two variable ones are ``Schedule failed: {exc}`` and
``Fetch raised: {type}: {exc}``."""

_SIDE_COLOR = {"BUY": "#00ff88", "SELL": "#ff5566"}
_GRADE_COLOR = {
    "A": "#00ff88",
    "B": "#88dd44",
    "C": "#dddd44",
    "D": "#ff9944",
    "F": "#ff5566",
}
_GATE_ARMED_COLOR = "#00ff88"
_GATE_BLOCKED_COLOR = "#ff5566"
_GATE_MIXED_COLOR = "#ffaa33"
_VOTE_BUY_COLOR = "#00ff88"
_VOTE_SELL_COLOR = "#ff5566"

_EMPTY = "—"
"""The em dash the tab renders for an absent value. One character, and
``gate_cell_text`` deliberately does NOT use it -- see its docstring."""


# --------------------------------------------------------------------- #
# Column specification                                                   #
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class HistoryColumn:
    """One of the thirteen columns. ``index`` is the table column index."""

    index: int
    key: str
    header: str
    header_tooltip: str = ""


COLUMNS: tuple[HistoryColumn, ...] = (
    HistoryColumn(0, "timestamp", "Timestamp (UTC)"),
    HistoryColumn(1, "exchange", "Exchange"),
    HistoryColumn(2, "symbol", "Symbol"),
    HistoryColumn(3, "bot", "Bot"),
    HistoryColumn(4, "side", "Side"),
    HistoryColumn(5, "amount", "Amount"),
    HistoryColumn(6, "price", "Price"),
    HistoryColumn(7, "cost", "Cost USD"),
    HistoryColumn(8, "fee", "Fee"),
    HistoryColumn(9, "trade_id", "Trade ID"),
    HistoryColumn(
        10,
        "grade",
        "Grade",
        "On-demand grade (A–F) computed by "
        "src.trading.trade_grader from surrounding same-asset "
        "trades on this page. Hover for the letter meaning.",
    ),
    HistoryColumn(
        11,
        "gates",
        "Gates",
        "Join against ~/.acervator_logs/trade/gate.log entries "
        "within ±60s of the trade. Hover any cell for the full "
        "scrum/fold arm state + blocker list at trade time.",
    ),
    HistoryColumn(
        12,
        "voting",
        "Voting",
        "Join against ~/.acervator_logs/trade/voting.log "
        "snapshots. Hover any cell for the per-indicator "
        "direction / confidence / timeframe / weight roll-up "
        "the panel saw at trade time.",
    ),
)

COLUMN_KEYS: tuple[str, ...] = tuple(c.key for c in COLUMNS)


# --------------------------------------------------------------------- #
# Row + page containers                                                  #
# --------------------------------------------------------------------- #


@dataclass
class HistoryCell:
    """One rendered cell. ``value`` is raw; ``text`` is what the screen
    shows."""

    key: str
    value: Any
    text: str
    color: Optional[str] = None
    tooltip: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "text": self.text,
            "color": self.color,
            "tooltip": self.tooltip,
        }


@dataclass
class HistoryRow:
    """Thirteen cells plus the row's identity and its gate-light state."""

    trade_id: str
    timestamp: float
    cells: list[HistoryCell] = field(default_factory=list)
    gate_lights: Optional[dict] = None

    def cell(self, key: str) -> HistoryCell:
        for candidate in self.cells:
            if candidate.key == key:
                return candidate
        raise KeyError(key)

    def as_dict(self) -> dict:
        return {
            "trade_id": self.trade_id,
            "timestamp": self.timestamp,
            "cells": [c.as_dict() for c in self.cells],
            "gate_lights": self.gate_lights,
        }


@dataclass
class HistoryPage:
    """One page of rows plus the pager state the footer renders."""

    rows: list[HistoryRow]
    page: int
    pages: int
    total: int
    page_size: int
    page_label: str
    prev_enabled: bool
    next_enabled: bool

    def as_dict(self) -> dict:
        return {
            "rows": [r.as_dict() for r in self.rows],
            "page": self.page,
            "pages": self.pages,
            "total": self.total,
            "page_size": self.page_size,
            "page_label": self.page_label,
            "prev_enabled": self.prev_enabled,
            "next_enabled": self.next_enabled,
        }


@dataclass
class HistoryFilters:
    """The five filter values the tab reads off two date edits and three
    combos. ``from_ts`` and ``to_ts`` are unix seconds; 0 is inactive."""

    from_ts: int = 0
    to_ts: int = 0
    exchange: str = ALL
    symbol: str = ALL
    side: str = ALL

    def as_dict(self) -> dict:
        return {
            "from_ts": self.from_ts,
            "to_ts": self.to_ts,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "side": self.side,
        }


# --------------------------------------------------------------------- #
# Fetch                                                                  #
# --------------------------------------------------------------------- #


async def fetch_trades(bot_manager: Any, since_ts: float) -> list[dict]:
    """Pull normalized trade rows for every active (exchange, symbol).

    One delegate, no second fetcher. Returns newest-first. This is also
    the payload the tab hands the Simulator through ``history_refreshed``.
    """
    return await fetch_all_history_chunked(bot_manager, since_ts)


def sort_trades(trades: list[dict]) -> list[dict]:
    """Return a new list in ``ROW_ORDER``. The fetch already sorts so."""
    return sorted(trades, key=lambda r: r.get("timestamp", 0), reverse=True)


# --------------------------------------------------------------------- #
# Filters                                                                #
# --------------------------------------------------------------------- #


def default_filters(now_ts: Optional[float] = None) -> HistoryFilters:
    """The filter state on open, and the state Reset returns to.

    ``from_ts`` is local midnight on the launch date, not UTC midnight --
    see ``DEFAULT_FROM_LOCAL``.
    """
    if now_ts is None:
        now_ts = time.time()
    return HistoryFilters(
        from_ts=int(datetime(*DEFAULT_FROM_LOCAL).timestamp()),
        to_ts=int(now_ts),
        exchange=ALL,
        symbol=ALL,
        side=ALL,
    )


def filter_options(trades: list[dict]) -> dict:
    """The three dropdown contents, ``(all)`` first.

    Exchange and symbol are the distinct non-empty values present in
    ``trades``, sorted. Side is fixed: the normalizer emits only BUY and
    SELL, so offering the loaded set would hide a side with no trades yet.
    """
    exchanges = sorted({r["exchange"] for r in trades if r.get("exchange")})
    symbols = sorted({r["symbol"] for r in trades if r.get("symbol")})
    return {
        "exchange": [ALL] + exchanges,
        "symbol": [ALL] + symbols,
        "side": [ALL] + list(SIDES),
    }


def apply_filters(trades: list[dict], filters: HistoryFilters) -> list[dict]:
    """Return the retained rows, order preserved.

    A filter at ``(all)`` or a date bound at 0 excludes nothing, so
    widening a filter never drops a row.
    """
    out: list[dict] = []
    for row in trades:
        ts = float(row.get("timestamp", 0) or 0)
        if filters.from_ts > 0 and ts < filters.from_ts:
            continue
        if filters.to_ts > 0 and ts > filters.to_ts:
            continue
        if filters.exchange != ALL and row.get("exchange") != filters.exchange:
            continue
        if filters.symbol != ALL and row.get("symbol") != filters.symbol:
            continue
        if filters.side != ALL and row.get("side") != filters.side:
            continue
        out.append(row)
    return out


# --------------------------------------------------------------------- #
# Paging                                                                 #
# --------------------------------------------------------------------- #


def page_count(total: int) -> int:
    """Pages needed for ``total`` rows. Zero rows is still one page."""
    return max(0, (total - 1) // PAGE_SIZE) + 1


def clamp_page(page: int, total: int) -> int:
    """Pull a page index back inside [0, last]. The tab clamps on render."""
    last = page_count(total) - 1
    if page > last:
        page = last
    if page < 0:
        page = 0
    return page


def page_slice(filtered: list[dict], page: int) -> list[dict]:
    """The rows on ``page``, after clamping. Empty only when nothing
    matched."""
    total = len(filtered)
    page = clamp_page(page, total)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    return filtered[start:end]


def page_label(page: int, total: int) -> str:
    """The footer's page counter, or "No matches" when nothing is
    retained."""
    if total == 0:
        return "No matches"
    page = clamp_page(page, total)
    return f"Page {page + 1} / {page_count(total)} ({total} trades)"


def summary_line(
    filtered: list[dict],
    loaded: int,
    last_fetched_ts: float = 0.0,
    now_ts: Optional[float] = None,
) -> str:
    """The line above the table: retained of loaded, both sides, fetch age.

    The two dollar totals sum the same recomputed ``cost`` the Cost USD
    column shows, so they inherit that column's defect exactly.
    """
    if now_ts is None:
        now_ts = time.time()
    total = len(filtered)
    if last_fetched_ts > 0:
        fetched_str = f"fetched {int(now_ts - last_fetched_ts)}s ago"
    else:
        fetched_str = "no fetch yet"
    buy_count = sum(1 for r in filtered if r.get("side") == "BUY")
    sell_count = sum(1 for r in filtered if r.get("side") == "SELL")
    buy_usd = sum(r.get("cost", 0) for r in filtered if r.get("side") == "BUY")
    sell_usd = sum(r.get("cost", 0) for r in filtered if r.get("side") == "SELL")
    return (
        f"{total} of {loaded} trades shown · "
        f"BUYs: {buy_count} (${buy_usd:,.2f}) · "
        f"SELLs: {sell_count} (${sell_usd:,.2f}) · "
        f"{fetched_str}"
    )


# --------------------------------------------------------------------- #
# The gate + voting join                                                 #
# --------------------------------------------------------------------- #


def build_join_indexes(page_rows: list[dict]) -> tuple[dict, dict]:
    """The two ``(bot_id, ts // 60)`` indexes this page joins against.

    Fail-soft: a reader that raises yields an empty index, and every
    Gates and Voting cell then reads as no-record. A caller that needs to
    tell a collapsed index from a genuinely empty log must compare the
    bucket totals -- that is what pin ``history.05.006`` does.
    """
    return build_page_gate_index(page_rows), build_page_voting_index(page_rows)


# --------------------------------------------------------------------- #
# Cell builders -- one per column, in table order                        #
# --------------------------------------------------------------------- #


def _timestamp_cell(row: dict) -> HistoryCell:
    stamp = row.get("datetime")
    text = stamp.strftime("%Y-%m-%d %H:%M:%S") if stamp is not None else _EMPTY
    return HistoryCell("timestamp", float(row.get("timestamp", 0) or 0), text)


def _plain_cell(key: str, row: dict, field_name: str) -> HistoryCell:
    raw = str(row.get(field_name, ""))
    return HistoryCell(key, raw, raw)


def _bot_cell(row: dict, bot_manager: Any) -> HistoryCell:
    label = resolve_bot_label(
        bot_manager, str(row.get("exchange", "")), str(row.get("symbol", ""))
    )
    return HistoryCell("bot", label, label)


def _side_cell(row: dict) -> HistoryCell:
    side = str(row.get("side", ""))
    return HistoryCell("side", side, side, _SIDE_COLOR.get(row.get("side")))


def _amount_cell(row: dict) -> HistoryCell:
    amount = row.get("amount", 0)
    return HistoryCell("amount", float(amount or 0), f"{amount:,.8f}")


def _price_cell(row: dict) -> HistoryCell:
    price = row.get("price", 0)
    return HistoryCell("price", float(price or 0), f"${price:,.8f}")


def _cost_cell(row: dict) -> HistoryCell:
    """Serves ``amount * price`` under a dollar sign. See the module
    docstring."""
    cost = row.get("cost", 0)
    return HistoryCell("cost", float(cost or 0), f"${cost:,.4f}")


def _fee_cell(row: dict) -> HistoryCell:
    fee = row.get("fee", 0)
    currency = str(row.get("fee_currency", ""))
    text = f"{fee:,.6f} {currency}" if fee > 0 else _EMPTY
    return HistoryCell("fee", {"amount": float(fee or 0), "currency": currency}, text)


def _trade_id_cell(row: dict) -> HistoryCell:
    """Full id in ``value``, elided past 16 characters in ``text``."""
    tid = str(row.get("id", ""))
    text = tid[:16] + "…" if len(tid) > 16 else tid
    return HistoryCell("trade_id", tid, text)


def grade_row(row_index: int, page_rows: list[dict], row: dict) -> str:
    """The A-to-F letter for one row, graded against its own page.

    THE PAGE IS NEWEST-FIRST, so a LOWER index is a LATER trade. Prior
    prices come from HIGHER indexes and future prices from LOWER ones;
    reading it the other way puts post-trade prices into the reference and
    returns the best grade for one of the worst trades.

    Needs at least three prior same-symbol prices on the page for a
    reference, and returns the em dash without one.
    """
    try:
        from src.trading.trade_grader import (
            PriceContext,
            TradeRecord,
            grade_trade,
        )
    except Exception:
        return _EMPTY
    symbol = str(row.get("symbol", ""))
    side = str(row.get("side", "")).lower()
    price = float(row.get("price", 0) or 0)
    quantity = float(row.get("amount", 0) or 0)
    if price <= 0 or quantity <= 0 or side not in ("buy", "sell"):
        return _EMPTY
    prior_prices: list[float] = []
    future_prices: list[float] = []
    for position, other in enumerate(page_rows):
        if str(other.get("symbol", "")) != symbol:
            continue
        other_price = float(other.get("price", 0) or 0)
        if other_price <= 0:
            continue
        if position < row_index:
            future_prices.append(other_price)
        elif position > row_index:
            prior_prices.append(other_price)
    reference = None
    if len(prior_prices) >= 3:
        import statistics

        reference = statistics.median(prior_prices[:5])
    record = TradeRecord(
        trade_id=str(row.get("id", "")),
        timestamp=row.get("datetime"),
        asset=symbol.split("/")[0] if "/" in symbol else symbol,
        side=side,
        price=price,
        quantity=quantity,
        fee=float(row.get("fee", 0) or 0),
    )
    context = PriceContext(
        ref_price_at_decision=reference,
        future_prices=future_prices[-10:],
        regime_tag="LIVE",
    )
    return grade_trade(record, context).overall


def _grade_cell(row_index: int, page_rows: list[dict], row: dict) -> HistoryCell:
    grade = grade_row(row_index, page_rows, row)
    return HistoryCell(
        "grade",
        grade,
        grade,
        _GRADE_COLOR.get(grade[:1]) if grade else None,
        grade_tooltip(grade),
    )


def _gate_color(text: str) -> Optional[str]:
    has_scrum = "S" in text
    has_fold = "F" in text
    if has_scrum and has_fold:
        return _GATE_MIXED_COLOR
    if has_scrum:
        return _GATE_ARMED_COLOR
    if has_fold:
        return _GATE_BLOCKED_COLOR
    return None


def _gate_lights(entry: Optional[dict]) -> Optional[dict]:
    """The five inputs the Simulator's gate-light cell draws from, plus
    the nineteen resolved lights.

    Present only when a gate record joined. A client that drew nineteen
    grey lights for a row with no record would say "evaluated, nothing
    fired" about a row nothing was recorded for.

    ``lights`` is ``src.trading.gate_vocabulary.gate_light_row``, the
    same rule the Simulator's ``GateLightsCell`` paints from. A client
    that re-derived a light colour from the four raw fields would be a
    second implementation of the gate map.
    """
    if not entry:
        return None
    data = entry.get("data") or {}
    scrum_armed = bool(data.get("scrum_armed"))
    fold_armed = bool(data.get("fold_armed"))
    scrum_blockers = list(data.get("scrum_blockers") or [])
    fold_blockers = list(data.get("fold_blockers") or [])
    landing_strip_side = data.get("landing_strip_side")
    return {
        "scrum_armed": scrum_armed,
        "fold_armed": fold_armed,
        "scrum_blockers": scrum_blockers,
        "fold_blockers": fold_blockers,
        "landing_strip_side": landing_strip_side,
        "lights": gate_light_row(
            scrum_armed,
            fold_armed,
            scrum_blockers,
            fold_blockers,
            str(landing_strip_side or ""),
        ),
    }


def _gates_cell(row: dict, bot_id: str, gate_index: dict) -> tuple[HistoryCell, Any]:
    ts = float(row.get("timestamp", 0) or 0)
    entry = lookup_gate_entry(gate_index, bot_id, ts)
    text = gate_cell_text(entry)
    cell = HistoryCell(
        "gates",
        _gate_lights(entry),
        text,
        _gate_color(text),
        gate_cell_tooltip(entry),
    )
    return cell, entry


def _voting_color(text: str) -> Optional[str]:
    upper = text.upper()
    if "BUY" in upper or upper.startswith("B "):
        return _VOTE_BUY_COLOR
    if "SELL" in upper or upper.startswith("S "):
        return _VOTE_SELL_COLOR
    return None


def _voting_cell(row: dict, bot_id: str, voting_index: dict) -> HistoryCell:
    ts = float(row.get("timestamp", 0) or 0)
    entry = lookup_voting_entry(
        voting_index, bot_id, ts, str(row.get("side", "") or "")
    )
    text = voting_cell_text(entry)
    panel = (entry.get("data") or {}).get("panel") if entry else None
    return HistoryCell(
        "voting",
        panel,
        text,
        _voting_color(text),
        voting_cell_tooltip(entry),
    )


def build_row(
    row_index: int,
    page_rows: list[dict],
    row: dict,
    bot_manager: Any = None,
    gate_index: Optional[dict] = None,
    voting_index: Optional[dict] = None,
) -> HistoryRow:
    """The thirteen cells for one trade, in table order.

    ``row_index`` is the row's position within ``page_rows``, not within
    the filtered set: the grade reads its reference prices off this page.
    """
    gate_index = gate_index if gate_index is not None else {}
    voting_index = voting_index if voting_index is not None else {}
    bot_id = resolve_bot_id_for_row(bot_manager, row)
    gates_cell, gate_entry = _gates_cell(row, bot_id, gate_index)
    cells = [
        _timestamp_cell(row),
        _plain_cell("exchange", row, "exchange"),
        _plain_cell("symbol", row, "symbol"),
        _bot_cell(row, bot_manager),
        _side_cell(row),
        _amount_cell(row),
        _price_cell(row),
        _cost_cell(row),
        _fee_cell(row),
        _trade_id_cell(row),
        _grade_cell(row_index, page_rows, row),
        gates_cell,
        _voting_cell(row, bot_id, voting_index),
    ]
    return HistoryRow(
        trade_id=str(row.get("id", "")),
        timestamp=float(row.get("timestamp", 0) or 0),
        cells=cells,
        gate_lights=_gate_lights(gate_entry),
    )


def build_page(
    filtered: list[dict],
    page: int = 0,
    bot_manager: Any = None,
    gate_index: Optional[dict] = None,
    voting_index: Optional[dict] = None,
) -> HistoryPage:
    """One rendered page: the rows plus the footer's pager state.

    Builds the join indexes for the page when none are supplied, which is
    the only disk read on this path.
    """
    total = len(filtered)
    page = clamp_page(page, total)
    rows_in = page_slice(filtered, page)
    if gate_index is None and voting_index is None:
        gate_index, voting_index = build_join_indexes(rows_in)
    pages = page_count(total)
    rows = [
        build_row(i, rows_in, r, bot_manager, gate_index, voting_index)
        for i, r in enumerate(rows_in)
    ]
    return HistoryPage(
        rows=rows,
        page=page,
        pages=pages,
        total=total,
        page_size=PAGE_SIZE,
        page_label=page_label(page, total),
        prev_enabled=page > 0,
        next_enabled=page < pages - 1,
    )


# --------------------------------------------------------------------- #
# CSV export -- the rows, not the file                                   #
# --------------------------------------------------------------------- #

CSV_HEADER: tuple[str, ...] = (
    "timestamp_utc",
    "exchange",
    "symbol",
    "bot",
    "side",
    "amount",
    "price",
    "cost_usd",
    "fee",
    "fee_currency",
    "trade_id",
)
"""Eleven columns, not thirteen: the export carries ``fee_currency`` as
its own field and carries no Grade, Gates or Voting."""


def csv_rows(filtered: list[dict], bot_manager: Any = None) -> list[list[str]]:
    """Every retained row as the strings the export writes.

    Returns rows; writes no file. The numbers here carry no thousands
    separator and a missing instant is the empty string, both unlike the
    table's own formatting.
    """
    out: list[list[str]] = []
    for row in filtered:
        stamp = row.get("datetime")
        ts_str = stamp.strftime("%Y-%m-%d %H:%M:%S") if stamp is not None else ""
        out.append(
            [
                ts_str,
                str(row.get("exchange", "")),
                str(row.get("symbol", "")),
                resolve_bot_label(
                    bot_manager,
                    str(row.get("exchange", "")),
                    str(row.get("symbol", "")),
                ),
                str(row.get("side", "")),
                f"{row.get('amount', 0):.8f}",
                f"{row.get('price', 0):.8f}",
                f"{row.get('cost', 0):.4f}",
                f"{row.get('fee', 0):.6f}",
                str(row.get("fee_currency", "")),
                str(row.get("id", "")),
            ]
        )
    return out


__all__ = [
    "ALL",
    "COLUMNS",
    "COLUMN_KEYS",
    "CSV_HEADER",
    "DEFAULT_FROM_LOCAL",
    "FETCH_POLL_INTERVAL_S",
    "FETCH_TIMEOUT_S",
    "PAGE_SIZE",
    "ROW_ORDER",
    "SIDES",
    "STATUS_TEXT",
    "HistoryCell",
    "HistoryColumn",
    "HistoryFilters",
    "HistoryPage",
    "HistoryRow",
    "apply_filters",
    "build_join_indexes",
    "build_page",
    "build_row",
    "clamp_page",
    "csv_rows",
    "default_filters",
    "fetch_trades",
    "filter_options",
    "grade_row",
    "page_count",
    "page_label",
    "page_slice",
    "sort_trades",
    "summary_line",
]
