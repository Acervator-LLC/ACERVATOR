"""console_tab_surface.py -- the Console tab view model served to a frontend.

Describes the whole tab as plain data: the log pane, the control bar and
its two buttons, the buffered-message indicator, the signals pane and its
header, the splitter, the three timers and the drain ledger. Colours,
paddings and fonts come from ``design_system`` tokens, so a page carries
the values the Qt tab paints rather than a second palette.

It also holds the two behaviours the tab owns rather than describes: the
capped block buffer behind each pane, and the log formatter that turns a
record into one console line.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``console.tab`` method, which is how the Electron renderer reaches
it. Nothing here imports Qt, so the same code serves any frontend.
"""

from __future__ import annotations

import logging
import re
from html import unescape
from typing import Any, Optional

from .. import design_system as ds

logger = logging.getLogger("acervator.gui.console_tab_surface")

METHOD = "console.tab"

TAB_TITLE = "Console"

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATEFMT = "%H:%M:%S"
HANDLER_LOGGERS = ("", "acervator")
HANDLER_LEVEL = logging.DEBUG

PANE_MAX_BLOCKS = 2000
SIGNAL_MAX_BLOCKS = 2000

PANE_FONT_FAMILY = "Consolas"
PANE_FONT_POINT_SIZE = 9
CONTROL_FONT_PX = 10

DRAIN_INTERVAL_MS = 500
HEALTH_INTERVAL_MS = 5000
PAUSE_REFRESH_INTERVAL_MS = 500

SPLIT_STRETCH_LOG = 3
SPLIT_STRETCH_SIGNALS = 2

PAUSE_BUTTON_TEXT = "⏸  Pause"
CLEAR_BUTTON_TEXT = "Clear"
PAUSE_INDICATOR_TEXT = ""
SIGNAL_HEADER_TEXT = "  SIGNALS — name · expected · actual"
#: A console line paints in these channels where its markup names none.
DEFAULT_LINE_COLOR = (224, 224, 240)

TAG_PATTERN = re.compile(r"<[^>]*>")
COLOR_PATTERN = re.compile(r"color\s*:\s*(#[0-9a-fA-F]{6}|rgb\(([^)]*)\))")

PANE_STYLE = (
    f"QPlainTextEdit {{ background: {ds.SURFACE_CHART}; color: "
    f"{ds.TEXT_CONSOLE}; "
    "border: none; padding: 4px; }"
)

CONTROL_BAR_STYLE = (
    f"QWidget {{ background: {ds.MAIN_TOOLBAR_SURFACE}; border-bottom: 1px "
    f"solid {ds.MAIN_SEPARATOR}; }}"
)

PAUSE_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.MAIN_BUTTON_SURFACE}; color: "
    f"{ds.TEXT_CONSOLE}; "
    f"border: 1px solid {ds.MAIN_BUTTON_BORDER}; padding: 4px 12px; "
    "font-family: Consolas; font-size: 10px; }"
    f"QPushButton:checked {{ background: {ds.MAIN_TOGGLE_CHECKED_AMBER}; "
    f"color: {ds.WARNING}; "
    f"border-color: {ds.WARNING}; }}"
    f"QPushButton:hover {{ background: {ds.MAIN_BUTTON_HOVER}; }}"
)

PAUSE_INDICATOR_STYLE = (
    f"color: {ds.WARNING}; font-family: Consolas; font-size: 10px; " "padding: 0 8px;"
)

CLEAR_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.MAIN_BUTTON_SURFACE}; color: "
    f"{ds.TEXT_CONSOLE}; "
    f"border: 1px solid {ds.MAIN_BUTTON_BORDER}; padding: 4px 12px; "
    "font-family: Consolas; font-size: 10px; }"
    f"QPushButton:hover {{ background: {ds.MAIN_BUTTON_HOVER}; }}"
)

SIGNAL_HEADER_STYLE = (
    f"background:{ds.SURFACE_CONSOLE_HEADER};color:{ds.PRIMARY};font-family:Consolas;"
    f"font-size:10px;padding:3px;border-top:1px solid {ds.SURFACE_4};"
)

