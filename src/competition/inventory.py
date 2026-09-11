"""What one Vessel carries: gear in counted slots, consumables and resources in stacks.

``VesselStore`` holds one ``Vessel`` under a caller-supplied ``store_key``, and
``put_in`` and ``take_out`` are the only paths in and out. ``weight_carried`` adds
``unit_weight`` over every holding, and ``StoreBook.hand_over`` is the only move
between two stores. ``OWED_FIGURES`` names the four figures no module sets and
``ABSENT_MECHANISMS`` names what no module builds.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from decimal import Decimal

from .conversion_rates import rate_named
from .items import ABSENT_MECHANISM_NOTES as ITEM_MECHANISM_NOTES
from .items import ITEM_TYPE_NAMES, item_type_named
from .materials import (
    MATERIAL_NAMES,
    STACK_CEILING_ABSENT,
    material_named,
    occupies_slot,
    quality_index,
    stacks,
)
from .quintessence_ledger import amount_text
from .vessels import Vessel

logger = logging.getLogger("acervator.inventory")

#: A Vessel's gear slot count while no figure sets it.
SLOT_COUNT_ABSENT = None

#: The fewest gear slots a ``VesselStore`` may be given.
MIN_SLOT_COUNT = 0

#: The fewest units one stack may be allowed to reach.
MIN_STACK_CEILING = 1

#: The fewest units one ``put_in`` or ``take_out`` call moves.
MIN_MOVED_UNITS = 1

#: The slots one gear item takes. Only the gear class is counted in slots.
SLOTS_PER_GEAR_ITEM = 1

#: The ``conversion_rates`` row holding the weight one material unit carries.
WEIGHT_PER_UNIT_RATE_NAME = "TempWeight_0001"

#: The ``conversion_rates`` row holding the weight one Quintessence of strength lifts.
MAX_WEIGHT_RATE_NAME = "max_weight_per_strength_quintessence"

#: How two Vessels of one class at one level under one owner reach separate keys.
VESSEL_ID_ABSENT = (
    "vessels.Vessel.record_key carries an owner, a class_name and a vessel_id, "
    "so vessel_key separates two Vessels of one class at one level under one "
    "owner and follows one Vessel across a level gained. StoreBook.open_store "
    "still takes the key from its caller, so a caller that builds its own key "
    "can still name one store twice"
)

#: What no figure sets about a Vessel's gear slots.
SLOT_COUNT_OWED = ITEM_MECHANISM_NOTES["slot count"]

#: What no figure sets about how far a stack runs.
STACK_CEILING_OWED = (
    "materials.STACK_CEILING_ABSENT carries no figure and the operator's word is "
    "'large', so every VesselStore takes its stack_ceiling from its caller"
)

#: What the weight one material unit carries stands on today.
WEIGHT_PER_UNIT_OWED = (
    "Material.weight_per_unit reads conversion_rates.WEIGHT_PER_MATERIAL_UNIT, a "
    "working figure of one that the operator has not decided"
)

#: What the weight a Vessel may haul stands on today, and what would read it.
MAX_WEIGHT_OWED = (
    "entity_stats.STATS names max weight as strength's effect and the rate is a "
    "working figure of one; no module here reads it, and an encumbrance rule would"
)

#: The four figures a store and a hauling rule need. None is decided.
OWED_FIGURES: tuple[str, ...] = (
    "a Vessel's gear slot count",
    "the stack ceiling",
    "weight per material unit",
    "maximum weight per Quintessence of strength",
)

#: What each entry in ``OWED_FIGURES`` stands on, and what would set it.
OWED_FIGURE_NOTES: dict[str, str] = {
    "a Vessel's gear slot count": SLOT_COUNT_OWED,
    "the stack ceiling": STACK_CEILING_OWED,
    "weight per material unit": WEIGHT_PER_UNIT_OWED,
    "maximum weight per Quintessence of strength": MAX_WEIGHT_OWED,
}

#: The two ``OWED_FIGURES`` entries a ``VesselStore`` refuses to be built without.
REQUIRED_FIGURES: tuple[str, ...] = (
    "a Vessel's gear slot count",
    "the stack ceiling",
)

#: What a store takes part in that no module builds.
ABSENT_MECHANISMS: tuple[str, ...] = (
    "encumbrance",
    "a hauling trip",
    "a foraging run",
    "equipping",
    "trading between players",
    "a world supply of material units",
    "named instances",
    "a surface",
    "a package export",
)

#: What each entry in ``ABSENT_MECHANISMS`` waits on.
ABSENT_MECHANISM_NOTES: dict[str, str] = {
    "encumbrance": (
        "weight_carried is the weight and nothing turns it into a refusal or a "
        "turn point penalty; both figures in MAX_WEIGHT_OWED are working"
    ),
    "a hauling trip": (
        "the operator's rule is that encumbrance matters only while a Vessel moves "
        "items itself, and world_movement moves a participant and carries nothing"
    ),
    "a foraging run": "nothing gathers a material, so every put_in is a caller's",
    "equipping": (
        "items.equip_check reads one total against one cohesion and no slot here "
        "holds gear to a Vessel's Quintessence"
    ),
    "trading between players": (
        "StoreBook.hand_over moves between two stores and asks no price, and no "
        "module prices a holding"
    ),
    "a world supply of material units": (
        "no module counts how many units of a material a world holds, so a stack "
        "is bounded by stack_ceiling alone"
    ),
    "named instances": ITEM_MECHANISM_NOTES["named instances"],
    "a surface": (
        "the Gear subtab prints that nothing holds the items one Vessel carries "
        "and the Resources subtab prints that nothing holds how many units are "
        "carried; neither calls this module"
    ),
    "a package export": (
        "the competition package entry binds no name from this module, so "
        "report_unbound_modules names inventory at every start"
    ),
}

#: What the two PoA subtabs read that a ``VesselStore`` answers.
SUBTAB_READINGS: dict[str, str] = {
    "gear": (
        "held_gear names every gear item in a counted slot, and slots_used with "
        "slot_count is the count the subtab has no figure for"
    ),
    "resources": (
        "held_stacks names every material and the units held at one quality grade, "
        "which is the amount the subtab prints as held by nothing"
    ),
}


class InventoryError(RuntimeError):
    """Base for every refusal this module raises."""


class InventoryNameError(InventoryError):
    """Raised at import for a name in ``MATERIAL_NAMES`` and ``ITEM_TYPE_NAMES``."""


class StoreKeyError(InventoryError):
    """Raised for a blank ``store_key`` or a key ``StoreBook`` already holds."""


class StoreFigureError(InventoryError):
    """Raised for a ``slot_count`` or ``stack_ceiling`` absent or out of range."""


class StorageClassError(InventoryError):
    """Raised when a name reaches the half of a store its storage class does not use."""


class SlotsFullError(InventoryError):
    """Raised by ``put_in`` when gear would take more slots than ``slot_count``."""


class StackCeilingError(InventoryError):
    """Raised by ``put_in`` when a stack would pass ``stack_ceiling``."""


class HoldingUnitsError(InventoryError):
    """Raised for units under ``MIN_MOVED_UNITS`` or a take-out above what is held."""


class UnknownStoreError(InventoryError):
    """Raised by ``StoreBook.store`` for a key the book does not hold."""


_SHARED_NAMES: tuple[str, ...] = tuple(
    sorted(set(MATERIAL_NAMES) & set(ITEM_TYPE_NAMES)),
)
if _SHARED_NAMES:
    raise InventoryNameError(
        f"{_SHARED_NAMES} sits in both MATERIAL_NAMES and ITEM_TYPE_NAMES, and a "
        f"holding name resolves to one table or the other",
    )


def _as_vessel(value: object) -> Vessel:
    """Return ``value`` as a ``Vessel``; every other type raises."""
    if not isinstance(value, Vessel):
        raise InventoryError(f"a Vessel was expected, got {type(value).__name__}")
    return value


def _as_store_key(value: object) -> str:
    """Return ``value`` as a non-empty ``store_key``; every other value raises."""
    if type(value) is not str or not value.strip():
        raise StoreKeyError(
            f"a store_key must be a non-empty string, got {value!r}; "
            f"{VESSEL_ID_ABSENT}",
        )
    return value


def _as_slot_count(value: object) -> int:
    """Return ``value`` as a gear slot count at or above ``MIN_SLOT_COUNT``."""
    if value is SLOT_COUNT_ABSENT:
        raise StoreFigureError(f"slot_count is absent; {SLOT_COUNT_OWED}")
    if type(value) is not int or value < MIN_SLOT_COUNT:
        raise StoreFigureError(
            f"slot_count must be a whole number at or above {MIN_SLOT_COUNT}, "
            f"got {value!r}",
        )
    return value


def _as_stack_ceiling(value: object) -> int:
    """Return ``value`` as a stack ceiling at or above ``MIN_STACK_CEILING``."""
    if value is STACK_CEILING_ABSENT:
        raise StoreFigureError(f"stack_ceiling is absent; {STACK_CEILING_OWED}")
    if type(value) is not int or value < MIN_STACK_CEILING:
        raise StoreFigureError(
            f"stack_ceiling must be a whole number at or above "
            f"{MIN_STACK_CEILING}, got {value!r}",
        )
    return value


def _as_moved_units(value: object, name: str) -> int:
    """Return ``value`` as whole units at or above ``MIN_MOVED_UNITS``."""
    if type(value) is not int or value < MIN_MOVED_UNITS:
        raise HoldingUnitsError(
            f"{name} must be a whole number of units at or above "
            f"{MIN_MOVED_UNITS}, got {value!r}",
        )
    return value


def _as_holding(name: str, quality: str) -> str:
    """Return the storage class of ``name``, refusing a bad grade or name first."""
    quality_index(quality)
    return storage_class_of(name)


def holding_names() -> tuple[str, ...]:
    """Every name a store holds: ``MATERIAL_NAMES`` then ``ITEM_TYPE_NAMES``."""
    return MATERIAL_NAMES + ITEM_TYPE_NAMES


def storage_class_of(name: str) -> str:
    """The storage class ``name`` stores under, read off its own table."""
    if name in MATERIAL_NAMES:
        return material_named(name).storage_class
    return item_type_named(name).storage_class


def unit_weight(name: str) -> Decimal:
    """The weight one unit of ``name`` carries, added over every material it lists."""
    if name in MATERIAL_NAMES:
        return material_named(name).weight_per_unit
    carried = Decimal(0)
    for part in item_type_named(name).components:
        carried += material_named(part.material).weight_per_unit * part.units
    return carried


def vessel_key(vessel: Vessel) -> str:
    """``Vessel.record_key`` joined, the ``store_key`` shape ``craft_id_for`` copies.

    The string renders the one key ``alignment.vessel_key`` returns, so a store
    and an alignment cannot disagree about which Vessel a record belongs to.
    """
    held = _as_vessel(vessel)
    return ":".join(held.record_key)


@dataclass(frozen=True)
class SlotItem:
    """One gear item standing in one counted slot, at the grade it was made at."""

    name: str
    quality: str

    def __post_init__(self) -> None:
        """Refuse a grade outside ``QUALITY_GRADES`` and a name that takes no slot."""
        quality_index(self.quality)
        held = storage_class_of(self.name)
        if not occupies_slot(held):
            raise StorageClassError(
                f"{self.name} stores as {held} and takes no slot; a SlotItem holds "
                f"gear alone",
            )

    @property
    def weight(self) -> Decimal:
        """The weight this one gear item carries, from ``unit_weight``."""
        return unit_weight(self.name)

    def to_dict(self) -> dict:
        """This slot as a JSON-safe dict, the weight a plain string."""
        return {
            "name": self.name,
            "quality": self.quality,
            "storage_class": storage_class_of(self.name),
            "weight": amount_text(self.weight),
        }


@dataclass(frozen=True)
class Stack:
    """One stacking name and the whole units held of it at one quality grade.

    A stacking class takes no slot, so ``units`` is bounded by ``stack_ceiling`` alone.
    """

    name: str
    quality: str
    units: int

    def __post_init__(self) -> None:
        """Refuse a grade outside ``QUALITY_GRADES``, a slot-taking name, bad units."""
        quality_index(self.quality)
        held = storage_class_of(self.name)
        if not stacks(held):
            raise StorageClassError(
                f"{self.name} stores as {held} and takes a counted slot; a Stack "
                f"holds a consumable or a resource",
            )
        _as_moved_units(self.units, f"{self.name} units")

    @property
    def weight(self) -> Decimal:
        """The weight these units carry, ``unit_weight`` times ``units``."""
        return unit_weight(self.name) * self.units

    def to_dict(self) -> dict:
        """This stack as a JSON-safe dict, every weight a plain string."""
        return {
            "name": self.name,
            "quality": self.quality,
            "storage_class": storage_class_of(self.name),
            "units": self.units,
            "unit_weight": amount_text(unit_weight(self.name)),
            "weight": amount_text(self.weight),
        }


@dataclass(frozen=True)
class StoreChange:
    """What one ``put_in`` or ``take_out`` moved, read off the store after it moved.

    ``units_held`` is what the store holds of that name and grade once the call returns.
    """

    store_key: str
    name: str
    quality: str
    units: int
    is_put_in: bool
    units_held: int
    slots_used: int
    weight_carried: Decimal

    def to_dict(self) -> dict:
        """This change as a JSON-safe dict, the weight a plain string."""
        return {
            "store_key": self.store_key,
            "name": self.name,
            "quality": self.quality,
            "units": self.units,
            "is_put_in": self.is_put_in,
            "units_held": self.units_held,
            "slots_used": self.slots_used,
            "weight_carried": amount_text(self.weight_carried),
        }


class VesselStore:
    """What one Vessel carries, in two halves that never take each other's space.

    Gear fills ``slot_count`` counted slots and a stacking name runs to
    ``stack_ceiling`` units, both figures arriving by construction.
    """

    def __init__(
        self,
        vessel: object,
        store_key: object,
        slot_count: object,
        stack_ceiling: object,
    ) -> None:
        """Hold one Vessel under ``store_key`` with both figures its rules need."""
        self._vessel = _as_vessel(vessel)
        self._store_key = _as_store_key(store_key)
        self._slot_count = _as_slot_count(slot_count)
        self._stack_ceiling = _as_stack_ceiling(stack_ceiling)
        self._slots: list[SlotItem] = []
        self._stacks: dict[tuple[str, str], int] = {}
        self._lock = threading.RLock()

    @property
    def vessel(self) -> Vessel:
        """The Vessel this store is held against."""
        return self._vessel

    @property
    def store_key(self) -> str:
        """The key ``StoreBook`` holds this store under."""
        return self._store_key

    @property
    def slot_count(self) -> int:
        """The counted gear slots this Vessel has, from its caller."""
        return self._slot_count

    @property
    def stack_ceiling(self) -> int:
        """The units one stacking name may reach, from its caller."""
        return self._stack_ceiling

    @property
    def slots_used(self) -> int:
        """The slots the gear held takes, ``SLOTS_PER_GEAR_ITEM`` each."""
        with self._lock:
            return len(self._slots) * SLOTS_PER_GEAR_ITEM

    @property
    def slots_free(self) -> int:
        """``slot_count`` less ``slots_used``."""
        return self._slot_count - self.slots_used

    def held_gear(self) -> tuple[SlotItem, ...]:
        """Every gear item in a counted slot, in the order ``put_in`` took them."""
        with self._lock:
            return tuple(self._slots)

    def held_stacks(self) -> tuple[Stack, ...]:
        """One ``Stack`` a name and grade held, sorted by name then grade."""
        with self._lock:
            return tuple(
                Stack(name, quality, self._stacks[(name, quality)])
                for name, quality in sorted(self._stacks)
            )

    def units_held(self, name: str, quality: str) -> int:
        """The units held of ``name`` at ``quality``, counting slots or a stack."""
        quality_index(quality)
        held = storage_class_of(name)
        with self._lock:
            if occupies_slot(held):
                return sum(
                    SLOTS_PER_GEAR_ITEM
                    for slot in self._slots
                    if slot.name == name and slot.quality == quality
                )
            return self._stacks.get((name, quality), 0)

    @property
    def weight_carried(self) -> Decimal:
        """Every held weight added, the gear slots and the stacks and nothing else."""
        carried = Decimal(0)
        with self._lock:
            for slot in self._slots:
                carried += slot.weight
            for stack in self.held_stacks():
                carried += stack.weight
        return carried

    def put_in(
        self,
        name: str,
        quality: str,
        units: object = MIN_MOVED_UNITS,
    ) -> StoreChange:
        """Put ``units`` of ``name`` at ``quality`` in, refusing a slot or ceiling.

        ``_as_holding`` refuses an unknown name or grade before anything is written.
        """
        moved = _as_moved_units(units, "units")
        held = _as_holding(name, quality)
        with self._lock:
            if occupies_slot(held):
                self._fill_slots(name, quality, moved)
            else:
                self._raise_stack(name, quality, moved)
            return self._change(name, quality, moved, is_put_in=True)

    def take_out(
        self,
        name: str,
        quality: str,
        units: object = MIN_MOVED_UNITS,
    ) -> StoreChange:
        """Take ``units`` of ``name`` at ``quality`` out, refusing more than is held.

        ``_as_holding`` refuses an unknown name or grade before anything is dropped.
        """
        moved = _as_moved_units(units, "units")
        held = _as_holding(name, quality)
        with self._lock:
            if occupies_slot(held):
                self._empty_slots(name, quality, moved)
            else:
                self._lower_stack(name, quality, moved)
            return self._change(name, quality, moved, is_put_in=False)

    def _fill_slots(self, name: str, quality: str, units: int) -> None:
        """Add ``units`` gear items, refusing a total above ``slot_count``."""
        taking = units * SLOTS_PER_GEAR_ITEM
        if taking > self.slots_free:
            raise SlotsFullError(
                f"{self._store_key} holds {self.slots_used} of {self._slot_count} "
                f"gear slots and {units} {name} takes {taking} more; no gear is held "
                f"in a slot this Vessel does not have",
            )
        self._slots.extend(SlotItem(name, quality) for _ in range(units))

    def _empty_slots(self, name: str, quality: str, units: int) -> None:
        """Drop ``units`` gear of ``name`` at ``quality``, refusing more than held."""
        standing = self.units_held(name, quality)
        if units > standing:
            raise HoldingUnitsError(
                f"{self._store_key} holds {standing} {name} at {quality} and "
                f"{units} was asked for; a store gives out nothing it does not hold",
            )
        left = units
        kept: list[SlotItem] = []
        for slot in self._slots:
            if left and slot.name == name and slot.quality == quality:
                left -= SLOTS_PER_GEAR_ITEM
                continue
            kept.append(slot)
        self._slots = kept

    def _raise_stack(self, name: str, quality: str, units: int) -> None:
        """Add ``units`` to one stack, refusing a total above ``stack_ceiling``."""
        standing = self._stacks.get((name, quality), 0)
        reached = standing + units
        if reached > self._stack_ceiling:
            raise StackCeilingError(
                f"{self._store_key} holds {standing} {name} at {quality} and "
                f"{units} more reaches {reached}, above the {self._stack_ceiling} "
                f"stack ceiling it was built with",
            )
        self._stacks[(name, quality)] = reached

    def _lower_stack(self, name: str, quality: str, units: int) -> None:
        """Take ``units`` off one stack, refusing more than the stack holds."""
        quality_index(quality)
        standing = self._stacks.get((name, quality), 0)
        if units > standing:
            raise HoldingUnitsError(
                f"{self._store_key} holds {standing} {name} at {quality} and "
                f"{units} was asked for; a stack never falls under nothing",
            )
        left = standing - units
        if left:
            self._stacks[(name, quality)] = left
        else:
            self._stacks.pop((name, quality), None)

    def _change(
        self,
        name: str,
        quality: str,
        units: int,
        *,
        is_put_in: bool,
    ) -> StoreChange:
        """Read the store after a move and log what it now holds."""
        change = StoreChange(
            self._store_key,
            name,
            quality,
            units,
            is_put_in,
            self.units_held(name, quality),
            self.slots_used,
            self.weight_carried,
        )
        logger.info(
            "%s %s %d %s at %s; it now holds %d, %d of %d gear slots, weight %s",
            self._store_key,
            "took in" if is_put_in else "gave out",
            units,
            name,
            quality,
            change.units_held,
            change.slots_used,
            self._slot_count,
            amount_text(change.weight_carried),
        )
        return change

    def to_dict(self) -> dict:
        """This store as a JSON-safe dict, every weight a plain string."""
        with self._lock:
            return {
                "store_key": self._store_key,
                "vessel": self._vessel.to_dict(),
                "slot_count": self._slot_count,
                "slots_used": self.slots_used,
                "slots_free": self.slots_free,
                "stack_ceiling": self._stack_ceiling,
                "gear": [slot.to_dict() for slot in self._slots],
                "stacks": [stack.to_dict() for stack in self.held_stacks()],
                "weight_carried": amount_text(self.weight_carried),
            }


class StoreBook:
    """Every ``VesselStore`` under its own key, and the one move between two of them.

    ``hand_over`` takes out of one store before it puts into another, and puts the
    units back when the second store refuses them.
    """

    def __init__(self) -> None:
        """Hold no store, and the lock every open and hand-over takes."""
        self._stores: dict[str, VesselStore] = {}
        self._lock = threading.RLock()

    def open_store(
        self,
        vessel: object,
        store_key: object,
        slot_count: object,
        stack_ceiling: object,
    ) -> VesselStore:
        """Open one store for ``vessel``, refusing a ``store_key`` this book holds."""
        store = VesselStore(vessel, store_key, slot_count, stack_ceiling)
        with self._lock:
            if store.store_key in self._stores:
                raise StoreKeyError(
                    f"{store.store_key} already names a store; {VESSEL_ID_ABSENT}",
                )
            self._stores[store.store_key] = store
        logger.info(
            "store %s opened for %s %s at level %d with %d gear slots and a "
            "%d unit stack ceiling",
            store.store_key,
            store.vessel.owner,
            store.vessel.class_name,
            store.vessel.level,
            store.slot_count,
            store.stack_ceiling,
        )
        return store

    def store(self, store_key: str) -> VesselStore:
        """The store ``store_key`` names, refusing a key this book does not hold."""
        wanted = _as_store_key(store_key)
        with self._lock:
            held = self._stores.get(wanted)
        if held is None:
            raise UnknownStoreError(
                f"{wanted!r} names no store; the book holds "
                f"{', '.join(self.store_keys()) or 'nothing'}",
            )
        return held

    def store_keys(self) -> list[str]:
        """Every key this book holds a store under, sorted."""
        with self._lock:
            return sorted(self._stores)

    def stores_of(self, owner: str) -> list[VesselStore]:
        """Every store whose Vessel ``owner`` matches, in ``store_keys`` order."""
        with self._lock:
            return [
                self._stores[key]
                for key in sorted(self._stores)
                if self._stores[key].vessel.owner == owner
            ]

    def hand_over(
        self,
        from_key: str,
        to_key: str,
        name: str,
        quality: str,
        units: object = MIN_MOVED_UNITS,
    ) -> tuple[StoreChange, StoreChange]:
        """Move ``units`` of ``name`` from one store to another in one call.

        The take-out runs first, and a refused put-in returns the units to the source.
        """
        giver = self.store(from_key)
        taker = self.store(to_key)
        if giver.store_key == taker.store_key:
            raise StoreKeyError(
                f"{giver.store_key} cannot hand to itself; a hand-over needs two "
                f"stores",
            )
        moved = _as_moved_units(units, "units")
        with self._lock:
            given = giver.take_out(name, quality, moved)
            try:
                taken = taker.put_in(name, quality, moved)
            except InventoryError:
                giver.put_in(name, quality, moved)
                raise
        logger.info(
            "%d %s at %s moved from %s to %s; the giver holds %d and the taker %d",
            moved,
            name,
            quality,
            giver.store_key,
            taker.store_key,
            given.units_held,
            taken.units_held,
        )
        return given, taken

    def to_dict(self) -> dict:
        """This book as a JSON-safe dict, one entry a store."""
        return {
            "store_keys": self.store_keys(),
            "stores": [self.store(key).to_dict() for key in self.store_keys()],
        }


def store_rows(store: VesselStore) -> list[dict]:
    """One row a holding in ``store``, the gear slots first then the stacks."""
    rows = [slot.to_dict() for slot in store.held_gear()]
    rows.extend(stack.to_dict() for stack in store.held_stacks())
    return rows


def unit_weight_rows() -> list[dict]:
    """One row a ``holding_names`` entry: its class, whether it stacks, its weight."""
    return [
        {
            "name": name,
            "storage_class": storage_class_of(name),
            "occupies_slot": occupies_slot(storage_class_of(name)),
            "stacks": stacks(storage_class_of(name)),
            "unit_weight": amount_text(unit_weight(name)),
        }
        for name in holding_names()
    ]


def figure_rows() -> list[dict]:
    """One row an ``OWED_FIGURES`` entry: its figure, and what would set it."""
    figures: dict[str, str | None] = {
        "a Vessel's gear slot count": SLOT_COUNT_ABSENT,
        "the stack ceiling": STACK_CEILING_ABSENT,
    }
    provenances: dict[str, str] = {}
    for figure, rate_name in (
        ("weight per material unit", WEIGHT_PER_UNIT_RATE_NAME),
        ("maximum weight per Quintessence of strength", MAX_WEIGHT_RATE_NAME),
    ):
        entry = rate_named(rate_name)
        figures[figure] = None if entry.rate is None else amount_text(entry.rate)
        provenances[figure] = entry.provenance
    return [
        {
            "figure": figure,
            "amount": figures[figure],
            "provenance": provenances.get(figure),
            "is_required_to_open_a_store": figure in REQUIRED_FIGURES,
            "note": OWED_FIGURE_NOTES[figure],
        }
        for figure in OWED_FIGURES
    ]
