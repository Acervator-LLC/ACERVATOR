"""Positive control for the offscreen pixel checker in tests/qt_pixel.py.

A pixel checker that cannot fail is exactly the blindness it was built
to fix, so the checker is exercised here on a widget where the model
and the screen are KNOWN to disagree.

THE CASE, measured 2026-08-11
=============================
A QTableWidget carrying per-cell ``item.setBackground(QColor(RED))``
plus a ``QTableWidget::item { background: GREY; }`` stylesheet rule:

    item.background().color().name()  ->  "#b3261e"   (the model)
    rendered pixel at the cell centre ->  "#101018"   (the screen)

The stylesheet wins at paint time. The item model is never updated, so
a test that reads the model passes while the operator looks at grey.

The same table WITHOUT the stylesheet renders red, and that variant is
the negative half of the control: it proves the sampler reports the
real colour rather than always disagreeing.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from tests.qt_pixel import (
    assert_pixel_colour,
    ensure_app,
    pixel_at,
    render_widget,
    table_cell_centre,
)

MODEL_RED = "#b3261e"
STYLESHEET_GREY = "#101018"
OVERRIDE_QSS = "QTableWidget::item { background: #101018; color: #ffffff; }"


def _table(*, with_stylesheet: bool) -> QTableWidget:
    """A one-row table painted red per cell, optionally overridden."""
    ensure_app()
    table = QTableWidget(1, 2)
    table.horizontalHeader().setVisible(False)
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    for col in range(2):
        item = QTableWidgetItem("x")
        item.setBackground(QColor(MODEL_RED))
        table.setItem(0, col, item)
    if with_stylesheet:
        table.setStyleSheet(OVERRIDE_QSS)
    table.resize(240, 80)
    return table


def test_control_the_sampler_reports_the_real_colour():
    """Negative half: with no override, model and screen agree.

    Without this, a sampler that returned a constant would still make
    the failing case below look like a success.
    """
    table = _table(with_stylesheet=False)
    point = table_cell_centre(table, 0, 0)

    assert table.item(0, 0).background().color().name() == MODEL_RED
    assert assert_pixel_colour(table, point, MODEL_RED) == MODEL_RED


def test_the_model_assertion_passes_while_the_pixel_assertion_fails():
    """Positive control: one widget, two verdicts that disagree."""
    table = _table(with_stylesheet=True)
    point = table_cell_centre(table, 0, 0)

    # (1) THE MODEL ASSERTION -- passes. This is the shape GUI006 flags.
    assert table.item(0, 0).background().color().name() == MODEL_RED

    # (2) THE PIXEL ASSERTION -- fails, on the same widget, same colour.
    with pytest.raises(AssertionError) as caught:
        assert_pixel_colour(table, point, MODEL_RED)
    assert STYLESHEET_GREY in str(caught.value)

    # And the sampled pixel is the stylesheet colour, not the model one.
    assert pixel_at(render_widget(table), point) == STYLESHEET_GREY


def test_render_widget_refuses_an_empty_image():
    """A zero-sized grab must raise, not return a blank sample.

    A checker that samples a 0x0 render reads a default colour for
    every point and can never disagree with anything.
    """
    ensure_app()
    table = _table(with_stylesheet=False)
    table.resize(0, 0)
    with pytest.raises(RuntimeError, match="empty image"):
        render_widget(table)


def test_a_sample_point_off_the_image_raises():
    """Off-image points must raise rather than read a default colour."""
    table = _table(with_stylesheet=False)
    image = render_widget(table)
    off = table_cell_centre(table, 0, 0)
    off.setX(image.width() + 50)
    with pytest.raises(IndexError):
        pixel_at(image, off)
