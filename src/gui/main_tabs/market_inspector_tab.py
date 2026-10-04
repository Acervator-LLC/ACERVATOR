"""``MarketInspectorTabMixin``, the Inspector tab builder."""

from __future__ import annotations

import logging
from typing import Any, Callable

from .main_window_surface import INSPECTOR_TAB

logger = logging.getLogger("acervator.gui")


class MarketInspectorTabMixin:
    """Builds the Inspector tab and wires its proposal, adopt and push handlers.

    ``variant_surface`` decides whether that tab is the Qt one or the React one.
    """

    # MainWindow supplies these at runtime; the annotations create no attribute.
    _adopt_topology_proposal: Callable[..., Any]
    _push_candidate_to_sim: Callable[..., Any]
    _push_candidate_to_paper: Callable[..., Any]
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
        try:
            self._market_inspector.set_push_to_sim_handler(self._push_candidate_to_sim)
        except Exception as _ps_exc:  # noqa: BLE001 - the Sim tab may not build
            logger.debug("Push to Sim wiring skipped: %s", _ps_exc)
        try:
            self._market_inspector.set_push_to_paper_handler(
                self._push_candidate_to_paper
            )
        except Exception as _pp_exc:  # noqa: BLE001 - the Paper tab may not build
            logger.debug("Push to Paper wiring skipped: %s", _pp_exc)
        self._wire_ata_chart_list(self._market_inspector)
        self._wire_ata_activity_log(self._market_inspector)
        self._main_tabs.addTab(self._market_inspector, INSPECTOR_TAB)

    def _wire_ata_activity_log(self, inspector: Any) -> None:
        """Point ``inspector``'s scan phase lines at the Live tab's ``StatusLog``.

        The Live tab is built first, so ``_status_log`` is the pane every
        other Activity Log writer already calls.
        """
        pane = getattr(self, "_status_log", None)
        if pane is None or not hasattr(inspector, "set_activity_log"):
            logger.debug("no Activity Log pane; ATA-SPM phase lines reach the log only")
            return
        inspector.set_activity_log(pane.log)

    def _wire_ata_chart_list(self, inspector: Any) -> None:
        """Point the Charts tab's ATA-SMP list at ``inspector``'s ``PushBoard`` and
        its chart at the ``SectorBoard``'s ``chart_call``.

        The Charts tab is built first, so it reads both boards through a
        callable instead of holding a second copy of the markets.
        """
        charts = getattr(self, "_charts_tab", None)
        if charts is None or not hasattr(charts, "set_ata_source"):
            logger.debug("Charts tab offers no set_ata_source; ATA-SMP list is empty")
            return
        charts.set_ata_source(inspector.watched_markets)
        # MarketInspectorTab keeps its SectorBoard as _ata_board and offers no accessor.
        board = getattr(inspector, "_ata_board", None)
        if board is None or not hasattr(charts, "set_ata_call_source"):
            logger.debug("no SectorBoard reachable; ATA-SMP charts draw no call")
            return
        charts.set_ata_call_source(board.chart_call)
