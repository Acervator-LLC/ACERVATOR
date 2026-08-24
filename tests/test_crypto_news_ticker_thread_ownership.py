"""Issue #105 — the news ticker must never destroy a running QThread.

WHAT WAS WRONG. ``force_refresh`` built ``QThread(self)``, a thread
PARENTED TO THE WIDGET, and ``_teardown_worker`` called ``wait(50)``
and then ``deleteLater()`` whatever that wait returned. Both halves
destroy a RUNNING QThread, and Qt answers that with ``std::terminate``:
exit 127, no traceback, no failure summary. Measured on the shipped
file, offscreen, both recipes.

A FAILURE IN THIS FILE MEANS the ticker can abort the trading
application from a teardown, with nothing written down for the crash
watchdog to read.

Nothing here opens a socket to a third party. The one network test
drives a loopback server that never finishes its body, which is the
shape the 50 ms wait could not survive.
"""
from __future__ import annotations

import multiprocessing
import os
import socket
import threading
import time
import warnings

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QThread, QTimer              # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget     # noqa: E402
from shiboken6 import Shiboken                          # noqa: E402

from src.gui import crypto_news_ticker as cnt           # noqa: E402

SRC = cnt.NewsSource("test", "Test Feed", "https://example.invalid/feed")


@pytest.fixture(name="qt_app")
def _qt_app() -> QApplication:
    """One QApplication for the module, as Qt requires.

    ``QApplication.instance()`` is typed as ``QCoreApplication``, which
    is the wider class. The isinstance narrows it rather than asserting
    the narrowing in a comment.
    """
    existing = QApplication.instance()
    if isinstance(existing, QApplication):
        return existing
    return QApplication([])


@pytest.fixture(name="ticker")
def _ticker(qt_app: QApplication):
    """A ticker whose fetch never touches the network.

    Torn down with ``stop()`` so no test leaves a live thread behind
    for the next one to trip over.
    """
    assert qt_app is not None
    widget = cnt.CryptoNewsTicker()
    yield widget
    widget.stop()


class _Blocker:
    """A stand-in fetch that blocks until it is released.

    ``honours_stop=False`` models a fetch that cannot be interrupted at
    all -- a third-party host mid-request, which is what the old
    ``wait(50)`` met. ``honours_stop=True`` models the repaired
    ``fetch_all``, which polls its flag.
    """

    def __init__(self, honours_stop: bool, limit_s: float = 5.0) -> None:
        self.honours_stop = honours_stop
        self.limit_s = limit_s
        self.entered = threading.Event()
        # An OUT-OF-BAND release, for teardown only. It is
        # deliberately not the product stop flag: a test that
        # needs an unstoppable fetch must still get one, or it is
        # not testing the abandon path. This lets such a test hand
        # the thread back in milliseconds instead of idling out
        # `limit_s`.
        self.released = threading.Event()

    def __call__(self, *_a, **kw):
        self.entered.set()
        should_stop = kw.get("should_stop")
        end = time.monotonic() + self.limit_s
        while time.monotonic() < end:
            if self.released.is_set():
                return []
            if self.honours_stop and should_stop is not None \
                    and should_stop():
                return []
            time.sleep(cnt.FETCH_POLL_S / 2)
        return []


def _run_fetch(ticker, blocker: _Blocker, qt_app: QApplication) -> None:
    """Start a fetch and wait until the worker is really inside it."""
    ticker.force_refresh()
    qt_app.processEvents()
    assert blocker.entered.wait(3.0), (
        "the worker never entered the fetch, so nothing below is a "
        "test of an in-flight teardown")


# ------------------------------------------------------------------
# The ownership defect itself.
# ------------------------------------------------------------------

