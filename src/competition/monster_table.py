"""The twelve monster tiers by signed depth, and the designs the art brief names.

``MONSTER_TIER_TABLE`` carries ``RANKS_PER_SIDE`` tiers below the participant's
plane and the same number above. ``BRIEF_DESIGNS`` is the closed transcription of
the art brief and ``MONSTER_DESIGNS`` is the open roster every consumer reads, so
``designs_at_depth`` answers a tier of any size. ``require_admissible`` applies
the two conditions in ``ADMISSION_CONDITIONS`` and refuses a source carrying a
``REFUSED_SOURCE_MARKERS`` term. Every tier's ``level`` is ``FIGURE_ABSENT``, and
``tier_embedded_quintessence`` raises ``LevelAbsentError`` until one is named, at
which point ``embedded_quintessence_at_level`` reads the amount out of
``entity_stats.quintessence_requirement``. ``require_monster_table`` drives the
table against the brief's published counts and runs once at import.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .entity_stats import quintessence_requirement, stat_block_at_level

if TYPE_CHECKING:
    from decimal import Decimal

logger = logging.getLogger("acervator.monster_table")

#: Tiers one side of the participant's plane. Twice this is the whole table.
RANKS_PER_SIDE = 6

#: The ``rank`` at which a tier's nature fixes its form.
OUTERMOST_RANK = RANKS_PER_SIDE

DESCENDING = "descending"
ASCENDING = "ascending"

#: The two sides a ``depth`` sign answers. There is no third and no zero.
DIRECTIONS: tuple[str, ...] = (DESCENDING, ASCENDING)

SOURCED = "sourced"
INVENTED = "invented"

#: How a design's entities are attested. A ``SOURCED`` row names its text.
ATTESTATIONS: tuple[str, ...] = (SOURCED, INVENTED)

#: A figure no source sets. Its tier's other fields say what would set it.
FIGURE_ABSENT = None

#: A line no source writes, as in an ascending tier's ``nature``.
TEXT_ABSENT = ""

#: The ``source`` of the summit, which the brief marks as modern invention.
INVENTED_SOURCE = "built on Lovecraft, modern fiction"

#: What every tier owes, and what it buys once named.
LEVEL_OWED_NOTE = (
    "the character level this tier sits at. No source names one. Once named, "
    "embedded_quintessence_at_level reads the amount out of "
    "entity_stats.quintessence_requirement instead of choosing it"
)

#: Both conditions a creature meets to enter ``MONSTER_DESIGNS``.
ADMISSION_CONDITIONS: tuple[str, ...] = (
    "a position on the nature axis, by what the creature fundamentally is",
    "a source attested in its own pre-modern text, named and verifiable",
)

#: Every body of material ``require_admissible`` refuses a source drawn from.
REFUSED_SOURCES: tuple[str, ...] = (
    "nineteenth and twentieth century occult revival",
    "correspondence tables, tarot-to-sphere charts and planetary seal sets",
    "Golden Dawn godforms and Enochian alphabet plates",
    "reconstructed Egypt, against attested funerary and temple imagery",
    "anything Crowley, or beyond the old verified texts",
)

#: The term ``admission_refusal`` matches, each named in ``REFUSED_SOURCES``.
REFUSED_SOURCE_MARKERS: tuple[str, ...] = (
    "crowley",
    "golden dawn",
    "enochian",
    "oto",
    "thelema",
    "tarot",
    "correspondence table",
    "planetary seal",
    "new age",
    "occult revival",
)

#: How an arbitrary creature is placed on the axis by its nature. None states one.
PLACEMENT_RULE: str = TEXT_ABSENT

#: What the brief says nearest a placement rule, and it places no creature.
PLACEMENT_RULE_NOTE = (
    "the art brief splits its entities four ways by how they behave and names "
    "no rule assigning an arbitrary creature to a tier"
)

#: Nothing ties a tier to a world layer. Twelve does not divide SEPHIROT_LAYERS.
WORLD_LAYER_TIE_ABSENT = (
    "no statement ties a monster tier to a world_grid layer. The dungeon's ten "
    "floors take the ten sphere names; the twelve tiers take none of them"
)

#: Waypoints naming the ascending side's nature. Nothing assigns one to a tier.
ASCENDING_FAMILIES: tuple[str, ...] = ("Angels", "Watchers", "Others")

#: The family ``both_sided_families`` finds on both sides of the plane.
FAMILIES_ON_BOTH_SIDES: tuple[str, ...] = ("Watchers",)

CAST_STATE = "cast"

#: Frames a state, off the brief's five motion durations.
STATE_FRAMES: dict[str, int] = {
    "idle": 4,
    "attack": 5,
    "hit": 2,
    "death": 10,
    CAST_STATE: 5,
}

#: Frames one entity that casts, adding every member of ``STATE_FRAMES``.
FRAMES_WITH_CAST = sum(STATE_FRAMES.values())

#: Frames one entity with no ability, dropping ``CAST_STATE``.
FRAMES_WITHOUT_CAST = FRAMES_WITH_CAST - STATE_FRAMES[CAST_STATE]

#: Frames the brief publishes an entity that casts.
BRIEF_FRAMES_WITH_CAST = 26

#: Frames the brief publishes an entity with no ability.
BRIEF_FRAMES_WITHOUT_CAST = 21

#: Frames the brief publishes a tier, keyed by depth. Its tier N is depth -N.
BRIEF_TIER_FRAMES: dict[int, int] = {
    -1: 63,
    -2: 156,
    -3: 936,
    -4: 182,
    -5: 78,
    -6: 52,
}

#: Frames the brief publishes for the tiers whose designs it names.
BRIEF_ROSTER_FRAMES = 531

#: Drawing jobs the brief publishes across the tiers whose designs it names.
BRIEF_DESIGN_COUNT = 21

#: Entity names the brief publishes as attested in a text.
BRIEF_ATTESTED_NAMES = 21

#: Entity names the brief publishes in all, attested and invented together.
BRIEF_TOTAL_NAMES = 23


class MonsterTableError(RuntimeError):
    """Base for every refusal this module raises."""


class UnknownMonsterTierError(MonsterTableError):
    """Raised by ``monster_tier_at`` for a depth ``MONSTER_TIER_TABLE`` lacks."""


class UnknownDesignError(MonsterTableError):
    """Raised by ``design_named`` for a name ``DESIGN_NAMES`` does not carry."""


class TierSpecError(MonsterTableError):
    """Raised by ``require_design_specs`` when a design leaves its tier's block."""


