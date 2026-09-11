"""The prayer a priest offers, and the alignment it writes on another player.

``PrayerRates`` carries the four figures a prayer needs and ``prayer_shifts``
reads the pair one congregation moves at, so ``PrayerRoll.pray`` files both
shifts through ``AlignmentLedger.score``. ``chosen_actions`` keeps a Vessel's own
run apart from ``received_prayers``, and ``ABSENT_READERS`` names what reads none
of this.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from .alignment import (
    CREATION,
    DESTRUCTION,
    FIGURE_ABSENT,
    NEUTRAL,
    POLES,
    ActionScore,
    Alignment,
    AlignmentLedger,
    RatioError,
    alignment_from_scores,
    vessel_key,
)
from .rpg_classes import CLASS_NAMES, class_named

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

logger = logging.getLogger("acervator.prayer")

#: What a prayer files against the Vessel that led it. Its own choice.
PRAYER_LED = "prayer led"

#: What a prayer files against the Vessel it was worked on. Not its own choice.
PRAYER_RECEIVED = "prayer received"

#: The two action names this module writes. No other module writes either.
PRAYER_ACTIONS: tuple[str, ...] = (PRAYER_LED, PRAYER_RECEIVED)

#: The one kind of target ``PrayerRoll.pray`` files against.
PLAYER_TARGET = "player"

#: Every kind of target a prayer reaches today.
TARGET_KINDS: tuple[str, ...] = (PLAYER_TARGET,)

#: What a second kind of target needs, and which part of this module takes it.
PLACE_TARGET_OWED = (
    "a consecrated place is a second kind of target and no module holds one. "
    "PrayerRates and prayer_shifts name no target and serve any kind. "
    "PrayerRoll.pray files through AlignmentLedger.score, which takes a Vessel, "
    "so a place needs its own filing step and none of the arithmetic here"
)

#: How far one prayer moves the target. No source sets it.
TARGET_SHIFT_PER_PRAYER = FIGURE_ABSENT

#: How far one prayer moves the priest that led it. No source sets it.
PRIEST_SHIFT_PER_PRAYER = FIGURE_ABSENT

#: What each priest past the first adds to the target's shift. No source sets it.
GROUP_SPEEDUP_PER_PRIEST = FIGURE_ABSENT

#: What each priest past the first takes off every priest's own shift. Absent.
GROUP_RELIEF_PER_PRIEST = FIGURE_ABSENT

#: The four figures ``PrayerRates`` takes, in the order it declares them.
FIGURES_OWED: tuple[str, ...] = (
    "target_shift",
    "priest_shift",
    "group_speedup",
    "group_relief",
)

#: What each entry in ``FIGURES_OWED`` is, and who sets it.
FIGURE_NOTES: dict[str, str] = {
    "target_shift": (
        "how much Creation or Destruction one prayer scores against the target. "
        "No figure names it and the operator sets it"
    ),
    "priest_shift": (
        "how much the same prayer scores against each priest that led it. The "
        "operator's word is slower, which orders it under target_shift and "
        "names no number"
    ),
    "group_speedup": (
        "what each priest past the first adds to target_shift. Zero is a "
        "congregation that prays no faster than one priest"
    ),
    "group_relief": (
        "what each priest past the first takes off priest_shift. Zero is a "
        "congregation that costs each priest the same as praying alone"
    ),
}

#: The relation every congregation size holds, enforced by ``require_shift_relations``.
SHIFT_ORDERING = (
    "priest_shift_at is strictly under target_shift_at at every size, "
    "target_shift_at never falls as the size rises, and priest_shift_at never "
    "rises as the size rises"
)

#: The ordering is on the scored shift. A polarity move is not the same quantity.
SHIFT_NOT_POLARITY = (
    "the ordering holds on the shift each side is scored at. A polarity move is "
    "that shift read against the Vessel's own scored_total, so a lightly scored "
    "priest can move further in polarity than a heavily scored target moves"
)

#: Why a congregation has a last size, and what would replace the refusal.
GROUP_FLOOR = (
    "ActionScore refuses a score carrying no creation and no destruction, so a "
    "size whose relief drives priest_shift_at to zero files nothing and pray "
    "refuses it. max_congregation is that last size, derived from priest_shift "
    "and group_relief alone. A smallest own shift from the operator would turn "
    "the refusal into a floor and let a congregation grow without limit"
)

#: How a prayer's shift is told apart from the target's own life choices.
CHOICE_SEPARATION = (
    "the target's shift files under PRAYER_RECEIVED and every other score "
    "against that Vessel is its own. chosen_actions reads the Vessel's own run, "
    "received_prayers reads what was worked on it, and "
    "AlignmentLedger.alignment_of keeps adding both"
)

#: Which clock a prayer answers to. None does.
CLOCK_ABSENT = (
    "AlignmentLedger.score carries no turn and no timestamp, and no scored "
    "action decays, so a prayer's shift sits outside the world turn and the "
    "event turn together. A cadence is the one part that would need a clock"
)

#: What limits how often one target is prayed over. Nothing does.
CADENCE_ABSENT = (
    "nothing caps how many prayers one target takes, from one priest or from "
    "many. pvp_vote.VOTE_CADENCE_WORLD_TURNS is the shape a cap would take, and "
    "the operator sets the figure"
)

#: What holds a target's agreement to be prayed over. No record does.
CONSENT_ABSENT = "no record holds a target's consent, and pray asks for none"

#: Why ``PrayerRoll`` takes the praying classes as an argument.
PRIEST_CLASSES_ABSENT = (
    "no entry in rpg_classes.CLASSES is named priest, and the seven are "
    f"{', '.join(CLASS_NAMES)}. PrayerRoll takes may_pray, and the operator "
    "names which classes it holds"
)

#: What keeps the pair a prayer joined. Only the returned record does.
PRAYER_LINK_UNSTORED = (
    "PrayerRoll holds each Prayer in memory and writes no file. The ledger keeps "
    "both shifts and not the pair they joined, and a store shaped like "
    "action_spend.PoaRecordStore would keep the link"
)

#: What reads a prayer. Nothing does.
ABSENT_READERS: tuple[str, ...] = (
    "a priest ability",
    "a surface",
    "a consecrated place",
    "world polarity",
)

#: What each entry in ``ABSENT_READERS`` waits on.
ABSENT_READER_NOTES: dict[str, str] = {
    "a priest ability": (
        "skill_ladder holds one skill and no ability calls pray, so nothing in "
        "the running program prays"
    ),
    "a surface": "no tab or panel shows a prayer, a priest or an alignment",
    "a consecrated place": (
        "no module holds a place or its consecration, and the group figures a "
        "place would read are the same pair PrayerRates holds"
    ),
    "world polarity": (
        "alignment.world_alignment derives one and no module stores it, so a "
        "prayer's shift reaches no cataclysm"
    ),
}

_SHIFT_TYPES = (int, str, Decimal)


class PrayerError(RuntimeError):
    """Base for every refusal this module raises."""


class FigureAbsentError(PrayerError):
    """Raised by ``PrayerRates`` for a figure no source sets."""


class ShiftValueError(PrayerError):
    """Raised for a shift that is a float, not finite, or outside its range."""


class ShiftOrderError(PrayerError):
    """Raised when a priest's own shift is not strictly under the target's."""


class CongregationError(PrayerError):
    """Raised for an empty congregation, a repeated priest, or a size past the last."""


class EligibilityError(PrayerError):
    """Raised by ``PrayerRoll.pray`` for a class outside ``may_pray``."""


class SelfPrayerError(PrayerError):
    """Raised when a target shares an owner with any priest leading the prayer."""


class PoleAbsentError(PrayerError):
    """Raised by ``pole_of`` for an unscored or exactly balanced Vessel."""


class MixedPoleError(PrayerError):
    """Raised by ``congregation_pole`` when two priests read different poles."""


def _as_shift(value: object, name: str) -> Decimal:
    """Return ``value`` as a finite ``Decimal`` above zero, refusing ``float``."""
    part = _as_decimal(value, name)
    if part <= 0:
        raise ShiftValueError(f"{name} must be above zero, got {value!r}")
    return part


def _as_group_step(value: object, name: str) -> Decimal:
    """Return ``value`` as a finite ``Decimal`` of zero or more, refusing ``float``."""
    part = _as_decimal(value, name)
    if part < 0:
        raise ShiftValueError(
            f"{name} must be zero or more; a negative step would make a larger "
            f"congregation slower or dearer, got {value!r}",
        )
    return part


def _as_decimal(value: object, name: str) -> Decimal:
    """Return ``value`` as a finite ``Decimal``, refusing ``float`` and a bad string."""
    if value is FIGURE_ABSENT:
        raise FigureAbsentError(
            f"{name} is not set; {FIGURE_NOTES.get(name, 'the operator sets it')}",
        )
    if type(value) not in _SHIFT_TYPES:
        raise ShiftValueError(
            f"{name} must be int, str or Decimal, not {type(value).__name__}; "
            f"a shift between {POLES} decided by binary floating point is refused",
        )
    try:
        part = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ShiftValueError(f"{name} must be a number, got {value!r}") from exc
    if not part.is_finite():
        raise ShiftValueError(f"{name} must be finite, got {value!r}")
    return part


def _as_size(value: object, name: str) -> int:
    """Return ``value`` as an int of one or more, refusing ``bool`` and every float."""
    if type(value) is not int:
        raise CongregationError(
            f"{name} must be int, not {type(value).__name__}",
        )
    if value < 1:
        raise CongregationError(f"{name} must be one or more, got {value!r}")
    return value


@dataclass(frozen=True)
class PrayerRates:
    """The four figures one prayer needs, and the relations they must hold.

    ``target_shift`` is strictly above ``priest_shift``, and ``group_speedup``
    and ``group_relief`` are each zero or more.
    """

    target_shift: Decimal
    priest_shift: Decimal
    group_speedup: Decimal
    group_relief: Decimal

    def __post_init__(self) -> None:
        """Coerce the four figures and refuse a priest shift not under the target's."""
        object.__setattr__(
            self,
            "target_shift",
            _as_shift(self.target_shift, "target_shift"),
        )
        object.__setattr__(
            self,
            "priest_shift",
            _as_shift(self.priest_shift, "priest_shift"),
        )
        object.__setattr__(
            self,
            "group_speedup",
            _as_group_step(self.group_speedup, "group_speedup"),
        )
        object.__setattr__(
            self,
            "group_relief",
            _as_group_step(self.group_relief, "group_relief"),
        )
        if self.priest_shift >= self.target_shift:
            raise ShiftOrderError(
                f"priest_shift {self.priest_shift} is not under target_shift "
                f"{self.target_shift}; {SHIFT_ORDERING}",
            )

    @property
    def max_congregation(self) -> int | None:
        """The last size ``priest_shift_at`` holds above zero, absent with no relief."""
        if self.group_relief == 0:
            return FIGURE_ABSENT
        try:
            whole, rest = divmod(self.priest_shift, self.group_relief)
        except (InvalidOperation, ArithmeticError) as exc:
            raise ShiftValueError(
                f"priest_shift {self.priest_shift} over group_relief "
                f"{self.group_relief} does not divide in this context: {exc}",
            ) from exc
        steps = int(whole) if rest > 0 else int(whole) - 1
        return steps + 1

    def target_shift_at(self, congregation: object) -> Decimal:
        """Return the shift the target takes from ``congregation`` priests at once."""
        size = _as_size(congregation, "congregation")
        return self.target_shift + self.group_speedup * (size - 1)

    def priest_shift_at(self, congregation: object) -> Decimal:
        """Return the shift each priest takes from ``congregation`` priests at once."""
        size = _as_size(congregation, "congregation")
        return self.priest_shift - self.group_relief * (size - 1)

    def to_dict(self) -> dict:
        """Return these rates as a JSON-safe dict, every amount a plain string."""
        return {
            "target_shift": str(self.target_shift),
            "priest_shift": str(self.priest_shift),
            "group_speedup": str(self.group_speedup),
            "group_relief": str(self.group_relief),
            "max_congregation": self.max_congregation,
            "shift_ordering": SHIFT_ORDERING,
            "group_floor": GROUP_FLOOR,
        }


