"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
bot_container.py — Isolated auto-trader container
===================================================
Each Auto Trader Container runs as an independent asyncio task with its
own error boundary.  A container crash does NOT propagate to other bots
or the main application.

Architecture:
  • Each bot has a unique ``bot_id`` and is bound to exactly one
    exchange, one base currency, and one target asset.
  • The ``BotManager`` oversees all containers, handles lifecycle
    (start/stop/restart), and aggregates status for the main window.
  • Containers communicate with the rest of the app exclusively via
    the EventBus — no shared mutable state.

Fault isolation strategy:
  • Each bot runs inside ``_run_with_guard()`` which catches ALL
    exceptions and emits ``bot.error`` events instead of crashing.
  • After N consecutive failures, the bot enters a cooldown state.
  • The manager can restart individual bots without affecting others.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # Names used only to describe what a value is, never to run
    # anything. guarded_place_order writes its order side, its order
    # kind and its return value as quoted names. This file turns every
    # such description into plain text at import time, so none of these
    # is ever looked up while the program runs. Naming them here lets
    # the checking tools find them; it adds no import when the program
    # runs, so it cannot cause an import loop and cannot slow start-up.
    # guarded_place_order still imports the real ones itself when it
    # needs to compare or build an order.
    from ..exchange.base import (
        ExchangeInterface,
        Order,
        OrderSide,
        OrderType,
    )

from ..core.event_bus import get_event_bus
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
    despawn_preview,
    despawn_threshold_days,
    make_bot_config,
)

logger = logging.getLogger("acervator.bot")

__all__ = [
    "DESPAWN_MAX_DAYS",
    "DESPAWN_PREVIEW_WINDOWS",
    "DOLLAR_PEGGED_CURRENCIES",
    "STACK_MODE_DEFAULT",
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
    "despawn_preview",
    "despawn_threshold_days",
    "make_bot_config",
]


