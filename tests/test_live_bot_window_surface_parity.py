"""The shipped Lite Live Bot window and the Qt-free surface, side by side.

A failure means the view model carries a different button, a different
heading, a different picker, a different pane, a different line, a
different warning, a different recorded step or a different refusal
than ``LiteLiveBotWindow``.

No test here reads or writes the operator's runtime tree, opens a
socket or reaches an exchange. Every key, secret, symbol, amount and
price below is invented.
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import live_bot_window as shipped
from src.gui.main_tabs import live_bot_window_surface as surface
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

WINDOW_PATH = REPO_ROOT / "src/gui/live_bot_window.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/live_bot_window_surface.py"
WIRING_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_CONTROL_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_CONTROL_PATH = REPO_ROOT / "src/gui/history_tab.py"
BUS_CONTROL_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
ELEMENT_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/dashboard_stat_card.py"
NESTED_CLASS_CONTROL_PATH = REPO_ROOT / "src/gui/stock_main_window.py"

PIXEL_SIZE = (900, 420)

# Counts measured off the file by the same counter that is pointed at a
# neighbour which really has one.
WINDOW_WIRING_CONNECTS = 6
WINDOW_VENUE_CONNECTS = 1
WINDOW_SIGNAL_BUILDS = 3
WINDOW_TIMER_BUILDS = 0
WINDOW_BUS_SITES = 4
WINDOW_ELEMENT_BUILDS = 23
CONTROL_WIRING_CONNECTS = 1
CONTROL_SIGNAL_BUILDS = 3
CONTROL_TIMER_BUILDS = 1
CONTROL_BUS_SITES = 2
CONTROL_ELEMENT_BUILDS = 3

# Invented values. No key, secret, symbol or amount below is the operator's.
API_KEY = "invented-key-0001"
API_SIGNATURE = "invented-signature-0001"
UNICODE_LINE = "Δ fold →⚡"
MARKUP_LINE = "<b>BUY </b> 1"
APOSTROPHE_LINE = "Ekthelius" + chr(39) + "s sell "
NEWLINE_LINE = "two\nlines"
LONG_LINE = "x" * 200
UNICODE_SYMBOL = "Δ/USD"

WIDGETS_HELD: list = []
BOXES_HELD: list = []


# ---------------------------------------------------------------------
# The shipped window reaches the process-wide event bus and the modal
# warning box. Every drive is given its own of each.
# ---------------------------------------------------------------------


class RecordingBus:
    """One event bus that records what a window took and gave back."""

    def __init__(self) -> None:
        self.topics: list = []
        self.handlers: dict = {}
        self.dropped: list = []

    def subscribe(self, topic, callback):
        """Take one topic and hand back the way off it."""
        self.topics.append(topic)
        self.handlers.setdefault(topic, []).append(callback)

        def unsubscribe():
            self.dropped.append(topic)

        return unsubscribe


class RecordingWarnings:
    """The modal warning box, recording what it was asked to show."""

    def __init__(self) -> None:
        self.shown: list = []

    def warning(self, _parent, title, text):
        """Record one warning instead of putting it in front of a person."""
        self.shown.append([title, text])

    def surface_warning(self, title, text):
        """The same recorder, called the way the surface calls it."""
        self.shown.append([title, text])


@pytest.fixture(autouse=True)
def quiet_modals(monkeypatch):
    """Replace the modal warning box for every test in this file.

    ``QMessageBox.warning`` blocks on a real answer. Nothing here may
    block, so the class the window reaches for is replaced for every
    test and the replacement is put back afterwards.
    """
    monkeypatch.setattr(shipped, "QMessageBox", RecordingWarnings())
    yield


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


def destroy(widget):
    """Destroy one top-level widget now, before the next one is built.

    A `LiteLiveBotWindow` does not die from a dropped reference. The
    lambdas `_wire_signals` connects capture the window, Qt owns the
    connection, and Python's collector cannot see that side. Measured on
    the offscreen driver: reference dropped, and close plus dropped,
    both leave the window in `QApplication.topLevelWidgets()`. The
    delivered `DeferredDelete` is what destroys it, so a test driving
    several windows in turn calls this between them and holds one alive
    at a time.
    """
    from PySide6.QtCore import QCoreApplication, QEvent

    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)


def module_values(module):
    """Every module-level value a window could change, read as text."""
    return {
        name: str(value)
        for name, value in vars(module).items()
        if not name.startswith("__") and not callable(value)
    }


def holding_group_boxes(monkeypatch):
    """Keep every group box the next window builds alive.

    The shipped window builds its configuration grid inside a group box
    it never adds to anything, so the box and every control on it is
    collected the moment the window is built. Holding the box changes no
    call the window makes; it only keeps the controls readable.
    """
    from PySide6.QtWidgets import QGroupBox

    held: list = []

    def make_group_box(*args, **kwargs):
        box = QGroupBox(*args, **kwargs)
        held.append(box)
        BOXES_HELD.append(box)
        return box

    monkeypatch.setattr(shipped, "QGroupBox", make_group_box)
    return held


class RecordingThreads:
    """The worker thread, recording what it was handed instead of running."""

    def __init__(self) -> None:
        self.started: list = []
        self.owner = self

    def make_thread(self, target=None, args=(), name=None, daemon=None):
        """The shipped call shape: a thread named and handed its work."""
        record = {"args": list(args), "name": name, "daemon": daemon}
        self.started.append(record)
        return _RecordedThread(record, target)

    def surface_thread(self, target, args, name, daemon):
        """The same recorder, called the way the surface calls it."""
        record = {"args": list(args), "name": name, "daemon": daemon}
        self.started.append(record)
        return _RecordedThread(record, target)


RecordingThreads.Thread = RecordingThreads.make_thread


class _RecordedThread:
    """One worker that records it was started rather than starting."""

    def __init__(self, record, target) -> None:
        self.record = record
        self.target = target

    def start(self) -> None:
        """Record the start the shipped window asks for."""
        self.record["started"] = True


class RunningLoop:
    """The bot's own loop, as the STOP button reads it."""

    def __init__(self, running: bool = True) -> None:
        self.running = running

    def is_running(self) -> bool:
        """Whether the worker's loop is still turning."""
        return self.running


