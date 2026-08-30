"""The Qt buy confirmation dialog and the Qt-free surface, side by side.

A failure means the view model writes a different banner, a different
detail row, a different button label, a different answer, a different
wait or a different sequence of calls than ``BuyConfirmationDialog`` and
``_BuyConfirmationBroker`` do on the same request.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import buy_confirmation_dialog as qt_dialog
from src.gui.main_tabs import buy_confirmation_surface as surface
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

LOGGER_NAME = "acervator.buy_confirmation"

DIALOG_PATH = REPO_ROOT / "src/gui/buy_confirmation_dialog.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/buy_confirmation_surface.py"

BUILD = "build"
CLICK = "click"

PIXEL_SIZE = (640, 480)

CALLS: list[list] = []


def app():
    """The process application object every render and widget needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def digest(trace):
    return hashlib.sha256(json.dumps(trace, sort_keys=True).encode("utf-8")).hexdigest()


class ClassPatch:
    """Replace methods on a class and put the class back exactly as found."""

    def __init__(self, target):
        self.target = target
        self.saved: list[tuple] = []

    def set(self, name, value):
        self.saved.append(
            (name, name in vars(self.target), vars(self.target).get(name))
        )
        setattr(self.target, name, value)

    def undo(self):
        for name, existed, old in reversed(self.saved):
            if existed:
                setattr(self.target, name, old)
            else:
                delattr(self.target, name)
        self.saved = []


class _Pending(dict):
    """The broker's pending map, with its two writes recorded."""

    def __setitem__(self, key, value):
        CALLS.append([surface.PENDING_SET, key])
        dict.__setitem__(self, key, value)

    def pop(self, key, default=None):
        CALLS.append([surface.PENDING_POP, key])
        return dict.pop(self, key, default)


class _SignalRecorder:
    """Stands in for the Qt signal so the emit is recorded, not delivered."""

    def __init__(self, answer=None):
        self.answer = answer
        self.emitted: list[tuple] = []

    def emit(self, *args):
        CALLS.append([surface.SIGNAL_EMIT, args[0]])
        self.emitted.append(args)
        payload = args[1]
        if self.answer is not None:
            payload["loop"].call_soon(payload["future"].set_result, self.answer)


class _Future:
    """Stands in for the bot's future, with ``done`` and the resolve read."""

    def __init__(self, already_done=False):
        self._done = already_done
        self.resolved: list = []

    def done(self):
        CALLS.append([surface.FUTURE_DONE, self._done])
        return self._done

    def set_result(self, value):
        self.resolved.append(value)


class _Loop:
    """Stands in for the bot's event loop, recording the resolve."""

    def call_soon_threadsafe(self, callback, *args):
        CALLS.append([surface.FUTURE_SET_RESULT, args[0]])
        callback(*args)


class _LoopProxy:
    """The real running loop, with ``create_future`` recorded."""

    def __init__(self, loop):
        self._loop = loop

    def create_future(self):
        CALLS.append([surface.FUTURE_CREATE])
        return self._loop.create_future()

    def __getattr__(self, name):
        return getattr(self._loop, name)


class _AsyncioProxy:
    """The real ``asyncio`` module, with the two calls the broker makes read."""

    TimeoutError = asyncio.TimeoutError

    def get_running_loop(self):
        return _LoopProxy(asyncio.get_running_loop())

    def wait_for(self, future, timeout):
        CALLS.append([surface.WAIT_FOR, timeout])
        return asyncio.wait_for(future, timeout)

    def __getattr__(self, name):
        return getattr(asyncio, name)


def trace_widgets(monkeypatch):
    """Swap the dialog's widget factories for recording ones.

    Every recorded value is read back off the real widget, so a wrong
    value reaches the trace rather than the value the dialog was told.
    The wrappers sit on the widget instances, so no Qt class is
    subclassed and the widget tree stays the one the dialog builds.
    """
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

    labels: list = []
    buttons: list = []
    label_tags = (surface.REASON, surface.DETAILS)
    button_tags = (surface.YES, surface.NO, surface.SKIP)

    def wrap_label(label, tag):
        def set_font(font):
            QLabel.setFont(label, font)
            CALLS.append(
                [tag + ".setFont", label.font().pointSize(), label.font().bold()]
            )

        def set_style_sheet(sheet):
            QLabel.setStyleSheet(label, sheet)
            CALLS.append([tag + ".setStyleSheet", label.styleSheet()])

        def set_word_wrap(on):
            QLabel.setWordWrap(label, on)
            CALLS.append([tag + ".setWordWrap", label.wordWrap()])

        def set_text_format(fmt):
            QLabel.setTextFormat(label, fmt)
            CALLS.append([tag + ".setTextFormat", label.textFormat().name])

        label.setFont = set_font
        label.setStyleSheet = set_style_sheet
        label.setWordWrap = set_word_wrap
        label.setTextFormat = set_text_format

    def make_label(text=""):
        label = QLabel(text)
        tag = label_tags[len(labels)]
        label.acervator_tag = tag
        labels.append(label)
        CALLS.append([tag + ".create", label.text()])
        wrap_label(label, tag)
        return label

    def make_button(text=""):
        button = QPushButton(text)
        tag = button_tags[len(buttons)]
        button.acervator_tag = tag
        buttons.append(button)
        CALLS.append([tag + ".create", button.text()])

        def set_style_sheet(sheet):
            QPushButton.setStyleSheet(button, sheet)
            CALLS.append([tag + ".setStyleSheet", button.styleSheet()])

        button.setStyleSheet = set_style_sheet
        return button

    class FrameFactory:
        """Builds the separator and carries the shape constant it is given."""

        HLine = QFrame.HLine

        def __call__(self):
            frame = QFrame()
            frame.acervator_tag = surface.SEPARATOR
            CALLS.append([surface.SEPARATOR_CREATE])

            def set_frame_shape(shape):
                QFrame.setFrameShape(frame, shape)
                CALLS.append(
                    [surface.SEPARATOR_SET_FRAME_SHAPE, frame.frameShape().name]
                )

            frame.setFrameShape = set_frame_shape
            return frame

    def make_vbox(parent=None):
        layout = QVBoxLayout(parent)
        CALLS.append([surface.LAYOUT_CREATE])

        def add_widget(widget, *args):
            QVBoxLayout.addWidget(layout, widget, *args)
            CALLS.append([surface.LAYOUT_ADD_WIDGET, widget.acervator_tag])

        def add_layout(child, *args):
            QVBoxLayout.addLayout(layout, child, *args)
            CALLS.append([surface.LAYOUT_ADD_LAYOUT, surface.BUTTON_ROW])

        layout.addWidget = add_widget
        layout.addLayout = add_layout
        return layout

    def make_hbox():
        row = QHBoxLayout()
        CALLS.append([surface.ROW_CREATE])

        def add_widget(widget, *args):
            QHBoxLayout.addWidget(row, widget, *args)
            CALLS.append([surface.ROW_ADD_WIDGET, widget.acervator_tag])

        row.addWidget = add_widget
        return row

    monkeypatch.setattr(qt_dialog, "QLabel", make_label)
    monkeypatch.setattr(qt_dialog, "QPushButton", make_button)
    monkeypatch.setattr(qt_dialog, "QFrame", FrameFactory())
    monkeypatch.setattr(qt_dialog, "QVBoxLayout", make_vbox)
    monkeypatch.setattr(qt_dialog, "QHBoxLayout", make_hbox)
    return labels, buttons


def trace_dialog_methods(exec_result=surface.ACCEPTED, press=None):
    """Record the calls the dialog makes on itself, and stand in for exec.

    ``press`` names the button the operator hits while the modal is up,
    which drives the dialog's own ``_answer`` rather than reimplementing
    it. Returns the patch so the caller can put the class back.
    """
    from PySide6.QtWidgets import QDialog

    target = qt_dialog.BuyConfirmationDialog
    patch = ClassPatch(target)
    original_setattr = target.__setattr__

    def set_accessible_name(self, name):
        QDialog.setAccessibleName(self, name)
        CALLS.append([surface.DIALOG_SET_ACCESSIBLE_NAME, self.accessibleName()])

    def set_window_title(self, title):
        QDialog.setWindowTitle(self, title)
        CALLS.append([surface.DIALOG_SET_WINDOW_TITLE, self.windowTitle()])

    def set_modal(self, modal):
        QDialog.setModal(self, modal)
        CALLS.append([surface.DIALOG_SET_MODAL, self.isModal()])

    def set_minimum_width(self, width):
        QDialog.setMinimumWidth(self, width)
        CALLS.append([surface.DIALOG_SET_MINIMUM_WIDTH, self.minimumWidth()])

    def set_window_flag(self, flag, on):
        QDialog.setWindowFlag(self, flag, on)
        CALLS.append([surface.DIALOG_SET_WINDOW_FLAG, flag.name, bool(on)])

    def raise_window(self):
        QDialog.raise_(self)
        CALLS.append([surface.DIALOG_RAISE])

    def activate_window(self):
        QDialog.activateWindow(self)
        CALLS.append([surface.DIALOG_ACTIVATE])

    def accept(self):
        QDialog.accept(self)
        CALLS.append([surface.DIALOG_ACCEPT])

    def record_setattr(self, name, value):
        original_setattr(self, name, value)
        if name == "result_value":
            CALLS.append([surface.DIALOG_RESULT_VALUE, self.result_value])

    def exec_modal(self):
        CALLS.append([surface.DIALOG_EXEC])
        if press is not None:
            self._answer(surface.BUTTON_ANSWERS[press])
        CALLS.append([surface.DIALOG_EXEC_RESULT, exec_result])
        if exec_result == surface.ACCEPTED:
            return QDialog.DialogCode.Accepted
        return QDialog.DialogCode.Rejected

    patch.set("setAccessibleName", set_accessible_name)
    patch.set("setWindowTitle", set_window_title)
    patch.set("setModal", set_modal)
    patch.set("setMinimumWidth", set_minimum_width)
    patch.set("setWindowFlag", set_window_flag)
    patch.set("raise_", raise_window)
    patch.set("activateWindow", activate_window)
    patch.set("accept", accept)
    patch.set("exec", exec_modal)
    patch.set("__setattr__", record_setattr)
    return patch


