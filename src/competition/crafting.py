"""A recipe, the craft it runs over several world turns, and the Quintessence it moves.

``Recipe`` names the ``ItemType`` it makes, the grade it makes it at, its list of
``Component`` entries, the ``loss_share`` it pays and the ``turns_required`` it
occupies. ``CraftRegister.begin_craft`` opens one for a ``Vessel`` and takes the
recipe's component units out of that Vessel's ``inventory.VesselStore``,
``abandon_craft`` puts those units back, and both make no ledger call.
``complete_craft`` puts the made item in the same store and then one
``QuintessenceLedger.embed_from_wallet`` call puts the item's cohesion in the
embedded bucket and the loss in the pleroma. ``COMPONENT_CONSUMPTION`` names when
the components leave, ``ABANDON_RETURNS_COMPONENTS`` names what brings them back
and ``CRAFT_DELIVERY`` names the order the two completion writes run in.
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
from .inventory import (
    InventoryError,
    StoreBook,
    StoreChange,
    VesselStore,
    vessel_key,
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

#: The units one craft puts in a store. One craft makes one item.
UNITS_PER_CRAFT = 1

#: Where a finished craft's item goes, and the order its two writes run in.
CRAFT_DELIVERY = (
    "complete_craft puts the item in the store StoreBook holds under "
    "inventory.vessel_key of the crafting Vessel, in the storage class the "
    "ItemType declares and at the Recipe's produced_quality, and it calls "
    "embed_from_wallet only once that store has taken it"
)

#: When a recipe's component units leave the crafting Vessel's store, and why then.
COMPONENT_CONSUMPTION = (
    "begin_craft takes every Component's units out of the store StoreBook holds "
    "under inventory.vessel_key of the crafting Vessel, at the Component's own "
    "quality, before the craft reaches open_crafts. A craft runs over "
    "turns_required world turns and a Vessel cannot carry material it is already "
    "working, so the units cannot wait for complete_craft: a store that still held "
    "them could hand them to another store or open a second craft on the same unit"
)

#: What a store that is short of a component leaves behind.
COMPONENT_REFUSAL_HOLDS = (
    "begin_craft reads units_held for every Component before it takes any, so a "
    "store short of one unit raises CraftComponentError with no unit moved, no "
    "craft in open_crafts and no ledger call made; a refusal part-way through the "
    "list puts back every unit already taken"
)

#: What ``abandon_craft`` puts back, and why it keeps every unit.
ABANDON_RETURNS_COMPONENTS = (
    "abandon_craft puts every Component's units back in the store begin_craft took "
    "them from, because the craft made no item and the ledger moved nothing, so a "
    "unit kept back would leave the world holding less material than it did with "
    "no bucket and no wallet recording the difference. No source sets a part-worked "
    "loss, so the whole list returns"
)

#: What an abandonment the store refuses leaves behind.
ABANDON_REFUSAL_HOLDS = (
    "abandon_craft puts the units back before it takes the craft out of "
    "open_crafts, so a store whose stack ceiling has since been reached leaves the "
    "craft open holding its components and the same call carries them back once "
    "the stack has room; a refusal part-way through the list takes back every unit "
    "already returned"
)

#: The one thing an open craft holds, now that ``begin_craft`` takes the components.
OPEN_CRAFT_HOLDS_COMPONENTS = (
    "an open craft holds the component units begin_craft took out of the store, so "
    "open_crafts is where those units are counted between begin_craft and either "
    "complete_craft or abandon_craft"
)

#: What no bucket records about the Quintessence a material unit carries.
MATERIAL_QUINTESSENCE_UNLEDGERED = (
    "Recipe.material_quintessence and material_surplus are read off the materials "
    "table, and no QuintessenceLedger movement credits the embedded bucket for a "
    "material unit a store holds, so consuming a component moves nothing in the "
    "ledger and the surplus is an amount nothing banks"
)

#: What a store refusal leaves behind, and why no item and no Quintessence is lost.
DELIVERY_REFUSAL_HOLDS = (
    "a store that has no free slot or has reached its stack ceiling raises before "
    "embed_from_wallet runs, so the craft stays in open_crafts, the wallet keeps "
    "quintessence_from_wallet and the store holds what it held; a ledger refusal "
    "after the store took the item takes that item back out before it raises"
)

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

#: What an open craft holds of the ledger. Nothing.
OPEN_CRAFT_HOLDS_NOTHING = (
    "begin_craft and abandon_craft make no ledger call, so an abandoned craft "
    "leaves its Quintessence in the wallet and conservation cannot break "
    "part-way through a craft; the component units are the one thing an open "
    "craft does hold, and OPEN_CRAFT_HOLDS_COMPONENTS says where they are counted"
)

#: What stops one craft completing twice.
SINGLE_COMPLETION = (
    "complete_craft records the craft_id and takes the craft out of open_crafts "
    "only once the store has taken the item and the ledger has moved, and it "
    "holds one lock across all three, so a second call raises, no refusal "
    "consumes a craft and no craft consumes a second set of materials"
)

#: What inventory holds of a craft, and what a Recipe's own units still stand on.
INVENTORY_ABSENT = (
    "inventory.VesselStore holds what a Vessel carries, begin_craft takes a "
    "Recipe's component units out of it and complete_craft puts the made item in, "
    "so the store's units held, its slots and its stack ceiling each refuse a "
    "craft alongside the wallet balance; foraging.ForageRegister.forage is the one "
    "module that puts a material unit in a store, and no world supply counts what "
    "it yields, so a craft consumes units nothing deducts from a total"
)

#: The two ends ``grid_faults`` drives. Neither sets a craft's loss.
LOSS_SHARE_ENDS: tuple[Decimal, ...] = (Decimal(0), Decimal(1))

#: What a craft takes part in, each note naming what builds it and what stays absent.
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
        "module repeats from one bound above it stays unexported. "
        "UNITS_PER_CRAFT, CRAFT_DELIVERY, DELIVERY_REFUSAL_HOLDS, "
        "CraftDeliveryError, COMPONENT_CONSUMPTION, COMPONENT_REFUSAL_HOLDS, "
        "ABANDON_RETURNS_COMPONENTS, ABANDON_REFUSAL_HOLDS, "
        "OPEN_CRAFT_HOLDS_COMPONENTS, MATERIAL_QUINTESSENCE_UNLEDGERED and "
        "CraftComponentError repeat no bound name and the entry file lists none of "
        "them, so each is reached by importing src.competition.crafting directly"
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


class CraftDeliveryError(CraftError):
    """Raised when the crafting Vessel's store has none or will not take the item."""


