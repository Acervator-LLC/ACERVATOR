"""A place a priest consecrates for a guild, and the status prayer holds it at.

``SizeRequirement`` carries one size's required turns and cost, and
``require_size_ordering`` refuses a larger size asking for less of either.
``ConsecrationRequest`` names where and for whom, and ``direction_for`` reads
``BLESSED`` or ``CURSED`` off the consecrating priest's own alignment.
``UpkeepRates`` holds the three figures a reading needs, ``PlaceStanding`` is one
reading, and ``ConsecrationRegister.guild_alignment`` joins held places to
``alignment.AlignmentLedger`` at the guild level.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from itertools import pairwise
from typing import TYPE_CHECKING

from .alignment import (
    CREATION,
    DESTRUCTION,
    NEUTRAL,
    ActionScore,
    Alignment,
    AlignmentLedger,
    alignment_from_scores,
    total_alignment,
    vessel_key,
)
from .guild_roster import Guild, GuildRoster
from .rpg_classes import CLASS_NAMES
from .vessels import Vessel
from .world_grid import GridPosition

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger("acervator.consecration")

#: A place consecrated toward Creation.
BLESSED = "blessed"

#: A place consecrated toward Destruction, the same act in the other direction.
CURSED = "cursed"

#: The two directions a consecration runs in. There is no third.
DIRECTIONS: tuple[str, ...] = (BLESSED, CURSED)

#: The pole each direction adds its weight to.
DIRECTION_POLES: dict[str, str] = {BLESSED: CREATION, CURSED: DESTRUCTION}

#: The status a consecration opens at, and the ceiling a prayer restores toward.
FULL_CONSECRATION = Decimal(1)

#: The floor a status falls to. No status reads below it.
LOST_CONSECRATION = Decimal(0)

#: A figure no source sets. Its own note says what would set it.
FIGURE_ABSENT = None

#: The clock every turn field in this module counts.
CLOCK = "world turn"

#: What names the world turn's length. Nothing does.
WORLD_TURN_SECONDS_ABSENT = (
    "no constant names the seconds in a world turn. pvp_vote counts whole world "
    "turns and its own notes carry the operator's one turn an hour, so the hour "
    "lives in prose and every turn field here is a whole turn index"
)

#: What names the size scale. Nothing does.
SIZE_SCALE_ABSENT = (
    "size is a whole rank, smallest first. Nothing names how many ranks there "
    "are, nor which rank a single simple building and an entire Guild Hall hold. "
    "The operator sets the scale"
)

#: What names a size's required turns and cost. Nothing does.
SIZE_FIGURES_ABSENT = (
    "turns_required and cost_quintessence arrive with the size, and this module "
    "holds no table of either. SizeRequirement refuses a size that lacks one, "
    "and require_size_ordering refuses a larger rank asking for less of either"
)

#: What names a consecration's alignment weight. Nothing does.
WEIGHT_SOURCE = (
    "scored_weight arrives with the act, the way alignment.RATIO_SOURCE says "
    "every ratio does. Size defines the required time and cost and ties to no "
    "weight, so a Guild Hall and a single building weigh the same here"
)

#: What names the decay rate, the restoration and the lapse point. Nothing does.
UPKEEP_FIGURES_ABSENT = (
    "decay_per_turn, restore_per_priest and lapse_at_or_below all arrive with "
    "UpkeepRates. No source names one, so every reading needs a caller to "
    "supply all three and a reading that lacks any is refused"
)

#: The shape of the fall between two prayers. No source names a curve.
DECAY_SHAPE = (
    "status falls by decay_per_turn for each whole world turn since the last "
    "prayer, a flat amount a turn. No source names a curve, and the orderings "
    "require_upkeep_ordering drives hold for any fall that never rises"
)

#: What a held place contributes, and what a lapsed one contributes.
CONTRIBUTION_IS_BINARY = (
    "a consecrated place contributes its whole scored_weight to its direction's "
    "pole, and a lapsed place contributes nothing. No source names a "
    "contribution that shrinks as the status falls, so none is derived"
)

#: What bounds the places one guild can hold. Priest attention does.
STACKING_BOUND = (
    "the arithmetic caps nothing: a guild's place alignment is the sum of every "
    "place it holds. The operator's decay rule is the bound, because each held "
    "place lapses within turns_until_lapse of its last prayer, so a guild holds "
    "only as many places as its priests keep praying over. No cap is added here"
)

#: What takes a held place from the guild holding it. Nothing does.
RIVAL_BREAK_ABSENT = (
    "one locator holds one consecration, so consecrate refuses a second guild "
    "and refuses the other direction while the place is consecrated. A rival "
    "re-consecrates only a place that has already lapsed, and no act breaks a "
    "consecration priests are still praying over"
)

#: Whether a priest must belong to the guild consecrating. No source says.
GUILD_MEMBERSHIP_OWED = (
    "the operator's words say a priest consecrates for their Guilds and do not "
    "say a priest must belong to the guild named. consecrate takes the guild as "
    "given and checks no membership, and GuildRoster.guild_of would answer it"
)

#: What names a priest. No class does.
PRIEST_CLASS_ABSENT = (
    "no name in rpg_classes.CLASS_NAMES is a priest, and no ability exists to "
    "consecrate with. consecrate takes any Vessel as the priest, so nothing "
    "refuses a consecration by a Vessel of the wrong class"
)

#: What owns the act that restores a status. Another module does.
PRAYER_WIRING_OWED = (
    "pray takes the praying priests and the turn as given and performs no "
    "prayer. prayer.PrayerRoll.pray targets a Vessel and no place, so nothing "
    "outside this module restores a consecration's status"
)

#: What a guild owns on a consecrated square. Nothing.
PLACE_OWNERSHIP_ABSENT = (
    "world_grid carries no owner on a square, a zone or a fact, so a "
    "consecration records the guild it is held for and confers no ownership of "
    "the place"
)

#: What a consecration builds. Nothing.
BUILDING_ABSENT = (
    "the operator made a base and city building system conditional on world "
    "instance storage on chain being viable, and the world grid is built with "
    "its byte budget measured. No building, guild hall or structure exists, so "
    "size is a rank on a consecration and nothing is constructed"
)

#: Where a guild's places reach the world. Only through the roster.
UNROSTERED_GUILD_PATH_ABSENT = (
    "world_alignment adds the places of each guild a GuildRoster holds, so the "
    "places of a guild key no roster carries reach the world nowhere. It is the "
    "same gap alignment.UNGUILDED_PATH_ABSENT names one level down"
)

#: What moves the cost a consecration declares. The ledger does, and not here.
QUINTESSENCE_MOVEMENT_ABSENT = (
    "cost_quintessence is a declared requirement and this module debits no "
    "wallet. quintessence_ledger owns every movement, and nothing spends a "
    "consecration's cost"
)

#: What reads a consecration. Nothing does.
ABSENT_READERS: tuple[str, ...] = (
    "a priest ability",
    "the world alignment",
    "a surface",
    "the map",
    "a notification",
)

#: What each entry in ``ABSENT_READERS`` waits on.
ABSENT_READER_NOTES: dict[str, str] = {
    "a priest ability": PRIEST_CLASS_ABSENT,
    "the world alignment": (
        "guild_alignment and world_alignment here join places to the chain, and "
        "no caller outside this module runs either"
    ),
    "a surface": "no tab or panel shows a consecrated place or its status",
    "the map": "map_glyphs carries no glyph for a consecrated place",
    "a notification": "nothing tells a guild that a place it holds is lapsing",
}


class ConsecrationError(RuntimeError):
    """Base for every refusal this module raises."""


class SizeError(ConsecrationError):
    """Raised by ``SizeRequirement`` and ``require_size_ordering`` for a bad size."""


class DirectionError(ConsecrationError):
    """Raised by ``direction_for`` when a priest's alignment names no direction."""


