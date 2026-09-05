"""Pin tests for the six suppression repairs in the main window.

Suppression audit 2026-08-13, sections H1, H2, H3, H5, H6 and H7. Each
directive hid a finding whose own message described a real defect: a
failure that reached no surface the operator reads.

Every test drives the REAL method, taken off the real class, and reads
the real surface -- the StatusLog widget, the API tester result view, or
the module logger. None of them inspects source text.

Two-sided control. Every "records" assertion below was run against the
unmodified tree first and failed there, and every "unchanged" assertion
passed there. The tests separate the repaired behaviour from the
behaviour that shipped; they do not merely restate it.

This file carries no suppression directive of any spelling. The unit
it covers REMOVES them, so adding one here would be self-defeating. Qt
and application imports are therefore function-local rather than
module-level behind an import-order pragma.
"""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
import sys
import threading

import pytest

# Set before anything imports Qt. conftest puts the repository on
# sys.path already, so this module adds nothing to it.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

# The colour StatusLog paints an "error" line, so a test reads the level off
# the surface rather than off the argument.
ERROR_COLOUR = "#ff3366"


def _mw():
    from src.gui import main_window

    return main_window


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    yield app


def _driven(*names: str, owner: str = "MainWindow"):
    """An object carrying the REAL functions named, off the real class.

    Constructing a MainWindow needs the whole application. Borrowing the
    functions keeps every call inside them resolving to live code, which
    a bare stub does not: `self._schedule_async` would raise
    AttributeError and the handler under test would swallow THAT, which
    is a different path from the one the application takes. Measured
    2026-08-13 -- it produced a plausible but wrong result.
    """
    cls = getattr(_mw(), owner)
    return type("Driven", (), {n: getattr(cls, n) for n in names})()


