"""History tab of the main window."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("acervator.gui")


class HistoryTabMixin:
    """Exchange-truth trade history and its Simulator front-load bridge."""

    # Supplied by MainWindow at runtime; declared so a type checker
    # can resolve them. Annotations only: no attribute is created and
    # the runtime base stays `object`.
    _bot_manager: Any
    _main_tabs: Any

    def _build_history_tab(self) -> None:
        """Build the History tab and add it to the main tab widget."""
        # --- Tab 12: History (v3.17.0 rebuild — exchange-truth) ---
        # Operator directive 2026-05-18: "I am still not happy with
        # the History tab. Clean out all code for it to start fresh
        # and make it so that it can pull trade histories from
        # current active exchanges." Old trade_history_tab.py replaced
        # by new history_tab.py that pulls live from each active
        # exchange's get_my_trades() API (v3.16.46+).
        try:
            from ..history_tab import HistoryTab

            self._history_tab = HistoryTab()
            self._history_tab.set_bot_manager(self._bot_manager)
            self._main_tabs.addTab(self._history_tab, "History")
            # Backward-compat alias for code paths that referenced
            # the old name; safe to remove after a few sessions.
            self._trade_history_tab = self._history_tab

            # v3.23.88 — H4 bridge, ACTUALLY wired this time.
            # Operator observation 2026-08-01: "History Tab does
            # not front load the Simulator Tab with YTD data
            # despite this being repeatedly directed." Prior
            # cascades emitted the signal from History but never
            # connected a subscriber on the Sim side. Fix here:
            # once both tabs exist, connect the signal → sim
            # front-load handler.
            try:
                sim_tab = getattr(self, "_simulator", None)
                fleet_panel = getattr(sim_tab, "fleet_replay", None)
                if (
                    fleet_panel is not None
                    and hasattr(self._history_tab, "history_refreshed")
                    and self._history_tab.history_refreshed is not None
                    and hasattr(fleet_panel, "on_history_refreshed")
                ):
                    self._history_tab.history_refreshed.connect(
                        fleet_panel.on_history_refreshed
                    )
                    logger.info("H4 bridge wired: History → Simulator " "front-load")
            except Exception as _br_exc:  # noqa: BLE001
                logger.debug("H4 bridge wire failed: %s", _br_exc)
        except Exception as exc:
            logger.warning("History tab unavailable: %s", exc)
            self._history_tab = None
            self._trade_history_tab = None

        # --- No second History tab ---
        # Issue #128 R6 folded the React renderer INTO the History
        # tab above: HistoryTab holds a HistoryWebTable where its
        # QTableWidget used to be. A separate "History (React)" tab
        # would put the same rows on screen twice.
