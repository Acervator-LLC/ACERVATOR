"""Compare the picture the shipped widget paints with the surface's own.

A parity test proves the Qt-free surface paints what the widget it
replaces paints. The comparison takes one render from each side. Two
renders of the SAME side, one value apart, measure the host's fonts and
its platform style rather than the product: whether the changed value
moves a pixel depends on the machine, so such a comparison passes on one
host and fails on the next. A claim that a value reaches no pixel is
proved by reading that value off both sides, never by a picture.

    from tests.fixtures.surface_pictures import assert_pictures_match

    assert_pictures_match(
        old_side=render_widget(dialog, SIZE),
        new_side=render_widget(built_from_the_payload, SIZE),
    )

Both arguments are keyword-only and named for the side they come from,
so a call carrying two renders of one side reads as the defect it is.
No digest or colour counter is left in a parity module for a test to
reach for.

FALSIFICATION
=============
Wrong if `_picture_digest` returns one value for every image, when
`assert_pictures_differ` could never report. The planted-defect test in
each parity module is the control that proves it can.
"""

from __future__ import annotations

import hashlib

__all__ = ["assert_pictures_differ", "assert_pictures_match"]


def _picture_digest(image) -> str:
    """SHA-256 over every byte the render painted."""
    return hashlib.sha256(bytes(image.constBits())).hexdigest()


def _tail(note: str) -> str:
    return f" [{note}]" if note else ""


def assert_pictures_match(*, old_side, new_side, note: str = "") -> None:
    """Fail unless the two sides painted one size and one set of bytes.

    `old_side` is the render of the shipped widget, `new_side` the render
    of a widget built only from the surface's view model.
    """
    if old_side.size() != new_side.size():
        raise AssertionError(
            f"the two sides rendered at different sizes{_tail(note)}: "
            f"old {old_side.width()}x{old_side.height()}, "
            f"new {new_side.width()}x{new_side.height()}"
        )
    old_digest = _picture_digest(old_side)
    new_digest = _picture_digest(new_side)
    if old_digest != new_digest:
        raise AssertionError(
            f"the surface painted a different picture than the widget"
            f"{_tail(note)}: old {old_digest}, new {new_digest}"
        )


def assert_pictures_differ(*, old_side, new_side, note: str = "") -> None:
    """Fail unless the two sides painted different bytes.

    Used with a planted defect on the new side: a pass means the picture
    comparison can report that defect rather than passing whatever the
    second side paints.
    """
    old_digest = _picture_digest(old_side)
    if old_digest == _picture_digest(new_side):
        raise AssertionError(
            f"the planted defect changed no pixel{_tail(note)}: both sides "
            f"painted {old_digest}, so the picture comparison would pass "
            "whatever the surface painted"
        )
