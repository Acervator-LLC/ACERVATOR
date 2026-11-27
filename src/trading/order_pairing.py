"""``pair_fill`` pairs a fill by the tranche event ids both records hold, else by ``motd_pairs`` order time."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import TYPE_CHECKING, Any, Optional

from src.trading.otd_math import fold_rebuy_price, opposing_sale_price
from src.trading.scrumming.execution import SettledFillFee, venue_fee_pct
from src.trading.scrumming.sizing import priced_usd, sale_proceeds_usd, sale_surplus_usd

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_MOTD_PCT = 5.0
"""The MOTD in percent ``motd_pairs`` clears where no bot's own distance is read."""


@dataclass(frozen=True)
class Fill:
    """One venue fill: the base, the stamp, the side, the price, the quantity and the fee in dollars."""

    asset: str
    when: datetime
    side: str
    price: float
    qty: float
    fee: float = 0.0


@dataclass(frozen=True)
class Order:
    """The fills of one base and side stamped in one second, at their quantity-weighted ``price``."""

    asset: str
    when: datetime
    side: str
    price: float
    qty: float
    fee: float


@dataclass(frozen=True)
class CyclePair:
    """A ``scrum`` and a ``fold`` order, the ``units`` both trade, and the ``level``."""

    scrum: Order
    fold: Order
    units: float
    extra_units: float
    level: float

    @property
    def direction(self) -> str:
        """``SCRUM_FOLD`` where ``scrum`` came first, else ``FOLD_SCRUM``."""
        return SCRUM_FOLD if self.scrum.when < self.fold.when else FOLD_SCRUM

    @property
    def opener(self) -> Order:
        """The earlier of ``scrum`` and ``fold``."""
        return self.scrum if self.direction == SCRUM_FOLD else self.fold

    @property
    def closer(self) -> Order:
        """The later of ``scrum`` and ``fold``."""
        return self.fold if self.direction == SCRUM_FOLD else self.scrum


def venue_orders(fills: Sequence[Fill]) -> list[Order]:
    """Return ``fills`` merged into one ``Order`` per base, side and stamp, oldest first."""
    merged: dict[tuple[str, str, datetime], list[Fill]] = {}
    for fill in sorted(fills, key=lambda one: one.when):
        merged.setdefault((fill.asset, fill.side, fill.when), []).append(fill)
    return [
        Order(
            asset=asset,
            when=when,
            side=side,
            price=math.fsum(f.price * f.qty for f in held)
            / math.fsum(f.qty for f in held),
            qty=math.fsum(f.qty for f in held),
            fee=math.fsum(f.fee for f in held),
        )
        for (asset, side, when), held in merged.items()
    ]


SCRUM_FOLD = "Scrum-Fold"
FOLD_SCRUM = "Fold-Scrum"
OPENING_SIDE = {SCRUM_FOLD: "sell", FOLD_SCRUM: "buy"}
NO_RUN_BESIDE = "no run of the other side next to its run"
NONE_CLEARS = "no order of the run next to it clears the MOTD"
LONGER_RUN = "its run is longer than the run next to it"
OTHERS_PAIRED = "each order of the run next to it that clears the MOTD paired another"
UNPAIRED_CAUSES = (NO_RUN_BESIDE, NONE_CLEARS, LONGER_RUN, OTHERS_PAIRED)


def motd_level(opener: Order, motd_pct: float) -> float:
    """Return a sell ``opener``'s ``fold_rebuy_price``, else ``opposing_sale_price``."""
    if opener.side == "sell":
        return fold_rebuy_price(opener.price, motd_pct)
    return opposing_sale_price(opener.price, motd_pct)


def clears_motd(opener: Order, closer: Order, motd_pct: float) -> bool:
    """Return True where ``closer`` reaches ``motd_level`` of ``opener``."""
    level = motd_level(opener, motd_pct)
    if opener.side == "sell":
        return closer.price <= level
    return closer.price >= level


def can_pair(opener: Order, closer: Order, motd_pct: float) -> bool:
    """Return True where ``opener`` comes first and ``closer`` ``clears_motd``."""
    return opener.when < closer.when and clears_motd(opener, closer, motd_pct)


def cycle_pair(opener: Order, closer: Order, motd_pct: float) -> CyclePair:
    """Return ``opener`` and ``closer`` as a ``CyclePair`` at their ``motd_level``."""
    scrum, fold = (opener, closer) if opener.side == "sell" else (closer, opener)
    units = min(scrum.qty, fold.qty)
    return CyclePair(scrum, fold, units, fold.qty - units, motd_level(opener, motd_pct))


def side_runs(orders: Sequence[Order]) -> list[list[Order]]:
    """Return ``orders`` in time order, split into runs of one side."""
    runs: list[list[Order]] = []
    for order in sorted(orders, key=lambda one: one.when):
        if runs and runs[-1][-1].side == order.side:
            runs[-1].append(order)
        else:
            runs.append([order])
    return runs


def run_pairs(
    earlier: Sequence[Order],
    later: Sequence[Order],
    motd_pct: float,
) -> list[CyclePair]:
    """Pair each later order with the latest open earlier order that ``can_pair``."""
    waiting = list(earlier)
    pairs: list[CyclePair] = []
    for closer in later:
        for index in range(len(waiting) - 1, -1, -1):
            if can_pair(waiting[index], closer, motd_pct):
                pairs.append(cycle_pair(waiting.pop(index), closer, motd_pct))
                break
    return pairs


