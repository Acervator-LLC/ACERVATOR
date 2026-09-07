"""``MarketInspectorTab``, the Market Inspector tab.

``MarketInspectorTab`` owns the fetch cycle and writes each scan into the
analyzer ``get_shared_inspector`` returns, which ``build_per_bot_view``
reads back for the Bot Details page. ``scan_state`` reports whether a
scan has been asked for, is running, or has finished, and
``_empty_table_text`` turns that state into the sentence an empty table
carries. ``_emit_scan`` publishes ``SCAN_STARTED_TOPIC`` and
``SCAN_FINISHED_TOPIC`` so a run leaves a record of what the scan
covered.
"""

from __future__ import annotations

import logging

from .main_tabs.market_inspector_surface import (
    COLOR_CORRELATION,
    COLOR_METHOD,
    NO_METHOD_TEXT,
    PAIR_COLUMNS,
    PAIRS_GROUP_TITLE,
    TOPOLOGIES_ZONE,
)
from .main_tabs.market_inspector_surface import right_zone_rows as _right_zone_rows

logger = logging.getLogger("acervator.market_inspector_gui")

try:
    from PySide6.QtWidgets import (
        QWidget,
        QVBoxLayout,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QCheckBox,
        QGroupBox,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QSplitter,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


def _fmt_age(seconds: float) -> str:
    s = max(0.0, float(seconds))
    if s < 60:
        return f"{int(s)}s"
    if s < 3600:
        return f"{int(s / 60)} min"
    if s < 86400:
        h = int(s / 3600)
        m = int((s % 3600) / 60)
        return f"{h}h {m}m" if m else f"{h}h"
    return f"{int(s / 86400)} days"


def _signal_color(signal: str) -> str:
    """Colour cue for a MarketInspector signal string."""
    if signal.startswith("ENTRY_LONG_HIGH"):
        return "#00ff88"
    if signal.startswith("ENTRY_LONG"):
        return "#66cc99"
    if signal.startswith("ENTRY_SHORT_HIGH"):
        return "#ff3366"
    if signal.startswith("ENTRY_SHORT"):
        return "#ff9966"
    if signal == "WATCHLIST":
        return "#ffcc00"
    return "#888"


def _fmt_tf_state(a) -> str:
    """One-line rendering of a TimeframeAnalysis for the table cell."""
    if a is None:
        return "—"
    tag = "▲" if a.at_upper_extreme else "▼" if a.at_lower_extreme else "·"
    tight = " T" if a.tightening else ""
    return f"{tag} bb={a.bb_position:.2f} z={a.z_score:+.2f}{tight}"


SCAN_NOT_ASKED = "not_asked"
SCAN_RUNNING = "running"
SCAN_FINISHED = "finished"

SCAN_STARTED_TOPIC = "market_inspector.scan_started"
SCAN_FINISHED_TOPIC = "market_inspector.scan_finished"

SIGNALS_NOUN = "markets"
PAIRS_NOUN = "opposing pairs"

ATA_SPM_MODULE = "ata_spm"
OPPOSING_TRADES_MODULE = "opposing_trades"
ARBITRAGE_MODULE = "arbitrage"

ATA_SPM_GROUP_TITLE = "ATA-SPM"
OPPOSING_TRADES_GROUP_TITLE = "Opposing Trades"
ARBITRAGE_GROUP_TITLE = "Multi-Exchange Arbitrage"

ATA_SPM_UNWIRED_TEXT = "Phase source not wired."
ATA_SPM_NO_RUN_TEXT = "No run yet. Ready to Send holds 0."
ATA_SPM_PHASE_KEY = "phase"
ATA_SPM_READY_KEY = "ready_to_send"

# The share a bullish bot feeds to the bot on the opposite market condition.
OPPOSING_TRADES_PROFIT_SHARE_PCT = 50
OPPOSING_TRADES_NOUN = "opposing trades"

MODULE_STATUS_STYLE = "color: #aaa; font-size: 11px;"


def _empty_table_text(scan_state: str, noun: str) -> str:
    """The sentence an empty table carries for one scan state.

    ``SCAN_NOT_ASKED``, ``SCAN_RUNNING`` and ``SCAN_FINISHED`` each get
    their own wording, so the three never read alike.
    """
    if scan_state == SCAN_RUNNING:
        return f"Scanning for {noun}…"
    if scan_state == SCAN_FINISHED:
        return f"Scan finished. No {noun} found."
    return f"No scan yet. Press Refresh to look for {noun}."


def _ata_spm_text(run) -> str:
    """The ATA-SPM region's line for what the phase source reports.

    ``None`` says no source is wired, an empty report says no run has
    been made, and a report carrying a phase names it beside the count
    the Ready to Send bucket holds.
    """
    if run is None:
        return ATA_SPM_UNWIRED_TEXT
    phase = str(run.get(ATA_SPM_PHASE_KEY) or "")
    if not phase:
        return ATA_SPM_NO_RUN_TEXT
    count = int(run.get(ATA_SPM_READY_KEY) or 0)
    return f"{phase}. Ready to Send holds {count}."


def _opposing_trades_text(scan_state: str, count: int) -> str:
    """The Opposing Trades region's line for one scan state and pair count.

    An unasked, a running and a finished scan each get their own
    wording, and a finished scan holding pairs names the profit share
    the bullish side feeds to the opposite one.
    """
    found = int(count or 0)
    if scan_state != SCAN_FINISHED or not found:
        return _empty_table_text(scan_state, OPPOSING_TRADES_NOUN)
    return (
        f"{found} {OPPOSING_TRADES_NOUN}. "
        f"{OPPOSING_TRADES_PROFIT_SHARE_PCT}% of profit goes to the opposite side."
    )


def _arbitrage_text(connectors) -> str:
    """The Multi-Exchange Arbitrage region's line for the venues in reach.

    ``None`` says no exchange source is wired, which no caller can
    confuse with a wired source carrying no connector. One venue names
    itself and says a second is needed to compare.
    """
    if connectors is None:
        return "Exchange source not wired."
    names = sorted(str(one) for one in connectors)
    if not names:
        return "No exchange connected."
    joined = ", ".join(names)
    if len(names) == 1:
        return f"1 venue connected: {joined}. A second venue is needed to compare."
    return f"{len(names)} venues connected: {joined}."


def _left_module_rows(run, scan_state: str, pair_count: int, connectors) -> list:
    """The three left-side regions as key, title and status, in screen order."""
    return [
        [ATA_SPM_MODULE, ATA_SPM_GROUP_TITLE, _ata_spm_text(run)],
        [
            OPPOSING_TRADES_MODULE,
            OPPOSING_TRADES_GROUP_TITLE,
            _opposing_trades_text(scan_state, pair_count),
        ],
        [ARBITRAGE_MODULE, ARBITRAGE_GROUP_TITLE, _arbitrage_text(connectors)],
    ]


def _emit_scan(topic: str, **fields) -> None:
    """Publish one scan record on the event bus.

    An event bus that cannot be reached leaves a debug line and never
    stops the scan that was reporting.
    """
    try:
        from ..core.event_bus import get_event_bus

        get_event_bus().emit(topic, **fields)
    except ImportError as exc:
        logger.debug("market inspector emit %s unavailable: %s", topic, exc)


if _HAS_QT:

    class MarketInspectorTab(QWidget):
        """Full-application Market Inspector tab.

        Fleet-wide HTF signal view over the top-N CoinGecko universe.
        Owns the fetch worker and writes results to the shared analyzer.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self._active_symbols: set = set()
            self._show_active = False  # Default: hide markets already traded
            self._last_meta: dict = {}
            self._pending_refresh = False
            self._scan_state = SCAN_NOT_ASKED
            # Wired by MainWindow's MarketInspectorTabMixin via set_exchange_source().
            self._connectors_getter = None
            self._scheduler = None
            self._ata_run_source = None
            self._build_ui()

        def _build_ui(self) -> None:
            """Build the splitter, the three modules, the filter row and the tables.

            The modules are ATA-SPM, Opposing Trades and Multi-Exchange
            Arbitrage, in that order above the filter row.
            ``MarketInspectorReactTab`` replaces this with one web view and
            keeps every method below it.
            """
            # Splitter panes: left is the HTF/Opposing content, right the proposals.
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            outer.setSpacing(0)
            self._outer_splitter = QSplitter(Qt.Horizontal)
            outer.addWidget(self._outer_splitter)

            left_pane = QWidget()
            layout = QVBoxLayout(left_pane)
            layout.setContentsMargins(6, 6, 6, 6)
            layout.setSpacing(6)

            # --- The three left-side zones ---
            self._module_labels: dict = {}
            self._module_boxes: dict = {}
            for key, title, status in _left_module_rows(
                None, self._scan_state, 0, None
            ):
                group = QGroupBox(title)
                box = QVBoxLayout(group)
                line = QLabel(status)
                line.setStyleSheet(MODULE_STATUS_STYLE)
                line.setWordWrap(True)
                box.addWidget(line)
                layout.addWidget(group)
                self._module_labels[key] = line
                self._module_boxes[key] = box
            zone = self._module_boxes[OPPOSING_TRADES_MODULE]

            # --- Filter row ---
            top_row = QHBoxLayout()
            top_row.setSpacing(8)
            self._refresh_btn = QPushButton("Refresh")
            self._refresh_btn.setToolTip(
                "Fetch HTF OHLCV from the connected exchange(s). "
                "Universe = top-volume */USD markets on those "
                "exchanges (active bot targets are always included). "
                "Runs on the app's async loop; typical time ~10-30 s "
                "depending on exchange rate limits."
            )
            self._refresh_btn.clicked.connect(lambda: self._start_fetch(force=True))
            top_row.addWidget(self._refresh_btn)

            self._show_active_chk = QCheckBox("Include active markets")
            self._show_active_chk.setChecked(False)
            self._show_active_chk.setToolTip(
                "By default the Market Inspector focuses on markets "
                "you are NOT already trading. Check this to include "
                "your active bot targets in the table."
            )
            self._show_active_chk.toggled.connect(self._on_toggle_show_active)
            top_row.addWidget(self._show_active_chk)

            top_row.addStretch()
            self._status_lbl = QLabel("No data yet — press Refresh.")
            self._status_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            top_row.addWidget(self._status_lbl)
            zone.addLayout(top_row)

            # --- HTF Signals table ---
            self._signals_group = QGroupBox("HTF Signals")
            sg = QVBoxLayout(self._signals_group)
            self._signals_tbl = QTableWidget()
            self._signals_tbl.setColumnCount(6)
            self._signals_tbl.setHorizontalHeaderLabels(
                ["Asset", "Signal", "Score", "Daily", "Weekly", "Active"]
            )
            self._signals_tbl.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents
            )
            self._signals_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            self._signals_tbl.setAlternatingRowColors(True)
            self._signals_tbl.setMaximumHeight(360)
            sg.addWidget(self._signals_tbl)
            self._signals_empty_lbl = QLabel(
                _empty_table_text(self._scan_state, SIGNALS_NOUN)
            )
            self._signals_empty_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            self._signals_empty_lbl.setWordWrap(True)
            sg.addWidget(self._signals_empty_lbl)
            zone.addWidget(self._signals_group)

            # --- Opposing Pairs table ---
            self._pairs_group = QGroupBox(PAIRS_GROUP_TITLE)
            pg = QVBoxLayout(self._pairs_group)
            self._pairs_tbl = QTableWidget()
            self._pairs_tbl.setColumnCount(len(PAIR_COLUMNS))
            self._pairs_tbl.setHorizontalHeaderLabels(list(PAIR_COLUMNS))
            self._pairs_tbl.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents
            )
            self._pairs_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            self._pairs_tbl.setAlternatingRowColors(True)
            self._pairs_tbl.setMaximumHeight(180)
            pg.addWidget(self._pairs_tbl)
            self._pairs_empty_lbl = QLabel(
                _empty_table_text(self._scan_state, PAIRS_NOUN)
            )
            self._pairs_empty_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
            self._pairs_empty_lbl.setWordWrap(True)
            pg.addWidget(self._pairs_empty_lbl)
            zone.addWidget(self._pairs_group)

            layout.addStretch()

            # v3.23.68 — right pane hosts the topology-proposal cards.
            try:
                from .market_inspector_topologies import MarketInspectorTopologies

                self._topologies_pane = MarketInspectorTopologies()
            except Exception as _tp_exc:  # noqa: BLE001 - GUI import guard
                logger.debug("topologies pane unavailable: %s", _tp_exc)
                self._topologies_pane = QWidget()

            right_pane = QWidget()
            right_layout = QVBoxLayout(right_pane)
            right_layout.setContentsMargins(6, 6, 6, 6)
            right_layout.setSpacing(6)
            self._zone_labels: dict = {}
            for key, title, status in _right_zone_rows(None):
                group = QGroupBox(title)
                box = QVBoxLayout(group)
                if key == TOPOLOGIES_ZONE:
                    box.addWidget(self._topologies_pane)
                    right_layout.addWidget(group, 1)
                    continue
                line = QLabel(status)
                line.setStyleSheet(MODULE_STATUS_STYLE)
                line.setWordWrap(True)
                box.addWidget(line)
                right_layout.addWidget(group)
                self._zone_labels[key] = line

            self._outer_splitter.addWidget(left_pane)
            self._outer_splitter.addWidget(right_pane)
            # (dismiss-store wiring: see set_dismiss_store below — the
            # owner supplies it, this tab never resolves settings itself)
            self._outer_splitter.setStretchFactor(0, 1)
            self._outer_splitter.setStretchFactor(1, 1)
            self._outer_splitter.setSizes([800, 800])
            self._render_empty_notes()

        # ── the three left-side modules ──────────────────────────────
        def set_ata_run_source(self, getter) -> None:
            """Take the callable the ATA-SPM region reads its run report from.

            ``getter`` is a zero-arg callable answering the phase and the
            Ready to Send count. Until one is wired the region says so.
            """
            self._ata_run_source = getter
            self._render_left_modules()

        def _ata_run(self):
            """The ATA-SPM run report, or None while no source answers."""
            getter = self._ata_run_source
            if getter is None:
                return None
            try:
                return dict(getter() or {})
            except Exception as exc:  # noqa: BLE001 - optional producer
                logger.debug("ATA-SPM run read failed: %s", exc)
                return None

        def _connectors_now(self):
            """The exchange connectors in reach, or None while none is wired."""
            if not (self._connectors_getter and self._scheduler):
                return None
            try:
                return dict(self._connectors_getter() or {})
            except Exception as exc:  # noqa: BLE001 - optional producer
                logger.debug("exchange connector read failed: %s", exc)
                return None

        def _render_left_modules(self) -> None:
            """Write each left-side module's line from the state it can read."""
            rows = _left_module_rows(
                self._ata_run(),
                self._scan_state,
                self._pairs_tbl.rowCount(),
                self._connectors_now(),
            )
            for key, _title, status in rows:
                line = self._module_labels.get(key)
                if line is not None:
                    line.setText(status)
            for key, _title, status in _right_zone_rows(self._ata_run()):
                line = self._zone_labels.get(key)
                if line is not None:
                    line.setText(status)

        # ── the widgets the logic below writes through ───────────────
        def _set_status(self, text: str) -> None:
            """Show ``text`` on the status line."""
            self._status_lbl.setText(text)

        def _set_refresh_enabled(self, enabled: bool) -> None:
            """Let the operator press Refresh, or refuse while a scan runs."""
            self._refresh_btn.setEnabled(bool(enabled))

        def _fill_signal_rows(self, signals: list) -> None:
            """Draw one HTF Signals row per entry of ``signals``."""
            self._signals_tbl.setRowCount(len(signals))
            self._render_empty_notes()
            for row, s in enumerate(signals):
                self._signals_tbl.setItem(row, 0, QTableWidgetItem(s.symbol))
                sig_item = QTableWidgetItem(s.signal)
                sig_item.setForeground(QColor(_signal_color(s.signal)))
                self._signals_tbl.setItem(row, 1, sig_item)
                self._signals_tbl.setItem(row, 2, QTableWidgetItem(f"{s.score:.2f}"))
                self._signals_tbl.setItem(
                    row, 3, QTableWidgetItem(_fmt_tf_state(s.per_tf.get("1d")))
                )
                self._signals_tbl.setItem(
                    row, 4, QTableWidgetItem(_fmt_tf_state(s.per_tf.get("1w")))
                )
                active_item = QTableWidgetItem("yes" if s.is_active else "—")
                if s.is_active:
                    active_item.setForeground(QColor("#00ccff"))
                self._signals_tbl.setItem(row, 5, active_item)

        def _fill_pair_rows(self, pairs: list) -> None:
            """Draw one Opposing Pairs row per entry of ``pairs``."""
            self._pairs_tbl.setRowCount(len(pairs))
            self._render_empty_notes()
            for row, p in enumerate(pairs):
                method = getattr(p, "method", None)
                self._pairs_tbl.setItem(
                    row,
                    0,
                    QTableWidgetItem(f"{p.long_side.symbol} ({p.long_side.signal})"),
                )
                self._pairs_tbl.setItem(
                    row,
                    1,
                    QTableWidgetItem(f"{p.short_side.symbol} ({p.short_side.signal})"),
                )
                method_item = QTableWidgetItem(
                    method.label if method else NO_METHOD_TEXT
                )
                method_item.setForeground(QColor(COLOR_METHOD))
                self._pairs_tbl.setItem(row, 2, method_item)
                self._pairs_tbl.setItem(
                    row,
                    3,
                    QTableWidgetItem(method.window_text if method else NO_METHOD_TEXT),
                )
                self._pairs_tbl.setItem(
                    row,
                    4,
                    QTableWidgetItem(
                        method.statistic_text if method else NO_METHOD_TEXT
                    ),
                )
                corr_item = QTableWidgetItem(f"{p.correlation_30d:+.3f}")
                corr_item.setForeground(QColor(COLOR_CORRELATION))
                self._pairs_tbl.setItem(row, 5, corr_item)
                self._pairs_tbl.setItem(
                    row,
                    6,
                    QTableWidgetItem(f"{p.long_side.score + p.short_side.score:.2f}"),
                )

        # ── external API ─────────────────────────────────────────────
        def scan_state(self) -> str:
            """Whether a scan is unasked, running, or finished.

            One of ``SCAN_NOT_ASKED``, ``SCAN_RUNNING`` or
            ``SCAN_FINISHED``, which is what tells an empty table apart
            from one waiting on a scan nobody started.
            """
            return self._scan_state

        def update_active_symbols(self, bot_statuses: list) -> None:
            """Refresh the active-symbol set from the current bot roster.
            Called by the main window whenever the bot list changes."""
            active: set = set()
            for s in bot_statuses or []:
                sym = s.get("symbol", "")
                if "/" in sym:
                    active.add(sym.split("/")[0].upper())
                elif sym:
                    active.add(sym.upper())
            self._active_symbols = active
            self._render_signals()

        def set_dismiss_store(self, store) -> None:
            """Forward ``store`` to ``_topologies_pane`` for dismissal persistence.

            No-op when the topologies import failed and the pane is a
            plain ``QWidget``.
            """
            pane = getattr(self, "_topologies_pane", None)
            if pane is not None and hasattr(pane, "set_dismiss_store"):
                pane.set_dismiss_store(store)

        def set_proposal_source(self, getter) -> None:
            """Wire the topology-proposal source into ``_topologies_pane``.

            ``getter`` is a zero-arg callable returning ``list[dict]``.
            No-op when the pane was not constructed.
            """
            pane = getattr(self, "_topologies_pane", None)
            if pane is None:
                return
            if hasattr(pane, "set_proposal_source"):
                pane.set_proposal_source(getter)

        def set_adopt_handler(self, handler) -> None:
            """v3.23.69 — wire the Adopt handoff (proposal → main window).

            ``handler`` receives one proposal dict and orchestrates the
            wizard + wire flow. No-op if the pane wasn't constructed.
            """
            pane = getattr(self, "_topologies_pane", None)
            if pane is None:
                return
            adopt_signal = getattr(pane, "adoptRequested", None)
            if adopt_signal is None:
                return
            adopt_signal.connect(handler)

        def current_topology_proposals(self) -> "list | None":
            """The proposals on display, for a simulator to read and wire.

            ``None`` says the right pane never built or refused the read,
            and a list says the pane answered. An empty list therefore
            means the pane holds no proposals, which no caller can
            confuse with a pane that is not there.

            Distinct from ``set_adopt_handler``: adopting creates real
            bots and wires on the live fleet, while this only lets a
            simulator read the shape.
            """
            pane = getattr(self, "_topologies_pane", None)
            getter = getattr(pane, "current_proposals", None)
            if getter is None:
                return None
            try:
                return list(getter() or [])
            except Exception as exc:  # noqa: BLE001 - optional producer
                logger.debug("topology proposal read failed: %s", exc)
                return None

        def set_exchange_source(self, connectors_getter, scheduler) -> None:
            """Wire the exchange-based data path.

            ``connectors_getter`` is a zero-arg callable returning the
            main window's ``{exchange_id: connector}`` dict at call
            time (so the tab always sees the current set).
            ``scheduler`` accepts a coroutine and schedules it on the
            app's asyncio loop.
            """
            self._connectors_getter = connectors_getter
            self._scheduler = scheduler
            self._render_left_modules()

        # ── fetch cycle ──────────────────────────────────────────────
        def _start_fetch(self, force: bool = False) -> None:
            if self._pending_refresh:
                return
            if not (self._connectors_getter and self._scheduler):
                self._set_status(
                    "Exchange source not wired — restart the app "
                    "after connecting an exchange."
                )
                return
            connectors = self._connectors_getter() or {}
            if not connectors:
                self._set_status(
                    "No exchange connectors — connect an exchange "
                    "on the Trading tab first."
                )
                return
            self._pending_refresh = True
            self._scan_state = SCAN_RUNNING
            self._set_refresh_enabled(False)
            self._set_status("Fetching…")
            self._render_empty_notes()
            self._render_left_modules()
            logger.info(
                "market inspector scan started: forced=%s connectors=%d "
                "active_symbols=%d",
                bool(force),
                len(connectors),
                len(self._active_symbols),
            )
            _emit_scan(
                SCAN_STARTED_TOPIC,
                forced=bool(force),
                connector_count=len(connectors),
                active_symbols=len(self._active_symbols),
            )
            try:
                self._scheduler(self._fetch_and_analyze(connectors, force=force))
            except Exception as exc:  # noqa: BLE001 - scheduler failure
                self._pending_refresh = False
                self._scan_state = SCAN_FINISHED
                self._set_refresh_enabled(True)
                self._set_status(f"Scheduler error: {exc}")
                self._finish_scan_record(0.0, error=f"scheduler: {exc}")
                self._render_empty_notes()
                self._render_left_modules()

        async def _fetch_and_analyze(
            self, connectors: dict, force: bool = False
        ) -> None:
            import time as _time

            started_at = _time.monotonic()
            try:
                from src.exchange.market_inspector_fetcher import fetch_htf_universe

                res = await fetch_htf_universe(
                    connectors,
                    active_symbols=self._active_symbols,
                    progress_cb=self._on_progress,
                    force_network=force,
                )
            except Exception as exc:  # noqa: BLE001 - fetcher surface
                logger.exception("market inspector fetch failed: %s", exc)
                self._last_meta = {
                    "source": "error",
                    "age_seconds": 0.0,
                    "error": str(exc),
                    "symbol_count": 0,
                }
                self._pending_refresh = False
                self._scan_state = SCAN_FINISHED
                self._set_refresh_enabled(True)
                self._finish_scan_record(_time.monotonic() - started_at, error=str(exc))
                self._render_signals()
                return
            self._last_meta = dict(res.meta or {})
            try:
                from ..trading.market_inspector import get_shared_inspector

                inspector = get_shared_inspector()
                inspector.scan_universe(
                    res.candles_by_symbol_by_tf,
                    self._active_symbols,
                    res.closes_by_symbol,
                )
            except Exception as exc:  # noqa: BLE001 - analyzer surface
                logger.exception("market inspector scan failed: %s", exc)
                self._set_status(f"Analyzer error: {exc}")
                self._pending_refresh = False
                self._scan_state = SCAN_FINISHED
                self._set_refresh_enabled(True)
                self._finish_scan_record(_time.monotonic() - started_at, error=str(exc))
                self._render_signals()
                return
            self._pending_refresh = False
            self._scan_state = SCAN_FINISHED
            self._set_refresh_enabled(True)
            self._finish_scan_record(_time.monotonic() - started_at)
            self._render_signals()

        def _on_progress(self, msg: str) -> None:
            self._set_status(msg)

        def _finish_scan_record(self, duration_s: float, error: str = "") -> None:
            """Log and publish what the scan just covered and how long it took.

            Reads the counts back off the shared analyzer, so the record
            carries what the scan produced rather than what it requested.
            """
            signal_count = 0
            pair_count = 0
            try:
                from ..trading.market_inspector import get_shared_inspector

                inspector = get_shared_inspector()
                signal_count = len(inspector.last_signals or [])
                pair_count = len(inspector.last_pairs or [])
            except Exception as exc:  # noqa: BLE001 - analyzer surface
                logger.debug("market inspector count read failed: %s", exc)
            meta = self._last_meta or {}
            market_count = int(meta.get("symbol_count", 0) or 0)
            source = str(meta.get("source", "?"))
            logger.info(
                "market inspector scan finished: %d market(s), %d signal(s), "
                "%d pair(s) in %.2fs source=%s%s",
                market_count,
                signal_count,
                pair_count,
                duration_s,
                source,
                f" error={error}" if error else "",
            )
            _emit_scan(
                SCAN_FINISHED_TOPIC,
                market_count=market_count,
                duration_s=round(float(duration_s), 3),
                signal_count=signal_count,
                pair_count=pair_count,
                source=source,
                error=error,
            )

        def _render_empty_notes(self) -> None:
            """Show each table's placeholder only while that table is empty.

            The sentence names the scan state, so an empty table says
            whether a scan was never asked for, is running, or finished.
            """
            for table, label, noun in (
                (self._signals_tbl, self._signals_empty_lbl, SIGNALS_NOUN),
                (self._pairs_tbl, self._pairs_empty_lbl, PAIRS_NOUN),
            ):
                label.setText(_empty_table_text(self._scan_state, noun))
                label.setVisible(table.rowCount() == 0)

        # ── rendering ────────────────────────────────────────────────
        def _on_toggle_show_active(self, checked: bool) -> None:
            self._show_active = bool(checked)
            self._render_signals()

        def _status_line(self) -> str:
            meta = self._last_meta or {}
            src = meta.get("source", "?")
            age = float(meta.get("age_seconds", 0.0) or 0.0)
            n = int(meta.get("symbol_count", 0) or 0)
            err = meta.get("error")
            if src == "coingecko":
                return f"Live CoinGecko  ·  {n} markets  ·  just now"
            if src == "cache":
                return f"Snapshot {_fmt_age(age)} old  ·  {n} markets" + (
                    f"  ·  fallback: {err}" if err else ""
                )
            if src == "error":
                return f"Fetch failed: {err or 'unknown'}"
            if src == "network-partial":
                return f"Network partial: {err or 'no OHLC'}"
            return "No data yet — press Refresh."

        def _shown_signals(self, signals: list) -> list:
            """The scored signals the table shows under the active filter."""
            if not self._show_active:
                signals = [s for s in signals if not s.is_active]
            # Sort by score desc; only show scored rows (skip NONE).
            return [s for s in signals if s.score > 0.0]

        def _render_signals(self) -> None:
            try:
                from ..trading.market_inspector import get_shared_inspector

                inspector = get_shared_inspector()
            except Exception:  # noqa: BLE001 - analyzer import guard
                self._set_status("Analyzer unavailable.")
                return

            self._set_status(self._status_line())
            self._fill_signal_rows(self._shown_signals(inspector.last_signals))
            self._fill_pair_rows(list(inspector.last_pairs))
            self._render_empty_notes()
            self._render_left_modules()

    def _per_bot_label(one: dict) -> QLabel:
        """One row of the per-bot view as the label the tab shows."""
        from .main_tabs import market_inspector_tab_surface as mi_surface

        label = QLabel(mi_surface.row_html(one))
        sheet = mi_surface.row_style(one)
        if sheet:
            label.setStyleSheet(sheet)
        if one.get("word_wrap"):
            label.setWordWrap(True)
        return label

    def build_per_bot_view(bot) -> QWidget:
        """Build the Bot Details per-bot Market Inspector tab widget.

        Draws the rows and groups ``market_inspector_tab_surface.per_bot_view``
        reads off the shared analyzer, which is the same description
        ``market_inspector_tab.js`` draws in the React window.
        """
        from .main_tabs import market_inspector_tab_surface as mi_surface

        view = mi_surface.per_bot_view(bot)
        w = QWidget()
        layout = QVBoxLayout(w)
        margin = int(view["margin_px"])
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(int(view["spacing_px"]))
        for one in view["rows"]:
            layout.addWidget(_per_bot_label(one))
        for group in view["groups"]:
            box = QGroupBox(group["title"])
            box.setStyleSheet(mi_surface.group_style())
            inner = QVBoxLayout(box)
            box_margin = mi_surface.GROUP_MARGIN_PX
            inner.setContentsMargins(box_margin, box_margin, box_margin, box_margin)
            inner.setSpacing(mi_surface.GROUP_SPACING_PX)
            for one in group["rows"]:
                inner.addWidget(_per_bot_label(one))
            layout.addWidget(box)
        if view["stretch"]:
            layout.addStretch()
        return w
