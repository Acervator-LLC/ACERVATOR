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

BOLD = "bold"

MARK_ELEMENTS = (
    "compass",
    "scale",
    "reptilian eye",
    "fiery aura",
    "scythe",
    "winged caduceus",
)
MARK_RADIUS = 40.0
FULL_TURN_DEGREES = 360.0
CURVE_STEPS = 18
LENS_STEPS = 16
MIN_SEGMENT = 1e-9

FACET_BANDS = 3
FACET_DETAIL = 1.0
FACET_DARK = 0.52
FACET_BRIGHT = 1.0
FACET_LIGHT_X = -0.24
FACET_LIGHT_Y = -0.32
FACET_JITTER = 0.11
FACET_JITTER_STEP = 0.6180339887
FACET_AURA_SWING = 0.22
FACET_AURA_TRAVEL = 2.0
FACET_SEAM_WIDTH = 0.6
DISC_STEPS = 16
STAFF_STEPS = 10
WING_SAMPLES = 26
BEAM_STEPS = 8
HANGER_STEPS = 4
BARB_BANDS = 1

STAFF_TOP_Y = -0.88
STAFF_BOTTOM_Y = 0.98
STAFF_HALF_TOP = 0.017
STAFF_HALF_BOTTOM = 0.031
FINIAL_Y = -0.93
FINIAL_RADIUS = 0.044

WING_ROOT = (0.050, -0.72)
WING_BEND = (0.34, -0.97)
WING_TIP = (0.74, -0.88)
WING_LOBES = 4
WING_LOBE_STEPS = 5
WING_LOBE_DEPTH = 0.090
WING_LOBE_TAPER = 0.55

COMPASS_HINGE_Y = -0.56
COMPASS_HINGE_RADIUS = 0.058
COMPASS_POINT = (0.62, 0.96)
COMPASS_HALF_HINGE = 0.036
COMPASS_HALF_POINT = 0.007
COMPASS_LEG_STEPS = 12

EYE_CENTRE_Y = -0.02
EYE_HALF_WIDTH = 0.300
EYE_UPPER_BULGE = 0.172
EYE_LOWER_BULGE = 0.150
EYE_LID_HALF = 0.014
IRIS_RADIUS = 0.125
SLIT_HALF_MIN = 0.010
SLIT_HALF_MAX = 0.044
SLIT_HALF_MID = 0.027
SLIT_HALF_SWING = 0.017
SLIT_HALF_HEIGHT = 0.108
SLIT_STEPS = 10

AURA_POINTS = 13
AURA_START_DEGREES = -90.0
AURA_BASE_X = 0.380
AURA_BASE_Y = 0.272
AURA_BASE_SPREAD_DEGREES = 12.5
AURA_CURL_DEGREES = 16.0
AURA_TIP_SHARE = 1.58
AURA_SPREAD_TAPER = 0.85
AURA_FLAME_STEPS = 7

SERPENT_HEAD_Y = -0.68
SERPENT_TAIL_Y = 0.92
SERPENT_BOW = 0.265
SERPENT_COILS = 2.0
SERPENT_STEPS = 40
SERPENT_HALF_HEAD = 0.042
SERPENT_HALF_TAIL = 0.009
SERPENT_SNOUT = (0.150, -0.060)
SERPENT_JAW = (0.150, 0.032)
SERPENT_TONGUE = (0.250, -0.020)
SERPENT_TONGUE_FORK = 0.040
SERPENT_TONGUE_HALF = 0.007
SERPENT_EYE_OFFSET = (0.072, -0.022)
SERPENT_EYE_RADIUS = 0.017
SERPENT_BROW_SHARE = 0.52
SERPENT_BROW_LIFT = 1.30

