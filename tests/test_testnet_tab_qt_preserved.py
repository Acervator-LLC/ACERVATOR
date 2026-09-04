"""The Qt Local Testnet tab stays built while React draws beside it.

The React panel reads the same values over the ``testnet_tab.state``
bridge method. Until the running application's logs verify that panel,
the Qt tab is what the operator sees, so these tests construct the real
widget and count the live Qt children it holds. A widget dropped from
the tree drops out of the count.
"""

from __future__ import annotations

import collections
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import testnet_tab as shipped
from src.gui.main_tabs import testnet_tab_surface as surface
from tests.qt_pixel import ensure_app, render_widget

#: Every widget class this tab builds itself, and how many it builds.
#: Qt builds scroll bars, header views and popup frames of its own, so
#: only the classes the tab constructs are counted.
BUILT_WIDGETS = {
    "QGroupBox": 7,
    "QLabel": 18,
    "QPushButton": 3,
    "QSpinBox": 2,
    "QDoubleSpinBox": 1,
    "QComboBox": 1,
    "QTableWidget": 4,
    "QTextEdit": 1,
    "QSplitter": 1,
}

TAB_SIZE = (900, 700)


@pytest.fixture()
def tab():
    """The real Qt tab over a stand-in chain, its poll timer stopped."""
    ensure_app()
    built = shipped.TestnetTab(None, surface.TestnetSnapshot(), None)
    built._timer.stop()
    yield built
    built.deleteLater()


def live_kinds(widget) -> dict:
    """How many live children of each class the widget tree still holds."""
    from PySide6.QtWidgets import QWidget

    counted = collections.Counter(
        one.__class__.__name__ for one in widget.findChildren(QWidget)
    )
    return {name: counted.get(name, 0) for name in BUILT_WIDGETS}


def test_the_tab_is_a_real_qt_widget_with_the_declared_accessible_name(tab):
    from PySide6.QtWidgets import QWidget

    assert isinstance(tab, QWidget)
    assert tab.accessibleName() == surface.ACCESSIBLE_NAME
    assert shipped._QT is True


def test_the_tab_still_holds_every_widget_it_builds(tab):
    """A deleted panel, table or button drops out of this count."""
    assert live_kinds(tab) == BUILT_WIDGETS


def test_the_count_falls_when_a_panel_is_taken_out_of_the_tree(tab):
    """The positive control: the counter sees a panel leave the tree.

    The events panel is unparented the way deleting its ``addWidget``
    would leave it, and both it and the table inside it stop being
    counted.
    """
    before = live_kinds(tab)
    tab._evt_tbl.parent().setParent(None)
    after = live_kinds(tab)
    assert after["QGroupBox"] == before["QGroupBox"] - 1
    assert after["QTableWidget"] == before["QTableWidget"] - 1
    assert after != BUILT_WIDGETS


def test_the_four_qt_tables_carry_the_columns_the_surface_declares(tab):
    wanted = {
        "_block_tbl": surface.BLOCK_COLUMNS,
        "_tx_tbl": surface.TX_COLUMNS,
        "_evt_tbl": surface.EVENT_COLUMNS,
        "_tok_tbl": surface.HOLDER_COLUMNS,
    }
    for name, columns in wanted.items():
        table = getattr(tab, name)
        assert table.columnCount() == len(columns), name
        assert [
            table.horizontalHeaderItem(at).text() for at in range(table.columnCount())
        ] == list(columns), name


def test_the_qt_tab_paints_pixels_rather_than_an_empty_picture(tab):
    """A tab that renders nothing is preserved in name only."""
    image = render_widget(tab, TAB_SIZE)
    seen = {
        image.pixelColor(x, y).name()
        for x in range(0, TAB_SIZE[0], 37)
        for y in range(0, TAB_SIZE[1], 41)
    }
    assert len(seen) > 1, seen
    assert surface.PANEL.lower() in seen, sorted(seen)


def test_the_pixel_reading_reports_one_colour_for_a_blank_widget():
    """The positive control for the painted-pixel check above."""
    from PySide6.QtWidgets import QWidget

    ensure_app()
    blank = QWidget()
    blank.setStyleSheet("background:" + surface.PANEL + ";")
    image = render_widget(blank, TAB_SIZE)
    seen = {
        image.pixelColor(x, y).name()
        for x in range(0, TAB_SIZE[0], 37)
        for y in range(0, TAB_SIZE[1], 41)
    }
    assert seen == {surface.PANEL.lower()}, sorted(seen)
    blank.deleteLater()
