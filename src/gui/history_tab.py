"""History tab: fetches exchange trade rows, filters, pages and exports them."""

from __future__ import annotations

import asyncio
import contextlib
import csv
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from src.exchange import history_read_contract as hrc

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


if _HAS_QT:

    class HistoryTab(QWidget):
        """Fetches exchange trade history, filters it, pages it and exports CSV."""

        PAGE_SIZE = 100

        history_refreshed = Signal(list)

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self._bot_manager = None
            self._all_trades: list[dict] = []
            self._filtered: list[dict] = []
            self._asset_class = class_filter_surface.active()
            self._page = 0
            self._fetch_in_flight = False
            self._last_fetched_ts: float = 0.0
            self._page_gate_index: dict = {}
            self._page_voting_index: dict = {}
            self._to_default_ts: int = 0
            self._build_ui()

        def set_bot_manager(self, bot_manager) -> None:
            self._bot_manager = bot_manager

        def set_asset_class(self, name) -> tuple:
            """Hold ``name`` as the class this table shows.

            Answers the rows kept for ``name`` and the rows ``_all_trades``
            holds in all; ``_apply_filters`` narrows them through
            ``class_filter_surface.trades_of_class``.
            """
            self._asset_class = class_filter_surface.normalise(name)
            if self._all_trades:
                self._apply_filters()
                self._render_page()
            else:
                self._filtered = []
            return (len(self._filtered), len(self._all_trades))

        def refresh(self) -> None:
            """Start an async trade fetch and re-render when it lands."""
            self._kick_async_fetch()

        def get_history_callback(self):
            """Return a no-op callable; the tab pulls history instead."""
            return lambda *_a, **_kw: None

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
            self._from_dt.setToolTip(
                "Default is the 2026-04-01 platform launch date. Drag "
                "or type an earlier/later date to widen or narrow the "
                "trade fetch window."
            )
            fl.addWidget(self._from_dt)

            fl.addWidget(QLabel("To:"))
            self._to_dt = QDateTimeEdit(QDateTime.currentDateTime())
            self._to_dt.setCalendarPopup(True)
            self._to_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
            self._to_dt.setMinimumWidth(150)
            self._to_dt.setToolTip(
                "Upper bound of the trade window. Left alone it follows the "
                "clock, so trades filled while the tab is open still show. "
                "Set it to pin the window to a fixed instant."
            )
            self._remember_to_bound()
            fl.addWidget(self._to_dt)

            fl.addWidget(QLabel("Exchange:"))
            self._exch_combo = QComboBox()
            self._exch_combo.addItem("(all)")
            self._exch_combo.setMinimumWidth(120)
            fl.addWidget(self._exch_combo)

            fl.addWidget(QLabel("Symbol:"))
            self._sym_combo = QComboBox()
            self._sym_combo.addItem("(all)")
            self._sym_combo.setMinimumWidth(120)
            fl.addWidget(self._sym_combo)

            fl.addWidget(QLabel("Side:"))
            self._side_combo = QComboBox()
            self._side_combo.addItems(["(all)", "BUY", "SELL"])
            fl.addWidget(self._side_combo)

            fl.addStretch(1)

            self._apply_btn = QPushButton("Apply")
            self._apply_btn.setToolTip("Apply current filters to the loaded history.")
            self._apply_btn.clicked.connect(self._apply_filters)
            fl.addWidget(self._apply_btn)

            self._reset_btn = QPushButton("Reset")
            self._reset_btn.setToolTip("Clear all filters and show full history.")
            self._reset_btn.clicked.connect(self._reset_filters)
            fl.addWidget(self._reset_btn)

            self._refresh_btn = QPushButton("Refresh")
            self._refresh_btn.setToolTip(
                "Pull fresh trade history from every active exchange."
            )
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
            self._prev_btn.clicked.connect(self._prev_page)
            foot.addWidget(self._prev_btn)

            self._page_label = QLabel(hrc.PAGE_LABEL_IDLE)
            self._page_label.setMinimumWidth(120)
            self._page_label.setAlignment(Qt.AlignCenter)
            foot.addWidget(self._page_label)

            self._next_btn = QPushButton("Next ▶")
            self._next_btn.clicked.connect(self._next_page)
            foot.addWidget(self._next_btn)

            foot.addStretch(1)

            self._progress = QProgressBar()
            self._progress.setMaximumWidth(150)
            self._progress.setRange(0, 0)  # busy indeterminate
            self._progress.setVisible(False)
            foot.addWidget(self._progress)

            self._export_btn = QPushButton("Export CSV…")
            self._export_btn.setToolTip(
                "Export the currently-filtered history view to a CSV file."
            )
            self._export_btn.clicked.connect(self._export_csv)
            foot.addWidget(self._export_btn)

            outer.addLayout(foot)

        # -- what the fetch, the filter and the render read and write ----
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

        def _build_model(self) -> dict:
            """The payload the table draws for the current page."""
            from .react_history_panel import TABLE_ONLY_CHROME, build_view_model

            return build_view_model(
                self._all_trades,
                self._current_filters(),
                self._page,
                self._bot_manager,
                last_fetched_ts=self._last_fetched_ts,
                filtered=self._filtered,
                gate_index=self._page_gate_index,
                voting_index=self._page_voting_index,
                chrome=TABLE_ONLY_CHROME,
            )

        def _paint_chrome(self, total: int, max_page: int) -> None:
            """Write the page counter, the two pager buttons and the summary."""
            self._page_label.setText(hrc.page_label(self._page, total))
            self._prev_btn.setEnabled(self._page > 0)
            self._next_btn.setEnabled(self._page < max_page)

            if self._last_fetched_ts > 0:
                age_s = int(time.time() - self._last_fetched_ts)
                fetched_str = f"fetched {age_s}s ago"
            else:
                fetched_str = "no fetch yet"
            total_loaded = len(self._all_trades)
            buy_count = sum(1 for r in self._filtered if r.get("side") == "BUY")
            sell_count = sum(1 for r in self._filtered if r.get("side") == "SELL")
            buy_usd = sum(
                r.get("cost", 0) for r in self._filtered if r.get("side") == "BUY"
            )
            sell_usd = sum(
                r.get("cost", 0) for r in self._filtered if r.get("side") == "SELL"
            )
            self._set_status(
                f"{total} of {total_loaded} trades shown · "
                f"BUYs: {buy_count} (${buy_usd:,.2f}) · "
                f"SELLs: {sell_count} (${sell_usd:,.2f}) · "
                f"{fetched_str}"
            )

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
                        _dur_elapsed = time.monotonic() - start_ts
                        # _admissible re-counts _all_trades against since_ts
                        # and (exchange, symbol, id) uniqueness.
                        _seen_keys: set = set()
                        _admissible = 0
                        for _row in self._all_trades:
                            _key = (
                                _row.get("exchange"),
                                _row.get("symbol"),
                                _row.get("id"),
                            )
                            _dupe = _key in _seen_keys
                            _seen_keys.add(_key)
                            _row_ts = float(_row.get("timestamp", 0) or 0)
                            if _dupe or not _row.get("id"):
                                continue
                            if 0 < _row_ts < since_ts:
                                continue
                            _admissible += 1
                        with contextlib.suppress(Exception):
                            from src.core.signal_contract import emit as _hist_emit

                            _hist_emit(
                                "history.05.002.postcondition.trades_stored",
                                actual=_admissible,
                                expected=len(self._all_trades),
                                duration=_dur_elapsed,
                                context={
                                    "since_ts": float(since_ts),
                                    "distinct_keys": len(_seen_keys),
                                    "poll_interval_s": 0.4,
                                },
                            )
                        self._last_fetched_ts = time.time()
                        if self.history_refreshed is not None:
                            try:
                                self.history_refreshed.emit(list(self._all_trades))
                            except Exception as _sig_exc:  # noqa: BLE001
                                logger.debug(
                                    "history_refreshed emit failed: %s", _sig_exc
                                )
                        self._populate_filter_options()
                        self._apply_filters()
                        return
                    if time.monotonic() - start_ts > 60.0:
                        poll_timer.stop()
                        self._set_fetching(False)
                        self._set_status(hrc.STATUS_TEXT["timeout"])
                except Exception as exc:
                    poll_timer.stop()
                    self._set_fetching(False)
                    logger.warning("history poll exception: %s", exc)

            poll_timer.timeout.connect(_check)
            poll_timer.start()

        def _populate_filter_options(self) -> None:
            """Refresh the exchange and symbol choices from the loaded data."""
            _build_t0 = time.monotonic()
            _want_exch = {r["exchange"] for r in self._all_trades if r.get("exchange")}
            _want_sym = {r["symbol"] for r in self._all_trades if r.get("symbol")}
            self._set_filter_options(sorted(_want_exch), sorted(_want_sym))
            _build_s = time.monotonic() - _build_t0

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
            to_ts = self._to_bound_ts()
            chosen = self._current_filters()
            from_ts = chosen.from_ts
            exch_f = chosen.exchange
            sym_f = chosen.symbol
            side_f = chosen.side

            _filter_t0 = time.monotonic()
            out: list[dict] = []
            for r in self._all_trades:
                ts = float(r.get("timestamp", 0) or 0)
                if from_ts > 0 and ts < from_ts:
                    continue
                if to_ts > 0 and ts > to_ts:
                    continue
                if exch_f != "(all)" and r.get("exchange") != exch_f:
                    continue
                if sym_f != "(all)" and r.get("symbol") != sym_f:
                    continue
                if side_f != "(all)" and r.get("side") != side_f:
                    continue
                out.append(r)
            self._filtered = class_filter_surface.trades_of_class(
                out, self._asset_class
            )
            _filter_s = time.monotonic() - _filter_t0
            # Read back from the controls, not the loop locals, so a
            # mis-wired predicate disagrees here.
            _verify = self._current_filters()
            _v_exch = _verify.exchange
            _v_sym = _verify.symbol
            _v_side = _verify.side
            _v_to = _verify.to_ts
            _violations = 0
            for _r in self._filtered:
                _rts = float(_r.get("timestamp", 0) or 0)
                if from_ts > 0 and _rts < from_ts:
                    _violations += 1
                elif _v_to > 0 and _rts > _v_to:
                    _violations += 1
                elif _v_exch != "(all)" and _r.get("exchange") != _v_exch:
                    _violations += 1
                elif _v_sym != "(all)" and _r.get("symbol") != _v_sym:
                    _violations += 1
                elif _v_side != "(all)" and _r.get("side") != _v_side:
                    _violations += 1
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _hist_emit

                _hist_emit(
                    "history.05.004.postcondition.filters_applied",
                    actual=_violations,
                    expected=0,
                    context={
                        "kept": len(self._filtered),
                        "loaded": len(self._all_trades),
                        "exchange": _v_exch,
                        "symbol": _v_sym,
                        "side": _v_side,
                        "from_ts": float(from_ts),
                        "to_ts": float(to_ts),
                    },
                    duration=_filter_s,
                )
            self._page = 0
            self._render_page()

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
            total = len(self._filtered)
            last_page = max(0, (total - 1) // self.PAGE_SIZE)
            self._page = min(max(self._page, 0), last_page)
            start = self._page * self.PAGE_SIZE
            end = min(start + self.PAGE_SIZE, total)
            rows = self._filtered[start:end]

            self._build_joiner_indexes_for_page(rows)

            model = self._build_model()
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

        def _grade_row(self, row_i: int, page_rows: list, r: dict) -> str:
            """Return the A-to-F grade for one row, delegating to grade_row."""
            from src.exchange.history_read_contract import grade_row

            return grade_row(row_i, page_rows, r)

        def _build_joiner_indexes_for_page(self, page_rows: list) -> None:
            """Bucket the page log entries by (bot_id, 60s) for the row joiner."""
            self._page_gate_index = {}
            self._page_voting_index = {}
            if not page_rows:
                return
            try:
                min_ts = min(
                    float(r.get("timestamp", 0) or 0)
                    for r in page_rows
                    if (r.get("timestamp") or 0) > 0
                )
                since_ts = max(0.0, min_ts - 60.0)
                since: Optional[datetime] = None
                if since_ts > 0:
                    since = datetime.fromtimestamp(since_ts, tz=timezone.utc)
            except (ValueError, TypeError):
                since = None

            try:
                from src.trading.live_log_reader import (
                    live_gate_decisions,
                    live_voting_panel_snapshots,
                )
            except Exception:
                return

            _join_t0 = time.monotonic()
            _gate_accepted = 0
            try:
                for entry in live_gate_decisions(since=since, validate=False):
                    bot_id = str(entry.get("bot_id", "") or "")
                    if not bot_id:
                        continue
                    ts = self._parse_entry_ts(entry.get("timestamp", ""))
                    if ts is None:
                        continue
                    key = (bot_id, int(ts) // 60)
                    self._page_gate_index.setdefault(key, []).append(entry)
                    _gate_accepted += 1
            except Exception:
                self._page_gate_index = {}

            _voting_accepted = 0
            try:
                for entry in live_voting_panel_snapshots(since=since):
                    bot_id = str(entry.get("bot_id", "") or "")
                    if not bot_id:
                        continue
                    ts = self._parse_entry_ts(entry.get("timestamp", ""))
                    if ts is None:
                        continue
                    key = (bot_id, int(ts) // 60)
                    self._page_voting_index.setdefault(key, []).append(entry)
                    _voting_accepted += 1
            except Exception:
                self._page_voting_index = {}
            _join_s = time.monotonic() - _join_t0

            # An emptied index collapses _bucketed while its counter stands.
            _bucketed = sum(len(v) for v in self._page_gate_index.values()) + sum(
                len(v) for v in self._page_voting_index.values()
            )
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _hist_emit

                _hist_emit(
                    "history.05.006.postcondition.joiner_indexes_built",
                    actual=_bucketed,
                    expected=_gate_accepted + _voting_accepted,
                    context={
                        "gate_accepted": _gate_accepted,
                        "voting_accepted": _voting_accepted,
                        "gate_buckets": len(self._page_gate_index),
                        "voting_buckets": len(self._page_voting_index),
                        "page_rows": len(page_rows),
                    },
                    duration=_join_s,
                )

        @staticmethod
        def _parse_entry_ts(s: str) -> Optional[float]:
            """Parse an ISO-8601 timestamp into unix seconds, or None."""
            if not s:
                return None
            try:
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                return datetime.fromisoformat(s).timestamp()
            except (ValueError, TypeError):
                return None

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
