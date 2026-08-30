"""spendable_profits_surface.py -- the spendable-profits strip as plain data.

Describes the strip under the main window header: the framed panel, its
five stat columns, the thin separator between them, the privacy dot under
every amount and the layout numbers that place them. Colours, paddings and
fonts come from ``design_system`` tokens, so a page carries the values the
Qt strip paints rather than a second palette.

It also holds the behaviour the strip owns rather than describes: the money
and count text each cell renders, the privacy mask every amount passes
through, the muted skin and tooltip an unknown amount gains, the colour a
negative amount takes, and the re-render a dot toggle triggers.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for the
``spendable_profits.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt, so the same code serves any frontend.
"""

from __future__ import annotations

from typing import Any, Optional

from ...core.privacy_mask_registry import get_privacy_mask_registry, mask_or

from .. import design_system as ds

METHOD = "spendable_profits.state"

EMPTY_TEXT = "—"
MONEY_PREFIX = "$"
MONEY_FORMAT = ",.2f"

FRAME_SHAPE = "StyledPanel"
FRAME_STYLE = (
    "SpendableProfitsWidget { "
    "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
    "    stop:0 rgba(0,40,30,200), stop:1 rgba(0,60,45,200)); "
    "  border: 1px solid rgba(0,255,180,80); border-radius: 4px; }"
)

OUTER_MARGINS_PX = (12, 6, 12, 6)
OUTER_SPACING_PX = 0
COLUMN_MARGINS_PX = (0, 0, 0, 0)
COLUMN_SPACING_PX = 2
SEPARATOR_GAP_PX = 14
DOT_ALIGN = "hcenter"
SEPARATOR_ALIGN = "vcenter"
TRAILING_STRETCH = True

LABEL_STYLE = (
    f"color: {ds.CARD_METRIC_LABEL}; font-size: 10px; "
    "letter-spacing: 1px; font-weight: 600;"
)
SPENDABLE_LABEL_STYLE = (
    f"color: {ds.PRIMARY}; font-size: 10px; letter-spacing: 1px; " "font-weight: 700;"
)
VALUE_STYLE_DEFAULT = f"color: {ds.TEXT_NEUTRAL}; font-size: 16px; font-weight: bold;"
VALUE_STYLE_HIGHLIGHT = f"color: {ds.SUCCESS}; font-size: 16px; font-weight: bold;"
VALUE_STYLE_NEGATIVE = f"color: {ds.ERROR}; font-size: 16px; font-weight: bold;"
VALUE_STYLE_MUTED = (
    f"color: {ds.CARD_METRIC_LABEL}; font-size: 16px; font-weight: bold;"
)
SEPARATOR_STYLE = f"color: {ds.MAIN_SEPARATOR}; font-size: 24px; margin: 0 2px;"

SEPARATOR_TEXT = "|"

SPENDABLE_TOOLTIP = (
    "Estimated expendable liquidity from positions filled 30+ days.\n"
    "Passive income safely withdrawable without disrupting positions."
)
SPENDABLE_UNKNOWN_TOOLTIP = (
    "Spendable amount is not derivable from current data "
    "sources. Requires exchange-pulled position-age data "
    "(see P0a in NEXT_SESSION_ORDERS.md)."
)
SPENDABLE_INITIAL_TEXT = "$0.00"

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

REALISED_DEFAULT = 0
EXCHANGE_COUNT_DEFAULT = 0

COLUMNS = (
    {
        "key": "spendable",
        "label": "SPENDABLE",
        "label_style": SPENDABLE_LABEL_STYLE,
        "label_tooltip": SPENDABLE_TOOLTIP,
        "field_id": "kpi.spendable",
        "source_key": "spendable",
        "default": None,
        "initial_text": SPENDABLE_INITIAL_TEXT,
        "initial_style": VALUE_STYLE_HIGHLIGHT,
    },
    {
        "key": "total_realised",
        "label": "REALISED",
        "label_style": LABEL_STYLE,
        "label_tooltip": "",
        "field_id": "kpi.realised",
        "source_key": "total_realised",
        "default": REALISED_DEFAULT,
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
    },
    {
        "key": "locked",
        "label": "LOCKED",
        "label_style": LABEL_STYLE,
        "label_tooltip": "",
        "field_id": "kpi.locked",
        "source_key": "locked",
        "default": None,
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
    },
    {
        "key": "mature",
        "label": "MATURE",
        "label_style": LABEL_STYLE,
        "label_tooltip": "",
        "field_id": "kpi.mature",
        "source_key": "mature",
        "default": None,
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
    },
    {
        "key": "exchanges",
        "label": "EXCH",
        "label_style": LABEL_STYLE,
        "label_tooltip": "",
        "field_id": "kpi.exch",
        "source_key": "exchange_count",
        "default": EXCHANGE_COUNT_DEFAULT,
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
    },
)

