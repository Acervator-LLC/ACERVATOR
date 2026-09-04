"""``StatusLog.__init__`` reports a block cap the document would not accept.

A ``StatusLog`` that loses ``setMaximumBlockCount`` keeps every line it is given,
and the refusal reaches ``logger`` at warning level.
"""

from __future__ import annotations

import logging
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

CAP_MARK = "block cap not set"
BLOCKS = 5000


def _pane_class():
    """The real ``StatusLog``, imported after the platform is chosen."""
    from qt_pixel import ensure_app

    from src.gui.widgets.status_log import StatusLog

    ensure_app()
    return StatusLog


def _refusing_pane_class():
    """A ``StatusLog`` subclass whose ``document`` raises."""
    parent = _pane_class()

    class _NoDocument(parent):
        def document(self):
            raise RuntimeError("this backend has no document")

    return _NoDocument


def test_a_block_cap_the_document_refuses_reaches_the_logger(capture_log):
    """A refused ``setMaximumBlockCount`` writes one warning naming the cap."""
    refusing = _refusing_pane_class()
    with capture_log("acervator.gui", logging.WARNING) as records:
        refusing()
    messages = [record.getMessage() for record in records]
    assert [m for m in messages if CAP_MARK in m], messages


def test_a_document_that_accepts_the_cap_writes_no_warning(capture_log):
    """The control for the refusal: an ordinary ``StatusLog`` logs nothing."""
    pane = _pane_class()
    with capture_log("acervator.gui", logging.WARNING) as records:
        pane()
    messages = [record.getMessage() for record in records]
    assert not [m for m in messages if CAP_MARK in m], messages


def test_the_document_holds_the_cap_the_pane_asked_for():
    """``StatusLog`` leaves its QTextDocument capped at ``BLOCKS`` blocks."""
    pane = _pane_class()
    assert pane().document().maximumBlockCount() == BLOCKS


def test_health_stats_marks_an_unreadable_block_count():
    """``health_stats`` answers ``document_blocks`` with -1 when the read raises."""
    refusing = _refusing_pane_class()
    assert refusing().health_stats()["document_blocks"] == -1


def test_health_stats_reports_the_real_block_count_when_it_reads():
    """The control for the mark: an ordinary ``StatusLog`` reports a real count."""
    pane = _pane_class()
    assert pane().health_stats()["document_blocks"] >= 0
