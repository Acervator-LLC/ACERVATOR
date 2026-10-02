"""``SystemStatusTabMixin`` builds the main window's Status tab.

``_build_system_status_tab`` asks ``variant_surface`` which form of the Status
tab to draw and appends what it answers. ``SystemStatusQtTab`` is the default
and ``SystemStatusReactPanel`` draws the same read-out
``system_status_tab_surface`` serves. ``_reorder_main_tabs`` moves the tab to
its place on the bar afterwards.
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
        """Append the Status tab, and hold None when its form cannot be built."""
        try:
            from ..variant_surface import SYSTEM_STATUS, surface_class

            self._system_status_tab = surface_class(SYSTEM_STATUS)()
            self._main_tabs.addTab(self._system_status_tab, HEADING)
        except Exception as exc:  # noqa: BLE001 - a missing tab is not a crash
            logger.warning("Status tab unavailable: %s", exc)
            self._system_status_tab = None
