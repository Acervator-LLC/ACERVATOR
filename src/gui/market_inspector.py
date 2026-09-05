"""market_inspector.py — Market Inspector tab.

Top-level tab that renders the HTF entry-opportunity view. Owns the
fetch cycle and writes results to the module-level shared
MarketInspector (`src.trading.market_inspector.get_shared_inspector`).
The Bot Details per-bot Market Inspector tab reads back from the same
shared analyzer via ``build_per_bot_view()``.

Two panels stacked in a scroll area:

  1. Filter row: [Refresh] button, [ ] Show active markets checkbox,
     last-updated + source badge.
  2. HTF Signals table: per-market row with signal chip, aggregate
     score, and D/W BB position + tightening state.
  3. Opposing Pairs table: long-side / short-side / 30-day correlation.

Refresh cadence is enforced by the fetcher: it serves the last network
result while it is younger than DEFAULT_MIN_REFRESH_S (15 min), and goes
to the network when the Refresh button passes force_network=True. Before
v3.25.9 neither half existed -- the constant was never read and the
parameter did not exist, so every refresh hit the venue.

sadp: R28 SSS + R70 RCN
v3.23.37 — Initial implementation.
"""

from __future__ import annotations

import logging

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


if _HAS_QT:

    class MarketInspectorTab(QWidget):
        """Full-application Market Inspector tab.

        Fleet-wide HTF signal view over the top-N CoinGecko universe.
        Owns the fetch worker and writes results to the shared analyzer.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
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

            self._active_symbols: set = set()
            self._show_active = False  # Default: hide markets already traded
            self._last_meta: dict = {}
            self._pending_refresh = False
            # Wired by MainWindow's MarketInspectorTabMixin via set_exchange_source().
            self._connectors_getter = None
            self._scheduler = None

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
            layout.addLayout(top_row)

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
            layout.addWidget(self._signals_group)

            # --- Opposing Pairs table ---
            self._pairs_group = QGroupBox("Opposing Pairs (30-day Pearson)")
            pg = QVBoxLayout(self._pairs_group)
            self._pairs_tbl = QTableWidget()
            self._pairs_tbl.setColumnCount(4)
            self._pairs_tbl.setHorizontalHeaderLabels(
                ["Long side", "Short side", "Correlation", "Score (Long+Short)"]
            )
            self._pairs_tbl.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents
            )
            self._pairs_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            self._pairs_tbl.setAlternatingRowColors(True)
            self._pairs_tbl.setMaximumHeight(180)
            pg.addWidget(self._pairs_tbl)
            layout.addWidget(self._pairs_group)

            layout.addStretch()

            # v3.23.68 — right pane hosts the topology-proposal cards.
            try:
                from .market_inspector_topologies import MarketInspectorTopologies

                self._topologies_pane = MarketInspectorTopologies()
            except Exception as _tp_exc:  # noqa: BLE001 - GUI import guard
                logger.debug("topologies pane unavailable: %s", _tp_exc)
                self._topologies_pane = QWidget()

            self._outer_splitter.addWidget(left_pane)
            self._outer_splitter.addWidget(self._topologies_pane)
            # (dismiss-store wiring: see set_dismiss_store below — the
            # owner supplies it, this tab never resolves settings itself)
            self._outer_splitter.setStretchFactor(0, 1)
            self._outer_splitter.setStretchFactor(1, 1)
            self._outer_splitter.setSizes([800, 800])

        # ── external API ─────────────────────────────────────────────
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

        def current_topology_proposals(self) -> list:
            """Proposals currently on display, for a SIMULATOR to stress.

            v3.24.79 — the read half of the topology seam. Nuclear Mode
            pulls these at Start and wires them across sim bots, which
            is the topology injection the mode exists to exercise.
            (The operator's "strategy injection" wording; in Market
            Inspector a strategy IS a topology — same thing, and the
            precise term is topology.)

            Distinct from `set_adopt_handler` above in the way that
            matters: adoption creates real bots and wires on the live
            fleet, while this only lets a simulator read the shape.
            Returns [] if the pane never constructed, so a build without
            the topology UI loses injections rather than the ability to
            run a soak.
            """
            pane = getattr(self, "_topologies_pane", None)
            getter = getattr(pane, "current_proposals", None)
            if getter is None:
                return []
            try:
                return list(getter() or [])
            except Exception as exc:  # noqa: BLE001 - optional producer
                logger.debug("topology proposal read failed: %s", exc)
                return []

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

        # ── fetch cycle ──────────────────────────────────────────────
        def _start_fetch(self, force: bool = False) -> None:
            if self._pending_refresh:
                return
            if not (self._connectors_getter and self._scheduler):
                self._status_lbl.setText(
                    "Exchange source not wired — restart the app "
                    "after connecting an exchange."
                )
                return
            connectors = self._connectors_getter() or {}
            if not connectors:
                self._status_lbl.setText(
                    "No exchange connectors — connect an exchange "
                    "on the Trading tab first."
                )
                return
            self._pending_refresh = True
            self._refresh_btn.setEnabled(False)
            self._status_lbl.setText("Fetching…")
            try:
                self._scheduler(self._fetch_and_analyze(connectors, force=force))
            except Exception as exc:  # noqa: BLE001 - scheduler failure
                self._pending_refresh = False
                self._refresh_btn.setEnabled(True)
                self._status_lbl.setText(f"Scheduler error: {exc}")

        async def _fetch_and_analyze(
            self, connectors: dict, force: bool = False
        ) -> None:
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
                self._refresh_btn.setEnabled(True)
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
                self._status_lbl.setText(f"Analyzer error: {exc}")
            self._pending_refresh = False
            self._refresh_btn.setEnabled(True)
            self._render_signals()

        def _on_progress(self, msg: str) -> None:
            self._status_lbl.setText(msg)

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

        def _render_signals(self) -> None:
            try:
                from ..trading.market_inspector import get_shared_inspector

                inspector = get_shared_inspector()
            except Exception:  # noqa: BLE001 - analyzer import guard
                self._status_lbl.setText("Analyzer unavailable.")
                return

            self._status_lbl.setText(self._status_line())

            # Signals table
            signals = inspector.last_signals
            if not self._show_active:
                signals = [s for s in signals if not s.is_active]
            # Sort by score desc; only show scored rows (skip NONE).
            signals = [s for s in signals if s.score > 0.0]
            self._signals_tbl.setRowCount(len(signals))
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

            # Opposing pairs table
            pairs = inspector.last_pairs
            self._pairs_tbl.setRowCount(len(pairs))
            for row, p in enumerate(pairs):
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
                corr_item = QTableWidgetItem(f"{p.correlation_30d:+.3f}")
                corr_item.setForeground(QColor("#ffcc66"))
                self._pairs_tbl.setItem(row, 2, corr_item)
                self._pairs_tbl.setItem(
                    row,
                    3,
                    QTableWidgetItem(f"{p.long_side.score + p.short_side.score:.2f}"),
                )

    def build_per_bot_view(bot) -> QWidget:
        """Build the Bot Details per-bot Market Inspector tab widget.

        Reads the shared analyzer's most recent scan and renders:
          - The bot's asset card (if the scan reached it)
          - Top-5 higher-scoring markets in the universe
          - Opposing pairs featuring the bot's asset
        """
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        # Get shared analyzer
        try:
            from ..trading.market_inspector import get_shared_inspector

            inspector = get_shared_inspector()
        except Exception:  # noqa: BLE001 - analyzer import guard
            layout.addWidget(QLabel("Market Inspector analyzer unavailable."))
            layout.addStretch()
            return w

        # Determine this bot's base asset
        asset = ""
        try:
            sym = getattr(bot.config, "symbol", "")
            asset = sym.split("/")[0].upper() if "/" in sym else sym.upper()
        except Exception:  # noqa: BLE001 - symbol parse best-effort
            asset = ""

        signals = inspector.last_signals
        if not signals:
            msg = QLabel(
                "<b>No Market Inspector scan yet.</b><br><br>"
                "Open the Market Inspector top-level tab and press "
                "Refresh to populate. The scan runs across the top-50 "
                "CoinGecko markets on daily and weekly candles; results "
                "are shared between the top-level tab and this per-bot "
                "view."
            )
            msg.setStyleSheet("color: #aaa; padding: 12px;")
            msg.setWordWrap(True)
            layout.addWidget(msg)
            layout.addStretch()
            return w

        # This bot's asset card
        own_signal = inspector.get_signal(asset)
        card = QGroupBox(f"This Bot's Asset — {asset or '?'}")
        cv = QVBoxLayout(card)
        if own_signal is None:
            cv.addWidget(
                QLabel(
                    f"No signal for {asset or 'this asset'} in the current "
                    f"scan. The universe covers CoinGecko top-50; markets "
                    f"outside that set are not tracked."
                )
            )
        else:
            sig_lbl = QLabel(
                f"Signal: <b>{own_signal.signal}</b>  |  "
                f"Score: {own_signal.score:.2f}  |  "
                f"Direction: {own_signal.direction or '—'}"
            )
            sig_lbl.setStyleSheet(
                f"color: {_signal_color(own_signal.signal)}; " "font-size: 13px;"
            )
            cv.addWidget(sig_lbl)
            for tf_key in ("1d", "1w"):
                a = own_signal.per_tf.get(tf_key)
                cv.addWidget(QLabel(f"{tf_key}: {_fmt_tf_state(a)}"))
        layout.addWidget(card)

        # Higher-scoring markets
        higher = [
            s
            for s in signals
            if s.score > (own_signal.score if own_signal else 0.0) and s.symbol != asset
        ][:5]
        if higher:
            hg = QGroupBox("Higher-Scoring Markets (top-5)")
            hv = QVBoxLayout(hg)
            for s in higher:
                row = QLabel(
                    f"{s.symbol}  ·  {s.signal}  ·  score {s.score:.2f}"
                    + ("  ·  ACTIVE" if s.is_active else "")
                )
                row.setStyleSheet(
                    f"color: {_signal_color(s.signal)}; " "font-family: monospace;"
                )
                hv.addWidget(row)
            layout.addWidget(hg)

        # Opposing pairs featuring this asset
        pairs = inspector.last_pairs
        rel_pairs = [
            p
            for p in pairs
            if p.long_side.symbol == asset or p.short_side.symbol == asset
        ]
        if rel_pairs:
            pg = QGroupBox("Opposing Pairs Featuring This Asset")
            pv = QVBoxLayout(pg)
            for p in rel_pairs:
                pv.addWidget(
                    QLabel(
                        f"{p.long_side.symbol} (long) ⇄ "
                        f"{p.short_side.symbol} (short)  ·  "
                        f"corr {p.correlation_30d:+.3f}"
                    )
                )
            layout.addWidget(pg)

        layout.addStretch()
        return w