SIGNAL_PANE_STYLE = (
    f"QPlainTextEdit{{background:{ds.SURFACE_CONSOLE};color:{ds.TEXT_LOG_MINT};"
    "font-family:Consolas;font-size:10px;border:none;}"
)

LOG_PANE = {
    "read_only": True,
    "font_family": PANE_FONT_FAMILY,
    "font_point_size": PANE_FONT_POINT_SIZE,
    "background": ds.SURFACE_CHART,
    "color": ds.TEXT_CONSOLE,
    "border": "none",
    "padding_px": 4,
    "wrap": False,
    "center_on_scroll": False,
    "max_blocks": PANE_MAX_BLOCKS,
    "style_sheet": PANE_STYLE,
}

SIGNAL_PANE = {
    "read_only": True,
    "font_family": PANE_FONT_FAMILY,
    "font_size_px": CONTROL_FONT_PX,
    "background": ds.SURFACE_CONSOLE,
    "color": ds.TEXT_LOG_MINT,
    "border": "none",
    "max_blocks": SIGNAL_MAX_BLOCKS,
    "style_sheet": SIGNAL_PANE_STYLE,
}

SIGNAL_HEADER = {
    "text": SIGNAL_HEADER_TEXT,
    "background": ds.SURFACE_CONSOLE_HEADER,
    "color": ds.PRIMARY,
    "font_family": PANE_FONT_FAMILY,
    "font_size_px": CONTROL_FONT_PX,
    "padding_px": 3,
    "border_top": f"1px solid {ds.SURFACE_4}",
    "style_sheet": SIGNAL_HEADER_STYLE,
}

CONTROL_BAR = {
    "background": ds.MAIN_TOOLBAR_SURFACE,
    "border_bottom": f"1px solid {ds.MAIN_SEPARATOR}",
    "margins_px": [6, 4, 6, 4],
    "spacing_px": 8,
    "child_stretch": [0, 0, 1, 0],
    "style_sheet": CONTROL_BAR_STYLE,
}

CONTAINER = {
    "margins_px": [0, 0, 0, 0],
    "spacing_px": 0,
    "child_stretch": [0, 1],
}
SIGNAL_BOX = {
    "margins_px": [0, 0, 0, 0],
    "spacing_px": 0,
    "child_stretch": [0, 1],
}

SPLITTER = {
    "orientation": "vertical",
    "children": ["log_pane", "signal_box"],
    "stretch": [SPLIT_STRETCH_LOG, SPLIT_STRETCH_SIGNALS],
}

PAUSE_BUTTON = {
    "text": PAUSE_BUTTON_TEXT,
    "checkable": True,
    "checked": False,
    "background": ds.MAIN_BUTTON_SURFACE,
    "color": ds.TEXT_CONSOLE,
    "border": f"1px solid {ds.MAIN_BUTTON_BORDER}",
    "padding_px": [4, 12],
    "font_family": PANE_FONT_FAMILY,
    "font_size_px": CONTROL_FONT_PX,
    "checked_background": ds.MAIN_TOGGLE_CHECKED_AMBER,
    "checked_color": ds.WARNING,
    "checked_border_color": ds.WARNING,
    "hover_background": ds.MAIN_BUTTON_HOVER,
    "style_sheet": PAUSE_BUTTON_STYLE,
}

PAUSE_INDICATOR = {
    "text": PAUSE_INDICATOR_TEXT,
    "color": ds.WARNING,
    "font_family": PANE_FONT_FAMILY,
    "font_size_px": CONTROL_FONT_PX,
    "padding_px": [0, 8],
    "style_sheet": PAUSE_INDICATOR_STYLE,
}

CLEAR_BUTTON = {
    "text": CLEAR_BUTTON_TEXT,
    "checkable": False,
    "background": ds.MAIN_BUTTON_SURFACE,
    "color": ds.TEXT_CONSOLE,
    "border": f"1px solid {ds.MAIN_BUTTON_BORDER}",
    "padding_px": [4, 12],
    "font_family": PANE_FONT_FAMILY,
    "font_size_px": CONTROL_FONT_PX,
    "hover_background": ds.MAIN_BUTTON_HOVER,
    "style_sheet": CLEAR_BUTTON_STYLE,
}

