"""One log record must reach the Console handler exactly once.

`_QtLogHandler` paints the Console pane. `logging.Logger.callHandlers`
fires a handler once per logger in the ancestry that holds it, so the
same handler object attached at two connected levels paints one record
twice. Counting repeated messages cannot see that defect: a retry that
logs the same text forty times is forty records. These tests count how
many times ONE record reaches the handler.
"""

from __future__ import annotations

import logging
import os
import sys
from collections import Counter
from typing import TYPE_CHECKING, Optional

import pytest

from src.core.logging_engine import LogManager

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

if TYPE_CHECKING:  # pragma: no cover
    from PySide6.QtWidgets import QApplication

TOUCHED = (
    "",
    "acervator",
    "acervator.gui",
    "acervator.scrumming",
    "acervator.exchange",
)


def reachable_handlers(
    logger: logging.Logger,
) -> list[tuple[str, logging.Handler]]:
    """Handlers one record on `logger` reaches, each with its holder.

    Mirrors `logging.Logger.callHandlers`: emit at every node, then stop
    at the first node whose `propagate` is False.
    """
    out: list[tuple[str, logging.Handler]] = []
    node: Optional[logging.Logger] = logger
    while node is not None:
        for handler in node.handlers:
            out.append((node.name, handler))
        node = node.parent if node.propagate else None
    return out


def repeated_deliveries(logger: logging.Logger) -> dict[int, list[str]]:
    """Handler ids one record on `logger` reaches more than once."""
    reached = reachable_handlers(logger)
    counts = Counter(id(handler) for _, handler in reached)
    return {
        handler_id: [name for name, h in reached if id(h) == handler_id]
        for handler_id, count in counts.items()
        if count > 1
    }


def every_logger() -> list[logging.Logger]:
    """Root plus every logger the manager has materialised."""
    out = [logging.getLogger()]
    for name, obj in list(logging.Logger.manager.loggerDict.items()):
        if isinstance(obj, logging.Logger):
            out.append(logging.getLogger(name))
    return out


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    """The QApplication the widget tests run against."""
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication as _QApplication

    running = _QApplication.instance()
    if isinstance(running, _QApplication):
        return running
    return _QApplication(sys.argv)


@pytest.fixture
def booted(qapp, tmp_path):
    """The production boot order: root config, LogManager, Console tab.

    Yields `(host, system_log_path)`. Logger state for every node this
    touches is restored afterwards, so the module leaves no handler
    behind for the rest of the suite.
    """
    from PySide6.QtWidgets import QTabWidget, QWidget

    from src.gui.main_tabs.console_tab import ConsoleTabMixin

    saved = {
        name: (
            list(logging.getLogger(name).handlers),
            logging.getLogger(name).propagate,
            logging.getLogger(name).level,
        )
        for name in TOUCHED
    }
    for name in TOUCHED:
        logging.getLogger(name).handlers.clear()

    logging.getLogger().setLevel(logging.INFO)
    manager = LogManager(tmp_path)

    class _Host(QWidget, ConsoleTabMixin):
        def __init__(self, tabs) -> None:
            QWidget.__init__(self)
            self.setAccessibleName("Console tab test host")
            self._main_tabs = tabs

        def _drain_signals(self) -> None:
            return None

        def _emit_console_health(self) -> None:
            return None

        def _refresh_console_pause_indicator(self) -> None:
            return None

        def _toggle_console_pause(self) -> None:
            return None

    tabs = QTabWidget()
    host = _Host(tabs)
    host._build_console_tab()
    try:
        yield host, tmp_path / "system.log"
    finally:
        host._signal_timer.stop()
        host._console_health_timer.stop()
        host._console_pause_refresh.stop()
        host.deleteLater()
        tabs.deleteLater()
        qapp.processEvents()
        for handler in list(logging.getLogger("acervator").handlers):
            handler.close()
        del manager
        for name, (handlers, propagate, level) in saved.items():
            node = logging.getLogger(name)
            node.handlers[:] = handlers
            node.propagate = propagate
            node.setLevel(level)


@pytest.fixture
def console_handler(booted):
    """The `_QtLogHandler` the booted Console tab attached."""
    host, _ = booted
    return host._console_log_handler


