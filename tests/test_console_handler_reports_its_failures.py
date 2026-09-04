"""``_QtLogHandler`` must report a record it could not paint.

A failure means the Console pane silently drops a line: the formatter or the
pane raised, the handler swallowed it, and nothing reached ``handleError``.
"""

from __future__ import annotations

import logging

import pytest

from src.gui.main_tabs.console_log_handler import _QtLogHandler


class _Cursor:
    class MoveOperation:
        End = "End"

    def __init__(self, pane):
        self._pane = pane

    def movePosition(self, _where):
        return None

    def insertText(self, text, _fmt):
        if self._pane.raises:
            raise RuntimeError("the pane refused the insert")
        self._pane.inserts.append(text)


class _Document:
    def __init__(self, pane):
        self._pane = pane

    def isEmpty(self):
        return self._pane.inserts == []


class _ScrollBar:
    def value(self):
        return 0

    def maximum(self):
        return 0

    def setValue(self, _value):
        return None


class _Pane:
    """Stands in for the ``QPlainTextEdit`` the handler paints."""

    def __init__(self, raises: bool = False):
        self.raises = raises
        self.inserts: list = []

    def textCursor(self):
        return _Cursor(self)

    def document(self):
        return _Document(self)

    def verticalScrollBar(self):
        return _ScrollBar()


class _RaisingFormatter(logging.Formatter):
    def format(self, record):
        raise ValueError("the formatter refused the record")


def _record(text: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="acervator.console_failure",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=text,
        args=(),
        exc_info=None,
    )


@pytest.fixture
def reported(monkeypatch):
    """A handler on a working pane, with every ``handleError`` call collected."""

    def _build(pane: _Pane, formatter: logging.Formatter) -> tuple:
        handler = _QtLogHandler(pane)
        handler.setFormatter(formatter)
        seen: list = []
        monkeypatch.setattr(handler, "handleError", seen.append)
        return handler, seen

    return _build


def test_a_formatter_that_raises_reaches_handle_error(reported):
    pane = _Pane()
    handler, seen = reported(pane, _RaisingFormatter())
    record = _record("the line the formatter refused")
    handler.emit(record)
    assert seen == [record], f"emit reported {seen}, expected the refused record"
    assert pane.inserts == [], f"a refused record still painted {pane.inserts}"


def test_a_record_that_formats_paints_and_reports_nothing(reported):
    pane = _Pane()
    handler, seen = reported(pane, logging.Formatter("%(message)s"))
    handler.emit(_record("the line that painted"))
    assert pane.inserts == ["the line that painted"]
    assert seen == [], f"a painted record still reported {seen}"


def test_a_pane_that_refuses_the_insert_reaches_handle_error(reported):
    handler, seen = reported(_Pane(raises=True), logging.Formatter("%(message)s"))
    handler.emit(_record("the line that never painted"))
    assert len(seen) == 1, f"a refused insert reported {len(seen)} times, expected 1"
    assert seen[0].getMessage() == "the line that never painted"


def test_a_refused_insert_is_not_reported_while_paused(reported):
    """The pause path returns before the pane, so nothing can refuse it."""
    handler, seen = reported(_Pane(raises=True), logging.Formatter("%(message)s"))
    handler.set_paused(True)
    handler.emit(_record("held while paused"))
    assert handler.buffered_count() == 1
    assert seen == [], f"the pause path reported {seen}"
    handler.set_paused(False)
    assert len(seen) == 1, "the drain reached the refusing pane and said nothing"
