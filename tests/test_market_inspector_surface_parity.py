"""The shipped Market Inspector screen and the Qt-free surface, side by side.

A failure means the view model carries a different button, a different
colour, a different tooltip, a different heading, a different table row,
a different status line, a different recorded step or a different
refusal than ``MarketInspectorTab`` or ``build_per_bot_view``.

No test here reads or writes the operator's runtime tree, opens a socket
or reaches an exchange. Every symbol, signal, score and correlation
below is invented.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import market_inspector as shipped
from src.gui.main_tabs import market_inspector_surface as surface
from src.trading import market_inspector as analyzer
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
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

SCREEN_PATH = REPO_ROOT / "src/gui/market_inspector.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/market_inspector_surface.py"
RIGHT_PANE_PATH = REPO_ROOT / "src/gui/market_inspector_topologies.py"
WIRING_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_CONTROL_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_CONTROL_PATH = REPO_ROOT / "src/gui/history_tab.py"
TIMER_NEIGHBOUR_PATH = REPO_ROOT / "src/gui/main_tabs/history_tab.py"
BUS_CONTROL_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
ELEMENT_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/dashboard_stat_card.py"
NESTED_CLASS_CONTROL_PATH = REPO_ROOT / "src/gui/stock_main_window.py"

PIXEL_SIZE = (1100, 760)

SHARED_INSPECTOR_NAME = "_GLOBAL_INSPECTOR"

# Counts measured off the file by the same counter that is pointed at a
# neighbour which really has one.
SCREEN_CONNECT_SITES = 3
SCREEN_TIMER_BUILDS = 0
SCREEN_BUS_SITES = 0
SCREEN_SIGNAL_BUILDS = 0
SCREEN_ELEMENT_BUILDS = 32
CONTROL_CONNECT_SITES = 1
CONTROL_TIMER_BUILDS = 1
CONTROL_BUS_SITES = 2
CONTROL_SIGNAL_BUILDS = 3
CONTROL_ELEMENT_BUILDS = 3

# Invented values. No symbol, score or correlation below is a market
# reading; all of them are written for this file.
UNICODE_SYMBOL = "Δ→⚡"
MARKUP_SYMBOL = "<b>BTC</b>"
APOSTROPHE_SYMBOL = "Ekthelius" + chr(39) + " Coin"
NEWLINE_SYMBOL = "two\nlines"
LONG_SYMBOL = "x" * 200

WIDGETS_HELD: list = []


def app():
    """The process application object every widget needs."""
    from tests.qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


def hold(widget):
    """Keep one widget alive so no later read reaches a collected object."""
    WIDGETS_HELD.append(widget)
    return widget


# The analyzer is process-wide, and BOTH screens read it through one
# accessor. Every test is given its own and the process one is put back.


@pytest.fixture(autouse=True)
def own_shared_inspector(monkeypatch):
    """Give this test its own analyzer and restore the process one after.

    ``get_shared_inspector`` returns one object for the whole process,
    both screens reach it through that one function, and the top-level
    screen writes its scan into it, so a scan a test leaves behind would
    decide what a later test draws. The guard refuses outright when the
    module no longer carries the name it resets, because a reset aimed
    at an absent name creates a fresh attribute and resets nothing.
    """
    if not hasattr(analyzer, SHARED_INSPECTOR_NAME):
        raise AssertionError(
            "src.trading.market_inspector no longer carries "
            f"{SHARED_INSPECTOR_NAME}; this guard would create that name "
            "instead of resetting the real shared analyzer, and every "
            "test in this file would share one object."
        )
    monkeypatch.setattr(analyzer, SHARED_INSPECTOR_NAME, None)
    yield
    monkeypatch.setattr(analyzer, SHARED_INSPECTOR_NAME, None)


def shared_inspector():
    """The analyzer both screens read, through the accessor both call."""
    return analyzer.get_shared_inspector()


def seat_inspector(signals, pairs):
    """Put one analyzer stand-in in the process-wide seat and return it.

    Called once per SIDE, so the screen that runs first cannot decide
    what the screen that runs second reads.
    """
    setattr(
        analyzer,
        SHARED_INSPECTOR_NAME,
        surface.InspectorSource(signals=signals, pairs=pairs),
    )
    return getattr(analyzer, SHARED_INSPECTOR_NAME)


# Invented market readings, and the case table both sides are driven with


def reading(**over):
    """One timeframe reading, at the upper band and tightening."""
    base = {
        "bb_position": 0.90,
        "z_score": 2.50,
        "tightening": True,
        "at_upper_extreme": True,
        "at_lower_extreme": False,
    }
    base.update(over)
    return surface.TimeframeState(**base)


def signal(**over):
    """One market signal, a high long entry by default."""
    base = {
        "symbol": "BTC",
        "signal": "ENTRY_LONG_HIGH",
        "score": 3.0,
        "direction": "long",
        "per_tf": {
            "1d": reading(),
            "1w": reading(
                bb_position=0.10,
                z_score=-1.20,
                tightening=False,
                at_upper_extreme=False,
                at_lower_extreme=True,
            ),
        },
        "is_active": False,
    }
    base.update(over)
    return surface.SignalState(**base)


def pair(long_side, short_side, correlation=-0.75):
    """One opposing pair over two signals."""
    return surface.PairState(long_side, short_side, correlation)


def one_signal(**over):
    """A screen holding a single signal and no pairs."""
    return {"signals": [signal(**over)], "pairs": [], "meta": {}}


def paired(**over):
    """A screen holding two signals and the pair over them."""
    long_side = signal(**over)
    short_side = signal(
        symbol="ETH", signal="ENTRY_SHORT", score=2.0, direction="short"
    )
    return {
        "signals": [long_side, short_side],
        "pairs": [pair(long_side, short_side)],
        "meta": {"source": "coingecko", "symbol_count": 2},
    }


CASES: dict = {
    "happy": lambda: paired(),
    "empty": lambda: {"signals": [], "pairs": [], "meta": {}},
    "zero_score": lambda: one_signal(score=0.0),
    "negative_score": lambda: one_signal(score=-2.0),
    "thousand_million": lambda: one_signal(score=1_000_000_000.0),
    "one_billionth": lambda: one_signal(score=1e-9),
    "whole_number_score": lambda: one_signal(score=12),
    "decimal_number_score": lambda: one_signal(score=12.0),
    "infinite_score": lambda: one_signal(score=float("inf")),
    "minus_infinite_score": lambda: one_signal(score=float("-inf")),
    "not_a_number_score": lambda: one_signal(score=float("nan")),
    "unicode": lambda: one_signal(symbol=UNICODE_SYMBOL),
    "markup": lambda: one_signal(symbol=MARKUP_SYMBOL),
    "apostrophe": lambda: one_signal(symbol=APOSTROPHE_SYMBOL),
    "newline": lambda: one_signal(symbol=NEWLINE_SYMBOL),
    "long": lambda: one_signal(symbol=LONG_SYMBOL),
    "wrong_capitals": lambda: one_signal(signal="entry_long_high"),
    "unnamed_signal": lambda: one_signal(signal=""),
    "watchlist": lambda: one_signal(signal="WATCHLIST", direction=""),
    "short_high": lambda: one_signal(signal="ENTRY_SHORT_HIGH", direction="short"),
    "short_low": lambda: one_signal(signal="ENTRY_SHORT_LOW", direction="short"),
    "long_medium": lambda: one_signal(signal="ENTRY_LONG_MEDIUM"),
    "scored_but_unsignalled": lambda: one_signal(signal="NONE"),
    "active": lambda: one_signal(is_active=True),
    "no_timeframes": lambda: one_signal(per_tf={}),
    "daily_only": lambda: one_signal(per_tf={"1d": reading()}),
    "mid_band": lambda: one_signal(
        per_tf={"1d": reading(at_upper_extreme=False, tightening=False)}
    ),
    "lower_band": lambda: one_signal(
        per_tf={
            "1d": reading(
                at_upper_extreme=False, at_lower_extreme=True, tightening=False
            )
        }
    ),
    "infinite_band": lambda: one_signal(
        per_tf={"1d": reading(bb_position=float("inf"), z_score=float("-inf"))}
    ),
    "not_a_number_band": lambda: one_signal(
        per_tf={"1d": reading(bb_position=float("nan"), z_score=float("nan"))}
    ),
    "three_rows": lambda: {
        "signals": [
            signal(symbol="ALPHA", score=3.0),
            signal(symbol="BETA", score=2.0, signal="ENTRY_LONG"),
            signal(symbol="GAMMA", score=1.0, signal="WATCHLIST"),
        ],
        "pairs": [],
        "meta": {},
    },
    "one_row": lambda: {"signals": [signal(symbol="ALPHA")], "pairs": [], "meta": {}},
    "mixed_scores": lambda: {
        "signals": [
            signal(symbol="ALPHA", score=3.0),
            signal(symbol="BETA", score=0.0, signal="NONE"),
            signal(symbol="GAMMA", score=1.0, is_active=True),
        ],
        "pairs": [],
        "meta": {},
    },
    "negative_correlation": lambda: paired(),
    "positive_correlation": lambda: {
        "signals": [signal(symbol="ALPHA"), signal(symbol="BETA")],
        "pairs": [pair(signal(symbol="ALPHA"), signal(symbol="BETA"), 0.90)],
        "meta": {},
    },
    "infinite_correlation": lambda: {
        "signals": [signal(symbol="ALPHA")],
        "pairs": [pair(signal(symbol="ALPHA"), signal(symbol="BETA"), float("inf"))],
        "meta": {},
    },
    "not_a_number_correlation": lambda: {
        "signals": [signal(symbol="ALPHA")],
        "pairs": [pair(signal(symbol="ALPHA"), signal(symbol="BETA"), float("nan"))],
        "meta": {},
    },
    "live_source": lambda: {
        "signals": [signal()],
        "pairs": [],
        "meta": {"source": "coingecko", "symbol_count": 7},
    },
    "cache_source": lambda: {
        "signals": [signal()],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": 3600.0, "symbol_count": 2},
    },
    "cache_with_fallback": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {
            "source": "cache",
            "age_seconds": 90.0,
            "symbol_count": 2,
            "error": "rate limited",
        },
    },
    "cache_one_second": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": 1.5, "symbol_count": 1},
    },
    "cache_two_days": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": 200000.0, "symbol_count": 1},
    },
    "cache_hours_and_minutes": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": 3660.0, "symbol_count": 1},
    },
    "cache_negative_age": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": -5.0, "symbol_count": 1},
    },
    "cache_minus_infinite_age": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": float("-inf"), "symbol_count": 1},
    },
    "cache_not_a_number_age": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": float("nan"), "symbol_count": 1},
    },
    "cache_one_billionth_age": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": 1e-9, "symbol_count": 1},
    },
    "cache_thousand_million_age": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": 1e9, "symbol_count": 1},
    },
    "error_source": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "error", "error": "venue down"},
    },
    "error_without_words": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "error"},
    },
    "partial_source": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "network-partial", "error": ""},
    },
    "partial_with_words": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "network-partial", "error": "two markets only"},
    },
    "unknown_source": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "weird"},
    },
    "unicode_error": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "error", "error": UNICODE_SYMBOL},
    },
    "markup_error": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "error", "error": MARKUP_SYMBOL},
    },
    "newline_error": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "error", "error": NEWLINE_SYMBOL},
    },
    "long_error": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "error", "error": LONG_SYMBOL},
    },
    "count_where_text_belongs": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "error", "error": 5},
    },
    "infinite_age": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "cache", "age_seconds": float("inf"), "symbol_count": 1},
    },
    "text_where_a_number_belongs": lambda: {
        "signals": [],
        "pairs": [],
        "meta": {"source": "coingecko", "symbol_count": "many"},
    },
    "number_where_text_belongs": lambda: one_signal(signal=5),
    "signal_is_missing": lambda: one_signal(signal=None),
    "band_is_text": lambda: one_signal(per_tf={"1d": "not a reading"}),
}

# The inputs both sides refuse, named so the outcome check can prove its
# set holds a refusal as well as an answer.
REFUSING = (
    "infinite_age",
    "text_where_a_number_belongs",
    "number_where_text_belongs",
    "signal_is_missing",
    "band_is_text",
)

SEQUENCES: dict = {
    "shrink": ["three_rows", "one_row"],
    "grow": ["one_row", "three_rows"],
    "empty_then_full": ["empty", "three_rows"],
    "full_then_empty": ["three_rows", "empty"],
    "same_twice": ["happy", "happy"],
    "refuse_then_answer": ["number_where_text_belongs", "happy"],
    "answer_then_refuse": ["happy", "infinite_age"],
    "three_steps": ["three_rows", "band_is_text", "one_row"],
    "source_changes": ["live_source", "cache_source", "error_source"],
}

PICTURE_CASES = (
    "happy",
    "empty",
    "three_rows",
    "active",
    "watchlist",
    "unicode",
    "long",
    "cache_with_fallback",
)

PER_BOT_CASES = (
    "happy",
    "empty",
    "three_rows",
    "mixed_scores",
    "active",
    "unicode",
    "long",
    "markup",
    "not_a_number_score",
)

PER_BOT_SYMBOLS = (
    "BTC/USD",
    "btc",
    "",
    "ALPHA/USD",
    "GAMMA/USD",
    "DOGE/USD",
    UNICODE_SYMBOL + "/USD",
    LONG_SYMBOL,
    NEWLINE_SYMBOL,
)

FLEET_LISTS: dict = {
    "empty_fleet": [],
    "no_fleet_at_all": None,
    "one_pair": [{"symbol": "BTC/USD"}],
    "bare_symbol": [{"symbol": "eth"}],
    "blank_symbol": [{"symbol": ""}],
    "no_symbol_key": [{}],
    "two_spellings": [{"symbol": "BTC/USD"}, {"symbol": "btc/usd"}],
    "unicode_symbol": [{"symbol": UNICODE_SYMBOL + "/USD"}],
    "long_symbol": [{"symbol": LONG_SYMBOL}],
    "number_where_text_belongs": [{"symbol": 5}],
    "nothing_where_text_belongs": [{"symbol": None}],
}

FLEET_REFUSING = ("number_where_text_belongs", "nothing_where_text_belongs")


# Reading the two sides into one shape


def numbered(value):
    """One value with every number replaced by its own text.

    ``12`` and ``12.0`` are equal as numbers and hash apart, and two
    not-a-numbers are never equal to each other. Reading each number as
    its own text tells the first pair apart and lets the second pair
    agree.
    """
    if isinstance(value, bool):
        return ["bool", repr(value)]
    if isinstance(value, (int, float)):
        return [type(value).__name__, repr(value)]
    if isinstance(value, dict):
        return {key: numbered(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [numbered(item) for item in value]
    return value


SETTLED_MARK = "<a size this machine settled on>"
ASKED_PANE_SIZES = frozenset({tuple(surface.SPLITTER_SIZES_PX)})


def platform_chosen(value):
    """One value with anything the machine chose replaced by a marker.

    A splitter reports the widths it settled on, not the widths it was
    given: ``setSizes((800, 800))`` reads back as the space the host
    happened to have. Everything this test asked for is kept.
    """
    if isinstance(value, dict):
        found = {}
        for key, item in value.items():
            if key == "pane_sizes_px" and tuple(item) not in ASKED_PANE_SIZES:
                found[key] = SETTLED_MARK
            else:
                found[key] = platform_chosen(item)
        return found
    if isinstance(value, (list, tuple)):
        return [platform_chosen(item) for item in value]
    return value


def readable(value):
    """One value ready to compare: machine values hidden, numbers as text."""
    return numbered(platform_chosen(value))


def digest(body):
    """One case's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(readable(body), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def guarded(run):
    """Run one drive, keeping either that it worked or how it refused.

    Only the refusal TYPE is kept. Python words one failure differently
    between versions, so a wording written down here would pin the
    machine this file was written on.
    """
    try:
        run()
        return {"error": ""}
    except Exception as exc:
        return {"error": type(exc).__name__}


