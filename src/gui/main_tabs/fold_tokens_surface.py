"""fold_tokens_surface.py -- the Fold Tranches panel's tokens, without Qt.

Describes the colours, sizes, column tooltips, sort orders and composed
row text behind the Fold Tranches panel of the Live Bot Settings window.
That window opens on Detail for a running bot, so every value here
reaches a screen the operator trades from.

``finite_number`` is the admission rule the module reads a stored number
through: exactly ``int`` or ``float``, finite, and inside the range a
float can hold. ``fold_display_order`` and ``fold_row_matches`` decide
which rows the table shows and in what order.
``compose_units_marked_row`` and ``compose_cycle_close_ratio`` return the
panel's two health verdicts, each as text plus the colour it is drawn in.
``extractor_tranche_cells`` and the two tooltip composers build an
Extractor Tranche row.

``table_chrome_px``, ``table_natural_width_px`` and ``health_row_plan``
replace the three helpers that read a live widget. Each takes its
readings as plain numbers, so the arithmetic behind the operator's
window runs with no Qt present. The caller takes the readings off the
polished widget and passes them in.

``FoldTokensModel`` records every step a caller drives, and keeps what it
recorded when a later step refuses.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``fold_tokens.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.live_settings.fold_tokens``, so a value changed on one side
alone is reported. Nothing here imports Qt, and nothing here reads the
clock, the filesystem or the environment -- at import time or later.
"""

from __future__ import annotations

import math
from typing import Any, Optional

METHOD = "fold_tokens.state"

EXTRACTOR_TRANCHE_BG_HEX = "#b3261e"
EXTRACTOR_TRANCHE_FG_HEX = "#ffffff"
FOLD_TRANCHE_BG_HEX = "#123a63"
FOLD_TRANCHE_FG_HEX = "#e0e0f0"
FOLD_TRANCHE_BORDER_HEX = "#6ea6e6"
EXTRACTOR_TRANCHE_BORDER_HEX = "#ffb0a6"

#: A fill this map does not know gets no border, so a future row type is
#: left alone rather than drawn with another type's edge.
TRANCHE_ROW_BORDER_BY_BG = {
    FOLD_TRANCHE_BG_HEX: FOLD_TRANCHE_BORDER_HEX,
    EXTRACTOR_TRANCHE_BG_HEX: EXTRACTOR_TRANCHE_BORDER_HEX,
}

TRANCHE_ROW_BORDER_PX = 2
TRANCHE_ROW_HEIGHT_PX = 30
TRANCHE_FIRE_BTN_INSET_PX = 8

ARBITER_COLUMN_INDEX = 10
ARBITER_COLUMN_HEADER = "Arbiter"

# Six places print an em dash, for six unrelated reasons. Each keeps
# its own name so a change to one cannot move the other five.
ARBITER_NOT_APPLICABLE = "—"
AGE_UNKNOWN = "—"
UNITS_UNKNOWN = "—"
CELL_NOT_APPLICABLE = "—"
NO_MARK_TEXT = "—"
RATIO_NO_DENOMINATOR_TEXT = "—  (nothing left to fold back)"

FOLD_SOURCE_MANUAL_SCRUM = "manual scrum"
FOLD_SOURCE_AUTO_REBALANCE = "auto rebalance"
FOLD_SOURCE_AUTO_SCRUM = "auto scrum"
FOLD_SOURCE_MANUAL_FG_HEX = "#00ccff"

OPERATOR_INITIATED_KEY = "operator_initiated"

FOLD_SOURCE_TOOLTIPS = {
    FOLD_SOURCE_MANUAL_SCRUM: (
        "An operator-pressed Manual Fire created this tranche. That "
        "button runs a rebalance; its SELL leg is a manual SCRUM, and "
        "a scrum is what queues a fold tranche.\n\n"
        "Stored as operator_initiated = true."
    ),
    FOLD_SOURCE_AUTO_REBALANCE: (
        "An AUTONOMOUS rebalance created this tranche: Wire Stack Fire "
        "or Max Cartridge Fire. The bot fired it, not the operator.\n\n"
        "Stored as operator_initiated = false. Which of the two fired "
        "is NOT stored on the tranche, so this panel does not name "
        "it; the trade log carries WIRE_STACK_SCRUM or "
        "CARTRIDGE_SCRUM for the sale itself."
    ),
    FOLD_SOURCE_AUTO_SCRUM: (
        "The ordinary scrum cycle created this tranche, or the DIST "
        "re-fold that follows a distribution sell.\n\n"
        "Those two paths store no operator_initiated key at all, and "
        "that absence is what this label reads."
    ),
}

TRANCHE_TABLE_VISIBLE_ROWS = 18

#: Fallback chrome and header, used only where there is no widget to
#: measure. The builder passes the measured readings instead.
TRANCHE_TABLE_FRAME_PX = 4
TRANCHE_TABLE_HEADER_PX = 24

FOLD_SORT_QUEUE_ORDER = "Queue order"
FOLD_SORT_OLDEST_FIRST = "Oldest first"
FOLD_SORT_NEWEST_FIRST = "Newest first"
FOLD_SORT_LARGEST_FIRST = "Largest USD first"
FOLD_SORT_SMALLEST_FIRST = "Smallest USD first"

#: The offered orders, in the order the combo box lists them. Queue
#: order is first and is the default.
FOLD_SORT_ORDERS = (
    FOLD_SORT_QUEUE_ORDER,
    FOLD_SORT_OLDEST_FIRST,
    FOLD_SORT_NEWEST_FIRST,
    FOLD_SORT_LARGEST_FIRST,
    FOLD_SORT_SMALLEST_FIRST,
)

