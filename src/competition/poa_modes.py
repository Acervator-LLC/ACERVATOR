"""The four PoA event modes, the Elite flag, the candle turn and the Impetus pool.

``MODES`` holds one entry an event type and ``variant_of`` pairs one with the
Elite flag. ``VARIANT_RULES`` is the one place the flag is read, so the turn's
timeframe, the difficulty, the entry fee and both loot ranks are properties of
``EventVariant``. ``turn_at`` reads the candle clock ``TF_SECONDS`` measures,
``seat_at`` seats a midturn entrant in the turn already running, and ``act``
spends the ``impetus_grant`` a level earns from an ``ImpetusPool``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

from ..exchange.data_pool import TF_SECONDS
from .rpg_classes import FIRST_LEVEL

MONSTER_SMASH = "monster_smash"
TEAM_MONSTER_SMASH = "team_monster_smash"
DUNGEON_CRAWL = "dungeon_crawl"
RAID = "raid"

#: The timeframe a turn is one candle of, by Elite flag.
ELITE_TIMEFRAME = "1m"
STANDARD_TIMEFRAME = "5m"

ELITE_SUFFIX = "_elite"
STANDARD_SUFFIX = ""

ELITE_LABEL = "Elite"
STANDARD_LABEL = "Standard"

#: The lowest and highest rank a variant property can hold.
RANK_FLOOR = 1

#: Four Impetus at ``FIRST_LEVEL``, one more every twenty levels.
IMPETUS_AT_FIRST_LEVEL = 4
IMPETUS_LEVELS_PER_STEP = 20

#: A speed multiplier may not take the grant past twice its level value, or below one.
IMPETUS_SPEED_CAP_FACTOR = 2
IMPETUS_FLOOR = 1


class PoaModeError(RuntimeError):
    """Base for every refusal this module raises."""


class UnknownModeError(PoaModeError):
    """Raised by ``mode_named`` for a code ``MODE_CODES`` does not carry."""


class FixedClockError(PoaModeError):
    """Raised by ``seat_at`` for a deadline later than the turn's own candle close."""


class MissedWindowError(PoaModeError):
    """Raised by ``act`` for an action offered after its turn's candle closed."""


class ExpiredPoolError(PoaModeError):
    """Raised by ``ImpetusPool.spend`` for a turn other than the pool's own."""


class PartialActionError(PoaModeError):
    """Raised by ``ImpetusPool.spend`` when ``remaining`` cannot pay the whole cost."""


@dataclass(frozen=True)
class EventMode:
    """One of the four event types, and the bounds and tier the issue gives it.

    ``tier`` is this mode's place in the 1a, 1b, 2a, 2b order, and every rank an
    ``EventVariant`` answers reads it.
    """

    code: str
    label: str
    tier: int
    party_min: int
    party_max: int
    guild_required: bool
    has_map: bool


#: Labels name pre-modern alchemical operations: fixation holds in fire, coagulation
#: binds parts, descension drives downward, cementation parts a mass.
MODES: tuple[EventMode, ...] = (
    EventMode(MONSTER_SMASH, "Fixation", 1, 1, 1, False, False),
    EventMode(TEAM_MONSTER_SMASH, "Coagulation", 2, 2, 120, True, False),
    EventMode(DUNGEON_CRAWL, "Descension", 3, 1, 6, False, True),
    EventMode(RAID, "Cementation", 4, 2, 60, True, True),
)

#: Every mode code, in the order ``MODES`` declares them.
MODE_CODES: tuple[str, ...] = tuple(mode.code for mode in MODES)

#: The top rank, which only an Elite Raid reaches.
RANK_CEILING = len(MODES) + 1


@dataclass(frozen=True)
class VariantRules:
    """What one side of the Elite flag sets: the label, the candle and four rank steps.

    ``suffix`` ends an ``EventVariant.code``, ``label`` names the variant on
    screen, and the four steps move the mode's ``tier`` to the rank it answers.
    """

    suffix: str
    label: str
    timeframe: str
    difficulty_step: int
    entry_fee_step: int
    loot_rarity_step: int
    loot_drop_step: int


STANDARD_RULES = VariantRules(
    STANDARD_SUFFIX, STANDARD_LABEL, STANDARD_TIMEFRAME, 0, 0, 0, 0
)
ELITE_RULES = VariantRules(ELITE_SUFFIX, ELITE_LABEL, ELITE_TIMEFRAME, 1, -1, 1, 1)

#: The one table the Elite flag indexes. No other code reads the flag.
VARIANT_RULES: dict[bool, VariantRules] = {False: STANDARD_RULES, True: ELITE_RULES}


def ranked(value: int) -> int:
    """``value`` held inside ``RANK_FLOOR`` and ``RANK_CEILING``."""
    return max(RANK_FLOOR, min(int(value), RANK_CEILING))


