"""The Paper Trader's money: a fake balance held in memory and nowhere else.

``FakeBalance`` is the paper bot's position, forked from the Simulator's
``SimPosition``: the units and the ``main_lots`` they sit in, the cash its
scrums leave and its folds spend, the ``fold_tranches`` its scrums queue in
the dict shape ``_tick_execute_scrum`` builds, the target and the growth
cycle's figures, and the trade counters ``BotStats`` carries on a live bot.
``PaperLedger`` carries Paper Spendable, Paper Locked, Paper Realized Profits
and Paper Mature Profits; ``opening_ledger`` sets both opening figures to
``fleet_target_usd``, the unbounded budget's opening, and
``FakeBalance.mature_usd`` calls ``src.trading.smart_wire.mature_profit_usd``,
the definition live reads. Nothing here reads or writes ``bot_state.json`` or
a live ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from ..trading.scrumming.sizing import priced_usd
from ..trading.smart_wire import MATURE_GROWTH_PCT, mature_profit_usd

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


def fleet_target_usd(bots: Sequence[Any]) -> float:
    """The sum of every bot's ``target_usd``, the figure both openings take."""
    total = 0.0
    for bot in bots or ():
        try:
            total += max(0.0, float(getattr(bot, "target_usd", 0.0) or 0.0))
        except (TypeError, ValueError):
            continue
    return total


@dataclass
class FakeBalance:
    """What one paper bot holds as the run ticks: its units and the
    ``main_lots`` they sit in, the cash its scrums left and its folds spent,
    the fold tranches those scrums queued in the shape ``_tick_execute_scrum``
    builds them, the target its folds grow from ``anchor_target_usd``, the
    growth cycle's consumed cap, standing surplus and side, the growth
    ``grow_target`` has applied and the steps it recorded in ``target_path``,
    and the counters ``BotStats`` carries on a live bot."""

    units: float = 0.0
    cash_usd: float = 0.0
    fold_tranches: list = field(default_factory=list)
    opening_price: float = 0.0
    last_trade_price: float = 0.0
    cycle_cap_consumed_usd: float = 0.0
    main_lots: list = field(default_factory=list)
    target_usd: float = 0.0
    anchor_target_usd: float = 0.0
    standing_surplus_usd: float = 0.0
    growth_side: Optional[str] = None
    last_trade_side: str = ""
    total_trades: int = 0
    total_buys: int = 0
    total_sells: int = 0
    total_scrummed_usd: float = 0.0
    total_folded_usd: float = 0.0
    trade_volume: float = 0.0
    tranches_created: int = 0
    tranches_closed: int = 0
    scrum_sells: int = 0
    growth_applied_usd: float = 0.0
    target_path: list = field(default_factory=list)

    @property
    def tranches(self) -> int:
        """How many fold tranches are queued."""
        return len(self.fold_tranches)

    def value_usd(self, price: float) -> float:
        """``units`` at ``price``, ignoring cash held from an earlier scrum."""
        return priced_usd(self.units, float(price))

    def total_usd(self, price: float) -> float:
        """``value_usd`` at ``price`` plus ``cash_usd``."""
        return self.value_usd(price) + self.cash_usd

    def cost_basis_usd(self) -> float:
        """Each lot's units at its ``initial_buy_price``, summed: the cost basis
        ``ScrummingBot.tick`` reads ``unrealised_pnl`` against."""
        return sum(
            float(lot.get("units", 0) or 0)
            * float(lot.get("initial_buy_price", 0) or 0)
            for lot in self.main_lots
        )

    def unrealised_pnl_usd(self, price: float) -> float:
        """``value_usd`` at ``price`` less ``cost_basis_usd``."""
        return self.value_usd(price) - self.cost_basis_usd()

    def mature_usd(self, price: float) -> float:
        """``mature_profit_usd`` of ``cost_basis_usd`` against ``value_usd``."""
        return mature_profit_usd(self.cost_basis_usd(), self.value_usd(price))


@dataclass
class PaperLedger:
    """The fleet's four paper figures and the fleet total both openings took.

    ``realized_profit_usd`` accumulates the ``fold_surplus_usd`` of every fold
    that closes tranches scrums opened.
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
        """The four figures over ``balances`` priced by ``prices`` per bot id:
        ``spendable_usd`` is ``opening_spendable_usd`` with each open balance's
        ``anchor_target_usd`` share replaced by its ``cash_usd``,
        ``locked_usd`` is ``opening_locked_usd`` with each share replaced by
        its ``value_usd``, and ``mature_profit_usd`` sums the positions past
        ``MATURE_GROWTH_PCT``."""
        held = dict(balances or {})
        at = dict(prices or {})
        spendable = self.opening_spendable_usd
        locked = self.opening_locked_usd
        mature = 0.0
        mature_bots = 0
        for bot_id, balance in held.items():
            price = float(at.get(bot_id, 0.0) or 0.0)
            spendable += balance.cash_usd - balance.anchor_target_usd
            locked += balance.value_usd(price) - balance.anchor_target_usd
            one = balance.mature_usd(price)
            if one > 0.0:
                mature += one
                mature_bots += 1
        return self._figures(spendable, locked, mature, mature_bots, len(held))

    def _figures(
        self,
        spendable: float,
        locked: float,
        mature: float,
        mature_bots: int,
        open_: int,
    ) -> dict:
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
            "bots_open": open_,
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
    "CURRENCY",
    "FIGURE_LABELS",
    "LOCKED_LABEL",
    "MATURE_GROWTH_PCT",
    "MATURE_LABEL",
    "REALIZED_LABEL",
    "SPENDABLE_LABEL",
    "FakeBalance",
    "PaperLedger",
    "fleet_target_usd",
    "mature_profit_usd",
    "opening_ledger",
]
