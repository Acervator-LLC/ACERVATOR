"""A recipe, the craft it runs over several world turns, and the Quintessence it moves.

``Recipe`` names the ``ItemType`` it makes, the grade it makes it at, its list of
``Component`` entries, the ``loss_share`` it pays and the ``turns_required`` it
occupies. ``CraftRegister.begin_craft`` opens one for a ``Vessel`` and debits
nothing, ``abandon_craft`` drops it and debits nothing, and ``complete_craft`` is
the only write path: one ``QuintessenceLedger.embed_from_wallet`` call puts the
item's cohesion in the embedded bucket and the loss in the pleroma.
``grid_faults`` drives every item type at every grade once at import.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .consecration import CLOCK, WORLD_TURN_SECONDS_ABSENT
from .items import (
    ITEM_TYPE_NAMES,
    Component,
    ItemType,
    item_type_named,
)
from .materials import QUALITY_GRADES, quality_index
from .quintessence_ledger import (
    QUINTESSENCE_MINIMUM_UNIT,
    QUINTESSENCE_SUPPLY_CAP,
    QuintessenceEmbed,
    QuintessenceLedger,
    amount_text,
    is_on_quintessence_grid,
    quantize_quintessence,
)
from .vessels import Vessel

logger = logging.getLogger("acervator.crafting")

#: A figure no source sets. Its own note says what would set it.
FIGURE_ABSENT = None

#: The fewest world turns one craft occupies.
MIN_CRAFT_TURNS = 1

#: The fewest components one ``Recipe`` may list.
MIN_COMPONENTS = 1

#: The one movement a craft makes, and the two buckets it reaches.
CRAFT_MOVEMENT = (
    "QuintessenceLedger.embed_from_wallet debits the wallet once, credits "
    "quintessence_embedded to the embedded bucket and quintessence_lost to the "
    "pleroma. A craft mints no Quintessence and destroys none"
)

#: Why ``release_to_pleroma`` is not part of a craft.
RELEASE_IS_SALVAGE = (
    "QuintessenceLedger.release_from_embedded moves the embedded bucket back to "
    "a wallet and to the pleroma, which is what destroying an item does. No "
    "craft calls it, and materials.salvage_loss_rule names the act it belongs to"
)

#: What names the loss a craft pays. Nothing does.
LOSS_SHARE_ABSENT = (
    "the operator set a salvage loss and set no crafting loss, so loss_share "
    "arrives with the Recipe and this module holds no table of it. Recipe "
    "refuses a loss_share of FIGURE_ABSENT and no craft opens without one"
)

#: What ``loss_share`` is a share of, and why it multiplies.
LOSS_SHARE_BASE = (
    "loss_share multiplies quintessence_embedded, so quintessence_lost stays a "
    "whole number of QUINTESSENCE_MINIMUM_UNIT. A share of the wallet amount "
    "would divide and leave a remainder no bucket can hold"
)

#: What a ``loss_share`` above one means, and that nothing refuses it.
LOSS_SHARE_UNBOUNDED = (
    "a loss_share above one loses more Quintessence than the item holds, which "
    "his much of it will be lost allows, so only the wallet balance bounds it"
)

#: What names how many turns a craft takes. Nothing does.
TURNS_ABSENT = (
    "turns_required arrives with the Recipe. The operator's words say crafting "
    "is multi-turn and sometimes lengthy and name no figure, and nothing here "
    "derives turns from an item's grade, its material count or its cohesion"
)

#: What names a world turn's length. Nothing does.
CRAFT_CLOCK_NOTE = WORLD_TURN_SECONDS_ABSENT

#: Why no recipe is declared in this module.
RECIPE_TABLE_ABSENT = (
    "every Recipe needs a loss_share and a turns_required, and no source names "
    "either, so this module declares no recipe table. One decided pair of "
    "figures is all a recipe for each name in ITEM_TYPE_NAMES would need"
)

#: Which of a Reincarnate's Vessels may craft. No field says.
PRIMARY_VESSEL_RULE_OWED = (
    "his words put crafting on secondary Vessels, and vessels.Vessel carries no "
    "field marking one primary, so begin_craft takes any Vessel and refuses "
    "none on that ground"
)

#: Why a craft lowers every Vessel one Reincarnate holds.
WALLET_BUDGET_SHARED = (
    "complete_craft debits the wallet vessels.Reincarnate.potential reads "
    "against every Vessel at once, so a craft lowers the fraction each of them "
    "runs at"
)

#: What an open craft holds. Nothing.
OPEN_CRAFT_HOLDS_NOTHING = (
    "begin_craft and abandon_craft make no ledger call, so an abandoned craft "
    "leaves its Quintessence in the wallet and conservation cannot break "
    "part-way through a craft"
)

#: What stops one craft completing twice.
SINGLE_COMPLETION = (
    "complete_craft takes the craft out of open_crafts before it moves anything "
    "and records its craft_id, so a second call raises and consumes no second "
    "set of materials"
)

#: What no module holds, so nothing proves a material existed before a craft.
INVENTORY_ABSENT = (
    "no module holds the materials a Vessel carries, so a Recipe names units "
    "nothing has counted and only the wallet balance refuses a craft"
)

#: The two ends ``grid_faults`` drives. Neither sets a craft's loss.
LOSS_SHARE_ENDS: tuple[Decimal, ...] = (Decimal(0), Decimal(1))

#: What a craft takes part in that no module builds.
ABSENT_MECHANISMS: tuple[str, ...] = (
    "a recipe table",
    "assignments",
    "notifications",
    "lifeskilling",
    "salvage",
    "inventory",
    "a crafting skill",
    "a surface",
    "a package export",
)

#: What each entry in ``ABSENT_MECHANISMS`` waits on.
ABSENT_MECHANISM_NOTES: dict[str, str] = {
    "a recipe table": RECIPE_TABLE_ABSENT,
    "assignments": (
        "nothing hands a Vessel a craft to carry, and vessels."
        "ABSENT_MECHANISM_NOTES names the same gap"
    ),
    "notifications": "nothing tells a player that complete_craft ran",
    "lifeskilling": "a craft is the only multi-turn Vessel act built here",
    "salvage": RELEASE_IS_SALVAGE,
    "inventory": INVENTORY_ABSENT,
    "a crafting skill": (
        "skill_ladder.SKILL_NAMES carries the Quintessence Transfer alone, so no "
        "skill level reads a craft and none changes its loss"
    ),
    "a surface": (
        "the gear subtab prints that nothing builds armour, weapons, accessories "
        "or consumables, and no panel calls begin_craft"
    ),
    "a package export": (
        "the competition package entry imports crafting and lists its names in "
        "__all__, so report_unbound_modules names no module at all and a name this "
        "module repeats from one bound above it stays unexported"
    ),
}

_AMOUNT_TYPES = (int, str, Decimal)


class CraftError(RuntimeError):
    """Base for every refusal this module raises."""


class RecipeError(CraftError):
    """Raised by ``Recipe`` for a bad material list or an absent figure."""


class CraftValueError(CraftError):
    """Raised for a Quintessence amount no bucket can hold."""


class CraftTurnError(CraftError):
    """Raised by ``complete_craft`` before a craft reaches ``completes_turn``."""


class UnknownCraftError(CraftError):
    """Raised by ``complete_craft`` and ``abandon_craft`` for a craft nothing holds."""


class HeldCraftError(CraftError):
    """Raised by ``begin_craft`` for a ``craft_id`` another open craft holds."""


def _as_share(value: object, name: str) -> Decimal:
    """Return ``value`` as a finite ``Decimal`` of zero or more, refusing ``float``."""
    if value is FIGURE_ABSENT:
        raise RecipeError(f"{name} is absent; {LOSS_SHARE_ABSENT}")
    if type(value) not in _AMOUNT_TYPES:
        raise RecipeError(
            f"{name} must be int, str or Decimal, not {type(value).__name__}; a "
            f"crafting figure decided by binary floating point is refused",
        )
    try:
        share = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise RecipeError(f"{name} must be a number, got {value!r}") from exc
    if not share.is_finite() or share < 0:
        raise RecipeError(f"{name} must be finite and zero or more, got {value!r}")
    return share


def _as_turns(value: object) -> int:
    """Return ``value`` as whole world turns of ``MIN_CRAFT_TURNS`` or more."""
    if value is FIGURE_ABSENT:
        raise RecipeError(f"turns_required is absent; {TURNS_ABSENT}")
    if type(value) is not int:
        raise RecipeError(
            f"turns_required must be a whole number of {CLOCK}s, "
            f"not {type(value).__name__}",
        )
    if value < MIN_CRAFT_TURNS:
        raise RecipeError(
            f"a craft occupies at least {MIN_CRAFT_TURNS} {CLOCK}, got {value!r}",
        )
    return value


def _as_turn_index(value: object, name: str) -> int:
    """Return ``value`` as a whole ``CLOCK`` index of zero or more."""
    if type(value) is not int:
        raise CraftTurnError(
            f"{name} must be a whole {CLOCK} index, not {type(value).__name__}",
        )
    if value < 0:
        raise CraftTurnError(f"{name} must be zero or more, got {value!r}")
    return value


def _as_craft_amount(value: Decimal, name: str) -> Decimal:
    """Return ``value`` as Quintessence on the minimum-unit grid, under the cap."""
    if not is_on_quintessence_grid(value):
        raise CraftValueError(
            f"{name} of {amount_text(value)} is not a whole number of "
            f"{amount_text(QUINTESSENCE_MINIMUM_UNIT)}, and no bucket holds it",
        )
    if value > QUINTESSENCE_SUPPLY_CAP:
        raise CraftValueError(
            f"{name} of {amount_text(value)} is above the "
            f"{amount_text(QUINTESSENCE_SUPPLY_CAP)} Quintessence that can exist",
        )
    return value


def _as_vessel(value: object) -> Vessel:
    """Return ``value`` as a ``Vessel``; every other type raises."""
    if not isinstance(value, Vessel):
        raise CraftError(f"a Vessel was expected, got {type(value).__name__}")
    return value


@dataclass(frozen=True)
class Recipe:
    """One recipe: the item it makes, its material list, its loss and its turns.

    ``quintessence_embedded`` is the produced item's cohesion and
    ``material_quintessence`` is the ceiling the list can cover.
    """

    item_type_name: str
    produced_quality: str
    components: tuple[Component, ...]
    loss_share: Decimal
    turns_required: int

    def __post_init__(self) -> None:
        """Coerce both figures and refuse a list that cannot hold the item together."""
        item_type_named(self.item_type_name)
        quality_index(self.produced_quality)
        listed = tuple(self.components)
        for part in listed:
            if not isinstance(part, Component):
                raise RecipeError(
                    f"a Component was expected in the material list of "
                    f"{self.item_type_name}, got {type(part).__name__}",
                )
        if len(listed) < MIN_COMPONENTS:
            raise RecipeError(
                f"{self.item_type_name} lists no material, so nothing is consumed "
                f"and no Quintessence could hold the item together",
            )
        named = tuple(part.material for part in listed)
        if len(set(named)) != len(named):
            raise RecipeError(
                f"{self.item_type_name} lists {named} and names one material "
                f"twice; raise that component's units instead",
            )
        object.__setattr__(self, "components", listed)
        object.__setattr__(self, "loss_share", _as_share(self.loss_share, "loss_share"))
        object.__setattr__(self, "turns_required", _as_turns(self.turns_required))
        held = self.quintessence_embedded
        _as_craft_amount(held, f"the cohesion of {self.item_type_name}")
        _as_craft_amount(self.quintessence_lost, "quintessence_lost")
        _as_craft_amount(self.quintessence_from_wallet, "quintessence_from_wallet")
        if held < QUINTESSENCE_MINIMUM_UNIT:
            raise RecipeError(
                f"{self.item_type_name} at {self.produced_quality} is held "
                f"together by {amount_text(held)}, under the "
                f"{amount_text(QUINTESSENCE_MINIMUM_UNIT)} minimum unit",
            )
        available = self.material_quintessence
        if held > available:
            raise RecipeError(
                f"{self.item_type_name} at {self.produced_quality} is held "
                f"together by {amount_text(held)} and its material list embeds "
                f"{amount_text(available)}; a craft cannot hold an item together "
                f"with Quintessence its materials never carried",
            )

    @property
    def item_type(self) -> ItemType:
        """The ``ITEM_TYPES`` entry ``item_type_name`` names."""
        return item_type_named(self.item_type_name)

    @property
    def material_quintessence(self) -> Decimal:
        """What every component embeds together, each at its own declared grade."""
        total = Decimal(0)
        for part in self.components:
            total += part.embedded
        return total

    @property
    def quintessence_embedded(self) -> Decimal:
        """The produced item's cohesion, which is what the item itself holds."""
        return self.item_type.cohesion_at(self.produced_quality)

    @property
    def quintessence_lost(self) -> Decimal:
        """``loss_share`` of ``quintessence_embedded``, rounded down onto the grid."""
        return quantize_quintessence(self.quintessence_embedded * self.loss_share)

    @property
    def quintessence_from_wallet(self) -> Decimal:
        """``quintessence_embedded`` plus ``quintessence_lost``, and nothing else."""
        return self.quintessence_embedded + self.quintessence_lost

    @property
    def material_surplus(self) -> Decimal:
        """What the material list embeds above the produced item's cohesion."""
        return self.material_quintessence - self.quintessence_embedded

    def to_dict(self) -> dict:
        """Return this recipe as a JSON-safe dict, every amount a plain string."""
        return {
            "item_type_name": self.item_type_name,
            "produced_quality": self.produced_quality,
            "components": [part.to_dict() for part in self.components],
            "material_quintessence": amount_text(self.material_quintessence),
            "quintessence_embedded": amount_text(self.quintessence_embedded),
            "quintessence_lost": amount_text(self.quintessence_lost),
            "quintessence_from_wallet": amount_text(self.quintessence_from_wallet),
            "material_surplus": amount_text(self.material_surplus),
            "loss_share": amount_text(self.loss_share),
            "loss_share_base": LOSS_SHARE_BASE,
            "turns_required": self.turns_required,
            "clock": CLOCK,
        }