class _LogSink(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture
def gui_log():
    sink = _LogSink()
    log = logging.getLogger("acervator.gui")
    previous = log.level
    log.addHandler(sink)
    log.setLevel(logging.DEBUG)
    yield sink
    log.setLevel(previous)
    log.removeHandler(sink)


def _errors(sink: _LogSink) -> list[logging.LogRecord]:
    return [r for r in sink.records if r.levelno >= logging.ERROR]


# ---------------------------------------------------------------- H1 --
# The bot-delete path swallowed the only stop. MONEY, LIVE-ORDER.


class _StopSpy:
    def __init__(self) -> None:
        self.ran: int = 0

    async def stop(self) -> None:
        self.ran += 1


class _Manager:
    def __init__(self, bot: _StopSpy) -> None:
        self._bot = bot
        self.unregistered: list[str] = []

    def get_bot(self, bot_id: str) -> _StopSpy:
        del bot_id
        return self._bot

    def unregister(self, bot_id: str) -> None:
        self.unregistered.append(bot_id)


class _Spool:
    def __init__(self) -> None:
        self.notes: list[tuple[str, str]] = []

    def notify(self, msg: str, level: str = "info") -> None:
        self.notes.append((msg, level))


class _YesBox:
    Yes = 0x4000
    No = 0x10000

    @staticmethod
    def question(*args, **kwargs) -> int:
        del args, kwargs
        return _YesBox.Yes


class _SilentSound:
    def __init__(self) -> None:
        self.played: list[str] = []

    def play_state_change(self) -> None:
        self.played.append("state")

    def play_error(self) -> None:
        self.played.append("error")


@pytest.fixture
def delete_rig(qapp, monkeypatch):
    """Answer the modal Yes and silence the sound engine.

    The operator runs this build against real money; a test must not
    make his machine play the state-change chime.
    """
    del qapp
    import src.core.sound_engine as sound_engine

    mw = _mw()
    monkeypatch.setattr(mw, "QMessageBox", _YesBox)
    monkeypatch.setattr(sound_engine, "get_sound_engine", _SilentSound)

    def _build(loop):
        bot = _StopSpy()
        manager = _Manager(bot)
        win = _driven("_on_bot_command", "_schedule_async")
        win._bot_manager = manager
        win._spool = _Spool()
        win._status_log = mw.StatusLog()
        win._async_loop = loop
        return win, manager, bot

    return _build


def test_h1_delete_records_a_failed_stop_at_the_operators_surface(delete_rig):
    """A closed loop is the shutdown window the audit named.

    A failure here would mean the only stop on the delete path is still
    swallowed: the bot is popped from the manager while its task keeps
    trading against the exchange, and the operator reads nothing but a
    success.
    """
    loop = asyncio.new_event_loop()
    loop.close()
    win, manager, bot = delete_rig(loop)

    win._on_bot_command("BTC-1", "delete")

    surface = win._status_log.toPlainText()
    failures = [ln for ln in surface.splitlines() if "Failed to stop" in ln]
    assert len(failures) == 1, surface
    assert "BTC-1" in failures[0]
    assert ERROR_COLOUR in win._status_log.toHtml()
    # The stop never reached the bot, which is exactly why it is worth
    # saying out loud.
    assert bot.ran == 0
    assert manager.unregistered == ["BTC-1"]


def test_h1_ordinary_delete_stops_the_bot_and_logs_nothing_spurious(delete_rig):
    """The healthy path must be untouched.

    A failure here would mean the repair changed the ordinary delete:
    either it now cries wolf on a delete that worked, or it stopped
    reaching bot.stop() at all.
    """
    win, manager, bot = delete_rig(None)

    win._on_bot_command("BTC-1", "delete")

    surface = win._status_log.toPlainText()
    assert "Failed to stop" not in surface
    assert ERROR_COLOUR not in win._status_log.toHtml()
    deleted = [ln for ln in surface.splitlines() if "deleted" in ln]
    assert len(deleted) == 1, surface
    assert bot.ran == 1
    assert manager.unregistered == ["BTC-1"]


# ---------------------------------------------------------------- H2 --
# The wire verifier answered "registered" when it did not know. MONEY.


class _WireManager:
    def __init__(self, behaviour: str) -> None:
        self.behaviour = behaviour

    def get_outgoing_wires(self, src_id: str):
        del src_id
        if self.behaviour == "mapping":
            return {"BOT-T": 25.0}
        if self.behaviour == "empty":
            return {}
        if self.behaviour == "none":
            return None
        raise AttributeError("SmartWireManager has no get_outgoing_wires")


class _BotManagerWithWires:
    def __init__(self, wire_manager) -> None:
        if wire_manager is not None:
            self.smart_wire_manager = wire_manager


def _wire_win(wire_manager):
    win = _driven("_wire_is_registered", "_wire_manager")
    win._bot_manager = _BotManagerWithWires(wire_manager)
    return win


@pytest.mark.parametrize(
    ("behaviour", "expected"),
    [(None, True), ("mapping", True), ("empty", False), ("none", False)],
)
def test_h2_verifier_unchanged_rows(behaviour, expected):
    """The three rows the repair must not move.

    A failure here would mean the repair changed an answer it had no
    business changing: a missing engine now reads as a refusal, or a
    confirmed wire now reads as unconfirmed.
    """
    manager = None if behaviour is None else _WireManager(behaviour)
    assert _wire_win(manager)._wire_is_registered("BOT-S", "BOT-T") is expected


def test_h2_unreadable_engine_is_not_counted_as_registered(gui_log):
    """The one row that moved.

    A failure here would mean the verifier still answers "the engine
    took it" when the engine is present and its read-back raised. The
    caller counts that as a drawn wire, so the operator is told wires
    are routing profit that no engine holds.
    """
    win = _wire_win(_WireManager("raise"))

    assert win._wire_is_registered("BOT-S", "BOT-T") is False

    errors = _errors(gui_log)
    assert len(errors) == 1
    assert "BOT-S" in errors[0].getMessage()
    assert "BOT-T" in errors[0].getMessage()
    assert errors[0].exc_info is not None


# ---------------------------------------------------------------- H3 --
# Disconnect reported a success it did not achieve. LIVE-ORDER.


class _Connector:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.ran: list[str] = []

    async def _close(self) -> None:
        self.ran.append("closed")
        if self.mode == "worker-raise":
            raise ConnectionResetError("socket already gone")

    def disconnect(self):
        if self.mode == "call-raise":
            raise RuntimeError("connector interface changed")
        return self._close()


def _api_tab(mode: str):
    from PySide6.QtWidgets import QLabel, QPushButton, QTextEdit

    win = _driven("_do_disconnect", "_log", owner="APITesterTab")
    win._connector = _Connector(mode)
    win._connected = True
    win._connect_btn = QPushButton()
    win._disconnect_btn = QPushButton()
    win._conn_status = QLabel()
    win._result_info = QLabel()
    win._result_view = QTextEdit()
    return win


@pytest.mark.parametrize("mode", ["worker-raise", "call-raise"])
def test_h3_failed_disconnect_is_recorded(qapp, mode):
    """Both layers the audit named, driven for real.

    "worker-raise" is the exception that used to die with the executor
    because nothing read the Future. "call-raise" is the one the handler
    could see and dropped with a bare pass.

    A failure here would mean the operator is still told the exchange
    connection closed while the session may still be open, with the only
    reference to it already discarded.
    """
    del qapp
    win = _api_tab(mode)

    win._do_disconnect()

    surface = win._result_view.toPlainText()
    assert "DISCONNECT FAILED" in surface
    assert "may still be open" in surface
    # The reference is still dropped: this unit records the failure, it
    # does not change what the handler does about it.
    assert win._connector is None


def test_h3_clean_disconnect_says_nothing_extra(qapp):
    """The healthy path must be untouched.

    A failure here would mean the repair reports a failure on a
    disconnect that succeeded.
    """
    del qapp
    win = _api_tab("ok")

    win._do_disconnect()

    surface = win._result_view.toPlainText()
    assert "DISCONNECT FAILED" not in surface
    assert "Connection closed" in surface
    assert win._connector is None


# ---------------------------------------------------------------- H5 --
# A journal write was dropped in silence. STATE-WRITE.


class _Journal:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.rows: list[object] = []

    def record(self, rec: object) -> None:
        if self.mode == "raise":
            raise OSError("journal file is read-only")
        self.rows.append(rec)


class _FeedbackEvent:
    def __init__(self) -> None:
        self.data = {
            "feedback": "watch the BTC ladder",
            "authenticated": True,
            "timestamp": "T",
        }


class _FeedbackSettings:
    @staticmethod
    def get(key: str, default=None):
        del key, default
        return {"log_feedback": True}


def _feedback_win(mode: str):
    win = _driven("_on_ai_feedback")
    win._settings = _FeedbackSettings()
    win._status_log = _mw().StatusLog()
    win._journal = _Journal(mode)
    return win


def test_h5_dropped_journal_note_is_recorded(qapp, gui_log):
    """A failure here would mean an AI_FEEDBACK note that never reached
    the journal leaves no trace anywhere that it did not.
    """
    del qapp
    win = _feedback_win("raise")

    win._on_ai_feedback(_FeedbackEvent())

    assert win._journal.rows == []
    errors = _errors(gui_log)
    assert len(errors) == 1
    assert "journal" in errors[0].getMessage()


def test_h5_written_journal_note_says_nothing(qapp, gui_log):
    """A failure here would mean the repair logs an error on the path
    where the note WAS written.
    """
    del qapp
    win = _feedback_win("ok")

    win._on_ai_feedback(_FeedbackEvent())

    assert len(win._journal.rows) == 1
    assert _errors(gui_log) == []


# ---------------------------------------------------------------- H6 --
# Bot error records were dropped on a malformed event. OBSERVABILITY.


class _ErrorEvent:
    def __init__(self, data: dict) -> None:
        self.data = data


class _PoisonedEvent:
    @property
    def data(self) -> dict:
        raise ValueError("event payload is poisoned")


def _error_log_win():
    win = _driven("_on_bot_error_for_log")
    win._error_log_buffer = []
    return win


def test_h6_malformed_event_drop_is_recorded(gui_log):
    """A non-numeric "consecutive" raises ValueError on the int().

    A failure here would mean a malformed bot.error event still drops
    the WHOLE error record with nothing anywhere to say the Errors card
    is under-reporting.
    """
    win = _error_log_win()

    win._on_bot_error_for_log(
        _ErrorEvent({"bot_id": "BTC-1", "error": "429", "consecutive": "three"})
    )

    assert win._error_log_buffer == []
    errors = _errors(gui_log)
    assert len(errors) == 1
    assert "dropped" in errors[0].getMessage()


def test_h6_well_formed_event_is_buffered_quietly(gui_log):
    """A failure here would mean the repair broke ordinary telemetry
    capture, or now cries wolf on a healthy event.
    """
    win = _error_log_win()

    win._on_bot_error_for_log(
        _ErrorEvent({"bot_id": "BTC-1", "error": "429", "consecutive": 3})
    )

    assert len(win._error_log_buffer) == 1
    row = win._error_log_buffer[0]
    assert row[1] == "BTC-1"
    assert row[3] == 3
    assert _errors(gui_log) == []


@pytest.mark.parametrize(
    "event",
    [
        _ErrorEvent({"bot_id": "BTC-1", "error": "429", "consecutive": 3}),
        _ErrorEvent({"bot_id": "BTC-1", "error": "429", "consecutive": "three"}),
        None,
        _PoisonedEvent(),
    ],
)
def test_h6_never_raises_over_the_closed_input_table(event, gui_log):
    """The docstring claims this slot never raises. This is the proof.

    The claim is closed over the event, which is the only input. A
    failure here would mean the docstring states a property the code
    does not have, and the bot.error listener can take the emitter down
    with it.
    """
    del gui_log
    _error_log_win()._on_bot_error_for_log(event)


def _call_off_gui_thread(win) -> list[BaseException]:
    """Run the slot on a non-GUI thread and collect anything that
    escapes it.

    threading.excepthook rather than a try/except: it sees everything
    that leaves the thread, and it needs no blind except clause of its
    own inside a file whose whole point is that suppressions are gone.
    """
    escaped: list[BaseException] = []

    def _hook(args) -> None:
        if args.exc_value is not None:
            escaped.append(args.exc_value)

    def _run() -> None:
        win._on_api_event({"action": "FETCH_BALANCE", "_thread_name": "asyncio-worker"})

    previous = threading.excepthook
    threading.excepthook = _hook
    try:
        worker = threading.Thread(target=_run, name="Thread-violation-probe")
        worker.start()
        worker.join()
    finally:
        threading.excepthook = previous
    return escaped


@pytest.fixture
def fake_home(monkeypatch, tmp_path):
    """Point Path.home() at a temporary tree.

    The standing constraint is absolute: a test never writes into the
    operator's log tree. This branch of _on_api_event writes a file
    under it, so the test redirects the root rather than exercising the
    operator's own logs.
    """

    def _home(cls) -> pathlib.Path:
        del cls
        return tmp_path

    monkeypatch.setattr(pathlib.Path, "home", classmethod(_home))
    return tmp_path


def test_h7_unwritable_violation_log_reaches_the_logger(fake_home, gui_log):
    """The log directory already exists as a FILE, so mkdir raises --
    the same shape as a permission error or a full disk.

    A failure here would mean the asyncio-on-GUI-thread arc's only field
    instrument writes nothing at all when it cannot write its file, and
    a real thread violation leaves no evidence anywhere.
    """
    (fake_home / ".acervator_logs").write_bytes(b"not a directory")
    win = _driven("_on_api_event")

    assert _call_off_gui_thread(win) == []

    errors = _errors(gui_log)
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert "Thread-violation-probe" in message
    assert "asyncio-worker" in message


def test_h7_writable_violation_log_still_writes_the_file(fake_home, gui_log):
    """A failure here would mean the repair broke the file record it was
    meant to back up, or now logs an error on the path that worked.
    """
    win = _driven("_on_api_event")

    assert _call_off_gui_thread(win) == []

    written = sorted(p.name for p in (fake_home / ".acervator_logs").glob("*"))
    assert len(written) == 1
    assert written[0].startswith("thread_violation_")
    assert _errors(gui_log) == []
