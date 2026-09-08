"""``MarketInspectorTabMixin``, the Inspector tab builder."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .main_window_surface import INSPECTOR_TAB

logger = logging.getLogger("acervator.gui")


class MarketInspectorTabMixin:
    """Builds the Inspector tab and wires its proposal and adopt handlers.

    ``variant_surface`` decides whether that tab is the Qt one or the React one.
    """

    # MainWindow supplies these at runtime; the annotations create no attribute.
    _adopt_topology_proposal: Callable[..., Any]
    _build_topology_proposals: Callable[..., Any]
    _main_tabs: Any
    _schedule_async: Callable[..., Any]
    _settings: Any

    def _build_market_inspector_tab(self) -> None:
        """Build the Inspector tab and add it to the main tab widget."""
        from ..variant_surface import MARKET_INSPECTOR, surface_class

        self._market_inspector = surface_class(MARKET_INSPECTOR)()
        try:
            self._market_inspector.set_dismiss_store(self._settings)
        except Exception as _ds_exc:  # noqa: BLE001 - persistence is optional
            logger.debug("topology dismiss-store wiring skipped: %s", _ds_exc)
        self._market_inspector.set_exchange_source(
            connectors_getter=(lambda: getattr(self, "_exchange_connectors", {})),
            scheduler=self._schedule_async,
        )
        self._market_inspector.set_proposal_source(
            lambda: self._build_topology_proposals()
        )
        self._market_inspector.set_adopt_handler(self._adopt_topology_proposal)
        self._main_tabs.addTab(self._market_inspector, INSPECTOR_TAB)
