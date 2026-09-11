"""Every PoA material, the Quintessence one unit embeds, and how it stores.

``MATERIALS`` carries one ore a metal ``rpg_classes.CLASSES`` declares, and
``material_named``, ``materials_in_storage_class``, ``material_rows`` and
``embedded_rows`` read it. ``embedded_quintessence`` reads one unit at one of the
``QUALITY_GRADES``, and ``grid_faults`` drives every material at every grade once
at import.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from .conversion_rates import (
    DECIDED,
    IRON_ORE_QUINTESSENCE_HIGH_QUALITY,
    IRON_ORE_QUINTESSENCE_LOW_QUALITY,
    PROVENANCES,
    WEIGHT_PER_MATERIAL_UNIT,
    WORKING,
)
from .loot_drop import TIER_NAMES
from .quintessence_ledger import (
    QUINTESSENCE_MINIMUM_UNIT,
    QUINTESSENCE_SUPPLY_CAP,
    amount_text,
    is_on_quintessence_grid,
)
from .rpg_classes import CLASSES

logger = logging.getLogger("acervator.materials")

GEAR = "gear"
CONSUMABLE = "consumable"
RESOURCE = "resource"

#: The three storage classes, which never take the same space as each other.
STORAGE_CLASSES: tuple[str, ...] = (GEAR, CONSUMABLE, RESOURCE)

#: The classes counted in fixed slots. Only ``GEAR`` takes one.
SLOT_STORAGE_CLASSES: tuple[str, ...] = (GEAR,)

#: The classes that stack, their ceiling ``STACK_CEILING_ABSENT``.
STACK_STORAGE_CLASSES: tuple[str, ...] = (CONSUMABLE, RESOURCE)

#: A stacking class's ceiling while no figure sets how large a stack runs.
STACK_CEILING_ABSENT = None

#: The share of an embedded amount a salvage returns while no figure sets it.
SALVAGE_RECOVERY_ABSENT = None

#: The quality grades, ``loot_drop.TIER_NAMES`` in its own order, lowest first.
QUALITY_GRADES: tuple[str, ...] = TIER_NAMES

#: The two ends of a band, the lowest grade and the highest.
BAND_ENDS = 2

#: The metal whose band every other entry in ``MATERIALS`` takes.
BAND_METAL = "iron"

#: What ``_metal_materials`` adds to a metal to name the material it is dug from.
ORE_SUFFIX = " ore"


class MaterialError(RuntimeError):
    """Base for every refusal this module raises."""


class UnknownMaterialError(MaterialError):
    """Raised by ``material_named`` for a name ``MATERIAL_NAMES`` does not carry."""


class UnknownQualityError(MaterialError):
    """Raised by ``quality_index`` for a grade ``QUALITY_GRADES`` does not carry."""


class UnknownStorageClassError(MaterialError):
    """Raised for a class outside ``STORAGE_CLASSES``."""


class MaterialValueError(MaterialError):
    """Raised for a band amount under ``QUINTESSENCE_MINIMUM_UNIT`` or off its grid."""


class MaterialGridError(MaterialError):
    """Raised at import when ``grid_faults`` finds an amount no bucket can hold."""


def _as_band_amount(value: object, name: str) -> Decimal:
    """Return ``value`` as a Decimal on the minimum-unit grid, at or above one unit."""
    if not isinstance(value, Decimal):
        raise MaterialValueError(
            f"{name} must be a Decimal, not {type(value).__name__}",
        )
    if not value.is_finite():
        raise MaterialValueError(f"{name} must be finite, got {value!r}")
    if value < QUINTESSENCE_MINIMUM_UNIT:
        raise MaterialValueError(
            f"{name} of {amount_text(value)} is under the "
            f"{amount_text(QUINTESSENCE_MINIMUM_UNIT)} minimum unit, and no "
            f"material embeds less Quintessence than the currency expresses",
        )
    if value > QUINTESSENCE_SUPPLY_CAP:
        raise MaterialValueError(
            f"{name} of {amount_text(value)} is above the "
            f"{amount_text(QUINTESSENCE_SUPPLY_CAP)} Quintessence that can exist",
        )
    if not is_on_quintessence_grid(value):
        raise MaterialValueError(
            f"{name} of {amount_text(value)} is not a whole number of "
            f"{amount_text(QUINTESSENCE_MINIMUM_UNIT)}, and no bucket holds it",
        )
    return value


def _as_storage_class(value: object) -> str:
    """Return ``value`` as one of ``STORAGE_CLASSES``, refusing every other name."""
    if value not in STORAGE_CLASSES:
        raise UnknownStorageClassError(
            f"{value!r} is not a PoA storage class; "
            f"the three are {', '.join(STORAGE_CLASSES)}",
        )
    return str(value)


def occupies_slot(storage_class: str) -> bool:
    """Return True while ``storage_class`` is one of ``SLOT_STORAGE_CLASSES``."""
    return _as_storage_class(storage_class) in SLOT_STORAGE_CLASSES


def stacks(storage_class: str) -> bool:
    """Return True while ``storage_class`` is one of ``STACK_STORAGE_CLASSES``."""
    return _as_storage_class(storage_class) in STACK_STORAGE_CLASSES


@dataclass(frozen=True)
class Material:
    """One material: its storage class, its embedded band, and its weight a unit.

    ``provenance`` says whether the operator set the band or it is still working.
    """

    name: str
    storage_class: str
    quintessence_at_lowest_quality: Decimal
    quintessence_at_highest_quality: Decimal
    weight_per_unit: Decimal
    provenance: str
    note: str

    def __post_init__(self) -> None:
        """Refuse a blank name or note, a bad class or provenance, and a bad band."""
        if not self.name.strip():
            raise UnknownMaterialError(f"a material needs a name, got {self.name!r}")
        if not self.note.strip():
            raise MaterialError(f"{self.name} needs a note on where its band came from")
        _as_storage_class(self.storage_class)
        if self.provenance not in PROVENANCES:
            raise MaterialError(
                f"{self.name} claims provenance {self.provenance!r}; "
                f"the three are {', '.join(PROVENANCES)}",
            )
        lowest = _as_band_amount(
            self.quintessence_at_lowest_quality,
            f"{self.name} at lowest quality",
        )
        highest = _as_band_amount(
            self.quintessence_at_highest_quality,
            f"{self.name} at highest quality",
        )
        if highest < lowest:
            raise MaterialValueError(
                f"{self.name} embeds {amount_text(highest)} at its highest quality "
                f"and {amount_text(lowest)} at its lowest",
            )
        if not isinstance(self.weight_per_unit, Decimal):
            raise MaterialValueError(
                f"{self.name} weight_per_unit must be a Decimal, "
                f"not {type(self.weight_per_unit).__name__}",
            )
        if not self.weight_per_unit.is_finite() or self.weight_per_unit < 0:
            raise MaterialValueError(
                f"{self.name} weight_per_unit must be finite and not negative",
            )

    @property
    def takes_a_slot(self) -> bool:
        """True while ``occupies_slot`` answers True for this ``storage_class``."""
        return occupies_slot(self.storage_class)

    def to_dict(self) -> dict:
        """Serve this material as a JSON-safe dict, every amount a plain string."""
        return {
            "name": self.name,
            "storage_class": self.storage_class,
            "occupies_slot": self.takes_a_slot,
            "stacks": stacks(self.storage_class),
            "stack_ceiling": STACK_CEILING_ABSENT,
            "quintessence_at_lowest_quality": amount_text(
                self.quintessence_at_lowest_quality,
            ),
            "quintessence_at_highest_quality": amount_text(
                self.quintessence_at_highest_quality,
            ),
            "weight_per_unit": amount_text(self.weight_per_unit),
            "salvage_recovery": SALVAGE_RECOVERY_ABSENT,
            "provenance": self.provenance,
            "note": self.note,
        }


def _ore_note(metal: str) -> str:
    """Return the note for ``metal``'s ore, naming whose figures its band carries."""
    if metal == BAND_METAL:
        return (
            "the operator's own band on the Quintessence one unit of iron ore "
            "embeds, from its lowest quality to its highest"
        )
    return (
        f"takes the {BAND_METAL} ore band until the operator names this "
        f"material's own scale"
    )


