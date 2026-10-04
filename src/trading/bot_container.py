"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
``BotContainer`` runs one bot's asyncio tick loop; ``BotManager``
registers the containers and drives start, stop, pause and resume.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from dataclasses import replace
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..exchange.base import (
        ExchangeInterface,
        MarketRules,
        Order,
        OrderSide,
        OrderType,
    )

from ..core.event_bus import get_event_bus
from ..exchange.timeframes import ALL_TIMEFRAMES
from .container import (
    BotRegistryMixin,
    FleetAggregationMixin,
    StateRestoreMixin,
)
from .container.config import (
    DESPAWN_MAX_DAYS,
    DESPAWN_PREVIEW_WINDOWS,
    DOLLAR_PEGGED_CURRENCIES,
    STACK_MODE_DEFAULT,
    START_ALL_GAP_SECONDS,
    BotConfig,
    BotMode,
    BotState,
    BotStats,
    _BOT_CONFIG_EXTRACTOR_ONLY_FIELDS,
    _BOT_CONFIG_SCRUMMING_ONLY_FIELDS,
    _BOT_CONFIG_SHARED_FIELDS,
    _DEPRECATED_KWARGS,
    _sanitize_deprecated_kwargs,
    as_finite_float,
    bot_config_kwargs,
    despawn_preview,
    despawn_threshold_days,
    make_bot_config,
    phantom_init_kwargs,
)

logger = logging.getLogger("acervator.bot")

__all__ = [
    "DESPAWN_MAX_DAYS",
    "DESPAWN_PREVIEW_WINDOWS",
    "DOLLAR_PEGGED_CURRENCIES",
    "STACK_MODE_DEFAULT",
    "START_ALL_GAP_SECONDS",
    "BotConfig",
    "BotContainer",
    "BotManager",
    "BotMode",
    "BotState",
    "BotStats",
    "_BOT_CONFIG_EXTRACTOR_ONLY_FIELDS",
    "_BOT_CONFIG_SCRUMMING_ONLY_FIELDS",
    "_BOT_CONFIG_SHARED_FIELDS",
    "_DEPRECATED_KWARGS",
    "_sanitize_deprecated_kwargs",
    "as_finite_float",
    "bot_config_kwargs",
    "despawn_preview",
    "despawn_threshold_days",
    "make_bot_config",
    "phantom_init_kwargs",
]


