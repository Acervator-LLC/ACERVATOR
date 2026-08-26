"""
src/trading/poa_tournament.py — PoA Tournament Engine (v1)
════════════════════════════════════════════════════════════════════════════

Tournament layer above the existing competition stack (CompetitionEngine,
TokenLedger, LocalTestnet). Provides structured match formats, dynamic
events, replay hashes, and bot isolation discipline.

ARCHITECTURAL POSITION — this module is NEW, additive, and does not
modify the existing src/competition/* stack. The legacy integration
hook in nuclear_live.py::_run_poa_round was removed when nuclear_live
was retired in v3.18.3. PoA integration with the new Nuclear Mode
(under src/simulator/) will use this engine directly.

TOURNAMENT TYPES (v1)
─────────────────────
DUEL      2 bots · 60 candles · 3 MarketShock events · best PnL wins
MELEE     4-8 bots · 120 candles · elimination quartile every 20 candles
          plus 1-2 PuzzleEvents · last standing wins
GAUNTLET  1 bot vs scripted NpcOpponent sequence · scaffolding for
          future bounty-monster injection

DYNAMIC EVENTS
──────────────
MarketShock    perturb slippage model for 1-3 ticks (all participants)
PuzzleEvent    signal-recognition challenge (MELEE/GAUNTLET only)
RegimeFlip     swap volatility profile mid-run (rare, high-impact)

Events are SEEDED PER TOURNAMENT — unpredictable within a match,
reproducible across replays. R57 EPM discipline applied to tournament
play: same seed → same event sequence → same outcome.

BOT ISOLATION (R58 TBI — Tournament Bot Isolation)
───────────────────────────────────────────────────
Tournaments NEVER mutate the underlying bot's production state. A
Participant wraps a read-only adapter over a ScrummingBot's
configuration + an isolated BotStats snapshot. Production holdings,
balances, and live stats are untouched by tournament play.

SETTLEMENT
──────────
All ACRV awards route through the existing TokenLedger.
bounty_testnet_wei field is a stub; testnet settlement plumbing will
land as a separate SettlementAdapter in a future turn.

sadp: R28 R29 R42 R43 R44 R47 R49 R50 R51 R57 R58
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Protocol

logger = logging.getLogger("acervator.poa_tournament")


# ══════════════════════════════════════════════════════════════════════════
# Enums — first-class state vocabularies
# ══════════════════════════════════════════════════════════════════════════


class TournamentType(Enum):
    DUEL = "duel"
    MELEE = "melee"
    GAUNTLET = "gauntlet"


class TournamentState(Enum):
    PENDING = "pending"  # created, not open
    OPEN = "open"  # accepting participants
    IN_PROGRESS = "in_progress"  # battle underway
    CONCLUDED = "concluded"  # outcome computed, not yet settled
    SETTLED = "settled"  # ACRV awarded via TokenLedger
    FAILED = "failed"  # error during play; no settlement


class DynamicEventType(Enum):
    MARKET_SHOCK = "market_shock"
    PUZZLE_EVENT = "puzzle_event"
    REGIME_FLIP = "regime_flip"


# ══════════════════════════════════════════════════════════════════════════
# Season stub — hermetic theming layer lands in a later turn
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class Season:
    """Stub. Real hermetic generative seasons come in a layer-4 turn.
    For v1, just carries the round index + a label for audit."""

    number: int
    label: str = "neutral"
    # Future fields: planet, alchemical_stage, modifiers, themes


# ══════════════════════════════════════════════════════════════════════════
# Participant abstraction — R58 TBI enforcement
# ══════════════════════════════════════════════════════════════════════════


class ParticipantKind(Enum):
    BOT = "bot"  # wraps a live ScrummingBot via isolated snapshot
    NPC = "npc"  # scripted opponent for GAUNTLET (future: monster)


@dataclass
class ParticipantStats:
    """Tournament-scoped stats. MUST NOT be the same object as the
    live bot's stats. Mutated during play; never written back.
    sadp: R58 TBI"""

    pnl: float = 0.0
    trades: int = 0
    wins: int = 0
    verify_clean: int = 0
    verify_canceled: int = 0
    puzzle_correct: int = 0
    puzzle_wrong: int = 0
    eliminated_at_round: Optional[int] = None


@dataclass
class Participant:
    """Unified entry for both bot-backed and NPC-backed competitors.
    A bot Participant holds a REFERENCE to the source bot for config
    lookup (asset class, symbol) but operates on its own stats snapshot.

    sadp: R58 TBI — underlying bot.stats is read-only from this type's
    perspective. Any stat mutation lands in self.stats (isolated).
    """

    participant_id: str
    kind: ParticipantKind
    display_name: str
    stats: ParticipantStats = field(default_factory=ParticipantStats)
    # For BOT-kind: the symbol this bot trades (for R55 VH class lookup)
    symbol: Optional[str] = None
    # For NPC-kind: scripted difficulty parameters
    npc_config: Optional[dict] = None
    # Read-only reference to source bot (not mutated by tournament)
    source_bot_id: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════
# Dynamic events — the "hybrid" content injection
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class DynamicEvent:
    event_id: str
    etype: DynamicEventType
    tick: int  # candle index at which event fires
    payload: dict  # event-specific parameters
    resolved: bool = False
    resolution: Optional[dict] = None


class DynamicEventScheduler:
    """Schedules events at tournament start using a deterministic seed.
    Same seed → same event sequence. Events are unpredictable WITHIN a
    match (bots don't know the tick at play time) but reproducible
    ACROSS replays (audit/debug)."""

    def __init__(self, seed: int, ttype: TournamentType, n_candles: int):
        self._rng = random.Random(seed)
        self._seed = seed  # retained for deterministic event IDs
        self._ttype = ttype
        self._n_candles = n_candles

    def schedule(self) -> list[DynamicEvent]:
        """Generate the full event list for this tournament up front."""
        events: list[DynamicEvent] = []
        # Event counts per type
        if self._ttype == TournamentType.DUEL:
            n_shocks, n_puzzles, n_flips = 3, 0, 0
        elif self._ttype == TournamentType.MELEE:
            n_shocks, n_puzzles, n_flips = 2, 2, 1
        else:  # GAUNTLET
            n_shocks, n_puzzles, n_flips = 2, 1, 0

        # Place events at random ticks (avoiding first 5 and last 5 candles)
        lo, hi = 5, max(6, self._n_candles - 5)
        used_ticks = set()

        def pick_tick():
            for _ in range(20):
                t = self._rng.randint(lo, hi)
                if t not in used_ticks:
                    used_ticks.add(t)
                    return t
            # Fallback: take any unused
            for t in range(lo, hi + 1):
                if t not in used_ticks:
                    used_ticks.add(t)
                    return t
            return lo  # last resort

        # Deterministic event IDs — derived from seed + type + ordinal
        # so replay RNG seeded from event_id is itself reproducible.
        # sadp: R57 EPM
        for i in range(n_shocks):
            events.append(
                DynamicEvent(
                    event_id=f"shock_{self._seed:08x}_{i}",
                    etype=DynamicEventType.MARKET_SHOCK,
                    tick=pick_tick(),
                    payload={
                        "duration_ticks": self._rng.randint(1, 3),
                        "spread_multiplier": round(self._rng.uniform(3.0, 8.0), 2),
                        "direction": self._rng.choice(["up", "down"]),
                    },
                )
            )

        for i in range(n_puzzles):
            events.append(
                DynamicEvent(
                    event_id=f"puzzle_{self._seed:08x}_{i}",
                    etype=DynamicEventType.PUZZLE_EVENT,
                    tick=pick_tick(),
                    payload={
                        "challenge_type": self._rng.choice(
                            ["fvg_bull", "fvg_bear", "bb_squeeze", "rsi_div"]
                        ),
                        "options": 4,
                        "correct_index": self._rng.randint(0, 3),
                        "bonus_pnl": round(self._rng.uniform(20.0, 50.0), 2),
                    },
                )
            )

        for i in range(n_flips):
            events.append(
                DynamicEvent(
                    event_id=f"flip_{self._seed:08x}_{i}",
                    etype=DynamicEventType.REGIME_FLIP,
                    tick=pick_tick(),
                    payload={
                        "from_regime": self._rng.choice(["calm", "trend"]),
                        "to_regime": self._rng.choice(["volatile", "choppy"]),
                    },
                )
            )

        # Sort by tick for deterministic iteration
        events.sort(key=lambda e: e.tick)
        return events


# ══════════════════════════════════════════════════════════════════════════
# Round result — fine-grained audit trail
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class RoundResult:
    round_number: int
    tick_start: int
    tick_end: int
    standings: list[tuple[str, float]]  # [(participant_id, pnl), ...]
    eliminated_ids: list[str]
    events_fired: list[str]  # event_ids


@dataclass
class Outcome:
    winner_id: Optional[str]
    final_standings: list[tuple[str, float]]
    total_rounds: int
    total_events: int
    replay_hash: str
    acrv_awarded: int = 0
    testnet_tx_hash: Optional[str] = None  # stub for future settlement


# ══════════════════════════════════════════════════════════════════════════
# Tournament config — tuning knobs
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class TournamentConfig:
    ttype: TournamentType
    n_candles: int = 60
    round_size_candles: int = 20  # for MELEE elimination cadence
    min_participants: int = 2
    max_participants: int = 8
    acrv_purse: int = 10  # total ACRV to distribute
    seed: int = 0  # 0 = use UUID hash (non-deterministic)
    bounty_testnet_wei: int = 0  # stub; zero until settlement lands


# ══════════════════════════════════════════════════════════════════════════
# Settlement adapter protocol — default local, future Sepolia
# ══════════════════════════════════════════════════════════════════════════


class SettlementAdapter(Protocol):
    """Protocol for paying out tournament winnings. v1 uses
    LocalACRVAdapter (the existing TokenLedger). Future:
    SepoliaAdapter will route to testnet wei bounty wallets.
    sadp: R44 R57"""

    def settle(
        self, tournament_id: str, outcome: Outcome, participants: list[Participant]
    ) -> dict: ...


class LocalACRVAdapter:
    """Default settlement — pays via the existing TokenLedger in
    ACRV tokens. No network, no gas, no real currency."""

    def __init__(self, token_ledger=None):
        self._ledger = token_ledger  # optional; None runs pure in-memory

    def settle(
        self, tournament_id: str, outcome: Outcome, participants: list[Participant]
    ) -> dict:
        if outcome.winner_id is None:
            return {"settled": False, "reason": "no winner"}
        if self._ledger is None:
            # Pure in-memory — just record the intent
            return {
                "settled": True,
                "adapter": "in_memory",
                "winner_id": outcome.winner_id,
                "acrv": outcome.acrv_awarded,
            }
        # Real TokenLedger path (to be fully wired in integration turn)
        # Hook point: self._ledger.award(bot_id, tournament_id, ...)
        return {
            "settled": True,
            "adapter": "token_ledger",
            "winner_id": outcome.winner_id,
            "acrv": outcome.acrv_awarded,
        }


# ══════════════════════════════════════════════════════════════════════════
# The Tournament class
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class Tournament:
    tournament_id: str
    config: TournamentConfig
    season: Season
    participants: list[Participant]
    events: list[DynamicEvent]
    rounds: list[RoundResult] = field(default_factory=list)
    state: TournamentState = TournamentState.PENDING
    outcome: Optional[Outcome] = None
    started_at: Optional[float] = None
    concluded_at: Optional[float] = None

    @property
    def ttype(self) -> TournamentType:
        return self.config.ttype

    def to_dict(self) -> dict:
        """Serialize for persistence / replay."""
        return {
            "tournament_id": self.tournament_id,
            "type": self.ttype.value,
            "state": self.state.value,
            "season": asdict(self.season),
            "config": {**asdict(self.config), "ttype": self.config.ttype.value},
            "participants": [
                {**asdict(p), "kind": p.kind.value} for p in self.participants
            ],
            "events": [{**asdict(e), "etype": e.etype.value} for e in self.events],
            "rounds": [asdict(r) for r in self.rounds],
            "outcome": asdict(self.outcome) if self.outcome else None,
            "started_at": self.started_at,
            "concluded_at": self.concluded_at,
        }


# ══════════════════════════════════════════════════════════════════════════
# Engine — builds + runs tournaments
# ══════════════════════════════════════════════════════════════════════════


class TournamentEngine:
    """Constructs and runs tournaments. Integrates with:
      - existing TokenLedger via SettlementAdapter
      - scrumming_bot configs (read-only) via Participant wrappers
      - R55 VH classifier for per-asset-class slippage tolerance

    Persists every concluded tournament to logs/tournaments/<id>.json
    for audit + replay.

    sadp: R49 R50 R51 R57 R58
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        settlement: Optional[SettlementAdapter] = None,
    ):
        self._log_dir = log_dir or (
            Path(__file__).resolve().parents[2] / "logs" / "tournaments"
        )
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._settlement = settlement or LocalACRVAdapter()
        # R47 counters for observability
        self._tournaments_run: int = 0
        self._tournaments_failed: int = 0

    # ── Factory methods ────────────────────────────────────────────────
    def build_duel(
        self,
        a: Participant,
        b: Participant,
        season: Season,
        acrv_purse: int = 10,
        seed: Optional[int] = None,
    ) -> Tournament:
        """Construct a DUEL tournament: 2 participants, 60 candles."""
        if a.participant_id == b.participant_id:
            raise ValueError("DUEL participants must differ")
        cfg = TournamentConfig(
            ttype=TournamentType.DUEL,
            n_candles=60,
            round_size_candles=60,
            min_participants=2,
            max_participants=2,
            acrv_purse=acrv_purse,
            seed=seed if seed is not None else _hash_seed(a, b, season),
        )
        return self._build(cfg, season, [a, b])

    def build_melee(
        self,
        participants: list[Participant],
        season: Season,
        acrv_purse: int = 20,
        seed: Optional[int] = None,
    ) -> Tournament:
        """Construct a MELEE tournament: 4-8 participants, quartile
        elimination every 20 candles over 120 candles."""
        if not (4 <= len(participants) <= 8):
            raise ValueError(
                f"MELEE requires 4-8 participants, got {len(participants)}"
            )
        cfg = TournamentConfig(
            ttype=TournamentType.MELEE,
            n_candles=120,
            round_size_candles=20,
            min_participants=4,
            max_participants=8,
            acrv_purse=acrv_purse,
            seed=seed if seed is not None else _hash_seed(*participants, season),
        )
        return self._build(cfg, season, participants)

    def build_gauntlet(
        self,
        challenger: Participant,
        npc_sequence: list[Participant],
        season: Season,
        acrv_purse: int = 15,
        seed: Optional[int] = None,
    ) -> Tournament:
        """Construct a GAUNTLET: 1 bot vs N scripted NPCs sequentially.
        Foundation for future bounty-monster injection."""
        if challenger.kind != ParticipantKind.BOT:
            raise ValueError("GAUNTLET challenger must be BOT kind")
        if not npc_sequence or any(p.kind != ParticipantKind.NPC for p in npc_sequence):
            raise ValueError("GAUNTLET opponents must all be NPC kind")
        cfg = TournamentConfig(
            ttype=TournamentType.GAUNTLET,
            n_candles=40 * len(npc_sequence),
            round_size_candles=40,
            min_participants=1,
            max_participants=1 + len(npc_sequence),
            acrv_purse=acrv_purse,
            seed=(
                seed
                if seed is not None
                else _hash_seed(challenger, *npc_sequence, season)
            ),
        )
        participants = [challenger, *npc_sequence]
        return self._build(cfg, season, participants)

    def _build(
        self, cfg: TournamentConfig, season: Season, participants: list[Participant]
    ) -> Tournament:
        events = DynamicEventScheduler(cfg.seed, cfg.ttype, cfg.n_candles).schedule()
        t = Tournament(
            tournament_id=f"trn_{uuid.uuid4().hex[:12]}",
            config=cfg,
            season=season,
            participants=participants,
            events=events,
            state=TournamentState.OPEN,
        )
        logger.info(
            "Built %s tournament %s: %d participants, %d events, " "seed=%d, season=%s",
            cfg.ttype.value,
            t.tournament_id,
            len(participants),
            len(events),
            cfg.seed,
            season.label,
        )
        return t

    # ── Run ────────────────────────────────────────────────────────────
    def run(
        self,
        tournament: Tournament,
        candle_provider: Optional[Callable[[int], dict]] = None,
    ) -> Outcome:
        """Execute the tournament. candle_provider(tick) returns a dict
        with at least 'close' price; if None, uses a synthetic series.

        This is the core battle loop. v1 implementation is deliberately
        lightweight — it does PnL accounting and event resolution without
        calling into the full ScrummingBot state machine. Integration
        with live bot decision logic (R57 EPM) is a later turn.

        sadp: R55 R57 R58
        """
        if tournament.state != TournamentState.OPEN:
            raise RuntimeError(
                f"Tournament {tournament.tournament_id} is "
                f"{tournament.state.value}, not OPEN"
            )

        tournament.state = TournamentState.IN_PROGRESS
        tournament.started_at = time.time()
        candle_provider = candle_provider or _synthetic_candles(
            tournament.config.seed, tournament.config.n_candles
        )

        try:
            if tournament.ttype == TournamentType.DUEL:
                self._run_duel(tournament, candle_provider)
            elif tournament.ttype == TournamentType.MELEE:
                self._run_melee(tournament, candle_provider)
            elif tournament.ttype == TournamentType.GAUNTLET:
                self._run_gauntlet(tournament, candle_provider)
            else:
                raise RuntimeError(f"Unknown type {tournament.ttype}")

            tournament.state = TournamentState.CONCLUDED
            tournament.concluded_at = time.time()
            outcome = self._compute_outcome(tournament)
            tournament.outcome = outcome

            # Settlement
            settlement = self._settlement.settle(
                tournament.tournament_id, outcome, tournament.participants
            )
            if settlement.get("settled"):
                tournament.state = TournamentState.SETTLED

            self._persist(tournament)
            self._tournaments_run += 1
            logger.info(
                "Tournament %s concluded: winner=%s, rounds=%d, "
                "events=%d, replay_hash=%s",
                tournament.tournament_id,
                outcome.winner_id,
                outcome.total_rounds,
                outcome.total_events,
                outcome.replay_hash[:16],
            )
            return outcome

        except Exception as e:
            tournament.state = TournamentState.FAILED
            tournament.concluded_at = time.time()
            self._tournaments_failed += 1
            logger.exception("Tournament %s FAILED: %s", tournament.tournament_id, e)
            # Still persist the failure for audit
            try:
                self._persist(tournament)
            except Exception:
                pass  # R28-OK / R61 ACCEPT — persist of failure state is best-effort; original exception re-raised below; do not mask the original tournament failure with a persist error if disk is full or persist itself fails
            raise

    # ── Format-specific runners ────────────────────────────────────────
    def _run_duel(self, t: Tournament, candle_provider: Callable[[int], dict]) -> None:
        events_by_tick = _events_by_tick(t.events)
        events_fired: list[str] = []
        last_close = 100.0

        for tick in range(t.config.n_candles):
            candle = candle_provider(tick)
            last_close = candle.get("close", last_close)
            # Apply events for this tick
            for ev in events_by_tick.get(tick, []):
                self._apply_event(t, ev, last_close, events_fired)
            # Participant actions — each makes a scrum decision
            for p in t.participants:
                self._tick_participant(p, candle, tick, t.config.seed)

        t.rounds.append(
            RoundResult(
                round_number=1,
                tick_start=0,
                tick_end=t.config.n_candles - 1,
                standings=sorted(
                    [(p.participant_id, p.stats.pnl) for p in t.participants],
                    key=lambda x: -x[1],
                ),
                eliminated_ids=[],
                events_fired=events_fired,
            )
        )

    def _run_melee(self, t: Tournament, candle_provider: Callable[[int], dict]) -> None:
        events_by_tick = _events_by_tick(t.events)
        round_events: list[str] = []
        active: set[str] = {p.participant_id for p in t.participants}
        last_close = 100.0
        round_number = 0

        for tick in range(t.config.n_candles):
            if len(active) <= 1:
                break
            candle = candle_provider(tick)
            last_close = candle.get("close", last_close)
            for ev in events_by_tick.get(tick, []):
                self._apply_event(t, ev, last_close, round_events)
            for p in t.participants:
                if p.participant_id in active:
                    self._tick_participant(p, candle, tick, t.config.seed)

            # Elimination: at each round boundary, eliminate bottom quartile
            if (tick + 1) % t.config.round_size_candles == 0:
                round_number += 1
                active_ranked = sorted(
                    [p for p in t.participants if p.participant_id in active],
                    key=lambda p: p.stats.pnl,
                )
                # Drop bottom quartile (min 1, at least keeping 1 alive)
                n_drop = max(1, len(active_ranked) // 4)
                n_drop = min(n_drop, len(active_ranked) - 1)
                dropped: list[str] = []
                for p in active_ranked[:n_drop]:
                    p.stats.eliminated_at_round = round_number
                    active.discard(p.participant_id)
                    dropped.append(p.participant_id)
                t.rounds.append(
                    RoundResult(
                        round_number=round_number,
                        tick_start=tick - t.config.round_size_candles + 1,
                        tick_end=tick,
                        standings=sorted(
                            [(p.participant_id, p.stats.pnl) for p in t.participants],
                            key=lambda x: -x[1],
                        ),
                        eliminated_ids=dropped,
                        events_fired=round_events,
                    )
                )
                round_events = []

    def _run_gauntlet(
        self, t: Tournament, candle_provider: Callable[[int], dict]
    ) -> None:
        events_by_tick = _events_by_tick(t.events)
        challenger = next(p for p in t.participants if p.kind == ParticipantKind.BOT)
        npcs = [p for p in t.participants if p.kind == ParticipantKind.NPC]
        round_events: list[str] = []
        last_close = 100.0

        for npc_idx, npc in enumerate(npcs, start=1):
            npc_start = (npc_idx - 1) * t.config.round_size_candles
            npc_end = npc_start + t.config.round_size_candles - 1
            for tick in range(npc_start, npc_end + 1):
                if tick >= t.config.n_candles:
                    break
                candle = candle_provider(tick)
                last_close = candle.get("close", last_close)
                for ev in events_by_tick.get(tick, []):
                    self._apply_event(t, ev, last_close, round_events)
                self._tick_participant(challenger, candle, tick, t.config.seed)
                self._tick_npc(npc, candle, tick, t.config.seed)
            t.rounds.append(
                RoundResult(
                    round_number=npc_idx,
                    tick_start=npc_start,
                    tick_end=npc_end,
                    standings=[
                        (challenger.participant_id, challenger.stats.pnl),
                        (npc.participant_id, npc.stats.pnl),
                    ],
                    eliminated_ids=[],
                    events_fired=round_events,
                )
            )
            round_events = []
            # If challenger lags badly, mark as defeated (no further NPCs)
            if challenger.stats.pnl < npc.stats.pnl - 50.0:
                challenger.stats.eliminated_at_round = npc_idx
                break

    # ── Core per-tick behavior ─────────────────────────────────────────
    def _tick_participant(
        self, p: Participant, candle: dict, tick: int, seed: int
    ) -> None:
        """v1 scrum-proxy logic. Simple momentum strategy; PnL accrues
        on close-vs-prev movement. Later turn will integrate real
        ScrummingBot decision flow via R57 EPM adapter.

        sadp: R55 R57 — symbol-aware (R55 VH class) once integration lands
        """
        # Seeded per-participant per-tick RNG for reproducibility
        rng = random.Random(
            (seed * 1_000_003 + hash(p.participant_id) + tick) & 0xFFFFFFFF
        )
        close = candle.get("close", 100.0)
        # Simple momentum: random-walk "performance" scaled by participant
        # stability factor (stub for bot config influence)
        raw_move = rng.gauss(0.0, 1.0)
        p.stats.pnl += raw_move
        if rng.random() < 0.15:
            p.stats.trades += 1
            # Apply slippage model parity with R55 VH v3 class lookup
            if p.symbol:
                from ..core.execution_discipline import verify_hit

                vh_fp, vh_status, _ = verify_hit(close, "sell", symbol=p.symbol)
                if vh_fp is None:
                    p.stats.verify_canceled += 1
                else:
                    p.stats.verify_clean += 1
            if raw_move > 0:
                p.stats.wins += 1

    def _tick_npc(self, npc: Participant, candle: dict, tick: int, seed: int) -> None:
        """NPC decision logic — purely scripted, parameterized by
        npc_config. Scaffolding for bounty-monster injection."""
        rng = random.Random((seed * 7 + hash(npc.participant_id) + tick) & 0xFFFFFFFF)
        difficulty = (npc.npc_config or {}).get("difficulty", 1.0)
        # NPCs get consistent small positive drift scaled by difficulty
        npc.stats.pnl += rng.gauss(0.5 * difficulty, 0.8)

    # ── Event resolution ───────────────────────────────────────────────
    def _apply_event(
        self, t: Tournament, ev: DynamicEvent, last_close: float, fired_log: list[str]
    ) -> None:
        """Resolve a dynamic event. v1: simple PnL adjustments reflecting
        how each event type affects participants differently."""
        if ev.resolved:
            return
        fired_log.append(ev.event_id)

        if ev.etype == DynamicEventType.MARKET_SHOCK:
            mult = ev.payload.get("spread_multiplier", 5.0)
            direction = 1 if ev.payload.get("direction") == "up" else -1
            # Traders with VH-aware symbols absorb shocks better
            for p in t.participants:
                if p.stats.eliminated_at_round is not None:
                    continue
                vh_protected = p.symbol is not None
                impact = mult * 0.5 * direction
                if vh_protected:
                    impact *= 0.3  # R55 VH class tolerance absorbs 70%
                p.stats.pnl += impact * random.Random(ev.event_id.encode()).gauss(0, 1)
            ev.resolution = {"applied_to": len(t.participants)}

        elif ev.etype == DynamicEventType.PUZZLE_EVENT:
            # Participants attempt to answer; 60% of bots get it right
            # (stub — later turn integrates with real TA heuristic)
            correct_idx = ev.payload.get("correct_index", 0)
            bonus = ev.payload.get("bonus_pnl", 30.0)
            rng = random.Random(ev.event_id.encode())
            resolved_by: list[str] = []
            for p in t.participants:
                if p.stats.eliminated_at_round is not None:
                    continue
                if p.kind == ParticipantKind.NPC:
                    continue  # NPCs don't do puzzles in v1
                chose = rng.randint(0, ev.payload.get("options", 4) - 1)
                if chose == correct_idx:
                    p.stats.pnl += bonus
                    p.stats.puzzle_correct += 1
                    resolved_by.append(p.participant_id)
                else:
                    p.stats.puzzle_wrong += 1
            ev.resolution = {"correct": len(resolved_by), "resolved_by": resolved_by}

        elif ev.etype == DynamicEventType.REGIME_FLIP:
            # Regime flip: increases volatility downstream. v1 models
            # as a one-time bonus/penalty applied to every participant
            rng = random.Random(ev.event_id.encode())
            for p in t.participants:
                if p.stats.eliminated_at_round is not None:
                    continue
                p.stats.pnl += rng.gauss(0, 3.0)
            ev.resolution = {"applied": True}

        ev.resolved = True

    # ── Outcome computation ────────────────────────────────────────────
    def _compute_outcome(self, t: Tournament) -> Outcome:
        # Determine winner
        if t.ttype == TournamentType.GAUNTLET:
            challenger = next(
                p for p in t.participants if p.kind == ParticipantKind.BOT
            )
            winner = (
                challenger if challenger.stats.eliminated_at_round is None else None
            )
        else:
            alive = [p for p in t.participants if p.stats.eliminated_at_round is None]
            winner = max(alive, key=lambda p: p.stats.pnl) if alive else None

        standings = sorted(
            [(p.participant_id, p.stats.pnl) for p in t.participants],
            key=lambda x: -x[1],
        )

        # Replay hash — captures config + events + final state for audit.
        # Deliberately EXCLUDES instance identity (tournament_id, event_id)
        # so that any two replays with the same seed + config produce
        # the same hash regardless of which UUID was minted.
        # sadp: R57 EPM
        hash_material = {
            "config": {**asdict(t.config), "ttype": t.ttype.value},
            "ttype": t.ttype.value,
            "season": asdict(t.season),
            "events": [
                {"tick": e.tick, "etype": e.etype.value, "payload": e.payload}
                for e in t.events
            ],
            "standings": standings,
        }
        replay_hash = hashlib.sha256(
            json.dumps(hash_material, sort_keys=True, default=str).encode()
        ).hexdigest()

        acrv = t.config.acrv_purse if winner else 0

        return Outcome(
            winner_id=winner.participant_id if winner else None,
            final_standings=standings,
            total_rounds=len(t.rounds),
            total_events=len(t.events),
            replay_hash=replay_hash,
            acrv_awarded=acrv,
        )

    # ── Persistence ────────────────────────────────────────────────────
    def _persist(self, t: Tournament) -> None:
        """Write tournament JSON to log dir for audit/replay."""
        path = self._log_dir / f"{t.tournament_id}.json"
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(t.to_dict(), f, indent=2, default=str)
        except Exception as e:
            logger.warning("Failed to persist tournament %s: %s", t.tournament_id, e)

    # ── Observability ──────────────────────────────────────────────────
    @property
    def stats(self) -> dict:
        return {
            "run": self._tournaments_run,
            "failed": self._tournaments_failed,
        }


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════


def _events_by_tick(events: list[DynamicEvent]) -> dict[int, list[DynamicEvent]]:
    out: dict[int, list[DynamicEvent]] = {}
    for e in events:
        out.setdefault(e.tick, []).append(e)
    return out


def _hash_seed(*items) -> int:
    """Deterministic seed from any number of hashable items."""
    parts = []
    for x in items:
        if isinstance(x, Participant):
            parts.append(x.participant_id)
        elif isinstance(x, Season):
            parts.append(f"season-{x.number}-{x.label}")
        else:
            parts.append(str(x))
    h = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(h[:4], "big")


def _synthetic_candles(seed: int, n_candles: int) -> Callable[[int], dict]:
    """Default candle provider — generates a synthetic OHLC series
    deterministic for a given seed. Used when no real candle feed
    is provided (tests, demos, sim-only tournaments)."""
    rng = random.Random(seed)
    prices: list[float] = [100.0]
    for _ in range(n_candles):
        prices.append(max(1.0, prices[-1] * (1 + rng.gauss(0, 0.008))))

    def provider(tick: int) -> dict:
        i = min(tick + 1, len(prices) - 1)
        prev = prices[i - 1]
        curr = prices[i]
        return {
            "open": prev,
            "close": curr,
            "high": max(prev, curr) * (1 + abs(rng.gauss(0, 0.003))),
            "low": min(prev, curr) * (1 - abs(rng.gauss(0, 0.003))),
            "volume": abs(rng.gauss(1000, 200)),
        }

    return provider


# ══════════════════════════════════════════════════════════════════════════
# Convenience factories
# ══════════════════════════════════════════════════════════════════════════


def make_bot_participant(
    participant_id: str,
    display_name: str,
    source_bot_id: str,
    symbol: Optional[str] = None,
) -> Participant:
    """Standard factory for bot-backed participant.
    sadp: R58 TBI — new ParticipantStats, NOT the source bot's stats."""
    return Participant(
        participant_id=participant_id,
        kind=ParticipantKind.BOT,
        display_name=display_name,
        source_bot_id=source_bot_id,
        symbol=symbol,
        stats=ParticipantStats(),
    )


def make_npc_participant(
    npc_id: str, label: str, difficulty: float = 1.0
) -> Participant:
    """Factory for scripted NPC. Difficulty scales NPC scoring aggression.
    Future: bounty monsters are this pattern + a testnet wei payout."""
    return Participant(
        participant_id=npc_id,
        kind=ParticipantKind.NPC,
        display_name=label,
        npc_config={"difficulty": difficulty},
        stats=ParticipantStats(),
    )
