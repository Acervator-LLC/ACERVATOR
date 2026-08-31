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

`assert_same_skin` answers "do these two sides carry the same skin?"
with renders alone, so no test needs to read `styleSheet()`, `palette()`
or a property off a live widget. It takes a builder for each side, not a
widget, because it renders each side more than once.

    from tests.fixtures.surface_pictures import assert_same_skin

    assert_same_skin(
        build_old_side=lambda: old_picture_tab("happy"),
        build_new_side=lambda: new_picture_tab("happy"),
        size=PIXEL_SIZE,
        control_rule="QTableWidget { background: #3a1414; }",
    )

Three renders, in this order. The two sides plain must paint one
picture. A third widget from the new builder, carrying `control_rule`,
must paint a different one. A fourth widget from that builder, with no
rule, must paint the first picture again.

`colour_count` and `assert_picture_can_report` are the refusal every
one of those renders passes first: a window that paints one colour
paints the same picture whatever it was told to show, so a comparison
of it reports nothing. `assert_cases_paint_differently` is the control
that feeds two genuinely different real inputs, one from each side, and
requires two pictures.

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
refuse; `tests/test_surface_picture_seal.py` holds that control. Wrong
also if `colour_count` returns a number above one for a render that
painted one colour, when `assert_picture_can_report` could never
refuse, or if a widget carrying `control_rule` paints the picture it
paints without one, when `assert_same_skin` reports nothing;
`tests/test_surface_skin_compare.py` holds both controls.
"""

from __future__ import annotations

import hashlib

__all__ = [
    "assert_cases_paint_differently",
    "assert_picture_can_report",
    "assert_pictures_differ",
    "assert_pictures_match",
    "assert_same_skin",
    "colour_count",
    "sealed",
    "unaltered",
]

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


def _side_note(side: str, note: str) -> str:
    return f"{side}, {note}" if note else side


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


def colour_count(image) -> int:
    """How many distinct colours a render painted.

    Derives the bytes per pixel from the image and steps over the row
    padding, so a platform that pads a scan line does not count a
    padding byte as a colour.
    """
    depth_bits = image.depth()
    if depth_bits % 8:
        raise AssertionError(
            f"this render is {depth_bits} bits per pixel, which does not "
            "divide into whole bytes, so its colours cannot be counted."
        )
    step = depth_bits // 8
    data = bytes(image.constBits())
    stride = image.bytesPerLine()
    painted: set[bytes] = set()
    for row in range(image.height()):
        start = row * stride
        line = data[start : start + image.width() * step]
        painted.update(line[at : at + step] for at in range(0, len(line), step))
    return len(painted)


def assert_picture_can_report(image, *, note: str = "") -> int:
    """Fail unless the render painted more than one colour.

    A window that paints one colour paints that picture whatever it was
    told to show, so a comparison against it passes whatever the other
    side painted. Returns the count so a caller can report it.
    """
    found = colour_count(image)
    if found < 2:
        raise AssertionError(
            f"this render painted {found} colour{_tail(note)}, so it paints "
            "the same picture whatever the widget was told to show and no "
            "comparison of it can report. Give the widget its data and a "
            "size that shows it before comparing."
        )
    return found


def assert_cases_paint_differently(*, old_side, new_side, note: str = "") -> None:
    """Fail unless two different real inputs painted different pictures.

    `old_side` is the render of the shipped widget for one case and
    `new_side` the render of the surface's widget for another. Each
    render is refused first if it painted one colour: two flat windows
    differ for no reason the product decided.
    """
    assert_picture_can_report(old_side, note=_side_note("old side", note))
    assert_picture_can_report(new_side, note=_side_note("new side", note))
    assert_pictures_differ(old_side=old_side, new_side=new_side, note=note)


def assert_same_skin(
    *,
    build_old_side,
    build_new_side,
    size: tuple[int, int],
    control_rule: str,
    note: str = "",
) -> None:
    """Fail unless both sides carry one skin, proved by rendered pixels.

    `build_old_side` and `build_new_side` each return a fresh widget for
    the same case; each is called more than once, so a widget passed in
    place of a builder is refused. `size` is the render size both sides
    get. `control_rule` is a style sheet rule NEITHER side sets.

    Three checks, in this order. The two sides plain must paint one
    picture. A widget from `build_new_side` carrying `control_rule` must
    paint a different one, which is what proves this run can see a skin
    at all. A later widget from `build_new_side`, with no rule, must
    paint the first picture again, which is what proves the rule reached
    only the widget it was applied to. That last pair is two renders of
    one side, and it is sound only because the control render already
    reported.

    Nothing here reads a style, a palette or a property off a live
    widget: the answer comes from the pixels each render painted.
    """
    if not callable(build_old_side) or not callable(build_new_side):
        raise AssertionError(
            f"assert_same_skin takes a builder for each side{_tail(note)}, "
            "not a widget and not a render: it builds each side more than "
            "once. Pass a callable that returns a fresh widget."
        )
    if not control_rule:
        raise AssertionError(
            f"assert_same_skin needs a control rule{_tail(note)}: without "
            "one the control render is the plain render and the check "
            "reports nothing. Pass a style sheet rule neither side sets."
        )

    from tests.qt_pixel import render_widget

    plain_old = render_widget(build_old_side(), size)
    plain_new = render_widget(build_new_side(), size)
    assert_picture_can_report(plain_old, note=_side_note("old side", note))
    assert_picture_can_report(plain_new, note=_side_note("new side", note))
    assert_pictures_match(old_side=plain_old, new_side=plain_new, note=note)

    skinned = build_new_side()
    skinned.setStyleSheet(control_rule)
    assert_pictures_differ(
        old_side=plain_old,
        new_side=render_widget(skinned, size),
        note=_side_note(f"control rule {control_rule!r}", note),
    )

    after_control = render_widget(build_new_side(), size)
    if _picture_digest(plain_new) != _picture_digest(after_control):
        raise AssertionError(
            f"the control rule {control_rule!r} outlived the widget it was "
            f"applied to{_tail(note)}: a later widget from the same builder "
            f"painted {_picture_digest(after_control)} where the first "
            f"painted {_picture_digest(plain_new)}. Every render after this "
            "one carries the rule."
        )
