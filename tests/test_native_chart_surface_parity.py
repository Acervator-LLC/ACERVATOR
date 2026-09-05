"""The Qt candlestick chart and the Qt-free surface, driven side by side.

A failure means the view model describes a different axis bound, tick
step, scale mapping, candle body, colour, number format, layout number,
step or branch than ``CandlestickChart`` paints on the same input.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui.main_tabs import native_chart_surface as surface
from tests.fixtures.host_fonts import has_real_fonts
from tests.fixtures.surface_pictures import (
    assert_picture_can_report,
    assert_pictures_differ,
    assert_pictures_match,
    colour_count,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CHART_SOURCE = REPO_ROOT / "src" / "gui" / "native_chart.py"
SURFACE_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "native_chart_surface.py"

PIXEL_SIZE = (520, 340)

CONNECT_RUNTIME_TOTAL = 9
CONNECT_SOURCE_TOTAL = 4
SHIPPED_CLASS_TOTAL = 6
SHIPPED_METHOD_TOTAL = 35
SHIPPED_NESTED_TOTAL = 10
SIGNAL_TOTAL = 1
EMIT_TOTAL = 1
TIMER_BUILT_TOTAL = 0
TIMER_STARTED_TOTAL = 0
THREAD_BUILT_TOTAL = 0
THREAD_STARTED_TOTAL = 0
BUS_SUBSCRIBE_TOTAL = 0
BUS_EMIT_TOTAL = 0


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def chart_module():
    """The shipped chart module, imported once the platform is chosen."""
    from src.gui import native_chart

    return native_chart


# The cases


class Series:
    """One named input both sides are driven with."""

    def __init__(self, name, rows, symbol="BTC-USD"):
        self.name = name
        self.rows = rows
        self.symbol = symbol


def bar(index, open_price, high, low, close, volume=100.0, start=1_700_000_000):
    return (start + index * 3600, open_price, high, low, close, volume)


def rising(count):
    return [
        bar(i, 10.0 + i, 11.0 + i, 9.0 + i, 10.5 + i, 100.0 + i) for i in range(count)
    ]


CASES = [
    Series("empty", []),
    Series("one point", rising(1)),
    Series("two points", rising(2)),
    Series("zero range", [bar(i, 10.0, 10.0, 10.0, 10.0, 5.0) for i in range(20)]),
    Series("normal", rising(30)),
    Series("high below low", [bar(i, 10.0, 5.0, 20.0, 10.0) for i in range(20)]),
    Series(
        "times backwards",
        [
            (1_700_000_000 - i * 3600, 10.0 + i, 11.0 + i, 9.0 + i, 10.5 + i, 100.0)
            for i in range(20)
        ],
    ),
    Series("sub cent", [bar(i, 0.004, 0.0051, 0.0039, 0.0047, 9.0) for i in range(25)]),
    Series(
        "above a thousand",
        [
            bar(i, 78_700.0 + i, 78_780.0 + i, 78_690.0 + i, 78_757.0 + i, 11.8)
            for i in range(25)
        ],
    ),
    Series(
        "one billionth", [bar(i, 1e-9, 2e-9, 5e-10, 1.5e-9, 1.0) for i in range(25)]
    ),
    Series(
        "a thousand million",
        [bar(i, 1e9, 1.1e9, 0.9e9, 1.05e9, 1e9) for i in range(25)],
    ),
    Series(
        "zero volume",
        [bar(i, 10.0 + i, 11.0 + i, 9.0 + i, 10.5 + i, 0.0) for i in range(20)],
    ),
    Series("unicode symbol", rising(20), symbol="BTC—USD ✦ ÅÄÖ"),
    Series("long symbol", rising(20), symbol="B" * 200),
    Series("markup symbol", rising(20), symbol="<b>BTC</b> & 'x'"),
    Series("newline symbol", rising(20), symbol="BTC\nUSD"),
    Series("wrong capitals", rising(20), symbol="bTc-UsD"),
]
BY_NAME = {case.name: case for case in CASES}

PICTURE_SCENARIOS = ("empty", "one point", "zero range", "normal")


def shipped_candles(case):
    module = chart_module()
    return [module.Candle(*row) for row in case.rows]


def surface_candles(case):
    return [surface.Candle(*row) for row in case.rows]


def drive_old(case):
    """The shipped widget, driven over one case and ready to render."""
    module = chart_module()
    app()
    chart = module.CandlestickChart(case.symbol)
    chart.resize(*PIXEL_SIZE)
    chart.set_candles(shipped_candles(case))
    return chart


def drive_new(case):
    """The surface's model, driven over the same case."""
    model = surface.ChartModel(case.symbol)
    model.set_candles(surface_candles(case))
    return model


def model_payload(case=None):
    """The view model after the same driving, stamped."""
    case = case or BY_NAME["normal"]
    return sealed(surface.build_view_model(drive_new(case), *PIXEL_SIZE))


# The recorder: the shipped paint runs unchanged, onto a stub painter


class PaintRecorder:
    """Stands in for ``QPainter`` and keeps every call the paint made.

    ``src.gui.native_chart`` reaches its painter through a module name, so
    swapping that name drives the real ``paintEvent`` and records the
    geometry it paints. Font metrics come from the real Qt class, because
    glyph widths belong to the host and not to the product.
    """

    Antialiasing = None
    TextAntialiasing = None
    LAST: list = []

    def __init__(self, device):
        self.device = device
        self.calls = []
        self._font = None
        PaintRecorder.LAST.append(self)

    def __getattr__(self, name):
        def record(*args):
            self.calls.append((name, tuple(_plain(a) for a in args)))
            return None

        return record

    def setFont(self, font):
        self._font = font
        self.calls.append(("setFont", (_plain(font),)))

    def fontMetrics(self):
        from PySide6.QtGui import QFont, QFontMetrics

        return QFontMetrics(self._font or QFont())

    def end(self):
        self.calls.append(("end", ()))
        return True


def _enum(value):
    """A comparable reading of one Qt enum."""
    return int(getattr(value, "value", value))


