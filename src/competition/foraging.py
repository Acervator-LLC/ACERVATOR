"""A foraging run: a Vessel standing on a square gathers the material it holds.

``derive_place_material`` reads ``world_grid.discovery_leaf`` for a square's own
locator and draws the material and the quality grade out of two windows nothing
else reads, so one square under one seed always forages the same material and
another square does not. ``ForageRegister.forage`` puts the units one run yields
into the standing Vessel's ``inventory.VesselStore`` and moves no Quintessence.
``FORAGE_YIELD_RATE_NAME`` names the working rate that sets those units,
``STANDING_POSITION_ABSENT`` names what no module records, ``ABSENT_MECHANISMS``
names what a run still does not do, and ``require_foraging`` drives the window
guard once at import.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from decimal import Decimal

from .conversion_rates import rate_named
from .inventory import (
    InventoryError,
    StoreBook,
    StoreChange,
    VesselStore,
    vessel_key,
)
from .materials import (
    MATERIALS,
    QUALITY_GRADES,
    Material,
    embedded_quintessence,
    material_named,
)
from .monster_spawn import DRAW_DIGITS as MONSTER_DRAW_DIGITS
from .monster_spawn import WINDOWS_READ as MONSTER_WINDOWS
from .monster_spawn import LocatorError, require_locator
from .quintessence_ledger import amount_text
from .vessels import Vessel
from .world_grid import (
    LEAF_DRAW_DIGITS,
    GridPosition,
    PoaWorld,
    WorldGridError,
    discovery_leaf,
    seed_commitment,
    square_xy,
)

logger = logging.getLogger("acervator.foraging")

#: Hex digits one draw here reads, half the width ``monster_spawn`` draws at.
DRAW_DIGITS = LEAF_DRAW_DIGITS // 2

#: Hex digits ``discovery_leaf`` returns, measured off the function itself.
LEAF_DIGITS = len(discovery_leaf("", ""))

#: Windows of ``DRAW_DIGITS`` hex digits one leaf holds.
LEAF_WINDOWS = LEAF_DIGITS // DRAW_DIGITS

#: The leaf window the material draw reads, the last but one.
MATERIAL_WINDOW = LEAF_WINDOWS - 2

#: The leaf window the quality draw reads, the last.
QUALITY_WINDOW = LEAF_WINDOWS - 1

#: Every window a foraging draw reads.
WINDOWS_READ: tuple[int, ...] = (MATERIAL_WINDOW, QUALITY_WINDOW)

#: The hex digits ``world_grid.committed_quintessence`` reads off a leaf.
AMOUNT_DIGITS = LEAF_DRAW_DIGITS

#: The step a forage locator names, so one square draws one material.
FORAGE_STEP = 0

#: The fewest units one run may yield.
MIN_FORAGE_UNITS = 1

#: The ``conversion_rates`` row holding the units one run yields.
FORAGE_YIELD_RATE_NAME = "material_units_per_forage_run"

#: Why a forage locator names a square's origin step and not the Vessel's own step.
SQUARE_HOLDS_ONE_MATERIAL = (
    "a square holds one material at one grade, so square_locator names the "
    "origin step of the square and a Vessel standing anywhere inside that square "
    "forages the same material; the step the Vessel stands on is read only to "
    "name the square it is in"
)

#: What no module records about where a Vessel stands, and what reads it here.
STANDING_POSITION_ABSENT = (
    "no module records where a Vessel stands. world_movement.JourneyLeg derives a "
    "position from the turn a leg opened and names a mover address, not a Vessel, "
    "so forage takes the standing GridPosition from its caller the way "
    "monster_spawn.derive_monster takes its tier weighting"
)

#: What a run banks of the Quintessence the gathered units embed, which is nothing.
FORAGE_QUINTESSENCE_UNLEDGERED = (
    "ForageRun.quintessence_embedded is read off materials.embedded_quintessence "
    "and no QuintessenceLedger movement credits the embedded bucket for it, so a "
    "run gathers units whose embedded amount no bucket records. crafting says the "
    "same about the units a recipe consumes"
)

#: What a foraging run takes part in, each note naming what stays absent.
ABSENT_MECHANISMS: tuple[str, ...] = (
    "a square that runs out",
    "a world supply of material units",
    "a turn cost",
    "encumbrance",
    "a skill",
    "a surface",
)

#: What each entry in ``ABSENT_MECHANISMS`` waits on.
ABSENT_MECHANISM_NOTES: dict[str, str] = {
    "a square that runs out": (
        "no source sets a deposit size, so the same square yields the same "
        "material and the same units on every run and nothing depletes"
    ),
    "a world supply of material units": (
        "inventory says no module counts how many units of a material a world "
        "holds, and a run adds units without deducting them from any total"
    ),
    "a turn cost": (
        "world_turn grants a pool and a run spends nothing out of it, so a run "
        "costs no turn and the operator's multi-turn reading has nothing to read"
    ),
    "encumbrance": (
        "VesselStore.weight_carried weighs what a run gathered and nothing turns "
        "that weight into a refusal or a turn point penalty; the operator's rule "
        "reads encumbrance while a Vessel moves items itself, and nothing moves one"
    ),
    "a skill": (
        "skill_ladder declares one skill and no skill gates a run, raises a yield "
        "or reaches a grade a square does not already hold"
    ),
    "a surface": (
        "the Resources subtab prints every material and that nothing holds how "
        "many units are carried, and no control on it opens a run"
    ),
}


class ForageError(RuntimeError):
    """Base for every refusal this module raises."""


class ForageLeafError(ForageError):
    """Raised by ``leaf_window`` and ``require_free_windows`` for a window misread."""


class ForageLocatorError(ForageError):
    """Raised by ``require_square_locator`` for a locator off a square's origin."""


