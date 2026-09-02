"""The Qt Smart Wire overlay and the Qt-free surface, driven side by side.

A failure means the view model describes a different curve, colour,
width, radius, angle, badge, drawing order, mouse route or branch than
``_WireCanvas`` builds on the same input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import wire_canvas_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CANVAS_SOURCE = REPO_ROOT / "src" / "gui" / "visualizer" / "wire_canvas.py"
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"

CANVAS_SIZE = (420, 300)

CONNECT_TOTAL = 0
SIGNAL_TOTAL = 0
TIMER_TOTAL = 0
BUS_TOPIC_TOTAL = 0
SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 6
SURFACE_CLASS_TOTAL = 2
PAYLOAD_KEY_TOTAL = 33
CONSTANT_TOTAL = 130
WIRE_CALL_TOTAL = 19


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def canonical(value):
    """`value` as nested lists of text, so two not-a-numbers compare equal.

    A drawing call can carry a not-a-number coordinate, and Python holds
    that such a value is unequal to itself. Reading every number as its
    own text lets the two sides be compared while keeping a whole number
    apart from a decimal one.
    """
    if isinstance(value, dict):
        return [[repr(key), canonical(inner)] for key, inner in sorted(value.items())]
    if isinstance(value, (list, tuple)):
        return [canonical(inner) for inner in value]
    return repr(value)


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(canonical(value), sort_keys=True, ensure_ascii=True).encode("utf-8")
    ).hexdigest()


# ---------------------------------------------------------------------
# The inputs. One table for the tab the sheet reads, one for the mouse.
# ---------------------------------------------------------------------


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "30 交易 ₿"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "the operator's share"

ALPHA = (40.0, 60.0)
BETA = (220.0, 150.0)
GAMMA = (300.0, 40.0)
CENTRES = {"alpha": ALPHA, "beta": BETA, "gamma": GAMMA}


def hit(x, y):
    """The lookup key the tab stub holds one point under."""
    return surface.point_key((x, y))


def wire(source_id="alpha", target_id="beta", **named):
    """One wire of the shape the visualizer tab keeps."""
    row = {"source_id": source_id, "target_id": target_id, "pct": 30, "phase": 0.5}
    row.update(named)
    return row


TWO_WIRES = [wire(), wire("beta", "gamma", pct=70, phase=2.0)]
OFFSETS = {"alpha->beta": 25.0, "beta->gamma": -18.0}


def tab_spec(**named):
    """One set of the values the sheet reads off the visualizer tab."""
    spec = {
        "wires": [dict(one) for one in TWO_WIRES],
        "bot_centers": dict(CENTRES),
        "wire_offsets": dict(OFFSETS),
        "bot_hits": {hit(*ALPHA): "alpha", hit(150.0, 120.0): "beta"},
        "wire_hits": {hit(100.0, 100.0): 0},
        "theme_key": "quantum",
        "wire_opacity_pct": 80,
    }
    spec.update(named)
    return spec


def dragging(**named):
    """A tab spec with a wire being dragged out of the first bot."""
    spec = {
        "dragging_wire": True,
        "wire_start_id": "alpha",
        "wire_mouse_pos": (150.0, 120.0),
    }
    spec.update(named)
    return tab_spec(**spec)


TAB_SPECS = {
    "happy_two_wires": tab_spec(),
    "one_wire": tab_spec(wires=[wire()]),
    "no_wires_and_no_drag": tab_spec(wires=[]),
    "empty_everywhere": {},
    "a_wire_whose_bot_is_missing": tab_spec(wires=[wire("alpha", "nowhere")]),
    "a_bot_at_the_origin": tab_spec(bot_centers=dict(CENTRES, alpha=(0.0, 0.0))),
    "a_bot_at_infinity": tab_spec(
        wires=[wire()], bot_centers=dict(CENTRES, alpha=(math.inf, 60.0))
    ),
    "a_bot_at_not_a_number": tab_spec(
        wires=[wire()], bot_centers=dict(CENTRES, beta=(math.nan, 60.0))
    ),
    "an_empty_bot_name": tab_spec(wires=[wire(source_id="")]),
    "zero_percent": tab_spec(wires=[wire(pct=0)]),
    "negative_percent": tab_spec(wires=[wire(pct=-25)]),
    "a_thousand_million_percent": tab_spec(wires=[wire(pct=1_000_000_000)]),
    "one_billionth_percent": tab_spec(wires=[wire(pct=1e-9)]),
    "infinity_percent": tab_spec(wires=[wire(pct=math.inf)]),
    "minus_infinity_percent": tab_spec(wires=[wire(pct=-math.inf)]),
    "not_a_number_percent": tab_spec(wires=[wire(pct=math.nan)]),
    "unicode_percent": tab_spec(wires=[wire(pct=UNICODE_TEXT)]),
    "two_hundred_characters_percent": tab_spec(wires=[wire(pct=LONG_TEXT)]),
    "markup_inside_the_percent": tab_spec(wires=[wire(pct=MARKUP_TEXT)]),
    "an_apostrophe_in_the_percent": tab_spec(wires=[wire(pct=APOSTROPHE_TEXT)]),
    "a_newline_in_the_percent": tab_spec(wires=[wire(pct=NEWLINE_TEXT)]),
    "text_where_a_percent_belongs": tab_spec(wires=[wire(pct="fifty")]),
    "no_percent_at_all": tab_spec(wires=[{"source_id": "alpha", "target_id": "beta"}]),
    "zero_phase": tab_spec(wires=[wire(phase=0)]),
    "negative_phase": tab_spec(wires=[wire(phase=-3.5)]),
    "a_thousand_million_phase": tab_spec(wires=[wire(phase=1_000_000_000)]),
    "one_billionth_phase": tab_spec(wires=[wire(phase=1e-9)]),
    "infinity_phase": tab_spec(wires=[wire(phase=math.inf)]),
    "minus_infinity_phase": tab_spec(wires=[wire(phase=-math.inf)]),
    "not_a_number_phase": tab_spec(wires=[wire(phase=math.nan)]),
    "text_where_a_phase_belongs": tab_spec(wires=[wire(phase="half")]),
    "zero_offset": tab_spec(wire_offsets={}),
    "negative_offset": tab_spec(wire_offsets={"alpha->beta": -90.0}),
    "one_billionth_offset": tab_spec(
        wires=[wire()], wire_offsets={"alpha->beta": 1e-9}
    ),
    "infinity_offset": tab_spec(wires=[wire()], wire_offsets={"alpha->beta": math.inf}),
    "text_where_an_offset_belongs": tab_spec(
        wires=[wire()], wire_offsets={"alpha->beta": "far"}
    ),
    "zero_opacity": tab_spec(wire_opacity_pct=0),
    "negative_opacity": tab_spec(wire_opacity_pct=-40),
    "opacity_above_one_hundred": tab_spec(wire_opacity_pct=250),
    "a_thousand_million_opacity": tab_spec(wire_opacity_pct=1_000_000_000),
    "one_billionth_opacity": tab_spec(wire_opacity_pct=1e-9),
    "opacity_written_as_text": tab_spec(wire_opacity_pct="60"),
    "opacity_as_a_flag": tab_spec(wire_opacity_pct=True),
    "text_where_an_opacity_belongs": tab_spec(wire_opacity_pct="loud"),
    "nothing_where_an_opacity_belongs": tab_spec(wire_opacity_pct=None),
    "infinity_opacity": tab_spec(wire_opacity_pct=math.inf),
    "minus_infinity_opacity": tab_spec(wire_opacity_pct=-math.inf),
    "not_a_number_opacity": tab_spec(wire_opacity_pct=math.nan),
    "theme_nebula": tab_spec(theme_key="nebula"),
    "theme_matrix": tab_spec(theme_key="matrix"),
    "theme_ocean": tab_spec(theme_key="ocean"),
    "theme_in_wrong_capitals": tab_spec(theme_key="QUANTUM"),
    "a_theme_that_names_nothing": tab_spec(theme_key="starfield"),
    "a_number_where_a_theme_belongs": tab_spec(theme_key=42),
    "nothing_where_a_theme_belongs": tab_spec(theme_key=None),
    "a_list_where_a_theme_belongs": tab_spec(theme_key=["quantum"]),
    "dragging_over_empty_space": dragging(wire_mouse_pos=(310.0, 260.0)),
    "dragging_over_a_new_bot": dragging(bot_hits={hit(150.0, 120.0): "gamma"}),
    "dragging_over_a_connected_bot": dragging(
        bot_hits={hit(150.0, 120.0): "beta"}, wire_mouse_pos=(150.0, 120.0)
    ),
    "dragging_back_to_the_same_bot": dragging(
        bot_hits={hit(150.0, 120.0): "alpha"}, wire_mouse_pos=(150.0, 120.0)
    ),
    "dragging_with_no_mouse_position": dragging(wire_mouse_pos=None),
    "dragging_from_the_origin": dragging(
        bot_centers=dict(CENTRES, alpha=(0.0, 0.0)), wire_mouse_pos=(150.0, 120.0)
    ),
    "dragging_from_a_missing_bot": dragging(wire_start_id="nowhere"),
    "dragging_to_the_origin": dragging(wire_mouse_pos=(0.0, 0.0)),
    "dragging_with_no_wires": dragging(wires=[]),
    "a_second_wire_refuses_after_the_first_paints": tab_spec(
        wires=[wire(), wire("beta", "gamma", phase="half")]
    ),
    "a_second_wire_refuses_on_its_offset": tab_spec(
        wires=[wire(), wire("beta", "gamma")],
        wire_offsets={"alpha->beta": 25.0, "beta->gamma": "far"},
    ),
}

TAB_NAMES = sorted(TAB_SPECS)

# Every tab the shipped sheet refuses, and the surface with it.
REFUSING_TAB_SPECS = (
    "a_list_where_a_theme_belongs",
    "a_second_wire_refuses_after_the_first_paints",
    "a_second_wire_refuses_on_its_offset",
    "infinity_opacity",
    "infinity_phase",
    "minus_infinity_opacity",
    "minus_infinity_phase",
    "not_a_number_opacity",
    "nothing_where_an_opacity_belongs",
    "text_where_a_phase_belongs",
    "text_where_an_offset_belongs",
    "text_where_an_opacity_belongs",
)

PRESS = surface.PRESS_EVENT
MOVE = surface.MOVE_EVENT
RELEASE = surface.RELEASE_EVENT
LEFT = surface.LEFT_BUTTON
RIGHT = surface.RIGHT_BUTTON
MIDDLE = surface.MIDDLE_BUTTON
NONE = surface.NO_BUTTON

EVENT_SPECS = {
    "nothing_touched": [],
    "a_move_over_a_wire": [[MOVE, NONE, 100.0, 100.0]],
    "a_move_over_empty_space": [[MOVE, NONE, 5.0, 5.0]],
    "a_left_press_on_a_bot": [[PRESS, LEFT, 40.0, 60.0]],
    "a_left_press_on_empty_space": [[PRESS, LEFT, 5.0, 5.0]],
    "a_right_press_on_a_wire": [[PRESS, RIGHT, 100.0, 100.0]],
    "a_right_press_on_empty_space": [[PRESS, RIGHT, 5.0, 5.0]],
    "a_middle_press": [[PRESS, MIDDLE, 40.0, 60.0]],
    "a_release_with_no_drag": [[RELEASE, LEFT, 40.0, 60.0]],
    "a_whole_drag": [
        [PRESS, LEFT, 40.0, 60.0],
        [MOVE, NONE, 150.0, 120.0],
        [RELEASE, LEFT, 220.0, 150.0],
    ],
    "a_drag_released_on_the_wrong_button": [
        [PRESS, LEFT, 40.0, 60.0],
        [RELEASE, RIGHT, 220.0, 150.0],
    ],
    "a_move_over_a_wire_then_empty_space": [
        [MOVE, NONE, 100.0, 100.0],
        [MOVE, NONE, 5.0, 5.0],
    ],
    "two_left_presses_in_a_row": [
        [PRESS, LEFT, 40.0, 60.0],
        [PRESS, LEFT, 40.0, 60.0],
    ],
    "a_move_after_a_press_that_did_nothing": [
        [PRESS, LEFT, 5.0, 5.0],
        [MOVE, NONE, 100.0, 100.0],
    ],
    "a_drag_then_a_move_over_a_wire": [
        [PRESS, LEFT, 40.0, 60.0],
        [MOVE, NONE, 150.0, 120.0],
        [RELEASE, LEFT, 150.0, 120.0],
        [MOVE, NONE, 100.0, 100.0],
    ],
    "a_right_press_during_a_drag": [
        [PRESS, LEFT, 40.0, 60.0],
        [PRESS, RIGHT, 100.0, 100.0],
    ],
}

EVENT_NAMES = sorted(EVENT_SPECS)


# ---------------------------------------------------------------------
# The visualizer tab both sides are driven against
# ---------------------------------------------------------------------


def driven_tab_class():
    """A stand-in visualizer tab wearing both sides' names at once.

    The sheet is the code under test; the tab it reads is the outward
    edge. One store answers both sides, so a difference between them is
    the sheet's and never the input's. The Qt side is asked in points
    and the surface side in pairs of numbers, and both reach the same
    store and the same record of what was asked.
    """
    from PySide6.QtCore import QPointF
    from PySide6.QtWidgets import QWidget

    class DrivenTab(QWidget):
        """The visualizer tab as the shipped sheet reaches it."""

        def __init__(self, **spec):
            super().__init__()
            self.setAccessibleName("Driven Visualizer Tab")
            self.store = surface.CanvasTabState(**spec)

        @property
        def _wires(self):
            return self.store.wires

        @property
        def _dragging_wire(self):
            return self.store.dragging_wire

        @property
        def _wire_start_id(self):
            return self.store.wire_start_id

        @property
        def _wire_mouse_pos(self):
            pos = self.store.wire_mouse_pos
            return None if pos is None else QPointF(pos[0], pos[1])

        @property
        def _theme_key(self):
            return self.store.theme_key

        @property
        def _wire_opacity_pct(self):
            return self.store.wire_opacity_pct

        def _get_bot_center(self, bot_id):
            found = self.store.bot_center(bot_id)
            return None if found is None else QPointF(found[0], found[1])

        def _bot_at_pos(self, pos):
            return self.store.bot_at_pos((pos.x(), pos.y()))

        def _wire_at_pos(self, pos):
            return self.store.wire_at_pos((pos.x(), pos.y()))

        def _get_wire_offset(self, wire_row):
            return self.store.wire_offset(wire_row)

        def _start_wire_drag(self, bot_id, pos):
            self.store.start_wire_drag(bot_id, (pos.x(), pos.y()))

        def _update_wire_drag(self, pos):
            self.store.update_wire_drag((pos.x(), pos.y()))

        def _finish_wire_drag(self, pos):
            self.store.finish_wire_drag((pos.x(), pos.y()))

        def _show_disconnect_menu(self, pos, wire_row):
            self.store.show_disconnect_menu((pos.x(), pos.y()), wire_row)

    return DrivenTab


# ---------------------------------------------------------------------
# The painter the shipped sheet draws through
# ---------------------------------------------------------------------


def colour_of(value):
    """One Qt colour as its four numbers."""
    return [value.red(), value.green(), value.blue(), value.alpha()]


def path_of(path):
    """One Qt curve as the list of points the drawing library keeps."""
    from PySide6.QtGui import QPainterPath

    names = {
        QPainterPath.ElementType.MoveToElement: surface.MOVE_TO_ELEMENT,
        QPainterPath.ElementType.CurveToElement: surface.CURVE_TO_ELEMENT,
        QPainterPath.ElementType.CurveToDataElement: surface.CURVE_TO_DATA_ELEMENT,
    }
    found = []
    for index in range(path.elementCount()):
        element = path.elementAt(index)
        found.append([names[element.type], element.x, element.y])
    return found


def rect_of(rect):
    """One Qt rectangle as its four numbers."""
    return [rect.x(), rect.y(), rect.width(), rect.height()]


def new_image():
    """One empty picture of the size the sheet is drawn at."""
    from PySide6.QtGui import QImage

    image = QImage(
        CANVAS_SIZE[0], CANVAS_SIZE[1], QImage.Format.Format_ARGB32_Premultiplied
    )
    image.fill(0)
    return image


def recorder_class(image):
    """A painter that keeps every drawing call and still paints `image`.

    The sheet builds its own painter, so the painter is the one part
    swapped: everything the sheet works out reaches this unchanged. A
    pen given as a bare style carries no colour and no width, which is
    recorded as nothing and zero.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QBrush, QPainter, QPen

    class RecordingPainter:
        """Records the drawing calls the sheet makes and forwards them."""

        Antialiasing = QPainter.RenderHint.Antialiasing

        def __init__(self, _device):
            self.painter = QPainter(image)
            self.calls = []

        def setRenderHint(self, hint):
            self.calls.append([surface.SET_RENDER_HINT, hint.name, int(hint.value)])
            self.painter.setRenderHint(hint)

        def setOpacity(self, value):
            self.calls.append([surface.SET_OPACITY, value])
            self.painter.setOpacity(value)

        def setPen(self, pen):
            if isinstance(pen, QPen):
                self.calls.append(
                    [
                        surface.SET_PEN,
                        colour_of(pen.color()),
                        pen.width(),
                        pen.style().name,
                    ]
                )
            else:
                self.calls.append([surface.SET_PEN, None, 0, pen.name])
            self.painter.setPen(pen)

        def setBrush(self, brush):
            gradient = brush.gradient() if isinstance(brush, QBrush) else None
            if gradient is not None:
                self.calls.append(
                    [
                        surface.SET_GRADIENT_BRUSH,
                        [gradient.center().x(), gradient.center().y()],
                        gradient.radius(),
                        [
                            [stop, colour_of(colour)]
                            for stop, colour in gradient.stops()
                        ],
                    ]
                )
            elif isinstance(brush, QBrush):
                self.calls.append([surface.SET_BRUSH, colour_of(brush.color())])
            else:
                self.calls.append([surface.SET_BRUSH, brush.name])
            self.painter.setBrush(brush)

        def setFont(self, font):
            self.calls.append(
                [surface.SET_FONT, font.family(), font.pointSize(), font.weight().name]
            )
            self.painter.setFont(font)

        def fontMetrics(self):
            return self.painter.fontMetrics()

        def drawPath(self, path):
            self.calls.append([surface.DRAW_PATH, path_of(path)])
            self.painter.drawPath(path)

        def drawEllipse(self, centre, rx, ry):
            self.calls.append([surface.DRAW_ELLIPSE, [centre.x(), centre.y()], rx, ry])
            self.painter.drawEllipse(centre, rx, ry)

        def drawPolygon(self, polygon):
            self.calls.append(
                [surface.DRAW_POLYGON, [[one.x(), one.y()] for one in polygon]]
            )
            self.painter.drawPolygon(polygon)

        def drawRoundedRect(self, rect, x_radius, y_radius):
            self.calls.append(
                [surface.DRAW_ROUNDED_RECT, rect_of(rect), x_radius, y_radius]
            )
            self.painter.drawRoundedRect(rect, x_radius, y_radius)

        def drawText(self, rect, alignment, text):
            self.calls.append(
                [
                    surface.DRAW_TEXT,
                    rect_of(rect),
                    Qt.AlignmentFlag(alignment).name,
                    text,
                ]
            )
            self.painter.drawText(rect, alignment, text)

        def drawLine(self, start, end):
            self.calls.append(
                [surface.DRAW_LINE, [start.x(), start.y()], [end.x(), end.y()]]
            )
            self.painter.drawLine(start, end)

        def end(self):
            self.calls.append([surface.END_PAINTER])
            self.painter.end()

    return RecordingPainter


