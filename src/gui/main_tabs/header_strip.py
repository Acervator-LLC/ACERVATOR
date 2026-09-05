"""``HeaderStripMixin`` builds the header stat strip of the main window."""

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
    """``HeaderStripMixin`` owns the header strip widgets.

    ``_build_header_strip`` lays out ``SpendableProfitsWidget``, five
    ``StatCard`` counters and ``_mode_btn``.
    """

    # MainWindow supplies these; the bare annotations create no attribute.
    _show_error_log_dialog: Callable[..., Any]
    _toggle_trading_mode: Callable[..., Any]
    _update_mode_btn_style: Callable[..., Any]
    setCentralWidget: Callable[..., Any]

    def _build_header_strip(self) -> QVBoxLayout:
        """Build the central ``QWidget``.

        Returns the ``QVBoxLayout`` the main tab widget is added to.
        """
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(4)
        top_row.setContentsMargins(0, 0, 0, 0)

        self._spendable_widget = SpendableProfitsWidget()
        top_row.addWidget(self._spendable_widget, stretch=3)

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
        # _stat_pnl is never added to top_row; MainWindow still calls set_value on it.
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
        self._stat_errors = StatCard("Errors", "0")
        self._stat_errors.setToolTip(
            "Error count across all bots since last reset. "
            "Click to open the Error Log; use the Reset button "
            "inside to clear all previous faults.\n\n"
            "Hover bot rows to see current ERROR/COOLDOWN state."
        )
        self._stat_errors.set_clickable(True, "Click to open the error log.")
        self._stat_errors.clicked.connect(self._show_error_log_dialog)
        # StatCard.set_value renders through mask_or once a dot is attached.
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

        # _on_main_tab_changed hides _header_strip_container on the Simulator tab.
        self._header_strip_container = QWidget()
        self._header_strip_container.setLayout(top_row)
        main_layout.addWidget(self._header_strip_container)

        return main_layout