#: order -> (stored key, descending). Queue order is absent on purpose:
#: it sorts by nothing and returns the list as the bot holds it.
FOLD_SORT_KEYS = {
    FOLD_SORT_OLDEST_FIRST: ("created_ts", False),
    FOLD_SORT_NEWEST_FIRST: ("created_ts", True),
    FOLD_SORT_LARGEST_FIRST: ("usd", True),
    FOLD_SORT_SMALLEST_FIRST: ("usd", False),
}

CREATED_TS_KEY = "created_ts"
USD_KEY = "usd"
UNITS_KEY = "units"

FOLD_COLUMN_TOOLTIPS = (
    "Position of this tranche in the fold queue.",
    "Time since the scrum created this tranche.",
    "Asset units this tranche will buy back.",
    "Cash parked for this tranche's buy-back.",
    "Price per unit at which the scrum sold.",
    "Price per unit first paid. Informational only.",
    "Price the fold gate needs. Not a trigger.",
    "Price gate only. Technical analysis must also agree.",
    "The action that created this tranche.",
    "Buy this tranche back now. Moves real money.",
    "Who may close this Extractor Tranche.",
)

FOLD_SORT_TOOLTIP = "Choose the row order. Unreadable rows stay last."
FOLD_FILTER_TOOLTIP = "Show only rows that contain this text."
FOLD_FILTER_PLACEHOLDER = "Filter rows..."

FOLD_OPEN_COUNT_TOOLTIP = "Fold tranches this bot holds in its queue now."
FOLD_PARKED_USD_TOOLTIP = "Total cash parked by every open fold tranche."
FOLD_OLDEST_AGE_TOOLTIP = "Age of the oldest tranche in this queue."
FOLD_UNITS_MARKED_TOOLTIP = "Asset units the queue claims, against units held."
FOLD_WIRE_DISCARDED_TOOLTIP = "Parked wire credit cleared by this bot, lifetime total."
FOLD_MALFORMED_TOOLTIP = "Stored tranches this bot could not read, lifetime total."
FOLD_CYCLE_CAP_TOOLTIP = "Growth cash one fold cycle may spend, and spent."

FOLD_OPENED_TOOLTIP = "Fold tranches this bot ever opened, less merged ones."
FOLD_CLOSED_TOOLTIP = "Fold tranches that folded back and bought the asset."
FOLD_CLOSE_RATIO_TOOLTIP = (
    "Share of opened tranches that folded back, discards excluded."
)
FOLD_DISCARDED_TOOLTIP = "Fold tranches removed without folding back, lifetime total."
FOLD_COUNTERS_RESET_TOOLTIP = "When an operator last set these four counters to zero."

FOLD_OVER_ALLOTMENT_FG_HEX = "#ff3366"
FOLD_RATIO_RED_FG_HEX = FOLD_OVER_ALLOTMENT_FG_HEX
FOLD_RATIO_AMBER_FG_HEX = "#ff9900"
FOLD_RATIO_GREEN_FG_HEX = "#00ff88"

#: Largest int the admission rule converts, inclusive and symmetric.
#: Above it the rule refuses rather than converting, because the
#: conversion raises.
FLOAT_SAFE_INT = 2**1023

ARBITER_PARENT = "parent"
ARBITER_SIBLING = "sibling"
ARBITER_LABELS = {ARBITER_PARENT: "Parent", ARBITER_SIBLING: "Sibling"}

#: Under five tranches the ratio carries no colour: too few to judge.
RATIO_MIN_DENOMINATOR = 5
RATIO_RED_BELOW = 0.5
RATIO_AMBER_BELOW = 0.8

#: Above one the queue claims more asset than the bot owns.
OVER_ALLOTMENT_ABOVE = 1.0

NO_COLOUR: Optional[str] = None

EXTRACTOR_ROW_INDEX_TEXT = "EXT"
EXTRACTOR_SOURCE_FORMAT = "extractor {pair}"
EXTRACTOR_UNKNOWN_PAIR = "?"
EXTRACTOR_UNKNOWN_FIELD = "?"
EXTRACTOR_DEFAULT_BASE_ASSET = "base"

MARKED_FORMAT = "{marked:,.6f} marked"
UNREADABLE_FORMAT = "  (+{unreadable} unreadable)"
HOLDINGS_UNREADABLE_TEXT = " / holdings unreadable"
HELD_FORMAT = " / {held:,.6f} held"
RATIO_FORMAT = "  ({ratio:,.2f}x)"
CLOSE_RATIO_FORMAT = "{ratio:.2%}  ({closed}/{denominator})"
UNITS_CELL_FORMAT = "{units:.6f}"
MARK_USD_FORMAT = "${mark_usd:,.4f}"

SECONDS_PER_DAY = 86400
SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60
DAYS_FORMAT = "{days}d {hours}h"
HOURS_FORMAT = "{hours}h {minutes}m"
MINUTES_FORMAT = "{minutes}m"

#: The ten fold columns an Extractor Tranche row fills, by index.
EXTRACTOR_CELL_COUNT = 10
EXTRACTOR_INDEX_COLUMN = 0
EXTRACTOR_AGE_COLUMN = 1
EXTRACTOR_UNITS_COLUMN = 2
EXTRACTOR_USD_COLUMN = 3
EXTRACTOR_STATE_COLUMN = 7
EXTRACTOR_SOURCE_COLUMN = 8

