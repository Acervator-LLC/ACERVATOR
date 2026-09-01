"""splash_screen_surface.py -- the launch splash as plain data.

Describes the frameless window Acervator paints over the main window while
it starts: the three phases it moves through, the time it spends in each,
the master fade the whole picture carries, the four element fades that run
inside it, and every colour, font, rectangle and text the painter is given.

It also holds the behaviour the splash owns rather than describes: the
25 ms tick that advances the clock, the phase the tick moves to, the close
at the end of the fade-out, the 750 ms hand-off to the caller's callback,
and the click that jumps straight to the fade-out.

``paint_ops`` returns the painter calls in the order the splash makes
them, so a frontend can replay the same picture from the same numbers.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``splash_screen.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt, so the same code serves any
frontend.
"""

from __future__ import annotations

import math
from typing import Any, Optional

METHOD = "splash_screen.state"

WINDOW_FLAGS = ("FramelessWindowHint", "WindowStaysOnTopHint", "SplashScreen")
DELETE_ON_CLOSE = True
TRANSLUCENT_BACKGROUND = False

TIMER_INTERVAL_MS = 25
TICK_SECONDS = 0.025
HANDOFF_DELAY_MS = 750

FADEIN = "fadein"
GLOW = "glow"
FADEOUT = "fadeout"
PHASES = (FADEIN, GLOW, FADEOUT)

GLOW_AT_S = 2.0
FADEOUT_AT_S = 6.0
CLOSE_AT_S = 8.5
CLICK_JUMPS_TO_S = 6.0

MASTER_RISE_S = 1.0
MASTER_FALL_FROM_S = 6.0
MASTER_FALL_S = 2.5
FULL_ALPHA = 255

LOGO_FADE = (0.2, 1.0)
TITLE_FADE = (0.8, 0.7)
SUBTITLE_FADE = (1.2, 0.6)
CREDIT_FADE = (1.5, 0.8)

BACKGROUND_STOPS = (
    (0.0, (8, 8, 18)),
    (0.3, (6, 6, 14)),
    (0.7, (8, 8, 20)),
    (1.0, (6, 6, 14)),
)
BACKGROUND_WIDTH_SHARE = 0.3

SCANLINE_MIN_ALPHA = 30
SCANLINE_STEP_PX = 3
SCANLINE_RGB = (255, 255, 255)
SCANLINE_ALPHA_CAP = 8
SCANLINE_ALPHA_DIVISOR = 20

LOGO_OFFSET_Y = -110
LOGO_GLOW_MIN_ALPHA = 10
LOGO_GLOW_RADIUS = 60
LOGO_GLOW_ALPHA_DIVISOR = 8
CYAN = (0, 255, 238)
BLUE = (0, 170, 255)
GREEN = (0, 255, 136)

OUTER_RING_RADIUS = 45
OUTER_RING_WIDTH = 2.0
INNER_RING_RADIUS = 28
INNER_RING_WIDTH = 1.5
INNER_RING_ALPHA_SHARE = 0.6
ORBIT_WIDTH = 1.2
ORBIT_ALPHA_SHARE = 0.5
ORBIT_ANGLES = (30, -30)
ORBIT_TRAIL_SPIN_SHARE = 0.7
ORBIT_RECT = (-52, -17, 104, 34)

SPIN_DEGREES_PER_S = 15
PULSE_BASE = 1.0
PULSE_DEPTH = 0.05
PULSE_RATE = 2.5

MONOGRAM = "A"
MONOGRAM_FONT = ("Helvetica", 26)
MONOGRAM_RECT = (-20, -16, 40, 32)
BOLD = "bold"

PARTICLE_ANGLES = (60, 200, 320)
PARTICLE_SPIN_SHARE = (1.2, -0.8)
PARTICLE_RADIUS = 45
PARTICLE_SIZE = 6
PARTICLE_TRAILS = 3
PARTICLE_TRAIL_STEP_DEGREES = 8
PARTICLE_TRAIL_SIZE = 3
PARTICLE_TRAIL_ALPHA_DIVISOR = 3

