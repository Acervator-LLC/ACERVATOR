"""Market Inspector tab of the main window."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("acervator.gui")


class MarketInspectorTabMixin:
    """The pair scanner and its topology-proposal handoff."""

    # Supplied by MainWindow at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
    _adopt_topology_proposal: Callable[..., Any]
    _build_topology_proposals: Callable[..., Any]
    _main_tabs: Any
    _schedule_async: Callable[..., Any]
    _settings: Any

    def _build_market_inspector_tab(self) -> None:
        """Build the Market Inspector tab and add it to the main tab widget."""
        # --- Tab 5: Market Inspector (v3.23.37 — replaces
        # legacy Market Map). Owns the fetch cycle; the Bot Details
        # per-bot Market Inspector tab reads back from the shared
        # analyzer at src/trading/market_inspector.py.
        # v3.23.38 — wired to the exchange-based fetcher via
        # set_exchange_source(): connectors are looked up lazily
        # so the tab always sees the current dict.
        from ..market_inspector import MarketInspectorTab

        self._market_inspector = MarketInspectorTab()
        # v3.24.57 (C35) — hand the proposals pane a place to
        # persist 24 h dismissals. The pane deliberately does not
        # resolve settings itself; this is the only point in the
        # tree that already holds the operator's manager.
        try:
            self._market_inspector.set_dismiss_store(self._settings)
        except Exception as _ds_exc:  # noqa: BLE001 - persistence is optional
            logger.debug("topology dismiss-store wiring skipped: %s", _ds_exc)
        self._market_inspector.set_exchange_source(
            connectors_getter=(lambda: getattr(self, "_exchange_connectors", {})),
            scheduler=self._schedule_async,
        )
        # v3.23.68 — wire topology proposals into the right pane.
        # Detector runs on-demand from the pane's Refresh button
        # (and the 10-min auto-timer), so this is a pure getter
        # that assembles the context dict from live subsystems.
        self._market_inspector.set_proposal_source(
            lambda: self._build_topology_proposals()
        )
        # v3.23.69 — wire the Adopt handoff: preview modal's Adopt
        # button emits `adoptRequested(proposal)` → the pane
        # forwards to the orchestrator on the main window.
        self._market_inspector.set_adopt_handler(self._adopt_topology_proposal)
        self._main_tabs.addTab(self._market_inspector, "Market Inspector")
