"""``StatusLog`` renders timestamped, colour-coded lines into a read-only pane."""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from typing import Callable

from ..main_tabs import status_log_surface as surface

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtGui import QFontMetrics, QTextBlockFormat, QTextCursor
    from PySide6.QtWidgets import QTextEdit

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class StatusLog(QTextEdit):
        """``StatusLog`` shows timestamped, colour-coded lines, read-only.

        ``pause`` diverts each ``log`` call into ``_pause_buffer`` up to
        ``_pause_buffer_cap`` entries, and ``resume`` replays them through
        ``_render`` with their original timestamps.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Status Log")
            self.setReadOnly(True)
            self.setMaximumHeight(150)
            self.setPlaceholderText("Activity log...")
            self._paused: bool = False
            self._pause_buffer: list[tuple] = []
            self._pause_buffer_cap: int = 2000
            self._relay: Callable[[str, str, str, str | None], None] | None = None

            # setMaximumBlockCount drops the oldest line once 5000 are held.
            try:
                self.document().setMaximumBlockCount(5000)
            except Exception:
                logger.warning(
                    "StatusLog: block cap not set; the pane grows unbounded",
                    exc_info=True,
                )
            import time as _t

            self._last_render_time: float = _t.time()
            self._total_renders: int = 0
            self._render_errors: int = 0
            self._last_render_error: str = ""
            self._last_render_error_time: float = 0.0

        def set_relay(self, relay) -> None:
            """Take the callable every ``log``, ``pause``, ``resume`` and
            ``notice`` call is reported to."""
            self._relay = relay

        def _tell(
            self,
            action: str,
            message: str = "",
            level: str = "",
            kind: str | None = None,
            lights: list | None = None,
        ) -> None:
            """Report one call to ``_relay`` without stopping ``_render``."""
            if self._relay is None:
                return
            try:
                self._relay(action, message, level, kind, lights)
            except Exception:
                logger.debug("StatusLog relay raised on %s", action, exc_info=True)

        def notice(self, text: str) -> None:
            """Append ``text`` with no timestamp, which is what ``_NotifyStub``
            relays."""
            self.append(text)
            self._tell("notice", text)

        def is_paused(self) -> bool:
            return self._paused

        def pause(self) -> None:
            self._paused = True
            self._tell("pause")

        def resume(self) -> None:
            """Clear ``_pause_buffer`` and replay every held entry through
            ``_render``."""
            self._paused = False
            self._tell("resume")
            buffered = list(self._pause_buffer)
            self._pause_buffer.clear()
            for ts, message, level, kind, lights in buffered:
                self._render(ts, message, level, kind, lights)
            if buffered:
                self.append(surface.resume_line(len(buffered))["html"])
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

        def toggle_pause(self) -> bool:
            """Call ``pause`` or ``resume``, and return the new ``_paused``."""
            if self._paused:
                self.resume()
            else:
                self.pause()
            return self._paused

        def log(
            self,
            message: str,
            level: str = "info",
            kind: str | None = None,
            lights: list | None = None,
        ) -> None:
            ts = datetime.now().strftime("%H:%M:%S")
            self._tell("log", message, level, kind, lights)
            if self._paused:
                # A full ``_pause_buffer`` drops the newest entry, not the oldest.
                if len(self._pause_buffer) < self._pause_buffer_cap:
                    self._pause_buffer.append((ts, message, level, kind, lights))
                return
            self._render(ts, message, level, kind, lights)

        def force_log(
            self,
            message: str,
            level: str = "warning",
            kind: str | None = None,
            lights: list | None = None,
        ) -> None:
            """Render *message* now, whatever ``_paused`` holds."""
            ts = datetime.now().strftime("%H:%M:%S")
            self._tell("force_log", message, level, kind, lights)
            self._render(ts, message, level, kind, lights)

        def health_stats(self) -> dict:
            """Return ``_paused``, the ``_pause_buffer`` size, the age and count
            of renders, ``_render_errors``, ``_last_render_error`` and the
            QTextDocument block count."""
            import time as _t

            try:
                blocks = self.document().blockCount()
            except Exception:
                blocks = -1
            return {
                "paused": self._paused,
                "pause_buffer_size": len(self._pause_buffer),
                "last_render_age_sec": round(_t.time() - self._last_render_time, 1),
                "total_renders": self._total_renders,
                "render_errors": self._render_errors,
                "last_render_error": self._last_render_error,
                "document_blocks": blocks,
            }

        def _render(
            self,
            ts: str,
            message: str,
            level: str = "info",
            kind: str | None = None,
            lights: list | None = None,
        ) -> None:
            try:
                self._render_safe(ts, message, level, kind, lights)
                import time as _t

                self._last_render_time = _t.time()
                self._total_renders += 1
            except Exception as exc:
                import time as _t

                self._render_errors += 1
                self._last_render_error = f"{type(exc).__name__}: {exc}"
                self._last_render_error_time = _t.time()
                with contextlib.suppress(Exception):
                    logger.error(
                        "StatusLog._render exception (#%d): %s | "
                        "message=%r level=%r",
                        self._render_errors,
                        self._last_render_error,
                        message[:200],
                        level,
                    )

        def _render_safe(
            self,
            ts: str,
            message: str,
            level: str = "info",
            kind: str | None = None,
            lights: list | None = None,
        ) -> None:
            style = surface.line_style(message, level, kind, lights)
            self.append(surface.line_html(ts, style))
            self._hang_message_column(surface.stamp_text(ts))
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
            self._report_trade_shape(message, style)
            self._report_named_kind(message, kind, style)

        def _hang_message_column(self, stamp_text: str) -> None:
            """Indent the block just appended so the stamp keeps its own column.

            The width comes from this widget's own font, so a wrapped message
            starts where the message starts and never under ``stamp_text``.
            """
            width = 0.0
            if stamp_text:
                advance = QFontMetrics(self.font()).horizontalAdvance(stamp_text + " ")
                width = float(advance)
            shape = QTextBlockFormat()
            shape.setLeftMargin(width)
            shape.setTextIndent(-width)
            spot = self.textCursor()
            spot.movePosition(QTextCursor.MoveOperation.End)
            spot.setBlockFormat(shape)

        def _report_named_kind(
            self, message: str, kind: str | None, style: dict
        ) -> None:
            """Report the kind a writer named against the kind its own words ask
            for, naming the writer through ``writer_mark``."""
            asked = surface.asked_kind(message)
            if asked == surface.NO_KIND:
                return
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _log_emit

                _log_emit(
                    "trading.12.008.postcondition.line_kind_named_by_writer",
                    actual=kind or surface.NO_KIND,
                    expected=asked,
                    context={
                        "writer": surface.writer_mark(message),
                        "drawn_kind": style["kind"],
                        "font_size_px": style["font_size_px"],
                        "bold": style["bold"],
                    },
                )

        def _report_trade_shape(self, message: str, style: dict) -> None:
            """Report the drawn kind of a message holding ``TRADE_PREFIX``, against
            ``KIND_TRADE``."""
            if surface.TRADE_PREFIX not in message:
                return
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _log_emit

                _log_emit(
                    "trading.12.007.postcondition.trade_line_drawn_as_trade",
                    actual=style["kind"],
                    expected=surface.KIND_TRADE,
                    context={
                        "tag": style["tag"],
                        "font_size_px": style["font_size_px"],
                        "bold": style["bold"],
                        "color": style["color"],
                    },
                )
