"""dashboard_stat_card_surface.py -- the header stat card as plain data.

Describes one card in the main window header: the framed panel, the small
muted caption above, the large accent amount below, the privacy dot that
can be attached under the amount, and the layout numbers that place them.
Colours, paddings and fonts come from ``design_system`` tokens, so a page
carries the values the Qt card paints rather than a second palette.

It also holds the behaviour the card owns rather than describes: the text
one amount renders, the privacy mask that amount passes through, the
re-render a dot toggle triggers, the pointer cursor and appended tooltip a
clickable card gains, and the click that fires the card's one signal.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for the
``dashboard_stat_card.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt, so the same code serves any frontend.
"""

from __future__ import annotations

from typing import Any, Optional

from ...core.privacy_mask_registry import get_privacy_mask_registry, mask_or

from . import header_strip_surface as header, privacy_dot_surface

from .. import design_system as ds

METHOD = "dashboard_stat_card.state"

DEFAULT_VALUE = "---"
EMPTY_TEXT = ""

FRAME_SHAPE = "StyledPanel"
FRAME_LINE_WIDTH_PX = 1

# The theme paints these on QFrame[frameShape="6"]; the page reads no theme
# sheet, so the card carries them.
FRAME_STYLE = (
    "border-style: solid; "
    f"border-width: {FRAME_LINE_WIDTH_PX}px; "
    f"border-color: {ds.OUTLINE}; "
    f"border-radius: {ds.RADIUS_SM}px; "
    f"padding: {ds.SPACE_CARD_PAD}px;"
)

OUTER_MARGINS_PX = (8, 4, 8, 4)
OUTER_SPACING_PX = 2
LABEL_ROW_MARGINS_PX = (0, 0, 0, 0)
LABEL_ROW_SPACING_PX = 4
LABEL_LEADING_STRETCH = True
LABEL_TRAILING_STRETCH = True

LABEL_ALIGN = "hcenter|bottom"
VALUE_ALIGN = "hcenter|top"
DOT_ALIGN = "hcenter"

LABEL_STYLE = f"color: {ds.MAIN_CAPTION}; {header.LABEL_FONT}"
VALUE_STYLE = f"color: {ds.PRIMARY}; {header.VALUE_FONT}"
LABEL_PROPERTY = "muted"
VALUE_PROPERTY = "heading"

CLICKABLE_CURSOR = "PointingHandCursor"
DEFAULT_CURSOR = "ArrowCursor"
TOOLTIP_JOIN = "\n\n"
LEFT_BUTTON = "left"

SIGNAL_NAME = "clicked"
SIGNALS = (SIGNAL_NAME,)

DOT_STYLE = (
    "PrivacyDot { "
    f"  color: {ds.PRIMARY_BRIGHT}; "
    "  background: transparent; "
    "  border: none; "
    "  padding: 0 4px; "
    "  font-size: 14px; "
    "} "
    f"PrivacyDot:hover {{ color: {ds.TEXT_MAX}; }}"
)
DOT_REVEALED_GLYPH = "●"
DOT_MASKED_GLYPH = "○"
DOT_REVEALED_STATE = "REVEALED. Click to mask."
DOT_MASKED_STATE = "MASKED. Click to reveal."

#: The ``dot_view`` fields the card's own dot carries, beside ``align``.
#: ``cursor_shape`` is the pointing hand the Qt ``PrivacyDot`` sets on itself.
_DOT_FIELDS = (
    "field_id",
    "masked",
    "text",
    "tooltip",
    "style_sheet",
    "flat",
    "focus_policy",
    "cursor_shape",
)

ACTIONS: dict = {}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()

VALUE_SET = "value_set"
VALUE_MASKED = "value_masked"
VALUE_PLAIN = "value_plain"
VALUE_REMASKED = "value_remasked"
DOT_ATTACHED = "dot_attached"
DOT_REUSED = "dot_reused"
DOT_TOGGLED = "dot_toggled"
DOT_CLICKED = "dot_clicked"
DOT_REFRESHED = "dot_refreshed"
DOT_REPAINTED = "dot_repainted"
CLICKABLE_ON = "clickable_on"
CLICKABLE_OFF = "clickable_off"
TOOLTIP_APPENDED = "tooltip_appended"
TOOLTIP_KEPT = "tooltip_kept"
CLICK_EMITTED = "click_emitted"
CLICK_IGNORED = "click_ignored"
DEFAULT_HANDLED = "default_handled"

