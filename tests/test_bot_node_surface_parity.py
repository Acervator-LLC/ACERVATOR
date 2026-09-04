"""The Qt locust card and the Qt-free surface, driven side by side.

A failure means the view model describes a different coordinate, radius,
angle, width, colour, label, tooltip, drawing order or branch than
``BotNodeWidget`` paints on the same input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import bot_node_surface as surface
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
NODE_SOURCE = REPO_ROOT / "src" / "gui" / "visualizer" / "bot_node.py"
CONNECT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "privacy_dot.py"
SIGNAL_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "launcher.py"
TIMER_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "history_tab.py"
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
ELEMENT_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "widgets" / "dashboard_stat_card.py"
PROPERTY_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "indicator_panel.py"
NESTED_CLASS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "stock_main_window.py"

CARD_SIZE = (112, 98)

CONNECT_TOTAL = 0
SIGNAL_TOTAL = 0
TIMER_TOTAL = 0
BUS_TOPIC_TOTAL = 0
ELEMENT_TOTAL = 0
SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 6
SURFACE_CLASS_TOTAL = 3
SIGNAL_NEIGHBOUR_TOTAL = 3
ELEMENT_NEIGHBOUR_TOTAL = 3
WHOLE_CARD_CALL_TOTAL = 83


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


# The inputs. One table for the card state, one for the card steps.


LONG_TEXT = "L" * 200
MARKUP_TEXT = '<b onclick="x">bold &amp; "quoted"</b>'
UNICODE_TEXT = "比特币 ₿"
NEWLINE_TEXT = "line one\nline two"
APOSTROPHE_TEXT = "the operator's coin"

HAPPY_PHASE = 0.7
DRAWS = [round(0.05 * (index % 19) + 0.02, 4) for index in range(21)]


def stats(**named):
    """One set of the numbers the visualizer keeps for a bot."""
    row = {
        "realised_pnl": 12.5,
        "total_trades": 7,
        "current_price": 50000.0,
        "trade_volume": 2_500_000.0,
    }
    row.update(named)
    return row


def data(**named):
    """One set of the values the visualizer sends the card."""
    row = {
        "bot_id": "abcdef0123456789",
        "symbol": "BTC-USD",
        "state": "running",
        "mode": "scrumming",
        "stats": stats(),
    }
    row.update(named)
    return row


def card(**named):
    """One card state, as both sides are set up with it."""
    spec = {
        "width_px": CARD_SIZE[0],
        "height_px": CARD_SIZE[1],
        "phase": HAPPY_PHASE,
        "theme_key": "quantum",
        "trade_pulses": [],
        "particles": [],
        "antenna_drive": 0.0,
        "bot_data": data(),
    }
    spec.update(named)
    return spec


SPECK = (40.0, 30.0, -12.0, 8.0, 0.9, 2.5)

CARD_SPECS = {
    "happy_running": card(),
    "an_idle_bot": card(bot_data=data(state="idle")),
    "a_paused_bot": card(bot_data=data(state="paused")),
    "a_bot_in_error": card(bot_data=data(state="error")),
    "a_stopped_bot": card(bot_data=data(state="stopped")),
    "a_bot_in_cooldown": card(bot_data=data(state="cooldown")),
    "a_state_nobody_declares": card(bot_data=data(state="melting")),
    "the_state_in_wrong_capitals": card(bot_data=data(state="RUNNING")),
    "no_bot_data_at_all": card(bot_data={}),
    "an_empty_stats_table": card(bot_data=data(stats={})),
    "no_keys_at_all": card(bot_data={"bot_id": "x"}),
    "one_trade_ring": card(trade_pulses=[0.6]),
    "three_trade_rings": card(trade_pulses=[0.9, 0.5, 0.1]),
    "a_ring_wider_than_the_card": card(trade_pulses=[100.0]),
    "a_ring_at_zero": card(trade_pulses=[0.0]),
    "a_negative_ring": card(trade_pulses=[-0.4]),
    "one_speck": card(particles=[SPECK]),
    "five_specks": card(particles=[SPECK] * 5),
    "a_speck_at_infinity": card(particles=[(math.inf, 30.0, 1.0, 1.0, 0.5, 2.0)]),
    "a_speck_at_not_a_number": card(particles=[(math.nan, 30.0, 1.0, 1.0, 0.5, 2.0)]),
    "a_speck_of_no_size": card(particles=[(40.0, 30.0, 1.0, 1.0, 0.5, 0.0)]),
    "a_speck_with_a_life_of_zero": card(particles=[(40.0, 30.0, 1.0, 1.0, 0.0, 2.0)]),
    "the_feelers_swaying": card(antenna_drive=1.0),
    "the_feelers_driven_to_infinity": card(antenna_drive=math.inf),
    "the_feelers_driven_to_not_a_number": card(antenna_drive=math.nan),
    "a_card_of_no_size": card(width_px=0, height_px=0),
    "a_card_one_pixel_wide": card(width_px=1, height_px=1),
    "a_card_wider_than_it_is_tall": card(width_px=300, height_px=98),
    "a_phase_of_zero": card(phase=0.0),
    "a_negative_phase": card(phase=-4.25),
    "a_thousand_million_phase": card(phase=1_000_000_000),
    "one_billionth_phase": card(phase=1e-9),
    "a_phase_at_not_a_number": card(phase=math.nan),
    "zero_profit": card(bot_data=data(stats=stats(realised_pnl=0))),
    "a_loss": card(bot_data=data(stats=stats(realised_pnl=-480.25))),
    "a_thousand_million_profit": card(
        bot_data=data(stats=stats(realised_pnl=1_000_000_000))
    ),
    "one_billionth_profit": card(bot_data=data(stats=stats(realised_pnl=1e-9))),
    "profit_at_infinity": card(bot_data=data(stats=stats(realised_pnl=math.inf))),
    "profit_at_minus_infinity": card(
        bot_data=data(stats=stats(realised_pnl=-math.inf))
    ),
    "profit_at_not_a_number": card(bot_data=data(stats=stats(realised_pnl=math.nan))),
    "profit_as_a_flag": card(bot_data=data(stats=stats(realised_pnl=True))),
    "zero_price": card(bot_data=data(stats=stats(current_price=0))),
    "a_negative_price": card(bot_data=data(stats=stats(current_price=-3.5))),
    "one_billionth_price": card(bot_data=data(stats=stats(current_price=1e-9))),
    "a_thousand_million_price": card(
        bot_data=data(stats=stats(current_price=1_000_000_000))
    ),
    "zero_volume": card(bot_data=data(stats=stats(trade_volume=0))),
    "a_thousand_volume": card(bot_data=data(stats=stats(trade_volume=4_800.0))),
    "a_negative_volume": card(bot_data=data(stats=stats(trade_volume=-900.0))),
    "one_billionth_volume": card(bot_data=data(stats=stats(trade_volume=1e-9))),
    "volume_at_infinity": card(bot_data=data(stats=stats(trade_volume=math.inf))),
    "zero_trades": card(bot_data=data(stats=stats(total_trades=0))),
    "a_negative_trade_count": card(bot_data=data(stats=stats(total_trades=-4))),
    "a_thousand_million_trades": card(
        bot_data=data(stats=stats(total_trades=1_000_000_000))
    ),
    "an_empty_symbol": card(bot_data=data(symbol="")),
    "a_unicode_symbol": card(bot_data=data(symbol=UNICODE_TEXT)),
    "a_two_hundred_character_symbol": card(bot_data=data(symbol=LONG_TEXT)),
    "markup_inside_the_symbol": card(bot_data=data(symbol=MARKUP_TEXT)),
    "an_apostrophe_in_the_symbol": card(bot_data=data(symbol=APOSTROPHE_TEXT)),
    "a_newline_in_the_symbol": card(bot_data=data(symbol=NEWLINE_TEXT)),
    "a_number_where_a_symbol_belongs": card(bot_data=data(symbol=42)),
    "nothing_where_a_symbol_belongs": card(bot_data=data(symbol=None)),
    "an_empty_bot_id": card(bot_data=data(bot_id="")),
    "a_two_hundred_character_bot_id": card(bot_data=data(bot_id=LONG_TEXT)),
    "a_unicode_bot_id": card(bot_data=data(bot_id=UNICODE_TEXT)),
    "a_newline_in_the_bot_id": card(bot_data=data(bot_id=NEWLINE_TEXT)),
    "a_mode_nobody_declares": card(bot_data=data(mode="grid")),
    "an_empty_mode": card(bot_data=data(mode="")),
    "theme_nebula": card(theme_key="nebula"),
    "theme_matrix": card(theme_key="matrix"),
    "theme_ocean": card(theme_key="ocean"),
    "a_theme_that_names_nothing": card(theme_key="starfield"),
    "a_theme_in_wrong_capitals": card(theme_key="QUANTUM"),
    "a_number_where_a_theme_belongs": card(theme_key=42),
    "nothing_where_a_theme_belongs": card(theme_key=None),
    # Every card below refuses part way through the paint.
    "a_phase_at_infinity": card(phase=math.inf),
    "a_phase_at_minus_infinity": card(phase=-math.inf),
    "an_idle_bot_at_a_phase_of_infinity": card(
        phase=math.inf, bot_data=data(state="idle")
    ),
    "a_ring_at_infinity": card(trade_pulses=[math.inf]),
    "a_ring_at_not_a_number": card(trade_pulses=[math.nan]),
    "a_speck_with_no_life_at_all": card(particles=[(1.0, 2.0, 1.0, 1.0, 0, 2.0)]),
    "text_where_a_profit_belongs": card(
        bot_data=data(stats=stats(realised_pnl="12.5"))
    ),
    "text_where_a_price_belongs": card(
        bot_data=data(stats=stats(current_price="fifty"))
    ),
    "text_where_a_volume_belongs": card(
        bot_data=data(stats=stats(trade_volume="lots"))
    ),
    "a_number_where_a_bot_id_belongs": card(bot_data=data(bot_id=42)),
    "nothing_where_a_bot_id_belongs": card(bot_data=data(bot_id=None)),
    "a_number_where_a_state_belongs": card(bot_data=data(state=42)),
    "a_number_where_a_mode_belongs": card(bot_data=data(mode=42)),
    "a_list_where_a_state_belongs": card(bot_data=data(state=["running"])),
    "a_list_where_a_theme_belongs": card(theme_key=["quantum"]),
    "a_list_where_the_stats_belong": card(bot_data=data(stats=[1, 2, 3])),
    "a_list_where_the_bot_data_belongs": card(bot_data=[1, 2, 3]),
}

CARD_NAMES = sorted(CARD_SPECS)

# Every card the shipped widget refuses, and the surface with it.
REFUSING_CARDS = (
    "a_list_where_a_state_belongs",
    "a_list_where_a_theme_belongs",
    "a_list_where_the_bot_data_belongs",
    "a_list_where_the_stats_belong",
    "a_number_where_a_bot_id_belongs",
    "a_number_where_a_mode_belongs",
    "a_number_where_a_state_belongs",
    "a_phase_at_infinity",
    "a_phase_at_minus_infinity",
    "a_phase_at_not_a_number",
    "a_ring_at_infinity",
    "a_ring_at_not_a_number",
    "a_speck_with_a_life_of_zero",
    "a_speck_with_no_life_at_all",
    "an_idle_bot_at_a_phase_of_infinity",
    "nothing_where_a_bot_id_belongs",
    "text_where_a_price_belongs",
    "text_where_a_profit_belongs",
    "text_where_a_volume_belongs",
)

THEME = surface.THEME_STEP
DATA = surface.DATA_STEP
ANIMATE = surface.ANIMATE_STEP

STEP_SPECS = {
    "nothing_done": [],
    "one_theme_change": [[THEME, "matrix"]],
    "a_theme_change_to_nothing": [[THEME, "starfield"]],
    "two_theme_changes": [[THEME, "ocean"], [THEME, "nebula"]],
    "first_data": [[DATA, data(), DRAWS[1:]]],
    "data_then_a_trade": [
        [DATA, data(stats=stats(total_trades=7)), DRAWS[1:]],
        [DATA, data(stats=stats(total_trades=8)), DRAWS[1:]],
    ],
    "a_trade_then_a_tick": [
        [DATA, data(stats=stats(total_trades=7)), DRAWS[1:]],
        [DATA, data(stats=stats(total_trades=8)), DRAWS[1:]],
        [ANIMATE, 0.25],
    ],
    "a_trade_then_a_long_wait": [
        [DATA, data(stats=stats(total_trades=8)), DRAWS[1:]],
        [ANIMATE, 4.0],
    ],
    "a_price_move": [
        [DATA, data(stats=stats(current_price=100.0)), DRAWS[1:]],
        [DATA, data(stats=stats(current_price=101.0)), DRAWS[1:]],
    ],
    "a_price_move_to_zero": [
        [DATA, data(stats=stats(current_price=100.0)), DRAWS[1:]],
        [DATA, data(stats=stats(current_price=0)), DRAWS[1:]],
    ],
    "a_price_that_did_not_move": [
        [DATA, data(stats=stats(current_price=100.0)), DRAWS[1:]],
        [DATA, data(stats=stats(current_price=100.0)), DRAWS[1:]],
    ],
    "a_trade_count_that_fell": [
        [DATA, data(stats=stats(total_trades=9)), DRAWS[1:]],
        [DATA, data(stats=stats(total_trades=2)), DRAWS[1:]],
    ],
    "three_ticks_after_a_trade": [
        [DATA, data(stats=stats(total_trades=8)), DRAWS[1:]],
        [ANIMATE, 0.1],
        [ANIMATE, 0.1],
        [ANIMATE, 0.1],
    ],
    "a_tick_of_zero": [[DATA, data(), DRAWS[1:]], [ANIMATE, 0.0]],
    "a_negative_tick": [[DATA, data(), DRAWS[1:]], [ANIMATE, -0.5]],
    "one_billionth_of_a_tick": [[DATA, data(), DRAWS[1:]], [ANIMATE, 1e-9]],
    "a_thousand_million_ticks": [[DATA, data(), DRAWS[1:]], [ANIMATE, 1_000_000_000]],
    "a_theme_change_then_a_trade": [
        [THEME, "ocean"],
        [DATA, data(stats=stats(total_trades=8)), DRAWS[1:]],
    ],
    "a_trade_then_a_theme_change": [
        [DATA, data(stats=stats(total_trades=8)), DRAWS[1:]],
        [THEME, "ocean"],
    ],
    # Every sequence below refuses part way through.
    "a_tick_at_infinity": [[DATA, data(), DRAWS[1:]], [ANIMATE, math.inf]],
    "a_tick_at_not_a_number": [[DATA, data(), DRAWS[1:]], [ANIMATE, math.nan]],
    "text_where_a_tick_belongs": [[DATA, data(), DRAWS[1:]], [ANIMATE, "half"]],
    "a_trade_after_a_theme_that_refuses": [
        [THEME, ["ocean"]],
        [DATA, data(), DRAWS[1:]],
    ],
    "a_second_data_that_refuses": [
        [DATA, data(), DRAWS[1:]],
        [DATA, [1, 2, 3], DRAWS[1:]],
    ],
}

STEP_NAMES = sorted(STEP_SPECS)

REFUSING_STEPS = (
    "a_second_data_that_refuses",
    "a_tick_at_infinity",
    "a_tick_at_not_a_number",
    "a_trade_after_a_theme_that_refuses",
    "text_where_a_tick_belongs",
)


# The three outward edges both sides are driven through


def hide_identifiers(value, field_id, mask="****"):
    """The privacy register with the identifier field switched on."""
    return mask if field_id == surface.MASK_FIELD_ID else str(value)


def show_identifiers(value, field_id, mask="****"):
    """The privacy register with nothing switched on."""
    del field_id, mask
    return str(value)


class ScriptedDraws(random.Random):
    """The operating system's random source, replaced by a written list.

    The shipped card takes its start angle and every speck speed from
    ``secrets.SystemRandom``. That class works each draw out as
    ``low + (high - low) * random()``, so replacing ``random`` alone
    leaves the real arithmetic in place and makes the same card twice.
    """

    def __init__(self, values):
        super().__init__(0)
        self.values = list(values)
        self.taken = []

    def random(self):
        if not self.values:
            raise AssertionError("the card asked for more draws than were written")
        value = self.values.pop(0)
        self.taken.append(value)
        return value


def shipped():
    """The module under conversion."""
    from src.gui.visualizer import bot_node

    return bot_node


# The painter the shipped card draws through


def colour_of(value):
    """One Qt colour as its four numbers."""
    return [value.red(), value.green(), value.blue(), value.alpha()]


def path_of(path):
    """One Qt shape as the list of steps the drawing library keeps."""
    from PySide6.QtGui import QPainterPath

    names = {
        QPainterPath.ElementType.MoveToElement: surface.MOVE_TO_ELEMENT,
        QPainterPath.ElementType.LineToElement: surface.LINE_TO_ELEMENT,
        QPainterPath.ElementType.CurveToElement: surface.CURVE_TO_ELEMENT,
        QPainterPath.ElementType.CurveToDataElement: surface.CURVE_TO_DATA_ELEMENT,
    }
    found = []
    for index in range(path.elementCount()):
        element = path.elementAt(index)
        found.append([names[element.type], element.x, element.y])
    return found


def new_image(size=CARD_SIZE):
    """One empty picture of the size the card is drawn at."""
    from PySide6.QtGui import QImage

    image = QImage(size[0], size[1], QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    return image


def recorder_class(image):
    """A painter that keeps every drawing call and still paints `image`.

    The card builds its own painter, so the painter is the one part
    swapped: everything the card works out reaches this unchanged. A pen
    given as a bare style carries no colour and no width, which is
    recorded as nothing and zero. A pen given as a bare colour is a
    different call and carries its own name.
    """
    from PySide6.QtGui import QBrush, QColor, QPainter, QPen

    class RecordingPainter:
        """Records the drawing calls the card makes and forwards them."""

        Antialiasing = QPainter.RenderHint.Antialiasing

        def __init__(self, _device):
            self.painter = QPainter(image)
            self.calls = []

        def setRenderHint(self, hint):
            self.calls.append([surface.SET_RENDER_HINT, hint.name, int(hint.value)])
            self.painter.setRenderHint(hint)

        def fillRect(self, x, y, width, height, colour):
            self.calls.append(
                [surface.FILL_RECT, [x, y, width, height], colour_of(colour)]
            )
            self.painter.fillRect(x, y, width, height, colour)

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
            elif isinstance(pen, QColor):
                self.calls.append([surface.SET_PEN_COLOR, colour_of(pen)])
            else:
                self.calls.append([surface.SET_PEN, None, 0, pen.name])
            self.painter.setPen(pen)

        def setBrush(self, brush):
            gradient = brush.gradient() if isinstance(brush, QBrush) else None
            if gradient is not None:
                stops = [[stop, colour_of(colour)] for stop, colour in gradient.stops()]
                if gradient.type().name == "RadialGradient":
                    self.calls.append(
                        [
                            surface.SET_RADIAL_BRUSH,
                            [gradient.center().x(), gradient.center().y()],
                            gradient.radius(),
                            stops,
                        ]
                    )
                else:
                    self.calls.append(
                        [
                            surface.SET_LINEAR_BRUSH,
                            [gradient.start().x(), gradient.start().y()],
                            [gradient.finalStop().x(), gradient.finalStop().y()],
                            stops,
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

        def drawPath(self, path):
            self.calls.append([surface.DRAW_PATH, path_of(path)])
            self.painter.drawPath(path)

        def drawEllipse(self, centre, x_radius, y_radius):
            self.calls.append(
                [
                    surface.DRAW_ELLIPSE,
                    [centre.x(), centre.y()],
                    x_radius,
                    y_radius,
                ]
            )
            self.painter.drawEllipse(centre, x_radius, y_radius)

        def drawLine(self, start, end):
            self.calls.append(
                [surface.DRAW_LINE, [start.x(), start.y()], [end.x(), end.y()]]
            )
            self.painter.drawLine(start, end)

        def drawText(self, rect, alignment, text):
            from PySide6.QtCore import Qt

            self.calls.append(
                [
                    surface.DRAW_TEXT,
                    [rect.x(), rect.y(), rect.width(), rect.height()],
                    Qt.AlignmentFlag(alignment).name,
                    text,
                ]
            )
            self.painter.drawText(rect, alignment, text)

        def end(self):
            self.calls.append([surface.END_PAINTER])
            self.painter.end()

    return RecordingPainter


def recording_node_class():
    """A locust card that also keeps the two effects that paint nothing.

    Redrawing and setting the hover text reach no pixel. Neither is
    declared by the shipped card, so recording them here adds nothing
    the class counter could see. The list starts as a value with no
    ``append``, so a build that recorded anything would raise rather
    than lose it.
    """
    node_class = shipped().BotNodeWidget

    class RecordingNode(node_class):
        """The shipped card, keeping the effects that paint no pixel."""

        route = ()

        def __init__(self):
            super().__init__()
            self.route = []

        def update(self, *args):
            self.route.append([surface.UPDATE_CARD])
            return super().update(*args)

        def setToolTip(self, text):
            self.route.append([surface.SET_TOOLTIP, text])
            return super().setToolTip(text)

    return RecordingNode


# Driving the two sides


def old_node(spec, draws=None):
    """The shipped card set up from one card state."""
    from src.gui.visualizer.particle import Particle

    app()
    module = shipped()
    was_rng = module._RNG
    module._RNG = ScriptedDraws(draws if draws is not None else DRAWS)
    try:
        node = recording_node_class()()
    finally:
        rng = module._RNG
        module._RNG = was_rng
    node.setMinimumSize(0, 0)
    node.resize(spec["width_px"], spec["height_px"])
    node._phase = spec["phase"]
    node._trade_pulses = list(spec["trade_pulses"])
    node._particles = [Particle(*row) for row in spec["particles"]]
    node._antenna_drive = spec["antenna_drive"]
    node._bot_data = spec["bot_data"]
    node.route = []
    return node, rng


def old_paint(node, image, mask):
    """Run one paint of the shipped card through the recording painter."""
    module = shipped()
    held = {}
    recorder = recorder_class(image)

    class Catcher(recorder):
        """Keeps the painter the card built so its calls can be read."""

        def __init__(self, device):
            super().__init__(device)
            held["painter"] = self

    was_painter = module.QPainter
    was_mask = module._mask_or
    module.QPainter = Catcher
    module._mask_or = mask
    refusal = None
    try:
        node.paintEvent(None)
    except Exception as exc:
        refusal = type(exc).__name__
    finally:
        module.QPainter = was_painter
        module._mask_or = was_mask
        painter = held.get("painter")
        if painter is not None and painter.painter.isActive():
            painter.painter.end()
    painter = held.get("painter")
    return (painter.calls if painter is not None else []), refusal


def old_trace(spec, steps=(), mask=show_identifiers, image=None):
    """Every value the shipped card can be asked for, as plain data."""
    node, rng = old_node(spec)
    module = shipped()
    was_rng = module._RNG
    module._RNG = rng
    try:
        node.set_theme(spec["theme_key"])
        for step in steps:
            if step[0] == surface.THEME_STEP:
                node.set_theme(step[1])
            elif step[0] == surface.DATA_STEP:
                node.set_bot_data(step[1])
            elif step[0] == surface.ANIMATE_STEP:
                node.animate(step[1])
            else:
                raise ValueError(surface.STEP_REFUSAL.format(kind=step[0]))
    finally:
        module._RNG = was_rng
    drawing, refusal = old_paint(
        node, image if image is not None else new_image(), mask
    )
    return {
        "drawing_calls": drawing,
        "route": [list(one) for one in node.route],
        "tooltip": node.toolTip(),
        "refusal": refusal,
    }


def new_trace(spec, steps=(), mask=show_identifiers):
    """The same values, read from the Qt-free view model."""
    model = new_model(spec)
    model.set_theme(spec["theme_key"])
    model.apply(steps)
    calls = model.paint(mask)
    return {
        "drawing_calls": [list(one) for one in calls],
        "route": [list(one) for one in model.calls],
        "tooltip": model.tooltip or "",
        "refusal": None,
    }


def outcome(work) -> dict:
    """What one side did: the value it answered, or the error it refused with."""
    try:
        return {"outcome": "answered", "value": work()}
    except Exception as exc:
        return {"outcome": "refused", "error": type(exc).__name__}


def old_outcome(spec, steps=(), mask=show_identifiers):
    answered = outcome(lambda: old_trace(spec, steps, mask))
    if answered["outcome"] == "answered" and answered["value"]["refusal"]:
        return {"outcome": "refused", "error": answered["value"]["refusal"]}
    return answered


def new_outcome(spec, steps=(), mask=show_identifiers):
    return outcome(lambda: new_trace(spec, steps, mask))


def partial_old(spec, steps=()):
    """The drawing calls the shipped card made before it refused."""
    answered = outcome(lambda: old_trace(spec, steps))
    if answered["outcome"] == "refused":
        return [], answered["error"]
    return answered["value"]["drawing_calls"], answered["value"]["refusal"]


def new_model(spec):
    """One surface card set up from the same state the shipped card gets."""
    return surface.BotNodeModel(
        spec["width_px"],
        spec["height_px"],
        spec["phase"],
        surface.THEME_FALLBACK_KEY,
        spec["bot_data"],
        spec["trade_pulses"],
        spec["particles"],
        spec["antenna_drive"],
    )


def painted_model(spec, steps=()):
    """One surface card painted, and the name of any refusal it made."""
    model = new_model(spec)
    refusal = None
    try:
        model.set_theme(spec["theme_key"])
        for step in steps:
            model.apply([step])
        model.paint(show_identifiers)
    except Exception as exc:
        refusal = type(exc).__name__
    return model, refusal


def partial_new(spec, steps=()):
    """The drawing calls the surface made before it refused."""
    model, refusal = painted_model(spec, steps)
    return [list(one) for one in model.draw_calls], refusal


# The two sides, value for value and by hash


@pytest.mark.parametrize("name", CARD_NAMES)
def test_the_two_sides_draw_the_same_card(name):
    """A coordinate, colour, width, radius, label or drawing order differs."""
    spec = CARD_SPECS[name]
    old = old_outcome(spec)
    new = new_outcome(spec)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    assert canonical(new["value"]) == canonical(old["value"]), name
    assert digest(new["value"]) == digest(old["value"]), name


@pytest.mark.parametrize("name", CARD_NAMES)
def test_the_two_sides_draw_the_same_card_with_identifiers_hidden(name):
    """The privacy switch hides a different label on one side."""
    spec = CARD_SPECS[name]
    old = old_outcome(spec, mask=hide_identifiers)
    new = new_outcome(spec, mask=hide_identifiers)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    assert canonical(new["value"]) == canonical(old["value"]), name


@pytest.mark.parametrize("name", STEP_NAMES)
def test_the_two_sides_answer_the_same_step_sequence(name):
    """A theme change, a trade or a tick left the two cards different."""
    steps = STEP_SPECS[name]
    spec = CARD_SPECS["happy_running"]
    old = old_outcome(spec, steps)
    new = new_outcome(spec, steps)
    assert new["outcome"] == old["outcome"], (name, old, new)
    if old["outcome"] == "refused":
        assert new["error"] == old["error"], (name, old, new)
        return
    assert canonical(new["value"]) == canonical(old["value"]), name
    assert digest(new["value"]) == digest(old["value"]), name


PARTIAL_CARDS = (
    "a_phase_at_infinity",
    "an_idle_bot_at_a_phase_of_infinity",
    "a_ring_at_infinity",
    "a_speck_with_no_life_at_all",
    "a_number_where_a_state_belongs",
    "a_number_where_a_bot_id_belongs",
    "text_where_a_volume_belongs",
)


@pytest.mark.parametrize("name", PARTIAL_CARDS)
def test_a_card_that_refuses_part_way_leaves_the_same_drawing_behind(name):
    """One side stopped drawing at a different point than the other.

    A refusal part way leaves everything already drawn on the screen.
    Only the list of calls made before the refusal reports that.
    """
    old_calls, old_error = partial_old(CARD_SPECS[name])
    new_calls, new_error = partial_new(CARD_SPECS[name])
    assert old_error is not None, name
    assert new_error == old_error, (name, old_error, new_error)
    assert canonical(new_calls) == canonical(old_calls), name
    assert digest(new_calls) == digest(old_calls), name


def test_the_partial_drawing_check_separates_four_stopping_points():
    """The partial check reports one length whatever the card refused on."""
    whole, whole_error = partial_old(CARD_SPECS["happy_running"])
    early, early_error = partial_old(CARD_SPECS["a_ring_at_infinity"])
    middle, middle_error = partial_old(CARD_SPECS["an_idle_bot_at_a_phase_of_infinity"])
    late, late_error = partial_old(CARD_SPECS["a_number_where_a_bot_id_belongs"])
    assert whole_error is None
    assert early_error == "OverflowError"
    assert middle_error == "ValueError"
    assert late_error == "TypeError"
    assert len(early) == 2, early
    assert len(early) < len(middle) < len(late) < len(whole), (
        len(early),
        len(middle),
        len(late),
        len(whole),
    )
    assert len(whole) == WHOLE_CARD_CALL_TOTAL, len(whole)
    assert early[0] == [surface.SET_RENDER_HINT, surface.RENDER_HINT, 1]
    assert whole[-1] == [surface.END_PAINTER]
    assert late[-1] != [surface.END_PAINTER]


def test_the_hash_tells_two_different_real_cards_apart_in_both_directions():
    """The hash returns one value whatever card it is given.

    Two real bots, one running and one stopped, are driven one through
    each side and then the other way round. A pass means the comparison
    reports a card drawn differently, whichever side drew it.
    """
    running_old = old_trace(CARD_SPECS["happy_running"])
    stopped_new = new_trace(CARD_SPECS["a_stopped_bot"])
    assert digest(running_old) != digest(stopped_new)
    running_new = new_trace(CARD_SPECS["happy_running"])
    stopped_old = old_trace(CARD_SPECS["a_stopped_bot"])
    assert digest(running_new) != digest(stopped_old)
    assert digest(running_old) == digest(running_new)
    assert digest(stopped_old) == digest(stopped_new)
    assert digest(old_trace(CARD_SPECS["happy_running"])) == digest(running_old)
    assert len(digest(running_old)) == 64


@pytest.mark.parametrize(
    "name", ["happy_running", "a_card_of_no_size", "theme_ocean", "no_bot_data_at_all"]
)
def test_the_sample_card_hashes_are_reported(name):
    """The comparison passed on a card trace that carries nothing."""
    value = old_outcome(CARD_SPECS[name])["value"]
    assert isinstance(value, dict)
    assert len(value) == 4, sorted(value)
    assert digest(value) == digest(new_outcome(CARD_SPECS[name])["value"])


def test_the_whole_card_makes_eighty_three_drawing_calls_on_both_sides():
    """A drawing call was added or lost from the card on one side only."""
    old = old_outcome(CARD_SPECS["happy_running"])["value"]["drawing_calls"]
    new = new_outcome(CARD_SPECS["happy_running"])["value"]["drawing_calls"]
    assert len(old) == WHOLE_CARD_CALL_TOTAL, len(old)
    assert len(new) == len(old)
    assert [call[0] for call in old[:2]] == [surface.SET_RENDER_HINT, surface.FILL_RECT]
    assert old[-1] == [surface.END_PAINTER]
    ringed = old_outcome(CARD_SPECS["one_trade_ring"])["value"]["drawing_calls"]
    assert len(ringed) == WHOLE_CARD_CALL_TOTAL + 3, len(ringed)
    specked = old_outcome(CARD_SPECS["five_specks"])["value"]["drawing_calls"]
    assert len(specked) == WHOLE_CARD_CALL_TOTAL + 15, len(specked)


def test_every_drawing_call_name_the_surface_declares_is_made():
    """The surface names a drawing call the card never makes."""
    seen = set()
    for name in CARD_NAMES:
        answered = old_outcome(CARD_SPECS[name])
        if answered["outcome"] != "answered":
            continue
        seen.update(call[0] for call in answered["value"]["drawing_calls"])
    assert seen == set(surface.DRAW_CALL_NAMES), sorted(
        set(surface.DRAW_CALL_NAMES) ^ seen
    )


def test_every_effect_name_the_surface_declares_is_reached():
    """The surface names an effect the card never has."""
    seen = set()
    for name in STEP_NAMES:
        answered = old_outcome(CARD_SPECS["happy_running"], STEP_SPECS[name])
        if answered["outcome"] != "answered":
            continue
        seen.update(call[0] for call in answered["value"]["route"])
    assert seen == set(surface.ROUTE_NAMES), sorted(set(surface.ROUTE_NAMES) ^ seen)


def test_every_paint_branch_the_surface_declares_is_taken():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    refused = 0
    for name in CARD_NAMES:
        model, error = painted_model(CARD_SPECS[name])
        refused += 1 if error else 0
        seen.update(model.paint_branches)
    assert refused == len(REFUSING_CARDS), refused
    assert seen == set(surface.PAINT_BRANCHES), sorted(
        set(surface.PAINT_BRANCHES) ^ seen
    )


# Answers and refusals


def test_both_answers_and_refusals_are_in_the_measured_card_set():
    """Every card was accepted, so no refusal was ever compared."""
    answered = []
    refused = []
    for name in CARD_NAMES:
        old = old_outcome(CARD_SPECS[name])
        (answered if old["outcome"] == "answered" else refused).append(name)
    assert answered, "no card was answered"
    assert refused, "no card was refused"
    assert set(refused) == set(REFUSING_CARDS), sorted(refused)
    assert len(answered) + len(refused) == len(CARD_SPECS)


def test_both_answers_and_refusals_are_in_the_measured_step_set():
    """Every step sequence was accepted, so no refusal was ever compared."""
    refused = [
        name
        for name in STEP_NAMES
        if old_outcome(CARD_SPECS["happy_running"], STEP_SPECS[name])["outcome"]
        == "refused"
    ]
    assert set(refused) == set(REFUSING_STEPS), sorted(refused)


@pytest.mark.parametrize("name", REFUSING_CARDS)
def test_a_refused_card_names_the_same_kind_of_error_on_both_sides(name):
    """One side refused a value the other accepted, or refused differently.

    The kind of error is compared and never its wording: this host runs
    one Python and the build machine another, and the two word the same
    refusal differently.
    """
    old = old_outcome(CARD_SPECS[name])
    new = new_outcome(CARD_SPECS[name])
    assert old["outcome"] == "refused", (name, old)
    assert new["outcome"] == "refused", (name, new)
    assert new["error"] == old["error"], (name, old, new)


def test_the_refusals_cover_every_kind_the_card_can_raise():
    """One kind of refusal was never driven, so its path is unchecked."""
    kinds = {old_outcome(CARD_SPECS[name])["error"] for name in REFUSING_CARDS}
    assert kinds == {
        "TypeError",
        "ValueError",
        "OverflowError",
        "AttributeError",
        "ZeroDivisionError",
    }, sorted(kinds)


def test_the_surface_refuses_a_card_step_of_an_unknown_kind():
    """A step kind no handler answers was run instead of refused."""
    model = surface.BotNodeModel()
    with pytest.raises(ValueError) as reported:
        model.apply([["resize", 4]])
    assert str(reported.value) == surface.STEP_REFUSAL.format(kind="resize")
    model.apply([[surface.ANIMATE_STEP, 0.5]])
    assert model.calls == [[surface.UPDATE_CARD]]


def test_the_surface_refuses_a_trade_with_too_few_draws():
    """A trade with no draws behind it built specks out of nothing."""
    model = surface.BotNodeModel()
    with pytest.raises(ValueError) as reported:
        model.set_bot_data(data(stats=stats(total_trades=1)), [0.5] * 19)
    assert str(reported.value) == surface.DRAW_REFUSAL.format(wanted=20, given=19)
    model.set_bot_data(data(stats=stats(total_trades=1)), [0.5] * 20)
    assert len(model.particles) == surface.PARTICLE_COUNT


def test_a_flag_where_a_profit_belongs_is_read_as_one_dollar():
    """A flag was refused as a number, or read as something other than one."""
    old = old_outcome(CARD_SPECS["profit_as_a_flag"])["value"]["drawing_calls"]
    new = new_outcome(CARD_SPECS["profit_as_a_flag"])["value"]["drawing_calls"]
    written = [call for call in old if call[0] == surface.DRAW_TEXT]
    assert written[1][3] == "$+1.0000", written[1]
    assert canonical(new) == canonical(old)


# The draws the card takes from the operating system


def test_the_card_takes_one_draw_to_start_and_twenty_for_each_trade():
    """The card asked the operating system a different number of times."""
    app()
    module = shipped()
    was = module._RNG
    script = ScriptedDraws(DRAWS)
    module._RNG = script
    try:
        node = module.BotNodeWidget()
        assert script.taken == DRAWS[:1], script.taken
        assert node._phase == surface.start_phase(DRAWS[0])
        node.set_bot_data(data(stats=stats(total_trades=99)))
    finally:
        module._RNG = was
    wanted = 1 + surface.PARTICLE_COUNT * surface.PARTICLE_DRAWS_EACH
    assert len(script.taken) == wanted, script.taken
    node.set_bot_data(data(stats=stats(total_trades=99)))
    assert len(script.taken) == wanted, "a repeat trade count drew again"


def test_the_draw_script_refuses_a_card_that_asks_for_more():
    """The draw script quietly repeats itself when the card asks too often."""
    script = ScriptedDraws([0.5])
    assert script.uniform(0, 10) == 5.0
    with pytest.raises(AssertionError):
        script.uniform(0, 10)


def test_the_two_sides_build_one_speck_from_one_set_of_draws():
    """A speck took a different draw, or took them in a different order."""
    node, rng = old_node(CARD_SPECS["happy_running"])
    module = shipped()
    was = module._RNG
    module._RNG = rng
    try:
        node.set_bot_data(data(stats=stats(total_trades=99)))
    finally:
        module._RNG = was
    mine = surface.spawn_particles(CARD_SIZE[0] / 2, CARD_SIZE[1] / 2, DRAWS[1:21])
    theirs = node._particles
    assert len(mine) == len(theirs) == surface.PARTICLE_COUNT
    for one, other in zip(mine, theirs):
        assert [one.x, one.y, one.vx, one.vy, one.life, one.size] == [
            other.x,
            other.y,
            other.vx,
            other.vy,
            other.life,
            other.size,
        ]
    assert mine[0].vx != mine[1].vx, "every speck took the same draw"


# The enumeration: wiring, signals, classes, methods, timers, bus topics


def parsed(path):
    return ast.parse(Path(path).read_text(encoding="utf-8"))


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def connect_sites(path) -> list:
    """Every ``.connect(`` call in `path`, as signal and target.

    The call is counted, never the name: an import line naming the
    signal type would otherwise read as a wire.
    """
    found = []
    for node in ast.walk(parsed(path)):
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
    found = []
    for node in ast.walk(parsed(path)):
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
    return [
        node
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith("QTimer")
    ]


def bus_sites(path) -> list:
    """Every ``subscribe(`` call in `path`, as the topic it names."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "subscribe"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            found.append(node.args[0].value)
    return sorted(found)


def element_sites(path) -> list:
    """Every screen element `path` builds and keeps, as name and kind.

    An element is a drawing-library object the widget holds on to. A
    local one built and dropped is not kept, so it is not counted.
    """
    found = []
    for node in ast.walk(parsed(path)):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        kind = dotted(node.value.func).split(".")[-1]
        if not (len(kind) > 1 and kind.startswith("Q") and kind[1].isupper()):
            continue
        for target in node.targets:
            if isinstance(target, ast.Attribute) and dotted(target).startswith("self."):
                found.append("%s = %s" % (dotted(target), kind))
    return sorted(found)


def declared(path) -> tuple:
    """Every class and every method `path` declares, by name.

    A class inside a method counts, and so does a method wearing a
    decorator: a read-only value and a factory are both methods. A
    declared signal is an assignment and never a method, so it is left
    out here and enumerated by ``signal_sites``.
    """
    classes: list = []
    methods: list = []

    def visit(node, trail):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                classes.append(".".join(trail + [child.name]))
                visit(child, trail + [child.name])
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if trail and isinstance(node, ast.ClassDef):
                    methods.append(".".join(trail + [child.name]))
                visit(child, trail)
            else:
                visit(child, trail)

    visit(parsed(path), [])
    return sorted(classes), sorted(methods)


SHIPPED_CLASSES = {"BotNodeWidget": "BotNodeModel"}

# The surface holds two classes the shipped file does not: the shape
# builder, which stands in for the drawing library's own, and the speck,
# which lives in a file of its own beside the shipped card.
EXTRA_SURFACE_CLASSES = ("PathBuilder", "NodeParticle")

SHIPPED_METHODS = {
    "BotNodeWidget.__init__": "BotNodeModel.__init__",
    "BotNodeWidget.set_theme": "BotNodeModel.set_theme",
    "BotNodeWidget.set_bot_data": "BotNodeModel.set_bot_data",
    "BotNodeWidget.animate": "BotNodeModel.animate",
    "BotNodeWidget._locust_body_path": "body_parts",
    "BotNodeWidget.paintEvent": "BotNodeModel.paint",
}


def test_every_shipped_class_and_method_has_a_counterpart():
    """The shipped card gained or lost a class or a method."""
    classes, methods = declared(NODE_SOURCE)
    assert classes == sorted(SHIPPED_CLASSES), classes
    assert len(classes) == SHIPPED_CLASS_TOTAL
    assert methods == sorted(SHIPPED_METHODS), methods
    assert len(methods) == SHIPPED_METHOD_TOTAL
    for counterpart in list(SHIPPED_CLASSES.values()) + list(SHIPPED_METHODS.values()):
        holder, _, attribute = counterpart.partition(".")
        target = getattr(surface, holder)
        assert callable(getattr(target, attribute) if attribute else target)


def test_every_surface_class_names_what_it_replaces():
    """The surface grew a class that stands in for nothing."""
    built, _methods = declared(
        REPO_ROOT / "src" / "gui" / "main_tabs" / "bot_node_surface.py"
    )
    assert built == sorted(list(SHIPPED_CLASSES.values()) + list(EXTRA_SURFACE_CLASSES))
    assert len(built) == SURFACE_CLASS_TOTAL
    from src.gui.visualizer import particle

    assert hasattr(particle, "Particle")
    assert surface.NodeParticle is not particle.Particle


def test_the_method_counter_leaves_a_signal_out():
    """The method counter counts a declared signal as a method.

    The shipped card declares none, so the counter is pointed at a
    neighbouring screen that declares three. A signal is callable, and a
    counter that took it for a method would report them there.
    """
    signals = signal_sites(SIGNAL_NEIGHBOUR)
    assert len(signals) == SIGNAL_NEIGHBOUR_TOTAL, signals
    assert "ModeCard.clicked" in signals
    _classes, methods = declared(SIGNAL_NEIGHBOUR)
    assert methods, "the method counter reports nothing"
    for name in signals:
        assert name not in methods, name
    assert "ModeCard.__init__" in methods


def test_the_method_counter_finds_a_factory_and_a_read_only_value():
    """The method counter misses a method that wears a decorator."""
    _classes, methods = declared(PROPERTY_NEIGHBOUR)
    assert "IndicatorVotingPanel.lock_timeframe" in methods
    assert "IndicatorVotingPanel.selected_bot_id" in methods
    assert "IndicatorVotingPanel._reading_fingerprint" in methods


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """The class counter only sees classes declared at the top of a file."""
    classes, _methods = declared(NESTED_CLASS_NEIGHBOUR)
    assert "StockMainWindow._StockLogHandler" in classes
    assert "StockMainWindow" in classes


def test_the_card_connects_nothing_and_the_counter_can_report():
    """The shipped card wires a signal the surface names no action for.

    The shipped card wires none, so the counter is pointed at a
    neighbouring widget that really does wire one.
    """
    sites = connect_sites(NODE_SOURCE)
    assert sites == [], sites
    assert len(sites) == CONNECT_TOTAL
    assert surface.ACTIONS == {}
    assert len(connect_sites(CONNECT_NEIGHBOUR)) >= 1, "the wiring counter is blind"


def test_the_card_declares_no_signal_and_the_counter_can_report():
    """The shipped card declares a signal the surface answers with nothing."""
    assert signal_sites(NODE_SOURCE) == []
    assert len(signal_sites(NODE_SOURCE)) == SIGNAL_TOTAL
    assert surface.SIGNALS == ()
    assert (
        len(signal_sites(SIGNAL_NEIGHBOUR)) == SIGNAL_NEIGHBOUR_TOTAL
    ), "the signal counter is blind"


def test_the_card_holds_no_timer_and_the_counter_can_report():
    """The card runs a timer the surface declares no delay for."""
    assert timer_sites(NODE_SOURCE) == []
    assert len(timer_sites(NODE_SOURCE)) == TIMER_TOTAL
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(timer_sites(TIMER_NEIGHBOUR)) >= 1, "the timer counter is blind"


def test_the_card_subscribes_to_no_bus_topic_and_the_counter_can_report():
    """The card listens on a topic the surface names none of."""
    assert bus_sites(NODE_SOURCE) == []
    assert len(bus_sites(NODE_SOURCE)) == BUS_TOPIC_TOTAL
    assert surface.BUS_TOPICS == ()
    neighbour = bus_sites(BUS_NEIGHBOUR)
    assert len(neighbour) >= 2, "the bus counter is blind"
    assert "wire.created" in neighbour


def test_the_card_keeps_no_screen_element_and_the_counter_can_report():
    """The card holds a screen element the surface declares none of."""
    assert element_sites(NODE_SOURCE) == []
    assert len(element_sites(NODE_SOURCE)) == ELEMENT_TOTAL
    assert surface.SCREEN_ELEMENTS == ()
    neighbour = element_sites(ELEMENT_NEIGHBOUR)
    assert len(neighbour) == ELEMENT_NEIGHBOUR_TOTAL, neighbour
    assert "self._value = QLabel" in neighbour


def test_the_card_starts_no_thread_of_its_own():
    """The card starts a worker that outlives the window that built it."""
    started = [
        dotted(node.func)
        for node in ast.walk(parsed(NODE_SOURCE))
        if isinstance(node, ast.Call) and "Thread" in dotted(node.func)
    ]
    assert started == [], started
    assert timer_sites(NODE_SOURCE) == []
    node, _rng = old_node(CARD_SPECS["happy_running"])
    assert node.findChildren(object) == [], node.findChildren(object)


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart reader accepts a name that is on neither side."""
    assert "BotNodeWidget.paintEvent" in SHIPPED_METHODS
    assert not hasattr(surface, "InventedModel")
    with pytest.raises(AttributeError):
        getattr(surface, "InventedModel")


# The completeness check


PAYLOAD_KEYS = {
    "ABDOMEN_BASE_ALPHA": "abdomen.base_alpha",
    "ABDOMEN_BASE_SWING": "abdomen.base_swing",
    "ABDOMEN_GRADIENT_BOTTOM_U": "abdomen.gradient_bottom_u",
    "ABDOMEN_GRADIENT_TOP_U": "abdomen.gradient_top_u",
    "ABDOMEN_PEN_WIDTH_PX": "abdomen.pen_width_px",
    "ABDOMEN_TIP_ALPHA": "abdomen.tip_alpha",
    "ABDOMEN_TIP_SWING": "abdomen.tip_swing",
    "ACTIONS": "actions",
    "ALIGN_CENTER": "alignment.name",
    "ALIGN_CENTER_VALUE": "alignment.value",
    "ANTENNA_AMBIENT_OFFSET": "antenna.ambient_offset",
    "ANTENNA_AMBIENT_PHASE_RATE": "antenna.ambient_phase_rate",
    "ANTENNA_BASE_X_U": "antenna.base_x_u",
    "ANTENNA_BASE_Y_U": "antenna.base_y_u",
    "ANTENNA_BEND_X_U": "antenna.bend_x_u",
    "ANTENNA_BEND_Y_U": "antenna.bend_y_u",
    "ANTENNA_DECAY_PER_S": "movement.antenna_decay_per_s",
    "ANTENNA_DRIVEN_OFFSET": "antenna.driven_offset",
    "ANTENNA_DRIVEN_PHASE_RATE": "antenna.driven_phase_rate",
    "ANTENNA_DRIVE_FLOOR": "movement.antenna_drive_floor",
    "ANTENNA_DRIVE_START": "movement.antenna_drive_start",
    "ANTENNA_PEN_WIDTH_PX": "antenna.pen_width_px",
    "ANTENNA_SIGNS": "antenna.signs",
    "ANTENNA_SWAY_AMBIENT": "antenna.sway_ambient",
    "ANTENNA_SWAY_DRIVEN": "antenna.sway_driven",
    "ANTENNA_TIP_ALPHA": "antenna.tip_alpha",
    "ANTENNA_TIP_RADIUS_PX": "antenna.tip_radius_px",
    "ANTENNA_TIP_X_U": "antenna.tip_x_u",
    "ANTENNA_TIP_Y_U": "antenna.tip_y_u",
    "BODY_PART_NAMES": "path.part_names",
    "BOT_ID_COLOR": "labels.bot_id_color",
    "BOT_ID_FONT_SIZE_PT": "font.bot_id_size_pt",
    "BOT_ID_KEY": "data_keys.bot_id",
    "BOT_ID_LABEL_CHARS": "privacy.label_chars",
    "BOT_ID_RECT_BOTTOM_PX": "labels.bot_id_bottom_px",
    "BOT_ID_RECT_HEIGHT_PX": "labels.bot_id_height_px",
    "BOT_ID_TOOLTIP_CHARS": "privacy.tooltip_chars",
    "BRACKET_ALPHA": "brackets.alpha",
    "BRACKET_FAR_INSET_PX": "brackets.far_inset_px",
    "BRACKET_LENGTH_PX": "brackets.length_px",
    "BRACKET_NEAR_INSET_PX": "brackets.near_inset_px",
    "BRACKET_PEN_WIDTH_PX": "brackets.pen_width_px",
    "BUS_TOPICS": "bus_topics",
    "CIRCUIT_ALPHA": "circuit.alpha",
    "CIRCUIT_DOT_RADIUS_PX": "circuit.dot_radius_px",
    "CIRCUIT_DOT_X_U": "circuit.dot_x_u",
    "CIRCUIT_DOT_Y_U": "circuit.dot_y_u",
    "CIRCUIT_LINE_HALF_U": "circuit.line_half_u",
    "CIRCUIT_LINE_Y_U": "circuit.line_y_u",
    "CIRCUIT_PEN_WIDTH_PX": "circuit.pen_width_px",
    "CLOSE_SNAP_LIMIT": "path.close_snap_limit",
    "CUBIC_CONTROL_WEIGHT": "path.cubic_control_weight",
    "CUBIC_DIVISOR": "path.cubic_divisor",
    "DEFAULT_MODE": "defaults.mode",
    "DEFAULT_STATE": "states.default",
    "DEFAULT_SYMBOL": "defaults.symbol",
    "DRAW_CALL_NAMES": "draw_call_names",
    "DRAW_REFUSAL": "formats.draw_refusal",
    "EYE_CENTRE_U": "eye.centre_u",
    "EYE_PHASE_RATE": "eye.phase_rate",
    "EYE_RADIUS_U": "eye.radius_u",
    "EYE_SWING_U": "eye.swing_u",
    "FONT_FAMILY": "font.family",
    "FONT_WEIGHT_BOLD": "font.bold",
    "FONT_WEIGHT_BOLD_VALUE": "font.bold_value",
    "FONT_WEIGHT_NORMAL": "font.normal",
    "FONT_WEIGHT_NORMAL_VALUE": "font.normal_value",
    "FORE_LEG_U": "legs.fore_u",
    "FUZZY_NULL_LIMIT": "path.fuzzy_null_limit",
    "FUZZY_SCALE": "path.fuzzy_scale",
    "GLOW_ALPHA": "glow.alpha",
    "GLOW_EDGE_COLOR": "glow.edge_color",
    "GLOW_RADIUS_U": "glow.radius_u",
    "GRADIENT_CENTRE_STOP": "glow.centre_stop",
    "GRADIENT_EDGE_STOP": "glow.edge_stop",
    "HEAD_FILLS": "theme.head_fills",
    "HEAD_PEN_WIDTH_PX": "head.pen_width_px",
    "HIND_LEG_PEN_WIDTH_PX": "legs.hind_pen_width_px",
    "HIND_LEG_U": "legs.hind_u",
    "IDLE_GREY": "states.idle_grey",
    "IRIS_ALPHA": "eye.iris_alpha",
    "IRIS_PEN_WIDTH_PX": "eye.iris_pen_width_px",
    "IRIS_RADIUS_RATIO": "eye.iris_radius_ratio",
    "LEG_COLORS": "states.leg_colors",
    "LEG_FALLBACK_COLORS": "states.leg_fallback_colors",
    "LEG_PEN_WIDTH_PX": "legs.pen_width_px",
    "LEG_SIGNS": "legs.signs",
    "MASK_FIELD_ID": "privacy.field_id",
    "METHOD": "method",
    "MID_LEG_U": "legs.mid_u",
    "MILLION": "tooltip.million",
    "MODE_KEY": "data_keys.mode",
    "NO_BOT_ID": "defaults.bot_id",
    "NO_BRUSH": "pens.no_brush",
    "PEN_CAP_STYLE": "pens.cap_style",
    "PEN_HALF_WIDTH_RATIO": "pens.half_width_ratio",
    "NO_PEN_STYLE": "pens.no_pen_style",
    "NO_PEN_WIDTH_PX": "pens.no_pen_width_px",
    "OPAQUE_ALPHA": "theme.opaque_alpha",
    "PAINT_BRANCHES": "paint_branch_names",
    "PARTICLE_ALPHA_FLOOR": "particle.alpha_floor",
    "PARTICLE_ALPHA_SCALE": "particle.alpha_scale",
    "PARTICLE_COUNT": "particle.count",
    "PARTICLE_DRAWS_EACH": "particle.draws_each",
    "PARTICLE_LIFE_FLOOR": "particle.life_floor",
    "PARTICLE_LIFE_MAX": "particle.life_max",
    "PARTICLE_LIFE_MIN": "particle.life_min",
    "PARTICLE_SIZE_MAX": "particle.size_max",
    "PARTICLE_SIZE_MIN": "particle.size_min",
    "PARTICLE_VELOCITY_MAX": "particle.velocity_max",
    "PARTICLE_VELOCITY_MIN": "particle.velocity_min",
    "PATH_ELEMENT_NAMES": "path.element_names",
    "PATH_ORIGIN": "path.origin",
    "PHASE_MAX": "movement.phase_max",
    "PHASE_MIN": "movement.phase_min",
    "PHASE_RATE_PER_S": "movement.phase_rate_per_s",
    "PNL_FLOOR_USD": "abdomen.floor_usd",
    "PNL_FONT_SIZE_PT": "font.pnl_size_pt",
    "PNL_KEY": "data_keys.pnl",
    "PNL_LOG_DIVISOR": "abdomen.log_divisor",
    "PNL_MAGNITUDE_MAX": "abdomen.magnitude_max",
    "PNL_RECT_BOTTOM_PX": "labels.pnl_bottom_px",
    "PNL_RECT_HEIGHT_PX": "labels.pnl_height_px",
    "PRICE_DASH": "tooltip.price_dash",
    "PRICE_FLOOR_USD": "tooltip.price_floor_usd",
    "PRICE_KEY": "data_keys.price",
    "PULSE_DECAY_PER_S": "movement.pulse_decay_per_s",
    "PULSE_FLOOR": "movement.pulse_floor",
    "PULSE_RING_ALPHA": "pulse_ring.alpha",
    "PULSE_RING_BASE_U": "pulse_ring.base_u",
    "PULSE_RING_GROWTH_PX": "pulse_ring.growth_px",
    "PULSE_RING_WIDTH_PX": "pulse_ring.width_px",
    "PULSE_START": "movement.pulse_start",
    "RECT_LEFT_PX": "labels.left_px",
    "RENDER_HINT": "render_hint.name",
    "RENDER_HINT_VALUE": "render_hint.value",
    "ROUTE_NAMES": "route_names",
    "SCALE_DIVISOR": "scale_divisor",
    "SCREEN_ELEMENTS": "screen_elements",
    "SEGMENT_COLOR": "segments.color",
    "SEGMENT_COUNT": "segments.count",
    "SEGMENT_PEN_WIDTH_PX": "segments.pen_width_px",
    "SEGMENT_STEP_U": "segments.step_u",
    "SEGMENT_TAPER_STEP_U": "segments.taper_step_u",
    "SEGMENT_TAPER_U": "segments.taper_u",
    "SEGMENT_TOP_U": "segments.top_u",
    "SIGNALS": "signals",
    "SOLID_PEN_STYLE": "pens.solid_style",
    "STATE_COLORS": "states.colors",
    "STATE_KEY": "data_keys.state",
    "STATE_NAMES": "states.names",
    "STATS_KEY": "data_keys.stats",
    "STEP_KINDS": "step_kinds",
    "STEP_REFUSAL": "formats.step_refusal",
    "STOPPED_GREY": "states.stopped_grey",
    "SYMBOL_FONT_SIZE_PT": "font.symbol_size_pt",
    "SYMBOL_KEY": "data_keys.symbol",
    "SYMBOL_RECT_HEIGHT_PX": "labels.symbol_height_px",
    "SYMBOL_RECT_TOP_PX": "labels.symbol_top_px",
    "THEME_COLORS": "theme.table",
    "THEME_COLOR_NAMES": "theme.color_names",
    "THEME_FALLBACK_KEY": "theme.fallback_key",
    "THEME_KEYS": "theme.keys",
    "THORAX_CENTRE_ALPHA": "thorax.centre_alpha",
    "THORAX_EDGE_ALPHA": "thorax.edge_alpha",
    "THORAX_GRADIENT_CENTRE_U": "thorax.gradient_centre_u",
    "THORAX_GRADIENT_RADIUS_U": "thorax.gradient_radius_u",
    "THORAX_PEN_WIDTH_PX": "thorax.pen_width_px",
    "THOUSAND": "tooltip.thousand",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TOOLTIP_BOT_MASK": "privacy.tooltip_mask",
    "TOOLTIP_FORMAT": "tooltip.format",
    "TRADES_KEY": "data_keys.trades",
    "VOLUME_KEY": "data_keys.volume",
    "VOLUME_MILLIONS_FORMAT": "tooltip.millions_format",
    "VOLUME_PLAIN_FORMAT": "tooltip.plain_format",
    "VOLUME_THOUSANDS_FORMAT": "tooltip.thousands_format",
    "WING_ALPHA_BASE": "wing.alpha_base",
    "WING_ALPHA_SWING": "wing.alpha_swing",
    "WING_HALF_OPEN": "wing.half_open",
    "WING_LIFT_U": "wing.lift_u",
    "WING_MAX_OPEN": "wing.max_open",
    "WING_PEN_ALPHA": "wing.pen_alpha",
    "WING_PEN_STYLE": "wing.pen_style",
    "WING_PEN_WIDTH_PX": "wing.pen_width_px",
    "WING_PULSE_BUMP": "wing.pulse_bump",
    "WING_RUNNING_BASE": "wing.running_base",
    "WING_RUNNING_PHASE_RATE": "wing.running_phase_rate",
    "WING_RUNNING_SWING": "wing.running_swing",
    "WING_SPREAD_OPEN_U": "wing.spread_open_u",
    "WING_SPREAD_U": "wing.spread_u",
    "WING_TIGHT_OPEN": "wing.tight_open",
    "WING_TIGHT_STATES": "wing.tight_states",
    "WING_TIP_RATIO": "wing.tip_ratio",
    "ZERO_STAT": "defaults.stat",
}

# Values the payload carries inside a list rather than at a path of
# their own: the drawing call names, the effect names, the branch names,
# the step kinds, the four curve step kinds and the six state names.
LIST_MEMBERS = {
    "ANIMATE_STEP": "step_kinds",
    "CURVE_TO_DATA_ELEMENT": "path.element_names",
    "CURVE_TO_ELEMENT": "path.element_names",
    "DATA_STEP": "step_kinds",
    "DRAW_ELLIPSE": "draw_call_names",
    "DRAW_LINE": "draw_call_names",
    "DRAW_PATH": "draw_call_names",
    "DRAW_TEXT": "draw_call_names",
    "END_PAINTER": "draw_call_names",
    "FILL_RECT": "draw_call_names",
    "LINE_TO_ELEMENT": "path.element_names",
    "MOVE_TO_ELEMENT": "path.element_names",
    "PAINT_NOTHING": "paint_branch_names",
    "PAINT_WHOLE": "paint_branch_names",
    "PARTICLE_DRAWN": "paint_branch_names",
    "PNL_NEGATIVE": "paint_branch_names",
    "PNL_POSITIVE": "paint_branch_names",
    "PRICE_HIDDEN": "paint_branch_names",
    "PRICE_SHOWN": "paint_branch_names",
    "PULSE_RING": "paint_branch_names",
    "SET_BRUSH": "draw_call_names",
    "SET_FONT": "draw_call_names",
    "SET_LINEAR_BRUSH": "draw_call_names",
    "SET_PEN": "draw_call_names",
    "SET_PEN_COLOR": "draw_call_names",
    "SET_RADIAL_BRUSH": "draw_call_names",
    "SET_RENDER_HINT": "draw_call_names",
    "SET_TOOLTIP": "route_names",
    "STATE_COOLDOWN": "states.names",
    "STATE_ERROR": "states.names",
    "STATE_IDLE": "states.names",
    "STATE_KNOWN": "paint_branch_names",
    "STATE_PAUSED": "states.names",
    "STATE_RUNNING": "states.names",
    "STATE_STOPPED": "states.names",
    "STATE_UNKNOWN": "paint_branch_names",
    "THEME_STEP": "step_kinds",
    "UPDATE_CARD": "route_names",
    "VOLUME_MILLIONS": "paint_branch_names",
    "VOLUME_PLAIN": "paint_branch_names",
    "VOLUME_THOUSANDS": "paint_branch_names",
    "WING_HALF": "paint_branch_names",
    "WING_PULSED": "paint_branch_names",
    "WING_RUNNING": "paint_branch_names",
    "WING_TIGHT": "paint_branch_names",
}

# The two values no payload key carries, each with the check that
# covers it. MIN_WIDTH_PX and MIN_HEIGHT_PX reach the payload as the
# smallest size the card may be shrunk to.
NOT_IN_THE_SNAPSHOT = {
    "MIN_WIDTH_PX": "test_the_smallest_card_size_is_read_off_both_sides",
    "MIN_HEIGHT_PX": "test_the_smallest_card_size_is_read_off_both_sides",
    "NODE_MODEL": "test_the_bridge_resets_the_card_state_on_request",
    "Call": "test_every_drawing_call_name_the_surface_declares_is_made",
}

STATE_ONLY_KEYS = {"drawing_calls", "paint_branches", "calls", "card"}


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
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


CONSTANT_TOTAL = 244
PAYLOAD_KEY_TOTAL = 44


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read.

    A comparison that reads some of the values passes whether the rest
    match or not. Every value is accounted for here: a payload path, a
    member of a list the payload carries, or one named with the check
    that covers it.
    """
    payload = surface.build_view_model(surface.BotNodeModel(*CARD_SIZE))
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            assert at_path(payload, PAYLOAD_KEYS[name]) == as_lists(value), name
        elif name in LIST_MEMBERS:
            assert value in at_path(payload, LIST_MEMBERS[name]), name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(PAYLOAD_KEYS) == 196
    assert len(LIST_MEMBERS) == 45
    assert len(NOT_IN_THE_SNAPSHOT) == 4


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.BotNodeModel(*CARD_SIZE))
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {path.split(".")[0] for path in LIST_MEMBERS.values()}
    answered |= {"minimum_size_px", "tooltip"}
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    assert len(payload) == PAYLOAD_KEY_TOTAL
    for key in STATE_ONLY_KEYS:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing."""
    payload = surface.build_view_model(surface.BotNodeModel(*CARD_SIZE))
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in LIST_MEMBERS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "GLOW_ALPHA" in surface_constants()
    assert "THEME_COLORS" in surface_constants()
    assert "body_parts" not in surface_constants()
    assert "BotNodeModel" not in surface_constants()
    assert "view_model" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "glow.invented")
    with pytest.raises(IndexError):
        at_path(payload, "path.origin.9")


# The surface carries its own values


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
    comparison above would be one side read twice. The card background
    the shipped card looks up is moved and the surface must not move
    with it. The comparison must then name that one value.
    """
    from PySide6.QtGui import QColor

    app()
    spec = CARD_SPECS["happy_running"]
    before = old_trace(spec)["drawing_calls"]
    restored_theme_table["quantum"]["bg"] = QColor(9, 9, 9)
    moved = old_trace(spec)["drawing_calls"]
    assert moved[1] == [surface.FILL_RECT, [0, 0, 112, 98], [9, 9, 9, 255]]
    assert before[1] == [surface.FILL_RECT, [0, 0, 112, 98], [10, 15, 25, 255]]
    mine = new_trace(spec)["drawing_calls"]
    assert mine[1] == before[1]
    apart = [
        index
        for index, (one, other) in enumerate(zip(mine, moved))
        if canonical(one) != canonical(other)
    ]
    assert 1 in apart, apart
    assert canonical(mine) == canonical(before)


def draws_nothing(*_args, **_named):
    """A body builder that returns a shape with no steps in it."""
    return {name: [] for name in surface.BODY_PART_NAMES}


def test_the_surface_does_not_follow_a_card_that_draws_no_body(monkeypatch):
    """The surface asked the shipped card to work out its geometry."""
    app()
    spec = CARD_SPECS["happy_running"]
    mine = new_trace(spec)["drawing_calls"]
    monkeypatch.setattr(
        shipped().BotNodeWidget, "_locust_body_path", draws_nothing, raising=True
    )
    stripped = old_outcome(spec)
    assert stripped["outcome"] == "refused", stripped
    again = new_trace(spec)["drawing_calls"]
    assert canonical(again) == canonical(mine)
    monkeypatch.undo()
    assert len(old_trace(spec)["drawing_calls"]) == len(mine)


def test_the_body_builder_guard_names_a_method_the_card_really_declares():
    """The guard above is pointed at a name the shipped card does not carry."""
    assert hasattr(shipped().BotNodeWidget, "_locust_body_path")
    with pytest.raises(AttributeError):
        object.__getattribute__(shipped().BotNodeWidget, "_invented_body_path")


def test_the_shipped_card_writes_to_no_shared_table(restored_theme_table):
    """The shipped card changes a table other tests read.

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
    for name in ("happy_running", "theme_matrix", "a_stopped_bot"):
        old_trace(CARD_SPECS[name])
    assert snapshot() == before
    restored_theme_table["quantum"]["bg"] = QColor(9, 9, 9)
    assert snapshot() != before, "the shared-table check cannot report a change"


def test_the_surface_keeps_no_state_between_two_cards():
    """A card built after another carried the first one's values."""
    first = surface.BotNodeModel(*CARD_SIZE, bot_data=data())
    first.apply([[ANIMATE, 0.5], [THEME, "matrix"]])
    first.paint(show_identifiers)
    second = surface.BotNodeModel(*CARD_SIZE, bot_data=data())
    assert second.calls == []
    assert second.draw_calls == []
    assert second.tooltip is None
    assert second.theme_key == surface.THEME_FALLBACK_KEY
    fresh = surface.build_view_model(second)
    again = surface.build_view_model(surface.BotNodeModel(*CARD_SIZE, bot_data=data()))
    assert canonical(fresh) == canonical(again)


def test_the_shipped_card_leaves_the_random_source_it_was_given():
    """A driven card left the operating system source swapped out."""
    module = shipped()
    was = module._RNG
    old_node(CARD_SPECS["happy_running"])
    assert module._RNG is was


def test_the_shipped_card_leaves_the_painter_and_the_privacy_answer_it_was_given():
    """A driven card left the painter or the privacy answer swapped out.

    Both are held by the whole process. A run that left either swapped
    would decide what a later file in the build machine's parallel run
    measures.
    """
    module = shipped()
    painter = module.QPainter
    privacy = module._mask_or
    old_trace(CARD_SPECS["happy_running"], mask=hide_identifiers)
    assert module.QPainter is painter
    assert module._mask_or is privacy
    old_outcome(CARD_SPECS["a_number_where_a_state_belongs"])
    assert module.QPainter is painter, "a refused card left the painter swapped"
    assert module._mask_or is privacy, "a refused card left the privacy answer swapped"


def test_the_swap_the_restore_undoes_really_happens():
    """The restore above passes because nothing was ever swapped.

    The painter the card builds is the recording one during a paint and
    the shipped one after it, so the restore has something real to undo.
    """
    module = shipped()
    shipped_painter = module.QPainter
    held = {}
    node, _rng = old_node(CARD_SPECS["happy_running"])
    was_paint = node.paintEvent

    def watched(event):
        held["during"] = module.QPainter
        return was_paint(event)

    node.paintEvent = watched
    old_paint(node, new_image(), show_identifiers)
    assert held["during"] is not shipped_painter
    assert module.QPainter is shipped_painter


def test_the_card_the_bridge_keeps_really_moves():
    """The card the bridge keeps never changes, so restoring it proves nothing."""
    was = surface.NODE_MODEL
    bridge_answer({"card": BRIDGE_CARD})
    assert surface.NODE_MODEL is not was
    assert surface.NODE_MODEL is surface.held_model()


# The shape builder against the drawing library


def qt_path(steps):
    """One Qt shape built from a list of named steps."""
    from PySide6.QtGui import QPainterPath

    app()
    path = QPainterPath()
    for step in steps:
        if step[0] == "move":
            path.moveTo(step[1], step[2])
        elif step[0] == "line":
            path.lineTo(step[1], step[2])
        elif step[0] == "quad":
            path.quadTo(step[1], step[2], step[3], step[4])
        else:
            path.closeSubpath()
    return path_of(path)


def mine_path(steps):
    """The same shape built by the surface."""
    path = surface.PathBuilder()
    for step in steps:
        if step[0] == "move":
            path.move_to(step[1], step[2])
        elif step[0] == "line":
            path.line_to(step[1], step[2])
        elif step[0] == "quad":
            path.quad_to(step[1], step[2], step[3], step[4])
        else:
            path.close()
    return path.parts()


PATH_STEPS = {
    "a_plain_triangle": [
        ("move", 1.0, 2.0),
        ("line", 9.0, 2.0),
        ("line", 5.0, 9.0),
        ("close",),
    ],
    "a_curve_and_a_close": [
        ("move", 1.0, 2.0),
        ("quad", 3.0, 4.0, 5.0, 6.0),
        ("close",),
    ],
    "a_step_that_goes_nowhere": [
        ("move", 1.0, 2.0),
        ("line", 1.0, 2.0),
        ("line", 5.0, 6.0),
    ],
    "a_step_one_ten_thousand_billionth_away": [
        ("move", 0.0, 0.0),
        ("line", 1e-13, 0.0),
    ],
    "a_curve_that_goes_nowhere": [("move", 1.0, 2.0), ("quad", 1.0, 2.0, 1.0, 2.0)],
    "a_curve_back_to_the_start": [
        ("move", 1.0, 2.0),
        ("quad", 3.0, 4.0, 1.0, 2.0),
        ("close",),
    ],
    "two_lifts_in_a_row": [("move", 1.0, 2.0), ("move", 3.0, 4.0)],
    "a_lift_after_a_step": [
        ("move", 1.0, 2.0),
        ("line", 5.0, 6.0),
        ("move", 1.0, 2.0),
    ],
    "a_close_with_one_point": [("move", 1.0, 2.0), ("close",)],
    "a_step_after_a_close": [
        ("move", 1.0, 2.0),
        ("line", 5.0, 6.0),
        ("close",),
        ("line", 7.0, 8.0),
    ],
    "a_lift_to_infinity": [("move", math.inf, 2.0), ("line", 3.0, 4.0)],
    "a_step_to_infinity": [("move", 1.0, 2.0), ("line", math.inf, 4.0)],
    "a_step_to_not_a_number": [("move", 1.0, 2.0), ("line", math.nan, 4.0)],
    "a_curve_bending_through_infinity": [
        ("move", 1.0, 2.0),
        ("quad", math.inf, 4.0, 5.0, 6.0),
    ],
    "a_curve_ending_at_not_a_number": [
        ("move", 1.0, 2.0),
        ("quad", 3.0, 4.0, math.nan, 6.0),
    ],
    "every_point_at_zero": [
        ("move", 0.0, 0.0),
        ("line", 0.0, 0.0),
        ("line", 0.0, 0.0),
        ("close",),
    ],
    "a_step_from_minus_zero": [("move", -0.0, -0.0), ("line", 0.0, 0.0)],
    "nothing_at_all": [],
    "a_close_with_nothing_before_it": [("close",)],
    "a_step_with_no_lift_before_it": [("line", 3.0, 4.0)],
    "a_close_a_hair_away_from_the_start": [
        ("move", 1.0, 2.0),
        ("line", 5.0, 6.0),
        ("line", 1.0 + 1e-11, 2.0),
        ("close",),
    ],
}


@pytest.mark.parametrize("name", sorted(PATH_STEPS))
def test_the_shape_builder_keeps_the_steps_the_library_keeps(name):
    """The surface built a shape the drawing library would not build."""
    steps = PATH_STEPS[name]
    assert canonical(mine_path(steps)) == canonical(qt_path(steps)), name


def test_the_shape_comparison_reports_two_different_shapes():
    """The shape comparison passes whatever shape it is handed."""
    assert canonical(qt_path(PATH_STEPS["a_plain_triangle"])) != canonical(
        qt_path(PATH_STEPS["a_curve_and_a_close"])
    )
    assert len(qt_path(PATH_STEPS["a_plain_triangle"])) == 4
    assert len(qt_path(PATH_STEPS["a_step_that_goes_nowhere"])) == 2


@pytest.mark.parametrize("name", sorted(surface.BODY_PART_NAMES))
def test_each_body_shape_matches_the_one_the_library_builds(name):
    """A body shape the surface builds differs from the shipped one."""
    app()
    node, _rng = old_node(CARD_SPECS["happy_running"])
    theirs = node._locust_body_path(56.0, 49.0, 1.8846153846153846, 0.35)
    mine = surface.body_parts(56.0, 49.0, 1.8846153846153846, 0.35)
    assert canonical(mine[name]) == canonical(path_of(theirs[name])), name
    assert mine[name], name


# The colours


def canonical_colour(value):
    """One colour as the six-digit value the screen reports."""
    from PySide6.QtGui import QColor

    return QColor(value[0], value[1], value[2]).name().lower()


def test_every_declared_card_colour_matches_the_shipped_table():
    """A card colour drifted from the table the shipped card reads."""
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


def test_every_declared_head_fill_matches_the_step_the_library_takes():
    """The head fill drifted from the lighter step the library works out."""
    from PySide6.QtGui import QColor
    from src.gui.visualizer.themes import THEMES

    app()
    for key in surface.THEME_KEYS:
        theirs = QColor(THEMES[key]["bg"]).lighter(120)
        assert list(surface.HEAD_FILLS[key]) == [
            theirs.red(),
            theirs.green(),
            theirs.blue(),
            theirs.alpha(),
        ], key


def test_every_declared_leg_colour_matches_the_step_the_library_takes():
    """A leg colour drifted from the darker step the library works out."""
    from PySide6.QtGui import QColor
    from src.gui.visualizer.themes import THEMES

    app()
    for key in surface.THEME_KEYS:
        for state in surface.STATE_NAMES:
            theirs = QColor(*surface.STATE_COLORS[key][state]).darker(120)
            assert list(surface.LEG_COLORS[key][state]) == [
                theirs.red(),
                theirs.green(),
                theirs.blue(),
                theirs.alpha(),
            ], (key, state)
        fallback = QColor(THEMES[key]["text"]).darker(120)
        assert list(surface.LEG_FALLBACK_COLORS[key]) == [
            fallback.red(),
            fallback.green(),
            fallback.blue(),
            fallback.alpha(),
        ], key


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
    assert len(set(written.values())) >= 24, sorted(set(written.values()))


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


EQUAL_CHANNEL_COLOURS = (
    "IDLE_GREY",
    "STOPPED_GREY",
    "SEGMENT_COLOR",
    "GLOW_EDGE_COLOR",
)


@pytest.mark.parametrize("name", EQUAL_CHANNEL_COLOURS)
def test_an_equal_channel_colour_is_compared_as_numbers(name):
    """A colour with three equal channels was left to a colour check.

    Grey reads the same with any two channels swapped, so no colour
    check can report a swap in it. Each is compared as its four numbers
    inside the drawing call that carries it, which the side-by-side
    comparison covers.
    """
    app()
    value = getattr(surface, name)
    assert value[0] == value[1] == value[2], value
    where = {
        "IDLE_GREY": "an_idle_bot",
        "STOPPED_GREY": "a_stopped_bot",
        "SEGMENT_COLOR": "happy_running",
        "GLOW_EDGE_COLOR": "happy_running",
    }[name]
    old = old_trace(CARD_SPECS[where])["drawing_calls"]
    assert holds(old, list(value)), (name, value)
    assert not holds(old, [1, 2, 3, 4]), "the colour search finds anything"


def test_the_alpha_of_every_layer_is_the_one_declared():
    """A see-through level drifted from the one the surface declares."""
    old = old_trace(CARD_SPECS["one_trade_ring"])["drawing_calls"]
    radial = [call for call in old if call[0] == surface.SET_RADIAL_BRUSH]
    linear = [call for call in old if call[0] == surface.SET_LINEAR_BRUSH]
    assert old[2][1][3] == int(surface.PULSE_RING_ALPHA * 0.6)
    assert radial[0][3][0][1][3] == surface.GLOW_ALPHA
    assert radial[0][3][1][1] == list(surface.GLOW_EDGE_COLOR)
    assert radial[1][3][0][1][3] == surface.THORAX_CENTRE_ALPHA
    assert radial[1][3][1][1][3] == surface.THORAX_EDGE_ALPHA
    assert linear[0][3][0][1][3] == surface.ABDOMEN_BASE_ALPHA + int(
        surface.ABDOMEN_BASE_SWING * surface.pnl_magnitude(12.5)
    )


# The pictures


def model_payload(name, steps=(), mask=show_identifiers):
    """The view model of one card, stamped."""
    model = new_model(CARD_SPECS[name])
    model.set_theme(CARD_SPECS[name]["theme_key"])
    return sealed(surface.build_view_model(model, steps or None, mask))


def image_painted_by_the_card(name, steps=(), mask=show_identifiers):
    """The picture the shipped Qt card paints."""
    app()
    image = new_image()
    old_trace(CARD_SPECS[name], steps, mask, image)
    return image


def image_painted_by_the_model(payload):
    """A picture drawn only from the view model, never from the card.

    A payload the caller changed after it came off the surface is
    refused.
    """
    payload = unaltered(payload)
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import (
        QBrush,
        QColor,
        QFont,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
        QRadialGradient,
    )

    app()
    image = new_image()
    painter = QPainter(image)

    def colour(value):
        return QColor(value[0], value[1], value[2], value[3])

    def path_from(elements):
        path = QPainterPath()
        index = 0
        while index < len(elements):
            step = elements[index]
            if step[0] == surface.MOVE_TO_ELEMENT:
                path.moveTo(QPointF(step[1], step[2]))
                index += 1
            elif step[0] == surface.LINE_TO_ELEMENT:
                path.lineTo(QPointF(step[1], step[2]))
                index += 1
            else:
                one, two, three = elements[index : index + 3]
                path.cubicTo(
                    QPointF(one[1], one[2]),
                    QPointF(two[1], two[2]),
                    QPointF(three[1], three[2]),
                )
                index += 3
        return path

    for call in payload["drawing_calls"]:
        name = call[0]
        if name == surface.SET_RENDER_HINT:
            painter.setRenderHint(getattr(QPainter.RenderHint, call[1]))
        elif name == surface.FILL_RECT:
            painter.fillRect(
                call[1][0], call[1][1], call[1][2], call[1][3], colour(call[2])
            )
        elif name == surface.SET_PEN:
            if call[1] is None:
                painter.setPen(getattr(Qt.PenStyle, call[3]))
            else:
                painter.setPen(
                    QPen(colour(call[1]), call[2], getattr(Qt.PenStyle, call[3]))
                )
        elif name == surface.SET_PEN_COLOR:
            painter.setPen(colour(call[1]))
        elif name == surface.SET_BRUSH:
            if isinstance(call[1], str):
                painter.setBrush(getattr(Qt.BrushStyle, call[1]))
            else:
                painter.setBrush(QBrush(colour(call[1])))
        elif name == surface.SET_RADIAL_BRUSH:
            wash = QRadialGradient(call[1][0], call[1][1], call[2])
            for stop, value in call[3]:
                wash.setColorAt(stop, colour(value))
            painter.setBrush(QBrush(wash))
        elif name == surface.SET_LINEAR_BRUSH:
            wash = QLinearGradient(call[1][0], call[1][1], call[2][0], call[2][1])
            for stop, value in call[3]:
                wash.setColorAt(stop, colour(value))
            painter.setBrush(QBrush(wash))
        elif name == surface.SET_FONT:
            painter.setFont(QFont(call[1], call[2], getattr(QFont.Weight, call[3])))
        elif name == surface.DRAW_PATH:
            painter.drawPath(path_from(call[1]))
        elif name == surface.DRAW_ELLIPSE:
            painter.drawEllipse(QPointF(call[1][0], call[1][1]), call[2], call[3])
        elif name == surface.DRAW_LINE:
            painter.drawLine(
                QPointF(call[1][0], call[1][1]), QPointF(call[2][0], call[2][1])
            )
        elif name == surface.DRAW_TEXT:
            painter.drawText(
                QRectF(*call[1]), getattr(Qt.AlignmentFlag, call[2]), call[3]
            )
        elif name == surface.END_PAINTER:
            painter.end()
    if painter.isActive():
        painter.end()
    return image


PICTURE_CARDS = [
    "happy_running",
    "an_idle_bot",
    "theme_matrix",
    "one_trade_ring",
    "five_specks",
    "a_loss",
    "a_two_hundred_character_symbol",
    "the_feelers_swaying",
]


@pytest.mark.parametrize("name", PICTURE_CARDS)
def test_the_two_sides_paint_one_card(name):
    """The surface painted a different card than the shipped one."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=image_painted_by_the_card(name),
        new_side=image_painted_by_the_model(model_payload(name)),
        note=note,
    )


@pytest.mark.parametrize("name", ["a_trade_then_a_tick", "one_theme_change"])
def test_the_two_sides_paint_one_card_after_a_step_sequence(name):
    """A trade or a theme change left the two sides painting different cards."""
    app()
    steps = STEP_SPECS[name]
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    assert_pictures_match(
        old_side=image_painted_by_the_card("happy_running", steps),
        new_side=image_painted_by_the_model(model_payload("happy_running", steps)),
        note=note,
    )


def test_the_two_sides_paint_one_card_with_identifiers_hidden():
    """The privacy switch painted a different label on one side."""
    app()
    assert_pictures_match(
        old_side=image_painted_by_the_card("happy_running", mask=hide_identifiers),
        new_side=image_painted_by_the_model(
            model_payload("happy_running", mask=hide_identifiers)
        ),
        note="identifiers hidden, %s"
        % ("real fonts" if has_real_fonts() else "no fonts"),
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    The running card off the shipped class against the stopped card off
    the surface. Both are real product cards and they carry different
    state colours, so a pass proves the comparison reports a card
    painted differently.
    """
    app()
    assert CARD_SPECS["happy_running"] != CARD_SPECS["a_stopped_bot"]
    assert_pictures_differ(
        old_side=image_painted_by_the_card("happy_running"),
        new_side=image_painted_by_the_model(model_payload("a_stopped_bot")),
        note="the running card against the stopped card",
    )


def colours_in(image) -> set:
    """Every colour the render painted, sampled every second pixel."""
    from PySide6.QtGui import QColor

    seen = set()
    for x in range(0, image.width(), 2):
        for y in range(0, image.height(), 2):
            seen.add(QColor(image.pixelColor(x, y)).name())
    return seen


@pytest.mark.parametrize("name", PICTURE_CARDS)
def test_the_painted_card_shows_more_than_one_colour(name):
    """The two sides matched because the card painted one flat colour."""
    app()
    for image in (
        image_painted_by_the_card(name),
        image_painted_by_the_model(model_payload(name)),
    ):
        assert image.width() == CARD_SIZE[0]
        assert image.height() == CARD_SIZE[1]
        seen = colours_in(image)
        assert len(seen) > 1, "%s painted one colour, so no change could show" % name


def test_an_unfed_card_paints_nothing_and_is_compared_by_value():
    """The empty card paints something, so its picture could report.

    A card holding no bot values draws nothing at all, so its picture is
    one flat colour and no picture check on it could ever fail. It is
    compared value for value instead.
    """
    app()
    image = image_painted_by_the_card("no_bot_data_at_all")
    assert len(colours_in(image)) == 1, "the empty card painted more than one colour"
    old = old_trace(CARD_SPECS["no_bot_data_at_all"])
    new = new_trace(CARD_SPECS["no_bot_data_at_all"])
    assert old["drawing_calls"] == []
    assert canonical(new) == canonical(old)


def test_neither_side_sets_a_skin_and_the_card_paints_its_own_ground():
    """A skin the host chose reached the picture instead of the card.

    Neither side sets a style sheet, and the card covers every pixel
    with its own background before anything else. So the platform's own
    look reaches no pixel of either picture.
    """
    app()
    node, _rng = old_node(CARD_SPECS["happy_running"])
    assert node.styleSheet() == ""
    old = old_trace(CARD_SPECS["happy_running"])["drawing_calls"]
    assert old[1] == [
        surface.FILL_RECT,
        [0, 0, CARD_SIZE[0], CARD_SIZE[1]],
        list(surface.THEME_COLORS["quantum"]["bg"]),
    ]
    image = image_painted_by_the_card("happy_running")
    ground = image.pixelColor(0, CARD_SIZE[1] // 2).name()
    assert ground == canonical_colour(surface.THEME_COLORS["quantum"]["bg"]), ground


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload("happy_running")
    payload["drawing_calls"][1][2] = [255, 0, 0, 255]
    with pytest.raises(AssertionError) as reported:
        image_painted_by_the_model(payload)
    assert "altered after it came off" in str(reported.value)
    with pytest.raises(AssertionError):
        image_painted_by_the_model(
            surface.build_view_model(surface.BotNodeModel(*CARD_SIZE, bot_data=data()))
        )


@skip_unless_no_fonts
def test_two_labels_of_equal_length_measure_the_same_width():
    """The host reports no fonts and the glyphs still have their own widths."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    assert narrow == wide, (narrow, wide)


@skip_unless_real_fonts
def test_two_labels_of_equal_length_measure_different_widths():
    """The host reports fonts and every glyph still has one width."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    assert narrow != wide, (narrow, wide)


# What a picture cannot see, read off both sides instead


def test_the_hover_text_is_read_off_both_sides():
    """The hover text reaches no pixel, so it must be read off both sides."""
    app()
    for name in ("happy_running", "zero_price", "a_thousand_volume", "zero_volume"):
        old = old_trace(CARD_SPECS[name])
        new = new_trace(CARD_SPECS[name])
        assert new["tooltip"] == old["tooltip"], name
        assert old["tooltip"], name
    plain = old_trace(CARD_SPECS["happy_running"])["tooltip"]
    assert plain.splitlines()[0] == "BTC-USD"
    assert "State: RUNNING" in plain
    assert "Volume: $2.5M" in plain
    hidden = old_trace(CARD_SPECS["happy_running"], mask=hide_identifiers)["tooltip"]
    assert hidden.splitlines()[0] == "****"
    assert hidden.splitlines()[-1] == "Bot: ********"
    assert "abcdef" not in hidden


def test_the_hover_text_hides_no_more_of_the_bot_id_than_the_label():
    """The hover text gave back an identifier the label was hiding."""
    app()
    hidden = old_trace(CARD_SPECS["happy_running"], mask=hide_identifiers)
    written = [call for call in hidden["drawing_calls"] if call[0] == surface.DRAW_TEXT]
    assert written[0][3] == "****"
    assert written[2][3] == "****"
    assert "abcdef0123456789" not in hidden["tooltip"]
    assert (
        new_trace(CARD_SPECS["happy_running"], mask=hide_identifiers)["tooltip"]
        == hidden["tooltip"]
    )


def test_the_redraw_the_card_asks_for_is_read_off_both_sides():
    """A redraw reaches no pixel, so it must be read off both sides."""
    app()
    for name in ("one_theme_change", "a_tick_of_zero", "first_data"):
        old = old_trace(CARD_SPECS["happy_running"], STEP_SPECS[name])
        new = new_trace(CARD_SPECS["happy_running"], STEP_SPECS[name])
        assert new["route"] == old["route"], name
    quiet = old_trace(CARD_SPECS["happy_running"], STEP_SPECS["nothing_done"])
    busy = old_trace(CARD_SPECS["happy_running"], STEP_SPECS["two_theme_changes"])
    assert quiet["route"].count([surface.UPDATE_CARD]) == 1
    assert busy["route"].count([surface.UPDATE_CARD]) == 3


def test_the_smallest_card_size_is_read_off_both_sides():
    """The card may be shrunk smaller on one side than the other."""
    app()
    module = shipped()
    was = module._RNG
    module._RNG = ScriptedDraws(DRAWS)
    try:
        node = module.BotNodeWidget()
    finally:
        module._RNG = was
    assert [node.minimumWidth(), node.minimumHeight()] == [
        surface.MIN_WIDTH_PX,
        surface.MIN_HEIGHT_PX,
    ]
    payload = surface.build_view_model(surface.BotNodeModel())
    assert payload["minimum_size_px"] == [surface.MIN_WIDTH_PX, surface.MIN_HEIGHT_PX]
    node.resize(1, 1)
    assert [node.width(), node.height()] == [
        surface.MIN_WIDTH_PX,
        surface.MIN_HEIGHT_PX,
    ]


def test_the_recording_card_records_nothing_while_it_is_built():
    """The recording card lost an effect the shipped one had at build time."""
    node, _rng = old_node(CARD_SPECS["happy_running"])
    assert node.route == []
    node.update()
    assert node.route == [[surface.UPDATE_CARD]]
    assert recording_node_class().route == ()


# The bridge


@pytest.fixture(autouse=True)
def restored_bridge_card():
    """Put the card the bridge keeps back after a test replaces it.

    The surface keeps one card at module level so the bridge can hold
    state between calls. Every test in this file gets its own, or the
    build machine's parallel run orders them differently and a result
    depends on what ran before it.
    """
    was = surface.NODE_MODEL
    yield
    surface.NODE_MODEL = was


BRIDGE_CARD = {
    "width_px": 112,
    "height_px": 98,
    "phase": 0.7,
    "theme_key": "quantum",
    "bot_data": {
        "bot_id": "abcdef0123456789",
        "symbol": "BTC-USD",
        "state": "running",
        "mode": "scrumming",
        "stats": {
            "realised_pnl": 12.5,
            "total_trades": 7,
            "current_price": 50000.0,
            "trade_volume": 2500000.0,
        },
    },
}


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        registry,
    )


def test_the_bridge_registers_the_bot_node_method():
    """The renderer cannot reach the locust card over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "bot_node.state"
    answer = bridge_answer({"card": BRIDGE_CARD})
    assert answer["ok"] is True
    result = answer["result"]
    assert result["drawing_calls"][0] == ["set_render_hint", "Antialiasing", 1]
    assert result["drawing_calls"][-1] == ["end"]
    assert result["paint_branches"][-1] == "paint.whole"
    assert result["card"]["tooltip"].splitlines()[0] == "BTC-USD"


def test_the_bridge_hides_the_fields_it_is_told_to_hide():
    """The privacy switch the renderer sent reached no label."""
    plain = bridge_answer({"card": BRIDGE_CARD})["result"]
    hidden = bridge_answer({"card": BRIDGE_CARD, "hidden": [surface.MASK_FIELD_ID]})[
        "result"
    ]
    written = [call for call in hidden["drawing_calls"] if call[0] == surface.DRAW_TEXT]
    assert written[0][3] == "****"
    assert "abcdef" not in hidden["card"]["tooltip"]
    assert "BTC-USD" in plain["card"]["tooltip"]


def test_the_bridge_resets_the_card_state_on_request():
    """The card state the bridge keeps was never cleared."""
    filled = bridge_answer({"card": BRIDGE_CARD, "steps": [[THEME, "matrix"]]})[
        "result"
    ]
    assert filled["theme"]["key"] == "matrix"
    kept = bridge_answer({})["result"]
    assert kept["theme"]["key"] == "matrix"
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["theme"]["key"] == "quantum"
    assert cleared["drawing_calls"] == []
    assert cleared["paint_branches"] == ["paint.nothing"]


def test_the_bridge_reports_a_value_the_card_refuses():
    """A value the card refuses ended the session instead of answering."""
    broken = dict(BRIDGE_CARD)
    broken["bot_data"] = dict(BRIDGE_CARD["bot_data"], state=42)
    answer = bridge_answer({"card": broken})
    assert answer["ok"] is False
    assert answer["error"]["type"] == "AttributeError"


def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer({"card": BRIDGE_CARD, "steps": [[ANIMATE, 0.25]]})
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["draw_call_names"] == list(surface.DRAW_CALL_NAMES)
    assert encoded["result"]["card"]["phase"] == 0.7 + 0.25 * 1.5


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'bot_node.state', 'params':"
    " {'card': {'width_px': 112, 'height_px': 98, 'bot_data':"
    " {'bot_id': 'abc', 'symbol': 'BTC', 'stats': {'realised_pnl': 1.0}}}}}),"
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
    """Reaching the locust card pulled Qt into the backend."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["paint_branches"][-1] == "paint.whole"
    assert result["drawing_calls"][-1] == ["end"]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_its_kept_card_only_when_asked():
    """The surface built its kept card while it was being imported."""
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys;"
            "from src.gui.main_tabs import bot_node_surface as s;"
            "print(s.NODE_MODEL is None, 'PySide6' in sys.modules,"
            " s.held_model() is not None, s.NODE_MODEL is not None)",
        ],
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    assert done.stdout.decode().strip().splitlines()[-1] == "True False True True"