PARAMS = {
    "plain": {
        "symbol": "BONK/USD",
        "reason": "Initial entry — bot holds zero",
        "cost_usd": 12.3456,
        "price": 0.00001234,
        "amount_asset": 1000000.5,
        "holdings_before": 250.125,
        "target_balance": 500.0,
    },
    "empty": {
        "symbol": "",
        "reason": "",
        "cost_usd": 0.0,
        "price": 0.0,
        "amount_asset": 0.0,
        "holdings_before": 0.0,
        "target_balance": 0.0,
    },
    "zero_price": {
        "symbol": "ETH/USD",
        "reason": "Zero price",
        "cost_usd": 10.0,
        "price": 0.0,
        "amount_asset": 0.0,
        "holdings_before": 5.0,
        "target_balance": 100.0,
    },
    "negative": {
        "symbol": "SOL/USD",
        "reason": "Negative everything",
        "cost_usd": -5.5,
        "price": -0.25,
        "amount_asset": -3.0,
        "holdings_before": -7.5,
        "target_balance": -100.0,
    },
    "very_large": {
        "symbol": "XRP/USD",
        "reason": "Very large numbers",
        "cost_usd": 1e18,
        "price": 9.87654321e12,
        "amount_asset": 1.23456789e15,
        "holdings_before": 1e20,
        "target_balance": 1e21,
    },
    "unicode": {
        "symbol": "Δ→⚡/USD",
        "reason": "Δ→⚡ over target — refuse or confirm",
        "cost_usd": 1.5,
        "price": 2.5,
        "amount_asset": 0.6,
        "holdings_before": 1.0,
        "target_balance": 10.0,
    },
    "long_spaced_reason": {
        "symbol": "DOGE/USD",
        "reason": "refuse this buy " * 13,
        "cost_usd": 1.0,
        "price": 1.0,
        "amount_asset": 1.0,
        "holdings_before": 1.0,
        "target_balance": 1.0,
    },
    "long_reason": {
        "symbol": "DOGE/USD",
        "reason": "x" * 200,
        "cost_usd": 1.0,
        "price": 1.0,
        "amount_asset": 1.0,
        "holdings_before": 1.0,
        "target_balance": 1.0,
    },
    "no_separator": {
        "symbol": "BONK",
        "reason": "Symbol carries no slash",
        "cost_usd": 1.0,
        "price": 1.0,
        "amount_asset": 1.0,
        "holdings_before": 1.0,
        "target_balance": 1.0,
    },
    "markup_in_text": {
        "symbol": "A<b>&/USD",
        "reason": "a <b>bold</b> & risky reason",
        "cost_usd": 1.0,
        "price": 1.0,
        "amount_asset": 1.0,
        "holdings_before": 1.0,
        "target_balance": 1.0,
    },
    "unknown_input": {
        "symbol": "BONK/USD",
        "reason": "Cost is not a number",
        "cost_usd": "not-a-number",
        "price": 1.0,
        "amount_asset": 1.0,
        "holdings_before": 1.0,
        "target_balance": 1.0,
    },
    "none_price": {
        "symbol": "BONK/USD",
        "reason": "Price is None",
        "cost_usd": 1.0,
        "price": None,
        "amount_asset": 1.0,
        "holdings_before": 1.0,
        "target_balance": 1.0,
    },
}

UNBUILDABLE = ("unknown_input", "none_price")

SCRIPTS = {
    name + "_" + button: [(BUILD, name), (CLICK, button)]
    for name in PARAMS
    if name not in UNBUILDABLE
    for button in (surface.YES, surface.NO, surface.SKIP)
}
SCRIPTS.update({name + "_untouched": [(BUILD, name)] for name in PARAMS})
SCRIPTS["rebuild"] = [
    (BUILD, "plain"),
    (CLICK, surface.YES),
    (BUILD, "unicode"),
    (CLICK, surface.SKIP),
]
SCRIPTS["every_button_in_turn"] = [
    (BUILD, "plain"),
    (CLICK, surface.YES),
    (CLICK, surface.NO),
    (CLICK, surface.SKIP),
    (CLICK, surface.YES),
]
SCRIPTS["empty_script"] = []


def read_widgets(dialog, labels, buttons):
    """Every visible string and button state the built dialog carries."""
    return {
        "reason_text": labels[0].text(),
        "details_text": labels[1].text(),
        "yes_text": buttons[0].text(),
        "no_text": buttons[1].text(),
        "skip_text": buttons[2].text(),
        "yes_enabled": buttons[0].isEnabled(),
        "no_enabled": buttons[1].isEnabled(),
        "skip_enabled": buttons[2].isEnabled(),
        "result_value": dialog.result_value,
        "accepted": dialog.result() == 1,
    }


def read_model(model):
    """Every visible string and button state the view model carries."""
    return {
        "reason_text": model.reason_text,
        "details_text": model.details,
        "yes_text": surface.BUTTONS[surface.YES]["text"],
        "no_text": surface.BUTTONS[surface.NO]["text"],
        "skip_text": surface.BUTTONS[surface.SKIP]["text"],
        "yes_enabled": surface.BUTTONS[surface.YES]["enabled"],
        "no_enabled": surface.BUTTONS[surface.NO]["enabled"],
        "skip_enabled": surface.BUTTONS[surface.SKIP]["enabled"],
        "result_value": model.result_value,
        "accepted": model.accepted,
    }


def snapshot(error, view):
    """One step's whole state: the error, the outputs and the call list."""
    body = {"error": error, "calls": [list(call) for call in CALLS]}
    body.update(view)
    return body


def run_old(script, monkeypatch):
    """Drive ``BuyConfirmationDialog`` through the script, step by step."""
    app()
    CALLS.clear()
    labels, buttons = trace_widgets(monkeypatch)
    patch = trace_dialog_methods()
    try:
        dialog = None
        trace = [snapshot(None, {})]
        for step in script:
            error = None
            if step[0] == BUILD:
                labels.clear()
                buttons.clear()
                try:
                    dialog = qt_dialog.BuyConfirmationDialog(**PARAMS[step[1]])
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
            else:
                try:
                    dialog._answer(surface.BUTTON_ANSWERS[step[1]])
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
            view = {} if error else read_widgets(dialog, labels, buttons)
            trace.append(snapshot(error, view))
        return trace
    finally:
        patch.undo()


def run_new(script):
    """Drive the view model through the same script, step by step."""
    CALLS.clear()
    model = surface.BuyConfirmationModel()
    trace = [snapshot(None, {})]
    for step in script:
        error = None
        try:
            if step[0] == BUILD:
                model.build(**PARAMS[step[1]])
            else:
                model.answer(surface.BUTTON_ANSWERS[step[1]])
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        CALLS.clear()
        CALLS.extend(model.calls)
        view = {} if error else read_model(model)
        trace.append(snapshot(error, view))
    return trace


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_old_and_new_traces_are_identical(name, monkeypatch):
    """A step of the script leaves the two sides in a different state."""
    old = run_old(SCRIPTS[name], monkeypatch)
    new = run_new(SCRIPTS[name])
    assert new == old
    assert digest(new) == digest(old)


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_the_trace_holds_the_whole_dialog(name, monkeypatch):
    """The comparison passed by measuring nothing."""
    old = run_old(SCRIPTS[name], monkeypatch)
    assert len(old) == len(SCRIPTS[name]) + 1
    assert old[0] == {"error": None, "calls": []}
    for step in old[1:]:
        assert step["calls"] != []
        if step["error"] is None:
            assert isinstance(step["details_text"], str)
            assert step["result_value"] in surface.ANSWERS
            assert step["yes_text"] and step["no_text"] and step["skip_text"]
    if SCRIPTS[name]:
        assert old[-1]["calls"] != []