class StopWaiter:
    """The wait the STOP button puts on the bot's own stop."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.waited: list = []

    def __call__(self, bot, timeout_s):
        self.waited.append(timeout_s)
        bot.stop_called += 1
        if self.fail:
            raise RuntimeError("will not stop")


class Bot:
    """One bot, as the window reads it."""

    def __init__(self, crash: bool = False) -> None:
        self.crash = crash
        self.stop_called = 0
        self.started = 0

    def run(self) -> None:
        self.started += 1
        if self.crash:
            raise RuntimeError("engine down")


# ---------------------------------------------------------------------
# The case tables both sides are driven with
# ---------------------------------------------------------------------

LOG_CASES: dict = {
    "buy": {"message": "BUY 1 BTC at 100"},
    "sell": {"message": "sell 2 ETH"},
    "fold": {"message": "fold rebuy done"},
    "scrum": {"message": "scrum  window open"},
    "initial_entry": {"message": "initial entry placed"},
    "fire_window": {"message": "fire-window open"},
    "executed": {"message": "Executed order 12"},
    "wrong_capitals": {"message": "EXECUTED ORDER 12"},
    "near_miss": {"message": "buyer beware"},
    "quiet": {"message": "idle tick"},
    "empty": {"message": ""},
    "no_message_key": {},
    "unicode": {"message": UNICODE_LINE},
    "markup": {"message": MARKUP_LINE},
    "apostrophe": {"message": APOSTROPHE_LINE},
    "newline": {"message": NEWLINE_LINE},
    "long": {"message": LONG_LINE},
    "zero": {"message": "0"},
    "negative": {"message": "-1"},
    "thousand_million": {"message": "1000000000"},
    "one_billionth": {"message": "0.000000001"},
    "infinite": {"message": "inf"},
    "minus_infinite": {"message": "-inf"},
    "not_a_number": {"message": "nan"},
    "number_where_text_belongs": {"message": 5},
    "message_is_a_decimal": {"message": 12.0},
    "message_is_true": {"message": True},
}

LOG_REFUSING = (
    "number_where_text_belongs",
    "message_is_a_decimal",
    "message_is_true",
)

FILL_CASES: dict = {
    "happy": {"side": "buy", "symbol": "BTC/USD", "amount": 0.5, "price": 100.0},
    "empty": {},
    "zero": {"side": "sell", "symbol": "BTC/USD", "amount": 0.0, "price": 0.0},
    "negative": {"side": "sell", "symbol": "BTC/USD", "amount": -2.0, "price": -1.5},
    "thousand_million": {
        "side": "buy",
        "symbol": "BTC/USD",
        "amount": 1_000_000_000.0,
        "price": 1_000_000_000.0,
    },
    "one_billionth": {
        "side": "buy",
        "symbol": "BTC/USD",
        "amount": 1e-9,
        "price": 1e-9,
    },
    "whole_number": {"side": "buy", "symbol": "BTC/USD", "amount": 12, "price": 12},
    "decimal_number": {
        "side": "buy",
        "symbol": "BTC/USD",
        "amount": 12.0,
        "price": 12.0,
    },
    "infinite": {
        "side": "buy",
        "symbol": "BTC/USD",
        "amount": float("inf"),
        "price": float("inf"),
    },
    "minus_infinite": {
        "side": "buy",
        "symbol": "BTC/USD",
        "amount": float("-inf"),
        "price": float("-inf"),
    },
    "not_a_number": {
        "side": "buy",
        "symbol": "BTC/USD",
        "amount": float("nan"),
        "price": float("nan"),
    },
    "unicode": {"side": "buy", "symbol": UNICODE_SYMBOL, "amount": 1.0, "price": 1.0},
    "markup": {"side": "buy", "symbol": "<i>X</i>/USD", "amount": 1.0, "price": 1.0},
    "apostrophe": {
        "side": "buy",
        "symbol": "Ekthelius" + chr(39) + "/USD",
        "amount": 1.0,
        "price": 1.0,
    },
    "newline": {"side": "buy", "symbol": "two\nlines", "amount": 1.0, "price": 1.0},
    "long": {"side": "buy", "symbol": LONG_LINE, "amount": 1.0, "price": 1.0},
    "wrong_capitals": {"side": "BUY", "symbol": "BTC/USD", "amount": 1.0, "price": 1.0},
    "number_where_text_belongs": {
        "side": "buy",
        "symbol": 5,
        "amount": 1.0,
        "price": 1.0,
    },
    "side_is_a_number": {"side": 5, "symbol": "BTC/USD", "amount": 1.0, "price": 1.0},
    "side_is_true": {"side": True, "symbol": "BTC/USD", "amount": 1.0, "price": 1.0},
    "text_where_a_number_belongs": {
        "side": "buy",
        "symbol": "BTC/USD",
        "amount": "many",
        "price": 1.0,
    },
    "price_is_text": {
        "side": "buy",
        "symbol": "BTC/USD",
        "amount": 1.0,
        "price": "lots",
    },
}

FILL_REFUSING = (
    "side_is_a_number",
    "side_is_true",
    "text_where_a_number_belongs",
    "price_is_text",
)

API_CASES: dict = {
    "request": ["exchange.request", {"method": "fetch_ticker"}],
    "response": ["exchange.response", {"status": 200}],
    "empty": ["exchange.request", {}],
    "text": ["exchange.response", "plain"],
    "number": ["exchange.response", 5],
    "nothing": ["exchange.response", None],
    "unicode": ["exchange.request", {"pair": UNICODE_SYMBOL}],
    "markup": ["exchange.request", {"note": "<b>x</b>"}],
    "apostrophe": ["exchange.request", {"note": "Ekthelius" + chr(39)}],
    "newline": ["exchange.request", {"note": "two\nlines"}],
    "long": ["exchange.request", {"note": LONG_LINE}],
    "not_a_number": ["exchange.response", {"age": float("nan")}],
    "infinite": ["exchange.response", {"age": float("inf")}],
    "minus_infinite": ["exchange.response", {"age": float("-inf")}],
    "thousand_million": ["exchange.response", {"slots": 1_000_000_000}],
    "one_billionth": ["exchange.response", {"age": 1e-9}],
    "zero": ["exchange.response", {"age": 0}],
    "negative": ["exchange.response", {"age": -1}],
}

API_REFUSING: tuple = ()

BASE_CASES = ("USD", "USDT", "USDC", "EUR", "GBP", "", UNICODE_SYMBOL)

EXCHANGE_CASES = ("coinbase", "kraken", "binance", "nope", "")

SEQUENCES: dict = {
    "log_then_fill": [["log", "buy"], ["fill", "happy"]],
    "fill_then_log": [["fill", "happy"], ["log", "buy"]],
    "two_logs": [["log", "buy"], ["log", "quiet"]],
    "log_then_refusing_log": [["log", "buy"], ["log", "number_where_text_belongs"]],
    "refusing_log_then_log": [["log", "number_where_text_belongs"], ["log", "buy"]],
    "fill_then_refusing_fill": [["fill", "happy"], ["fill", "side_is_a_number"]],
    "refusing_fill_then_fill": [["fill", "side_is_a_number"], ["fill", "happy"]],
    "api_then_log": [["api", "request"], ["log", "sell"]],
    "empty_then_full": [["log", "empty"], ["log", "buy"]],
    "three_steps": [["log", "buy"], ["fill", "happy"], ["api", "response"]],
    "base_then_log": [["base", "EUR"], ["log", "buy"]],
    "base_then_unknown_base": [["base", "EUR"], ["base", "GBP"]],
    "exchange_then_base": [["exchange", "kraken"], ["base", "USDC"]],
    "start_then_stop": [["credentials", "both"], ["start", ""], ["stop", ""]],
    "start_then_start": [["credentials", "both"], ["start", ""], ["start", ""]],
    "start_with_no_credentials": [["start", ""]],
    "start_with_no_key": [["credentials", "secret_only"], ["start", ""]],
    "start_with_no_signature": [["credentials", "key_only"], ["start", ""]],
    "start_with_no_target": [
        ["credentials", "both"],
        ["base", "GBP"],
        ["clear_target", ""],
        ["start", ""],
    ],
    "stop_with_no_bot": [["stop", ""]],
    "close_with_no_bot": [["close", ""]],
    "start_then_close": [["credentials", "both"], ["start", ""], ["close", ""]],
    "log_after_start": [["credentials", "both"], ["start", ""], ["log", "buy"]],
    "many_lines": [["log", "buy"]] * 6,
}

CREDENTIALS = {
    "both": [API_KEY, API_SIGNATURE],
    "key_only": [API_KEY, ""],
    "secret_only": ["", API_SIGNATURE],
    "padded": ["  " + API_KEY + "  ", "  " + API_SIGNATURE + "  "],
    "none": ["", ""],
}

PICTURE_CASES = (
    "at_rest",
    "running",
    "one_log_line",
    "one_fill_line",
    "many_lines",
    "unicode_line",
    "long_line",
)

WORKER_CASES: dict = {
    "happy": {},
    "connect_refuses": {"connect_error": RuntimeError("no venue")},
    "bot_crashes": {"crash": True},
    "disconnect_refuses": {"disconnect_error": RuntimeError("stuck")},
    "config_refuses": {"config_error": ValueError("bad config")},
    "bot_refuses_to_build": {"bot_error": TypeError("bad bot")},
}

WORKER_REFUSING = ("config_refuses", "bot_refuses_to_build")


# ---------------------------------------------------------------------
# Reading the two sides into one shape
# ---------------------------------------------------------------------


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


FONT_MARK = "<a width this machine's fonts decided>"
SEEDED_WIDTHS = frozenset({surface.WINDOW_WIDTH, surface.WINDOW_HEIGHT})


def platform_chosen(value):
    """One value with anything the machine chose replaced by a marker.

    A settled pixel width is the host's answer, not the product's.
    Everything this test seeded is kept.
    """
    if isinstance(value, dict):
        found = {}
        for key, item in value.items():
            if key.endswith("_px") and item not in SEEDED_WIDTHS:
                found[key] = FONT_MARK
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
    """One drive's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(readable(body), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def guarded(run):
    """Run one step, keeping either that it worked or how it refused.

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


def event(topic, data):
    """One bus message of the shape both sides read."""
    return types.SimpleNamespace(topic=topic, data=data)


# ---------------------------------------------------------------------
# Building each side
# ---------------------------------------------------------------------


def old_window(monkeypatch, bus, warnings, threads):
    """One real Lite Live Bot window, with its dropped group box held."""
    app()
    holding_group_boxes(monkeypatch)
    monkeypatch.setattr(shipped, "get_event_bus", lambda: bus)
    monkeypatch.setattr(shipped, "QMessageBox", warnings)
    monkeypatch.setattr(shipped, "threading", threads)
    return hold(shipped.LiteLiveBotWindow())


def new_model(bus, warnings, threads):
    """One surface window wired to the same recorders."""
    return surface.LiveBotWindowModel(
        event_bus=bus,
        warn=warnings.surface_warning,
        thread_factory=threads.surface_thread,
    )


def read_old(window):
    """One shipped window read into the one shape both sides use."""
    return {
        "accessible_name": window.accessibleName(),
        "window_title": window.windowTitle(),
        "window_width_px": window.width(),
        "window_height_px": window.height(),
        "exchange_ids": [
            window.cb_exchange.itemText(index)
            for index in range(window.cb_exchange.count())
        ],
        "exchange_id": window.cb_exchange.currentText(),
        "bases": [
            window.cb_base.itemText(index) for index in range(window.cb_base.count())
        ],
        "base": window.cb_base.currentText(),
        "target_assets": [
            window.cb_target.itemText(index)
            for index in range(window.cb_target.count())
        ],
        "target_asset": window.cb_target.currentText(),
        "target_dollars": window.sp_target.value(),
        "target_min": window.sp_target.minimum(),
        "target_max": window.sp_target.maximum(),
        "target_decimals": window.sp_target.decimals(),
        "target_step": window.sp_target.singleStep(),
        "api_key": window.ed_api_key.text(),
        "api_signature": window.ed_api_secret.text(),
        "key_echo_mode": window.ed_api_key.echoMode().name,
        "signature_echo_mode": window.ed_api_secret.echoMode().name,
        "start_label": window.btn_start.text(),
        "stop_label": window.btn_stop.text(),
        "start_enabled": window.btn_start.isEnabled(),
        "stop_enabled": window.btn_stop.isEnabled(),
        "status_text": window.lbl_status.text(),
        "console": read_old_pane(window.txt_console, surface.CONSOLE_TITLE),
        "api": read_old_pane(window.txt_api, surface.API_TITLE),
        "activity": read_old_pane(window.txt_activity, surface.ACTIVITY_TITLE),
        "bot_built": window._bot is not None,
        "exchange_built": window._exchange is not None,
        "subscriptions_held": len(window._unsubs),
    }


def read_old_pane(pane, title):
    """One real pane read as far as the window reads it."""
    return {
        "title": title,
        "read_only": pane.isReadOnly(),
        "wrap_mode": pane.lineWrapMode().name,
        "style_sheet": pane.styleSheet(),
        "max_blocks": pane.maximumBlockCount(),
        "text": pane.toPlainText(),
        "block_count": pane.blockCount(),
    }


def read_new(payload):
    """One surface window read into the one shape both sides use."""
    return {
        "accessible_name": payload["accessible_name"],
        "window_title": payload["window_title"],
        "window_width_px": payload["window_width"],
        "window_height_px": payload["window_height"],
        "exchange_ids": list(payload["exchange_ids"]),
        "exchange_id": payload["exchange_id"],
        "bases": list(payload["bases"]),
        "base": payload["base"],
        "target_assets": list(payload["target_assets"]),
        "target_asset": payload["target_asset"],
        "target_dollars": payload["target_dollars"],
        "target_min": payload["target_min"],
        "target_max": payload["target_max"],
        "target_decimals": payload["target_decimals"],
        "target_step": payload["target_step"],
        "api_key": payload["api_key"],
        "api_signature": payload["api_secret"],
        "key_echo_mode": payload["echo_mode"],
        "signature_echo_mode": payload["echo_mode"],
        "start_label": payload["start_label"],
        "stop_label": payload["stop_label"],
        "start_enabled": payload["start_enabled"],
        "stop_enabled": payload["stop_enabled"],
        "status_text": payload["status_text"],
        "console": read_new_pane(payload["console"]),
        "api": read_new_pane(payload["api"]),
        "activity": read_new_pane(payload["activity"]),
        "bot_built": payload["bot_built"],
        "exchange_built": payload["exchange_built"],
        "subscriptions_held": payload["subscriptions_held"],
    }


def read_new_pane(found):
    """One surface pane read as far as the window reads it."""
    return {
        "title": found["title"],
        "read_only": found["read_only"],
        "wrap_mode": found["wrap_mode"],
        "style_sheet": found["style_sheet"],
        "max_blocks": found["max_blocks"],
        "text": found["text"],
        "block_count": found["block_count"],
    }


# ---------------------------------------------------------------------
# Driving both sides through the same steps
# ---------------------------------------------------------------------


def old_steps(window, steps):
    """Every step one shipped window takes, each one on its own."""
    found = []
    for kind, name in steps:
        found.append(one_old_step(window, kind, name))
    return found


def one_old_step(window, kind, name):
    """One named step against the shipped window."""
    if kind == "log":
        return lambda: window._on_bot_log(event(surface.LOG_TOPIC, LOG_CASES[name]))
    if kind == "fill":
        return lambda: window._on_trade_filled(
            event(surface.FILL_TOPIC, FILL_CASES[name])
        )
    if kind == "api":
        topic, data = API_CASES[name]
        return lambda: window._on_api_event(event(topic, data))
    if kind == "base":
        return lambda: window.cb_base.setCurrentText(name)
    if kind == "base_slot":
        return lambda: window._on_base_changed(name)
    if kind == "exchange":
        return lambda: window.cb_exchange.setCurrentText(name)
    if kind == "target":
        return lambda: window.cb_target.setCurrentText(name)
    if kind == "clear_target":
        return window.cb_target.clear
    if kind == "credentials":
        key, signature = CREDENTIALS[name]
        return lambda: (
            window.ed_api_key.setText(key),
            window.ed_api_secret.setText(signature),
        )
    if kind == "start":
        return window.btn_start.click
    if kind == "stop":
        return window.btn_stop.click
    if kind == "close":
        return lambda: window.closeEvent(close_event())
    raise LookupError(kind)


def close_event():
    """One window-close message of the shape the window reads."""
    from PySide6.QtGui import QCloseEvent

    return QCloseEvent()


def new_steps(model, steps):
    """Every step one surface window takes, each one on its own."""
    return [one_new_step(model, kind, name) for kind, name in steps]


def one_new_step(model, kind, name):
    """One named step against the surface window."""
    if kind == "log":
        return lambda: model.on_bot_log(
            surface.BusEvent(surface.LOG_TOPIC, LOG_CASES[name])
        )
    if kind == "fill":
        return lambda: model.on_trade_filled(
            surface.BusEvent(surface.FILL_TOPIC, FILL_CASES[name])
        )
    if kind == "api":
        topic, data = API_CASES[name]
        return lambda: model.on_api_event(surface.BusEvent(topic, data))
    if kind == "base":
        return lambda: model.choose_base(name)
    if kind == "base_slot":
        return lambda: model.on_base_changed(name)
    if kind == "exchange":
        return lambda: model.choose_exchange(name)
    if kind == "target":
        return lambda: model.choose_target_asset(name)
    if kind == "clear_target":
        return lambda: model.on_base_changed(surface.NO_TARGET_ASSET)
    if kind == "credentials":
        key, signature = CREDENTIALS[name]
        return lambda: setattr(model, "api_key", key) or setattr(
            model, "api_secret", signature
        )
    if kind == "start":
        return model.press_start
    if kind == "stop":
        return model.press_stop
    if kind == "close":
        return model.close_event
    raise LookupError(kind)


def drive(steps, monkeypatch):
    """Both sides through the same steps, read into one shape.

    Every step is guarded on its own, so a step that refuses does not
    swallow the steps after it and the two sides are compared on WHICH
    step refused as well as on what they hold.
    """
    old_bus = RecordingBus()
    old_warnings = RecordingWarnings()
    old_threads = RecordingThreads()
    window = old_window(monkeypatch, old_bus, old_warnings, old_threads)
    old_outcome = [guarded(step) for step in old_steps(window, steps)]
    old_state = read_old(window)

    new_bus = RecordingBus()
    new_warnings = RecordingWarnings()
    new_threads = RecordingThreads()
    model = new_model(new_bus, new_warnings, new_threads)
    new_outcome = [guarded(step) for step in new_steps(model, steps)]
    payload = surface.build_view_model(model)
    new_state = read_new(payload)
    return {
        "old": old_state,
        "new": new_state,
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
        "old_topics": old_bus.topics,
        "new_topics": new_bus.topics,
        "old_dropped": old_bus.dropped,
        "new_dropped": new_bus.dropped,
        "old_warnings": old_warnings.shown,
        "new_warnings": new_warnings.shown,
        "old_threads": old_threads.started,
        "new_threads": new_threads.started,
        "payload": payload,
        "window": window,
        "model": model,
    }


def both_sides_agree(run, note):
    """Fail unless the two sides did the same thing and hold the same state."""
    assert (
        run["old_outcome"] == run["new_outcome"]
    ), "%s: the shipped window and the surface refused differently: %r against %r" % (
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
    assert run["old_topics"] == run["new_topics"], (
        note,
        run["old_topics"],
        run["new_topics"],
    )
    assert run["old_dropped"] == run["new_dropped"], note
    assert run["old_warnings"] == run["new_warnings"], (
        note,
        run["old_warnings"],
        run["new_warnings"],
    )
    assert run["old_threads"] == run["new_threads"], (
        note,
        run["old_threads"],
        run["new_threads"],
    )


# ---------------------------------------------------------------------
# The two sides, case by case
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(LOG_CASES))
def test_one_bot_log_line_reaches_the_same_panes(name, monkeypatch):
    """The surface writes a log line the shipped window does not."""
    both_sides_agree(drive([["log", name]], monkeypatch), name)


@pytest.mark.parametrize("name", sorted(FILL_CASES))
def test_one_filled_order_writes_the_same_line(name, monkeypatch):
    """The surface writes a fill line the shipped window does not."""
    both_sides_agree(drive([["fill", name]], monkeypatch), name)


@pytest.mark.parametrize("name", sorted(API_CASES))
def test_one_exchange_message_writes_the_same_line(name, monkeypatch):
    """The surface writes an API line the shipped window does not."""
    both_sides_agree(drive([["api", name]], monkeypatch), name)


@pytest.mark.parametrize("base", BASE_CASES)
def test_one_base_choice_refills_the_same_target_picker(base, monkeypatch):
    """The surface offers different assets than the shipped picker."""
    both_sides_agree(drive([["base", base]], monkeypatch), base)


@pytest.mark.parametrize("base", BASE_CASES)
def test_the_base_slot_refills_the_same_target_picker(base, monkeypatch):
    """The wired slot fills the target picker differently on the two sides."""
    both_sides_agree(drive([["base_slot", base]], monkeypatch), base)


@pytest.mark.parametrize("exchange_id", EXCHANGE_CASES)
def test_one_exchange_choice_lands_the_same_way(exchange_id, monkeypatch):
    """The surface takes an exchange id the shipped picker refuses."""
    both_sides_agree(drive([["exchange", exchange_id]], monkeypatch), exchange_id)


@pytest.mark.parametrize("name", sorted(CREDENTIALS))
def test_one_credential_pair_starts_the_same_way(name, monkeypatch):
    """The window starts on credentials the other side refuses."""
    both_sides_agree(drive([["credentials", name], ["start", ""]], monkeypatch), name)


@pytest.mark.parametrize("name", sorted(SEQUENCES))
def test_a_step_sequence_is_the_shipped_windows(name, monkeypatch):
    """A sequence of steps left the two sides holding different text."""
    both_sides_agree(drive(SEQUENCES[name], monkeypatch), name)


def test_every_case_in_every_table_is_driven(monkeypatch):
    """A case sits in a table that nothing ever drives."""
    driven = {"log": set(), "fill": set(), "api": set(), "base": set()}
    for name in LOG_CASES:
        both_sides_agree(drive([["log", name]], monkeypatch), name)
        driven["log"].add(name)
    for name in FILL_CASES:
        both_sides_agree(drive([["fill", name]], monkeypatch), name)
        driven["fill"].add(name)
    for name in API_CASES:
        both_sides_agree(drive([["api", name]], monkeypatch), name)
        driven["api"].add(name)
    for base in BASE_CASES:
        both_sides_agree(drive([["base", base]], monkeypatch), base)
        driven["base"].add(base)
    assert driven["log"] == set(LOG_CASES)
    assert driven["fill"] == set(FILL_CASES)
    assert driven["api"] == set(API_CASES)
    assert driven["base"] == set(BASE_CASES)
    for steps in SEQUENCES.values():
        for kind, name in steps:
            if kind == "credentials":
                assert name in CREDENTIALS, name
    assert set(WORKER_CASES) >= set(WORKER_REFUSING)
    assert set(LOG_REFUSING) <= set(LOG_CASES)
    assert set(FILL_REFUSING) <= set(FILL_CASES)
    assert API_REFUSING == ()


def test_the_sample_hashes_are_reported(monkeypatch):
    """The comparison reports no hash, so nothing can be checked by hand."""
    quiet = drive([["log", "quiet"]], monkeypatch)
    buy = drive([["log", "buy"]], monkeypatch)
    assert len(digest(quiet["old"])) == 64
    assert digest(quiet["old"]) == digest(quiet["new"])
    assert digest(buy["old"]) == digest(buy["new"])
    assert digest(quiet["old"]) != digest(buy["old"])


def test_two_genuinely_different_real_inputs_hash_apart(monkeypatch):
    """The hash gives one value for every window, so it tells nothing apart."""
    quiet = drive([["log", "quiet"]], monkeypatch)
    buy = drive([["log", "buy"]], monkeypatch)
    assert digest(quiet["old"]) != digest(buy["new"]), "old quiet against new buy"
    assert digest(buy["old"]) != digest(quiet["new"]), "old buy against new quiet"
    assert digest(quiet["old"]) == digest(quiet["new"])
    assert digest(buy["old"]) == digest(buy["new"])


def test_the_same_input_hashes_the_same_twice(monkeypatch):
    """The hash moves between two runs of one input, so it reads the clock."""
    assert digest(drive([["log", "buy"]], monkeypatch)["old"]) == digest(
        drive([["log", "buy"]], monkeypatch)["old"]
    )
    assert digest(drive([["log", "buy"]], monkeypatch)["new"]) == digest(
        drive([["log", "buy"]], monkeypatch)["new"]
    )


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
    kept = readable({"window_width_px": surface.WINDOW_WIDTH, "block_count": 3})
    assert kept["window_width_px"] == ["int", str(surface.WINDOW_WIDTH)]
    assert kept["block_count"] == ["int", "3"]
    hidden = platform_chosen({"settled_px": 471})
    assert hidden["settled_px"] == FONT_MARK
    assert (
        platform_chosen({"window_width_px": surface.WINDOW_WIDTH})["window_width_px"]
        == surface.WINDOW_WIDTH
    )


# ---------------------------------------------------------------------
# What each side DID: answered, or refused with which type
# ---------------------------------------------------------------------


def refusals(outcome):
    """The refusal type of every step that refused, in order."""
    return [step["error"] for step in outcome if step["error"]]


def test_the_outcomes_hold_both_an_answer_and_a_refusal(monkeypatch):
    """Every case answered, or every case refused, so the set proves nothing."""
    found = {}
    for name in sorted(LOG_CASES):
        found["log:" + name] = refusals(
            drive([["log", name]], monkeypatch)["old_outcome"]
        )
    for name in sorted(FILL_CASES):
        found["fill:" + name] = refusals(
            drive([["fill", name]], monkeypatch)["old_outcome"]
        )
    answered = [name for name, done in found.items() if not done]
    refused = [name for name, done in found.items() if done]
    assert answered, found
    assert refused, found
    expected = sorted(["log:" + name for name in LOG_REFUSING])
    expected += sorted(["fill:" + name for name in FILL_REFUSING])
    assert sorted(refused) == sorted(expected), sorted(set(refused) ^ set(expected))
    assert len(answered) + len(refused) == len(LOG_CASES) + len(FILL_CASES)


@pytest.mark.parametrize("name", sorted(LOG_REFUSING))
def test_a_refused_log_line_refuses_the_same_way_on_both_sides(name, monkeypatch):
    """One side answered a log line the other refused, or refused differently."""
    run = drive([["log", name]], monkeypatch)
    assert refusals(run["old_outcome"]), name
    assert run["old_outcome"] == run["new_outcome"], (
        name,
        run["old_outcome"],
        run["new_outcome"],
    )
    both_sides_agree(run, name)


@pytest.mark.parametrize("name", sorted(FILL_REFUSING))
def test_a_refused_fill_refuses_the_same_way_on_both_sides(name, monkeypatch):
    """One side answered a fill the other refused, or refused differently."""
    run = drive([["fill", name]], monkeypatch)
    assert refusals(run["old_outcome"]), name
    assert run["old_outcome"] == run["new_outcome"], (
        name,
        run["old_outcome"],
        run["new_outcome"],
    )
    both_sides_agree(run, name)


def test_the_refusal_comparison_holds_more_than_one_type(monkeypatch):
    """Every refusal shares one type, so a swapped refusal reads as unchanged."""
    kinds = set()
    for name in LOG_REFUSING:
        kinds.update(refusals(drive([["log", name]], monkeypatch)["old_outcome"]))
    for name in FILL_REFUSING:
        kinds.update(refusals(drive([["fill", name]], monkeypatch)["old_outcome"]))
    assert len(kinds) > 1, kinds
    assert kinds == {"AttributeError", "ValueError"}, kinds
    assert guarded(lambda: 1) != guarded(lambda: 1 / 0)
    assert guarded(lambda: int("x"))["error"] == "ValueError"


def test_the_refusal_reader_reports_two_different_wordings(monkeypatch):
    """Two refusals worded apart read the same, so a wording change is unseen.

    Both wordings are read off the shipped side. Neither is written down:
    Python words one failure differently between its own versions.
    """
    run = drive([], monkeypatch)
    window = run["window"]
    first = headline_of(
        lambda: window._on_bot_log(event(surface.LOG_TOPIC, {"message": 5}))
    )
    second = headline_of(
        lambda: window._on_trade_filled(
            event(surface.FILL_TOPIC, FILL_CASES["text_where_a_number_belongs"])
        )
    )
    assert first, "the shipped window answered an input it should refuse"
    assert second, "the shipped window answered an input it should refuse"
    assert first != second, (first, second)
    assert headline_of(lambda: None) == ""


def test_a_sequence_that_refuses_part_way_leaves_the_same_text(monkeypatch):
    """A refused step left different text on the two sides."""
    run = drive(SEQUENCES["log_then_refusing_log"], monkeypatch)
    both_sides_agree(run, "log_then_refusing_log")
    assert refusals(run["old_outcome"]) == ["AttributeError"]
    assert run["old"]["console"]["text"] == "BUY 1 BTC at 100\n"
    assert run["old"]["console"]["block_count"] == 2
    clean = drive([["log", "buy"]], monkeypatch)
    assert clean["old"]["console"]["text"] == "BUY 1 BTC at 100"
    assert digest(run["old"]) != digest(clean["old"])


# ---------------------------------------------------------------------
# The worker thread
# ---------------------------------------------------------------------


class OldExchange:
    """One venue connection, as the shipped worker drives it."""

    def __init__(self, exchange_id, connect_error=None, disconnect_error=None) -> None:
        self.exchange_id = exchange_id
        self.connect_error = connect_error
        self.disconnect_error = disconnect_error
        self.calls: list = []

    async def connect(self, api_key, api_secret):
        self.calls.append(["connect", api_key, api_secret])
        if self.connect_error is not None:
            raise self.connect_error

    async def disconnect(self):
        self.calls.append(["disconnect"])
        if self.disconnect_error is not None:
            raise self.disconnect_error


class NewExchange:
    """One venue connection, as the surface worker drives it."""

    def __init__(self, exchange_id, connect_error=None, disconnect_error=None) -> None:
        self.exchange_id = exchange_id
        self.connect_error = connect_error
        self.disconnect_error = disconnect_error
        self.calls: list = []

    def connect(self, api_key, api_secret):
        self.calls.append(["connect", api_key, api_secret])
        if self.connect_error is not None:
            raise self.connect_error

    def disconnect(self):
        self.calls.append(["disconnect"])
        if self.disconnect_error is not None:
            raise self.disconnect_error


class OldBot:
    """One bot, as the shipped worker drives it."""

    def __init__(self, config, exchange, crash=False) -> None:
        import threading as real_threading

        self.config = config
        self.exchange = exchange
        self.crash = crash
        self._stop_event = real_threading.Event()
        self._stop_event.set()

    async def start(self):
        if self.crash:
            raise RuntimeError("engine down")

    async def stop(self):
        return None


class NewBot:
    """One bot, as the surface worker drives it."""

    def __init__(self, config, exchange, crash=False) -> None:
        self.config = config
        self.exchange = exchange
        self.crash = crash

    def start(self):
        if self.crash:
            raise RuntimeError("engine down")


def worker_run(name, monkeypatch):
    """One worker case driven through both sides, read into one shape."""
    spec = WORKER_CASES[name]
    args = ("coinbase", "USD", "BTC", "BTC/USD", 200.0, API_KEY, API_SIGNATURE)

    old_bus = RecordingBus()
    window = old_window(monkeypatch, old_bus, RecordingWarnings(), RecordingThreads())
    old_exchanges: list = []

    def old_exchange(exchange_id):
        found = OldExchange(
            exchange_id, spec.get("connect_error"), spec.get("disconnect_error")
        )
        old_exchanges.append(found)
        return found

    def config(mode, **fields):
        if spec.get("config_error") is not None:
            raise spec["config_error"]
        return dict(fields, mode=str(mode))

    def old_bot(cfg, exchange):
        if spec.get("bot_error") is not None:
            raise spec["bot_error"]
        return OldBot(cfg, exchange, spec.get("crash", False))

    monkeypatch.setattr(shipped, "CCXTConnector", old_exchange)
    monkeypatch.setattr(shipped, "make_bot_config", config)
    monkeypatch.setattr(shipped, "ScrummingBot", old_bot)
    monkeypatch.setattr(
        shipped, "BotMode", types.SimpleNamespace(SCRUMMING="SCRUMMING")
    )
    old_outcome = guarded(lambda: window._run_bot(*args))
    old_state = {
        "console": window.txt_console.toPlainText(),
        "exchange_calls": [found.calls for found in old_exchanges],
        "configs": [
            found.config for found in [window._bot] if isinstance(found, OldBot)
        ],
        "bot_built": window._bot is not None,
    }

    new_exchanges: list = []

    def new_exchange(exchange_id):
        found = NewExchange(
            exchange_id, spec.get("connect_error"), spec.get("disconnect_error")
        )
        new_exchanges.append(found)
        return found

    def new_bot(cfg, exchange):
        if spec.get("bot_error") is not None:
            raise spec["bot_error"]
        return NewBot(cfg, exchange, spec.get("crash", False))

    model = surface.LiveBotWindowModel(
        exchange_factory=new_exchange, config_factory=config, bot_factory=new_bot
    )
    new_outcome = guarded(lambda: model.run_bot(*args))
    new_state = {
        "console": model.console.text,
        "exchange_calls": [found.calls for found in new_exchanges],
        "configs": [found.config for found in [model.bot] if isinstance(found, NewBot)],
        "bot_built": model.bot is not None,
    }
    return {
        "old": old_state,
        "new": new_state,
        "old_outcome": old_outcome,
        "new_outcome": new_outcome,
    }


@pytest.mark.parametrize("name", sorted(WORKER_CASES))
def test_the_worker_does_the_same_thing_on_both_sides(name, monkeypatch):
    """The surface worker connects, builds or disconnects differently."""
    run = worker_run(name, monkeypatch)
    assert run["old_outcome"] == run["new_outcome"], (
        name,
        run["old_outcome"],
        run["new_outcome"],
    )
    assert readable(run["old"]) == readable(run["new"]), (
        name,
        run["old"],
        run["new"],
    )
    assert digest(run["old"]) == digest(run["new"]), name


def test_every_worker_case_is_driven(monkeypatch):
    """A worker case sits in the table that nothing ever drives."""
    driven = set()
    for name in WORKER_CASES:
        run = worker_run(name, monkeypatch)
        assert run["old_outcome"] == run["new_outcome"], name
        driven.add(name)
    assert driven == set(WORKER_CASES)


def test_the_worker_outcomes_hold_both_an_answer_and_a_refusal(monkeypatch):
    """Every worker case answered, so the refusal set proves nothing."""
    found = {
        name: worker_run(name, monkeypatch)["old_outcome"]["error"]
        for name in sorted(WORKER_CASES)
    }
    refused = sorted(name for name, error in found.items() if error)
    assert refused == sorted(WORKER_REFUSING), found
    assert {found[name] for name in WORKER_REFUSING} == {"ValueError", "TypeError"}


def test_a_venue_that_refuses_the_connection_ends_the_worker(monkeypatch):
    """A refused connection ran the bot anyway, or said nothing about it."""
    run = worker_run("connect_refuses", monkeypatch)
    assert run["old"]["bot_built"] is False
    assert run["new"]["bot_built"] is False
    assert run["old"]["console"].startswith("CONNECT FAILED")
    assert run["old"]["console"] == run["new"]["console"]
    assert run["old"]["exchange_calls"] == [[["connect", API_KEY, API_SIGNATURE]]]


def test_a_config_the_worker_cannot_build_leaves_the_venue_open(monkeypatch):
    """A refused config closed the venue, so the two sides would differ.

    The shipped worker builds the config and the bot outside the block
    that closes the connection, so a refusal there ends the worker with
    the venue still open. The surface does the same.
    """
    run = worker_run("config_refuses", monkeypatch)
    assert run["old_outcome"]["error"] == "ValueError"
    assert run["old"]["exchange_calls"] == [[["connect", API_KEY, API_SIGNATURE]]]
    assert run["new"]["exchange_calls"] == [[["connect", API_KEY, API_SIGNATURE]]]
    healthy = worker_run("happy", monkeypatch)
    assert healthy["old"]["exchange_calls"] == [
        [["connect", API_KEY, API_SIGNATURE], ["disconnect"]]
    ]


def old_worker_that_cannot_close(monkeypatch):
    """One shipped worker whose venue refuses to close, driven on its own."""
    window = old_window(
        monkeypatch, RecordingBus(), RecordingWarnings(), RecordingThreads()
    )
    monkeypatch.setattr(
        shipped,
        "CCXTConnector",
        lambda exchange_id: OldExchange(
            exchange_id, disconnect_error=RuntimeError("stuck")
        ),
    )
    monkeypatch.setattr(shipped, "make_bot_config", lambda mode, **fields: dict(fields))
    monkeypatch.setattr(shipped, "ScrummingBot", OldBot)
    monkeypatch.setattr(
        shipped, "BotMode", types.SimpleNamespace(SCRUMMING="SCRUMMING")
    )
    window._run_bot("coinbase", "USD", "BTC", "BTC/USD", 200.0, API_KEY, API_SIGNATURE)


def test_the_disconnect_warning_is_written_under_the_same_logger(monkeypatch):
    """A venue that will not close is announced differently on one side."""
    app()
    old_said = warnings_from(
        surface.LOGGER_NAME,
        lambda: old_worker_that_cannot_close(monkeypatch),
    )
    new_said = warnings_from(
        surface.LOGGER_NAME,
        lambda: surface.LiveBotWindowModel(
            exchange_factory=lambda exchange_id: NewExchange(
                exchange_id, disconnect_error=RuntimeError("stuck")
            ),
            config_factory=lambda mode, **fields: dict(fields),
            bot_factory=lambda cfg, exchange: NewBot(cfg, exchange),
        ).run_bot("coinbase", "USD", "BTC", "BTC/USD", 200.0, API_KEY, API_SIGNATURE),
    )
    assert len(old_said) == 1, old_said
    assert old_said == new_said, (old_said, new_said)
    assert "Lite Live Bot status refresh failed" in old_said[0]


def test_the_config_the_worker_builds_carries_the_chosen_pair(monkeypatch):
    """The worker built a config for a pair the operator did not choose."""
    run = worker_run("happy", monkeypatch)
    assert run["old"]["configs"] == run["new"]["configs"]
    assert run["old"]["configs"] == [
        {
            "exchange_id": "coinbase",
            "base_currency": "USD",
            "target_asset": "BTC",
            "symbol": "BTC/USD",
            "target_balance": 200.0,
            "mode": "SCRUMMING",
        }
    ]


# ---------------------------------------------------------------------
# STOP
# ---------------------------------------------------------------------


def test_the_stop_button_asks_the_bot_to_stop_on_both_sides(monkeypatch):
    """The STOP button left the bot running on one side."""
    import asyncio
    import threading as real_threading

    app()
    run = drive([], monkeypatch)
    window = run["window"]
    loop = asyncio.new_event_loop()
    runner = real_threading.Thread(target=loop.run_forever, daemon=True)
    runner.start()
    while not loop.is_running():
        pass
    stopped: list = []

    class LoopBot:
        async def stop(self):
            stopped.append(1)

    try:
        window._bot = LoopBot()
        window._loop = loop
        window._on_stop()
    finally:
        loop.call_soon_threadsafe(loop.stop)
    assert stopped == [1]
    assert window.txt_console.toPlainText().splitlines() == [
        surface.STOPPING_TEXT,
        surface.STOPPED_TEXT,
    ]

    waiter = StopWaiter()
    model = surface.LiveBotWindowModel(stop_caller=waiter)
    model.bot = Bot()
    model.loop = RunningLoop()
    model.on_stop()
    assert model.bot is None
    assert waiter.waited == [surface.STOP_TIMEOUT_S]
    assert model.console.text.splitlines() == [
        surface.STOPPING_TEXT,
        surface.STOPPED_TEXT,
    ]


def test_a_bot_that_will_not_stop_writes_the_same_line(monkeypatch):
    """A bot that refuses to stop is reported differently on one side."""
    import asyncio
    import threading as real_threading

    app()
    run = drive([], monkeypatch)
    window = run["window"]
    loop = asyncio.new_event_loop()
    runner = real_threading.Thread(target=loop.run_forever, daemon=True)
    runner.start()
    while not loop.is_running():
        pass

    class RefusingBot:
        async def stop(self):
            raise RuntimeError("will not stop")

    try:
        window._bot = RefusingBot()
        window._loop = loop
        window._on_stop()
    finally:
        loop.call_soon_threadsafe(loop.stop)
    old_lines = window.txt_console.toPlainText().splitlines()

    model = surface.LiveBotWindowModel(stop_caller=StopWaiter(fail=True))
    model.bot = Bot()
    model.loop = RunningLoop()
    model.on_stop()
    assert old_lines == model.console.text.splitlines()
    assert old_lines[1].startswith("STOP ERROR:")


def test_a_stop_with_no_running_loop_still_clears_the_window(monkeypatch):
    """A window with no loop left its buttons pointing the wrong way."""
    run = drive([], monkeypatch)
    window = run["window"]
    window._bot = object()
    window._loop = None
    window.btn_start.setEnabled(False)
    window.btn_stop.setEnabled(True)
    window._on_stop()
    model = surface.LiveBotWindowModel()
    model.bot = Bot()
    model.loop = None
    model.start_enabled = False
    model.stop_enabled = True
    model.on_stop()
    assert window.btn_start.isEnabled() is model.start_enabled is True
    assert window.btn_stop.isEnabled() is model.stop_enabled is False
    assert window.lbl_status.text() == model.status_text == surface.STATUS_IDLE
    assert window.txt_console.toPlainText() == model.console.text


def test_a_way_off_a_topic_that_refuses_is_swallowed_on_both_sides(monkeypatch):
    """One bad way back off a topic stopped the rest from being dropped."""
    run = drive([], monkeypatch)
    window = run["window"]
    dropped: list = []

    def refuse():
        raise RuntimeError("bus gone")

    window._bot = object()
    window._unsubs = [lambda: dropped.append("a"), refuse, lambda: dropped.append("b")]
    window._on_stop()
    assert dropped == ["a", "b"]
    assert window._unsubs == []
    taken = drive([["credentials", "both"], ["start", ""]], monkeypatch)
    taken["window"]._bot = object()
    taken["window"]._on_stop()
    assert taken["old_topics"] == list(surface.BUS_TOPICS)
    taken["model"].bot = Bot()
    taken["model"].on_stop()
    assert taken["new_topics"] == list(surface.BUS_TOPICS)

    model = surface.LiveBotWindowModel()
    model.bot = Bot()
    model_dropped: list = []
    model.unsubs = [
        lambda: model_dropped.append("a"),
        refuse,
        lambda: model_dropped.append("b"),
    ]
    model.on_stop()
    assert model_dropped == dropped
    assert model.unsubs == []
    assert surface.UNSUBSCRIBE_FAILED in [call[0] for call in model.calls]


# ---------------------------------------------------------------------
# The configuration group the shipped window drops
# ---------------------------------------------------------------------


def test_the_shipped_window_drops_its_whole_configuration_group(monkeypatch):
    """The configuration controls reach the window, so the record is wrong.

    The shipped window builds the grid inside one group box and then
    puts a second group box on screen, so every picker, the target box
    and both credential fields are collected as the window is built.
    Reading one of them raises rather than answering.
    """
    app()
    monkeypatch.setattr(shipped, "get_event_bus", lambda: RecordingBus())
    dropped = hold(shipped.LiteLiveBotWindow())
    with pytest.raises(RuntimeError):
        dropped.cb_exchange.currentText()
    with pytest.raises(RuntimeError):
        dropped.sp_target.value()
    with pytest.raises(RuntimeError):
        dropped.ed_api_key.text()
    assert dropped.btn_start.text() == surface.START_LABEL
    assert dropped.lbl_status.text() == surface.STATUS_IDLE
    assert dropped.txt_console.isReadOnly() is True
    assert surface.CONTROLS_REACH_THE_WINDOW is False
    held = holding_group_boxes(monkeypatch)
    kept = hold(shipped.LiteLiveBotWindow())
    assert kept.cb_exchange.currentText() == surface.DEFAULT_EXCHANGE_ID
    assert len(held) == surface.CONFIG_GROUPS_BUILT + len(surface.PANE_TITLES)
    assert [box.title() for box in held[: surface.CONFIG_GROUPS_BUILT]] == [
        surface.CONFIG_GROUP_TITLE,
        surface.CONFIG_GROUP_TITLE,
    ]


def test_the_group_the_window_shows_holds_only_the_buttons(monkeypatch):
    """The configuration grid reached the group the operator sees."""
    app()
    monkeypatch.setattr(shipped, "get_event_bus", lambda: RecordingBus())
    window = hold(shipped.LiteLiveBotWindow())
    root = window.centralWidget().layout()
    group = root.itemAt(surface.DROPPED_GROUP_INDEX).widget()
    assert group.title() == surface.CONFIG_GROUP_TITLE
    container = group.layout().itemAt(0).widget()
    rows = container.layout()
    assert rows.count() == 1, "the configuration grid reached the window"
    button_row = rows.itemAt(0).layout()
    found = [
        button_row.itemAt(index).widget()
        for index in range(button_row.count())
        if button_row.itemAt(index).widget() is not None
    ]
    assert [widget.text() for widget in found] == [
        surface.START_LABEL,
        surface.STOP_LABEL,
        surface.STATUS_IDLE,
    ]
    assert list(surface.DROPPED_ITEM_NAMES) == [cell[0] for cell in surface.GRID_CELLS]


def test_the_surface_names_every_item_that_reaches_the_window(monkeypatch):
    """An item the operator sees is missing from the live list."""
    app()
    monkeypatch.setattr(shipped, "get_event_bus", lambda: RecordingBus())
    window = hold(shipped.LiteLiveBotWindow())
    live = {
        "start_button": window.btn_start,
        "stop_button": window.btn_stop,
        "status_label": window.lbl_status,
        "console_pane": window.txt_console,
        "api_pane": window.txt_api,
        "activity_pane": window.txt_activity,
    }
    assert sorted(live) == sorted(surface.LIVE_ITEM_NAMES)
    for name, widget in live.items():
        assert widget.isHidden() is False, name
    assert set(surface.LIVE_ITEM_NAMES) & set(surface.DROPPED_ITEM_NAMES) == set()


# ---------------------------------------------------------------------
# Counting what the shipped file wires, waits on, and builds
# ---------------------------------------------------------------------

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
    "QPlainTextEdit",
    "QDoubleSpinBox",
    "QMainWindow",
    "QMessageBox",
)


def count_text(path, needle):
    """How many times one written form appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def count_built(path, names):
    """How many times one file constructs any of `names`."""
    text = path.read_text(encoding="utf-8")
    return sum(len(re.findall(r"\b%s\s*\(" % name, text)) for name in names)


