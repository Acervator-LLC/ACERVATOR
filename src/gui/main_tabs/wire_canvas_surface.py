"""wire_canvas_surface.py -- the Smart Wire overlay.

Describes the see-through sheet that lies over the bot visualizer and
draws the wires between bots. Each wire is a hanging catenary with a glow, a
travelling dot, a direction arrow and a small badge showing its share
percentage. A wire being dragged is drawn as a dashed line whose colour
says what a release would do.

``WireCanvasModel`` is the sheet. ``paint`` returns the ordered list of
drawing operations, each with its own coordinates, colours, widths and
sizes. ``press``, ``move`` and ``release`` are the mouse, and each one
records what the sheet asked the visualizer tab to do.
``build_view_model`` returns every value the sheet holds as one dict.

The sheet asks the visualizer tab where the bots are and which wire is
under the mouse. That tab is supplied by the caller, so this module
holds the drawing and the routing and nothing else.

One quantity belongs to the drawing engine, not to this screen: the width of
a printed label. It is taken as a callable, and ``no_advance`` is the value
used when the caller supplies none. ``catenary_curve`` works out the wire
itself, and ``place_badge`` keeps two percentage badges apart.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``wire_canvas.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.visualizer.wire_canvas`` or its theme table, so a value
changed on one side alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

METHOD = "wire_canvas.state"

CANVAS_ACCESSIBLE_NAME = "Wire Canvas"
CANVAS_STYLE = "background: transparent;"
TRANSLUCENT_ATTRIBUTE = "WA_TranslucentBackground"
TRANSLUCENT_ATTRIBUTE_VALUE = 120
CANVAS_ATTRIBUTES = ((TRANSLUCENT_ATTRIBUTE, TRANSLUCENT_ATTRIBUTE_VALUE),)

RENDER_HINT = "Antialiasing"
RENDER_HINT_VALUE = 1

OPACITY_MIN_PCT = 0
OPACITY_MAX_PCT = 100
DEFAULT_OPACITY_PCT = 100
OPACITY_SCALE = 100.0

THEME_FALLBACK_KEY = "quantum"
THEME_COLOR_NAMES = ("accent", "accent2", "success", "warning", "error")
OPAQUE_ALPHA = 255
ALPHA_SCALE = float(OPAQUE_ALPHA)
ALPHA_UNIT = 1.0 / ALPHA_SCALE

THEME_COLORS = {
    "nebula": {
        "accent": (120, 80, 255, OPAQUE_ALPHA),
        "accent2": (255, 60, 180, OPAQUE_ALPHA),
        "success": (0, 255, 160, OPAQUE_ALPHA),
        "warning": (255, 200, 0, OPAQUE_ALPHA),
        "error": (255, 40, 80, OPAQUE_ALPHA),
    },
    "matrix": {
        "accent": (0, 255, 65, OPAQUE_ALPHA),
        "accent2": (0, 180, 45, OPAQUE_ALPHA),
        "success": (0, 255, 100, OPAQUE_ALPHA),
        "warning": (200, 255, 0, OPAQUE_ALPHA),
        "error": (255, 0, 0, OPAQUE_ALPHA),
    },
    "quantum": {
        "accent": (0, 200, 255, OPAQUE_ALPHA),
        "accent2": (0, 255, 200, OPAQUE_ALPHA),
        "success": (0, 255, 136, OPAQUE_ALPHA),
        "warning": (255, 180, 0, OPAQUE_ALPHA),
        "error": (255, 50, 80, OPAQUE_ALPHA),
    },
    "ocean": {
        "accent": (0, 150, 255, OPAQUE_ALPHA),
        "accent2": (0, 220, 180, OPAQUE_ALPHA),
        "success": (0, 230, 170, OPAQUE_ALPHA),
        "warning": (255, 200, 50, OPAQUE_ALPHA),
        "error": (255, 60, 90, OPAQUE_ALPHA),
    },
}
THEME_KEYS = ("nebula", "matrix", "quantum", "ocean")

# A wire hangs with 18 % more cable than the straight distance between its bots.
CATENARY_SLACK_RATIO = 0.18
CATENARY_SAMPLES = 24
CATENARY_SOLVE_STEPS = 60
# u is span / 2a. sinh(u) / u runs from 1 upward, and sinh(300) still divides.
CATENARY_U_MIN = 1e-9
CATENARY_U_MAX = 300.0
# wire_offset turns into slack: the lower slot of a pair hangs deeper.
CATENARY_OFFSET_SLACK = 0.004
CATENARY_MIN_SLACK = 0.04
HALF = 2.0
HALF_INDEX = 2

MOVE_TO_ELEMENT = "MoveToElement"
LINE_TO_ELEMENT = "LineToElement"
CURVE_TO_ELEMENT = "CurveToElement"
CURVE_TO_DATA_ELEMENT = "CurveToDataElement"

GLOW_ALPHA = 25
GLOW_WIDTH_PX = 8
MID_GLOW_ALPHA = 50
MID_GLOW_WIDTH_PX = 4
CORE_WIDTH_PX = 2

PULSE_PHASE_SCALE = 0.5
PULSE_PHASE_OFFSET = 0.5
PULSE_ALPHA = 200
PULSE_GRADIENT_RADIUS_PX = 12
PULSE_RADIUS_PX = 8
PULSE_CENTRE_STOP = 0.0
PULSE_EDGE_STOP = 1.0
PULSE_EDGE_COLOR = (0, 0, 0, 0)

ARROW_PERCENT = 0.7
ARROW_BACK_PERCENT = 0.65
ARROW_SIZE_PX = 6
ARROW_SIDE_RATIO = 0.5
ARROW_WIDTH_PX = 2
ZERO_LENGTH_FALLBACK = 1

LABEL_FORMAT = "{pct}%"
LABEL_WIDTH_PX = 1
BADGE_PADDING_PX = 8
BADGE_HEIGHT_PX = 18
BADGE_TOP_OFFSET_PX = -9
BADGE_HALF_DIVISOR = 2
BADGE_CORNER_PX = 4
BADGE_FILL = (0, 0, 0, 160)
NO_ADVANCE_PX = 0
# Two badges keep this much clear air between them.
BADGE_GAP_PX = 2
BADGE_PUSH_PX = 20
BADGE_PUSH_TRIES = 60

FONT_FAMILY = "Consolas"
FONT_SIZE_PT = 8
FONT_WEIGHT = "Bold"
FONT_WEIGHT_VALUE = 700

DRAG_ALPHA = 120
DRAG_WIDTH_PX = 2
DRAG_PEN_STYLE = "DashLine"
DRAG_PEN_STYLE_VALUE = 2

SOLID_PEN_STYLE = "SolidLine"
NO_PEN_STYLE = "NoPen"
NO_PEN_WIDTH_PX = 0
NO_BRUSH = "NoBrush"

ALIGN_CENTER = "AlignCenter"
ALIGN_CENTER_VALUE = 132

DEFAULT_PHASE = 0
DEFAULT_PCT = 50
DEFAULT_OFFSET = 0
NO_BOT_ID = ""
ORIGIN_POINT = (0.0, 0.0)

LEFT_BUTTON = "LeftButton"
RIGHT_BUTTON = "RightButton"
MIDDLE_BUTTON = "MiddleButton"
NO_BUTTON = "NoButton"
BUTTON_VALUES = {
    NO_BUTTON: 0,
    LEFT_BUTTON: 1,
    RIGHT_BUTTON: 2,
    MIDDLE_BUTTON: 4,
}

POINTING_HAND_CURSOR = "PointingHandCursor"
POINTING_HAND_CURSOR_VALUE = 13
ARROW_CURSOR = "ArrowCursor"
ARROW_CURSOR_VALUE = 0
CURSOR_VALUES = {
    ARROW_CURSOR: ARROW_CURSOR_VALUE,
    POINTING_HAND_CURSOR: POINTING_HAND_CURSOR_VALUE,
}

PRESS_EVENT = "press"
MOVE_EVENT = "move"
RELEASE_EVENT = "release"
EVENT_KINDS = (PRESS_EVENT, MOVE_EVENT, RELEASE_EVENT)

SET_RENDER_HINT = "set_render_hint"
SET_OPACITY = "set_opacity"
SET_PEN = "set_pen"
SET_BRUSH = "set_brush"
SET_GRADIENT_BRUSH = "set_gradient_brush"
SET_FONT = "set_font"
DRAW_PATH = "draw_path"
DRAW_ELLIPSE = "draw_ellipse"
DRAW_POLYGON = "draw_polygon"
DRAW_ROUNDED_RECT = "draw_rounded_rect"
DRAW_TEXT = "draw_text"
DRAW_LINE = "draw_line"
END_PAINTER = "end"
DRAW_CALL_NAMES = (
    SET_RENDER_HINT,
    SET_OPACITY,
    SET_PEN,
    SET_BRUSH,
    SET_GRADIENT_BRUSH,
    SET_FONT,
    DRAW_PATH,
    DRAW_ELLIPSE,
    DRAW_POLYGON,
    DRAW_ROUNDED_RECT,
    DRAW_TEXT,
    DRAW_LINE,
    END_PAINTER,
)

TAB_BOT_CENTER = "tab.bot_center"
TAB_WIRE_OFFSET = "tab.wire_offset"
TAB_BOT_AT_POS = "tab.bot_at_pos"
TAB_START_WIRE_DRAG = "tab.start_wire_drag"
TAB_WIRE_AT_POS = "tab.wire_at_pos"
TAB_SHOW_DISCONNECT_MENU = "tab.show_disconnect_menu"
TAB_UPDATE_WIRE_DRAG = "tab.update_wire_drag"
TAB_FINISH_WIRE_DRAG = "tab.finish_wire_drag"
SET_CURSOR = "canvas.set_cursor"
BASE_PRESS = "base.mouse_press"
BASE_MOVE = "base.mouse_move"
BASE_RELEASE = "base.mouse_release"
ROUTE_NAMES = (
    TAB_BOT_CENTER,
    TAB_WIRE_OFFSET,
    TAB_BOT_AT_POS,
    TAB_START_WIRE_DRAG,
    TAB_WIRE_AT_POS,
    TAB_SHOW_DISCONNECT_MENU,
    TAB_UPDATE_WIRE_DRAG,
    TAB_FINISH_WIRE_DRAG,
    SET_CURSOR,
    BASE_PRESS,
    BASE_MOVE,
    BASE_RELEASE,
)

ACTIONS: dict = {}
SIGNALS: tuple = ()
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()

EVENT_REFUSAL = "a mouse event is a kind, a button and a position, not {kind}"

Call = list
Point = tuple


def as_point(value: Any) -> list:
    """One position as the pair of decimals the drawing library stores."""
    return [float(value[0]), float(value[1])]


def is_finite_point(value: Any) -> bool:
    """True when both coordinates are numbers the drawing library keeps.

    The library drops a point at infinity or at not-a-number rather
    than storing it, so a curve reaching one is never built.
    """
    return math.isfinite(value[0]) and math.isfinite(value[1])


def is_point(value: Any) -> bool:
    """True when `value` is a position the sheet will draw to.

    Nothing is not a position, and neither is the origin: the drawing
    library treats a point at (0, 0) as empty, so a bot sitting exactly
    on the origin is skipped the same way a missing bot is.
    """
    if value is None:
        return False
    return tuple(value) != ORIGIN_POINT


def opacity_percent(declared: Any) -> int:
    """The wire opacity as a whole number from 0 to 100.

    A value below 0 reads as 0 and one above 100 reads as 100. Anything
    that is not a number is refused, which is what the shipped sheet
    does with the operator's opacity slider value.
    """
    return max(OPACITY_MIN_PCT, min(OPACITY_MAX_PCT, int(declared)))


def opacity_fraction(declared: Any) -> float:
    """The wire opacity as a fraction of one."""
    return opacity_percent(declared) / OPACITY_SCALE


def theme(key: Any) -> dict:
    """The five wire colours of one theme, falling back to Quantum."""
    return THEME_COLORS.get(key, THEME_COLORS[THEME_FALLBACK_KEY])


def with_alpha(color: Any, alpha: int) -> list:
    """One colour at a different see-through level."""
    red, green, blue, _alpha = tuple(color)
    return [red, green, blue, alpha]


def slack_for_offset(offset: Any) -> float:
    """The cable slack one wire hangs with, from its pair offset."""
    try:
        shift = float(offset or 0.0)
    except (TypeError, ValueError):
        shift = 0.0
    return max(CATENARY_MIN_SLACK, CATENARY_SLACK_RATIO + shift * CATENARY_OFFSET_SLACK)


def catenary_parameter(span_px: Any, drop_px: Any, length_px: Any) -> Optional[float]:
    """Return the catenary parameter a for one span, drop and cable length.

    With ``u = span / 2a`` the curve satisfies ``sinh(u) / u = sqrt(length^2 -
    drop^2) / span``; both sides are ratios, solved by halving the interval
    CATENARY_SOLVE_STEPS times, and the answer is None when no curve exists.
    """
    span = abs(float(span_px))
    drop = float(drop_px)
    length = float(length_px)
    if span <= 0.0 or not math.isfinite(length):
        return None
    if length <= math.hypot(span, drop):
        return None
    wanted_ratio = math.sqrt(length * length - drop * drop) / span
    ceiling_ratio = math.sinh(CATENARY_U_MAX) / CATENARY_U_MAX
    if wanted_ratio >= ceiling_ratio:
        return None
    low = CATENARY_U_MIN
    high = CATENARY_U_MAX
    for _step in range(CATENARY_SOLVE_STEPS):
        middle = (low + high) / HALF
        held_ratio = math.sinh(middle) / middle
        if held_ratio > wanted_ratio:
            high = middle
        else:
            low = middle
    return span / (HALF * (low + high) / HALF)


def catenary_curve(
    src: Any,
    tgt: Any,
    slack_ratio: Any = CATENARY_SLACK_RATIO,
    samples: Any = CATENARY_SAMPLES,
) -> dict:
    """Return the hanging wire between two bots, sampled into points.

    ``points`` runs from src to tgt and ``flattest`` indexes the point where
    the curve is least steep, which is the lowest point of the hanging wire.
    """
    x_from, y_from = float(src[0]), float(src[1])
    x_to, y_to = float(tgt[0]), float(tgt[1])
    count = max(2, int(samples))
    span = x_to - x_from
    drop = y_to - y_from
    length = math.hypot(span, drop) * (1.0 + max(0.0, float(slack_ratio)))
    a = catenary_parameter(span, drop, length)
    if a is None:
        straight = [
            [
                x_from + span * at / (count - 1),
                y_from + drop * at / (count - 1),
            ]
            for at in range(count)
        ]
        return {"points": straight, "flattest": count // HALF_INDEX}
    flipped = span < 0.0
    if flipped:
        x_from, y_from, x_to, y_to = x_to, y_to, x_from, y_from
        span, drop = -span, -drop
    vertex_x = x_from + span / HALF + a * math.atanh(drop / length)
    lift = y_from + a * math.cosh((x_from - vertex_x) / a)
    points = []
    for at in range(count):
        x_at = x_from + span * at / (count - 1)
        points.append([x_at, lift - a * math.cosh((x_at - vertex_x) / a)])
    if flipped:
        points.reverse()
    low = min(max(vertex_x, x_from), x_to)
    flattest = int(round((low - x_from) / span * (count - 1)))
    if flipped:
        flattest = count - 1 - flattest
    return {"points": points, "flattest": max(0, min(count - 1, flattest))}


def catenary_elements(points: Any) -> list:
    """The sampled hanging wire as the drawing library stores it.

    A first point the library refuses leaves nothing at all, and every later
    point it refuses is dropped.
    """
    placed = [one for one in points if is_finite_point(one)]
    if not placed or not is_finite_point(points[0] if points else None):
        return []
    elements = [[MOVE_TO_ELEMENT] + as_point(placed[0])]
    for one in placed[1:]:
        elements.append([LINE_TO_ELEMENT] + as_point(one))
    return elements


def rects_overlap(first: Any, second: Any, gap: Any = BADGE_GAP_PX) -> bool:
    """True when two badge rectangles sit within `gap` pixels of each other."""
    left, top, width, height = (float(one) for one in first)
    other_left, other_top, other_width, other_height = (float(one) for one in second)
    return (
        left - gap < other_left + other_width
        and other_left - gap < left + width
        and top - gap < other_top + other_height
        and other_top - gap < top + height
    )


def badge_order(points: Any, flattest: Any) -> list:
    """Every place a badge may sit, the flattest first and then outward."""
    count = len(points)
    start = max(0, min(count - 1, int(flattest)))
    order = [start]
    for step in range(1, count):
        for at in (start - step, start + step):
            if 0 <= at < count:
                order.append(at)
    return order


def place_badge(points: Any, flattest: Any, advance_px: Any, placed: Any) -> list:
    """Return one wire's badge rectangle, clear of every rectangle in `placed`.

    Walks the curve outward from its flattest point, then pushes the badge down
    in BADGE_PUSH_PX steps up to BADGE_PUSH_TRIES times.
    """
    for at in badge_order(points, flattest):
        box = badge_rect(points[at], advance_px)
        if not any(rects_overlap(box, one) for one in placed):
            return box
    box = badge_rect(points[max(0, min(len(points) - 1, int(flattest)))], advance_px)
    for step in range(1, BADGE_PUSH_TRIES + 1):
        pushed = [box[0], box[1] + step * BADGE_PUSH_PX, box[2], box[3]]
        if not any(rects_overlap(pushed, one) for one in placed):
            return pushed
    return box


def no_advance(label: Any) -> int:
    """The printed width of `label` when the caller measures no text."""
    return NO_ADVANCE_PX


def pulse_percent(phase: Any) -> float:
    """How far along the wire the travelling dot sits, from 0 to 1."""
    return math.sin(phase) * PULSE_PHASE_SCALE + PULSE_PHASE_OFFSET


def arrow_points(arrow_pt: Any, arrow_prev: Any) -> list:
    """The three corners of the direction arrow.

    The arrow points the way the wire runs. A wire with no length keeps
    a length of one so the arrow still has a direction.
    """
    dx = arrow_pt[0] - arrow_prev[0]
    dy = arrow_pt[1] - arrow_prev[1]
    length = math.sqrt(dx * dx + dy * dy) or ZERO_LENGTH_FALLBACK
    dx /= length
    dy /= length
    size = ARROW_SIZE_PX
    return [
        as_point(arrow_pt),
        as_point(
            [
                arrow_pt[0] - size * dx + size * ARROW_SIDE_RATIO * dy,
                arrow_pt[1] - size * dy - size * ARROW_SIDE_RATIO * dx,
            ]
        ),
        as_point(
            [
                arrow_pt[0] - size * dx - size * ARROW_SIDE_RATIO * dy,
                arrow_pt[1] - size * dy + size * ARROW_SIDE_RATIO * dx,
            ]
        ),
    ]


def label_text(pct: Any) -> str:
    """The wording on one wire's badge."""
    return LABEL_FORMAT.format(pct=pct)