class LocatorError(ConsecrationError):
    """Raised by ``place_locator`` for a position or layer no locator can hold."""


class HeldPlaceError(ConsecrationError):
    """Raised by ``consecrate`` for a locator another consecration still holds."""


class UnknownPlaceError(ConsecrationError):
    """Raised by ``place`` for a locator no consecration in the register names."""


class UpkeepError(ConsecrationError):
    """Raised by ``UpkeepRates`` and ``require_upkeep_ordering`` for a bad figure."""


_AMOUNT_TYPES = (int, str, Decimal)


def _as_amount(value: object, name: str) -> Decimal:
    """Return ``value`` as a finite ``Decimal`` of zero or more, refusing ``float``."""
    if value is FIGURE_ABSENT:
        raise UpkeepError(f"{name} is absent; {UPKEEP_FIGURES_ABSENT}")
    if type(value) not in _AMOUNT_TYPES:
        raise UpkeepError(
            f"{name} must be int, str or Decimal, not {type(value).__name__}; a "
            f"consecration figure decided by binary floating point is refused",
        )
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise UpkeepError(f"{name} must be a number, got {value!r}") from exc
    if not amount.is_finite() or amount < 0:
        raise UpkeepError(f"{name} must be finite and zero or more, got {value!r}")
    return amount