VENUE_RECEIVERS = ("_exchange", "exchange")


def count_connects(path):
    """Wiring calls and venue calls named `connect`, counted apart.

    ``exchange.connect(...)`` opens a venue session; it is not a wiring,
    and a plain text count reads it as one. The two are split on what
    the call is made on, so the split holds whether the call is awaited
    or not.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wiring = 0
    venue = 0
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            continue
        owner = node.func.value
        if isinstance(owner, ast.Attribute) and owner.attr in VENUE_RECEIVERS:
            venue += 1
        else:
            wiring += 1
    return wiring, venue


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


def test_the_window_wires_six_signals_and_the_surface_names_six_actions():
    """A wiring appeared on one side and not the other."""
    wiring, venue = count_connects(WINDOW_PATH)
    assert wiring == WINDOW_WIRING_CONNECTS == 6
    assert venue == WINDOW_VENUE_CONNECTS == 1
    assert count_text(WINDOW_PATH, ".connect(") == wiring + venue
    assert count_connects(SURFACE_PATH) == (0, WINDOW_VENUE_CONNECTS)
    assert count_connects(WIRING_CONTROL_PATH) == (CONTROL_WIRING_CONNECTS, 0)
    assert CONTROL_WIRING_CONNECTS == 1
    assert len(surface.ACTIONS) == wiring
    for name in surface.ACTIONS.values():
        assert callable(getattr(surface.LiveBotWindowModel, name)), name


def test_the_window_declares_three_signals_and_the_surface_names_three():
    """A signal declaration appeared on one side and not the other."""
    signal_names = ("Signal",)
    assert count_built(WINDOW_PATH, signal_names) == WINDOW_SIGNAL_BUILDS == 3
    assert count_built(SURFACE_PATH, signal_names) == 0
    assert count_built(SIGNAL_CONTROL_PATH, signal_names) == CONTROL_SIGNAL_BUILDS == 3
    assert count_text(WINDOW_PATH, "Signal") > WINDOW_SIGNAL_BUILDS
    assert len(surface.SIGNAL_NAMES) == WINDOW_SIGNAL_BUILDS


def test_the_window_starts_no_timer_and_the_surface_names_no_wait():
    """A wait appeared on one side and not the other."""
    from PySide6.QtCore import QObject, QTimer

    app()
    timer_names = ("QTimer",)
    assert count_built(WINDOW_PATH, timer_names) == WINDOW_TIMER_BUILDS == 0
    assert count_built(SURFACE_PATH, timer_names) == 0
    assert count_built(TIMER_CONTROL_PATH, timer_names) == CONTROL_TIMER_BUILDS == 1
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
        held = QTimer()
        held.start(5)
        held.stop()
        seeded = list(started)
        started.clear()
        was = shipped.get_event_bus
        shipped.get_event_bus = lambda: RecordingBus()
        try:
            hold(shipped.LiteLiveBotWindow())
        finally:
            shipped.get_event_bus = was
        old_started = list(started)
        started.clear()
        surface.LiveBotWindowModel()
        new_started = list(started)
    finally:
        QObject.startTimer = first_start
        QTimer.start = first_timer
        QTimer.singleShot = first_single
    assert [name for name, _args in seeded] == ["QTimer.start"], seeded
    assert old_started == [], old_started
    assert new_started == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()


def test_the_window_subscribes_to_four_topics_and_the_surface_names_four():
    """A bus wiring appeared on one side and not the other."""
    assert count_text(WINDOW_PATH, ".subscribe(") == WINDOW_BUS_SITES == 4
    assert count_text(SURFACE_PATH, "self.subscribe(") == WINDOW_BUS_SITES
    assert count_text(SURFACE_PATH, "self.event_bus.subscribe(") == 1
    assert count_text(BUS_CONTROL_PATH, ".subscribe(") == CONTROL_BUS_SITES == 2
    assert len(surface.BUS_TOPICS) == WINDOW_BUS_SITES
    assert surface.BUS_TOPICS == (
        surface.LOG_TOPIC,
        surface.FILL_TOPIC,
        surface.REQUEST_TOPIC,
        surface.RESPONSE_TOPIC,
    )


def test_the_screen_elements_the_window_builds_are_counted():
    """The element counter cannot report, so its number means nothing."""
    assert count_elements(WINDOW_PATH) == WINDOW_ELEMENT_BUILDS == 23
    assert count_elements(ELEMENT_CONTROL_PATH) == CONTROL_ELEMENT_BUILDS == 3
    assert count_built(ELEMENT_CONTROL_PATH, WIDGET_NAMES_BUILT) == 2
    assert declared_widget_classes(ELEMENT_CONTROL_PATH) == {"StatCard"}
    assert declared_widget_classes(WINDOW_PATH) == {"LiteLiveBotWindow"}
    assert count_built(WINDOW_PATH, WIDGET_NAMES_BUILT) == 22
    assert count_elements(SURFACE_PATH) == 0
    assert declared_widget_classes(SURFACE_PATH) == set()


def test_the_class_counter_finds_a_class_declared_inside_a_method():
    """The class counter reads the top level only, so a nested class is lost."""
    found = declared_classes(NESTED_CLASS_CONTROL_PATH)
    assert "_StockLogHandler" in found, sorted(found)
    assert "StockMainWindow" in found, sorted(found)
    assert len(found) == 4, sorted(found)
    tree = ast.parse(NESTED_CLASS_CONTROL_PATH.read_text(encoding="utf-8"))
    top_level = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert top_level == set(), top_level
    assert declared_classes(WINDOW_PATH) == {"LiteLiveBotWindow"}


# ---------------------------------------------------------------------
# Every class and every method has a counterpart
# ---------------------------------------------------------------------


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
    assert "_sig_console" not in members(shipped.LiteLiveBotWindow)
    assert isinstance(vars(shipped.LiteLiveBotWindow)["_sig_console"], Signal)


CLASS_MAP = {"LiteLiveBotWindow": "LiveBotWindowModel"}

METHOD_MAP = {
    "LiteLiveBotWindow.__init__": "LiveBotWindowModel.__init__",
    "LiteLiveBotWindow._build_ui": "LiveBotWindowModel.build_ui",
    "LiteLiveBotWindow._build_controls": "LiveBotWindowModel.build_controls",
    "LiteLiveBotWindow._build_panes": "LiveBotWindowModel.build_panes",
    "LiteLiveBotWindow._wire_signals": "LiveBotWindowModel.wire_signals",
    "LiteLiveBotWindow._on_base_changed": "LiveBotWindowModel.on_base_changed",
    "LiteLiveBotWindow._on_bot_log": "LiveBotWindowModel.on_bot_log",
    "LiteLiveBotWindow._on_trade_filled": "LiveBotWindowModel.on_trade_filled",
    "LiteLiveBotWindow._on_api_event": "LiveBotWindowModel.on_api_event",
    "LiteLiveBotWindow._on_start": "LiveBotWindowModel.on_start",
    "LiteLiveBotWindow._run_bot": "LiveBotWindowModel.run_bot",
    "LiteLiveBotWindow._on_stop": "LiveBotWindowModel.on_stop",
    "LiteLiveBotWindow.closeEvent": "LiveBotWindowModel.close_event",
}

HELPER_MAP = {
    "main": "launch",
    "_sig_console": "LiveBotWindowModel.append_console",
    "_sig_api": "LiveBotWindowModel.append_api",
    "_sig_activity": "LiveBotWindowModel.append_activity",
    "start_button": "LiveBotWindowModel.press_start",
    "stop_button": "LiveBotWindowModel.press_stop",
    "exchange_picker": "LiveBotWindowModel.choose_exchange",
    "base_picker": "LiveBotWindowModel.choose_base",
    "target_picker": "LiveBotWindowModel.choose_target_asset",
    "warning_box": "LiveBotWindowModel.raise_warning",
    "bus_subscribe": "LiveBotWindowModel.subscribe",
    "worker_thread": "LiveBotWindowModel.start_thread",
    "pane_widget": "PaneModel",
    "bus_event": "BusEvent",
    "bridge_handler": "view_model",
    "shared_window": "pane_model",
    "model_from_wiring": "build_model",
    "whole_state": "build_view_model",
    "one_pane_read": "pane_view",
    "activity_keyword": "is_activity_line",
    "fill_text": "fill_line",
    "api_text": "api_line",
    "pane_append": "appended",
    "pane_cap": "capped",
    "pairs_for_base": "target_assets",
    "pair_name": "symbol_for",
    "collaborator": "wired",
    "no_bus_unsubscribe": "no_unsubscribe",
}

WINDOW_MODEL_MEMBERS = {
    "__init__",
    "build_ui",
    "build_controls",
    "build_panes",
    "wire_signals",
    "on_base_changed",
    "choose_exchange",
    "choose_base",
    "choose_target_asset",
    "append_console",
    "append_api",
    "append_activity",
    "on_bot_log",
    "on_trade_filled",
    "on_api_event",
    "press_start",
    "press_stop",
    "on_start",
    "raise_warning",
    "subscribe",
    "start_thread",
    "run_bot",
    "on_stop",
    "close_event",
}

PANE_MEMBERS = {"__init__", "append", "block_count"}


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


def test_every_shipped_class_and_method_has_a_counterpart():
    """A class or a method exists on one side and nowhere on the other."""
    app()
    assert shipped_classes() == set(CLASS_MAP)
    assert len(CLASS_MAP) == 1
    found = {}
    for name in sorted(shipped_classes()):
        for member in members(getattr(shipped, name)):
            found["%s.%s" % (name, member)] = member
    assert set(found) == set(METHOD_MAP), sorted(set(found) ^ set(METHOD_MAP))
    assert len(METHOD_MAP) == 13
    for target in set(METHOD_MAP.values()) | set(CLASS_MAP.values()):
        assert callable(resolve(target)), target
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 28
    assert members(surface.LiveBotWindowModel) == WINDOW_MODEL_MEMBERS, sorted(
        members(surface.LiveBotWindowModel) ^ WINDOW_MODEL_MEMBERS
    )
    assert len(WINDOW_MODEL_MEMBERS) == 24
    assert members(surface.PaneModel) == PANE_MEMBERS, sorted(
        members(surface.PaneModel) ^ PANE_MEMBERS
    )
    assert declared_classes(WINDOW_PATH) == set(CLASS_MAP)


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    app()
    assert "_on_start" in members(shipped.LiteLiveBotWindow)
    assert "closeEvent" in members(shipped.LiteLiveBotWindow)
    assert "LiteLiveBotWindow" not in WINDOW_MODEL_MEMBERS
    with pytest.raises(AttributeError):
        resolve("LiveBotWindowModel.no_such_member")
    assert WINDOW_MODEL_MEMBERS - {"on_start"} != WINDOW_MODEL_MEMBERS
    assert members(surface.LiveBotWindowModel) - {"on_stop"} != WINDOW_MODEL_MEMBERS
    assert PANE_MEMBERS - {"append"} != PANE_MEMBERS
    assert set(METHOD_MAP) - {"LiteLiveBotWindow.__init__"} != set(METHOD_MAP)
    assert shipped_classes() - {"LiteLiveBotWindow"} != shipped_classes()


def test_the_module_level_entry_point_has_a_counterpart():
    """The standalone launcher exists on one side and nowhere on the other."""
    import inspect

    app()
    assert callable(shipped.main)
    assert list(inspect.signature(shipped.main).parameters) == []
    steps: list = []

    class FakeApp:
        def __init__(self, argv):
            steps.append(["app", len(argv)])

        def exec(self):
            steps.append(["exec"])
            return 7

    was_app = shipped.QApplication
    was_show = shipped.LiteLiveBotWindow.show
    was_bus = shipped.get_event_bus
    shipped.QApplication = FakeApp
    shipped.LiteLiveBotWindow.show = lambda self: steps.append(["show"])
    shipped.get_event_bus = lambda: RecordingBus()
    try:
        old_code = shipped.main()
    finally:
        shipped.QApplication = was_app
        shipped.LiteLiveBotWindow.show = was_show
        shipped.get_event_bus = was_bus
    assert old_code == 7
    assert [step[0] for step in steps] == ["app", "show", "exec"]

    new_steps: list = []

    class SurfaceApp:
        def exec(self):
            new_steps.append(["exec"])
            return 7

    new_code = surface.launch(SurfaceApp, show=lambda model: new_steps.append(["show"]))
    assert new_code == old_code
    assert [step[0] for step in new_steps] == ["show", "exec"]


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the window passes it."""
    import inspect

    app()
    assert list(
        inspect.signature(shipped.LiteLiveBotWindow._run_bot).parameters
    ) == list(inspect.signature(surface.LiveBotWindowModel.run_bot).parameters)
    assert list(
        inspect.signature(shipped.LiteLiveBotWindow._on_base_changed).parameters
    ) == list(inspect.signature(surface.LiveBotWindowModel.on_base_changed).parameters)
    assert list(inspect.signature(shipped.LiteLiveBotWindow._on_start).parameters) == [
        "self"
    ]
    assert list(inspect.signature(surface.LiveBotWindowModel.on_start).parameters) == [
        "self"
    ]
    assert list(inspect.signature(surface.view_model).parameters) == ["params"]