def badge_rect(label_pt: Any, advance_px: Any) -> list:
    """The badge behind the percentage, centred on the curve's middle."""
    width = advance_px + BADGE_PADDING_PX
    return [
        label_pt[0] - width / BADGE_HALF_DIVISOR,
        label_pt[1] + BADGE_TOP_OFFSET_PX,
        float(width),
        float(BADGE_HEIGHT_PX),
    ]


def solid_pen(color: Any, width_px: Any) -> Call:
    """A drawing call setting a plain line of one colour and width."""
    return [SET_PEN, list(color), width_px, SOLID_PEN_STYLE]


def no_pen() -> Call:
    """A drawing call turning the outline off."""
    return [SET_PEN, None, NO_PEN_WIDTH_PX, NO_PEN_STYLE]


WIRE_DRAWN = "wire.drawn"
WIRE_SKIPPED = "wire.skipped"
DRAG_DISCONNECT = "drag.disconnect"
DRAG_CONNECT = "drag.connect"
DRAG_LOOSE = "drag.loose"
PAINT_NOTHING = "paint.nothing"
PAINT_BRANCHES = (
    WIRE_DRAWN,
    WIRE_SKIPPED,
    DRAG_DISCONNECT,
    DRAG_CONNECT,
    DRAG_LOOSE,
    PAINT_NOTHING,
)


