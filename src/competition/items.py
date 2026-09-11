"""Every PoA item type, the materials it is made of, and what holds it together.

``ITEM_TYPES`` carries one entry a name the gear subtab prints, and
``item_type_named``, ``item_types_in_storage_class``, ``item_rows`` and
``cohesion_rows`` read it. One ``Component`` names a material, its units and its
quality, and ``ItemType.cohesion`` adds every component's block through
``entity_stats.quintessence_requirement``. ``equip_check`` asks whether one total
covers that cohesion, and ``grid_faults`` drives every type at every grade once at
import.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from .conversion_rates import rate_named
from .entity_stats import (
    STAT_NAMES,
    Potential,
    StatBlock,
    potential_at,
    quintessence_requirement,
    stat_block,
)
from .materials import (
    BAND_METAL,
    CONSUMABLE,
    GEAR,
    ORE_SUFFIX,
    QUALITY_GRADES,
    embedded_quintessence,
    material_named,
    occupies_slot,
    quality_index,
    stacks,
)
from .quintessence_ledger import (
    QUINTESSENCE_MINIMUM_UNIT,
    QUINTESSENCE_SUPPLY_CAP,
    amount_text,
    is_on_quintessence_grid,
)

logger = logging.getLogger("acervator.items")

#: The ``conversion_rates`` row turning one component's stats into cohesion.
COHESION_RATE_NAME = "item_cohesion_per_component_quintessence"

# quintessence_requirement adds every amount of every block, so which stat holds
# a component's amount never changes an item's cohesion.
#: The stat a ``Component`` block puts its whole amount in.
COHESION_STAT = STAT_NAMES[0]

#: The grade every entry in ``ITEM_TYPES`` declares, the lowest grade there is.
DECLARED_QUALITY = QUALITY_GRADES[0]

#: The material every declared ``Component`` names, ``BAND_METAL`` and ``ORE_SUFFIX``.
DECLARED_MATERIAL = BAND_METAL + ORE_SUFFIX

#: The units one declared ``Component`` holds while no recipe sets a count.
UNITS_PER_DECLARED_COMPONENT = 1

#: The fewest units one ``Component`` may hold.
MIN_COMPONENT_UNITS = 1

#: The fewest components one ``ItemType`` may list.
MIN_COMPONENTS = 1

#: Why no entry in ``ITEM_TYPES`` takes the third storage class.
RESOURCE_ITEM_TYPE_ABSENT = (
    "every entry in materials.MATERIALS already declares the RESOURCE storage "
    "class, so a resource is a material and no item type restates one"
)

#: What no entry in ``ITEM_TYPES`` carries, by the operator's own sourcing rule.
NAMED_INSTANCES_ABSENT = (
    "no artefact is named here; every entry in ITEM_TYPES is a type, and a named "
    "instance waits on crafting naming what it made"
)

#: What an ``EquipCheck`` whose total covers the cohesion reads.
EQUIP_ALLOWED = "the total Quintessence covers the item's cohesion"

#: What an ``EquipCheck`` whose total falls short reads.
EQUIP_REFUSED = "the item's cohesion is above the total Quintessence held"

#: What an item takes part in, each note naming what builds it and what stays absent.
ABSENT_MECHANISMS: tuple[str, ...] = (
    "a crafting recipe",
    "salvage",
    "equipping",
    "inventory",
    "slot count",
    "encumbrance",
    "loot generation",
    "named instances",
)

#: What each entry in ``ABSENT_MECHANISMS`` stands on, and what it still waits on.
ABSENT_MECHANISM_NOTES: dict[str, str] = {
    "a crafting recipe": (
        "crafting.Recipe is declared and crafting.recipe_for builds one out of an "
        "item type's own component list; no table names a Recipe, because "
        "loss_share and turns_required are two figures no source sets and Recipe "
        "refuses an absent one"
    ),
    "salvage": "nothing destroys an item for the Quintessence it embeds",
    "equipping": (
        "inventory.VesselStore.put_in holds a gear item in one of a Vessel's "
        "counted slots, and nothing reads that item's cohesion against the "
        "Vessel's Quintessence, so equip_check still has no caller"
    ),
    "inventory": (
        "inventory.VesselStore holds them, gear in counted slots and consumables "
        "and resources in stacks, StoreBook.hand_over is still the only move "
        "between two stores, and a craft and a foraging run are the other two ways "
        "a store changes: crafting.CraftRegister.complete_craft puts a made item in "
        "the crafting Vessel's store, begin_craft takes that recipe's component "
        "units out of it, and foraging.ForageRegister.forage puts in the units the "
        "square a Vessel stands on yields; no panel calls any of them"
    ),
    "slot count": "no figure sets how many gear slots a Vessel has",
    "encumbrance": (
        "inventory.VesselStore.weight_carried weighs it, adding unit_weight over "
        "every holding, and nothing turns that weight into a refusal or a turn "
        "point penalty"
    ),
    "loot generation": (
        "loot_drop.drop_from_pool draws a tier and a LootDrop names an item_type, "
        "a quality and a storage_class; no source names the item type a tier "
        "yields, so drop_for_market takes a yields mapping from its caller"
    ),
    "named instances": NAMED_INSTANCES_ABSENT,
}


class ItemError(RuntimeError):
    """Base for every refusal this module raises."""


class UnknownItemTypeError(ItemError):
    """Raised by ``item_type_named`` for a name ``ITEM_TYPE_NAMES`` does not carry."""


class ItemComponentError(ItemError):
    """Raised for an empty material list, bad units, or one material listed twice."""


class ItemValueError(ItemError):
    """Raised for a cohesion under ``QUINTESSENCE_MINIMUM_UNIT`` or off its grid."""


class ItemGridError(ItemError):
    """Raised at import when ``grid_faults`` finds a cohesion no bucket can hold."""


def _cohesion_rate() -> Decimal:
    """Return the figure ``rate_named`` holds for ``COHESION_RATE_NAME``."""
    entry = rate_named(COHESION_RATE_NAME)
    if entry.rate is None:
        raise ItemValueError(
            f"{COHESION_RATE_NAME} carries no figure, and no item states what holds "
            f"it together until the conversion table sets one",
        )
    return entry.rate


#: The Quintessence one Quintessence of a component's stats holds together.
COHESION_PER_COMPONENT_QUINTESSENCE: Decimal = _cohesion_rate()


def _as_cohesion(value: Decimal, name: str) -> Decimal:
    """Return ``value`` as a cohesion on the minimum-unit grid, at or above one unit."""
    if value < QUINTESSENCE_MINIMUM_UNIT:
        raise ItemValueError(
            f"{name} is held together by {amount_text(value)}, under the "
            f"{amount_text(QUINTESSENCE_MINIMUM_UNIT)} minimum unit, and no item "
            f"embeds less Quintessence than the currency expresses",
        )
    if value > QUINTESSENCE_SUPPLY_CAP:
        raise ItemValueError(
            f"{name} is held together by {amount_text(value)}, above the "
            f"{amount_text(QUINTESSENCE_SUPPLY_CAP)} Quintessence that can exist, "
            f"so no holder could ever cover it",
        )
    if not is_on_quintessence_grid(value):
        raise ItemValueError(
            f"{name} is held together by {amount_text(value)}, which is not a whole "
            f"number of {amount_text(QUINTESSENCE_MINIMUM_UNIT)}, and no bucket "
            f"holds it",
        )
    return value


@dataclass(frozen=True)
class Component:
    """One entry in an item's material list: a material, its units and its quality.

    ``embedded`` reads ``materials.embedded_quintessence`` for one unit and
    multiplies it by ``units``.
    """

    material: str
    units: int
    quality: str

    def __post_init__(self) -> None:
        """Refuse a material or grade the tables do not carry, and units under one."""
        material_named(self.material)
        quality_index(self.quality)
        if type(self.units) is not int or self.units < MIN_COMPONENT_UNITS:
            raise ItemComponentError(
                f"{self.material} needs at least {MIN_COMPONENT_UNITS} whole unit in "
                f"a material list, got {self.units!r}",
            )

    def embedded_at(self, quality: str) -> Decimal:
        """The Quintessence ``units`` of this material embed at ``quality``."""
        one_unit = embedded_quintessence(material_named(self.material), quality)
        return one_unit * self.units

    @property
    def embedded(self) -> Decimal:
        """``embedded_at`` read at this component's own ``quality``."""
        return self.embedded_at(self.quality)

    def block_at(self, quality: str) -> StatBlock:
        """This component at ``quality`` as one block, amount in ``COHESION_STAT``."""
        held = self.embedded_at(quality) * COHESION_PER_COMPONENT_QUINTESSENCE
        return stat_block(
            {name: (held if name == COHESION_STAT else 0) for name in STAT_NAMES},
        )

    def to_dict(self) -> dict:
        """This component as a JSON-safe dict, every amount a plain string."""
        return {
            "material": self.material,
            "units": self.units,
            "quality": self.quality,
            "embedded": amount_text(self.embedded),
        }