CALL_NAMES = (
    VALUE_SET,
    VALUE_MASKED,
    VALUE_PLAIN,
    VALUE_REMASKED,
    DOT_ATTACHED,
    DOT_REUSED,
    DOT_TOGGLED,
    DOT_CLICKED,
    DOT_REFRESHED,
    DOT_REPAINTED,
    CLICKABLE_ON,
    CLICKABLE_OFF,
    TOOLTIP_APPENDED,
    TOOLTIP_KEPT,
    CLICK_EMITTED,
    CLICK_IGNORED,
    DEFAULT_HANDLED,
)


def built_text(value: Any, part: str) -> str:
    """The text one built part carries, refusing what a label refuses.

    ``None`` builds an empty part. Anything that is not text is refused,
    naming the part and the type it was given, so a caller cannot build a
    card the Qt side would reject.
    """
    if value is None:
        return EMPTY_TEXT
    if not isinstance(value, str):
        raise TypeError(
            f"a stat card {part} is built from text, not {type(value).__name__}"
        )
    return value


def is_masked(field_id: Any) -> bool:
    """Whether the privacy registry currently hides one field."""
    try:
        return bool(get_privacy_mask_registry().is_masked(field_id))
    except Exception:
        return False


def privacy_dot(field_id: Any, masked: Optional[bool] = None) -> dict:
    """``privacy_dot_surface.dot_view`` cut to ``_DOT_FIELDS``, plus ``align``.

    ``DOT_ALIGN`` names where under the amount the dot sits.
    """
    painted = privacy_dot_surface.dot_view(field_id, masked)
    carried = {name: painted[name] for name in _DOT_FIELDS}
    carried["align"] = DOT_ALIGN
    return carried


def label_row_items() -> list:
    """The caption row, item by item, in the order the card adds them."""
    items: list = []
    if LABEL_LEADING_STRETCH:
        items.append({"kind": "stretch"})
    items.append({"kind": "widget", "role": "label"})
    if LABEL_TRAILING_STRETCH:
        items.append({"kind": "stretch"})
    return items


def outer_items(has_dot: bool) -> list:
    """The card column, item by item, in the order the card adds them."""
    items: list = [
        {"kind": "layout", "role": "label_row"},
        {"kind": "widget", "role": "value"},
    ]
    if has_dot:
        items.append({"kind": "widget", "role": "dot", "align": DOT_ALIGN})
    return items