class ForageWorldError(ForageError):
    """Raised for a ``world_id`` the ``PoaWorld`` does not hold or cannot forage."""


class SeedNotPublishedError(ForageWorldError):
    """Raised by ``forage`` while the world has not posted the seed it committed."""


class SeedCommitmentError(ForageWorldError):
    """Raised by ``forage`` for a seed that does not rebuild the world's commitment."""


class ForageSquareError(ForageError):
    """Raised by ``forage`` for a square off the layer the world declares."""


class VesselNotOnSquareError(ForageError):
    """Raised by ``forage`` when the standing Vessel is on another square."""


class ForageYieldError(ForageError):
    """Raised by ``forage_units_per_run`` while the yield rate sets no whole units."""


class ForageStoreError(ForageError):
    """Raised when the book holds no store for the Vessel, or the store refuses."""


# -- The two windows, and the digits another module already reads -------------


def digits_read_elsewhere() -> tuple[tuple[int, int], ...]:
    """Every hex-digit span of a leaf another module already draws from.

    The first span is the amount ``world_grid.committed_quintessence`` reads, and
    one span follows each window in ``monster_spawn.WINDOWS_READ``.
    """
    spans = [(0, AMOUNT_DIGITS)]
    for window in MONSTER_WINDOWS:
        start = window * MONSTER_DRAW_DIGITS
        spans.append((start, start + MONSTER_DRAW_DIGITS))
    return tuple(spans)


def digits_read_here() -> tuple[tuple[int, int], ...]:
    """The hex-digit span of each window in ``WINDOWS_READ``, in its declared order."""
    return tuple(
        (window * DRAW_DIGITS, window * DRAW_DIGITS + DRAW_DIGITS)
        for window in WINDOWS_READ
    )


def _spans_overlap(first: tuple[int, int], second: tuple[int, int]) -> bool:
    """Whether two half-open hex-digit spans share a digit."""
    return first[0] < second[1] and second[0] < first[1]


def require_free_windows() -> None:
    """Refuse a foraging window that reads digits another draw already reads.

    A window overlapping ``digits_read_elsewhere``, overlapping the other window
    in ``WINDOWS_READ``, or running past ``LEAF_DIGITS`` raises ``ForageLeafError``.
    """
    here = digits_read_here()
    for span in here:
        if span[1] > LEAF_DIGITS:
            raise ForageLeafError(
                f"a foraging window reads digits {span[0]} to {span[1]}, past the "
                f"{LEAF_DIGITS} hex digits a leaf holds",
            )
        for taken in digits_read_elsewhere():
            if _spans_overlap(span, taken):
                raise ForageLeafError(
                    f"a foraging window reads digits {span[0]} to {span[1]}, which "
                    f"the draw at digits {taken[0]} to {taken[1]} already reads; a "
                    f"square's material would follow its creature",
                )
    if _spans_overlap(here[0], here[1]):
        raise ForageLeafError(
            f"the material window reads digits {here[0]} and the quality window "
            f"{here[1]}; one square's material and its grade would be one draw",
        )


