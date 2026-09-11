"""Entering a dungeon, leaving one, and the clock a participant is on either side.

``DUNGEON_MODES`` reads ``poa_modes.EventMode.has_map``, and
``event_turns_per_world_turn`` refuses a world turn the event candle leaves a
remainder of. ``DungeonRegister.enter`` takes one ``EntryRequest``, refuses a
party ``world_movement.mover_locator`` does not place at the dungeon and writes
one ``DungeonEntry``; ``leave`` writes the matching ``DungeonExit``, and
``clock_of`` answers ``EVENT_CLOCK`` inside an open entry and ``WORLD_CLOCK``
outside.
``ABSENT_MECHANISMS`` names what a dungeon still lacks, the interior and combat
among them.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..core.io_utils import atomic_write_json
from .consecration import CLOCK, WORLD_TURN_SECONDS_ABSENT
from .poa_modes import (
    MODES,
    EventMode,
    EventVariant,
    PoaModeError,
    TurnSeat,
    seat_at,
    turn_at,
    variant_of,
)
from .world_grid import GridPosition
from .world_turn import FIRST_TURN_INDEX

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .army_command import Party
    from .world_grid import PoaWorld, WorldFact
    from .world_movement import WorldJourneys

logger = logging.getLogger("acervator.dungeon_entry")

#: The clock outside a dungeon, the name ``consecration`` already declares.
WORLD_CLOCK = CLOCK

#: The clock inside a dungeon, one candle of ``EventVariant.turn_timeframe``.
EVENT_CLOCK = "event turn"

#: The two clocks a participant can be on. There is no third.
CLOCKS: tuple[str, ...] = (WORLD_CLOCK, EVENT_CLOCK)

#: The modes held at a map locator, read off ``EventMode.has_map``.
DUNGEON_MODES: tuple[EventMode, ...] = tuple(mode for mode in MODES if mode.has_map)

#: Every dungeon mode's code, in the order ``MODES`` declares them.
DUNGEON_MODE_CODES: tuple[str, ...] = tuple(mode.code for mode in DUNGEON_MODES)

#: The modes held nowhere on the map, the arena every participant starts on.
ARENA_MODES: tuple[EventMode, ...] = tuple(mode for mode in MODES if not mode.has_map)

#: Every arena mode's code, in the order ``MODES`` declares them.
ARENA_MODE_CODES: tuple[str, ...] = tuple(mode.code for mode in ARENA_MODES)

#: What a dungeon is addressed by here: a locator, and the kind its fact carries.
DUNGEON_IS_A_LOCATOR = (
    "no module declares a dungeon. world_grid.WorldFact carries a kind and that "
    "kind is caller text with no declared values, so a dungeon is the locator a "
    "fact sits at plus the kind whoever discovered it named"
)

DUNGEON_STORE_VERSION = 1
DEFAULT_DUNGEON_PATH = Path.home() / ".acervator" / "poa_dungeon_entries.json"


class DungeonEntryError(RuntimeError):
    """Base for every refusal this module raises."""


class NotADungeonError(DungeonEntryError):
    """Raised by ``require_dungeon`` for a mode held at no map locator."""


class PartyModeError(DungeonEntryError):
    """Raised by ``enter`` for a party formed in a mode other than the variant's."""


class UndiscoveredDungeonError(DungeonEntryError):
    """Raised by ``enter`` for a locator the party's leader holds no reference to."""


class AlreadyInsideError(DungeonEntryError):
    """Raised by ``enter`` for a member an open entry already holds."""


class PartyScatteredError(DungeonEntryError):
    """Raised by ``enter`` for a member ``mover_locator`` does not stand at the dungeon."""


class EntryHeldError(DungeonEntryError):
    """Raised by ``enter`` for an entry id the register already holds."""


class UnknownEntryError(DungeonEntryError):
    """Raised by ``entry`` for an entry id the register does not hold."""


class NotInsideError(DungeonEntryError):
    """Raised by ``leave`` for an entry a ``DungeonExit`` already closed."""


