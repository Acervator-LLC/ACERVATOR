"""The spendable-profits strip as plain data, with no Qt behind it."""

from __future__ import annotations

import math
from typing import Any, Optional

from ...core.privacy_mask_registry import (
    ABSENT_TEXT as _ABSENT_TEXT,
    get_privacy_mask_registry,
    mask_or,
)

from . import header_strip_surface as header
from . import privacy_dot_surface

from .. import design_system as ds

METHOD = "spendable_profits.state"

#: The request field carrying ``header_strip_surface.profits_payload``.
PROFITS_PARAM = "profits"

EMPTY_TEXT = _ABSENT_TEXT
MONEY_PREFIX = "$"
MONEY_FORMAT = ",.2f"

#: Qt writes an rgba alpha over this scale, which a page needs to paint one.
ALPHA_SCALE = 255

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
SEPARATOR_GAP_PX = header.SPENDABLE_COLUMN_GAP_PX
RULE_W_PX = header.SPENDABLE_RULE_W_PX
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
    "Cash balance pulled from the exchange, across the bots sharing one wallet."
)
SPENDABLE_UNKNOWN_TOOLTIP = (
    "This amount is not in the data the strip was given for this refresh."
)
UNREADABLE_TOOLTIP = (
    "This amount did not arrive as a number, so nothing is shown for it."
)

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

#: The ``dot_view`` fields one column's dot carries. ``cursor_shape`` is the
#: pointing hand the Qt ``PrivacyDot`` sets on itself.
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

REALISED_DEFAULT = None
EXCHANGE_COUNT_DEFAULT = None

#: How ``update_profits`` renders one column, named per column so no cell is
#: drawn from its position in ``COLUMNS``.
RENDER_SPENDABLE = "spendable"
RENDER_MONEY = "money"
RENDER_COUNT = "count"
RENDER_AMMO = "ammo"
RENDER_PNL = "pnl"