class RepeatedDesignError(MonsterTableError):
    """Raised by ``require_distinct_design_names`` when two rows share a name."""


class LevelAbsentError(MonsterTableError):
    """Raised by ``tier_embedded_quintessence`` while a tier's ``level`` is absent."""


class InadmissibleCreatureError(MonsterTableError):
    """Raised by ``require_admissible`` for a creature failing either condition."""


class BriefDisagreementError(MonsterTableError):
    """Raised by ``require_brief_frame_totals`` when a count leaves the brief."""


@dataclass(frozen=True)
class MonsterTier:
    """One position on the nature axis, at a signed ``depth`` that is never zero.

    ``nominal_cell_px`` holds the sizes the tier's sprites are authored at and
    reaches no power figure. ``entities`` counts the drawing jobs the tier needs
    and ``level`` is ``FIGURE_ABSENT`` on every row.
    """

    depth: int
    name: str
    nature: str
    entities: int | None
    nominal_cell_px: tuple[int, ...]
    frames_per_entity: int | None
    on_screen_low: int | None
    on_screen_high: int | None
    behaviour: str
    silhouette: str
    register_note: str
    form_bound: bool | None
    level: int | None
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        """Refuse a zero depth and a depth past ``RANKS_PER_SIDE`` either side."""
        if self.depth == 0 or abs(self.depth) > RANKS_PER_SIDE:
            refusal = (
                f"a tier sits at 1 to {RANKS_PER_SIDE} either side of the "
                f"participant's plane, got depth {self.depth}"
            )
            raise UnknownMonsterTierError(refusal)

    @property
    def direction(self) -> str:
        """Answer ``DESCENDING`` below the participant's plane, ``ASCENDING`` above."""
        return DESCENDING if self.depth < 0 else ASCENDING

    @property
    def rank(self) -> int:
        """Answer this tier's place on its own side, 1 to ``RANKS_PER_SIDE``."""
        return abs(self.depth)

    def to_dict(self) -> dict:
        """Return this tier as a JSON-safe dict, every absence its own literal."""
        return {
            "depth": self.depth,
            "direction": self.direction,
            "rank": self.rank,
            "name": self.name,
            "nature": self.nature,
            "entities": self.entities,
            "nominal_cell_px": list(self.nominal_cell_px),
            "frames_per_entity": self.frames_per_entity,
            "on_screen_low": self.on_screen_low,
            "on_screen_high": self.on_screen_high,
            "behaviour": self.behaviour,
            "silhouette": self.silhouette,
            "register_note": self.register_note,
            "form_bound": self.form_bound,
            "level": self.level,
            "level_note": LEVEL_OWED_NOTE,
            "sources": list(self.sources),
        }


