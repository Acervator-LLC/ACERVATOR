"""GUI006 fixture, BAD half: colour claims with no rendered pixel.

Byte-for-byte the same widget and the same colour claims as
`known_good_colour_test.py`, with the pixel checks deleted and nothing
else changed. Every assertion here still PASSES at runtime against a
widget whose stylesheet paints it a different colour, which is the
whole defect: the model reports what it was told, not what was drawn.

The archetype must exit 1 on this file and 0 on its pair.

Named `*_test.py` under a `tests/` directory so the archetype's
`_is_test_file` and its bandit B101 suppression both recognise it. It
lives under docs/audits and is never collected by pytest, which only
walks the repository's own `tests/`.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

RED = "#b3261e"


def _build_table() -> QTableWidget:
    """One red cell, painted through the item model."""
    table = QTableWidget(1, 1)
    item = QTableWidgetItem("x")
    item.setBackground(QColor(RED))
    table.setItem(0, 0, item)
    table.resize(120, 40)
    return table


def test_the_cell_is_red_on_screen() -> None:
    """Reads the model only. Cannot see a stylesheet override."""
    table = _build_table()
    assert table.item(0, 0).background().color().name() == RED
    assert table.item(0, 0).foreground().color().name() != RED


def test_the_button_accent_is_painted() -> None:
    """A stylesheet claim with nothing rendered to confirm it."""
    table = _build_table()
    table.setStyleSheet("QTableWidget { background: #101018; }")
    assert "#101018" in table.styleSheet()


def test_the_ramp_colour_comes_back_through_a_helper() -> None:
    """The indirect shape: the live read hides in a nested helper."""
    table = _build_table()

    def _cell_colour(col: int) -> str:
        return table.item(0, col).background().color().name()

    assert _cell_colour(0) == RED