class ClockOrderError(DungeonEntryError):
    """Raised by ``leave`` for a world turn or an epoch before the entry's own."""


class ClockNestingError(DungeonEntryError):
    """Raised by ``event_turns_per_world_turn`` for a remainder over whole candles."""


#: What rules a dungeon's inside. Nothing does, and the reading is the operator's.
INTERIOR_ABSENT = (
    "a dungeon's inside is unbuilt and the operator's ruling is owed. Two "
    "readings exist: a dungeon is a place ON the grid, so a participant keeps "
    "its square and its step and nothing new is needed; or a dungeon is a "
    "separate space with its own coordinates, a second grid with its own "
    "viewrange and positions. An entry here names a grid locator and no inside, "
    "so either reading can follow it"
)

#: What resolves a fight inside a dungeon. Nothing does.
COMBAT_ABSENT = (
    "nothing resolves a fight. monster_table declares tiers and entity_stats "
    "declares blocks, and no module turns two of them into a result"
)

#: What ends a Vessel inside a dungeon. Nothing does, and a round has no length.
PERMADEATH_ABSENT = (
    "the operator's ten-round window has no code and a round has no declared "
    "length, so entering a dungeon costs nothing. vessels.ABSENT_MECHANISMS "
    "names permadeath for the same gap"
)

#: What draws a dungeon. Nothing here, and the screen files are another unit's.
TACTICAL_MAP_ABSENT = (
    "this module draws nothing. The operator's map click opens the map subtab "
    "and the screen files belong to another unit"
)

#: What happens when a party loses a member inside. Nothing states it.
MEMBER_LOSS_ABSENT = (
    "an entry holds the whole party and one exit closes it. party_locators reads "
    "where every member stood at entry, and no module writes a position inside a "
    "dungeon, so there is no place a member could be lost at. Whether one member "
    "leaves alone, and what a party of none becomes, is unanswered"
)

#: What happens when the world turn closes while a party is inside. Nothing states it.
WORLD_TURN_CLOSE_ABSENT = (
    "an entry records the world turn it left and an exit the world turn it "
    "returned to, and nothing acts on a world turn closing in between. The "
    "operator has written no rule for it"
)

#: Whether every member stands where the dungeon is, and what a still member lacks.
MEMBER_POSITION_ABSENT = (
    "enter reads every member's own locator through party_locators, which calls "
    "world_movement.mover_locator one member at a time, and PartyScatteredError "
    "refuses a party not all standing at the dungeon's own locator. What is still "
    "absent is a place for a member that has walked nowhere: such a member holds "
    "no locator at all and is refused rather than placed, because nothing records "
    "a participant standing still at the arena every participant starts on, and "
    "nothing holds a member in place between the world turn the check reads and "
    "the entry itself"
)

#: What every absent mechanism waits on, one entry each.
ABSENT_MECHANISMS: dict[str, str] = {
    "interior": INTERIOR_ABSENT,
    "combat": COMBAT_ABSENT,
    "permadeath": PERMADEATH_ABSENT,
    "tactical_map": TACTICAL_MAP_ABSENT,
    "member_loss": MEMBER_LOSS_ABSENT,
    "member_position": MEMBER_POSITION_ABSENT,
    "world_turn_close": WORLD_TURN_CLOSE_ABSENT,
    "world_turn_seconds": WORLD_TURN_SECONDS_ABSENT,
    "dungeon_object": DUNGEON_IS_A_LOCATOR,
}

#: What binds this module into the package, and what that leaves owed.
EXPORT_OWED = (
    "src/competition/__init__.py imports dungeon_entry and lists its names in "
    "__all__, so report_unbound_modules no longer logs this module and every form "
    "is reachable as src.competition.<name>. A name this module repeats from a "
    "module bound above it stays unexported and is reached by importing "
    "src.competition.dungeon_entry directly"
)


def _as_identifier(value: object, name: str) -> str:
    """Return ``value`` as a non-blank string; every other value raises."""
    if type(value) is not str or not value.strip():
        refusal = f"{name} must be a non-empty string, got {value!r}"
        raise DungeonEntryError(refusal)
    return value.strip()