@dataclass(frozen=True)
class MonsterDesign:
    """One drawing job, the entities it covers, and the text attesting them.

    ``nominal_cell_px`` is the size this sprite is authored at. ``source`` names
    the text for a ``SOURCED`` row and ``INVENTED_SOURCE`` for an invented one.
    """

    name: str
    depth: int
    entity_names: tuple[str, ...]
    source: str
    attestation: str
    nominal_cell_px: int
    frames: int
    on_screen_low: int
    on_screen_high: int

    def __post_init__(self) -> None:
        """Refuse a blank ``name`` or ``source`` and an unknown ``attestation``."""
        if not self.name.strip():
            refusal = f"a design needs a name, got {self.name!r}"
            raise UnknownDesignError(refusal)
        if not self.source.strip():
            refusal = f"{self.name} needs the source attesting it"
            raise TierSpecError(refusal)
        if self.attestation not in ATTESTATIONS:
            refusal = (
                f"{self.name} claims attestation {self.attestation!r}; "
                f"one of {ATTESTATIONS} was expected"
            )
            raise TierSpecError(refusal)

    def to_dict(self) -> dict:
        """Return this design as a JSON-safe dict."""
        return {
            "name": self.name,
            "depth": self.depth,
            "entity_names": list(self.entity_names),
            "source": self.source,
            "attestation": self.attestation,
            "nominal_cell_px": self.nominal_cell_px,
            "frames": self.frames,
            "on_screen_low": self.on_screen_low,
            "on_screen_high": self.on_screen_high,
        }


