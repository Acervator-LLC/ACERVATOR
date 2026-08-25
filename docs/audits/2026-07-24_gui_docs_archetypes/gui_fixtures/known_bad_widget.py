"""A PySide6 widget with SIX deliberately-introduced GUI defects.

Ground truth — each defect is labeled with the tool expected to catch it:

  G1  no_accessible_name         line 23    GUIArchetype GUI001 (high)
  G2  missing_docstring          line 23    GUIArchetype GUI002 (medium)
  G3  absolute_positioning       line 30    GUIArchetype GUI003 (high)
  G4  child_widget_no_parent     line 26    GUIArchetype GUI004 (medium)
  G5  hardcoded_password         line 20    Bandit B105 (remapped to high)
  G6  no_signal_wiring           line 29-30 GUIArchetype GUI005 (medium)

Not-labeled but potentially caught by ruff:
  - Missing function type hints on __init__ (ANN)
  - No F/E/W issues intentionally.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QPushButton, QWidget

ADMIN_PASSWORD = "letmein"  # G5 hardcoded credential — Bandit B105


class LegacyForm(QWidget):
    # G2 no docstring here — GUI002
    def __init__(self, parent=None):
        super().__init__(parent)
        # G1 no self.setAccessibleName / setAccessibleDescription call anywhere
        # G4 child widgets without parent argument
        self._input = QLineEdit()
        self._submit = QPushButton("Go")
        # G3 absolute positioning, no QLayout
        self._input.setGeometry(10, 10, 200, 30)
        self._submit.setGeometry(220, 10, 60, 30)
