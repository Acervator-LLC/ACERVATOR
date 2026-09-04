"""Phantom Bots tab of the Live Bot Settings dialog."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from .. import design_system as ds


class PhantomBotsTabMixin:
    """Phantom timeframe toggles and the phantom state table."""

    # Supplied by BotLiveSettingsDialog at runtime; declared so a
    # type checker can resolve them. Annotations only: no attribute
    # is created and the runtime base stays `object`.
    _bot: Any
    _configure_form: Callable[..., Any]
    _mark_changed: Callable[..., Any]
    _phantom_tf_checks: dict

    # Tab 6: Phantom Bots (v3.23.39 — merged from Phantom Bot +
    # Phantom State per operator directive 2026-07-27).
    def _create_phantom_bots_tab(self) -> QWidget:
        """Combined Phantom Balance Bots config + runtime view.

        Config sections (top): enable toggle, active-TF checkboxes,
        lock duration. Writes route through ScrummingBot's
        ``update_phantom_config`` (phantom state lives on the bot,
        not on BotConfig).

        Runtime sections (below): coordinator status summary,
        per-phantom table (from ``_phantom_mgr.get_phantoms``),
        and cross-bot active-lock table (from ``_coordinator``).
        Everything is scrumming-only.
        """

        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(8)

        bot = self._bot

        info = QLabel(
            "Multi-timeframe shadow bots. Higher TFs override lower TFs.\n"
            "Enable/disable and TF-set changes apply immediately to "
            "NEW phantoms. Already-started phantoms keep their "
            "original configuration until the next bot restart."
        )
        info.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL}; font-size: 11px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # ── Config: Enable toggle ─────────────────────────────────
        enable_group = QGroupBox("Phantom Balance Bots")
        ef = QVBoxLayout(enable_group)
        self._phantom_enable = QCheckBox("Enable Phantom Balance Bots")
        self._phantom_enable.setChecked(bool(getattr(bot, "_phantoms_enabled", False)))
        self._phantom_enable.toggled.connect(
            lambda v: self._mark_changed("enable_phantoms", bool(v))
        )
        ef.addWidget(self._phantom_enable)
        layout.addWidget(enable_group)

        # ── Config: Timeframe checkboxes ─────────────────────────
        tf_group = QGroupBox("Active Timeframes")
        tf_layout = QVBoxLayout(tf_group)
        tf_hint = QLabel(
            "v3.15.61 — TFs not supported by this bot's exchange "
            "are disabled (greyed). Coinbase: 1m/5m/15m/30m/1h/2h/6h/1d. "
            "Binance: full set. Others vary."
        )
        tf_hint.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL}; font-size: 10px;")
        tf_hint.setWordWrap(True)
        tf_layout.addWidget(tf_hint)

        self._phantom_tf_checks: dict = {}
        current_tfs = set(getattr(bot, "_phantom_timeframes", []) or [])
        try:
            from ...exchange.timeframes import available_timeframes

            _ex_id = getattr(bot.config, "exchange_id", None)
            _ph_allowed = set(available_timeframes(_ex_id))
        except Exception:
            _ph_allowed = {
                "1m",
                "5m",
                "15m",
                "30m",
                "1h",
                "2h",
                "4h",
                "6h",
                "12h",
                "1d",
                "1w",
            }
        tf_row = QHBoxLayout()
        for tf in [
            "1m",
            "5m",
            "15m",
            "30m",
            "1h",
            "2h",
            "4h",
            "6h",
            "12h",
            "1d",
            "1w",
        ]:
            cb = QCheckBox(tf)
            supported = tf in _ph_allowed
            cb.setChecked(tf in current_tfs and supported)
            cb.setEnabled(supported)
            cb.setToolTip(
                f"{tf}: "
                + (
                    "supported"
                    if supported
                    else f"NOT supported by exchange "
                    f"({getattr(bot.config, 'exchange_id', '?')})"
                )
            )
            cb.toggled.connect(self._phantom_tfs_changed)
            self._phantom_tf_checks[tf] = cb
            tf_row.addWidget(cb)
        tf_layout.addLayout(tf_row)
        layout.addWidget(tf_group)

        # ── Config: Lock duration ─────────────────────────────────
        lock_group = QGroupBox("Higher-TF Lock Duration")
        lf = QFormLayout(lock_group)
        self._configure_form(lf)
        self._phantom_lock = QSpinBox()
        self._phantom_lock.setRange(1, 10)
        coord = getattr(bot, "_coordinator", None)
        current_lock = int(getattr(coord, "lock_candle_count", 2) if coord else 2)
        self._phantom_lock.setValue(current_lock)
        self._phantom_lock.setToolTip(
            "When a higher-TF phantom locks a lower-TF phantom, "
            "how many candles does the lock persist?"
        )
        self._phantom_lock.valueChanged.connect(
            lambda v: self._mark_changed("lock_candle_count", int(v))
        )
        lf.addRow("Candles to lock:", self._phantom_lock)
        layout.addWidget(lock_group)

        # ── Runtime: Coordinator Status ───────────────────────────
        phantoms_enabled = bool(getattr(bot, "_phantoms_enabled", False))
        phantoms_started = bool(getattr(bot, "_phantoms_started", False))
        phantom_tfs = list(getattr(bot, "_phantom_timeframes", []) or [])
        phantom_locked = bool(getattr(bot, "_phantom_locked", False))
        phantom_lock_tf = str(getattr(bot, "_phantom_lock_timeframe", "") or "")

        summary = QGroupBox("Coordinator Status")
        sf = QFormLayout(summary)
        self._configure_form(sf)

        en_lbl = QLabel("YES" if phantoms_enabled else "NO")
        en_lbl.setStyleSheet(
            "color: " + (ds.SUCCESS if phantoms_enabled else ds.TEXT_INACTIVE)
        )
        sf.addRow("Phantoms enabled:", en_lbl)

        started_lbl = QLabel("YES" if phantoms_started else "NO")
        started_lbl.setStyleSheet(
            "color: "
            + (
                ds.SUCCESS
                if phantoms_started
                else ds.FOLD_RATIO_AMBER if phantoms_enabled else ds.TEXT_INACTIVE
            )
        )
        sf.addRow("Phantoms started:", started_lbl)

        sf.addRow(
            "Configured timeframes:",
            QLabel(", ".join(phantom_tfs) if phantom_tfs else "— (none)"),
        )

        if phantom_locked:
            lock_lbl = QLabel(
                f"LOCKED — SCRUM suppressed by {phantom_lock_tf} TF "
                f"phantom (downside protection active)"
            )
            lock_lbl.setStyleSheet(f"color: {ds.FOLD_RATIO_AMBER}; font-weight: bold;")
        else:
            lock_lbl = QLabel("UNLOCKED — SCRUM allowed")
            lock_lbl.setStyleSheet(f"color: {ds.SUCCESS};")
        sf.addRow("SCRUM lock state:", lock_lbl)
        layout.addWidget(summary)

        # ── Runtime: Per-Phantom State table ─────────────────────
        phantom_mgr = getattr(bot, "_phantom_mgr", None)
        bot_id = getattr(bot, "bot_id", "")
        phantoms: list = []
        if phantom_mgr is not None:
            try:
                phantoms = list(phantom_mgr.get_phantoms(bot_id) or [])
            except Exception:  # noqa: BLE001 - defensive probe
                phantoms = []

        if phantoms:
            ph_group = QGroupBox(f"Per-Phantom State ({len(phantoms)})")
            pl = QVBoxLayout(ph_group)

            tbl = QTableWidget()
            tbl.setColumnCount(7)
            tbl.setHorizontalHeaderLabels(
                [
                    "TF",
                    "State",
                    "Target",
                    "Trades",
                    "P&L",
                    "Bullish/Bearish",
                    "Confidence",
                ]
            )
            tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            tbl.setRowCount(len(phantoms))
            tbl.setMaximumHeight(280)
            tbl.setAlternatingRowColors(True)
            tbl.setEditTriggers(QTableWidget.NoEditTriggers)

            for row, ph in enumerate(phantoms):
                try:
                    st = ph.get_status()
                except Exception:  # noqa: BLE001 - defensive probe
                    st = {}

                tbl.setItem(row, 0, QTableWidgetItem(str(st.get("timeframe", "?"))))
                tbl.setItem(row, 1, QTableWidgetItem(str(st.get("state", "?"))))
                tbl.setItem(
                    row,
                    2,
                    QTableWidgetItem(
                        f"${float(st.get('target_balance', 0) or 0):,.2f}"
                    ),
                )
                tbl.setItem(row, 3, QTableWidgetItem(str(st.get("total_trades", 0))))

                pnl = float(st.get("realized_pnl_exchange", 0) or 0)
                pi = QTableWidgetItem(f"${pnl:+,.4f}")
                pi.setForeground(
                    QColor(
                        ds.SUCCESS
                        if pnl > 0
                        else ds.ERROR if pnl < 0 else ds.TEXT_INACTIVE
                    )
                )
                tbl.setItem(row, 4, pi)

                summary_d = st.get("last_summary", {}) or {}
                bullish = summary_d.get("bullish", 0)
                bearish = summary_d.get("bearish", 0)
                tbl.setItem(row, 5, QTableWidgetItem(f"{bullish}/{bearish}"))

                conf = float(summary_d.get("confidence", 0) or 0)
                ci = QTableWidgetItem(f"{conf:.2%}")
                if conf >= 0.50:
                    ci.setForeground(QColor(ds.SUCCESS))
                elif conf >= 0.25:
                    ci.setForeground(QColor(ds.FOLD_RATIO_AMBER))
                tbl.setItem(row, 6, ci)

            pl.addWidget(tbl)
            layout.addWidget(ph_group)

        # ── Runtime: Active Locks (cross-bot) ────────────────────
        coordinator = getattr(bot, "_coordinator", None)
        active_locks: list = []
        if coordinator is not None:
            try:
                active_locks = list(coordinator.get_active_locks() or [])
            except Exception:  # noqa: BLE001 - defensive probe
                active_locks = []

        if active_locks:
            locks_group = QGroupBox(f"Active Locks ({len(active_locks)})")
            ll = QVBoxLayout(locks_group)

            lock_tbl = QTableWidget()
            lock_tbl.setColumnCount(4)
            lock_tbl.setHorizontalHeaderLabels(
                ["Source TF", "Source Bot", "Direction", "Candles left"]
            )
            lock_tbl.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents
            )
            lock_tbl.setRowCount(len(active_locks))
            lock_tbl.setMaximumHeight(220)
            lock_tbl.setAlternatingRowColors(True)
            lock_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

            for row, lk in enumerate(active_locks):
                lock_tbl.setItem(
                    row, 0, QTableWidgetItem(str(lk.get("source_tf", "?")))
                )
                src_bot = str(lk.get("source_bot", "?"))
                src_item = QTableWidgetItem(src_bot)
                if src_bot == bot_id:
                    src_item.setForeground(QColor(ds.FOLD_SOURCE_MANUAL))
                    src_item.setText(f"{src_bot} (this bot)")
                lock_tbl.setItem(row, 1, src_item)

                dir_str = str(lk.get("locked_direction", "?"))
                di = QTableWidgetItem(dir_str)
                if "BULLISH" in dir_str:
                    di.setForeground(QColor(ds.SUCCESS))
                elif "BEARISH" in dir_str:
                    di.setForeground(QColor(ds.ERROR))
                lock_tbl.setItem(row, 2, di)

                cr = int(lk.get("candles_remaining", 0) or 0)
                lock_tbl.setItem(row, 3, QTableWidgetItem(str(cr)))

            ll.addWidget(lock_tbl)
            layout.addWidget(locks_group)

        # ── Empty-state message when nothing is running ──────────
        if not phantoms and not active_locks:
            if not phantoms_enabled:
                msg = QLabel(
                    "Phantom Bots are DISABLED on this bot. "
                    "Toggle 'Enable Phantom Balance Bots' above "
                    "to activate the multi-TF coordinator."
                )
            elif not phantoms_started:
                msg = QLabel(
                    "Phantoms enabled but not yet started. They "
                    "spin up automatically on the first tick after "
                    "bot is running. If this persists, check the "
                    "Activity Log for phantom-startup errors."
                )
            else:
                msg = QLabel(
                    "Phantoms active but no per-phantom state "
                    "available yet, and no locks currently held. "
                    "State populates after each phantom completes "
                    "its first signal cycle."
                )
            msg.setStyleSheet(
                f"color: {ds.CARD_METRIC_LABEL}; font-style: italic; " "padding: 10px;"
            )
            msg.setWordWrap(True)
            layout.addWidget(msg)

        layout.addStretch()
        return w

    def _phantom_tfs_changed(self):
        """Called when any phantom TF checkbox toggles. Collect the
        full selected set and mark it as a single config change."""
        selected = [tf for tf, cb in self._phantom_tf_checks.items() if cb.isChecked()]
        self._mark_changed("phantom_timeframes", selected)