_DESCENDING_TIERS: tuple[MonsterTier, ...] = (
    MonsterTier(
        depth=-1,
        name="the surface floor",
        nature="afflicters with an appetite and no mandate",
        entities=3,
        nominal_cell_px=(32,),
        frames_per_entity=FRAMES_WITHOUT_CAST,
        on_screen_low=4,
        on_screen_high=8,
        behaviour="single target, closes, bites, dies quickly",
        silhouette="open form, light on the outside, rim lit",
        register_note=TEXT_ABSENT,
        form_bound=False,
        level=FIGURE_ABSENT,
        sources=(),
    ),
    MonsterTier(
        depth=-2,
        name="executors of a mandate or of fate",
        nature="cold, not wicked",
        entities=6,
        nominal_cell_px=(48,),
        frames_per_entity=FRAMES_WITH_CAST,
        on_screen_low=4,
        on_screen_high=6,
        behaviour="acts on a condition, never on a grudge; no taunt, no gloat",
        silhouette="form half closed; the light is behind a grille",
        register_note="the attack animation has no wind-up flourish; it executes",
        form_bound=False,
        level=FIGURE_ABSENT,
        sources=(),
    ),
    MonsterTier(
        depth=-3,
        name="the decan rank",
        nature=TEXT_ABSENT,
        entities=36,
        nominal_cell_px=(64,),
        frames_per_entity=FRAMES_WITH_CAST,
        on_screen_low=2,
        on_screen_high=3,
        behaviour="applies the affliction of the body part it owns, and can lift it",
        silhouette="an engraved figure, flat and frontal, like a cut gem",
        register_note=(
            "a decan is not a demon; the text invokes it to heal; draw "
            "authority, not malice"
        ),
        form_bound=False,
        level=FIGURE_ABSENT,
        sources=(
            "The Sacred Book of Hermes to Asclepius",
            "Stobaean Hermetica 6, Hermes to Tat, On the Decans",
        ),
    ),
    MonsterTier(
        depth=-4,
        name="floor bosses",
        nature="adversaries of cosmic order",
        entities=7,
        nominal_cell_px=(96,),
        frames_per_entity=FRAMES_WITH_CAST,
        on_screen_low=1,
        on_screen_high=1,
        behaviour="attacks the order of the floor itself, not only the party",
        silhouette="form mostly closed; light escapes as a seam along the spine",
        register_note=TEXT_ABSENT,
        form_bound=False,
        level=FIGURE_ABSENT,
        sources=(),
    ),
    MonsterTier(
        depth=-5,
        name="the fall tier",
        nature="morally dualist, with a rebellion behind it",
        entities=3,
        nominal_cell_px=(96,),
        frames_per_entity=FRAMES_WITH_CAST,
        on_screen_low=1,
        on_screen_high=2,
        behaviour="uses the party's own craft vocabulary against it",
        silhouette="a closed shell wearing worked metal it made itself",
        register_note=(
            "the only tier that is morally wicked; it fell, and everything "
            "above it is indifferent"
        ),
        form_bound=False,
        level=FIGURE_ABSENT,
        sources=(),
    ),
    MonsterTier(
        depth=-6,
        name="the summit",
        nature=TEXT_ABSENT,
        entities=2,
        nominal_cell_px=(160, 96),
        frames_per_entity=FRAMES_WITH_CAST,
        on_screen_low=1,
        on_screen_high=3,
        behaviour=TEXT_ABSENT,
        silhouette=(
            "a sealed shell; the light inside is a hairline crack and nothing "
            "more; the form does not read as an animal or a person"
        ),
        register_note=(
            "it does not notice the party; its attack animation has no "
            "target-acquire frame"
        ),
        form_bound=True,
        level=FIGURE_ABSENT,
        sources=(
            (
                "Stobaean Hermetica 6, Hermes to Tat, On the Decans, "
                "for the two-rank shape alone"
            ),
        ),
    ),
)


def _ascending_tier(rank: int) -> MonsterTier:
    """Build an ascending tier at ``rank``, on the axis and described nowhere."""
    return MonsterTier(
        depth=rank,
        name=TEXT_ABSENT,
        nature=TEXT_ABSENT,
        entities=FIGURE_ABSENT,
        nominal_cell_px=(),
        frames_per_entity=FIGURE_ABSENT,
        on_screen_low=FIGURE_ABSENT,
        on_screen_high=FIGURE_ABSENT,
        behaviour=TEXT_ABSENT,
        silhouette=TEXT_ABSENT,
        register_note=TEXT_ABSENT,
        form_bound=True if rank == OUTERMOST_RANK else FIGURE_ABSENT,
        level=FIGURE_ABSENT,
        sources=(),
    )


_ASCENDING_TIERS: tuple[MonsterTier, ...] = tuple(
    _ascending_tier(rank) for rank in range(1, RANKS_PER_SIDE + 1)
)

#: Every tier, deepest first, the participant's plane crossed at the middle.
MONSTER_TIER_TABLE: tuple[MonsterTier, ...] = (
    tuple(reversed(_DESCENDING_TIERS)) + _ASCENDING_TIERS
)


