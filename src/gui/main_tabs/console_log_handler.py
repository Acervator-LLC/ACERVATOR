"""Logging handler and Qt relay that paint the Console pane."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QColor, QTextCharFormat

from .. import design_system as ds

__all__ = ["_QtLogHandler", "_QtLogRelay"]


# MEM-221 (Session 24, 2026-04-22) — thread-safe log handler.
#
# Previous implementation called cursor.insertText(),
# self._te.document(), sb.setValue() directly from emit().
# emit() runs on whatever thread called logger.xxx() — which
# includes ThreadPoolExecutor workers created by asyncio.to_thread.
# CCXT, urllib3, and other libraries log at DEBUG/INFO from
# inside those worker threads. Touching a QPlainTextEdit from
# a non-GUI thread is undefined behavior in Qt; on Windows it
# reliably produces an access violation.
#
# MEM-217's faulthandler captured this at 2026-04-22 00:24:01,
# thread asyncio_0: src\gui\main_window.py:1635 in emit
# (inside cursor.insertText) called from inside CCXT's fetch()
# which called logger.debug().
#
# Fix: emit() emits a Qt Signal carrying the formatted text.
# The signal is connected (Qt.AutoConnection default) to a
# @Slot on the main thread; when emitted from a worker
# thread, Qt queues the slot invocation via the main event
# loop, so the actual widget update runs on the main thread.
#
# THE SIGNAL LIVES ON A RELAY, NOT ON THE HANDLER.
#
# The handler used to inherit QObject AND logging.Handler,
# which is a name collision on `emit`, and a real one:
# QObject.emit(signal, *args) -> bool is the old-style
# signal dispatcher, while logging.Handler.emit(record) ->
# None is what the logging framework calls. One method
# cannot be both, and the handler's emit has always
# shadowed QObject's at runtime. No signature satisfies
# both contracts — a widened one then breaks the logging
# side, which is the side that is actually called.
#
# So the handler is a plain logging.Handler and the QObject
# is this relay, which owns the signal and the slot.
# Threading is unchanged: the relay is built on the main
# thread inside the handler's constructor, the connection
# is still AutoConnection, and a log call from a worker
# thread is still queued onto the main thread before
# anything touches the widget. Only the object holding the
# signal moved.
class _QtLogRelay(QObject):
    # Signal carries (formatted_msg, r, g, b) so we don't
    # cross thread boundaries with a QColor instance (the
    # QColor is created lazily on the receiving thread).
    append = Signal(str, int, int, int)

    def __init__(
        self,
        paint: Callable[[str, int, int, int], None],
    ) -> None:
        QObject.__init__(self)
        # The painter is taken as a callable rather than the
        # handler itself: the relay has no other business
        # with the handler, and asking for exactly what it
        # calls keeps it from reaching into anything else.
        self._paint = paint
        # AutoConnection: same-thread → DirectConnection,
        # cross-thread → QueuedConnection (runs on receiver's
        # thread). The receiver (self) is constructed on the
        # main thread, so the slot always runs there.
        # Qt.ConnectionType.AutoConnection is the same
        # object as the bare Qt.AutoConnection used before
        # (verified: `is` holds); the scoped spelling is
        # the one the type stubs declare.
        self.append.connect(self._deliver, Qt.ConnectionType.AutoConnection)

    @Slot(str, int, int, int)
    def _deliver(
        self,
        msg: str,
        r: int,
        g: int,
        b: int,
    ) -> None:
        """Paint one console line on the main thread.

        Qt invokes this slot; the painter it calls is a
        plain method now that the handler is not a QObject.
        """
        self._paint(msg, r, g, b)


class _QtLogHandler(logging.Handler):
    COLORS = {
        "DEBUG": QColor(ds.TEXT_MUTED),
        "INFO": QColor(ds.TEXT_INACTIVE),
        "WARNING": QColor(ds.WARNING),
        "ERROR": QColor(ds.ERROR),
        "CRITICAL": QColor(ds.MAIN_LOG_CRITICAL),
    }
    HIGHLIGHT = QColor(ds.PRIMARY)  # indicator panel events

    def __init__(self, text_edit):
        logging.Handler.__init__(self)
        self._te = text_edit
        # v3.16.7 — pause support. When True, emit() buffers
        # messages instead of dispatching to the widget. On
        # resume, the buffer drains as a single batch.
        self._paused = False
        self._buffer: list[tuple[str, int, int, int]] = []
        self._buffer_max = 5000  # cap to keep memory bounded
        self._buffer_dropped = 0  # count of msgs dropped at cap
        # The relay is held by name as well as by signal:
        # dropping the QObject would take the connection
        # with it the next time Python collected it.
        self._relay = _QtLogRelay(self._append_to_widget)
        self._append_signal = self._relay.append

    def emit(self, record):
        """Runs on WHATEVER thread called logger.xxx().
        MUST NOT touch the widget directly — worker threads
        calling CCXT/urllib3/etc. reach here from non-GUI
        threads. Emit a signal and return; Qt queues the
        actual widget update to the main thread.

        v3.16.7 — when paused, buffer messages instead of
        emitting. Resume drains the buffer as a single batch
        so the operator's reading position is preserved.

        v3.18.10 — MEM-221 fix. The pause-buffer mutation
        (self._buffer.append + self._buffer_dropped += 1)
        used to happen INSIDE emit(), which is a cross-
        thread write. Now: emit() always signals; the
        main-thread slot (_append_to_widget) reads
        self._paused and decides whether to buffer or
        paint. All buffer state mutation now happens on
        the main thread. CPython's GIL was masking the
        race in practice but the audit
        (test_mem221_thread_safe_log_handler) correctly
        insisted the architecture be clean.
        """
        try:
            msg = self.format(record)
            color = (
                self.HIGHLIGHT
                if "INDICATOR PANEL" in msg
                else self.COLORS.get(record.levelname, self.COLORS["INFO"])
            )
            # ALWAYS signal — the slot decides buffer vs paint
            # based on the (main-thread-owned) pause state.
            self._append_signal.emit(msg, color.red(), color.green(), color.blue())
        except Exception:  # noqa: S110
            # Never raise from a log handler — would
            # propagate up through every logger.xxx() call
            # and destabilise the app.
            pass

    def set_paused(self, paused: bool) -> None:
        """v3.16.7 — toggle pause. On resume, drain the
        buffer (flushing each entry through the queued
        signal so it's still thread-safe)."""
        self._paused = bool(paused)
        if not self._paused and self._buffer:
            # Drain the buffer — emit each as a queued signal
            # so the actual widget update happens on the main
            # thread (same path as live emit).
            for msg, r, g, b in self._buffer:
                self._append_signal.emit(msg, r, g, b)
            self._buffer.clear()
            if self._buffer_dropped > 0:
                self._append_signal.emit(
                    f"[CONSOLE PAUSE] {self._buffer_dropped} "
                    f"messages dropped (buffer cap={self._buffer_max})",
                    255,
                    170,
                    0,
                )
                self._buffer_dropped = 0

    def buffered_count(self) -> int:
        return len(self._buffer)

    def _append_to_widget(self, msg, r, g, b):
        """Runs on the MAIN thread (Qt queues cross-thread
        signals via the event loop). Safe to touch the
        QPlainTextEdit + the pause buffer here.

        No longer decorated @Slot: a slot is a QObject
        concept and this class is not one any more. The
        decorator now sits on _QtLogRelay._deliver, which
        is the QObject method Qt actually invokes, and
        which calls straight into here. The thread this
        body runs on is unchanged.

        v3.18.10 — MEM-221 hardening. Both pause-buffer
        mutation and widget painting now happen exclusively
        on the main thread (this slot), serialized by the
        Qt event loop. emit() used to mutate the buffer
        directly from worker threads.
        """
        try:
            # v3.18.10 — pause path: buffer here on the
            # main thread instead of inside emit() (which
            # ran on any thread).
            if self._paused:
                if len(self._buffer) >= self._buffer_max:
                    self._buffer_dropped += 1
                    return
                self._buffer.append((msg, r, g, b))
                return
            color = QColor(r, g, b)
            # Fast path: QPlainTextEdit + QTextCursor +
            # QTextCharFormat. No HTML parsing.
            cursor = self._te.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            if self._te.document().isEmpty():
                cursor.insertText(msg, fmt)
            else:
                cursor.insertText("\n" + msg, fmt)
            # Auto-scroll only if user is already at bottom.
            sb = self._te.verticalScrollBar()
            if sb.value() >= sb.maximum() - 20:
                sb.setValue(sb.maximum())
        except Exception:  # noqa: S110
            pass
