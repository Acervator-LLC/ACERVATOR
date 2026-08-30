"""privacy_dot_surface.py -- the per-field privacy dot as plain data.

Describes the small clickable dot the dashboard puts under every masked
amount: the glyph it paints, the tooltip it carries, the skin it wears and
the flat, focus-free, pointing-hand button it is. Colours come from
``design_system`` tokens, so a page carries the values the Qt dot paints
rather than a second palette.

It also holds the behaviour the dot owns rather than describes: the mask it
flips in the process privacy registry on a click, the repaint that follows,
the callback it runs afterwards, and the two failures it swallows -- a
registry that cannot answer, and a callback that raises.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for the
``privacy_dot.state`` method, which is how the Electron renderer reaches it.
Nothing here imports Qt, so the same code serves any frontend.
"""

from __future__ import annotations

from typing import Any, Optional

from ...core.privacy_mask_registry import get_privacy_mask_registry

from .. import design_system as ds

METHOD = "privacy_dot.state"

DEFAULT_FIELD_ID = "kpi.spendable"

REVEALED_GLYPH = "●"
MASKED_GLYPH = "○"
REVEALED_STATE = "REVEALED. Click to mask."
MASKED_STATE = "MASKED. Click to reveal."
TOOLTIP_SEPARATOR = ": "

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

FLAT = True
FOCUS_POLICY = "NoFocus"
CURSOR_SHAPE = "PointingHandCursor"

ACTIONS = {"clicked": "clicked"}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()

BUILT = "built"
CLICKED = "clicked"
TOGGLE_FAILED = "toggle_failed"
REFRESHED = "refreshed"
REGISTRY_UNREADABLE = "registry_unreadable"
CALLBACK_RAN = "callback_ran"
CALLBACK_FAILED = "callback_failed"
CALLBACK_SKIPPED = "callback_skipped"

CALL_NAMES = (
    BUILT,
    CLICKED,
    TOGGLE_FAILED,
    REFRESHED,
    REGISTRY_UNREADABLE,
    CALLBACK_RAN,
    CALLBACK_FAILED,
    CALLBACK_SKIPPED,
)


def glyph(masked: bool) -> str:
    """The character the dot paints for one mask state."""
    return MASKED_GLYPH if masked else REVEALED_GLYPH


def state_text(masked: bool) -> str:
    """The words the tooltip carries for one mask state."""
    return MASKED_STATE if masked else REVEALED_STATE


def tooltip(field_id: Any, masked: bool) -> str:
    """The whole tooltip one field's dot carries."""
    return f"{field_id}{TOOLTIP_SEPARATOR}{state_text(masked)}"


def read_mask(field_id: Any) -> bool:
    """Whether the privacy registry currently hides one field.

    A registry that cannot answer reads as revealed, so a repaint never
    fails on a field id the registry refuses.
    """
    try:
        return bool(get_privacy_mask_registry().is_masked(field_id))
    except Exception:
        return False


def dot_view(field_id: Any, masked: Optional[bool] = None) -> dict:
    """The glyph, tooltip and skin one field's dot carries.

    ``masked`` given reads as the state to render; left out, the process
    privacy registry decides.
    """
    hidden = read_mask(field_id) if masked is None else bool(masked)
    return {
        "field_id": field_id,
        "masked": hidden,
        "text": glyph(hidden),
        "tooltip": tooltip(field_id, hidden),
        "style_sheet": DOT_STYLE,
        "flat": FLAT,
        "focus_policy": FOCUS_POLICY,
        "cursor_shape": CURSOR_SHAPE,
    }


class PrivacyDotModel:
    """One dot's state, with no Qt object behind it.

    Holds the field it toggles, the callback its owner runs after a click,
    the painted glyph, tooltip and skin, and the branch markers of every
    path taken so far.
    """

    def __init__(self, field_id: Any, on_toggle=None) -> None:
        self._field_id = field_id
        self._on_toggle = on_toggle
        self.calls: list = [BUILT]
        self.masked = False
        self.text = ""
        self.tooltip = ""
        self.style_sheet = DOT_STYLE
        self.flat = FLAT
        self.focus_policy = FOCUS_POLICY
        self.cursor_shape = CURSOR_SHAPE
        self.refresh()

    def field_id(self) -> Any:
        """The field this dot masks and reveals."""
        return self._field_id

    def clicked(self) -> None:
        """Flip the field's mask, repaint, then run the owner's callback.

        A registry that refuses the field leaves the mask untouched, and a
        callback that raises is swallowed, so neither can stop the repaint.
        """
        self.calls.append(CLICKED)
        try:
            registry = get_privacy_mask_registry()
            registry.set_masked(self._field_id, not registry.is_masked(self._field_id))
        except Exception:
            self.calls.append(TOGGLE_FAILED)
        self.refresh()
        if callable(self._on_toggle):
            try:
                self._on_toggle()
                self.calls.append(CALLBACK_RAN)
            except Exception:
                self.calls.append(CALLBACK_FAILED)
        else:
            self.calls.append(CALLBACK_SKIPPED)

    def refresh(self) -> None:
        """Repaint the glyph, tooltip and skin from the registry."""
        self.calls.append(REFRESHED)
        try:
            hidden = bool(get_privacy_mask_registry().is_masked(self._field_id))
        except Exception:
            self.calls.append(REGISTRY_UNREADABLE)
            hidden = False
        painted = glyph(hidden)
        tip = tooltip(self._field_id, hidden)
        self.masked = hidden
        self.text = painted
        self.style_sheet = DOT_STYLE
        self.tooltip = tip


def build_view_model(model: Optional[PrivacyDotModel] = None) -> dict:
    """Return the whole dot state as one serialisable dict."""
    state = PrivacyDotModel(DEFAULT_FIELD_ID) if model is None else model
    return {
        "field_id": state.field_id(),
        "masked": state.masked,
        "text": state.text,
        "tooltip": state.tooltip,
        "style_sheet": state.style_sheet,
        "flat": state.flat,
        "focus_policy": state.focus_policy,
        "cursor_shape": state.cursor_shape,
        "glyphs": {"revealed": REVEALED_GLYPH, "masked": MASKED_GLYPH},
        "states": {"revealed": REVEALED_STATE, "masked": MASKED_STATE},
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "calls": list(state.calls),
        "method": METHOD,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``privacy_dot.state``.

    Builds a dot for the field under ``field_id``, clicks it as many times
    as ``clicks`` asks, and repaints it when ``refresh`` is asked for.
    """
    asked = params or {}
    field_id = asked.get("field_id", DEFAULT_FIELD_ID)
    state = PrivacyDotModel(field_id)
    for _ in range(int(asked.get("clicks", 0) or 0)):
        state.clicked()
    if asked.get("refresh"):
        state.refresh()
    return build_view_model(state)
