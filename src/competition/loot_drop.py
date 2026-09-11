"""The five loot tiers, the drop a qualifying market makes, and the store holding it.

``LOOT_TIERS`` carries the five weights and ``tier_bounds`` cuts them into whole
spans of ``draw_span``. ``band_tier_bounds`` cuts the same spans from a band of
the tiers a world leaves on its chart, spreading the weight of the tiers off the
chart across the tiers left in proportion, so ``band_weights_total`` reaches
``WEIGHT_TOTAL_PCT`` on every band and each surviving pair keeps the odds it held
on the full chart. ``drop_from_pool`` refuses a pool under
``MIN_ELIGIBLE_POOL`` and ``drop_for_market`` refuses a market
``MarketRotation.reward_reason`` does not answer ``IN_ROTATION`` for, and a
``yields`` mapping names the ``items.ITEM_TYPES`` entry each tier drops.
``augment_action`` applies a holding's bonuses to one action's Impetus cost and
effect, ``LootStore`` holds every ``LootDrop``, one file a chain, and
``LootStore.deliver`` puts one drop in an ``inventory.VesselStore`` once.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import TYPE_CHECKING

from numpy.random import Generator, default_rng

from ..core.io_utils import atomic_write_json
from .market_rotation import (
    IN_ROTATION,
    MIN_ELIGIBLE_POOL,
    EligiblePool,
    MarketRotation,
)
from .poa_modes import IMPETUS_FLOOR, IMPETUS_SPEED_CAP_FACTOR

if TYPE_CHECKING:
    from .inventory import StoreChange, VesselStore

CALX = "Calx"
CAUDA_PAVONIS = "Cauda Pavonis"
FLORES = "Flores"
ELIXIR = "Elixir"
MAGISTERIUM = "Magisterium"

#: The characters a short form may run to. Cauda Pavonis prints Pavonis.
SHORT_FORM_CHARS = 12

#: Every tier weight adds up to this. tier_bounds refuses a set that does not,
#: and band_tier_bounds refuses a band whose renormalised weights do not.
WEIGHT_TOTAL_PCT = Decimal(100)

#: A fraction times this is a percentage.
PERCENT_SCALE = Decimal(100)

#: The seed drop_rng draws under. One run reproduces another's rolls.
LOOT_DROP_SEED = 1155

DEFAULT_LOOT_PATH = Path.home() / ".acervator" / "loot_store.json"
LOOT_FILE_VERSION = 2

#: The units one drop puts in a store. One drop is one item.
UNITS_PER_DROP = 1

#: What no source sets, and what ``require_yields`` refuses a drop without.
TIER_YIELD_ABSENT = (
    "no source names the item type a loot tier yields, so drop_for_market takes a "
    "yields mapping from its caller and refuses a drop without one"
)

#: What a ``LootDrop`` does not name, so ``LootStore.deliver`` is given the store.
DROP_VESSEL_ABSENT = (
    "a LootDrop names a holder by wallet address and names no Vessel, and "
    "inventory.StoreBook keys one store a Vessel, so LootStore.deliver takes the "
    "receiving store from its caller"
)


class LootError(RuntimeError):
    """Base for every refusal this module raises."""


class LootTableError(LootError):
    """Raised when a chart's weights do not total ``WEIGHT_TOTAL_PCT``.

    ``tier_bounds`` raises it for the five, and ``band_tier_bounds`` for a band.
    """


class UnknownTierError(LootError):
    """Raised by ``tier_named`` and ``tier_for_roll`` for a tier outside the five."""


class LootDropRefusedError(LootError):
    """Raised by ``drop_from_pool`` and ``drop_for_market`` when no market qualifies."""


class DropItemError(LootError):
    """Raised for an item type or a quality grade the item tables do not declare."""


class TierYieldError(LootError):
    """Raised by ``require_yields`` for a tier carrying no item type."""


class DropDeliveryError(LootError):
    """Raised by ``LootStore.deliver`` for an unheld item or a second delivery."""


class LootStoreError(LootError):
    """Raised when a ``LootStore`` file cannot be replayed."""


@dataclass(frozen=True)
class LootTier:
    """One rarity tier, its ``weight_pct``, and the two bonuses an item carries.

    ``impetus_relief`` takes Impetus off one action's cost and
    ``effect_bonus_pct`` raises that action's effect.
    """

    name: str
    short_form: str
    weight_pct: Decimal
    impetus_relief: int
    effect_bonus_pct: Decimal


LOOT_TIERS: tuple[LootTier, ...] = (
    LootTier(CALX, "Calx", Decimal(60), 0, Decimal(2)),
    LootTier(CAUDA_PAVONIS, "Pavonis", Decimal(25), 0, Decimal(5)),
    LootTier(FLORES, "Flores", Decimal(11), 1, Decimal(10)),
    LootTier(ELIXIR, "Elixir", Decimal("3.5"), 1, Decimal(20)),
    LootTier(MAGISTERIUM, "Magisterium", Decimal("0.5"), 2, Decimal(50)),
)

#: Every tier name, in the order LOOT_TIERS declares them.
TIER_NAMES: tuple[str, ...] = tuple(tier.name for tier in LOOT_TIERS)


def weights_total() -> Decimal:
    """Add every ``weight_pct`` in ``LOOT_TIERS`` exactly."""
    total = Decimal(0)
    for tier in LOOT_TIERS:
        total += tier.weight_pct
    return total


def weight_places() -> int:
    """Count the most decimal places any ``weight_pct`` in ``LOOT_TIERS`` carries."""
    places = 0
    for tier in LOOT_TIERS:
        exponent = tier.weight_pct.as_tuple().exponent
        if isinstance(exponent, int) and exponent < 0:
            places = max(places, -exponent)
    return places


def weight_scale() -> int:
    """Return the power of ten making every ``weight_pct`` a whole number."""
    return int(10 ** weight_places())


def draw_span() -> int:
    """Return the whole numbers a roll is drawn from, ``WEIGHT_TOTAL_PCT`` scaled."""
    return int(WEIGHT_TOTAL_PCT * weight_scale())


def tier_span(tier: LootTier) -> int:
    """Return the whole rolls of ``draw_span`` that ``tier`` owns."""
    return int(tier.weight_pct * weight_scale())


def require_whole_table() -> None:
    """Refuse ``LOOT_TIERS`` unless ``weights_total`` reaches ``WEIGHT_TOTAL_PCT``.

    Every ``short_form`` must also sit inside ``SHORT_FORM_CHARS``.
    """
    total = weights_total()
    if total != WEIGHT_TOTAL_PCT:
        refusal = (
            f"the {len(LOOT_TIERS)} loot weights total {total}, not "
            f"{WEIGHT_TOTAL_PCT}; no roll span can be cut from them"
        )
        raise LootTableError(refusal)
    for tier in LOOT_TIERS:
        if len(tier.short_form) > SHORT_FORM_CHARS:
            refusal = (
                f"the short form {tier.short_form!r} runs "
                f"{len(tier.short_form)} characters, over the "
                f"{SHORT_FORM_CHARS} a row holds"
            )
            raise LootTableError(refusal)


def tier_bounds() -> tuple[tuple[int, int, LootTier], ...]:
    """Cut ``LOOT_TIERS`` into half-open roll spans after ``require_whole_table``."""
    require_whole_table()
    bounds: list[tuple[int, int, LootTier]] = []
    lower = 0
    for tier in LOOT_TIERS:
        upper = lower + tier_span(tier)
        bounds.append((lower, upper, tier))
        lower = upper
    return tuple(bounds)


def tier_for_roll(roll: int) -> LootTier:
    """Return the tier whose span in ``tier_bounds`` holds ``roll``."""
    value = int(roll)
    for lower, upper, tier in tier_bounds():
        if lower <= value < upper:
            return tier
    refusal = (
        f"a roll of {value} sits outside the draw span of 0 to "
        f"{draw_span() - 1}; every roll lands on one of {', '.join(TIER_NAMES)}"
    )
    raise UnknownTierError(refusal)


# -- The band, which rolls only the tiers a world leaves on its chart ---------


def require_band(band: object) -> tuple[LootTier, ...]:
    """Return the ``LOOT_TIERS`` entries ``band`` names, in the declared order.

    A band is what ``world_tier.loot_band`` keeps on a world's chart, and
    ``require_whole_table`` governs this path too, so a hand-written table not
    totalling ``WEIGHT_TOTAL_PCT`` is refused before any band is read.
    """
    require_whole_table()
    if isinstance(band, str) or not isinstance(band, Sequence):
        refusal = (
            f"a band is a sequence of loot tier names, got "
            f"{type(band).__name__}; the five are {', '.join(TIER_NAMES)}"
        )
        raise UnknownTierError(refusal)
    named = [str(name) for name in band]
    if not named:
        refusal = (
            f"an empty band leaves no tier to roll; the five are "
            f"{', '.join(TIER_NAMES)}"
        )
        raise UnknownTierError(refusal)
    if len(set(named)) != len(named):
        refusal = f"the band {', '.join(named)} names a tier twice"
        raise UnknownTierError(refusal)
    for name in named:
        tier_named(name)
    kept = set(named)
    return tuple(tier for tier in LOOT_TIERS if tier.name in kept)


def band_draw_span(band: object) -> int:
    """Return the whole numbers a roll on ``band`` is drawn from.

    Every tier keeps the ``tier_span`` it owns on the full chart, so the span
    shrinks by exactly what the tiers off the chart took.
    """
    tiers = require_band(band)
    span = 0
    for tier in tiers:
        span += tier_span(tier)
    if span <= 0:
        refusal = (
            f"the band {', '.join(tier.name for tier in tiers)} owns none of the "
            f"{draw_span()} rolls a full chart holds, so no roll lands on it"
        )
        raise LootTableError(refusal)
    return span


def band_weight_pct(band: object) -> tuple[tuple[LootTier, Fraction], ...]:
    """Return every tier in ``band`` beside the percent it owns of the band.

    The weight of each tier off the chart is spread across the tiers left in
    proportion to what they already held, so every surviving pair keeps the odds
    it had on the full chart and a ``Fraction`` carries the share exactly.
    """
    tiers = require_band(band)
    share = Fraction(WEIGHT_TOTAL_PCT) / band_draw_span(band)
    return tuple((tier, tier_span(tier) * share) for tier in tiers)


def band_weights_total(band: object) -> Fraction:
    """Add the percent every tier in ``band`` owns, exactly."""
    total = Fraction(0)
    for _tier, weight in band_weight_pct(band):
        total += weight
    return total


def require_whole_band(band: object) -> None:
    """Refuse ``band`` unless ``band_weights_total`` reaches ``WEIGHT_TOTAL_PCT``."""
    total = band_weights_total(band)
    if total != WEIGHT_TOTAL_PCT:
        refusal = (
            f"the band's renormalised weights total {total}, not "
            f"{WEIGHT_TOTAL_PCT}; no roll span can be cut from them"
        )
        raise LootTableError(refusal)


def band_tier_bounds(band: object) -> tuple[tuple[int, int, LootTier], ...]:
    """Cut ``band`` into half-open roll spans after ``require_whole_band``."""
    require_whole_band(band)
    bounds: list[tuple[int, int, LootTier]] = []
    lower = 0
    for tier in require_band(band):
        upper = lower + tier_span(tier)
        bounds.append((lower, upper, tier))
        lower = upper
    return tuple(bounds)


def band_tier_for_roll(roll: int, band: object) -> LootTier:
    """Return the tier whose span in ``band_tier_bounds`` holds ``roll``."""
    value = int(roll)
    for lower, upper, tier in band_tier_bounds(band):
        if lower <= value < upper:
            return tier
    names = ", ".join(tier.name for tier in require_band(band))
    refusal = (
        f"a roll of {value} sits outside the band's draw span of 0 to "
        f"{band_draw_span(band) - 1}; every roll lands on one of {names}"
    )
    raise UnknownTierError(refusal)


def tier_named(name: str) -> LootTier:
    """Return the entry in ``LOOT_TIERS`` whose ``name`` matches, raising for others."""
    for tier in LOOT_TIERS:
        if tier.name == name:
            return tier
    refusal = f"{name!r} is not a loot tier; the five are {', '.join(TIER_NAMES)}"
    raise UnknownTierError(refusal)


def bonus_text(tier: LootTier) -> str:
    """Print ``tier``'s ``effect_bonus_pct``, plus ``impetus_relief`` when it is set.

    A tier relieving no Impetus prints the effect alone.
    """
    effect = f"effect +{tier.effect_bonus_pct}%"
    if tier.impetus_relief == 0:
        return effect
    return f"Impetus -{tier.impetus_relief}, {effect}"


# -- The bonuses, which augment an action and never a trading figure ----------


@dataclass(frozen=True)
class AugmentedAction:
    """One action's Impetus cost and effect after a holding's bonuses.

    ``base_cost`` is the cost before any item and ``cost`` never falls below
    ``IMPETUS_FLOOR``.
    """

    base_cost: int
    cost: int
    relief: int
    effect_multiplier: Decimal


def held_relief(held: tuple[LootTier, ...]) -> int:
    """Add the Impetus every tier in ``held`` takes off one action's cost."""
    return sum(tier.impetus_relief for tier in held)


