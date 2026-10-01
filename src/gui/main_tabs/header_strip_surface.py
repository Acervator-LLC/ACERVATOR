"""header_strip_surface.py -- the header stat strip view model served to a frontend."""

from __future__ import annotations

import math
from typing import Any, Optional

from ...core.privacy_mask_registry import (
    ABSENT_TEXT as _ABSENT_TEXT,
    get_privacy_mask_registry,
    mask_or,
)
from ...trading.target_bands import (
    TERRITORY_AT_TARGET,
    TERRITORY_FOLD,
    TERRITORY_SCRUM,
)

from .. import design_system as ds
from ..color_alpha import css_colours
from . import asset_class_surface, main_window_surface, privacy_dot_surface

METHOD = "header.strip"

EMPTY_TEXT = _ABSENT_TEXT
MONEY_PREFIX = "$"
MONEY_FORMAT = ",.2f"
COUNT_FORMAT = "str"

#: What the central layout leaves either side of the top row.
CENTRAL_SIDE_MARGIN_PX = 6

#: The gap the top row leaves between two of its slots.
TOP_ROW_SPACING_PX = 4

CENTRAL_LAYOUT = {
    "margins_px": [CENTRAL_SIDE_MARGIN_PX, 4, CENTRAL_SIDE_MARGIN_PX, 4],
    "spacing_px": 4,
    "child_stretch": [0],
}

#: The stretch each ``TOP_ROW_ORDER`` slot takes. The six slots holding text
#: divide the whole row between them; the class group's slot takes zero, so it
#: shrinks to the square and the square sits against the row's right edge.
TOP_ROW_STRETCH = [3, 1, 1, 1, 1, 1, 0]