def headline_of(run):
    """The first line of a refusal, read off whichever side is driven."""
    try:
        run()
        return ""
    except Exception as exc:
        return str(exc).splitlines()[:1]


def painted(colour):
    """One declared colour as the name a painted cell reports.

    ``#888`` and ``#888888`` are one colour and two strings. The shipped
    side reports the six-digit spelling because Qt expands it, so the
    surface's declared spelling is read through the same expansion
    before the two are compared.
    """
    from PySide6.QtGui import QColor

    if colour is None:
        return None
    if not colour:
        return ""
    return QColor(colour).name()


def cell_of(table, row, column):
    """One table cell as its text and the colour it was given."""
    item = table.item(row, column)
    if item is None:
        return [None, None]
    brush = item.foreground()
    if brush.style().name == "NoBrush":
        return [item.text(), ""]
    return [item.text(), brush.color().name()]


def table_rows(table):
    """Every drawn cell of one table, row by row."""
    return [
        [cell_of(table, row, column) for column in range(table.columnCount())]
        for row in range(table.rowCount())
    ]


def headers_of(table):
    """The heading over each column of one table."""
    return [
        table.horizontalHeaderItem(column).text()
        for column in range(table.columnCount())
    ]


def margins_of(layout):
    """The four margins one layout holds."""
    found = layout.contentsMargins()
    return [found.left(), found.top(), found.right(), found.bottom()]


def read_old(tab):
    """One shipped screen read into the one shape both sides use."""
    left = tab._outer_splitter.widget(0)
    top = left.layout().itemAt(0).layout()
    signals_table = tab._signals_tbl
    return {
        "accessible_name": tab.accessibleName(),
        "style_sheet": tab.styleSheet(),
        "refresh_label": tab._refresh_btn.text(),
        "refresh_tooltip": tab._refresh_btn.toolTip(),
        "refresh_enabled": tab._refresh_btn.isEnabled(),
        "show_active_label": tab._show_active_chk.text(),
        "show_active_checked": tab._show_active_chk.isChecked(),
        "show_active_tooltip": tab._show_active_chk.toolTip(),
        "show_active": tab._show_active,
        "status_text": tab._status_lbl.text(),
        "status_style": tab._status_lbl.styleSheet(),
        "signals_group_title": tab._signals_group.title(),
        "signal_columns": headers_of(signals_table),
        "signals_max_height_px": signals_table.maximumHeight(),
        "signal_rows": table_rows(signals_table),
        "pairs_group_title": tab._pairs_group.title(),
        "pair_columns": headers_of(tab._pairs_tbl),
        "pairs_max_height_px": tab._pairs_tbl.maximumHeight(),
        "pair_rows": table_rows(tab._pairs_tbl),
        "table_resize_mode": (
            signals_table.horizontalHeader().sectionResizeMode(0).name
        ),
        "table_edit_triggers": signals_table.editTriggers().name,
        "table_alternating_rows": signals_table.alternatingRowColors(),
        "splitter_orientation": tab._outer_splitter.orientation().name,
        "splitter_panes": tab._outer_splitter.count(),
        "outer_margins_px": margins_of(tab.layout()),
        "outer_spacing_px": tab.layout().spacing(),
        "left_margins_px": margins_of(left.layout()),
        "left_spacing_px": left.layout().spacing(),
        "top_row_spacing_px": top.spacing(),
        "top_row_items": top.count(),
        "left_items": left.layout().count(),
        "active_symbols": sorted(tab._active_symbols),
        "last_meta": dict(tab._last_meta),
        "pending_refresh": tab._pending_refresh,
        "exchange_source_wired": bool(tab._connectors_getter and tab._scheduler),
    }


TOP_ROW_ITEM_COUNT = 4
LEFT_ITEM_COUNT = 4


def read_new(payload):
    """One surface screen read into the one shape both sides use."""
    return {
        "accessible_name": payload["accessible_name"],
        "style_sheet": payload["style_sheet"],
        "refresh_label": payload["refresh_label"],
        "refresh_tooltip": payload["refresh_tooltip"],
        "refresh_enabled": payload["refresh_enabled"],
        "show_active_label": payload["show_active_label"],
        "show_active_checked": payload["show_active_checked"],
        "show_active_tooltip": payload["show_active_tooltip"],
        "show_active": payload["show_active"],
        "status_text": payload["status_text"],
        "status_style": payload["status_style"],
        "signals_group_title": payload["signals_group_title"],
        "signal_columns": payload["signal_columns"],
        "signals_max_height_px": payload["signals_max_height_px"],
        "signal_rows": [
            [[text, painted(colour)] for text, colour in row]
            for row in payload["signal_rows"]
        ],
        "pairs_group_title": payload["pairs_group_title"],
        "pair_columns": payload["pair_columns"],
        "pairs_max_height_px": payload["pairs_max_height_px"],
        "pair_rows": [
            [[text, painted(colour)] for text, colour in row]
            for row in payload["pair_rows"]
        ],
        "table_resize_mode": payload["table_resize_mode"],
        "table_edit_triggers": payload["table_edit_triggers"],
        "table_alternating_rows": payload["table_alternating_rows"],
        "splitter_orientation": payload["splitter_orientation"],
        "splitter_panes": payload["splitter_panes"],
        "outer_margins_px": payload["outer_margins_px"],
        "outer_spacing_px": payload["outer_spacing_px"],
        "left_margins_px": payload["left_margins_px"],
        "left_spacing_px": payload["left_spacing_px"],
        "top_row_spacing_px": payload["top_row_spacing_px"],
        "top_row_items": TOP_ROW_ITEM_COUNT,
        "left_items": LEFT_ITEM_COUNT,
        "active_symbols": payload["active_symbols"],
        "last_meta": payload["last_meta"],
        "pending_refresh": payload["pending_refresh"],
        "exchange_source_wired": payload["exchange_source_wired"],
    }


class FetchAnswer:
    """What the fetcher hands back, as this file invents it."""

    def __init__(self, meta):
        self.candles_by_symbol_by_tf = {"BTC": {"1d": []}}
        self.closes_by_symbol = {"BTC": [1.0, 2.0]}
        self.meta = dict(meta)