def _as_whole(value: object, name: str) -> int:
    """Return ``value`` as a whole number of zero or more, refusing every other type."""
    if value is FIGURE_ABSENT:
        raise SizeError(f"{name} is absent; {SIZE_FIGURES_ABSENT}")
    if type(value) is not int:
        raise SizeError(f"{name} must be a whole number, not {type(value).__name__}")
    if value < 0:
        raise SizeError(f"{name} must be zero or more, got {value!r}")
    return value


def _as_guild_key(value: object) -> str:
    """Return a ``Guild``'s own key, or ``value`` itself as a non-blank guild key."""
    if isinstance(value, Guild):
        return value.key
    if type(value) is not str or not value.strip():
        raise ConsecrationError(f"guild must be a Guild or a key, got {value!r}")
    return value


def _as_locator(value: object) -> str:
    """Return ``value`` as a non-blank locator; every other value raises."""
    if type(value) is not str or not value.strip():
        raise LocatorError(f"locator must be a non-empty text, got {value!r}")
    return value


def place_locator(position: object, layer: object) -> str:
    """Return the ``GridPosition.locator`` text one consecration is recorded at."""
    if not isinstance(position, GridPosition):
        raise LocatorError(
            f"a GridPosition was expected, got {type(position).__name__}",
        )
    if type(layer) is not int or layer < 0:
        raise LocatorError(
            f"layer must be a whole number of zero or more, got {layer!r}",
        )
    return position.locator(layer)


def direction_for(ledger: object, priest: object) -> str:
    """Return ``BLESSED`` or ``CURSED`` from ``priest``'s own alignment polarity."""
    if not isinstance(ledger, AlignmentLedger):
        raise DirectionError(
            f"an AlignmentLedger was expected, got {type(ledger).__name__}",
        )
    if not isinstance(priest, Vessel):
        raise DirectionError(f"a Vessel was expected, got {type(priest).__name__}")
    reading = ledger.alignment_of(priest).polarity
    if reading is None:
        raise DirectionError(
            f"{vessel_key(priest)} has scored no action, so alignment."
            f"POLARITY_ABSENT is its reading and it names neither {BLESSED} nor "
            f"{CURSED}",
        )
    if reading == NEUTRAL:
        raise DirectionError(
            f"{vessel_key(priest)} reads exactly {NEUTRAL}, which names neither "
            f"{BLESSED} nor {CURSED}; alignment.NEUTRAL_BAND is absent",
        )
    return BLESSED if reading > NEUTRAL else CURSED


@dataclass(frozen=True)
class SizeRequirement:
    """One size rank, and the world turns and Quintessence cost it requires."""

    size: int
    turns_required: int
    cost_quintessence: Decimal

    def __post_init__(self) -> None:
        """Coerce the rank and both requirements, refusing an absent figure."""
        object.__setattr__(self, "size", _as_whole(self.size, "size"))
        object.__setattr__(
            self,
            "turns_required",
            _as_whole(self.turns_required, "turns_required"),
        )
        object.__setattr__(
            self,
            "cost_quintessence",
            _as_amount(self.cost_quintessence, "cost_quintessence"),
        )

    def to_dict(self) -> dict:
        """Return this requirement as a JSON-safe dict, the cost a plain string."""
        return {
            "size": self.size,
            "turns_required": self.turns_required,
            "cost_quintessence": str(self.cost_quintessence),
            "clock": CLOCK,
        }


def require_size_ordering(
    requirements: Iterable[SizeRequirement],
) -> tuple[SizeRequirement, ...]:
    """Refuse a larger size rank requiring less time or cost than a smaller rank."""
    held = tuple(requirements)
    for entry in held:
        if not isinstance(entry, SizeRequirement):
            raise SizeError(
                f"a SizeRequirement was expected, got {type(entry).__name__}",
            )
    ranked = tuple(sorted(held, key=lambda entry: entry.size))
    seen: set[int] = set()
    for entry in ranked:
        if entry.size in seen:
            raise SizeError(
                f"size rank {entry.size} is named twice; one rank carries one "
                f"requirement",
            )
        seen.add(entry.size)
    for smaller, larger in pairwise(ranked):
        if larger.turns_required < smaller.turns_required:
            raise SizeError(
                f"size {larger.size} requires {larger.turns_required} {CLOCK}s "
                f"and the smaller size {smaller.size} requires "
                f"{smaller.turns_required}; a larger size requires at least as "
                f"much time",
            )
        if larger.cost_quintessence < smaller.cost_quintessence:
            raise SizeError(
                f"size {larger.size} costs {larger.cost_quintessence} and the "
                f"smaller size {smaller.size} costs "
                f"{smaller.cost_quintessence}; a larger size requires at least "
                f"as much cost",
            )
    return ranked