class TestThreadOwnership:
    def test_fetch_thread_is_not_parented_to_the_widget(
            self, monkeypatch, ticker, qt_app):
        """A FAILURE HERE MEANS destroying the widget destroys a
        running thread, which is ``std::terminate``."""
        blocker = _Blocker(honours_stop=True)
        monkeypatch.setattr(cnt, "fetch_all", blocker)
        _run_fetch(ticker, blocker, qt_app)
        thread = ticker._worker_thread
        assert thread is not None
        assert thread.parent() is None, (
            "the fetch thread is a child of the widget again")
        assert thread not in ticker.findChildren(QThread)

    def test_the_registry_holds_thread_and_worker(
            self, monkeypatch, ticker, qt_app):
        """A FAILURE HERE MEANS the only reference to a running worker
        belongs to the widget, so the widget going away collects the
        worker mid-emit -- issue #58."""
        blocker = _Blocker(honours_stop=True)
        monkeypatch.setattr(cnt, "fetch_all", blocker)
        _run_fetch(ticker, blocker, qt_app)
        thread = ticker._worker_thread
        assert thread in cnt._LIVE_WORKERS
        assert cnt._LIVE_WORKERS[thread] is ticker._worker

    def test_destroying_the_widget_leaves_the_thread_alive(
            self, monkeypatch, qt_app):
        """The recipe that aborted the suite 2,573 tests in.

        A FAILURE HERE MEANS widget destruction reaches the thread
        again.
        """
        blocker = _Blocker(honours_stop=True)
        monkeypatch.setattr(cnt, "fetch_all", blocker)
        holder = QWidget()
        widget = cnt.CryptoNewsTicker(holder)
        widget.force_refresh()
        qt_app.processEvents()
        assert blocker.entered.wait(3.0)
        thread = widget._worker_thread
        assert thread is not None
        holder.deleteLater()
        del widget
        del holder
        qt_app.processEvents()
        assert Shiboken.isValid(thread), (
            "the thread was destroyed with the widget")
        assert thread in cnt._LIVE_WORKERS
        # Release it the way the shipped path does.
        cnt._LIVE_WORKERS[thread].request_stop()
        assert thread.wait(cnt._STOP_WAIT_MS)


