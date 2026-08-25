"""C04: the wire overlay must not cover the default List view.

THE DEFECT
`_on_tab_changed` called `_wire_canvas.show()` whenever the Bot Swarm
tab was active, ignoring which VIEW was showing. It fires at
construction, and the default view is List, so the canvas was shown
over the list on every launch.

It then took its geometry from `_grid_widget` — the HIDDEN stacked page,
which QStackedLayout never geometries in StackOne mode — so it sat at a
stale 640x480 over the list's top ~452 px and 93% of its width.
`_WireCanvas` is not transparent for mouse events and defines no
`wheelEvent`, so clicks and scrolls in the first ~15 rows of the DEFAULT
view were swallowed.

Measured before the fix (audit render probe):
    wire_canvas visible : True
    childAt(200, 200)   : _WireCanvas
Measured after:
    wire_canvas visible : False
    childAt(200, 200)   : QWidget   (the list)
    grid geometry       : 680x733   (was a stale 640x480)

This is the same failure `_reposition_wire_canvas`'s own comment records
("7 broken interactions"): the v3.23.19 fix scoped the canvas to the
grid, then v3.23.61 made the grid the hidden page without revisiting it.

WHY C06b HAD TO LAND FIRST
While broken, this overlay was the only thing shielding the default view
from `_finish_wire_drag`'s two silent wire-removal branches. Restoring
the view ARMS those gestures, so they were confirmed in C06b before this
shipped.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from src.gui.bot_visualizer import BotVisualizationTab  # noqa: E402


@pytest.fixture
def tab():
    app = QApplication.instance() or QApplication([])
    t = BotVisualizationTab()
    t.resize(1400, 800)
    t.show()
    app.processEvents()
    yield t, app
    t.close()
    app.processEvents()


class TestDefaultViewIsUsable:
    def test_the_default_view_is_the_list(self, tab):
        """Positive control: if the default were Grid, every assertion
        below would pass for the wrong reason."""
        t, _ = tab
        assert t._view_stack.currentIndex() == 0
        assert t._view_mode == "list"

    def test_canvas_is_hidden_on_the_default_view(self, tab):
        """THE defect. It was shown at construction regardless of view."""
        t, _ = tab
        assert not t._wire_canvas.isVisible(), (
            "the wire overlay is visible over the List view; it is "
            "mouse-opaque and will swallow clicks in the top rows"
        )

    def test_clicks_in_the_list_area_do_not_hit_the_canvas(self, tab):
        """The consequence, measured the way the audit measured it."""
        t, _ = tab
        for pt in ((200, 200), (200, 400), (200, 600)):
            child = t.childAt(*pt)
            assert (
                type(child).__name__ != "_WireCanvas"
            ), f"a click at {pt} lands on the wire overlay, not the list"


class TestGridStillWorks:
    def test_switching_to_grid_shows_the_canvas(self, tab):
        """Negative control: hiding it on List must not disable it
        everywhere. Grid mode is where wire-drag lives."""
        t, app = tab
        t._view_combo.setCurrentIndex(1)
        app.processEvents()
        assert t._wire_canvas.isVisible()

    def test_grid_geometry_is_not_stale(self, tab):
        """It used to reveal whatever rect it last had — after any
        resize in List mode, the wrong one. 640x480 was the stale
        default the audit measured."""
        t, app = tab
        t._view_combo.setCurrentIndex(1)
        app.processEvents()
        g = t._wire_canvas.geometry()
        assert (g.width(), g.height()) != (
            640,
            480,
        ), "canvas is showing the stale default rect"
        assert g.width() > 600 and g.height() > 600

    def test_switching_back_hides_it_again(self, tab):
        t, app = tab
        t._view_combo.setCurrentIndex(1)
        app.processEvents()
        t._view_combo.setCurrentIndex(0)
        app.processEvents()
        assert not t._wire_canvas.isVisible()


class TestResizeKeepsGeometryCurrent:
    def test_resize_while_hidden_is_not_dropped(self, tab):
        """resizeEvent used to skip entirely unless the canvas was
        visible, so resizes during List mode were lost and Grid then
        opened with the pre-resize rect."""
        t, app = tab
        t.resize(1000, 700)
        app.processEvents()
        t._view_combo.setCurrentIndex(1)
        app.processEvents()
        g = t._wire_canvas.geometry()
        assert g.width() <= 1000, (
            f"canvas width {g.width()} exceeds the resized window; the "
            f"resize was dropped while hidden"
        )