@dataclass(frozen=True)
class UpkeepRates:
    """The three figures a status reading needs, none of them named anywhere."""

    decay_per_turn: Decimal
    restore_per_priest: Decimal
    lapse_at_or_below: Decimal

    def __post_init__(self) -> None:
        """Coerce all three figures, refusing a lapse point off the status scale."""
        object.__setattr__(
            self,
            "decay_per_turn",
            _as_amount(self.decay_per_turn, "decay_per_turn"),
        )
        object.__setattr__(
            self,
            "restore_per_priest",
            _as_amount(self.restore_per_priest, "restore_per_priest"),
        )
        object.__setattr__(
            self,
            "lapse_at_or_below",
            _as_amount(self.lapse_at_or_below, "lapse_at_or_below"),
        )
        if self.lapse_at_or_below >= FULL_CONSECRATION:
            raise UpkeepError(
                f"lapse_at_or_below of {self.lapse_at_or_below} is not below "
                f"{FULL_CONSECRATION}, so a place would read lapsed on the turn "
                f"it was consecrated",
            )

    def fall_over(self, turns: int) -> Decimal:
        """Return the status lost over ``turns`` world turns of silence."""
        return self.decay_per_turn * turns

    def restored_by(self, priests: int) -> Decimal:
        """Return the status ``priests`` praying together restore in one prayer."""
        return self.restore_per_priest * priests

    def to_dict(self) -> dict:
        """Return these figures as a JSON-safe dict, with what names them."""
        return {
            "decay_per_turn": str(self.decay_per_turn),
            "restore_per_priest": str(self.restore_per_priest),
            "lapse_at_or_below": str(self.lapse_at_or_below),
            "clock": CLOCK,
            "upkeep_figures_absent": UPKEEP_FIGURES_ABSENT,
            "decay_shape": DECAY_SHAPE,
        }


@dataclass(frozen=True)
class ConsecrationRequest:
    """Where a consecration goes, for which guild, at which size and weight."""

    position: GridPosition
    layer: int
    guild: object
    requirement: SizeRequirement
    scored_weight: Decimal

    def __post_init__(self) -> None:
        """Coerce the guild key and the weight, refusing a weight of zero."""
        place_locator(self.position, self.layer)
        object.__setattr__(self, "guild", _as_guild_key(self.guild))
        if not isinstance(self.requirement, SizeRequirement):
            raise SizeError(
                f"a SizeRequirement was expected, got "
                f"{type(self.requirement).__name__}; {SIZE_FIGURES_ABSENT}",
            )
        weight = _as_amount(self.scored_weight, "scored_weight")
        if weight == 0:
            raise ConsecrationError(
                f"scored_weight of {weight} scores nothing; {WEIGHT_SOURCE}",
            )
        object.__setattr__(self, "scored_weight", weight)

    @property
    def locator(self) -> str:
        """Return the ``place_locator`` text this request is recorded at."""
        return place_locator(self.position, self.layer)

    @property
    def guild_key(self) -> str:
        """Return the guild key this request holds the place for."""
        return _as_guild_key(self.guild)


@dataclass(frozen=True)
class Consecration:
    """One act: the locator, the guild it is held for, its size and its direction."""

    locator: str
    guild_key: str
    priest: tuple[str, str]
    requirement: SizeRequirement
    direction: str
    scored_weight: Decimal
    consecrated_turn: int

    @property
    def creation(self) -> Decimal:
        """Return ``scored_weight`` while ``direction`` is ``BLESSED``, else zero."""
        return self.scored_weight if self.direction == BLESSED else Decimal(0)

    @property
    def destruction(self) -> Decimal:
        """Return ``scored_weight`` while ``direction`` is ``CURSED``, else zero."""
        return self.scored_weight if self.direction == CURSED else Decimal(0)

    @property
    def action(self) -> str:
        """Return the action name this act scores its ratio under."""
        return f"{self.direction} place {self.locator}"

    def score(self) -> ActionScore:
        """Return one ``ActionScore`` on the pole ``direction`` names."""
        return ActionScore(self.action, self.creation, self.destruction)

    def to_dict(self) -> dict:
        """Return this act as a JSON-safe dict, every amount a plain string."""
        return {
            "locator": self.locator,
            "guild_key": self.guild_key,
            "priest": list(self.priest),
            "requirement": self.requirement.to_dict(),
            "direction": self.direction,
            "pole": DIRECTION_POLES[self.direction],
            "scored_weight": str(self.scored_weight),
            CREATION: str(self.creation),
            DESTRUCTION: str(self.destruction),
            "consecrated_turn": self.consecrated_turn,
            "clock": CLOCK,
        }


