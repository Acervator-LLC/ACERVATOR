"""The incapacitated state a taking needs, and the two forms a taking takes.

``IncapacitationRegister.set_health`` marks ``KIND_PHYSICAL`` at
``HEALTH_AT_ZERO`` and ``apply_mental`` marks ``KIND_MENTAL``, so
``condition_of`` reads ``CONDITION_INCAPACITATED`` for either kind and
``CONDITION_ABLE`` for neither. ``take_control`` and ``steal_vessel`` both run
``require_taking_permitted``, which reads ``pvp_vote.may_destroy``, and
``steal_vessel`` alone moves ``Vessel.owner``. ``dilution_at`` reads one
address's ``Potential`` across a taking and ``ABILITY_ABSENT`` names what invokes
either form.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from .alignment import ActionScore, AlignmentLedger, vessel_key
from .entity_stats import Potential
from .pvp_vote import PvpLock, PvpMode, may_destroy
from .quintessence_ledger import amount_text
from .rpg_classes import CLASS_NAMES
from .vessels import Reincarnate, Vessel

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger("acervator.domination")

#: What ``condition_of`` reads for a Vessel no register has marked.
CONDITION_ABLE = "able"

#: The one condition a taking needs. His rule gates on it and names no cause.
CONDITION_INCAPACITATED = "incapacitated"

#: Every condition a Vessel reads. No third condition exists.
CONDITIONS: tuple[str, ...] = (CONDITION_ABLE, CONDITION_INCAPACITATED)

#: His first cause, a body at its end.
KIND_PHYSICAL = "physical"

#: His second cause, a mind compromised.
KIND_MENTAL = "mental"

#: Both kinds he named. A taking reads either one and asks for neither.
INCAPACITATION_KINDS: tuple[str, ...] = (KIND_PHYSICAL, KIND_MENTAL)

#: The one health reading that sets ``KIND_PHYSICAL``.
HEALTH_AT_ZERO = Decimal(0)

#: What ``Incapacitation.cause`` reads for a Vessel at ``HEALTH_AT_ZERO``.
CAUSE_HEALTH_AT_ZERO = "health at zero"

#: The one mental effect he named. ``MENTAL_EFFECTS`` holds the class.
MENTAL_EFFECT_DAZE = "daze"

#: Every named member of the mental class, which his own words leave open.
MENTAL_EFFECTS: tuple[str, ...] = (MENTAL_EFFECT_DAZE,)

#: The form that leaves ``Vessel.owner`` alone, his temporary control.
TAKING_CONTROL = "control"

#: The form that moves ``Vessel.owner``, his literal steal.
TAKING_THEFT = "theft"

#: Both forms, in the order his sentence names them.
TAKING_FORMS: tuple[str, ...] = (TAKING_CONTROL, TAKING_THEFT)

#: The action name ``score_taking`` files a ``TAKING_CONTROL`` under.
ACTION_CONTROL = "temporary control of another player's Vessel"

#: The action name ``score_taking`` files a ``TAKING_THEFT`` under.
ACTION_THEFT = "theft of another player's Vessel"

#: Both action names, one a form, in the order of ``TAKING_FORMS``.
ACTION_NAMES: dict[str, str] = {
    TAKING_CONTROL: ACTION_CONTROL,
    TAKING_THEFT: ACTION_THEFT,
}

#: The level ``require_taking_dilutes_the_thief`` drives every Vessel at.
DRIVEN_LEVEL = 12

#: The one balance ``require_taking_dilutes_the_thief`` reads both sides against.
DRIVEN_BALANCE = Decimal(100)

#: The health above ``HEALTH_AT_ZERO`` the driven refusal reads. No figure caps it.
DRIVEN_HEALTH = Decimal(1)

#: The end one driven ``Incapacitation`` carries, standing in for an ability's.
DRIVEN_END_WORLD_TURN = 1

#: What invokes either form. No ability system exists.
ABILITY_ABSENT = (
    "the ability that invokes them is absent. Nothing outside "
    "require_taking_dilutes_the_thief calls take_control or steal_vessel, and "
    "skill_ladder.SKILL_NAMES holds one entry, the Quintessence Transfer"
)

#: What ends a ``ControlHold``. No figure names a length.
CONTROL_END_ABSENT = (
    "nothing ends a control hold. No figure names its length, and the only "
    "clock figure in reach is PvpMode.expires_turn, which lapses the permission "
    "and not the hold"
)

#: What reduces a health reading to ``HEALTH_AT_ZERO``. Nothing does.
HEALTH_SOURCE_ABSENT = (
    "no module holds a Vessel's health. vessels.Vessel carries owner, class_name, "
    "level and vessel_id, entity_stats.STAT_NAMES holds strength, dexterity, "
    "constitution, intelligence and wisdom and no health, and no figure names a "
    "maximum. "
    "set_health takes the reading from its caller, and combat is absent, so "
    "nothing reduces one to HEALTH_AT_ZERO"
)

#: Why a bot's health is not a Vessel's health.
TRADING_HEALTH_SEPARATE = (
    "rpg_metrics.health_metrics reads max_health_usd off "
    "scrumming_state.target_balance and names no Vessel, so no Vessel's health "
    "comes from it"
)

#: What joins ``MENTAL_EFFECTS``, and what applies or removes one. Nothing does.
MENTAL_EFFECT_SOURCE_ABSENT = (
    "his phrase 'or similar' makes the mental kind a class and not one effect, "
    "so MENTAL_EFFECTS holds the one effect he named and a second joins that "
    "tuple. apply_mental and clear_mental are the only writers, abilities are "
    "absent, and nothing applies or removes a daze"
)

#: Where an incapacitation's length comes from. This module computes none.
INCAPACITATION_LENGTH_GIVEN = (
    "an incapacitation's length belongs to the ability that caused it, so a "
    "caller supplies holds_until_world_turn and this module records it. "
    "Incapacitation.holds_at reads a recorded end against one world turn, and no "
    "timer, no decay and no length of its own exists here. An entry given no end "
    "holds at every world turn"
)

#: What a taking scores. ``score_taking`` takes its ratio from its caller.
TAKING_RATIO_ABSENT = (
    "neither form declares a ratio of Creation to Destruction. "
    "alignment.RATIO_SOURCE puts the ratio on the action, this module holds "
    "none, and the operator sets the figure a taking carries"
)

#: Whose alignment a taking moves, read off his rule about a Vessel's choices.
ALIGNMENT_SUBJECT = (
    "score_taking files the action against the acting Vessel and not against "
    "the Reincarnate behind it, reading alignment as a function of all a "
    "Vessel's life choices. AlignmentLedger.alignment_of_address adds every "
    "Vessel an address owns when a player reading is wanted"
)

#: What ``alignment.vessel_key`` carries across a theft, and what stays behind.
KEY_FOLLOWS_THE_OWNER = (
    "alignment.vessel_key files a Vessel under its owner, its class and its "
    "vessel_id, so a theft moves the taken Vessel to a new key and no other "
    "Vessel of the victim's ever held that key. steal_vessel moves the "
    "incapacitation onto the new key and clears the old one, and the scored "
    "actions AlignmentLedger holds stay under the victim's key. "
    "alignment.VESSEL_ID_OWED names the key shape that would carry those across"
)

#: Why no call hands a Vessel to a third address.
DUMPING_REFUSED = (
    "steal_vessel reads the new owner off thief.address, so no call moves a "
    "Vessel to an address that is not the taker's. Forcing a Vessel onto an "
    "enemy to dilute them is unreachable, and a thief dilutes only itself"
)

#: Why a thief may hold a Vessel its balance cannot power.
UNPOWERED_TAKING_OPEN = (
    "entity_stats.potential_at clamps its fraction and refuses nothing, and "
    "vessels.VESSEL_COUNT_UNCAPPED names the balance as the only bound on "
    "Vessel count. A theft that leaves every Vessel under full potential is "
    "permitted, and the thief carries the loss"
)

#: What reads a taking or an incapacitation. Nothing does.
ABSENT_READERS: tuple[str, ...] = (
    "an ability",
    "combat",
    "a surface",
    "a health reading",
    "a mental effect",
    "a control duration",
    "a Creation to Destruction ratio",
)

#: What each entry in ``ABSENT_READERS`` waits on.
ABSENT_READER_NOTES: dict[str, str] = {
    "an ability": ABILITY_ABSENT,
    "combat": "nothing resolves a fight, so no fight incapacitates a Vessel",
    "a surface": "no tab or panel shows a taking, a control hold or a condition",
    "a health reading": HEALTH_SOURCE_ABSENT,
    "a mental effect": MENTAL_EFFECT_SOURCE_ABSENT,
    "a control duration": CONTROL_END_ABSENT,
    "a Creation to Destruction ratio": TAKING_RATIO_ABSENT,
}

#: What an importer reaches, measured on the package's own export list.
PACKAGE_EXPORT_OWED = (
    "src/competition/__init__.py imports this module and lists its names in "
    "__all__, so every form is reachable as src.competition.<name>. A name this "
    "module repeats from a module bound above it stays unexported and is reached "
    "by importing src.competition.domination directly"
)


class DominationError(RuntimeError):
    """Base for every refusal this module raises."""


class ConditionError(DominationError):
    """Raised by ``require_incapacitated`` for a Vessel reading ``CONDITION_ABLE``."""


class PvpPermissionError(DominationError):
    """Raised when ``may_destroy`` refuses the taker against the Vessel's owner."""


