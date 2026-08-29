"""notification_spool_surface.py -- the Notification Spool view model.

Builds the line the Notification Spool paints for one market or bot
event: the timestamp stamp and the colour the message text takes for its
level. Colours come from ``design_system`` tokens, so a line on a page
carries the value the Qt pane paints rather than a second palette.

It also holds the state the pane owns rather than describes: the lines
the document carries, the block count the document reports, and the jump
to the newest line the pane performs after every event.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``notification_spool.lines`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt, and it sits beside the
other surfaces rather than beside ``widgets/notification_spool.py``
because that package imports Qt in its ``__init__``.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Optional

from .. import design_system as ds

logger = logging.getLogger("acervator.gui.notification_spool_surface")

METHOD = "notification_spool.lines"

ACCESSIBLE_NAME = "Notification Spool"
READ_ONLY = True
MAX_HEIGHT_PX = 100
PLACEHOLDER_TEXT = "Market status and bot notifications..."
MAX_BLOCKS = 0

TIMESTAMP_FORMAT = "%H:%M:%S"
DEFAULT_LEVEL = "info"

TIMESTAMP_COLOR = ds.TEXT_PLACEHOLDER

LEVEL_COLORS = {
    "info": ds.PRIMARY,
    "success": ds.SUCCESS,
    "warning": ds.WARNING,
    "error": ds.ERROR,
    "market": ds.STATE_MARKET,
}
DEFAULT_LEVEL_COLOR = ds.TEXT_HIGH

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


def timestamp(now: Optional[datetime] = None) -> str:
    """The stamp one line carries, taken when the event arrives."""
    return (datetime.now() if now is None else now).strftime(TIMESTAMP_FORMAT)


def level_color(level: Any) -> str:
    """The colour one message takes. A level the map does not name is
    painted in the neutral body colour rather than any level colour."""
    return LEVEL_COLORS.get(level, DEFAULT_LEVEL_COLOR)


def stamp_html(stamp: str) -> str:
    """The leading timestamp span every line carries, and its trailing space."""
    return f'<span style="color:{TIMESTAMP_COLOR}">{stamp}</span> '


def body_html(message: str, color: str) -> str:
    """The message span, painted in the colour the level chose."""
    return f'<span style="color:{color}">{message}</span>'


def line_html(stamp: str, message: str, color: str) -> str:
    """The whole HTML string the Notification Spool appends for one line."""
    return stamp_html(stamp) + body_html(message, color)


def build_line(stamp: str, message: str, level: Any = DEFAULT_LEVEL) -> dict:
    """One painted line: its HTML, its colour token and that colour's channels."""
    color = level_color(level)
    red, green, blue = rgb(color)
    return {
        "stamp": stamp,
        "message": message,
        "level": level,
        "color": color,
        "html": line_html(stamp, message, color),
        "r": red,
        "g": green,
        "b": blue,
    }


class NotificationSpoolModel:
    """The Notification Spool's own state: its document and its scrolling.

    A line reaches ``sink`` when it paints. ``max_blocks`` is the
    document cap: zero, the pane's own value, keeps every line. Every
    notification jumps the view to the newest line, which is what
    ``scroll_count`` counts.
    """

    def __init__(
        self,
        sink: Optional[Callable[[str], None]] = None,
        max_blocks: int = MAX_BLOCKS,
    ) -> None:
        self.sink = sink
        self.max_blocks = max_blocks
        self.lines: list[dict] = []
        self.painted: list[dict] = []
        self.scroll_count = 0

    def notify(
        self,
        message: str,
        level: Any = DEFAULT_LEVEL,
        now: Optional[datetime] = None,
    ) -> None:
        """Take the stamp, paint the line and follow the newest line."""
        self.append(build_line(timestamp(now), message, level))
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

    def document_blocks(self) -> int:
        """The pane's block count: one per painted line, never below one."""
        return max(1, len(self.lines))

    def take_painted(self) -> list[dict]:
        """Return the lines painted since the last call and clear them."""
        batch = list(self.painted)
        self.painted.clear()
        return batch


PANE_MODEL = NotificationSpoolModel()


def build_view_model(
    model: NotificationSpoolModel, messages: Optional[list] = None
) -> dict:
    """Return the whole surface state as one serialisable dict.

    A message is a mapping with ``message`` and ``level``. A message that
    cannot be read is skipped rather than raised, so one bad entry in a
    batch cannot lose the rest.
    """
    model.take_painted()
    for entry in messages or []:
        try:
            text = str(entry.get("message", ""))
            level = entry.get("level", DEFAULT_LEVEL)
        except Exception as exc:
            logger.warning("notification spool message skipped: %s", exc)
            continue
        model.notify(text, level)
    return {
        "widget": dict(WIDGET),
        "document": {"lines": model.take_painted()},
        "document_blocks": model.document_blocks(),
        "timestamp_color": list(rgb(TIMESTAMP_COLOR)),
        "level_colors": {
            name: list(rgb(token)) for name, token in LEVEL_COLORS.items()
        },
        "default_level_color": list(rgb(DEFAULT_LEVEL_COLOR)),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``notification_spool.lines``.

    Reads ``messages`` from the request parameters. The document persists
    between calls because the pane's own does.
    """
    return build_view_model(PANE_MODEL, params.get("messages") or [])
