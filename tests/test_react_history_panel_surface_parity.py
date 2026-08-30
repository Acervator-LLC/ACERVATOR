"""The shipped React History table and the Qt-free surface, side by side.

A failure means the surface builds a different page, a different palette,
a different push statement, a different view model, a different recorded
call or a different path than ``HistoryWebTable``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.exchange import history_read_contract as hrc
from src.gui import react_history_panel as shipped
from src.gui.main_tabs import react_history_panel_surface as surface
from tests.fixtures.host_fonts import (
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

PANEL_PATH = REPO_ROOT / "src/gui/react_history_panel.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/react_history_panel_surface.py"
TIMER_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/history_tab.py"
BUS_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
CHART_PATH = REPO_ROOT / "src/gui/tradingview_chart.py"

PIXEL_SIZE = (900, 620)
SMALL_PIXEL_SIZE = (400, 300)

# The real browser view announces no accessible name of its own, so the
# recorder standing in for it announces the same.
WEB_VIEW_ACCESSIBLE_NAME = ""

# A browser paints the whole visible area, so a render of this host
# carries exactly one colour whatever the product values are.
BROWSER_DRAWN_COLOUR_COUNT = 1

# Every way a page can pull something in from outside the file it was
# built from. None appears in the page this panel builds.
FETCH_MARKERS: tuple[str, ...] = (
    "<script src=",
    "<link ",
    "fetch(",
    "XMLHttpRequest",
    "WebSocket",
    "EventSource",
    "@import",
    "url(",
    "<iframe",
    "srcdoc",
    "navigator.sendBeacon",
    "document.write",
)

# The addresses the vendored React bundle carries as text: five element
# namespace names and the link its own error message prints. Nothing
# fetches any of them.
PAGE_ADDRESSES: list = [
    "http://www.w3.org/1998/Math/MathML",
    "http://www.w3.org/1999/xhtml",
    "http://www.w3.org/1999/xlink",
    "http://www.w3.org/2000/svg",
    "http://www.w3.org/XML/1998/namespace",
    "https://reactjs.org/docs/error-decoder.html?invariant=",
]

# The chrome colours the chart's theme table holds, typed out here rather
# than read from either side, so a re-valued theme cannot move both
# together.
CYBERPUNK_BG = "#0a0a0f"
CYBERPUNK_ACCENT = "#00ffcc"
NEON_BG = "#f5f5fa"
NEON_ACCENT = "#6600cc"
TERMINAL_TEXT = "#00ff00"
MINIMAL_ACCENT = "#2563eb"
GLASS_BORDER = "#3a3a50"

# The counts the shipped panel carries. Each is measured off the file and
# compared with what the surface declares.
PANEL_CONNECT_SITES = 1
PANEL_TIMER_SITES = 0
PANEL_BUS_SITES = 0

BASE_TS = 1_700_000_000.0
LATER_TS = 1_700_000_600.0
BILLION_TS = 1_000_000_000
BILLIONTH_TS = 1e-9

UNICODE_TEXT = "Δ_flip→⚡"
MARKUP_TEXT = "<b>bot</b>&nbsp;<script>x</script>"
APOSTROPHE_TEXT = "it's a 'quoted' name"
NEWLINE_TEXT = "two\nlines"
LONG_TEXT = "Z" * 200
WRONG_CAPITALS_SIDE = "buy"
INFINITY = float("inf")

HELD: list = []


# ---------------------------------------------------------------------
# The browser the shipped panel talks to, recording every ask
# ---------------------------------------------------------------------


def recording_web_view():
    """A stand-in for the browser that records what it was asked to do.

    Built inside a function so importing this module needs no Qt class at
    module scope. The shipped panel looks ``QWebEngineView`` up in its own
    module namespace, so replacing it there runs the real host code
    against a widget that keeps every statement rather than a browser.
    """
    from PySide6.QtCore import Signal
    from PySide6.QtWidgets import QWidget

    class RecordingPage:
        """The page object. A push carries no callback; a read carries one."""

        def __init__(self, view):
            self._view = view

        def runJavaScript(self, script, callback=None):
            if callback is None:
                self._view.pushes.append(script)
            else:
                self._view.reads.append(script)
                self._view.callbacks.append(callback)

    class RecordingWebView(QWidget):
        """A widget carrying the browser's signal and its page."""

        loadFinished = Signal(bool)

        def __init__(self):
            super().__init__()
            self.setAccessibleName(WEB_VIEW_ACCESSIBLE_NAME)
            self.html = ""
            self.pushes: list = []
            self.reads: list = []
            self.callbacks: list = []
            self._recording_page = RecordingPage(self)

        def setHtml(self, html):
            self.html = html

        def page(self):
            return self._recording_page

    return RecordingWebView


class LogGrab(logging.Handler):
    """Keeps every record the panel's own logger emits, level and text."""

    def __init__(self):
        super().__init__()
        self.records: list = []

    def emit(self, record):
        self.records.append([record.levelname, record.getMessage()])


def app():
    """The process application object every render needs."""
    from qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


def new_panel(theme=surface.DEFAULT_THEME, parent=None):
    """One real HistoryWebTable whose browser is the recorder.

    The recorder is a real widget, so the host's own layout runs. Held so
    no later read reaches a collected widget.
    """
    app()
    original = shipped.QWebEngineView
    shipped.QWebEngineView = recording_web_view()
    try:
        panel = shipped.HistoryWebTable(parent, theme)
    finally:
        shipped.QWebEngineView = original
    HELD.append(panel)
    return panel


# ---------------------------------------------------------------------
# The trades and filters both sides read
# ---------------------------------------------------------------------


def trade(
    trade_id="t-1",
    symbol="CHIP/USD",
    exchange="coinbase",
    side="BUY",
    ts=BASE_TS,
    price=10.0,
    amount=2.0,
    fee=0.01,
    fee_currency="USD",
):
    """One normalised trade row, the shape the exchange reader returns."""
    from datetime import datetime, timezone

    return {
        "id": trade_id,
        "exchange": exchange,
        "symbol": symbol,
        "side": side,
        "amount": amount,
        "price": price,
        "cost": (amount * price) if isinstance(amount, (int, float)) else 0,
        "fee": fee,
        "fee_currency": fee_currency,
        "timestamp": ts,
        "datetime": (
            datetime.fromtimestamp(ts, tz=timezone.utc)
            if isinstance(ts, (int, float)) and ts > 0
            else None
        ),
    }


def filters(**over):
    """The contract's five filter values, with everything open as the base."""
    return hrc.HistoryFilters(**over)


class BrokenFilters:
    """A filters object with no ``as_dict``, as a wrong caller would pass."""

    from_ts = 0
    to_ts = 0
    exchange = hrc.ALL
    symbol = hrc.ALL
    side = hrc.ALL


TWO_TRADES = [trade(), trade("t-2", side="SELL", ts=LATER_TS)]

VIEW_CASES: dict = {
    "happy": {"trades": TWO_TRADES, "filters": filters()},
    "empty": {"trades": [], "filters": filters()},
    "zero_page": {"trades": TWO_TRADES, "filters": filters(), "page": 0},
    "negative_page": {"trades": TWO_TRADES, "filters": filters(), "page": -4},
    "thousand_million_page": {
        "trades": TWO_TRADES,
        "filters": filters(),
        "page": 1_000_000_000,
    },
    "thousand_million_amount": {
        "trades": [trade(amount=1_000_000_000, price=1_000_000_000)],
        "filters": filters(),
    },
    "one_billionth_amount": {
        "trades": [trade(amount=1e-9, price=1e-9)],
        "filters": filters(),
    },
    "negative_amount": {
        "trades": [trade(amount=-3.5, price=-1.0)],
        "filters": filters(),
    },
    "zero_amount": {"trades": [trade(amount=0, price=0, fee=0)], "filters": filters()},
    "unicode_symbol": {
        "trades": [trade(symbol=UNICODE_TEXT, exchange=UNICODE_TEXT)],
        "filters": filters(),
    },
    "markup_symbol": {"trades": [trade(symbol=MARKUP_TEXT)], "filters": filters()},
    "apostrophe_symbol": {
        "trades": [trade(symbol=APOSTROPHE_TEXT)],
        "filters": filters(),
    },
    "newline_symbol": {"trades": [trade(symbol=NEWLINE_TEXT)], "filters": filters()},
    "long_symbol": {"trades": [trade(symbol=LONG_TEXT)], "filters": filters()},
    "wrong_capitals_side": {
        "trades": [trade(side=WRONG_CAPITALS_SIDE)],
        "filters": filters(side="BUY"),
    },
    "number_where_text_belongs": {
        "trades": [trade(symbol=7, exchange=7, trade_id=7)],
        "filters": filters(),
    },
    "text_where_number_belongs": {
        "trades": [trade(amount="lots", price="dear")],
        "filters": filters(),
    },
    "infinity_where_number_belongs": {
        "trades": [trade(amount=INFINITY, price=INFINITY)],
        "filters": filters(),
    },
    "one_billionth_bound": {
        "trades": TWO_TRADES,
        "filters": filters(from_ts=BILLIONTH_TS),
    },
    "thousand_million_bound": {
        "trades": TWO_TRADES,
        "filters": filters(from_ts=BILLION_TS, to_ts=BILLION_TS * 2),
    },
    "negative_bound": {"trades": TWO_TRADES, "filters": filters(from_ts=-5, to_ts=-9)},
    "text_where_a_bound_belongs": {
        "trades": TWO_TRADES,
        "filters": filters(from_ts="soon"),
    },
    "infinity_where_a_bound_belongs": {
        "trades": TWO_TRADES,
        "filters": filters(from_ts=INFINITY),
    },
    "filters_without_as_dict": {"trades": TWO_TRADES, "filters": BrokenFilters()},
    "trades_that_are_not_a_list": {"trades": 7, "filters": filters()},
    "supplied_filtered_set": {
        "trades": TWO_TRADES,
        "filters": filters(),
        "filtered": [TWO_TRADES[0]],
    },
    "supplied_join_indexes": {
        "trades": TWO_TRADES,
        "filters": filters(),
        "gate_index": {},
        "voting_index": {},
    },
    "table_only_chrome": {
        "trades": TWO_TRADES,
        "filters": filters(),
        "chrome": dict(surface.TABLE_ONLY_CHROME),
    },
    "fetch_age": {
        "trades": TWO_TRADES,
        "filters": filters(),
        "last_fetched_ts": BASE_TS,
        "now_ts": LATER_TS,
    },
}