# ---------------------------------------------------------------------
# The drawing engine both sides are given
# ---------------------------------------------------------------------


def qt_sample(src, control, tgt, percent):
    """The point at `percent` along the curve, from the drawing library."""
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QPainterPath

    path = QPainterPath()
    path.moveTo(QPointF(src[0], src[1]))
    path.quadTo(QPointF(control[0], control[1]), QPointF(tgt[0], tgt[1]))
    point = path.pointAtPercent(percent)
    return [point.x(), point.y()]


def qt_advance(label):
    """The printed width of one badge label, from the font engine."""
    from PySide6.QtGui import QFont, QFontMetrics

    app()
    font = QFont(surface.FONT_FAMILY, surface.FONT_SIZE_PT, QFont.Weight.Bold)
    return QFontMetrics(font).horizontalAdvance(label)


# ---------------------------------------------------------------------
# Driving the two sides
# ---------------------------------------------------------------------


def qt_event(kind, button, x, y):
    """One Qt mouse event of the kind, button and position named."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    types_by_kind = {
        surface.PRESS_EVENT: QEvent.Type.MouseButtonPress,
        surface.MOVE_EVENT: QEvent.Type.MouseMove,
        surface.RELEASE_EVENT: QEvent.Type.MouseButtonRelease,
    }
    buttons = {
        surface.LEFT_BUTTON: Qt.MouseButton.LeftButton,
        surface.RIGHT_BUTTON: Qt.MouseButton.RightButton,
        surface.MIDDLE_BUTTON: Qt.MouseButton.MiddleButton,
        surface.NO_BUTTON: Qt.MouseButton.NoButton,
    }
    event = QMouseEvent(
        types_by_kind[kind],
        QPointF(x, y),
        QPointF(x, y),
        buttons[button],
        buttons[button],
        Qt.KeyboardModifier.NoModifier,
    )
    event.setAccepted(True)
    return event


HANDLER_NAMES = {
    surface.PRESS_EVENT: "mousePressEvent",
    surface.MOVE_EVENT: "mouseMoveEvent",
    surface.RELEASE_EVENT: "mouseReleaseEvent",
}
BASE_MARKS = {
    surface.PRESS_EVENT: surface.BASE_PRESS,
    surface.MOVE_EVENT: surface.BASE_MOVE,
    surface.RELEASE_EVENT: surface.BASE_RELEASE,
}


def old_canvas(spec):
    """The shipped sheet over a stand-in visualizer tab."""
    from src.gui.visualizer import wire_canvas as shipped

    app()
    tab = driven_tab_class()(**spec)
    canvas = shipped._WireCanvas(tab)
    canvas.resize(*CANVAS_SIZE)
    return canvas, tab


def old_attributes(canvas):
    """The window attributes the shipped sheet turned on."""
    from PySide6.QtCore import Qt

    flag = Qt.WidgetAttribute.WA_TranslucentBackground
    if not canvas.testAttribute(flag):
        return []
    return [[flag.name, int(flag.value)]]


def old_route(canvas, tab, events):
    """Run the mouse events on the shipped sheet and record the route."""
    from PySide6.QtCore import Qt

    composed = []
    for kind, button, x, y in events:
        tab.store.calls = []
        canvas.unsetCursor()
        event = qt_event(kind, button, x, y)
        getattr(canvas, HANDLER_NAMES[kind])(event)
        composed.extend(tab.store.calls)
        if canvas.testAttribute(Qt.WidgetAttribute.WA_SetCursor):
            composed.append([surface.SET_CURSOR, canvas.cursor().shape().name])
        if not event.isAccepted():
            composed.append([BASE_MARKS[kind]])
    return composed


def old_paint(canvas, tab, image):
    """Run one paint of the shipped sheet through the recording painter."""
    from src.gui.visualizer import wire_canvas as shipped

    held = {}
    recorder = recorder_class(image)

    class Catcher(recorder):
        """Keeps the painter the sheet built so its calls can be read."""

        def __init__(self, device):
            super().__init__(device)
            held["painter"] = self

    was = shipped.QPainter
    shipped.QPainter = Catcher
    tab.store.calls = []
    try:
        canvas.paintEvent(None)
    finally:
        shipped.QPainter = was
        painter = held.get("painter")
        if painter is not None and painter.painter.isActive():
            painter.painter.end()
    painter = held.get("painter")
    return (painter.calls if painter is not None else []), list(tab.store.calls)


def old_trace(spec, events=(), image=None):
    """Every value the shipped sheet can be asked for, as plain data."""
    canvas, tab = old_canvas(spec)
    route = old_route(canvas, tab, events)
    drawing, paint_asks = old_paint(
        canvas, tab, image if image is not None else new_image()
    )
    from PySide6.QtCore import Qt

    cursor = (
        canvas.cursor().shape().name
        if canvas.testAttribute(Qt.WidgetAttribute.WA_SetCursor)
        else None
    )
    return {
        "accessible_name": canvas.accessibleName(),
        "style_sheet": canvas.styleSheet(),
        "attributes": old_attributes(canvas),
        "cursor": cursor,
        "route": route,
        "drawing_calls": drawing,
        "paint_asks": paint_asks,
        "tab": tab.store.state()["dragging_wire"],
        "tab_start_id": tab.store.wire_start_id,
        "tab_mouse_pos": (
            None if tab.store.wire_mouse_pos is None else list(tab.store.wire_mouse_pos)
        ),
    }


def new_trace(spec, events=()):
    """The same values, read from the Qt-free view model."""
    tab = surface.CanvasTabState(**spec)
    model = surface.WireCanvasModel(tab)
    route = []
    for event in events:
        tab.calls = []
        before = len(model.calls)
        model.apply([event])
        route.extend(tab.calls)
        route.extend(model.calls[before:])
    tab.calls = []
    payload = surface.build_view_model(model, None, qt_sample, qt_advance)
    return {
        "accessible_name": payload["accessible_name"],
        "style_sheet": payload["style_sheet"],
        "attributes": payload["attributes"],
        "cursor": payload["cursor"],
        "route": route,
        "drawing_calls": payload["drawing_calls"],
        "paint_asks": payload["tab"]["calls"],
        "tab": payload["tab"]["dragging_wire"],
        "tab_start_id": payload["tab"]["wire_start_id"],
        "tab_mouse_pos": payload["tab"]["wire_mouse_pos"],
    }


def outcome(work) -> dict:
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {
            "outcome": "refused",
            "error": type(exc).__name__,
            "message": str(exc),
        }


def old_outcome(spec, events=()):
    return outcome(lambda: old_trace(spec, events))


def new_outcome(spec, events=()):
    return outcome(lambda: new_trace(spec, events))


def partial_old(spec, events=()):
    """The drawing calls the shipped sheet made before it refused.

    Returns the calls, the picture and the name of the refusal, or
    nothing when the sheet drew the whole sheet.
    """
    from src.gui.visualizer import wire_canvas as shipped

    canvas, tab = old_canvas(spec)
    old_route(canvas, tab, events)
    image = new_image()
    held = {}
    recorder = recorder_class(image)

    class Catcher(recorder):
        """Keeps the painter the sheet built so its calls can be read."""

        def __init__(self, device):
            super().__init__(device)
            held["painter"] = self

    was = shipped.QPainter
    shipped.QPainter = Catcher
    refusal = None
    try:
        canvas.paintEvent(None)
    except Exception as exc:
        refusal = type(exc).__name__
    finally:
        shipped.QPainter = was
        painter = held.get("painter")
        if painter is not None and painter.painter.isActive():
            painter.painter.end()
    painter = held.get("painter")
    return (painter.calls if painter is not None else []), image, refusal


def partial_new(spec, events=()):
    """The drawing calls the surface made before it refused."""
    tab = surface.CanvasTabState(**spec)
    model = surface.WireCanvasModel(tab)
    if events:
        model.apply(events)
    refusal = None
    try:
        model.paint(qt_sample, qt_advance)
    except Exception as exc:
        refusal = type(exc).__name__
    return [list(one) for one in model.draw_calls], refusal


# ---------------------------------------------------------------------
# The two sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", TAB_NAMES)
def test_the_two_sides_draw_the_same_sheet(name):
    """A coordinate, colour, width, radius, badge or drawing order differs."""
    spec = TAB_SPECS[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    assert canonical(new["value"]) == canonical(old["value"]), name
    assert digest(new["value"]) == digest(old["value"]), name


@pytest.mark.parametrize("name", EVENT_NAMES)
def test_the_two_sides_route_the_same_mouse(name):
    """A mouse route, cursor or drag the sheet started differs between them."""
    events = EVENT_SPECS[name]
    spec = TAB_SPECS["happy_two_wires"]
    old = old_outcome(spec, events)
    new = new_outcome(spec, events)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        assert new["message"] == old["message"], (name, old, new)
        return
    assert canonical(new["value"]) == canonical(old["value"]), name
    assert digest(new["value"]) == digest(old["value"]), name


@pytest.mark.parametrize("name", EVENT_NAMES)
def test_a_mouse_sequence_leaves_the_two_sides_drawing_the_same_sheet(name):
    """A drag changed the sheet on one side only, so the next paint differs.

    A single value cannot report this: the drawing only differs after the
    events have moved the tab on to a state the paint then reads.
    """
    events = EVENT_SPECS[name]
    spec = TAB_SPECS["happy_two_wires"]
    old = old_outcome(spec, events)["value"]
    new = new_outcome(spec, events)["value"]
    assert canonical(new["drawing_calls"]) == canonical(old["drawing_calls"]), name
    assert new["tab"] == old["tab"], name
    assert new["tab_mouse_pos"] == old["tab_mouse_pos"], name


PARTIAL_SPECS = (
    "a_second_wire_refuses_after_the_first_paints",
    "a_second_wire_refuses_on_its_offset",
    "infinity_opacity",
    "text_where_an_opacity_belongs",
)


@pytest.mark.parametrize("name", PARTIAL_SPECS)
def test_a_sheet_that_refuses_part_way_leaves_the_same_drawing_behind(name):
    """One side stopped drawing at a different point than the other.

    A refusal part way leaves everything already drawn on the screen.
    Only the list of calls made before the refusal reports that.
    """
    old_calls, _image, old_error = partial_old(TAB_SPECS[name])
    new_calls, new_error = partial_new(TAB_SPECS[name])
    assert old_error is not None, name
    assert new_error == old_error, (name, old_error, new_error)
    assert canonical(new_calls) == canonical(old_calls), name
    assert digest(new_calls) == digest(old_calls), name


def test_the_partial_drawing_check_reports_a_first_wire_that_did_paint():
    """The partial check passes on a sheet that drew nothing at all."""
    whole, _image, whole_error = partial_old(TAB_SPECS["happy_two_wires"])
    partial, _partial_image, partial_error = partial_old(
        TAB_SPECS["a_second_wire_refuses_after_the_first_paints"]
    )
    early, _early_image, early_error = partial_old(TAB_SPECS["infinity_opacity"])
    assert whole_error is None
    assert partial_error == "TypeError"
    assert early_error == "OverflowError"
    assert len(early) == 1, early
    assert len(partial) > len(early), (len(partial), len(early))
    assert len(partial) < len(whole), (len(partial), len(whole))
    assert len(whole) == WIRE_CALL_TOTAL * 2 + 3, len(whole)
    assert partial[0] == [surface.SET_RENDER_HINT, surface.RENDER_HINT, 1]


def test_the_hash_tells_two_different_sheets_apart():
    """The hash returns one value whatever sheet it is given."""
    quantum = old_outcome(TAB_SPECS["happy_two_wires"])["value"]
    matrix = old_outcome(TAB_SPECS["theme_matrix"])["value"]
    assert canonical(quantum) != canonical(matrix)
    assert digest(quantum) != digest(matrix)
    assert digest(quantum) == digest(old_outcome(TAB_SPECS["happy_two_wires"])["value"])
    assert len(digest(quantum)) == 64


def test_the_hash_tells_two_different_mouse_routes_apart():
    """The route hash returns one value whatever was pressed."""
    quiet = old_outcome(TAB_SPECS["happy_two_wires"], EVENT_SPECS["nothing_touched"])
    dragged = old_outcome(TAB_SPECS["happy_two_wires"], EVENT_SPECS["a_whole_drag"])
    assert digest(quiet["value"]) != digest(dragged["value"])
    assert quiet["value"]["route"] == []
    assert dragged["value"]["route"] != []


@pytest.mark.parametrize("name", ["happy_two_wires", "empty_everywhere", "theme_ocean"])
def test_the_sample_sheet_hashes_are_reported(name):
    """The comparison passed on a sheet trace that carries nothing."""
    value = old_outcome(TAB_SPECS[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == 10, sorted(value)
    assert digest(value) == digest(new_outcome(TAB_SPECS[name])["value"])


def test_one_wire_makes_nineteen_drawing_calls_on_both_sides():
    """A drawing call was added or lost from one wire on one side only."""
    old = old_outcome(TAB_SPECS["one_wire"])["value"]["drawing_calls"]
    new = new_outcome(TAB_SPECS["one_wire"])["value"]["drawing_calls"]
    assert len(old) == WIRE_CALL_TOTAL + 3, old
    assert len(new) == len(old)
    two = old_outcome(TAB_SPECS["happy_two_wires"])["value"]["drawing_calls"]
    assert len(two) == WIRE_CALL_TOTAL * 2 + 3, len(two)
    assert [call[0] for call in old[:3]] == [
        surface.SET_RENDER_HINT,
        surface.SET_OPACITY,
        surface.SET_PEN,
    ]
    assert old[-1] == [surface.END_PAINTER]


def test_every_drawing_call_name_the_surface_declares_is_made():
    """The surface names a drawing call the sheet never makes."""
    seen = set()
    for name in TAB_NAMES:
        answered = old_outcome(TAB_SPECS[name])
        if answered["outcome"] != "answered":
            continue
        seen.update(call[0] for call in answered["value"]["drawing_calls"])
    assert seen == set(surface.DRAW_CALL_NAMES), sorted(
        set(surface.DRAW_CALL_NAMES) ^ seen
    )


def test_every_route_name_the_surface_declares_is_reached():
    """The surface names a mouse route the sheet never takes."""
    seen = set()
    for name in EVENT_NAMES:
        answered = old_outcome(TAB_SPECS["happy_two_wires"], EVENT_SPECS[name])
        seen.update(call[0] for call in answered["value"]["route"])
        seen.update(call[0] for call in answered["value"]["paint_asks"])
    assert seen == set(surface.ROUTE_NAMES), sorted(set(surface.ROUTE_NAMES) ^ seen)


def test_every_paint_branch_the_surface_declares_is_taken():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for name in TAB_NAMES:
        tab = surface.CanvasTabState(**TAB_SPECS[name])
        model = surface.WireCanvasModel(tab)
        try:
            model.paint(qt_sample, qt_advance)
        except Exception:
            seen.update(model.paint_branches)
            continue
        seen.update(model.paint_branches)
    assert seen == set(surface.PAINT_BRANCHES), sorted(
        set(surface.PAINT_BRANCHES) ^ seen
    )


DRAG_COLOUR_SPECS = {
    "dragging_over_empty_space": ("warning", surface.DRAG_LOOSE),
    "dragging_over_a_new_bot": ("success", surface.DRAG_CONNECT),
    "dragging_over_a_connected_bot": ("error", surface.DRAG_DISCONNECT),
    "dragging_back_to_the_same_bot": ("warning", surface.DRAG_LOOSE),
}


@pytest.mark.parametrize("name", sorted(DRAG_COLOUR_SPECS))
def test_the_dragged_wire_carries_the_colour_its_branch_names(name):
    """The dragged wire is drawn in a colour that says the wrong thing."""
    wanted, branch = DRAG_COLOUR_SPECS[name]
    spec = TAB_SPECS[name]
    old = old_outcome(spec)["value"]["drawing_calls"]
    tab = surface.CanvasTabState(**spec)
    model = surface.WireCanvasModel(tab)
    model.paint(qt_sample, qt_advance)
    assert branch in model.paint_branches, (name, model.paint_branches)
    expected = surface.with_alpha(surface.theme(spec["theme_key"])[wanted], 120)
    assert old[-3] == [surface.SET_PEN, expected, 2, surface.DRAG_PEN_STYLE], name
    assert old[-2][0] == surface.DRAW_LINE
    assert old[-3] == model.draw_calls[-3]


# ---------------------------------------------------------------------
# Answers and refusals
# ---------------------------------------------------------------------


def test_both_answers_and_refusals_are_in_the_measured_tab_set():
    """Every tab was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for name in TAB_NAMES:
        old = old_outcome(TAB_SPECS[name])
        (answered if old["outcome"] == "answered" else refused).append(name)
    assert answered, "no tab was answered"
    assert refused, "no tab was refused"
    assert set(refused) == set(REFUSING_TAB_SPECS), sorted(refused)
    assert len(answered) + len(refused) == len(TAB_SPECS)