def held_effect_multiplier(held: tuple[LootTier, ...]) -> Decimal:
    """Add every ``effect_bonus_pct`` in ``held``, capped at the Impetus factor."""
    added = Decimal(0)
    for tier in held:
        added += tier.effect_bonus_pct
    multiplier = Decimal(1) + added / PERCENT_SCALE
    return min(multiplier, Decimal(IMPETUS_SPEED_CAP_FACTOR))


def augment_action(cost: int, held: tuple[LootTier, ...]) -> AugmentedAction:
    """Apply ``held``'s bonuses to one action costing ``cost`` Impetus.

    ``cost`` floors at ``IMPETUS_FLOOR`` and ``effect_multiplier`` caps at
    ``IMPETUS_SPEED_CAP_FACTOR``.
    """
    base = int(cost)
    if base < IMPETUS_FLOOR:
        refusal = f"an action costing {base} Impetus is below {IMPETUS_FLOOR}"
        raise LootError(refusal)
    relief = held_relief(held)
    return AugmentedAction(
        base_cost=base,
        cost=max(IMPETUS_FLOOR, base - relief),
        relief=relief,
        effect_multiplier=held_effect_multiplier(held),
    )


# -- What a tier yields, which the item table declares and no figure maps -----


def declared_item_types() -> tuple[str, ...]:
    """Every name ``items.ITEM_TYPE_NAMES`` declares, imported inside this function."""
    # materials imports this module for TIER_NAMES, so items is read at call time.
    from .items import ITEM_TYPE_NAMES

    return ITEM_TYPE_NAMES