class TestStopIsBounded:
    def test_stop_returns_and_clears_when_the_fetch_honours_the_flag(
            self, monkeypatch, ticker, qt_app):
        """The repaired path. A FAILURE HERE MEANS the stop flag no
        longer reaches the fetch, so the bounded wait cannot succeed
        and every teardown falls back to abandoning a thread."""
        blocker = _Blocker(honours_stop=True)
        monkeypatch.setattr(cnt, "fetch_all", blocker)
        _run_fetch(ticker, blocker, qt_app)
        started = time.monotonic()
        ticker.stop()
        elapsed = time.monotonic() - started
        assert elapsed < cnt._STOP_WAIT_MS / 1000.0, (
            "stop() used the whole bound, so the wait timed out")
        assert ticker._worker_thread is None
        assert ticker._worker is None

    def test_stop_abandons_rather_than_destroys_an_unstoppable_thread(
            self, monkeypatch, ticker, qt_app, capture_log):
        """The pathological branch, driven rather than assumed.

        A FAILURE HERE MEANS a thread that will not stop is destroyed
        anyway, which is the abort.

        ``capture_log`` rather than ``caplog``, for the reason
        ``tests/conftest.py`` gives at the fixture and the sibling
        defusedxml file repeats: ``logging_engine`` sets
        ``acervator.propagate = False``, so once ANY earlier test has
        built the engine, no record from this logger reaches the root
        handler ``caplog`` installs. This test shipped with ``caplog``
        and was therefore green alone and green as a file -- neither
        builds the engine -- and red at file 69 of the full run. Worse
        than red: for as long as it was green it could not fail, so it
        asserted nothing.

        The capture is taken at TWO nodes on purpose. The inner one is
        the emitting logger, and proves the line is emitted at all. The
        outer one is ``acervator``, which is the node ``logging_engine``
        hangs its file handlers on -- so it proves the record still
        REACHES the operator's crash watchdog, rather than only that
        some logger somewhere saw it.
        """
        blocker = _Blocker(honours_stop=False, limit_s=4.0)
        monkeypatch.setattr(cnt, "fetch_all", blocker)
        _run_fetch(ticker, blocker, qt_app)
        with capture_log("acervator") as at_engine_node:
            with capture_log("acervator.crypto_news_ticker") as at_emitter:
                ticker.stop()
        thread = ticker._worker_thread
        assert thread is not None, (
            "the reference was dropped, so force_refresh can start a "
            "second fetch beside the first -- issue #58 tail")
        assert Shiboken.isValid(thread), "a running thread was destroyed"
        assert thread.isRunning()
        assert any("did not stop" in r.getMessage() for r in at_emitter), (
            "the abandon was silent; the watchdog gets nothing to read")
        assert any("did not stop" in r.getMessage()
                   for r in at_engine_node), (
            "the abandon was logged but does not propagate to the "
            "`acervator` node, where logging_engine attaches the "
            "handler that writes ~/.acervator_logs/console/system.log. "
            "The watchdog would still get nothing to read.")
        assert thread.wait(6000)

    def test_force_refresh_refuses_a_second_fetch_after_a_failed_stop(
            self, monkeypatch, ticker, qt_app):
        """A FAILURE HERE MEANS two fetches can run at once, because
        the guard reads a reference a timed-out teardown cleared."""
        blocker = _Blocker(honours_stop=False, limit_s=4.0)
        monkeypatch.setattr(cnt, "fetch_all", blocker)
        _run_fetch(ticker, blocker, qt_app)
        ticker.stop()
        first = ticker._worker_thread
        ticker.force_refresh()
        assert ticker._worker_thread is first
        assert first is not None
        assert first.wait(6000)

    @pytest.mark.parametrize("stops", [1, 2, 3])
    def test_only_the_first_stop_does_work(
            self, monkeypatch, qt_app, capture_log, stops):
        """A second stop() on an abandoned worker must be a no-op.

        This shape is REACHABLE IN THE PRODUCT, not only in a fixture.
        When a wait fails the thread is abandoned and both references
        stay set on purpose, so the next caller -- an application close
        after a failed tab teardown -- arrives with the same worker
        still attached.

        A FAILURE HERE MEANS that second call does the work again:

          * it blocks the GUI thread for another whole _STOP_WAIT_MS on
            a thread already flagged and already asked to quit;
          * it writes the abandon ERROR again, so the operator crash
            watchdog reads two thread failures where one happened;
          * it re-detaches signals already detached, which libpyside
            reports as "Failed to disconnect (None) from signal".

        The duplicated log line is the one that matters. A log read
        during a crash must not multiply its own entries by the number
        of times something polite called stop().

        stops=1 is the built-in control. It must pass with the guard
        present OR absent, which is what shows the other two shapes
        fail for the guard and not for some unrelated reason.
        """
        # Long enough that no wait in this test can succeed, so an
        # unguarded extra stop fails its own wait and logs its own
        # error rather than quietly succeeding.
        blocker = _Blocker(honours_stop=False, limit_s=30.0)
        monkeypatch.setattr(cnt, "fetch_all", blocker)
        widget = cnt.CryptoNewsTicker()
        try:
            _run_fetch(widget, blocker, qt_app)
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                with capture_log("acervator.crypto_news_ticker") as records:
                    started = time.monotonic()
                    widget.stop()
                    first_elapsed = time.monotonic() - started
                    extra_elapsed = []
                    for _ in range(stops - 1):
                        mark = time.monotonic()
                        widget.stop()
                        extra_elapsed.append(time.monotonic() - mark)

            bound_s = cnt._STOP_WAIT_MS / 1000.0
            assert first_elapsed >= bound_s * 0.5, (
                f"the FIRST stop returned in {first_elapsed:.3f}s; it "
                f"never waited, so this test is not driving the abandon "
                f"path at all")
            for index, elapsed in enumerate(extra_elapsed, start=2):
                assert elapsed < bound_s * 0.25, (
                    f"stop() call {index} took {elapsed:.3f}s against a "
                    f"{bound_s:.1f}s bound: an extra stop repeats the "
                    f"wait instead of being a no-op")

            abandons = [r for r in records
                        if "did not stop" in r.getMessage()]
            assert len(abandons) == 1, (
                f"{stops} stop() calls wrote {len(abandons)} abandon "
                f"ERROR lines; the crash watchdog would read "
                f"{len(abandons)} thread failures where 1 happened")

            failed_disconnects = [
                str(w.message) for w in caught
                if "Failed to disconnect" in str(w.message)]
            assert failed_disconnects == [], (
                "an extra stop re-detached signals the first stop had "
                f"already detached: {failed_disconnects}")
        finally:
            blocker.released.set()
            thread = widget._worker_thread
            if thread is not None:
                thread.wait(10000)

    def test_the_stop_bound_is_derived_from_the_poll_slice(self):
        """The bound must stay a multiple of the only blocking step
        left on the worker thread, not a fresh magic number."""
        assert cnt._STOP_WAIT_MS / 1000.0 >= 20 * cnt.FETCH_POLL_S


