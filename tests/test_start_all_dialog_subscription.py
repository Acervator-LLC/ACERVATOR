"""The Start All dialog says so when it cannot subscribe to the bus.

``StartAllProgressDialog`` sets ``_unsub`` from ``EventBus.subscribe``. A
refusal leaves ``_unsub`` as None and writes one record to ``acervator.gui.start_all``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from src.gui.start_all_progress_dialog import StartAllProgressDialog
from tests.qt_pixel import ensure_app

LOGGER = "acervator.gui.start_all"


def _build_dialog():
    """Return a constructed dialog and the callable that disposes of it."""
    ensure_app()
    dialog = StartAllProgressDialog(object())
    return dialog, dialog.close


def test_a_refused_subscribe_is_logged(capture_log, monkeypatch):
    """A dialog that cannot subscribe leaves a record naming the refusal."""

    def _refuse():
        raise RuntimeError("bus unavailable")

    monkeypatch.setattr("src.core.event_bus.get_event_bus", _refuse)
    with capture_log(LOGGER) as records:
        dialog, dispose = _build_dialog()
    try:
        assert dialog._unsub is None
        assert records, "a refused subscribe produced no log record"
        assert any(
            "bus unavailable" in r.getMessage() for r in records
        ), "the log record does not carry the refusal: %r" % [
            r.getMessage() for r in records
        ]
    finally:
        dispose()


def test_a_successful_subscribe_logs_nothing(capture_log):
    """The same instrument stays empty when ``EventBus.subscribe`` answers."""
    with capture_log(LOGGER) as records:
        dialog, dispose = _build_dialog()
    try:
        assert callable(dialog._unsub)
        assert not records, "a working subscribe logged %r" % [
            r.getMessage() for r in records
        ]
    finally:
        dispose()