def blocked_right_pane():
    """Stop the topology pane from being imported, for one build only.

    The shipped screen falls back to plain space when that import
    refuses. Both sides are built through that fallback so the picture
    comparison measures this screen and not the pane's own screen.
    """
    import importlib.abc

    class Refuse(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.endswith("market_inspector_topologies"):
                raise ImportError("right pane blocked")
            return None

    return Refuse()


RIGHT_PANE_MODULE = "src.gui.market_inspector_topologies"


def old_screen(right_pane=True):
    """One real Market Inspector screen.

    A module already loaded is never asked for again, so the pane is
    taken out of the loaded set as well as refused on the way in.
    """
    app()
    if right_pane:
        return hold(shipped.MarketInspectorTab())
    refuse = blocked_right_pane()
    sys.meta_path.insert(0, refuse)
    was = sys.modules.pop(RIGHT_PANE_MODULE, None)
    try:
        return hold(shipped.MarketInspectorTab())
    finally:
        sys.meta_path.remove(refuse)
        if was is not None:
            sys.modules[RIGHT_PANE_MODULE] = was


def new_screen(**wiring):
    """One surface Market Inspector screen."""
    return surface.MarketInspectorScreenModel(**wiring)


def press_old_switch(tab, checked):
    """Click the shipped "Include active markets" switch.

    The two things a click does are done here as two steps: the
    switch takes the new state, then the slot runs. Qt swallows an
    exception raised inside a slot it delivers itself, so a click
    made through the signal would read as an answer on the shipped
    side and as a refusal on the surface. Both halves are proved by
    a control below.
    """
    switch = tab._show_active_chk
    if bool(checked) == switch.isChecked():
        return
    was = switch.blockSignals(True)
    switch.setChecked(checked)
    switch.blockSignals(was)
    tab._on_toggle_show_active(checked)


def old_steps(tab, steps, state):
    """Every step one shipped screen takes, each one on its own."""
    found = []
    for step in steps:
        name = step[0]
        if name == "render":
            found.append(tab._render_signals)
        elif name == "toggle":
            found.append(lambda checked=step[1]: press_old_switch(tab, checked))
        elif name == "fleet":
            found.append(lambda roster=step[1]: tab.update_active_symbols(roster))
        elif name == "progress":
            found.append(lambda message=step[1]: tab._on_progress(message))
        elif name == "start":
            found.append(lambda force=step[1]: tab._start_fetch(force=force))
        elif name == "fetch":
            found.append(
                lambda force=step[1]: asyncio.run(
                    tab._fetch_and_analyze({"venue": object()}, force=force)
                )
            )
        else:
            raise AssertionError("no such step: %r" % (name,))
    return found


def new_steps(model, steps, state):
    """Every step one surface screen takes, each one on its own."""
    found = []
    for step in steps:
        name = step[0]
        if name == "render":
            found.append(model.render_signals)
        elif name == "toggle":
            found.append(lambda checked=step[1]: model.press_show_active(checked))
        elif name == "fleet":
            found.append(lambda roster=step[1]: model.update_active_symbols(roster))
        elif name == "progress":
            found.append(lambda message=step[1]: model.on_progress(message))
        elif name == "start":
            found.append(lambda force=step[1]: model.start_fetch(force=force))
        elif name == "fetch":
            found.append(
                lambda force=step[1]: asyncio.run(
                    model.fetch_and_analyze({"venue": object()}, force=force)
                )
            )
        else:
            raise AssertionError("no such step: %r" % (name,))
    return found


def invented_fetcher(monkeypatch, meta, raises=None):
    """Point both sides at one invented fetch that reaches no network."""
    from src.exchange import market_inspector_fetcher

    async def answer(_connectors, active_symbols=None, progress_cb=None, **rest):
        FETCHES_SEEN.append([sorted(active_symbols or []), rest.get("force_network")])
        if raises is not None:
            raise raises
        return FetchAnswer(meta)

    monkeypatch.setattr(market_inspector_fetcher, "fetch_htf_universe", answer)


FETCHES_SEEN: list = []


def drive(names, steps=(("render",),), wiring=None):
    """Both sides through the same steps, read into one shape.

    One starting state is built and handed to BOTH sides, so a
    difference can only come from the screens. Each side is given its
    own analyzer in the process-wide seat. Every step is guarded on its
    own, so a step that refuses does not swallow the steps after it.
    """
    states = [CASES[name]() for name in names]
    state = states[-1]
    all_steps = []
    for index, name in enumerate(names):
        all_steps.append(("seat", index))
        all_steps.extend(steps)
    del all_steps

    old_state = None
    new_state = None
    old_outcome = []
    new_outcome = []

    def run_side(build, step_maker, seat):
        outcome = []
        screen = build()
        for index, one in enumerate(states):
            seat(one["signals"], one["pairs"])
            outcome.append(guarded(lambda one=one: set_meta(screen, one["meta"])))
            for step in step_maker(screen, steps, one):
                outcome.append(guarded(step))
        return screen, outcome

    old_screen_built, old_outcome = run_side(old_screen, old_steps, seat_inspector)
    old_state = read_old(old_screen_built)

    model = new_screen(**(wiring or {}))
    new_outcome = []
    for one in states:
        seat_inspector(one["signals"], one["pairs"])
        new_outcome.append(guarded(lambda one=one: set_meta(model, one["meta"])))
        for step in new_steps(model, steps, one):
            new_outcome.append(guarded(step))
    new_state = read_new(surface.build_view_model(model))
    return {
        "old": old_state,
        "new": new_state,
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
        "state": state,
    }


def set_meta(screen, meta):
    """Give one screen the fetch report the case carries."""
    if isinstance(screen, surface.MarketInspectorScreenModel):
        screen.last_meta = dict(meta)
    else:
        screen._last_meta = dict(meta)


def both_sides_agree(run, note):
    """Fail unless the two sides did the same thing and hold the same state."""
    assert (
        run["old_outcome"] == run["new_outcome"]
    ), "%s: the shipped screen and the surface refused differently: %r against %r" % (
        note,
        run["old_outcome"],
        run["new_outcome"],
    )
    assert readable(run["old"]) == readable(run["new"]), "%s: %r against %r" % (
        note,
        readable(run["old"]),
        readable(run["new"]),
    )
    assert digest(run["old"]) == digest(run["new"]), "%s: %s against %s" % (
        note,
        digest(run["old"]),
        digest(run["new"]),
    )


# The two sides, case by case


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_screen_is_the_shipped_screens(name):
    """The surface describes a screen the shipped screen does not build."""
    both_sides_agree(drive([name]), name)


def test_every_case_in_the_table_is_driven():
    """A case sits in the table that nothing ever drives."""
    driven = set()
    for name in CASES:
        both_sides_agree(drive([name]), name)
        driven.add(name)
    for name, steps in SEQUENCES.items():
        both_sides_agree(drive(steps), name)
        driven.update(steps)
    assert driven == set(CASES), sorted(driven ^ set(CASES))
    assert len(CASES) == len(driven)
    assert set(PICTURE_CASES) <= set(CASES), sorted(set(PICTURE_CASES) - set(CASES))
    assert set(PER_BOT_CASES) <= set(CASES), sorted(set(PER_BOT_CASES) - set(CASES))
    assert set(REFUSING) <= set(CASES), sorted(set(REFUSING) - set(CASES))


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_screen_showing_active_markets_is_the_shipped_screen(name):
    """The switch that lists traded markets shows a different set."""
    both_sides_agree(drive([name], steps=(("toggle", True),)), name)


@pytest.mark.parametrize("name", sorted(FLEET_LISTS))
def test_the_fleet_roster_reaches_both_sides_alike(name):
    """A fleet roster produced a different active-market set on one side."""
    both_sides_agree(drive(["happy"], steps=(("fleet", FLEET_LISTS[name]),)), name)


def test_every_fleet_roster_in_the_table_is_driven():
    """A roster sits in the table that nothing ever drives."""
    driven = set()
    for name in FLEET_LISTS:
        both_sides_agree(drive(["happy"], steps=(("fleet", FLEET_LISTS[name]),)), name)
        driven.add(name)
    assert driven == set(FLEET_LISTS)
    assert set(FLEET_REFUSING) <= set(FLEET_LISTS)


@pytest.mark.parametrize("name", sorted(FLEET_REFUSING))
def test_a_refused_fleet_roster_refuses_the_same_way_on_both_sides(name):
    """A roster one side refuses is accepted by the other."""
    run = drive(["happy"], steps=(("fleet", FLEET_LISTS[name]),))
    assert refusals(run["old_outcome"]), name
    both_sides_agree(run, name)


def test_the_sample_hashes_are_reported():
    """The comparison reports no hash, so nothing can be checked by hand."""
    happy = drive(["happy"])
    empty = drive(["empty"])
    assert len(digest(happy["old"])) == 64
    assert digest(happy["old"]) == digest(happy["new"])
    assert digest(empty["old"]) == digest(empty["new"])
    assert digest(happy["old"]) != digest(empty["old"])


def test_two_genuinely_different_real_inputs_hash_apart():
    """The hash gives one value for every screen, so it tells nothing apart."""
    happy = drive(["happy"])
    rows = drive(["three_rows"])
    assert digest(happy["old"]) != digest(rows["new"]), "old happy against new rows"
    assert digest(rows["old"]) != digest(happy["new"]), "old rows against new happy"
    assert digest(happy["old"]) == digest(happy["new"])
    assert digest(rows["old"]) == digest(rows["new"])


def test_the_same_input_hashes_the_same_twice():
    """The hash moves between two runs of one input, so it reads the clock."""
    assert digest(drive(["happy"])["old"]) == digest(drive(["happy"])["old"])
    assert digest(drive(["happy"])["new"]) == digest(drive(["happy"])["new"])


def test_a_whole_number_and_a_decimal_are_told_apart():
    """The reader treats 12 and 12.0 as one value, so a change reads as none."""
    assert readable(12) != readable(12.0)
    assert digest({"a": 12}) != digest({"a": 12.0})
    assert readable(True) != readable(1)


def test_two_not_a_numbers_built_apart_compare_equal():
    """The reader calls two not-a-numbers different, reporting a false change."""
    first = float("nan")
    second = float("inf") - float("inf")
    assert first != second
    assert readable(first) == readable(second)
    assert digest({"a": first}) == digest({"a": second})
    assert readable(float("inf")) != readable(float("-inf"))


def test_the_machine_rule_keeps_a_seeded_value_and_hides_a_chosen_one():
    """The rule hiding the machine's answers hides a value this test seeded."""
    asked = list(surface.SPLITTER_SIZES_PX)
    kept = readable({"signals_max_height_px": 360, "pane_sizes_px": asked})
    assert kept["signals_max_height_px"] == ["int", "360"]
    assert kept["pane_sizes_px"] == [["int", "800"], ["int", "800"]]
    hidden = platform_chosen({"pane_sizes_px": [636, 0]})
    assert hidden["pane_sizes_px"] == SETTLED_MARK
    assert platform_chosen({"pane_sizes_px": asked})["pane_sizes_px"] == asked


# What each side DID: answered, or refused with which type


def refusals(outcome):
    """The refusal type of every step that refused, in order."""
    return [step["error"] for step in outcome if step["error"]]


def outcomes(names):
    """How the shipped screen refused each named case, if it did."""
    return {name: refusals(drive([name])["old_outcome"]) for name in names}


def test_the_outcomes_hold_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the set proves nothing."""
    found = outcomes(sorted(CASES))
    answered = [name for name, done in found.items() if not done]
    refused = [name for name, done in found.items() if done]
    assert answered, found
    assert refused, found
    assert sorted(refused) == sorted(REFUSING), sorted(set(refused) ^ set(REFUSING))
    assert len(answered) + len(refused) == len(CASES)


@pytest.mark.parametrize("name", sorted(REFUSING))
def test_a_refused_input_refuses_the_same_way_on_both_sides(name):
    """One side answered an input the other refused, or refused differently."""
    run = drive([name])
    assert refusals(run["old_outcome"]), name
    assert run["old_outcome"] == run["new_outcome"], "%s: %r against %r" % (
        name,
        run["old_outcome"],
        run["new_outcome"],
    )
    both_sides_agree(run, name)


def test_the_refusal_comparison_holds_more_than_one_type():
    """Every refusal shares one type, so a swapped refusal reads as unchanged."""
    found = outcomes(sorted(REFUSING))
    kinds = {kind for done in found.values() for kind in done}
    assert len(kinds) > 1, found
    assert kinds == {"AttributeError", "OverflowError", "ValueError"}, kinds
    assert guarded(lambda: 1) != guarded(lambda: 1 / 0)
    assert guarded(lambda: int("x"))["error"] == "ValueError"


def test_the_refusal_reader_reports_two_different_wordings():
    """Two refusals worded apart read the same, so a wording change is unseen.

    Both wordings are read off the shipped side. Neither is written down:
    Python words one failure differently between its own versions.
    """
    first = headline_of(lambda: shipped._fmt_age(float("inf")))
    second = headline_of(lambda: shipped._signal_color(5))
    assert first, "the shipped screen answered an input it should refuse"
    assert second, "the shipped screen answered an input it should refuse"
    assert first != second, (first, second)
    assert headline_of(lambda: None) == ""


# Step sequences, including one that refuses part way


@pytest.mark.parametrize("name", sorted(SEQUENCES))
def test_a_step_sequence_is_the_shipped_screens(name):
    """A rewrite left the surface holding rows the shipped screen does not."""
    both_sides_agree(drive(SEQUENCES[name]), name)


def test_a_sequence_that_refuses_part_way_leaves_the_same_rows_on_both_sides():
    """A rewrite that refuses part way left different rows on the two sides."""
    run = drive(SEQUENCES["three_steps"])
    both_sides_agree(run, "three_steps")
    assert refusals(run["old_outcome"]) == ["AttributeError"]
    assert len(run["old"]["signal_rows"]) == 1
    assert run["old"]["signal_rows"][0][0][0] == "ALPHA"


def test_the_sequence_check_reports_a_row_left_behind():
    """The sequence check passes whatever a rewrite leaves on screen."""
    kept = drive(SEQUENCES["answer_then_refuse"])
    fresh = drive(["infinite_age"])
    assert digest(kept["old"]) != digest(fresh["old"]), "the left-behind row is unseen"
    assert len(kept["old"]["signal_rows"]) == 2
    assert fresh["old"]["signal_rows"] == []


def test_a_toggle_after_a_refused_step_shows_the_same_rows():
    """A refused step left the two sides listing different markets."""
    run = drive(
        ["band_is_text", "mixed_scores"],
        steps=(("render",), ("toggle", True)),
    )
    both_sides_agree(run, "toggle after a refused render")
    assert refusals(run["old_outcome"]) == ["AttributeError", "AttributeError"]
    assert [row[0][0] for row in run["old"]["signal_rows"]] == ["ALPHA", "GAMMA"]


def test_the_switch_really_reaches_the_slot_on_the_shipped_screen():
    """The switch is wired to nothing, so pressing it in code proves nothing."""
    app()
    seat_inspector([signal(is_active=True)], [])
    tab = old_screen()
    assert tab._show_active is False
    tab._show_active_chk.setChecked(True)
    assert tab._show_active is True, "the switch reaches no slot"
    assert len(table_rows(tab._signals_tbl)) == 1
    tab._show_active_chk.setChecked(True)
    assert tab._show_active is True
    tab._show_active_chk.setChecked(False)
    assert tab._show_active is False
    assert table_rows(tab._signals_tbl) == []


def test_pressing_the_switch_refuses_the_same_way_on_both_sides():
    """One side refused a switch press the other side answered."""
    app()
    seat_inspector([], [])
    tab = old_screen()
    tab._last_meta = {"source": "cache", "age_seconds": float("inf")}
    model = new_screen()
    model.last_meta = {"source": "cache", "age_seconds": float("inf")}
    assert guarded(lambda: tab._on_toggle_show_active(True)) == {
        "error": "OverflowError"
    }
    assert guarded(lambda: model.press_show_active(True)) == {"error": "OverflowError"}
    assert tab._show_active is model.show_active is True
    assert model.show_active_checked is True


# The fetch cycle


def test_pressing_refresh_with_nothing_wired_writes_the_same_line():
    """The screen started a fetch with no exchange wired, or said nothing."""
    run = drive(["happy"], steps=(("start", True),))
    both_sides_agree(run, "no exchange wired")
    assert run["old"]["status_text"] == surface.NOT_WIRED_TEXT
    assert run["old"]["pending_refresh"] is False


def test_pressing_refresh_with_no_connectors_writes_the_same_line():
    """The screen started a fetch with no venue connected, or said nothing."""
    app()
    tab = old_screen()
    tab.set_exchange_source(lambda: {}, lambda call: None)
    tab._start_fetch(force=True)
    model = new_screen()
    model.set_exchange_source(lambda: {}, lambda call: None)
    model.start_fetch(force=True)
    assert tab._status_lbl.text() == surface.NO_CONNECTORS_TEXT
    assert model.status_label_text == surface.NO_CONNECTORS_TEXT
    assert tab._pending_refresh is model.pending_refresh is False


def test_pressing_refresh_hands_the_fetch_to_the_loop_on_both_sides():
    """Refresh scheduled nothing, or left the button pressable while it runs."""
    app()
    old_sent: list = []
    tab = old_screen()
    tab.set_exchange_source(
        lambda: {"venue": object()},
        lambda call: (old_sent.append(call), call.close())[0],
    )
    tab._start_fetch(force=True)
    new_sent: list = []
    model = new_screen()
    model.set_exchange_source(lambda: {"venue": object()}, new_sent.append)
    model.start_fetch(force=True)
    assert len(old_sent) == len(new_sent) == 1
    assert tab._status_lbl.text() == model.status_label_text == surface.FETCHING_TEXT
    assert tab._refresh_btn.isEnabled() is model.refresh_enabled is False
    assert tab._pending_refresh is model.pending_refresh is True
    tab._start_fetch(force=True)
    model.start_fetch(force=True)
    assert len(old_sent) == len(new_sent) == 1, "a second press started a second fetch"
    assert surface.FETCH_BLOCKED in [call[0] for call in model.calls]


def test_a_scheduler_that_refuses_writes_the_same_line_on_both_sides():
    """A loop that will not take the fetch left the screen stuck on Fetching."""
    app()

    def refuse(call):
        if hasattr(call, "close"):
            call.close()
        raise RuntimeError("no loop")

    tab = old_screen()
    tab.set_exchange_source(lambda: {"venue": object()}, refuse)
    tab._start_fetch(force=True)
    model = new_screen()
    model.set_exchange_source(lambda: {"venue": object()}, refuse)
    model.start_fetch(force=True)
    assert tab._status_lbl.text() == model.status_label_text
    assert tab._status_lbl.text() == surface.SCHEDULER_ERROR_FORMAT.format(
        error="no loop"
    )
    assert tab._refresh_btn.isEnabled() is model.refresh_enabled is True
    assert tab._pending_refresh is model.pending_refresh is False


def test_a_finished_fetch_writes_the_same_screen_on_both_sides(monkeypatch):
    """A finished fetch left the two sides holding different rows."""
    meta = {"source": "coingecko", "symbol_count": 3, "age_seconds": 0.0}
    invented_fetcher(monkeypatch, meta)
    FETCHES_SEEN.clear()
    app()
    signals = [signal(symbol="ALPHA")]
    tab = old_screen()
    seat_inspector(signals, [])
    tab._active_symbols = {"BTC"}
    asyncio.run(tab._fetch_and_analyze({"venue": object()}, force=True))
    old_read = read_old(tab)
    old_seen = list(FETCHES_SEEN)
    FETCHES_SEEN.clear()
    model = new_screen()
    seat_inspector(signals, [])
    model.active_symbols = {"BTC"}
    asyncio.run(model.fetch_and_analyze({"venue": object()}, force=True))
    new_read = read_new(surface.build_view_model(model))
    assert readable(old_read) == readable(new_read)
    assert old_seen == FETCHES_SEEN == [[["BTC"], True]]
    assert old_read["status_text"] == surface.STATUS_LIVE_FORMAT.format(count=3)


def test_a_fetch_that_refuses_writes_the_same_report_on_both_sides(monkeypatch):
    """A failed fetch left the two sides reporting it differently."""
    invented_fetcher(monkeypatch, {}, raises=RuntimeError("venue down"))
    app()
    tab = old_screen()
    seat_inspector([], [])
    asyncio.run(tab._fetch_and_analyze({"venue": object()}, force=False))
    old_read = read_old(tab)
    model = new_screen()
    seat_inspector([], [])
    asyncio.run(model.fetch_and_analyze({"venue": object()}, force=False))
    new_read = read_new(surface.build_view_model(model))
    assert readable(old_read) == readable(new_read)
    assert old_read["last_meta"]["source"] == surface.SOURCE_ERROR
    assert old_read["last_meta"]["error"] == "venue down"
    assert old_read["status_text"] == surface.STATUS_ERROR_FORMAT.format(
        error="venue down"
    )
    assert old_read["refresh_enabled"] is True
    assert old_read["pending_refresh"] is False


def test_a_progress_line_reaches_the_status_label_on_both_sides(monkeypatch):
    """The progress the fetch reports never reached the screen."""
    meta = {"source": "coingecko", "symbol_count": 1}
    from src.exchange import market_inspector_fetcher

    async def talkative(_connectors, active_symbols=None, progress_cb=None, **rest):
        if progress_cb is not None:
            progress_cb("two of nine markets")
        raise RuntimeError("stopped after the progress line")

    monkeypatch.setattr(market_inspector_fetcher, "fetch_htf_universe", talkative)
    app()
    tab = old_screen()
    seat_inspector([], [])
    tab._on_progress("two of nine markets")
    assert tab._status_lbl.text() == "two of nine markets"
    model = new_screen()
    model.on_progress("two of nine markets")
    assert model.status_label_text == "two of nine markets"
    assert surface.PROGRESS_WRITTEN in [call[0] for call in model.calls]
    assert meta


def test_an_analyzer_that_refuses_a_scan_hides_its_own_words_on_both_sides(
    monkeypatch,
):
    """The analyzer error the screen writes survives the redraw after it.

    The shipped screen writes "Analyzer error: ..." into the status
    label and then calls the redraw, which rewrites that label from the
    fetch report. The words never reach the operator. The surface keeps
    the same order, so both sides show the fetch line. A failure here
    means the two sides no longer agree about it.
    """
    meta = {"source": "coingecko", "symbol_count": 3}
    invented_fetcher(monkeypatch, meta)
    app()
    tab = old_screen()
    setattr(
        analyzer,
        SHARED_INSPECTOR_NAME,
        surface.InspectorSource(raises=ValueError("bad candles")),
    )
    asyncio.run(tab._fetch_and_analyze({"venue": object()}, force=False))
    old_text = tab._status_lbl.text()
    model = new_screen()
    setattr(
        analyzer,
        SHARED_INSPECTOR_NAME,
        surface.InspectorSource(raises=ValueError("bad candles")),
    )
    asyncio.run(model.fetch_and_analyze({"venue": object()}, force=False))
    assert old_text == model.status_label_text
    assert old_text == surface.STATUS_LIVE_FORMAT.format(count=3)
    written = surface.ANALYZER_ERROR_FORMAT.format(error="bad candles")
    assert old_text != written, "the analyzer error now survives the redraw"
    assert surface.SCAN_FAILED in [call[0] for call in model.calls]


def test_an_unreachable_analyzer_writes_the_same_line_on_both_sides():
    """A screen whose analyzer cannot be reached says nothing about it."""
    app()
    tab = old_screen()
    model = new_screen()
    refuse = analyzer_blocked()
    sys.meta_path.insert(0, refuse)
    was = sys.modules.pop("src.trading.market_inspector", None)
    try:
        tab._render_signals()
        model.render_signals()
    finally:
        sys.meta_path.remove(refuse)
        if was is not None:
            sys.modules["src.trading.market_inspector"] = was
    assert tab._status_lbl.text() == model.status_label_text
    assert tab._status_lbl.text() == surface.ANALYZER_UNAVAILABLE_TEXT
    assert surface.ANALYZER_UNREACHABLE in [call[0] for call in model.calls]


def analyzer_blocked():
    """Stop the analyzer module from being imported, for one call only."""
    import importlib.abc

    class Refuse(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.endswith("trading.market_inspector"):
                raise ImportError("analyzer blocked")
            return None

    return Refuse()


# The right pane and its three wiring points


class RecordingPane:
    """A right pane that records everything the screen hands it."""

    def __init__(self, proposals=None, raises=None):
        self.proposals = [] if proposals is None else list(proposals)
        self.raises = raises
        self.stores: list = []
        self.sources: list = []
        self.handlers: list = []

    def set_dismiss_store(self, store):
        self.stores.append(store)

    def set_proposal_source(self, getter):
        self.sources.append(getter)

    def current_proposals(self):
        if self.raises is not None:
            raise self.raises
        return list(self.proposals)

    @property
    def adoptRequested(self):
        return self

    def connect(self, handler):
        self.handlers.append(handler)


def test_the_three_wiring_points_reach_the_pane_on_both_sides():
    """A wiring the window sends never reaches the right pane."""
    app()
    tab = old_screen()
    old_pane = RecordingPane([{"id": "proposal-1"}])
    tab._topologies_pane = old_pane
    tab.set_dismiss_store("a store")
    tab.set_proposal_source("a getter")
    tab.set_adopt_handler("a handler")
    new_pane = RecordingPane([{"id": "proposal-1"}])
    model = new_screen(topologies_pane=new_pane)
    model.set_dismiss_store("a store")
    model.set_proposal_source("a getter")
    model.set_adopt_handler("a handler")
    assert old_pane.stores == new_pane.stores == ["a store"]
    assert old_pane.sources == new_pane.sources == ["a getter"]
    assert old_pane.handlers == new_pane.handlers == ["a handler"]
    assert tab.current_topology_proposals() == model.current_topology_proposals()
    assert model.current_topology_proposals() == [{"id": "proposal-1"}]


def test_a_pane_with_no_wiring_points_takes_nothing_on_both_sides():
    """A plain right pane took a wiring it cannot hold, or raised."""
    from PySide6.QtWidgets import QWidget

    app()
    tab = old_screen()
    tab._topologies_pane = QWidget()
    model = new_screen(topologies_pane=object())
    assert tab.set_dismiss_store("a store") is None
    assert model.set_dismiss_store("a store") is None
    assert tab.set_proposal_source("a getter") is None
    assert model.set_proposal_source("a getter") is None
    assert tab.set_adopt_handler("a handler") is None
    assert model.set_adopt_handler("a handler") is None
    assert tab.current_topology_proposals() == model.current_topology_proposals() == []
    assert surface.STORE_UNREACHABLE in [call[0] for call in model.calls]
    assert surface.ADOPT_UNREACHABLE in [call[0] for call in model.calls]


def test_no_pane_at_all_takes_nothing_on_both_sides():
    """A screen with no right pane raised instead of doing nothing."""
    app()
    tab = old_screen()
    tab._topologies_pane = None
    model = new_screen(topologies_pane=None)
    assert tab.set_dismiss_store("a store") is None
    assert model.set_dismiss_store("a store") is None
    assert tab.set_proposal_source("a getter") is None
    assert model.set_proposal_source("a getter") is None
    assert tab.set_adopt_handler("a handler") is None
    assert model.set_adopt_handler("a handler") is None
    assert tab.current_topology_proposals() == model.current_topology_proposals() == []
    assert surface.SOURCE_UNREACHABLE in [call[0] for call in model.calls]


def test_a_pane_that_refuses_to_list_its_proposals_answers_nothing():
    """A refusing pane took the whole screen down with it."""
    app()
    tab = old_screen()
    tab._topologies_pane = RecordingPane(raises=RuntimeError("detector gone"))
    model = new_screen(
        topologies_pane=RecordingPane(raises=RuntimeError("detector gone"))
    )
    assert tab.current_topology_proposals() == model.current_topology_proposals() == []
    assert surface.PROPOSALS_UNREADABLE in [call[0] for call in model.calls]


def test_a_pane_answering_nothing_reads_as_an_empty_list_on_both_sides():
    """A pane that answers nothing produced a different value on one side."""
    app()

    class Quiet:
        def current_proposals(self):
            return None

    tab = old_screen()
    tab._topologies_pane = Quiet()
    model = new_screen(topologies_pane=Quiet())
    assert tab.current_topology_proposals() == model.current_topology_proposals() == []


def test_the_shipped_screen_builds_the_real_right_pane():
    """The screen the operator opens carries no proposals pane."""
    app()
    from src.gui.market_inspector_topologies import MarketInspectorTopologies

    tab = old_screen()
    assert isinstance(tab._topologies_pane, MarketInspectorTopologies)
    plain = old_screen(right_pane=False)
    assert not isinstance(plain._topologies_pane, MarketInspectorTopologies)
    assert plain._topologies_pane is not None


# The per-bot screen


class Config:
    """One bot configuration, carrying only the symbol both sides read."""

    def __init__(self, symbol):
        self.symbol = symbol


class Bot:
    """One bot, as far as the per-bot screen reads it."""

    def __init__(self, symbol):
        self.config = Config(symbol)


def read_old_per_bot(widget):
    """One shipped per-bot screen read into the one shape both sides use."""
    from PySide6.QtWidgets import QGroupBox, QLabel

    def walk(owner):
        layout = owner.layout()
        found = []
        for index in range(layout.count()):
            item = layout.itemAt(index)
            child = item.widget()
            if child is None:
                found.append([surface.STRETCH_ELEMENT])
            elif isinstance(child, QGroupBox):
                found.append([surface.GROUP_ELEMENT, child.title(), walk(child)])
            elif isinstance(child, QLabel):
                found.append(
                    [
                        surface.LABEL_ELEMENT,
                        child.text(),
                        child.styleSheet(),
                        child.wordWrap(),
                    ]
                )
            else:
                found.append([type(child).__name__])
        return found

    return {
        "spacing_px": widget.layout().spacing(),
        "order": walk(widget),
    }


def drive_per_bot(case_name, symbol):
    """Both per-bot screens from one starting state and one symbol."""
    state = CASES[case_name]()
    app()
    seat_inspector(state["signals"], state["pairs"])
    old_widget = hold(shipped.build_per_bot_view(Bot(symbol)))
    old_read = read_old_per_bot(old_widget)
    seat_inspector(state["signals"], state["pairs"])
    model = surface.build_per_bot_model(Bot(symbol))
    new_read = surface.per_bot_view(model)
    return {
        "old": old_read,
        "new": {"spacing_px": new_read["spacing_px"], "order": new_read["order"]},
        "asset": new_read["asset"],
    }


@pytest.mark.parametrize("name", sorted(PER_BOT_CASES))
@pytest.mark.parametrize("symbol", PER_BOT_SYMBOLS)
def test_the_per_bot_screen_is_the_shipped_screen(name, symbol):
    """The per-bot view model carries a card the shipped view does not."""
    run = drive_per_bot(name, symbol)
    note = "%s / %r" % (name, symbol)
    assert readable(run["old"]) == readable(run["new"]), "%s: %r against %r" % (
        note,
        run["old"],
        run["new"],
    )
    assert digest(run["old"]) == digest(run["new"]), note


def test_the_per_bot_hash_tells_two_real_screens_apart():
    """The per-bot hash gives one value for every screen."""
    own = drive_per_bot("happy", "BTC/USD")
    other = drive_per_bot("happy", "DOGE/USD")
    assert digest(own["old"]) != digest(other["new"]), "old own against new other"
    assert digest(other["old"]) != digest(own["new"]), "old other against new own"
    assert digest(own["old"]) == digest(own["new"])
    assert digest(other["old"]) == digest(other["new"])


def test_a_per_bot_screen_with_no_scan_says_so_on_both_sides():
    """A per-bot screen with no scan behind it showed an empty card."""
    run = drive_per_bot("empty", "BTC/USD")
    assert run["old"]["order"] == run["new"]["order"]
    assert run["old"]["order"][0][1] == surface.NO_SCAN_TEXT
    assert run["old"]["order"][0][2] == surface.NO_SCAN_STYLE
    assert run["old"]["order"][0][3] is True
    assert run["old"]["order"][-1] == [surface.STRETCH_ELEMENT]


def test_a_per_bot_screen_with_no_analyzer_says_so_on_both_sides():
    """A per-bot screen whose analyzer is gone raised instead of saying so."""
    app()
    refuse = analyzer_blocked()
    sys.meta_path.insert(0, refuse)
    was = sys.modules.pop("src.trading.market_inspector", None)
    try:
        old_widget = hold(shipped.build_per_bot_view(Bot("BTC/USD")))
        model = surface.build_per_bot_model(Bot("BTC/USD"))
    finally:
        sys.meta_path.remove(refuse)
        if was is not None:
            sys.modules["src.trading.market_inspector"] = was
    old_read = read_old_per_bot(old_widget)
    assert old_read["order"] == model.order
    assert old_read["order"][0][1] == surface.PER_BOT_UNAVAILABLE_TEXT


def test_a_bot_with_no_symbol_to_read_shows_the_same_card():
    """A bot whose symbol cannot be read raised on one side."""
    state = CASES["happy"]()
    app()
    seat_inspector(state["signals"], state["pairs"])
    old_widget = hold(shipped.build_per_bot_view(object()))
    seat_inspector(state["signals"], state["pairs"])
    model = surface.build_per_bot_model(object())
    assert read_old_per_bot(old_widget)["order"] == model.order
    assert model.asset == surface.NO_ASSET
    assert surface.UNKNOWN_ASSET_MARK in model.order[0][1]


def test_the_higher_scoring_card_holds_at_most_five_rows_on_both_sides():
    """The top-five card listed a different number of markets on one side."""
    signals = [signal(symbol="M%02d" % index, score=index) for index in range(1, 9)]
    app()
    seat_inspector(signals, [])
    old_widget = hold(shipped.build_per_bot_view(Bot("M01/USD")))
    seat_inspector(signals, [])
    model = surface.build_per_bot_model(Bot("M01/USD"))
    old_read = read_old_per_bot(old_widget)
    assert old_read["order"] == model.order
    higher = [row for row in model.order if row[0] == surface.GROUP_ELEMENT]
    assert higher[1][1] == surface.HIGHER_GROUP_TITLE
    assert len(higher[1][2]) == surface.HIGHER_LIMIT == 5


# The surface holds its own values


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file():
    """The surface reads the shipped file, so the comparison reads one side."""
    app()
    state = CASES["happy"]()
    before = shipped._signal_color
    moved_title = "Renamed group"

    def moved_colour(name):
        return "#123456"

    shipped._signal_color = moved_colour
    try:
        seat_inspector(state["signals"], state["pairs"])
        tab = old_screen()
        tab._render_signals()
        moved = read_old(tab)
        moved["signals_group_title"] = moved_title
        seat_inspector(state["signals"], state["pairs"])
        model = new_screen()
        model.render_signals()
        kept = read_new(surface.build_view_model(model))
        assert moved["signal_rows"][0][1][1] == "#123456"
        assert kept["signal_rows"][0][1][1] == painted(surface.COLOR_ENTRY_LONG_HIGH)
        assert kept["signal_rows"][0][1][1] != "#123456"
        differences = [
            key
            for key in sorted(set(moved) & set(kept))
            if readable(moved[key]) != readable(kept[key])
        ]
        assert differences == ["signal_rows", "signals_group_title"], differences
    finally:
        shipped._signal_color = before
    both_sides_agree(drive(["happy"]), "after the value was put back")


def test_the_shipped_file_is_not_named_by_the_surface():
    """The surface reaches into the screen it replaces."""
    text = SURFACE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    assert not any("gui.market_inspector" in name for name in imported), imported
    assert "market_inspector_topologies" not in imported, imported


# Counting what the shipped file wires, waits on, and builds

WIDGET_NAMES_BUILT = (
    "QWidget",
    "QLabel",
    "QPushButton",
    "QTableWidget",
    "QTableWidgetItem",
    "QGroupBox",
    "QFrame",
    "QScrollArea",
    "QLineEdit",
    "QComboBox",
    "QCheckBox",
    "QSpinBox",
    "QTextEdit",
    "QProgressBar",
    "QSplitter",
    "QDialog",
)


def count_text(path, needle):
    """How many times one wiring call appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def count_built(path, names):
    """How many times one file constructs any of `names`."""
    text = path.read_text(encoding="utf-8")
    return sum(len(re.findall(r"\b%s\s*\(" % name, text)) for name in names)


def declared_classes(path):
    """Every class one file declares, wherever it is declared.

    A class inside an ``if``, inside a method or inside another class is
    still a class, so the whole tree is walked rather than its top level.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}


def declared_widget_classes(path):
    """Every class one file declares that ends up being a screen element."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    found: set = set()
    growing = True
    while growing:
        growing = False
        for node in classes:
            if node.name in found:
                continue
            for base in node.bases:
                name = (
                    base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
                )
                if name.startswith("Q") or name in found:
                    found.add(node.name)
                    growing = True
                    break
    return found


def count_elements(path):
    """How many screen elements one file builds, its own classes included."""
    return count_built(path, WIDGET_NAMES_BUILT) + len(declared_widget_classes(path))


SURFACE_CONNECT_SITES = 1


def test_the_screen_wires_three_signals_and_the_surface_names_three_actions():
    """A wiring appeared on one side and not the other.

    The surface holds one ``.connect(`` of its own. It is the hand-off
    the shipped screen makes to whatever right pane it was given, and
    the surface makes the same hand-off to whatever it is given. The
    surface declares no signal and builds no Qt object.
    """
    assert count_text(SCREEN_PATH, ".connect(") == SCREEN_CONNECT_SITES == 3
    assert count_text(SURFACE_PATH, ".connect(") == SURFACE_CONNECT_SITES == 1
    assert count_text(WIRING_CONTROL_PATH, ".connect(") == CONTROL_CONNECT_SITES == 1
    assert len(surface.ACTIONS) == count_text(SCREEN_PATH, ".connect(")
    for name in surface.ACTIONS.values():
        assert callable(getattr(surface.MarketInspectorScreenModel, name)), name


def test_the_screen_starts_no_timer_of_its_own_and_the_pane_starts_one():
    """A wait appeared on one side and not the other.

    The file builds no timer. The screen it puts on the operator's
    display starts one, and that timer belongs to the right pane at
    ``src/gui/market_inspector_topologies.py``, not to this file.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
    timer_names = ("QTimer",)
    assert count_built(SCREEN_PATH, timer_names) == SCREEN_TIMER_BUILDS == 0
    assert count_built(SURFACE_PATH, timer_names) == 0
    assert count_built(TIMER_CONTROL_PATH, timer_names) == CONTROL_TIMER_BUILDS == 1
    assert count_built(TIMER_NEIGHBOUR_PATH, timer_names) == 0
    assert count_built(RIGHT_PANE_PATH, timer_names) == 1
    assert count_text(RIGHT_PANE_PATH, "QTimer") > count_built(
        RIGHT_PANE_PATH, timer_names
    )
    started: list = []
    first_start = QObject.startTimer
    first_timer = QTimer.start
    first_single = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return first_start(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return first_timer(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", args))
        return first_single(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        old_screen()
        with_pane = list(started)
        started.clear()
        old_screen(right_pane=False)
        without_pane = list(started)
        started.clear()
        new_screen()
        new_started = list(started)
    finally:
        QObject.startTimer = first_start
        QTimer.start = first_timer
        QTimer.singleShot = first_single
    assert [name for name, _args in with_pane] == ["QTimer.start"], with_pane
    assert without_pane == [], without_pane
    assert new_started == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(surface.TIMERS) == SCREEN_TIMER_BUILDS


def test_the_screen_declares_no_signal_of_its_own():
    """A signal declaration appeared on one side and not the other."""
    signal_names = ("Signal",)
    assert count_built(SCREEN_PATH, signal_names) == SCREEN_SIGNAL_BUILDS == 0
    assert count_built(SURFACE_PATH, signal_names) == 0
    assert count_built(SIGNAL_CONTROL_PATH, signal_names) == CONTROL_SIGNAL_BUILDS == 3
    assert count_text(SIGNAL_CONTROL_PATH, "Signal") > CONTROL_SIGNAL_BUILDS


def test_the_screen_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_text(SCREEN_PATH, ".subscribe(") == SCREEN_BUS_SITES == 0
    assert count_text(SURFACE_PATH, ".subscribe(") == 0
    assert count_text(BUS_CONTROL_PATH, ".subscribe(") == CONTROL_BUS_SITES == 2
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_text(SCREEN_PATH, ".subscribe(")


def test_the_screen_elements_the_file_builds_are_counted():
    """The element counter cannot report, so its number means nothing."""
    assert count_elements(SCREEN_PATH) == SCREEN_ELEMENT_BUILDS == 32
    assert count_elements(ELEMENT_CONTROL_PATH) == CONTROL_ELEMENT_BUILDS == 3
    assert count_built(ELEMENT_CONTROL_PATH, WIDGET_NAMES_BUILT) == 2
    assert declared_widget_classes(ELEMENT_CONTROL_PATH) == {"StatCard"}
    assert declared_widget_classes(SCREEN_PATH) == {"MarketInspectorTab"}
    assert count_built(SCREEN_PATH, WIDGET_NAMES_BUILT) == 31
    assert count_elements(SURFACE_PATH) == 0
    assert declared_widget_classes(SURFACE_PATH) == set()


def test_the_class_counter_finds_a_class_declared_inside_another():
    """The class counter reads the top level only, so a nested class is lost."""
    found = declared_classes(NESTED_CLASS_CONTROL_PATH)
    assert "_StockLogHandler" in found, sorted(found)
    assert "StockMainWindow" in found, sorted(found)
    assert len(found) == 4, sorted(found)
    tree = ast.parse(NESTED_CLASS_CONTROL_PATH.read_text(encoding="utf-8"))
    top_level = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert top_level == set(), top_level
    assert declared_classes(SCREEN_PATH) == {"MarketInspectorTab"}
    assert {
        node.name
        for node in ast.parse(SCREEN_PATH.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ClassDef)
    } == set()


# Every class, function and method has a counterpart


def members(owner):
    """Every method, factory and read-only value a class declares, by name.

    A signal is callable and is not a method, so it is excluded by name.
    A read-only value is not callable at all, so asking ``callable``
    alone misses it.
    """
    import inspect

    from PySide6.QtCore import Signal

    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if isinstance(value, Signal):
            continue
        if inspect.isfunction(value) or isinstance(
            value, (property, classmethod, staticmethod)
        ):
            found.add(name)
    return found


def test_the_member_counter_excludes_a_signal_and_finds_both_quiet_shapes():
    """The counter counts a signal, or misses a factory or a read-only value."""
    from PySide6.QtCore import Signal

    from src.gui import indicator_panel, launcher

    app()
    panel = indicator_panel.IndicatorVotingPanel
    assert callable(Signal())
    assert isinstance(vars(launcher.ModeCard)["clicked"], Signal)
    assert "clicked" not in members(launcher.ModeCard)
    assert "__init__" in members(launcher.ModeCard)
    assert isinstance(vars(panel)["_reading_fingerprint"], staticmethod)
    assert "_reading_fingerprint" in members(panel)
    assert isinstance(vars(panel)["lock_timeframe"], property)
    assert not callable(vars(panel)["lock_timeframe"])
    assert "lock_timeframe" in members(panel)
    assert isinstance(vars(panel)["selected_bot_id"], property)
    assert not callable(vars(panel)["selected_bot_id"])
    assert "selected_bot_id" in members(panel)


CLASS_MAP = {"MarketInspectorTab": "MarketInspectorScreenModel"}

METHOD_MAP = {
    "MarketInspectorTab.__init__": "MarketInspectorScreenModel.__init__",
    "MarketInspectorTab.update_active_symbols": (
        "MarketInspectorScreenModel.update_active_symbols"
    ),
    "MarketInspectorTab.set_dismiss_store": (
        "MarketInspectorScreenModel.set_dismiss_store"
    ),
    "MarketInspectorTab.set_proposal_source": (
        "MarketInspectorScreenModel.set_proposal_source"
    ),
    "MarketInspectorTab.set_adopt_handler": (
        "MarketInspectorScreenModel.set_adopt_handler"
    ),
    "MarketInspectorTab.current_topology_proposals": (
        "MarketInspectorScreenModel.current_topology_proposals"
    ),
    "MarketInspectorTab.set_exchange_source": (
        "MarketInspectorScreenModel.set_exchange_source"
    ),
    "MarketInspectorTab._start_fetch": "MarketInspectorScreenModel.start_fetch",
    "MarketInspectorTab._fetch_and_analyze": (
        "MarketInspectorScreenModel.fetch_and_analyze"
    ),
    "MarketInspectorTab._on_progress": "MarketInspectorScreenModel.on_progress",
    "MarketInspectorTab._on_toggle_show_active": (
        "MarketInspectorScreenModel.on_toggle_show_active"
    ),
    "MarketInspectorTab._status_line": "MarketInspectorScreenModel.status_line",
    "MarketInspectorTab._render_signals": ("MarketInspectorScreenModel.render_signals"),
}

FUNCTION_MAP = {
    "_fmt_age": "age_text",
    "_signal_color": "signal_color",
    "_fmt_tf_state": "timeframe_text",
    "build_per_bot_view": "build_per_bot_model",
}

HELPER_MAP = {
    "status_line_body": "status_text",
    "active_symbol_parse": "active_symbols_from",
    "bot_asset_parse": "asset_of",
    "signals_table_row": "fill_signal_row",
    "pairs_table_row": "fill_pair_row",
    "table_row_count": "set_row_count",
    "switch_press": "MarketInspectorScreenModel.press_show_active",
    "signals_table_filter": "shown_signals",
    "timeframe_reading": "TimeframeState",
    "market_signal": "SignalState",
    "opposing_pair": "PairState",
    "shared_analyzer": "InspectorSource",
    "right_pane": "TopologyPaneModel",
    "per_bot_screen": "PerBotViewModel",
    "per_bot_read": "per_bot_view",
    "screen_from_fleet": "build_model",
    "whole_state": "build_view_model",
    "shared_screen": "pane_model",
    "bridge_handler": "view_model",
    "scheduled_fetch": "MarketInspectorScreenModel.fetch_call",
    "analyzer_lookup": "MarketInspectorScreenModel.inspector",
    "fetcher_lookup": "MarketInspectorScreenModel.fetch_universe",
}

SCREEN_MODEL_MEMBERS = {
    "__init__",
    "inspector",
    "fetch_universe",
    "update_active_symbols",
    "set_dismiss_store",
    "set_proposal_source",
    "set_adopt_handler",
    "current_topology_proposals",
    "set_exchange_source",
    "start_fetch",
    "fetch_call",
    "fetch_and_analyze",
    "on_progress",
    "press_show_active",
    "on_toggle_show_active",
    "status_line",
    "render_signals",
}

PER_BOT_MODEL_MEMBERS = {
    "__init__",
    "mark",
    "inspector",
    "build",
    "own_card_rows",
    "higher_rows",
    "pair_lines",
}

INSPECTOR_SOURCE_MEMBERS = {"__init__", "scan_universe", "get_signal"}

PANE_MODEL_MEMBERS = {
    "__init__",
    "set_dismiss_store",
    "set_proposal_source",
    "current_proposals",
    "adoptRequested",
    "connect",
}


def resolve(dotted):
    """The member a dotted name in a map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def shipped_classes():
    """Every class the shipped module declares, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def shipped_functions():
    """Every function the shipped module declares, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def test_every_shipped_class_function_and_method_has_a_counterpart():
    """A class, a function or a method exists on one side and not the other."""
    app()
    assert shipped_classes() == set(CLASS_MAP)
    assert len(CLASS_MAP) == 1
    assert shipped_functions() == set(FUNCTION_MAP), sorted(
        shipped_functions() ^ set(FUNCTION_MAP)
    )
    assert len(FUNCTION_MAP) == 4
    found = {}
    for name in sorted(shipped_classes()):
        for member in members(getattr(shipped, name)):
            found["%s.%s" % (name, member)] = member
    assert set(found) == set(METHOD_MAP), sorted(set(found) ^ set(METHOD_MAP))
    assert len(METHOD_MAP) == 13
    targets = (
        set(METHOD_MAP.values())
        | set(CLASS_MAP.values())
        | set(FUNCTION_MAP.values())
        | set(HELPER_MAP.values())
    )
    for target in sorted(targets):
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 22
    assert members(surface.MarketInspectorScreenModel) == SCREEN_MODEL_MEMBERS, sorted(
        members(surface.MarketInspectorScreenModel) ^ SCREEN_MODEL_MEMBERS
    )
    assert len(SCREEN_MODEL_MEMBERS) == 17
    assert members(surface.PerBotViewModel) == PER_BOT_MODEL_MEMBERS, sorted(
        members(surface.PerBotViewModel) ^ PER_BOT_MODEL_MEMBERS
    )
    assert members(surface.InspectorSource) == INSPECTOR_SOURCE_MEMBERS
    assert members(surface.TopologyPaneModel) == PANE_MODEL_MEMBERS, sorted(
        members(surface.TopologyPaneModel) ^ PANE_MODEL_MEMBERS
    )
    assert declared_classes(SCREEN_PATH) == set(CLASS_MAP)


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    app()
    assert "update_active_symbols" in members(shipped.MarketInspectorTab)
    assert "_render_signals" in members(shipped.MarketInspectorTab)
    assert "MarketInspectorTab" not in SCREEN_MODEL_MEMBERS
    with pytest.raises(AttributeError):
        resolve("MarketInspectorScreenModel.no_such_member")
    assert SCREEN_MODEL_MEMBERS - {"render_signals"} != SCREEN_MODEL_MEMBERS
    assert (
        members(surface.MarketInspectorScreenModel) - {"start_fetch"}
        != SCREEN_MODEL_MEMBERS
    )
    assert PER_BOT_MODEL_MEMBERS - {"build"} != PER_BOT_MODEL_MEMBERS
    assert set(METHOD_MAP) - {"MarketInspectorTab.__init__"} != set(METHOD_MAP)
    assert shipped_classes() - {"MarketInspectorTab"} != shipped_classes()
    assert shipped_functions() - {"build_per_bot_view"} != shipped_functions()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the window passes it."""
    import inspect

    app()
    assert list(
        inspect.signature(shipped.MarketInspectorTab.update_active_symbols).parameters
    ) == list(
        inspect.signature(
            surface.MarketInspectorScreenModel.update_active_symbols
        ).parameters
    )
    assert list(
        inspect.signature(shipped.MarketInspectorTab.set_exchange_source).parameters
    ) == ["self", "connectors_getter", "scheduler"]
    assert list(
        inspect.signature(
            surface.MarketInspectorScreenModel.set_exchange_source
        ).parameters
    ) == ["self", "connectors_getter", "scheduler"]
    assert list(
        inspect.signature(shipped.MarketInspectorTab._start_fetch).parameters
    ) == list(
        inspect.signature(surface.MarketInspectorScreenModel.start_fetch).parameters
    )
    assert list(
        inspect.signature(shipped.MarketInspectorTab._fetch_and_analyze).parameters
    ) == list(
        inspect.signature(
            surface.MarketInspectorScreenModel.fetch_and_analyze
        ).parameters
    )
    assert list(inspect.signature(shipped._fmt_age).parameters) == ["seconds"]
    assert list(inspect.signature(surface.age_text).parameters) == ["seconds"]
    assert list(inspect.signature(shipped.build_per_bot_view).parameters) == ["bot"]
    assert list(inspect.signature(surface.build_per_bot_model).parameters) == [
        "bot",
        "inspector_source",
    ]
    assert list(inspect.signature(surface.view_model).parameters) == ["params"]


def test_the_stand_in_analyzer_answers_the_way_the_real_one_does():
    """The stand-in analyzer reads differently from the shipped analyzer."""
    import inspect

    for name in ("scan_universe", "get_signal"):
        assert list(
            inspect.signature(getattr(analyzer.MarketInspector, name)).parameters
        ) == list(
            inspect.signature(getattr(surface.InspectorSource, name)).parameters
        ), name
    assert isinstance(vars(analyzer.MarketInspector)["last_signals"], property)
    assert isinstance(vars(analyzer.MarketInspector)["last_pairs"], property)
    real = analyzer.MarketInspector()
    assert real.last_signals == []
    assert real.last_pairs == []
    assert real.get_signal("BTC") is None
    stand_in = surface.InspectorSource()
    assert stand_in.last_signals == []
    assert stand_in.last_pairs == []
    assert stand_in.get_signal("BTC") is None
    seeded = surface.InspectorSource(signals=[signal(symbol="BTC")])
    assert seeded.get_signal("BTC").symbol == "BTC"
    assert seeded.get_signal("ETH") is None


def dotted_name(path):
    """The dotted module name one file under the repo root carries."""
    parts = path.relative_to(REPO_ROOT).with_suffix("").parts
    return ".".join(parts)


def imported_modules(path):
    """Every module one file imports, as a full dotted name.

    A relative import is resolved against the file's own package, so
    ``src.gui.market_inspector`` and ``src.trading.market_inspector``
    are told apart. They share a last part and are two different files.
    """
    package = dotted_name(path).rsplit(".", 1)[0].split(".")
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            root = list(package[: len(package) - node.level + 1]) if node.level else []
            tail = [node.module] if node.module else []
            base = ".".join(root + tail)
            found.add(base)
            found.update("%s.%s" % (base, alias.name) for alias in node.names)
    return found


def modules_importing(module, skip=()):
    """Every file under src that imports the module named exactly `module`."""
    found = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path in skip:
            continue
        if module in imported_modules(path):
            found.append(str(path))
    return found


def test_the_screen_is_reached_by_two_windows_and_the_surface_by_the_bridge():
    """The count of readers is wrong, so a lost reader would pass unseen."""
    readers = modules_importing(
        "src.gui.market_inspector", skip=(SURFACE_PATH, SCREEN_PATH)
    )
    assert readers == [
        str(REPO_ROOT / "src/gui/live_settings/market_inspector_tab.py"),
        str(REPO_ROOT / "src/gui/main_tabs/market_inspector_tab.py"),
    ], readers
    analyzer_readers = modules_importing("src.trading.market_inspector")
    assert str(REPO_ROOT / "src/gui/main_window.py") in analyzer_readers
    assert set(readers).isdisjoint(analyzer_readers), "two files share a name"
    assert modules_importing("src.gui.main_tabs.market_inspector_surface") == [
        str(REPO_ROOT / "src/core/desktop_bridge.py")
    ]
    known = modules_importing("src.gui.design_system")
    assert len(known) > 5, known


# The screen paints, and the two sides paint the same pixels


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def old_screen_for_picture(name):
    """One shipped screen with a plain right pane, drawn from one case."""
    state = CASES[name]()
    app()
    seat_inspector(state["signals"], state["pairs"])
    tab = old_screen(right_pane=False)
    tab._last_meta = dict(state["meta"])
    tab._render_signals()
    return tab


def model_payload(name):
    """The surface's whole payload for one case, stamped as it comes off."""
    state = CASES[name]()
    seat_inspector(state["signals"], state["pairs"])
    model = new_screen()
    model.last_meta = dict(state["meta"])
    model.render_signals()
    return sealed(surface.build_view_model(model))


def screen_painted_by_the_model(payload):
    """One whole screen built only from the surface's view model."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import (
        QCheckBox,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QPushButton,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    payload = unaltered(payload)
    app()
    screen = hold(QWidget())
    outer = QVBoxLayout(screen)
    outer.setContentsMargins(*payload["outer_margins_px"])
    outer.setSpacing(payload["outer_spacing_px"])
    splitter = QSplitter(Qt.Horizontal)
    outer.addWidget(splitter)

    left = QWidget()
    layout = QVBoxLayout(left)
    layout.setContentsMargins(*payload["left_margins_px"])
    layout.setSpacing(payload["left_spacing_px"])

    top = QHBoxLayout()
    top.setSpacing(payload["top_row_spacing_px"])
    refresh = QPushButton(payload["refresh_label"])
    refresh.setToolTip(payload["refresh_tooltip"])
    refresh.setEnabled(payload["refresh_enabled"])
    top.addWidget(refresh)
    switch = QCheckBox(payload["show_active_label"])
    switch.setChecked(payload["show_active_checked"])
    switch.setToolTip(payload["show_active_tooltip"])
    top.addWidget(switch)
    top.addStretch()
    status = QLabel(payload["status_text"])
    status.setStyleSheet(payload["status_style"])
    top.addWidget(status)
    layout.addLayout(top)

    def table_of(columns, rows, max_height):
        table = QTableWidget()
        table.setColumnCount(len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(payload["table_alternating_rows"])
        table.setMaximumHeight(max_height)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, (text, colour) in enumerate(row):
                item = QTableWidgetItem(text)
                if colour:
                    item.setForeground(QColor(colour))
                table.setItem(row_index, column_index, item)
        return table

    signals_group = QGroupBox(payload["signals_group_title"])
    signals_layout = QVBoxLayout(signals_group)
    signals_layout.addWidget(
        table_of(
            payload["signal_columns"],
            payload["signal_rows"],
            payload["signals_max_height_px"],
        )
    )
    layout.addWidget(signals_group)

    pairs_group = QGroupBox(payload["pairs_group_title"])
    pairs_layout = QVBoxLayout(pairs_group)
    pairs_layout.addWidget(
        table_of(
            payload["pair_columns"],
            payload["pair_rows"],
            payload["pairs_max_height_px"],
        )
    )
    layout.addWidget(pairs_group)
    layout.addStretch()

    splitter.addWidget(left)
    splitter.addWidget(QWidget())
    splitter.setStretchFactor(0, payload["splitter_stretch"][0])
    splitter.setStretchFactor(1, payload["splitter_stretch"][1])
    splitter.setSizes(payload["splitter_sizes_px"])
    return screen


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a screen the shipped screen does not."""
    app()
    old_side = render_offscreen(old_screen_for_picture(name), PIXEL_SIZE)
    new_side = render_offscreen(
        screen_painted_by_the_model(model_payload(name)), PIXEL_SIZE
    )
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the surface paints."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(old_screen_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            screen_painted_by_the_model(model_payload("empty")), PIXEL_SIZE
        ),
        note="one paired market against none",
    )
    assert_pictures_differ(
        old_side=render_offscreen(old_screen_for_picture("empty"), PIXEL_SIZE),
        new_side=render_offscreen(
            screen_painted_by_the_model(model_payload("three_rows")), PIXEL_SIZE
        ),
        note="no markets against three",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_screen_for_picture("happy"), PIXEL_SIZE),
        new_side=render_offscreen(
            screen_painted_by_the_model(model_payload("happy")), PIXEL_SIZE
        ),
        note="one case, both sides",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused():
    """A render of a changed payload would measure the machine, not the product."""
    payload = model_payload("happy")
    payload["refresh_label"] = "moved"
    with pytest.raises(AssertionError):
        screen_painted_by_the_model(payload)
    with pytest.raises(AssertionError):
        screen_painted_by_the_model({"refresh_label": ""})
    assert screen_painted_by_the_model(model_payload("happy")) is not None


