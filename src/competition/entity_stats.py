"""Every PoA entity's stats, each measured in Quintessence, declared in one table.

``STATS`` is that table and ``STAT_NAMES``, ``stat_named``, ``stats_for_principle``
and ``StatBlock`` all read it, so its size is never assumed. ``stat_at_level``
advances one stat through the ``TREE_SPHERES`` bands of ``LEVELS_PER_SPHERE``
levels at the rate ``quintessence_per_level`` reads off the band, and
``quintessence_requirement`` adds a block for a Vessel or a monster and several
blocks for an item's components. ``potential_at`` reads what fraction of a
requirement a balance reaches.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, localcontext

from .quintessence_ledger import QUINTESSENCE_SUPPLY_CAP, amount_text
from .rpg_classes import ARC_LEVELS, FIRST_LEVEL, MERCURY, PRINCIPLES, SALT, SULPHUR
from .world_grid import TREE_SPHERES

logger = logging.getLogger("acervator.entity_stats")

#: The ``StatDef.effect`` of a stat no built figure reads.
NO_EFFECT_NAMED = "no_effect_named"

#: The band ``FIRST_LEVEL`` falls in, the first of ``TREE_SPHERES``.
FIRST_SPHERE = 1

#: Levels one band carries, ``ARC_LEVELS`` over ``TREE_SPHERES``.
LEVELS_PER_SPHERE = ARC_LEVELS // TREE_SPHERES

#: The two bounds ``potential_at`` clamps its fraction between.
NO_POTENTIAL = Decimal(0)
FULL_POTENTIAL = Decimal(1)

#: Decimal digits ``potential_at`` computes its fraction to.
POTENTIAL_PRECISION = 28

_NUMBER_TYPES = (int, float, Decimal)


class EntityStatsError(RuntimeError):
    """Base for every refusal this module raises."""


class StatValueError(EntityStatsError):
    """Raised for a stat or balance outside zero to ``QUINTESSENCE_SUPPLY_CAP``."""


class StatLevelError(EntityStatsError):
    """Raised for a level outside ``FIRST_LEVEL`` to ``ARC_LEVELS``."""


class SphereBandError(EntityStatsError):
    """Raised for a band outside ``FIRST_SPHERE`` to ``TREE_SPHERES``."""


class UnknownPrincipleError(EntityStatsError):
    """Raised by ``stats_for_principle`` for a name ``PRINCIPLES`` does not carry."""


class UnknownStatError(EntityStatsError):
    """Raised for a stat name ``STAT_NAMES`` does not carry."""


@dataclass(frozen=True)
class StatDef:
    """One stat in ``STATS``: its name, its principle, and what it sets.

    ``effect`` is ``NO_EFFECT_NAMED`` while no built figure reads the stat.
    """

    name: str
    principle: str
    effect: str

    def __post_init__(self) -> None:
        """Refuse a blank ``name`` and a ``principle`` outside ``PRINCIPLES``."""
        if not self.name.strip():
            raise UnknownStatError(f"a stat needs a name, got {self.name!r}")
        if self.principle not in PRINCIPLES:
            raise UnknownPrincipleError(
                f"{self.name} sits in {self.principle!r}, "
                f"and the three principles are {', '.join(PRINCIPLES)}"
            )


#: The stat table. A name, a count or a principle changes here and nowhere else.
STATS: tuple[StatDef, ...] = (
    StatDef("strength", SALT, "max weight"),
    StatDef("dexterity", SULPHUR, NO_EFFECT_NAMED),
    StatDef("constitution", SALT, "turn point penalty while carrying"),
    StatDef("intelligence", MERCURY, NO_EFFECT_NAMED),
    StatDef("wisdom", MERCURY, NO_EFFECT_NAMED),
)

#: Every name in ``STATS``, in the order it declares them.
STAT_NAMES: tuple[str, ...] = tuple(entry.name for entry in STATS)

if len(set(STAT_NAMES)) != len(STAT_NAMES):
    raise UnknownStatError(f"STATS declares a name twice: {STAT_NAMES}")


def _as_quintessence(value: object, name: str) -> Decimal:
    """Return ``value`` as a Decimal in Quintessence; bool, str and NaN raise."""
    if type(value) is bool or type(value) not in _NUMBER_TYPES:
        raise StatValueError(
            f"{name} must be int, float or Decimal, not {type(value).__name__}"
        )
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if not amount.is_finite():
        raise StatValueError(f"{name} must be finite, got {value!r}")
    if amount < 0:
        raise StatValueError(f"{name} must not be negative, got {value!r}")
    if amount > QUINTESSENCE_SUPPLY_CAP:
        raise StatValueError(
            f"{name} of {amount_text(amount)} is above the "
            f"{amount_text(QUINTESSENCE_SUPPLY_CAP)} Quintessence that can exist"
        )
    return amount


def _as_level(value: object) -> int:
    """Return ``value`` as an int from ``FIRST_LEVEL`` to ``ARC_LEVELS``."""
    if type(value) is not int:
        raise StatLevelError(f"level must be int, not {type(value).__name__}")
    if not FIRST_LEVEL <= value <= ARC_LEVELS:
        raise StatLevelError(
            f"level must be {FIRST_LEVEL} to {ARC_LEVELS}, got {value!r}"
        )
    return value


def _as_sphere(value: object) -> int:
    """Return ``value`` as an int from ``FIRST_SPHERE`` to ``TREE_SPHERES``."""
    if type(value) is not int:
        raise SphereBandError(f"sphere must be int, not {type(value).__name__}")
    if not FIRST_SPHERE <= value <= TREE_SPHERES:
        raise SphereBandError(
            f"sphere must be {FIRST_SPHERE} to {TREE_SPHERES}, got {value!r}"
        )
    return value


def stat_named(name: str) -> StatDef | None:
    """The entry in ``STATS`` whose ``name`` matches, or None for any other."""
    for entry in STATS:
        if entry.name == name:
            return entry
    return None


def stats_for_principle(principle: str) -> tuple[str, ...]:
    """The names ``STATS`` puts in ``principle``, in ``STAT_NAMES`` order."""
    if principle not in PRINCIPLES:
        raise UnknownPrincipleError(
            f"{principle!r} is not a PoA principle; "
            f"the three are {', '.join(PRINCIPLES)}"
        )
    return tuple(entry.name for entry in STATS if entry.principle == principle)


def sphere_of_level(level: int) -> int:
    """The band ``level`` falls in, from ``FIRST_SPHERE`` to ``TREE_SPHERES``."""
    reached = _as_level(level)
    band = (reached - FIRST_LEVEL) // LEVELS_PER_SPHERE + FIRST_SPHERE
    return min(band, TREE_SPHERES)


def quintessence_per_level(sphere: int) -> Decimal:
    """The Quintessence a level adds inside ``sphere``, its own place on the Tree."""
    return Decimal(_as_sphere(sphere))


def first_level_of_sphere(sphere: int) -> int:
    """The lowest level ``sphere`` carries, ``LEVELS_PER_SPHERE`` above the band under it."""
    band = _as_sphere(sphere)
    return FIRST_LEVEL + (band - FIRST_SPHERE) * LEVELS_PER_SPHERE


def stat_at_level(level: int) -> Decimal:
    """The Quintessence one stat measures at ``level``.

    Every band up to ``sphere_of_level`` is counted at the rate
    ``quintessence_per_level`` sets for it.
    """
    reached = _as_level(level)
    measured = Decimal(0)
    for band in range(FIRST_SPHERE, sphere_of_level(reached) + 1):
        opens = first_level_of_sphere(band)
        closes = min(reached, opens + LEVELS_PER_SPHERE - 1)
        measured += quintessence_per_level(band) * (closes - opens + 1)
    return measured


@dataclass(frozen=True)
class StatBlock:
    """One entity's stats, one amount a member of ``STATS``.

    ``amounts`` runs in ``STAT_NAMES`` order and ``stat_of`` reads one by name.
    """

    amounts: tuple[Decimal, ...]

    def __post_init__(self) -> None:
        """Refuse a length other than ``STAT_NAMES`` and coerce every amount."""
        if len(self.amounts) != len(STAT_NAMES):
            raise StatValueError(
                f"a stat block holds {len(STAT_NAMES)} amounts for "
                f"{', '.join(STAT_NAMES)}, got {len(self.amounts)}"
            )
        object.__setattr__(
            self,
            "amounts",
            tuple(
                _as_quintessence(amount, name)
                for name, amount in zip(STAT_NAMES, self.amounts, strict=True)
            ),
        )

    def stat_of(self, name: str) -> Decimal:
        """The amount this block holds in ``name``, refusing a name outside ``STATS``."""
        if stat_named(name) is None:
            raise UnknownStatError(
                f"{name!r} is not a PoA stat; "
                f"the stat table carries {', '.join(STAT_NAMES)}"
            )
        return self.amounts[STAT_NAMES.index(name)]

    def principle_total(self, principle: str) -> Decimal:
        """Add the amounts ``stats_for_principle`` names for ``principle``."""
        total = Decimal(0)
        for name in stats_for_principle(principle):
            total += self.stat_of(name)
        return total

    @property
    def requirement(self) -> Decimal:
        """This block's own Quintessence, from ``quintessence_requirement``."""
        return quintessence_requirement((self,))

    def to_dict(self) -> dict:
        """This block as a JSON-safe dict, every amount a plain string."""
        return {
            name: amount_text(amount)
            for name, amount in zip(STAT_NAMES, self.amounts, strict=True)
        }