class ActingVesselError(DominationError):
    """Raised for an acting Vessel whose ``owner`` is not the taker's address."""


class TakenVesselError(DominationError):
    """Raised for a taken Vessel outside the victim's own ``Reincarnate.vessels``."""


class TakingFormError(DominationError):
    """Raised by ``Taking`` for a form outside ``TAKING_FORMS``."""


class DilutionError(DominationError):
    """Raised by ``dilution_at`` for two readings of two different addresses."""


class ThiefDilutionError(DominationError):
    """Raised by ``require_taking_dilutes_the_thief`` when a driven reading departs."""


def _as_health(value: object) -> Decimal:
    """Return ``value`` as a finite health reading of zero or more, refusing ``float``."""
    if type(value) not in (int, str, Decimal):
        raise ConditionError(
            f"health must be int, str or Decimal, not {type(value).__name__}; a "
            f"reading against {HEALTH_AT_ZERO} decided by binary floating point "
            f"is refused"
        )
    try:
        reading = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ConditionError(f"health must be a number, got {value!r}") from exc
    if not reading.is_finite() or reading < HEALTH_AT_ZERO:
        raise ConditionError(
            f"health must be finite and {HEALTH_AT_ZERO} or more, got {value!r}"
        )
    return reading


@dataclass(frozen=True)
class Incapacitation:
    """One kind a Vessel is incapacitated by, its cause, and the end its caller gave.

    ``kind`` is a member of ``INCAPACITATION_KINDS``, ``cause`` is
    ``CAUSE_HEALTH_AT_ZERO`` or a ``MENTAL_EFFECTS`` entry, and
    ``INCAPACITATION_LENGTH_GIVEN`` names where ``holds_until_world_turn`` comes
    from.
    """

    kind: str
    cause: str
    holds_until_world_turn: int | None = None

    def __post_init__(self) -> None:
        """Refuse a ``kind`` outside ``INCAPACITATION_KINDS``."""
        if self.kind not in INCAPACITATION_KINDS:
            raise ConditionError(
                f"{self.kind!r} is no kind of incapacitation; the two are "
                f"{', '.join(INCAPACITATION_KINDS)}"
            )

    @property
    def has_end(self) -> bool:
        """Whether a caller gave this entry a ``holds_until_world_turn``."""
        return self.holds_until_world_turn is not None

    def holds_at(self, world_turn: int) -> bool:
        """Whether this entry holds on ``world_turn``, true while no caller gave an end."""
        if self.holds_until_world_turn is None:
            return True
        return int(world_turn) < self.holds_until_world_turn

    def to_dict(self) -> dict:
        """This incapacitation as a JSON-safe dict, carrying its kind, cause and end."""
        return {
            "kind": self.kind,
            "cause": self.cause,
            "holds_until_world_turn": self.holds_until_world_turn,
            "has_end": self.has_end,
        }