def test_the_screen_declares_no_skin_of_its_own():
    """A colour the surface ships is one the screen never paints.

    The rule the control applies is one neither side sets, so the
    difference it makes is the rule and not a value already there.
    """
    from tests.qt_pixel import render_widget

    app()
    assert surface.SKIN == {}
    assert surface.STYLE_SHEET == ""
    assert old_screen().styleSheet() == ""
    assert "QWidget" not in surface.STATUS_STYLE
    assert "background-color" not in surface.STATUS_STYLE
    assert "background-color" not in surface.NO_SCAN_STYLE
    skinned = screen_painted_by_the_model(model_payload("happy"))
    skinned.setStyleSheet("QWidget { background-color: #3a1414; }")
    assert_pictures_differ(
        old_side=render_widget(old_screen_for_picture("happy"), PIXEL_SIZE),
        new_side=render_widget(skinned, PIXEL_SIZE),
        note="a rule the screen does not set",
    )
    assert_pictures_match(
        old_side=render_widget(old_screen_for_picture("happy"), PIXEL_SIZE),
        new_side=render_widget(
            screen_painted_by_the_model(model_payload("happy")), PIXEL_SIZE
        ),
        note="neither side carries a skin of its own",
    )


def test_the_pane_widths_are_compared_as_asked_for():
    """The widths the screen was given differ between the two sides."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter, QWidget

    app()
    assert surface.SPLITTER_SIZES_PX == (800, 800)
    equal = QSplitter(Qt.Horizontal)
    equal.addWidget(QWidget())
    equal.addWidget(QWidget())
    equal.setSizes(list(surface.SPLITTER_SIZES_PX))
    unequal = QSplitter(Qt.Horizontal)
    unequal.addWidget(QWidget())
    unequal.addWidget(QWidget())
    unequal.setSizes([100, 900])
    assert equal.sizes() != unequal.sizes(), "the read-back ignores the ask"
    settled = old_screen()._outer_splitter.sizes()
    assert settled != list(surface.SPLITTER_SIZES_PX), settled


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves nothing."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert wide > narrow
    else:
        assert wide == narrow


@skip_unless_no_fonts
def test_with_no_font_database_every_letter_advances_alike():
    """Two strings of equal length measured apart with no font database."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_with_a_font_database_the_letters_advance_apart():
    """A run holding fonts measured every glyph the same width."""
    app()
    assert app_font_advance_px(WIDE_LABEL) > app_font_advance_px(NARROW_LABEL)


