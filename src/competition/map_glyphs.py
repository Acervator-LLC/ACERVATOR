"""The map mark of every PoA kind: one glyph and one colour token a kind.

``PLANET_GLYPHS`` gives a class its glyph through the ``planet`` field
``rpg_classes.CLASSES`` already carries, ``TIER_GLYPHS`` ranks the five loot
tiers and ``MODE_GLYPHS`` the four event modes. ``marks`` serves all sixteen
after ``require_distinct_marks`` refuses a repeated glyph, and
``ABSENT_FAMILIES`` names each kind no module under ``src`` builds an entity for.
"""

from __future__ import annotations

from dataclasses import dataclass

from .loot_drop import (
    CALX,
    CAUDA_PAVONIS,
    ELIXIR,
    FLORES,
    LOOT_TIERS,
    MAGISTERIUM,
    LootTier,
)
from .poa_modes import (
    DUNGEON_CRAWL,
    MODES,
    MONSTER_SMASH,
    RAID,
    TEAM_MONSTER_SMASH,
    EventMode,
)
from .rpg_classes import (
    CLASSES,
    DAMAGE,
    PURE_HEALER,
    PURE_SUPPORT,
    SUPPORT_HEALER,
    TANK,
    CharacterClass,
)

VESSEL_FAMILY = "Vessel"
LOOT_FAMILY = "Loot tier"
EVENT_FAMILY = "Event mode"

#: Every family ``marks`` serves, in the order it serves them.
FAMILIES: tuple[str, ...] = (VESSEL_FAMILY, LOOT_FAMILY, EVENT_FAMILY)

# U+2642 and U+2640 are named MALE SIGN and FEMALE SIGN, the standard alchemical
# marks for Mars iron and Venus copper.
PLANET_GLYPHS: dict[str, str] = {
    "Saturn": "♄",
    "Jupiter": "♃",
    "Mars": "♂",
    "Sol": "☉",
    "Mercury": "☿",
    "Venus": "♀",
    "Luna": "☽",
}

#: The colour token each ``rpg_classes.ASSIGNMENTS`` entry paints its glyph in.
ASSIGNMENT_COLOUR_TOKENS: dict[str, str] = {
    TANK: "INFO",
    DAMAGE: "DANGER",
    PURE_HEALER: "SUCCESS",
    SUPPORT_HEALER: "PRIMARY",
    PURE_SUPPORT: "WARNING",
}

#: The alchemical stage each tier name denotes, rising with rarity.
TIER_GLYPHS: dict[str, str] = {
    CALX: "⊖",
    CAUDA_PAVONIS: "⚹",
    FLORES: "⚘",
    ELIXIR: "☥",
    MAGISTERIUM: "⛤",
}

#: The rarity ramp, from the commonest tier's grey to the rarest tier's gold.
TIER_COLOUR_TOKENS: dict[str, str] = {
    CALX: "TEXT_MED",
    CAUDA_PAVONIS: "SUCCESS",
    FLORES: "INFO",
    ELIXIR: "SECONDARY",
    MAGISTERIUM: "ACCENT_GOLD",
}

#: One heraldic mark an event mode: a cross, a banner, a tower and a shield.
MODE_GLYPHS: dict[str, str] = {
    MONSTER_SMASH: "✠",
    TEAM_MONSTER_SMASH: "⚑",
    DUNGEON_CRAWL: "♖",
    RAID: "⛨",
}

#: The heat ramp over ``poa_modes.EventMode.tier``, coolest mode first.
MODE_COLOUR_TOKENS: dict[str, str] = {
    MONSTER_SMASH: "STATE_ARMED",
    TEAM_MONSTER_SMASH: "WARNING",
    DUNGEON_CRAWL: "WARNING_STRONG",
    RAID: "DANGER",
}

#: Each kind the directive names that no module under ``src`` holds an entity for.
ABSENT_FAMILIES: dict[str, str] = {
    "Monster": (
        "No module declares a monster, so nothing supplies a name to draw. The "
        "art brief's 21 designs across 6 tiers are in no file under src."
    ),
    "World fact kind": (
        "world_grid.WorldFact.kind is text the caller passes in, and no module "
        "under src names one, so no asset kind has a mark."
    ),
    "Zone terrain": (
        "world_grid.ZoneRegion carries a boundary and a discoverer and no "
        "terrain kind, so no terrain has a mark."
    ),
}


class MapMarkError(RuntimeError):
    """Base for every refusal this module raises."""


class MissingGlyphError(MapMarkError):
    """Raised when a kind in ``CLASSES``, ``LOOT_TIERS`` or ``MODES`` has no glyph."""


class RepeatedGlyphError(MapMarkError):
    """Raised by ``require_distinct_marks`` when two kinds carry one glyph."""


class UnknownMarkError(MapMarkError):
    """Raised by ``mark_for`` for a kind no family declares."""


@dataclass(frozen=True)
class MapMark:
    """One kind's map mark: its ``glyph`` and the ``colour_token`` painting it.

    ``kind`` is the class name, the tier name or the mode code, and ``label`` is
    what the screen prints beside the glyph.
    """

    kind: str
    family: str
    label: str
    glyph: str
    colour_token: str

    @property
    def codepoint(self) -> str:
        """``glyph`` as its ``U+XXXX`` codepoint, which the legend prints."""
        return "U+%04X" % ord(self.glyph)

    def to_dict(self) -> dict:
        """Return this mark as the PoA tab surface serves it."""
        return {
            "kind": self.kind,
            "family": self.family,
            "label": self.label,
            "glyph": self.glyph,
            "colour_token": self.colour_token,
            "codepoint": self.codepoint,
        }


