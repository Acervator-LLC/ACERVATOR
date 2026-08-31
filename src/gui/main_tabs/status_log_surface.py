"""status_log_surface.py -- the Activity Log view model served to a frontend.

Builds the line the Activity Log paints for one message: the timestamp
stamp, the colour the message text takes, the size and weight a trade or
wire message is raised to, and the bullet a wire message carries. Colours
come from ``design_system`` tokens, so a line on a page carries the value
the Qt pane paints rather than a second palette.

It also holds the state the pane owns rather than describes: the pause
buffer that decides whether a line paints now or waits, the document cap
that drops the oldest line, and the render counters the Activity-Log
watchdog polls through ``health_stats``.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``status_log.lines`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt, and it sits beside the other
surfaces rather than beside ``widgets/status_log.py`` because that
package imports Qt in its ``__init__``.
"""

from __future__ import annotations

import contextlib
import logging
import time
from datetime import datetime
from typing import Any, Callable, Optional

from .. import design_system as ds

logger = logging.getLogger("acervator.gui")

METHOD = "status_log.lines"

ACCESSIBLE_NAME = "Status Log"
READ_ONLY = True
MAX_HEIGHT_PX = 150
PLACEHOLDER_TEXT = "Activity log..."
MAX_BLOCKS = 5000
PAUSE_BUFFER_CAP = 2000

TIMESTAMP_FORMAT = "%H:%M:%S"
RESUME_STAMP = "—"

DEFAULT_LOG_LEVEL = "info"
DEFAULT_FORCE_LEVEL = "warning"

TRADE_PREFIX = "TRADE NOTIFICATION:"
WIRE_FLOW_PREFIXES = ("WIRE FLOW", "WIRE INCOME")
WIRE_STACK_PREFIX = "WIRE STACK"
WIRE_BULLET = "⚡ "

TRADE_FONT_SIZE_PX = 14
WIRE_FONT_SIZE_PX = 12

TIMESTAMP_COLOR = ds.CARD_METRIC_LABEL
WIRE_FLOW_COLOR = ds.MAIN_BADGE_MAGENTA
WIRE_STACK_COLOR = ds.STATE_PENDING
RESUME_MARKER_COLOR = ds.PRIMARY

STAGE_COLORS = (
    ("FILLED", ds.SUCCESS),
    ("PLACED", ds.WARNING),
    ("SENT", ds.PRIMARY),
)
STAGE_DEFAULT_COLOR = ds.ERROR

LEVEL_COLORS = {
    "info": ds.PRIMARY,
    "success": ds.SUCCESS,
    "warning": ds.WARNING,
    "error": ds.ERROR,
}
DEFAULT_LEVEL_COLOR = ds.TEXT_HIGH

RENDER_ERROR_FORMAT = "StatusLog._render exception (#%d): %s | message=%r level=%r"
RENDER_ERROR_MESSAGE_CHARS = 200

KIND_TRADE = "trade"
KIND_WIRE_FLOW = "wire_flow"
KIND_WIRE_STACK = "wire_stack"
KIND_PLAIN = "plain"
KIND_RESUME = "resume"

WIDGET = {
    "accessible_name": ACCESSIBLE_NAME,
    "read_only": READ_ONLY,
    "maximum_height_px": MAX_HEIGHT_PX,
    "placeholder_text": PLACEHOLDER_TEXT,
    "maximum_block_count": MAX_BLOCKS,
}


def rgb(hex_color: str) -> tuple[int, int, int]:
    """Split a ``#rgb`` or ``#rrggbb`` token into its three 0-255 channels."""
    digits = hex_color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
    )


def now_seconds() -> float:
    """The wall clock the render counters and ``health_stats`` read."""
    return time.time()


def timestamp(now: Optional[datetime] = None) -> str:
    """The stamp one line carries, taken when the message arrives."""
    return (datetime.now() if now is None else now).strftime(TIMESTAMP_FORMAT)


def stage_color(message: str) -> str:
    """The colour a trade notification takes, read from its stage word.

    The first stage named anywhere in the message wins, in the order
    FILLED, PLACED, SENT. A message naming none paints the error colour,
    which is what a cancellation gets.
    """
    for stage, token in STAGE_COLORS:
        if stage in message:
            return token
    return STAGE_DEFAULT_COLOR


def level_color(level: Any) -> str:
    """The colour a plain line takes. A level the map does not name is
    painted in the neutral body colour rather than any level colour."""
    return LEVEL_COLORS.get(level, DEFAULT_LEVEL_COLOR)


