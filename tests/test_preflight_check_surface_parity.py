"""The shipped pre-flight check and the Qt-free surface, side by side.

A failure means the view model returns a different result, writes a
different report line, raises a different message box, offers different
buttons, writes a different status line or ends the wizard gate a
different way than ``check_symbol``, ``format_result_for_user`` and the
message boxes the bot wizard raises over them.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import preflight_check as shipped
from src.gui.main_tabs import preflight_check_surface as surface
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

LOGGER_NAME = "acervator.preflight"

PIXEL_SIZE = (640, 480)
TALL_PIXEL_SIZE = (640, 640)

CLICKED_SIGNAL = "2clicked()"

CHECK = "check"
GATE = "gate"

CLOCK_START = 100.0
CLOCK_STEP = 0.25

CALLS: list[list] = []

# The gate literals, typed independently of the surface, so the two
# sides cannot agree by definition.
CALLER_FAILURE_TITLE = "Pre-flight check failed"
CALLER_WARNING_TITLE = "Pre-flight check — warnings"
CALLER_FAILURE_BODY = "{}\n\nBot creation aborted."
CALLER_WARNING_BODY = "{}\n\nProceed with bot creation?"
CALLER_BLOCKED_LOG = "Pre-flight FAILED for {} on {}: {}"
CALLER_DECLINED_LOG = "Bot creation declined at pre-flight ({} warning(s))"
CALLER_PROCEED_LOG = "Pre-flight OK for {} on {} ({} ms)"
CALLER_SKIP_LOG = (
    "Pre-flight skipped (Extractor mode is multi-pair; symbol "
    "validation deferred to runtime watch-list refresh)"
)
CALLER_MODULE_MISSING_LOG = "Pre-flight check skipped (module unavailable)"
CALLER_ERRORED_LOG = "Pre-flight check errored: {}: {} — continuing anyway"
# Qt plain text format, so a symbol carrying tags reaches the operator whole.
CALLER_TEXT_FORMAT_VALUE = 0

FULL_MARKET = {
    "active": True,
    "limits": {"amount": {"min": 0.01}, "cost": {"min": 1.0}},
    "precision": {"price": 1e-06, "amount": 1e-08},
}
INACTIVE_MARKET = {
    "active": False,
    "limits": {"amount": {"min": 0.01}, "cost": {"min": 1.0}},
    "precision": {"price": 1e-06, "amount": 1e-08},
}
BARE_MARKET = {
    "active": True,
    "limits": {"amount": {"min": 0.0}, "cost": {"min": 0.0}},
    "precision": {},
}
NEGATIVE_MARKET = {
    "active": True,
    "limits": {"amount": {"min": -0.5}, "cost": {"min": -1.0}},
    "precision": {"price": 1e-06, "amount": 1e-08},
}
HUGE_MARKET = {
    "active": True,
    "limits": {"amount": {"min": 1e15}, "cost": {"min": 1e15}},
    "precision": {"price": 1e-12, "amount": 1e-12},
}
EMPTY_LIMITS_MARKET = {"active": True, "limits": None, "precision": None}
NO_ACTIVE_FLAG_MARKET = {
    "limits": {"amount": {"min": 0.01}, "cost": {"min": 1.0}},
    "precision": {"price": 1e-06, "amount": 1e-08},
}

TICK_SIZE_MODE = 4
DECIMAL_PLACES_MODE = 2
SIGNIFICANT_DIGITS_MODE = 3

PAIR = "RAVE/USD"
UNICODE_PAIR = "Δ→⚡/USD"
MARKUP_PAIR = "<b>BTC</b>/USD"
LONG_SYMBOL = "X" * 200


class RaisingConfig:
    """A wizard config whose first read raises a named error."""

    def __init__(self, error):
        self.error = error

    def get(self, name, default=None):
        raise self.error


class FakeExchange:
    """A ccxt exchange whose two calls are recorded and steerable."""

    markets: dict = {}
    ticker: dict = {}
    load_error = None
    ticker_error = None
    precisionMode = TICK_SIZE_MODE

    def __init__(self, config):
        self.config = dict(config)
        CALLS.append([surface.CONFIG_BUILD, sorted(self.config)])
        CALLS.append([surface.EXCHANGE_CREATE, self.config.get("timeout")])

    def load_markets(self):
        if type(self).load_error is not None:
            raise type(self).load_error
        CALLS.append([surface.MARKETS_LOAD, len(type(self).markets)])
        return dict(type(self).markets)

    def fetch_ticker(self, symbol):
        if type(self).ticker_error is not None:
            raise type(self).ticker_error
        CALLS.append([surface.TICKER_FETCH, symbol])
        return dict(type(self).ticker)


def install_ccxt(monkeypatch, spec):
    """Put one steerable ccxt module in place of the real one."""
    if spec.get("no_ccxt"):
        monkeypatch.setitem(sys.modules, "ccxt", None)
        return
    module = types.ModuleType("ccxt")
    exchange = type(
        "SpecExchange",
        (FakeExchange,),
        {
            "markets": spec.get("markets", {}),
            "ticker": spec.get("ticker", {}),
            "load_error": spec.get("load_error"),
            "ticker_error": spec.get("ticker_error"),
            "precisionMode": spec.get("precision_mode", TICK_SIZE_MODE),
        },
    )
    for name in spec.get("exchanges", ("coinbase",)):
        setattr(module, name, exchange)
    monkeypatch.setitem(sys.modules, "ccxt", module)


def freeze_clock(monkeypatch):
    """Both sides read the same monotonic clock, one step per reading."""
    state = {"now": CLOCK_START}

    def tick():
        state["now"] += CLOCK_STEP
        return state["now"]

    monkeypatch.setattr(time, "monotonic", tick)
    return state


CASES = {
    "happy": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", PAIR, 500.0),
    },
    "thin_capital": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", PAIR, 2.0),
    },
    "inactive_market": {
        "spec": {"markets": {PAIR: INACTIVE_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", PAIR, 500.0),
    },
    "two_warnings": {
        "spec": {"markets": {PAIR: INACTIVE_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", PAIR, 2.0),
    },
    "no_ccxt": {
        "spec": {"no_ccxt": True},
        "args": ("coinbase", PAIR, 500.0),
    },
    "unknown_exchange": {
        "spec": {"markets": {PAIR: FULL_MARKET}},
        "args": ("notanexchange", PAIR, 500.0),
    },
    "empty_exchange": {
        "spec": {"markets": {PAIR: FULL_MARKET}},
        "args": ("", PAIR, 500.0),
    },
    "symbol_casing": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", "rave/usd", 500.0),
    },
    "symbol_dash": {
        "spec": {"markets": {"RAVE-USD": FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", "RAVE/USD", 500.0),
    },
    "symbol_slash": {
        "spec": {"markets": {"RAVE/USD": FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", "RAVE-USD", 500.0),
    },
    "symbol_missing": {
        "spec": {"markets": {PAIR: FULL_MARKET}},
        "args": ("coinbase", "ZZZ/USD", 500.0),
    },
    "empty_symbol": {
        "spec": {"markets": {PAIR: FULL_MARKET}},
        "args": ("coinbase", "", 500.0),
    },
    "no_markets": {
        "spec": {"markets": {}},
        "args": ("coinbase", PAIR, 500.0),
    },
    "load_raises": {
        "spec": {
            "markets": {PAIR: FULL_MARKET},
            "load_error": RuntimeError("venue refused the market list"),
        },
        "args": ("coinbase", PAIR, 500.0),
    },
    "ticker_raises": {
        "spec": {
            "markets": {PAIR: FULL_MARKET},
            "ticker_error": RuntimeError("ticker endpoint is down"),
        },
        "args": ("coinbase", PAIR, 500.0),
    },
    "ticker_blank": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": None}},
        "args": ("coinbase", PAIR, 500.0),
    },
    "zero_balance": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", PAIR, 0.0),
    },
    "zero_limits": {
        "spec": {"markets": {PAIR: BARE_MARKET}, "ticker": {"last": 0.0}},
        "args": ("coinbase", PAIR, 500.0),
    },
    "empty_limits": {
        "spec": {"markets": {PAIR: EMPTY_LIMITS_MARKET}, "ticker": {}},
        "args": ("coinbase", PAIR, 500.0),
    },
    "no_active_flag": {
        "spec": {
            "markets": {PAIR: NO_ACTIVE_FLAG_MARKET},
            "ticker": {"last": 0.0123},
        },
        "args": ("coinbase", PAIR, 500.0),
    },
    "negative_balance": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", PAIR, -50.0),
    },
    "negative_limits": {
        "spec": {"markets": {PAIR: NEGATIVE_MARKET}, "ticker": {"last": -0.5}},
        "args": ("coinbase", PAIR, 500.0),
    },
    "very_large": {
        "spec": {"markets": {PAIR: HUGE_MARKET}, "ticker": {"last": 1e12}},
        "args": ("coinbase", PAIR, 1e18),
    },
    "unicode_symbol": {
        "spec": {"markets": {UNICODE_PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", UNICODE_PAIR, 500.0),
    },
    "long_symbol": {
        "spec": {"markets": {LONG_SYMBOL: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", LONG_SYMBOL, 500.0),
    },
    "markup_symbol": {
        "spec": {"markets": {MARKUP_PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", MARKUP_PAIR, 500.0),
    },
    "unknown_input": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", PAIR, "not-a-number"),
    },
    "decimal_places_mode": {
        "spec": {
            "markets": {PAIR: {"active": True, "precision": {"price": 8, "amount": 6}}},
            "ticker": {"last": 0.0123},
            "precision_mode": DECIMAL_PLACES_MODE,
        },
        "args": ("coinbase", PAIR, 500.0),
    },
    "significant_digits_mode": {
        "spec": {
            "markets": {PAIR: {"active": True, "precision": {"price": 8, "amount": 6}}},
            "ticker": {"last": 0.0123},
            "precision_mode": SIGNIFICANT_DIGITS_MODE,
        },
        "args": ("coinbase", PAIR, 500.0),
    },
    "credentials": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", PAIR, 500.0, "key-1", "secret-1", "phrase-1"),
    },
    "partial_credentials": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "args": ("coinbase", PAIR, 500.0, "key-1", "", ""),
    },
}

NO_EXCHANGE_CASES = ("no_ccxt", "unknown_exchange", "empty_exchange")

FAILING_CASES = (
    "no_ccxt",
    "unknown_exchange",
    "empty_exchange",
    "symbol_casing",
    "symbol_dash",
    "symbol_slash",
    "symbol_missing",
    "empty_symbol",
    "no_markets",
    "load_raises",
    "unknown_input",
)

WARNING_CASES = (
    "thin_capital",
    "inactive_market",
    "two_warnings",
    "zero_balance",
    "negative_balance",
)

GATE_CONFIG = {
    "exchange_id": "coinbase",
    "target_asset": "RAVE",
    "base_currency": "USD",
    "target_balance": 500.0,
}

GATE_CASES = {
    "proceed": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "config": dict(GATE_CONFIG),
    },
    "warned": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "config": {**GATE_CONFIG, "target_balance": 2.0},
    },
    "blocked": {
        "spec": {"markets": {"ZZZ/USD": FULL_MARKET}},
        "config": dict(GATE_CONFIG),
    },
    "extractor": {
        "spec": {"markets": {PAIR: FULL_MARKET}},
        "config": {**GATE_CONFIG, "mode": "extractor"},
    },
    "investment_amount": {
        "spec": {"markets": {PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "config": {
            "exchange_id": "coinbase",
            "target_asset": "RAVE",
            "base_currency": "USD",
            "investment_amount": 2.0,
        },
    },
    "wizard_defaults": {
        "spec": {"markets": {"BTC/USDT": FULL_MARKET}, "ticker": {"last": 60000.0}},
        "config": {"exchange_id": "coinbase"},
    },
    "unicode_pair": {
        "spec": {"markets": {UNICODE_PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "config": {**GATE_CONFIG, "target_asset": "Δ→⚡", "target_balance": 2.0},
    },
    "markup_pair": {
        "spec": {"markets": {MARKUP_PAIR: FULL_MARKET}, "ticker": {"last": 0.0123}},
        "config": {**GATE_CONFIG, "target_asset": "<b>BTC</b>", "target_balance": 2.0},
    },
    "long_pair": {
        "spec": {"markets": {}},
        "config": {**GATE_CONFIG, "target_asset": "X" * 200},
    },
    "module_missing": {
        "spec": {"markets": {PAIR: FULL_MARKET}},
        "config": RaisingConfig(ImportError("preflight_check is unavailable")),
    },
    "errored": {
        "spec": {"markets": {PAIR: FULL_MARKET}},
        "config": RaisingConfig(RuntimeError("the wizard config broke")),
    },
}

GATE_ANSWERS = (None, surface.OK, surface.YES, surface.NO)


def app():
    """The process application object every render and box needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


