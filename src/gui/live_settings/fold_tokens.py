"""Constants and pure helpers behind the Fold Tranches panel.

Qt appears in annotations only, so every helper here is testable without
a QApplication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import design_system as ds

if TYPE_CHECKING:
    from PySide6.QtWidgets import QFormLayout, QTableWidget, QWidget


# White on EXTRACTOR_TRANCHE_SURFACE measures 6.54:1, clearing WCAG AA.
EXTRACTOR_TRANCHE_BG_HEX = ds.EXTRACTOR_TRANCHE_SURFACE
EXTRACTOR_TRANCHE_FG_HEX = ds.TEXT_MAX


# A foreground must be set explicitly; the theme's own text measures 1.47:1 here.
FOLD_TRANCHE_BG_HEX = ds.FOLD_TRANCHE_SURFACE
FOLD_TRANCHE_FG_HEX = ds.TEXT_HIGH


# No shared colour clears WCAG SC 1.4.11's 3:1 against both fills.
FOLD_TRANCHE_BORDER_HEX = ds.FOLD_TRANCHE_BORDER
EXTRACTOR_TRANCHE_BORDER_HEX = ds.EXTRACTOR_TRANCHE_BORDER

# Keyed off the cell's own background brush, not row index, so a table
# reorder can never mis-colour a border. An unlisted fill gets none.
TRANCHE_ROW_BORDER_BY_BG = {
    FOLD_TRANCHE_BG_HEX: FOLD_TRANCHE_BORDER_HEX,
    EXTRACTOR_TRANCHE_BG_HEX: EXTRACTOR_TRANCHE_BORDER_HEX,
}

# Thick enough to read as a container edge at the table's row height.
TRANCHE_ROW_BORDER_PX = 2

# Row height a fill needs to read as a container band, not a stripe.
TRANCHE_ROW_HEIGHT_PX = 30

# Clearance so the Fire button, painted over the delegate, does not
# cover the border rule at its own column.
TRANCHE_FIRE_BTN_INSET_PX = 8


# Appended after column 9 (Fire), which dispatches a real market buy.
ARBITER_COLUMN_INDEX = 10
ARBITER_COLUMN_HEADER = "Arbiter"

# A fold tranche has no Arbiter; only an Extractor Tranche does.
ARBITER_NOT_APPLICABLE = "—"

FOLD_SOURCE_MANUAL_SCRUM = "manual scrum"
FOLD_SOURCE_AUTO_REBALANCE = "auto rebalance"
FOLD_SOURCE_AUTO_SCRUM = "auto scrum"

# `ds.FOLD_SOURCE_MANUAL` (#00ccff) measures 6.12:1 on the fold fill,
# per `_paint_fold_tranche_row`.
FOLD_SOURCE_MANUAL_FG_HEX = ds.FOLD_SOURCE_MANUAL

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

# Fallback only; the builder passes the measured `fold_table_chrome_px(table)`.
TRANCHE_TABLE_FRAME_PX = 4

# Fallback only; the builder passes the real
# `horizontalHeader().sizeHint().height()`.
TRANCHE_TABLE_HEADER_PX = 24


def fold_table_chrome_px(table: QTableWidget) -> int:
    """Vertical pixels this table spends on what is not a row.

    Frame top plus bottom, plus the horizontal scroll bar; the header
    is measured by the caller. Calls `ensurePolished` first: an
    unpolished table reports `frameWidth() == 1` where the resolved
    theme reports 13. The scroll bar is reserved whether or not it is
    drawn, since its presence is not knowable until layout.
    """
    table.ensurePolished()
    return 2 * int(table.frameWidth()) + int(
        table.horizontalScrollBar().sizeHint().height()
    )


def fold_table_max_height_px(
    row_count: int,
    header_px: int = TRANCHE_TABLE_HEADER_PX,
    chrome_px: int = TRANCHE_TABLE_FRAME_PX,
) -> int:
    """Height cap that shows up to `TRANCHE_TABLE_VISIBLE_ROWS` rows.

    Pure, so the arithmetic is testable without a QApplication. The cap
    follows `row_count` below the ceiling, so a short queue does not
    open a tall empty box. `chrome_px` must be measured by the caller:
    a value that budgets less than the widget actually spends can hide
    a one-row table's only row.
    """
    visible = max(1, min(int(row_count or 0), TRANCHE_TABLE_VISIBLE_ROWS))
    return visible * TRANCHE_ROW_HEIGHT_PX + int(header_px) + int(chrome_px)


# QAbstractScrollArea.sizeHint does not sum column widths.


def fold_table_natural_width_px(table: QTableWidget) -> int:
    """Table width that leaves the viewport as wide as the columns.

    `horizontalHeader().length()` is the summed column width, the one
    number `sizeHint` omits. Adds the vertical header, both frame
    edges, and the vertical scroll bar, all outside the viewport. The
    scroll bar is reserved whether or not it is drawn, since a longer
    queue can always add one after layout. Calls `ensurePolished`
    first, since `frameWidth()` reports 1 unpolished and 13 resolved.
    """
    table.ensurePolished()
    header = table.verticalHeader()
    scroll_bar = table.verticalScrollBar()
    return (
        int(table.horizontalHeader().length())
        + (0 if header is None or header.isHidden() else int(header.width()))
        + 2 * int(table.frameWidth())
        + (0 if scroll_bar is None else int(scroll_bar.sizeHint().width()))
    )


# Every sort key reads a field already stored on the tranche.
FOLD_SORT_QUEUE_ORDER = "Queue order"
FOLD_SORT_OLDEST_FIRST = "Oldest first"
FOLD_SORT_NEWEST_FIRST = "Newest first"
FOLD_SORT_LARGEST_FIRST = "Largest USD first"
FOLD_SORT_SMALLEST_FIRST = "Smallest USD first"

# Combo box order; Queue order is first and is the default.
FOLD_SORT_ORDERS = (
    FOLD_SORT_QUEUE_ORDER,
    FOLD_SORT_OLDEST_FIRST,
    FOLD_SORT_NEWEST_FIRST,
    FOLD_SORT_LARGEST_FIRST,
    FOLD_SORT_SMALLEST_FIRST,
)

# order -> (stored key, descending). Queue order is absent: it sorts by
# nothing and returns the list as the bot holds it.
FOLD_SORT_KEYS = {
    FOLD_SORT_OLDEST_FIRST: ("created_ts", False),
    FOLD_SORT_NEWEST_FIRST: ("created_ts", True),
    FOLD_SORT_LARGEST_FIRST: ("usd", True),
    FOLD_SORT_SMALLEST_FIRST: ("usd", False),
}


def fold_display_order(tranches: list, order: str) -> list[tuple[int, dict]]:
    """Return `(queue_index, tranche)` pairs in the chosen order.

    The queue index is the tranche's position in `_fold_tranches`, the
    same one the `#` column prints and the Fire button quotes back in
    its confirmation, so re-ordering the display never renumbers a
    tranche.

    A tranche whose sort key is absent, the wrong type, `nan`, `inf` or
    a huge int is never given a position: it keeps queue order and goes
    last, rather than being coerced to 0.0 and sorted to the top of
    "Smallest USD first".
    """
    from ...trading.bot_container import as_finite_float

    pairs = list(enumerate(list(tranches or [])))
    spec = FOLD_SORT_KEYS.get(order)
    if spec is None:
        return pairs
    field, descending = spec
    readable: list[tuple[int, dict, float]] = []
    refused: list[tuple[int, dict]] = []
    for index, tranche in pairs:
        value = (
            as_finite_float(tranche.get(field)) if isinstance(tranche, dict) else None
        )
        if value is None:
            refused.append((index, tranche))
        else:
            readable.append((index, tranche, value))
    # Negating the key, not `reverse=True`, keeps the queue-index
    # tie-break ascending in both directions.
    if descending:
        readable.sort(key=lambda row: (-row[2], row[0]))
    else:
        readable.sort(key=lambda row: (row[2], row[0]))
    return [(index, tranche) for index, tranche, _ in readable] + refused


def fold_row_matches_filter(cell_texts: list, needle: str) -> bool:
    """Return True when a rendered cell of the row holds `needle`.

    Searches the cells this panel already composed, never the tranche
    dict again, so it can never surface a value the table does not
    show. An empty or blank needle matches everything.
    """
    text = str(needle or "").strip().casefold()
    if not text:
        return True
    return any(text in str(cell or "").casefold() for cell in cell_texts)


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

# For the sort combo box and the filter field.
FOLD_SORT_TOOLTIP = "Choose the row order. Unreadable rows stay last."
FOLD_FILTER_TOOLTIP = "Show only rows that contain this text."
FOLD_FILTER_PLACEHOLDER = "Filter rows..."

# The invariant: opened - closed - discarded == open tranches.
FOLD_OPEN_COUNT_TOOLTIP = "Fold tranches this bot holds in its queue now."
FOLD_PARKED_USD_TOOLTIP = "Total cash parked by every open fold tranche."
FOLD_OLDEST_AGE_TOOLTIP = "Age of the oldest tranche in this queue."
FOLD_UNITS_MARKED_TOOLTIP = "Asset units the queue claims, against units held."
FOLD_WIRE_DISCARDED_TOOLTIP = "Parked wire credit cleared by this bot, lifetime total."
FOLD_MALFORMED_TOOLTIP = "Stored tranches this bot could not read, lifetime total."
FOLD_CYCLE_CAP_TOOLTIP = "Growth cash one fold cycle may spend, and spent."

# ── The counter rows ───────────────────────────────────────────────────
FOLD_OPENED_TOOLTIP = "Fold tranches this bot ever opened, less merged ones."
FOLD_CLOSED_TOOLTIP = "Fold tranches that folded back and bought the asset."
FOLD_CLOSE_RATIO_TOOLTIP = (
    "Share of opened tranches that folded back, discards excluded."
)
FOLD_DISCARDED_TOOLTIP = "Fold tranches removed without folding back, lifetime total."
FOLD_COUNTERS_RESET_TOOLTIP = "When an operator last set these four counters to zero."


def install_health_row(
    form: QFormLayout, label_text: str, widget: QWidget, tooltip: str
) -> QWidget:
    """Add one summary row and tooltip both the label and the value.

    `QFormLayout.addRow(str, widget)` builds the label itself, so a
    tooltip set on the value alone leaves it bare. `labelForField` asks
    the layout for that label rather than keeping a second reference
    that could drift from it.
    """
    form.addRow(label_text, widget)
    widget.setToolTip(tooltip)
    label = form.labelForField(widget)
    if label is not None:
        label.setToolTip(tooltip)
    return widget


# The row reports _current_holdings against the queue's summed units.

# Above 1.00x the queue claims more asset than the bot owns; the
# threshold is a ledger fact, not a chosen level.
FOLD_OVER_ALLOTMENT_FG_HEX = ds.ERROR

# Same red as the allotment row above, by reference, not a second literal.
FOLD_RATIO_RED_FG_HEX = FOLD_OVER_ALLOTMENT_FG_HEX
FOLD_RATIO_AMBER_FG_HEX = ds.FOLD_RATIO_AMBER
FOLD_RATIO_GREEN_FG_HEX = ds.SUCCESS


def compose_units_marked_row(
    tranches: list, holdings: object
) -> tuple[str, str | None]:
    """Return `(text, colour_hex_or_None)` for the allotment row.

    Pure, so the number beside the operator's holdings is testable
    without Qt. An unreadable `units` value is counted, never added as
    zero. When holdings are zero or unusable, the row says so and
    prints no ratio.
    """
    from ...trading.bot_container import as_finite_float

    marked = 0.0
    unreadable = 0
    for tranche in list(tranches or []):
        value = (
            as_finite_float(tranche.get("units", 0))
            if isinstance(tranche, dict)
            else None
        )
        if value is None:
            unreadable += 1
        else:
            marked += value
    text = f"{marked:,.6f} marked"
    if unreadable:
        text += f"  (+{unreadable} unreadable)"
    held = as_finite_float(holdings)
    if held is None:
        return (f"{text} / holdings unreadable", None)
    if held <= 0:
        return (f"{text} / {held:,.6f} held", None)
    ratio = marked / held
    text += f" / {held:,.6f} held  ({ratio:,.2f}x)"
    if ratio > 1.0:
        return (text, FOLD_OVER_ALLOTMENT_FG_HEX)
    return (text, None)


def compose_cycle_close_ratio(
    created: int, closed: int, discarded: int
) -> tuple[str, str | None]:
    """Return `(text, colour_hex_or_None)` for the cycle close ratio.

    Pure, so the panel's only health verdict is testable without Qt.

    Of every tranche this bot opened and did not discard, the share
    that folded back:

        ratio = closed / (created - discarded)

    A tranche still open counts in the denominator, so a stagnating
    queue shows up here rather than reading 100%. When
    `created - discarded` is at or below zero there is no denominator,
    and the row says so instead of printing a number.
    """
    denominator = int(created) - int(discarded)
    if denominator <= 0:
        return ("—  (nothing left to fold back)", None)
    ratio = int(closed) / denominator
    text = f"{ratio:.2%}  ({int(closed)}/{denominator})"
    if denominator < 5:
        return (text, None)
    if ratio < 0.5:
        return (text, FOLD_RATIO_RED_FG_HEX)
    if ratio < 0.8:
        return (text, FOLD_RATIO_AMBER_FG_HEX)
    return (text, FOLD_RATIO_GREEN_FG_HEX)


def _fold_tranche_source_label(tranche: dict) -> str:
    """Name the action that created this fold tranche.

    Reads the stored `operator_initiated` key: truthy is a manual scrum
    from `ExecutionEngineMixin._execute_manual_rebalance`; present but
    falsy is an autonomous rebalance (Wire Stack or Max Cartridge Fire);
    absent is the ordinary scrum cycle or a DIST re-fold, neither of
    which writes the key. A merge into an older part-spent tranche keeps
    that tranche's own value, so a manual scrum merged into an
    autonomous remnant reads as the remnant's provenance afterward.
    """
    if tranche.get("operator_initiated"):
        return FOLD_SOURCE_MANUAL_SCRUM
    if "operator_initiated" in tranche:
        return FOLD_SOURCE_AUTO_REBALANCE
    return FOLD_SOURCE_AUTO_SCRUM


def _arbiter_label(value: object) -> str:
    """Return the operator's word for a value: ``Parent``/``Sibling``.

    Asks `extractor_bot.arbiter_label`, the module that owns the field,
    rather than keeping a second mapping that could disagree with it.
    Imported inside the function, deferred like every other trading
    import in this GUI module.
    """
    from ...trading.extractor_bot import arbiter_label

    return arbiter_label(value)


def _compose_arbiter_tooltip(value: object) -> str:
    """Explain the Arbiter toggle without overstating what it does.

    The `Parent` value names a force-sell of the tranche by the
    base-currency Scrumming Bot at a growth threshold; no trigger,
    threshold field or caller for that exists yet, so today a Parent
    tranche behaves exactly like a Sibling one. The toggle only stores
    the value.
    """
    label = _arbiter_label(value)
    return (
        f"ARBITER: {label} — who may close THIS Extractor Tranche.\n"
        f"\n"
        f"Parent — the base-currency Scrumming Bot force-sells this "
        f"tranche at x% of growth.\n"
        f"Sibling — the Extractor does all the work and the parent "
        f"stands back.\n"
        f"\n"
        f"RECORDS A DECISION, MOVES NO MONEY. Clicking this places no "
        f"order, cancels none, and changes no balance or Target "
        f"Balance. It writes one value on this tranche and nothing "
        f"else.\n"
        f"\n"
        f"NOT YET ACTED ON. The parent force-sell that 'Parent' names "
        f"is not built, so today a Parent tranche behaves exactly like "
        f"a Sibling one. The value is stored and survives a restart, "
        f"ready for the unit that builds it.\n"
        f"\n"
        f"Per tranche, not per bot. Every Extractor Tranche carries its "
        f"own Arbiter."
    )


def _format_tranche_age(seconds: float) -> str:
    """Coarse age string for a tranche row: ``3d 4h``, ``12m``, ``—``.

    Module scope, so a row can be composed and tested without Qt.
    """
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def _compose_extractor_tranche_cells(row: dict, now_ts: float) -> list[str]:
    """Return the ten cell strings for one Extractor Tranche row.

    Pure, so the row's content is testable without Qt, using the fold
    table's own columns.

    Sell ref $, Original cost $ and Min rebuy $ price the parent's
    asset; an Extractor Tranche prices in base per ALT, a different
    pair, so those three cells print an em dash instead of mixing
    denominations. The alt-side figures are in the tooltip instead.

    Units is the parent's base currency out on lease. USD parked
    carries the marked value once the child has priced the position,
    and an em dash rather than cost basis when it has not.
    """
    # Exact type and finite; deferred, like every other trading import
    # in this module.
    from ...trading.bot_container import as_finite_float

    opened = float(row.get("opened_at", 0.0) or 0.0)
    age = _format_tranche_age(now_ts - opened) if opened > 0 else "—"

    units = float(row.get("base_deployed", 0.0) or 0.0)

    # as_finite_float refuses bool, nan, inf and int overflow.
    mark_usd = as_finite_float(row.get("mark_value_usd"))
    usd_text = f"${mark_usd:,.4f}" if mark_usd is not None else "—"

    state = str(row.get("state", "") or "—")
    pair = str(row.get("pair", "") or "?")

    return [
        "EXT",  # 0  "#" — not a fold index; never a fire target
        age,  # 1  Age
        f"{units:.6f}",  # 2  Units (parent's base currency on lease)
        usd_text,  # 3  USD parked -> marked value, or em dash
        "—",  # 4  Sell ref $   (parent-asset price; N/A)
        "—",  # 5  Original cost $ (parent-asset price; N/A)
        "—",  # 6  Min rebuy $ (parent-asset price; N/A)
        state,  # 7  Status -> the child's position state
        f"extractor {pair}",  # 8  Source
        "—",  # 9  Fire -> the parent cannot fire a child
    ]


def _compose_extractor_tranche_tooltip(row: dict) -> str:
    """Explain one Extractor Tranche row, units included.

    Carries what the columns cannot: which child holds the lease, the
    alt-denominated figures, and, when there is no mark, that fact
    rather than a number standing in for one.
    """
    # Same admission rule as the cell composer: the "—" cell and this
    # tooltip must never disagree about whether a mark exists.
    from ...trading.bot_container import as_finite_float

    base_asset = row.get("base_asset", "") or "base"
    lines = [
        "EXTRACTOR TRANCHE — not this bot's inventory.",
        "",
        (
            f"Child bot: {row.get('child_bot_name', '?')} "
            f"({row.get('child_bot_id', '?')})"
        ),
        f"Pair: {row.get('pair', '?')}",
        f"State: {row.get('state', '?')}",
        "",
        (
            f"{float(row.get('base_deployed', 0.0) or 0.0):.8f} "
            f"{base_asset} of this bot's asset is leased to that "
            f"Extractor."
        ),
        f"Alt units held: {float(row.get('alt_units', 0.0) or 0.0):.8f}",
    ]
    mark_price = as_finite_float(row.get("mark_price_base_per_alt"))
    if mark_price is not None:
        lines.append(
            f"Last mark: {mark_price:.8f} {base_asset} per alt "
            f"unit, recorded by the Extractor's own tick."
        )
    else:
        lines.append(
            "No mark available — this position has not been priced "
            "since it was loaded. The USD column shows an em dash "
            "rather than substituting cost basis."
        )
    lines += [
        "",
        (
            "This row is a RECORD, not inventory. It is not in this bot's "
            "fold queue and not in its lots, so no gate, no SCRUM sizing "
            "and no fold-back can act on it. There is no Fire button "
            "because the parent does not close a child's position."
        ),
    ]
    return "\n".join(lines)