@dataclass(frozen=True)
class ItemType:
    """One kind of item: its name, its storage class and the materials it is made of.

    ``cohesion`` is the Quintessence holding it together, and ``to_dict`` serves
    every component so a salvage can read the list back.
    """

    name: str
    storage_class: str
    components: tuple[Component, ...]
    note: str

    def __post_init__(self) -> None:
        """Refuse a blank name, a bad class, an empty list, and a repeated material."""
        if not self.name.strip():
            raise UnknownItemTypeError(f"an item type needs a name, got {self.name!r}")
        if not self.note.strip():
            raise ItemError(f"{self.name} needs a note on where its shape came from")
        occupies_slot(self.storage_class)
        listed = tuple(self.components)
        object.__setattr__(self, "components", listed)
        if len(listed) < MIN_COMPONENTS:
            raise ItemComponentError(
                f"{self.name} lists no material, so nothing holds it together and "
                f"its cohesion would be under the "
                f"{amount_text(QUINTESSENCE_MINIMUM_UNIT)} minimum unit",
            )
        named = tuple(part.material for part in listed)
        if len(set(named)) != len(named):
            raise ItemComponentError(
                f"{self.name} lists {named} and names one material twice; raise that "
                f"component's units instead",
            )
        _as_cohesion(self.cohesion, self.name)

    @property
    def takes_a_slot(self) -> bool:
        """True while ``occupies_slot`` answers True for this ``storage_class``."""
        return occupies_slot(self.storage_class)

    def blocks_at(self, quality: str | None = None) -> tuple[StatBlock, ...]:
        """One block a component, ``quality`` overriding every component's own grade."""
        return tuple(
            part.block_at(part.quality if quality is None else quality)
            for part in self.components
        )

    @property
    def cohesion(self) -> Decimal:
        """The Quintessence holding this item together, at each component's grade."""
        return quintessence_requirement(self.blocks_at())

    def cohesion_at(self, quality: str) -> Decimal:
        """``cohesion`` with every component read at ``quality``."""
        return quintessence_requirement(self.blocks_at(quality))

    def to_dict(self) -> dict:
        """This item type as a JSON-safe dict, one entry a component."""
        return {
            "name": self.name,
            "storage_class": self.storage_class,
            "occupies_slot": self.takes_a_slot,
            "stacks": stacks(self.storage_class),
            "components": [part.to_dict() for part in self.components],
            "cohesion": amount_text(self.cohesion),
            "named_instances": NAMED_INSTANCES_ABSENT,
            "note": self.note,
        }