def default_button_value(box):
    """The standard-button value the box would press on Return, or zero."""
    chosen = box.defaultButton()
    if chosen is None:
        return surface.NO_DEFAULT_BUTTON_VALUE
    return box.standardButton(chosen).value


def record_box(box, name):
    """Read one message box back and append what it carries."""
    CALLS.extend(
        [
            [surface.BOX_CREATE, name],
            [surface.BOX_SET_WINDOW_TITLE, name, box.windowTitle()],
            [surface.BOX_SET_TEXT, name, box.text()],
            [surface.BOX_SET_ICON, name, box.icon().value],
            [surface.BOX_SET_STANDARD_BUTTONS, name, box.standardButtons().value],
            [surface.BOX_SET_DEFAULT_BUTTON, name, default_button_value(box)],
            [surface.BOX_EXEC, name],
        ]
    )


def build_box(
    icon_value,
    title,
    body,
    buttons_value,
    default_value,
    text_format_value,
    style_sheet="",
):
    """One real QMessageBox, built from six plain values and a skin."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox

    app()
    box = QMessageBox(
        QMessageBox.Icon(icon_value),
        title,
        body,
        QMessageBox.StandardButton(buttons_value),
    )
    box.setTextFormat(Qt.TextFormat(text_format_value))
    if default_value != surface.NO_DEFAULT_BUTTON_VALUE:
        box.setDefaultButton(QMessageBox.StandardButton(default_value))
    if style_sheet:
        box.setStyleSheet(style_sheet)
    return box


def box_button_texts(box):
    """The label on every button the box offers, in its own order."""
    return [button.text() for button in box.buttons()]


def old_failure_box(report):
    """The box the wizard raises when the check fails."""
    from PySide6.QtWidgets import QMessageBox

    return build_box(
        QMessageBox.Icon.Critical.value,
        CALLER_FAILURE_TITLE,
        CALLER_FAILURE_BODY.format(report),
        QMessageBox.StandardButton.Ok.value,
        surface.NO_DEFAULT_BUTTON_VALUE,
        CALLER_TEXT_FORMAT_VALUE,
    )


def old_warning_box(report):
    """The box the wizard raises when the check passes with warnings."""
    from PySide6.QtWidgets import QMessageBox

    return build_box(
        QMessageBox.Icon.Question.value,
        CALLER_WARNING_TITLE,
        CALLER_WARNING_BODY.format(report),
        (QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No).value,
        QMessageBox.StandardButton.No.value,
        CALLER_TEXT_FORMAT_VALUE,
    )


def new_box(payload):
    """A box built only from the surface payload, never from the wizard.

    A payload the caller changed after it came off the surface is
    refused.
    """
    unaltered(payload)
    properties = (
        payload["failure_widget"]
        if payload["box"] == surface.FAILURE_BOX
        else payload["warning_widget"]
    )
    return build_box(
        properties["icon_value"],
        payload["box_title"],
        payload["box_body"],
        properties["buttons_value"],
        properties["default_button_value"],
        properties["text_format_value"],
        properties["style_sheet"],
    )


# The wizard reads a Yes and nothing else as consent. Typed here, so a changed
# table cannot move both sides at once.
WIZARD_BUTTON_ANSWER = {"ok": False, "yes": True, "no": False}
WIZARD_CLOSED_ANSWER = False
WIZARD_CREATES_BOT = {
    "proceed": True,
    "blocked": False,
    "declined": False,
    "skipped": True,
    "module_missing": True,
    "errored": True,
}
WIZARD_BUTTON_NAMES = {1024: ("ok",), 81920: ("yes", "no")}


def record_status(line, level):
    CALLS.append([surface.STATUS_LOG, line, level])


def record_outcome(outcome):
    CALLS.append([surface.GATE_OUTCOME, outcome, WIZARD_CREATES_BOT[outcome]])


def format_ms(value):
    """The elapsed reading as the wizard writes it into the status log."""
    return f"{value:.0f}"


def snapshot(view):
    """One step's whole state: the outputs and the ordered call list."""
    body = {"calls": [list(call) for call in CALLS]}
    body.update(view)
    return body


def blank_view():
    """Every field a gate step reports, before anything has run."""
    return {
        "result": {},
        "report": "",
        "box": "",
        "box_title": "",
        "box_body": "",
        "box_buttons": [],
        "status_line": "",
        "status_level": surface.LEVEL_INFO,
        "outcome": surface.DEFAULT_OUTCOME,
        "answered": surface.DEFAULT_ANSWER,
    }


def run_old_check(name, monkeypatch):
    """Drive the shipped check and its report over one case."""
    case = CASES[name]
    install_ccxt(monkeypatch, case["spec"])
    freeze_clock(monkeypatch)
    CALLS.clear()
    result = shipped.check_symbol(*case["args"])
    report = shipped.format_result_for_user(result)
    return snapshot({"result": dataclasses.asdict(result), "report": report})


def run_new_check(name, monkeypatch):
    """Drive the surface's check and its report over the same case."""
    case = CASES[name]
    install_ccxt(monkeypatch, case["spec"])
    freeze_clock(monkeypatch)
    CALLS.clear()
    model = surface.PreflightModel()
    result = model.check(*case["args"])
    report = model.format_result(result)
    return snapshot({"result": result, "report": report})


def offered_buttons(box):
    """The buttons the real box carries, named by the wizard's own table."""
    return WIZARD_BUTTON_NAMES[box.standardButtons().value]


def old_gate_symbol(config):
    """The pair the wizard builds before it calls the check."""
    return (
        str(config.get("target_asset", "BTC"))
        + "/"
        + str(config.get("base_currency", "USDT"))
    )


def _old_leave(view, button, closed, unanswered, offered):
    """The way out of the open box, and the answer it leaves behind."""
    if closed:
        CALLS.append([surface.BOX_CLOSE, WIZARD_CLOSED_ANSWER])
        view["answered"] = WIZARD_CLOSED_ANSWER
        return None
    pressed = button if button in offered else unanswered
    answer = WIZARD_BUTTON_ANSWER[pressed]
    CALLS.append([surface.BOX_ANSWER, pressed, answer])
    view["answered"] = answer
    return pressed


def _old_settle(view, outcome, line, level):
    """Write one status line and record the outcome the wizard reached."""
    record_status(line, level)
    view["status_line"] = line
    view["status_level"] = level
    view["outcome"] = outcome
    record_outcome(outcome)
    return snapshot(view)


def run_old_gate(name, button, closed, monkeypatch):
    """Drive the shipped check under the wizard's own gate."""
    case = GATE_CASES[name]
    install_ccxt(monkeypatch, case["spec"])
    freeze_clock(monkeypatch)
    CALLS.clear()
    app()
    config = case["config"]
    view = blank_view()
    try:
        if config.get("mode") == "extractor":
            return _old_settle(
                view, surface.OUTCOME_SKIPPED, CALLER_SKIP_LOG, surface.LEVEL_INFO
            )
        result = shipped.check_symbol(
            exchange_id=config.get("exchange_id", ""),
            symbol=old_gate_symbol(config),
            target_balance=config.get(
                "target_balance", config.get("investment_amount", 200.0)
            ),
        )
        report = shipped.format_result_for_user(result)
        view["result"] = dataclasses.asdict(result)
        view["report"] = report
        if not result.success:
            box = old_failure_box(report)
            record_box(box, surface.FAILURE_BOX)
            view.update(
                {
                    "box": surface.FAILURE_BOX,
                    "box_title": box.windowTitle(),
                    "box_body": box.text(),
                    "box_buttons": list(offered_buttons(box)),
                }
            )
            _old_leave(view, button, closed, "ok", offered_buttons(box))
            return _old_settle(
                view,
                surface.OUTCOME_BLOCKED,
                CALLER_BLOCKED_LOG.format(
                    result.symbol, result.exchange_id, result.message
                ),
                surface.LEVEL_ERROR,
            )
        if result.warnings:
            box = old_warning_box(report)
            record_box(box, surface.WARNING_BOX)
            view.update(
                {
                    "box": surface.WARNING_BOX,
                    "box_title": box.windowTitle(),
                    "box_body": box.text(),
                    "box_buttons": list(offered_buttons(box)),
                }
            )
            pressed = _old_leave(view, button, closed, "no", offered_buttons(box))
            if pressed != "yes":
                return _old_settle(
                    view,
                    surface.OUTCOME_DECLINED,
                    CALLER_DECLINED_LOG.format(len(result.warnings)),
                    surface.LEVEL_WARNING,
                )
        return _old_settle(
            view,
            surface.OUTCOME_PROCEED,
            CALLER_PROCEED_LOG.format(
                result.symbol, result.exchange_id, format_ms(result.elapsed_ms)
            ),
            surface.LEVEL_INFO,
        )
    except ImportError:
        return _old_settle(
            view,
            surface.OUTCOME_MODULE_MISSING,
            CALLER_MODULE_MISSING_LOG,
            surface.LEVEL_WARNING,
        )
    except Exception as exc:
        return _old_settle(
            view,
            surface.OUTCOME_ERRORED,
            CALLER_ERRORED_LOG.format(type(exc).__name__, exc),
            surface.LEVEL_WARNING,
        )