def _as_turn(value: object, name: str) -> int:
    """Return ``value`` as a whole index at or above ``FIRST_TURN_INDEX``."""
    refusal = f"{name} must be a whole turn index, got {value!r}"
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise DungeonEntryError(refusal)
    try:
        turn = int(value)
    except ValueError as exc:
        raise DungeonEntryError(refusal) from exc
    if turn < FIRST_TURN_INDEX:
        below = (
            f"{name} of {turn} is below {FIRST_TURN_INDEX}, the first index "
            f"either clock counts"
        )
        raise DungeonEntryError(below)
    return turn


def _as_epoch(value: object, name: str) -> float:
    """Return ``value`` as an epoch second at or after zero."""
    refusal = f"{name} must be an epoch second, got {value!r}"
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise DungeonEntryError(refusal)
    try:
        seconds = float(value)
    except ValueError as exc:
        raise DungeonEntryError(refusal) from exc
    if seconds < 0:
        before = f"{name} of {seconds} is before the epoch"
        raise DungeonEntryError(before)
    return seconds


def is_dungeon_mode(mode: EventMode) -> bool:
    """Answer whether ``mode`` is one of the ``DUNGEON_MODES`` a map locator holds."""
    return mode in DUNGEON_MODES


def require_dungeon(variant: EventVariant) -> EventVariant:
    """Return ``variant`` when its mode holds a map, refusing every arena mode."""
    if is_dungeon_mode(variant.mode):
        return variant
    refusal = (
        f"{variant.mode.label} is held at no map locator, so nothing is entered "
        f"in it. Only [{', '.join(DUNGEON_MODE_CODES)}] hold a dungeon; "
        f"[{', '.join(ARENA_MODE_CODES)}] run at the arena every participant "
        f"starts on"
    )
    raise NotADungeonError(refusal)


def dungeon_variant(code: str, *, elite: bool = False) -> EventVariant:
    """Return the variant ``variant_of`` builds for ``code``, refusing an arena mode."""
    return require_dungeon(variant_of(code, elite))


def event_turns_per_world_turn(
    variant: EventVariant,
    world_turn_seconds: object,
) -> int:
    """Return the ``variant`` event turns one world turn of that length holds.

    Raises ``ClockNestingError`` unless the event candle divides the world turn
    whole; a remainder would seat a participant for part of a turn.
    """
    event_seconds = variant.turn_seconds
    not_seconds = f"a world turn of {world_turn_seconds!r} is not a count of seconds"
    if isinstance(world_turn_seconds, bool) or not isinstance(
        world_turn_seconds,
        (int, str),
    ):
        raise ClockNestingError(not_seconds)
    try:
        world_seconds = int(world_turn_seconds)
    except ValueError as exc:
        raise ClockNestingError(not_seconds) from exc
    if world_seconds <= 0:
        empty = (
            f"a world turn of {world_seconds}s holds no "
            f"{variant.turn_timeframe} candle"
        )
        raise ClockNestingError(empty)
    # An hour of world turn divides whole by both candles: 12 at 5m, 60 at 1m.
    whole, remainder = divmod(world_seconds, event_seconds)
    if remainder:
        refusal = (
            f"a world turn of {world_seconds}s holds {whole} whole "
            f"{variant.turn_timeframe} candles and {remainder}s over; the two "
            f"clocks nest as exact multiples or a participant inside holds part "
            f"of a turn"
        )
        raise ClockNestingError(refusal)
    return whole


@dataclass(frozen=True)
class EntryRequest:
    """What one entry names: who enters, in which variant, where, and on which turns.

    ``world_turn`` is the ``WORLD_CLOCK`` index the party leaves and ``at_epoch``
    is the second the ``EVENT_CLOCK`` seat is taken at.
    """

    party: Party
    variant: EventVariant
    layer: int
    position: GridPosition
    world_turn: int
    at_epoch: float


