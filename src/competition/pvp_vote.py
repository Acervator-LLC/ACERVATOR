"""The PvP vote a world calls, the mode it carries and the destruction permission.

``call_vote`` opens a ``PvpBallot`` on the world clock and refuses a second call
inside ``VOTE_CADENCE_WORLD_TURNS``, while ``cast_vote`` reads the event clock's
``CASTING_WINDOW_TURNS`` standard candles. ``resolve`` settles at
``PvpBallot.resolving_turn`` and ``mode_from`` turns a carried ballot into a
``PvpMode`` holding ``PVP_MODE_WORLD_TURNS``. ``may_destroy`` answers the
permission and reads ``pvp_event`` beside the mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .poa_modes import MONSTER_SMASH, EventVariant, Turn, turn_at, variant_of

logger = logging.getLogger("acervator.pvp_vote")

#: Standard candles one casting window counts, his fifteen minutes at 300s each.
CASTING_WINDOW_TURNS = 3

#: Any standard variant carries the 5m candle ``CASTING_WINDOW_TURNS`` counts.
CASTING_VARIANT: EventVariant = variant_of(MONSTER_SMASH)

#: World turns between two calls, his one vote every 24 hours at one turn an hour.
VOTE_CADENCE_WORLD_TURNS = 24

#: World turns a carried mode holds, the cadence span, so PvP lapses as the
#: next call opens.
PVP_MODE_WORLD_TURNS = VOTE_CADENCE_WORLD_TURNS

#: World turns past ``called_turn`` a ballot resolves on, one world-turn boundary.
RESOLUTION_WORLD_TURNS = 1

#: The carry fraction's numerator over the whole roll, two thirds, not a majority.
CARRY_NUMERATOR = 2

#: The carry fraction's denominator; two thirds of the roll needs more than one guild.
CARRY_DENOMINATOR = 3

#: The smallest roll ``call_vote`` opens a ballot against.
MIN_ELIGIBLE_ROLL = 1


class PvpVoteError(RuntimeError):
    """Base for every refusal this module raises."""


class VoteCadenceError(PvpVoteError):
    """Raised by ``call_vote`` inside ``VOTE_CADENCE_WORLD_TURNS`` of the last call."""


class EmptyRollError(PvpVoteError):
    """Raised by ``call_vote`` under ``MIN_ELIGIBLE_ROLL`` participants."""


class CastingClosedError(PvpVoteError):
    """Raised by ``cast_vote`` outside the ballot's own casting candles."""


class DuplicateVoteError(PvpVoteError):
    """Raised by ``cast_vote`` for a second vote from one ``voter``."""


class RollExceededError(PvpVoteError):
    """Raised by ``cast_vote`` for a vote past ``eligible_at_call`` votes."""


class EarlyResolutionError(PvpVoteError):
    """Raised by ``resolve`` before the ballot's own ``resolving_turn``."""


class SettledBallotError(PvpVoteError):
    """Raised by ``cast_vote`` and ``resolve`` for a ballot already resolved."""


