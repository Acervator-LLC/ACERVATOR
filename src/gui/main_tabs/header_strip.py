"""Header stat strip of the main window."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..widgets.dashboard_stat_card import StatCard
from ..widgets.spendable_profits import SpendableProfitsWidget


class HeaderStripMixin:
    """Spendable profits, the five counter cards and the mode toggle."""

    # Supplied by MainWindow at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
    _show_error_log_dialog: Callable[..., Any]
    _toggle_trading_mode: Callable[..., Any]
    _update_mode_btn_style: Callable[..., Any]
    setCentralWidget: Callable[..., Any]

    def _build_header_strip(self) -> QVBoxLayout:
        """Build the central widget and the header strip.

        Returns the central layout the main tab widget is added to.
        """
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(4)

        # === Top row: Spendable Profits + 4 Stat Cards in one tight line ===
        top_row = QHBoxLayout()
        top_row.setSpacing(4)
        top_row.setContentsMargins(0, 0, 0, 0)

        self._spendable_widget = SpendableProfitsWidget()
        top_row.addWidget(self._spendable_widget, stretch=3)

        # v3.15.50 — operator directive 2026-04-24: "How about display
        # total scrummed and total folded. Like two high scores for
        # the platform run. Just add it all up from all running bots."
        # Replaced the P/L card (operator: "still displaying strange
        # numbers I do not understand") with two high-score cards
        # showing cumulative SCRUM (sell USD) and FOLD (buy USD)
        # across the platform run. Easy to understand at a glance:
        # both numbers grow monotonically; the gap between them is
        # the bot's trading appetite.
        self._stat_scrummed = StatCard("Scrummed", "$0.00")
        self._stat_scrummed.setToolTip(
            "Total Scrummed (high score) — cumulative USD sold "
            "across all bots since the platform run started. Grows "
            "with every SCRUM (sell at upper-band) + MANUAL_SCRUM "
            "fill. Resets to $0.00 only on a fresh process start."
        )
        self._stat_folded = StatCard("Folded", "$0.00")
        self._stat_folded.setToolTip(
            "Total Folded (high score) — cumulative USD bought "
            "across all bots since the platform run started. Grows "
            "with every FOLD (buy at lower-band) + MANUAL_FOLD "
            "fill. Resets to $0.00 only on a fresh process start."
        )
        # Keep _stat_pnl as a backing field referenced elsewhere in
        # the class but hide it from the header. Other code paths
        # (e.g., _stat_pnl.set_value updates from background tasks)
        # remain valid; the card just isn't laid out.
        self._stat_pnl = StatCard("P/L", "$0.00")
        self._stat_pnl.setVisible(False)
        self._stat_trades = StatCard("Trades", "0")
        self._stat_trades.setToolTip(
            "Total executed buy and sell trades across all active bots."
        )
        self._stat_bots = StatCard("Bots", "0")
        self._stat_bots.setToolTip(
            "Bots currently in RUNNING state (actively trading)."
        )
        # v3.16.46 — relabeled per operator directive 2026-05-10:
        # "No error counter updating despite all the prior CCX
        # error occurrences." The card now shows lifetime cumulative
        # error count across all bots (never resets), with current
        # ERROR-state count visible in the tooltip.
        # v3.23.60 — dropped "(lifetime)" qualifier per operator
        # directive 2026-07-31: prefer recent data. The Error Log
        # dialog now exposes a Reset button that zeros per-bot
        # total_errors / consecutive_errors / last_error + clears
        # the rolling buffer, so this counter can be a "since last
        # reset" view rather than an all-time monument.
        self._stat_errors = StatCard("Errors", "0")
        self._stat_errors.setToolTip(
            "Error count across all bots since last reset. "
            "Click to open the Error Log; use the Reset button "
            "inside to clear all previous faults.\n\n"
            "Hover bot rows to see current ERROR/COOLDOWN state."
        )
        # v3.16.52 — Errors card is clickable; opens a dialog showing
        # the rolling error log buffer (last 200 bot.error events plus
        # each bot's current last_error / consecutive_errors snapshot).
        self._stat_errors.set_clickable(True, "Click to open the error log.")
        self._stat_errors.clicked.connect(self._show_error_log_dialog)
        # v3.23.7 — attach a privacy dot to each of the 5 top-right
        # counter cards. The dot toggles that field's mask state in
        # the registry; the card's set_value() path passes the value
        # through mask_or() so the next render hides it.
        self._stat_scrummed.attach_privacy_dot("counter.scrummed")
        self._stat_folded.attach_privacy_dot("counter.folded")
        self._stat_trades.attach_privacy_dot("counter.trades")
        self._stat_bots.attach_privacy_dot("counter.bots")
        self._stat_errors.attach_privacy_dot("counter.errors")
        for card in [
            self._stat_scrummed,
            self._stat_folded,
            self._stat_trades,
            self._stat_bots,
            self._stat_errors,
        ]:
            top_row.addWidget(card, stretch=1)

        # Mode toggle: Crypto ↔ Stock
        self._trading_mode = "crypto"
        self._mode_btn = QPushButton("Crypto Mode")
        self._mode_btn.setMinimumWidth(110)
        self._mode_btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self._mode_btn.setCheckable(True)
        self._mode_btn.setChecked(False)
        self._mode_btn.setToolTip("Toggle between Crypto and Stock trading layers")
        self._mode_btn.clicked.connect(self._toggle_trading_mode)
        self._update_mode_btn_style()
        top_row.addWidget(self._mode_btn, stretch=1)

        # v3.18.3 — wrap the header stat strip in a container widget
        # so it can be hidden when the active tab is Simulator or
        # Paper Trader. Per operator directive 2026-05-19: the
        # window-level strip's absence on isolated tabs IS the
        # context differentiator (no PAPER/SIM badge needed). The
        # Trading tab keeps the strip; Simulator/Paper hide it and
        # show their own inline strips inside the tab content.
        self._header_strip_container = QWidget()
        self._header_strip_container.setLayout(top_row)
        main_layout.addWidget(self._header_strip_container)

        return main_layout
