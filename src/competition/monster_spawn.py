"""Monster identity derived from the committed seed, the layer and the locator.

``derive_monster`` reads ``world_grid.discovery_leaf`` for a locator, draws a tier
out of the weighting its caller supplies and draws one design from
``monster_table.designs_at_depth``. ``TIER_WEIGHTING_OWED`` names the figure no
source sets and ``require_weighting`` refuses a weighting missing a declared depth.
``DerivedMonster.embedded_quintessence`` raises ``LevelAbsentError`` while every
tier's ``level`` is absent, so generation reaches no power figure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .monster_table import (
    FIGURE_ABSENT,
    LEVEL_OWED_NOTE,
    MONSTER_TIER_TABLE,
    TEXT_ABSENT,
    MonsterDesign,
    MonsterTier,
    design_named,
    designs_at_depth,
    monster_tier_at,
    tier_embedded_quintessence,
)
from .world_grid import (
    LEAF_DRAW_DIGITS,
    GridPosition,
    WorldGridError,
    discovery_leaf,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from decimal import Decimal

logger = logging.getLogger("acervator.monster_spawn")

#: Hex digits one draw reads, the width ``committed_quintessence`` reads an amount at.
DRAW_DIGITS = LEAF_DRAW_DIGITS

#: Hex digits ``discovery_leaf`` returns, measured off the function itself.
LEAF_DIGITS = len(discovery_leaf("", ""))

#: The window ``committed_quintessence`` reads, which the draws below leave alone.
AMOUNT_WINDOW = 0

#: The leaf window the tier draw reads.
TIER_WINDOW = 1

#: The leaf window the design draw reads.
DESIGN_WINDOW = 2

#: Every window generation reads, past the one holding the amount.
WINDOWS_READ: tuple[int, ...] = (TIER_WINDOW, DESIGN_WINDOW)

#: Colon-separated fields a locator carries, as ``GridPosition.locator`` writes it.
LOCATOR_FIELDS = 4

#: The figure no source sets, and what a caller passes once it is set.
TIER_WEIGHTING_OWED = (
    "how often a tier is encountered. The art brief publishes on_screen_low and "
    "on_screen_high a tier, which is how many of that tier stand in one square "
    "at once, and names no rule reading either end of that span as a draw share. "
    "Four readings of the same span order the twelve tiers four different ways, "
    "so derive_monster takes the weighting from its caller and holds none"
)

#: What a tier naming no design owes, and the count the brief leaves unnamed.
DESIGN_ABSENT_NOTE = (
    "this tier names no design. The decan rank at depth -3 counts 36 entities "
    "the art brief leaves unnamed, and the six ascending tiers hold no entity"
)


class MonsterSpawnError(RuntimeError):
    """Base for every refusal this module raises."""


class TierWeightingError(MonsterSpawnError):
    """Raised by ``require_weighting`` for a weighting no caller has completed."""


class LocatorError(MonsterSpawnError):
    """Raised by ``require_locator`` for text ``GridPosition.locator`` never writes."""


class LeafError(MonsterSpawnError):
    """Raised by ``leaf_window`` for a leaf outside ``LEAF_DIGITS`` hex digits."""


# -- What the art brief publishes, and what a weighting would read ------------


def declared_depths() -> tuple[int, ...]:
    """Return every ``depth`` in ``MONSTER_TIER_TABLE``, deepest first."""
    return tuple(tier.depth for tier in MONSTER_TIER_TABLE)


def on_screen_span(depth: int) -> tuple[int | None, int | None]:
    """Return the tier at ``depth``'s ``on_screen_low`` and ``on_screen_high``."""
    tier = monster_tier_at(depth)
    return tier.on_screen_low, tier.on_screen_high


def tiers_without_an_on_screen_count() -> tuple[int, ...]:
    """Return every depth whose ``on_screen_low`` or ``on_screen_high`` is absent."""
    return tuple(
        tier.depth
        for tier in MONSTER_TIER_TABLE
        if tier.on_screen_low is None or tier.on_screen_high is None
    )


def tiers_without_a_design() -> tuple[int, ...]:
    """Return every depth ``designs_at_depth`` answers with no design."""
    return tuple(
        tier.depth for tier in MONSTER_TIER_TABLE if not designs_at_depth(tier.depth)
    )


def on_screen_rows() -> list[dict]:
    """Return one row a tier, carrying the span a tier weighting would read."""
    rows = []
    for tier in MONSTER_TIER_TABLE:
        low, high = on_screen_span(tier.depth)
        rows.append(
            {
                "depth": tier.depth,
                "tier_name": tier.name,
                "on_screen_low": low,
                "on_screen_high": high,
                "designs": len(designs_at_depth(tier.depth)),
                "weighting_note": TIER_WEIGHTING_OWED,
            },
        )
    return rows


# -- The weighting, which the caller holds -----------------------------------


def weighting_span(weights: Mapping[int, int]) -> int:
    """Add every share in ``weights``, the whole numbers a tier roll is drawn from."""
    return sum(weights[depth] for depth in weights)


