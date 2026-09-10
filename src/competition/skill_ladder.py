"""The ten-level skill ladder, its cost and effect curves, and the transfer skill.

``cost_of_level`` compounds ``FIRST_LEVEL_COST`` by ``LEVEL_COST_MULTIPLIER`` a
level, ``cost_to_reach`` sums the ladder below one level and ``level_for`` reads a
level back from quality-weighted uses. ``SkillProgress.record_use`` adds one use's
own quality and refuses ``MIN_USE_QUALITY``, while ``effect_at`` rises by
``EFFECT_STEP_PER_LEVEL``. ``TRANSFER_SKILL_NAME`` is the ladder's one member:
``transfer_level`` gates a transfer and ``transfer_bleed`` reads the fraction
``quintessence_ledger.transfer`` charges at that level.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .quintessence_ledger import (
    MAX_TRANSFER_SKILL_LEVEL,
    MIN_TRANSFER_SKILL_LEVEL,
    TRANSFER,
    QuintessenceLedger,
    bleed_fraction,
)

#: The level a skill stands at before one use is recorded.
UNTRAINED_LEVEL = 0

#: The trained levels a skill carries, from the bounds the transfer bleed reads.
FIRST_SKILL_LEVEL = MIN_TRANSFER_SKILL_LEVEL
MAX_SKILL_LEVEL = MAX_TRANSFER_SKILL_LEVEL

#: Quality-weighted uses the first level costs, and the step each level above it.
FIRST_LEVEL_COST = Decimal(1)
LEVEL_COST_MULTIPLIER = Decimal("2.5")

#: The multiplier an untrained skill carries, and the step each level adds to it.
UNTRAINED_EFFECT = Decimal(1)
EFFECT_STEP_PER_LEVEL = Decimal("0.1")

#: The quality one use may carry. A use at MIN_USE_QUALITY advances nothing.
MIN_USE_QUALITY = Decimal(0)
MAX_USE_QUALITY = Decimal(1)

#: The ladder's one member. No second skill is built.
TRANSFER_SKILL_NAME = "Quintessence Transfer"
SKILL_NAMES: tuple[str, ...] = (TRANSFER_SKILL_NAME,)

#: hours = amount / (TRANSFER_HOURS_DIVISOR x level), floored at MIN_TRANSFER_HOURS.
TRANSFER_HOURS_DIVISOR = Decimal(10)
MIN_TRANSFER_HOURS = Decimal(1)

_NUMBER_TYPES = (int, float, Decimal)


class SkillLadderError(RuntimeError):
    """Base for every refusal this module raises."""


class UnknownSkillError(SkillLadderError):
    """Raised by ``SkillProgress`` for a name ``SKILL_NAMES`` does not carry."""


class SkillLevelError(SkillLadderError):
    """Raised for a level outside ``UNTRAINED_LEVEL`` to ``MAX_SKILL_LEVEL``."""


class UseQualityError(SkillLadderError):
    """Raised for a quality outside ``MIN_USE_QUALITY`` to ``MAX_USE_QUALITY``."""


class WorthlessUseError(SkillLadderError):
    """Raised by ``record_use`` for a use whose quality is ``MIN_USE_QUALITY``."""


class SkillGateError(SkillLadderError):
    """Raised by ``transfer_level`` while the transfer skill stands untrained."""


def _as_quality(value: object) -> Decimal:
    """Return ``value`` as a Decimal quality; bool, NaN and out of range raise."""
    if type(value) is bool or type(value) not in _NUMBER_TYPES:
        raise UseQualityError(
            f"quality must be int, float or Decimal, not {type(value).__name__}"
        )
    quality = value if isinstance(value, Decimal) else Decimal(str(value))
    if not quality.is_finite():
        raise UseQualityError(f"quality must be finite, got {value!r}")
    if quality < MIN_USE_QUALITY or quality > MAX_USE_QUALITY:
        raise UseQualityError(
            f"quality must be {MIN_USE_QUALITY} to {MAX_USE_QUALITY}, got {value!r}"
        )
    return quality


def _as_non_negative(value: object, name: str) -> Decimal:
    """Return ``value`` as a non-negative finite Decimal; bool and NaN raise."""
    if type(value) is bool or type(value) not in _NUMBER_TYPES:
        raise SkillLadderError(
            f"{name} must be int, float or Decimal, not {type(value).__name__}"
        )
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if not amount.is_finite():
        raise SkillLadderError(f"{name} must be finite, got {value!r}")
    if amount < 0:
        raise SkillLadderError(f"{name} must not be negative, got {value!r}")
    return amount


def _as_level(value: object, lowest: int) -> int:
    """Return ``value`` as an int level between ``lowest`` and ``MAX_SKILL_LEVEL``."""
    if type(value) is not int:
        raise SkillLevelError(f"level must be int, not {type(value).__name__}")
    if not lowest <= value <= MAX_SKILL_LEVEL:
        raise SkillLevelError(
            f"level must be {lowest} to {MAX_SKILL_LEVEL}, got {value!r}"
        )
    return value


def cost_of_level(level: int) -> Decimal:
    """Return the quality-weighted uses ``level`` itself costs."""
    trained = _as_level(level, FIRST_SKILL_LEVEL)
    return FIRST_LEVEL_COST * LEVEL_COST_MULTIPLIER ** (trained - FIRST_SKILL_LEVEL)


def cost_to_reach(level: int) -> Decimal:
    """Return every level's ``cost_of_level`` from the first up to ``level``, summed."""
    reached = _as_level(level, UNTRAINED_LEVEL)
    return sum(
        (cost_of_level(step) for step in range(FIRST_SKILL_LEVEL, reached + 1)),
        Decimal(0),
    )