def test_every_mouse_sequence_is_answered_by_both_sides():
    """A mouse sequence was refused, which the comparison never reports."""
    for name in EVENT_NAMES:
        old = old_outcome(TAB_SPECS["happy_two_wires"], EVENT_SPECS[name])
        new = new_outcome(TAB_SPECS["happy_two_wires"], EVENT_SPECS[name])
        assert old["outcome"] == "answered", (name, old)
        assert new["outcome"] == "answered", (name, new)


@pytest.mark.parametrize("name", REFUSING_TAB_SPECS)
def test_a_refused_tab_names_the_same_error_and_wording_on_both_sides(name):
    """One side refused a value the other accepted, or worded it differently."""
    spec = TAB_SPECS[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert new["error"] == old["error"], (name, old, new)
    assert new["message"] == old["message"], (name, old, new)
    assert old["error"] in ("TypeError", "ValueError", "OverflowError")


def test_the_refusals_cover_every_kind_the_sheet_can_raise():
    """One kind of refusal was never driven, so its wording is unchecked."""
    kinds = {old_outcome(TAB_SPECS[name])["error"] for name in REFUSING_TAB_SPECS}
    assert kinds == {"TypeError", "ValueError", "OverflowError"}, sorted(kinds)


def test_the_surface_refuses_a_mouse_event_of_an_unknown_kind():
    """An event kind no handler answers was run instead of refused."""
    model = surface.WireCanvasModel(surface.CanvasTabState(**TAB_SPECS["one_wire"]))
    with pytest.raises(ValueError) as reported:
        model.apply([["scroll", LEFT, 1.0, 2.0]])
    assert str(reported.value) == surface.EVENT_REFUSAL.format(kind="scroll")
    model.apply([[PRESS, LEFT, 5.0, 5.0]])
    assert model.calls == [[surface.BASE_PRESS]]


def test_a_flag_where_an_opacity_belongs_is_read_as_one_percent():
    """A flag was refused as a number, or read as something other than one."""
    old = old_outcome(TAB_SPECS["opacity_as_a_flag"])["value"]
    new = new_outcome(TAB_SPECS["opacity_as_a_flag"])["value"]
    assert old["drawing_calls"][1] == [surface.SET_OPACITY, 0.01]
    assert new["drawing_calls"][1] == old["drawing_calls"][1]
    assert surface.opacity_percent(True) == 1
    assert surface.opacity_percent(False) == 0


# ---------------------------------------------------------------------
# The enumeration: wiring, signals, classes, methods, timers, bus topics
# ---------------------------------------------------------------------


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            target = node.args[0]
            found.append(
                (
                    dotted(node.func.value),
                    "lambda" if isinstance(target, ast.Lambda) else dotted(target),
                )
            )
    return sorted(found)


def signal_sites(path) -> list:
    """Every ``Signal()`` a class in `path` declares, as class and name."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Assign):
                continue
            value = statement.value
            if isinstance(value, ast.Call) and dotted(value.func).endswith("Signal"):
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        found.append("%s.%s" % (node.name, target.id))
    return sorted(found)


def timer_sites(path) -> list:
    """Every ``QTimer(`` construction in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path) -> list:
    """Every ``subscribe(`` site in `path`, as the topic it names."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def classes_in(module) -> list:
    """Every class `module` declares, read off the module object."""
    return sorted(
        name
        for name, value in vars(module).items()
        if isinstance(value, type) and value.__module__ == module.__name__
    )


def methods_in(module) -> list:
    """Every method the module's classes declare, read off the class objects.

    A declared signal is callable too, so only real functions are counted
    here; the signals are enumerated by ``signal_sites``.
    """
    found = []
    for class_name in classes_in(module):
        held = getattr(module, class_name)
        for name, value in vars(held).items():
            if isinstance(value, types.FunctionType) and (
                not name.startswith("__") or name == "__init__"
            ):
                found.append("%s.%s" % (class_name, name))
    return sorted(found)


SHIPPED_CLASSES = {"_WireCanvas": "WireCanvasModel"}

# The surface holds one class the shipped file does not: the visualizer
# tab the sheet reads, which lives in another file and is stood in for
# here so the sheet can be driven with no visualizer built.
EXTRA_SURFACE_CLASSES = {"CanvasTabState": "BotVisualizationTab"}

SHIPPED_METHODS = {
    "_WireCanvas.__init__": "WireCanvasModel.__init__",
    "_WireCanvas.mousePressEvent": "WireCanvasModel.press",
    "_WireCanvas.mouseMoveEvent": "WireCanvasModel.move",
    "_WireCanvas.mouseReleaseEvent": "WireCanvasModel.release",
    "_WireCanvas.paintEvent": "WireCanvasModel.paint",
    "_WireCanvas._draw_glow_wire": "wire_calls",
}


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped sheet gained or lost a class or a method."""
    from src.gui.visualizer import wire_canvas as shipped

    classes = classes_in(shipped)
    assert classes == sorted(SHIPPED_CLASSES), classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    methods = methods_in(shipped)
    assert methods == sorted(SHIPPED_METHODS), methods
    assert len(methods) == SHIPPED_METHOD_TOTAL
    for counterpart in list(SHIPPED_CLASSES.values()) + list(SHIPPED_METHODS.values()):
        holder, _, attribute = counterpart.partition(".")
        target = getattr(surface, holder)
        assert callable(
            getattr(target, attribute) if attribute else target
        ), counterpart


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing."""
    built = classes_in(surface)
    assert built == sorted(
        list(SHIPPED_CLASSES.values()) + list(EXTRA_SURFACE_CLASSES)
    ), built
    assert len(built) == SURFACE_CLASS_TOTAL
    from src.gui import bot_visualizer

    for named in EXTRA_SURFACE_CLASSES.values():
        assert named in classes_in(bot_visualizer), named


def test_the_method_counter_leaves_a_signal_out():
    """The method counter counts a declared signal as a method.

    The shipped sheet declares none, so the counter is pointed at a
    neighbouring screen that declares three. A signal is callable, and a
    counter that took it for a method would report them there.
    """
    from src.gui import launcher

    declared = signal_sites(SIGNAL_NEIGHBOUR)
    assert len(declared) == 3, declared
    counted = methods_in(launcher)
    assert counted, "the method counter reports nothing"
    for name in declared:
        assert name not in counted, name
    assert "ModeCard.__init__" in counted


def test_the_sheet_connects_nothing_and_the_counter_can_report():
    """The shipped sheet connects a signal the surface names no action for.

    The shipped sheet connects none, so the counter is pointed at a
    neighbouring widget that really does connect one.
    """
    sites = connect_sites(CANVAS_SOURCE)
    assert sites == [], sites
    assert len(sites) == CONNECT_TOTAL
    assert surface.ACTIONS == {}
    assert len(surface.ACTIONS) == CONNECT_TOTAL
    assert CANVAS_SOURCE.read_text(encoding="utf-8").count(".connect(") == 0
    assert len(connect_sites(CONNECT_NEIGHBOUR)) >= 1, "the connect counter is blind"


def test_the_sheet_declares_no_signal_and_the_counter_can_report():
    """The shipped sheet declares a signal the surface answers with nothing."""
    declared = signal_sites(CANVAS_SOURCE)
    assert declared == [], declared
    assert len(declared) == SIGNAL_TOTAL
    assert surface.SIGNALS == ()
    assert len(signal_sites(SIGNAL_NEIGHBOUR)) == 3, "the signal counter is blind"


def test_the_sheet_holds_no_timer_and_the_counter_can_report():
    """The sheet runs a timer the surface declares no delay for."""
    assert timer_sites(CANVAS_SOURCE) == []
    assert len(timer_sites(CANVAS_SOURCE)) == TIMER_TOTAL
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(timer_sites(TIMER_NEIGHBOUR)) >= 1, "the timer counter is blind"


def test_the_sheet_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The sheet listens on a topic the surface names none of."""
    assert bus_sites(CANVAS_SOURCE) == []
    assert len(bus_sites(CANVAS_SOURCE)) == BUS_TOPIC_TOTAL
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter is blind"
    assert "wire.created" in neighbour


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "_WireCanvas.paintEvent" in SHIPPED_METHODS
    assert not hasattr(surface, "InventedModel")
    assert "InventedModel" not in SHIPPED_CLASSES.values()
    with pytest.raises(AttributeError):
        getattr(surface, "InventedModel")


# ---------------------------------------------------------------------
# The completeness check
# ---------------------------------------------------------------------


PAYLOAD_KEYS = {
    "ACTIONS": "actions",
    "ALIGN_CENTER": "alignment.name",
    "ALIGN_CENTER_VALUE": "alignment.value",
    "ARROW_BACK_PERCENT": "arrow.back_percent",
    "ARROW_CURSOR_VALUE": "cursors.ArrowCursor",
    "ARROW_PERCENT": "arrow.percent",
    "ARROW_SIDE_RATIO": "arrow.side_ratio",
    "ARROW_SIZE_PX": "arrow.size_px",
    "ARROW_WIDTH_PX": "arrow.width_px",
    "BADGE_CORNER_PX": "badge.corner_px",
    "BADGE_FILL": "badge.fill",
    "BADGE_HALF_DIVISOR": "badge.half_divisor",
    "BADGE_HEIGHT_PX": "badge.height_px",
    "BADGE_PADDING_PX": "badge.padding_px",
    "BADGE_TOP_OFFSET_PX": "badge.top_offset_px",
    "BUS_TOPICS": "bus_topics",
    "BUTTON_VALUES": "buttons",
    "CANVAS_ACCESSIBLE_NAME": "accessible_name",
    "CANVAS_ATTRIBUTES": "attributes",
    "CANVAS_STYLE": "style_sheet",
    "CONTROL_POINT_DIVISOR": "curve.control_divisor",
    "CORE_WIDTH_PX": "glow.core_width_px",
    "CUBIC_CONTROL_WEIGHT": "curve.cubic_control_weight",
    "CUBIC_DIVISOR": "curve.cubic_divisor",
    "CURSOR_VALUES": "cursors",
    "DEFAULT_OFFSET": "defaults.offset",
    "DEFAULT_OPACITY_PCT": "opacity.default_pct",
    "DEFAULT_PCT": "defaults.pct",
    "DEFAULT_PHASE": "defaults.phase",
    "DRAG_ALPHA": "drag.alpha",
    "DRAG_PEN_STYLE": "drag.pen_style",
    "DRAG_PEN_STYLE_VALUE": "drag.pen_style_value",
    "DRAG_WIDTH_PX": "drag.width_px",
    "DRAW_CALL_NAMES": "draw_call_names",
    "EVENT_KINDS": "event_kinds",
    "EVENT_REFUSAL": "formats.event_refusal",
    "FONT_FAMILY": "font.family",
    "FONT_SIZE_PT": "font.size_pt",
    "FONT_WEIGHT": "font.weight",
    "FONT_WEIGHT_VALUE": "font.weight_value",
    "GLOW_ALPHA": "glow.alpha",
    "GLOW_WIDTH_PX": "glow.width_px",
    "LABEL_FORMAT": "formats.label",
    "LABEL_PERCENT": "badge.label_percent",
    "LABEL_WIDTH_PX": "badge.label_width_px",
    "MID_GLOW_ALPHA": "glow.mid_alpha",
    "MID_GLOW_WIDTH_PX": "glow.mid_width_px",
    "NO_ADVANCE_PX": "badge.no_advance_px",
    "NO_BOT_ID": "defaults.no_bot_id",
    "NO_BRUSH": "pens.no_brush",
    "NO_PEN_STYLE": "pens.no_pen_style",
    "NO_PEN_WIDTH_PX": "pens.no_pen_width_px",
    "OPACITY_MAX_PCT": "opacity.max_pct",
    "OPACITY_MIN_PCT": "opacity.min_pct",
    "OPACITY_SCALE": "opacity.scale",
    "OPAQUE_ALPHA": "theme.opaque_alpha",
    "ALPHA_SCALE": "theme.alpha_scale",
    "ALPHA_UNIT": "theme.alpha_unit",
    "ORIGIN_POINT": "defaults.origin_point",
    "PAINT_BRANCHES": "paint_branch_names",
    "POINTING_HAND_CURSOR_VALUE": "cursors.PointingHandCursor",
    "POINT_KEY_FORMAT": "formats.point_key",
    "PULSE_ALPHA": "pulse.alpha",
    "PULSE_CENTRE_STOP": "pulse.centre_stop",
    "PULSE_EDGE_COLOR": "pulse.edge_color",
    "PULSE_EDGE_STOP": "pulse.edge_stop",
    "PULSE_GRADIENT_RADIUS_PX": "pulse.gradient_radius_px",
    "PULSE_PHASE_OFFSET": "pulse.phase_offset",
    "PULSE_PHASE_SCALE": "pulse.phase_scale",
    "PULSE_RADIUS_PX": "pulse.radius_px",
    "RENDER_HINT": "render_hint.name",
    "RENDER_HINT_VALUE": "render_hint.value",
    "ROUTE_NAMES": "route_names",
    "SIGNALS": "signals",
    "SOLID_PEN_STYLE": "pens.solid_style",
    "THEME_COLORS": "theme.table",
    "THEME_COLOR_NAMES": "theme.color_names",
    "THEME_FALLBACK_KEY": "theme.fallback_key",
    "THEME_KEYS": "theme.keys",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TRANSLUCENT_ATTRIBUTE": "attributes.0.0",
    "TRANSLUCENT_ATTRIBUTE_VALUE": "attributes.0.1",
    "WIRE_KEY_FORMAT": "formats.wire_key",
    "ZERO_LENGTH_FALLBACK": "arrow.zero_length_fallback",
}

# Values the payload carries inside a list rather than at a path of
# their own: the drawing call names, the mouse route names, the branch
# names, the mouse event kinds and the three curve point kinds.
LIST_MEMBERS = {
    "BASE_MOVE": "route_names",
    "BASE_PRESS": "route_names",
    "BASE_RELEASE": "route_names",
    "CURVE_TO_DATA_ELEMENT": "curve.element_names",
    "CURVE_TO_ELEMENT": "curve.element_names",
    "DRAG_CONNECT": "paint_branch_names",
    "DRAG_DISCONNECT": "paint_branch_names",
    "DRAG_LOOSE": "paint_branch_names",
    "DRAW_ELLIPSE": "draw_call_names",
    "DRAW_LINE": "draw_call_names",
    "DRAW_PATH": "draw_call_names",
    "DRAW_POLYGON": "draw_call_names",
    "DRAW_ROUNDED_RECT": "draw_call_names",
    "DRAW_TEXT": "draw_call_names",
    "END_PAINTER": "draw_call_names",
    "MOVE_EVENT": "event_kinds",
    "MOVE_TO_ELEMENT": "curve.element_names",
    "PAINT_NOTHING": "paint_branch_names",
    "PRESS_EVENT": "event_kinds",
    "RELEASE_EVENT": "event_kinds",
    "SET_BRUSH": "draw_call_names",
    "SET_CURSOR": "route_names",
    "SET_FONT": "draw_call_names",
    "SET_GRADIENT_BRUSH": "draw_call_names",
    "SET_OPACITY": "draw_call_names",
    "SET_PEN": "draw_call_names",
    "SET_RENDER_HINT": "draw_call_names",
    "TAB_BOT_AT_POS": "route_names",
    "TAB_BOT_CENTER": "route_names",
    "TAB_FINISH_WIRE_DRAG": "route_names",
    "TAB_SHOW_DISCONNECT_MENU": "route_names",
    "TAB_START_WIRE_DRAG": "route_names",
    "TAB_UPDATE_WIRE_DRAG": "route_names",
    "TAB_WIRE_AT_POS": "route_names",
    "TAB_WIRE_OFFSET": "route_names",
    "WIRE_DRAWN": "paint_branch_names",
    "WIRE_SKIPPED": "paint_branch_names",
}

# Values the payload carries as the key of a table rather than a value.
KEY_MEMBERS = {
    "ARROW_CURSOR": "cursors",
    "LEFT_BUTTON": "buttons",
    "MIDDLE_BUTTON": "buttons",
    "NO_BUTTON": "buttons",
    "POINTING_HAND_CURSOR": "cursors",
    "RIGHT_BUTTON": "buttons",
}

# The two values no payload key carries, each with the check that covers
# it. METHOD is the name the bridge registers under and CANVAS_MODEL the
# sheet state the bridge keeps between calls.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_wire_canvas_method",
    "CANVAS_MODEL": "test_the_bridge_resets_the_sheet_state_on_request",
}

