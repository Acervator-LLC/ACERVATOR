"""Unit R -- the logging engine records its own faults instead of
swallowing them, and still never raises into the trading loop.

Eight sites in ``logging_engine.py`` were ``try/except/pass``: five bus
teardowns in ``attach_to_bus`` and three recovery blocks in the bus
handlers. ruff S110 flagged all eight ("consider logging the exception")
and the file could not be edited until they were cleared.

The naive repair recurses. Three of the eight were already reporting a
handler fault through ``self._sys_logger``; wrapping that report in
another report through the same logger is why the inner
``except Exception: pass`` was there. So the report is layered instead:
a counter that cannot fail, then the system logger, then ``sys.stderr``
only when the logger is the casualty.

WHAT A FAILURE OF THIS MODULE WOULD MEAN
  * a `raise` escaping any handler -- a broken log writer has reached the
    event bus and from there the trading loop. That is the outcome every
    "fail-soft" docstring in the file promises to prevent, on the path
    that records real orders.
  * an empty counter after a forced fault -- the engine is back to
    swallowing silently, and the operator gets a log that stops without
    ever saying why. That was the shipped behaviour.
  * a counter that fills on a CLEAN run -- the instrument is stuck on and
    every other assertion here is meaningless.
"""

from __future__ import annotations

import logging
import re

import pytest

from src.core.logging_engine import LogManager, _emergency_stderr


class Boom(RuntimeError):
    """A distinct fault type so a record is unambiguous."""


class RefusingBus:
    """A bus whose ``unsubscribe`` raises for one topic.

    The real shape the five teardown guards defend against.
    ``attach_to_bus`` takes an untyped ``bus`` and the repo's own
    ``EventBus.unsubscribe`` documents "Never raises", so a raise here
    means a foreign object that does not honour that contract.
    """

    def __init__(self, bad_topic: str) -> None:
        self.bad_topic = bad_topic

    def subscribe(self, topic: str, _cb: object) -> None:
        return None

    def unsubscribe(self, topic: str, _cb: object) -> int:
        if topic == self.bad_topic:
            raise Boom("unsubscribe(" + topic + ") refused")
        return 1


class WorkingBus:
    """A bus that behaves. Drives the clean-run control."""

    def __init__(self) -> None:
        self.topics: list[str] = []

    def subscribe(self, topic: str, _cb: object) -> None:
        self.topics.append(topic)

    def unsubscribe(self, _topic: str, _cb: object) -> int:
        return 1


class DeadLogger:
    """A system logger whose every call raises.

    The condition the three nested guards existed for: the reporting
    channel is itself the casualty.
    """

    def __init__(self) -> None:
        self.calls = 0

    def warning(self, *_a: object, **_k: object) -> None:
        self.calls += 1
        raise Boom("system logger is dead")

    def info(self, *_a: object, **_k: object) -> None:
        raise Boom("system logger is dead")


class Evt:
    """Bus-event stand-in. The handlers read ``.data`` and nothing else."""

    def __init__(self, data: dict) -> None:
        self.data = data


TEARDOWN_TOPICS = [
    "trade.filled",
    "pnl.event",
    "bot.gate_decision",
    "bot.voting_panel_snapshot",
    "bot.log",
]

HANDLERS = [
    (
        "_on_gate_decision_bus",
        {"bot_id": "b1", "symbol": "BTC-USD", "scrum_armed": True},
    ),
    (
        "_on_voting_panel_snapshot_bus",
        {"bot_id": "b1", "symbol": "BTC-USD", "panel": {"v": 1}},
    ),
    (
        "_on_trade_filled_bus",
        {
            "bot_id": "b1",
            "symbol": "BTC-USD",
            "side": "BUY",
            "amount": 1.0,
            "price": 2.0,
        },
    ),
]


def _break_writers(mgr: LogManager) -> None:
    def explode(*_a: object, **_k: object) -> None:
        raise Boom("writer failed")

    for attr in ("_gate_writer", "_voting_writer", "_trade_writer"):
        setattr(getattr(mgr, attr), "write", explode)


