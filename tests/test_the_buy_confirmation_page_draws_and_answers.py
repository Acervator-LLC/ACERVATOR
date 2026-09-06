"""The React buy confirmation page draws the order's figures and answers it.

``react_dialog`` builds the class ``variant_surface`` names for
``BUY_CONFIRMATION``. ``ROW_VALUES_JS`` and ``BUTTONS_JS`` read what the browser
drew, a press in that document runs the inherited ``_answer``, and
``answer_through_the_broker`` drives the real ``_on_request_received``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("PySide6.QtWebEngineWidgets")

from src._variant import ENV_VAR, QT, REACT  # noqa: E402
from src.gui import buy_confirmation_dialog as qt_dialog  # noqa: E402
from src.gui import variant_surface  # noqa: E402
from src.gui.main_tabs import buy_confirmation_surface as surface  # noqa: E402

JS_TIMEOUT_MS = 30_000
SETTLE_SECONDS = 30.0

#: When no press has reached the modal by now, ``close_the_modal`` rejects it.
GIVE_UP_MS = 40_000

REQUEST = {
    "symbol": "BONK/USD",
    "reason": "Initial entry: bot holds zero",
    "cost_usd": 12.3456789,
    "price": 0.0000123456,
    "amount_asset": 1000000.5,
    "holdings_before": 250.125,
    "target_balance": 500.0,
}

ROW_VALUES_JS = (
    "JSON.stringify(Array.from("
    "document.querySelectorAll('[data-part=\"detail-row\"]')).map("
    "function (n) { return ["
    "n.getAttribute('data-key'),"
    "n.querySelector('[data-part=\"detail-label\"]').textContent,"
    "n.querySelector('[data-part=\"detail-value\"]').textContent]; }))"
)

BUTTONS_JS = (
    "JSON.stringify(Array.from("
    "document.querySelectorAll('[data-part=\"confirm-button\"]')).map("
    "function (n) { return [n.getAttribute('data-key'),"
    "n.getAttribute('data-answer'), n.textContent]; }))"
)

BANNER_JS = "document.querySelector('[data-part=\"reason-banner\"]').textContent"

CLICK_JS = (
    "(function (name) {"
    " var one = document.querySelector("
    "'[data-part=\"confirm-button\"][data-key=\"' + name + '\"]');"
    " if (one === null) { return false; }"
    " one.click();"
    " return true; })(%s)"
)


def qapp():
    """The one application object every widget in this file needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def evaluate(view, script: str) -> Any:
    """Evaluate ``script`` in ``view`` and return the value it answers."""
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    box: dict = {}

    def caught(value: Any = None) -> None:
        box.setdefault("value", value)
        loop.quit()

    view.page().runJavaScript(script, caught)
    QTimer.singleShot(JS_TIMEOUT_MS, loop.quit)
    loop.exec()
    assert "value" in box, "the browser never answered: " + script[:60]
    return box["value"]


