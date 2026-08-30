"""The shipped TradingView chart and the Qt-free surface, side by side.

A failure means the view model carries a different page, a different
colour, a different button, a different call into the page, a different
layout number or a different fallback than
``src.gui.tradingview_chart`` hands the browser.

The shipped chart draws nothing itself: it builds one HTML page and
gives it to a browser widget, then talks to that page with JavaScript
calls. Both sides are driven through that same boundary here. The
browser widget is replaced with one that records what it is handed and
loads nothing, so no test reaches the internet.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import tradingview_chart as shipped
from src.gui.main_tabs import tradingview_chart_surface as surface
from tests.fixtures.host_fonts import has_real_fonts
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

SHIPPED_PATH = REPO_ROOT / "src/gui/tradingview_chart.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/tradingview_chart_surface.py"
BRIDGE_PATH = REPO_ROOT / "src/core/desktop_bridge.py"
WIRED_CONNECT_PATH = REPO_ROOT / "src/gui/main_tabs/history_tab.py"
WIRED_TIMER_PATH = REPO_ROOT / "src/gui/history_tab.py"
WIRED_BUS_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"

METHOD_NAME = "tradingview.chart"

SWATCH_SIZE = (260, 160)
SWATCH_SYMBOL = "BTC/USDT"

THEME_TOTAL = 5
THEME_KEY_TOTAL = 8
BUTTON_TOTAL = 7
CALL_TOTAL = 5
SHIPPED_METHOD_TOTAL = 9
SURFACE_FUNCTION_TOTAL = 14
CONSTANT_TOTAL = 61
PAYLOAD_KEY_TOTAL = 44

# Every value typed out here rather than read from either module, so a
# value moved on both sides together is still reported.
EXPECTED_ACCESSIBLE_NAME = "Trading View Chart"
EXPECTED_LOGGER_NAME = "acervator.gui"
EXPECTED_MISSING_WARNING = "TradingView charts require PySide6-WebEngine"
EXPECTED_DEFAULT_SYMBOL = "BTC/USDT"
EXPECTED_DEFAULT_THEME = "cyberpunk_dark"
EXPECTED_SCRIPT_URL = (
    "https://unpkg.com/lightweight-charts@4.1.0/dist/"
    "lightweight-charts.standalone.production.js"
)

EXPECTED_THEMES = {
    "cyberpunk_dark": {
        "bg": "#0a0a0f",
        "text": "#e0e0f0",
        "grid": "#1a1a28",
        "border": "#2a2a44",
        "accent": "#00ffcc",
        "btn_bg": "#12121a",
        "btn_hover": "#1e1e35",
        "watermark": "rgba(0,255,204,0.07)",
    },
    "neon_light": {
        "bg": "#f5f5fa",
        "text": "#1a1a2e",
        "grid": "#e5e5f0",
        "border": "#ccccdd",
        "accent": "#6600cc",
        "btn_bg": "#eeeef5",
        "btn_hover": "#e0e0f0",
        "watermark": "rgba(102,0,204,0.07)",
    },
    "classic_terminal": {
        "bg": "#0a0a0a",
        "text": "#00ff00",
        "grid": "#181818",
        "border": "#003300",
        "accent": "#00ff00",
        "btn_bg": "#111111",
        "btn_hover": "#1a1a1a",
        "watermark": "rgba(0,255,0,0.05)",
    },
    "minimal_modern": {
        "bg": "#fafafa",
        "text": "#1a1a1a",
        "grid": "#e8e8e8",
        "border": "#e0e0e0",
        "accent": "#2563eb",
        "btn_bg": "#f0f0f0",
        "btn_hover": "#eeeeee",
        "watermark": "rgba(37,99,235,0.05)",
    },
    "glass_metal": {
        "bg": "#1c1c24",
        "text": "#d0d0e0",
        "grid": "#2c2c3a",
        "border": "#3a3a50",
        "accent": "#88ccff",
        "btn_bg": "#242430",
        "btn_hover": "#30303f",
        "watermark": "rgba(136,204,255,0.07)",
    },
}

EXPECTED_THEME_ORDER = (
    "cyberpunk_dark",
    "neon_light",
    "classic_terminal",
    "minimal_modern",
    "glass_metal",
)

EXPECTED_THEME_KEYS = (
    "bg",
    "text",
    "grid",
    "border",
    "accent",
    "btn_bg",
    "btn_hover",
    "watermark",
)

EXPECTED_BUTTONS = (
    ("1m", "1", False),
    ("5m", "5", False),
    ("15m", "15", False),
    ("1H", "60", True),
    ("4H", "240", False),
    ("1D", "D", False),
    ("1W", "W", False),
)

EXPECTED_CALL_FORMATS = {
    "set_candles": "setCandles('{payload}')",
    "update_candle": "updateCandle('{payload}')",
    "set_bollinger_bands": "setBollingerBands('{payload}')",
    "add_trade_marker": "addTradeMarker('{payload}')",
    "set_grid_levels": "setGridLevels('{payload}')",
}

EXPECTED_CANDLE_SERIES = {
    "up": "#00ff88",
    "down": "#ff3366",
    "border_up": "#00ff88",
    "border_down": "#ff3366",
    "wick_up": "#00ff88",
    "wick_down": "#ff3366",
}

EXPECTED_VOLUME_SERIES = {
    "color": "#26a69a",
    "price_format": "volume",
    "price_scale_id": "",
    "scale_margin_top": 0.85,
    "scale_margin_bottom": 0,
    "up": "rgba(0, 255, 136, 0.3)",
    "down": "rgba(255, 51, 102, 0.3)",
}

EXPECTED_BOLLINGER_SERIES = {
    "upper_color": "rgba(0, 170, 255, 0.4)",
    "lower_color": "rgba(0, 170, 255, 0.4)",
    "middle_color": "rgba(0, 170, 255, 0.2)",
    "line_width_px": 1,
    "middle_line_style": 2,
    "fields": ["upper", "middle", "lower"],
}

EXPECTED_MARKER_SKIN = {
    "buy_position": "belowBar",
    "sell_position": "aboveBar",
    "buy_color": "#00ff88",
    "sell_color": "#ff3366",
    "buy_shape": "arrowUp",
    "sell_shape": "arrowDown",
    "amount_decimals": 4,
    "sorted_by": "time",
}

EXPECTED_GRID_LINE_SKIN = {
    "buy_color": "rgba(0, 255, 136, 0.15)",
    "sell_color": "rgba(255, 51, 102, 0.15)",
    "line_width_px": 1,
    "line_style": 2,
    "axis_label_visible": True,
    "cleared_before_draw": False,
}

EXPECTED_PAGE_MARGINS = [0, 0, 0, 0]

# Colours whose three channels are equal, so a channel swap would paint
# the same pixel. Compared as exact text instead.
EQUAL_CHANNEL_COLORS = {
    ("classic_terminal", "bg"): "#0a0a0a",
    ("classic_terminal", "grid"): "#181818",
    ("classic_terminal", "btn_bg"): "#111111",
    ("classic_terminal", "btn_hover"): "#1a1a1a",
    ("minimal_modern", "bg"): "#fafafa",
    ("minimal_modern", "text"): "#1a1a1a",
    ("minimal_modern", "grid"): "#e8e8e8",
    ("minimal_modern", "border"): "#e0e0e0",
    ("minimal_modern", "btn_bg"): "#f0f0f0",
    ("minimal_modern", "btn_hover"): "#eeeeee",
}

# One colour used under two names. A picture cannot say which name it
# came from, so each is read by name.
REPEATED_COLORS = {
    ("classic_terminal", "text"): "#00ff00",
    ("classic_terminal", "accent"): "#00ff00",
    ("neon_light", "btn_hover"): "#e0e0f0",
    ("cyberpunk_dark", "text"): "#e0e0f0",
}


# ---------------------------------------------------------------------
# One table, every case, driven through both sides
# ---------------------------------------------------------------------

LONG_SYMBOL = "Z" * 200
UNICODE_SYMBOL = "₿/€ 中文 éè"
MARKUP_SYMBOL = "<script>alert('x')</script>"
NEWLINE_SYMBOL = "BTC\nUSDT"
QUOTE_SYMBOL = "BTC'USDT"

BASE_CANDLES = [
    {"time": 1, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0},
    {"time": 2, "open": 1.5, "high": 2.5, "low": 1.0, "close": 1.2, "volume": 20.0},
]

BASE_CANDLE = {
    "time": 3,
    "open": 1.2,
    "high": 1.9,
    "low": 1.1,
    "close": 1.8,
    "volume": 30.0,
}

BASE_BANDS = [
    {"time": 1, "upper": 2.0, "middle": 1.5, "lower": 1.0},
    {"time": 2, "upper": 2.2, "middle": 1.6, "lower": 1.1},
]

BASE_LEVELS = [
    {"price": 100.0, "side": "buy", "level": 1},
    {"price": 200.0, "side": "sell", "level": 2},
]


def case(**named):
    """One driving case, on the happy values unless a key is given."""
    made = {
        "symbol": EXPECTED_DEFAULT_SYMBOL,
        "theme": EXPECTED_DEFAULT_THEME,
        "candles": BASE_CANDLES,
        "candle": BASE_CANDLE,
        "bands": BASE_BANDS,
        "marker": (1700000000, "buy", 0.01),
        "levels": BASE_LEVELS,
        "switch_to": "neon_light",
    }
    made.update(named)
    return made


CASES = {
    "happy": case(),
    "empty_symbol": case(symbol=""),
    "empty_data": case(candles=[], bands=[], levels=[]),
    "zero_amount": case(marker=(0, "buy", 0.0)),
    "negative_amount": case(marker=(-1, "sell", -12.5)),
    "a_thousand_million": case(marker=(1, "sell", 1000000000.0)),
    "one_billionth": case(marker=(1, "buy", 1e-09)),
    "infinite_amount": case(marker=(1, "buy", float("inf"))),
    "unicode_symbol": case(symbol=UNICODE_SYMBOL),
    "two_hundred_characters": case(symbol=LONG_SYMBOL),
    "markup_in_the_symbol": case(symbol=MARKUP_SYMBOL),
    "quote_in_the_symbol": case(symbol=QUOTE_SYMBOL),
    "newline_in_the_symbol": case(symbol=NEWLINE_SYMBOL),
    "number_where_text_belongs": case(symbol=12345),
    "text_where_a_number_belongs": case(marker=(1, "buy", "0.01")),
    "wrong_capitals_in_the_theme": case(theme="Cyberpunk_Dark"),
    "unknown_theme": case(theme="dark"),
    "no_theme_at_all": case(theme=None),
    "every_theme_neon": case(theme="neon_light", switch_to="classic_terminal"),
    "every_theme_terminal": case(theme="classic_terminal", switch_to="glass_metal"),
    "every_theme_minimal": case(theme="minimal_modern", switch_to="cyberpunk_dark"),
    "every_theme_glass": case(theme="glass_metal", switch_to="minimal_modern"),
    "unknown_side_on_the_marker": case(marker=(1, "HOLD", 1.0)),
    "switch_to_an_unknown_theme": case(switch_to="no_such_theme"),
}

# Inputs both sides must refuse, and the way each refuses them.
REFUSALS = {
    "a_candle_set": ("set_candles", {1, 2}),
    "a_bare_object": ("set_candles", object()),
    "bands_holding_bytes": ("set_bollinger_bands", [b"raw"]),
    "levels_holding_a_set": ("set_grid_levels", [{"price": {1}}]),
}


# ---------------------------------------------------------------------
# Reading each side
# ---------------------------------------------------------------------

HELD: list = []


def app():
    """The process application object every render needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def digest(payload):
    """A stable hash over one side's whole answer."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _recording_page(view):
    class Page:
        """The page object the chart asks for before every call."""

        def runJavaScript(self, js):
            if not isinstance(js, str):
                raise AssertionError(f"the chart ran a non-string call: {js!r}")
            view.js.append(js)

    return Page()


def _recording_web_view_class():
    from PySide6.QtWidgets import QWidget

    class RecordingWebView(QWidget):
        """A browser widget that records and loads nothing.

        Stands in for ``QWebEngineView`` so the shipped chart runs its
        real code without reaching the internet. Anything the chart
        asks for that a browser would not answer fails loudly.
        """

        def __init__(self, *args, **named):
            super().__init__(*args, **named)
            self.setAccessibleName("Recording Web View")
            self.html: list = []
            self.js: list = []
            self._page = _recording_page(self)

        def setHtml(self, html):
            if not isinstance(html, str):
                raise AssertionError(f"the chart set a non-string page: {html!r}")
            self.html.append(html)

        def page(self):
            return self._page

    return RecordingWebView


@contextmanager
def recording_web_view():
    """Swap the browser widget for one that records and loads nothing."""
    was = shipped.QWebEngineView
    shipped.QWebEngineView = _recording_web_view_class()
    try:
        yield
    finally:
        shipped.QWebEngineView = was


@pytest.fixture(autouse=True)
def restore_shipped_theme_table():
    """The shipped chart writes the symbol into the theme table it reads.

    A failure means one test left that table carrying another test's
    symbol, so the run stopped being repeatable.
    """
    was = {name: dict(one) for name, one in shipped.CHART_THEMES.items()}
    yield
    for name, one in shipped.CHART_THEMES.items():
        one.clear()
        one.update(was[name])


def old_chart(symbol=EXPECTED_DEFAULT_SYMBOL, theme=EXPECTED_DEFAULT_THEME):
    """The shipped chart, built with a browser widget that records."""
    app()
    chart = shipped.TradingViewChart(symbol=symbol, theme=theme)
    HELD.append(chart)
    return chart


def old_display(spec):
    """Everything the shipped chart hands the browser for one case."""
    with recording_web_view():
        chart = old_chart(spec["symbol"], spec["theme"])
        view = chart._web
        first_html = view.html[-1]
        chart.set_candles(spec["candles"])
        chart.update_candle(spec["candle"])
        chart.set_bollinger_bands(spec["bands"])
        chart.add_trade_marker(*spec["marker"])
        chart.set_grid_levels(spec["levels"])
        calls = list(view.js)
        layout = chart.layout()
        margins = layout.contentsMargins()
        shown = {
            "accessible_name": chart.accessibleName(),
            "symbol": chart._symbol,
            "theme": chart._theme,
            "html": first_html,
            "html_sha": hashlib.sha256(first_html.encode("utf-8")).hexdigest(),
            "margins_px": [
                margins.left(),
                margins.top(),
                margins.right(),
                margins.bottom(),
            ],
            "child_count": layout.count(),
            "child_is_the_web_view": layout.itemAt(0).widget() is view,
            "page_count": len(view.html),
            "calls": calls,
            "call_count": len(calls),
        }
        chart.set_theme(spec["switch_to"])
        switched = view.html[-1]
        shown["theme_after_switch"] = chart._theme
        shown["html_after_switch"] = switched
        shown["html_after_switch_sha"] = hashlib.sha256(
            switched.encode("utf-8")
        ).hexdigest()
        shown["page_count_after_switch"] = len(view.html)
        shown["calls_after_switch"] = list(view.js)
    return shown


def new_display(spec):
    """Everything the surface says the chart hands the browser."""
    model = surface.TradingViewChartModel(spec["symbol"], spec["theme"])
    first_html = model.html
    model.set_candles(spec["candles"])
    model.update_candle(spec["candle"])
    model.set_bollinger_bands(spec["bands"])
    model.add_trade_marker(*spec["marker"])
    model.set_grid_levels(spec["levels"])
    calls = model.calls
    shown = {
        "accessible_name": surface.WIDGET_ACCESSIBLE_NAME,
        "symbol": model.symbol,
        "theme": model.theme,
        "html": first_html,
        "html_sha": hashlib.sha256(first_html.encode("utf-8")).hexdigest(),
        "margins_px": list(surface.PAGE["margins_px"]),
        "child_count": len(surface.PAGE["children"]),
        "child_is_the_web_view": surface.PAGE["children"][0] == "web_view",
        "page_count": 1,
        "calls": calls,
        "call_count": len(calls),
    }
    switched = model.set_theme(spec["switch_to"])
    shown["theme_after_switch"] = model.theme
    shown["html_after_switch"] = switched
    shown["html_after_switch_sha"] = hashlib.sha256(
        switched.encode("utf-8")
    ).hexdigest()
    shown["page_count_after_switch"] = 2
    shown["calls_after_switch"] = model.calls
    return shown


def both_displays(spec):
    """Drive both sides with one case in one call."""
    return old_display(spec), new_display(spec)


def outcome(work):
    """What one side did with an input: answered with what, or refused."""
    try:
        return ("answered", work())
    except Exception as exc:
        return ("refused", type(exc).__name__)


# ---------------------------------------------------------------------
# The enumeration: every item on one side has a counterpart
# ---------------------------------------------------------------------

SHIPPED_CLASSES = ("TradingViewChart",)

SHIPPED_MEMBERS = {
    "TradingViewChart": (
        "__init__",
        "_setup_ui",
        "set_candles",
        "update_candle",
        "set_bollinger_bands",
        "add_trade_marker",
        "set_grid_levels",
        "set_theme",
        "_run_js",
    ),
}

COUNTERPARTS = {
    "TradingViewChart": "TradingViewChartModel",
    "TradingViewChart.__init__": "TradingViewChartModel.__init__",
    "TradingViewChart._setup_ui": "page_html",
    "TradingViewChart.set_candles": "TradingViewChartModel.set_candles",
    "TradingViewChart.update_candle": "TradingViewChartModel.update_candle",
    "TradingViewChart.set_bollinger_bands": (
        "TradingViewChartModel.set_bollinger_bands"
    ),
    "TradingViewChart.add_trade_marker": "TradingViewChartModel.add_trade_marker",
    "TradingViewChart.set_grid_levels": "TradingViewChartModel.set_grid_levels",
    "TradingViewChart.set_theme": "TradingViewChartModel.set_theme",
    "TradingViewChart._run_js": "TradingViewChartModel.run_js",
}

SURFACE_FUNCTIONS = (
    "theme_colors",
    "page_colors",
    "page_html",
    "call_text",
    "marker_payload",
    "marker_position",
    "marker_color",
    "marker_shape",
    "grid_line_color",
    "volume_bar_color",
    "button_class",
    "buttons",
    "build_view_model",
    "view_model",
)

SURFACE_CLASSES = ("TradingViewChartModel",)

SURFACE_MODEL_MEMBERS = (
    "__init__",
    "symbol",
    "theme",
    "html",
    "calls",
    "run_js",
    "set_candles",
    "update_candle",
    "set_bollinger_bands",
    "add_trade_marker",
    "set_grid_levels",
    "set_theme",
)


def shipped_definitions():
    """Every class the shipped module itself defines."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def shipped_callables():
    """Every method the shipped module itself defines, as Class.name."""
    import inspect

    found = set()
    for name in shipped_definitions():
        holder = getattr(shipped, name)
        for member, value in vars(holder).items():
            if inspect.isfunction(value):
                found.add(f"{name}.{member}")
    return found


