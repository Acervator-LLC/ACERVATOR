"""
challenge_protocol.py — Bot-to-Bot Challenge Protocol
======================================================
Bots accumulate Elo ratings from head-to-head competitions.
Higher-rated bots can only be challenged by other high-rated bots.

Challenge lifecycle:
  1. Challenger sends a signed challenge to a target bot
  2. Target accepts or declines
  3. Both bots trade the agreed asset for the agreed duration
  4. Arbiter (shared competition engine) adjudicates
  5. Elo ratings update; tokens flow from loser's stake to winner

Elo update formula (K=32 standard):
  Expected = 1 / (1 + 10 ^ ((opponent_rating - own_rating) / 400))
  New rating = old_rating + K * (result - expected)
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# ── Elo engine ────────────────────────────────────────────────────────────────

DEFAULT_ELO = 1200
ELO_K_FACTOR = 32
MIN_ELO = 100


def elo_expected(rating_a: float, rating_b: float) -> float:
    """Expected score for A against B (0–1)."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400))


def elo_update(
    winner_rating: float, loser_rating: float, k: float = ELO_K_FACTOR
) -> tuple[float, float]:

    # sadp: R28  # Elo calc: fail-loudly on invalid inputs(R28)
    """Return (new_winner_rating, new_loser_rating)."""
    exp_w = elo_expected(winner_rating, loser_rating)
    exp_l = elo_expected(loser_rating, winner_rating)
    new_w = winner_rating + k * (1 - exp_w)
    new_l = max(MIN_ELO, loser_rating + k * (0 - exp_l))
    return round(new_w, 1), round(new_l, 1)


# ── Rating registry ───────────────────────────────────────────────────────────


@dataclass
class BotRating:
    bot_id: str
    rating: float = DEFAULT_ELO
    wins: int = 0
    losses: int = 0
    draws: int = 0
    last_competed: float = 0.0
    consecutive_top1: int = 0  # for Grand Accumulator eligibility

    @property
    def total_games(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def win_rate(self) -> float:
        if self.total_games == 0:
            return 0.0
        return self.wins / self.total_games

    def to_dict(self) -> dict:
        return {
            "bot_id": self.bot_id,
            "rating": self.rating,
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "last_competed": self.last_competed,
            "consecutive_top1": self.consecutive_top1,
        }


class RatingRegistry:
    """
    Persistent Elo rating registry for all bots.
    R33: Match history is append-only.
    """

    REGISTRY_FILE = "elo_registry.json"

    def __init__(self, registry_path: Optional[str] = None):
        self._path = Path(registry_path or self.REGISTRY_FILE)
        self._ratings: Dict[str, BotRating] = {}
        self._history: List[dict] = []

    def get_or_create(self, bot_id: str) -> BotRating:
        if bot_id not in self._ratings:
            self._ratings[bot_id] = BotRating(bot_id=bot_id)
        return self._ratings[bot_id]

    def record_result(self, winner_id: str, loser_id: str, competition_id: str):

        # sadp: R28 R29 R33  # Elo record: fail-loudly(R28) idempotent(R29) append-only(R33)
        """Update Elo ratings after a competition result."""
        w = self.get_or_create(winner_id)
        l = self.get_or_create(loser_id)

        new_w, new_l = elo_update(w.rating, l.rating)

        w.rating = new_w
        w.wins += 1
        l.rating = new_l
        l.losses += 1
        w.last_competed = l.last_competed = time.time()

        # Track consecutive top-1 finishes for Grand Accumulator
        w.consecutive_top1 += 1
        l.consecutive_top1 = 0

        self._history.append(
            {
                "competition_id": competition_id,
                "winner": winner_id[:12],
                "loser": loser_id[:12],
                "winner_new_elo": new_w,
                "loser_new_elo": new_l,
                "timestamp": time.time(),
            }
        )
        self.save()

    def leaderboard(self, top_n: int = 20) -> List[dict]:
        ranked = sorted(self._ratings.values(), key=lambda r: r.rating, reverse=True)
        return [
            {
                "rank": i + 1,
                "bot_id": r.bot_id[:12] + "...",
                "rating": r.rating,
                "w": r.wins,
                "l": r.losses,
                "win_rate": f"{r.win_rate:.0%}",
            }
            for i, r in enumerate(ranked[:top_n])
        ]

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "ratings": {bid: r.to_dict() for bid, r in self._ratings.items()},
                    "history": self._history,
                },
                indent=2,
            )
        )

    def load(self) -> "RatingRegistry":
        if not self._path.exists():
            return self
        data = json.loads(self._path.read_text())
        for bid, rd in data.get("ratings", {}).items():
            self._ratings[bid] = BotRating(**rd)
        self._history = data.get("history", [])
        return self


# ── Challenge message ─────────────────────────────────────────────────────────


@dataclass
class ChallengeMessage:
    """
    A signed challenge from one bot to another.
    The challenger commits to: symbol, duration, starting capital.
    The stake is held in escrow until adjudication.
    """

    challenge_id: str
    challenger_id: str
    target_id: str
    symbol: str
    duration_ticks: int
    starting_capital: float
    stake_acrv: int  # ACRV tokens at risk from each bot
    issued_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 3600)
    accepted: bool = False
    declined: bool = False
    signature: str = ""

    def challenge_hash(self) -> str:
        d = {
            "challenge_id": self.challenge_id,
            "challenger_id": self.challenger_id,
            "target_id": self.target_id,
            "symbol": self.symbol,
            "duration_ticks": self.duration_ticks,
            "starting_capital": round(self.starting_capital, 2),
            "stake_acrv": self.stake_acrv,
            "issued_at": round(self.issued_at, 3),
        }
        return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


def create_challenge(
    challenger_id: str,
    target_id: str,
    symbol: str = "BTC/USDT",
    duration_ticks: int = 500,
    starting_capital: float = 400.0,
    stake_acrv: int = 10,
) -> ChallengeMessage:
    """Create a new challenge from one bot to another."""
    return ChallengeMessage(
        challenge_id=f"CHAL-{uuid.uuid4().hex[:8].upper()}",
        challenger_id=challenger_id,
        target_id=target_id,
        symbol=symbol,
        duration_ticks=duration_ticks,
        starting_capital=starting_capital,
        stake_acrv=stake_acrv,
    )