def top_out_uses() -> Decimal:
    """Return the quality-weighted uses the whole ladder costs."""
    return cost_to_reach(MAX_SKILL_LEVEL)


def level_for(weighted_uses: object) -> int:
    """Return the highest level ``weighted_uses`` has paid ``cost_to_reach`` for."""
    paid = _as_non_negative(weighted_uses, "weighted_uses")
    reached = UNTRAINED_LEVEL
    for step in range(FIRST_SKILL_LEVEL, MAX_SKILL_LEVEL + 1):
        if paid < cost_to_reach(step):
            break
        reached = step
    return reached


def effect_at(level: int) -> Decimal:
    """Return ``UNTRAINED_EFFECT`` plus ``EFFECT_STEP_PER_LEVEL`` for each level."""
    return UNTRAINED_EFFECT + EFFECT_STEP_PER_LEVEL * _as_level(level, UNTRAINED_LEVEL)


@dataclass
class SkillProgress:
    """One participant's standing in one skill, held in quality-weighted uses.

    ``weighted_uses`` sums each use's own quality and is never a count of uses;
    ``action_spend.PoaRecordStore`` is what holds it across a restart.
    """

    skill_name: str
    weighted_uses: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        """Refuse a name outside ``SKILL_NAMES`` and a negative ``weighted_uses``."""
        if self.skill_name not in SKILL_NAMES:
            raise UnknownSkillError(
                f"{self.skill_name!r} is not a PoA skill; "
                f"the ladder carries {', '.join(SKILL_NAMES)}"
            )
        self.weighted_uses = _as_non_negative(self.weighted_uses, "weighted_uses")

    @property
    def level(self) -> int:
        """Return the level ``weighted_uses`` has paid for, from ``level_for``."""
        return level_for(self.weighted_uses)

    @property
    def effect(self) -> Decimal:
        """Return the multiplier this standing carries, from ``effect_at``."""
        return effect_at(self.level)

    @property
    def uses_to_next_level(self) -> Decimal:
        """Return the weighted uses the next level still owes, or zero at the cap."""
        reached = self.level
        if reached >= MAX_SKILL_LEVEL:
            return Decimal(0)
        return cost_to_reach(reached + 1) - self.weighted_uses

    def record_use(self, quality: object) -> Decimal:
        """Add one use's ``quality`` to ``weighted_uses`` and return the total.

        A quality of ``MIN_USE_QUALITY`` raises ``WorthlessUseError`` and adds
        nothing.
        """
        contributed = _as_quality(quality)
        if contributed == MIN_USE_QUALITY:
            raise WorthlessUseError(
                f"a use of quality {contributed} advances nothing; "
                f"{self.skill_name} stands at level {self.level} on "
                f"{self.weighted_uses} weighted uses"
            )
        self.weighted_uses += contributed
        return self.weighted_uses


def transfer_level(progress: SkillProgress) -> int:
    """Return ``progress``'s level, raising ``SkillGateError`` while it is untrained."""
    reached = progress.level
    if reached == UNTRAINED_LEVEL:
        raise SkillGateError(
            f"{progress.skill_name} stands at level {UNTRAINED_LEVEL} on "
            f"{progress.weighted_uses} weighted uses; level {FIRST_SKILL_LEVEL} "
            f"costs {cost_of_level(FIRST_SKILL_LEVEL)} and no transfer runs below it"
        )
    return reached


def transfer_bleed(progress: SkillProgress) -> Decimal:
    """Return the bleed ``progress``'s level pays, gated by ``transfer_level``."""
    return bleed_fraction(transfer_level(progress))


def transfer_hours(amount: object, level: int) -> Decimal:
    """Return the hours ``amount`` takes at ``level``, floored at one hour."""
    sent = _as_non_negative(amount, "amount")
    trained = _as_level(level, FIRST_SKILL_LEVEL)
    return max(MIN_TRANSFER_HOURS, sent / (TRANSFER_HOURS_DIVISOR * trained))


def transfers_sent(ledger: QuintessenceLedger, address: str) -> int:
    """Return the transfers ``address`` has sent on ``ledger``, one a skill use."""
    return len(
        [
            movement
            for movement in ledger.movements(address)
            if movement.kind == TRANSFER and movement.source == address
        ]
    )


@dataclass(frozen=True)
class LadderStep:
    """One level of the transfer skill, as ``transfer_ladder`` serves it.

    ``cost_to_reach`` is the whole ladder up to ``level`` and ``bleed`` is what a
    transfer pays there.
    """

    level: int
    level_cost: Decimal
    cost_to_reach: Decimal
    effect: Decimal
    bleed: Decimal


def transfer_ladder() -> tuple[LadderStep, ...]:
    """Return every trained level of the transfer skill, lowest first."""
    return tuple(
        LadderStep(
            level=level,
            level_cost=cost_of_level(level),
            cost_to_reach=cost_to_reach(level),
            effect=effect_at(level),
            bleed=bleed_fraction(level),
        )
        for level in range(FIRST_SKILL_LEVEL, MAX_SKILL_LEVEL + 1)
    )
