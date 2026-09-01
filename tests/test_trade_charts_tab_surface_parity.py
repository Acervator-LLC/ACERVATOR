"""The Qt Asset Charts tab and the Qt-free surface, driven side by side.

A failure means the view model describes a different panel, a different
label, a different overlay line, a different number format, a different
refusal, a different emitted signal or a different branch than
``TradeChartsTab`` takes on the same input.
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.core import signal_contract as sc
from src.gui.main_tabs import trade_charts_tab_surface as surface
from tests.fixtures.surface_pictures import (
    assert_picture_can_report,
    assert_pictures_differ,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SURFACE_SOURCE = REPO_ROOT / "src" / "gui" / "main_tabs" / "trade_charts_tab_surface.py"

PIXEL_SIZE = (900, 620)

FIXED_NOW = 1_700_000_000.0
TICK_BASE = 500.0
TICK_STEP = 0.25
FIXED_STAMP = "2000-01-01T00:00:00"

LOG_NAME = "acervator.gui"

SHIPPED_CLASS_TOTAL = 1
SHIPPED_METHOD_TOTAL = 6
SHIPPED_FUNCTION_TOTAL = 0
SHIPPED_CONNECT_TOTAL = 1
SHIPPED_SIGNAL_TOTAL = 0
SHIPPED_SIGNAL_EMIT_TOTAL = 0
SHIPPED_BUS_EMIT_TOTAL = 5
SHIPPED_BUS_SUBSCRIBE_TOTAL = 0
SHIPPED_TIMER_BUILT_TOTAL = 0
SHIPPED_TIMER_STARTED_TOTAL = 0
SHIPPED_THREAD_BUILT_TOTAL = 0
SHIPPED_THREAD_STARTED_TOTAL = 0

PAYLOAD_KEY_TOTAL = 33
CONSTANT_TOTAL = 153
CALL_CONSTANT_TOTAL = 42


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=repr).encode(
            "utf-8"
        )
    ).hexdigest()


def canonical(value):
    """`value` as nested text, so a not-a-number compares equal to itself."""
    if isinstance(value, dict):
        return {repr(key): canonical(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical(inner) for inner in value]
    return repr(value)


def first_difference(left, right, where=""):
    """The path to the first value the two sides disagree on, or nothing."""
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right), key=repr):
            if key not in left:
                return f"{where}.{key} missing on the old side"
            if key not in right:
                return f"{where}.{key} missing on the new side"
            found = first_difference(left[key], right[key], f"{where}.{key}")
            if found:
                return found
        return ""
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return f"{where} holds {len(left)} on the old side, {len(right)} on the new"
        for index, (one, other) in enumerate(zip(left, right)):
            found = first_difference(one, other, f"{where}[{index}]")
            if found:
                return found
        return ""
    if left != right:
        return f"{where}: old {left!r}, new {right!r}"
    return ""


def app():
    """The one application object every render is taken against."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


# ---------------------------------------------------------------------
# The recorders. Each side gets its own; neither reads the other's.
# ---------------------------------------------------------------------


class Row:
    """One OHLCV row, of the shape `ChartDataFetcher.fetch` returns."""

    def __init__(self, time, open, high, low, close, volume):
        self.time = time
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


class Lump:
    """A candle carrying its readings as attributes, as Nuclear Mode sends."""

    def __init__(self, time=0, open=0.0, high=0.0, low=0.0, close=0.0, volume=0.0):
        self.time = time
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


class QtFetcher:
    """`ChartDataFetcher` for the Qt side: one answer per call, or a refusal."""

    def __init__(self, answers=None):
        self.answers = list(answers or [])
        self.asked = []

    async def fetch(self, symbol, timeframe, exchange=None, limit=100):
        self.asked.append([symbol, timeframe, exchange, limit])
        if not self.answers:
            return [], ""
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return [Row(*one) for one in answer[0]], answer[1]


class QtBot:
    """The ScrummingBot the Qt tab reads its overlay lines off."""

    def __init__(self, **readings):
        for name, value in readings.items():
            setattr(self, name, value)


class QtManager:
    """The bot manager the Qt tab asks for one bot by id."""

    def __init__(self, bots=None):
        self.bots = dict(bots or {})
        self.asked = []

    def get_bot(self, bot_id):
        self.asked.append(bot_id)
        return self.bots.get(bot_id)


class RecordingSignal:
    """The one signal the Qt panel offers, recording what connected to it."""

    def __init__(self, panel):
        self.panel = panel
        self.handlers = []

    def connect(self, handler):
        self.handlers.append(handler)
        self.panel.timeframe_connected = True
        self.panel.record(["chart.timeframe_changed.connect"])

    def emit(self, value):
        for handler in list(self.handlers):
            handler(value)


class RecordingChart:
    """The chart the Qt tab writes to, recording every call and argument.

    Every method and every attribute the shipped tab reaches for is here
    and records. The slots refuse any other write, so a call this
    recorder cannot see is reported rather than swallowed.
    """

    __slots__ = ("_panel", "_label", "timeframe_changed")

    def __init__(self, panel, symbol):
        self._panel = panel
        self._label = symbol
        self.timeframe_changed = RecordingSignal(panel)

    @property
    def _symbol(self):
        """The header text, as the tab last wrote it."""
        return self._label

    @_symbol.setter
    def _symbol(self, value):
        self._label = value
        self._panel.label = value
        self._panel.record(["chart._symbol", value])

    @property
    def _candles(self):
        """The candles on this chart, which the fetch reads back off it."""
        return self._panel.candles

    @property
    def symbol(self):
        """The pair this chart is titled with."""
        return self._label

    @symbol.setter
    def symbol(self, value):
        self._label = value
        self._panel.label = value
        self._panel.chart_repaints += 1
        self._panel.record(["chart.symbol", value])

    def set_timeframe(self, timeframe):
        self._panel.chart_timeframe = timeframe
        self._panel.record(["chart.set_timeframe", timeframe])

    def set_candles(self, candles):
        self._panel.candles = [
            [one.time, one.open, one.high, one.low, one.close, one.volume]
            for one in candles
        ]
        self._panel.error_text = ""
        self._panel.chart_repaints += 1
        self._panel.record(["chart.set_candles", len(self._panel.candles)])

    def set_error(self, message):
        self._panel.error_text = message
        self._panel.chart_repaints += 1
        self._panel.record(["chart.set_error", message])

    def set_trade_history_markers(self, trades):
        self._panel.markers = [dict(one) for one in trades]
        self._panel.chart_repaints += 1
        self._panel.record(
            ["chart.set_trade_history_markers", len(self._panel.markers)]
        )

    def set_tranche_floors(self, floors):
        self._panel.floors = [list(one) for one in floors]
        self._panel.chart_repaints += 1
        self._panel.record(["chart.set_tranche_floors", len(self._panel.floors)])

    def set_target_balance_lines(self, anchor, ceiling):
        self._panel.tb_anchor = anchor
        self._panel.tb_ceiling = ceiling
        self._panel.chart_repaints += 1
        self._panel.record(["chart.set_target_balance_lines", anchor, ceiling])

    def set_fire_armed_state(
        self, scrum_armed, fold_armed, scrum_blockers=None, fold_blockers=None
    ):
        state = {
            "scrum_armed": bool(scrum_armed),
            "fold_armed": bool(fold_armed),
            "scrum_blockers": list(scrum_blockers or []),
            "fold_blockers": list(fold_blockers or []),
        }
        self._panel.armed = state
        self._panel.chart_repaints += 1
        self._panel.record(["chart.set_fire_armed_state", dict(state)])

    def update(self):
        self._panel.chart_repaints += 1
        self._panel.record(["chart.update"])


class RecordingPanel:
    """`ChartPanel` for the Qt side, recording every call the tab makes.

    Holds the same readings ``PanelSink`` holds, so the two sides are
    compared on what the tab did rather than on what either recorder is.
    """

    made: list = []

    def __init__(self, symbol):
        self.built_with = symbol
        self.label = symbol
        self.timeframe = surface.COMBO_TIMEFRAME
        self.chart_timeframe = ""
        self.candles = []
        self.error_text = ""
        self.source = ""
        self.markers = []
        self.floors = []
        self.tb_anchor = None
        self.tb_ceiling = None
        self.armed = None
        self.minimum_height_px = None
        self.maximum_height_px = None
        self.chart_repaints = 0
        self.panel_repaints = 0
        self.parent_cleared = False
        self.deleted = False
        self.timeframe_connected = False
        self.column = None
        self.calls = []
        self.chart = RecordingChart(self, symbol)
        RecordingPanel.made.append(self)

    def record(self, call):
        self.calls.append(list(call))

    def setMinimumHeight(self, pixels):
        self.minimum_height_px = pixels
        self.record(["setMinimumHeight", pixels])

    def setMaximumHeight(self, pixels):
        self.maximum_height_px = pixels
        self.record(["setMaximumHeight", pixels])

    def set_source(self, source):
        self.source = source
        self.chart_repaints += 1
        self.record(["set_source", source])

    def update(self):
        self.panel_repaints += 1
        self.record(["update"])

    def setParent(self, parent):
        self.parent_cleared = parent is None
        if parent is None and self.column is not None:
            self.column.slots.remove(self)
        self.record(["dropped"])

    def deleteLater(self):
        self.deleted = True

    def as_values(self):
        return {
            "built_with": self.built_with,
            "label": self.label,
            "timeframe": self.timeframe,
            "chart_timeframe": self.chart_timeframe,
            "candles": [list(one) for one in self.candles],
            "candle_count": len(self.candles),
            "error_text": self.error_text,
            "source": self.source,
            "markers": [dict(one) for one in self.markers],
            "floors": [list(one) for one in self.floors],
            "tb_anchor": self.tb_anchor,
            "tb_ceiling": self.tb_ceiling,
            "armed": None if self.armed is None else dict(self.armed),
            "minimum_height_px": self.minimum_height_px,
            "maximum_height_px": self.maximum_height_px,
            "chart_repaints": self.chart_repaints,
            "panel_repaints": self.panel_repaints,
            "parent_cleared": self.parent_cleared,
            "deleted": self.deleted,
            "timeframe_connected": self.timeframe_connected,
            "calls": [list(one) for one in self.calls],
        }


class LayoutSlot:
    """One slot of the scroll column: a panel, or the trailing stretch."""

    def __init__(self, held):
        self.held = held

    def widget(self):
        return self.held


class RecordingLayout:
    """The scroll column, recording what the tab inserts and where."""

    def __init__(self):
        self.slots = [None]

    def count(self):
        return len(self.slots)

    def insertWidget(self, index, widget):
        widget.column = self
        self.slots.insert(index, widget)

    def addStretch(self):
        self.slots.append(None)

    def setSpacing(self, pixels):
        self.spacing_px = pixels

    def setContentsMargins(self, *margins):
        self.margins_px = list(margins)

    def itemAt(self, index):
        return LayoutSlot(self.slots[index])