COLUMNS = (
    {
        "key": "spendable",
        "label": "SPENDABLE",
        "label_style": SPENDABLE_LABEL_STYLE,
        "label_tooltip": SPENDABLE_TOOLTIP,
        "field_id": "kpi.spendable",
        "source_key": "spendable",
        "default": None,
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_MUTED,
        "render": RENDER_SPENDABLE,
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
        "render": RENDER_MONEY,
    },
    {
        "key": "pnl",
        "label": "P/L",
        "label_style": LABEL_STYLE,
        "label_tooltip": header.PNL_TOOLTIP,
        "field_id": "kpi.pnl",
        "source_key": "unrealised",
        "default": None,
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
        "render": RENDER_PNL,
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
        "render": RENDER_MONEY,
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
        "render": RENDER_MONEY,
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
        "render": RENDER_COUNT,
    },
    {
        "key": "total_ammo",
        "label": header.AMMO_LABEL,
        "label_style": LABEL_STYLE,
        "label_tooltip": header.AMMO_TOOLTIP,
        "field_id": "kpi.ammo",
        "source_key": "total_ammo",
        "default": None,
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_MUTED,
        "render": RENDER_AMMO,
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
SPENDABLE_UNREADABLE = "spendable_unreadable"
SPENDABLE_POSITIVE = "spendable_positive"
SPENDABLE_NEGATIVE = "spendable_negative"
PRIVACY_TOGGLED = "privacy_toggled"
PRIVACY_TOGGLE_SKIPPED = "privacy_toggle_skipped"
DOTS_REFRESHED = "dots_refreshed"

CALL_NAMES = (
    UPDATE,
    SPENDABLE_UNKNOWN,
    SPENDABLE_UNREADABLE,
    SPENDABLE_POSITIVE,
    SPENDABLE_NEGATIVE,
    PRIVACY_TOGGLED,
    PRIVACY_TOGGLE_SKIPPED,
    DOTS_REFRESHED,
)


def money_amount(value: Any) -> Any:
    """The finite number a payload value carries, unconverted, or ``None``."""
    if type(value) is int:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    return None


def money_text(value: Any) -> str:
    """Render one amount as money text, or as the strip's empty marker."""
    amount = money_amount(value)
    if amount is None:
        return EMPTY_TEXT
    return f"{MONEY_PREFIX}{amount:{MONEY_FORMAT}}"


def count_text(value: Any) -> str:
    """Render a whole exchange count, or the strip's empty marker."""
    if type(value) is not int:
        return EMPTY_TEXT
    return str(value)


def is_masked(field_id: Any) -> bool:
    """Whether the privacy registry currently hides one field."""
    try:
        return bool(get_privacy_mask_registry().is_masked(field_id))
    except Exception:
        return False


def privacy_dot(field_id: str, masked: Optional[bool] = None) -> dict:
    """``privacy_dot_surface.dot_view`` cut to ``_DOT_FIELDS``.

    ``_DOT_FIELDS`` names the glyph, tooltip and skin one column carries.
    """
    painted = privacy_dot_surface.dot_view(field_id, masked)
    return {name: painted[name] for name in _DOT_FIELDS}


def spendable_cell(value: Any) -> dict:
    """The SPENDABLE cell's text, skin and tooltip for one amount."""
    if value is None:
        return {
            "text": mask_or(EMPTY_TEXT, "kpi.spendable"),
            "style_sheet": VALUE_STYLE_MUTED,
            "tooltip": SPENDABLE_UNKNOWN_TOOLTIP,
        }
    amount = money_amount(value)
    if amount is None:
        return {
            "text": mask_or(EMPTY_TEXT, "kpi.spendable"),
            "style_sheet": VALUE_STYLE_MUTED,
            "tooltip": UNREADABLE_TOOLTIP,
        }
    style = VALUE_STYLE_HIGHLIGHT if amount >= 0 else VALUE_STYLE_NEGATIVE
    return {
        "text": mask_or(money_text(amount), "kpi.spendable"),
        "style_sheet": style,
        "tooltip": "",
    }


def column_cell(column: dict, raw: Any, payload: dict) -> dict:
    """One column's text, skin and tooltip, chosen by its own ``render``.

    ``RENDER_AMMO`` reads ``ammo_lean`` out of ``payload`` for its colour;
    every other renderer reads only ``raw``.
    """
    kind = column.get("render")
    field_id = column["field_id"]
    if kind == RENDER_SPENDABLE:
        return spendable_cell(raw)
    if kind == RENDER_AMMO:
        return header.ammo_cell(raw, payload.get("ammo_lean"))
    if kind == RENDER_PNL:
        return {
            "text": mask_or(header.pnl_text(raw), field_id),
            "style_sheet": VALUE_STYLE_DEFAULT,
            "tooltip": "",
        }
    text = count_text(raw) if kind == RENDER_COUNT else money_text(raw)
    return {
        "text": mask_or(text, field_id),
        "style_sheet": VALUE_STYLE_DEFAULT,
        "tooltip": "",
    }


def spendable_branch(value: Any) -> str:
    """The call name the SPENDABLE amount earns from its own value."""
    if value is None:
        return SPENDABLE_UNKNOWN
    amount = money_amount(value)
    if amount is None:
        return SPENDABLE_UNREADABLE
    return SPENDABLE_POSITIVE if amount >= 0 else SPENDABLE_NEGATIVE


def initial_cells() -> dict:
    """Every cell as the strip is built, before any payload arrives."""
    return {
        column["key"]: {
            "text": column["initial_text"],
            "style_sheet": column["initial_style"],
            "tooltip": "",
        }
        for column in COLUMNS
    }


class SpendableProfitsModel:
    """The strip's cells, dots and last payload between refreshes."""

    def __init__(self) -> None:
        self.last_data: dict = {}
        self.cells: dict = initial_cells()
        self.dots: dict = {
            column["field_id"]: privacy_dot(column["field_id"]) for column in COLUMNS
        }
        self.calls: list = []

    def update_profits(self, data: dict) -> None:
        """Render every cell from one payload, then keep that payload."""
        kept = dict(data) if isinstance(data, dict) else {}
        amount = data.get(COLUMNS[0]["source_key"], COLUMNS[0]["default"])
        rendered = {}
        for column in COLUMNS:
            raw = data.get(column["source_key"], column["default"])
            rendered[column["key"]] = column_cell(column, raw, data)
        self.cells.update(rendered)
        self.last_data = kept
        self.calls.append(UPDATE)
        self.calls.append(spendable_branch(amount))

    def privacy_toggled(self) -> None:
        """Re-render the cells from the kept payload after a dot toggle."""
        if not self.last_data:
            self.calls.append(PRIVACY_TOGGLE_SKIPPED)
            return
        self.update_profits(self.last_data)
        self.calls.append(PRIVACY_TOGGLED)

    def refresh_privacy_dots(self) -> None:
        """Repaint every dot from the registry, then re-render the cells."""
        for field_id in self.dots:
            self.dots[field_id] = privacy_dot(field_id)
        if self.last_data:
            self.update_profits(self.last_data)
        self.calls.append(DOTS_REFRESHED)


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
    """The whole strip state as one serialisable dict, both lengths named."""
    state = SpendableProfitsModel() if model is None else model
    items = layout_items()
    return {
        "frame": {"style_sheet": FRAME_STYLE, "frame_shape": FRAME_SHAPE},
        "alpha_scale": ALPHA_SCALE,
        "layout": {
            "margins_px": list(OUTER_MARGINS_PX),
            "spacing_px": OUTER_SPACING_PX,
            "column_margins_px": list(COLUMN_MARGINS_PX),
            "column_spacing_px": COLUMN_SPACING_PX,
            "separator_gap_px": SEPARATOR_GAP_PX,
            "rule_w_px": RULE_W_PX,
            "dot_align": DOT_ALIGN,
            "trailing_stretch": TRAILING_STRETCH,
        },
        "separator": {
            "text": SEPARATOR_TEXT,
            "style_sheet": SEPARATOR_STYLE,
            "align": SEPARATOR_ALIGN,
        },
        "items": items,
        "item_count": len(items),
        "order": list(COLUMN_ORDER),
        "field_ids": dict(FIELD_ID_BY_KEY),
        "column_count": len(COLUMNS),
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
        "calls": list(state.calls),
        "method": METHOD,
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``spendable_profits.state``."""
    asked = params or {}
    state = SpendableProfitsModel()
    profits = asked.get(PROFITS_PARAM)
    if profits is not None:
        state.update_profits(profits)
    if asked.get("refresh_dots"):
        state.refresh_privacy_dots()
    return build_view_model(state)


def live_view_model(params: dict, live: Any) -> dict:
    """Answer ``spendable_profits.state`` from the fleet ``live`` holds.

    The payload comes from ``header_strip_surface.profits_payload``, the one
    builder the Qt window's own tick calls, so both hosts read one aggregate
    and neither host derives a figure of its own.
    """
    from . import header_strip_surface

    asked = dict(params or {})
    if asked.get(PROFITS_PARAM) is None:
        aggregate = header_strip_surface.fleet_aggregate(live)
        if aggregate is not None:
            asked[PROFITS_PARAM] = header_strip_surface.profits_payload(
                aggregate,
                header_strip_surface.configured_exchange_count(live) or 0,
            )
    return view_model(asked)


def bind_live(live: Any) -> Any:
    """Return a ``spendable_profits.state`` handler reading ``live``.

    ``build_registry`` calls this when the running program serves the bridge.
    """

    def handler(params: dict) -> dict:
        return live_view_model(params or {}, live)

    return handler
