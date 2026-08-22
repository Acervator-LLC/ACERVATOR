"""
history_tab.py — Acervator History tab.

v3.23.71 rebuild (2026-07-31) per operator directive: deprecate the
hallucinated fetch + join logic from the v3.17.0-era file; import
the sound pieces from ``src.gui.history_helpers`` instead. Fixes:

  * H1 — default From date pinned to 2026-04-01 (platform launch).
  * H2 — Gate column renamed "Gates"; per-row mouseover explains
    every scrum/fold blocker at trade time.
  * H3 — Grade + Gates + Voting columns all carry rich HTML
    tooltips. Voting tooltip enumerates each indicator's direction,
    confidence, timeframe, and weight (data was already captured in
    voting.log; the old cell surfaced only the compressed marker).
  * H4 — refresh emits ``history_refreshed(list)`` signal so the
    Simulator (v3.23.72 rebuild) can front-load YTD ticks without
    a second network round-trip.
  * H5 — trade fetch is a chunked-window walk (30-day windows, per-
    id dedupe, backwards to the From date) instead of a single
    ``limit=500`` call. Fixes the operator-reported "fewer trades in
    History than boot-up YTD data pull" gap for any bot exceeding
    the exchange's per-time-range cap (RAVE had 881 YTD; old fetcher
    dropped 381).

Chrome (filter bar, table, pagination, CSV export) preserved.

sadp: R28 (fail-loud display), R44 (exchange truth), R70 RCN
"""
from __future__ import annotations

import asyncio
import contextlib
import csv
import logging
import time
from datetime import datetime, timezone
from typing import Optional

try:
    from PySide6.QtCore import QDateTime, Qt, QTimer, Signal
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QAbstractItemView, QComboBox, QDateTimeEdit, QFileDialog,
        QGroupBox, QHBoxLayout, QHeaderView, QLabel,
        QMessageBox, QProgressBar, QPushButton,
        QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    )  # v3.19.12 removed unused QSpacerItem
    _HAS_QT = True
except ImportError:
    # THE FALLBACK THIS REPLACES DID NOT DO WHAT ITS COMMENT PROMISED.
    #
    # It bound ``Qt = QTimer = Signal = QColor = None`` and
    # ``QWidget = object`` under the note "methods still importable".
    # Both halves were false:
    #
    #   * ``QColor(...)`` and ``QTimer(...)`` are called unguarded at 13
    #     sites in the render and fetch paths. With PySide6 absent every
    #     one raised ``TypeError: 'NoneType' object is not callable``,
    #     which is what the module imported ONLY to do.
    #   * The fallback never bound QTableWidgetItem, QLabel, QMessageBox,
    #     QHeaderView or the rest at all, so those sites raised
    #     NameError. The fallback was partial as well as wrong.
    #
    # The form below is the one this repo already uses in
    # bot_visualizer.py and nine other src/gui modules: when Qt is
    # missing there is no Qt and no widget class, so importing this
    # module still succeeds (the module-level helper below stays
    # usable) and asking for the widget fails by name, as an
    # ImportError, at the import site. main_window.py:5079-5117 already
    # catches exactly that and logs "History tab unavailable".
    _HAS_QT = False

logger = logging.getLogger("acervator.gui.history")


# ─────────────────────────────────────────────────────────────────────
# Trade normalization + chunked fetch moved to src.gui.history_helpers
# (v3.23.71 rebuild). This module holds only the widget + its callbacks.
# ─────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────
# History fetcher — retired v3.23.71 (dropped trades > 500 per symbol
# because it made a single get_my_trades() call). Replaced by
# src.gui.history_helpers.fetch_all_history_chunked which walks in
# 30-day windows with per-id dedupe. The old async _fetch_all_history
# function and its inline _normalize_trade helper both move to that
# module — this file no longer holds fetch logic.
# ─────────────────────────────────────────────────────────────────────


def _resolve_bot_label(bot_manager, exchange_id: str, symbol: str) -> str:
    """Find the bot (if any) whose configured symbol matches this row.
    Returns 'TICKER/last4' label, or empty string if no match.

    ``exchange_id`` IS AN UNBUILT FILTER, NOT A DEAD PARAMETER, and the
    docstring above used to hide that by claiming an "(exchange,
    symbol) pair" match. The loop below has only ever compared
    ``cfg.symbol``. The field to compare the argument against exists
    (``BotConfig.exchange_id``, src/trading/bot_container.py:101) and
    both call sites already pass the trade row's exchange, so the
    argument is wired end to end and simply never read.

    It stays unbuilt HERE on purpose. The sibling resolver
    ``history_helpers.resolve_bot_id_for_row`` (line 320) picks the bot
    for the Gates and Voting columns using the same symbol-only match.
    Narrowing this one alone would let the Bot column and the Gates
    column name different bots on the same row whenever one symbol is
    traded on two exchanges. Both resolvers have to narrow in one
    change, and that change moves labels on screen; this unit is
    structural and moves nothing.

    Discarded with ``del`` rather than renamed, so the parameter keeps
    the name the eventual filter needs. Same form as the deliberately
    unused parameters at bot_visualizer.py:56.
    """
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
        except Exception as _bot_exc:  # noqa: BLE001 - best-effort label
            logger.debug(
                "history_tab bot-label lookup skipped one bot: %s",
                _bot_exc)
            continue
    return ""


# ─────────────────────────────────────────────────────────────────────
# History tab widget
# ─────────────────────────────────────────────────────────────────────