@dataclass(frozen=True)
class EquipCheck:
    """What one total Quintessence reaches against one item type's cohesion.

    ``is_allowed`` is the ``Potential.is_full`` of the blocks ``cohesion`` adds, so
    the two readings cannot disagree.
    """

    item_name: str
    cohesion: Decimal
    total: Decimal
    is_allowed: bool
    reason: str
    potential: Potential

    def to_dict(self) -> dict:
        """This check as a JSON-safe dict, every amount a plain string."""
        return {
            "item_name": self.item_name,
            "cohesion": amount_text(self.cohesion),
            "total": amount_text(self.total),
            "is_allowed": self.is_allowed,
            "reason": self.reason,
            "potential": self.potential.to_dict(),
        }


def _declared_components() -> tuple[Component, ...]:
    """One component of ``DECLARED_MATERIAL`` at ``DECLARED_QUALITY``, in one unit."""
    return (
        Component(DECLARED_MATERIAL, UNITS_PER_DECLARED_COMPONENT, DECLARED_QUALITY),
    )


def _type_note(name: str) -> str:
    """Return the note for ``name``, saying where its name and its list came from."""
    return (
        f"{name} is one of the four item classes the gear subtab prints as built by "
        f"nothing; its list holds {UNITS_PER_DECLARED_COMPONENT} unit of "
        f"{DECLARED_MATERIAL} at {DECLARED_QUALITY}, the one material whose band the "
        f"operator decided, until a crafting recipe names this type's own list"
    )


