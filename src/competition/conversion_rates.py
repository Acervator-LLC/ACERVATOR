"""Every rate turning one PoA quantity into another, each carrying its provenance.

``CONVERSION_RATES`` is the table and ``rate_named``, ``working_rates``,
``absent_rates``, ``anchored_rates`` and ``rate_rows`` read it. One
``ConversionRate`` carries a ``provenance`` of ``MEASURED``, ``DECIDED`` or
``WORKING``, and a ``MEASURED`` entry names the ``source_module`` and
``source_symbol`` holding its figure. ``source_disagreements`` drives every such
symbol and runs once at import.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from decimal import Decimal

from .entity_stats import (
    FIRST_SPHERE,
    STAT_NAMES,
    quintessence_per_level,
    quintessence_requirement,
    stat_block,
)
from .loot_drop import TIER_NAMES
from .poa_modes import base_impetus
from .quintessence_ledger import QUINTESSENCE_PER_FEE_USD, amount_text
from .rpg_classes import ARC_LEVELS, FIRST_LEVEL
from .world_grid import SQUARE_STEPS, TREE_SPHERES

logger = logging.getLogger("acervator.conversion_rates")

MEASURED = "measured"
DECIDED = "decided"
WORKING = "working"

#: The three places a figure in this table may come from.
PROVENANCES: tuple[str, ...] = (MEASURED, DECIDED, WORKING)

#: The ``source_module`` of an entry no other module owns.
NO_SOURCE_MODULE = ""

#: The ``source_symbol`` of an entry no other module owns.
NO_SOURCE_SYMBOL = ""

#: An entry's ``rate`` while no figure sets it. Its ``note`` says what would.
RATE_ABSENT = None

#: The ``yields_unit`` of every rate answering in Quintessence.
QUINTESSENCE = "Quintessence"

#: One unit of iron ore at its lowest quality, the operator's own lower bound.
IRON_ORE_QUINTESSENCE_LOW_QUALITY = Decimal("0.00000001")

#: One unit of iron ore at its highest quality, the operator's own upper bound.
IRON_ORE_QUINTESSENCE_HIGH_QUALITY = Decimal("0.00000005")

#: A world's Quintessence equals its participants' holdings, one for one.
WORLD_BUDGET_PER_PARTICIPANT_QUINTESSENCE = Decimal(1)

#: The working rate of every stat whose effect ``STATS`` leaves unnamed.
STAT_EFFECT_PER_QUINTESSENCE = Decimal(1)

#: The working weight one unit of any material carries.
WEIGHT_PER_MATERIAL_UNIT = Decimal(1)

#: The working weight one Quintessence of strength may carry.
WEIGHT_PER_STRENGTH_QUINTESSENCE = Decimal(1)

#: The working Quintessence one destroyed item of any loot tier releases.
LOOT_RELEASED_QUINTESSENCE = IRON_ORE_QUINTESSENCE_HIGH_QUALITY

#: Creature tiers the art brief draws. No module names one.
MONSTER_TIERS = 6

#: The widths ``TempMonsterTier_0001`` and its siblings number their slots to.
TEMP_SLOT_DIGITS = 4


class ConversionRateError(RuntimeError):
    """Base for every refusal this module raises."""


class UnknownRateError(ConversionRateError):
    """Raised by ``rate_named`` for a name ``RATE_NAMES`` does not carry."""


class RateProvenanceError(ConversionRateError):
    """Raised for a ``provenance`` outside ``PROVENANCES`` or a missing source."""


class RateValueError(ConversionRateError):
    """Raised for a ``rate`` that is not a finite Decimal at or above zero."""


class RateSourceError(ConversionRateError):
    """Raised at import when ``source_disagreements`` finds a figure out of step."""


@dataclass(frozen=True)
class ConversionRate:
    """One rate: ``rate`` of ``yields_unit`` a ``per_unit``, and where it came from.

    ``rate`` of ``RATE_ABSENT`` means no figure sets it, and ``note`` says what
    would.
    """

    name: str
    per_unit: str
    yields_unit: str
    rate: Decimal | None
    provenance: str
    source_module: str
    source_symbol: str
    source_args: tuple[object, ...]
    note: str

    def __post_init__(self) -> None:
        """Refuse a blank ``name`` or ``note``, and a bad ``provenance`` or ``rate``."""
        if not self.name.strip():
            raise UnknownRateError(f"a rate needs a name, got {self.name!r}")
        if not self.note.strip():
            raise ConversionRateError(f"{self.name} needs a note on its end function")
        if self.provenance not in PROVENANCES:
            raise RateProvenanceError(
                f"{self.name} claims provenance {self.provenance!r}; "
                f"the three are {', '.join(PROVENANCES)}"
            )
        if self.provenance == MEASURED and not self.source_symbol:
            raise RateProvenanceError(
                f"{self.name} is {MEASURED} and names no source_symbol"
            )
        if self.rate is None:
            if self.source_symbol:
                raise RateProvenanceError(
                    f"{self.name} names source {self.source} and carries no figure"
                )
            return
        if not isinstance(self.rate, Decimal):
            raise RateValueError(
                f"{self.name} must hold a Decimal, not {type(self.rate).__name__}"
            )
        if not self.rate.is_finite() or self.rate < 0:
            raise RateValueError(f"{self.name} must be finite and not negative")

    @property
    def is_absent(self) -> bool:
        """True while ``rate`` is ``RATE_ABSENT`` and no figure sets it."""
        return self.rate is None

    @property
    def is_working(self) -> bool:
        """True while ``provenance`` is ``WORKING`` and the operator may replace it."""
        return self.provenance == WORKING

    @property
    def source(self) -> str:
        """``source_module`` and ``source_symbol`` joined, or an empty string."""
        if not self.source_symbol:
            return NO_SOURCE_SYMBOL
        return f"{self.source_module}.{self.source_symbol}"

    def to_dict(self) -> dict:
        """Serve this rate as a JSON-safe dict, the figure a plain string or None."""
        return {
            "name": self.name,
            "per_unit": self.per_unit,
            "yields_unit": self.yields_unit,
            "rate": None if self.rate is None else amount_text(self.rate),
            "provenance": self.provenance,
            "source": self.source,
            "note": self.note,
        }


#: A stat block holding one point in the first member of ``STAT_NAMES``.
ONE_POINT_BLOCK = stat_block(
    {name: (1 if name == STAT_NAMES[0] else 0) for name in STAT_NAMES}
)


def _temp_slot(prefix: str, ordinal: int) -> str:
    """``prefix`` and ``ordinal`` joined, the ordinal to ``TEMP_SLOT_DIGITS``."""
    return f"{prefix}_{ordinal:0{TEMP_SLOT_DIGITS}d}"


def _loot_release_rates() -> tuple[ConversionRate, ...]:
    """One working entry a ``TIER_NAMES`` name, at ``LOOT_RELEASED_QUINTESSENCE``."""
    return tuple(
        ConversionRate(
            name=f"loot_released_quintessence_{tier.lower().replace(' ', '_')}",
            per_unit=f"one destroyed {tier} item",
            yields_unit=QUINTESSENCE,
            rate=LOOT_RELEASED_QUINTESSENCE,
            provenance=WORKING,
            source_module=NO_SOURCE_MODULE,
            source_symbol=NO_SOURCE_SYMBOL,
            source_args=(),
            note=(
                "end function: the Quintessence a salvaged item of this tier "
                "releases to a wallet. Flat across all five tiers; no curve and "
                "no salvage loss is set"
            ),
        )
        for tier in TIER_NAMES
    )


def _monster_embedded_rates() -> tuple[ConversionRate, ...]:
    """One absent working entry each of the ``MONSTER_TIERS`` the art brief draws."""
    return tuple(
        ConversionRate(
            name=_temp_slot("TempMonsterTier", ordinal),
            per_unit=f"one creature of art-brief tier {ordinal}",
            yields_unit=QUINTESSENCE,
            rate=RATE_ABSENT,
            provenance=WORKING,
            source_module=NO_SOURCE_MODULE,
            source_symbol=NO_SOURCE_SYMBOL,
            source_args=(),
            note=(
                "end function: the Quintessence embedded in a creature of this "
                "tier, which falls out of entity_stats.quintessence_requirement "
                "once the tier's level is named. The level is the missing figure"
            ),
        )
        for ordinal in range(1, MONSTER_TIERS + 1)
    )


_ANCHORED_RATES: tuple[ConversionRate, ...] = (
    ConversionRate(
        name="stat_point_quintessence",
        per_unit="one stat point",
        yields_unit=QUINTESSENCE,
        rate=quintessence_requirement((ONE_POINT_BLOCK,)),
        provenance=MEASURED,
        source_module="entity_stats",
        source_symbol="quintessence_requirement",
        source_args=((ONE_POINT_BLOCK,),),
        note="the identity; a stat amount is Quintessence and nothing scales it",
    ),
    ConversionRate(
        name="stat_quintessence_per_level_at_sphere_1",
        per_unit="one level inside the first sphere",
        yields_unit=QUINTESSENCE,
        rate=quintessence_per_level(FIRST_SPHERE),
        provenance=MEASURED,
        source_module="entity_stats",
        source_symbol="quintessence_per_level",
        source_args=(FIRST_SPHERE,),
        note="one stat's rate in the lowest band; the band's own ordinal sets it",
    ),
    ConversionRate(
        name="stat_quintessence_per_level_at_sphere_10",
        per_unit="one level inside the tenth sphere",
        yields_unit=QUINTESSENCE,
        rate=quintessence_per_level(TREE_SPHERES),
        provenance=MEASURED,
        source_module="entity_stats",
        source_symbol="quintessence_per_level",
        source_args=(TREE_SPHERES,),
        note="one stat's rate in the highest band; one stat reaches 550 at level 100",
    ),
    ConversionRate(
        name="quintessence_per_certified_fee_usd",
        per_unit="one US dollar of certified venue fee",
        yields_unit=QUINTESSENCE,
        rate=QUINTESSENCE_PER_FEE_USD,
        provenance=MEASURED,
        source_module="quintessence_ledger",
        source_symbol="QUINTESSENCE_PER_FEE_USD",
        source_args=(),
        note="a ceiling; distil multiplies it by a trade grade of zero to one",
    ),
    ConversionRate(
        name="impetus_per_turn_at_level_1",
        per_unit="one turn at the first level",
        yields_unit="Impetus",
        rate=Decimal(base_impetus(FIRST_LEVEL)),
        provenance=MEASURED,
        source_module="poa_modes",
        source_symbol="base_impetus",
        source_args=(FIRST_LEVEL,),
        note="the pool one turn grants before any speed multiplier applies",
    ),
    ConversionRate(
        name="impetus_per_turn_at_level_100",
        per_unit="one turn at the last level of the arc",
        yields_unit="Impetus",
        rate=Decimal(base_impetus(ARC_LEVELS)),
        provenance=MEASURED,
        source_module="poa_modes",
        source_symbol="base_impetus",
        source_args=(ARC_LEVELS,),
        note="the pool one turn grants before any speed multiplier applies",
    ),
    ConversionRate(
        name="steps_per_square",
        per_unit="one world square",
        yields_unit="position steps",
        rate=Decimal(SQUARE_STEPS),
        provenance=MEASURED,
        source_module="world_grid",
        source_symbol="SQUARE_STEPS",
        source_args=(),
        note="a position is whole percent of a square across both axes",
    ),
    ConversionRate(
        name="minimum_units_per_quintessence",
        per_unit="one whole Quintessence",
        yields_unit="minimum units",
        rate=RATE_ABSENT,
        provenance=DECIDED,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "the operator set 100,000,000, the same resolution as BTC. This "
            "table imports the constant once quintessence_ledger declares it "
            "and keeps no copy of its own"
        ),
    ),
    ConversionRate(
        name="iron_ore_quintessence_low_quality",
        per_unit="one unit of iron ore at its lowest quality",
        yields_unit=QUINTESSENCE,
        rate=IRON_ORE_QUINTESSENCE_LOW_QUALITY,
        provenance=DECIDED,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note="the operator's own lower bound on embedded Quintessence in ore",
    ),
    ConversionRate(
        name="iron_ore_quintessence_high_quality",
        per_unit="one unit of iron ore at its highest quality",
        yields_unit=QUINTESSENCE,
        rate=IRON_ORE_QUINTESSENCE_HIGH_QUALITY,
        provenance=DECIDED,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note="the operator's own upper bound on embedded Quintessence in ore",
    ),
    ConversionRate(
        name="world_budget_per_participant_quintessence",
        per_unit="one Quintessence a participant of that world holds",
        yields_unit=QUINTESSENCE,
        rate=WORLD_BUDGET_PER_PARTICIPANT_QUINTESSENCE,
        provenance=DECIDED,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "the operator's rule: a world's Quintessence is the total of its "
            "participating players, spread over its Sephirot layers"
        ),
    ),
)

_WORKING_RATES: tuple[ConversionRate, ...] = (
    ConversionRate(
        name=_temp_slot("TempResource", 1) + "_low_quality",
        per_unit="one unit of a material other than iron ore, at lowest quality",
        yields_unit=QUINTESSENCE,
        rate=IRON_ORE_QUINTESSENCE_LOW_QUALITY,
        provenance=WORKING,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "end function: embedded Quintessence a non-ore material holds. Takes "
            "the iron ore band until the operator names this material's own scale"
        ),
    ),
    ConversionRate(
        name=_temp_slot("TempResource", 1) + "_high_quality",
        per_unit="one unit of a material other than iron ore, at highest quality",
        yields_unit=QUINTESSENCE,
        rate=IRON_ORE_QUINTESSENCE_HIGH_QUALITY,
        provenance=WORKING,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "end function: embedded Quintessence a non-ore material holds. Takes "
            "the iron ore band until the operator names this material's own scale"
        ),
    ),
    ConversionRate(
        name=_temp_slot("TempStat", 1),
        per_unit="one Quintessence of dexterity",
        yields_unit="effect magnitude",
        rate=STAT_EFFECT_PER_QUINTESSENCE,
        provenance=WORKING,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "end function: what dexterity buys. STATS leaves its effect unnamed; "
            "damage is the proposed reading and the operator rules on it"
        ),
    ),
    ConversionRate(
        name=_temp_slot("TempStat", 2),
        per_unit="one Quintessence of intelligence",
        yields_unit="effect magnitude",
        rate=STAT_EFFECT_PER_QUINTESSENCE,
        provenance=WORKING,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "end function: what intelligence buys. STATS leaves its effect "
            "unnamed; restoration is the proposed reading and the operator rules "
            "on it"
        ),
    ),
    ConversionRate(
        name=_temp_slot("TempStat", 3),
        per_unit="one Quintessence of wisdom",
        yields_unit="effect magnitude",
        rate=STAT_EFFECT_PER_QUINTESSENCE,
        provenance=WORKING,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "end function: what wisdom buys. STATS leaves its effect unnamed; "
            "support potency is the proposed reading and the operator rules on it"
        ),
    ),
    ConversionRate(
        name="item_cohesion_per_component_quintessence",
        per_unit="one Quintessence of one component's stats",
        yields_unit=QUINTESSENCE,
        rate=Decimal(1),
        provenance=WORKING,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "end function: the Quintessence holding an item together. One for one "
            "with entity_stats.quintessence_requirement until a component model "
            "names a coefficient"
        ),
    ),
    ConversionRate(
        name=_temp_slot("TempWeight", 1),
        per_unit="one unit of any material",
        yields_unit="weight units",
        rate=WEIGHT_PER_MATERIAL_UNIT,
        provenance=WORKING,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "end function: the weight strength's limit is measured against. "
            "Nothing weighs anything today and no figure sets a material's weight"
        ),
    ),
    ConversionRate(
        name="max_weight_per_strength_quintessence",
        per_unit="one Quintessence of strength",
        yields_unit="weight units",
        rate=WEIGHT_PER_STRENGTH_QUINTESSENCE,
        provenance=WORKING,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "end function: the maximum weight a Vessel may haul. STATS names this "
            "effect for strength and no figure sets the rate"
        ),
    ),
    ConversionRate(
        name="impetus_speed_per_constitution_quintessence",
        per_unit="one Quintessence of constitution",
        yields_unit="Impetus speed multiplier",
        rate=RATE_ABSENT,
        provenance=WORKING,
        source_module=NO_SOURCE_MODULE,
        source_symbol=NO_SOURCE_SYMBOL,
        source_args=(),
        note=(
            "end function: the carrying penalty constitution buys back. It enters "
            "through the speed_multiplier poa_modes.impetus_grant already takes. "
            "Any figure here moves the turn economy, so the operator sets it"
        ),
    ),
    *_loot_release_rates(),
    *_monster_embedded_rates(),
)

#: The whole table. A rate is added, replaced or promoted here and nowhere else.
CONVERSION_RATES: tuple[ConversionRate, ...] = (*_ANCHORED_RATES, *_WORKING_RATES)

#: Every name in ``CONVERSION_RATES``, in the order it declares them.
RATE_NAMES: tuple[str, ...] = tuple(entry.name for entry in CONVERSION_RATES)

if len(set(RATE_NAMES)) != len(RATE_NAMES):
    raise UnknownRateError(f"CONVERSION_RATES declares a name twice: {RATE_NAMES}")


def rate_named(name: str) -> ConversionRate:
    """The entry in ``CONVERSION_RATES`` whose ``name`` matches, refusing any other.

    The whole entry answers, so a reader always holds its ``provenance``.
    """
    for entry in CONVERSION_RATES:
        if entry.name == name:
            return entry
    raise UnknownRateError(
        f"{name!r} is not a PoA conversion rate; "
        f"the table carries {len(RATE_NAMES)} names"
    )


def rates_with_provenance(provenance: str) -> tuple[ConversionRate, ...]:
    """Every entry whose ``provenance`` matches, refusing a name outside it."""
    if provenance not in PROVENANCES:
        raise RateProvenanceError(
            f"{provenance!r} is not a provenance; "
            f"the three are {', '.join(PROVENANCES)}"
        )
    return tuple(entry for entry in CONVERSION_RATES if entry.provenance == provenance)


def working_rates() -> tuple[ConversionRate, ...]:
    """Every ``WORKING`` entry, which is the list of figures the operator still owes."""
    found = rates_with_provenance(WORKING)
    logger.info(
        "%s of %s conversion rates are working figures: %s",
        len(found),
        len(RATE_NAMES),
        ", ".join(entry.name for entry in found),
    )
    return found


def absent_rates() -> tuple[ConversionRate, ...]:
    """Every entry whose ``rate`` is ``RATE_ABSENT``, carrying no figure at all."""
    found = tuple(entry for entry in CONVERSION_RATES if entry.is_absent)
    logger.info(
        "%s of %s conversion rates carry no figure: %s",
        len(found),
        len(RATE_NAMES),
        ", ".join(entry.name for entry in found),
    )
    return found


def anchored_rates() -> tuple[ConversionRate, ...]:
    """Every entry naming a ``source_symbol``, which ``source_disagreements`` drives."""
    return tuple(entry for entry in CONVERSION_RATES if entry.source_symbol)


def _source_figure(entry: ConversionRate) -> Decimal:
    """Read ``entry``'s figure back out of the module its ``source`` names."""
    module = sys.modules[f"{__package__}.{entry.source_module}"]
    owner = getattr(module, entry.source_symbol)
    figure: object = owner(*entry.source_args) if callable(owner) else owner
    if isinstance(figure, Decimal):
        return figure
    if isinstance(figure, int) and not isinstance(figure, bool):
        return Decimal(figure)
    refusal = (
        f"{entry.source} answers {type(figure).__name__}, "
        f"and a rate reads only Decimal or int"
    )
    raise RateSourceError(refusal)


def source_disagreements() -> tuple[tuple[str, str, str, str], ...]:
    """Every anchored entry whose ``source`` answers a figure other than its ``rate``.

    One row is the entry name, its ``source``, its own figure and the source's.
    """
    out: list[tuple[str, str, str, str]] = []
    for entry in anchored_rates():
        owned = _source_figure(entry)
        if entry.rate != owned:
            published = amount_text(entry.rate) if entry.rate is not None else ""
            out.append((entry.name, entry.source, published, amount_text(owned)))
    logger.info(
        "drove %s anchored conversion rates against their own modules, %s disagreed",
        len(anchored_rates()),
        len(out),
    )
    return tuple(out)


def rate_rows() -> list[dict]:
    """One row an entry in ``CONVERSION_RATES``, as ``to_dict`` serves it."""
    return [entry.to_dict() for entry in CONVERSION_RATES]


_DISAGREEMENTS = source_disagreements()
if _DISAGREEMENTS:
    raise RateSourceError(
        f"a conversion rate is out of step with the module that owns it: "
        f"{_DISAGREEMENTS}"
    )
