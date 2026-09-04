"""header_strip_surface.py -- the header stat strip view model served to a frontend."""

from __future__ import annotations

import math
from typing import Any, Optional

from ...core.privacy_mask_registry import get_privacy_mask_registry, mask_or

from .. import design_system as ds
from ..color_alpha import css_colours

METHOD = "header.strip"

EMPTY_TEXT = "—"
MONEY_PREFIX = "$"
MONEY_FORMAT = ",.2f"
PNL_FORMAT = "+,.4f"
COUNT_FORMAT = "str"

CENTRAL_LAYOUT = {
    "margins_px": [6, 4, 6, 4],
    "spacing_px": 4,
    "child_stretch": [0],
}

TOP_ROW = {
    "margins_px": [0, 0, 0, 0],
    "spacing_px": 4,
    "child_stretch": [3, 1, 1, 1, 1, 1, 1],
}

TOP_ROW_ORDER = [
    "spendable",
    "scrummed",
    "folded",
    "trades",
    "bots",
    "errors",
    "mode_button",
]

ISOLATED_TABS = ("Simulator", "Paper Trader")

SPENDABLE_STYLE = (
    "SpendableProfitsWidget { "
    "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
    "    stop:0 rgba(0,40,30,200), stop:1 rgba(0,60,45,200)); "
    "  border: 1px solid rgba(0,255,180,80); border-radius: 4px; }"
)

SPENDABLE_LAYOUT = {
    "margins_px": [12, 6, 12, 6],
    "spacing_px": 0,
    "column_spacing_px": 14,
    "column_margins_px": [0, 0, 0, 0],
    "column_spacing": 2,
    "frame_shape": "StyledPanel",
    "separator_align": "vcenter",
    "dot_align": "hcenter",
}