def motd_pairs(orders: Sequence[Order], motd_pct: float) -> tuple[CyclePair, ...]:
    """Return ``run_pairs`` over each of ``side_runs`` and the run after it."""
    runs = side_runs(orders)
    return tuple(
        pair
        for earlier, later in pairwise(runs)
        for pair in run_pairs(earlier, later, motd_pct)
    )


def unpaired_cause(
    order: Order,
    run: Sequence[Order],
    beside: Sequence[Order],
    motd_pct: float,
    *,
    opens: bool,
) -> str:
    """Return why ``order`` of ``run`` paired no order of ``beside``."""
    if not beside:
        return NO_RUN_BESIDE
    if not any(
        can_pair(order, other, motd_pct) if opens else can_pair(other, order, motd_pct)
        for other in beside
    ):
        return NONE_CLEARS
    if len(run) > len(beside):
        return LONGER_RUN
    return OTHERS_PAIRED


def order_pair(
    order: Order, orders: Sequence[Order], motd_pct: float
) -> Optional[CyclePair]:
    """The ``motd_pairs`` pair of ``orders`` whose scrum or fold is ``order``, or None."""
    for pair in motd_pairs(orders, motd_pct):
        if order in (pair.scrum, pair.fold):
            return pair
    return None


def unpaired_causes(
    order: Order, orders: Sequence[Order], motd_pct: float
) -> tuple[str, str]:
    """``unpaired_cause`` of ``order`` against the run after its ``side_runs`` run, then the run before."""
    runs = side_runs(orders)
    at = next((index for index, run in enumerate(runs) if order in run), -1)
    if at < 0:
        return NO_RUN_BESIDE, NO_RUN_BESIDE
    after = runs[at + 1] if at + 1 < len(runs) else []
    before = runs[at - 1] if at > 0 else []
    return (
        unpaired_cause(order, runs[at], after, motd_pct, opens=True),
        unpaired_cause(order, runs[at], before, motd_pct, opens=False),
    )


PAIRED_BY_EVENT_IDS = "event ids"
PAIRED_BY_ORDER_TIME = "order time at the MOTD"
NOT_PAIRED = "no pair"
PAIRING_METHODS = (PAIRED_BY_EVENT_IDS, PAIRED_BY_ORDER_TIME, NOT_PAIRED)


@dataclass(frozen=True)
class EventIds:
    """The tranche event ids one platform record ``spent`` and ``opened``."""

    spent: tuple[str, ...]
    opened: tuple[str, ...]

    def meets(self, other: EventIds) -> bool:
        """True where this record opened an id ``other`` spent, or spent one ``other`` opened."""
        return bool(
            set(self.spent) & set(other.opened) or set(self.opened) & set(other.spent)
        )


@dataclass(frozen=True)
class FillPairing:
    """What ``pair_fill`` found: the ``method``, the event-id ``partners``, the order-time ``pair`` and the ``causes``."""

    method: str
    partners: tuple[Any, ...]
    pair: Optional[CyclePair]
    causes: tuple[str, str]


def pair_fill(
    own: EventIds,
    records: Sequence[tuple[Any, EventIds]],
    order: Order,
    orders: Sequence[Order],
    motd_pct: float,
) -> FillPairing:
    """Each of ``records`` whose ``EventIds`` meets ``own``, else ``order_pair``, else ``unpaired_causes``."""
    partners = tuple(record for record, ids in records if own.meets(ids))
    if partners:
        return FillPairing(PAIRED_BY_EVENT_IDS, partners, None, ("", ""))
    pair = order_pair(order, orders, motd_pct)
    if pair is not None:
        return FillPairing(PAIRED_BY_ORDER_TIME, (), pair, ("", ""))
    return FillPairing(NOT_PAIRED, (), None, unpaired_causes(order, orders, motd_pct))


@dataclass(frozen=True)
class Leg:
    """One order of a pair: its ``units``, its ``price`` and its ``fee_usd``."""

    units: float
    price: float
    fee_usd: float


@dataclass(frozen=True)
class PairFigures:
    """A pair's units sold and bought, its accumulation in units and its profit in dollars."""

    units_sold: float
    units_bought: float
    accumulated_units: float
    proceeds_usd: float
    buy_price: float
    buy_fee_pct: Optional[float]
    profit_usd: float


def pair_figures(sells: Sequence[Leg], buys: Sequence[Leg], quote: str) -> PairFigures:
    """``sale_surplus_usd`` of the ``sells`` proceeds bought back at the ``buys`` price and ``venue_fee_pct``."""
    sold = math.fsum(leg.units for leg in sells)
    bought = math.fsum(leg.units for leg in buys)
    proceeds = math.fsum(
        sale_proceeds_usd(priced_usd(leg.units, leg.price), leg.fee_usd)
        for leg in sells
    )
    paid = math.fsum(priced_usd(leg.units, leg.price) for leg in buys)
    price = paid / bought if bought > 0.0 else 0.0
    fees = math.fsum(leg.fee_usd for leg in buys)
    fee_pct = venue_fee_pct(
        SettledFillFee(bought, price, fees, quote, True), price, quote
    )
    return PairFigures(
        units_sold=sold,
        units_bought=bought,
        accumulated_units=bought - sold,
        proceeds_usd=proceeds,
        buy_price=price,
        buy_fee_pct=fee_pct,
        profit_usd=sale_surplus_usd(proceeds, sold, price, fee_pct),
    )
