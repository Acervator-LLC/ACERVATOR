"""The Paper Trader's money: a fake balance held in memory and nowhere else.

``FakeBalance`` carries the units, the cash, the cost basis and the open fold
tranches one paper bot holds. ``PaperLedger`` carries Paper Spendable, Paper
Locked, Paper Realized Profits and Paper Mature Profits; ``opening_ledger`` sets
both opening figures to ``fleet_target_usd``, and ``FakeBalance.mature_usd``
calls ``src.trading.smart_wire.mature_profit_usd``, the definition live reads.
Nothing here reads or writes ``bot_state.json`` or a live ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from ..trading.smart_wire import MATURE_GROWTH_PCT, mature_profit_usd

#: The paper budget as a multiple of the bot's dollar target.
BUDGET_MULTIPLE = 2.0

CURRENCY = "USD"

SPENDABLE_LABEL = "Paper Spendable"
LOCKED_LABEL = "Paper Locked"
REALIZED_LABEL = "Paper Realized Profits"
MATURE_LABEL = "Paper Mature Profits"

#: The four figures, in the order the tab reports them.
FIGURE_LABELS = (
    ("spendable_usd", SPENDABLE_LABEL),
    ("locked_usd", LOCKED_LABEL),
    ("realized_profit_usd", REALIZED_LABEL),
    ("mature_profit_usd", MATURE_LABEL),
)


def budget_usd(target_usd: float) -> float:
    """``target_usd`` times ``BUDGET_MULTIPLE``, one bot's whole paper budget."""
    try:
        target = float(target_usd)
    except (TypeError, ValueError):
        target = 0.0
    return max(0.0, target) * BUDGET_MULTIPLE


def fleet_target_usd(bots: Sequence[Any]) -> float:
    """The sum of every bot's ``target_usd``, the figure both openings take."""
    total = 0.0
    for bot in bots or ():
        try:
            total += max(0.0, float(getattr(bot, "target_usd", 0.0) or 0.0))
        except (TypeError, ValueError):
            continue
    return total


def fleet_budget_usd(bots: Sequence[Any]) -> float:
    """``fleet_target_usd`` times ``BUDGET_MULTIPLE``, the whole fleet budget."""
    return fleet_target_usd(bots) * BUDGET_MULTIPLE


@dataclass
class FakeBalance:
    """What one paper bot holds: units, cash, cost basis and open tranches."""

    units: float = 0.0
    cash_usd: float = 0.0
    budget_usd: float = 0.0
    cost_basis_usd: float = 0.0
    tranche_proceeds_usd: list[float] = field(default_factory=list)

    @property
    def tranches(self) -> int:
        """How many entries ``tranche_proceeds_usd`` holds, one per open tranche."""
        return len(self.tranche_proceeds_usd)

    def value_usd(self, price: float) -> float:
        """``units`` at ``price``, ignoring ``cash_usd``."""
        return self.units * float(price)

    def total_usd(self, price: float) -> float:
        """``value_usd`` at ``price`` plus ``cash_usd``."""
        return self.value_usd(price) + self.cash_usd

    def mature_usd(self, price: float) -> float:
        """``mature_profit_usd`` of ``cost_basis_usd`` against ``value_usd``."""
        return mature_profit_usd(self.cost_basis_usd, self.value_usd(price))

    def open_tranche(self, proceeds_usd: float) -> None:
        """Append one scrum's ``proceeds_usd`` to ``tranche_proceeds_usd``."""
        self.tranche_proceeds_usd.append(float(proceeds_usd))

    def close_tranche(self, spend_usd: float) -> float:
        """Pop the oldest tranche and return its proceeds less ``spend_usd``.

        An empty ``tranche_proceeds_usd`` closes nothing and returns 0.0.
        """
        if not self.tranche_proceeds_usd:
            return 0.0
        return self.tranche_proceeds_usd.pop(0) - float(spend_usd)

    def sell_basis(self, units_sold: float) -> float:
        """Remove ``units_sold``'s share of ``cost_basis_usd`` and return it."""
        held = float(self.units)
        if held <= 0.0 or float(units_sold) <= 0.0:
            return 0.0
        share = min(1.0, float(units_sold) / held)
        removed = self.cost_basis_usd * share
        self.cost_basis_usd -= removed
        return removed