# What a picture cannot see


def test_the_refresh_tooltip_is_compared_as_a_string():
    """The words the Refresh button explains itself with reached no pixel."""
    app()
    assert old_screen()._refresh_btn.toolTip() == surface.REFRESH_TOOLTIP
    assert len(surface.REFRESH_TOOLTIP) > 100


def test_the_include_active_tooltip_is_compared_as_a_string():
    """The words the switch explains itself with reached no pixel."""
    app()
    assert old_screen()._show_active_chk.toolTip() == surface.SHOW_ACTIVE_TOOLTIP
    assert len(surface.SHOW_ACTIVE_TOOLTIP) > 100


def test_the_table_reading_rules_are_compared_as_values():
    """A table became editable, or stopped striping its rows, on one side."""
    app()
    tab = old_screen()
    for table in (tab._signals_tbl, tab._pairs_tbl):
        assert table.editTriggers().name == surface.TABLE_EDIT_TRIGGERS
        assert table.alternatingRowColors() is surface.TABLE_ALTERNATING_ROWS
        assert (
            table.horizontalHeader().sectionResizeMode(0).name
            == surface.TABLE_RESIZE_MODE
        )
    assert surface.TABLE_EDIT_TRIGGERS == "NoEditTriggers"
    assert surface.TABLE_RESIZE_MODE == "ResizeToContents"


