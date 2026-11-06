# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Qt build of the unlock screen, drawn from ``fleet_unlock_surface``.

``FleetUnlockDialog`` builds one password row and two buttons from the names
that module declares, and ``ask_for_unlock`` shows it and answers whether the
saved fleet came open. ``src/gui/main_window.py, in unlock_fleet`` is the only
thing the typed password is handed to, and ``main.py, in main`` raises this
screen on a launch the latch holds.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6 import QtWidgets

from .main_tabs import fleet_unlock_surface as surface
from .tooltips import set_description

logger = logging.getLogger(surface.LOGGER_NAME)


class FleetUnlockDialog(QtWidgets.QDialog):
    """Take the password for a sealed saved fleet and hand it to one window.

    ``window`` is what answers ``unlock_fleet``; the dialog reads nothing off
    the state file and stores no password of its own.
    """

    def __init__(self, window: Any, parent: Optional[QtWidgets.QWidget] = None) -> None:
        """Build the screen from ``fleet_unlock_surface`` against *window*."""
        super().__init__(parent)
        self._window = window
        self._outcome = surface.OUTCOME_EMPTY

        box = surface.WIDGET
        self.setAccessibleName(box["accessible_name"])
        self.setWindowTitle(box["window_title"])
        self.setModal(box["modal"])
        self.setMinimumWidth(box["minimum_width_px"])
        self.setStyleSheet(box["style_sheet"])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(*surface.LAYOUT["margins_px"])
        layout.setSpacing(surface.LAYOUT["spacing_px"])

        layout.addWidget(self._line(surface.HEADLINE_LABEL, surface.HEADLINE_TEXT))
        layout.addWidget(self._line(surface.DETAIL_LABEL, surface.DETAIL_TEXT))

        row = surface.PHRASE_ROW
        form = QtWidgets.QFormLayout()
        self._phrase = QtWidgets.QLineEdit(self)
        self._phrase.setObjectName(row["object_name"])
        self._phrase.setPlaceholderText(row["placeholder"])
        if row["echo_hidden"]:
            self._phrase.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        set_description(self._phrase, row["description"])
        self._phrase.textChanged.connect(self._show_press_state)
        self._phrase.returnPressed.connect(self._on_unlock)
        form.addRow(str(row["label"]), self._phrase)
        layout.addLayout(form)

        self._feedback = self._line(surface.FEEDBACK_LABEL, surface.RESTING_TEXT)
        layout.addWidget(self._feedback)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setContentsMargins(*surface.BUTTON_ROW_LAYOUT["margins_px"])
        buttons.setSpacing(surface.BUTTON_ROW_LAYOUT["spacing_px"])
        buttons.addStretch(surface.STRETCH_WEIGHT)
        self._dismiss = self._button(surface.DISMISS, self._on_dismiss)
        buttons.addWidget(self._dismiss)
        self._unlock = self._button(surface.UNLOCK, self._on_unlock)
        buttons.addWidget(self._unlock)
        layout.addLayout(buttons)

        self._show_press_state()
        self._phrase.setFocus()

    def _line(self, spec: dict, text: str) -> QtWidgets.QLabel:
        """One label of the screen, named and wrapped the way *spec* declares."""
        label = QtWidgets.QLabel(str(text), self)
        label.setObjectName(spec["object_name"])
        label.setWordWrap(spec["word_wrap"])
        return label

    def _button(self, name: str, pressed: Any) -> QtWidgets.QPushButton:
        """One button of the screen, built from the ``buttons`` entry *name* names."""
        spec = surface.build_view_model(self._phrase.text())["buttons"][name]
        button = QtWidgets.QPushButton(spec["text"], self)
        button.setObjectName(name)
        button.setMinimumHeight(spec["minimum_height_px"])
        button.setDefault(spec["is_default"])
        button.setAutoDefault(spec["is_default"])
        set_description(button, spec["description"])
        button.clicked.connect(pressed)
        return button

    @property
    def unlocked(self) -> bool:
        """True only once a typed password opened the saved fleet."""
        return surface.outcome_answer(self._outcome)

    @property
    def outcome(self) -> str:
        """The last ``fleet_unlock_surface.unlock_outcome`` this screen read."""
        return self._outcome

    def press_live(self) -> bool:
        """Whether the Unlock button is live for the row as it stands."""
        return bool(self._unlock.isEnabled())

    def feedback_text(self) -> str:
        """The words the feedback label is carrying."""
        return str(self._feedback.text())

    def type_password(self, typed: str) -> None:
        """Put *typed* in the password row, as a keystroke would."""
        self._phrase.setText(str(typed))

    def _show_press_state(self) -> None:
        """Arm or blind the Unlock button for the row, from one declared reading.

        ``fleet_unlock_surface.build_view_model`` decides it, so an empty row
        cannot reach ``src/core/encryption.py, in open_master_key`` on either
        build.
        """
        spec = surface.build_view_model(self._phrase.text())["buttons"][surface.UNLOCK]
        self._unlock.setEnabled(spec["enabled"])
        set_description(self._unlock, spec["description"])

    def _on_unlock(self) -> None:
        """Hand the typed password to the window and draw what came back.

        ``fleet_unlock_surface.unlock_outcome`` is the whole decision, and this
        closes only on the outcome that opened the fleet.
        """
        self._outcome = surface.unlock_outcome(self._phrase.text(), self._window)
        self._feedback.setText(surface.outcome_words(self._outcome))
        if self._outcome == surface.OUTCOME_OPENED:
            logger.info(surface.OPENED_LOG)
            self.accept()
            return
        if self._outcome == surface.OUTCOME_NO_WINDOW:
            logger.error(surface.NO_WINDOW_LOG)
            return
        if self._outcome == surface.OUTCOME_REFUSED:
            logger.warning(surface.REFUSED_LOG)

    def _on_dismiss(self) -> None:
        """Leave the fleet sealed and close, which is what Escape also does."""
        logger.warning(surface.DISMISSED_LOG)
        self.reject()

    def reject(self) -> None:
        """Escape and the title-bar X land here, and both leave the fleet sealed.

        The outcome is cleared to ``fleet_unlock_surface.OUTCOME_EMPTY`` here as
        well as in ``_on_dismiss``, so no path out of this screen reports an
        unlock the operator did not get.
        """
        if self._outcome != surface.OUTCOME_OPENED:
            self._outcome = surface.OUTCOME_EMPTY
        super().reject()


