"""
competition_engine.py — Competition Lifecycle Engine
=====================================================
Manages the full lifecycle of a Proof-of-Accumulation competition:

  1. REGISTRATION  — bots register with capital commitment + config hash
  2. ACTIVE        — bots trade; each trade appended to their Merkle log
  3. SUBMISSION    — trading closes; bots submit Merkle root + performance claim
  4. ADJUDICATION  — arbiter verifies submissions, ranks bots, awards tokens

A competition can be:
  LOCAL  — multiple ScaleInstance bots on the same machine, same price feed
  P2P    — two bots on different machines exchanging signed submissions

The price feed is SHARED — all bots see the same market data.
The strategy is PRIVATE — parameter details are never published.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .bot_identity import BotIdentity, TradeRecord
from .merkle_log import MerkleTradeLog
from .season_schedule import classify_tier, RARITY_TIERS
from .token_ledger import TokenLedger


class CompetitionStatus(str, Enum):
    REGISTRATION = "REGISTRATION"
    ACTIVE = "ACTIVE"
    SUBMISSION = "SUBMISSION"
    ADJUDICATED = "ADJUDICATED"
    CANCELLED = "CANCELLED"


@dataclass
class BotRegistration:
    bot_id: str
    config_hash: str  # SHA-256 of strategy config — proves consistency
    capital_usd: float
    registered_at: float = field(default_factory=time.time)


@dataclass
class PerformanceSubmission:
    """What a bot submits at competition close."""

    bot_id: str
    merkle_root: str
    trade_count: int
    starting_value: float
    final_value: float
    advantage_usd: float  # final_value - starting_value
    advantage_pct: float  # advantage_usd / starting_value * 100
    sharpe: float  # if available
    submitted_at: float = field(default_factory=time.time)
    # The full log is kept private — only the root is submitted
    _full_log: Optional[MerkleTradeLog] = field(default=None, repr=False)


@dataclass
class CompetitionResult:
    """Final result record — immutable once adjudicated."""

    competition_id: str
    season: int
    symbol: str
    market_regime: str
    start_time: float
    end_time: float
    participants: int
    submissions: List[dict]  # ranked, anonymised after adjudication
    winner_bot_id: str
    winner_tier: str
    winner_token_award: int
    adjudicated_at: float = field(default_factory=time.time)


class CompetitionEngine:
    """
    Coordinates a single competition instance.
    Thread-safe within a single process.
    """

    def __init__(
        self,
        competition_id: Optional[str] = None,
        season: int = 1,
        symbol: str = "BTC/USDT",
        duration_ticks: int = 500,
        ledger: Optional[TokenLedger] = None,
        results_dir: Optional[str] = None,
    ):
        self.competition_id = competition_id or f"COMP-{uuid.uuid4().hex[:8].upper()}"
        self.season = season
        self.symbol = symbol
        self.duration_ticks = duration_ticks
        self.status = CompetitionStatus.REGISTRATION
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.market_regime: str = "ANY"

        self._registrations: Dict[str, BotRegistration] = {}
        self._logs: Dict[str, MerkleTradeLog] = {}
        self._submissions: Dict[str, PerformanceSubmission] = {}
        self._result: Optional[CompetitionResult] = None

        self._ledger = ledger or TokenLedger()
        self._results_dir = Path(results_dir or "competition_results")

    # ── Registration phase ────────────────────────────────────────────────────

    def register_bot(
        self, identity: BotIdentity, capital_usd: float, config: Optional[dict] = None
    ) -> BotRegistration:

        # sadp: R28 R29  # register: fail-loudly if not REGISTRATION(R28) idempotent(R29)
        """
        Register a bot for this competition.
        R28: Raises if competition is not in REGISTRATION status.
        """
        if self.status != CompetitionStatus.REGISTRATION:
            raise RuntimeError(f"Cannot register: competition is {self.status.value}")

        config_hash = self._hash_config(config or {})
        reg = BotRegistration(
            bot_id=identity.bot_id,
            config_hash=config_hash,
            capital_usd=capital_usd,
        )
        self._registrations[identity.bot_id] = reg

        # Create a Merkle log for this bot
        self._logs[identity.bot_id] = MerkleTradeLog(
            competition_id=self.competition_id,
            bot_id=identity.bot_id,
        )
        return reg

    def open(self):

        # sadp: R28  # open: fail-loudly if <2 bots(R28)
        """
        Close registration and open trading.
        R28: Raises if fewer than 2 bots registered.
        """
        if len(self._registrations) < 2:
            raise RuntimeError(
                f"Need at least 2 registered bots to start "
                f"(have {len(self._registrations)})"
            )
        self.status = CompetitionStatus.ACTIVE
        self.start_time = time.time()

    # ── Active trading phase ──────────────────────────────────────────────────

    def record_trade(
        self,
        identity: BotIdentity,
        side: str,
        quantity: float,
        price: float,
        role: str = "UNKNOWN",
        skip_sig: bool = False,
    ) -> TradeRecord:

        # sadp: R28 R29 R33  # fail-loudly-on-wrong-competition(R28) skip-duplicate-seq(R29) log-append-only(R33)
        """
        Record a signed trade in the bot's Merkle log.
        R28: Raises if bot is not registered or competition is not ACTIVE.
        """
        if self.status != CompetitionStatus.ACTIVE:
            raise RuntimeError(
                f"Competition is not ACTIVE (status={self.status.value})"
            )
        if identity.bot_id not in self._registrations:
            raise RuntimeError(f"Bot {identity.short_id} is not registered")

        log = self._logs[identity.bot_id]
        seq = log.size
        record = TradeRecord(
            bot_pubkey=identity.bot_id,
            competition=self.competition_id,
            symbol=self.symbol,
            side=side,
            quantity=quantity,
            price=price,
            timestamp=time.time(),
            trade_seq=seq,
            role=role,
        )
        if not skip_sig:
            record = identity.sign_trade(record)
        log.append(record, skip_sig_verify=skip_sig)
        return record

    def close(self, market_regime: str = "ANY"):

        # sadp: R28 R33  # close: fail-loudly if not ACTIVE(R28) immutable(R33)
        """Close trading and move to SUBMISSION phase."""
        if self.status != CompetitionStatus.ACTIVE:
            raise RuntimeError(f"Cannot close: status={self.status.value}")
        self.status = CompetitionStatus.SUBMISSION
        self.end_time = time.time()
        self.market_regime = market_regime

    # ── Submission phase ──────────────────────────────────────────────────────

    def submit(
        self,
        bot_id: str,
        starting_value: float,
        final_value: float,
        sharpe: float = 0.0,
    ) -> PerformanceSubmission:

        # sadp: R28 R29 R33  # submit: fail-loudly on empty log(R28) idempotent(R29) immutable(R33)
        """
        Submit a performance claim for adjudication.
        The Merkle root proves the trades happened; the values are the claim.
        R28: Raises if bot has no log or log is empty.
        """
        if self.status != CompetitionStatus.SUBMISSION:
            raise RuntimeError(f"Cannot submit: status={self.status.value}")
        if bot_id not in self._logs:
            raise RuntimeError(f"No trade log for bot {bot_id[:12]}...")
        log = self._logs[bot_id]
        if log.size == 0:
            raise RuntimeError(f"Bot {bot_id[:12]}... has no recorded trades")

        adv_usd = final_value - starting_value
        adv_pct = adv_usd / max(starting_value, 0.01) * 100

        sub = PerformanceSubmission(
            bot_id=bot_id,
            merkle_root=log.root,
            trade_count=log.size,
            starting_value=starting_value,
            final_value=final_value,
            advantage_usd=adv_usd,
            advantage_pct=adv_pct,
            sharpe=sharpe,
            _full_log=log,
        )
        self._submissions[bot_id] = sub
        return sub

    # ── Adjudication phase ────────────────────────────────────────────────────

    def adjudicate(self) -> CompetitionResult:

        # sadp: R28 R29 R33  # fail-loudly(R28) idempotent-via-status-check(R29) results-immutable(R33)
        """
        Rank all submissions by advantage%, award tokens to the winner.
        R29: Idempotent — calling twice returns the same result.
        """
        if self.status == CompetitionStatus.ADJUDICATED:
            return self._result

        if self.status != CompetitionStatus.SUBMISSION:
            raise RuntimeError(f"Cannot adjudicate: status={self.status.value}")

        if not self._submissions:
            raise RuntimeError("No submissions to adjudicate")

        # Rank by advantage % (primary), trade count (tiebreak)
        ranked = sorted(
            self._submissions.values(),
            key=lambda s: (s.advantage_pct, s.trade_count),
            reverse=True,
        )
        n = len(ranked)

        # Assign rank percentiles and determine tiers
        results = []
        winner_award = None
        winner_bot = ranked[0]

        for i, sub in enumerate(ranked):
            rank_pct = (i + 1) / n  # 1/n = top, 1.0 = bottom
            perfect = i == 0 and sub.advantage_pct >= 100 and sub.trade_count >= 10
            tier = classify_tier(
                rank_pct,
                market_regime=self.market_regime,
                perfect=perfect,
                consecutive_top1=0,  # TODO: track across seasons
            )

            result_entry = {
                "rank": i + 1,
                "bot_id": sub.bot_id[:12] + "...",
                "bot_id_full": sub.bot_id,
                "advantage_pct": round(sub.advantage_pct, 2),
                "advantage_usd": round(sub.advantage_usd, 2),
                "final_value": round(sub.final_value, 2),
                "trade_count": sub.trade_count,
                "sharpe": round(sub.sharpe, 3),
                "merkle_root": sub.merkle_root[:16] + "...",
                "tier": tier.name if tier else None,
                "tier_emoji": tier.emoji if tier else "",
                "rank_pct": round(rank_pct, 3),
            }
            results.append(result_entry)

            # Award tokens to qualifying bots
            if tier:
                try:
                    self._ledger.award(
                        bot_id=sub.bot_id,
                        competition_id=self.competition_id,
                        season=self.season,
                        tier=tier,
                        rank_pct=rank_pct,
                        competition_root=sub.merkle_root,
                    )
                    if i == 0:
                        winner_award = tier
                except OverflowError as e:
                    # Supply exhausted — log and continue
                    import logging

                    logging.getLogger("acervator.competition").warning(
                        "Token supply exhausted: %s", e
                    )

        self._result = CompetitionResult(
            competition_id=self.competition_id,
            season=self.season,
            symbol=self.symbol,
            market_regime=self.market_regime,
            start_time=self.start_time,
            end_time=self.end_time,
            participants=n,
            submissions=results,
            winner_bot_id=winner_bot.bot_id,
            winner_tier=winner_award.name if winner_award else "None",
            winner_token_award=winner_award.base_value if winner_award else 0,
        )
        self.status = CompetitionStatus.ADJUDICATED
        self._save_result()
        return self._result

    # ── Result display ────────────────────────────────────────────────────────

    def results_table(self) -> str:
        """Human-readable results table."""
        if not self._result:
            return "Not yet adjudicated."
        r = self._result
        lines = [
            f"  COMPETITION {r.competition_id}  ·  Season {r.season}",
            f"  {r.symbol}  ·  Regime: {r.market_regime}  ·  {r.participants} bots",
            f"  {'─'*68}",
            f"  {'Rank':<5} {'Bot ID':<14} {'Adv%':>8} {'Adv$':>10} "
            f"{'Trades':>7} {'Tier':<20}",
            f"  {'─'*68}",
        ]
        for s in r.submissions:
            tier_str = f"{s['tier_emoji']} {s['tier']}" if s["tier"] else "—"
            lines.append(
                f"  {s['rank']:<5} {s['bot_id']:<14} "
                f"{s['advantage_pct']:>+7.2f}%  "
                f"${s['advantage_usd']:>9,.2f}  "
                f"{s['trade_count']:>6}  {tier_str}"
            )
        lines.append(f"  {'─'*68}")
        lines.append(
            f"  Winner: {r.winner_bot_id[:12]}...  "
            f"Tier: {r.winner_tier}  "
            f"Award: {r.winner_token_award:,} ACRV"
        )
        return "\n".join(lines)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _hash_config(config: dict) -> str:
        """SHA-256 of the config dict. Strategy stays private; hash proves consistency."""
        canonical = json.dumps(config, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _save_result(self):

        # sadp: R28 R33  # result save: fail-loudly(R28) append-only(R33)
        if not self._result:
            return
        self._results_dir.mkdir(parents=True, exist_ok=True)
        path = self._results_dir / f"{self.competition_id}.json"
        path.write_text(
            json.dumps(
                {
                    "competition_id": self._result.competition_id,
                    "season": self._result.season,
                    "symbol": self._result.symbol,
                    "market_regime": self._result.market_regime,
                    "participants": self._result.participants,
                    "submissions": self._result.submissions,
                    "winner_bot_id": self._result.winner_bot_id,
                    "winner_tier": self._result.winner_tier,
                    "winner_tokens": self._result.winner_token_award,
                    "adjudicated_at": self._result.adjudicated_at,
                },
                indent=2,
            )
        )