def line_style(message: str, level: Any = DEFAULT_LOG_LEVEL) -> dict:
    """The colour, size, weight and bullet one message paints with.

    The prefix decides before the level does: a trade notification, then
    a wire-flow or wire-income message, then a wire-stack message. Only a
    message matching no prefix is coloured by its level.
    """
    if message.startswith(TRADE_PREFIX):
        return {
            "kind": KIND_TRADE,
            "color": stage_color(message),
            "font_size_px": TRADE_FONT_SIZE_PX,
            "bold": True,
            "italic": False,
            "bullet": "",
        }
    if any(message.startswith(prefix) for prefix in WIRE_FLOW_PREFIXES):
        return {
            "kind": KIND_WIRE_FLOW,
            "color": WIRE_FLOW_COLOR,
            "font_size_px": WIRE_FONT_SIZE_PX,
            "bold": True,
            "italic": False,
            "bullet": WIRE_BULLET,
        }
    if message.startswith(WIRE_STACK_PREFIX):
        return {
            "kind": KIND_WIRE_STACK,
            "color": WIRE_STACK_COLOR,
            "font_size_px": WIRE_FONT_SIZE_PX,
            "bold": True,
            "italic": False,
            "bullet": WIRE_BULLET,
        }
    return {
        "kind": KIND_PLAIN,
        "color": level_color(level),
        "font_size_px": None,
        "bold": False,
        "italic": False,
        "bullet": "",
    }


def stamp_html(stamp: str) -> str:
    """The leading ``[hh:mm:ss]`` span every line carries."""
    return f'<span style="color:{TIMESTAMP_COLOR}">[{stamp}]</span> '


def body_html(message: str, style: dict) -> str:
    """The message span, built from the style the prefix or level chose."""
    declarations = f"color:{style['color']}"
    if style["font_size_px"] is not None:
        declarations += f";font-size:{style['font_size_px']}px;font-weight:bold;"
    if style["italic"]:
        declarations += ";font-style:italic;"
    return f'<span style="{declarations}">{style["bullet"]}{message}</span>'


def line_html(stamp: str, message: str, style: dict) -> str:
    """The whole HTML string the Activity Log appends for one line."""
    return stamp_html(stamp) + body_html(message, style)


def build_line(stamp: str, message: str, level: Any = DEFAULT_LOG_LEVEL) -> dict:
    """One painted line: its HTML, its colour and the style it carries."""
    style = line_style(message, level)
    red, green, blue = rgb(style["color"])
    return {
        "stamp": stamp,
        "message": message,
        "level": level,
        "html": line_html(stamp, message, style),
        "r": red,
        "g": green,
        "b": blue,
        **style,
    }


def resume_line(buffered_count: int) -> dict:
    """The notice closing a resume, naming how many lines were held."""
    style = {
        "kind": KIND_RESUME,
        "color": RESUME_MARKER_COLOR,
        "font_size_px": None,
        "bold": False,
        "italic": True,
        "bullet": "",
    }
    message = f"(resumed — {buffered_count} buffered message(s) above)"
    red, green, blue = rgb(style["color"])
    return {
        "stamp": RESUME_STAMP,
        "message": message,
        "level": None,
        "html": line_html(RESUME_STAMP, message, style),
        "r": red,
        "g": green,
        "b": blue,
        **style,
    }