def require_mental_effect(effect: object) -> str:
    """Return ``effect`` when ``MENTAL_EFFECTS`` names it; every other value raises."""
    if effect not in MENTAL_EFFECTS:
        raise ConditionError(
            f"{effect!r} is no mental effect; {', '.join(MENTAL_EFFECTS)} is "
            f"named and {MENTAL_EFFECT_SOURCE_ABSENT}"
        )
    return str(effect)


class IncapacitationRegister:
    """Every ``Incapacitation`` a Vessel holds, filed under ``vessel_key`` by kind.

    ``set_health`` writes and removes ``KIND_PHYSICAL`` and ``apply_mental``
    writes ``KIND_MENTAL``, and ``condition_of`` reads either one.
    """

    def __init__(self) -> None:
        """Open a register holding no Vessel."""
        self._held: dict[tuple[str, str, str], dict[str, Incapacitation]] = {}

    @property
    def marked_count(self) -> int:
        """How many Vessels this register reads ``CONDITION_INCAPACITATED``."""
        return len(self._held)

    def set_health(
        self,
        vessel: object,
        health: object,
        holds_until_world_turn: int | None = None,
    ) -> str:
        """File ``vessel``'s health, marking ``KIND_PHYSICAL`` at ``HEALTH_AT_ZERO``."""
        key = vessel_key(vessel)
        reading = _as_health(health)
        if reading > HEALTH_AT_ZERO:
            self._drop(key, KIND_PHYSICAL)
        else:
            self._add(
                key,
                Incapacitation(
                    KIND_PHYSICAL, CAUSE_HEALTH_AT_ZERO, holds_until_world_turn
                ),
            )
        condition = self.condition_of(vessel)
        logger.info(
            "%s %s reads health %s and condition %s until world turn %s; %s",
            key[0],
            key[1],
            reading,
            condition,
            holds_until_world_turn,
            HEALTH_SOURCE_ABSENT,
        )
        return condition

    def apply_mental(
        self,
        vessel: object,
        effect: object,
        holds_until_world_turn: int | None = None,
    ) -> str:
        """File ``effect`` against ``vessel`` as ``KIND_MENTAL``, returning its condition."""
        key = vessel_key(vessel)
        named = require_mental_effect(effect)
        self._add(key, Incapacitation(KIND_MENTAL, named, holds_until_world_turn))
        logger.info(
            "%s %s reads %s under a %s until world turn %s; %s",
            key[0],
            key[1],
            CONDITION_INCAPACITATED,
            named,
            holds_until_world_turn,
            MENTAL_EFFECT_SOURCE_ABSENT,
        )
        return CONDITION_INCAPACITATED

    def clear_mental(self, vessel: object) -> str:
        """Drop ``KIND_MENTAL`` from ``vessel``, returning the condition left."""
        key = vessel_key(vessel)
        self._drop(key, KIND_MENTAL)
        return self.condition_of(vessel)

    def clear(self, vessel: object) -> str:
        """Drop every kind from ``vessel``, returning ``CONDITION_ABLE``."""
        key = vessel_key(vessel)
        self._held.pop(key, None)
        logger.info("%s %s reads %s", key[0], key[1], CONDITION_ABLE)
        return CONDITION_ABLE

    def carry_to(self, from_vessel: object, to_vessel: object) -> tuple[str, ...]:
        """Move every kind from ``from_vessel`` to ``to_vessel``, returning the kinds."""
        held = self.incapacitations_of(from_vessel)
        self.clear(from_vessel)
        key = vessel_key(to_vessel)
        for entry in held:
            self._add(key, entry)
        return tuple(entry.kind for entry in held)

    def incapacitations_of(
        self, vessel: object, world_turn: int | None = None
    ) -> tuple[Incapacitation, ...]:
        """Every ``Incapacitation`` ``vessel`` holds, those holding at ``world_turn``."""
        by_kind = self._held.get(vessel_key(vessel), {})
        held = tuple(by_kind[kind] for kind in INCAPACITATION_KINDS if kind in by_kind)
        if world_turn is None:
            return held
        return tuple(entry for entry in held if entry.holds_at(world_turn))

    def kinds_of(
        self, vessel: object, world_turn: int | None = None
    ) -> tuple[str, ...]:
        """Every kind ``vessel`` is incapacitated by, empty while it reads able."""
        return tuple(
            entry.kind for entry in self.incapacitations_of(vessel, world_turn)
        )

    def condition_of(self, vessel: object, world_turn: int | None = None) -> str:
        """Read ``vessel``'s condition, ``CONDITION_ABLE`` while no kind holds."""
        if self.incapacitations_of(vessel, world_turn):
            return CONDITION_INCAPACITATED
        return CONDITION_ABLE

    def is_incapacitated(self, vessel: object, world_turn: int | None = None) -> bool:
        """Whether ``condition_of`` reads ``CONDITION_INCAPACITATED`` for ``vessel``."""
        return self.condition_of(vessel, world_turn) == CONDITION_INCAPACITATED

    def rows(self) -> list[dict]:
        """One row a marked Vessel, carrying its ``vessel_key`` triple and every kind."""
        return [
            {
                "owner": owner,
                "class_name": class_name,
                "vessel_id": vessel_id,
                "condition": CONDITION_INCAPACITATED,
                "incapacitations": [
                    by_kind[kind].to_dict()
                    for kind in INCAPACITATION_KINDS
                    if kind in by_kind
                ],
            }
            for (owner, class_name, vessel_id), by_kind in sorted(self._held.items())
        ]

    def to_dict(self) -> dict:
        """This register as a JSON-safe dict, carrying every marked Vessel and what is owed."""
        return {
            "marked_count": self.marked_count,
            "marked": self.rows(),
            "conditions": list(CONDITIONS),
            "kinds": list(INCAPACITATION_KINDS),
            "mental_effects": list(MENTAL_EFFECTS),
            "health_at_zero": amount_text(HEALTH_AT_ZERO),
            "health_source_absent": HEALTH_SOURCE_ABSENT,
            "trading_health_separate": TRADING_HEALTH_SEPARATE,
            "mental_effect_source_absent": MENTAL_EFFECT_SOURCE_ABSENT,
            "incapacitation_length_given": INCAPACITATION_LENGTH_GIVEN,
            "key_follows_the_owner": KEY_FOLLOWS_THE_OWNER,
        }

    def _add(self, key: tuple[str, str, str], entry: Incapacitation) -> None:
        """File ``entry`` under ``key``, replacing any entry of the same kind."""
        self._held.setdefault(key, {})[entry.kind] = entry

    def _drop(self, key: tuple[str, str, str], kind: str) -> None:
        """Drop ``kind`` from ``key``, dropping the key once it holds nothing."""
        by_kind = self._held.get(key)
        if by_kind is None:
            return
        by_kind.pop(kind, None)
        if not by_kind:
            del self._held[key]