class SignalRecorder:
    """`signal_contract.emit`, recording what the tab handed it.

    Records and returns. It never raises: the tab wraps every emit in a
    suppression, so a recorder that raised would report nothing at all.
    """

    def __init__(self):
        self.records = []

    def __call__(self, name, actual, expected=None, **named):
        self.records.append(
            {
                "name": name,
                "actual": actual,
                "expected": expected,
                "every": named.get("every", 0.0),
                "duration": named.get("duration"),
                "context": dict(named.get("context") or {}),
            }
        )
        return None


class LogRecorder(logging.Handler):
    """The tab's own logger, recording the arguments and not the wording."""

    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.info = []
        self.refusals = []

    def emit(self, record):
        if record.levelno >= logging.INFO:
            self.info.append([repr(one) for one in record.args])
        else:
            self.refusals.extend(type(one).__name__ for one in record.args)


class Ticker:
    """A counter standing in for the monotonic clock, one step per reading."""

    def __init__(self):
        self.reads = 0

    def __call__(self):
        self.reads += 1
        return TICK_BASE + TICK_STEP * self.reads


# ---------------------------------------------------------------------
# The scenarios. One spec drives both sides; neither reads the other.
# ---------------------------------------------------------------------

LONG_NAME = "L" * 200
FLOOR_LOTS = [
    {"initial_buy_price": 0.5, "units": 2.0},
    {"initial_buy_price": 0.5, "units": 3.0},
    {"initial_buy_price": 12.0, "units": 1.0},
    {"initial_buy_price": 0.0, "units": 9.0},
]
GATE_ON = {
    "scrum_armed": True,
    "fold_armed": False,
    "scrum_blockers": ["cooldown"],
    "fold_blockers": [],
}
HEALTHY_BOT = {
    "_anchor_target_balance": 50.0,
    "_target_balance": 63.53,
    "cycle_growth_cap_usd": 0.549148,
    "_fold_cycle_cap_consumed": 0.5,
    "_current_holdings": 4.0,
    "_quote_to_usd": 1.0,
    "_last_gate_state": GATE_ON,
    "_main_lots": FLOOR_LOTS,
}
CANDLE_ROWS = [
    (1_700_000_000, 1.0, 2.0, 0.5, 1.5, 10.0),
    (1_700_003_600, 1.5, 2.5, 1.0, 2.0, 11.0),
    (1_700_007_200, 2.0, 3.0, 1.5, 2.5, 12.0),
]
FLAT_ROWS = [(1_700_000_000 + i * 60, 5.0, 5.0, 5.0, 5.0, 5.0) for i in range(4)]
NAN_ROWS = [(1_700_000_000, 1.0, float("nan"), 0.5, 1.5, 10.0)]
ONE_ROW = [(1_700_000_000, 1.0, 2.0, 0.5, 1.5, 10.0)]


def status(bot_id="b1", symbol="BTC/USD", price=100.0, state="idle", **extra):
    """One bot status of the shape the running window hands the tab."""
    one = {
        "bot_id": bot_id,
        "symbol": symbol,
        "state": state,
        "exchange": "coinbase",
        "stats": {"current_price": price},
    }
    one.update(extra)
    return one


SCENARIOS = [
    {
        "name": "happy",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [("update", [status()])],
    },
    {
        "name": "two_bots_one_dropped",
        "bots": {"b1": HEALTHY_BOT, "b2": HEALTHY_BOT},
        "steps": [
            ("update", [status(), status("b2", "ETH/USD", 2000.0, "scrumming")]),
            ("update", [status()]),
        ],
    },
    {
        "name": "extractor_filtered",
        "bots": {},
        "steps": [
            (
                "update",
                [status(), status("b9", "*/USDC", 1.0, "idle", mode="extractor")],
            )
        ],
    },
    {
        "name": "wildcard_symbol",
        "bots": {},
        "steps": [("update", [status("b3", "*/USDC")])],
    },
    {
        "name": "blank_bot_id",
        "bots": {},
        "steps": [("update", [status("", "BTC/USD"), status("b4", "")])],
    },
    {
        "name": "empty_statuses",
        "bots": {},
        "steps": [("update", [])],
    },
    {
        "name": "symbol_followed",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [("update", [status()]), ("update", [status(symbol="SOL/USD")])],
    },
    {
        "name": "no_manager",
        "bots": None,
        "steps": [("update", [status()])],
    },
    {
        "name": "manager_has_no_bot",
        "bots": {},
        "steps": [("update", [status()])],
    },
    {
        "name": "zero_price",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [("update", [status(price=0)])],
    },
    {
        "name": "negative_price",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [("update", [status(price=-1.5)])],
    },
    {
        "name": "thousand_million_price",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [("update", [status(price=1_000_000_000.0)])],
    },
    {
        "name": "one_billionth_price",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [("update", [status(price=1e-9)])],
    },
    {
        "name": "infinite_price",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [("update", [status(price=float("inf"))])],
    },
    {
        "name": "minus_infinite_price",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [("update", [status(price=float("-inf"))])],
    },
    {
        "name": "not_a_number_price",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [("update", [status(price=float("nan"))])],
    },
    {
        "name": "price_two_to_the_1023",
        "bots": {},
        "steps": [("update", [status(price=2**1023)])],
    },
    {
        "name": "price_two_to_the_1024",
        "bots": {},
        "steps": [("update", [status(price=2**1024)])],
    },
    {
        "name": "price_stored_true",
        "bots": {},
        "steps": [("update", [status(price=True)])],
    },
    {
        "name": "price_is_text",
        "bots": {},
        "steps": [("update", [status(price="12.7")])],
    },
    {
        "name": "state_is_a_number",
        "bots": {},
        "steps": [("update", [status(state=12)])],
    },
    {
        "name": "unicode_symbol",
        "bots": {},
        "steps": [("update", [status(symbol="₿/€", state="иdle")])],
    },
    {
        "name": "markup_symbol",
        "bots": {},
        "steps": [("update", [status(symbol="<b>BTC</b>/USD")])],
    },
    {
        "name": "apostrophe_symbol",
        "bots": {},
        "steps": [("update", [status(symbol="O'Brien/USD")])],
    },
    {
        "name": "newline_symbol",
        "bots": {},
        "steps": [("update", [status(symbol="BTC\nUSD")])],
    },
    {
        "name": "long_symbol",
        "bots": {},
        "steps": [("update", [status(symbol=LONG_NAME)])],
    },
    {
        "name": "wrong_capitals_state",
        "bots": {},
        "steps": [("update", [status(state="IdLe")])],
    },
    {
        "name": "holdings_zero",
        "bots": {"b1": dict(HEALTHY_BOT, _current_holdings=0.0)},
        "steps": [("update", [status()])],
    },
    {
        "name": "anchor_zero",
        "bots": {"b1": dict(HEALTHY_BOT, _anchor_target_balance=0.0)},
        "steps": [("update", [status()])],
    },
    {
        "name": "anchor_not_a_number",
        "bots": {"b1": dict(HEALTHY_BOT, _anchor_target_balance=float("nan"))},
        "steps": [("update", [status()])],
    },
    {
        "name": "anchor_infinite",
        "bots": {"b1": dict(HEALTHY_BOT, _anchor_target_balance=float("inf"))},
        "steps": [("update", [status()])],
    },
    {
        "name": "anchor_minus_infinite",
        "bots": {"b1": dict(HEALTHY_BOT, _anchor_target_balance=float("-inf"))},
        "steps": [("update", [status()])],
    },
    {
        "name": "anchor_is_text",
        "bots": {"b1": dict(HEALTHY_BOT, _anchor_target_balance="fifty")},
        "steps": [("update", [status()])],
    },
    {
        "name": "anchor_is_numeric_text",
        "bots": {"b1": dict(HEALTHY_BOT, _anchor_target_balance="12.7")},
        "steps": [("update", [status()])],
    },
    {
        "name": "anchor_stored_true",
        "bots": {"b1": dict(HEALTHY_BOT, _anchor_target_balance=True)},
        "steps": [("update", [status()])],
    },
    {
        "name": "holdings_beyond_a_float",
        "bots": {"b1": dict(HEALTHY_BOT, _current_holdings=10**400)},
        "steps": [("update", [status()])],
    },
    {
        "name": "quote_rate_zero",
        "bots": {"b1": dict(HEALTHY_BOT, _quote_to_usd=0.0)},
        "steps": [("update", [status()])],
    },
    {
        "name": "gate_state_missing",
        "bots": {
            "b1": {k: v for k, v in HEALTHY_BOT.items() if k != "_last_gate_state"}
        },
        "steps": [("update", [status()])],
    },
    {
        "name": "gate_state_is_text",
        "bots": {"b1": dict(HEALTHY_BOT, _last_gate_state="armed")},
        "steps": [("update", [status()])],
    },
    {
        "name": "no_lots",
        "bots": {"b1": dict(HEALTHY_BOT, _main_lots=[])},
        "steps": [("update", [status()])],
    },
    {
        "name": "lot_price_is_text",
        "bots": {"b1": dict(HEALTHY_BOT, _main_lots=[{"initial_buy_price": "cheap"}])},
        "steps": [("update", [status()])],
    },
    {
        "name": "lot_units_stored_true",
        "bots": {
            "b1": dict(
                HEALTHY_BOT,
                _main_lots=[{"initial_buy_price": 0.25, "units": True}],
            )
        },
        "steps": [("update", [status()])],
    },
    {
        "name": "trades_become_markers",
        "bots": {"b1": HEALTHY_BOT},
        "steps": [
            ("trade", {"bot_id": "b1", "symbol": "BTC/USD", "side": "sell"}),
            ("trade", {"bot_id": "b1", "symbol": "ETH/USD", "side": "buy"}),
            ("update", [status()]),
        ],
    },
    {
        "name": "trade_overwrites_its_own_stamp",
        "bots": {},
        "steps": [("trade", {"timestamp": "supplied", "bot_id": "b1"})],
    },
    {
        "name": "timeframe_changed_on_a_known_panel",
        "bots": {},
        "steps": [("update", [status()]), ("tf", "b1", "1h")],
    },
    {
        "name": "timeframe_changed_to_another_frame",
        "bots": {},
        "steps": [("update", [status()]), ("tf", "b1", "4h")],
    },
    {
        "name": "timeframe_changed_on_a_dropped_panel",
        "bots": {},
        "steps": [("update", [status()]), ("update", []), ("tf", "b1", "1h")],
    },
    {
        "name": "fetch_returns_candles",
        "bots": {},
        "answers": [(CANDLE_ROWS, "Coinbase OHLCV")],
        "steps": [("update", [status()]), ("fetch",)],
    },
    {
        "name": "fetch_returns_one_candle",
        "bots": {},
        "answers": [(ONE_ROW, "Coinbase OHLCV")],
        "steps": [("update", [status()]), ("fetch",)],
    },
    {
        "name": "fetch_returns_a_flat_series",
        "bots": {},
        "answers": [(FLAT_ROWS, "CoinGecko")],
        "steps": [("update", [status()]), ("fetch",)],
    },
    {
        "name": "fetch_returns_a_not_a_number",
        "bots": {},
        "answers": [(NAN_ROWS, "Cache (stale)")],
        "steps": [("update", [status()]), ("fetch",)],
    },
    {
        "name": "fetch_returns_nothing",
        "bots": {},
        "answers": [([], "No data: Exchange, CoinGecko")],
        "steps": [("update", [status()]), ("fetch",)],
    },
    {
        "name": "fetch_refuses",
        "bots": {},
        "answers": [ValueError("market not found for this pair and timeframe")],
        "steps": [("update", [status()]), ("fetch",)],
    },
    {
        "name": "fetch_twice_is_throttled",
        "bots": {},
        "answers": [(CANDLE_ROWS, "Coinbase OHLCV"), (ONE_ROW, "second")],
        "steps": [("update", [status()]), ("fetch",), ("fetch",)],
    },
    {
        "name": "fetch_with_a_connector",
        "bots": {},
        "answers": [(CANDLE_ROWS, "Coinbase OHLCV")],
        "connectors": {"coinbase": "a connector"},
        "steps": [("update", [status()]), ("fetch",)],
    },
    {
        "name": "fetch_skips_a_wildcard_panel_forever",
        "bots": {},
        "steps": [("nuclear", "b7", "*/USDC", CANDLE_ROWS, "storm", 0.0), ("fetch",)],
    },
    {
        "name": "nuclear_from_objects",
        "bots": {},
        "steps": [("nuclear", "b5", "DOGE/USD", CANDLE_ROWS, "melt", 0.0)],
    },
    {
        "name": "nuclear_from_dicts",
        "bots": {},
        "steps": [("nuclear_dicts", "b5", "DOGE/USD", CANDLE_ROWS, "melt", 0.0)],
    },
    {
        "name": "nuclear_with_no_candles",
        "bots": {},
        "steps": [("nuclear", "b5", "DOGE/USD", [], "quiet", 0.0)],
    },
    {
        "name": "nuclear_with_a_last_price",
        "bots": {},
        "steps": [("nuclear", "b5", "DOGE/USD", CANDLE_ROWS, "surge", 0.125)],
    },
    {
        "name": "nuclear_over_a_live_panel",
        "bots": {},
        "steps": [
            ("update", [status()]),
            ("nuclear", "b1", "BTC/USD", ONE_ROW, "aftershock", 0.0),
        ],
    },
]