def test_the_table_heights_are_compared_as_values():
    """A table grew past the height the screen gives it."""
    app()
    tab = old_screen()
    assert tab._signals_tbl.maximumHeight() == surface.SIGNALS_MAX_HEIGHT_PX == 360
    assert tab._pairs_tbl.maximumHeight() == surface.PAIRS_MAX_HEIGHT_PX == 180
    assert surface.SIGNALS_MAX_HEIGHT_PX != surface.PAIRS_MAX_HEIGHT_PX


def test_the_signal_colours_are_compared_as_exact_text():
    """A swapped colour channel reads the same, so a wrong colour passes.

    Every colour is compared as text in one spelling. The five signal
    colours each hold three different channels, so a channel swap
    changes the text. The fallback ``#888`` holds three equal channels
    and cannot show a swap at all, which is why it is compared as exact
    text and said so here. Its digit count is part of that text: Qt
    expands it to ``#888888`` when it paints, so the two spellings are
    one colour and two strings.
    """
    from PySide6.QtGui import QColor

    told_apart = (
        surface.COLOR_ENTRY_LONG_HIGH,
        surface.COLOR_ENTRY_LONG,
        surface.COLOR_ENTRY_SHORT_HIGH,
        surface.COLOR_ENTRY_SHORT,
        surface.COLOR_WATCHLIST,
        surface.COLOR_ACTIVE,
        surface.COLOR_CORRELATION,
    )
    for colour in told_apart:
        assert len(colour) == 7, colour
        assert len({colour[1:3], colour[3:5], colour[5:7]}) > 1, colour
        assert colour == colour.lower(), colour
    flat = surface.COLOR_OTHER
    assert flat == "#888"
    assert len(flat) == 4, "the flat colour is written in three digits"
    assert len({flat[1], flat[2], flat[3]}) == 1, flat
    assert QColor(flat).name() == "#888888"
    assert QColor(flat).name() != flat
    assert len(set(told_apart)) == len(told_apart)


def test_each_signal_name_reaches_its_own_colour_on_both_sides():
    """Two signal names share one colour, so a wrong colour reads as right."""
    names = (
        "ENTRY_LONG_HIGH",
        "ENTRY_LONG_MEDIUM",
        "ENTRY_SHORT_HIGH",
        "ENTRY_SHORT_LOW",
        "WATCHLIST",
        "NONE",
        "",
        "entry_long_high",
    )
    old_colours = [shipped._signal_color(name) for name in names]
    new_colours = [surface.signal_color(name) for name in names]
    assert old_colours == new_colours, list(zip(names, old_colours, new_colours))
    assert len(set(old_colours)) == 6, old_colours


def test_each_snapshot_age_reads_the_same_on_both_sides():
    """A snapshot age was worded differently on one side."""
    spans = (0, 1.5, 59.9, 60, 3599, 3600, 3660, 7200, 86399, 86400, 200000, -5, 1e-9)
    assert [shipped._fmt_age(span) for span in spans] == [
        surface.age_text(span) for span in spans
    ]
    assert len({shipped._fmt_age(span) for span in spans}) > 5


def test_each_timeframe_reading_reads_the_same_on_both_sides():
    """A band reading was worded differently on one side."""
    readings = (
        None,
        reading(),
        reading(at_upper_extreme=False, at_lower_extreme=True, tightening=False),
        reading(at_upper_extreme=False, tightening=False),
        reading(bb_position=float("nan"), z_score=float("inf")),
    )
    old_text = [shipped._fmt_tf_state(one) for one in readings]
    new_text = [surface.timeframe_text(one) for one in readings]
    assert old_text == new_text, list(zip(old_text, new_text))
    assert len(set(old_text)) == len(readings)


def test_the_recorded_steps_are_compared_as_values():
    """The recorded steps are a list nothing reads, so a lost step is unseen."""
    state = CASES["happy"]()
    seat_inspector(state["signals"], state["pairs"])
    model = new_screen()
    model.render_signals()
    names = [call[0] for call in model.calls]
    assert names.count(surface.STATUS_WRITTEN) == 1
    assert names.count(surface.SIGNALS_DRAWN) == 1
    assert names.count(surface.PAIRS_DRAWN) == 1
    assert surface.SCREEN_BUILT in names
    payload = surface.build_view_model(model)
    assert payload["calls"] == [list(call) for call in model.calls]
    assert set(names) <= set(surface.CALL_NAMES), sorted(
        set(names) - set(surface.CALL_NAMES)
    )


def test_the_bare_cell_carries_no_colour_on_either_side():
    """A cell the screen leaves plain took a colour on one side.

    The two sides are compared cell by cell, and the case driven here
    holds both a plain cell and a coloured one, so the comparison cannot
    pass by finding every cell plain.
    """
    run = drive(["happy"])
    both_sides_agree(run, "happy")
    colours = [cell[1] for row in run["old"]["signal_rows"] for cell in row]
    assert "" in colours, colours
    assert painted(surface.COLOR_ENTRY_LONG_HIGH) in colours, colours
    assert run["old"]["signal_rows"][0][0][1] == ""
    assert run["old"]["signal_rows"][0][1][1] != ""
    payload = surface.build_view_model(new_screen())
    assert payload["colors"]["none"] == surface.NO_COLOR == ""
    assert payload["no_cell"] is surface.NO_CELL is None
    assert painted(surface.NO_COLOR) == ""
    assert painted(surface.NO_CELL) is None
    assert painted(surface.COLOR_ENTRY_LONG_HIGH) != ""