@dataclass(frozen=True)
class Taking:
    """One taking: its form, the taker, the acting Vessel, the owner and the Vessel taken.

    ``world_turn`` is the world-clock index ``may_destroy`` read the permission
    on, and ``moves_ownership`` separates the two forms.
    """

    form: str
    taker: str
    acting_class_name: str
    owner: str
    taken_class_name: str
    taken_level: int
    world_turn: int

    def __post_init__(self) -> None:
        """Refuse a ``form`` outside ``TAKING_FORMS``."""
        if self.form not in TAKING_FORMS:
            raise TakingFormError(
                f"{self.form!r} is no taking form; the two are "
                f"{', '.join(TAKING_FORMS)}"
            )

    @property
    def action(self) -> str:
        """The ``ACTION_NAMES`` entry this form files under."""
        return ACTION_NAMES[self.form]

    @property
    def moves_ownership(self) -> bool:
        """Whether this form moves ``Vessel.owner``, true for ``TAKING_THEFT`` alone."""
        return self.form == TAKING_THEFT

    def to_dict(self) -> dict:
        """This taking as a JSON-safe dict, reconstructible after ownership moved."""
        return {
            "form": self.form,
            "action": self.action,
            "taker": self.taker,
            "acting_class_name": self.acting_class_name,
            "owner": self.owner,
            "taken_class_name": self.taken_class_name,
            "taken_level": self.taken_level,
            "world_turn": self.world_turn,
            "moves_ownership": self.moves_ownership,
            "ratio_absent": TAKING_RATIO_ABSENT,
        }


