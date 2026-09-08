"""The Paper Trader's money: a fake balance held in memory and nowhere else.

``FakeBalance`` carries the units, the cash and the fold tranches one paper bot
holds, and ``opening_balance`` fills it from ``budget_usd``. Nothing here reads
or writes ``bot_state.json``, a venue balance or a live ledger.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The paper budget as a multiple of the bot's dollar target.
BUDGET_MULTIPLE = 2.0

CURRENCY = "USD"


def budget_usd(target_usd: float) -> float:
    """``target_usd`` times ``BUDGET_MULTIPLE``, the whole paper budget."""
    try:
        target = float(target_usd)
    except (TypeError, ValueError):
        target = 0.0
    return max(0.0, target) * BUDGET_MULTIPLE


@dataclass
class FakeBalance:
    """What one paper bot holds: units, cash and open fold tranches."""

    units: float = 0.0
    cash_usd: float = 0.0
    tranches: int = 0
    budget_usd: float = 0.0

    def value_usd(self, price: float) -> float:
        """``units`` at ``price``, ignoring ``cash_usd``."""
        return self.units * float(price)

    def total_usd(self, price: float) -> float:
        """``value_usd`` at ``price`` plus ``cash_usd``."""
        return self.value_usd(price) + self.cash_usd


def opening_balance(target_usd: float, price: float) -> FakeBalance:
    """A ``FakeBalance`` holding ``target_usd`` of units and the rest in cash.

    A ``price`` at or below zero buys no units and leaves the whole budget as
    ``cash_usd``.
    """
    whole = budget_usd(target_usd)
    held_usd = min(whole / BUDGET_MULTIPLE, whole)
    units = held_usd / float(price) if float(price) > 0.0 else 0.0
    return FakeBalance(
        units=units,
        cash_usd=whole - units * float(price),
        tranches=0,
        budget_usd=whole,
    )


__all__ = [
    "BUDGET_MULTIPLE",
    "CURRENCY",
    "FakeBalance",
    "budget_usd",
    "opening_balance",
]
