"""Order execution for ScrummingBot: places venue orders and settles fills.

Holds the sell, buy, detonation and manual-rebalance paths, plus the
venue-fee record a settled sell produces.
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
class SettledSellFee:
    """The fee the VENUE reported for one settled sell.

    issue #133 unit 9b. A sell is credited NET: the venue keeps its
    fee out of the proceeds. The fold-tranche loops valued a sell at
    ``units x fill_price``, which is the GROSS notional, so every
    tranche was booked richer than the wallet actually got.

    This record carries the venue's own number from the point an
    order settles to the point a tranche is valued. It NEVER carries
    a fee derived from ``config.trading_fee_pct``: that is the bot's
    configured estimate, the venue charges what it charges, and
    synthesising one in place of the other books a number the
    exchange never charged.

    ``units`` and ``price`` identify the fill this fee belongs to. A
    consumer that cannot match both books the gross, because a fee
    from some other order is not this order's fee.

    ``reported`` is False when the venue gave no fee. That case books
    the gross and says so; it does not fall back to a rate.
    """

    units: float
    price: float
    fee_amount: float
    currency: str
    reported: bool


class ExecutionEngineMixin:
    """Place orders at the venue and book what the venue reports back.

    Every method here runs downstream of a gate decision; none of them
    decides whether to trade.
    """

    # Supplied by ScrummingBot at runtime; declared so a type
    # checker can resolve them. Annotations only: no attribute is
    # created and the runtime base stays `object`.
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

    # issue #133 unit 9b -- a CLASS-LEVEL default, not only an
    # `__init__` one. A sell must never raise `AttributeError` on a bot
    # built without `__init__`, and both the suite and the restore
    # paths build them that way. `None` is immutable and every write
    # goes to the instance, so no bot can read another bot's fee.
    _last_sell_venue_fee: Optional["SettledSellFee"] = None

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
        """Resolve ``label`` against the closed set above. Never raises.

        This runs AFTER an order is already placed. Raising on a bad
        label would abandon the accounting for a trade that really
        happened, which is strictly worse than logging the default.
        ``None`` and ``""`` are accepted and mean "use the default".
        Anything else unrecognised also degrades to the default, and
        says so in the developer log so the caller gets fixed.
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
        """Re-read a just-placed order so accounting books the REAL fill.

        A market order is not settled the instant ``create_order``
        returns, so this polls briefly rather than reading once.

        ``label`` names the CALLER in that fallback line, drawn from a
        closed set (see ``_settled_fill_label``). It is ABSENT on the
        manual path, which keeps the message byte-identical to what the
        operator has always read there.

        Returns ``(fill_amount, fill_price, is_real)``.

        issue #133 unit 9b -- also records the venue's fee, taken from
        the SAME order object the accepted fill came from. That is the
        re-read order when a re-read is what settled, not the object
        the caller passed in. An ESTIMATE clears the record: the venue
        confirmed nothing, so there is no fee to book.
        """
        self._last_sell_venue_fee = None

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
                    return f_amt, f_px, True
                amt = f_amt or amt
                px = f_px or px

        est_amt = amt if amt > 0 else float(requested_amount or 0.0)
        est_px = px if px > 0 else float(quoted_price or 0.0)
        self._last_sell_venue_fee = None
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
        """Store the fee the VENUE reported for a just-settled sell.

        issue #133 unit 9b. Called from the two places that hold a
        settled order object: `_execute_sell`, which serves SCRUM and
        DIST, and `_settled_fill`, which serves the manual paths. It
        reads `order.fee` and `order.fee_currency` only. The connector
        fills both from the venue's own `fee.cost` / `fee.currency`
        (`CCXTConnector._parse_order` in `src/exchange/ccxt_connector.py`),
        so nothing here is computed.

        A BUY clears the record instead of writing it. Sale proceeds
        are the only consumer and a buy fee is not a sale fee.

        WHAT REACHES THIS METHOD ON COINBASE, ESTABLISHED FROM SOURCE
        rather than from a live call. `ccxt.coinbase.create_order`
        returns `parse_order(response["success_response"])`, and that
        body carries four keys -- `order_id`, `product_id`, `side`,
        `client_order_id`. There is no `total_fees` in it, so
        `fee.cost` parses to None and `Order.fee` is 0.0 on EVERY
        just-placed Coinbase order. `fetch_order` is a different
        endpoint and its documented body does carry `total_fees`;
        whether Coinbase has settled a NON-ZERO value into it seconds
        after a market fill is unobserved and is not assumed here.

        So on live Coinbase the SCRUM and DIST paths, which read the
        placed order and never re-read it, record no fee and book the
        gross -- and say so, every time, in the operator's log. That
        is the specified no-fee behaviour, not a silent one. The
        manual paths re-read through `_settled_fill` and are the only
        ones a Coinbase fee can currently reach.

        Never raises. The order already executed, and losing the
        accounting for a real trade is worse than losing a fee.
        """
        _side = getattr(order, "side", None)
        _side_txt = str(getattr(_side, "value", _side) or "").lower()
        if _side_txt != "sell":
            self._last_sell_venue_fee = None
            return
        try:
            _units = float(units)
            _price = float(price)
        except (TypeError, ValueError):
            self._last_sell_venue_fee = None
            return
        try:
            _amount = float(getattr(order, "fee", 0) or 0)
            _currency = str(getattr(order, "fee_currency", "") or "")
        except (TypeError, ValueError):
            _amount = 0.0
            _currency = ""
        self._last_sell_venue_fee = SettledSellFee(
            units=_units,
            price=_price,
            fee_amount=_amount,
            currency=_currency.strip().upper(),
            reported=_amount > 0.0,
        )

    def _take_venue_fee(self, units: float, price: float) -> Optional[SettledSellFee]:
        """Consume the stored fee, and only for the fill it belongs to.

        Single use: the record is cleared whether or not it matched, so
        one venue fee can never be subtracted from two valuations. A
        record whose units or price disagree with the fill being valued
        belongs to some other order, so it is discarded rather than
        applied.
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

    def _settled_sale_proceeds(
        self, units: float, price: float, *, label: str
    ) -> float:
        """Value a settled sell at what the venue actually credited.

        issue #133 unit 9b. The three fold-tranche loops booked
        `units x fill_price`, the GROSS notional. A venue credits the
        NET: it keeps its fee out of the proceeds.

        THE NUMBERS, EACH WITH ITS PROVENANCE. Bot c8e5c5db,
        2026-08-26 21:50:57, 473 CHIP at $0.03376:

        * $15.96848 booked gross -- LOGGED, `trade.log` and
          `pnl/daily/2026-08-26.ndjson`, both carrying no fee field;
        * 1.2% -- the venue's own rate, read off Coinbase's CSV export
          of CHIP fills, 92 of 92 August 2026 fills at exactly 1.2000%
          of subtotal, both sides;
        * $15.77686 net -- INFERRED from those two. The export ends
          2026-08-20, so the credited amount for this trade itself is
          recorded nowhere and is not claimed as measured.

        Returns the gross MINUS the fee the venue reported. Books the
        gross, and emits the reason, when that fee cannot be used. It
        never falls back to `config.trading_fee_pct`: that value was
        1.6 on the measured trade and the venue charged 1.2, so a
        synthesised fee books a number the exchange never charged.
        """
        _units = float(units)
        _price = float(price)
        _gross = _units * _price
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
        _net = _gross - _fee.fee_amount
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
        """Rebalance holdings to target in one shot.

        Invoked from tick() when self._manual_fire_pending is True
        (operator clicked Manual Fire), AND from two autonomous code
        paths that piggyback on the same rebalance-to-center math:
        Wire Stack Fire (L4213) and Max Cartridge Fire (L4477).

          - ``"manual_button"`` (default) — operator clicked Fire.
            Emits ``type="MANUAL_SCRUM"`` / ``"MANUAL_FOLD"`` with
            ``operator_initiated=True``.
          - ``"wire_stack"`` — autonomous Wire Stack Fire (L4213).
            Emits ``type="WIRE_STACK_SCRUM"`` / ``"WIRE_STACK_FOLD"``
            with ``operator_initiated=False``.
          - ``"max_cartridge"`` — autonomous Max Cartridge Fire
            (L4477). Emits ``type="CARTRIDGE_SCRUM"`` /
            ``"CARTRIDGE_FOLD"`` with ``operator_initiated=False``.

        Unknown values raise ``ValueError`` (fail-loud so the next
        caller can't silently inherit the wrong attribution).

        Semantic:
          - Computes delta_usd = current_value - target_balance at
            ticker.last
          - delta > 0 → sell delta/price asset at MARKET
          - delta < 0 → buy |delta|/price asset at MARKET (clipped by
            available USD)
          - |delta| within 1% dust band → no-op with operator log

        The operator_initiated flag makes operator-clicked trades
        visible to downstream audits (equity curve, P/L attribution,
        reconciliation tools) so a manual intervention doesn't look
        identical to an autonomous Wire Stack or Max Cartridge fire
        in the trade log.
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

        current_value = self._current_holdings * price * _qrate
        delta_usd = current_value - self._target_balance
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
                    getattr(self.config, "max_target_growth_pct", 0.0) or 0.0
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

        if abs(delta_usd) < dust:
            self._bus.emit(
                "bot.log",
                bot_id=self.bot_id,
                message=(
                    f"MANUAL FIRE: already within dust band "
                    f"(|delta|=${abs(delta_usd):.4f} < "
                    f"${dust:.2f}). No-op."
                ),
            )
            return

        class _ManualSummary:
            consensus_confidence = 1.0
            direction = None
            raw_votes: dict = {}

            def __repr__(self) -> str:
                return "<ManualSummary operator_initiated=True>"

        _ManualSummary()

        if delta_usd > 0:
            _denom_sc = price * _qrate
            sell_amount = (delta_usd / _denom_sc) if _denom_sc > 0 else 0.0
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

            # issue #133 unit 9b -- the venue credits the NET,
            # exactly as on the SCRUM and DIST paths. `_settled_fill`
            # carried the fee from whichever order object settled.
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

            # issue #133 unit 2 -- the third build loop, same rule. Two
            # of this method's three callers fire autonomously, so
            # leaving it out would bound the count everywhere the
            # operator does not click and nowhere he does.
            new_tranches_count -= self._bound_new_fold_tranches(
                _manual_tranche_count_before
            )

            # 2026-08-12 — MIRRORED FROM THE SCRUM PATH. This method
            # serves three callers -- Manual Fire, Wire Stack and Max
            # Cartridge -- and two of the three fire autonomously, so
            # the gap was never "manual only". `fill_usd` is already net
            # of Smart Wire routing and is the same figure the build
            # loop divided, so the units test inside the helper reads
            # this sale's own rate. Runs before the _fold_queue_usd sum
            # below so the derived scalar reports the scaled queue.
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

            # issue #133 unit 11 -- the parked pool exists only while the
            # fold queue is empty. This sell has just filled it, so the
            # pool lands here. After the top-up: the merge blends `ref`
            # from `usd / ref` per record, and wire USD carries no units.
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
                    f"(~${self._current_holdings * price * float(self._quote_to_usd or 1.0):.2f})."
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
            buy_usd = min(buy_usd_target, usd_balance)
            if buy_usd <= 0:
                err_tail = f" (fetch error: {_bal_err})" if _bal_err else ""
                held_tail = (
                    f", of which ${_held_by_others:.4f} is reserved by "
                    f"other bots' in-flight orders"
                    if _held_by_others > 1e-9
                    else ""
                )
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
            buy_amount = (buy_usd / denom) if denom > 0 else 0.0
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
                    # Finite, per _fold_discharge_order. Coerced so the
                    # write-back below is float arithmetic.
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
                    f"(~${self._current_holdings * price * float(self._quote_to_usd or 1.0):.2f})."
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
        """Execute the detonation harvest.

        Operator Q3: "Sell everything above the ANCHOR, not above
        current target (locks in full gains)."
        Operator post-detonation semantic: "Yes — reset target to
        anchor. 'Locks in' means fully reset; re-accumulate from
        scratch."

        Effect:
          1. Compute excess = current_holdings_value - anchor
          2. MARKET SELL excess/price asset
          3. Reset self._target_balance = anchor (full reset)
          4. Clear fold queue (no re-accumulation pressure)
          5. Tag the trade and resulting tranches auto_detonated=True
             for downstream audit visibility
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
        current_value = self._current_holdings * price * _qrate
        excess_usd = current_value - self._anchor_target_balance
        if excess_usd <= 0:
            return

        sell_amount = excess_usd / (price * _qrate) if (price * _qrate) > 0 else 0.0
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
        float(getattr(self, "_standing_surplus_usd", 0.0) or 0.0)
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
                f"Fold queue cleared. Bot will re-accumulate "
                f"from scratch on next dip."
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
        """Execute a sell order. Returns actual fill price captured from
        original semantics.

        issue #133 unit 9b -- also records the fee the venue reported
        for the settled order, so the SCRUM and DIST fold loops can
        value the sale at what the wallet was credited. The record is
        cleared on entry: a sell that never reaches the exchange must
        not leave the previous sell's fee readable.
        """
        self._last_sell_venue_fee = None

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
                _crr_msg = (
                    f"SELL REFUSED (capital reservation, v3.20.2): "
                    f"requested {amount:.6f} {self.config.target_asset} but "
                    f"only {_crr_effective:.6f} available to this bot — "
                    f"other bots hold reservations on this asset. "
                    f"_current_holdings={float(self._current_holdings or 0):.6f}; "
                    f"check Settings → Capital Reservations or "
                    f"force_release if a reservation is stale."
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
            logger.debug(
                "Bot %s capital reservation pre-check raised %s — "
                "falling through to existing gates; v3.20.1 backstop "
                "remains active.",
                self.bot_id,
                _crr_exc,
            )

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
            # issue #133 unit 9b -- the only point on the SCRUM and
            # DIST paths that holds the settled order, so the venue's
            # fee is carried from here.
            self._record_venue_fee(order, amount, actual_fill)
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
        """Fail-closed ScrummingBot wrapper around the generalized
        buy-safety helper at
        ``src/trading/buy_safety.py::verify_buy_safe_or_refuse``.

        Returns ``(verified_units, refuse_reason)``. If
        ``refuse_reason`` is non-empty, the caller MUST refuse the
        buy and emit the reason to ``bot.log``. Otherwise
        ``verified_units`` is the bot's current position in
        ``target_asset`` units (may be ``0.0`` for legitimately-empty).

        ScrummingBot's expected-units source: ``sum(lot["units"]
        for lot in self._main_lots)`` — the bot's full attributed
        position across all open lots.
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
        """Execute a buy order. Returns actual fill price captured from
        the exchange response. See _execute_sell docstring for the
        Chunk 6 fill-price-capture design.
        has full causal context on every buy."""

        try:
            _ctx = dict(trace_context or {})
            _path = _ctx.get("path", "unspecified")
            _holdings = self._current_holdings
            _value = _holdings * price * float(self._quote_to_usd or 1.0)
            _delta = _value - self._target_balance
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
                        f"MEM-251 v2 LAYER 2 (SMART CEILING) BREACH — "
                        f"buy REFUSED. Path={_path}. Projected position "
                        f"${_projected_position_usd:.2f} > Smart Ceiling "
                        f"${_smart_ceiling_usd:.2f} (anchor "
                        f"${_anchor:.2f} × multiple "
                        f"{self.config.position_ceiling_multiple}). "
                        f"Bot has reached configured maturity — no further "
                        f"acquisition until detonation harvests grown "
                        f"position on next bullish higher-TF vote."
                    )
                    self._bus.emit("bot.log", bot_id=self.bot_id, message=_reason)
                    logger.warning("Bot %s %s", self.bot_id, _reason)
                    return None

        try:
            amount = cost / price
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
                amount = cost / vh_fp
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
