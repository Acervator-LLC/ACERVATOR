"""``SimStatusLog`` renders timestamped, colour-coded lines into a read-only pane.

A fork of ``src/gui/widgets/status_log.py`` ``StatusLog`` under the Simulator's
name; the Simulator's Activity Log spool. ``SimStatusLogModel`` is the fork of
``StatusLogModel`` the React host holds. Both add ``log_at``, a ``log`` whose
stamp the caller gives, which a simulated trade's line needs for its candle time.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import datetime
from typing import Any, Callable

from ..main_tabs import status_log_surface as surface
from ..main_tabs.status_log_surface import DEFAULT_LOG_LEVEL, StatusLogModel

logger = logging.getLogger("acervator.gui")


class SimStatusLogModel(StatusLogModel):
    """``StatusLogModel`` with ``log_at``: ``log`` under a stamp the caller gives."""

    def log_at(self, stamp: str, message: str, level: Any = DEFAULT_LOG_LEVEL) -> None:
        """Paint ``message`` under ``stamp``, or hold it under a pause as ``log`` does."""
        if self.paused:
            if len(self.pause_buffer) < self.pause_buffer_cap:
                self.pause_buffer.append((stamp, message, level))
            return
        self.render(stamp, message, level)


try:
    from PySide6.QtWidgets import QTextEdit

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class SimStatusLog(QTextEdit):
        """``SimStatusLog`` shows timestamped, colour-coded lines, read-only.

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
            self._pause_buffer: list[tuple[str, str, str]] = []
            self._pause_buffer_cap: int = 2000
            self._relay: Callable[[str, str, str], None] | None = None

            # setMaximumBlockCount drops the oldest line once 5000 are held.
            try:
                self.document().setMaximumBlockCount(5000)
            except Exception:
                logger.warning(
                    "SimStatusLog: block cap not set; the pane grows unbounded",
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

        def _tell(self, action: str, message: str = "", level: str = "") -> None:
            """Report one call to ``_relay`` without stopping ``_render``."""
            if self._relay is None:
                return
            try:
                self._relay(action, message, level)
            except Exception:
                logger.debug("SimStatusLog relay raised on %s", action, exc_info=True)

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
            for ts, message, level in buffered:
                self._render(ts, message, level)
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

        def log(self, message: str, level: str = "info") -> None:
            ts = datetime.now().strftime("%H:%M:%S")
            self._tell("log", message, level)
            if self._paused:
                # A full ``_pause_buffer`` drops the newest entry, not the oldest.
                if len(self._pause_buffer) < self._pause_buffer_cap:
                    self._pause_buffer.append((ts, message, level))
                return
            self._render(ts, message, level)

        def log_at(self, stamp: str, message: str, level: str = "info") -> None:
            """``log`` under ``stamp`` instead of the clock: held under a pause, else rendered."""
            self._tell("log", message, level)
            if self._paused:
                if len(self._pause_buffer) < self._pause_buffer_cap:
                    self._pause_buffer.append((stamp, message, level))
                return
            self._render(stamp, message, level)

        def force_log(self, message: str, level: str = "warning") -> None:
            """Render *message* now, whatever ``_paused`` holds."""
            ts = datetime.now().strftime("%H:%M:%S")
            self._tell("force_log", message, level)
            self._render(ts, message, level)

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

        def _render(self, ts: str, message: str, level: str = "info") -> None:
            try:
                self._render_safe(ts, message, level)
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
                        "SimStatusLog._render exception (#%d): %s | "
                        "message=%r level=%r",
                        self._render_errors,
                        self._last_render_error,
                        message[:200],
                        level,
                    )

        def _render_safe(self, ts: str, message: str, level: str = "info") -> None:
            self.append(surface.line_html(ts, surface.line_style(message, level)))
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
