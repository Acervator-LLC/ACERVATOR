"""PoA tournaments built and run by ``TournamentEngine``.

``build_duel``, ``build_melee`` and ``build_gauntlet`` return a ``Tournament``
from a ``TournamentConfig``, and ``run`` plays it over a candle provider to an
``Outcome``. ``DynamicEventScheduler`` places MARKET_SHOCK, PUZZLE_EVENT and
REGIME_FLIP events from ``TournamentConfig.seed``. ``LocalACRVAdapter`` settles
``Outcome.acrv_awarded`` and ``_persist`` writes each ``Tournament`` to JSON.
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


class TournamentType(Enum):
    DUEL = "duel"
    MELEE = "melee"
    GAUNTLET = "gauntlet"


class TournamentState(Enum):
    PENDING = "pending"  # created, not open
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CONCLUDED = "concluded"  # outcome computed, settlement not attempted
    SETTLED = "settled"  # SettlementAdapter.settle reported settled
    FAILED = "failed"  # error during play; no settlement


class DynamicEventType(Enum):
    MARKET_SHOCK = "market_shock"
    PUZZLE_EVENT = "puzzle_event"
    REGIME_FLIP = "regime_flip"


@dataclass
class Season:
    """Round index and label carried on ``Tournament.season``."""

    number: int
    label: str = "neutral"


class ParticipantKind(Enum):
    BOT = "bot"  # Participant.source_bot_id names a bot; no bot object is held
    NPC = "npc"  # scored by _tick_npc from Participant.npc_config


@dataclass
class ParticipantStats:
    """Per-``Participant`` tallies mutated by ``_tick_participant``.

    ``eliminated_at_round`` is set by ``_run_melee`` and ``_run_gauntlet``.
    """

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
    """A competitor entered in a ``Tournament``.

    ``source_bot_id`` and ``symbol`` are set for ``ParticipantKind.BOT``;
    ``npc_config`` is set for ``ParticipantKind.NPC``.
    """

    participant_id: str
    kind: ParticipantKind
    display_name: str
    stats: ParticipantStats = field(default_factory=ParticipantStats)
    symbol: Optional[str] = None
    npc_config: Optional[dict] = None
    source_bot_id: Optional[str] = None


@dataclass
class DynamicEvent:
    event_id: str
    etype: DynamicEventType
    tick: int  # candle index chosen by DynamicEventScheduler.schedule
    payload: dict
    resolved: bool = False
    resolution: Optional[dict] = None


class DynamicEventScheduler:
    """Places ``DynamicEvent`` objects on ticks from a seeded ``random.Random``.

    ``schedule`` returns the same list for the same seed, ``ttype`` and
    ``n_candles``.
    """

    def __init__(self, seed: int, ttype: TournamentType, n_candles: int):
        self._rng = random.Random(seed)
        self._seed = seed  # formatted into every DynamicEvent.event_id
        self._ttype = ttype
        self._n_candles = n_candles

    def schedule(self) -> list[DynamicEvent]:
        """Return the ``DynamicEvent`` list for this tournament, sorted by tick."""
        events: list[DynamicEvent] = []
        if self._ttype == TournamentType.DUEL:
            n_shocks, n_puzzles, n_flips = 3, 0, 0
        elif self._ttype == TournamentType.MELEE:
            n_shocks, n_puzzles, n_flips = 2, 2, 1
        else:  # GAUNTLET
            n_shocks, n_puzzles, n_flips = 2, 1, 0

        # Ticks avoid the first 5 and the last 5 candles.
        lo, hi = 5, max(6, self._n_candles - 5)
        used_ticks = set()

        def pick_tick():
            for _ in range(20):
                t = self._rng.randint(lo, hi)
                if t not in used_ticks:
                    used_ticks.add(t)
                    return t
            for t in range(lo, hi + 1):
                if t not in used_ticks:
                    used_ticks.add(t)
                    return t
            return lo

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

        events.sort(key=lambda e: e.tick)
        return events


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
    testnet_tx_hash: Optional[str] = None  # never assigned in this module


@dataclass
class TournamentConfig:
    ttype: TournamentType
    n_candles: int = 60
    round_size_candles: int = 20  # _run_melee cadence, _run_gauntlet round length
    min_participants: int = 2
    max_participants: int = 8
    acrv_purse: int = 10
    seed: int = 0  # the build_* methods substitute _hash_seed when seed is None
    bounty_testnet_wei: int = 0  # never read in this module


class SettlementAdapter(Protocol):
    """Settlement contract used by ``TournamentEngine``.

    ``settle`` receives the ``Outcome`` and the ``Participant`` list and
    returns a result dict carrying a ``settled`` key.
    """

    def settle(
        self, tournament_id: str, outcome: Outcome, participants: list[Participant]
    ) -> dict: ...


class LocalACRVAdapter:
    """Default ``SettlementAdapter`` for ``TournamentEngine``.

    ``settle`` reports ``Outcome.acrv_awarded`` and calls no method on the
    ledger given to ``__init__``.
    """

    def __init__(self, token_ledger=None):
        self._ledger = token_ledger  # never read by settle

    def settle(
        self, tournament_id: str, outcome: Outcome, participants: list[Participant]
    ) -> dict:
        if outcome.winner_id is None:
            return {"settled": False, "reason": "no winner"}
        if self._ledger is None:
            return {
                "settled": True,
                "adapter": "in_memory",
                "winner_id": outcome.winner_id,
                "acrv": outcome.acrv_awarded,
            }
        return {
            "settled": True,
            "adapter": "token_ledger",
            "winner_id": outcome.winner_id,
            "acrv": outcome.acrv_awarded,
        }


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
        """Return a JSON-ready dict of this ``Tournament`` for ``_persist``."""
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


class TournamentEngine:
    """Builds and runs ``Tournament`` objects.

    ``build_duel``, ``build_melee`` and ``build_gauntlet`` construct one;
    ``run`` plays it, settles it through ``_settlement`` and calls
    ``_persist``.
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
        self._tournaments_run: int = 0
        self._tournaments_failed: int = 0

    def build_duel(
        self,
        a: Participant,
        b: Participant,
        season: Season,
        acrv_purse: int = 10,
        seed: Optional[int] = None,
    ) -> Tournament:
        """Return a DUEL ``Tournament`` over 60 candles for ``a`` and ``b``.

        ``seed`` defaults to ``_hash_seed(a, b, season)``.
        """
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
        """Return a MELEE ``Tournament`` over 120 candles for 4 to 8 participants.

        ``_run_melee`` drops the bottom quartile every
        ``round_size_candles`` candles.
        """
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
        """Return a GAUNTLET ``Tournament`` for ``challenger`` and ``npc_sequence``.

        ``n_candles`` is 40 per entry of ``npc_sequence``.
        """
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

    def run(
        self,
        tournament: Tournament,
        candle_provider: Optional[Callable[[int], dict]] = None,
    ) -> Outcome:
        """Play ``tournament`` and return its ``Outcome``.

        ``candle_provider(tick)`` returns a dict holding ``close``; when it is
        None, ``_synthetic_candles`` supplies one.
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
            try:
                self._persist(tournament)
            except Exception:
                pass
            raise

    def _run_duel(self, t: Tournament, candle_provider: Callable[[int], dict]) -> None:
        events_by_tick = _events_by_tick(t.events)
        events_fired: list[str] = []
        last_close = 100.0

        for tick in range(t.config.n_candles):
            candle = candle_provider(tick)
            last_close = candle.get("close", last_close)
            for ev in events_by_tick.get(tick, []):
                self._apply_event(t, ev, last_close, events_fired)
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

            if (tick + 1) % t.config.round_size_candles == 0:
                round_number += 1
                active_ranked = sorted(
                    [p for p in t.participants if p.participant_id in active],
                    key=lambda p: p.stats.pnl,
                )
                # At least one ranked participant always stays active.
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
            if challenger.stats.pnl < npc.stats.pnl - 50.0:
                challenger.stats.eliminated_at_round = npc_idx
                break

    def _tick_participant(
        self, p: Participant, candle: dict, tick: int, seed: int
    ) -> None:
        """Move ``p.stats.pnl`` by one seeded draw for this tick.

        ``verify_hit`` is called with ``p.symbol`` on the ticks that count a
        trade.
        """
        rng = random.Random(
            (seed * 1_000_003 + hash(p.participant_id) + tick) & 0xFFFFFFFF
        )
        close = candle.get("close", 100.0)
        raw_move = rng.gauss(0.0, 1.0)
        p.stats.pnl += raw_move
        if rng.random() < 0.15:
            p.stats.trades += 1
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
        """Move ``npc.stats.pnl`` by a seeded draw scaled by ``npc_config``.

        The ``difficulty`` key of ``npc_config`` defaults to 1.0.
        """
        rng = random.Random((seed * 7 + hash(npc.participant_id) + tick) & 0xFFFFFFFF)
        difficulty = (npc.npc_config or {}).get("difficulty", 1.0)
        npc.stats.pnl += rng.gauss(0.5 * difficulty, 0.8)

    def _apply_event(
        self, t: Tournament, ev: DynamicEvent, last_close: float, fired_log: list[str]
    ) -> None:
        """Apply ``ev`` to each live ``Participant`` and set ``ev.resolution``.

        ``ev.resolved`` makes a second call a no-op.
        """
        if ev.resolved:
            return
        fired_log.append(ev.event_id)

        if ev.etype == DynamicEventType.MARKET_SHOCK:
            mult = ev.payload.get("spread_multiplier", 5.0)
            direction = 1 if ev.payload.get("direction") == "up" else -1
            for p in t.participants:
                if p.stats.eliminated_at_round is not None:
                    continue
                vh_protected = p.symbol is not None
                impact = mult * 0.5 * direction
                if vh_protected:
                    impact *= 0.3
                p.stats.pnl += impact * random.Random(ev.event_id.encode()).gauss(0, 1)
            ev.resolution = {"applied_to": len(t.participants)}

        elif ev.etype == DynamicEventType.PUZZLE_EVENT:
            correct_idx = ev.payload.get("correct_index", 0)
            bonus = ev.payload.get("bonus_pnl", 30.0)
            rng = random.Random(ev.event_id.encode())
            resolved_by: list[str] = []
            for p in t.participants:
                if p.stats.eliminated_at_round is not None:
                    continue
                if p.kind == ParticipantKind.NPC:
                    continue  # NPCs never answer a PUZZLE_EVENT
                chose = rng.randint(0, ev.payload.get("options", 4) - 1)
                if chose == correct_idx:
                    p.stats.pnl += bonus
                    p.stats.puzzle_correct += 1
                    resolved_by.append(p.participant_id)
                else:
                    p.stats.puzzle_wrong += 1
            ev.resolution = {"correct": len(resolved_by), "resolved_by": resolved_by}

        elif ev.etype == DynamicEventType.REGIME_FLIP:
            rng = random.Random(ev.event_id.encode())
            for p in t.participants:
                if p.stats.eliminated_at_round is not None:
                    continue
                p.stats.pnl += rng.gauss(0, 3.0)
            ev.resolution = {"applied": True}

        ev.resolved = True

    def _compute_outcome(self, t: Tournament) -> Outcome:
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

        # hash_material omits tournament_id and event_id.
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

    def _persist(self, t: Tournament) -> None:
        """Write ``t.to_dict`` as JSON under ``self._log_dir``."""
        path = self._log_dir / f"{t.tournament_id}.json"
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(t.to_dict(), f, indent=2, default=str)
        except Exception as e:
            logger.warning("Failed to persist tournament %s: %s", t.tournament_id, e)

    @property
    def stats(self) -> dict:
        return {
            "run": self._tournaments_run,
            "failed": self._tournaments_failed,
        }


def _events_by_tick(events: list[DynamicEvent]) -> dict[int, list[DynamicEvent]]:
    out: dict[int, list[DynamicEvent]] = {}
    for e in events:
        out.setdefault(e.tick, []).append(e)
    return out


def _hash_seed(*items) -> int:
    """Return a 32-bit seed over ``Participant`` ids and ``Season`` fields."""
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
    """Return a ``provider(tick)`` yielding OHLC dicts from a seeded ``Random``.

    ``run`` uses it when its ``candle_provider`` argument is None.
    """
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


def make_bot_participant(
    participant_id: str,
    display_name: str,
    source_bot_id: str,
    symbol: Optional[str] = None,
) -> Participant:
    """Return a BOT ``Participant`` holding a fresh ``ParticipantStats``."""
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
    """Return an NPC ``Participant`` whose ``npc_config`` carries ``difficulty``."""
    return Participant(
        participant_id=npc_id,
        kind=ParticipantKind.NPC,
        display_name=label,
        npc_config={"difficulty": difficulty},
        stats=ParticipantStats(),
    )