STATE_ONLY_KEYS = {"cursor", "drawing_calls", "paint_branches", "calls", "tab"}


def at_path(payload, path):
    """The payload value one dotted path names; a number steps into a list."""
    found = payload
    for step in path.split("."):
        found = found[int(step)] if step.isdigit() else found[step]
    return found


def as_lists(value):
    """`value` with every tuple turned into a list, at every depth."""
    if isinstance(value, dict):
        return {key: as_lists(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_lists(inner) for inner in value]
    return value


def surface_constants() -> dict:
    """Every value the surface exports that is not a function or a class."""
    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read.

    A comparison that reads some of the values passes whether the rest
    match or not. Every value is accounted for here: a payload path, a
    member of a list or a key of a table the payload carries, or one of
    the two named with the check that covers it.
    """
    tab = surface.CanvasTabState(**TAB_SPECS["happy_two_wires"])
    payload = surface.build_view_model(surface.WireCanvasModel(tab))
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payload, PAYLOAD_KEYS[name]) == as_lists(value), name
        elif name in LIST_MEMBERS:
            assert value in at_path(payload, LIST_MEMBERS[name]), name
        elif name in KEY_MEMBERS:
            assert value in at_path(payload, KEY_MEMBERS[name]), name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(PAYLOAD_KEYS) == 85
    assert len(LIST_MEMBERS) == 37
    assert len(KEY_MEMBERS) == 6
    assert len(NOT_IN_THE_SNAPSHOT) == 2


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    tab = surface.CanvasTabState(**TAB_SPECS["happy_two_wires"])
    payload = surface.build_view_model(surface.WireCanvasModel(tab))
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {path.split(".")[0] for path in LIST_MEMBERS.values()}
    answered |= {path.split(".")[0] for path in KEY_MEMBERS.values()}
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    assert len(payload) == PAYLOAD_KEY_TOTAL
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing."""
    tab = surface.CanvasTabState(**TAB_SPECS["happy_two_wires"])
    payload = surface.build_view_model(surface.WireCanvasModel(tab))
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in LIST_MEMBERS
    assert invented not in KEY_MEMBERS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "GLOW_ALPHA" in surface_constants()
    assert "THEME_COLORS" in surface_constants()
    assert "wire_calls" not in surface_constants()
    assert "WireCanvasModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "glow.invented")
    with pytest.raises(IndexError):
        at_path(payload, "attributes.9")


# ---------------------------------------------------------------------
# The surface carries its own values
# ---------------------------------------------------------------------


@pytest.fixture
def restored_theme_table():
    """Put the shipped colour table back after a test changes it."""
    from src.gui.visualizer import themes

    pristine = {name: dict(row) for name, row in themes.THEMES.items()}
    yield themes.THEMES
    for name in [one for one in themes.THEMES if one not in pristine]:
        del themes.THEMES[name]
    for name, row in pristine.items():
        themes.THEMES.setdefault(name, {})
        themes.THEMES[name].clear()
        themes.THEMES[name].update(row)


def test_the_surface_does_not_follow_a_colour_moved_in_the_shipped_table(
    restored_theme_table,
):
    """The surface read its colours off the table it replaces.

    A surface that read the shipped table would follow it, and the whole
    comparison above would be one side read twice. The wire colour the
    shipped sheet looks up is moved and the surface must not move with
    it.
    """
    from PySide6.QtGui import QColor

    app()
    spec = TAB_SPECS["one_wire"]
    before = old_outcome(spec)["value"]["drawing_calls"]
    restored_theme_table["quantum"]["accent"] = QColor(9, 9, 9)
    moved = old_outcome(spec)["value"]["drawing_calls"]
    assert moved[2] == [surface.SET_PEN, [9, 9, 9, surface.GLOW_ALPHA], 8, "SolidLine"]
    assert before[2] == [surface.SET_PEN, [0, 200, 255, 25], 8, "SolidLine"]
    mine = new_outcome(spec)["value"]["drawing_calls"]
    assert mine[2] == before[2]
    assert canonical(mine) == canonical(before)


def draws_nothing(*_args, **_named):
    """A wire drawer that makes no drawing call at all."""
    return None


def test_the_surface_does_not_follow_a_sheet_that_draws_nothing(monkeypatch):
    """The surface asked the shipped sheet to work out its drawing."""
    from src.gui.visualizer import wire_canvas as shipped

    app()
    spec = TAB_SPECS["one_wire"]
    mine = new_outcome(spec)["value"]["drawing_calls"]
    monkeypatch.setattr(shipped._WireCanvas, "_draw_glow_wire", draws_nothing)
    stripped = old_outcome(spec)["value"]["drawing_calls"]
    assert len(stripped) == 3, stripped
    again = new_outcome(spec)["value"]["drawing_calls"]
    assert canonical(again) == canonical(mine)
    assert len(again) == WIRE_CALL_TOTAL + 3
    monkeypatch.undo()
    assert len(old_outcome(spec)["value"]["drawing_calls"]) == len(mine)


def test_the_shipped_sheet_writes_to_no_shared_table(restored_theme_table):
    """The shipped sheet changes a table other tests read.

    A test whose result depends on what ran before it passes alone and
    fails under the build machine's parallel run.
    """
    from PySide6.QtGui import QColor

    app()

    def snapshot():
        return {
            name: {
                key: value.name() if isinstance(value, QColor) else value
                for key, value in row.items()
            }
            for name, row in restored_theme_table.items()
        }

    before = snapshot()
    for name in ("happy_two_wires", "theme_matrix", "dragging_over_a_new_bot"):
        old_outcome(TAB_SPECS[name])
    assert snapshot() == before
    restored_theme_table["quantum"]["accent"] = QColor(9, 9, 9)
    assert snapshot() != before, "the shared-table check cannot report a change"


def test_the_surface_keeps_no_state_between_two_sheets():
    """A sheet built after another carried the first one's values."""
    first = surface.WireCanvasModel(
        surface.CanvasTabState(**TAB_SPECS["happy_two_wires"])
    )
    first.apply(EVENT_SPECS["a_whole_drag"])
    first.paint(qt_sample, qt_advance)
    second = surface.WireCanvasModel(
        surface.CanvasTabState(**TAB_SPECS["happy_two_wires"])
    )
    assert second.calls == []
    assert second.cursor is None
    assert second.draw_calls == []
    fresh = surface.build_view_model(second, None, qt_sample, qt_advance)
    again = surface.build_view_model(
        surface.WireCanvasModel(surface.CanvasTabState(**TAB_SPECS["happy_two_wires"])),
        None,
        qt_sample,
        qt_advance,
    )
    assert canonical(fresh) == canonical(again)


# ---------------------------------------------------------------------
# The colours
# ---------------------------------------------------------------------


def canonical_colour(value):
    """One colour as the six-digit value the screen reports."""
    from PySide6.QtGui import QColor

    return QColor(value[0], value[1], value[2]).name().lower()


def test_every_declared_wire_colour_matches_the_shipped_table():
    """A wire colour drifted from the table the shipped sheet reads."""
    from src.gui.visualizer.themes import THEMES

    app()
    for key in surface.THEME_KEYS:
        for name in surface.THEME_COLOR_NAMES:
            mine = surface.THEME_COLORS[key][name]
            theirs = THEMES[key][name]
            assert list(mine) == [
                theirs.red(),
                theirs.green(),
                theirs.blue(),
                theirs.alpha(),
            ], (key, name)


def test_the_declared_colours_stay_apart_when_written_in_full():
    """Two declared colours become one when written in full."""
    app()
    written = {
        "%s.%s" % (key, name): canonical_colour(surface.THEME_COLORS[key][name])
        for key in surface.THEME_KEYS
        for name in surface.THEME_COLOR_NAMES
    }
    assert canonical_colour(surface.THEME_COLORS["quantum"]["accent"]) == "#00c8ff"
    assert all(len(value) == 7 for value in written.values()), written
    assert len(set(written.values())) >= 15, sorted(set(written.values()))


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour check passes a value with its channels swapped."""
    app()
    accent = surface.THEME_COLORS["quantum"]["accent"]
    assert canonical_colour(accent) == "#00c8ff"
    assert canonical_colour([accent[2], accent[1], accent[0], 255]) != "#00c8ff"
    assert canonical_colour(surface.THEME_COLORS["matrix"]["error"]) == "#ff0000"


def holds(value, wanted):
    """True when `wanted` appears anywhere inside `value`."""
    if value == wanted:
        return True
    if isinstance(value, list):
        return any(holds(inner, wanted) for inner in value)
    return False


EQUAL_CHANNEL_COLOURS = ("PULSE_EDGE_COLOR", "BADGE_FILL")


@pytest.mark.parametrize("name", EQUAL_CHANNEL_COLOURS)
def test_an_equal_channel_colour_is_compared_as_numbers(name):
    """A colour with three equal channels was left to a colour check.

    Black reads the same with any two channels swapped, so no colour
    check can report a swap in it. Both are compared as their four
    numbers inside the drawing call that carries them, which the
    side-by-side comparison covers.
    """
    app()
    value = getattr(surface, name)
    assert value[0] == value[1] == value[2], value
    old = old_outcome(TAB_SPECS["one_wire"])["value"]["drawing_calls"]
    assert holds(old, list(value)), (name, value)
    assert not holds(old, [1, 2, 3, 4]), "the colour search finds anything"


def test_the_alpha_of_every_wire_layer_is_the_one_declared():
    """A see-through level drifted from the one the surface declares."""
    old = old_outcome(TAB_SPECS["one_wire"])["value"]["drawing_calls"]
    gradient = [call for call in old if call[0] == surface.SET_GRADIENT_BRUSH][0]
    assert old[2][1][3] == surface.GLOW_ALPHA
    assert old[5][1][3] == surface.MID_GLOW_ALPHA
    assert old[7][1][3] == surface.OPAQUE_ALPHA
    assert gradient[3][0][1][3] == surface.PULSE_ALPHA
    assert gradient[3][1][1] == list(surface.PULSE_EDGE_COLOR)


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------


def model_payload(name, events=()):
    """The view model of one tab, stamped."""
    tab = surface.CanvasTabState(**TAB_SPECS[name])
    model = surface.WireCanvasModel(tab)
    return sealed(
        surface.build_view_model(model, events or None, qt_sample, qt_advance)
    )


def image_painted_by_the_sheet(name, events=()):
    """The picture the shipped Qt sheet paints."""
    app()
    image = new_image()
    old_trace(TAB_SPECS[name], events, image)
    return image


def image_painted_by_the_model(payload):
    """A picture drawn only from the view model, never from the sheet.

    A payload the caller changed after it came off the surface is
    refused.
    """
    payload = unaltered(payload)
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import (
        QBrush,
        QColor,
        QFont,
        QPainter,
        QPainterPath,
        QPolygonF,
        QRadialGradient,
    )

    app()
    image = new_image()
    painter = QPainter(image)

    def colour(value):
        return QColor(value[0], value[1], value[2], value[3])

    def path_from(elements):
        path = QPainterPath()
        path.moveTo(QPointF(elements[0][1], elements[0][2]))
        for index in range(1, len(elements), 3):
            one, two, three = elements[index : index + 3]
            path.cubicTo(
                QPointF(one[1], one[2]),
                QPointF(two[1], two[2]),
                QPointF(three[1], three[2]),
            )
        return path

    for call in payload["drawing_calls"]:
        name = call[0]
        if name == surface.SET_RENDER_HINT:
            painter.setRenderHint(getattr(QPainter.RenderHint, call[1]))
        elif name == surface.SET_OPACITY:
            painter.setOpacity(call[1])
        elif name == surface.SET_PEN:
            from PySide6.QtGui import QPen

            if call[1] is None:
                painter.setPen(getattr(Qt.PenStyle, call[3]))
            else:
                painter.setPen(
                    QPen(colour(call[1]), call[2], getattr(Qt.PenStyle, call[3]))
                )
        elif name == surface.SET_BRUSH:
            if isinstance(call[1], str):
                painter.setBrush(getattr(Qt.BrushStyle, call[1]))
            else:
                painter.setBrush(QBrush(colour(call[1])))
        elif name == surface.SET_GRADIENT_BRUSH:
            wash = QRadialGradient(call[1][0], call[1][1], call[2])
            for stop, value in call[3]:
                wash.setColorAt(stop, colour(value))
            painter.setBrush(QBrush(wash))
        elif name == surface.SET_FONT:
            painter.setFont(QFont(call[1], call[2], getattr(QFont.Weight, call[3])))
        elif name == surface.DRAW_PATH:
            painter.drawPath(path_from(call[1]))
        elif name == surface.DRAW_ELLIPSE:
            painter.drawEllipse(QPointF(call[1][0], call[1][1]), call[2], call[3])
        elif name == surface.DRAW_POLYGON:
            painter.drawPolygon(QPolygonF([QPointF(one[0], one[1]) for one in call[1]]))
        elif name == surface.DRAW_ROUNDED_RECT:
            painter.drawRoundedRect(QRectF(*call[1]), call[2], call[3])
        elif name == surface.DRAW_TEXT:
            painter.drawText(
                QRectF(*call[1]), getattr(Qt.AlignmentFlag, call[2]), call[3]
            )
        elif name == surface.DRAW_LINE:
            painter.drawLine(
                QPointF(call[1][0], call[1][1]), QPointF(call[2][0], call[2][1])
            )
        elif name == surface.END_PAINTER:
            painter.end()
    if painter.isActive():
        painter.end()
    return image


PICTURE_TABS = [
    "happy_two_wires",
    "one_wire",
    "theme_matrix",
    "dragging_over_a_connected_bot",
    "zero_percent",
    "two_hundred_characters_percent",
]


@pytest.mark.parametrize("name", PICTURE_TABS)
def test_the_two_sides_paint_one_sheet(name):
    """The surface painted a different sheet than the shipped one."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=image_painted_by_the_sheet(name),
        new_side=image_painted_by_the_model(model_payload(name)),
        note=note,
    )


