# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""``PhantomBot`` read-only TA observers, one per timeframe.

Each ``PhantomBot._tick`` computes TA on its own timeframe and stores it
on ``last_summary``, constructing no order. ``TimeframeCoordinator`` weights
those summaries by ``tf_rank`` in ``get_higher_tf_bias`` and returns them per
timeframe in ``get_multi_tf_summary``. ``TIMEFRAME_ORDER`` runs 1m to 1w,
lowest rank first.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..exchange.base import ExchangeInterface

from ..core.event_bus import get_event_bus
from .bot_container import BotState
from .ta_engine import VotingEngine, VotingSummary, SignalDirection, candles_from_raw

logger = logging.getLogger("acervator.phantom")


TIMEFRAME_ORDER: list[str] = [
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
    "1w",
]

TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


def tf_rank(timeframe: str) -> int:
    """Return the index of ``timeframe`` in ``TIMEFRAME_ORDER``, or -1."""
    try:
        return TIMEFRAME_ORDER.index(timeframe)
    except ValueError:
        return -1


def is_higher_tf(a: str, b: str) -> bool:
    """Return True when ``tf_rank(a)`` exceeds ``tf_rank(b)``."""
    return tf_rank(a) > tf_rank(b)


@dataclass
class TradeLock:
    """One entry in ``TimeframeCoordinator._locks``.

    ``is_locked`` matches it against every timeframe below
    ``source_timeframe``, and ``tick_candle`` decrements
    ``candles_remaining``.
    """

    source_timeframe: str
    source_bot_id: str
    direction: SignalDirection  # The direction locked OUT, not the one allowed.
    candles_remaining: int
    created_at: float = field(default_factory=time.time)
    # Read by nothing; is_locked always covers every lower timeframe.
    lock_all_lower: bool = True

    @property
    def is_expired(self) -> bool:
        return self.candles_remaining <= 0