def modules_importing(module, skip=()):
    """Every file under src that imports the module named exactly `module`."""
    found = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if path in skip:
            continue
        names = []
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names += [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom):
                names.append(node.module or "")
        if any(name.split(".")[-1] == module for name in names):
            found.append(str(path))
    return found


def test_the_surface_is_reached_by_the_bridge():
    """The count of readers is wrong, so a lost reader would pass unseen."""
    assert modules_importing("live_bot_window_surface") == [
        str(REPO_ROOT / "src/core/desktop_bridge.py")
    ]
    assert modules_importing("live_bot_window", skip=(WINDOW_PATH, SURFACE_PATH)) == []
    known = modules_importing("event_bus")
    assert len(known) > 5, known


# ---------------------------------------------------------------------
# The surface holds its own values
# ---------------------------------------------------------------------


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_file(monkeypatch):
    """The surface reads the shipped file, so the comparison reads one side."""
    app()
    kept_pairs = {key: list(value) for key, value in surface.DEFAULT_PAIRS.items()}
    monkeypatch.setattr(
        shipped, "DEFAULT_PAIRS", {"USD": ["ZZZ"], "USDT": [], "USDC": [], "EUR": []}
    )
    monkeypatch.setattr(shipped, "get_event_bus", lambda: RecordingBus())
    holding_group_boxes(monkeypatch)
    moved = read_old(hold(shipped.LiteLiveBotWindow()))
    kept = read_new(surface.build_view_model(surface.LiveBotWindowModel()))
    assert moved["target_assets"] == ["ZZZ"]
    assert kept["target_assets"] == kept_pairs["USD"]
    differences = [
        key
        for key in sorted(set(moved) & set(kept))
        if readable(moved[key]) != readable(kept[key])
    ]
    assert differences == ["target_asset", "target_assets"], differences