def point_at(points: Any, percent: Any) -> list:
    """The sampled point at `percent` along the wire, from 0 to 1."""
    count = len(points)
    if not count:
        return list(ORIGIN_POINT)
    share = max(0.0, min(1.0, float(percent)))
    return as_point(points[int(round(share * (count - 1)))])


def wire_calls(
    points: Any,
    badge: Any,
    color1: Any,
    color2: Any,
    phase: Any,
    pct: Any,
    into: Optional[list] = None,
) -> list:
    """Every drawing operation one wire makes, in the order it makes them.

    A wide faint line, a narrower brighter one and the wire itself, then
    the travelling dot, the direction arrow and the percentage badge that
    ``place_badge`` already found room for.
    """
    calls = [] if into is None else into
    elements = catenary_elements(points)
    calls.append(solid_pen(with_alpha(color1, GLOW_ALPHA), GLOW_WIDTH_PX))
    calls.append([SET_BRUSH, NO_BRUSH])
    calls.append([DRAW_PATH, elements])
    calls.append(solid_pen(with_alpha(color1, MID_GLOW_ALPHA), MID_GLOW_WIDTH_PX))
    calls.append([DRAW_PATH, elements])
    calls.append(solid_pen(color1, CORE_WIDTH_PX))
    calls.append([DRAW_PATH, elements])

    pulse_pt = point_at(points, pulse_percent(phase))
    calls.append(
        [
            SET_GRADIENT_BRUSH,
            as_point(pulse_pt),
            float(PULSE_GRADIENT_RADIUS_PX),
            [
                [PULSE_CENTRE_STOP, with_alpha(color2, PULSE_ALPHA)],
                [PULSE_EDGE_STOP, list(PULSE_EDGE_COLOR)],
            ],
        ]
    )
    calls.append(no_pen())
    calls.append([DRAW_ELLIPSE, as_point(pulse_pt), PULSE_RADIUS_PX, PULSE_RADIUS_PX])

    arrow_pt = point_at(points, ARROW_PERCENT)
    arrow_prev = point_at(points, ARROW_BACK_PERCENT)
    calls.append(solid_pen(color1, ARROW_WIDTH_PX))
    calls.append([SET_BRUSH, list(color1)])
    calls.append([DRAW_POLYGON, arrow_points(arrow_pt, arrow_prev)])

    label = label_text(pct)
    calls.append([SET_FONT, FONT_FAMILY, FONT_SIZE_PT, FONT_WEIGHT])
    calls.append([SET_BRUSH, list(BADGE_FILL)])
    calls.append(no_pen())
    calls.append([DRAW_ROUNDED_RECT, list(badge), BADGE_CORNER_PX, BADGE_CORNER_PX])
    calls.append(solid_pen(color1, LABEL_WIDTH_PX))
    calls.append([DRAW_TEXT, list(badge), ALIGN_CENTER, label])
    return calls


