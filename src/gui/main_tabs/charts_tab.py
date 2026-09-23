"""Charts tab of the main window."""

from __future__ import annotations

import logging
from typing import Any

from .main_window_surface import CHARTS_TAB

logger = logging.getLogger("acervator.gui")


class ChartsTabMixin:
    """The per-asset chart grid.

    ``variant_surface`` decides whether that tab is the Qt one or the
    React one.
    """

    # Supplied by MainWindow at runtime; annotation only, so no attribute
    # is created here.
    _main_tabs: Any
    _stored_accent: Any

    def _build_charts_tab(self) -> None:
        """Build the Charts tab and add it to the main tab widget."""
        from ..variant_surface import CHARTS, surface_class

        try:
            built = surface_class(CHARTS)()
        except Exception as exc:
            logger.warning("React Charts tab unavailable: %s", exc)
            from ..widgets.trade_charts_tab import TradeChartsTab

            built = TradeChartsTab()
        self._charts_tab = built
        from ..theme_engine import THEMES, accented, applied_theme

        self._charts_tab.set_theme(
            accented(THEMES[applied_theme()], self._stored_accent())
        )
        self._main_tabs.addTab(self._charts_tab, CHARTS_TAB)
