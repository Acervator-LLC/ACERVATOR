"""
season_schedule.py — ACRV Token Supply Schedule and Rarity Tiers
=================================================================
Hard cap: 10,000,000 ACRV (never changes, enforced in token_ledger.py)
Season rewards decrease each season.  Later tokens are harder to earn.
Rarity tiers are awarded based on performance rank within the field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── Supply constants ──────────────────────────────────────────────────────────

TOTAL_SUPPLY_CAP = 10_000_000  # Hard cap — immutable
GENESIS_SEASON = 1
INITIAL_REWARD = 500_000  # Season 1 reward pool
DECAY_FACTOR = 0.85  # Each season awards 85% of the prior season
MIN_SEASON_REWARD = 100  # Floor — never less than this per season


def season_reward(season: int) -> int:
    """
    Tokens available to award in a given season.
    Decays geometrically from 500,000 with floor at 100.
    """
    if season < 1:
        raise ValueError(f"Season must be ≥ 1, got {season}")
    raw = INITIAL_REWARD * (DECAY_FACTOR ** (season - 1))
    return max(MIN_SEASON_REWARD, int(raw))


def cumulative_supply(through_season: int) -> int:
    """Total tokens that could have been awarded through a given season."""
    total = sum(season_reward(s) for s in range(1, through_season + 1))
    return min(total, TOTAL_SUPPLY_CAP)


# ── Rarity tiers ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RarityTier:
    name: str
    emoji: str
    description: str
    rank_pct_max: float  # top N% of field qualifies (1.0 = all)
    condition: str  # human-readable additional condition
    max_ever: Optional[int]  # None = unlimited within season budget
    base_value: int  # ACRV tokens awarded per win

    def qualifies(self, rank_pct: float, market_regime: str = "ANY") -> bool:
        """
        rank_pct: this bot's percentile rank (0.01 = top 1%)
        market_regime: "BULL" | "BEAR" | "SIDEWAYS" | "ANY"
        """
        if rank_pct > self.rank_pct_max:
            return False
        if self.name == "Bear Slayer" and market_regime != "BEAR":
            return False
        return True


RARITY_TIERS = [
    RarityTier(
        name="Harvest",
        emoji="🌾",
        description="Top 50% of competition field",
        rank_pct_max=0.50,
        condition="Win rate > 50% of competing bots",
        max_ever=None,
        base_value=10,
    ),
    RarityTier(
        name="Gold Fold",
        emoji="🪙",
        description="Top 10% of competition field",
        rank_pct_max=0.10,
        condition="Advantage/capital in top 10% of field",
        max_ever=None,
        base_value=50,
    ),
    RarityTier(
        name="Bear Slayer",
        emoji="🐻",
        description="Top 25% during a verified bear market competition",
        rank_pct_max=0.25,
        condition="Bear regime only — price down ≥ 20% during window",
        max_ever=10_000,
        base_value=100,
    ),
    RarityTier(
        name="Grand Accumulator",
        emoji="⚡",
        description="Top 1% across 3+ consecutive seasons",
        rank_pct_max=0.01,
        condition="Must hold top 1% in three consecutive seasons",
        max_ever=1_000,
        base_value=500,
    ),
    RarityTier(
        name="Ekthelius",
        emoji="∞",
        description="Perfect score across all metrics, any season",
        rank_pct_max=0.001,
        condition="100% win rate + top Sharpe + max capital efficiency",
        max_ever=21,
        base_value=10_000,
    ),
]

TIER_BY_NAME = {t.name: t for t in RARITY_TIERS}


def classify_tier(
    rank_pct: float,
    market_regime: str = "ANY",
    perfect: bool = False,
    consecutive_top1: int = 0,
) -> Optional[RarityTier]:
    """
    Return the highest tier this bot qualifies for given its performance metrics.
    Returns None if below Harvest threshold.
    """
    if perfect and rank_pct <= 0.001:
        return TIER_BY_NAME["Ekthelius"]
    if rank_pct <= 0.01 and consecutive_top1 >= 3:
        return TIER_BY_NAME["Grand Accumulator"]
    if market_regime == "BEAR" and rank_pct <= 0.25:
        return TIER_BY_NAME["Bear Slayer"]
    if rank_pct <= 0.10:
        return TIER_BY_NAME["Gold Fold"]
    if rank_pct <= 0.50:
        return TIER_BY_NAME["Harvest"]
    return None