COLUMN_ORDER = tuple(column["key"] for column in COLUMNS)
FIELD_ID_BY_KEY = {column["key"]: column["field_id"] for column in COLUMNS}

ACTIONS: dict = {}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()

UPDATE = "update_profits"
SPENDABLE_UNKNOWN = "spendable_unknown"
SPENDABLE_POSITIVE = "spendable_positive"
SPENDABLE_NEGATIVE = "spendable_negative"
PRIVACY_TOGGLED = "privacy_toggled"
PRIVACY_TOGGLE_SKIPPED = "privacy_toggle_skipped"
DOTS_REFRESHED = "dots_refreshed"

CALL_NAMES = (
    UPDATE,
    SPENDABLE_UNKNOWN,
    SPENDABLE_POSITIVE,
    SPENDABLE_NEGATIVE,
    PRIVACY_TOGGLED,
    PRIVACY_TOGGLE_SKIPPED,
    DOTS_REFRESHED,
)


def money_text(value: Any) -> str:
    """Render one amount as the strip's money string.

    ``None`` renders as the empty marker rather than a fabricated number.
    """
    if value is None:
        return EMPTY_TEXT
    return f"{MONEY_PREFIX}{value:{MONEY_FORMAT}}"


def count_text(value: Any) -> str:
    """Render the exchange count as the strip's plain string."""
    return str(value)


def is_masked(field_id: Any) -> bool:
    """Whether the privacy registry currently hides one field."""
    try:
        return bool(get_privacy_mask_registry().is_masked(field_id))
    except Exception:
        return False


def privacy_dot(field_id: str, masked: Optional[bool] = None) -> dict:
    """The glyph, tooltip and skin one amount's privacy dot carries."""
    hidden = is_masked(field_id) if masked is None else bool(masked)
    state = DOT_MASKED_STATE if hidden else DOT_REVEALED_STATE
    return {
        "field_id": field_id,
        "masked": hidden,
        "text": DOT_MASKED_GLYPH if hidden else DOT_REVEALED_GLYPH,
        "tooltip": f"{field_id}: {state}",
        "style_sheet": DOT_STYLE,
    }


def spendable_cell(value: Any) -> dict:
    """The SPENDABLE cell's text, skin and tooltip for one amount.

    An unknown amount paints muted and explains itself, a negative one
    paints in the error colour, and zero or above in the success colour.
    """
    if value is None:
        return {
            "text": mask_or(EMPTY_TEXT, "kpi.spendable"),
            "style_sheet": VALUE_STYLE_MUTED,
            "tooltip": SPENDABLE_UNKNOWN_TOOLTIP,
        }
    style = VALUE_STYLE_HIGHLIGHT if value >= 0 else VALUE_STYLE_NEGATIVE
    return {
        "text": mask_or(money_text(value), "kpi.spendable"),
        "style_sheet": style,
        "tooltip": "",
    }


def initial_cells() -> dict:
    """Every cell as the strip is built, before any payload arrives.

    The built texts skip the privacy mask, so a masked field still shows
    its placeholder until the first payload is rendered.
    """
    return {
        column["key"]: {
            "text": column["initial_text"],
            "style_sheet": column["initial_style"],
            "tooltip": "",
        }
        for column in COLUMNS
    }


