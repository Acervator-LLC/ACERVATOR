"""Pins for the Qt widget teardown and the leak guard — issue #101.

WHY THIS FILE EXISTS
====================
``tests/conftest.py::_destroy_qt_widgets`` looked like careful cleanup
and destroyed nothing. It did ``hide()``, ``setParent(None)``,
``deleteLater()``, then ``processEvents()``. ``deleteLater()`` posts a
``DeferredDelete`` event and ``processEvents()`` never delivers one, so
every widget it "cleaned up" stayed in
``QApplication.topLevelWidgets()`` for the rest of the session.

A surviving widget is not a local problem.
``tests/test_sim_visuals_expand_reentrancy.py`` asks that list for every
open ``QDialog`` and takes element zero. One leftover dialog from ANY
earlier file makes element zero the wrong widget, and the test then
reports its own subject as leaked while it examines a stranger. Three
units spent a full diagnosis each on that shape on 2026-08-23.

WHAT IS PINNED HERE
===================
Every claim in the conftest comment block, as a measurement:

  * the trap        deleteLater() + processEvents() leaves it alive
  * the repair      sendPostedEvents(w, DeferredDelete) destroys it
  * the instrument  _live_top_level_widgets sees it and stops seeing it
  * the sparing     _stop_owned_threads reports a thread that will not
                    stop, so the teardown does not destroy a widget
                    that owns one -- Qt answers that with
                    std::terminate, not an exception

If any of these stops holding, the shared fixture is lying about its
own name again and the next unit pays for it.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import threading
from pathlib import Path
from types import ModuleType

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtWidgets import QApplication, QDialog, QWidget

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFTEST = REPO_ROOT / "tests" / "conftest.py"


def _load_conftest() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "conftest_under_test_widgets", CONFTEST)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cf = _load_conftest()


def _app() -> QApplication:
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    return QApplication(sys.argv)


def _alive(cls: type) -> int:
    return sum(1 for w in _app().topLevelWidgets() if isinstance(w, cls))


# ── The instrument ──────────────────────────────────────────────────

class TestTheInstrumentWorks:
    """A count of zero is a claim about the instrument until the
    instrument has been shown to count something."""

    def test_it_sees_a_widget_that_exists(self) -> None:
        _app()
        before = cf._live_top_level_widgets()
        d = QDialog()
        after = cf._live_top_level_widgets()
        try:
            new = set(after) - set(before)
            assert len(new) == 1, "the probe did not see a live dialog"
            assert after[next(iter(new))] == "QDialog"
        finally:
            d.setParent(None)
            del d

    def test_it_stops_seeing_a_widget_that_is_destroyed(self) -> None:
        _app()
        before = cf._live_top_level_widgets()
        d = QDialog()
        assert len(set(cf._live_top_level_widgets()) - set(before)) == 1
        del d
        assert set(cf._live_top_level_widgets()) - set(before) == set(), (
            "the probe still reports a widget with no owner left")


# ── The trap ────────────────────────────────────────────────────────

class TestDeleteLaterIsTheLeak:
    def test_a_parentless_widget_dies_with_its_last_reference(self) -> None:
        """NEGATIVE CONTROL. Nothing is wrong with plain ownership."""
        before = _alive(QDialog)
        d = QDialog()
        del d
        assert _alive(QDialog) == before

    def test_delete_later_plus_process_events_leaves_it_alive(self) -> None:
        """THE TRAP, stated as a measurement. `processEvents()` does not
        deliver `DeferredDelete`, so the cleanup call CAUSES the leak."""
        app = _app()
        before = _alive(QDialog)
        d = QDialog()
        d.deleteLater()
        del d
        app.processEvents()
        assert _alive(QDialog) == before + 1, (
            "processEvents() now delivers DeferredDelete. If Qt changed "
            "this, the conftest comment block is out of date -- but the "
            "explicit delivery below is still correct and still cheap.")
        # Do not leave it for the next file. This is the repair.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert _alive(QDialog) == before

    def test_delivering_the_event_destroys_it(self) -> None:
        """THE REPAIR."""
        before = _alive(QDialog)
        d = QDialog()
        d.deleteLater()
        QCoreApplication.sendPostedEvents(d, QEvent.Type.DeferredDelete)
        del d
        assert _alive(QDialog) == before

    def test_a_parented_dialog_is_still_a_top_level_widget(self) -> None:
        """`topLevelWidgets()` lists every WINDOW, and a dialog with a
        parent is a window. The teardown loop therefore does reach
        parented dialogs, and `setParent(None)` there is not a no-op."""
        host = QWidget()
        before = _alive(QDialog)
        d = QDialog(host)
        try:
            assert _alive(QDialog) == before + 1
        finally:
            d.setParent(None)
            del d
            host.setParent(None)
            del host


# ── The sparing rule ────────────────────────────────────────────────

class _BlockedThread(QThread):
    """A thread that ignores `quit()` until the test releases it.

    `quit()` ends a QThread's event loop. It cannot interrupt a `run()`
    that is busy, and the news ticker's worker runs a network fetch
    inside `run()`. This class reproduces that shape deterministically
    with an event instead of a socket, so the pin never depends on
    timing or on the network.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.release = threading.Event()

    def run(self) -> None:            # pragma: no cover - other thread
        self.release.wait(30.0)


