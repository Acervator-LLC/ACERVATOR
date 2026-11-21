"""Activity Log line styles and ``StatusLogModel`` state, served to the bridge as
``METHOD`` by ``view_model``."""

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

BOT_TAG_PATTERN = re.compile(r"^\[[^\[\]]*\]\s+")

ROLE_GLYPHS = {
    SIDE_ROLES[SELL_SIDE]: READOUT_SELL_GLYPH,
    SIDE_ROLES[BUY_SIDE]: READOUT_BUY_GLYPH,
}
GLYPH_FORMAT = "{glyph} "

TRADE_FIELD_SPLIT = ": "
TRADE_FIELD_COUNT = 3
TRADE_STAGE_SPLIT = " "
TRADE_TEXT_FORMAT = "{stage} [{role}] {symbol}"

TRADE_FONT_SIZE_PX = 14
WIRE_FONT_SIZE_PX = 12

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
    ("REFUSED", ds.ERROR),
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

KIND_TRADE = LINE_KIND_TRADE
KIND_WIRE_FLOW = LINE_KIND_WIRE_FLOW
KIND_WIRE_STACK = LINE_KIND_WIRE_STACK
KIND_PLAIN = "plain"
KIND_RESUME = "resume"

KIND_MARKERS = (
    (KIND_TRADE, (TRADE_PREFIX,)),
    (KIND_WIRE_FLOW, WIRE_FLOW_PREFIXES),
    (KIND_WIRE_STACK, (WIRE_STACK_PREFIX,)),
)
NO_KIND = ""

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
    """Split ``hex_color``, ``#rgb`` or ``#rrggbb``, into three 0-255 channels."""
    digits = hex_color.lstrip("#")
    if len(digits) == 3:
        digits = "".join(digit * 2 for digit in digits)
    return (
        int(digits[0:2], 16),
        int(digits[2:4], 16),
        int(digits[4:6], 16),
    )


def now_seconds() -> float:
    """Return ``time.time``, the default ``StatusLogModel`` clock."""
    return time.time()


def timestamp(now: Optional[datetime] = None) -> str:
    """Format ``now``, or the current time, with ``TIMESTAMP_FORMAT``."""
    return (datetime.now() if now is None else now).strftime(TIMESTAMP_FORMAT)


def stage_color(message: str) -> str:
    """Return the first ``STAGE_COLORS`` colour whose stage ``message`` names, else
    ``STAGE_DEFAULT_COLOR``."""
    for stage, token in STAGE_COLORS:
        if stage in message:
            return token
    return STAGE_DEFAULT_COLOR


def level_color(level: Any) -> str:
    """Return ``level``'s ``LEVEL_COLORS`` colour, else ``DEFAULT_LEVEL_COLOR``."""
    return LEVEL_COLORS.get(level, DEFAULT_LEVEL_COLOR)


def bot_tag(message: str) -> str:
    """Return the ``[TICKER/last4] `` tag ``BOT_TAG_PATTERN`` matches opening
    ``message``, or an empty string."""
    found = BOT_TAG_PATTERN.match(message)
    return found.group(0) if found else ""


def shape_source(message: str) -> str:
    """Return ``message`` without its leading ``bot_tag``."""
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


def trade_text(shaped: str) -> tuple[str, str]:
    """Return the ``TRADE_TEXT_FORMAT`` text and role of a ``TRADE_PREFIX`` line with
    ``TRADE_FIELD_COUNT`` fields, else ``shaped`` and an empty role."""
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
    """Return the arguments as one line's style dict, copying each of ``lights``."""
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


def line_style(
    message: str,
    level: Any = DEFAULT_LOG_LEVEL,
    kind: Optional[str] = None,
    lights: Optional[list] = None,
) -> dict:
    """Return the trade or wire style ``kind`` names for ``message``, else the
    ``level_color`` style with ``lights``."""
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
    """Return ``stamp`` in ``STAMP_FORMAT``, or ``NOTICE_STAMP`` when empty."""
    return STAMP_FORMAT.format(stamp=stamp) if stamp else NOTICE_STAMP


def stamp_html(stamp: str) -> str:
    """Return ``stamp_text`` of ``stamp`` in a ``TIMESTAMP_COLOR`` span."""
    return f'<span style="color:{TIMESTAMP_COLOR}">{stamp_text(stamp)}</span> '