def test_the_scripts_reach_every_answer_and_every_failure(monkeypatch):
    """A state was never driven, so its parity was never compared."""
    answers = set()
    errors = set()
    reasons = set()
    for name in SCRIPTS:
        for step in run_old(SCRIPTS[name], monkeypatch):
            if step["error"]:
                errors.add(step["error"].split(":")[0])
            if step.get("result_value"):
                answers.add(step["result_value"])
            if step.get("reason_text") is not None:
                reasons.add(step["reason_text"])
    assert answers == {surface.ANSWER_YES, surface.ANSWER_NO, surface.ANSWER_SKIP}
    assert errors == {"ValueError", "TypeError"}
    assert "" in reasons
    assert "x" * 200 in reasons
    assert any("⚡" in text for text in reasons)


def test_a_build_that_cannot_format_stops_at_the_same_call(monkeypatch):
    """One side placed a widget the other never reached."""
    old = run_old([(BUILD, "unknown_input")], monkeypatch)
    new = run_new([(BUILD, "unknown_input")])
    assert old[1]["error"].startswith("ValueError")
    assert len(old[1]["calls"]) == 14
    assert old[1]["calls"][-1] == [surface.LAYOUT_ADD_WIDGET, surface.SEPARATOR]
    assert new[1] == old[1]
    good = run_old([(BUILD, "plain")], monkeypatch)
    assert good[1]["error"] is None
    assert len(good[1]["calls"]) == 29
    for name in UNBUILDABLE:
        failed = run_old([(BUILD, name)], monkeypatch)
        assert failed[1]["error"] is not None, name
        assert run_new([(BUILD, name)])[1] == failed[1], name
    assert len(UNBUILDABLE) == 2


def test_every_detail_row_is_the_dialogs_own(monkeypatch):
    """A detail row's wording, spacing or number format drifted."""
    old = run_old([(BUILD, "plain")], monkeypatch)
    painted = old[1]["details_text"]
    spec = PARAMS["plain"]
    assert painted == surface.details_text(
        spec["symbol"],
        spec["cost_usd"],
        spec["price"],
        spec["amount_asset"],
        spec["holdings_before"],
        spec["target_balance"],
    )
    assert "<b>Symbol:</b>   BONK/USD<br>" in painted
    assert "<b>Cost:</b>     $12.3456 USD<br>" in painted
    assert "<b>Price:</b>    $0.00001234<br>" in painted
    assert "<b>Amount:</b>   1000000.500000 BONK<br>" in painted
    assert "<b>Current holdings:</b> 250.125000 (~$0.0031)<br>" in painted
    assert "<b>Target balance:</b>   $500.00<br>" in painted
    assert painted.endswith("<b>After this buy:</b>   $12.3487")
    assert painted.count("<br>") == 6


def test_the_detail_arithmetic_matches_the_dialogs_own(monkeypatch):
    """The holdings value or the after-buy total drifted from the dialog."""
    for name in ("plain", "negative", "zero_price", "very_large"):
        spec = PARAMS[name]
        old = run_old([(BUILD, name)], monkeypatch)
        holdings = surface.holdings_usd(spec["holdings_before"], spec["price"])
        after = surface.after_buy_usd(
            spec["holdings_before"], spec["price"], spec["cost_usd"]
        )
        assert holdings == spec["holdings_before"] * spec["price"], name
        assert after == holdings + spec["cost_usd"], name
        assert f"(~${holdings:.4f})" in old[1]["details_text"], name
        assert old[1]["details_text"].endswith(f"${after:.4f}"), name
    assert surface.holdings_usd(2.0, 3.0) == 6.0
    assert surface.after_buy_usd(2.0, 3.0, 1.0) == 7.0
    assert surface.after_buy_usd(2.0, 3.0, 1.0) != surface.holdings_usd(2.0, 3.0)


def test_the_base_currency_is_read_the_way_the_dialog_reads_it():
    """The asset name shown beside the amount drifted from the dialog."""
    for symbol in ("BONK/USD", "BONK", "", "A/B/C", "Δ→⚡/USD", "/USD"):
        assert surface.base_currency(symbol) == symbol.split("/")[0], symbol
    assert surface.base_currency("BONK/USD") == "BONK"
    assert surface.base_currency("BONK/USD") != "USD"
    assert surface.SYMBOL_SEPARATOR == "/"


def test_the_format_strings_agree_with_the_dialogs_f_string():
    """The surface's format constants drifted from the dialog's f-string."""
    for symbol, cost, price, amount, holdings, target in (
        ("BONK/USD", 1.0, 2.0, 3.0, 4.0, 5.0),
        ("", 0.0, 0.0, 0.0, 0.0, 0.0),
        ("Δ/USD", -1.5, -2.5, -3.5, -4.5, -5.5),
        ("X/USD", 1e18, 1e-9, 1e15, 1e20, 1e21),
    ):
        assert surface.DETAIL_SYMBOL.format(symbol=symbol) == (
            f"<b>Symbol:</b>   {symbol}<br>"
        )
        assert surface.DETAIL_COST.format(cost_usd=cost) == (
            f"<b>Cost:</b>     ${cost:.4f} USD<br>"
        )
        assert surface.DETAIL_PRICE.format(price=price) == (
            f"<b>Price:</b>    ${price:.8f}<br>"
        )
        assert surface.DETAIL_AMOUNT.format(
            amount_asset=amount, base=symbol.split("/")[0]
        ) == (f"<b>Amount:</b>   {amount:.6f} {symbol.split('/')[0]}<br>")
        assert surface.DETAIL_HOLDINGS.format(
            holdings_before=holdings, holdings_usd=holdings * price
        ) == (f"<b>Current holdings:</b> {holdings:.6f} (~${holdings * price:.4f})<br>")
        assert surface.DETAIL_TARGET.format(target_balance=target) == (
            f"<b>Target balance:</b>   ${target:.2f}<br>"
        )
        assert surface.DETAIL_AFTER.format(after_usd=holdings * price + cost) == (
            f"<b>After this buy:</b>   ${holdings * price + cost:.4f}"
        )
    assert surface.DETAIL_COST != surface.DETAIL_TARGET
    assert surface.DETAIL_PRICE.count(".8f") == 1
    assert surface.DETAIL_TARGET.count(".2f") == 1
    assert surface.DETAIL_AMOUNT.count(".6f") == 1
    assert surface.DETAIL_COST.count(".4f") == 1


def test_widget_properties_match_the_dialog():
    """A dialog property drifted from the value the surface reports."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDialog

    app()
    dialog = qt_dialog.BuyConfirmationDialog(**PARAMS["plain"])
    dialog.setWindowFlag(Qt.WindowStaysOnTopHint, surface.STAYS_ON_TOP)
    assert surface.WIDGET == {
        "accessible_name": dialog.accessibleName(),
        "window_title": dialog.windowTitle(),
        "modal": dialog.isModal(),
        "minimum_width_px": dialog.minimumWidth(),
        "size_px": [dialog.width(), dialog.height()],
        "style_sheet": dialog.styleSheet(),
        "stays_on_top": bool(dialog.windowFlags() & Qt.WindowStaysOnTopHint),
    }
    assert surface.ACCESSIBLE_NAME == "Buy Confirmation Dialog"
    assert surface.WINDOW_TITLE == "Confirm Buy Order"
    assert surface.MODAL is True
    assert surface.MINIMUM_WIDTH_PX == 420
    assert surface.STYLE_SHEET == ""
    from qt_pixel import render_widget

    assert_pictures_match(
        old_side=render_widget(dialog, PIXEL_SIZE),
        new_side=render_widget(
            dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
        ),
    )
    bare = QDialog()
    assert bare.accessibleName() != surface.ACCESSIBLE_NAME
    assert bare.windowTitle() != surface.WINDOW_TITLE
    assert bare.isModal() != surface.MODAL
    assert bare.minimumWidth() != surface.MINIMUM_WIDTH_PX
    assert (
        bool(bare.windowFlags() & Qt.WindowStaysOnTopHint) is not surface.STAYS_ON_TOP
    )
    assert list(surface.DEFAULT_SIZE_PX) == [bare.width(), bare.height()]


def test_layout_matches_the_dialog():
    """A margin, a spacing, an order or a stretch drifted from the dialog."""
    from PySide6.QtWidgets import QHBoxLayout, QWidget

    app()
    dialog = qt_dialog.BuyConfirmationDialog(**PARAMS["plain"])
    layout = dialog.layout()
    margins = layout.contentsMargins()
    assert surface.LAYOUT["margins_px"] == [
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ]
    assert surface.LAYOUT["spacing_px"] == layout.spacing()
    assert surface.LAYOUT["child_stretch"] == [
        layout.stretch(index) for index in range(layout.count())
    ]
    assert len(surface.LAYOUT["order"]) == layout.count() == 4
    row = layout.itemAt(3).layout()
    row_margins = row.contentsMargins()
    assert surface.BUTTON_ROW_LAYOUT["margins_px"] == [
        row_margins.left(),
        row_margins.top(),
        row_margins.right(),
        row_margins.bottom(),
    ]
    assert surface.BUTTON_ROW_LAYOUT["spacing_px"] == row.spacing()
    assert surface.BUTTON_ROW_LAYOUT["child_stretch"] == [
        row.stretch(index) for index in range(row.count())
    ]
    assert len(surface.BUTTON_ROW_LAYOUT["order"]) == row.count() == 3
    holder = QWidget()
    bare_row = QHBoxLayout(holder)
    bare_margins = bare_row.contentsMargins()
    assert [
        bare_margins.left(),
        bare_margins.top(),
        bare_margins.right(),
        bare_margins.bottom(),
    ] != surface.BUTTON_ROW_LAYOUT["margins_px"]


def test_the_children_match_the_dialog(monkeypatch):
    """A label's font, wrap, skin or text format drifted from the dialog."""
    from PySide6.QtWidgets import QFrame, QLabel

    app()
    CALLS.clear()
    labels, _buttons = trace_widgets(monkeypatch)
    dialog = qt_dialog.BuyConfirmationDialog(**PARAMS["plain"])
    reason, details = labels
    separator = dialog.layout().itemAt(1).widget()
    assert surface.REASON_LABEL == {
        "point_size": reason.font().pointSize(),
        "bold": reason.font().bold(),
        "word_wrap": reason.wordWrap(),
        "style_sheet": reason.styleSheet(),
    }
    assert surface.DETAILS_LABEL == {
        "text_format": details.textFormat().name,
        "text_format_value": details.textFormat().value,
        "word_wrap": details.wordWrap(),
        "style_sheet": details.styleSheet(),
    }
    assert surface.SEPARATOR_FRAME == {
        "frame_shape": separator.frameShape().name,
        "frame_shape_value": separator.frameShape().value,
    }
    from qt_pixel import render_widget

    assert_pictures_match(
        old_side=render_widget(dialog, PIXEL_SIZE),
        new_side=render_widget(
            dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
        ),
    )
    bare_label = QLabel("")
    assert bare_label.wordWrap() != surface.REASON_LABEL["word_wrap"]
    assert bare_label.styleSheet() != surface.REASON_LABEL["style_sheet"]
    assert bare_label.textFormat().name != surface.DETAILS_TEXT_FORMAT
    assert QFrame().frameShape().name != surface.SEPARATOR_FRAME_SHAPE
    assert surface.REASON_POINT_SIZE != bare_label.font().pointSize()
    assert surface.REASON_BOLD is not bare_label.font().bold()
    assert surface.DETAILS_WORD_WRAP is not surface.REASON_WORD_WRAP