class PhantomBot:
    """A read-only TA observer registered on one ``TimeframeCoordinator``.

    ``_tick`` refreshes ``last_summary`` for ``timeframe``; ``target_balance``,
    ``total_trades`` and ``realised_pnl`` are reported by ``get_status`` and
    changed by nothing here.
    """

    def __init__(
        self,
        parent_bot_id: str,
        phantom_id: str,
        timeframe: str,
        target_balance: float,
        exchange: ExchangeInterface,
        symbol: str,
        coordinator: "TimeframeCoordinator",
        ta_weights: Optional[dict[str, float]] = None,
        bus=None,
        sim_mode: bool = False,
    ) -> None:
        # When True, _run_loop never self-schedules; tick_for_cursor drives ticks.
        self._sim_mode = bool(sim_mode)
        self._last_cursor_bucket: Optional[int] = None
        self.parent_bot_id = parent_bot_id
        self.phantom_id = phantom_id
        self.timeframe = timeframe
        self.target_balance = target_balance
        self.exchange = exchange
        self.symbol = symbol
        self.coordinator = coordinator
        self.voting_engine = VotingEngine(weights=ta_weights)

        self._bus = bus if bus is not None else get_event_bus()
        self.state = BotState.IDLE
        self.last_summary: Optional[VotingSummary] = None
        self.last_action_time: float = 0.0
        self.total_trades: int = 0
        self.realised_pnl: float = 0.0
        self._current_holdings: float = 0.0
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    @property
    def rank(self) -> int:
        return tf_rank(self.timeframe)

    @property
    def candle_seconds(self) -> int:
        return TIMEFRAME_SECONDS.get(self.timeframe, 3600)

    async def start(self) -> None:
        self.state = BotState.RUNNING
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())
        self._bus.emit(
            "phantom.started",
            parent=self.parent_bot_id,
            phantom=self.phantom_id,
            timeframe=self.timeframe,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self.state = BotState.STOPPED

    async def tick_for_cursor(self, cursor_ts: float) -> bool:
        """Run ``_tick`` when ``cursor_ts`` enters a new ``candle_seconds``
        bucket, and return whether it ran.

        Repeated calls inside one bucket return False without ticking.
        """
        try:
            _period = max(1, int(self.candle_seconds))
        except Exception:
            return False
        _bucket = int(float(cursor_ts) // _period)
        if _bucket == getattr(self, "_last_cursor_bucket", None):
            return False
        self._last_cursor_bucket = _bucket
        await self._tick()
        return True

    async def _run_loop(self) -> None:
        """Call ``_tick`` until ``_stop_event`` is set, logging any exception."""
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Phantom %s error: %s", self.phantom_id, exc)
                self._bus.emit(
                    "phantom.error",
                    phantom=self.phantom_id,
                    error=str(exc),
                )
            if getattr(self, "_sim_mode", False):
                await self._stop_event.wait()
                break
            # Wall clock: 60s for every phantom once candle_seconds exceeds 60.
            await asyncio.sleep(min(self.candle_seconds, 60))

    async def _tick(self) -> None:
        """Fetch candles for ``timeframe`` and set ``last_summary`` from
        ``voting_engine``.

        Returns without setting ``last_summary`` on fewer than 30 candles, and
        constructs no order on any path.
        """
        raw = await self.exchange.get_ohlcv(
            self.symbol,
            timeframe=self.timeframe,
            limit=100,
        )
        candles = candles_from_raw(raw)
        if len(candles) < 30:
            return

        summary = self.voting_engine.compute_all(candles, self.timeframe)
        self.last_summary = summary

        self._bus.emit(
            "phantom.analysis",
            phantom=self.phantom_id,
            timeframe=self.timeframe,
            bullish=summary.bullish_count,
            bearish=summary.bearish_count,
            net_score=summary.net_score,
            confidence=summary.consensus_confidence,
        )

    def get_status(self) -> dict:
        return {
            "phantom_id": self.phantom_id,
            "parent_bot_id": self.parent_bot_id,
            "timeframe": self.timeframe,
            "state": self.state.value,
            "target_balance": self.target_balance,
            "total_trades": self.total_trades,
            "realised_pnl": round(self.realised_pnl, 4),
            "last_summary": {
                "bullish": self.last_summary.bullish_count if self.last_summary else 0,
                "bearish": self.last_summary.bearish_count if self.last_summary else 0,
                "net_score": self.last_summary.net_score if self.last_summary else 0,
                "confidence": (
                    self.last_summary.consensus_confidence if self.last_summary else 0
                ),
            },
        }


class TimeframeCoordinator:
    """Registry of ``PhantomBot`` instances and their ``TradeLock`` list.

    ``get_higher_tf_bias`` and ``get_multi_tf_summary`` read the registered
    phantoms; ``create_lock``, ``is_locked`` and ``tick_candle`` own the locks.
    """

    def __init__(self, lock_candle_count: int = 2, bus=None) -> None:
        self.lock_candle_count = lock_candle_count
        self._locks: list[TradeLock] = []
        self._phantoms: dict[str, PhantomBot] = {}
        self._bus = bus if bus is not None else get_event_bus()

    def register_phantom(self, phantom: PhantomBot) -> None:
        self._phantoms[phantom.phantom_id] = phantom

    def unregister_phantom(self, phantom_id: str) -> None:
        self._phantoms.pop(phantom_id, None)

    def get_phantoms_for_parent(self, parent_bot_id: str) -> list[PhantomBot]:
        return [p for p in self._phantoms.values() if p.parent_bot_id == parent_bot_id]

    def get_phantom_by_timeframe(
        self,
        parent_bot_id: str,
        timeframe: str,
    ) -> Optional[PhantomBot]:
        for p in self._phantoms.values():
            if p.parent_bot_id == parent_bot_id and p.timeframe == timeframe:
                return p
        return None

    def create_lock(
        self,
        source_timeframe: str,
        source_bot_id: str,
        locked_direction: SignalDirection,
        candle_count: Optional[int] = None,
    ) -> TradeLock:
        """Append a ``TradeLock`` on ``locked_direction`` sourced at
        ``source_timeframe``.

        ``candle_count`` defaults to ``lock_candle_count`` and is counted down
        by ``tick_candle``.
        """
        count = candle_count or self.lock_candle_count
        lock = TradeLock(
            source_timeframe=source_timeframe,
            source_bot_id=source_bot_id,
            direction=locked_direction,
            candles_remaining=count,
        )
        self._locks.append(lock)

        self._bus.emit(
            "timeframe.lock_created",
            source_tf=source_timeframe,
            locked_direction=locked_direction.name,
            candles=count,
        )
        logger.info(
            "Trade lock: %s locked %s direction for %d candles (from %s)",
            source_timeframe,
            locked_direction.name,
            count,
            source_bot_id,
        )
        return lock

    def is_locked(self, timeframe: str, direction: SignalDirection) -> bool:
        """Report whether any ``TradeLock`` above ``timeframe`` names
        ``direction``.

        Runs ``_cleanup_expired`` first, and returns False while ``_locks`` is
        empty.
        """
        self._cleanup_expired()
        target_rank = tf_rank(timeframe)

        for lock in self._locks:
            lock_rank = tf_rank(lock.source_timeframe)
            if lock_rank > target_rank and lock.direction == direction:
                return True
        return False

    def get_active_locks(self) -> list[dict]:
        """Return each unexpired ``TradeLock`` as a dict."""
        self._cleanup_expired()
        return [
            {
                "source_tf": lk.source_timeframe,
                "source_bot": lk.source_bot_id,
                "locked_direction": lk.direction.name,
                "candles_remaining": lk.candles_remaining,
            }
            for lk in self._locks
        ]

    def tick_candle(self, timeframe: str) -> None:
        """Decrement ``candles_remaining`` on every ``TradeLock`` sourced at
        ``timeframe``, then run ``_cleanup_expired``.
        """
        for lock in self._locks:
            if lock.source_timeframe == timeframe:
                lock.candles_remaining -= 1

        self._cleanup_expired()

    def _cleanup_expired(self) -> None:
        before = len(self._locks)
        self._locks = [lk for lk in self._locks if not lk.is_expired]
        removed = before - len(self._locks)
        if removed > 0:
            logger.debug("Cleaned up %d expired trade locks", removed)

    def get_higher_tf_bias(
        self,
        parent_bot_id: str,
        base_timeframe: str,
        min_confidence: float = 0.30,
    ) -> tuple[Optional[SignalDirection], dict]:
        """Weigh every registered phantom ranked above ``base_timeframe`` by
        ``rank`` times ``consensus_confidence``, skipping any below
        ``min_confidence``.

        Returns a ``SignalDirection`` with a detail dict, or None when no
        higher phantom has a ``last_summary``.
        """
        base_rank = tf_rank(base_timeframe)
        higher = [
            p
            for p in self.get_phantoms_for_parent(parent_bot_id)
            if p.rank > base_rank and p.last_summary is not None
        ]
        if not higher:
            return None, {"reason": "no higher-TF phantoms with summaries"}

        bull_weight = 0.0
        bear_weight = 0.0
        contrib: list[dict] = []
        for p in higher:
            s = p.last_summary
            if s.consensus_confidence < min_confidence:
                contrib.append(
                    {
                        "tf": p.timeframe,
                        "skipped": True,
                        "conf": s.consensus_confidence,
                        "direction": s.consensus_direction.name,
                    }
                )
                continue
            # A 4h phantom at rank 6 and confidence 0.5 contributes 3.0.
            weight = max(1, p.rank) * float(s.consensus_confidence)
            if s.consensus_direction == SignalDirection.BULLISH:
                bull_weight += weight
            elif s.consensus_direction == SignalDirection.BEARISH:
                bear_weight += weight
            contrib.append(
                {
                    "tf": p.timeframe,
                    "weight": round(weight, 3),
                    "direction": s.consensus_direction.name,
                    "conf": round(s.consensus_confidence, 3),
                }
            )

        if bull_weight == 0 and bear_weight == 0:
            return SignalDirection.NEUTRAL, {
                "bull_weight": 0.0,
                "bear_weight": 0.0,
                "contributors": contrib,
                "reason": "all higher-TF phantoms below confidence floor or NEUTRAL",
            }
        if bull_weight > bear_weight:
            direction = SignalDirection.BULLISH
        elif bear_weight > bull_weight:
            direction = SignalDirection.BEARISH
        else:
            direction = SignalDirection.NEUTRAL
        return direction, {
            "bull_weight": round(bull_weight, 3),
            "bear_weight": round(bear_weight, 3),
            "contributors": contrib,
        }

    def get_multi_tf_summary(self, parent_bot_id: str) -> dict:
        """Return each registered phantom's ``last_summary`` for
        ``parent_bot_id``, keyed by timeframe in ``rank`` order.

        A phantom without a ``last_summary`` contributes no key.
        """
        phantoms = self.get_phantoms_for_parent(parent_bot_id)
        result = {}

        for p in sorted(phantoms, key=lambda x: x.rank):
            if p.last_summary:
                result[p.timeframe] = {
                    "bullish": p.last_summary.bullish_count,
                    "bearish": p.last_summary.bearish_count,
                    "neutral": p.last_summary.neutral_count,
                    "net_score": p.last_summary.net_score,
                    "confidence": p.last_summary.consensus_confidence,
                    "direction": p.last_summary.consensus_direction.name,
                    "signals": [
                        {
                            "indicator": s.indicator,
                            "direction": s.direction.name,
                            "confidence": round(s.confidence, 3),
                            "details": s.details,
                        }
                        for s in p.last_summary.signals
                    ],
                    "locks": [
                        lk
                        for lk in self.get_active_locks()
                        if lk["source_tf"] == p.timeframe
                    ],
                }

        return result


class PhantomBalanceManager:
    """Owns one ``PhantomBot`` set per parent bot id.

    ``create_phantom_set`` builds and registers them on ``coordinator``, and
    ``start_all``, ``stop_all`` and ``remove_set`` act on a whole set.
    """

    def __init__(self, coordinator: TimeframeCoordinator) -> None:
        self.coordinator = coordinator
        self._sets: dict[str, list[PhantomBot]] = {}

    def create_phantom_set(
        self,
        parent_bot_id: str,
        timeframes: list[str],
        target_balance: float,
        exchange: ExchangeInterface,
        symbol: str,
        balance_scaling: str = "equal",
        ta_weights: Optional[dict[str, float]] = None,
    ) -> list[PhantomBot]:
        """Build one ``PhantomBot`` per entry in ``timeframes`` and
        register each on ``coordinator``.

        ``balance_scaling`` of "weighted" scales ``target_balance`` by
        ``tf_rank``; any other value gives every phantom ``target_balance``.
        """
        phantoms = []
        for i, tf in enumerate(sorted(timeframes, key=tf_rank)):
            if balance_scaling == "weighted":
                rank = tf_rank(tf)
                max_rank = tf_rank(timeframes[-1]) if timeframes else 1
                weight = 0.5 + 0.5 * (rank / (max_rank + 1))
                ptb = target_balance * weight
            else:
                ptb = target_balance

            phantom = PhantomBot(
                parent_bot_id=parent_bot_id,
                phantom_id=f"{parent_bot_id}_phantom_{tf}",
                timeframe=tf,
                target_balance=ptb,
                exchange=exchange,
                symbol=symbol,
                coordinator=self.coordinator,
                ta_weights=ta_weights,
                # Inherit the coordinator's bus; None falls back to the global.
                bus=getattr(self.coordinator, "_bus", None),
            )
            self.coordinator.register_phantom(phantom)
            phantoms.append(phantom)

        self._sets[parent_bot_id] = phantoms
        return phantoms

    async def start_all(self, parent_bot_id: str) -> None:
        for phantom in self._sets.get(parent_bot_id, []):
            await phantom.start()

    async def stop_all(self, parent_bot_id: str) -> None:
        for phantom in self._sets.get(parent_bot_id, []):
            await phantom.stop()

    def get_phantoms(self, parent_bot_id: str) -> list[PhantomBot]:
        return self._sets.get(parent_bot_id, [])

    def remove_set(self, parent_bot_id: str) -> None:
        for phantom in self._sets.pop(parent_bot_id, []):
            self.coordinator.unregister_phantom(phantom.phantom_id)