class SpendableProfitsModel:
    """The strip's state between payloads, with no Qt object behind it.

    Holds the last payload so a privacy-dot toggle re-renders the same
    numbers, the rendered cell for every column, and the dot under each.
    """

    def __init__(self) -> None:
        self.last_data: dict = {}
        self.cells: dict = initial_cells()
        self.dots: dict = {
            column["field_id"]: privacy_dot(column["field_id"]) for column in COLUMNS
        }
        self.calls: list = []

    def update_profits(self, data: dict) -> None:
        """Render every cell from one payload.

        Keeps the payload first, then writes the cells in the order the
        strip writes them, so a payload that cannot be rendered leaves the
        same cells written as the strip leaves.
        """
        self.last_data = dict(data) if isinstance(data, dict) else {}
        self.calls.append(UPDATE)
        first, last = COLUMNS[0], COLUMNS[-1]
        amount = data.get(first["source_key"], first["default"])
        if amount is None:
            self.calls.append(SPENDABLE_UNKNOWN)
        elif amount >= 0:
            self.calls.append(SPENDABLE_POSITIVE)
        else:
            self.calls.append(SPENDABLE_NEGATIVE)
        self.cells[first["key"]] = spendable_cell(amount)
        for column in COLUMNS[1:-1]:
            raw = data.get(column["source_key"], column["default"])
            self.cells[column["key"]] = {
                "text": mask_or(money_text(raw), column["field_id"]),
                "style_sheet": VALUE_STYLE_DEFAULT,
                "tooltip": "",
            }
        count = data.get(last["source_key"], last["default"])
        self.cells[last["key"]] = {
            "text": mask_or(count_text(count), last["field_id"]),
            "style_sheet": VALUE_STYLE_DEFAULT,
            "tooltip": "",
        }

    def privacy_toggled(self) -> None:
        """Re-render the cells from the kept payload after a dot toggle.

        A model that has rendered no payload has nothing to re-render.
        """
        if self.last_data:
            self.calls.append(PRIVACY_TOGGLED)
            self.update_profits(self.last_data)
        else:
            self.calls.append(PRIVACY_TOGGLE_SKIPPED)

    def refresh_privacy_dots(self) -> None:
        """Repaint every dot from the registry, then re-render the cells."""
        self.calls.append(DOTS_REFRESHED)
        for field_id in self.dots:
            self.dots[field_id] = privacy_dot(field_id)
        if self.last_data:
            self.update_profits(self.last_data)


def layout_items() -> list:
    """The outer row, item by item, in the order the strip adds them."""
    items: list = [{"kind": "layout", "column": COLUMNS[0]["key"]}]
    for column in COLUMNS[1:]:
        items.append({"kind": "spacing", "px": SEPARATOR_GAP_PX})
        items.append({"kind": "separator"})
        items.append({"kind": "spacing", "px": SEPARATOR_GAP_PX})
        items.append({"kind": "layout", "column": column["key"]})
    items.append({"kind": "stretch"})
    return items


def build_view_model(model: Optional[SpendableProfitsModel] = None) -> dict:
    """Return the whole strip state as one serialisable dict."""
    state = SpendableProfitsModel() if model is None else model
    return {
        "frame": {"style_sheet": FRAME_STYLE, "frame_shape": FRAME_SHAPE},
        "layout": {
            "margins_px": list(OUTER_MARGINS_PX),
            "spacing_px": OUTER_SPACING_PX,
            "column_margins_px": list(COLUMN_MARGINS_PX),
            "column_spacing_px": COLUMN_SPACING_PX,
            "separator_gap_px": SEPARATOR_GAP_PX,
            "dot_align": DOT_ALIGN,
            "trailing_stretch": TRAILING_STRETCH,
        },
        "separator": {
            "text": SEPARATOR_TEXT,
            "style_sheet": SEPARATOR_STYLE,
            "align": SEPARATOR_ALIGN,
        },
        "items": layout_items(),
        "order": list(COLUMN_ORDER),
        "field_ids": dict(FIELD_ID_BY_KEY),
        "columns": [
            {
                **column,
                **state.cells[column["key"]],
                "dot": state.dots[column["field_id"]],
            }
            for column in COLUMNS
        ],
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "call_names": list(CALL_NAMES),
        "method": METHOD,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``spendable_profits.state``.

    Renders the payload under ``profits`` when the request carries one,
    and repaints every dot when the request asks for it.
    """
    asked = params or {}
    state = SpendableProfitsModel()
    profits = asked.get("profits")
    if profits is not None:
        state.update_profits(profits)
    if asked.get("refresh_dots"):
        state.refresh_privacy_dots()
    return build_view_model(state)