TOP_ROW = {
    "margins_px": [0, 0, 0, 0],
    "spacing_px": TOP_ROW_SPACING_PX,
    "child_stretch": TOP_ROW_STRETCH,
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

#: The narrowest the spendable strip draws at. Its widest column, SPENDABLE,
#: keeps its caption and an elided amount at this width.
SPENDABLE_MIN_W = 180

#: The room one KPI column needs for a whole money amount at its own size.
#: Ninety-four, not a hundred and ten: eight columns at this width keep
#: ``spendable_natural_w`` at the 890 the seven held, so no other slot moves.
KPI_COLUMN_W = 94

#: The narrowest one counter card draws at, caption and amount both elided.
COUNTER_MIN_W = 48

#: The slot names the top row gives a declared floor, in row order. The
#: class group is not here; ``asset_class_surface.group_side_px`` answers it,
#: because the group's floor grows with the class count.
COUNTER_SLOTS = ("scrummed", "folded", "trades", "bots", "errors")

#: The window's own tuple, so a tab renamed there renames here too.
ISOLATED_TABS = main_window_surface.ISOLATED_TABS

SPENDABLE_STYLE = (
    "SpendableProfitsWidget { "
    "  background: qlineargradient(x1:0, y1:0, x2:1, y2:0, "
    "    stop:0 rgba(0,40,30,200), stop:1 rgba(0,60,45,200)); "
    "  border: 1px solid rgba(0,255,180,80); border-radius: 4px; }"
)

#: What the strip leaves either side of its own columns.
SPENDABLE_SIDE_MARGIN_PX = 6

#: What the strip's own margins take off the room its text has.
SPENDABLE_TEXT_PAD = 2 * SPENDABLE_SIDE_MARGIN_PX

#: The gap the strip leaves either side of a rule between two columns. Four,
#: not fourteen: ``spendable_natural_w`` counts twelve of them, and the room
#: that returns is what the two new columns take.
SPENDABLE_COLUMN_GAP_PX = 3

#: The width one rule between two columns draws at. Declared, not measured:
#: the glyph reads 52 px wide in a fallback font and ``spendable_natural_w``
#: counted none of it, so every column drew narrower than its own amount.
SPENDABLE_RULE_W_PX = 12

#: One share of the row each, so the eight columns sit at one pitch.
SPENDABLE_COLUMN_STRETCH = 1

SPENDABLE_LAYOUT = {
    "margins_px": [SPENDABLE_SIDE_MARGIN_PX, 4, SPENDABLE_SIDE_MARGIN_PX, 4],
    "spacing_px": 0,
    "column_spacing_px": SPENDABLE_COLUMN_GAP_PX,
    "column_margins_px": [0, 0, 0, 0],
    "column_spacing": 2,
    "column_stretch": SPENDABLE_COLUMN_STRETCH,
    "rule_w_px": SPENDABLE_RULE_W_PX,
    "frame_shape": "StyledPanel",
    "separator_align": "vcenter",
    "label_align": "hcenter|bottom",
    "value_align": "hcenter|top",
    "dot_align": "hcenter",
}


#: One caption font for every panel in the strip, and one amount font under it.
LABEL_FONT_PX = 10
LABEL_FONT = f"font-size: {LABEL_FONT_PX}px; font-weight: 600;"

#: The size every money amount draws at where its column has the room.
VALUE_FONT_PX = 14

#: The smallest a money amount shrinks to, which is the caption's own size,
#: so an amount never draws smaller than the caption above it. Measured in
#: the application font, 10 px carries a signed amount past a thousand
#: million dollars in a 93 px column; wider than that is elided.
VALUE_FONT_MIN_PX = LABEL_FONT_PX

VALUE_FONT = f"font-size: {VALUE_FONT_PX}px; font-weight: bold;"


def value_font(size_px: Any) -> str:
    """The amount font declaration at ``size_px``."""
    return f"font-size: {int(size_px)}px; font-weight: bold;"


def fitted_value_px(advance_at: Any, room_px: Any) -> int:
    """The largest size from ``VALUE_FONT_PX`` down to ``VALUE_FONT_MIN_PX``
    whose ``advance_at`` reading fits ``room_px``.

    Answers ``VALUE_FONT_MIN_PX`` where no size fits, and the caller elides.
    """
    room = int(room_px or 0)
    for size_px in range(VALUE_FONT_PX, VALUE_FONT_MIN_PX - 1, -1):
        if int(advance_at(size_px)) <= room:
            return size_px
    return VALUE_FONT_MIN_PX

KPI_LABEL_STYLE = f"color: {ds.CARD_METRIC_LABEL}; {LABEL_FONT}"
SPENDABLE_LABEL_STYLE = f"color: {ds.PRIMARY}; {LABEL_FONT}"
VALUE_STYLE_DEFAULT = f"color: {ds.TEXT_NEUTRAL}; {VALUE_FONT}"
VALUE_STYLE_HIGHLIGHT = f"color: {ds.SUCCESS}; {VALUE_FONT}"
VALUE_STYLE_NEGATIVE = f"color: {ds.ERROR}; {VALUE_FONT}"
VALUE_STYLE_MUTED = f"color: {ds.CARD_METRIC_LABEL}; {VALUE_FONT}"
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

AMMO_LABEL = "AMMO"
AMMO_TOOLTIP = (
    "Total Ammo — every bot's Target Delta added together, in whole "
    "dollars. Green while more bots hold more than their target, red "
    "while more hold less."
)
AMMO_UNKNOWN_TOOLTIP = (
    "This fleet reports no Target Delta total, so nothing is shown for it."
)

#: The Ammo total's own format: whole dollars, with a thousands mark.
AMMO_FORMAT = ",.0f"

#: The P/L card's format: the venue's unrealised figure, signed, to the cent.
PNL_FORMAT = "+,.2f"

PNL_TOOLTIP = (
    "P/L — the unrealised profit and loss the exchange answers across "
    "every bot's open position. Realised profit and loss has its own "
    "column in the strip on the left."
)

ACCUMULATED_LABEL = "ACCUMULATED"
ACCUMULATED_TOOLTIP = (
    "Accumulated — every bot's accrued funds added together, which is "
    "each live Target Balance less the anchor it was set from."
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
        "key": "pnl",
        "label": "P/L",
        "label_style": KPI_LABEL_STYLE,
        "label_tooltip": PNL_TOOLTIP,
        "field_id": "kpi.pnl",
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
    {
        "key": "total_ammo",
        "label": AMMO_LABEL,
        "label_style": KPI_LABEL_STYLE,
        "label_tooltip": AMMO_TOOLTIP,
        "field_id": "kpi.ammo",
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_MUTED,
    },
    {
        "key": "accumulated",
        "label": ACCUMULATED_LABEL,
        "label_style": KPI_LABEL_STYLE,
        "label_tooltip": ACCUMULATED_TOOLTIP,
        "field_id": "kpi.accumulated",
        "initial_text": EMPTY_TEXT,
        "initial_style": VALUE_STYLE_DEFAULT,
    },
)

#: What a card leaves either side of its caption and its amount. Four, not
#: eight: the row draws six cards where it drew five, and the eight pixels
#: this returns is the text room the widest amount needs.
CARD_SIDE_MARGIN_PX = 4

#: What a card's own margins take off the room its text has.
COUNTER_TEXT_PAD = 2 * CARD_SIDE_MARGIN_PX

#: The room one counter card gives its own amount. Declared here and not
#: read off ``KPI_COLUMN_W``: a card holds one amount where the strip now
#: divides its width eight ways.
COUNTER_TEXT_W = 110

#: The room one counter needs for a whole money amount at its own size.
COUNTER_NATURAL_W = COUNTER_TEXT_W + COUNTER_TEXT_PAD

CARD_LAYOUT = {
    "margins_px": [CARD_SIDE_MARGIN_PX, 4, CARD_SIDE_MARGIN_PX, 4],
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
CARD_LABEL_STYLE = f"color: {ds.MAIN_CAPTION}; {LABEL_FONT}"
CARD_VALUE_STYLE = f"color: {ds.PRIMARY}; {VALUE_FONT}"
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
        "label": "SCRUMMED",
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
        "label": "FOLDED",
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
        "label": "TRADES",
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
        "label": "BOTS",
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
        "label": "ERRORS",
        "initial_text": "0",
        "tooltip": click_tooltip(ERRORS_TOOLTIP, ERRORS_CLICK_TOOLTIP),
        "field_id": "counter.errors",
        "clickable": True,
        "cursor": "pointing_hand",
        "source_key": "total_errors_lifetime",
        "format": COUNT_FORMAT,
    },
)

