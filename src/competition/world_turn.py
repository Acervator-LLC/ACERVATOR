"""The pool one world turn grants a participant, counted in steps.

``UNLADEN_STEPS_ABSENT`` names the one figure no source sets, so ``TurnGrant``
refuses a grant built without it and ``granted_steps`` floors at
``MIN_GRANT_STEPS``. ``WorldTurnPool.spend`` refuses a cost above ``remaining``
and every turn but its own. ``WorldTurnPools.open_pool`` refuses a second pool
for one participant in one turn, and ``ABSENT_READERS`` names what spends none of
this yet.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from .consecration import CLOCK, WORLD_TURN_SECONDS_ABSENT
from .world_movement import BASE_STEPS_PER_TURN

logger = logging.getLogger("acervator.world_turn")

#: The unit a grant and a spend are both counted in, one whole percent of a square.
STEP_UNIT = "step"

#: A figure no source sets. Its own note says what would set it.
FIGURE_ABSENT = None

#: What names the steps a world turn grants. Nothing does.
UNLADEN_STEPS_ABSENT = (
    f"unladen_steps arrives with the grant and no source names it. world_movement "
    f"moves one leg at {BASE_STEPS_PER_TURN} steps a {CLOCK} under its own terrain "
    f"and encumbrance multipliers, so a grant read off that rate would count both "
    f"multipliers twice. The operator sets the figure"
)

#: What weighs a carried load. Nothing does.
PENALTY_ABSENT = (
    "penalty_steps arrives with the grant. Nothing weighs a Vessel's carried items "
    "and no material carries a weight, so no module computes an encumbrance penalty"
)

#: Where one action's cost comes from. No module prices one.
COST_SOURCE = (
    "cost arrives with the action, the way alignment.RATIO_SOURCE says every ratio "
    "does. No module prices a world-turn action in steps, and movement is the only "
    "act whose own rate names a figure a turn"
)

#: The fewest steps a grant holds once its penalty is taken.
MIN_GRANT_STEPS = 0

#: The fewest steps one action costs, so no spend leaves ``remaining`` where it was.
MIN_SPEND_STEPS = 1

#: The first world turn a pool opens on, the whole-index convention pvp_vote counts.
FIRST_TURN_INDEX = 0

#: What spends a world-turn pool. Nothing does.
ABSENT_READERS: tuple[str, ...] = (
    "movement",
    "encumbrance",
    "crafting",
    "a surface",
)

#: What each entry in ``ABSENT_READERS`` waits on.
ABSENT_READER_NOTES: dict[str, str] = {
    "movement": (
        "world_movement derives a leg's progress from its own rate and reads no "
        "pool, so a journey spends no step here"
    ),
    "encumbrance": (
        "no module weighs a carried load, so nothing computes the penalty_steps a "
        "grant takes"
    ),
    "crafting": (
        "crafting counts whole turns to completes_turn and spends no step in any "
        "of them"
    ),
    "a surface": (
        "the tab's turn meter reads the event turn's candle and its Impetus line "
        "reads that pool; no panel names a world turn"
    ),
}


class WorldTurnError(RuntimeError):
    """Base for every refusal this module raises."""


class StepFigureError(WorldTurnError):
    """Raised for a step figure that is absent, fractional or below its floor."""


class ExpiredTurnError(WorldTurnError):
    """Raised by ``spend`` and ``open_pool`` for a turn other than the pool's own."""


class ExhaustedPoolError(WorldTurnError):
    """Raised by ``WorldTurnPool.spend`` when ``remaining`` cannot pay the cost."""


class DoublePoolError(WorldTurnError):
    """Raised by ``open_pool`` for a participant already holding that turn's pool."""


class UnknownPoolError(WorldTurnError):
    """Raised by ``pool`` for a participant no ``open_pool`` has granted one."""


def _as_steps(
    value: object,
    name: str,
    absent_note: str,
    minimum: int = MIN_GRANT_STEPS,
) -> int:
    """Return ``value`` as whole steps of ``minimum`` or more, refusing other types."""
    if value is FIGURE_ABSENT:
        refusal = f"{name} is absent; {absent_note}"
        raise StepFigureError(refusal)
    if type(value) is not int:
        refusal = (
            f"{name} must be a whole number of {STEP_UNIT}s, not "
            f"{type(value).__name__}; a {CLOCK} figure decided by binary "
            f"floating point is refused"
        )
        raise StepFigureError(refusal)
    if value < minimum:
        refusal = f"{name} must be {minimum} or more {STEP_UNIT}s, got {value!r}"
        raise StepFigureError(refusal)
    return value