KPI_LABEL_STYLE = (
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

SEPARATOR = {"text": "|", "style_sheet": SEPARATOR_STYLE}

SPENDABLE_TOOLTIP = (
    "Cash balance pulled from the exchange, across the bots sharing one wallet."
)
SPENDABLE_UNKNOWN_TOOLTIP = (
    "This amount is not in the data the strip was given for this refresh."
)
UNREADABLE_TOOLTIP = (
    "This amount did not arrive as a number, so nothing is shown for it."
)

KPI_COLUMNS = (
    {
        "key": "spendable",
        "label": "SPENDABLE",
        "label_style": SPENDABLE_LABEL_STYLE,
        "label_tooltip": SPENDABLE_TOOLTIP,
        "field_id": "kpi.spendable",
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_MUTED,
    },
    {
        "key": "total_realised",
        "label": "REALISED",
        "label_style": KPI_LABEL_STYLE,
        "label_tooltip": "",
        "field_id": "kpi.realised",
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
    },
    {
        "key": "locked",
        "label": "LOCKED",
        "label_style": KPI_LABEL_STYLE,
        "label_tooltip": "",
        "field_id": "kpi.locked",
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
    },
    {
        "key": "mature",
        "label": "MATURE",
        "label_style": KPI_LABEL_STYLE,
        "label_tooltip": "",
        "field_id": "kpi.mature",
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
    },
    {
        "key": "exchanges",
        "label": "EXCH",
        "label_style": KPI_LABEL_STYLE,
        "label_tooltip": "",
        "field_id": "kpi.exch",
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
    },
)

CARD_LAYOUT = {
    "margins_px": [8, 4, 8, 4],
    "spacing_px": 2,
    "frame_shape": "StyledPanel",
    "label_align": "hcenter|bottom",
    "value_align": "hcenter|top",
    "dot_align": "hcenter",
}
CARD_LABEL_ROW = {
    "margins_px": [0, 0, 0, 0],
    "spacing_px": 4,
    "order": ["stretch", "label", "stretch"],
}
CARD_LABEL_STYLE = f"font-size: 10px; color: {ds.MAIN_CAPTION};"
CARD_VALUE_STYLE = f"font-size: 14px; font-weight: bold; color: {ds.PRIMARY};"
CARD_LABEL_PROPERTY = "muted"
CARD_VALUE_PROPERTY = "heading"

SCRUMMED_TOOLTIP = (
    "Total Scrummed (high score) — cumulative USD sold "
    "across all bots since the platform run started. Grows "
    "with every SCRUM (sell at upper-band) + MANUAL_SCRUM "
    "fill. Resets to $0.00 only on a fresh process start."
)
FOLDED_TOOLTIP = (
    "Total Folded (high score) — cumulative USD bought "
    "across all bots since the platform run started. Grows "
    "with every FOLD (buy at lower-band) + MANUAL_FOLD "
    "fill. Resets to $0.00 only on a fresh process start."
)
TRADES_TOOLTIP = "Total executed buy and sell trades across all active bots."
BOTS_TOOLTIP = "Bots currently in RUNNING state (actively trading)."
ERRORS_TOOLTIP = (
    "Error count across all bots since last reset. "
    "Click to open the Error Log; use the Reset button "
    "inside to clear all previous faults.\n\n"
    "Hover bot rows to see current ERROR/COOLDOWN state."
)
ERRORS_CLICK_TOOLTIP = "Click to open the error log."


def click_tooltip(base: Any, suffix: Any) -> str:
    """Render the tooltip a card carries once it becomes clickable."""
    text = "" if base is None else str(base)
    tail = "" if suffix is None else str(suffix)
    if not tail or tail in text:
        return text
    return (text + "\n\n" + tail).strip()


COUNTER_CARDS = (
    {
        "key": "scrummed",
        "label": "Scrummed",
        "initial_text": "$0.00",
        "tooltip": SCRUMMED_TOOLTIP,
        "field_id": "counter.scrummed",
        "clickable": False,
        "cursor": "arrow",
        "source_key": "total_scrummed_usd",
        "format": MONEY_FORMAT,
    },
    {
        "key": "folded",
        "label": "Folded",
        "initial_text": "$0.00",
        "tooltip": FOLDED_TOOLTIP,
        "field_id": "counter.folded",
        "clickable": False,
        "cursor": "arrow",
        "source_key": "total_folded_usd",
        "format": MONEY_FORMAT,
    },
    {
        "key": "trades",
        "label": "Trades",
        "initial_text": "0",
        "tooltip": TRADES_TOOLTIP,
        "field_id": "counter.trades",
        "clickable": False,
        "cursor": "arrow",
        "source_key": "total_trades",
        "format": COUNT_FORMAT,
    },
    {
        "key": "bots",
        "label": "Bots",
        "initial_text": "0",
        "tooltip": BOTS_TOOLTIP,
        "field_id": "counter.bots",
        "clickable": False,
        "cursor": "arrow",
        "source_key": "running",
        "format": COUNT_FORMAT,
    },
    {
        "key": "errors",
        "label": "Errors",
        "initial_text": "0",
        "tooltip": click_tooltip(ERRORS_TOOLTIP, ERRORS_CLICK_TOOLTIP),
        "field_id": "counter.errors",
        "clickable": True,
        "cursor": "pointing_hand",
        "source_key": "total_errors_lifetime",
        "format": COUNT_FORMAT,
    },
)

HIDDEN_CARD = {
    "key": "pnl",
    "label": "P/L",
    "initial_text": "$0.00",
    "tooltip": "",
    "field_id": None,
    "visible": False,
    "source_key": "total_realised_pnl",
    "format": PNL_FORMAT,
}

PROFITS_SOURCE_KEYS = ("wallet_cash_usd", "crypto_position_value_usd")

STATS_KEYS = (
    tuple(card["source_key"] for card in COUNTER_CARDS)
    + (HIDDEN_CARD["source_key"],)
    + PROFITS_SOURCE_KEYS
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

DEFAULT_MODE = "crypto"

MODE_BUTTON = {
    "minimum_width_px": 110,
    "horizontal_policy": "Preferred",
    "vertical_policy": "Expanding",
    "checkable": True,
    "tooltip": "Toggle between Crypto and Stock trading layers",
}

MODE_CARDS = {
    "crypto": {
        "text": "Crypto Mode",
        "checked": False,
        "color": ds.LAYER_CRYPTO,
        "style_sheet": (
            "QPushButton { background: rgba(0, 200, 160, 40); "
            f"color: {ds.LAYER_CRYPTO}; border: 1px solid rgba(0, 200, 160, "
            "100); "
            "border-radius: 4px; font-weight: bold; font-size: 11px; }"
            "QPushButton:hover { background: rgba(0, 200, 160, 70); }"
        ),
        "window_title": "Acervator — CRYPTO WING",
    },
    "stock": {
        "text": "Stock Mode",
        "checked": True,
        "color": ds.LAYER_STOCK,
        "style_sheet": (
            "QPushButton { background: rgba(80, 140, 255, 40); "
            f"color: {ds.LAYER_STOCK}; border: 1px solid rgba(80, 140, 255, "
            "100); "
            "border-radius: 4px; font-weight: bold; font-size: 11px; }"
            "QPushButton:hover { background: rgba(80, 140, 255, 70); }"
        ),
        "window_title": "Acervator — STOCK WING",
    },
}

ACTIONS = {
    "errors.clicked": "show_error_log_dialog",
    "mode_button.clicked": "toggle_trading_mode",
}


def money_amount(value: Any) -> Any:
    """The finite number a payload value carries, unconverted, or ``None``."""
    if type(value) is int:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    return None


def money_text(value: Any) -> str:
    """Render one KPI amount, or the strip's empty marker."""
    amount = money_amount(value)
    if amount is None:
        return EMPTY_TEXT
    return f"{MONEY_PREFIX}{amount:{MONEY_FORMAT}}"


def count_text(value: Any) -> str:
    """Render one counter card as the strip's plain string."""
    return str(value)


def exchange_count_text(value: Any) -> str:
    """Render a whole exchange count, or the strip's empty marker."""
    if type(value) is not int:
        return EMPTY_TEXT
    return str(value)


def pnl_text(value: Any) -> str:
    """Render the hidden P/L card, which carries a sign and four places."""
    return f"{MONEY_PREFIX}{value:{PNL_FORMAT}}"


def is_masked(field_id: Any) -> bool:
    """Whether the privacy registry currently hides one field."""
    try:
        return bool(get_privacy_mask_registry().is_masked(field_id))
    except Exception:
        return False


def privacy_dot(field_id: str, masked: Optional[bool] = None) -> dict:
    """The glyph, tooltip and skin one value's privacy dot carries."""
    hidden = is_masked(field_id) if masked is None else bool(masked)
    glyph = DOT_MASKED_GLYPH if hidden else DOT_REVEALED_GLYPH
    state = "MASKED. Click to reveal." if hidden else "REVEALED. Click to mask."
    return {
        "field_id": field_id,
        "masked": hidden,
        "text": glyph,
        "tooltip": f"{field_id}: {state}",
        "style_sheet": DOT_STYLE,
    }


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


def kpi_cells(profits: Optional[dict]) -> dict:
    """Every KPI cell the spendable panel shows for one payload."""
    data = profits if isinstance(profits, dict) else {}
    return {
        "spendable": spendable_cell(data.get("spendable")),
        "total_realised": {
            "text": mask_or(money_text(data.get("total_realised")), "kpi.realised"),
            "style_sheet": VALUE_STYLE_DEFAULT,
            "tooltip": "",
        },
        "locked": {
            "text": mask_or(money_text(data.get("locked")), "kpi.locked"),
            "style_sheet": VALUE_STYLE_DEFAULT,
            "tooltip": "",
        },
        "mature": {
            "text": mask_or(money_text(data.get("mature")), "kpi.mature"),
            "style_sheet": VALUE_STYLE_DEFAULT,
            "tooltip": "",
        },
        "exchanges": {
            "text": mask_or(
                exchange_count_text(data.get("exchange_count")), "kpi.exch"
            ),
            "style_sheet": VALUE_STYLE_DEFAULT,
            "tooltip": "",
        },
    }


def counter_cells(stats: Optional[dict]) -> dict:
    """Every counter card's rendered value for one aggregate snapshot."""
    data = stats if isinstance(stats, dict) else {}
    scrummed = float(data.get("total_scrummed_usd", 0.0) or 0.0)
    folded = float(data.get("total_folded_usd", 0.0) or 0.0)
    return {
        "scrummed": mask_or(money_text(scrummed), "counter.scrummed"),
        "folded": mask_or(money_text(folded), "counter.folded"),
        "trades": mask_or(count_text(data.get("total_trades", 0)), "counter.trades"),
        "bots": mask_or(count_text(data.get("running", 0)), "counter.bots"),
        "errors": mask_or(
            count_text(data.get("total_errors_lifetime", 0)), "counter.errors"
        ),
    }


def hidden_card_text(stats: Optional[dict]) -> str:
    """The P/L card's value."""
    data = stats if isinstance(stats, dict) else {}
    return pnl_text(float(data.get("total_realised_pnl", 0.0) or 0.0))


def profits_payload(stats: Optional[dict], exchange_count: int = 0) -> dict:
    """The payload the spendable panel receives for one snapshot."""
    data = stats if isinstance(stats, dict) else {}
    wallet_cash = float(data.get("wallet_cash_usd", 0.0) or 0.0)
    position_value = float(data.get("crypto_position_value_usd", 0.0) or 0.0)
    known = wallet_cash > 0 or position_value > 0
    return {
        "spendable": wallet_cash if known else None,
        "total_realised": None,
        "locked": position_value if known else None,
        "mature": None,
        "exchange_count": int(exchange_count),
    }


def mode_card(mode: Any) -> dict:
    """The mode button's text, checked state and skin for one wing."""
    key = "stock" if str(mode) == "stock" else DEFAULT_MODE
    return {"mode": key, **MODE_BUTTON, **MODE_CARDS[key]}


def strip_visible(tab_name: Any) -> bool:
    """Whether the strip shows while ``tab_name`` is the active tab."""
    return tab_name not in ISOLATED_TABS


def build_view_model(
    stats: Optional[dict] = None,
    exchange_count: int = 0,
    mode: Any = DEFAULT_MODE,
    tab_name: Any = None,
    profits: Optional[dict] = None,
) -> dict:
    """Return the whole strip state as one serialisable dict.

    The style sheets are written the way the Qt widget carries them, with
    the alpha byte Qt reads. The payload leaves under
    `src.gui.color_alpha.css_colours`, so the renderer receives the share
    a browser reads and no style sheet is written out twice.
    """
    payload = profits_payload(stats, exchange_count) if profits is None else profits
    cells = kpi_cells(payload)
    values = counter_cells(stats)
    strip = {
        "central_layout": CENTRAL_LAYOUT,
        "top_row": TOP_ROW,
        "top_row_order": list(TOP_ROW_ORDER),
        "visible": strip_visible(tab_name),
        "isolated_tabs": list(ISOLATED_TABS),
        "spendable": {
            "style_sheet": SPENDABLE_STYLE,
            "layout": SPENDABLE_LAYOUT,
            "separator": SEPARATOR,
            "columns": [
                {
                    **column,
                    **cells[column["key"]],
                    "dot": privacy_dot(column["field_id"]),
                }
                for column in KPI_COLUMNS
            ],
        },
        "card_layout": CARD_LAYOUT,
        "card_label_row": CARD_LABEL_ROW,
        "card_label_style": CARD_LABEL_STYLE,
        "card_value_style": CARD_VALUE_STYLE,
        "card_label_property": CARD_LABEL_PROPERTY,
        "card_value_property": CARD_VALUE_PROPERTY,
        "counters": [
            {
                **card,
                "text": values[card["key"]],
                "dot": privacy_dot(card["field_id"]),
            }
            for card in COUNTER_CARDS
        ],
        "hidden_card": {**HIDDEN_CARD, "text": hidden_card_text(stats)},
        "mode_button": mode_card(mode),
        "actions": dict(ACTIONS),
    }
    return css_colours(strip)


def view_model(params: dict) -> dict:
    """Bridge handler for ``header.strip``."""
    return build_view_model(
        stats=params.get("stats") or {},
        exchange_count=int(params.get("exchange_count") or 0),
        mode=params.get("mode", DEFAULT_MODE),
        tab_name=params.get("tab_name"),
        profits=params.get("profits"),
    )