CONTROL_BAR_ORDER = ["pause_button", "pause_indicator", "stretch", "clear_button"]

TIMERS = {
    "drain": {"interval_ms": DRAIN_INTERVAL_MS, "running": True},
    "health": {"interval_ms": HEALTH_INTERVAL_MS, "running": True},
    "pause_refresh": {"interval_ms": PAUSE_REFRESH_INTERVAL_MS, "running": False},
}

ACTIONS = {
    "pause_button.clicked": "toggle_console_pause",
    "clear_button.clicked": "clear_log_pane",
    "drain.timeout": "drain_signals",
    "health.timeout": "emit_console_health",
    "pause_refresh.timeout": "refresh_console_pause_indicator",
}

LOG_HANDLER = {
    "format": LOG_FORMAT,
    "datefmt": LOG_DATEFMT,
    "loggers": list(HANDLER_LOGGERS),
    "handler_level": HANDLER_LEVEL,
}

FORMATTER = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)


def format_record(fields: Any) -> str:
    """Render one log record as the console line the Qt pane shows.

    Reads ``name``, ``level``, ``message`` and an optional epoch
    ``created`` from a mapping. The formatter is the one the tab attaches
    to its handler, so a page never rebuilds the line itself.
    """
    message = fields.get("message")
    record = logging.LogRecord(
        name=str(fields.get("name") or ""),
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="" if message is None else str(message),
        args=(),
        exc_info=None,
    )
    record.levelname = str(fields.get("level") or "INFO")
    created = fields.get("created")
    if created is not None:
        record.created = float(created)
    return FORMATTER.format(record)


def line_text(markup: Any) -> str:
    """One console line as plain words, with every tag taken out.

    ``unescape`` puts back an entity the markup carried, so the Qt pane
    and a page show one line the same way.
    """
    body = "" if markup is None else str(markup)
    return unescape(TAG_PATTERN.sub("", body))


def line_channels(markup: Any, fallback: tuple = DEFAULT_LINE_COLOR) -> list:
    """The three channels one line paints in, read off its first colour."""
    found = COLOR_PATTERN.search("" if markup is None else str(markup))
    if found is None:
        return list(fallback)
    digits = found.group(1)
    if digits.startswith("#"):
        body = digits[1:]
        return [int(body[at : at + 2], 16) for at in (0, 2, 4)]
    return [int(one) for one in found.group(2).split(",")]


def record_channels(fields: Any, line: Any) -> list:
    """The three channels one record's line paints in.

    ``console_log_surface`` owns the level colours, so a page and the Qt
    pane paint one record the same.
    """
    from . import console_log_surface

    level = str(fields.get("level") or console_log_surface.DEFAULT_LEVEL)
    return list(console_log_surface.line_color(level, str(line)))


class ConsolePane:
    """The capped block buffer behind one console pane.

    Text arrives at the end of the last block; each newline starts a new
    one. Once the block count passes ``max_blocks`` the oldest blocks
    fall off, which is what bounds the pane's memory. A cap of zero or
    less holds every block.
    """

    def __init__(self, max_blocks: int = PANE_MAX_BLOCKS) -> None:
        self.max_blocks = max_blocks
        self._blocks: list[str] = []
        self._colors: list[list] = []

    def insert(self, text: Any, color: Any = None) -> None:
        """Append text at the end, in ``color``. An empty string changes nothing."""
        body = "" if text is None else str(text)
        if not body:
            return
        parts = body.split("\n")
        channels = list(color) if color else list(DEFAULT_LINE_COLOR)
        if not self._blocks:
            self._blocks = parts
            self._colors = [list(channels) for _ in parts]
        else:
            self._blocks[-1] += parts[0]
            self._blocks.extend(parts[1:])
            if not self._colors:
                self._colors = [list(channels)]
            self._colors[-1] = list(channels)
            self._colors.extend(list(channels) for _ in parts[1:])
        self._trim()

    def _trim(self) -> None:
        if self.max_blocks > 0 and len(self._blocks) > self.max_blocks:
            dropped = len(self._blocks) - self.max_blocks
            del self._blocks[:dropped]
            del self._colors[:dropped]

    def clear(self) -> None:
        """Empty the pane, the way the Clear button does."""
        self._blocks = []
        self._colors = []

    def blocks(self) -> list[str]:
        return list(self._blocks)

    def block_colors(self) -> list:
        """One set of three channels per block, in block order."""
        return [list(one) for one in self._colors]

    def block_count(self) -> int:
        """Blocks held. An empty pane counts as one, as the Qt pane does."""
        return len(self._blocks) or 1

    def is_empty(self) -> bool:
        return not self._blocks

    def text(self) -> str:
        return "\n".join(self._blocks)

    def as_dict(self) -> dict:
        return {
            "text": self.text(),
            "blocks": self.blocks(),
            "block_colors": self.block_colors(),
            "block_count": self.block_count(),
            "is_empty": self.is_empty(),
        }