def leaf_window(leaf: str, window: int) -> int:
    """The number ``window`` reads out of ``leaf``, ``DRAW_DIGITS`` hex digits wide."""
    if not 0 <= window < LEAF_WINDOWS:
        raise ForageLeafError(
            f"window {window} sits outside the {LEAF_WINDOWS} windows of "
            f"{DRAW_DIGITS} hex digits a leaf holds",
        )
    if len(leaf) != LEAF_DIGITS:
        raise ForageLeafError(
            f"a leaf runs {LEAF_DIGITS} hex digits; {leaf!r} runs {len(leaf)}",
        )
    start = window * DRAW_DIGITS
    try:
        return int(leaf[start : start + DRAW_DIGITS], 16)
    except ValueError as exc:
        raise ForageLeafError(
            f"{leaf!r} carries a digit outside base sixteen: {exc}",
        ) from exc


def material_for_leaf(leaf: str) -> tuple[int, Material]:
    """The roll ``MATERIAL_WINDOW`` draws from ``leaf`` and the material it names."""
    roll = leaf_window(leaf, MATERIAL_WINDOW) % len(MATERIALS)
    return roll, MATERIALS[roll]


def quality_for_leaf(leaf: str) -> tuple[int, str]:
    """The roll ``QUALITY_WINDOW`` draws from ``leaf`` and the grade it names."""
    roll = leaf_window(leaf, QUALITY_WINDOW) % len(QUALITY_GRADES)
    return roll, QUALITY_GRADES[roll]


# -- The locator one square's material is drawn from -------------------------


def _as_square_index(value: object) -> int:
    """Return ``value`` as a whole square index of zero or more."""
    if type(value) is not int or value < 0:
        raise ForageSquareError(
            f"a square index must be a whole number of zero or more, got {value!r}",
        )
    return value


def _as_layer(value: object) -> int:
    """Return ``value`` as a whole layer ordinal of zero or more."""
    if type(value) is not int or value < 0:
        raise ForageSquareError(
            f"a layer must be a whole number of zero or more, got {value!r}",
        )
    return value


def square_locator(layer: object, square_index: object) -> str:
    """The text a square's own material is drawn from, its origin step on ``layer``.

    ``SQUARE_HOLDS_ONE_MATERIAL`` says why the step is the origin and not the
    Vessel's own step.
    """
    held = _as_layer(layer)
    square = _as_square_index(square_index)
    return GridPosition(square, FORAGE_STEP, FORAGE_STEP).locator(held)


def require_square_locator(locator: str) -> tuple[int, GridPosition]:
    """The layer and position ``locator`` names, refusing a step off the origin.

    ``monster_spawn.require_locator`` reads the four fields, so a forage locator
    and a monster locator are the same text in the same format.
    """
    try:
        layer, position = require_locator(locator)
    except LocatorError as exc:
        raise ForageLocatorError(
            f"{locator!r} names no place a run can read: {exc}",
        ) from exc
    if (position.step_x, position.step_y) != (FORAGE_STEP, FORAGE_STEP):
        raise ForageLocatorError(
            f"{locator!r} stands {position.step_x} and {position.step_y} steps "
            f"into its square; {SQUARE_HOLDS_ONE_MATERIAL}",
        )
    return layer, position


# -- What the place holds ----------------------------------------------------