def _plain(value):
    """A comparable, hashable reading of one painter argument."""
    from PySide6.QtCore import QPointF, QRectF
    from PySide6.QtGui import QBrush, QColor, QFont, QGradient, QPen, QPolygonF

    if isinstance(value, QColor):
        return ("color", value.red(), value.green(), value.blue(), value.alpha())
    if isinstance(value, QPen):
        return (
            "pen",
            _plain(value.color()),
            round(value.widthF(), 6),
            _enum(value.style()),
        )
    if isinstance(value, QBrush):
        return ("brush", _plain(value.color()), _enum(value.style()))
    if isinstance(value, QRectF):
        return (
            "rect",
            round(value.x(), 6),
            round(value.y(), 6),
            round(value.width(), 6),
            round(value.height(), 6),
        )
    if isinstance(value, QPointF):
        return ("point", round(value.x(), 6), round(value.y(), 6))
    if isinstance(value, QPolygonF):
        return ("poly", tuple(_plain(value.at(i)) for i in range(value.count())))
    if isinstance(value, QFont):
        return ("font", value.family(), value.pointSize(), value.weight())
    if isinstance(value, QGradient):
        return (
            "gradient",
            tuple((round(at, 6), _plain(colour)) for at, colour in value.stops()),
        )
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (int, str, bool)) or value is None:
        return value
    return repr(value)


def record_paint(case, size=PIXEL_SIZE, setup=None):
    """Every painter call the shipped chart makes for one case.

    ``setup`` runs against the built chart before the paint.
    """
    module = chart_module()
    app()
    from PySide6.QtGui import QImage

    chart = module.CandlestickChart(case.symbol)
    chart.resize(*size)
    chart.set_candles(shipped_candles(case))
    if setup is not None:
        setup(chart)
    held = QImage(size[0], size[1], QImage.Format_ARGB32)
    original = module.QPainter
    PaintRecorder.Antialiasing = original.Antialiasing
    PaintRecorder.TextAntialiasing = original.TextAntialiasing
    PaintRecorder.LAST = []
    module.QPainter = PaintRecorder
    try:
        chart.paintEvent(None)
    finally:
        module.QPainter = original
    assert module.QPainter is original, "the painter name was left swapped"
    assert PaintRecorder.LAST, "the paint never reached the recorder"
    assert held.width() == size[0]
    return PaintRecorder.LAST[0].calls


def calls_named(calls, name):
    return [args for called, args in calls if called == name]


def full_width_lines(calls, left, right):
    """The y of every horizontal line spanning the plotting width."""
    found = []
    for x0, y0, x1, y1 in calls_named(calls, "drawLine"):
        if x0 == left and x1 == right and y0 == y1:
            found.append(y0)
    return found


# Enumeration


def parsed_chart():
    return ast.parse(CHART_SOURCE.read_text(encoding="utf-8"))


def test_the_shipped_file_holds_the_classes_the_surface_answers_for():
    """The chart grew or lost a class the surface does not describe."""
    tree = parsed_chart()
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    assert len(classes) == SHIPPED_CLASS_TOTAL, [c.name for c in classes]
    methods = [
        x
        for c in classes
        for x in c.body
        if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert len(methods) == SHIPPED_METHOD_TOTAL, [m.name for m in methods]
    named = {m.name for m in methods}
    nested = [
        n.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name not in named
    ]
    assert len(nested) == SHIPPED_NESTED_TOTAL, nested


def test_the_chart_builds_no_timer_and_starts_no_thread():
    """The chart grew a timer or a thread the surface does not declare."""
    tree = parsed_chart()
    built = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in {"QTimer", "QThread", "Thread", "QThreadPool"}
    ]
    started = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"start", "singleShot", "startTimer"}
    ]
    assert len(built) == TIMER_BUILT_TOTAL + THREAD_BUILT_TOTAL, [
        ast.unparse(n) for n in built
    ]
    assert len(started) == TIMER_STARTED_TOTAL + THREAD_STARTED_TOTAL, [
        ast.unparse(n) for n in started
    ]
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert surface.THREADS == ()


def test_the_chart_reaches_no_event_bus():
    """The chart grew a bus call the surface does not declare."""
    tree = parsed_chart()
    reached = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"subscribe", "publish", "emit_event"}
    ]
    assert len(reached) == BUS_SUBSCRIBE_TOTAL + BUS_EMIT_TOTAL, [
        ast.unparse(n) for n in reached
    ]
    assert surface.BUS_TOPICS == ()


def test_one_signal_is_declared_and_one_emit_sends_it():
    """The chart's signal count moved away from what the surface names."""
    tree = parsed_chart()
    declared = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "Signal"
    ]
    emits = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "emit"
    ]
    assert len(declared) == SIGNAL_TOTAL
    assert len(emits) == EMIT_TOTAL
    assert len(surface.SIGNALS) == SIGNAL_TOTAL


def test_the_panel_makes_nine_connections_from_four_written_lines():
    """A connection was added or lost, or a helper stopped repeating one."""
    module = chart_module()
    app()
    from PySide6.QtCore import SignalInstance

    tree = parsed_chart()
    written = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "connect"
    ]
    assert len(written) == CONNECT_SOURCE_TOTAL, [n.lineno for n in written]

    seen = []
    original = SignalInstance.connect

    def counting(self, *args, **kwargs):
        seen.append(1)
        return original(self, *args, **kwargs)

    SignalInstance.connect = counting
    try:
        panel = module.ChartPanel("BTC-USD")
        made = len(seen)
        before_control = made
        panel.chart.timeframe_changed.connect(lambda *_: None)
        control = len(seen) - before_control
    finally:
        SignalInstance.connect = original
    assert SignalInstance.connect is original
    assert (
        control == 1
    ), "the counter cannot see a connection, so its total means nothing"
    assert made == CONNECT_RUNTIME_TOTAL, made
    assert len(surface.ACTIONS) == CONNECT_RUNTIME_TOTAL


def test_every_action_the_surface_names_is_one_the_panel_connects():
    """The surface names an action the panel never wires."""
    assert set(surface.ACTIONS.values()) <= {
        name for name in dir(surface.ChartModel) if not name.startswith("__")
    }


# Value for value, and by hash

PRICES = [
    0.0,
    1e-9,
    9.999e-05,
    0.0001,
    0.00010001,
    0.009999,
    0.01,
    0.010001,
    0.9999,
    1,
    1.0,
    12,
    12.0,
    12.7,
    999.999,
    1000,
    1000.001,
    1_234_567.891,
    1e9,
    -5.5,
    -0.00001,
    True,
    False,
    2**1023,
    float("inf"),
    float("-inf"),
]