def test_the_buttons_match_the_dialog(monkeypatch):
    """A button's label, state or skin drifted from the dialog's own."""
    app()
    CALLS.clear()
    _labels, buttons = trace_widgets(monkeypatch)
    dialog = qt_dialog.BuyConfirmationDialog(**PARAMS["plain"])
    names = (surface.YES, surface.NO, surface.SKIP)
    assert surface.BUTTONS == {
        name: {
            "text": button.text(),
            "enabled": button.isEnabled(),
            "style_sheet": button.styleSheet(),
        }
        for name, button in zip(names, buttons)
    }
    assert surface.YES_TEXT == "Yes — place the buy"
    assert surface.NO_TEXT == "No — refuse this buy"
    assert surface.SKIP_TEXT == "Skip this cycle"
    assert surface.YES_ENABLED is True
    assert surface.NO_ENABLED is True
    assert surface.SKIP_ENABLED is True
    assert len({surface.YES_TEXT, surface.NO_TEXT, surface.SKIP_TEXT}) == 3
    assert len({surface.YES_STYLE, surface.NO_STYLE, surface.SKIP_STYLE}) == 3
    from qt_pixel import render_widget

    assert_pictures_match(
        old_side=render_widget(dialog, PIXEL_SIZE),
        new_side=render_widget(
            dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
        ),
    )


COLOUR_TOKENS = (
    ("reason_color", surface.REASON_COLOR, "#ffaa00"),
    ("yes_surface", surface.YES_SURFACE, "#225522"),
    ("no_surface", surface.NO_SURFACE, "#552222"),
    ("button_text_color", surface.BUTTON_TEXT_COLOR, "white"),
)


def test_rgb_matches_qcolor_on_every_token():
    """The Qt-free colour split disagrees with QColor on a token."""
    from PySide6.QtGui import QColor

    assert surface.rgb("#123456") == (18, 52, 86)
    assert surface.rgb("#abc") == (170, 187, 204)
    assert surface.rgb("#ff8000") != surface.rgb("#0080ff")
    for _name, token, expected in COLOUR_TOKENS:
        assert token == expected, token
        painted = QColor(token)
        assert surface.rgb(token) == (painted.red(), painted.green(), painted.blue())
    assert surface.rgb(surface.YES_SURFACE) != surface.rgb(surface.NO_SURFACE)


def test_a_channel_swap_is_reported_on_every_colour_that_can_show_one():
    """A colour check a swapped red and blue would pass proves nothing.

    ``white`` has three equal channels and ``#225522`` has equal red and
    blue, so no red/blue swap can change either. Both are named here
    rather than left to look like coverage, and every token is still
    separated from every other by an exact comparison.
    """
    swap_blind = (surface.BUTTON_TEXT_COLOR, surface.YES_SURFACE)
    swappable = 0
    for _name, token, _expected in COLOUR_TOKENS:
        red, green, blue = surface.rgb(token)
        if token in swap_blind:
            assert (red, green, blue) == (blue, green, red), token
            continue
        assert (red, green, blue) != (blue, green, red), token
        swappable += 1
    assert swappable == 2
    assert len(swap_blind) == 2
    values = [surface.rgb(token) for _n, token, _e in COLOUR_TOKENS]
    assert len(set(values)) == len(COLOUR_TOKENS)


def test_the_skins_are_the_dialogs_own(monkeypatch):
    """The surface ships a skin the dialog does not paint."""
    app()
    CALLS.clear()
    labels, buttons = trace_widgets(monkeypatch)
    dialog = qt_dialog.BuyConfirmationDialog(**PARAMS["plain"])
    assert surface.REASON_STYLE == labels[0].styleSheet()
    assert surface.DETAILS_STYLE == labels[1].styleSheet()
    assert surface.YES_STYLE == buttons[0].styleSheet()
    assert surface.NO_STYLE == buttons[1].styleSheet()
    assert surface.SKIP_STYLE == buttons[2].styleSheet()
    assert surface.REASON_COLOR in surface.REASON_STYLE
    assert surface.YES_SURFACE in surface.YES_STYLE
    assert surface.NO_SURFACE in surface.NO_STYLE
    assert surface.YES_SURFACE not in surface.NO_STYLE
    assert surface.NO_SURFACE not in surface.YES_STYLE
    assert "padding: 8px 16px" in surface.SKIP_STYLE
    assert "background-color" not in surface.SKIP_STYLE
    assert surface.REASON_STYLE == "color: #ffaa00; padding: 8px;"
    assert surface.DETAILS_STYLE == "padding: 8px;"
    from qt_pixel import render_widget

    assert_pictures_match(
        old_side=render_widget(dialog, PIXEL_SIZE),
        new_side=render_widget(
            dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
        ),
    )
    for token in (surface.YES_SURFACE, surface.NO_SURFACE, surface.REASON_COLOR):
        assert token in dialog.styleSheet() + "".join(
            widget.styleSheet() for widget in labels + buttons
        ), token


