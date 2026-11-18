# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The first-run screen: import a fleet file, or start a new instance with no bots.

``main.py, in main`` raises ``ask_for_import`` after the splash while
``src/core/fleet_import.py, in fleet_on_disk`` answers False, and each file
picked goes to ``src/core/fleet_import.py, in import_fleet``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6 import QtWidgets

from ..core import fleet_import
from ..core.log_paths import resolve_fleet_path
from . import design_system as ds
from .tooltips import set_description

logger = logging.getLogger("acervator.gui.fleet_import")

ACCESSIBLE_NAME = "Fleet Import Dialog"
WINDOW_TITLE = "Acervator - no saved fleet"
MINIMUM_WIDTH_PX = 600

HEADLINE_TEXT = "No saved fleet was found."
DETAIL_FORMAT = (
    "This instance reads its fleet from {expected}. The folder name starts with "
    "a dot, so some file browsers hide it."
)
CHOICE_TEXT = (
    "Import a fleet file to bring its bots here, or start a new instance with "
    "no bots."
)
IMPORT_TEXT = "Import a fleet file..."
IMPORT_DESCRIPTION = (
    "Opens the file picker. The picked file is copied here, and its bots load Idle."
)
NEW_TEXT = "Start a new instance"
NEW_DESCRIPTION = "Opens with no bots, and writes nothing."
PICKER_CAPTION = "Pick a fleet file"
PICKER_FILTER = "Fleet files (*.json);;All files (*)"

HEADLINE = "headline"
DETAIL = "detail"
CHOICE = "choice"
FEEDBACK = "feedback"
IMPORT = "import"
NEW = "new_instance"

STYLE_SHEET = (
    f"QDialog {{ background: {ds.SURFACE_3}; color: {ds.TEXT_HIGH}; }}"
    f"QLabel {{ color: {ds.TEXT_MED};"
    f" font-family: {ds.FONT_FAMILY_UI};"
    f" font-size: {ds.TYPE_BODY}px; }}"
    f"QLabel#{HEADLINE} {{ color: {ds.WARNING};"
    f" font-size: {ds.TYPE_H3}px;"
    f" font-weight: {ds.WEIGHT_BOLD}; }}"
    f"QLabel#{DETAIL} {{ color: {ds.TEXT_HIGH}; }}"
    f"QLabel#{FEEDBACK} {{ color: {ds.DANGER}; }}"
    f"QPushButton {{ background: {ds.SURFACE_2};"
    f" color: {ds.TEXT_HIGH};"
    f" border: 1px solid {ds.OUTLINE};"
    f" border-radius: {ds.RADIUS_SM}px;"
    f" padding: {ds.SPACE_S}px {ds.SPACE_L}px;"
    f" font-family: {ds.FONT_FAMILY_UI};"
    f" font-size: {ds.TYPE_BODY}px; }}"
    f"QPushButton#{NEW} {{ border: {ds.FOCUS_RING_WIDTH}px solid"
    f" {ds.PRIMARY}; color: {ds.PRIMARY}; }}"
    f"QPushButton#{IMPORT} {{ color: {ds.SUCCESS};"
    f" border: 1px solid {ds.SUCCESS}; }}"
    f"QPushButton:focus {{ outline: none;"
    f" border: {ds.FOCUS_RING_WIDTH}px solid {ds.FOCUS_RING_COLOR}; }}"
)

BUILD_FAILED_LOG = (
    "fleet import screen could not be shown (%s). No file is imported and the "
    "platform opens with no bots."
)
PICK_CANCELLED_LOG = "fleet import: the file picker closed with no file picked"
NEW_INSTANCE_LOG = "fleet import: the operator started a new instance with no bots"