BY_NAME = {spec["name"]: spec for spec in SCENARIOS}
REFUSING = ("price_is_text", "state_is_a_number", "price_two_to_the_1024")


# ---------------------------------------------------------------------
# Driving the two sides
# ---------------------------------------------------------------------


@contextlib.contextmanager
def held_still():
    """Hold the clock, the counter and the emitter still for one drive.

    Every seam is process-wide, so each is put back the way it was found
    when the drive ends, whether it ended cleanly or on a refusal.
    """
    import src.gui.native_chart as native
    from src.gui.widgets import trade_charts_tab as shipped

    first_time = time.time
    first_monotonic = time.monotonic
    first_emit = sc.emit
    first_datetime = shipped.datetime
    first_panel = native.ChartPanel

    recorder = SignalRecorder()
    logs = LogRecorder()
    ticker = Ticker()
    logger = logging.getLogger(LOG_NAME)
    first_level = logger.level

    class FrozenDateTime:
        @staticmethod
        def now():
            return types.SimpleNamespace(isoformat=lambda: FIXED_STAMP)

    time.time = lambda: FIXED_NOW
    time.monotonic = ticker
    sc.emit = recorder
    shipped.datetime = FrozenDateTime
    native.ChartPanel = RecordingPanel
    logger.addHandler(logs)
    logger.setLevel(logging.DEBUG)
    RecordingPanel.made = []
    try:
        yield recorder, logs
    finally:
        time.time = first_time
        time.monotonic = first_monotonic
        sc.emit = first_emit
        shipped.datetime = first_datetime
        native.ChartPanel = first_panel
        logger.removeHandler(logs)
        logger.setLevel(first_level)


def qt_tab():
    """A live `TradeChartsTab`, with its fetcher replaced by a stand-in."""
    from src.gui.widgets.trade_charts_tab import TradeChartsTab

    app()
    tab = TradeChartsTab()
    tab._scroll_layout = RecordingLayout()
    return tab


def drive_old(spec):
    """Run one scenario's steps on the shipped tab and read its state back."""
    with held_still() as (signals, logs):
        tab = qt_tab()
        tab._fetcher = QtFetcher(spec.get("answers"))
        manager = (
            None
            if spec.get("bots") is None
            else QtManager(
                {one: QtBot(**readings) for one, readings in spec["bots"].items()}
            )
        )
        connectors = spec.get("connectors")
        refusal = None
        dropped: list = []
        known: list = []
        for index, step in enumerate(spec["steps"]):
            try:
                run_old_step(tab, step, manager, connectors)
            except Exception as exc:
                refusal = [index, step[0], type(exc).__name__]
                break
            finally:
                held = list(tab._chart_panels)
                dropped.extend(one for one in known if one not in held)
                known = held
        trace = read_old(tab, signals, logs, refusal, dropped)
    return trace


def run_old_step(tab, step, manager, connectors):
    """One step of a scenario, on the shipped tab."""
    import asyncio

    kind = step[0]
    if kind == "update":
        tab.update_charts(step[1], manager, connectors)
    elif kind == "tf":
        tab._on_tf_changed(step[1], step[2])
    elif kind == "fetch":
        asyncio.run(tab.fetch_chart_data(connectors))
    elif kind == "trade":
        tab.log_trade(dict(step[1]))
    elif kind == "nuclear":
        tab.push_synthetic_candles(
            step[1], step[2], [Lump(*one) for one in step[3]], step[4], step[5]
        )
    elif kind == "nuclear_dicts":
        tab.push_synthetic_candles(
            step[1],
            step[2],
            [
                dict(zip(("time", "open", "high", "low", "close", "volume"), one))
                for one in step[3]
            ],
            step[4],
            step[5],
        )
    else:
        raise AssertionError(f"no step named {kind}")


def read_old(tab, signals, logs, refusal, dropped):
    """Everything the shipped tab holds after a drive, as plain values."""
    layout = tab._scroll_layout
    order = [
        bot_id
        for slot in layout.slots
        if slot is not None
        for bot_id, info in tab._chart_panels.items()
        if info["panel"] is slot
    ]
    return {
        "accessible_name": tab.accessibleName(),
        "container": {
            "margins_px": [
                tab.layout().contentsMargins().left(),
                tab.layout().contentsMargins().top(),
                tab.layout().contentsMargins().right(),
                tab.layout().contentsMargins().bottom(),
            ],
            "spacing_px": tab.layout().spacing(),
        },
        "panel_order": order,
        "panel_count": len(tab._chart_panels),
        "panels": {
            bot_id: {
                "symbol": info["symbol"],
                "exchange_id": info["exchange_id"],
                "last_fetch": info["last_fetch"],
                "synthetic": info.get("synthetic", False),
                "panel": info["panel"].as_values(),
            }
            for bot_id, info in tab._chart_panels.items()
        },
        "dropped": list(dropped),
        "trade_log": [dict(one) for one in tab._trade_log],
        "logs": [list(one) for one in logs.info],
        "refusal_types": list(logs.refusals),
        "signals": [dict(one) for one in signals.records],
        "fetch_asked": [list(one) for one in tab._fetcher.asked],
        "refusal": refusal,
    }


def drive_new(spec):
    """Run one scenario's steps on the surface and read its state back."""
    manager = (
        None
        if spec.get("bots") is None
        else surface.ManagerSource(
            {
                one: surface.BotSource(**readings)
                for one, readings in spec["bots"].items()
            }
        )
    )
    model = surface.TradeChartsTabModel(
        manager=manager,
        fetcher=surface.FetchSource(spec.get("answers")),
        clock=FIXED_NOW,
        ticks=[TICK_BASE, TICK_BASE + TICK_STEP] * 64,
    )
    connectors = spec.get("connectors")
    refusal = None
    for index, step in enumerate(spec["steps"]):
        try:
            run_new_step(model, step, connectors)
        except Exception as exc:
            refusal = [index, step[0], type(exc).__name__]
            break
    return read_new(model, refusal)


def run_new_step(model, step, connectors):
    """One step of a scenario, on the surface."""
    import asyncio

    kind = step[0]
    if kind == "update":
        model.update_charts(step[1], exchange_connectors=connectors)
    elif kind == "tf":
        model.on_timeframe_changed(step[1], step[2])
    elif kind == "fetch":
        asyncio.run(model.fetch_chart_data(connectors))
    elif kind == "trade":
        model.log_trade(dict(step[1]), FIXED_STAMP)
    elif kind == "nuclear":
        model.push_synthetic_candles(
            step[1], step[2], [Lump(*one) for one in step[3]], step[4], step[5]
        )
    elif kind == "nuclear_dicts":
        model.push_synthetic_candles(
            step[1],
            step[2],
            [
                dict(zip(("time", "open", "high", "low", "close", "volume"), one))
                for one in step[3]
            ],
            step[4],
            step[5],
        )
    else:
        raise AssertionError(f"no step named {kind}")


FAILURE_MARKERS = (
    surface.UPDATE_MARKERS_FAILED,
    surface.UPDATE_TB_FAILED,
    surface.UPDATE_FIRE_FAILED,
    surface.UPDATE_FLOORS_FAILED,
)


def read_new(model, refusal):
    """Everything the surface holds after a drive, as plain values."""
    payload = surface.build_view_model(model)
    return {
        "accessible_name": payload["accessible_name"],
        "container": payload["container"],
        "panel_order": payload["panel_order"],
        "panel_count": payload["panel_count"],
        "panels": payload["panels"],
        "dropped": payload["dropped"],
        "trade_log": payload["trade_log"],
        "logs": [[repr(one) for one in line[1:]] for line in payload["logs"]],
        "refusal_types": [
            call[2] for call in model.calls if call[0] in FAILURE_MARKERS
        ],
        "signals": payload["signals"],
        "fetch_asked": payload["fetch"]["asked"],
        "refusal": refusal,
    }


# ---------------------------------------------------------------------
# The two sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", [spec["name"] for spec in SCENARIOS])
def test_the_two_sides_describe_the_same_tab(name):
    """The view model describes a different tab than the widget builds."""
    old = canonical(drive_old(BY_NAME[name]))
    new = canonical(drive_new(BY_NAME[name]))
    assert first_difference(old, new) == "", first_difference(old, new)
    assert digest(old) == digest(new), name


@pytest.mark.parametrize("name", [spec["name"] for spec in SCENARIOS])
def test_the_sample_hashes_are_reported(name):
    """A scenario reached no hash, so nothing was compared for it."""
    stamp = digest(canonical(drive_old(BY_NAME[name])))
    assert len(stamp) == 64
    assert stamp == digest(canonical(drive_old(BY_NAME[name]))), name