@dataclass(frozen=True)
class DungeonEntry:
    """One party's entry: who, which locator, the world turn left, the event turn.

    ``variant`` and ``seat`` rebuild the event clock from the stored codes, so an
    entry is reconstructible from ``to_dict`` alone.
    """

    entry_id: str
    world_id: str
    fact_id: str
    locator: str
    layer: int
    square_index: int
    step_x: int
    step_y: int
    kind: str
    mode_code: str
    elite: bool
    leader: str
    members: tuple[str, ...]
    entered_world_turn: int
    entered_event_turn: int
    entered_at: float

    @property
    def variant(self) -> EventVariant:
        """Return the ``EventVariant`` ``mode_code`` and ``elite`` name."""
        return variant_of(self.mode_code, self.elite)

    @property
    def variant_code(self) -> str:
        """Return the event type's own code, carrying the Elite suffix."""
        return self.variant.code

    @property
    def party_size(self) -> int:
        """Return how many addresses ``members`` holds."""
        return len(self.members)

    @property
    def seat(self) -> TurnSeat:
        """Return the ``TurnSeat`` this entry took on the event clock."""
        return seat_at(self.variant, self.entered_at)

    @property
    def position(self) -> GridPosition:
        """Return the ``GridPosition`` this entry was taken at."""
        return GridPosition(self.square_index, self.step_x, self.step_y)

    def holds(self, address: object) -> bool:
        """Answer whether ``members`` carries ``address``."""
        return str(address).strip() in self.members

    def event_turn_at(self, at_epoch: object) -> int:
        """Return the index of this entry's own event turn at ``at_epoch``."""
        return turn_at(self.variant, _as_epoch(at_epoch, "at_epoch")).index

    def to_dict(self) -> dict:
        """Return this entry as a JSON-safe dict ``from_dict`` rebuilds."""
        return {
            "entry_id": self.entry_id,
            "world_id": self.world_id,
            "fact_id": self.fact_id,
            "locator": self.locator,
            "layer": self.layer,
            "square_index": self.square_index,
            "step_x": self.step_x,
            "step_y": self.step_y,
            "kind": self.kind,
            "mode_code": self.mode_code,
            "elite": self.elite,
            "leader": self.leader,
            "members": list(self.members),
            "entered_world_turn": self.entered_world_turn,
            "entered_event_turn": self.entered_event_turn,
            "entered_at": self.entered_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DungeonEntry:
        """Return an entry rebuilt from a dict written by ``to_dict``."""
        return cls(
            entry_id=str(d["entry_id"]),
            world_id=str(d["world_id"]),
            fact_id=str(d["fact_id"]),
            locator=str(d["locator"]),
            layer=int(d["layer"]),
            square_index=int(d["square_index"]),
            step_x=int(d["step_x"]),
            step_y=int(d["step_y"]),
            kind=str(d["kind"]),
            mode_code=str(d["mode_code"]),
            elite=bool(d["elite"]),
            leader=str(d["leader"]),
            members=tuple(str(member) for member in (d.get("members") or [])),
            entered_world_turn=int(d["entered_world_turn"]),
            entered_event_turn=int(d["entered_event_turn"]),
            entered_at=float(d["entered_at"]),
        )


@dataclass(frozen=True)
class DungeonExit:
    """One entry's return to the world clock, on both turn indexes at once."""

    entry_id: str
    left_world_turn: int
    left_event_turn: int
    left_at: float

    def to_dict(self) -> dict:
        """Return this exit as a JSON-safe dict ``from_dict`` rebuilds."""
        return {
            "entry_id": self.entry_id,
            "left_world_turn": self.left_world_turn,
            "left_event_turn": self.left_event_turn,
            "left_at": self.left_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> DungeonExit:
        """Return an exit rebuilt from a dict written by ``to_dict``."""
        return cls(
            entry_id=str(d["entry_id"]),
            left_world_turn=int(d["left_world_turn"]),
            left_event_turn=int(d["left_event_turn"]),
            left_at=float(d["left_at"]),
        )


def entry_id_for(fact_id: str, leader: str, world_turn: int, event_turn: int) -> str:
    """Return the identifier one leader's entry at ``fact_id`` holds on both turns."""
    return f"{fact_id}:{leader}:w{world_turn}:e{event_turn}"


class DungeonRegister:
    """Holds every ``DungeonEntry`` and the ``DungeonExit`` that closed it.

    ``enter`` reads a ``world_grid.PoaWorld`` for the locator and an
    ``EntryRequest`` for who enters, and ``clock_of`` answers which of ``CLOCKS``
    an address is on.
    """

    def __init__(self, store_path: str | Path | None = None) -> None:
        """Point the register at ``store_path`` or ``DEFAULT_DUNGEON_PATH``."""
        self._path: Path = Path(store_path) if store_path else DEFAULT_DUNGEON_PATH
        self._entries: dict[str, DungeonEntry] = {}
        self._exits: dict[str, DungeonExit] = {}
        self._lock = threading.RLock()

    @property
    def store_path(self) -> Path:
        """Return the file ``save`` writes and ``load`` replays."""
        return self._path

    # -- Entering, which is the clock switch ---------------------------------

    def enter(
        self,
        world: PoaWorld,
        request: EntryRequest,
        journeys: WorldJourneys,
    ) -> DungeonEntry:
        """Move ``request.party`` off ``WORLD_CLOCK`` onto the ``EVENT_CLOCK``.

        The locator is derived from the request's own position and layer, every
        member's own locator is read from ``journeys``, and the refusals are
        ``NotADungeonError``, ``PartyModeError``, ``UndiscoveredDungeonError``,
        ``PartyScatteredError``, ``AlreadyInsideError`` and ``EntryHeldError``.
        """
        variant = require_dungeon(request.variant)
        party = request.party
        self._require_party_mode(party, variant)
        entered_world_turn = _as_turn(request.world_turn, "world_turn")
        entered_at = _as_epoch(request.at_epoch, "at_epoch")
        leader = _as_identifier(party.leader, "party.leader")
        members = tuple(_as_identifier(member, "member") for member in party.members)

        world_id = self._world_id_of(world)
        position = request.position
        locator = position.locator(int(request.layer))
        fact_id = f"{world_id}:{locator}"
        fact = self._require_discovered(world, world_id, fact_id, leader, variant)
        self._require_party_at(
            self.party_locators(journeys, world_id, members, entered_world_turn),
            locator,
            leader,
            variant,
        )

        seat = seat_at(variant, entered_at)
        entered_event_turn = seat.turn.index
        entry_id = entry_id_for(
            fact_id,
            leader,
            entered_world_turn,
            entered_event_turn,
        )
        entry = DungeonEntry(
            entry_id=entry_id,
            world_id=world_id,
            fact_id=fact_id,
            locator=locator,
            layer=int(request.layer),
            square_index=position.square_index,
            step_x=position.step_x,
            step_y=position.step_y,
            kind=fact.kind,
            mode_code=variant.mode.code,
            elite=bool(variant.elite),
            leader=leader,
            members=members,
            entered_world_turn=entered_world_turn,
            entered_event_turn=entered_event_turn,
            entered_at=entered_at,
        )
        with self._lock:
            self._require_free(members, entry_id)
            if entry_id in self._entries:
                refusal = (
                    f"{leader} already holds entry {entry_id}; one leader enters "
                    f"{fact_id} once on {WORLD_CLOCK} {entered_world_turn} and "
                    f"{variant.turn_timeframe} turn {entered_event_turn}"
                )
                raise EntryHeldError(refusal)
            self._entries[entry_id] = entry
            self.save()
        logger.info(
            "%s took %d into %s at %s, off %s %d onto %s %d of the %s candle",
            leader,
            entry.party_size,
            fact.kind,
            locator,
            WORLD_CLOCK,
            entered_world_turn,
            EVENT_CLOCK,
            entered_event_turn,
            variant.turn_timeframe,
        )
        return entry

    def leave(self, entry_id: str, world_turn: int, at_epoch: float) -> DungeonExit:
        """Return the whole party of ``entry_id`` to ``WORLD_CLOCK``.

        Raises ``NotInsideError`` for an entry an exit already closed, and
        ``ClockOrderError`` for a turn or an epoch before the entry's own.
        """
        entry = self.entry(entry_id)
        left_world_turn = _as_turn(world_turn, "world_turn")
        left_at = _as_epoch(at_epoch, "at_epoch")
        with self._lock:
            held = self._exits.get(entry.entry_id)
            if held is not None:
                refusal = (
                    f"entry {entry.entry_id} returned to {WORLD_CLOCK} "
                    f"{held.left_world_turn} already; nothing is inside it to "
                    f"bring out a second time"
                )
                raise NotInsideError(refusal)
            self._require_later(entry, left_world_turn, left_at)
            left = DungeonExit(
                entry_id=entry.entry_id,
                left_world_turn=left_world_turn,
                left_event_turn=entry.event_turn_at(left_at),
                left_at=left_at,
            )
            self._exits[entry.entry_id] = left
            self.save()
        logger.info(
            "%s brought %d out of %s, off %s %d back onto %s %d",
            entry.leader,
            entry.party_size,
            entry.locator,
            EVENT_CLOCK,
            left.left_event_turn,
            WORLD_CLOCK,
            left.left_world_turn,
        )
        return left

    # -- Which clock, the one question this module answers --------------------

    def clock_of(self, address: object) -> str:
        """Return the clock ``address`` answers to, one of ``CLOCKS``."""
        return WORLD_CLOCK if self.open_entry_of(address) is None else EVENT_CLOCK

    def is_inside(self, address: object) -> bool:
        """Answer whether an open entry holds ``address``."""
        return self.open_entry_of(address) is not None

    def open_entry_of(self, address: object) -> DungeonEntry | None:
        """Return the one open entry holding ``address``, or None while none does."""
        wallet = str(address).strip()
        with self._lock:
            for key in sorted(self._entries):
                if key in self._exits:
                    continue
                entry = self._entries[key]
                if wallet in entry.members:
                    return entry
        return None

    def open_entries(self) -> tuple[DungeonEntry, ...]:
        """Return every entry no exit has closed, by entry id."""
        with self._lock:
            return tuple(
                self._entries[key]
                for key in sorted(self._entries)
                if key not in self._exits
            )

    def is_open(self, entry_id: str) -> bool:
        """Answer whether ``entry_id`` is held and no exit has closed it."""
        key = _as_identifier(entry_id, "entry_id")
        with self._lock:
            return key in self._entries and key not in self._exits

    # -- Readers -------------------------------------------------------------

    def entry(self, entry_id: str) -> DungeonEntry:
        """Return the ``DungeonEntry`` ``entry_id`` names, refusing one nobody holds."""
        key = _as_identifier(entry_id, "entry_id")
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            refusal = f"no dungeon entry {key!r} is held"
            raise UnknownEntryError(refusal)
        return entry

    def exit_of(self, entry_id: str) -> DungeonExit | None:
        """Return the ``DungeonExit`` closing ``entry_id``, or None while it is open."""
        entry = self.entry(entry_id)
        with self._lock:
            return self._exits.get(entry.entry_id)

    def entry_ids(self) -> tuple[str, ...]:
        """Return every entry id this register holds, sorted."""
        with self._lock:
            return tuple(sorted(self._entries))

    def entry_rows(self) -> list[dict]:
        """Return every entry with the clock it sits on, as a surface would serve it."""
        rows = []
        with self._lock:
            for key in sorted(self._entries):
                entry = self._entries[key]
                left = self._exits.get(key)
                rows.append(
                    {
                        "entry_id": entry.entry_id,
                        "world_id": entry.world_id,
                        "locator": entry.locator,
                        "kind": entry.kind,
                        "variant_code": entry.variant_code,
                        "mode_code": entry.mode_code,
                        "elite": entry.elite,
                        "leader": entry.leader,
                        "party_size": entry.party_size,
                        "members": list(entry.members),
                        "entered_world_turn": entry.entered_world_turn,
                        "entered_event_turn": entry.entered_event_turn,
                        "turn_timeframe": entry.variant.turn_timeframe,
                        "clock": WORLD_CLOCK if left else EVENT_CLOCK,
                        "left_world_turn": (
                            None if left is None else left.left_world_turn
                        ),
                        "left_event_turn": (
                            None if left is None else left.left_event_turn
                        ),
                    },
                )
        return rows

    def clock_rows(self, addresses: Sequence[object]) -> list[dict]:
        """Return the clock each of ``addresses`` answers to, with its entry."""
        rows = []
        for address in addresses:
            wallet = str(address).strip()
            entry = self.open_entry_of(wallet)
            rows.append(
                {
                    "address": wallet,
                    "clock": WORLD_CLOCK if entry is None else EVENT_CLOCK,
                    "entry_id": None if entry is None else entry.entry_id,
                    "locator": None if entry is None else entry.locator,
                },
            )
        return rows

    def party_locators(
        self,
        journeys: WorldJourneys,
        world_id: str,
        members: Sequence[object],
        world_turn: int,
    ) -> dict[str, str | None]:
        """Return the locator each of ``members`` stands at on ``world_turn``.

        ``world_movement.mover_locator`` answers one member at a time, so this is
        the one reader that holds a whole party's places together, and a member
        with no journey leg open by ``world_turn`` holds None.
        """
        standing: dict[str, str | None] = {}
        for member in members:
            wallet = _as_identifier(member, "member")
            standing[wallet] = journeys.mover_locator(world_id, wallet, world_turn)
        return standing

    def absent_notes(self) -> dict:
        """Return every mechanism ``ABSENT_MECHANISMS`` names and what it waits on."""
        return dict(ABSENT_MECHANISMS)

    # -- Refusals ------------------------------------------------------------

    def _require_party_mode(self, party: Party, variant: EventVariant) -> None:
        """Raise unless ``party`` was formed in the mode ``variant`` runs."""
        if party.mode.code == variant.mode.code:
            return
        refusal = (
            f"this party was formed for {party.mode.label} and admits "
            f"{party.mode.party_min} to {party.mode.party_max}; entering a "
            f"{variant.mode.label} needs a party formed in {variant.mode.code}"
        )
        raise PartyModeError(refusal)

    def _require_party_at(
        self,
        standing: dict[str, str | None],
        locator: str,
        leader: str,
        variant: EventVariant,
    ) -> None:
        """Raise unless every member in ``standing`` stands at ``locator`` itself.

        A member holding None has walked no leg by the entry's own world turn, so
        no journey places it at ``locator`` and it is refused beside the members
        standing somewhere else.
        """
        elsewhere = [
            f"{member} at "
            + ("no journey leg open by this turn" if held is None else held)
            for member, held in standing.items()
            if held != locator
        ]
        if not elsewhere:
            return
        refusal = (
            f"{leader} leads this {variant.mode.label} into {locator} and "
            f"{len(elsewhere)} of {len(standing)} members stand away from it: "
            f"{'; '.join(elsewhere)}; a party walks into a dungeon from the "
            f"dungeon's own position"
        )
        raise PartyScatteredError(refusal)

    def _require_discovered(
        self,
        world: PoaWorld,
        world_id: str,
        fact_id: str,
        leader: str,
        variant: EventVariant,
    ) -> WorldFact:
        """Raise unless ``leader`` references ``fact_id``, then return that fact.

        The leader navigates, so the leader's own discovery is what admits a party.
        """
        known = world.knows(world_id, leader)
        if fact_id not in known:
            refusal = (
                f"{leader} leads this {variant.mode.label} and holds no "
                f"reference to {fact_id}; a dungeon is entered only where it has "
                f"been discovered, and this leader knows {len(known)} place(s)"
            )
            raise UndiscoveredDungeonError(refusal)
        return world.fact(world_id, fact_id)

    def _require_free(self, members: tuple[str, ...], entry_id: str) -> None:
        """Raise for any member of ``members`` an open entry already holds."""
        for member in members:
            held = self.open_entry_of(member)
            if held is None:
                continue
            refusal = (
                f"{member} is inside {held.locator} on entry {held.entry_id} and "
                f"answers to the {EVENT_CLOCK}; entry {entry_id} would put one "
                f"participant on two event clocks at once"
            )
            raise AlreadyInsideError(refusal)

    def _require_later(
        self,
        entry: DungeonEntry,
        left_world_turn: int,
        left_at: float,
    ) -> None:
        """Raise for a world turn or an epoch before ``entry`` was taken."""
        if left_world_turn < entry.entered_world_turn:
            earlier_turn = (
                f"entry {entry.entry_id} was taken on {WORLD_CLOCK} "
                f"{entry.entered_world_turn} and is not left on {left_world_turn}"
            )
            raise ClockOrderError(earlier_turn)
        if left_at < entry.entered_at:
            earlier_epoch = (
                f"entry {entry.entry_id} was taken at {entry.entered_at:.0f} and "
                f"is not left at {left_at:.0f}"
            )
            raise ClockOrderError(earlier_epoch)

    def _world_id_of(self, world: PoaWorld) -> str:
        """Return the one world ``world`` holds, refusing none and refusing several."""
        held = tuple(world.world_ids)
        if len(held) != 1:
            refusal = (
                f"this PoaWorld holds {len(held)} world(s) and an entry names "
                f"one; worlds: {', '.join(held) or 'none'}"
            )
            raise DungeonEntryError(refusal)
        return str(held[0])

    # -- Durability ----------------------------------------------------------

    def to_dict(self) -> dict:
        """Return every entry and exit as a JSON-safe dict ``load`` replays."""
        with self._lock:
            return {
                "version": DUNGEON_STORE_VERSION,
                "entries": [
                    self._entries[key].to_dict() for key in sorted(self._entries)
                ],
                "exits": [self._exits[key].to_dict() for key in sorted(self._exits)],
            }

    def save(self) -> None:
        """Write every entry and exit to ``store_path``."""
        payload = self.to_dict()
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(self._path, payload)
        except OSError:
            logger.exception("dungeon entries not written to %s", self._path)

    def load(self) -> DungeonRegister:
        """Replay ``store_path``, holding the register unchanged when it is empty."""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return self
        try:
            payload = json.loads(raw)
        except ValueError:
            logger.exception("dungeon entries at %s unreadable", self._path)
            return self
        entries: dict[str, DungeonEntry] = {}
        exits: dict[str, DungeonExit] = {}
        for row in payload.get("entries") or []:
            try:
                entry = DungeonEntry.from_dict(row)
            except (KeyError, TypeError, ValueError, PoaModeError):
                logger.exception("dungeon entry row skipped")
                continue
            entries[entry.entry_id] = entry
        for row in payload.get("exits") or []:
            try:
                left = DungeonExit.from_dict(row)
            except (KeyError, TypeError, ValueError):
                logger.exception("dungeon exit row skipped")
                continue
            exits[left.entry_id] = left
        with self._lock:
            self._entries = entries
            self._exits = {
                key: value for key, value in exits.items() if key in entries
            }
        logger.info(
            "replayed %d dungeon entries and %d exits from %s",
            len(self._entries),
            len(self._exits),
            self._path,
        )
        return self


def mode_rows() -> list[dict]:
    """Return every entry in ``MODES`` with whether a dungeon entry exists in it."""
    return [
        {
            "mode_code": mode.code,
            "label": mode.label,
            "is_dungeon": is_dungeon_mode(mode),
            "has_map": mode.has_map,
            "party_min": mode.party_min,
            "party_max": mode.party_max,
            "guild_required": mode.guild_required,
        }
        for mode in MODES
    ]


def nesting_rows(world_turn_seconds: object) -> list[dict]:
    """Return each dungeon variant's event turns in one world turn of that length."""
    rows = []
    for mode in DUNGEON_MODES:
        for elite in (False, True):
            variant = variant_of(mode.code, elite)
            rows.append(
                {
                    "variant_code": variant.code,
                    "turn_timeframe": variant.turn_timeframe,
                    "event_turn_seconds": variant.turn_seconds,
                    "event_turns_per_world_turn": event_turns_per_world_turn(
                        variant,
                        world_turn_seconds,
                    ),
                },
            )
    return rows