def monster_tier_at(depth: int) -> MonsterTier:
    """Return the tier at ``depth``, negative below the plane and positive above."""
    for tier in MONSTER_TIER_TABLE:
        if tier.depth == depth:
            return tier
    refusal = (
        f"no tier sits at depth {depth}; "
        f"{[tier.depth for tier in MONSTER_TIER_TABLE]} are declared"
    )
    raise UnknownMonsterTierError(refusal)


def _sourced(
    name: str,
    depth: int,
    source: str,
    entity_names: tuple[str, ...] = (),
) -> MonsterDesign:
    """Build a ``SOURCED`` design, taking cell, frames and screen count off its tier."""
    tier = monster_tier_at(depth)
    return MonsterDesign(
        name=name,
        depth=depth,
        entity_names=entity_names or (name,),
        source=source,
        attestation=SOURCED,
        nominal_cell_px=tier.nominal_cell_px[0],
        frames=tier.frames_per_entity or 0,
        on_screen_low=tier.on_screen_low or 0,
        on_screen_high=tier.on_screen_high or 0,
    )


#: The art brief's own roster, closed, and what ``require_brief_frame_totals`` reads.
BRIEF_DESIGNS: tuple[MonsterDesign, ...] = (
    _sourced("Lamashtu", -1, "Mesopotamian incantations"),
    _sourced("Lilith", -1, "Mesopotamian, then Jewish material"),
    _sourced("Empousa", -1, "Greek popular material"),
    _sourced("the gallû", -2, "Descent of Inanna to the Underworld"),
    _sourced("Ammit", -2, "Book of the Dead, spell 125"),
    _sourced("the Keres", -2, "Hesiod, Theogony"),
    _sourced("the Sebitti", -2, "Erra and Ishum"),
    _sourced("Humbaba", -2, "Epic of Gilgamesh"),
    _sourced("Mot", -2, "the Ugaritic Baal cycle"),
    _sourced("Apophis", -4, "Egyptian religion"),
    _sourced("Anzû", -4, "Mesopotamian"),
    _sourced("Asag", -4, "Lugal-e"),
    _sourced("Typhon", -4, "Hesiod, Theogony"),
    _sourced("Echidna", -4, "Hesiod, Theogony"),
    _sourced("the Gigantes", -4, "Greek material"),
    _sourced("Aži Dahāka", -4, "Zoroastrian material"),
    _sourced(
        "the Watchers and the Nephilim",
        -5,
        "1 Enoch 6-16",
        ("the Watchers", "the Nephilim"),
    ),
    _sourced("Asmodeus", -5, "Tobit"),
    _sourced(
        "Angra Mainyu and the daevas",
        -5,
        "Zoroastrian material",
        ("Angra Mainyu", "the daevas"),
    ),
    MonsterDesign(
        name="the Avatar",
        depth=-6,
        entity_names=("the Avatar",),
        source=INVENTED_SOURCE,
        attestation=INVENTED,
        nominal_cell_px=160,
        frames=FRAMES_WITH_CAST,
        on_screen_low=1,
        on_screen_high=1,
    ),
    MonsterDesign(
        name="a direct servant",
        depth=-6,
        entity_names=("a direct servant",),
        source=INVENTED_SOURCE,
        attestation=INVENTED,
        nominal_cell_px=96,
        frames=FRAMES_WITH_CAST,
        on_screen_low=2,
        on_screen_high=3,
    ),
)

#: Every design any tier holds. A tier takes as many rows as its entities allow.
MONSTER_DESIGNS: tuple[MonsterDesign, ...] = BRIEF_DESIGNS

#: Every design name, in the order ``MONSTER_DESIGNS`` declares them.
DESIGN_NAMES: tuple[str, ...] = tuple(design.name for design in MONSTER_DESIGNS)


