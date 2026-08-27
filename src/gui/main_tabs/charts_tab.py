"""Asset Charts tab of the main window."""

from __future__ import annotations

from typing import Any

from ..widgets.trade_charts_tab import TradeChartsTab


class ChartsTabMixin:
    """The per-asset chart grid."""

    # Supplied by MainWindow at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
    _main_tabs: Any

    def _build_charts_tab(self) -> None:
        """Build the Asset Charts tab and add it to the main tab widget."""
        # --- Tab 2: Charts ---
        self._charts_tab = TradeChartsTab()
        self._main_tabs.addTab(self._charts_tab, "Asset Charts")

        # --- Tab 3: API Tester — REMOVED per MEM-247 (Session 26) ---
        # Operator directive: "API Tester can be ripped out."
        # Class APITesterTab remains in this file (unused) pending a
        # future cleanup pass. Left in place to avoid cascading import /
        # symbol-reference breakage during the Phase 1 slice. If
        # resurrected later, re-add the addTab line above this block.