def test_the_surface_carries_the_exchange_ids_the_connector_offers():
    """The surface offers an exchange the connector cannot reach."""
    from src.exchange.ccxt_connector import SUPPORTED_EXCHANGES

    assert list(surface.EXCHANGE_IDS) == sorted(SUPPORTED_EXCHANGES)
    assert surface.DEFAULT_EXCHANGE_ID in surface.EXCHANGE_IDS
    assert len(surface.EXCHANGE_IDS) > 1


def test_the_shipped_file_is_not_named_by_the_surface():
    """The surface reaches into the window it replaces."""
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    assert not any("live_bot_window" == name for name in imported), imported
    assert not any("scrumming_bot" in name for name in imported), imported
    assert not any("ccxt_connector" in name for name in imported), imported


# ---------------------------------------------------------------------
# The window paints, and the two sides paint the same pixels
# ---------------------------------------------------------------------

PICTURE_STEPS = {
    "at_rest": [],
    "running": [["credentials", "both"], ["start", ""]],
    "one_log_line": [["log", "buy"]],
    "one_fill_line": [["fill", "happy"]],
    "many_lines": [["log", "buy"], ["log", "quiet"], ["fill", "happy"]],
    "unicode_line": [["log", "unicode"]],
    "long_line": [["log", "long"]],
}


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def old_window_for_picture(name, monkeypatch):
    """One shipped window, whole, driven through one named case.

    The three panes and the button row are everything the operator
    sees. The configuration grid never reaches the screen, so nothing
    of it is in the frame on either side.
    """
    run = drive(PICTURE_STEPS[name], monkeypatch)
    return run["window"]


def model_payload(name, monkeypatch):
    """The surface's whole payload for one case, stamped as it comes off."""
    run = drive(PICTURE_STEPS[name], monkeypatch)
    return sealed(run["payload"])


def window_painted_by_the_model(payload):
    """One window built only from the surface's view model."""
    from PySide6.QtWidgets import (
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QMainWindow,
        QPlainTextEdit,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )

    payload = unaltered(payload)
    app()
    screen = hold(QWidget())
    root = QVBoxLayout(screen)
    group = QGroupBox(payload["config_group_title"])
    group_rows = QVBoxLayout(group)
    container = QWidget()
    rows = QVBoxLayout(container)
    button_row = QHBoxLayout()
    start = QPushButton(payload["start_label"])
    start.setEnabled(payload["start_enabled"])
    stop = QPushButton(payload["stop_label"])
    stop.setEnabled(payload["stop_enabled"])
    button_row.addWidget(start)
    button_row.addWidget(stop)
    button_row.addStretch()
    button_row.addWidget(QLabel(payload["status_text"]))
    rows.addLayout(button_row)
    group_rows.addWidget(container)
    root.addWidget(group)
    panes = QHBoxLayout()
    for index, key in enumerate(("console", "api", "activity")):
        found = payload[key]
        box = QGroupBox(found["title"])
        column = QVBoxLayout(box)
        pane = QPlainTextEdit()
        pane.setReadOnly(found["read_only"])
        pane.setLineWrapMode(QPlainTextEdit.NoWrap)
        pane.setStyleSheet(found["style_sheet"])
        pane.setMaximumBlockCount(found["max_blocks"])
        pane.appendPlainText(found["text"])
        column.addWidget(pane)
        panes.addWidget(box, payload["pane_stretches"][index])
    holder = QWidget()
    holder.setLayout(panes)
    root.addWidget(holder, payload["panes_root_stretch"])
    window = hold(QMainWindow())
    window.setAccessibleName(payload["accessible_name"])
    window.setWindowTitle(payload["window_title"])
    window.setCentralWidget(screen)
    return window