SCALE_BEAM_Y = 0.52
SCALE_BEAM_HALF = 0.38
SCALE_BEAM_HALF_THICK = 0.019
SCALE_BOSS_RADIUS = 0.042
SCALE_HANGER_X = 0.330
SCALE_HANGER_DROP = 0.200
SCALE_HANGER_HALF = 0.008
SCALE_PAN_HALF = 0.125
SCALE_PAN_DEPTH = 0.058
SCALE_PAN_HALF_THICK = 0.011
SCALE_PAN_STEPS = 10
SCALE_TILT_MAX_DEGREES = 9.0
SCALE_SWING_RATE = 4.2
SCALE_SETTLE_TAU_S = 0.9
SCALE_SETTLE_LIMIT_S = 5.0

SCYTHE_BUTT = (0.90, 0.86)
SCYTHE_BEND = (0.52, 0.16)
SCYTHE_HEAD = (-0.20, -0.46)
SCYTHE_HALF_BUTT = 0.034
SCYTHE_HALF_HEAD = 0.020

FEATHER_QUILL = (-0.56, -0.70)
FEATHER_TIP = (-0.98, -0.48)
FEATHER_HALF_BASE = 0.020
FEATHER_HALF_TIP = 0.005
FEATHER_VANE_UPPER = 0.108
FEATHER_VANE_LOWER = 0.078
FEATHER_VANE_TAPER = 0.62
FEATHER_LOWER_SPAN = (0.04, 0.97)
FEATHER_UPPER_SPANS = ((0.04, 0.47), (0.60, 0.97))
FEATHER_SPLIT_SPAN = (0.47, 0.60)
FEATHER_SPLIT_BARBS = 3
FEATHER_BARBS = 15
FEATHER_BARB_RAKE_DEGREES = 42.0
FEATHER_BARB_SHARE = 0.94
FEATHER_BARB_HALF_ROOT = 0.0075
FEATHER_BARB_HALF_TIP = 0.0012
FEATHER_VANE_STEPS = 24

STAFF_ALPHA_SHARE = 0.88
WING_ALPHA_SHARE = 0.92
COMPASS_ALPHA_SHARE = 0.85
SERPENT_ALPHA_SHARE = 0.78
SCALE_ALPHA_SHARE = 0.82
AURA_ALPHA_SHARE = 0.72
EYE_ALPHA_SHARE = 1.0
IRIS_ALPHA_SHARE = 0.85
SCYTHE_ALPHA_SHARE = 0.70
FEATHER_VANE_ALPHA_SHARE = 0.26
FEATHER_BARB_ALPHA_SHARE = 0.66
PUPIL_RGB = (6, 6, 14)

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


def slit_half_width(pulse: Any) -> Any:
    """The reptilian pupil's half-width at this breath, clamped to the slit bounds."""
    breath = (pulse - PULSE_BASE) / PULSE_DEPTH
    return max(
        SLIT_HALF_MIN, min(SLIT_HALF_MAX, SLIT_HALF_MID + SLIT_HALF_SWING * breath)
    )


def scale_tilt_degrees(t: Any) -> Any:
    """How far the balance beam sits off level at `t`, swinging then settling."""
    since = t - LOGO_FADE[0]
    if not math.isfinite(since) or since <= 0 or since > SCALE_SETTLE_LIMIT_S:
        return 0.0
    return (
        SCALE_TILT_MAX_DEGREES
        * math.cos(SCALE_SWING_RATE * since)
        * math.exp(-since / SCALE_SETTLE_TAU_S)
    )


def _steps(base: int) -> int:
    return max(2, int(round(base * FACET_DETAIL)))


def _between(start: list, end: list, share: Any) -> list:
    return [
        start[0] + (end[0] - start[0]) * share,
        start[1] + (end[1] - start[1]) * share,
    ]


def _strip(left: list, right: list, bands: int) -> list:
    """Triangles filling the band between two edge chains, `bands` facets across."""
    faces: list = []
    count = min(len(left), len(right))
    for index in range(count - 1):
        for band in range(bands):
            near = band / bands
            far = (band + 1) / bands
            corner = [
                _between(left[index], right[index], near),
                _between(left[index + 1], right[index + 1], near),
                _between(left[index + 1], right[index + 1], far),
                _between(left[index], right[index], far),
            ]
            faces.append([corner[0], corner[1], corner[2]])
            faces.append([corner[0], corner[2], corner[3]])
    return faces