THEME_CASES: tuple[str, ...] = (
    "cyberpunk_dark",
    "neon_light",
    "classic_terminal",
    "minimal_modern",
    "glass_metal",
    "no_such_theme",
    "",
    UNICODE_TEXT,
)

DATE_CASES: tuple = (
    0,
    -1,
    -1_000_000_000,
    1,
    BILLION_TS,
    BILLIONTH_TS,
    BASE_TS,
    INFINITY,
    "soon",
    None,
)

ASSET_CASES: tuple[str, ...] = (
    "history_panel.css",
    "history_panel.js",
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "no_such_asset.js",
    "vendor",
    "",
    UNICODE_TEXT,
)

PUSH_CASES: dict = {
    "empty": {},
    "happy": {"rows": 2, "summary": "2 of 2 trades shown"},
    "zero": {"total": 0},
    "negative": {"total": -5},
    "thousand_million": {"total": 1_000_000_000},
    "one_billionth": {"total": 1e-9},
    "unicode": {"symbol": UNICODE_TEXT},
    "markup": {"symbol": MARKUP_TEXT},
    "apostrophe": {"symbol": APOSTROPHE_TEXT},
    "newline": {"symbol": NEWLINE_TEXT},
    "long": {"symbol": LONG_TEXT},
    "wrong_capitals": {"side": WRONG_CAPITALS_SIDE},
    "number_where_text_belongs": {"symbol": 7},
    "text_where_number_belongs": {"total": "lots"},
    "line_terminators": {"symbol": "a b c"},
    "infinity_where_number_belongs": {"total": INFINITY},
}

# Each step drives one of the host's three entry points on both sides.
HOST_CASES: dict = {
    "held_then_loaded": (("set_model", "happy"), ("load", True)),
    "loaded_then_pushed": (("load", True), ("set_model", "happy")),
    "load_failed": (("set_model", "happy"), ("load", False)),
    "load_failed_then_recovered": (
        ("set_model", "happy"),
        ("load", False),
        ("load", True),
    ),
    "empty_model_on_load": (("load", True),),
    "row_count_before_load": (("row_count", None),),
    "row_count_after_load": (("load", True), ("row_count", None)),
    "row_count_twice": (("load", True), ("row_count", None), ("row_count", None)),
    "push_every_hostile_value": tuple(
        ("set_model", name) for name in sorted(PUSH_CASES)
    )
    + (("load", True),),
    "reloaded_pushes_again": (
        ("load", True),
        ("set_model", "unicode"),
        ("load", False),
        ("load", True),
    ),
    "never_loaded": (("set_model", "markup"), ("set_model", "apostrophe")),
}


def row_count_callback(value):
    """The callback both sides hand the page. Never called by either side."""
    return value


# ---------------------------------------------------------------------
# Reading the two sides into one shape
# ---------------------------------------------------------------------


def guarded(run):
    """Run one drive, keeping either what it returned or how it refused."""
    try:
        return {"error": "", "message": "", "answer": run()}
    except Exception as exc:
        return {"error": type(exc).__name__, "message": str(exc), "answer": None}


def digest(body):
    """One case's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def text_digest(value):
    """One string as a single hash, so a 162 KB page compares in one line."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_old_host(panel):
    """The shipped host's whole state, read off the widget and its browser."""
    return {
        "accessible_name": panel.accessibleName(),
        "page_ready": panel.page_ready,
        "model": panel.model(),
        "pushes": list(panel._web.pushes),
        "scripts": list(panel._web.reads),
        "callback_count": len(panel._web.callbacks),
        "html_digest": text_digest(panel._web.html),
        "margins": [
            panel.layout().contentsMargins().left(),
            panel.layout().contentsMargins().top(),
            panel.layout().contentsMargins().right(),
            panel.layout().contentsMargins().bottom(),
        ],
        "spacing": panel.layout().spacing(),
        "stretch": panel.layout().stretch(0),
    }


def read_new_host(model):
    """The surface model's whole state in the same shape."""
    return {
        "accessible_name": model.accessible_name,
        "page_ready": model.page_ready,
        "model": model.model(),
        "pushes": list(model.pushes),
        "scripts": list(model.scripts),
        "callback_count": len(model.callbacks),
        "html_digest": text_digest(model.html),
        "margins": list(model.margins),
        "spacing": model.spacing,
        "stretch": model.stretch,
    }


# ---------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------


def run_steps(host, steps, is_old):
    """Drive one case's steps through either side's host."""
    for step in steps:
        name = step[0]
        if name == "load":
            if is_old:
                host._web.loadFinished.emit(step[1])
            else:
                host._on_load_finished(step[1])
        elif name == "set_model":
            host.set_model(dict(PUSH_CASES[step[1]]))
        elif name == "row_count":
            host.row_count(row_count_callback)


def old_host(name, theme=surface.DEFAULT_THEME):
    """The shipped host, driven over one case."""
    panel = new_panel(theme)
    run_steps(panel, HOST_CASES[name], is_old=True)
    return panel


def new_host(name, theme=surface.DEFAULT_THEME):
    """The surface model, driven over the same case."""
    model = surface.HistoryPanelModel(theme=theme)
    run_steps(model, HOST_CASES[name], is_old=False)
    return model


def old_view(name):
    """The shipped view-model builder, driven over one case."""
    case = dict(VIEW_CASES[name])
    return guarded(
        lambda: shipped.build_view_model(
            case["trades"],
            case["filters"],
            page=case.get("page", 0),
            last_fetched_ts=case.get("last_fetched_ts", 0.0),
            now_ts=case.get("now_ts"),
            filtered=case.get("filtered"),
            gate_index=case.get("gate_index"),
            voting_index=case.get("voting_index"),
            chrome=case.get("chrome"),
        )
    )


def new_view(name):
    """The surface's view-model builder, driven over the same case."""
    case = dict(VIEW_CASES[name])
    return guarded(
        lambda: surface.build_view_model(
            case["trades"],
            case["filters"],
            page=case.get("page", 0),
            last_fetched_ts=case.get("last_fetched_ts", 0.0),
            now_ts=case.get("now_ts"),
            filtered=case.get("filtered"),
            gate_index=case.get("gate_index"),
            voting_index=case.get("voting_index"),
            chrome=case.get("chrome"),
        )
    )


@pytest.fixture(autouse=True)
def no_live_logs(monkeypatch):
    """Read EMPTY live logs, so no case reaches the operator's gate log."""
    import src.trading.live_log_reader as reader

    def empty(*args, **kwargs):
        del args, kwargs
        return iter([])

    monkeypatch.setattr(reader, "live_gate_decisions", empty)
    monkeypatch.setattr(reader, "live_voting_panel_snapshots", empty)


# ---------------------------------------------------------------------
# Side by side
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(HOST_CASES))
def test_the_host_state_is_the_shipped_panels(name):
    """The surface holds a different state than the shipped host."""
    old_side = read_old_host(old_host(name))
    new_side = read_new_host(new_host(name))
    assert new_side == old_side, name
    assert digest(new_side) == digest(old_side), name


@pytest.mark.parametrize("name", sorted(VIEW_CASES))
def test_the_view_model_is_the_shipped_panels(name):
    """The surface builds a different view model than the shipped panel."""
    old_side = old_view(name)
    new_side = new_view(name)
    assert new_side == old_side, name
    assert digest(new_side) == digest(old_side), name


@pytest.mark.parametrize("theme", THEME_CASES)
def test_the_page_is_the_shipped_panels(theme):
    """The surface builds a different page than the shipped panel."""
    old_side = shipped.panel_html(theme)
    new_side = surface.panel_html(theme)
    assert text_digest(new_side) == text_digest(old_side), theme
    assert new_side == old_side, theme


@pytest.mark.parametrize("theme", THEME_CASES)
def test_the_palette_is_the_shipped_panels(theme):
    """The surface picks a different palette than the shipped panel.

    The render beside the value read is what proves the value has to be
    read: the browser paints the whole window, so no theme colour of
    either side reaches a Qt pixel.
    """
    from qt_pixel import render_widget

    app()
    assert surface.palette(theme) == shipped._palette(theme), theme
    assert list(surface.palette(theme)) == list(surface.PALETTE_KEYS), theme
    assert (
        colour_count(render_widget(real_panel(theme), SMALL_PIXEL_SIZE))
        == BROWSER_DRAWN_COLOUR_COUNT
    ), theme


@pytest.mark.parametrize("name", ASSET_CASES)
def test_the_asset_read_is_the_shipped_panels(name):
    """The surface reads a different asset, or refuses differently."""
    old_side = guarded(lambda: shipped.read_asset(name))
    new_side = guarded(lambda: surface.read_asset(name))
    assert new_side == old_side, name
    assert digest(new_side) == digest(old_side), name


