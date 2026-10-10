"""``EmptyTabsMixin`` builds a tab whose screen is not written yet.

``_add_empty_tab`` takes a surface and ``_empty_tab_class`` answers with
``EmptyTabQtPanel`` or the React panel for the running build. The heading, the
state sentence and the issue sentence come from the one view model that
``src.core.desktop_bridge`` also serves to the ``src/gui/web`` module, and
``SKIN`` carries the colours and sizes both sides paint. A model carrying
``build_text`` draws one more control, and ``buildRequested`` carries its press
out with the sector the note names.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import design_system as ds

HEADING_NAME = "empty-tab-heading"
STATE_NAME = "empty-tab-state"
ISSUE_NAME = "empty-tab-issue"
BUILD_NAME = "empty-tab-build"

HEADING_SIZE_PX = 20
BODY_SIZE_PX = ds.TYPE_BODY

MARGINS_PX = (24, 24, 24, 24)
SPACING_PX = 8

#: The room the build button takes, so it draws at its own width and the row
#: beside it stays empty.
BUILD_PAD_PX = (10, 18, 10, 18)
BUILD_RADIUS_PX = 3
BUILD_TOP_GAP_PX = 8

PANEL_STYLE = f"QWidget {{ background: {ds.SURFACE_0}; }}"
HEADING_STYLE = (
    f"QLabel {{ color: {ds.TEXT_MAX}; font-size: {HEADING_SIZE_PX}px; "
    "font-weight: bold; }"
)
BODY_STYLE = f"QLabel {{ color: {ds.TEXT_EMPTY_STATE}; font-size: {BODY_SIZE_PX}px; }}"
BUILD_STYLE = (
    f"QPushButton {{ background: {ds.PRIMARY}; color: {ds.SURFACE_0}; "
    f"font-size: {BODY_SIZE_PX}px; font-weight: bold; border: none; "
    f"border-radius: {BUILD_RADIUS_PX}px; "
    f"padding: {BUILD_PAD_PX[0]}px {BUILD_PAD_PX[1]}px "
    f"{BUILD_PAD_PX[2]}px {BUILD_PAD_PX[3]}px; }}"
    f"QPushButton:hover {{ background: {ds.PRIMARY_BRIGHT}; }}"
)

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
    "--empty-tab-build-ground": ds.PRIMARY,
    "--empty-tab-build-hover": ds.PRIMARY_BRIGHT,
    "--empty-tab-build-colour": ds.SURFACE_0,
    "--empty-tab-build-radius": f"{BUILD_RADIUS_PX}px",
    "--empty-tab-build-pad": "{0}px {1}px {2}px {3}px".format(*BUILD_PAD_PX),
    "--empty-tab-build-top": f"{BUILD_TOP_GAP_PX}px",
}

#: Each drawn label: its object name, the view-model field, and its skin.
LABELS = (
    (HEADING_NAME, "heading", HEADING_STYLE),
    (STATE_NAME, "state_text", BODY_STYLE),
    (ISSUE_NAME, "issue_text", BODY_STYLE),
)


class EmptyTabQtPanel(QWidget):
    """One tab drawn from an empty-state view model, in Qt labels.

    Every word comes from ``model``; the widget derives none of its own, and a
    model carrying ``build_text`` also draws the button ``buildRequested`` fires.
    """

    #: Carries ``build_class`` when the build button is pressed.
    buildRequested = Signal(str)  # noqa: N815 - Qt signal name

    def __init__(self, model: dict, parent=None) -> None:
        """Draw the heading, the two sentences and, where offered, the button."""
        super().__init__(parent)
        self.setAccessibleName(model["accessible_name"])
        self.setStyleSheet(PANEL_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*MARGINS_PX)
        layout.setSpacing(SPACING_PX)
        for name, field, style in LABELS:
            label = QLabel(str(model.get(field) or ""))
            label.setObjectName(name)
            label.setAccessibleName(name)
            label.setStyleSheet(style)
            layout.addWidget(label)
        self._build = self._build_button(model)
        if self._build is not None:
            layout.addSpacing(BUILD_TOP_GAP_PX)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addWidget(self._build)
            row.addStretch(1)
            layout.addLayout(row)
        layout.addStretch(1)

    def build_button(self):
        """The build button this panel drew, or None where it offered none."""
        return self._build

    def _build_button(self, model: dict):
        """The button ``build_text`` names, wired to ``buildRequested``."""
        label = str(model.get("build_text") or "")
        if not label:
            return None
        key = str(model.get("build_class") or "")
        button = QPushButton(label, self)
        button.setObjectName(BUILD_NAME)
        button.setAccessibleName(label)
        button.setStyleSheet(BUILD_STYLE)
        button.clicked.connect(lambda: self.buildRequested.emit(key))
        return button


def _empty_tab_class() -> type:
    """The empty-tab panel class the running variant draws, Qt or React."""
    from ..variant_surface import EMPTY_TAB, surface_class

    return surface_class(EMPTY_TAB)


class EmptyTabsMixin:
    """Supplies ``_add_empty_tab`` to the main window."""

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