@pytest.mark.parametrize("name", ["a_whole_drag", "a_move_over_a_wire"])
def test_the_two_sides_paint_one_sheet_after_a_mouse_sequence(name):
    """A drag left the two sides painting different sheets."""
    app()
    events = EVENT_SPECS[name]
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=image_painted_by_the_sheet("happy_two_wires", events),
        new_side=image_painted_by_the_model(model_payload("happy_two_wires", events)),
        note=note,
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    The Quantum sheet off the shipped class against the Matrix sheet off
    the surface. Both are real product sheets and they carry different
    wire colours, so a pass proves the comparison reports a sheet painted
    differently.
    """
    app()
    assert TAB_SPECS["happy_two_wires"] != TAB_SPECS["theme_matrix"]
    assert_pictures_differ(
        old_side=image_painted_by_the_sheet("happy_two_wires"),
        new_side=image_painted_by_the_model(model_payload("theme_matrix")),
        note="the Quantum sheet against the Matrix sheet",
    )


def colours_in(image) -> set:
    """Every colour the render painted, sampled every third pixel."""
    from PySide6.QtGui import QColor

    seen = set()
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            seen.add(QColor(image.pixelColor(x, y)).name())
    return seen


@pytest.mark.parametrize("name", PICTURE_TABS)
def test_the_painted_sheet_shows_more_than_one_colour(name):
    """The two sides matched because the sheet painted one flat colour."""
    app()
    for image in (
        image_painted_by_the_sheet(name),
        image_painted_by_the_model(model_payload(name)),
    ):
        assert image.width() == CANVAS_SIZE[0]
        assert image.height() == CANVAS_SIZE[1]
        seen = colours_in(image)
        assert len(seen) > 1, "%s painted one colour, so no change could show" % name


def test_an_empty_sheet_paints_one_colour_and_is_compared_by_value():
    """The empty sheet paints something, so its picture could report.

    A sheet with no wire and no drag draws nothing at all, so its picture
    is one flat colour and no picture check on it could ever fail. It is
    compared value for value instead.
    """
    app()
    image = image_painted_by_the_sheet("no_wires_and_no_drag")
    assert len(colours_in(image)) == 1, "the empty sheet painted more than one colour"
    old = old_outcome(TAB_SPECS["no_wires_and_no_drag"])["value"]
    new = new_outcome(TAB_SPECS["no_wires_and_no_drag"])["value"]
    assert old["drawing_calls"] == []
    assert canonical(new) == canonical(old)


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload("one_wire")
    payload["drawing_calls"][2][1] = [255, 0, 0, 25]
    with pytest.raises(AssertionError) as reported:
        image_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    tab = surface.CanvasTabState(**TAB_SPECS["one_wire"])
    with pytest.raises(AssertionError):
        image_painted_by_the_model(
            surface.build_view_model(
                surface.WireCanvasModel(tab), None, qt_sample, qt_advance
            )
        )


@skip_unless_no_fonts
def test_two_badge_labels_of_equal_length_measure_the_same_width():
    """The host reports no fonts and the glyphs still have their own widths."""
    app()
    narrow = app_font_advance_px(surface.label_text(NARROW_LABEL))
    wide = app_font_advance_px(surface.label_text(WIDE_LABEL))
    assert narrow == wide, (narrow, wide)


@skip_unless_real_fonts
def test_two_badge_labels_of_equal_length_measure_different_widths():
    """The host reports fonts and every glyph still has one width."""
    app()
    narrow = app_font_advance_px(surface.label_text(NARROW_LABEL))
    wide = app_font_advance_px(surface.label_text(WIDE_LABEL))
    assert narrow != wide, (narrow, wide)


def test_the_badge_is_as_wide_as_the_label_the_font_engine_measured():
    """The badge stopped following the width of the text inside it."""
    app()
    short = old_outcome(TAB_SPECS["zero_percent"])["value"]["drawing_calls"]
    long_one = old_outcome(TAB_SPECS["two_hundred_characters_percent"])["value"][
        "drawing_calls"
    ]
    short_badge = [call for call in short if call[0] == surface.DRAW_ROUNDED_RECT][0]
    long_badge = [call for call in long_one if call[0] == surface.DRAW_ROUNDED_RECT][0]
    assert long_badge[1][2] > short_badge[1][2], (short_badge, long_badge)
    assert short_badge[1][2] == qt_advance("0%") + surface.BADGE_PADDING_PX
    assert short_badge[1][3] == float(surface.BADGE_HEIGHT_PX)


def test_the_surface_default_curve_agrees_with_the_drawing_library():
    """The surface works out a point on the curve the library disagrees with.

    The bridge answers with the surface's own curve when the caller
    supplies no drawing engine. It must land on the same point the
    library does, to a millionth of a pixel.
    """
    app()
    src, control, tgt = (40.0, 60.0), (130.0, 130.0), (220.0, 150.0)
    for percent in (0.0, 0.25, 0.5, 0.65, 0.7, 1.0):
        mine = surface.quadratic_point(src, control, tgt, percent)
        theirs = qt_sample(src, control, tgt, percent)
        assert abs(mine[0] - theirs[0]) < 1e-6, percent
        assert abs(mine[1] - theirs[1]) < 1e-6, percent
    off = surface.quadratic_point(src, control, tgt, 0.9)
    assert abs(off[0] - qt_sample(src, control, tgt, 0.7)[0]) > 1.0


# ---------------------------------------------------------------------
# What a picture cannot see, read off both sides instead
# ---------------------------------------------------------------------


def test_the_values_no_picture_carries_are_read_off_both_sides():
    """A value that reaches no pixel was left to the render to report.

    The sheet's name for a screen reader, its style sheet, the
    see-through window setting and the mouse pointer paint nothing of
    their own. Each is read off the shipped sheet and off the surface
    directly.
    """
    app()
    old = old_outcome(TAB_SPECS["happy_two_wires"])["value"]
    new = new_outcome(TAB_SPECS["happy_two_wires"])["value"]
    assert new["accessible_name"] == old["accessible_name"]
    assert new["style_sheet"] == old["style_sheet"]
    assert new["attributes"] == old["attributes"]
    assert new["cursor"] == old["cursor"]
    assert old["accessible_name"] == "Wire Canvas"
    assert old["style_sheet"] == "background: transparent;"
    assert old["attributes"] == [["WA_TranslucentBackground", 120]]
    assert old["cursor"] is None


def test_the_mouse_pointer_is_read_off_both_sides():
    """A pointer change reaches no pixel, so it must be read off both sides."""
    app()
    for name, wanted in (
        ("a_move_over_a_wire", "PointingHandCursor"),
        ("a_move_over_empty_space", "ArrowCursor"),
        ("a_move_over_a_wire_then_empty_space", "ArrowCursor"),
        ("nothing_touched", None),
    ):
        events = EVENT_SPECS[name]
        old = old_outcome(TAB_SPECS["happy_two_wires"], events)["value"]
        new = new_outcome(TAB_SPECS["happy_two_wires"], events)["value"]
        assert old["cursor"] == wanted, name
        assert new["cursor"] == old["cursor"], name


def test_the_drag_the_sheet_started_is_read_off_both_sides():
    """A drag reaches no pixel until it is drawn, so it is read off both."""
    app()
    events = EVENT_SPECS["a_whole_drag"]
    old = old_outcome(TAB_SPECS["happy_two_wires"], events)["value"]
    new = new_outcome(TAB_SPECS["happy_two_wires"], events)["value"]
    assert new["route"] == old["route"]
    assert new["tab"] == old["tab"] is False
    assert new["tab_start_id"] == old["tab_start_id"] == ""
    started = old_outcome(TAB_SPECS["happy_two_wires"], [[PRESS, LEFT, 40.0, 60.0]])[
        "value"
    ]
    assert started["tab"] is True
    assert started["tab_start_id"] == "alpha"
    assert started["tab_mouse_pos"] == [40.0, 60.0]


def test_the_questions_the_sheet_asks_the_tab_are_read_off_both_sides():
    """The sheet asked the visualizer a different question on each side."""
    app()
    for name in ("happy_two_wires", "dragging_over_a_new_bot", "a_bot_at_the_origin"):
        old = old_outcome(TAB_SPECS[name])["value"]
        new = new_outcome(TAB_SPECS[name])["value"]
        assert new["paint_asks"] == old["paint_asks"], name
        assert old["paint_asks"], name
    skipped = old_outcome(TAB_SPECS["a_bot_at_the_origin"])["value"]
    assert [surface.TAB_BOT_CENTER, "alpha"] in skipped["paint_asks"]
    assert [surface.TAB_WIRE_OFFSET, "alpha->beta"] not in skipped["paint_asks"]


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


@pytest.fixture(autouse=True)
def restored_bridge_sheet():
    """Put the sheet the bridge keeps back after a test replaces it.

    The surface keeps one sheet at module level so the bridge can hold
    state between calls. Every test in this file gets its own, or the
    build machine's parallel run orders them differently and a result
    depends on what ran before it.
    """
    was = surface.CANVAS_MODEL
    yield
    surface.CANVAS_MODEL = was


BRIDGE_TAB = {
    "wires": [{"source_id": "alpha", "target_id": "beta", "pct": 30, "phase": 0.5}],
    "bot_centers": {"alpha": [40.0, 60.0], "beta": [220.0, 150.0]},
    "wire_offsets": {"alpha->beta": 25.0},
    "bot_hits": {"40.0,60.0": "alpha"},
    "theme_key": "quantum",
    "wire_opacity_pct": 80,
}


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


def test_the_bridge_registers_the_wire_canvas_method():
    """The renderer cannot reach the wire sheet over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "wire_canvas.state"
    answer = bridge_answer({"tab": BRIDGE_TAB})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["accessible_name"] == "Wire Canvas"
    assert result["drawing_calls"][0] == ["set_render_hint", "Antialiasing", 1]
    assert result["drawing_calls"][-1] == ["end"]
    assert result["paint_branches"] == ["wire.drawn"]