def view_of(model):
    """The surface payload for a model that has already been driven, stamped."""
    return sealed(surface.build_view_model(model))


def run_new_gate(name, button, closed, monkeypatch):
    """Drive the surface over the same wizard gate."""
    case = GATE_CASES[name]
    install_ccxt(monkeypatch, case["spec"])
    freeze_clock(monkeypatch)
    CALLS.clear()
    app()
    model = surface.PreflightModel()
    model.run_gate(case["config"], "", button, closed)
    exchange_calls = list(CALLS)
    CALLS.clear()
    CALLS.extend(_new_calls(model, exchange_calls))
    return snapshot(
        {
            "result": dict(model.result),
            "report": model.report,
            "box": model.box,
            "box_title": model.box_title,
            "box_body": model.box_body,
            "box_buttons": list(model.box_buttons),
            "status_line": model.status_line,
            "status_level": model.status_level,
            "outcome": model.outcome,
            "answered": model.answered,
        }
    )


BOX_STEPS = 7

REPLAYED = (
    surface.BOX_ANSWER,
    surface.BOX_CLOSE,
    surface.STATUS_LOG,
    surface.GATE_OUTCOME,
)


def _new_calls(model, exchange_calls):
    """The surface's calls, with the box read back off a real Qt box.

    The exchange calls come from the fake the surface itself drove, so
    a config or a request the surface changed reaches the trace rather
    than the value the surface was told.
    """
    ordered = list(exchange_calls)
    for call in model.calls:
        if call[0] == surface.BOX_CREATE:
            record_box(new_box(view_of(model)), model.box)
            ordered.extend(CALLS[-BOX_STEPS:])
            del CALLS[-BOX_STEPS:]
        elif call[0] in REPLAYED:
            ordered.append(list(call))
    return ordered


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_check_returns_the_same_result(name, monkeypatch):
    """The surface returned a different result than the shipped check."""
    old = run_old_check(name, monkeypatch)
    new = run_new_check(name, monkeypatch)
    assert new == old, name
    assert digest(new) == digest(old), name


@pytest.mark.parametrize("name", sorted(CASES))
def test_the_check_trace_holds_the_whole_result(name, monkeypatch):
    """The comparison passed by measuring nothing."""
    old = run_old_check(name, monkeypatch)
    assert set(old["result"]) == set(surface.RESULT_FIELDS)
    assert isinstance(old["result"]["message"], str)
    assert old["result"]["message"] != ""
    assert isinstance(old["report"], str)
    assert old["report"] != ""
    assert old["result"]["success"] is (name not in FAILING_CASES)
    assert old["result"]["elapsed_ms"] == CLOCK_STEP * 1000
    assert (old["calls"] == []) is (name in NO_EXCHANGE_CASES)


GATE_SCRIPTS = {}
for _name in GATE_CASES:
    for _answer in GATE_ANSWERS:
        GATE_SCRIPTS[f"{_name}_{_answer or 'unanswered'}"] = (_name, _answer, False)
    GATE_SCRIPTS[f"{_name}_closed"] = (_name, None, True)


@pytest.mark.parametrize("script", sorted(GATE_SCRIPTS))
def test_the_gate_ends_the_same_way(script, monkeypatch):
    """A step of the gate left the two sides in a different state."""
    name, button, closed = GATE_SCRIPTS[script]
    old = run_old_gate(name, button, closed, monkeypatch)
    new = run_new_gate(name, button, closed, monkeypatch)
    assert new == old, script
    assert digest(new) == digest(old), script


@pytest.mark.parametrize("script", sorted(GATE_SCRIPTS))
def test_the_gate_trace_holds_the_whole_gate(script, monkeypatch):
    """The comparison passed by measuring nothing."""
    name, button, closed = GATE_SCRIPTS[script]
    old = run_old_gate(name, button, closed, monkeypatch)
    assert old["outcome"] in surface.OUTCOMES
    assert old["status_line"] != ""
    assert old["status_level"] in surface.OUTCOME_LEVELS.values()
    assert old["calls"] != []
    assert old["calls"][-1][0] == surface.GATE_OUTCOME
    if old["box"]:
        assert old["box_title"] != ""
        assert old["box_body"] != ""
        assert old["box_buttons"] != []


def test_the_scripts_reach_every_outcome_and_every_failure(monkeypatch):
    """A state was never driven, so its parity was never compared."""
    outcomes = set()
    answers = set()
    boxes = set()
    levels = set()
    warning_counts = set()
    for script in GATE_SCRIPTS:
        name, button, closed = GATE_SCRIPTS[script]
        step = run_old_gate(name, button, closed, monkeypatch)
        outcomes.add(step["outcome"])
        answers.add(step["answered"])
        boxes.add(step["box"])
        levels.add(step["status_level"])
        if step["result"]:
            warning_counts.add(len(step["result"]["warnings"]))
    assert outcomes == set(surface.OUTCOMES)
    assert answers == {True, False}
    assert boxes == {"", surface.FAILURE_BOX, surface.WARNING_BOX}
    assert levels == {surface.LEVEL_INFO, surface.LEVEL_WARNING, surface.LEVEL_ERROR}
    assert warning_counts == {0, 1}

    messages = set()
    reports = set()
    warning_lines = set()
    for name in CASES:
        step = run_old_check(name, monkeypatch)
        messages.add(step["result"]["message"])
        reports.add(step["report"])
        warning_lines.update(step["result"]["warnings"])
    assert surface.CCXT_MISSING_MESSAGE in messages
    assert any(text.startswith("Exchange '") for text in messages)
    assert any("not found but" in text for text in messages)
    assert any("is not listed on" in text for text in messages)
    assert any(text.startswith("Pre-flight check failed: ") for text in messages)
    assert "Symbol verified on Coinbase." in messages
    assert any("⚡" in report for report in reports)
    assert any("X" * 200 in report for report in reports)
    assert any("<b>BTC</b>" in report for report in reports)
    assert len(warning_lines) == 4
    assert any(line.startswith("Market reported as inactive") for line in warning_lines)
    assert any("less than 3x min-order-cost" in line for line in warning_lines)


def test_every_check_case_drives_the_branch_it_names(monkeypatch):
    """A case was renamed and stopped reaching the path it stands for."""
    reached = {}
    for name in CASES:
        reached[name] = run_old_check(name, monkeypatch)["result"]
    assert reached["no_ccxt"]["message"] == surface.CCXT_MISSING_MESSAGE
    assert reached["unknown_exchange"]["message"].startswith("Exchange 'notanexchange'")
    assert reached["empty_exchange"]["message"].startswith("Exchange ''")
    assert "but 'RAVE/USD' exists" in reached["symbol_casing"]["message"]
    assert "but 'RAVE-USD' exists" in reached["symbol_dash"]["message"]
    assert "but 'RAVE/USD' exists" in reached["symbol_slash"]["message"]
    assert reached["symbol_missing"]["message"].startswith("Symbol 'ZZZ/USD' is not")
    assert reached["empty_symbol"]["message"].startswith("Symbol '' is not")
    assert reached["no_markets"]["message"].startswith("Symbol 'RAVE/USD' is not")
    assert reached["load_raises"]["message"] == (
        "Pre-flight check failed: RuntimeError: venue refused the market list"
    )
    assert reached["unknown_input"]["message"].startswith(
        "Pre-flight check failed: TypeError"
    )
    assert reached["ticker_raises"]["last_price"] == 0.0
    assert reached["ticker_raises"]["success"] is True
    assert reached["ticker_blank"]["last_price"] == 0.0
    assert reached["happy"]["warnings"] == []
    assert len(reached["thin_capital"]["warnings"]) == 1
    assert len(reached["inactive_market"]["warnings"]) == 1
    assert len(reached["two_warnings"]["warnings"]) == 2
    assert reached["zero_limits"]["min_order_cost"] == 0.0
    assert reached["zero_limits"]["warnings"] == []
    assert reached["empty_limits"]["min_order_amount"] == 0.0
    assert reached["no_active_flag"]["market_active"] is True
    assert "active" not in NO_ACTIVE_FLAG_MARKET
    assert reached["no_active_flag"]["warnings"] == []
    assert reached["inactive_market"]["market_active"] is False
    assert reached["negative_limits"]["warnings"] == []
    assert reached["negative_balance"]["warnings"] != []
    assert reached["very_large"]["last_price"] == 1e12
    assert reached["decimal_places_mode"]["price_precision"] == 8
    assert reached["decimal_places_mode"]["amount_precision"] == 6
    assert reached["significant_digits_mode"]["price_precision"] == 0
    assert reached["happy"]["price_precision"] == 6
    assert reached["happy"]["amount_precision"] == 8


def new_payload(name, monkeypatch, button=None, closed=False):
    """The surface payload for one gate case, driven end to end."""
    case = GATE_CASES[name]
    install_ccxt(monkeypatch, case["spec"])
    freeze_clock(monkeypatch)
    CALLS.clear()
    model = surface.PreflightModel()
    model.run_gate(case["config"], "", button, closed)
    return view_of(model)


def old_box_widget(name, monkeypatch):
    """The box the wizard raises for one gate case."""
    case = GATE_CASES[name]
    install_ccxt(monkeypatch, case["spec"])
    freeze_clock(monkeypatch)
    CALLS.clear()
    app()
    config = case["config"]
    result = shipped.check_symbol(
        exchange_id=config.get("exchange_id", ""),
        symbol=old_gate_symbol(config),
        target_balance=config.get(
            "target_balance", config.get("investment_amount", 200.0)
        ),
    )
    report = shipped.format_result_for_user(result)
    if not result.success:
        return old_failure_box(report)
    return old_warning_box(report)


BOX_CASES = (
    "blocked",
    "long_pair",
    "warned",
    "investment_amount",
    "unicode_pair",
    "markup_pair",
)

FAILURE_CASES = ("blocked", "long_pair")


@pytest.mark.parametrize("name", BOX_CASES)
def test_the_two_sides_render_the_same_pixels(name, monkeypatch):
    """The box paints a value or a position the wizard's box does not."""
    app()
    assert_pictures_match(
        old_side=render_offscreen(old_box_widget(name, monkeypatch), PIXEL_SIZE),
        new_side=render_offscreen(new_box(new_payload(name, monkeypatch)), PIXEL_SIZE),
        note=name,
    )


