"""``EmptyTabsMixin`` builds the three tabs whose screens are not written yet.

One builder per tab hands ``_add_empty_tab`` a surface, and
``empty_tab_widget`` draws that surface's ``view_model``. The heading, the
state sentence and the issue sentence come from the one view model that
``src.core.desktop_bridge`` also serves to the ``src/gui/web`` module.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .. import design_system as ds
from . import paper_trader_tab_surface as paper_trader
from . import proof_of_accumulation_tab_surface as proof_of_accumulation
from . import system_status_tab_surface as system_status

EMPTY_TAB_SURFACES = (paper_trader, system_status, proof_of_accumulation)

HEADING_NAME = "empty-tab-heading"
STATE_NAME = "empty-tab-state"
ISSUE_NAME = "empty-tab-issue"

PANEL_STYLE = f"QWidget {{ background: {ds.SURFACE_0}; }}"
HEADING_STYLE = (
    f"QLabel {{ color: {ds.TEXT_MAX}; font-size: 20px; font-weight: bold; }}"
)
BODY_STYLE = f"QLabel {{ color: {ds.TEXT_EMPTY_STATE}; font-size: 13px; }}"

MARGINS_PX = (24, 24, 24, 24)
SPACING_PX = 8

#: Each drawn label: its object name, the view-model field, and its skin.
LABELS = (
    (HEADING_NAME, "heading", HEADING_STYLE),
    (STATE_NAME, "state_text", BODY_STYLE),
    (ISSUE_NAME, "issue_text", BODY_STYLE),
)


def empty_tab_widget(model: dict) -> QWidget:
    """One tab drawn from an empty-state view model.

    Every word comes from ``model``; the widget derives none of its own.
    """
    panel = QWidget()
    panel.setAccessibleName(model["accessible_name"])
    panel.setStyleSheet(PANEL_STYLE)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(*MARGINS_PX)
    layout.setSpacing(SPACING_PX)
    for name, field, style in LABELS:
        label = QLabel(model[field])
        label.setObjectName(name)
        label.setAccessibleName(name)
        label.setStyleSheet(style)
        layout.addWidget(label)
    layout.addStretch(1)
    return panel


class EmptyTabsMixin:
    """Supplies the three empty-tab builders to the main window."""

    # Annotation only; MainWindow supplies this and no attribute is created here.
    _main_tabs: Any

    def _add_empty_tab(self, surface: Any) -> QWidget:
        """Draw one surface's empty state and add it to ``_main_tabs``.

        ``_empty_tabs`` keeps each panel under its surface's bridge method.
        """
        if not hasattr(self, "_empty_tabs"):
            self._empty_tabs: dict = {}
        model = surface.view_model({})
        panel = empty_tab_widget(model)
        self._empty_tabs[surface.METHOD] = panel
        self._main_tabs.addTab(panel, model["heading"])
        return panel

    def _build_paper_trader_tab(self) -> None:
        """Add the Paper Trader tab to ``_main_tabs``."""
        self._add_empty_tab(paper_trader)

    def _build_system_status_tab(self) -> None:
        """Add the System Status tab to ``_main_tabs``."""
        self._add_empty_tab(system_status)

    def _build_proof_of_accumulation_tab(self) -> None:
        """Add the Proof of Accumulation tab to ``_main_tabs``."""
        self._add_empty_tab(proof_of_accumulation)