@dataclass(frozen=True)
class Craft:
    """One ``Recipe`` opened by one ``Vessel``, before ``complete_craft`` pays it.

    ``begin_craft`` debits nothing and ``completes_turn`` is the turn it finishes
    on.
    """

    craft_id: str
    recipe: Recipe
    vessel: Vessel
    opened_turn: int

    @property
    def crafter(self) -> str:
        """The wallet address this craft debits, which is the Vessel's own owner."""
        return self.vessel.owner

    @property
    def completes_turn(self) -> int:
        """The ``CLOCK`` index this craft finishes on."""
        return self.opened_turn + self.recipe.turns_required - 1

    def turns_remaining(self, at_turn: object) -> int:
        """Return the turns still owed at ``at_turn``, and zero once it finished."""
        reached = _as_turn_index(at_turn, "at_turn")
        return max(0, self.completes_turn - reached)

    def to_dict(self) -> dict:
        """Return this open craft as a JSON-safe dict, one entry its recipe."""
        return {
            "craft_id": self.craft_id,
            "crafter": self.crafter,
            "vessel": self.vessel.to_dict(),
            "recipe": self.recipe.to_dict(),
            "opened_turn": self.opened_turn,
            "completes_turn": self.completes_turn,
            "clock": CLOCK,
            "world_turn_seconds_absent": CRAFT_CLOCK_NOTE,
            "holds": OPEN_CRAFT_HOLDS_NOTHING,
        }