@pytest.mark.parametrize("ts", DATE_CASES)
def test_the_filter_bound_text_is_the_shipped_panels(ts):
    """The surface writes a different filter bound, or refuses differently."""
    old_side = guarded(lambda: shipped._date_text(ts))
    new_side = guarded(lambda: surface.date_text(ts))
    assert new_side == old_side, ts


@pytest.mark.parametrize("name", sorted(PUSH_CASES))
def test_the_push_statement_is_the_shipped_panels(name):
    """The surface sends a different statement into the page."""
    payload = dict(PUSH_CASES[name])
    old_side = guarded(lambda: shipped.state_push_script(payload))
    new_side = guarded(lambda: surface.state_push_script(payload))
    assert new_side == old_side, name
    assert digest(new_side) == digest(old_side), name


def test_the_asset_directory_is_the_shipped_panels():
    """The surface reads its assets from a different directory."""
    assert surface.asset_dir() == shipped.asset_dir()
    assert surface.asset_dir().is_dir()
    assert surface.asset_dir().name == surface.ASSET_SUBDIR


def test_the_sample_hashes_are_reported():
    """The reported sample hashes are not the hashes the run produced."""
    samples = {
        "host_happy": digest(read_new_host(new_host("held_then_loaded"))),
        "view_happy": digest(new_view("happy")),
        "page_default": text_digest(surface.panel_html()),
        "push_unicode": digest(
            guarded(lambda: surface.state_push_script(PUSH_CASES["unicode"]))
        ),
    }
    assert samples["host_happy"] == digest(read_old_host(old_host("held_then_loaded")))
    assert samples["view_happy"] == digest(old_view("happy"))
    assert samples["page_default"] == text_digest(shipped.panel_html())
    assert len({len(value) for value in samples.values()}) == 1
    assert all(len(value) == 64 for value in samples.values())
    assert len(set(samples.values())) == 4, samples


def test_two_genuinely_different_cases_hash_apart():
    """The hash reports one value for every case, so a match means
    nothing."""
    assert digest(old_view("happy")) != digest(new_view("empty"))
    assert digest(read_old_host(old_host("load_failed"))) != digest(
        read_new_host(new_host("loaded_then_pushed"))
    )
    assert text_digest(shipped.panel_html("cyberpunk_dark")) != text_digest(
        surface.panel_html("neon_light")
    )
    assert digest(old_view("unicode_symbol")) != digest(new_view("markup_symbol"))
    assert digest(new_view("happy")) == digest(old_view("happy"))


# ---------------------------------------------------------------------
# Answered or refused
# ---------------------------------------------------------------------


def test_the_outcome_set_holds_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the input table
    exercises one outcome and proves nothing about the other."""
    view_outcomes = {name: new_view(name)["error"] for name in VIEW_CASES}
    assert view_outcomes == {name: old_view(name)["error"] for name in VIEW_CASES}
    answered = sorted(name for name, error in view_outcomes.items() if not error)
    refused = sorted(name for name, error in view_outcomes.items() if error)
    assert answered, view_outcomes
    assert refused, view_outcomes
    assert set(refused) == {
        "filters_without_as_dict",
        "infinity_where_a_bound_belongs",
        "text_where_a_bound_belongs",
        "text_where_number_belongs",
        "trades_that_are_not_a_list",
    }
    assert view_outcomes["text_where_number_belongs"] == "ValueError"
    assert view_outcomes["infinity_where_number_belongs"] == ""
    assert len(answered) + len(refused) == len(VIEW_CASES)
    assert {view_outcomes[name] for name in refused} == {
        "AttributeError",
        "OverflowError",
        "TypeError",
        "ValueError",
    }


def test_every_refusal_carries_the_shipped_panels_own_words():
    """A refusal reads differently on the two sides."""
    for name in sorted(VIEW_CASES):
        old_side = old_view(name)
        new_side = new_view(name)
        assert new_side["error"] == old_side["error"], name
        assert new_side["message"] == old_side["message"], name
    assert new_view("text_where_a_bound_belongs")["error"] == "TypeError"
    assert new_view("filters_without_as_dict")["error"] == "AttributeError"
    assert new_view("infinity_where_a_bound_belongs")["error"] == "OverflowError"


def test_the_asset_outcome_set_holds_both_an_answer_and_a_refusal():
    """Every asset read answered, or every one refused."""
    outcomes = {
        name: guarded(lambda n=name: surface.read_asset(n)) for name in ASSET_CASES
    }
    answered = sorted(name for name, found in outcomes.items() if not found["error"])
    refused = sorted(name for name, found in outcomes.items() if found["error"])
    assert answered == [
        "history_panel.css",
        "history_panel.js",
        "vendor/react-dom.production.min.js",
        "vendor/react.production.min.js",
    ]
    assert refused == ["", "no_such_asset.js", "vendor", UNICODE_TEXT]
    assert {outcomes[name]["error"] for name in refused} == {"HistoryPanelAssetMissing"}
    for name in refused:
        assert outcomes[name]["message"].startswith("History panel asset not readable")


def test_the_filter_bound_outcome_set_holds_both_an_answer_and_a_refusal():
    """Every bound answered, or every one refused."""
    outcomes = {
        str(ts): guarded(lambda t=ts: surface.date_text(t)) for ts in DATE_CASES
    }
    answered = sorted(name for name, found in outcomes.items() if not found["error"])
    refused = sorted(name for name, found in outcomes.items() if found["error"])
    assert answered and refused, outcomes
    assert refused == ["None", "inf", "soon"]
    assert {outcomes[name]["error"] for name in refused} == {
        "OverflowError",
        "TypeError",
    }
    assert outcomes["0"]["answer"] == surface.DATE_ANY_TEXT
    assert outcomes["-1"]["answer"] == surface.DATE_ANY_TEXT
    assert outcomes[str(BILLIONTH_TS)]["answer"] == "1970-01-01 00:00"


@pytest.mark.parametrize("name", sorted(HOST_CASES))
def test_every_host_case_reaches_the_path_it_names(name):
    """A path the surface names is never the branch that ran."""
    old_side = old_host(name)
    new_side = new_host(name)
    steps = HOST_CASES[name]
    if any(step[0] == "set_model" for step in steps):
        assert new_side.set_model_path in surface.SET_MODEL_PATHS, name
    if any(step[0] == "row_count" for step in steps):
        assert new_side.row_count_path in surface.ROW_COUNT_PATHS, name
    if any(step[0] == "load" for step in steps):
        assert new_side.load_path in surface.LOAD_PATHS, name
    if new_side.set_model_path == surface.SET_MODEL_PATH_HELD:
        assert old_side._web.pushes == [] or steps[-1][0] != "set_model", name
    if new_side.row_count_path == surface.ROW_COUNT_PATH_REFUSED:
        assert old_side._web.reads == [], name
    if new_side.load_path == surface.LOAD_PATH_FAILED:
        assert old_side.page_ready is False, name
    if new_side.load_path in (surface.LOAD_PATH_READY, surface.LOAD_PATH_PUSHED):
        assert old_side.page_ready is True, name


def test_the_path_set_covers_every_branch_the_host_holds():
    """A branch of the host is reached by no case in the table."""
    reached = {"set_model": set(), "row_count": set(), "load": set()}
    for name in HOST_CASES:
        model = new_host(name)
        if model.set_model_path:
            reached["set_model"].add(model.set_model_path)
        if model.row_count_path:
            reached["row_count"].add(model.row_count_path)
        if model.load_path:
            reached["load"].add(model.load_path)
    assert reached["set_model"] == set(surface.SET_MODEL_PATHS)
    assert reached["row_count"] == set(surface.ROW_COUNT_PATHS)
    assert reached["load"] == set(surface.LOAD_PATHS)
    assert len(surface.LOAD_PATHS) == 3


# ---------------------------------------------------------------------
# What the two sides do, value by value
# ---------------------------------------------------------------------


def test_a_model_held_before_the_page_loads_is_pushed_by_the_load():
    """A model handed over early is dropped on the way in."""
    old_side = old_host("held_then_loaded")
    new_side = new_host("held_then_loaded")
    assert len(old_side._web.pushes) == 1
    assert new_side.pushes == old_side._web.pushes
    assert new_side.load_path == surface.LOAD_PATH_PUSHED
    assert old_side.model() == new_side.model() == dict(PUSH_CASES["happy"])


def test_a_page_that_never_loaded_is_never_pushed_to():
    """A statement reached a page that is not up."""
    old_side = old_host("never_loaded")
    new_side = new_host("never_loaded")
    assert old_side._web.pushes == []
    assert new_side.pushes == []
    assert new_side.set_model_path == surface.SET_MODEL_PATH_HELD
    assert old_side.page_ready is new_side.page_ready is False
    pushed = new_host("loaded_then_pushed")
    assert len(pushed.pushes) == 1


def test_a_failed_load_writes_the_shipped_panels_own_warning():
    """The line the panel logs when the page fails to come up moved."""
    logger = logging.getLogger(surface.LOGGER_NAME)
    grab = LogGrab()
    original_level = logger.level
    logger.addHandler(grab)
    logger.setLevel(logging.DEBUG)
    try:
        old_side = old_host("load_failed")
    finally:
        logger.removeHandler(grab)
        logger.setLevel(original_level)
    new_side = new_host("load_failed")
    assert grab.records == [["WARNING", "React History page failed to load"]]
    assert new_side.logs == grab.records
    assert new_side.logs == [[surface.LOAD_FAILED_LEVEL, surface.LOAD_FAILED_MESSAGE]]
    assert old_side.page_ready is False
    assert old_side._web.pushes == [] == new_side.pushes


def test_the_warning_watcher_can_see_a_line_that_was_written():
    """The log watcher reports nothing whatever the panel logs."""
    logger = logging.getLogger(surface.LOGGER_NAME)
    grab = LogGrab()
    original_level = logger.level
    logger.addHandler(grab)
    logger.setLevel(logging.DEBUG)
    try:
        old_host("load_failed")
        first = list(grab.records)
        old_host("empty_model_on_load")
        assert list(grab.records) == first
        logger.warning("a line this panel never writes")
    finally:
        logger.removeHandler(grab)
        logger.setLevel(original_level)
    assert first == [["WARNING", surface.LOAD_FAILED_MESSAGE]]
    assert grab.records[-1] == ["WARNING", "a line this panel never writes"]


def test_a_row_count_before_the_page_loads_asks_nothing():
    """A read reached a page that is not up."""
    old_side = new_panel()
    new_side = surface.HistoryPanelModel()
    assert old_side.row_count(row_count_callback) is False
    assert new_side.row_count(row_count_callback) is False
    assert old_side._web.reads == [] == new_side.scripts
    old_side._web.loadFinished.emit(True)
    new_side._on_load_finished(True)
    assert old_side.row_count(row_count_callback) is True
    assert new_side.row_count(row_count_callback) is True
    assert old_side._web.reads == new_side.scripts == [surface.ROW_COUNT_JS]


def test_the_row_count_hands_the_page_the_callers_own_callback():
    """The callback the caller passed is not the one handed over."""
    old_side = new_panel()
    old_side._web.loadFinished.emit(True)
    old_side.row_count(row_count_callback)
    new_side = new_host("row_count_after_load")
    assert old_side._web.callbacks == [row_count_callback]
    assert new_side.callbacks == [row_count_callback]
    assert len(new_side.callbacks) == len(old_side._web.callbacks) == 1


def test_neither_side_answers_the_row_count_itself():
    """One side answered the count without asking the page."""
    seen: list = []
    old_side = new_panel()
    old_side._web.loadFinished.emit(True)
    old_side.row_count(seen.append)
    new_side = surface.HistoryPanelModel()
    new_side._on_load_finished(True)
    new_side.row_count(seen.append)
    assert seen == []
    seen.append("the watcher can record")
    assert seen == ["the watcher can record"]


def test_the_model_read_back_is_a_copy_on_both_sides():
    """Changing the answer changes what the host holds."""
    old_side = old_host("held_then_loaded")
    new_side = new_host("held_then_loaded")
    old_copy = old_side.model()
    new_copy = new_side.model()
    old_copy["rows"] = "changed"
    new_copy["rows"] = "changed"
    assert old_side.model() == new_side.model() == dict(PUSH_CASES["happy"])
    assert old_side.model()["rows"] == 2


def test_the_push_statement_escapes_the_two_js_line_terminators():
    """A line terminator inside the data ends the statement early."""
    payload = dict(PUSH_CASES["line_terminators"])
    old_side = shipped.state_push_script(payload)
    new_side = surface.state_push_script(payload)
    assert new_side == old_side
    assert " " not in new_side
    assert " " not in new_side
    assert "\\u2028" in new_side and "\\u2029" in new_side
    assert new_side.startswith(surface.PUSH_PREFIX)
    assert new_side.endswith(surface.PUSH_SUFFIX)


def test_an_apostrophe_in_the_data_is_left_unquoted_on_both_sides():
    """The statement wraps its JSON in quotes an apostrophe would end."""
    payload = dict(PUSH_CASES["apostrophe"])
    old_side = shipped.state_push_script(payload)
    new_side = surface.state_push_script(payload)
    assert new_side == old_side
    assert new_side.startswith(surface.PUSH_FUNCTION + "({")
    assert "'" in new_side
    assert surface.PUSH_PREFIX + "'" not in new_side


def test_the_page_carries_the_palette_the_theme_names():
    """A theme reaches the page as another theme's colours."""
    for theme, colour in (
        ("cyberpunk_dark", CYBERPUNK_BG),
        ("neon_light", NEON_BG),
        ("classic_terminal", TERMINAL_TEXT),
        ("minimal_modern", MINIMAL_ACCENT),
        ("glass_metal", GLASS_BORDER),
    ):
        old_side = shipped.panel_html(theme)
        new_side = surface.panel_html(theme)
        assert colour in new_side, theme
        assert new_side == old_side, theme
    assert CYBERPUNK_ACCENT in surface.panel_html("cyberpunk_dark")
    assert NEON_ACCENT in surface.panel_html("neon_light")
    assert NEON_ACCENT not in surface.panel_html("cyberpunk_dark")


