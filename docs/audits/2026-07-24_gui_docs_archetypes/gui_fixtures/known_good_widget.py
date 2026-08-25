"""A PySide6 widget with zero known GUI-quality defects.

Ground truth: GUIArchetype.review() should produce zero critical/high
findings. This widget follows the SKILL's PySide6 conventions:
  - Class-level docstring present.
  - Layout used (QVBoxLayout), not absolute positioning.
  - Accessible-name setter called on every interactive widget.
  - Child widgets constructed with a parent argument.
  - Every interactive widget's primary signal is wired to a slot.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SearchPanel(QWidget):
    """A search panel with a text input and a submit button.

    Renders a labeled text field and a submit button in a vertical
    stack. Emits `search_requested(text: str)` when the user presses
    Enter or clicks Submit.
    """

    search_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAccessibleName("Search panel")
        self.setAccessibleDescription("Enter a query; press Enter or Submit to search.")

        self._input = QLineEdit(self)
        self._input.setAccessibleName("Search input")
        self._input.setAccessibleDescription("Type a query and press Enter.")
        self._input.returnPressed.connect(self._on_submit)

        self._submit = QPushButton("Submit", self)
        self._submit.setAccessibleName("Submit search")
        self._submit.setAccessibleDescription("Run the search with the current query.")
        self._submit.clicked.connect(self._on_submit)

        layout = QVBoxLayout(self)
        layout.addWidget(self._input)
        layout.addWidget(self._submit)
        self.setLayout(layout)

    def _on_submit(self) -> None:
        self.search_requested.emit(self._input.text())