def prayer_shifts(rates: object, congregation: object) -> tuple[Decimal, Decimal]:
    """Return the target's shift and each priest's own at ``congregation``.

    ``require_shift_relations`` runs first, so a pair that breaches
    ``SHIFT_ORDERING`` is never returned.
    """
    if not isinstance(rates, PrayerRates):
        raise PrayerError(f"a PrayerRates was expected, got {type(rates).__name__}")
    size = _as_size(congregation, "congregation")
    require_shift_relations(rates, size)
    return (rates.target_shift_at(size), rates.priest_shift_at(size))


def require_shift_relations(rates: object, congregation: object) -> None:
    """Refuse ``congregation`` unless ``rates`` holds all of ``SHIFT_ORDERING``."""
    if not isinstance(rates, PrayerRates):
        raise PrayerError(f"a PrayerRates was expected, got {type(rates).__name__}")
    size = _as_size(congregation, "congregation")
    own = rates.priest_shift_at(size)
    moved = rates.target_shift_at(size)
    if own <= 0:
        raise CongregationError(
            f"{size} priests reduce each own shift to {own}, which scores "
            f"nothing; {rates.max_congregation} is the last size that files. "
            f"{GROUP_FLOOR}",
        )
    if own >= moved:
        raise ShiftOrderError(
            f"at {size} priests the own shift {own} is not under the target's "
            f"{moved}; {SHIFT_ORDERING}",
        )
    if size == 1:
        return
    smaller = size - 1
    if moved < rates.target_shift_at(smaller):
        raise ShiftOrderError(
            f"{size} priests move the target {moved} where {smaller} move "
            f"{rates.target_shift_at(smaller)}; a larger congregation is never "
            f"slower",
        )
    if own > rates.priest_shift_at(smaller):
        raise ShiftOrderError(
            f"{size} priests each pay {own} where {smaller} each pay "
            f"{rates.priest_shift_at(smaller)}; a larger congregation never "
            f"costs a priest more",
        )