class BotContainer:
    """One bot's isolated asyncio container; ``ScrummingBot`` and
    ``ExtractorBot`` subclass it and implement ``tick``."""

    MAX_CONSECUTIVE_ERRORS = 5
    COOLDOWN_SECONDS = 60

    def __init__(
        self,
        config: BotConfig,
        exchange: ExchangeInterface,
    ) -> None:
        self.bot_id: str = str(uuid.uuid4())[:8]
        self.config = config
        self.exchange = exchange
        self.stats = BotStats()
        self.state = BotState.IDLE
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._start_time: float = 0.0
        self._bus = get_event_bus()
        self._data_pool = None  # set by BotManager.set_data_pool
        self._market_rules_cache: dict[str, "MarketRules"] = {}
        self._phantoms_enabled: bool = False

    def force_fire(self, aggressive: bool = False) -> None:
        """Manual fire hook; the base implementation does nothing."""
        return

    def _invalidate_balance(
        self,
        currency: Optional[str] = None,
    ) -> None:
        """End the ``MarketDataPool`` balance window for this exchange and
        currency, so the next ``_get_balance`` re-fetches.

        A ``currency`` of None clears every slot this exchange holds.
        """
        if self._data_pool is None:
            return
        try:
            self._data_pool.invalidate_balance(self.config.exchange_id, currency)
        except Exception as _inv_exc:  # noqa: BLE001
            logger.debug("Bot %s balance invalidate failed: %s", self.bot_id, _inv_exc)

    def _invalidate_symbol_balances(self, symbol: str) -> None:
        """End the balance window for both legs of ``symbol``.

        A trade moves the base and the quote together, and naming both leaves
        every other currency's slot alone. A ``symbol`` naming no leg clears
        every slot this exchange holds rather than none.
        """
        if self._data_pool is None:
            return
        legs: list[str] = []
        if isinstance(symbol, str):
            legs = [leg for leg in symbol.split("/") if leg]
        if not legs:
            logger.debug(
                "Bot %s invalidating every balance slot: %r names no currency",
                self.bot_id,
                symbol,
            )
            self._invalidate_balance()
            return
        for leg in legs:
            self._invalidate_balance(leg)

    async def _get_market_rules(self, symbol: str) -> "MarketRules":
        """Return the venue's published ``MarketRules`` for ``symbol``, cached,
        and an all-``None`` record when the lookup fails or the venue lists no
        such market."""
        from ..exchange.base import MarketRules
        from .scrumming.sizing import (
            CLASS_CRYPTO,
            order_types_for,
            venue_session,
            venue_settlement_days,
        )

        cached = self._market_rules_cache.get(symbol)
        if cached is not None:
            return cached
        # Every connector a container holds is a crypto connector.
        session = venue_session(CLASS_CRYPTO, self.config.exchange_id)
        # No record was read here, so only the cited table can answer.
        order_types = order_types_for(None, CLASS_CRYPTO, self.config.exchange_id)
        settlement = venue_settlement_days(CLASS_CRYPTO, self.config.exchange_id)
        unread = MarketRules(
            read=False,
            session=session,
            order_types=order_types,
            settlement_days=settlement,
        )
        try:
            markets = await self.exchange.get_markets()
        except Exception as exc:
            logger.warning(
                "Bot %s could not fetch markets for %s, so its order limits "
                "are unknown: %s",
                self.bot_id,
                symbol,
                exc,
            )
            # A failure is not cached: caching it left the guard blind for the
            # container's life after one transient error.
            return unread
        for m in markets or []:
            if getattr(m, "symbol", None) == symbol:
                rules = getattr(m, "rules", None)
                if not isinstance(rules, MarketRules):
                    rules = unread
                else:
                    rules = replace(
                        rules,
                        session=session,
                        # The venue's own declaration rode in on this record.
                        order_types=order_types_for(
                            rules, CLASS_CRYPTO, self.config.exchange_id
                        ),
                        settlement_days=settlement,
                    )
                self._market_rules_cache[symbol] = rules
                return rules
        logger.warning(
            "Bot %s: %s is absent from the venue's market list, so its order "
            "limits are unknown",
            self.bot_id,
            symbol,
        )
        return unread

    def _warn_order(self, message: str) -> None:
        """Put ``message`` on the Console through ``bot.log`` and in the log,
        so an order the guard could not check is read where the operator
        watches."""
        logger.warning("Bot %s %s", getattr(self, "bot_id", "?"), message)
        bus = getattr(self, "_bus", None)
        if bus is None:
            return
        try:
            bus.emit("bot.log", bot_id=getattr(self, "bot_id", "?"), message=message)
        except Exception as exc:
            logger.debug("bot.log emit for an unchecked order raised: %s", exc)

    def _refuse_order(self, message: str) -> None:
        """Put ``message`` on the Console through ``bot.log``, log it, and raise
        it, so a refused order is read where the operator watches."""
        logger.error("Bot %s %s", getattr(self, "bot_id", "?"), message)
        bus = getattr(self, "_bus", None)
        if bus is not None:
            try:
                bus.emit(
                    "bot.log",
                    bot_id=getattr(self, "bot_id", "?"),
                    message=message,
                )
            except Exception as exc:
                logger.debug("bot.log emit for a refused order raised: %s", exc)
        raise Exception(message)

    # OVERTAKEN in the docstring below: "``amount`` reaches ``place_order``
    # unchanged; the market's rules are read to refuse a sub-minimum size and a
    # sub-minimum notional, and ``CCXTConnector.place_order`` is where a size is
    # stepped."
    # ``sized_order`` floors ``amount`` onto ``MarketRules.amount_increment``
    # here, before ``min_cost`` is measured and before ``place_order`` is called.
    # ``venue_variant`` then refuses an unbuilt variant and replaces
    # ``OrderType.MARKET`` where the venue declares none.
    # OVERTAKEN, the sentence above reading "``venue_variant`` then refuses an
    # unbuilt variant": ``variant_permits_close`` exempts one unbuilt variant,
    # ``VARIANT_ROLLING_POSITION``, and only for ``OrderSide.SELL``, so a
    # position in a market the venue expires can still be closed.
    async def guarded_place_order(
        self,
        symbol: str,
        side: "OrderSide",
        order_type: "OrderType",
        amount: float,
        price: Optional[float] = None,
        purpose: str = "trade",
    ) -> Optional[Order]:
        """Place an order through ``exchange.place_order``, sizing ``amount``
        onto the market's own rules first and refusing a non-finite,
        non-positive or sub-minimum size with ``PRE-FLIGHT REJECTED``.

        OVERTAKEN: "sizing ``amount`` onto the market's own rules first".
        ``amount`` reaches ``place_order`` unchanged; the market's rules are read
        to refuse a sub-minimum size and a sub-minimum notional, and
        ``CCXTConnector.place_order`` is where a size is stepped.
        """
        from ..exchange.base import OrderSide, OrderType

        # Exact type test: ``isinstance`` would admit bool, and every
        # comparison against NaN below is False.
        _side_str = "BUY" if side == OrderSide.BUY else "SELL"
        _amt_is_number = type(amount) in (int, float)
        _amt = 0.0
        if _amt_is_number:
            try:
                _amt = float(amount)
            except (TypeError, ValueError, OverflowError):
                # An int too large for a float has no usable size.
                _amt_is_number = False
                _amt = 0.0
        if not _amt_is_number or not math.isfinite(_amt) or _amt <= 0.0:
            # ``math.isfinite`` runs before the positivity test because
            # ``nan <= 0.0`` is False.
            self._refuse_order(
                f"PRE-FLIGHT REJECTED: {_side_str} {symbol} amount is not "
                f"a finite positive number: {amount!r} "
                f"(type {type(amount).__name__}). An amount that is not a "
                f"number cannot be sized, compared or sent, and this one "
                f"means an upstream value is already corrupt. "
                f"API not called."
            )

        # The market's own published rules. A rule the venue did not publish is
        # None, and None never satisfies a comparison the way 0.0 did.
        try:
            _rules = await self._get_market_rules(symbol)
        except Exception:
            from ..exchange.base import MarketRules as _MarketRules

            _rules = _MarketRules(read=False)

        if not _rules.read:
            self._warn_order(
                f"LIMITS NOT READ: {symbol} market record could not be "
                f"obtained, so no minimum size or cost is known for this "
                f"{_side_str} of {_amt:.10f}. The venue enforces its own; "
                f"Acervator checks nothing here."
            )

        # Every live order passes here, so the venue's own step is applied at
        # the one submitting site and not at each composing site.
        from .scrumming.sizing import (
            BELOW_MINIMUM_AMOUNT,
            BELOW_ONE_UNIT,
            CLASS_CRYPTO,
            HELD_OUTSIDE_SESSION,
            outside_session,
            sized_order,
            unit_rule,
            untradeable_reason,
            variant_built,
            variant_permits_close,
            variant_replaces_market_order,
            venue_variant,
        )

        # Every connector a container holds is a crypto connector; nothing
        # constructs a broker one.
        _sized = sized_order(
            _amt, unit_rule(CLASS_CRYPTO, self.config.exchange_id), _rules
        )

        if _sized.refusal == BELOW_MINIMUM_AMOUNT:
            self._refuse_order(
                f"PRE-FLIGHT REJECTED: {_side_str} {symbol} amount "
                f"{_amt:.10f} is below min_amount {_rules.min_amount} "
                f"on a size increment of {_rules.amount_increment}. "
                f"{BELOW_MINIMUM_AMOUNT}. "
                f"API not called."
            )

        if _sized.refusal == BELOW_ONE_UNIT:
            self._refuse_order(
                f"PRE-FLIGHT REJECTED: {_side_str} {symbol} amount "
                f"{_amt:.10f} floors to nothing on a size increment of "
                f"{_rules.amount_increment}. {BELOW_ONE_UNIT}. "
                f"API not called."
            )

        # A venue that published no step and a pair with no cited rule both
        # leave the amount as it came in, and neither refuses on that ground.
        if 0.0 < _sized.units < _amt:
            self._warn_order(
                f"SIZED ON THE VENUE'S STEP: {_side_str} {symbol} "
                f"{_amt:.10f} to {_sized.units:.10f} on a size increment of "
                f"{_rules.amount_increment} ({_sized.source})."
            )
            _amt = _sized.units
            amount = _sized.units

        if _rules.min_cost is not None and price is not None:
            try:
                _px = float(price)
            except (TypeError, ValueError):
                _px = 0.0
            if _px > 0:
                # The venue books a price on its own tick, so min_cost is
                # compared against the notional at that price.
                _booked_px = _rules.price_on_tick(_px)
                if _booked_px is None or _booked_px <= 0.0:
                    _booked_px = _px
                _notional = _amt * _booked_px
                if _notional < _rules.min_cost:
                    self._refuse_order(
                        f"PRE-FLIGHT REJECTED: {_side_str} {symbol} notional "
                        f"${_notional:.4f} ({_amt:.10f} \u00d7 ${_px:.8f}) "
                        f"is below min_cost ${_rules.min_cost:.4f}. "
                        f"Priced at ${_booked_px:.8f} on a price tick of "
                        f"{_rules.price_increment}. "
                        f"API not called."
                    )

        # Last point before any venue contact, so a hold can only stop an order
        # that every check above already passed.
        if outside_session(_rules.session, time.time()):
            self._warn_order(
                f"HELD: {_side_str} {symbol} {_amt:.10f} is "
                f"{HELD_OUTSIDE_SESSION} ({_rules.session}). Nothing is "
                f"submitted and no state changes; the next tick decides "
                f"again. API not called."
            )
            return None

        # The venue's own rules pick the variant, and both branches run before
        # the order is sent.
        _ref_px = 0.0
        if price is not None and type(price) in (int, float):
            _ref_px = float(price)
        if not math.isfinite(_ref_px) or _ref_px <= 0.0:
            _ref_px = float(getattr(self.stats, "current_price", 0.0) or 0.0)
        if not math.isfinite(_ref_px) or _ref_px <= 0.0:
            _ref_px = 0.0
        _variant = venue_variant(_rules, _ref_px or None)

        # A position already open in an expiring market must still be able to
        # close, so a SELL passes where a BUY refuses and only that one variant
        # reaches the exception.
        _closing = variant_permits_close(_variant) and side == OrderSide.SELL

        if not variant_built(_variant) and not _closing:
            self._refuse_order(
                f"PRE-FLIGHT REJECTED: {_side_str} {symbol} needs a bot "
                f"variant the program does not hold. "
                f"{untradeable_reason(_rules, _ref_px or None)}. "
                f"The market is still read and still charted. "
                f"API not called."
            )

        if _closing:
            _left = _rules.days_to_expiry(time.time())
            _left_text = "an unreadable number of" if _left is None else f"{_left:.2f}"
            self._warn_order(
                f"CLOSING AN EXPIRING MARKET: SELL {symbol} {_amt:.10f} is "
                f"submitted where a BUY is refused, because the venue expires "
                f"this contract in {_left_text} days ({_variant}). Nothing "
                f"rebuys it."
            )

        if variant_replaces_market_order(_variant) and order_type == OrderType.MARKET:
            _limit_px = _rules.price_on_tick(_ref_px) if _ref_px else None
            if _limit_px is None or not math.isfinite(_limit_px) or _limit_px <= 0.0:
                _limit_px = _ref_px
            if _limit_px <= 0.0:
                self._refuse_order(
                    f"PRE-FLIGHT REJECTED: {_side_str} {symbol} needs a limit "
                    f"price on a venue declaring no market order, and no price "
                    f"is known for this market. "
                    f"API not called."
                )
            order_type = OrderType.LIMIT
            price = _limit_px
            self._warn_order(
                f"LIMIT FOR A VENUE TAKING NO MARKET ORDER: {_side_str} "
                f"{symbol} {_amt:.10f} at ${_limit_px:.8f} on a price tick of "
                f"{_rules.price_increment} ({_variant})."
            )

        # Deterministic client_order_id derived from the trade intent,
        # so a retry of the same intent reuses the same coid.
        from ..exchange.idempotency import get_idempotency_layer, TradeIntent

        _idem = get_idempotency_layer()
        _intent = TradeIntent(
            symbol=symbol,
            side="buy" if side == OrderSide.BUY else "sell",
            amount=float(amount),
            price=float(price) if price is not None else None,
            bot_id=getattr(self, "bot_id", "?"),
            purpose=purpose,
        )
        _coid = _idem.derive_coid(_intent)

        try:
            order = await self.exchange.place_order(
                symbol, side, order_type, amount, price, client_order_id=_coid
            )
            _idem.mark_fulfilled(_intent)
            # Every live order passes here, so the venue's figure is stale from
            # this line on and the window ends at the one submitting site.
            self._invalidate_symbol_balances(symbol)
            return order
        except Exception:
            raise

    async def start(self) -> None:
        """Launch the bot's trading loop in a guarded asyncio task."""
        if self.state in (BotState.RUNNING, BotState.STARTING):
            logger.warning("Bot %s already running", self.bot_id)
            return

        # A fresh start reports no error from the previous run.
        self.stats.last_error = ""
        self.stats.consecutive_errors = 0

        self.state = BotState.STARTING
        self._stop_event.clear()
        self._start_time = time.monotonic()
        if self._data_pool:
            self._data_pool.register(
                self.config.exchange_id,
                self.config.symbol,
                getattr(self.config, "ta_timeframe", "1h"),
            )
        self._task = asyncio.create_task(self._run_with_guard())
        self._bus.emit("bot.started", bot_id=self.bot_id, config=self.config)
        logger.info("Bot %s starting on %s", self.bot_id, self.config.symbol)

    async def stop(self) -> None:
        """Stop the trading loop task and unregister from the data pool."""
        self._stop_event.set()
        self._pause_event.set()  # Unpause so the loop can exit
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.state = BotState.STOPPED
        self.stats.uptime_seconds = time.monotonic() - self._start_time
        if self._data_pool:
            self._data_pool.unregister(
                self.config.exchange_id,
                self.config.symbol,
                getattr(self.config, "ta_timeframe", "1h"),
            )
        self._bus.emit("bot.stopped", bot_id=self.bot_id)
        logger.info("Bot %s stopped", self.bot_id)

    async def pause(self) -> None:
        """Suspend the trading loop and set state PAUSED."""
        self._pause_event.clear()
        self.state = BotState.PAUSED
        self._bus.emit("bot.paused", bot_id=self.bot_id)

    async def resume(self) -> None:
        """Resume from paused state."""
        self._pause_event.set()
        self.state = BotState.RUNNING
        self._bus.emit("bot.resumed", bot_id=self.bot_id)

    async def _run_with_guard(self) -> None:
        """Run ``tick`` until stopped, emitting ``bot.error`` on failure
        and cooling down after ``MAX_CONSECUTIVE_ERRORS``."""
        self.state = BotState.RUNNING
        try:
            while not self._stop_event.is_set():
                try:
                    await self._pause_event.wait()
                    if self._stop_event.is_set():
                        break

                    await self.tick()

                    self.stats.consecutive_errors = 0
                    # Only ERROR is cleared; COOLDOWN and PAUSED own
                    # their own transitions.
                    if self.state == BotState.ERROR:
                        self.state = BotState.RUNNING

                    # Heartbeat so uptime_seconds moves while running.
                    if self._start_time:
                        self.stats.uptime_seconds = time.monotonic() - self._start_time

                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.stats.consecutive_errors += 1
                    self.stats.total_errors += 1  # Cumulative; never reset.
                    self.stats.last_error = f"{type(exc).__name__}: {exc}"
                    # ERROR is set on the first failed tick, not the fifth.
                    self.state = BotState.ERROR
                    logger.error(
                        "Bot %s error (%d/%d, lifetime %d): %s",
                        self.bot_id,
                        self.stats.consecutive_errors,
                        self.MAX_CONSECUTIVE_ERRORS,
                        self.stats.total_errors,
                        exc,
                    )
                    self._bus.emit(
                        "bot.error",
                        bot_id=self.bot_id,
                        error=str(exc),
                        consecutive=self.stats.consecutive_errors,
                    )

                    if self.stats.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
                        self.state = BotState.COOLDOWN
                        self._bus.emit("bot.cooldown", bot_id=self.bot_id)
                        logger.warning(
                            "Bot %s entering cooldown for %ds",
                            self.bot_id,
                            self.COOLDOWN_SECONDS,
                        )
                        await asyncio.sleep(self.COOLDOWN_SECONDS)
                        self.stats.consecutive_errors = 0
                        self.state = BotState.RUNNING

                await asyncio.sleep(self.tick_interval)

        except asyncio.CancelledError:
            pass
        finally:
            self.stats.uptime_seconds = time.monotonic() - self._start_time

    @property
    def tick_interval(self) -> float:
        """Seconds between trading ticks; subclasses override."""
        return 5.0

    async def tick(self) -> None:
        """One iteration of the trading loop; subclasses must override."""
        raise NotImplementedError("Subclasses must implement tick()")

    def get_status(self) -> dict:
        """Return a snapshot of the bot's state and stats."""
        scrum_mode = getattr(self, "scrum_target_mode", None)
        armed_action = getattr(self, "armed_action", None)
        anchor_tb = getattr(self, "_anchor_target_balance", None)
        ceiling_usd = getattr(self, "position_ceiling_usd", None)
        ceiling_ratio = getattr(self, "ceiling_ratio", None)
        fold_taper = getattr(self, "fold_rate_taper", 1.0)

        # Queued tranches larger than one cycle's cycle_growth_cap_usd;
        # each is PART-CONSUMED, not skipped, so the count is advisory.
        _over_cap_summary = {
            "tranches_over_cycle_cap": 0,
            "tranches_over_cycle_cap_usd": 0.0,
        }
        try:
            _budget = float(getattr(self, "cycle_growth_cap_usd", 0.0) or 0.0)
            if _budget > 0:
                _over = [
                    float(_t.get("usd", 0) or 0)
                    for _t in (getattr(self, "_fold_tranches", []) or [])
                    if isinstance(_t, dict) and float(_t.get("usd", 0) or 0) > _budget
                ]
                _over_cap_summary = {
                    "tranches_over_cycle_cap": len(_over),
                    "tranches_over_cycle_cap_usd": round(sum(_over), 8),
                }
        except Exception as _oc_exc:  # noqa: BLE001
            logger.debug(
                "over-cap tranche summary unavailable for %s: %s",
                getattr(self, "bot_id", "?"),
                _oc_exc,
            )

        return {
            "bot_id": self.bot_id,
            "state": self.state.value,
            "exchange": self.config.exchange_id,
            "symbol": self.config.symbol,
            "mode": self.config.mode.value,
            "scrum_target_mode": scrum_mode,
            "armed_action": armed_action,
            "anchor_target_balance": anchor_tb,
            "position_ceiling_enabled": getattr(
                self.config, "position_ceiling_enabled", False
            ),
            "position_ceiling_multiple": getattr(
                self.config, "position_ceiling_multiple", 5.0
            ),
            "position_ceiling_usd": ceiling_usd,
            "ceiling_ratio": ceiling_ratio,
            "fold_rate_taper": fold_taper,
            "detonation_enabled": getattr(self.config, "detonation_enabled", False),
            "detonation_timeframe": getattr(self.config, "detonation_timeframe", "1d"),
            "target_balance": self.config.target_balance,
            # Runtime values the bot trades against; config.target_balance
            # above is the operator's unchanged input.
            "live_target_balance": float(getattr(self, "_target_balance", 0.0) or 0.0),
            "standing_surplus_usd": float(
                getattr(self, "_standing_surplus_usd", 0.0) or 0.0
            ),
            "fold_cycle_cap_consumed": float(
                getattr(self, "_fold_cycle_cap_consumed", 0.0) or 0.0
            ),
            "cycle_growth_budget_usd": round(
                float(getattr(self, "cycle_growth_cap_usd", 0.0) or 0.0), 8
            ),
            **_over_cap_summary,
            "ta_timeframe": getattr(self.config, "ta_timeframe", "1h") or "1h",
            "current_holdings": float(getattr(self, "_current_holdings", 0.0)),
            # 1.0 for USD-quoted pairs.
            "quote_to_usd": float(getattr(self, "_quote_to_usd", 1.0) or 1.0),
            "stats": {
                # Prefer the exchange's trade count once a refresh has landed.
                "total_trades": (
                    int(getattr(self.stats, "exchange_trade_count", 0) or 0)
                    if float(getattr(self.stats, "exchange_data_fresh_ts", 0.0) or 0.0)
                    > 0
                    else self.stats.total_trades
                ),
                "trade_volume": round(self.stats.trade_volume, 2),
                "realised_pnl": round(self.stats.realised_pnl, 4),
                "unrealised_pnl": round(self.stats.unrealised_pnl, 4),
                "active_buys": self.stats.active_buy_orders,
                "active_sells": self.stats.active_sell_orders,
                "current_price": self.stats.current_price,
                "position_value": round(getattr(self.stats, "position_value", 0.0), 4),
                "extended_positions": self.stats.extended_positions_created,
                # Live elapsed time while RUNNING or STARTING; the
                # stored value otherwise.
                "uptime": round(
                    (
                        (time.monotonic() - self._start_time)
                        if (
                            self._start_time
                            and self.state in (BotState.RUNNING, BotState.STARTING)
                        )
                        else self.stats.uptime_seconds
                    ),
                    1,
                ),
                "last_error": self.stats.last_error,
                # This bot's own accumulators, from self.stats.
                "total_scrummed_usd": round(
                    getattr(self.stats, "total_scrummed_usd", 0.0), 4
                ),
                "total_folded_usd": round(
                    getattr(self.stats, "total_folded_usd", 0.0), 4
                ),
                "ytd_scrummed_usd": round(
                    getattr(self.stats, "ytd_scrummed_usd", 0.0), 4
                ),
                "ytd_folded_usd": round(getattr(self.stats, "ytd_folded_usd", 0.0), 4),
                # Exchange-pulled. The Swarm locust reads these three to place
                # a bot in a growth stage; a zero fresh_ts means no reading.
                "realized_pnl_exchange": round(
                    float(getattr(self.stats, "realized_pnl_exchange", 0.0) or 0.0), 4
                ),
                "cost_basis_total_exchange": round(
                    float(getattr(self.stats, "cost_basis_total_exchange", 0.0) or 0.0),
                    4,
                ),
                "exchange_data_fresh_ts": float(
                    getattr(self.stats, "exchange_data_fresh_ts", 0.0) or 0.0
                ),
                # The fills behind total_trades, published beside it so a
                # multi-piece order is readable as one trade and several fills.
                "exchange_fill_count": int(
                    getattr(self.stats, "exchange_fill_count", 0) or 0
                ),
                # Saved beside the figure it describes, so a restart draws the
                # last complete reading instead of recomputing a short one.
                "fill_history_complete": bool(
                    getattr(self.stats, "fill_history_complete", False)
                ),
            },
            # A single bot's portfolio contribution is its position
            # value.
            "portfolio_value": round(
                getattr(self.stats, "position_value", 0.0) or 0.0, 4
            ),
            # Defaults stand in until a tick writes _last_gate_state.
            "auto_fire": dict(
                getattr(
                    self,
                    "_last_gate_state",
                    {
                        "scrum_armed": False,
                        "fold_armed": False,
                        "scrum_blockers": ["pre-tick"],
                        "fold_blockers": ["pre-tick"],
                        "evaluated_at_tick": 0,
                    },
                )
            ),
        }

    def get_full_state(self) -> dict:
        """Export config, stats and per-mode runtime state for persistence."""
        from dataclasses import asdict

        state = {
            "bot_id": self.bot_id,
            "state_when_saved": self.state.value,
            "config": asdict(self.config),
            "stats": asdict(self.stats),
            "saved_at": time.time(),
        }
        state["config"]["mode"] = self.config.mode.value

        # Persist the phantom flag so an explicit OFF survives restart.
        if hasattr(self, "_phantoms_enabled"):
            state["phantoms_enabled"] = bool(self._phantoms_enabled)

        # The key spells the field and the attribute: phantom_timeframes.
        # Every name the bot holds is written, however many, so a set of
        # several survives a restart instead of falling back to a default.
        _phantom_tfs = [
            str(one)
            for one in (getattr(self, "_phantom_timeframes", None) or [])
            if str(one) in ALL_TIMEFRAMES
        ]
        if _phantom_tfs:
            state["phantom_timeframes"] = _phantom_tfs

        # The coordinator owns the count; no BotConfig field carries it.
        _coordinator = getattr(self, "_coordinator", None)
        _lock_candles = getattr(_coordinator, "lock_candle_count", None)
        if _lock_candles is not None:
            state["lock_candle_count"] = int(_lock_candles)

        # Fetched by name: this parent does not define the exporter.
        _export_scrumming = getattr(self, "export_scrumming_state", None)
        if _export_scrumming is not None:
            try:
                state["scrumming_state"] = _export_scrumming()
            except Exception as exc:
                logger.warning(
                    "export_scrumming_state failed on %s: %s", self.bot_id, exc
                )

        # Fetched by name; the mode check comes first.
        _export_extractor = getattr(self, "export_state", None)
        if self.config.mode == BotMode.EXTRACTOR and _export_extractor is not None:
            try:
                state["extractor_state"] = _export_extractor()
            except Exception as exc:
                logger.warning(
                    "export_state (extractor) failed on %s: %s", self.bot_id, exc
                )

        return state


