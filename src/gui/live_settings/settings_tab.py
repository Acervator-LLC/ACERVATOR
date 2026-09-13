"""Settings tab of the Live Bot Settings dialog."""

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

from .. import design_system as ds
from .denom_rows import _compose_denom_row_text

logger = logging.getLogger("acervator.gui")


class SettingsTabMixin:
    """Editable bot configuration, written on Apply."""

    # Annotations only; BotLiveSettingsDialog supplies these at runtime.
    _bot: Any
    _configure_form: Callable[..., Any]
    _mark_changed: Callable[..., Any]

    def _refresh_target_denom_rows(self) -> None:
        """Repaint the Target-BTC and Target-ETH rows.

        Reads the scout and the currency monitor. Idempotent and
        non-raising; the periodic timer and construction both call it.
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
            _asset = str(getattr(_cfg, "target_asset", "") or "").upper()
            _eid = str(getattr(_cfg, "exchange_id", "") or "")
            _target_usd = float(getattr(_cfg, "target_balance", 0.0) or 0.0)
            # Import here to keep top-level GUI imports cheap.
            from ...exchange.currency_rate_monitor import get_currency_monitor
            from ...exchange.market_pairs_scout import get_scout

            _rates = get_currency_monitor().snapshot()
            _scout = get_scout()
            _usd_pair = _scout.get_pair(_asset, "USD", exchange_id=(_eid or None))
            if _usd_pair is None:
                _usd_pair = _scout.get_pair(_asset, "USDC", exchange_id=(_eid or None))
            _usd_pct = float(_usd_pair.pct_24h) if _usd_pair else 0.0
            # BTC row
            if _asset == "BTC":
                _btc_row.setVisible(False)
                _btc_lbl.setVisible(False)
            else:
                _btc_row.setVisible(True)
                _btc_lbl.setVisible(True)
                _btc_pair = _scout.get_pair(_asset, "BTC", exchange_id=(_eid or None))
                if _btc_pair is None:
                    _btc_lbl.setText("(not listed on exchange)")
                    _btc_lbl.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL};")
                else:
                    _txt, _color = _compose_denom_row_text(
                        "BTC",
                        _target_usd,
                        _rates.btc_usd,
                        _btc_pair.pct_24h,
                        _usd_pct,
                    )
                    _btc_lbl.setText(_txt)
                    _btc_lbl.setStyleSheet(f"color: {_color};")
            # ETH row
            if _asset == "ETH":
                _eth_row.setVisible(False)
                _eth_lbl.setVisible(False)
            else:
                _eth_row.setVisible(True)
                _eth_lbl.setVisible(True)
                _eth_pair = _scout.get_pair(_asset, "ETH", exchange_id=(_eid or None))
                if _eth_pair is None:
                    _eth_lbl.setText("(not listed on exchange)")
                    _eth_lbl.setStyleSheet(f"color: {ds.CARD_METRIC_LABEL};")
                else:
                    _txt, _color = _compose_denom_row_text(
                        "ETH",
                        _target_usd,
                        _rates.eth_usd,
                        _eth_pair.pct_24h,
                        _usd_pct,
                    )
                    _eth_lbl.setText(_txt)
                    _eth_lbl.setStyleSheet(f"color: {_color};")
        except Exception as _denom_exc:  # noqa: BLE001 - refresh best-effort
            logger.debug("target denom row refresh raised: %s", _denom_exc)

    def _on_self_destruct_clicked(self) -> None:
        """Operator-initiated SELF-DESTRUCT. Two-step confirmation:
        (1) modal dialog explains the consequences and requires
            the operator to type "SELF-DESTRUCT" literally.
        (2) call bot.self_destruct(confirmation_token=...) which
            only proceeds if the token matches.

        All paths are non-raising — the dialog is non-modal blocking
        and any exceptions surface in the bot's log.
        """
        try:
            from PySide6.QtWidgets import (
                QInputDialog,
                QMessageBox,
                QLineEdit,
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
        import threading, asyncio as _aio

        def _run():
            _sd_phrase = "SELF-DESTRUCT"
            try:
                result = _aio.run(
                    self._bot.self_destruct(confirmation_token=_sd_phrase)
                )
                logger.info("Bot %s self_destruct result: %s", bid, result)
            except Exception as exc:
                logger.warning("Bot %s self_destruct dispatch raised: %s", bid, exc)

        threading.Thread(target=_run, daemon=True, name=f"self-destruct-{bid}").start()
        QMessageBox.information(
            self,
            "Self-Destruct Dispatched",
            f"Self-destruct dispatched for bot {bid} — "
            f"check the Activity Log for SELF-DESTRUCT FIRING "
            f"or SELF-DESTRUCT FAILED to confirm outcome.\n"
            f"Bot will be PAUSED on completion.",
        )

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

        # --- Trading Mode Settings ---
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
        mf.addRow("Order Visibility:", self._vis)

        self._aggressive = QCheckBox("Aggressive Trading (force IOC-limit takers)")
        self._aggressive.setChecked(cfg.aggressive_trading)
        self._aggressive.setToolTip(
            "When ON, every engine-initiated buy/sell executes as "
            "an Immediate-Or-Cancel limit order priced through the "
            "spread — i.e., pays the taker fee for immediate fill. "
            "When OFF, the bot may use passive maker orders where "
            "appropriate. Manual fire is unaffected by this flag."
        )
        self._aggressive.toggled.connect(
            lambda v: self._mark_changed("aggressive_trading", v)
        )
        mf.addRow(self._aggressive)

        self._stack_mode = QCheckBox("Stack Mode (split SCRUM across upward tranches)")
        self._stack_mode.setChecked(getattr(cfg, "stack_mode", False))
        self._stack_mode.setToolTip(
            "When ON, a SCRUM fires as N Stack Tranches at ascending "
            "price levels instead of a single sell. First tranche at "
            "the Minimum Opposing Trade Distance (opposing hysteresis "
            "level); successive tranches spaced by Split Distance per "
            "the Spacing model. See the Stack Tranches tab for live "
            "tranche state (added Sub-phase 2E). Visibility gates "
            "book placement: orderbook = resting limits; internal = "
            "tracked off-books, market-fire on threshold cross."
        )
        self._stack_mode.toggled.connect(lambda v: self._mark_changed("stack_mode", v))
        mf.addRow(self._stack_mode)

        self._split_distance = QDoubleSpinBox()
        self._split_distance.setRange(0.1, 20.0)
        self._split_distance.setDecimals(2)
        self._split_distance.setSuffix(" %")
        self._split_distance.setValue(getattr(cfg, "split_distance", 1.0))
        self._split_distance.setToolTip(
            "Percent spacing between successive Stack tranches. "
            "Applied per stack_spacing_mode: Linear = constant "
            "delta, Logarithmic = arithmetically-growing delta, "
            "Exponential = geometrically-growing delta."
        )
        self._split_distance.valueChanged.connect(
            lambda v: self._mark_changed("split_distance", v)
        )
        mf.addRow("Split Distance:", self._split_distance)

        self._stack_count = QSpinBox()
        self._stack_count.setRange(2, 20)
        self._stack_count.setValue(int(getattr(cfg, "stack_tranche_count_target", 3)))
        self._stack_count.setToolTip(
            "Target number of Stack tranches to create from a SCRUM. "
            "Actual runtime count may be lower if (a) per-tranche "
            "size falls below the exchange minimum order size, or "
            "(b) two computed tranche prices land within 0.1% of "
            "each other (then merged upwards)."
        )
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
        self._stack_spacing.setToolTip(
            "Spacing model for successive Stack tranches. Each "
            "sequence is the cumulative distance from the anchor, "
            "in units of Split Distance."
        )
        self._stack_spacing.currentIndexChanged.connect(
            lambda: self._mark_changed(
                "stack_spacing_mode", self._stack_spacing.currentData()
            )
        )
        mf.addRow("Spacing:", self._stack_spacing)

        self._personal_hold_qty = QDoubleSpinBox()
        self._personal_hold_qty.setRange(0.0, 1_000_000_000.0)
        self._personal_hold_qty.setDecimals(10)
        self._personal_hold_qty.setValue(float(getattr(cfg, "personal_hold_qty", 0.0)))
        self._personal_hold_qty.setToolTip(
            "Target-asset units to hold OUT of the bot's view "
            "(personal reserve). The bot won't buy or sell these "
            "units; they're also reserved from any sibling bot on "
            "the same asset via the CapitalReservationRegistry."
        )
        self._personal_hold_qty.valueChanged.connect(
            lambda v: self._mark_changed("personal_hold_qty", float(v))
        )
        mf.addRow("Personal Hold (units):", self._personal_hold_qty)

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
            sf.addRow("Opposing Trade Interval:", self._scrum_interval)

            self._bb_tol = QDoubleSpinBox()
            self._bb_tol.setRange(0.25, 5.0)
            self._bb_tol.setDecimals(2)
            self._bb_tol.setSuffix(" %")
            self._bb_tol.setValue(cfg.bb_tolerance_pct)
            self._bb_tol.valueChanged.connect(
                lambda v: self._mark_changed("bb_tolerance_pct", v)
            )
            sf.addRow("BB Tolerance:", self._bb_tol)

            self._landing = QSpinBox()
            self._landing.setRange(2, 10)
            self._landing.setValue(cfg.bb_landing_strip_candles)
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
            self._ta_tf.setToolTip(
                "TA Timeframe — filtered to granularities supported "
                "by this bot's exchange. v3.15.61."
            )
            self._ta_tf.currentTextChanged.connect(
                lambda v: self._mark_changed("ta_timeframe", v)
            )
            sf.addRow("TA Timeframe:", self._ta_tf)

            self._target_bal = QDoubleSpinBox()
            self._target_bal.setRange(1.0, 1000000.0)
            self._target_bal.setDecimals(2)
            self._target_bal.setPrefix("$ ")
            self._target_bal.setValue(cfg.target_balance)
            self._target_bal.setToolTip(
                "The balance this bot trades relative to. HARD-CAPPED: "
                "position can never exceed Target × (1 + Max Target Growth %/100). "
                "MEM-246/249/251."
            )
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
        _live_lbl.setToolTip(
            "The target the bot actually trades against.\n\n"
            "The spinbox above is your input value and does not "
            "move when compounding grows the target. This row is "
            "the runtime figure."
        )
        sf.addRow("Live target (traded against):", _live_lbl)

        _surplus = float(getattr(self._bot, "_standing_surplus_usd", 0.0) or 0.0)
        _surplus_lbl = QLabel(f"${_surplus:,.4f}")
        if _surplus > 1e-9:
            _surplus_lbl.setStyleSheet(f"color: {ds.FOLD_RATIO_AMBER};")
            _surplus_lbl.setToolTip(
                "Surplus parked above the per-cycle growth cap.\n\n"
                "There is currently NO drain from this pool — it "
                "accrues and stays. Implementing the drain is "
                "Phase 2 of the tranche repair."
            )
        sf.addRow("Standing surplus:", _surplus_lbl)

        _budget = round(
            float(getattr(self._bot, "cycle_growth_cap_usd", 0.0) or 0.0), 8
        )
        _consumed = float(getattr(self._bot, "_fold_cycle_cap_consumed", 0.0) or 0.0)
        sf.addRow(
            "Cycle growth budget:",
            QLabel(f"${_budget:,.4f} — consumed ${_consumed:,.4f}"),
        )

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
            _over_lbl.setToolTip(
                "Tranches larger than the entire per-cycle budget.\n\n"
                "The fold takes what the budget allows from the "
                "first of these that does not fit and leaves the "
                "remainder queued, so each needs more than one "
                "cycle to fold back in full."
            )
            sf.addRow("Over-cap tranches:", _over_lbl)

        self._target_btc_lbl = QLabel("—")
        self._target_btc_lbl.setToolTip(
            "Target USD ÷ (BTC/USD spot). Δ24h vs USD = "
            "pct_24h(<target>/BTC) − pct_24h(<target>/USD). "
            "Positive Δ means BTC-quoted pair is cheaper in "
            "USD terms than the USD-quoted pair right now."
        )
        self._target_btc_row_label = QLabel("Target BTC:")
        sf.addRow(self._target_btc_row_label, self._target_btc_lbl)
        self._target_eth_lbl = QLabel("—")
        self._target_eth_lbl.setToolTip(
            "Target USD ÷ (ETH/USD spot). Δ24h vs USD = "
            "pct_24h(<target>/ETH) − pct_24h(<target>/USD). "
            "Positive Δ means ETH-quoted pair is cheaper in "
            "USD terms than the USD-quoted pair right now."
        )
        self._target_eth_row_label = QLabel("Target ETH:")
        sf.addRow(self._target_eth_row_label, self._target_eth_lbl)
        self._refresh_target_denom_rows()
        try:
            from PySide6.QtCore import QTimer as _QTimer

            self._denom_refresh_timer = _QTimer(self)
            self._denom_refresh_timer.setInterval(5_000)
            self._denom_refresh_timer.timeout.connect(self._refresh_target_denom_rows)
            self._denom_refresh_timer.start()
        except Exception as _tmr_exc:  # noqa: BLE001 - timer setup best-effort
            logger.debug("denom-row refresh timer failed to start: %s", _tmr_exc)

        self._max_entry_px = QDoubleSpinBox()
        self._max_entry_px.setRange(0.0, 10_000_000.0)
        self._max_entry_px.setDecimals(8)
        self._max_entry_px.setPrefix("$ ")
        _max_ep_cfg = getattr(cfg, "max_entry_price", None)
        self._max_entry_px.setValue(float(_max_ep_cfg) if _max_ep_cfg else 0.0)
        self._max_entry_px.setToolTip(
            "Bot REFUSES any auto-buy when current price is ABOVE "
            "this. Use to cap entry exposure at known overvaluation. "
            "0 = no ceiling (default). Manual Fire bypasses this gate."
        )
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
        self._min_entry_px.setToolTip(
            "Bot REFUSES any auto-buy when current price is BELOW "
            "this. Use to avoid catching a falling knife. 0 = no "
            "floor (default). Manual Fire bypasses this gate."
        )
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
        self._trading_fee.setToolTip(
            "Coinbase trading fee tier (per side). The opposite-"
            "direction hysteresis safety adds this to the scrum "
            "interval — bot will not flip BUY↔SELL until price "
            "moves ≥ (interval + fee)% in the opposing direction. "
            "0.6% = Coinbase Advanced Trade max-tier default. "
            "Lower this if you're on a discounted tier."
        )
        self._trading_fee.valueChanged.connect(
            lambda v: self._mark_changed("trading_fee_pct", float(v))
        )
        sf.addRow("Trading Fee %:", self._trading_fee)

        self._max_target_growth = QDoubleSpinBox()
        self._max_target_growth.setRange(0.0, 100.0)
        self._max_target_growth.setSuffix("%")
        self._max_target_growth.setDecimals(2)
        self._max_target_growth.setSingleStep(0.25)
        self._max_target_growth.setValue(
            float(getattr(cfg, "max_target_growth_pct", 1.0))
        )
        self._max_target_growth.setToolTip(
            "Per-event cap on how much a fold surplus may grow Target Balance.\n"
            "Absolute ceiling = Target × (1 + this%/100). Default 1%.\n"
            "THIS IS THE ONLY MECHANISM ALLOWED TO INCREASE TARGET BALANCE.\n"
            "Set to 0% to freeze Target Balance entirely (no growth at all)."
        )
        self._max_target_growth.valueChanged.connect(
            lambda v: self._mark_changed("max_target_growth_pct", v)
        )
        sf.addRow("Max Target Growth %:", self._max_target_growth)

        self._profit_folding_active = QCheckBox("Profit Folding Active")
        self._profit_folding_active.setChecked(
            bool(getattr(cfg, "profit_folding_active", True))
        )
        self._profit_folding_active.setToolTip(
            "When ON, fold surplus grows the effective target "
            "balance via the compounding drain (subject to Max "
            "Target Growth % cap). OFF freezes target at anchor "
            "regardless of fold profit. Wizard parity: matches "
            "the dedicated Profit Folding page at bot creation."
        )
        self._profit_folding_active.toggled.connect(
            lambda v: self._mark_changed("profit_folding_active", v)
        )
        sf.addRow(self._profit_folding_active)

        layout.addWidget(scrum_group)

        # --- Advanced ---
        adv_group = QGroupBox("Advanced Scrumming (P1.9)")
        af = QFormLayout(adv_group)
        self._configure_form(af)

        self._detect_pct = QSpinBox()
        self._detect_pct.setRange(10, 90)
        self._detect_pct.setSuffix(" %")
        self._detect_pct.setValue(int(cfg.scrum_detect_pct))
        self._detect_pct.setToolTip(
            "BB DETECT threshold: % distance from BB midline to "
            "band before SEARCH→TRACK. Lower = earlier detection. "
            "v3.15.57 — also defines the HARD GATE: SCRUM cannot "
            "occur below the Upper BB Detection Threshold; FOLD "
            "cannot occur above the Lower BB Detection Threshold. "
            "75% → upper gate at bb_pos≥0.875, lower gate at "
            "bb_pos≤0.125. Live-editable."
        )
        self._detect_pct.valueChanged.connect(
            lambda v: self._mark_changed("scrum_detect_pct", v)
        )
        af.addRow("Detect Threshold:", self._detect_pct)

        self._fire_pct = QDoubleSpinBox()
        self._fire_pct.setRange(0.1, 10.0)
        self._fire_pct.setDecimals(2)
        self._fire_pct.setSuffix(" %")
        self._fire_pct.setValue(float(cfg.scrum_fire_pct))
        self._fire_pct.setToolTip(
            "FIRE threshold: % distance from BB band to trigger trade."
        )
        self._fire_pct.valueChanged.connect(
            lambda v: self._mark_changed("scrum_fire_pct", v)
        )
        af.addRow("Fire Threshold:", self._fire_pct)

        self._midline_gate = QCheckBox("BB Midline Gate")
        self._midline_gate.setChecked(bool(cfg.bb_midline_gate))
        self._midline_gate.setToolTip(
            "When enabled: scrums ONLY fire above BB midline,\n"
            "folds ONLY fire below midline (sell-high/buy-low)."
        )
        self._midline_gate.toggled.connect(
            lambda v: self._mark_changed("bb_midline_gate", v)
        )
        af.addRow(self._midline_gate)

        self._read_rate = QSpinBox()
        self._read_rate.setRange(1, 60)
        self._read_rate.setSuffix(" min")
        self._read_rate.setValue(int(cfg.scrum_read_rate_min))
        self._read_rate.setToolTip(
            "SEARCH-mode read rate in minutes. TRACK mode reads 10x faster."
        )
        self._read_rate.valueChanged.connect(
            lambda v: self._mark_changed("scrum_read_rate_min", v)
        )
        af.addRow("Read Rate:", self._read_rate)

        self._band_travel = QSpinBox()
        self._band_travel.setRange(0, 100)
        self._band_travel.setSuffix(" %")
        self._band_travel.setValue(int(cfg.band_travel_pct))
        self._band_travel.setToolTip(
            "Secondary harvest trigger: % of BB band width price must "
            "travel since last fold. 0 disables."
        )
        self._band_travel.valueChanged.connect(
            lambda v: self._mark_changed("band_travel_pct", v)
        )
        af.addRow("Band Travel:", self._band_travel)

        self._bullseye = QCheckBox("BB Bullseye Check")
        self._bullseye.setChecked(bool(cfg.bb_bullseye_check))
        self._bullseye.setToolTip(
            "Counts a band touch within 0.5% (or a candle wick within "
            "0.2%) as BB proximity.\n"
            "With the delta at or over the interval that arms the BB "
            "priority skew, which lowers the TA confidence floor. The "
            "fire threshold and the midline gate are unchanged."
        )
        self._bullseye.toggled.connect(
            lambda v: self._mark_changed("bb_bullseye_check", v)
        )
        af.addRow(self._bullseye)

        self._scrum_fold_pct = QSpinBox()
        self._scrum_fold_pct.setRange(1, 100)
        self._scrum_fold_pct.setSuffix(" %")
        self._scrum_fold_pct.setValue(int(getattr(cfg, "scrum_fold_pct", 100)))
        self._scrum_fold_pct.setToolTip(
            "% of scrum sale proceeds queued for fold (rebuy).\n"
            "100% = full reentry (max accumulation, max risk).\n"
            "Lower values preserve cash buffer — safer when\n"
            "price keeps falling after the scrum."
        )
        self._scrum_fold_pct.valueChanged.connect(
            lambda v: self._mark_changed("scrum_fold_pct", v)
        )
        af.addRow("Scrum Fold Ratio:", self._scrum_fold_pct)

        from ...trading.bot_container import despawn_threshold_days

        self._tranche_despawn_days = QSpinBox()
        self._tranche_despawn_days.setRange(0, 365)
        self._tranche_despawn_days.setSuffix(" days")
        self._tranche_despawn_days.setSpecialValueText("Off")
        self._tranche_despawn_days.setValue(despawn_threshold_days(cfg))
        self._tranche_despawn_days.setToolTip(
            "DESPAWN any tranche this old - both fold tranches\n"
            "and stack tranches, from this one setting. 0 = Off\n"
            "(default).\n\n"
            "MERGE, DESPAWN and CLEAR are the only three things\n"
            "that collapse or remove a tranche. This is despawn:\n"
            "the age-driven one.\n\n"
            "IT IS NOT A TRADE. No order is placed or cancelled,\n"
            "no balance moves, holdings and cost basis are\n"
            "untouched. The record goes.\n\n"
            "WHAT THE RECORD HELD: the tranche's ref price, its\n"
            "parked fold USD, its units, and its initial_buy_price\n"
            "(the MEM-171 provenance figure). The scrum sale that\n"
            "made it already happened, so those dollars are\n"
            "already in the wallet - the record was only the\n"
            "queued intent to buy the units back. A despawned\n"
            "tranche can no longer fold back, so that money goes\n"
            "from queued rebuy to ordinary spendable balance.\n\n"
            "A tranche is despawned at exactly this age or older.\n"
            "A tranche with no timestamp is NEVER despawned, and\n"
            "a stack tranche holding a resting exchange order is\n"
            "kept until that order settles.\n\n"
            "SEE THE COUNT FIRST: the Fold Tranches tab prints how\n"
            "many of this bot's tranches each candidate window\n"
            "would remove, and what they hold."
        )
        self._tranche_despawn_days.valueChanged.connect(
            lambda v: self._mark_changed("tranche_despawn_days", v)
        )
        af.addRow("Tranche Despawn Timer:", self._tranche_despawn_days)

        self._wire_inflow_stack_pct = QDoubleSpinBox()
        self._wire_inflow_stack_pct.setRange(0.0, 100.0)
        self._wire_inflow_stack_pct.setDecimals(2)
        self._wire_inflow_stack_pct.setSuffix(" %")
        self._wire_inflow_stack_pct.setValue(
            float(getattr(cfg, "wire_inflow_stack_pct", 1.0))
        )
        self._wire_inflow_stack_pct.setToolTip(
            "Wire inflow stacking percentage. Controls how "
            "aggressively the bot stacks new buy-side positions "
            "when fresh wire-inflow signals arrive. Default 1.0%; "
            "rarely adjusted in practice."
        )
        self._wire_inflow_stack_pct.valueChanged.connect(
            lambda v: self._mark_changed("wire_inflow_stack_pct", float(v))
        )
        af.addRow("Wire Inflow Stack:", self._wire_inflow_stack_pct)

        layout.addWidget(adv_group)

        # --- Hedge Rebalance ---
        hedge_group = QGroupBox("Hedge Rebalance")
        hf = QFormLayout(hedge_group)
        self._configure_form(hf)

        self._hedge_active = QCheckBox("Hedge Rebalance Active")
        self._hedge_active.setChecked(bool(cfg.hedge_rebalance_active))
        self._hedge_active.setToolTip(
            "Separate USD reserve for buying on sharp drawdowns.\n"
            "NOT taken from Target Balance.\n\n"
            "Ticking this on a running bot fills the reserve up to "
            "Hedge Balance at once.\n"
            "Unticking keeps the reserve and refuses every hedge buy "
            "and every refill."
        )
        self._hedge_active.toggled.connect(
            lambda v: self._mark_changed("hedge_rebalance_active", v)
        )
        hf.addRow(self._hedge_active)

        self._hedge_balance = QDoubleSpinBox()
        self._hedge_balance.setRange(0.0, 999999999.0)
        self._hedge_balance.setDecimals(2)
        self._hedge_balance.setPrefix("$ ")
        self._hedge_balance.setValue(float(cfg.hedge_balance))
        self._hedge_balance.setToolTip(
            "USD reserve amount for hedge rebalancing (separate from "
            "Target Balance).\n\n"
            "$ 0.00 is NOT an off switch. It is an empty reserve that "
            "never refills,\n"
            "and any reserve the bot already holds stays spendable until "
            "it drains.\n"
            "Untick Hedge Rebalance Active to turn the hedge off."
        )
        self._hedge_balance.valueChanged.connect(
            lambda v: self._mark_changed("hedge_balance", v)
        )
        hf.addRow("Hedge Balance:", self._hedge_balance)

        layout.addWidget(hedge_group)

        cb_group = QGroupBox("Circuit Breakers (v3.15.58)")
        cf = QFormLayout(cb_group)
        self._configure_form(cf)

        self._cb_soft_pct = QDoubleSpinBox()
        self._cb_soft_pct.setRange(0.0, 100.0)
        self._cb_soft_pct.setDecimals(1)
        self._cb_soft_pct.setSuffix(" %")
        self._cb_soft_pct.setValue(
            float(getattr(cfg, "circuit_breaker_soft_pct", 25.0))
        )
        self._cb_soft_pct.setToolTip(
            "SOFT Circuit Breaker threshold. Single-candle move ≥ "
            "this % interrupts the side of the market that just "
            "moved (UP→SCRUM, DOWN→FOLD). Re-opens after cooldown "
            "candles. Default 25%. Set 0 to disable."
        )
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
        self._cb_hard_pct.setToolTip(
            "HARD Circuit Breaker threshold. Single-candle move ≥ "
            "this % PAUSES the bot. Operator reset required to "
            "resume. Persists across restart. Default 35%. Set 0 "
            "to disable."
        )
        self._cb_hard_pct.valueChanged.connect(
            lambda v: self._mark_changed("circuit_breaker_hard_pct", float(v))
        )
        cf.addRow("Hard CB Threshold:", self._cb_hard_pct)

        self._cb_cooldown = QSpinBox()
        self._cb_cooldown.setRange(1, 100)
        self._cb_cooldown.setValue(
            int(getattr(cfg, "circuit_breaker_cooldown_candles", 3))
        )
        self._cb_cooldown.setToolTip(
            "Number of candles the soft breaker stays active "
            "before re-opening. Default 3."
        )
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
        self._max_cartridge_pct.setToolTip(
            "Maximum |Target Delta| as % of Target Balance. "
            "When the position drifts beyond this %, the bot "
            "fires an immediate aggressive rebalance "
            "(bypasses BB Detection / hysteresis / soft CB / "
            "higher-TF bias). Default 10%. Set 0 to disable. "
            "v3.15.63."
        )
        self._max_cartridge_pct.valueChanged.connect(
            lambda v: self._mark_changed("max_cartridge_size_pct", float(v))
        )
        cf.addRow("Max Cartridge Size:", self._max_cartridge_pct)

        self._cartridge_smart_chk = QCheckBox("Calibrate to BB range")
        self._cartridge_smart_chk.setChecked(
            bool(getattr(cfg, "max_cartridge_smart", False))
        )
        self._cartridge_smart_chk.setToolTip(
            "When ON, Cartridge size is derived from current BB "
            "range rather than the static % above. Hard floor at "
            "the Opposing Trade Interval (cartridge cannot fire "
            "below the interval). Soft ceiling configured below. "
            "Default OFF preserves static behavior. v3.15.92."
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
        self._cartridge_smart_ceiling.setToolTip(
            "Maximum effective cartridge threshold under Smart "
            "calibration. Prevents cartridge from being "
            "effectively disabled during volatility expansion. "
            "Only applies when Smart Cartridge is ON. "
            "Default 30%. v3.15.92."
        )
        self._cartridge_smart_ceiling.valueChanged.connect(
            lambda v: self._mark_changed("max_cartridge_smart_ceiling_pct", float(v))
        )
        cf.addRow("Smart Ceiling:", self._cartridge_smart_ceiling)

        reset_row = QHBoxLayout()
        self._cb_reset_all_btn = QPushButton("Reset All Breakers")
        self._cb_reset_all_btn.setToolTip(
            "Operator override: clears any active soft and hard "
            "circuit breakers. Hard reset also resumes the bot if "
            "it is PAUSED."
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

        sd_group = QGroupBox("DANGER ZONE — Self-Destruct (v3.15.62)")
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
        self._self_destruct_btn.setToolTip(
            "Aggressively exit the entire position. " "Confirmation required."
        )
        self._self_destruct_btn.clicked.connect(self._on_self_destruct_clicked)
        sdv.addWidget(self._self_destruct_btn)
        layout.addWidget(sd_group)

        risk_group = QGroupBox("Risk Controls (MEM-244)")
        rf = QFormLayout(risk_group)
        self._configure_form(rf)

        self._ceiling_enabled = QCheckBox("Enable Position Ceiling")
        self._ceiling_enabled.setChecked(
            bool(getattr(cfg, "position_ceiling_enabled", False))
        )
        self._ceiling_enabled.setToolTip(
            "Cap accumulation at Nx of the bot's INITIAL "
            "target_balance (stable anchor set at creation).\n"
            "Fold rate tapers 100% → 10% as value approaches "
            "ceiling (ratio 0.5 → 1.0), hard-stops at ceiling.\n"
            "Scrum always allowed. Protects against runaway "
            "accumulation on conviction plays."
        )
        self._ceiling_enabled.toggled.connect(
            lambda v: self._mark_changed("position_ceiling_enabled", v)
        )
        rf.addRow(self._ceiling_enabled)

        self._ceiling_mult = QDoubleSpinBox()
        self._ceiling_mult.setRange(1.0, 10.0)
        self._ceiling_mult.setDecimals(1)
        self._ceiling_mult.setSingleStep(0.5)
        self._ceiling_mult.setSuffix("x anchor")
        self._ceiling_mult.setValue(
            float(getattr(cfg, "position_ceiling_multiple", 5.0))
        )
        self._ceiling_mult.setToolTip(
            "Ceiling multiplier. 1x = no accumulation beyond "
            "anchor. 10x = 10x runway. Default 5x."
        )
        self._ceiling_mult.valueChanged.connect(
            lambda v: self._mark_changed("position_ceiling_multiple", v)
        )
        rf.addRow("Ceiling Multiple:", self._ceiling_mult)

        self._deto_enabled = QCheckBox("Enable Detonation (auto-harvest on bullish TF)")
        self._deto_enabled.setChecked(bool(getattr(cfg, "detonation_enabled", False)))
        self._deto_enabled.setToolTip(
            "Monitor a higher TF for BULLISH + high-confidence "
            "signal. Edge-triggered: fires ONCE per transition "
            "into bullish state.\n"
            "On trigger: MARKET sell everything above the anchor, "
            "then reset target_balance to anchor ('lock in' gains, "
            "re-accumulate from scratch).\n"
            "Rate-limited to 1 check/hour.\n"
            "Additional gate: fires only when current value is "
            "above the anchor — no harvest if the bot is below "
            "its initial anchor."
        )
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
        self._deto_tf.setToolTip(
            "Timeframe to monitor for bullish detonation signal. "
            "1D = daily, 1W = weekly. Higher = stronger conviction, "
            "fewer triggers."
        )
        self._deto_tf.currentTextChanged.connect(
            lambda v: self._mark_changed("detonation_timeframe", v)
        )
        rf.addRow("Detonation TF:", self._deto_tf)

        self._deto_conf = QDoubleSpinBox()
        self._deto_conf.setRange(0.50, 1.00)
        self._deto_conf.setDecimals(2)
        self._deto_conf.setSingleStep(0.05)
        self._deto_conf.setValue(float(getattr(cfg, "detonation_confidence_min", 0.75)))
        self._deto_conf.setToolTip(
            "Minimum TA consensus confidence for detonation. "
            "Default 0.75 (high conviction only, per MEM-244)."
        )
        self._deto_conf.valueChanged.connect(
            lambda v: self._mark_changed("detonation_confidence_min", v)
        )
        rf.addRow("Min Confidence:", self._deto_conf)

        layout.addWidget(risk_group)

        gates_group = QGroupBox("Strategy Gate Flags (v3.16.15)")
        gf = QFormLayout(gates_group)
        self._configure_form(gf)

        self._gate_scrum_ta = QCheckBox("SCRUM requires bullish TA")
        self._gate_scrum_ta.setChecked(
            bool(getattr(cfg, "scrum_require_ta_bullish", True))
        )
        self._gate_scrum_ta.setToolTip(
            "ON (Conservative): scrum auto-fire requires TA "
            "consensus BULLISH. Protects against scrumming "
            "false tops. OFF (Lean): scrum fires at BB-upper + "
            "delta regardless of TA."
        )
        self._gate_scrum_ta.toggled.connect(
            lambda v: self._mark_changed("scrum_require_ta_bullish", v)
        )
        gf.addRow(self._gate_scrum_ta)

        self._gate_scrum_uptrend = QCheckBox("SCRUM holds in sustained uptrend")
        self._gate_scrum_uptrend.setChecked(
            bool(getattr(cfg, "scrum_hold_in_uptrend", True))
        )
        self._gate_scrum_uptrend.setToolTip(
            "ON (Conservative): if 65 %+ of last 20 candles "
            "were bullish, bot holds rather than scrumming "
            "each band touch. OFF (Lean): scrum every "
            "BB-upper touch regardless of trend strength."
        )
        self._gate_scrum_uptrend.toggled.connect(
            lambda v: self._mark_changed("scrum_hold_in_uptrend", v)
        )
        gf.addRow(self._gate_scrum_uptrend)

        self._gate_scrum_htf = QCheckBox("SCRUM defers to higher-TF bullish")
        self._gate_scrum_htf.setChecked(bool(getattr(cfg, "scrum_defer_to_htf", True)))
        self._gate_scrum_htf.setToolTip(
            "ON (Conservative): refuse scrum when a higher-TF "
            "phantom signals BULLISH. OFF (Lean): cartridge "
            "captures HTF swings organically; this gate is "
            "redundant if Smart Cartridge is ON."
        )
        self._gate_scrum_htf.toggled.connect(
            lambda v: self._mark_changed("scrum_defer_to_htf", v)
        )
        gf.addRow(self._gate_scrum_htf)

        self._gate_fold_ta = QCheckBox("FOLD requires bearish TA")
        self._gate_fold_ta.setChecked(
            bool(getattr(cfg, "fold_require_ta_bearish", True))
        )
        self._gate_fold_ta.setToolTip(
            "ON (Conservative): mirror of SCRUM TA gate on "
            "the fold side. OFF (Lean): fold fires at "
            "BB-lower + tranche-eligible regardless of TA."
        )
        self._gate_fold_ta.toggled.connect(
            lambda v: self._mark_changed("fold_require_ta_bearish", v)
        )
        gf.addRow(self._gate_fold_ta)

        self._gate_fold_htf = QCheckBox("FOLD defers to higher-TF bearish")
        self._gate_fold_htf.setChecked(bool(getattr(cfg, "fold_defer_to_htf", True)))
        self._gate_fold_htf.setToolTip(
            "ON (Conservative): mirror of SCRUM HTF gate on "
            "the fold side. OFF (Lean): fold fires regardless "
            "of higher-TF bearish bias."
        )
        self._gate_fold_htf.toggled.connect(
            lambda v: self._mark_changed("fold_defer_to_htf", v)
        )
        gf.addRow(self._gate_fold_htf)

        layout.addWidget(gates_group)

        if cfg.mode.value == "extractor":
            ext_group = QGroupBox("Extractor — Pool & Artillery")
            ef = QFormLayout(ext_group)
            self._configure_form(ef)

            self._ext_chunk_size = QDoubleSpinBox()
            self._ext_chunk_size.setRange(10.0, 10_000_000.0)
            self._ext_chunk_size.setDecimals(2)
            self._ext_chunk_size.setPrefix("$")
            self._ext_chunk_size.setValue(
                float(getattr(cfg, "extractor_chunk_size_usd", 100.0))
            )
            self._ext_chunk_size.setToolTip(
                "USD-equivalent of base currency this bot owns. "
                "Sized at construction; changing live re-anchors "
                "the pool's reference USD value (not the held base "
                "units — those are exchange-tracked)."
            )
            self._ext_chunk_size.valueChanged.connect(
                lambda v: self._mark_changed("extractor_chunk_size_usd", v)
            )
            ef.addRow("Pool size (USD):", self._ext_chunk_size)

            self._ext_artillery_size = QDoubleSpinBox()
            self._ext_artillery_size.setRange(0.5, 100_000.0)
            self._ext_artillery_size.setDecimals(2)
            self._ext_artillery_size.setPrefix("$")
            self._ext_artillery_size.setValue(
                float(getattr(cfg, "extractor_artillery_size_usd", 5.0))
            )
            self._ext_artillery_size.setToolTip(
                "USD-equivalent per artillery round. Smaller = more "
                "opportunities; larger = bigger per-round impact."
            )
            self._ext_artillery_size.valueChanged.connect(
                lambda v: self._mark_changed("extractor_artillery_size_usd", v)
            )
            ef.addRow("Artillery size (USD):", self._ext_artillery_size)

            self._ext_scan_top_n = QSpinBox()
            self._ext_scan_top_n.setRange(5, 10)
            self._ext_scan_top_n.setValue(int(getattr(cfg, "extractor_scan_top_n", 8)))
            self._ext_scan_top_n.setToolTip(
                "Top-N */<base> pairs by 24h volume to keep on the "
                "auto-scan watch list. Range [5, 10] per design "
                "doc §6. Ignored when manual alt-targets are set."
            )
            self._ext_scan_top_n.valueChanged.connect(
                lambda v: self._mark_changed("extractor_scan_top_n", v)
            )
            ef.addRow("Auto-scan top-N:", self._ext_scan_top_n)

            self._ext_scan_refresh = QSpinBox()
            # The wizard row and the manual both offer 10 to 240 candles.
            self._ext_scan_refresh.setRange(10, 240)
            self._ext_scan_refresh.setSuffix(" candles")
            self._ext_scan_refresh.setValue(
                int(getattr(cfg, "extractor_scan_refresh_candles", 60))
            )
            self._ext_scan_refresh.setToolTip(
                "Candles of this bot's timeframe between watch-list "
                "refreshes. Lower = more responsive; higher = less "
                "thrashing."
            )
            self._ext_scan_refresh.valueChanged.connect(
                lambda v: self._mark_changed("extractor_scan_refresh_candles", v)
            )
            ef.addRow("Scan refresh:", self._ext_scan_refresh)

            self._ext_exit_pct = QDoubleSpinBox()
            self._ext_exit_pct.setRange(10.0, 100.0)
            self._ext_exit_pct.setDecimals(1)
            self._ext_exit_pct.setSuffix(" %")
            self._ext_exit_pct.setValue(
                float(getattr(cfg, "extractor_exit_pct", 100.0))
            )
            self._ext_exit_pct.setToolTip(
                "% of alt position sold on bullish trigger. "
                "100 = full exit; <100 leaves a rider tail."
            )
            self._ext_exit_pct.valueChanged.connect(
                lambda v: self._mark_changed("extractor_exit_pct", v)
            )
            ef.addRow("Exit %:", self._ext_exit_pct)

            layout.addWidget(ext_group)

        layout.addStretch()
        return w
