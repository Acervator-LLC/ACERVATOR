"""History tab: fetches exchange trade rows, filters, pages and exports them."""

from __future__ import annotations

import asyncio
import contextlib
import csv
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Generator, Optional

from src.core.trade_historian import missing_history_line
from src.exchange import history_read_contract as hrc
from src.gui.main_tabs import history_tab_surface as hts

from . import design_system as ds
from .main_tabs import class_filter_surface

try:
    from PySide6.QtCore import QDateTime, Qt, QTimer, Signal
    from PySide6.QtWidgets import (
        QComboBox,
        QDateTimeEdit,
        QFileDialog,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMessageBox,
        QProgressBar,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    from .tooltips import set_description

    _HAS_QT = True
except ImportError:
    _HAS_QT = False

logger = logging.getLogger("acervator.gui.history")


def _resolve_bot_label(bot_manager, exchange_id: str, symbol: str) -> str:
    """Return the 'TICKER/last4' label of the bot whose symbol matches."""
    del exchange_id
    if bot_manager is None:
        return ""
    try:
        bots = list(getattr(bot_manager, "_bots", {}).values())
    except Exception:
        return ""
    for bot in bots:
        try:
            cfg = getattr(bot, "config", None)
            if cfg is None:
                continue
            if str(getattr(cfg, "symbol", "")) != symbol:
                continue
            bot_id = str(getattr(bot, "bot_id", "") or "")
            ticker = str(getattr(cfg, "target_asset", "") or "")
            if not ticker:
                ticker = symbol.split("/")[0] if "/" in symbol else symbol
            return f"{ticker}/{bot_id[-4:]}" if bot_id else ticker
        except Exception as _bot_exc:  # noqa: BLE001
            logger.debug("history_tab bot-label lookup skipped one bot: %s", _bot_exc)
            continue
    return ""


def _parse_iso_ts(s: str) -> Optional[float]:
    """Parse an ISO-8601 timestamp into unix seconds, or None when unreadable."""
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except (ValueError, TypeError):
        return None


def _entry_bucket_key(entry: dict) -> Optional[tuple]:
    """The ``(bot_id, minute)`` key of one log entry, or None when unreadable."""
    bot_id = str(entry.get("bot_id", "") or "")
    if not bot_id:
        return None
    ts = _parse_iso_ts(entry.get("timestamp", ""))
    if ts is None:
        return None
    return (bot_id, int(ts) // 60)


def join_bucket_keys(rows: list, bot_manager) -> set:
    """The ``(bot_id, minute)`` keys the gate and voting lookups can reach.

    ``lookup_gate_entry`` reads a row's own minute and the two beside it, so an
    index holding only these keys answers every lookup identically.
    """
    from src.exchange.history_helpers import resolve_bot_id_for_row

    keys: set = set()
    bot_ids: dict = {}
    for row in rows:
        ts = float(row.get("timestamp", 0) or 0)
        if ts <= 0:
            continue
        row_identity = (
            str(row.get("bot_id", "") or ""),
            str(row.get("symbol", "") or ""),
        )
        bot_id = bot_ids.get(row_identity)
        if bot_id is None:
            bot_id = resolve_bot_id_for_row(bot_manager, row)
            bot_ids[row_identity] = bot_id
        if not bot_id:
            continue
        minute = int(ts) // 60
        keys.add((bot_id, minute - 1))
        keys.add((bot_id, minute))
        keys.add((bot_id, minute + 1))
    return keys


#: Seconds one step of ``read_join_indexes`` reads log entries before it yields.
JOIN_STEP_S = 0.008

#: Rows one step of ``join_steps``, ``landing_steps`` or ``view_steps`` reads.
STEP_ROWS = 1000

#: Rows one step of ``HistoryTab._page_steps`` builds.
RENDER_STEP_ROWS = 25


def read_join_indexes(
    since, wanted_keys: set
) -> Generator[None, None, tuple[dict, dict, int]]:
    """The gate and voting indexes from ``since``, holding only ``wanted_keys``,
    each entry kept as its JSON text, ``JOIN_STEP_S`` of reading a step.

    Answers the two indexes and the entries kept; a raising read empties that
    side's index while the count stands, so a caller can see the loss.
    """
    from src.trading.live_log_reader import (
        live_gate_decisions,
        live_voting_panel_snapshots,
    )

    gate_index: dict = {}
    voting_index: dict = {}
    kept = 0
    began = time.monotonic()
    try:
        for entry in live_gate_decisions(since=since, validate=False):
            key = _entry_bucket_key(entry)
            if key is not None and key in wanted_keys:
                gate_index.setdefault(key, []).append(json.dumps(entry))
                kept += 1
            if time.monotonic() - began >= JOIN_STEP_S:
                yield
                began = time.monotonic()
    except Exception as _gate_exc:  # noqa: BLE001 - a torn log read
        logger.debug("history: gate index read fail-soft: %s", _gate_exc)
        gate_index = {}
    try:
        for entry in live_voting_panel_snapshots(since=since):
            key = _entry_bucket_key(entry)
            if key is not None and key in wanted_keys:
                voting_index.setdefault(key, []).append(json.dumps(entry))
                kept += 1
            if time.monotonic() - began >= JOIN_STEP_S:
                yield
                began = time.monotonic()
    except Exception as _vote_exc:  # noqa: BLE001 - a torn log read
        logger.debug("history: voting index read fail-soft: %s", _vote_exc)
        voting_index = {}
    return (
        {key: tuple(held) for key, held in gate_index.items()},
        {key: tuple(held) for key, held in voting_index.items()},
        kept,
    )


def join_since(rows: list) -> Optional[datetime]:
    """The read's lower bound: the earliest row less the join tolerance."""
    from src.exchange.history_helpers import JOIN_TOLERANCE_SECONDS

    stamps = [
        float(r.get("timestamp", 0) or 0) for r in rows if (r.get("timestamp") or 0) > 0
    ]
    if not stamps:
        return None
    return datetime.fromtimestamp(
        max(0.0, min(stamps) - JOIN_TOLERANCE_SECONDS), tz=timezone.utc
    )


def join_steps(rows: list, bot_manager) -> Generator[None, None, dict]:
    """``read_join_indexes`` for the keys ``rows`` can reach, the keys built
    ``STEP_ROWS`` rows a step."""
    began = time.monotonic()
    wanted: set = set()
    for start in range(0, len(rows), STEP_ROWS):
        wanted |= join_bucket_keys(rows[start : start + STEP_ROWS], bot_manager)
        yield
    gate, voting, kept = yield from read_join_indexes(join_since(rows), wanted)
    return {
        "gate": gate,
        "voting": voting,
        "kept": kept,
        "rows": len(rows),
        "seconds": time.monotonic() - began,
    }


def page_join_indexes(
    rows: list, bot_manager, gate_text: dict, voting_text: dict
) -> tuple[dict, dict]:
    """The gate and voting entries ``rows`` can reach, parsed from the JSON text
    ``read_join_indexes`` holds."""
    keys = join_bucket_keys(rows, bot_manager)
    return (
        {
            key: [json.loads(t) for t in gate_text[key]]
            for key in keys & gate_text.keys()
        },
        {
            key: [json.loads(t) for t in voting_text[key]]
            for key in keys & voting_text.keys()
        },
    )


def admissible_rows(rows: list, since_ts: float, seen: set) -> int:
    """How many of ``rows`` are not stamped before ``since_ts`` and carry an id
    whose ``(exchange, symbol, id)`` ``seen`` lacks; ``seen`` takes each triple."""
    admissible = 0
    for row in rows:
        key = (row.get("exchange"), row.get("symbol"), row.get("id"))
        dupe = key in seen
        seen.add(key)
        stamp = float(row.get("timestamp", 0) or 0)
        if dupe or not row.get("id"):
            continue
        if 0 < stamp < since_ts:
            continue
        admissible += 1
    return admissible


def landing_steps(rows: list, since_ts: float) -> Generator[None, None, dict]:
    """The pickers' ``hrc.filter_options`` and the ``admissible_rows`` count of
    ``rows``, one ``STEP_ROWS`` slice a step."""
    began = time.monotonic()
    options = hrc.filter_options(rows)
    options_s = time.monotonic() - began
    yield
    seen: set = set()
    admissible = 0
    for start in range(0, len(rows), STEP_ROWS):
        admissible += admissible_rows(rows[start : start + STEP_ROWS], since_ts, seen)
        yield
    return {
        "admissible": admissible,
        "distinct": len(seen),
        "options": options,
        "options_s": options_s,
    }


def refused_rows(rows: list, from_ts: int, verify: hrc.HistoryFilters) -> int:
    """How many of ``rows`` ``from_ts`` or the read-back ``verify`` refuses."""
    refused = 0
    for row in rows:
        stamp = float(row.get("timestamp", 0) or 0)
        if from_ts > 0 and stamp < from_ts:
            refused += 1
        elif verify.to_ts > 0 and stamp > verify.to_ts:
            refused += 1
        elif verify.exchange != hrc.ALL and row.get("exchange") != verify.exchange:
            refused += 1
        elif verify.symbol != hrc.ALL and row.get("symbol") != verify.symbol:
            refused += 1
        elif verify.side != hrc.ALL and row.get("side") != verify.side:
            refused += 1
    return refused


@dataclass(frozen=True)
class HistoryView:
    """The rows ``predicate`` keeps, filed by asset class, with each class's
    ``SummaryTotals`` and the rows ``verify`` refuses."""

    kept: dict
    totals: dict
    refused: dict
    predicate: hrc.HistoryFilters
    verify: hrc.HistoryFilters
    seconds: float

    def rows_of(self, key: str) -> list:
        """The kept rows of asset class ``key``, in the order ``view_steps``
        read them."""
        return self.kept.get(key, [])

    def totals_of(self, key: str) -> hrc.SummaryTotals:
        """The ``SummaryTotals`` of ``rows_of(key)``."""
        return self.totals.get(key, hrc.SummaryTotals())


def view_steps(
    rows: list, predicate: hrc.HistoryFilters, verify: hrc.HistoryFilters
) -> Generator[None, None, HistoryView]:
    """The ``HistoryView`` of ``rows`` under ``predicate``, its refusals read
    against ``verify``, one ``STEP_ROWS`` slice a step."""
    seconds = 0.0
    matched: list = []
    for start in range(0, len(rows), STEP_ROWS):
        began = time.monotonic()
        matched.extend(hrc.apply_filters(rows[start : start + STEP_ROWS], predicate))
        seconds += time.monotonic() - began
        yield
    answered: dict = {}
    kept: dict = {}
    for start in range(0, len(matched), STEP_ROWS):
        began = time.monotonic()
        part = matched[start : start + STEP_ROWS]
        for key, held in class_filter_surface.trades_by_class(part, answered).items():
            kept.setdefault(key, []).extend(held)
        seconds += time.monotonic() - began
        yield
    totals: dict = {}
    refused: dict = {}
    for key, held in kept.items():
        totals[key] = hrc.summary_totals(held)
        yield
        refused[key] = 0
        for start in range(0, len(held), STEP_ROWS):
            part = held[start : start + STEP_ROWS]
            refused[key] += refused_rows(part, predicate.from_ts, verify)
            yield
    return HistoryView(
        kept=kept,
        totals=totals,
        refused=refused,
        predicate=predicate,
        verify=verify,
        seconds=seconds,
    )


if _HAS_QT:

    class HistoryTab(QWidget):
        """Fetches exchange trade history, filters it, pages it and exports CSV."""

        PAGE_SIZE = 100

        history_refreshed = Signal(object)

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self.setAccessibleName("History Tab")
            self._bot_manager = None
            self._all_trades: list[dict] = []
            self._filtered: list[dict] = []
            self._filtered_totals = hrc.SummaryTotals()
            self._view: Optional[HistoryView] = None
            self._view_options: dict = hrc.filter_options([])
            self._view_build_id: int = 0
            self._landing_build_id: int = 0
            self._asset_class = class_filter_surface.active()
            self._page = 0
            self._fetch_in_flight = False
            self._last_fetched_ts: float = 0.0
            self._page_gate_index: dict = {}
            self._page_voting_index: dict = {}
            self._rows_version: int = 0
            self._join_version: int = 0
            self._page_cache: Optional[tuple] = None
            self._render_build_id: int = 0
            self._drawn_render_id: int = 0
            self._step_chains: list[tuple] = []
            self._drive_due = False
            self._join_build_id: int = 0
            self._join_due = False
            self._to_default_ts: int = 0
            # The historian calls back off its own thread, so the two sets
            # are read and written under _history_lock.
            self._history_lock = threading.Lock()
            self._history_scanned: set[str] = set()
            self._history_refused: set[str] = set()
            self._build_ui()

        def set_bot_manager(self, bot_manager) -> None:
            self._bot_manager = bot_manager

        def set_asset_class(self, name) -> tuple:
            """Hold ``name`` as the class this table shows, drawn from the held
            ``HistoryView`` when the class moves.

            Answers the rows kept for ``name`` and the rows ``_all_trades`` holds.
            """
            key = class_filter_surface.normalise(name)
            moved = key != self._asset_class
            self._asset_class = key
            if self._view is not None:
                if moved:
                    self._show_view()
            elif not self._all_trades:
                self._hold_rows([], hrc.SummaryTotals())
            return (len(self._filtered), len(self._all_trades))

        def refresh(self) -> None:
            """Start an async trade fetch and re-render when it lands."""
            self._kick_async_fetch()

        def get_history_callback(self):
            """Return the callable the connector calls as ``(symbol, analysis)``."""
            return self._record_history_scan

        def _record_history_scan(self, symbol, analysis, *_a, **_kw) -> None:
            """Record one scan result into ``_history_scanned`` and
            ``_history_refused``.

            A truthy ``analysis.analysis_error`` marks ``symbol`` refused.
            """
            name = str(symbol)
            refused = bool(getattr(analysis, "analysis_error", "") or "")
            with self._history_lock:
                self._history_scanned.add(name)
                if refused:
                    self._history_refused.add(name)
                else:
                    self._history_refused.discard(name)

        def missing_history_status(self) -> str:
            """``missing_history_line`` for the refused symbols, else empty."""
            with self._history_lock:
                refused = len(self._history_refused)
                scanned = len(self._history_scanned)
            if not refused:
                return ""
            return missing_history_line(refused, scanned)

        def _build_ui(self) -> None:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(8, 8, 8, 8)
            outer.setSpacing(6)

            filt = QGroupBox("Filters")
            fl = QHBoxLayout(filt)
            fl.setContentsMargins(8, 6, 8, 6)

            # Local-time QDateTime so _default_from reads 2026-04-01 00:00 anywhere.
            from PySide6.QtCore import QDate, QTime

            fl.addWidget(QLabel("From:"))
            _default_from = QDateTime(QDate(2026, 4, 1), QTime(0, 0, 0))
            self._from_dt = QDateTimeEdit(_default_from)
            self._from_dt.setCalendarPopup(True)
            self._from_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
            self._from_dt.setMinimumWidth(150)
            set_description(self._from_dt, hts.FROM_TOOLTIP)
            fl.addWidget(self._from_dt)

            fl.addWidget(QLabel("To:"))
            self._to_dt = QDateTimeEdit(QDateTime.currentDateTime())
            self._to_dt.setCalendarPopup(True)
            self._to_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
            self._to_dt.setMinimumWidth(150)
            set_description(self._to_dt, hts.TO_TOOLTIP)
            self._remember_to_bound()
            fl.addWidget(self._to_dt)

            fl.addWidget(QLabel("Exchange:"))
            self._exch_combo = QComboBox()
            self._exch_combo.addItem("(all)")
            self._exch_combo.setMinimumWidth(120)
            set_description(self._exch_combo, hts.EXCHANGE_TOOLTIP)
            fl.addWidget(self._exch_combo)

            fl.addWidget(QLabel("Symbol:"))
            self._sym_combo = QComboBox()
            self._sym_combo.addItem("(all)")
            self._sym_combo.setMinimumWidth(120)
            set_description(self._sym_combo, hts.SYMBOL_TOOLTIP)
            fl.addWidget(self._sym_combo)

            fl.addWidget(QLabel("Side:"))
            self._side_combo = QComboBox()
            self._side_combo.addItems(["(all)", "BUY", "SELL"])
            set_description(self._side_combo, hts.SIDE_TOOLTIP)
            fl.addWidget(self._side_combo)

            fl.addStretch(1)

            self._apply_btn = QPushButton("Apply")
            set_description(self._apply_btn, hts.APPLY_TOOLTIP)
            self._apply_btn.clicked.connect(self._apply_filters)
            fl.addWidget(self._apply_btn)

            self._reset_btn = QPushButton("Reset")
            set_description(self._reset_btn, hts.RESET_TOOLTIP)
            self._reset_btn.clicked.connect(self._reset_filters)
            fl.addWidget(self._reset_btn)

            self._refresh_btn = QPushButton("Refresh")
            set_description(self._refresh_btn, hts.REFRESH_TOOLTIP)
            self._refresh_btn.clicked.connect(self.refresh)
            fl.addWidget(self._refresh_btn)

            outer.addWidget(filt)

            self._summary = QLabel(hrc.STATUS_TEXT["idle"])
            self._summary.setStyleSheet(f"color: {ds.TEXT_INACTIVE}; padding: 2px 6px;")
            outer.addWidget(self._summary)

            from .history_table_variant import history_table_class

            self._table = history_table_class()(self)
            outer.addWidget(self._table, stretch=1)

            foot = QHBoxLayout()
            foot.setContentsMargins(0, 0, 0, 0)

            self._prev_btn = QPushButton("◀ Prev")
            set_description(self._prev_btn, hts.PREV_TOOLTIP)
            self._prev_btn.clicked.connect(self._prev_page)
            foot.addWidget(self._prev_btn)

            self._page_label = QLabel(hrc.PAGE_LABEL_IDLE)
            self._page_label.setMinimumWidth(120)
            self._page_label.setAlignment(Qt.AlignCenter)
            foot.addWidget(self._page_label)

            self._next_btn = QPushButton("Next ▶")
            set_description(self._next_btn, hts.NEXT_TOOLTIP)
            self._next_btn.clicked.connect(self._next_page)
            foot.addWidget(self._next_btn)

            foot.addStretch(1)

            self._progress = QProgressBar()
            self._progress.setMaximumWidth(150)
            self._progress.setRange(0, 0)  # busy indeterminate
            self._progress.setVisible(False)
            foot.addWidget(self._progress)

            self._export_btn = QPushButton("Export CSV…")
            set_description(self._export_btn, hts.EXPORT_TOOLTIP)
            self._export_btn.clicked.connect(self._export_csv)
            foot.addWidget(self._export_btn)

            outer.addLayout(foot)

        # A variant that draws this tab another way overrides these and
        # inherits the fetch, filter, page and export behaviour unchanged.

        def _since_ts(self) -> float:
            """The From bound in unix seconds, or thirty days back."""
            try:
                return self._from_dt.dateTime().toSecsSinceEpoch()
            except Exception as _from_exc:  # noqa: BLE001 - a torn-down date edit
                logger.debug("history: From bound not readable: %s", _from_exc)
                return time.time() - 30 * 86400

        def _set_status(self, text: str) -> None:
            """Write ``text`` into the line above the table."""
            self._summary.setText(text)

        def _set_fetching(self, fetching: bool) -> None:
            """Show the busy bar and refuse Refresh while a fetch is in flight."""
            self._fetch_in_flight = fetching
            self._progress.setVisible(fetching)
            self._refresh_btn.setEnabled(not fetching)

        def _filter_options(self) -> dict:
            """The exchange and symbol values the filter bar offers now."""
            return {
                "exchange": {
                    self._exch_combo.itemText(i)
                    for i in range(self._exch_combo.count())
                }
                - {"(all)"},
                "symbol": {
                    self._sym_combo.itemText(i) for i in range(self._sym_combo.count())
                }
                - {"(all)"},
            }

        def _set_filter_options(self, exchanges: list, symbols: list) -> None:
            """Refill the two choice lists, keeping the current selection."""
            for combo, values in (
                (self._exch_combo, exchanges),
                (self._sym_combo, symbols),
            ):
                chosen = combo.currentText()
                combo.blockSignals(True)
                combo.clear()
                combo.addItem("(all)")
                for value in values:
                    combo.addItem(value)
                index = combo.findText(chosen)
                if index >= 0:
                    combo.setCurrentIndex(index)
                combo.blockSignals(False)

        def _reset_filter_values(self) -> None:
            """Return the five filters to the values the tab opens on."""
            from PySide6.QtCore import QDate, QTime

            self._from_dt.setDateTime(QDateTime(QDate(2026, 4, 1), QTime(0, 0, 0)))
            self._to_dt.setDateTime(QDateTime.currentDateTime())
            self._remember_to_bound()
            self._exch_combo.setCurrentIndex(0)
            self._sym_combo.setCurrentIndex(0)
            self._side_combo.setCurrentIndex(0)

        def _build_model(self, rendered: Optional[hrc.HistoryPage] = None) -> dict:
            """The payload the table draws for ``rendered``, by default the
            ``_current_page``."""
            from .react_history_panel import TABLE_ONLY_CHROME, build_view_model

            return build_view_model(
                self._all_trades,
                self._current_filters(),
                self._page,
                self._bot_manager,
                last_fetched_ts=self._last_fetched_ts,
                filtered=self._filtered,
                chrome=TABLE_ONLY_CHROME,
                totals=self._filtered_totals,
                options=self._view_options,
                rendered=self._current_page() if rendered is None else rendered,
            )

        def _page_key(self) -> tuple:
            """The ``_rows_version``, clamped page number and ``_join_version``
            the page ``_page`` names is built from."""
            return (
                self._rows_version,
                hrc.clamp_page(self._page, len(self._filtered)),
                self._join_version,
            )

        def _cached_page(self, key: tuple) -> Optional[hrc.HistoryPage]:
            """The page ``_draw_page`` last drew when it was built from ``key``."""
            held = self._page_cache
            if held is not None and held[0] == key:
                return held[1]
            return None

        def _current_page(self) -> hrc.HistoryPage:
            """The page ``_page`` names: the ``_cached_page``, else built in one
            turn."""
            key = self._page_key()
            held = self._cached_page(key)
            if held is not None:
                return held
            gate_index, voting_index = page_join_indexes(
                hrc.page_slice(self._filtered, key[1]),
                self._bot_manager,
                self._page_gate_index,
                self._page_voting_index,
            )
            return hrc.build_page(
                self._filtered, key[1], self._bot_manager, gate_index, voting_index
            )

        def _paint_chrome(self, total: int, max_page: int) -> None:
            """Write the page counter, the two pager buttons and the summary."""
            self._page_label.setText(hrc.page_label(self._page, total))
            self._prev_btn.setEnabled(self._page > 0)
            self._next_btn.setEnabled(self._page < max_page)
            summary = hrc.summary_text(
                total,
                len(self._all_trades),
                self._filtered_totals,
                self._last_fetched_ts,
            )
            missing = self.missing_history_status()
            self._set_status(f"{summary}  {missing}" if missing else summary)

        def _remember_to_bound(self) -> None:
            """Record the To value the tab itself wrote, read back off the
            widget so any precision Qt drops is recorded as stored."""
            try:
                self._to_default_ts = int(self._to_dt.dateTime().toSecsSinceEpoch())
            except Exception as _to_exc:  # noqa: BLE001 - a torn-down date edit
                logger.debug("history: To bound not readable: %s", _to_exc)
                self._to_default_ts = 0

        def _to_bound_ts(self) -> int:
            """The To bound in unix seconds, advanced to now while untouched.

            An untouched bound means "up to now". Frozen at the instant the
            tab was built it hides every trade the exchange filled after
            that, so the screen disagrees with the venue. A bound the
            operator set is left exactly where they put it.
            """
            try:
                current = int(self._to_dt.dateTime().toSecsSinceEpoch())
            except Exception as _to_exc:  # noqa: BLE001 - a torn-down date edit
                logger.debug("history: To bound not readable: %s", _to_exc)
                return 0
            if current != self._to_default_ts:
                return current
            now = int(time.time())
            if now <= current:
                return current
            self._to_dt.blockSignals(True)
            self._to_dt.setDateTime(QDateTime.fromSecsSinceEpoch(now))
            self._to_dt.blockSignals(False)
            self._remember_to_bound()
            return self._to_default_ts

        def _kick_async_fetch(self) -> None:
            if self._fetch_in_flight:
                return
            if self._bot_manager is None:
                self._set_status(hrc.STATUS_TEXT["no_bot_manager"])
                return
            since_ts = self._since_ts()

            loop = getattr(self._bot_manager, "_async_loop", None)
            if loop is None:
                self._set_status(hrc.STATUS_TEXT["no_async_loop"])
                return

            self._set_fetching(True)
            self._set_status(hrc.STATUS_TEXT["fetching"])

            try:
                from src.exchange.history_helpers import fetch_all_history_chunked

                future = asyncio.run_coroutine_threadsafe(
                    fetch_all_history_chunked(self._bot_manager, since_ts), loop
                )
            except Exception as exc:
                self._set_fetching(False)
                self._set_status(f"Schedule failed: {exc}")
                return

            # Poll the future without blocking the GUI.
            start_ts = time.monotonic()
            poll_timer = QTimer(self)
            poll_timer.setInterval(400)

            def _check():
                try:
                    if future.done():
                        poll_timer.stop()
                        self._set_fetching(False)
                        try:
                            result = future.result(timeout=0.1)
                        except Exception as rx:
                            self._set_status(f"Fetch raised: {type(rx).__name__}: {rx}")
                            logger.warning("history fetch raised: %s", rx)
                            return
                        self._all_trades = list(result or [])
                        self._view = None
                        self._join_due = True
                        _dur_elapsed = time.monotonic() - start_ts
                        self._last_fetched_ts = time.time()
                        if self.history_refreshed is not None:
                            try:
                                self.history_refreshed.emit(list(self._all_trades))
                            except Exception as _sig_exc:  # noqa: BLE001
                                logger.debug(
                                    "history_refreshed emit failed: %s", _sig_exc
                                )
                        self._start_landing_build(since_ts, _dur_elapsed)
                        return
                    if time.monotonic() - start_ts > hrc.FETCH_TIMEOUT_S:
                        poll_timer.stop()
                        self._set_fetching(False)
                        self._set_status(hrc.STATUS_TEXT["timeout"])
                except Exception as exc:
                    poll_timer.stop()
                    self._set_fetching(False)
                    logger.warning("history poll exception: %s", exc)

            poll_timer.timeout.connect(_check)
            poll_timer.start()

        def _populate_filter_options(self, options: dict, options_s: float) -> None:
            """Refill the exchange and symbol choices from ``options``, which
            ``landing_steps`` read off the loaded rows in ``options_s``."""
            _build_t0 = time.monotonic()
            self._view_options = options
            _want_exch = set(options["exchange"][1:])
            _want_sym = set(options["symbol"][1:])
            self._set_filter_options(
                list(options["exchange"][1:]), list(options["symbol"][1:])
            )
            _build_s = options_s + time.monotonic() - _build_t0

            _offered = self._filter_options()
            _have_exch = _offered["exchange"]
            _have_sym = _offered["symbol"]
            _mismatched = len(_want_exch ^ _have_exch) + len(_want_sym ^ _have_sym)
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _hist_emit

                _hist_emit(
                    "history.05.003.postcondition.filter_options_built",
                    actual=_mismatched,
                    expected=0,
                    context={
                        "exchanges_offered": len(_have_exch),
                        "exchanges_loaded": len(_want_exch),
                        "symbols_offered": len(_have_sym),
                        "symbols_loaded": len(_want_sym),
                        "trades_loaded": len(self._all_trades),
                    },
                    duration=_build_s,
                )

        def _apply_filters(self) -> None:
            # Apply with no prior fetch starts one; its poll re-enters here.
            if (
                self._last_fetched_ts == 0
                and not self._fetch_in_flight
                and self._bot_manager is not None
            ):
                logger.info(
                    "history: Apply pressed with no prior fetch; "
                    "kicking implicit fetch"
                )
                self._kick_async_fetch()
                return
            self._start_view_build()

        def _start_landing_build(self, since_ts: float, fetch_s: float) -> None:
            """Run ``landing_steps`` over ``_all_trades``; ``_take_landing``
            takes the newest build's answer."""
            self._landing_build_id += 1
            build_id = self._landing_build_id
            rows = self._all_trades
            self._run_steps(
                landing_steps(rows, since_ts),
                lambda: build_id == self._landing_build_id and rows is self._all_trades,
                lambda facts: self._take_landing(facts, since_ts, fetch_s),
            )

        def _start_view_build(self) -> None:
            """Run ``view_steps`` over ``_all_trades`` and the filter controls;
            ``_take_view`` takes the newest build's answer."""
            self._view_build_id += 1
            build_id = self._view_build_id
            rows = self._all_trades
            to_ts = self._to_bound_ts()
            chosen = self._current_filters()
            predicate = hrc.HistoryFilters(
                from_ts=chosen.from_ts,
                to_ts=to_ts,
                exchange=chosen.exchange,
                symbol=chosen.symbol,
                side=chosen.side,
            )
            # ``verify`` reads the controls again for ``refused_rows``.
            verify = self._current_filters()
            self._run_steps(
                view_steps(rows, predicate, verify),
                lambda: build_id == self._view_build_id and rows is self._all_trades,
                self._take_view,
            )

        def _run_steps(
            self,
            steps: Generator,
            current: Callable[[], bool],
            finish: Callable,
        ) -> None:
            """Queue ``steps`` on ``_step_chains`` for ``_drive_steps``, which
            hands its answer to ``finish`` while ``current`` holds."""
            self._step_chains.append((steps, current, finish))
            self._post_drive()

        def _post_drive(self) -> None:
            """Post one ``_drive_steps`` call while ``_step_chains`` holds a
            chain and none is posted."""
            if self._step_chains and not self._drive_due:
                self._drive_due = True
                QTimer.singleShot(0, self, self._drive_steps)

        def _drive_steps(self) -> None:
            """Run one step of the first chain in ``_step_chains`` and requeue it
            last, or drop it when finished or ``current`` fails."""
            self._drive_due = False
            if not self._step_chains:
                return
            steps, current, finish = self._step_chains.pop(0)
            try:
                if not current():
                    steps.close()
                    return
                try:
                    next(steps)
                except StopIteration as done:
                    finish(done.value)
                    return
                self._step_chains.append((steps, current, finish))
            finally:
                self._post_drive()

        def _take_landing(self, facts: dict, since_ts: float, fetch_s: float) -> None:
            """Refill the pickers from a finished ``landing_steps``, then apply
            the filters to the rows it read."""
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _hist_emit

                _hist_emit(
                    "history.05.002.postcondition.trades_stored",
                    actual=facts["admissible"],
                    expected=len(self._all_trades),
                    duration=fetch_s,
                    context={
                        "since_ts": float(since_ts),
                        "distinct_keys": facts["distinct"],
                        "poll_interval_s": 0.4,
                    },
                )
            self._populate_filter_options(facts["options"], facts["options_s"])
            self._apply_filters()

        def _take_view(self, view: HistoryView) -> None:
            """Hold a finished ``HistoryView`` of the rows in hand and draw it."""
            self._view = view
            self._show_view()

        def _show_view(self) -> None:
            """Draw page one of the held ``HistoryView`` for ``_asset_class``."""
            view = self._view
            if view is None:
                return
            key = self._asset_class
            self._hold_rows(view.rows_of(key), view.totals_of(key))
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _hist_emit

                _hist_emit(
                    "history.05.004.postcondition.filters_applied",
                    actual=view.refused.get(key, 0),
                    expected=0,
                    context={
                        "kept": len(self._filtered),
                        "loaded": len(self._all_trades),
                        "exchange": view.verify.exchange,
                        "symbol": view.verify.symbol,
                        "side": view.verify.side,
                        "from_ts": float(view.predicate.from_ts),
                        "to_ts": float(view.predicate.to_ts),
                    },
                    duration=view.seconds,
                )
            self._page = 0
            self._render_page()

        def _hold_rows(self, rows: list, totals: hrc.SummaryTotals) -> None:
            """Hold ``rows`` as ``_filtered`` with their ``totals``, the one
            write of both, and step ``_rows_version``."""
            self._filtered = rows
            self._filtered_totals = totals
            self._rows_version += 1

        def _hold_indexes(self, gate: dict, voting: dict) -> None:
            """Hold the two join indexes a page reads, the one write of both, and
            step ``_join_version``."""
            self._page_gate_index = gate
            self._page_voting_index = voting
            self._join_version += 1

        def _reset_filters(self) -> None:
            self._reset_filter_values()
            self._apply_filters()

        def _current_filters(self):
            """The five filter values from the two date edits and three combos."""
            try:
                from_ts = self._from_dt.dateTime().toSecsSinceEpoch()
                to_ts = self._to_dt.dateTime().toSecsSinceEpoch()
            except Exception:  # a torn-down date edit
                from_ts, to_ts = 0, 0
            return hrc.HistoryFilters(
                from_ts=int(from_ts),
                to_ts=int(to_ts),
                exchange=self._exch_combo.currentText(),
                symbol=self._sym_combo.currentText(),
                side=self._side_combo.currentText(),
            )

        def _render_page(self) -> None:
            """Draw the page ``_page`` names, its rows built ``RENDER_STEP_ROWS``
            a step; a newer ``_render_page`` drops this one."""
            total = len(self._filtered)
            last_page = max(0, (total - 1) // self.PAGE_SIZE)
            self._page = min(max(self._page, 0), last_page)
            self._render_build_id += 1
            build_id = self._render_build_id
            key = self._page_key()
            steps = self._page_steps(
                key,
                self._filtered,
                (self._page_gate_index, self._page_voting_index),
            )
            self._run_steps(
                steps,
                lambda: build_id == self._render_build_id,
                lambda rendered: self._draw_page(key, rendered, total, last_page),
            )

        def _page_steps(
            self, key: tuple, rows: list, indexes: tuple
        ) -> Generator[None, None, hrc.HistoryPage]:
            """The page ``key`` names: the ``_cached_page``, else the
            ``page_join_indexes`` of ``rows`` and ``indexes``, then
            ``hrc.build_page_steps``."""
            held = self._cached_page(key)
            if held is not None:
                return held
            page = key[1]
            gate_index, voting_index = page_join_indexes(
                hrc.page_slice(rows, page), self._bot_manager, *indexes
            )
            yield
            rendered = yield from hrc.build_page_steps(
                rows,
                page,
                self._bot_manager,
                gate_index,
                voting_index,
                RENDER_STEP_ROWS,
            )
            yield
            return rendered

        def _draw_page(
            self, key: tuple, rendered: hrc.HistoryPage, total: int, last_page: int
        ) -> None:
            """Hold ``rendered`` as the page ``key`` names and push it to the
            table, then the counter, the pager buttons, the summary and the join
            read a landing left due."""
            self._page_cache = (key, rendered)
            self._drawn_render_id = self._render_build_id
            model = self._build_model(rendered)
            self._table.set_model(model)

            # _want_rows recomputes the slice from total and the clamped page.
            _want_rows = min(
                self.PAGE_SIZE, max(0, total - self._page * self.PAGE_SIZE)
            )
            _page_now = self._page

            def _emit_drawn(drawn) -> None:
                try:
                    _actual = int(drawn)
                except (TypeError, ValueError):
                    _actual = -1
                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _hist_emit

                    _hist_emit(
                        "history.05.005.postcondition.page_rendered",
                        actual=_actual,
                        expected=_want_rows,
                        context={
                            "page": _page_now,
                            "pages": last_page + 1,
                            "filtered": total,
                            "pushed_rows": len(model["page"]["rows"]),
                            "readback": _actual >= 0,
                            "page_size": self.PAGE_SIZE,
                        },
                    )

            if not self._table.row_count(_emit_drawn):
                _emit_drawn(-1)

            self._paint_chrome(total, last_page)
            if self._join_due:
                self._join_due = False
                self._start_join_index_build()

        def _grade_row(self, row_i: int, page_rows: list, r: dict) -> str:
            """Return the A-to-F grade for one row, delegating to grade_row."""
            from src.exchange.history_read_contract import grade_row

            return grade_row(row_i, page_rows, r)

        def _start_join_index_build(self) -> None:
            """Run ``join_steps`` over ``_all_trades``; ``_on_join_indexes_ready``
            takes the newest build's answer.

            ``_render_page`` then reads the held indexes, so no page draw and no
            pager press touches disk.
            """
            self._join_build_id += 1
            build_id = self._join_build_id
            rows = self._all_trades
            if not rows:
                self._hold_indexes({}, {})
                return
            self._run_steps(
                join_steps(rows, self._bot_manager),
                lambda: build_id == self._join_build_id,
                lambda payload: self._on_join_indexes_ready(
                    dict(payload, build_id=build_id)
                ),
            )

        def _on_join_indexes_ready(self, payload: dict) -> None:
            """Hold a finished index pair and redraw the page it covers."""
            if payload.get("build_id") != self._join_build_id:
                return
            self._hold_indexes(payload.get("gate") or {}, payload.get("voting") or {})

            # An emptied index collapses _bucketed while kept stands.
            _bucketed = sum(len(v) for v in self._page_gate_index.values()) + sum(
                len(v) for v in self._page_voting_index.values()
            )
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _hist_emit

                _hist_emit(
                    "history.05.006.postcondition.joiner_indexes_built",
                    actual=_bucketed,
                    expected=int(payload.get("kept") or 0),
                    context={
                        "gate_buckets": len(self._page_gate_index),
                        "voting_buckets": len(self._page_voting_index),
                        "loaded_rows": int(payload.get("rows") or 0),
                        "off_gui_thread": False,
                    },
                    duration=float(payload.get("seconds") or 0.0),
                )
            self._render_page()

        def _prev_page(self) -> None:
            self._page -= 1
            self._render_page()

        def _next_page(self) -> None:
            self._page += 1
            self._render_page()

        def _export_csv(self) -> None:
            if not self._filtered:
                QMessageBox.information(
                    self,
                    "No data",
                    "Nothing to export — apply filters or " "refresh first.",
                )
                return
            default_name = (
                f"acervator_history_" f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            )
            path, _ = QFileDialog.getSaveFileName(
                self, "Export trade history", default_name, "CSV files (*.csv)"
            )
            if not path:
                return
            # _export_t0 starts below the blocking file dialog, excluding operator wait.
            _export_t0 = time.monotonic()
            try:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(
                        [
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
                        ]
                    )
                    for r in self._filtered:
                        dt = r.get("datetime")
                        ts_str = (
                            dt.strftime("%Y-%m-%d %H:%M:%S") if dt is not None else ""
                        )
                        bot_label = _resolve_bot_label(
                            self._bot_manager,
                            r.get("exchange", ""),
                            r.get("symbol", ""),
                        )
                        w.writerow(
                            [
                                ts_str,
                                r.get("exchange", ""),
                                r.get("symbol", ""),
                                bot_label,
                                r.get("side", ""),
                                f"{r.get('amount', 0):.8f}",
                                f"{r.get('price', 0):.8f}",
                                f"{r.get('cost', 0):.4f}",
                                f"{r.get('fee', 0):.6f}",
                                r.get("fee_currency", ""),
                                r.get("id", ""),
                            ]
                        )
                # _written counts the file's own records, minus the header row.
                _written = -1
                try:
                    with open(path, "r", newline="", encoding="utf-8") as _rf:
                        _written = sum(1 for _ in csv.reader(_rf)) - 1
                except (OSError, csv.Error) as _rb_exc:
                    logger.debug("history csv read-back failed: %s", _rb_exc)
                _export_s = time.monotonic() - _export_t0
                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _hist_emit

                    _hist_emit(
                        "history.05.007.postcondition.csv_exported",
                        actual=_written,
                        expected=len(self._filtered),
                        context={
                            "readback": _written >= 0,
                            "loaded": len(self._all_trades),
                        },
                        duration=_export_s,
                    )
                QMessageBox.information(
                    self,
                    "Export complete",
                    f"Wrote {len(self._filtered)} rows to:\n{path}",
                )
            except Exception as exc:
                logger.exception("CSV export raised")
                QMessageBox.warning(
                    self,
                    "Export failed",
                    f"Could not write CSV:\n\n{type(exc).__name__}: {exc}",
                )
