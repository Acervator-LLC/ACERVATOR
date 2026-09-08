"""``SimulatorTabMixin`` builds the main window's Sim tab.

``_build_simulator_tab`` inserts the tab at ``SIMULATOR_BUILD_INDEX``, and
``variant_surface`` decides whether it is the Qt clone or the React one. The
tab is handed no connector, no bot manager and no event bus: its one data path
is ``TabletSource``, which reads Stone Tablets and answers no send.
"""

from __future__ import annotations

import logging
from typing import Any

from .main_window_surface import SIMULATOR_BUILD_INDEX
from .simulator_tab_surface import HEADING

logger = logging.getLogger("acervator.gui")


class SimulatorTabMixin:
    """Supplies ``_build_simulator_tab`` to the main window."""

    # MainWindow supplies _main_tabs; annotation only, no attribute is created.
    _main_tabs: Any

    def _build_simulator_tab(self) -> None:
        """Insert the Sim tab at ``SIMULATOR_BUILD_INDEX``."""
        try:
            from ..variant_surface import SIMULATOR, surface_class

            self._simulator_tab = surface_class(SIMULATOR)()
            self._main_tabs.insertTab(
                SIMULATOR_BUILD_INDEX, self._simulator_tab, HEADING
            )
        except Exception as exc:  # noqa: BLE001 - a missing tab is not a crash
            logger.warning("Sim tab unavailable: %s", exc)
            self._simulator_tab = None