@dataclass(frozen=True)
class CraftResult:
    """One finished craft, carrying enough to rebuild what it consumed and moved.

    ``moved`` is what ``embed_from_wallet`` answered, and ``is_accounted``
    compares it against this record's own three amounts.
    """

    craft_id: str
    recipe: Recipe
    crafter: str
    item_name: str
    produced_quality: str
    quintessence_from_wallet: Decimal
    quintessence_embedded: Decimal
    quintessence_lost: Decimal
    turns_taken: int
    completed_turn: int
    moved: QuintessenceEmbed

    @property
    def is_accounted(self) -> bool:
        """Whether this record and the ledger agree on all three amounts."""
        return (
            self.quintessence_from_wallet == self.moved.spent
            and self.quintessence_embedded == self.moved.embedded
            and self.quintessence_lost == self.moved.bled
            and self.moved.spent == self.moved.embedded + self.moved.bled
        )

    @property
    def unaccounted(self) -> Decimal:
        """What left the wallet and reached neither bucket, which is always zero."""
        return self.moved.spent - self.moved.embedded - self.moved.bled

    def to_dict(self) -> dict:
        """Return this finished craft as a dict, every amount a plain string."""
        return {
            "craft_id": self.craft_id,
            "crafter": self.crafter,
            "item_name": self.item_name,
            "produced_quality": self.produced_quality,
            "recipe": self.recipe.to_dict(),
            "quintessence_from_wallet": amount_text(self.quintessence_from_wallet),
            "quintessence_embedded": amount_text(self.quintessence_embedded),
            "quintessence_lost": amount_text(self.quintessence_lost),
            "ledger_spent": amount_text(self.moved.spent),
            "ledger_embedded": amount_text(self.moved.embedded),
            "ledger_pleroma": amount_text(self.moved.bled),
            "unaccounted": amount_text(self.unaccounted),
            "is_accounted": self.is_accounted,
            "turns_taken": self.turns_taken,
            "completed_turn": self.completed_turn,
            "clock": CLOCK,
            "movement": CRAFT_MOVEMENT,
        }