def design_named(name: str) -> MonsterDesign:
    """Return the design ``name`` names, out of ``MONSTER_DESIGNS``."""
    for design in MONSTER_DESIGNS:
        if design.name == name:
            return design
    refusal = f"no design is named {name!r}; {len(DESIGN_NAMES)} designs are declared"
    raise UnknownDesignError(refusal)


def designs_at_depth(depth: int) -> tuple[MonsterDesign, ...]:
    """Return every design the tier at ``depth`` holds, empty where it holds none."""
    monster_tier_at(depth)
    return tuple(design for design in MONSTER_DESIGNS if design.depth == depth)


def monster_tier_frames(depth: int) -> int:
    """Count frames the tier at ``depth`` costs, its ``entities`` by its frames each."""
    tier = monster_tier_at(depth)
    entities = tier.entities
    frames = tier.frames_per_entity
    if entities is None or frames is None:
        return 0
    return entities * frames


def roster_frames() -> int:
    """Add ``monster_tier_frames`` over every tier in ``MONSTER_TIER_TABLE``."""
    return sum(monster_tier_frames(tier.depth) for tier in MONSTER_TIER_TABLE)


def named_design_frames() -> int:
    """Add the ``frames`` of every row in ``BRIEF_DESIGNS``."""
    return sum(design.frames for design in BRIEF_DESIGNS)


def drawing_jobs() -> int:
    """Add the ``entities`` of every tier that declares one."""
    return sum(
        tier.entities
        for tier in MONSTER_TIER_TABLE
        if tier.entities is not None
    )


def unspecified_entities() -> int:
    """Count entities ``MONSTER_TIER_TABLE`` holds that no design names."""
    return drawing_jobs() - len(MONSTER_DESIGNS)


def attested_name_count() -> int:
    """Add the ``entity_names`` of every ``SOURCED`` row of ``BRIEF_DESIGNS``."""
    return sum(
        len(design.entity_names)
        for design in BRIEF_DESIGNS
        if design.attestation == SOURCED
    )


def invented_name_count() -> int:
    """Add the ``entity_names`` of every ``INVENTED`` row of ``BRIEF_DESIGNS``."""
    return sum(
        len(design.entity_names)
        for design in BRIEF_DESIGNS
        if design.attestation == INVENTED
    )


def absent_levels() -> tuple[MonsterTier, ...]:
    """Return every tier whose ``level`` is ``FIGURE_ABSENT``, the owed list."""
    return tuple(tier for tier in MONSTER_TIER_TABLE if tier.level is None)


def levels_owed() -> int:
    """Count ``absent_levels``, the levels the table still waits on."""
    return len(absent_levels())


def tiers_without_a_nature() -> tuple[MonsterTier, ...]:
    """Return every tier whose ``nature`` is ``TEXT_ABSENT``, naming a membership."""
    return tuple(tier for tier in MONSTER_TIER_TABLE if tier.nature == TEXT_ABSENT)


def _bare(name: str) -> str:
    """Lower ``name`` and drop a leading article, so ``the Watchers`` matches."""
    return name.strip().lower().removeprefix("the ")


def both_sided_families() -> tuple[str, ...]:
    """Return every ``ASCENDING_FAMILIES`` name a descending design's entity carries."""
    below = {
        _bare(name)
        for design in MONSTER_DESIGNS
        if design.depth < 0
        for name in design.entity_names
    }
    return tuple(family for family in ASCENDING_FAMILIES if _bare(family) in below)


def admission_refusal(source: str) -> str:
    """Return the ``REFUSED_SOURCE_MARKERS`` term ``source`` carries, else blank."""
    lowered = source.lower()
    for marker in REFUSED_SOURCE_MARKERS:
        if marker in lowered:
            return marker
    return TEXT_ABSENT