TITLE = "ACERVATOR"
TITLE_FONT = ("Segoe UI", 32)
TITLE_RGB = (0, 255, 210)
TITLE_RECT = (-25, 45)
TITLE_GLOW_BASE = 60
TITLE_GLOW_DEPTH = 30
TITLE_GLOW_RATE = 2.0
TITLE_GLOW_FLOOR = 140

RULE_MAX_WIDTH = 200
RULE_START_S = 1.0
RULE_GROW_S = 0.5
RULE_MIN_WIDTH = 5
RULE_OFFSET_Y = 22
RULE_WIDTH = 1.5

SUBTITLE = "An Accumulation Trading Platform"
SUBTITLE_FONT = ("Segoe UI", 12)
SUBTITLE_RGB = (140, 155, 210)
SUBTITLE_RECT = (30, 22)

VERSION_PREFIX = "v"
VERSION_FONT = ("Consolas", 9)
VERSION_RGB = (90, 150, 255)
VERSION_RECT = (55, 16)

CREDIT_LABEL_RGB = (140, 140, 170)
CREDIT_LABEL_FONT = ("Segoe UI", 9)
DESIGNER_LABEL = "Designed, prompted, and engineered by"
DESIGNER_LABEL_RECT = (90, 16)
DESIGNER = "Ekthelius the Accumulator"
DESIGNER_FONT = ("Segoe UI", 13)
DESIGNER_RGB = (255, 200, 80)
DESIGNER_RECT = (108, 24)
DESIGNER_ALIAS = "a.k.a. Anthony L. Brown"
DESIGNER_ALIAS_RGB = (180, 170, 140)
DESIGNER_ALIAS_ALPHA_SHARE = 0.7
DESIGNER_ALIAS_RECT = (132, 16)
BUILDER_LABEL = "Built, simulated, tested, and verified by"
BUILDER_LABEL_RECT = (160, 16)
BUILDER = "Claude of Anthropic"
BUILDER_FONT = ("Segoe UI", 12)
BUILDER_RGB = (120, 160, 255)
BUILDER_RECT = (178, 20)

HINT = "click anywhere to continue"
HINT_FONT = ("Segoe UI", 8)
HINT_RGB = (80, 80, 110)
HINT_AT_S = 3.0
HINT_GROW_S = 0.5
HINT_MAX_ALPHA = 80
HINT_OFFSET_Y = -30
HINT_HEIGHT = 16

ALIGN_CENTRE = "centre"
NO_PEN = "no_pen"
NO_BRUSH = "no_brush"
ANTIALIASING = "antialiasing"

BUILT = "built"
TICKED = "ticked"
ENTERED_GLOW = "entered_glow"
ENTERED_FADEOUT = "entered_fadeout"
CLOSED = "closed"
HANDOFF_SCHEDULED = "handoff_scheduled"
HANDOFF_SKIPPED = "handoff_skipped"
REPAINTED = "repainted"
CLICKED = "clicked"
SCREEN_GEOMETRY = "screen_geometry"
TARGET_GEOMETRY = "target_geometry"

CALL_NAMES = (
    BUILT,
    TICKED,
    ENTERED_GLOW,
    ENTERED_FADEOUT,
    CLOSED,
    HANDOFF_SCHEDULED,
    HANDOFF_SKIPPED,
    REPAINTED,
    CLICKED,
    SCREEN_GEOMETRY,
    TARGET_GEOMETRY,
)

ACTIONS = {"timeout": "tick"}
TIMERS = {"tick": TIMER_INTERVAL_MS}
TIMER_DELAYS_MS = (TIMER_INTERVAL_MS, HANDOFF_DELAY_MS)
BUS_TOPICS: tuple = ()

DEFAULT_GEOMETRY = (0, 0, 800, 800)


def running_version() -> str:
    """The version the splash paints, read when asked rather than at import."""
    from src import __version__

    return str(__version__)


def master_opacity(t: Any) -> Any:
    """How much of the whole picture is painted at elapsed time `t`.

    Rises through the first second, holds, then falls away over the 2.5
    seconds after the sixth. A time that compares false against both
    bounds -- a not-a-number -- holds full.
    """
    if t < MASTER_RISE_S:
        return t
    if t > MASTER_FALL_FROM_S:
        return max(0, 1.0 - (t - MASTER_FALL_FROM_S) / MASTER_FALL_S)
    return 1.0