@dataclass
class ConsecratedPlace:
    """One ``Consecration`` and the prayer history its status falls from."""

    consecration: Consecration
    status_at_last_prayer: Decimal = FULL_CONSECRATION
    last_prayer_turn: int = 0
    last_prayer_priests: int = 0
    prayer_count: int = 0

    def to_dict(self) -> dict:
        """Return this place as a JSON-safe dict, the held status a plain string."""
        return {
            "consecration": self.consecration.to_dict(),
            "status_at_last_prayer": str(self.status_at_last_prayer),
            "last_prayer_turn": self.last_prayer_turn,
            "last_prayer_priests": self.last_prayer_priests,
            "prayer_count": self.prayer_count,
        }


@dataclass(frozen=True)
class PlaceStanding:
    """One place read at one world turn: its status, and whether it still holds."""

    locator: str
    guild_key: str
    direction: str
    turn: int
    turns_since_prayer: int
    status: Decimal
    is_consecrated: bool
    turns_until_lapse: int | None

    def to_dict(self) -> dict:
        """Return this reading as a JSON-safe dict, the status a plain string."""
        return {
            "locator": self.locator,
            "guild_key": self.guild_key,
            "direction": self.direction,
            "turn": self.turn,
            "turns_since_prayer": self.turns_since_prayer,
            "status": str(self.status),
            "is_consecrated": self.is_consecrated,
            "turns_until_lapse": self.turns_until_lapse,
            "clock": CLOCK,
            "contribution_is_binary": CONTRIBUTION_IS_BINARY,
        }


def turns_until_lapse(status: Decimal, rates: UpkeepRates) -> int | None:
    """Return the world turns of silence ``status`` survives, absent while flat."""
    if rates.decay_per_turn == 0:
        return FIGURE_ABSENT
    if status <= rates.lapse_at_or_below:
        return 0
    margin = status - rates.lapse_at_or_below
    turns = margin / rates.decay_per_turn
    return int(turns.to_integral_value(rounding=ROUND_CEILING))