# ---------------------------------------------------------------------------
# Bot container
# ---------------------------------------------------------------------------
class BotContainer:
    """
    Isolated auto-trader container.  Subclassed by ``ScrummingBot`` (the
    only remaining engine; ``GridBot`` was deleted v3.16.0). Original
    docstring left intact below for historical context. New text:
    ``ScrummingBot`` which implement the mode-specific trading logic.

    Lifecycle::

        bot = ScrummingBot(config, exchange)
        await bot.start()     # Begins the trading loop
        await bot.pause()     # Suspends without cancelling orders
        await bot.resume()    # Resumes from pause
        await bot.stop()      # Graceful shutdown
    """

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
        self._volume_guard = None  # Set by BotManager if available
        self._data_pool = None  # Set by BotManager if available
        # v3.15.78 — Pre-flight precision-check cache. Operator
        # directive 2026-04-27: "We should not be spamming the APIs
        # with improperly valued orders." Maps symbol → (min_amount,
        # min_cost, amount_precision). Lazy-loaded from
        # exchange.get_markets() on first need; refreshed only when
        # explicitly invalidated. Markets rarely change at the
        # min-precision level so a long-lived cache is safe.
        self._market_limits_cache: dict[str, tuple] = {}
        # ------------------------------------------------------------
        # Phantom settings — given a starting value HERE, on the shared
        # parent, so that get_full_state writes both keys for every bot.
        #
        # THE DEFECT THIS CLOSES: only ScrummingBot ever set
        # _phantoms_enabled, and it does so in its own constructor.
        # Every other bot reached get_full_state with the attribute
        # missing, and the guarded read there simply left the key out.
        # A saved Extractor and a saved Scrumming bot therefore had
        # differently-shaped records, and nothing in the file said why.
        #
        # False is taken from the code, not chosen: ExtractorBot
        # declares enable_phantoms=False as its own default and never
        # stores the value, and restore_bots_from_state builds every
        # ExtractorBot with enable_phantoms=False. The Extractor is
        # exactly the bot that was missing the key. ScrummingBot
        # overwrites this line moments later from its own constructor
        # argument, so no phantom behaviour changes for it.
        self._phantoms_enabled: bool = False
        # Nothing in the codebase assigns _phantom_config, so the export
        # has never emitted this key for any bot at all. The empty
        # mapping is what "no phantom settings were recorded" looks
        # like. Restore reads no such key back, so no behaviour hangs
        # on the value — only the shape of the saved record changes.
        self._phantom_config: dict = {}

    def force_fire(self, aggressive: bool = False) -> None:
        """MEM-236 + MEM-241 — Manual Fire from the dashboard. Base
        implementation is a no-op; ScrummingBot overrides. Grid bots
        ignore (no equivalent rate-gate and no rebalance semantic).
        Called from the GUI thread via BotManager, so the
        implementation must be thread-safe and non-blocking — set a
        flag or counter; do NOT call async methods directly here.

        Args:
            aggressive: MEM-241. When True (new GUI default), the
                scrumming implementation executes a market-order
                rebalance-to-target bypassing TA/BB gates. When False,
                legacy MEM-236 behavior (flush tick-skip, run normal
                gate checks next tick).
        """
        return

    async def _get_market_limits(
        self,
        symbol: str,
    ) -> tuple[float, float, int]:
        """v3.15.78 — Return ``(min_amount, min_cost, amount_precision)``
        for ``symbol`` from the exchange's market metadata. Cached on
        the bot for the bot's lifetime (markets rarely change at the
        precision level). Returns ``(0.0, 0.0, 8)`` on any lookup
        failure so the caller fails-open rather than blocking trades
        on metadata absence.

        Operator directive 2026-04-27: "We should not be spamming the
        APIs with improperly valued orders."

        sadp: R28 R44
        """
        cached = self._market_limits_cache.get(symbol)
        if cached is not None:
            return cached
        try:
            markets = await self.exchange.get_markets()
        except Exception as exc:
            logger.debug(
                "Bot %s could not fetch markets for precision check: %s",
                self.bot_id,
                exc,
            )
            # Negative-cache the failure briefly so we don't spam
            # get_markets() on every order. Fail-open with
            # zero-min so trades still flow.
            fallback = (0.0, 0.0, 8)
            self._market_limits_cache[symbol] = fallback
            return fallback
        for m in markets or []:
            if getattr(m, "symbol", None) == symbol:
                limits = (
                    float(getattr(m, "min_amount", 0.0) or 0.0),
                    float(getattr(m, "min_cost", 0.0) or 0.0),
                    int(getattr(m, "amount_precision", 8) or 8),
                )
                self._market_limits_cache[symbol] = limits
                return limits
        # Symbol not in markets list — cache zero so we don't re-loop
        fallback = (0.0, 0.0, 8)
        self._market_limits_cache[symbol] = fallback
        return fallback

    async def guarded_place_order(
        self,
        symbol: str,
        side: "OrderSide",
        order_type: "OrderType",
        amount: float,
        price: Optional[float] = None,
        purpose: str = "trade",
    ) -> "Order":

        # sadp: R28 R29  # order placement: fail-loudly(R28) idempotent(R29)
        """
        Place an order through the VolumeGuard if available.
        Falls back to direct exchange.place_order if guard is disabled/absent.

        v3.15.78 — Pre-flight precision check. If the rounded amount is
        below the exchange's ``min_amount`` for ``symbol``, OR the
        notional cost (amount × price) is below ``min_cost``, raise a
        ``PRE-FLIGHT REJECTED`` exception WITHOUT calling the exchange.
        Operator directive 2026-04-27: "We should not be spamming the
        APIs with improperly valued orders." Caught by the existing
        SCRUM/FOLD failure-handling at every call site (which logs
        ``SELL FAILED: {exc}`` / ``BUY FAILED: {exc}``); the
        ``PRE-FLIGHT REJECTED`` prefix in the message lets the operator
        distinguish locally-rejected orders from exchange-rejected
        ones at a glance.
        """
        from ..exchange.base import OrderSide, OrderType, Order, OrderStatus

        # ============================================================
        # THE AMOUNT MUST BE A NUMBER. NOTHING ELSE REACHES THE VENUE.
        # ============================================================
        # Every dispatch path out of this method is BELOW this block:
        # the VolumeGuard call and the direct exchange call. Both hand
        # the caller's ``amount`` object on unchanged, so this is the
        # only place that can refuse it.
        #
        # THE SIZE CHECK BELOW CANNOT DO THIS JOB. It reads
        # ``float(amount)`` inside a try that yields 0.0 on failure,
        # and it decides with ``<``. Both steps are blind to a NaN:
        # ``math.floor(nan * scale)`` raises ValueError, which drops
        # the test back to ``_amt < _min_amount``, and every
        # comparison against NaN is False. A NaN amount therefore
        # passed the size check and was handed to the exchange. A live
        # path produces one: when standing_surplus_usd cannot be read
        # the fold preview returns NaN, and that value is an addend in
        # buy_usd_target.
        #
        # THE TYPE TEST IS EXACT, NOT ``isinstance``. An isinstance
        # test admits every subclass, so ``bool`` passes it and
        # ``float(True)`` then makes True look like a one-unit order.
        # It also admits a float subclass, an int subclass, an IntEnum
        # member and every numpy scalar. The abstract types do not
        # describe the domain either: measured on Python 3.14, ``bool``
        # passes numbers.Real, ``Decimal`` fails it and ``Fraction``
        # passes it. A type is not a domain. An exact type test cannot
        # be spoofed from Python.
        #
        # THIS REFUSAL IS LOUDER THAN THE SIZE REFUSAL BELOW, and it
        # should be. An order below the exchange minimum is ordinary
        # market friction. An amount that is not a finite positive
        # number means an upstream invariant is ALREADY broken, so it
        # is logged at error level here, where the bot and the symbol
        # are both known.
        _side_str = "BUY" if side == OrderSide.BUY else "SELL"
        _amt_is_number = type(amount) in (int, float)
        _amt = 0.0
        if _amt_is_number:
            try:
                _amt = float(amount)
            except (TypeError, ValueError, OverflowError):
                # An int too large for a float lands here. It has no
                # float value, so it has no usable size.
                # ``math.isfinite`` would raise OverflowError on it for
                # the same reason, which is why the conversion is
                # guarded here rather than left to the test below.
                _amt_is_number = False
                _amt = 0.0
        if not _amt_is_number or not math.isfinite(_amt) or _amt <= 0.0:
            # ``math.isfinite`` is read BEFORE the positivity test on
            # purpose. ``nan <= 0.0`` is False, so a positivity test
            # alone would pass a NaN straight through.
            logger.error(
                "Bot %s PRE-FLIGHT REJECTED %s %s: amount is not a finite "
                "positive number: %r (type %s). Upstream produced an "
                "unusable size; the API was not called.",
                getattr(self, "bot_id", "?"),
                _side_str,
                symbol,
                amount,
                type(amount).__name__,
            )
            raise Exception(
                f"PRE-FLIGHT REJECTED: {_side_str} {symbol} amount is not "
                f"a finite positive number: {amount!r} "
                f"(type {type(amount).__name__}). An amount that is not a "
                f"number cannot be sized, compared or sent, and this one "
                f"means an upstream value is already corrupt. "
                f"API not called."
            )

        # ============================================================
        # v3.15.78 — Pre-flight precision check.
        # ============================================================
        # Look up the exchange's min_amount / min_cost for this symbol.
        # Round the requested amount to amount_precision before the
        # comparison (the exchange does this internally; if our amount
        # rounds to zero or below min, the exchange rejects with
        # "amount precision" errors like the operator-reported RAVE
        # case from 2026-04-27).
        try:
            _min_amount, _min_cost, _amount_prec = await self._get_market_limits(symbol)
        except Exception:  # R28-OK: market-limits probe; safe defaults if fetch fails
            _min_amount, _min_cost, _amount_prec = 0.0, 0.0, 8

        # Truncate (NOT round) the amount to the exchange's precision.
        # Banker's rounding (Python's default) would let 0.05 RAVE pass
        # a 0.1-min check by rounding UP to 0.1, but the exchange itself
        # truncates excess precision. Truncation matches reality.
        #
        # The size test below is made in WHOLE STEPS, not in fractions
        # of a coin. A step is the smallest size the exchange will
        # accept for this symbol. Both sides are scaled up by the same
        # power of ten, so the test compares two whole counts of the
        # same thing. Nothing is divided to reach the verdict, and
        # comparing whole counts cannot drift the way comparing
        # fractions can.
        #
        # The two sides round in OPPOSITE directions, on purpose:
        #   • the requested size rounds DOWN, because the exchange
        #     throws away any size below a whole step;
        #   • the minimum rounds UP, because a minimum of any size at
        #     all still demands at least one whole step. Rounding the
        #     minimum down would turn a minimum smaller than one step
        #     into a minimum of zero, and a zero-size order would then
        #     be handed to the exchange instead of being refused here.
        #
        # ``_amt_trunc`` below is still worked out, but only so the
        # rejection message can quote the truncated size back to the
        # operator.
        import math as _math

        _amt_steps: Optional[int] = None
        _min_steps: Optional[int] = None
        if _amount_prec >= 0:
            try:
                _scale = 10 ** int(_amount_prec)
                _amt_steps = _math.floor(_amt * _scale)
                _min_steps = _math.ceil(_min_amount * _scale)
                _amt_trunc = _amt_steps / _scale
            except (TypeError, ValueError, OverflowError):
                _amt_steps = None
                _min_steps = None
                _amt_trunc = _amt
        else:
            _amt_trunc = _amt

        # When the step counts could not be worked out (precision is
        # negative, or the scaling overflowed) fall back to comparing
        # the untruncated size, exactly as before.
        if _amt_steps is None or _min_steps is None:
            _below_min = _amt < _min_amount
        else:
            _below_min = _amt_steps < _min_steps
        if _min_amount > 0 and _below_min:
            raise Exception(
                f"PRE-FLIGHT REJECTED: {_side_str} amount {_amt:.8f} "
                f"({_amt_trunc:.{max(_amount_prec,0)}f} after truncating "
                f"to precision={_amount_prec}) is below {symbol} "
                f"min_amount {_min_amount}. API not called."
            )

        if _min_cost > 0 and price is not None:
            try:
                _px = float(price)
            except (TypeError, ValueError):
                _px = 0.0
            if _px > 0:
                _notional = _amt * _px
                if _notional < _min_cost:
                    raise Exception(
                        f"PRE-FLIGHT REJECTED: {_side_str} notional "
                        f"${_notional:.4f} ({_amt:.8f} \u00d7 ${_px:.8f}) "
                        f"is below {symbol} min_cost ${_min_cost:.4f}. "
                        f"API not called."
                    )

        # ============================================================
        # End of pre-flight check. Continue to existing dispatch.
        # ============================================================

        if self._volume_guard and self._volume_guard.enabled:
            side_str = "buy" if side == OrderSide.BUY else "sell"
            ot_str = "market" if order_type == OrderType.MARKET else "limit"
            report = await self._volume_guard.execute(
                symbol,
                side_str,
                amount,
                price=price or 0,
                order_type=ot_str,
                exchange=self.exchange,
            )

            if not report.success:
                raise Exception(f"VolumeGuard execution failed: {report.reason}")

            # Construct a synthetic Order from the report
            return Order(
                id=f"vg_{int(time.time()*1000)}",
                symbol=symbol,
                side=side,
                type=order_type,
                amount=report.requested_amount,
                price=report.avg_fill_price,
                filled=report.executed_amount,
                remaining=report.requested_amount - report.executed_amount,
                average=report.avg_fill_price,
                status=(
                    OrderStatus.CLOSED
                    if report.executed_amount > 0
                    else OrderStatus.FAILED
                ),
                timestamp=time.time(),
            )

        # ============================================================
        # v3.15.98 — TD-004 idempotency closure.
        # ============================================================
        # Derive a deterministic client_order_id from the trade INTENT
        # (symbol + side + amount + price + bot_id + purpose + session
        # nonce). On retry of the same intent within TTL the same coid
        # is reused; the exchange refuses the duplicate (Coinbase 409,
        # Binance -2010), preventing double-fills from network-timeout
        # retry storms. See src/exchange/idempotency.py for the full
        # design rationale.
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

        # No guard — direct execution
        try:
            order = await self.exchange.place_order(
                symbol, side, order_type, amount, price, client_order_id=_coid
            )
            _idem.mark_fulfilled(_intent)
            return order
        except Exception:
            # On non-409 rejection, invalidate so a future legitimate
            # retry can generate a fresh coid. We can't always tell from
            # here whether it was 409 (duplicate, GOOD — keep) vs other
            # 4xx (invalidate); err on the side of keeping cached. The
            # TTL window will evict if it never resolves.
            raise

    # -- Lifecycle ------------------------------------------------------
    async def start(self) -> None:
        """Launch the bot's trading loop in a guarded asyncio task."""
        if self.state in (BotState.RUNNING, BotState.STARTING):
            logger.warning("Bot %s already running", self.bot_id)
            return

        # v3.15.98 — clear stale last_error on (re)start. Operator-reported
        # 2026-04-28: a NameError captured during a prior run kept showing
        # in the dashboard "Last Error" panel after the bug was fixed,
        # making it impossible to tell whether the latest start was clean
        # or still broken. Stamp a fresh start: reset the error and consec
        # counter so the panel reflects the CURRENT session.
        self.stats.last_error = ""
        self.stats.consecutive_errors = 0

        self.state = BotState.STARTING
        self._stop_event.clear()
        self._start_time = time.monotonic()
        # Register with shared data pool
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
        """Gracefully stop the bot and cancel remaining orders."""
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
        # Unregister from shared data pool
        if self._data_pool:
            self._data_pool.unregister(
                self.config.exchange_id,
                self.config.symbol,
                getattr(self.config, "ta_timeframe", "1h"),
            )
        self._bus.emit("bot.stopped", bot_id=self.bot_id)
        logger.info("Bot %s stopped", self.bot_id)

    async def pause(self) -> None:
        """Suspend the trading loop without cancelling orders."""
        self._pause_event.clear()
        self.state = BotState.PAUSED
        self._bus.emit("bot.paused", bot_id=self.bot_id)

    async def resume(self) -> None:
        """Resume from paused state."""
        self._pause_event.set()
        self.state = BotState.RUNNING
        self._bus.emit("bot.resumed", bot_id=self.bot_id)

    # -- Fault-isolated execution wrapper --------------------------------
    async def _run_with_guard(self) -> None:
        # sadp: R28 R32  # circuit-breaker wrapper(R32) fail-loudly(R28)
        """
        Wraps the trading loop in a fault boundary.  All exceptions are
        caught, logged, and emitted as events.  After MAX_CONSECUTIVE_ERRORS,
        the bot enters cooldown before retrying.
        """
        self.state = BotState.RUNNING
        try:
            while not self._stop_event.is_set():
                try:
                    # Wait if paused
                    await self._pause_event.wait()
                    if self._stop_event.is_set():
                        break

                    # === MAIN TRADING TICK ===
                    await self.tick()

                    # Reset error counter on success
                    self.stats.consecutive_errors = 0
                    # v3.24.40 (C54 / NF-122) — clear the ERROR state a
                    # failing tick set below. Only ERROR is cleared:
                    # COOLDOWN owns its own transition back to RUNNING,
                    # and PAUSED/STOPPING must not be overwritten by a
                    # tick that happened to succeed.
                    if self.state == BotState.ERROR:
                        self.state = BotState.RUNNING

                    # v3.16.5 — heartbeat update of uptime_seconds. The
                    # dashboard reads this via get_status_dict; without
                    # the heartbeat, the operator-facing Uptime display
                    # never increments while the bot is running. Cheap
                    # operation; safe to do every tick.
                    if self._start_time:
                        self.stats.uptime_seconds = time.monotonic() - self._start_time

                except asyncio.CancelledError:
                    raise  # Let cancellation propagate
                except Exception as exc:
                    self.stats.consecutive_errors += 1
                    self.stats.total_errors += 1  # v3.16.46 — cumulative, never resets
                    self.stats.last_error = f"{type(exc).__name__}: {exc}"
                    # v3.24.40 (C54 / NF-122) — BotState.ERROR was
                    # assigned NOWHERE in src/. It was only ever
                    # compared against, in get_aggregate_stats, so the
                    # dashboard's current-state "Errors" count was
                    # structurally pinned at zero: a bot could fail
                    # every tick and the fleet still reported 0 errored.
                    # The state machine went RUNNING -> COOLDOWN (at 5
                    # consecutive) -> RUNNING and skipped ERROR
                    # entirely. Set it here so a failing bot is visible
                    # from the first failure rather than the fifth.
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

                # Tick interval — subclasses can override
                await asyncio.sleep(self.tick_interval)

        except asyncio.CancelledError:
            pass
        finally:
            self.stats.uptime_seconds = time.monotonic() - self._start_time

    # -- Subclass hooks -------------------------------------------------
    @property
    def tick_interval(self) -> float:
        # sadp: R28 R29  # base tick: fail-loudly(R28) idempotent-order(R29)
        """Seconds between trading ticks.  Override in subclasses."""
        return 5.0

    async def tick(self) -> None:

        # sadp: R28 R29  # base tick: fail-loudly(R28) idempotent-order(R29)
        """
        One iteration of the trading loop.  Subclasses MUST override this
        with their mode-specific logic (grid management or scrumming).
        """
        raise NotImplementedError("Subclasses must implement tick()")

    # -- Status ---------------------------------------------------------
    def get_status(self) -> dict:
        """Return a snapshot of the bot's state and stats."""
        # MEM-236 — expose scrum SEARCH/TRACK/FIRE phase when this is a
        # scrumming bot subclass, so the GUI can pace tracking beeps.
        # None for grid bots (they don't have this phase machine).
        scrum_mode = getattr(self, "scrum_target_mode", None)
        # MEM-241 — armed_action is 'scrum' / 'fold' / None based on
        # delta sign. Drives the Fire button's internal color so the
        # operator sees whether pressing Fire will sell (scrum/red) or
        # buy (fold/green). None on grid bots and on scrumming bots
        # within the dust band around target.
        armed_action = getattr(self, "armed_action", None)
        # MEM-244 — Risk Control state for dashboard indicators
        anchor_tb = getattr(self, "_anchor_target_balance", None)
        ceiling_usd = getattr(self, "position_ceiling_usd", None)
        ceiling_ratio = getattr(self, "ceiling_ratio", None)
        fold_taper = getattr(self, "fold_rate_taper", 1.0)

        # v3.24.50 (Phase 1 Step 3) — how much queued tranche capital
        # exceeds one whole cycle's budget. issue #133 unit 10: a
        # tranche that does not fit is PART-CONSUMED, not skipped.
        # `_plan_fold_consumption` takes `take_usd = room` from it and
        # leaves the remainder queued, so this counts tranches needing
        # more than one cycle to fold back in full.
        # Computed defensively: a status call must never raise.
        # Issue #106 - the budget below reads `cycle_growth_cap_usd`
        # rather than respelling `anchor * pct/100`: the cap compounds
        # off the grown target now and this readout must move with it.
        # `getattr` like the MEM-244 probes - a grid bot has no cap.
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
        except Exception as _oc_exc:  # noqa: BLE001 - status must not raise
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
            "scrum_target_mode": scrum_mode,  # MEM-236
            "armed_action": armed_action,  # MEM-241
            # MEM-244 Risk Controls
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
            # v3.24.50 (Phase 1 Step 3) — the COMPOUNDING SURFACE.
            #
            # `target_balance` above is `config.target_balance`: the
            # operator's input, which compounding does not move. The
            # number the bot actually trades against is the runtime
            # `_target_balance`, and it was exported nowhere, so no GUI
            # could show whether compounding had done anything. That is
            # the mechanism behind the target-delta drift docket.
            #
            # Read-only additions. Nothing consumes these to make a
            # trading decision; they exist so Phase 2 and Phase 3 are
            # observable, because the failure mode this whole cascade is
            # fixing is "it silently did nothing and nobody could tell".
            "live_target_balance": float(getattr(self, "_target_balance", 0.0) or 0.0),
            "standing_surplus_usd": float(
                getattr(self, "_standing_surplus_usd", 0.0) or 0.0
            ),
            "fold_cycle_cap_consumed": float(
                getattr(self, "_fold_cycle_cap_consumed", 0.0) or 0.0
            ),
            # Issue #106 - this export and the enforcement drifted apart
            # the moment the target first grew. Same property the bot
            # enforces with, so row and bound are now one number.
            "cycle_growth_budget_usd": round(
                float(getattr(self, "cycle_growth_cap_usd", 0.0) or 0.0), 8
            ),
            # How much queued tranche capital the per-cycle filter can
            # never admit, because a tranche is only taken if it fits
            # ENTIRELY. Counted here rather than in the GUI so the
            # arithmetic lives beside the fields it reads.
            **_over_cap_summary,
            "ta_timeframe": getattr(self.config, "ta_timeframe", "1h") or "1h",
            # MEM-248: expose current_holdings so the GUI Ammo column can
            # compute position_value = holdings × price even when the tick
            # loop hasn't yet populated stats.position_value. Without this,
            # idle / freshly-restored bots that actually hold positions
            # rendered as "$0.00 at center line" — dangerously hiding real
            # exposure (operator caught this on an XRP bot that had 104.8
            # XRP ≈ $149.85 but showed Ammo $0.0000).
            "current_holdings": float(getattr(self, "_current_holdings", 0.0)),
            # v3.15.55 — quote→USD multiplier so the GUI can render
            # USD-correct Ammo/position even on crypto-quoted pairs
            # (BTC/ETH, anything/BTC). 1.0 for USD-quoted pairs (no-op).
            "quote_to_usd": float(getattr(self, "_quote_to_usd", 1.0) or 1.0),
            "stats": {
                # v3.23.24 — prefer exchange_trade_count (from
                # get_my_trades / compute_position_health, refreshed
                # every 5min) when a refresh has landed. Falls back to
                # the internal counter for the first ~5min after bot
                # start, and for exchanges without get_my_trades.
                # Directive: position-health values belong to the
                # exchange, not internal accumulators.
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
                # v3.16.5 — live uptime computation. Operator-reported
                # 2026-04-28: dashboard Uptime field never incremented
                # despite bots running normally. Root cause: stats.uptime_seconds
                # was only updated in stop() and the tick-loop finally
                # block — while the bot was RUNNING, it stayed at the
                # dataclass default (0.0). Compute the live elapsed time
                # here so the dashboard always sees the current value.
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
                # v3.24.40 (C54 / NF-83) — THIS BOT'S OWN accumulators.
                # Consumers read these per row; the producer never
                # emitted them, so anything reading them off a status
                # dict got nothing. They must come from self.stats, NOT
                # from BotManager.get_aggregate_stats: that is a
                # fleet-wide sum, and sourcing a per-bot key from it
                # would make every row show the fleet total.
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
            },
            # v3.24.40 (C54) — this bot's contribution to portfolio
            # value, at the TOP level because check_live_monitor reads
            # it off the status root. There is no separate
            # portfolio_value field on BotStats; a single bot's
            # portfolio contribution IS its position value.
            "portfolio_value": round(
                getattr(self.stats, "position_value", 0.0) or 0.0, 4
            ),
            # v3.16.16 — auto-fire eligibility snapshot from last tick.
            # GUI fire button reads this to render solid (auto would
            # fire) vs outline (manual override only) and tooltip the
            # specific blocking gate(s). Falls back to defaults for
            # bot subclasses that don't maintain _last_gate_state.
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
        """Export complete bot state for persistence. Includes config, stats,
        grid levels, and all data needed to restore without re-executing trades."""
        from dataclasses import asdict

        state = {
            "bot_id": self.bot_id,
            "state_when_saved": self.state.value,
            "config": asdict(self.config),
            "stats": asdict(self.stats),
            "saved_at": time.time(),
        }
        # Config mode is an enum — convert to string
        state["config"]["mode"] = self.config.mode.value

        # v3.20.4 — grid_levels save block removed (grid_bot deleted
        # v3.16.0). No live ScrummingBot/ExtractorBot has a `grid`
        # attribute; the legacy block was dead code.

        # Scrumming bot: save phantom config
        if hasattr(self, "_phantom_config"):
            state["phantom_config"] = self._phantom_config

        # v3.16.27 P0g — save the phantom enabled flag so operator's
        # explicit OFF state survives shutdown. Operator-reported
        # 2026-05-05: "On bot restart, phantom bots are activating
        # despite being turned off prior to shut down." Root cause was
        # that this flag was never persisted — restore always fell
        # back to ScrummingBot.__init__'s default `enable_phantoms=True`.
        if hasattr(self, "_phantoms_enabled"):
            state["phantoms_enabled"] = bool(self._phantoms_enabled)

        # MEM-245 — Scrumming bot compounding state (main_lots,
        # fold_tranches, accumulation state). Without this, every
        # restart reseeds main_lots at current price and starts with
        # zero tranches, resetting the compounding mechanism.
        #
        # The exporter belongs to ScrummingBot, not to this shared
        # parent, so it is fetched by name with a default rather than
        # read straight off self. Same guard as before, same skip when
        # the bot has no exporter, and the same warning if the exporter
        # itself misbehaves — but now there is no window in which the
        # attribute can vanish between the check and the call. This
        # matches how the auto-fire snapshot above reads
        # _last_gate_state.
        _export_scrumming = getattr(self, "export_scrumming_state", None)
        if _export_scrumming is not None:
            try:
                state["scrumming_state"] = _export_scrumming()
            except Exception as exc:
                logger.warning(
                    "export_scrumming_state failed on %s: %s", self.bot_id, exc
                )

        # v3.20.4 — Extractor runtime state (positions, chunk, hedge,
        # watch list, tick counter). Without this, every restart of a
        # persisted Extractor would lose all open positions + the
        # chunk/hedge balances would reset to construction defaults.
        # Symmetric to scrumming_state above; gated on the bot's mode
        # so we only emit the key for actual Extractors (avoids inflating
        # state files for ScrummingBots that happen to inherit
        # export_state from a future refactor).
        # sadp: R28 FL  R49 MDEL  R55 GOV  R68 DPA
        #
        # Fetched by name with a default, for the same reason as the
        # scrumming exporter above: this exporter belongs to
        # ExtractorBot, not to this shared parent. The mode check is
        # kept and still comes first.
        _export_extractor = getattr(self, "export_state", None)
        if self.config.mode == BotMode.EXTRACTOR and _export_extractor is not None:
            try:
                state["extractor_state"] = _export_extractor()
            except Exception as exc:
                logger.warning(
                    "export_state (extractor) failed on %s: %s", self.bot_id, exc
                )

        return state


