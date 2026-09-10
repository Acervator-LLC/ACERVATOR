"""``ProofOfAccumulationTabMixin`` builds the main window's Accumulation tab.

``_build_proof_of_accumulation_tab`` appends ``ProofOfAccumulationReactPanel``,
which draws the three-zone shell ``proof_of_accumulation_tab_surface`` serves.
``_reorder_main_tabs`` moves it to its place on the bar afterwards. The screen
has no Qt original, so no ``variant_surface`` entry decides the side.
"""

from __future__ import annotations

import logging
from typing import Any

from .proof_of_accumulation_tab_surface import HEADING

logger = logging.getLogger("acervator.gui")


class ProofOfAccumulationTabMixin:
    """Supplies ``_build_proof_of_accumulation_tab`` to the main window."""

    # MainWindow supplies _main_tabs; annotation only, no attribute is created.
    _main_tabs: Any

    def _build_proof_of_accumulation_tab(self) -> None:
        """Append the Accumulation tab, and hold None when its page cannot be built."""
        try:
            from ..react_proof_of_accumulation_tab import ProofOfAccumulationReactPanel

            self._proof_of_accumulation_tab = ProofOfAccumulationReactPanel()
            self._main_tabs.addTab(self._proof_of_accumulation_tab, HEADING)
        except Exception as exc:  # noqa: BLE001 - a missing tab is not a crash
            logger.warning("Accumulation tab unavailable: %s", exc)
            self._proof_of_accumulation_tab = None