class ConsecrationRegister:
    """Every consecrated place, one a locator, and the alignment held places add.

    ``consecrate`` opens one at ``FULL_CONSECRATION``, ``pray`` restores a status
    and ``guild_alignment`` joins the held places to ``AlignmentLedger`` totals.
    """

    def __init__(self) -> None:
        """Open an empty register, holding no place."""
        self._places: dict[str, ConsecratedPlace] = {}

    @property
    def place_count(self) -> int:
        """How many consecrations this register holds, lapsed ones included."""
        return len(self._places)

    def locators(self) -> tuple[str, ...]:
        """Every locator this register holds a consecration at, in locator order."""
        return tuple(sorted(self._places))

    def consecrate(
        self,
        request: object,
        priest: object,
        turn: object,
        ledger: object,
    ) -> Consecration:
        """Consecrate one place, its direction read off ``priest``'s own alignment."""
        if not isinstance(request, ConsecrationRequest):
            raise ConsecrationError(
                f"a ConsecrationRequest was expected, got {type(request).__name__}",
            )
        opened_turn = _as_whole(turn, "turn")
        direction = direction_for(ledger, priest)
        self._require_free(request.locator, request.guild_key, direction)
        act = Consecration(
            request.locator,
            request.guild_key,
            vessel_key(priest),
            request.requirement,
            direction,
            request.scored_weight,
            opened_turn,
        )
        self._places[act.locator] = ConsecratedPlace(
            act,
            FULL_CONSECRATION,
            opened_turn,
            1,
            0,
        )
        logger.info(
            "%s %s consecrated %s as %s for guild %s at weight %s, requiring %d "
            "%ss and %s Quintessence on %s %d; %s",
            act.priest[0],
            act.priest[1],
            act.locator,
            direction,
            act.guild_key,
            act.scored_weight,
            act.requirement.turns_required,
            CLOCK,
            act.requirement.cost_quintessence,
            CLOCK,
            opened_turn,
            QUINTESSENCE_MOVEMENT_ABSENT,
        )
        return act

    def place(self, locator: object) -> ConsecratedPlace:
        """Return the ``ConsecratedPlace`` at ``locator``, raising while none is."""
        key = _as_locator(locator)
        held = self._places.get(key)
        if held is None:
            raise UnknownPlaceError(
                f"no consecration names {key}; this register holds "
                f"{self.place_count} place(s)",
            )
        return held

    def standing(self, locator: object, turn: object, rates: object) -> PlaceStanding:
        """Read one place at world turn ``turn``, its status fallen by ``DECAY_SHAPE``.

        ``is_consecrated`` reads False once the status reaches ``lapse_at_or_below``.
        """
        held = self.place(locator)
        figures = self._as_rates(rates)
        at_turn = _as_whole(turn, "turn")
        if at_turn < held.last_prayer_turn:
            raise UpkeepError(
                f"{CLOCK} {at_turn} is before the last prayer on "
                f"{held.consecration.locator} at {CLOCK} "
                f"{held.last_prayer_turn}; a status is read forward only",
            )
        elapsed = at_turn - held.last_prayer_turn
        fallen = held.status_at_last_prayer - figures.fall_over(elapsed)
        status = max(LOST_CONSECRATION, fallen)
        return PlaceStanding(
            held.consecration.locator,
            held.consecration.guild_key,
            held.consecration.direction,
            at_turn,
            elapsed,
            status,
            status > figures.lapse_at_or_below,
            turns_until_lapse(status, figures),
        )

    def pray(
        self,
        locator: object,
        priests: object,
        turn: object,
        rates: object,
    ) -> PlaceStanding:
        """Restore one place's status by ``priests`` praying over it on ``turn``."""
        held = self.place(locator)
        figures = self._as_rates(rates)
        praying = _as_whole(priests, "priests")
        if praying < 1:
            raise UpkeepError(
                f"a prayer needs at least one priest, got {praying}; "
                f"{PRAYER_WIRING_OWED}",
            )
        before = self.standing(locator, turn, figures)
        restored = before.status + figures.restored_by(praying)
        held.status_at_last_prayer = min(FULL_CONSECRATION, restored)
        held.last_prayer_turn = before.turn
        held.last_prayer_priests = praying
        held.prayer_count += 1
        after = self.standing(locator, turn, figures)
        logger.info(
            "%d priest(s) prayed over %s on %s %d, taking its status from %s to "
            "%s; consecrated=%s, lapsing in %s %ss",
            praying,
            after.locator,
            CLOCK,
            after.turn,
            before.status,
            after.status,
            after.is_consecrated,
            after.turns_until_lapse,
            CLOCK,
        )
        return after

    def last_prayer_turn(self) -> int | None:
        """Return the latest world turn any place here was prayed over."""
        if not self._places:
            return FIGURE_ABSENT
        return max(place.last_prayer_turn for place in self._places.values())

    def standings(self, turn: object, rates: object) -> tuple[PlaceStanding, ...]:
        """Read every place this register holds at world turn ``turn``."""
        figures = self._as_rates(rates)
        at_turn = _as_whole(turn, "turn")
        latest = self.last_prayer_turn()
        if latest is not None and at_turn < latest:
            raise UpkeepError(
                f"{CLOCK} {at_turn} is before the latest prayer in this "
                f"register, on {CLOCK} {latest}; a register keeps only each "
                f"place's latest prayer, so no earlier {CLOCK} has a reading",
            )
        return tuple(
            self.standing(locator, at_turn, figures) for locator in self.locators()
        )

    def held_standings(
        self,
        guild_key: object,
        turn: object,
        rates: object,
    ) -> tuple[PlaceStanding, ...]:
        """Every still-consecrated place one guild holds at world turn ``turn``."""
        key = _as_guild_key(guild_key)
        return tuple(
            reading
            for reading in self.standings(turn, rates)
            if reading.guild_key == key and reading.is_consecrated
        )

    def place_scores(
        self,
        guild_key: object,
        turn: object,
        rates: object,
    ) -> tuple[ActionScore, ...]:
        """One ``ActionScore`` a held place, a lapsed place scoring nothing."""
        return tuple(
            self.place(reading.locator).consecration.score()
            for reading in self.held_standings(guild_key, turn, rates)
        )

    def place_alignment(
        self,
        guild_key: object,
        turn: object,
        rates: object,
    ) -> Alignment:
        """Add every held place of one guild, ``UNSCORED`` while it holds none."""
        return alignment_from_scores(self.place_scores(guild_key, turn, rates))

    def guild_alignment(
        self,
        ledger: object,
        guild: object,
        turn: object,
        rates: object,
    ) -> Alignment:
        """Add one guild's Vessel alignment and the held places it consecrated for."""
        if not isinstance(ledger, AlignmentLedger):
            raise ConsecrationError(
                f"an AlignmentLedger was expected, got {type(ledger).__name__}",
            )
        if not isinstance(guild, Guild):
            raise ConsecrationError(f"a Guild was expected, got {type(guild).__name__}")
        places = self.place_alignment(guild.key, turn, rates)
        reading = total_alignment((ledger.guild_alignment(guild), places))
        logger.info(
            "guild %s reads %s over %s at polarity %s with %d held place(s) "
            "adding %s over %s",
            guild.key,
            reading.net_creation,
            reading.scored_total,
            reading.polarity,
            places.scored_actions,
            places.net_creation,
            places.scored_total,
        )
        return reading

    def world_alignment(
        self,
        ledger: object,
        roster: object,
        turn: object,
        rates: object,
    ) -> Alignment:
        """Add every guild's Vessels and its held places, over the whole roster."""
        if not isinstance(ledger, AlignmentLedger):
            raise ConsecrationError(
                f"an AlignmentLedger was expected, got {type(ledger).__name__}",
            )
        if not isinstance(roster, GuildRoster):
            raise ConsecrationError(
                f"a GuildRoster was expected, got {type(roster).__name__}",
            )
        parts = [ledger.world_alignment(roster)]
        parts.extend(
            self.place_alignment(guild.key, turn, rates) for guild in roster.guilds()
        )
        reading = total_alignment(parts)
        outside = self.unrostered_guild_keys(roster)
        logger.info(
            "the world reads %s over %s at polarity %s across %d guild(s), and "
            "%d guild key(s) hold places that reach it nowhere: %s",
            reading.net_creation,
            reading.scored_total,
            reading.polarity,
            roster.guild_count,
            len(outside),
            UNROSTERED_GUILD_PATH_ABSENT,
        )
        return reading

    def unrostered_guild_keys(self, roster: object) -> tuple[str, ...]:
        """Every guild key holding a place here that ``roster`` does not carry."""
        if not isinstance(roster, GuildRoster):
            raise ConsecrationError(
                f"a GuildRoster was expected, got {type(roster).__name__}",
            )
        seated = set(roster.keys())
        held = {place.consecration.guild_key for place in self._places.values()}
        return tuple(sorted(key for key in held if key not in seated))

    def rows(self, turn: object, rates: object) -> list[dict]:
        """One row a place, carrying its act, its prayer history and its standing."""
        return [
            {
                "place": self._places[reading.locator].to_dict(),
                "standing": reading.to_dict(),
            }
            for reading in self.standings(turn, rates)
        ]

    def to_dict(self, turn: object, rates: object) -> dict:
        """Return this register read at ``turn`` as a dict, with what is owed."""
        figures = self._as_rates(rates)
        return {
            "place_count": self.place_count,
            "places": self.rows(turn, figures),
            "rates": figures.to_dict(),
            "directions": list(DIRECTIONS),
            "direction_poles": dict(DIRECTION_POLES),
            "clock": CLOCK,
            "world_turn_seconds_absent": WORLD_TURN_SECONDS_ABSENT,
            "size_scale_absent": SIZE_SCALE_ABSENT,
            "size_figures_absent": SIZE_FIGURES_ABSENT,
            "weight_source": WEIGHT_SOURCE,
            "upkeep_figures_absent": UPKEEP_FIGURES_ABSENT,
            "decay_shape": DECAY_SHAPE,
            "contribution_is_binary": CONTRIBUTION_IS_BINARY,
            "stacking_bound": STACKING_BOUND,
            "rival_break_absent": RIVAL_BREAK_ABSENT,
            "guild_membership_owed": GUILD_MEMBERSHIP_OWED,
            "priest_class_absent": PRIEST_CLASS_ABSENT,
            "prayer_wiring_owed": PRAYER_WIRING_OWED,
            "place_ownership_absent": PLACE_OWNERSHIP_ABSENT,
            "building_absent": BUILDING_ABSENT,
            "unrostered_guild_path_absent": UNROSTERED_GUILD_PATH_ABSENT,
            "quintessence_movement_absent": QUINTESSENCE_MOVEMENT_ABSENT,
            "absent_readers": list(ABSENT_READERS),
            "absent_reader_notes": dict(ABSENT_READER_NOTES),
        }

    def _require_free(self, locator: str, guild_key: str, direction: str) -> None:
        """Refuse a second consecration at ``locator`` while the first still holds."""
        held = self._places.get(locator)
        if held is None:
            return
        raise HeldPlaceError(
            f"{locator} is already consecrated as {held.consecration.direction} "
            f"for guild {held.consecration.guild_key}, last prayed over on "
            f"{CLOCK} {held.last_prayer_turn}; guild {guild_key} cannot "
            f"consecrate it as {direction}. {RIVAL_BREAK_ABSENT}",
        )

    def _as_rates(self, value: object) -> UpkeepRates:
        """Return ``value`` as ``UpkeepRates``; every other value raises."""
        if not isinstance(value, UpkeepRates):
            raise UpkeepError(
                f"an UpkeepRates was expected, got {type(value).__name__}; "
                f"{UPKEEP_FIGURES_ABSENT}",
            )
        return value