@pytest.mark.parametrize("name", BOX_CASES)
def test_the_two_boxes_carry_the_same_properties(name, monkeypatch):
    """A box property drifted from the value the surface reports."""
    from PySide6.QtCore import Qt

    app()
    old = old_box_widget(name, monkeypatch)
    payload = new_payload(name, monkeypatch)
    properties = (
        payload["failure_widget"]
        if payload["box"] == surface.FAILURE_BOX
        else payload["warning_widget"]
    )
    assert payload["box"] == (
        surface.FAILURE_BOX if name in FAILURE_CASES else surface.WARNING_BOX
    )
    assert properties["window_title"] == old.windowTitle()
    assert payload["box_title"] == old.windowTitle()
    assert payload["box_body"] == old.text()
    assert properties["icon_value"] == old.icon().value
    assert properties["icon"] == old.icon().name
    assert properties["buttons_value"] == old.standardButtons().value
    assert properties["default_button_value"] == default_button_value(old)
    assert properties["modal"] is old.isModal()
    assert properties["accessible_name"] == old.accessibleName()
    assert properties["style_sheet"] == ""
    assert properties["size_px"] == [old.width(), old.height()]
    assert properties["stays_on_top"] is bool(
        old.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    )
    assert properties["text_format_value"] == old.textFormat().value
    assert properties["text_format"] == old.textFormat().name


def test_the_button_labels_are_the_boxes_own(monkeypatch):
    """A button label drifted from the label the wizard's box carries."""
    app()
    old_failure = old_box_widget("blocked", monkeypatch)
    old_warning = old_box_widget("warned", monkeypatch)
    new_failure = new_box(new_payload("blocked", monkeypatch))
    new_warning = new_box(new_payload("warned", monkeypatch))
    assert box_button_texts(new_failure) == box_button_texts(old_failure)
    assert box_button_texts(new_warning) == box_button_texts(old_warning)
    assert box_button_texts(old_failure) == [surface.OK_TEXT]
    assert box_button_texts(old_warning) == [surface.YES_TEXT, surface.NO_TEXT]
    assert box_button_texts(old_failure) != box_button_texts(old_warning)
    payload = new_payload("warned", monkeypatch)
    assert [
        payload["buttons"][name]["text"] for name in payload["warning_buttons"]
    ] == (box_button_texts(old_warning))
    assert [
        payload["buttons"][name]["text"] for name in payload["failure_buttons"]
    ] == box_button_texts(old_failure)
    for button in old_warning.buttons() + old_failure.buttons():
        assert button.isEnabled() is True
    assert set(surface.BUTTON_ENABLED.values()) == {True}


def test_the_button_values_are_qts_own():
    """A standard-button number drifted from the one Qt uses."""
    from PySide6.QtWidgets import QMessageBox

    app()
    assert surface.OK_BUTTON_VALUE == QMessageBox.StandardButton.Ok.value
    assert surface.YES_BUTTON_VALUE == QMessageBox.StandardButton.Yes.value
    assert surface.NO_BUTTON_VALUE == QMessageBox.StandardButton.No.value
    assert surface.FAILURE_ICON_VALUE == QMessageBox.Icon.Critical.value
    assert surface.WARNING_ICON_VALUE == QMessageBox.Icon.Question.value
    assert surface.FAILURE_ICON_VALUE != surface.WARNING_ICON_VALUE
    assert (
        surface.WARNING_BUTTONS_VALUE
        == (QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No).value
    )
    assert surface.WARNING_BUTTONS_VALUE != surface.FAILURE_BUTTONS_VALUE
    assert surface.NO_DEFAULT_BUTTON_VALUE == 0
    assert QMessageBox.StandardButton(surface.OK_BUTTON_VALUE) == (
        QMessageBox.StandardButton.Ok
    )
    assert len(set(surface.BUTTON_VALUES.values())) == 3


def test_the_surface_ships_the_gate_strings_the_operator_reads():
    """A string the operator reads was retyped rather than carried over."""
    assert surface.FAILURE_TITLE == CALLER_FAILURE_TITLE
    assert surface.WARNING_TITLE == CALLER_WARNING_TITLE
    assert surface.FAILURE_BODY_FORMAT.format(report="R") == CALLER_FAILURE_BODY.format(
        "R"
    )
    assert surface.WARNING_BODY_FORMAT.format(report="R") == CALLER_WARNING_BODY.format(
        "R"
    )
    assert surface.EXTRACTOR_SKIP_LOG == CALLER_SKIP_LOG
    assert surface.MODULE_MISSING_LOG == CALLER_MODULE_MISSING_LOG
    assert surface.BLOCKED_LOG_FORMAT.format(
        symbol="S", exchange_id="E", message="M"
    ) == CALLER_BLOCKED_LOG.format("S", "E", "M")
    assert surface.DECLINED_LOG_FORMAT.format(
        warning_count=2
    ) == CALLER_DECLINED_LOG.format(2)
    assert surface.PROCEED_LOG_FORMAT.format(
        symbol="S", exchange_id="E", elapsed_ms=12.4
    ) == CALLER_PROCEED_LOG.format("S", "E", "12")
    assert surface.ERRORED_LOG_FORMAT.format(
        error_type="T", error="E"
    ) == CALLER_ERRORED_LOG.format("T", "E")


def shipped_check_output(monkeypatch):
    """Every message, warning and report the shipped check produces."""
    produced = set()
    for name in CASES:
        step = run_old_check(name, monkeypatch)
        produced.add(step["result"]["message"])
        produced.update(step["result"]["warnings"])
        produced.add(step["report"])
    return produced


def test_the_check_strings_are_the_shipped_checks_own(monkeypatch):
    """A message the operator reads drifted from the shipped check's."""
    produced = shipped_check_output(monkeypatch)
    assert len(produced) >= 30, sorted(produced)
    for literal in (
        surface.CCXT_MISSING_MESSAGE,
        "not recognized by CCXT. ",
        "Check spelling (e.g. 'coinbase', 'binance').",
        "not found but ",
        "Use the exact casing/format listed by the exchange.",
        "is not listed on ",
        "Check the asset is ",
        "actively traded on this exchange.",
        "Symbol verified on ",
        "Pre-flight check failed: ",
        "Market reported as inactive by ",
        "is less than 3x min-order-cost ",
        "Bot may only place a handful of trades.",
        surface.PASSED_HEADLINE,
        "⚠ Pre-flight check FAILED",
        "Elapsed: ",
        "Exchange: ",
        "Symbol: ",
        "Market active: ",
        surface.ACTIVE_NOT_REPORTED,
        surface.PRICE_UNREAD_LINE,
        "Current price: $",
        "Min order amount: ",
        "Min order cost: $",
        "Price precision: ",
        "Check elapsed: ",
        surface.WARNINGS_HEADLINE,
        str(surface.MIN_COST_HEADROOM) + "x min-order-cost",
    ):
        assert any(literal in text for text in produced), literal
    absent = "a-string-the-shipped-check-never-holds"
    assert not any(absent in text for text in produced), absent


def test_the_report_is_built_from_the_declared_formats(monkeypatch):
    """A report line was assembled from a format the surface never names."""
    step = run_old_check("two_warnings", monkeypatch)
    result = step["result"]
    lines = step["report"].split(surface.REPORT_JOIN)
    assert lines[0] == surface.PASSED_HEADLINE
    assert lines[1] == surface.BLANK_LINE
    assert lines[2] == surface.EXCHANGE_LINE_FORMAT.format(exchange_name="Coinbase")
    assert lines[3] == surface.SYMBOL_LINE_FORMAT.format(symbol=result["symbol"])
    assert lines[4] == surface.ACTIVE_LINE_FORMAT.format(active_word=surface.ACTIVE_NO)
    assert lines[5] == surface.PRICE_LINE_FORMAT.format(last_price=result["last_price"])
    assert lines[6] == surface.MIN_AMOUNT_LINE_FORMAT.format(
        min_order_amount=result["min_order_amount"],
        amount_precision=result["amount_precision"],
    )
    assert lines[7] == surface.MIN_COST_LINE_FORMAT.format(
        min_order_cost=result["min_order_cost"]
    )
    assert lines[8] == surface.PRICE_PRECISION_LINE_FORMAT.format(
        price_precision=result["price_precision"]
    )
    assert lines[9] == surface.BLANK_LINE
    assert lines[10] == surface.ELAPSED_LINE_FORMAT.format(
        elapsed_ms=result["elapsed_ms"]
    )
    assert lines[11] == surface.BLANK_LINE
    assert lines[12] == surface.WARNINGS_HEADLINE
    assert lines[13] == surface.WARNING_LINE_FORMAT.format(
        warning=result["warnings"][0]
    )
    assert lines[14] == surface.WARNING_LINE_FORMAT.format(
        warning=result["warnings"][1]
    )
    assert len(lines) == 15
    active = run_old_check("happy", monkeypatch)["report"].split(surface.REPORT_JOIN)
    assert active[4] == surface.ACTIVE_LINE_FORMAT.format(
        active_word=surface.ACTIVE_YES
    )
    assert surface.ACTIVE_YES != surface.ACTIVE_NO
    assert len(active) == 11
    bare = run_old_check("zero_limits", monkeypatch)["report"].split(
        surface.REPORT_JOIN
    )
    assert len(bare) == 7
    assert not any(line.startswith("Min order") for line in bare)
    assert not any(line.startswith("Current price") for line in bare)
    assert not any(line.startswith("Price precision") for line in bare)
    failed = run_old_check("symbol_missing", monkeypatch)["report"]
    assert failed == surface.FAILURE_REPORT_FORMAT.format(
        message=run_old_check("symbol_missing", monkeypatch)["result"]["message"],
        elapsed_ms=CLOCK_STEP * 1000,
    )


