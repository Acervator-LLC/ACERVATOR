"""GUI006 fixture, GOOD half: colour claims backed by a rendered pixel.

Paired with `known_bad_colour_test.py`, which is the same file with the
pixel checks deleted. The archetype must exit 0 here and 1 there; a
rule that cannot tell these two apart is not measuring anything.

Named `*_test.py` so the archetype's `_is_test_file` recognises it.
It lives under docs/audits and is never collected by pytest, which
only walks `tests/`.
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
    """Reads the model AND the pixel, so the two cannot disagree."""
    table = _build_table()
    assert table.item(0, 0).background().color().name() == RED

    image = table.grab().toImage()
    centre = table.visualItemRect(table.item(0, 0)).center()
    assert QColor(image.pixelColor(centre)).name() == RED


def test_the_button_accent_is_painted() -> None:
    """A stylesheet claim, also checked against the render."""
    table = _build_table()
    table.setStyleSheet("QTableWidget { background: #101018; }")
    assert "#101018" in table.styleSheet()

    image = table.grab().toImage()
    assert QColor(image.pixelColor(1, 1)).name() == "#101018"