def require_upkeep_ordering(rates: object, turns: object, priests: object) -> None:
    """Drive the orderings the operator's decay rule implies, over ``turns``."""
    if not isinstance(rates, UpkeepRates):
        raise UpkeepError(f"an UpkeepRates was expected, got {type(rates).__name__}")
    span = _as_whole(turns, "turns")
    crowd = _as_whole(priests, "priests")
    if rates.decay_per_turn > 0 and rates.restore_per_priest == 0:
        raise UpkeepError(
            f"a status falls {rates.decay_per_turn} a {CLOCK} and a praying "
            f"priest restores {rates.restore_per_priest}, so no amount of "
            f"prayer holds a place consecrated",
        )
    falls = [rates.fall_over(elapsed) for elapsed in range(span + 1)]
    for elapsed, (earlier, later) in enumerate(pairwise(falls)):
        if later < earlier:
            raise UpkeepError(
                f"the fall over {elapsed + 1} {CLOCK}s is {later} and over "
                f"{elapsed} it is {earlier}; more elapsed time never leaves a "
                f"higher status",
            )
    restores = [rates.restored_by(count) for count in range(crowd + 1)]
    for count, (fewer, more) in enumerate(pairwise(restores)):
        if more < fewer:
            raise UpkeepError(
                f"{count + 1} priest(s) restore {more} and {count} restore "
                f"{fewer}; more priests restore at least as much as fewer",
            )