def test_the_shipped_classes_each_have_a_counterpart():
    """A class on the shipped side has nothing standing for it."""
    defined = shipped_definitions()
    assert defined == set(SHIPPED_CLASSES), defined
    assert len(defined) == 1
    for name in SHIPPED_CLASSES:
        assert name in COUNTERPARTS, name
        assert hasattr(surface, COUNTERPARTS[name].split(".")[0]), name


def test_the_shipped_methods_each_have_a_counterpart():
    """A method on the shipped side has nothing standing for it."""
    found = shipped_callables()
    expected = {
        f"{holder}.{member}"
        for holder, members in SHIPPED_MEMBERS.items()
        for member in members
    }
    assert found == expected, found
    assert len(found) == SHIPPED_METHOD_TOTAL
    for name in found:
        assert name in COUNTERPARTS, name
        assert hasattr(surface, COUNTERPARTS[name].split(".")[0]), name
    assert len(COUNTERPARTS) == len(SHIPPED_CLASSES) + SHIPPED_METHOD_TOTAL


def test_the_definition_counter_can_see_a_definition():
    """The counter reported none because it can never report one."""
    import inspect

    from src.gui.main_tabs import table_cells_surface as neighbour

    defined = {
        name
        for name, value in vars(neighbour).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == neighbour.__name__
    }
    assert len(defined) > 0, "the counter cannot see a definition anywhere"
    assert "TableCellsModel" in defined
    assert shipped_callables(), "the method counter cannot see a method"


