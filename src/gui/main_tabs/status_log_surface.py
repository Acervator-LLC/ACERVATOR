"""status_log_surface.py -- the Activity Log view model served to a frontend.

Builds the line the Activity Log paints for one message: the timestamp
stamp, the colour the message text takes, the size and weight a trade or
wire message is raised to, and the glyph a trade or wire line carries. Colours
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
import html
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable, Optional

from ...core.event_bus import (
    LINE_KIND_TRADE,
    LINE_KIND_WIRE_FLOW,
    LINE_KIND_WIRE_STACK,
)
from ...trading.gate_vocabulary import BANK_MARKER_COLOR, LIGHT_LABEL_COLOR
from .. import design_system as ds
from .native_chart_surface import READOUT_BUY_GLYPH, READOUT_SELL_GLYPH
from .trade_charts_tab_surface import BUY_SIDE, SELL_SIDE, SIDE_ROLES

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
NOTICE_STAMP = ""
STAMP_FORMAT = "[{stamp}]"

DEFAULT_LOG_LEVEL = "info"
DEFAULT_FORCE_LEVEL = "warning"

TRADE_PREFIX = "TRADE NOTIFICATION:"
WIRE_FLOW_PREFIXES = ("WIRE FLOW", "WIRE INCOME")
WIRE_STACK_PREFIX = "WIRE STACK"
WIRE_BULLET = "⚡ "

#: ``MainWindow._on_bot_log`` opens a bot's line with ``[TICKER/last4] ``.
BOT_TAG_PATTERN = re.compile(r"^\[[^\[\]]*\]\s+")

#: The glyph a trade role draws, by the side ``SIDE_ROLES`` gives that role.
ROLE_GLYPHS = {
    SIDE_ROLES[SELL_SIDE]: READOUT_SELL_GLYPH,
    SIDE_ROLES[BUY_SIDE]: READOUT_BUY_GLYPH,
}
GLYPH_FORMAT = "{glyph} "

#: ``_emit_trade_notification`` writes ``<ROLE>: <SYMBOL>: <STAGE>`` after
#: ``TRADE_PREFIX``, then the stage's own numbers.
TRADE_FIELD_SPLIT = ": "
TRADE_FIELD_COUNT = 3
TRADE_STAGE_SPLIT = " "
TRADE_TEXT_FORMAT = "{stage} [{role}] {symbol}"

TRADE_FONT_SIZE_PX = 14
WIRE_FONT_SIZE_PX = 12

#: A gate light draws its own colour behind two spaces, so no glyph is needed.
LIGHT_DOT_TEXT = "&nbsp;&nbsp;"
LIGHT_SEPARATOR = " "

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

#: A writer names one of the first three on its own ``bot.log`` emit.
KIND_TRADE = LINE_KIND_TRADE
KIND_WIRE_FLOW = LINE_KIND_WIRE_FLOW
KIND_WIRE_STACK = LINE_KIND_WIRE_STACK
KIND_PLAIN = "plain"
KIND_RESUME = "resume"

#: The words a message opens with that ``asked_kind`` reads its kind from, in the
#: order it reads them.
KIND_MARKERS = (
    (KIND_TRADE, (TRADE_PREFIX,)),
    (KIND_WIRE_FLOW, WIRE_FLOW_PREFIXES),
    (KIND_WIRE_STACK, (WIRE_STACK_PREFIX,)),
)
NO_KIND = ""

#: How much of a line's own opening ``writer_mark`` keeps to name its writer.
WRITER_MARK_SPLIT = ":"
WRITER_MARK_CHARS = 40

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


def bot_tag(message: str) -> str:
    """The ``[TICKER/last4] `` tag ``MainWindow._on_bot_log`` opens a bot's line
    with. ``BOT_TAG_PATTERN`` matching nothing gives an empty string."""
    found = BOT_TAG_PATTERN.match(message)
    return found.group(0) if found else ""


# The first sentence of the docstring below is overtaken. Quoted whole:
#   "The part of one message the prefix rules read."
# It is the part of one message ``line_style`` draws as the line's text.
def shape_source(message: str) -> str:
    """The part of one message the prefix rules read. ``bot_tag`` comes off
    before ``TRADE_PREFIX`` or a wire prefix is matched."""
    return message[len(bot_tag(message)) :]


def asked_kind(message: str) -> str:
    """The kind one message's own words ask for, read from a marker anywhere in
    it, or ``NO_KIND``."""
    for kind, markers in KIND_MARKERS:
        if any(marker in message for marker in markers):
            return kind
    return NO_KIND


def writer_mark(message: str) -> str:
    """The words one line opens with after ``bot_tag``, which name the writer
    that wrote it, cut at ``WRITER_MARK_SPLIT`` and ``WRITER_MARK_CHARS``."""
    head = shape_source(message).split(WRITER_MARK_SPLIT, 1)[0]
    return head[:WRITER_MARK_CHARS]


# A message not opening with ``TRADE_PREFIX`` carries no ``<ROLE>: <SYMBOL>:
# <STAGE>`` to read, and draws unchanged.
def trade_text(shaped: str) -> tuple[str, str]:
    """The stage-first text a trade message draws, and the role it named.
    A message short of ``TRADE_FIELD_COUNT`` fields draws unchanged, no role."""
    if not shaped.startswith(TRADE_PREFIX):
        return shaped, ""
    body = shaped[len(TRADE_PREFIX) :].strip()
    fields = body.split(TRADE_FIELD_SPLIT, TRADE_FIELD_COUNT - 1)
    if len(fields) < TRADE_FIELD_COUNT:
        return shaped, ""
    role, symbol, tail = fields
    stage, _, rest = tail.partition(TRADE_STAGE_SPLIT)
    drawn = TRADE_TEXT_FORMAT.format(stage=stage, role=role, symbol=symbol)
    return (drawn + TRADE_STAGE_SPLIT + rest if rest else drawn), role


# One sentence of the docstring below is overtaken. Quoted whole:
#   "One line's drawn shape: ``kind``, ``tag``, ``bullet``, ``text`` and its
#   weights."
# The shape also carries ``lights``, the gate lights a per-tick line draws.
def style_of(
    kind: str,
    tag: str,
    text: str,
    color: str,
    font_size_px: Optional[int] = None,
    bold: bool = False,
    italic: bool = False,
    bullet: str = "",
    lights: Optional[list] = None,
) -> dict:
    """One line's drawn shape: ``kind``, ``tag``, ``bullet``, ``text`` and its
    weights. ``line_style``, ``resume_line`` and ``notice_line`` all return it."""
    return {
        "kind": kind,
        "tag": tag,
        "text": text,
        "color": color,
        "font_size_px": font_size_px,
        "bold": bold,
        "italic": italic,
        "bullet": bullet,
        "lights": [dict(one) for one in lights or []],
    }


# The second sentence of the docstring below is overtaken. Quoted whole:
#   "``TRADE_PREFIX`` then the wire prefixes decide before ``level_color`` does."
# The ``kind`` the writer named decides, and ``level_color`` paints a line naming
# none.
def line_style(
    message: str,
    level: Any = DEFAULT_LOG_LEVEL,
    kind: Optional[str] = None,
    lights: Optional[list] = None,
) -> dict:
    """The three parts one message draws, and the weights it draws them in.
    ``TRADE_PREFIX`` then the wire prefixes decide before ``level_color`` does."""
    tag = bot_tag(message)
    shaped = shape_source(message)
    if kind == KIND_TRADE:
        drawn, role = trade_text(shaped)
        glyph = ROLE_GLYPHS.get(role, "")
        return style_of(
            KIND_TRADE,
            tag,
            drawn,
            stage_color(shaped),
            font_size_px=TRADE_FONT_SIZE_PX,
            bold=True,
            bullet=GLYPH_FORMAT.format(glyph=glyph) if glyph else "",
        )
    if kind == KIND_WIRE_FLOW:
        return style_of(
            KIND_WIRE_FLOW,
            tag,
            shaped,
            WIRE_FLOW_COLOR,
            font_size_px=WIRE_FONT_SIZE_PX,
            bold=True,
            bullet=WIRE_BULLET,
        )
    if kind == KIND_WIRE_STACK:
        return style_of(
            KIND_WIRE_STACK,
            tag,
            shaped,
            WIRE_STACK_COLOR,
            font_size_px=WIRE_FONT_SIZE_PX,
            bold=True,
            bullet=WIRE_BULLET,
        )
    return style_of(KIND_PLAIN, tag, shaped, level_color(level), lights=lights)


def stamp_text(stamp: str) -> str:
    """The leading ``[hh:mm:ss]`` a line paints, empty for an unstamped one."""
    return STAMP_FORMAT.format(stamp=stamp) if stamp else NOTICE_STAMP


def stamp_html(stamp: str) -> str:
    """The leading ``[hh:mm:ss]`` span every line carries."""
    return f'<span style="color:{TIMESTAMP_COLOR}">{stamp_text(stamp)}</span> '


def body_html(style: dict) -> str:
    """The body span: the bot's tag, then the glyph, then the drawn text.
    ``html.escape`` keeps a message carrying ``<`` from vanishing as a tag."""
    declarations = f"color:{style['color']}"
    if style["font_size_px"] is not None:
        declarations += f";font-size:{style['font_size_px']}px;font-weight:bold;"
    if style["italic"]:
        declarations += ";font-style:italic;"
    tag = html.escape(style["tag"], quote=False)
    drawn = html.escape(style["text"], quote=False)
    lit = lights_html(style.get("lights"))
    return f'<span style="{declarations}">{tag}{style["bullet"]}{drawn}{lit}</span>'


def light_html(light: dict) -> str:
    """One gate light: its label, then its own resolved colour as a block."""
    label = html.escape(str(light.get("label", "")), quote=False)
    tone = str(light.get("color", "") or "")
    return (
        f'<span style="color:{LIGHT_LABEL_COLOR}">{label}</span>'
        f'<span style="background-color:{tone}">{LIGHT_DOT_TEXT}</span>'
    )


def bank_marker_html(bank: str) -> str:
    """The marker closing one bank of gate lights."""
    marked = html.escape(str(bank), quote=False)
    return f'<span style="color:{BANK_MARKER_COLOR}">{marked}</span>'


def lights_html(lights: Optional[list]) -> str:
    """Every gate light one line carries, each bank closed by its own marker.

    ``gate_light_row`` gives the draw order and each light's colour, so no
    order and no colour is decided here.
    """
    parts: list[str] = []
    bank = ""
    for light in lights or []:
        named = str(light.get("bank", ""))
        if bank and named != bank:
            parts.append(bank_marker_html(bank))
        bank = named
        parts.append(light_html(light))
    if bank:
        parts.append(bank_marker_html(bank))
    if not parts:
        return ""
    return LIGHT_SEPARATOR + LIGHT_SEPARATOR.join(parts)


# One sentence of the docstring below is overtaken. Quoted whole:
#   "The whole HTML string the Activity Log appends for one line."
# A per-tick line closes with ``lights_html``, inside the body span.
def line_html(stamp: str, style: dict) -> str:
    """The whole HTML string the Activity Log appends for one line."""
    return stamp_html(stamp) + body_html(style)


def painted_line(stamp: str, level: Any, style: dict) -> dict:
    """One painted line: its stamp, its level, its HTML and its whole shape."""
    red, green, blue = rgb(style["color"])
    return {
        "stamp": stamp,
        "stamp_text": stamp_text(stamp),
        "level": level,
        "html": line_html(stamp, style),
        "r": red,
        "g": green,
        "b": blue,
        **style,
    }


def build_line(
    stamp: str,
    message: str,
    level: Any = DEFAULT_LOG_LEVEL,
    kind: Optional[str] = None,
    lights: Optional[list] = None,
) -> dict:
    """One painted line for ``message``, shaped by ``line_style``."""
    return painted_line(stamp, level, line_style(message, level, kind, lights))


def resume_line(buffered_count: int) -> dict:
    """The notice closing a resume, naming how many lines were held."""
    text = f"(resumed — {buffered_count} buffered message(s) above)"
    style = style_of(KIND_RESUME, "", text, RESUME_MARKER_COLOR, italic=True)
    return painted_line(RESUME_STAMP, None, style)


def notice_line(text: str) -> dict:
    """One unstamped line, which is what ``StatusLog.notice`` appends."""
    style = style_of(KIND_PLAIN, "", str(text), DEFAULT_LEVEL_COLOR)
    return painted_line(NOTICE_STAMP, None, style)


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
        self.pause_buffer: list[tuple] = []
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
        for stamp, message, level, kind, lights in buffered:
            self.render(stamp, message, level, kind, lights)
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
        kind: Optional[str] = None,
        lights: Optional[list] = None,
    ) -> None:
        """Take the stamp, then paint the line or hold it under a pause."""
        stamp = timestamp(now)
        if self.paused:
            if len(self.pause_buffer) < self.pause_buffer_cap:
                self.pause_buffer.append((stamp, message, level, kind, lights))
            return
        self.render(stamp, message, level, kind, lights)

    def force_log(
        self,
        message: str,
        level: Any = DEFAULT_FORCE_LEVEL,
        now: Optional[datetime] = None,
        kind: Optional[str] = None,
        lights: Optional[list] = None,
    ) -> None:
        """Paint a line whether or not the pane is paused.

        The Activity-Log watchdog reports through this, so a pause cannot
        hide the report that the log stopped painting.
        """
        self.render(timestamp(now), message, level, kind, lights)

    def append_text(self, text: str) -> None:
        """Paint one unstamped line through ``notice_line``, whatever ``paused``
        holds."""
        self.append(notice_line(text))
        self.scroll_to_end()
        self.last_render_time = self.clock()
        self.total_renders += 1

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

    def render(
        self,
        stamp: str,
        message: str,
        level: Any = DEFAULT_LOG_LEVEL,
        kind: Optional[str] = None,
        lights: Optional[list] = None,
    ) -> None:
        """Paint one line and count the outcome.

        A sink that raises is counted and reported to the file logger, so
        a message lost at the pane leaves a trace the watchdog can read.
        """
        try:
            self.render_line(stamp, message, level, kind, lights)
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
        self,
        stamp: str,
        message: str,
        level: Any = DEFAULT_LOG_LEVEL,
        kind: Optional[str] = None,
        lights: Optional[list] = None,
    ) -> None:
        """Build one line, send it to the sink and follow the newest line."""
        self.append(build_line(stamp, message, level, kind, lights))
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


# One sentence of the docstring below is overtaken. Quoted whole:
#   "A message is a mapping with ``message``, ``level`` and an optional ``force``
#   that paints it through a pause."
# A message also carries ``kind``, the kind its writer named.
# A message also carries ``lights``, the gate lights its writer resolved.
def build_view_model(
    model: StatusLogModel,
    messages: Optional[list] = None,
    paused: Optional[bool] = None,
    toggle: bool = False,
    notices: Optional[list] = None,
    whole: bool = False,
) -> dict:
    """Return the whole surface state as one serialisable dict.

    ``toggle`` flips the pause state, ``paused`` sets it, and a resume
    drains the held lines ahead of this batch. A message is a mapping with
    ``message``, ``level`` and an optional ``force`` that paints it
    through a pause. A message that cannot be read is skipped rather than
    raised, which is the guarantee the pane gives its callers. ``whole``
    returns every line the document holds rather than this call's batch,
    which is what a pane opening for the first time draws.
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
            named = entry.get("kind")
            lit = entry.get("lights")
        except Exception as exc:
            logger.warning("status log message skipped: %s", exc)
            continue
        if forced:
            model.force_log(text, level, kind=named, lights=lit)
        else:
            model.log(text, level, kind=named, lights=lit)
    for relayed in notices or []:
        model.append_text(str(relayed))
    batch = model.take_painted()
    return {
        "widget": dict(WIDGET),
        "document": {"lines": [dict(one) for one in model.lines] if whole else batch},
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
        "light_label_color": list(rgb(LIGHT_LABEL_COLOR)),
        "bank_marker_color": list(rgb(BANK_MARKER_COLOR)),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``status_log.lines``.

    Reads ``messages``, ``notices``, ``paused``, ``toggle`` and ``whole``
    from the request parameters. The pause state persists between calls
    because the pane's own does.
    """
    paused = params.get("paused")
    return build_view_model(
        pane_model(),
        params.get("messages") or [],
        paused=None if paused is None else bool(paused),
        toggle=bool(params.get("toggle", False)),
        notices=params.get("notices") or [],
        whole=bool(params.get("whole", False)),
    )