def _fan(centre: list, rim: list) -> list:
    return [[list(centre), rim[index], rim[index + 1]] for index in range(len(rim) - 1)]


def _disc(centre_x: Any, centre_y: Any, radius: Any) -> list:
    steps = _steps(DISC_STEPS)
    rim = []
    for index in range(steps + 1):
        radians = math.radians(FULL_TURN_DEGREES * index / steps)
        rim.append(
            [
                centre_x + radius * math.cos(radians),
                centre_y + radius * math.sin(radians),
            ]
        )
    return _fan([centre_x, centre_y], rim)


def _resample(points: list, count: int) -> list:
    out = []
    last = len(points) - 1
    for index in range(count):
        at = last * index / (count - 1)
        low = int(at)
        out.append(_between(points[low], points[min(low + 1, last)], at - low))
    return out


def _mirrored_faces(faces: list) -> list:
    return [[[-point[0], point[1]] for point in face] for face in faces]


def _rotated(x: Any, y: Any, pivot_y: Any, degrees: Any) -> tuple:
    radians = math.radians(degrees)
    dy = y - pivot_y
    return (
        x * math.cos(radians) - dy * math.sin(radians),
        pivot_y + x * math.sin(radians) + dy * math.cos(radians),
    )


def _quadratic(start: tuple, bend: tuple, end: tuple, steps: int) -> list:
    """`steps` plus one points along the quadratic curve from `start` to `end`."""
    out = []
    for index in range(steps + 1):
        u = index / steps
        v = 1.0 - u
        out.append(
            (
                v * v * start[0] + 2 * v * u * bend[0] + u * u * end[0],
                v * v * start[1] + 2 * v * u * bend[1] + u * u * end[1],
            )
        )
    return out


def _normal(behind: tuple, ahead: tuple) -> tuple:
    dx = ahead[0] - behind[0]
    dy = ahead[1] - behind[1]
    length = math.hypot(dx, dy)
    if length < MIN_SEGMENT:
        return (0.0, 0.0)
    return (-dy / length, dx / length)


def _ribbon_edges(points: list, half_start: Any, half_end: Any) -> tuple:
    """Two edge chains either side of `points`, the half-width tapering along it."""
    count = len(points)
    left: list = []
    right: list = []
    for index, point in enumerate(points):
        nx, ny = _normal(points[max(index - 1, 0)], points[min(index + 1, count - 1)])
        share = index / (count - 1) if count > 1 else 0.0
        half = half_start + (half_end - half_start) * share
        left.append([point[0] + nx * half, point[1] + ny * half])
        right.append([point[0] - nx * half, point[1] - ny * half])
    return left, right


def _ribbon_faces(points: list, half_start: Any, half_end: Any, bands: int) -> list:
    left, right = _ribbon_edges(points, half_start, half_end)
    return _strip(left, right, bands)


def _vane_edges(points: list, side: int, width: Any, span: tuple) -> tuple:
    """The outer edge and the rachis spine of one vane lobe, over `span` of it."""
    count = len(points)
    edge: list = []
    spine: list = []
    for index, point in enumerate(points):
        share = index / (count - 1) if count > 1 else 0.0
        if share < span[0] or share > span[1]:
            continue
        nx, ny = _normal(points[max(index - 1, 0)], points[min(index + 1, count - 1)])
        half = width * math.sin(math.pi * share) ** FEATHER_VANE_TAPER
        edge.append([point[0] + nx * half * side, point[1] + ny * half * side])
        spine.append([point[0], point[1]])
    return edge, spine


def _lens_edges(
    centre_y: Any, half_width: Any, up: Any, down: Any, steps: int
) -> tuple:
    """The upper and lower edges of a pointed almond, both running left to right."""
    upper: list = []
    lower: list = []
    for index in range(steps + 1):
        across = -1.0 + 2.0 * index / steps
        bulge = 1.0 - across * across
        upper.append([half_width * across, centre_y - up * bulge])
        lower.append([half_width * across, centre_y + down * bulge])
    return upper, lower


