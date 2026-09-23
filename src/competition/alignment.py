"""The Creation-to-Destruction scale, and the alignment a Vessel accumulates.

``ActionScore`` carries one action's ratio and ``Alignment`` adds every score a
Vessel has taken, so ``AlignmentLedger.alignment_of`` answers one Vessel and
``UNSCORED`` answers a Vessel no action has touched. ``guild_alignment`` adds the
Vessels of a ``Guild``'s members and ``world_alignment`` adds every guild a
``GuildRoster`` holds. ``NEUTRAL`` is the middle of the scale, ``NEUTRAL_BAND``
is absent, and ``ABSENT_READERS`` names what reads none of this.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from .guild_roster import Guild, GuildRoster
from .vessels import Vessel

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger("acervator.alignment")

CREATION = "creation"
DESTRUCTION = "destruction"

#: The two poles a ratio divides between. There is no third pole.
POLES: tuple[str, ...] = (CREATION, DESTRUCTION)

#: The middle of the scale. A net of this against any scored total reads balanced.
NEUTRAL = Decimal(0)

#: The polarity of a score that is all Creation.
FULL_CREATION = Decimal(1)

#: The polarity of a score that is all Destruction.
FULL_DESTRUCTION = Decimal(-1)

#: A figure no source sets. Its own note says what would set it.
FIGURE_ABSENT = None

#: What ``Alignment.polarity`` reads when no action has been scored.
POLARITY_ABSENT = None

#: How far from ``NEUTRAL`` a total sits and still reads neutral. No figure sets it.
NEUTRAL_BAND = FIGURE_ABSENT

#: What ``NEUTRAL_BAND`` owes, and what naming it buys.
NEUTRAL_BAND_NOTE = (
    "the width around NEUTRAL a total reads as neutral within. No figure names "
    "one. Exact balance needs no width: is_exactly_balanced answers a net of "
    "NEUTRAL against a scored total above zero. A band is what a three-way "
    "naming of a world's polarity would need, and the operator sets it"
)

#: Nothing removes a scored action from a total. Alignment does not decay.
DECAY_ABSENT = (
    "no scored action is ever dropped from a total, and no clock reduces one. "
    "Alignment is every action a Vessel has taken, for the Vessel's whole life"
)

#: Offsetting is open. Many light Creation scores cancel one heavy Destruction score.
OFFSETTING_OPEN = (
    "net_creation is a plain sum, so a thousand scores of 1 Creation cancel one "
    "score of 1000 Destruction and the pair reads exactly balanced. "
    "scored_total keeps the weight both sides carried, which separates a Vessel "
    "that has done much from one that has done little at the same polarity"
)

#: What a Vessel's alignment files under. ``level`` is left out of the key.
VESSEL_KEY_FIELDS: tuple[str, ...] = ("owner", "class_name", "vessel_id")

#: What the key separates, and the one move it still does not carry a record across.
VESSEL_ID_OWED = (
    "vessels.Vessel.record_key carries the vessel_id, so two Vessels of one "
    "class under one owner hold two keys and two alignments, and level is left "
    "out of the key so a level gained keeps the alignment the Vessel earned. "
    "The owner is still in the key, so domination.steal_vessel moves a taken "
    "Vessel to a new key and the scored actions stay under the victim's. A key "
    "of the vessel_id alone would carry them across, and it would leave "
    "alignment_of_address and unguilded_addresses no owner to read"
)

#: What the roll-up cannot reach, measured on ``GuildRoster.guild_of``.
UNGUILDED_PATH_ABSENT = (
    "GuildRoster.guild_of answers None for an address in no guild, so an "
    "unguilded Vessel's scores reach guild_alignment nowhere and reach "
    "world_alignment nowhere. The chain runs Vessel, Guild, World and has no "
    "step for a player outside every guild"
)

#: What ties a ``GuildRoster`` to one world. No module does.
WORLD_TIE_ABSENT = (
    "no module ties a GuildRoster to a world_grid world, so world_alignment "
    "reads the guilds one roster holds and takes the world on trust"
)

#: What reads an alignment. Nothing does.
ABSENT_READERS: tuple[str, ...] = (
    "cataclysms",
    "world polarity",
    "abilities",
    "combat",
    "necromancy",
    "energy vampirism",
    "a surface",
)

#: What each entry in ``ABSENT_READERS`` waits on.
ABSENT_READER_NOTES: dict[str, str] = {
    "cataclysms": "no module names a cataclysm, so nothing reads a world's polarity",
    "world polarity": "world_alignment derives one and no module stores or shows it",
    "abilities": "skill_ladder holds one skill, and no ability carries a ratio",
    "combat": "nothing resolves a fight, so no fight scores an action",
    "necromancy": "no skill exists to score, and the operator sets its ratio",
    "energy vampirism": "no skill exists to score, and the operator sets its ratio",
    "a surface": "no tab or panel shows an alignment at any of the three levels",
}

#: What no action yet carries, and who sets it.
RATIO_SOURCE = (
    "an action's ratio of Creation to Destruction arrives with the action. This "
    "module holds no table of ratios and assigns none. The one action the "
    "package builds is skill_ladder's Quintessence Transfer, and whether a "
    "transfer scores at all is the operator's ruling"
)

#: Why the monster nature axis is a separate axis, measured on ``monster_table``.
MONSTER_AXIS_SEPARATE: tuple[str, ...] = (
    (
        "MonsterTier refuses depth 0 and DIRECTIONS names no zero, and this "
        "scale needs NEUTRAL at the middle"
    ),
    (
        "the decan rank at depth -3 is invoked to heal, which is no Destruction "
        "position below the plane"
    ),
    (
        "depth -5 is marked the only morally wicked tier, and everything above "
        "it is indifferent"
    ),
    (
        "the Watchers sit at depth -5 and in ASCENDING_FAMILIES, so one family "
        "holds two positions"
    ),
    (
        "PLACEMENT_RULE is absent, so nothing places an arbitrary creature and "
        "nothing could score an arbitrary action from it"
    ),
)


class AlignmentError(RuntimeError):
    """Base for every refusal this module raises."""


class RatioError(AlignmentError):
    """Raised by ``ActionScore`` for a bad part, a float, or a zero scored total."""


class VesselKeyError(AlignmentError):
    """Raised by ``vessel_key`` for anything that is not a ``Vessel``."""


class ScaleError(AlignmentError):
    """Raised by ``require_alignment_scale`` when an anchor leaves the scale."""


_RATIO_TYPES = (int, str, Decimal)


def _as_ratio_part(value: object, name: str) -> Decimal:
    """Return ``value`` as a finite ``Decimal`` of zero or more, refusing ``float``."""
    if type(value) not in _RATIO_TYPES:
        raise RatioError(
            f"{name} must be int, str or Decimal, not {type(value).__name__}; "
            f"a ratio between {POLES} decided by binary floating point is refused",
        )
    try:
        part = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise RatioError(f"{name} must be a number, got {value!r}") from exc
    if not part.is_finite() or part < 0:
        raise RatioError(f"{name} must be finite and zero or more, got {value!r}")
    return part


def _as_action_name(value: object) -> str:
    """Return ``value`` as a non-blank action name; every other value raises."""
    if type(value) is not str or not value.strip():
        raise RatioError(f"action must be a non-empty name, got {value!r}")
    return value


def vessel_key(vessel: object) -> tuple[str, str, str]:
    """Return the ``VESSEL_KEY_FIELDS`` triple one Vessel's alignment files under.

    The triple is ``Vessel.record_key``, which ``inventory.vessel_key`` and
    ``crafting.craft_id_for`` join, so no second key shape is built by hand.
    """
    if not isinstance(vessel, Vessel):
        raise VesselKeyError(
            f"a Vessel was expected, got {type(vessel).__name__}; {VESSEL_ID_OWED}",
        )
    return vessel.record_key


@dataclass(frozen=True)
class ActionScore:
    """One action, and the ratio of Creation to Destruction it carried.

    ``net_creation`` takes ``destruction`` off ``creation`` and ``scored_total``
    adds both, so ``polarity`` runs ``FULL_DESTRUCTION`` to ``FULL_CREATION``.
    """

    action: str
    creation: Decimal
    destruction: Decimal

    def __post_init__(self) -> None:
        """Coerce both parts, refusing a blank ``action`` and a zero ratio."""
        object.__setattr__(self, "action", _as_action_name(self.action))
        object.__setattr__(self, CREATION, _as_ratio_part(self.creation, CREATION))
        object.__setattr__(
            self,
            DESTRUCTION,
            _as_ratio_part(self.destruction, DESTRUCTION),
        )
        if self.scored_total == 0:
            raise RatioError(
                f"{self.action} carries no {CREATION} and no {DESTRUCTION}, so it "
                f"names no ratio and scores nothing",
            )

    @property
    def net_creation(self) -> Decimal:
        """``creation`` less ``destruction``, above ``NEUTRAL`` toward Creation."""
        return self.creation - self.destruction

    @property
    def scored_total(self) -> Decimal:
        """``creation`` and ``destruction`` added, the weight this action carries."""
        return self.creation + self.destruction

    @property
    def polarity(self) -> Decimal:
        """``net_creation`` over ``scored_total``, on the gradient between the poles."""
        return self.net_creation / self.scored_total

    def to_dict(self) -> dict:
        """Return this score as a JSON-safe dict, every amount a plain string."""
        return {
            "action": self.action,
            CREATION: str(self.creation),
            DESTRUCTION: str(self.destruction),
            "net_creation": str(self.net_creation),
            "scored_total": str(self.scored_total),
            "polarity": str(self.polarity),
        }


@dataclass(frozen=True)
class Alignment:
    """Every scored action added, read at a Vessel, a guild or a world.

    ``scored_actions`` counts what went in, and ``polarity`` reads
    ``POLARITY_ABSENT`` while that count is zero.
    """

    scored_actions: int
    creation: Decimal
    destruction: Decimal

    @property
    def net_creation(self) -> Decimal:
        """``creation`` less ``destruction``, above ``NEUTRAL`` toward Creation."""
        return self.creation - self.destruction

    @property
    def scored_total(self) -> Decimal:
        """``creation`` and ``destruction`` added over every action scored."""
        return self.creation + self.destruction

    @property
    def is_scored(self) -> bool:
        """Whether any action has been scored against this alignment."""
        return self.scored_actions > 0

    @property
    def polarity(self) -> Decimal | None:
        """``net_creation`` over ``scored_total``, absent while nothing is scored."""
        if not self.is_scored:
            return POLARITY_ABSENT
        return self.net_creation / self.scored_total

    @property
    def is_exactly_balanced(self) -> bool:
        """Whether actions have been scored and ``net_creation`` is ``NEUTRAL``."""
        return self.is_scored and self.net_creation == NEUTRAL

    def to_dict(self) -> dict:
        """Return this alignment as a dict, an absent polarity its own literal."""
        reading = self.polarity
        return {
            "scored_actions": self.scored_actions,
            CREATION: str(self.creation),
            DESTRUCTION: str(self.destruction),
            "net_creation": str(self.net_creation),
            "scored_total": str(self.scored_total),
            "polarity": POLARITY_ABSENT if reading is None else str(reading),
            "is_scored": self.is_scored,
            "is_exactly_balanced": self.is_exactly_balanced,
            "neutral_band": NEUTRAL_BAND,
            "neutral_band_note": NEUTRAL_BAND_NOTE,
        }


#: What a Vessel reads before any action of its own has been scored.
UNSCORED = Alignment(0, Decimal(0), Decimal(0))


def alignment_from_scores(scores: Iterable[ActionScore]) -> Alignment:
    """Add every ``ActionScore`` in ``scores``, ``UNSCORED`` for an empty run."""
    held = tuple(scores)
    for score in held:
        if not isinstance(score, ActionScore):
            raise RatioError(
                f"an ActionScore was expected, got {type(score).__name__}",
            )
    if not held:
        return UNSCORED
    return Alignment(
        len(held),
        sum((score.creation for score in held), Decimal(0)),
        sum((score.destruction for score in held), Decimal(0)),
    )


def total_alignment(parts: Iterable[Alignment]) -> Alignment:
    """Add every ``Alignment`` in ``parts``, ``UNSCORED`` for an empty run."""
    held = tuple(parts)
    for part in held:
        if not isinstance(part, Alignment):
            raise AlignmentError(
                f"an Alignment was expected, got {type(part).__name__}",
            )
    if not held:
        return UNSCORED
    return Alignment(
        sum(part.scored_actions for part in held),
        sum((part.creation for part in held), Decimal(0)),
        sum((part.destruction for part in held), Decimal(0)),
    )


class AlignmentLedger:
    """Every ``ActionScore`` each Vessel has taken, filed under ``vessel_key``.

    ``score`` appends one and ``alignment_of`` folds a Vessel's own run through
    ``alignment_from_scores``, so no stored total can drift from its actions.
    """

    def __init__(self) -> None:
        """Open an empty ledger, holding no Vessel and no score."""
        self._scores: dict[tuple[str, str, str], list[ActionScore]] = {}

    @property
    def vessel_count(self) -> int:
        """How many Vessels this ledger has scored an action against."""
        return len(self._scores)

    @property
    def scored_action_count(self) -> int:
        """How many scores this ledger holds over every Vessel."""
        return sum(len(run) for run in self._scores.values())

    def score(
        self,
        vessel: object,
        action: object,
        creation: object,
        destruction: object,
    ) -> ActionScore:
        """Score one action against ``vessel`` at the ratio the caller names."""
        key = vessel_key(vessel)
        entry = ActionScore(
            _as_action_name(action),
            _as_ratio_part(creation, CREATION),
            _as_ratio_part(destruction, DESTRUCTION),
        )
        self._scores.setdefault(key, []).append(entry)
        running = self.alignment_of(vessel)
        logger.info(
            "%s %s %s scored %s at %s %s to %s %s, and now reads %s over %s at "
            "polarity %s across %d actions",
            key[0],
            key[1],
            key[2],
            entry.action,
            entry.creation,
            CREATION,
            entry.destruction,
            DESTRUCTION,
            running.net_creation,
            running.scored_total,
            running.polarity,
            running.scored_actions,
        )
        return entry

    def actions_of(self, vessel: object) -> tuple[ActionScore, ...]:
        """Every score against ``vessel``, in the order they were scored."""
        return tuple(self._scores.get(vessel_key(vessel), ()))

    def alignment_of(self, vessel: object) -> Alignment:
        """Read ``vessel``'s own alignment, ``UNSCORED`` while nothing has scored it."""
        return alignment_from_scores(self.actions_of(vessel))

    def alignment_of_address(self, address: object) -> Alignment:
        """Add every Vessel ``address`` owns, across every class it has scored."""
        owner = self._as_owner(address)
        return total_alignment(
            alignment_from_scores(run)
            for key, run in self._scores.items()
            if key[0] == owner
        )

    def guild_alignment(self, guild: object) -> Alignment:
        """Add the Vessels of every member a ``Guild`` holds, informing the guild."""
        if not isinstance(guild, Guild):
            raise AlignmentError(
                f"a Guild was expected, got {type(guild).__name__}",
            )
        reading = total_alignment(
            self.alignment_of_address(member) for member in guild.members
        )
        logger.info(
            "guild %s reads %s over %s at polarity %s from %d members",
            guild.key,
            reading.net_creation,
            reading.scored_total,
            reading.polarity,
            guild.member_count,
        )
        return reading

    def world_alignment(self, roster: object) -> Alignment:
        """Add every guild a ``GuildRoster`` holds, defining the world's alignment."""
        if not isinstance(roster, GuildRoster):
            raise AlignmentError(
                f"a GuildRoster was expected, got {type(roster).__name__}",
            )
        reading = total_alignment(
            self.guild_alignment(guild) for guild in roster.guilds()
        )
        outside = self.unguilded_addresses(roster)
        logger.info(
            "the world reads %s over %s at polarity %s from %d guilds, and %d "
            "scored addresses reach it nowhere: %s",
            reading.net_creation,
            reading.scored_total,
            reading.polarity,
            roster.guild_count,
            len(outside),
            UNGUILDED_PATH_ABSENT,
        )
        return reading

    def unguilded_addresses(self, roster: object) -> tuple[str, ...]:
        """Every scored owner ``GuildRoster.guild_of`` answers None for."""
        if not isinstance(roster, GuildRoster):
            raise AlignmentError(
                f"a GuildRoster was expected, got {type(roster).__name__}",
            )
        owners = sorted({key[0] for key in self._scores})
        return tuple(owner for owner in owners if roster.guild_of(owner) is None)

    def rows(self) -> list[dict]:
        """One row a Vessel, carrying its key, its alignment and its scores."""
        return [
            {
                "owner": owner,
                "class_name": class_name,
                "vessel_id": vessel_id,
                "alignment": alignment_from_scores(run).to_dict(),
                "actions": [score.to_dict() for score in run],
            }
            for (owner, class_name, vessel_id), run in sorted(self._scores.items())
        ]

    def to_dict(self) -> dict:
        """Return this ledger as a dict, one entry a Vessel, with what is owed."""
        return {
            "vessel_count": self.vessel_count,
            "scored_action_count": self.scored_action_count,
            "vessels": self.rows(),
            "vessel_key_fields": list(VESSEL_KEY_FIELDS),
            "vessel_id_owed": VESSEL_ID_OWED,
            "decay_absent": DECAY_ABSENT,
            "offsetting_open": OFFSETTING_OPEN,
            "ratio_source": RATIO_SOURCE,
            "unguilded_path_absent": UNGUILDED_PATH_ABSENT,
            "world_tie_absent": WORLD_TIE_ABSENT,
            "absent_readers": list(ABSENT_READERS),
            "absent_reader_notes": dict(ABSENT_READER_NOTES),
            "monster_axis_separate": list(MONSTER_AXIS_SEPARATE),
        }

    def _as_owner(self, value: object) -> str:
        """Return ``value`` as a non-blank owner address; every other value raises."""
        if type(value) is not str or not value.strip():
            raise AlignmentError(f"owner must be a non-empty address, got {value!r}")
        return value