def pole_of(ledger: object, vessel: object) -> str:
    """Return the pole ``ledger`` reads for ``vessel``, refusing an absent reading."""
    if not isinstance(ledger, AlignmentLedger):
        raise PrayerError(
            f"an AlignmentLedger was expected, got {type(ledger).__name__}",
        )
    standing = ledger.alignment_of(vessel)
    key = vessel_key(vessel)
    if not standing.is_scored:
        raise PoleAbsentError(
            f"{key[0]} {key[1]} has no scored action, so it reads no pole and "
            f"carries no alignment to pray",
        )
    # net_creation carries the sign polarity does, with no division by scored_total.
    reading = standing.net_creation
    if reading == NEUTRAL:
        raise PoleAbsentError(
            f"{key[0]} {key[1]} reads exactly {NEUTRAL}, which names neither of "
            f"{POLES}, so it carries no alignment to pray",
        )
    return CREATION if reading > NEUTRAL else DESTRUCTION


def congregation_pole(ledger: object, priests: Sequence[object]) -> str:
    """Return the one pole every Vessel in ``priests`` reads, refusing a mixed set."""
    held = tuple(priests)
    if not held:
        raise CongregationError("a prayer needs at least one priest, got none")
    poles = tuple(pole_of(ledger, priest) for priest in held)
    if len(set(poles)) > 1:
        named = ", ".join(
            f"{vessel_key(priest)[1]} reads {pole}"
            for priest, pole in zip(held, poles, strict=True)
        )
        raise MixedPoleError(
            f"priests praying together hold one pole; {named}",
        )
    return poles[0]