class WireCanvasModel:
    """The see-through sheet that draws the wires between bots.

    Reads the bot positions and the wire list from the visualizer tab it
    is given. ``paint`` builds the ordered list of drawing operations and
    ``press``, ``move`` and ``release`` route the mouse back to that tab.
    Every step is recorded in the order the shipped sheet takes it.
    """

    def __init__(self, tab: Any) -> None:
        self.tab = tab
        self.accessible_name = CANVAS_ACCESSIBLE_NAME
        self.style_sheet = CANVAS_STYLE
        self.attributes = [list(one) for one in CANVAS_ATTRIBUTES]
        self.cursor: Optional[str] = None
        self.calls: list = []
        self.draw_calls: list = []
        self.paint_branches: list = []
        self.badges: list = []

    def set_cursor(self, shape: str) -> None:
        """Change the mouse pointer over the sheet."""
        self.cursor = shape
        self.calls.append([SET_CURSOR, shape])

    def press(self, button: Any, pos: Any) -> None:
        """A mouse button pressed at `pos`.

        The left button on a bot starts a wire. The right button on a
        wire opens the disconnect menu. Anything else goes to the plain
        handler underneath.
        """
        if button == LEFT_BUTTON:
            bot_id = self.tab.bot_at_pos(pos)
            if bot_id:
                self.tab.start_wire_drag(bot_id, pos)
                return
        elif button == RIGHT_BUTTON:
            wire = self.tab.wire_at_pos(pos)
            if wire:
                self.tab.show_disconnect_menu(pos, wire)
                return
        self.calls.append([BASE_PRESS])

    def move(self, pos: Any) -> None:
        """The mouse moved to `pos`.

        While a wire is being dragged the drag follows the mouse.
        Otherwise the pointer turns into a hand over a wire.
        """
        if self.tab.dragging_wire:
            self.tab.update_wire_drag(pos)
            return
        wire = self.tab.wire_at_pos(pos)
        if wire:
            self.set_cursor(POINTING_HAND_CURSOR)
        else:
            self.set_cursor(ARROW_CURSOR)
        self.calls.append([BASE_MOVE])

    def release(self, button: Any, pos: Any) -> None:
        """A mouse button released at `pos`, which ends a drag."""
        if button == LEFT_BUTTON and self.tab.dragging_wire:
            self.tab.finish_wire_drag(pos)
            return
        self.calls.append([BASE_RELEASE])

    def apply(self, events: Any) -> None:
        """Run each mouse event in order; each is a kind, a button and a point."""
        for event in events:
            kind, button, x, y = event
            pos = (x, y)
            if kind == PRESS_EVENT:
                self.press(button, pos)
            elif kind == MOVE_EVENT:
                self.move(pos)
            elif kind == RELEASE_EVENT:
                self.release(button, pos)
            else:
                raise ValueError(EVENT_REFUSAL.format(kind=kind))

    def paint(self, advance: Callable = no_advance) -> list:
        """Build the drawing programme and return it.

        Nothing is drawn while there is no wire and no drag. Every hanging wire
        is measured first so ``place_badge`` keeps the percentage badges apart,
        then each wire's operations are appended in order.
        """
        self.draw_calls = []
        self.paint_branches = []
        self.badges = []
        tab = self.tab
        if not tab.wires and not tab.dragging_wire:
            self.paint_branches.append(PAINT_NOTHING)
            return self.draw_calls

        self.draw_calls.append([SET_RENDER_HINT, RENDER_HINT, RENDER_HINT_VALUE])
        declared = getattr(tab, "wire_opacity_pct", DEFAULT_OPACITY_PCT)
        self.draw_calls.append([SET_OPACITY, opacity_fraction(declared)])
        colors = theme(tab.theme_key)

        hanging = []
        for wire in tab.wires:
            src = tab.bot_center(wire["source_id"])
            tgt = tab.bot_center(wire["target_id"])
            if not is_point(src) or not is_point(tgt):
                self.paint_branches.append(WIRE_SKIPPED)
                continue
            self.paint_branches.append(WIRE_DRAWN)
            curve = catenary_curve(src, tgt, slack_for_offset(tab.wire_offset(wire)))
            badge = place_badge(
                curve["points"],
                curve["flattest"],
                advance(label_text(wire.get("pct", DEFAULT_PCT))),
                self.badges,
            )
            self.badges.append(badge)
            hanging.append((wire, curve, badge))

        for wire, curve, badge in hanging:
            wire_calls(
                curve["points"],
                badge,
                colors["accent"],
                colors["accent2"],
                wire.get("phase", DEFAULT_PHASE),
                wire.get("pct", DEFAULT_PCT),
                self.draw_calls,
            )

        if tab.dragging_wire and is_point(tab.wire_mouse_pos):
            start = tab.bot_center(tab.wire_start_id)
            if is_point(start):
                hover_id = tab.bot_at_pos(tab.wire_mouse_pos)
                is_disconnect = False
                if hover_id and hover_id != tab.wire_start_id:
                    is_disconnect = any(
                        one["source_id"] == tab.wire_start_id
                        and one["target_id"] == hover_id
                        for one in tab.wires
                    )
                if is_disconnect:
                    color = colors["error"]
                    self.paint_branches.append(DRAG_DISCONNECT)
                elif hover_id and hover_id != tab.wire_start_id:
                    color = colors["success"]
                    self.paint_branches.append(DRAG_CONNECT)
                else:
                    color = colors["warning"]
                    self.paint_branches.append(DRAG_LOOSE)
                self.draw_calls.append(
                    [
                        SET_PEN,
                        with_alpha(color, DRAG_ALPHA),
                        DRAG_WIDTH_PX,
                        DRAG_PEN_STYLE,
                    ]
                )
                self.draw_calls.append(
                    [DRAW_LINE, as_point(start), as_point(tab.wire_mouse_pos)]
                )

        self.draw_calls.append([END_PAINTER])
        return self.draw_calls