class TestWorkerStaysSilentAfterStop:
    def test_a_stopped_worker_emits_nothing(self, qt_app):
        """Issue #58, the emit half. A FAILURE HERE MEANS a result
        arrives at a widget that asked to be left alone."""
        assert qt_app is not None
        worker = cnt._FetchWorker()
        seen: list[object] = []
        worker.headlinesReady.connect(seen.append)
        worker.failed.connect(seen.append)
        worker.request_stop()
        worker.run()
        assert seen == []

    def test_an_unstopped_worker_still_emits(self, monkeypatch, qt_app):
        """The positive control for the test above: with the flag
        clear, the same call DOES deliver."""
        assert qt_app is not None
        monkeypatch.setattr(cnt, "fetch_all", lambda **_kw: [])
        worker = cnt._FetchWorker()
        seen: list[object] = []
        worker.headlinesReady.connect(seen.append)
        worker.run()
        assert seen == [[]]

    def test_run_on_the_gui_thread_does_not_quit_the_event_loop(
            self, monkeypatch, qt_app):
        """`run` quits its own thread in a finally. A FAILURE HERE
        MEANS that finally can stop the event loop of the whole
        application when `run` is reached from the GUI thread."""
        monkeypatch.setattr(cnt, "fetch_all", lambda **_kw: [])
        worker = cnt._FetchWorker()
        QTimer.singleShot(0, worker.run)
        QTimer.singleShot(300, qt_app.quit)
        started = time.monotonic()
        qt_app.exec()
        elapsed = time.monotonic() - started
        assert elapsed > 0.2, (
            f"the event loop returned after {elapsed:.3f}s, so run() "
            f"quit the GUI thread")


# ------------------------------------------------------------------
# The reason 50 ms could never work: the fetch had no bound.
# ------------------------------------------------------------------

class TestFetchIsBounded:
    def test_fetch_all_returns_inside_its_budget(self, monkeypatch):
        """A FAILURE HERE MEANS ``fetch_all`` waits on the pool again,
        so no teardown wait can be chosen that works."""
        def _slow(_source, *_a, **_kw):
            time.sleep(5.0)
            return []

        monkeypatch.setattr(cnt, "fetch_one", _slow)
        started = time.monotonic()
        out = cnt.fetch_all((SRC, SRC, SRC), budget_s=0.4)
        elapsed = time.monotonic() - started
        assert out == []
        assert elapsed < 2.0, (
            f"fetch_all took {elapsed:.2f}s for a 0.4s budget")

    def test_fetch_all_returns_promptly_once_stop_is_set(
            self, monkeypatch):
        """A FAILURE HERE MEANS the stop flag is not read between
        feeds, so the worker cannot return inside the teardown bound."""
        def _slow(_source, *_a, **_kw):
            time.sleep(5.0)
            return []

        monkeypatch.setattr(cnt, "fetch_one", _slow)
        flag = threading.Event()
        flag.set()
        started = time.monotonic()
        cnt.fetch_all((SRC, SRC), should_stop=flag.is_set, budget_s=30.0)
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, (
            f"a stopped fetch_all took {elapsed:.2f}s")

    def test_fetch_all_keeps_the_feeds_that_did_answer(self, monkeypatch):
        """A partial ticker beats an empty one. A FAILURE HERE MEANS a
        slow feed can still empty the whole strip."""
        fast = cnt.NewsHeadline("Fast", "https://ex/1", SRC, 10.0)

        def _mixed(source, *_a, **_kw):
            if source.slug == "slow":
                time.sleep(5.0)
                return []
            return [fast]

        monkeypatch.setattr(cnt, "fetch_one", _mixed)
        slow = cnt.NewsSource("slow", "Slow", "https://example.invalid/s")
        out = cnt.fetch_all((SRC, slow), budget_s=0.5)
        assert [h.title for h in out] == ["Fast"]

    def test_read_is_abandoned_when_stop_is_requested(self):
        """A FAILURE HERE MEANS a body still streams to its end after
        the widget asked to go away."""
        flag = threading.Event()
        flag.set()
        assert cnt._read_bounded(
            _Stream(b"x" * 4096), SRC, flag.is_set, None) is None

    def test_read_is_abandoned_past_the_deadline(self):
        """A FAILURE HERE MEANS a drip-feeding host sets the duration
        of the fetch."""
        assert cnt._read_bounded(
            _Stream(b"x" * 4096), SRC, cnt._never_stop,
            time.monotonic() - 1.0) is None

    def test_read_returns_the_whole_body_when_nothing_interferes(self):
        """The positive control for the two tests above."""
        body = b"y" * (cnt.READ_CHUNK_BYTES * 2 + 17)
        assert cnt._read_bounded(
            _Stream(body), SRC, cnt._never_stop,
            time.monotonic() + 30.0) == body