def test_the_format_strings_carry_their_own_placeholders():
    """A placeholder was dropped, so a value never reaches the operator."""
    named = {
        surface.UNKNOWN_EXCHANGE_FORMAT: ("exchange_id",),
        surface.SYMBOL_CASING_FORMAT: ("symbol", "hit"),
        surface.SYMBOL_MISSING_FORMAT: ("symbol", "exchange_name"),
        surface.SUCCESS_MESSAGE_FORMAT: ("exchange_name",),
        surface.CHECK_FAILED_MESSAGE_FORMAT: ("error_type", "error"),
        surface.INACTIVE_WARNING_FORMAT: ("exchange_name",),
        surface.THIN_CAPITAL_WARNING_FORMAT: ("target_balance", "min_order_cost"),
        surface.FAILURE_REPORT_FORMAT: ("message", "elapsed_ms"),
        surface.EXCHANGE_LINE_FORMAT: ("exchange_name",),
        surface.SYMBOL_LINE_FORMAT: ("symbol",),
        surface.ACTIVE_LINE_FORMAT: ("active_word",),
        surface.PRICE_LINE_FORMAT: ("last_price",),
        surface.MIN_AMOUNT_LINE_FORMAT: ("min_order_amount", "amount_precision"),
        surface.MIN_COST_LINE_FORMAT: ("min_order_cost",),
        surface.PRICE_PRECISION_LINE_FORMAT: ("price_precision",),
        surface.ELAPSED_LINE_FORMAT: ("elapsed_ms",),
        surface.WARNING_LINE_FORMAT: ("warning",),
        surface.FAILURE_BODY_FORMAT: ("report",),
        surface.WARNING_BODY_FORMAT: ("report",),
        surface.BLOCKED_LOG_FORMAT: ("symbol", "exchange_id", "message"),
        surface.DECLINED_LOG_FORMAT: ("warning_count",),
        surface.PROCEED_LOG_FORMAT: ("symbol", "exchange_id", "elapsed_ms"),
        surface.ERRORED_LOG_FORMAT: ("error_type", "error"),
    }
    for template, fields in named.items():
        for field in fields:
            assert "{" + field in template, (template, field)
        assert template.count("{") == len(fields), template
    assert len(named) == 23
    assert "{elapsed_ms:.0f}" in surface.FAILURE_REPORT_FORMAT
    assert "{elapsed_ms:.0f}" in surface.ELAPSED_LINE_FORMAT
    assert "{elapsed_ms:.0f}" in surface.PROCEED_LOG_FORMAT
    assert "{last_price:.8f}" in surface.PRICE_LINE_FORMAT
    assert "{min_order_cost:.4f}" in surface.MIN_COST_LINE_FORMAT
    assert "{target_balance:.2f}" in surface.THIN_CAPITAL_WARNING_FORMAT
    assert "{min_order_cost:.2f}" in surface.THIN_CAPITAL_WARNING_FORMAT
    assert surface.PRICE_LINE_FORMAT.format(last_price=1.5) == (
        "Current price: $1.50000000"
    )
    assert surface.MIN_COST_LINE_FORMAT.format(min_order_cost=1.5) == (
        "Min order cost: $1.5000"
    )
    assert surface.ELAPSED_LINE_FORMAT.format(elapsed_ms=12.6) == (
        "Check elapsed: 13 ms"
    )
    assert surface.CHECK_FAILED_LOG.count("%s") == 1


def test_the_config_the_check_sends_is_the_shipped_configs_own(monkeypatch):
    """The surface asked the exchange for different settings."""
    old = run_old_check("credentials", monkeypatch)
    new = run_new_check("credentials", monkeypatch)
    built = [call for call in old["calls"] if call[0] == surface.CONFIG_BUILD]
    assert built == [
        [
            surface.CONFIG_BUILD,
            ["apiKey", "enableRateLimit", "password", "secret", "timeout"],
        ]
    ]
    assert [call for call in new["calls"] if call[0] == surface.CONFIG_BUILD] == built
    partial_old = run_old_check("partial_credentials", monkeypatch)
    partial_new = run_new_check("partial_credentials", monkeypatch)
    partial = [call for call in partial_old["calls"] if call[0] == surface.CONFIG_BUILD]
    assert partial == [[surface.CONFIG_BUILD, ["apiKey", "enableRateLimit", "timeout"]]]
    assert [
        call for call in partial_new["calls"] if call[0] == surface.CONFIG_BUILD
    ] == partial
    plain = run_old_check("happy", monkeypatch)
    assert [call for call in plain["calls"] if call[0] == surface.CONFIG_BUILD] == [
        [surface.CONFIG_BUILD, ["enableRateLimit", "timeout"]]
    ]
    assert [call for call in plain["calls"] if call[0] == surface.EXCHANGE_CREATE] == [
        [surface.EXCHANGE_CREATE, surface.REQUEST_TIMEOUT_MS]
    ]
    plain_config = {
        "enableRateLimit": True,
        "timeout": surface.REQUEST_TIMEOUT_MS,
    }
    assert surface.build_config({}) == plain_config
    named = [name for name, _ in surface.CREDENTIAL_FIELDS]
    fields = [field for _, field in surface.CREDENTIAL_FIELDS]
    given = dict(zip(named, ("one", "two", "three")))
    assert surface.build_config(given) == {
        **plain_config,
        **dict(zip(fields, ("one", "two", "three"))),
    }
    assert list(surface.build_config(given))[2:] == fields
    blanks = dict(zip(named, ("", None, surface.CREDENTIAL_ABSENT)))
    assert surface.build_config(blanks) == plain_config
    assert surface.build_config({named[0]: "one"}) == {
        **plain_config,
        fields[0]: "one",
    }
    assert surface.REQUEST_TIMEOUT_MS == 15000
    assert surface.ENABLE_RATE_LIMIT is True


def test_the_error_log_is_the_shipped_checks_own(monkeypatch, capture_log):
    """The line the trade log carries drifted from the shipped check's."""
    for name in ("load_raises", "unknown_input"):
        with capture_log(LOGGER_NAME) as old_records:
            run_old_check(name, monkeypatch)
        old_logs = [record.getMessage() for record in old_records]
        with capture_log(LOGGER_NAME) as new_records:
            run_new_check(name, monkeypatch)
        new_logs = [record.getMessage() for record in new_records]
        assert new_logs == old_logs, name
        assert len(old_logs) == 1, name
        assert [record.levelname for record in old_records] == ["ERROR"], name
    with capture_log(LOGGER_NAME) as records:
        run_old_check("load_raises", monkeypatch)
    assert [record.getMessage() for record in records] == [
        "Preflight check failed: venue refused the market list"
    ]
    with capture_log(LOGGER_NAME) as quiet:
        run_old_check("happy", monkeypatch)
    assert [record.getMessage() for record in quiet] == []
    with capture_log(LOGGER_NAME) as absent:
        run_old_check("symbol_missing", monkeypatch)
    assert [record.getMessage() for record in absent] == []
    assert surface.LOGGER_NAME == LOGGER_NAME
    assert surface.logger.name == shipped.logger.name == LOGGER_NAME


def test_the_status_lines_are_the_wizards_own(monkeypatch):
    """The line the operator sees in the status log drifted."""
    expected = {
        ("proceed", None, False): (
            "Pre-flight OK for RAVE/USD on coinbase (250 ms)",
            surface.LEVEL_INFO,
        ),
        ("warned", surface.YES, False): (
            "Pre-flight OK for RAVE/USD on coinbase (250 ms)",
            surface.LEVEL_INFO,
        ),
        ("warned", surface.NO, False): (
            "Bot creation declined at pre-flight (1 warning(s))",
            surface.LEVEL_WARNING,
        ),
        ("warned", None, True): (
            "Bot creation declined at pre-flight (1 warning(s))",
            surface.LEVEL_WARNING,
        ),
        ("blocked", None, False): (
            "Pre-flight FAILED for RAVE/USD on coinbase: Symbol 'RAVE/USD' is "
            "not listed on Coinbase. Check the asset is actively traded on "
            "this exchange.",
            surface.LEVEL_ERROR,
        ),
        ("extractor", None, False): (CALLER_SKIP_LOG, surface.LEVEL_INFO),
        ("module_missing", None, False): (
            CALLER_MODULE_MISSING_LOG,
            surface.LEVEL_WARNING,
        ),
        ("errored", None, False): (
            "Pre-flight check errored: RuntimeError: the wizard config "
            "broke — continuing anyway",
            surface.LEVEL_WARNING,
        ),
    }
    for (name, button, closed), (line, level) in expected.items():
        old = run_old_gate(name, button, closed, monkeypatch)
        new = run_new_gate(name, button, closed, monkeypatch)
        assert old["status_line"] == line, name
        assert old["status_level"] == level, name
        assert new["status_line"] == old["status_line"], name
        assert new["status_level"] == old["status_level"], name
    assert len(expected) == 8
    assert len({line for line, _ in expected.values()}) == 6


def model_with_the_warning_box_open(monkeypatch):
    """A model that has raised the warning box and pressed nothing."""
    case = GATE_CASES["warned"]
    install_ccxt(monkeypatch, case["spec"])
    freeze_clock(monkeypatch)
    model = surface.PreflightModel()
    model.format_result(
        model.check(
            exchange_id=case["config"]["exchange_id"],
            symbol=surface.gate_symbol(case["config"]),
            target_balance=surface.gate_target_balance(case["config"]),
        )
    )
    model.ask_warnings()
    return model


def test_a_declared_action_records_the_press_instead_of_reaching_qt(monkeypatch):
    """A name in ACTIONS reached a method that recorded nothing."""
    for action, target in surface.ACTIONS.items():
        model = model_with_the_warning_box_open(monkeypatch)
        assert model.box == surface.WARNING_BOX, action
        assert model.box_title == surface.WARNING_TITLE, action
        assert [call for call in model.calls if call[0] == surface.BOX_EXEC] == [
            [surface.BOX_EXEC, surface.WARNING_BOX]
        ], action
        assert model.outcome == surface.DEFAULT_OUTCOME, action
        before = len(model.calls)
        widget = action.split(".")[0]
        if target == "answer":
            getattr(model, target)(widget)
            pressed = [surface.BOX_ANSWER, widget, surface.BUTTON_ANSWERS[widget]]
            outcome = surface.BUTTON_OUTCOMES[widget]
            answered = surface.BUTTON_ANSWERS[widget]
        else:
            getattr(model, target)()
            pressed = [surface.BOX_CLOSE, surface.CLOSED_ANSWER]
            outcome = surface.BOX_CLOSED_OUTCOMES[surface.WARNING_BOX]
            answered = surface.CLOSED_ANSWER
        recorded = model.calls[before:]
        assert recorded[0] == pressed, (action, recorded)
        assert recorded[-1] == [
            surface.GATE_OUTCOME,
            outcome,
            surface.CREATES_BOT[outcome],
        ], (action, recorded)
        assert model.outcome == outcome, action
        assert model.answered is answered, action


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    assert len(surface.ACTIONS) == len(surface.BUTTON_VALUES) + 1
    assert set(surface.ACTIONS) == {
        "ok.clicked",
        "yes.clicked",
        "no.clicked",
        "box.closed",
    }
    for name in surface.BUTTON_VALUES:
        assert surface.ACTIONS[f"{name}.clicked"] == "answer"
    assert surface.ACTIONS["box.closed"] == "close_window"
    for target in set(surface.ACTIONS.values()):
        assert callable(getattr(surface.PreflightModel, target)), target
    assert set(surface.BUTTON_ANSWERS) == set(surface.BUTTON_VALUES)
    assert set(surface.BUTTON_OUTCOMES) == set(surface.BUTTON_VALUES)


METHOD_MAP = {
    "PreflightResult": "preflight_result",
    "check_symbol": "PreflightModel.check",
    "format_result_for_user": "PreflightModel.format_result",
}

MODEL_MEMBERS = {
    "__init__",
    "answered",
    "outcome",
    "check",
    "_inspect_market",
    "_unlisted",
    "_capacity_warnings",
    "_finish",
    "format_result",
    "skip_extractor",
    "show_failure",
    "ask_warnings",
    "_raise_box",
    "answer",
    "close_window",
    "_settle",
    "_status_line_for",
    "_log_status",
    "report_module_missing",
    "report_error",
    "run_gate",
    "_leave_box",
}

