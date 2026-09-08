"""``HistoryTabMixin`` builds the main window's History tab."""

from __future__ import annotations

import logging
from typing import Any

from .main_window_surface import HISTORY_TAB

logger = logging.getLogger("acervator.gui")


class HistoryTabMixin:
    """``_build_history_tab`` adds the History tab and wires it to the Simulator.

    ``variant_surface`` decides whether that tab is the Qt one or the React one.
    """

    # MainWindow supplies _bot_manager and _main_tabs; annotations only, no attribute.
    _bot_manager: Any
    _main_tabs: Any

    def _build_history_tab(self) -> None:
        """Add ``HistoryTab`` to ``_main_tabs`` and connect ``history_refreshed``."""
        try:
            from ..variant_surface import HISTORY, surface_class

            self._history_tab = surface_class(HISTORY)()
            self._history_tab.set_bot_manager(self._bot_manager)
            self._main_tabs.addTab(self._history_tab, HISTORY_TAB)
            # MainWindow and ApiTesterTab read _trade_history_tab under this name.
            self._trade_history_tab = self._history_tab
        except Exception as exc:
            logger.warning("History tab unavailable: %s", exc)
            self._history_tab = None
            self._trade_history_tab = None
