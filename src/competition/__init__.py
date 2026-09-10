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
from .certification_socket import (
    CertificationSocket,
    CertificationRefusedError,
    CertificationReceipt,
    CertifiedFill,
)
from .challenge_protocol import (
    RatingRegistry,
    create_challenge,
    elo_update,
    ChallengeMessage,
)
from .project_age import (
    ProjectAgeLookup,
    ProjectAgeVerdict,
    ProjectAgeError,
    MIN_PROJECT_AGE_MONTHS,
    REFUSAL_REASONS,
)
from .rpg_classes import (
    CharacterClass,
    ClassPick,
    ClassProgress,
    UnknownClassError,
    CLASSES,
    CLASS_NAMES,
    ROLES,
    PRINCIPLES,
    ASSIGNMENTS,
    ARC_LEVELS,
    class_named,
    class_rows,
    pick_class,
)
from .rpg_metrics import (
    METRIC_SOURCES,
    METRIC_SEAMS,
    METRIC_NAMES,
    profile_metrics,
    read_metrics,
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
    "CertificationSocket",
    "CertificationRefusedError",
    "CertificationReceipt",
    "CertifiedFill",
    "RatingRegistry",
    "create_challenge",
    "elo_update",
    "ChallengeMessage",
    "ProjectAgeLookup",
    "ProjectAgeVerdict",
    "ProjectAgeError",
    "MIN_PROJECT_AGE_MONTHS",
    "REFUSAL_REASONS",
    "CharacterClass",
    "ClassPick",
    "ClassProgress",
    "UnknownClassError",
    "CLASSES",
    "CLASS_NAMES",
    "ROLES",
    "PRINCIPLES",
    "ASSIGNMENTS",
    "ARC_LEVELS",
    "class_named",
    "class_rows",
    "pick_class",
    "METRIC_SOURCES",
    "METRIC_SEAMS",
    "METRIC_NAMES",
    "profile_metrics",
    "read_metrics",
]