def body_html(style: dict) -> str:
    """Return one ``style`` span of the escaped tag, the bullet, the escaped text and
    ``lights_html``."""
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
    """Return ``light``'s escaped label, then ``LIGHT_DOT_TEXT`` on its colour."""
    label = html.escape(str(light.get("label", "")), quote=False)
    tone = str(light.get("color", "") or "")
    return (
        f'<span style="color:{LIGHT_LABEL_COLOR}">{label}</span>'
        f'<span style="background-color:{tone}">{LIGHT_DOT_TEXT}</span>'
    )


def bank_marker_html(bank: str) -> str:
    """Return the escaped ``bank`` name in ``BANK_MARKER_COLOR``."""
    marked = html.escape(str(bank), quote=False)
    return f'<span style="color:{BANK_MARKER_COLOR}">{marked}</span>'


def lights_html(lights: Optional[list]) -> str:
    """Return ``light_html`` of each of ``lights`` in order, each bank closed by
    ``bank_marker_html``, joined by ``LIGHT_SEPARATOR``."""
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


def line_html(stamp: str, style: dict) -> str:
    """Return ``stamp_html`` of ``stamp`` followed by ``body_html`` of ``style``."""
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
    """Return the italic ``KIND_RESUME`` line naming ``buffered_count`` held lines,
    stamped ``RESUME_STAMP``."""
    text = f"(resumed — {buffered_count} buffered message(s) above)"
    style = style_of(KIND_RESUME, "", text, RESUME_MARKER_COLOR, italic=True)
    return painted_line(RESUME_STAMP, None, style)


def notice_line(text: str) -> dict:
    """Return ``text`` as an unstamped ``KIND_PLAIN`` line in the default colour."""
    style = style_of(KIND_PLAIN, "", str(text), DEFAULT_LEVEL_COLOR)
    return painted_line(NOTICE_STAMP, None, style)


class StatusLogModel:
    """The Activity Log's ``lines`` up to ``max_blocks``, its ``pause_buffer`` and its
    render counters."""

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
        """Set ``paused`` false, ``render`` each held line with its own stamp, then
        ``append`` a ``resume_line`` if any."""
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
        """Stamp ``message``, then ``render`` it, or while ``paused`` hold it in
        ``pause_buffer`` up to ``pause_buffer_cap``."""
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
        """Stamp and ``render`` ``message`` even while ``paused``."""
        self.render(timestamp(now), message, level, kind, lights)

    def append_text(self, text: str) -> None:
        """Paint one unstamped line through ``notice_line``, whatever ``paused``
        holds."""
        self.append(notice_line(text))
        self.scroll_to_end()
        self.last_render_time = self.clock()
        self.total_renders += 1

    def health_stats(self) -> dict:
        """Return ``paused``, the ``pause_buffer`` size, the render counters and
        ``document_blocks`` as one dict."""
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
        """Return the number of ``lines``, never below one."""
        return max(1, len(self.lines))

    def render(
        self,
        stamp: str,
        message: str,
        level: Any = DEFAULT_LOG_LEVEL,
        kind: Optional[str] = None,
        lights: Optional[list] = None,
    ) -> None:
        """Call ``render_line``, then count it in ``total_renders``, or an exception in
        ``render_errors`` and ``logger``."""
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
        """Pass ``build_line``'s line to ``append``, then ``scroll_to_end``."""
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
    """Return ``PANE_MODEL``, the one ``StatusLogModel`` kept between calls, built on
    the first call."""
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = StatusLogModel()
    return PANE_MODEL


def build_view_model(
    model: StatusLogModel,
    messages: Optional[list] = None,
    paused: Optional[bool] = None,
    toggle: bool = False,
    notices: Optional[list] = None,
    whole: bool = False,
) -> dict:
    """Apply ``toggle``, ``paused``, ``messages`` and ``notices`` to ``model``, then
    return its state as one dict."""
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
    """Handle ``METHOD`` by passing ``params`` to ``build_view_model`` on
    ``pane_model``."""
    paused = params.get("paused")
    return build_view_model(
        pane_model(),
        params.get("messages") or [],
        paused=None if paused is None else bool(paused),
        toggle=bool(params.get("toggle", False)),
        notices=params.get("notices") or [],
        whole=bool(params.get("whole", False)),
    )