# ---------------------------------------------------------------------------
# Bot manager — oversees all containers
# ---------------------------------------------------------------------------
class BotManager(StateRestoreMixin, BotRegistryMixin, FleetAggregationMixin):
    """
    Central registry for all bot containers.  Provides:
      - Create / start / stop / restart individual bots
      - Aggregate stats for the main window dashboard
      - Bulk operations (stop all, pause all)
      - State persistence (save/restore between sessions)
    """

    def __init__(self, bus=None) -> None:
        """v3.24.61 (C17 / SWARM-4.23) — `bus` is injectable.

        This constructor subscribes three handlers below, INSIDE
        `__init__`. A caller that rebinds `._bus` afterwards — which is
        exactly what `nuclear_controller.py:262` does, one line after
        constructing at :261 — is already too late: the subscriptions
        are latched on the process-wide bus and, until C17, could never
        be retracted.

        The leaked handlers are bound methods of an abandoned SIM
        manager, so they went on firing on LIVE events for the life of
        the process, three more per replay.

        Defaults to the process-wide bus, so every live construction
        site is unchanged.
        """
        self._bots: dict[str, BotContainer] = {}
        # Retained so the subscriptions can be taken off again. Every
        # caller of `subscribe` in src/ discarded these closures, which
        # is what made the leak unfixable from outside.
        self._bus_unsubs: list = []
        # v3.24.35 (C01 PR-0) — restore observation registries.
        #
        # save_state rebuilds "bots" solely from the registered set, so
        # a bot's absence from self._bots currently means BOTH "the
        # operator deleted it" and "restore could not load it" — and the
        # 60s save timer resolves that ambiguity by deleting the record
        # either way. Absence is not evidence.
        #
        # _restore_ledger is written ONLY by code that OBSERVED a bot
        # fail to load, so it can distinguish the two. PR-0 records and
        # reports; PR-1 uses it to decide what a save must carry.
        self._restore_ledger: dict[str, str] = {}  # bot_id -> reason
        self._boot_state_records: dict = {}  # bot_id -> record
        self._restore_completed: bool = False
        # C17 — resolved HERE, ~40 lines ahead of the three subscribes
        # below, so an injected bus is the one they land on.
        self._bus = bus if bus is not None else get_event_bus()
        self._state_manager = None
        self._volume_guard = None  # Shared VolumeGuard for all bots
        self._data_pool = None  # Shared MarketDataPool for API efficiency
        self._ticker_refresh_task = None  # Bulk ticker refresher handle
        self._ticker_refresh_stop = False
        self._live_monitor = None  # AI feedback loop (LiveMonitor)
        self._connector = None  # CcxtConnector — set via set_connector()
        # v3.20.71 Phase B-2 — CapitalRegistry broker integration.
        # Wired by main.py via set_capital_registry() AFTER settings.json
        # is loaded so initial_reservations can rehydrate from disk. When
        # None (e.g. in tests that don't construct the registry), register()
        # skips the reservation gate — keeps legacy test paths working.
        # Operator-locked Q3: register() returns (False, reason) on
        # over-allocation; the wizard surfaces the reason to the user
        # and does NOT add the bot. MEM-417.
        self._capital_registry = None
        # v3.16.19 — persistent asyncio loop reference. Set by
        # main.py via set_async_loop(). Used to route
        # bootstrap_exchange_state() onto the SAME loop that
        # bot.tick() runs on, so any asyncio.Lock instances
        # acquired during bootstrap (e.g., the v3.16.17 data_pool
        # ticker-coalescing locks) bind to the right loop and
        # don't poison the cache when the throwaway thread
        # finishes. Operator-reported runtime bug 2026-05-01:
        # "RuntimeError: <Lock object [unlocked, waiter ...]>"
        # on BONK after creating a 15th bot (TAO) — root cause
        # was the previous asyncio.run() spawn creating a
        # throwaway loop that bound the per-symbol lock, then
        # closing and leaving the lock pointing at a dead loop.
        self._async_loop = None
        # Session 26 P1b (2026-04-24) — Smart Wire singleton shared across
        # all bots. Operator spec: "Smart Wire feeds passively increase
        # Fold Queue of target bots ... distributed evenly across existing
        # tranches OR wait for a new tranche to form." Registration of
        # wires happens via the Bot Swarm GUI; actual fold-profit routing
        # fires from each source bot's fold success path.
        from .smart_wire import SmartWireManager

        # C17 — the wire manager emits bot.log on two paths and resolved
        # get_event_bus() lazily, so a SIM manager's wire activity
        # reached the LIVE bus even after this manager was isolated.
        self._smart_wire_mgr = SmartWireManager(bus=self._bus)
        # Subscribe to cross-bot profit routing events.
        # C17 — the closures are RETAINED now. Discarding them is what
        # left three handlers per sim replay permanently attached to the
        # process-wide bus.
        self._bus_unsubs.append(
            self._bus.subscribe("profit.cross_bot", self._on_cross_bot_profit)
        )
        # P1b — GUI wire drag events land on the manager + register/
        # unregister with the SmartWireManager so the fold path can see
        # them. Source-side routing fires per fold inside ScrummingBot.
        self._bus_unsubs.append(
            self._bus.subscribe("wire.created", self._on_wire_created_mgr)
        )
        self._bus_unsubs.append(
            self._bus.subscribe("wire.removed", self._on_wire_removed_mgr)
        )

    def detach_bus(self) -> int:
        """Retract every subscription this manager made.

        v3.24.61 (C17). Call in sim teardown. Returns the number of
        subscriptions removed, so a caller (or the exit gate) can assert
        the bus is back where it started.

        Never raises: teardown paths must complete. Idempotent — the
        retained list is cleared, so a second call is a no-op rather
        than a double-removal.
        """
        removed = 0
        for _off in list(self._bus_unsubs):
            try:
                _off()
                removed += 1
            except Exception as exc:  # R28-OK: teardown must finish
                logger.debug("bus detach skipped one handler: %s", exc)
        self._bus_unsubs = []
        return removed

    @property
    def smart_wire_manager(self):
        """Expose the SmartWireManager singleton (used by GUI to
        register/unregister wires drawn in the Bot Swarm tab)."""
        return self._smart_wire_mgr

    def _on_wire_created_mgr(self, event) -> None:
        """GUI wire drag → register with SmartWireManager so fold
        profits actually route. Session 26 P1b.

        v3.24.37 (C06c) — the result was discarded. register_wire
        refuses a wire whose pct is non-numeric, <= 0, > 100, or whose
        endpoints are equal, and every one of those refusals was
        dropped here: the GUI had already drawn the wire and the event
        had already fired, so the canvas showed a routing the engine
        never accepted and no fold profit would ever follow. An
        overwrite of an existing pct was equally invisible.
        """
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
        """GUI wire disconnect → unregister."""
        try:
            src = event.data.get("source_id", "")
            tgt = event.data.get("target_id", "")
            if src and tgt:
                self._smart_wire_mgr.unregister_wire(src, tgt)
        except Exception as exc:
            logger.warning("BotManager wire.removed handler raised: %s", exc)

    def _on_cross_bot_profit(self, event) -> None:
        """Handle cross-bot profit transfer.

        MEM-249 (Session 26 operator directive, enforces MEM-246 Phase B absolutely):
        Target Balance is a HARD CODED set-point. The ONLY legitimate mechanism
        that may grow it is fold-surplus bounded by max_target_growth_pct per
        event. Cross-bot profit wire is NOT that mechanism — it is a separate
        profit-routing feature that was previously pumping BOTH _target_balance
        AND config.target_balance unclamped, which is exactly the path the
        operator caught on 2026-04-23: "Target Balance increasing in this
        manner does not happen anymore!? It BREAKS the system."

        Fix: cross-bot profit routes to the recipient's `realised_pnl` stat.
        Operator still sees the profit in the P/L column; Target stays frozen
        at its set-point (subject only to the fold-surplus clamp). Target
        Balance is NOW safe against every mutation path we control.
        """
        target_id = event.data.get("target_bot_id", "")
        amount = event.data.get("amount", 0)
        source_id = event.data.get("source_bot_id", "")
        target_bot = self._bots.get(target_id)
        if target_bot and amount > 0:
            # Route to realised_pnl — NOT to target_balance. Target stays frozen.
            # sadp: R1 R28 — fold-only target growth; fail loudly if anyone else tries.
            if hasattr(target_bot, "stats") and hasattr(
                target_bot.stats, "realised_pnl"
            ):
                target_bot.stats.realised_pnl += float(amount)
            self._bus.emit(
                "bot.log",
                bot_id=target_id,
                message=(
                    f"CROSS-BOT RECEIVED: +${amount:.4f} from "
                    f"{source_id[:8]} booked to realised_pnl "
                    f"(Target frozen at ${target_bot.config.target_balance:.2f} — "
                    f"MEM-249 cross-wire no longer touches Target)."
                ),
            )
        elif not target_bot:
            self._bus.emit(
                "bot.log",
                bot_id=source_id,
                message=f"CROSS-BOT FAILED: target bot {target_id[:8]} not found",
            )

    def set_state_manager(self, sm) -> None:
        """Attach a StateManager for persistence."""
        self._state_manager = sm

    def force_fire(self, bot_id: str, aggressive: bool = False) -> bool:
        """MEM-236 + MEM-241 — Manual Fire from the dashboard.

        Looks up the bot by id and calls its force_fire() method. Safe
        on unknown bot_id (returns False) and on grid bots (base class
        force_fire is a no-op). Returns True when the call reached a
        scrumming bot instance.

        Called synchronously from the GUI thread — must not await or
        block. The bot's force_fire only mutates a counter/flag that
        the async tick loop picks up on next iteration.

        Args:
            aggressive: MEM-241. When True (GUI default), scrumming
                bots execute a one-shot market-order rebalance-to-target
                on the next tick, bypassing gate checks. When False,
                legacy MEM-236 flush-tick-skip behavior.
        """
        bot = self._bots.get(bot_id)
        if bot is None:
            return False
        try:
            # Forward-compat: older ScrummingBot builds may not accept
            # the aggressive kwarg. Try the new signature first; fall
            # back if TypeError on unexpected keyword.
            try:
                bot.force_fire(aggressive=aggressive)
            except TypeError:
                bot.force_fire()
            return hasattr(bot, "scrum_target_mode")
        except Exception as exc:
            logger.warning("force_fire failed on %s: %s", bot_id, exc)
            return False

    def set_volume_guard(self, guard) -> None:
        """Attach a VolumeGuard for market-safe trade execution."""
        self._volume_guard = guard
        for bot in self._bots.values():
            bot._volume_guard = guard
        logger.info(
            "VolumeGuard attached to BotManager (%d existing bots)", len(self._bots)
        )

    def set_data_pool(self, pool) -> None:
        """Attach shared MarketDataPool for efficient API usage."""
        self._data_pool = pool
        for bot in self._bots.values():
            bot._data_pool = pool
        logger.info(
            "DataPool attached to BotManager (%d existing bots)", len(self._bots)
        )

    # ── Bulk ticker refresh (operator item 1, 2026-08-06) ───────────

    def _connectors_by_exchange(self) -> dict:
        """One live connector per distinct exchange_id across the fleet.

        The bulk fetch is per-exchange, so 35 bots on one exchange need
        exactly one connector — not one per bot.
        """
        out: dict = {}
        for bot_id, bot in self._bots.items():
            try:
                exch_id = getattr(bot.config, "exchange_id", None)
                conn = getattr(bot, "exchange", None)
            except Exception as exc:
                # One malformed container must not blind the refresher
                # for the whole fleet, but a silent skip here would hide
                # a bot that never gets fresh prices.
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
        """One bulk ticker refresh across every exchange in the fleet.

        Separated from the loop so it is testable without a scheduler
        and callable on demand (e.g. immediately after a manual fire).
        """
        pool = getattr(self, "_data_pool", None)
        if pool is None or not hasattr(pool, "refresh_all_tickers"):
            return 0
        total = 0
        for exch_id, conn in self._connectors_by_exchange().items():
            try:
                total += await pool.refresh_all_tickers(conn, exch_id)
            except (
                Exception
            ) as exc:  # R28-OK: refresher is best-effort; bots keep their own fetch path
                logger.warning("Bulk ticker refresh raised for %s: %s", exch_id, exc)
        return total

    async def _ticker_refresh_loop(self, interval: float) -> None:
        """Warm the shared ticker cache on a display-grade cadence.

        WHY: a bot fetching its own ticker on its own gated schedule
        spends 35 calls to cover ground one bulk call covers. Measured
        2026-08-06: 10,272 ticker fetches/hour across the fleet, which
        this reduces to ~720 at the 5s default.

        This does NOT change any bot's decision cadence. Bots still act
        on their own gated schedule; that schedule now sees a fresher
        price. It REPLACES traffic rather than adding it: a warmed entry
        takes the fast path in `get_or_fetch_ticker`, so the bot does
        not issue its own request.

        CORRECTED 2026-08-07 -- what this does NOT do
        This was originally shipped believing it also unstuck the stale
        Ammo readout. It does not. The dashboard reads
        `stats.current_price` (`main_window.py:1621`), whose only
        recurring writer is `scrumming_bot.py:5136`, downstream of the
        read-rate gate. Nothing here writes that field. Display
        freshness is fixed separately, by having the display consult the
        pool cache this loop keeps warm.
        """
        logger.info("Bulk ticker refresher started (every %.1fs)", interval)
        while not self._ticker_refresh_stop:
            try:
                await asyncio.sleep(interval)
                if self._ticker_refresh_stop:
                    break
                await self.refresh_all_tickers_once()
            except asyncio.CancelledError:
                raise
            except (
                Exception
            ) as exc:  # R28-OK: the loop must survive any single failed cycle
                logger.warning("Ticker refresh cycle failed: %s", exc)
        logger.info("Bulk ticker refresher stopped.")

    def start_ticker_refresher(self, interval: float = 5.0) -> bool:
        """Launch the refresher on the manager's loop. Idempotent."""
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
        """v3.16.19 — Attach the persistent asyncio loop.

        Required so ``bootstrap_exchange_state`` (and any future
        BotManager-side coroutine launches) can run on the SAME
        loop as ``bot.tick()`` instead of spawning a throwaway
        loop in a new thread via ``asyncio.run()``. The throwaway
        pattern was poisoning v3.16.17's per-symbol asyncio.Lock
        instances, leaving them bound to a loop that would soon
        close. Operator-reported 2026-05-01 — see CHANGELOG
        v3.16.19 for the full root-cause writeup.
        """
        self._async_loop = loop
        logger.info(
            "AsyncLoop attached to BotManager (id=%s)",
            id(loop) if loop is not None else "None",
        )

    def _dispatch_bootstrap(self, bot, source: str) -> None:
        """v3.16.19 — Run ``bot.bootstrap_exchange_state()`` on the
        persistent asyncio loop when wired, otherwise fall back to
        the legacy throwaway-thread pattern.

        Persistent-loop path (production): use
        ``asyncio.run_coroutine_threadsafe(coro, self._async_loop)``.
        The coroutine runs on the SAME loop that ``bot.tick()`` will
        run on, so any asyncio.Lock created during bootstrap (e.g.,
        the v3.16.17 ticker-coalescing locks in MarketDataPool)
        binds to the right loop and stays valid for tick-time
        access. The future is fire-and-forget — exceptions are
        logged via add_done_callback rather than blocking the
        caller.

        Throwaway-loop path (tests / no-loop fallback): the legacy
        ``asyncio.run()`` in a daemon thread. Only safe in
        environments where the bot will not later use shared
        asyncio primitives on a different loop (i.e., tests that
        construct bots in isolation).

        Parameters
        ----------
        source : str
            Origin label for log messages ("set_connector" |
            "register" | future). Helps the operator distinguish
            which dispatch path failed when warnings appear.
        """
        coro = bot.bootstrap_exchange_state()
        loop = self._async_loop
        if loop is not None and not loop.is_closed():
            try:
                fut = asyncio.run_coroutine_threadsafe(coro, loop)

                def _on_done(_fut, _bid=bot.bot_id, _src=source):
                    try:
                        _exc = _fut.exception()
                    except (
                        Exception
                    ) as _probe_exc:  # R28-OK: future-state probe; defensive against future cancellation surfacing as a non-Exception
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
        # Fallback: no persistent loop wired (test harness path).
        # Close the coroutine first if we can't dispatch — leaving
        # an unawaited coroutine raises a RuntimeWarning.
        try:
            coro.close()
        except Exception as _close_exc:
            # The comment here used to say this was logged. It was not.
            # Nothing was written anywhere, so a failure to tidy up the
            # unused start-up job left no trace at all. It is written
            # now. The failure is still not treated as fatal, because
            # a fresh job is started on the next lines either way; the
            # only cost of a failed tidy-up is a warning from Python
            # about a job nobody waited for.
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
        """Create or reconfigure LiveMonitor from settings dict.

        Called when settings are saved. Keys:
          api_key, interval_hours, connect_phrase, confirm_phrase, enabled
        """
        if not settings.get("enabled") or not settings.get("api_key"):
            self._live_monitor = None
            logger.info("LiveMonitor disabled")
            return
        from .live_monitor import LiveMonitor, TradeJournal

        journal = TradeJournal()
        self._live_monitor = LiveMonitor(
            api_key=settings["api_key"],
            journal=journal,
            interval_hours=settings.get("interval_hours", 4.0),
            connect_phrase=settings.get("connect_phrase", ""),
            confirm_phrase=settings.get("confirm_phrase", ""),
        )
        logger.info(
            "LiveMonitor configured (interval=%.1fh, phrase='%s')",
            settings.get("interval_hours", 4.0),
            settings.get("connect_phrase", "")[:20],
        )

    async def check_live_monitor(self) -> dict | None:
        """Run AI feedback check if due. Returns feedback dict or None."""
        if not self._live_monitor or not self._live_monitor.enabled:
            return None
        if not self._live_monitor.should_check:
            return None
        # Aggregate portfolio stats from all bots.
        #
        # v3.24.40 (C54) — get_status() emitted NEITHER key, so both
        # .get(..., 0) calls returned 0 for every bot on every check.
        # The monitor was handed "Portfolio: $0.00 | Passive: $0.00"
        # every time, sent that to the model, and surfaced the reply on
        # the bus as ai.feedback — advice about a portfolio it had been
        # told was empty. The default argument made it silent.
        #
        # portfolio_value is now emitted per bot. passive_value has no
        # source anywhere in src/ (declared nowhere, written nowhere),
        # so it is reported as UNAVAILABLE rather than as $0.00. A
        # buy-and-hold baseline needs each position's entry basis; that
        # is a real computation, not a default, and inventing a zero
        # for it is what made this wrong in the first place.
        total_port = 0.0
        contributing = 0
        for bot in self._bots.values():
            try:
                s = bot.get_status()
            except Exception as exc:  # R28-OK: lifecycle/state best-effort
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
        """
        Attach the CcxtConnector so BotManager can register bot symbols
        for post-connect trade history scanning.

        MEM-255: ALSO fires a one-shot live-pull of exchange state for every
        registered bot that supports `bootstrap_exchange_state`. Without
        this, idle bots (not yet started) show holdings=0 in the GUI
        because the tick-time MEM-226 handshake never runs. Operator
        directive: "if it displays exchange data, it should plug in
        immediately to the first verified API."
        """
        self._connector = connector
        # Register any already-running bots' symbols immediately
        for bot in self._bots.values():
            connector.add_scan_symbol(bot.config.symbol)
            # Attach the connector as the bot's exchange so bootstrap +
            # subsequent tick-time handshake see a real exchange. (Some
            # callers already set bot.exchange at construction; this is
            # idempotent when they match.)
            if not getattr(bot, "exchange", None) or bot.exchange is None:
                try:
                    bot.exchange = connector
                except Exception as _attach_exc:
                    # A bot may be a frozen record that refuses any
                    # attribute write, so this must not stop the loop
                    # or reach the caller. It DOES have to be said out
                    # loud: the bot now holds no connector, later reads
                    # fall back to a default, and a bot with no
                    # connector cannot trade. Silence here is what made
                    # that state invisible.
                    logger.error(
                        "Bot %s would not accept the exchange connector "
                        "(%s). It has no connector and cannot trade "
                        "until one is attached.",
                        getattr(bot, "bot_id", "<unknown bot>"),
                        _attach_exc,
                    )
            # Fire the one-shot live-pull on the persistent asyncio
            # loop when available (v3.16.19 fix for cross-loop Lock
            # poisoning). Falls back to the legacy throwaway-thread
            # `asyncio.run` path only when no loop is wired — that
            # branch is only used in test harnesses that don't
            # attach a persistent loop.
            if hasattr(bot, "bootstrap_exchange_state"):
                self._dispatch_bootstrap(bot, "set_connector")
        logger.info(
            "Connector attached to BotManager — "
            "%d symbol(s) registered for history scanning + bootstrap",
            len(self._bots),
        )

    # ------------------------------------------------------------------
    # v3.20.71 Phase B-2 — CapitalRegistry broker integration
    # ------------------------------------------------------------------
    def set_capital_registry(self, registry) -> None:
        """Wire in a CapitalRegistry broker instance. After this is set,
        register() consults it as a reservation gate (Q3 refuse-outright)
        and unregister() releases the reservation. main.py wires this in
        AFTER settings.json is loaded so initial_reservations can
        rehydrate from disk per Q4."""
        self._capital_registry = registry

    @property
    def capital_registry(self):
        """Expose the broker for tests + Phase D's GUI registry table."""
        return self._capital_registry

    def reconcile_capital_registry(
        self,
        *,
        exchange_id: str,
        base_currency: str,
        drift_threshold_pct: float = 5.0,
    ) -> "Optional[dict]":
        """v3.20.73 Phase D — periodic reconciliation of one
        (exchange, base) pool against the live exchange balance.
        Locked Q1: 5-minute cadence (callers schedule the call;
        this method is the single-shot reconcile step).

        Mechanism:
        - Fetch live exchange balance via the wired connector
        - Convert to USD using a best-effort rate from the connector ticker
        - Call ``registry.reconcile_with_exchange(...)`` which
          returns ``{wallet_base, wallet_usd, reserved_usd, reserved_base,
          free_usd, free_base, drift_usd, drift_pct}``
        - If ``drift_pct > drift_threshold_pct`` (default 5%), emit
          ``capital.drift_alert`` event with the full report for the
          operator notification panel
        - Refresh the registry's snapshot rate (so reserved_base on
          each reservation tracks the current rate)

        Returns the drift report dict, or None if the registry isn't
        wired or the connector can't fetch a balance. Never raises.

        MEM-419.
        """
        if self._capital_registry is None:
            return None
        try:
            # Fetch wallet balance via the connector's sync interface
            if not self._connector or not hasattr(self._connector, "_ccxt_sync"):
                return None
            balances = self._connector._ccxt_sync.fetch_balance()
            free = balances.get("free", {}) if isinstance(balances, dict) else {}
            wallet_base = float(free.get(base_currency, 0) or 0)
            # Rate lookup (USD-like = 1.0)
            rate = self._usd_per_base_for(exchange_id, base_currency)
            if rate is None:
                # Comparing the wallet against the saved claims needs a
                # real price. Without one this used to carry on with a
                # made-up $1.00, which rewrote every saved claim in the
                # pool through reconcile_with_exchange and raised a
                # false drift alarm. No price means no comparison.
                logger.warning(
                    "Skipped the %s/%s capital check: no %s price is "
                    "available. The saved claims are left exactly as "
                    "they are.",
                    exchange_id,
                    base_currency,
                    base_currency,
                )
                return None
            # Reconcile
            report = self._capital_registry.reconcile_with_exchange(
                exchange_id=exchange_id,
                base_currency=base_currency,
                exchange_balance_base=wallet_base,
                current_rate_usd_per_base=rate,
            )
            # Drift alert
            drift_pct = float(report.get("drift_pct", 0.0) or 0.0)
            if abs(drift_pct) > drift_threshold_pct:
                self._bus.emit(
                    "capital.drift_alert",
                    exchange_id=exchange_id,
                    base_currency=base_currency,
                    drift_pct=drift_pct,
                    report=report,
                )
                logger.warning(
                    "v3.20.73 capital drift on %s/%s: %.2f%% "
                    "(wallet $%.2f vs reserved $%.2f)",
                    exchange_id,
                    base_currency,
                    drift_pct,
                    report.get("wallet_usd", 0.0),
                    report.get("reserved_usd", 0.0),
                )
            return report
        except (
            Exception
        ) as _exc:  # R28-OK: reconcile best-effort; never block bot lifecycle
            logger.warning(
                "v3.20.73 reconcile_capital_registry failed " "for %s/%s: %s",
                exchange_id,
                base_currency,
                _exc,
            )
            return None

    def reconcile_all_capital(
        self,
        *,
        drift_threshold_pct: float = 5.0,
    ) -> list[dict]:
        """v3.20.73 Phase D — reconcile every (exchange, base) tuple
        that has at least one active reservation. Returns the list of
        drift reports (one per pool). Empty list if no registry / no
        reservations. The 5-min cadence callers (Phase D background
        task / GUI manual-refresh) invoke this single method to
        reconcile all pools in one pass."""
        if self._capital_registry is None:
            return []
        reservations = self._capital_registry.get_reservations()
        # Distinct (exchange, base) tuples to reconcile
        pools: set[tuple[str, str]] = set()
        for r in reservations:
            pools.add((r.exchange_id, r.base_currency))
        reports: list[dict] = []
        for exch, base in sorted(pools):
            rep = self.reconcile_capital_registry(
                exchange_id=exch,
                base_currency=base,
                drift_threshold_pct=drift_threshold_pct,
            )
            if rep is not None:
                rep["exchange_id"] = exch
                rep["base_currency"] = base
                reports.append(rep)
        return reports

    def notify_bot_profit(
        self,
        *,
        bot_id: str,
        profit_usd: float,
    ) -> tuple[bool, "Optional[str]"]:
        """v3.20.72 Phase C-1 — relay an Extractor profit credit to
        the CapitalRegistry so the bot's reservation grows by the
        profit amount (MEM-418). Closes the cross-bot leak surface:
        without this, sibling bots see the wallet's grown balance as
        unreserved excess and could claim it (fee-stacking cascade).

        Locked Q6 semantics: same-bot-only overshoot. The bot's own
        reservation grows immediately even if the wallet provider
        hasn't observed the profit settlement yet; siblings'
        request_reservation() calls then see the higher total and
        refuse over-allocation against unsettled profit.

        Returns ``(success, reason)``. On failure (no registry wired
        / no existing reservation / non-positive profit), this is a
        no-op — never blocks the trade flow.
        """
        if self._capital_registry is None or profit_usd <= 0:
            return False, None
        try:
            granted, reason, _ = self._capital_registry.grow_reservation(
                bot_id=bot_id, additional_usd=profit_usd
            )
            return granted, reason
        except (
            Exception
        ) as _exc:  # R28-OK: best-effort registry growth; never block trade
            logger.warning(
                "v3.20.72 notify_bot_profit failed for bot %s " "(+$%.2f): %s",
                bot_id,
                profit_usd,
                _exc,
            )
            return False, str(_exc)

    def _reservation_usd_and_mode(self, bot) -> tuple[float, str]:
        """Extract the canonical (usd_amount, bot_mode) tuple from a bot
        config for registry consultation. Scrumming uses target_balance;
        Extractor uses extractor_chunk_size_usd. Mode string is
        lowercase, matching the broker's expected enum."""
        try:
            mode_val = getattr(bot.config, "mode", None)
            mode_str = (
                str(mode_val.value if hasattr(mode_val, "value") else mode_val) or ""
            ).lower()
        except Exception:  # R28-OK: best-effort mode probe; default to scrumming
            mode_str = "scrumming"
        if "extractor" in mode_str:
            usd_amount = float(getattr(bot.config, "extractor_chunk_size_usd", 0) or 0)
            return usd_amount, "extractor"
        usd_amount = float(getattr(bot.config, "target_balance", 0) or 0)
        return usd_amount, "scrumming"

    def _usd_per_base_for(
        self,
        exchange_id: str,
        base_currency: str,
    ) -> "Optional[float]":
        """How many dollars one unit of ``base_currency`` is worth.

        Returns nothing when no honest price can be had: the price
        request failed, the exchange gave back zero or a negative
        number or something that is not a number, or there is no
        exchange connection at all.

        This used to return 1.0 in every one of those cases. That
        priced one Bitcoin at one dollar, silently, on the path that
        decides how much money each bot may claim. Two things were
        measured with that made-up number in place: ``register``
        refused a $2,000 bot on a real half-Bitcoin wallet and dropped
        the bot, blaming a wallet it had valued at fifty cents; and
        ``reconcile_capital_registry`` overwrote a saved claim of
        0.0327 BTC with 2000.0 BTC and saved it to disk.

        There is no correct number to hand back when the price is
        unknown, so it hands back nothing and each caller decides what
        to do about it. Dollar-pegged coins still return 1.0, because
        for those one dollar per unit is the true price, not a
        stand-in.

        ``exchange_id`` is accepted for a future per-exchange price
        source; the lookup is exchange-wide today.
        """
        base = (base_currency or "").upper()
        if base in DOLLAR_PEGGED_CURRENCIES:
            return 1.0
        if not self._connector or not hasattr(self._connector, "_ccxt_sync"):
            logger.warning(
                "No exchange connection, so no %s price for %s. "
                "Returning no rate rather than pretending one %s is "
                "worth one dollar.",
                base,
                exchange_id,
                base,
            )
            return None
        try:
            t = self._connector._ccxt_sync.fetch_ticker(f"{base}/USD")
            rate = float(t.get("last") or t.get("close") or 0)
        except Exception as _rate_exc:
            logger.warning(
                "Could not read the %s/USD price on %s (%s). Returning "
                "no rate rather than pretending one %s is worth one "
                "dollar.",
                base,
                exchange_id,
                _rate_exc,
                base,
            )
            return None
        if rate <= 0:
            logger.warning(
                "The %s/USD price on %s came back as %r, which cannot "
                "be a price. Returning no rate rather than pretending "
                "one %s is worth one dollar.",
                base,
                exchange_id,
                rate,
                base,
            )
            return None
        return rate

    # -- Bulk operations ------------------------------------------------
    async def start_all(
        self,
        verify_timeout_seconds: float = 10.0,
        min_gap_seconds: float = 0.6,
        eligible_filter: Optional[Callable[["BotContainer"], bool]] = None,
    ) -> None:
        """v3.16.11 — VERIFY-THEN-NEXT staggered start. Operator directive
        2026-04-28 (clarification): "Should have a delay between bots hence
        staggered. One should start, be verified running, then the next
        one starts..."

        v3.23.86 — bumped defaults ~10-15% slower per operator directive
        2026-07-31 (avg ~3 initial start failures per boot):
          * ``verify_timeout_seconds`` 8.0 → 10.0 (25% more headroom for
            slow-handshake bots to reach RUNNING before we time out and
            move on).
          * ``min_gap_seconds`` 0.5 → 0.6 (20% larger cooldown between
            bots to space API-handshake bursts).
        Combined effect on a 35-bot boot: ~3.5s extra total, roughly
        10-15% slower depending on per-bot handshake variance.

        Each eligible bot starts; the loop polls `bot.state` until it
        reaches RUNNING (or `verify_timeout_seconds` elapses), then a
        small `min_gap_seconds` cooldown before the next bot starts.
        The fixed-delay v3.16.7 version was wrong — a slow-starting bot
        (network handshake / candle backfill) wouldn't have its
        verification reflected before the next one fired.

        Emits `bot_manager.start_all_progress` events:
          phase="begin"        — total + zero started
          phase="bot_starting" — bot.bot_id, count
          phase="bot_started"  — bot reached RUNNING (verified)
          phase="bot_timeout"  — verify_timeout elapsed; moving on anyway
          phase="cancelled"    — operator hit Cancel
          phase="done"         — all eligible bots processed

        Filter: by default, all bots in IDLE/STOPPED are eligible. Pass
        `eligible_filter=lambda b: b._was_running` to restart only bots
        whose `state_when_saved == "running"` (the auto-restart-after-
        crash scenario).
        """
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
            # Verify-then-next: poll until state==RUNNING or timeout.
            verified = False
            poll_interval = 0.25
            elapsed = 0.0
            while elapsed < verify_timeout_seconds:
                if getattr(self, "_start_all_cancel", False):
                    break
                if bot.state == BotState.RUNNING:
                    verified = True
                    break
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
            if verified:
                self._bus.emit(
                    "bot_manager.start_all_progress",
                    phase="bot_started",
                    total=total,
                    started=i + 1,
                    bot_id=bot.bot_id,
                )
            else:
                # Timeout — proceed to next bot anyway. The slow bot
                # may still come up; the operator can see the timeout
                # event and decide.
                self._bus.emit(
                    "bot_manager.start_all_progress",
                    phase="bot_timeout",
                    total=total,
                    started=i + 1,
                    bot_id=bot.bot_id,
                    timeout_seconds=verify_timeout_seconds,
                )
            # Small cooldown before next bot to space out exchange-API
            # bursts (each bot does its own handshake during start).
            if i < len(eligible) - 1:
                await asyncio.sleep(min_gap_seconds)
        self._bus.emit(
            "bot_manager.start_all_progress", phase="done", total=total, started=total
        )

    def cancel_start_all(self) -> None:
        """Operator-callable: abort an in-flight start_all. The current
        bot finishes its start; subsequent bots are skipped."""
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
