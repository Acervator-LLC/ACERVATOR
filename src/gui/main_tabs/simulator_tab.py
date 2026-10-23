"""``SimulatorTabMixin`` builds the main window's Sim tab.

``_build_simulator_tab`` inserts the tab at ``SIMULATOR_BUILD_INDEX``, and
``variant_surface`` decides whether it is the Qt clone or the React one. The
tab is handed no connector, no bot manager and no event bus: its one data path
is ``TabletSource``, which reads Stone Tablets and answers no send. A caught
build seats ``BuildFailureNote`` in the same slot, naming the tab and what the
build raised.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .. import design_system as ds
from .main_window_surface import SIMULATOR_BUILD_INDEX
from .simulator_tab_surface import HEADING

logger = logging.getLogger("acervator.gui")

UNAVAILABLE_LOG = "Sim tab unavailable: %s"
NOTE_REFUSED_LOG = "Sim tab build note unavailable: %s"

NOTE_NAME = "sim-tab-build-failure"
NOTE_HEADING_NAME = "sim-tab-build-failure-heading"
NOTE_REASON_NAME = "sim-tab-build-failure-reason"
NOTE_REST_NAME = "sim-tab-build-failure-rest"

NOTE_HEADING = f"The {HEADING} tab did not build."
NOTE_REASON = "What the build reported: {text}"
NOTE_NO_REASON = "The build reported no text."
NOTE_REST = "Every other tab is working."

NOTE_HEADING_SIZE_PX = ds.TYPE_H3
NOTE_MARGINS_PX = (ds.SPACE_L, ds.SPACE_L, ds.SPACE_L, ds.SPACE_L)
NOTE_SPACING_PX = ds.SPACE_S

NOTE_PANEL_STYLE = f"QWidget {{ background: {ds.SURFACE_0}; }}"
NOTE_HEADING_STYLE = (
    f"QLabel {{ color: {ds.WARNING}; font-size: {NOTE_HEADING_SIZE_PX}px; "
    "font-weight: bold; }"
)
NOTE_BODY_STYLE = (
    f"QLabel {{ color: {ds.TEXT_EMPTY_STATE}; font-size: {ds.TYPE_BODY}px; }}"
)


def failure_text(exc: BaseException) -> str:
    """The sentence ``BuildFailureNote`` draws for ``exc``.

    Answers ``NOTE_NO_REASON`` for an exception carrying no text of its own.
    """
    text = str(exc).strip()
    return NOTE_REASON.format(text=text) if text else NOTE_NO_REASON


def _note_label(text: str, name: str, style: str) -> QLabel:
    """One wrapped ``QLabel`` of ``BuildFailureNote``, named ``name``."""
    label = QLabel(text)
    label.setObjectName(name)
    label.setAccessibleName(name)
    label.setStyleSheet(style)
    label.setWordWrap(True)
    return label


class BuildFailureNote(QWidget):
    """The page seated at ``SIMULATOR_BUILD_INDEX`` when the Sim tab will not build.

    It draws ``NOTE_HEADING``, the sentence ``failure_text`` answers, and
    ``NOTE_REST``.
    """

    def __init__(self, text: str, parent: Any = None) -> None:
        """Draws ``NOTE_HEADING``, ``text`` and ``NOTE_REST`` on ``NOTE_PANEL_STYLE``."""
        super().__init__(parent)
        self.setObjectName(NOTE_NAME)
        self.setAccessibleName(NOTE_NAME)
        self.setStyleSheet(NOTE_PANEL_STYLE)
        box = QVBoxLayout(self)
        box.setContentsMargins(*NOTE_MARGINS_PX)
        box.setSpacing(NOTE_SPACING_PX)
        box.addWidget(_note_label(NOTE_HEADING, NOTE_HEADING_NAME, NOTE_HEADING_STYLE))
        box.addWidget(_note_label(text, NOTE_REASON_NAME, NOTE_BODY_STYLE))
        box.addWidget(_note_label(NOTE_REST, NOTE_REST_NAME, NOTE_BODY_STYLE))
        box.addStretch(1)


class SimulatorTabMixin:
    """Supplies ``_build_simulator_tab`` to the main window."""

    # MainWindow supplies _main_tabs; annotation only, no attribute is created.
    _main_tabs: Any

    def _build_simulator_tab(self) -> None:
        """Insert the Sim tab at ``SIMULATOR_BUILD_INDEX``."""
        try:
            from ..variant_surface import SIMULATOR, surface_class

            self._simulator_tab = surface_class(SIMULATOR)()
            self._main_tabs.insertTab(
                SIMULATOR_BUILD_INDEX, self._simulator_tab, HEADING
            )
        except Exception as exc:  # noqa: BLE001 - a missing tab is not a crash
            logger.warning(UNAVAILABLE_LOG, exc)
            self._simulator_tab = None
            self._seat_simulator_build_note(failure_text(exc))

    def _seat_simulator_build_note(self, text: str) -> None:
        """Insert ``BuildFailureNote`` carrying ``text`` at ``SIMULATOR_BUILD_INDEX``.

        A tab book that refuses this insert leaves ``NOTE_REFUSED_LOG`` and no
        page, keeping a caught build clear of the window.
        """
        try:
            self._main_tabs.insertTab(
                SIMULATOR_BUILD_INDEX, BuildFailureNote(text), HEADING
            )
        except Exception as note_exc:
            logger.warning(NOTE_REFUSED_LOG, note_exc)