ARBITER_TOOLTIP_FORMAT = (
    "ARBITER: {label} — who may close THIS Extractor Tranche.\n"
    "\n"
    "Parent — the base-currency Scrumming Bot force-sells this "
    "tranche at x% of growth.\n"
    "Sibling — the Extractor does all the work and the parent "
    "stands back.\n"
    "\n"
    "RECORDS A DECISION, MOVES NO MONEY. Clicking this places no "
    "order, cancels none, and changes no balance or Target "
    "Balance. It writes one value on this tranche and nothing "
    "else.\n"
    "\n"
    "NOT YET ACTED ON. The parent force-sell that 'Parent' names "
    "is not built, so today a Parent tranche behaves exactly like "
    "a Sibling one. The value is stored and survives a restart, "
    "ready for the unit that builds it.\n"
    "\n"
    "Per tranche, not per bot. Every Extractor Tranche carries its "
    "own Arbiter."
)

EXTRACTOR_TOOLTIP_HEADING = "EXTRACTOR TRANCHE — not this bot's inventory."
EXTRACTOR_TOOLTIP_CHILD_FORMAT = "Child bot: {name} ({bot_id})"
EXTRACTOR_TOOLTIP_PAIR_FORMAT = "Pair: {pair}"
EXTRACTOR_TOOLTIP_STATE_FORMAT = "State: {state}"
# Both take text already formatted, so a refused figure can print the
# em dash where a float format would raise.
EXTRACTOR_TOOLTIP_LEASE_FORMAT = (
    "{base_deployed} {base_asset} of this bot's asset is leased to that Extractor."
)
EXTRACTOR_TOOLTIP_ALT_FORMAT = "Alt units held: {alt_units}"
EXTRACTOR_TOOLTIP_FIGURE_FORMAT = "{figure:.8f}"
EXTRACTOR_TOOLTIP_MARK_FORMAT = (
    "Last mark: {mark_price:.8f} {base_asset} per alt unit, recorded by "
    "the Extractor's own tick."
)
EXTRACTOR_TOOLTIP_NO_MARK = (
    "No mark available — this position has not been priced since it "
    "was loaded. The USD column shows an em dash rather than "
    "substituting cost basis."
)
EXTRACTOR_TOOLTIP_FOOTER = (
    "This row is a RECORD, not inventory. It is not in this bot's fold "
    "queue and not in its lots, so no gate, no SCRUM sizing and no "
    "fold-back can act on it. There is no Fire button because the "
    "parent does not close a child's position."
)

STEP_FINITE = "finite_number"
STEP_ORDER = "fold_display_order"
STEP_FILTER = "fold_row_matches"
STEP_HEIGHT = "table_max_height_px"
STEP_CHROME = "table_chrome_px"
STEP_WIDTH = "table_natural_width_px"
STEP_HEALTH_ROW = "health_row_plan"
STEP_UNITS_ROW = "compose_units_marked_row"
STEP_RATIO = "compose_cycle_close_ratio"
STEP_SOURCE = "fold_source_label"
STEP_ARBITER = "arbiter_label"
STEP_ARBITER_TIP = "arbiter_tooltip"
STEP_AGE = "format_tranche_age"
STEP_CELLS = "extractor_tranche_cells"
STEP_EXTRACTOR_TIP = "extractor_tranche_tooltip"
STEP_BORDER = "row_border_hex"

STEP_NAMES = (
    STEP_FINITE,
    STEP_ORDER,
    STEP_FILTER,
    STEP_HEIGHT,
    STEP_CHROME,
    STEP_WIDTH,
    STEP_HEALTH_ROW,
    STEP_UNITS_ROW,
    STEP_RATIO,
    STEP_SOURCE,
    STEP_ARBITER,
    STEP_ARBITER_TIP,
    STEP_AGE,
    STEP_CELLS,
    STEP_EXTRACTOR_TIP,
    STEP_BORDER,
)


def finite_number(value: Any) -> Optional[float]:
    """`value` as a float when it is EXACTLY int or float AND finite.

    None for everything else, and None is an answer rather than an
    error. ``bool`` is refused by exact type, so a stored ``True`` never
    reads as the number one. An int outside the float range is refused
    by comparison rather than converted, because the conversion raises.
    """
    if type(value) is float:
        return value if math.isfinite(value) else None
    if type(value) is int and -FLOAT_SAFE_INT <= value <= FLOAT_SAFE_INT:
        return float(value)
    return None


def normalize_arbiter(value: Any) -> str:
    """Coerce anything at all to one of the two stored arbiter values.

    Only the exact text ``parent``, stripped and lower-cased, reads as
    parent. Everything else lands on sibling, the value that describes
    what the code already does. Never raises.
    """
    if not isinstance(value, str):
        return ARBITER_SIBLING
    text = value.strip().lower()
    return ARBITER_PARENT if text == ARBITER_PARENT else ARBITER_SIBLING


def arbiter_label(value: Any) -> str:
    """The operator-facing word for a stored arbiter value."""
    return ARBITER_LABELS[normalize_arbiter(value)]


def row_border_hex(background_hex: Any) -> Optional[str]:
    """The border a tranche row gets for its fill.

    None for a fill the map does not know, so a future row type is left
    alone rather than drawn with another type's edge.
    """
    return TRANCHE_ROW_BORDER_BY_BG.get(background_hex)


def table_chrome_px(frame_width_px: Any, hscroll_height_px: Any) -> int:
    """Vertical pixels a polished table spends on what is not a row.

    Frame top plus bottom, plus the horizontal scroll bar, which is
    reserved whether or not it appears. Both readings are taken off the
    polished widget by the caller; an unpolished frame width under-counts
    the frame and hides a row.
    """
    return 2 * int(frame_width_px) + int(hscroll_height_px)