class FleetImportDialog(QtWidgets.QDialog):
    """Offer the two first-run choices and carry out the one pressed.

    ``import_outcome`` holds the last ``fleet_import.ImportOutcome`` a pick gave,
    and the screen closes only on one that ``imported``.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Build the screen around ``resolve_fleet_path`` as the expected place."""
        super().__init__(parent)
        self._outcome: Optional[fleet_import.ImportOutcome] = None

        self.setAccessibleName(ACCESSIBLE_NAME)
        self.setWindowTitle(WINDOW_TITLE)
        self.setModal(True)
        self.setMinimumWidth(MINIMUM_WIDTH_PX)
        self.setStyleSheet(STYLE_SHEET)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(ds.SPACE_L, ds.SPACE_L, ds.SPACE_L, ds.SPACE_L)
        layout.setSpacing(ds.SPACE_M)

        expected = DETAIL_FORMAT.format(expected=resolve_fleet_path())
        layout.addWidget(self._line(HEADLINE, HEADLINE_TEXT))
        layout.addWidget(self._line(DETAIL, expected))
        layout.addWidget(self._line(CHOICE, CHOICE_TEXT))
        self._feedback = self._line(FEEDBACK, "")
        layout.addWidget(self._feedback)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(ds.SPACE_M)
        buttons.addStretch(1)
        self._new = self._button(NEW, NEW_TEXT, NEW_DESCRIPTION, self._on_new)
        self._new.setDefault(True)
        buttons.addWidget(self._new)
        self._import = self._button(
            IMPORT, IMPORT_TEXT, IMPORT_DESCRIPTION, self._on_import
        )
        buttons.addWidget(self._import)
        layout.addLayout(buttons)

    def _line(self, name: str, text: str) -> QtWidgets.QLabel:
        """One wrapped label named *name*, so ``STYLE_SHEET`` colours it."""
        label = QtWidgets.QLabel(text, self)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label

    def _button(
        self, name: str, text: str, description: str, pressed
    ) -> QtWidgets.QPushButton:
        """One button named *name*, wired to *pressed*."""
        button = QtWidgets.QPushButton(text, self)
        button.setObjectName(name)
        button.setMinimumHeight(ds.TARGET_LARGE)
        set_description(button, description)
        button.clicked.connect(pressed)
        return button

    @property
    def import_outcome(self) -> Optional[fleet_import.ImportOutcome]:
        """The last ``fleet_import.ImportOutcome`` a pick gave, or None before one."""
        return self._outcome

    @property
    def imported(self) -> bool:
        """True only once ``import_outcome`` wrote the fleet file."""
        return self._outcome is not None and self._outcome.imported

    def feedback_text(self) -> str:
        """The refusal sentence the feedback label carries, or an empty string."""
        return str(self._feedback.text())

    def _on_import(self) -> None:
        """Open ``QFileDialog.getOpenFileName`` and hand the pick to ``import_fleet``.

        A refused file puts its sentence in the feedback label and leaves both
        buttons live, so the operator can pick again or start a new instance.
        """
        picked, _chosen_filter = QtWidgets.QFileDialog.getOpenFileName(
            self, PICKER_CAPTION, str(Path.home()), PICKER_FILTER
        )
        if not picked:
            logger.info(PICK_CANCELLED_LOG)
            return
        self._outcome = fleet_import.import_fleet(picked)
        if self._outcome.imported:
            self.accept()
            return
        self._feedback.setText(self._outcome.sentence)

    def _on_new(self) -> None:
        """Close with nothing imported, which is what Escape and the X also do."""
        logger.info(NEW_INSTANCE_LOG)
        self.reject()


def release_dialog(dialog: Optional[FleetImportDialog]) -> None:
    """Destroy *dialog* now, handing ownership back to Python with ``setParent``."""
    if dialog is None:
        return
    try:
        dialog.close()
        dialog.setParent(None)
    except RuntimeError as exc:
        logger.debug("fleet import screen was already destroyed: %s", exc)


def ask_for_import(
    parent: Optional[QtWidgets.QWidget] = None,
) -> Optional[fleet_import.ImportOutcome]:
    """Show the first-run screen and answer the import it completed, or None.

    None means a new instance with no bots, including a screen that could not
    be built, which ``BUILD_FAILED_LOG`` records.
    """
    dialog: Optional[FleetImportDialog] = None
    try:
        dialog = FleetImportDialog(parent=parent)
        dialog.exec()
        outcome = dialog.import_outcome if dialog.imported else None
    except Exception as exc:
        logger.error(BUILD_FAILED_LOG, exc)
        outcome = None
    finally:
        release_dialog(dialog)
    return outcome