def shift_parts(direction: str, shift: Decimal) -> tuple[Decimal, Decimal]:
    """Return ``shift`` as the creation and destruction parts ``direction`` names."""
    if direction == CREATION:
        return (shift, Decimal(0))
    if direction == DESTRUCTION:
        return (Decimal(0), shift)
    raise PrayerError(f"direction must be one of {POLES}, got {direction!r}")


def received_prayers(ledger: object, vessel: object) -> tuple[ActionScore, ...]:
    """Every score against ``vessel`` filed under ``PRAYER_RECEIVED``."""
    if not isinstance(ledger, AlignmentLedger):
        raise PrayerError(
            f"an AlignmentLedger was expected, got {type(ledger).__name__}",
        )
    return tuple(
        score
        for score in ledger.actions_of(vessel)
        if score.action == PRAYER_RECEIVED
    )


def chosen_actions(ledger: object, vessel: object) -> tuple[ActionScore, ...]:
    """Every score against ``vessel`` that no other Vessel's prayer worked on it."""
    if not isinstance(ledger, AlignmentLedger):
        raise PrayerError(
            f"an AlignmentLedger was expected, got {type(ledger).__name__}",
        )
    return tuple(
        score
        for score in ledger.actions_of(vessel)
        if score.action != PRAYER_RECEIVED
    )


