"""
# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
phantom_balance.py — Phantom Balance Bots v1.1
# ┌─────────────────────────────────────────────────────────────┐
# │ AI DEVELOPER NOTE                                           │
# │                                                             │
# │ PATENT-ELIGIBLE INVENTION #2.                               │
# │                                                             │
# │ Phantom Balance creates read-only copies of a bot on        │
# │ multiple timeframes (5m, 15m, 1h, 4h). Each phantom         │
# │ computes TA independently. The hierarchy:                   │
# │                                                             │
# │   4h TradeLock overrides 1h overrides 15m overrides 5m     │
# │                                                             │
# │ If 4h TA says "don't trade", all lower TFs are blocked.    │
# │ If 5m TA says "scrum" but 1h says "trend hold", blocked.   │
# │                                                             │
# │ The phantom bots never place orders. They only vote.        │
# │ The primary bot on its home timeframe makes the final       │
# │ execution decision using the aggregated phantom signals.    │
# │                                                             │
# │ Validated: 4/5 scenarios improved in Phantom Balance sim.   │
# └─────────────────────────────────────────────────────────────┘
================================================
Phantom Balance Bots are shadow instances of a parent Speculative
Scrumming Bot that operate on different timeframes simultaneously.

Architecture:
  ┌────────────────────────────────────────┐
  │         Parent Scrumming Bot           │
  │           (e.g. 1h timeframe)          │
  ├────────────────────────────────────────┤
  │  Phantom 5m │ Phantom 15m │ Phantom 4h │ Phantom 1d │
  └────────────────────────────────────────┘

Key behaviours:
  1. Each phantom tracks its own Target Balance on its own timeframe
     but shares the same exchange connection and asset pair.
  2. Higher timeframe phantoms can identify optimal large-scale exits
     and "pull in" lower timeframes to maximize profit/accumulation.
  3. A higher-TF phantom trading will temporarily DISABLE contradicting
     trades on lower timeframes for a configurable candle count.
  4. Phantoms communicate via the TimeframeCoordinator.

Timeframe hierarchy (lowest → highest):
  1m < 5m < 15m < 30m < 1h < 2h < 4h < 6h < 12h < 1d < 1w
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..exchange.base import ExchangeInterface

from ..core.event_bus import get_event_bus
from .bot_container import BotConfig, BotMode, BotState
from .ta_engine import VotingEngine, VotingSummary, SignalDirection, candles_from_raw

logger = logging.getLogger("acervator.phantom")


# ---------------------------------------------------------------------------
# Timeframe hierarchy
# ---------------------------------------------------------------------------
TIMEFRAME_ORDER: list[str] = [
    "1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w",
]

TIMEFRAME_SECONDS: dict[str, int] = {
    "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600,
    "12h": 43200, "1d": 86400, "1w": 604800,
}


def tf_rank(timeframe: str) -> int:
    """Numeric rank of a timeframe (higher = longer)."""
    try:
        return TIMEFRAME_ORDER.index(timeframe)
    except ValueError:
        return -1


def is_higher_tf(a: str, b: str) -> bool:
    """Return True if timeframe *a* is strictly higher than *b*."""
    return tf_rank(a) > tf_rank(b)


# ---------------------------------------------------------------------------
# Trade lock — used to prevent contradicting trades
# ---------------------------------------------------------------------------
@dataclass
class TradeLock:
    """
    A temporary lock placed by a higher-timeframe phantom to prevent
    contradicting trades on lower timeframes.
    """
    source_timeframe: str
    source_bot_id: str
    direction: SignalDirection     # The direction that is LOCKED OUT
    candles_remaining: int         # How many candles this lock persists
    created_at: float = field(default_factory=time.time)
    lock_all_lower: bool = True    # Lock all TFs below source, not just one

    @property
    def is_expired(self) -> bool:
        return self.candles_remaining <= 0


# ---------------------------------------------------------------------------
# Phantom Balance Bot
# ---------------------------------------------------------------------------
class PhantomBalanceBot:
    """
    A shadow of a parent ScrummingBot operating on a specific timeframe.

    Each phantom:
      - Has its own target balance (can differ from parent)
      - Runs TA analysis on its assigned timeframe
      - Coordinates with other phantoms via the TimeframeCoordinator
      - Can trigger "pull-in" events that override lower-TF phantoms
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
        # v3.24.64 (C18) — in sim the REPLAY owns the clock. See
        # tick_for_cursor and the sim branch in _run_loop.
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

        # v3.24.61 (C17 / SN-42) — injectable; this bot emits on the bus
        # at :173/:200/:251. Defaults to the process-wide bus so live
        # construction is unchanged.
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

    # -- Lifecycle ------------------------------------------------------
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
        """Advance this phantom iff its own timeframe closed a candle.

        v3.24.64 (C18). The replay owns the clock, so it calls this as
        the cursor moves instead of letting the phantom sleep on wall
        time. A phantom on 1h ticks once per simulated hour of tape, not
        once per real minute.

        Returns True when a tick actually ran, so a caller can count
        them — "the phantoms were enabled" and "the phantoms ran" are
        different claims, and only the second one is worth verifying.

        Idempotent within a bucket: called repeatedly inside the same
        candle it runs once. That is what keeps a phantom's sampling
        moment deterministic across replays of the same tape.
        """
        try:
            _period = max(1, int(self.candle_seconds))
        except Exception:  # R28-OK: unreadable period -> do not tick
            return False
        _bucket = int(float(cursor_ts) // _period)
        if _bucket == getattr(self, "_last_cursor_bucket", None):
            return False
        self._last_cursor_bucket = _bucket
        await self._tick()
        return True

    # -- Main loop ------------------------------------------------------
    async def _run_loop(self) -> None:
        """Phantom analysis and trading loop."""
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
            # v3.24.64 (C18) — a sim phantom does NOT self-schedule.
            #
            # This sleep is WALL CLOCK: min(candle_seconds, 60) is 60
            # real seconds for every phantom regardless of timeframe. In
            # live that is roughly right — real time and market time are
            # the same thing. In a replay they are not: a run covering
            # ~15,000 candles finishes in minutes, so each phantom got a
            # handful of ticks at arbitrary REPLAY positions, and
            # get_higher_tf_bias read a last_summary computed at a
            # random point in history.
            #
            # That made SN-1 (six phantoms sharing one series) only half
            # the fidelity problem: giving them six DIFFERENT series
            # still leaves the sampling moment random. In sim the replay
            # drives ticks through `tick_for_cursor`, so a phantom
            # advances exactly when its own timeframe closes a candle.
            if getattr(self, "_sim_mode", False):
                await self._stop_event.wait()
                break
            # Sleep for one candle period (phantom operates per-candle)
            await asyncio.sleep(min(self.candle_seconds, 60))

    async def _tick(self) -> None:
        """One analysis cycle.

        v3.15.61 redesign (operator directive 2026-04-26):
          "Redesign phantom bots so that they ONLY provide TA over rides
           and do not place orders until AFTER the override is in place
           and based upon the higher TF TA readings. As long as the higher
           TF bot is considering placing an order, the lower TF
           measurements are just used for fine tuning the order timing."
          "This must be wired gracefully to prevent rogue order placement
           as observed in early development."

        Phantoms now do ONE thing: compute TA on their assigned timeframe
        and expose the result via ``self.last_summary``. They do not
        propose trades, do not maintain holdings, do not consult target
        balance, and have no code path — at all — that constructs an
        order. The trade-execution helpers were removed wholesale; if
        any future change tries to call ``phantom._execute_buy`` or
        ``phantom._execute_sell`` it will raise ``AttributeError`` rather
        than fall through into a no-op + bus emit (the prior MEM-259
        defense had the right intent but kept a residual code path the
        operator caught firing real orders during early development).

        The parent ScrummingBot consumes the multi-TF bias via
        ``TimeframeCoordinator.get_higher_tf_bias`` to decide whether to
        proceed with its OWN order. Lower-TF phantoms (vs. the parent
        TF) are used to fine-tune timing inside the parent's tick loop;
        higher-TF phantoms gate the directional intent.
        """
        # Fetch candles for this timeframe
        raw = await self.exchange.get_ohlcv(
            self.symbol, timeframe=self.timeframe, limit=100,
        )
        candles = candles_from_raw(raw)
        if len(candles) < 30:
            return

        # Run TA voting — the only purpose of a phantom.
        summary = self.voting_engine.compute_all(candles, self.timeframe)
        self.last_summary = summary

        # Emit analysis event so the GUI (Indicator Panel, multi-TF
        # summary) and the parent bot's gate can consume it.
        self._bus.emit(
            "phantom.analysis",
            phantom=self.phantom_id,
            timeframe=self.timeframe,
            bullish=summary.bullish_count,
            bearish=summary.bearish_count,
            net_score=summary.net_score,
            confidence=summary.consensus_confidence,
        )
        # That's it. No trade construction, no order placement, no
        # delta-vs-target math. Phantoms are READ-ONLY TA observers.

    # NOTE — v3.15.61: the methods _execute_sell and _execute_buy were
    # REMOVED wholesale. They had been hard-disabled to no-ops in MEM-259
    # but the residual code path was still a regression risk. Removing
    # them entirely makes "rogue phantom order" a structural impossibility
    # — the AttributeError from any accidental future call is a louder
    # failure mode than a silent no-op.

    # -- Status --------------------------------------------------------
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
                "confidence": self.last_summary.consensus_confidence if self.last_summary else 0,
            },
        }


