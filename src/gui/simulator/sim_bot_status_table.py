"""The Simulator's Scrumming-bot table.

``SimBotStatusTable`` is ``BotStatusTable`` with the Simulator's three own
readings: ``_display_price`` prices a row from its own ``stats.current_price``
at ``SIM_PRICE_AGE_S``, ``_denom_cell`` denominates through
``sim_target_denom_cell`` over ``usd_rates``, and ``_sort_lookups`` orders the
rows by those two.
"""

from __future__ import annotations

import logging

from .sim_bot_status_table_surface import (
    SIM_PRICE_AGE_S,
    sim_target_denom_cell,
    usd_rates,
)

logger = logging.getLogger("acervator.gui")

try:
    from ..main_tabs.bot_status_table_surface import SortLookups
    from ..widgets.bot_status_table import SCRUMMING_COLUMNS, BotStatusTable

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    __all__ = ["SCRUMMING_COLUMNS", "SimBotStatusTable"]

    class SimBotStatusTable(BotStatusTable):
        """Live's table over the row's own price and the fleet's own rates."""

        def __init__(self, on_bot_clicked=None, on_fire_clicked=None, parent=None):
            """Hold an empty rate map until the first ``update_bots``."""
            self._rates: dict = {}
            super().__init__(
                on_bot_clicked=on_bot_clicked,
                on_fire_clicked=on_fire_clicked,
                parent=parent,
            )

        def update_bots(self, bot_statuses: list[dict]) -> None:
            """Rewrite every row, ``usd_rates`` read off ``bot_statuses`` first."""
            self._rates = usd_rates(list(bot_statuses))
            super().update_bots(bot_statuses)

        def _display_price(self, status: dict, stats: dict) -> tuple:
            """The row's own ``current_price``, at ``SIM_PRICE_AGE_S``."""
            del status
            return float(stats.get("current_price", 0.0) or 0.0), SIM_PRICE_AGE_S

        def _denom_cell(
            self, quote: str, base_asset: str, exchange_id: str, target_val: float
        ) -> tuple:
            """One Target-denom cell, ``sim_target_denom_cell`` over ``_rates``."""
            del exchange_id
            return sim_target_denom_cell(quote, base_asset, target_val, self._rates)

        def _sort_lookups(self) -> SortLookups:
            """``order_statuses``' two readings, over the Simulator's own figures."""

            def price(status) -> tuple:
                stats = status.get("stats", {}) or {}
                return self._display_price(status, stats)

            def denom_text(
                quote: str, base: str, exchange_id: str, target: float
            ) -> str:
                return self._denom_cell(quote, base, exchange_id, target)[0]

            return SortLookups(price, denom_text)
