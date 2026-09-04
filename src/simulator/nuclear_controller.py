"""Single-tape Nuclear orchestrator: one scout bot walking one tape.

The controller takes a ``tape_id`` ("A", "B", ...) rather than a symbol
and builds the synthetic trading symbol from it ("TAPEA/USD"), so
``BotConfig`` has something to bind to and the bot never sees the tape's
real-world source.

It owns an isolated ``EventBus`` and ``BotManager``, constructs one
sim-mode ``ScrummingBot`` against a ``NuclearSimExchange``, and runs a
world-clock coroutine that advances the tape on a cadence. Smart Wire,
spawning and load oscillation are not part of it.

``NuclearModePanel`` drives ``NuclearFleetController`` instead, so
nothing under ``src/`` constructs this class; both share
``nuclear_candle_source``. ``start`` is synchronous here and a coroutine
on the fleet controller.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import traceback
from typing import Callable, Optional

from ..core.event_bus import EventBus
from ..trading.bot_container import (
    BotManager,
    BotMode,
    make_bot_config,
)
from ..trading.scrumming_bot import ScrummingBot
from .fleet.fleet_replay_controller import _make_sim_capital_registry

from .nuclear_candle_source import NuclearCandleSource
from .nuclear_sim_exchange import NuclearSimExchange, _tape_id_to_base

logger = logging.getLogger("acervator.nuclear_sim")


_SIM_QUOTE = "USD"


class NuclearController:
    """Orchestrate an isolated nuclear-mode sim run.

    ``stop`` leaves the scout attached so ``snapshot`` still reports its
    final state; ``_teardown_quiet`` is what releases it.

    Lifecycle:
        src = NuclearCandleSource()
        ctl = NuclearController(
            candle_source=src,
            tape_id="A",
            activity_cb=tab.log_activity,
        )
        ctl.start(async_loop=main_loop)
        ctl.stop()
    """

    DEFAULT_WORLD_CLOCK_MS: int = 250

    def __init__(
        self,
        candle_source: NuclearCandleSource,
        tape_id: str,
        activity_cb: Optional[Callable[[str], None]] = None,
        perf_cb: Optional[Callable[[str], None]] = None,
        seed_amount: float = 200.0,
        world_clock_ms: Optional[int] = None,
    ) -> None:
        if tape_id not in candle_source.list_tapes():
            raise ValueError(
                f"NuclearController: tape {tape_id!r} not available. "
                f"Discovered tapes: {candle_source.list_tapes()}"
            )
        self._src = candle_source
        self._tape_id = tape_id
        self._activity_cb = activity_cb or (lambda _msg: None)
        self._perf_cb = perf_cb or (lambda _msg: None)
        self._seed_amount = float(seed_amount)
        self._world_clock_ms = int(world_clock_ms or self.DEFAULT_WORLD_CLOCK_MS)

        self._sim_symbol = f"{_tape_id_to_base(tape_id)}/{_SIM_QUOTE}"

        # Built on start()
        self._exchange: Optional[NuclearSimExchange] = None
        self._sim_bus: Optional[EventBus] = None
        self._sim_bot_manager: Optional[BotManager] = None
        self._scout: Optional[ScrummingBot] = None
        self._world_clock_task: Optional[asyncio.Task] = None
        self._scout_task_future = None

        self._running: bool = False
        self._started_at: float = 0.0
        self._world_clock_ticks: int = 0
        self._exception_count: int = 0
        self._last_exception: str = ""
        self._trade_count: int = 0
        self._scrum_count: int = 0
        self._fold_count: int = 0
        self._error_count: int = 0
        self._bus_unsubs: list = []

    # ─── Public surface ────────────────────────────────────────────────

    def is_running(self) -> bool:
        return self._running

    def tape_id(self) -> str:
        return self._tape_id

    def tape_label(self) -> str:
        return self._src.tape_label(self._tape_id)

    def start(self, async_loop: asyncio.AbstractEventLoop) -> bool:
        """Start the scout. Returns True on clean start, False on
        failure (logged + activity-cb). Never raises.
        """
        if self._running:
            self._log_activity("Nuclear: already running; ignoring start.")
            return False
        try:
            self._build_context()
            self._wire_bus_subscriptions()
            self._construct_scout()
            self._start_async_pieces(async_loop)
            self._running = True
            self._started_at = time.monotonic()
            self._log_activity(
                f"Nuclear: scout started on {self.tape_label()} "
                f"(sim symbol={self._sim_symbol}, "
                f"seed=${self._seed_amount:.2f}, "
                f"world_clock={self._world_clock_ms}ms)."
            )
            return True
        except Exception as exc:
            self._exception_count += 1
            self._last_exception = f"{type(exc).__name__}: {exc}"
            sys.stderr.write(
                f"[NuclearController.start] {self._last_exception}\n"
                f"{traceback.format_exc()}"
            )
            logger.error("NuclearController.start failed: %s", exc)
            self._log_activity(
                f"Nuclear: start FAILED — {self._last_exception}. "
                f"See stderr for full traceback."
            )
            self._teardown_quiet()
            return False

    def stop(self) -> None:
        if not self._running and self._scout is None:
            return
        self._log_activity("Nuclear: stopping...")
        if self._world_clock_task is not None and not self._world_clock_task.done():
            self._world_clock_task.cancel()
        if self._scout is not None and self._scout._task is not None:
            loop = self._scout._task.get_loop()
            try:
                asyncio.run_coroutine_threadsafe(self._scout.stop(), loop)
            except Exception as exc:
                self._log_activity(
                    f"Nuclear: scout.stop scheduling failed: "
                    f"{type(exc).__name__}: {exc}"
                )
        for unsub in self._bus_unsubs:
            try:
                unsub()
            except Exception as _unsub_exc:  # noqa: BLE001
                # A failed unsubscribe leaves a live handler on the sim bus,
                # so the next run double-counts its events.
                logger.debug("nuclear: unsubscribe failed: %s", _unsub_exc)
        self._bus_unsubs.clear()
        self._running = False
        self._log_activity("Nuclear: stopped.")

    def snapshot(self) -> dict:
        """Single-call status read for the GUI panel."""
        uptime = time.monotonic() - self._started_at if self._running else 0.0
        scout_state = "—"
        scout_holdings = 0.0
        scout_target = 0.0
        if self._scout is not None:
            try:
                scout_state = str(self._scout.state.value)
                scout_holdings = float(getattr(self._scout, "_current_holdings", 0.0))
                scout_target = float(getattr(self._scout, "_target_balance", 0.0))
            except Exception as _snap_exc:  # noqa: BLE001
                # A GUI timer polls this, so a read failure shows only as
                # status fields that stop moving.
                logger.debug("nuclear: scout snapshot read: %s", _snap_exc)
        # A raising tape read would stall the whole status panel, not just
        # the two price fields below.
        _last_px = 0.0
        _last_vol = 0.0
        try:
            _cur = self._src.current(self._tape_id)
            if _cur and len(_cur) >= 6:
                _last_px = float(_cur[4])
                _last_vol = float(_cur[5])
        except (KeyError, TypeError, ValueError, IndexError) as _px_exc:
            logger.debug("snapshot: tape read failed: %s", _px_exc)
        _voting = getattr(self._scout, "_last_summary", None)

        ex_snap = self._exchange.snapshot() if self._exchange else {}
        tape_info = self._src.tape_info(self._tape_id)
        return {
            "running": self._running,
            "uptime_seconds": uptime,
            "tape_id": self._tape_id,
            "tape_label": self.tape_label(),
            "tape_direction": tape_info.get("direction", "?"),
            "tape_cursor": tape_info.get("cursor", 0),
            "tape_length": tape_info.get("n_candles", 0),
            "tape_wraps": tape_info.get("wrap_count", 0),
            "world_clock_ms": self._world_clock_ms,
            "world_clock_ticks": self._world_clock_ticks,
            "scout_state": scout_state,
            "scout_holdings": scout_holdings,
            "scout_target": scout_target,
            "trade_count": self._trade_count,
            "scrum_count": self._scrum_count,
            "fold_count": self._fold_count,
            "error_count": self._error_count,
            "exception_count": self._exception_count,
            "last_exception": self._last_exception,
            "exchange_snapshot": ex_snap,
            # The Indicator Voting Panel and the price chart read the four
            # keys below.
            "symbol": self._sim_symbol,
            "last_price": _last_px,
            "last_volume": _last_vol,
            "voting_summary": _voting,
        }

    # ─── Internal: context build ───────────────────────────────────────

    def _build_context(self) -> None:
        self._src.wire(self._tape_id)

        # Injected, not rebound afterwards: BotManager.__init__ subscribes
        # three handlers, and rebinding `._bus` leaves them on the live bus.
        self._sim_bus = EventBus()
        self._sim_bot_manager = BotManager(bus=self._sim_bus)

        self._exchange = NuclearSimExchange(
            self._src,
            quote_currency=_SIM_QUOTE,
            quote_seed=self._seed_amount,
            fee_pct=0.0,
        )

    def _wire_bus_subscriptions(self) -> None:
        bus = self._sim_bus

        def _on_trade(event):
            self._trade_count += 1
            try:
                side = str(event.data.get("side", "")).lower()
                action = str(event.data.get("action", "")).lower()
            except Exception:  # R28-OK
                side = ""
                action = ""
            if "sell" in side or "scrum" in action:
                self._scrum_count += 1
            elif "buy" in side or "fold" in action:
                self._fold_count += 1
            self._log_activity(
                f"sim trade.filled #{self._trade_count}: "
                f"side={side or '?'} action={action or '?'}"
            )

        def _on_bot_error(event):
            self._error_count += 1
            try:
                err = str(event.data.get("error", ""))[:240]
            except Exception:  # R28-OK
                err = ""
            self._log_activity(f"sim bot.error #{self._error_count}: {err}")

        def _on_bot_log(event):
            try:
                msg = str(event.data.get("message", ""))[:240]
            except Exception:  # R28-OK
                msg = ""
            if msg:
                self._log_activity(f"sim bot.log: {msg}")

        self._bus_unsubs.append(bus.subscribe("trade.filled", _on_trade))
        self._bus_unsubs.append(bus.subscribe("bot.error", _on_bot_error))
        self._bus_unsubs.append(bus.subscribe("bot.log", _on_bot_log))

    def _construct_scout(self) -> None:
        base = _tape_id_to_base(self._tape_id)
        # make_bot_config raises on a kwarg foreign to the mode; BotConfig
        # constructed directly would store it.
        cfg = make_bot_config(
            BotMode.SCRUMMING,
            exchange_id="nuclear_sim",
            base_currency=_SIM_QUOTE,
            target_asset=base,
            symbol=self._sim_symbol,
            target_balance=self._seed_amount,
            scrumming_interval_pct=1.0,
            ta_timeframe="1h",
        )
        # _make_sim_capital_registry raises rather than falling back to the
        # process-wide registry, which autosaves to reservation_state.json.
        # Aborting is right; the abort must say why.
        try:
            _sim_registry = _make_sim_capital_registry()
        except Exception as _crr_exc:
            raise RuntimeError(
                f"Nuclear Mode cannot start: sim capital-registry "
                f"isolation failed ({_crr_exc}). Refusing to run the "
                f"scout against the process-wide registry, which "
                f"persists to the operator's reservation_state.json."
            ) from _crr_exc
        scout = ScrummingBot(
            cfg,
            self._exchange,
            enable_phantoms=True,
            sim_mode=True,
            capital_registry=_sim_registry,
        )
        # sim_mode gives the bot a private bus of its own; this re-points it
        # at the one _wire_bus_subscriptions counts on.
        scout._bus = self._sim_bus
        self._sim_bot_manager.register(scout)
        self._scout = scout

    def _start_async_pieces(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._scout is None:
            raise RuntimeError("scout not constructed yet")
        self._scout_task_future = asyncio.run_coroutine_threadsafe(
            self._scout.start(), loop
        )

        async def _world_clock():
            interval = self._world_clock_ms / 1000.0
            tape_id = self._tape_id
            src = self._src
            while True:
                try:
                    src.advance(tape_id)
                    self._world_clock_ticks += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._exception_count += 1
                    self._last_exception = f"{type(exc).__name__}: {exc}"
                    sys.stderr.write(
                        f"[NuclearController.world_clock] " f"{self._last_exception}\n"
                    )
                    self._log_activity(
                        f"Nuclear: world-clock exception "
                        f"#{self._exception_count}: "
                        f"{self._last_exception}"
                    )
                await asyncio.sleep(interval)

        self._world_clock_task = asyncio.run_coroutine_threadsafe(_world_clock(), loop)

    # ─── Internal: teardown / logging ──────────────────────────────────

    def _teardown_quiet(self) -> None:
        # Retract the manager's own subscriptions so they do not accumulate
        # on the private bus across repeated runs.
        _mgr = getattr(self, "_sim_bot_manager", None)
        if _mgr is not None and hasattr(_mgr, "detach_bus"):
            try:
                _mgr.detach_bus()
            except Exception as _db_exc:  # R28-OK: teardown must finish
                logger.debug("nuclear: manager bus detach failed: %s", _db_exc)
        for unsub in self._bus_unsubs:
            try:
                unsub()
            except Exception as _unsub_exc:  # noqa: BLE001
                logger.debug("nuclear: teardown unsubscribe failed: %s", _unsub_exc)
        self._bus_unsubs.clear()
        if self._world_clock_task is not None and not self._world_clock_task.done():
            try:
                self._world_clock_task.cancel()
            except Exception as _cancel_exc:  # noqa: BLE001
                # A task that refuses to cancel keeps advancing the tape
                # after stop, visible only as a status panel that will not
                # settle.
                logger.debug("nuclear: world-clock cancel failed: %s", _cancel_exc)
        self._world_clock_task = None
        self._scout = None
        self._exchange = None
        self._sim_bot_manager = None
        self._sim_bus = None

    def _log_activity(self, msg: str) -> None:
        """Hand one line to the caller's activity callback, never raising."""
        try:
            self._activity_cb(msg)
        except Exception as _sf_exc:  # noqa: BLE001
            logger.warning("nuclear: activity callback failed: %s", _sf_exc)