def until(app, holds: Callable[[], bool], seconds: float = SETTLE_SECONDS) -> bool:
    """Run the event loop until ``holds`` is true or ``seconds`` pass."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if holds():
            return True
        app.processEvents()
    return holds()


def dispose(app, widget) -> None:
    """Close ``widget`` and deliver the deletion its web view waits on."""
    from PySide6.QtCore import QCoreApplication, QEvent

    widget.close()
    app.processEvents()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(widget, QEvent.Type.DeferredDelete)
    app.processEvents()


def rows_drawn(dialog) -> list:
    """The detail rows the browser is showing, as key, label and value."""
    return json.loads(evaluate(dialog._web, ROW_VALUES_JS))


@contextlib.contextmanager
def react_dialog(app, request_fields=None):
    """A ``BUY_CONFIRMATION`` dialog under ``REACT``, with its rows drawn."""
    made = variant_surface.surface_class(variant_surface.BUY_CONFIRMATION, REACT)
    dialog = made(**(request_fields or REQUEST))
    dialog.show()
    try:
        assert until(app, lambda: dialog.page_ready), "the page never loaded"
        assert until(app, lambda: rows_drawn(dialog) != []), "no detail row was drawn"
        yield dialog
    finally:
        dispose(app, dialog)


# ── what the browser draws ────────────────────────────────────────────


def test_the_page_draws_the_alert_line_the_request_carried() -> None:
    """The banner words are the ones the bot sent with the request."""
    app = qapp()
    with react_dialog(app) as dialog:
        assert evaluate(dialog._web, BANNER_JS) == REQUEST["reason"]


def test_the_page_draws_the_seven_figures_the_qt_dialog_shows() -> None:
    """Every drawn value appears in the Qt dialog's own detail label."""
    app = qapp()
    written = surface.detail_row_values(
        REQUEST["symbol"],
        REQUEST["cost_usd"],
        REQUEST["price"],
        REQUEST["amount_asset"],
        REQUEST["holdings_before"],
        REQUEST["target_balance"],
    )
    qt_label = surface.details_text(
        REQUEST["symbol"],
        REQUEST["cost_usd"],
        REQUEST["price"],
        REQUEST["amount_asset"],
        REQUEST["holdings_before"],
        REQUEST["target_balance"],
    )
    with react_dialog(app) as dialog:
        drawn = rows_drawn(dialog)
    assert [row[0] for row in drawn] == list(surface.DETAIL_ROW_ORDER), drawn
    for key, label, value in drawn:
        assert label == surface.DETAIL_ROW_LABELS[key], (key, label)
        assert value == written[key], (key, value, written[key])
        assert value in qt_label, (key, value)


def test_a_request_carrying_another_cost_draws_another_figure() -> None:
    """Positive control: the reading follows the request the dialog was given."""
    app = qapp()
    with react_dialog(app) as dialog:
        first = rows_drawn(dialog)
    other = dict(REQUEST)
    other["cost_usd"] = 999.5
    with react_dialog(app, other) as dialog:
        assert rows_drawn(dialog) != first


def test_the_page_draws_three_buttons_carrying_the_qt_answers() -> None:
    """Each drawn button carries the words and the answer the Qt button has."""
    app = qapp()
    with react_dialog(app) as dialog:
        drawn = json.loads(evaluate(dialog._web, BUTTONS_JS))
    assert [one[0] for one in drawn] == [surface.YES, surface.NO, surface.SKIP]
    for name, answer, words in drawn:
        assert answer == surface.BUTTON_ANSWERS[name], (name, answer)
        assert words == surface.BUTTONS[name]["text"], (name, words)


# ── a press in the document answers the buy ───────────────────────────


@pytest.mark.parametrize("name", [surface.YES, surface.NO, surface.SKIP])
def test_a_press_in_the_document_sets_the_dialogs_own_answer(name: str) -> None:
    """The click reaches ``_answer`` and the dialog accepts with that answer."""
    from PySide6.QtWidgets import QDialog

    app = qapp()
    with react_dialog(app) as dialog:
        assert dialog.result_value == surface.DEFAULT_ANSWER
        assert evaluate(dialog._web, CLICK_JS % json.dumps(name)) is True
        assert until(app, lambda: dialog.result() == int(QDialog.Accepted.value))
        assert dialog.result_value == surface.BUTTON_ANSWERS[name]


def test_a_name_the_surface_does_not_carry_answers_nothing() -> None:
    """Positive control: ``run_action`` refuses a name outside the three."""
    app = qapp()
    with react_dialog(app) as dialog:
        assert dialog.run_action("no-such-button") is False
        assert dialog.result_value == surface.DEFAULT_ANSWER
        assert dialog.run_action(surface.YES) is True
        assert dialog.result_value == surface.ANSWER_YES


# ── the broker raises it and the bot's future carries the answer ───────


def answer_through_the_broker(app, variant: str, name: str) -> tuple:
    """The answer the broker's own future carries after one press."""
    from PySide6.QtCore import QTimer

    seen: dict = {}
    held = {id(w) for w in app.topLevelWidgets()}
    os.environ[ENV_VAR] = variant
    qt_dialog._broker = None
    broker = qt_dialog.get_broker()
    loop = asyncio.new_event_loop()
    future = loop.create_future()
    payload = dict(REQUEST)
    payload.update({"request_id": "probe_1", "bot_id": "probe", "loop": loop})
    payload["future"] = future
    try:
        QTimer.singleShot(0, lambda: press_when_drawn(app, held, seen, name))
        QTimer.singleShot(GIVE_UP_MS, lambda: close_the_modal(app, held, seen))
        broker._on_request_received("probe_1", payload)
        answered = loop.run_until_complete(asyncio.wait_for(future, timeout=5))
    finally:
        loop.close()
        os.environ.pop(ENV_VAR, None)
        qt_dialog._broker = None
    return answered, seen