BLIND_TO_THE_PICTURE = {
    "refresh tooltip": "test_the_refresh_tooltip_is_compared_as_a_string",
    "switch tooltip": "test_the_include_active_tooltip_is_compared_as_a_string",
    "table reading rules": "test_the_table_reading_rules_are_compared_as_values",
    "table heights": "test_the_table_heights_are_compared_as_values",
    "signal colours": "test_the_signal_colours_are_compared_as_exact_text",
    "colour per signal": "test_each_signal_name_reaches_its_own_colour_on_both_sides",
    "snapshot age": "test_each_snapshot_age_reads_the_same_on_both_sides",
    "band reading": "test_each_timeframe_reading_reads_the_same_on_both_sides",
    "recorded steps": "test_the_recorded_steps_are_compared_as_values",
    "bare cell": "test_the_bare_cell_carries_no_colour_on_either_side",
    "pane widths": "test_the_pane_widths_are_compared_as_asked_for",
    "fetch wiring": "test_pressing_refresh_hands_the_fetch_to_the_loop_on_both_sides",
    "scheduler refusal": (
        "test_a_scheduler_that_refuses_writes_the_same_line_on_both_sides"
    ),
    "fetch report": "test_a_fetch_that_refuses_writes_the_same_report_on_both_sides",
    "analyzer refusal": (
        "test_an_analyzer_that_refuses_a_scan_hides_its_own_words_on_both_sides"
    ),
    "analyzer gone": "test_an_unreachable_analyzer_writes_the_same_line_on_both_sides",
    "pane wiring": "test_the_three_wiring_points_reach_the_pane_on_both_sides",
    "pane refusal": "test_a_pane_that_refuses_to_list_its_proposals_answers_nothing",
    "per-bot cards": "test_the_per_bot_screen_is_the_shipped_screen",
    "top-five limit": (
        "test_the_higher_scoring_card_holds_at_most_five_rows_on_both_sides"
    ),
    "refusal type": "test_a_refused_input_refuses_the_same_way_on_both_sides",
    "refusal wording": "test_the_refusal_reader_reports_two_different_wordings",
    "log lines": "test_the_two_sides_write_the_same_lines_when_a_fetch_refuses",
    "switch wiring": ("test_the_switch_really_reaches_the_slot_on_the_shipped_screen"),
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 24
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


# The screen writes under the logger it names


def lines_from(logger_name, run, level=logging.WARNING):
    """Every line one named logger emits while `run` is running.

    The handler is attached to the named logger, never through a capture
    fixture: this project's loggers do not pass their records up, so a
    fixture reading the root logger would see nothing. It is detached
    even when `run` refuses part way, and each record is flushed as it
    arrives. One side at a time: a recorder wrapped around both sides
    would report the sum and hide a line lost on one of them.
    """
    found: list = []

    class Recorder(logging.Handler):
        def emit(self, record):
            found.append(record.getMessage())
            self.flush()

    handler = Recorder()
    target = logging.getLogger(logger_name)
    target.addHandler(handler)
    was = target.level
    target.setLevel(level)
    try:
        guarded(run)
    finally:
        target.removeHandler(handler)
        target.setLevel(was)
    return found


def test_the_two_sides_write_the_same_lines_when_a_fetch_refuses(monkeypatch):
    """A failed fetch is announced differently on one side."""
    invented_fetcher(monkeypatch, {}, raises=RuntimeError("venue down"))
    app()
    tab = old_screen()
    seat_inspector([], [])
    old_said = lines_from(
        surface.LOGGER_NAME,
        lambda: asyncio.run(tab._fetch_and_analyze({"venue": object()})),
        level=logging.DEBUG,
    )
    model = new_screen()
    seat_inspector([], [])
    new_said = lines_from(
        surface.LOGGER_NAME,
        lambda: asyncio.run(model.fetch_and_analyze({"venue": object()})),
        level=logging.DEBUG,
    )
    assert old_said == new_said, (old_said, new_said)
    assert len(old_said) == 1, old_said
    assert "market inspector fetch failed" in old_said[0]


def test_the_line_recorder_can_report():
    """The recorder sees nothing whatever the code says, so silence is empty."""
    said = lines_from(
        surface.LOGGER_NAME,
        lambda: logging.getLogger(surface.LOGGER_NAME).warning("a seeded line"),
    )
    assert said == ["a seeded line"]
    seat_inspector([], [])
    quiet = lines_from(surface.LOGGER_NAME, lambda: new_screen().render_signals())
    assert quiet == []
    survived = lines_from(
        surface.LOGGER_NAME,
        lambda: [
            logging.getLogger(surface.LOGGER_NAME).warning("before the refusal"),
            surface.age_text(float("inf")),
        ],
    )
    assert survived == ["before the refusal"], survived
    assert logging.getLogger(surface.LOGGER_NAME).handlers == []


def test_the_surface_writes_under_the_logger_the_screen_names():
    """The surface writes under a name no operator log is collected from."""
    assert surface.LOGGER_NAME == "acervator.market_inspector_gui"
    assert surface.logger.name == surface.LOGGER_NAME
    assert shipped.logger.name == surface.LOGGER_NAME


# Every value reaches the compared snapshot


def freeze(value):
    """One value as a single comparable string."""

    def plain(found):
        if isinstance(found, (tuple, list)):
            return [plain(item) for item in found]
        if isinstance(found, dict):
            return {str(key): plain(item) for key, item in found.items()}
        return found

    return json.dumps(plain(value), sort_keys=True, default=str)


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
        if isinstance(value, (surface.MarketInspectorScreenModel, logging.Logger)):
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
    for name in CASES:
        state = CASES[name]()
        seat_inspector(state["signals"], state["pairs"])
        model = new_screen()
        model.last_meta = dict(state["meta"])
        guarded(model.render_signals)
        guarded(lambda model=model: model.on_toggle_show_active(True))
        payloads.append(surface.build_view_model(model))
    for name in FLEET_LISTS:
        seat_inspector([signal()], [])
        model = new_screen()
        guarded(
            lambda model=model, name=name: model.update_active_symbols(
                FLEET_LISTS[name]
            )
        )
        payloads.append(surface.build_view_model(model))
    unwired = new_screen()
    unwired.start_fetch(force=True)
    payloads.append(surface.build_view_model(unwired))
    empty_venue = new_screen()
    empty_venue.set_exchange_source(lambda: {}, lambda call: None)
    empty_venue.start_fetch()
    payloads.append(surface.build_view_model(empty_venue))
    scheduled = new_screen()
    scheduled.set_exchange_source(lambda: {"venue": object()}, lambda call: None)
    scheduled.start_fetch(force=True)
    scheduled.start_fetch(force=True)
    payloads.append(surface.build_view_model(scheduled))

    def refuse(call):
        raise RuntimeError("no loop")

    refused = new_screen()
    refused.set_exchange_source(lambda: {"venue": object()}, refuse)
    refused.start_fetch()
    payloads.append(surface.build_view_model(refused))
    seat_inspector([], [])
    failing = new_screen(fetcher=refusing_fetcher())
    asyncio.run(failing.fetch_and_analyze({"venue": object()}))
    payloads.append(surface.build_view_model(failing))
    answered = new_screen(
        fetcher=answering_fetcher({"source": "coingecko", "symbol_count": 1})
    )
    answered.inspector_source = surface.InspectorSource(signals=[signal()])
    asyncio.run(answered.fetch_and_analyze({"venue": object()}, force=True))
    payloads.append(surface.build_view_model(answered))
    scanned = new_screen(
        fetcher=answering_fetcher({"source": "cache", "age_seconds": 30.0}),
        inspector_source=surface.InspectorSource(raises=ValueError("bad candles")),
    )
    asyncio.run(scanned.fetch_and_analyze({"venue": object()}))
    payloads.append(surface.build_view_model(scanned))
    talking = new_screen()
    talking.on_progress("two of nine markets")
    payloads.append(surface.build_view_model(talking))
    wired = new_screen(topologies_pane=surface.TopologyPaneModel([{"id": "p1"}]))
    wired.set_dismiss_store("a store")
    wired.set_proposal_source("a getter")
    wired.set_adopt_handler("a handler")
    wired.current_topology_proposals()
    payloads.append(surface.build_view_model(wired))
    bare = new_screen(topologies_pane=object())
    bare.set_dismiss_store("a store")
    bare.set_proposal_source("a getter")
    bare.set_adopt_handler("a handler")
    bare.current_topology_proposals()
    payloads.append(surface.build_view_model(bare))
    paneless = new_screen()
    paneless.set_proposal_source("a getter")
    paneless.set_adopt_handler("a handler")
    payloads.append(surface.build_view_model(paneless))
    blind = new_screen(inspector_source=None)
    refuse_import = analyzer_blocked()
    sys.meta_path.insert(0, refuse_import)
    was = sys.modules.pop("src.trading.market_inspector", None)
    try:
        blind.render_signals()
    finally:
        sys.meta_path.remove(refuse_import)
        if was is not None:
            sys.modules["src.trading.market_inspector"] = was
    payloads.append(surface.build_view_model(blind))
    seat_inspector([signal()], [])
    payloads.append(
        surface.build_view_model(surface.build_model([{"symbol": "BTC/USD"}]))
    )
    payloads.append(surface.build_view_model(surface.build_model()))
    return payloads


def refusing_fetcher():
    """A fetch that always refuses, reaching no network."""

    async def refuse(_connectors, active_symbols=None, progress_cb=None, **rest):
        raise RuntimeError("venue down")

    return refuse


def answering_fetcher(meta):
    """A fetch that always answers, reaching no network."""

    async def answer(_connectors, active_symbols=None, progress_cb=None, **rest):
        return FetchAnswer(meta)

    return answer


COVERED_ELSEWHERE = {
    "PANE_MODEL": "test_importing_the_surface_reads_no_settings_file",
    "LOGGER_NAME": "test_the_surface_writes_under_the_logger_the_screen_names",
    "SPLITTER_SIZES_PX": "test_the_pane_widths_are_compared_as_asked_for",
    "TOPOLOGIES_MISSING_LOG": "test_the_shipped_screen_builds_the_real_right_pane",
    "PER_BOT_UNAVAILABLE_TEXT": (
        "test_a_per_bot_screen_with_no_analyzer_says_so_on_both_sides"
    ),
    "NO_CELL": "test_the_bare_cell_carries_no_colour_on_either_side",
}

PER_BOT_ONLY = (
    "NO_SCAN_TEXT",
    "NO_SCAN_STYLE",
    "NO_SCAN_WORD_WRAP",
    "OWN_CARD_TITLE_FORMAT",
    "UNKNOWN_ASSET_MARK",
    "THIS_ASSET_TEXT",
    "NO_SIGNAL_FORMAT",
    "SIGNAL_LINE_FORMAT",
    "SIGNAL_LINE_STYLE_FORMAT",
    "NO_DIRECTION_MARK",
    "HIGHER_GROUP_TITLE",
    "HIGHER_LIMIT",
    "HIGHER_ROW_FORMAT",
    "HIGHER_ROW_ACTIVE_SUFFIX",
    "HIGHER_ROW_QUIET_SUFFIX",
    "HIGHER_ROW_STYLE_FORMAT",
    "PER_BOT_PAIRS_GROUP_TITLE",
    "PER_BOT_PAIR_FORMAT",
    "LABEL_ELEMENT",
    "GROUP_ELEMENT",
    "STRETCH_ELEMENT",
    "NO_STYLE",
    "NO_WORD_WRAP",
)


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped screen."""
    constants = surface_constants()
    assert len(constants) > 80, len(constants)
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name
    for name in PER_BOT_ONLY:
        assert name in constants, name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    assert "SIGNAL_COLUMNS" in missing_from_payload(surface_constants(), thinned)
    assert "REFRESH_TOOLTIP" in missing_from_payload(surface_constants(), thinned)


PAYLOAD_KEY_SOURCES = {
    "method": "METHOD",
    "accessible_name": "model.accessible_name",
    "style_sheet": "model.style_sheet",
    "skin": "SKIN",
    "refresh_label": "REFRESH_LABEL",
    "refresh_tooltip": "REFRESH_TOOLTIP",
    "refresh_enabled": "model.refresh_enabled",
    "show_active_label": "SHOW_ACTIVE_LABEL",
    "show_active_checked": "model.show_active_checked",
    "no_cell": "NO_CELL",
    "show_active_default": "SHOW_ACTIVE_CHECKED",
    "show_active_tooltip": "SHOW_ACTIVE_TOOLTIP",
    "show_active": "model.show_active",
    "status_text": "model.status_label_text",
    "status_initial_text": "STATUS_INITIAL_TEXT",
    "status_style": "STATUS_STYLE",
    "signals_group_title": "SIGNALS_GROUP_TITLE",
    "signal_columns": "SIGNAL_COLUMNS",
    "signals_max_height_px": "SIGNALS_MAX_HEIGHT_PX",
    "signal_rows": "model.signal_rows",
    "pairs_group_title": "PAIRS_GROUP_TITLE",
    "pair_columns": "PAIR_COLUMNS",
    "pairs_max_height_px": "PAIRS_MAX_HEIGHT_PX",
    "pair_rows": "model.pair_rows",
    "table_resize_mode": "TABLE_RESIZE_MODE",
    "table_edit_triggers": "TABLE_EDIT_TRIGGERS",
    "table_alternating_rows": "TABLE_ALTERNATING_ROWS",
    "splitter_orientation": "SPLITTER_ORIENTATION",
    "splitter_stretch": "SPLITTER_STRETCH",
    "splitter_sizes_px": "SPLITTER_SIZES_PX",
    "splitter_panes": "SPLITTER_PANES",
    "outer_margins_px": "OUTER_MARGINS_PX",
    "outer_spacing_px": "OUTER_SPACING_PX",
    "left_margins_px": "LEFT_MARGINS_PX",
    "left_spacing_px": "LEFT_SPACING_PX",
    "top_row_spacing_px": "TOP_ROW_SPACING_PX",
    "top_row_margins_px": "TOP_ROW_MARGINS_PX",
    "per_bot_spacing_px": "PER_BOT_SPACING_PX",
    "per_bot_margins_px": "PER_BOT_MARGINS_PX",
    "group_margins_px": "GROUP_MARGINS_PX",
    "group_spacing_px": "GROUP_SPACING_PX",
    "per_bot_view": "PER_BOT_MARGINS_PX",
    "active_symbols": "model.active_symbols",
    "last_meta": "model.last_meta",
    "pending_refresh": "model.pending_refresh",
    "exchange_source_wired": "model.connectors_getter",
    "scheduled": "model.scheduled",
    "colors": "COLOR_ENTRY_LONG_HIGH",
    "signal_names": "SIGNAL_ENTRY_LONG_HIGH",
    "timeframe": "TIMEFRAME_KEYS",
    "cells": "ACTIVE_YES",
    "age": "MINUTE_S",
    "sources": "SOURCE_COINGECKO",
    "status_formats": "STATUS_LIVE_FORMAT",
    "fetch_texts": "NOT_WIRED_TEXT",
    "logs": "FETCH_FAILED_LOG",
    "error_meta": "ERROR_META_SOURCE",
    "per_bot": "HIGHER_GROUP_TITLE",
    "elements": "LABEL_ELEMENT",
    "marks": "STRONG_OPEN",
    "symbols": "SYMBOL_SEPARATOR",
    "adopt_signal_name": "MarketInspectorScreenModel.ADOPT_SIGNAL_NAME",
    "timers": "TIMERS",
    "timer_delays_ms": "TIMER_DELAYS_MS",
    "bus_topics": "BUS_TOPICS",
    "actions": "ACTIONS",
    "call_names": "CALL_NAMES",
    "logger_name": "LOGGER_NAME",
    "calls": "model.calls",
}

NONE_SOURCES = ("NO_CELL",)

GROUP_KEYS = {
    "colors",
    "signal_names",
    "timeframe",
    "cells",
    "age",
    "sources",
    "status_formats",
    "fetch_texts",
    "logs",
    "error_meta",
    "per_bot",
    "elements",
    "symbols",
    "marks",
    "per_bot_view",
}

DERIVED_KEYS = {"active_symbols", "exchange_source_wired"}


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("model."):
        return getattr(model, name.split(".", 1)[1])
    return resolve(name)


def backed(key, value, source, model):
    """Whether one payload key carries what its named source holds."""
    held = resolve_source(source, model)
    if key in GROUP_KEYS:
        return freeze(held) in {freeze(item) for item in value.values()}
    if key == "active_symbols":
        return list(value) == sorted(held)
    if key == "exchange_source_wired":
        return value is bool(held and model.scheduler)
    return freeze(value) == freeze(held)


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    seat_inspector([signal()], [])
    model = new_screen()
    model.render_signals()
    payload = surface.build_view_model(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES), sorted(
        set(payload) ^ set(PAYLOAD_KEY_SOURCES)
    )
    for key, source in PAYLOAD_KEY_SOURCES.items():
        if source.startswith("model."):
            assert hasattr(model, source.split(".", 1)[1]), source
        else:
            assert resolve(source) is not None or source in NONE_SOURCES, source
        assert backed(key, payload[key], source, model), key
    assert GROUP_KEYS <= set(payload)
    assert DERIVED_KEYS <= set(payload)


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    seat_inspector([signal()], [])
    model = new_screen()
    model.render_signals()
    payload = surface.build_view_model(model)
    assert backed("refresh_label", payload["refresh_label"], "REFRESH_LABEL", model)
    assert not backed("refresh_label", "Reload", "REFRESH_LABEL", model)
    assert not backed("signal_columns", ["Asset"], "SIGNAL_COLUMNS", model)
    assert not backed("skin", {"a": "b"}, "SKIN", model)
    assert not backed("colors", {"entry_long_high": "#123456"}, "COLOR_OTHER", model)
    assert not backed("active_symbols", ["BTC"], "model.active_symbols", model)
    assert not backed("calls", [], "model.calls", model)


# What the shipped module keeps between screens


def test_the_shipped_module_changes_no_value_the_next_screen_reads():
    """One screen left a changed value behind for the next one."""
    app()
    before = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    for name in CASES:
        guarded(lambda name=name: drive([name]))
    after = {
        name: str(value)
        for name, value in vars(shipped).items()
        if not name.startswith("__") and not callable(value)
    }
    assert after == before


def test_the_shipped_screen_writes_to_the_process_wide_analyzer(monkeypatch):
    """The screen changes no shared state, so no test can disturb another."""
    invented_fetcher(monkeypatch, {"source": "coingecko", "symbol_count": 1})
    app()
    live = surface.InspectorSource()
    setattr(analyzer, SHARED_INSPECTOR_NAME, live)
    assert shared_inspector() is live
    assert live.scans == []
    tab = old_screen()
    tab._active_symbols = {"BTC"}
    asyncio.run(tab._fetch_and_analyze({"venue": object()}, force=True))
    assert len(live.scans) == 1, "the screen reached some other analyzer"
    assert live.scans[0][1] == ["BTC"]
    assert shared_inspector() is live
    model = new_screen()
    model.active_symbols = {"ETH"}
    asyncio.run(model.fetch_and_analyze({"venue": object()}, force=True))
    assert len(live.scans) == 2
    assert live.scans[1][1] == ["ETH"]
    assert model.inspector() is live


def test_each_test_is_given_its_own_analyzer():
    """Two tests share one analyzer, so the order they run in decides both."""
    assert shared_inspector().last_signals == []
    setattr(analyzer, SHARED_INSPECTOR_NAME, surface.InspectorSource([signal()]))
    assert shared_inspector().last_signals != []


def test_each_test_is_given_its_own_analyzer_again():
    """The scan the test above seated survived into this one."""
    assert shared_inspector().last_signals == []


def test_the_guard_refuses_when_the_shared_name_is_absent():
    """The guard resets a name the module does not carry, so it resets nothing."""
    assert hasattr(analyzer, SHARED_INSPECTOR_NAME)
    assert not hasattr(analyzer, "_NO_SUCH_SHARED_NAME")
    assert getattr(analyzer, "_NO_SUCH_SHARED_NAME", "absent") == "absent"
    fresh = analyzer.get_shared_inspector()
    assert fresh is analyzer.get_shared_inspector()
    setattr(analyzer, SHARED_INSPECTOR_NAME, None)
    assert analyzer.get_shared_inspector() is not fresh


def test_the_surface_keeps_no_value_between_two_screens():
    """One screen left a changed value behind for the next one."""
    seat_inspector([signal()], [])
    first = new_screen()
    first.render_signals()
    second = surface.MarketInspectorScreenModel()
    assert second.signal_rows == []
    assert second.pair_rows == []
    assert second.calls != first.calls
    assert second.last_meta == {}
    assert first.signal_rows != []


# The bridge


def test_view_model_is_json_serialisable():
    """The renderer cannot read a payload the bridge cannot encode."""
    seat_inspector([signal()], [])
    model = new_screen()
    model.render_signals()
    payload = surface.build_view_model(model)
    text = json.dumps(payload)
    assert json.loads(text)["method"] == surface.METHOD
    assert len(text) > 1000


def test_the_bridge_registers_the_market_inspector_method():
    """The renderer cannot reach the Market Inspector over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "market_inspector.state"
    assert registered[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 4, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )
    assert answer["ok"] is True
    assert answer["result"]["refresh_label"] == surface.REFRESH_LABEL


def test_the_bridge_import_list_is_alphabetical():
    """The bridge import list drifted out of order."""
    from src.core import desktop_bridge

    source = Path(desktop_bridge.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    names: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.gui.main_tabs":
            names = [alias.name for alias in node.names]
    assert names == sorted(names), names
    assert "market_inspector_surface" in names
    assert names.index("market_inspector_surface") + 1 == names.index(
        "market_inspector_tab_surface"
    )


def test_the_bridge_keeps_the_screen_until_a_reset():
    """The screen forgot its rows between two calls, or kept them past a reset."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 5, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({"reset": True})
    seat_inspector([signal(), signal(symbol="ETH", score=2.0)], [])
    filled = ask({"render": True})
    assert len(filled["signal_rows"]) == 2
    assert len(ask({})["signal_rows"]) == 2
    assert ask({"reset": True})["signal_rows"] == []
    assert surface.PANE_MODEL.signal_rows == []


def test_the_bridge_reports_a_state_it_cannot_read():
    """A broken request answered as if it had worked."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 6,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "meta": {"source": "coingecko", "symbol_count": "many"},
                    "show_active": True,
                },
            }
        ),
        registered,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "ValueError"
    desktop_bridge.handle_line(
        json.dumps({"id": 7, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )


def test_the_bridge_drives_every_step_the_screen_takes():
    """A step the renderer sends never reaches the screen."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 8, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({"reset": True})
    seat_inspector([signal(is_active=True)], [])
    blank = ask({"render": True})
    assert blank["signal_rows"] == []
    listed = ask({"show_active": True})
    assert len(listed["signal_rows"]) == 1
    assert listed["show_active"] is True
    roster = ask({"bot_statuses": [{"symbol": "BTC/USD"}]})
    assert roster["active_symbols"] == ["BTC"]
    proposals = ask({"proposals": [{"id": "p1"}]})
    assert proposals["method"] == surface.METHOD
    aged = ask({"meta": {"source": "cache", "age_seconds": 90.0, "symbol_count": 3}})
    assert aged["last_meta"]["source"] == "cache"
    pressed = ask({"refresh": True, "force": True})
    assert pressed["status_text"] == surface.NOT_WIRED_TEXT
    ask({"reset": True})


# Without Qt at all

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
    "json.dumps({'id': 1, 'method': 'market_inspector.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = BLOCK_QT + (
    "import json, sys\n"
    "from src.gui.main_tabs import market_inspector_surface as s\n"
    "long_side = s.SignalState(symbol='BTC', signal='ENTRY_LONG_HIGH',\n"
    "    score=3.0, direction='long', per_tf={\n"
    "        '1d': s.TimeframeState(0.90, 2.50, True, True, False),\n"
    "        '1w': s.TimeframeState(0.10, -1.20, False, False, True)})\n"
    "short_side = s.SignalState(symbol='ETH', signal='ENTRY_SHORT',\n"
    "    score=2.0, direction='short', per_tf={})\n"
    "held = s.InspectorSource(signals=[long_side, short_side],\n"
    "    pairs=[s.PairState(long_side, short_side, -0.75)])\n"
    "model = s.build_model([{'symbol': 'XRP/USD'}], inspector_source=held)\n"
    "model.last_meta = {'source': 'cache', 'age_seconds': 3660.0,\n"
    "    'symbol_count': 2}\n"
    "model.render_signals()\n"
    "payload = s.build_view_model(model)\n"
    "class Config:\n"
    "    symbol = 'BTC/USD'\n"
    "class Bot:\n"
    "    config = Config()\n"
    "per_bot = s.build_per_bot_model(Bot(), held)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'refresh_label': payload['refresh_label'],\n"
    "    'status_text': payload['status_text'],\n"
    "    'signal_columns': payload['signal_columns'],\n"
    "    'signal_rows': payload['signal_rows'],\n"
    "    'pair_rows': payload['pair_rows'],\n"
    "    'active_symbols': payload['active_symbols'],\n"
    "    'per_bot_asset': per_bot.asset,\n"
    "    'per_bot_groups': [row[1] for row in per_bot.order\n"
    "        if row[0] == 'group'],\n"
    "    'calls': len(payload['calls'])}))\n"
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
    """Reaching the Market Inspector pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == surface.METHOD
    assert result["refresh_label"] == surface.REFRESH_LABEL
    assert result["signal_rows"] == []
    assert result["status_text"] == surface.STATUS_INITIAL_TEXT


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_the_screen_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["refresh_label"] == surface.REFRESH_LABEL
    assert answered["signal_columns"] == list(surface.SIGNAL_COLUMNS)
    assert answered["status_text"] == surface.STATUS_CACHE_FORMAT.format(
        age="1h 1m", count=2
    )
    assert len(answered["signal_rows"]) == 2
    assert answered["signal_rows"][0][1] == [
        "ENTRY_LONG_HIGH",
        surface.COLOR_ENTRY_LONG_HIGH,
    ]
    assert len(answered["pair_rows"]) == 1
    assert answered["active_symbols"] == ["XRP"]
    assert answered["per_bot_asset"] == "BTC"
    assert answered["per_bot_groups"][0] == surface.OWN_CARD_TITLE_FORMAT.format(
        asset="BTC"
    )
    assert answered["calls"] > 3


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_shipped_file_builds_no_screen_without_qt():
    """The shipped file builds its screen where the surface is not needed.

    The file loads without the old interface library, but everything it
    declares sits behind that library: with it absent the module holds
    no screen class and no per-bot builder at all.
    """
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui import market_inspector as m\n"
        "    out = {'imported': True, 'has_qt': m._HAS_QT,\n"
        "        'has_screen': hasattr(m, 'MarketInspectorTab'),\n"
        "        'has_per_bot': hasattr(m, 'build_per_bot_view'),\n"
        "        'has_helper': hasattr(m, '_fmt_age')}\n"
        "except Exception as exc:\n"
        "    out = {'imported': False, 'error': type(exc).__name__,\n"
        "        'headline': str(exc)}\n"
        "print(json.dumps(out))\n"
    )
    answered = run_script(probe)
    assert answered["imported"] is True, answered
    assert answered["has_qt"] is False, answered
    assert answered["has_screen"] is False, answered
    assert answered["has_per_bot"] is False, answered
    assert answered["has_helper"] is True, answered
    assert "_HAS_QT" in SCREEN_PATH.read_text(encoding="utf-8")


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
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
    screen_imports = {
        (node.module or "")
        for node in ast.walk(ast.parse(SCREEN_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in screen_imports), screen_imports


def test_the_surface_opens_no_file_and_no_socket():
    """The surface reached for a file, a network address or a browser."""
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    reached = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in (
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "mkdir",
        "urlopen",
        "socket",
        "listen",
    ):
        assert forbidden not in reached, forbidden
    text = SURFACE_PATH.read_text(encoding="utf-8")
    assert "webbrowser" not in text
    assert "acervator_logs" not in text
    assert "Path.home" not in text


SETTINGS_PROBE = """
import json
import os
import shutil
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-mi-probe-'))
at_import = root / 'at-import'
on_request = root / 'on-request'
at_import.mkdir()
on_request.mkdir()
(at_import / 'settings.json').write_text('{}', encoding='utf-8')
(on_request / 'settings.json').write_text('{}', encoding='utf-8')
os.environ['ACERVATOR_SETTINGS_ROOT'] = str(at_import)

from src.gui.main_tabs import market_inspector_surface as s
from src.trading import market_inspector as a

built_at_import = s.PANE_MODEL is not None
analyzer_at_import = a._GLOBAL_INSPECTOR is not None

os.environ['ACERVATOR_SETTINGS_ROOT'] = str(on_request)
a._GLOBAL_INSPECTOR = s.InspectorSource(
    signals=[s.SignalState(symbol='SEEDED', signal='WATCHLIST', score=1.0)])

payload = s.view_model({'render': True})

from src.core.privacy_mask_registry import get_privacy_mask_registry

answer = {'built_at_import': built_at_import,
          'analyzer_at_import': analyzer_at_import,
          'built_on_request': s.PANE_MODEL is not None,
          'rows': [row[0][0] for row in payload['signal_rows']],
          'points_at': str(get_privacy_mask_registry().settings_path),
          'on_request_file': str(on_request / 'settings.json'),
          'at_import_file': str(at_import / 'settings.json')}
shutil.rmtree(root, ignore_errors=True)
print(json.dumps(answer))
"""


def test_importing_the_surface_reads_no_settings_file():
    """Loading the surface built its screen, or read a folder, at import.

    The settings root is aimed at one folder while the surface is
    imported and at a second folder before the first request. Nothing is
    built at import; the analyzer seeded AFTER the folder moved is what
    the first request reports. The register's own answer is read at the
    end and names the second folder, which proves the folder really
    moved between the two moments.
    """
    answered = run_script(SETTINGS_PROBE)
    assert answered["built_at_import"] is False, answered
    assert answered["analyzer_at_import"] is False, answered
    assert answered["built_on_request"] is True, answered
    assert answered["rows"] == ["SEEDED"], answered
    assert answered["points_at"] == answered["on_request_file"], answered
    assert answered["points_at"] != answered["at_import_file"], answered