# --------------------------------------------------------------------
# Sites 1-5 -- the five bus teardowns
# --------------------------------------------------------------------
@pytest.mark.parametrize("topic", TEARDOWN_TOPICS)
def test_refused_unsubscribe_is_recorded_and_does_not_raise(tmp_path, topic):
    """A bus that refuses to detach one topic is counted, not swallowed.

    A refused unsubscribe is not cosmetic: the previous handler stays on
    the bus and every subsequent trade is written to trade.log twice. If
    this counter stays empty that double-write is invisible, which is
    the state the file shipped in.
    """
    mgr = LogManager(log_dir=tmp_path)
    bus = RefusingBus(topic)
    mgr.attach_to_bus(bus)
    mgr.attach_to_bus(bus)

    counts = mgr.internal_failure_counts()
    assert counts.get("attach_to_bus/unsubscribe " + topic) == 1
    assert list(counts) == ["attach_to_bus/unsubscribe " + topic]


def test_refused_unsubscribe_reaches_the_system_logger(tmp_path):
    """The five teardown faults reach the operator-facing log too.

    The counter is a programmatic surface. If nothing lands on the
    ``acervator`` logger the fault is reachable only from a test, and the
    human reading system.log still sees nothing.
    """
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("acervator")
    probe = Capture()
    logger.addHandler(probe)
    try:
        mgr = LogManager(log_dir=tmp_path)

        class AllRefusing:
            def subscribe(self, topic: str, _cb: object) -> None:
                return None

            def unsubscribe(self, topic: str, _cb: object) -> int:
                raise Boom("unsubscribe(" + topic + ") refused")

        bus = AllRefusing()
        mgr.attach_to_bus(bus)
        mgr.attach_to_bus(bus)
    finally:
        logger.removeHandler(probe)

    logged = [
        r.getMessage()
        for r in records
        if "internal failure at attach_to_bus/unsubscribe" in r.getMessage()
    ]
    assert len(logged) == len(TEARDOWN_TOPICS)
    for topic in TEARDOWN_TOPICS:
        assert any(topic in m for m in logged), topic


# --------------------------------------------------------------------
# Sites 6-8 -- the three handler recovery blocks
# --------------------------------------------------------------------
@pytest.mark.parametrize(("method", "payload"), HANDLERS)
def test_handler_survives_writer_and_logger_both_failing(
    tmp_path, capsys, method, payload
):
    """Writer dead AND system logger dead: still no raise, still recorded.

    This is the branch the removed nested ``except Exception: pass``
    occupied. Reporting a logger fault through that same logger is the
    recursion it was guarding against, so the fallback has to leave the
    logger entirely.

    If this raises, a dead log writer has propagated into the event bus.
    If the counter is empty, the engine is silently swallowing again.
    """
    mgr = LogManager(log_dir=tmp_path)
    _break_writers(mgr)
    dead = DeadLogger()
    mgr._sys_logger = dead

    getattr(mgr, method)(Evt(payload))  # must not raise

    counts = mgr.internal_failure_counts()
    assert counts.get(method) == 1
    assert counts.get("_sys_logger") == 1
    assert dead.calls == 1

    # The stderr line carries a bracketed "[LogManager]" prefix, not the
    # system logger's phrasing. Asserted against the observed artefact --
    # the first draft of this test guessed the logger's wording and went
    # red on all three handlers.
    err = capsys.readouterr().err
    assert "[LogManager] internal failure at " + method in err
    assert "system logger also failed" in err


@pytest.mark.parametrize(("method", "payload"), HANDLERS)
def test_handler_with_live_logger_does_not_touch_stderr(
    tmp_path, capsys, method, payload
):
    """Writer dead but logger alive: the normal channel carries it.

    stderr is the emergency channel only. If it fills up here, every
    ordinary logging hiccup is spraying the console, and the signal that
    the logger itself died is lost in the noise.
    """
    mgr = LogManager(log_dir=tmp_path)
    _break_writers(mgr)

    getattr(mgr, method)(Evt(payload))  # must not raise

    counts = mgr.internal_failure_counts()
    assert counts.get(method) == 1
    assert "_sys_logger" not in counts
    assert "[LogManager]" not in capsys.readouterr().err