def press_when_drawn(app, held: set, seen: dict, name: str) -> None:
    """Wait for the modal the broker raised and press ``name`` on it."""
    deadline = time.time() + SETTLE_SECONDS
    while time.time() < deadline:
        app.processEvents()
        dialog = modal_on_screen(app, held)
        if dialog is None:
            continue
        if not isinstance(dialog, qt_dialog.BuyConfirmationDialog):
            continue
        if not hasattr(dialog, "page_ready"):
            seen["kind"] = type(dialog).__name__
            press_qt(dialog, name)
            return
        if not dialog.page_ready or not rows_drawn(dialog):
            continue
        seen["kind"] = type(dialog).__name__
        seen["rows"] = rows_drawn(dialog)
        seen["clicked"] = evaluate(dialog._web, CLICK_JS % json.dumps(name))
        return
    seen["kind"] = "none"


def close_the_modal(app, held: set, seen: dict) -> None:
    """Reject a modal no press reached, so the waiting ``exec`` returns."""
    if seen.get("kind") not in (None, "none"):
        return
    dialog = modal_on_screen(app, held)
    if dialog is not None:
        seen.setdefault("kind", "gave up")
        dialog.reject()


def modal_on_screen(app, held: set):
    """The confirmation dialog this call opened, never one held before it."""
    for widget in app.topLevelWidgets():
        if id(widget) in held or not widget.isVisible():
            continue
        if isinstance(widget, qt_dialog.BuyConfirmationDialog):
            return widget
    return None


def press_qt(dialog, name: str) -> None:
    """Press one of the Qt dialog's own three buttons."""
    row = dialog.layout().itemAt(dialog.layout().count() - 1).layout()
    at = [surface.YES, surface.NO, surface.SKIP].index(name)
    row.itemAt(at).widget().click()


@pytest.mark.parametrize("name", [surface.YES, surface.NO, surface.SKIP])
def test_the_broker_resolves_the_future_with_the_react_press(name: str) -> None:
    """One press in the browser answers the buy the bot task is waiting on."""
    app = qapp()
    answered, seen = answer_through_the_broker(app, REACT, name)
    assert seen.get("kind") == "BuyConfirmationReactDialog", seen
    assert seen.get("clicked") is True, seen
    assert len(seen.get("rows", [])) == len(surface.DETAIL_ROW_ORDER), seen
    assert answered == surface.BUTTON_ANSWERS[name]


@pytest.mark.parametrize("name", [surface.YES, surface.NO, surface.SKIP])
def test_the_qt_build_answers_the_same_value(name: str) -> None:
    """Control: under ``QT`` the broker raises the Qt dialog and answers the same."""
    app = qapp()
    answered, seen = answer_through_the_broker(app, QT, name)
    assert seen.get("kind") == "BuyConfirmationDialog", seen
    assert answered == surface.BUTTON_ANSWERS[name]


# ── the composition, removed ──────────────────────────────────────────


def test_only_this_screen_stops_when_its_seam_entry_is_removed() -> None:
    """Without the entry the broker names no dialog, and the rest still draw."""
    held = variant_surface._LOADERS.pop(variant_surface.BUY_CONFIRMATION)
    try:
        with pytest.raises(KeyError):
            qt_dialog.dialog_class()
        others = [
            name
            for name in variant_surface.screens()
            if name != variant_surface.BUY_CONFIRMATION
        ]
        assert others, "the seam holds no other screen to compare against"
        for name in others:
            assert variant_surface.surface_class(name, REACT) is not None, name
    finally:
        variant_surface._LOADERS[variant_surface.BUY_CONFIRMATION] = held
    assert variant_surface.BUY_CONFIRMATION in variant_surface.screens()