def test_an_unknown_theme_falls_back_to_the_shipped_default():
    """An unknown theme paints something the shipped panel does not."""
    from qt_pixel import render_widget

    app()
    for theme in ("no_such_theme", "", UNICODE_TEXT):
        assert surface.palette(theme) == shipped._palette(theme), theme
        assert surface.palette(theme) == surface.palette(surface.DEFAULT_THEME), theme
    assert surface.palette("neon_light") != surface.palette(surface.DEFAULT_THEME)
    assert (
        colour_count(render_widget(real_panel("no_such_theme"), SMALL_PIXEL_SIZE))
        == BROWSER_DRAWN_COLOUR_COUNT
    )


def test_the_page_reaches_no_network():
    """The page fetches something from outside the machine."""
    page = surface.panel_html()
    for fetcher in FETCH_MARKERS:
        assert fetcher not in page, fetcher
    lines = page.split(surface.HTML_JOIN)
    assert lines.count(surface.HTML_SCRIPT_OPEN) == len(surface.ASSET_NAMES)
    assert lines.count(surface.HTML_SCRIPT_OPEN) == 3
    assert lines.count(surface.HTML_SCRIPT_CLOSE) == 3
    assert page.count(surface.HTML_SCRIPT_OPEN) == 4
    assert page == shipped.panel_html()


def test_a_script_tag_written_as_text_is_not_counted_as_a_tag():
    """A tag the bundle prints as text is counted as a tag the page runs.

    The React DOM bundle carries the literal text ``<script>`` inside one
    of its own strings, so the page holds four of them and runs three.
    """
    page = surface.panel_html()
    assert page.count(surface.HTML_SCRIPT_OPEN) == 4
    assert page.split(surface.HTML_JOIN).count(surface.HTML_SCRIPT_OPEN) == 3
    assert (
        surface.read_asset("vendor/react-dom.production.min.js").count(
            surface.HTML_SCRIPT_OPEN
        )
        == 1
    )
    assert surface.read_asset("history_panel.js").count(surface.HTML_SCRIPT_OPEN) == 0


def test_every_address_the_page_holds_is_text_the_bundle_prints():
    """An address in the page is one the page would fetch."""
    import re

    page = surface.panel_html()
    found = sorted(set(re.findall(r"https?://[A-Za-z0-9./_?=&+#:-]+", page)))
    assert found == PAGE_ADDRESSES
    assert len(found) == 6
    for address in found[:5]:
        assert address.startswith("http://www.w3.org/")
    assert found[5].startswith("https://reactjs.org/docs/")
    for address in found:
        assert "<script src=" + address not in page
        assert 'fetch("' + address not in page


def test_the_network_scan_can_see_a_fetch_that_is_there():
    """The network scan reports nothing whatever the page carries."""
    page = surface.panel_html()
    assert "<script src=" not in page
    assert "fetch(" not in page
    seeded = page + '<script src="https://example.invalid/x.js"></script>fetch("x")'
    assert [marker for marker in FETCH_MARKERS if marker in seeded] == [
        "<script src=",
        "fetch(",
    ]
    assert [marker for marker in FETCH_MARKERS if marker in page] == []


def test_the_page_is_built_by_joining_never_by_formatting():
    """A brace or a percent in the bundle broke the page build."""
    page = surface.panel_html()
    assert "%" in page
    assert "{" in page and "}" in page
    assert page == shipped.panel_html()
    assert len(page) > 100_000


def test_the_chrome_the_client_asks_for_reaches_the_view_model():
    """The chrome flags the host sends were dropped."""
    answered = new_view("table_only_chrome")["answer"]
    assert answered["chrome"] == surface.TABLE_ONLY_CHROME
    assert answered["chrome"] == {"summary": False, "filters": False, "pager": False}
    assert old_view("table_only_chrome")["answer"]["chrome"] == answered["chrome"]
    assert new_view("happy")["answer"]["chrome"] == {}


# ---------------------------------------------------------------------
# The window the browser draws
# ---------------------------------------------------------------------


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def real_panel(theme):
    """The shipped host with its real browser, ready to render."""
    app()
    panel = shipped.HistoryWebTable(None, theme)
    HELD.append(panel)
    return panel


def panel_from_the_surface(theme):
    """A host built only from the surface's payload, ready to render."""
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    app()
    payload = surface.build_payload(surface.HistoryPanelModel(theme=theme))
    panel = QWidget()
    HELD.append(panel)
    panel.setAccessibleName(payload["accessible_name"])
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(*payload["content_margins"])
    layout.setSpacing(payload["content_spacing"])
    web = QWebEngineView()
    web.setHtml(surface.panel_html(payload["theme"]))
    layout.addWidget(web, payload["web_stretch"])
    return panel


def test_the_visible_area_is_drawn_by_the_browser_and_carries_no_qt_pixel():
    """A product value reaches a Qt pixel, so a picture could report one."""
    app()
    old_side = render_offscreen(real_panel("cyberpunk_dark"), PIXEL_SIZE)
    new_side = render_offscreen(panel_from_the_surface("neon_light"), PIXEL_SIZE)
    assert colour_count(old_side) == 1
    assert colour_count(new_side) == 1
    with pytest.raises(AssertionError) as refused:
        assert_pictures_differ(
            old_side=old_side, new_side=new_side, note="two different themes"
        )
    assert "painted one picture" in str(refused.value)
    assert_pictures_match(
        old_side=old_side, new_side=new_side, note="two different themes"
    )


