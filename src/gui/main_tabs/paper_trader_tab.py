"""``PaperTraderTabMixin`` builds the Paper tab into the main window.

``_build_paper_trader_tab`` inserts the tab at ``PAPER_BUILD_INDEX``, and
``variant_surface`` decides whether it is the Qt clone or the React one. The
tab is handed no connector, no live bot manager and no event bus: its one data
path is ``PaperExchange``, which reads the venue's public market feed and
answers no send.
"""

from __future__ import annotations

import logging
from typing import Any

from .main_window_surface import PAPER_BUILD_INDEX
from ..paper.paper_trading_tab_surface import HEADING

logger = logging.getLogger("acervator.gui")


class PaperTraderTabMixin:
    """Supplies ``_build_paper_trader_tab`` to the main window."""

    # MainWindow supplies _main_tabs; annotation only, no attribute is created.
    _main_tabs: Any

    def _build_paper_trader_tab(self) -> None:
        """Insert the Paper tab at ``PAPER_BUILD_INDEX``."""
        try:
            from ..variant_surface import PAPER_TRADER, surface_class

            self._paper_trader_tab = surface_class(PAPER_TRADER)()
            self._main_tabs.insertTab(
                PAPER_BUILD_INDEX, self._paper_trader_tab, HEADING
            )
        except Exception as exc:  # noqa: BLE001 - a missing tab is not a crash
            logger.warning("Paper tab unavailable: %s", exc)
            self._paper_trader_tab = None