if _HAS_QT:

    class HistoryTab(QWidget):
        """v3.23.71 — exchange-truth trade history tab, rebuild-refactor.

        Fetch + gate/voting join + tooltip builders isolated into
        ``src.gui.history_helpers`` (pure, testable). See module
        docstring for the H1-H5 fix map.

        Public surface (used by main_window):
          • __init__(parent=None)
          • set_bot_manager(bot_manager)
          • refresh()  — manual refresh (called by tab-activated event)
        """

        PAGE_SIZE = 100

        # v3.23.71 H4: emit the freshly-fetched trade list so the Simulator
        # tab (v3.23.72 rebuild) can front-load YTD ticks without a second
        # network round-trip. Consumer subscribes in main_window.
        history_refreshed = Signal(list)

        def __init__(self, parent=None) -> None:
            super().__init__(parent)
            self._bot_manager = None
            self._all_trades: list[dict] = []  # full unfiltered fetch
            self._filtered: list[dict] = []    # post-filter view
            self._page = 0
            self._fetch_in_flight = False
            self._last_fetched_ts: float = 0.0
            # v3.23.10 D-01 — per-page gate/voting joiner caches. Built once
            # per _render_page (NOT per row) so the read-time join is O(1)
            # per row. Bucket key = (bot_id, int(ts) // 60) so the ±60s
            # tolerance window catches adjacent buckets via a 3-bucket scan.
            self._page_gate_index: dict = {}
            self._page_voting_index: dict = {}
            self._build_ui()

        # ── Public API ────────────────────────────────────────────────────
        def set_bot_manager(self, bot_manager) -> None:
            self._bot_manager = bot_manager

        def refresh(self) -> None:
            """Trigger an async fetch + re-render. Called from operator's
            Refresh button and on tab-activated event."""
            self._kick_async_fetch()

        def get_history_callback(self):
            """Backward-compat shim. The old TradeHistoryTab exposed a
            push-callback that the connector invoked on each trade event
            (`conn.set_history_callback(cb)` in main_window.py). The
            v3.17.0 rebuild uses pull instead — `exchange.get_my_trades()`
            on Refresh — so this callback is a no-op. Returning a no-op
            lambda lets the existing connector wiring complete without
            error during the transition. Safe to remove once all
            `conn.set_history_callback(...)` call sites in main_window.py
            are deleted (queued for v3.17.1+).
            """
            return lambda *_a, **_kw: None

        # ── UI construction ───────────────────────────────────────────────
        def _build_ui(self) -> None:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(8, 8, 8, 8)
            outer.setSpacing(6)

            # ── Filter bar ────────────────────────────────────────────────
            filt = QGroupBox("Filters")
            fl = QHBoxLayout(filt)
            fl.setContentsMargins(8, 6, 8, 6)

            # Date range — v3.23.71 H1: default From = 2026-04-01 launch date.
            # Construct as local-time QDateTime so the widget renders the
            # exact "2026-04-01 00:00" label regardless of the operator's
            # timezone offset. Convert to UTC unix seconds at fetch time.
            from PySide6.QtCore import QDate, QTime
            fl.addWidget(QLabel("From:"))
            _default_from = QDateTime(
                QDate(2026, 4, 1), QTime(0, 0, 0))
            self._from_dt = QDateTimeEdit(_default_from)
            self._from_dt.setCalendarPopup(True)
            self._from_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
            self._from_dt.setMinimumWidth(150)
            self._from_dt.setToolTip(
                "Default is the 2026-04-01 platform launch date. Drag "
                "or type an earlier/later date to widen or narrow the "
                "trade fetch window.")
            fl.addWidget(self._from_dt)

            fl.addWidget(QLabel("To:"))
            self._to_dt = QDateTimeEdit(QDateTime.currentDateTime())
            self._to_dt.setCalendarPopup(True)
            self._to_dt.setDisplayFormat("yyyy-MM-dd HH:mm")
            self._to_dt.setMinimumWidth(150)
            fl.addWidget(self._to_dt)

            # Exchange filter
            fl.addWidget(QLabel("Exchange:"))
            self._exch_combo = QComboBox()
            self._exch_combo.addItem("(all)")
            self._exch_combo.setMinimumWidth(120)
            fl.addWidget(self._exch_combo)

            # Symbol filter
            fl.addWidget(QLabel("Symbol:"))
            self._sym_combo = QComboBox()
            self._sym_combo.addItem("(all)")
            self._sym_combo.setMinimumWidth(120)
            fl.addWidget(self._sym_combo)

            # Side filter
            fl.addWidget(QLabel("Side:"))
            self._side_combo = QComboBox()
            self._side_combo.addItems(["(all)", "BUY", "SELL"])
            fl.addWidget(self._side_combo)

            fl.addStretch(1)

            # Apply / Reset / Refresh buttons
            self._apply_btn = QPushButton("Apply")
            self._apply_btn.setToolTip(
                "Apply current filters to the loaded history.")
            self._apply_btn.clicked.connect(self._apply_filters)
            fl.addWidget(self._apply_btn)

            self._reset_btn = QPushButton("Reset")
            self._reset_btn.setToolTip(
                "Clear all filters and show full history.")
            self._reset_btn.clicked.connect(self._reset_filters)
            fl.addWidget(self._reset_btn)

            self._refresh_btn = QPushButton("Refresh")
            self._refresh_btn.setToolTip(
                "Pull fresh trade history from every active exchange.")
            self._refresh_btn.clicked.connect(self.refresh)
            fl.addWidget(self._refresh_btn)

            outer.addWidget(filt)

            # ── Summary line ─────────────────────────────────────────────
            self._summary = QLabel("No history loaded yet — click Refresh.")
            self._summary.setStyleSheet("color: #aaa; padding: 2px 6px;")
            outer.addWidget(self._summary)

            # ── Trades table ─────────────────────────────────────────────
            # v3.20.78 — added "Grade" column at index 10 backed by
            # sadp._tools.trade_grader. Grading is on-demand and operator-
            # visible; never feeds back into trading decisions.
            # v3.23.10 D-01 — added "Gate" (idx 11) + "Voting" (idx 12)
            # columns wired via the read-time joiner against live's
            # gate.log + voting.log streams (sadp._tools.live_log_reader).
            # The join is per-page, indexed by (bot_id, ts-bucket), with a
            # ±60s tolerance per operator's 2026-06-13 pin. Pre-v3.23.6
            # rows where no gate/voting entry exists render as '—'.
            self._table = QTableWidget()
            self._table.setColumnCount(13)
            self._table.setHorizontalHeaderLabels([
                "Timestamp (UTC)", "Exchange", "Symbol", "Bot",
                "Side", "Amount", "Price", "Cost USD",
                "Fee", "Trade ID", "Grade", "Gates", "Voting"])
            # v3.23.71 H2: column renamed Gate → Gates. Header tooltip
            # walks the operator through the join contract.
            _hdr = self._table.horizontalHeaderItem(11)
            if _hdr is not None:
                _hdr.setToolTip(
                    "Join against ~/.acervator_logs/trade/gate.log entries "
                    "within ±60s of the trade. Hover any cell for the full "
                    "scrum/fold arm state + blocker list at trade time.")
            _hdr = self._table.horizontalHeaderItem(12)
            if _hdr is not None:
                _hdr.setToolTip(
                    "Join against ~/.acervator_logs/trade/voting.log "
                    "snapshots. Hover any cell for the per-indicator "
                    "direction / confidence / timeframe / weight roll-up "
                    "the panel saw at trade time.")
            _hdr = self._table.horizontalHeaderItem(10)
            if _hdr is not None:
                _hdr.setToolTip(
                    "On-demand grade (A–F) computed by "
                    "src.trading.trade_grader from surrounding same-asset "
                    "trades on this page. Hover for the letter meaning.")
            self._table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents)
            self._table.horizontalHeader().setStretchLastSection(False)
            self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self._table.setAlternatingRowColors(True)
            self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
            outer.addWidget(self._table, stretch=1)

            # ── Footer bar (pagination + export) ─────────────────────────
            foot = QHBoxLayout()
            foot.setContentsMargins(0, 0, 0, 0)

            self._prev_btn = QPushButton("◀ Prev")
            self._prev_btn.clicked.connect(self._prev_page)
            foot.addWidget(self._prev_btn)

            self._page_label = QLabel("Page —")
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
                "Export the currently-filtered history view to a CSV file.")
            self._export_btn.clicked.connect(self._export_csv)
            foot.addWidget(self._export_btn)

            outer.addLayout(foot)

        # ── Async fetch + result handling ─────────────────────────────────
        def _kick_async_fetch(self) -> None:
            if self._fetch_in_flight:
                return
            if self._bot_manager is None:
                self._summary.setText(
                    "Bot manager unavailable — cannot fetch history.")
                return
            # Compute since_ts from the From filter (UTC unix seconds)
            try:
                qdt = self._from_dt.dateTime()
                # Treat as local time, convert to UTC unix seconds
                since_ts = qdt.toSecsSinceEpoch()
            except Exception:
                since_ts = time.time() - 30 * 86400

            loop = getattr(self._bot_manager, "_async_loop", None)
            if loop is None:
                self._summary.setText(
                    "Async loop not ready — try again after platform starts.")
                return

            self._fetch_in_flight = True
            self._progress.setVisible(True)
            self._refresh_btn.setEnabled(False)
            self._summary.setText("Fetching trade history from exchanges…")

            try:
                # v3.23.71 H5: chunked-window walk instead of the single
                # limit=500 call that dropped trades for any bot with
                # more than the exchange's per-time-range cap.
                from .history_helpers import fetch_all_history_chunked
                future = asyncio.run_coroutine_threadsafe(
                    fetch_all_history_chunked(self._bot_manager, since_ts),
                    loop)
            except Exception as exc:
                self._fetch_in_flight = False
                self._progress.setVisible(False)
                self._refresh_btn.setEnabled(True)
                self._summary.setText(f"Schedule failed: {exc}")
                return

            # Poll the future without blocking the GUI.
            start_ts = time.monotonic()
            poll_timer = QTimer(self)
            poll_timer.setInterval(400)

            def _check():
                try:
                    if future.done():
                        poll_timer.stop()
                        self._fetch_in_flight = False
                        self._progress.setVisible(False)
                        self._refresh_btn.setEnabled(True)
                        try:
                            result = future.result(timeout=0.1)
                        except Exception as rx:
                            self._summary.setText(
                                f"Fetch raised: {type(rx).__name__}: {rx}")
                            logger.warning(
                                "history fetch raised: %s", rx)
                            return
                        self._all_trades = list(result or [])
                        # The rows are stored and the fetch is over.
                        # Stop the clock HERE, above the admissibility
                        # count and above the emitter block, so
                        # instrumentation is not billed to the fetch.
                        _dur_elapsed = time.monotonic() - start_ts
                        # 05.002 -- WHAT LANDED IN `_all_trades`, NEVER
                        # WHAT THE FETCH SAID IT RETURNED.
                        #
                        # `fetch_all_history_chunked` admits a row on two
                        # rules and drops it on either
                        # (history_helpers.py:282-288): the row is at or
                        # after `since_ts`, and its
                        # (exchange, symbol, id) key has not been seen on
                        # an earlier (exchange, symbol) pair. Both are
                        # enforced inside the helper's own loop and
                        # NOTHING downstream re-checks them, so a row that
                        # breaks either one is displayed, graded,
                        # exported, and handed to the Simulator through
                        # `history_refreshed` exactly like a good one.
                        #
                        # `actual` counts the rows in the STORED list that
                        # still satisfy both rules. `expected` is how many
                        # rows that list holds. Two different expressions,
                        # so a duplicate that survived the per-pair dedupe
                        # or a row older than the From date drives them
                        # apart and `ok` goes False. Reporting
                        # `len(result)` back would echo the request as
                        # though it were the result and could never fail.
                        #
                        # THE DURATION IS THE OPERATOR-VISIBLE FETCH
                        # LATENCY, and it is honest about its own
                        # resolution: the future is observed by a 400 ms
                        # poll, so a reading is the true fetch time plus
                        # up to one poll interval. `poll_interval_s` rides
                        # in the context so a reader of item 17 sees the
                        # quantum rather than infers it. The bracket opens
                        # at `start_ts`, one line below the schedule, and
                        # closes above -- it spans the fetch and nothing
                        # else.
                        _seen_keys: set = set()
                        _admissible = 0
                        for _row in self._all_trades:
                            _key = (_row.get("exchange"), _row.get("symbol"),
                                    _row.get("id"))
                            _dupe = _key in _seen_keys
                            _seen_keys.add(_key)
                            _row_ts = float(_row.get("timestamp", 0) or 0)
                            if _dupe or not _row.get("id"):
                                continue
                            if 0 < _row_ts < since_ts:
                                continue
                            _admissible += 1
                        with contextlib.suppress(Exception):
                            from src.core.signal_contract import (
                                emit as _hist_emit)
                            _hist_emit(
                                "history.05.002.postcondition.trades_stored",
                                actual=_admissible,
                                expected=len(self._all_trades),
                                duration=_dur_elapsed,
                                context={"since_ts": float(since_ts),
                                         "distinct_keys": len(_seen_keys),
                                         "poll_interval_s": 0.4})
                        self._last_fetched_ts = time.time()
                        # v3.23.71 H4: emit for Simulator's front-load.
                        if self.history_refreshed is not None:
                            try:
                                self.history_refreshed.emit(
                                    list(self._all_trades))
                            except Exception as _sig_exc:  # noqa: BLE001
                                logger.debug(
                                    "history_refreshed emit failed: %s",
                                    _sig_exc)
                        self._populate_filter_options()
                        self._apply_filters()
                        return
                    # 60s sanity timeout
                    if time.monotonic() - start_ts > 60.0:
                        poll_timer.stop()
                        self._fetch_in_flight = False
                        self._progress.setVisible(False)
                        self._refresh_btn.setEnabled(True)
                        self._summary.setText(
                            "Fetch timeout (60s). Exchange may be rate-"
                            "limited; try again.")
                except Exception as exc:
                    poll_timer.stop()
                    self._fetch_in_flight = False
                    self._progress.setVisible(False)
                    self._refresh_btn.setEnabled(True)
                    logger.warning(
                        "history poll exception: %s", exc)

            poll_timer.timeout.connect(_check)
            poll_timer.start()

        # ── Filter handling ──────────────────────────────────────────────
        def _populate_filter_options(self) -> None:
            """Refresh the exchange/symbol comboboxes from the loaded data."""
            # 10.3 -- THE BRACKET OPENS HERE AND CLOSES ON THE SECOND
            # `blockSignals(False)`, so it spans THE REBUILD OF THE TWO
            # COMBOS and nothing else. The read-back below is this pin's
            # own bookkeeping; folding it in would time the check
            # instead of the work.
            #
            # The rebuild is O(loaded trades): two set comprehensions
            # over `_all_trades`, two sorts and two `addItem` loops, all
            # on the GUI thread. That is the operation this
            # postcondition asserts about, and it is the number item 17
            # reads when the History tab goes heavy.
            _build_t0 = time.monotonic()
            # Exchanges
            cur_exch = self._exch_combo.currentText()
            self._exch_combo.blockSignals(True)
            self._exch_combo.clear()
            self._exch_combo.addItem("(all)")
            for x in sorted({r["exchange"] for r in self._all_trades
                             if r.get("exchange")}):
                self._exch_combo.addItem(x)
            idx = self._exch_combo.findText(cur_exch)
            if idx >= 0:
                self._exch_combo.setCurrentIndex(idx)
            self._exch_combo.blockSignals(False)

            # Symbols
            cur_sym = self._sym_combo.currentText()
            self._sym_combo.blockSignals(True)
            self._sym_combo.clear()
            self._sym_combo.addItem("(all)")
            for s in sorted({r["symbol"] for r in self._all_trades
                             if r.get("symbol")}):
                self._sym_combo.addItem(s)
            idx = self._sym_combo.findText(cur_sym)
            if idx >= 0:
                self._sym_combo.setCurrentIndex(idx)
            self._sym_combo.blockSignals(False)
            _build_s = time.monotonic() - _build_t0

            # 05.003 -- READ BOTH COMBOS BACK OUT, ENTRY BY ENTRY.
            #
            # Not `count()`. A count agrees with a set of the right SIZE
            # holding the wrong members, and both lists are rebuilt from
            # scratch on every fetch behind `blockSignals`, which is the
            # state where a wrong member is least visible: the operator
            # sees a plausible dropdown and filters against a symbol the
            # fetch never returned.
            #
            # `actual` is the symmetric difference, summed over the two
            # lists, between what the widget now offers and the distinct
            # values `_all_trades` actually holds. `expected` is zero --
            # the declared intent that the dropdown offers every loaded
            # value and invents none. Both terms are non-negative so they
            # cannot cancel: an exchange list short by one is not hidden
            # by a symbol list long by one.
            #
            # The `(all)` sentinel is discounted on the widget side
            # because it is chrome, not data. An exchange or a symbol
            # literally spelled `(all)` would be discounted with it; no
            # venue names one that way, and the alternative -- trusting
            # index 0 to be the sentinel -- would silently pass a list
            # that had lost it.
            _want_exch = {r["exchange"] for r in self._all_trades
                          if r.get("exchange")}
            _want_sym = {r["symbol"] for r in self._all_trades
                         if r.get("symbol")}
            _have_exch = {
                self._exch_combo.itemText(i)
                for i in range(self._exch_combo.count())} - {"(all)"}
            _have_sym = {
                self._sym_combo.itemText(i)
                for i in range(self._sym_combo.count())} - {"(all)"}
            _mismatched = len(_want_exch ^ _have_exch) + len(
                _want_sym ^ _have_sym)
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _hist_emit
                _hist_emit(
                    "history.05.003.postcondition.filter_options_built",
                    actual=_mismatched, expected=0,
                    context={"exchanges_offered": len(_have_exch),
                             "exchanges_loaded": len(_want_exch),
                             "symbols_offered": len(_have_sym),
                             "symbols_loaded": len(_want_sym),
                             "trades_loaded": len(self._all_trades)},
                    duration=_build_s)

        def _apply_filters(self) -> None:
            # v3.20.36 — operator-reported 2026-05-31: pressing Apply with
            # a valid filter range produced "0 of 0 trades · no fetch yet"
            # forever, because Apply only filters local data — it never
            # triggers a fetch. The companion gap was that the History
            # tab's documented "auto-refresh on tab activation" (file
            # docstring line 21) was never wired in main_window. Together
            # the two gaps meant the only path to a fetch was the operator
            # explicitly clicking Refresh — but the natural UX intent of
            # setting filters + clicking Apply is "show me those trades."
            # Fix: if no prior fetch has occurred, treat Apply as
            # implicit-Refresh-then-Apply. The fetch's completion handler
            # already calls _apply_filters() recursively on success
            # (_kick_async_fetch line ~477), so the filter pass runs
            # automatically once data arrives.
            if (self._last_fetched_ts == 0
                    and not self._fetch_in_flight
                    and self._bot_manager is not None):
                logger.info(
                    "history: Apply pressed with no prior fetch; "
                    "kicking implicit fetch")
                self._kick_async_fetch()
                return
            try:
                from_ts = self._from_dt.dateTime().toSecsSinceEpoch()
                to_ts = self._to_dt.dateTime().toSecsSinceEpoch()
            except Exception:
                from_ts, to_ts = 0, 0
            exch_f = self._exch_combo.currentText()
            sym_f = self._sym_combo.currentText()
            side_f = self._side_combo.currentText()

            # 10.3 -- THE BRACKET SPANS THE FILTER PASS ONLY.
            #
            # It opens above the loop and closes on the assignment to
            # `self._filtered`, so it covers the single O(loaded trades)
            # walk that IS the operation. It excludes the widget reads
            # above it, which are five Qt property fetches, and it
            # excludes the verification loop below it, which walks the
            # RETAINED set to judge this one. Timing the check with the
            # work would leave a reader unable to tell a slow filter
            # from a slow verifier.
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
            self._filtered = out
            _filter_s = time.monotonic() - _filter_t0
            # 05.004 -- RE-READ THE RETAINED SET AGAINST THE WIDGETS.
            #
            # The predicates below are read back from the COMBOS, not
            # from the `exch_f` / `sym_f` / `side_f` locals the loop
            # above used. That is the whole difference between a check
            # and an echo: a block that compared against the wrong
            # widget, or that was skipped entirely, agrees with those
            # locals and disagrees with the operator's actual selection.
            # Five filters read from three combos and two date edits is
            # exactly the shape where one gets wired to its neighbour.
            #
            # `actual` is how many RETAINED rows break at least one
            # active filter. `expected` is zero. A row that should have
            # been excluded and was not makes the two differ, and `ok`
            # goes False.
            #
            # An inactive filter -- `(all)`, or a date edit that yielded
            # nothing -- excludes nothing and is not checked, so widening
            # a filter is never read as a violation.
            _v_exch = self._exch_combo.currentText()
            _v_sym = self._sym_combo.currentText()
            _v_side = self._side_combo.currentText()
            _violations = 0
            for _r in self._filtered:
                _rts = float(_r.get("timestamp", 0) or 0)
                if from_ts > 0 and _rts < from_ts:
                    _violations += 1
                elif to_ts > 0 and _rts > to_ts:
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
                    actual=_violations, expected=0,
                    context={"kept": len(self._filtered),
                             "loaded": len(self._all_trades),
                             "exchange": _v_exch, "symbol": _v_sym,
                             "side": _v_side,
                             "from_ts": float(from_ts),
                             "to_ts": float(to_ts)},
                    duration=_filter_s)
            self._page = 0
            self._render_page()

        def _reset_filters(self) -> None:
            # v3.23.71 H1: reset From = 2026-04-01 (matches init default).
            from PySide6.QtCore import QDate, QTime
            self._from_dt.setDateTime(
                QDateTime(QDate(2026, 4, 1), QTime(0, 0, 0)))
            self._to_dt.setDateTime(QDateTime.currentDateTime())
            self._exch_combo.setCurrentIndex(0)
            self._sym_combo.setCurrentIndex(0)
            self._side_combo.setCurrentIndex(0)
            self._apply_filters()

        # ── Pagination + rendering ───────────────────────────────────────
        def _render_page(self) -> None:
            total = len(self._filtered)
            max_page = max(0, (total - 1) // self.PAGE_SIZE)
            if self._page > max_page:
                self._page = max_page
            if self._page < 0:
                self._page = 0
            start = self._page * self.PAGE_SIZE
            end = min(start + self.PAGE_SIZE, total)
            rows = self._filtered[start:end]

            # v3.23.10 D-01 — build gate/voting indexes ONCE per page render
            # (NOT per row) so the joiner stays O(rows) instead of O(rows*N).
            # Lazy-imports the live_log_reader inside the helper so an
            # absent log dir / unwritable env doesn't break the GUI render.
            self._build_joiner_indexes_for_page(rows)

            self._table.setRowCount(len(rows))
            for row_i, r in enumerate(rows):
                dt = r.get("datetime")
                ts_str = (dt.strftime("%Y-%m-%d %H:%M:%S")
                          if dt is not None else "—")
                self._table.setItem(row_i, 0, QTableWidgetItem(ts_str))
                self._table.setItem(row_i, 1, QTableWidgetItem(
                    str(r.get("exchange", ""))))
                self._table.setItem(row_i, 2, QTableWidgetItem(
                    str(r.get("symbol", ""))))
                bot_label = _resolve_bot_label(
                    self._bot_manager,
                    r.get("exchange", ""),
                    r.get("symbol", ""))
                self._table.setItem(row_i, 3, QTableWidgetItem(bot_label))
                side_item = QTableWidgetItem(str(r.get("side", "")))
                if r.get("side") == "BUY":
                    side_item.setForeground(QColor("#00ff88"))
                elif r.get("side") == "SELL":
                    side_item.setForeground(QColor("#ff5566"))
                self._table.setItem(row_i, 4, side_item)
                self._table.setItem(row_i, 5, QTableWidgetItem(
                    f"{r.get('amount', 0):,.8f}"))
                self._table.setItem(row_i, 6, QTableWidgetItem(
                    f"${r.get('price', 0):,.8f}"))
                self._table.setItem(row_i, 7, QTableWidgetItem(
                    f"${r.get('cost', 0):,.4f}"))
                fee_str = (f"{r.get('fee', 0):,.6f} {r.get('fee_currency', '')}"
                           if r.get("fee", 0) > 0 else "—")
                self._table.setItem(row_i, 8, QTableWidgetItem(fee_str))
                tid = str(r.get("id", ""))
                self._table.setItem(row_i, 9, QTableWidgetItem(
                    tid[:16] + "…" if len(tid) > 16 else tid))
                # v3.20.78 — Grade column (idx 10). On-demand grading via
                # sadp._tools.trade_grader using context from the
                # surrounding filtered trades (same asset/exchange) on
                # this page. Read-only display; never feeds back into
                # trading decisions.
                grade_str = self._grade_row(row_i, rows, r)
                grade_item = QTableWidgetItem(grade_str)
                # Color by letter
                if grade_str.startswith("A"):
                    grade_item.setForeground(QColor("#00ff88"))
                elif grade_str.startswith("B"):
                    grade_item.setForeground(QColor("#88dd44"))
                elif grade_str.startswith("C"):
                    grade_item.setForeground(QColor("#dddd44"))
                elif grade_str.startswith("D"):
                    grade_item.setForeground(QColor("#ff9944"))
                elif grade_str.startswith("F"):
                    grade_item.setForeground(QColor("#ff5566"))
                # v3.23.71 H3: Grade cell gets a tooltip explaining the
                # letter's meaning.
                from .history_helpers import grade_tooltip as _grade_tt
                grade_item.setToolTip(_grade_tt(grade_str))
                self._table.setItem(row_i, 10, grade_item)

                # v3.23.71 H2 + H3: Gates column (idx 11) and Voting
                # column (idx 12) now use the isolated helpers. Text is
                # the compact cell marker; tooltip is the rich HTML view
                # of the full state captured at trade time.
                from .history_helpers import (
                    resolve_bot_id_for_row as _resolve_bid,
                    lookup_gate_entry as _lookup_gate,
                    lookup_voting_entry as _lookup_vote,
                    gate_cell_text as _gate_txt,
                    gate_cell_tooltip as _gate_tt,
                    voting_cell_text as _vote_txt,
                    voting_cell_tooltip as _vote_tt,
                )
                bid_for_join = _resolve_bid(self._bot_manager, r)
                ts_for_join = float(r.get("timestamp", 0) or 0)
                gate_entry = _lookup_gate(
                    self._page_gate_index, bid_for_join, ts_for_join)
                gate_str = _gate_txt(gate_entry)
                gate_item = QTableWidgetItem(gate_str)
                if "S" in gate_str and "F" not in gate_str:
                    gate_item.setForeground(QColor("#00ff88"))
                elif "F" in gate_str and "S" not in gate_str:
                    gate_item.setForeground(QColor("#ff5566"))
                elif "S" in gate_str and "F" in gate_str:
                    gate_item.setForeground(QColor("#ffaa33"))
                gate_item.setToolTip(_gate_tt(gate_entry))
                self._table.setItem(row_i, 11, gate_item)
                # v3.24.98 — THE SIMULATOR'S OWN GATE ROW, in this column.
                #
                # Operator, 2026-08-08: the Gates column "should align with
                # gate row indicators found in the Simulator and show gate
                # latching status for each trade... This will keeps styling
                # and readability consistent."
                #
                # `GateLightsCell` is the widget the Simulator draws, so
                # this is the same ten labelled LEDs with the same colour
                # semantics -- grey not evaluated, green passed, red
                # blocked, amber not-the-blocker -- rather than a second
                # rendering that could drift from it.
                #
                # Only when a record exists: a widget on a row with no gate
                # data would paint ten grey lights, which reads as
                # "evaluated, nothing fired" and is exactly the confusion
                # being removed. Those rows keep the text cell.
                if gate_entry:
                    try:
                        from .simulator_tab.fleet.sim_visuals import (
                            GateLightsCell as _GLC)
                        _gd = gate_entry.get("data") or {}
                        _cell = _GLC()
                        _cell.update_gates(
                            scrum_armed=bool(_gd.get("scrum_armed")),
                            fold_armed=bool(_gd.get("fold_armed")),
                            scrum_blockers=list(_gd.get("scrum_blockers") or []),
                            fold_blockers=list(_gd.get("fold_blockers") or []),
                            landing_strip_side=_gd.get("landing_strip_side"))
                        _cell.setToolTip(_gate_tt(gate_entry))
                        self._table.setCellWidget(row_i, 11, _cell)
                    except Exception as _glc_exc:  # noqa: BLE001 - GUI guard
                        logger.debug(
                            "gate lights cell unavailable: %s", _glc_exc)

                vote_entry = _lookup_vote(
                    self._page_voting_index, bid_for_join, ts_for_join,
                    str(r.get("side", "") or ""))
                voting_str = _vote_txt(vote_entry)
                voting_item = QTableWidgetItem(voting_str)
                up = voting_str.upper()
                if "BUY" in up or up.startswith("B "):
                    voting_item.setForeground(QColor("#00ff88"))
                elif "SELL" in up or up.startswith("S "):
                    voting_item.setForeground(QColor("#ff5566"))
                voting_item.setToolTip(_vote_tt(vote_entry))
                self._table.setItem(row_i, 12, voting_item)

            # 05.005 -- COUNT THE ROWS THE TABLE ITSELF DREW.
            #
            # Not `rowCount()` on its own. `setRowCount(n)` makes
            # `rowCount()` return `n` whether or not a single cell was
            # ever filled, so a loop that stopped early -- the Gates
            # column builds a `GateLightsCell` widget per row, and the
            # grader plus both joiner lookups run per row -- leaves a
            # table that reports a full page and shows blank lines. This
            # walks the table and counts the rows whose timestamp cell
            # actually exists.
            #
            # `expected` is the pagination arithmetic recomputed from
            # `total` and the CLAMPED page, independently of the `rows`
            # slice that fed the loop. So a clamp that disagrees with the
            # slice, an off-by-one in `end`, or a page left beyond the
            # last one shows up here rather than as an empty table the
            # operator has to interpret.
            #
            # NO DURATION. The bracket would have to span the joiner
            # build, which has its own pin below and its own log I/O, and
            # one number covering both would be attributable to neither.
            _drawn = sum(
                1 for _i in range(self._table.rowCount())
                if self._table.item(_i, 0) is not None)
            _want_rows = min(self.PAGE_SIZE,
                             max(0, total - self._page * self.PAGE_SIZE))
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _hist_emit
                _hist_emit(
                    "history.05.005.postcondition.page_rendered",
                    actual=_drawn, expected=_want_rows,
                    context={"page": self._page, "pages": max_page + 1,
                             "filtered": total,
                             "row_count": self._table.rowCount(),
                             "page_size": self.PAGE_SIZE})

            # Page label
            if total == 0:
                self._page_label.setText("No matches")
            else:
                self._page_label.setText(
                    f"Page {self._page + 1} / {max_page + 1} "
                    f"({total} trades)")
            self._prev_btn.setEnabled(self._page > 0)
            self._next_btn.setEnabled(self._page < max_page)

            # Summary
            if self._last_fetched_ts > 0:
                age_s = int(time.time() - self._last_fetched_ts)
                fetched_str = f"fetched {age_s}s ago"
            else:
                fetched_str = "no fetch yet"
            total_loaded = len(self._all_trades)
            buy_count = sum(1 for r in self._filtered if r.get("side") == "BUY")
            sell_count = sum(1 for r in self._filtered if r.get("side") == "SELL")
            buy_usd = sum(r.get("cost", 0) for r in self._filtered
                          if r.get("side") == "BUY")
            sell_usd = sum(r.get("cost", 0) for r in self._filtered
                           if r.get("side") == "SELL")
            self._summary.setText(
                f"{total} of {total_loaded} trades shown · "
                f"BUYs: {buy_count} (${buy_usd:,.2f}) · "
                f"SELLs: {sell_count} (${sell_usd:,.2f}) · "
                f"{fetched_str}")

        # ── Trade grading (v3.20.78) ─────────────────────────────────────
        def _grade_row(self, row_i: int, page_rows: list,
                        r: dict) -> str:
            """Grade a single trade row.

            Uses the surrounding page-context for ref-price + future-price
            proxies (this page's filtered rows of the same symbol). On-
            demand, read-only — grade NEVER feeds back into trading
            decisions. Returns the letter grade string or "—" on insufficient
            context."""
            try:
                from src.trading.trade_grader import (
                    TradeRecord, PriceContext, grade_trade)
            except Exception:
                return "—"
            symbol = str(r.get("symbol", ""))
            side = str(r.get("side", "")).lower()  # BUY → buy / SELL → sell
            price = float(r.get("price", 0) or 0)
            qty = float(r.get("amount", 0) or 0)
            if price <= 0 or qty <= 0 or side not in ("buy", "sell"):
                return "—"
            # Surrounding same-symbol rows on this page (before/after).
            #
            # v3.24.56 (C52 / NF-16) — THE PAGE IS NEWEST-FIRST.
            # `history_helpers.py:295` sorts the fetch with
            # `reverse=True`, and nothing re-sorts between there and here:
            # `_all_trades` is assigned verbatim, `_filtered` preserves that
            # order, and `_render_page` slices it. So a LOWER index is a
            # LATER trade.
            #
            # This loop previously read `j < row_i` as "before", which put
            # post-trade prices into the ref price and pre-trade prices into
            # the MFE/MAE window. Every letter grade and grade tooltip was
            # computed with the time axis running backwards.
            #
            # The two errors do not cancel: on a buy immediately followed by
            # a fall, the inverted reading returns A+ where the correct one
            # returns D — the best available grade for one of the worst
            # available trades.
            same_sym_prior_prices = []
            same_sym_future_prices = []
            for j, other in enumerate(page_rows):
                if str(other.get("symbol", "")) != symbol:
                    continue
                op = float(other.get("price", 0) or 0)
                if op <= 0:
                    continue
                if j < row_i:
                    # Lower index = more recent = AFTER this trade.
                    same_sym_future_prices.append(op)
                elif j > row_i:
                    # Higher index = older = BEFORE this trade.
                    same_sym_prior_prices.append(op)
            # Ref price = median of the 5 NEAREST prior same-symbol prices
            # on this page; require at least 3 for sensible context.
            #
            # The slice direction flips with the axis. Iteration runs
            # newest-first, so `same_sym_prior_prices` comes out
            # nearest-first — `[:5]` are the five immediately preceding
            # trades. The old `[-5:]` would now reach for the five OLDEST
            # rows on the page, which is a different (and worse) reference
            # than the one the docstring describes.
            ref = None
            if len(same_sym_prior_prices) >= 3:
                import statistics
                ref = statistics.median(same_sym_prior_prices[:5])
            rec = TradeRecord(
                trade_id=str(r.get("id", "")),
                timestamp=r.get("datetime"),
                asset=symbol.split("/")[0] if "/" in symbol else symbol,
                side=side,
                price=price,
                quantity=qty,
                fee=float(r.get("fee", 0) or 0),
            )
            ctx = PriceContext(
                ref_price_at_decision=ref,
                # Nearest 10 post-trade prices. Same slice-direction flip as
                # the ref price: iteration is newest-first, so this list
                # comes out newest-first and the trades immediately
                # FOLLOWING this one are at the end. `[:10]` would take the
                # ten most distant, which on a full page is a different
                # MFE/MAE window than the one being described.
                future_prices=same_sym_future_prices[-10:],
                regime_tag="LIVE",
            )
            g = grade_trade(rec, ctx)
            return g.overall

        # ── Read-time joiner (v3.23.10 D-01) ─────────────────────────────
        def _build_joiner_indexes_for_page(self, page_rows: list) -> None:
            """Build per-page (bot_id, 60s-bucket) → entries dicts for
            gate.log + voting.log so the per-row joiner is O(1).

            Strategy:
              1. Determine the page's time window from page_rows. Use the
                 min trade timestamp minus the radius (60s) as the ``since``
                 cutoff so the live-log iterators don't scan back further
                 than necessary.

                 v3.24.24 — this claim is now TRUE. Until then ``since`` was
                 applied after ``json.loads``, so the cutoff discarded work
                 already done and a narrow page window still paid a full
                 parse of all 165,062 rows / 262 MB. ``live_log_reader`` now
                 skips rotated files by mtime and rejects lines by raw-text
                 ISO prefix before parsing: a 30-day cutoff measured
                 1.726 s -> 0.004 s.
              2. Lazy-import sadp._tools.live_log_reader so an absent log
                 dir doesn't break import-time wiring (matches the
                 precedent set by _grade_row's trade_grader import at
                 line ~703).
              3. Bucket each entry by ``(bot_id, int(ts) // 60)``. The
                 per-row lookup then probes the bucket plus its two
                 neighbors so the ±60s tolerance window is fully covered.
              4. Fail-soft — any exception in the build collapses the
                 indexes to empty so the per-row renderer falls back to
                 '—' rather than breaking the GUI.
            """
            # Reset to empty regardless — graceful degrade default.
            self._page_gate_index = {}
            self._page_voting_index = {}
            if not page_rows:
                return
            try:
                # Earliest trade ts on the page, minus a 60s safety margin.
                min_ts = min(
                    float(r.get("timestamp", 0) or 0)
                    for r in page_rows
                    if (r.get("timestamp") or 0) > 0)
                since_ts = max(0.0, min_ts - 60.0)
                since: Optional[datetime] = None
                if since_ts > 0:
                    since = datetime.fromtimestamp(since_ts, tz=timezone.utc)
            except (ValueError, TypeError):
                since = None

            # Lazy import — matches _grade_row's pattern (line ~703) and
            # keeps the GUI importable even if sadp._tools is unavailable.
            try:
                from src.trading.live_log_reader import (
                    live_gate_decisions, live_voting_panel_snapshots)
            except Exception:
                return

            # 10.3 -- THE BRACKET SPANS BOTH READER LOOPS AND NOTHING
            # ELSE.
            #
            # It opens below the lazy import and closes after the voting
            # loop's fail-soft handler, so it covers the two log reads
            # and the bucketing that IS the joiner build. This is the
            # only disk I/O on the render path -- `live_gate_decisions`
            # and `live_voting_panel_snapshots` walk gate.log and
            # voting.log -- so it is the number that moves when the
            # operator's log ladder grows.
            #
            # IT IS MEASURED ON THE FAIL-SOFT PATH TOO. Both handlers
            # empty their index and fall through to here, so a reader
            # that threw on line 90,000 still reports how long it ran
            # before it threw. A duration taken only on the clean path
            # would go silent in exactly the case this pin exists to
            # make visible.
            #
            # THE TWO EARLY RETURNS ABOVE ARE OUTSIDE IT, and they emit
            # nothing at all, so neither one can report a duration for a
            # build that never started.
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
                # Fail-soft — any reader exception collapses gate joins
                # to '—' so the GUI keeps rendering trade rows.
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

            # 05.006 -- THE FAIL-SOFT COLLAPSE, MADE VISIBLE.
            #
            # Both blocks above discard the WHOLE index on any reader
            # exception. That is the right behaviour for the GUI and it
            # is invisible to the operator: every Gates and Voting cell
            # then renders the same em dash it renders when no log entry
            # exists, so "the reader threw on line 90,000" and "this bot
            # never traded" look identical on screen. Two joined columns
            # can go dark without one symptom.
            #
            # `actual` is what the two indexes NOW HOLD, summed over
            # their buckets and read back out of the dicts the per-row
            # joiner will use next. `expected` is how many entries the
            # two loops accepted. They agree exactly while the build
            # completes; a mid-iteration exception empties an index and
            # leaves its counter standing, so `actual` collapses,
            # `expected` does not, and `ok` goes False with the two
            # halves named in the context.
            #
            # THE TWO EARLY RETURNS ABOVE EMIT NOTHING, and neither is a
            # gap: an empty page has no window to read for, and a failed
            # `live_log_reader` import means the join was never attempted
            # rather than attempted and lost.
            _bucketed = (
                sum(len(v) for v in self._page_gate_index.values())
                + sum(len(v) for v in self._page_voting_index.values()))
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _hist_emit
                _hist_emit(
                    "history.05.006.postcondition.joiner_indexes_built",
                    actual=_bucketed,
                    expected=_gate_accepted + _voting_accepted,
                    context={"gate_accepted": _gate_accepted,
                             "voting_accepted": _voting_accepted,
                             "gate_buckets": len(self._page_gate_index),
                             "voting_buckets": len(self._page_voting_index),
                             "page_rows": len(page_rows)},
                    duration=_join_s)

        @staticmethod
        def _parse_entry_ts(s: str) -> Optional[float]:
            """Parse an ISO-8601 log-entry timestamp into unix seconds.
            Returns None on parse failure (fail-soft per R28 FL)."""
            if not s:
                return None
            try:
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                return datetime.fromisoformat(s).timestamp()
            except (ValueError, TypeError):
                return None

        # _resolve_bot_id_for_row + _lookup_gate_marker + _lookup_voting_marker
        # removed v3.23.71. Their logic moved to src.gui.history_helpers where
        # it is pure/testable; the render path in _render_page now calls the
        # module-level helpers directly (see the v3.23.71 H2/H3 block above).

        def _prev_page(self) -> None:
            self._page -= 1
            self._render_page()

        def _next_page(self) -> None:
            self._page += 1
            self._render_page()

        # ── CSV export ───────────────────────────────────────────────────
        def _export_csv(self) -> None:
            if not self._filtered:
                QMessageBox.information(
                    self, "No data", "Nothing to export — apply filters or "
                                      "refresh first.")
                return
            default_name = (
                f"acervator_history_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            path, _ = QFileDialog.getSaveFileName(
                self, "Export trade history",
                default_name, "CSV files (*.csv)")
            if not path:
                return
            # 10.3 -- THE BRACKET OPENS BELOW THE FILE DIALOG.
            #
            # `QFileDialog.getSaveFileName` blocks until the operator
            # picks a path. That wait is human time, it is unbounded,
            # and it is not export cost. Including it would put a
            # coffee break on the record as disk latency, and item 17
            # reads this number as latency.
            #
            # What the bracket DOES span is the write and the read-back:
            # both touch the same file, both are the export, and a slow
            # or full disk shows in either. `readback` in the context
            # already says whether the second half ran, so a reader can
            # tell a whole reading from a half one.
            _export_t0 = time.monotonic()
            try:
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow([
                        "timestamp_utc", "exchange", "symbol", "bot",
                        "side", "amount", "price", "cost_usd",
                        "fee", "fee_currency", "trade_id"])
                    for r in self._filtered:
                        dt = r.get("datetime")
                        ts_str = (dt.strftime("%Y-%m-%d %H:%M:%S")
                                  if dt is not None else "")
                        bot_label = _resolve_bot_label(
                            self._bot_manager,
                            r.get("exchange", ""),
                            r.get("symbol", ""))
                        w.writerow([
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
                        ])
                # 05.007 -- COUNT THE FILE'S OWN ROWS, NOT THE ROWS
                # THAT WERE HANDED TO THE WRITER.
                #
                # The message box below already reports
                # `len(self._filtered)`, which is the ASK. Nothing has
                # ever read the artifact. A row whose formatting raised,
                # a short write, a full disk, a path that resolved
                # somewhere else -- each of those leaves the operator
                # with a confident "Wrote N rows" and a file holding
                # fewer.
                #
                # Read back through `csv.reader`, the same module and
                # dialect that wrote it, so a quoted field carrying a
                # comma or a newline counts as one record and not as
                # two. Minus one for the header row.
                #
                # A read-back that itself fails records -1, which equals
                # no row count and therefore reports `ok` False. That is
                # deliberate: UNVERIFIED IS NOT VERIFIED, and `readback`
                # in the context says which of the two happened. It is
                # caught separately from the write so an unreadable file
                # is never reported to the operator as a failed export.
                _written = -1
                try:
                    with open(path, "r", newline="",
                              encoding="utf-8") as _rf:
                        _written = sum(1 for _ in csv.reader(_rf)) - 1
                except (OSError, csv.Error) as _rb_exc:
                    logger.debug(
                        "history csv read-back failed: %s", _rb_exc)
                _export_s = time.monotonic() - _export_t0
                with contextlib.suppress(Exception):
                    from src.core.signal_contract import emit as _hist_emit
                    _hist_emit(
                        "history.05.007.postcondition.csv_exported",
                        actual=_written, expected=len(self._filtered),
                        context={"readback": _written >= 0,
                                 "loaded": len(self._all_trades)},
                        duration=_export_s)
                QMessageBox.information(
                    self, "Export complete",
                    f"Wrote {len(self._filtered)} rows to:\n{path}")
            except Exception as exc:
                logger.exception("CSV export raised")
                QMessageBox.warning(
                    self, "Export failed",
                    f"Could not write CSV:\n\n{type(exc).__name__}: {exc}")
