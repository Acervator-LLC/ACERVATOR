"""The seven PoA character classes, their roles, and the per-class level record.

``CLASSES`` holds one class a classical planet, each carrying the Paracelsian
``principle`` of its metal and one ``assignment`` from ``ASSIGNMENTS``.
``class_named`` and ``classes_for_role`` read the array, and ``ClassProgress``
holds one participant's level and experience in one class.
``pick_class`` refuses a name ``CLASSES`` does not carry.
"""

from __future__ import annotations

from dataclasses import dataclass

SALT = "Salt"
SULPHUR = "Sulphur"
MERCURY = "Mercury"

#: The tria prima, one principle a body: solid, combustible, fluid.
PRINCIPLES: tuple[str, ...] = (SALT, SULPHUR, MERCURY)

TANK = "Tank"
DAMAGE = "Damage"
HEALER = "Healer"
SUPPORT = "Support"

#: The four roles. Support is the role the class array gained with Mercury's split.
ROLES: tuple[str, ...] = (TANK, DAMAGE, HEALER, SUPPORT)

PURE_HEALER = "pure healer"
SUPPORT_HEALER = "support healer"
PURE_SUPPORT = "pure support"

#: The five ways a class is assigned across ``ROLES``.
ASSIGNMENTS: tuple[str, ...] = (
    TANK,
    DAMAGE,
    PURE_HEALER,
    SUPPORT_HEALER,
    PURE_SUPPORT,
)

#: Roles each assignment carries. Only SUPPORT_HEALER carries two.
ASSIGNMENT_ROLES: dict[str, tuple[str, ...]] = {
    TANK: (TANK,),
    DAMAGE: (DAMAGE,),
    PURE_HEALER: (HEALER,),
    SUPPORT_HEALER: (HEALER, SUPPORT),
    PURE_SUPPORT: (SUPPORT,),
}

#: Levels in one ability arc. Each alchemical phase of the chain opens another.
ARC_LEVELS = 100

#: The level a class starts at before any event is played.
FIRST_LEVEL = 1


@dataclass(frozen=True)
class CharacterClass:
    """One of the seven classes: its name, its planet, its metal and its role.

    ``principle`` is the Paracelsian body the metal belongs to, and
    ``assignment`` is one of ``ASSIGNMENTS``.
    """

    name: str
    planet: str
    metal: str
    principle: str
    assignment: str

    @property
    def roles(self) -> tuple[str, ...]:
        """The roles ``assignment`` carries, read from ``ASSIGNMENT_ROLES``."""
        return ASSIGNMENT_ROLES[self.assignment]


CLASSES: tuple[CharacterClass, ...] = (
    CharacterClass("Lead Ward", "Saturn", "lead", SALT, TANK),
    CharacterClass("Tin Bulwark", "Jupiter", "tin", SALT, TANK),
    CharacterClass("Iron Edge", "Mars", "iron", SULPHUR, DAMAGE),
    CharacterClass("Solar Lance", "Sol", "gold", SULPHUR, DAMAGE),
    CharacterClass(
        "Quicksilver Draught",
        "Mercury",
        "quicksilver",
        MERCURY,
        PURE_HEALER,
    ),
    CharacterClass("Copper Conduit", "Venus", "copper", MERCURY, SUPPORT_HEALER),
    CharacterClass("Silver Mirror", "Luna", "silver", MERCURY, PURE_SUPPORT),
)

#: Every class name, in the order ``CLASSES`` declares them.
CLASS_NAMES: tuple[str, ...] = tuple(entry.name for entry in CLASSES)


class UnknownClassError(ValueError):
    """Raised by ``pick_class`` for a name ``CLASS_NAMES`` does not carry."""


@dataclass
class ClassProgress:
    """One participant's standing in one class, levelled on its own.

    ``level`` and ``experience`` are state this package keeps; no trading field
    holds either.
    """

    class_name: str
    level: int = FIRST_LEVEL
    experience: int = 0


@dataclass(frozen=True)
class ClassPick:
    """The class one ``participant`` plays for one ``event_id``."""

    participant: str
    event_id: str
    class_name: str


def class_named(name: str) -> CharacterClass | None:
    """The entry in ``CLASSES`` whose ``name`` matches, or None for any other."""
    for entry in CLASSES:
        if entry.name == name:
            return entry
    return None


def pick_class(participant: str, event_id: str, class_name: str) -> ClassPick:
    """Return a ``ClassPick``, raising for a name outside ``CLASS_NAMES``."""
    if class_named(class_name) is None:
        refusal = (
            f"{class_name!r} is not a PoA class; "
            f"the seven are {', '.join(CLASS_NAMES)}"
        )
        raise UnknownClassError(refusal)
    return ClassPick(participant, event_id, class_name)


def class_row(entry: CharacterClass) -> dict:
    """One ``CharacterClass`` as the PoA tab surface serves it."""
    return {
        "name": entry.name,
        "planet": entry.planet,
        "metal": entry.metal,
        "principle": entry.principle,
        "assignment": entry.assignment,
        "roles": list(entry.roles),
        "level": FIRST_LEVEL,
    }


def class_rows() -> list[dict]:
    """Every entry in ``CLASSES`` as ``class_row`` serves it, in declared order."""
    return [class_row(entry) for entry in CLASSES]
