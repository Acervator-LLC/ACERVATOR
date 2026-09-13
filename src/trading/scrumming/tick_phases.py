"""Phase methods behind ScrummingBot.tick: one concern per pass."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Optional

from ..target_bands import at_target_dust_band
from ..ta_engine import VotingEngine, candles_from_raw, detect_bb_proximity
from .snapshots import yes_no as _yes_no

logger = logging.getLogger("acervator.scrumming")


class TickPhaseMixin:
    """One method per phase of the trade loop, called in order by tick."""

    # Bare annotations: ScrummingBot supplies these at runtime, and
    # no attribute is created here.
    _absorb_pending_wire_credits_into: Callable[..., None]
    _aggressive: bool
    _anchor_target_balance: float
    _apply_fold_target_growth: Callable[..., Any]
    _apply_scrum_fold_pct: Callable[..., None]
    _below_min_fold_log_ts: float
    _below_min_scrum_log_ts: float
    _bound_new_fold_tranches: Callable[..., Any]
    _bus: Any
    _cartridge_last_smart_pct: float
    _check_detonation_trigger: Callable[..., Any]
    _current_holdings: float
    _dist_accumulator: float
    _drop_malformed_fold_tranches: Callable[..., int]
    _emit_gate_decision_at_fire: Callable[..., None]
    _emit_trade_fire_snapshot: Callable[..., None]
    _emit_trade_notification: Callable[..., None]
    _emit_voting_panel_snapshot_at_fire: Callable[..., None]
    _execute_buy: Callable[..., Any]
    _execute_detonation: Callable[..., Any]
    _execute_manual_rebalance: Callable[..., Any]
    _execute_sell: Callable[..., Any]
    _fold_cycle_cap_consumed: float
    _fold_diag_last_blocker_set: str
    _fold_diag_tick: int
    _fold_eligible_tranches: Callable[..., list[dict]]
    _fold_queue_ref_price: float
    _fill_fee_fields: Callable[..., dict]
    _fold_queue_usd: float
    _fold_tranches: list[dict]
    _get_balance: Callable[..., Any]
    _get_market_limits: Callable[..., Any]
    _get_ohlcv: Callable[..., Any]
    _get_ticker: Callable[..., Any]
    _hedge_bal: float
    _hedge_trades: int
    _initialised: Any
    _invisible: bool
    _land_pending_wire_credits: Callable[..., float]
    _last_price: float
    _last_summary: Any
    _last_trade_price: float
    _last_trade_side: Optional[str]
    _main_lots: list[dict]
    _manual_fire_pending: bool
    _pending_stack_buy_usd: float
    _pending_wire_credits: float
    _phantom_gate_logged: bool
    _phantom_mgr: Any
    _phantom_tf_dropped_note: Optional[str]
    _phantom_timeframes: list[str]
    _phantoms_enabled: bool
    _phantoms_started: bool
    _plan_fold_consumption: Callable[..., Any]
    _quote_to_usd: float
    _refresh_quote_to_usd: Callable[..., Any]
    _reset_opposing_hysteresis_after_fill: Callable[..., None]
    _route_scrum_proceeds_via_wires: Callable[..., float]
    _scrum_target_mode: str
    _scrum_target_side: Optional[str]
    _settle_fold_plan: Callable[..., Any]
    _settled_sale_proceeds: Callable[..., float]
    _smart_wire_mgr: Any
    _standing_surplus_usd: float
    _sum_sibling_base_currency_claims: Callable[..., float]
    _ta_weights: Any
    _target_balance: Any
    _target_grow_last_side: Optional[str]
    _top_up_remnant_fold_tranches: Callable[..., Any]
    _tranches_closed_lifetime: int
    _tranches_created_lifetime: int
    _underfunded_log_counter: int
    _verify_buy_safe_or_refuse: Callable[..., Any]
    bot_id: Any
    config: Any
    exchange: Any
    note_scrum_retention_usd: Callable[..., None]
    reset_swos_cycle: Callable[..., None]
    stats: Any

    @property
    def _hedge_balance_initial(self) -> float:
        """Return the hedge ceiling off config.hedge_balance, and zero while
        hedge_rebalance_active is off."""
        if not self.config.hedge_rebalance_active:
            return 0.0
        return float(self.config.hedge_balance)

    @_hedge_balance_initial.setter
    def _hedge_balance_initial(self, value: float) -> None:
        """Write the ceiling onto config.hedge_balance, the one place it is
        stored."""
        self.config.hedge_balance = float(value)

    async def _tick_initialise(self, symbol: str) -> None:
        """Run the boot handshake; the tick ends whatever this decides."""
        ticker = await self._get_ticker(symbol)
        self._last_price = ticker.last
        self.stats.current_price = ticker.last
        try:
            await self._refresh_quote_to_usd()
        except Exception as _sup:
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        try:
            _bal1 = await self._get_balance(self.config.target_asset)
            _h1 = float(getattr(_bal1, "total", 0) or _bal1.free or 0)
            await asyncio.sleep(0.25)
            _bal2 = await self._get_balance(self.config.target_asset)
            _h2 = float(getattr(_bal2, "total", 0) or _bal2.free or 0)
        except Exception as _hs_exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"INIT HANDSHAKE FAILED: exchange balance fetch "
                    f"raised ({_hs_exc}). Bot NOT marked initialised. "
                    f"Outer loop will retry on next tick. Refusing to "
                    f"proceed with unknown holdings."
                ),
            )
            logger.warning(
                "Bot %s init handshake raised: %s; will retry", self.bot_id, _hs_exc
            )
            raise

        _max_h = max(_h1, _h2)
        _abs_diff = abs(_h1 - _h2)
        _rel_diff = _abs_diff / _max_h if _max_h > 0 else 0.0
        if _max_h > 0 and _rel_diff > 0.001:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"INIT HANDSHAKE MISMATCH: two successive "
                    f"get_balance reads returned "
                    f"{_h1:.6f} vs {_h2:.6f} ({_rel_diff*100:.2f}% "
                    f"diff). Refusing to initialise on an uncertain "
                    f"read. Retrying next tick."
                ),
            )
            logger.warning(
                "Bot %s init handshake mismatch: %.6f vs %.6f",
                self.bot_id,
                _h1,
                _h2,
            )
            return

        if getattr(_bal1, "absent", False) or getattr(_bal2, "absent", False):
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"INIT HANDSHAKE REFUSED (absent-sentinel): "
                    f"exchange OMITTED "
                    f"{self.config.target_asset} from "
                    f"fetch_balance response "
                    f"(bal1.absent={getattr(_bal1, 'absent', '?')}, "
                    f"bal2.absent={getattr(_bal2, 'absent', '?')}). "
                    f"Cannot verify holdings. Will NOT initialise bot "
                    f"on a structurally-zeroed read. Retrying next tick."
                ),
            )
            logger.warning(
                "Bot %s init handshake refused — %s absent from exchange response",
                self.bot_id,
                self.config.target_asset,
            )
            return

        _lots_units = sum(float(lot.get("units", 0) or 0) for lot in self._main_lots)
        if _h2 == 0.0 and _lots_units > 0.0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"INIT HANDSHAKE REFUSED (lots-cross-check): "
                    f"exchange reports 0 {self.config.target_asset} "
                    f"but restored state shows {_lots_units:.6f} "
                    f"units in _main_lots. Refusing to overwrite "
                    f"persisted holdings with a suspicious zero. If "
                    f"the position was genuinely liquidated "
                    f"off-platform, operator must clear _main_lots "
                    f"via state reset tool. Retrying next tick."
                ),
            )
            logger.warning(
                "Bot %s init handshake refused — exchange=0 vs " "restored lots=%.6f",
                self.bot_id,
                _lots_units,
            )
            return

        _never_scrummed = (
            int(getattr(self, "_tranches_created_lifetime", 0) or 0) == 0
            and float(getattr(self, "_tranches_counters_reset_ts", 0.0) or 0.0) <= 0.0
        )
        if _never_scrummed and _h2 > 0:
            _sib_units = 0.0
            _mgr = getattr(self, "_bot_manager", None)
            if _mgr is not None:
                try:
                    if _mgr.has_sibling_target_bots(
                        self.bot_id, self.config.target_asset
                    ):
                        _sib_units = float(
                            _mgr.sum_sibling_tracked_units(
                                self.bot_id, self.config.target_asset
                            )
                            or 0.0
                        )
                except Exception as _sib_exc:  # noqa: BLE001
                    _sib_units = float(_h2)
                    logger.warning(
                        "Bot %s adoption: sibling query raised (%s); "
                        "claiming nothing",
                        self.bot_id,
                        _sib_exc,
                    )
            _own = max(0.0, float(_h2) - _sib_units)

            _px_cap = float(getattr(ticker, "last", 0.0) or 0.0)
            _cap_usd = float(self._target_balance or 0.0)
            _uncapped = _own
            _was_capped = False
            if _cap_usd > 0 and _px_cap > 0 and _own * _px_cap > _cap_usd:
                _own = _cap_usd / _px_cap
                _was_capped = True
            if _was_capped:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"ADOPTION CAPPED: exchange holds "
                        f"{_uncapped:.6f} {self.config.target_asset} but "
                        f"this bot may adopt at most ${_cap_usd:.2f} "
                        f"({_own:.6f} units @ ${_px_cap:.8f}). The "
                        f"remaining {_uncapped - _own:.6f} units stay "
                        f"unmanaged. Raise this bot's Target Balance to "
                        f"change this."
                    ),
                )
                try:
                    from src.core.signal_contract import emit as _cap_emit

                    _cap_emit(
                        "bot.01.003.postcondition.adoption_capped",
                        actual=round(_own, 10),
                        expected=round(_uncapped, 10),
                        context={
                            "bot_id": str(self.bot_id),
                            "asset": str(self.config.target_asset),
                            "cap_usd": _cap_usd,
                            "withheld_units": round(_uncapped - _own, 10),
                        },
                    )
                except Exception as _sup:  # noqa: BLE001
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "tick",
                        type(_sup).__name__,
                        _sup,
                    )

            _held = sum(float(lot.get("units", 0) or 0) for lot in self._main_lots)
            if _own > 0.0 and abs(_own - _held) > 1e-12:
                _px = float(getattr(ticker, "last", 0.0) or 0.0)
                _basis_src = "ticker"
                _basis = _px
                try:
                    _cb = float(
                        getattr(self.stats, "cost_basis_total_exchange", 0.0) or 0.0
                    )
                    if _cb > 0:
                        _basis = _cb / _own
                        _basis_src = "exchange cost basis"
                except (TypeError, ValueError, ZeroDivisionError) as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "tick",
                        type(_sup).__name__,
                        _sup,
                    )
                if _basis > 0:
                    self._main_lots = [
                        {
                            "units": _own,
                            "initial_buy_price": _basis,
                        }
                    ]
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"OPENING POSITION ADOPTED: {_own:.6f} "
                            f"{self.config.target_asset} held on the exchange "
                            f"(${_own * _px:.2f} @ ${_px:.8f}) is this bot's "
                            f"opening position; cost basis ${_basis:.8f} from "
                            f"{_basis_src}. This bot has never scrummed, so "
                            f"it has no earned history to protect"
                            + (
                                f"; {_sib_units:.6f} units excluded as sibling"
                                f"-tracked"
                                if _sib_units > 0
                                else ""
                            )
                            + f". Previously tracked {_held:.6f}."
                        ),
                    )
                    logger.info(
                        "Bot %s adopted opening position: %.8f %s @ %.8f "
                        "(was %.8f, sibling-tracked %.8f)",
                        self.bot_id,
                        _own,
                        self.config.target_asset,
                        _basis,
                        _held,
                        _sib_units,
                    )

        self._current_holdings = sum(
            float(lot.get("units", 0) or 0) for lot in self._main_lots
        )
        self._initialised = True
        _qrate = float(self._quote_to_usd or 1.0)
        _init_usd = self._current_holdings * ticker.last * _qrate
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"INIT HANDSHAKE OK: position=${_init_usd:.2f} "
                f"verified across 2 reads within tolerance. "
                f"(forensic: {self._current_holdings:.6f} "
                f"{self.config.target_asset} @ ${ticker.last:.8f}"
                f'{chr(44)+chr(32)+f"quote-USD={_qrate:.4f}" if abs(_qrate - 1.0) > 1e-9 else ""})'
            ),
        )

        _init_usd = (
            self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
        )
        _init_delta = _init_usd - self._target_balance
        _init_region = (
            "on-target"
            if abs(_init_delta) < at_target_dust_band(self._target_balance)
            else (
                "above target by " + f"${_init_delta:+.2f}"
                if _init_delta > 0
                else "below target by " + f"${_init_delta:+.2f}"
            )
        )
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"Scrumming init: {symbol} position=${_init_usd:.2f} "
                f"vs target=${self._target_balance:.2f} ({_init_region}). "
                f"(forensic: {self._current_holdings:.6f} "
                f"{self.config.target_asset} @ ${ticker.last:.8f})"
            ),
        )
        vis = "INVISIBLE" if self._invisible else "ORDER BOOK"
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=f"  Mode: {vis}" f"{' + AGGRESSIVE' if self._aggressive else ''}",
        )

        if not getattr(self, "_phantom_gate_logged", False):
            logger.info(
                "P0g-DIAG | bot=%s tick-gate _phantoms_enabled=%s "
                "_phantoms_started=%s timeframes=%s",
                self.bot_id[:8],
                self._phantoms_enabled,
                self._phantoms_started,
                self._phantom_timeframes,
            )
            self._phantom_gate_logged = True
        if self._phantoms_enabled and not self._phantoms_started:
            self._phantom_mgr.create_phantom_set(
                parent_bot_id=self.bot_id,
                timeframes=self._phantom_timeframes,
                target_balance=self._target_balance,
                exchange=self.exchange,
                symbol=symbol,
                ta_weights=self._ta_weights,
            )
            await self._phantom_mgr.start_all(self.bot_id)
            self._phantoms_started = True
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"  Phantoms: {len(self._phantom_timeframes)} TFs active "
                f"({', '.join(self._phantom_timeframes)})",
            )
            if self._phantom_tf_dropped_note:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=self._phantom_tf_dropped_note,
                )

    async def _tick_manual_fire(self, ticker: Any) -> None:
        """Run the operator-invoked rebalance for this tick."""
        _mf_usd = (
            self._current_holdings * ticker.last * float(self._quote_to_usd or 1.0)
        )
        _mf_delta = _mf_usd - self._target_balance
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"MANUAL FIRE: tick reached rebalance entry. "
                f"position=${_mf_usd:.2f} vs target=${self._target_balance:.2f} "
                f"(delta=${_mf_delta:+.2f}). Executing rebalance... "
                f"(forensic: holdings={self._current_holdings:.6f} "
                f"price=${ticker.last:.8f} target=${self._target_balance:.2f})"
            ),
        )
        try:
            await self._execute_manual_rebalance(ticker, caller_intent="manual_button")
        except Exception as exc:
            self._manual_fire_pending = False
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"MANUAL FIRE: exception during rebalance: {exc}",
            )
            logger.exception("Manual fire rebalance failed")

    async def _tick_wire_stack_fire(self, ticker: Any, _stack_pending: float) -> None:
        """Acquire a pending wire-stack allocation by aggressive rebalance."""
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"WIRE STACK FIRE: acquiring ${_stack_pending:.2f} of "
                f"{self.config.target_asset} via aggressive rebalance "
                f"to new target ${self._target_balance:.2f}."
            ),
        )
        try:
            self._emit_trade_notification(
                "WIRE_STACK", "SENT", f"${_stack_pending:.2f} acquisition"
            )
        except Exception as _sup:
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
        self._pending_stack_buy_usd = 0.0
        _verified_units, _refuse_msg = await self._verify_buy_safe_or_refuse(
            path="wire_stack"
        )
        if _refuse_msg:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=_refuse_msg)
            logger.warning("Bot %s %s", self.bot_id, _refuse_msg)
            return
        try:
            await self._execute_manual_rebalance(ticker, caller_intent="wire_stack")
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"WIRE STACK FIRE: rebalance raised " f"{type(exc).__name__}: {exc}"
                ),
            )
            logger.exception("Wire stack rebalance failed")

    def _tick_smart_cartridge_pct(self, _cartridge_pct: float) -> float:
        """Return the cartridge threshold percent, BB-calibrated when enabled."""
        _smart_bb = getattr(self, "_last_bb", None)
        if (
            getattr(self.config, "max_cartridge_smart", False)
            and _smart_bb is not None
            and getattr(_smart_bb, "upper", 0) > 0
            and getattr(_smart_bb, "lower", 0) > 0
        ):
            try:
                _bb_mid = (
                    getattr(_smart_bb, "bb_middle", 0)
                    or getattr(_smart_bb, "middle", 0)
                    or ((_smart_bb.upper + _smart_bb.lower) / 2.0)
                )
                if _bb_mid > 0:
                    _bb_range_pct = (
                        (_smart_bb.upper - _smart_bb.lower) / _bb_mid * 100.0
                    )
                    _interval_floor = float(self.config.scrumming_interval_pct or 0)
                    _smart_ceiling = float(
                        getattr(self.config, "max_cartridge_smart_ceiling_pct", 30.0)
                        or 30.0
                    )
                    _smart_pct = max(
                        _interval_floor, min(_smart_ceiling, _bb_range_pct)
                    )
                    _last_smart = float(
                        getattr(self, "_cartridge_last_smart_pct", 0.0) or 0.0
                    )
                    if abs(_smart_pct - _last_smart) >= 1.0:
                        try:
                            self._bus.emit(
                                "bot.log",
                                bot_id=self.bot_id,
                                message=(
                                    f"SMART CARTRIDGE calibrated to "
                                    f"{_smart_pct:.2f}% "
                                    f"(BB range {_bb_range_pct:.2f}%, "
                                    f"floor={_interval_floor:.2f}%, "
                                    f"ceiling={_smart_ceiling:.2f}%). "
                                    f"Effective threshold = "
                                    f"${self._target_balance * _smart_pct / 100.0:.2f}."
                                ),
                            )
                        except Exception as _sup:
                            logger.debug(
                                "suppressed in %s: %s: %s",
                                "tick",
                                type(_sup).__name__,
                                _sup,
                            )
                        self._cartridge_last_smart_pct = _smart_pct
                    _cartridge_pct = _smart_pct
            except (TypeError, ValueError, ZeroDivisionError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
        return _cartridge_pct

    async def _tick_cartridge_fire(
        self,
        ticker: Any,
        _direction: str,
        _cartridge_delta: float,
        _cartridge_threshold: float,
        _cartridge_pct: float,
    ) -> None:
        """Fire the max-cartridge rebalance; the tick ends after this."""
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"MAX CARTRIDGE FIRE ({_direction}): "
                f"|delta|=${abs(_cartridge_delta):.2f} "
                f"≥ threshold ${_cartridge_threshold:.2f} "
                f"({_cartridge_pct:.1f}% of target "
                f"${self._target_balance:.2f}). "
                f"Hysteresis clear. Firing aggressive "
                f"rebalance — bypasses BB Detection / "
                f"soft CB / higher-TF bias gates. "
                f"v3.15.79 NO LONGER bypasses "
                f"opposing-direction hysteresis."
            ),
        )
        if _direction == "FOLD":
            _verified_units, _refuse_msg = await self._verify_buy_safe_or_refuse(
                path="cartridge_fold"
            )
            if _refuse_msg:
                self._bus.emit("bot.log", bot_id=self.bot_id, message=_refuse_msg)
                logger.warning("Bot %s %s", self.bot_id, _refuse_msg)
                return
        try:
            self._emit_trade_notification(
                f"CARTRIDGE_{_direction}",
                "SENT",
                f"|delta|=${abs(_cartridge_delta):.2f} ≥ "
                f"${_cartridge_threshold:.2f}",
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "tick",
                type(_sup).__name__,
                _sup,
            )
        try:
            await self._execute_manual_rebalance(ticker, caller_intent="max_cartridge")
        except Exception as exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MAX CARTRIDGE: rebalance raised " f"{type(exc).__name__}: {exc}"
                ),
            )
            logger.exception("Max cartridge rebalance failed")

    async def _tick_detonation(self, ticker: Any) -> bool:
        """Return True when a detonation fired and the tick must stop."""
        if getattr(self.config, "detonation_enabled", False):
            try:
                fired = await self._check_detonation_trigger(ticker)
                if fired:
                    await self._execute_detonation(ticker)
                    return True
            except Exception as exc:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"DETONATION: check/execute raised: " f"{exc}. Continuing tick."
                    ),
                )
                logger.exception("Detonation raised")
        return False

    async def _tick_initial_entry(
        self, ticker: Any, symbol: str, current_value: float
    ) -> None:
        """Decide and place the structural entry buy for an empty position."""
        try:
            _fresh_bal = await self._get_balance(self.config.target_asset)
            _fresh_units = float(_fresh_bal.free or 0)
        except Exception as _fb_exc:
            _fresh_units = None
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"INITIAL ENTRY: fresh balance fetch raised "
                    f"({type(_fb_exc).__name__}: {_fb_exc}). "
                    f"Falling back to internal state. If phantom-"
                    f"buy appears, check exchange UI directly."
                ),
            )

        if _fresh_units is not None:
            _qrate = float(self._quote_to_usd or 1.0)
            _attributed_units = sum(
                float(lot.get("units", 0) or 0) for lot in self._main_lots
            )
            _fresh_units_eff = _attributed_units
            _fresh_usd = _attributed_units * ticker.last * _qrate

            if self._current_holdings > 0 and _fresh_units_eff == 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INITIAL ENTRY BLOCKED (Phase-B guard a): "
                        f"attributed units 0 but saved state "
                        f"holds {self._current_holdings:.6f} "
                        f"units "
                        f"(~${self._current_holdings * ticker.last * _qrate:.2f}). "
                        f"Refusing buy on top of existing position. "
                        f"Clear saved state manually before restart."
                    ),
                )
                return

            _value_threshold = max(
                self._target_balance * 0.25, max(self._target_balance * 0.01, 1.0)
            )
            if _fresh_usd >= _value_threshold:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INITIAL ENTRY BLOCKED (Phase-B guard b): "
                        f"fresh USD value ${_fresh_usd:.2f} "
                        f"({_fresh_units_eff:.6f} {self.config.target_asset} "
                        f"@ ${ticker.last:.8f}) ≥ threshold "
                        f"${_value_threshold:.2f}. Not empty — let "
                        f"the regular scrum/fold cycle handle this "
                        f"position instead of initial entry."
                    ),
                )
                return

            if getattr(self.config, "position_ceiling_enabled", False):
                try:
                    _smart_mult = float(
                        getattr(self.config, "position_ceiling_multiple", 1.0)
                    )
                    _smart_mult = max(1.0, min(10.0, _smart_mult))
                    _smart_ceiling_usd = self._anchor_target_balance * _smart_mult
                    _prospective = _fresh_usd + self._target_balance
                    if _prospective > _smart_ceiling_usd:
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"INITIAL ENTRY BLOCKED "
                                f"(Position Ceiling): prospective "
                                f"position ${_prospective:.2f} "
                                f"(existing ${_fresh_usd:.2f} + "
                                f"buy ${self._target_balance:.2f}) "
                                f"would exceed Position Ceiling "
                                f"${_smart_ceiling_usd:.2f} "
                                f"(anchor "
                                f"${self._anchor_target_balance:.2f} "
                                f"× Ceiling Multiple {_smart_mult:.1f}x). "
                                f"Refusing buy."
                            ),
                        )
                        return
                except (TypeError, ValueError, AttributeError) as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "tick",
                        type(_sup).__name__,
                        _sup,
                    )

        try:
            _quote_bal = await self._get_balance(self.config.base_currency)
            _quote_free_raw = float(_quote_bal.free or 0)
        except Exception as _qb_exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"INITIAL ENTRY BLOCKED: quote-currency balance "
                    f"fetch raised ({_qb_exc}). Retrying next tick."
                ),
            )
            return

        _sibling_claims = self._sum_sibling_base_currency_claims()
        _quote_free = _quote_free_raw - _sibling_claims
        if _quote_free < 0:
            self._underfunded_log_counter = (
                getattr(self, "_underfunded_log_counter", 0) + 1
            )
            if self._underfunded_log_counter % 60 == 1:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INITIAL ENTRY BLOCKED (over-allocation): "
                        f"raw {self.config.base_currency} free "
                        f"${_quote_free_raw:.2f} − sibling claims "
                        f"${_sibling_claims:.2f} = "
                        f"${_quote_free:.2f} (negative). Operator has "
                        f"over-allocated capital across bots on this "
                        f"exchange. Refusing to fire until allocations "
                        f"are rebalanced. Reduce another bot's "
                        f"target_balance OR add base-currency funds OR "
                        f"pause a sibling bot to release its claim."
                    ),
                )
            return

        if _quote_free < self._target_balance:
            self._underfunded_log_counter = (
                getattr(self, "_underfunded_log_counter", 0) + 1
            )
            if self._underfunded_log_counter % 60 == 1:
                _have_str = (
                    f"${_quote_free:.2f} after sibling claims "
                    f"${_sibling_claims:.2f} (raw ${_quote_free_raw:.2f})"
                    if _sibling_claims > 0
                    else f"${_quote_free:.2f}"
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INITIAL ENTRY BLOCKED: insufficient "
                        f"{self.config.base_currency} — have "
                        f"{_have_str}, need "
                        f"${self._target_balance:.2f}. "
                        f"({self.config.target_asset} position: "
                        f"{self._current_holdings:.6f} @ "
                        f"${ticker.last:.8f} = "
                        f"${current_value:.2f})"
                    ),
                )
            return
        self._underfunded_log_counter = 0

        candles = await self._get_ohlcv(symbol, self.config.ta_timeframe, limit=100)
        if candles and len(candles) >= 30:
            engine = VotingEngine()
            parsed = candles_from_raw(candles)
            summary = engine.compute_all(
                parsed, self.config.ta_timeframe, symbol=self.config.symbol
            )
            self._last_summary = summary

            _wallet = (
                f" [{self.config.base_currency}: ${_quote_free:.2f} · "
                f"{self.config.target_asset}: "
                f"{self._current_holdings:.6f} = "
                f"${current_value:.2f}]"
            )

            _init_bb = detect_bb_proximity(
                parsed,
                tolerance_pct=self.config.bb_tolerance_pct,
                consolidation_threshold=3.0,
                min_pattern_candles=self.config.bb_landing_strip_candles,
            )
            if (
                _init_bb is None
                or _init_bb.upper <= 0
                or _init_bb.lower <= 0
                or _init_bb.upper <= _init_bb.lower
            ):
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"INITIAL ENTRY BLOCKED: BB data not yet "
                    f"computable — need proper band formation "
                    f"before entry. Price=${ticker.last:.8f}"
                    f"{_wallet}",
                )
                return

            _init_price = ticker.last
            _init_bb_width = _init_bb.upper - _init_bb.lower
            _init_bb_pos = (_init_price - _init_bb.lower) / max(_init_bb_width, 1e-12)

            if _init_bb_pos > 0.30:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"INITIAL ENTRY BLOCKED: bb_pos="
                    f"{_init_bb_pos:.2f} > 0.30 — price too "
                    f"high in band for structural entry. "
                    f"Waiting for decline to lower third."
                    f"{_wallet}",
                )
                return

            _detect_pct_frac = self.config.scrum_detect_pct / 100.0
            _fire_pct_frac = self.config.scrum_fire_pct / 100.0
            _bb_mid_init = (_init_bb.upper + _init_bb.lower) / 2.0
            _lower_half = _bb_mid_init - _init_bb.lower
            _dist_down = (_bb_mid_init - _init_price) / max(_lower_half, 1e-12)
            _near_lower = (
                abs(_init_price - _init_bb.lower) / max(_init_bb.lower, 1e-12)
                <= _fire_pct_frac
            )

            if not (
                _near_lower
                or (_bb_mid_init - _init_price)
                >= _detect_pct_frac * max(_lower_half, 1e-12)
            ):
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"INITIAL ENTRY BLOCKED: distance-down "
                    f"{_dist_down:.0%} < {_detect_pct_frac:.0%} "
                    f"and not within {_fire_pct_frac:.2%} of "
                    f"lower band. Price=${_init_price:.8f} "
                    f"(lower=${_init_bb.lower:.8f}, "
                    f"mid=${_bb_mid_init:.8f})"
                    f"{_wallet}",
                )
                return

            if summary.consensus_direction.name != "BEARISH":
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"INITIAL ENTRY BLOCKED: TA="
                    f"{summary.consensus_direction.name} "
                    f"({summary.consensus_confidence:.0%}) — "
                    f"need BEARISH (accumulation-trading "
                    f"thesis: buy decline, not rally). "
                    f"BB OK (pos={_init_bb_pos:.2f}, "
                    f"dist={_dist_down:.0%})."
                    f"{_wallet}",
                )
                return

            buy_cost = self._target_balance
            price = _init_price
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"INITIAL ENTRY: all 4 gates pass — "
                f"BB OK, bb_pos={_init_bb_pos:.2f}, "
                f"dist_down={_dist_down:.0%}, "
                f"TA=BEARISH ({summary.consensus_confidence:.0%}). "
                f"Acquiring ${buy_cost:.2f} of "
                f"{self.config.target_asset} @ ${price:.8f}",
            )
            entry_fill = await self._execute_buy(
                buy_cost,
                price,
                summary,
                trace_context={
                    "path": "zero_balance_initial_entry",
                    "bb_pos": f"{_init_bb_pos:.3f}",
                    "dist_down": f"{_dist_down:.1%}",
                    "gate_current_value": f"${current_value:.6f}",
                    "gate_threshold": f"${self._target_balance * 0.01:.6f}",
                },
            )
            if entry_fill is None or entry_fill <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"INITIAL ENTRY ABORTED: buy failed at "
                        f"${price:.8f}; no main_lots entry added. "
                        f"Bot will retry on next tick if gates "
                        f"still pass."
                    ),
                )
                return
            bought_units = buy_cost / entry_fill
            self._main_lots.append(
                {
                    "units": bought_units,
                    "initial_buy_price": entry_fill,
                }
            )
            _entry_usd = self._current_holdings * entry_fill
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"INITIAL ENTRY COMPLETE: position=${_entry_usd:.2f} "
                    f"vs target=${self._target_balance:.2f}. "
                    f"(forensic: {self._current_holdings:.6f} "
                    f"{self.config.target_asset} filled @ ${entry_fill:.8f}, "
                    f"intended ${price:.8f})"
                ),
            )
            self._bus.emit(
                "trade.filled",
                bot_id=self.bot_id,
                side="buy",
                type="ENTRY",
                price=entry_fill,
                amount=bought_units,
                size=buy_cost,
                profit=0.0,
                operator_initiated=False,
                **self._fill_fee_fields(entry_fill),
            )
            self._emit_voting_panel_snapshot_at_fire(side="BUY", trade_action="ENTRY")
            self._emit_gate_decision_at_fire(side="BUY", trade_action="ENTRY")

    def _tick_target_ramp(
        self,
        bb_result: Any,
        ticker: Any,
        delta: float,
        delta_pct: float,
        _interval_usd: float,
    ) -> bool:
        """Advance the search/track/fire ramp and return whether it fires."""
        detect_pct_frac = self.config.scrum_detect_pct / 100.0
        fire_pct_frac = self.config.scrum_fire_pct / 100.0

        target_fires = True
        if bb_result is not None and bb_result.upper > 0 and bb_result.lower > 0:
            _bb_mid = bb_result.middle
            _bb_upper = bb_result.upper
            _bb_lower = bb_result.lower
            _price = ticker.last
            if _price > _bb_mid:
                _side = "upper"
                _band_range = _bb_upper - _bb_mid
                _band_span = max(_band_range, 1e-12)
                _dist_abs = _price - _bb_mid
                _dist_to_band = _dist_abs / _band_span
                _near_band = abs(_price - _bb_upper) <= fire_pct_frac * _bb_upper
            else:
                _side = "lower"
                _band_range = _bb_mid - _bb_lower
                _band_span = max(_band_range, 1e-12)
                _dist_abs = _bb_mid - _price
                _dist_to_band = _dist_abs / _band_span
                _near_band = abs(_price - _bb_lower) <= fire_pct_frac * _bb_lower

            _prev_side = self._scrum_target_side
            _mode = self._scrum_target_mode

            if _prev_side is not None and _prev_side != _side:
                _mode = "search"

            if _mode == "search":
                if _near_band and abs(delta) >= _interval_usd * 0.5:
                    _mode = "fire"
                    self._scrum_target_side = _side
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: SEARCH→FIRE ({_side}) — fast move to band, "
                        f"Δ {delta_pct:.1f}% ≥ {self.config.scrumming_interval_pct * 0.5:.1f}%",
                    )
                elif (
                    _dist_abs >= detect_pct_frac * _band_span
                    and abs(delta) >= _interval_usd * 0.5
                ):
                    _mode = "track"
                    self._scrum_target_side = _side
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: SEARCH→TRACK ({_side}) — "
                        f"BB dist {_dist_to_band:.0%} ≥ {detect_pct_frac:.0%}",
                    )
            elif _mode == "track":
                if _near_band:
                    _mode = "fire"
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: TRACK→FIRE ({_side}) — "
                        f"within {fire_pct_frac:.2%} of BB band",
                    )
                elif _dist_abs < detect_pct_frac * 0.5 * _band_span:
                    _mode = "search"
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: TRACK→SEARCH — retreated "
                        f"(dist {_dist_to_band:.0%} < {detect_pct_frac * 0.5:.0%})",
                    )
            elif _mode == "fire":
                if not _near_band and _dist_abs >= detect_pct_frac * _band_span:
                    _mode = "track"
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: FIRE→TRACK ({_side}) — off band, "
                        f"still in detect zone (dist {_dist_to_band:.0%})",
                    )
                elif _dist_abs < detect_pct_frac * 0.5 * _band_span:
                    _mode = "search"
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"TARGET: FIRE→SEARCH — retreated "
                        f"(dist {_dist_to_band:.0%} < {detect_pct_frac * 0.5:.0%})",
                    )

            self._scrum_target_mode = _mode
            target_fires = _mode == "fire"
        return target_fires

    def _tick_bullseye_notices(
        self, bb_result: Any, candles: list, ticker: Any
    ) -> None:
        """Emit the band-touch notices for this tick's price."""
        bullseye_upper = False
        bullseye_upper_wick = False
        bullseye_lower = False
        bullseye_lower_wick = False
        if (
            self.config.bb_bullseye_check
            and bb_result is not None
            and bb_result.upper > 0
            and bb_result.lower > 0
        ):
            _bp = ticker.last
            _touch_tol = 0.005
            _wick_tol = 0.002
            bullseye_upper = abs(_bp - bb_result.upper) / bb_result.upper < _touch_tol
            bullseye_lower = abs(_bp - bb_result.lower) / bb_result.lower < _touch_tol
            if candles and not bullseye_upper:
                _last_high = candles[-1].high
                bullseye_upper_wick = _last_high >= bb_result.upper * (1.0 - _wick_tol)
            if candles and not bullseye_lower:
                _last_low = candles[-1].low
                bullseye_lower_wick = _last_low <= bb_result.lower * (1.0 + _wick_tol)

        if bullseye_upper or bullseye_upper_wick:
            _ramp = self._scrum_target_mode.upper()
            _fire_gate = "passes" if _ramp == "FIRE" else "holds"
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"BULLSEYE UPPER ({'wick' if bullseye_upper_wick else 'close'}): "
                f"price ${ticker.last:.8f} at BB upper ${bb_result.upper:.8f}. "
                f"Ramp at {_ramp}, so the FIRE gate {_fire_gate}.",
            )
        if bullseye_lower or bullseye_lower_wick:
            _queued = len(self._fold_tranches or [])
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"BULLSEYE LOWER ({'wick' if bullseye_lower_wick else 'close'}): "
                f"price ${ticker.last:.8f} at BB lower ${bb_result.lower:.8f}. "
                f"{_queued} tranche(s) queued; a fold needs one whose "
                f"reference price the market has fallen past.",
            )

    async def _tick_execute_scrum(
        self,
        ticker: Any,
        summary: Any,
        bb_result: Any,
        delta: float,
        delta_pct: float,
        current_value: float,
        bb_pos: float,
        eff_direction: Any,
        eff_confidence: float,
        _eff_conf_floor: float,
        position_boost: float,
        _scrum_chain_result: Any,
    ) -> None:
        """Sell the authorised Target Delta and queue the proceeds as tranches."""
        scrum_asset = abs(delta) / ticker.last
        try:
            self._emit_trade_fire_snapshot(
                "scrum",
                summary,
                float(ticker.last),
                decision_extra={
                    "delta": round(float(delta), 6),
                    "scrum_asset": round(float(scrum_asset), 8),
                    "overrides_applied": list(
                        getattr(_scrum_chain_result, "overrides_applied", []) or []
                    ),
                },
            )
        except Exception as _sup:
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)

        _scrum_skipped_below_min = False
        try:
            _qrate_for_cost = float(self._quote_to_usd or 1.0)
            _scrum_notional_usd = scrum_asset * float(ticker.last) * _qrate_for_cost
            _min_amt_sc, _min_cost_sc, _ = await self._get_market_limits(
                self.config.symbol
            )
            _below_min_cost_sc = _min_cost_sc > 0 and _scrum_notional_usd < _min_cost_sc
            _below_min_amt_sc = (
                _min_amt_sc > 0
                and _scrum_notional_usd < _min_amt_sc * float(ticker.last)
            )
            if _below_min_cost_sc or _below_min_amt_sc:
                _scrum_skipped_below_min = True
                import time as _t_sc

                _now_ts = _t_sc.time()
                if (_now_ts - self._below_min_scrum_log_ts) >= 300.0:
                    self._below_min_scrum_log_ts = _now_ts
                    _reason_parts = []
                    if _below_min_cost_sc:
                        _reason_parts.append(
                            f"notional ${_scrum_notional_usd:.4f} < "
                            f"min_cost ${_min_cost_sc:.2f}"
                        )
                    if _below_min_amt_sc:
                        _reason_parts.append(
                            f"amount {scrum_asset:.8f} < "
                            f"min_amount {_min_amt_sc:.8f}"
                        )
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"SCRUM HELD (below min trade size): "
                            f"Target Delta ${abs(delta):.4f} = "
                            f"{scrum_asset:.8f} units × "
                            f"${float(ticker.last):.8f}. "
                            f"{self.config.symbol} blockers: "
                            f"{'; '.join(_reason_parts)}. "
                            f"Bot intentionally idle until "
                            f"conditions allow a tradeable "
                            f"size. (Throttled: next emit "
                            f"~5 min.)"
                        ),
                    )
        except Exception as _mc_exc:
            logger.debug(
                "Bot %s SCRUM min_cost pre-check raised: %s "
                "(falling through to normal _execute_sell)",
                self.bot_id,
                _mc_exc,
            )

        if _scrum_skipped_below_min:
            sell_fill = None
        else:
            sell_fill = await self._execute_sell(scrum_asset, ticker.last, summary)
        if sell_fill is None or sell_fill <= 0:
            if not _scrum_skipped_below_min:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SCRUM ABORTED: sell failed for "
                        f"{scrum_asset:.6f} units @ ${ticker.last:.8f}. "
                        f"No tranches queued; main_lots unchanged; "
                        f"no fold profit claimed. Retry next tick."
                    ),
                )
        else:
            # _settled_sale_proceeds nets the venue's reported fee out
            # of the gross scrum_asset * sell_fill.
            scrum_usd = self._settled_sale_proceeds(
                scrum_asset, sell_fill, label="SCRUM"
            )

            if self._fold_cycle_cap_consumed > 1e-9:
                _prev_cap_consumed = self._fold_cycle_cap_consumed
                self._fold_cycle_cap_consumed = 0.0
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD CYCLE RESET (SCRUM fired): "
                        f"Target Delta swung positive, sell "
                        f"event ends fold cycle. Growth Rate "
                        f"Cap consumed ${_prev_cap_consumed:.4f} "
                        f"this cycle — reset to $0.00. Next "
                        f"fold burst gets fresh cap budget."
                    ),
                )

            _scrum_routed_total = self._route_scrum_proceeds_via_wires(
                scrum_usd=scrum_usd, sell_fill=sell_fill, label="scrum"
            )

            scrum_usd = scrum_usd - _scrum_routed_total

            self._main_lots.sort(key=lambda l: l["initial_buy_price"], reverse=True)
            _tranche_count_before = len(self._fold_tranches)
            _units_remaining = scrum_asset
            _first_new_tranche = None
            for _lot in list(self._main_lots):
                if _units_remaining <= 1e-12:
                    break
                _take = min(_lot["units"], _units_remaining)
                if _take <= 1e-12:
                    continue
                _t_usd = (_take / scrum_asset) * scrum_usd
                _new_tr = {
                    "usd": _t_usd,
                    "units": _take,
                    "ref": sell_fill,
                    "initial_buy_price": _lot["initial_buy_price"],
                    "created_ts": time.time(),
                }
                self._fold_tranches.append(_new_tr)
                self._tranches_created_lifetime += 1
                if _first_new_tranche is None:
                    _first_new_tranche = _new_tr
                _lot["units"] -= _take
                _units_remaining -= _take
                if _lot["units"] <= 1e-12:
                    self._main_lots.remove(_lot)

            # _bound_new_fold_tranches merges and replaces the tranche
            # object, so _first_new_tranche is re-read from the list.
            if self._bound_new_fold_tranches(_tranche_count_before):
                _first_new_tranche = self._fold_tranches[_tranche_count_before]

            if (
                _first_new_tranche is not None
                and _tranche_count_before == 0
                and self._pending_wire_credits > 0
            ):
                self._absorb_pending_wire_credits_into(_first_new_tranche)

            self._apply_scrum_fold_pct(_tranche_count_before, scrum_usd, scrum_asset)

            self._top_up_remnant_fold_tranches(
                _tranche_count_before,
                float(getattr(bb_result, "lower", 0.0) or 0.0),
                float(getattr(bb_result, "upper", 0.0) or 0.0),
            )

            # Ordered after the top-up because wire USD carries no units.
            self._land_pending_wire_credits()

            self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
            self._fold_queue_ref_price = sell_fill
            self.stats.trade_volume += scrum_usd

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"SCRUM: Target=${self._target_balance:.2f}, "
                f"Value=${current_value:.2f} (+{delta_pct:.1f}%), "
                f"sold {scrum_asset:.6f} (${scrum_usd:.4f}) on "
                f"{eff_direction.name} (conf={eff_confidence:.2f}"
                f"≥floor {_eff_conf_floor:.2f}, "
                f"pos_skew={position_boost:+.2f}, bb={bb_pos:.0%}). "
                f"Fill=${sell_fill:.8f}, queued ${scrum_usd:.4f} for fold.",
            )
            self._bus.emit(
                "trade.filled",
                bot_id=self.bot_id,
                side="sell",
                type="SCRUM",
                price=sell_fill,
                amount=scrum_asset,
                size=scrum_usd,
                profit=0,
                **self._fill_fee_fields(sell_fill),
            )
            self._emit_voting_panel_snapshot_at_fire(side="SELL", trade_action="SCRUM")
            self._emit_gate_decision_at_fire(side="SELL", trade_action="SCRUM")
            try:
                _avg_entry_for_pnl = 0.0
                if self._main_lots:
                    _tu = sum(float(l.get("units", 0) or 0) for l in self._main_lots)
                    if _tu > 0:
                        _avg_entry_for_pnl = (
                            sum(
                                float(l.get("units", 0) or 0)
                                * float(l.get("initial_buy_price", 0) or 0)
                                for l in self._main_lots
                            )
                            / _tu
                        )
                _pct_vs_entry = 0.0
                if _avg_entry_for_pnl > 0:
                    _pct_vs_entry = (
                        (sell_fill - _avg_entry_for_pnl) / _avg_entry_for_pnl * 100.0
                    )
                self._bus.emit(
                    "pnl.event",
                    bot_id=self.bot_id,
                    data={
                        "kind": "SCRUM",
                        "asset": self.config.target_asset,
                        "symbol": self.config.symbol,
                        "units": float(scrum_asset),
                        "fill_price": float(sell_fill),
                        "usd_captured": float(scrum_usd)
                        * float(self._quote_to_usd or 1.0),
                        "avg_entry": float(_avg_entry_for_pnl),
                        "pct_vs_avg_entry": float(_pct_vs_entry),
                    },
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
            _scrum_usd_true = float(scrum_usd) * float(self._quote_to_usd or 1.0)
            self.stats.total_scrummed_usd += _scrum_usd_true
            self.note_scrum_retention_usd(_scrum_usd_true)
            self._last_trade_side = "SCRUM"
            self._reset_opposing_hysteresis_after_fill()

            self._scrum_target_mode = "search"
            self._scrum_target_side = None
            self._last_trade_price = sell_fill

    def _tick_fold_diagnostics(
        self,
        ticker: Any,
        bb_pos: float,
        is_bearish: bool,
        fold_ok_midline: bool,
        _bb_below_lower_dt: bool,
        _fold_blockers: list,
        _otd_pct_for_gate: float,
        _otd_factor: float,
    ) -> None:
        """Emit the fold-queue diagnostics for this tick's gate outcome."""
        try:
            self._fold_diag_tick += 1
            if self._fold_tranches:
                _per_tranche_eligible = len(
                    self._fold_eligible_tranches(ticker.last, _otd_factor)
                )
                _patent_only_eligible = sum(
                    1
                    for _t in self._fold_tranches
                    if ticker.last
                    <= float(_t.get("initial_buy_price", _t.get("ref", 0)))
                )
                _gate_armed_now = len(_fold_blockers) == 0

                if _per_tranche_eligible > 0 and not _gate_armed_now:
                    # The blocker names, not their rendered numbers: a
                    # confidence moving one decimal is not a new blocker.
                    _blocker_key = "|".join(
                        sorted(one.split("(")[0] for one in _fold_blockers)
                    )
                    if _blocker_key != self._fold_diag_last_blocker_set:
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"FOLD DIAG blocked: "
                                f"{_per_tranche_eligible} of "
                                f"{len(self._fold_tranches)} tranche(s) "
                                f"eligible at ${ticker.last:.8f}, and the "
                                f"fold gate refused. "
                                f"Blocked by {', '.join(_fold_blockers)}. "
                                f"BB position {bb_pos:.1%}, TA bearish "
                                f"{_yes_no(is_bearish)}, midline gate "
                                f"{_yes_no(fold_ok_midline)}, below the "
                                f"lower detect line "
                                f"{_yes_no(_bb_below_lower_dt)}. "
                                f"Cycle cap used "
                                f"${self._fold_cycle_cap_consumed:.4f}. "
                                f"Target ${self._target_balance:.4f} from "
                                f"anchor ${self._anchor_target_balance:.4f}, "
                                f"last grown on the "
                                f"{self._target_grow_last_side} side. "
                                f"Profit folding "
                                f"{_yes_no(self.config.profit_folding_active)}."
                            ),
                        )
                        self._fold_diag_last_blocker_set = _blocker_key

                if self._fold_diag_tick % 100 == 0:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD DIAG state (tick "
                            f"{self._fold_diag_tick}): "
                            f"{len(self._fold_tranches)} tranche(s) queued, "
                            f"{_per_tranche_eligible} eligible, "
                            f"{_patent_only_eligible} eligible on the "
                            f"patent gate alone. "
                            f"Price ${ticker.last:.8f}, BB position "
                            f"{bb_pos:.1%}, TA bearish "
                            f"{_yes_no(is_bearish)}. "
                            f"Cycle cap used "
                            f"${self._fold_cycle_cap_consumed:.4f}. "
                            f"Target ${self._target_balance:.4f} from "
                            f"anchor ${self._anchor_target_balance:.4f}, "
                            f"last grown on the "
                            f"{self._target_grow_last_side} side. "
                            f"{self._tranches_created_lifetime} created and "
                            f"{self._tranches_closed_lifetime} closed for "
                            f"the life of this bot."
                        ),
                    )

                if _per_tranche_eligible == 0 and self._fold_diag_tick % 500 == 0:
                    _min_ref = min(
                        float(_t.get("ref", 0)) for _t in self._fold_tranches
                    )
                    _otd_diag = _otd_pct_for_gate
                    _activation = _min_ref * _otd_factor
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD DIAG waiting: "
                            f"{len(self._fold_tranches)} tranche(s) queued "
                            f"and none eligible at "
                            f"${ticker.last:.8f}. "
                            f"Lowest tranche reference ${_min_ref:.8f}. "
                            f"The {_otd_diag:.2f}% opposing-trade-distance "
                            f"gate opens the fold at or below "
                            f"${_activation:.8f}, a further "
                            f"{max(0.0, (ticker.last / _activation - 1.0) * 100.0):.2f}% "
                            f"fall."
                            if _activation > 0
                            else f"FOLD DIAG waiting: "
                            f"{len(self._fold_tranches)} tranche(s) queued "
                            f"and none eligible at ${ticker.last:.8f}. "
                            f"Lowest tranche reference ${_min_ref:.8f}."
                        ),
                    )
        except Exception as _diag_exc:
            logger.debug("FOLD DIAG emission failed: %s", _diag_exc)

    async def _tick_execute_fold(
        self,
        ticker: Any,
        summary: Any,
        delta: float,
        _otd_factor: float,
        _fold_chain_result: Any,
    ) -> bool:
        """Rebuy the eligible tranches; True means the tick must stop."""
        try:
            self._emit_trade_fire_snapshot(
                "fold",
                summary,
                float(ticker.last),
                decision_extra={
                    "delta": round(float(delta), 6),
                    "n_fold_tranches": len(self._fold_tranches or []),
                    "overrides_applied": list(
                        getattr(_fold_chain_result, "overrides_applied", []) or []
                    ),
                },
            )
        except Exception as _sup:
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
        self._drop_malformed_fold_tranches()
        _eligible = self._fold_eligible_tranches(ticker.last, _otd_factor)
        try:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD DIAG passed: the fold gate cleared at "
                    f"${ticker.last:.8f}. "
                    f"{len(_eligible)} of {len(self._fold_tranches)} "
                    f"tranche(s) eligible. "
                    f"Cycle cap used "
                    f"${self._fold_cycle_cap_consumed:.4f}. "
                    f"Profit folding "
                    f"{_yes_no(self.config.profit_folding_active)}."
                ),
            )
        except Exception as _sup:
            logger.debug("suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup)
        _excluded = 0
        _partial_count = 0
        _taper = 0.0
        _fold_plan: list[tuple[dict, float, float]] = []
        if _eligible:
            # cycle_growth_cap_usd is the bound _plan_fold_consumption
            # applies; _max_growth_pct only feeds the emit below.
            _max_growth_pct = float(getattr(self.config, "max_target_growth_pct", 1.0))
            _cycle_cap_usd = self.cycle_growth_cap_usd
            # _cycle_open_target only feeds the emit below.
            _cycle_open_target = max(
                0.0,
                float(self._target_balance) - float(self._fold_cycle_cap_consumed),
            )
            _cap_remaining_for_queue = max(
                0.0, _cycle_cap_usd - self._fold_cycle_cap_consumed
            )
            _elig_sorted = sorted(
                _eligible,
                key=lambda _t: -float(_t.get("initial_buy_price", _t.get("ref", 0))),
            )
            _fold_plan, _elig_capped, _partial_count = self._plan_fold_consumption(
                _elig_sorted, _cap_remaining_for_queue
            )
            _running_usd = sum(_take for _, _take, _ in _fold_plan)
            _excluded = len(_eligible) - len(_elig_capped)
            if _excluded > 0 or _partial_count > 0:
                _excluded_usd = (
                    sum(float(t.get("usd", 0) or 0) for t in _eligible) - _running_usd
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD CYCLE-CAP: deploying "
                        f"${_running_usd:.2f} of "
                        f"${(sum(float(t.get('usd',0) or 0) for t in _eligible)):.2f} "
                        f"eligible, bounded by the per-cycle growth "
                        f"cap ${_cycle_cap_usd:.2f} "
                        f"(${_cap_remaining_for_queue:.2f} remaining "
                        f"after ${self._fold_cycle_cap_consumed:.2f} "
                        f"consumed this cycle, "
                        f"{_max_growth_pct}% of cycle-open target "
                        f"${_cycle_open_target:.2f}, "
                        f"anchor ${self._anchor_target_balance:.2f}). "
                        f"{_partial_count} tranche(s) part-consumed "
                        f"— each keeps its remaining balance and "
                        f"stays queued. {_excluded} of "
                        f"{len(_eligible)} left untouched. "
                        f"${_excluded_usd:.2f} stays queued in "
                        f"total for the next TA-validated fold "
                        f"opportunity."
                    ),
                )
            _eligible = _elig_capped
        if _eligible:
            _taper = self.fold_rate_taper
            if _taper <= 0.0:
                _ratio = self.ceiling_ratio or 0.0
                _ceiling_pos_usd = (
                    self._current_holdings
                    * ticker.last
                    * float(self._quote_to_usd or 1.0)
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD BLOCKED by position ceiling: "
                        f"current ${_ceiling_pos_usd:.2f} "
                        f">= ceiling ${self.position_ceiling_usd:.2f} "
                        f"({_ratio*100:.1f}% of ceiling). "
                        f"Scrum still allowed."
                    ),
                )
                _eligible = []

        if _eligible:
            _fusd = sum(t["usd"] for t in _eligible)
            sum(t["units"] for t in _eligible)
            buy_cost = _fusd * _taper
            if _taper < 1.0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD TAPER: ratio "
                        f"{(self.ceiling_ratio or 0)*100:.1f}% of "
                        f"ceiling → fold sized at {_taper*100:.0f}% "
                        f"of eligible (${_fusd:.4f} → "
                        f"${buy_cost:.4f})."
                    ),
                )

            _fold_skipped_below_min = False
            try:
                _qrate_fc = float(self._quote_to_usd or 1.0)
                _fold_notional_usd = buy_cost * _qrate_fc
                _min_amt_fc, _min_cost_fc, _ = await self._get_market_limits(
                    self.config.symbol
                )
                buy_cost / float(ticker.last) if ticker.last > 0 else 0.0
                _below_min_cost_fc = (
                    _min_cost_fc > 0 and _fold_notional_usd < _min_cost_fc
                )
                _below_min_amt_fc = _min_amt_fc > 0 and buy_cost < _min_amt_fc * float(
                    ticker.last
                )
                if _below_min_cost_fc or _below_min_amt_fc:
                    _fold_skipped_below_min = True
                    import time as _t_fc

                    _now_ts_fc = _t_fc.time()
                    if (_now_ts_fc - self._below_min_fold_log_ts) >= 300.0:
                        self._below_min_fold_log_ts = _now_ts_fc
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"FOLD HELD (below min trade size): "
                                f"{len(_eligible)} eligible tranche(s) "
                                f"totaling ${_fusd:.4f} (tapered to "
                                f"${buy_cost:.4f}) is below "
                                f"{self.config.symbol} min_cost "
                                f"${_min_cost_fc:.2f}. Bot intentionally "
                                f"holding; tranches stay queued until "
                                f"more accumulate or price moves "
                                f"enough. (Throttled: next emit ~5 min.)"
                            ),
                        )
            except Exception as _mc_fold_exc:
                logger.debug(
                    "Bot %s FOLD min_cost pre-check raised: %s "
                    "(falling through to normal _execute_buy)",
                    self.bot_id,
                    _mc_fold_exc,
                )

            buy_asset = buy_cost / ticker.last
            asset_at_scrum = sum(t["usd"] / t["ref"] for t in _eligible)
            extra_asset = buy_asset - asset_at_scrum
            min_ref = min(t["ref"] for t in _eligible)
            pct_cheaper = (1 - ticker.last / min_ref) * 100
            accum_profit = extra_asset * ticker.last

            _intended_min_ref = min(t["ref"] for t in _eligible)

            if _fold_skipped_below_min:
                buy_fill = None
            else:
                buy_fill = await self._execute_buy(
                    buy_cost,
                    ticker.last,
                    summary,
                    trace_context={
                        "path": "fold_rebuy",
                        "eligible_tranches": len(_eligible),
                        "min_ref": f"${min_ref:.8f}",
                        "pct_cheaper": f"{pct_cheaper:.2f}%",
                    },
                )
            if buy_fill is None or buy_fill <= 0:
                if not _fold_skipped_below_min:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD ABORTED: rebuy failed at "
                            f"${ticker.last:.8f} for "
                            f"{len(_eligible)} eligible tranches. "
                            f"Tranches stay queued; no profit booked; "
                            f"no hedge replenish. Will retry next "
                            f"tick."
                        ),
                    )
                return True

            buy_asset = buy_cost / buy_fill
            asset_at_scrum = sum(t["usd"] / t["ref"] for t in _eligible)
            extra_asset = buy_asset - asset_at_scrum
            pct_cheaper = (1 - buy_fill / _intended_min_ref) * 100
            accum_profit = extra_asset * buy_fill

            _total_elig_units = sum(t["units"] for t in _eligible) + 1e-12
            for _t in _eligible:
                _share = _t["units"] / _total_elig_units
                self._main_lots.append(
                    {
                        "units": buy_asset * _share,
                        "initial_buy_price": _t["initial_buy_price"],
                    }
                )

            _pre_remove = len(self._fold_tranches)
            _removed, _n_spent = self._settle_fold_plan(_fold_plan)
            if _removed > 0:
                self._tranches_closed_lifetime += _removed
            if _removed != _n_spent:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD DEQUEUE MISMATCH: {_n_spent} "
                        f"tranche(s) were drained to nothing but "
                        f"{_removed} left the queue. Likely "
                        f"concurrent mutation — investigate."
                    ),
                )
            self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
            if not self._fold_tranches:
                self._fold_queue_ref_price = 0.0

            self.stats.trade_volume += buy_cost

            _new_surplus_usd = max(0.0, accum_profit * float(self._quote_to_usd or 1.0))

            # These three feed only the FOLD DIAG surplus emit;
            # _apply_fold_target_growth reads the cap itself.
            _cap_pct_growth = float(getattr(self.config, "max_target_growth_pct", 1.0))
            _cycle_cap_growth = self.cycle_growth_cap_usd
            _cycle_open_target_d = max(
                0.0,
                float(self._target_balance) - float(self._fold_cycle_cap_consumed),
            )

            try:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD DIAG surplus: bought at "
                        f"${buy_fill:.8f}, holdings "
                        f"{self._current_holdings:.6f}. "
                        f"Accumulated profit "
                        f"${float(accum_profit):.6f} against target "
                        f"${self._target_balance:.4f} gives new surplus "
                        f"${_new_surplus_usd:+.4f} on standing surplus "
                        f"${self._standing_surplus_usd:.4f}. "
                        f"Cycle budget ${_cycle_cap_growth:.4f}, "
                        f"{_cap_pct_growth}% of the cycle-open target "
                        f"${_cycle_open_target_d:.4f} at anchor "
                        f"${self._anchor_target_balance:.4f}. "
                        f"Profit folding "
                        f"{_yes_no(self.config.profit_folding_active)}."
                    ),
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )

            _growth_applied = self._apply_fold_target_growth(
                accum_profit, source="auto"
            )

            try:
                mgr = self._smart_wire_mgr
                if (
                    mgr is not None
                    and _growth_applied > 0
                    and hasattr(mgr, "distribute_fold_profit")
                ):
                    try:
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=(
                                f"[WIRE FIRE] fold-compound: "
                                f"${_growth_applied:.4f} → "
                                f"distribute_fold_profit "
                                f"(from realized compound growth "
                                f"@{buy_fill:.8f})"
                            ),
                        )
                    except Exception as _sup:  # noqa: BLE001
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "tick",
                            type(_sup).__name__,
                            _sup,
                        )
                    mgr.distribute_fold_profit(
                        source_id=self.bot_id,
                        profit_usd=float(_growth_applied),
                        ref=f"fold-compound@{buy_fill:.8f}",
                    )
            except Exception as _wr_exc:
                logger.warning(
                    "Bot %s Smart Wire compound-route raised: %s "
                    "(fold profit still booked locally)",
                    self.bot_id,
                    _wr_exc,
                )

            if (
                self.config.hedge_rebalance_active
                and self._hedge_balance_initial > 0
                and self._hedge_bal < self._hedge_balance_initial
                and _growth_applied > 0
            ):
                _prev = self._hedge_bal
                self._hedge_bal = min(
                    self._hedge_balance_initial,
                    self._hedge_bal + _growth_applied * 0.08,
                )
                _added = self._hedge_bal - _prev
                if _added > 1e-9:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"HEDGE REPLENISH: +${_added:.4f} from compound growth "
                        f"→ reserve now ${self._hedge_bal:.2f} "
                        f"(cap ${self._hedge_balance_initial:.2f})",
                    )

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"FOLD: Bought ${buy_cost:.4f} @ ${buy_fill:.8f} "
                f"(intended ${ticker.last:.8f}, "
                f"{pct_cheaper:.1f}% below min tranche ref ${_intended_min_ref:.8f}). "
                f"Accumulated +{extra_asset:.6f} extra asset. "
                f"Profit: ${accum_profit:.4f}. "
                f"Rebought {_n_spent} tranche(s) whole and "
                f"part-consumed {_partial_count}, out of "
                f"{_pre_remove} queued "
                f"(others held by the OTD price gate: needs "
                f"price <= ref x {_otd_factor:.4f}"
                + (
                    f"; {_excluded} more were price-eligible "
                    f"but skipped by the per-cycle cap"
                    if _excluded
                    else ""
                )
                + ")",
            )
            self._bus.emit(
                "trade.filled",
                bot_id=self.bot_id,
                side="buy",
                type="FOLD",
                price=buy_fill,
                amount=(buy_cost / buy_fill) if buy_fill else 0.0,
                size=buy_cost,
                profit=_growth_applied,
                **self._fill_fee_fields(buy_fill),
            )
            self._emit_voting_panel_snapshot_at_fire(side="BUY", trade_action="FOLD")
            self._emit_gate_decision_at_fire(side="BUY", trade_action="FOLD")
            try:
                _pct_token_gain = 0.0
                if asset_at_scrum > 1e-12:
                    _pct_token_gain = extra_asset / asset_at_scrum * 100.0
                self._bus.emit(
                    "pnl.event",
                    bot_id=self.bot_id,
                    data={
                        "kind": "FOLD",
                        "asset": self.config.target_asset,
                        "symbol": self.config.symbol,
                        "units_rebought": float(buy_asset),
                        "units_at_scrum_refs": float(asset_at_scrum),
                        "extra_asset": float(extra_asset),
                        "pct_token_gain": float(_pct_token_gain),
                        "fill_price": float(buy_fill),
                        "min_ref": float(min_ref),
                        "pct_cheaper_vs_ref": float(pct_cheaper),
                        "usd_spent": float(buy_cost) * float(self._quote_to_usd or 1.0),
                        "growth_applied_usd": float(_growth_applied),
                    },
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
            self.stats.total_folded_usd += float(buy_cost) * float(
                self._quote_to_usd or 1.0
            )
            self.reset_swos_cycle()
            self._last_trade_side = "FOLD"
            self._last_trade_price = buy_fill
            self._reset_opposing_hysteresis_after_fill()

            if extra_asset > 0:
                self._dist_accumulator += extra_asset

        else:
            _min_ref = min(t["ref"] for t in self._fold_tranches)
            _min_ibp = min(
                t.get("initial_buy_price", t["ref"]) for t in self._fold_tranches
            )
            _binding = (
                "the price it was first bought at"
                if ticker.last > _min_ibp
                else "the price its scrum sold at"
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"HOLD FOLD: TA is bearish and all "
                f"{len(self._fold_tranches)} tranche(s) are gated. "
                f"Price ${ticker.last:.8f} is above {_binding}. "
                f"Lowest sell reference ${_min_ref:.8f}, lowest buy "
                f"price ${_min_ibp:.8f}.",
            )
        return False

    async def _tick_distribute(
        self, ticker: Any, summary: Any, bb_result: Any, is_bullish: bool
    ) -> None:
        """Sell the accumulated excess and re-queue the proceeds for fold."""
        if self._dist_accumulator > 0 and is_bullish:
            dist_asset = self._dist_accumulator
            try:
                bal = await self._get_balance(self.config.symbol.split("/")[0])
                dist_asset = min(dist_asset, bal)
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s", "tick", type(_sup).__name__, _sup
                )
            if dist_asset > 0:
                dist_fill = await self._execute_sell(dist_asset, ticker.last, summary)
                if dist_fill is None or dist_fill <= 0:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"DIST ABORTED: sell failed for "
                            f"{dist_asset:.6f} excess @ ${ticker.last:.8f}. "
                            f"Accumulator kept; no re-fold tranches "
                            f"created. Retry next tick."
                        ),
                    )
                else:
                    # _settled_sale_proceeds nets the venue's reported
                    # fee out of dist_asset * dist_fill.
                    dist_usd = self._settled_sale_proceeds(
                        dist_asset, dist_fill, label="DIST"
                    )
                    self.stats.trade_volume += dist_usd

                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"DIST: Sold {dist_asset:.6f} excess @ ${dist_fill:.8f} "
                        f"(intended ${ticker.last:.8f}) = ${dist_usd:.4f}",
                    )
                    self._bus.emit(
                        "trade.filled",
                        bot_id=self.bot_id,
                        side="sell",
                        type="DIST",
                        price=dist_fill,
                        amount=dist_asset,
                        size=dist_usd,
                        profit=dist_usd * 0.02,
                        **self._fill_fee_fields(dist_fill),
                    )
                    self._emit_voting_panel_snapshot_at_fire(
                        side="SELL", trade_action="DIST"
                    )
                    self._emit_gate_decision_at_fire(side="SELL", trade_action="DIST")
                    self._last_trade_price = dist_fill

                    self._dist_accumulator = 0.0

                    if self.config.profit_folding_active:
                        self._main_lots.sort(
                            key=lambda l: l["initial_buy_price"], reverse=True
                        )
                        _dist_tranche_count_before = len(self._fold_tranches)
                        _units_remaining = dist_asset
                        for _lot in list(self._main_lots):
                            if _units_remaining <= 1e-12:
                                break
                            _take = min(_lot["units"], _units_remaining)
                            if _take <= 1e-12:
                                continue
                            _t_usd = (_take / dist_asset) * dist_usd
                            self._fold_tranches.append(
                                {
                                    "usd": _t_usd,
                                    "units": _take,
                                    "ref": dist_fill,
                                    "initial_buy_price": _lot["initial_buy_price"],
                                    "created_ts": time.time(),
                                }
                            )
                            self._tranches_created_lifetime += 1
                            _lot["units"] -= _take
                            _units_remaining -= _take
                            if _lot["units"] <= 1e-12:
                                self._main_lots.remove(_lot)
                        self._bound_new_fold_tranches(_dist_tranche_count_before)
                        # scrum_fold_pct governs DIST proceeds as it governs a SCRUM.
                        self._apply_scrum_fold_pct(
                            _dist_tranche_count_before, dist_usd, dist_asset
                        )
                        self._top_up_remnant_fold_tranches(
                            _dist_tranche_count_before,
                            float(getattr(bb_result, "lower", 0.0) or 0.0),
                            float(getattr(bb_result, "upper", 0.0) or 0.0),
                        )
                        # Ordered after the top-up because wire USD carries no units.
                        self._land_pending_wire_credits()
                        self._fold_queue_usd = sum(
                            t["usd"] for t in self._fold_tranches
                        )
                        self._fold_queue_ref_price = dist_fill
                        self._bus.emit(
                            "bot.log",
                            bot_id=self.bot_id,
                            message=f"DIST proceeds ${dist_usd:.4f} queued for re-fold "
                            f"(tranche-provenance preserved, fill=${dist_fill:.8f})",
                        )