#: The item table. A name, a storage class or a list changes here and nowhere else.
ITEM_TYPES: tuple[ItemType, ...] = (
    ItemType("armour", GEAR, _declared_components(), _type_note("armour")),
    ItemType("weapons", GEAR, _declared_components(), _type_note("weapons")),
    ItemType(
        "accessories",
        GEAR,
        _declared_components(),
        _type_note("accessories"),
    ),
    ItemType(
        "consumables",
        CONSUMABLE,
        _declared_components(),
        _type_note("consumables"),
    ),
)

#: Every name in ``ITEM_TYPES``, in the order it declares them.
ITEM_TYPE_NAMES: tuple[str, ...] = tuple(entry.name for entry in ITEM_TYPES)

if len(set(ITEM_TYPE_NAMES)) != len(ITEM_TYPE_NAMES):
    raise UnknownItemTypeError(
        f"ITEM_TYPES declares a name twice: {ITEM_TYPE_NAMES}",
    )


def item_type_named(name: str) -> ItemType:
    """Return the entry in ``ITEM_TYPES`` whose ``name`` matches, refusing the rest."""
    for entry in ITEM_TYPES:
        if entry.name == name:
            return entry
    raise UnknownItemTypeError(
        f"{name!r} is not a PoA item type; "
        f"the table carries {', '.join(ITEM_TYPE_NAMES)}",
    )


def item_types_in_storage_class(storage_class: str) -> tuple[ItemType, ...]:
    """Every entry in ``ITEM_TYPES`` whose ``storage_class`` matches.

    ``occupies_slot`` refuses a class outside ``materials.STORAGE_CLASSES``.
    """
    occupies_slot(storage_class)
    return tuple(entry for entry in ITEM_TYPES if entry.storage_class == storage_class)


def equip_check(item: ItemType, total_quintessence: object) -> EquipCheck:
    """Ask whether ``total_quintessence`` covers the cohesion of ``item``.

    ``potential_at`` reads the blocks ``ItemType.cohesion`` adds, and
    ``ABSENT_MECHANISMS`` names the equipping this waits on.
    """
    reading = potential_at(total_quintessence, item.blocks_at())
    reason = EQUIP_ALLOWED if reading.is_full else EQUIP_REFUSED
    logger.info(
        "%s is held together by %s against a total of %s, so it reads %s",
        item.name,
        amount_text(reading.requirement),
        amount_text(reading.balance),
        reason,
    )
    return EquipCheck(
        item.name,
        reading.requirement,
        reading.balance,
        reading.is_full,
        reason,
        reading,
    )


def item_rows() -> list[dict]:
    """One row an entry in ``ITEM_TYPES``, as ``to_dict`` serves it."""
    return [entry.to_dict() for entry in ITEM_TYPES]


def cohesion_rows() -> list[dict]:
    """One row a type at a grade: its name, the grade, and what holds it together."""
    return [
        {
            "item_type": entry.name,
            "quality": quality,
            "cohesion": amount_text(entry.cohesion_at(quality)),
        }
        for entry in ITEM_TYPES
        for quality in QUALITY_GRADES
    ]


def grid_faults() -> tuple[tuple[str, str, str, str], ...]:
    """Every item type and grade whose cohesion breaks one of the three rules.

    One row is the type, the grade, the amount and the rule it broke.
    """
    out: list[tuple[str, str, str, str]] = []
    unit = amount_text(QUINTESSENCE_MINIMUM_UNIT)
    cap = amount_text(QUINTESSENCE_SUPPLY_CAP)
    for entry in ITEM_TYPES:
        for quality in QUALITY_GRADES:
            amount = entry.cohesion_at(quality)
            if amount < QUINTESSENCE_MINIMUM_UNIT:
                out.append((entry.name, quality, amount_text(amount), f"under {unit}"))
            if not is_on_quintessence_grid(amount):
                out.append(
                    (
                        entry.name,
                        quality,
                        amount_text(amount),
                        f"not a whole number of {unit}",
                    ),
                )
            if amount > QUINTESSENCE_SUPPLY_CAP:
                out.append(
                    (entry.name, quality, amount_text(amount), f"above the {cap}"),
                )
    logger.info(
        "drove %s item types across %s quality grades, %s cohesions broke a rule",
        len(ITEM_TYPES),
        len(QUALITY_GRADES),
        len(out),
    )
    return tuple(out)


_FAULTS = grid_faults()
if _FAULTS:
    raise ItemGridError(
        f"an item's cohesion is Quintessence no bucket holds: {_FAULTS}",
    )