@dataclass(frozen=True)
class ForagePlace:
    """One square's material and grade, both drawn from that square's own leaf.

    ``material_roll`` and ``quality_roll`` are the two window draws, so a reader
    rebuilds either one from ``leaf``.
    """

    locator: str
    layer: int
    square_index: int
    leaf: str
    material_name: str
    quality: str
    material_roll: int
    quality_roll: int

    @property
    def material(self) -> Material:
        """The ``MATERIALS`` entry ``material_name`` names."""
        return material_named(self.material_name)

    @property
    def quintessence_per_unit(self) -> Decimal:
        """The Quintessence one gathered unit embeds, at this place's grade."""
        return embedded_quintessence(self.material, self.quality)

    @property
    def weight_per_unit(self) -> Decimal:
        """The weight one gathered unit carries, off the material itself."""
        return self.material.weight_per_unit

    def to_dict(self) -> dict:
        """This place as a JSON-safe dict, every amount a plain string."""
        return {
            "locator": self.locator,
            "layer": self.layer,
            "square_index": self.square_index,
            "leaf": self.leaf,
            "material_name": self.material_name,
            "quality": self.quality,
            "storage_class": self.material.storage_class,
            "material_roll": self.material_roll,
            "quality_roll": self.quality_roll,
            "quintessence_per_unit": amount_text(self.quintessence_per_unit),
            "weight_per_unit": amount_text(self.weight_per_unit),
        }


def derive_place_material(seed: str, locator: str) -> ForagePlace:
    """Derive the material and grade the square ``locator`` names holds under ``seed``.

    ``world_grid.seed_commitment`` hides the seed, so a caller holding none
    derives no leaf.
    """
    held_layer, position = require_square_locator(locator)
    leaf = discovery_leaf(seed, locator)
    material_roll, material = material_for_leaf(leaf)
    quality_roll, quality = quality_for_leaf(leaf)
    place = ForagePlace(
        locator=locator,
        layer=held_layer,
        square_index=position.square_index,
        leaf=leaf,
        material_name=material.name,
        quality=quality,
        material_roll=material_roll,
        quality_roll=quality_roll,
    )
    logger.debug(
        "%s holds %s at %s, rolls %d and %d",
        locator,
        material.name,
        quality,
        material_roll,
        quality_roll,
    )
    return place


def derive_place_material_at(
    seed: str,
    layer: object,
    square_index: object,
) -> ForagePlace:
    """Derive what the square at ``square_index`` on ``layer`` holds under ``seed``."""
    return derive_place_material(seed, square_locator(layer, square_index))


# -- The units one run yields, which no source sets --------------------------


def _as_forage_units(value: object, name: str) -> int:
    """Return ``value`` as whole units at or above ``MIN_FORAGE_UNITS``.

    A figure absent, a fraction of a unit, or fewer than ``MIN_FORAGE_UNITS``
    raises ``ForageYieldError``.
    """
    if value is None:
        raise ForageYieldError(
            f"{name} carries no figure, and no run yields units until the "
            f"conversion table sets one",
        )
    if not isinstance(value, Decimal):
        raise ForageYieldError(
            f"{name} must be a Decimal, not {type(value).__name__}",
        )
    if not value.is_finite():
        raise ForageYieldError(f"{name} must be finite, got {value!r}")
    if value != value.to_integral_value():
        raise ForageYieldError(
            f"{name} of {amount_text(value)} is not a whole number of units, and "
            f"a store holds no part unit",
        )
    units = int(value)
    if units < MIN_FORAGE_UNITS:
        raise ForageYieldError(
            f"{name} of {units} is under the {MIN_FORAGE_UNITS} unit a run yields "
            f"at least",
        )
    return units


def forage_units_per_run() -> int:
    """The units one run yields, from the ``FORAGE_YIELD_RATE_NAME`` working rate."""
    entry = rate_named(FORAGE_YIELD_RATE_NAME)
    return _as_forage_units(entry.rate, FORAGE_YIELD_RATE_NAME)


def forage_yield_provenance() -> str:
    """The provenance the yield rate carries, which says who set the figure."""
    return rate_named(FORAGE_YIELD_RATE_NAME).provenance


# -- What one run did --------------------------------------------------------


@dataclass(frozen=True)
class ForageRun:
    """What one run gathered, read off the store once the units went in.

    ``quintessence_embedded`` is the amount those units embed and
    ``FORAGE_QUINTESSENCE_UNLEDGERED`` says no bucket records it.
    """

    place: ForagePlace
    vessel: Vessel
    store_key: str
    units_gathered: int
    units_held: int
    slots_used: int
    weight_carried: Decimal
    quintessence_embedded: Decimal

    def to_dict(self) -> dict:
        """This run as a JSON-safe dict, every amount a plain string."""
        return {
            "place": self.place.to_dict(),
            "vessel": self.vessel.to_dict(),
            "store_key": self.store_key,
            "units_gathered": self.units_gathered,
            "units_held": self.units_held,
            "slots_used": self.slots_used,
            "weight_carried": amount_text(self.weight_carried),
            "quintessence_embedded": amount_text(self.quintessence_embedded),
            "quintessence_note": FORAGE_QUINTESSENCE_UNLEDGERED,
        }


