"""console_log_surface.py -- the Console log view model served to a frontend.

Colours a formatted log line, holds the pause buffer that decides whether
a line paints now or waits, and assembles both into one serialisable
dict. Colours come from ``design_system`` tokens, so a line on a page
carries the value the Qt pane paints rather than a second palette.

The text arrives already formatted: the Console tab owns the
``logging.Formatter`` and the record itself never reaches here.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``console.log_lines`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt, so the same code serves any
frontend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from .. import design_system as ds

logger = logging.getLogger("acervator.gui.console_log_surface")

METHOD = "console.log_lines"

HIGHLIGHT_MARKER = "INDICATOR PANEL"
BUFFER_MAX = 5000
SCROLL_SLACK = 20

LEVEL_COLORS = {
    "DEBUG": ds.TEXT_MUTED,
    "INFO": ds.TEXT_INACTIVE,
    "WARNING": ds.WARNING,
    "ERROR": ds.ERROR,
    "CRITICAL": ds.MAIN_LOG_CRITICAL,
}
DEFAULT_LEVEL = "INFO"
HIGHLIGHT_COLOR = ds.PRIMARY
DROP_NOTICE_LEVEL = "WARNING"
DROP_NOTICE_COLOR = ds.WARNING


def rgb(hex_color: str) -> tuple[int, int, int]:
    """Split a ``#rrggbb`` token into its three 0-255 channels."""
    digits = hex_color.lstrip("#")
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
    )


def line_token(levelname: str, text: str) -> str:
    """The token a line paints in: the marker beats the level, and an
    unknown level takes the default."""
    if HIGHLIGHT_MARKER in text:
        return HIGHLIGHT_COLOR
    return LEVEL_COLORS.get(levelname, LEVEL_COLORS[DEFAULT_LEVEL])


def line_color(levelname: str, text: str) -> tuple[int, int, int]:
    """The three channels one console line paints in."""
    return rgb(line_token(levelname, text))


@dataclass(frozen=True)
class ConsoleLine:
    """One console line, the level it came in at, and the colour it paints in."""

    text: str
    level: str
    color: str
    r: int
    g: int
    b: int

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "level": self.level,
            "color": self.color,
            "r": self.r,
            "g": self.g,
            "b": self.b,
        }


def build_line(levelname: Any, text: Any) -> ConsoleLine:
    """Colour one formatted line; a missing level paints as the default level."""
    body = "" if text is None else str(text)
    label = str(levelname) if levelname else DEFAULT_LEVEL
    token = line_token(label, body)
    red, green, blue = rgb(token)
    return ConsoleLine(body, label, token, red, green, blue)


class ConsoleLogBuffer:
    """The pause buffer that decides when a line reaches the pane.

    While paused a line is held instead of painted. A line arriving with
    ``buffer_max`` already held is counted as dropped, not held. Resuming
    returns the held lines in arrival order, followed by one notice
    naming the dropped count.
    """

    def __init__(self, buffer_max: int = BUFFER_MAX) -> None:
        self.is_paused = False
        self.buffer_max = buffer_max
        self._held: list[ConsoleLine] = []
        self._dropped_count = 0

    def accept(self, line: ConsoleLine) -> Optional[ConsoleLine]:
        """Return the line to paint now, or ``None`` when it is held."""
        if self.is_paused:
            if len(self._held) >= self.buffer_max:
                self._dropped_count += 1
                return None
            self._held.append(line)
            return None
        return line

    def set_paused(self, paused: bool) -> list[ConsoleLine]:
        """Set the pause state and return the lines the pane now paints.

        Nothing drains while paused, and nothing drains when no line is
        held; a dropped count with no held line keeps its value for the
        next drain.
        """
        self.is_paused = bool(paused)
        if self.is_paused or not self._held:
            return []
        drained = list(self._held)
        self._held.clear()
        if self._dropped_count > 0:
            drained.append(self.drop_notice())
            self._dropped_count = 0
        return drained

    def drop_notice(self) -> ConsoleLine:
        """The line reporting how many messages the cap discarded."""
        red, green, blue = rgb(DROP_NOTICE_COLOR)
        return ConsoleLine(
            f"[CONSOLE PAUSE] {self._dropped_count} "
            f"messages dropped (buffer cap={self.buffer_max})",
            DROP_NOTICE_LEVEL,
            DROP_NOTICE_COLOR,
            red,
            green,
            blue,
        )

    def buffered_count(self) -> int:
        return len(self._held)

    def dropped_count(self) -> int:
        return self._dropped_count


