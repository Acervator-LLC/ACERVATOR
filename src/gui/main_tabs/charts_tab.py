"""Asset Charts tab of the main window."""

from __future__ import annotations

from typing import Any

from ..widgets.trade_charts_tab import TradeChartsTab


class ChartsTabMixin:
    """The per-asset chart grid."""

    # Supplied by MainWindow at runtime; annotation only, so no attribute
    # is created here.
    _main_tabs: Any

    def _build_charts_tab(self) -> None:
        """Build the Asset Charts tab and add it to the main tab widget."""
        self._charts_tab = TradeChartsTab()
        self._main_tabs.addTab(self._charts_tab, "Asset Charts")