class CraftComponentError(CraftError):
    """Raised when the crafting Vessel's store cannot give or take back a component."""


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


def _as_store_book(value: object) -> StoreBook:
    """Return ``value`` as the ``StoreBook`` every finished craft delivers into."""
    if not isinstance(value, StoreBook):
        raise CraftDeliveryError(
            f"a StoreBook was expected, got {type(value).__name__}; "
            f"{CRAFT_DELIVERY}",
        )
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
            "material_quintessence_unledgered": MATERIAL_QUINTESSENCE_UNLEDGERED,
            "component_consumption": COMPONENT_CONSUMPTION,
            "loss_share": amount_text(self.loss_share),
            "loss_share_base": LOSS_SHARE_BASE,
            "turns_required": self.turns_required,
            "clock": CLOCK,
        }


@dataclass(frozen=True)
class Craft:
    """One ``Recipe`` opened by one ``Vessel``, before ``complete_craft`` pays it.

    ``begin_craft`` makes no ledger call and holds the component units it took out
    of the store, ``completes_turn`` is the turn it finishes on and ``store_key``
    is both where those units came from and where the made item goes.
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
    def store_key(self) -> str:
        """The key the item goes under, ``inventory.vessel_key`` of this Vessel."""
        return vessel_key(self.vessel)

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
            "store_key": self.store_key,
            "clock": CLOCK,
            "world_turn_seconds_absent": CRAFT_CLOCK_NOTE,
            "holds": OPEN_CRAFT_HOLDS_NOTHING,
            "holds_components": OPEN_CRAFT_HOLDS_COMPONENTS,
            "component_consumption": COMPONENT_CONSUMPTION,
            "abandonment": ABANDON_RETURNS_COMPONENTS,
            "delivery": CRAFT_DELIVERY,
        }


@dataclass(frozen=True)
class CraftResult:
    """One finished craft, carrying enough to rebuild what it consumed and moved.

    ``moved`` is what ``embed_from_wallet`` answered and ``is_accounted``
    compares it against this record's own three amounts. ``delivered`` is what
    the crafting Vessel's store answered and ``is_stored`` reads it back.
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
    delivered: StoreChange

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
    def store_key(self) -> str:
        """The store that took the item, read off the change it answered."""
        return self.delivered.store_key

    @property
    def is_stored(self) -> bool:
        """Whether the store took this craft's own item at its own grade."""
        return (
            self.delivered.is_put_in
            and self.delivered.name == self.item_name
            and self.delivered.quality == self.produced_quality
            and self.delivered.units == UNITS_PER_CRAFT
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
            "store_key": self.store_key,
            "delivered": self.delivered.to_dict(),
            "is_stored": self.is_stored,
            "turns_taken": self.turns_taken,
            "completed_turn": self.completed_turn,
            "clock": CLOCK,
            "movement": CRAFT_MOVEMENT,
            "component_consumption": COMPONENT_CONSUMPTION,
            "delivery": CRAFT_DELIVERY,
        }


