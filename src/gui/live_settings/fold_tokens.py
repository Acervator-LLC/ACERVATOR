"""Constants and pure helpers behind the Fold Tranches panel.

Qt appears in annotations only, so every helper here is testable without
a QApplication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import design_system as ds

if TYPE_CHECKING:
    from PySide6.QtWidgets import QFormLayout, QTableWidget, QWidget


# ── Extractor Tranche row colours (item 4, operator spec 2026-08-11) ──
# "It will be denoted in with a red background and white text since
# existing tranches are blue."
#
# The values come from `design_system.py`, the GUI token module. The
# legacy `theme_engine.py` is not imported: it disagrees with the token
# module on eight roles.
#
# The blue stays blue. Nothing below touches the existing per-cell
# foregrounds on ordinary tranche rows.
#
# WHY NOT THE THEME'S OWN DANGER COLOUR. `theme_engine.accent_danger`
# is `#ff5577`; white text on it computes to about 3.1:1, which fails
# WCAG AA for normal text — the standard `theme_engine` names as its own
# grounding. `#b3261e` with white gives about 6.5:1 and passes.
# `#b3261e` against white measures 6.54:1. The test file computes that
# ratio from these two constants and fails below 4.5:1, so the
# legibility claim is measured rather than asserted. The calculator
# lives there and not here because this module would never call it.
#
# An explicit item background beats the stylesheet's
# `alternate-background-color`, so this row reads the same in all five
# themes, the two light ones included.
EXTRACTOR_TRANCHE_BG_HEX = ds.EXTRACTOR_TRANCHE_SURFACE
EXTRACTOR_TRANCHE_FG_HEX = ds.TEXT_MAX


# ── Fold Tranche row colours (operator spec 2026-08-11) ──────────────
# "I would like the tranches to be colored as described with stronger
# borders so they appear like proper containers." — where "as
# described" is the item 4 spec above: "a red background and white text
# since existing tranches are blue."
#
# THE BLUE WAS NEVER PAINTED. Before this change "existing tranches are
# blue" was true only of two per-cell FOREGROUNDS — the `#00ccff`
# Source cell on a manually-fired tranche and the Fire button's own
# stylesheet. The row background was whatever
# `alternate-background-color` supplied. This makes the blue real.
#
# WHY #123a63 AND NOT A BRIGHTER BLUE. Every existing foreground on a
# fold row has to stay legible on it, and none of them may be re-tuned,
# because they carry trading meaning (green = price gate open, amber =
# price gate shut). Measured against #123a63: Status green #00ff88 is
# 8.65:1, Status amber #ff9900 is 5.42:1, Source cyan #00ccff is
# 6.12:1, body text #e0e0f0 is 8.88:1. All clear WCAG AA at 4.5:1, so
# NO semantic colour changes. The brighter blues all break at least one
# of them — #1e40af drops amber to 4.07:1, #1d4ed8 drops the accent to
# 3.54:1.
#
# THE FOREGROUND MUST BE EXPLICIT. Seven of the ten fold columns set no
# foreground and inherit the theme palette, which is `#1a1a2e` on Neon
# Light and `#1a1a1a` on Minimal Modern. A dark navy fill without an
# explicit foreground would put near-black text on it in the two light
# themes — measured 1.47:1. `#e0e0f0` is already the dark theme's
# `text_primary`, so the default theme's text does not visibly change;
# only the background does.
FOLD_TRANCHE_BG_HEX = ds.FOLD_TRANCHE_SURFACE
FOLD_TRANCHE_FG_HEX = ds.TEXT_HIGH


# ── Row border colours — the "proper containers" half of the spec ────
# Each border is derived from its OWN fill, because no single colour
# clears 3:1 (WCAG SC 1.4.11, non-text UI boundary) against both fills
# AND both theme backgrounds: white fails on the light theme at 1.15:1,
# black fails on the blue at 2.65:1, and the theme's `border_primary`
# #7a7a9c fails on both fills at 1.92:1 and 1.58:1.
#
# Measured: #6ea6e6 on #123a63 is 4.56:1; #ffb0a6 on #b3261e is 3.74:1.
# Both clear the floor. Two rejected on the number and recorded so they
# are not retried: #e05a50 on the red is 1.79:1 and #ff8a7e is 2.86:1 —
# a red tint cannot clear 3:1 until it is very pale.
#
# NEEDING A PER-ROW BORDER COLOUR IS WHY THIS IS A DELEGATE. A
# stylesheet cannot vary a border by row, and a `QTableWidget::item`
# rule additionally destroys every per-cell background — measured, see
# `_TrancheRowBorderDelegate`.
FOLD_TRANCHE_BORDER_HEX = ds.FOLD_TRANCHE_BORDER
EXTRACTOR_TRANCHE_BORDER_HEX = ds.EXTRACTOR_TRANCHE_BORDER

# The delegate keys the border off the cell's OWN background brush, not
# off its row index. Row index would be wrong the moment anything
# reordered the table, and the Fire button already depends on row order
# being the fold-list index. A fill this map does not know gets NO
# border, so any future row type is left alone rather than mis-drawn.
TRANCHE_ROW_BORDER_BY_BG = {
    FOLD_TRANCHE_BG_HEX: FOLD_TRANCHE_BORDER_HEX,
    EXTRACTOR_TRANCHE_BG_HEX: EXTRACTOR_TRANCHE_BORDER_HEX,
}

# Thick enough to read as a container edge at the table's row height.
TRANCHE_ROW_BORDER_PX = 2

# Vertical mass. A fill reads as a container only when the band has
# height; 30px was chosen against `setMaximumHeight(280)` on the table,
# which then shows ~8 rows before scrolling.
TRANCHE_ROW_HEIGHT_PX = 30

# How much shorter than the row the Fire button is drawn. A cell WIDGET
# is painted on top of the delegate, so a full-height button hides the
# container edge at its own column. Measured on the rendered PNG: with
# a full-height button the top and bottom rules spanned 849px of the
# table's 988 and broke for 41px exactly at this column. 8px leaves
# room for the 2px rule plus clearance at both ends.
TRANCHE_FIRE_BTN_INSET_PX = 8


# ── The Arbiter column (item 5, operator directive 2026-08-10) ───────
# "This should be next to each Extractor Tranche that spawns and be a
# toggling status button that reads Parent or Sibling under an Arbiter
# column."
#
# INDEX 10, AFTER Fire, AND THE POSITION IS NOT A PREFERENCE. Column 9
# is pinned as the Fire column by tests that address it by literal
# index — `tests/test_extractor_tranche_listing.py` and
# `tests/test_tranche_row_container_styling.py` both name `9`. Putting
# Arbiter anywhere below 10 renumbers Fire and breaks those tests
# without changing a single invariant they exist to protect. Worse than
# the test breakage: the Fire button dispatches a REAL market buy, so
# any renumbering that moved a toggle onto that column, or Fire off it,
# would put an unguarded control where a money-moving one is expected.
# Appending at 10 renumbers nothing.
ARBITER_COLUMN_INDEX = 10
ARBITER_COLUMN_HEADER = "Arbiter"

# What a fold row shows in the Arbiter column. An Arbiter belongs to an
# Extractor Tranche; a fold tranche has no child holding it and no
# second party who could close it. The em dash is item 4's own answer
# for a column that does not apply to a row — it is what an Extractor
# row prints under Fire.
ARBITER_NOT_APPLICABLE = "—"

# ── The Source column (issue #98 defect 5) ───────────────────────────
# WHAT THE COLUMN USED TO SAY, AND WHY IT WAS WRONG.
# The cell read `"manual fire" if t.get("operator_initiated") else
# "auto scrum"`. `operator_initiated` is written at ONE site,
# `scrumming_bot.py:12398`, inside the SCRUM (sell) branch of
# `_execute_manual_rebalance`, and its value comes from that method's
# intent map at `scrumming_bot.py:12153`:
#
#     "manual_button": ("MANUAL_SCRUM", "MANUAL_FOLD", True)
#     "wire_stack":    ("WIRE_STACK_SCRUM", "WIRE_STACK_FOLD", False)
#     "max_cartridge": ("CARTRIDGE_SCRUM", "CARTRIDGE_FOLD", False)
#
# So the flag means MANUAL SCRUM: an operator-pressed SELL that CREATED
# this tranche. A manual FIRE is the opposite operation. It is a BUY,
# and it REMOVES a tranche (`scrumming_bot.py:3548`). A tranche created
# by a manual fire cannot exist, so the old label named an action that
# could not have produced the row it sat on.
#
# THREE PROVENANCES, NOT TWO, AND THE THIRD IS THE KEY'S ABSENCE.
# The two autonomous append sites -- the SCRUM cycle at
# `scrumming_bot.py:9112` and the DIST re-fold at `:10721` -- write no
# `operator_initiated` key at all. `_restore_state` copies each stored
# tranche dict verbatim (`scrumming_bot.py:5211`) and stamps nothing,
# so the absence survives a save and a reload and is readable here.
# That splits the old false branch in two:
#
#   key True     an operator pressed Manual Fire on this bot; the SELL
#                leg of that rebalance created this tranche
#   key False    an AUTONOMOUS rebalance created it -- Wire Stack Fire
#                or Max Cartridge Fire. Which of the two is NOT stored
#                and this panel does not guess.
#   key absent   the ordinary scrum cycle, or the DIST re-fold
#
# MEASURED ON THE LIVE FLEET, `~/.acervator/bot_state.json` read-only
# at 2026-08-23 19:28:19, 1,687 open fold tranches on 38 bots:
# 214 True, 1,189 False, 284 absent. So the old code mislabelled 214
# rows with an impossible action and printed one word over 1,473 rows
# that come from two different mechanisms.
#
# THE MERGE CAVEAT, CARRIED OVER RATHER THAN INVENTED HERE.
# `_top_up_remnant_fold_tranches` keeps the OLDER record, so a manual
# scrum merged into an autonomous remnant is displayed thereafter as
# the remnant's provenance. `scrumming_bot.py:12453` states that; this
# column is its only consumer and no gate, order or amount reads the
# field.
FOLD_SOURCE_MANUAL_SCRUM = "manual scrum"
FOLD_SOURCE_AUTO_REBALANCE = "auto rebalance"
FOLD_SOURCE_AUTO_SCRUM = "auto scrum"

#: The cyan already carried by the operator-initiated cell. Kept on the
#: manual-scrum row only: `_paint_fold_tranche_row` measured it at
#: 6.12:1 against the fold fill, and this unit renames a label rather
#: than re-tuning a colour.
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


# ── Reaching a tranche in a long queue (issue #98 defect 7) ──────────
# WHAT WAS MEASURED. The table was capped at `setMaximumHeight(280)`
# over 30px rows and a header, so about EIGHT rows were visible. The
# longest live queue is BILL/USD at 230. `setSortingEnabled` appeared
# zero times in this file and no filter or search existed, so on TAO
# the summary named a 30.4-day oldest tranche while rows one to three
# read 2.7d, 2.7d and 3.6d and the operator could not reach the row
# the headline was about.
#
# WHY `setSortingEnabled` IS STILL NOT USED, AND THIS IS NOT A
# PREFERENCE. `QTableWidget` sorting moves ITEMS. It does NOT move the
# widgets placed with `setCellWidget`, and this table places two of
# them on every row: the Fire button, which dispatches a real market
# buy, and the Arbiter toggle. Turning Qt's own sort on would slide the
# text of every row while leaving those controls where they were, so
# the Fire button on the row the operator reads would belong to a
# different tranche. That is defect 8's failure mode with money behind
# it, manufactured on purpose. The order is decided HERE instead, on
# the list, and the table is REBUILT - so every row is composed with
# its own tranche and its own button, and identity capture is intact.
#
# THE `#` COLUMN KEEPS ITS MEANING. It prints the tranche's position in
# `_fold_tranches`, never the visual row, so re-ordering the display
# never renumbers a tranche.

#: How many rows the table shows before it scrolls. Was about 8, from
#: the 280px cap this replaces.
TRANCHE_TABLE_VISIBLE_ROWS = 18

#: Fallback chrome, used only when there is no widget to measure. The
#: builder passes the measured `fold_table_chrome_px(table)` instead.
#: This literal is 32px short of the shipped theme: 26px of styled
#: frame and a 10px horizontal scroll bar, enough to leave a one-row
#: table showing its header and zero pixels of its only row.
TRANCHE_TABLE_FRAME_PX = 4

#: Fallback header height, used only when there is no header to
#: measure. The builder passes the real
#: `horizontalHeader().sizeHint().height()`.
TRANCHE_TABLE_HEADER_PX = 24


def fold_table_chrome_px(table: QTableWidget) -> int:
    """Vertical pixels this table spends on what is not a row.

    Frame top plus bottom, plus the horizontal scroll bar. The header
    is measured by the caller and is not counted here.

    `ensurePolished` IS THE WHOLE POINT OF THE CALL. An unpolished
    table answers `frameWidth() == 1`; the same table answers `13`
    once the theme's `QTableWidget` border is resolved, so measuring
    before polish under-counts the frame by 24px and hides a row.

    THE SCROLL BAR IS RESERVED WHETHER OR NOT IT APPEARS. Eleven
    `ResizeToContents` columns measure 1,582px against a 521px
    viewport, so it is always drawn here, and its presence is not
    knowable until after the table has been laid out.
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

    Pure, so the arithmetic behind the operator's window is testable
    without a QApplication - the same reason `_compose_denom_row_text`
    lives at module scope.

    A SHORT QUEUE DOES NOT GET A TALL EMPTY BOX. The cap follows the
    row count until it reaches the ceiling, so a bot with three
    tranches shows three rows and the group closes around them.

    `chrome_px` IS MEASURED BY THE CALLER, NOT ASSUMED HERE. A cap
    that budgets less chrome than the widget spends is subtracted from
    the rows, and a one-row table then draws its header and nothing
    else - issue #133 unit 1, seen on CHIP/USD `c8e5c5db` with one
    tranche the summary counted and the table did not show.
    """
    visible = max(1, min(int(row_count or 0), TRANCHE_TABLE_VISIBLE_ROWS))
    return visible * TRANCHE_ROW_HEIGHT_PX + int(header_px) + int(chrome_px)


# ── A whole tranche row, not a size hint (issue #133 unit 12) ────────
# QTableWidget is a QScrollArea. QAbstractScrollArea::sizeHint returns
# a fixed default and does not sum columns, so the tab holding the
# tranche table can hint narrower than one row.
#
# Operator display 1536x960 logical (1920x1200 at 125%), real font
# database, cyberpunk_dark, his CHIP/USD tranche: dialog 859, tab
# viewport 825, row right edge 963 - 138px cut. BTC-scale prices 170px,
# seven-figure USD parked 228px.


def fold_table_natural_width_px(table: QTableWidget) -> int:
    """Table width that leaves the viewport as wide as the columns.

    `horizontalHeader().length()` is the summed column width, the one
    number `sizeHint` omits. Added to it, all outside the viewport:
    the vertical header, both frame edges, and the vertical scroll bar.

    THE VERTICAL SCROLL BAR IS RESERVED WHETHER OR NOT IT APPEARS.
    `fold_table_max_height_px` caps the table at 18 rows, and a longer
    queue draws one; its width is not knowable until the table is laid
    out. `fold_table_chrome_px` reserves the horizontal bar for the
    same reason.

    `ensurePolished` before the read. Unpolished `frameWidth()` is 1;
    polished under this theme it is 13.
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