def _slit_edges(half_width: Any, steps: int) -> tuple:
    """The two edges of the pupil, pointed top and bottom and widest at the middle."""
    right: list = []
    left: list = []
    for index in range(steps + 1):
        along = -1.0 + 2.0 * index / steps
        bulge = 1.0 - along * along
        right.append([half_width * bulge, EYE_CENTRE_Y + SLIT_HALF_HEIGHT * along])
        left.append([-half_width * bulge, EYE_CENTRE_Y + SLIT_HALF_HEIGHT * along])
    return right, left


def _wing_edges() -> tuple:
    """The wing's curved leading edge and its `WING_LOBES` scalloped trailing edge."""
    lead = _quadratic(WING_ROOT, WING_BEND, WING_TIP, _steps(CURVE_STEPS))
    trail: list = []
    for lobe in range(WING_LOBES):
        at = lobe / WING_LOBES
        to = (lobe + 1) / WING_LOBES
        start = (
            WING_TIP[0] + (WING_ROOT[0] - WING_TIP[0]) * at,
            WING_TIP[1] + (WING_ROOT[1] - WING_TIP[1]) * at,
        )
        end = (
            WING_TIP[0] + (WING_ROOT[0] - WING_TIP[0]) * to,
            WING_TIP[1] + (WING_ROOT[1] - WING_TIP[1]) * to,
        )
        depth = WING_LOBE_DEPTH * (1.0 - at * WING_LOBE_TAPER)
        bend = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + depth)
        trail.extend(_quadratic(start, bend, end, _steps(WING_LOBE_STEPS)))
    trail.reverse()
    samples = _steps(WING_SAMPLES)
    return (
        _resample([[point[0], point[1]] for point in lead], samples),
        _resample([[point[0], point[1]] for point in trail], samples),
    )


def _aura_point(degrees: Any, share: Any) -> list:
    radians = math.radians(degrees)
    return [
        AURA_BASE_X * share * math.cos(radians),
        EYE_CENTRE_Y + AURA_BASE_Y * share * math.sin(radians),
    ]


def aura_flame_edges(index: int, spin: Any) -> tuple:
    """The trailing and leading edges of one flame, both running base to tip."""
    middle = AURA_START_DEGREES + index * FULL_TURN_DEGREES / AURA_POINTS + spin
    trailing: list = []
    leading: list = []
    steps = _steps(AURA_FLAME_STEPS)
    for step in range(steps + 1):
        height = step / steps
        angle = middle + AURA_CURL_DEGREES * height * height
        reach = 1.0 + (AURA_TIP_SHARE - 1.0) * height
        spread = AURA_BASE_SPREAD_DEGREES * (1.0 - height) ** AURA_SPREAD_TAPER
        trailing.append(_aura_point(angle - spread, reach))
        leading.append(_aura_point(angle + spread, reach))
    return trailing, leading


def _serpent_spine(phase: Any) -> list:
    out = []
    steps = _steps(SERPENT_STEPS)
    for index in range(steps + 1):
        along = index / steps
        out.append(
            [
                SERPENT_BOW * math.sin(2 * math.pi * SERPENT_COILS * along + phase),
                SERPENT_HEAD_Y + (SERPENT_TAIL_Y - SERPENT_HEAD_Y) * along,
            ]
        )
    return out


def _pan_spine(centre_x: Any, centre_y: Any) -> list:
    out = []
    steps = _steps(SCALE_PAN_STEPS)
    for index in range(steps + 1):
        across = -1.0 + 2.0 * index / steps
        out.append(
            [
                centre_x + SCALE_PAN_HALF * across,
                centre_y + SCALE_PAN_DEPTH * (1.0 - across * across),
            ]
        )
    return out