# --------------------------------------------------------------------
# The instrument's own controls
# --------------------------------------------------------------------
def test_clean_run_records_nothing(tmp_path):
    """A healthy attach + handler pass leaves the counters empty.

    This is the positive control for every other assertion here. A
    counter that fills on a clean run reports "fault" always, and a
    always-on instrument measures nothing.
    """
    mgr = LogManager(log_dir=tmp_path)
    bus = WorkingBus()
    mgr.attach_to_bus(bus)
    mgr.attach_to_bus(bus)
    mgr._on_trade_filled_bus(
        Evt(
            {
                "bot_id": "b1",
                "symbol": "BTC-USD",
                "side": "BUY",
                "amount": 1.0,
                "price": 2.0,
            }
        )
    )

    assert mgr.internal_failure_counts() == {}
    assert "trade.filled" in bus.topics


def test_internal_failure_counts_returns_a_copy(tmp_path):
    """Mutating the returned dict must not corrupt the engine's state.

    If this leaks the live dict, a caller inspecting the counters can
    silently erase the record of a fault.
    """
    mgr = LogManager(log_dir=tmp_path)
    mgr.attach_to_bus(RefusingBus("trade.filled"))
    mgr.attach_to_bus(RefusingBus("trade.filled"))

    snapshot = mgr.internal_failure_counts()
    snapshot.clear()
    snapshot["injected"] = 99

    assert mgr.internal_failure_counts() != {}
    assert "injected" not in mgr.internal_failure_counts()


def test_emergency_stderr_reports_false_when_stderr_is_absent(monkeypatch):
    """``sys.stderr`` is None under a windowed launch; say so, do not raise.

    The operator runs this platform frozen. If this raises, the last-resort
    channel becomes a new crash source on exactly the path that exists to
    stop crashes.
    """
    monkeypatch.setattr("src.core.logging_engine.sys.stderr", None)
    assert _emergency_stderr("anything") is False


def test_emergency_stderr_reports_false_when_the_write_fails(monkeypatch):
    """A stderr that raises is reported as a miss, never swallowed.

    The bool is what lets the caller count a dead emergency channel
    instead of losing the fault entirely.
    """

    class BadStream:
        def write(self, _text: str) -> int:
            raise OSError("stderr is gone")

    monkeypatch.setattr("src.core.logging_engine.sys.stderr", BadStream())
    assert _emergency_stderr("anything") is False


def test_emergency_stderr_reports_true_on_success(capsys):
    """The success side of the same switch.

    Without this the False cases above could both be passing for the
    wrong reason -- a function that always returns False.
    """
    assert _emergency_stderr("unit-r-probe") is True
    assert "unit-r-probe" in capsys.readouterr().err


def test_the_attach_line_names_the_pnl_file_log_pnl_actually_writes(tmp_path):
    """``attach_to_bus`` announces the bucket ``log_pnl`` writes into.

    The bucket is read back off disk, so renaming it fails this test.
    """
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("acervator")
    probe = Capture()
    logger.addHandler(probe)
    try:
        mgr = LogManager(log_dir=tmp_path)
        mgr.attach_to_bus(WorkingBus())
        mgr.log_pnl("coinbase", "b1", 1.0, 0.0, 1)
    finally:
        logger.removeHandler(probe)

    lines = [r.getMessage() for r in records if "attached to bus" in r.getMessage()]
    assert len(lines) == 1, f"expected one attach announcement, got {records!r}"
    line = lines[0]

    written = sorted((tmp_path / "pnl").rglob("*.ndjson"))
    assert written, "log_pnl wrote no file, so the announcement cannot be checked"
    bucket = written[0].parent.relative_to(tmp_path).as_posix()
    assert bucket in line, f"announcement {line!r} omits the bucket {bucket!r}"
    suffix = written[0].suffix
    assert suffix in line, f"announcement {line!r} omits {suffix!r}"


def test_the_attach_line_carries_no_version_string(tmp_path):
    """``attach_to_bus`` announces no version. A version goes stale on disk."""
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("acervator")
    probe = Capture()
    logger.addHandler(probe)
    try:
        LogManager(log_dir=tmp_path).attach_to_bus(WorkingBus())
    finally:
        logger.removeHandler(probe)

    lines = [r.getMessage() for r in records if "attached to bus" in r.getMessage()]
    assert len(lines) == 1, f"expected one attach announcement, got {records!r}"
    assert re.search(r"v\d+\.\d+\.\d+", lines[0]) is None, lines[0]
