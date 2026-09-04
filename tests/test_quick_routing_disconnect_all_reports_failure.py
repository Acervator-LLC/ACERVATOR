"""Disconnect All must say so when the clear or the redraw fails.

The operator has already answered Yes to a swarm-wide destructive prompt,
so a silent return is indistinguishable from a completed clear.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

import src.core.event_bus as event_bus  # noqa: E402
from src.gui.visualizer.quick_routing import QuickRoutingMatrix  # noqa: E402

LOGGER_NAME = "acervator.gui.bot_visualizer"
PAIRS = [("src-1", "dst-1"), ("src-2", "dst-2")]
LOCKED = "bot_state.json is locked"


class _Viz(QWidget):
    """Parent stand-in whose route clear either raises or returns PAIRS."""

    def __init__(self, clear_raises: bool) -> None:
        super().__init__()
        self.setAccessibleName("quick routing parent stand-in")
        self._clear_raises = clear_raises
        self.clear_calls = 0

    def _clear_all_routes_in_state(self) -> list[tuple[str, str]]:
        self.clear_calls += 1
        if self._clear_raises:
            raise RuntimeError(LOCKED)
        return list(PAIRS)


class _Bus:
    """Event bus stand-in that records emits or refuses to take them."""

    def __init__(self, emit_raises: bool) -> None:
        self._emit_raises = emit_raises
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, topic: str, **payload) -> None:
        if self._emit_raises:
            raise RuntimeError("bus is down")
        self.emitted.append((topic, payload))


@pytest.fixture
def harness(monkeypatch):
    """Build the matrix with Yes pre-answered and every dialog captured."""
    QApplication.instance() or QApplication([])
    shown: list[str] = []

    def _answer_yes(_parent, _title, _text, _buttons, _default):
        return QMessageBox.Yes

    def _capture_warning(_parent, _title, text):
        shown.append(text)

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_answer_yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(_capture_warning))

    def build(clear_raises=False, emit_raises=False):
        viz = _Viz(clear_raises)
        bus = _Bus(emit_raises)
        monkeypatch.setattr(event_bus, "get_event_bus", lambda: bus)
        return QuickRoutingMatrix(viz), viz, bus, shown

    return build


class _Recorder(logging.Handler):
    """Collect the error text this module's logger emits during one call."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def errors():
    """Attach a recorder to the quick-routing logger for one test."""
    recorder = _Recorder()
    logger = logging.getLogger(LOGGER_NAME)
    logger.addHandler(recorder)
    try:
        yield recorder.messages
    finally:
        logger.removeHandler(recorder)


def test_a_clear_that_raises_puts_a_message_in_front_of_the_operator(harness):
    matrix, viz, _bus, shown = harness(clear_raises=True)
    matrix._on_disconnect_all_clicked()
    assert viz.clear_calls == 1, "the clear was never attempted"
    assert shown, "Disconnect All failed and told the operator nothing"
    assert LOCKED in shown[0], shown


def test_a_clear_that_succeeds_puts_no_message_in_front_of_the_operator(harness):
    matrix, viz, _bus, shown = harness()
    matrix._on_disconnect_all_clicked()
    assert viz.clear_calls == 1, "the clear was never attempted"
    assert shown == [], f"a successful clear interrupted the operator: {shown}"


def test_a_clear_that_raises_is_logged_as_an_error(harness, errors):
    matrix, _viz, _bus, _shown = harness(clear_raises=True)
    matrix._on_disconnect_all_clicked()
    assert any("no wire was removed" in m for m in errors), errors


def test_a_clear_that_succeeds_logs_no_error(harness, errors):
    matrix, _viz, _bus, _shown = harness()
    matrix._on_disconnect_all_clicked()
    assert errors == [], errors


def test_a_redraw_that_raises_is_logged_as_an_error(harness, errors):
    matrix, _viz, _bus, _shown = harness(emit_raises=True)
    matrix._on_disconnect_all_clicked()
    assert any("redraw events FAILED" in m for m in errors), errors


def test_a_redraw_that_succeeds_emits_one_event_per_removed_pair(harness):
    matrix, _viz, bus, _shown = harness()
    matrix._on_disconnect_all_clicked()
    assert [t for t, _p in bus.emitted] == ["wire.removed"] * len(PAIRS)


def test_a_declined_confirmation_never_reaches_the_clear(harness, monkeypatch):
    matrix, viz, _bus, shown = harness()

    def _answer_no(_parent, _title, _text, _buttons, _default):
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "question", staticmethod(_answer_no))
    matrix._on_disconnect_all_clicked()
    assert viz.clear_calls == 0, "answering No still cleared every wire"
    assert shown == [], f"answering No showed a dialog: {shown}"