def caduceus_faces(spin: Any, pulse: Any) -> list:
    """The staff, its two coiled serpents and the wings, as toneable triangle groups."""
    staff_spine = [
        [0.0, STAFF_TOP_Y + (STAFF_BOTTOM_Y - STAFF_TOP_Y) * step / _steps(STAFF_STEPS)]
        for step in range(_steps(STAFF_STEPS) + 1)
    ]
    groups = [
        (
            _ribbon_faces(staff_spine, STAFF_HALF_TOP, STAFF_HALF_BOTTOM, FACET_BANDS),
            CYAN,
            STAFF_ALPHA_SHARE,
            0.0,
        )
    ]
    for phase in (math.pi / 2, -math.pi / 2):
        spine = _serpent_spine(phase)
        facing = 1.0 if phase > 0 else -1.0
        head = spine[0]
        snout = [
            head[0] + SERPENT_SNOUT[0] * facing,
            head[1] + SERPENT_SNOUT[1],
        ]
        groups.append(
            (
                _ribbon_faces(spine, SERPENT_HALF_HEAD, SERPENT_HALF_TAIL, FACET_BANDS),
                BLUE,
                SERPENT_ALPHA_SHARE,
                0.0,
            )
        )
        groups.append(
            (
                _strip(
                    [
                        [head[0], head[1] - SERPENT_HALF_HEAD],
                        [
                            head[0] + SERPENT_SNOUT[0] * SERPENT_BROW_SHARE * facing,
                            head[1] - SERPENT_HALF_HEAD * SERPENT_BROW_LIFT,
                        ],
                        snout,
                    ],
                    [
                        [head[0], head[1] + SERPENT_HALF_HEAD],
                        [
                            head[0] + SERPENT_JAW[0] * facing,
                            head[1] + SERPENT_JAW[1],
                        ],
                        snout,
                    ],
                    FACET_BANDS,
                ),
                BLUE,
                SERPENT_ALPHA_SHARE,
                0.0,
            )
        )
        for fork in (-SERPENT_TONGUE_FORK, SERPENT_TONGUE_FORK):
            groups.append(
                (
                    _ribbon_faces(
                        [
                            snout,
                            [
                                head[0] + SERPENT_TONGUE[0] * facing,
                                head[1] + SERPENT_TONGUE[1] + fork,
                            ],
                        ],
                        SERPENT_TONGUE_HALF,
                        SERPENT_TONGUE_HALF,
                        BARB_BANDS,
                    ),
                    BLUE,
                    SERPENT_ALPHA_SHARE,
                    0.0,
                )
            )
        groups.append(
            (
                _disc(
                    head[0] + SERPENT_EYE_OFFSET[0] * facing,
                    head[1] + SERPENT_EYE_OFFSET[1],
                    SERPENT_EYE_RADIUS,
                ),
                CYAN,
                EYE_ALPHA_SHARE,
                0.0,
            )
        )
    lead, trail = _wing_edges()
    wing = _strip(lead, trail, FACET_BANDS)
    groups.append((wing, CYAN, WING_ALPHA_SHARE, 0.0))
    groups.append((_mirrored_faces(wing), CYAN, WING_ALPHA_SHARE, 0.0))
    groups.append((_disc(0.0, FINIAL_Y, FINIAL_RADIUS), CYAN, STAFF_ALPHA_SHARE, 0.0))
    return groups


def compass_faces() -> list:
    """The dividers: a hinge above centre and two legs splaying to the A-frame."""
    leg = _quadratic(
        (0.0, COMPASS_HINGE_Y),
        (COMPASS_POINT[0] / 2, (COMPASS_HINGE_Y + COMPASS_POINT[1]) / 2),
        COMPASS_POINT,
        _steps(COMPASS_LEG_STEPS),
    )
    spine = [[point[0], point[1]] for point in leg]
    right = _ribbon_faces(spine, COMPASS_HALF_HINGE, COMPASS_HALF_POINT, FACET_BANDS)
    return [
        (right, CYAN, COMPASS_ALPHA_SHARE, 0.0),
        (_mirrored_faces(right), CYAN, COMPASS_ALPHA_SHARE, 0.0),
        (
            _disc(0.0, COMPASS_HINGE_Y, COMPASS_HINGE_RADIUS),
            CYAN,
            COMPASS_ALPHA_SHARE,
            0.0,
        ),
    ]