@dataclass(frozen=True)
class ControlHold:
    """One ``TAKING_CONTROL``: the taker acts with a Vessel its owner keeps.

    ``owner`` reads off ``vessel`` and is unchanged by this hold, and
    ``CONTROL_END_ABSENT`` names what would end it.
    """

    taking: Taking
    vessel: Vessel

    @property
    def controller(self) -> str:
        """The address acting with ``vessel``, which is ``taking.taker``."""
        return self.taking.taker

    @property
    def owner(self) -> str:
        """The address still owning ``vessel``, unmoved by this hold."""
        return self.vessel.owner

    def to_dict(self) -> dict:
        """This hold as a JSON-safe dict, carrying the taking and the Vessel held."""
        return {
            "taking": self.taking.to_dict(),
            "vessel": self.vessel.to_dict(),
            "controller": self.controller,
            "owner": self.owner,
            "control_end_absent": CONTROL_END_ABSENT,
        }


@dataclass(frozen=True)
class Theft:
    """One ``TAKING_THEFT``: both Reincarnates rebuilt around the Vessel that moved.

    ``victim_after`` holds every Vessel but ``taken_vessel``, and ``thief_after``
    holds ``taken_vessel`` under its new owner.
    """

    taking: Taking
    taken_vessel: Vessel
    victim_after: Reincarnate
    thief_after: Reincarnate

    def to_dict(self) -> dict:
        """This theft as a JSON-safe dict, carrying both sides after the move."""
        return {
            "taking": self.taking.to_dict(),
            "taken_vessel": self.taken_vessel.to_dict(),
            "victim_after": self.victim_after.to_dict(),
            "thief_after": self.thief_after.to_dict(),
            "dumping_refused": DUMPING_REFUSED,
            "unpowered_taking_open": UNPOWERED_TAKING_OPEN,
            "key_follows_the_owner": KEY_FOLLOWS_THE_OWNER,
        }


@dataclass(frozen=True)
class Dilution:
    """One address's ``Potential`` before and after a taking, at one unchanged balance.

    ``fraction_change`` is negative for a thief and positive for the victim it
    took from.
    """

    address: str
    before: Potential
    after: Potential

    @property
    def fraction_change(self) -> Decimal:
        """``after.fraction`` less ``before.fraction``."""
        return self.after.fraction - self.before.fraction

    @property
    def requirement_change(self) -> Decimal:
        """``after.requirement`` less ``before.requirement``."""
        return self.after.requirement - self.before.requirement

    @property
    def is_weaker(self) -> bool:
        """Whether ``fraction_change`` falls below zero."""
        return self.fraction_change < 0

    def to_dict(self) -> dict:
        """This reading as a JSON-safe dict, every amount a plain string."""
        return {
            "address": self.address,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "fraction_change": str(self.fraction_change),
            "requirement_change": amount_text(self.requirement_change),
            "is_weaker": self.is_weaker,
        }