def test_the_picture_check_reports_two_renders_that_really_differ():
    """The picture comparison passes whatever the second side painted."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(real_panel("cyberpunk_dark"), PIXEL_SIZE),
        new_side=render_offscreen(
            panel_from_the_surface("neon_light"), SMALL_PIXEL_SIZE
        ),
        note="one host at two sizes",
    )
    assert_pictures_match(
        old_side=render_offscreen(real_panel("cyberpunk_dark"), PIXEL_SIZE),
        new_side=render_offscreen(panel_from_the_surface("cyberpunk_dark"), PIXEL_SIZE),
        note="one theme, both sides",
    )


def test_the_theme_the_picture_cannot_show_is_read_off_both_sides():
    """A theme that paints no pixel was left to a picture to report."""
    from qt_pixel import render_widget

    app()
    assert (
        colour_count(render_widget(real_panel("neon_light"), SMALL_PIXEL_SIZE))
        == BROWSER_DRAWN_COLOUR_COUNT
    )
    for theme in surface.THEME_NAMES:
        assert surface.palette(theme) == shipped._palette(theme), theme
    assert surface.palette("cyberpunk_dark") != surface.palette("neon_light")
    assert surface.palette("cyberpunk_dark")["--bg"] == CYBERPUNK_BG
    assert surface.palette("neon_light")["--accent"] == NEON_ACCENT
    assert text_digest(surface.panel_html("cyberpunk_dark")) != text_digest(
        surface.panel_html("neon_light")
    )


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves nothing."""
    app()
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    metrics = QFontMetrics(QApplication.font())
    narrow = metrics.horizontalAdvance("iiiiiiii")
    wide = metrics.horizontalAdvance("WWWWWWWW")
    if has_real_fonts():
        assert wide > narrow
    else:
        assert wide == narrow


@skip_unless_no_fonts
def test_with_no_font_database_the_window_is_still_flat():
    """The host painted more than one colour with no font database, so
    the browser is reaching a Qt pixel after all."""
    app()
    assert colour_count(render_offscreen(real_panel("cyberpunk_dark"), PIXEL_SIZE)) == 1


@skip_unless_real_fonts
def test_with_a_font_database_the_window_is_still_flat():
    """The host painted more than one colour on a run holding fonts, so
    the flat window is a property of this machine rather than the
    browser."""
    app()
    assert colour_count(render_offscreen(real_panel("cyberpunk_dark"), PIXEL_SIZE)) == 1


# ---------------------------------------------------------------------
# What a picture cannot see
# ---------------------------------------------------------------------