def scythe_faces() -> list:
    """The shaft and its blade, the feather of Ma'at, with a split vane and barbs."""
    shaft = [
        [point[0], point[1]]
        for point in _quadratic(
            SCYTHE_BUTT, SCYTHE_BEND, SCYTHE_HEAD, _steps(CURVE_STEPS)
        )
    ]
    rachis = [
        [point[0], point[1]]
        for point in _quadratic(
            SCYTHE_HEAD, FEATHER_QUILL, FEATHER_TIP, _steps(FEATHER_VANE_STEPS)
        )
    ]
    groups = [
        (
            _ribbon_faces(shaft, SCYTHE_HALF_BUTT, SCYTHE_HALF_HEAD, FACET_BANDS),
            CYAN,
            SCYTHE_ALPHA_SHARE,
            0.0,
        ),
        (
            _ribbon_faces(rachis, FEATHER_HALF_BASE, FEATHER_HALF_TIP, FACET_BANDS),
            CYAN,
            SCYTHE_ALPHA_SHARE,
            0.0,
        ),
    ]
    for span in FEATHER_UPPER_SPANS:
        edge, spine = _vane_edges(rachis, 1, FEATHER_VANE_UPPER, span)
        groups.append(
            (
                _strip(edge, spine, FACET_BANDS),
                CYAN,
                FEATHER_VANE_ALPHA_SHARE,
                0.0,
            )
        )
    edge, spine = _vane_edges(rachis, -1, FEATHER_VANE_LOWER, FEATHER_LOWER_SPAN)
    groups.append(
        (_strip(edge, spine, FACET_BANDS), CYAN, FEATHER_VANE_ALPHA_SHARE, 0.0)
    )
    groups.extend(_feather_barb_groups(rachis))
    return groups


def _feather_barb_groups(rachis: list) -> list:
    """The barbs raked back off the rachis, `FEATHER_SPLIT_BARBS` inside the split."""
    groups: list = []
    count = len(rachis) - 1
    rake = math.radians(FEATHER_BARB_RAKE_DEGREES)
    for step in range(1, FEATHER_BARBS + 1):
        share = step / (FEATHER_BARBS + 1)
        index = int(share * count)
        point = rachis[index]
        nx, ny = _normal(rachis[max(index - 1, 0)], rachis[min(index + 1, count)])
        for side in (1.0, -1.0):
            width = (FEATHER_VANE_UPPER if side > 0 else FEATHER_VANE_LOWER) * math.sin(
                math.pi * share
            ) ** FEATHER_VANE_TAPER
            reach = width * FEATHER_BARB_SHARE
            dx = nx * side * math.cos(rake) - ny * side * math.sin(rake)
            dy = nx * side * math.sin(rake) + ny * side * math.cos(rake)
            groups.append(
                (
                    _ribbon_faces(
                        [
                            [point[0], point[1]],
                            [point[0] + dx * reach, point[1] + dy * reach],
                        ],
                        FEATHER_BARB_HALF_ROOT,
                        FEATHER_BARB_HALF_TIP,
                        BARB_BANDS,
                    ),
                    CYAN,
                    FEATHER_BARB_ALPHA_SHARE,
                    0.0,
                )
            )
    span = FEATHER_SPLIT_SPAN[1] - FEATHER_SPLIT_SPAN[0]
    for step in range(FEATHER_SPLIT_BARBS):
        share = FEATHER_SPLIT_SPAN[0] + span * (step + 1) / (FEATHER_SPLIT_BARBS + 1)
        index = int(share * count)
        point = rachis[index]
        nx, ny = _normal(rachis[max(index - 1, 0)], rachis[min(index + 1, count)])
        reach = FEATHER_VANE_UPPER * FEATHER_BARB_SHARE
        groups.append(
            (
                _ribbon_faces(
                    [
                        [point[0], point[1]],
                        [point[0] + nx * reach, point[1] + ny * reach],
                    ],
                    FEATHER_BARB_HALF_ROOT,
                    FEATHER_BARB_HALF_TIP,
                    BARB_BANDS,
                ),
                CYAN,
                FEATHER_BARB_ALPHA_SHARE,
                0.0,
            )
        )
    return groups