def drop_storage_class(item_type: str, quality: str) -> str:
    """Return the class ``items.ITEM_TYPES`` stores ``item_type`` under."""
    # A drop's storage class comes from the item type and never from the drop.
    from .items import UnknownItemTypeError, item_type_named
    from .materials import UnknownQualityError, quality_index

    try:
        quality_index(quality)
        return item_type_named(item_type).storage_class
    except (UnknownItemTypeError, UnknownQualityError) as exc:
        raise DropItemError(str(exc)) from exc


def require_yields(yields: Mapping[str, str] | None) -> dict[str, str]:
    """Return ``yields`` once every ``TIER_NAMES`` entry maps to a declared type."""
    if yields is None:
        raise TierYieldError(TIER_YIELD_ABSENT)
    extra = tuple(sorted(set(yields) - set(TIER_NAMES)))
    if extra:
        refusal = (
            f"{', '.join(extra)} names no loot tier; the five are "
            f"{', '.join(TIER_NAMES)}"
        )
        raise UnknownTierError(refusal)
    declared = declared_item_types()
    mapped: dict[str, str] = {}
    for name in TIER_NAMES:
        item_type = yields.get(name)
        if item_type is None:
            refusal = (
                f"{name} carries no item type, so a roll landing on it would name "
                f"no thing; {TIER_YIELD_ABSENT}"
            )
            raise TierYieldError(refusal)
        if item_type not in declared:
            refusal = (
                f"{name} yields {item_type!r}, which is not a PoA item type; "
                f"the table carries {', '.join(declared)}"
            )
            raise DropItemError(refusal)
        mapped[name] = item_type
    return mapped