BLIND_TO_THE_PICTURE = {
    "page_html": "test_the_page_is_the_shipped_panels",
    "palette": "test_the_palette_is_the_shipped_panels",
    "theme_fallback": "test_an_unknown_theme_falls_back_to_the_shipped_default",
    "asset_names": "test_the_asset_read_is_the_shipped_panels",
    "asset_directory": "test_the_asset_directory_is_the_shipped_panels",
    "asset_refusal": "test_the_asset_outcome_set_holds_both_an_answer_and_a_refusal",
    "row_count_script": "test_a_row_count_before_the_page_loads_asks_nothing",
    "row_count_callback": "test_the_row_count_hands_the_page_the_callers_own_callback",
    "push_statement": "test_the_push_statement_is_the_shipped_panels",
    "line_terminators": "test_the_push_statement_escapes_the_two_js_line_terminators",
    "apostrophe": "test_an_apostrophe_in_the_data_is_left_unquoted_on_both_sides",
    "view_model": "test_the_view_model_is_the_shipped_panels",
    "view_refusal": "test_every_refusal_carries_the_shipped_panels_own_words",
    "filter_bound_text": "test_the_filter_bound_text_is_the_shipped_panels",
    "chrome_flags": "test_the_chrome_the_client_asks_for_reaches_the_view_model",
    "held_model": "test_a_model_held_before_the_page_loads_is_pushed_by_the_load",
    "page_ready": "test_a_page_that_never_loaded_is_never_pushed_to",
    "warning_line": "test_a_failed_load_writes_the_shipped_panels_own_warning",
    "model_copy": "test_the_model_read_back_is_a_copy_on_both_sides",
    "accessible_name": "test_the_accessible_name_is_compared_as_a_string",
    "layout_numbers": "test_the_layout_numbers_are_compared_as_values",
    "signal_wiring": "test_the_connect_sites_match_the_actions",
    "timer": "test_the_panel_starts_no_timer",
    "bus_topic": "test_the_panel_subscribes_to_no_bus_topic",
    "skin": "test_the_panel_declares_no_skin_of_its_own",
    "network": "test_the_page_reaches_no_network",
    "page_addresses": "test_every_address_the_page_holds_is_text_the_bundle_prints",
    "script_tag_text": "test_a_script_tag_written_as_text_is_not_counted_as_a_tag",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    app()
    assert len(BLIND_TO_THE_PICTURE) == 28
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert colour_count(render_offscreen(real_panel("cyberpunk_dark"), PIXEL_SIZE)) == 1


def test_the_accessible_name_is_compared_as_a_string():
    """The name a screen reader announces moved on one side."""
    assert new_panel().accessibleName() == surface.ACCESSIBLE_NAME
    assert surface.HistoryPanelModel().accessible_name == "React History Table"
    assert real_panel("cyberpunk_dark").accessibleName() == surface.ACCESSIBLE_NAME
    assert surface.WIDGETS[0]["accessible_name"] == surface.ACCESSIBLE_NAME


def test_the_layout_numbers_are_compared_as_values():
    """A margin, a spacing or a stretch moved on one side."""
    panel = new_panel()
    margins = panel.layout().contentsMargins()
    assert [
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ] == list(surface.CONTENT_MARGINS)
    assert panel.layout().spacing() == surface.CONTENT_SPACING == 0
    assert panel.layout().stretch(0) == surface.WEB_STRETCH == 1
    assert panel.layout().count() == 1
    assert panel.layout().metaObject().className() == surface.LAYOUT_KIND


# ---------------------------------------------------------------------
# The counterpart map
# ---------------------------------------------------------------------


METHOD_MAP = {
    "HistoryWebTable.__init__": "HistoryPanelModel.__init__",
    "HistoryWebTable.page_ready": "HistoryPanelModel.page_ready",
    "HistoryWebTable.model": "HistoryPanelModel.model",
    "HistoryWebTable.set_model": "HistoryPanelModel.set_model",
    "HistoryWebTable.row_count": "HistoryPanelModel.row_count",
    "HistoryWebTable._push": "HistoryPanelModel._push",
    "HistoryWebTable._on_load_finished": "HistoryPanelModel._on_load_finished",
}

MODEL_MEMBERS = {
    "__init__",
    "page_ready",
    "model",
    "set_model",
    "_set_model_finish",
    "row_count",
    "_row_count_finish",
    "_push",
    "_on_load_finished",
    "_load_finish",
}

HELPER_MAP = {
    "asset_dir": "asset_dir",
    "read_asset": "read_asset",
    "_palette": "palette",
    "panel_html": "panel_html",
    "_date_text": "date_text",
    "build_view_model": "build_view_model",
    "state_push_script": "state_push_script",
}

CLASS_MAP = {
    "HistoryPanelAssetMissing": "HistoryPanelAssetMissing",
    "HistoryWebTable": "HistoryPanelModel",
}

SURFACE_ONLY_FUNCTIONS = ("widget", "build_filters", "build_payload", "view_model")


def members(owner):
    """Every method and property a class defines, by name."""
    import inspect

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if inspect.isfunction(value) or isinstance(value, property):
            found.add(name)
    return found


def module_classes(module):
    """Every class a module defines, by name."""
    import inspect

    return {
        name
        for name, value in vars(module).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == module.__name__
    }


def module_functions(module):
    """Every function a module defines at its top level, by name."""
    import inspect

    return {
        name
        for name, value in vars(module).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == module.__name__
    }


def resolve(dotted):
    """The member a dotted name in the map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def test_every_shipped_class_and_method_has_a_counterpart():
    """A class or a method exists on one side and nowhere on the other."""
    assert module_classes(shipped) == {"HistoryPanelAssetMissing", "HistoryWebTable"}
    assert len(module_classes(shipped)) == 2 == len(CLASS_MAP)
    assert set(CLASS_MAP) == module_classes(shipped)
    for target in CLASS_MAP.values():
        assert callable(getattr(surface, target)), target
    assert members(shipped.HistoryWebTable) == {
        "__init__",
        "page_ready",
        "model",
        "set_model",
        "row_count",
        "_push",
        "_on_load_finished",
    }
    assert len(members(shipped.HistoryWebTable)) == 7
    assert {name.split(".")[-1] for name in METHOD_MAP} == members(
        shipped.HistoryWebTable
    )
    assert len(METHOD_MAP) == 7
    for target in METHOD_MAP.values():
        assert resolve(target) is not None, target
    assert members(surface.HistoryPanelModel) == MODEL_MEMBERS
    assert len(MODEL_MEMBERS) == 10
    assert {target.split(".")[-1] for target in METHOD_MAP.values()} < MODEL_MEMBERS
    assert module_functions(shipped) == set(HELPER_MAP)
    assert len(HELPER_MAP) == 7
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert module_functions(surface) == set(HELPER_MAP.values()) | set(
        SURFACE_ONLY_FUNCTIONS
    )


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "set_model" in members(shipped.HistoryWebTable)
    assert "row_count" in members(shipped.HistoryWebTable)
    assert "logger" not in module_classes(shipped)
    assert "QWidget" not in module_classes(shipped)
    with pytest.raises(AttributeError):
        resolve("HistoryPanelModel.no_such_member")
    assert MODEL_MEMBERS - {"set_model"} != MODEL_MEMBERS
    assert members(surface.HistoryPanelModel) - {"row_count"} != MODEL_MEMBERS
    assert set(METHOD_MAP) - {"HistoryWebTable.row_count"} != set(METHOD_MAP)
    assert module_functions(shipped) - {"panel_html"} != set(HELPER_MAP)
    assert set(SURFACE_ONLY_FUNCTIONS) & module_functions(shipped) == set()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the host passes it."""
    import inspect

    for old_name, new_name in (
        ("__init__", "__init__"),
        ("model", "model"),
        ("set_model", "set_model"),
        ("row_count", "row_count"),
        ("_push", "_push"),
        ("_on_load_finished", "_on_load_finished"),
    ):
        old = list(
            inspect.signature(getattr(shipped.HistoryWebTable, old_name)).parameters
        )
        new = list(
            inspect.signature(getattr(surface.HistoryPanelModel, new_name)).parameters
        )
        assert new == old, old_name
    assert list(inspect.signature(shipped.HistoryWebTable.__init__).parameters) == [
        "self",
        "parent",
        "theme",
    ]
    theme_default = inspect.signature(shipped.HistoryWebTable.__init__).parameters[
        "theme"
    ]
    assert theme_default.default == surface.DEFAULT_THEME
    for old_name, new_name in HELPER_MAP.items():
        old = list(inspect.signature(getattr(shipped, old_name)).parameters)
        new = list(inspect.signature(getattr(surface, new_name)).parameters)
        assert new == old, old_name
    assert len(inspect.signature(shipped.build_view_model).parameters) == 10


def count_sites(path, needle):
    """How many times one wiring call appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    assert count_sites(PANEL_PATH, ".connect(") == PANEL_CONNECT_SITES == 1
    assert count_sites(SURFACE_PATH, ".connect(") == 0
    assert len(surface.ACTIONS) == count_sites(PANEL_PATH, ".connect(")
    assert set(surface.ACTIONS) == {"web.loadFinished"}
    assert count_sites(PANEL_PATH, "loadFinished.connect(") == 1
    assert count_sites(PANEL_PATH, "a-call-this-panel-never-makes") == 0
    panel = new_panel()
    assert panel._web.isSignalConnected(
        panel._web.metaObject().method(
            panel._web.metaObject().indexOfSignal("loadFinished(bool)")
        )
    )


def test_the_wired_signal_runs_the_method_the_surface_names():
    """The signal the surface names is wired to nothing."""
    panel = new_panel()
    model = surface.HistoryPanelModel()
    assert surface.ACTIONS["web.loadFinished"] == "_on_load_finished"
    assert callable(getattr(shipped.HistoryWebTable, "_on_load_finished"))
    assert callable(getattr(surface.HistoryPanelModel, "_on_load_finished"))
    panel._web.loadFinished.emit(True)
    model._on_load_finished(True)
    assert panel.page_ready is True
    assert model.page_ready is True
    assert model.connected == surface.ACTIONS


def test_the_panel_starts_no_timer():
    """A wait appeared on one side and not the other.

    The counter is proved able to report by counting a neighbouring file
    that really does start one, and by starting one under the watcher.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
    assert count_sites(PANEL_PATH, "QTimer") == PANEL_TIMER_SITES == 0
    assert count_sites(SURFACE_PATH, "QTimer") == 0
    assert count_sites(TIMER_NEIGHBOUR_PATH, "QTimer") > 0
    started: list = []
    original_start_timer = QObject.startTimer
    original_timer_start = QTimer.start
    original_single_shot = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return original_start_timer(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return original_timer_start(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", args))
        return original_single_shot(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        for name in ("held_then_loaded", "row_count_after_load"):
            old_host(name)
            new_host(name)
        observed = list(started)
        started.clear()
        QTimer().start(250)
    finally:
        QObject.startTimer = original_start_timer
        QTimer.start = original_timer_start
        QTimer.singleShot = original_single_shot
    assert started == [("QTimer.start", (250,))]
    assert observed == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(surface.TIMERS) == len(observed) == 0


def test_the_panel_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_sites(PANEL_PATH, ".subscribe(") == PANEL_BUS_SITES == 0
    assert count_sites(SURFACE_PATH, ".subscribe(") == 0
    assert count_sites(BUS_NEIGHBOUR_PATH, ".subscribe(") > 0
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_sites(PANEL_PATH, ".subscribe(")


def test_the_panel_declares_no_skin_of_its_own():
    """A colour the surface ships is one the panel never paints."""
    from qt_pixel import render_widget

    app()
    assert (
        colour_count(render_widget(real_panel("cyberpunk_dark"), SMALL_PIXEL_SIZE))
        == BROWSER_DRAWN_COLOUR_COUNT
    )
    assert surface.SKIN == {}
    assert surface.PANEL_STYLE_SHEET == ""
    assert new_panel().styleSheet() == ""
    assert real_panel("cyberpunk_dark").styleSheet() == ""
    assert surface.WIDGETS[0]["style_sheet"] == ""
    assert count_sites(PANEL_PATH, "setStyleSheet(") == 0
    assert count_sites(CHART_PATH, "background") > 0


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    import ast

    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            else:
                imported.update(alias.name for alias in node.names)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    assert imported == {
        "__future__",
        "datetime",
        "json",
        "pathlib",
        "src.exchange",
        "sys",
        "typing",
    }
    panel_tree = ast.parse(PANEL_PATH.read_text(encoding="utf-8"))
    panel_imports = {
        (node.module or "")
        for node in ast.walk(panel_tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in panel_imports), panel_imports


def test_the_widget_tree_is_the_panels_own():
    """A widget appeared on one side, or moved to another parent."""
    from PySide6.QtWidgets import QVBoxLayout

    app()
    panel = new_panel()
    assert [node["name"] for node in surface.WIDGETS] == list(surface.WIDGET_NAMES)
    assert len(surface.WIDGETS) == 2
    assert isinstance(panel.layout(), QVBoxLayout)
    assert panel.layout().count() == 1
    assert panel.layout().itemAt(0).widget() is panel._web
    assert surface.WIDGET_CHILDREN[""] == ("panel",)
    assert surface.WIDGET_CHILDREN["panel"] == ("web",)
    assert surface.WIDGET_PARENTS["web"] == "panel"
    assert surface.WIDGET_INDEX["web"] == 0
    assert surface.WIDGET_KINDS == {"panel": "QWidget", "web": "QWebEngineView"}
    assert surface.BUTTON_NAMES == ()
    assert surface.BUTTONS_ENABLED == {}
    real = real_panel("cyberpunk_dark")
    assert (
        real.layout()
        .itemAt(0)
        .widget()
        .metaObject()
        .className()
        .startswith("QWebEngineView")
    )


def test_the_host_takes_the_parent_the_caller_gives_it():
    """A parent the caller passed was dropped."""
    from PySide6.QtWidgets import QWidget

    app()
    owner = QWidget()
    HELD.append(owner)
    panel = new_panel(parent=owner)
    model = surface.HistoryPanelModel(parent=owner)
    assert panel.parent() is owner
    assert model.parent is owner
    assert surface.HistoryPanelModel().parent is None
    assert new_panel().parent() is None


# ---------------------------------------------------------------------
# Every value reaches the compared snapshot
# ---------------------------------------------------------------------


def normalise(value):
    """One value with every tuple turned into a list."""
    if isinstance(value, (list, tuple)):
        return [normalise(item) for item in value]
    if isinstance(value, dict):
        return {key: normalise(item) for key, item in value.items()}
    return value


def freeze(value):
    """One value as a single comparable string."""
    return json.dumps(normalise(value), sort_keys=True, default=str)


def surface_constants():
    """Every value the surface exports, by name."""
    import inspect

    found = {}
    for name, value in vars(surface).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) or inspect.isclass(value):
            continue
        if inspect.ismodule(value):
            continue
        if getattr(value, "__module__", "") in ("typing", "__future__"):
            continue
        if isinstance(value, surface.HistoryPanelModel):
            continue
        found[name] = value
    return found


def payload_values(payloads):
    """Every value any of these payloads carries, frozen for comparison."""
    found = set()

    def walk(value):
        found.add(freeze(value))
        if isinstance(value, dict):
            for key, item in value.items():
                found.add(freeze(key))
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for payload in payloads:
        walk(payload)
    return found


def compared_payloads():
    """The payloads the completeness check reads, one per driven path."""
    payloads = []
    held = surface.HistoryPanelModel()
    held.set_model(dict(PUSH_CASES["happy"]))
    held._on_load_finished(True)
    payloads.append(
        surface.build_payload(
            held,
            {
                "trades": TWO_TRADES,
                "filters": filters().as_dict(),
                "chrome": dict(surface.TABLE_ONLY_CHROME),
                "last_fetched_ts": BASE_TS,
                "now_ts": LATER_TS,
            },
            action="set_model",
        )
    )
    failed = surface.HistoryPanelModel()
    failed.set_model(dict(PUSH_CASES["unicode"]))
    payloads.append(
        surface.build_payload(failed, {"ok": False}, action="load_finished")
    )
    counted = surface.HistoryPanelModel()
    counted._on_load_finished(True)
    payloads.append(surface.build_payload(counted, {}, action="row_count"))
    refused = surface.HistoryPanelModel()
    payloads.append(surface.build_payload(refused, {}, action="row_count"))
    for theme in surface.THEME_NAMES:
        payloads.append(surface.build_payload(surface.HistoryPanelModel(theme=theme)))
    return payloads


COVERED_ELSEWHERE = {
    "ASSET_READ_MODE": "test_the_asset_read_is_the_shipped_panels",
    "BUILD_HTML": "test_the_recorded_calls_are_compared_as_values",
    "BUILD_RETURN": "test_the_recorded_calls_are_compared_as_values",
    "BUILD_START": "test_the_recorded_calls_are_compared_as_values",
    "HTML_JOIN": "test_the_page_is_the_shipped_panels",
    "LOAD_LOGGED": "test_the_recorded_calls_are_compared_as_values",
    "LOAD_PATH_FAILED": "test_every_host_case_reaches_the_path_it_names",
    "LOAD_PATH_PUSHED": "test_every_host_case_reaches_the_path_it_names",
    "LOAD_PATH_READY": "test_every_host_case_reaches_the_path_it_names",
    "LOAD_RETURN": "test_the_recorded_calls_are_compared_as_values",
    "LOAD_START": "test_the_recorded_calls_are_compared_as_values",
    "PUSH_CALL": "test_the_recorded_calls_are_compared_as_values",
    "ROW_COUNT_ASK": "test_the_recorded_calls_are_compared_as_values",
    "ROW_COUNT_PATH_ASKED": "test_every_host_case_reaches_the_path_it_names",
    "ROW_COUNT_PATH_REFUSED": "test_every_host_case_reaches_the_path_it_names",
    "ROW_COUNT_RETURN": "test_the_recorded_calls_are_compared_as_values",
    "ROW_COUNT_START": "test_the_recorded_calls_are_compared_as_values",
    "SET_MODEL_PATH_HELD": "test_every_host_case_reaches_the_path_it_names",
    "SET_MODEL_PATH_PUSHED": "test_every_host_case_reaches_the_path_it_names",
    "SET_MODEL_RETURN": "test_the_recorded_calls_are_compared_as_values",
    "SET_MODEL_START": "test_the_recorded_calls_are_compared_as_values",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped
    panel."""
    constants = surface_constants()
    assert len(constants) > 55
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops
    exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    assert "ROW_COUNT_JS" in missing_from_payload(surface_constants(), thinned)
    assert "THEME_CHROME" in missing_from_payload(surface_constants(), thinned)


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "accessible_name": ("ACCESSIBLE_NAME",),
    "logger_name": ("LOGGER_NAME",),
    "widgets": ("WIDGETS",),
    "widget_names": ("WIDGET_NAMES",),
    "widget_kinds": ("WIDGET_KINDS",),
    "widget_parents": ("WIDGET_PARENTS",),
    "widget_children": ("WIDGET_CHILDREN",),
    "widget_index": ("WIDGET_INDEX",),
    "button_names": ("BUTTON_NAMES",),
    "buttons_enabled": ("BUTTONS_ENABLED",),
    "panel_kind": ("PANEL_KIND",),
    "web_kind": ("WEB_KIND",),
    "layout_kind": ("LAYOUT_KIND",),
    "content_margins": ("CONTENT_MARGINS",),
    "content_spacing": ("CONTENT_SPACING",),
    "web_stretch": ("WEB_STRETCH",),
    "panel_style_sheet": ("PANEL_STYLE_SHEET",),
    "asset_names": ("ASSET_NAMES",),
    "style_asset": ("STYLE_ASSET",),
    "asset_subdir": ("ASSET_SUBDIR",),
    "asset_encoding": ("ASSET_ENCODING",),
    "asset_newline": ("ASSET_NEWLINE",),
    "asset_read_mode": ("ASSET_READ_MODE",),
    "bundle_attr": ("BUNDLE_ATTR",),
    "bundle_parts": ("BUNDLE_PARTS",),
    "asset_error_format": ("ASSET_ERROR_FORMAT",),
    "asset_dir": ("asset_dir",),
    "table_only_chrome": ("TABLE_ONLY_CHROME",),
    "row_count_js": ("ROW_COUNT_JS",),
    "default_theme": ("DEFAULT_THEME",),
    "theme_names": ("THEME_NAMES",),
    "theme_chrome": ("THEME_CHROME",),
    "palette_keys": ("PALETTE_KEYS",),
    "palette_source_keys": ("PALETTE_SOURCE_KEYS",),
    "palette": ("palette",),
    "html_parts": (
        "HTML_DOCTYPE",
        "HTML_HEAD_OPEN",
        "HTML_STYLE_OPEN",
        "HTML_ROOT_OPEN",
        "HTML_ROOT_CLOSE",
        "HTML_STYLE_CLOSE",
        "HTML_ROOT_DIV",
        "HTML_SCRIPT_OPEN",
        "HTML_SCRIPT_CLOSE",
        "HTML_TAIL",
    ),
    "html_join": ("HTML_JOIN",),
    "override_format": ("OVERRIDE_FORMAT",),
    "override_join": ("OVERRIDE_JOIN",),
    "html_length": ("model.html",),
    "date_format": ("DATE_FORMAT",),
    "date_any_text": ("DATE_ANY_TEXT",),
    "date_inactive_max": ("DATE_INACTIVE_MAX",),
    "push_function": ("PUSH_FUNCTION",),
    "push_prefix": ("PUSH_PREFIX",),
    "push_suffix": ("PUSH_SUFFIX",),
    "push_ensure_ascii": ("PUSH_ENSURE_ASCII",),
    "default_page": ("DEFAULT_PAGE",),
    "default_last_fetched_ts": ("DEFAULT_LAST_FETCHED_TS",),
    "no_chrome": ("NO_CHROME",),
    "load_failed_message": ("LOAD_FAILED_MESSAGE",),
    "load_failed_level": ("LOAD_FAILED_LEVEL",),
    "no_path": ("NO_PATH",),
    "set_model_paths": ("SET_MODEL_PATHS",),
    "row_count_paths": ("ROW_COUNT_PATHS",),
    "load_paths": ("LOAD_PATHS",),
    "call_names": (
        "BUILD_START",
        "BUILD_HTML",
        "BUILD_RETURN",
        "SET_MODEL_START",
        "SET_MODEL_RETURN",
        "ROW_COUNT_START",
        "ROW_COUNT_ASK",
        "ROW_COUNT_RETURN",
        "LOAD_START",
        "LOAD_LOGGED",
        "LOAD_RETURN",
        "PUSH_CALL",
    ),
    "actions": ("ACTIONS",),
    "bridge_actions": ("BRIDGE_ACTIONS",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "bus_topics": ("BUS_TOPICS",),
    "skin": ("SKIN",),
    "theme": ("model.theme",),
    "page_ready": ("model.page_ready",),
    "state": ("model.model",),
    "view": ("view",),
    "pushes": ("model.pushes",),
    "scripts": ("model.scripts",),
    "callback_count": ("model.callbacks",),
    "logs": ("model.logs",),
    "set_model_path": ("model.set_model_path",),
    "row_count_path": ("model.row_count_path",),
    "load_path": ("model.load_path",),
    "has_parent": ("model.parent",),
    "connected": ("model.connected",),
    "calls": ("model.calls",),
}


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("model."):
        found = getattr(model, name.split(".", 1)[1])
    elif name == "view":
        return None
    else:
        found = getattr(surface, name)
    return found() if callable(found) and name != "palette" else found


def backed(key, value, sources, model):
    """Whether one payload key carries exactly what its named sources hold."""
    if key == "has_parent":
        return value is (model.parent is not None)
    if key == "html_length":
        return value == len(model.html)
    if key == "callback_count":
        return value == len(model.callbacks)
    if key == "palette":
        return value == surface.palette(model.theme)
    if key == "view":
        return value is None or isinstance(value, dict)
    resolved = [resolve_source(name, model) for name in sources]
    if len(sources) == 1:
        return freeze(value) == freeze(resolved[0])
    return [freeze(item) for item in value] == [freeze(item) for item in resolved]


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model = surface.HistoryPanelModel()
    model._on_load_finished(True)
    model.set_model(dict(PUSH_CASES["happy"]))
    payload = surface.build_payload(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES)
    assert len(payload) == 78
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(model, name.split(".", 1)[1]), name
            elif name != "view":
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, model), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = surface.HistoryPanelModel()
    payload = surface.build_payload(model)
    assert backed("row_count_js", payload["row_count_js"], ("ROW_COUNT_JS",), model)
    assert not backed("row_count_js", "document.body", ("ROW_COUNT_JS",), model)
    assert not backed("asset_names", ["one.js"], ("ASSET_NAMES",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("html_length", 0, ("model.html",), model)
    assert not backed("callback_count", 9, ("model.callbacks",), model)
    assert not backed("palette", {"--bg": "#000000"}, ("palette",), model)


def test_the_recorded_calls_are_compared_as_values():
    """A step the host takes stopped being recorded, or moved in order."""
    model = surface.HistoryPanelModel()
    assert model.calls[0] == [surface.BUILD_START, surface.DEFAULT_THEME]
    assert model.calls[1] == [surface.BUILD_HTML, len(model.html)]
    assert model.calls[2] == [surface.BUILD_RETURN, 2]
    model.set_model(dict(PUSH_CASES["happy"]))
    assert model.calls[3] == [surface.SET_MODEL_START, False]
    assert model.calls[4] == [surface.SET_MODEL_RETURN, surface.SET_MODEL_PATH_HELD, 0]
    assert model.row_count(row_count_callback) is False
    assert model.calls[5] == [surface.ROW_COUNT_START, False]
    assert model.calls[6] == [
        surface.ROW_COUNT_RETURN,
        surface.ROW_COUNT_PATH_REFUSED,
        0,
    ]
    model._on_load_finished(True)
    assert model.calls[7] == [surface.LOAD_START, True]
    assert model.calls[8] == [surface.PUSH_CALL, len(model.pushes[0])]
    assert model.calls[9] == [surface.LOAD_RETURN, surface.LOAD_PATH_PUSHED, True]
    assert model.row_count(row_count_callback) is True
    assert model.calls[11] == [surface.ROW_COUNT_ASK, surface.ROW_COUNT_JS, True]
    model._on_load_finished(False)
    assert model.calls[-3] == [surface.LOAD_START, False]
    assert model.calls[-2] == [surface.LOAD_LOGGED, surface.LOAD_FAILED_MESSAGE]
    assert model.calls[-1] == [surface.LOAD_RETURN, surface.LOAD_PATH_FAILED, False]
    assert len(model.calls) == 16


# ---------------------------------------------------------------------
# The values are the surface's own, not the shipped panel's
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_panel():
    """The surface reads the shipped panel, so the two can never disagree."""
    from qt_pixel import render_widget

    from src.gui import tradingview_chart

    app()
    assert (
        colour_count(render_widget(real_panel("cyberpunk_dark"), SMALL_PIXEL_SIZE))
        == BROWSER_DRAWN_COLOUR_COUNT
    )
    original_themes = tradingview_chart.CHART_THEMES
    original_assets = shipped.ASSET_NAMES
    original_style = shipped.STYLE_ASSET
    original_script = shipped.ROW_COUNT_JS
    original_chrome = shipped.TABLE_ONLY_CHROME
    try:
        tradingview_chart.CHART_THEMES = {
            "cyberpunk_dark": {
                "bg": "#111111",
                "text": "#222222",
                "grid": "#333333",
                "border": "#444444",
                "accent": "#555555",
                "btn_bg": "#666666",
            }
        }
        shipped.ASSET_NAMES = ("history_panel.js",)
        shipped.STYLE_ASSET = "no_such.css"
        shipped.ROW_COUNT_JS = "document.body"
        shipped.TABLE_ONLY_CHROME = {"summary": True}
        assert shipped._palette("cyberpunk_dark")["--bg"] == "#111111"
        assert surface.palette("cyberpunk_dark")["--bg"] == CYBERPUNK_BG
        assert surface.ASSET_NAMES != shipped.ASSET_NAMES
        assert len(surface.ASSET_NAMES) == 3
        assert surface.STYLE_ASSET == "history_panel.css"
        assert surface.ROW_COUNT_JS != shipped.ROW_COUNT_JS
        assert surface.TABLE_ONLY_CHROME == {
            "summary": False,
            "filters": False,
            "pager": False,
        }
        assert guarded(lambda: surface.panel_html("cyberpunk_dark"))["error"] == ""
        assert (
            guarded(lambda: shipped.panel_html("cyberpunk_dark"))["error"]
            == "HistoryPanelAssetMissing"
        )
    finally:
        tradingview_chart.CHART_THEMES = original_themes
        shipped.ASSET_NAMES = original_assets
        shipped.STYLE_ASSET = original_style
        shipped.ROW_COUNT_JS = original_script
        shipped.TABLE_ONLY_CHROME = original_chrome
    assert surface.panel_html("cyberpunk_dark") == shipped.panel_html("cyberpunk_dark")
    assert surface.palette("neon_light") == shipped._palette("neon_light")


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def call_bridge(params):
    """One request through the real bridge, returning the whole frame."""
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": 1, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model = surface.HistoryPanelModel()
    model._on_load_finished(True)
    payload = surface.build_payload(model, {}, action="row_count")
    encoded = json.loads(json.dumps(payload))
    assert encoded["method"] == "react_history_panel.state"
    assert encoded["accessible_name"] == "React History Table"
    assert encoded["row_count_js"] == surface.ROW_COUNT_JS
    assert encoded["scripts"] == [surface.ROW_COUNT_JS]
    assert encoded["theme_chrome"]["neon_light"]["accent"] == NEON_ACCENT


def test_bridge_registers_the_react_history_panel_method():
    """The frontend cannot reach the History table."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model
    assert "react_history_panel.state" in registry
    frame = call_bridge({"reset": True})
    assert frame["ok"] is True
    assert frame["result"]["method"] == surface.METHOD
    assert frame["result"]["page_ready"] is False
    unknown = desktop_bridge.handle_line(
        json.dumps({"id": 2, "method": "react_history_panel.no_such"}), registry
    )
    assert unknown["ok"] is False


def test_the_bridge_carries_every_action():
    """An action the bridge names does nothing when it is asked for."""
    call_bridge({"reset": True})
    loaded = call_bridge({"action": "load_finished", "ok": True})
    assert loaded["result"]["page_ready"] is True
    assert loaded["result"]["load_path"] == surface.LOAD_PATH_READY
    counted = call_bridge({"action": "row_count"})
    assert counted["result"]["scripts"] == [surface.ROW_COUNT_JS]
    assert counted["result"]["row_count_path"] == surface.ROW_COUNT_PATH_ASKED
    pushed = call_bridge(
        {
            "action": "set_model",
            "trades": [
                {
                    "id": "t-1",
                    "exchange": "coinbase",
                    "symbol": "CHIP/USD",
                    "side": "BUY",
                    "amount": 2.0,
                    "price": 10.0,
                    "cost": 20.0,
                    "fee": 0.01,
                    "fee_currency": "USD",
                    "timestamp": BASE_TS,
                }
            ],
            "filters": {"side": "BUY"},
            "chrome": dict(surface.TABLE_ONLY_CHROME),
        }
    )
    assert pushed["result"]["set_model_path"] == surface.SET_MODEL_PATH_PUSHED
    assert pushed["result"]["view"]["loaded"] == 1
    assert pushed["result"]["view"]["filters"]["side"] == "BUY"
    assert pushed["result"]["view"]["chrome"] == surface.TABLE_ONLY_CHROME
    assert len(pushed["result"]["pushes"]) == 1
    assert set(surface.BRIDGE_ACTIONS) == {"set_model", "row_count", "load_finished"}
    call_bridge({"reset": True})


def test_the_bridge_keeps_the_page_until_a_reset():
    """A second request forgot the page the first one brought up."""
    call_bridge({"reset": True})
    call_bridge({"action": "load_finished", "ok": True})
    assert call_bridge({})["result"]["page_ready"] is True
    themed = call_bridge({"reset": True, "theme": "neon_light"})
    assert themed["result"]["theme"] == "neon_light"
    assert themed["result"]["page_ready"] is False
    assert themed["result"]["palette"]["--accent"] == NEON_ACCENT
    back = call_bridge({"reset": True})
    assert back["result"]["theme"] == surface.DEFAULT_THEME


def test_the_bridge_reports_a_request_it_cannot_serve():
    """A bad request ends the session instead of answering."""
    frame = call_bridge({"reset": True, "trades": 7, "filters": {}})
    assert frame["ok"] is False
    assert frame["error"]["type"] == "TypeError"
    assert call_bridge({"reset": True})["ok"] is True


# ---------------------------------------------------------------------
# Without Qt at all
# ---------------------------------------------------------------------

BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

BRIDGE_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'react_history_panel.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = (
    BLOCK_QT + "import hashlib, json, sys\n"
    "from src.gui.main_tabs import react_history_panel_surface as s\n"
    "model = s.HistoryPanelModel(theme='neon_light')\n"
    "model.set_model({'symbol': 'it\\u2019s <b>x</b>'})\n"
    "held = model.set_model_path\n"
    "model._on_load_finished(True)\n"
    "model.row_count(len)\n"
    "page = s.panel_html('neon_light')\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'page_digest': hashlib.sha256(page.encode()).hexdigest(),\n"
    "    'page_len': len(page), 'held': held,\n"
    "    'load_path': model.load_path, 'row_count_path': model.row_count_path,\n"
    "    'pushes': model.pushes, 'scripts': model.scripts,\n"
    "    'palette': s.palette('neon_light'), 'widgets': len(s.WIDGETS),\n"
    "    'calls': len(model.calls)}))\n"
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
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the History table pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == "react_history_panel.state"
    assert result["accessible_name"] == "React History Table"
    assert result["asset_names"] == [
        "vendor/react.production.min.js",
        "vendor/react-dom.production.min.js",
        "history_panel.js",
    ]
    assert result["row_count_js"] == surface.ROW_COUNT_JS
    assert result["content_margins"] == [0, 0, 0, 0]
    assert result["table_only_chrome"] == {
        "summary": False,
        "filters": False,
        "pager": False,
    }
    assert result["pushes"] == []
    assert result["scripts"] == []


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_the_page_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["page_len"] == len(surface.panel_html("neon_light"))
    assert answered["page_digest"] == text_digest(shipped.panel_html("neon_light"))
    assert answered["held"] == surface.SET_MODEL_PATH_HELD
    assert answered["load_path"] == surface.LOAD_PATH_PUSHED
    assert answered["row_count_path"] == surface.ROW_COUNT_PATH_ASKED
    assert answered["scripts"] == [surface.ROW_COUNT_JS]
    assert len(answered["pushes"]) == 1
    assert answered["pushes"][0].startswith(surface.PUSH_PREFIX)
    assert "\\u2019" in answered["pushes"][0]
    assert answered["palette"]["--accent"] == NEON_ACCENT
    assert answered["widgets"] == 2
    assert answered["calls"] == 11


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_hosts_the_page():
    """The Qt block let the shipped panel through."""
    probe = BLOCK_QT + (
        "import json\n"
        "from src.gui import react_history_panel as p\n"
        "print(json.dumps({'built': hasattr(p, 'HistoryWebTable'),\n"
        "    'has_web': p._HAS_WEBENGINE,\n"
        "    'page_len': len(p.panel_html())}))\n"
    )
    answered = run_script(probe)
    assert answered["has_web"] is False
    assert answered["built"] is False
    assert answered["page_len"] == len(surface.panel_html())