def scale_faces(t: Any) -> list:
    """The balance: one beam that settles level, its boss, two hangers and two pans."""
    tilt = scale_tilt_degrees(t)
    beam = _resample(
        [
            list(_rotated(-SCALE_BEAM_HALF, SCALE_BEAM_Y, SCALE_BEAM_Y, tilt)),
            list(_rotated(SCALE_BEAM_HALF, SCALE_BEAM_Y, SCALE_BEAM_Y, tilt)),
        ],
        _steps(BEAM_STEPS),
    )
    groups = [
        (
            _ribbon_faces(
                beam, SCALE_BEAM_HALF_THICK, SCALE_BEAM_HALF_THICK, FACET_BANDS
            ),
            BLUE,
            SCALE_ALPHA_SHARE,
            0.0,
        ),
        (
            _disc(0.0, SCALE_BEAM_Y, SCALE_BOSS_RADIUS),
            BLUE,
            SCALE_ALPHA_SHARE,
            0.0,
        ),
    ]
    for side in (-1.0, 1.0):
        top = _rotated(SCALE_HANGER_X * side, SCALE_BEAM_Y, SCALE_BEAM_Y, tilt)
        pan_y = top[1] + SCALE_HANGER_DROP
        hanger = _resample([[top[0], top[1]], [top[0], pan_y]], _steps(HANGER_STEPS))
        groups.append(
            (
                _ribbon_faces(hanger, SCALE_HANGER_HALF, SCALE_HANGER_HALF, BARB_BANDS),
                BLUE,
                SCALE_ALPHA_SHARE,
                0.0,
            )
        )
        groups.append(
            (
                _ribbon_faces(
                    _pan_spine(top[0], pan_y),
                    SCALE_PAN_HALF_THICK,
                    SCALE_PAN_HALF_THICK,
                    FACET_BANDS,
                ),
                BLUE,
                SCALE_ALPHA_SHARE,
                0.0,
            )
        )
    return groups


def aura_faces(spin: Any) -> list:
    """The `AURA_POINTS` flames wreathing the eye, each retoned as the wreath turns."""
    groups = []
    for index in range(AURA_POINTS):
        trailing, leading = aura_flame_edges(index, spin)
        seat = index * FULL_TURN_DEGREES / AURA_POINTS * FACET_AURA_TRAVEL
        bias = FACET_AURA_SWING * math.cos(math.radians(seat))
        groups.append(
            (_strip(trailing, leading, FACET_BANDS), GREEN, AURA_ALPHA_SHARE, bias)
        )
    return groups


def eye_socket_faces() -> list:
    """The almond, its lid and the iris, everything of the eye but the pupil."""
    upper, lower = _lens_edges(
        EYE_CENTRE_Y,
        EYE_HALF_WIDTH,
        EYE_UPPER_BULGE,
        EYE_LOWER_BULGE,
        _steps(LENS_STEPS),
    )
    outline = upper + list(reversed(lower)) + [upper[0]]
    return [
        (_strip(upper, lower, FACET_BANDS), PUPIL_RGB, EYE_ALPHA_SHARE, 0.0),
        (
            _ribbon_faces(outline, EYE_LID_HALF, EYE_LID_HALF, BARB_BANDS),
            CYAN,
            EYE_ALPHA_SHARE,
            0.0,
        ),
        (
            _disc(0.0, EYE_CENTRE_Y, IRIS_RADIUS),
            BLUE,
            IRIS_ALPHA_SHARE,
            0.0,
        ),
    ]


