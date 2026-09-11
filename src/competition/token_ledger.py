"""
token_ledger.py — ACRV Hard-Capped Token Ledger
================================================
Hard cap: 10,000,000 ACRV.  Once minted, tokens cannot be destroyed.
Awards are idempotent: awarding the same competition result twice
produces exactly one entry (R29).

The ledger is append-only (R33): every award event is logged with:
  bot_id, competition_id, tier, amount, timestamp, competition_root

Balances are computed by replaying the append-only log.
There is no "edit balance" operation — only "award tokens".
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .season_schedule import TOTAL_SUPPLY_CAP, season_reward, RarityTier


@dataclass
class AwardRecord:
    """An immutable award entry in the ledger."""

    event_id: str  # SHA-256(bot_id + competition_id + tier) — idempotency key
    bot_id: str
    competition_id: str
    season: int
    tier_name: str
    tier_emoji: str
    amount: int  # ACRV tokens awarded
    timestamp: float
    competition_root: str  # Merkle root proving the competition result
    rank_pct: float  # percentile rank at award time

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "bot_id": self.bot_id,
            "competition_id": self.competition_id,
            "season": self.season,
            "tier_name": self.tier_name,
            "tier_emoji": self.tier_emoji,
            "amount": self.amount,
            "timestamp": self.timestamp,
            "competition_root": self.competition_root,
            "rank_pct": self.rank_pct,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AwardRecord":
        return cls(**d)


class TokenLedger:
    """
    Append-only ACRV token ledger.

    award()  — mint tokens for a competition result (idempotent)
    balance()  — current balance for a bot
    total_minted()  — total ACRV in existence
    remaining_ever()  — tokens still mintable under TOTAL_SUPPLY_CAP
    season_minted()  — ACRV minted so far in one season, the figure award()
    checks against season_reward() for that season
    """

    LEDGER_FILE = "acrv_ledger.json"

    def __init__(self, ledger_path: Optional[str] = None):
        self._path: Path = Path(ledger_path or self.LEDGER_FILE)
        self._events: List[AwardRecord] = []
        self._seen: set = set()  # idempotency keys

    # ── Award ─────────────────────────────────────────────────────────────────

    def award(
        self,
        bot_id: str,
        competition_id: str,
        season: int,
        tier: RarityTier,
        rank_pct: float,
        competition_root: str,
    ) -> Optional[AwardRecord]:

        # sadp: R28 R29 R33  # fail-loudly(R28) idempotent-via-event_id(R29) append-only-log(R33)
        """
        Award tokens for a verified competition result.

        R29 (Idempotency): Each (bot_id, competition_id, tier) triple
        produces exactly one award event regardless of how many times
        this method is called.

        R28 (Fail Loudly): Raises if supply cap would be exceeded.

        Returns the AwardRecord if a new award was created, None if duplicate.
        """
        event_id = self._event_id(bot_id, competition_id, tier.name)
        if event_id in self._seen:
            return None  # Idempotent — already awarded

        # Supply cap check
        if self.total_minted() + tier.base_value > TOTAL_SUPPLY_CAP:
            raise OverflowError(
                f"Supply cap {TOTAL_SUPPLY_CAP:,} ACRV would be exceeded. "
                f"Only {self.remaining_ever()} tokens remain mintable."
            )

        # Season budget check
        season_budget = season_reward(season)
        season_minted = self.season_minted(season)
        if season_minted + tier.base_value > season_budget:
            raise OverflowError(
                f"Season {season} budget of {season_budget:,} ACRV would be "
                f"exceeded. {season_budget - season_minted} tokens remain."
            )

        # Tier supply check
        if tier.max_ever is not None:
            tier_minted = sum(1 for e in self._events if e.tier_name == tier.name)
            if tier_minted >= tier.max_ever:
                raise OverflowError(
                    f"Tier '{tier.name}' has reached its maximum supply "
                    f"of {tier.max_ever}. This tier is permanently exhausted."
                )

        record = AwardRecord(
            event_id=event_id,
            bot_id=bot_id,
            competition_id=competition_id,
            season=season,
            tier_name=tier.name,
            tier_emoji=tier.emoji,
            amount=tier.base_value,
            timestamp=time.time(),
            competition_root=competition_root,
            rank_pct=round(rank_pct, 4),
        )
        self._events.append(record)
        self._seen.add(event_id)
        self.save()
        return record

    # ── Queries ───────────────────────────────────────────────────────────────

    def balance(self, bot_id: str) -> int:

        # sadp: R33  # balance query: read-only ledger(R33)
        """Total ACRV held by a bot (sum of all award amounts)."""
        return sum(e.amount for e in self._events if e.bot_id == bot_id)

    def awards(self, bot_id: str) -> List[AwardRecord]:

        # sadp: R28 R29 R33  # token award — already annotated
        """All award records for a bot, newest first."""
        return sorted(
            [e for e in self._events if e.bot_id == bot_id],
            key=lambda e: e.timestamp,
            reverse=True,
        )

    def total_minted(self) -> int:
        return sum(e.amount for e in self._events)

    def remaining_ever(self) -> int:
        return TOTAL_SUPPLY_CAP - self.total_minted()

    def season_minted(self, season: int) -> int:
        return sum(e.amount for e in self._events if e.season == season)

    def leaderboard(self, top_n: int = 20) -> List[dict]:
        """Top holders by ACRV balance."""
        balances: Dict[str, int] = {}
        for e in self._events:
            balances[e.bot_id] = balances.get(e.bot_id, 0) + e.amount
        ranked = sorted(balances.items(), key=lambda x: x[1], reverse=True)
        return [
            {
                "rank": i + 1,
                "bot_id": bid[:12],
                "balance": bal,
                "tiers": [e.tier_name for e in self.awards(bid)],
            }
            for i, (bid, bal) in enumerate(ranked[:top_n])
        ]

    def supply_summary(self) -> dict:
        tier_counts: Dict[str, int] = {}
        for e in self._events:
            tier_counts[e.tier_name] = tier_counts.get(e.tier_name, 0) + 1
        return {
            "total_cap": TOTAL_SUPPLY_CAP,
            "total_minted": self.total_minted(),
            "remaining": self.remaining_ever(),
            "pct_minted": self.total_minted() / TOTAL_SUPPLY_CAP * 100,
            "tier_counts": tier_counts,
            "total_holders": len({e.bot_id for e in self._events}),
        }

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self):

        # sadp: R28 R33  # ledger save: fail-loudly(R28) append-only(R33)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "total_cap": TOTAL_SUPPLY_CAP,
                    "total_minted": self.total_minted(),
                    "events": [e.to_dict() for e in self._events],
                },
                indent=2,
            )
        )

    def load(self) -> "TokenLedger":
        if not self._path.exists():
            return self
        data = json.loads(self._path.read_text())
        for rd in data.get("events", []):
            record = AwardRecord.from_dict(rd)
            self._events.append(record)
            self._seen.add(record.event_id)
        return self

    @staticmethod
    def _event_id(bot_id: str, competition_id: str, tier_name: str) -> str:
        raw = f"{bot_id}:{competition_id}:{tier_name}"
        return hashlib.sha256(raw.encode()).hexdigest()