def release_dialog(dialog: Optional[FleetUnlockDialog]) -> None:
    """Destroy *dialog* now, handing ownership back to Python with ``setParent``.

    ``deleteLater`` would leave the widget in ``topLevelWidgets`` until an event
    loop delivered a deferred delete, and ``ask_for_unlock`` reads the answer
    before this call.
    """
    if dialog is None:
        return
    try:
        dialog.close()
        dialog.setParent(None)
    except RuntimeError as exc:
        logger.debug(surface.RELEASE_LOG, exc)


def ask_for_unlock(window: Any, parent: Optional[QtWidgets.QWidget] = None) -> bool:
    """Show the unlock screen and answer whether the saved fleet came open.

    A screen that cannot be built answers
    ``fleet_unlock_surface.BUILD_FAILED_ANSWER``, so a fleet is never reported
    open by a surface the operator could not read.
    """
    dialog: Optional[FleetUnlockDialog] = None
    try:
        dialog = FleetUnlockDialog(window, parent=parent)
        dialog.exec()
        opened = bool(dialog.unlocked)
    except Exception as exc:  # noqa: BLE001 - a broken screen means a sealed fleet
        logger.error(surface.BUILD_FAILED_LOG, exc)
        opened = surface.BUILD_FAILED_ANSWER
    finally:
        release_dialog(dialog)
    return opened