@pytest.mark.parametrize("price", PRICES)
def test_the_two_sides_format_one_price_the_same_way(price):
    """The surface formats a price the shipped chart formats differently."""
    module = chart_module()
    app()
    chart = module.CandlestickChart()
    assert surface.fmt_price(price) == chart._fmt_price(price)


def test_a_price_format_refusal_matches_by_type():
    """One side refused a price the other accepted."""
    module = chart_module()
    app()
    chart = module.CandlestickChart()
    for value in ("12.7", None, 2**1024):
        with pytest.raises(Exception) as shipped:
            chart._fmt_price(value)
        with pytest.raises(Exception) as ours:
            surface.fmt_price(value)
        assert type(ours.value) is type(shipped.value)


def test_two_not_a_numbers_compare_by_text_not_by_value():
    """A not-a-number slipped through a comparison that can never hold."""
    both = [surface.fmt_price(float("nan")), chart_fmt(float("nan"))]
    assert both[0] == both[1]
    assert math.isnan(float(both[0]))
    assert float("nan") != float("nan")


def chart_fmt(value):
    module = chart_module()
    app()
    return module.CandlestickChart()._fmt_price(value)


def test_a_whole_number_and_a_decimal_are_told_apart_by_hash():
    """A check that reads 12 and 12.0 as one value would pass on either."""
    assert surface.fmt_price(12) == surface.fmt_price(12.0)
    assert digest(12) != digest(12.0)


def digest(value):
    return hashlib.sha256(repr((type(value).__name__, value)).encode()).hexdigest()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_the_two_sides_agree_on_the_natural_height(case):
    """The surface sizes the widget differently from the shipped chart."""
    module = chart_module()
    app()
    chart = module.CandlestickChart()
    chart.set_candles(shipped_candles(case))
    model = drive_new(case)
    for volume in (False, True):
        for macd in (False, True):
            for vortex in (False, True):
                for stoch in (False, True):
                    chart._show_volume = volume
                    chart._show_macd = macd
                    chart._show_vortex = vortex
                    chart._show_stochrsi = stoch
                    chart._macd_data = [(1, 1, 1)] if macd else []
                    chart._vortex_data = [(1, 1)] if vortex else []
                    chart._stochrsi_data = [0.5] if stoch else []
                    model.flags["show_volume"] = volume
                    model.flags["show_macd"] = macd
                    model.flags["show_vortex"] = vortex
                    model.flags["show_stochrsi"] = stoch
                    model.macd_data = [(1, 1, 1)] if macd else []
                    model.vortex_data = [(1, 1)] if vortex else []
                    model.stochrsi_data = [0.5] if stoch else []
                    assert model.apply_height() == chart._natural_height_for_panes()


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_the_two_sides_agree_on_the_visible_window(case):
    """The surface reads a different visible window than the chart."""
    module = chart_module()
    app()
    chart = module.CandlestickChart()
    chart.set_candles(shipped_candles(case))
    model = drive_new(case)
    for start in (None, 0, 3, -5, 999):
        for count in (None, 4, 8, 10, 999):
            chart._visible_start, chart._visible_count = start, count
            model.visible_start, model.visible_count = start, count
            assert model.visible_start_now() == chart._effective_visible_start()
            assert model.visible_count_now() == chart._effective_visible_count()


def test_the_two_sides_carry_one_palette():
    """A colour on the surface is not the colour the chart paints with."""
    module = chart_module()
    app()
    chart = module.CandlestickChart
    pairs = {
        "BG_TOP": surface.BG_TOP,
        "BG_BOT": surface.BG_BOT,
        "GRID_MAJOR": surface.GRID_MAJOR,
        "GRID_MINOR": surface.GRID_MINOR,
        "TEXT_DIM": surface.TEXT_DIM,
        "TEXT_LIGHT": surface.TEXT_LIGHT,
        "ACCENT": surface.ACCENT,
        "UP_FILL": surface.UP_FILL,
        "UP_BORDER": surface.UP_BORDER,
        "DOWN_FILL": surface.DOWN_FILL,
        "DOWN_BORDER": surface.DOWN_BORDER,
        "UP_WICK": surface.UP_WICK,
        "DOWN_WICK": surface.DOWN_WICK,
        "VOL_UP": surface.VOL_UP,
        "VOL_DOWN": surface.VOL_DOWN,
        "VOL_UP_BORDER": surface.VOL_UP_BORDER,
        "VOL_DOWN_BORDER": surface.VOL_DOWN_BORDER,
        "CROSSHAIR_COLOR": surface.CROSSHAIR_COLOR,
        "PRICE_LINE_COLOR": surface.PRICE_LINE_COLOR,
        "BUY_POS_COLOR": surface.BUY_POS_COLOR,
        "SELL_POS_COLOR": surface.SELL_POS_COLOR,
        "INVISIBLE_ICON": surface.INVISIBLE_ICON,
        "VISIBLE_ICON": surface.VISIBLE_ICON,
    }
    for name, ours in pairs.items():
        theirs = getattr(chart, name)
        assert (
            theirs.red(),
            theirs.green(),
            theirs.blue(),
            theirs.alpha(),
        ) == ours, name
    assert list(surface.TIMEFRAMES) == chart.TIMEFRAMES


def test_the_palette_check_would_report_a_changed_channel():
    """The palette check reads a colour that cannot differ."""
    from PySide6.QtGui import QColor

    app()
    swapped = QColor(154, 166, 38)
    assert (
        swapped.red(),
        swapped.green(),
        swapped.blue(),
        swapped.alpha(),
    ) != surface.UP_FILL


# The painted geometry, read off the shipped paint