def alignment_from_choices(ledger: object, vessel: object) -> Alignment:
    """Read ``vessel``'s alignment over ``chosen_actions`` alone."""
    return alignment_from_scores(chosen_actions(ledger, vessel))


def alignment_from_prayers(ledger: object, vessel: object) -> Alignment:
    """Read ``vessel``'s alignment over ``received_prayers`` alone."""
    return alignment_from_scores(received_prayers(ledger, vessel))


@dataclass(frozen=True)
class Prayer:
    """One prayer: the priests that led it, the target, and the two shifts it filed.

    ``direction`` is the pole every priest read and ``congregation`` counts the
    priests that led it.
    """

    target: object
    priests: tuple
    direction: str
    congregation: int
    target_shift: Decimal
    priest_shift: Decimal
    target_score: ActionScore
    priest_scores: tuple[ActionScore, ...]

    @property
    def target_key(self) -> tuple[str, str, str]:
        """The key ``AlignmentLedger`` filed the target's shift under."""
        return vessel_key(self.target)

    @property
    def priest_keys(self) -> tuple[tuple[str, str, str], ...]:
        """One key a priest, in the order the prayer named them."""
        return tuple(vessel_key(priest) for priest in self.priests)

    def to_dict(self) -> dict:
        """Return this prayer as a JSON-safe dict, every amount a plain string."""
        return {
            "direction": self.direction,
            "congregation": self.congregation,
            "target": list(self.target_key),
            "priests": [list(key) for key in self.priest_keys],
            "target_shift": str(self.target_shift),
            "priest_shift": str(self.priest_shift),
            "target_score": self.target_score.to_dict(),
            "priest_scores": [score.to_dict() for score in self.priest_scores],
            "target_kind": PLAYER_TARGET,
        }