PROFITS_SOURCE_KEYS = (
    "wallet_cash_usd",
    "crypto_position_value_usd",
    "total_realized_exchange",
    "total_unrealized_exchange",
    "total_mature_exchange",
    "bots_with_fresh_exchange_data",
    "realised_history_complete",
    "total_target_delta_usd",
    "total_accrued_usd",
    "bots_scrum_territory",
    "bots_fold_territory",
)

#: `get_aggregate_stats` counts the bots the venue has answered for. At zero
#: neither exchange figure is a reading, so both columns stay absent.
EXCHANGE_FRESHNESS_KEY = "bots_with_fresh_exchange_data"

#: `get_aggregate_stats` answers False while any answered bot's fill history
#: was cut short. The realised sum is then not a reading. An aggregate without
#: the key walks no venue fill history at all, so its realised figure is whole.
REALISED_COMPLETE_KEY = "realised_history_complete"

STATS_KEYS = tuple(card["source_key"] for card in COUNTER_CARDS) + PROFITS_SOURCE_KEYS

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

#: The request field ``view_model`` reads the wing from.
MODE_PARAM = "mode"

#: The request field carrying ``BotManager.get_aggregate_stats``.
STATS_PARAM = "stats"

#: The request field carrying how many exchanges the program is configured for.
EXCHANGE_COUNT_PARAM = "exchange_count"

MODE_BUTTON = {
    "horizontal_policy": "Preferred",
    "vertical_policy": "Expanding",
    "checkable": True,
    "tooltip": "Pick the asset class every tab filters to",
}

ACTIONS = {
    "errors.clicked": "show_error_log_dialog",
    "mode_button.clicked": "select_asset_class",
}


def spendable_natural_w() -> int:
    """The room the whole strip needs for every ``KPI_COLUMNS`` amount.

    ``KPI_COLUMN_W`` per column, each rule's own ``SPENDABLE_RULE_W_PX`` and
    the gap either side of it, and ``SPENDABLE_TEXT_PAD`` for the frame.
    """
    held = len(KPI_COLUMNS)
    rules = max(held - 1, 0) * (SPENDABLE_RULE_W_PX + 2 * SPENDABLE_COLUMN_GAP_PX)
    return held * KPI_COLUMN_W + rules + SPENDABLE_TEXT_PAD


def slot_natural_w(slot: Any) -> int:
    """The width one slot draws at where the row can afford it.

    ``react_dashboard_stat_card`` and ``react_spendable_profits`` read
    ``COUNTER_NATURAL_W`` and ``spendable_natural_w`` for their own sizeHint.
    """
    name = str(slot or "")
    if name == "spendable":
        return spendable_natural_w()
    if name in COUNTER_SLOTS:
        return COUNTER_NATURAL_W
    return slot_min_w(name)