def _component_text(parts: tuple[Component, ...]) -> str:
    """``parts`` as ``units material at quality``, joined, for a log line or refusal."""
    return ", ".join(
        f"{part.units} {part.material} at {part.quality}" for part in parts
    )


def _shortfall_text(short: tuple[tuple[str, str, int, int], ...]) -> str:
    """Each short component as its units, material, grade and the units held."""
    return ", ".join(
        f"{units} {material} at {quality}, holding {held}"
        for material, quality, units, held in short
    )


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
    """Takes a craft's components out of a store, holds it over its turns, delivers.

    The ledger and the ``StoreBook`` both arrive by construction, so a demo run is
    one ``CraftRegister`` over another chain's ledger and another book running the
    same ``begin_craft`` and ``complete_craft`` path.
    """

    def __init__(self, ledger: QuintessenceLedger, store_book: object) -> None:
        """Hold the ledger every craft debits, the book it delivers into, the open."""
        if not isinstance(ledger, QuintessenceLedger):
            raise CraftError(
                f"a QuintessenceLedger was expected, got {type(ledger).__name__}",
            )
        self._ledger = ledger
        self._store_book = _as_store_book(store_book)
        self._open: dict[str, Craft] = {}
        self._completed: set[str] = set()
        self._lock = threading.RLock()

    def _store_for(self, vessel: Vessel) -> VesselStore:
        """The store the book holds for ``vessel``, keyed by ``inventory.vessel_key``."""
        wanted = vessel_key(vessel)
        try:
            return self._store_book.store(wanted)
        except InventoryError as exc:
            raise CraftDeliveryError(
                f"{wanted} names no store in the book this register holds, so a "
                f"finished craft would have nowhere to put its item: {exc}",
            ) from exc

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
        """Open ``recipe`` for ``vessel`` and take its components out of that store.

        No ledger call is made here. ``COMPONENT_CONSUMPTION`` says why the units
        leave now and ``COMPONENT_REFUSAL_HOLDS`` says what a short store leaves.
        """
        if not isinstance(recipe, Recipe):
            raise CraftError(f"a Recipe was expected, got {type(recipe).__name__}")
        crafter = _as_vessel(vessel)
        opened = _as_turn_index(opened_turn, "opened_turn")
        store = self._store_for(crafter)
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
            self._take_components(craft, store)
            self._open[craft.craft_id] = craft
        logger.info(
            "craft %s opened on %s %s, finishing on %s; %s left %s, %s stays in %s "
            "until then and the item goes to %s",
            craft.craft_id,
            CLOCK,
            opened,
            craft.completes_turn,
            _component_text(recipe.components),
            store.store_key,
            amount_text(owed),
            crafter.owner,
            store.store_key,
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
        """Drop an open craft, put its components back, and debit nothing.

        ``ABANDON_RETURNS_COMPONENTS`` says why the whole list goes back and
        ``ABANDON_REFUSAL_HOLDS`` says what a store that refuses them leaves behind.
        """
        with self._lock:
            held = self._open.get(craft_id)
            if held is None:
                raise UnknownCraftError(self._missing_craft(craft_id))
            store = self._store_for(held.vessel)
            self._put_components_back(
                store,
                held.recipe.components,
                ABANDON_REFUSAL_HOLDS,
            )
            craft = self._take_craft(craft_id)
        logger.info(
            "craft %s abandoned (%s); %s stays in %s, %s went back to %s and no "
            "item is made",
            craft.craft_id,
            reason,
            amount_text(craft.recipe.quintessence_from_wallet),
            craft.crafter,
            _component_text(craft.recipe.components),
            store.store_key,
        )
        return craft

    def _component_shortfalls(
        self,
        recipe: Recipe,
        store: VesselStore,
    ) -> tuple[tuple[str, str, int, int], ...]:
        """Each component ``store`` is short of: material, grade, units, units held."""
        short: list[tuple[str, str, int, int]] = []
        for part in recipe.components:
            held = store.units_held(part.material, part.quality)
            if held < part.units:
                short.append((part.material, part.quality, part.units, held))
        return tuple(short)

    def _take_components(
        self,
        craft: Craft,
        store: VesselStore,
    ) -> tuple[StoreChange, ...]:
        """Take every component's units out of ``store``, moving none if one is short.

        Every shortfall is read before the first unit moves, so a store that cannot
        cover the whole material list gives out nothing.
        """
        recipe = craft.recipe
        short = self._component_shortfalls(recipe, store)
        if short:
            raise CraftComponentError(
                f"craft {craft.craft_id} consumes "
                f"{_component_text(recipe.components)} and {store.store_key} is "
                f"short of {_shortfall_text(short)}. {COMPONENT_REFUSAL_HOLDS}",
            )
        taken: list[StoreChange] = []
        for part in recipe.components:
            try:
                taken.append(store.take_out(part.material, part.quality, part.units))
            except InventoryError as exc:
                self._put_components_back(
                    store,
                    recipe.components[: len(taken)],
                    COMPONENT_REFUSAL_HOLDS,
                )
                raise CraftComponentError(
                    f"craft {craft.craft_id} could not take {part.units} "
                    f"{part.material} at {part.quality} out of {store.store_key}: "
                    f"{exc}. {COMPONENT_REFUSAL_HOLDS}",
                ) from exc
        logger.info(
            "craft %s took %s out of %s, which now carries weight %s",
            craft.craft_id,
            _component_text(recipe.components),
            store.store_key,
            amount_text(store.weight_carried),
        )
        return tuple(taken)

    def _put_components_back(
        self,
        store: VesselStore,
        parts: tuple[Component, ...],
        holds: str,
    ) -> tuple[StoreChange, ...]:
        """Put ``parts`` back in ``store``, taking back out every part it did take."""
        given: list[StoreChange] = []
        for part in parts:
            try:
                given.append(store.put_in(part.material, part.quality, part.units))
            except InventoryError as exc:
                for done in parts[: len(given)]:
                    store.take_out(done.material, done.quality, done.units)
                raise CraftComponentError(
                    f"{store.store_key} would not take back {part.units} "
                    f"{part.material} at {part.quality}: {exc}. {holds}",
                ) from exc
        return tuple(given)

    def complete_craft(self, craft_id: str, at_turn: object) -> CraftResult:
        """Make the item at ``completes_turn``, store it, and move the Quintessence.

        ``begin_craft`` already took the components, so nothing more is consumed
        here. The crafting Vessel's store takes the item first, then one
        ``embed_from_wallet`` call debits the wallet, embeds the item's cohesion
        and sends the loss to the pleroma. ``DELIVERY_REFUSAL_HOLDS`` names what
        either refusal leaves behind, and a craft left open by one keeps its
        components.
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
            recipe = craft.recipe
            store = self._store_for(craft.vessel)
            stored = self._store_item(craft, store)
            # embed_from_wallet is the one movement a craft makes; it mints nothing.
            try:
                moved = self._ledger.embed_from_wallet(
                    craft.crafter,
                    recipe.quintessence_from_wallet,
                    recipe.quintessence_embedded,
                )
            except Exception:
                store.take_out(
                    recipe.item_type_name,
                    recipe.produced_quality,
                    UNITS_PER_CRAFT,
                )
                logger.warning(
                    "craft %s stays open: %s took the %s back out because the "
                    "ledger moved nothing",
                    craft.craft_id,
                    store.store_key,
                    recipe.item_type_name,
                )
                raise
            del self._open[craft_id]
            self._completed.add(craft_id)
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
            delivered=stored,
        )
        logger.info(
            "craft %s made %s at %s: %s left %s, %s is embedded, %s joined the "
            "pleroma, %s unaccounted, and %s now holds %d",
            result.craft_id,
            result.item_name,
            result.produced_quality,
            amount_text(result.quintessence_from_wallet),
            result.crafter,
            amount_text(result.quintessence_embedded),
            amount_text(result.quintessence_lost),
            amount_text(result.unaccounted),
            result.store_key,
            result.delivered.units_held,
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

    def _store_item(self, craft: Craft, store: VesselStore) -> StoreChange:
        """Put one made item in ``store``, raising before any Quintessence moves.

        ``VesselStore.put_in`` reads the ``ItemType``'s own storage class, so gear
        reaches a counted slot and a consumable reaches a stack.
        """
        recipe = craft.recipe
        try:
            return store.put_in(
                recipe.item_type_name,
                recipe.produced_quality,
                UNITS_PER_CRAFT,
            )
        except InventoryError as exc:
            raise CraftDeliveryError(
                f"craft {craft.craft_id} made {recipe.item_type_name} at "
                f"{recipe.produced_quality} and {store.store_key} would not take "
                f"it: {exc}. {DELIVERY_REFUSAL_HOLDS}",
            ) from exc

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