def test_the_bridge_measures_the_badge_from_the_widths_it_is_sent():
    """The badge ignored the label width the renderer measured."""
    plain = bridge_answer({"tab": BRIDGE_TAB})["result"]
    measured = bridge_answer({"tab": BRIDGE_TAB, "advances": {"30%": 40}})["result"]
    plain_badge = [
        call for call in plain["drawing_calls"] if call[0] == "draw_rounded_rect"
    ][0]
    measured_badge = [
        call for call in measured["drawing_calls"] if call[0] == "draw_rounded_rect"
    ][0]
    assert plain_badge[1][2] == float(surface.BADGE_PADDING_PX)
    assert measured_badge[1][2] == float(40 + surface.BADGE_PADDING_PX)


def test_the_bridge_resets_the_sheet_state_on_request():
    """The sheet state the bridge keeps was never cleared."""
    filled = bridge_answer({"tab": BRIDGE_TAB, "events": [[PRESS, LEFT, 40.0, 60.0]]})[
        "result"
    ]
    assert filled["tab"]["dragging_wire"] is True
    assert filled["tab"]["wire_start_id"] == "alpha"
    kept = bridge_answer({})["result"]
    assert kept["tab"]["dragging_wire"] is True
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["tab"]["dragging_wire"] is False
    assert cleared["tab"]["wires"] == []
    assert cleared["drawing_calls"] == []


def test_the_bridge_reports_a_value_the_sheet_refuses():
    """A value the sheet refuses ended the session instead of answering."""
    answer = bridge_answer({"tab": dict(BRIDGE_TAB, wire_opacity_pct="loud")})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"
    assert "loud" in answer["error"]["message"]


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"tab": BRIDGE_TAB, "events": [[MOVE, NONE, 5.0, 5.0]]})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["cursor"] == "ArrowCursor"
    assert encoded["result"]["draw_call_names"] == list(surface.DRAW_CALL_NAMES)


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'wire_canvas.state', 'params':"
    " {'tab': {'wires': [{'source_id': 'a', 'target_id': 'b', 'pct': 30}],"
    " 'bot_centers': {'a': [10.0, 20.0], 'b': [200.0, 40.0]}}}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)


def run_probe(prelude):
    done = subprocess.run(
        [sys.executable, "-"],
        input=(prelude + QT_PROBE).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the wire sheet pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["accessible_name"] == "Wire Canvas"
    assert result["paint_branches"] == ["wire.drawn"]
    assert len(result["drawing_calls"]) == WIRE_CALL_TOTAL + 3


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