def require_weighting(weights: Mapping[int, int]) -> None:
    """Refuse a weighting missing a declared depth or naming a depth no tier holds.

    Every share is a whole number at or above zero and one share at least is
    positive.
    """
    declared = declared_depths()
    missing = [depth for depth in declared if depth not in weights]
    if missing:
        refusal = (
            f"a tier weighting names every depth in {list(declared)} and carries "
            f"no share for {missing}: {TIER_WEIGHTING_OWED}"
        )
        raise TierWeightingError(refusal)
    unknown = sorted(depth for depth in weights if depth not in declared)
    if unknown:
        refusal = f"{unknown} name no tier; {list(declared)} are declared"
        raise TierWeightingError(refusal)
    for depth in declared:
        share = weights[depth]
        if isinstance(share, bool) or not isinstance(share, int) or share < 0:
            refusal = (
                f"depth {depth} carries a share of {share!r}; a share is a whole "
                f"number at or above zero"
            )
            raise TierWeightingError(refusal)
    if weighting_span(weights) <= 0:
        refusal = (
            f"every one of the {len(declared)} declared tiers carries a share of "
            f"zero, so no tier can be drawn"
        )
        raise TierWeightingError(refusal)


def tier_bounds(weights: Mapping[int, int]) -> tuple[tuple[int, int, int], ...]:
    """Cut ``weights`` into half-open roll spans, deepest depth first.

    ``require_weighting`` runs first and a depth with a share of zero takes no span.
    """
    require_weighting(weights)
    bounds: list[tuple[int, int, int]] = []
    lower = 0
    for depth in declared_depths():
        upper = lower + weights[depth]
        if upper > lower:
            bounds.append((lower, upper, depth))
        lower = upper
    return tuple(bounds)


def depth_for_roll(roll: int, weights: Mapping[int, int]) -> int:
    """Return the depth whose span in ``tier_bounds`` holds ``roll``."""
    value = int(roll)
    for lower, upper, depth in tier_bounds(weights):
        if lower <= value < upper:
            return depth
    refusal = (
        f"a roll of {value} sits outside the draw span of 0 to "
        f"{weighting_span(weights) - 1}"
    )
    raise TierWeightingError(refusal)


# -- The leaf, and the two draws it answers ----------------------------------


def leaf_window(leaf: str, window: int) -> int:
    """Return the number ``window`` reads out of ``leaf``, ``DRAW_DIGITS`` wide."""
    windows = LEAF_DIGITS // DRAW_DIGITS
    if not 0 <= window < windows:
        refusal = (
            f"window {window} sits outside the {windows} windows of "
            f"{DRAW_DIGITS} hex digits a leaf holds"
        )
        raise LeafError(refusal)
    if len(leaf) != LEAF_DIGITS:
        refusal = f"a leaf runs {LEAF_DIGITS} hex digits; {leaf!r} runs {len(leaf)}"
        raise LeafError(refusal)
    start = window * DRAW_DIGITS
    try:
        return int(leaf[start : start + DRAW_DIGITS], 16)
    except ValueError as exc:
        refusal = f"{leaf!r} carries a digit outside base sixteen: {exc}"
        raise LeafError(refusal) from exc


def require_distinct_windows() -> None:
    """Refuse a window reading the same hex digits twice or past ``LEAF_DIGITS``."""
    used = (AMOUNT_WINDOW, *WINDOWS_READ)
    if len(set(used)) != len(used):
        refusal = f"windows {list(used)} read the same hex digits twice"
        raise LeafError(refusal)
    widest = max(used)
    if DRAW_DIGITS * (widest + 1) > LEAF_DIGITS:
        refusal = (
            f"window {widest} of {DRAW_DIGITS} hex digits runs past the "
            f"{LEAF_DIGITS} digits a leaf holds"
        )
        raise LeafError(refusal)


def tier_for_leaf(leaf: str, weights: Mapping[int, int]) -> tuple[int, int]:
    """Return the roll ``TIER_WINDOW`` draws from ``leaf`` and the depth holding it."""
    require_weighting(weights)
    roll = leaf_window(leaf, TIER_WINDOW) % weighting_span(weights)
    return roll, depth_for_roll(roll, weights)


def design_for_leaf(leaf: str, depth: int) -> tuple[int | None, str]:
    """Return the roll ``DESIGN_WINDOW`` draws from ``leaf`` and the design it names.

    A depth ``designs_at_depth`` answers empty draws ``FIGURE_ABSENT`` and
    ``TEXT_ABSENT``.
    """
    designs = designs_at_depth(depth)
    if not designs:
        return FIGURE_ABSENT, TEXT_ABSENT
    roll = leaf_window(leaf, DESIGN_WINDOW) % len(designs)
    return roll, designs[roll].name


# -- The locator, whose one format ``GridPosition`` writes --------------------


