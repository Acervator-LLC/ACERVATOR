"""Status tab of the Live Bot Settings dialog."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .. import design_system as ds


class StatusTabMixin:
    """Read-only stats tab."""

    # Supplied by BotLiveSettingsDialog at runtime; declared so a
    # type checker can resolve them. Annotations only: no attribute
    # is created and the runtime base stays `object`.
    _bot: Any
    _configure_form: Callable[..., Any]

    # ---------------------------------------------------------------
    # Tab 1: Status (read-only)
    # ---------------------------------------------------------------
    def _create_status_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(6)

        status = self._bot.get_status()
        stats = status.get("stats", {})

        # Stats
        stats_group = QGroupBox("Statistics")
        sf = QFormLayout(stats_group)
        self._configure_form(sf)

        # v3.23.7 Anomaly B: internal `stats.realised_pnl` display row
        # removed. Operator directive 2026-06-13: "Prefer to just pull
        # from the exchange. It is the true indicator of position
        # health." The exchange-pulled FIFO-matched realized P/L (see
        # below) is the sole P/L displayed; the (exchange) qualifier
        # is dropped from its label since it is now the only one.

        # v3.16.47 — Exchange-pulled position health (updated every
        # 5 min by tick loop; bootstrap-refreshed on first start).
        # Operator directive 2026-05-10: position health belongs to
        # the exchange. Display alongside internal so divergence is
        # visible at a glance.
        _bot_stats = getattr(self._bot, "stats", None)
        if _bot_stats is not None:
            _re = float(getattr(_bot_stats, "realized_pnl_exchange", 0.0) or 0.0)
            _ae = float(getattr(_bot_stats, "avg_entry_exchange", 0.0) or 0.0)
            _cb = float(getattr(_bot_stats, "cost_basis_total_exchange", 0.0) or 0.0)
            _ue = float(getattr(_bot_stats, "unrealised_pnl", 0.0) or 0.0)
            _fee = float(getattr(_bot_stats, "fees_paid_exchange", 0.0) or 0.0)
            _tc = int(getattr(_bot_stats, "exchange_trade_count", 0) or 0)
            _fts = float(getattr(_bot_stats, "exchange_data_fresh_ts", 0.0) or 0.0)

            if _fts > 0:
                import time as _t

                _age_sec = _t.time() - _fts
                _age_str = (
                    f"{_age_sec:.0f}s" if _age_sec < 60 else f"{_age_sec/60:.1f}m"
                )

                rep_lbl = QLabel(f"${_re:+,.4f}")
                rep_lbl.setStyleSheet(
                    f"font-weight: bold; font-size: 13px; "
                    f"color: {ds.SUCCESS if _re >= 0 else ds.ERROR};"
                )
                rep_lbl.setToolTip(
                    f"Realized P/L pulled from the exchange "
                    f"(FIFO-matched buy/sell pairs from {_tc} trades). "
                    f"Refreshed {_age_str} ago."
                )
                # v3.23.7 Anomaly B: label dropped the "(exchange)"
                # qualifier — this is now the only P/L row.
                sf.addRow("Realised P/L:", rep_lbl)

                if _ue != 0:
                    ue_lbl = QLabel(f"${_ue:+,.4f}")
                    ue_lbl.setStyleSheet(
                        f"color: {ds.SUCCESS if _ue >= 0 else ds.ERROR};"
                    )
                    sf.addRow("Unrealised P/L:", ue_lbl)

                if _ae > 0:
                    sf.addRow("Avg Entry (exchange):", QLabel(f"${_ae:.8f}"))
                    sf.addRow("Cost Basis Total:", QLabel(f"${_cb:,.4f}"))
                if _fee > 0:
                    sf.addRow("Fees Paid:", QLabel(f"${_fee:,.4f}"))
            else:
                pending_lbl = QLabel("— (refresh pending)")
                pending_lbl.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL};")
                pending_lbl.setToolTip(
                    "Exchange position health refresh has not yet "
                    "completed. First refresh fires on bot bootstrap; "
                    "subsequent every 5 minutes."
                )
                # v3.23.7 Anomaly B: label dropped "(exchange)" qualifier.
                sf.addRow("Realised P/L:", pending_lbl)

        sf.addRow("Total Trades:", QLabel(str(stats.get("total_trades", 0))))
        sf.addRow("Active Buys:", QLabel(str(stats.get("active_buys", 0))))
        sf.addRow("Active Sells:", QLabel(str(stats.get("active_sells", 0))))

        from ...core.fmt import fmt_price as _fp

        price = stats.get("current_price", 0)
        sf.addRow("Current Price:", QLabel(_fp(price) if price > 0 else "—"))
        sf.addRow("Uptime:", QLabel(f"{stats.get('uptime', 0):.0f}s"))

        if stats.get("last_error"):
            err = QLabel(stats["last_error"][:80])
            err.setStyleSheet(f"color: {ds.ERROR};")
            err.setWordWrap(True)
            sf.addRow("Last Error:", err)
        layout.addWidget(stats_group)

        # v3.20.4 — Grid Levels table removed (grid_bot deleted
        # v3.16.0; no live bot has a `grid` attribute).

        layout.addStretch()
        return w