def pupil_faces(pulse: Any) -> list:
    """The vertical slit pupil at this breath, narrow at the peak and wide at the low."""
    right, left = _slit_edges(slit_half_width(pulse), _steps(SLIT_STEPS))
    return [(_strip(right, left, FACET_BANDS), PUPIL_RGB, EYE_ALPHA_SHARE, 0.0)]


def eye_faces(pulse: Any) -> list:
    """The almond, its lid, the iris and the vertical slit pupil at this breath."""
    return eye_socket_faces() + pupil_faces(pulse)


def mark_layers(spin: Any, pulse: Any, t: Any) -> list:
    """Each component's triangle groups, named, back layer first."""
    return [
        ("winged caduceus", caduceus_faces(spin, pulse)),
        ("compass", compass_faces()),
        ("scythe", scythe_faces()),
        ("scale", scale_faces(t)),
        ("fiery aura", aura_faces(spin)),
        ("reptilian eye", eye_faces(pulse)),
    ]


def mark_triangle_count(spin: Any = 0.0, pulse: Any = 1.0, t: Any = 0.0) -> int:
    """How many triangles the whole mark is built from at this moment."""
    return sum(
        len(faces)
        for _name, groups in mark_layers(spin, pulse, t)
        for faces, _rgb, _share_of, _bias in groups
    )


def _tone(rgb: tuple, alpha: int, level: Any) -> list:
    lit = FACET_DARK + (FACET_BRIGHT - FACET_DARK) * max(0.0, min(1.0, level))
    return [int(rgb[0] * lit), int(rgb[1] * lit), int(rgb[2] * lit), alpha]


def _level(face: list, index: int) -> Any:
    centre_x = (face[0][0] + face[1][0] + face[2][0]) / 3.0
    centre_y = (face[0][1] + face[1][1] + face[2][1]) / 3.0
    drift = FACET_JITTER * (((index + 1) * FACET_JITTER_STEP) % 1.0 - 0.5)
    return 0.5 + FACET_LIGHT_X * centre_x + FACET_LIGHT_Y * centre_y + drift


def toned_mesh(
    faces: list, rgb: tuple, shade: int, bias: Any, cx: Any, cy: Any, radius: Any
) -> list:
    """Place `faces` at (`cx`, `cy`) and give each its own tone of `rgb`."""
    out = []
    for index, face in enumerate(faces):
        colour = _tone(rgb, shade, _level(face, index) + bias)
        out.append(
            [
                [cx + face[0][0] * radius, cy + face[0][1] * radius],
                [cx + face[1][0] * radius, cy + face[1][1] * radius],
                [cx + face[2][0] * radius, cy + face[2][1] * radius],
                colour,
            ]
        )
    return out


def _share(alpha: Any, part: Any) -> int:
    return int(alpha * part)


def sigil_ops(cx: Any, cy: Any, alpha: int, spin: Any, pulse: Any, t: Any) -> list:
    """One `mesh` call per component group of the six `MARK_ELEMENTS`, back first.

    `alpha` is the logo fade, `spin` the turn the rings carry, and `pulse` the
    breath that scales them.
    """
    radius = MARK_RADIUS * pulse
    ops: list = []
    for _name, groups in mark_layers(spin, pulse, t):
        for faces, rgb, part, bias in groups:
            ops.append(
                [
                    "mesh",
                    toned_mesh(faces, rgb, _share(alpha, part), bias, cx, cy, radius),
                ]
            )
    return ops


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

    ops.extend(sigil_ops(cx, logo_y, logo_a, spin, pulse, t))

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
        "texts": [TITLE, SUBTITLE, DESIGNER, DESIGNER_ALIAS, BUILDER, HINT],
        "labels": [DESIGNER_LABEL, BUILDER_LABEL],
        "mark": {
            "elements": list(MARK_ELEMENTS),
            "aura_points": AURA_POINTS,
            "radius": MARK_RADIUS,
            "pupil": "vertical slit",
            "scythe_blade": "feather of Ma'at",
        },
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
