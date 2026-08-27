"""Activity Log pane: timestamped, colour-coded, read-only."""

from __future__ import annotations

import logging
from datetime import datetime

from .. import design_system as ds

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import QTextEdit

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    # ---------------------------------------------------------------
    # Status Log - persistent feedback panel
    # ---------------------------------------------------------------
    # DPA: Q-001 exception — fixed 150px height caps visible content;
    # HTML formatting useful for timestamp+color coding.
    class StatusLog(QTextEdit):
        """Read-only scrolling log with timestamped, color-coded messages.

        v3.15.67 — operator directive 2026-04-26:
          "Need a way to stop the damn console from spooling so I can
           properly capture errors."

        Pause/Resume support: when paused, incoming log() calls are
        buffered (capped at 2000 entries to avoid unbounded memory).
        On resume, the buffer flushes in chronological order with the
        ORIGINAL timestamps so historical context is preserved. The
        operator can read errors that arrived during the pause without
        losing them.
        """

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAccessibleName("Status Log")
            self.setReadOnly(True)
            self.setMaximumHeight(150)
            self.setPlaceholderText("Activity log...")
            # v3.15.67 — pause/resume state
            self._paused: bool = False
            self._pause_buffer: list[tuple[str, str, str]] = []
            self._pause_buffer_cap: int = 2000

            # v3.16.35 — Activity Log silent-failure visibility.
            # Operator-reported 2026-05-06: "Noticed two days in a row
            # now that the Activity Log has stopped spooling around 5
            # to 6 AM but am not seeing any explicit errors. We may
            # need to place a error catching loop that monitors data
            # throughput to this module in order to give the issue
            # visibility."
            #
            # Three silent-failure mitigations land here:
            #
            # 1. Document block-count cap. Qt's QTextEdit has a built-
            #    in maximumBlockCount on its underlying QTextDocument
            #    that drops the oldest line(s) once the cap is hit.
            #    Without this, a long-running session accumulates
            #    HTML blocks indefinitely; eventually render slows
            #    and the log appears to "stop spooling." 5,000 lines
            #    is plenty of recent context (about 4-8 hours of
            #    typical activity at production rates).
            try:  # noqa: SIM105
                self.document().setMaximumBlockCount(5000)
            except (
                Exception
            ):  # R28-OK: defensive — older Qt may not support  # noqa: S110
                pass
            # 2. Throughput tracking. Every successful render bumps
            #    _last_render_time + _total_renders. The watchdog
            #    QTimer in MainWindow polls these and surfaces a
            #    warning to stderr / file logger when there's been
            #    no activity for an extended window despite bots
            #    running. Operator gets visibility BEFORE the next
            #    morning's "log stopped at 5 AM" surprise.
            import time as _t

            self._last_render_time: float = _t.time()
            self._total_renders: int = 0
            self._render_errors: int = 0
            self._last_render_error: str = ""
            self._last_render_error_time: float = 0.0

        # v3.15.67 — pause/resume API
        def is_paused(self) -> bool:
            return self._paused

        def pause(self) -> None:
            self._paused = True

        def resume(self) -> None:
            """Flush the buffered messages in chronological order."""
            self._paused = False
            buffered = list(self._pause_buffer)
            self._pause_buffer.clear()
            for ts, message, level in buffered:
                self._render(ts, message, level)
            if buffered:
                # Mark resume point so operator knows what was buffered.
                self.append(
                    f'<span style="color:{ds.CARD_METRIC_LABEL}">[—]</span> '
                    f'<span style="color:{ds.PRIMARY};font-style:italic;">'
                    f"(resumed — {len(buffered)} buffered message(s) above)"
                    f"</span>"
                )
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

        def toggle_pause(self) -> bool:
            """Flip the paused flag; return new state."""
            if self._paused:
                self.resume()
            else:
                self.pause()
            return self._paused

        def log(self, message: str, level: str = "info") -> None:
            ts = datetime.now().strftime("%H:%M:%S")
            # v3.15.67 — when paused, buffer the message + level + ts
            # tuple so the original chronological order survives the
            # eventual flush. Cap the buffer to avoid unbounded growth.
            if self._paused:
                if len(self._pause_buffer) < self._pause_buffer_cap:
                    self._pause_buffer.append((ts, message, level))
                # else: silently drop oldest? No — silently drop newest
                # so the pause window doesn't lose what triggered the
                # operator's pause in the first place.
                return
            self._render(ts, message, level)

        def force_log(self, message: str, level: str = "warning") -> None:
            """v3.16.35 — bypass the paused flag for watchdog/health
            messages that MUST surface even if the operator paused
            the log. Used by the Activity-Log throughput watchdog."""
            ts = datetime.now().strftime("%H:%M:%S")
            self._render(ts, message, level)

        def health_stats(self) -> dict:
            """v3.16.35 — Watchdog accessor. Returns:
              - paused: bool
              - pause_buffer_size: int
              - last_render_age_sec: float
              - total_renders: int
              - render_errors: int
              - last_render_error: str (most recent exception message)
              - document_blocks: int (current QTextDocument block count)
            Operator-debuggable surface — the watchdog QTimer in
            MainWindow polls this every 60s; the operator can also
            call it interactively from the Console tab."""
            import time as _t

            try:
                blocks = self.document().blockCount()
            except Exception:  # R28-OK: doc accessor edge case
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
            # v3.16.35 — wrap the entire render path in try/except so
            # any Qt exception (cross-thread call, document overflow,
            # malformed HTML in `message`) is captured + counted
            # rather than silently dropped. Operator-reported 2026-05-06:
            # log silently stopped spooling — without this guard, an
            # exception inside append() takes the message with it. We
            # log render errors to stdlib logger + bump
            # _render_errors so the watchdog can surface the trend.
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
                # Surface to file logger (separate channel) so the
                # operator can recover what was lost
                try:  # noqa: SIM105
                    logger.error(
                        "StatusLog._render exception (#%d): %s | "
                        "message=%r level=%r",
                        self._render_errors,
                        self._last_render_error,
                        message[:200],
                        level,
                    )
                except (
                    Exception
                ):  # R28-OK: defensive — logger itself may have failed  # noqa: S110
                    pass

        def _render_safe(self, ts: str, message: str, level: str = "info") -> None:
            # v3.15.53 — operator directive 2026-04-25: trade notifications
            # in big red letters at SENT / PLACED / FILLED / CANCELLED.
            # The engine emits messages prefixed "TRADE NOTIFICATION:".
            # Render those at large size + bold + red so they stand out
            # from regular activity-log chatter. Replaces several other
            # related notices that were less prominent.
            if message.startswith("TRADE NOTIFICATION:"):
                # Extract the stage if present so we can color by stage
                # (FILLED green, CANCELLED red, SENT/PLACED amber).
                stage_color = ds.ERROR  # red default (CANCELLED / generic)
                if "FILLED" in message:
                    stage_color = ds.SUCCESS
                elif "PLACED" in message:
                    stage_color = ds.WARNING
                elif "SENT" in message:
                    stage_color = ds.PRIMARY
                self.append(
                    f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                    f'<span style="color:{stage_color};font-size:14px;'
                    f'font-weight:bold;">{message}</span>'
                )
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                return
            # v3.15.68 — WIRE FLOW logs (Smart Wire profit routing):
            # distinct magenta color, slightly larger, bold so the
            # operator can spot wire activity at a glance and verify
            # that profit is flowing where it should.
            # v3.15.74 — also styles the dust-skip / unreachable / error
            # variants emitted by SmartWireManager.distribute_fold_profit
            # (all share the "WIRE FLOW" prefix). Target-side
            # WIRE INCOME and WIRE INCOME PENDING now also get the
            # magenta treatment so the operator sees the full source→
            # target flow uniformly.
            if message.startswith("WIRE FLOW") or message.startswith("WIRE INCOME"):
                self.append(
                    f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                    f'<span style="color:{ds.MAIN_BADGE_MAGENTA};font-size:12px;'
                    f'font-weight:bold;">⚡ {message}</span>'
                )
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                return
            # v3.15.69 — WIRE STACK logs (wire income converting to
            # asset acquisition at entry). Green-tinted magenta (gold)
            # to distinguish from generic WIRE FLOW.
            if message.startswith("WIRE STACK") or message.startswith(
                "WIRE STACK FIRE"
            ):
                self.append(
                    f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                    f'<span style="color:{ds.STATE_PENDING};font-size:12px;'
                    f'font-weight:bold;">⚡ {message}</span>'
                )
                self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
                return
            colors = {
                "info": ds.PRIMARY,
                "success": ds.SUCCESS,
                "warning": ds.WARNING,
                "error": ds.ERROR,
            }
            color = colors.get(level, ds.TEXT_HIGH)
            self.append(
                f'<span style="color:{ds.CARD_METRIC_LABEL}">[{ts}]</span> '
                f'<span style="color:{color}">{message}</span>'
            )
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