def slot_stretch(slot: Any) -> int:
    """The stretch one ``TOP_ROW_ORDER`` slot takes of the row."""
    name = str(slot or "")
    if name not in TOP_ROW_ORDER:
        return 0
    return int(TOP_ROW_STRETCH[TOP_ROW_ORDER.index(name)])


def slot_min_w(slot: Any) -> int:
    """The narrowest one ``TOP_ROW_ORDER`` slot draws at.

    Every slot declares a floor, so ``top_row_min_w`` never reads the width
    of the text a slot happens to hold.
    """
    name = str(slot or "")
    if name == "spendable":
        return SPENDABLE_MIN_W
    if name == "mode_button":
        return asset_class_surface.group_side_px()
    if name in COUNTER_SLOTS:
        return COUNTER_MIN_W
    return 0


def slot_floor_w(slot: Any) -> int:
    """The width both hosts floor one ``TOP_ROW_ORDER`` slot at.

    The spendable strip floors at ``slot_natural_w``, because its columns hold
    whole money amounts; every other slot floors at ``slot_min_w``, so the row
    never grows past the window and pushes the class square off its right edge.
    """
    name = str(slot or "")
    if name == "spendable":
        return slot_natural_w(name)
    return slot_min_w(name)


def top_row_min_w() -> int:
    """The narrowest the header top row draws at, holding every slot.

    The sum of every ``slot_min_w``, plus the ``TOP_ROW`` gap between two
    of them.
    """
    held = [slot for slot in TOP_ROW_ORDER if slot_min_w(slot) > 0]
    gaps = max(len(held) - 1, 0) * TOP_ROW_SPACING_PX
    return sum(slot_min_w(slot) for slot in held) + gaps


def window_min_w() -> int:
    """The narrowest the main window draws at, as ``top_row_min_w`` sets it."""
    return top_row_min_w() + 2 * CENTRAL_SIDE_MARGIN_PX