def _metal_materials() -> tuple[Material, ...]:
    """One ore a metal ``rpg_classes.CLASSES`` declares, in its declared order."""
    metals = tuple(dict.fromkeys(entry.metal for entry in CLASSES))
    return tuple(
        Material(
            name=metal + ORE_SUFFIX,
            storage_class=RESOURCE,
            quintessence_at_lowest_quality=IRON_ORE_QUINTESSENCE_LOW_QUALITY,
            quintessence_at_highest_quality=IRON_ORE_QUINTESSENCE_HIGH_QUALITY,
            weight_per_unit=WEIGHT_PER_MATERIAL_UNIT,
            provenance=DECIDED if metal == BAND_METAL else WORKING,
            note=_ore_note(metal),
        )
        for metal in metals
    )


# An embedded amount counts against QUINTESSENCE_SUPPLY_CAP and sits in no wallet.
# A Material declares its band; QuintessenceLedger owns every movement of it.
MATERIALS: tuple[Material, ...] = _metal_materials()

#: Every name in ``MATERIALS``, in the order it declares them.
MATERIAL_NAMES: tuple[str, ...] = tuple(entry.name for entry in MATERIALS)

if len(set(MATERIAL_NAMES)) != len(MATERIAL_NAMES):
    raise UnknownMaterialError(f"MATERIALS declares a name twice: {MATERIAL_NAMES}")