def require_incapacitated(
    register: IncapacitationRegister, vessel: object, world_turn: int | None = None
) -> str:
    """Raise unless ``register`` reads ``CONDITION_INCAPACITATED`` at ``world_turn``."""
    condition = register.condition_of(vessel, world_turn)
    if condition == CONDITION_INCAPACITATED:
        return condition
    key = vessel_key(vessel)
    raise ConditionError(
        f"{key[0]}'s {key[1]} reads {condition} and only a Vessel reading "
        f"{CONDITION_INCAPACITATED} may be taken, by either of "
        f"{', '.join(INCAPACITATION_KINDS)}; {HEALTH_SOURCE_ABSENT}"
    )


def require_taking_permitted(
    taker: str,
    owner: str,
    world_turn: int,
    mode: PvpMode | None = None,
    *,
    lock: PvpLock | None = None,
    pvp_event: bool = False,
) -> bool:
    """Raise unless ``may_destroy`` permits ``taker`` against ``owner``.

    No second permission exists here, and ``may_destroy`` refuses a taker against
    its own address.
    """
    if may_destroy(taker, owner, world_turn, mode, lock=lock, pvp_event=pvp_event):
        return True
    raise PvpPermissionError(
        f"{taker} may not take {owner}'s Vessel on world turn {world_turn}; "
        f"pvp_vote.may_destroy permits a taking while a PvP mode or a PvP lock "
        f"holds that turn or a PvP event is set, and never against one's own"
    )


def _require_acting_vessel(taker: str, acting_vessel: Vessel) -> Vessel:
    """Return ``acting_vessel`` when ``taker`` owns it; every other owner raises."""
    if acting_vessel.owner != taker:
        raise ActingVesselError(
            f"the acting {acting_vessel.class_name} is owned by "
            f"{acting_vessel.owner!r} and {taker!r} is taking; a taker acts with "
            f"a Vessel of its own"
        )
    return acting_vessel


def _taken_index(victim: Reincarnate, taken_vessel: Vessel) -> int:
    """The position ``taken_vessel`` holds in ``victim.vessels``; absence raises."""
    try:
        return victim.vessels.index(taken_vessel)
    except ValueError as exc:
        raise TakenVesselError(
            f"{victim.address} holds {len(victim.vessels)} Vessel(s) and none of "
            f"them is a {taken_vessel.class_name} at level {taken_vessel.level} "
            f"owned by {taken_vessel.owner!r}"
        ) from exc


def _gate(
    register: IncapacitationRegister,
    taker: str,
    acting_vessel: Vessel,
    taken_vessel: Vessel,
    world_turn: int,
    mode: PvpMode | None,
    lock: PvpLock | None,
    pvp_event: bool,
) -> None:
    """Run both refusals every taking answers to, the PvP one first."""
    _require_acting_vessel(taker, acting_vessel)
    require_taking_permitted(
        taker,
        taken_vessel.owner,
        world_turn,
        mode,
        lock=lock,
        pvp_event=pvp_event,
    )
    require_incapacitated(register, taken_vessel, int(world_turn))


def take_control(
    register: IncapacitationRegister,
    taker: Reincarnate,
    acting_vessel: Vessel,
    taken_vessel: Vessel,
    world_turn: int,
    mode: PvpMode | None = None,
    *,
    lock: PvpLock | None = None,
    pvp_event: bool = False,
) -> ControlHold:
    """Hold ``taken_vessel`` under ``taker`` while its owner keeps it.

    No ``Vessel.owner`` moves and no ``Reincarnate`` is rebuilt, and
    ``CONTROL_END_ABSENT`` names what would end the hold.
    """
    _gate(
        register,
        taker.address,
        acting_vessel,
        taken_vessel,
        world_turn,
        mode,
        lock,
        pvp_event,
    )
    hold = ControlHold(
        Taking(
            TAKING_CONTROL,
            taker.address,
            acting_vessel.class_name,
            taken_vessel.owner,
            taken_vessel.class_name,
            taken_vessel.level,
            int(world_turn),
        ),
        taken_vessel,
    )
    logger.info(
        "%s acts with %s's %s on world turn %d through its own %s; ownership is "
        "unmoved and %s",
        hold.controller,
        hold.owner,
        taken_vessel.class_name,
        hold.taking.world_turn,
        acting_vessel.class_name,
        CONTROL_END_ABSENT,
    )
    return hold