def _as_turn_index(value: object, name: str) -> int:
    """Return ``value`` as a whole ``CLOCK`` index of ``FIRST_TURN_INDEX`` or more."""
    if type(value) is not int:
        refusal = (
            f"{name} must be a whole {CLOCK} index, not "
            f"{type(value).__name__}; {WORLD_TURN_SECONDS_ABSENT}"
        )
        raise WorldTurnError(refusal)
    if value < FIRST_TURN_INDEX:
        refusal = f"{name} must be {FIRST_TURN_INDEX} or more, got {value!r}"
        raise WorldTurnError(refusal)
    return value


def _as_participant(value: object) -> str:
    """Return ``value`` as a non-blank wallet address; every other value raises."""
    if type(value) is not str or not value.strip():
        refusal = f"participant must be a non-empty wallet address, got {value!r}"
        raise WorldTurnError(refusal)
    return value.strip()


@dataclass(frozen=True)
class TurnGrant:
    """What one world turn grants one participant, in steps, after its penalty.

    ``penalty_steps`` is the only figure that lowers ``granted_steps``, which
    floors at ``MIN_GRANT_STEPS``.
    """

    participant: str
    turn_index: int
    unladen_steps: int
    penalty_steps: int = 0

    def __post_init__(self) -> None:
        """Coerce the address, the turn index and both step figures."""
        object.__setattr__(self, "participant", _as_participant(self.participant))
        object.__setattr__(
            self,
            "turn_index",
            _as_turn_index(self.turn_index, "turn_index"),
        )
        object.__setattr__(
            self,
            "unladen_steps",
            _as_steps(self.unladen_steps, "unladen_steps", UNLADEN_STEPS_ABSENT),
        )
        object.__setattr__(
            self,
            "penalty_steps",
            _as_steps(self.penalty_steps, "penalty_steps", PENALTY_ABSENT),
        )

    @property
    def granted_steps(self) -> int:
        """``unladen_steps`` less ``penalty_steps``, never below ``MIN_GRANT_STEPS``."""
        return max(MIN_GRANT_STEPS, self.unladen_steps - self.penalty_steps)

    def to_dict(self) -> dict:
        """Return this grant as a JSON-safe dict, naming the clock it counts."""
        return {
            "participant": self.participant,
            "turn_index": self.turn_index,
            "unladen_steps": self.unladen_steps,
            "penalty_steps": self.penalty_steps,
            "granted_steps": self.granted_steps,
            "unit": STEP_UNIT,
            "clock": CLOCK,
        }


@dataclass
class WorldTurnPool:
    """One world turn's grant of steps, spent inside that turn and lost with it.

    ``grant.turn_index`` binds the pool to one turn, so ``spend`` refuses every
    other turn and nothing unspent carries forward.
    """

    grant: TurnGrant
    spent: int = 0

    @property
    def participant(self) -> str:
        """The wallet address this pool was granted to."""
        return self.grant.participant

    @property
    def turn_index(self) -> int:
        """The one world turn this pool may be spent in."""
        return self.grant.turn_index

    @property
    def granted(self) -> int:
        """The steps this turn granted, from ``TurnGrant.granted_steps``."""
        return self.grant.granted_steps

    @property
    def remaining(self) -> int:
        """The steps still unspent in this turn."""
        return self.granted - self.spent

    def spend(self, cost: int, at_turn: int) -> int:
        """Spend ``cost`` steps, refusing another turn or a cost above ``remaining``.

        Returns the steps remaining after the spend.
        """
        asked = _as_turn_index(at_turn, "at_turn")
        if asked != self.turn_index:
            refusal = (
                f"this pool granted {self.granted} {STEP_UNIT}s to "
                f"{self.participant} for {CLOCK} {self.turn_index} and "
                f"{self.remaining} is unspent; {CLOCK} {asked} is a different "
                f"turn, and a {CLOCK}'s steps expire with the turn that "
                f"granted them"
            )
            raise ExpiredTurnError(refusal)
        steps = _as_steps(cost, "cost", COST_SOURCE, MIN_SPEND_STEPS)
        if steps > self.remaining:
            refusal = (
                f"this action costs {steps} {STEP_UNIT}s and {self.remaining} "
                f"remains of {self.granted} in {CLOCK} {self.turn_index}; no "
                f"partial action exists and nobody borrows against the next turn"
            )
            raise ExhaustedPoolError(refusal)
        self.spent += steps
        return self.remaining

    def to_dict(self) -> dict:
        """Return this pool as a JSON-safe dict, beside the grant behind it."""
        return {
            "participant": self.participant,
            "turn_index": self.turn_index,
            "granted": self.granted,
            "spent": self.spent,
            "remaining": self.remaining,
            "unit": STEP_UNIT,
            "clock": CLOCK,
            "grant": self.grant.to_dict(),
        }


