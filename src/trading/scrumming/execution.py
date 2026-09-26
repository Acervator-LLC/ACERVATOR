"""Order execution for ScrummingBot: places venue orders and settles fills.

Holds the sell, buy, detonation and manual-rebalance paths, plus the
venue-fee records a settled fill produces on either side.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from ...exchange.base import OrderSide, OrderType
from ..target_bands import manual_fire_dust_band
from ..ta_engine import VotingSummary
from ..wallet_reservations import get_wallet_reservations, wallet_key
from .sizing import (
    FRACTIONAL_UNITS,
    fold_units,
    priced_usd,
    sale_proceeds_usd,
    scrum_units,
    spend_less_unsettled_usd,
    target_delta_usd,
    unsettled_usd,
    wallet_capped_spend_usd,
)

logger = logging.getLogger("acervator.scrumming")


@dataclass
class MemorisedTrade:
    """A scrumming event stored for potential conversion to a grid level."""

    timestamp: float
    side: str
    price: float
    amount: float
    voting_summary: Optional[VotingSummary] = None


@dataclass(frozen=True)
class SettledFillFee:
    """The fee the venue reported for one settled fill, on either side.

    ``units`` and ``price`` identify the fill, ``reported`` is False when the
    venue gave no fee, and ``fee_amount`` is never derived from
    ``config.trading_fee_pct``.
    """

    units: float
    price: float
    fee_amount: float
    currency: str
    reported: bool


class ExecutionEngineMixin:
    """Place orders at the venue and book what the venue reports back.

    ``_execute_sell``, ``_execute_buy``, ``_execute_detonation`` and
    ``_execute_manual_rebalance`` each run after a tick has chosen the trade.
    """

    # ScrummingBot supplies these at runtime; the annotations create no attributes.
    _anchor_target_balance: float
    _apply_fold_target_growth: Callable[..., Any]
    _apply_scrum_fold_pct: Callable[..., None]
    _bound_new_fold_tranches: Callable[..., Any]
    _bus: Any
    _crr: Callable[..., Any]
    _current_holdings: float
    _emit_gate_decision_at_fire: Callable[..., None]
    _emit_trade_notification: Callable[..., None]
    _emit_voting_panel_snapshot_at_fire: Callable[..., None]
    _fold_discharge_order: Callable[..., list[dict]]
    _fold_preview_unreadable_refs: int
    _fold_preview_unreadable_units: int
    _fold_queue_usd: float
    _fold_tranches: list[dict]
    _get_balance: Callable[..., Any]
    _hyst_armed_fold_side: bool
    _hyst_armed_scrum_side: bool
    _hyst_ref_fold_side: float
    _hyst_ref_scrum_side: float
    _initialised: Any
    _invisible: bool
    _land_pending_wire_credits: Callable[..., float]
    _last_trade_price: float
    _last_trade_side: Optional[str]
    _main_lots: list[dict]
    _manual_fire_pending: bool
    _memorised_trades: list[MemorisedTrade]
    _open_stack_from_scrum: Callable[..., Any]
    _preview_fold_growth: Callable[..., Any]
    _quote_to_usd: float
    _reconcile_holdings: Callable[..., Any]
    _refresh_quote_to_usd: Callable[..., Any]
    _reset_opposing_hysteresis_after_fill: Callable[..., None]
    _route_scrum_proceeds_via_wires: Callable[..., Any]
    _spawn_stack_from_fold: Callable[..., Any]
    _standing_surplus_usd: float
    _target_balance: Any
    _top_up_remnant_fold_tranches: Callable[..., Any]
    _tranches_closed_lifetime: int
    _tranches_created_lifetime: int
    _tranches_discarded_lifetime: Any
    bot_id: Any
    config: Any
    exchange: Any
    guarded_place_order: Callable[..., Any]
    note_scrum_retention_usd: Callable[..., None]
    reset_swos_cycle: Callable[..., None]
    stats: Any

    # Class-level defaults; every write lands on the instance, never on the class.
    _last_sell_venue_fee: Optional["SettledFillFee"] = None
    _last_fill_venue_fee: Optional["SettledFillFee"] = None

    # One get_order per fill whose placed order reported no fee, and none otherwise.
    _VENUE_FEE_REREADS = 1
    _VENUE_FEE_REREAD_DELAY_S = 0.2

    _SETTLED_FILL_DEFAULT_LABEL = "MANUAL FIRE"
    _SETTLED_FILL_LABELS = frozenset(
        (
            "MANUAL FIRE",
            "SCRUM",
            "DIST",
            "STACK",
        )
    )

    @classmethod
    def _settled_fill_label(cls, label: object) -> str:
        """Resolve ``label`` against ``_SETTLED_FILL_LABELS``, never raising.

        ``None`` and ``""`` return ``_SETTLED_FILL_DEFAULT_LABEL`` silently, and
        any other unrecognised value returns it after a warning.
        """
        if isinstance(label, str) and label in cls._SETTLED_FILL_LABELS:
            return label
        if label is not None and label != "":
            logger.warning(
                "settled-fill label %r is not one of %s; the operator "
                "log will read %s",
                label,
                sorted(cls._SETTLED_FILL_LABELS),
                cls._SETTLED_FILL_DEFAULT_LABEL,
            )
        return cls._SETTLED_FILL_DEFAULT_LABEL

    async def _settled_fill(
        self,
        order,
        symbol: str,
        requested_amount: float,
        quoted_price: float,
        label: str | None = None,
    ):
        """Re-read a just-placed ``order`` until the venue reports a fill.

        Returns ``(fill_amount, fill_price, is_real)``, calls
        ``_record_venue_fee`` on whichever order object settled, and clears both
        venue-fee records when it books an estimate.
        """
        self._last_sell_venue_fee = None
        self._last_fill_venue_fee = None

        def _extract(o):
            if o is None:
                return 0.0, 0.0
            try:
                amt = float(getattr(o, "filled", 0) or 0)
            except (TypeError, ValueError):
                amt = 0.0
            try:
                px = float(getattr(o, "average", 0) or 0)
            except (TypeError, ValueError):
                px = 0.0
            return amt, px

        amt, px = _extract(order)
        if amt > 0 and px > 0:
            self._record_venue_fee(order, amt, px)
            await self._settle_venue_fee(order, amt, px)
            return amt, px, True

        order_id = str(getattr(order, "id", "") or "")
        if order_id:
            for _attempt in range(3):
                try:
                    await asyncio.sleep(0.2)
                    fetched = await self.exchange.get_order(order_id, symbol)
                except Exception as exc:
                    logger.debug(
                        "settled-fill re-read failed for %s: %s", order_id, exc
                    )
                    break
                f_amt, f_px = _extract(fetched)
                if f_amt > 0 and f_px > 0:
                    self._record_venue_fee(fetched, f_amt, f_px)
                    await self._settle_venue_fee(fetched, f_amt, f_px)
                    return f_amt, f_px, True
                amt = f_amt or amt
                px = f_px or px

        est_amt = amt if amt > 0 else float(requested_amount or 0.0)
        est_px = px if px > 0 else float(quoted_price or 0.0)
        self._last_sell_venue_fee = None
        self._last_fill_venue_fee = None
        _label = self._settled_fill_label(label)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"{_label}: exchange reported no settled fill for "
                f"order {order_id or '?'}; booking the ESTIMATE "
                f"({est_amt:.6f} @ ${est_px:.8f}) instead of a "
                f"confirmed fill. Position accounting may drift from "
                f"the exchange until the next reconcile."
            ),
        )
        return est_amt, est_px, False

    def _venue_quote_currency(self) -> str:
        """The currency a sale is credited in, taken from the symbol."""
        _sym = str(getattr(self.config, "symbol", "") or "")
        _, _, _quote = _sym.partition("/")
        return _quote.strip().upper()

    def _record_venue_fee(self, order, units: float, price: float) -> None:
        """Store the fee the venue reported for a just-settled fill.

        Writes ``_last_fill_venue_fee`` on either side, writes
        ``_last_sell_venue_fee`` for a sell only, reads ``order.fee`` and
        ``order.fee_currency`` only, and never raises.
        """
        self._last_fill_venue_fee = self._venue_fee_record(order, units, price)
        _side = getattr(order, "side", None)
        _side_txt = str(getattr(_side, "value", _side) or "").lower()
        if _side_txt != "sell":
            self._last_sell_venue_fee = None
            return
        self._last_sell_venue_fee = self._last_fill_venue_fee

    @staticmethod
    def _venue_fee_record(
        order, units: float, price: float
    ) -> Optional[SettledFillFee]:
        """Build a ``SettledFillFee`` from ``order.fee`` and ``order.fee_currency``.

        Returns None when ``units`` or ``price`` is not a number, and computes no
        fee of its own.
        """
        try:
            _units = float(units)
            _price = float(price)
        except (TypeError, ValueError):
            return None
        try:
            _amount = float(getattr(order, "fee", 0) or 0)
            _currency = str(getattr(order, "fee_currency", "") or "")
        except (TypeError, ValueError):
            _amount = 0.0
            _currency = ""
        return SettledFillFee(
            units=_units,
            price=_price,
            fee_amount=_amount,
            currency=_currency.strip().upper(),
            reported=_amount > 0.0,
        )

    async def _settle_venue_fee(self, order, units: float, price: float) -> None:
        """Re-reads ``order`` by its id and takes the settled venue fee from that body.

        Writes ``_last_fill_venue_fee`` only, and leaves it unchanged when
        ``get_order`` reports no fee.
        """
        _held = self._last_fill_venue_fee
        if _held is not None and _held.reported:
            return
        _order_id = str(getattr(order, "id", "") or "")
        _symbol = str(getattr(self.config, "symbol", "") or "")
        if not _order_id or not _symbol:
            return
        for _attempt in range(self._VENUE_FEE_REREADS):
            try:
                await asyncio.sleep(self._VENUE_FEE_REREAD_DELAY_S)
                _settled = await self.exchange.get_order(_order_id, _symbol)
            except Exception as exc:
                logger.debug("venue-fee re-read failed for %s: %s", _order_id, exc)
                return
            _probe = self._venue_fee_record(_settled, units, price)
            if _probe is not None and _probe.reported:
                self._last_fill_venue_fee = _probe
                return

    def _take_venue_fee(self, units: float, price: float) -> Optional[SettledFillFee]:
        """Consume the stored fee, and only for the fill it belongs to.

        ``_last_sell_venue_fee`` is cleared on every call, and a record whose
        ``units`` or ``price`` disagree with this fill returns None.
        """
        _rec = self._last_sell_venue_fee
        self._last_sell_venue_fee = None
        if _rec is None:
            return None
        try:
            _units = float(units)
            _price = float(price)
        except (TypeError, ValueError):
            return None
        if not math.isclose(_rec.units, _units, rel_tol=1e-9, abs_tol=1e-12):
            return None
        if not math.isclose(_rec.price, _price, rel_tol=1e-9, abs_tol=1e-12):
            return None
        return _rec

    def _fill_fee_fields(self, fill_price: float) -> dict:
        """The ``trade.filled`` fee fields for the fill that settled at ``fill_price``.

        Returns ``fee_usd`` when the venue reported a usable fee, otherwise
        ``fee_refusal`` naming why, and never reads ``config.trading_fee_pct``.
        """
        _rec = self._last_fill_venue_fee
        self._last_fill_venue_fee = None
        try:
            _price = float(fill_price)
        except (TypeError, ValueError):
            return {"fee_refusal": "the fill price is not a number"}
        if _rec is None:
            return {"fee_refusal": "no settled order was held for this fill"}
        if not _rec.reported:
            return {"fee_refusal": "the venue reported no fee"}
        if not math.isclose(_rec.price, _price, rel_tol=1e-9, abs_tol=1e-12):
            return {"fee_refusal": "the reported fee belongs to a different fill"}
        if not _rec.currency:
            return {"fee_refusal": "the venue named no fee currency"}
        _quote = self._venue_quote_currency()
        if _quote and _rec.currency != _quote:
            return {
                "fee_refusal": (
                    f"the venue charged the fee in {_rec.currency}, not the "
                    f"{_quote} this fill is priced in"
                )
            }
        _rate = float(getattr(self, "_quote_to_usd", 0.0) or 0.0)
        if _rate <= 0.0:
            return {"fee_refusal": f"no {_quote or 'quote'}-to-USD rate is cached"}
        _fee_usd = _rec.fee_amount * _rate
        if not math.isfinite(_fee_usd) or _fee_usd <= 0.0:
            return {"fee_refusal": "the reported fee converts to nothing in USD"}
        return {"fee_usd": _fee_usd}

    def _settled_sale_proceeds(
        self, units: float, price: float, *, label: str
    ) -> float:
        """Value a settled sell at ``units`` times ``price`` minus the venue fee.

        ``_take_venue_fee`` supplying no usable fee books the gross and emits
        the reason to ``bot.log``, and ``config.trading_fee_pct`` is never
        substituted.
        """
        _units = float(units)
        _price = float(price)
        _gross = priced_usd(_units, _price)
        _fee = self._take_venue_fee(_units, _price)
        _refusal = ""
        if _fee is None or not _fee.reported:
            _refusal = "the venue reported no fee"
        elif not _fee.currency:
            _refusal = "the venue named no fee currency"
        elif self._venue_quote_currency() and _fee.currency != (
            self._venue_quote_currency()
        ):
            _refusal = (
                f"the venue charged the fee in {_fee.currency}, not the "
                f"{self._venue_quote_currency()} this sale is credited in"
            )
        elif _fee.fee_amount >= _gross:
            _refusal = (
                f"the reported fee ${_fee.fee_amount:.5f} is not smaller "
                f"than the gross ${_gross:.5f}"
            )
        if _refusal:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"{label} PROCEEDS BOOKED GROSS ${_gross:.5f} for "
                    f"{_units:.6f} @ ${_price:.8f}: {_refusal}. No fee "
                    f"was subtracted and none was estimated. Tranches "
                    f"read richer than the wallet if the venue did "
                    f"charge one."
                ),
            )
            return _gross
        _net = sale_proceeds_usd(_gross, _fee.fee_amount)
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"{label} PROCEEDS BOOKED NET ${_net:.5f} for "
                f"{_units:.6f} @ ${_price:.8f}: gross ${_gross:.5f} "
                f"minus the ${_fee.fee_amount:.5f} {_fee.currency} fee "
                f"the venue reported."
            ),
        )
        return _net

    async def _execute_manual_rebalance(
        self, ticker, caller_intent: str = "manual_button"
    ) -> None:
        """Move holdings back to ``_target_balance`` with one market order.

        ``caller_intent`` picks the trade labels and the
        ``operator_initiated`` flag out of ``_INTENT_MAP`` and raises
        ``ValueError`` when unknown, and a delta inside
        ``manual_fire_dust_band`` is a logged no-op.
        """

        _INTENT_MAP = {
            "manual_button": ("MANUAL_SCRUM", "MANUAL_FOLD", True),
            "wire_stack": ("WIRE_STACK_SCRUM", "WIRE_STACK_FOLD", False),
            "max_cartridge": ("CARTRIDGE_SCRUM", "CARTRIDGE_FOLD", False),
        }
        if caller_intent not in _INTENT_MAP:
            raise ValueError(
                f"_execute_manual_rebalance: unknown caller_intent "
                f"{caller_intent!r}; expected one of "
                f"{sorted(_INTENT_MAP)}"
            )
        _scrum_label, _fold_label, _operator_initiated = _INTENT_MAP[caller_intent]

        self._manual_fire_pending = False

        price = ticker.last
        if not price or price <= 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message="MANUAL FIRE: no valid price; aborting.",
            )
            return

        try:
            await self._refresh_quote_to_usd()
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_execute_manual_rebalance",
                type(_sup).__name__,
                _sup,
            )
        _qrate = float(self._quote_to_usd or 1.0)

        current_value = priced_usd(self._current_holdings, price, _qrate)
        delta_usd = target_delta_usd(current_value, self._target_balance)
        dust = manual_fire_dust_band(self._target_balance)

        if caller_intent != "manual_button":
            try:
                _xbal = await self._get_balance(self.config.target_asset)
                _xunits = float(
                    getattr(_xbal, "total", 0) or getattr(_xbal, "free", 0) or 0.0
                )
                _absent = bool(getattr(_xbal, "absent", False))
            except Exception as _xb_exc:  # noqa: BLE001
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"AUTONOMOUS FIRE REFUSED: could not read "
                        f"{self.config.target_asset} balance to verify the "
                        f"position ({_xb_exc}). Gates are bypassed on this "
                        f"path, so an unverified position is not traded."
                    ),
                )
                return
            if _absent:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"AUTONOMOUS FIRE REFUSED: exchange OMITTED "
                        f"{self.config.target_asset} from its balance "
                        f"response, so the position cannot be verified."
                    ),
                )
                return
            _xvalue = _xunits * price * _qrate
            if abs(_xvalue - current_value) > dust:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"AUTONOMOUS FIRE REFUSED (position mismatch): this "
                        f"bot has {self._current_holdings:.6f} "
                        f"{self.config.target_asset} (${current_value:.2f}) "
                        f"but the exchange reports {_xunits:.6f} "
                        f"(${_xvalue:.2f}). Gates are bypassed on this path, "
                        f"so it will not trade on a disputed position. "
                        f"Intended {'SELL' if delta_usd > 0 else 'BUY'} of "
                        f"${abs(delta_usd):.2f} withheld."
                    ),
                )
                logger.warning(
                    "Bot %s autonomous fire refused: internal %.8f vs "
                    "exchange %.8f %s",
                    self.bot_id,
                    self._current_holdings,
                    _xunits,
                    self.config.target_asset,
                )
                return
            if delta_usd < 0:
                _growth = float(
                    getattr(self.config, "max_target_growth_pct", 1.0) or 0.0
                )
                _ceiling = float(self._target_balance) * (1.0 + _growth / 100.0)
                _prospective = _xvalue + abs(delta_usd)
                if _prospective > _ceiling + dust:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"AUTONOMOUS FIRE REFUSED (ceiling): buying "
                            f"${abs(delta_usd):.2f} would take the position "
                            f"to ${_prospective:.2f}, above the "
                            f"${_ceiling:.2f} cap (target "
                            f"${self._target_balance:.2f} x 1+{_growth:.1f}%)."
                        ),
                    )
                    logger.warning(
                        "Bot %s autonomous buy refused: prospective %.2f "
                        "> ceiling %.2f",
                        self.bot_id,
                        _prospective,
                        _ceiling,
                    )
                    return

        if abs(delta_usd) <= dust:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE: already within dust band "
                    f"(|delta|=${abs(delta_usd):.4f} <= "
                    f"${dust:.2f}). No-op."
                ),
            )
            return

        if delta_usd > 0:
            _denom_sc = price * _qrate
            sell_amount = (
                scrum_units(delta_usd, _denom_sc, FRACTIONAL_UNITS)
                if _denom_sc > 0
                else 0.0
            )
            sell_amount = min(sell_amount, self._current_holdings)
            if sell_amount <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message="MANUAL FIRE: computed zero sell amount; abort.",
                )
                return

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE SCRUM: delta=+${delta_usd:.4f} "
                    f"over target → selling {sell_amount:.6f} "
                    f"{self.config.symbol.split('/')[0]} @ MARKET "
                    f"(~${price:.8f}) to rebalance."
                ),
            )

            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.SELL,
                order_type=OrderType.MARKET,
                amount=sell_amount,
                price=None,
            )

            if order is None:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message="MANUAL FIRE SCRUM: exchange returned no order.",
                )
                return

            fill_amount, fill_price, _fill_is_real = await self._settled_fill(
                order, self.config.symbol, sell_amount, price
            )
            if fill_amount <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"MANUAL FIRE SCRUM: order placed but no "
                        f"filled amount reported (order.filled="
                        f"{getattr(order, 'filled', 'missing')}, "
                        f"order.amount={getattr(order, 'amount', 'missing')}). "
                        f"Aborting post-fill accounting; check exchange for actual state."
                    ),
                )
                return
            if fill_price <= 0:
                fill_price = price

            fill_usd = self._settled_sale_proceeds(
                fill_amount, fill_price, label=_scrum_label
            )
            self._current_holdings = max(0.0, self._current_holdings - fill_amount)

            _manual_routed_total = self._route_scrum_proceeds_via_wires(
                scrum_usd=fill_usd, sell_fill=fill_price, label="manual_scrum"
            )
            fill_usd = max(0.0, fill_usd - _manual_routed_total)

            self._main_lots.sort(key=lambda l: l["initial_buy_price"], reverse=True)
            _manual_tranche_count_before = len(self._fold_tranches)
            remaining = fill_amount
            new_tranches_count = 0
            for lot in list(self._main_lots):
                if remaining <= 1e-12:
                    break
                take = min(lot["units"], remaining)
                t_usd = (take / fill_amount) * fill_usd
                self._fold_tranches.append(
                    {
                        "usd": t_usd,
                        "units": take,
                        "ref": fill_price,
                        "initial_buy_price": lot["initial_buy_price"],
                        "operator_initiated": _operator_initiated,
                        "created_ts": time.time(),
                    }
                )
                self._tranches_created_lifetime += 1
                lot["units"] -= take
                remaining -= take
                if lot["units"] <= 1e-12:
                    self._main_lots.remove(lot)
                new_tranches_count += 1

            # Returns how many tranches the merge removed.
            new_tranches_count -= self._bound_new_fold_tranches(
                _manual_tranche_count_before
            )

            # Must precede the _fold_queue_usd sum below.
            self._apply_scrum_fold_pct(
                _manual_tranche_count_before, fill_usd, fill_amount
            )

            _bb_last = getattr(self, "_last_bb", None)
            _merged_n, _ = self._top_up_remnant_fold_tranches(
                _manual_tranche_count_before,
                float(getattr(_bb_last, "lower", 0.0) or 0.0),
                float(getattr(_bb_last, "upper", 0.0) or 0.0),
            )
            new_tranches_count -= _merged_n

            self._land_pending_wire_credits()

            self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
            self.stats.total_trades += 1

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE SCRUM FILLED: {fill_amount:.6f} "
                    f"@ ${fill_price:.8f} = ${fill_usd:.4f}. "
                    f"{new_tranches_count} tranche(s) queued "
                    f"(operator_initiated). Holdings now "
                    f"{self._current_holdings:.6f} "
                    f"(~${priced_usd(self._current_holdings, price, float(self._quote_to_usd or 1.0)):.2f})."
                ),
            )
            self._bus.emit(
                "trade.filled",
                bot_id=self.bot_id,
                data={
                    "type": _scrum_label,
                    "side": "SELL",
                    "amount": fill_amount,
                    "price": fill_price,
                    "usd": fill_usd,
                    "profit": 0.0,
                    "operator_initiated": _operator_initiated,
                    **self._fill_fee_fields(fill_price),
                },
            )
            self._emit_voting_panel_snapshot_at_fire(
                side="SELL", trade_action=str(_scrum_label or "MANUAL_SCRUM")
            )
            self._emit_gate_decision_at_fire(
                side="SELL", trade_action=str(_scrum_label or "MANUAL_SCRUM")
            )
            try:
                self._bus.emit(
                    "pnl.event",
                    bot_id=self.bot_id,
                    data={
                        "kind": "SCRUM",
                        "asset": self.config.target_asset,
                        "symbol": self.config.symbol,
                        "units": float(fill_amount),
                        "fill_price": float(fill_price),
                        "usd_captured": float(fill_usd)
                        * float(self._quote_to_usd or 1.0),
                        "operator_initiated": _operator_initiated,
                        "manual_kind": _scrum_label,
                    },
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_manual_rebalance",
                    type(_sup).__name__,
                    _sup,
                )
            _fill_usd_true = float(fill_usd) * float(self._quote_to_usd or 1.0)
            self.stats.total_scrummed_usd += _fill_usd_true
            self.note_scrum_retention_usd(_fill_usd_true)
            self._last_trade_side = "SCRUM"
            self._last_trade_price = fill_price
            self._reset_opposing_hysteresis_after_fill()

        else:

            if caller_intent != "manual_button" and self._fold_tranches:
                from ..otd_math import (
                    fold_rebuy_factor,
                )

                _fold_factor = 1.0
                _best_rebuy = 0.0
                _distance_ok = False

                _unreadable_refs = 0
                _thresholds: list[float] = []
                try:
                    _fold_factor = fold_rebuy_factor(
                        getattr(self.config, "scrumming_interval_pct", 0) or 0,
                        getattr(self.config, "trading_fee_pct", 0.6) or 0.6,
                    )

                    for _t in self._fold_tranches:
                        _t_thresh = float(_t.get("ref", 0)) * _fold_factor
                        if not math.isfinite(_t_thresh):
                            _unreadable_refs += 1
                            continue
                        _thresholds.append(_t_thresh)
                    if _thresholds:
                        _best_rebuy = max(_thresholds)
                        _distance_ok = price <= _best_rebuy
                except (TypeError, ValueError, OverflowError) as _otd_exc:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"AUTONOMOUS FIRE REFUSED (opposing distance "
                            f"unreadable): {_otd_exc}. Gates are bypassed on "
                            f"this path, so a rebuy distance that cannot be "
                            f"computed is not traded. Intended BUY of "
                            f"${abs(delta_usd):.2f} withheld."
                        ),
                    )
                    logger.warning(
                        "Bot %s autonomous fold refused: opposing distance "
                        "unreadable: %s",
                        self.bot_id,
                        _otd_exc,
                    )
                    return
                _unread_tail = ""
                if _unreadable_refs:
                    _unread_tail = (
                        f" {_unreadable_refs} of the "
                        f"{len(self._fold_tranches)} queued tranche(s) hold "
                        f"a ref that is not a finite number; those set no "
                        f"threshold at all, so this answer is the one for "
                        f"the {len(_thresholds)} readable tranche(s)."
                    )
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD REF UNREADABLE: {_unreadable_refs} of "
                            f"{len(self._fold_tranches)} queued tranche(s) hold a "
                            f"ref that is not a finite number (nan or inf), so "
                            f"they set no rebuy threshold and the gate answered "
                            f"on the {len(_thresholds)} readable one(s). The "
                            f"ladder is NOT altered here; this gate only "
                            f"withholds or allows the fire. Repair the row in "
                            f"bot state to bring those tranches back into the "
                            f"distance test."
                        ),
                    )
                    logger.warning(
                        "Bot %s fold ref unreadable on %d of %d tranche(s); "
                        "gated on the %d readable one(s)",
                        self.bot_id,
                        _unreadable_refs,
                        len(self._fold_tranches),
                        len(_thresholds),
                    )
                if not _distance_ok:
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"AUTONOMOUS FIRE REFUSED (opposing distance): at "
                            f"${price:.8f} not one of the "
                            f"{len(self._fold_tranches)} queued tranche(s) is "
                            f"eligible. The highest rebuy any of them allows "
                            f"is ${_best_rebuy:.8f} (its ref x "
                            f"{_fold_factor:.4f}), so price must fall "
                            f"${price - _best_rebuy:.8f} further. Gates are "
                            f"bypassed on this path, so it will not rebuy "
                            f"above what it sold at. Intended BUY of "
                            f"${abs(delta_usd):.2f} withheld.{_unread_tail}"
                        ),
                    )
                    logger.warning(
                        "Bot %s autonomous fold refused: price %.8f above "
                        "best rebuy %.8f across %d tranche(s), %d unreadable",
                        self.bot_id,
                        price,
                        _best_rebuy,
                        len(self._fold_tranches),
                        _unreadable_refs,
                    )
                    return

            _denom_pre = price * _qrate
            _growth_preview = 0.0
            self._fold_preview_unreadable_refs = 0
            self._fold_preview_unreadable_units = 0
            if _denom_pre > 0:
                for _ in range(4):
                    _units_pre = ((-delta_usd) + _growth_preview) / _denom_pre
                    _g = self._preview_fold_growth(_units_pre, price)
                    if abs(_g - _growth_preview) <= 1e-9:
                        break
                    _growth_preview = _g
            _preview_unreadable = int(
                getattr(self, "_fold_preview_unreadable_refs", 0) or 0
            )
            if _preview_unreadable:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD SIZING REF UNREADABLE: {_preview_unreadable} of "
                        f"{len(self._fold_tranches)} queued tranche(s) hold a "
                        f"ref that is not a finite number (nan or inf). Those "
                        f"set no discharge order and add no prospective "
                        f"growth, so this buy is sized on the "
                        f"{len(self._fold_tranches) - _preview_unreadable} "
                        f"readable one(s). The ladder is NOT altered here. "
                        f"Repair the row in bot state to bring those tranches "
                        f"back into the sizing."
                    ),
                )
                logger.warning(
                    "Bot %s fold sizing ref unreadable on %d of %d " "tranche(s)",
                    self.bot_id,
                    _preview_unreadable,
                    len(self._fold_tranches),
                )
            _preview_unsizable = int(
                getattr(self, "_fold_preview_unreadable_units", 0) or 0
            )
            if _preview_unsizable:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD SIZING UNITS UNREADABLE: {_preview_unsizable} of "
                        f"{len(self._fold_tranches)} queued tranche(s) hold "
                        f"units that are not a finite number (nan or inf). "
                        f"Those discharge nothing and add no prospective "
                        f"growth, so this buy is sized on the remaining "
                        f"readable one(s). The ladder is NOT altered here. "
                        f"Repair the row in bot state to bring those tranches "
                        f"back into the sizing."
                    ),
                )
                logger.warning(
                    "Bot %s fold sizing units unreadable on %d of %d " "tranche(s)",
                    self.bot_id,
                    _preview_unsizable,
                    len(self._fold_tranches),
                )
            buy_usd_target = -delta_usd + _growth_preview
            if _growth_preview > 1e-9:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"MANUAL FIRE FOLD: sizing against the "
                        f"POST-growth target — base deficit "
                        f"${-delta_usd:.4f} + prospective compound "
                        f"growth ${_growth_preview:.4f} = "
                        f"${buy_usd_target:.4f}. Without this the "
                        f"fold would land ${_growth_preview:.4f} "
                        f"short and could not compound."
                    ),
                )
            quote_currency = self.config.symbol.split("/")[-1]
            quote_free = 0.0
            _bal_err = None
            try:
                bal = await self._get_balance(quote_currency)
                quote_free = float(getattr(bal, "free", 0) or 0)
            except Exception as exc:
                _bal_err = exc
                try:
                    balances = await self.exchange.get_balances()
                    b = balances.get(quote_currency)
                    if b is not None:
                        quote_free = float(getattr(b, "free", 0) or 0)
                except Exception as exc2:
                    _bal_err = exc2
            _wallet_key = wallet_key(self.config.exchange_id, quote_currency)
            _reservations = get_wallet_reservations()
            _wallet_free = quote_free * _qrate
            usd_balance = _reservations.available(_wallet_key, _wallet_free)
            _held_by_others = _reservations.reserved(_wallet_key)
            # A sale the venue has not settled has not returned its cash, so its
            # dollars are held back before the buy is sized against the wallet.
            try:
                _fold_rules = await self._get_market_rules(self.config.symbol)
                _settlement = getattr(_fold_rules, "settlement_days", None)
            except Exception:
                _settlement = None
            _unsettled = unsettled_usd(
                getattr(self, "_fold_tranches", ()), time.time(), _settlement
            )
            buy_usd = spend_less_unsettled_usd(
                wallet_capped_spend_usd(buy_usd_target, usd_balance),
                usd_balance,
                _unsettled,
            )
            if buy_usd <= 0:
                err_tail = f" (fetch error: {_bal_err})" if _bal_err else ""
                unsettled_tail = (
                    f", of which ${_unsettled:.4f} is cash the venue has not "
                    f"settled at {_settlement} day(s)"
                    if _unsettled > 1e-9
                    else ""
                )
                held_tail = (
                    f", of which ${_held_by_others:.4f} is reserved by "
                    f"other bots' in-flight orders"
                    if _held_by_others > 1e-9
                    else ""
                ) + unsettled_tail
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"MANUAL FIRE FOLD: delta=-${buy_usd_target:.4f} "
                        f"but {quote_currency} free=${quote_free:.4f} "
                        f"(~${_wallet_free:.4f} USD{held_tail}; "
                        f"spendable ${usd_balance:.4f})"
                        f"{err_tail}. Cannot rebalance."
                    ),
                )
                return
            denom = price * _qrate
            buy_amount = (
                fold_units(buy_usd, denom, FRACTIONAL_UNITS) if denom > 0 else 0.0
            )
            clipped = buy_usd < buy_usd_target
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE FOLD: delta=-${buy_usd_target:.4f} "
                    f"under target → buying {buy_amount:.6f} "
                    f"{self.config.symbol.split('/')[0]} @ MARKET "
                    f"(~${price:.8f}) with ${buy_usd:.4f}"
                    f"{f' (CLIPPED by {quote_currency})' if clipped else ''}."
                ),
            )

            _reservations.reserve(_wallet_key, buy_usd)
            try:
                order = await self.guarded_place_order(
                    symbol=self.config.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    amount=buy_amount,
                    price=None,
                )
            finally:
                _reservations.release(_wallet_key, buy_usd)

            if order is None:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message="MANUAL FIRE FOLD: exchange returned no order.",
                )
                return

            fill_amount, fill_price, _fill_is_real = await self._settled_fill(
                order, self.config.symbol, buy_amount, price
            )
            if fill_amount <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"MANUAL FIRE FOLD: order placed but no "
                        f"filled amount reported (order.filled="
                        f"{getattr(order, 'filled', 'missing')}, "
                        f"order.amount={getattr(order, 'amount', 'missing')}). "
                        f"Aborting post-fill accounting; check exchange for actual state."
                    ),
                )
                return
            if fill_price <= 0:
                fill_price = price

            _manual_fold_accum_profit = 0.0
            if self._fold_tranches:
                remaining = fill_amount
                consumed = []
                for t in self._fold_discharge_order():
                    if remaining <= 1e-12:
                        break
                    # _fold_discharge_order yields finite units.
                    t_units = float(t.get("units", 0.0) or 0.0)
                    take = min(t_units, remaining)
                    if take <= 1e-12:
                        continue
                    _t_ref = float(t.get("ref", 0.0) or 0.0)
                    if _t_ref > fill_price:
                        _manual_fold_accum_profit += take * (_t_ref - fill_price)
                    self._main_lots.append(
                        {
                            "units": take,
                            "initial_buy_price": t.get("initial_buy_price", fill_price),
                            "operator_initiated": _operator_initiated,
                        }
                    )
                    t["units"] = t_units - take
                    if t_units > 0:
                        t["usd"] *= t["units"] / t_units
                    remaining -= take
                    if t["units"] <= 1e-12:
                        consumed.append(t)

                for t in consumed:
                    self._fold_tranches.remove(t)
                if consumed:
                    try:
                        self._tranches_closed_lifetime = int(
                            getattr(self, "_tranches_closed_lifetime", 0) or 0
                        ) + len(consumed)
                    except Exception as _sup:
                        logger.debug(
                            "suppressed in %s: %s: %s",
                            "_execute_manual_rebalance",
                            type(_sup).__name__,
                            _sup,
                        )

                if remaining > 1e-12:
                    self._main_lots.append(
                        {
                            "units": remaining,
                            "initial_buy_price": fill_price,
                            "operator_initiated": _operator_initiated,
                        }
                    )

                self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)

                msg = (
                    f"MANUAL FIRE FOLD FILLED: {fill_amount:.6f} @ "
                    f"${fill_price:.8f}. Discharged "
                    f"{len(consumed)} tranche(s) bypassing MEM-171 "
                    f"gates (operator override)."
                )
            else:
                self._main_lots.append(
                    {
                        "units": fill_amount,
                        "initial_buy_price": fill_price,
                        "operator_initiated": _operator_initiated,
                    }
                )
                msg = (
                    f"MANUAL FIRE FOLD FILLED: {fill_amount:.6f} @ "
                    f"${fill_price:.8f}. No tranches queued; "
                    f"opened new lot (operator_initiated)."
                )

            self._current_holdings += fill_amount
            self.stats.total_trades += 1

            _growth_applied = self._apply_fold_target_growth(
                _manual_fold_accum_profit, source=str(_fold_label)
            )

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    msg + f" Holdings now "
                    f"{self._current_holdings:.6f} "
                    f"(~${priced_usd(self._current_holdings, price, float(self._quote_to_usd or 1.0)):.2f})."
                ),
            )
            self.stats.total_folded_usd += float(
                fill_amount * fill_price * float(self._quote_to_usd or 1.0)
            )
            self.reset_swos_cycle()
            self._last_trade_side = "FOLD"
            self._reset_opposing_hysteresis_after_fill()
            self._bus.emit(
                "trade.filled",
                bot_id=self.bot_id,
                data={
                    "type": _fold_label,
                    "side": "BUY",
                    "amount": fill_amount,
                    "price": fill_price,
                    "usd": fill_amount * fill_price,
                    "profit": _growth_applied,
                    "operator_initiated": _operator_initiated,
                    **self._fill_fee_fields(fill_price),
                },
            )
            self._emit_voting_panel_snapshot_at_fire(
                side="BUY", trade_action=str(_fold_label or "MANUAL_FOLD")
            )
            self._emit_gate_decision_at_fire(
                side="BUY", trade_action=str(_fold_label or "MANUAL_FOLD")
            )
            try:
                self._bus.emit(
                    "pnl.event",
                    bot_id=self.bot_id,
                    data={
                        "kind": "FOLD",
                        "asset": self.config.target_asset,
                        "symbol": self.config.symbol,
                        "units_rebought": float(fill_amount),
                        "fill_price": float(fill_price),
                        "usd_spent": float(fill_amount * fill_price)
                        * float(self._quote_to_usd or 1.0),
                        "operator_initiated": _operator_initiated,
                        "manual_kind": _fold_label,
                    },
                )
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_manual_rebalance",
                    type(_sup).__name__,
                    _sup,
                )
            self._last_trade_price = fill_price

    async def _execute_detonation(self, ticker) -> None:
        """Sell everything above ``_anchor_target_balance`` and reset to it.

        Clears ``_fold_tranches`` and ``_standing_surplus_usd``, reseeds
        ``_main_lots`` at the fill price, and emits ``trade.filled`` carrying
        ``auto_detonated``.
        """
        price = getattr(ticker, "last", None)
        if not price or price <= 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message="DETONATION: no valid price; aborting.",
            )
            return

        _qrate = float(self._quote_to_usd or 1.0)
        current_value = priced_usd(self._current_holdings, price, _qrate)
        excess_usd = target_delta_usd(current_value, self._anchor_target_balance)
        if excess_usd <= 0:
            return

        sell_amount = (
            scrum_units(excess_usd, price * _qrate, FRACTIONAL_UNITS)
            if (price * _qrate) > 0
            else 0.0
        )
        sell_amount = min(sell_amount, self._current_holdings)
        if sell_amount <= 0:
            return

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"DETONATION HARVEST: value=${current_value:.2f}, "
                f"anchor=${self._anchor_target_balance:.2f}, "
                f"selling {sell_amount:.6f} "
                f"{self.config.symbol.split('/')[0]} @ MARKET "
                f"(~${price:.8f}) to lock in "
                f"${excess_usd:.2f} gains."
            ),
        )

        order = await self.guarded_place_order(
            symbol=self.config.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            amount=sell_amount,
            price=None,
        )

        if order is None:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message="DETONATION: exchange returned no order.",
            )
            return

        _filled_raw = (
            getattr(order, "filled", None)
            or getattr(order, "amount", None)
            or sell_amount
        )
        try:
            fill_amount = float(_filled_raw or 0.0)
        except (TypeError, ValueError):
            fill_amount = 0.0
        if fill_amount <= 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    "DETONATION: order placed but no filled "
                    "amount reported. Check exchange for actual "
                    "state."
                ),
            )
            return

        fill_price = (
            getattr(order, "average_price", None)
            or getattr(order, "average", None)
            or getattr(order, "price", None)
            or price
        )
        try:
            fill_price = float(fill_price)
        except (TypeError, ValueError):
            fill_price = price

        fill_usd = fill_price * fill_amount

        self._current_holdings = max(0.0, self._current_holdings - fill_amount)

        _detonation_routed_total = self._route_scrum_proceeds_via_wires(
            scrum_usd=fill_usd, sell_fill=fill_price, label="detonation"
        )
        try:
            _detonation_kept = float(fill_usd) - float(_detonation_routed_total or 0.0)
            self._bus.emit(
                "pnl.event",
                bot_id=self.bot_id,
                data={
                    "kind": "SCRUM",
                    "asset": self.config.target_asset,
                    "symbol": self.config.symbol,
                    "units": float(fill_amount),
                    "fill_price": float(fill_price),
                    "usd_captured": _detonation_kept * float(self._quote_to_usd or 1.0),
                    "usd_routed_via_wires": float(_detonation_routed_total or 0.0)
                    * float(self._quote_to_usd or 1.0),
                    "operator_initiated": False,
                    "manual_kind": "DETONATION",
                },
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_execute_detonation",
                type(_sup).__name__,
                _sup,
            )

        prior_target = self._target_balance
        self._target_balance = self._anchor_target_balance
        _detonated_tranches = len(self._fold_tranches)
        if _detonated_tranches:
            self._tranches_discarded_lifetime = (
                int(getattr(self, "_tranches_discarded_lifetime", 0) or 0)
                + _detonated_tranches
            )
        self._fold_tranches.clear()
        self._fold_queue_usd = 0.0
        _discharged_surplus = float(getattr(self, "_standing_surplus_usd", 0.0) or 0.0)
        self._standing_surplus_usd = 0.0
        try:
            self.stats.standing_surplus_usd = 0.0
        except Exception as _sp_exc:  # noqa: BLE001
            logger.debug("detonation surplus mirror failed: %s", _sp_exc)

        self._main_lots.clear()
        if self._current_holdings > 0:
            self._main_lots.append(
                {
                    "units": self._current_holdings,
                    "initial_buy_price": fill_price,
                    "auto_detonated_reset": True,
                }
            )

        self.stats.total_trades += 1
        self._last_trade_price = fill_price

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"DETONATION COMPLETE: filled {fill_amount:.6f} @ "
                f"${fill_price:.8f} = ${fill_usd:.2f}. "
                f"target_balance reset ${prior_target:.2f} → "
                f"${self._anchor_target_balance:.2f} (anchor). "
                f"Fold queue cleared. Standing surplus "
                f"${_discharged_surplus:.4f} discharged. "
                f"Bot will re-accumulate from scratch on next dip."
            ),
        )

        self._bus.emit(
            "trade.filled",
            bot_id=self.bot_id,
            data={
                "type": "AUTO_DETONATION",
                "side": "SELL",
                "amount": fill_amount,
                "price": fill_price,
                "usd": fill_usd,
                "profit": excess_usd,
                "auto_detonated": True,
                "anchor": self._anchor_target_balance,
                **self._fill_fee_fields(fill_price),
            },
        )
        self._emit_voting_panel_snapshot_at_fire(
            side="SELL", trade_action="AUTO_DETONATION"
        )
        self._emit_gate_decision_at_fire(side="SELL", trade_action="AUTO_DETONATION")

    async def _execute_sell(
        self,
        amount: float,
        price: float,
        summary: VotingSummary,
        bypass_stack: bool = False,
    ) -> Optional[float]:
        """Place a market sell and return the fill price, or None when refused.

        Both venue-fee records are cleared on entry and written by
        ``_record_venue_fee`` once the venue reports a settled order.
        """
        self._last_sell_venue_fee = None
        self._last_fill_venue_fee = None

        if (
            not bypass_stack
            and getattr(self.config, "stack_mode", False)
            and amount
            and amount > 0
            and price
            and price > 0
        ):
            _n = await self._open_stack_from_scrum(
                scrum_price=float(price),
                scrum_size=float(amount),
                summary=summary,
            )
            if _n > 0:
                return None

        if (
            self._hyst_armed_scrum_side
            and self._hyst_ref_scrum_side > 0
            and getattr(self.config, "scrumming_interval_pct", 0) > 0
        ):
            try:
                _px_check = float(price)
            except (TypeError, ValueError):
                _px_check = 0.0
            _interval = float(self.config.scrumming_interval_pct)
            _fee = float(getattr(self.config, "trading_fee_pct", 0.6))
            _eff_pct = _interval + _fee
            _interval_frac = _eff_pct / 100.0
            _required_min = self._hyst_ref_scrum_side * (1.0 + _interval_frac)
            if _px_check > 0 and _px_check < _required_min:
                _rise_pct = (
                    (_px_check - self._hyst_ref_scrum_side)
                    / self._hyst_ref_scrum_side
                    * 100.0
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SCRUM REFUSED (opposing hysteresis v3.15.77): "
                        f"pivot ref ${self._hyst_ref_scrum_side:.8f} "
                        f"(captured when Δ crossed positive after recent "
                        f"FOLD), current ${_px_check:.8f} "
                        f"(only {_rise_pct:+.2f}% from pivot). "
                        f"Need ≥ {_eff_pct:.2f}% rise "
                        f"(interval {_interval:.2f}% + fee {_fee:.2f}%; "
                        f"price ≥ ${_required_min:.8f}) before "
                        f"SCRUM can fire."
                    ),
                )
                self._emit_trade_notification(
                    "SCRUM", "CANCELLED", f"hysteresis (need ≥ {_eff_pct:.2f}% rise)"
                )
                return None

        try:
            _crr_reg = self._crr()
            if _crr_reg is None:
                raise RuntimeError("no capital registry")
            _crr_effective = _crr_reg.effective_available(
                asset=self.config.target_asset,
                bot_id=self.bot_id,
                total_holdings=float(self._current_holdings or 0),
            )
            if amount > _crr_effective + 1e-12:
                try:
                    _crr_holders = ", ".join(
                        f"{r.bot_id} holds {r.qty:.6f}"
                        for r in _crr_reg.reservations_for(
                            asset=self.config.target_asset,
                            excluding_bot_id=self.bot_id,
                        )
                    )
                except Exception as _crr_who:  # noqa: BLE001
                    # Must not raise: the outer except turns a refusal into a sell.
                    # The outer except refuses the sell, so a raise here costs
                    # only _crr_holders.
                    _crr_holders = ""
                    logger.debug(
                        "Bot %s could not list claim holders on %s: %s",
                        self.bot_id,
                        self.config.target_asset,
                        _crr_who,
                    )
                _crr_msg = (
                    f"SELL REFUSED (capital reservation, v3.20.2): "
                    f"requested {amount:.6f} {self.config.target_asset} but "
                    f"only {_crr_effective:.6f} available to this bot — "
                    f"_current_holdings={float(self._current_holdings or 0):.6f}; "
                    f"claimed by "
                    f"{_crr_holders or 'a bot the registry cannot name'}. "
                    f"Stopping a named bot releases its claim."
                )
                self._bus.emit("bot.log", bot_id=self.bot_id, message=_crr_msg)
                self._emit_trade_notification(
                    "SCRUM",
                    "CANCELLED",
                    f"capital reservation (avail {_crr_effective:.6f})",
                )
                logger.info(
                    "Bot %s sell refused by capital reservation: "
                    "amount=%.6f effective=%.6f asset=%s",
                    self.bot_id,
                    amount,
                    _crr_effective,
                    self.config.target_asset,
                )
                return None
        except Exception as _crr_exc:
            # The only reader of another bot's claim; without it this sell is
            # bounded by _current_holdings alone.
            logger.warning(
                "Bot %s sell of %.6f %s is NOT bounded by any other bot's "
                "capital reservation: the pre-check raised %s: %s. A sibling "
                "bot's claim on this asset is invisible to this sell.",
                self.bot_id,
                amount,
                self.config.target_asset,
                type(_crr_exc).__name__,
                _crr_exc,
            )
            # A raised pre-check has not answered, so this sell stops instead
            # of running on _current_holdings alone.
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"SELL REFUSED (capital reservation unreadable): the "
                    f"pre-check raised {type(_crr_exc).__name__}: "
                    f"{_crr_exc}. No sibling bot's claim on "
                    f"{self.config.target_asset} could be read, so this sell "
                    f"of {amount:.6f} is refused instead of placed unbounded. "
                    f"The next tick reads the claim table again."
                ),
            )
            self._emit_trade_notification(
                "SCRUM", "CANCELLED", "capital reservation unreadable"
            )
            return None

        try:
            _open = await self.exchange.get_open_orders(self.config.symbol)
        except Exception as _oo_exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"P0b SELL REFUSED (fail-closed): "
                    f"get_open_orders raised {type(_oo_exc).__name__}: "
                    f"{_oo_exc}. Cannot verify absence of stacked "
                    f"orders. Refusing."
                ),
            )
            return None
        try:
            _open_sells = [
                o
                for o in (_open or [])
                if getattr(o, "side", None) == OrderSide.SELL
                and getattr(o, "symbol", None) == self.config.symbol
            ]
        except Exception:
            _open_sells = [
                o
                for o in (_open or [])
                if getattr(o, "symbol", None) == self.config.symbol
            ]
        if _open_sells:
            _ids = ", ".join(str(getattr(o, "id", "?")) for o in _open_sells[:3])
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"P0b STACKED SELL REFUSED: {len(_open_sells)} open "
                    f"SELL order(s) already on exchange for "
                    f"{self.config.symbol} (ids: {_ids}). "
                    f"Refusing to place a second SELL on top. "
                    f"Wait for existing order(s) to fill or cancel."
                ),
            )
            return None

        try:
            from ...core.execution_discipline import verify_hit as _vh

            vh_fp, vh_status, vh_samples = _vh(
                price, "sell", symbol=self.config.target_asset
            )
            self.stats.verify_samples += vh_samples
            if vh_fp is None:
                self.stats.verify_canceled += 1
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"SELL CANCELED (R55 VH): slippage would "
                    f"exceed {self.config.target_asset} class "
                    f"tolerance @ ${price:.8f}",
                )
                logger.info(
                    "Bot %s VH-canceled sell of %.6f at %.4f",
                    self.bot_id,
                    amount,
                    price,
                )
                return
            if vh_status == "clean":
                self.stats.verify_clean += 1
            else:
                self.stats.verify_adjusted += 1

            if self._invisible:
                ot = OrderType.MARKET
                exec_price = None
            else:
                ot = OrderType.LIMIT
                exec_price = vh_fp

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"SELL signal: {amount:.6f} @ ${price:.8f} "
                f"(VH:{vh_status}, confidence="
                f"{summary.consensus_confidence:.2f}, "
                f"{'MARKET' if self._invisible else 'LIMIT'})",
            )
            self._emit_trade_notification(
                "SCRUM", "SENT", f"{amount:.6f} @ ${price:.8f}"
            )

            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.SELL,
                order_type=ot,
                amount=amount,
                price=exec_price,
            )

            if order is None:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SELL ABORTED: exchange/guard returned no order for "
                        f"{amount:.6f} {self.config.target_asset} @ "
                        f"${price:.8f}. No state update. Caller must not "
                        f"treat this as success."
                    ),
                )
                logger.warning(
                    "Bot %s sell aborted (order None) for %.6f at %.4f",
                    self.bot_id,
                    amount,
                    price,
                )
                try:
                    await self._reconcile_holdings(reason="post_failure")
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "_execute_sell",
                        type(_sup).__name__,
                        _sup,
                    )
                return None

            self._current_holdings -= amount
            self.stats.total_sells += 1
            self.stats.total_trades += 1

            actual_fill = getattr(order, "average", None) or getattr(
                order, "price", None
            )
            if not actual_fill or actual_fill <= 0:
                actual_fill = price
            # The only point on the SCRUM and DIST paths holding the settled order.
            self._record_venue_fee(order, amount, actual_fill)
            await self._settle_venue_fee(order, amount, actual_fill)
            slippage_pct = ((actual_fill - price) / price * 100.0) if price > 0 else 0.0

            self.stats.trade_volume += amount * actual_fill
            self.stats.last_trade_time = time.time()

            try:
                _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
                _fill_usd = float(amount) * float(actual_fill) * _qrate
                self.stats.ytd_scrummed_usd = (
                    float(getattr(self.stats, "ytd_scrummed_usd", 0.0) or 0.0)
                    + _fill_usd
                )
            except (TypeError, ValueError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_sell",
                    type(_sup).__name__,
                    _sup,
                )

            self._memorised_trades.append(
                MemorisedTrade(
                    timestamp=time.time(),
                    side="sell",
                    price=actual_fill,
                    amount=amount,
                    voting_summary=summary,
                )
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"SELL FILLED: {amount:.6f} {self.config.target_asset} "
                f"@ ${actual_fill:.8f} "
                f"(intended ${price:.8f}, slip {slippage_pct:+.3f}%)",
            )
            self._emit_trade_notification(
                "SCRUM", "FILLED", f"{amount:.6f} @ ${actual_fill:.8f}"
            )
            logger.info(
                "Bot %s sold %.6f at %.4f (intended %.4f, slip %+.3f%%, confidence=%.2f)",
                self.bot_id,
                amount,
                actual_fill,
                price,
                slippage_pct,
                summary.consensus_confidence,
            )
            return actual_fill
        except Exception as exc:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=f"SELL FAILED: {exc}")
            logger.error("Bot %s sell failed: %s", self.bot_id, exc)
            try:
                await self._reconcile_holdings(reason="post_failure")
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_sell",
                    type(_sup).__name__,
                    _sup,
                )
            return None

    async def _verify_buy_safe_or_refuse(
        self,
        *,
        path: str,
    ) -> tuple[Optional[float], str]:
        """Check the position through ``verify_buy_safe_or_refuse``.

        Returns ``(verified_units, refuse_reason)`` for ``path``, with the
        expected units summed from ``_main_lots``, and a non-empty
        ``refuse_reason`` obliges the caller to refuse the buy.
        """
        from ..buy_safety import verify_buy_safe_or_refuse

        expected_units = sum(
            float(lot.get("units", 0.0)) for lot in getattr(self, "_main_lots", [])
        )
        return await verify_buy_safe_or_refuse(
            self.exchange,
            self.config.target_asset,
            expected_units,
            path=path,
        )

    async def _execute_buy(
        self,
        cost: float,
        price: float,
        summary: VotingSummary,
        trace_context: Optional[dict] = None,
    ) -> Optional[float]:
        """Place a market buy and return the fill price, or None when refused.

        ``trace_context`` supplies the ``path`` named in the buy trace this
        emits to ``bot.log``, and ``_last_fill_venue_fee`` is cleared on entry.
        """
        self._last_fill_venue_fee = None

        try:
            _ctx = dict(trace_context or {})
            _path = _ctx.get("path", "unspecified")
            _holdings = self._current_holdings
            _value = priced_usd(_holdings, price, float(self._quote_to_usd or 1.0))
            _delta = target_delta_usd(_value, self._target_balance)
            _tranches_n = len(self._fold_tranches)
            _main_lots_n = len(self._main_lots)
            _ctx_extras = ", ".join(f"{k}={v}" for k, v in _ctx.items() if k != "path")
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MEM-205 BUY TRACE: path={_path} "
                    f"value=${_value:.4f} target=${self._target_balance:.2f} "
                    f"delta=${_delta:+.4f} cost=${cost:.4f} price=${price:.8f} "
                    f"holdings={_holdings:.6f} "
                    f"main_lots={_main_lots_n} fold_tranches={_tranches_n} "
                    f"initialised={self._initialised} "
                    f"conf={summary.consensus_confidence:.2f}"
                    + (f" | {_ctx_extras}" if _ctx_extras else "")
                ),
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s", "_execute_buy", type(_sup).__name__, _sup
            )

        if (
            self._hyst_armed_fold_side
            and self._hyst_ref_fold_side > 0
            and getattr(self.config, "scrumming_interval_pct", 0) > 0
        ):
            try:
                _px_check = float(price)
            except (TypeError, ValueError):
                _px_check = 0.0
            _interval = float(self.config.scrumming_interval_pct)
            _fee = float(getattr(self.config, "trading_fee_pct", 0.6))
            _eff_pct = _interval + _fee
            _interval_frac = _eff_pct / 100.0
            _required_max = self._hyst_ref_fold_side * (1.0 - _interval_frac)
            if _px_check > 0 and _px_check > _required_max:
                _drop_pct = (
                    (self._hyst_ref_fold_side - _px_check)
                    / self._hyst_ref_fold_side
                    * 100.0
                )
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"FOLD REFUSED (opposing hysteresis v3.15.77): "
                        f"pivot ref ${self._hyst_ref_fold_side:.8f} "
                        f"(captured when Δ crossed negative after recent "
                        f"SCRUM), current ${_px_check:.8f} "
                        f"(only {_drop_pct:+.2f}% from pivot). "
                        f"Need ≥ {_eff_pct:.2f}% drop "
                        f"(interval {_interval:.2f}% + fee {_fee:.2f}%; "
                        f"price ≤ ${_required_max:.8f}) before "
                        f"FOLD can fire."
                    ),
                )
                self._emit_trade_notification(
                    "FOLD", "CANCELLED", f"hysteresis (need ≥ {_eff_pct:.2f}% drop)"
                )
                return None

        _max_ep = getattr(self.config, "max_entry_price", None)
        _min_ep = getattr(self.config, "min_entry_price", None)
        try:
            _px = float(price) if price is not None else 0.0
        except (TypeError, ValueError):
            _px = 0.0
        if _max_ep is not None and _px > 0 and _px > float(_max_ep):
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"BUY REFUSED (max_entry_price gate): current "
                    f"price ${_px:.8f} > max_entry_price "
                    f"${float(_max_ep):.8f}. Operator-set ceiling. "
                    f"Bot stands down until price drops below."
                ),
            )
            return None
        if _min_ep is not None and _px > 0 and _px < float(_min_ep):
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"BUY REFUSED (min_entry_price gate): current "
                    f"price ${_px:.8f} < min_entry_price "
                    f"${float(_min_ep):.8f}. Operator-set floor. "
                    f"Bot stands down until price rises above."
                ),
            )
            return None

        try:
            _open = await self.exchange.get_open_orders(self.config.symbol)
        except Exception as _oo_exc:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"P0b BUY REFUSED (fail-closed): "
                    f"get_open_orders raised {type(_oo_exc).__name__}: "
                    f"{_oo_exc}. Cannot verify absence of stacked "
                    f"orders. Refusing."
                ),
            )
            return None
        try:
            from ...exchange.base import OrderSide as _OS

            _open_buys = [
                o
                for o in (_open or [])
                if getattr(o, "side", None) == _OS.BUY
                and getattr(o, "symbol", None) == self.config.symbol
            ]
        except Exception:
            _open_buys = [
                o
                for o in (_open or [])
                if getattr(o, "symbol", None) == self.config.symbol
            ]
        if _open_buys:
            _ids = ", ".join(str(getattr(o, "id", "?")) for o in _open_buys[:3])
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"P0b STACKED BUY REFUSED: {len(_open_buys)} open "
                    f"BUY order(s) already on exchange for "
                    f"{self.config.symbol} (ids: {_ids}). "
                    f"Refusing to place a second BUY on top. "
                    f"Wait for existing order(s) to fill or cancel."
                ),
            )
            return None

        _ctx = trace_context or {}
        _path = _ctx.get("path", "unspecified")
        _cap_pct = float(getattr(self.config, "max_target_growth_pct", 1.0))
        _anchor = float(getattr(self, "_anchor_target_balance", self._target_balance))
        _per_cycle_growth_budget = _anchor * (_cap_pct / 100.0)

        _fresh_units, _refuse_reason_msg = await self._verify_buy_safe_or_refuse(
            path=_path
        )
        if _refuse_reason_msg:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=_refuse_reason_msg)
            logger.warning("Bot %s %s", self.bot_id, _refuse_reason_msg)
            return None

        _qrate_buy = float(self._quote_to_usd or 1.0)
        _ceiling_units = sum(float(lot.get("units", 0) or 0) for lot in self._main_lots)
        _current_position_usd = _ceiling_units * price * _qrate_buy
        _projected_position_usd = _current_position_usd + cost

        _target_delta_usd = float(self._target_balance) - _current_position_usd
        _slippage_tol_pct = 0.5
        if _path == "zero_balance_initial_entry":
            _path_budget = float(self._target_balance)
        elif _path in ("fold_rebuy", "manual_tranche_fire"):
            _path_budget = float(cost)
        elif _path == "hedge_replenish":
            try:
                _hedge_limit = float(getattr(self, "_hedge_bal", 0.0) or 0.0)
            except (TypeError, ValueError):
                _hedge_limit = 0.0
            _path_budget = _hedge_limit
        else:
            _path_budget = max(0.0, _target_delta_usd) + _per_cycle_growth_budget
            logger.warning(
                "Bot %s _execute_buy: unspecified path used the conservative "
                "fold_rebuy-equivalent budget (cost=$%.2f, budget=$%.2f). "
                "If this is a new legitimate path, enumerate it in the "
                "Layer 1 dispatch.",
                self.bot_id,
                cost,
                _path_budget,
            )

        _budget_with_tol = _path_budget * (1.0 + _slippage_tol_pct / 100.0)
        if cost > _budget_with_tol:
            _reason = (
                f"MEM-251 v2 LAYER 1 BREACH — buy REFUSED. "
                f"Path={_path}. Current position=${_current_position_usd:.2f} "
                f"({_fresh_units:.8f} {self.config.target_asset} @ "
                f"${price:.8f}). Target=${self._target_balance:.2f}, "
                f"Target Delta=${_target_delta_usd:+.2f}. "
                f"Path budget=${_path_budget:.2f} (+{_slippage_tol_pct:.2f}% "
                f"tol → ${_budget_with_tol:.2f}). Proposed cost ${cost:.2f} "
                f"exceeds budget. No buy may exceed its path's Target-Delta "
                f"+ per-cycle-growth allowance."
            )
            self._bus.emit("bot.log", bot_id=self.bot_id, message=_reason)
            logger.warning("Bot %s %s", self.bot_id, _reason)
            return None

        if getattr(self.config, "position_ceiling_enabled", False):
            try:
                _smart_ceiling_usd = self.position_ceiling_usd
            except Exception:
                _smart_ceiling_usd = None
            if _smart_ceiling_usd is not None and _smart_ceiling_usd > 0:
                if _projected_position_usd > _smart_ceiling_usd:
                    _reason = (
                        f"MEM-251 v2 LAYER 2 (POSITION CEILING) BREACH — "
                        f"buy REFUSED. Path={_path}. Projected position "
                        f"${_projected_position_usd:.2f} > Position Ceiling "
                        f"${_smart_ceiling_usd:.2f} (anchor "
                        f"${_anchor:.2f} × Ceiling Multiple "
                        f"{self.config.position_ceiling_multiple}). "
                        f"Bot has reached configured maturity — no further "
                        f"acquisition until detonation harvests grown "
                        f"position on next bullish higher-TF vote."
                    )
                    self._bus.emit("bot.log", bot_id=self.bot_id, message=_reason)
                    logger.warning("Bot %s %s", self.bot_id, _reason)
                    return None

        try:
            amount = fold_units(cost, price, FRACTIONAL_UNITS)
            if _qrate_buy > 0 and abs(_qrate_buy - 1.0) > 1e-9:
                amount = amount / _qrate_buy

            from ...core.execution_discipline import verify_hit as _vh

            vh_fp, vh_status, vh_samples = _vh(
                price, "buy", symbol=self.config.target_asset
            )
            self.stats.verify_samples += vh_samples
            if vh_fp is None:
                self.stats.verify_canceled += 1
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=f"BUY CANCELED (R55 VH): slippage would "
                    f"exceed {self.config.target_asset} class "
                    f"tolerance @ ${price:.8f}",
                )
                logger.info(
                    "Bot %s VH-canceled buy of %.6f at %.4f", self.bot_id, amount, price
                )
                return
            if vh_status == "clean":
                self.stats.verify_clean += 1
            else:
                self.stats.verify_adjusted += 1
                amount = fold_units(cost, vh_fp, FRACTIONAL_UNITS)
                if _qrate_buy > 0 and abs(_qrate_buy - 1.0) > 1e-9:
                    amount = amount / _qrate_buy

            if self._invisible:
                ot = OrderType.MARKET
                exec_price = None
            else:
                ot = OrderType.LIMIT
                exec_price = vh_fp

            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"BUY signal: {amount:.6f} @ ${price:.8f} "
                f"(VH:{vh_status}, confidence="
                f"{summary.consensus_confidence:.2f}, "
                f"{'MARKET' if self._invisible else 'LIMIT'})",
            )
            self._emit_trade_notification(
                "FOLD", "SENT", f"{amount:.6f} @ ${price:.8f}"
            )

            order = await self.guarded_place_order(
                symbol=self.config.symbol,
                side=OrderSide.BUY,
                order_type=ot,
                amount=amount,
                price=exec_price,
            )

            if order is None:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"BUY ABORTED: exchange/guard returned no order for "
                        f"{amount:.6f} {self.config.target_asset} @ "
                        f"${price:.8f}. No state update. Caller must not "
                        f"treat this as success."
                    ),
                )
                logger.warning(
                    "Bot %s buy aborted (order None) for %.6f at %.4f",
                    self.bot_id,
                    amount,
                    price,
                )
                try:
                    await self._reconcile_holdings(reason="post_failure")
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "_execute_buy",
                        type(_sup).__name__,
                        _sup,
                    )
                return None

            self._current_holdings += amount
            self.stats.total_buys += 1
            self.stats.total_trades += 1

            actual_fill = getattr(order, "average", None) or getattr(
                order, "price", None
            )
            if not actual_fill or actual_fill <= 0:
                actual_fill = price
            # The only point on the FOLD and ENTRY paths holding the settled order.
            self._last_fill_venue_fee = self._venue_fee_record(
                order, amount, actual_fill
            )
            await self._settle_venue_fee(order, amount, actual_fill)
            slippage_pct = ((actual_fill - price) / price * 100.0) if price > 0 else 0.0

            self.stats.trade_volume += amount * actual_fill
            self.stats.last_trade_time = time.time()

            try:
                _qrate = float(getattr(self, "_quote_to_usd", 1.0) or 1.0)
                _fill_usd = float(amount) * float(actual_fill) * _qrate
                self.stats.ytd_folded_usd = (
                    float(getattr(self.stats, "ytd_folded_usd", 0.0) or 0.0) + _fill_usd
                )
            except (TypeError, ValueError) as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_buy",
                    type(_sup).__name__,
                    _sup,
                )

            self._memorised_trades.append(
                MemorisedTrade(
                    timestamp=time.time(),
                    side="buy",
                    price=actual_fill,
                    amount=amount,
                    voting_summary=summary,
                )
            )
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=f"BUY FILLED: {amount:.6f} {self.config.target_asset} "
                f"@ ${actual_fill:.8f} "
                f"(intended ${price:.8f}, slip {slippage_pct:+.3f}%, "
                f"holdings now {self._current_holdings:.6f})",
            )
            self._emit_trade_notification(
                "FOLD", "FILLED", f"{amount:.6f} @ ${actual_fill:.8f}"
            )

            await self._spawn_stack_from_fold(
                fold_price=actual_fill, fold_size=amount, summary=summary, path=_path
            )
            return actual_fill
        except Exception as exc:
            self._bus.emit("bot.log", bot_id=self.bot_id, message=f"BUY FAILED: {exc}")
            logger.error("Bot %s buy failed: %s", self.bot_id, exc)
            try:
                await self._reconcile_holdings(reason="post_failure")
            except Exception as _sup:
                logger.debug(
                    "suppressed in %s: %s: %s",
                    "_execute_buy",
                    type(_sup).__name__,
                    _sup,
                )
            return None
