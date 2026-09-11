"""A world's tier, the depth it reaches, and the Quintessence a slaying imports.

``WorldTierRegistry`` holds one ``WorldTier`` a world, ``raise_tier`` moves one
step deeper, and ``import_on_slaying`` moves Quintessence out of the pleroma
through ``QuintessenceLedger.embed_from_pleroma`` while minting none.
``lowest_depth_of`` reads the depths ``monster_table`` declares, so
``MAX_WORLD_TIER`` adds no second scale. ``loot_band`` cuts ``TIER_NAMES`` from
its low end, ``loot_band_at_tier`` raises ``FigureAbsentError``, and
``NO_CALLER_NOTE`` names what would reach any of this.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from .loot_drop import LOOT_TIERS, TIER_NAMES
from .monster_table import (
    DESCENDING,
    RANKS_PER_SIDE,
    monster_tier_at,
    tier_embedded_quintessence,
)
from .quintessence_ledger import QuintessenceLedger, amount_text

logger = logging.getLogger("acervator.world_tier")

#: The tier a world opens on, reaching one depth below the participant's plane.
FIRST_WORLD_TIER = 1

#: The deepest tier a world reaches, ``monster_table``'s own count of ranks a side.
MAX_WORLD_TIER = RANKS_PER_SIDE

#: A figure no source sets. Its owed note says what would set it.
FIGURE_ABSENT = None

#: What would reach ``WorldTierRegistry``, and what exists of it today.
NO_CALLER_NOTE = (
    "a cataclysm reads raise_tier and a combat result reads import_on_slaying. "
    "No module names a cataclysm, an alignment or a combat, so nothing calls it"
)

#: Loot tiers that leave the low end of the chart a world tier. Nothing sets it.
TIERS_OFF_CHART_PER_WORLD_TIER: int | None = FIGURE_ABSENT

#: What a loot band waits on, and what naming the figure buys.
TIERS_OFF_CHART_OWED_NOTE = (
    "how many loot tiers leave the chart for each world tier above "
    "FIRST_WORLD_TIER. No statement names one. Once named, loot_band_at_tier "
    "answers from loot_band, and the same band answers materials.QUALITY_GRADES "
    "because both read loot_drop.TIER_NAMES"
)

#: Imported Quintessence that raises a world one tier. Nothing sets it.
TIER_RAISE_THRESHOLD_QUINTESSENCE: Decimal | None = FIGURE_ABSENT

#: What bounds a tier raise, and what stays unbounded while no figure sets it.
TIER_RAISE_THRESHOLD_OWED_NOTE = (
    "the imported Quintessence that raises a world one tier. No statement names "
    "one, so nothing bounds how often raise_tier may be called and a world can "
    "be farmed to MAX_WORLD_TIER by repeated slaying"
)

#: Why a cut band is no drop table, which ``band_weight_total`` measures.
BAND_REWEIGHT_OWED_NOTE = (
    "the weights a cut band carries. loot_drop.require_whole_table refuses any "
    "set not totalling loot_drop.WEIGHT_TOTAL_PCT, so loot_drop.tier_bounds "
    "cuts no roll span from a band until a reweighting rule is named"
)


class WorldTierError(RuntimeError):
    """Base for every refusal this module raises."""


class UnknownWorldError(WorldTierError):
    """Raised for a world id ``WorldTierRegistry`` holds no ``WorldTier`` for."""


class WorldTierBoundError(WorldTierError):
    """Raised for a tier outside ``FIRST_WORLD_TIER`` to ``MAX_WORLD_TIER``."""


class FigureAbsentError(WorldTierError):
    """Raised when a figure this module declares ``FIGURE_ABSENT`` is read."""


def _as_world_id(value: object) -> str:
    """Return ``value`` as a non-empty world id string; every other value raises."""
    if type(value) is not str or not value.strip():
        refusal = f"world_id must be a non-empty string, got {value!r}"
        raise UnknownWorldError(refusal)
    return value


def require_tier(value: object) -> int:
    """Return ``value`` as a tier of ``FIRST_WORLD_TIER`` to ``MAX_WORLD_TIER``."""
    if type(value) is not int:
        refusal = f"a world tier must be int, not {type(value).__name__}"
        raise WorldTierBoundError(refusal)
    if not FIRST_WORLD_TIER <= value <= MAX_WORLD_TIER:
        refusal = (
            f"a world tier runs {FIRST_WORLD_TIER} to {MAX_WORLD_TIER}, the "
            f"{RANKS_PER_SIDE} {DESCENDING} ranks monster_table declares, "
            f"got {value}"
        )
        raise WorldTierBoundError(refusal)
    return value


def lowest_depth_of(tier: object) -> int:
    """Return the ``monster_table`` depth a world at ``tier`` reaches, never zero."""
    return -require_tier(tier)


def world_tier_depths(tier: object) -> tuple[int, ...]:
    """Return every depth a world at ``tier`` reaches, the shallowest first."""
    return tuple(range(-1, lowest_depth_of(tier) - 1, -1))


def deepest_tier_name(tier: object) -> str:
    """Return the ``monster_table`` tier name at ``lowest_depth_of`` of ``tier``."""
    return monster_tier_at(lowest_depth_of(tier)).name


def slaying_import_amount(tier: object, depth: object) -> Decimal:
    """Return the Quintessence a creature at ``depth`` imports into a world at ``tier``.

    ``tier_embedded_quintessence`` raises ``LevelAbsentError`` while no
    ``monster_table`` tier declares a level, so no depth answers an amount today.
    """
    reached = world_tier_depths(tier)
    if type(depth) is not int or depth not in reached:
        refusal = (
            f"a world at tier {tier!r} reaches {list(reached)}, "
            f"and no creature of it sits at depth {depth!r}"
        )
        raise WorldTierBoundError(refusal)
    return tier_embedded_quintessence(depth)


def tier_raise_threshold() -> Decimal:
    """Return the imported Quintessence that raises a world one tier."""
    if TIER_RAISE_THRESHOLD_QUINTESSENCE is None:
        refusal = f"no threshold raises a world tier: {TIER_RAISE_THRESHOLD_OWED_NOTE}"
        raise FigureAbsentError(refusal)
    return TIER_RAISE_THRESHOLD_QUINTESSENCE


def loot_band(tiers_off_chart: object) -> tuple[str, ...]:
    """Return ``TIER_NAMES`` with ``tiers_off_chart`` of them cut off its low end.

    ``TIER_NAMES`` runs lowest grade first, so the cut takes the commonest items.
    """
    if type(tiers_off_chart) is not int or tiers_off_chart < 0:
        refusal = (
            f"tiers_off_chart must be a whole count of the {len(TIER_NAMES)} "
            f"loot tiers, got {tiers_off_chart!r}"
        )
        raise WorldTierBoundError(refusal)
    if tiers_off_chart >= len(TIER_NAMES):
        refusal = (
            f"cutting {tiers_off_chart} of {len(TIER_NAMES)} loot tiers leaves "
            f"no tier on the chart; {', '.join(TIER_NAMES)} are declared"
        )
        raise WorldTierBoundError(refusal)
    return TIER_NAMES[tiers_off_chart:]


def band_weight_total(tiers_off_chart: object) -> Decimal:
    """Add the ``weight_pct`` of every tier ``loot_band`` leaves on the chart."""
    band = loot_band(tiers_off_chart)
    total = Decimal(0)
    for tier in LOOT_TIERS:
        if tier.name in band:
            total += tier.weight_pct
    return total


def loot_band_at_tier(tier: object) -> tuple[str, ...]:
    """Return the loot band a world at ``tier`` rolls on."""
    steps = require_tier(tier) - FIRST_WORLD_TIER
    if TIERS_OFF_CHART_PER_WORLD_TIER is None:
        refusal = f"no band follows from a world tier: {TIERS_OFF_CHART_OWED_NOTE}"
        raise FigureAbsentError(refusal)
    return loot_band(TIERS_OFF_CHART_PER_WORLD_TIER * steps)


@dataclass(frozen=True)
class WorldTier:
    """One world's tier and the Quintessence imported into it since it opened.

    ``tier`` is a count and ``lowest_depth`` is the ``monster_table`` depth it
    names, so a higher tier reaches a deeper dimension.
    """

    world_id: str
    tier: int
    imported_quintessence: Decimal

    @property
    def lowest_depth(self) -> int:
        """Return the deepest ``monster_table`` depth this world reaches."""
        return lowest_depth_of(self.tier)

    @property
    def is_deepest(self) -> bool:
        """True while this world sits at ``MAX_WORLD_TIER`` and rises no further."""
        return self.tier == MAX_WORLD_TIER

    def to_dict(self) -> dict:
        """Return this world as a JSON-safe dict, its amount a plain string."""
        return {
            "world_id": self.world_id,
            "tier": self.tier,
            "lowest_depth": self.lowest_depth,
            "deepest_tier_name": deepest_tier_name(self.tier),
            "depths_reached": list(world_tier_depths(self.tier)),
            "imported_quintessence": amount_text(self.imported_quintessence),
            "is_deepest": self.is_deepest,
        }


class WorldTierRegistry:
    """Every ``WorldTier`` in memory, reached by ``world_id``.

    ``import_on_slaying`` commits to the ledger first and credits the world with
    what the ledger moved, so a refused move leaves the registry untouched.
    """

    def __init__(self) -> None:
        """Open a registry holding no world."""
        self._worlds: dict[str, WorldTier] = {}

    @property
    def world_count(self) -> int:
        """Return how many worlds the registry holds."""
        return len(self._worlds)

    def world_ids(self) -> list[str]:
        """Return every ``world_id`` the registry holds, in sorted order."""
        return sorted(self._worlds)

    def world(self, world_id: object) -> WorldTier:
        """Return the ``WorldTier`` under ``world_id``, raising for every other id."""
        wanted = _as_world_id(world_id)
        found = self._worlds.get(wanted)
        if found is None:
            refusal = (
                f"{wanted!r} is no world in this registry; it holds "
                f"{self.world_count} of them"
            )
            raise UnknownWorldError(refusal)
        return found

    def open_world(self, world_id: object) -> WorldTier:
        """Open ``world_id`` at ``FIRST_WORLD_TIER`` with nothing imported."""
        wanted = _as_world_id(world_id)
        standing = self._worlds.get(wanted)
        if standing is not None:
            refusal = f"world {wanted!r} is already open at tier {standing.tier}"
            raise UnknownWorldError(refusal)
        opened = WorldTier(
            world_id=wanted,
            tier=FIRST_WORLD_TIER,
            imported_quintessence=Decimal(0),
        )
        self._worlds[wanted] = opened
        logger.info(
            "world %s opens at tier %d, reaching depth %d",
            wanted,
            opened.tier,
            opened.lowest_depth,
        )
        return opened

    def raise_tier(self, world_id: object) -> WorldTier:
        """Move ``world_id`` one tier deeper, refusing a world at ``MAX_WORLD_TIER``."""
        standing = self.world(world_id)
        if standing.is_deepest:
            refusal = (
                f"world {standing.world_id!r} sits at tier {standing.tier} of "
                f"{MAX_WORLD_TIER} and reaches depth {standing.lowest_depth} "
                f"already"
            )
            raise WorldTierBoundError(refusal)
        raised = WorldTier(
            world_id=standing.world_id,
            tier=require_tier(standing.tier + 1),
            imported_quintessence=standing.imported_quintessence,
        )
        self._worlds[standing.world_id] = raised
        logger.info(
            "world %s rises to tier %d, reaching depth %d",
            raised.world_id,
            raised.tier,
            raised.lowest_depth,
        )
        return raised

    def import_on_slaying(
        self,
        ledger: QuintessenceLedger,
        world_id: object,
        amount: object,
    ) -> Decimal:
        """Move ``amount`` from the pleroma into the embedded bucket for ``world_id``.

        The ledger mints nothing, and a pleroma holding less than ``amount``
        refuses the whole move and credits the world nothing.
        """
        standing = self.world(world_id)
        imported = ledger.embed_from_pleroma(amount)
        if imported == 0:
            return Decimal(0)
        self._worlds[standing.world_id] = WorldTier(
            world_id=standing.world_id,
            tier=standing.tier,
            imported_quintessence=standing.imported_quintessence + imported,
        )
        logger.info(
            "world %s imports %s Quintessence out of the pleroma",
            standing.world_id,
            amount_text(imported),
        )
        return imported

    def imported_total(self) -> Decimal:
        """Add the ``imported_quintessence`` of every world the registry holds."""
        total = Decimal(0)
        for world in self._worlds.values():
            total += world.imported_quintessence
        return total

    def rows(self) -> list[dict]:
        """Return one row a world, ordered by ``world_id``."""
        return [self._worlds[key].to_dict() for key in self.world_ids()]


def require_world_tier_scale() -> None:
    """Refuse a tier ``monster_table`` declares no matching descending rank for."""
    for tier in range(FIRST_WORLD_TIER, MAX_WORLD_TIER + 1):
        depth = lowest_depth_of(tier)
        reached = monster_tier_at(depth)
        if reached.direction != DESCENDING or reached.rank != tier:
            refusal = (
                f"world tier {tier} reads depth {depth}, which monster_table "
                f"answers as {reached.direction} rank {reached.rank}"
            )
            raise WorldTierBoundError(refusal)


require_world_tier_scale()