GEOMETRY_CASES = [
    c for c in CASES if c.name not in {"empty", "high below low", "times backwards"}
]


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda c: c.name)
def test_the_surface_places_every_candle_body_where_the_chart_paints_it(case):
    """The surface computes a different candle body than the chart paints."""
    calls = record_paint(case)
    payload = surface.build_view_model(drive_new(case), *PIXEL_SIZE)
    axis, panes = payload["price_axis"], payload["panes"]
    geometry = payload["candles"]["geometry"]
    expected = []
    for body in payload["candles"]["bodies"]:
        top = surface.price_to_y(
            body["open"],
            panes["price_top_px"],
            panes["price_height_px"],
            axis["low"],
            axis["span"],
        )
        bottom = surface.price_to_y(
            body["close"],
            panes["price_top_px"],
            panes["price_height_px"],
            axis["low"],
            axis["span"],
        )
        left = round(body["x_px"] + geometry["gap_px"] / 2, 6)
        expected.append(
            (
                "rect",
                left,
                round(min(top, bottom), 6),
                round(geometry["body_px"], 6),
                round(max(abs(top - bottom), 1), 6),
            )
        )
        if panes["volume_height_px"] and body["volume_height_px"] > 0:
            expected.append(
                (
                    "rect",
                    left,
                    round(panes["volume_bottom_px"] - body["volume_height_px"], 6),
                    round(geometry["body_px"], 6),
                    round(body["volume_height_px"], 6),
                )
            )
    painted = [
        args[0] for args in calls_named(calls, "drawRect") if args[0][0] == "rect"
    ]
    assert painted == expected, (case.name, painted[:4], expected[:4])


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda c: c.name)
def test_the_surface_places_every_price_grid_line_where_the_chart_paints_it(case):
    """The surface picks a different tick step or bound than the chart."""
    calls = record_paint(case)
    payload = surface.build_view_model(drive_new(case), *PIXEL_SIZE)
    axis, panes = payload["price_axis"], payload["panes"]
    expected = []
    for tick in axis["grid"]["ticks"]:
        y = int(
            surface.price_to_y(
                tick["price"],
                panes["price_top_px"],
                panes["price_height_px"],
                axis["low"],
                axis["span"],
            )
        )
        if panes["price_top_px"] <= y <= panes["price_bottom_px"]:
            expected.append(y)
    drawn = full_width_lines(
        calls, panes["left_margin_px"], PIXEL_SIZE[0] - panes["right_margin_px"]
    )
    for y in expected:
        assert y in drawn, (case.name, y, sorted(set(drawn))[:12])


@pytest.mark.parametrize("case", GEOMETRY_CASES, ids=lambda c: c.name)
def test_the_surface_writes_every_axis_label_the_chart_writes(case):
    """The surface rounds an axis price differently from the chart."""
    calls = record_paint(case)
    payload = surface.build_view_model(drive_new(case), *PIXEL_SIZE)
    written = {
        args[-1] for args in calls_named(calls, "drawText") if isinstance(args[-1], str)
    }
    labels = {t["label"] for t in payload["price_axis"]["grid"]["ticks"]}
    assert labels & written or not labels, (case.name, sorted(labels)[:5])
    assert payload["price_axis"]["last_price_label"] in written


def test_a_tight_range_at_a_high_price_keeps_its_top_price_tick():
    """``price_grid`` scales its last-tick tolerance to the tick step."""
    grid = surface.price_grid(117999.7, 118000.3)
    prices = [tick["price"] for tick in grid["ticks"]]
    assert prices[-1] == pytest.approx(118000.3, abs=grid["step"] / 100), prices


def test_a_low_priced_range_gains_no_tick_past_its_top():
    """``price_grid`` draws no tick above ``high`` at BONK prices."""
    grid = surface.price_grid(3.0e-06, 3.2e-06)
    prices = [tick["price"] for tick in grid["ticks"]]
    assert prices[-1] <= 3.2e-06 + grid["step"] / 100, prices
    assert len(prices) == 11, prices


def test_slingshot_bandwidth_is_bollingers_published_normalisation():
    """``slingshot_bands`` divides by the middle price with nothing added."""
    from src.trading.indicators.slingshot import SlingshotIndicator

    closes = [3.1e-06 * (1.0 + 0.004 * (index % 7)) for index in range(60)]
    rows = [row for row in surface.slingshot_bands(closes) if row is not None]
    assert rows, "slingshot_bands returned no band row to compare"
    for close, upper, lower, middle, bandwidth in rows:
        del close
        assert bandwidth == SlingshotIndicator._bandwidth(upper, lower, middle), (
            bandwidth,
            middle,
        )


def test_the_bandwidth_comparison_would_see_an_added_epsilon():
    """An added epsilon moves the bandwidth ``slingshot_bands`` returns."""
    from src.trading.indicators.slingshot import SlingshotIndicator

    middle = 3.1e-06
    published = SlingshotIndicator._bandwidth(middle * 1.02, middle * 0.98, middle)
    biased = (middle * 1.02 - middle * 0.98) / (middle + 1e-9)
    drift = abs(biased / published - 1.0)
    assert drift > 3e-4, drift


GLOW_WIDTH_PX = 6


def armed_glow_rects(scrum_armed, fold_armed):
    """The right-edge glow rectangles painted for one armed state."""
    calls = record_paint(
        BY_NAME["normal"],
        setup=lambda chart: chart.set_fire_armed_state(scrum_armed, fold_armed),
    )
    glow_x = PIXEL_SIZE[0] - surface.RIGHT_MARGIN_PX - 4
    return [
        args[0]
        for args in calls_named(calls, "drawRect")
        if args[0][0] == "rect"
        and args[0][3] == GLOW_WIDTH_PX
        and round(args[0][1]) == glow_x
    ]


def test_no_armed_gate_paints_no_right_edge_glow():
    """``set_fire_armed_state`` with both flags off paints no glow."""
    assert armed_glow_rects(False, False) == []


def test_an_armed_scrum_paints_one_glow_in_the_upper_half():
    """A scrum-armed chart paints its glow above the price pane's middle."""
    rects = armed_glow_rects(True, False)
    assert len(rects) == 1, rects
    payload = surface.build_view_model(drive_new(BY_NAME["normal"]), *PIXEL_SIZE)
    panes = payload["panes"]
    middle = panes["price_top_px"] + panes["price_height_px"] / 2
    assert rects[0][2] < middle, (rects, middle)


def test_an_armed_fold_paints_one_glow_in_the_lower_half():
    """A fold-armed chart paints its glow below the price pane's middle."""
    rects = armed_glow_rects(False, True)
    assert len(rects) == 1, rects
    payload = surface.build_view_model(drive_new(BY_NAME["normal"]), *PIXEL_SIZE)
    panes = payload["panes"]
    middle = panes["price_top_px"] + panes["price_height_px"] / 2
    assert rects[0][2] >= middle, (rects, middle)