def table_max_height_px(
    row_count: Any,
    header_px: Any = TRANCHE_TABLE_HEADER_PX,
    chrome_px: Any = TRANCHE_TABLE_FRAME_PX,
) -> int:
    """Height cap that shows up to `TRANCHE_TABLE_VISIBLE_ROWS` rows.

    A short queue keeps a short box: the cap follows the row count until
    it reaches the ceiling. A cap budgeting less chrome than the widget
    spends is subtracted from the rows, so a one-row table would draw its
    header and nothing else.
    """
    visible = max(1, min(int(row_count or 0), TRANCHE_TABLE_VISIBLE_ROWS))
    return visible * TRANCHE_ROW_HEIGHT_PX + int(header_px) + int(chrome_px)


def table_natural_width_px(
    header_length_px: Any,
    frame_width_px: Any,
    vheader_present: bool = True,
    vheader_hidden: bool = False,
    vheader_width_px: Any = 0,
    vscroll_present: bool = True,
    vscroll_width_px: Any = 0,
) -> int:
    """Table width that leaves the viewport as wide as the columns.

    `header_length_px` is the summed column width, the number a scroll
    area's own size hint omits. Added to it, all outside the viewport:
    the vertical header when there is one and it is shown, both frame
    edges, and the vertical scroll bar when there is one, which is
    reserved whether or not it appears.

    A missing vertical header and a hidden one are separate inputs. Both
    add nothing, and keeping them apart means a table that lost its
    header does not read as one that merely hid it.
    """
    width = int(header_length_px) + 2 * int(frame_width_px)
    if vheader_present and not vheader_hidden:
        width += int(vheader_width_px)
    if vscroll_present:
        width += int(vscroll_width_px)
    return width


def health_row_plan(label_text: str, tooltip: str, label_exists: bool = True) -> dict:
    """What one summary row sets, on the value and on its own label.

    A form builds the label itself, so a tooltip set on the value alone
    leaves the words the operator points at bare. `label_exists` is False
    where the form holds no label for the value -- a row added
    widget-only -- and the plan then tooltips the value alone.
    """
    return {
        "row_added": True,
        "label_text": label_text,
        "widget_tooltip": tooltip,
        "label_tooltip": tooltip if label_exists else None,
        "returns_widget": True,
    }


def fold_display_order(tranches: Any, order: Any) -> list:
    """`(queue_index, tranche)` pairs in the chosen order.

    The queue index travels with the row, so re-ordering the display
    never renumbers a tranche. A row whose sort key is absent, the wrong
    type or not a finite number keeps queue order and goes last, where it
    can be seen, rather than being coerced to zero and sorted to the top
    of a smallest-first list.

    The queue index is the tie-break in both directions, so two tranches
    created in the same second keep the order the bot holds them in.
    """
    pairs = list(enumerate(list(tranches or [])))
    spec = FOLD_SORT_KEYS.get(order)
    if spec is None:
        return pairs
    field, descending = spec
    readable: list = []
    refused: list = []
    for index, tranche in pairs:
        value = finite_number(tranche.get(field)) if isinstance(tranche, dict) else None
        if value is None:
            refused.append((index, tranche))
        else:
            readable.append((index, tranche, value))
    if descending:
        readable.sort(key=lambda row: (-row[2], row[0]))
    else:
        readable.sort(key=lambda row: (row[2], row[0]))
    return [(index, tranche) for index, tranche, _ in readable] + refused


def fold_row_matches(cell_texts: Any, needle: Any) -> bool:
    """True when a rendered cell of the row holds `needle`.

    Reads the cells the table already composed, so the filter can never
    surface a quantity the table does not show. An empty or blank needle
    matches everything, so clearing the box restores the whole queue.
    """
    text = str(needle or "").strip().casefold()
    if not text:
        return True
    return any(text in str(cell or "").casefold() for cell in cell_texts)


def fold_source_label(tranche: dict) -> str:
    """Name the action that CREATED this fold tranche.

    Three answers, because the stored record distinguishes three cases:
    the flag truthy, the flag stored falsey, and the key absent. A falsey
    non-bool takes the autonomous branch, which is the shipped test.
    """
    if tranche.get(OPERATOR_INITIATED_KEY):
        return FOLD_SOURCE_MANUAL_SCRUM
    if OPERATOR_INITIATED_KEY in tranche:
        return FOLD_SOURCE_AUTO_REBALANCE
    return FOLD_SOURCE_AUTO_SCRUM


def compose_units_marked_row(tranches: Any, holdings: Any) -> tuple:
    """`(text, colour_hex_or_None)` for the allotment row.

    An unreadable ``units`` is counted beside the number, never added as
    zero: a refused contributor rides beside the total instead of quietly
    lowering it. No ratio is printed without holdings, because a ratio
    against zero is not a large number, it is not a number.
    """
    marked = 0.0
    unreadable = 0
    for tranche in list(tranches or []):
        value = (
            finite_number(tranche.get(UNITS_KEY, 0))
            if isinstance(tranche, dict)
            else None
        )
        if value is None:
            unreadable += 1
        else:
            marked += value
    text = MARKED_FORMAT.format(marked=marked)
    if unreadable:
        text += UNREADABLE_FORMAT.format(unreadable=unreadable)
    held = finite_number(holdings)
    if held is None:
        return (text + HOLDINGS_UNREADABLE_TEXT, NO_COLOUR)
    if held <= 0:
        return (text + HELD_FORMAT.format(held=held), NO_COLOUR)
    ratio = marked / held
    text += HELD_FORMAT.format(held=held) + RATIO_FORMAT.format(ratio=ratio)
    if ratio > OVER_ALLOTMENT_ABOVE:
        return (text, FOLD_OVER_ALLOTMENT_FG_HEX)
    return (text, NO_COLOUR)