def test_the_comparison_reports_two_different_real_inputs():
    """The comparison passes whatever the surface holds.

    Two genuinely different real inputs, one through each side, in both
    directions. A comparison that cannot tell them apart reports nothing
    about the pairs that matched.
    """
    one = canonical(drive_old(BY_NAME["happy"]))
    other = canonical(drive_new(BY_NAME["fetch_returns_candles"]))
    assert digest(one) != digest(other)
    assert first_difference(one, other) != ""
    flipped_old = canonical(drive_old(BY_NAME["fetch_returns_candles"]))
    flipped_new = canonical(drive_new(BY_NAME["happy"]))
    assert digest(flipped_old) != digest(flipped_new)
    assert first_difference(flipped_old, flipped_new) != ""


def test_the_same_input_twice_reaches_one_hash():
    """A drive is not repeatable, so no hash of it means anything.

    Each drive below is its own run. The last pair is the control: the
    same side driven with a different input must reach another hash, or
    a repeatable drive would prove nothing.
    """
    first_new = digest(canonical(drive_new(BY_NAME["happy"])))
    again_new = digest(canonical(drive_new(BY_NAME["happy"])))
    assert first_new == again_new
    first_old = digest(canonical(drive_old(BY_NAME["happy"])))
    again_old = digest(canonical(drive_old(BY_NAME["happy"])))
    assert first_old == again_old
    other_new = digest(canonical(drive_new(BY_NAME["zero_price"])))
    other_old = digest(canonical(drive_old(BY_NAME["zero_price"])))
    assert other_new != first_new
    assert other_old != first_old


def test_a_whole_number_and_a_decimal_reach_different_hashes():
    """The hash folds 12 and 12.0 together, so a type change reads as none.

    A candle carrying a whole number reaches the chart as a whole
    number. Both sides are driven, so the difference is the product's
    and not the comparison's.
    """
    whole_spec = {
        "name": "whole",
        "bots": {},
        "answers": [([(12, 12, 12, 12, 12, 12)], "one")],
        "steps": [("update", [status()]), ("fetch",)],
    }
    decimal_spec = dict(
        whole_spec,
        name="decimal",
        answers=[([(12, 12.0, 12.0, 12.0, 12.0, 12.0)], "one")],
    )
    whole_old, whole_new = drive_old(whole_spec), drive_new(whole_spec)
    decimal_old, decimal_new = drive_old(decimal_spec), drive_new(decimal_spec)
    assert digest(canonical(whole_old)) == digest(canonical(whole_new))
    assert digest(canonical(decimal_old)) == digest(canonical(decimal_new))
    assert digest(canonical(whole_old)) != digest(canonical(decimal_old))
    assert first_difference(canonical(whole_old), canonical(decimal_old)) != ""
    assert whole_old["panels"]["b1"]["panel"]["candles"][0][1] == 12
    assert decimal_old["panels"]["b1"]["panel"]["candles"][0][1] == 12.0


def test_two_not_a_numbers_compare_equal_to_each_other():
    """The comparison reports a difference between two not-a-numbers.

    A plain comparison of two not-a-numbers is never equal, so a trace
    carrying one would fail against itself and every real difference
    would be hidden in the noise.
    """
    left = canonical({"v": float("nan")})
    right = canonical({"v": float("nan")})
    assert left == right
    assert first_difference(left, right) == ""
    assert first_difference(left, canonical({"v": float("inf")})) != ""


@pytest.mark.parametrize("name", REFUSING)
def test_a_refused_step_names_the_same_error_on_both_sides(name):
    """One side refused where the other carried on, or with another error."""
    old = drive_old(BY_NAME[name])
    new = drive_new(BY_NAME[name])
    assert old["refusal"] is not None, name
    assert old["refusal"] == new["refusal"], (old["refusal"], new["refusal"])
    assert isinstance(old["refusal"][0], int)
    assert old["refusal"][1] in ("update", "tf", "fetch", "trade", "nuclear")


def test_a_refusal_keeps_everything_recorded_before_it():
    """A refusal threw away the steps that had already run."""
    spec = {
        "name": "refuses_on_the_second_pass",
        "bots": {},
        "steps": [("update", [status()]), ("update", [status(price="12.7")])],
    }
    old = drive_old(spec)
    new = drive_new(spec)
    assert old["refusal"] == [1, "update", "TypeError"], old["refusal"]
    assert old["refusal"] == new["refusal"]
    assert old["panel_count"] == 1
    assert new["panel_count"] == 1
    assert len(old["signals"]) == 2
    assert len(new["signals"]) == 2
    assert first_difference(canonical(old), canonical(new)) == ""


def test_every_declared_outcome_is_reached_by_a_scenario():
    """An outcome the surface names is never taken, so nothing covers it."""
    seen = set()
    for spec in SCENARIOS:
        model_calls = surface_calls(spec)
        for call in model_calls:
            if call[0] == surface.FETCH_EMIT_REFRESHED:
                seen.add(call[4])
    assert seen == set(surface.OUTCOMES), sorted(set(surface.OUTCOMES) - seen)


def surface_calls(spec):
    """The branch markers one scenario's surface drive recorded."""
    manager = (
        None
        if spec.get("bots") is None
        else surface.ManagerSource(
            {
                one: surface.BotSource(**readings)
                for one, readings in spec["bots"].items()
            }
        )
    )
    model = surface.TradeChartsTabModel(
        manager=manager,
        fetcher=surface.FetchSource(spec.get("answers")),
        clock=FIXED_NOW,
        ticks=[TICK_BASE, TICK_BASE + TICK_STEP] * 64,
    )
    for step in spec["steps"]:
        try:
            run_new_step(model, step, spec.get("connectors"))
        except Exception:
            break
    return model.calls


NO_PUBLIC_ROUTE = {
    surface.UPDATE_MARKERS_FAILED: (
        "test_the_marker_guard_reports_a_trade_log_entry_that_is_not_a_record"
    )
}


def test_every_branch_marker_fires_across_the_scenarios():
    """A branch the surface declares is never taken by any scenario.

    One marker has no route through the tab's own entry points, because
    ``log_trade`` accepts only a record. It is named here with the check
    that drives it directly.
    """
    seen = set()
    for spec in SCENARIOS:
        seen.update(call[0] for call in surface_calls(spec))
    seen.update(
        call[0]
        for call in surface_calls(
            {
                "name": "refuses",
                "bots": {},
                "steps": [("update", [status()]), ("update", [status(price="12.7")])],
            }
        )
    )
    missing = set(surface.CALL_NAMES) - seen
    assert missing == set(NO_PUBLIC_ROUTE), sorted(missing ^ set(NO_PUBLIC_ROUTE))
    for covered in NO_PUBLIC_ROUTE.values():
        assert covered in globals() and callable(globals()[covered])


def test_the_marker_guard_reports_a_trade_log_entry_that_is_not_a_record():
    """A trade log entry that is not a record stopped the whole pass.

    Nothing the tab offers can put such an entry in the log, so the
    guard is reachable only by writing the list directly.
    """
    model = surface.TradeChartsTabModel()
    model.trade_log = [1]
    panel = surface.PanelSink("BTC/USD")
    model._feed_overlays("b1", "BTC/USD", surface.BotSource(), panel)
    failed = [call for call in model.calls if call[0] == surface.UPDATE_MARKERS_FAILED]
    assert failed == [[surface.UPDATE_MARKERS_FAILED, "b1", "AttributeError"]]
    assert panel.markers == []
    assert panel.tb_anchor is None
    assert panel.armed is not None


# ---------------------------------------------------------------------
# What went where
# ---------------------------------------------------------------------

SHIPPED_SOURCE = REPO_ROOT / "src" / "gui" / "widgets" / "trade_charts_tab.py"


def shipped_tree():
    return ast.parse(SHIPPED_SOURCE.read_text(encoding="utf-8"))