@dataclass(frozen=True)
class EventVariant:
    """One ``EventMode`` under one Elite flag: one of the eight event types.

    Every property below reads ``rules``, so ``elite`` is read in one place and
    no rule branches on it.
    """

    mode: EventMode
    elite: bool = False

    @property
    def rules(self) -> VariantRules:
        """The ``VariantRules`` this variant's ``elite`` flag selects."""
        return VARIANT_RULES[self.elite]

    @property
    def code(self) -> str:
        """The mode's code, carrying ``rules.suffix`` for the Elite variant."""
        return f"{self.mode.code}{self.rules.suffix}"

    @property
    def variant_label(self) -> str:
        """``ELITE_LABEL`` or ``STANDARD_LABEL``, from ``rules.label``."""
        return self.rules.label

    @property
    def turn_timeframe(self) -> str:
        """The candle one turn is one of, from ``rules.timeframe``."""
        return self.rules.timeframe

    @property
    def turn_seconds(self) -> int:
        """The seconds in ``turn_timeframe``, read from ``TF_SECONDS``."""
        return TF_SECONDS[self.turn_timeframe]

    @property
    def difficulty_rank(self) -> int:
        """The mode's ``tier`` moved by ``rules.difficulty_step``."""
        return ranked(self.mode.tier + self.rules.difficulty_step)

    @property
    def entry_fee_rank(self) -> int:
        """The mode's ``tier`` moved by ``rules.entry_fee_step``."""
        return ranked(self.mode.tier + self.rules.entry_fee_step)

    @property
    def loot_rarity_rank(self) -> int:
        """The mode's ``tier`` moved by ``rules.loot_rarity_step``."""
        return ranked(self.mode.tier + self.rules.loot_rarity_step)

    @property
    def loot_drop_rank(self) -> int:
        """The mode's ``tier`` moved by ``rules.loot_drop_step``."""
        return ranked(self.mode.tier + self.rules.loot_drop_step)


def mode_named(code: str) -> EventMode:
    """The entry in ``MODES`` whose ``code`` matches, raising for any other."""
    for mode in MODES:
        if mode.code == code:
            return mode
    refusal = (
        f"{code!r} is not a PoA event mode; " f"the four are {', '.join(MODE_CODES)}"
    )
    raise UnknownModeError(refusal)


def variant_of(code: str, elite: bool = False) -> EventVariant:
    """The ``EventVariant`` for the mode ``code`` names, under ``elite``."""
    return EventVariant(mode_named(code), bool(elite))


#: Every event type: each mode under each side of the Elite flag.
VARIANTS: tuple[EventVariant, ...] = tuple(
    EventVariant(mode, elite) for mode in MODES for elite in (False, True)
)


@dataclass(frozen=True)
class Turn:
    """One turn of one ``EventVariant``, indexed off the shared candle clock.

    ``index`` counts ``variant.turn_seconds`` candles from the epoch, so every
    participant and every market share one boundary.
    """

    variant: EventVariant
    index: int

    @property
    def opened_at(self) -> float:
        """The epoch second this turn's candle opened."""
        return float(self.index * self.variant.turn_seconds)

    @property
    def closes_at(self) -> float:
        """The epoch second this turn's candle closes."""
        return self.opened_at + self.variant.turn_seconds

    def holds(self, at_epoch: float) -> bool:
        """Whether ``at_epoch`` falls inside this turn's own candle."""
        return self.opened_at <= float(at_epoch) < self.closes_at

    def seconds_left(self, at_epoch: float) -> float:
        """The seconds from ``at_epoch`` to ``closes_at``, never below zero."""
        return max(0.0, self.closes_at - float(at_epoch))