if len(QUALITY_GRADES) < BAND_ENDS:
    raise UnknownQualityError(
        f"a band needs {BAND_ENDS} ends, and QUALITY_GRADES carries {QUALITY_GRADES}",
    )


def material_named(name: str) -> Material:
    """Return the entry in ``MATERIALS`` whose ``name`` matches, refusing the rest."""
    for entry in MATERIALS:
        if entry.name == name:
            return entry
    raise UnknownMaterialError(
        f"{name!r} is not a PoA material; "
        f"the table carries {', '.join(MATERIAL_NAMES)}",
    )


def materials_in_storage_class(storage_class: str) -> tuple[Material, ...]:
    """Every entry in ``MATERIALS`` whose ``storage_class`` matches."""
    wanted = _as_storage_class(storage_class)
    return tuple(entry for entry in MATERIALS if entry.storage_class == wanted)


def quality_index(quality: str) -> int:
    """Return the place ``quality`` takes in ``QUALITY_GRADES``, refusing the rest."""
    if quality not in QUALITY_GRADES:
        raise UnknownQualityError(
            f"{quality!r} is not a PoA quality grade; "
            f"the grades are {', '.join(QUALITY_GRADES)}",
        )
    return QUALITY_GRADES.index(quality)


def embedded_quintessence(material: Material, quality: str) -> Decimal:
    """Return the Quintessence one unit of ``material`` embeds at ``quality``.

    The band divides evenly over ``QUALITY_GRADES`` and its two ends answer the
    material's own two figures.
    """
    steps = len(QUALITY_GRADES) - 1
    span = (
        material.quintessence_at_highest_quality
        - material.quintessence_at_lowest_quality
    )
    reached = quality_index(quality)
    return material.quintessence_at_lowest_quality + span * reached / steps


def salvage_loss_rule() -> str:
    """Return the operator's rule on a salvage loss, which no figure here sets."""
    return (
        "much of an embedded amount is lost when an item is destroyed for its "
        "Quintessence, and advanced salvaging skill mitigates only part of that "
        "loss; salvage without proportionate skill is destructive"
    )


def material_rows() -> list[dict]:
    """One row an entry in ``MATERIALS``, as ``to_dict`` serves it."""
    return [entry.to_dict() for entry in MATERIALS]


def embedded_rows() -> list[dict]:
    """One row a material at a grade: its name, the grade, and what it embeds."""
    return [
        {
            "material": entry.name,
            "quality": quality,
            "quintessence": amount_text(embedded_quintessence(entry, quality)),
        }
        for entry in MATERIALS
        for quality in QUALITY_GRADES
    ]


def grid_faults() -> tuple[tuple[str, str, str, str], ...]:
    """Every material and grade whose embedded amount breaks one of the three rules.

    One row is the material, the grade, the amount and the rule it broke.
    """
    out: list[tuple[str, str, str, str]] = []
    unit = amount_text(QUINTESSENCE_MINIMUM_UNIT)
    for entry in MATERIALS:
        for quality in QUALITY_GRADES:
            amount = embedded_quintessence(entry, quality)
            if amount < QUINTESSENCE_MINIMUM_UNIT:
                out.append(
                    (entry.name, quality, amount_text(amount), f"under {unit}"),
                )
            if not is_on_quintessence_grid(amount):
                out.append(
                    (
                        entry.name,
                        quality,
                        amount_text(amount),
                        f"not a whole number of {unit}",
                    ),
                )
        ends = (
            (QUALITY_GRADES[0], entry.quintessence_at_lowest_quality),
            (QUALITY_GRADES[-1], entry.quintessence_at_highest_quality),
        )
        for quality, declared in ends:
            reached = embedded_quintessence(entry, quality)
            if reached != declared:
                out.append(
                    (
                        entry.name,
                        quality,
                        amount_text(reached),
                        f"does not reproduce the declared {amount_text(declared)}",
                    ),
                )
    logger.info(
        "drove %s materials across %s quality grades, %s amounts broke a rule",
        len(MATERIALS),
        len(QUALITY_GRADES),
        len(out),
    )
    return tuple(out)


_FAULTS = grid_faults()
if _FAULTS:
    raise MaterialGridError(
        f"a material embeds Quintessence no bucket holds: {_FAULTS}",
    )