def test_the_surface_functions_are_reachable_and_described():
    """A named helper is missing, or carries no description."""
    import inspect

    found = {
        name
        for name, value in vars(surface).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == surface.__name__
    }
    assert found == set(SURFACE_FUNCTIONS), found
    assert len(SURFACE_FUNCTIONS) == SURFACE_FUNCTION_TOTAL
    for name in SURFACE_FUNCTIONS:
        member = getattr(surface, name)
        assert callable(member), name
        assert (member.__doc__ or "").strip(), name
    classes = {
        name
        for name, value in vars(surface).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == surface.__name__
    }
    assert classes == set(SURFACE_CLASSES)
    for member in SURFACE_MODEL_MEMBERS:
        assert hasattr(surface.TradingViewChartModel, member), member
    assert len(SURFACE_MODEL_MEMBERS) == 12
    with pytest.raises(AttributeError):
        surface.no_such_helper()


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    shipped_text = SHIPPED_PATH.read_text(encoding="utf-8")
    surface_text = SURFACE_PATH.read_text(encoding="utf-8")
    assert shipped_text.count(".connect(") == 0
    assert surface_text.count(".connect(") == 0
    assert len(surface.ACTIONS) == shipped_text.count(".connect(")
    assert len(surface.ACTIONS) == surface_text.count(".connect(")
    wired = WIRED_CONNECT_PATH.read_text(encoding="utf-8")
    assert wired.count(".connect(") > 0, "the counter cannot report a wiring"


def test_the_chart_declares_no_timer_and_no_bus_topic():
    """The surface gained behaviour the chart it replaces never had."""
    from src.gui.main_tabs import console_tab_surface as neighbour

    shipped_text = SHIPPED_PATH.read_text(encoding="utf-8")
    assert shipped_text.count("QTimer") == 0
    assert shipped_text.count(".subscribe(") == 0
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert surface.BUS_TOPICS == ()
    assert surface.SKIN == {}
    payload = surface.build_view_model()
    assert payload["timers"] == {}
    assert payload["timer_delays_ms"] == []
    assert payload["bus_topics"] == []
    assert payload["skin"] == {}
    assert payload["actions"] == {}
    timer_neighbour = WIRED_TIMER_PATH.read_text(encoding="utf-8")
    bus_neighbour = WIRED_BUS_PATH.read_text(encoding="utf-8")
    assert timer_neighbour.count("QTimer") > 0, "the timer counter cannot report"
    assert bus_neighbour.count(".subscribe(") > 0, "the bus counter cannot report"
    assert len(neighbour.TIMERS) > 0, "the surface timer counter cannot report"


def test_the_chart_builds_whatever_the_module_names_as_the_browser():
    """The chart holds a browser widget the module does not name.

    Swapping the module's own name changes what the chart builds, which
    is what makes the recording widget a fair stand-in everywhere else.
    """
    assert shipped.QWebEngineView.__name__ == "QWebEngineView"
    with recording_web_view():
        chart = old_chart()
        assert type(chart._web) is shipped.QWebEngineView
        assert type(chart._web).__name__ == "RecordingWebView"
        assert chart.layout().itemAt(0).widget() is chart._web
    assert shipped.QWebEngineView.__name__ == "QWebEngineView"


# ---------------------------------------------------------------------
# The two sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_case_reads_the_same_on_both_sides(name):
    """The surface answers a case differently than the shipped chart."""
    old, new = both_displays(CASES[name])
    assert set(old) == set(new), (sorted(old), sorted(new))
    for key in sorted(old):
        assert old[key] == new[key], (name, key, old[key], new[key])


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_case_hashes_the_same_on_both_sides(name):
    """The two sides differ in a value no direct comparison reads."""
    old, new = both_displays(CASES[name])
    assert digest(old) == digest(new), (name, digest(old), digest(new))


def test_the_sample_hashes_are_reported():
    """The hashes quoted in the report are not the ones the code makes."""
    samples = {}
    for name in ("happy", "empty_data", "unicode_symbol"):
        old, new = both_displays(CASES[name])
        assert digest(old) == digest(new), name
        samples[name] = digest(old)
    assert len(set(samples.values())) == 3, samples
    for value in samples.values():
        assert len(value) == 64


def test_the_hash_can_report_a_difference():
    """The hash returns one value whatever it is given.

    Two real cases, one taken from each side. A pass proves the hash
    tells two answers apart, so the matches above are not green by
    being unable to fail.
    """
    old = old_display(CASES["happy"])
    new = new_display(CASES["every_theme_neon"])
    assert digest(old) != digest(new)
    assert old["html"] != new["html"]
    assert old["html_sha"] != new["html_sha"]


def test_the_page_hash_tells_two_symbols_apart():
    """One page hash for two different symbols."""
    one = old_display(CASES["happy"])
    other = old_display(CASES["unicode_symbol"])
    assert one["html_sha"] != other["html_sha"]
    assert new_display(CASES["happy"])["html_sha"] == one["html_sha"]


@pytest.mark.parametrize("name", sorted(REFUSALS))
def test_both_sides_refuse_the_same_input_the_same_way(name):
    """One side answered an input the other refused."""
    method, payload = REFUSALS[name]
    with recording_web_view():
        chart = old_chart()
        old = outcome(lambda: getattr(chart, method)(payload))
    model = surface.TradingViewChartModel()
    new = outcome(lambda: getattr(model, method)(payload))
    assert old == new, (name, old, new)
    assert old[0] == "refused", (name, old)
    assert old[1] == "TypeError", (name, old)


def test_an_unhashable_theme_is_refused_the_same_way_on_both_sides():
    """One side fell back where the other refused."""
    with recording_web_view():
        old = outcome(lambda: old_chart("BTC/USDT", ["not", "a", "name"]))
    new = outcome(lambda: surface.TradingViewChartModel("BTC/USDT", ["a", "list"]))
    assert old == new, (old, new)
    assert old == ("refused", "TypeError")