class PrayerRoll:
    """Every prayer offered, each one filed against one ``AlignmentLedger``.

    ``may_pray`` names the classes a priest may hold and ``pray`` refuses every
    other class.
    """

    def __init__(self, ledger: object, may_pray: Iterable[str]) -> None:
        """Hold ``ledger`` and the ``may_pray`` names, refusing an unknown class."""
        if not isinstance(ledger, AlignmentLedger):
            raise PrayerError(
                f"an AlignmentLedger was expected, got {type(ledger).__name__}",
            )
        named = tuple(may_pray)
        for name in named:
            if class_named(name) is None:
                raise EligibilityError(
                    f"{name!r} is not a PoA class; the seven are "
                    f"{', '.join(CLASS_NAMES)}. {PRIEST_CLASSES_ABSENT}",
                )
        self._ledger: AlignmentLedger = ledger
        self._may_pray: tuple[str, ...] = named
        self._prayers: list[Prayer] = []

    @property
    def ledger(self) -> AlignmentLedger:
        """The ledger ``pray`` scores both shifts against."""
        return self._ledger

    @property
    def may_pray(self) -> tuple[str, ...]:
        """The class names this roll admits as priests."""
        return self._may_pray

    @property
    def prayer_count(self) -> int:
        """How many prayers this roll has filed."""
        return len(self._prayers)

    def prayers(self) -> tuple[Prayer, ...]:
        """Every prayer filed, in the order ``pray`` filed them."""
        return tuple(self._prayers)

    def prayers_over(self, vessel: object) -> tuple[Prayer, ...]:
        """Every prayer filed against ``vessel`` as the target."""
        key = vessel_key(vessel)
        return tuple(
            prayer for prayer in self._prayers if prayer.target_key == key
        )

    def prayers_led_by(self, vessel: object) -> tuple[Prayer, ...]:
        """Every prayer ``vessel`` was one of the priests on."""
        key = vessel_key(vessel)
        return tuple(
            prayer for prayer in self._prayers if key in prayer.priest_keys
        )

    def pray(
        self,
        priests: Sequence[object],
        target: object,
        rates: object,
    ) -> Prayer:
        """File one prayer, shifting ``target`` toward the pole ``priests`` read.

        Every priest takes the same smaller shift in that direction, and
        ``require_shift_relations`` refuses a size ``rates`` cannot carry.
        """
        held = tuple(priests)
        if not held:
            raise CongregationError("a prayer needs at least one priest, got none")
        priest_keys = tuple(vessel_key(priest) for priest in held)
        if len(set(priest_keys)) != len(priest_keys):
            raise CongregationError(
                f"one Vessel holds one place in a congregation; {priest_keys} "
                f"names {len(priest_keys) - len(set(priest_keys))} twice",
            )
        for key in priest_keys:
            if key[1] not in self._may_pray:
                raise EligibilityError(
                    f"{key[1]} is not on this roll's may_pray "
                    f"{self._may_pray}; {PRIEST_CLASSES_ABSENT}",
                )
        target_key = vessel_key(target)
        owners = {key[0] for key in priest_keys}
        if target_key[0] in owners:
            raise SelfPrayerError(
                f"{target_key[0]} owns both the target {target_key[1]} and a "
                f"priest on this prayer; a prayer shifts another player",
            )
        direction = congregation_pole(self._ledger, held)
        size = len(held)
        # Every refusal runs before the first score, so no prayer half-files a pair.
        target_shift, priest_shift = prayer_shifts(rates, size)
        target_creation, target_destruction = shift_parts(direction, target_shift)
        priest_creation, priest_destruction = shift_parts(direction, priest_shift)
        target_score = self._ledger.score(
            target,
            PRAYER_RECEIVED,
            target_creation,
            target_destruction,
        )
        priest_scores = tuple(
            self._ledger.score(
                priest,
                PRAYER_LED,
                priest_creation,
                priest_destruction,
            )
            for priest in held
        )
        filed = Prayer(
            target,
            held,
            direction,
            size,
            target_shift,
            priest_shift,
            target_score,
            priest_scores,
        )
        self._prayers.append(filed)
        logger.info(
            "%d priests prayed %s over %s %s, shifting it %s and each of them "
            "%s; the target now reads polarity %s and the first priest %s",
            size,
            direction,
            target_key[0],
            target_key[1],
            target_shift,
            priest_shift,
            self._ledger.alignment_of(target).polarity,
            self._ledger.alignment_of(held[0]).polarity,
        )
        return filed

    def rows(self) -> list[dict]:
        """One row a prayer, in the order ``pray`` filed them."""
        return [prayer.to_dict() for prayer in self._prayers]

    def to_dict(self) -> dict:
        """Return this roll as a dict, one entry a prayer, with what is owed."""
        return {
            "prayer_count": self.prayer_count,
            "may_pray": list(self._may_pray),
            "prayers": self.rows(),
            "target_kinds": list(TARGET_KINDS),
            "place_target_owed": PLACE_TARGET_OWED,
            "figures_owed": list(FIGURES_OWED),
            "figure_notes": dict(FIGURE_NOTES),
            "shift_ordering": SHIFT_ORDERING,
            "shift_not_polarity": SHIFT_NOT_POLARITY,
            "group_floor": GROUP_FLOOR,
            "choice_separation": CHOICE_SEPARATION,
            "clock_absent": CLOCK_ABSENT,
            "cadence_absent": CADENCE_ABSENT,
            "consent_absent": CONSENT_ABSENT,
            "priest_classes_absent": PRIEST_CLASSES_ABSENT,
            "prayer_link_unstored": PRAYER_LINK_UNSTORED,
            "absent_readers": list(ABSENT_READERS),
            "absent_reader_notes": dict(ABSENT_READER_NOTES),
        }


def require_prayer_rules() -> None:
    """Drive the zero-shift refusal ``max_congregation`` rests on, and log the gaps.

    ``ActionScore`` refusing a score of zero on both poles is what lets
    ``require_shift_relations`` cap a congregation.
    """
    try:
        ActionScore(PRAYER_RECEIVED, Decimal(0), Decimal(0))
    except RatioError:
        pass
    else:
        raise PrayerError(
            f"ActionScore accepted a shift of zero on both poles, so "
            f"max_congregation rests on nothing; {GROUP_FLOOR}",
        )
    logger.info(
        "a prayer writes %s on its target and %s on each priest, %d figures are "
        "absent (%s), and %d readers are absent: %s",
        PRAYER_RECEIVED,
        PRAYER_LED,
        len(FIGURES_OWED),
        ", ".join(FIGURES_OWED),
        len(ABSENT_READERS),
        ", ".join(ABSENT_READERS),
    )


require_prayer_rules()