@dataclass(frozen=True)
class Potential:
    """What one balance reaches against one requirement.

    ``fraction`` sits between ``NO_POTENTIAL`` and ``FULL_POTENTIAL``, and
    ``is_full`` compares two Quintessence amounts.
    """

    requirement: Decimal
    balance: Decimal
    fraction: Decimal
    shortfall: Decimal
    is_full: bool

    def to_dict(self) -> dict:
        """This reading as a JSON-safe dict, every amount a plain string."""
        return {
            "requirement": amount_text(self.requirement),
            "balance": amount_text(self.balance),
            "fraction": amount_text(self.fraction),
            "shortfall": amount_text(self.shortfall),
            "is_full": self.is_full,
        }


def stat_block(amounts: Mapping[str, object]) -> StatBlock:
    """A ``StatBlock`` from a mapping carrying every name in ``STAT_NAMES``."""
    missing = [name for name in STAT_NAMES if name not in amounts]
    unknown = [name for name in amounts if stat_named(name) is None]
    if missing or unknown:
        raise UnknownStatError(
            f"a stat block needs {', '.join(STAT_NAMES)}; "
            f"missing {missing}, unknown {unknown}"
        )
    return StatBlock(
        tuple(_as_quintessence(amounts[name], name) for name in STAT_NAMES)
    )