WIZARD_MAP = {
    "extractor_skip": "PreflightModel.skip_extractor",
    "failure_box": "PreflightModel.show_failure",
    "warning_box": "PreflightModel.ask_warnings",
    "button_press": "PreflightModel.answer",
    "window_closed": "PreflightModel.close_window",
    "import_error": "PreflightModel.report_module_missing",
    "unexpected_error": "PreflightModel.report_error",
    "whole_gate": "PreflightModel.run_gate",
}


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


def resolve(dotted):
    """The member a dotted name in the map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def shipped_member_names():
    """Every function and class the shipped module defines, by name."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if (inspect.isfunction(value) or inspect.isclass(value))
        and getattr(value, "__module__", "") == shipped.__name__
    }


def test_every_shipped_member_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    assert shipped_member_names() == set(METHOD_MAP)
    assert len(METHOD_MAP) == 3
    for target in METHOD_MAP.values():
        assert resolve(target) is not None, target
    assert members(surface.PreflightModel) == MODEL_MEMBERS
    assert len(MODEL_MEMBERS) == 22
    assert len(WIZARD_MAP) == 8
    for target in WIZARD_MAP.values():
        assert resolve(target) is not None, target
    assert {target.split(".")[-1] for target in WIZARD_MAP.values()} < MODEL_MEMBERS


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "check_symbol" in shipped_member_names()
    assert "format_result_for_user" in shipped_member_names()
    assert "PreflightResult" in shipped_member_names()
    assert "logger" not in shipped_member_names()
    assert "dataclass" not in shipped_member_names()
    assert "precision_to_decimals" not in shipped_member_names()
    with pytest.raises(AttributeError):
        resolve("PreflightModel.no_such_member")
    assert MODEL_MEMBERS - {"check"} != MODEL_MEMBERS
    assert members(surface.PreflightModel) - {"answer"} != MODEL_MEMBERS
    assert isinstance(vars(surface.PreflightModel)["outcome"], property)
    assert isinstance(vars(surface.PreflightModel)["answered"], property)
    assert set(METHOD_MAP) - {"check_symbol"} != set(METHOD_MAP)


def test_the_result_schema_matches_the_shipped_dataclass():
    """A field appeared on one result and not on the other."""
    fields = dataclasses.fields(shipped.PreflightResult)
    assert tuple(field.name for field in fields) == surface.RESULT_FIELDS
    assert len(surface.RESULT_FIELDS) == 14
    defaults = {}
    for field in fields:
        if field.default is not dataclasses.MISSING:
            defaults[field.name] = field.default
    assert defaults == surface.RESULT_DEFAULTS
    assert len(surface.RESULT_DEFAULTS) == 9
    required = [
        field.name
        for field in fields
        if field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
    ]
    assert required == ["success", "exchange_id", "symbol", "message"]
    blank = surface.preflight_result(True, "e", "s", "m")
    assert list(blank) == list(surface.RESULT_FIELDS)
    assert blank["warnings"] == []
    assert blank["market_active"] is False
    assert blank["active_reported"] is False
    assert blank["price_read"] is False
    assert blank["elapsed_ms"] == 0.0
    first = surface.preflight_result(True, "e", "s", "m")
    first["warnings"].append("only mine")
    assert surface.preflight_result(True, "e", "s", "m")["warnings"] == []
    assert dataclasses.asdict(shipped.PreflightResult(True, "e", "s", "m")) == blank


def test_the_check_signature_matches_the_shipped_check():
    """The check stopped taking the arguments the wizard passes it."""
    import inspect

    old = inspect.signature(shipped.check_symbol).parameters
    new = inspect.signature(surface.PreflightModel.check).parameters
    assert list(new) == ["self"] + list(old)
    assert list(old) == [
        "exchange_id",
        "symbol",
        "target_balance",
        "api_key",
        "api_secret",
        "passphrase",
    ]
    optional = [name for name, p in old.items() if p.default is not p.empty]
    assert optional == ["api_key", "api_secret", "passphrase"]
    assert [name for name, p in new.items() if p.default is not p.empty] == optional
    for name in optional:
        assert not old[name].default
        assert not new[name].default
    assert surface.CREDENTIAL_ABSENT is None
    assert [name for name, _ in surface.CREDENTIAL_FIELDS] == optional


def test_the_boxes_start_no_timer(monkeypatch):
    """A wait appeared on one side and not the other.

    The gate waits on the exchange and on the operator, not on a clock.
    The watcher counts every timer any Qt object starts while both
    boxes are built, and its positive control proves it counts.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
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
        for name in ("blocked", "warned"):
            old_box_widget(name, monkeypatch)
            new_box(new_payload(name, monkeypatch))
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


def test_the_picture_reports_a_different_gate_case(monkeypatch):
    """The image comparison passes whatever the second side paints.

    Two real gate cases, one driven into each side. One raises the
    warning box and the other the failure box, so a pass proves the
    comparison reports a box painted differently.
    """
    app()
    assert new_payload("warned", monkeypatch)["box"] == surface.WARNING_BOX
    assert new_payload("blocked", monkeypatch)["box"] == surface.FAILURE_BOX
    assert_pictures_differ(
        old_side=render_offscreen(old_box_widget("warned", monkeypatch), PIXEL_SIZE),
        new_side=render_offscreen(
            new_box(new_payload("blocked", monkeypatch)), PIXEL_SIZE
        ),
        note="warned from the wizard against blocked from the surface",
    )


def disguise(text):
    """The same text, one letter for another, at the same length."""
    return "".join("Z" if letter.isalpha() else letter for letter in text)


def test_a_same_length_text_change_is_compared_as_an_exact_string(monkeypatch):
    """A same-length text swap was left to the render to report.

    Whether a swap of equal length and equal word shape moves a pixel
    depends on the fonts the host installs, so no render carries this
    proof on every machine. The body text is read off the wizard's box
    and off the surface and compared character for character.
    """
    app()
    for name in BOX_CASES:
        old = run_old_gate(name, None, False, monkeypatch)
        new = run_new_gate(name, None, False, monkeypatch)
        assert new["box_body"] == old["box_body"], name
        assert new["report"] == old["report"], name
    body = run_old_gate("warned", None, False, monkeypatch)["box_body"]
    swapped = disguise(body)
    assert swapped != body
    assert len(swapped) == len(body)
    assert swapped.count("\n") == body.count("\n")


def test_the_window_title_a_picture_cannot_see_is_compared_as_a_string(monkeypatch):
    """The title bar is not painted into an offscreen render.

    A grab of a message box carries its contents, not its frame, so a
    wrong title reaches no pixel. Both titles are read off the two
    boxes and compared character for character.
    """
    app()
    for name in BOX_CASES:
        old = old_box_widget(name, monkeypatch)
        payload = new_payload(name, monkeypatch)
        assert payload["box_title"] == old.windowTitle(), name
    painted = new_box(new_payload("warned", monkeypatch))
    assert painted.windowTitle() == old_box_widget("warned", monkeypatch).windowTitle()
    assert surface.FAILURE_TITLE != surface.WARNING_TITLE
    assert new_payload("blocked", monkeypatch)["box_title"] == surface.FAILURE_TITLE
    assert new_payload("warned", monkeypatch)["box_title"] == surface.WARNING_TITLE


def test_the_default_button_a_picture_may_not_show_is_compared_as_a_flag(monkeypatch):
    """Which button the Return key presses was left to the render.

    Whether a default button paints a mark is the platform style's
    choice, so the flag is read off both boxes as a number instead.
    """
    app()
    old_warning = old_box_widget("warned", monkeypatch)
    old_failure = old_box_widget("blocked", monkeypatch)
    assert default_button_value(old_warning) == surface.NO_BUTTON_VALUE
    assert default_button_value(old_failure) == surface.NO_DEFAULT_BUTTON_VALUE
    assert old_failure.defaultButton() is None
    assert old_warning.defaultButton() is not None
    warned = new_payload("warned", monkeypatch)
    blocked = new_payload("blocked", monkeypatch)
    assert warned["warning_widget"]["default_button_value"] == default_button_value(
        old_warning
    )
    assert blocked["failure_widget"]["default_button_value"] == default_button_value(
        old_failure
    )
    assert surface.WARNING_DEFAULT_BUTTON == surface.NO
    assert surface.BUTTON_VALUES[surface.WARNING_DEFAULT_BUTTON] == (
        surface.WARNING_DEFAULT_BUTTON_VALUE
    )
    assert surface.WARNING_DEFAULT_BUTTON_VALUE != surface.YES_BUTTON_VALUE
    assert default_button_value(new_box(warned)) == default_button_value(old_warning)
    assert default_button_value(new_box(blocked)) == default_button_value(old_failure)


def test_the_answer_and_the_outcome_a_picture_cannot_see_are_compared_as_values(
    monkeypatch,
):
    """The answer and the outcome are painted nowhere.

    Neither reaches a pixel, so no render can report a wrong one. Both
    are compared as exact values in every gate step, and the values
    they can hold are pinned here.
    """
    app()
    yes = run_old_gate("warned", surface.YES, False, monkeypatch)
    no = run_old_gate("warned", surface.NO, False, monkeypatch)
    assert yes["answered"] is True
    assert no["answered"] is False
    assert yes["outcome"] == surface.OUTCOME_PROCEED
    assert no["outcome"] == surface.OUTCOME_DECLINED
    assert run_new_gate("warned", surface.YES, False, monkeypatch)["answered"] is True
    assert run_new_gate("warned", surface.NO, False, monkeypatch)["answered"] is False
    assert set(surface.ANSWERS) == {True, False}
    assert surface.DEFAULT_ANSWER is surface.ANSWER_CANCEL is False
    assert surface.CLOSED_ANSWER is surface.ANSWER_CANCEL
    assert surface.ANSWER_PROCEED is True
    assert surface.DEFAULT_OUTCOME == surface.OUTCOME_BLOCKED
    assert surface.CLOSED_OUTCOME == surface.OUTCOME_DECLINED
    assert surface.BOX_CLOSED_OUTCOMES == {
        surface.FAILURE_BOX: surface.OUTCOME_BLOCKED,
        surface.WARNING_BOX: surface.OUTCOME_DECLINED,
    }
    assert len(surface.OUTCOMES) == 6
    assert len(set(surface.OUTCOMES)) == 6
    assert surface.CREATES_BOT == {
        surface.OUTCOME_PROCEED: True,
        surface.OUTCOME_BLOCKED: False,
        surface.OUTCOME_DECLINED: False,
        surface.OUTCOME_SKIPPED: True,
        surface.OUTCOME_MODULE_MISSING: True,
        surface.OUTCOME_ERRORED: True,
    }
    assert set(surface.CREATES_BOT) == set(surface.OUTCOMES)
    assert set(surface.OUTCOME_LEVELS) == set(surface.OUTCOMES)
    assert sum(1 for makes in surface.CREATES_BOT.values() if not makes) == 2
    answered = new_payload("warned", monkeypatch, button=surface.YES)
    refused = new_payload("warned", monkeypatch, button=surface.NO)
    assert answered["answered"] is True
    assert refused["answered"] is False
    assert answered["box_body"] == refused["box_body"]
    assert_pictures_match(
        old_side=render_offscreen(old_box_widget("warned", monkeypatch), PIXEL_SIZE),
        new_side=render_offscreen(new_box(answered), PIXEL_SIZE),
        note="the answer reaches no pixel",
    )


def test_the_boxes_declare_no_skin_of_their_own(monkeypatch):
    """A colour the surface ships is one the wizard's box never paints.

    The wizard's boxes carry no style sheet of their own. The
    application theme paints them, and it paints both sides the same.
    The style sheet is read off the wizard's box and off the surface,
    and the two shipped sides paint one picture.
    """
    app()
    assert surface.SKIN == {}
    assert len(surface.SKIN) == 0
    assert surface.STYLE_SHEET == ""
    payload = new_payload("warned", monkeypatch)
    assert payload["skin"] == {}
    assert payload["warning_widget"]["style_sheet"] == ""
    assert payload["failure_widget"]["style_sheet"] == ""
    for name in BOX_CASES:
        assert old_box_widget(name, monkeypatch).styleSheet() == "", name
        assert new_box(new_payload(name, monkeypatch)).styleSheet() == "", name
    assert_pictures_match(
        old_side=render_offscreen(old_box_widget("warned", monkeypatch), PIXEL_SIZE),
        new_side=render_offscreen(
            new_box(new_payload("warned", monkeypatch)), PIXEL_SIZE
        ),
        note="neither side carries a skin of its own",
    )


def test_the_layout_is_the_boxes_own(monkeypatch):
    """A margin, a spacing or an order drifted from the wizard's box."""
    app()
    old = old_box_widget("warned", monkeypatch)
    layout = old.layout()
    margins = layout.contentsMargins()
    assert surface.LAYOUT["margins_px"] == [
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ]
    assert surface.LAYOUT["spacing_px"] == layout.spacing()
    assert surface.LAYOUT["margins_px"] == [11, 11, 11, 11]
    assert surface.LAYOUT["spacing_px"] == 6
    assert len(surface.LAYOUT["order"]) == layout.count() == 4
    assert surface.LAYOUT["child_stretch"] == [0 for _ in range(layout.count())]
    assert len(surface.LAYOUT["order"]) == len(surface.LAYOUT["child_stretch"])
    placed = [layout.itemAt(index).widget() for index in range(layout.count())]
    assert [
        widget.objectName() if widget else surface.SPACER_CHILD for widget in placed
    ] == [
        surface.CHILD_OBJECT_NAMES.get(name, surface.SPACER_CHILD)
        for name in surface.LAYOUT["order"]
    ]
    assert placed[1] is None
    assert surface.LAYOUT["order"][1] == surface.SPACER_CHILD
    assert len(surface.CHILD_OBJECT_NAMES) == 3
    assert len(set(surface.CHILD_OBJECT_NAMES.values())) == 3
    assert new_payload("warned", monkeypatch)["layout"] == surface.LAYOUT
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    holder = QWidget()
    moved = QVBoxLayout(holder)
    moved.setContentsMargins(3, 3, 3, 3)
    moved.setSpacing(1)
    found = moved.contentsMargins()
    assert [found.left(), found.top(), found.right(), found.bottom()] == [3, 3, 3, 3]
    assert [
        found.left(),
        found.top(),
        found.right(),
        found.bottom(),
    ] != surface.LAYOUT["margins_px"]
    assert moved.spacing() == 1 != surface.LAYOUT["spacing_px"]