def steal_vessel(
    register: IncapacitationRegister,
    thief: Reincarnate,
    acting_vessel: Vessel,
    victim: Reincarnate,
    taken_vessel: Vessel,
    world_turn: int,
    mode: PvpMode | None = None,
    *,
    lock: PvpLock | None = None,
    pvp_event: bool = False,
) -> Theft:
    """Move ``taken_vessel`` from ``victim`` to ``thief``, rebuilding both sides.

    Every Vessel ``thief`` owns reads a lower ``Potential.fraction`` afterwards,
    and ``DUMPING_REFUSED`` names the address a taken Vessel can reach.
    """
    _gate(
        register,
        thief.address,
        acting_vessel,
        taken_vessel,
        world_turn,
        mode,
        lock,
        pvp_event,
    )
    index = _taken_index(victim, taken_vessel)
    moved = replace(taken_vessel, owner=thief.address)
    # replace copies the vessel_id and moved names a new owner, so carry_to
    # moves the kinds onto the key moved holds.
    register.carry_to(taken_vessel, moved)
    theft = Theft(
        Taking(
            TAKING_THEFT,
            thief.address,
            acting_vessel.class_name,
            victim.address,
            taken_vessel.class_name,
            taken_vessel.level,
            int(world_turn),
        ),
        moved,
        Reincarnate(
            victim.address, victim.vessels[:index] + victim.vessels[index + 1 :]
        ),
        Reincarnate(thief.address, thief.vessels + (moved,)),
    )
    logger.info(
        "%s stole %s's %s on world turn %d; %s now holds %d Vessel(s) needing "
        "%s and %s holds %d needing %s",
        theft.taking.taker,
        theft.taking.owner,
        theft.taking.taken_class_name,
        theft.taking.world_turn,
        theft.thief_after.address,
        len(theft.thief_after.vessels),
        amount_text(theft.thief_after.requirement),
        theft.victim_after.address,
        len(theft.victim_after.vessels),
        amount_text(theft.victim_after.requirement),
    )
    return theft


def dilution_at(before: Reincarnate, after: Reincarnate, balance: object) -> Dilution:
    """Read one address's ``Potential`` across a taking at one unchanged ``balance``."""
    if before.address != after.address:
        raise DilutionError(
            f"{before.address!r} and {after.address!r} are two addresses and one "
            f"dilution reads one wallet across a taking"
        )
    reading = Dilution(
        before.address, before.potential(balance), after.potential(balance)
    )
    logger.info(
        "%s moved from %d Vessel(s) at %s of full to %d at %s, a change of %s on "
        "a balance of %s",
        reading.address,
        len(before.vessels),
        amount_text(reading.before.fraction),
        len(after.vessels),
        amount_text(reading.after.fraction),
        reading.fraction_change,
        amount_text(reading.after.balance),
    )
    return reading


def score_taking(
    ledger: AlignmentLedger,
    taking: Taking,
    acting_vessel: Vessel,
    creation: object,
    destruction: object,
) -> ActionScore:
    """Score ``taking`` against ``acting_vessel`` at the ratio the caller names.

    ``TAKING_RATIO_ABSENT`` names who sets the figure, and ``ALIGNMENT_SUBJECT``
    names why the acting Vessel carries it.
    """
    if not isinstance(ledger, AlignmentLedger):
        raise DominationError(
            f"an AlignmentLedger was expected, got {type(ledger).__name__}"
        )
    if not isinstance(taking, Taking):
        raise DominationError(f"a Taking was expected, got {type(taking).__name__}")
    if (
        acting_vessel.owner != taking.taker
        or acting_vessel.class_name != taking.acting_class_name
    ):
        raise ActingVesselError(
            f"{taking.taker}'s {taking.acting_class_name} performed this "
            f"{taking.form} and {acting_vessel.owner}'s "
            f"{acting_vessel.class_name} is being scored for it"
        )
    return ledger.score(acting_vessel, taking.action, creation, destruction)


def _driven_pair() -> tuple[Reincarnate, Reincarnate]:
    """A victim of four Vessels and a thief of three, every one at ``DRIVEN_LEVEL``."""
    victim = Reincarnate(
        "0xvictim",
        tuple(Vessel("0xvictim", name, DRIVEN_LEVEL) for name in CLASS_NAMES[:4]),
    )
    thief = Reincarnate(
        "0xthief",
        tuple(Vessel("0xthief", name, DRIVEN_LEVEL) for name in CLASS_NAMES[4:7]),
    )
    return victim, thief


def _require_refusal(
    call: str,
    wanted: type[DominationError],
    run: Callable[..., object],
    *args: object,
) -> str:
    """Run ``run`` expecting ``wanted``; returning nothing raises ``ThiefDilutionError``."""
    try:
        run(*args)
    except wanted as exc:
        return str(exc)
    raise ThiefDilutionError(
        f"{call} returned where {wanted.__name__} was expected; a taking that "
        f"refuses neither gate would move a Vessel nobody may touch"
    )