@pytest.mark.parametrize("name", sorted(PICTURE_CASES))
def test_the_two_sides_render_the_same_pixels(name, monkeypatch):
    """The surface paints a window the shipped window does not."""
    app()
    old_side = render_offscreen(old_window_for_picture(name, monkeypatch), PIXEL_SIZE)
    new_side = render_offscreen(
        window_painted_by_the_model(model_payload(name, monkeypatch)), PIXEL_SIZE
    )
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


def test_every_picture_case_is_driven(monkeypatch):
    """A picture case sits in the table that nothing ever paints."""
    assert set(PICTURE_CASES) == set(PICTURE_STEPS)
    for name in PICTURE_CASES:
        assert PICTURE_STEPS[name] is not None


def test_the_picture_check_reports_two_different_real_cases(monkeypatch):
    """The picture comparison passes whatever the surface paints."""
    app()
    assert_pictures_differ(
        old_side=render_offscreen(
            old_window_for_picture("at_rest", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            window_painted_by_the_model(model_payload("one_log_line", monkeypatch)),
            PIXEL_SIZE,
        ),
        note="an empty console against one line",
    )
    assert_pictures_differ(
        old_side=render_offscreen(
            old_window_for_picture("one_log_line", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            window_painted_by_the_model(model_payload("running", monkeypatch)),
            PIXEL_SIZE,
        ),
        note="one line against a running window",
    )
    assert_pictures_match(
        old_side=render_offscreen(
            old_window_for_picture("at_rest", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_offscreen(
            window_painted_by_the_model(model_payload("at_rest", monkeypatch)),
            PIXEL_SIZE,
        ),
        note="one case, both sides",
    )


def test_a_payload_changed_after_it_came_off_the_surface_is_refused(monkeypatch):
    """A render of a changed payload would measure the machine, not the product."""
    payload = model_payload("at_rest", monkeypatch)
    payload["status_text"] = "moved"
    with pytest.raises(AssertionError):
        window_painted_by_the_model(payload)
    with pytest.raises(AssertionError):
        window_painted_by_the_model({"status_text": ""})
    assert (
        window_painted_by_the_model(model_payload("at_rest", monkeypatch)) is not None
    )


def test_the_window_declares_no_skin_of_its_own(monkeypatch):
    """A colour the surface ships is one the window never paints.

    The rule the control applies is one neither side sets, so the
    difference it makes is the rule and not a value already there.
    """
    from tests.qt_pixel import render_widget

    app()
    assert surface.SKIN == {}
    assert surface.STYLE_SHEET == ""
    run = drive([], monkeypatch)
    assert run["window"].styleSheet() == ""
    assert run["window"].centralWidget().styleSheet() == ""
    assert "border" not in surface.PANE_STYLE
    skinned = window_painted_by_the_model(model_payload("at_rest", monkeypatch))
    skinned.setStyleSheet("QGroupBox { border: 3px solid #3a1414; }")
    assert_pictures_differ(
        old_side=render_widget(
            old_window_for_picture("at_rest", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_widget(skinned, PIXEL_SIZE),
        note="a rule the window does not set",
    )
    assert_pictures_match(
        old_side=render_widget(
            old_window_for_picture("at_rest", monkeypatch), PIXEL_SIZE
        ),
        new_side=render_widget(
            window_painted_by_the_model(model_payload("at_rest", monkeypatch)),
            PIXEL_SIZE,
        ),
        note="neither side carries a skin of its own",
    )


def test_the_window_size_is_compared_as_the_ask(monkeypatch):
    """The size the window was given differs between the two sides."""
    run = drive([], monkeypatch)
    assert run["window"].width() == surface.WINDOW_WIDTH == 1400
    assert run["window"].height() == surface.WINDOW_HEIGHT == 700


def test_the_platform_keeps_the_block_cap_the_pane_was_given():
    """The pane refused the cap it was given, so the ask is not the cap."""
    from PySide6.QtWidgets import QPlainTextEdit

    app()
    pane = QPlainTextEdit()
    pane.setMaximumBlockCount(surface.PANE_MAX_BLOCKS)
    assert pane.maximumBlockCount() == surface.PANE_MAX_BLOCKS
    pane.setMaximumBlockCount(-5)
    floor = pane.maximumBlockCount()
    assert floor <= 0, floor
    assert surface.PANE_MAX_BLOCKS > floor


def test_the_platform_lifts_the_target_box_into_its_own_range():
    """The target box keeps a value outside its range, so the range is empty.

    The value the box is given and the value it settles on are two
    different things. The box's own lift is pinned here; the surface
    carries the range that was asked for, not the settled value.
    """
    from PySide6.QtWidgets import QDoubleSpinBox

    app()
    box = QDoubleSpinBox()
    box.setRange(surface.TARGET_MIN, surface.TARGET_MAX)
    box.setDecimals(surface.TARGET_DECIMALS)
    box.setValue(surface.TARGET_DEFAULT)
    assert box.value() == surface.TARGET_DEFAULT
    box.setValue(-5.0)
    assert box.value() == surface.TARGET_MIN
    box.setValue(surface.TARGET_MAX * 1_000_000)
    assert box.value() == surface.TARGET_MAX
    box.setValue(1e-9)
    assert box.value() == surface.TARGET_MIN
    box.setValue(float("nan"))
    lifted_not_a_number = box.value()
    box.setValue(float("inf"))
    assert box.value() == surface.TARGET_MAX
    box.setValue(float("-inf"))
    assert box.value() == surface.TARGET_MIN
    assert lifted_not_a_number in (surface.TARGET_MIN, surface.TARGET_MAX)


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


# ---------------------------------------------------------------------
# What a picture cannot see
# ---------------------------------------------------------------------


def test_the_pane_look_is_compared_as_a_string(monkeypatch):
    """The three panes carry a different look on the two sides."""
    run = drive([], monkeypatch)
    for key in ("console", "api", "activity"):
        assert run["old"][key]["style_sheet"] == run["new"][key]["style_sheet"]
        assert run["old"][key]["style_sheet"] == surface.PANE_STYLE
    assert "Consolas" in surface.PANE_STYLE
    assert "#0e1420" in surface.PANE_STYLE


def test_the_pane_colours_are_compared_as_exact_text():
    """A swapped colour channel reads the same, so a wrong colour passes.

    Both colours are compared as text in one spelling. Each has three
    different channels, so a channel swap changes the text. Neither has
    equal channels, so neither is blind to a swap.
    """
    ground = "#0e1420"
    ink = "#c8d4e3"
    assert ground in surface.PANE_STYLE
    assert ink in surface.PANE_STYLE
    assert len({ground[1:3], ground[3:5], ground[5:7]}) == 3, ground
    assert len({ink[1:3], ink[3:5], ink[5:7]}) == 3, ink
    assert ground == ground.lower()
    assert ink == ink.lower()
    assert ground != ink


def test_the_read_only_mark_is_compared_as_a_value(monkeypatch):
    """A pane took typed text on one side and not the other."""
    run = drive([], monkeypatch)
    for key in ("console", "api", "activity"):
        assert run["old"][key]["read_only"] is run["new"][key]["read_only"] is True


def test_the_wrap_mode_is_compared_as_a_value(monkeypatch):
    """A pane wrapped a long line on one side and not the other."""
    run = drive([], monkeypatch)
    for key in ("console", "api", "activity"):
        assert run["old"][key]["wrap_mode"] == run["new"][key]["wrap_mode"]
        assert run["old"][key]["wrap_mode"] == surface.PANE_WRAP_MODE == "NoWrap"


def test_the_block_cap_is_compared_as_a_value(monkeypatch):
    """A pane kept a different number of lines on the two sides."""
    run = drive([], monkeypatch)
    for key in ("console", "api", "activity"):
        assert run["old"][key]["max_blocks"] == run["new"][key]["max_blocks"]
        assert run["old"][key]["max_blocks"] == surface.PANE_MAX_BLOCKS == 5000


def test_the_pane_cap_drops_the_oldest_line_on_both_sides():
    """A full pane dropped the wrong end, or kept growing."""
    from PySide6.QtWidgets import QPlainTextEdit

    app()
    pane = QPlainTextEdit()
    pane.setMaximumBlockCount(3)
    model = surface.PaneModel("Console", max_blocks=3)
    for index in range(6):
        line = "line%d" % index
        pane.appendPlainText(line)
        model.append(line)
    assert pane.toPlainText() == model.text
    assert pane.blockCount() == model.block_count() == 3
    assert model.text == "line3\nline4\nline5"


def test_the_echo_mode_is_compared_as_a_value(monkeypatch):
    """A credential field showed its text on one side and hid it on the other."""
    run = drive([], monkeypatch)
    assert run["old"]["key_echo_mode"] == run["new"]["key_echo_mode"]
    assert run["old"]["signature_echo_mode"] == run["new"]["signature_echo_mode"]
    assert surface.ECHO_MODE == "Password"


def test_the_pane_stretches_are_compared_as_values(monkeypatch):
    """The three panes take different widths on the two sides."""
    app()
    run = drive([], monkeypatch)
    root = run["window"].centralWidget().layout()
    panes = root.itemAt(1).widget().layout()
    assert [panes.stretch(index) for index in range(panes.count())] == list(
        surface.PANE_STRETCHES
    )
    assert [
        panes.itemAt(index).widget().title() for index in range(panes.count())
    ] == list(surface.PANE_TITLES)
    assert root.stretch(1) == surface.PANES_ROOT_STRETCH


def test_the_grid_places_every_control_the_same_way(monkeypatch):
    """A control sits in a different cell on the two sides."""
    app()
    monkeypatch.setattr(shipped, "get_event_bus", lambda: RecordingBus())
    held = holding_group_boxes(monkeypatch)
    hold(shipped.LiteLiveBotWindow())
    grid = held[surface.DROPPED_GROUP_INDEX].layout()
    placed = [list(grid.getItemPosition(index)) for index in range(grid.count())]
    declared = [[cell[1], cell[2], cell[3], cell[4]] for cell in surface.GRID_CELLS]
    assert placed == declared, (placed, declared)


def test_the_warning_words_are_compared_as_strings(monkeypatch):
    """A warning box carries different words on the two sides."""
    run = drive([["start", ""]], monkeypatch)
    both_sides_agree(run, "no credentials")
    assert run["old_warnings"] == [
        [surface.CREDENTIALS_TITLE, surface.CREDENTIALS_TEXT]
    ]
    assert "API key and secret" in surface.CREDENTIALS_TEXT
    empty = drive(
        [["credentials", "both"], ["base", "GBP"], ["clear_target", ""], ["start", ""]],
        monkeypatch,
    )
    assert empty["old_warnings"] == [
        [surface.SELECT_PAIR_TITLE, surface.SELECT_PAIR_TEXT]
    ]


def test_the_thread_the_window_hands_off_is_compared_as_values(monkeypatch):
    """The worker was handed a different pair, or a different name."""
    run = drive([["credentials", "padded"], ["start", ""]], monkeypatch)
    both_sides_agree(run, "padded credentials")
    assert run["old_threads"] == [
        {
            "args": [
                surface.DEFAULT_EXCHANGE_ID,
                surface.DEFAULT_BASE,
                "BTC",
                "BTC/USD",
                surface.TARGET_DEFAULT,
                API_KEY,
                API_SIGNATURE,
            ],
            "name": surface.THREAD_NAME,
            "daemon": True,
            "started": True,
        }
    ]


def test_the_topics_the_window_takes_are_compared_as_values(monkeypatch):
    """The window listened to a different set of topics on one side."""
    run = drive([["credentials", "both"], ["start", ""]], monkeypatch)
    assert run["old_topics"] == list(surface.BUS_TOPICS)
    assert run["new_topics"] == run["old_topics"]
    stopped = drive(SEQUENCES["start_then_stop"], monkeypatch)
    assert stopped["old_dropped"] == [], "no worker ran, so no topic is dropped"
    assert stopped["new_dropped"] == stopped["old_dropped"]


def test_the_recorded_steps_are_compared_as_values(monkeypatch):
    """The recorded steps are a list nothing reads, so a lost step is unseen."""
    run = drive([["log", "buy"], ["fill", "happy"]], monkeypatch)
    names = [call[0] for call in run["model"].calls]
    assert names.count(surface.LOG_SEEN) == 1
    assert names.count(surface.ACTIVITY_SEEN) == 1
    assert names.count(surface.FILL_SEEN) == 1
    assert surface.WINDOW_BUILT in names
    assert surface.PANES_BUILT in names
    assert surface.SIGNALS_WIRED in names
    assert run["payload"]["calls"] == [list(call) for call in run["model"].calls]


BLIND_TO_THE_PICTURE = {
    "pane look": "test_the_pane_look_is_compared_as_a_string",
    "pane colours": "test_the_pane_colours_are_compared_as_exact_text",
    "read-only mark": "test_the_read_only_mark_is_compared_as_a_value",
    "wrap mode": "test_the_wrap_mode_is_compared_as_a_value",
    "block cap": "test_the_block_cap_is_compared_as_a_value",
    "oldest line dropped": "test_the_pane_cap_drops_the_oldest_line_on_both_sides",
    "masked credentials": "test_the_echo_mode_is_compared_as_a_value",
    "pane widths": "test_the_pane_stretches_are_compared_as_values",
    "grid places": "test_the_grid_places_every_control_the_same_way",
    "warning words": "test_the_warning_words_are_compared_as_strings",
    "worker hand-off": "test_the_thread_the_window_hands_off_is_compared_as_values",
    "bus topics": "test_the_topics_the_window_takes_are_compared_as_values",
    "recorded steps": "test_the_recorded_steps_are_compared_as_values",
    "dropped controls": "test_the_shipped_window_drops_its_whole_configuration_group",
    "window size": "test_the_window_size_is_compared_as_the_ask",
    "refusal type": "test_a_refused_log_line_refuses_the_same_way_on_both_sides",
    "refusal wording": "test_the_refusal_reader_reports_two_different_wordings",
    "worker steps": "test_the_worker_does_the_same_thing_on_both_sides",
    "disconnect warning": "test_the_disconnect_warning_is_written_under_the_same_logger",
    "stop wait": "test_the_stop_button_asks_the_bot_to_stop_on_both_sides",
    "target box range": "test_the_platform_lifts_the_target_box_into_its_own_range",
    "entry point": "test_the_module_level_entry_point_has_a_counterpart",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    assert len(BLIND_TO_THE_PICTURE) == 22
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by


# ---------------------------------------------------------------------
# The surface writes under the logger it names
# ---------------------------------------------------------------------


def warnings_from(logger_name, run, level=logging.WARNING):
    """Every line one named logger emits while `run` is running.

    The handler is attached to the named logger, never through a capture
    fixture: this project's loggers do not pass their records up, so a
    fixture reading the root logger would see nothing. It is detached
    even when `run` refuses part way, and each record is flushed as it
    arrives.
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


def test_the_line_recorder_can_report():
    """The recorder sees nothing whatever the code says, so silence is empty."""
    said = warnings_from(
        surface.LOGGER_NAME,
        lambda: logging.getLogger(surface.LOGGER_NAME).warning("a seeded line"),
    )
    assert said == ["a seeded line"]
    quiet = warnings_from(surface.LOGGER_NAME, surface.LiveBotWindowModel)
    assert quiet == []
    survived = warnings_from(
        surface.LOGGER_NAME,
        lambda: [
            logging.getLogger(surface.LOGGER_NAME).warning("before the refusal"),
            surface.LiveBotWindowModel().run_bot(
                "coinbase", "USD", "BTC", "BTC/USD", 200.0, API_KEY, API_SIGNATURE
            ),
        ],
    )
    assert survived == ["before the refusal"]
    assert logging.getLogger(surface.LOGGER_NAME).handlers == []


def test_the_surface_writes_under_the_logger_it_names():
    """The surface writes under a name no operator log is collected from."""
    assert surface.LOGGER_NAME == "acervator.gui.live_bot"
    assert surface.logger.name == surface.LOGGER_NAME
    assert shipped.logger.name == surface.LOGGER_NAME


# ---------------------------------------------------------------------
# Every value reaches the compared snapshot
# ---------------------------------------------------------------------


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
        if isinstance(value, (surface.LiveBotWindowModel, logging.Logger)):
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
    warnings = RecordingWarnings()
    threads = RecordingThreads()
    for name in LOG_CASES:
        model = surface.LiveBotWindowModel()
        guarded(
            lambda model=model, name=name: model.on_bot_log(
                surface.BusEvent(surface.LOG_TOPIC, LOG_CASES[name])
            )
        )
        payloads.append(surface.build_view_model(model))
    for name in FILL_CASES:
        model = surface.LiveBotWindowModel()
        guarded(
            lambda model=model, name=name: model.on_trade_filled(
                surface.BusEvent(surface.FILL_TOPIC, FILL_CASES[name])
            )
        )
        payloads.append(surface.build_view_model(model))
    for name in API_CASES:
        topic, data = API_CASES[name]
        model = surface.LiveBotWindowModel()
        guarded(
            lambda model=model, topic=topic, data=data: model.on_api_event(
                surface.BusEvent(topic, data)
            )
        )
        payloads.append(surface.build_view_model(model))
    for base in BASE_CASES:
        model = surface.LiveBotWindowModel()
        model.choose_base(base)
        model.on_base_changed(base)
        payloads.append(surface.build_view_model(model))
    for exchange_id in EXCHANGE_CASES:
        model = surface.LiveBotWindowModel()
        model.choose_exchange(exchange_id)
        payloads.append(surface.build_view_model(model))
    for name, pair in CREDENTIALS.items():
        model = surface.LiveBotWindowModel(
            event_bus=RecordingBus(),
            warn=warnings.surface_warning,
            thread_factory=threads.surface_thread,
        )
        model.api_key, model.api_secret = pair
        model.on_start()
        model.on_start()
        payloads.append(surface.build_view_model(model))
    already_running = surface.LiveBotWindowModel(
        event_bus=RecordingBus(),
        warn=warnings.surface_warning,
        thread_factory=threads.surface_thread,
    )
    already_running.bot = Bot()
    already_running.on_start()
    already_running.press_start()
    already_running.press_stop()
    payloads.append(surface.build_view_model(already_running))
    picked = surface.LiveBotWindowModel()
    picked.choose_target_asset("ETH")
    picked.choose_target_asset("nope")
    picked.target_dollars = surface.TARGET_MAX
    payloads.append(surface.build_view_model(picked))
    stopped = surface.LiveBotWindowModel(stop_caller=StopWaiter())
    stopped.bot = Bot()
    stopped.loop = RunningLoop()
    stopped.unsubs = [lambda: None]
    stopped.on_stop()
    stopped.close_event()
    payloads.append(surface.build_view_model(stopped))
    failed_stop = surface.LiveBotWindowModel(stop_caller=StopWaiter(fail=True))
    failed_stop.bot = Bot()
    failed_stop.loop = RunningLoop()

    def refuse():
        raise RuntimeError("bus gone")

    failed_stop.unsubs = [refuse]
    failed_stop.on_stop()
    payloads.append(surface.build_view_model(failed_stop))
    for name in WORKER_CASES:
        spec = WORKER_CASES[name]
        model = surface.LiveBotWindowModel(
            exchange_factory=lambda exchange_id, spec=spec: NewExchange(
                exchange_id, spec.get("connect_error"), spec.get("disconnect_error")
            ),
            config_factory=lambda mode, spec=spec, **fields: (
                _raise(spec["config_error"])
                if spec.get("config_error") is not None
                else dict(fields, mode=str(mode))
            ),
            bot_factory=lambda cfg, exchange, spec=spec: (
                _raise(spec["bot_error"])
                if spec.get("bot_error") is not None
                else NewBot(cfg, exchange, spec.get("crash", False))
            ),
        )
        guarded(
            lambda model=model: model.run_bot(
                "coinbase", "USD", "BTC", "BTC/USD", 200.0, API_KEY, API_SIGNATURE
            )
        )
        payloads.append(surface.build_view_model(model))
    launched = surface.LiveBotWindowModel()
    launched.calls.append([surface.LAUNCHED, launched.window_title])
    payloads.append(surface.build_view_model(launched))
    unwired = surface.LiveBotWindowModel()
    guarded(
        lambda: unwired.run_bot(
            "coinbase", "USD", "BTC", "BTC/USD", 200.0, API_KEY, API_SIGNATURE
        )
    )
    payloads.append(surface.build_view_model(unwired))
    payloads.append(surface.build_view_model(surface.build_model()))
    capped_pane = surface.LiveBotWindowModel()
    capped_pane.console.max_blocks = surface.PANE_MAX_BLOCKS
    capped_pane.append_console(surface.NO_TEXT)
    payloads.append(surface.build_view_model(capped_pane))
    return payloads


def _raise(error):
    """Raise the refusal one worker case was built with."""
    raise error


COVERED_ELSEWHERE = {
    "PANE_MODEL": "test_importing_the_surface_builds_no_window",
    "LOGGER_NAME": "test_the_surface_writes_under_the_logger_it_names",
    "NOT_WIRED_FORMAT": "test_a_worker_with_nothing_wired_names_what_is_missing",
    "TARGET_MIN": "test_the_platform_lifts_the_target_box_into_its_own_range",
    "POLL_INTERVAL_S": "test_the_worker_waits_the_interval_the_window_names",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped window."""
    constants = surface_constants()
    assert len(constants) > 80, len(constants)
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    assert "ACTIVITY_KEYWORDS" in missing_from_payload(surface_constants(), thinned)
    assert "PANE_STYLE" in missing_from_payload(surface_constants(), thinned)


def test_a_worker_with_nothing_wired_names_what_is_missing():
    """A worker with no venue wired refused without saying what was absent."""
    model = surface.LiveBotWindowModel()
    with pytest.raises(TypeError) as reported:
        model.run_bot(
            "coinbase", "USD", "BTC", "BTC/USD", 200.0, API_KEY, API_SIGNATURE
        )
    assert "exchange_factory" in str(reported.value)
    assert surface.NOT_WIRED_FORMAT.format(name="exchange_factory") in str(
        reported.value
    )
    assert surface.wired(len, "counter") is len


def test_the_worker_waits_the_interval_the_window_names(monkeypatch):
    """The worker polls at a different rate than the window names.

    The wait is read off the running worker, never off the file. The
    bot is asked to stop on the first wait, so the worker takes exactly
    one turn.
    """
    import asyncio
    import threading as real_threading

    app()
    window = old_window(
        monkeypatch, RecordingBus(), RecordingWarnings(), RecordingThreads()
    )
    waits: list = []
    running_bot: list = []
    real_sleep = asyncio.sleep

    class PollingBot:
        def __init__(self, config, exchange):
            self._stop_event = real_threading.Event()
            running_bot.append(self)

        async def start(self):
            return None

    async def watch_sleep(seconds):
        waits.append(seconds)
        running_bot[0]._stop_event.set()
        return await real_sleep(0)

    monkeypatch.setattr(shipped, "CCXTConnector", OldExchange)
    monkeypatch.setattr(shipped, "make_bot_config", lambda mode, **fields: dict(fields))
    monkeypatch.setattr(shipped, "ScrummingBot", PollingBot)
    monkeypatch.setattr(
        shipped, "BotMode", types.SimpleNamespace(SCRUMMING="SCRUMMING")
    )
    monkeypatch.setattr(asyncio, "sleep", watch_sleep)
    window._run_bot("coinbase", "USD", "BTC", "BTC/USD", 200.0, API_KEY, API_SIGNATURE)
    assert waits == [surface.POLL_INTERVAL_S], waits
    assert surface.POLL_INTERVAL_S == 1.0


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "accessible_name": ("model.accessible_name",),
    "window_title": ("model.window_title",),
    "window_width": ("model.window_width",),
    "window_height": ("model.window_height",),
    "config_group_title": ("CONFIG_GROUP_TITLE",),
    "config_groups_built": ("CONFIG_GROUPS_BUILT",),
    "dropped_group_index": ("DROPPED_GROUP_INDEX",),
    "controls_reach_the_window": ("model.controls_reach_the_window",),
    "live_item_names": ("LIVE_ITEM_NAMES",),
    "dropped_item_names": ("DROPPED_ITEM_NAMES",),
    "grid_cells": ("GRID_CELLS",),
    "exchange_label": ("EXCHANGE_LABEL",),
    "base_label": ("BASE_LABEL",),
    "target_label": ("TARGET_LABEL",),
    "target_dollars_label": ("TARGET_DOLLARS_LABEL",),
    "credential_labels": ("CREDENTIAL_LABELS",),
    "credential_fields": ("CREDENTIAL_FIELDS",),
    "not_wired_format": ("NOT_WIRED_FORMAT",),
    "exchange_ids": ("model.exchange_ids",),
    "exchange_id": ("model.exchange_id",),
    "default_exchange_id": ("DEFAULT_EXCHANGE_ID",),
    "bases": ("model.bases",),
    "base": ("model.base",),
    "default_base": ("DEFAULT_BASE",),
    "default_pairs": ("DEFAULT_PAIRS",),
    "target_assets": ("model.target_assets",),
    "target_asset": ("model.target_asset",),
    "no_target_asset": ("NO_TARGET_ASSET",),
    "target_dollars": ("model.target_dollars",),
    "target_min": ("TARGET_MIN",),
    "target_max": ("TARGET_MAX",),
    "target_decimals": ("TARGET_DECIMALS",),
    "target_default": ("TARGET_DEFAULT",),
    "target_step": ("TARGET_STEP",),
    "echo_mode": ("ECHO_MODE",),
    "api_key": ("model.api_key",),
    "api_secret": ("model.api_secret",),
    "no_credential": ("NO_CREDENTIAL",),
    "start_label": ("START_LABEL",),
    "stop_label": ("STOP_LABEL",),
    "start_enabled": ("model.start_enabled",),
    "stop_enabled": ("model.stop_enabled",),
    "start_enabled_at_rest": ("START_ENABLED_AT_REST",),
    "stop_enabled_at_rest": ("STOP_ENABLED_AT_REST",),
    "status_text": ("model.status_text",),
    "status_idle": ("STATUS_IDLE",),
    "status_running_format": ("STATUS_RUNNING_FORMAT",),
    "pane_titles": ("PANE_TITLES",),
    "pane_stretches": ("PANE_STRETCHES",),
    "panes_root_stretch": ("PANES_ROOT_STRETCH",),
    "pane_read_only": ("PANE_READ_ONLY",),
    "pane_wrap_mode": ("PANE_WRAP_MODE",),
    "pane_max_blocks": ("PANE_MAX_BLOCKS",),
    "pane_style": ("PANE_STYLE",),
    "no_text": ("NO_TEXT",),
    "one_block": ("ONE_BLOCK",),
    "block_separator": ("BLOCK_SEPARATOR",),
    "console": ("model.console",),
    "api": ("model.api",),
    "activity": ("model.activity",),
    "console_title": ("CONSOLE_TITLE",),
    "api_title": ("API_TITLE",),
    "activity_title": ("ACTIVITY_TITLE",),
    "bus_topics": ("BUS_TOPICS",),
    "log_topic": ("LOG_TOPIC",),
    "fill_topic": ("FILL_TOPIC",),
    "request_topic": ("REQUEST_TOPIC",),
    "response_topic": ("RESPONSE_TOPIC",),
    "subscribed": ("model.subscribed",),
    "message_key": ("MESSAGE_KEY",),
    "no_message": ("NO_MESSAGE",),
    "activity_keywords": ("ACTIVITY_KEYWORDS",),
    "side_key": ("SIDE_KEY",),
    "symbol_key": ("SYMBOL_KEY",),
    "amount_key": ("AMOUNT_KEY",),
    "price_key": ("PRICE_KEY",),
    "unknown_field": ("UNKNOWN_FIELD",),
    "no_amount": ("NO_AMOUNT",),
    "no_price": ("NO_PRICE",),
    "already_running_text": ("ALREADY_RUNNING_TEXT",),
    "select_pair_title": ("SELECT_PAIR_TITLE",),
    "select_pair_text": ("SELECT_PAIR_TEXT",),
    "credentials_title": ("CREDENTIALS_TITLE",),
    "credentials_text": ("CREDENTIALS_TEXT",),
    "warnings": ("model.warnings",),
    "starting_format": ("STARTING_FORMAT",),
    "connected_format": ("CONNECTED_FORMAT",),
    "connect_failed_format": ("CONNECT_FAILED_FORMAT",),
    "bot_crashed_format": ("BOT_CRASHED_FORMAT",),
    "disconnect_failed_log": ("DISCONNECT_FAILED_LOG",),
    "stopping_text": ("STOPPING_TEXT",),
    "stop_error_format": ("STOP_ERROR_FORMAT",),
    "stopped_text": ("STOPPED_TEXT",),
    "thread_name": ("THREAD_NAME",),
    "thread_daemon": ("THREAD_DAEMON",),
    "bot_thread_held": ("model.bot_thread",),
    "threads": ("model.threads",),
    "stop_timeout_s": ("STOP_TIMEOUT_S",),
    "poll_interval_s": ("POLL_INTERVAL_S",),
    "bot_mode_name": ("BOT_MODE_NAME",),
    "symbol_format": ("SYMBOL_FORMAT",),
    "bot_built": ("model.bot",),
    "exchange_built": ("model.exchange",),
    "subscriptions_held": ("model.unsubs",),
    "skin": ("SKIN",),
    "style_sheet": ("STYLE_SHEET",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "signal_names": ("SIGNAL_NAMES",),
    "actions": ("ACTIONS",),
    "logger_name": ("LOGGER_NAME",),
    "calls": ("model.calls",),
}

FREE_SHAPE_KEYS = ("calls", "grid_cells")
HELD_KEYS = ("bot_built", "exchange_built", "bot_thread_held")
COUNT_KEYS = ("subscriptions_held",)


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("model."):
        found = getattr(model, name.split(".", 1)[1])
        return found() if callable(found) else found
    return getattr(surface, name)


def backed(key, value, sources, model):
    """Whether one payload key carries exactly what its named sources hold."""
    resolved = resolve_source(sources[0], model)
    if isinstance(resolved, surface.PaneModel):
        return freeze(value) == freeze(surface.pane_view(resolved))
    if key in HELD_KEYS:
        return value is (resolved is not None)
    if key in COUNT_KEYS:
        return value == len(resolved)
    if key in FREE_SHAPE_KEYS:
        return len(value) == len(resolved)
    return freeze(value) == freeze(resolved)


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model = surface.LiveBotWindowModel()
    payload = surface.build_view_model(model)
    assert set(payload) == set(PAYLOAD_KEY_SOURCES), sorted(
        set(payload) ^ set(PAYLOAD_KEY_SOURCES)
    )
    fresh = surface.LiveBotWindowModel()
    surface.build_view_model(fresh)
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(fresh, name.split(".", 1)[1]), name
            else:
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, fresh), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = surface.LiveBotWindowModel()
    payload = surface.build_view_model(model)
    assert backed("start_label", payload["start_label"], ("START_LABEL",), model)
    assert not backed("start_label", "GO", ("START_LABEL",), model)
    assert not backed("pane_titles", ["Console"], ("PANE_TITLES",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("console", {}, ("model.console",), model)
    assert not backed("bot_built", True, ("model.bot",), model)
    assert not backed("subscriptions_held", 4, ("model.unsubs",), model)


# ---------------------------------------------------------------------
# What each side keeps between windows
# ---------------------------------------------------------------------


def drive_one_window(name):
    """Build one real window, take one log case, destroy the window."""
    window = shipped.LiteLiveBotWindow()
    outcome = guarded(
        lambda: window._on_bot_log(event(surface.LOG_TOPIC, LOG_CASES[name]))
    )
    destroy(window)
    return outcome


def test_the_shipped_module_changes_no_value_the_next_window_reads(monkeypatch):
    """One window left a changed value behind for the next one."""
    app()
    monkeypatch.setattr(shipped, "get_event_bus", lambda: RecordingBus())
    before = module_values(shipped)
    for name in list(LOG_CASES)[:5]:
        assert drive_one_window(name) == {"error": ""}
    after = module_values(shipped)
    assert after == before, {
        name: (before.get(name), after.get(name))
        for name in set(before) | set(after)
        if before.get(name) != after.get(name)
    }


def test_the_module_state_check_reports_a_value_a_window_changed(monkeypatch):
    """The module-state check passes whatever a window leaves behind."""
    app()
    monkeypatch.setattr(shipped, "get_event_bus", lambda: RecordingBus())
    monkeypatch.setattr(shipped, "DEFAULT_PAIRS", dict(shipped.DEFAULT_PAIRS))

    def leaking_log(self, incoming):
        shipped.DEFAULT_PAIRS["USD"] = ["a pair one window left behind"]
        self.txt_console.appendPlainText(incoming.data.get("message", ""))

    monkeypatch.setattr(shipped.LiteLiveBotWindow, "_on_bot_log", leaking_log)
    before = module_values(shipped)
    for name in list(LOG_CASES)[:5]:
        assert drive_one_window(name) == {"error": ""}
    after = module_values(shipped)
    assert set(after) == set(before), sorted(set(after) ^ set(before))
    assert after != before, "a window changed DEFAULT_PAIRS and no read value moved"
    assert after["DEFAULT_PAIRS"] != before["DEFAULT_PAIRS"]


def test_the_shipped_window_writes_to_the_process_wide_event_bus(monkeypatch):
    """The window reaches no shared object, so no test can disturb another."""
    from src.core.event_bus import get_event_bus

    app()
    live = get_event_bus()
    assert shipped.get_event_bus() is live
    taken = RecordingBus()
    monkeypatch.setattr(shipped, "get_event_bus", lambda: taken)
    window = hold(shipped.LiteLiveBotWindow())
    assert window._bus is taken
    assert window._bus is not live


def test_the_surface_keeps_no_value_between_two_windows():
    """One window left a changed value behind for the next one."""
    first = surface.LiveBotWindowModel()
    first.append_console("a line")
    first.calls.append(["a step only the first window took"])
    second = surface.LiveBotWindowModel()
    assert second.console.text == surface.NO_TEXT
    assert first.console.text == "a line"
    assert second.calls != first.calls
    assert first.calls[-1] not in second.calls
    assert first.calls is not second.calls
    assert first.console is not second.console
    assert surface.DEFAULT_PAIRS["USD"] == (
        "BTC",
        "ETH",
        "SOL",
        "ADA",
        "AVAX",
        "DOT",
        "BONK",
        "PEPE",
        "WIF",
    )


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


def test_view_model_is_json_serialisable():
    """The renderer cannot read a payload the bridge cannot encode."""
    model = surface.LiveBotWindowModel()
    model.append_console("a line")
    payload = surface.build_view_model(model)
    text = json.dumps(payload)
    assert json.loads(text)["method"] == surface.METHOD
    assert len(text) > 1000


def test_the_bridge_registers_the_live_bot_window_method():
    """The renderer cannot reach the live bot window over the bridge."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    assert surface.METHOD in registered
    assert surface.METHOD == "live_bot_window.state"
    assert registered[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 4, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )
    assert answer["ok"] is True
    assert answer["result"]["start_label"] == surface.START_LABEL


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
    assert "live_bot_window_surface" in names
    assert names.index("launcher_surface") + 1 == names.index("live_bot_window_surface")


def test_the_bridge_keeps_the_window_until_a_reset():
    """The window forgot its text between two calls, or kept it past a reset."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 5, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({"reset": True})
    filled = ask({"log": {"message": "BUY 1 BTC"}})
    assert filled["console"]["text"] == "BUY 1 BTC"
    assert ask({})["console"]["text"] == "BUY 1 BTC"
    assert ask({"reset": True})["console"]["text"] == surface.NO_TEXT
    assert surface.PANE_MODEL.console.text == surface.NO_TEXT


def test_the_bridge_reports_a_state_it_cannot_read():
    """A broken request answered as if it had worked."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 6,
                "method": surface.METHOD,
                "params": {"reset": True, "log": {"message": 5}},
            }
        ),
        registered,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "AttributeError"
    desktop_bridge.handle_line(
        json.dumps({"id": 7, "method": surface.METHOD, "params": {"reset": True}}),
        registered,
    )


def test_the_bridge_drives_every_step_the_window_takes():
    """A step the renderer sends never reaches the window."""
    from src.core import desktop_bridge

    registered = desktop_bridge.build_registry()

    def ask(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 8, "method": surface.METHOD, "params": params}),
            registered,
        )["result"]

    ask({"reset": True})
    picked = ask(
        {
            "exchange_id": "kraken",
            "base": "USDC",
            "target_asset": "SOL",
            "target_dollars": 350.0,
            "api_key": API_KEY,
            "api_secret": API_SIGNATURE,
        }
    )
    assert picked["exchange_id"] == "kraken"
    assert picked["base"] == "USDC"
    assert picked["target_asset"] == "SOL"
    lined = ask({"log": {"message": "sell 1 SOL"}, "fill": FILL_CASES["happy"]})
    assert "sell 1 SOL" in lined["console"]["text"]
    assert lined["activity"]["text"].startswith("sell 1 SOL")
    answered = ask({"api_event": {"method": "fetch_ticker"}})
    assert answered["api"]["text"].startswith("[exchange.request]")
    running = ask({"start": True})
    assert running["status_text"] == "Status: running SOL/USDC"
    assert running["subscribed"] == list(surface.BUS_TOPICS)
    quiet = ask({"stop": True})
    assert (
        quiet["status_text"] == running["status_text"]
    ), "no worker ran over the bridge, so the window keeps its running line"
    assert surface.STOPPING_TEXT not in quiet["console"]["text"]
    ask({"close": True})
    ask({"reset": True})


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
    "json.dumps({'id': 1, 'method': 'live_bot_window.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = BLOCK_QT + (
    "import json, sys\n"
    "from src.gui.main_tabs import live_bot_window_surface as s\n"
    "model = s.build_model()\n"
    "model.choose_base('USDC')\n"
    "model.choose_target_asset('SOL')\n"
    "model.on_bot_log(s.BusEvent(s.LOG_TOPIC, {'message': 'BUY 1 SOL'}))\n"
    "model.on_trade_filled(s.BusEvent(s.FILL_TOPIC,\n"
    "    {'side': 'buy', 'symbol': 'SOL/USDC', 'amount': 0.5, 'price': 100.0}))\n"
    "model.on_api_event(s.BusEvent(s.REQUEST_TOPIC, {'method': 'fetch_ticker'}))\n"
    "payload = s.build_view_model(model)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'title': payload['window_title'],\n"
    "    'start_label': payload['start_label'],\n"
    "    'status': payload['status_text'],\n"
    "    'pane_style': payload['pane_style'],\n"
    "    'panes': payload['pane_titles'],\n"
    "    'base': payload['base'],\n"
    "    'target_asset': payload['target_asset'],\n"
    "    'console': payload['console']['text'],\n"
    "    'activity': payload['activity']['text'],\n"
    "    'api': payload['api']['text'],\n"
    "    'topics': payload['bus_topics'],\n"
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
    """Reaching the live bot window pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == surface.METHOD
    assert result["start_label"] == surface.START_LABEL
    assert result["console"]["text"] == surface.NO_TEXT
    assert result["status_text"] == surface.STATUS_IDLE


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_builds_the_window_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["title"] == surface.WINDOW_TITLE
    assert answered["start_label"] == surface.START_LABEL
    assert answered["status"] == surface.STATUS_IDLE
    assert answered["pane_style"] == surface.PANE_STYLE
    assert answered["panes"] == list(surface.PANE_TITLES)
    assert answered["base"] == "USDC"
    assert answered["target_asset"] == "SOL"
    assert answered["console"] == "BUY 1 SOL"
    assert answered["activity"].splitlines() == [
        "BUY 1 SOL",
        "FILL: BUY 0.500000 SOL/USDC @ $100.00000000",
    ]
    assert answered["api"].startswith("[exchange.request]")
    assert answered["topics"] == list(surface.BUS_TOPICS)
    assert answered["calls"] > 3


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_builds_the_window():
    """The Qt block let the shipped window through."""
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui import live_bot_window as w\n"
        "    out = {'imported': True, 'window': hasattr(w, 'LiteLiveBotWindow')}\n"
        "except Exception as exc:\n"
        "    out = {'imported': False, 'error': type(exc).__name__,\n"
        "        'headline': str(exc)}\n"
        "print(json.dumps(out))\n"
    )
    answered = run_script(probe)
    assert answered["imported"] is False
    assert answered["error"] == "ImportError"
    assert answered["headline"] == "PySide6 blocked"


SETTINGS_PROBE = """
import json
import os
import shutil
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-live-bot-probe-'))
at_import = root / 'at-import'
on_request = root / 'on-request'
at_import.mkdir()
on_request.mkdir()
os.environ['ACERVATOR_SETTINGS_ROOT'] = str(at_import)

from src.gui.main_tabs import live_bot_window_surface as s

built_at_import = s.PANE_MODEL is not None
read_at_import = sorted(p.name for p in at_import.iterdir())

os.environ['ACERVATOR_SETTINGS_ROOT'] = str(on_request)
model = s.pane_model()

from src.core.privacy_mask_registry import PrivacyMaskRegistry

control = PrivacyMaskRegistry()
answer = {'built_at_import': built_at_import,
          'built_on_request': model is s.PANE_MODEL,
          'title': model.window_title,
          'at_import_files': read_at_import,
          'files_after_request': sorted(p.name for p in at_import.iterdir()),
          'on_request_files': sorted(p.name for p in on_request.iterdir()),
          'control_points_at': str(control.settings_path),
          'on_request_root': str(on_request)}
shutil.rmtree(root, ignore_errors=True)
print(json.dumps(answer))
"""


def test_importing_the_surface_builds_no_window():
    """Loading the surface built a window before anything asked for one.

    The settings root is aimed at one folder while the surface is
    imported and at a second folder before the first request. The
    surface leaves both folders untouched, and a register built after
    the switch points at the second folder, which is what proves the
    probe can tell the two apart.
    """
    answered = run_script(SETTINGS_PROBE)
    assert answered["built_at_import"] is False, answered
    assert answered["built_on_request"] is True, answered
    assert answered["title"] == surface.WINDOW_TITLE, answered
    assert answered["at_import_files"] == [], answered
    assert answered["files_after_request"] == [], answered
    assert answered["on_request_files"] == [], answered
    assert answered["control_points_at"].startswith(answered["on_request_root"])


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
    window_imports = {
        (node.module or "")
        for node in ast.walk(ast.parse(WINDOW_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in window_imports), window_imports


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
