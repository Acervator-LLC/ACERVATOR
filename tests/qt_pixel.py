"""Offscreen pixel verification for Qt widgets.

WHY THIS EXISTS
===============
Reading a colour back off a Qt object tells you what the widget was
TOLD to paint. It does not tell you what the widget painted.

MEASURED 2026-08-11, the real case this was built for: a QTableWidget
whose cells carry ``item.setBackground(QColor("#b3261e"))`` AND a
``QTableWidget::item { background: #101018; }`` stylesheet rule renders
the cell ``#101018`` while ``item.background().color().name()`` still
returns ``"#b3261e"``. The stylesheet wins at paint time; the item
model keeps the old value forever. A test asserting the model value
passes on a table the operator sees as dark grey.

Before this module the repository contained ZERO reads of a rendered
pixel: ``toImage(`` and ``pixelColor`` appeared nowhere under tests/.
Every colour claim in the suite was a model claim.

WHERE THIS LIVES AND WHY
========================
``tests/qt_pixel.py``, not ``dev_harness/harness/``. It is a test utility,
not an archetype rule: it needs a live QApplication, a real widget
instance, and a render, so it can only run inside a test. The archetype
is static and must stay that way. ``dev_harness/harness/`` is also
self-protecting and nothing new belongs in it.

``tests/`` has no ``__init__.py``, so under pytest's default prepend
import mode the tests directory is on ``sys.path`` and a sibling test
module imports this as ``from qt_pixel import ...``.

USAGE
=====
    from qt_pixel import assert_pixel_colour, pixel_at, render_widget

    assert_pixel_colour(table, table_cell_centre(table, 0, 0), "#b3261e")

FALSIFICATION
=============
This module is wrong if (a) ``render_widget`` returns an all-default
image because the widget was never polished or sized, in which case
every sample would read the same colour and the checker could not
fail -- ``test_qt_pixel_control.py`` holds the control that proves it
can; (b) the platform plugin is not ``offscreen`` and a real
compositor alters the output; (c) a sampled point lands outside the
rendered image, which raises rather than returning a wrong colour.
"""

from __future__ import annotations

import os

# Must precede any QApplication construction. setdefault, not
# assignment: a caller that has already chosen a platform keeps it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QPoint  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView,
    QApplication,
    QWidget,
)

__all__ = [
    "assert_pixel_colour",
    "ensure_app",
    "pixel_at",
    "render_widget",
    "sample_pixels",
    "table_cell_centre",
]


def ensure_app() -> QCoreApplication:
    """Return the process application object, creating one if absent.

    The declared type is QCoreApplication because that is what
    `QApplication.instance()` is typed to return; a suite that already
    built its own application object keeps it rather than getting a
    second one.
    """
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def render_widget(widget: QWidget, size: tuple[int, int] | None = None) -> QImage:
    """Render `widget` offscreen and return the painted image.

    `ensurePolished` is what applies a stylesheet, and processEvents
    flushes any pending layout. Without both, the grab can capture an
    unstyled or zero-sized widget and every sample reads the same
    default colour -- a checker that cannot fail.
    """
    ensure_app()
    if size is not None:
        widget.resize(size[0], size[1])
    widget.ensurePolished()
    QApplication.processEvents()
    image = widget.grab().toImage()
    if image.isNull() or image.width() == 0 or image.height() == 0:
        raise RuntimeError(
            f"{type(widget).__name__} rendered an empty image "
            f"({image.width()}x{image.height()}); give it a size before "
            "sampling, or the sample proves nothing."
        )
    return image


def pixel_at(image: QImage, point: QPoint) -> str:
    """Return the painted colour at `point` as a lowercase #rrggbb."""
    if not (0 <= point.x() < image.width() and 0 <= point.y() < image.height()):
        raise IndexError(
            f"sample point ({point.x()}, {point.y()}) is outside the "
            f"{image.width()}x{image.height()} render; a point off the "
            "image would silently read as a default colour."
        )
    return QColor(image.pixelColor(point)).name().lower()


def sample_pixels(
    widget: QWidget, points: list[QPoint], size: tuple[int, int] | None = None
) -> list[str]:
    """Render once and return the painted colour at each point."""
    image = render_widget(widget, size=size)
    return [pixel_at(image, p) for p in points]


def table_cell_centre(view: QAbstractItemView, row: int, col: int) -> QPoint:
    """Centre of a cell in viewport coordinates, offset to widget space.

    `visualRect` is viewport-relative; `grab()` on the view captures the
    whole widget including the frame and headers, so the viewport origin
    has to be added back or the sample lands on the wrong cell.
    """
    index = view.model().index(row, col)
    rect = view.visualRect(index)
    origin = view.viewport().mapTo(view, rect.center())
    return QPoint(origin.x(), origin.y())


def assert_pixel_colour(
    widget: QWidget,
    point: QPoint,
    expected_hex: str,
    size: tuple[int, int] | None = None,
    tolerance: int = 0,
) -> str:
    """Assert the RENDERED pixel at `point` matches `expected_hex`.

    `tolerance` is a per-channel 0-255 allowance for antialiasing at an
    edge. It defaults to 0 -- an exact match -- because a wide default
    is how a pixel checker quietly stops being able to fail.

    Returns the sampled colour so a caller can report it.
    """
    image = render_widget(widget, size=size)
    actual = pixel_at(image, point)
    expected = QColor(expected_hex)
    got = QColor(actual)
    deltas = (
        abs(got.red() - expected.red()),
        abs(got.green() - expected.green()),
        abs(got.blue() - expected.blue()),
    )
    if max(deltas) > tolerance:
        raise AssertionError(
            f"rendered pixel at ({point.x()}, {point.y()}) is {actual}, "
            f"expected {expected.name().lower()} "
            f"(per-channel delta {deltas}, tolerance {tolerance}). "
            "The widget model may still report the expected colour; the "
            "screen does not."
        )
    return actual