@dataclass
class PvpBallot:
    """One world's PvP vote: ``called_by``, the roll, every vote and the outcome.

    ``called_turn`` and ``resolved_turn`` are world-turn indices, and
    ``window_turn`` is the event clock's first casting candle.
    """

    world_id: str
    called_by: str
    called_turn: int
    eligible_at_call: int
    window_turn: Turn
    votes: dict[str, bool] = field(default_factory=dict)
    resolved_turn: int | None = None
    carried: bool | None = None

    @property
    def resolving_turn(self) -> int:
        """The world turn this ballot settles on, ``RESOLUTION_WORLD_TURNS`` on."""
        return self.called_turn + RESOLUTION_WORLD_TURNS

    @property
    def window_seconds(self) -> int:
        """The seconds ``CASTING_WINDOW_TURNS`` of ``window_turn``'s candle span."""
        return CASTING_WINDOW_TURNS * self.window_turn.variant.turn_seconds

    @property
    def window_closes_at(self) -> float:
        """The epoch second the last casting candle closes, on the event clock."""
        return self.window_turn.opened_at + self.window_seconds

    def casting_open(self, at_epoch: float) -> bool:
        """Whether ``at_epoch`` falls inside this ballot's own casting candles."""
        return self.window_turn.opened_at <= float(at_epoch) < self.window_closes_at

    @property
    def cast(self) -> int:
        """The votes in ``votes``, for and against together."""
        return len(self.votes)

    @property
    def votes_for(self) -> int:
        """The entries in ``votes`` cast for PvP."""
        return sum(1 for support in self.votes.values() if support)

    @property
    def votes_against(self) -> int:
        """The entries in ``votes`` cast against PvP."""
        return self.cast - self.votes_for

    @property
    def carry_threshold(self) -> int:
        """The whole votes two thirds of ``eligible_at_call`` takes, rounding up."""
        scaled = self.eligible_at_call * CARRY_NUMERATOR
        return -(-scaled // CARRY_DENOMINATOR)

    @property
    def quorum_reached(self) -> bool:
        """Whether ``cast`` reaches two thirds of ``eligible_at_call``."""
        return self.cast * CARRY_DENOMINATOR >= self.eligible_at_call * CARRY_NUMERATOR

    @property
    def would_carry(self) -> bool:
        """Whether ``votes_for`` reaches two thirds of ``eligible_at_call``."""
        return (
            self.votes_for * CARRY_DENOMINATOR
            >= self.eligible_at_call * CARRY_NUMERATOR
        )


@dataclass(frozen=True)
class PvpMode:
    """One world's PvP mode, begun on ``began_turn`` for ``PVP_MODE_WORLD_TURNS``."""

    world_id: str
    began_turn: int

    @property
    def expires_turn(self) -> int:
        """The world turn this mode lapses on, moved only by another carried ballot."""
        return self.began_turn + PVP_MODE_WORLD_TURNS

    def holds(self, world_turn: int) -> bool:
        """Whether ``world_turn`` falls inside this mode's own span."""
        return self.began_turn <= int(world_turn) < self.expires_turn


def call_vote(
    world_id: str,
    called_by: str,
    called_turn: int,
    eligible_at_call: int,
    window_open_epoch: float,
    last_called_turn: int | None = None,
) -> PvpBallot:
    """Open a ``PvpBallot`` on world turn ``called_turn``, refusing an early call.

    ``eligible_at_call`` is every participant in the world and
    ``window_open_epoch`` seats the first casting candle on the event clock.
    """
    roll = int(eligible_at_call)
    if roll < MIN_ELIGIBLE_ROLL:
        refusal = (
            f"a roll of {roll} participants carries no vote in {world_id}; two "
            f"thirds of the whole world must vote for PvP and a roll below "
            f"{MIN_ELIGIBLE_ROLL} has nobody to count"
        )
        raise EmptyRollError(refusal)
    turn = int(called_turn)
    if last_called_turn is not None:
        elapsed = turn - int(last_called_turn)
        if elapsed < VOTE_CADENCE_WORLD_TURNS:
            refusal = (
                f"{world_id} last called a PvP vote on world turn "
                f"{int(last_called_turn)} and turn {turn} is {elapsed} turns "
                f"later; one vote is put forth every "
                f"{VOTE_CADENCE_WORLD_TURNS} world turns"
            )
            raise VoteCadenceError(refusal)
    ballot = PvpBallot(
        world_id=world_id,
        called_by=called_by,
        called_turn=turn,
        eligible_at_call=roll,
        window_turn=turn_at(CASTING_VARIANT, window_open_epoch),
    )
    logger.info(
        "%s called a PvP vote on world turn %d, resolving on %d; %d of %d "
        "participants carry it, casting open to epoch %.0f",
        called_by,
        ballot.called_turn,
        ballot.resolving_turn,
        ballot.carry_threshold,
        ballot.eligible_at_call,
        ballot.window_closes_at,
    )
    return ballot


def cast_vote(ballot: PvpBallot, voter: str, at_epoch: float, *, support: bool) -> int:
    """Record ``voter``'s one vote in the casting window, returning ``ballot.cast``."""
    if ballot.resolved_turn is not None:
        refusal = (
            f"the PvP vote in {ballot.world_id} resolved on world turn "
            f"{ballot.resolved_turn} and carried={ballot.carried}; no vote is "
            f"recorded after the boundary that settled it"
        )
        raise SettledBallotError(refusal)
    if not ballot.casting_open(at_epoch):
        refusal = (
            f"the casting window of {CASTING_WINDOW_TURNS} "
            f"{ballot.window_turn.variant.turn_timeframe} candles opened at "
            f"{ballot.window_turn.opened_at:.0f} and closed at "
            f"{ballot.window_closes_at:.0f}; it is {float(at_epoch):.0f} and "
            f"{voter} casts nothing"
        )
        raise CastingClosedError(refusal)
    if voter in ballot.votes:
        refusal = (
            f"{voter} already voted {ballot.votes[voter]} in {ballot.world_id}; "
            f"one participant holds one vote and no holding weights it"
        )
        raise DuplicateVoteError(refusal)
    if ballot.cast >= ballot.eligible_at_call:
        refusal = (
            f"{ballot.cast} votes are cast and {ballot.world_id} carried "
            f"{ballot.eligible_at_call} participants when the vote was called; "
            f"{voter} is past the roll the quorum is read against"
        )
        raise RollExceededError(refusal)
    ballot.votes[voter] = bool(support)
    logger.info(
        "%s voted %s in %s; %d of %d cast, %d for, %d needed to carry",
        voter,
        bool(support),
        ballot.world_id,
        ballot.cast,
        ballot.eligible_at_call,
        ballot.votes_for,
        ballot.carry_threshold,
    )
    return ballot.cast


def resolve(ballot: PvpBallot, at_world_turn: int) -> bool:
    """Settle ``ballot`` at or past its ``resolving_turn``, returning ``carried``."""
    if ballot.resolved_turn is not None:
        refusal = (
            f"the PvP vote in {ballot.world_id} resolved on world turn "
            f"{ballot.resolved_turn} and carried={ballot.carried}; a ballot "
            f"settles on one boundary only"
        )
        raise SettledBallotError(refusal)
    turn = int(at_world_turn)
    if turn < ballot.resolving_turn:
        refusal = (
            f"the PvP vote in {ballot.world_id} was called on world turn "
            f"{ballot.called_turn} and resolves on {ballot.resolving_turn}; "
            f"turn {turn} is inside the peaceful turn and actions placed there "
            f"resolve peacefully"
        )
        raise EarlyResolutionError(refusal)
    ballot.resolved_turn = turn
    ballot.carried = ballot.would_carry
    logger.info(
        "the PvP vote in %s resolved on world turn %d carried=%s; %d of %d "
        "cast, %d for, %d against, quorum=%s, %d needed",
        ballot.world_id,
        turn,
        ballot.carried,
        ballot.cast,
        ballot.eligible_at_call,
        ballot.votes_for,
        ballot.votes_against,
        ballot.quorum_reached,
        ballot.carry_threshold,
    )
    return ballot.carried


def mode_from(ballot: PvpBallot) -> PvpMode | None:
    """Return the ``PvpMode`` a carried ``ballot`` begins, or None."""
    if not ballot.carried:
        return None
    return PvpMode(world_id=ballot.world_id, began_turn=ballot.resolving_turn)


def may_destroy(
    actor: str,
    target: str,
    world_turn: int,
    mode: PvpMode | None = None,
    *,
    pvp_event: bool = False,
) -> bool:
    """Whether ``actor`` may destroy ``target``'s Vessels on world turn ``world_turn``.

    True only while ``mode`` holds that world turn or ``pvp_event`` is set, and
    never for ``actor`` against its own.
    """
    if actor == target:
        return False
    in_mode = mode is not None and mode.holds(world_turn)
    return bool(in_mode or pvp_event)


def ballot_row(ballot: PvpBallot) -> dict:
    """``ballot`` as a JSON-safe dict, carrying every vote and the outcome."""
    return {
        "world_id": ballot.world_id,
        "called_by": ballot.called_by,
        "called_turn": ballot.called_turn,
        "resolving_turn": ballot.resolving_turn,
        "resolved_turn": ballot.resolved_turn,
        "eligible_at_call": ballot.eligible_at_call,
        "window_turn_index": ballot.window_turn.index,
        "window_timeframe": ballot.window_turn.variant.turn_timeframe,
        "window_opened_at": ballot.window_turn.opened_at,
        "window_closes_at": ballot.window_closes_at,
        "casting_window_turns": CASTING_WINDOW_TURNS,
        "votes": dict(ballot.votes),
        "cast": ballot.cast,
        "votes_for": ballot.votes_for,
        "votes_against": ballot.votes_against,
        "carry_threshold": ballot.carry_threshold,
        "quorum_reached": ballot.quorum_reached,
        "carried": ballot.carried,
    }