def glyph_for_planet(planet: str) -> str:
    """The glyph ``PLANET_GLYPHS`` holds for ``planet``, raising for any other."""
    held = PLANET_GLYPHS.get(planet)
    if held is None:
        refusal = (
            f"{planet!r} has no glyph; the seven planets are "
            f"{', '.join(PLANET_GLYPHS)}"
        )
        raise MissingGlyphError(refusal)
    return held


def class_mark(entry: CharacterClass) -> MapMark:
    """The mark for one ``CLASSES`` entry, glyphed by its planet."""
    token = ASSIGNMENT_COLOUR_TOKENS.get(entry.assignment)
    if token is None:
        refusal = (
            f"{entry.assignment!r} has no colour token; the assignments are "
            f"{', '.join(ASSIGNMENT_COLOUR_TOKENS)}"
        )
        raise MissingGlyphError(refusal)
    return MapMark(
        kind=entry.name,
        family=VESSEL_FAMILY,
        label=f"{entry.name} - {entry.planet}",
        glyph=glyph_for_planet(entry.planet),
        colour_token=token,
    )


def tier_mark(tier: LootTier) -> MapMark:
    """One ``LOOT_TIERS`` entry's mark, labelled by name and a differing short_form."""
    glyph = TIER_GLYPHS.get(tier.name)
    token = TIER_COLOUR_TOKENS.get(tier.name)
    if glyph is None or token is None:
        refusal = f"{tier.name!r} has no glyph and colour token pair in this module"
        raise MissingGlyphError(refusal)
    short = "" if tier.short_form == tier.name else f" - {tier.short_form}"
    return MapMark(
        kind=tier.name,
        family=LOOT_FAMILY,
        label=f"{tier.name}{short}",
        glyph=glyph,
        colour_token=token,
    )


def mode_mark(mode: EventMode) -> MapMark:
    """The mark for one ``MODES`` entry, labelled by the mode's own label."""
    glyph = MODE_GLYPHS.get(mode.code)
    token = MODE_COLOUR_TOKENS.get(mode.code)
    if glyph is None or token is None:
        refusal = f"{mode.code!r} has no glyph and colour token pair in this module"
        raise MissingGlyphError(refusal)
    return MapMark(
        kind=mode.code,
        family=EVENT_FAMILY,
        label=mode.label,
        glyph=glyph,
        colour_token=token,
    )


def require_distinct_marks(held: tuple[MapMark, ...]) -> tuple[MapMark, ...]:
    """Return ``held`` after refusing a glyph or a kind two marks share."""
    by_glyph: dict[str, str] = {}
    for mark in held:
        standing = by_glyph.get(mark.glyph)
        if standing is not None:
            refusal = (
                f"{mark.kind} and {standing} both draw {mark.codepoint}; "
                f"a map needs one glyph a kind"
            )
            raise RepeatedGlyphError(refusal)
        by_glyph[mark.glyph] = mark.kind
    if len(by_glyph) != len(held):
        raise RepeatedGlyphError(f"{len(held)} marks carry {len(by_glyph)} kinds")
    return held


def marks() -> tuple[MapMark, ...]:
    """Every mark, Vessels then loot tiers then event modes, each one distinct."""
    held = (
        tuple(class_mark(entry) for entry in CLASSES)
        + tuple(tier_mark(tier) for tier in LOOT_TIERS)
        + tuple(mode_mark(mode) for mode in MODES)
    )
    return require_distinct_marks(held)


def mark_for(kind: str) -> MapMark:
    """The mark whose ``kind`` matches, raising ``UnknownMarkError`` for any other."""
    for mark in marks():
        if mark.kind == kind:
            return mark
    refusal = f"{kind!r} has no map mark; the kinds are {', '.join(mark_kinds())}"
    raise UnknownMarkError(refusal)


def mark_kinds() -> tuple[str, ...]:
    """Every ``MapMark.kind``, in the order ``marks`` serves them."""
    return tuple(mark.kind for mark in marks())


def marks_in(family: str) -> tuple[MapMark, ...]:
    """Every mark whose ``family`` matches, empty for a family outside ``FAMILIES``."""
    return tuple(mark for mark in marks() if mark.family == family)


def colour_token_names() -> tuple[str, ...]:
    """Every colour token the marks name, once each, in first-use order."""
    names: list[str] = []
    for mark in marks():
        if mark.colour_token not in names:
            names.append(mark.colour_token)
    return tuple(names)


def mark_rows() -> list[dict]:
    """Every mark as ``MapMark.to_dict`` serves it, in declared order."""
    return [mark.to_dict() for mark in marks()]


def family_rows() -> list[dict]:
    """One row a family, carrying that family's marks in declared order."""
    return [
        {"family": family, "marks": [mark.to_dict() for mark in marks_in(family)]}
        for family in FAMILIES
    ]


def absent_rows() -> list[dict]:
    """One row each ``ABSENT_FAMILIES`` kind, carrying the sentence it waits on."""
    return [
        {"family": family, "note": note} for family, note in ABSENT_FAMILIES.items()
    ]