@pytest.fixture
def control_chain():
    """A parent/child pair outside the acervator tree, plus one handler.

    Owned end to end so the controls state their own propagation. Nodes
    under `acervator` inherit `propagate = False` from the logging
    engine, which would silently disconnect the chain a control is
    asserting about.
    """
    parent = logging.getLogger("attach_control_151")
    child = logging.getLogger("attach_control_151.leaf")
    handler = logging.NullHandler()
    parent.propagate = True
    child.propagate = True
    try:
        yield parent, child, handler
    finally:
        parent.removeHandler(handler)
        child.removeHandler(handler)
        handler.close()


def paint(qapp, pane, name: str, message: str, times: int = 1) -> int:
    """Log `message` on `name` `times` over, return its pane line count."""
    pane.clear()
    for _ in range(times):
        logging.getLogger(name).warning(message)
    qapp.processEvents()
    return pane.toPlainText().count(message)


@pytest.mark.parametrize(
    "name",
    [
        "acervator.exchange",
        "acervator.gui.attach_probe",
        "acervator.scrumming.attach_probe",
        "acervator.core.retry",
    ],
)
def test_one_record_paints_one_console_line(booted, qapp, name):
    """A single record must produce a single pane line.

    A failure means the pane's handler is attached at two connected
    levels of this logger's ancestry, so the operator reads one event
    as two.
    """
    host, _ = booted
    assert paint(qapp, host._console, name, f"attached-once {name}") == 1


def test_a_message_logged_three_times_paints_three_lines(booted, qapp):
    """Recurrence is not duplication.

    The retry loop logs the same text once per attempt. Three calls are
    three records and must paint three lines; a check that collapsed
    them would report a working handler as broken.
    """
    host, _ = booted
    painted = paint(
        qapp,
        host._console,
        "acervator.exchange",
        "RateLimitExceeded on get_my_trades (attempt 1/3)",
        times=3,
    )
    assert painted == 3


def test_one_record_writes_one_system_log_line(booted):
    """The file path delivers once for the exchange retry logger."""
    _host, system_log = booted
    before = (
        len(system_log.read_text(encoding="utf-8").splitlines())
        if system_log.exists()
        else 0
    )
    logging.getLogger("acervator.exchange").warning("attached-once file probe")
    for handler in logging.getLogger("acervator").handlers:
        handler.flush()
    after = len(system_log.read_text(encoding="utf-8").splitlines())
    assert after - before == 1


def test_no_logger_reaches_the_console_handler_twice(booted, console_handler):
    """No materialised logger delivers one record to the pane twice.

    Scoped to the handler the Console tab just built, so an unrelated
    module's leaked handler cannot colour this verdict. A failure names
    the logger and the two holders, which is the whole diagnosis.
    """
    offenders = {
        logger.name: [
            holder
            for holder, handler in reachable_handlers(logger)
            if handler is console_handler
        ]
        for logger in every_logger()
    }
    assert {name: h for name, h in offenders.items() if len(h) > 1} == {}


def test_no_logger_reaches_the_system_log_handler_twice(booted):
    """No materialised logger writes one record to `system.log` twice."""
    file_handlers = [
        handler
        for handler in logging.getLogger("acervator").handlers
        if isinstance(handler, logging.FileHandler)
    ]
    assert len(file_handlers) == 1
    target = file_handlers[0]
    offenders = {
        logger.name: [
            holder
            for holder, handler in reachable_handlers(logger)
            if handler is target
        ]
        for logger in every_logger()
    }
    assert {name: h for name, h in offenders.items() if len(h) > 1} == {}


def test_the_delivery_count_sees_a_handler_on_two_connected_levels(control_chain):
    """Positive control for `repeated_deliveries`.

    The check reports a double-attach only if it can see one. Planted
    here because this function is an instrument, not code under
    development: one handler object on a parent and its child, both
    propagating, is the exact shape the two tests above must catch.
    """
    parent, child, handler = control_chain
    parent.addHandler(handler)
    assert repeated_deliveries(child) == {}
    child.addHandler(handler)
    assert repeated_deliveries(child) == {id(handler): [child.name, parent.name]}


def test_the_delivery_count_ignores_a_propagation_break(control_chain):
    """A handler below a `propagate = False` node is not double-reached.

    `logging_engine` sets `acervator.propagate = False`, so the Console
    handler on `acervator` and the one on root serve disjoint sets. A
    check that flagged that pair would refuse the correct arrangement.
    """
    parent, child, handler = control_chain
    parent.addHandler(handler)
    child.addHandler(handler)
    assert repeated_deliveries(child) == {id(handler): [child.name, parent.name]}
    child.propagate = False
    assert repeated_deliveries(child) == {}