def require_locator(locator: str) -> tuple[int, GridPosition]:
    """Return the layer and ``GridPosition`` that write ``locator`` back."""
    fields = locator.split(":")
    if len(fields) != LOCATOR_FIELDS:
        refusal = (
            f"a locator carries {LOCATOR_FIELDS} colon-separated fields; "
            f"{locator!r} carries {len(fields)}"
        )
        raise LocatorError(refusal)
    try:
        layer, square, step_x, step_y = (int(field) for field in fields)
    except ValueError as exc:
        refusal = f"{locator!r} carries a field that is not a whole number: {exc}"
        raise LocatorError(refusal) from exc
    try:
        position = GridPosition(square, step_x, step_y)
    except WorldGridError as exc:
        refusal = f"{locator!r} names no position on the grid: {exc}"
        raise LocatorError(refusal) from exc
    if position.locator(layer) != locator:
        refusal = (
            f"{locator!r} is not the text GridPosition.locator writes for layer "
            f"{layer} at {position}"
        )
        raise LocatorError(refusal)
    return layer, position


# -- The derived monster -----------------------------------------------------


@dataclass(frozen=True)
class DerivedMonster:
    """One locator's encounter, the tier it sits at and the design it drew.

    ``design_name`` is ``TEXT_ABSENT`` at a depth ``designs_at_depth`` answers
    empty, and no field carries a level, a stat or an amount of Quintessence.
    """

    locator: str
    layer: int
    leaf: str
    depth: int
    design_name: str
    tier_roll: int
    design_roll: int | None

    @property
    def tier(self) -> MonsterTier:
        """Return the row ``MONSTER_TIER_TABLE`` holds at this monster's ``depth``."""
        return monster_tier_at(self.depth)

    @property
    def design(self) -> MonsterDesign | None:
        """Return the design ``design_name`` names, None at a tier naming none."""
        if self.design_name == TEXT_ABSENT:
            return None
        return design_named(self.design_name)

    def embedded_quintessence(self) -> Decimal:
        """Read the Quintessence this monster embeds, which its tier's ``level`` sets.

        ``monster_table.tier_embedded_quintessence`` raises while that level is absent.
        """
        return tier_embedded_quintessence(self.depth)

    def to_dict(self) -> dict:
        """Return this monster as a JSON-safe dict, every absence its own literal."""
        tier = self.tier
        absent = self.design_name == TEXT_ABSENT
        return {
            "locator": self.locator,
            "layer": self.layer,
            "leaf": self.leaf,
            "depth": self.depth,
            "direction": tier.direction,
            "rank": tier.rank,
            "tier_name": tier.name,
            "design_name": self.design_name,
            "designs_at_tier": len(designs_at_depth(self.depth)),
            "tier_roll": self.tier_roll,
            "design_roll": self.design_roll,
            "level": tier.level,
            "level_note": LEVEL_OWED_NOTE,
            "design_note": DESIGN_ABSENT_NOTE if absent else TEXT_ABSENT,
        }


def derive_monster(
    seed: str,
    locator: str,
    weights: Mapping[int, int],
) -> DerivedMonster:
    """Derive the monster at ``locator`` under ``seed``, its tier from ``weights``.

    ``world_grid.seed_commitment`` hides ``seed`` and a caller holding no seed
    derives no leaf.
    """
    layer, _ = require_locator(locator)
    leaf = discovery_leaf(seed, locator)
    tier_roll, depth = tier_for_leaf(leaf, weights)
    design_roll, design_name = design_for_leaf(leaf, depth)
    monster = DerivedMonster(
        locator=locator,
        layer=layer,
        leaf=leaf,
        depth=depth,
        design_name=design_name,
        tier_roll=tier_roll,
        design_roll=design_roll,
    )
    logger.debug(
        "%s derives depth %d, %s, design %r",
        locator,
        depth,
        monster.tier.name,
        design_name,
    )
    return monster


def derive_monster_at(
    seed: str,
    layer: int,
    position: GridPosition,
    weights: Mapping[int, int],
) -> DerivedMonster:
    """Derive the monster where ``position`` sits on ``layer``, under ``seed``."""
    return derive_monster(seed, position.locator(layer), weights)


def require_monster_spawn() -> None:
    """Drive ``require_distinct_windows`` and log what generation derives."""
    require_distinct_windows()
    named = len(MONSTER_TIER_TABLE) - len(tiers_without_a_design())
    logger.info(
        "monster generation draws a tier from leaf window %d and a design from "
        "window %d, %d hex digits each. %d of %d tiers name a design and depths "
        "%s name none; depths %s publish no on-screen count, so no tier "
        "weighting follows from the brief. No tier names a level, so no level, "
        "stat or Quintessence amount is derived",
        TIER_WINDOW,
        DESIGN_WINDOW,
        DRAW_DIGITS,
        named,
        len(MONSTER_TIER_TABLE),
        list(tiers_without_a_design()),
        list(tiers_without_an_on_screen_count()),
    )


require_monster_spawn()