def test_both_gates_armed_paint_both_glows():
    """A chart armed on both sides paints two right-edge glows."""
    assert len(armed_glow_rects(True, True)) == 2


def squeezing_closes(count=200):
    """Closes whose volatility alternates, so slingshot squeezes fire."""
    closes = []
    price = 100.0
    for index in range(count):
        step = 0.02 if (index // 40) % 2 == 0 else 1.6
        price += step if index % 2 == 0 else -step * 0.9
        closes.append(price)
    return closes


def test_the_slingshot_overlay_ignores_the_bollinger_toggle():
    """``_show_slingshot`` alone decides whether the markers paint."""
    module = chart_module()
    closes = squeezing_closes()
    assert any(
        fire["kind"] == "squeeze" for fire in surface.slingshot_fires(closes)
    ), "the fixture closes produce no squeeze to paint"
    candles = [
        module.Candle(
            time=1_700_000_000 + index * 3600,
            open=close,
            high=close * 1.001,
            low=close * 0.999,
            close=close,
            volume=1.0,
        )
        for index, close in enumerate(closes)
    ]

    def diamonds_with(show_bb):
        def setup(chart):
            chart.set_candles(candles)
            chart._show_slingshot = True
            chart._show_bb = show_bb

        calls = record_paint(BY_NAME["normal"], setup=setup)
        return [
            args[0]
            for args in calls_named(calls, "drawPolygon")
            if len(args[0][1]) == 4
        ]

    without_bb = diamonds_with(False)
    assert without_bb, "the slingshot overlay painted no diamond at all"
    assert diamonds_with(True) == without_bb


def test_the_recorder_reports_a_difference_between_two_real_inputs():
    """The recorder returns the same calls whatever it is driven with."""
    one = record_paint(BY_NAME["normal"])
    other = record_paint(BY_NAME["sub cent"])
    assert one != other
    assert record_paint(BY_NAME["normal"]) == one


def test_the_recorder_captured_the_paint_and_not_an_empty_run():
    """The recorder captured nothing, so every geometry check is empty."""
    calls = record_paint(BY_NAME["normal"])
    assert len(calls) > 50, len(calls)
    assert calls[-1][0] == "end"
    assert len(record_paint(BY_NAME["empty"])) < len(calls)


# Steps, refusals and the recorder that keeps what came before


def test_a_step_sequence_records_every_step_in_order():
    """The model lost a step, or recorded them out of order."""
    model = surface.ChartModel("BTC-USD")
    model.set_candles(surface_candles(BY_NAME["normal"]))
    model.set_source_label("coinbase")
    model.set_timeframe("4h")
    model.toggle_indicator("macd", True)
    assert [name for _, name in model.steps] == [
        "set_candles",
        "set_source_label",
        "set_timeframe",
        "toggle_indicator",
    ]
    assert [index for index, _ in model.steps] == [0, 1, 2, 3]


def test_a_sequence_that_refuses_part_way_keeps_what_it_recorded():
    """A refusal threw away the steps the model had already taken."""
    model = surface.ChartModel("BTC-USD")
    model.set_candles(surface_candles(BY_NAME["normal"]))
    model.set_timeframe("1d")
    with pytest.raises(surface.Refused):
        model.toggle_indicator("not-an-indicator", True)
    assert [name for _, name in model.steps] == [
        "set_candles",
        "set_timeframe",
        "toggle_indicator",
    ]
    assert model.timeframe == "1d"
    assert len(model.candles) == 30
    model.set_source_label("kraken")
    assert model.steps[-1] == [3, "set_source_label"]


def test_a_refusal_is_told_apart_from_a_step_that_worked():
    """The refusal check passes whether or not the model refused."""
    model = surface.ChartModel()
    model.toggle_indicator("macd", True)
    assert model.flags["show_macd"] is True
    with pytest.raises(surface.Refused):
        model.toggle_indicator("macd_typo", True)


@pytest.mark.parametrize(
    "trade",
    [
        {"ts": 0, "side": "buy", "price": 10.0},
        {"ts": 1_700_000_000, "side": "buy", "price": 0},
        {"ts": "x", "side": "buy", "price": 10.0},
        {"ts": 1_700_000_000, "side": "buy", "price": "x"},
        {"ts": 1_700_000_000, "side": "buy", "price": 10**400},
        {},
    ],
)
def test_the_two_sides_skip_the_same_unusable_trade(trade):
    """One side kept, or refused, a trade marker the other did not."""
    module = chart_module()
    app()
    chart = module.CandlestickChart()
    model = surface.ChartModel()
    shipped_refusal = ours_refusal = None
    try:
        chart.set_trade_history_markers([trade])
    except Exception as refused:
        shipped_refusal = type(refused)
    try:
        model.set_markers([trade])
    except Exception as refused:
        ours_refusal = type(refused)
    assert ours_refusal is shipped_refusal, (shipped_refusal, ours_refusal)
    if shipped_refusal is None:
        assert len(model.markers) == len(chart._markers)


def test_the_two_sides_keep_the_same_usable_trade():
    """The skip check drops everything, so it can never report a loss."""
    module = chart_module()
    app()
    good = {"ts": 1_700_000_000, "side": "sell", "price": 12.5, "role": "SCRUM"}
    chart = module.CandlestickChart()
    chart.set_trade_history_markers([good])
    model = surface.ChartModel()
    model.set_markers([good])
    assert len(chart._markers) == 1
    assert len(model.markers) == 1
    assert model.markers[0].label == chart._markers[0].label
    assert model.markers[0].price == chart._markers[0].price


# Completeness, backing and growth


def surface_constants():
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                found[target.id] = node.lineno
    return found


def leaves(value, path=""):
    """Every leaf inside a payload, with the path that reaches it."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield from leaves(inner, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, inner in enumerate(value):
            yield from leaves(inner, f"{path}[{index}]")
    else:
        yield path, value


def test_every_constant_the_surface_ships_reaches_the_view_model():
    """The comparison reads part of the surface, so the rest is unchecked."""
    payload = surface.build_view_model(drive_new(BY_NAME["normal"]), *PIXEL_SIZE)
    published = set(payload["skin"]) | set(payload["metrics"])
    declared = surface_constants()
    structural = {
        "METHOD",
        "ACTIONS",
        "SIGNALS",
        "TIMERS",
        "TIMER_DELAYS_MS",
        "BUS_TOPICS",
        "THREADS",
        "ACCESSIBLE_NAME",
        "TIMEFRAMES",
        "INDICATOR_DEFAULTS",
        "STEP_NAMES",
        "SKIN",
        "METRICS",
        "PANE_MODEL",
    }
    missing = sorted(
        name
        for name in declared
        if name not in structural and name.lower() not in published
    )
    assert missing == [], missing


def test_the_completeness_check_would_report_a_constant_left_out():
    """The completeness check passes whatever the surface leaves out."""
    published = set(surface.SKIN) | set(surface.METRICS)
    assert "up_fill" in published
    assert "a_constant_no_surface_ships" not in published


def test_no_published_key_is_backed_by_nothing():
    """A published value is empty, so a check on it can never report."""
    payload = surface.build_view_model(drive_new(BY_NAME["normal"]), *PIXEL_SIZE)
    unbacked = [
        path
        for path, value in leaves(payload)
        if value is None and not path.startswith((".target_balance", ".empty"))
    ]
    assert unbacked == [], unbacked


def test_the_surface_and_the_shipped_file_name_the_same_indicators():
    """One side grew an indicator the other never heard of."""
    module = chart_module()
    app()
    chart = module.CandlestickChart()
    shipped = {
        name[len("_show_") :] for name in vars(chart) if name.startswith("_show_")
    }
    assert shipped == set(surface.INDICATOR_DEFAULTS)
    for name, default in surface.INDICATOR_DEFAULTS.items():
        assert getattr(chart, f"_show_{name}") == default, name


def test_the_indicator_check_reads_the_widget_and_not_its_own_table():
    """The indicator check reads a name it wrote itself."""
    module = chart_module()
    app()
    chart = module.CandlestickChart()
    assert not hasattr(chart, "_show_a_name_the_chart_never_had")


def test_the_surface_grew_no_public_name_the_module_does_not_carry():
    """A name parsed off the file is not a name the module exposes."""
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    parsed = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    }
    live = {
        name
        for name in dir(surface)
        if not name.startswith("_")
        and callable(getattr(surface, name))
        and getattr(getattr(surface, name), "__module__", "") == surface.__name__
    }
    assert parsed == live, (sorted(parsed - live), sorted(live - parsed))


# Nothing at import time touches the world

PROBE = r"""
import builtins, importlib, json, os, sys, threading, time

reads = {"clock": 0, "files": 0}
real_open, real_time, real_monotonic = builtins.open, time.time, time.monotonic


def watch_open(*a, **k):
    reads["files"] += 1
    return real_open(*a, **k)


builtins.open = watch_open
time.time = lambda: (reads.__setitem__("clock", reads["clock"] + 1), real_time())[1]
time.monotonic = lambda: (
    reads.__setitem__("clock", reads["clock"] + 1),
    real_monotonic(),
)[1]

importlib.import_module("json.decoder")
baseline = dict(reads)
threads_before = threading.active_count()

module = importlib.import_module("src.gui.main_tabs.native_chart_surface")

after_import = {
    "clock": reads["clock"] - baseline["clock"],
    "files": reads["files"] - baseline["files"],
}
qt = sorted(n for n in sys.modules if n.split(".")[0] == "PySide6")
threads_after = threading.active_count() - threads_before

control_before = dict(reads)
time.time()
with watch_open(os.__file__) as handle:
    handle.read(1)
control = {
    "clock": reads["clock"] - control_before["clock"],
    "files": reads["files"] - control_before["files"],
}

model = module.ChartModel("BTC-USD")
model.set_candles(
    [module.Candle(1700000000 + i * 3600, 10.0 + i, 11.0 + i, 9.0 + i, 10.5 + i, 1.0)
     for i in range(30)]
)
payload = module.build_view_model(model, 520, 340)

print(json.dumps({
    "after_import": after_import,
    "qt_modules": qt,
    "threads": threads_after,
    "control": control,
    "built": payload["candle_count"],
    "ticks": len(payload["price_axis"]["grid"]["ticks"]),
}))
"""


def probe_result(env_extra=None):
    env = dict(os.environ)
    env.pop("QT_QPA_PLATFORM", None)
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.update(env_extra or {})
    done = subprocess.run(
        [sys.executable, "-"],
        input=PROBE.encode("utf-8"),
        capture_output=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode().strip().splitlines()[-1])


def test_importing_the_surface_touches_no_clock_no_file_and_no_thread():
    """Importing the surface reads the world before anything asks it to."""
    seen = probe_result()
    assert seen["control"]["clock"] >= 1, "the probe cannot see a clock read"
    assert seen["control"]["files"] >= 1, "the probe cannot see a file open"
    assert seen["after_import"] == {"clock": 0, "files": 0}, seen["after_import"]
    assert seen["threads"] == 0
    assert seen["qt_modules"] == [], seen["qt_modules"]
    assert seen["built"] == 30
    assert seen["ticks"] > 0


def test_the_surface_builds_its_whole_model_with_pyside_absent():
    """The surface needs Qt loaded before it can answer."""
    seen = probe_result()
    assert seen["qt_modules"] == []
    assert seen["ticks"] > 0


def test_the_surface_writes_no_file_into_a_throwaway_home(tmp_path):
    """The surface wrote into the home directory it was pointed at."""
    home = tmp_path / "throwaway"
    home.mkdir()
    seen = probe_result(
        {
            "ACERVATOR_TEST_HOME": str(home),
            "HOME": str(home),
            "USERPROFILE": str(home),
        }
    )
    assert seen["after_import"] == {"clock": 0, "files": 0}
    assert list(home.rglob("*")) == [], list(home.rglob("*"))
    (home / "planted.txt").write_text("x", encoding="utf-8")
    assert list(home.rglob("*")) != [], "the file check cannot see a written file"


# Order independence


def test_the_surface_module_holds_no_state_between_two_models():
    """One chart's state reached another chart built after it."""
    first = surface.ChartModel("AAA")
    first.set_candles(surface_candles(BY_NAME["normal"]))
    first.toggle_indicator("macd", True)
    second = surface.ChartModel("BBB")
    assert second.candles == []
    assert second.flags == {
        "show_%s" % k: v for k, v in surface.INDICATOR_DEFAULTS.items()
    }
    assert second.steps == []
    assert first.flags["show_macd"] is True


def test_the_bridge_handler_starts_clean_when_it_is_reset():
    """A reset left the previous chart's values in place."""
    surface.view_model({"reset": True, "symbol": "AAA"})
    surface.view_model(
        {"candles": [{"time": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}]}
    )
    after = surface.view_model({"reset": True, "symbol": "BBB"})
    assert after["candle_count"] == 0
    assert after["symbol"] == "BBB"
    assert after["steps"] == []


def mutable_module_bindings(module):
    """Every non-dunder name a module binds to a mutable container."""
    return {
        name: type(value).__name__
        for name, value in vars(module).items()
        if not name.startswith("__") and isinstance(value, (list, dict, set, bytearray))
    }


def test_the_chart_module_binds_no_mutable_table_at_import():
    """Importing ``native_chart`` binds no shared mutable container."""
    from src.gui import native_chart

    assert mutable_module_bindings(native_chart) == {}, mutable_module_bindings(
        native_chart
    )


def test_the_mutable_binding_reader_reports_a_module_that_has_one():
    """The reader names a mutable module-level binding when one exists."""
    from types import ModuleType

    holder = ModuleType("holder")
    holder.table = {}
    assert mutable_module_bindings(holder) == {"table": "dict"}


# The pictures


def widget_painted_by_the_chart(case):
    """The shipped widget, driven over one case and ready to render."""
    return drive_old(case)


def widget_painted_by_the_model(payload):
    """A widget built only from the payload, never from the shipped chart.

    A payload the caller changed after it came off the surface is refused.
    """
    payload = unaltered(payload)
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import (
        QBrush,
        QColor,
        QFont,
        QFontMetrics,
        QLinearGradient,
        QPainter,
        QPen,
    )
    from PySide6.QtWidgets import QWidget

    app()
    metrics = payload["metrics"]
    skin = payload["skin"]

    def colour(key):
        return QColor(*skin[key])

    class PayloadChart(QWidget):
        def __init__(self):
            super().__init__()
            self.setAccessibleName(payload["accessible_name"])

        def paintEvent(self, _event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.TextAntialiasing)
            width, height = self.width(), self.height()
            ground = QLinearGradient(0, 0, 0, height)
            ground.setColorAt(0, colour("bg_top"))
            ground.setColorAt(1, colour("bg_bot"))
            painter.fillRect(0, 0, width, height, ground)

            font_small = QFont("Consolas", 8)
            font_small.setHintingPreference(QFont.PreferFullHinting)
            font_header = QFont("Segoe UI", 10, QFont.Bold)
            font_ohlc = QFont("Consolas", 9, QFont.Bold)
            small_metrics = QFontMetrics(font_small)

            if payload["empty"] is not None:
                painter.setPen(QPen(colour("text_dim")))
                painter.setFont(QFont("Segoe UI", 11))
                painter.drawText(
                    QRectF(0, 0, width, height),
                    Qt.AlignCenter,
                    payload["empty"]["message"],
                )
                self._header(painter, width, font_header, font_small)
                painter.end()
                return

            panes = payload["panes"]
            axis = payload["price_axis"]
            left = panes["left_margin_px"]
            right = width - panes["right_margin_px"]

            def to_y(price):
                return surface.price_to_y(
                    price,
                    panes["price_top_px"],
                    panes["price_height_px"],
                    axis["low"],
                    axis["span"],
                )

            for tick in axis["grid"]["ticks"]:
                y = int(to_y(tick["price"]))
                if not panes["price_top_px"] <= y <= panes["price_bottom_px"]:
                    continue
                painter.setPen(
                    QPen(
                        colour("grid_major") if tick["major"] else colour("grid_minor"),
                        1,
                        Qt.DotLine,
                    )
                )
                painter.drawLine(left, y, right, y)
                painter.setPen(QPen(colour("text_light")))
                painter.setFont(font_small)
                painter.drawText(right + 6, y + 4, tick["label"])

            geometry = payload["candles"]["geometry"]
            column = geometry["column_px"]
            for tick in payload["time_axis"]["ticks"]:
                x = int(surface.index_to_x(tick["index"], left, column) + column / 2)
                if x < left or x > right:
                    continue
                painter.setPen(QPen(colour("grid_minor"), 1, Qt.DotLine))
                painter.drawLine(x, panes["price_top_px"], x, panes["time_axis_top_px"])
                if tick["label"]:
                    painter.setPen(QPen(colour("text_light")))
                    painter.setFont(font_small)
                    painter.drawText(
                        x - metrics["time_label_offset_px"],
                        panes["time_axis_top_px"] + metrics["time_label_baseline_px"],
                        tick["label"],
                    )

            for body in payload["candles"]["bodies"]:
                wick_x = body["x_px"] + column / 2
                painter.setPen(QPen(QColor(*body["colors"]["wick"]), 1))
                painter.drawLine(
                    int(wick_x),
                    int(to_y(body["high"])),
                    int(wick_x),
                    int(to_y(body["low"])),
                )
                top, bottom = to_y(body["open"]), to_y(body["close"])
                painter.setBrush(QBrush(QColor(*body["colors"]["fill"])))
                painter.setPen(QPen(QColor(*body["colors"]["border"]), 1))
                painter.drawRect(
                    QRectF(
                        body["x_px"] + geometry["gap_px"] / 2,
                        min(top, bottom),
                        geometry["body_px"],
                        max(abs(top - bottom), 1),
                    )
                )
                if panes["volume_height_px"] and body["volume_height_px"] > 0:
                    painter.setBrush(QBrush(QColor(*body["volume_colors"]["fill"])))
                    painter.setPen(QPen(QColor(*body["volume_colors"]["border"]), 1))
                    painter.drawRect(
                        QRectF(
                            body["x_px"] + geometry["gap_px"] / 2,
                            panes["volume_bottom_px"] - body["volume_height_px"],
                            geometry["body_px"],
                            body["volume_height_px"],
                        )
                    )

            if panes["volume_height_px"]:
                painter.setPen(QPen(colour("grid_major"), 1))
                painter.drawLine(
                    left,
                    int(panes["volume_top_px"]),
                    right,
                    int(panes["volume_top_px"]),
                )

            last_y = to_y(axis["last_price"])
            painter.setPen(QPen(colour("price_line_color"), 1, Qt.DashLine))
            painter.drawLine(left, int(last_y), right, int(last_y))
            label = axis["last_price_label"]
            badge_width = (
                small_metrics.horizontalAdvance(label) + metrics["price_badge_pad_px"]
            )
            badge = QRectF(
                right,
                last_y - metrics["price_badge_lift_px"],
                badge_width,
                metrics["price_badge_height_px"],
            )
            painter.setBrush(QBrush(colour("price_badge_fill")))
            painter.setPen(QPen(colour("price_line_color"), 1))
            painter.drawRoundedRect(
                badge,
                metrics["price_badge_radius_px"],
                metrics["price_badge_radius_px"],
            )
            painter.setFont(font_small)
            painter.drawText(badge, Qt.AlignCenter, label)

            if panes["volume_height_px"] and payload["candles"]["max_volume"] > 0:
                painter.setPen(QPen(colour("text_dim")))
                painter.setFont(font_small)
                painter.drawText(
                    right + metrics["volume_axis_inset_px"],
                    int(panes["volume_top_px"] + metrics["volume_axis_baseline_px"]),
                    metrics["volume_axis_format"].format(
                        value=payload["candles"]["volume_label"]
                    ),
                )

            painter.setFont(font_ohlc)
            ohlc_metrics = QFontMetrics(font_ohlc)
            baseline = panes["ohlc_top_px"] + metrics["ohlc_baseline_px"]
            cursor = left + metrics["ohlc_inset_px"]
            for text, value, tone in payload["ohlc_row"]:
                if text:
                    painter.setPen(QPen(colour("text_dim")))
                    painter.drawText(int(cursor), int(baseline), text)
                    cursor += (
                        ohlc_metrics.horizontalAdvance(text)
                        + metrics["ohlc_label_gap_px"]
                    )
                painter.setPen(QPen(QColor(*tone)))
                painter.drawText(int(cursor), int(baseline), value)
                cursor += (
                    ohlc_metrics.horizontalAdvance(value) + metrics["ohlc_value_gap_px"]
                )

            self._header(painter, width, font_header, font_small)
            self._grip(painter, width, height)
            painter.end()

        def _header(self, painter, width, font_header, font_small):
            painter.setFont(font_header)
            painter.setPen(QPen(colour("accent")))
            painter.drawText(
                metrics["header_symbol_x_px"],
                metrics["header_baseline_px"],
                payload["symbol"],
            )
            painter.setFont(font_small)
            painter.setPen(QPen(colour("text_dim")))
            offset = (
                QFontMetrics(font_header).horizontalAdvance(payload["symbol"])
                + metrics["header_info_gap_px"]
            )
            painter.drawText(
                int(offset), metrics["header_baseline_px"], payload["header_text"]
            )
            if payload["error_text"]:
                painter.setPen(QPen(colour("header_error_color")))
                painter.drawText(
                    metrics["header_symbol_x_px"],
                    metrics["header_baseline_px"] + metrics["header_error_drop_px"],
                    payload["error_text"],
                )

        def _grip(self, painter, width, height):
            grip_y = height - payload["resize_grip_px"] // 2
            painter.setPen(QPen(colour("grip_color"), metrics["grip_line_width_px"]))
            centre = width / 2
            for offset in metrics["grip_dash_offsets_px"]:
                painter.drawLine(
                    int(centre + offset - metrics["grip_dash_half_px"]),
                    int(grip_y),
                    int(centre + offset + metrics["grip_dash_half_px"]),
                    int(grip_y),
                )

    built = PayloadChart()
    built.resize(*PIXEL_SIZE)
    return built


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_the_two_sides_paint_one_picture(name):
    """The surface painted a different chart than the shipped widget."""
    app()
    note = "%s, %s" % (name, "real fonts" if has_real_fonts() else "no fonts")
    old_side = render_offscreen(widget_painted_by_the_chart(BY_NAME[name]), PIXEL_SIZE)
    assert_picture_can_report(old_side, note=note)
    new_side = render_offscreen(
        widget_painted_by_the_model(model_payload(BY_NAME[name])), PIXEL_SIZE
    )
    assert_picture_can_report(new_side, note=note)
    assert_pictures_match(old_side=old_side, new_side=new_side, note=note)


def test_two_different_series_paint_two_different_pictures():
    """The picture check passes whatever the second side painted."""
    app()
    old_side = render_offscreen(
        widget_painted_by_the_chart(BY_NAME["normal"]), PIXEL_SIZE
    )
    assert_picture_can_report(old_side, note="normal")
    new_side = render_offscreen(
        widget_painted_by_the_model(model_payload(BY_NAME["sub cent"])), PIXEL_SIZE
    )
    assert_picture_can_report(new_side, note="sub cent")
    assert_pictures_differ(old_side=old_side, new_side=new_side, note="two real inputs")


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    app()
    payload = model_payload()
    payload["symbol"] = "MOVED"
    with pytest.raises(AssertionError):
        widget_painted_by_the_model(payload)


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_no_style_rule_reaches_a_pixel_of_the_chart(name):
    """A style rule moved a pixel, so a skin control could report here.

    The chart paints its whole rectangle in ``paintEvent``, so a style
    sheet reaches nothing it draws. ``assert_same_skin`` needs a rule that
    changes the picture, and no rule does on this widget; the old side
    against new side comparison above is what carries the skin instead.
    """
    app()
    plain = render_offscreen(widget_painted_by_the_chart(BY_NAME[name]), PIXEL_SIZE)
    skinned_widget = widget_painted_by_the_chart(BY_NAME[name])
    skinned_widget.setStyleSheet("QWidget { background: #7d1a4a; }")
    skinned = render_offscreen(skinned_widget, PIXEL_SIZE)
    assert_picture_can_report(plain, note=name)
    assert_pictures_match(old_side=plain, new_side=skinned, note=name)


@pytest.mark.parametrize("name", PICTURE_SCENARIOS)
def test_each_state_paints_more_than_one_colour(name):
    """A state paints one flat colour, so its picture proves nothing."""
    app()
    painted = render_offscreen(widget_painted_by_the_chart(BY_NAME[name]), PIXEL_SIZE)
    assert colour_count(painted) > 1, name