def master_alpha(t: Any) -> int:
    """The master opacity as the 0-255 alpha every colour carries."""
    return int(master_opacity(t) * FULL_ALPHA)


def element_alpha(t: Any, fade: tuple, alpha: int) -> int:
    """One element's alpha: its own fade, scaled by the master alpha."""
    start, duration = fade
    return int(min(1, max(0, (t - start) / duration)) * alpha)


def spin_degrees(t: Any) -> Any:
    """How far the logo rings and particles have turned at `t`."""
    return t * SPIN_DEGREES_PER_S


def pulse_scale(t: Any) -> Any:
    """The breathing scale the logo carries at `t`."""
    return PULSE_BASE + PULSE_DEPTH * math.sin(t * PULSE_RATE)


def rule_width(t: Any) -> int:
    """How wide the rule under the title has grown at `t`."""
    return min(
        RULE_MAX_WIDTH,
        int(RULE_MAX_WIDTH * min(1, max(0, (t - RULE_START_S) / RULE_GROW_S))),
    )


def hint_alpha(t: Any) -> int:
    """The alpha of the click hint at `t`. Painted only after the third second."""
    return int(min(1, (t - HINT_AT_S) / HINT_GROW_S) * HINT_MAX_ALPHA)


def title_glow(t: Any) -> int:
    """The breathing brightness the title carries at `t`."""
    return int(TITLE_GLOW_BASE + TITLE_GLOW_DEPTH * math.sin(t * TITLE_GLOW_RATE))


def _rgba(rgb: tuple, alpha: Any) -> list:
    return [rgb[0], rgb[1], rgb[2], alpha]


def _font(spec: tuple, bold: bool = False) -> list:
    return ["font", spec[0], spec[1], BOLD] if bold else ["font", spec[0], spec[1]]


def _centred_text(rect: list, text: str) -> list:
    return ["text", rect, ALIGN_CENTRE, text]


def background_gradient(width: Any, height: Any, alpha: Any) -> list:
    """The four-stop gradient the splash fills its whole rectangle with."""
    return [
        "gradient",
        [0, 0],
        [width * BACKGROUND_WIDTH_SHARE, height],
        [[at, _rgba(rgb, alpha)] for at, rgb in BACKGROUND_STOPS],
    ]