def _as_vessel(value: object) -> Vessel:
    """Return ``value`` as a ``Vessel``; every other type raises."""
    if not isinstance(value, Vessel):
        raise ForageError(f"a Vessel was expected, got {type(value).__name__}")
    return value


def _as_position(value: object) -> GridPosition:
    """Return ``value`` as the ``GridPosition`` a Vessel stands on."""
    if not isinstance(value, GridPosition):
        raise ForageError(
            f"a GridPosition was expected, got {type(value).__name__}; "
            f"{STANDING_POSITION_ABSENT}",
        )
    return value


def _as_world(value: object) -> PoaWorld:
    """Return ``value`` as the ``PoaWorld`` whose seed every leaf is read under."""
    if not isinstance(value, PoaWorld):
        raise ForageWorldError(
            f"a PoaWorld was expected, got {type(value).__name__}; a run reads a "
            f"leaf under the seed that world committed",
        )
    return value


def _as_store_book(value: object) -> StoreBook:
    """Return ``value`` as the ``StoreBook`` every run puts its units into."""
    if not isinstance(value, StoreBook):
        raise ForageStoreError(
            f"a StoreBook was expected, got {type(value).__name__}; a run puts "
            f"its units in the standing Vessel's own store",
        )
    return value


class ForageRegister:
    """Gathers the material one square holds into the standing Vessel's store.

    The ``PoaWorld`` and the ``StoreBook`` both arrive by construction, so a demo
    run is one register over another chain's world and another book running the
    same ``forage`` path.
    """

    def __init__(self, world: object, store_book: object) -> None:
        """Hold the world every leaf is read under and the book a run fills."""
        self._world = _as_world(world)
        self._store_book = _as_store_book(store_book)
        self._runs: list[ForageRun] = []
        self._lock = threading.RLock()

    @property
    def world(self) -> PoaWorld:
        """The world whose committed seed every run's leaf is read under."""
        return self._world

    def runs(self) -> list[ForageRun]:
        """Every run this register has made, in the order it made them."""
        with self._lock:
            return list(self._runs)

    def _store_for(self, vessel: Vessel) -> VesselStore:
        """The store the book holds for ``vessel``, under ``inventory.vessel_key``."""
        wanted = vessel_key(vessel)
        try:
            return self._store_book.store(wanted)
        except InventoryError as exc:
            raise ForageStoreError(
                f"{wanted} names no store in the book this register holds, so a "
                f"run would have nowhere to put what it gathered: {exc}",
            ) from exc

    def _require_forageable(
        self,
        seed: str,
        world_id: str,
        layer: int,
        square_index: int,
        vessel: Vessel,
    ) -> None:
        """Refuse a world, a seed, a layer or a square no run reads a leaf at.

        ``SeedNotPublishedError`` comes first, so an unpublished world never
        reaches the commitment reading.
        """
        try:
            record = self._world.world(world_id)
            published = self._world.seed_is_published(world_id)
        except WorldGridError as exc:
            raise ForageWorldError(
                f"{vessel.class_name} of {vessel.owner} cannot forage square "
                f"{square_index} of layer {layer}: {exc}",
            ) from exc
        if not published:
            raise SeedNotPublishedError(
                f"world {world_id} holds its seed under commitment "
                f"{record.commitment[:16]} and has not published it, so "
                f"{vessel.class_name} of {vessel.owner} reads no leaf at square "
                f"{square_index} of layer {layer}",
            )
        if seed_commitment(seed) != record.commitment:
            raise SeedCommitmentError(
                f"the seed offered rebuilds commitment "
                f"{seed_commitment(seed)[:16]} and world {world_id} published "
                f"{record.commitment[:16]}, so {vessel.class_name} of "
                f"{vessel.owner} reads no leaf at square {square_index} of layer "
                f"{layer}",
            )
        try:
            self._world.require_breached(world_id, layer)
        except WorldGridError as exc:
            raise ForageWorldError(
                f"{vessel.class_name} of {vessel.owner} cannot forage square "
                f"{square_index} of layer {layer}: {exc}",
            ) from exc
        try:
            square_xy(square_index, record.width)
        except WorldGridError as exc:
            raise ForageSquareError(
                f"{vessel.class_name} of {vessel.owner} stands on no square of "
                f"world {world_id}: {exc}",
            ) from exc

    def forage(
        self,
        seed: str,
        world_id: str,
        vessel: object,
        standing: object,
        locator: str,
    ) -> ForageRun:
        """Gather the material the square ``locator`` names into ``vessel``'s store.

        A ``standing`` on another square raises ``VesselNotOnSquareError``, and
        one ``VesselStore.put_in`` call takes every unit ``forage_units_per_run``
        names.
        """
        gatherer = _as_vessel(vessel)
        stood = _as_position(standing)
        held_layer, position = require_square_locator(locator)
        square = position.square_index
        if stood.square_index != square:
            raise VesselNotOnSquareError(
                f"{gatherer.class_name} of {gatherer.owner} stands on square "
                f"{stood.square_index} of layer {held_layer} and square {square} "
                f"was named; a Vessel forages the square it stands on",
            )
        self._require_forageable(seed, world_id, held_layer, square, gatherer)
        place = derive_place_material(seed, locator)
        units = forage_units_per_run()
        store = self._store_for(gatherer)
        change = self._gather_into(place, store, units, gatherer)
        run = ForageRun(
            place=place,
            vessel=gatherer,
            store_key=store.store_key,
            units_gathered=units,
            units_held=change.units_held,
            slots_used=change.slots_used,
            weight_carried=change.weight_carried,
            quintessence_embedded=place.quintessence_per_unit * units,
        )
        with self._lock:
            self._runs.append(run)
        logger.info(
            "%s of %s foraged %d %s at %s off square %d of layer %d into %s; it "
            "now holds %d, weight %s, embedding %s that no bucket records",
            gatherer.class_name,
            gatherer.owner,
            units,
            place.material_name,
            place.quality,
            square,
            held_layer,
            store.store_key,
            run.units_held,
            amount_text(run.weight_carried),
            amount_text(run.quintessence_embedded),
        )
        return run

    def _gather_into(
        self,
        place: ForagePlace,
        store: VesselStore,
        units: int,
        vessel: Vessel,
    ) -> StoreChange:
        """Put ``units`` of what ``place`` holds into ``store`` in one call."""
        try:
            return store.put_in(place.material_name, place.quality, units)
        except InventoryError as exc:
            raise ForageStoreError(
                f"{store.store_key} cannot take the {units} {place.material_name} "
                f"at {place.quality} that square {place.square_index} of layer "
                f"{place.layer} yielded to {vessel.class_name} of {vessel.owner}, "
                f"so the store holds what it held: {exc}",
            ) from exc

    def run_rows(self) -> list[dict]:
        """One row a run this register made, as ``ForageRun.to_dict`` serves it."""
        return [run.to_dict() for run in self.runs()]