def test_the_model_calls_stop_where_the_check_stops(monkeypatch):
    """One side recorded a step the other never reached."""
    install_ccxt(monkeypatch, CASES["happy"]["spec"])
    freeze_clock(monkeypatch)
    model = surface.PreflightModel()
    model.check(*CASES["happy"]["args"])
    good = [call[0] for call in model.calls]
    assert good == [
        surface.CHECK_START,
        surface.CCXT_IMPORT,
        surface.EXCHANGE_LOOKUP,
        surface.CONFIG_BUILD,
        surface.EXCHANGE_CREATE,
        surface.MARKETS_LOAD,
        surface.MARKET_READ,
        surface.PRECISION_READ,
        surface.TICKER_FETCH,
        surface.RESULT_RETURN,
    ]
    stopped = {}
    for name in (
        "no_ccxt",
        "unknown_exchange",
        "symbol_casing",
        "symbol_missing",
        "load_raises",
        "ticker_raises",
        "two_warnings",
        "unknown_input",
    ):
        install_ccxt(monkeypatch, CASES[name]["spec"])
        freeze_clock(monkeypatch)
        each = surface.PreflightModel()
        each.check(*CASES[name]["args"])
        stopped[name] = [call[0] for call in each.calls]
    assert stopped["no_ccxt"] == [
        surface.CHECK_START,
        surface.CCXT_MISSING,
        surface.RESULT_RETURN,
    ]
    assert stopped["unknown_exchange"][-2] == surface.EXCHANGE_MISSING
    assert stopped["symbol_casing"][-2] == surface.SYMBOL_CASING
    assert stopped["symbol_missing"][-3] == surface.SYMBOL_ALTERNATIVES
    assert stopped["symbol_missing"][-2] == surface.SYMBOL_MISSING
    assert stopped["load_raises"][-2] == surface.CHECK_ERROR
    assert surface.MARKETS_LOAD not in stopped["load_raises"]
    assert stopped["ticker_raises"].count(surface.TICKER_FAILED) == 1
    assert surface.TICKER_FETCH not in stopped["ticker_raises"]
    assert stopped["two_warnings"].count(surface.WARNING_ADD) == 2
    assert good.count(surface.WARNING_ADD) == 0
    assert stopped["unknown_input"][-2] == surface.CHECK_ERROR
    assert len({tuple(steps) for steps in stopped.values()}) == 8


CALL_NAMES = {
    "CHECK_START": "check.start",
    "CCXT_IMPORT": "ccxt.import",
    "CCXT_MISSING": "ccxt.missing",
    "EXCHANGE_LOOKUP": "exchange.lookup",
    "EXCHANGE_MISSING": "exchange.missing",
    "CONFIG_BUILD": "config.build",
    "EXCHANGE_CREATE": "exchange.create",
    "MARKETS_LOAD": "markets.load",
    "SYMBOL_ALTERNATIVES": "symbol.alternatives",
    "SYMBOL_CASING": "symbol.casing",
    "SYMBOL_MISSING": "symbol.missing",
    "MARKET_READ": "market.read",
    "PRECISION_READ": "precision.read",
    "TICKER_FETCH": "ticker.fetch",
    "TICKER_FAILED": "ticker.failed",
    "WARNING_ADD": "warning.add",
    "RESULT_RETURN": "result.return",
    "CHECK_ERROR": "check.error",
    "REPORT_LINES": "report.lines",
    "REPORT_RETURN": "report.return",
    "BOX_CREATE": "box.create",
    "BOX_SET_WINDOW_TITLE": "box.setWindowTitle",
    "BOX_SET_TEXT": "box.setText",
    "BOX_SET_ICON": "box.setIcon",
    "BOX_SET_STANDARD_BUTTONS": "box.setStandardButtons",
    "BOX_SET_DEFAULT_BUTTON": "box.setDefaultButton",
    "BOX_EXEC": "box.exec",
    "BOX_ANSWER": "box.answer",
    "BOX_CLOSE": "box.close",
    "STATUS_LOG": "status.log",
    "GATE_OUTCOME": "gate.outcome",
}


def test_the_call_names_are_the_ones_the_trace_writes():
    """The trace and the surface stopped agreeing on what to call a step.

    The Qt side of the trace builds each label from these literals, so
    a label read out of the surface cannot make both sides agree by
    definition.
    """
    for constant, literal in CALL_NAMES.items():
        assert getattr(surface, constant) == literal, constant
    assert len(set(CALL_NAMES.values())) == 31
    assert len(CALL_NAMES) == 31


def test_the_symbol_spellings_are_the_shipped_checks_own():
    """The list of spellings the check tries changed length or order."""
    assert surface.symbol_alternatives("RAVE/USD") == [
        "RAVE/USD",
        "rave/usd",
        "RAVE-USD",
        "RAVE/USD",
    ]
    assert surface.symbol_alternatives("rave-usd") == [
        "RAVE-USD",
        "rave-usd",
        "rave-usd",
        "rave/usd",
    ]
    assert len(surface.symbol_alternatives("a/b")) == 4
    assert surface.symbol_alternatives("") == ["", "", "", ""]
    assert surface.SEPARATOR_SLASH == "/"
    assert surface.SEPARATOR_DASH == "-"
    assert surface.exchange_name("coinbase") == "Coinbase"
    assert surface.exchange_name("") == ""
    assert surface.exchange_name("BINANCE") == "Binance"
    assert surface.elapsed_since(1.0, 1.25) == 250.0
    assert surface.elapsed_since(1.0, 1.0) == 0.0
    assert surface.MS_PER_SECOND == 1000
    assert surface.MIN_COST_HEADROOM == 3
    assert surface.PRECISION_FALLBACK_DECIMALS == 0
    assert surface.gate_symbol({}) == "BTC/USDT"
    assert surface.gate_symbol({"target_asset": "RAVE", "base_currency": "USD"}) == (
        "RAVE/USD"
    )
    assert surface.gate_target_balance({}) == 200.0
    assert surface.gate_target_balance({"investment_amount": 5.0}) == 5.0
    assert (
        surface.gate_target_balance({"investment_amount": 5.0, "target_balance": 9.0})
        == 9.0
    )
    assert surface.DEFAULT_TARGET_ASSET == "BTC"
    assert surface.DEFAULT_BASE_CURRENCY == "USDT"
    assert surface.DEFAULT_TARGET_BALANCE == 200.0
    assert surface.EXTRACTOR_MODE == "extractor"