def width_budget() -> dict:
    """Every floor the top row holds, as one serialisable dict.

    ``slots`` carries the ``slot_floor_w`` both variants set on each slot:
    ``setMinimumWidth`` on the Qt row, ``min-width`` on the page's flex item.
    """
    return {
        "slots": {slot: slot_floor_w(slot) for slot in TOP_ROW_ORDER},
        "spendable_text_pad_px": SPENDABLE_TEXT_PAD,
        "counter_text_pad_px": COUNTER_TEXT_PAD,
        "top_row_min_w_px": top_row_min_w(),
        "window_min_w_px": window_min_w(),
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
    """Render the P/L card's amount with its sign, or the strip's empty marker."""
    amount = money_amount(value)
    if amount is None:
        return EMPTY_TEXT
    return f"{MONEY_PREFIX}{amount:{PNL_FORMAT}}"


def ammo_total_text(value: Any) -> str:
    """Render the fleet Ammo total in whole dollars, or the empty marker.

    ``AMMO_FORMAT`` drops the decimal part, and a total below zero keeps its
    minus ahead of ``MONEY_PREFIX``.
    """
    amount = money_amount(value)
    if amount is None:
        return EMPTY_TEXT
    whole = round(amount)
    sign = "-" if whole < 0 else ""
    return f"{sign}{MONEY_PREFIX}{abs(whole):{AMMO_FORMAT}}"


def ammo_lean(above: Any, below: Any) -> str:
    """Which territory holds more bots, counted in bots and not in dollars.

    Answers ``TERRITORY_AT_TARGET`` where neither count is the larger, which
    is the one case the Ammo column draws in the strip's neutral text.
    """
    try:
        scrum, fold = int(above or 0), int(below or 0)
    except (TypeError, ValueError):
        return TERRITORY_AT_TARGET
    if scrum > fold:
        return TERRITORY_SCRUM
    if fold > scrum:
        return TERRITORY_FOLD
    return TERRITORY_AT_TARGET


#: The value skin each ``ammo_lean`` answer draws the Ammo total in.
AMMO_LEAN_STYLES = {
    TERRITORY_SCRUM: VALUE_STYLE_HIGHLIGHT,
    TERRITORY_FOLD: VALUE_STYLE_NEGATIVE,
    TERRITORY_AT_TARGET: VALUE_STYLE_DEFAULT,
}


def ammo_cell(value: Any, lean: Any) -> dict:
    """The AMMO column's text, skin and tooltip for one total and one lean."""
    text = ammo_total_text(value)
    if text == EMPTY_TEXT:
        return {
            "text": mask_or(EMPTY_TEXT, "kpi.ammo"),
            "style_sheet": VALUE_STYLE_MUTED,
            "tooltip": AMMO_UNKNOWN_TOOLTIP,
        }
    return {
        "text": mask_or(text, "kpi.ammo"),
        "style_sheet": AMMO_LEAN_STYLES[ammo_lean_key(lean)],
        "tooltip": "",
    }


def ammo_lean_key(lean: Any) -> str:
    """One ``AMMO_LEAN_STYLES`` key, defaulting to ``TERRITORY_AT_TARGET``."""
    name = str(lean or "")
    return name if name in AMMO_LEAN_STYLES else TERRITORY_AT_TARGET


def is_masked(field_id: Any) -> bool:
    """Whether the privacy registry currently hides one field."""
    try:
        return bool(get_privacy_mask_registry().is_masked(field_id))
    except Exception:
        return False


def privacy_dot(field_id: str, masked: Optional[bool] = None) -> dict:
    """The glyph, tooltip, skin and press behaviour one privacy dot carries.

    ``flat``, ``focus_policy`` and ``cursor_shape`` come from
    ``privacy_dot_surface``, which is where the Qt ``PrivacyDot`` reads them.
    """
    hidden = is_masked(field_id) if masked is None else bool(masked)
    glyph = DOT_MASKED_GLYPH if hidden else DOT_REVEALED_GLYPH
    state = "MASKED. Click to reveal." if hidden else "REVEALED. Click to mask."
    return {
        "field_id": field_id,
        "masked": hidden,
        "text": glyph,
        "tooltip": f"{field_id}: {state}",
        "style_sheet": DOT_STYLE,
        "flat": privacy_dot_surface.FLAT,
        "focus_policy": privacy_dot_surface.FOCUS_POLICY,
        "cursor_shape": privacy_dot_surface.CURSOR_SHAPE,
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
        "pnl": {
            "text": mask_or(pnl_text(data.get("unrealised")), "kpi.pnl"),
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
        "total_ammo": ammo_cell(data.get("total_ammo"), data.get("ammo_lean")),
        "accumulated": {
            "text": mask_or(money_text(data.get("accumulated")), "kpi.accumulated"),
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


def exchange_amount(stats: Optional[dict], key: str) -> Any:
    """One exchange-sourced figure from ``stats``, or ``None`` when
    ``EXCHANGE_FRESHNESS_KEY`` counts no answered bot.

    ``profits_payload`` reads it for ``total_realized_exchange`` and
    ``total_mature_exchange``.
    """
    data = stats if isinstance(stats, dict) else {}
    try:
        answered = int(data.get(EXCHANGE_FRESHNESS_KEY, 0) or 0)
    except (TypeError, ValueError):
        return None
    if answered <= 0:
        return None
    return money_amount(float(data.get(key, 0.0) or 0.0))


def realised_amount(stats: Optional[dict]) -> Any:
    """The fleet realised figure, or ``None`` when it is not a reading.

    ``exchange_amount`` answers ``None`` while the venue has answered for no
    bot; this answers ``None`` as well when ``REALISED_COMPLETE_KEY`` reads
    False, which is a venue fill history the walk could not finish. The column
    then draws the strip's empty marker rather than a sum over part of a
    history. The Paper and Simulator aggregates carry no such walk and omit
    the key, so their realised figure passes through whole.
    """
    data = stats if isinstance(stats, dict) else {}
    if not bool(data.get(REALISED_COMPLETE_KEY, True)):
        return None
    return exchange_amount(data, "total_realized_exchange")


def unrealised_amount(stats: Optional[dict]) -> Any:
    """The fleet's unrealised profit and loss, or ``None`` while it is no reading.

    ``reconciliation`` writes each bot's ``unrealised_pnl`` from the venue, and
    ``exchange_amount`` answers ``None`` while the venue has answered for no bot.
    """
    return exchange_amount(stats, "total_unrealized_exchange")


def profits_payload(stats: Optional[dict], exchange_count: int = 0) -> dict:
    """The payload the spendable panel receives for one snapshot."""
    data = stats if isinstance(stats, dict) else {}
    wallet_cash = float(data.get("wallet_cash_usd", 0.0) or 0.0)
    position_value = float(data.get("crypto_position_value_usd", 0.0) or 0.0)
    known = wallet_cash > 0 or position_value > 0
    return {
        "spendable": wallet_cash if known else None,
        "total_realised": realised_amount(data),
        "locked": position_value if known else None,
        "unrealised": unrealised_amount(data),
        "mature": exchange_amount(data, "total_mature_exchange"),
        "exchange_count": int(exchange_count),
        "total_ammo": money_amount(data.get("total_target_delta_usd")),
        "accumulated": money_amount(data.get("total_accrued_usd")),
        "ammo_lean": ammo_lean(
            data.get("bots_scrum_territory"), data.get("bots_fold_territory")
        ),
    }


def next_mode(mode: Any) -> str:
    """The class the group steps to, so a frontend spells no class name."""
    classes = asset_class_surface.asset_classes()
    if not classes:
        return DEFAULT_MODE
    here = classes.index(asset_class_surface.normalise(mode))
    return classes[(here + 1) % len(classes)]


def mode_card(mode: Any) -> dict:
    """The whole segmented group: one button per class, and the active one.

    ``asset_class_surface.class_buttons`` builds the buttons, so the group
    follows ``ASSET_CLASSES`` with no edit here.
    """
    key = asset_class_surface.normalise(mode)
    rows, columns = asset_class_surface.grid_shape()
    return {
        "mode": key,
        "next_mode": next_mode(key),
        "mode_param": MODE_PARAM,
        "buttons": asset_class_surface.class_buttons(key),
        "text_pad_px": asset_class_surface.BUTTON_TEXT_PAD,
        "group_spacing_px": asset_class_surface.GROUP_SPACING_PX,
        "grid_rows": rows,
        "grid_columns": columns,
        "minimum_width_px": asset_class_surface.segment_width_px(),
        "side_px": asset_class_surface.group_side_px(),
        "window_title": asset_class_surface.window_title(key),
        "add_exchange": {
            "label": asset_class_surface.add_exchange_label(key),
            "tooltip": asset_class_surface.add_exchange_tooltip(key),
            "enabled": asset_class_surface.add_exchange_enabled(key),
        },
        **MODE_BUTTON,
    }


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
        "width_budget": width_budget(),
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
        "mode_button": mode_card(mode),
        "actions": dict(ACTIONS),
    }
    return css_colours(strip)


def view_model(params: dict) -> dict:
    """Bridge handler for ``header.strip``."""
    return build_view_model(
        stats=params.get("stats") or {},
        exchange_count=int(params.get(EXCHANGE_COUNT_PARAM) or 0),
        mode=params.get(MODE_PARAM, DEFAULT_MODE),
        tab_name=params.get("tab_name"),
        profits=params.get("profits"),
    )


def fleet_aggregate(live: Any) -> Optional[dict]:
    """``BotManager.get_aggregate_stats`` from ``live``, or None with no fleet."""
    manager = getattr(live, "bot_manager", None)
    reader = getattr(manager, "get_aggregate_stats", None)
    if not callable(reader):
        return None
    found = reader()
    return found if isinstance(found, dict) else None


def configured_exchange_count(live: Any) -> Optional[int]:
    """How many exchanges ``live.settings_manager`` lists, or None with none.

    The Qt window counts its own exchange sub-tabs, one per listed exchange.
    """
    settings = getattr(live, "settings_manager", None)
    listed = getattr(settings, "list_exchanges", None)
    if not callable(listed):
        return None
    return len(list(listed() or []))


def live_view_model(params: dict, live: Any) -> dict:
    """Answer ``header.strip`` with the fleet the running program holds.

    ``fleet_aggregate`` fills ``STATS_PARAM`` and ``configured_exchange_count``
    fills ``EXCHANGE_COUNT_PARAM`` when the request names neither, so the shell
    draws the same figures the Qt strip draws. Neither figure is derived here.
    """
    asked = dict(params or {})
    if asked.get(STATS_PARAM) is None:
        aggregate = fleet_aggregate(live)
        if aggregate is not None:
            asked[STATS_PARAM] = aggregate
    if asked.get(EXCHANGE_COUNT_PARAM) is None:
        counted = configured_exchange_count(live)
        if counted is not None:
            asked[EXCHANGE_COUNT_PARAM] = counted
    return view_model(asked)


def bind_live(live: Any) -> Any:
    """Return a ``header.strip`` handler reading ``live``.

    ``build_registry`` calls this when the running program serves the bridge.
    """

    def handler(params: dict) -> dict:
        return live_view_model(params or {}, live)

    return handler
