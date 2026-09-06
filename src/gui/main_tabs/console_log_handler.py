"""``_QtLogHandler`` formats each record the Console pane shows.

``_QtLogRelay`` carries the formatted line to the GUI thread and paints it there.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtGui import QColor, QTextCharFormat

from .. import design_system as ds

__all__ = ["_QtLogHandler", "_QtLogRelay"]


def _paint_failure(msg) -> logging.LogRecord:
    """Return the record ``_append_to_widget`` hands to ``handleError``."""
    return logging.LogRecord(__name__, logging.ERROR, __file__, 0, msg, None, None)


class _QtLogRelay(QObject):
    """``append`` carries a formatted line from any thread to ``_deliver``.

    ``_deliver`` runs on the thread that constructed the relay.
    """

    # Colour travels as three ints; QColor is built on the receiving thread.
    append = Signal(str, int, int, int)

    def __init__(
        self,
        paint: Callable[[str, int, int, int], None],
    ) -> None:
        QObject.__init__(self)
        self._paint = paint
        self.append.connect(self._deliver, Qt.ConnectionType.AutoConnection)

    @Slot(str, int, int, int)
    def _deliver(
        self,
        msg: str,
        r: int,
        g: int,
        b: int,
    ) -> None:
        """Call the painter given to ``__init__`` with ``msg`` and its colour."""
        self._paint(msg, r, g, b)


class _QtLogHandler(logging.Handler):
    """Format each record and hand it to ``_QtLogRelay`` to paint.

    ``set_paused`` holds lines in ``_buffer`` up to ``_buffer_max``, and
    ``buffered_count`` reports how many are held. A ``painter`` takes the
    line in place of ``_te``.
    """

    COLORS = {
        "DEBUG": QColor(ds.TEXT_MUTED),
        "INFO": QColor(ds.TEXT_INACTIVE),
        "WARNING": QColor(ds.WARNING),
        "ERROR": QColor(ds.ERROR),
        "CRITICAL": QColor(ds.MAIN_LOG_CRITICAL),
    }
    HIGHLIGHT = QColor(ds.PRIMARY)  # Painted for messages holding "INDICATOR PANEL".

    def __init__(self, text_edit, painter: Callable[[str, int, int, int], None] = None):
        """Paint into ``text_edit``, or into ``painter`` when one is given."""
        logging.Handler.__init__(self)
        self._te = text_edit
        self._painter = painter
        self._paused = False
        self._buffer: list[tuple[str, int, int, int]] = []
        self._buffer_max = 5000
        self._buffer_dropped = 0
        # Held by name: collecting the relay would drop the queued connection.
        self._relay = _QtLogRelay(self._append_to_widget)
        self._append_signal = self._relay.append

    def emit(self, record):
        """Format ``record`` and signal the line to ``_append_to_widget``.

        Runs on whatever thread called the logger and never touches ``self._te``.
        """
        try:
            msg = self.format(record)
            color = (
                self.HIGHLIGHT
                if "INDICATOR PANEL" in msg
                else self.COLORS.get(record.levelname, self.COLORS["INFO"])
            )
            self._append_signal.emit(msg, color.red(), color.green(), color.blue())
        except Exception:
            self.handleError(record)

    def set_paused(self, paused: bool) -> None:
        """Hold new lines in ``_buffer`` while ``paused``, and drain them on resume.

        A drain that followed a ``_buffer_max`` overflow appends one notice line.
        """
        self._paused = bool(paused)
        if not self._paused and self._buffer:
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
        """Return how many lines ``_buffer`` is holding."""
        return len(self._buffer)

    def _append_to_widget(self, msg, r, g, b):
        """Append ``msg`` to ``self._te`` in the colour ``(r, g, b)``.

        Runs on the GUI thread, and fills ``_buffer`` while ``_paused`` is set.
        """
        try:
            if self._paused:
                if len(self._buffer) >= self._buffer_max:
                    self._buffer_dropped += 1
                    return
                self._buffer.append((msg, r, g, b))
                return
            if self._painter is not None:
                self._painter(msg, r, g, b)
                return
            color = QColor(r, g, b)
            cursor = self._te.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            if self._te.document().isEmpty():
                cursor.insertText(msg, fmt)
            else:
                cursor.insertText("\n" + msg, fmt)
            # Follow the tail only while the scrollbar sits within 20 of its maximum.
            sb = self._te.verticalScrollBar()
            if sb.value() >= sb.maximum() - 20:
                sb.setValue(sb.maximum())
        except Exception:
            self.handleError(_paint_failure(msg))
