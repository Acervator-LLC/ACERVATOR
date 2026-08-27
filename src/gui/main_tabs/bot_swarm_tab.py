"""Bot Swarm tab of the main window."""

from __future__ import annotations

from typing import Any


class BotSwarmTabMixin:
    """The fleet visualiser."""

    # Supplied by MainWindow at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
    _main_tabs: Any

    def _build_bot_swarm_tab(self) -> None:
        """Build the Bot Swarm tab and add it to the main tab widget."""
        # --- Tab 4: Bot Visualization ---
        from ..bot_visualizer import BotVisualizationTab

        self._bot_viz = BotVisualizationTab()
        self._main_tabs.addTab(self._bot_viz, "Bot Swarm")
