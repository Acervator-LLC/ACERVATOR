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

`sealed` and `unaltered` are the stamp that keeps an altered payload out
of a render. A payload producer returns `sealed(payload)` as the payload
comes off the widget or off the surface. The builder that turns a
payload into a widget starts with `unaltered(payload)`, which refuses a
payload that was never sealed and refuses one whose content moved after
the seal. A test that wants to render a value it changed has no payload
the builder accepts.

    def model_payload(spec):
        return sealed(surface.build_view_model(...))

    def dialog_painted_by_the_model(payload):
        payload = unaltered(payload)
        ...

FALSIFICATION
=============
Wrong if `_picture_digest` returns one value for every image, when
`assert_pictures_differ` could never report. Each parity module holds a
control that renders two different real inputs, one from each side, and
proves the comparison reports them. Wrong also if `_content_digest`
returns one value for every payload, when `unaltered` could never
refuse; `tests/test_surface_picture_seal.py` holds that control.
"""

from __future__ import annotations

import hashlib

__all__ = ["assert_pictures_differ", "assert_pictures_match", "sealed", "unaltered"]

_STAMPS: dict[int, str] = {}
_SEALED: list[object] = []


def _picture_digest(image) -> str:
    """SHA-256 over every byte the render painted."""
    return hashlib.sha256(bytes(image.constBits())).hexdigest()


def _canonical(value):
    """`value` as nested lists of text, ordered so a swap changes it."""
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: repr(item[0]))
        return [[repr(key), _canonical(inner)] for key, inner in pairs]
    if isinstance(value, (list, tuple)):
        return [_canonical(inner) for inner in value]
    return repr(value)


def _content_digest(payload) -> str:
    """SHA-256 over every value the payload carries, at every depth."""
    return hashlib.sha256(repr(_canonical(payload)).encode("utf-8")).hexdigest()


def sealed(payload):
    """Stamp `payload` with its content and return it unchanged.

    Called by a payload producer as the payload comes off the shipped
    widget or off the surface. The payload is kept alive so its identity
    cannot be handed to a later object.
    """
    _STAMPS[id(payload)] = _content_digest(payload)
    _SEALED.append(payload)
    return payload


def unaltered(payload):
    """Return `payload` if it still carries the stamp `sealed` gave it.

    Called by a builder before it paints a widget from a payload. Raises
    when the payload never came off a side, and when a value inside it
    moved after the seal.
    """
    stamp = _STAMPS.get(id(payload))
    if stamp is None:
        raise AssertionError(
            "this payload never came off the widget or off the surface, so "
            "a render of it measures neither side. Take the payload from "
            "the producer that seals it."
        )
    now = _content_digest(payload)
    if stamp != now:
        raise AssertionError(
            "this payload was altered after it came off the widget or off "
            f"the surface: sealed {stamp}, now {now}. A render of a changed "
            "payload measures the host's fonts, not the product. Read the "
            "changed value off both sides instead."
        )
    return payload


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

    Used with two different real inputs, one taken from each side: a
    pass means the picture comparison reports a difference rather than
    passing whatever the second side paints.
    """
    old_digest = _picture_digest(old_side)
    if old_digest == _picture_digest(new_side):
        raise AssertionError(
            f"the two real inputs painted one picture{_tail(note)}: both "
            f"sides painted {old_digest}, so the picture comparison would "
            "pass whatever the surface painted"
        )