def test_the_outcomes_hold_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the set proves nothing."""
    kinds = set()
    with recording_web_view():
        chart = old_chart()
        kinds.add(outcome(lambda: chart.set_candles(BASE_CANDLES))[0])
        kinds.add(outcome(lambda: chart.set_candles({1, 2}))[0])
    model = surface.TradingViewChartModel()
    kinds.add(outcome(lambda: model.set_candles(BASE_CANDLES))[0])
    kinds.add(outcome(lambda: model.set_candles({1, 2}))[0])
    assert kinds == {"answered", "refused"}, kinds


# ---------------------------------------------------------------------
# The page, the themes, the buttons and the calls, read off both sides
# ---------------------------------------------------------------------


def test_the_two_sides_hold_one_page_template():
    """The surface holds a different page than the shipped chart."""
    assert surface.CHART_HTML == shipped.CHART_HTML
    assert surface.CHART_HTML.count("%(bg)s") == 3
    assert surface.CHART_HTML.count("%(symbol)s") == 1
    for key in EXPECTED_THEME_KEYS:
        assert "%%(%s)s" % key in surface.CHART_HTML, key
    assert "%(symbol)s" in surface.CHART_HTML


@pytest.mark.parametrize("theme", sorted(EXPECTED_THEMES))
def test_every_theme_matches_value_for_value(theme):
    """A theme colour moved on one side alone."""
    assert surface.CHART_THEMES[theme] == EXPECTED_THEMES[theme]
    assert shipped.CHART_THEMES[theme] == EXPECTED_THEMES[theme]
    assert surface.CHART_THEMES[theme] == shipped.CHART_THEMES[theme]
    assert sorted(surface.CHART_THEMES[theme]) == sorted(EXPECTED_THEME_KEYS)


def test_the_theme_table_holds_five_themes_in_one_order():
    """A theme was added, dropped or reordered on one side alone."""
    assert list(surface.CHART_THEMES) == list(EXPECTED_THEME_ORDER)
    assert list(shipped.CHART_THEMES) == list(EXPECTED_THEME_ORDER)
    assert surface.THEME_ORDER == EXPECTED_THEME_ORDER
    assert len(surface.CHART_THEMES) == THEME_TOTAL
    assert surface.THEME_KEYS == EXPECTED_THEME_KEYS
    assert len(surface.THEME_KEYS) == THEME_KEY_TOTAL


@pytest.mark.parametrize("theme", sorted(EXPECTED_THEMES))
def test_both_sides_build_one_page_for_one_theme(theme):
    """The page one theme produces differs between the two sides."""
    old = old_display(case(theme=theme))
    new = new_display(case(theme=theme))
    assert old["html"] == new["html"], theme
    assert old["html_sha"] == new["html_sha"], theme
    for value in EXPECTED_THEMES[theme].values():
        assert value in new["html"], (theme, value)


def test_an_unknown_theme_falls_back_the_same_way_on_both_sides():
    """One side fell back to a different theme than the other."""
    old = old_display(case(theme="no_such_theme"))
    new = new_display(case(theme="no_such_theme"))
    assert old["html"] == new["html"]
    assert surface.theme_colors("no_such_theme") == dict(
        EXPECTED_THEMES[EXPECTED_DEFAULT_THEME]
    )
    assert surface.FALLBACK_THEME == EXPECTED_DEFAULT_THEME
    assert EXPECTED_THEMES["cyberpunk_dark"]["bg"] in new["html"]
    assert EXPECTED_THEMES["neon_light"]["bg"] not in new["html"]


def test_the_theme_helper_answers_for_a_known_and_an_unknown_name():
    """The fallback fires for every name, or for none."""
    known = surface.theme_colors("glass_metal")
    unknown = surface.theme_colors("glass metal")
    assert known == EXPECTED_THEMES["glass_metal"]
    assert unknown == EXPECTED_THEMES["cyberpunk_dark"]
    assert known != unknown


def test_the_theme_helper_hands_back_a_copy():
    """The helper handed back the table's own row, so a caller can edit it."""
    first = surface.theme_colors("neon_light")
    first["bg"] = "#000000"
    assert surface.CHART_THEMES["neon_light"]["bg"] == "#f5f5fa"
    assert surface.theme_colors("neon_light")["bg"] == "#f5f5fa"


@pytest.mark.parametrize("index", range(BUTTON_TOTAL))
def test_every_timeframe_button_carries_the_shipped_label_and_value(index):
    """A timeframe button changed its label, its value or its state."""
    label, value, active = EXPECTED_BUTTONS[index]
    made = surface.buttons()[index]
    assert made["label"] == label
    assert made["value"] == value
    assert made["active"] is active
    assert made["enabled"] is True
    assert "onclick=\"setTimeframe('%s')\">%s<" % (value, label) in surface.CHART_HTML
    assert "onclick=\"setTimeframe('%s')\">%s<" % (value, label) in shipped.CHART_HTML


def test_the_buttons_come_back_in_one_order_with_one_active():
    """The buttons were reordered, or none of them starts active."""
    made = surface.buttons()
    assert len(made) == BUTTON_TOTAL
    assert [one["label"] for one in made] == [one[0] for one in EXPECTED_BUTTONS]
    assert [one["value"] for one in made] == [one[1] for one in EXPECTED_BUTTONS]
    active = [one for one in made if one["active"]]
    assert len(active) == 1
    assert active[0]["value"] == "60"
    assert active[0]["label"] == "1H"
    assert active[0]["class_name"] == "tf-btn active"
    assert made[0]["class_name"] == "tf-btn"
    assert surface.CHART_HTML.count('class="tf-btn active"') == 1
    assert shipped.CHART_HTML.count('class="tf-btn active"') == 1
    assert surface.CHART_HTML.count('class="tf-btn"') == BUTTON_TOTAL - 1


def test_another_button_can_be_marked_active():
    """The active button is fixed whatever the caller asks for."""
    made = surface.buttons("D")
    active = [one for one in made if one["active"]]
    assert len(active) == 1
    assert active[0]["label"] == "1D"
    assert surface.buttons("no_such_value") == [
        dict(one, active=False, class_name="tf-btn")
        for one in surface.TIMEFRAME_BUTTONS
    ]
    assert surface.button_class(True) == "tf-btn active"
    assert surface.button_class(False) == "tf-btn"


@pytest.mark.parametrize("name", sorted(EXPECTED_CALL_FORMATS))
def test_every_call_into_the_page_matches_on_both_sides(name):
    """A call into the page is spelled differently on the two sides."""
    assert surface.CALL_FORMATS[name] == EXPECTED_CALL_FORMATS[name]
    old = old_display(CASES["happy"])
    new = new_display(CASES["happy"])
    index = list(surface.CALL_ORDER).index(name)
    assert old["calls"][index] == new["calls"][index], name
    assert old["calls"][index].startswith(
        EXPECTED_CALL_FORMATS[name].split("(")[0] + "('"
    )


def test_the_five_calls_arrive_in_one_order():
    """A call was dropped, added or reordered on one side."""
    old, new = both_displays(CASES["happy"])
    assert old["call_count"] == CALL_TOTAL
    assert new["call_count"] == CALL_TOTAL
    assert list(surface.CALL_ORDER) == [
        "set_candles",
        "update_candle",
        "set_bollinger_bands",
        "add_trade_marker",
        "set_grid_levels",
    ]
    names = [one.split("(")[0] for one in new["calls"]]
    assert names == [
        "setCandles",
        "updateCandle",
        "setBollingerBands",
        "addTradeMarker",
        "setGridLevels",
    ]
    assert old["calls"] == new["calls"]


def test_a_trade_marker_carries_the_same_three_values():
    """A trade marker lost a value, or gained one."""
    assert surface.MARKER_FIELDS == ("time", "side", "amount")
    made = surface.marker_payload(7, "sell", 2.5)
    assert made == {"time": 7, "side": "sell", "amount": 2.5}
    assert list(made) == list(surface.MARKER_FIELDS)
    with recording_web_view():
        chart = old_chart()
        chart.add_trade_marker(7, "sell", 2.5)
        old_call = chart._web.js[-1]
    model = surface.TradingViewChartModel()
    model.add_trade_marker(7, "sell", 2.5)
    assert old_call == model.calls[-1]
    assert old_call == "addTradeMarker('%s')" % json.dumps(made)


def test_a_payload_is_quoted_the_same_way_on_both_sides():
    """The JSON inside the call is quoted differently on the two sides."""
    with recording_web_view():
        chart = old_chart()
        chart.set_candles(BASE_CANDLES)
        old_call = chart._web.js[-1]
    model = surface.TradingViewChartModel()
    model.set_candles(BASE_CANDLES)
    assert old_call == model.calls[-1]
    assert old_call.startswith("setCandles('[")
    assert old_call.endswith("]')")
    assert json.loads(old_call[len("setCandles('") : -len("')")]) == BASE_CANDLES


def test_the_call_helper_refuses_a_name_it_does_not_know():
    """An unknown call name was answered instead of refused."""
    assert surface.call_text("set_candles", []) == "setCandles('[]')"
    with pytest.raises(KeyError):
        surface.call_text("noSuchCall", [])


# ---------------------------------------------------------------------
# The values around the page: series, markers, grid lines, layout
# ---------------------------------------------------------------------


