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

from ...core.emit_contracts import FILL_BUY, FILL_SELL
from ...exchange.base import OrderSide, OrderType
from ..container.config import target_growth_pct
from ..otd_math import (
    ROUND_TRIP_FEES,
    DistanceSettings,
    DistanceSettingUnreadable,
    distance_settings,
)
from ..target_bands import manual_fire_dust_band
from ..ta_engine import VotingSummary
from ..wallet_reservations import get_wallet_reservations, wallet_key
from .sizing import (
    FRACTIONAL_UNITS,
    discharge_gain_usd,
    fold_tranche_records,
    fold_units,
    held_wire_usd,
    opposing_event_id,
    priced_usd,
    rebalance_held_usd,
    routed_share_pct,
    sale_proceeds_usd,
    scrum_units,
    spend_less_unsettled_usd,
    target_delta_usd,
    tranche_rebuy_price,
    wallet_capped_spend_usd,
)

logger = logging.getLogger("acervator.scrumming")

# A fraction of the price a refusal was taken at, not a percent.
REFUSAL_HOLD_MOVE_FRACTION: float = 0.001


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


def venue_fee_record(order: Any, units: Any, price: Any) -> Optional[SettledFillFee]:
    """Build a ``SettledFillFee`` from ``order.fee`` and ``order.fee_currency``.

    Returns None when ``units`` or ``price`` is not a number, and computes no fee of
    its own.
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


def fill_fee_fields(
    record: Optional[SettledFillFee], fill_price: Any, quote: str, rate: Any
) -> dict:
    """The fee field of one ``SettledFill``: ``fee_usd`` for a fee ``record`` charged in
    ``quote`` at ``fill_price``, priced at ``rate`` dollars a unit, otherwise
    ``fee_refusal`` naming why.
    """
    try:
        _price = float(fill_price)
    except (TypeError, ValueError):
        return {"fee_refusal": "the fill price is not a number"}
    if record is None:
        return {"fee_refusal": "no settled order was held for this fill"}
    if not record.reported:
        return {"fee_refusal": "the venue reported no fee"}
    if not math.isclose(record.price, _price, rel_tol=1e-9, abs_tol=1e-12):
        return {"fee_refusal": "the reported fee belongs to a different fill"}
    if not record.currency:
        return {"fee_refusal": "the venue named no fee currency"}
    if quote and record.currency != quote:
        return {
            "fee_refusal": (
                f"the venue charged the fee in {record.currency}, not the "
                f"{quote} this fill is priced in"
            )
        }
    _rate = float(rate or 0.0)
    if _rate <= 0.0:
        return {"fee_refusal": f"no {quote or 'quote'}-to-USD rate is cached"}
    _fee_usd = record.fee_amount * _rate
    if not math.isfinite(_fee_usd) or _fee_usd <= 0.0:
        return {"fee_refusal": "the reported fee converts to nothing in USD"}
    return {"fee_usd": _fee_usd}


def venue_fee_pct(
    record: Optional[SettledFillFee], fill_price: Any, quote: str, base: str = ""
) -> Optional[float]:
    """The fee ``record`` reports as a percentage of its fill, charged in ``quote`` or ``base``, else None."""
    if record is None or not record.reported or not record.currency:
        return None
    try:
        _price = float(fill_price)
    except (TypeError, ValueError):
        return None
    if not math.isclose(record.price, _price, rel_tol=1e-9, abs_tol=1e-12):
        return None
    if quote and record.currency == quote:
        _charged_on = record.units * record.price
    elif base and record.currency == base:
        _charged_on = record.units
    else:
        return None
    if not math.isfinite(_charged_on) or _charged_on <= 0.0:
        return None
    _pct = record.fee_amount / _charged_on * 100.0
    if not math.isfinite(_pct) or not 0.0 < _pct < 100.0:
        return None
    return _pct


class ExecutionEngineMixin:
    """Place orders at the venue and book what the venue reports back.

    ``_execute_sell``, ``_execute_buy``, ``_execute_detonation`` and
    ``_execute_manual_rebalance`` each run after a tick has chosen the trade.
    """

    # ScrummingBot supplies these at runtime; the annotations create no attributes.
    _anchor_target_balance: float
    _announce_fill: Callable[..., None]
    _apply_fold_target_growth: Callable[..., Any]
    _apply_scrum_fold_pct: Callable[..., None]
    _bound_new_fold_tranches: Callable[..., Any]
    _bus: Any
    _cb_last_candle_ts: float
    _combine_fold_tranches_within_distance: Callable[..., Any]
    _count_trade_volume: Callable[..., float]
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
    _hold_resting_order: Callable[..., Any]
    _hyst_armed_fold_side: bool
    _hyst_armed_scrum_side: bool
    _hyst_ref_fold_side: float
    _hyst_ref_scrum_side: float
    _initialised: Any
    _invisible: bool
    _land_pending_wire_credits: Callable[..., float]
    _last_settled_order: Any
    _last_trade_price: float
    _last_trade_side: Optional[str]
    _main_lots: list[dict]
    _manual_fire_pending: bool
    _open_stack_from_scrum: Callable[..., Any]
    _order_asked_units: Callable[..., float]
    _preview_fold_growth: Callable[..., Any]
    _quote_to_usd: float
    _read_settled_order: Callable[..., Any]
    _reconcile_holdings: Callable[..., Any]
    _record_audited_venue_units: Callable[..., float]
    _record_venue_units_after_fill: Callable[..., float]
    _refresh_quote_to_usd: Callable[..., Any]
    _reset_opposing_hysteresis_after_fill: Callable[..., None]
    _resting_order_for: Callable[..., Any]
    _return_wire_credits_to_pool: Callable[..., float]
    _route_scrum_proceeds_via_wires: Callable[..., Any]
    _run_booker: Callable[..., Any]
    _spawn_stack_from_fold: Callable[..., Any]
    _standing_surplus_usd: float
    _target_balance: Any
    _top_up_remnant_fold_tranches: Callable[..., Any]
    _tranches_closed_lifetime: int
    _tranches_created_lifetime: int
    _tranches_discarded_lifetime: Any
    _venue_claimable_units: Callable[..., Any]
    bot_id: Any
    config: Any
    exchange: Any
    guarded_place_order: Callable[..., Any]
    note_scrum_retention_usd: Callable[..., None]
    refresh_priced_figures_after_fill: Callable[..., Any]
    reset_swos_cycle: Callable[..., None]
    stats: Any

    # Class-level defaults; every write lands on the instance, never on the class.
    _last_sell_venue_fee: Optional["SettledFillFee"] = None
    _last_fill_venue_fee: Optional["SettledFillFee"] = None

    # The highest venue_fee_pct any of this bot's fills reported; _note_venue_fee_pct writes it.
    highest_venue_fee_pct: float = 0.0

    # The units the venue reported sold on the last _execute_sell, for the
    # callers that take those units off _main_lots.
    _last_sell_filled_units: float = 0.0

    # The units the venue reported bought on the last _execute_buy, for the
    # callers that add those units to _main_lots.
    _last_buy_filled_units: float = 0.0

    # One get_order per fill whose placed order reported no fee, and none otherwise.
    _VENUE_FEE_REREADS = 1
    _VENUE_FEE_REREAD_DELAY_S = 0.2

    # One entry per refusal reason, each holding the candle and price it was taken at.
    _refusal_holds: Optional[dict] = None

    _SETTLED_FILL_DEFAULT_LABEL = "MANUAL FIRE"
    _SETTLED_FILL_LABELS = frozenset(
        (
            "MANUAL FIRE",
            "SCRUM",
            "DIST",
            "STACK",
            "FOLD",
            "DETONATION",
            "SELF-DESTRUCT",
            "EXPIRY CLOSE",
        )
    )

    def _refusal_is_new(self, reason: str, price: float) -> bool:
        """Record a refusal under ``reason`` and say whether it is a new decision.

        Every refusal site in the trade path and in ``tick``'s verdict chain
        calls this to decide whether to announce itself. The refusal itself
        always stands and only the announcement is held. A refusal is new on
        the first call for ``reason``, on a different candle from
        ``_cb_last_candle_ts``, when no candle is known, and once ``price``
        differs by ``REFUSAL_HOLD_MOVE_FRACTION`` from the price the previous
        call for ``reason`` carried. ``_refusal_holds`` takes the new
        ``price`` on every call, whichever answer it gives.
        """
        try:
            px = float(price)
        except (TypeError, ValueError):
            return True

        try:
            bar = float(getattr(self, "_cb_last_candle_ts", 0.0) or 0.0)
        except (TypeError, ValueError):
            bar = 0.0

        holds = self._refusal_holds
        if holds is None:
            holds = {}
            self._refusal_holds = holds

        held = holds.get(reason)
        holds[reason] = (bar, px)

        if held is None or bar <= 0.0:
            return True
        held_bar, held_px = held
        if held_bar != bar or held_px <= 0.0 or px <= 0.0:
            return True
        return abs(px - held_px) / held_px >= REFUSAL_HOLD_MOVE_FRACTION

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
        """Re-read a just-placed ``order`` until the venue reports a fill, and
        answer ``(fill_amount, fill_price, is_real)`` where ``fill_amount`` is
        the venue's own filled count, zero when it reported none.

        Calls ``_record_venue_fee`` on whichever order object settled, clears
        both venue-fee records when it books an estimate, and falls back to
        ``quoted_price`` for the price alone.
        """
        self._last_sell_venue_fee = None
        self._last_fill_venue_fee = None

        amt, px, settled, _last = await self._read_settled_order(order, symbol)
        if settled is not None:
            self._record_venue_fee(settled, amt, px)
            await self._settle_venue_fee(settled, amt, px)
            return amt, px, True

        order_id = str(getattr(order, "id", "") or "")
        est_amt = amt
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
                f"the exchange until the next reconcile. The unit count is "
                f"the exchange's own, out of "
                f"{float(requested_amount or 0.0):.6f} asked, so a zero "
                f"books nothing against the position."
            ),
        )
        return est_amt, est_px, False

    def _note_resting_fee(
        self,
        record: dict,
        units: float,
        price: float,
        fee: float,
        fee_currency: str,
    ) -> None:
        """Hold the fee the venue reported for one later piece on
        ``_last_fill_venue_fee``, and on ``_last_sell_venue_fee`` for a sell.
        """
        self._last_fill_venue_fee = SettledFillFee(
            units=float(units),
            price=float(price),
            fee_amount=float(fee),
            currency=str(fee_currency or "").strip().upper(),
            reported=float(fee) > 0.0,
        )
        self._last_sell_venue_fee = (
            self._last_fill_venue_fee if record.get("side") == "sell" else None
        )

    async def _book_sale(
        self,
        units: float,
        fill_price: float,
        asked_units: float,
        intended: float,
        label: str,
        confidence: float,
    ) -> float:
        """Take one settled piece of a sale off ``_current_holdings``, and return its fill
        price.

        ``refresh_priced_figures_after_fill`` takes one venue reading for the row.
        """
        self._last_sell_filled_units = units
        self._current_holdings = max(0.0, self._current_holdings - units)

        if not fill_price or fill_price <= 0:
            fill_price = intended
        slippage_pct = (
            ((fill_price - intended) / intended * 100.0) if intended > 0 else 0.0
        )

        self._count_trade_volume(units, fill_price)

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=f"SELL FILLED: {units:.6f} "
            f"{self.config.target_asset} of {asked_units:.6f} asked "
            f"@ ${fill_price:.8f} "
            f"(intended ${intended:.8f}, slip {slippage_pct:+.3f}%)",
        )
        self._emit_trade_notification(
            "SCRUM", "FILLED", f"{units:.6f} @ ${fill_price:.8f}"
        )
        logger.info(
            "Bot %s sold %.6f at %.4f (intended %.4f, slip %+.3f%%, confidence=%.2f)",
            self.bot_id,
            units,
            fill_price,
            intended,
            slippage_pct,
            confidence,
        )
        # The fill moved _current_holdings above and not the audited venue
        # count. One read puts both priced figures on this fill. Guarded
        # here too, so no refresh can lose a sale the venue already made.
        try:
            await self.refresh_priced_figures_after_fill(reason=label.lower())
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_book_sale",
                type(_sup).__name__,
                _sup,
            )
        return fill_price

    async def _book_sale_fill(
        self,
        units: float,
        fill_price: float,
        asked: float,
        first: bool,
        *,
        label: str,
        intended: float,
        asked_units: float,
        confidence: float,
        path_booker: str = "",
        path_context: Optional[dict] = None,
        sources: Optional[list] = None,
    ) -> float:
        """Book one later piece of a held sale through ``_book_sale``, then through the
        method ``path_booker`` names.
        """
        fill_price = await self._book_sale(
            units, fill_price, asked_units, intended, label, confidence
        )
        await self._run_booker(
            path_booker, units, fill_price, asked, first, path_context, sources
        )
        return fill_price

    async def _book_purchase(
        self,
        units: float,
        fill_price: float,
        asked_units: float,
        intended: float,
        path: str,
        venue_before: Optional[float],
        summary: Any,
    ) -> float:
        """Add one settled piece of a buy to ``_current_holdings``, and return its fill
        price.

        ``venue_before`` is the venue reading taken before the order, None for a later
        piece, which moves ``_audited_venue_units`` by ``units``.
        """
        if not fill_price or fill_price <= 0:
            fill_price = intended

        self._last_buy_filled_units = units
        self._current_holdings += units
        # _fresh_units is the pre-fill venue reading _verify_buy_safe_or_refuse
        # already took, so the row's venue figure moves with no second fetch.
        if venue_before is not None:
            self._record_audited_venue_units(venue_before + units)
        else:
            self._record_venue_units_after_fill(units)

        slippage_pct = (
            ((fill_price - intended) / intended * 100.0) if intended > 0 else 0.0
        )

        self._count_trade_volume(units, fill_price)

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=f"BUY FILLED: {units:.6f} "
            f"{self.config.target_asset} of {asked_units:.6f} asked "
            f"@ ${fill_price:.8f} "
            f"(intended ${intended:.8f}, slip {slippage_pct:+.3f}%, "
            f"holdings now {self._current_holdings:.6f})",
        )
        self._emit_trade_notification(
            "FOLD", "FILLED", f"{units:.6f} @ ${fill_price:.8f}"
        )

        await self._spawn_stack_from_fold(
            fold_price=fill_price,
            fold_size=units,
            summary=summary,
            path=path,
        )
        return fill_price

    async def _book_purchase_fill(
        self,
        units: float,
        fill_price: float,
        asked: float,
        first: bool,
        *,
        path: str,
        intended: float,
        asked_units: float,
        confidence: float,
        net_score: float,
        path_booker: str = "",
        path_context: Optional[dict] = None,
        sources: Optional[list] = None,
    ) -> float:
        """Book one later piece of a held buy through ``_book_purchase``, then through
        the method ``path_booker`` names.
        """
        fill_price = await self._book_purchase(
            units,
            fill_price,
            asked_units,
            intended,
            path,
            None,
            VotingSummary(net_score=net_score, consensus_confidence=confidence),
        )
        await self._run_booker(
            path_booker, units, fill_price, asked, first, path_context, sources
        )
        return fill_price

    async def _book_spread_pct(self, symbol: str) -> Optional[float]:
        """Read ``symbol``'s book off the venue and return its bid-ask gap.

        Returns None when ``get_orderbook`` raises, exceeds
        ``SYNC_CALL_TIMEOUT_SEC`` or serves an empty side, so a slow or
        refusing venue leaves the order on the path it takes today.
        """
        try:
            from ...core.execution_discipline import book_spread_pct
            from ...exchange.ccxt_connector import SYNC_CALL_TIMEOUT_SEC

            book = await asyncio.wait_for(
                self.exchange.get_orderbook(symbol),
                timeout=SYNC_CALL_TIMEOUT_SEC,
            )
            bids = list(getattr(book, "bids", None) or [])
            asks = list(getattr(book, "asks", None) or [])
            if not bids or not asks:
                return None
            return book_spread_pct(bids[0][0], asks[0][0])
        except Exception as _book_exc:  # noqa: BLE001
            logger.debug(
                "Bot %s book read for %s failed: %s: %s",
                self.bot_id,
                symbol,
                type(_book_exc).__name__,
                _book_exc,
            )
            return None

    def _venue_quote_currency(self) -> str:
        """The currency a sale is credited in, read off the symbol through
        ``market_rules_store.quote_currency``.

        A contract symbol joins the leg it settles on and its expiry date to
        that currency, and the venue reports its fee in the currency alone.
        """
        from ...exchange.market_rules_store import quote_currency

        _sym = str(getattr(self.config, "symbol", "") or "")
        return quote_currency(_sym).strip().upper()

    def _record_venue_fee(self, order, units: float, price: float) -> None:
        """Store the fee the venue reported for a just-settled fill.

        Writes ``_last_fill_venue_fee`` on either side, writes
        ``_last_sell_venue_fee`` for a sell only, reads ``order.fee`` and
        ``order.fee_currency`` only, and never raises.
        """
        self._last_fill_venue_fee = venue_fee_record(order, units, price)
        _side = getattr(order, "side", None)
        _side_txt = str(getattr(_side, "value", _side) or "").lower()
        if _side_txt != "sell":
            self._last_sell_venue_fee = None
            return
        self._last_sell_venue_fee = self._last_fill_venue_fee

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
            _probe = venue_fee_record(_settled, units, price)
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

    def _note_venue_fee_pct(
        self, record: Optional[SettledFillFee], fill_price: float
    ) -> None:
        """Raise ``highest_venue_fee_pct`` to the ``venue_fee_pct`` of ``record`` and log each rise."""
        charged = venue_fee_pct(
            record,
            fill_price,
            self._venue_quote_currency(),
            str(getattr(self.config, "target_asset", "") or "").strip().upper(),
        )
        if charged is None:
            return
        held = self.highest_venue_fee_pct
        self.highest_venue_fee_pct = max(held, charged)
        if self.highest_venue_fee_pct == held:
            return
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"VENUE FEE: the venue charged {charged:.4f}% on this fill, the "
                f"highest it has reported for this bot. The Minimum Opposing "
                f"Trade Distance reads the larger of this fee and the Trading "
                f"Fee setting."
            ),
        )

    def opposing_distance_settings(self) -> DistanceSettings:
        """``distance_settings`` of ``config`` at ``highest_venue_fee_pct``, the one reading every distance check takes."""
        return distance_settings(self.config, self.highest_venue_fee_pct)

    def opposing_trade_distance_pct(self, band: Any = None) -> float:
        """The Minimum Opposing Trade Distance at ``band``, a percentage, read through ``opposing_distance_settings``."""
        return self.opposing_distance_settings().distance_at_band(band)

    def _pivot_distance_text(self) -> str:
        """``opposing_trade_distance_pct`` as a pivot line prints it, or the ``DistanceSettingUnreadable`` it raised."""
        try:
            return f"{self.opposing_trade_distance_pct():.2f}%"
        except DistanceSettingUnreadable as unread:
            return f"a distance that cannot be read ({unread})"

    def _refuse_unreadable_distance(
        self, unread: DistanceSettingUnreadable, side: str, price: float
    ) -> None:
        """Log ``unread`` once per held refusal: ``side`` refuses while a distance setting holds no number."""
        if not self._refusal_is_new(f"distance_unreadable_{side.lower()}", price):
            return
        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"{side} REFUSED (opposing distance unreadable): {unread}, so "
                f"the Minimum Opposing Trade Distance cannot be read. Nothing "
                f"trades on it until the setting holds a number."
            ),
        )
        self._emit_trade_notification(
            side, "REFUSED", f"{unread.setting} {unread.reason}"
        )

    def _fill_fee_fields(self, fill_price: float) -> dict:
        """The ``SettledFill`` fee field for the fill that settled at ``fill_price``,
        read by ``fill_fee_fields`` off ``_last_fill_venue_fee``, which this consumes.

        It never reads ``config.trading_fee_pct``.
        """
        _rec = self._last_fill_venue_fee
        self._last_fill_venue_fee = None
        self._note_venue_fee_pct(_rec, fill_price)
        return fill_fee_fields(
            _rec,
            fill_price,
            self._venue_quote_currency(),
            getattr(self, "_quote_to_usd", 0.0),
        )

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
        ``manual_fire_dust_band`` is a logged no-op. Every intent, the Manual
        Fire button included, reads the venue's own ``target_asset`` balance
        before the size is decided and refuses a position the venue disputes
        by more than that band.
        """

        _INTENT_MAP = {
            "manual_button": ("MANUAL_SCRUM", "MANUAL_FOLD", True),
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

        _held = self._resting_order_for("_book_manual_sale", "_book_manual_purchase")
        if _held is not None:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE HELD: order {_held['order_id']} from an earlier "
                    f"fire still rests at the venue with "
                    f"{float(_held['asked']) - float(_held['booked']):.8f} units "
                    f"unfilled. Its fill is booked when the venue reports it, and "
                    f"no second order is sent while it rests."
                ),
            )
            return

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

        # The pre-fill venue reading every intent takes, the button included.
        _venue_units: Optional[float] = None

        # A refused press carries the words the Fire button itself shows.
        _refusal_prefix = (
            "MANUAL FIRE WILL NOT ACT"
            if caller_intent == "manual_button"
            else "AUTONOMOUS FIRE REFUSED"
        )
        _refusal_subject = (
            "manual fire" if caller_intent == "manual_button" else "autonomous fire"
        )
        # The hold rate-limits a repeating tick; one deliberate press always answers.
        _announce_every_refusal = caller_intent == "manual_button"

        try:
            _xbal = await self._get_balance(self.config.target_asset)
            _xunits = float(
                getattr(_xbal, "total", 0) or getattr(_xbal, "free", 0) or 0.0
            )
            _absent = bool(getattr(_xbal, "absent", False))
        except Exception as _xb_exc:  # noqa: BLE001
            if _announce_every_refusal or self._refusal_is_new(
                "manual_balance_unreadable", price
            ):
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"{_refusal_prefix}: could not read "
                        f"{self.config.target_asset} balance to verify the "
                        f"position ({_xb_exc}). Gates are bypassed on this "
                        f"path, so an unverified position is not traded."
                    ),
                )
            return
        if _absent:
            if _announce_every_refusal or self._refusal_is_new(
                "manual_balance_omitted", price
            ):
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"{_refusal_prefix}: exchange OMITTED "
                        f"{self.config.target_asset} from its balance "
                        f"response, so the position cannot be verified."
                    ),
                )
            return
        _venue_units = _xunits
        _xvalue = _xunits * price * _qrate
        if abs(_xvalue - current_value) > dust:
            if _announce_every_refusal or self._refusal_is_new(
                "manual_position_mismatch", price
            ):
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"{_refusal_prefix} (position mismatch): this "
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
                    "Bot %s %s refused: internal %.8f vs exchange %.8f %s",
                    self.bot_id,
                    _refusal_subject,
                    self._current_holdings,
                    _xunits,
                    self.config.target_asset,
                )
            return
        if caller_intent != "manual_button":
            if delta_usd < 0:
                _growth = float(target_growth_pct(self.config) or 0.0)
                _ceiling = float(self._target_balance) * (1.0 + _growth / 100.0)
                _prospective = _xvalue + abs(delta_usd)
                if _prospective > _ceiling + dust:
                    if not self._refusal_is_new("manual_ceiling", price):
                        return
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
            _manual_sale = {
                "label": _scrum_label,
                "operator_initiated": _operator_initiated,
                "price": float(price),
            }
            self._hold_resting_order(
                order,
                "_book_manual_sale",
                "sell",
                fill_amount,
                fill_price,
                _manual_sale,
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
            await self._book_manual_sale(
                fill_amount,
                fill_price,
                self._order_asked_units(self._last_settled_order or order, sell_amount),
                True,
                venue_units=_venue_units,
                **_manual_sale,
            )

        else:
            if await self._refuses_stacked_buy(price, _announce_every_refusal):
                return

            _floor: Optional[DistanceSettings] = None
            _unpaid: list[dict] = []
            if caller_intent != "manual_button" and self._fold_tranches:
                _best_rebuy = 0.0
                _distance_ok = False

                _unreadable_refs = 0
                _thresholds: list[float] = []
                try:
                    _floor = self.opposing_distance_settings()

                    for _t in self._fold_tranches:
                        _t_thresh = tranche_rebuy_price(_t, _floor)
                        if not math.isfinite(_t_thresh):
                            _unreadable_refs += 1
                            continue
                        _thresholds.append(_t_thresh)
                        if price > _t_thresh:
                            _unpaid.append(_t)
                    if _thresholds:
                        _best_rebuy = max(_thresholds)
                        _distance_ok = price <= _best_rebuy
                except (TypeError, ValueError, OverflowError) as _otd_exc:
                    if not self._refusal_is_new("manual_distance_unreadable", price):
                        return
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
                    if not self._refusal_is_new("manual_opposing_distance", price):
                        return
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"AUTONOMOUS FIRE REFUSED (opposing distance): at "
                            f"${price:.8f} not one of the "
                            f"{len(self._fold_tranches)} queued tranche(s) is "
                            f"eligible. The highest rebuy any of them allows "
                            f"is ${_best_rebuy:.8f} (its sale price less the "
                            f"distance and its wire share), so price must fall "
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
            elif caller_intent != "manual_button":
                try:
                    _floor = self.opposing_distance_settings()
                except DistanceSettingUnreadable:
                    _floor = None
            _fee: Optional[float] = None
            try:
                _fee = self.opposing_distance_settings().fee_pct
            except DistanceSettingUnreadable:
                _fee = None

            _denom_pre = price * _qrate
            _growth_preview = 0.0
            self._fold_preview_unreadable_refs = 0
            self._fold_preview_unreadable_units = 0
            if _denom_pre > 0:
                for _ in range(4):
                    _units_pre = ((-delta_usd) + _growth_preview) / _denom_pre
                    _g = self._preview_fold_growth(_units_pre, price, _floor, _fee)
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
            # The spend leaves unpaid tranches' dollars, wire credits and the
            # pool in the wallet.
            _paying = [
                t for t in self._fold_tranches if not any(t is u for u in _unpaid)
            ]
            _unsettled, _held_back = rebalance_held_usd(
                _paying,
                _unpaid,
                time.time(),
                _settlement,
                getattr(self, "_pending_wire_credits", 0.0),
            )
            buy_usd = spend_less_unsettled_usd(
                wallet_capped_spend_usd(buy_usd_target, usd_balance),
                usd_balance,
                _unsettled + _held_back,
            )
            if buy_usd <= 0:
                err_tail = f" (fetch error: {_bal_err})" if _bal_err else ""
                unsettled_tail = (
                    f", of which ${_unsettled:.4f} is cash the venue has not "
                    f"settled at {_settlement} day(s)"
                    if _unsettled > 1e-9
                    else ""
                ) + (
                    f", of which ${_held_back:.4f} is held for tranches above "
                    f"their own floor and for wire credits"
                    if _held_back > 1e-9
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
            _manual_purchase = {
                "label": _fold_label,
                "operator_initiated": _operator_initiated,
                "price": float(price),
                "floor_distance": (
                    [_floor.interval_pct, _floor.fee_pct, _floor.band_travel_pct]
                    if _floor is not None
                    else None
                ),
                "fee_pct": _fee,
            }
            self._hold_resting_order(
                order,
                "_book_manual_purchase",
                "buy",
                fill_amount,
                fill_price,
                _manual_purchase,
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
            await self._book_manual_purchase(
                fill_amount,
                fill_price,
                self._order_asked_units(self._last_settled_order or order, buy_amount),
                True,
                venue_units=_venue_units,
                **_manual_purchase,
            )

    async def _book_manual_sale(
        self,
        units: float,
        fill_price: float,
        asked: float,
        _first: bool,
        *,
        label: str,
        operator_initiated: bool,
        price: float,
        venue_units: Optional[float] = None,
    ) -> None:
        """Book one settled piece of a Manual Fire or cartridge sale as fold
        tranches, and announce it.

        ``venue_units`` is the venue reading taken before the order, None for a later
        piece, which moves ``_audited_venue_units`` by ``units``.
        """
        fill_amount = units
        if fill_price <= 0:
            fill_price = price

        fill_usd = self._settled_sale_proceeds(fill_amount, fill_price, label=label)
        self._current_holdings = max(0.0, self._current_holdings - fill_amount)
        if venue_units is not None:
            self._record_audited_venue_units(venue_units - fill_amount)
        else:
            self._record_venue_units_after_fill(-fill_amount)

        _manual_routed_total = self._route_scrum_proceeds_via_wires(
            scrum_usd=fill_usd, sell_fill=fill_price, label="manual_scrum"
        )
        _manual_wire_share = routed_share_pct(fill_usd, _manual_routed_total)
        fill_usd = max(0.0, fill_usd - _manual_routed_total)

        self._main_lots.sort(key=lambda l: l["initial_buy_price"], reverse=True)
        _manual_tranche_count_before = len(self._fold_tranches)
        _manual_event_ts = time.time()
        _manual_records, _manual_unqueued = fold_tranche_records(
            self._main_lots,
            fill_price,
            fill_amount,
            fill_usd,
            opposing_event_id(label, _manual_event_ts),
            _manual_event_ts,
            _manual_wire_share,
        )
        for _record in _manual_records:
            _record["operator_initiated"] = operator_initiated
        self._fold_tranches.extend(_manual_records)
        self._tranches_created_lifetime += len(_manual_records)
        new_tranches_count = len(_manual_records)
        if _manual_unqueued > 1e-12:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"FOLD ALIGNMENT SHORT: this sale sold "
                    f"{fill_amount:.8f} units and the lot book covered "
                    f"only {fill_amount - _manual_unqueued:.8f}. "
                    f"{_manual_unqueued:.8f} units are queued against no "
                    f"tranche and will not be bought back."
                ),
            )

        # Returns how many tranches the merge removed.
        new_tranches_count -= self._bound_new_fold_tranches(
            _manual_tranche_count_before
        )

        # Must precede the _fold_queue_usd sum below.
        self._apply_scrum_fold_pct(_manual_tranche_count_before, fill_usd, fill_amount)

        _bb_last = getattr(self, "_last_bb", None)
        _merged_n, _ = self._top_up_remnant_fold_tranches(
            _manual_tranche_count_before,
            float(getattr(_bb_last, "lower", 0.0) or 0.0),
            float(getattr(_bb_last, "upper", 0.0) or 0.0),
        )
        new_tranches_count -= _merged_n
        _combined_n, _ = self._combine_fold_tranches_within_distance()
        new_tranches_count = max(0, new_tranches_count - _combined_n)

        self._land_pending_wire_credits()

        self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)
        self._count_trade_volume(fill_amount, fill_price)

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
        self._emit_voting_panel_snapshot_at_fire(
            side="SELL", trade_action=str(label or "MANUAL_SCRUM")
        )
        self._emit_gate_decision_at_fire(
            side="SELL", trade_action=str(label or "MANUAL_SCRUM")
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
                    "usd_captured": float(fill_usd) * float(self._quote_to_usd or 1.0),
                    "operator_initiated": operator_initiated,
                    "manual_kind": label,
                },
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_book_manual_sale",
                type(_sup).__name__,
                _sup,
            )
        _fill_usd_true = float(fill_usd) * float(self._quote_to_usd or 1.0)
        self.stats.total_scrummed_usd += _fill_usd_true
        self.note_scrum_retention_usd(_fill_usd_true)
        self._last_trade_side = "SCRUM"
        self._last_trade_price = fill_price
        self._reset_opposing_hysteresis_after_fill()
        self._announce_fill(
            kind=label,
            side=FILL_SELL,
            units=fill_amount,
            price=fill_price,
            usd=fill_usd,
            profit=0.0,
            operator_initiated=operator_initiated,
            fee=self._fill_fee_fields(fill_price),
        )

    async def _book_manual_purchase(
        self,
        units: float,
        fill_price: float,
        asked: float,
        _first: bool,
        *,
        label: str,
        operator_initiated: bool,
        price: float,
        venue_units: Optional[float] = None,
        floor_distance: Optional[list] = None,
        fee_pct: Optional[float] = None,
    ) -> None:
        """Book one settled piece of a Manual Fire or cartridge buy against the
        queued tranches, and announce it.

        ``venue_units`` is the venue reading taken before the order, None for a later
        piece, which moves ``_audited_venue_units`` by ``units``. With
        ``floor_distance``, a tranche whose ``tranche_rebuy_price`` sits under
        ``fill_price`` stays unpaid. A tranche pays its units from its own sale
        dollars, and one that ends returns its wire credit to the pool.
        """
        fill_amount = units
        if fill_price <= 0:
            fill_price = price
        _floor = DistanceSettings(*floor_distance) if floor_distance else None

        _manual_fold_accum_profit = 0.0
        if self._fold_tranches:
            remaining = fill_amount
            consumed = []
            for t in self._fold_discharge_order():
                if remaining <= 1e-12:
                    break
                if _floor is not None and fill_price > tranche_rebuy_price(t, _floor):
                    continue
                # _fold_discharge_order yields finite units.
                t_units = float(t.get("units", 0.0) or 0.0)
                take = min(t_units, remaining)
                if take <= 1e-12:
                    continue
                _manual_fold_accum_profit += discharge_gain_usd(
                    t, take, fill_price, fee_pct
                )
                self._main_lots.append(
                    {
                        "units": take,
                        "initial_buy_price": t.get("initial_buy_price", fill_price),
                        "operator_initiated": operator_initiated,
                    }
                )
                _credit = held_wire_usd(t)
                _t_usd = float(t.get("usd", 0.0) or 0.0)
                t["units"] = t_units - take
                if t_units > 0:
                    t["usd"] = _credit + (_t_usd - _credit) * (t["units"] / t_units)
                remaining -= take
                if t["units"] <= 1e-12:
                    consumed.append(t)

            for t in consumed:
                self._return_wire_credits_to_pool(t)
                self._fold_tranches.remove(t)
            if consumed:
                try:
                    self._tranches_closed_lifetime = int(
                        getattr(self, "_tranches_closed_lifetime", 0) or 0
                    ) + len(consumed)
                except Exception as _sup:
                    logger.debug(
                        "suppressed in %s: %s: %s",
                        "_book_manual_purchase",
                        type(_sup).__name__,
                        _sup,
                    )

            if remaining > 1e-12:
                self._main_lots.append(
                    {
                        "units": remaining,
                        "initial_buy_price": fill_price,
                        "operator_initiated": operator_initiated,
                    }
                )

            self._fold_queue_usd = sum(t["usd"] for t in self._fold_tranches)

            if _floor is None:
                msg = (
                    f"MANUAL FIRE FOLD FILLED: {fill_amount:.6f} @ "
                    f"${fill_price:.8f}. Discharged "
                    f"{len(consumed)} tranche(s) bypassing price-floor "
                    f"gates (operator override)."
                )
            else:
                _held_above = sum(
                    1
                    for t in self._fold_tranches
                    if fill_price > tranche_rebuy_price(t, _floor)
                )
                msg = (
                    f"MANUAL FIRE FOLD FILLED: {fill_amount:.6f} @ "
                    f"${fill_price:.8f}. Discharged {len(consumed)} tranche(s), "
                    f"each at or under its own sale price less the distance and "
                    f"its wire share; {_held_above} above that stay queued unpaid."
                )
        else:
            self._main_lots.append(
                {
                    "units": fill_amount,
                    "initial_buy_price": fill_price,
                    "operator_initiated": operator_initiated,
                }
            )
            msg = (
                f"MANUAL FIRE FOLD FILLED: {fill_amount:.6f} @ "
                f"${fill_price:.8f}. No tranches queued; "
                f"opened new lot (operator_initiated)."
            )

        self._current_holdings += fill_amount
        if venue_units is not None:
            self._record_audited_venue_units(venue_units + fill_amount)
        else:
            self._record_venue_units_after_fill(fill_amount)
        self._count_trade_volume(fill_amount, fill_price)

        _growth_applied = self._apply_fold_target_growth(
            _manual_fold_accum_profit, source=str(label)
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
        self._emit_voting_panel_snapshot_at_fire(
            side="BUY", trade_action=str(label or "MANUAL_FOLD")
        )
        self._emit_gate_decision_at_fire(
            side="BUY", trade_action=str(label or "MANUAL_FOLD")
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
                    "operator_initiated": operator_initiated,
                    "manual_kind": label,
                },
            )
        except Exception as _sup:
            logger.debug(
                "suppressed in %s: %s: %s",
                "_book_manual_purchase",
                type(_sup).__name__,
                _sup,
            )
        self._last_trade_price = fill_price
        self._announce_fill(
            kind=label,
            side=FILL_BUY,
            units=fill_amount,
            price=fill_price,
            usd=fill_amount * fill_price,
            profit=_growth_applied,
            operator_initiated=operator_initiated,
            fee=self._fill_fee_fields(fill_price),
        )

    async def _execute_detonation(self, ticker) -> bool:
        """Sell everything above ``_anchor_target_balance`` and reset to it.

        Sizes the sale from ``_venue_claimable_units``, so the amount comes
        from the exchange balance rather than from the attributed
        ``_current_holdings``. Clears ``_fold_tranches`` and
        ``_standing_surplus_usd``, reseeds ``_main_lots`` at the fill price,
        and announces an ``AUTO_DETONATION`` fill through ``_announce_fill``.
        Returns True once the venue figure decided the harvest, and False on
        every refusal, which ``_tick_detonation`` reads as no fire.
        """
        price = getattr(ticker, "last", None)
        if not price or price <= 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message="DETONATION: no valid price; aborting.",
            )
            return False

        venue_units, refusal = await self._venue_claimable_units()
        if venue_units is None:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"DETONATION REFUSED: {refusal}. The sale is sized from "
                    f"the exchange balance, not from the "
                    f"{self._current_holdings:.8f} units attributed to this "
                    f"bot, so nothing was sold."
                ),
            )
            logger.warning(
                "Bot %s detonation refused — %s (attributed %.8f units)",
                self.bot_id,
                refusal,
                self._current_holdings,
            )
            return False

        _qrate = float(self._quote_to_usd or 1.0)
        current_value = priced_usd(venue_units, price, _qrate)
        excess_usd = target_delta_usd(current_value, self._anchor_target_balance)
        if excess_usd <= 0:
            return True

        sell_amount = (
            scrum_units(excess_usd, price * _qrate, FRACTIONAL_UNITS)
            if (price * _qrate) > 0
            else 0.0
        )
        sell_amount = min(sell_amount, venue_units)
        if sell_amount <= 0:
            return True

        self._bus.emit(
            "bot.log",
            bot_id=self.bot_id,
            message=(
                f"DETONATION HARVEST: exchange holds {venue_units:.8f} "
                f"{self.config.symbol.split('/')[0]} for this bot "
                f"(value=${current_value:.2f}), "
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
            return False

        fill_amount, fill_price, _ = await self._settled_fill(
            order, self.config.symbol, sell_amount, price, label="DETONATION"
        )
        _detonation = {"excess_usd": float(excess_usd)}
        self._hold_resting_order(
            order, "_book_detonation", "sell", fill_amount, fill_price, _detonation
        )
        if fill_amount <= 0:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    "DETONATION: order placed but no filled "
                    "amount reported. Check exchange for actual "
                    "state. The bullish edge stays spent, because a sale the "
                    "venue has not reported must not be sent twice."
                ),
            )
            return True
        await self._book_detonation(
            fill_amount,
            fill_price or price,
            self._order_asked_units(self._last_settled_order or order, sell_amount),
            True,
            venue_units=venue_units,
            **_detonation,
        )
        return True

    async def _book_detonation(
        self,
        units: float,
        fill_price: float,
        asked: float,
        _first: bool,
        *,
        excess_usd: float,
        venue_units: Optional[float] = None,
    ) -> None:
        """Book one settled piece of a detonation: reset ``_target_balance`` to the
        anchor, clear the fold queue and reseed ``_main_lots``.

        ``venue_units`` is the venue reading taken before the order, None for a later
        piece, which takes ``units`` off ``_current_holdings``.
        """
        fill_amount = units
        held_before = (
            float(venue_units) if venue_units is not None else self._current_holdings
        )
        fill_usd = fill_price * fill_amount

        self._current_holdings = max(0.0, held_before - fill_amount)
        self._record_venue_units_after_fill(-fill_amount)

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
                "_book_detonation",
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
        for _cleared in list(self._fold_tranches):
            self._return_wire_credits_to_pool(_cleared)
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

        self._count_trade_volume(fill_amount, fill_price)
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
                f"{self._current_holdings:.8f} units remain of the "
                f"{held_before:.8f} the exchange held for this bot. "
                f"Bot will re-accumulate from scratch on next dip."
            ),
        )

        self._emit_voting_panel_snapshot_at_fire(
            side="SELL", trade_action="AUTO_DETONATION"
        )
        self._emit_gate_decision_at_fire(side="SELL", trade_action="AUTO_DETONATION")
        self._announce_fill(
            kind="AUTO_DETONATION",
            side=FILL_SELL,
            units=fill_amount,
            price=fill_price,
            usd=fill_usd,
            profit=excess_usd,
            operator_initiated=False,
            fee=self._fill_fee_fields(fill_price),
        )

    async def _execute_sell(
        self,
        amount: float,
        price: float,
        summary: VotingSummary,
        bypass_stack: bool = False,
        label: str = "SCRUM",
        booker: str = "",
        booking: Optional[dict] = None,
    ) -> Optional[float]:
        """Place a market sell and return the fill price, or None when refused.

        ``_settled_fill`` supplies the units the venue reported sold, under
        ``label``, and those units are what leaves ``_current_holdings``;
        ``amount`` is only what was asked for, so a partial fill no longer
        takes units off the ledger the venue never sold. A venue reporting no
        filled amount leaves ``_current_holdings`` and ``_main_lots`` untouched
        and answers None, which every caller already reads as no sale. The
        figure is left on ``_last_sell_filled_units`` for the callers that take
        the same units off ``_main_lots``. Both venue-fee records are cleared on
        entry and written by ``_settled_fill`` off whichever order object
        settled.
        """
        self._last_sell_venue_fee = None
        self._last_fill_venue_fee = None
        self._last_sell_filled_units = 0.0

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

        if self._hyst_armed_scrum_side and self._hyst_ref_scrum_side > 0:
            try:
                _px_check = float(price)
            except (TypeError, ValueError):
                _px_check = 0.0
            try:
                _held = self.opposing_distance_settings()
            except DistanceSettingUnreadable as _unread:
                self._refuse_unreadable_distance(_unread, "SCRUM", _px_check)
                return None
            _eff_pct = _held.distance_pct()
            _interval_frac = _eff_pct / 100.0
            _required_min = self._hyst_ref_scrum_side * (1.0 + _interval_frac)
            if _px_check > 0 and _px_check < _required_min:
                _rise_pct = (
                    (_px_check - self._hyst_ref_scrum_side)
                    / self._hyst_ref_scrum_side
                    * 100.0
                )
                if self._refusal_is_new("scrum_hysteresis", _px_check):
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"SCRUM REFUSED (opposing hysteresis): "
                            f"pivot ref ${self._hyst_ref_scrum_side:.8f} "
                            f"(captured when Δ crossed positive after recent "
                            f"FOLD), current ${_px_check:.8f} "
                            f"(only {_rise_pct:+.2f}% from pivot). "
                            f"Need ≥ {_eff_pct:.2f}% rise "
                            f"(interval {_held.interval_pct:.2f}% + fee "
                            f"{_held.fee_pct:.2f}%, at least {ROUND_TRIP_FEES} "
                            f"fees; price ≥ ${_required_min:.8f}) before "
                            f"SCRUM can fire."
                        ),
                    )
                    self._emit_trade_notification(
                        "SCRUM",
                        "REFUSED",
                        f"hysteresis (need ≥ {_eff_pct:.2f}% rise)",
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
                    f"SELL REFUSED (capital reservation): "
                    f"requested {amount:.6f} {self.config.target_asset} but "
                    f"only {_crr_effective:.6f} available to this bot — "
                    f"_current_holdings={float(self._current_holdings or 0):.6f}; "
                    f"claimed by "
                    f"{_crr_holders or 'a bot the registry cannot name'}. "
                    f"Stopping a named bot releases its claim."
                )
                if self._refusal_is_new("sell_reservation", price):
                    self._bus.emit("bot.log", bot_id=self.bot_id, message=_crr_msg)
                    self._emit_trade_notification(
                        "SCRUM",
                        "REFUSED",
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
            # A raised pre-check has not answered, so this sell stops instead
            # of running on _current_holdings alone.
            if self._refusal_is_new("sell_reservation_unreadable", price):
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
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SELL REFUSED (capital reservation unreadable): the "
                        f"pre-check raised {type(_crr_exc).__name__}: "
                        f"{_crr_exc}. No sibling bot's claim on "
                        f"{self.config.target_asset} could be read, so this sell "
                        f"of {amount:.6f} is refused instead of placed unbounded. "
                        f"The next tick asks the claim table again."
                    ),
                )
                self._emit_trade_notification(
                    "SCRUM", "REFUSED", "capital reservation unreadable"
                )
            return None

        try:
            _open = await self.exchange.get_open_orders(self.config.symbol)
        except Exception as _oo_exc:
            if self._refusal_is_new("sell_open_orders_unreadable", price):
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
            if self._refusal_is_new("sell_stacked", price):
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
            from ...core.execution_discipline import verify_book_spread as _vbs

            _book_spread = await self._book_spread_pct(self.config.symbol)
            vh_fp, vh_status, vh_spread = _vbs(
                price, _book_spread, symbol=self.config.target_asset
            )
            self._last_book_spread_pct = vh_spread
            self._last_slippage_status = vh_status
            if vh_spread is not None:
                self.stats.verify_samples += 1
            if vh_fp is None:
                self.stats.verify_canceled += 1
                if self._refusal_is_new("sell_slippage", price):
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"SELL CANCELED (VH): venue book spread "
                        f"{(vh_spread or 0.0) * 100.0:.4f}% would "
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
            elif vh_status == "adjusted":
                self.stats.verify_adjusted += 1

            if self._invisible:
                ot = OrderType.MARKET
                exec_price = None
            else:
                ot = OrderType.LIMIT
                # The limit price is the figure this bot decided. verify_hit's
                # draw models a fill and never prices a live order.
                exec_price = float(price)

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

            # The only point on the SCRUM, DIST and STACK paths holding the
            # settled order; _settled_fill records the venue fee off it.
            filled_units, actual_fill, _ = await self._settled_fill(
                order, self.config.symbol, amount, price, label=label
            )
            asked = self._order_asked_units(self._last_settled_order or order, amount)
            self._hold_resting_order(
                order,
                "_book_sale_fill",
                "sell",
                filled_units,
                actual_fill,
                {
                    "label": label,
                    "intended": float(price),
                    "asked_units": float(amount),
                    "confidence": float(summary.consensus_confidence),
                    "path_booker": booker,
                    "path_context": dict(booking or {}),
                },
            )
            if filled_units <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"SELL SENT, NO FILL REPORTED: {amount:.6f} "
                        f"{self.config.target_asset} @ ${price:.8f} was "
                        f"accepted and the exchange reported no filled "
                        f"amount. Holdings and the lot book are unchanged and "
                        f"no fold tranche is queued. A LIMIT order resting on "
                        f"the book reports this until it trades, and the "
                        f"open-order check refuses a second SELL meanwhile."
                    ),
                )
                self._emit_trade_notification(
                    "SCRUM", "REFUSED", "exchange reported no filled amount"
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
            actual_fill = await self._book_sale(
                filled_units,
                actual_fill,
                amount,
                price,
                label,
                summary.consensus_confidence,
            )
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
        await self._run_booker(booker, filled_units, actual_fill, asked, True, booking)
        return actual_fill

    async def _refuses_stacked_buy(
        self, price: Any, announce_every: bool = False
    ) -> bool:
        """True where ``get_open_orders`` raises or names an open BUY on
        ``config.symbol``, after the P0b line ``_refusal_is_new`` admits, or every
        line with ``announce_every``."""
        try:
            _open = await self.exchange.get_open_orders(self.config.symbol)
        except Exception as _oo_exc:
            if announce_every or self._refusal_is_new(
                "buy_open_orders_unreadable", price
            ):
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
            return True
        try:
            _open_buys = [
                o
                for o in (_open or [])
                if getattr(o, "side", None) == OrderSide.BUY
                and getattr(o, "symbol", None) == self.config.symbol
            ]
        except Exception:
            _open_buys = [
                o
                for o in (_open or [])
                if getattr(o, "symbol", None) == self.config.symbol
            ]
        if not _open_buys:
            return False
        _ids = ", ".join(str(getattr(o, "id", "?")) for o in _open_buys[:3])
        if announce_every or self._refusal_is_new("buy_stacked", price):
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
        return True

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
        booker: str = "",
        booking: Optional[dict] = None,
        sources: Optional[list] = None,
    ) -> Optional[float]:
        """Place a market buy and return the fill price, or None when refused.

        ``trace_context`` supplies the ``path`` named in the buy trace this
        emits to ``bot.log``. ``_settled_fill`` supplies the units the venue
        reported bought, and those units are what reaches
        ``_current_holdings`` and ``_audited_venue_units``; ``cost`` is only
        what was asked for, so a resting or partly filled order adds no units
        the venue never bought. A venue reporting no filled amount leaves both
        figures untouched and answers None, which every caller already reads as
        no buy. The figure is left on ``_last_buy_filled_units`` for the
        callers that add the same units to ``_main_lots``.
        """
        self._last_fill_venue_fee = None
        self._last_buy_filled_units = 0.0

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
                    f"BUY TRACE: path={_path} "
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

        if self._hyst_armed_fold_side and self._hyst_ref_fold_side > 0:
            try:
                _px_check = float(price)
            except (TypeError, ValueError):
                _px_check = 0.0
            try:
                _held = self.opposing_distance_settings()
            except DistanceSettingUnreadable as _unread:
                self._refuse_unreadable_distance(_unread, "FOLD", _px_check)
                return None
            _eff_pct = _held.distance_pct()
            _interval_frac = _eff_pct / 100.0
            _required_max = self._hyst_ref_fold_side * (1.0 - _interval_frac)
            if _px_check > 0 and _px_check > _required_max:
                _drop_pct = (
                    (self._hyst_ref_fold_side - _px_check)
                    / self._hyst_ref_fold_side
                    * 100.0
                )
                if self._refusal_is_new("fold_hysteresis", _px_check):
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=(
                            f"FOLD REFUSED (opposing hysteresis): "
                            f"pivot ref ${self._hyst_ref_fold_side:.8f} "
                            f"(captured when Δ crossed negative after recent "
                            f"SCRUM), current ${_px_check:.8f} "
                            f"(only {_drop_pct:+.2f}% from pivot). "
                            f"Need ≥ {_eff_pct:.2f}% drop "
                            f"(interval {_held.interval_pct:.2f}% + fee "
                            f"{_held.fee_pct:.2f}%, at least {ROUND_TRIP_FEES} "
                            f"fees; price ≤ ${_required_max:.8f}) before "
                            f"FOLD can fire."
                        ),
                    )
                    self._emit_trade_notification(
                        "FOLD",
                        "REFUSED",
                        f"hysteresis (need ≥ {_eff_pct:.2f}% drop)",
                    )
                return None

        _max_ep = getattr(self.config, "max_entry_price", None)
        _min_ep = getattr(self.config, "min_entry_price", None)
        try:
            _px = float(price) if price is not None else 0.0
        except (TypeError, ValueError):
            _px = 0.0
        if _max_ep is not None and _px > 0 and _px > float(_max_ep):
            if self._refusal_is_new("buy_above_max_entry", _px):
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
            if self._refusal_is_new("buy_below_min_entry", _px):
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

        if await self._refuses_stacked_buy(price):
            return None

        _ctx = trace_context or {}
        _path = _ctx.get("path", "unspecified")
        _cap_pct = float(target_growth_pct(self.config))
        _anchor = float(getattr(self, "_anchor_target_balance", self._target_balance))
        _per_cycle_growth_budget = _anchor * (_cap_pct / 100.0)

        _fresh_units, _refuse_reason_msg = await self._verify_buy_safe_or_refuse(
            path=_path
        )
        if _refuse_reason_msg:
            if self._refusal_is_new("buy_safety", price):
                self._bus.emit(
                    "bot.log", bot_id=self.bot_id, message=_refuse_reason_msg
                )
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
                f"LAYER 1 BREACH — buy REFUSED. "
                f"Path={_path}. Current position=${_current_position_usd:.2f} "
                f"({_fresh_units:.8f} {self.config.target_asset} @ "
                f"${price:.8f}). Target=${self._target_balance:.2f}, "
                f"Target Delta=${_target_delta_usd:+.2f}. "
                f"Path budget=${_path_budget:.2f} (+{_slippage_tol_pct:.2f}% "
                f"tol → ${_budget_with_tol:.2f}). Proposed cost ${cost:.2f} "
                f"exceeds budget. No buy may exceed its path's Target-Delta "
                f"+ per-cycle-growth allowance."
            )
            if self._refusal_is_new("buy_layer1_budget", price):
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
                        f"LAYER 2 (POSITION CEILING) BREACH — "
                        f"buy REFUSED. Path={_path}. Projected position "
                        f"${_projected_position_usd:.2f} > Position Ceiling "
                        f"${_smart_ceiling_usd:.2f} (anchor "
                        f"${_anchor:.2f} × Ceiling Multiple "
                        f"{self.config.position_ceiling_multiple}). "
                        f"Bot has reached configured maturity — no further "
                        f"acquisition until detonation harvests grown "
                        f"position on next bullish higher-TF vote."
                    )
                    if self._refusal_is_new("buy_layer2_ceiling", price):
                        self._bus.emit("bot.log", bot_id=self.bot_id, message=_reason)
                        logger.warning("Bot %s %s", self.bot_id, _reason)
                    return None

        try:
            amount = fold_units(cost, price, FRACTIONAL_UNITS)
            if _qrate_buy > 0 and abs(_qrate_buy - 1.0) > 1e-9:
                amount = amount / _qrate_buy

            from ...core.execution_discipline import verify_book_spread as _vbs

            _book_spread = await self._book_spread_pct(self.config.symbol)
            vh_fp, vh_status, vh_spread = _vbs(
                price, _book_spread, symbol=self.config.target_asset
            )
            self._last_book_spread_pct = vh_spread
            self._last_slippage_status = vh_status
            if vh_spread is not None:
                self.stats.verify_samples += 1
            if vh_fp is None:
                self.stats.verify_canceled += 1
                if self._refusal_is_new("buy_slippage", price):
                    self._bus.emit(
                        "bot.log",
                        bot_id=self.bot_id,
                        message=f"BUY CANCELED (VH): venue book spread "
                        f"{(vh_spread or 0.0) * 100.0:.4f}% would "
                        f"exceed {self.config.target_asset} class "
                        f"tolerance @ ${price:.8f}",
                    )
                    logger.info(
                        "Bot %s VH-canceled buy of %.6f at %.4f",
                        self.bot_id,
                        amount,
                        price,
                    )
                return
            if vh_status == "clean":
                self.stats.verify_clean += 1
            elif vh_status == "adjusted":
                self.stats.verify_adjusted += 1

            if self._invisible:
                ot = OrderType.MARKET
                exec_price = None
            else:
                ot = OrderType.LIMIT
                # The limit price is the figure this bot decided. verify_hit's
                # draw models a fill and never prices or sizes a live order.
                exec_price = float(price)

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

            # The only point on the FOLD and ENTRY paths holding the settled
            # order; _settled_fill records the venue fee off it.
            filled_units, actual_fill, _ = await self._settled_fill(
                order, self.config.symbol, amount, price, label="FOLD"
            )
            asked = self._order_asked_units(self._last_settled_order or order, amount)
            self._hold_resting_order(
                order,
                "_book_purchase_fill",
                "buy",
                filled_units,
                actual_fill,
                {
                    "path": _path,
                    "intended": float(price),
                    "asked_units": float(amount),
                    "confidence": float(summary.consensus_confidence),
                    "net_score": float(getattr(summary, "net_score", 0.0) or 0.0),
                    "path_booker": booker,
                    "path_context": dict(booking or {}),
                },
                sources,
            )
            if filled_units <= 0:
                self._bus.emit(
                    "bot.log",
                    bot_id=self.bot_id,
                    message=(
                        f"BUY SENT, NO FILL REPORTED: {amount:.6f} "
                        f"{self.config.target_asset} @ ${price:.8f} was "
                        f"accepted and the exchange reported no filled "
                        f"amount. Holdings and the lot book are unchanged. A "
                        f"LIMIT order resting on the book reports this until "
                        f"it trades."
                    ),
                )
                self._emit_trade_notification(
                    "FOLD", "REFUSED", "exchange reported no filled amount"
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
            actual_fill = await self._book_purchase(
                filled_units,
                actual_fill,
                amount,
                price,
                _path,
                _fresh_units,
                summary,
            )
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
        await self._run_booker(
            booker, filled_units, actual_fill, asked, True, booking, sources
        )
        return actual_fill
