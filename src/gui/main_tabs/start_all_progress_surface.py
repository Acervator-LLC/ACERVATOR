"""start_all_progress_surface.py -- the Start All progress view model.

Describes the dialog the staggered bulk start puts on screen as plain
data: the window, its skin, the headline, the fixed explanatory line,
the list of bot lines and the two buttons. Colours come from
``design_system`` tokens, so a page carries the values the Qt dialog
paints rather than a second palette.

It also holds the state the dialog owns rather than describes: the
headline text, the bot lines already listed, which button is enabled,
and the ordered calls each progress event makes. Six phases drive it --
``begin``, ``bot_starting``, ``bot_started``, ``bot_timeout``, ``done``
and ``cancelled`` -- and a phase the surface does not name changes
nothing.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``start_all_progress.state`` method, which is how the Electron
renderer reaches it. Nothing here imports Qt, and it sits beside the
other surfaces rather than beside ``start_all_progress_dialog.py``
because that module imports Qt at the top.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional

from .. import design_system as ds

logger = logging.getLogger("acervator.gui.start_all")

METHOD = "start_all_progress.state"

TOPIC = "bot_manager.start_all_progress"

ACCESSIBLE_NAME = "Start All Progress Dialog"
WINDOW_TITLE = "Auto-starting bots"
MODAL = False
MINIMUM_WIDTH_PX = 420
SIZE_PX = (520, 360)

STYLE_SHEET = (
    f"QDialog {{ background: {ds.MAIN_TOOLBAR_SURFACE}; color: {ds.TEXT_CONSOLE}; }}"
    f"QLabel {{ color: {ds.TEXT_CONSOLE}; font-family: Consolas; font-size: 11px; }}"
    f"QListWidget {{ background: {ds.SURFACE_CHART}; color: {ds.TEXT_CONSOLE}; "
    f"border: 1px solid {ds.MAIN_SEPARATOR}; font-family: Consolas; font-size: 10px; }}"
    f"QPushButton {{ background: {ds.MAIN_BUTTON_SURFACE}; color: {ds.TEXT_CONSOLE}; "
    f"border: 1px solid {ds.MAIN_BUTTON_BORDER}; padding: 6px 18px; "
    "font-family: Consolas; font-size: 10px; }"
    f"QPushButton:hover {{ background: {ds.MAIN_BUTTON_HOVER}; }}"
    f"QPushButton:disabled {{ color: {ds.TEXT_PLACEHOLDER}; "
    f"border-color: {ds.MAIN_SEPARATOR}; }}"
)

SUBLINE_STYLE = f"color: {ds.CARD_METRIC_LABEL};"

DIALOG_SURFACE = ds.MAIN_TOOLBAR_SURFACE
TEXT_COLOR = ds.TEXT_CONSOLE
LIST_SURFACE = ds.SURFACE_CHART
LIST_BORDER = ds.MAIN_SEPARATOR
BUTTON_SURFACE = ds.MAIN_BUTTON_SURFACE
BUTTON_BORDER = ds.MAIN_BUTTON_BORDER
BUTTON_HOVER = ds.MAIN_BUTTON_HOVER
DISABLED_TEXT = ds.TEXT_PLACEHOLDER
SUBLINE_COLOR = ds.CARD_METRIC_LABEL

WIDGET = {
    "accessible_name": ACCESSIBLE_NAME,
    "window_title": WINDOW_TITLE,
    "modal": MODAL,
    "minimum_width_px": MINIMUM_WIDTH_PX,
    "size_px": list(SIZE_PX),
    "style_sheet": STYLE_SHEET,
}

LAYOUT = {
    "margins_px": [14, 14, 14, 14],
    "spacing_px": 10,
    "order": ["headline", "subline", "list", "button_row"],
    "child_stretch": [0, 0, 1, 0],
}

BUTTON_ROW = {
    "margins_px": [0, 0, 0, 0],
    "order": ["stretch", "cancel", "close"],
    "leading_stretch": 1,
}

HEADLINE_INITIAL_TEXT = "Preparing to auto-start bots..."
HEADLINE_POINT_SIZE = 12
HEADLINE_BOLD = True

SUBLINE_TEXT = (
    "Bots are started one at a time with a ~2.5-second pause "
    "between each (verify-then-next + a 2s minimum gap so the "
    "per-exchange CCXT call queue has time to drain). Click "
    "Cancel to abort the remaining bots — bots already started "
    "will keep running."
)
SUBLINE_WORD_WRAP = True

CANCEL_TEXT = "Cancel remaining"
CLOSE_TEXT = "Close"
CANCEL_ENABLED_AT_START = True
CLOSE_ENABLED_AT_START = False

HEADLINE = {
    "initial_text": HEADLINE_INITIAL_TEXT,
    "point_size": HEADLINE_POINT_SIZE,
    "bold": HEADLINE_BOLD,
}

SUBLINE = {
    "text": SUBLINE_TEXT,
    "word_wrap": SUBLINE_WORD_WRAP,
    "style_sheet": SUBLINE_STYLE,
}

BUTTONS = {
    "cancel": {"text": CANCEL_TEXT, "enabled": CANCEL_ENABLED_AT_START},
    "close": {"text": CLOSE_TEXT, "enabled": CLOSE_ENABLED_AT_START},
}

ACTIONS = {
    "cancel.clicked": "cancel",
    "close.clicked": "accept",
    "progress.received": "handle_progress",
}

BEGIN = "begin"
BOT_STARTING = "bot_starting"
BOT_STARTED = "bot_started"
BOT_TIMEOUT = "bot_timeout"
DONE = "done"
CANCELLED = "cancelled"

PHASES = (BEGIN, BOT_STARTING, BOT_STARTED, BOT_TIMEOUT, DONE, CANCELLED)

EVENT_FIELDS = ("phase", "total", "started", "bot_id")

HEADLINE_NO_BOTS = "No bots to auto-start."
HEADLINE_BEGIN = "Auto-starting {total} bots (0/{total} verified)"
HEADLINE_BOT_STARTING = (
    "Auto-starting {total} bots ({started}/{total} verified, starting {bot_id}...)"
)
HEADLINE_BOT_STARTED = "Auto-starting {total} bots ({started}/{total} verified)"
HEADLINE_DONE = "Done — {total} bot(s) processed."
HEADLINE_CANCELLED = "Cancelled — {started}/{total} bots had started."
HEADLINE_CANCELLING = "Cancelling..."
HEADLINE_CANCEL_FAILED = "Cancel FAILED — bots may still be starting"

ITEM_BOT_STARTING = "⏳ {bot_id} (starting...)"
ITEM_BOT_STARTED = "✓ {bot_id}"
ITEM_BOT_TIMEOUT = "⚠ {bot_id} (start verify timed out — may still come up)"

NO_BOTS_CLOSE_DELAY_MS = 800
DONE_CLOSE_DELAY_MS = 2000

HEADLINE_SET_TEXT = "headline.setText"
LIST_CLEAR = "list.clear"
LIST_ADD_ITEM = "list.addItem"
LIST_COUNT = "list.count"
LIST_ITEM = "list.item"
LIST_SET_ITEM_TEXT = "list.setItemText"
LIST_SCROLL_TO_BOTTOM = "list.scrollToBottom"
CANCEL_SET_ENABLED = "cancel.setEnabled"
CLOSE_SET_ENABLED = "close.setEnabled"
CLOSE_AFTER = "closeAfter"

EVENT_DROPPED_LOG = "Start All progress event dropped (%s): %s"
CANCEL_FAILED_LOG = "cancel_start_all failed: %s"
UNSUBSCRIBE_FAILED_LOG = "Start All progress unsubscribe failed, handler leaked: %s"

CANCEL_REFUSED = "cancel_start_all refused"
UNSUBSCRIBE_REFUSED = "unsubscribe refused"

DialogCall = list[object]


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


def progress_fields(data: Any) -> Optional[tuple]:
    """The four fields one progress event carries, or None when it fails.

    A missing field falls back to the dialog's own default, and a bot id
    of None reads as the empty string. An event the surface cannot read
    is logged and dropped rather than raised, because the bus delivers it
    on the thread that emitted it.
    """
    try:
        phase = data.get("phase", "")
        total = int(data.get("total", 0))
        started = int(data.get("started", 0))
        bot_id = str(data.get("bot_id", "") or "")
    except (AttributeError, TypeError, ValueError) as exc:
        logger.exception(EVENT_DROPPED_LOG, type(exc).__name__, exc)
        return None
    return (phase, total, started, bot_id)


def unsubscribe(unsubscriber: Any) -> None:
    """Drop this dialog's handler off the bus when the window closes.

    A failed unsubscribe leaks the handler for the process lifetime, so
    it is logged; the close still proceeds, because a window that cannot
    be closed is worse than a leaked handler.
    """
    try:
        if unsubscriber and callable(unsubscriber):
            unsubscriber()
    except Exception as exc:
        logger.exception(UNSUBSCRIBE_FAILED_LOG, exc)


class CancelSource:
    """Stands in for ``BotManager`` when the cancel outcome arrives as data.

    Carries the one method the Cancel button calls, so the headline is
    chosen by the same path whether the press reaches the live manager or
    a request.
    """

    def __init__(self, refuses: bool = False) -> None:
        self.refuses = refuses

    def cancel_start_all(self) -> None:
        if self.refuses:
            raise RuntimeError(CANCEL_REFUSED)


def unsubscriber_for(refuses: bool) -> Callable[[], None]:
    """Stands in for the bus unsubscribe callable when its outcome is data."""

    def drop_handler() -> None:
        if refuses:
            raise RuntimeError(UNSUBSCRIBE_REFUSED)

    return drop_handler


class StartAllProgressModel:
    """The Start All dialog's headline, bot lines and two buttons.

    ``handle_progress`` advances the dialog through one progress event.
    Every change it makes is also appended to ``calls`` in the order the
    Qt dialog makes it, so a caller can replay the same sequence on a
    widget it owns.
    """

    def __init__(self) -> None:
        self.headline = HEADLINE_INITIAL_TEXT
        self.items: list[str] = []
        self.cancel_enabled = CANCEL_ENABLED_AT_START
        self.close_enabled = CLOSE_ENABLED_AT_START
        self.calls: list[DialogCall] = []

    def set_headline(self, text: str) -> None:
        self.headline = text
        self.calls.append([HEADLINE_SET_TEXT, text])

    def clear_items(self) -> None:
        self.items = []
        self.calls.append([LIST_CLEAR])

    def add_item(self, text: str) -> None:
        self.items.append(text)
        self.calls.append([LIST_ADD_ITEM, text])

    def item_count(self) -> int:
        self.calls.append([LIST_COUNT])
        return len(self.items)

    def item_text(self, row: int) -> Optional[str]:
        self.calls.append([LIST_ITEM, row])
        return self.items[row]

    def set_item_text(self, row: int, text: str) -> None:
        self.items[row] = text
        self.calls.append([LIST_SET_ITEM_TEXT, row, text])

    def scroll_to_bottom(self) -> None:
        self.calls.append([LIST_SCROLL_TO_BOTTOM])

    def set_cancel_enabled(self, enabled: bool) -> None:
        self.cancel_enabled = enabled
        self.calls.append([CANCEL_SET_ENABLED, enabled])

    def set_close_enabled(self, enabled: bool) -> None:
        self.close_enabled = enabled
        self.calls.append([CLOSE_SET_ENABLED, enabled])

    def close_after(self, delay_ms: int) -> None:
        self.calls.append([CLOSE_AFTER, delay_ms])

    def replace_last_matching(self, bot_id: str, new_text: str) -> None:
        """Rewrite the newest line carrying ``bot_id``, or add one.

        The match is a substring of the whole line, so a bot id that
        reads inside a longer id claims that longer line. A bot with no
        line yet gains one instead of being lost.
        """
        for row in range(self.item_count() - 1, -1, -1):
            text = self.item_text(row)
            if text is None:
                continue
            if bot_id in text:
                self.set_item_text(row, new_text)
                self.scroll_to_bottom()
                return
        self.add_item(new_text)
        self.scroll_to_bottom()

    def handle_progress(
        self, phase: str, total: int, started: int, bot_id: str
    ) -> None:
        """Advance the dialog through one progress event.

        ``begin`` with a total of zero says so in the headline, enables
        Close and asks to be dismissed, because there is nothing to
        watch. ``bot_timeout`` leaves the headline alone and marks only
        the line. A phase the surface does not name changes nothing.
        """
        if phase == BEGIN:
            if total == 0:
                self.set_headline(HEADLINE_NO_BOTS)
                self.set_cancel_enabled(False)
                self.set_close_enabled(True)
                self.close_after(NO_BOTS_CLOSE_DELAY_MS)
                return
            self.set_headline(HEADLINE_BEGIN.format(total=total))
            self.clear_items()
        elif phase == BOT_STARTING:
            self.set_headline(
                HEADLINE_BOT_STARTING.format(
                    total=total, started=started, bot_id=bot_id
                )
            )
            if bot_id:
                self.add_item(ITEM_BOT_STARTING.format(bot_id=bot_id))
                self.scroll_to_bottom()
        elif phase == BOT_STARTED:
            self.set_headline(HEADLINE_BOT_STARTED.format(total=total, started=started))
            if bot_id:
                self.replace_last_matching(
                    bot_id, ITEM_BOT_STARTED.format(bot_id=bot_id)
                )
        elif phase == BOT_TIMEOUT:
            if bot_id:
                self.replace_last_matching(
                    bot_id, ITEM_BOT_TIMEOUT.format(bot_id=bot_id)
                )
        elif phase == DONE:
            self.set_headline(HEADLINE_DONE.format(total=total))
            self.set_cancel_enabled(False)
            self.set_close_enabled(True)
            self.close_after(DONE_CLOSE_DELAY_MS)
        elif phase == CANCELLED:
            self.set_headline(HEADLINE_CANCELLED.format(started=started, total=total))
            self.set_cancel_enabled(False)
            self.set_close_enabled(True)

    def cancel(self, bot_manager: Any) -> None:
        """Press Cancel: ask the manager to stop, then say what happened.

        A manager that refuses leaves Cancel disabled under a headline
        naming the failure, because a dialog reading "Cancelling..."
        while bots keep starting tells the operator the opposite of what
        is happening.
        """
        try:
            bot_manager.cancel_start_all()
        except Exception as exc:
            logger.exception(CANCEL_FAILED_LOG, exc)
            self.set_headline(HEADLINE_CANCEL_FAILED)
            self.set_cancel_enabled(False)
            return
        self.set_cancel_enabled(False)
        self.set_headline(HEADLINE_CANCELLING)


PANE_MODEL = StartAllProgressModel()


def build_view_model(
    model: StartAllProgressModel,
    events: Optional[Iterable[Any]] = None,
    cancel: bool = False,
    bot_manager: Any = None,
    close: bool = False,
    unsubscriber: Any = None,
) -> dict:
    """Return the whole surface state as one serialisable dict.

    The events are applied in order, then the Cancel press, then the
    close. An event the surface cannot read is dropped and the rest are
    still applied, so one bad event cannot lose the run.
    """
    for entry in events or ():
        fields = progress_fields(entry)
        if fields is not None:
            model.handle_progress(*fields)
    if cancel:
        model.cancel(bot_manager)
    if close:
        unsubscribe(unsubscriber)
    return {
        "widget": dict(WIDGET),
        "layout": dict(LAYOUT),
        "button_row": dict(BUTTON_ROW),
        "headline": dict(HEADLINE),
        "subline": dict(SUBLINE),
        "buttons": {name: dict(spec) for name, spec in BUTTONS.items()},
        "actions": dict(ACTIONS),
        "topic": TOPIC,
        "phases": list(PHASES),
        "event_fields": list(EVENT_FIELDS),
        "headline_text": model.headline,
        "items": list(model.items),
        "item_count": len(model.items),
        "cancel_enabled": model.cancel_enabled,
        "close_enabled": model.close_enabled,
        "calls": [list(call) for call in model.calls],
        "dialog_surface": list(rgb(DIALOG_SURFACE)),
        "text_color": list(rgb(TEXT_COLOR)),
        "list_surface": list(rgb(LIST_SURFACE)),
        "list_border": list(rgb(LIST_BORDER)),
        "button_surface": list(rgb(BUTTON_SURFACE)),
        "button_border": list(rgb(BUTTON_BORDER)),
        "button_hover": list(rgb(BUTTON_HOVER)),
        "disabled_text": list(rgb(DISABLED_TEXT)),
        "subline_color": list(rgb(SUBLINE_COLOR)),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``start_all_progress.state``.

    Reads ``reset``, ``events``, ``cancel``, ``cancel_refused``,
    ``close`` and ``unsubscribe_refused`` from the request parameters.
    The headline, the bot lines and the button states persist between
    calls because the dialog's own do; ``reset`` is what a fresh Start
    All sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = StartAllProgressModel()
    return build_view_model(
        PANE_MODEL,
        params.get("events"),
        cancel=bool(params.get("cancel", False)),
        bot_manager=CancelSource(bool(params.get("cancel_refused", False))),
        close=bool(params.get("close", False)),
        unsubscriber=unsubscriber_for(bool(params.get("unsubscribe_refused", False))),
    )