# ── The row order the operator chooses (issue #98 defect 7) ──────────
# EVERY ORDER READS A FIELD THAT IS ALREADY STORED ON THE TRANCHE.
# `created_ts` is written at all three creation sites
# (`scrumming_bot.py:9110`, `:10726`, `:12397`) and was present on
# 1,701 of 1,701 live tranches when the panel was evaluated; `usd` is
# the parked cash the "USD parked" column already prints. No order
# derives a quantity, and none invents one.
FOLD_SORT_QUEUE_ORDER = "Queue order"
FOLD_SORT_OLDEST_FIRST = "Oldest first"
FOLD_SORT_NEWEST_FIRST = "Newest first"
FOLD_SORT_LARGEST_FIRST = "Largest USD first"
FOLD_SORT_SMALLEST_FIRST = "Smallest USD first"

#: The offered orders, in the order the combo box lists them. Queue
#: order is first and is the default, so a panel nobody has touched
#: renders exactly as it always did.
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


def fold_display_order(tranches: list, order: str) -> list[tuple[int, dict]]:
    """Return `(queue_index, tranche)` pairs in the chosen order.

    THE QUEUE INDEX TRAVELS WITH THE ROW. It is the tranche's position
    in `_fold_tranches`, and it is what the `#` column prints and what
    the Fire button quotes back in its confirmation. Returning it
    beside the tranche is what lets the display be re-ordered without
    the panel ever renumbering a tranche.

    A ROW THIS PANEL CANNOT READ IS NEVER GIVEN A POSITION. A tranche
    whose sort key is absent, the wrong type, `nan`, `inf` or a huge
    int has no place on a scale, so it is not put on one: refused rows
    keep queue order and go LAST, together, where they can be seen.
    Coercing them to 0.0 would have sorted a corrupt record to the top
    of "Smallest USD first" and told the operator it was the smallest
    tranche they own.

    `as_finite_float` is the module's one admission rule, imported the
    way every other trading symbol enters this file.
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
    # The queue index is the tie-break in BOTH directions, so two
    # tranches created in the same second keep the order the bot holds
    # them in rather than swapping between rebuilds. Negating the key
    # for the descending case leaves that tie-break ascending;
    # `reverse=True` would have flipped it as well.
    if descending:
        readable.sort(key=lambda row: (-row[2], row[0]))
    else:
        readable.sort(key=lambda row: (row[2], row[0]))
    return [(index, tranche) for index, tranche, _ in readable] + refused


def fold_row_matches_filter(cell_texts: list, needle: str) -> bool:
    """Return True when a rendered cell of the row holds `needle`.

    IT SEARCHES WHAT IS ON THE SCREEN, AND THAT IS THE POINT. Every
    string it reads is a cell this panel already composed from a stored
    field, so the filter can never surface a quantity the table does
    not show, and it needs no second reading of the tranche dict that
    could disagree with the first.

    An empty or blank needle matches everything, so clearing the box
    restores the whole queue.
    """
    text = str(needle or "").strip().casefold()
    if not text:
        return True
    return any(text in str(cell or "").casefold() for cell in cell_texts)


# ── The column documentation the panel said it had (defect 6) ────────
# The prose explainer was removed on operator directive 2026-07-26 and
# the comment that replaced it named "column headers + per-column
# tooltips" as the authoritative per-tranche documentation. Measured on
# the built table: ZERO of the eleven headers carried a tooltip, no
# summary row carried one, and only three columns - Min rebuy, Status
# and Arbiter - carried a cell tooltip. The authority the comment named
# was empty.
#
# THE WRITING STANDARD IS THE OPERATOR'S, from issue #53: uniform,
# Simplified Technical English, about ten words, no MEM numbers, no
# version strings and no code identifiers. One line each, so every
# tooltip this unit adds is the same shape.
#
# A HEADER TOOLTIP DOCUMENTS THE COLUMN. The longer per-row tooltips
# already on Min rebuy, Status, Source and Arbiter document THAT ROW'S
# value and its caveats; they are not replaced here.
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

#: Same standard, for the two controls that reach a row.
FOLD_SORT_TOOLTIP = "Choose the row order. Unreadable rows stay last."
FOLD_FILTER_TOOLTIP = "Show only rows that contain this text."
FOLD_FILTER_PLACEHOLDER = "Filter rows..."

# ── Summary-row tooltips (defect 6) ──────────────────────────────────
# The four counter rows - opened, closed, the close ratio and tranches
# discarded - were left bare by defect 6 because defect 4 owned the
# counters and they did not reconcile. Defect 4 has now landed: every
# site that removes a fold tranche moves exactly one of opened, closed
# or discarded, so the four rows describe quantities that hold
# `opened - closed - discarded == open tranches`. They carry the same
# ten-word tooltip standard as every other row on this form.
FOLD_OPEN_COUNT_TOOLTIP = "Fold tranches this bot holds in its queue now."
FOLD_PARKED_USD_TOOLTIP = "Total cash parked by every open fold tranche."
FOLD_OLDEST_AGE_TOOLTIP = "Age of the oldest tranche in this queue."
FOLD_UNITS_MARKED_TOOLTIP = "Asset units the queue claims, against units held."
FOLD_WIRE_DISCARDED_TOOLTIP = "Parked wire credit cleared by this bot, lifetime total."
FOLD_MALFORMED_TOOLTIP = "Stored tranches this bot could not read, lifetime total."
FOLD_CYCLE_CAP_TOOLTIP = "Growth cash one fold cycle may spend, and spent."

# ── The counter rows (defect 4) ──────────────────────────────────────
# Same standard: one line, about ten words, no code identifiers.
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
    """Add one summary row and tooltip BOTH halves of it.

    `QFormLayout.addRow(str, widget)` builds the label itself, so a
    tooltip set on the value alone leaves the words the operator
    actually points at bare - which is what the panel did on every row
    that had a tooltip at all. `labelForField` asks the layout which
    label it made rather than keeping a second reference that could
    drift.
    """
    form.addRow(label_text, widget)
    widget.setToolTip(tooltip)
    label = form.labelForField(widget)
    if label is not None:
        label.setToolTip(tooltip)
    return widget


# ── The allotment total (issue #98 defect 9) ─────────────────────────
# WHAT WAS MEASURED, 2026-08-23, over the live state file: tranche
# `units` summed against the units the bot holds gave PUMP/USD 1.99x
# and CAP/USD 1.34x. The fold queue claimed twice the asset PUMP owns.
# The panel printed per-row Units, no total, and no comparison, so the
# condition was invisible on the one surface that owns the ledger.
#
# `_current_holdings` IS THE FIELD, NOT A DERIVED QUANTITY. The bot
# keeps it as the units it holds (`bot_container.py:482`), exports it
# as `current_holdings` (`bot_container.py:1869`) and maintains the
# invariant `sum(lot["units"]) == _current_holdings`. The evaluation
# used `position_value / current_price` only because it was reading a
# state file; the panel has the bot and reads the field.
#
# THIS ROW ATTRIBUTES NOTHING. It reports two stored quantities and
# their ratio. The cause of an excess sits outside this panel and is
# not guessed at here.

#: The red already used for a health verdict on this same form and for
#: the over-cap tranche row on the Settings tab. One threshold, and it
#: is not a taste: above 1.00x the queue claims more asset than the bot
#: owns, which is a statement about the ledger rather than a level
#: somebody picked.
FOLD_OVER_ALLOTMENT_FG_HEX = ds.ERROR

#: The three colours the cycle-close-ratio verdict has always used,
#: lifted out of the widget so the pure composer below can return one
#: and a test can name it. Red is the SAME red as the row above, by
#: reference rather than by a second copy of the literal.
FOLD_RATIO_RED_FG_HEX = FOLD_OVER_ALLOTMENT_FG_HEX
FOLD_RATIO_AMBER_FG_HEX = ds.FOLD_RATIO_AMBER
FOLD_RATIO_GREEN_FG_HEX = ds.SUCCESS


def compose_units_marked_row(
    tranches: list, holdings: object
) -> tuple[str, str | None]:
    """Return `(text, colour_hex_or_None)` for the allotment row.

    Pure, so the number beside the operator's holdings is testable
    without Qt.

    AN UNREADABLE `units` IS COUNTED, NEVER ADDED AS ZERO. That is the
    rule the parked-USD total on this same form already follows: a
    refused contributor rides beside the number instead of quietly
    lowering it.

    NO RATIO WITHOUT HOLDINGS. When the bot holds nothing, or the
    holdings value is not a usable number, the row says so and prints
    no multiple. A ratio against zero is not a large number; it is not
    a number.
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

    THE DEFINITION, IN ONE SENTENCE: of every tranche this bot opened
    and did not discard, the share that folded back.

        ratio = closed / (created - discarded)

    WHAT WAS WRONG WITH THE OLD ONE. It was `closed / created`, and a
    discarded tranche stayed in the denominator. A discard is a record
    the operator cleared, the despawn sweep delisted, a detonation
    abandoned or the fold guard could not read. None of those is a
    failure to fold back, and each of them lowered the ratio
    permanently. Measured on the live fleet, 2026-08-23: BTC/USD had
    opened 160, folded back 118 and discarded 42, so it folded back
    every tranche it still had, and the panel printed 73.75%.

    A TRANCHE STILL STANDING IS STILL IN THE DENOMINATOR, deliberately.
    It was opened, it was not discarded, and it has not folded. That is
    what makes a stagnating queue show up here at all, and it is why
    this ratio is not simply `closed / (closed + discarded)` -- that
    reading is 100% on a bot whose queue has never moved.

    NOTHING LEFT TO FOLD IS NOT 100%. When `created - discarded` is
    zero or below there is no denominator, and the row says so rather
    than printing a number. A ratio whose healthy value and whose
    broken value are both "100%" measures nothing.
    """
    denominator = int(created) - int(discarded)
    if denominator <= 0:
        return ("—  (nothing left to fold back)", None)
    ratio = int(closed) / denominator
    text = f"{ratio:.2%}  ({int(closed)}/{denominator})"
    # The bands are the ones this row already used. Only the quantity
    # they judge has changed.
    if denominator < 5:
        return (text, None)
    if ratio < 0.5:
        return (text, FOLD_RATIO_RED_FG_HEX)
    if ratio < 0.8:
        return (text, FOLD_RATIO_AMBER_FG_HEX)
    return (text, FOLD_RATIO_GREEN_FG_HEX)


def _fold_tranche_source_label(tranche: dict) -> str:
    """Name the action that CREATED this fold tranche.

    Three answers, because the stored record distinguishes three cases
    and the old two-way test threw one of them away. See the block
    above for the write sites and the live counts.

    THE TRUTHINESS TEST IS DELIBERATE AND UNCHANGED. The shipped cell
    asked `if t.get("operator_initiated")`, so a stored `0`, `""` or
    `False` all took the autonomous branch. Keeping that test means a
    row whose flag is a falsey non-bool renders exactly as it did
    before, and this unit changes the WORDS on the cell rather than
    which branch a row lands in. Only the key's presence is new
    information, and `in` is the one test that can see it.
    """
    if tranche.get("operator_initiated"):
        return FOLD_SOURCE_MANUAL_SCRUM
    if "operator_initiated" in tranche:
        return FOLD_SOURCE_AUTO_REBALANCE
    return FOLD_SOURCE_AUTO_SCRUM


def _arbiter_label(value: object) -> str:
    """Return the operator's word for a value: ``Parent``/``Sibling``.

    ONE MAPPING, AND IT LIVES IN THE TRADING MODULE. The word shown on
    the button and the value stored on the position must never be able
    to disagree, so this does not keep its own table — it asks the
    module that owns the field. Imported inside the function because
    every other trading import in this file is deferred the same way,
    and a GUI module has no business pulling the trading stack in at
    import time.
    """
    from ...trading.extractor_bot import arbiter_label

    return arbiter_label(value)


def _compose_arbiter_tooltip(value: object) -> str:
    """Explain the Arbiter toggle without overstating what it does.

    THIS TOOLTIP IS DELIBERATELY HONEST ABOUT AN ABSENCE. The `Parent`
    value names a force-sell of the tranche by the base-currency
    Scrumming Bot at a growth threshold. No such mechanism exists in
    this repository — no trigger, no threshold field, no caller. So
    today the toggle RECORDS AN INTENTION and changes no trading
    decision, and a tranche set to Parent behaves exactly like one set
    to Sibling. Describing it as working behaviour would be a false
    claim about the fleet, made on the operator's own screen.
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

    Module scope so an Extractor Tranche row can be composed and tested
    without a QApplication, matching `_compose_denom_row_text` above.
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

    Pure, so the row's content is testable without Qt. The columns are
    the fold table's columns, because item 4 lists Extractor Tranches in
    that same table.

    EVERY COLUMN THAT WOULD MIX DENOMINATIONS PRINTS AN EM DASH. "Sell
    ref $", "Original cost $" and "Min rebuy $" are prices of the
    PARENT's asset per unit. An Extractor Tranche's prices are quoted in
    base per ALT — a different pair entirely — so putting them under
    those headings would place one asset's number beneath another
    asset's label. A dash is the honest cell. The alt-side figures are
    in the tooltip, where they carry their own units.

    "Units" is the base currency this position holds out of the parent's
    asset, which is the same denomination the fold column uses and the
    quantity the parent actually cares about: how much of my asset is
    out on lease.

    "USD parked" carries the marked value when the child has priced the
    position, and an em dash when it has not. Never cost basis. A
    position restored from disk and not yet ticked has NO mark, and
    printing its cost basis in a market-value column would report a
    stale purchase as if it were today's worth.
    """
    # EXACT type AND finite, the same admission rule the Stack panel
    # reads its timestamps with and the same one `as_finite_float`
    # already enforces for the despawn threshold. Deferred import,
    # the way every other trading symbol enters this module.
    from ...trading.bot_container import as_finite_float

    opened = float(row.get("opened_at", 0.0) or 0.0)
    age = _format_tranche_age(now_ts - opened) if opened > 0 else "—"

    units = float(row.get("base_deployed", 0.0) or 0.0)

    # `isinstance` admitted bool, because bool subclasses int, so a
    # stored `True` printed "$1.0000" into a money column and a
    # stored `False` printed "$0.0000" — a fabricated valuation
    # where the docstring above promises an em dash for a position
    # that was never priced. A type is not a domain either, and
    # this column has no `> 0` test to catch the rest by accident:
    # `nan` and `inf` reached the format and printed "$nan" and
    # "$inf", and an int above the float maximum raised
    # OverflowError out of the row builder. Every refused shape now
    # takes the em-dash path this column already had.
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
    alt-denominated figures, and — when there is no mark — the fact that
    no mark exists, rather than a number standing in for one.
    """
    # Same admission rule as the cell composer above; the two are
    # one contract. The tooltip exists to say why the USD cell is
    # blank, so a cell reading "—" beside a tooltip reading
    # "Last mark: nan" would have contradicted the cell it explains.
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