def place_rows(seed: str, layer: object, square_indices: tuple[int, ...]) -> list[dict]:
    """One row a square in ``square_indices``, naming what that square holds."""
    return [
        derive_place_material_at(seed, layer, square).to_dict()
        for square in square_indices
    ]


def mechanism_rows() -> list[dict]:
    """One row an ``ABSENT_MECHANISMS`` entry and the note saying what it waits on."""
    return [
        {"mechanism": name, "note": ABSENT_MECHANISM_NOTES[name]}
        for name in ABSENT_MECHANISMS
    ]


def require_foraging() -> None:
    """Drive ``require_free_windows`` and log what a run derives and what it owes."""
    require_free_windows()
    entry = rate_named(FORAGE_YIELD_RATE_NAME)
    logger.info(
        "a foraging run draws a material from leaf window %d and a grade from "
        "window %d, %d hex digits each, off digits no other draw reads. %d "
        "materials and %d grades are reachable, and the %s yield of %s unit a run "
        "is the figure no source sets",
        MATERIAL_WINDOW,
        QUALITY_WINDOW,
        DRAW_DIGITS,
        len(MATERIALS),
        len(QUALITY_GRADES),
        entry.provenance,
        "no" if entry.rate is None else amount_text(entry.rate),
    )


require_foraging()