def craft_id_for(recipe: Recipe, vessel: Vessel, opened_turn: int) -> str:
    """Return the identifier one craft is held under, from its recipe and Vessel.

    The Vessel part is ``Vessel.record_key`` joined, the shape
    ``inventory.vessel_key`` renders, so two Vessels of one class at one level
    under one owner open two crafts under two ids.
    """
    return (
        f"{recipe.item_type_name}:{recipe.produced_quality}:"
        f"{':'.join(vessel.record_key)}:{opened_turn}"
    )


class CraftRegister:
    """Opens a craft, holds it over its turns, and completes it on one ledger call.

    The ledger arrives by construction, so a demo run is one ``CraftRegister``
    over another chain's ledger running the same ``complete_craft`` path.
    """

    def __init__(self, ledger: QuintessenceLedger) -> None:
        """Hold the ledger every craft debits, and the crafts standing open."""
        if not isinstance(ledger, QuintessenceLedger):
            raise CraftError(
                f"a QuintessenceLedger was expected, got {type(ledger).__name__}",
            )
        self._ledger = ledger
        self._open: dict[str, Craft] = {}
        self._completed: set[str] = set()
        self._lock = threading.RLock()

    def quote(self, recipe: Recipe) -> Decimal:
        """Return what ``recipe`` takes out of a wallet, from its own amounts."""
        if not isinstance(recipe, Recipe):
            raise CraftError(f"a Recipe was expected, got {type(recipe).__name__}")
        return recipe.quintessence_from_wallet

    def can_afford(self, recipe: Recipe, vessel: Vessel) -> bool:
        """Whether the Vessel owner's wallet covers what ``quote`` answers."""
        crafter = _as_vessel(vessel).owner
        return self._ledger.balance(crafter) >= self.quote(recipe)

    def begin_craft(
        self,
        recipe: Recipe,
        vessel: Vessel,
        opened_turn: object,
    ) -> Craft:
        """Open ``recipe`` for ``vessel``, refusing a wallet that cannot cover it.

        Nothing is debited here; ``complete_craft`` is the only write path.
        """
        if not isinstance(recipe, Recipe):
            raise CraftError(f"a Recipe was expected, got {type(recipe).__name__}")
        crafter = _as_vessel(vessel)
        opened = _as_turn_index(opened_turn, "opened_turn")
        owed = recipe.quintessence_from_wallet
        balance = self._ledger.balance(crafter.owner)
        if balance < owed:
            raise CraftError(
                f"{crafter.owner} holds {amount_text(balance)} and "
                f"{recipe.item_type_name} at {recipe.produced_quality} takes "
                f"{amount_text(owed)} out of a wallet; no craft opens on a wallet "
                f"that cannot cover it",
            )
        craft = Craft(
            craft_id=craft_id_for(recipe, crafter, opened),
            recipe=recipe,
            vessel=crafter,
            opened_turn=opened,
        )
        with self._lock:
            if craft.craft_id in self._open:
                raise HeldCraftError(
                    f"{craft.craft_id} is already open; one Vessel opens one craft "
                    f"of one recipe on one {CLOCK}",
                )
            self._open[craft.craft_id] = craft
        logger.info(
            "craft %s opened on %s %s, finishing on %s; %s stays in %s until then",
            craft.craft_id,
            CLOCK,
            opened,
            craft.completes_turn,
            amount_text(owed),
            crafter.owner,
        )
        return craft

    def open_crafts(self) -> list[Craft]:
        """Every craft that has neither completed nor been abandoned."""
        with self._lock:
            return [self._open[key] for key in sorted(self._open)]

    def completed_crafts(self) -> list[str]:
        """Every ``craft_id`` ``complete_craft`` has paid, so none pays twice."""
        with self._lock:
            return sorted(self._completed)

    def abandon_craft(self, craft_id: str, reason: str) -> Craft:
        """Drop an open craft, debiting nothing and producing no item."""
        craft = self._take_craft(craft_id)
        logger.info(
            "craft %s abandoned (%s); %s stays in %s and no item is made",
            craft.craft_id,
            reason,
            amount_text(craft.recipe.quintessence_from_wallet),
            craft.crafter,
        )
        return craft

    def complete_craft(self, craft_id: str, at_turn: object) -> CraftResult:
        """Make the item at ``completes_turn`` and move the Quintessence once.

        One ``embed_from_wallet`` call debits the wallet, embeds the item's
        cohesion and sends the loss to the pleroma.
        """
        reached = _as_turn_index(at_turn, "at_turn")
        with self._lock:
            craft = self._open.get(craft_id)
            if craft is None:
                raise UnknownCraftError(self._missing_craft(craft_id))
            if reached < craft.completes_turn:
                raise CraftTurnError(
                    f"craft {craft.craft_id} finishes on {CLOCK} "
                    f"{craft.completes_turn} and it is {CLOCK} {reached}; no part "
                    f"of an item exists",
                )
            del self._open[craft_id]
            self._completed.add(craft_id)
        recipe = craft.recipe
        # embed_from_wallet is the one movement a craft makes; it mints nothing.
        moved = self._ledger.embed_from_wallet(
            craft.crafter,
            recipe.quintessence_from_wallet,
            recipe.quintessence_embedded,
        )
        result = CraftResult(
            craft_id=craft.craft_id,
            recipe=recipe,
            crafter=craft.crafter,
            item_name=recipe.item_type_name,
            produced_quality=recipe.produced_quality,
            quintessence_from_wallet=recipe.quintessence_from_wallet,
            quintessence_embedded=recipe.quintessence_embedded,
            quintessence_lost=recipe.quintessence_lost,
            turns_taken=recipe.turns_required,
            completed_turn=reached,
            moved=moved,
        )
        logger.info(
            "craft %s made %s at %s: %s left %s, %s is embedded, %s joined the "
            "pleroma, %s unaccounted",
            result.craft_id,
            result.item_name,
            result.produced_quality,
            amount_text(result.quintessence_from_wallet),
            result.crafter,
            amount_text(result.quintessence_embedded),
            amount_text(result.quintessence_lost),
            amount_text(result.unaccounted),
        )
        if not result.is_accounted:
            raise CraftValueError(
                f"craft {result.craft_id} took "
                f"{amount_text(result.quintessence_from_wallet)} from a wallet and "
                f"the ledger moved {amount_text(moved.spent)} as "
                f"{amount_text(moved.embedded)} embedded and "
                f"{amount_text(moved.bled)} to the pleroma",
            )
        return result

    def _take_craft(self, craft_id: str) -> Craft:
        """Take an open craft out of ``open_crafts``, refusing one nothing holds."""
        with self._lock:
            craft = self._open.pop(craft_id, None)
        if craft is None:
            raise UnknownCraftError(self._missing_craft(craft_id))
        return craft

    def _missing_craft(self, craft_id: str) -> str:
        """Say whether ``craft_id`` already completed or was never opened."""
        if craft_id in self._completed:
            return f"{craft_id!r} has already completed; {SINGLE_COMPLETION}"
        return f"{craft_id!r} is not an open craft; {len(self._open)} stand open"