class BotManager(StateRestoreMixin, BotRegistryMixin, FleetAggregationMixin):
    """Registry for every ``BotContainer``: register, start, stop, pause,
    aggregate fleet stats, and save or restore state."""

    def __init__(self, bus=None) -> None:
        """Subscribe two handlers on ``bus``, defaulting to the
        process-wide bus."""
        self._bots: dict[str, BotContainer] = {}
        # Retained so detach_bus can retract them.
        self._bus_unsubs: list = []
        self._restore_ledger: dict[str, str] = {}  # bot_id -> reason
        self._boot_state_records: dict = {}  # bot_id -> record
        self._restore_completed: bool = False
        self._bus = bus if bus is not None else get_event_bus()
        self._state_manager = None
        self._ta_weights: Optional[dict] = None  # set from the settings store
        self._data_pool = None  # one MarketDataPool shared by every bot
        self._ticker_refresh_task = None
        self._ticker_refresh_stop = False
        self._live_monitor = None  # AI feedback loop (LiveMonitor)
        self._connector = None  # CcxtConnector — set via set_connector()
        # Set by set_async_loop(); shared by _dispatch_bootstrap.
        self._async_loop = None
        from .smart_wire import SmartWireManager

        self._smart_wire_mgr = SmartWireManager(bus=self._bus)
        self._bus_unsubs.append(
            self._bus.subscribe("wire.created", self._on_wire_created_mgr)
        )
        self._bus_unsubs.append(
            self._bus.subscribe("wire.removed", self._on_wire_removed_mgr)
        )

    def detach_bus(self) -> int:
        """Retract every subscription this manager made and return the
        count; never raises, and idempotent."""
        removed = 0
        for _off in list(self._bus_unsubs):
            try:
                _off()
                removed += 1
            except Exception as exc:
                logger.debug("bus detach skipped one handler: %s", exc)
        self._bus_unsubs = []
        return removed

    @property
    def smart_wire_manager(self):
        """Return the shared ``SmartWireManager``."""
        return self._smart_wire_mgr

    def _on_wire_created_mgr(self, event) -> None:
        """Register a drawn wire with ``SmartWireManager``, logging a
        refusal or an overwritten pct."""
        try:
            src = event.data.get("source_id", "")
            tgt = event.data.get("target_id", "")
            pct = event.data.get("pct", 0)
            if src and tgt:
                res = self._smart_wire_mgr.register_wire(src, tgt, pct) or {}
                if not res.get("applied"):
                    logger.warning(
                        "BotManager wire.created: engine REFUSED %s -> %s "
                        "@ %r (%s); anything drawing this wire is showing "
                        "a routing that will never carry profit",
                        src,
                        tgt,
                        pct,
                        res.get("reason", "no reason given"),
                    )
                elif res.get("replaced_pct") is not None:
                    logger.warning(
                        "BotManager wire.created: %s -> %s OVERWROTE an "
                        "existing %.2f%% with %.2f%%",
                        src,
                        tgt,
                        res["replaced_pct"],
                        res.get("pct", 0.0),
                    )
        except Exception as exc:
            logger.warning("BotManager wire.created handler raised: %s", exc)

    def _on_wire_removed_mgr(self, event) -> None:
        """Unregister the wire named by the event."""
        try:
            src = event.data.get("source_id", "")
            tgt = event.data.get("target_id", "")
            if src and tgt:
                self._smart_wire_mgr.unregister_wire(src, tgt)
        except Exception as exc:
            logger.warning("BotManager wire.removed handler raised: %s", exc)

    def set_state_manager(self, sm) -> None:
        """Attach a StateManager for persistence."""
        self._state_manager = sm

    def set_ta_weights(self, weights) -> None:
        """Hold the indicator weights every bot built from here votes with.

        Set before ``restore_bots_from_state`` so a restored bot carries the
        figures the Settings dialog stored. None leaves each bot on
        ``ta_engine.DEFAULT_WEIGHTS``.
        """
        self._ta_weights = dict(weights) if weights else None
        logger.info(
            "TA weights attached to BotManager (%d names)",
            0 if not self._ta_weights else len(self._ta_weights),
        )

    @property
    def ta_weights(self):
        """The indicator weights a new bot is built with, or None."""
        return None if self._ta_weights is None else dict(self._ta_weights)

    def push_ta_weights(self, weights) -> int:
        """Hold ``weights`` and hand them to every bot already built.

        ``set_ta_weights`` holds without pushing, which is what the launch path
        wants: a restored bot is built with the figures rather than given them
        afterwards. This one is for a weight the operator saves while bots run,
        and it returns how many bots took it.
        """
        self.set_ta_weights(weights)
        reached = 0
        for bot in list(self._bots.values()):
            taker = getattr(bot, "set_ta_weights", None)
            if taker is None:
                continue
            taker(self._ta_weights)
            reached += 1
        logger.info(
            "TA weights pushed to %d of %d running bots", reached, len(self._bots)
        )
        return reached

    def force_fire(self, bot_id: str, aggressive: bool = False) -> bool:
        """Call ``force_fire`` on ``bot_id``; returns False for an
        unknown bot or one without ``scrum_target_mode``."""
        bot = self._bots.get(bot_id)
        if bot is None:
            return False
        try:
            # Fall back to the no-argument signature on TypeError.
            try:
                bot.force_fire(aggressive=aggressive)
            except TypeError:
                bot.force_fire()
            return hasattr(bot, "scrum_target_mode")
        except Exception as exc:
            logger.warning("force_fire failed on %s: %s", bot_id, exc)
            return False

    def set_data_pool(self, pool) -> None:
        """Attach shared MarketDataPool for efficient API usage."""
        self._data_pool = pool
        for bot in self._bots.values():
            bot._data_pool = pool
        logger.info(
            "DataPool attached to BotManager (%d existing bots)", len(self._bots)
        )

    def _connectors_by_exchange(self) -> dict:
        """One live connector per distinct ``exchange_id`` in the fleet."""
        out: dict = {}
        for bot_id, bot in self._bots.items():
            try:
                exch_id = getattr(bot.config, "exchange_id", None)
                conn = getattr(bot, "exchange", None)
            except Exception as exc:
                # Skip a container whose handles cannot be read, and say which.
                logger.warning(
                    "Ticker refresh: cannot read exchange handle for %s "
                    "(%s); that bot keeps its own fetch path.",
                    bot_id,
                    exc,
                )
                continue
            if exch_id and conn is not None and exch_id not in out:
                out[exch_id] = conn
        return out

    async def refresh_all_tickers_once(self) -> int:
        """One bulk ticker refresh across every exchange in the fleet."""
        pool = getattr(self, "_data_pool", None)
        if pool is None or not hasattr(pool, "refresh_all_tickers"):
            return 0
        total = 0
        for exch_id, conn in self._connectors_by_exchange().items():
            try:
                total += await pool.refresh_all_tickers(conn, exch_id)
            except Exception as exc:
                logger.warning("Bulk ticker refresh raised for %s: %s", exch_id, exc)
        return total

    async def _ticker_refresh_loop(self, interval: float) -> None:
        """Refresh the shared ticker cache every ``interval`` seconds
        until ``_ticker_refresh_stop``."""
        logger.info("Bulk ticker refresher started (every %.1fs)", interval)
        while not self._ticker_refresh_stop:
            try:
                await asyncio.sleep(interval)
                if self._ticker_refresh_stop:
                    break
                await self.refresh_all_tickers_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Ticker refresh cycle failed: %s", exc)
        logger.info("Bulk ticker refresher stopped.")

    def start_ticker_refresher(self, interval: float = 5.0) -> bool:
        """Launch the refresher on the manager's loop; idempotent."""
        if getattr(self, "_ticker_refresh_task", None) is not None:
            return False
        loop = getattr(self, "_async_loop", None)
        if loop is None:
            logger.warning("Bulk ticker refresher not started: no async loop attached.")
            return False
        self._ticker_refresh_stop = False
        self._ticker_refresh_task = asyncio.run_coroutine_threadsafe(
            self._ticker_refresh_loop(interval), loop
        )
        return True

    def stop_ticker_refresher(self) -> None:
        task = getattr(self, "_ticker_refresh_task", None)
        self._ticker_refresh_stop = True
        if task is not None:
            task.cancel()
            self._ticker_refresh_task = None

    def set_async_loop(self, loop) -> None:
        """Attach the persistent asyncio loop used for BotManager
        coroutines."""
        self._async_loop = loop
        logger.info(
            "AsyncLoop attached to BotManager (id=%s)",
            id(loop) if loop is not None else "None",
        )

    def _dispatch_bootstrap(self, bot, source: str) -> None:
        """Run ``bot.bootstrap_exchange_state()`` on the persistent
        loop, or in a daemon thread when no loop is attached."""
        coro = bot.bootstrap_exchange_state()
        loop = self._async_loop
        if loop is not None and not loop.is_closed():
            try:
                fut = asyncio.run_coroutine_threadsafe(coro, loop)

                def _on_done(_fut, _bid=bot.bot_id, _src=source):
                    try:
                        _exc = _fut.exception()
                    except Exception as _probe_exc:
                        logger.debug(
                            "Bot %s bootstrap (%s) future probe raised %s",
                            _bid,
                            _src,
                            _probe_exc,
                        )
                        return
                    if _exc is not None:
                        logger.warning(
                            "Bot %s bootstrap dispatch (%s) raised: %s",
                            _bid,
                            _src,
                            _exc,
                        )

                fut.add_done_callback(_on_done)
            except Exception as exc:
                logger.warning(
                    "Bot %s bootstrap scheduling (%s) failed: %s",
                    bot.bot_id,
                    source,
                    exc,
                )
            return
        # Close the coroutine before starting a fresh one; an unawaited
        # coroutine raises RuntimeWarning.
        try:
            coro.close()
        except Exception as _close_exc:
            logger.debug(
                "Bot %s could not close the unused start-up job from "
                "%s (%s). Carrying on to start a fresh one.",
                bot.bot_id,
                source,
                _close_exc,
            )
        try:
            import threading
            import asyncio as _aio

            def _boot(_b=bot, _src=source):
                try:
                    _aio.run(_b.bootstrap_exchange_state())
                except Exception as _exc:
                    logger.warning(
                        "Bot %s bootstrap dispatch (%s, fallback) failed: %s",
                        _b.bot_id,
                        _src,
                        _exc,
                    )

            threading.Thread(
                target=_boot,
                daemon=True,
                name=f"bot-bootstrap-{source[:6]}-{bot.bot_id[:8]}",
            ).start()
        except Exception as exc:
            logger.warning(
                "Bot %s bootstrap scheduling (%s, fallback) failed: %s",
                bot.bot_id,
                source,
                exc,
            )

    def set_live_monitor(self, monitor) -> None:
        """Attach LiveMonitor for AI feedback loop."""
        self._live_monitor = monitor
        logger.info(
            "LiveMonitor attached to BotManager (enabled=%s)",
            monitor.enabled if monitor else False,
        )

    def configure_live_monitor(self, settings: dict) -> None:
        """Create or clear the LiveMonitor from ``settings``, reading
        enabled, api_key, interval_hours, connect_phrase and
        confirm_phrase. ``LiveMonitor.wait_hours`` refuses an interval
        ``should_check`` cannot count."""
        if not settings.get("enabled") or not settings.get("api_key"):
            self._live_monitor = None
            logger.info("LiveMonitor disabled")
            return
        from .live_monitor import LiveMonitor, TradeJournal

        journal = TradeJournal()
        self._live_monitor = LiveMonitor(
            api_key=settings["api_key"],
            journal=journal,
            interval_hours=settings.get(
                "interval_hours", LiveMonitor.DEFAULT_INTERVAL_HOURS
            ),
            connect_phrase=settings.get("connect_phrase", ""),
            confirm_phrase=settings.get("confirm_phrase", ""),
        )
        # interval_hours is the figure wait_hours kept, not the stored one.
        logger.info(
            "LiveMonitor configured (interval=%.1fh, phrase='%s')",
            self._live_monitor.interval_hours,
            settings.get("connect_phrase", "")[:20],
        )

    async def check_live_monitor(self) -> dict | None:
        """Return the AI feedback dict when a check is due, else None."""
        if not self._live_monitor or not self._live_monitor.enabled:
            return None
        if not self._live_monitor.should_check:
            return None
        total_port = 0.0
        contributing = 0
        for bot in self._bots.values():
            try:
                s = bot.get_status()
            except Exception as exc:
                logger.warning(
                    "live monitor: get_status failed for a bot (%s); it "
                    "is excluded from the portfolio total",
                    exc,
                )
                continue
            if "portfolio_value" in s:
                total_port += float(s.get("portfolio_value") or 0.0)
                contributing += 1
        if contributing < len(self._bots):
            logger.warning(
                "live monitor: only %d of %d bots reported a portfolio "
                "value; the figure sent for analysis is PARTIAL",
                contributing,
                len(self._bots),
            )
        result = await self._live_monitor.analyze(
            portfolio=total_port, passive=None, bots=len(self._bots)
        )
        if result.get("feedback"):
            self._bus.emit("ai.feedback", data=result)
            logger.info("AI feedback received: %s", result.get("feedback", "")[:80])
        return result

    @property
    def live_monitor_info(self) -> dict:
        """Return current LiveMonitor connection status."""
        if not self._live_monitor:
            return {"enabled": False, "authenticated": False, "checks": 0}
        return self._live_monitor.connection_info

    def set_connector(self, connector) -> None:
        """Attach the CcxtConnector, register every bot's symbol, and
        bootstrap each bot's exchange state."""
        self._connector = connector
        for bot in self._bots.values():
            connector.add_scan_symbol(bot.config.symbol)
            # Only fill an empty exchange handle; an existing one
            # is left alone.
            if not getattr(bot, "exchange", None) or bot.exchange is None:
                try:
                    bot.exchange = connector
                except Exception as _attach_exc:
                    logger.error(
                        "Bot %s would not accept the exchange connector "
                        "(%s). It has no connector and cannot trade "
                        "until one is attached.",
                        getattr(bot, "bot_id", "<unknown bot>"),
                        _attach_exc,
                    )
            if hasattr(bot, "bootstrap_exchange_state"):
                self._dispatch_bootstrap(bot, "set_connector")
        logger.info(
            "Connector attached to BotManager — "
            "%d symbol(s) registered for history scanning + bootstrap",
            len(self._bots),
        )

    async def _await_running(self, bot, timeout_seconds: float) -> bool:
        """Poll ``bot.state`` every 0.25 s and return True on RUNNING,
        False on ``timeout_seconds`` or on a ``cancel_start_all``."""
        poll_interval = 0.25
        elapsed = 0.0
        while elapsed < timeout_seconds:
            if getattr(self, "_start_all_cancel", False):
                return False
            if bot.state == BotState.RUNNING:
                return True
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        return False

    async def start_all(
        self,
        verify_timeout_seconds: float = 10.0,
        min_gap_seconds: float = START_ALL_GAP_SECONDS,
        eligible_filter: Optional[Callable[["BotContainer"], bool]] = None,
    ) -> None:
        """Start each eligible bot in turn, waiting up to
        ``verify_timeout_seconds`` for RUNNING and ``min_gap_seconds``
        between bots, retrying a bot that does not reach RUNNING exactly
        once, and emitting ``bot_manager.start_all_progress``."""
        eligible = [
            b
            for b in self._bots.values()
            if b.state in (BotState.IDLE, BotState.STOPPED)
            and (eligible_filter is None or eligible_filter(b))
        ]
        total = len(eligible)
        self._start_all_cancel = False
        self._bus.emit(
            "bot_manager.start_all_progress", phase="begin", total=total, started=0
        )
        if total == 0:
            self._bus.emit(
                "bot_manager.start_all_progress", phase="done", total=0, started=0
            )
            return
        for i, bot in enumerate(eligible):
            if getattr(self, "_start_all_cancel", False):
                self._bus.emit(
                    "bot_manager.start_all_progress",
                    phase="cancelled",
                    total=total,
                    started=i,
                )
                return
            self._bus.emit(
                "bot_manager.start_all_progress",
                phase="bot_starting",
                total=total,
                started=i,
                bot_id=bot.bot_id,
            )
            await bot.start()
            verified = await self._await_running(bot, verify_timeout_seconds)
            if not verified and not getattr(self, "_start_all_cancel", False):
                logger.warning(
                    "Bot %s did not reach RUNNING in %.1fs; retrying once",
                    bot.bot_id,
                    verify_timeout_seconds,
                )
                # stop() first: start() on a STARTING bot returns without
                # replacing the task, so a bare second start does nothing.
                await asyncio.sleep(min_gap_seconds)
                await bot.stop()
                await bot.start()
                verified = await self._await_running(bot, verify_timeout_seconds)
            if verified:
                self._bus.emit(
                    "bot_manager.start_all_progress",
                    phase="bot_started",
                    total=total,
                    started=i + 1,
                    bot_id=bot.bot_id,
                )
            else:
                # A timed-out bot may still come up; move to the next one.
                logger.warning(
                    "Bot %s is not RUNNING after %.1fs; start_all moved on",
                    bot.bot_id,
                    verify_timeout_seconds,
                )
                self._bus.emit(
                    "bot_manager.start_all_progress",
                    phase="bot_timeout",
                    total=total,
                    started=i + 1,
                    bot_id=bot.bot_id,
                    timeout_seconds=verify_timeout_seconds,
                )
            if i < len(eligible) - 1:
                await asyncio.sleep(min_gap_seconds)
        self._bus.emit(
            "bot_manager.start_all_progress", phase="done", total=total, started=total
        )

    def cancel_start_all(self) -> None:
        """Abort an in-flight ``start_all`` after the current bot's
        start."""
        self._start_all_cancel = True

    async def stop_all(self) -> None:
        tasks = [bot.stop() for bot in self._bots.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def pause_all(self) -> None:
        for bot in self._bots.values():
            if bot.state == BotState.RUNNING:
                await bot.pause()

    async def resume_all(self) -> None:
        for bot in self._bots.values():
            if bot.state == BotState.PAUSED:
                await bot.resume()