class WorldTurnPools:
    """Holds the one pool each participant's current world turn grants.

    A pool expires with its turn, so the register keeps no closed turn and
    writes no file.
    """

    def __init__(self) -> None:
        """Hold no pool; ``open_pool`` grants the first."""
        self._lock = threading.RLock()
        self._pools: dict[str, WorldTurnPool] = {}

    @property
    def participants(self) -> tuple[str, ...]:
        """The participants holding a pool, in the order each first opened one."""
        return tuple(self._pools)

    def open_pool(
        self,
        participant: str,
        turn_index: int,
        unladen_steps: int,
        penalty_steps: int = 0,
    ) -> WorldTurnPool:
        """Grant ``participant`` the one pool ``turn_index`` carries, refusing a second.

        Raises ``DoublePoolError`` for the turn already held and
        ``ExpiredTurnError`` for a turn before it.
        """
        grant = TurnGrant(participant, turn_index, unladen_steps, penalty_steps)
        with self._lock:
            held = self._pools.get(grant.participant)
            if held is not None:
                self._require_later_turn(held, grant)
                if held.remaining:
                    logger.info(
                        "%s lost %d of %d %ss unspent when %s %d closed",
                        held.participant,
                        held.remaining,
                        held.granted,
                        STEP_UNIT,
                        CLOCK,
                        held.turn_index,
                    )
            pool = WorldTurnPool(grant)
            self._pools[grant.participant] = pool
        logger.info(
            "%s holds %d %ss for %s %d, %d unladen less %d penalty",
            pool.participant,
            pool.granted,
            STEP_UNIT,
            CLOCK,
            pool.turn_index,
            grant.unladen_steps,
            grant.penalty_steps,
        )
        return pool

    def pool(self, participant: str, turn_index: int) -> WorldTurnPool:
        """Return the pool ``participant`` holds for ``turn_index``, refusing others."""
        key = _as_participant(participant)
        asked = _as_turn_index(turn_index, "turn_index")
        held = self._pools.get(key)
        if held is None:
            named = ", ".join(sorted(self._pools)) or "none"
            refusal = (
                f"no {CLOCK} pool is open for {key}; nothing grants one until "
                f"open_pool does, and participants holding one: {named}"
            )
            raise UnknownPoolError(refusal)
        if held.turn_index != asked:
            refusal = (
                f"{key} holds a pool for {CLOCK} {held.turn_index}, not {CLOCK} "
                f"{asked}; a {CLOCK}'s steps expire with the turn that granted "
                f"them"
            )
            raise ExpiredTurnError(refusal)
        return held

    def spend(self, participant: str, cost: int, at_turn: int) -> int:
        """Spend ``cost`` from ``participant``'s pool, logging what is left."""
        pool = self.pool(participant, at_turn)
        remaining = pool.spend(cost, at_turn)
        logger.info(
            "%s spent %d of %d %ss in %s %d, %d remaining",
            pool.participant,
            pool.spent,
            pool.granted,
            STEP_UNIT,
            CLOCK,
            pool.turn_index,
            remaining,
        )
        return remaining

    def remaining(self, participant: str, at_turn: int) -> int:
        """Return the steps ``participant`` has left in ``at_turn``."""
        return self.pool(participant, at_turn).remaining

    def pool_rows(self) -> list[dict]:
        """Every held pool as ``WorldTurnPool.to_dict`` serves it."""
        return [pool.to_dict() for pool in self._pools.values()]

    def _require_later_turn(self, held: WorldTurnPool, grant: TurnGrant) -> None:
        """Refuse a second pool for ``held``'s own turn, and any turn before it."""
        if held.turn_index == grant.turn_index:
            refusal = (
                f"{held.participant} already holds a pool of {held.granted} "
                f"{STEP_UNIT}s for {CLOCK} {held.turn_index} with "
                f"{held.remaining} unspent; one participant holds one pool a "
                f"{CLOCK}"
            )
            raise DoublePoolError(refusal)
        if held.turn_index > grant.turn_index:
            refusal = (
                f"{held.participant} holds a pool for {CLOCK} "
                f"{held.turn_index}, and {CLOCK} {grant.turn_index} has closed; "
                f"a closed turn grants nothing a second time"
            )
            raise ExpiredTurnError(refusal)


def turn_economy_row() -> dict:
    """Return the world turn's economy as a surface reads it, every absence named."""
    return {
        "clock": CLOCK,
        "unit": STEP_UNIT,
        "min_grant_steps": MIN_GRANT_STEPS,
        "min_spend_steps": MIN_SPEND_STEPS,
        "first_turn_index": FIRST_TURN_INDEX,
        "world_turn_seconds_absent": WORLD_TURN_SECONDS_ABSENT,
        "unladen_steps_absent": UNLADEN_STEPS_ABSENT,
        "penalty_absent": PENALTY_ABSENT,
        "cost_source": COST_SOURCE,
        "absent_readers": list(ABSENT_READERS),
        "absent_reader_notes": dict(ABSENT_READER_NOTES),
    }