def compose_cycle_close_ratio(created: Any, closed: Any, discarded: Any) -> tuple:
    """`(text, colour_hex_or_None)` for the cycle close ratio.

    Of every tranche this bot opened and did not discard, the share that
    folded back. A tranche still standing stays in the denominator, which
    is what makes a stagnating queue show up here. With nothing left to
    fold back there is no denominator, and the row says so rather than
    printing a number whose healthy and broken values are both 100%.
    """
    denominator = int(created) - int(discarded)
    if denominator <= 0:
        return (RATIO_NO_DENOMINATOR_TEXT, NO_COLOUR)
    ratio = int(closed) / denominator
    text = CLOSE_RATIO_FORMAT.format(
        ratio=ratio, closed=int(closed), denominator=denominator
    )
    if denominator < RATIO_MIN_DENOMINATOR:
        return (text, NO_COLOUR)
    if ratio < RATIO_RED_BELOW:
        return (text, FOLD_RATIO_RED_FG_HEX)
    if ratio < RATIO_AMBER_BELOW:
        return (text, FOLD_RATIO_AMBER_FG_HEX)
    return (text, FOLD_RATIO_GREEN_FG_HEX)


def arbiter_tooltip(value: Any) -> str:
    """Explain the Arbiter toggle without overstating what it does.

    The parent force-sell the ``Parent`` value names is not built, so the
    tooltip says the toggle records a decision and moves no money.
    """
    return ARBITER_TOOLTIP_FORMAT.format(label=arbiter_label(value))


def format_tranche_age(seconds: Any) -> str:
    """Coarse age for a tranche row: ``3d 4h``, ``12m``, or an em dash.

    A missing age and a negative one both print the dash. A value that is
    not a number raises; every caller admits its seconds through
    ``finite_number`` first.
    """
    if seconds is None or seconds < 0:
        return AGE_UNKNOWN
    total = int(seconds)
    days, rem = divmod(total, SECONDS_PER_DAY)
    hours, rem = divmod(rem, SECONDS_PER_HOUR)
    minutes = rem // SECONDS_PER_MINUTE
    if days:
        return DAYS_FORMAT.format(days=days, hours=hours)
    if hours:
        return HOURS_FORMAT.format(hours=hours, minutes=minutes)
    return MINUTES_FORMAT.format(minutes=minutes)


def extractor_tranche_cells(row: dict, now_ts: float) -> list:
    """The ten cell strings for one Extractor Tranche row.

    Every column that would mix denominations prints an em dash: the
    price columns carry the parent asset's price per unit, and an
    Extractor Tranche's prices are quoted in base per alt. ``USD parked``
    carries the marked value when the child has priced the position, and
    an em dash when it has not, never cost basis.

    ``now_ts`` is passed in. Nothing here reads the clock.

    ``opened_at``, ``base_deployed`` and ``mark_value_usd`` all pass the
    admission rule, so Age, Units and ``USD parked`` each print an em
    dash on a value that is not a finite number rather than a figure the
    bot does not hold.
    """
    opened = finite_number(row.get("opened_at"))
    age = (
        format_tranche_age(now_ts - opened)
        if opened is not None and opened > 0
        else AGE_UNKNOWN
    )
    units = finite_number(row.get("base_deployed"))
    units_text = (
        UNITS_CELL_FORMAT.format(units=units) if units is not None else UNITS_UNKNOWN
    )
    mark_usd = finite_number(row.get("mark_value_usd"))
    usd_text = (
        MARK_USD_FORMAT.format(mark_usd=mark_usd)
        if mark_usd is not None
        else NO_MARK_TEXT
    )
    state = str(row.get("state", "") or CELL_NOT_APPLICABLE)
    pair = str(row.get("pair", "") or EXTRACTOR_UNKNOWN_PAIR)
    return [
        EXTRACTOR_ROW_INDEX_TEXT,
        age,
        units_text,
        usd_text,
        CELL_NOT_APPLICABLE,
        CELL_NOT_APPLICABLE,
        CELL_NOT_APPLICABLE,
        state,
        EXTRACTOR_SOURCE_FORMAT.format(pair=pair),
        CELL_NOT_APPLICABLE,
    ]


def extractor_tranche_tooltip(row: dict) -> str:
    """Explain one Extractor Tranche row, units included.

    Carries what the columns cannot: which child holds the lease, the
    alt-denominated figures, and, where there is no mark, the fact that
    no mark exists rather than a number standing in for one. A leased
    amount or an alt holding that is not a finite number prints an em
    dash, the same mark the cell beside it shows.
    """
    base_asset = row.get("base_asset", "") or EXTRACTOR_DEFAULT_BASE_ASSET
    deployed = finite_number(row.get("base_deployed"))
    alt_units = finite_number(row.get("alt_units"))
    lines = [
        EXTRACTOR_TOOLTIP_HEADING,
        "",
        EXTRACTOR_TOOLTIP_CHILD_FORMAT.format(
            name=row.get("child_bot_name", EXTRACTOR_UNKNOWN_FIELD),
            bot_id=row.get("child_bot_id", EXTRACTOR_UNKNOWN_FIELD),
        ),
        EXTRACTOR_TOOLTIP_PAIR_FORMAT.format(
            pair=row.get("pair", EXTRACTOR_UNKNOWN_FIELD)
        ),
        EXTRACTOR_TOOLTIP_STATE_FORMAT.format(
            state=row.get("state", EXTRACTOR_UNKNOWN_FIELD)
        ),
        "",
        EXTRACTOR_TOOLTIP_LEASE_FORMAT.format(
            base_deployed=(
                EXTRACTOR_TOOLTIP_FIGURE_FORMAT.format(figure=deployed)
                if deployed is not None
                else UNITS_UNKNOWN
            ),
            base_asset=base_asset,
        ),
        EXTRACTOR_TOOLTIP_ALT_FORMAT.format(
            alt_units=(
                EXTRACTOR_TOOLTIP_FIGURE_FORMAT.format(figure=alt_units)
                if alt_units is not None
                else UNITS_UNKNOWN
            )
        ),
    ]
    mark_price = finite_number(row.get("mark_price_base_per_alt"))
    if mark_price is not None:
        lines.append(
            EXTRACTOR_TOOLTIP_MARK_FORMAT.format(
                mark_price=mark_price, base_asset=base_asset
            )
        )
    else:
        lines.append(EXTRACTOR_TOOLTIP_NO_MARK)
    lines += ["", EXTRACTOR_TOOLTIP_FOOTER]
    return "\n".join(lines)