def paint_ops(t: Any, width: Any, height: Any, version: Optional[str] = None) -> list:
    """Every painter call the splash makes at elapsed time `t`, in order.

    `width` and `height` are the rectangle the splash was given. `version`
    is the text under the subtitle; left out, the running version is read.
    """
    painted = str(running_version() if version is None else version)
    alpha = master_alpha(t)
    logo_a = element_alpha(t, LOGO_FADE, alpha)
    title_a = element_alpha(t, TITLE_FADE, alpha)
    sub_a = element_alpha(t, SUBTITLE_FADE, alpha)
    cred_a = element_alpha(t, CREDIT_FADE, alpha)

    ops: list = [
        ["render_hint", ANTIALIASING],
        ["pen_style", NO_PEN],
        ["fill_rect", 0, 0, width, height, background_gradient(width, height, alpha)],
    ]

    if alpha > SCANLINE_MIN_ALPHA:
        ops.append(
            [
                "pen_colour",
                _rgba(
                    SCANLINE_RGB,
                    min(SCANLINE_ALPHA_CAP, alpha // SCANLINE_ALPHA_DIVISOR),
                ),
            ]
        )
        for y in range(0, height, SCANLINE_STEP_PX):
            ops.append(["line", 0, y, width, y])

    cx = width / 2
    cy = height / 2
    logo_y = cy + LOGO_OFFSET_Y
    spin = spin_degrees(t)
    pulse = pulse_scale(t)

    if logo_a > LOGO_GLOW_MIN_ALPHA:
        glow_r = int(LOGO_GLOW_RADIUS * pulse)
        ops.append(["pen_style", NO_PEN])
        ops.append(["brush_colour", _rgba(CYAN, logo_a // LOGO_GLOW_ALPHA_DIVISOR)])
        ops.append(
            [
                "ellipse",
                [cx - glow_r, logo_y - glow_r, glow_r * 2, glow_r * 2],
            ]
        )

    ops.append(["pen", _rgba(CYAN, logo_a), OUTER_RING_WIDTH])
    ops.append(["brush_style", NO_BRUSH])
    outer_r = OUTER_RING_RADIUS * pulse
    ops.append(["ellipse", [cx - outer_r, logo_y - outer_r, outer_r * 2, outer_r * 2]])

    ops.append(
        ["pen", _rgba(BLUE, int(logo_a * INNER_RING_ALPHA_SHARE)), INNER_RING_WIDTH]
    )
    inner_r = INNER_RING_RADIUS * pulse
    ops.append(["ellipse", [cx - inner_r, logo_y - inner_r, inner_r * 2, inner_r * 2]])

    ops.append(["pen", _rgba(GREEN, int(logo_a * ORBIT_ALPHA_SHARE)), ORBIT_WIDTH])
    turned = (
        ORBIT_ANGLES[0] + spin,
        ORBIT_ANGLES[1] - spin * ORBIT_TRAIL_SPIN_SHARE,
    )
    for angle in turned:
        ops.append(["save"])
        ops.append(["translate", cx, logo_y])
        ops.append(["rotate", angle])
        ops.append(["ellipse", list(ORBIT_RECT)])
        ops.append(["restore"])

    ops.append(["pen_colour", _rgba(CYAN, logo_a)])
    ops.append(_font(MONOGRAM_FONT, bold=True))
    ops.append(
        _centred_text(
            [
                cx + MONOGRAM_RECT[0],
                logo_y + MONOGRAM_RECT[1],
                MONOGRAM_RECT[2],
                MONOGRAM_RECT[3],
            ],
            MONOGRAM,
        )
    )

    ops.append(["pen_style", NO_PEN])
    half = PARTICLE_SIZE / 2
    trail_half = PARTICLE_TRAIL_SIZE / 2
    for index, base_angle in enumerate(PARTICLE_ANGLES):
        share = PARTICLE_SPIN_SHARE[0] if index % 2 == 0 else PARTICLE_SPIN_SHARE[1]
        angle = base_angle + spin * share
        ex = cx + PARTICLE_RADIUS * pulse * math.cos(math.radians(angle))
        ey = logo_y + PARTICLE_RADIUS * pulse * math.sin(math.radians(angle))
        ops.append(["brush_colour", _rgba(GREEN, logo_a)])
        ops.append(["ellipse", [ex - half, ey - half, PARTICLE_SIZE, PARTICLE_SIZE]])
        for trail in range(1, PARTICLE_TRAILS + 1):
            behind = angle - trail * PARTICLE_TRAIL_STEP_DEGREES
            tx = cx + PARTICLE_RADIUS * pulse * math.cos(math.radians(behind))
            ty = logo_y + PARTICLE_RADIUS * pulse * math.sin(math.radians(behind))
            faded = max(0, logo_a // (trail * PARTICLE_TRAIL_ALPHA_DIVISOR))
            ops.append(["brush_colour", _rgba(GREEN, faded)])
            ops.append(
                [
                    "ellipse",
                    [
                        tx - trail_half,
                        ty - trail_half,
                        PARTICLE_TRAIL_SIZE,
                        PARTICLE_TRAIL_SIZE,
                    ],
                ]
            )

    ops.append(
        [
            "pen_colour",
            _rgba(TITLE_RGB, min(title_a, title_glow(t) + TITLE_GLOW_FLOOR)),
        ]
    )
    ops.append(_font(TITLE_FONT, bold=True))
    ops.append(_centred_text([0, cy + TITLE_RECT[0], width, TITLE_RECT[1]], TITLE))

    line_w = rule_width(t)
    if line_w > RULE_MIN_WIDTH:
        ops.append(["pen", _rgba(CYAN, sub_a), RULE_WIDTH])
        ops.append(
            [
                "line",
                int(cx - line_w / 2),
                int(cy + RULE_OFFSET_Y),
                int(cx + line_w / 2),
                int(cy + RULE_OFFSET_Y),
            ]
        )

    ops.append(["pen_colour", _rgba(SUBTITLE_RGB, sub_a)])
    ops.append(_font(SUBTITLE_FONT))
    ops.append(
        _centred_text([0, cy + SUBTITLE_RECT[0], width, SUBTITLE_RECT[1]], SUBTITLE)
    )

    ops.append(["pen_colour", _rgba(VERSION_RGB, sub_a)])
    ops.append(_font(VERSION_FONT))
    ops.append(
        _centred_text(
            [0, cy + VERSION_RECT[0], width, VERSION_RECT[1]],
            VERSION_PREFIX + painted,
        )
    )

    ops.append(["pen_colour", _rgba(CREDIT_LABEL_RGB, cred_a)])
    ops.append(_font(CREDIT_LABEL_FONT))
    ops.append(
        _centred_text(
            [0, cy + DESIGNER_LABEL_RECT[0], width, DESIGNER_LABEL_RECT[1]],
            DESIGNER_LABEL,
        )
    )
    ops.append(["pen_colour", _rgba(DESIGNER_RGB, cred_a)])
    ops.append(_font(DESIGNER_FONT, bold=True))
    ops.append(
        _centred_text([0, cy + DESIGNER_RECT[0], width, DESIGNER_RECT[1]], DESIGNER)
    )
    ops.append(
        [
            "pen_colour",
            _rgba(DESIGNER_ALIAS_RGB, int(cred_a * DESIGNER_ALIAS_ALPHA_SHARE)),
        ]
    )
    ops.append(_font(CREDIT_LABEL_FONT))
    ops.append(
        _centred_text(
            [0, cy + DESIGNER_ALIAS_RECT[0], width, DESIGNER_ALIAS_RECT[1]],
            DESIGNER_ALIAS,
        )
    )
    ops.append(["pen_colour", _rgba(CREDIT_LABEL_RGB, cred_a)])
    ops.append(_font(CREDIT_LABEL_FONT))
    ops.append(
        _centred_text(
            [0, cy + BUILDER_LABEL_RECT[0], width, BUILDER_LABEL_RECT[1]],
            BUILDER_LABEL,
        )
    )
    ops.append(["pen_colour", _rgba(BUILDER_RGB, cred_a)])
    ops.append(_font(BUILDER_FONT, bold=True))
    ops.append(
        _centred_text([0, cy + BUILDER_RECT[0], width, BUILDER_RECT[1]], BUILDER)
    )

    if t > HINT_AT_S:
        ops.append(["pen_colour", _rgba(HINT_RGB, hint_alpha(t))])
        ops.append(_font(HINT_FONT))
        ops.append(_centred_text([0, height + HINT_OFFSET_Y, width, HINT_HEIGHT], HINT))

    ops.append(["end"])
    return ops


class SplashScreenModel:
    """One splash's clock, phase and geometry, with no Qt object behind it.

    Built with the rectangle the primary screen reports, falling back to the
    rectangle the window it covers reports when there is no screen. Holds
    the branch markers of every path taken so far.
    """

    def __init__(
        self,
        screen_geometry: Optional[tuple] = None,
        target_geometry: Optional[tuple] = None,
        on_finished=None,
    ) -> None:
        self.calls: list = [BUILT]
        self.elapsed_s: Any = 0.0
        self.phase = FADEIN
        self.on_finished = on_finished
        self.is_open = True
        self.closes = 0
        self.timer_running = True
        self.repaints = 0
        self.handoff_delays_ms: list = []
        if screen_geometry is not None:
            self.calls.append(SCREEN_GEOMETRY)
            self.geometry = list(screen_geometry)
        else:
            self.calls.append(TARGET_GEOMETRY)
            self.geometry = list(
                DEFAULT_GEOMETRY if target_geometry is None else target_geometry
            )

    def width(self) -> Any:
        """The width of the rectangle the splash paints into."""
        return self.geometry[2]

    def height(self) -> Any:
        """The height of the rectangle the splash paints into."""
        return self.geometry[3]

    def tick(self) -> None:
        """Advance the clock by one 25 ms step and move the phase on.

        At most one phase change happens per step. The step that ends the
        fade-out stops the timer, closes the window and schedules the
        caller's callback, and paints nothing. There is no re-entry guard:
        a further step past the close closes again and schedules again,
        which the stopped timer is what prevents.
        """
        self.calls.append(TICKED)
        self.elapsed_s += TICK_SECONDS
        if self.phase == FADEIN and self.elapsed_s >= GLOW_AT_S:
            self.phase = GLOW
            self.calls.append(ENTERED_GLOW)
        elif self.phase == GLOW and self.elapsed_s >= FADEOUT_AT_S:
            self.phase = FADEOUT
            self.calls.append(ENTERED_FADEOUT)
        elif self.phase == FADEOUT and self.elapsed_s >= CLOSE_AT_S:
            self.timer_running = False
            self.is_open = False
            self.closes += 1
            self.calls.append(CLOSED)
            if self.on_finished is not None:
                self.handoff_delays_ms.append(HANDOFF_DELAY_MS)
                self.calls.append(HANDOFF_SCHEDULED)
            else:
                self.calls.append(HANDOFF_SKIPPED)
            return
        self.repaints += 1
        self.calls.append(REPAINTED)

    def clicked(self) -> None:
        """Jump the clock to the start of the fade-out."""
        self.calls.append(CLICKED)
        self.elapsed_s = CLICK_JUMPS_TO_S
        self.phase = FADEOUT

    def paint_ops(self, version: Optional[str] = None) -> list:
        """Every painter call this splash makes at its current time."""
        return paint_ops(self.elapsed_s, self.width(), self.height(), version)


def build_view_model(
    model: Optional[SplashScreenModel] = None, version: Optional[str] = None
) -> dict:
    """Return the whole splash state as one serialisable dict."""
    state = SplashScreenModel() if model is None else model
    return {
        "phase": state.phase,
        "phases": list(PHASES),
        "elapsed_s": state.elapsed_s,
        "geometry": list(state.geometry),
        "is_open": state.is_open,
        "closes": state.closes,
        "timer_running": state.timer_running,
        "repaints": state.repaints,
        "handoff_delays_ms": list(state.handoff_delays_ms),
        "window_flags": list(WINDOW_FLAGS),
        "delete_on_close": DELETE_ON_CLOSE,
        "translucent_background": TRANSLUCENT_BACKGROUND,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "phase_boundaries_s": {
            GLOW: GLOW_AT_S,
            FADEOUT: FADEOUT_AT_S,
            "close": CLOSE_AT_S,
        },
        "element_fades": {
            "logo": list(LOGO_FADE),
            "title": list(TITLE_FADE),
            "subtitle": list(SUBTITLE_FADE),
            "credit": list(CREDIT_FADE),
        },
        "texts": [TITLE, SUBTITLE, MONOGRAM, DESIGNER, DESIGNER_ALIAS, BUILDER, HINT],
        "labels": [DESIGNER_LABEL, BUILDER_LABEL],
        "paint_ops": state.paint_ops(version),
        "call_names": list(CALL_NAMES),
        "calls": list(state.calls),
        "method": METHOD,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``splash_screen.state``.

    Builds a splash over the rectangle under ``screen_geometry`` or
    ``target_geometry``, ticks it as many times as ``ticks`` asks, clicks it
    when ``click`` is asked for, and paints the version under ``version``.
    """
    asked = params or {}
    screen = asked.get("screen_geometry")
    state = SplashScreenModel(
        screen_geometry=tuple(screen) if screen else None,
        target_geometry=(
            tuple(asked["target_geometry"]) if asked.get("target_geometry") else None
        ),
        on_finished=asked.get("on_finished"),
    )
    if asked.get("click"):
        state.clicked()
    for _ in range(int(asked.get("ticks", 0) or 0)):
        state.tick()
    return build_view_model(state, version=asked.get("version"))