def test_the_shipped_strings_are_the_dialogs_own():
    """A string the operator reads was retyped rather than carried over."""
    dialog_text = DIALOG_PATH.read_text(encoding="utf-8")
    for literal in (
        surface.ACCESSIBLE_NAME,
        surface.WINDOW_TITLE,
        surface.YES_TEXT,
        surface.NO_TEXT,
        surface.SKIP_TEXT,
        surface.TIMEOUT_LOG,
        surface.REASON_STYLE,
        surface.DETAILS_STYLE,
        surface.ANSWER_YES,
        surface.ANSWER_SKIP,
        surface.ANSWER_TIMEOUT,
    ):
        assert literal in dialog_text, literal
    assert surface.YES_SURFACE in dialog_text
    assert surface.NO_SURFACE in dialog_text
    for half in surface.HEADLESS_LOG.split("; "):
        assert half in dialog_text, half
    for half in surface.NO_QT_ERROR.split("dialog "):
        assert half in dialog_text, half


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    import ast

    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    assert imported == {"logging", "typing", "__future__", ""}
    dialog_tree = ast.parse(DIALOG_PATH.read_text(encoding="utf-8"))
    dialog_imports = {
        (node.module or "")
        for node in ast.walk(dialog_tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in dialog_imports), dialog_imports


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other."""
    dialog_text = DIALOG_PATH.read_text(encoding="utf-8")
    surface_text = SURFACE_PATH.read_text(encoding="utf-8")
    assert dialog_text.count(".connect(") == 4
    assert (
        "self._request_signal.connect(self._on_request_received, Qt.AutoConnection)"
        in dialog_text
    )
    assert 'btn_yes.clicked.connect(lambda: self._answer("yes"))' in dialog_text
    assert 'btn_no.clicked.connect(lambda: self._answer("no"))' in dialog_text
    assert 'btn_skip.clicked.connect(lambda: self._answer("skip"))' in dialog_text
    assert surface_text.count(".connect(") == 0
    assert len(surface.ACTIONS) == dialog_text.count(".connect(")
    assert set(surface.ACTIONS) == {
        "request.received",
        "yes.clicked",
        "no.clicked",
        "skip.clicked",
    }
    assert surface.ACTIONS["request.received"] == "show_request"
    assert surface.ACTIONS["yes.clicked"] == "answer_yes"
    assert surface.ACTIONS["no.clicked"] == "answer_no"
    assert surface.ACTIONS["skip.clicked"] == "answer_skip"
    for target in surface.ACTIONS.values():
        assert callable(getattr(surface.BuyConfirmationModel, target)), target


METHOD_MAP = {
    "get_broker": "broker_state",
    "_BuyConfirmationBroker.__init__": "BuyConfirmationModel.__init__",
    "_BuyConfirmationBroker.request_confirmation": "BuyConfirmationModel.request",
    "_BuyConfirmationBroker._on_request_received": "BuyConfirmationModel.show_request",
    "BuyConfirmationDialog.__init__": "BuyConfirmationModel.build",
    "BuyConfirmationDialog._answer": "BuyConfirmationModel.answer",
}

MODEL_METHODS = {
    "build",
    "answer",
    "answer_yes",
    "answer_no",
    "answer_skip",
    "request",
    "timed_out",
    "show_request",
}


def resolve(dotted):
    """The callable a dotted name in the map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def qt_method_names():
    """Every method the Qt module defines, as dotted names.

    ``_request_signal`` is a Qt Signal, which reads as a routine but is
    not a function, so it is filtered by ``isfunction`` rather than by
    name.
    """
    import inspect

    names = {"get_broker"}
    for owner in ("_BuyConfirmationBroker", "BuyConfirmationDialog"):
        holder = getattr(qt_dialog, owner)
        for name, value in vars(holder).items():
            if inspect.isfunction(value) and not name.startswith("__"):
                names.add(owner + "." + name)
        names.add(owner + ".__init__")
    return names


def test_every_dialog_method_has_a_counterpart():
    """A method exists on one side and nowhere on the other."""
    assert qt_method_names() == set(METHOD_MAP)
    assert len(METHOD_MAP) == 6
    for target in METHOD_MAP.values():
        assert callable(resolve(target)), target
    surface_methods = {
        name
        for name, value in vars(surface.BuyConfirmationModel).items()
        if callable(value) and not name.startswith("__")
    }
    assert surface_methods == MODEL_METHODS
    assert len(surface_methods) == 8


def test_a_method_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    assert "BuyConfirmationDialog._answer" in qt_method_names()
    assert "_BuyConfirmationBroker.request_confirmation" in qt_method_names()
    assert "BuyConfirmationDialog.setWindowFlag" not in qt_method_names()
    assert "_BuyConfirmationBroker._request_signal" not in qt_method_names()
    import inspect

    signal = vars(qt_dialog._BuyConfirmationBroker)["_request_signal"]
    assert inspect.isroutine(signal)
    assert not inspect.isfunction(signal)
    with pytest.raises(AttributeError):
        resolve("BuyConfirmationModel.no_such_method")
    assert MODEL_METHODS - {"build"} != MODEL_METHODS
    assert set(METHOD_MAP.values()) <= {
        "broker_state",
        "BuyConfirmationModel.__init__",
        "BuyConfirmationModel.request",
        "BuyConfirmationModel.show_request",
        "BuyConfirmationModel.build",
        "BuyConfirmationModel.answer",
    }


CALL_NAMES = {
    "DIALOG_SET_ACCESSIBLE_NAME": "dialog.setAccessibleName",
    "DIALOG_RESULT_VALUE": "dialog.result_value",
    "DIALOG_SET_WINDOW_TITLE": "dialog.setWindowTitle",
    "DIALOG_SET_MODAL": "dialog.setModal",
    "DIALOG_SET_MINIMUM_WIDTH": "dialog.setMinimumWidth",
    "LAYOUT_CREATE": "layout.create",
    "LAYOUT_ADD_WIDGET": "layout.addWidget",
    "LAYOUT_ADD_LAYOUT": "layout.addLayout",
    "ROW_CREATE": "row.create",
    "ROW_ADD_WIDGET": "row.addWidget",
    "REASON_CREATE": "reason.create",
    "REASON_SET_FONT": "reason.setFont",
    "REASON_SET_STYLE_SHEET": "reason.setStyleSheet",
    "REASON_SET_WORD_WRAP": "reason.setWordWrap",
    "SEPARATOR_CREATE": "separator.create",
    "SEPARATOR_SET_FRAME_SHAPE": "separator.setFrameShape",
    "DETAILS_CREATE": "details.create",
    "DETAILS_SET_TEXT_FORMAT": "details.setTextFormat",
    "DETAILS_SET_STYLE_SHEET": "details.setStyleSheet",
    "YES_CREATE": "yes.create",
    "NO_CREATE": "no.create",
    "SKIP_CREATE": "skip.create",
    "YES_SET_STYLE_SHEET": "yes.setStyleSheet",
    "NO_SET_STYLE_SHEET": "no.setStyleSheet",
    "SKIP_SET_STYLE_SHEET": "skip.setStyleSheet",
    "DIALOG_ACCEPT": "dialog.accept",
    "DIALOG_SET_WINDOW_FLAG": "dialog.setWindowFlag",
    "DIALOG_RAISE": "dialog.raise_",
    "DIALOG_ACTIVATE": "dialog.activateWindow",
    "DIALOG_EXEC": "dialog.exec",
    "DIALOG_EXEC_RESULT": "dialog.exec.result",
    "FUTURE_CREATE": "loop.create_future",
    "PENDING_SET": "pending.set",
    "SIGNAL_EMIT": "signal.emit",
    "WAIT_FOR": "wait_for",
    "PENDING_POP": "pending.pop",
    "FUTURE_DONE": "future.done",
    "FUTURE_SET_RESULT": "future.set_result",
}


def test_the_call_names_are_the_ones_the_trace_writes():
    """The trace and the surface stopped agreeing on what to call a call.

    The Qt side of the trace builds each label from these literals, so a
    label read out of the surface cannot make both sides agree by
    definition.
    """
    for constant, literal in CALL_NAMES.items():
        assert getattr(surface, constant) == literal, constant
    assert len(set(CALL_NAMES.values())) == 38


def broker_host(answer=None, future=None):
    """A duck-typed broker carrying only what the two methods touch."""
    return type(
        "Host",
        (),
        {"_pending": _Pending(), "_request_signal": _SignalRecorder(answer)},
    )()


def run_show_request_old(payload_spec, exec_result, press, future_done, monkeypatch):
    """Drive ``_on_request_received`` on a duck-typed broker."""
    app()
    CALLS.clear()
    trace_widgets(monkeypatch)
    patch = trace_dialog_methods(exec_result, press)
    try:
        host = broker_host()
        future = _Future(future_done)
        payload = dict(PARAMS[payload_spec])
        payload.update(
            {
                "request_id": "bot-a_1234",
                "bot_id": "bot-a",
                "loop": _Loop(),
                "future": future,
            }
        )
        host._pending[payload["request_id"]] = payload
        CALLS.clear()
        qt_dialog._BuyConfirmationBroker._on_request_received(
            host, payload["request_id"], payload
        )
        return (
            [list(call) for call in CALLS],
            future.resolved,
            sorted(host._pending),
        )
    finally:
        patch.undo()


def run_show_request_new(payload_spec, exec_result, press, future_done):
    """Drive ``show_request`` on the view model with the same payload."""
    model = surface.BuyConfirmationModel()
    payload = dict(PARAMS[payload_spec])
    payload.update({"request_id": "bot-a_1234", "bot_id": "bot-a"})
    model.pending[payload["request_id"]] = payload
    answer = model.show_request(payload, exec_result, press, future_done)
    resolved = [] if future_done else [answer]
    return [list(call) for call in model.calls], resolved, sorted(model.pending)


SHOW_CASES = {
    "yes": ("plain", surface.ACCEPTED, surface.YES, False),
    "no": ("plain", surface.ACCEPTED, surface.NO, False),
    "skip": ("plain", surface.ACCEPTED, surface.SKIP, False),
    "closed_by_window": ("plain", surface.REJECTED, None, False),
    "closed_after_press": ("plain", surface.REJECTED, surface.YES, False),
    "no_press_accepted": ("plain", surface.ACCEPTED, None, False),
    "future_already_done": ("plain", surface.ACCEPTED, surface.YES, True),
    "unicode_payload": ("unicode", surface.ACCEPTED, surface.SKIP, False),
    "empty_payload": ("empty", surface.ACCEPTED, surface.NO, False),
    "very_large_payload": ("very_large", surface.ACCEPTED, surface.YES, False),
}


@pytest.mark.parametrize("name", sorted(SHOW_CASES))
def test_the_broker_raises_the_modal_the_same_way(name, monkeypatch):
    """The broker made a different call, or resolved a different answer."""
    spec, exec_result, press, future_done = SHOW_CASES[name]
    old_calls, old_resolved, old_pending = run_show_request_old(
        spec, exec_result, press, future_done, monkeypatch
    )
    new_calls, new_resolved, new_pending = run_show_request_new(
        spec, exec_result, press, future_done
    )
    assert new_calls == old_calls
    assert new_resolved == old_resolved
    assert new_pending == old_pending == []
    assert digest(new_calls) == digest(old_calls)


def test_a_closed_window_counts_as_no(monkeypatch):
    """A dialog dismissed by its window button placed a buy."""
    _calls, resolved, _pending = run_show_request_old(
        "plain", surface.REJECTED, surface.YES, False, monkeypatch
    )
    assert resolved == [surface.ANSWER_NO]
    assert surface.CLOSED_ANSWER == surface.ANSWER_NO
    _new_calls, new_resolved, _new_pending = run_show_request_new(
        "plain", surface.REJECTED, surface.YES, False
    )
    assert new_resolved == resolved
    accepted_calls, accepted_resolved, _accepted_pending = run_show_request_old(
        "plain", surface.ACCEPTED, surface.YES, False, monkeypatch
    )
    assert accepted_resolved == [surface.ANSWER_YES]
    assert accepted_calls != _calls


def test_a_future_already_resolved_is_left_alone(monkeypatch):
    """A second resolve reached a future that had already answered."""
    calls, resolved, _pending = run_show_request_old(
        "plain", surface.ACCEPTED, surface.YES, True, monkeypatch
    )
    assert resolved == []
    assert [surface.FUTURE_DONE, True] in calls
    assert not any(call[0] == surface.FUTURE_SET_RESULT for call in calls)
    live_calls, live_resolved, _live_pending = run_show_request_old(
        "plain", surface.ACCEPTED, surface.YES, False, monkeypatch
    )
    assert live_resolved == [surface.ANSWER_YES]
    assert [surface.FUTURE_SET_RESULT, surface.ANSWER_YES] in live_calls


def test_the_broker_drops_the_pending_request(monkeypatch):
    """A finished request stayed in the pending map for the process life."""
    calls, _resolved, pending = run_show_request_old(
        "plain", surface.ACCEPTED, surface.YES, False, monkeypatch
    )
    assert calls[-1] == [surface.PENDING_POP, "bot-a_1234"]
    assert pending == []
    new_calls, _new_resolved, new_pending = run_show_request_new(
        "plain", surface.ACCEPTED, surface.YES, False
    )
    assert new_calls[-1] == calls[-1]
    assert new_pending == pending


def run_request_old(bot_id, answer, timeout_sec, monkeypatch):
    """Drive ``request_confirmation`` on a duck-typed broker."""
    monkeypatch.setattr(qt_dialog, "asyncio", _AsyncioProxy())
    host = broker_host(answer)
    CALLS.clear()

    async def drive():
        return await qt_dialog._BuyConfirmationBroker.request_confirmation(
            host,
            bot_id=bot_id,
            symbol="BONK/USD",
            reason="Over target",
            cost_usd=1.0,
            price=2.0,
            amount_asset=3.0,
            holdings_before=4.0,
            target_balance=5.0,
            timeout_sec=timeout_sec,
        )

    result = asyncio.run(drive())
    emitted = host._request_signal.emitted
    return result, [list(call) for call in CALLS], emitted, sorted(host._pending)


def run_request_new(bot_id, answer, timeout_sec, millis):
    """Drive the view model's request path with the same clock reading."""
    model = surface.BuyConfirmationModel()
    payload = model.request(
        bot_id=bot_id,
        symbol="BONK/USD",
        reason="Over target",
        cost_usd=1.0,
        price=2.0,
        amount_asset=3.0,
        holdings_before=4.0,
        target_balance=5.0,
        loop_time=millis / surface.REQUEST_ID_MILLIS_SCALE,
        timeout_sec=timeout_sec,
    )
    if answer is None:
        result = model.timed_out(bot_id, payload["request_id"], timeout_sec)
    else:
        result = answer
    return (
        result,
        [list(call) for call in model.calls],
        payload,
        sorted(model.pending),
    )


REQUEST_CASES = {
    "answered_yes": ("bot-a", surface.ANSWER_YES, 5.0),
    "answered_no": ("bot-a", surface.ANSWER_NO, 5.0),
    "answered_skip": ("bot-a", surface.ANSWER_SKIP, 5.0),
    "underscore_bot_id": ("bot_a_1", surface.ANSWER_YES, 5.0),
    "empty_bot_id": ("", surface.ANSWER_YES, 5.0),
    "unicode_bot_id": ("Δ→⚡", surface.ANSWER_YES, 5.0),
    "long_bot_id": ("b" * 200, surface.ANSWER_YES, 5.0),
    "timed_out": ("bot-a", None, 0),
    "timed_out_default_wait": ("bot-a", None, 0.0),
}


@pytest.mark.parametrize("name", sorted(REQUEST_CASES))
def test_the_request_path_matches_the_broker(name, monkeypatch, capture_log):
    """The broker filed, emitted or waited differently from the surface.

    The pending map is compared as well as the call list: a surface that
    logs a pop it never made would otherwise read as identical.
    """
    bot_id, answer, timeout_sec = REQUEST_CASES[name]
    with capture_log(LOGGER_NAME) as old_records:
        old_result, old_calls, emitted, old_pending = run_request_old(
            bot_id, answer, timeout_sec, monkeypatch
        )
    old_logs = [record.getMessage() for record in old_records]
    key = emitted[0][0]
    millis = int(key.rsplit("_", 1)[1])
    with capture_log(LOGGER_NAME) as new_records:
        new_result, new_calls, payload, new_pending = run_request_new(
            bot_id, answer, timeout_sec, millis
        )
    new_logs = [record.getMessage() for record in new_records]
    assert payload["request_id"] == key
    assert new_result == old_result
    assert new_calls == old_calls
    assert new_logs == old_logs
    assert new_pending == old_pending
    assert old_pending == ([] if answer is None else [key])
    assert digest(new_calls) == digest(old_calls)


def test_the_request_id_format_is_the_brokers_own(monkeypatch):
    """The key a pending request is filed under drifted from the broker."""
    _result, _calls, emitted, pending = run_request_old(
        "bot-a", surface.ANSWER_YES, 5.0, monkeypatch
    )
    key = emitted[0][0]
    millis = int(key.rsplit("_", 1)[1])
    assert pending == [key]
    assert surface.request_id("bot-a", millis) == key
    assert surface.request_id("bot-a", millis) != f"bot-a-{millis}"
    assert surface.request_id("bot-a", millis) != f"{millis}_bot-a"
    assert surface.REQUEST_ID_FORMAT == "{bot_id}_{millis}"
    assert surface.millis_of(1.5) == 1500
    assert surface.millis_of(0.0) == 0
    assert surface.REQUEST_ID_MILLIS_SCALE == 1000


def test_the_payload_carries_every_field_the_dialog_reads(monkeypatch):
    """A field the dialog reads was missing from the payload."""
    _result, _calls, emitted, _pending = run_request_old(
        "bot-a", surface.ANSWER_YES, 5.0, monkeypatch
    )
    payload = emitted[0][1]
    assert set(payload) == set(surface.PAYLOAD_FIELDS)
    assert len(surface.PAYLOAD_FIELDS) == 11
    for field in surface.DIALOG_FIELDS:
        assert field in payload, field
    assert len(surface.DIALOG_FIELDS) == 7
    assert set(surface.DIALOG_FIELDS) < set(surface.PAYLOAD_FIELDS)
    assert set(surface.REQUEST_FIELDS) - {"timeout_sec"} < set(surface.PAYLOAD_FIELDS)
    assert len(surface.REQUEST_FIELDS) == 9


def test_the_timeout_is_sixty_seconds_on_both_sides():
    """The wait before a buy is refused drifted from the broker's own."""
    import inspect

    signature = inspect.signature(qt_dialog._BuyConfirmationBroker.request_confirmation)
    assert signature.parameters["timeout_sec"].default == surface.TIMEOUT_SEC
    assert surface.TIMEOUT_SEC == 60.0
    assert surface.TIMEOUT_MS == int(surface.TIMEOUT_SEC * 1000)
    assert surface.TIMEOUT_MS == 60000
    assert set(signature.parameters) - {"self"} == set(surface.REQUEST_FIELDS)


def test_a_timeout_logs_and_refuses(monkeypatch, capture_log):
    """A silent timeout placed a buy nobody approved."""
    with capture_log(LOGGER_NAME) as old_records:
        old_result, old_calls, emitted, old_pending = run_request_old(
            "bot-a", None, 0, monkeypatch
        )
    old_logs = [record.getMessage() for record in old_records]
    assert old_result == surface.ANSWER_TIMEOUT
    assert old_logs == ["Buy confirmation timed out after 0s for bot bot-a"]
    assert old_calls[-1] == [surface.PENDING_POP, emitted[0][0]]
    assert old_pending == []
    key = emitted[0][0]
    millis = int(key.rsplit("_", 1)[1])
    _new_result, _new_calls, _payload, new_pending = run_request_new(
        "bot-a", None, 0, millis
    )
    assert new_pending == old_pending
    with capture_log(LOGGER_NAME) as answered_records:
        answered, _calls, _emitted, answered_pending = run_request_old(
            "bot-a", surface.ANSWER_YES, 5.0, monkeypatch
        )
    assert answered == surface.ANSWER_YES
    assert [record.getMessage() for record in answered_records] == []
    assert len(answered_pending) == 1


def test_get_broker_matches_the_surface(monkeypatch):
    """The broker was built twice, or a headless process got one anyway."""
    app()
    monkeypatch.setattr(qt_dialog, "_broker", None)
    first = qt_dialog.get_broker()
    second = qt_dialog.get_broker()
    assert first is second
    model = surface.BuyConfirmationModel()
    assert surface.broker_state(True, model) is model
    assert isinstance(surface.broker_state(True), surface.BuyConfirmationModel)
    monkeypatch.setattr(qt_dialog, "_broker", None)
    monkeypatch.setattr(qt_dialog, "_QT_AVAILABLE", False)
    with pytest.raises(RuntimeError) as qt_error:
        qt_dialog.get_broker()
    with pytest.raises(RuntimeError) as surface_error:
        surface.broker_state(False)
    assert str(surface_error.value) == str(qt_error.value)
    assert str(qt_error.value) == surface.NO_QT_ERROR
    assert issubclass(surface.BrokerUnavailable, RuntimeError)


def dialog_painted_by_the_dialog(spec):
    """The shipped dialog, built from one parameter set."""
    app()
    return qt_dialog.BuyConfirmationDialog(**PARAMS[spec])


def model_payload(spec, button=None):
    """The surface payload for the same parameter set, stamped."""
    model = surface.BuyConfirmationModel()
    return sealed(surface.build_view_model(model, button=button, **PARAMS[spec]))


def dialog_painted_by_the_model(payload):
    """A bare dialog filled only from the payload, never from the dialog.

    A payload the caller changed after it came off the surface is
    refused.
    """
    unaltered(payload)
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import (
        QDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
    )

    properties = payload["widget"]
    dialog = QDialog()
    dialog.setAccessibleName(properties["accessible_name"])
    dialog.setWindowTitle(properties["window_title"])
    dialog.setModal(properties["modal"])
    dialog.setMinimumWidth(properties["minimum_width_px"])
    dialog.resize(properties["size_px"][0], properties["size_px"][1])
    dialog.setStyleSheet(properties["style_sheet"])

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(*payload["layout"]["margins_px"])
    layout.setSpacing(payload["layout"]["spacing_px"])

    reason = QLabel(payload["reason_text"])
    font = QFont()
    font.setBold(payload["reason_label"]["bold"])
    font.setPointSize(payload["reason_label"]["point_size"])
    reason.setFont(font)
    reason.setStyleSheet(payload["reason_label"]["style_sheet"])
    reason.setWordWrap(payload["reason_label"]["word_wrap"])

    separator = QFrame()
    separator.setFrameShape(QFrame.Shape(payload["separator"]["frame_shape_value"]))

    details = QLabel(payload["details_text"])
    details.setTextFormat(Qt.TextFormat(payload["details_label"]["text_format_value"]))
    details.setStyleSheet(payload["details_label"]["style_sheet"])
    details.setWordWrap(payload["details_label"]["word_wrap"])

    row = QHBoxLayout()
    row.setContentsMargins(*payload["button_row"]["margins_px"])
    row.setSpacing(payload["button_row"]["spacing_px"])

    pressable = {}
    for name in payload["button_row"]["order"]:
        spec = payload["buttons"][name]
        button = QPushButton(spec["text"])
        button.setStyleSheet(spec["style_sheet"])
        button.setEnabled(spec["enabled"])
        pressable[name] = button

    placed = {"reason": reason, "separator": separator, "details": details}
    for index, name in enumerate(payload["layout"]["order"]):
        if name == "button_row":
            layout.addLayout(row)
        else:
            layout.addWidget(placed[name], payload["layout"]["child_stretch"][index])
    for index, name in enumerate(payload["button_row"]["order"]):
        row.addWidget(pressable[name], payload["button_row"]["child_stretch"][index])
    return dialog


PIXEL_SPECS = ("plain", "empty", "zero_price", "negative", "unicode", "no_separator")


@pytest.mark.parametrize("spec", PIXEL_SPECS)
def test_the_two_sides_render_the_same_pixels(spec):
    """The page paints a value, a colour or a position the dialog does not."""
    app()
    assert_pictures_match(
        old_side=render_offscreen(dialog_painted_by_the_dialog(spec), PIXEL_SIZE),
        new_side=render_offscreen(
            dialog_painted_by_the_model(model_payload(spec)), PIXEL_SIZE
        ),
        note=spec,
    )


def test_the_pixel_check_reports_a_different_parameter_set():
    """The image comparison passes whatever the second side paints.

    Two real parameter sets, one driven into each side. One carries a
    symbol, a reason and four figures; the other carries none of them,
    so a pass proves the comparison reports a dialog painted
    differently.
    """
    app()
    assert PARAMS["plain"] != PARAMS["empty"]
    assert_pictures_differ(
        old_side=render_offscreen(dialog_painted_by_the_dialog("plain"), PIXEL_SIZE),
        new_side=render_offscreen(
            dialog_painted_by_the_model(model_payload("empty")), PIXEL_SIZE
        ),
        note="plain from the dialog against empty from the surface",
    )


SILENT_IN_THE_RENDER = ("bold", "point_size")


def test_the_text_a_picture_may_not_show_is_compared_as_exact_strings(monkeypatch):
    """A same-length text swap was left to the render to report.

    Whether a swap of equal length moves a pixel depends on the fonts
    the host installs, so the render cannot carry this proof anywhere.
    Both painted strings are read off the dialog's own labels and off
    the surface and compared character for character.
    """
    app()
    CALLS.clear()
    labels, buttons = trace_widgets(monkeypatch)
    qt_dialog.BuyConfirmationDialog(**PARAMS["plain"])
    payload = model_payload("plain")
    assert payload["reason_text"] == labels[0].text()
    assert payload["details_text"] == labels[1].text()
    assert [payload["buttons"][name]["text"] for name in ("yes", "no", "skip")] == [
        button.text() for button in buttons
    ]
    disguised = "Z" * len(payload["reason_text"])
    assert len(disguised) == len(payload["reason_text"])
    assert disguised != payload["reason_text"] != ""
    assert disguised != labels[0].text()


def test_the_font_a_picture_may_not_show_is_compared_as_numbers(monkeypatch):
    """The banner's weight was left to the render to report.

    A weight paints a heavier stem only where the host installs a bold
    face, so no render carries this proof on every machine. The weight
    is read off the dialog's own font and off the surface as a flag. The
    point size changes the size of the box on every host and stays a
    picture check, in ``test_the_pixel_check_reports_one_planted_defect``
    under ``shrink_the_reason_font``.
    """
    app()
    CALLS.clear()
    labels, _buttons = trace_widgets(monkeypatch)
    qt_dialog.BuyConfirmationDialog(**PARAMS["plain"])
    font = labels[0].font()
    for token in SILENT_IN_THE_RENDER:
        assert token in surface.REASON_LABEL
    assert surface.REASON_LABEL["point_size"] == font.pointSize() == 12
    assert surface.REASON_LABEL["bold"] == font.bold() is True
    for size in (8, 20):
        assert surface.REASON_LABEL["point_size"] != size


def test_the_answer_a_picture_cannot_see_is_compared_as_a_string(monkeypatch):
    """The answer the dialog carries never reaches a pixel.

    ``result_value`` is not painted anywhere, so no render can report a
    wrong answer. It is compared as an exact string in every trace, and
    the four values it can hold are pinned here.
    """
    old = run_old([(BUILD, "plain"), (CLICK, surface.SKIP)], monkeypatch)
    assert old[1]["result_value"] == surface.ANSWER_NO
    assert old[2]["result_value"] == surface.ANSWER_SKIP
    assert surface.ANSWERS == ("yes", "no", "skip", "timeout")
    assert len(set(surface.ANSWERS)) == 4
    assert surface.DEFAULT_ANSWER == surface.ANSWER_NO
    assert surface.HEADLESS_ANSWER == surface.ANSWER_NO
    assert surface.ANSWER_TIMEOUT not in surface.BUTTON_ANSWERS.values()
    same = model_payload("plain")
    other = model_payload("plain", button=surface.SKIP)
    assert same["result_value"] != other["result_value"]
    assert same["details_text"] == other["details_text"]
    assert same["reason_text"] == other["reason_text"]
    assert same["buttons"] == other["buttons"]
    assert same["widget"] == other["widget"]
    painted_by_the_answer = [
        key for key in same if key not in ("result_value", "accepted", "calls")
    ]
    assert [same[key] for key in painted_by_the_answer] == [
        other[key] for key in painted_by_the_answer
    ]
    assert old[1]["details_text"] == old[2]["details_text"]
    assert old[1]["reason_text"] == old[2]["reason_text"]


BLIND_TO_THE_PICTURE = {
    "window_size": "test_widget_properties_match_the_dialog",
    "button_row_stretch": "test_layout_matches_the_dialog",
    "answer": "test_the_answer_a_picture_cannot_see_is_compared_as_a_string",
    "reason_bold": "test_the_font_a_picture_may_not_show_is_compared_as_numbers",
    "declared_colour": "test_the_skins_are_the_dialogs_own",
    "line_text": "test_the_text_a_picture_may_not_show_is_compared_as_exact_strings",
}


def test_everything_a_picture_cannot_see_is_named_and_covered(monkeypatch):
    """A value no render can report was left to the render to report.

    Six values are named here with the check that does cover each, and
    every one of them is proved by reading the value off the dialog and
    off the surface. None is proved by a picture: whether a value moves
    a pixel depends on the host's fonts and on how the platform style
    repaints a declared colour, so a picture answers the question
    differently from one machine to the next. The one picture in this
    test compares the dialog's pixels against the surface's pixels.
    """
    app()
    CALLS.clear()
    labels, buttons = trace_widgets(monkeypatch)
    dialog = qt_dialog.BuyConfirmationDialog(**PARAMS["plain"])
    assert len(BLIND_TO_THE_PICTURE) == 6
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by

    assert list(surface.DEFAULT_SIZE_PX) == [dialog.width(), dialog.height()]
    assert surface.WIDGET["size_px"] == [dialog.width(), dialog.height()]

    row = dialog.layout().itemAt(3).layout()
    assert surface.BUTTON_ROW_LAYOUT["child_stretch"] == [
        row.stretch(index) for index in range(row.count())
    ]
    assert surface.BUTTON_ROW_LAYOUT["child_stretch"] == [0, 0, 0]

    assert surface.YES_STYLE == buttons[0].styleSheet()
    assert surface.NO_STYLE == buttons[1].styleSheet()
    assert surface.YES_SURFACE in buttons[0].styleSheet()
    assert surface.NO_SURFACE in buttons[1].styleSheet()

    assert surface.REASON_LABEL["bold"] == labels[0].font().bold()
    assert surface.REASON_LABEL["point_size"] == labels[0].font().pointSize()
    payload = model_payload("plain")
    assert payload["reason_text"] == labels[0].text()
    assert payload["details_text"] == labels[1].text()
    assert payload["result_value"] == dialog.result_value

    from qt_pixel import render_widget

    assert_pictures_match(
        old_side=render_widget(dialog, PIXEL_SIZE),
        new_side=render_widget(
            dialog_painted_by_the_model(model_payload("plain")), PIXEL_SIZE
        ),
    )


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = model_payload("plain", button=surface.YES)
    encoded = json.loads(json.dumps(payload))
    assert encoded["reason_text"] == "Initial entry — bot holds zero"
    assert encoded["result_value"] == "yes"
    assert encoded["accepted"] is True
    assert encoded["calls"][-1] == ["dialog.accept"]
    assert encoded["timeout_sec"] == 60.0
    assert encoded["timeout_ms"] == 60000
    assert encoded["answers"] == ["yes", "no", "skip", "timeout"]
    assert encoded["reason_color"] == [255, 170, 0]
    assert encoded["yes_surface"] == [34, 85, 34]
    assert encoded["no_surface"] == [85, 34, 34]
    assert encoded["button_text_color"] == [255, 255, 255]
    assert encoded["widget"]["accessible_name"] == "Buy Confirmation Dialog"
    assert encoded["buttons"]["skip"]["text"] == "Skip this cycle"
    assert len(encoded["calls"]) == 31


def test_view_model_matches_the_dialog_on_the_same_request(monkeypatch):
    """The bridge payload disagrees with the dialog on the same request."""
    CALLS.clear()
    labels, buttons = trace_widgets(monkeypatch)
    dialog = qt_dialog.BuyConfirmationDialog(**PARAMS["plain"])
    payload = model_payload("plain")
    assert payload["reason_text"] == labels[0].text()
    assert payload["details_text"] == labels[1].text()
    assert payload["result_value"] == dialog.result_value
    assert [payload["buttons"][name]["text"] for name in ("yes", "no", "skip")] == [
        button.text() for button in buttons
    ]


def test_bridge_registers_the_buy_confirmation_method():
    """The renderer cannot reach the buy confirmation through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "buy_confirmation.state"
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 41,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "symbol": "BONK/USD",
                    "reason": "Over target",
                    "cost_usd": 1.0,
                    "price": 2.0,
                    "amount_asset": 3.0,
                    "holdings_before": 4.0,
                    "target_balance": 5.0,
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert answer["result"]["reason_text"] == "Over target"
    assert answer["result"]["result_value"] == "no"
    assert "<b>Symbol:</b>   BONK/USD<br>" in answer["result"]["details_text"]


def test_the_bridge_carries_every_button():
    """A button press over the bridge changed nothing."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 42, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    for name, expected in surface.BUTTON_ANSWERS.items():
        pressed = call({"reset": True, "symbol": "A/B", "button": name})
        assert pressed["result_value"] == expected, name
        assert pressed["accepted"] is True
    untouched = call({"reset": True, "symbol": "A/B"})
    assert untouched["result_value"] == surface.DEFAULT_ANSWER
    assert untouched["accepted"] is False
    assert call({"reset": True})["details_text"].startswith("<b>Symbol:</b>   <br>")


def test_the_bridge_keeps_the_answer_until_a_reset():
    """The dialog forgot its answer between two bridge calls."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 43, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    call({"reset": True, "symbol": "A/B", "button": surface.YES})
    kept = call({"symbol": "A/B"})
    assert len(kept["calls"]) > 31
    assert call({"reset": True, "symbol": "A/B"})["calls"] == kept["calls"][-29:]
    call({"reset": True})


QT_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'buy_confirmation.state', 'params':"
    " {'reset': True, 'symbol': 'BONK/USD', 'reason': 'Over target',"
    " 'cost_usd': 1.0, 'price': 2.0, 'amount_asset': 3.0,"
    " 'holdings_before': 4.0, 'target_balance': 5.0}}),"
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
    """Reaching the buy confirmation pulled Qt into the backend process."""
    answered = run_probe("")
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["reason_text"] == "Over target"
    assert result["widget"]["window_title"] == "Confirm Buy Order"
    assert result["buttons"]["yes"]["text"] == "Yes — place the buy"
    assert "<b>Price:</b>    $2.00000000<br>" in result["details_text"]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_probe("import PySide6.QtCore;")
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


BLOCK_QT = (
    "import sys;"
    "\nclass _Block:\n"
    "    def find_module(self, name, path=None):\n"
    "        return None\n"
    "\nimport importlib.abc, importlib.machinery\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

HEADLESS_PROBE = BLOCK_QT + (
    "import asyncio, json, logging, sys\n"
    "records = []\n"
    "class Sink(logging.Handler):\n"
    "    def emit(self, record):\n"
    "        records.append(record.getMessage())\n"
    "logger = logging.getLogger('acervator.buy_confirmation')\n"
    "logger.addHandler(Sink())\n"
    "logger.setLevel(logging.DEBUG)\n"
    "from src.gui import buy_confirmation_dialog as d\n"
    "from src.gui.main_tabs import buy_confirmation_surface as s\n"
    "old = asyncio.run(d._BuyConfirmationBroker().request_confirmation(bot_id='b'))\n"
    "old_logs = list(records)\n"
    "records.clear()\n"
    "new = s.headless_answer()\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules, 'available': d._QT_AVAILABLE,"
    " 'old': old, 'new': new, 'old_logs': old_logs, 'new_logs': list(records)}))\n"
)


def test_a_process_with_no_qt_refuses_the_buy_the_same_way():
    """The headless stub answered differently from the surface."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=HEADLESS_PROBE.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    answered = json.loads(done.stdout.decode().splitlines()[-1])
    assert answered["qt"] is False
    assert answered["available"] is False
    assert answered["old"] == surface.HEADLESS_ANSWER
    assert answered["new"] == answered["old"]
    assert answered["old_logs"] == [surface.HEADLESS_LOG]
    assert answered["new_logs"] == answered["old_logs"]


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    done = subprocess.run(
        [sys.executable, "-"],
        input=probe.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    assert json.loads(done.stdout.decode().splitlines()[-1])["qt"] is True
