"""``SystemStatusTabMixin`` builds the main window's Status tab.

``_build_system_status_tab`` appends ``SystemStatusReactPanel``, which draws the
emitter network read-out ``system_status_tab_surface`` serves.
``_reorder_main_tabs`` moves it to its place on the bar afterwards. The screen
has no Qt original, so no ``variant_surface`` entry decides the side.
"""

from __future__ import annotations

import logging
from typing import Any

from .system_status_tab_surface import HEADING

logger = logging.getLogger("acervator.gui")


class SystemStatusTabMixin:
    """Supplies ``_build_system_status_tab`` to the main window."""

    # MainWindow supplies _main_tabs; annotation only, no attribute is created.
    _main_tabs: Any

    def _build_system_status_tab(self) -> None:
        """Append the Status tab, and hold None when its page cannot be built."""
        try:
            from ..react_system_status_tab import SystemStatusReactPanel

            self._system_status_tab = SystemStatusReactPanel()
            self._main_tabs.addTab(self._system_status_tab, HEADING)
        except Exception as exc:  # noqa: BLE001 - a missing tab is not a crash
            logger.warning("Status tab unavailable: %s", exc)
            self._system_status_tab = None
