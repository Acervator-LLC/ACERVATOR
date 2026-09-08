"""``SimulatorTabMixin`` builds the Sim tab of the main window."""

from __future__ import annotations

from typing import Any

from .main_window_surface import SIM_TAB, SIMULATOR_BUILD_INDEX


class SimulatorTabMixin:
    """``_build_simulator_tab`` inserts ``SimulatorTab`` and wires ``_bot_manager``."""

    # MainWindow supplies these; the bare annotations create no attribute.
    _bot_manager: Any
    _main_tabs: Any
    _market_inspector: Any

    def _build_simulator_tab(self) -> None:
        """Insert ``SimulatorTab`` into ``_main_tabs`` and wire its getters."""
        from ..simulator_tab import SimulatorTab

        self._simulator = SimulatorTab()
        # _reorder_main_tabs runs after every builder, so this is not the final slot.
        self._main_tabs.insertTab(SIMULATOR_BUILD_INDEX, self._simulator, SIM_TAB)
        if hasattr(self._simulator, "set_connectors_getter"):
            self._simulator.set_connectors_getter(
                lambda: getattr(self, "_exchange_connectors", {})
            )
        if hasattr(self._simulator, "set_bot_manager"):
            self._simulator.set_bot_manager(self._bot_manager)
        # _bot_viz is built by _build_bot_swarm_tab, not by this method.
        if hasattr(self._simulator, "set_swarm_getter"):
            self._simulator.set_swarm_getter(lambda: getattr(self, "_bot_viz", None))
        if hasattr(self._simulator, "set_topology_getter"):
            self._simulator.set_topology_getter(
                lambda: (
                    self._market_inspector.current_topology_proposals()
                    if hasattr(
                        getattr(self, "_market_inspector", None),
                        "current_topology_proposals",
                    )
                    else None
                )
            )
