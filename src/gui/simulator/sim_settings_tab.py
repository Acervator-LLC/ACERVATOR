"""Settings tab of the Simulator's Bot Settings window, forked from
``live_settings.settings_tab``; every write reaches ``SimBotView`` and is refused."""

from __future__ import annotations

import logging
from typing import Any, Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...exchange.timeframes import (
    snapped_timeframe_notice,
    unserved_timeframe_notice,
)
from ...simulator.tablet_source import SendRefused
from .. import design_system as ds
from ..live_settings.settings_tab import SettingsTabMixin
from .sim_bot_status_table_surface import sim_target_denom_cell
from ..descriptions import SETTINGS_TAB_DESCRIPTIONS
from ..tooltips import set_description

logger = logging.getLogger("acervator.gui")

#: The budget row's reading while ``cycle_growth_cap_usd`` is not held.
BUDGET_UNREADABLE_TEXT = "— (unreadable)"


class SimSettingsTabMixin(SettingsTabMixin):
    """Editable bot configuration, written on Apply.

    Live's ``SettingsTabMixin`` is the base for ``_show_admitted_figure`` and
    ``_clear_refused_dash``, so the dollar boxes read the one ``as_box_figure``
    admission Live reads; every other method here is this fork's own.
    """

    # Annotations only; SimBotDetailDialog supplies these at runtime.
    _bot: Any
    _configure_form: Callable[..., Any]
    _mark_changed: Callable[..., Any]

    def _refresh_target_denom_rows(self) -> None:
        """Paint the Target-BTC and Target-ETH rows from ``_denom_rates``.

        ``_denom_rates`` is the fleet's own BTC and ETH rows, read once by
        ``sim_target_denom_cell``; no scout and no rate monitor is asked.
        """
        try:
            _btc_lbl = getattr(self, "_target_btc_lbl", None)
            _eth_lbl = getattr(self, "_target_eth_lbl", None)
            _btc_row = getattr(self, "_target_btc_row_label", None)
            _eth_row = getattr(self, "_target_eth_row_label", None)
            if _btc_lbl is None or _eth_lbl is None:
                return
            _bot = getattr(self, "_bot", None)
            if _bot is None:
                return
            _cfg = getattr(_bot, "config", None)
            if _cfg is None:
                return
            from ...trading.container.config import as_finite_float

            _asset = str(getattr(_cfg, "target_asset", "") or "").upper()
            # The same admission the dollar box reads, so a stored figure the
            # box draws as a dash never reaches these two rows as money.
            _read_target = as_finite_float(getattr(_cfg, "target_balance", None))
            if _read_target is None:
                return
            _target_usd = _read_target
            _rates = dict(getattr(self, "_denom_rates", None) or {})
            for _quote, _row, _lbl in (
                ("BTC", _btc_row, _btc_lbl),
                ("ETH", _eth_row, _eth_lbl),
            ):
                if _asset == _quote:
                    _row.setVisible(False)
                    _lbl.setVisible(False)
                    continue
                _row.setVisible(True)
                _lbl.setVisible(True)
                _txt, _color = sim_target_denom_cell(
                    _quote, _asset, _target_usd, _rates
                )
                _lbl.setText(_txt)
                _lbl.setStyleSheet(f"color: {_color};")
        except Exception as _denom_exc:  # noqa: BLE001 - refresh best-effort
            logger.debug("target denom row refresh raised: %s", _denom_exc)

    def _on_self_destruct_clicked(self) -> None:
        """Confirm as Live confirms, then ask ``SimBotView.self_destruct``.

        The view raises ``SendRefused``; the refusal is logged with Live's
        line and shown in place of Live's dispatched box.
        """
        try:
            from PySide6.QtWidgets import (
                QInputDialog,
                QMessageBox,
            )
        except Exception:
            return
        if not hasattr(self._bot, "self_destruct"):
            QMessageBox.warning(
                self,
                "Self-Destruct Unavailable",
                "This bot type does not support self-destruct.",
            )
            return
        sym = getattr(self._bot.config, "symbol", "?")
        bid = self._bot.bot_id[:8] if getattr(self._bot, "bot_id", None) else "?"
        text, ok = QInputDialog.getText(
            self,
            "Confirm SELF-DESTRUCT",
            f"This will MARKET-SELL the entire {sym} position "
            f"on bot {bid} and PAUSE the bot.\n\n"
            f"State (lots, tranches, fold queue) will be CLEARED.\n"
            f"All auto gates (BB threshold, hysteresis, circuit\n"
            f"breakers, higher-TF bias) BYPASSED.\n\n"
            f"To confirm, type SELF-DESTRUCT (case-sensitive):",
            QLineEdit.Normal,
            "",
        )
        if not ok:
            return
        if (text or "").strip() != "SELF-DESTRUCT":
            QMessageBox.information(
                self,
                "Self-Destruct Cancelled",
                "Confirmation token did not match. No action taken.",
            )
            return
        try:
            self._bot.self_destruct(confirmation_token=(text or "").strip())
        except SendRefused as exc:
            logger.warning("Bot %s self_destruct dispatch raised: %s", bid, exc)
            QMessageBox.warning(
                self,
                "Self-Destruct refused",
                f"Nothing was sold and nothing was paused.\n\n{exc}",
            )
            return

    # Tab 2: Settings (editable)
    def _create_settings_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(6)

        cfg = self._bot.config
        is_scrumming = cfg.mode.value == "scrumming"

        info = QLabel(
            "Changes take effect immediately when Apply is clicked. "
            "The bot does not need to be restarted."
        )
        info.setStyleSheet(
            f"color: {ds.CARD_METRIC_LABEL}; font-size: 11px; margin-bottom: 4px;"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        mode_group = QGroupBox("Trading Parameters")
        mf = QFormLayout(mode_group)
        self._configure_form(mf)

        # Visibility
        self._vis = QComboBox()
        self._vis.addItem("Order Book (Visible)", "orderbook")
        self._vis.addItem("Internal (Invisible)", "internal")
        idx = self._vis.findData(cfg.visibility)
        if idx >= 0:
            self._vis.setCurrentIndex(idx)
        self._vis.currentIndexChanged.connect(
            lambda: self._mark_changed("visibility", self._vis.currentData())
        )
        set_description(self._vis, SETTINGS_TAB_DESCRIPTIONS["vis"])
        mf.addRow("Order Visibility:", self._vis)

        self._aggressive = QCheckBox("Aggressive Trading (force IOC-limit takers)")
        self._aggressive.setChecked(cfg.aggressive_trading)
        set_description(self._aggressive, SETTINGS_TAB_DESCRIPTIONS["aggressive"])
        self._aggressive.toggled.connect(
            lambda v: self._mark_changed("aggressive_trading", v)
        )
        mf.addRow(self._aggressive)

        self._stack_mode = QCheckBox("Stack Mode (split SCRUM across upward tranches)")
        self._stack_mode.setChecked(getattr(cfg, "stack_mode", False))
        set_description(self._stack_mode, SETTINGS_TAB_DESCRIPTIONS["stack_mode"])
        self._stack_mode.toggled.connect(lambda v: self._mark_changed("stack_mode", v))
        mf.addRow(self._stack_mode)

        self._split_distance = QDoubleSpinBox()
        self._split_distance.setRange(0.1, 20.0)
        self._split_distance.setDecimals(2)
        self._split_distance.setSuffix(" %")
        self._split_distance.setValue(getattr(cfg, "split_distance", 1.0))
        set_description(
            self._split_distance, SETTINGS_TAB_DESCRIPTIONS["split_distance"]
        )
        self._split_distance.valueChanged.connect(
            lambda v: self._mark_changed("split_distance", v)
        )
        mf.addRow("Split Distance:", self._split_distance)

        self._stack_count = QSpinBox()
        self._stack_count.setRange(2, 20)
        self._stack_count.setValue(int(getattr(cfg, "stack_tranche_count_target", 3)))
        set_description(self._stack_count, SETTINGS_TAB_DESCRIPTIONS["stack_count"])
        self._stack_count.valueChanged.connect(
            lambda v: self._mark_changed("stack_tranche_count_target", v)
        )
        mf.addRow("Tranche Count:", self._stack_count)

        self._stack_spacing = QComboBox()
        # Each sequence is level_multipliers(mode, 4) from stack_math.
        self._stack_spacing.addItem("Linear (1, 2, 3, 4…)", "linear")
        self._stack_spacing.addItem("Quadratic (1, 4, 9, 16…)", "quadratic")
        self._stack_spacing.addItem("Exponential (1, 2, 4, 8…)", "exponential")
        _cur_spacing = getattr(cfg, "stack_spacing_mode", "linear")
        _idx = self._stack_spacing.findData(_cur_spacing)
        if _idx >= 0:
            self._stack_spacing.setCurrentIndex(_idx)
        set_description(self._stack_spacing, SETTINGS_TAB_DESCRIPTIONS["stack_spacing"])
        self._stack_spacing.currentIndexChanged.connect(
            lambda: self._mark_changed(
                "stack_spacing_mode", self._stack_spacing.currentData()
            )
        )
        mf.addRow("Spacing:", self._stack_spacing)

        layout.addWidget(mode_group)

        scrum_group = QGroupBox(
            "Scrumming Settings" if is_scrumming else "Trading Parameters (continued)"
        )
        sf = QFormLayout(scrum_group)
        self._configure_form(sf)

        if is_scrumming:
            self._scrum_interval = QDoubleSpinBox()
            self._scrum_interval.setRange(0.1, 20.0)
            self._scrum_interval.setDecimals(2)
            self._scrum_interval.setSuffix(" %")
            self._scrum_interval.setValue(cfg.scrumming_interval_pct)
            self._scrum_interval.valueChanged.connect(
                lambda v: self._mark_changed("scrumming_interval_pct", v)
            )
            set_description(
                self._scrum_interval, SETTINGS_TAB_DESCRIPTIONS["scrum_interval"]
            )
            sf.addRow("Opposing Trade Interval:", self._scrum_interval)

            self._bb_tol = QDoubleSpinBox()
            self._bb_tol.setRange(0.25, 5.0)
            self._bb_tol.setDecimals(2)
            self._bb_tol.setSuffix(" %")
            self._bb_tol.setValue(cfg.bb_tolerance_pct)
            self._bb_tol.valueChanged.connect(
                lambda v: self._mark_changed("bb_tolerance_pct", v)
            )
            set_description(self._bb_tol, SETTINGS_TAB_DESCRIPTIONS["bb_tol"])
            sf.addRow("BB Tolerance:", self._bb_tol)

            self._landing = QSpinBox()
            self._landing.setRange(2, 10)
            self._landing.setValue(cfg.bb_landing_strip_candles)
            set_description(self._landing, SETTINGS_TAB_DESCRIPTIONS["landing"])
            self._landing.valueChanged.connect(
                lambda v: self._mark_changed("bb_landing_strip_candles", v)
            )
            sf.addRow("Landing Strip Candles:", self._landing)

            # Filtered to the timeframes the bot's exchange supports.
            self._ta_tf = QComboBox()
            try:
                from ...exchange.timeframes import available_timeframes

                _ex_id = getattr(cfg, "exchange_id", None)
                _allowed_tfs = available_timeframes(_ex_id)
            except Exception:
                _allowed_tfs = (
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
                )
            for tf in _allowed_tfs:
                self._ta_tf.addItem(tf)
            idx = self._ta_tf.findText(cfg.ta_timeframe)
            if idx >= 0:
                self._ta_tf.setCurrentIndex(idx)
            else:
                # Operator's saved TF is no longer supported on this
                # exchange — fall back to 1h or first.
                fallback_idx = self._ta_tf.findText("1h")
                if fallback_idx < 0:
                    fallback_idx = 0
                self._ta_tf.setCurrentIndex(fallback_idx)
            set_description(self._ta_tf, SETTINGS_TAB_DESCRIPTIONS["ta_tf"])
            self._ta_tf.currentTextChanged.connect(self._ta_timeframe_picked)
            sf.addRow("TA Timeframe:", self._ta_tf)
            self._ta_tf_notice = QLabel(
                snapped_timeframe_notice(
                    getattr(cfg, "exchange_id", None),
                    getattr(cfg, "ta_timeframe_unserved", ""),
                    cfg.ta_timeframe,
                )
                or unserved_timeframe_notice(
                    getattr(cfg, "exchange_id", None),
                    cfg.ta_timeframe,
                    self._ta_tf.currentText(),
                )
            )
            if self._ta_tf_notice.text():
                self._ta_tf_notice.setWordWrap(True)
                self._ta_tf_notice.setStyleSheet(
                    f"color: {ds.WARNING}; font-size: 11px;"
                )
                set_description(
                    self._ta_tf, f"{self._ta_tf.toolTip()}\n{self._ta_tf_notice.text()}"
                )
                sf.addRow(self._ta_tf_notice)

            self._target_bal = QDoubleSpinBox()
            self._target_bal.setRange(1.0, 1000000.0)
            self._target_bal.setDecimals(2)
            self._target_bal.setPrefix("$ ")
            set_description(self._target_bal, SETTINGS_TAB_DESCRIPTIONS["target_bal"])
            self._show_admitted_figure(self._target_bal, cfg, "target_bal")
            self._target_bal.valueChanged.connect(
                lambda v: self._mark_changed("target_balance", v)
            )
            sf.addRow("Target Balance:", self._target_bal)

        _live_tb = float(getattr(self._bot, "_target_balance", 0.0) or 0.0)
        _anchor_tb = float(getattr(self._bot, "_anchor_target_balance", 0.0) or 0.0)
        _accrued = _live_tb - _anchor_tb
        _live_lbl = QLabel(
            f"${_live_tb:,.4f}   (anchor ${_anchor_tb:,.2f}, "
            f"accrued {_accrued:+,.4f})"
        )
        if abs(_accrued) < 1e-9:
            # Zero accrual is the condition the whole tranche repair
            # exists to change. Say so rather than showing a bare 0.
            _live_lbl.setText(
                f"${_live_tb:,.4f}   (anchor ${_anchor_tb:,.2f} — " f"never compounded)"
            )
            _live_lbl.setStyleSheet(f"color: {ds.FOLD_RATIO_AMBER};")
        else:
            _live_lbl.setStyleSheet(f"color: {ds.SUCCESS};")
        set_description(_live_lbl, SETTINGS_TAB_DESCRIPTIONS["live_lbl"])
        sf.addRow("Live target (traded against):", _live_lbl)

        _surplus = float(getattr(self._bot, "_standing_surplus_usd", 0.0) or 0.0)
        _surplus_lbl = QLabel(f"${_surplus:,.4f}")
        if _surplus > 1e-9:
            _surplus_lbl.setStyleSheet(f"color: {ds.FOLD_RATIO_AMBER};")
            set_description(_surplus_lbl, SETTINGS_TAB_DESCRIPTIONS["surplus_lbl"])
        sf.addRow("Standing surplus:", _surplus_lbl)

        _cap = getattr(self._bot, "cycle_growth_cap_usd", None)
        _budget = round(float(_cap or 0.0), 8) if _cap is not None else None
        _consumed = float(getattr(self._bot, "_fold_cycle_cap_consumed", 0.0) or 0.0)
        _budget_text = (
            f"${_budget:,.4f}" if _budget is not None else BUDGET_UNREADABLE_TEXT
        )
        sf.addRow(
            "Cycle growth budget:",
            QLabel(f"{_budget_text} — consumed ${_consumed:,.4f}"),
        )
        _budget = _budget or 0.0

        _tranches = list(getattr(self._bot, "_fold_tranches", []) or [])
        _over = [
            float(t.get("usd", 0) or 0)
            for t in _tranches
            if isinstance(t, dict)
            and _budget > 0
            and float(t.get("usd", 0) or 0) > _budget
        ]
        if _over:
            _over_lbl = QLabel(
                f"{len(_over)} of {len(_tranches)} " f"(${sum(_over):,.4f})"
            )
            _over_lbl.setStyleSheet(f"color: {ds.ERROR};")
            set_description(_over_lbl, SETTINGS_TAB_DESCRIPTIONS["over_lbl"])
            sf.addRow("Over-cap tranches:", _over_lbl)

        self._target_btc_lbl = QLabel("—")
        set_description(
            self._target_btc_lbl, SETTINGS_TAB_DESCRIPTIONS["target_btc_lbl"]
        )
        self._target_btc_row_label = QLabel("Target BTC:")
        sf.addRow(self._target_btc_row_label, self._target_btc_lbl)
        self._target_eth_lbl = QLabel("—")
        set_description(
            self._target_eth_lbl, SETTINGS_TAB_DESCRIPTIONS["target_eth_lbl"]
        )
        self._target_eth_row_label = QLabel("Target ETH:")
        sf.addRow(self._target_eth_row_label, self._target_eth_lbl)
        self._refresh_target_denom_rows()

        self._max_entry_px = QDoubleSpinBox()
        self._max_entry_px.setRange(0.0, 10_000_000.0)
        self._max_entry_px.setDecimals(8)
        self._max_entry_px.setPrefix("$ ")
        _max_ep_cfg = getattr(cfg, "max_entry_price", None)
        self._max_entry_px.setValue(float(_max_ep_cfg) if _max_ep_cfg else 0.0)
        set_description(self._max_entry_px, SETTINGS_TAB_DESCRIPTIONS["max_entry_px"])
        self._max_entry_px.valueChanged.connect(
            lambda v: self._mark_changed("max_entry_price", float(v) if v > 0 else None)
        )
        sf.addRow("Max Entry Price:", self._max_entry_px)

        self._min_entry_px = QDoubleSpinBox()
        self._min_entry_px.setRange(0.0, 10_000_000.0)
        self._min_entry_px.setDecimals(8)
        self._min_entry_px.setPrefix("$ ")
        _min_ep_cfg = getattr(cfg, "min_entry_price", None)
        self._min_entry_px.setValue(float(_min_ep_cfg) if _min_ep_cfg else 0.0)
        set_description(self._min_entry_px, SETTINGS_TAB_DESCRIPTIONS["min_entry_px"])
        self._min_entry_px.valueChanged.connect(
            lambda v: self._mark_changed("min_entry_price", float(v) if v > 0 else None)
        )
        sf.addRow("Min Entry Price:", self._min_entry_px)

        self._trading_fee = QDoubleSpinBox()
        self._trading_fee.setRange(0.0, 5.0)
        self._trading_fee.setSuffix("%")
        self._trading_fee.setDecimals(2)
        self._trading_fee.setSingleStep(0.05)
        self._trading_fee.setValue(float(getattr(cfg, "trading_fee_pct", 0.6) or 0.6))
        set_description(self._trading_fee, SETTINGS_TAB_DESCRIPTIONS["trading_fee"])
        self._trading_fee.valueChanged.connect(
            lambda v: self._mark_changed("trading_fee_pct", float(v))
        )
        sf.addRow("Trading Fee %:", self._trading_fee)

        self._max_target_growth = QDoubleSpinBox()
        self._max_target_growth.setRange(0.0, 100.0)
        self._max_target_growth.setSuffix("%")
        self._max_target_growth.setDecimals(2)
        self._max_target_growth.setSingleStep(0.25)
        from ...trading.container.config import target_growth_pct

        self._max_target_growth.setValue(float(target_growth_pct(cfg)))
        set_description(
            self._max_target_growth, SETTINGS_TAB_DESCRIPTIONS["max_target_growth"]
        )
        self._max_target_growth.valueChanged.connect(
            lambda v: self._mark_changed("max_target_growth_pct", v)
        )
        sf.addRow("Max Target Growth %:", self._max_target_growth)

        from ...trading.container.config import (
            FOLD_RATIO_MAX_PCT,
            FOLD_RATIO_MIN_PCT,
            fold_ratio_pct,
        )

        self._scrum_fold_pct = QSpinBox()
        self._scrum_fold_pct.setRange(FOLD_RATIO_MIN_PCT, FOLD_RATIO_MAX_PCT)
        self._scrum_fold_pct.setSuffix(" %")
        self._scrum_fold_pct.setValue(fold_ratio_pct(cfg))
        set_description(
            self._scrum_fold_pct, SETTINGS_TAB_DESCRIPTIONS["scrum_fold_pct"]
        )
        self._scrum_fold_pct.valueChanged.connect(
            lambda v: self._mark_changed("scrum_fold_pct", v)
        )
        sf.addRow("Scrum Fold Ratio:", self._scrum_fold_pct)

        self._profit_folding_active = QCheckBox("Profit Folding Active")
        self._profit_folding_active.setChecked(
            bool(getattr(cfg, "profit_folding_active", True))
        )
        set_description(
            self._profit_folding_active,
            SETTINGS_TAB_DESCRIPTIONS["profit_folding_active"],
        )
        self._profit_folding_active.toggled.connect(
            lambda v: self._mark_changed("profit_folding_active", v)
        )
        sf.addRow(self._profit_folding_active)

        layout.addWidget(scrum_group)

        adv_group = QGroupBox("Advanced Scrumming")
        af = QFormLayout(adv_group)
        self._configure_form(af)

        self._detect_pct = QSpinBox()
        self._detect_pct.setRange(10, 90)
        self._detect_pct.setSuffix(" %")
        self._detect_pct.setValue(int(cfg.scrum_detect_pct))
        set_description(self._detect_pct, SETTINGS_TAB_DESCRIPTIONS["detect_pct"])
        self._detect_pct.valueChanged.connect(
            lambda v: self._mark_changed("scrum_detect_pct", v)
        )
        af.addRow("Detect Threshold:", self._detect_pct)

        self._fire_pct = QDoubleSpinBox()
        self._fire_pct.setRange(0.1, 10.0)
        self._fire_pct.setDecimals(2)
        self._fire_pct.setSuffix(" %")
        self._fire_pct.setValue(float(cfg.scrum_fire_pct))
        set_description(self._fire_pct, SETTINGS_TAB_DESCRIPTIONS["fire_pct"])
        self._fire_pct.valueChanged.connect(
            lambda v: self._mark_changed("scrum_fire_pct", v)
        )
        af.addRow("Fire Threshold:", self._fire_pct)

        self._midline_gate = QCheckBox("BB Midline Gate")
        self._midline_gate.setChecked(bool(cfg.bb_midline_gate))
        set_description(self._midline_gate, SETTINGS_TAB_DESCRIPTIONS["midline_gate"])
        self._midline_gate.toggled.connect(
            lambda v: self._mark_changed("bb_midline_gate", v)
        )
        af.addRow(self._midline_gate)

        self._scrum_read_rate_min = QSpinBox()
        self._scrum_read_rate_min.setRange(1, 60)
        self._scrum_read_rate_min.setSuffix(" min")
        self._scrum_read_rate_min.setValue(int(cfg.scrum_read_rate_min))
        set_description(
            self._scrum_read_rate_min, SETTINGS_TAB_DESCRIPTIONS["scrum_read_rate_min"]
        )
        self._scrum_read_rate_min.valueChanged.connect(
            lambda v: self._mark_changed("scrum_read_rate_min", v)
        )
        af.addRow("Read Rate:", self._scrum_read_rate_min)

        self._band_travel = QSpinBox()
        self._band_travel.setRange(0, 100)
        self._band_travel.setSuffix(" %")
        self._band_travel.setValue(int(cfg.band_travel_pct))
        set_description(self._band_travel, SETTINGS_TAB_DESCRIPTIONS["band_travel"])
        self._band_travel.valueChanged.connect(
            lambda v: self._mark_changed("band_travel_pct", v)
        )
        af.addRow("Band Travel:", self._band_travel)

        self._bb_bullseye_check = QCheckBox("BB Bullseye Check")
        self._bb_bullseye_check.setChecked(bool(cfg.bb_bullseye_check))
        set_description(
            self._bb_bullseye_check, SETTINGS_TAB_DESCRIPTIONS["bb_bullseye_check"]
        )
        self._bb_bullseye_check.toggled.connect(
            lambda v: self._mark_changed("bb_bullseye_check", v)
        )
        af.addRow(self._bb_bullseye_check)

        from ...trading.container.config import despawn_threshold_days
        from ..main_tabs.live_settings_tab_surface import DESPAWN_FIELD, TOOLTIPS

        self._tranche_despawn_days = QSpinBox()
        self._tranche_despawn_days.setRange(0, 365)
        self._tranche_despawn_days.setSuffix(" days")
        self._tranche_despawn_days.setSpecialValueText("Off")
        self._tranche_despawn_days.setValue(despawn_threshold_days(cfg))
        set_description(self._tranche_despawn_days, TOOLTIPS[DESPAWN_FIELD])
        self._tranche_despawn_days.valueChanged.connect(
            lambda v: self._mark_changed("tranche_despawn_days", v)
        )
        af.addRow("Tranche Despawn Timer:", self._tranche_despawn_days)

        layout.addWidget(adv_group)

        hedge_group = QGroupBox("Hedge Rebalance")
        hf = QFormLayout(hedge_group)
        self._configure_form(hf)

        self._hedge_active = QCheckBox("Hedge Rebalance Active")
        self._hedge_active.setChecked(bool(cfg.hedge_rebalance_active))
        set_description(self._hedge_active, SETTINGS_TAB_DESCRIPTIONS["hedge_active"])
        self._hedge_active.toggled.connect(
            lambda v: self._mark_changed("hedge_rebalance_active", v)
        )
        hf.addRow(self._hedge_active)

        self._hedge_balance = QDoubleSpinBox()
        self._hedge_balance.setRange(0.0, 999999999.0)
        self._hedge_balance.setDecimals(2)
        self._hedge_balance.setPrefix("$ ")
        set_description(self._hedge_balance, SETTINGS_TAB_DESCRIPTIONS["hedge_balance"])
        self._show_admitted_figure(self._hedge_balance, cfg, "hedge_balance")
        self._hedge_balance.valueChanged.connect(
            lambda v: self._mark_changed("hedge_balance", v)
        )
        hf.addRow("Hedge Balance:", self._hedge_balance)

        layout.addWidget(hedge_group)

        cb_group = QGroupBox("Circuit Breakers")
        cf = QFormLayout(cb_group)
        self._configure_form(cf)

        self._cb_soft_pct = QDoubleSpinBox()
        self._cb_soft_pct.setRange(0.0, 100.0)
        self._cb_soft_pct.setDecimals(1)
        self._cb_soft_pct.setSuffix(" %")
        self._cb_soft_pct.setValue(
            float(getattr(cfg, "circuit_breaker_soft_pct", 25.0))
        )
        set_description(self._cb_soft_pct, SETTINGS_TAB_DESCRIPTIONS["cb_soft_pct"])
        self._cb_soft_pct.valueChanged.connect(
            lambda v: self._mark_changed("circuit_breaker_soft_pct", float(v))
        )
        cf.addRow("Soft CB Threshold:", self._cb_soft_pct)

        self._cb_hard_pct = QDoubleSpinBox()
        self._cb_hard_pct.setRange(0.0, 100.0)
        self._cb_hard_pct.setDecimals(1)
        self._cb_hard_pct.setSuffix(" %")
        self._cb_hard_pct.setValue(
            float(getattr(cfg, "circuit_breaker_hard_pct", 35.0))
        )
        set_description(self._cb_hard_pct, SETTINGS_TAB_DESCRIPTIONS["cb_hard_pct"])
        self._cb_hard_pct.valueChanged.connect(
            lambda v: self._mark_changed("circuit_breaker_hard_pct", float(v))
        )
        cf.addRow("Hard CB Threshold:", self._cb_hard_pct)

        self._cb_cooldown = QSpinBox()
        self._cb_cooldown.setRange(1, 100)
        self._cb_cooldown.setValue(
            int(getattr(cfg, "circuit_breaker_cooldown_candles", 3))
        )
        set_description(self._cb_cooldown, SETTINGS_TAB_DESCRIPTIONS["cb_cooldown"])
        self._cb_cooldown.valueChanged.connect(
            lambda v: self._mark_changed("circuit_breaker_cooldown_candles", int(v))
        )
        cf.addRow("Soft CB Cooldown:", self._cb_cooldown)

        self._max_cartridge_pct = QDoubleSpinBox()
        self._max_cartridge_pct.setRange(0.0, 200.0)
        self._max_cartridge_pct.setDecimals(1)
        self._max_cartridge_pct.setSuffix(" %")
        self._max_cartridge_pct.setValue(
            float(getattr(cfg, "max_cartridge_size_pct", 10.0))
        )
        set_description(
            self._max_cartridge_pct, SETTINGS_TAB_DESCRIPTIONS["max_cartridge_pct"]
        )
        self._max_cartridge_pct.valueChanged.connect(
            lambda v: self._mark_changed("max_cartridge_size_pct", float(v))
        )
        cf.addRow("Max Cartridge Size:", self._max_cartridge_pct)

        self._cartridge_smart_chk = QCheckBox("Calibrate to BB range")
        self._cartridge_smart_chk.setChecked(
            bool(getattr(cfg, "max_cartridge_smart", False))
        )
        set_description(
            self._cartridge_smart_chk, SETTINGS_TAB_DESCRIPTIONS["cartridge_smart_chk"]
        )
        self._cartridge_smart_chk.toggled.connect(
            lambda checked: self._mark_changed("max_cartridge_smart", bool(checked))
        )
        cf.addRow("Smart Cartridge:", self._cartridge_smart_chk)

        self._cartridge_smart_ceiling = QDoubleSpinBox()
        self._cartridge_smart_ceiling.setRange(1.0, 100.0)
        self._cartridge_smart_ceiling.setDecimals(1)
        self._cartridge_smart_ceiling.setSuffix(" %")
        self._cartridge_smart_ceiling.setValue(
            float(getattr(cfg, "max_cartridge_smart_ceiling_pct", 30.0))
        )
        set_description(
            self._cartridge_smart_ceiling,
            SETTINGS_TAB_DESCRIPTIONS["cartridge_smart_ceiling"],
        )
        self._cartridge_smart_ceiling.valueChanged.connect(
            lambda v: self._mark_changed("max_cartridge_smart_ceiling_pct", float(v))
        )
        cf.addRow("Smart Ceiling:", self._cartridge_smart_ceiling)

        reset_row = QHBoxLayout()
        self._cb_reset_all_btn = QPushButton("Reset All Breakers")
        set_description(
            self._cb_reset_all_btn, SETTINGS_TAB_DESCRIPTIONS["cb_reset_all_btn"]
        )

        def _on_cb_reset_all():
            orig = self._cb_reset_all_btn.text()
            status = "Reset failed"
            if hasattr(self._bot, "reset_circuit_breaker"):
                try:
                    result = self._bot.reset_circuit_breaker("all")
                    applied = (
                        result.get("applied", []) if isinstance(result, dict) else []
                    )
                    status = "Reset applied" if applied else "Nothing to reset"
                except Exception as _reset_exc:
                    logger.debug("reset_circuit_breaker raised: %s", _reset_exc)
            self._cb_reset_all_btn.setText(status)
            from PySide6.QtCore import QTimer as _QTimer

            _QTimer.singleShot(2000, lambda: self._cb_reset_all_btn.setText(orig))

        self._cb_reset_all_btn.clicked.connect(_on_cb_reset_all)
        reset_row.addWidget(self._cb_reset_all_btn)
        cf.addRow(reset_row)

        layout.addWidget(cb_group)

        sd_group = QGroupBox("DANGER ZONE — Self-Destruct")
        sd_group.setStyleSheet(
            f"QGroupBox{{border:1px solid {ds.ERROR};color:{ds.ERROR};}}"
            f"QGroupBox::title{{color:{ds.ERROR};font-weight:bold;}}"
        )
        sdv = QVBoxLayout(sd_group)
        sd_hint = QLabel(
            "AGGRESSIVE FULL-POSITION EXIT. Market-sells the "
            "entire holdings of this bot's target asset and "
            "PAUSES the bot. State (lots, fold tranches) is "
            "cleared. Auto gates bypassed (operator override).\n\n"
            "Confirmation required."
        )
        sd_hint.setWordWrap(True)
        sd_hint.setStyleSheet(f"color:{ds.TEXT_INACTIVE};font-size:10px;")
        sdv.addWidget(sd_hint)
        self._self_destruct_btn = QPushButton("💥  SELF-DESTRUCT  💥")
        self._self_destruct_btn.setStyleSheet(
            f"QPushButton{{background:{ds.SETTINGS_DESTRUCTIVE_SURFACE};color:{ds.ERROR};"
            f"border:2px solid {ds.ERROR};border-radius:4px;"
            "padding:8px 12px;font-weight:bold;}"
            f"QPushButton:hover{{background:{ds.SETTINGS_DESTRUCTIVE_HOVER};color:{ds.TEXT_MAX};}}"
        )
        set_description(
            self._self_destruct_btn, SETTINGS_TAB_DESCRIPTIONS["self_destruct_btn"]
        )
        self._self_destruct_btn.clicked.connect(self._on_self_destruct_clicked)
        sdv.addWidget(self._self_destruct_btn)
        layout.addWidget(sd_group)

        risk_group = QGroupBox("Risk Controls")
        rf = QFormLayout(risk_group)
        self._configure_form(rf)

        self._ceiling_enabled = QCheckBox("Enable Position Ceiling")
        self._ceiling_enabled.setChecked(
            bool(getattr(cfg, "position_ceiling_enabled", False))
        )
        set_description(
            self._ceiling_enabled, SETTINGS_TAB_DESCRIPTIONS["ceiling_enabled"]
        )
        self._ceiling_enabled.toggled.connect(
            lambda v: self._mark_changed("position_ceiling_enabled", v)
        )
        rf.addRow(self._ceiling_enabled)

        from ...trading.container.config import (
            CEILING_MULTIPLE_MAX,
            CEILING_MULTIPLE_MIN,
            DETONATION_BAR_MAX,
            DETONATION_BAR_MIN,
            DETONATION_CONFIDENCE_MIN_DEFAULT,
            ceiling_multiple,
        )

        self._ceiling_mult = QDoubleSpinBox()
        self._ceiling_mult.setRange(CEILING_MULTIPLE_MIN, CEILING_MULTIPLE_MAX)
        self._ceiling_mult.setDecimals(1)
        self._ceiling_mult.setSingleStep(0.5)
        self._ceiling_mult.setSuffix("x anchor")
        self._ceiling_mult.setValue(ceiling_multiple(cfg))
        set_description(self._ceiling_mult, SETTINGS_TAB_DESCRIPTIONS["ceiling_mult"])
        self._ceiling_mult.valueChanged.connect(
            lambda v: self._mark_changed("position_ceiling_multiple", v)
        )
        rf.addRow("Ceiling Multiple:", self._ceiling_mult)

        self._deto_enabled = QCheckBox("Enable Detonation (auto-harvest on bullish TF)")
        self._deto_enabled.setChecked(bool(getattr(cfg, "detonation_enabled", False)))
        set_description(self._deto_enabled, SETTINGS_TAB_DESCRIPTIONS["deto_enabled"])
        self._deto_enabled.toggled.connect(
            lambda v: self._mark_changed("detonation_enabled", v)
        )
        rf.addRow(self._deto_enabled)

        self._deto_tf = QComboBox()
        self._deto_tf.addItems(["1d", "1w"])
        _cur_tf = getattr(cfg, "detonation_timeframe", "1d") or "1d"
        _idx = self._deto_tf.findText(_cur_tf)
        if _idx >= 0:
            self._deto_tf.setCurrentIndex(_idx)
        set_description(self._deto_tf, SETTINGS_TAB_DESCRIPTIONS["deto_tf"])
        self._deto_tf.currentTextChanged.connect(
            lambda v: self._mark_changed("detonation_timeframe", v)
        )
        rf.addRow("Detonation TF:", self._deto_tf)

        self._deto_conf = QDoubleSpinBox()
        self._deto_conf.setRange(DETONATION_BAR_MIN, DETONATION_BAR_MAX)
        self._deto_conf.setDecimals(2)
        self._deto_conf.setSingleStep(0.05)
        self._deto_conf.setValue(
            float(
                getattr(
                    cfg, "detonation_confidence_min", DETONATION_CONFIDENCE_MIN_DEFAULT
                )
            )
        )
        set_description(self._deto_conf, SETTINGS_TAB_DESCRIPTIONS["deto_conf"])
        self._deto_conf.valueChanged.connect(
            lambda v: self._mark_changed("detonation_confidence_min", v)
        )
        rf.addRow("Min Confidence:", self._deto_conf)

        layout.addWidget(risk_group)

        gates_group = QGroupBox("Strategy Gate Flags")
        gf = QFormLayout(gates_group)
        self._configure_form(gf)

        self._gate_scrum_ta = QCheckBox("SCRUM requires bullish TA")
        self._gate_scrum_ta.setChecked(
            bool(getattr(cfg, "scrum_require_ta_bullish", True))
        )
        set_description(self._gate_scrum_ta, SETTINGS_TAB_DESCRIPTIONS["gate_scrum_ta"])
        self._gate_scrum_ta.toggled.connect(
            lambda v: self._mark_changed("scrum_require_ta_bullish", v)
        )
        gf.addRow(self._gate_scrum_ta)

        self._gate_scrum_uptrend = QCheckBox("SCRUM holds in sustained uptrend")
        self._gate_scrum_uptrend.setChecked(
            bool(getattr(cfg, "scrum_hold_in_uptrend", True))
        )
        set_description(
            self._gate_scrum_uptrend, SETTINGS_TAB_DESCRIPTIONS["gate_scrum_uptrend"]
        )
        self._gate_scrum_uptrend.toggled.connect(
            lambda v: self._mark_changed("scrum_hold_in_uptrend", v)
        )
        gf.addRow(self._gate_scrum_uptrend)

        self._gate_scrum_htf = QCheckBox("SCRUM defers to higher-TF bullish")
        self._gate_scrum_htf.setChecked(bool(getattr(cfg, "scrum_defer_to_htf", True)))
        set_description(
            self._gate_scrum_htf, SETTINGS_TAB_DESCRIPTIONS["gate_scrum_htf"]
        )
        self._gate_scrum_htf.toggled.connect(
            lambda v: self._mark_changed("scrum_defer_to_htf", v)
        )
        gf.addRow(self._gate_scrum_htf)

        self._gate_fold_ta = QCheckBox("FOLD requires bearish TA")
        self._gate_fold_ta.setChecked(
            bool(getattr(cfg, "fold_require_ta_bearish", True))
        )
        set_description(self._gate_fold_ta, SETTINGS_TAB_DESCRIPTIONS["gate_fold_ta"])
        self._gate_fold_ta.toggled.connect(
            lambda v: self._mark_changed("fold_require_ta_bearish", v)
        )
        gf.addRow(self._gate_fold_ta)

        self._gate_fold_htf = QCheckBox("FOLD defers to higher-TF bearish")
        self._gate_fold_htf.setChecked(bool(getattr(cfg, "fold_defer_to_htf", True)))
        set_description(self._gate_fold_htf, SETTINGS_TAB_DESCRIPTIONS["gate_fold_htf"])
        self._gate_fold_htf.toggled.connect(
            lambda v: self._mark_changed("fold_defer_to_htf", v)
        )
        gf.addRow(self._gate_fold_htf)

        layout.addWidget(gates_group)

        if cfg.mode.value == "extractor":
            ext_group = QGroupBox("Extractor — Pool && Artillery")
            ef = QFormLayout(ext_group)
            self._configure_form(ef)

            self._ext_chunk_size = QDoubleSpinBox()
            self._ext_chunk_size.setRange(10.0, 10_000_000.0)
            self._ext_chunk_size.setDecimals(2)
            self._ext_chunk_size.setPrefix("$")
            self._ext_chunk_size.setValue(
                float(getattr(cfg, "extractor_chunk_size_usd", 100.0))
            )
            set_description(
                self._ext_chunk_size, SETTINGS_TAB_DESCRIPTIONS["ext_chunk_size"]
            )
            self._ext_chunk_size.valueChanged.connect(
                lambda v: self._mark_changed("extractor_chunk_size_usd", v)
            )
            ef.addRow("Chunk size (USD):", self._ext_chunk_size)

            self._ext_artillery_size = QDoubleSpinBox()
            self._ext_artillery_size.setRange(0.5, 100_000.0)
            self._ext_artillery_size.setDecimals(2)
            self._ext_artillery_size.setPrefix("$")
            self._ext_artillery_size.setValue(
                float(getattr(cfg, "extractor_artillery_size_usd", 5.0))
            )
            set_description(
                self._ext_artillery_size,
                SETTINGS_TAB_DESCRIPTIONS["ext_artillery_size"],
            )
            self._ext_artillery_size.valueChanged.connect(
                lambda v: self._mark_changed("extractor_artillery_size_usd", v)
            )
            ef.addRow("Artillery size (USD):", self._ext_artillery_size)

            self._ext_scan_top_n = QSpinBox()
            self._ext_scan_top_n.setRange(5, 10)
            self._ext_scan_top_n.setValue(int(getattr(cfg, "extractor_scan_top_n", 8)))
            set_description(
                self._ext_scan_top_n, SETTINGS_TAB_DESCRIPTIONS["ext_scan_top_n"]
            )
            self._ext_scan_top_n.valueChanged.connect(
                lambda v: self._mark_changed("extractor_scan_top_n", v)
            )
            ef.addRow("Watch list top-N:", self._ext_scan_top_n)

            self._ext_scan_refresh = QSpinBox()
            # The wizard row and the manual both offer 10 to 240 candles.
            self._ext_scan_refresh.setRange(10, 240)
            self._ext_scan_refresh.setSuffix(" candles")
            self._ext_scan_refresh.setValue(
                int(getattr(cfg, "extractor_scan_refresh_candles", 60))
            )
            set_description(
                self._ext_scan_refresh, SETTINGS_TAB_DESCRIPTIONS["ext_scan_refresh"]
            )
            self._ext_scan_refresh.valueChanged.connect(
                lambda v: self._mark_changed("extractor_scan_refresh_candles", v)
            )
            ef.addRow("Watch list refresh:", self._ext_scan_refresh)

            self._ext_exit_pct = QDoubleSpinBox()
            self._ext_exit_pct.setRange(10.0, 100.0)
            self._ext_exit_pct.setDecimals(1)
            self._ext_exit_pct.setSuffix(" %")
            self._ext_exit_pct.setValue(
                float(getattr(cfg, "extractor_exit_pct", 100.0))
            )
            set_description(
                self._ext_exit_pct, SETTINGS_TAB_DESCRIPTIONS["ext_exit_pct"]
            )
            self._ext_exit_pct.valueChanged.connect(
                lambda v: self._mark_changed("extractor_exit_pct", v)
            )
            ef.addRow("Exit %:", self._ext_exit_pct)

            layout.addWidget(ext_group)

        layout.addStretch()
        return w