def require_admissible(depth: int, source: str) -> None:
    """Refuse a creature with no tier on the axis or with a refused ``source``."""
    monster_tier_at(depth)
    if not source.strip():
        refusal = f"a creature at depth {depth} needs {ADMISSION_CONDITIONS[1]}"
        raise InadmissibleCreatureError(refusal)
    marker = admission_refusal(source)
    if marker:
        refusal = f"{source!r} carries {marker!r}, which {REFUSED_SOURCES} exclude"
        raise InadmissibleCreatureError(refusal)


def embedded_quintessence_at_level(level: int) -> Decimal:
    """Read the Quintessence an entity at ``level`` embeds, from its own stat block.

    ``entity_stats.stat_block_at_level`` refuses a level outside the arc.
    """
    return quintessence_requirement((stat_block_at_level(level),))


def tier_embedded_quintessence(depth: int) -> Decimal:
    """Read the Quintessence one entity of the tier at ``depth`` embeds."""
    tier = monster_tier_at(depth)
    level = tier.level
    if level is None:
        refusal = (
            f"the tier at depth {depth} has no level, so no Quintessence "
            f"amount follows: {LEVEL_OWED_NOTE}"
        )
        raise LevelAbsentError(refusal)
    return embedded_quintessence_at_level(level)


def monster_tier_rows() -> list[dict]:
    """Return one row a tier in ``MONSTER_TIER_TABLE``, carrying its own absences."""
    return [tier.to_dict() for tier in MONSTER_TIER_TABLE]


def design_rows() -> list[dict]:
    """Return one row a design in ``MONSTER_DESIGNS``."""
    return [design.to_dict() for design in MONSTER_DESIGNS]


def require_every_depth() -> None:
    """Refuse a table missing a depth or declaring one twice."""
    expected = {
        sign * rank for rank in range(1, RANKS_PER_SIDE + 1) for sign in (-1, 1)
    }
    declared = [tier.depth for tier in MONSTER_TIER_TABLE]
    if sorted(declared) != sorted(expected):
        refusal = (
            f"the table must declare each of {sorted(expected)} once, "
            f"got {sorted(declared)}"
        )
        raise UnknownMonsterTierError(refusal)


def require_distinct_design_names() -> None:
    """Refuse two rows of ``MONSTER_DESIGNS`` sharing a name."""
    repeated = sorted({name for name in DESIGN_NAMES if DESIGN_NAMES.count(name) > 1})
    if repeated:
        refusal = f"these design names repeat: {repeated}"
        raise RepeatedDesignError(refusal)


def require_roster_fits_tier() -> None:
    """Refuse a tier holding more designs than its ``entities`` allows."""
    for tier in MONSTER_TIER_TABLE:
        held = len(designs_at_depth(tier.depth))
        allowed = tier.entities
        if allowed is None:
            if held:
                refusal = (
                    f"depth {tier.depth} counts no entities and holds "
                    f"{held} designs"
                )
                raise TierSpecError(refusal)
            continue
        if held > allowed:
            refusal = (
                f"depth {tier.depth} allows {allowed} entities and holds "
                f"{held} designs"
            )
            raise TierSpecError(refusal)


def require_design_specs() -> None:
    """Refuse a design whose cell, frames, screen count or source leaves its tier."""
    for design in MONSTER_DESIGNS:
        tier = monster_tier_at(design.depth)
        if design.nominal_cell_px not in tier.nominal_cell_px:
            refusal = (
                f"{design.name} is authored at {design.nominal_cell_px} and its "
                f"tier declares {tier.nominal_cell_px}"
            )
            raise TierSpecError(refusal)
        if design.frames != tier.frames_per_entity:
            refusal = (
                f"{design.name} carries {design.frames} frames and its tier "
                f"declares {tier.frames_per_entity}"
            )
            raise TierSpecError(refusal)
        low = tier.on_screen_low or 0
        high = tier.on_screen_high or 0
        if design.on_screen_low < low or design.on_screen_high > high:
            refusal = (
                f"{design.name} shows {design.on_screen_low} to "
                f"{design.on_screen_high} and its tier declares {low} to {high}"
            )
            raise TierSpecError(refusal)
        if not design.entity_names:
            refusal = f"{design.name} names no entity"
            raise TierSpecError(refusal)
        if design.attestation == INVENTED and design.source != INVENTED_SOURCE:
            refusal = (
                f"{design.name} is invented and names {design.source!r} "
                f"rather than {INVENTED_SOURCE!r}"
            )
            raise TierSpecError(refusal)
        if design.attestation == SOURCED:
            require_admissible(design.depth, design.source)