def require_alignment_scale() -> None:
    """Drive the anchors of the scale and log what this module holds and lacks."""
    pure_creation = ActionScore("all Creation", Decimal(1), Decimal(0))
    pure_destruction = ActionScore("all Destruction", Decimal(0), Decimal(1))
    if pure_creation.polarity != FULL_CREATION:
        raise ScaleError(
            f"a score of all {CREATION} reads {pure_creation.polarity}; "
            f"{FULL_CREATION} is the pole",
        )
    if pure_destruction.polarity != FULL_DESTRUCTION:
        raise ScaleError(
            f"a score of all {DESTRUCTION} reads {pure_destruction.polarity}; "
            f"{FULL_DESTRUCTION} is the pole",
        )
    balanced = alignment_from_scores((pure_creation, pure_destruction))
    if balanced.polarity != NEUTRAL or not balanced.is_exactly_balanced:
        raise ScaleError(
            f"a balanced pair reads {balanced.polarity} and "
            f"is_exactly_balanced {balanced.is_exactly_balanced}; "
            f"{NEUTRAL} and True were expected",
        )
    if UNSCORED.polarity is not POLARITY_ABSENT or UNSCORED.is_exactly_balanced:
        raise ScaleError(
            f"UNSCORED reads polarity {UNSCORED.polarity} and "
            f"is_exactly_balanced {UNSCORED.is_exactly_balanced}; an unscored "
            f"Vessel and a balanced one must read apart",
        )
    logger.info(
        "the scale runs %s to %s with %s at the middle, the neutral band is %s, "
        "and %d readers are absent: %s",
        FULL_DESTRUCTION,
        FULL_CREATION,
        NEUTRAL,
        NEUTRAL_BAND,
        len(ABSENT_READERS),
        ", ".join(ABSENT_READERS),
    )


require_alignment_scale()