POINT_KEY_FORMAT = "{x!r},{y!r}"
WIRE_KEY_FORMAT = "{source_id}->{target_id}"


def point_key(pos: Any) -> str:
    """One position as the text a lookup table is keyed by."""
    return POINT_KEY_FORMAT.format(x=float(pos[0]), y=float(pos[1]))


def wire_key(wire: Any) -> str:
    """One wire as the text a lookup table is keyed by."""
    return WIRE_KEY_FORMAT.format(
        source_id=wire["source_id"], target_id=wire["target_id"]
    )


class CanvasTabState:
    """The visualizer tab as the sheet sees it, held as plain values.

    The sheet asks the tab where each bot is, which bot or wire is under
    a point, and how far a wire is bowed. This holds those answers as
    tables so the sheet can be driven with no visualizer built, and
    records every question in the order it is asked.
    """

    def __init__(
        self,
        wires: Any = None,
        bot_centers: Any = None,
        wire_offsets: Any = None,
        bot_hits: Any = None,
        wire_hits: Any = None,
        dragging_wire: Any = False,
        wire_start_id: Any = NO_BOT_ID,
        wire_mouse_pos: Any = None,
        theme_key: Any = THEME_FALLBACK_KEY,
        wire_opacity_pct: Any = DEFAULT_OPACITY_PCT,
    ) -> None:
        self.wires = list(wires or [])
        self.bot_centers = dict(bot_centers or {})
        self.wire_offsets = dict(wire_offsets or {})
        self.bot_hits = dict(bot_hits or {})
        self.wire_hits = dict(wire_hits or {})
        self.dragging_wire = dragging_wire
        self.wire_start_id = wire_start_id
        self.wire_mouse_pos = wire_mouse_pos
        self.theme_key = theme_key
        self.wire_opacity_pct = wire_opacity_pct
        self.calls: list = []

    def record(self, *call: Any) -> None:
        """Keep one question the sheet asked, in the order it was asked."""
        self.calls.append(list(call))

    def bot_center(self, bot_id: Any) -> Any:
        """Where one bot sits, or nothing when the tab holds no such bot."""
        self.record(TAB_BOT_CENTER, bot_id)
        return self.bot_centers.get(bot_id)

    def bot_at_pos(self, pos: Any) -> Any:
        """Which bot is under `pos`, or empty text when none is."""
        self.record(TAB_BOT_AT_POS, list(pos))
        return self.bot_hits.get(point_key(pos), NO_BOT_ID)

    def wire_at_pos(self, pos: Any) -> Any:
        """Which wire is under `pos`, or nothing when none is."""
        self.record(TAB_WIRE_AT_POS, list(pos))
        found = self.wire_hits.get(point_key(pos))
        return None if found is None else self.wires[found]

    def wire_offset(self, wire: Any) -> Any:
        """How far one wire is bowed away from the straight line."""
        self.record(TAB_WIRE_OFFSET, wire_key(wire))
        return self.wire_offsets.get(wire_key(wire), DEFAULT_OFFSET)

    def start_wire_drag(self, bot_id: Any, pos: Any) -> None:
        """Begin dragging a new wire out of one bot."""
        self.record(TAB_START_WIRE_DRAG, bot_id, list(pos))
        self.dragging_wire = True
        self.wire_start_id = bot_id
        self.wire_mouse_pos = tuple(pos)

    def update_wire_drag(self, pos: Any) -> None:
        """Move the loose end of the wire being dragged."""
        self.record(TAB_UPDATE_WIRE_DRAG, list(pos))
        self.wire_mouse_pos = tuple(pos)

    def finish_wire_drag(self, pos: Any) -> None:
        """Let go of the wire being dragged."""
        self.record(TAB_FINISH_WIRE_DRAG, list(pos))
        self.dragging_wire = False
        self.wire_mouse_pos = None
        self.wire_start_id = NO_BOT_ID

    def show_disconnect_menu(self, pos: Any, wire: Any) -> None:
        """Open the menu that removes one wire."""
        self.record(TAB_SHOW_DISCONNECT_MENU, list(pos), wire_key(wire))

    def state(self) -> dict:
        """Every value this tab holds, as one dict, with the two bag orders repeated as lists."""
        return {
            "wires": [dict(one) for one in self.wires],
            "bot_center_order": list(self.bot_centers),
            "wire_order": [wire_key(one) for one in self.wires],
            "bot_centers": {
                name: list(point) if point is not None else None
                for name, point in self.bot_centers.items()
            },
            "wire_offsets": dict(self.wire_offsets),
            "bot_hits": dict(self.bot_hits),
            "wire_hits": dict(self.wire_hits),
            "dragging_wire": self.dragging_wire,
            "wire_start_id": self.wire_start_id,
            "wire_mouse_pos": (
                None if self.wire_mouse_pos is None else list(self.wire_mouse_pos)
            ),
            "theme_key": self.theme_key,
            "wire_opacity_pct": self.wire_opacity_pct,
            "calls": [list(one) for one in self.calls],
        }