def turn_at(variant: EventVariant, at_epoch: float) -> Turn:
    """The ``Turn`` of ``variant`` that the candle clock is in at ``at_epoch``."""
    seconds = variant.turn_seconds
    return Turn(variant, int(float(at_epoch) // seconds))


@dataclass(frozen=True)
class TurnSeat:
    """A participant's place in one ``Turn``, taken at ``joined_at``.

    ``deadline`` is the turn's own candle close, so a midturn entrant holds the
    remainder of the candle and never a fresh turn's worth of it.
    """

    turn: Turn
    joined_at: float

    @property
    def deadline(self) -> float:
        """The turn's ``closes_at``, which joining later does not move."""
        return self.turn.closes_at

    @property
    def seconds_left(self) -> float:
        """The seconds this seat holds, from ``joined_at`` to ``deadline``."""
        return self.turn.seconds_left(self.joined_at)

    @property
    def full_turn(self) -> bool:
        """Whether this seat was taken on the turn's own opening boundary."""
        return float(self.joined_at) <= self.turn.opened_at


def seat_at(
    variant: EventVariant, at_epoch: float, deadline: float | None = None
) -> TurnSeat:
    """Seat a participant in ``variant``'s running turn, refusing a later deadline.

    A ``deadline`` past the turn's candle close would extend the turn, which the
    shared clock refuses.
    """
    turn = turn_at(variant, at_epoch)
    if deadline is not None and float(deadline) > turn.closes_at:
        refusal = (
            f"turn {turn.index} of the {variant.turn_timeframe} candle closes at "
            f"{turn.closes_at:.0f}; a deadline of {float(deadline):.0f} would "
            f"extend it by {float(deadline) - turn.closes_at:.0f}s, and the "
            f"candle clock is fixed for every participant"
        )
        raise FixedClockError(refusal)
    return TurnSeat(turn, float(at_epoch))


def _as_multiplier(value: object) -> Decimal:
    """``value`` as a Decimal speed multiplier, raising below zero."""
    try:
        multiplier = Decimal(str(value))
    except (ArithmeticError, InvalidOperation, TypeError, ValueError) as exc:
        raise PoaModeError(f"{value!r} is not a speed multiplier") from exc
    if multiplier < 0:
        raise PoaModeError(f"a speed multiplier of {multiplier} is below zero")
    return multiplier


def base_impetus(level: int) -> int:
    """Four at ``FIRST_LEVEL``, one more every ``IMPETUS_LEVELS_PER_STEP`` levels."""
    if int(level) < FIRST_LEVEL:
        raise PoaModeError(f"level {level} is below {FIRST_LEVEL}")
    return IMPETUS_AT_FIRST_LEVEL + int(level) // IMPETUS_LEVELS_PER_STEP


def impetus_grant(level: int, speed_multiplier: object = 1) -> int:
    """The Impetus one turn grants at ``level``, scaled by ``speed_multiplier``.

    The product is capped at ``IMPETUS_SPEED_CAP_FACTOR`` times the level's own
    grant and floored at ``IMPETUS_FLOOR``, with fractions rounding down.
    """
    base = base_impetus(level)
    scaled = (Decimal(base) * _as_multiplier(speed_multiplier)).to_integral_value(
        rounding=ROUND_FLOOR
    )
    capped = min(int(scaled), base * IMPETUS_SPEED_CAP_FACTOR)
    return max(IMPETUS_FLOOR, capped)


@dataclass
class ImpetusPool:
    """One turn's Impetus grant, spent inside that turn and lost with it.

    ``turn_index`` binds the pool to one turn, so ``spend`` refuses every other
    turn and nothing unspent carries forward.
    """

    turn_index: int
    granted: int
    spent: int = 0

    @property
    def remaining(self) -> int:
        """The Impetus still unspent in this turn."""
        return self.granted - self.spent

    def spend(self, cost: int, at_turn: int) -> int:
        """Spend ``cost``, refusing another turn or a cost ``remaining`` cannot pay."""
        if int(at_turn) != self.turn_index:
            refusal = (
                f"this pool granted {self.granted} Impetus for turn "
                f"{self.turn_index} and {self.remaining} is unspent; turn "
                f"{int(at_turn)} is a different turn, and Impetus expires with "
                f"the candle that granted it"
            )
            raise ExpiredPoolError(refusal)
        if int(cost) > self.remaining:
            refusal = (
                f"this action costs {int(cost)} Impetus and {self.remaining} "
                f"remains in turn {self.turn_index}; no partial action exists "
                f"and nobody borrows against the next turn"
            )
            raise PartialActionError(refusal)
        self.spent += int(cost)
        return self.remaining


def pool_for(turn: Turn, level: int, speed_multiplier: object = 1) -> ImpetusPool:
    """The ``ImpetusPool`` ``turn`` grants a participant at ``level``."""
    return ImpetusPool(turn.index, impetus_grant(level, speed_multiplier))


def act(seat: TurnSeat, pool: ImpetusPool, cost: int, at_epoch: float) -> int:
    """Spend ``cost`` for one action, refusing it once ``seat``'s candle has closed.

    Returns the Impetus remaining in ``pool`` after the action.
    """
    if not seat.turn.holds(at_epoch):
        refusal = (
            f"turn {seat.turn.index} of the "
            f"{seat.turn.variant.turn_timeframe} candle closed at "
            f"{seat.turn.closes_at:.0f} and it is {float(at_epoch):.0f}; the "
            f"{int(cost)} Impetus for this action is lost with that turn"
        )
        raise MissedWindowError(refusal)
    return pool.spend(cost, turn_at(seat.turn.variant, at_epoch).index)


def variant_row(variant: EventVariant) -> dict:
    """One ``EventVariant`` as the PoA tab surface serves it."""
    return {
        "code": variant.code,
        "mode": variant.mode.code,
        "label": variant.mode.label,
        "variant_label": variant.variant_label,
        "elite": variant.elite,
        "tier": variant.mode.tier,
        "turn_timeframe": variant.turn_timeframe,
        "turn_seconds": variant.turn_seconds,
        "difficulty_rank": variant.difficulty_rank,
        "entry_fee_rank": variant.entry_fee_rank,
        "loot_rarity_rank": variant.loot_rarity_rank,
        "loot_drop_rank": variant.loot_drop_rank,
        "party_min": variant.mode.party_min,
        "party_max": variant.mode.party_max,
        "guild_required": variant.mode.guild_required,
        "has_map": variant.mode.has_map,
    }


def variant_rows() -> list[dict]:
    """Every entry in ``VARIANTS`` as ``variant_row`` serves it, in declared order."""
    return [variant_row(variant) for variant in VARIANTS]