def require_brief_frame_totals() -> None:
    """Refuse a count this table derives that the art brief does not publish."""
    if FRAMES_WITH_CAST != BRIEF_FRAMES_WITH_CAST:
        refusal = (
            f"STATE_FRAMES adds to {FRAMES_WITH_CAST}; the brief publishes "
            f"{BRIEF_FRAMES_WITH_CAST}"
        )
        raise BriefDisagreementError(refusal)
    if FRAMES_WITHOUT_CAST != BRIEF_FRAMES_WITHOUT_CAST:
        refusal = (
            f"dropping {CAST_STATE} leaves {FRAMES_WITHOUT_CAST}; the brief "
            f"publishes {BRIEF_FRAMES_WITHOUT_CAST}"
        )
        raise BriefDisagreementError(refusal)
    for depth, published in BRIEF_TIER_FRAMES.items():
        derived = monster_tier_frames(depth)
        if derived != published:
            refusal = (
                f"depth {depth} derives {derived} frames; the brief publishes "
                f"{published}"
            )
            raise BriefDisagreementError(refusal)
    if named_design_frames() != BRIEF_ROSTER_FRAMES:
        refusal = (
            f"BRIEF_DESIGNS adds to {named_design_frames()} frames; the brief "
            f"publishes {BRIEF_ROSTER_FRAMES}"
        )
        raise BriefDisagreementError(refusal)
    if len(BRIEF_DESIGNS) != BRIEF_DESIGN_COUNT:
        refusal = (
            f"{len(BRIEF_DESIGNS)} designs are transcribed; the brief publishes "
            f"{BRIEF_DESIGN_COUNT}"
        )
        raise BriefDisagreementError(refusal)
    if attested_name_count() != BRIEF_ATTESTED_NAMES:
        refusal = (
            f"{attested_name_count()} attested names are transcribed; the brief "
            f"publishes {BRIEF_ATTESTED_NAMES}"
        )
        raise BriefDisagreementError(refusal)
    total = attested_name_count() + invented_name_count()
    if total != BRIEF_TOTAL_NAMES:
        refusal = (
            f"{total} names are transcribed; the brief publishes "
            f"{BRIEF_TOTAL_NAMES}"
        )
        raise BriefDisagreementError(refusal)


def require_both_sided_families() -> None:
    """Refuse a measured both-sided family set outside ``FAMILIES_ON_BOTH_SIDES``."""
    measured = both_sided_families()
    if measured != FAMILIES_ON_BOTH_SIDES:
        refusal = (
            f"{list(measured)} appear on both sides of the plane; "
            f"{list(FAMILIES_ON_BOTH_SIDES)} are declared"
        )
        raise BriefDisagreementError(refusal)


def require_monster_table() -> None:
    """Drive every refusal above and log what the table holds."""
    require_every_depth()
    require_distinct_design_names()
    require_roster_fits_tier()
    require_design_specs()
    require_brief_frame_totals()
    require_both_sided_families()
    logger.info(
        "%d monster tiers, %d below and %d above, count %d drawing jobs and "
        "%d frames. %d designs are named, %d entities are not, %d levels are "
        "owed, and %s appear on both sides",
        len(MONSTER_TIER_TABLE),
        RANKS_PER_SIDE,
        RANKS_PER_SIDE,
        drawing_jobs(),
        roster_frames(),
        len(MONSTER_DESIGNS),
        unspecified_entities(),
        levels_owed(),
        list(FAMILIES_ON_BOTH_SIDES),
    )


require_monster_table()