class _Stream:
    """A minimal advancing read source for ``_read_bounded``."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self._offset = 0

    def read(self, amount: int) -> bytes:
        chunk = self._body[self._offset:self._offset + amount]
        self._offset += len(chunk)
        return chunk


# ------------------------------------------------------------------
# The falsifier, out of process. This is the recipe that produced the
# abort on the shipped file.
#
# A SEPARATE PROCESS IS THE POINT. `std::terminate` prints no
# traceback and no failure summary, so a suite that meets it reports
# nothing at all -- measured here: with the repair reverted, a run of
# this very file ended with status 3221226505 and printed no FAILED
# line. An exit code is the only thing left to read, and only a child
# process has one.
#
# `multiprocessing` rather than `subprocess`: a spawned child re-imports
# this module and runs `_shipped_recipe` by name, so there is no argv
# to build and no command string for a reader to have to trust.
# ------------------------------------------------------------------

def _shipped_recipe(mode: str) -> None:
    """Drive the ticker teardown in a fresh process. Child entry point."""
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication, QEvent, QTimer
    from PySide6.QtWidgets import QApplication
    from src.gui import crypto_news_ticker as tk

    def _unstoppable(*_a, **_kw):
        time.sleep(3.0)
        return []

    app = QApplication.instance() or QApplication([])
    tk.fetch_all = _unstoppable
    widget = tk.CryptoNewsTicker()
    widget.show()
    widget.start()
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()
    if mode == "stop":
        widget.stop()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    else:
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(widget, QEvent.DeferredDelete)
    app.processEvents()
    QTimer.singleShot(0, app.quit)
    app.exec()


@pytest.mark.parametrize("mode", ["stop", "destroy"])
def test_the_shipped_recipe_no_longer_aborts(mode):
    """The reproduction, out of process, exit code checked.

    The abort has two spellings for one event. A POSIX shell reports it
    as 127; a raw Windows status is 3221226505, which is 0xC0000409,
    the fast-fail code. Both are named below, so a failure says what
    happened rather than only that a number was wrong. Before the
    repair both modes aborted.
    """
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=_shipped_recipe, args=(mode,))
    proc.start()
    proc.join(180)
    assert not proc.is_alive(), "the child hung; killed by the join bound"
    aborts = {127, 3221226505, -6, -1073740791}
    assert proc.exitcode not in aborts, (
        f"std::terminate (exit {proc.exitcode}): the ticker destroyed a "
        f"running QThread from the {mode!r} recipe")
    assert proc.exitcode == 0, f"child exit {proc.exitcode}"


# ------------------------------------------------------------------
# The real fetch path, against a host that never finishes.
# ------------------------------------------------------------------

def _start_drip_server():
    """Loopback HTTP server: one byte every 0.5 s, body never ends."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)
    stop = threading.Event()

    def _serve() -> None:
        while not stop.is_set():
            try:
                conn, _addr = srv.accept()
            except OSError:
                return
            threading.Thread(target=_drip, args=(conn,),
                             daemon=True).start()

    def _drip(conn) -> None:
        try:
            conn.recv(4096)
            conn.sendall(b"HTTP/1.1 200 OK\r\n"
                         b"Content-Type: application/xml\r\n"
                         b"Connection: close\r\n\r\n")
            while not stop.is_set():
                conn.sendall(b"<")
                time.sleep(0.5)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    threading.Thread(target=_serve, daemon=True).start()
    return srv.getsockname()[1], stop, srv


def test_stop_beats_a_host_that_never_finishes(monkeypatch, qt_app):
    """The condition the 50 ms wait was written for, driven for real.

    A FAILURE HERE MEANS a teardown during a live fetch still cannot
    complete, whatever the wait is set to.
    """
    port, stop_flag, srv = _start_drip_server()
    sources = tuple(
        cnt.NewsSource("drip%d" % i, "Drip %d" % i,
                       "http://127.0.0.1:%d/f%d.xml" % (port, i))
        for i in range(3))
    real_fetch_all = cnt.fetch_all

    def _local_fetch_all(*_a, **kw):
        # fetch_all binds NEWS_SOURCES as a DEFAULT argument, so
        # rebinding the module global would not reach it. Nothing here
        # leaves 127.0.0.1.
        return real_fetch_all(sources, **kw)

    monkeypatch.setattr(cnt, "fetch_all", _local_fetch_all)
    widget = cnt.CryptoNewsTicker()
    try:
        widget.force_refresh()
        qt_app.processEvents()
        time.sleep(1.0)
        started = time.monotonic()
        widget.stop()
        elapsed = time.monotonic() - started
        assert widget._worker_thread is None, (
            "the thread did not stop, so the fetch is still not "
            "interruptible")
        assert elapsed < cnt._STOP_WAIT_MS / 1000.0
    finally:
        widget.stop()
        stop_flag.set()
        srv.close()