def test_the_candle_series_colours_match_on_both_sides():
    """A candle colour moved on one side alone."""
    assert surface.CANDLE_SERIES == EXPECTED_CANDLE_SERIES
    for value in set(EXPECTED_CANDLE_SERIES.values()):
        assert value in shipped.CHART_HTML, value
        assert value in surface.CHART_HTML, value
    assert shipped.CHART_HTML.count("upColor: '#00ff88'") == 1
    assert surface.CHART_HTML.count("upColor: '#00ff88'") == 1


def test_the_volume_series_settings_match_on_both_sides():
    """A volume setting moved on one side alone."""
    assert surface.VOLUME_SERIES == EXPECTED_VOLUME_SERIES
    assert "color: '#26a69a'" in surface.CHART_HTML
    assert "scaleMargins: { top: 0.85, bottom: 0 }" in surface.CHART_HTML
    assert "scaleMargins: { top: 0.85, bottom: 0 }" in shipped.CHART_HTML
    assert surface.volume_bar_color(1.0, 1.0) == "rgba(0, 255, 136, 0.3)"
    assert surface.volume_bar_color(1.0, 2.0) == "rgba(0, 255, 136, 0.3)"
    assert surface.volume_bar_color(2.0, 1.0) == "rgba(255, 51, 102, 0.3)"


def test_the_bollinger_settings_match_on_both_sides():
    """A Bollinger line changed colour, width or style."""
    assert surface.BOLLINGER_SERIES == EXPECTED_BOLLINGER_SERIES
    assert surface.BOLLINGER_SERIES["upper_color"] == (
        surface.BOLLINGER_SERIES["lower_color"]
    )
    assert surface.BOLLINGER_SERIES["middle_color"] != (
        surface.BOLLINGER_SERIES["upper_color"]
    )
    assert shipped.CHART_HTML.count("rgba(0, 170, 255, 0.4)") == 2
    assert surface.CHART_HTML.count("rgba(0, 170, 255, 0.4)") == 2
    assert surface.CHART_HTML.count("rgba(0, 170, 255, 0.2)") == 1


def test_the_marker_skin_answers_both_ways():
    """A buy and a sell marker read the same, so the side is lost."""
    assert surface.MARKER_SKIN == EXPECTED_MARKER_SKIN
    assert surface.marker_position("buy") == "belowBar"
    assert surface.marker_position("sell") == "aboveBar"
    assert surface.marker_position("HOLD") == "aboveBar"
    assert surface.marker_color("buy") == "#00ff88"
    assert surface.marker_color("sell") == "#ff3366"
    assert surface.marker_shape("buy") == "arrowUp"
    assert surface.marker_shape("sell") == "arrowDown"
    assert surface.marker_color("buy") != surface.marker_color("sell")
    assert surface.marker_shape("buy") != surface.marker_shape("sell")


def test_the_grid_line_skin_answers_both_ways():
    """A buy and a sell grid line read the same, so the side is lost."""
    assert surface.GRID_LINE_SKIN == EXPECTED_GRID_LINE_SKIN
    assert surface.grid_line_color("buy") == "rgba(0, 255, 136, 0.15)"
    assert surface.grid_line_color("sell") == "rgba(255, 51, 102, 0.15)"
    assert surface.grid_line_color("anything") == "rgba(255, 51, 102, 0.15)"
    assert surface.grid_line_color("buy") != surface.grid_line_color("sell")
    assert surface.GRID_LEVEL_FIELDS == ("price", "side", "level")


def test_the_grid_lines_are_never_cleared_before_they_are_drawn():
    """The chart clears old grid lines, so the declared value is wrong."""
    assert surface.GRID_LINE_SKIN["cleared_before_draw"] is False
    assert "removePriceLine" not in shipped.CHART_HTML
    assert "removePriceLine" not in surface.CHART_HTML
    assert shipped.CHART_HTML.count("createPriceLine") == 1


def test_the_watermark_and_the_time_scale_match_on_both_sides():
    """The watermark or the time scale changed on one side alone."""
    assert surface.WATERMARK == {
        "visible": True,
        "font_size_px": 48,
        "text_source": "symbol",
    }
    assert surface.TIME_SCALE == {"time_visible": True, "seconds_visible": False}
    assert "fontSize: 48," in shipped.CHART_HTML
    assert "fontSize: 48," in surface.CHART_HTML
    assert "secondsVisible: false," in surface.CHART_HTML


def test_the_toolbar_and_the_button_skin_match_on_both_sides():
    """A toolbar or button layout number changed on one side alone."""
    assert surface.TOOLBAR == {
        "position": "absolute",
        "top_px": 8,
        "right_px": 8,
        "z_index": 10,
        "display": "flex",
        "gap_px": 6,
    }
    assert surface.BUTTON_SKIN["padding_px"] == [4, 10]
    assert surface.BUTTON_SKIN["radius_px"] == 4
    assert surface.BUTTON_SKIN["font_size_px"] == 12
    assert surface.BUTTON_SKIN["border_width_px"] == 1
    assert surface.BUTTON_SKIN["cursor"] == "pointer"
    assert surface.BUTTON_SKIN["handler"] == "setTimeframe"
    assert "top: 8px; right: 8px; z-index: 10;" in shipped.CHART_HTML
    assert "padding: 4px 10px; border-radius: 4px;" in shipped.CHART_HTML
    assert "gap: 6px;" in shipped.CHART_HTML


def test_the_page_layout_matches_on_both_sides():
    """The chart holds its browser widget in a different frame."""
    old = old_display(CASES["happy"])
    assert old["margins_px"] == EXPECTED_PAGE_MARGINS
    assert surface.PAGE["margins_px"] == EXPECTED_PAGE_MARGINS
    assert surface.PAGE["children"] == ["web_view"]
    assert surface.PAGE["layout"] == "vertical"
    assert old["child_count"] == 1
    assert old["child_is_the_web_view"] is True


def test_the_page_names_the_same_charting_library_on_both_sides():
    """The page asks for a different charting library than it did."""
    assert surface.SCRIPT_URL == EXPECTED_SCRIPT_URL
    assert EXPECTED_SCRIPT_URL in shipped.CHART_HTML
    assert EXPECTED_SCRIPT_URL in surface.CHART_HTML
    assert surface.WEB_VIEW["script_url"] == EXPECTED_SCRIPT_URL
    assert surface.WEB_VIEW["carries_script"] is False
    assert surface.CHART_HTML.count("<script src=") == 1
    assert shipped.CHART_HTML.count("<script src=") == 1


def test_the_page_calls_back_through_the_same_bridge_name():
    """The page calls back into a different object than it did."""
    assert surface.BRIDGE_OBJECT == "qtBridge"
    assert surface.BRIDGE_CALLBACK == "timeframeChanged"
    assert "window.qtBridge.timeframeChanged(tf);" in shipped.CHART_HTML
    assert "window.qtBridge.timeframeChanged(tf);" in surface.CHART_HTML


def test_the_missing_browser_warning_matches_on_both_sides():
    """The message shown with no browser installed changed."""
    assert surface.MISSING_WEBENGINE_WARNING == EXPECTED_MISSING_WARNING
    assert surface.LOGGER_NAME == EXPECTED_LOGGER_NAME
    assert shipped.logger.name == EXPECTED_LOGGER_NAME
    payload = surface.build_view_model()
    assert payload["missing_webengine_warning"] == EXPECTED_MISSING_WARNING
    assert payload["logger_name"] == EXPECTED_LOGGER_NAME


def test_the_defaults_match_on_both_sides():
    """A default symbol or theme changed on one side alone."""
    import inspect

    signature = inspect.signature(shipped.TradingViewChart.__init__)
    assert signature.parameters["symbol"].default == EXPECTED_DEFAULT_SYMBOL
    assert signature.parameters["theme"].default == EXPECTED_DEFAULT_THEME
    assert signature.parameters["parent"].default is None
    assert surface.DEFAULT_SYMBOL == EXPECTED_DEFAULT_SYMBOL
    assert surface.DEFAULT_THEME == EXPECTED_DEFAULT_THEME
    model = surface.TradingViewChartModel()
    assert model.symbol == EXPECTED_DEFAULT_SYMBOL
    assert model.theme == EXPECTED_DEFAULT_THEME


def test_the_model_keeps_every_call_it_made():
    """The model forgot a call, or handed back its own list."""
    model = surface.TradingViewChartModel()
    assert model.calls == []
    model.set_candles([])
    held = model.calls
    held.append("setCandles('[]')")
    assert len(model.calls) == 1
    assert model.calls == ["setCandles('[]')"]


def test_switching_the_theme_replaces_the_whole_page():
    """A theme switch left the page or the calls as they were."""
    old, new = both_displays(CASES["happy"])
    assert old["page_count"] == 1
    assert old["page_count_after_switch"] == 2
    assert new["page_count_after_switch"] == 2
    assert old["html"] != old["html_after_switch"]
    assert new["html"] != new["html_after_switch"]
    assert old["html_after_switch"] == new["html_after_switch"]
    assert old["theme_after_switch"] == "neon_light"
    assert new["theme_after_switch"] == "neon_light"
    assert old["calls_after_switch"] == old["calls"]
    assert new["calls_after_switch"] == new["calls"]