def item_type_for_tier(tier: LootTier, yields: Mapping[str, str] | None) -> str:
    """Return the item type ``yields`` gives ``tier``, after ``require_yields``."""
    return require_yields(yields)[tier.name]


# -- The drop ----------------------------------------------------------------


def drop_rng(seed: int = LOOT_DROP_SEED) -> Generator:
    """Seed a numpy generator with ``seed``, which ``drop_for_market`` rolls from."""
    return default_rng(seed)


@dataclass(frozen=True)
class DropRequest:
    """One participant asking one market for a drop, at one point on the clock.

    ``at_epoch`` of None takes the drop's time from ``time.time``.
    """

    exchange_id: str
    symbol: str
    season: int
    holder: str
    at_epoch: float | None = None


def request_from_pool(
    pool: EligiblePool,
    symbol: str,
    holder: str,
    at_epoch: float | None = None,
) -> DropRequest:
    """Build a ``DropRequest`` for ``symbol`` from ``pool``'s exchange and season."""
    return DropRequest(pool.exchange_id, symbol, pool.season, holder, at_epoch)


@dataclass(frozen=True)
class LootDrop:
    """One item a qualifying market dropped: its tier, its ``item_type``, its holder.

    ``quality`` is this drop's own ``tier_name`` and ``storage_class`` is read off
    ``items.ITEM_TYPES``.
    """

    item_id: str
    tier_name: str
    short_form: str
    item_type: str
    exchange_id: str
    symbol: str
    season: int
    roll: int
    holder: str
    dropped_at: float

    def __post_init__(self) -> None:
        """Refuse an ``item_type`` or a ``quality`` the item tables do not declare."""
        drop_storage_class(self.item_type, self.quality)

    @property
    def tier(self) -> LootTier:
        """Return the entry in ``LOOT_TIERS`` this drop's ``tier_name`` names."""
        return tier_named(self.tier_name)

    @property
    def quality(self) -> str:
        """This drop's quality grade, which is its own ``tier_name``."""
        return self.tier_name

    @property
    def storage_class(self) -> str:
        """The class ``items.ITEM_TYPES`` stores this drop's ``item_type`` under."""
        return drop_storage_class(self.item_type, self.quality)

    def to_dict(self) -> dict:
        """Return this drop as a JSON-safe dict, ``storage_class`` among the reads."""
        return {
            "item_id": self.item_id,
            "tier_name": self.tier_name,
            "short_form": self.short_form,
            "item_type": self.item_type,
            "quality": self.quality,
            "storage_class": self.storage_class,
            "exchange_id": self.exchange_id,
            "symbol": self.symbol,
            "season": self.season,
            "roll": self.roll,
            "holder": self.holder,
            "dropped_at": self.dropped_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> LootDrop:
        """Rebuild a ``LootDrop``, deriving ``quality`` and ``storage_class`` afresh."""
        return cls(
            item_id=str(d["item_id"]),
            tier_name=str(d["tier_name"]),
            short_form=str(d["short_form"]),
            item_type=str(d["item_type"]),
            exchange_id=str(d["exchange_id"]),
            symbol=str(d["symbol"]),
            season=int(d["season"]),
            roll=int(d["roll"]),
            holder=str(d["holder"]),
            dropped_at=float(d["dropped_at"]),
        )


def item_id_for(payload: dict) -> str:
    """Hash a drop's own contents with sha256, which names its ``item_id``."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def drop_for_market(
    rotation: MarketRotation,
    request: DropRequest,
    yields: Mapping[str, str] | None = None,
    rng: Generator | None = None,
    band: Sequence[str] | None = None,
) -> LootDrop:
    """Draw one ``LootDrop`` for ``request``, refusing a market outside the rotation.

    ``MarketRotation.reward_reason`` decides what qualifies and ``require_yields``
    decides what the rolled tier names; a ``band`` of None rolls ``TIER_NAMES``
    and any other band rolls only the tiers it keeps.
    """
    reason = rotation.reward_reason(request.exchange_id, request.symbol)
    if reason != IN_ROTATION:
        refusal = (
            f"{request.symbol} on {request.exchange_id} does not qualify: "
            f"{reason}; a drop comes from a market the open rotation window drew"
        )
        raise LootDropRefusedError(refusal)
    mapped = require_yields(yields)
    rolled = TIER_NAMES if band is None else band
    generator = drop_rng() if rng is None else rng
    roll = int(generator.integers(0, band_draw_span(rolled)))
    tier = band_tier_for_roll(roll, rolled)
    item_type = mapped[tier.name]
    dropped_at = time.time() if request.at_epoch is None else float(request.at_epoch)
    payload = {
        "tier_name": tier.name,
        "item_type": item_type,
        "exchange_id": request.exchange_id,
        "symbol": request.symbol,
        "season": int(request.season),
        "roll": roll,
        "holder": request.holder,
        "dropped_at": dropped_at,
    }
    return LootDrop(
        item_id=item_id_for(payload),
        tier_name=tier.name,
        short_form=tier.short_form,
        item_type=item_type,
        exchange_id=request.exchange_id,
        symbol=request.symbol,
        season=int(request.season),
        roll=roll,
        holder=request.holder,
        dropped_at=dropped_at,
    )


def drop_from_pool(
    rotation: MarketRotation,
    pool: EligiblePool,
    request: DropRequest,
    yields: Mapping[str, str] | None = None,
    rng: Generator | None = None,
    band: Sequence[str] | None = None,
) -> LootDrop:
    """Draw for ``request`` once ``pool.pool_size`` clears ``MIN_ELIGIBLE_POOL``.

    A pool under that floor raises ``LootDropRefusedError`` naming both numbers,
    and ``band`` reaches ``drop_for_market`` unread here.
    """
    if request.exchange_id != pool.exchange_id:
        refusal = (
            f"the request names {request.exchange_id} and the pool holds "
            f"{pool.exchange_id}; one pool answers for one exchange"
        )
        raise LootDropRefusedError(refusal)
    if pool.pool_size < MIN_ELIGIBLE_POOL:
        refusal = (
            f"{pool.exchange_id} holds {pool.pool_size} eligible markets, under "
            f"the floor of {MIN_ELIGIBLE_POOL}, so no window opens, no market "
            f"qualifies and no loot drops"
        )
        raise LootDropRefusedError(refusal)
    return drop_for_market(rotation, request, yields, rng, band)


# -- The store ---------------------------------------------------------------


class LootStore:
    """Every ``LootDrop`` one chain has made, held in one file beside the ledgers."""

    def __init__(self, store_path: str | Path | None = None) -> None:
        """Point the store at ``store_path`` or ``DEFAULT_LOOT_PATH``, reading none."""
        self._path: Path = Path(store_path) if store_path else DEFAULT_LOOT_PATH
        self._drops: list[LootDrop] = []
        self._delivered: dict[str, str] = {}

    @property
    def store_path(self) -> Path:
        """Return the file ``save`` writes and ``load`` reads."""
        return self._path

    def add(self, drop: LootDrop) -> LootDrop:
        """Take ``drop``, refusing a second item under the same ``item_id``."""
        for held in self._drops:
            if held.item_id == drop.item_id:
                refusal = (
                    f"item {drop.item_id[:16]} is already held; a drop names "
                    f"itself by the sha256 of its own contents"
                )
                raise LootStoreError(refusal)
        self._drops.append(drop)
        return drop

    def drop(self, item_id: str) -> LootDrop:
        """Return the drop ``item_id`` names, refusing an id this store lacks."""
        wanted = str(item_id)
        for held in self._drops:
            if held.item_id == wanted:
                return held
        refusal = (
            f"{wanted[:16]} names no item this store holds; it holds "
            f"{len(self._drops)}"
        )
        raise DropDeliveryError(refusal)

    def delivered_to(self, item_id: str) -> str | None:
        """Return the ``store_key`` that took ``item_id``, or None while none has."""
        return self._delivered.get(str(item_id))

    def undelivered(self, holder: str) -> list[LootDrop]:
        """``holder``'s drops no store has taken, in ``held`` order."""
        return [
            drop for drop in self.held(holder)
            if drop.item_id not in self._delivered
        ]

    def deliver(self, item_id: str, store: VesselStore) -> StoreChange:
        """Put the drop ``item_id`` names into ``store``, once and only on success.

        ``VesselStore.put_in`` decides whether a slot or a stack takes it, and a
        refusal leaves the drop undelivered.
        """
        from .inventory import VesselStore as VesselStoreClass

        if not isinstance(store, VesselStoreClass):
            refusal = (
                f"a VesselStore was expected, got {type(store).__name__}; "
                f"{DROP_VESSEL_ABSENT}"
            )
            raise DropDeliveryError(refusal)
        held = self.drop(item_id)
        taken = self.delivered_to(held.item_id)
        if taken is not None:
            refusal = (
                f"item {held.item_id[:16]} already went to {taken}; one drop "
                f"reaches one store"
            )
            raise DropDeliveryError(refusal)
        change = store.put_in(held.item_type, held.quality, UNITS_PER_DROP)
        self._delivered[held.item_id] = change.store_key
        return change

    def held(self, holder: str) -> list[LootDrop]:
        """Return ``holder``'s drops, rarest first and newest first inside one tier."""
        order = {tier.name: index for index, tier in enumerate(LOOT_TIERS)}
        mine = [drop for drop in self._drops if drop.holder == holder]
        return sorted(mine, key=lambda d: (-order[d.tier_name], -d.dropped_at))

    def held_tiers(self, holder: str) -> tuple[LootTier, ...]:
        """Return ``holder``'s items as the tiers ``augment_action`` reads."""
        return tuple(drop.tier for drop in self.held(holder))

    def save(self) -> Path:
        """Write every drop and every delivery through ``atomic_write_json``."""
        return atomic_write_json(
            self._path,
            {
                "version": LOOT_FILE_VERSION,
                "drops": [drop.to_dict() for drop in self._drops],
                "deliveries": dict(self._delivered),
            },
        )

    def load(self) -> LootStore:
        """Replay ``store_path``, raising on an unreadable file or a second replay."""
        if self._drops or self._delivered:
            already = f"{self._path} is already loaded; a second replay would double it"
            raise LootStoreError(already)
        if not self._path.exists():
            return self
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            unreadable = f"{self._path} could not be replayed: {exc}"
            raise LootStoreError(unreadable) from exc
        version = data.get("version") if isinstance(data, dict) else None
        if version != LOOT_FILE_VERSION:
            wrong = (
                f"{self._path} is version {version!r}, "
                f"this build reads version {LOOT_FILE_VERSION}"
            )
            raise LootStoreError(wrong)
        try:
            for record in data.get("drops", []):
                self._drops.append(LootDrop.from_dict(record))
        except (KeyError, TypeError, ValueError, LootError) as exc:
            unreadable = f"{self._path} could not be replayed: {exc}"
            raise LootStoreError(unreadable) from exc
        self._replay_deliveries(data.get("deliveries", {}))
        return self

    def _replay_deliveries(self, recorded: object) -> None:
        """Take ``recorded`` back, refusing a delivery naming an item no drop holds."""
        if not isinstance(recorded, dict):
            wrong = f"{self._path} carries deliveries as {type(recorded).__name__}"
            raise LootStoreError(wrong)
        ids = {drop.item_id for drop in self._drops}
        for item_id, store_key in recorded.items():
            if str(item_id) not in ids:
                wrong = (
                    f"{self._path} records {str(item_id)[:16]} delivered to "
                    f"{store_key} and holds no such drop"
                )
                raise LootStoreError(wrong)
            self._delivered[str(item_id)] = str(store_key)
