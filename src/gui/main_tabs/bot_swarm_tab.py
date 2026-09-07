"""Bot Swarm tab of the main window."""

from __future__ import annotations

import logging
from typing import Any

from .main_window_surface import SWARM_TAB

logger = logging.getLogger("acervator.gui")


class BotSwarmTabMixin:
    """The fleet visualiser.

    ``variant_surface`` decides whether that tab is the Qt one or the
    React one.
    """

    # Supplied by MainWindow at runtime; annotation only, so no attribute
    # is created here.
    _main_tabs: Any

    def _build_bot_swarm_tab(self) -> None:
        """Build the Bot Swarm tab and add it to the main tab widget."""
        from ..variant_surface import BOT_SWARM, surface_class

        try:
            built = surface_class(BOT_SWARM)()
        except Exception as exc:
            logger.warning("React Bot Swarm tab unavailable: %s", exc)
            from ..bot_visualizer import BotVisualizationTab

            built = BotVisualizationTab()
        self._bot_viz = built
        self._main_tabs.addTab(self._bot_viz, SWARM_TAB)