def test_switching_the_theme_keeps_the_symbol_on_both_sides():
    """A theme switch dropped the symbol from the page."""
    spec = case(symbol="ETH/USD", switch_to="glass_metal")
    old = old_display(spec)
    new = new_display(spec)
    assert "ETH/USD" in old["html_after_switch"]
    assert "ETH/USD" in new["html_after_switch"]
    assert old["html_after_switch"] == new["html_after_switch"]
    assert old["symbol"] == "ETH/USD"
    assert new["symbol"] == "ETH/USD"


def test_the_shipped_chart_writes_the_symbol_into_its_theme_table():
    """The shipped defect this surface does not copy is gone.

    The shipped chart adds the symbol to the shared theme row it reads.
    The surface works on a copy. Both hand the browser one page, which
    is what this proves.
    """
    assert "symbol" not in shipped.CHART_THEMES["cyberpunk_dark"]
    with recording_web_view():
        chart = old_chart("XRP/USD", "cyberpunk_dark")
        page = chart._web.html[-1]
    assert shipped.CHART_THEMES["cyberpunk_dark"]["symbol"] == "XRP/USD"
    assert "symbol" not in surface.CHART_THEMES["cyberpunk_dark"]
    assert surface.page_html("XRP/USD", "cyberpunk_dark") == page


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------


def font_note():
    """Which font answer this host gave, carried into a failure message."""
    return "real fonts" if has_real_fonts() else "no fonts"


def old_swatch_payload(theme):
    """The nine values the shipped chart filled its page from, stamped."""
    with recording_web_view():
        chart = old_chart(SWATCH_SYMBOL, theme)
        assert chart._web.html, "the shipped chart set no page"
    return sealed(dict(shipped.CHART_THEMES[theme]))


def new_swatch_payload(theme):
    """The nine values the surface fills the page from, stamped."""
    return sealed(surface.page_colors(SWATCH_SYMBOL, theme))


def build_swatch(payload):
    """A panel painted from the nine values one side handed over.

    Every colour the page uses reaches a pixel here: three as painted
    grounds, two as glyph colours and the frame border as itself. A
    payload changed after it came off a side is refused.
    """
    payload = unaltered(payload)
    from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

    frame = QFrame()
    frame.setStyleSheet(
        "QFrame { background: %s; border: 1px solid %s; }"
        % (payload["bg"], payload["border"])
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(6, 6, 6, 6)
    layout.setSpacing(4)
    for text, color in (
        (payload["symbol"], payload["text"]),
        (payload["watermark"], payload["accent"]),
    ):
        label = QLabel(str(text), frame)
        label.setStyleSheet("QLabel { color: %s; border: none; }" % color)
        layout.addWidget(label)
    for band in ("btn_bg", "btn_hover", "grid"):
        strip = QLabel("", frame)
        strip.setFixedHeight(12)
        strip.setStyleSheet("QLabel { background: %s; border: none; }" % payload[band])
        layout.addWidget(strip)
    HELD.append(frame)
    return frame


@pytest.mark.parametrize("theme", sorted(EXPECTED_THEMES))
def test_the_two_sides_paint_one_swatch(theme):
    """The surface painted a different theme than the shipped chart."""
    app()
    assert_pictures_match(
        old_side=render_offscreen(build_swatch(old_swatch_payload(theme)), SWATCH_SIZE),
        new_side=render_offscreen(build_swatch(new_swatch_payload(theme)), SWATCH_SIZE),
        note="%s, %s" % (theme, font_note()),
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real themes, one taken from each side. A pass proves the
    comparison reports a panel painted differently, so the matches
    above are not green by being unable to fail.
    """
    app()
    assert_pictures_differ(
        old_side=render_offscreen(
            build_swatch(old_swatch_payload("cyberpunk_dark")), SWATCH_SIZE
        ),
        new_side=render_offscreen(
            build_swatch(new_swatch_payload("neon_light")), SWATCH_SIZE
        ),
        note="a dark theme against a light one, %s" % font_note(),
    )


def test_the_picture_comparison_reports_one_changed_colour():
    """A single changed colour paints the same picture."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(
            build_swatch(old_swatch_payload("cyberpunk_dark")), SWATCH_SIZE
        ),
        new_side=render_offscreen(
            build_swatch(new_swatch_payload("glass_metal")), SWATCH_SIZE
        ),
        note="two dark themes, %s" % font_note(),
    )


@pytest.mark.parametrize("theme", sorted(EXPECTED_THEMES))
def test_the_painted_swatch_shows_more_than_one_colour(theme):
    """The two sides matched because the panel painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    image = render_offscreen(build_swatch(new_swatch_payload(theme)), SWATCH_SIZE)
    assert image.height() == SWATCH_SIZE[1]
    assert image.width() >= SWATCH_SIZE[0], image.width()
    wider = render_offscreen(
        build_swatch(new_swatch_payload(theme)), (SWATCH_SIZE[0] * 3, SWATCH_SIZE[1])
    )
    assert wider.width() > image.width(), "the requested width reaches no render"
    seen = set()
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            seen.add(QColor(image.pixelColor(x, y)).name())
    assert len(seen) > 2, f"the panel painted {len(seen)} colours on {theme}"


def test_a_payload_the_test_changed_is_refused_by_the_builder():
    """A changed payload reached a render, which measures the host."""
    payload = new_swatch_payload("neon_light")
    payload["bg"] = "#000000"
    with pytest.raises(AssertionError) as reported:
        build_swatch(payload)
    assert "altered after it came off" in str(reported.value)
    payload["bg"] = EXPECTED_THEMES["neon_light"]["bg"]
    assert build_swatch(payload) is not None


def test_a_payload_the_test_built_itself_is_refused_by_the_builder():
    """A payload from neither side reached a render."""
    with pytest.raises(AssertionError) as reported:
        build_swatch(dict(EXPECTED_THEMES["neon_light"], symbol=SWATCH_SYMBOL))
    assert "never came off" in str(reported.value)


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on.

    With no font database every family resolves to a box advancing one
    em per character, so two strings of equal length need equal width.
    With a font database the glyphs decide the width. Both answers are
    handled here and this file is run both ways.
    """
    app()
    from PySide6.QtWidgets import QLabel

    narrow = QLabel("iiii")
    wide = QLabel("WWWW")
    HELD.extend([narrow, wide])
    if has_real_fonts():
        assert (
            narrow.sizeHint().width() != wide.sizeHint().width()
        ), "the host reports fonts and every glyph still has one width"
    else:
        assert (
            narrow.sizeHint().width() == wide.sizeHint().width()
        ), "the host reports no fonts and the glyphs still have their own widths"


# ---------------------------------------------------------------------
# What no picture can report, each read off both sides instead
# ---------------------------------------------------------------------

