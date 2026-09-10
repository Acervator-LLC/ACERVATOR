"""
competition — Proof of Accumulation (PoA) package
===================================================
Cryptographic competition layer for Acervator bots.

Quick start:
    from src.competition import BotIdentity, CompetitionEngine, TokenLedger

    identity = BotIdentity().generate()
    engine   = CompetitionEngine(season=1, symbol="BTC/USDT")
    engine.register_bot(identity, capital_usd=400.0)
"""

from .bot_identity import BotIdentity, TradeRecord
from .merkle_log import MerkleTradeLog, merkle_root, verify_proof
from .season_schedule import (
    season_reward,
    classify_tier,
    RARITY_TIERS,
    TOTAL_SUPPLY_CAP,
    TIER_BY_NAME,
)
from .token_ledger import TokenLedger, AwardRecord
from .quintessence_ledger import (
    QuintessenceLedger,
    QuintessenceLedgerError,
    QuintessenceMovement,
    QuintessenceConservation,
    QuintessenceTransfer,
    QUINTESSENCE_SUPPLY_CAP,
    bleed_fraction,
)
from .competition_engine import (
    CompetitionEngine,
    CompetitionStatus,
    CompetitionResult,
    PerformanceSubmission,
)
from .local_testnet import LocalTestnet
from .challenge_protocol import (
    RatingRegistry,
    create_challenge,
    elo_update,
    ChallengeMessage,
)

__all__ = [
    "BotIdentity",
    "TradeRecord",
    "MerkleTradeLog",
    "merkle_root",
    "verify_proof",
    "season_reward",
    "classify_tier",
    "RARITY_TIERS",
    "TOTAL_SUPPLY_CAP",
    "TIER_BY_NAME",
    "TokenLedger",
    "AwardRecord",
    "QuintessenceLedger",
    "QuintessenceLedgerError",
    "QuintessenceMovement",
    "QuintessenceConservation",
    "QuintessenceTransfer",
    "QUINTESSENCE_SUPPLY_CAP",
    "bleed_fraction",
    "CompetitionEngine",
    "CompetitionStatus",
    "CompetitionResult",
    "PerformanceSubmission",
    "LocalTestnet",
    "RatingRegistry",
    "create_challenge",
    "elo_update",
    "ChallengeMessage",
]