BLIND_TO_THE_PICTURE = {
    "window_title": (
        "test_the_window_title_a_picture_cannot_see_is_compared_as_a_string"
    ),
    "same_length_text": (
        "test_a_same_length_text_change_is_compared_as_an_exact_string"
    ),
    "default_button": (
        "test_the_default_button_a_picture_may_not_show_is_compared_as_a_flag"
    ),
    "answer": (
        "test_the_answer_and_the_outcome_a_picture_cannot_see_are_compared_as_values"
    ),
    "outcome": (
        "test_the_answer_and_the_outcome_a_picture_cannot_see_are_compared_as_values"
    ),
    "status_line": "test_the_status_lines_are_the_wizards_own",
    "log_line": "test_the_error_log_is_the_shipped_checks_own",
    "check_result": "test_the_check_returns_the_same_result",
    "exchange_config": "test_the_config_the_check_sends_is_the_shipped_configs_own",
    "accessible_name": "test_the_two_boxes_carry_the_same_properties",
    "modal_flag": "test_the_two_boxes_carry_the_same_properties",
    "stays_on_top_flag": "test_the_two_boxes_carry_the_same_properties",
    "window_size": "test_the_two_boxes_carry_the_same_properties",
    "button_enabled": "test_the_button_labels_are_the_boxes_own",
    "request_timeout_ms": (
        "test_the_config_the_check_sends_is_the_shipped_configs_own"
    ),
    "timer_delay": "test_the_boxes_start_no_timer",
}


def test_everything_a_picture_cannot_see_is_named_and_covered(monkeypatch):
    """A value no render can report was left to the render to report.

    Sixteen values never reach a pixel comparison, each named here with
    the check that does cover it. The title bar is outside the grab.
    The answer, the outcome, the status line and the log line are
    painted nowhere. The check result and the settings the check sends
    the exchange are read, not drawn. The accessible name, the modal
    flag and the always-on-top flag paint no mark, and the window size
    is overwritten by the render size before the grab. Whether a button
    can be pressed paints nothing, because every button is enabled.
    Whether the default button paints a mark is the platform style's
    choice, so it is read as a number. Two strings of one length and
    one word shape paint the same boxes on a host with no glyphs. The
    gate starts no timer, so no delay can be seen.
    """
    app()
    assert len(BLIND_TO_THE_PICTURE) == 16
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    old = old_box_widget("warned", monkeypatch)
    payload = new_payload("warned", monkeypatch)
    properties = payload["warning_widget"]
    assert properties["size_px"] == [old.width(), old.height()]
    assert properties["accessible_name"] == old.accessibleName() == ""
    assert properties["modal"] is old.isModal() is True
    assert properties["stays_on_top"] is False
    assert payload["request_timeout_ms"] == surface.REQUEST_TIMEOUT_MS
    assert payload["timers"] == {}
    assert payload["timer_delays_ms"] == []
    assert_pictures_match(
        old_side=render_offscreen(old, PIXEL_SIZE),
        new_side=render_offscreen(new_box(payload), PIXEL_SIZE),
    )


def test_view_model_is_json_serialisable(monkeypatch):
    """The bridge cannot encode what the surface returns."""
    payload = new_payload("warned", monkeypatch, button=surface.YES)
    encoded = json.loads(json.dumps(payload))
    assert encoded["outcome"] == "proceed"
    assert encoded["answered"] is True
    assert encoded["checked"] is True
    assert encoded["box"] == "warning_box"
    assert encoded["box_title"] == "Pre-flight check — warnings"
    assert encoded["box_buttons"] == ["yes", "no"]
    assert encoded["result"]["symbol"] == "RAVE/USD"
    assert encoded["result"]["success"] is True
    assert len(encoded["result"]["warnings"]) == 1
    assert encoded["status_line"] == "Pre-flight OK for RAVE/USD on coinbase (250 ms)"
    assert encoded["status_level"] == "info"
    assert encoded["failure_widget"]["window_title"] == "Pre-flight check failed"
    assert encoded["failure_widget"]["buttons_value"] == 1024
    assert encoded["warning_widget"]["buttons_value"] == 81920
    assert encoded["warning_widget"]["default_button_value"] == 65536
    assert encoded["buttons"]["yes"]["text"] == "&Yes"
    assert encoded["buttons"]["no"]["outcome"] == "declined"
    assert encoded["buttons"]["ok"]["answer"] is False
    assert encoded["outcomes"] == list(surface.OUTCOMES)
    assert encoded["skin"] == {}
    assert encoded["timer_delays_ms"] == []
    assert encoded["request_timeout_ms"] == 15000
    assert encoded["result_fields"] == list(surface.RESULT_FIELDS)
    assert encoded["calls"][-1] == ["gate.outcome", "proceed", True]
    assert len(encoded["calls"]) == 23


def test_bridge_registers_the_preflight_check_method(monkeypatch):
    """The renderer cannot reach the pre-flight surface through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "preflight_check.state"
    assert registry[surface.METHOD] is surface.view_model
    install_ccxt(monkeypatch, GATE_CASES["warned"]["spec"])
    freeze_clock(monkeypatch)
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 61,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "run": True,
                    "config": GATE_CASES["warned"]["config"],
                    "button": surface.YES,
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["outcome"] == surface.OUTCOME_PROCEED
    assert result["answered"] is True
    assert result["box"] == surface.WARNING_BOX
    assert result["result"]["symbol"] == "RAVE/USD"
    assert "less than 3x min-order-cost" in result["result"]["warnings"][0]


def test_the_bridge_carries_every_button_and_the_closed_window(monkeypatch):
    """A button press over the bridge changed nothing."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 62, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    for button, outcome in (
        (surface.YES, surface.OUTCOME_PROCEED),
        (surface.NO, surface.OUTCOME_DECLINED),
        (surface.OK, surface.OUTCOME_DECLINED),
        (None, surface.OUTCOME_DECLINED),
    ):
        install_ccxt(monkeypatch, GATE_CASES["warned"]["spec"])
        freeze_clock(monkeypatch)
        pressed = call(
            {
                "reset": True,
                "run": True,
                "config": GATE_CASES["warned"]["config"],
                "button": button,
            }
        )
        assert pressed["outcome"] == outcome, button
        assert pressed["answered"] is surface.BUTTON_ANSWERS.get(
            button, surface.DEFAULT_ANSWER
        ), button
    install_ccxt(monkeypatch, GATE_CASES["warned"]["spec"])
    freeze_clock(monkeypatch)
    closed = call(
        {
            "reset": True,
            "run": True,
            "config": GATE_CASES["warned"]["config"],
            "closed": True,
        }
    )
    assert closed["outcome"] == surface.OUTCOME_DECLINED
    assert closed["answered"] is surface.CLOSED_ANSWER
    install_ccxt(monkeypatch, GATE_CASES["blocked"]["spec"])
    freeze_clock(monkeypatch)
    blocked = call(
        {"reset": True, "run": True, "config": GATE_CASES["blocked"]["config"]}
    )
    assert blocked["outcome"] == surface.OUTCOME_BLOCKED
    assert blocked["box"] == surface.FAILURE_BOX
    assert blocked["box_buttons"] == [surface.OK]
    idle = call({"reset": True})
    assert idle["outcome"] == surface.DEFAULT_OUTCOME
    assert idle["checked"] is False
    assert idle["calls"] == []
    call({"reset": True})


def test_the_bridge_keeps_the_outcome_until_a_reset(monkeypatch):
    """The gate forgot its answer between two bridge calls."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 63, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    install_ccxt(monkeypatch, GATE_CASES["warned"]["spec"])
    freeze_clock(monkeypatch)
    first = call(
        {
            "reset": True,
            "run": True,
            "config": GATE_CASES["warned"]["config"],
            "button": surface.YES,
        }
    )
    kept = call({})
    assert kept["outcome"] == first["outcome"]
    assert kept["calls"] == first["calls"]
    assert kept["answered"] is True
    fresh = call({"reset": True})
    assert fresh["outcome"] == surface.DEFAULT_OUTCOME
    assert fresh["calls"] == []
    assert fresh["answered"] is surface.DEFAULT_ANSWER
    call({"reset": True})


BRIDGE_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'preflight_check.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

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

FAKE_CCXT = (
    "import sys, types\n"
    "_module = types.ModuleType('ccxt')\n"
    "class _Venue:\n"
    "    precisionMode = 4\n"
    "    def __init__(self, config):\n"
    "        self.config = config\n"
    "    def load_markets(self):\n"
    "        return {'RAVE/USD': {'active': True,\n"
    "            'limits': {'amount': {'min': 0.01}, 'cost': {'min': 1.0}},\n"
    "            'precision': {'price': 1e-06, 'amount': 1e-08}}}\n"
    "    def fetch_ticker(self, symbol):\n"
    "        return {'last': 0.0123}\n"
    "_module.coinbase = _Venue\n"
    "sys.modules['ccxt'] = _module\n"
)

HEADLESS_PROBE = (
    BLOCK_QT + FAKE_CCXT + "import json, sys\n"
    "from src.gui.main_tabs import preflight_check_surface as s\n"
    "model = s.PreflightModel()\n"
    "outcome = model.run_gate({'exchange_id': 'coinbase',\n"
    "    'target_asset': 'RAVE', 'base_currency': 'USD',\n"
    "    'target_balance': 2.0}, '', s.YES)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'outcome': outcome, 'answered': model.answered,\n"
    "    'box': model.box, 'box_title': model.box_title,\n"
    "    'status_line': model.status_line,\n"
    "    'warnings': model.result['warnings'],\n"
    "    'report_lines': model.report.count(chr(10)) + 1,\n"
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
    """Reaching the pre-flight surface pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["failure_widget"]["window_title"] == "Pre-flight check failed"
    assert result["warning_widget"]["window_title"] == "Pre-flight check — warnings"
    assert result["buttons"]["yes"]["text"] == "&Yes"
    assert result["buttons"]["no"]["text"] == "&No"
    assert result["buttons"]["ok"]["text"] == "OK"
    assert result["outcome"] == "blocked"
    assert result["answered"] is False
    assert result["request_timeout_ms"] == 15000


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_runs_the_whole_gate_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["outcome"] == "proceed"
    assert answered["answered"] is True
    assert answered["box"] == "warning_box"
    assert answered["box_title"] == "Pre-flight check — warnings"
    assert answered["status_line"].startswith("Pre-flight OK for RAVE/USD on coinbase")
    assert len(answered["warnings"]) == 1
    assert "less than 3x min-order-cost" in answered["warnings"][0]
    assert answered["report_lines"] == 14
    assert answered["calls"] == 23


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_raises_the_boxes():
    """The Qt block let a module through that imports PySide6."""
    probe = BLOCK_QT + (
        "import json\n"
        "try:\n"
        "    from src.gui import instance_consent_dialog\n"
        "    blocked = False\n"
        "except ImportError:\n"
        "    blocked = True\n"
        "print(json.dumps({'blocked': blocked}))\n"
    )
    assert run_script(probe)["blocked"] is True


def test_the_shipped_check_needs_no_qt_either():
    """The shipped check grew a Qt import the surface would inherit."""
    probe = BLOCK_QT + (
        "import json, sys\n"
        "from src.gui import preflight_check\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
        "    'fields': [f.name for f in "
        "__import__('dataclasses').fields(preflight_check.PreflightResult)]}))\n"
    )
    answered = run_script(probe)
    assert answered["qt"] is False
    assert answered["fields"] == list(surface.RESULT_FIELDS)