LEDGER_FIELDS = (
    "seq",
    "drain_ticks",
    "read",
    "rendered",
    "slice_dropped",
    "markers",
    "health_ticks_seen",
)


class SignalLedger:
    """The seven counters the drain writes and the health timer reads.

    The tab starts every one at zero. They are kept here as data so a
    page reports the same numbers the Qt tab holds.
    """

    def __init__(self) -> None:
        for name in LEDGER_FIELDS:
            setattr(self, name, 0)

    def as_dict(self) -> dict:
        return {name: int(getattr(self, name)) for name in LEDGER_FIELDS}


def build_view_model(
    log_pane: ConsolePane,
    signal_pane: ConsolePane,
    ledger: SignalLedger,
    records: Optional[list] = None,
    signal_lines: Optional[list] = None,
    clear_log: bool = False,
) -> dict:
    """Return the whole tab state as one serialisable dict.

    ``clear_log`` empties the log pane first, which is the Clear button.
    Each record is formatted and appended as its own block; a record that
    cannot be read is skipped rather than raised, which is the guarantee
    the Qt log handler gives its callers.
    """
    if clear_log:
        log_pane.clear()
    for record in records or []:
        try:
            line = format_record(record)
        except Exception as exc:
            logger.warning("console record skipped: %s", exc)
            continue
        channels = record_channels(record, line)
        log_pane.insert(line if log_pane.is_empty() else "\n" + line, channels)
    for line in signal_lines or []:
        body = line_text(line)
        signal_pane.insert(
            body if signal_pane.is_empty() else "\n" + body, line_channels(line)
        )
    return {
        "tab_title": TAB_TITLE,
        "container": CONTAINER,
        "control_bar": CONTROL_BAR,
        "control_bar_order": CONTROL_BAR_ORDER,
        "pause_button": PAUSE_BUTTON,
        "pause_indicator": PAUSE_INDICATOR,
        "clear_button": CLEAR_BUTTON,
        "signal_box": SIGNAL_BOX,
        "signal_header": SIGNAL_HEADER,
        "splitter": SPLITTER,
        "timers": TIMERS,
        "actions": ACTIONS,
        "log_handler": LOG_HANDLER,
        "log_pane": {**LOG_PANE, **log_pane.as_dict()},
        "signal_pane": {**SIGNAL_PANE, **signal_pane.as_dict()},
        "ledger": ledger.as_dict(),
    }


LOG_PANE_BUFFER = ConsolePane(PANE_MAX_BLOCKS)
SIGNAL_PANE_BUFFER = ConsolePane(SIGNAL_MAX_BLOCKS)
DRAIN_LEDGER = SignalLedger()


def view_model(params: dict) -> dict:
    """Bridge handler for ``console.tab``.

    Reads ``records``, ``signal_lines`` and ``clear`` from the request
    parameters. Both panes and the ledger persist between calls because
    the Qt panes they stand for do.
    """
    return build_view_model(
        LOG_PANE_BUFFER,
        SIGNAL_PANE_BUFFER,
        DRAIN_LEDGER,
        records=params.get("records") or [],
        signal_lines=params.get("signal_lines") or [],
        clear_log=bool(params.get("clear")),
    )
