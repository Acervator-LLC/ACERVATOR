"""bot_node_surface.py -- the locust card drawn for one bot.

Describes the small card the Bot Visualizer draws for every running bot.
The card is an insect: a head with one eye, a chest plate, a tail, two
wings, two feelers and six legs. The eye and the chest carry the bot
state as a colour. The tail carries the profit or loss. A trade sends a
ring outward and throws a few specks of light.

``BotNodeModel`` is the card. ``paint`` returns the ordered list of
drawing operations, each with its own coordinates, colours, widths and
sizes. ``set_theme``, ``set_bot_data`` and ``animate`` are the three
ways the visualizer changes the card, and each records what it did.
``build_view_model`` returns every value the card holds as one dict.

Three things belong outside this screen: the start angle and the speck
speeds, which the shipped card draws from the operating system, and
whether an identifier is hidden, which the privacy register answers.
All three are handed in, so nothing here reads a clock, a random source
or a settings file. ``plain_text`` is the value used when the caller
hands in no privacy answer.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``bot_node.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.visualizer.bot_node`` or its colour table, so a value changed
on one side alone is reported. Nothing here imports Qt, and nothing runs
at import time except building the tables below.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Optional

from ...core.fmt import fmt_pnl, fmt_price

METHOD = "bot_node.state"

MIN_WIDTH_PX = 112
MIN_HEIGHT_PX = 98

RENDER_HINT = "Antialiasing"
RENDER_HINT_VALUE = 1

OPAQUE_ALPHA = 255
THEME_FALLBACK_KEY = "quantum"
THEME_KEYS = ("nebula", "matrix", "quantum", "ocean")
THEME_COLOR_NAMES = (
    "bg",
    "accent",
    "accent2",
    "success",
    "warning",
    "error",
    "text",
    "particle",
)

THEME_COLORS = {
    "nebula": {
        "bg": (8, 4, 20, OPAQUE_ALPHA),
        "accent": (120, 80, 255, OPAQUE_ALPHA),
        "accent2": (255, 60, 180, OPAQUE_ALPHA),
        "success": (0, 255, 160, OPAQUE_ALPHA),
        "warning": (255, 200, 0, OPAQUE_ALPHA),
        "error": (255, 40, 80, OPAQUE_ALPHA),
        "text": (200, 200, 240, OPAQUE_ALPHA),
        "particle": (180, 120, 255, 80),
    },
    "matrix": {
        "bg": (0, 8, 0, OPAQUE_ALPHA),
        "accent": (0, 255, 65, OPAQUE_ALPHA),
        "accent2": (0, 180, 45, OPAQUE_ALPHA),
        "success": (0, 255, 100, OPAQUE_ALPHA),
        "warning": (200, 255, 0, OPAQUE_ALPHA),
        "error": (255, 0, 0, OPAQUE_ALPHA),
        "text": (0, 220, 55, OPAQUE_ALPHA),
        "particle": (0, 255, 65, 60),
    },
    "quantum": {
        "bg": (10, 15, 25, OPAQUE_ALPHA),
        "accent": (0, 200, 255, OPAQUE_ALPHA),
        "accent2": (0, 255, 200, OPAQUE_ALPHA),
        "success": (0, 255, 136, OPAQUE_ALPHA),
        "warning": (255, 180, 0, OPAQUE_ALPHA),
        "error": (255, 50, 80, OPAQUE_ALPHA),
        "text": (180, 220, 255, OPAQUE_ALPHA),
        "particle": (0, 200, 255, 60),
    },
    "ocean": {
        "bg": (5, 10, 30, OPAQUE_ALPHA),
        "accent": (0, 150, 255, OPAQUE_ALPHA),
        "accent2": (0, 220, 180, OPAQUE_ALPHA),
        "success": (0, 230, 170, OPAQUE_ALPHA),
        "warning": (255, 200, 50, OPAQUE_ALPHA),
        "error": (255, 60, 90, OPAQUE_ALPHA),
        "text": (160, 200, 240, OPAQUE_ALPHA),
        "particle": (0, 120, 200, 50),
    },
}

IDLE_GREY = (100, 100, 100, OPAQUE_ALPHA)
STOPPED_GREY = (80, 80, 80, OPAQUE_ALPHA)

STATE_RUNNING = "running"
STATE_IDLE = "idle"
STATE_PAUSED = "paused"
STATE_ERROR = "error"
STATE_STOPPED = "stopped"
STATE_COOLDOWN = "cooldown"
STATE_NAMES = (
    STATE_RUNNING,
    STATE_IDLE,
    STATE_PAUSED,
    STATE_ERROR,
    STATE_STOPPED,
    STATE_COOLDOWN,
)

STATE_COLORS = {
    key: {
        STATE_RUNNING: colors["success"],
        STATE_IDLE: IDLE_GREY,
        STATE_PAUSED: colors["warning"],
        STATE_ERROR: colors["error"],
        STATE_STOPPED: STOPPED_GREY,
        STATE_COOLDOWN: colors["warning"],
    }
    for key, colors in THEME_COLORS.items()
}

# The head fill is the card background one step lighter and a leg is the
# state colour one step darker. The drawing library works both steps out
# in colour-wheel terms, so the answers are written out as numbers.
HEAD_FILLS = {
    "nebula": (10, 5, 24, OPAQUE_ALPHA),
    "matrix": (0, 10, 0, OPAQUE_ALPHA),
    "quantum": (12, 18, 30, OPAQUE_ALPHA),
    "ocean": (6, 12, 36, OPAQUE_ALPHA),
}

LEG_COLORS = {
    "nebula": {
        STATE_RUNNING: (0, 212, 133, OPAQUE_ALPHA),
        STATE_IDLE: (83, 83, 83, OPAQUE_ALPHA),
        STATE_PAUSED: (212, 167, 0, OPAQUE_ALPHA),
        STATE_ERROR: (212, 33, 67, OPAQUE_ALPHA),
        STATE_STOPPED: (67, 67, 67, OPAQUE_ALPHA),
        STATE_COOLDOWN: (212, 167, 0, OPAQUE_ALPHA),
    },
    "matrix": {
        STATE_RUNNING: (0, 212, 83, OPAQUE_ALPHA),
        STATE_IDLE: (83, 83, 83, OPAQUE_ALPHA),
        STATE_PAUSED: (167, 212, 0, OPAQUE_ALPHA),
        STATE_ERROR: (212, 0, 0, OPAQUE_ALPHA),
        STATE_STOPPED: (67, 67, 67, OPAQUE_ALPHA),
        STATE_COOLDOWN: (167, 212, 0, OPAQUE_ALPHA),
    },
    "quantum": {
        STATE_RUNNING: (0, 212, 113, OPAQUE_ALPHA),
        STATE_IDLE: (83, 83, 83, OPAQUE_ALPHA),
        STATE_PAUSED: (212, 150, 0, OPAQUE_ALPHA),
        STATE_ERROR: (212, 42, 67, OPAQUE_ALPHA),
        STATE_STOPPED: (67, 67, 67, OPAQUE_ALPHA),
        STATE_COOLDOWN: (212, 150, 0, OPAQUE_ALPHA),
    },
    "ocean": {
        STATE_RUNNING: (0, 192, 142, OPAQUE_ALPHA),
        STATE_IDLE: (83, 83, 83, OPAQUE_ALPHA),
        STATE_PAUSED: (212, 167, 42, OPAQUE_ALPHA),
        STATE_ERROR: (212, 50, 75, OPAQUE_ALPHA),
        STATE_STOPPED: (67, 67, 67, OPAQUE_ALPHA),
        STATE_COOLDOWN: (212, 167, 42, OPAQUE_ALPHA),
    },
}

LEG_FALLBACK_COLORS = {
    "nebula": (167, 167, 200, OPAQUE_ALPHA),
    "matrix": (0, 183, 46, OPAQUE_ALPHA),
    "quantum": (150, 183, 212, OPAQUE_ALPHA),
    "ocean": (133, 167, 200, OPAQUE_ALPHA),
}

DEFAULT_STATE = STATE_IDLE
DEFAULT_SYMBOL = "???"
DEFAULT_MODE = "scrumming"
STATS_KEY = "stats"
STATE_KEY = "state"
SYMBOL_KEY = "symbol"
MODE_KEY = "mode"
BOT_ID_KEY = "bot_id"
PNL_KEY = "realised_pnl"
TRADES_KEY = "total_trades"
PRICE_KEY = "current_price"
VOLUME_KEY = "trade_volume"
ZERO_STAT = 0
NO_BOT_ID = ""

PHASE_MIN = 0
PHASE_MAX = math.pi * 2
PHASE_RATE_PER_S = 1.5
PULSE_DECAY_PER_S = 0.8
PULSE_START = 1.0
PULSE_FLOOR = 0
ANTENNA_DRIVE_START = 1.0
ANTENNA_DECAY_PER_S = 1.0
ANTENNA_DRIVE_FLOOR = 0.0

PARTICLE_COUNT = 5
PARTICLE_VELOCITY_MIN = -30
PARTICLE_VELOCITY_MAX = 30
PARTICLE_LIFE_MIN = 0.5
PARTICLE_LIFE_MAX = 1.5
PARTICLE_SIZE_MIN = 1.5
PARTICLE_SIZE_MAX = 3.5
PARTICLE_DRAWS_EACH = 4
PARTICLE_ALPHA_SCALE = 255
PARTICLE_ALPHA_FLOOR = 0
PARTICLE_LIFE_FLOOR = 0

SCALE_DIVISOR = 52.0

WING_HALF_OPEN = 0.35
WING_RUNNING_BASE = 0.55
WING_RUNNING_SWING = 0.15
WING_RUNNING_PHASE_RATE = 3
WING_TIGHT_OPEN = 0.15
WING_TIGHT_STATES = (STATE_STOPPED, STATE_IDLE)
WING_PULSE_BUMP = 0.3
WING_MAX_OPEN = 1.0

PULSE_RING_BASE_U = 20
PULSE_RING_GROWTH_PX = 40
PULSE_RING_ALPHA = 180
PULSE_RING_WIDTH_PX = 2

GLOW_RADIUS_U = 18
GLOW_ALPHA = 55
GLOW_EDGE_COLOR = (0, 0, 0, 0)
GRADIENT_CENTRE_STOP = 0.0
GRADIENT_EDGE_STOP = 1.0

WING_ALPHA_BASE = 50
WING_ALPHA_SWING = 40
WING_PEN_ALPHA = 100
WING_PEN_WIDTH_PX = 1
WING_PEN_STYLE = "DashLine"
WING_SPREAD_U = 4.5
WING_SPREAD_OPEN_U = 6
WING_LIFT_U = 2
WING_TIP_RATIO = 0.85

PNL_FLOOR_USD = 0.1
PNL_LOG_DIVISOR = 4.0
PNL_MAGNITUDE_MAX = 1.0
ABDOMEN_BASE_ALPHA = 90
ABDOMEN_BASE_SWING = 120
ABDOMEN_TIP_ALPHA = 40
ABDOMEN_TIP_SWING = 60
ABDOMEN_GRADIENT_TOP_U = 2
ABDOMEN_GRADIENT_BOTTOM_U = 18
ABDOMEN_PEN_WIDTH_PX = 1

SEGMENT_COLOR = (0, 0, 0, 120)
SEGMENT_PEN_WIDTH_PX = 1
SEGMENT_COUNT = 3
SEGMENT_TOP_U = 2
SEGMENT_STEP_U = 4
SEGMENT_TAPER_U = 5.5
SEGMENT_TAPER_STEP_U = 0.8

THORAX_GRADIENT_CENTRE_U = 5
THORAX_GRADIENT_RADIUS_U = 10
THORAX_CENTRE_ALPHA = 90
THORAX_EDGE_ALPHA = 30
THORAX_PEN_WIDTH_PX = 2

HEAD_PEN_WIDTH_PX = 2

EYE_RADIUS_U = 1.8
EYE_SWING_U = 0.6
EYE_PHASE_RATE = 3
EYE_CENTRE_U = 16.5
IRIS_ALPHA = 200
IRIS_PEN_WIDTH_PX = 1
IRIS_RADIUS_RATIO = 1.5

ANTENNA_SIGNS = (-1, 1)
ANTENNA_PEN_WIDTH_PX = 1
ANTENNA_SWAY_AMBIENT = 0.4
ANTENNA_AMBIENT_PHASE_RATE = 2
ANTENNA_AMBIENT_OFFSET = 1.0
ANTENNA_SWAY_DRIVEN = 0.8
ANTENNA_DRIVEN_PHASE_RATE = 6
ANTENNA_DRIVEN_OFFSET = 0.5
ANTENNA_BASE_X_U = 2
ANTENNA_BASE_Y_U = 19
ANTENNA_BEND_X_U = 4
ANTENNA_BEND_Y_U = 24
ANTENNA_TIP_X_U = 5
ANTENNA_TIP_Y_U = 28
ANTENNA_TIP_ALPHA = 180
ANTENNA_TIP_RADIUS_PX = 1.2

LEG_SIGNS = (-1, 1)
LEG_PEN_WIDTH_PX = 2
HIND_LEG_PEN_WIDTH_PX = 3
FORE_LEG_U = ((5.5, -8), (8, -4), (9, 3))
MID_LEG_U = ((6.5, -3), (9.5, 1), (10, 8))
HIND_LEG_U = ((6, 1), (11, -4), (10, 10))

BRACKET_ALPHA = 140
BRACKET_PEN_WIDTH_PX = 1
BRACKET_LENGTH_PX = 6
BRACKET_NEAR_INSET_PX = 1
BRACKET_FAR_INSET_PX = 2

CIRCUIT_ALPHA = 110
CIRCUIT_PEN_WIDTH_PX = 1
CIRCUIT_LINE_Y_U = (-6, -8)
CIRCUIT_LINE_HALF_U = 4
CIRCUIT_DOT_X_U = (-4, 4)
CIRCUIT_DOT_Y_U = -7
CIRCUIT_DOT_RADIUS_PX = 1.2

FONT_FAMILY = "Consolas"
SYMBOL_FONT_SIZE_PT = 7
PNL_FONT_SIZE_PT = 7
BOT_ID_FONT_SIZE_PT = 5
FONT_WEIGHT_BOLD = "Bold"
FONT_WEIGHT_NORMAL = "Normal"
FONT_WEIGHT_BOLD_VALUE = 700
FONT_WEIGHT_NORMAL_VALUE = 400

ALIGN_CENTER = "AlignCenter"
ALIGN_CENTER_VALUE = 132

SYMBOL_RECT_TOP_PX = 2
SYMBOL_RECT_HEIGHT_PX = 11
PNL_RECT_BOTTOM_PX = 22
PNL_RECT_HEIGHT_PX = 11
BOT_ID_RECT_BOTTOM_PX = 10
BOT_ID_RECT_HEIGHT_PX = 9
RECT_LEFT_PX = 0
BOT_ID_COLOR = (110, 110, 140, OPAQUE_ALPHA)

MASK_FIELD_ID = "bot_swarm.identifiers"
BOT_ID_LABEL_CHARS = 8
BOT_ID_TOOLTIP_CHARS = 12
TOOLTIP_BOT_MASK = "********"

MILLION = 1e6
THOUSAND = 1e3
VOLUME_MILLIONS_FORMAT = "${value:.1f}M"
VOLUME_THOUSANDS_FORMAT = "${value:.1f}K"
VOLUME_PLAIN_FORMAT = "${value:.0f}"
PRICE_FLOOR_USD = 0
PRICE_DASH = "—"
TOOLTIP_FORMAT = (
    "{symbol}\n"
    "State: {state}\n"
    "Mode: {mode}\n"
    "Trades: {trades}\n"
    "Price: {price}\n"
    "Volume: {volume}\n"
    "P/L: {pnl}\n"
    "Bot: {bot_id}"
)

MOVE_TO_ELEMENT = "MoveToElement"
LINE_TO_ELEMENT = "LineToElement"
CURVE_TO_ELEMENT = "CurveToElement"
CURVE_TO_DATA_ELEMENT = "CurveToDataElement"
PATH_ELEMENT_NAMES = (
    MOVE_TO_ELEMENT,
    LINE_TO_ELEMENT,
    CURVE_TO_ELEMENT,
    CURVE_TO_DATA_ELEMENT,
)
PATH_ORIGIN = (0.0, 0.0)
CUBIC_DIVISOR = 3
CUBIC_CONTROL_WEIGHT = 2
FUZZY_SCALE = 1000000000000.0
FUZZY_NULL_LIMIT = 0.000000000001
CLOSE_SNAP_LIMIT = 1e-12

BODY_PART_NAMES = ("head", "thorax", "abdomen", "wing_l", "wing_r")

SOLID_PEN_STYLE = "SolidLine"
NO_PEN_STYLE = "NoPen"
NO_PEN_WIDTH_PX = 0
NO_BRUSH = "NoBrush"

SET_RENDER_HINT = "set_render_hint"
FILL_RECT = "fill_rect"
SET_PEN = "set_pen"
SET_PEN_COLOR = "set_pen_color"
SET_BRUSH = "set_brush"
SET_RADIAL_BRUSH = "set_radial_brush"
SET_LINEAR_BRUSH = "set_linear_brush"
SET_FONT = "set_font"
DRAW_PATH = "draw_path"
DRAW_ELLIPSE = "draw_ellipse"
DRAW_LINE = "draw_line"
DRAW_TEXT = "draw_text"
END_PAINTER = "end"
DRAW_CALL_NAMES = (
    SET_RENDER_HINT,
    FILL_RECT,
    SET_PEN,
    SET_PEN_COLOR,
    SET_BRUSH,
    SET_RADIAL_BRUSH,
    SET_LINEAR_BRUSH,
    SET_FONT,
    DRAW_PATH,
    DRAW_ELLIPSE,
    DRAW_LINE,
    DRAW_TEXT,
    END_PAINTER,
)

UPDATE_CARD = "card.update"
SET_TOOLTIP = "card.set_tooltip"
ROUTE_NAMES = (UPDATE_CARD, SET_TOOLTIP)

PAINT_NOTHING = "paint.nothing"
PAINT_WHOLE = "paint.whole"
WING_RUNNING = "wing.running"
WING_TIGHT = "wing.tight"
WING_HALF = "wing.half"
WING_PULSED = "wing.pulsed"
PULSE_RING = "pulse.ring"
PARTICLE_DRAWN = "particle.drawn"
PNL_POSITIVE = "pnl.positive"
PNL_NEGATIVE = "pnl.negative"
STATE_KNOWN = "state.known"
STATE_UNKNOWN = "state.unknown"
VOLUME_MILLIONS = "volume.millions"
VOLUME_THOUSANDS = "volume.thousands"
VOLUME_PLAIN = "volume.plain"
PRICE_SHOWN = "price.shown"
PRICE_HIDDEN = "price.hidden"
PAINT_BRANCHES = (
    PAINT_NOTHING,
    PAINT_WHOLE,
    WING_RUNNING,
    WING_TIGHT,
    WING_HALF,
    WING_PULSED,
    PULSE_RING,
    PARTICLE_DRAWN,
    PNL_POSITIVE,
    PNL_NEGATIVE,
    STATE_KNOWN,
    STATE_UNKNOWN,
    VOLUME_MILLIONS,
    VOLUME_THOUSANDS,
    VOLUME_PLAIN,
    PRICE_SHOWN,
    PRICE_HIDDEN,
)

THEME_STEP = "theme"
DATA_STEP = "data"
ANIMATE_STEP = "animate"
STEP_KINDS = (THEME_STEP, DATA_STEP, ANIMATE_STEP)
STEP_REFUSAL = "a card step is a kind and its value, not {kind}"
DRAW_REFUSAL = "five specks need {wanted} draws between 0 and 1, not {given}"

ACTIONS: dict = {}
SIGNALS: tuple = ()
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
SCREEN_ELEMENTS: tuple = ()

Call = list


def plain_text(value: Any, field_id: str, mask: str = "****") -> str:
    """The value as it reads when no identifier is hidden.

    Stands where the privacy register goes. A caller that wants the
    register's answer hands its own function in.
    """
    del field_id, mask
    return str(value)


def as_point(value: Any) -> list:
    """One position as the pair of decimals the drawing library stores."""
    return [float(value[0]), float(value[1])]


def as_color(value: Any) -> list:
    """One colour as its four whole numbers."""
    return [int(one) for one in value]


def with_alpha(color: Any, alpha: Any) -> list:
    """One colour at a different see-through level.

    The drawing library keeps a level between 0 and 255 and pulls any
    value outside that range back to the nearest end.
    """
    red, green, blue, _alpha = tuple(color)
    return [red, green, blue, max(0, min(OPAQUE_ALPHA, int(alpha)))]


def theme(key: Any) -> dict:
    """The eight card colours of one theme, falling back to Quantum."""
    return THEME_COLORS.get(key, THEME_COLORS[THEME_FALLBACK_KEY])


def theme_key_or_fallback(key: Any) -> str:
    """The theme this card paints in, falling back to Quantum."""
    return key if key in THEME_COLORS else THEME_FALLBACK_KEY


def uniform(low: Any, high: Any, draw: Any) -> float:
    """One value between `low` and `high` from a draw between 0 and 1.

    The shipped card takes each draw from the operating system. The
    caller hands the draws in so the same card can be built twice.
    """
    return low + (high - low) * draw


def start_phase(draw: Any) -> float:
    """The angle one card starts its idle movement at."""
    return uniform(PHASE_MIN, PHASE_MAX, draw)


def fuzzy_same(first: Any, second: Any) -> bool:
    """True when the drawing library holds two numbers to be one number.

    Either number being zero puts the test on the gap between them.
    Otherwise the gap is measured against the smaller of the two.
    """
    if first == 0 or second == 0:
        return abs(first - second) <= FUZZY_NULL_LIMIT
    return abs(first - second) * FUZZY_SCALE <= min(abs(first), abs(second))


def same_point(first: Any, second: Any) -> bool:
    """True when the drawing library holds two positions to be one."""
    return fuzzy_same(first[0], second[0]) and fuzzy_same(first[1], second[1])


def is_finite_point(value: Any) -> bool:
    """True when both coordinates are numbers the drawing library keeps."""
    return math.isfinite(value[0]) and math.isfinite(value[1])


class PathBuilder:
    """A shape built the way the drawing library builds one.

    The library drops a step whose coordinates are not finite, drops a
    straight step that lands where the shape already is, and drops a
    curve whose three points are one point. Closing a shape draws a
    straight step back to the start unless the shape is already there.
    """

    def __init__(self) -> None:
        self.elements: list = []
        self.start_index = 0
        self.needs_move = False

    def _last(self) -> list:
        return [self.elements[-1][1], self.elements[-1][2]]

    def _ensure_data(self) -> None:
        if not self.elements:
            self.elements.append([MOVE_TO_ELEMENT] + list(PATH_ORIGIN))

    def _maybe_move_to(self) -> None:
        if self.needs_move:
            self.elements.append([MOVE_TO_ELEMENT] + self._last())
            self.start_index = len(self.elements) - 1
            self.needs_move = False

    def move_to(self, x: Any, y: Any) -> "PathBuilder":
        """Lift the pen and put it down at one position."""
        if not is_finite_point((x, y)):
            return self
        self._ensure_data()
        self.needs_move = False
        if self.elements[-1][0] == MOVE_TO_ELEMENT:
            self.elements[-1][1] = float(x)
            self.elements[-1][2] = float(y)
        else:
            self.elements.append([MOVE_TO_ELEMENT, float(x), float(y)])
        self.start_index = len(self.elements) - 1
        return self

    def line_to(self, x: Any, y: Any) -> "PathBuilder":
        """Draw a straight step to one position."""
        if not is_finite_point((x, y)):
            return self
        self._ensure_data()
        self._maybe_move_to()
        if same_point((x, y), self._last()):
            return self
        self.elements.append([LINE_TO_ELEMENT, float(x), float(y)])
        return self

    def quad_to(self, bend_x: Any, bend_y: Any, x: Any, y: Any) -> "PathBuilder":
        """Draw a curve bending through one point on its way to another.

        The library keeps a curve that bends through one point as a
        curve that bends through two, each one third of the way toward
        the bending point.
        """
        if not is_finite_point((bend_x, bend_y)) or not is_finite_point((x, y)):
            return self
        self._ensure_data()
        self._maybe_move_to()
        previous = self._last()
        if same_point(previous, (bend_x, bend_y)) and same_point(
            (bend_x, bend_y), (x, y)
        ):
            return self
        first = [
            (previous[0] + CUBIC_CONTROL_WEIGHT * bend_x) / CUBIC_DIVISOR,
            (previous[1] + CUBIC_CONTROL_WEIGHT * bend_y) / CUBIC_DIVISOR,
        ]
        second = [
            (x + CUBIC_CONTROL_WEIGHT * bend_x) / CUBIC_DIVISOR,
            (y + CUBIC_CONTROL_WEIGHT * bend_y) / CUBIC_DIVISOR,
        ]
        if (
            same_point(previous, first)
            and same_point(first, second)
            and same_point(second, (x, y))
        ):
            return self
        self.elements.append([CURVE_TO_ELEMENT] + as_point(first))
        self.elements.append([CURVE_TO_DATA_ELEMENT] + as_point(second))
        self.elements.append([CURVE_TO_DATA_ELEMENT, float(x), float(y)])
        return self

    def close(self) -> "PathBuilder":
        """Draw the straight step back to where the shape started."""
        if not self.elements:
            return self
        self.needs_move = True
        first = self.elements[self.start_index]
        last = self.elements[-1]
        if first[1] == last[1] and first[2] == last[2]:
            return self
        if (
            abs(first[1] - last[1]) < CLOSE_SNAP_LIMIT
            and abs(first[2] - last[2]) < CLOSE_SNAP_LIMIT
        ):
            last[1] = first[1]
            last[2] = first[2]
            return self
        self.elements.append([LINE_TO_ELEMENT, first[1], first[2]])
        return self

    def parts(self) -> list:
        """The shape as the list of steps the drawing library keeps."""
        return [list(one) for one in self.elements]


class NodeParticle:
    """One speck of light thrown by a trade, in card coordinates."""

    def __init__(self, x: Any, y: Any, vx: Any, vy: Any, life: Any, size: Any) -> None:
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.size = size

    def step(self, dt: Any) -> None:
        """Move the speck on by `dt` seconds and take that off its life."""
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    @property
    def alpha(self) -> float:
        """How solid the speck is now, from 1 when new down to 0."""
        return max(PARTICLE_ALPHA_FLOOR, self.life / self.max_life)

    def state(self) -> dict:
        """Every value this speck holds, as one dict."""
        return {
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "life": self.life,
            "max_life": self.max_life,
            "size": self.size,
        }


def spawn_particles(cx: Any, cy: Any, draws: Any) -> list:
    """The five specks one trade throws, from twenty draws.

    Each speck takes four draws in turn: sideways speed, up-and-down
    speed, life and size.
    """
    taken = list(draws)
    wanted = PARTICLE_COUNT * PARTICLE_DRAWS_EACH
    if len(taken) < wanted:
        raise ValueError(DRAW_REFUSAL.format(wanted=wanted, given=len(taken)))
    built = []
    for index in range(PARTICLE_COUNT):
        head = index * PARTICLE_DRAWS_EACH
        four = taken[head : head + PARTICLE_DRAWS_EACH]
        built.append(
            NodeParticle(
                cx,
                cy,
                uniform(PARTICLE_VELOCITY_MIN, PARTICLE_VELOCITY_MAX, four[0]),
                uniform(PARTICLE_VELOCITY_MIN, PARTICLE_VELOCITY_MAX, four[1]),
                uniform(PARTICLE_LIFE_MIN, PARTICLE_LIFE_MAX, four[2]),
                uniform(PARTICLE_SIZE_MIN, PARTICLE_SIZE_MAX, four[3]),
            )
        )
    return built


def solid_pen(color: Any, width_px: Any) -> Call:
    """A drawing call setting a plain line of one colour and width."""
    return [SET_PEN, as_color(color), width_px, SOLID_PEN_STYLE]


def no_pen() -> Call:
    """A drawing call turning the outline off."""
    return [SET_PEN, None, NO_PEN_WIDTH_PX, NO_PEN_STYLE]


def wing_openness(state: Any, phase: Any, pulses: Any) -> tuple:
    """How far the wings stand open, and which rule set them there.

    A running card beats its wings, a stopped or idle one folds them
    tight and every other state holds them half open. A trade still
    ringing flicks them wider.
    """
    if state == STATE_RUNNING:
        open_at = WING_RUNNING_BASE + WING_RUNNING_SWING * math.sin(
            phase * WING_RUNNING_PHASE_RATE
        )
        branch = WING_RUNNING
    elif state in WING_TIGHT_STATES:
        open_at = WING_TIGHT_OPEN
        branch = WING_TIGHT
    else:
        open_at = WING_HALF_OPEN
        branch = WING_HALF
    branches = [branch]
    if pulses:
        open_at = min(WING_MAX_OPEN, open_at + WING_PULSE_BUMP * pulses[0])
        branches.append(WING_PULSED)
    return open_at, branches


def pnl_magnitude(pnl: Any) -> float:
    """How strongly the tail is tinted, from 0 for nothing to 1 for a lot.

    The tint follows the number of digits in the profit or loss, so ten
    thousand dollars reads apart from ten cents.
    """
    return min(
        PNL_MAGNITUDE_MAX,
        math.log10(max(abs(pnl), PNL_FLOOR_USD) + 1.0) / PNL_LOG_DIVISOR,
    )


def volume_text(volume: Any) -> tuple:
    """The traded amount in dollars, and which rule wrote it."""
    if volume >= MILLION:
        return VOLUME_MILLIONS_FORMAT.format(value=volume / MILLION), VOLUME_MILLIONS
    if volume >= THOUSAND:
        return VOLUME_THOUSANDS_FORMAT.format(value=volume / THOUSAND), VOLUME_THOUSANDS
    return VOLUME_PLAIN_FORMAT.format(value=volume), VOLUME_PLAIN


def body_parts(cx: Any, cy: Any, scale: Any, wing_open: Any) -> dict:
    """The five shapes the insect body is drawn from.

    Every measurement below is in units of `scale`, which is the card's
    shorter side divided by fifty-two. `wing_open` runs from 0 for wings
    folded to 1 for wings spread.
    """
    u = scale
    parts: dict = {}

    head = PathBuilder()
    head.move_to(cx - 4 * u, cy - 16 * u)
    head.quad_to(cx - 5 * u, cy - 19 * u, cx, cy - 20 * u)
    head.quad_to(cx + 5 * u, cy - 19 * u, cx + 4 * u, cy - 16 * u)
    head.line_to(cx + 3.5 * u, cy - 13 * u)
    head.line_to(cx - 3.5 * u, cy - 13 * u)
    head.close()
    parts["head"] = head.parts()

    thorax = PathBuilder()
    thorax.move_to(cx - 6 * u, cy - 12 * u)
    thorax.line_to(cx + 6 * u, cy - 12 * u)
    thorax.line_to(cx + 7 * u, cy - 4 * u)
    thorax.line_to(cx + 6 * u, cy + 2 * u)
    thorax.line_to(cx - 6 * u, cy + 2 * u)
    thorax.line_to(cx - 7 * u, cy - 4 * u)
    thorax.close()
    parts["thorax"] = thorax.parts()

    abdomen = PathBuilder()
    abdomen.move_to(cx - 5.5 * u, cy + 2 * u)
    abdomen.line_to(cx + 5.5 * u, cy + 2 * u)
    abdomen.quad_to(cx + 5 * u, cy + 10 * u, cx + 2.5 * u, cy + 16 * u)
    abdomen.quad_to(cx, cy + 18 * u, cx - 2.5 * u, cy + 16 * u)
    abdomen.quad_to(cx - 5 * u, cy + 10 * u, cx - 5.5 * u, cy + 2 * u)
    abdomen.close()
    parts["abdomen"] = abdomen.parts()

    spread = WING_SPREAD_U * u + wing_open * WING_SPREAD_OPEN_U * u
    lift = wing_open * WING_LIFT_U * u

    wing_l = PathBuilder()
    wing_l.move_to(cx - 4 * u, cy - 10 * u)
    wing_l.quad_to(
        cx - spread,
        cy - 6 * u - lift,
        cx - spread * WING_TIP_RATIO,
        cy + 4 * u - lift,
    )
    wing_l.quad_to(cx - 4 * u, cy + 2 * u, cx - 3 * u, cy - 10 * u)
    wing_l.close()
    parts["wing_l"] = wing_l.parts()

    wing_r = PathBuilder()
    wing_r.move_to(cx + 4 * u, cy - 10 * u)
    wing_r.quad_to(
        cx + spread,
        cy - 6 * u - lift,
        cx + spread * WING_TIP_RATIO,
        cy + 4 * u - lift,
    )
    wing_r.quad_to(cx + 4 * u, cy + 2 * u, cx + 3 * u, cy - 10 * u)
    wing_r.close()
    parts["wing_r"] = wing_r.parts()

    return parts


def antenna_sway(phase: Any, drive: Any, sign: Any) -> float:
    """How far one feeler leans, from the idle beat and the last price move."""
    return ANTENNA_SWAY_AMBIENT * math.sin(
        phase * ANTENNA_AMBIENT_PHASE_RATE + sign * ANTENNA_AMBIENT_OFFSET
    ) + ANTENNA_SWAY_DRIVEN * drive * math.sin(
        phase * ANTENNA_DRIVEN_PHASE_RATE + sign * ANTENNA_DRIVEN_OFFSET
    )


def antenna_path(cx: Any, cy: Any, scale: Any, sign: Any, sway: Any) -> list:
    """One feeler as the steps the drawing library keeps."""
    path = PathBuilder()
    path.move_to(cx + sign * ANTENNA_BASE_X_U * scale, cy - ANTENNA_BASE_Y_U * scale)
    path.quad_to(
        cx + sign * (ANTENNA_BEND_X_U + sway) * scale,
        cy - ANTENNA_BEND_Y_U * scale,
        cx + sign * (ANTENNA_TIP_X_U + sway) * scale,
        cy - ANTENNA_TIP_Y_U * scale,
    )
    return path.parts()


def leg_points(cx: Any, cy: Any, scale: Any, sign: Any, leg_u: Any) -> list:
    """The hip, knee and foot of one leg, as three positions."""
    return [[cx + sign * across * scale, cy + down * scale] for across, down in leg_u]


def bracket_corners(width: Any, height: Any) -> list:
    """The four corner marks, each as a position and the way it turns."""
    near = BRACKET_NEAR_INSET_PX
    far_x = width - BRACKET_FAR_INSET_PX
    far_y = height - BRACKET_FAR_INSET_PX
    return [
        [near, near, 1, 1],
        [far_x, near, -1, 1],
        [near, far_y, 1, -1],
        [far_x, far_y, -1, -1],
    ]


class BotNodeModel:
    """One bot's locust card.

    Holds the theme, the idle angle, the trade rings, the specks and the
    latest bot values. ``paint`` builds the ordered drawing programme
    and returns it. ``set_theme``, ``set_bot_data`` and ``animate``
    change the card and record what they did, in the order the shipped
    card does them.
    """

    def __init__(
        self,
        width_px: Any = MIN_WIDTH_PX,
        height_px: Any = MIN_HEIGHT_PX,
        phase: Any = PHASE_MIN,
        theme_key: Any = THEME_FALLBACK_KEY,
        bot_data: Any = None,
        trade_pulses: Any = None,
        particles: Any = None,
        antenna_drive: Any = ANTENNA_DRIVE_FLOOR,
    ) -> None:
        self.width_px = width_px
        self.height_px = height_px
        self.minimum_size_px = [MIN_WIDTH_PX, MIN_HEIGHT_PX]
        self.phase = phase
        self.theme_key = theme_key_or_fallback(theme_key)
        self.bot_data = {} if bot_data is None else bot_data
        self.trade_pulses = list(trade_pulses or [])
        self.particles = [
            one if isinstance(one, NodeParticle) else NodeParticle(*one)
            for one in (particles or [])
        ]
        self.antenna_drive = antenna_drive
        self.tooltip: Optional[str] = None
        self.calls: list = []
        self.draw_calls: list = []
        self.paint_branches: list = []

    def apply(self, steps: Any) -> None:
        """Run each card change in order; each is a kind and its value."""
        for step in steps:
            kind = step[0]
            if kind == THEME_STEP:
                self.set_theme(step[1])
            elif kind == DATA_STEP:
                self.set_bot_data(step[1], step[2] if len(step) > 2 else ())
            elif kind == ANIMATE_STEP:
                self.animate(step[1])
            else:
                raise ValueError(STEP_REFUSAL.format(kind=kind))

    def set_theme(self, theme_key: Any) -> None:
        """Change the colour set the card paints in and redraw it."""
        self.theme_key = theme_key_or_fallback(theme_key)
        self.calls.append([UPDATE_CARD])

    def set_bot_data(self, data: Any, draws: Any = ()) -> None:
        """Take the latest values for this bot.

        A rise in the trade count sends a ring out and throws five
        specks, which need twenty draws. Any change in price starts the
        feelers swaying.
        """
        old_trades = self.bot_data.get(STATS_KEY, {}).get(TRADES_KEY, ZERO_STAT)
        new_trades = data.get(STATS_KEY, {}).get(TRADES_KEY, ZERO_STAT)
        if new_trades > old_trades:
            self.trade_pulses.append(PULSE_START)
            self.particles.extend(
                spawn_particles(self.width_px / 2, self.height_px / 2, draws)
            )
        old_price = self.bot_data.get(STATS_KEY, {}).get(PRICE_KEY, ZERO_STAT)
        new_price = data.get(STATS_KEY, {}).get(PRICE_KEY, ZERO_STAT)
        if old_price and new_price and old_price != new_price:
            self.antenna_drive = ANTENNA_DRIVE_START
        self.bot_data = data

    def animate(self, dt: Any) -> None:
        """Move the card on by `dt` seconds and redraw it."""
        self.phase += dt * PHASE_RATE_PER_S
        self.trade_pulses = [
            one - dt * PULSE_DECAY_PER_S
            for one in self.trade_pulses
            if one - dt * PULSE_DECAY_PER_S > PULSE_FLOOR
        ]
        for one in self.particles:
            one.step(dt)
        self.particles = [
            one for one in self.particles if one.life > PARTICLE_LIFE_FLOOR
        ]
        self.antenna_drive = max(
            ANTENNA_DRIVE_FLOOR, self.antenna_drive - dt * ANTENNA_DECAY_PER_S
        )
        self.calls.append([UPDATE_CARD])

    def paint(self, mask: Optional[Callable] = None) -> list:
        """Build the drawing programme and return it.

        Nothing is drawn while the card holds no bot values. Each step
        is appended as it is worked out, so a value the card refuses
        part way leaves the earlier steps standing, as the shipped card
        leaves them on the screen.
        """
        self.draw_calls = []
        self.paint_branches = []
        self.tooltip = None
        hide = mask or plain_text
        calls = self.draw_calls
        if not self.bot_data:
            self.paint_branches.append(PAINT_NOTHING)
            return calls

        calls.append([SET_RENDER_HINT, RENDER_HINT, RENDER_HINT_VALUE])
        colors = theme(self.theme_key)
        width, height = self.width_px, self.height_px
        cx, cy = width / 2, height / 2
        calls.append([FILL_RECT, [0, 0, width, height], as_color(colors["bg"])])

        data = self.bot_data
        stats = data.get(STATS_KEY, {})
        state = data.get(STATE_KEY, DEFAULT_STATE)
        symbol = data.get(SYMBOL_KEY, DEFAULT_SYMBOL)
        mode = data.get(MODE_KEY, DEFAULT_MODE)
        pnl = stats.get(PNL_KEY, ZERO_STAT)
        trades = stats.get(TRADES_KEY, ZERO_STAT)
        price = stats.get(PRICE_KEY, ZERO_STAT)
        volume = stats.get(VOLUME_KEY, ZERO_STAT)

        states = STATE_COLORS[self.theme_key]
        state_color = states.get(state, colors["text"])
        leg_color = LEG_COLORS[self.theme_key].get(
            state, LEG_FALLBACK_COLORS[self.theme_key]
        )
        self.paint_branches.append(STATE_KNOWN if state in states else STATE_UNKNOWN)
        if pnl >= 0:
            pnl_color = colors["success"]
            self.paint_branches.append(PNL_POSITIVE)
        else:
            pnl_color = colors["error"]
            self.paint_branches.append(PNL_NEGATIVE)

        scale = min(width, height) / SCALE_DIVISOR
        wing_open, wing_branches = wing_openness(state, self.phase, self.trade_pulses)
        self.paint_branches.extend(wing_branches)

        for pulse in self.trade_pulses:
            radius = PULSE_RING_BASE_U * scale + (1 - pulse) * PULSE_RING_GROWTH_PX
            ring = with_alpha(colors["success"], int(PULSE_RING_ALPHA * pulse))
            calls.append([SET_PEN, ring, PULSE_RING_WIDTH_PX, SOLID_PEN_STYLE])
            calls.append([SET_BRUSH, NO_BRUSH])
            calls.append([DRAW_ELLIPSE, as_point((cx, cy)), radius, radius])
            self.paint_branches.append(PULSE_RING)

        for speck in self.particles:
            speck_color = with_alpha(
                colors["particle"], int(PARTICLE_ALPHA_SCALE * speck.alpha)
            )
            calls.append(no_pen())
            calls.append([SET_BRUSH, speck_color])
            calls.append(
                [
                    DRAW_ELLIPSE,
                    as_point((speck.x, speck.y)),
                    speck.size,
                    speck.size,
                ]
            )
            self.paint_branches.append(PARTICLE_DRAWN)

        parts = body_parts(cx, cy, scale, wing_open)

        calls.append(no_pen())
        calls.append(
            [
                SET_RADIAL_BRUSH,
                as_point((cx, cy)),
                GLOW_RADIUS_U * scale,
                [
                    [GRADIENT_CENTRE_STOP, with_alpha(state_color, GLOW_ALPHA)],
                    [GRADIENT_EDGE_STOP, list(GLOW_EDGE_COLOR)],
                ],
            ]
        )
        calls.append(
            [
                DRAW_ELLIPSE,
                as_point((cx, cy)),
                GLOW_RADIUS_U * scale,
                GLOW_RADIUS_U * scale,
            ]
        )

        calls.append(
            [
                SET_BRUSH,
                with_alpha(
                    colors["accent"],
                    WING_ALPHA_BASE + int(WING_ALPHA_SWING * wing_open),
                ),
            ]
        )
        calls.append(
            [
                SET_PEN,
                with_alpha(colors["accent2"], WING_PEN_ALPHA),
                WING_PEN_WIDTH_PX,
                WING_PEN_STYLE,
            ]
        )
        calls.append([DRAW_PATH, parts["wing_l"]])
        calls.append([DRAW_PATH, parts["wing_r"]])

        magnitude = pnl_magnitude(pnl)
        calls.append(
            [
                SET_LINEAR_BRUSH,
                as_point((cx, cy + ABDOMEN_GRADIENT_TOP_U * scale)),
                as_point((cx, cy + ABDOMEN_GRADIENT_BOTTOM_U * scale)),
                [
                    [
                        GRADIENT_CENTRE_STOP,
                        with_alpha(
                            pnl_color,
                            int(ABDOMEN_BASE_ALPHA + ABDOMEN_BASE_SWING * magnitude),
                        ),
                    ],
                    [
                        GRADIENT_EDGE_STOP,
                        with_alpha(
                            pnl_color,
                            int(ABDOMEN_TIP_ALPHA + ABDOMEN_TIP_SWING * magnitude),
                        ),
                    ],
                ],
            ]
        )
        calls.append(solid_pen(pnl_color, ABDOMEN_PEN_WIDTH_PX))
        calls.append([DRAW_PATH, parts["abdomen"]])

        calls.append(solid_pen(SEGMENT_COLOR, SEGMENT_PEN_WIDTH_PX))
        for index in range(1, SEGMENT_COUNT + 1):
            y_seg = cy + (SEGMENT_TOP_U + index * SEGMENT_STEP_U) * scale
            taper = SEGMENT_TAPER_U - index * SEGMENT_TAPER_STEP_U
            calls.append(
                [
                    DRAW_LINE,
                    as_point((cx - taper * scale, y_seg)),
                    as_point((cx + taper * scale, y_seg)),
                ]
            )

        calls.append(
            [
                SET_RADIAL_BRUSH,
                as_point((cx, cy - THORAX_GRADIENT_CENTRE_U * scale)),
                THORAX_GRADIENT_RADIUS_U * scale,
                [
                    [
                        GRADIENT_CENTRE_STOP,
                        with_alpha(state_color, THORAX_CENTRE_ALPHA),
                    ],
                    [GRADIENT_EDGE_STOP, with_alpha(state_color, THORAX_EDGE_ALPHA)],
                ],
            ]
        )
        calls.append(solid_pen(state_color, THORAX_PEN_WIDTH_PX))
        calls.append([DRAW_PATH, parts["thorax"]])

        calls.append([SET_BRUSH, as_color(HEAD_FILLS[self.theme_key])])
        calls.append(solid_pen(state_color, HEAD_PEN_WIDTH_PX))
        calls.append([DRAW_PATH, parts["head"]])

        eye_radius = EYE_RADIUS_U * scale + EYE_SWING_U * scale * math.sin(
            self.phase * EYE_PHASE_RATE
        )
        calls.append(no_pen())
        calls.append([SET_BRUSH, as_color(state_color)])
        calls.append(
            [
                DRAW_ELLIPSE,
                as_point((cx, cy - EYE_CENTRE_U * scale)),
                eye_radius,
                eye_radius,
            ]
        )

        antenna_pen = solid_pen(colors["accent2"], ANTENNA_PEN_WIDTH_PX)
        calls.append(list(antenna_pen))
        calls.append([SET_BRUSH, NO_BRUSH])
        for sign in ANTENNA_SIGNS:
            sway = antenna_sway(self.phase, self.antenna_drive, sign)
            calls.append([DRAW_PATH, antenna_path(cx, cy, scale, sign, sway)])
            calls.append(no_pen())
            calls.append([SET_BRUSH, with_alpha(colors["accent2"], ANTENNA_TIP_ALPHA)])
            calls.append(
                [
                    DRAW_ELLIPSE,
                    as_point(
                        (
                            cx + sign * (ANTENNA_TIP_X_U + sway) * scale,
                            cy - ANTENNA_TIP_Y_U * scale,
                        )
                    ),
                    ANTENNA_TIP_RADIUS_PX,
                    ANTENNA_TIP_RADIUS_PX,
                ]
            )
            calls.append(list(antenna_pen))

        calls.append(solid_pen(leg_color, LEG_PEN_WIDTH_PX))
        for sign in LEG_SIGNS:
            for leg_u in (FORE_LEG_U, MID_LEG_U):
                hip, knee, foot = leg_points(cx, cy, scale, sign, leg_u)
                calls.append([DRAW_LINE, as_point(hip), as_point(knee)])
                calls.append([DRAW_LINE, as_point(knee), as_point(foot)])
            calls.append(solid_pen(leg_color, HIND_LEG_PEN_WIDTH_PX))
            hip, knee, foot = leg_points(cx, cy, scale, sign, HIND_LEG_U)
            calls.append([DRAW_LINE, as_point(hip), as_point(knee)])
            calls.append([DRAW_LINE, as_point(knee), as_point(foot)])
            calls.append(solid_pen(leg_color, LEG_PEN_WIDTH_PX))

        calls.append(
            solid_pen(
                with_alpha(colors["accent2"], BRACKET_ALPHA), BRACKET_PEN_WIDTH_PX
            )
        )
        for bx, by, dx, dy in bracket_corners(width, height):
            calls.append(
                [
                    DRAW_LINE,
                    as_point((bx, by)),
                    as_point((bx + dx * BRACKET_LENGTH_PX, by)),
                ]
            )
            calls.append(
                [
                    DRAW_LINE,
                    as_point((bx, by)),
                    as_point((bx, by + dy * BRACKET_LENGTH_PX)),
                ]
            )

        circuit_color = with_alpha(colors["accent"], CIRCUIT_ALPHA)
        calls.append(solid_pen(circuit_color, CIRCUIT_PEN_WIDTH_PX))
        for down_u in CIRCUIT_LINE_Y_U:
            y_line = cy + down_u * scale
            calls.append(
                [
                    DRAW_LINE,
                    as_point((cx - CIRCUIT_LINE_HALF_U * scale, y_line)),
                    as_point((cx + CIRCUIT_LINE_HALF_U * scale, y_line)),
                ]
            )
        calls.append(no_pen())
        calls.append([SET_BRUSH, list(circuit_color)])
        for across_u in CIRCUIT_DOT_X_U:
            calls.append(
                [
                    DRAW_ELLIPSE,
                    as_point((cx + across_u * scale, cy + CIRCUIT_DOT_Y_U * scale)),
                    CIRCUIT_DOT_RADIUS_PX,
                    CIRCUIT_DOT_RADIUS_PX,
                ]
            )

        calls.append(
            solid_pen(with_alpha(colors["accent2"], IRIS_ALPHA), IRIS_PEN_WIDTH_PX)
        )
        calls.append([SET_BRUSH, NO_BRUSH])
        calls.append(
            [
                DRAW_ELLIPSE,
                as_point((cx, cy - EYE_CENTRE_U * scale)),
                eye_radius * IRIS_RADIUS_RATIO,
                eye_radius * IRIS_RADIUS_RATIO,
            ]
        )

        calls.append([SET_FONT, FONT_FAMILY, SYMBOL_FONT_SIZE_PT, FONT_WEIGHT_BOLD])
        calls.append([SET_PEN_COLOR, as_color(colors["text"])])
        calls.append(
            [
                DRAW_TEXT,
                [
                    float(RECT_LEFT_PX),
                    float(SYMBOL_RECT_TOP_PX),
                    float(width),
                    float(SYMBOL_RECT_HEIGHT_PX),
                ],
                ALIGN_CENTER,
                hide(symbol, MASK_FIELD_ID),
            ]
        )

        calls.append([SET_FONT, FONT_FAMILY, PNL_FONT_SIZE_PT, FONT_WEIGHT_BOLD])
        calls.append([SET_PEN_COLOR, as_color(pnl_color)])
        calls.append(
            [
                DRAW_TEXT,
                [
                    float(RECT_LEFT_PX),
                    float(height - PNL_RECT_BOTTOM_PX),
                    float(width),
                    float(PNL_RECT_HEIGHT_PX),
                ],
                ALIGN_CENTER,
                fmt_pnl(pnl),
            ]
        )

        calls.append([SET_FONT, FONT_FAMILY, BOT_ID_FONT_SIZE_PT, FONT_WEIGHT_NORMAL])
        calls.append([SET_PEN_COLOR, as_color(BOT_ID_COLOR)])
        bot_id_short = data.get(BOT_ID_KEY, NO_BOT_ID)[:BOT_ID_LABEL_CHARS]
        calls.append(
            [
                DRAW_TEXT,
                [
                    float(RECT_LEFT_PX),
                    float(height - BOT_ID_RECT_BOTTOM_PX),
                    float(width),
                    float(BOT_ID_RECT_HEIGHT_PX),
                ],
                ALIGN_CENTER,
                hide(bot_id_short, MASK_FIELD_ID),
            ]
        )

        written, volume_branch = volume_text(volume)
        self.paint_branches.append(volume_branch)
        if price > PRICE_FLOOR_USD:
            price_text = fmt_price(price)
            self.paint_branches.append(PRICE_SHOWN)
        else:
            price_text = PRICE_DASH
            self.paint_branches.append(PRICE_HIDDEN)
        self.tooltip = TOOLTIP_FORMAT.format(
            symbol=hide(symbol, MASK_FIELD_ID),
            state=state.upper(),
            mode=mode.upper(),
            trades=trades,
            price=price_text,
            volume=written,
            pnl=fmt_pnl(pnl),
            bot_id=hide(
                str(data.get(BOT_ID_KEY, NO_BOT_ID))[:BOT_ID_TOOLTIP_CHARS],
                MASK_FIELD_ID,
                mask=TOOLTIP_BOT_MASK,
            ),
        )
        self.calls.append([SET_TOOLTIP, self.tooltip])

        calls.append([END_PAINTER])
        self.paint_branches.append(PAINT_WHOLE)
        return calls

    def state(self) -> dict:
        """Every value this card holds, as one dict."""
        return {
            "width_px": self.width_px,
            "height_px": self.height_px,
            "minimum_size_px": list(self.minimum_size_px),
            "phase": self.phase,
            "theme_key": self.theme_key,
            "bot_data": self.bot_data,
            "trade_pulses": list(self.trade_pulses),
            "particles": [one.state() for one in self.particles],
            "antenna_drive": self.antenna_drive,
            "tooltip": self.tooltip,
        }


def masking(hidden: Any) -> Callable:
    """A privacy answer that hides the fields the caller names."""
    fields = set(hidden or ())

    def hide(value: Any, field_id: str, mask: str = "****") -> str:
        return mask if field_id in fields else str(value)

    return hide


def build_view_model(
    model: BotNodeModel,
    steps: Any = None,
    mask: Optional[Callable] = None,
) -> dict:
    """Return every value the locust card holds as one dict.

    `steps` runs a list of card changes before the values are read, each
    one a name and its arguments: ``theme``, ``data`` or ``animate``.
    `mask` answers whether an identifier is hidden; without one nothing
    is hidden.
    """
    if steps:
        model.apply(steps)
    drawing_calls = model.paint(mask)
    return {
        "method": METHOD,
        "minimum_size_px": list(model.minimum_size_px),
        "render_hint": {"name": RENDER_HINT, "value": RENDER_HINT_VALUE},
        "theme": {
            "key": model.theme_key,
            "fallback_key": THEME_FALLBACK_KEY,
            "keys": list(THEME_KEYS),
            "color_names": list(THEME_COLOR_NAMES),
            "opaque_alpha": OPAQUE_ALPHA,
            "table": {
                name: {color: list(value) for color, value in sorted(row.items())}
                for name, row in THEME_COLORS.items()
            },
            "colors": {
                color: list(value)
                for color, value in sorted(theme(model.theme_key).items())
            },
            "head_fills": {name: list(value) for name, value in HEAD_FILLS.items()},
        },
        "states": {
            "names": list(STATE_NAMES),
            "default": DEFAULT_STATE,
            "idle_grey": list(IDLE_GREY),
            "stopped_grey": list(STOPPED_GREY),
            "colors": {
                name: {state: list(value) for state, value in sorted(row.items())}
                for name, row in STATE_COLORS.items()
            },
            "leg_colors": {
                name: {state: list(value) for state, value in sorted(row.items())}
                for name, row in LEG_COLORS.items()
            },
            "leg_fallback_colors": {
                name: list(value) for name, value in LEG_FALLBACK_COLORS.items()
            },
        },
        "data_keys": {
            "stats": STATS_KEY,
            "state": STATE_KEY,
            "symbol": SYMBOL_KEY,
            "mode": MODE_KEY,
            "bot_id": BOT_ID_KEY,
            "pnl": PNL_KEY,
            "trades": TRADES_KEY,
            "price": PRICE_KEY,
            "volume": VOLUME_KEY,
        },
        "defaults": {
            "symbol": DEFAULT_SYMBOL,
            "mode": DEFAULT_MODE,
            "stat": ZERO_STAT,
            "bot_id": NO_BOT_ID,
        },
        "movement": {
            "phase_min": PHASE_MIN,
            "phase_max": PHASE_MAX,
            "phase_rate_per_s": PHASE_RATE_PER_S,
            "pulse_decay_per_s": PULSE_DECAY_PER_S,
            "pulse_start": PULSE_START,
            "pulse_floor": PULSE_FLOOR,
            "antenna_drive_start": ANTENNA_DRIVE_START,
            "antenna_decay_per_s": ANTENNA_DECAY_PER_S,
            "antenna_drive_floor": ANTENNA_DRIVE_FLOOR,
        },
        "particle": {
            "count": PARTICLE_COUNT,
            "velocity_min": PARTICLE_VELOCITY_MIN,
            "velocity_max": PARTICLE_VELOCITY_MAX,
            "life_min": PARTICLE_LIFE_MIN,
            "life_max": PARTICLE_LIFE_MAX,
            "size_min": PARTICLE_SIZE_MIN,
            "size_max": PARTICLE_SIZE_MAX,
            "draws_each": PARTICLE_DRAWS_EACH,
            "alpha_scale": PARTICLE_ALPHA_SCALE,
            "alpha_floor": PARTICLE_ALPHA_FLOOR,
            "life_floor": PARTICLE_LIFE_FLOOR,
        },
        "wing": {
            "half_open": WING_HALF_OPEN,
            "running_base": WING_RUNNING_BASE,
            "running_swing": WING_RUNNING_SWING,
            "running_phase_rate": WING_RUNNING_PHASE_RATE,
            "tight_open": WING_TIGHT_OPEN,
            "tight_states": list(WING_TIGHT_STATES),
            "pulse_bump": WING_PULSE_BUMP,
            "max_open": WING_MAX_OPEN,
            "alpha_base": WING_ALPHA_BASE,
            "alpha_swing": WING_ALPHA_SWING,
            "pen_alpha": WING_PEN_ALPHA,
            "pen_width_px": WING_PEN_WIDTH_PX,
            "pen_style": WING_PEN_STYLE,
            "spread_u": WING_SPREAD_U,
            "spread_open_u": WING_SPREAD_OPEN_U,
            "lift_u": WING_LIFT_U,
            "tip_ratio": WING_TIP_RATIO,
        },
        "pulse_ring": {
            "base_u": PULSE_RING_BASE_U,
            "growth_px": PULSE_RING_GROWTH_PX,
            "alpha": PULSE_RING_ALPHA,
            "width_px": PULSE_RING_WIDTH_PX,
        },
        "glow": {
            "radius_u": GLOW_RADIUS_U,
            "alpha": GLOW_ALPHA,
            "edge_color": list(GLOW_EDGE_COLOR),
            "centre_stop": GRADIENT_CENTRE_STOP,
            "edge_stop": GRADIENT_EDGE_STOP,
        },
        "abdomen": {
            "floor_usd": PNL_FLOOR_USD,
            "log_divisor": PNL_LOG_DIVISOR,
            "magnitude_max": PNL_MAGNITUDE_MAX,
            "base_alpha": ABDOMEN_BASE_ALPHA,
            "base_swing": ABDOMEN_BASE_SWING,
            "tip_alpha": ABDOMEN_TIP_ALPHA,
            "tip_swing": ABDOMEN_TIP_SWING,
            "gradient_top_u": ABDOMEN_GRADIENT_TOP_U,
            "gradient_bottom_u": ABDOMEN_GRADIENT_BOTTOM_U,
            "pen_width_px": ABDOMEN_PEN_WIDTH_PX,
        },
        "segments": {
            "color": list(SEGMENT_COLOR),
            "pen_width_px": SEGMENT_PEN_WIDTH_PX,
            "count": SEGMENT_COUNT,
            "top_u": SEGMENT_TOP_U,
            "step_u": SEGMENT_STEP_U,
            "taper_u": SEGMENT_TAPER_U,
            "taper_step_u": SEGMENT_TAPER_STEP_U,
        },
        "thorax": {
            "gradient_centre_u": THORAX_GRADIENT_CENTRE_U,
            "gradient_radius_u": THORAX_GRADIENT_RADIUS_U,
            "centre_alpha": THORAX_CENTRE_ALPHA,
            "edge_alpha": THORAX_EDGE_ALPHA,
            "pen_width_px": THORAX_PEN_WIDTH_PX,
        },
        "head": {"pen_width_px": HEAD_PEN_WIDTH_PX},
        "eye": {
            "radius_u": EYE_RADIUS_U,
            "swing_u": EYE_SWING_U,
            "phase_rate": EYE_PHASE_RATE,
            "centre_u": EYE_CENTRE_U,
            "iris_alpha": IRIS_ALPHA,
            "iris_pen_width_px": IRIS_PEN_WIDTH_PX,
            "iris_radius_ratio": IRIS_RADIUS_RATIO,
        },
        "antenna": {
            "signs": list(ANTENNA_SIGNS),
            "pen_width_px": ANTENNA_PEN_WIDTH_PX,
            "sway_ambient": ANTENNA_SWAY_AMBIENT,
            "ambient_phase_rate": ANTENNA_AMBIENT_PHASE_RATE,
            "ambient_offset": ANTENNA_AMBIENT_OFFSET,
            "sway_driven": ANTENNA_SWAY_DRIVEN,
            "driven_phase_rate": ANTENNA_DRIVEN_PHASE_RATE,
            "driven_offset": ANTENNA_DRIVEN_OFFSET,
            "base_x_u": ANTENNA_BASE_X_U,
            "base_y_u": ANTENNA_BASE_Y_U,
            "bend_x_u": ANTENNA_BEND_X_U,
            "bend_y_u": ANTENNA_BEND_Y_U,
            "tip_x_u": ANTENNA_TIP_X_U,
            "tip_y_u": ANTENNA_TIP_Y_U,
            "tip_alpha": ANTENNA_TIP_ALPHA,
            "tip_radius_px": ANTENNA_TIP_RADIUS_PX,
        },
        "legs": {
            "signs": list(LEG_SIGNS),
            "pen_width_px": LEG_PEN_WIDTH_PX,
            "hind_pen_width_px": HIND_LEG_PEN_WIDTH_PX,
            "fore_u": [list(one) for one in FORE_LEG_U],
            "mid_u": [list(one) for one in MID_LEG_U],
            "hind_u": [list(one) for one in HIND_LEG_U],
        },
        "brackets": {
            "alpha": BRACKET_ALPHA,
            "pen_width_px": BRACKET_PEN_WIDTH_PX,
            "length_px": BRACKET_LENGTH_PX,
            "near_inset_px": BRACKET_NEAR_INSET_PX,
            "far_inset_px": BRACKET_FAR_INSET_PX,
        },
        "circuit": {
            "alpha": CIRCUIT_ALPHA,
            "pen_width_px": CIRCUIT_PEN_WIDTH_PX,
            "line_y_u": list(CIRCUIT_LINE_Y_U),
            "line_half_u": CIRCUIT_LINE_HALF_U,
            "dot_x_u": list(CIRCUIT_DOT_X_U),
            "dot_y_u": CIRCUIT_DOT_Y_U,
            "dot_radius_px": CIRCUIT_DOT_RADIUS_PX,
        },
        "font": {
            "family": FONT_FAMILY,
            "symbol_size_pt": SYMBOL_FONT_SIZE_PT,
            "pnl_size_pt": PNL_FONT_SIZE_PT,
            "bot_id_size_pt": BOT_ID_FONT_SIZE_PT,
            "bold": FONT_WEIGHT_BOLD,
            "normal": FONT_WEIGHT_NORMAL,
            "bold_value": FONT_WEIGHT_BOLD_VALUE,
            "normal_value": FONT_WEIGHT_NORMAL_VALUE,
        },
        "labels": {
            "left_px": RECT_LEFT_PX,
            "symbol_top_px": SYMBOL_RECT_TOP_PX,
            "symbol_height_px": SYMBOL_RECT_HEIGHT_PX,
            "pnl_bottom_px": PNL_RECT_BOTTOM_PX,
            "pnl_height_px": PNL_RECT_HEIGHT_PX,
            "bot_id_bottom_px": BOT_ID_RECT_BOTTOM_PX,
            "bot_id_height_px": BOT_ID_RECT_HEIGHT_PX,
            "bot_id_color": list(BOT_ID_COLOR),
        },
        "privacy": {
            "field_id": MASK_FIELD_ID,
            "label_chars": BOT_ID_LABEL_CHARS,
            "tooltip_chars": BOT_ID_TOOLTIP_CHARS,
            "tooltip_mask": TOOLTIP_BOT_MASK,
        },
        "tooltip": {
            "text": model.tooltip,
            "format": TOOLTIP_FORMAT,
            "million": MILLION,
            "thousand": THOUSAND,
            "millions_format": VOLUME_MILLIONS_FORMAT,
            "thousands_format": VOLUME_THOUSANDS_FORMAT,
            "plain_format": VOLUME_PLAIN_FORMAT,
            "price_floor_usd": PRICE_FLOOR_USD,
            "price_dash": PRICE_DASH,
        },
        "path": {
            "element_names": list(PATH_ELEMENT_NAMES),
            "origin": list(PATH_ORIGIN),
            "cubic_divisor": CUBIC_DIVISOR,
            "cubic_control_weight": CUBIC_CONTROL_WEIGHT,
            "fuzzy_scale": FUZZY_SCALE,
            "fuzzy_null_limit": FUZZY_NULL_LIMIT,
            "close_snap_limit": CLOSE_SNAP_LIMIT,
            "part_names": list(BODY_PART_NAMES),
        },
        "pens": {
            "solid_style": SOLID_PEN_STYLE,
            "no_pen_style": NO_PEN_STYLE,
            "no_pen_width_px": NO_PEN_WIDTH_PX,
            "no_brush": NO_BRUSH,
        },
        "alignment": {"name": ALIGN_CENTER, "value": ALIGN_CENTER_VALUE},
        "scale_divisor": SCALE_DIVISOR,
        "step_kinds": list(STEP_KINDS),
        "draw_call_names": list(DRAW_CALL_NAMES),
        "route_names": list(ROUTE_NAMES),
        "paint_branch_names": list(PAINT_BRANCHES),
        "formats": {"step_refusal": STEP_REFUSAL, "draw_refusal": DRAW_REFUSAL},
        "actions": dict(ACTIONS),
        "signals": list(SIGNALS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "screen_elements": list(SCREEN_ELEMENTS),
        "drawing_calls": [list(one) for one in drawing_calls],
        "paint_branches": list(model.paint_branches),
        "calls": [list(one) for one in model.calls],
        "card": model.state(),
    }


NODE_MODEL: Optional[BotNodeModel] = None


def held_model() -> BotNodeModel:
    """The card the bridge keeps between calls, built on first request."""
    global NODE_MODEL
    if NODE_MODEL is None:
        NODE_MODEL = BotNodeModel()
    return NODE_MODEL


def view_model(params: dict) -> dict:
    """Bridge handler for ``bot_node.state``.

    ``card`` builds a fresh card from the values the renderer sends and
    ``reset`` clears the card without changing them. ``steps`` runs card
    changes before the values are read. ``hidden`` names the privacy
    fields to mask.
    """
    global NODE_MODEL
    if "card" in params:
        NODE_MODEL = BotNodeModel(**(params.get("card") or {}))
    elif params.get("reset", False):
        NODE_MODEL = BotNodeModel()
    return build_view_model(
        held_model(),
        params.get("steps"),
        masking(params.get("hidden")),
    )