def opening_balance(target_usd: float, price: float) -> FakeBalance:
    """A ``FakeBalance`` holding ``target_usd`` of units and ``target_usd`` of cash.

    One bot's share of ``opening_ledger``; a ``price`` at or below zero buys no
    units and leaves the whole ``budget_usd`` as ``cash_usd``.
    """
    whole = budget_usd(target_usd)
    held_usd = min(whole / BUDGET_MULTIPLE, whole)
    units = held_usd / float(price) if float(price) > 0.0 else 0.0
    spent = units * float(price)
    return FakeBalance(
        units=units,
        cash_usd=whole - spent,
        budget_usd=whole,
        cost_basis_usd=spent,
    )


@dataclass
class PaperLedger:
    """The fleet's four paper figures and the fleet total both openings took.

    ``realized_profit_usd`` accumulates as folds close the tranches scrums
    opened.
    """

    fleet_target_usd: float = 0.0
    opening_spendable_usd: float = 0.0
    opening_locked_usd: float = 0.0
    realized_profit_usd: float = 0.0

    def record_close(self, realized_usd: float) -> float:
        """Add ``realized_usd`` to ``realized_profit_usd`` and return the total."""
        self.realized_profit_usd += float(realized_usd)
        return self.realized_profit_usd

    def figures(
        self, balances: Optional[dict] = None, prices: Optional[dict] = None
    ) -> dict:
        """The four figures over ``balances``, priced by ``prices`` per bot id.

        ``spendable_usd`` sums ``cash_usd``, ``locked_usd`` sums ``value_usd``
        and ``mature_profit_usd`` sums only the positions past
        ``MATURE_GROWTH_PCT``.
        """
        held = balances or {}
        at = prices or {}
        spendable = 0.0
        locked = 0.0
        mature = 0.0
        mature_bots = 0
        for bot_id, balance in held.items():
            price = float(at.get(bot_id, 0.0) or 0.0)
            spendable += balance.cash_usd
            locked += balance.value_usd(price)
            one = balance.mature_usd(price)
            if one > 0.0:
                mature += one
                mature_bots += 1
        return {
            "fleet_target_usd": self.fleet_target_usd,
            "opening_spendable_usd": self.opening_spendable_usd,
            "opening_locked_usd": self.opening_locked_usd,
            "spendable_usd": spendable,
            "locked_usd": locked,
            "realized_profit_usd": self.realized_profit_usd,
            "mature_profit_usd": mature,
            "mature_positions": mature_bots,
            "mature_growth_pct": MATURE_GROWTH_PCT,
            "bots_open": len(held),
        }


def opening_ledger(bots: Sequence[Any]) -> PaperLedger:
    """A ``PaperLedger`` opening Paper Spendable and Paper Locked at the fleet total.

    Every press of Start rebuilds it from ``bots``; adding or removing a paper
    bot moves both opening figures on the next press, never inside a run.
    """
    total = fleet_target_usd(bots)
    return PaperLedger(
        fleet_target_usd=total,
        opening_spendable_usd=total,
        opening_locked_usd=total,
    )


__all__ = [
    "BUDGET_MULTIPLE",
    "CURRENCY",
    "FIGURE_LABELS",
    "LOCKED_LABEL",
    "MATURE_GROWTH_PCT",
    "MATURE_LABEL",
    "REALIZED_LABEL",
    "SPENDABLE_LABEL",
    "FakeBalance",
    "PaperLedger",
    "budget_usd",
    "fleet_budget_usd",
    "fleet_target_usd",
    "mature_profit_usd",
    "opening_balance",
    "opening_ledger",
]