STEP_HANDLERS = {
    STEP_FINITE: finite_number,
    STEP_ORDER: fold_display_order,
    STEP_FILTER: fold_row_matches,
    STEP_HEIGHT: table_max_height_px,
    STEP_CHROME: table_chrome_px,
    STEP_WIDTH: table_natural_width_px,
    STEP_HEALTH_ROW: health_row_plan,
    STEP_UNITS_ROW: compose_units_marked_row,
    STEP_RATIO: compose_cycle_close_ratio,
    STEP_SOURCE: fold_source_label,
    STEP_ARBITER: arbiter_label,
    STEP_ARBITER_TIP: arbiter_tooltip,
    STEP_AGE: format_tranche_age,
    STEP_CELLS: extractor_tranche_cells,
    STEP_EXTRACTOR_TIP: extractor_tranche_tooltip,
    STEP_BORDER: row_border_hex,
}

UNKNOWN_STEP_REFUSAL = LookupError


def plain(value: Any) -> Any:
    """`value` as JSON-safe data, tuples flattened to lists.

    A float the encoder cannot carry -- an infinity or a not-a-number --
    becomes its own text, so a step that produced one is still reported
    rather than breaking the frame.
    """
    if isinstance(value, (list, tuple)):
        return [plain(inner) for inner in value]
    if isinstance(value, dict):
        return {str(key): plain(inner) for key, inner in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    return value


class FoldTokensModel:
    """The panel's driven state: every step run, in the order it ran.

    ``run`` records a step only after it answers, so a step that refuses
    leaves every earlier record in place. ``refused`` names the step that
    raised, by index, name and refusal type. The wording is not kept,
    because the platform words a refusal differently by operand type and
    by release.
    """

    def __init__(self) -> None:
        self.calls: list = []
        self.refused: Optional[dict] = None

    def run(self, name: str, *args: Any) -> Any:
        """Run one named step, record it, and re-raise what it raises."""
        index = len(self.calls)
        if name not in STEP_HANDLERS:
            self.refused = {
                "index": index,
                "step": name,
                "refusal_type": UNKNOWN_STEP_REFUSAL.__name__,
            }
            raise UNKNOWN_STEP_REFUSAL(name)
        try:
            answer = STEP_HANDLERS[name](*args)
        except Exception as exc:
            self.refused = {
                "index": index,
                "step": name,
                "refusal_type": type(exc).__name__,
            }
            raise
        self.calls.append([name, plain(answer)])
        return answer

    def run_steps(self, steps: Any) -> dict:
        """Run a sequence, stopping at the first step that refuses.

        Returns what ran, what refused and how many steps were reached,
        so a caller sees the records taken before the refusal.
        """
        self.refused = None
        ran = 0
        for step in list(steps or []):
            name = step[0] if isinstance(step, (list, tuple)) and step else str(step)
            args = list(step[1:]) if isinstance(step, (list, tuple)) else []
            try:
                self.run(name, *args)
            except Exception:
                break
            ran += 1
        return {
            "ran": ran,
            "calls": [list(call) for call in self.calls],
            "refused": dict(self.refused) if self.refused else None,
        }


def tokens() -> dict:
    """Every exported value this surface carries, keyed by its name."""
    return {
        "METHOD": METHOD,
        "EXTRACTOR_TRANCHE_BG_HEX": EXTRACTOR_TRANCHE_BG_HEX,
        "EXTRACTOR_TRANCHE_FG_HEX": EXTRACTOR_TRANCHE_FG_HEX,
        "FOLD_TRANCHE_BG_HEX": FOLD_TRANCHE_BG_HEX,
        "FOLD_TRANCHE_FG_HEX": FOLD_TRANCHE_FG_HEX,
        "FOLD_TRANCHE_BORDER_HEX": FOLD_TRANCHE_BORDER_HEX,
        "EXTRACTOR_TRANCHE_BORDER_HEX": EXTRACTOR_TRANCHE_BORDER_HEX,
        "TRANCHE_ROW_BORDER_BY_BG": dict(TRANCHE_ROW_BORDER_BY_BG),
        "TRANCHE_ROW_BORDER_PX": TRANCHE_ROW_BORDER_PX,
        "TRANCHE_ROW_HEIGHT_PX": TRANCHE_ROW_HEIGHT_PX,
        "TRANCHE_FIRE_BTN_INSET_PX": TRANCHE_FIRE_BTN_INSET_PX,
        "ARBITER_COLUMN_INDEX": ARBITER_COLUMN_INDEX,
        "ARBITER_COLUMN_HEADER": ARBITER_COLUMN_HEADER,
        "ARBITER_NOT_APPLICABLE": ARBITER_NOT_APPLICABLE,
        "AGE_UNKNOWN": AGE_UNKNOWN,
        "CELL_NOT_APPLICABLE": CELL_NOT_APPLICABLE,
        "NO_MARK_TEXT": NO_MARK_TEXT,
        "RATIO_NO_DENOMINATOR_TEXT": RATIO_NO_DENOMINATOR_TEXT,
        "FOLD_SOURCE_MANUAL_SCRUM": FOLD_SOURCE_MANUAL_SCRUM,
        "FOLD_SOURCE_AUTO_REBALANCE": FOLD_SOURCE_AUTO_REBALANCE,
        "FOLD_SOURCE_AUTO_SCRUM": FOLD_SOURCE_AUTO_SCRUM,
        "FOLD_SOURCE_MANUAL_FG_HEX": FOLD_SOURCE_MANUAL_FG_HEX,
        "OPERATOR_INITIATED_KEY": OPERATOR_INITIATED_KEY,
        "FOLD_SOURCE_TOOLTIPS": dict(FOLD_SOURCE_TOOLTIPS),
        "TRANCHE_TABLE_VISIBLE_ROWS": TRANCHE_TABLE_VISIBLE_ROWS,
        "TRANCHE_TABLE_FRAME_PX": TRANCHE_TABLE_FRAME_PX,
        "TRANCHE_TABLE_HEADER_PX": TRANCHE_TABLE_HEADER_PX,
        "FOLD_SORT_QUEUE_ORDER": FOLD_SORT_QUEUE_ORDER,
        "FOLD_SORT_OLDEST_FIRST": FOLD_SORT_OLDEST_FIRST,
        "FOLD_SORT_NEWEST_FIRST": FOLD_SORT_NEWEST_FIRST,
        "FOLD_SORT_LARGEST_FIRST": FOLD_SORT_LARGEST_FIRST,
        "FOLD_SORT_SMALLEST_FIRST": FOLD_SORT_SMALLEST_FIRST,
        "FOLD_SORT_ORDERS": list(FOLD_SORT_ORDERS),
        "FOLD_SORT_KEYS": {key: list(spec) for key, spec in FOLD_SORT_KEYS.items()},
        "CREATED_TS_KEY": CREATED_TS_KEY,
        "USD_KEY": USD_KEY,
        "UNITS_KEY": UNITS_KEY,
        "FOLD_COLUMN_TOOLTIPS": list(FOLD_COLUMN_TOOLTIPS),
        "FOLD_SORT_TOOLTIP": FOLD_SORT_TOOLTIP,
        "FOLD_FILTER_TOOLTIP": FOLD_FILTER_TOOLTIP,
        "FOLD_FILTER_PLACEHOLDER": FOLD_FILTER_PLACEHOLDER,
        "FOLD_OPEN_COUNT_TOOLTIP": FOLD_OPEN_COUNT_TOOLTIP,
        "FOLD_PARKED_USD_TOOLTIP": FOLD_PARKED_USD_TOOLTIP,
        "FOLD_OLDEST_AGE_TOOLTIP": FOLD_OLDEST_AGE_TOOLTIP,
        "FOLD_UNITS_MARKED_TOOLTIP": FOLD_UNITS_MARKED_TOOLTIP,
        "FOLD_WIRE_DISCARDED_TOOLTIP": FOLD_WIRE_DISCARDED_TOOLTIP,
        "FOLD_MALFORMED_TOOLTIP": FOLD_MALFORMED_TOOLTIP,
        "FOLD_CYCLE_CAP_TOOLTIP": FOLD_CYCLE_CAP_TOOLTIP,
        "FOLD_OPENED_TOOLTIP": FOLD_OPENED_TOOLTIP,
        "FOLD_CLOSED_TOOLTIP": FOLD_CLOSED_TOOLTIP,
        "FOLD_CLOSE_RATIO_TOOLTIP": FOLD_CLOSE_RATIO_TOOLTIP,
        "FOLD_DISCARDED_TOOLTIP": FOLD_DISCARDED_TOOLTIP,
        "FOLD_COUNTERS_RESET_TOOLTIP": FOLD_COUNTERS_RESET_TOOLTIP,
        "FOLD_OVER_ALLOTMENT_FG_HEX": FOLD_OVER_ALLOTMENT_FG_HEX,
        "FOLD_RATIO_RED_FG_HEX": FOLD_RATIO_RED_FG_HEX,
        "FOLD_RATIO_AMBER_FG_HEX": FOLD_RATIO_AMBER_FG_HEX,
        "FOLD_RATIO_GREEN_FG_HEX": FOLD_RATIO_GREEN_FG_HEX,
        "FLOAT_SAFE_INT": str(FLOAT_SAFE_INT),
        "ARBITER_PARENT": ARBITER_PARENT,
        "ARBITER_SIBLING": ARBITER_SIBLING,
        "ARBITER_LABELS": dict(ARBITER_LABELS),
        "RATIO_MIN_DENOMINATOR": RATIO_MIN_DENOMINATOR,
        "RATIO_RED_BELOW": RATIO_RED_BELOW,
        "RATIO_AMBER_BELOW": RATIO_AMBER_BELOW,
        "OVER_ALLOTMENT_ABOVE": OVER_ALLOTMENT_ABOVE,
        "NO_COLOUR": NO_COLOUR,
        "EXTRACTOR_ROW_INDEX_TEXT": EXTRACTOR_ROW_INDEX_TEXT,
        "EXTRACTOR_SOURCE_FORMAT": EXTRACTOR_SOURCE_FORMAT,
        "EXTRACTOR_UNKNOWN_PAIR": EXTRACTOR_UNKNOWN_PAIR,
        "EXTRACTOR_UNKNOWN_FIELD": EXTRACTOR_UNKNOWN_FIELD,
        "EXTRACTOR_DEFAULT_BASE_ASSET": EXTRACTOR_DEFAULT_BASE_ASSET,
        "MARKED_FORMAT": MARKED_FORMAT,
        "UNREADABLE_FORMAT": UNREADABLE_FORMAT,
        "HOLDINGS_UNREADABLE_TEXT": HOLDINGS_UNREADABLE_TEXT,
        "HELD_FORMAT": HELD_FORMAT,
        "RATIO_FORMAT": RATIO_FORMAT,
        "CLOSE_RATIO_FORMAT": CLOSE_RATIO_FORMAT,
        "UNITS_CELL_FORMAT": UNITS_CELL_FORMAT,
        "MARK_USD_FORMAT": MARK_USD_FORMAT,
        "SECONDS_PER_DAY": SECONDS_PER_DAY,
        "SECONDS_PER_HOUR": SECONDS_PER_HOUR,
        "SECONDS_PER_MINUTE": SECONDS_PER_MINUTE,
        "DAYS_FORMAT": DAYS_FORMAT,
        "HOURS_FORMAT": HOURS_FORMAT,
        "MINUTES_FORMAT": MINUTES_FORMAT,
        "EXTRACTOR_CELL_COUNT": EXTRACTOR_CELL_COUNT,
        "EXTRACTOR_INDEX_COLUMN": EXTRACTOR_INDEX_COLUMN,
        "EXTRACTOR_AGE_COLUMN": EXTRACTOR_AGE_COLUMN,
        "EXTRACTOR_UNITS_COLUMN": EXTRACTOR_UNITS_COLUMN,
        "EXTRACTOR_USD_COLUMN": EXTRACTOR_USD_COLUMN,
        "EXTRACTOR_STATE_COLUMN": EXTRACTOR_STATE_COLUMN,
        "EXTRACTOR_SOURCE_COLUMN": EXTRACTOR_SOURCE_COLUMN,
        "ARBITER_TOOLTIP_FORMAT": ARBITER_TOOLTIP_FORMAT,
        "EXTRACTOR_TOOLTIP_HEADING": EXTRACTOR_TOOLTIP_HEADING,
        "EXTRACTOR_TOOLTIP_CHILD_FORMAT": EXTRACTOR_TOOLTIP_CHILD_FORMAT,
        "EXTRACTOR_TOOLTIP_PAIR_FORMAT": EXTRACTOR_TOOLTIP_PAIR_FORMAT,
        "EXTRACTOR_TOOLTIP_STATE_FORMAT": EXTRACTOR_TOOLTIP_STATE_FORMAT,
        "EXTRACTOR_TOOLTIP_LEASE_FORMAT": EXTRACTOR_TOOLTIP_LEASE_FORMAT,
        "EXTRACTOR_TOOLTIP_ALT_FORMAT": EXTRACTOR_TOOLTIP_ALT_FORMAT,
        "EXTRACTOR_TOOLTIP_MARK_FORMAT": EXTRACTOR_TOOLTIP_MARK_FORMAT,
        "EXTRACTOR_TOOLTIP_NO_MARK": EXTRACTOR_TOOLTIP_NO_MARK,
        "EXTRACTOR_TOOLTIP_FOOTER": EXTRACTOR_TOOLTIP_FOOTER,
        "STEP_FINITE": STEP_FINITE,
        "STEP_ORDER": STEP_ORDER,
        "STEP_FILTER": STEP_FILTER,
        "STEP_HEIGHT": STEP_HEIGHT,
        "STEP_CHROME": STEP_CHROME,
        "STEP_WIDTH": STEP_WIDTH,
        "STEP_HEALTH_ROW": STEP_HEALTH_ROW,
        "STEP_UNITS_ROW": STEP_UNITS_ROW,
        "STEP_RATIO": STEP_RATIO,
        "STEP_SOURCE": STEP_SOURCE,
        "STEP_ARBITER": STEP_ARBITER,
        "STEP_ARBITER_TIP": STEP_ARBITER_TIP,
        "STEP_AGE": STEP_AGE,
        "STEP_CELLS": STEP_CELLS,
        "STEP_EXTRACTOR_TIP": STEP_EXTRACTOR_TIP,
        "STEP_BORDER": STEP_BORDER,
        "STEP_NAMES": list(STEP_NAMES),
        "UNKNOWN_STEP_REFUSAL": UNKNOWN_STEP_REFUSAL.__name__,
    }


#: The panel wires no signal, runs no timer and reaches no event bus.
#: Declared so a counter comparing the two sides has a value to read.
ACTIONS: dict = {}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
BUS_EMITS: tuple = ()


def build_view_model(model: FoldTokensModel, steps: Any = None) -> dict:
    """The whole surface as data: its tokens, its steps and what ran."""
    driven = model.run_steps(steps)
    return {
        "method": METHOD,
        "tokens": tokens(),
        "step_names": list(STEP_NAMES),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "bus_emits": list(BUS_EMITS),
        "ran": driven["ran"],
        "calls": driven["calls"],
        "refused": driven["refused"],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``fold_tokens.state``.

    Reads ``steps``, a list of ``[step_name, *args]`` the caller wants
    driven. Each request builds its own model, so one request never reads
    the steps another request drove and two requests cannot interleave.
    """
    return build_view_model(FoldTokensModel(), (params or {}).get("steps"))