def require_consecration_scale() -> None:
    """Drive the scale, both directions and both orderings, and log what is absent."""
    ranked = require_size_ordering(
        (SizeRequirement(2, 8, Decimal(40)), SizeRequirement(1, 2, Decimal(10))),
    )
    if tuple(entry.size for entry in ranked) != (1, 2):
        raise SizeError(
            f"require_size_ordering returned ranks "
            f"{[entry.size for entry in ranked]}; smallest first was expected",
        )
    rates = UpkeepRates(Decimal("0.25"), Decimal("0.5"), LOST_CONSECRATION)
    require_upkeep_ordering(rates, len(ranked) * 2, len(ranked))
    if turns_until_lapse(LOST_CONSECRATION, rates) != 0:
        raise UpkeepError(
            f"a status of {LOST_CONSECRATION} lapses in "
            f"{turns_until_lapse(LOST_CONSECRATION, rates)} {CLOCK}s; a status "
            f"at or below lapse_at_or_below has already lapsed",
        )
    priest = ("owner", CLASS_NAMES[0])
    blessed = Consecration("0:0:0:0", "g", priest, ranked[0], BLESSED, Decimal(1), 0)
    cursed = Consecration("0:0:0:1", "g", priest, ranked[0], CURSED, Decimal(1), 0)
    if blessed.score().polarity <= NEUTRAL or cursed.score().polarity >= NEUTRAL:
        raise DirectionError(
            f"a {BLESSED} place reads {blessed.score().polarity} and a {CURSED} "
            f"place reads {cursed.score().polarity}; the two sit on opposite "
            f"sides of {NEUTRAL}",
        )
    logger.info(
        "a consecration runs %s to %s on the %s, %s and %s are the two "
        "directions, and %d readers are absent: %s",
        LOST_CONSECRATION,
        FULL_CONSECRATION,
        CLOCK,
        BLESSED,
        CURSED,
        len(ABSENT_READERS),
        ", ".join(ABSENT_READERS),
    )


require_consecration_scale()