class StatusLogModel:
    """The Activity Log's own state: its document, pause buffer and counters.

    A line reaches ``sink`` when it paints. While paused a line is held
    instead, and a line arriving with ``pause_buffer_cap`` already held is
    discarded so that what triggered the pause survives. ``render`` is the
    guarded path: a sink that raises is counted and logged rather than
    losing the message silently, which is what the Activity-Log watchdog
    reads through ``health_stats``.
    """

    def __init__(
        self,
        sink: Optional[Callable[[str], None]] = None,
        max_blocks: int = MAX_BLOCKS,
        pause_buffer_cap: int = PAUSE_BUFFER_CAP,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.sink = sink
        self.max_blocks = max_blocks
        self.pause_buffer_cap = pause_buffer_cap
        self.clock = clock or now_seconds
        self.paused = False
        self.pause_buffer: list[tuple[str, str, Any]] = []
        self.lines: list[dict] = []
        self.painted: list[dict] = []
        self.scroll_count = 0
        self.last_render_time = self.clock()
        self.total_renders = 0
        self.render_errors = 0
        self.last_render_error = ""
        self.last_render_error_time = 0.0

    def is_paused(self) -> bool:
        return self.paused

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        """Paint the held lines in arrival order, then the resume notice.

        Each held line keeps the stamp it arrived with. The notice is
        painted outside the guarded path, exactly as the pane paints it.
        """
        self.paused = False
        buffered = list(self.pause_buffer)
        self.pause_buffer.clear()
        for stamp, message, level in buffered:
            self.render(stamp, message, level)
        if buffered:
            self.append(resume_line(len(buffered)))
            self.scroll_to_end()

    def toggle_pause(self) -> bool:
        """Flip the paused state and return what it became."""
        if self.paused:
            self.resume()
        else:
            self.pause()
        return self.paused

    def log(
        self,
        message: str,
        level: Any = DEFAULT_LOG_LEVEL,
        now: Optional[datetime] = None,
    ) -> None:
        """Take the stamp, then paint the line or hold it under a pause."""
        stamp = timestamp(now)
        if self.paused:
            if len(self.pause_buffer) < self.pause_buffer_cap:
                self.pause_buffer.append((stamp, message, level))
            return
        self.render(stamp, message, level)

    def force_log(
        self,
        message: str,
        level: Any = DEFAULT_FORCE_LEVEL,
        now: Optional[datetime] = None,
    ) -> None:
        """Paint a line whether or not the pane is paused.

        The Activity-Log watchdog reports through this, so a pause cannot
        hide the report that the log stopped painting.
        """
        self.render(timestamp(now), message, level)

    def health_stats(self) -> dict:
        """The counters the Activity-Log watchdog polls every 60 s."""
        return {
            "paused": self.paused,
            "pause_buffer_size": len(self.pause_buffer),
            "last_render_age_sec": round(self.clock() - self.last_render_time, 1),
            "total_renders": self.total_renders,
            "render_errors": self.render_errors,
            "last_render_error": self.last_render_error,
            "document_blocks": self.document_blocks(),
        }

    def document_blocks(self) -> int:
        """The pane's block count: one per painted line, never below one."""
        return max(1, len(self.lines))

    def render(self, stamp: str, message: str, level: Any = DEFAULT_LOG_LEVEL) -> None:
        """Paint one line and count the outcome.

        A sink that raises is counted and reported to the file logger, so
        a message lost at the pane leaves a trace the watchdog can read.
        """
        try:
            self.render_line(stamp, message, level)
            self.last_render_time = self.clock()
            self.total_renders += 1
        except Exception as exc:
            self.render_errors += 1
            self.last_render_error = f"{type(exc).__name__}: {exc}"
            self.last_render_error_time = self.clock()
            with contextlib.suppress(Exception):
                logger.error(
                    RENDER_ERROR_FORMAT,
                    self.render_errors,
                    self.last_render_error,
                    message[:RENDER_ERROR_MESSAGE_CHARS],
                    level,
                )

    def render_line(
        self, stamp: str, message: str, level: Any = DEFAULT_LOG_LEVEL
    ) -> None:
        """Build one line, send it to the sink and follow the newest line."""
        self.append(build_line(stamp, message, level))
        self.scroll_to_end()

    def append(self, line: dict) -> None:
        """Send one line to the sink and drop the oldest over the cap."""
        if self.sink is not None:
            self.sink(line["html"])
        self.lines.append(line)
        self.painted.append(line)
        if self.max_blocks > 0:
            while len(self.lines) > self.max_blocks:
                self.lines.pop(0)

    def scroll_to_end(self) -> None:
        self.scroll_count += 1

    def take_painted(self) -> list[dict]:
        """Return the lines painted since the last call and clear them."""
        batch = list(self.painted)
        self.painted.clear()
        return batch


PANE_MODEL: Optional[StatusLogModel] = None


def pane_model() -> StatusLogModel:
    """The one log the bridge keeps between calls.

    Built on the first request, never at import: the constructor
    stamps ``last_render_time`` from the clock.
    """
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = StatusLogModel()
    return PANE_MODEL


def build_view_model(
    model: StatusLogModel,
    messages: Optional[list] = None,
    paused: Optional[bool] = None,
    toggle: bool = False,
) -> dict:
    """Return the whole surface state as one serialisable dict.

    ``toggle`` flips the pause state, ``paused`` sets it, and a resume
    drains the held lines ahead of this batch. A message is a mapping with
    ``message``, ``level`` and an optional ``force`` that paints it
    through a pause. A message that cannot be read is skipped rather than
    raised, which is the guarantee the pane gives its callers.
    """
    model.take_painted()
    if toggle:
        model.toggle_pause()
    elif paused is not None:
        if paused:
            model.pause()
        else:
            model.resume()
    for entry in messages or []:
        try:
            text = str(entry.get("message", ""))
            level = entry.get("level", DEFAULT_LOG_LEVEL)
            forced = bool(entry.get("force", False))
        except Exception as exc:
            logger.warning("status log message skipped: %s", exc)
            continue
        if forced:
            model.force_log(text, level)
        else:
            model.log(text, level)
    return {
        "widget": dict(WIDGET),
        "document": {"lines": model.take_painted()},
        "paused": model.paused,
        "buffered": len(model.pause_buffer),
        "buffer_cap": model.pause_buffer_cap,
        "document_blocks": model.document_blocks(),
        "health": model.health_stats(),
        "timestamp_color": list(rgb(TIMESTAMP_COLOR)),
        "level_colors": {
            name: list(rgb(token)) for name, token in LEVEL_COLORS.items()
        },
        "default_level_color": list(rgb(DEFAULT_LEVEL_COLOR)),
        "stage_colors": {stage: list(rgb(token)) for stage, token in STAGE_COLORS},
        "stage_default_color": list(rgb(STAGE_DEFAULT_COLOR)),
        "wire_flow_color": list(rgb(WIRE_FLOW_COLOR)),
        "wire_stack_color": list(rgb(WIRE_STACK_COLOR)),
        "resume_marker_color": list(rgb(RESUME_MARKER_COLOR)),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``status_log.lines``.

    Reads ``messages``, ``paused`` and ``toggle`` from the request
    parameters. The pause state persists between calls because the pane's
    own does.
    """
    paused = params.get("paused")
    return build_view_model(
        pane_model(),
        params.get("messages") or [],
        paused=None if paused is None else bool(paused),
        toggle=bool(params.get("toggle", False)),
    )