def count_shipped(tree):
    """Every item the shipped file holds, counted off the parsed tree."""
    emit_names = set()
    subscribe_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local = alias.asname or alias.name
                if alias.name == "emit" and "signal_contract" in node.module:
                    emit_names.add(local)
                if alias.name == "subscribe" and (
                    "event_bus" in node.module or "signal_contract" in node.module
                ):
                    subscribe_names.add(local)
    found = {
        "classes": 0,
        "methods": 0,
        "module_functions": 0,
        "connects": 0,
        "signals_declared": 0,
        "signal_emits": 0,
        "bus_emits": 0,
        "bus_subscribes": 0,
        "timers_built": 0,
        "timers_started": 0,
        "threads_built": 0,
        "threads_started": 0,
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            found["classes"] += 1
            for body in node.body:
                if isinstance(body, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found["methods"] += 1
                if isinstance(body, ast.Assign) and isinstance(body.value, ast.Call):
                    if ast.unparse(body.value.func).split(".")[-1] == "Signal":
                        found["signals_declared"] += 1
        elif isinstance(node, ast.Call):
            whole = ast.unparse(node.func)
            base = whole.split(".")[-1]
            if base == "connect":
                found["connects"] += 1
            if base == "emit":
                found["signal_emits"] += 1
            if whole in emit_names:
                found["bus_emits"] += 1
            if whole in subscribe_names:
                found["bus_subscribes"] += 1
            if base == "QTimer":
                found["timers_built"] += 1
            if base in ("QThread", "Thread"):
                found["threads_built"] += 1
            if base == "singleShot":
                found["timers_built"] += 1
                found["timers_started"] += 1
            if base in ("start", "timer_start") and "timer" in whole.lower():
                found["timers_started"] += 1
            if base in ("start", "run") and (
                "thread" in whole.lower() or "worker" in whole.lower()
            ):
                found["threads_started"] += 1
    found["module_functions"] = sum(
        1
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )
    return found


CONTROL_BODY = """
from PySide6.QtCore import QThread, QTimer, Signal
from src.core.signal_contract import emit as away
from src.core.event_bus import subscribe as elsewhere


class Extra:
    ping = Signal(str)

    async def waited(self):
        return None

    def acted(self):
        self.ping.emit("x")
        self.ping.connect(self.acted)
        one_timer = QTimer()
        one_timer.start()
        QTimer.singleShot(1, self.acted)
        worker_thread = QThread()
        worker_thread.start()
        away("a", actual=1, expected=1)
        elsewhere("topic", self.acted)


def alone():
    return None
"""


def test_the_shipped_file_holds_what_this_unit_says_it_holds():
    """The enumeration counts something other than what the file holds."""
    found = count_shipped(shipped_tree())
    assert found["classes"] == SHIPPED_CLASS_TOTAL
    assert found["methods"] == SHIPPED_METHOD_TOTAL
    assert found["module_functions"] == SHIPPED_FUNCTION_TOTAL
    assert found["connects"] == SHIPPED_CONNECT_TOTAL
    assert found["signals_declared"] == SHIPPED_SIGNAL_TOTAL
    assert found["signal_emits"] == SHIPPED_SIGNAL_EMIT_TOTAL
    assert found["bus_emits"] == SHIPPED_BUS_EMIT_TOTAL
    assert found["bus_subscribes"] == SHIPPED_BUS_SUBSCRIBE_TOTAL
    assert found["timers_built"] == SHIPPED_TIMER_BUILT_TOTAL
    assert found["timers_started"] == SHIPPED_TIMER_STARTED_TOTAL
    assert found["threads_built"] == SHIPPED_THREAD_BUILT_TOTAL
    assert found["threads_started"] == SHIPPED_THREAD_STARTED_TOTAL


def test_every_counter_reports_one_more_when_one_more_is_there():
    """A counter reads zero because it cannot see, not because none is there.

    The control adds exactly one of each item, including a bus emit and
    a bus subscribe reached through a renamed import.
    """
    plain = count_shipped(shipped_tree())
    raised = count_shipped(
        ast.parse(SHIPPED_SOURCE.read_text(encoding="utf-8") + CONTROL_BODY)
    )
    blind = [name for name in plain if raised[name] <= plain[name]]
    assert blind == [], blind
    assert raised["bus_emits"] == plain["bus_emits"] + 1
    assert raised["bus_subscribes"] == plain["bus_subscribes"] + 1


def test_the_one_connected_action_has_a_counterpart_on_the_surface():
    """The shipped tab connects an action the surface names no handler for."""
    assert len(surface.ACTIONS) == SHIPPED_CONNECT_TOTAL
    for handler in surface.ACTIONS.values():
        assert callable(getattr(surface.TradeChartsTabModel, handler))


def test_every_shipped_method_has_a_counterpart_on_the_surface():
    """A method of the shipped tab reached no method on the surface."""
    moved = {
        "__init__": "__init__",
        "update_charts": "update_charts",
        "_on_tf_changed": "on_timeframe_changed",
        "fetch_chart_data": "fetch_chart_data",
        "log_trade": "log_trade",
        "push_synthetic_candles": "push_synthetic_candles",
    }
    shipped_methods = set()
    for node in ast.walk(shipped_tree()):
        if isinstance(node, ast.ClassDef):
            shipped_methods.update(
                body.name
                for body in node.body
                if isinstance(body, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    assert shipped_methods == set(moved), shipped_methods ^ set(moved)
    assert len(moved) == SHIPPED_METHOD_TOTAL
    for here in moved.values():
        assert callable(getattr(surface.TradeChartsTabModel, here)), here


def test_the_counterpart_reader_reports_a_missing_counterpart():
    """The counterpart check passes for a method the surface does not hold."""
    assert not hasattr(surface.TradeChartsTabModel, "a_method_nobody_wrote")


def test_the_tab_builds_no_timer_and_starts_no_thread():
    """The tab holds a timer or a thread the surface does not describe."""
    found = count_shipped(shipped_tree())
    assert found["timers_built"] == 0
    assert found["timers_started"] == 0
    assert found["threads_built"] == 0
    assert found["threads_started"] == 0
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    raised = count_shipped(
        ast.parse(SHIPPED_SOURCE.read_text(encoding="utf-8") + CONTROL_BODY)
    )
    assert raised["timers_built"] > 0
    assert raised["threads_started"] > 0


def test_the_tab_subscribes_to_no_bus_topic():
    """The tab subscribes to a topic the surface does not describe."""
    found = count_shipped(shipped_tree())
    assert found["bus_subscribes"] == 0
    assert surface.BUS_TOPICS == ()
    raised = count_shipped(
        ast.parse(SHIPPED_SOURCE.read_text(encoding="utf-8") + CONTROL_BODY)
    )
    assert raised["bus_subscribes"] == 1


def test_the_five_signals_the_tab_emits_are_the_five_the_surface_names():
    """A signal the tab emits is missing from the surface's list."""
    emitted = set()
    for spec in SCENARIOS:
        emitted.update(one["name"] for one in drive_old(spec)["signals"])
    assert emitted == set(surface.SIGNAL_NAMES), sorted(
        set(surface.SIGNAL_NAMES) ^ emitted
    )
    assert len(surface.SIGNAL_NAMES) == SHIPPED_BUS_EMIT_TOTAL


def test_the_signal_recorder_sees_what_the_tab_emits():
    """The signal recorder is never reached, so its zero means nothing."""
    empty = drive_old(BY_NAME["empty_statuses"])
    assert [one["name"] for one in empty["signals"]] == [
        surface.MOUNTED_SIGNAL,
        surface.SYMBOLS_SIGNAL,
    ]
    fetched = drive_old(BY_NAME["fetch_returns_candles"])
    assert [one["name"] for one in fetched["signals"]] == [
        surface.MOUNTED_SIGNAL,
        surface.SYMBOLS_SIGNAL,
        surface.REFRESHED_SIGNAL,
        surface.FRESH_SIGNAL,
    ]
    rearmed = drive_old(BY_NAME["timeframe_changed_on_a_known_panel"])
    assert surface.REARMED_SIGNAL in [one["name"] for one in rearmed["signals"]]


def test_only_the_fetch_signal_carries_a_duration():
    """A signal that follows no bounded operation reports a made-up number."""
    for spec in SCENARIOS:
        for one in drive_new(spec)["signals"]:
            if one["name"] == surface.REFRESHED_SIGNAL:
                assert one["duration"] == pytest.approx(TICK_STEP), one
            else:
                assert one["duration"] is None, one


def test_the_duration_follows_the_gap_between_the_two_readings():
    """The duration reports a constant rather than measuring the fetch."""
    model = surface.TradeChartsTabModel(
        fetcher=surface.FetchSource([(CANDLE_ROWS, "one"), (ONE_ROW, "two")]),
        clock=FIXED_NOW,
        ticks=[0.0, 2.5],
    )
    model.update_charts([status()])
    import asyncio

    asyncio.run(model.fetch_chart_data())
    fetched = [one for one in model.signals if one.name == surface.REFRESHED_SIGNAL]
    assert fetched[0].duration == pytest.approx(2.5)


# ---------------------------------------------------------------------
# The comparison is complete
# ---------------------------------------------------------------------

PAYLOAD_PATHS = {
    "ACCESSIBLE_NAME": "accessible_name",
    "OUTER_MARGINS_PX": "container.margins_px",
    "OUTER_SPACING_PX": "container.spacing_px",
    "SCROLL_RESIZABLE": "scroll.widget_resizable",
    "SCROLL_HORIZONTAL_POLICY": "scroll.horizontal_policy",
    "SCROLL_HORIZONTAL_POLICY_VALUE": "scroll.horizontal_policy_value",
    "CONTENT_MARGINS_PX": "content.margins_px",
    "CONTENT_SPACING_PX": "content.spacing_px",
    "CONTENT_STRETCH_ADDED": "content.stretch_added",
    "STRETCH_SLOTS": "content.stretch_slots",
    "PANEL_TIMEFRAME": "panel_defaults.timeframe",
    "COMBO_TIMEFRAME": "panel_defaults.combo_timeframe",
    "PANEL_MINIMUM_HEIGHT_PX": "panel_defaults.minimum_height_px",
    "PANEL_MAXIMUM_HEIGHT_PX": "panel_defaults.maximum_height_px",
    "NUCLEAR_TIMEFRAME": "nuclear_defaults.timeframe",
    "NUCLEAR_MINIMUM_HEIGHT_PX": "nuclear_defaults.minimum_height_px",
    "NUCLEAR_MAXIMUM_HEIGHT_PX": "nuclear_defaults.maximum_height_px",
    "NUCLEAR_EXCHANGE_ID": "nuclear_defaults.exchange_id",
    "FETCH_THROTTLE_S": "fetch.throttle_s",
    "FETCH_LIMIT": "fetch.limit",
    "STALE_AFTER_S": "fetch.stale_after_s",
    "AGE_DECIMALS": "fetch.age_decimals",
    "NEVER_FETCHED": "fetch.never_fetched",
    "MISSING_LAST_FETCH": "fetch.missing_last_fetch",
    "ERROR_TEXT_LIMIT": "fetch.error_text_limit",
    "EXTRACTOR_MODE": "filters.extractor_mode",
    "WILDCARD": "filters.wildcard",
    "PRICE_LABEL_FORMAT": "formats.price_label",
    "NUCLEAR_LABEL_FORMAT": "formats.nuclear_label",
    "AWAITING_FORMAT": "formats.awaiting",
    "FLOOR_SMALL_FORMAT": "formats.floor_small",
    "FLOOR_LARGE_FORMAT": "formats.floor_large",
    "FOLLOW_LOG_FORMAT": "formats.follow_log",
    "FLOOR_FORMAT_SWITCH": "floor_format_switch",
    "EMPTY_SOURCE": "empty_source",
    "BOT_ID_LOG_LENGTH": "bot_id_log_length",
    "CANDLE_CLOSE_INDEX": "candle_close_index",
    "MODE_KEY": "keys.mode",
    "BOT_ID_KEY": "keys.bot_id",
    "SYMBOL_KEY": "keys.symbol",
    "STATE_KEY": "keys.state",
    "EXCHANGE_KEY": "keys.exchange",
    "STATS_KEY": "keys.stats",
    "PRICE_KEY": "keys.price",
    "PANEL_KEY": "keys.panel",
    "LAST_FETCH_KEY": "keys.last_fetch",
    "EXCHANGE_ID_KEY": "keys.exchange_id",
    "SYNTHETIC_KEY": "keys.synthetic",
    "TIMESTAMP_KEY": "keys.timestamp",
    "FLOOR_PRICE_KEY": "keys.floor_price",
    "FLOOR_UNITS_KEY": "keys.floor_units",
    "SCRUM_ARMED_KEY": "keys.scrum_armed",
    "FOLD_ARMED_KEY": "keys.fold_armed",
    "SCRUM_BLOCKERS_KEY": "keys.scrum_blockers",
    "FOLD_BLOCKERS_KEY": "keys.fold_blockers",
    "CANDLE_TIME_KEY": "keys.candle_time",
    "CANDLE_OPEN_KEY": "keys.candle_open",
    "CANDLE_HIGH_KEY": "keys.candle_high",
    "CANDLE_LOW_KEY": "keys.candle_low",
    "CANDLE_CLOSE_KEY": "keys.candle_close",
    "CANDLE_VOLUME_KEY": "keys.candle_volume",
    "ANCHOR_ATTRIBUTE": "attributes.anchor",
    "TARGET_ATTRIBUTE": "attributes.target",
    "CAP_ATTRIBUTE": "attributes.cap",
    "CONSUMED_ATTRIBUTE": "attributes.consumed",
    "HOLDINGS_ATTRIBUTE": "attributes.holdings",
    "QUOTE_RATE_ATTRIBUTE": "attributes.quote_rate",
    "GATE_STATE_ATTRIBUTE": "attributes.gate_state",
    "LOTS_ATTRIBUTE": "attributes.lots",
    "DEFAULT_MODE": "defaults.mode",
    "DEFAULT_BOT_ID": "defaults.bot_id",
    "DEFAULT_SYMBOL": "defaults.symbol",
    "DEFAULT_STATE": "defaults.state",
    "DEFAULT_EXCHANGE_ID": "defaults.exchange_id",
    "DEFAULT_PRICE": "defaults.price",
    "DEFAULT_ANCHOR_USD": "defaults.anchor_usd",
    "DEFAULT_CAP_USD": "defaults.cap_usd",
    "DEFAULT_CONSUMED_USD": "defaults.consumed_usd",
    "DEFAULT_HOLDINGS": "defaults.holdings",
    "DEFAULT_QUOTE_RATE": "defaults.quote_rate",
    "CYCLE_OPEN_FLOOR_USD": "defaults.cycle_open_floor_usd",
    "DEFAULT_FLOOR_PRICE": "defaults.floor_price",
    "DEFAULT_FLOOR_UNITS": "defaults.floor_units",
    "NO_FLOOR_UNITS": "defaults.no_floor_units",
    "DEFAULT_CANDLE_TIME": "defaults.candle_time",
    "DEFAULT_CANDLE_VOLUME": "defaults.candle_volume",
    "NO_LAST_PRICE": "defaults.last_price",
    "SIGNAL_EVERY_S": "signal_settings.every_s",
    "NO_THROTTLE": "signal_settings.no_throttle",
    "NO_DURATION": "signal_settings.no_duration",
    "NO_DRIFT": "signal_settings.no_drift",
    "NO_STALE": "signal_settings.no_stale",
    "REARM_EXPECTED": "signal_settings.rearm_expected",
    "ACTIONS": "actions",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "BUS_TOPICS": "bus_topics",
    "CALL_NAMES": "call_names",
    "SIGNAL_NAMES": "signal_names",
    "THROTTLED_SIGNALS": "throttled_signals",
    "OUTCOMES": "outcomes",
    "METHOD": "",
}

LIST_MEMBERS = {
    "MOUNTED_SIGNAL": "signal_names",
    "SYMBOLS_SIGNAL": "signal_names",
    "REARMED_SIGNAL": "signal_names",
    "REFRESHED_SIGNAL": "signal_names",
    "FRESH_SIGNAL": "signal_names",
    "OUTCOME_CANDLES": "outcomes",
    "OUTCOME_EMPTY": "outcomes",
    "OUTCOME_RAISED": "outcomes",
}

CALL_CONSTANTS = {
    name
    for name in dir(surface)
    if name.startswith(
        ("UPDATE_", "TF_", "FETCH_START", "FETCH_THROTTLED", "FETCH_WILDCARD")
    )
    or name
    in (
        "FETCH_CANDLES",
        "FETCH_EMPTY",
        "FETCH_RAISED",
        "FETCH_EMIT_REFRESHED",
        "FETCH_EMIT_FRESH",
        "LOG_TRADE",
        "NUCLEAR_PANEL_CREATED",
        "NUCLEAR_PANEL_KEPT",
        "NUCLEAR_CANDLES_SET",
    )
}

NOT_IN_THE_SNAPSHOT = {
    "ModelCall": "test_the_call_list_is_a_plain_list",
    "PANE_MODEL": "test_the_bridge_keeps_and_resets_the_tab_state",
}

STATE_ONLY_KEYS = {
    "panel_order",
    "panel_count",
    "panels",
    "dropped",
    "trade_log",
    "logs",
    "signals",
    "calls",
    "scroll",
    "content",
    "container",
    "fetch",
    "accessible_name",
    "formats",
    "keys",
    "attributes",
    "defaults",
    "signal_settings",
    "panel_defaults",
    "nuclear_defaults",
    "filters",
}


def at_path(payload, path):
    """The value one dotted path names inside the payload."""
    here = payload
    for step in path.split("."):
        here = here[step]
    return here


def surface_constants():
    """Every value the surface exports, by name."""
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

    A comparison reading some of the values passes whether the rest
    match or not. Every value is accounted for here: a snapshot path, a
    member of a list the snapshot holds, one of the branch markers, or
    one named with the check that covers it.
    """
    payload = surface.build_view_model(surface.TradeChartsTabModel())
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in CALL_CONSTANTS:
            assert value in payload["call_names"], name
        elif name in PAYLOAD_PATHS:
            path = PAYLOAD_PATHS[name]
            if not path:
                continue
            carried = at_path(payload, path)
            if isinstance(value, tuple):
                assert carried == list(value), name
            else:
                assert carried == value, name
        elif name in LIST_MEMBERS:
            assert value in payload[LIST_MEMBERS[name]], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered = NOT_IN_THE_SNAPSHOT[name]
            assert covered in globals() and callable(globals()[covered]), name
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.TradeChartsTabModel())
    answered = {path.split(".")[0] for path in PAYLOAD_PATHS.values() if path}
    answered |= set(LIST_MEMBERS.values())
    assert set(payload) == answered | STATE_ONLY_KEYS, sorted(
        set(payload) ^ (answered | STATE_ONLY_KEYS)
    )
    assert len(payload) == PAYLOAD_KEY_TOTAL


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing."""
    payload = surface.build_view_model(surface.TradeChartsTabModel())
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_PATHS
    assert invented not in LIST_MEMBERS
    assert invented not in CALL_CONSTANTS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in surface_constants()
    assert "PANEL_TIMEFRAME" in surface_constants()
    assert "FETCH_THROTTLE_S" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "TradeChartsTabModel" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "formats.invented")


def test_the_call_list_is_a_plain_list():
    """The branch-marker list is not the type the surface declares."""
    assert surface.ModelCall is list
    model = surface.TradeChartsTabModel()
    model.update_charts([])
    assert all(isinstance(one, list) for one in model.calls)


def module_names_off_the_file():
    """Every name the surface file binds at module level, read off the tree."""
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names.update(one.id for one in node.targets if isinstance(one, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    return names


def names_the_surface_imports():
    """Every name the surface file brings in from somewhere else."""
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    brought = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            brought.update((one.asname or one.name).split(".")[0] for one in node.names)
    return brought


def module_names_off_the_import():
    """Every name the imported surface module binds, minus what it imports."""
    return {
        name
        for name, value in vars(surface).items()
        if not name.startswith("__")
        and not isinstance(value, types.ModuleType)
        and name not in names_the_surface_imports()
    }


def test_the_file_and_the_imported_module_carry_the_same_names():
    """The surface grew a name on one side that the other does not carry."""
    off_file = module_names_off_the_file()
    off_import = module_names_off_the_import()
    assert off_file - off_import == set(), off_file - off_import
    assert off_import - off_file == set(), off_import - off_file
    assert "ModelCall" in off_file
    assert "ModelCall" in off_import


def test_the_growth_check_reports_a_name_on_one_side_only():
    """The growth check passes for a name only one side carries."""
    off_file = module_names_off_the_file()
    assert "A_NAME_NOBODY_WROTE" not in off_file
    grown = off_file | {"A_NAME_NOBODY_WROTE"}
    assert grown - module_names_off_the_import() == {"A_NAME_NOBODY_WROTE"}
    assert "PANEL_TIMEFRAME" in off_file
    assert "TradeChartsTabModel" in off_file


# ---------------------------------------------------------------------
# The surface carries its own values
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_value_moved_in_the_shipped_tab(monkeypatch):
    """The surface read its values off the tab it replaces.

    A surface that read the shipped tab would follow it, and the whole
    comparison above would be one side read twice.
    """
    from src.gui.widgets import trade_charts_tab as shipped

    first = shipped.logger
    swallowed: list = []
    before = surface.build_view_model(surface.TradeChartsTabModel())
    monkeypatch.setattr(shipped, "logger", logging.getLogger("moved.logger"))
    monkeypatch.setattr(
        shipped.TradeChartsTab,
        "log_trade",
        lambda self, trade: swallowed.append(trade),
        raising=True,
    )
    after = surface.build_view_model(surface.TradeChartsTabModel())
    assert after == before
    assert after["panel_defaults"]["minimum_height_px"] == 300
    assert after["fetch"]["throttle_s"] == 30
    assert swallowed == []
    monkeypatch.undo()
    assert shipped.logger is first


def test_the_surface_module_never_imports_the_shipped_tab():
    """The surface reaches the tab it replaces, so both sides move together."""
    tree = ast.parse(SURFACE_SOURCE.read_text(encoding="utf-8"))
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            reached.update(one.name for one in node.names)
        elif isinstance(node, ast.ImportFrom):
            reached.add(node.module or "")
    assert not any("trade_charts_tab" in one for one in reached), reached
    assert not any("PySide6" in one for one in reached), reached
    assert "time" in reached


def test_the_shipped_tab_writes_to_no_shared_table():
    """The tab changed something every later test would inherit."""
    from src.gui.widgets import trade_charts_tab as shipped

    before = sorted(vars(shipped))
    drive_old(BY_NAME["happy"])
    drive_old(BY_NAME["fetch_returns_candles"])
    assert sorted(vars(shipped)) == before


def test_every_process_wide_seam_is_put_back_after_a_refusal():
    """A seam a drive swapped outlived the drive that swapped it."""
    from src.gui.widgets import trade_charts_tab as shipped

    first = (time.time, time.monotonic, sc.emit, shipped.datetime)
    inside = {}
    with held_still():
        inside["time"] = time.time
        inside["monotonic"] = time.monotonic
        inside["emit"] = sc.emit
        assert inside["time"]() == FIXED_NOW
        assert inside["emit"] is not first[2]
    assert (time.time, time.monotonic, sc.emit, shipped.datetime) == first
    drive_old(BY_NAME["price_is_text"])
    assert (time.time, time.monotonic, sc.emit, shipped.datetime) == first
    assert time.time() != FIXED_NOW


def test_the_panel_class_is_put_back_after_a_drive():
    """The recording panel outlived its drive and reached other tests."""
    import src.gui.native_chart as native

    first = native.ChartPanel
    drive_old(BY_NAME["happy"])
    assert native.ChartPanel is first
    assert first.__name__ == "ChartPanel"


# ---------------------------------------------------------------------
# The numbers the tab computes
# ---------------------------------------------------------------------


def test_the_ceiling_takes_the_spent_cap_off_the_live_target():
    """The ceiling line counts growth already applied twice."""
    lines = surface.target_balance_lines(
        {
            "anchor_usd": 50.0,
            "target_usd": 55.4148,
            "consumed_usd": 0.5,
            "cap_usd": 0.549148,
            "holdings": 1.0,
            "quote_rate": 1.0,
        }
    )
    assert lines[0] == pytest.approx(50.0)
    assert lines[1] == pytest.approx(55.463948)


def test_the_cycle_open_target_never_goes_below_zero():
    """A consumption larger than the target drew a negative ceiling."""
    lines = surface.target_balance_lines(
        {
            "anchor_usd": 10.0,
            "target_usd": 1.0,
            "consumed_usd": 9.0,
            "cap_usd": 2.0,
            "holdings": 1.0,
            "quote_rate": 1.0,
        }
    )
    assert lines[1] == pytest.approx(2.0)


@pytest.mark.parametrize(
    "readings",
    [
        {"anchor_usd": 0.0, "holdings": 1.0, "quote_rate": 1.0},
        {"anchor_usd": 1.0, "holdings": 0.0, "quote_rate": 1.0},
        {"anchor_usd": 1.0, "holdings": 1.0, "quote_rate": 0.0},
        {"anchor_usd": -1.0, "holdings": 1.0, "quote_rate": 1.0},
        {"anchor_usd": float("nan"), "holdings": 1.0, "quote_rate": 1.0},
    ],
)
def test_no_projection_leaves_both_overlay_lines_blank(readings):
    """A line was drawn where the price axis has no place to put it."""
    full = dict({"target_usd": 1.0, "consumed_usd": 0.0, "cap_usd": 0.0}, **readings)
    assert surface.target_balance_lines(full) == [None, None]


@pytest.mark.parametrize(
    "price,expected",
    [
        (0.5, "$0.5000"),
        (0.9999, "$0.9999"),
        (1, "$1.00"),
        (1.0, "$1.00"),
        (12.345, "$12.35"),
        (1e-9, "$0.0000"),
    ],
)
def test_the_floor_label_switches_at_one_dollar(price, expected):
    """A floor line reads with the wrong number of places."""
    assert surface.floor_label(price) == expected


def test_lots_at_one_price_draw_one_line():
    """Two lots at one price stacked two labels on one level."""
    floors = surface.tranche_floors(FLOOR_LOTS)
    assert floors == [[0.5, "$0.5000"], [12.0, "$12.00"]]


def test_a_lot_priced_at_zero_anchors_no_line():
    """A lot with no entry price drew a line at the bottom of the chart."""
    assert surface.tranche_floors([{"initial_buy_price": 0.0, "units": 5.0}]) == []
    assert surface.tranche_floors([{"initial_buy_price": -2.0, "units": 5.0}]) == []


def test_the_price_label_puts_the_state_in_capitals():
    """The header shows the state as stored rather than in capitals."""
    assert surface.price_label("BTC/USD", 100.0, "idle") == (
        "BTC/USD  •  $100.00000000  •  IDLE"
    )


def test_the_nuclear_label_shows_four_places():
    """A Nuclear header shows a different number of places than a live one."""
    assert surface.nuclear_label("DOGE/USD", 0.125, "melt") == (
        "DOGE/USD  •  $0.1250  •  ⚡melt"
    )


def test_a_stored_true_price_prints_as_one_dollar():
    """A stored true reached the header as a real-looking figure."""
    assert surface.price_label("BTC/USD", True, "idle").startswith(
        "BTC/USD  •  $1.00000000"
    )


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------

PICTURE_CASES = ("happy", "fetch_returns_candles", "nuclear_from_objects")
CONTROL_RULE = "QWidget { background: #3a1414; }"


def payload_for(name):
    """The surface's view model for one case, sealed as it comes off."""
    spec = BY_NAME[name]
    manager = (
        None
        if spec.get("bots") is None
        else surface.ManagerSource(
            {
                one: surface.BotSource(**readings)
                for one, readings in spec["bots"].items()
            }
        )
    )
    model = surface.TradeChartsTabModel(
        manager=manager,
        fetcher=surface.FetchSource(spec.get("answers")),
        clock=FIXED_NOW,
        ticks=[TICK_BASE, TICK_BASE + TICK_STEP] * 64,
    )
    for step in spec["steps"]:
        run_new_step(model, step, spec.get("connectors"))
    return sealed(surface.build_view_model(model))


def old_picture_tab(name):
    """The shipped tab, driven for one case, with its real chart panels."""
    from src.gui.widgets.trade_charts_tab import TradeChartsTab

    app()
    spec = BY_NAME[name]
    tab = TradeChartsTab()
    tab._fetcher = QtFetcher(spec.get("answers"))
    manager = (
        None
        if spec.get("bots") is None
        else QtManager(
            {one: QtBot(**readings) for one, readings in spec["bots"].items()}
        )
    )
    first_time = time.time
    time.time = lambda: FIXED_NOW
    try:
        for step in spec["steps"]:
            run_old_step(tab, step, manager, spec.get("connectors"))
    finally:
        time.time = first_time
    return tab


def new_picture_tab(payload):
    """A tab built only from the surface's view model, with real chart panels."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

    from src.gui.native_chart import Candle, ChartPanel

    payload = unaltered(payload)
    app()
    host = QWidget()
    host.setAccessibleName(payload["accessible_name"])
    outer = QVBoxLayout(host)
    outer.setContentsMargins(*payload["container"]["margins_px"])
    outer.setSpacing(payload["container"]["spacing_px"])

    scroll = QScrollArea()
    scroll.setWidgetResizable(payload["scroll"]["widget_resizable"])
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    content = QWidget()
    column = QVBoxLayout(content)
    column.setSpacing(payload["content"]["spacing_px"])
    column.setContentsMargins(*payload["content"]["margins_px"])
    column.addStretch()

    for bot_id in payload["panel_order"]:
        held = payload["panels"][bot_id]["panel"]
        panel = ChartPanel(held["built_with"])
        panel.chart.set_timeframe(held["chart_timeframe"])
        if held["minimum_height_px"] is not None:
            panel.setMinimumHeight(held["minimum_height_px"])
        if held["maximum_height_px"] is not None:
            panel.setMaximumHeight(held["maximum_height_px"])
        if held["candles"]:
            panel.chart.set_candles([Candle(*row) for row in held["candles"]])
        if held["source"]:
            panel.set_source(held["source"])
        if held["error_text"]:
            panel.chart.set_error(held["error_text"])
        if held["markers"]:
            panel.chart.set_trade_history_markers(held["markers"])
        if held["floors"]:
            panel.chart.set_tranche_floors([tuple(one) for one in held["floors"]])
        panel.chart.set_target_balance_lines(held["tb_anchor"], held["tb_ceiling"])
        if held["armed"] is not None:
            panel.chart.set_fire_armed_state(
                held["armed"]["scrum_armed"],
                held["armed"]["fold_armed"],
                held["armed"]["scrum_blockers"],
                held["armed"]["fold_blockers"],
            )
        panel.chart._symbol = held["label"]
        column.insertWidget(column.count() - 1, panel)

    scroll.setWidget(content)
    outer.addWidget(scroll)
    return host


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_carry_one_skin(name):
    """The surface's tab paints a different skin than the widget it replaces."""
    app()
    assert_same_skin(
        build_old_side=lambda: old_picture_tab(name),
        build_new_side=lambda: new_picture_tab(payload_for(name)),
        size=PIXEL_SIZE,
        control_rule=CONTROL_RULE,
        note=name,
    )


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_painted_tab_shows_more_than_one_colour(name):
    """A render paints one colour, so no comparison of it can report."""
    from tests.qt_pixel import render_widget

    app()
    old_colours = assert_picture_can_report(
        render_widget(old_picture_tab(name), PIXEL_SIZE), note=f"old side, {name}"
    )
    new_colours = assert_picture_can_report(
        render_widget(new_picture_tab(payload_for(name)), PIXEL_SIZE),
        note=f"new side, {name}",
    )
    assert old_colours == new_colours, (name, old_colours, new_colours)
    assert old_colours > 1


def test_the_picture_comparison_reports_two_different_real_inputs():
    """The picture comparison passes whatever the surface paints."""
    from tests.qt_pixel import render_widget

    app()
    one = render_widget(old_picture_tab("happy"), PIXEL_SIZE)
    other = render_widget(
        new_picture_tab(payload_for("fetch_returns_candles")), PIXEL_SIZE
    )
    assert_picture_can_report(one, note="old side, happy")
    assert_picture_can_report(other, note="new side, candles")
    assert_pictures_differ(old_side=one, new_side=other, note="two real inputs")


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, so the picture measures the test."""
    payload = payload_for("happy")
    payload["accessible_name"] = "moved"
    with pytest.raises(AssertionError):
        new_picture_tab(payload)
    with pytest.raises(AssertionError):
        new_picture_tab({"accessible_name": "never sealed"})


def test_the_colour_counter_reports_a_flat_render():
    """The colour counter cannot see a flat window, so its answer is empty."""
    from PySide6.QtGui import QImage

    app()
    flat = QImage(8, 8, QImage.Format_ARGB32)
    flat.fill(0xFF203040)
    assert colour_count(flat) == 1
    with pytest.raises(AssertionError):
        assert_picture_can_report(flat, note="a flat control")


# ---------------------------------------------------------------------
# The world this run touches
# ---------------------------------------------------------------------


LOOPBACK = ("127.0.0.1", "::1", "localhost")


def address_of(args):
    """The host one connection attempt names, or an empty name."""
    for one in args:
        if isinstance(one, tuple) and one and isinstance(one[0], str):
            return one[0]
    return ""


def test_this_run_opens_no_connection_off_this_machine(monkeypatch):
    """A drive reached a host off this machine.

    The counter watches this process only. A child process opening a
    connection of its own would not be seen here. Loopback is allowed
    and counted: the event loop this run drives the fetch on builds a
    local socket pair to wake itself, which is the runner and not the
    product.
    """
    reached = []

    def watch(name, real):
        def seen(*args, **named):
            reached.append([name, address_of(args)])
            if address_of(args) not in LOOPBACK:
                raise AssertionError(f"this run tried to reach {address_of(args)}")
            return real(*args, **named)

        return seen

    monkeypatch.setattr(
        socket,
        "create_connection",
        watch("create_connection", socket.create_connection),
    )
    monkeypatch.setattr(
        socket.socket, "connect", watch("connect", socket.socket.connect)
    )
    monkeypatch.setattr(
        socket.socket, "connect_ex", watch("connect_ex", socket.socket.connect_ex)
    )
    for name in ("happy", "fetch_returns_candles", "nuclear_from_objects"):
        assert digest(canonical(drive_old(BY_NAME[name]))) == digest(
            canonical(drive_new(BY_NAME[name]))
        )
    off_machine = [one for one in reached if one[1] not in LOOPBACK]
    assert off_machine == [], off_machine
    with pytest.raises(AssertionError):
        socket.socket().connect(("example.invalid", 80))
    assert reached[-1] == ["connect", "example.invalid"]


def test_the_surface_reads_no_clock_when_it_is_handed_the_time():
    """The surface read the wall clock, so its answer moves between runs."""

    def refuse():
        raise AssertionError("this drive read the clock")

    first_time, first_monotonic = time.time, time.monotonic
    time.time = refuse
    time.monotonic = refuse
    try:
        answered = drive_new(BY_NAME["fetch_returns_candles"])
    finally:
        time.time, time.monotonic = first_time, first_monotonic
    assert answered["panel_count"] == 1
    with pytest.raises(AssertionError):
        refuse()


def test_the_surface_reads_the_clock_when_it_is_handed_none():
    """The surface never reads a clock, so the guard above proves nothing."""
    read = []
    first_time = time.time
    time.time = lambda: read.append(1) or FIXED_NOW
    try:
        model = surface.TradeChartsTabModel()
        import asyncio

        asyncio.run(model.fetch_chart_data())
    finally:
        time.time = first_time
    assert read == [1]


HOME_PROBE = """
import json, os, sys
from pathlib import Path
sys.path.insert(0, %(repo)r)
home = Path(os.environ["ACERVATOR_TEST_HOME"])
before = sorted(str(p) for p in home.rglob("*") if p.is_file())
from src.gui.main_tabs import trade_charts_tab_surface as surface
model = surface.TradeChartsTabModel(
    manager=surface.ManagerSource({"b1": surface.BotSource(
        _anchor_target_balance=50.0, _target_balance=63.53,
        cycle_growth_cap_usd=0.549148, _fold_cycle_cap_consumed=0.5,
        _current_holdings=4.0, _quote_to_usd=1.0,
        _main_lots=[{"initial_buy_price": 0.5, "units": 2.0}])}),
    fetcher=surface.FetchSource([([[1, 1.0, 2.0, 0.5, 1.5, 10.0]], "Coinbase")]),
    clock=1700000000.0, ticks=[0.0, 0.25] * 8)
answer = surface.build_view_model(
    model,
    statuses=[{"bot_id": "b1", "symbol": "BTC/USD", "state": "idle",
               "exchange": "coinbase", "stats": {"current_price": 100.0}}],
    fetch_now=True,
)
%(extra)s
after = sorted(str(p) for p in home.rglob("*") if p.is_file())
print(json.dumps({"before": len(before), "after": len(after),
                  "panels": answer["panel_count"],
                  "signals": len(answer["signals"])}))
"""


def run_home_probe(extra):
    """Drive the surface in a fresh process under a throwaway home."""
    home = Path(tempfile.mkdtemp(prefix="acervator-throwaway-home-"))
    environment = dict(os.environ)
    environment["ACERVATOR_TEST_HOME"] = str(home)
    finished = subprocess.run(
        [sys.executable, "-"],
        input=(HOME_PROBE % {"repo": str(REPO_ROOT), "extra": extra}).encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        env=environment,
        timeout=120,
        check=False,
    )
    assert finished.returncode == 0, finished.stderr.decode()
    return json.loads(finished.stdout.decode().strip().splitlines()[-1]), home


def test_a_whole_drive_of_the_surface_creates_no_file():
    """The surface wrote a file, so a view model reached the disk."""
    answered, home = run_home_probe("")
    assert answered["before"] == 0
    assert answered["after"] == 0, answered
    assert answered["panels"] == 1
    assert answered["signals"] == 4
    assert list(home.rglob("*")) == []


def test_the_file_counter_reports_a_file_that_was_created():
    """The file counter cannot see a file, so its zero means nothing."""
    answered, home = run_home_probe('(home / "one.txt").write_bytes(b"1")')
    assert answered["before"] == 0
    assert answered["after"] == 1, answered
    assert [p.name for p in home.rglob("*")] == ["one.txt"]


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


@pytest.fixture
def fresh_pane_model():
    """Put the tab state the bridge keeps back exactly as it was found."""
    first = surface.PANE_MODEL
    surface.PANE_MODEL = surface.TradeChartsTabModel()
    yield
    surface.PANE_MODEL = first


def bridge_answer(params, request_id=1):
    from src.core import desktop_bridge

    return desktop_bridge.handle_line(
        json.dumps({"id": request_id, "method": surface.METHOD, "params": params}),
        desktop_bridge.build_registry(),
    )


BRIDGE_STATUSES = [
    {
        "bot_id": "b1",
        "symbol": "BTC/USD",
        "state": "scrumming",
        "exchange": "coinbase",
        "stats": {"current_price": 64000.5},
    }
]
BRIDGE_BOTS = {
    "b1": {
        "_anchor_target_balance": 50.0,
        "_target_balance": 55.4148,
        "cycle_growth_cap_usd": 0.549148,
        "_fold_cycle_cap_consumed": 0.5,
        "_current_holdings": 1.0,
        "_quote_to_usd": 1.0,
        "_main_lots": [{"initial_buy_price": 0.5, "units": 2.0}],
    }
}


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_registers_the_asset_charts_method():
    """The renderer cannot reach the Asset Charts tab over the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "trade_charts_tab.state"
    answer = bridge_answer({"reset": True})
    assert answer["ok"] is True
    assert answer["result"]["panel_count"] == 0
    assert answer["result"]["fetch"]["throttle_s"] == 30


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_keeps_and_resets_the_tab_state():
    """The tab state the bridge keeps was never kept, or never cleared."""
    filled = bridge_answer(
        {
            "reset": True,
            "bots": BRIDGE_BOTS,
            "now": FIXED_NOW,
            "statuses": BRIDGE_STATUSES,
        }
    )["result"]
    assert filled["panel_count"] == 1
    assert filled["panels"]["b1"]["panel"]["tb_anchor"] == pytest.approx(50.0)
    kept = bridge_answer({})["result"]
    assert kept["panel_count"] == 1
    cleared = bridge_answer({"reset": True})["result"]
    assert cleared["panel_count"] == 0
    assert cleared["calls"] == []


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_runs_a_fetch_pass():
    """A fetch over the bridge reached no panel at all."""
    answer = bridge_answer(
        {
            "reset": True,
            "now": FIXED_NOW,
            "ticks": [0.0, 0.25],
            "answers": [[[[1, 1.0, 2.0, 0.5, 1.5, 10.0]], "Coinbase"]],
            "statuses": BRIDGE_STATUSES,
            "fetch": True,
        }
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["panels"]["b1"]["panel"]["candle_count"] == 1
    assert result["panels"]["b1"]["panel"]["source"] == "Coinbase"
    assert result["signals"][-2]["name"] == surface.REFRESHED_SIGNAL
    assert result["signals"][-2]["duration"] == pytest.approx(0.25)


@pytest.mark.usefixtures("fresh_pane_model")
def test_the_bridge_answer_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    answer = bridge_answer(
        {"reset": True, "now": FIXED_NOW, "statuses": BRIDGE_STATUSES}
    )
    encoded = json.loads(json.dumps(answer))
    assert encoded["ok"] is True
    assert encoded["result"]["panel_count"] == 1
    assert encoded["result"]["panels"]["b1"]["panel"]["label"].startswith("BTC/USD")


QT_PROBE = """
import asyncio, builtins, json, sys
import time as _t
from src.core import desktop_bridge

registry = desktop_bridge.build_registry()


def request(fetch):
    return json.dumps({"id": 1, "method": "trade_charts_tab.state", "params": {
        "reset": True, "now": 1700000000.0, "ticks": [0.0, 0.25],
        "answers": [[[[1, 1.0, 2.0, 0.5, 1.5, 10.0]], "Coinbase"]],
        "statuses": [{"bot_id": "b1", "symbol": "BTC/USD", "state": "idle",
                      "exchange": "coinbase", "stats": {"current_price": 100.0}}],
        "fetch": fetch}})


async def nothing():
    return None


opened = []
reads = []
first_open, first_time, first_mono = builtins.open, _t.time, _t.monotonic
builtins.open = lambda *a, **k: (opened.append(a[:1]), first_open(*a, **k))[1]
_t.time = lambda: (reads.append("time"), 0.0)[1]
_t.monotonic = lambda: (reads.append("mono"), 0.0)[1]

quiet = desktop_bridge.handle_line(request(False), registry)
without_fetch = len(reads)
reads.clear()
asyncio.run(nothing())
loop_only = len(reads)
reads.clear()
frame = desktop_bridge.handle_line(request(True), registry)
with_fetch = len(reads)

_t.time, _t.monotonic, builtins.open = first_time, first_mono, first_open
print(json.dumps({"frame": frame, "quiet": quiet, "qt": "PySide6" in sys.modules,
                  "without_fetch": without_fetch, "loop_only": loop_only,
                  "with_fetch": with_fetch, "opens": len(opened)}))
"""


def run_probe(prelude):
    """Answer one bridge request in a fresh process and report what it touched."""
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
    """Reaching the Asset Charts tab pulled Qt into the backend.

    A request that runs no fetch reads no clock and opens no file. A
    request that runs one reads the clock exactly as many times as an
    empty event loop does, so the surface adds none of its own.
    """
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["without_fetch"] == 0, answered
    assert answered["with_fetch"] == answered["loop_only"], answered
    assert answered["loop_only"] > 0, answered
    assert answered["opens"] == 0, answered
    assert answered["quiet"]["ok"] is True
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["panel_count"] == 1
    assert result["panels"]["b1"]["panel"]["candles"] == [[1, 1.0, 2.0, 0.5, 1.5, 10.0]]
    assert result["panels"]["b1"]["panel"]["label"] == (
        "BTC/USD  •  $100.00000000  •  IDLE"
    )


def test_the_qt_probe_reports_qt_when_the_process_loaded_it():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True
    assert loaded["frame"]["result"]["panel_count"] == 1


def test_the_clock_and_open_counters_in_the_probe_can_report():
    """The probe's counters cannot see a read or an open, so their zeros lie."""
    answered = run_probe("")
    assert answered["without_fetch"] == 0
    seeded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import time as _t, builtins, json;"
            "reads = []; opened = [];"
            "first = _t.monotonic; first_open = builtins.open;"
            "_t.monotonic = lambda: (reads.append('mono'), 0.0)[1];"
            "builtins.open = lambda *a, **k: (opened.append(a[:1]), first_open(*a, **k))[1];"
            "_t.monotonic();"
            "builtins.open('pyproject.toml').close();"
            "_t.monotonic = first; builtins.open = first_open;"
            "print(json.dumps({'clock_reads': len(reads), 'opens': len(opened)}))",
        ],
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=120,
        check=False,
    )
    assert seeded.returncode == 0, seeded.stderr.decode()
    planted = json.loads(seeded.stdout.decode().splitlines()[-1])
    assert planted["clock_reads"] == 1
    assert planted["opens"] == 1


def test_nothing_runs_at_import_time_that_touches_the_world():
    """Importing the surface read a clock or opened a file."""
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            "import time as _t, builtins, json, sys;"
            "reads = []; opened = [];"
            "first_mono = _t.monotonic; first_time = _t.time; first_open = builtins.open;"
            "_t.monotonic = lambda: (reads.append('m'), 0.0)[1];"
            "_t.time = lambda: (reads.append('t'), 0.0)[1];"
            "import importlib;"
            "importlib.import_module('src.gui.main_tabs.trade_charts_tab_surface');"
            "builtins.open = lambda *a, **k: (opened.append(a[:1]), first_open(*a, **k))[1];"
            "_t.monotonic = first_mono; _t.time = first_time; builtins.open = first_open;"
            "print(json.dumps({'reads': len(reads), 'qt': 'PySide6' in sys.modules}))",
        ],
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    answered = json.loads(done.stdout.decode().splitlines()[-1])
    assert answered["reads"] == 0, answered
    assert answered["qt"] is False