class StatCardModel:
    """One header stat card's state, with no Qt object behind it.

    Holds the caption, the last raw amount so a privacy-dot toggle
    re-renders the same number, the rendered amount, the dot under it, the
    tooltip, the pointer cursor and the clicks the card has emitted.
    """

    def __init__(self, label: Any, value: Any = DEFAULT_VALUE) -> None:
        self.label_text: str = built_text(label, "label")
        self.value_text: str = built_text(value, "value")
        self.raw_value: Any = value
        self.field_id: Any = None
        self.dot: Optional[dict] = None
        self.tooltip: str = EMPTY_TEXT
        self.is_clickable: bool = False
        self.cursor: str = DEFAULT_CURSOR
        self.clicks: int = 0
        self.calls: list = []

    def set_value(self, value: Any) -> None:
        """Render one amount, through the mask when a dot is attached."""
        self.raw_value = str(value)
        self.calls.append(VALUE_SET)
        if self.field_id:
            self.calls.append(VALUE_MASKED)
            self.value_text = mask_or(self.raw_value, self.field_id)
        else:
            self.calls.append(VALUE_PLAIN)
            self.value_text = self.raw_value

    def attach_privacy_dot(self, field_id: Any) -> dict:
        """Put a privacy dot under the amount and render once through it.

        A card that already carries a dot keeps it and keeps the field it
        was first given.
        """
        if self.dot is not None:
            self.calls.append(DOT_REUSED)
            return self.dot
        self.field_id = field_id
        self.calls.append(DOT_ATTACHED)
        self.dot = privacy_dot(field_id)
        self.dot_toggled()
        return self.dot

    def dot_toggled(self) -> None:
        """Re-render the amount from the kept raw value after a toggle."""
        self.calls.append(DOT_TOGGLED)
        if self.field_id:
            self.calls.append(VALUE_REMASKED)
            self.value_text = mask_or(self.raw_value, self.field_id)

    def dot_clicked(self) -> Optional[dict]:
        """The card after its own dot is clicked.

        The dot widget flips the field in the registry and repaints
        itself, then calls back into the card, which re-renders the
        amount. The flip is the dot's, so this reads the registry rather
        than writing it.
        """
        self.calls.append(DOT_CLICKED)
        if self.dot is not None:
            self.dot = privacy_dot(self.field_id)
        self.dot_toggled()
        return self.dot

    def refresh_privacy_dot(self) -> None:
        """Repaint the dot from the registry, then re-render the amount."""
        self.calls.append(DOT_REFRESHED)
        if self.dot is not None:
            self.calls.append(DOT_REPAINTED)
            self.dot = privacy_dot(self.field_id)
        if self.field_id:
            self.calls.append(VALUE_REMASKED)
            self.value_text = mask_or(self.raw_value, self.field_id)

    def set_clickable(self, clickable: Any, tooltip_suffix: Any = "") -> None:
        """Turn click handling on or off and carry the pointer cursor.

        A suffix already inside the tooltip is not appended twice.
        """
        self.is_clickable = bool(clickable)
        if self.is_clickable:
            self.calls.append(CLICKABLE_ON)
            self.cursor = CLICKABLE_CURSOR
            if tooltip_suffix:
                base = self.tooltip or EMPTY_TEXT
                if tooltip_suffix not in base:
                    self.calls.append(TOOLTIP_APPENDED)
                    self.tooltip = (base + TOOLTIP_JOIN + tooltip_suffix).strip()
                else:
                    self.calls.append(TOOLTIP_KEPT)
        else:
            self.calls.append(CLICKABLE_OFF)
            self.cursor = DEFAULT_CURSOR

    def mouse_pressed(self, button: Any) -> None:
        """Fire the card's one signal on a left press of a clickable card.

        The default handling runs on every press, clickable or not.
        """
        if self.is_clickable and button == LEFT_BUTTON:
            self.calls.append(CLICK_EMITTED)
            self.clicks += 1
        else:
            self.calls.append(CLICK_IGNORED)
        self.calls.append(DEFAULT_HANDLED)


def build_view_model(model: StatCardModel) -> dict:
    """Return the whole card state as one serialisable dict."""
    return {
        "frame": {"style_sheet": FRAME_STYLE, "frame_shape": FRAME_SHAPE},
        "layout": {
            "margins_px": list(OUTER_MARGINS_PX),
            "spacing_px": OUTER_SPACING_PX,
            "label_row_margins_px": list(LABEL_ROW_MARGINS_PX),
            "label_row_spacing_px": LABEL_ROW_SPACING_PX,
            "label_leading_stretch": LABEL_LEADING_STRETCH,
            "label_trailing_stretch": LABEL_TRAILING_STRETCH,
            "dot_align": DOT_ALIGN,
        },
        "label": {
            "text": model.label_text,
            "style_sheet": LABEL_STYLE,
            "align": LABEL_ALIGN,
            "property": LABEL_PROPERTY,
        },
        "value": {
            "text": model.value_text,
            "style_sheet": VALUE_STYLE,
            "align": VALUE_ALIGN,
            "property": VALUE_PROPERTY,
            "default_text": DEFAULT_VALUE,
        },
        "dot": model.dot,
        "items": outer_items(model.dot is not None),
        "label_row_items": label_row_items(),
        "tooltip": model.tooltip,
        "clickable": {
            "is_clickable": model.is_clickable,
            "cursor": model.cursor,
            "tooltip_join": TOOLTIP_JOIN,
            "button": LEFT_BUTTON,
        },
        "privacy": {"field_id": model.field_id, "raw_value": model.raw_value},
        "signals": list(SIGNALS),
        "clicks": model.clicks,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "method": METHOD,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``dashboard_stat_card.state``.

    Builds one card from ``label`` and ``value``, attaches a dot when the
    request names a ``field_id``, turns clicking on when it asks, and
    repaints the dot when it asks.
    """
    asked = params or {}
    card = StatCardModel(asked.get("label"), asked.get("value", DEFAULT_VALUE))
    field_id = asked.get("field_id")
    if field_id is not None:
        card.attach_privacy_dot(field_id)
    if asked.get("clickable"):
        card.set_clickable(True, asked.get("tooltip_suffix", ""))
    if asked.get("refresh_dot"):
        card.refresh_privacy_dot()
    return build_view_model(card)