def _components_at(item: ItemType, quality: str) -> tuple[Component, ...]:
    """``item``'s own material list, every entry read at ``quality``."""
    return tuple(
        Component(part.material, part.units, quality) for part in item.components
    )


def recipe_for(
    item_type_name: str,
    produced_quality: str,
    loss_share: object,
    turns_required: object,
) -> Recipe:
    """Return a ``Recipe`` making ``item_type_name`` out of that type's own list.

    ``RECIPE_TABLE_ABSENT`` says why both figures arrive from the caller.
    """
    item = item_type_named(item_type_name)
    quality_index(produced_quality)
    return Recipe(
        item_type_name=item.name,
        produced_quality=produced_quality,
        components=_components_at(item, produced_quality),
        loss_share=_as_share(loss_share, "loss_share"),
        turns_required=_as_turns(turns_required),
    )


def recipe_rows(loss_share: object, turns_required: object) -> list[dict]:
    """One row an item type at each grade, at the ``loss_share`` the caller names."""
    return [
        recipe_for(name, quality, loss_share, turns_required).to_dict()
        for name in ITEM_TYPE_NAMES
        for quality in QUALITY_GRADES
    ]


def grid_faults() -> tuple[tuple[str, str, str, str, str], ...]:
    """Every item type, grade and loss end whose amounts break one of four rules.

    One row is the type, the grade, the loss end, the amount and the rule broken.
    """
    out: list[tuple[str, str, str, str, str]] = []
    unit = amount_text(QUINTESSENCE_MINIMUM_UNIT)
    for name in ITEM_TYPE_NAMES:
        for quality in QUALITY_GRADES:
            for share in LOSS_SHARE_ENDS:
                recipe = recipe_for(name, quality, share, MIN_CRAFT_TURNS)
                end = amount_text(share)
                held = recipe.quintessence_embedded
                lost = recipe.quintessence_lost
                taken = recipe.quintessence_from_wallet
                if held < QUINTESSENCE_MINIMUM_UNIT:
                    out.append((name, quality, end, amount_text(held), f"under {unit}"))
                for amount, label in ((held, "cohesion"), (lost, "loss")):
                    if not is_on_quintessence_grid(amount):
                        out.append(
                            (
                                name,
                                quality,
                                end,
                                amount_text(amount),
                                f"{label} is not a whole number of {unit}",
                            ),
                        )
                if taken != held + lost:
                    split = (
                        f"is not {amount_text(held)} embedded "
                        f"plus {amount_text(lost)} lost"
                    )
                    out.append((name, quality, end, amount_text(taken), split))
                available = recipe.material_quintessence
                if held > available:
                    over = f"is above the {amount_text(available)} its materials embed"
                    out.append((name, quality, end, amount_text(held), over))
    logger.info(
        "drove %s item types across %s quality grades at %s loss ends, "
        "%s amounts broke a rule",
        len(ITEM_TYPE_NAMES),
        len(QUALITY_GRADES),
        len(LOSS_SHARE_ENDS),
        len(out),
    )
    return tuple(out)


_FAULTS = grid_faults()
if _FAULTS:
    raise CraftValueError(
        f"a craft would move Quintessence no bucket holds: {_FAULTS}",
    )