# ---------------------------------------------------------------------------
# Timeframe Coordinator
# ---------------------------------------------------------------------------
class TimeframeCoordinator:
    """
    Manages the hierarchy of Phantom Balance Bots and enforces:
      1. Higher-TF prioritization — locks that prevent contradicting trades
      2. Pull-in mechanics — higher TF bots override lower TF behaviour
      3. Lock expiration per candle count

    Usage::

        coord = TimeframeCoordinator()
        coord.create_lock("4h", "phantom_4h", SignalDirection.BULLISH, candle_count=3)
        # Now all timeframes below 4h are locked from bullish trades for 3 candles
        assert coord.is_locked("1h", SignalDirection.BULLISH) == True
        assert coord.is_locked("1h", SignalDirection.BEARISH) == False  # Only bullish locked
        assert coord.is_locked("1d", SignalDirection.BULLISH) == False  # Higher TF, not locked
    """

    def __init__(self, lock_candle_count: int = 2, bus=None) -> None:
        self.lock_candle_count = lock_candle_count
        self._locks: list[TradeLock] = []
        self._phantoms: dict[str, PhantomBalanceBot] = {}
        # v3.24.61 (C17 / SN-42) — injectable. This coordinator emits on
        # the bus (:358), and ScrummingBot constructs one AFTER its own
        # sim private-bus swap without passing it, so a sim bot's
        # coordinator emitted onto the LIVE bus. Defaults to the
        # process-wide bus, so live construction is unchanged.
        self._bus = bus if bus is not None else get_event_bus()

    # -- Phantom management ---------------------------------------------
    def register_phantom(self, phantom: PhantomBalanceBot) -> None:
        self._phantoms[phantom.phantom_id] = phantom

    def unregister_phantom(self, phantom_id: str) -> None:
        self._phantoms.pop(phantom_id, None)

    def get_phantoms_for_parent(self, parent_bot_id: str) -> list[PhantomBalanceBot]:
        return [
            p for p in self._phantoms.values()
            if p.parent_bot_id == parent_bot_id
        ]

    def get_phantom_by_timeframe(
        self, parent_bot_id: str, timeframe: str,
    ) -> Optional[PhantomBalanceBot]:
        for p in self._phantoms.values():
            if p.parent_bot_id == parent_bot_id and p.timeframe == timeframe:
                return p
        return None

    # -- Lock management ------------------------------------------------
    def create_lock(
        self,
        source_timeframe: str,
        source_bot_id: str,
        locked_direction: SignalDirection,
        candle_count: Optional[int] = None,
    ) -> TradeLock:
        """
        Create a trade lock.  All timeframes BELOW *source_timeframe*
        are prevented from trading in *locked_direction* for
        *candle_count* candles of the source timeframe.
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
            source_timeframe, locked_direction.name, count, source_bot_id,
        )
        return lock

    def is_locked(self, timeframe: str, direction: SignalDirection) -> bool:
        """
        Check if *timeframe* is locked from trading in *direction*.
        A timeframe is locked if any HIGHER timeframe has an active
        lock against that direction.
        """
        self._cleanup_expired()
        target_rank = tf_rank(timeframe)

        for lock in self._locks:
            lock_rank = tf_rank(lock.source_timeframe)
            if lock_rank > target_rank and lock.direction == direction:
                return True
        return False

    def get_active_locks(self) -> list[dict]:
        """Return all active locks as dicts for UI display."""
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
        """
        Called when a candle closes on *timeframe*.  Decrements lock
        counters for locks sourced from this timeframe.
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

    # ------------------------------------------------------------------
    # v3.15.61 — Higher-TF directional-bias accessor (operator directive
    # 2026-04-26: "As long as the higher TF bot is considering placing
    # an order, the lower TF measurements are just used for fine tuning
    # the order timing.")
    # ------------------------------------------------------------------
    def get_higher_tf_bias(
        self,
        parent_bot_id: str,
        base_timeframe: str,
        min_confidence: float = 0.30,
    ) -> tuple[Optional[SignalDirection], dict]:
        """Compute the dominant directional bias from phantoms whose
        timeframe is HIGHER than ``base_timeframe``.

        Returns (direction, detail) where:
          direction: SignalDirection.BULLISH / BEARISH / NEUTRAL when
              the higher-TF consensus is meaningful; None when there
              are no higher-TF phantoms with usable summaries (in which
              case the parent gate should default to "no override").
          detail: dict with raw bullish/bearish weight + the contributing
              phantoms for log surfacing.

        Weighting: higher-TF phantoms count more (linear in tf_rank).
        A phantom contributes only if its
        ``last_summary.consensus_confidence >= min_confidence`` —
        low-confidence phantoms abstain.

        This is the read accessor the parent ScrummingBot's SCRUM/FOLD
        gates use to enforce the operator's "higher TF gates lower TF
        intent" directive. It NEVER mutates state, NEVER places orders,
        and is safe to call from any thread (read-only over the phantom
        registry).
        """
        base_rank = tf_rank(base_timeframe)
        higher = [
            p for p in self.get_phantoms_for_parent(parent_bot_id)
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
                contrib.append({
                    "tf": p.timeframe, "skipped": True,
                    "conf": s.consensus_confidence,
                    "direction": s.consensus_direction.name,
                })
                continue
            # Linear weight: 4h-rank=6 contributes 6, 1d-rank=9 contributes 9
            weight = max(1, p.rank) * float(s.consensus_confidence)
            if s.consensus_direction == SignalDirection.BULLISH:
                bull_weight += weight
            elif s.consensus_direction == SignalDirection.BEARISH:
                bear_weight += weight
            # NEUTRAL contributes to neither side.
            contrib.append({
                "tf": p.timeframe, "weight": round(weight, 3),
                "direction": s.consensus_direction.name,
                "conf": round(s.consensus_confidence, 3),
            })

        if bull_weight == 0 and bear_weight == 0:
            return SignalDirection.NEUTRAL, {
                "bull_weight": 0.0, "bear_weight": 0.0,
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

    # -- Multi-timeframe analysis summary --------------------------------
    def get_multi_tf_summary(self, parent_bot_id: str) -> dict:
        """
        Return a summary of all phantom analyses for a parent bot,
        organized by timeframe for the indicator voting window.
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
                        lk for lk in self.get_active_locks()
                        if lk["source_tf"] == p.timeframe
                    ],
                }

        return result


# ---------------------------------------------------------------------------
# Phantom Balance Manager — creates and manages phantom sets for a parent bot
# ---------------------------------------------------------------------------
class PhantomBalanceManager:
    """
    High-level manager that creates a set of Phantom Balance Bots
    for a parent Speculative Scrumming Bot.

    Usage::

        mgr = PhantomBalanceManager(coordinator)
        phantoms = mgr.create_phantom_set(
            parent_bot_id="bot_abc",
            timeframes=["5m", "15m", "1h", "4h", "1d"],
            target_balance=200.0,
            exchange=exchange,
            symbol="BTC/USDT",
        )
        await mgr.start_all("bot_abc")
    """

    def __init__(self, coordinator: TimeframeCoordinator) -> None:
        self.coordinator = coordinator
        self._sets: dict[str, list[PhantomBalanceBot]] = {}

    def create_phantom_set(
        self,
        parent_bot_id: str,
        timeframes: list[str],
        target_balance: float,
        exchange: ExchangeInterface,
        symbol: str,
        balance_scaling: str = "equal",
        ta_weights: Optional[dict[str, float]] = None,
    ) -> list[PhantomBalanceBot]:
        """
        Create a set of phantoms for a parent bot.

        *balance_scaling*:
          "equal"  — each phantom gets the same target balance
          "weighted" — higher TFs get proportionally larger balances
        """
        phantoms = []
        for i, tf in enumerate(sorted(timeframes, key=tf_rank)):
            if balance_scaling == "weighted":
                # Higher TFs get larger share
                rank = tf_rank(tf)
                max_rank = tf_rank(timeframes[-1]) if timeframes else 1
                weight = 0.5 + 0.5 * (rank / (max_rank + 1))
                ptb = target_balance * weight
            else:
                ptb = target_balance

            phantom = PhantomBalanceBot(
                parent_bot_id=parent_bot_id,
                phantom_id=f"{parent_bot_id}_phantom_{tf}",
                timeframe=tf,
                target_balance=ptb,
                exchange=exchange,
                symbol=symbol,
                coordinator=self.coordinator,
                ta_weights=ta_weights,
                # v3.24.61 (C17) — inherit the coordinator's bus. The
                # coordinator already carries the sim's private bus when
                # there is one, so phantoms follow their parent's
                # isolation instead of each resolving the global bus.
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

    def get_phantoms(self, parent_bot_id: str) -> list[PhantomBalanceBot]:
        return self._sets.get(parent_bot_id, [])

    def remove_set(self, parent_bot_id: str) -> None:
        for phantom in self._sets.pop(parent_bot_id, []):
            self.coordinator.unregister_phantom(phantom.phantom_id)
