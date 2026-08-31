"""The skin comparison a parity test uses instead of reading a live style.

A failure means a parity test can be told two sides carry one skin when
the pixels say otherwise, or refused when the pixels say they do.
"""

from __future__ import annotations

import pytest

from tests.fixtures.host_fonts import load_run_fonts
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_same_skin,
    colour_count,
)

SIZE = (420, 220)
FORCED_ITEM_SHEET = "QTableWidget::item { background: #101018; }"
CONTROL_RULE = "QTableWidget { gridline-color: #3a1414; border: 3px solid #7a1414; }"

_alive: list[object] = []


def app():
    """The one application object, with this run's font choice applied."""
    from PySide6.QtWidgets import QApplication

    load_run_fonts()
    return QApplication.instance()


def hold(widget):
    """Keep `widget` alive for the run so no render reads a freed object."""
    _alive.append(widget)
    return widget


def table(item_colour="#b3261e", sheet="", rows=3):
    """A real table of the shape a parity test renders."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

    built = hold(QTableWidget())
    built.setColumnCount(2)
    built.setRowCount(rows)
    built.setHorizontalHeaderLabels(["Pair", "Ammo"])
    for row in range(rows):
        for column in range(2):
            cell = QTableWidgetItem("BTC" if column == 0 else "$50.00")
            cell.setBackground(QColor(item_colour))
            built.setItem(row, column, cell)
    if sheet:
        built.setStyleSheet(sheet)
    return built


def flat_window():
    """A window that paints its background and nothing else."""
    from PySide6.QtWidgets import QWidget

    return hold(QWidget())


def render(widget):
    """One render of `widget` at the size every check here uses."""
    from tests.qt_pixel import render_widget

    return render_widget(widget, SIZE)


def test_two_sides_built_the_same_way_carry_one_skin():
    """The check refused two sides that paint the same picture."""
    app()
    assert_same_skin(
        build_old_side=table,
        build_new_side=table,
        size=SIZE,
        control_rule=CONTROL_RULE,
    )


def test_two_sides_with_different_skins_are_reported():
    """The check passed two sides whose skins paint different pictures."""
    app()
    with pytest.raises(AssertionError) as reported:
        assert_same_skin(
            build_old_side=table,
            build_new_side=lambda: table(sheet=FORCED_ITEM_SHEET),
            size=SIZE,
            control_rule=CONTROL_RULE,
        )
    assert "painted a different picture" in str(reported.value)


def test_a_declared_colour_the_platform_repaints_does_not_split_the_sides():
    """A live-object read decided the verdict where the pixels agree.

    Both sides force the item background from a style sheet, so the two
    different declared item colours reach no pixel. A check reading the
    item colour reports a difference the screen does not carry.
    """
    app()
    assert_same_skin(
        build_old_side=lambda: table("#b3261e", FORCED_ITEM_SHEET),
        build_new_side=lambda: table("#00ff00", FORCED_ITEM_SHEET),
        size=SIZE,
        control_rule=CONTROL_RULE,
    )


def test_one_declared_style_on_both_sides_does_not_hide_two_pictures():
    """A live-object read decided the verdict where the pixels differ.

    Neither side sets a style sheet, so a check comparing declared style
    sheets compares one empty string with another and reports nothing.
    The items carry different colours and the two sides paint apart.
    """
    app()
    with pytest.raises(AssertionError) as reported:
        assert_same_skin(
            build_old_side=lambda: table("#b3261e"),
            build_new_side=lambda: table("#00ff00"),
            size=SIZE,
            control_rule=CONTROL_RULE,
        )
    assert "painted a different picture" in str(reported.value)


def test_a_render_that_paints_one_colour_is_refused():
    """A window that paints one colour reached a comparison."""
    app()
    with pytest.raises(AssertionError) as reported:
        assert_picture_can_report(render(flat_window()))
    assert "no comparison of it can report" in str(reported.value)


def test_a_render_that_paints_many_colours_is_accepted():
    """The refusal fires on a render that carries the product's pixels."""
    app()
    found = assert_picture_can_report(render(table()))
    assert found > colour_count(render(flat_window()))


def test_a_flat_window_paints_one_colour_and_a_table_paints_more():
    """The colour counter returns one number whatever a render painted."""
    app()
    flat = colour_count(render(flat_window()))
    rich = colour_count(render(table()))
    assert flat == 1, flat
    assert rich > flat, (rich, flat)


def test_a_side_that_paints_one_colour_is_refused_before_any_comparison():
    """Two flat windows passed the skin check by painting nothing."""
    app()
    with pytest.raises(AssertionError) as reported:
        assert_same_skin(
            build_old_side=flat_window,
            build_new_side=flat_window,
            size=SIZE,
            control_rule=CONTROL_RULE,
        )
    assert "painted 1 colour" in str(reported.value)


def test_a_control_rule_that_reaches_a_later_widget_is_reported():
    """A skin that outlived its widget went unreported.

    The stand-in builder carries the rule on every widget after its
    first, which is what a style sheet left behind does to every render
    that follows it.
    """
    app()
    calls: list[int] = []

    def leaky_builder():
        built = table()
        if calls:
            built.setStyleSheet(CONTROL_RULE)
        calls.append(1)
        return built

    with pytest.raises(AssertionError) as reported:
        assert_same_skin(
            build_old_side=table,
            build_new_side=leaky_builder,
            size=SIZE,
            control_rule=CONTROL_RULE,
        )
    assert "outlived the widget" in str(reported.value)


def test_a_widget_passed_in_place_of_a_builder_is_refused():
    """A widget reached the check that renders each side more than once."""
    app()
    with pytest.raises(AssertionError) as reported:
        assert_same_skin(
            build_old_side=table(),
            build_new_side=table,
            size=SIZE,
            control_rule=CONTROL_RULE,
        )
    assert "not a widget" in str(reported.value)


def test_an_empty_control_rule_is_refused():
    """A control rule that paints nothing was accepted as a control."""
    app()
    with pytest.raises(AssertionError) as reported:
        assert_same_skin(
            build_old_side=table,
            build_new_side=table,
            size=SIZE,
            control_rule="",
        )
    assert "needs a control rule" in str(reported.value)


def test_two_different_real_cases_paint_two_pictures():
    """The picture comparison passes whatever the second side paints."""
    app()
    assert_cases_paint_differently(
        old_side=render(table(rows=3)),
        new_side=render(table(rows=6)),
        note="three rows against six",
    )


def test_two_renders_of_one_case_fail_the_cases_control():
    """The cases control reports a difference between two equal pictures."""
    app()
    with pytest.raises(AssertionError) as reported:
        assert_cases_paint_differently(
            old_side=render(table()),
            new_side=render(table()),
        )
    assert "painted one picture" in str(reported.value)


def test_the_cases_control_refuses_a_flat_render():
    """A flat window served as one half of the reporting control."""
    app()
    with pytest.raises(AssertionError) as reported:
        assert_cases_paint_differently(
            old_side=render(flat_window()),
            new_side=render(table()),
        )
    assert "old side" in str(reported.value)