def stat_block_at_level(level: int) -> StatBlock:
    """A ``StatBlock`` holding ``stat_at_level`` in every member of ``STATS``."""
    measured = stat_at_level(level)
    return StatBlock(tuple(measured for _ in STATS))


def quintessence_requirement(blocks: Iterable[StatBlock]) -> Decimal:
    """Add every amount of every block in ``blocks``, exactly.

    ``blocks`` holds one block a Vessel or a monster, and one block a component.
    """
    total = Decimal(0)
    for block in blocks:
        for amount in block.amounts:
            total += amount
    return total


def potential_at(balance: object, blocks: Iterable[StatBlock]) -> Potential:
    """Read what fraction of the ``blocks`` requirement ``balance`` reaches.

    A balance under that requirement answers under ``FULL_POTENTIAL``, and no
    call here refuses it.
    """
    held = _as_quintessence(balance, "balance")
    required = quintessence_requirement(blocks)
    if required == 0:
        return Potential(required, held, FULL_POTENTIAL, Decimal(0), True)
    covered = held >= required
    owed = Decimal(0) if covered else required - held
    with localcontext() as ctx:
        ctx.prec = POTENTIAL_PRECISION
        fraction = min(FULL_POTENTIAL, max(NO_POTENTIAL, held / required))
    logger.info(
        "a balance of %s against a requirement of %s reaches %s, shortfall %s",
        amount_text(held),
        amount_text(required),
        amount_text(fraction),
        amount_text(owed),
    )
    return Potential(required, held, fraction, owed, covered)


def stat_rows() -> list[dict]:
    """One row an entry in ``STATS``: its name, its principle and its effect."""
    return [
        {
            "name": entry.name,
            "principle": entry.principle,
            "effect": entry.effect,
        }
        for entry in STATS
    ]


def sphere_rows() -> list[dict]:
    """One row a band: its number, the level it opens at, its rate and its close."""
    return [
        {
            "sphere": band,
            "opens_at_level": first_level_of_sphere(band),
            "quintessence_per_level": amount_text(quintessence_per_level(band)),
            "stat_at_band_close": amount_text(
                stat_at_level(
                    min(first_level_of_sphere(band) + LEVELS_PER_SPHERE - 1, ARC_LEVELS)
                )
            ),
        }
        for band in range(FIRST_SPHERE, TREE_SPHERES + 1)
    ]