class ConsoleDocument:
    """The lines one batch appends to the pane, in paint order."""

    def __init__(self) -> None:
        self._lines: list[ConsoleLine] = []

    def append(self, line: ConsoleLine) -> None:
        self._lines.append(line)

    @property
    def lines(self) -> list[ConsoleLine]:
        return list(self._lines)

    def is_empty(self) -> bool:
        return not self._lines

    def insert_text(self, pane_empty: bool = True) -> str:
        """Join the batch with newlines and lead with the separator.

        A pane that already holds text needs a leading newline; an empty
        pane does not, and an empty batch inserts nothing.
        """
        if not self._lines:
            return ""
        joined = "\n".join(line.text for line in self._lines)
        return joined if pane_empty else "\n" + joined

    def as_dict(self, pane_empty: bool = True) -> dict:
        return {
            "insert_text": self.insert_text(pane_empty),
            "lines": [line.as_dict() for line in self._lines],
        }


def follows_tail(
    scroll_value: int,
    scroll_max: int,
    slack: int = SCROLL_SLACK,
) -> bool:
    """Whether the pane jumps to the newest line after an append.

    True while the view sits within ``slack`` of the bottom, so a reader
    who scrolled up keeps their position.
    """
    return scroll_value >= scroll_max - slack


PANE_BUFFER = ConsoleLogBuffer()


def build_view_model(
    buffer: ConsoleLogBuffer,
    records: list,
    paused: Optional[bool] = None,
    pane_empty: bool = True,
    scroll_value: int = 0,
    scroll_max: int = 0,
) -> dict:
    """Return the whole surface state as one serialisable dict.

    ``paused`` toggles the pane when it is given, and a resume drains the
    held lines ahead of this batch. A record is a mapping with ``level``
    and ``text``. A record that cannot be read is skipped rather than
    raised, which is the guarantee the Qt handler gives its callers.
    """
    document = ConsoleDocument()
    if paused is not None:
        for line in buffer.set_paused(paused):
            document.append(line)
    for record in records:
        try:
            line = build_line(record.get("level"), record.get("text"))
        except Exception as exc:
            logger.warning("console record skipped: %s", exc)
            continue
        painted = buffer.accept(line)
        if painted is not None:
            document.append(painted)
    return {
        "document": document.as_dict(pane_empty),
        "paused": buffer.is_paused,
        "buffered": buffer.buffered_count(),
        "dropped": buffer.dropped_count(),
        "buffer_max": buffer.buffer_max,
        "follow_tail": follows_tail(scroll_value, scroll_max),
        "level_colors": {
            name: list(rgb(value)) for name, value in LEVEL_COLORS.items()
        },
        "level_hex": dict(LEVEL_COLORS),
        "level_order": list(LEVEL_COLORS),
        "default_level": DEFAULT_LEVEL,
        "highlight_color": list(rgb(HIGHLIGHT_COLOR)),
        "highlight_hex": HIGHLIGHT_COLOR,
        "highlight_marker": HIGHLIGHT_MARKER,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``console.log_lines``.

    Reads ``records``, ``paused``, ``pane_empty``, ``scroll_value`` and
    ``scroll_max`` from the request parameters. The pause state persists
    between calls because the pane's own does.
    """
    paused = params.get("paused")
    return build_view_model(
        PANE_BUFFER,
        params.get("records") or [],
        paused=None if paused is None else bool(paused),
        pane_empty=bool(params.get("pane_empty", True)),
        scroll_value=int(params.get("scroll_value") or 0),
        scroll_max=int(params.get("scroll_max") or 0),
    )