def require_taking_dilutes_the_thief() -> None:
    """Drive one theft on real Reincarnates and log both sides of the dilution.

    A departure raises ``ThiefDilutionError``, and both gates are driven to their
    refusals first.
    """
    victim, thief = _driven_pair()
    register = IncapacitationRegister()
    taken = victim.vessels[0]
    dazed = victim.vessels[1]
    acting = thief.vessels[0]
    peaceful = _require_refusal(
        "steal_vessel with no PvP mode",
        PvpPermissionError,
        steal_vessel,
        register,
        thief,
        acting,
        victim,
        taken,
        0,
    )
    mode = PvpMode("0xworld", 0)
    register.set_health(taken, DRIVEN_HEALTH)
    able = _require_refusal(
        "steal_vessel against a Vessel above HEALTH_AT_ZERO under no effect",
        ConditionError,
        steal_vessel,
        register,
        thief,
        acting,
        victim,
        taken,
        0,
        mode,
    )
    lapsing = victim.vessels[2]
    register.apply_mental(lapsing, MENTAL_EFFECT_DAZE, DRIVEN_END_WORLD_TURN)
    if register.condition_of(lapsing, 0) != CONDITION_INCAPACITATED:
        raise ThiefDilutionError(
            f"a {MENTAL_EFFECT_DAZE} given an end of world turn "
            f"{DRIVEN_END_WORLD_TURN} reads "
            f"{register.condition_of(lapsing, 0)} on world turn 0"
        )
    lapsed = _require_refusal(
        "take_control past a caller-given end",
        ConditionError,
        take_control,
        register,
        thief,
        acting,
        lapsing,
        DRIVEN_END_WORLD_TURN,
        mode,
    )
    register.apply_mental(dazed, MENTAL_EFFECT_DAZE)
    hold = take_control(register, thief, acting, dazed, 0, mode)
    if hold.owner != victim.address or hold.taking.moves_ownership:
        raise ThiefDilutionError(
            f"a {MENTAL_EFFECT_DAZE} gave {hold.controller} control of a Vessel "
            f"reading owner {hold.owner!r}, and moves_ownership reads "
            f"{hold.taking.moves_ownership}"
        )
    register.set_health(taken, HEALTH_AT_ZERO)
    theft = steal_vessel(register, thief, acting, victim, taken, 0, mode)
    if theft.taken_vessel.owner != thief.address:
        raise ThiefDilutionError(
            f"the taken {taken.class_name} reads owner "
            f"{theft.taken_vessel.owner!r} after a theft by {thief.address!r}"
        )
    robbed = dilution_at(victim, theft.victim_after, DRIVEN_BALANCE)
    enriched = dilution_at(thief, theft.thief_after, DRIVEN_BALANCE)
    if robbed.is_weaker or not enriched.is_weaker:
        raise ThiefDilutionError(
            f"{robbed.address} changed by {robbed.fraction_change} and "
            f"{enriched.address} by {enriched.fraction_change}; a theft raises "
            f"the victim's remaining Vessels and lowers every one of the thief's"
        )
    logger.info(
        "a theft of one Vessel at level %d on a balance of %s moved %s from %s "
        "to %s of full and %s from %s to %s",
        DRIVEN_LEVEL,
        amount_text(DRIVEN_BALANCE),
        robbed.address,
        amount_text(robbed.before.fraction),
        amount_text(robbed.after.fraction),
        enriched.address,
        amount_text(enriched.before.fraction),
        amount_text(enriched.after.fraction),
    )
    logger.info(
        "the taken %s reads %s under its new owner and a fresh %s of %s reads "
        "%s: %s",
        theft.taking.taken_class_name,
        register.condition_of(theft.taken_vessel),
        taken.class_name,
        victim.address,
        register.condition_of(taken),
        KEY_FOLLOWS_THE_OWNER,
    )
    logger.info("without a PvP mode a theft refused with %r", peaceful)
    logger.info(
        "at health %s under no effect a theft refused with %r",
        DRIVEN_HEALTH,
        able,
    )
    logger.info(
        "the taken %s read kinds %s at health %s and the held %s read kinds %s "
        "under a %s",
        theft.taking.taken_class_name,
        register.kinds_of(theft.taken_vessel),
        HEALTH_AT_ZERO,
        hold.taking.taken_class_name,
        register.kinds_of(dazed),
        MENTAL_EFFECT_DAZE,
    )
    logger.info(
        "a %s given an end of world turn %d read kinds %s on turn 0 and %s on "
        "that turn, refusing with %r; %s",
        MENTAL_EFFECT_DAZE,
        DRIVEN_END_WORLD_TURN,
        register.kinds_of(lapsing, 0),
        register.kinds_of(lapsing, DRIVEN_END_WORLD_TURN),
        lapsed,
        INCAPACITATION_LENGTH_GIVEN,
    )
    logger.info(
        "%d readers are absent: %s. %s",
        len(ABSENT_READERS),
        ", ".join(ABSENT_READERS),
        PACKAGE_EXPORT_OWED,
    )


require_taking_dilutes_the_thief()
