"""Read-only ``HistoryPage`` values for the History tab.

``build_page`` returns ``HistoryRow`` records as ``str``, ``int``, ``float``,
``bool``, ``None``, ``list`` and ``dict``; no Qt type and no ``datetime``
object crosses the boundary. Each of the thirteen ``COLUMNS`` yields one
``HistoryCell`` carrying ``value``, ``text``, ``color`` and ``tooltip``.
``ROW_ORDER`` is the whole ordering contract, and nothing here writes or
emits.
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

PAGE_SIZE = 100
"""Rows per page, the same 100 ``HistoryTab.PAGE_SIZE`` holds."""

ALL = "(all)"
"""The sentinel at index 0 of every ``filter_options`` list. No exchange,
symbol or side is ever named ``(all)``."""

SIDES = ("BUY", "SELL")
"""The only two sides ``history_helpers`` normalizes a raw side to."""

ROW_ORDER = "timestamp_desc"
"""Newest first. ``fetch_all_history_chunked`` sorts ``reverse=True``,
``HistoryTab`` calls no ``setSortingEnabled``, and nothing re-sorts."""

DEFAULT_FROM_LOCAL = (2026, 4, 1, 0, 0, 0)
"""The From date the tab opens and resets to, as LOCAL wall-clock parts.

``HistoryTab`` builds ``QDateTime(QDate(2026, 4, 1), QTime(0, 0, 0))`` with
no timezone and reads it back with ``toSecsSinceEpoch()``, which Qt takes as
local time. ``history_helpers.DEFAULT_START_DATE`` is the same wall clock in
UTC and a different instant everywhere but UTC."""

FETCH_POLL_INTERVAL_S = 0.4
"""``HistoryTab`` polls the fetch future on a 400 ms timer, so an observed
fetch latency is the true latency plus up to one interval."""

FETCH_TIMEOUT_S = 60.0
"""``HistoryTab`` abandons a fetch after 60 s."""

STATUS_TEXT = {
    "idle": "No history loaded yet — click Refresh.",
    "no_bot_manager": "Bot manager unavailable — cannot fetch history.",
    "no_async_loop": "Async loop not ready — try again after platform starts.",
    "fetching": "Fetching trade history from exchanges…",
    "timeout": "Fetch timeout (60s). Exchange may be rate-limited; try again.",
}
"""The five fixed status strings shown before any row exists. The two
variable ones are ``Schedule failed: {exc}`` and
``Fetch raised: {type}: {exc}``."""

PAGE_LABEL_IDLE = "Page —"
"""The page counter before a page is drawn, ahead of any ``page_label`` call."""

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
"""The one-character em dash rendered for an absent value. ``gate_cell_text``
returns the words "no record" and never this."""


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
    """Thirteen ``HistoryCell`` records plus ``trade_id`` and ``gate_lights``."""

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
    """One page of ``HistoryRow`` records plus the pager state for the footer."""

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


async def fetch_trades(bot_manager: Any, since_ts: float) -> list[dict]:
    """Pull normalized trade rows for every active (exchange, symbol).

    ``fetch_all_history_chunked`` returns them newest-first, and
    ``HistoryTab`` re-emits the same list on ``history_refreshed``.
    """
    return await fetch_all_history_chunked(bot_manager, since_ts)


def sort_trades(trades: list[dict]) -> list[dict]:
    """Return a new list in ``ROW_ORDER``; ``fetch_trades`` already sorts so."""
    return sorted(trades, key=lambda r: r.get("timestamp", 0), reverse=True)


def default_filters(now_ts: Optional[float] = None) -> HistoryFilters:
    """The filter state on open, and the state Reset returns to.

    ``from_ts`` is ``DEFAULT_FROM_LOCAL`` as a local instant, not UTC midnight.
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
    """The three dropdown contents, ``ALL`` first.

    Exchange and symbol are the distinct non-empty values in ``trades``,
    sorted; side is always the fixed ``SIDES`` pair.
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

    A filter at ``ALL`` or a date bound at 0 excludes nothing.
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


def page_count(total: int) -> int:
    """Pages of ``PAGE_SIZE`` needed for ``total`` rows; zero rows is one."""
    return max(0, (total - 1) // PAGE_SIZE) + 1


def clamp_page(page: int, total: int) -> int:
    """Pull ``page`` back inside 0 to ``page_count`` minus one."""
    last = page_count(total) - 1
    if page > last:
        page = last
    if page < 0:
        page = 0
    return page


def page_slice(filtered: list[dict], page: int) -> list[dict]:
    """The ``filtered`` rows on ``page``, after ``clamp_page``."""
    total = len(filtered)
    page = clamp_page(page, total)
    start = page * PAGE_SIZE
    end = min(start + PAGE_SIZE, total)
    return filtered[start:end]


def page_label(page: int, total: int) -> str:
    """The footer's page counter, or "No matches" when ``total`` is zero."""
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

    The two dollar totals sum the same ``cost`` field ``_cost_cell`` renders.
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


def build_join_indexes(page_rows: list[dict]) -> tuple[dict, dict]:
    """The ``(bot_id, ts // 60)`` gate and voting indexes for ``page_rows``.

    ``build_page_gate_index`` and ``build_page_voting_index`` each yield an
    empty dict when their log read raises, and every joined cell then reads
    as no-record.
    """
    return build_page_gate_index(page_rows), build_page_voting_index(page_rows)


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
    """Render the ``cost`` field, which ``history_helpers`` sets to
    ``amount * price``, with a dollar sign for every quote currency."""
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
    """The A-to-F letter ``graded_row`` gives one row, or ``_EMPTY`` for none."""
    grade = graded_row(row_index, page_rows, row)
    return _EMPTY if grade is None else grade.overall


def graded_row(row_index: int, page_rows: list[dict], row: dict):
    """The whole ``TradeGrade`` for one row, graded against ``page_rows``.

    ``page_rows`` is newest-first, so ``prior_prices`` come from indexes above
    ``row_index``; None comes back only for an unusable ``price``, ``amount`` or
    ``side``, never for a missing ``reference``.
    """
    try:
        from src.trading.trade_grader import (
            PriceContext,
            TradeRecord,
            grade_trade,
        )
    except Exception:
        return None
    symbol = str(row.get("symbol", ""))
    side = str(row.get("side", "")).lower()
    price = float(row.get("price", 0) or 0)
    quantity = float(row.get("amount", 0) or 0)
    if price <= 0 or quantity <= 0 or side not in ("buy", "sell"):
        return None
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
    return grade_trade(record, context)


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
    """The five raw gate fields plus the nineteen ``gate_light_row`` lights.

    A falsy ``entry`` returns None, never a row of nineteen unlit lights.
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

    ``row_index`` is the position within ``page_rows``, not within the
    filtered set, and ``grade_row`` reads its reference prices off that page.
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
    """One rendered page: the ``HistoryRow`` list plus the pager state.

    ``build_join_indexes`` runs when neither index is supplied, and it is the
    only disk read on this path.
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
"""Eleven columns against the thirteen ``COLUMNS``: the export carries
``fee_currency`` as its own field and no Grade, Gates or Voting."""


def csv_rows(filtered: list[dict], bot_manager: Any = None) -> list[list[str]]:
    """Every row of ``filtered`` as the strings the export writes.

    ``csv_rows`` writes no file, its numbers carry no thousands separator,
    and a missing instant is the empty string.
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
    "PAGE_LABEL_IDLE",
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