class TestTheTeardownSparesWhatWouldAbort:
    def test_a_thread_that_will_not_stop_is_reported(
            self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Qt answers a QThread destroyed while running with
        `std::terminate`: no traceback, no failure summary, exit 127.
        `_stop_owned_threads` is the question the teardown asks first."""
        _app()
        monkeypatch.setattr(cf, "_WIDGET_TEARDOWN_WAIT_MS", 50)
        host = QWidget()
        t = _BlockedThread(host)
        t.start()
        try:
            while not t.isRunning():
                pass
            assert cf._stop_owned_threads(host) == 1, (
                "a running thread was reported as stopped; the teardown "
                "would then destroy its owner and abort the process")
        finally:
            t.release.set()
            t.wait(30000)
            t.setParent(None)
            del t
            host.setParent(None)
            del host

    def test_a_thread_that_stops_is_not_reported(self) -> None:
        """A plain QThread runs an event loop, so `quit()` ends it. The
        widget is then safe to destroy, which is the common case."""
        _app()
        host = QWidget()
        t = QThread(host)
        t.start()
        try:
            while not t.isRunning():
                pass
            assert cf._stop_owned_threads(host) == 0
            assert not t.isRunning()
        finally:
            t.wait(30000)
            t.setParent(None)
            del t
            host.setParent(None)
            del host

    def test_a_widget_with_no_threads_costs_nothing(self) -> None:
        _app()
        w = QWidget()
        try:
            assert cf._stop_owned_threads(w) == 0
        finally:
            w.setParent(None)
            del w


# ── The coupled repair: api_logger's handler could not keep its promise

class TestRecordSurvivesADestroyedListener:
    """`src/exchange/api_logger.py` is repaired in the same change,
    because the teardown above cannot destroy anything without it.

    `MainWindow._on_api_event` stays in `APIInteractionLog._listeners`
    after the window is destroyed. The `except Exception` around the
    listener call was there so that a listener which raises cannot
    break `record()`. It could not keep that promise: its own
    diagnostic read `getattr(cb, "__qualname__", repr(cb))`, Python
    built `repr(cb)` on every call, and `repr()` of a bound method
    whose Qt object is gone raises RuntimeError. The RuntimeError left
    the handler and came out of `record()`, which is on the API path.

    Measured 2026-08-24: 39 tests across four files failed on this the
    moment the suite teardown began destroying widgets for real.
    """

    def test_a_listener_whose_repr_raises_does_not_break_record(self) -> None:
        from src.exchange.api_logger import APIInteractionLog

        class _Detonator:
            """A listener shaped like a destroyed Qt bound method: it
            raises when called, when asked for any attribute, and when
            repr'd."""

            def __call__(self, entry: dict) -> None:
                raise RuntimeError("Internal C++ object already deleted.")

            def __getattr__(self, name: str) -> object:
                raise RuntimeError("Internal C++ object already deleted.")

            def __repr__(self) -> str:
                raise RuntimeError("Internal C++ object already deleted.")

        log = APIInteractionLog()
        log._listeners.append(_Detonator())
        entry = log.record(exchange="app", action="PIN", reason="issue 101")
        assert entry["action"] == "PIN", (
            "record() did not return; the listener handler raised out of "
            "it again")

    def test_a_healthy_listener_is_still_named_in_the_log(self) -> None:
        """POSITIVE CONTROL. The repair must not silence the diagnostic
        the handler exists to produce."""
        from src.exchange.api_logger import _listener_name

        class _Named:
            def ping(self) -> None:
                pass

        assert _listener_name(_Named().ping).endswith("_Named.ping")