def measured_advance(advances: Any) -> Callable:
    """A text measurer reading widths the caller already worked out."""

    def advance(label: Any) -> int:
        return dict(advances).get(label, NO_ADVANCE_PX)

    return advance


def build_view_model(
    model: WireCanvasModel,
    events: Any = None,
    advance: Optional[Callable] = None,
) -> dict:
    """Return every value the wire sheet holds as one dict.

    `events` runs a list of mouse events before the values are read, as the
    operator does when dragging a wire, and `advance` measures the printed
    width of a label for the caller's own drawing engine.
    """
    if events:
        model.apply(events)
    drawing_calls = model.paint(advance or no_advance)
    tab = model.tab
    return {
        "accessible_name": model.accessible_name,
        "style_sheet": model.style_sheet,
        "attributes": [list(one) for one in model.attributes],
        "render_hint": {"name": RENDER_HINT, "value": RENDER_HINT_VALUE},
        "opacity": {
            "min_pct": OPACITY_MIN_PCT,
            "max_pct": OPACITY_MAX_PCT,
            "default_pct": DEFAULT_OPACITY_PCT,
            "scale": OPACITY_SCALE,
        },
        "theme": {
            "key": tab.theme_key,
            "fallback_key": THEME_FALLBACK_KEY,
            "keys": list(THEME_KEYS),
            "color_names": list(THEME_COLOR_NAMES),
            "opaque_alpha": OPAQUE_ALPHA,
            "alpha_scale": ALPHA_SCALE,
            "alpha_unit": ALPHA_UNIT,
            "table": {
                name: {color: list(value) for color, value in sorted(colors.items())}
                for name, colors in THEME_COLORS.items()
            },
            "colors": {
                color: list(value)
                for color, value in sorted(theme(tab.theme_key).items())
            },
        },
        "curve": {
            "slack_ratio": CATENARY_SLACK_RATIO,
            "min_slack": CATENARY_MIN_SLACK,
            "offset_slack": CATENARY_OFFSET_SLACK,
            "samples": CATENARY_SAMPLES,
            "solve_steps": CATENARY_SOLVE_STEPS,
            "element_names": [MOVE_TO_ELEMENT, LINE_TO_ELEMENT],
        },
        "glow": {
            "alpha": GLOW_ALPHA,
            "width_px": GLOW_WIDTH_PX,
            "mid_alpha": MID_GLOW_ALPHA,
            "mid_width_px": MID_GLOW_WIDTH_PX,
            "core_width_px": CORE_WIDTH_PX,
        },
        "pulse": {
            "phase_scale": PULSE_PHASE_SCALE,
            "phase_offset": PULSE_PHASE_OFFSET,
            "alpha": PULSE_ALPHA,
            "gradient_radius_px": PULSE_GRADIENT_RADIUS_PX,
            "radius_px": PULSE_RADIUS_PX,
            "centre_stop": PULSE_CENTRE_STOP,
            "edge_stop": PULSE_EDGE_STOP,
            "edge_color": list(PULSE_EDGE_COLOR),
        },
        "arrow": {
            "percent": ARROW_PERCENT,
            "back_percent": ARROW_BACK_PERCENT,
            "size_px": ARROW_SIZE_PX,
            "side_ratio": ARROW_SIDE_RATIO,
            "width_px": ARROW_WIDTH_PX,
            "zero_length_fallback": ZERO_LENGTH_FALLBACK,
        },
        "badge": {
            "label_width_px": LABEL_WIDTH_PX,
            "padding_px": BADGE_PADDING_PX,
            "height_px": BADGE_HEIGHT_PX,
            "top_offset_px": BADGE_TOP_OFFSET_PX,
            "half_divisor": BADGE_HALF_DIVISOR,
            "corner_px": BADGE_CORNER_PX,
            "fill": list(BADGE_FILL),
            "no_advance_px": NO_ADVANCE_PX,
            "gap_px": BADGE_GAP_PX,
            "push_px": BADGE_PUSH_PX,
            "push_tries": BADGE_PUSH_TRIES,
            "placed": [list(one) for one in model.badges],
        },
        "font": {
            "family": FONT_FAMILY,
            "size_pt": FONT_SIZE_PT,
            "weight": FONT_WEIGHT,
            "weight_value": FONT_WEIGHT_VALUE,
        },
        "drag": {
            "alpha": DRAG_ALPHA,
            "width_px": DRAG_WIDTH_PX,
            "pen_style": DRAG_PEN_STYLE,
            "pen_style_value": DRAG_PEN_STYLE_VALUE,
        },
        "pens": {
            "solid_style": SOLID_PEN_STYLE,
            "no_pen_style": NO_PEN_STYLE,
            "no_pen_width_px": NO_PEN_WIDTH_PX,
            "no_brush": NO_BRUSH,
        },
        "alignment": {"name": ALIGN_CENTER, "value": ALIGN_CENTER_VALUE},
        "defaults": {
            "phase": DEFAULT_PHASE,
            "pct": DEFAULT_PCT,
            "offset": DEFAULT_OFFSET,
            "no_bot_id": NO_BOT_ID,
            "origin_point": list(ORIGIN_POINT),
        },
        "buttons": dict(BUTTON_VALUES),
        "cursors": dict(CURSOR_VALUES),
        "cursor": model.cursor,
        "event_kinds": list(EVENT_KINDS),
        "draw_call_names": list(DRAW_CALL_NAMES),
        "route_names": list(ROUTE_NAMES),
        "paint_branch_names": list(PAINT_BRANCHES),
        "formats": {
            "label": LABEL_FORMAT,
            "event_refusal": EVENT_REFUSAL,
            "point_key": POINT_KEY_FORMAT,
            "wire_key": WIRE_KEY_FORMAT,
        },
        "actions": dict(ACTIONS),
        "signals": list(SIGNALS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "drawing_calls": [list(one) for one in drawing_calls],
        "paint_branches": list(model.paint_branches),
        "calls": [list(one) for one in model.calls],
        "tab": tab.state(),
    }


CANVAS_MODEL = WireCanvasModel(CanvasTabState())


def view_model(params: dict) -> dict:
    """Bridge handler for ``wire_canvas.state``.

    ``tab`` builds a fresh sheet over the wires and bot positions the
    renderer sends, and ``reset`` clears the sheet without changing them.
    ``events`` runs mouse events before the values are read. ``advances``
    carries the printed width of each badge label, which the renderer
    measures with its own fonts.
    """
    global CANVAS_MODEL
    if "tab" in params:
        CANVAS_MODEL = WireCanvasModel(CanvasTabState(**(params.get("tab") or {})))
    elif params.get("reset", False):
        CANVAS_MODEL = WireCanvasModel(CanvasTabState())
    return build_view_model(
        CANVAS_MODEL,
        params.get("events"),
        advance=measured_advance(params.get("advances") or {}),
    )
