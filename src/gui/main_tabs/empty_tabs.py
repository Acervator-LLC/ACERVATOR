"""``EmptyTabsMixin`` builds the two tabs whose screens are not written yet.

One builder per tab hands ``_add_empty_tab`` a surface, and
``_empty_tab_class`` answers with ``EmptyTabQtPanel`` or the React panel for
the running build. The heading, the state sentence and the issue sentence come
from the one view model that ``src.core.desktop_bridge`` also serves to the
``src/gui/web`` module, and ``SKIN`` carries the colours and sizes both sides
paint.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .. import design_system as ds
from . import proof_of_accumulation_tab_surface as proof_of_accumulation
from . import system_status_tab_surface as system_status

EMPTY_TAB_SURFACES = (system_status, proof_of_accumulation)

HEADING_NAME = "empty-tab-heading"
STATE_NAME = "empty-tab-state"
ISSUE_NAME = "empty-tab-issue"

HEADING_SIZE_PX = 20
BODY_SIZE_PX = ds.TYPE_BODY

MARGINS_PX = (24, 24, 24, 24)
SPACING_PX = 8

PANEL_STYLE = f"QWidget {{ background: {ds.SURFACE_0}; }}"
HEADING_STYLE = (
    f"QLabel {{ color: {ds.TEXT_MAX}; font-size: {HEADING_SIZE_PX}px; "
    "font-weight: bold; }"
)
BODY_STYLE = f"QLabel {{ color: {ds.TEXT_EMPTY_STATE}; font-size: {BODY_SIZE_PX}px; }}"

#: The skin both sides paint, as the CSS custom properties the page reads.
SKIN = {
    "--empty-tab-ground": ds.SURFACE_0,
    "--empty-tab-heading-colour": ds.TEXT_MAX,
    "--empty-tab-body-colour": ds.TEXT_EMPTY_STATE,
    "--empty-tab-heading-size": f"{HEADING_SIZE_PX}px",
    "--empty-tab-body-size": f"{BODY_SIZE_PX}px",
    # Qt reads left, top, right, bottom; CSS padding reads top, right, bottom, left.
    "--empty-tab-pad": "{1}px {2}px {3}px {0}px".format(*MARGINS_PX),
    "--empty-tab-gap": f"{SPACING_PX}px",
}

#: Each drawn label: its object name, the view-model field, and its skin.
LABELS = (
    (HEADING_NAME, "heading", HEADING_STYLE),
    (STATE_NAME, "state_text", BODY_STYLE),
    (ISSUE_NAME, "issue_text", BODY_STYLE),
)


class EmptyTabQtPanel(QWidget):
    """One tab drawn from an empty-state view model, in Qt labels.

    Every word comes from ``model``; the widget derives none of its own.
    """

    def __init__(self, model: dict, parent=None) -> None:
        """Draw the heading, the state sentence and the issue sentence."""
        super().__init__(parent)
        self.setAccessibleName(model["accessible_name"])
        self.setStyleSheet(PANEL_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*MARGINS_PX)
        layout.setSpacing(SPACING_PX)
        for name, field, style in LABELS:
            label = QLabel(model[field])
            label.setObjectName(name)
            label.setAccessibleName(name)
            label.setStyleSheet(style)
            layout.addWidget(label)
        layout.addStretch(1)


def _empty_tab_class() -> type:
    """The empty-tab panel class the running variant draws, Qt or React."""
    from ..variant_surface import EMPTY_TAB, surface_class

    return surface_class(EMPTY_TAB)


class EmptyTabsMixin:
    """Supplies the three empty-tab builders to the main window."""

    # Annotation only; MainWindow supplies this and no attribute is created here.
    _main_tabs: Any

    def _add_empty_tab(self, surface: Any, index: int | None = None) -> QWidget:
        """Draw one surface's empty state and add it to ``_main_tabs``.

        ``index`` inserts at that slot; None appends. ``_empty_tabs`` keeps each
        panel under its surface's bridge method.
        """
        if not hasattr(self, "_empty_tabs"):
            self._empty_tabs: dict = {}
        model = surface.view_model({})
        panel = _empty_tab_class()(model)
        self._empty_tabs[surface.METHOD] = panel
        if index is None:
            self._main_tabs.addTab(panel, model["heading"])
        else:
            self._main_tabs.insertTab(index, panel, model["heading"])
        return panel

    def _build_system_status_tab(self) -> None:
        """Add the System Status tab to ``_main_tabs``."""
        self._add_empty_tab(system_status)

    def _build_proof_of_accumulation_tab(self) -> None:
        """Add the Proof of Accumulation tab to ``_main_tabs``."""
        self._add_empty_tab(proof_of_accumulation)