BLIND_TO_THE_PICTURE = {
    "page_text": "test_both_sides_build_one_page_for_one_theme",
    "page_template": "test_the_two_sides_hold_one_page_template",
    "script_url": "test_the_page_names_the_same_charting_library_on_both_sides",
    "accessible_name": "test_the_accessible_name_is_compared_as_text",
    "page_margins": "test_the_page_layout_matches_on_both_sides",
    "call_formats": "test_every_call_into_the_page_matches_on_both_sides",
    "call_order": "test_the_five_calls_arrive_in_one_order",
    "marker_fields": "test_a_trade_marker_carries_the_same_three_values",
    "marker_sides": "test_the_marker_skin_answers_both_ways",
    "grid_line_sides": "test_the_grid_line_skin_answers_both_ways",
    "button_values": "test_every_timeframe_button_carries_the_shipped_label_and_value",
    "active_button": "test_the_buttons_come_back_in_one_order_with_one_active",
    "watermark_colour": "test_the_watermark_is_compared_as_text_not_as_a_pixel",
    "equal_channel_colours": "test_the_colours_with_equal_channels_are_compared_as_text",
    "repeated_colours": "test_the_colours_two_names_share_are_compared_by_name",
    "json_quoting": "test_a_payload_is_quoted_the_same_way_on_both_sides",
    "bridge_callback": "test_the_page_calls_back_through_the_same_bridge_name",
    "missing_browser_warning": "test_the_missing_browser_warning_matches_on_both_sides",
    "series_colours": "test_the_candle_series_colours_match_on_both_sides",
    "volume_settings": "test_the_volume_series_settings_match_on_both_sides",
    "bollinger_settings": "test_the_bollinger_settings_match_on_both_sides",
    "toolbar_numbers": "test_the_toolbar_and_the_button_skin_match_on_both_sides",
    "defaults": "test_the_defaults_match_on_both_sides",
    "theme_fallback": "test_an_unknown_theme_falls_back_the_same_way_on_both_sides",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report.

    The shipped chart paints nothing itself: a browser draws the page
    from the text below. Twenty-four things reach no Qt pixel at all,
    each named here with the check that does cover it.
    """
    assert len(BLIND_TO_THE_PICTURE) == 24
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert len(set(BLIND_TO_THE_PICTURE.values())) == 24


def test_the_blind_list_can_report_a_name_no_test_backs():
    """The blind list passed because it looks at nothing."""
    invented = "test_no_such_check_exists"
    assert invented not in BLIND_TO_THE_PICTURE.values()
    assert invented not in globals()
    assert "test_the_page_layout_matches_on_both_sides" in globals()


def test_the_accessible_name_is_compared_as_text():
    """A name assistive software reads changed and no pixel moved."""
    with recording_web_view():
        chart = old_chart()
        assert chart.accessibleName() == EXPECTED_ACCESSIBLE_NAME
    assert surface.WIDGET_ACCESSIBLE_NAME == EXPECTED_ACCESSIBLE_NAME
    assert surface.build_view_model()["accessible_name"] == EXPECTED_ACCESSIBLE_NAME


def test_the_watermark_is_compared_as_text_not_as_a_pixel():
    """A watermark colour changed and no pixel could show it.

    The watermark colours carry an alpha of 0.07, which a Qt style
    sheet reads as fully transparent, so no render can report them.
    """
    for theme, values in EXPECTED_THEMES.items():
        assert surface.CHART_THEMES[theme]["watermark"] == values["watermark"]
        assert shipped.CHART_THEMES[theme]["watermark"] == values["watermark"]
        assert values["watermark"].startswith("rgba(")
        assert values["watermark"].endswith(")")
    assert len({one["watermark"] for one in EXPECTED_THEMES.values()}) == THEME_TOTAL


@pytest.mark.parametrize("spot", sorted(EQUAL_CHANNEL_COLORS))
def test_the_colours_with_equal_channels_are_compared_as_text(spot):
    """A colour whose channels are equal changed and no pixel moved."""
    theme, key = spot
    expected = EQUAL_CHANNEL_COLORS[spot]
    assert surface.CHART_THEMES[theme][key] == expected
    assert shipped.CHART_THEMES[theme][key] == expected
    channels = [expected[1:3], expected[3:5], expected[5:7]]
    assert len(set(channels)) == 1, (spot, channels)


def test_the_colours_two_names_share_are_compared_by_name():
    """One colour under two names, so a picture cannot say which moved."""
    for spot, expected in REPEATED_COLORS.items():
        theme, key = spot
        assert surface.CHART_THEMES[theme][key] == expected, spot
        assert shipped.CHART_THEMES[theme][key] == expected, spot
    assert (
        surface.CHART_THEMES["classic_terminal"]["text"]
        == surface.CHART_THEMES["classic_terminal"]["accent"]
    )
    assert (
        surface.CHART_THEMES["neon_light"]["btn_hover"]
        == surface.CHART_THEMES["cyberpunk_dark"]["text"]
    )
    assert surface.CANDLE_SERIES["up"] == surface.MARKER_SKIN["buy_color"]
    assert surface.CANDLE_SERIES["down"] == surface.MARKER_SKIN["sell_color"]


# ---------------------------------------------------------------------
# Nothing the surface holds is left out of the snapshot
# ---------------------------------------------------------------------

# Every constant the surface exports and the payload key that carries
# it. A comparison reading some of the constants passes whether the
# rest match or not; this closes that gap for every one at once.
CONSTANT_LOCATION = {
    "WIDGET_ACCESSIBLE_NAME": ("accessible_name", None),
    "LOGGER_NAME": ("logger_name", None),
    "MISSING_WEBENGINE_WARNING": ("missing_webengine_warning", None),
    "DEFAULT_SYMBOL": ("default_symbol", None),
    "DEFAULT_THEME": ("default_theme", None),
    "FALLBACK_THEME": ("fallback_theme", None),
    "SYMBOL_KEY": ("symbol_key", None),
    "SCRIPT_URL": ("script_url", None),
    "CHART_THEMES": ("themes", None),
    "CYBERPUNK_DARK": ("themes", "cyberpunk_dark"),
    "NEON_LIGHT": ("themes", "neon_light"),
    "CLASSIC_TERMINAL": ("themes", "classic_terminal"),
    "MINIMAL_MODERN": ("themes", "minimal_modern"),
    "GLASS_METAL": ("themes", "glass_metal"),
    "THEME_ORDER": ("theme_order", None),
    "THEME_KEYS": ("theme_keys", None),
    "PAGE": ("page", None),
    "WEB_VIEW": ("web_view", None),
    "TOOLBAR": ("toolbar", None),
    "BUTTON_SKIN": ("button_skin", None),
    "ACTIVE_TIMEFRAME": ("active_timeframe", None),
    "CANDLE_SERIES": ("candle_series", None),
    "UP_COLOR": ("candle_series", "up"),
    "DOWN_COLOR": ("candle_series", "down"),
    "VOLUME_SERIES": ("volume_series", None),
    "VOLUME_COLOR": ("volume_series", "color"),
    "VOLUME_UP_COLOR": ("volume_series", "up"),
    "VOLUME_DOWN_COLOR": ("volume_series", "down"),
    "BOLLINGER_SERIES": ("bollinger_series", None),
    "BB_EDGE_COLOR": ("bollinger_series", "upper_color"),
    "BB_MIDDLE_COLOR": ("bollinger_series", "middle_color"),
    "MARKER_SKIN": ("marker_skin", None),
    "GRID_LINE_SKIN": ("grid_line_skin", None),
    "GRID_BUY_COLOR": ("grid_line_skin", "buy_color"),
    "GRID_SELL_COLOR": ("grid_line_skin", "sell_color"),
    "WATERMARK": ("watermark", None),
    "TIME_SCALE": ("time_scale", None),
    "BUY_SIDE": ("buy_side", None),
    "SELL_SIDE": ("sell_side", None),
    "CANDLE_FIELDS": ("candle_fields", None),
    "VOLUME_FIELD": ("volume_field", None),
    "MARKER_FIELDS": ("marker_fields", None),
    "GRID_LEVEL_FIELDS": ("grid_level_fields", None),
    "BRIDGE_OBJECT": ("bridge_object", None),
    "BRIDGE_CALLBACK": ("bridge_callback", None),
    "CALL_FORMATS": ("call_formats", None),
    "SET_CANDLES_FORMAT": ("call_formats", "set_candles"),
    "UPDATE_CANDLE_FORMAT": ("call_formats", "update_candle"),
    "SET_BOLLINGER_BANDS_FORMAT": ("call_formats", "set_bollinger_bands"),
    "ADD_TRADE_MARKER_FORMAT": ("call_formats", "add_trade_marker"),
    "SET_GRID_LEVELS_FORMAT": ("call_formats", "set_grid_levels"),
    "CALL_ORDER": ("call_order", None),
    "NO_CALLS": ("calls", None),
    "ACTIONS": ("actions", None),
    "TIMERS": ("timers", None),
    "TIMER_DELAYS_MS": ("timer_delays_ms", None),
    "BUS_TOPICS": ("bus_topics", None),
    "SKIN": ("skin", None),
}

# The constants no snapshot key carries, each with the check that
# covers it.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_tradingview_chart_method",
    "CHART_HTML": "test_the_two_sides_hold_one_page_template",
    "TIMEFRAME_BUTTONS": "test_the_buttons_come_back_in_one_order_with_one_active",
}

# The snapshot keys built for each call rather than held as a constant.
BUILT_PER_CALL = {"symbol", "theme", "html", "colors", "buttons"}


def surface_constants():
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


def test_every_constant_the_surface_holds_reaches_the_snapshot():
    """A constant the surface exports is in no snapshot the tests read.

    Every constant is accounted for: a snapshot key, a key inside one,
    or one of the names above with the check that covers it.
    """
    payload = surface.build_view_model()
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in CONSTANT_LOCATION:
            key, inner = CONSTANT_LOCATION[name]
            carried = payload[key] if inner is None else payload[key][inner]
            wanted = list(value) if isinstance(value, tuple) else value
            assert carried == wanted, (name, carried, wanted)
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(CONSTANT_LOCATION) + len(NOT_IN_THE_SNAPSHOT) == CONSTANT_TOTAL


def test_every_snapshot_key_carries_a_constant_the_surface_holds():
    """The snapshot grew a key no constant on the surface backs."""
    payload = surface.build_view_model()
    from_constants = {key for key, _ in CONSTANT_LOCATION.values()}
    assert set(payload) == from_constants | BUILT_PER_CALL
    assert len(payload) == PAYLOAD_KEY_TOTAL
    for key in BUILT_PER_CALL:
        assert key in payload


def test_the_completeness_check_can_report_a_made_up_name():
    """The completeness check passed because it looks at nothing.

    A constant that reaches no snapshot key and no named exception must
    land in the unaccounted list, and a snapshot key no constant backs
    must land outside the two sets above.
    """
    payload = surface.build_view_model()
    invented = "INVENTED_CONSTANT"
    assert invented not in CONSTANT_LOCATION
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    from_constants = {key for key, _ in CONSTANT_LOCATION.values()}
    assert "invented_key" not in from_constants | BUILT_PER_CALL
    assert "CHART_THEMES" in surface_constants()
    assert "CALL_FORMATS" in surface_constants()
    assert "page_html" not in surface_constants()
    assert "TradingViewChartModel" not in surface_constants()
    assert "view_model" not in surface_constants()


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = surface.view_model({"symbol": "ETH/USD", "theme": "glass_metal"})
    text = json.dumps(payload, ensure_ascii=True)
    back = json.loads(text)
    assert back["symbol"] == "ETH/USD"
    assert back["themes"]["glass_metal"] == EXPECTED_THEMES["glass_metal"]
    assert back["html"] == surface.page_html("ETH/USD", "glass_metal")
    assert len(back["buttons"]) == BUTTON_TOTAL


def test_the_bridge_registers_the_tradingview_chart_method():
    """The renderer cannot reach the chart through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == METHOD_NAME
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps(
            {"id": 31, "method": surface.METHOD, "params": {"symbol": "SOL/USD"}}
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["symbol"] == "SOL/USD"
    assert result["accessible_name"] == EXPECTED_ACCESSIBLE_NAME
    assert len(result["themes"]) == THEME_TOTAL


def test_the_bridge_registration_is_two_lines_and_no_more():
    """The bridge grew more than the one registration this unit adds."""
    text = BRIDGE_PATH.read_text(encoding="utf-8")
    assert text.count("tradingview_chart_surface") == 3
    assert (
        "tradingview_chart_surface.METHOD: tradingview_chart_surface.view_model" in text
    )
    assert "tradingview_chart_surface,\n" in text


def test_the_bridge_answers_with_no_parameters_at_all():
    """A request carrying nothing ended the session."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 32, "method": METHOD_NAME}), registry
    )
    assert answer["ok"] is True
    assert answer["result"]["symbol"] == EXPECTED_DEFAULT_SYMBOL
    assert answer["result"]["theme"] == EXPECTED_DEFAULT_THEME


def test_the_bridge_ignores_a_parameter_it_does_not_know():
    """An unknown parameter ended the session."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {"id": 33, "method": METHOD_NAME, "params": {"no_such_key": "value"}}
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["symbol"] == EXPECTED_DEFAULT_SYMBOL


def test_the_bridge_reports_a_request_the_surface_refuses():
    """A refused request ended the session instead of being reported."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 34, "method": METHOD_NAME, "params": {"theme": ["a"]}}),
        registry,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "TypeError"


def test_two_calls_with_one_request_answer_the_same():
    """The surface held state between two calls."""
    first = surface.view_model({"symbol": "ETH/USD"})
    second = surface.view_model({"symbol": "SOL/USD"})
    third = surface.view_model({"symbol": "ETH/USD"})
    assert first == third
    assert digest(first) == digest(third)
    assert first != second
    assert first["themes"] == second["themes"]


# ---------------------------------------------------------------------
# The surface does not follow a value moved on the shipped side
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_moved_shipped_theme(monkeypatch):
    """The surface read its colours off the shipped module."""
    was = dict(shipped.CHART_THEMES["cyberpunk_dark"])
    monkeypatch.setitem(shipped.CHART_THEMES, "cyberpunk_dark", dict(was, bg="#123456"))
    assert shipped.CHART_THEMES["cyberpunk_dark"]["bg"] == "#123456"
    assert surface.CHART_THEMES["cyberpunk_dark"]["bg"] == was["bg"]
    assert surface.theme_colors("cyberpunk_dark")["bg"] == was["bg"]
    assert "#123456" not in surface.page_html("BTC/USDT", "cyberpunk_dark")
    old = old_display(CASES["happy"])
    new = new_display(CASES["happy"])
    assert "#123456" in old["html"]
    assert "#123456" not in new["html"]
    assert old["html"] != new["html"]


def test_the_surface_does_not_follow_a_moved_shipped_page(monkeypatch):
    """The surface read its page off the shipped module."""
    monkeypatch.setattr(shipped, "CHART_HTML", "<html>%(bg)s %(symbol)s</html>")
    assert shipped.CHART_HTML == "<html>%(bg)s %(symbol)s</html>"
    made = surface.page_html("BTC/USDT", "cyberpunk_dark")
    assert made.startswith("<!DOCTYPE html>")
    assert EXPECTED_SCRIPT_URL in made
    assert len(made) > 1000


def test_the_surface_does_not_follow_a_replaced_shipped_class(monkeypatch):
    """The surface built its answer from the shipped class."""

    class Stub:
        def __init__(self, *args, **named):
            self.args = args

    monkeypatch.setattr(shipped, "TradingViewChart", Stub)
    assert shipped.TradingViewChart is Stub
    model = surface.TradingViewChartModel("BTC/USDT", "neon_light")
    assert model.html == surface.page_html("BTC/USDT", "neon_light")
    assert EXPECTED_THEMES["neon_light"]["bg"] in model.html


# ---------------------------------------------------------------------
# The surface without Qt, proved in a process of its own
# ---------------------------------------------------------------------

BLOCK_QT = (
    "import sys\n"
    "class Refuse:\n"
    "    def find_module(self, name, path=None):\n"
    "        return self\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.split('.')[0] in ('PySide6', 'shiboken6'):\n"
    "            raise ImportError('Qt is blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, Refuse())\n"
)

BRIDGE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.core import desktop_bridge\n"
    "registry = desktop_bridge.build_registry()\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
    "    'method': 'tradingview.chart',\n"
    "    'params': {'symbol': 'SOL/USD', 'theme': 'glass_metal'}}), registry)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules, 'frame': frame}))\n"
)

TABLE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.gui.main_tabs import tradingview_chart_surface as s\n"
    "model = s.TradingViewChartModel('BTC/USDT', 'cyberpunk_dark')\n"
    "model.set_candles([])\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'themes': s.CHART_THEMES,\n"
    "    'buttons': s.buttons(),\n"
    "    'script_url': s.SCRIPT_URL,\n"
    "    'html': model.html,\n"
    "    'calls': model.calls,\n"
    "    'fallback': s.theme_colors('no_such_theme'),\n"
    "    'formats': s.CALL_FORMATS}))\n"
)

STUB_PROBE = BLOCK_QT + (
    "import io, json, logging\n"
    "held = io.StringIO()\n"
    "log = logging.getLogger('acervator.gui')\n"
    "log.setLevel(logging.WARNING)\n"
    "log.addHandler(logging.StreamHandler(held))\n"
    "from src.gui import tradingview_chart as t\n"
    "chart = t.TradingViewChart(symbol='BTC/USDT', theme='cyberpunk_dark')\n"
    "print(json.dumps({'has_webengine': t._HAS_WEBENGINE,\n"
    "    'warning': held.getvalue().strip(),\n"
    "    'has_set_candles': hasattr(chart, 'set_candles'),\n"
    "    'has_set_theme': hasattr(chart, 'set_theme'),\n"
    "    'members': sorted(k for k in vars(t.TradingViewChart)\n"
    "        if not k.startswith('__'))}))\n"
)


def run_script(source):
    """Run one probe in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the chart pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["symbol"] == "SOL/USD"
    assert result["theme"] == "glass_metal"
    assert result["accessible_name"] == EXPECTED_ACCESSIBLE_NAME
    assert result["html"] == surface.page_html("SOL/USD", "glass_metal")


def test_the_surface_carries_every_value_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(TABLE_PROBE)
    assert answered["qt"] is False
    assert answered["themes"] == EXPECTED_THEMES
    assert [one["label"] for one in answered["buttons"]] == [
        one[0] for one in EXPECTED_BUTTONS
    ]
    assert answered["script_url"] == EXPECTED_SCRIPT_URL
    assert answered["html"] == surface.page_html("BTC/USDT", "cyberpunk_dark")
    assert answered["calls"] == ["setCandles('[]')"]
    assert answered["fallback"] == EXPECTED_THEMES["cyberpunk_dark"]
    assert answered["formats"] == EXPECTED_CALL_FORMATS


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script(
        "import sys"
        + chr(10)
        + "import PySide6.QtCore"
        + chr(10)
        + BRIDGE_PROBE.replace(BLOCK_QT, "")
    )
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_qt_block_leaves_the_shipped_chart_without_its_methods():
    """The Qt block let the shipped chart through, so it proves nothing.

    With no browser widget the shipped module defines a stand-in class
    that logs a warning and carries none of the eight chart methods.
    """
    answered = run_script(STUB_PROBE)
    assert answered["has_webengine"] is False
    assert answered["warning"] == EXPECTED_MISSING_WARNING
    assert answered["has_set_candles"] is False
    assert answered["has_set_theme"] is False
    assert answered["members"] == ["__init__"] or answered["members"] == []
    assert surface.MISSING_WEBENGINE_WARNING == answered["warning"]
