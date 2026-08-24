"""
bot_live_settings.py — Live Bot Settings Dialog.

Opens when clicking the Detail button on a running bot. Allows editing
bot configuration in real-time. (Prior to v3.20.4 also hosted an
"Adjust Stack" tab for Grid bots — removed alongside grid_bot cleanup.)
"""

from __future__ import annotations

import logging

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
        QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
        QPushButton, QTabWidget, QWidget,
        QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
        QScrollArea, QLineEdit,
        QStyledItemDelegate, QStyleOptionViewItem,
    )
    from PySide6.QtCore import Qt, Signal, QModelIndex, QPersistentModelIndex
    from PySide6.QtGui import QColor, QBrush, QPainter, QPen
    _HAS_QT = True
except ImportError:
    _HAS_QT = False


# ── Extractor Tranche row colours (item 4, operator spec 2026-08-11) ──
# "It will be denoted in with a red background and white text since
# existing tranches are blue."
#
# Hex literals, because that is what this file already uses. There is a
# theme system in `theme_engine.py` and a token module in
# `design_system.py`, and this module imports neither; every colour in
# here is a literal (`#00ccff`, `#00ff88`, `#ff9900`, `#ff3366`). A
# theme import for two values would be a second mechanism beside the one
# already in place.
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
EXTRACTOR_TRANCHE_BG_HEX = "#b3261e"
EXTRACTOR_TRANCHE_FG_HEX = "#ffffff"


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
FOLD_TRANCHE_BG_HEX = "#123a63"
FOLD_TRANCHE_FG_HEX = "#e0e0f0"


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
FOLD_TRANCHE_BORDER_HEX = "#6ea6e6"
EXTRACTOR_TRANCHE_BORDER_HEX = "#ffb0a6"

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
FOLD_SOURCE_MANUAL_FG_HEX = "#00ccff"

FOLD_SOURCE_TOOLTIPS = {
    FOLD_SOURCE_MANUAL_SCRUM: (
        "An operator-pressed Manual Fire created this tranche. That "
        "button runs a rebalance; its SELL leg is a manual SCRUM, and "
        "a scrum is what queues a fold tranche.\n\n"
        "Stored as operator_initiated = true."),
    FOLD_SOURCE_AUTO_REBALANCE: (
        "An AUTONOMOUS rebalance created this tranche: Wire Stack Fire "
        "or Max Cartridge Fire. The bot fired it, not the operator.\n\n"
        "Stored as operator_initiated = false. Which of the two fired "
        "is NOT stored on the tranche, so this panel does not name "
        "it; the trade log carries WIRE_STACK_SCRUM or "
        "CARTRIDGE_SCRUM for the sale itself."),
    FOLD_SOURCE_AUTO_SCRUM: (
        "The ordinary scrum cycle created this tranche, or the DIST "
        "re-fold that follows a distribution sell.\n\n"
        "Those two paths store no operator_initiated key at all, and "
        "that absence is what this label reads."),
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

#: The table's own frame, top plus bottom. `QTableWidget` draws a 1px
#: sunken frame by default and the height cap must include it, or the
#: last row is clipped by exactly that much.
TRANCHE_TABLE_FRAME_PX = 4

#: Fallback header height, used only when there is no header to
#: measure. The builder passes the real
#: `horizontalHeader().sizeHint().height()`.
TRANCHE_TABLE_HEADER_PX = 24


def fold_table_max_height_px(
        row_count: int,
        header_px: int = TRANCHE_TABLE_HEADER_PX) -> int:
    """Height cap that shows up to `TRANCHE_TABLE_VISIBLE_ROWS` rows.

    Pure, so the arithmetic behind the operator's window is testable
    without a QApplication - the same reason `_compose_denom_row_text`
    lives at module scope.

    A SHORT QUEUE DOES NOT GET A TALL EMPTY BOX. The cap follows the
    row count until it reaches the ceiling, so a bot with three
    tranches shows three rows and the group closes around them.
    """
    visible = max(1, min(int(row_count or 0), TRANCHE_TABLE_VISIBLE_ROWS))
    return (visible * TRANCHE_ROW_HEIGHT_PX
            + int(header_px) + TRANCHE_TABLE_FRAME_PX)


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


def fold_display_order(
        tranches: list, order: str) -> list[tuple[int, dict]]:
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
    from ..trading.bot_container import as_finite_float

    pairs = list(enumerate(list(tranches or [])))
    spec = FOLD_SORT_KEYS.get(order)
    if spec is None:
        return pairs
    field, descending = spec
    readable: list[tuple[int, dict, float]] = []
    refused: list[tuple[int, dict]] = []
    for index, tranche in pairs:
        value = (as_finite_float(tranche.get(field))
                 if isinstance(tranche, dict) else None)
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
    return ([(index, tranche) for index, tranche, _ in readable]
            + refused)


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
# discarded - are NOT given tooltips here. Issue #98 defect 4 holds
# that those counters do not reconcile with the standing list on 13 of
# 38 bots, and a separate unit is repairing them. Writing a ten-word
# description of a number that is under repair would document the wrong
# meaning, and it would edit the exact lines that unit owns.
FOLD_OPEN_COUNT_TOOLTIP = (
    "Fold tranches this bot holds in its queue now.")
FOLD_PARKED_USD_TOOLTIP = (
    "Total cash parked by every open fold tranche.")
FOLD_OLDEST_AGE_TOOLTIP = (
    "Age of the oldest tranche in this queue.")
FOLD_UNITS_MARKED_TOOLTIP = (
    "Asset units the queue claims, against units held.")
FOLD_WIRE_DISCARDED_TOOLTIP = (
    "Parked wire credit cleared by this bot, lifetime total.")
FOLD_MALFORMED_TOOLTIP = (
    "Stored tranches this bot could not read, lifetime total.")
FOLD_CYCLE_CAP_TOOLTIP = (
    "Growth cash one fold cycle may spend, and spent.")


def install_health_row(form: QFormLayout, label_text: str,
                       widget: QWidget, tooltip: str) -> QWidget:
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
FOLD_OVER_ALLOTMENT_FG_HEX = "#ff3366"


def compose_units_marked_row(
        tranches: list, holdings: object) -> tuple[str, str | None]:
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
    from ..trading.bot_container import as_finite_float

    marked = 0.0
    unreadable = 0
    for tranche in list(tranches or []):
        value = (as_finite_float(tranche.get("units", 0))
                 if isinstance(tranche, dict) else None)
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
    from ..trading.extractor_bot import arbiter_label
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
        f"own Arbiter.")


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


def _compose_extractor_tranche_cells(
        row: dict, now_ts: float) -> list[str]:
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
    from ..trading.bot_container import as_finite_float

    opened = float(row.get("opened_at", 0.0) or 0.0)
    age = (_format_tranche_age(now_ts - opened) if opened > 0 else "—")

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
    usd_text = (f"${mark_usd:,.4f}" if mark_usd is not None else "—")

    state = str(row.get("state", "") or "—")
    pair = str(row.get("pair", "") or "?")

    return [
        "EXT",          # 0  "#" — not a fold index; never a fire target
        age,            # 1  Age
        f"{units:.6f}",  # 2  Units (parent's base currency on lease)
        usd_text,       # 3  USD parked -> marked value, or em dash
        "—",            # 4  Sell ref $   (parent-asset price; N/A)
        "—",            # 5  Original cost $ (parent-asset price; N/A)
        "—",            # 6  Min rebuy $ (parent-asset price; N/A)
        state,          # 7  Status -> the child's position state
        f"extractor {pair}",  # 8  Source
        "—",            # 9  Fire -> the parent cannot fire a child
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
    from ..trading.bot_container import as_finite_float

    base_asset = row.get("base_asset", "") or "base"
    lines = [
        "EXTRACTOR TRANCHE — not this bot's inventory.",
        "",
        (f"Child bot: {row.get('child_bot_name', '?')} "
         f"({row.get('child_bot_id', '?')})"),
        f"Pair: {row.get('pair', '?')}",
        f"State: {row.get('state', '?')}",
        "",
        (f"{float(row.get('base_deployed', 0.0) or 0.0):.8f} "
         f"{base_asset} of this bot's asset is leased to that "
         f"Extractor."),
        f"Alt units held: {float(row.get('alt_units', 0.0) or 0.0):.8f}",
    ]
    mark_price = as_finite_float(row.get("mark_price_base_per_alt"))
    if mark_price is not None:
        lines.append(
            f"Last mark: {mark_price:.8f} {base_asset} per alt "
            f"unit, recorded by the Extractor's own tick.")
    else:
        lines.append(
            "No mark available — this position has not been priced "
            "since it was loaded. The USD column shows an em dash "
            "rather than substituting cost basis.")
    lines += [
        "",
        ("This row is a RECORD, not inventory. It is not in this bot's "
         "fold queue and not in its lots, so no gate, no SCRUM sizing "
         "and no fold-back can act on it. There is no Fire button "
         "because the parent does not close a child's position."),
    ]
    return "\n".join(lines)


# v3.23.48 — pure formatter for the Target-BTC / Target-ETH cross-
# pair denomination rows. Lives at module scope so it can be unit-
# tested without a QApplication. The Qt-side widget helper on
# BotLiveSettingsDialog delegates here.
def _compose_denom_row_text(
        quote_currency: str,
        target_usd: float, quote_usd: float,
        pair_pct_24h: float, usd_pair_pct_24h: float,
) -> tuple[str, str]:
    """Return ``(text, color_hex)`` for one denomination row.

    ``quote_usd`` is the USD price of one unit of the quote currency
    (e.g., BTC/USD or ETH/USD from CurrencyRateMonitor). Returns a
    "pending…" grey row when the quote-USD rate is not yet available.
    Colours: green (`#00ff88`) for divergence > +0.1 %, red
    (`#ff3366`) for < -0.1 %, grey (`#a8a8c5`) otherwise.
    """
    if quote_usd <= 0:
        return ("pending…", "#a8a8c5")
    _units = target_usd / quote_usd
    _delta = pair_pct_24h - usd_pair_pct_24h
    if abs(_delta) < 0.1:
        _color = "#a8a8c5"
        _sign = ""
    elif _delta > 0:
        _color = "#00ff88"
        _sign = "+"
    else:
        _color = "#ff3366"
        _sign = ""
    if _units >= 1:
        _units_txt = f"{_units:.4f}"
    elif _units >= 0.01:
        _units_txt = f"{_units:.5f}"
    else:
        _units_txt = f"{_units:.6f}"
    _txt = (
        f"{_units_txt} {quote_currency}  "
        f"(Δ24h vs USD: {_sign}{_delta:.2f} %)")
    return (_txt, _color)


if _HAS_QT:

    class _TrancheRowBorderDelegate(QStyledItemDelegate):
        """Strokes a container edge on top of a painted tranche row.

        Installed on the Open Tranches table ONLY, via
        `setItemDelegate`. This is the first item delegate in the
        repository, which is a real architectural addition rather than
        a tweak, so the reason it is required is recorded here.

        WHY NOT A STYLESHEET. Adding ANY `QTableWidget::item` rule to
        this table DESTROYS every per-cell `setBackground`. Measured
        offscreen against a four-row replica: with an `::item` border
        rule the rows came back as the plain alternating background and
        BOTH fills were gone — item 4's red included. Qt routes item
        painting through QStyleSheetStyle once an `::item` rule exists
        and the item's BackgroundRole is dropped.

        That failure is silent and would not be caught by the existing
        suite. `tests/test_extractor_tranche_listing.py` asserts
        `cell.background().color().name()`, which reads the MODEL. The
        item keeps its brush; only the painting ignores it. A
        stylesheet implementation would therefore ship a green suite
        over a surface with no colour on it at all. The tests added
        alongside this class sample RENDERED PIXELS for that reason.

        WHY NOT GRID LINES. `gridline-color` recolours both axes
        equally, which produces a bright four-way grid — a spreadsheet,
        not a container. And `setShowGrid(False)` is worse here:
        measured, two adjacent blue rows then butt together with no
        separator and merge into one slab.

        The delegate keeps both fills intact because `super().paint()`
        honours BackgroundRole and this only strokes afterwards.
        Measured on the same replica: fills survived, the rule drew at
        the intended colour, and the vertical seam between columns
        stayed fill-coloured, so the rules read as one row-spanning
        edge rather than ten little boxes.
        """

        def paint(self, painter: QPainter, option: QStyleOptionViewItem,
                  index: QModelIndex | QPersistentModelIndex) -> None:
            """Paint the cell normally, then stroke its row edges.

            The border colour comes from the cell's own background
            brush through `TRANCHE_ROW_BORDER_BY_BG`. A cell whose fill
            is not in that map gets no stroke at all, so this cannot
            draw on a row it was not designed for.
            """
            super().paint(painter, option, index)

            brush = index.data(Qt.ItemDataRole.BackgroundRole)
            if brush is None:
                return
            try:
                fill = brush.color().name()
            except AttributeError:
                # A BackgroundRole carrying a QColor rather than a
                # QBrush. Qt permits both; neither is an error.
                try:
                    fill = QColor(brush).name()
                except (TypeError, ValueError):
                    return
            border_hex = TRANCHE_ROW_BORDER_BY_BG.get(fill)
            if border_hex is None:
                return

            painter.save()
            pen = QPen(QColor(border_hex), TRANCHE_ROW_BORDER_PX)
            # Square caps, or a 2px pen rounds past the cell edge and
            # the seam between two columns picks up a visible nub.
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            rect = option.rect
            # Inset by half the pen width so the stroke lands INSIDE
            # the cell. A line drawn exactly on `top()` is half
            # clipped, which reads as a 1px line on one row and 2px on
            # its neighbour.
            inset = TRANCHE_ROW_BORDER_PX // 2
            top = rect.top() + inset
            bottom = rect.bottom() - inset
            painter.drawLine(rect.left(), top, rect.right(), top)
            painter.drawLine(rect.left(), bottom, rect.right(), bottom)
            painter.restore()

    #: What the despawn rows say a despawn DOES, in the operator's own
    #: three verbs. MERGE collapses tranches into each other, DESPAWN
    #: removes an aged one, CLEAR is the operator's manual removal.
    #: Nothing else collapses or removes a tranche.
    #:
    #: WHERE THE VALUE GOES, and it is the question a removal has to
    #: answer. A fold tranche is an EARMARK, not custody: the scrum
    #: SELL already happened, the units already left `_main_lots`, and
    #: the dollars are already sitting in the shared exchange wallet.
    #: The record is the bot's queued intent to buy those units back at
    #: or below `ref`. Removing it places no order, cancels no order
    #: and moves no balance, so nothing the exchange reports changes.
    #: What is lost is the INTENT and the `initial_buy_price`
    #: provenance that came with it: those dollars stop being a queued
    #: rebuy and go back to being ordinary spendable balance.
    DESPAWN_ROW_TOOLTIP = (
        "DESPAWN removes a tranche once it reaches this age.\n\n"
        "The control is on the Settings tab, under Advanced -\n"
        "Tranche Despawn Timer. 0 is Off and is the default.\n\n"
        "IT IS NOT A TRADE. No order is placed or cancelled and no\n"
        "balance moves. The scrum sale already happened, so the\n"
        "dollars are already in the wallet; the record is only this\n"
        "bot's queued intent to buy those units back. Removing it\n"
        "returns that money to ordinary spendable balance and drops\n"
        "the original-cost provenance the record carried.\n\n"
        "A tranche with no timestamp is NEVER removed. A stack\n"
        "tranche holding a resting exchange order is kept until that\n"
        "order settles.\n\n"
        "MERGE, DESPAWN and CLEAR are the only three things that\n"
        "collapse or remove a tranche.")

    def despawn_timer_text(days: int) -> str:
        """Name the armed threshold and where the control lives.

        THE POINTER IS PART OF THE ANSWER. The spinbox sits on the
        Settings tab under Advanced, well below the fold, which is the
        measured reason the operator never found it. A row that
        reported "Off" and stopped would restate the problem without
        moving anybody toward the fix.
        """
        _where = "Settings tab > Advanced > Tranche Despawn Timer"
        if days <= 0:
            return f"Off  -  {_where}"
        return f"{days} day(s)  -  {_where}"

    def despawn_preview_text(days: int, armed: dict,
                             windows: list) -> str:
        """Say what a sweep takes, in records, dollars and units.

        DOLLARS ALONE WOULD UNDERSTATE IT. The smallest live tranche
        holds $0.00000022 and 87% of the fleet's tranches hold under a
        dollar, so a USD-only line reads as "nothing" for a removal
        that drops hundreds of records. The count leads; the money and
        the units follow.

        THE OFF FORM IS A MENU, not a verdict. Each candidate window
        prints its own count and money, so the operator chooses a
        threshold against this bot's real ages.
        """
        if days > 0:
            parts = [
                f"{armed['fold_removed']} of {armed['fold_open']} "
                f"fold tranche(s)",
                f"${armed['usd_removed']:,.4f}",
                f"{armed['units_removed']:,.8f} units",
            ]
            if armed["stack_open"]:
                parts.append(
                    f"{armed['stack_removed']} of "
                    f"{armed['stack_open']} stack tranche(s)")
            if armed["stack_kept_live_order"]:
                parts.append(
                    f"{armed['stack_kept_live_order']} stack kept "
                    f"(live order)")
            if armed["ageless_kept"]:
                parts.append(
                    f"{armed['ageless_kept']} kept (no timestamp)")
            return "  -  ".join(parts)
        if not windows:
            return "nothing to remove"
        return "if armed at  " + "  -  ".join(
            f"{w}d: {p['fold_removed'] + p['stack_removed']} "
            f"(${p['usd_removed']:,.4f})"
            for w, p in windows)

    def pin_despawn_rows(dialog: BotLiveSettingsDialog, days: int,
                         fold_snapshot: list,
                         stack_snapshot: list, now_ts: float,
                         elapsed: float) -> None:
        """Pin the two rendered rows against the bot's own ledgers.

        `actual` IS A WIDGET READ AND `expected` IS A MODEL READ, so the
        two cannot agree by construction. The two labels are asked what
        text they now carry; the expectation is rendered from the bot's
        live ledgers, read again here rather than from the snapshot the
        builder held. A builder that rendered a stale list, wrote the
        wrong label, or had its text overwritten further down the tab
        shows up as a mismatch on the operator's own machine.

        WHAT IT DOES NOT PROVE, said plainly: both sides go through
        `despawn_preview`, so this pin cannot show that the shared
        predicate matches the SWEEP. That is
        `tests/test_despawn_window_is_usable.py`'s job, and it does it
        by driving the shipped sweep and this preview over one fixture.

        THE DURATION SPANS THE PREVIEW, not the row build. Five passes
        over both ledgers run on the Qt GUI thread every time this tab
        is built or rebuilt, and BILL/USD carries 230 fold tranches
        today. That is the cost worth measuring on the operator's
        machine rather than arguing about here.
        """
        import contextlib

        with contextlib.suppress(Exception):
            from src.core.signal_contract import emit as _despawn_emit

            from ..trading.bot_container import (
                DESPAWN_PREVIEW_WINDOWS,
                despawn_preview,
            )
            _bot = dialog._bot
            _live_fold = list(getattr(_bot, "_fold_tranches", []) or [])
            _live_stack = list(getattr(_bot, "_stack_tranches", []) or [])
            _armed = despawn_preview(_live_fold, _live_stack, days, now_ts)
            _windows = [
                (w, despawn_preview(_live_fold, _live_stack, w, now_ts))
                for w in DESPAWN_PREVIEW_WINDOWS
            ]
            _timer_lbl = getattr(dialog, "_fold_despawn_timer_lbl", None)
            _preview_lbl = getattr(
                dialog, "_fold_despawn_preview_lbl", None)
            _despawn_emit(
                "gui.04.003.postcondition.despawn_rows_match_ledger",
                actual={
                    "timer_row": (
                        _timer_lbl.text() if _timer_lbl is not None
                        else None),
                    "preview_row": (
                        _preview_lbl.text() if _preview_lbl is not None
                        else None),
                },
                expected={
                    "timer_row": despawn_timer_text(days),
                    "preview_row": despawn_preview_text(
                        days, _armed, _windows),
                },
                duration=elapsed,
                context={
                    "bot_id": getattr(_bot, "bot_id", "?"),
                    "threshold_days": days,
                    "fold_open": len(_live_fold),
                    "stack_open": len(_live_stack),
                    "fold_removed": _armed["fold_removed"],
                    "usd_removed": _armed["usd_removed"],
                    "snapshot_fold_open": len(fold_snapshot),
                    "snapshot_stack_open": len(stack_snapshot),
                })

    def install_despawn_rows(dialog: BotLiveSettingsDialog,
                             form: QFormLayout,
                             tranches: list, now_ts: float) -> dict:
        """Add the two despawn rows to the health form; return the preview.

        THE DEFECT THIS REPAIRS IS NOT A BROKEN SWEEP. Item 9's despawn
        timer shipped on 2026-08-13 and works. Measured against the
        operator's state file on 2026-08-24: it reads 0 - Off - on all
        38 bots, every one of the 1,680 open fold tranches carries a
        usable `created_ts`, and the feature has never run once. The
        count that worries the operator is on THIS tab; the control is
        on the Settings tab; and nothing on either surface said what
        turning it on would do. So the panel now names the setting
        where the problem is already on screen, and prints the
        consequence BEFORE it is committed rather than after.

        NO BUTTON IS ADDED HERE, DELIBERATELY. Despawn is the
        AGE-driven removal and Clear is the operator's manual one. A
        "despawn now" button would be a second manual removal wearing
        the age function's name, and the operator's model has exactly
        three verbs - merge, despawn, clear. The setting stays the only
        way to arm this, and these rows exist to make that setting an
        informed choice.

        WHEN THE TIMER IS OFF the row prints one window per candidate
        in `DESPAWN_PREVIEW_WINDOWS`, so the operator picks a number
        against real counts instead of guessing. WHEN IT IS ON the row
        prints what the next sweep takes at the armed threshold.

        THE COUNTS COME FROM THE SHARED RULE, never from arithmetic
        written here. `despawn_preview` carries the sweep's own
        predicate - inclusive boundary, ageless records kept, stack
        records with live orders kept - and a second copy on this
        surface is exactly the defect that made the Min-rebuy column
        print a price the executor refuses.

        A MODULE FUNCTION AND NOT A METHOD, and that is load-bearing
        rather than style. `_create_fold_tranches_tab` is driven as an
        UNBOUND function by several existing test files, against stub
        dialogs that carry `_bot` and nothing else; a new `self.` call
        made 332 of those tests raise `AttributeError` when it was one.
        Resolved from the module, this reaches every caller the tab
        already has, and the handles are set on whatever object is
        passed.

        Args:
          dialog: the dialog building the tab. Only `_bot` is read;
            the two label handles are set on it.
          form: the Fold-Tranche Cycle Health `QFormLayout`.
          tranches: this bot's fold tranches, as the builder read them.
          now_ts: the wall clock the rest of the tab ages against, so
            the preview and the Age column cannot disagree.

        Returns:
          The preview at the ARMED threshold, which is all zeroes when
          the timer is off.

        """
        import time as _clock

        from ..trading.bot_container import (
            DESPAWN_PREVIEW_WINDOWS,
            despawn_preview,
            despawn_threshold_days,
        )

        _bot = dialog._bot
        _stack = list(getattr(_bot, "_stack_tranches", []) or [])
        _t0 = _clock.monotonic()
        _days = despawn_threshold_days(_bot.config)
        armed = despawn_preview(tranches, _stack, _days, now_ts)
        windows = [
            (w, despawn_preview(tranches, _stack, w, now_ts))
            for w in DESPAWN_PREVIEW_WINDOWS
        ]
        _elapsed = _clock.monotonic() - _t0

        timer_lbl = QLabel(despawn_timer_text(_days))
        timer_lbl.setToolTip(DESPAWN_ROW_TOOLTIP)
        # AMBER ONLY WHEN THE COLOUR IS TRUE. Off with nothing aged is
        # a correct, quiet state, and colouring it would teach the
        # operator to ignore the row. Off while the widest candidate
        # window already holds records is the state this unit exists
        # for, and it is the only one marked.
        _widest = windows[-1][1] if windows else armed
        if _days <= 0 and (_widest["fold_removed"]
                           + _widest["stack_removed"]):
            timer_lbl.setStyleSheet("color: #ff9900;")
        dialog._fold_despawn_timer_lbl = timer_lbl
        # issue #98 defect 6 - BOTH HALVES OF THE ROW. These two rows
        # already carried `DESPAWN_ROW_TOOLTIP` on the value; the words
        # the operator actually points at carried nothing. The text is
        # issue #103's and is not rewritten here - only the label half
        # is given the tooltip the value half already had.
        install_health_row(form, "Tranche despawn timer:", timer_lbl,
                           DESPAWN_ROW_TOOLTIP)

        preview_lbl = QLabel(
            despawn_preview_text(_days, armed, windows))
        dialog._fold_despawn_preview_lbl = preview_lbl
        install_health_row(form, "Despawn would remove:", preview_lbl,
                           DESPAWN_ROW_TOOLTIP)

        pin_despawn_rows(dialog, _days, tranches, _stack, now_ts,
                         _elapsed)
        return armed



    # ── The operator can REACH a tranche (issue #98 defect 7) ────────
    #
    # WHAT WAS WRONG. 280px over 30px rows put about EIGHT of up to 230
    # rows on screen, `setSortingEnabled` appeared zero times in this
    # file, and no filter or search existed. On TAO the summary named a
    # 30.4-day oldest tranche while rows one to three read 2.7d, 2.7d
    # and 3.6d. The row the headline was about could not be reached.
    #
    # THREE PARTS. The height cap follows the row count; the order is
    # chosen from stored fields and applied by rebuilding; the filter
    # HIDES rows without moving any. Qt's own `setSortingEnabled` is
    # still not used, and the reason is at `FOLD_SORT_ORDERS`: it moves
    # items and leaves `setCellWidget` widgets behind, which would
    # detach every Fire button from the row it is drawn on.
    #
    # MODULE FUNCTIONS AND NOT METHODS, for the reason
    # `install_despawn_rows` above records: `_create_fold_tranches_tab`
    # is driven as an UNBOUND function by several existing test files
    # against stub dialogs that carry `_bot` and little else, and a new
    # `self.` call inside the builder makes every one of them raise
    # `AttributeError`. Measured, not predicted: writing these as two
    # methods and calling them from the builder failed 324 tests across
    # five files. The dialog is passed in, and every attribute is read
    # with `getattr` and a default, so a stub builds the tab exactly as
    # the real dialog does.
    def fold_sort_order(dialog: BotLiveSettingsDialog) -> str:
        """Return the order the operator picked, or queue order.

        READ THROUGH ONE FUNCTION so the builder never guesses a
        default, and so a rebuild started by anything else - a clear, a
        refresh - keeps the operator's choice instead of silently
        snapping back to queue order. An order this panel does not
        offer is refused rather than passed through to the sorter.
        """
        order = getattr(dialog, "_fold_sort_key", FOLD_SORT_QUEUE_ORDER)
        if order not in FOLD_SORT_ORDERS:
            return FOLD_SORT_QUEUE_ORDER
        return order


    def build_fold_row_controls(
            dialog: BotLiveSettingsDialog) -> QHBoxLayout:
        """Build the order combo and the filter box, above the table."""
        row = QHBoxLayout()

        order_lbl = QLabel("Order:")
        order_lbl.setToolTip(FOLD_SORT_TOOLTIP)
        combo = QComboBox()
        combo.addItems(list(FOLD_SORT_ORDERS))
        combo.setCurrentText(fold_sort_order(dialog))
        combo.setToolTip(FOLD_SORT_TOOLTIP)
        # `activated` AND NOT `currentIndexChanged`. The rebuild below
        # destroys this combo and builds a new one with the chosen
        # order already selected; `currentIndexChanged` would fire
        # again on that programmatic `setCurrentText` and start a
        # second rebuild from inside the first.
        combo.activated.connect(
            lambda _index, dlg=dialog, box=combo:
                on_fold_sort_changed(dlg, box.currentText()))
        dialog._fold_sort_combo = combo

        edit = QLineEdit()
        edit.setPlaceholderText(FOLD_FILTER_PLACEHOLDER)
        edit.setToolTip(FOLD_FILTER_TOOLTIP)
        edit.setClearButtonEnabled(True)
        edit.textChanged.connect(
            lambda text, dlg=dialog: on_fold_filter_changed(dlg, text))
        dialog._fold_filter_edit = edit

        row.addWidget(order_lbl)
        row.addWidget(combo)
        row.addWidget(edit, 1)
        return row


    def on_fold_sort_changed(
            dialog: BotLiveSettingsDialog, order: str) -> None:
        """Remember the order and rebuild the tab to apply it.

        THE REBUILD IS DEFERRED BY ONE EVENT-LOOP TURN, and that is
        load-bearing rather than tidy. `_refresh_fold_tranches_tab`
        deletes the page this combo lives on, and this function runs
        inside that combo's own signal. Handing the rebuild to the
        event loop means the signal has returned before the sender is
        torn down.

        NOTHING IS REBUILT FOR AN ORDER THIS PANEL DOES NOT OFFER, and
        nothing is rebuilt when the order did not change.
        """
        if order not in FOLD_SORT_ORDERS:
            logger.warning(
                "Fold Tranches: ignoring unknown row order %r", order)
            return
        if order == fold_sort_order(dialog):
            return
        dialog._fold_sort_key = order
        rebuild = getattr(dialog, "_refresh_fold_tranches_tab", None)
        if not callable(rebuild):
            return
        from PySide6.QtCore import QTimer as _QTimer
        _QTimer.singleShot(0, rebuild)


    def on_fold_filter_changed(
            dialog: BotLiveSettingsDialog, needle: str) -> None:
        """Hide every row that does not contain `needle`.

        HIDING, NOT RE-ORDERING, AND NOT REBUILDING. `setRowHidden`
        leaves every row where it is, so the Fire button drawn on a row
        still belongs to that row's tranche. A rebuild would work too
        and costs a whole widget tree on every keystroke.

        The text it matches is `_fold_row_texts`, harvested from the
        built table, so the filter reads exactly what is on screen.
        """
        table = getattr(dialog, "_fold_tranche_table", None)
        if table is None:
            return
        texts = getattr(dialog, "_fold_row_texts", []) or []
        for row in range(table.rowCount()):
            cells = texts[row] if row < len(texts) else []
            table.setRowHidden(
                row, not fold_row_matches_filter(cells, needle))


    class BotLiveSettingsDialog(QDialog):
        """
        Editable bot detail dialog for running bots.

        Tab 1: Status — read-only stats
        Tab 2: Settings — editable config fields (applied immediately)
        (Pre-v3.20.4 also had Tab 3: Adjust Stack — removed alongside
        grid_bot cleanup.)
        """

        settings_changed = Signal(str, dict)  # bot_id, {field: new_value}

        # issue #98 defect 7 - the row order the operator chose, held
        # on the dialog so a rebuild started by anything at all - a
        # clear, a refresh, a second order change - keeps their choice.
        #
        # A CLASS ATTRIBUTE, NOT AN `__init__` LINE, and the reason is
        # the same one that made the reach controls module functions:
        # several test files build this tab through a STUB dialog that
        # never runs `__init__`. A class default is inherited by a real
        # dialog and read through `getattr` by a stub, so one spelling
        # serves both. `fold_sort_order` still refuses a value this
        # panel does not offer, whichever way it arrived.
        _fold_sort_key: str = FOLD_SORT_QUEUE_ORDER

        def __init__(self, bot, bot_manager=None, parent=None):
            super().__init__(parent)
            self._bot = bot
            self._bm = bot_manager
            self._changes: dict = {}
            # v3.16.18 — navigation between sibling bots without
            # closing the dialog manually. Set by the Prev/Next
            # buttons; main_window._on_bot_clicked reads after
            # exec() returns and re-opens the dialog for the
            # target bot at the same geometry + active tab.
            self._pending_navigate_to: str | None = None

            cfg = bot.config
            bid = bot.bot_id
            self.setWindowTitle(f"Bot Settings — {cfg.symbol} [{bid[:8]}]")
            # MEM-240 — minimum raised from (620, 580) because the
            # Settings tab alone contains ~980px of controls across 4
            # group boxes (Trading Parameters, Scrumming Settings,
            # Advanced Scrumming, Hedge Rebalance). At 580px the
            # QFormLayout rows compressed to sub-minimum heights,
            # causing QDoubleSpinBox/QComboBox/QCheckBox to render
            # as striped bands (Qt's native widget paint code can't
            # draw controls below ~24px tall). Tabs now also wrap in
            # QScrollArea as a safety net for smaller screens.
            self.setMinimumSize(640, 720)

            layout = QVBoxLayout(self)

            # Header
            hdr_row = QHBoxLayout()
            hdr = QLabel(f"{cfg.symbol}  •  {cfg.mode.value.upper()}")
            hdr.setStyleSheet("font-size: 18px; font-weight: bold; color: #00ffcc;")
            hdr_row.addWidget(hdr)

            state = bot.state.value
            state_colors = {"running": "#00ff88", "idle": "#888", "paused": "#ffaa00",
                            "error": "#ff3366", "stopped": "#666", "cooldown": "#ffaa00"}
            state_lbl = QLabel(f"  {state.upper()}")
            state_lbl.setStyleSheet(
                f"font-size: 14px; font-weight: bold; "
                f"color: {state_colors.get(state, '#ccc')}; "
                f"background: {state_colors.get(state, '#ccc')}22; "
                f"padding: 2px 8px; border-radius: 4px;")
            hdr_row.addWidget(state_lbl)
            hdr_row.addStretch()

            # v3.16.18 — Prev / Next bot navigation buttons.
            # Lets the operator cycle through sibling bots without
            # closing+re-opening the Detail panel manually. Order
            # follows BotManager._bots insertion order, with wrap-around
            # at both ends. Buttons are hidden if there's only one bot.
            nav_btn_qss = (
                "QPushButton { background: #1a1a2e; color: #00ffcc; "
                "border: 1px solid #00ffcc55; border-radius: 4px; "
                "padding: 4px 10px; font-weight: bold; font-size: 12px; "
                "min-width: 70px; }"
                "QPushButton:hover { background: #00ffcc22; "
                "border: 1px solid #00ffcc; }"
                "QPushButton:disabled { background: #2a2a3f; "
                "color: #555; border: 1px solid #2a2a3f; }"
            )
            self._prev_btn = QPushButton("◀ Prev")
            self._prev_btn.setStyleSheet(nav_btn_qss)
            self._prev_btn.setToolTip(
                "Switch to the previous bot in the swarm without "
                "closing this dialog (Ctrl+Left)")
            self._prev_btn.clicked.connect(
                lambda: self._navigate_to_sibling(-1))
            hdr_row.addWidget(self._prev_btn)

            self._next_btn = QPushButton("Next ▶")
            self._next_btn.setStyleSheet(nav_btn_qss)
            self._next_btn.setToolTip(
                "Switch to the next bot in the swarm without "
                "closing this dialog (Ctrl+Right)")
            self._next_btn.clicked.connect(
                lambda: self._navigate_to_sibling(1))
            hdr_row.addWidget(self._next_btn)

            # Hide both if we can't navigate (single-bot or no manager)
            _siblings = self._sibling_bot_ids()
            _can_nav = len(_siblings) > 1
            self._prev_btn.setVisible(_can_nav)
            self._next_btn.setVisible(_can_nav)

            layout.addLayout(hdr_row)

            # Tabs
            tabs = QTabWidget()
            self._tabs = tabs  # v3.16.18 — used by navigation to
                               # report the active tab back to the
                               # parent so the next bot's dialog
                               # opens on the same tab.

            # --- Tab 1: Status ---
            tabs.addTab(self._wrap_scrollable(
                self._create_status_tab()), "Status")

            # --- Tab 2: Settings ---
            tabs.addTab(self._wrap_scrollable(
                self._create_settings_tab()), "Settings")

            # --- Tab 3: Fold Tranches (Scrumming only — v3.16.39 P2-VIS) ---
            # Operator directive 2026-05-08 (post live-trading evaluation):
            # surface the bot's two-leg cycle machinery — open
            # _fold_tranches, parked USD, oldest tranche age,
            # lifetime created/closed counters — so the operator can
            # see Leg-1/Leg-2 health at a glance instead of needing
            # post-hoc CSV analysis. MEM-171 / ADR-004 mechanics.
            if cfg.mode.value == "scrumming":
                # issue #98 defect 1 - installed through the one site
                # that also records the page, so a clear can rebuild
                # this tab in place instead of telling the operator to
                # reopen the dialog.
                self._install_fold_tranches_tab(tabs)

            # --- Tab 3.5: Stack Tranches (Scrumming only) ---
            # v3.23.28 — mirror of Fold Tranches for the Stack Mode
            # ledger.
            # v3.23.29 — dropped the `stack_mode` sub-gate: the tab
            # now always renders for scrumming bots (matching Fold
            # Tranches behaviour). When the ledger is empty OR
            # stack_mode is off, _create_stack_tranches_tab() renders
            # a friendly "no tranches yet" panel with the enable hint
            # instead of the tab being invisible. Operator-reported
            # 2026-07-25: the sub-gate hid the tab even while inspecting
            # the feature, defeating the reason for adding it.
            if cfg.mode.value == "scrumming":
                tabs.addTab(self._wrap_scrollable(
                    self._create_stack_tranches_tab()), "Stack Tranches")

            # --- Tab 4: Bot Swarm (Scrumming only — v3.16.44 P2-VIS) ---
            # Operator directive 2026-05-08: pre-emptively surface Smart
            # Wire / Bot Swarm state — outbound wires, inbound wires,
            # pending credits, provenance, recent transactions — so issues
            # in this code path can be caught BEFORE they accumulate (same
            # pattern that Fold Tranches tab caught the compound bug).
            if cfg.mode.value == "scrumming":
                tabs.addTab(self._wrap_scrollable(
                    self._create_bot_swarm_tab()), "Bot Swarm")

            # --- Tab 5: Market Inspector (Scrumming only — v3.23.37) ---
            # Per-bot view of the shared Market Inspector's most recent
            # HTF scan. Renders this bot's asset card, higher-scoring
            # markets in the top-50 universe, and opposing pairs that
            # feature this bot's asset. Reads from
            # src.trading.market_inspector.get_shared_inspector(); the
            # top-level Market Inspector tab owns the fetch cycle.
            # Replaced the legacy Mr. Inspector tab which was a
            # phantom for crypto bots (no caller wired
            # ScrummingBot._mr_inspector).
            if cfg.mode.value == "scrumming":
                tabs.addTab(self._wrap_scrollable(
                    self._create_market_inspector_tab()),
                    "Market Inspector")

            # --- Tab 6: Phantom Bots (Scrumming only — merged v3.23.39) ---
            # Single tab combining the retired "Phantom State" (runtime
            # view) with the "Phantom Bot" config surface. Per operator
            # directive 2026-07-27: consolidate so the two aspects of the
            # phantom subsystem live in one place. Order inside the tab:
            # config (enable + TFs + lock) → coordinator status →
            # per-phantom table → active locks.
            if cfg.mode.value == "scrumming":
                tabs.addTab(self._wrap_scrollable(
                    self._create_phantom_bots_tab()), "Phantom Bots")

            # v3.20.4 — Adjust Stack tab removed (grid_bot deleted
            # v3.16.0; cfg.mode.value can never be "grid" since
            # BotMode.GRID was dropped from the enum).

            # --- v3.19.3: Positions Held (Extractor only) ---
            # Operator decision #7 from the Extractor design doc:
            # per-position Manual Fire buttons in a dedicated tab.
            # No global fire — each open position has its own button
            # that closes that specific position at market.
            if cfg.mode.value == "extractor":
                tabs.addTab(self._wrap_scrollable(
                    self._create_positions_held_tab()), "Positions Held")

            layout.addWidget(tabs)

            # Bottom buttons
            btn_row = QHBoxLayout()
            btn_row.addStretch()

            self._apply_btn = QPushButton("Apply Changes")
            self._apply_btn.setStyleSheet(
                "QPushButton { background: #00ffcc; color: #0a0a12; "
                "border: none; border-radius: 6px; padding: 8px 20px; "
                "font-weight: bold; font-size: 12px; }"
                "QPushButton:hover { background: #00ddaa; }"
                "QPushButton:disabled { background: #333; color: #666; }")
            self._apply_btn.setEnabled(False)
            self._apply_btn.clicked.connect(self._apply_changes)
            btn_row.addWidget(self._apply_btn)

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet(
                "QPushButton { background: #2a2a3f; color: #aaa; "
                "border: 1px solid #3a3a5f; border-radius: 6px; "
                "padding: 8px 20px; }"
                "QPushButton:hover { background: #3a3a5f; }")
            close_btn.clicked.connect(self.accept)
            btn_row.addWidget(close_btn)
            layout.addLayout(btn_row)

            # Change indicator
            self._change_lbl = QLabel("")
            self._change_lbl.setStyleSheet("color: #ffaa00; font-size: 11px;")
            layout.addWidget(self._change_lbl)

            # v3.16.18 — Ctrl+Left / Ctrl+Right keyboard shortcuts
            # for Prev/Next navigation. Only wire up when we actually
            # have siblings to navigate between.
            try:
                from PySide6.QtGui import QShortcut, QKeySequence
                if _can_nav:
                    QShortcut(QKeySequence("Ctrl+Left"), self,
                              activated=lambda: self._navigate_to_sibling(-1))
                    QShortcut(QKeySequence("Ctrl+Right"), self,
                              activated=lambda: self._navigate_to_sibling(1))
            except Exception as _shortcut_exc:  # noqa: BLE001 - keyboard shortcut wiring is optional
                logger.debug(
                    "sibling navigation shortcuts unavailable: %s",
                    _shortcut_exc)

        # ── v3.16.18 — sibling navigation ──────────────────────────
        def _sibling_bot_ids(self) -> list:
            """Return the ordered list of bot ids in the current
            BotManager, in insertion order. Empty list when no
            manager is attached (e.g., dialog opened in test
            harness)."""
            if self._bm is None:
                return []
            try:
                return list(self._bm._bots.keys())
            except Exception:  # R28-OK: bot-manager probe; treat as no siblings on access failure
                return []

        def _navigate_to_sibling(self, direction: int) -> None:
            """Stage a navigation request and close this dialog.

            ``direction`` is +1 (Next) or -1 (Prev). Wraps around
            both ends so the operator can cycle through the swarm
            indefinitely. The actual close+reopen is performed by
            ``main_window._on_bot_clicked`` once exec() returns —
            this method only sets ``self._pending_navigate_to``
            with the target bot_id, then accepts the dialog.

            Pending unsaved changes are discarded (consistent with
            the existing Close button behaviour). Apply Changes
            must be clicked first to commit edits.
            """
            ids = self._sibling_bot_ids()
            if len(ids) < 2:
                return
            try:
                cur_idx = ids.index(self._bot.bot_id)
            except ValueError:
                # Current bot was unregistered while the dialog was
                # open — fall through to opening the first bot in
                # the list rather than crashing.
                cur_idx = 0 if direction > 0 else 1
            new_idx = (cur_idx + direction) % len(ids)
            self._pending_navigate_to = ids[new_idx]
            self.accept()

        def active_tab_index(self) -> int:
            """v3.16.18 — Used by main_window so the next bot's
            dialog opens on the same tab the operator was viewing
            (e.g., they navigated from the Settings tab; the next
            bot's dialog should open on Settings, not Status)."""
            try:
                return int(self._tabs.currentIndex())
            except Exception:  # R28-OK: tab-index probe; default to Status (0) on access failure
                return 0

        def _wrap_scrollable(self, content: QWidget) -> QScrollArea:
            """MEM-240 — Wrap a tab's content widget in a QScrollArea
            so QFormLayout rows never get compressed below their
            natural height.

            Background: when the dialog is smaller than the tab's
            intrinsic size, QTabWidget hands the tab less vertical
            space. Without a scroll area in between, QVBoxLayout
            redistributes that shortage down into the child
            QGroupBoxes, which in turn compresses their QFormLayout
            rows. Rows compressed below ~24px cause Qt's native
            widget paint to fail, rendering QDoubleSpinBox /
            QComboBox / QCheckBox as horizontal striped bands rather
            than controls. A scroll area fixes this by giving the
            content its natural size and introducing a scroll bar
            when the viewport is too small.

            setWidgetResizable(True) = the child widget expands
            horizontally with the viewport but keeps its own
            vertical size; that's exactly what we want here.
            """
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            scroll.setWidget(content)
            return scroll

        def _configure_form(self, form: QFormLayout) -> None:
            """MEM-240 — Apply row-sizing defaults that keep form rows
            at natural height regardless of container pressure.

            - fieldGrowthPolicy=AllNonFixedFieldsGrow: fields expand
              horizontally to fill available width (prevents labels
              wrapping unpredictably).
            - rowWrapPolicy=DontWrapRows: labels and fields stay on
              the same line at dialog minimum widths.
            - Generous spacing so rows don't visually collide even
              when the theme-provided row baseline is small.
            """
            form.setFieldGrowthPolicy(
                QFormLayout.AllNonFixedFieldsGrow)
            form.setRowWrapPolicy(QFormLayout.DontWrapRows)
            form.setHorizontalSpacing(12)
            form.setVerticalSpacing(8)
            form.setContentsMargins(8, 8, 8, 8)

        def _refresh_target_denom_rows(self) -> None:
            """v3.23.48 — repaint the Target-BTC + Target-ETH rows
            using current scout + currency-monitor data. Idempotent
            and non-raising; called by the periodic timer AND once at
            construction."""
            try:
                _btc_lbl = getattr(self, "_target_btc_lbl", None)
                _eth_lbl = getattr(self, "_target_eth_lbl", None)
                _btc_row = getattr(
                    self, "_target_btc_row_label", None)
                _eth_row = getattr(
                    self, "_target_eth_row_label", None)
                if _btc_lbl is None or _eth_lbl is None:
                    return
                _bot = getattr(self, "_bot", None)
                if _bot is None:
                    return
                _cfg = getattr(_bot, "config", None)
                if _cfg is None:
                    return
                _asset = str(getattr(
                    _cfg, "target_asset", "") or "").upper()
                _eid = str(getattr(
                    _cfg, "exchange_id", "") or "")
                _target_usd = float(getattr(
                    _cfg, "target_balance", 0.0) or 0.0)
                # Import here to keep top-level GUI imports cheap.
                from ..exchange.currency_rate_monitor import (
                    get_currency_monitor)
                from ..exchange.market_pairs_scout import get_scout
                _rates = get_currency_monitor().snapshot()
                _scout = get_scout()
                _usd_pair = _scout.get_pair(
                    _asset, "USD", exchange_id=(_eid or None))
                if _usd_pair is None:
                    _usd_pair = _scout.get_pair(
                        _asset, "USDC", exchange_id=(_eid or None))
                _usd_pct = (
                    float(_usd_pair.pct_24h) if _usd_pair else 0.0)
                # BTC row
                if _asset == "BTC":
                    _btc_row.setVisible(False)
                    _btc_lbl.setVisible(False)
                else:
                    _btc_row.setVisible(True)
                    _btc_lbl.setVisible(True)
                    _btc_pair = _scout.get_pair(
                        _asset, "BTC", exchange_id=(_eid or None))
                    if _btc_pair is None:
                        _btc_lbl.setText("(not listed on exchange)")
                        _btc_lbl.setStyleSheet("color: #888;")
                    else:
                        _txt, _color = _compose_denom_row_text(
                            "BTC", _target_usd, _rates.btc_usd,
                            _btc_pair.pct_24h, _usd_pct)
                        _btc_lbl.setText(_txt)
                        _btc_lbl.setStyleSheet(f"color: {_color};")
                # ETH row
                if _asset == "ETH":
                    _eth_row.setVisible(False)
                    _eth_lbl.setVisible(False)
                else:
                    _eth_row.setVisible(True)
                    _eth_lbl.setVisible(True)
                    _eth_pair = _scout.get_pair(
                        _asset, "ETH", exchange_id=(_eid or None))
                    if _eth_pair is None:
                        _eth_lbl.setText("(not listed on exchange)")
                        _eth_lbl.setStyleSheet("color: #888;")
                    else:
                        _txt, _color = _compose_denom_row_text(
                            "ETH", _target_usd, _rates.eth_usd,
                            _eth_pair.pct_24h, _usd_pct)
                        _eth_lbl.setText(_txt)
                        _eth_lbl.setStyleSheet(f"color: {_color};")
            except Exception as _denom_exc:  # noqa: BLE001 - refresh best-effort
                logger.debug(
                    "target denom row refresh raised: %s", _denom_exc)

        def _mark_changed(self, field: str, value):
            """Track a changed field and enable Apply button."""
            # MEM-232: phantom fields aren't on BotConfig — read the
            # current runtime value from the bot instance for the
            # comparison so "pending change" logic is accurate.
            if field == "enable_phantoms":
                original = getattr(self._bot, "_phantoms_enabled", None)
            elif field == "phantom_timeframes":
                original = list(getattr(self._bot, "_phantom_timeframes", []))
                value = list(value)
            elif field == "lock_candle_count":
                coord = getattr(self._bot, "_coordinator", None)
                original = getattr(coord, "lock_candle_count", None) if coord else None
            else:
                original = getattr(self._bot.config, field, None)

            if value == original:
                self._changes.pop(field, None)
            else:
                self._changes[field] = value

            if self._changes:
                self._apply_btn.setEnabled(True)
                fields = ", ".join(self._changes.keys())
                self._change_lbl.setText(f"Pending changes: {fields}")
            else:
                self._apply_btn.setEnabled(False)
                self._change_lbl.setText("")

        def _apply_changes(self):
            """Apply all pending changes to the bot config."""
            if not self._changes:
                return

            cfg = self._bot.config
            applied = []

            # MEM-232: phantom fields don't live on BotConfig — they're
            # runtime attributes on ScrummingBot. Route them through
            # update_phantom_config() which handles mid-session safely.
            _PHANTOM_FIELDS = {
                "enable_phantoms", "phantom_timeframes", "lock_candle_count"}
            phantom_changes = {f: v for f, v in self._changes.items()
                               if f in _PHANTOM_FIELDS}
            other_changes = {f: v for f, v in self._changes.items()
                             if f not in _PHANTOM_FIELDS}

            if phantom_changes and hasattr(
                    self._bot, "update_phantom_config"):
                try:
                    result = self._bot.update_phantom_config(**phantom_changes)
                    for k, v in result.get("applied", {}).items():
                        applied.append(f"{k}={v}")
                    for caveat in result.get("caveats", []):
                        logger.info("Bot %s phantom caveat: %s",
                                    self._bot.bot_id[:8], caveat)
                except Exception as exc:  # sadp: R61 CBF — surface in log
                    logger.warning(
                        "Bot %s: phantom config update failed: %s",
                        self._bot.bot_id[:8], exc)

            # Session 26 (2026-04-24) operator-reported bug: setattr on
            # config alone leaves the bot's RUNTIME attributes stale.
            # Some fields have runtime parallels on ScrummingBot that
            # must be updated in lockstep. Route those through the
            # bot's own live-update methods; plain config-only fields
            # keep the old setattr path.
            # Session 26 full Settings→Functions audit (2026-04-24):
            # fields whose values are snapshotted into ScrummingBot
            # runtime attrs at __init__ and consumed via those attrs
            # (not re-read from config each tick) MUST be routed through
            # a bot method that updates both surfaces. Otherwise live
            # setattr on config leaves the runtime stale. Full list in
            # docs/operator_logs/AUDIT_2026-04-24_settings_to_functions.md.
            _RUNTIME_ROUTED = {
                "target_balance":     "set_target_balance_live",
                "visibility":         "set_visibility_live",
                "aggressive_trading": "set_aggressive_live",
                "hedge_balance":      "set_hedge_balance_live",
                # v3.20.5 — Pool Size live-update (Extractor only).
                # Operator-reported 2026-05-23 that editing this field
                # didn't refresh the dashboard's Pool/Liquid numerics —
                # root cause was no runtime hook. ExtractorBot.
                # set_chunk_size_usd() recomputes chunk_size_base from
                # the rate captured at construction, scales _chunk_free_
                # base proportionally so deployed positions aren't
                # disturbed, and resizes the CapitalReservationRegistry
                # claim so concurrent ScrummingBots see the new number.
                "extractor_chunk_size_usd": "set_chunk_size_usd",
            }
            for field, value in other_changes.items():
                route = _RUNTIME_ROUTED.get(field)
                if route and hasattr(self._bot, route):
                    try:
                        result = getattr(self._bot, route)(value)
                        if result.get("applied"):
                            applied.append(f"{field}={value} (runtime+anchor synced)")
                        else:
                            reason = result.get("reason", "unknown")
                            logger.warning(
                                "Bot %s: %s live-update refused: %s",
                                self._bot.bot_id[:8], field, reason)
                            applied.append(f"{field}={value} (REFUSED: {reason})")
                    except Exception as exc:
                        logger.warning(
                            "Bot %s: %s live-update raised: %s",
                            self._bot.bot_id[:8], field, exc)
                        applied.append(f"{field}={value} (ERROR: {exc})")
                elif hasattr(cfg, field):
                    setattr(cfg, field, value)
                    applied.append(f"{field}={value}")

            logger.info("Bot %s: live settings changed: %s",
                        self._bot.bot_id[:8], ", ".join(applied))
            self._changes.clear()
            self._apply_btn.setEnabled(False)
            self._change_lbl.setText(
                f"Applied {len(applied)} change(s) — active immediately")
            self._change_lbl.setStyleSheet("color: #00ff88; font-size: 11px;")

            self.settings_changed.emit(self._bot.bot_id,
                                       {f: getattr(cfg, f, None) for f in [a.split("=")[0] for a in applied]})

        # ---------------------------------------------------------------
        # v3.15.62 — Self-destruct handler with type-to-confirm
        # ---------------------------------------------------------------
        def _on_self_destruct_clicked(self) -> None:
            """Operator-initiated SELF-DESTRUCT. Two-step confirmation:
            (1) modal dialog explains the consequences and requires
                the operator to type "SELF-DESTRUCT" literally.
            (2) call bot.self_destruct(confirmation_token=...) which
                only proceeds if the token matches.

            All paths are non-raising — the dialog is non-modal blocking
            and any exceptions surface in the bot's log.
            """
            try:
                from PySide6.QtWidgets import (
                    QInputDialog, QMessageBox, QLineEdit,
                )
            except Exception:
                return
            if not hasattr(self._bot, "self_destruct"):
                QMessageBox.warning(
                    self, "Self-Destruct Unavailable",
                    "This bot type does not support self-destruct.")
                return
            sym = getattr(self._bot.config, "symbol", "?")
            bid = (self._bot.bot_id[:8]
                   if getattr(self._bot, "bot_id", None) else "?")
            text, ok = QInputDialog.getText(
                self, "Confirm SELF-DESTRUCT",
                f"This will MARKET-SELL the entire {sym} position "
                f"on bot {bid} and PAUSE the bot.\n\n"
                f"State (lots, tranches, fold queue) will be CLEARED.\n"
                f"All auto gates (BB threshold, hysteresis, circuit\n"
                f"breakers, higher-TF bias) BYPASSED.\n\n"
                f"To confirm, type SELF-DESTRUCT (case-sensitive):",
                QLineEdit.Normal, "")
            if not ok:
                return
            if (text or "").strip() != "SELF-DESTRUCT":
                QMessageBox.information(
                    self, "Self-Destruct Cancelled",
                    "Confirmation token did not match. No action taken.")
                return
            # Run the async self_destruct method. We use asyncio.run on
            # a fresh thread so we don't block the GUI nor require an
            # event loop in the dialog thread.
            import threading, asyncio as _aio
            def _run():
                # SELF_DESTRUCT_TOKEN is an operator confirmation phrase,
                # not a credential — extracted into a local so Bandit's
                # B106 (function-arg literal) heuristic doesn't misread
                # it. Suppressed via nosec on the assignment.
                _sd_phrase = "SELF-DESTRUCT"  # nosec B105
                try:
                    result = _aio.run(
                        self._bot.self_destruct(
                            confirmation_token=_sd_phrase))
                    logger.info(
                        "Bot %s self_destruct result: %s",
                        bid, result)
                except Exception as exc:
                    logger.warning(
                        "Bot %s self_destruct dispatch raised: %s",
                        bid, exc)
            threading.Thread(
                target=_run, daemon=True,
                name=f"self-destruct-{bid}").start()
            QMessageBox.information(
                self, "Self-Destruct Dispatched",
                f"Self-destruct dispatched for bot {bid} — "
                f"check the Activity Log for SELF-DESTRUCT FIRING "
                f"or SELF-DESTRUCT FAILED to confirm outcome.\n"
                f"Bot will be PAUSED on completion.")

        # ---------------------------------------------------------------
        # Tab 1: Status (read-only)
        # ---------------------------------------------------------------
        def _create_status_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.setSpacing(6)

            status = self._bot.get_status()
            stats = status.get("stats", {})
            cfg = self._bot.config

            # Stats
            stats_group = QGroupBox("Statistics")
            sf = QFormLayout(stats_group)
            self._configure_form(sf)

            # v3.23.7 Anomaly B: internal `stats.realised_pnl` display row
            # removed. Operator directive 2026-06-13: "Prefer to just pull
            # from the exchange. It is the true indicator of position
            # health." The exchange-pulled FIFO-matched realized P/L (see
            # below) is the sole P/L displayed; the (exchange) qualifier
            # is dropped from its label since it is now the only one.

            # v3.16.47 — Exchange-pulled position health (updated every
            # 5 min by tick loop; bootstrap-refreshed on first start).
            # Operator directive 2026-05-10: position health belongs to
            # the exchange. Display alongside internal so divergence is
            # visible at a glance.
            _bot_stats = getattr(self._bot, "stats", None)
            if _bot_stats is not None:
                _re = float(getattr(_bot_stats, "realized_pnl_exchange", 0.0) or 0.0)
                _ae = float(getattr(_bot_stats, "avg_entry_exchange", 0.0) or 0.0)
                _cb = float(getattr(_bot_stats, "cost_basis_total_exchange", 0.0) or 0.0)
                _ue = float(getattr(_bot_stats, "unrealised_pnl", 0.0) or 0.0)
                _fee = float(getattr(_bot_stats, "fees_paid_exchange", 0.0) or 0.0)
                _tc = int(getattr(_bot_stats, "exchange_trade_count", 0) or 0)
                _fts = float(getattr(_bot_stats, "exchange_data_fresh_ts", 0.0) or 0.0)

                if _fts > 0:
                    import time as _t
                    _age_sec = _t.time() - _fts
                    _age_str = (f"{_age_sec:.0f}s" if _age_sec < 60
                                else f"{_age_sec/60:.1f}m")

                    rep_lbl = QLabel(f"${_re:+,.4f}")
                    rep_lbl.setStyleSheet(
                        f"font-weight: bold; font-size: 13px; "
                        f"color: {'#00ff88' if _re >= 0 else '#ff3366'};")
                    rep_lbl.setToolTip(
                        f"Realized P/L pulled from the exchange "
                        f"(FIFO-matched buy/sell pairs from {_tc} trades). "
                        f"Refreshed {_age_str} ago.")
                    # v3.23.7 Anomaly B: label dropped the "(exchange)"
                    # qualifier — this is now the only P/L row.
                    sf.addRow("Realised P/L:", rep_lbl)

                    if _ue != 0:
                        ue_lbl = QLabel(f"${_ue:+,.4f}")
                        ue_lbl.setStyleSheet(
                            f"color: {'#00ff88' if _ue >= 0 else '#ff3366'};")
                        sf.addRow("Unrealised P/L:", ue_lbl)

                    if _ae > 0:
                        sf.addRow("Avg Entry (exchange):",
                                  QLabel(f"${_ae:.8f}"))
                        sf.addRow("Cost Basis Total:",
                                  QLabel(f"${_cb:,.4f}"))
                    if _fee > 0:
                        sf.addRow("Fees Paid:",
                                  QLabel(f"${_fee:,.4f}"))
                else:
                    pending_lbl = QLabel("— (refresh pending)")
                    pending_lbl.setStyleSheet("color: #888;")
                    pending_lbl.setToolTip(
                        "Exchange position health refresh has not yet "
                        "completed. First refresh fires on bot bootstrap; "
                        "subsequent every 5 minutes.")
                    # v3.23.7 Anomaly B: label dropped "(exchange)" qualifier.
                    sf.addRow("Realised P/L:", pending_lbl)

            sf.addRow("Total Trades:", QLabel(str(stats.get("total_trades", 0))))
            sf.addRow("Active Buys:", QLabel(str(stats.get("active_buys", 0))))
            sf.addRow("Active Sells:", QLabel(str(stats.get("active_sells", 0))))

            from ..core.fmt import fmt_price as _fp
            price = stats.get("current_price", 0)
            sf.addRow("Current Price:", QLabel(_fp(price) if price > 0 else "—"))
            sf.addRow("Uptime:", QLabel(f"{stats.get('uptime', 0):.0f}s"))

            if stats.get("last_error"):
                err = QLabel(stats["last_error"][:80])
                err.setStyleSheet("color: #ff3366;")
                err.setWordWrap(True)
                sf.addRow("Last Error:", err)
            layout.addWidget(stats_group)

            # v3.20.4 — Grid Levels table removed (grid_bot deleted
            # v3.16.0; no live bot has a `grid` attribute).

            layout.addStretch()
            return w

        # ---------------------------------------------------------------
        # Tab 3: Fold Tranches (v3.16.39 P2-VIS, scrumming-only)
        # ---------------------------------------------------------------
        # Surfaces the bot's two-leg cycle machinery per MEM-171 /
        # ADR-004. A SCRUM consumes _main_lots highest-initial_buy_price-
        # first and parks proceeds in _fold_tranches with TWO recorded
        # prices: ref (the SCRUM's sell price) and initial_buy_price
        # (the original buy cost — patent CEILING for re-acquisition,
        # NOT a floor). Leg-2 (FOLD-BACK) fires when current price is
        # BELOW BOTH the ref (binding gate; ensures unit-surplus) AND
        # the initial_buy_price ceiling (patent invariant). Until then,
        # the tranche sits in queue.
        #
        # Operator's pre-2026-05-08 visibility: none. Could only see the
        # cumulative state by pulling persisted state JSON manually.
        # This tab makes the queue first-class.
        def _create_positions_held_tab(self) -> QWidget:
            """v3.19.3 — Positions Held tab for Extractor bots.

            Renders one row per open ExtractorPosition with the columns
            from design doc §10: Pair | State | Tier | Alt units |
            Entry (USD) | Current (USD) | Δ% (USD) | Corrections |
            Manual Fire (button).

            Per operator decision #7, the Manual Fire button is
            per-position only — NO global fire on the bot row. Clicking
            a row's button immediately closes that specific position at
            market via ``ExtractorBot.manual_fire_position(pair)``.

            Position values reported here use the position's stored
            avg-buy price as a fallback; live ticker refresh happens
            asynchronously by the bot's tick loop. Operator can re-open
            the dialog (or rely on the bot table's pool color) for
            up-to-date status.

            sadp: R28 R55  # manual override per-position + non-blocking dispatch
            """
            from PySide6.QtWidgets import (
                QGroupBox, QFormLayout, QLabel, QPushButton,
                QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
            )
            from PySide6.QtCore import Qt
            import asyncio as _asyncio
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.setSpacing(8)

            # --- Summary section ---
            summary = QGroupBox("Extractor Pool Status")
            sf = QFormLayout(summary)
            self._configure_form(sf)
            chunk_size_usd = float(getattr(
                self._bot, "_chunk_size_usd", 0.0) or 0.0)
            chunk_free_base = float(getattr(
                self._bot, "_chunk_free_base", 0.0) or 0.0)
            chunk_size_base = float(getattr(
                self._bot, "_chunk_size_base", 0.0) or 0.0)
            extracted_total = float(getattr(
                self._bot, "_chunk_extracted_total", 0.0) or 0.0)
            base_currency = self._bot.config.base_currency
            try:
                pool_color = self._bot.pool_color()
            except Exception:  # R28-OK: snapshot read; UI doesn't crash on bot lookup
                pool_color = "green"
            color_hex = {"green": "#00ff88", "yellow": "#ffaa00",
                         "red": "#ff3366"}.get(pool_color, "#a8a8c5")
            pool_lbl = QLabel(f"<b>{pool_color.upper()}</b>")
            pool_lbl.setStyleSheet(f"color: {color_hex}; font-size: 14px;")
            sf.addRow("Pool color:", pool_lbl)
            sf.addRow(f"Chunk size ({base_currency} / USD):",
                      QLabel(f"{chunk_size_base:.8f} / ${chunk_size_usd:,.2f}"))
            sf.addRow(f"Chunk free ({base_currency}):",
                      QLabel(f"{chunk_free_base:.8f}"))
            sf.addRow(f"Lifetime extracted ({base_currency}):",
                      QLabel(f"{extracted_total:+.8f}"))
            layout.addWidget(summary)

            # --- Positions table ---
            try:
                positions = self._bot.positions_for_gui()
            except Exception:  # R28-OK: snapshot read; UI doesn't crash
                positions = []

            if not positions:
                empty_lbl = QLabel(
                    "<i>No open positions. Bot is watching its top-N "
                    "watch list for bearish signals. Pool color is "
                    "<b>GREEN</b> (fully in base currency).</i>")
                empty_lbl.setWordWrap(True)
                empty_lbl.setStyleSheet("color: #8a8aab; padding: 16px;")
                layout.addWidget(empty_lbl)
                layout.addStretch()
                return w

            table = QTableWidget()
            columns = [
                "Pair", "State", "Tier", "Alt units",
                "Entry (USD)", "Current (USD)", "Δ% (USD)",
                "Corrections", "Manual Fire",
            ]
            table.setColumnCount(len(columns))
            table.setHorizontalHeaderLabels(columns)
            table.setRowCount(len(positions))
            table.horizontalHeader().setSectionResizeMode(
                QHeaderView.ResizeToContents)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectRows)
            table.setAlternatingRowColors(True)

            for row, p in enumerate(positions):
                pair = str(p.get("pair", ""))
                state = str(p.get("state", ""))
                tier = int(p.get("tier", 1))
                alt_units = float(p.get("alt_units", 0.0))
                entry_usd = float(p.get("entry_usd", 0.0))
                current_usd = float(p.get("current_usd_approx", 0.0))
                delta_pct = float(p.get("delta_pct_usd_approx", 0.0))
                corrections = int(p.get("corrections_fired", 0))

                cells = [
                    pair, state.upper(), str(tier),
                    f"{alt_units:.6f}",
                    f"${entry_usd:,.4f}",
                    f"${current_usd:,.4f}",
                    f"{delta_pct:+.2f}%",
                    str(corrections),
                ]
                for col, txt in enumerate(cells):
                    item = QTableWidgetItem(txt)
                    item.setTextAlignment(Qt.AlignCenter)
                    # State cell color: red on drawdown, amber on
                    # bullish_exit-pending, green on in_flight
                    if col == 1:
                        if state == "drawdown":
                            item.setForeground(Qt.red)
                        elif state == "bullish_exit":
                            item.setForeground(Qt.yellow)
                        else:
                            item.setForeground(Qt.green)
                    # Δ% color: green if positive, red if negative
                    if col == 6:
                        if delta_pct > 0:
                            item.setForeground(Qt.green)
                        elif delta_pct < 0:
                            item.setForeground(Qt.red)
                    table.setItem(row, col, item)

                # Manual Fire button — operator decision #7
                fire_btn = QPushButton("Fire")
                fire_btn.setFixedHeight(24)
                fire_btn.setStyleSheet(
                    "QPushButton { background: #ff6600; color: white; "
                    "border: none; border-radius: 4px; padding: 4px 12px; "
                    "font-weight: bold; }"
                    "QPushButton:hover { background: #ff8833; }")

                def _make_fire_handler(pair_to_fire: str):
                    def _on_fire():
                        # Confirmation dialog — operator-initiated
                        # release is irreversible at the exchange.
                        confirm = QMessageBox.question(
                            self, "Manual Fire — confirm position close",
                            f"Close position on <b>{pair_to_fire}</b> "
                            f"at current market price?<br><br>"
                            f"This will fire a 100% market SELL on the "
                            f"alt units, returning base currency to the "
                            f"pool. Bypasses the auto path's "
                            f"base-unit-profitability gate per "
                            f"operator-sovereignty (v3.18.15 invariant).<br>"
                            f"<br>MEM-257 fail-closed still applies.",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.No)
                        if confirm != QMessageBox.Yes:
                            return

                        # Schedule the close on the bot manager's loop
                        loop = (getattr(self._bm, "_async_loop", None)
                                if self._bm else None)
                        if loop is None:
                            QMessageBox.warning(
                                self, "Async loop unavailable",
                                "Bot manager async loop not running. "
                                "Try again after platform launch completes.")
                            return

                        coro = self._bot.manual_fire_position(pair_to_fire)
                        try:
                            _asyncio.run_coroutine_threadsafe(coro, loop)
                        except Exception as exc:
                            QMessageBox.warning(
                                self, "Schedule failed",
                                f"Could not schedule the close:\n\n"
                                f"{type(exc).__name__}: {exc}")
                            return

                        # Non-blocking dispatch — same pattern as
                        # manual_fire_tranche (v3.16.55). The bot.log
                        # event subscription on the main window surfaces
                        # the outcome via "EXTRACTOR MANUAL FIRE COMPLETE"
                        # / refusal log lines.
                        QMessageBox.information(
                            self, "Manual Fire dispatched",
                            f"Close dispatched for <b>{pair_to_fire}</b>. "
                            f"Watch the Activity Log for the completion "
                            f"line. Re-open this dialog after the order "
                            f"settles to see updated state.")
                    return _on_fire

                fire_btn.clicked.connect(_make_fire_handler(pair))
                table.setCellWidget(row, 8, fire_btn)

            layout.addWidget(table, stretch=1)

            # --- Footer explainer ---
            footer = QLabel(
                "<b>Per-position Manual Fire</b> (operator decision #7): "
                "each button closes ITS position at current market "
                "price. Bypasses the auto path's base-unit-profitability "
                "gate per operator-sovereignty invariant (v3.18.15). "
                "MEM-257 FAIL-CLOSED still applies to any new buys the "
                "bot subsequently initiates (artillery, correction) on "
                "behalf of the pool.")
            footer.setWordWrap(True)
            footer.setStyleSheet("color: #8a8aab; padding: 8px; "
                                  "font-size: 11px;")
            layout.addWidget(footer)
            return w

        def _on_clear_fold_tranches(self) -> None:
            """Discard this bot's queued fold tranches, after confirming.

            v3.24.44 — operator directive 2026-08-06. Destructive to
            queued INTENT only: no order is placed, and holdings, cost
            basis and target balance are untouched.

            The dialog states the parked-wire-credit consequence because
            clearing opens the absorb window (it is gated on the bot
            holding zero tranches), and the absorb dumps the whole pool
            into a single tranche with no split and no cap reference. On
            a bot with several hundred dollars parked against a
            single-digit cycle cap that mints one permanently un-foldable
            tranche. The operator has to see the number before deciding.
            """
            from PySide6.QtWidgets import QMessageBox

            bot = self._bot
            tranches = list(getattr(bot, "_fold_tranches", []) or [])
            if not tranches:
                QMessageBox.information(
                    self, "Clear fold tranches",
                    "This bot has no queued fold tranches.")
                return
            if not hasattr(bot, "clear_fold_tranches"):
                QMessageBox.warning(
                    self, "Clear fold tranches",
                    "This bot type does not support clearing tranches.")
                return

            n = len(tranches)
            usd = sum(float(t.get("usd", 0) or 0) for t in tranches)
            units = sum(float(t.get("units", 0) or 0) for t in tranches)
            parked = float(getattr(bot, "_pending_wire_credits", 0.0) or 0.0)

            body = [
                f"Discard {n} queued fold tranche(s) for "
                f"{getattr(bot.config, 'symbol', '')}?",
                "",
                f"    queued USD   ${usd:,.4f}",
                f"    units        {units:.8f}",
                "",
                "This places NO order. Holdings, cost basis and target "
                "balance are unchanged — only the queued intent to buy "
                "back is discarded. The next SCRUM creates fresh "
                "tranches.",
                "",
                "This cannot be undone.",
            ]
            if parked > 1e-9:
                body += [
                    "",
                    f"WARNING — this bot also holds ${parked:,.4f} in "
                    f"pending wire credits. Clearing opens the absorb "
                    f"window, and the next SCRUM will move that entire "
                    f"amount into a SINGLE tranche. If it exceeds the "
                    f"per-cycle cap, that tranche cannot be folded.",
                ]

            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Clear fold tranches")
            box.setText("\n".join(body))
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
            box.setDefaultButton(QMessageBox.Cancel)
            if box.exec() != QMessageBox.Yes:
                return

            try:
                report = bot.clear_fold_tranches(reason="operator (GUI)")
            except Exception as exc:  # noqa: BLE001 - operator surface
                logger.exception("clear_fold_tranches failed: %s", exc)
                QMessageBox.critical(
                    self, "Clear fold tranches",
                    f"Nothing was cleared — the call failed:\n\n{exc}")
                return

            # issue #98 defects 1, 2 and 3.
            #
            # THE RESULT LEADS. The message used to open with
            # "Discarded N tranche(s)" and then say "No order was
            # placed", which is REASSURANCE standing where a RESULT
            # belongs - after a button that appeared to have done
            # nothing, beside a table that had not changed. Read in
            # that position it reads as a failure. The order is now
            # what happened, what the panel shows, whether it reached
            # disk, and only then what did NOT happen.
            #
            # EVERY LINE REPORTS THE STEP THAT ACTUALLY RAN. The panel
            # line and the save line come back from `_settle_after_clear`
            # carrying the real outcome of each, so a refresh that could
            # not run or a save that raised is named here rather than
            # papered over.
            _settled = self._settle_after_clear("Clear fold tranches")
            _now_open = len(getattr(bot, "_fold_tranches", []) or [])
            QMessageBox.information(
                self, "Clear fold tranches",
                "\n\n".join([
                    f"Cleared {report.get('count', 0)} fold tranche(s) "
                    f"holding "
                    f"${float(report.get('usd', 0)):,.4f}.",
                    f"This bot now holds {_now_open} open fold "
                    f"tranche(s).",
                    "\n".join(_settled),
                    "No order was placed. Holdings, cost basis and "
                    "target balance are unchanged — only the queued "
                    "intent to buy back is gone.",
                ]))

        def _on_clear_wire_credits(self) -> None:
            """Discard this bot's parked Smart Wire credits, after
            confirming.

            v3.24.45 — operator directive 2026-08-06. The dialog states
            that this releases an EARMARK rather than moving funds,
            because that is the fact that makes it safe and it is not
            obvious from the label: `_pending_wire_credits` has no order
            or transfer site anywhere in src/, and all bots share one
            exchange wallet, so the cash returns to spendable balance.
            """
            from PySide6.QtWidgets import QMessageBox

            bot = self._bot
            parked = float(getattr(bot, "_pending_wire_credits", 0.0) or 0.0)
            entries = len(getattr(bot, "_pending_wire_ledger", []) or [])
            if parked <= 1e-9 and not entries:
                QMessageBox.information(
                    self, "Clear wire credits",
                    "This bot has no parked wire credits.")
                return
            if not hasattr(bot, "clear_pending_wire_credits"):
                QMessageBox.warning(
                    self, "Clear wire credits",
                    "This bot type does not support clearing wire credits.")
                return

            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Clear wire credits")
            box.setText("\n".join([
                f"Discard ${parked:,.4f} of parked Smart Wire credit for "
                f"{getattr(bot.config, 'symbol', '')}?",
                "",
                f"    ledger entries   {entries}",
                "",
                "This releases an EARMARK, it does not move money. No "
                "order is placed. All bots share one exchange wallet, so "
                "the cash simply returns to ordinary spendable balance "
                "instead of being reserved for a future fold tranche.",
                "",
                "This cannot be undone.",
            ]))
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
            box.setDefaultButton(QMessageBox.Cancel)
            if box.exec() != QMessageBox.Yes:
                return

            try:
                report = bot.clear_pending_wire_credits(
                    reason="operator (GUI)")
            except Exception as exc:  # noqa: BLE001 - operator surface
                logger.exception("clear_pending_wire_credits failed: %s", exc)
                QMessageBox.critical(
                    self, "Clear wire credits",
                    f"Nothing was cleared — the call failed:\n\n{exc}")
                return

            # issue #98 defects 1, 2 and 3, on the sibling button.
            # Same three steps and the same message order as the fold
            # clear above; see the comment there for why the result
            # leads and the reassurance follows.
            _settled = self._settle_after_clear("Clear wire credits")
            _now_parked = float(
                getattr(bot, "_pending_wire_credits", 0.0) or 0.0)
            QMessageBox.information(
                self, "Clear wire credits",
                "\n\n".join([
                    f"Cleared ${float(report.get('usd', 0)):,.4f} of "
                    f"parked Smart Wire credit.",
                    f"This bot now has ${_now_parked:,.4f} parked.",
                    "\n".join(_settled),
                    "No funds moved. This released an EARMARK only, so "
                    "the cash returns to ordinary spendable balance.",
                ]))

        def _paint_fold_tranche_row(
                self, table: QTableWidget, row: int) -> None:
            """Paint one fold tranche row blue, after its cells exist.

            Operator spec 2026-08-11: the existing tranches are the
            blue ones. Before this, "blue" was only two per-cell
            foregrounds; the row background was the theme's
            alternating brush. This paints the actual row.

            Called AFTER the row's items are set, because it reads
            each item to decide whether that cell already owns a
            foreground.

            SEMANTIC FOREGROUNDS ARE NEVER OVERWRITTEN. The Status
            cell carries green for "price gate open" and amber for
            "price gate shut"; the Source cell carries `#00ccff` on a
            manual-scrum tranche -- one an operator's own Manual Fire
            SOLD into being (issue #98 defect 5 corrected the word on
            that cell; the colour and the rows carrying it are the
            same ones). Those colours are trading meaning,
            not decoration, and this is a visual change, so they are
            left exactly as they are. All three were measured against
            this fill and clear WCAG AA — 8.65:1, 5.42:1 and 6.12:1 —
            so none of them needed re-tuning either.

            Detection is by brush style rather than by a hard-coded
            column list. `QTableWidgetItem.foreground()` returns a
            NoBrush brush when nothing was set, so a cell that later
            gains a semantic colour is respected automatically instead
            of silently losing it to a stale column number here.
            """
            bg = QBrush(QColor(FOLD_TRANCHE_BG_HEX))
            fg = QBrush(QColor(FOLD_TRANCHE_FG_HEX))
            for col in range(table.columnCount()):
                cell = table.item(row, col)
                if cell is None:
                    # Column 9 holds the Fire button as a cell WIDGET
                    # and has no item. It still gets a background-only
                    # item: the widget is drawn on top of the cell, so
                    # this fills the margin around the button and, more
                    # importantly, gives the delegate a fill to read so
                    # the container edge does not stop one cell short
                    # of the row's end.
                    cell = QTableWidgetItem("")
                    table.setItem(row, col, cell)
                cell.setBackground(bg)
                if cell.foreground().style() == Qt.BrushStyle.NoBrush:
                    cell.setForeground(fg)

        def _paint_extractor_tranche_rows(
                self, table: QTableWidget, ext_rows: list[dict],
                start_row: int, now_ts: float) -> None:
            """Fill and paint the Extractor Tranche rows of the table.

            Operator spec 2026-08-11: "It will be denoted in with a red
            background and white text since existing tranches are blue."

            PER-CELL, BECAUSE THAT IS THE MECHANISM ALREADY HERE. The
            Source column sets a per-cell foreground on operator-
            initiated tranches, and the only `setBackground` precedent
            in this GUI pairs a per-cell background brush with a
            per-cell foreground brush. There is no item delegate and no
            background role anywhere in this repository, so there is no
            row-wide mechanism to reuse and no second mechanism is
            introduced here.

            Per-cell means EVERY column gets painted. Column 9 matters
            most: on a fold row it holds a widget and has no item at
            all, so leaving it out would end the red band one cell
            short and show a blue Fire button on a red row.

            The blue rows are not touched. This only ever writes rows at
            `start_row` and beyond, which is where the caller has
            already reserved space past the last fold tranche.
            """
            bg = QBrush(QColor(EXTRACTOR_TRANCHE_BG_HEX))
            fg = QBrush(QColor(EXTRACTOR_TRANCHE_FG_HEX))
            for offset, row_data in enumerate(ext_rows):
                target_row = start_row + offset
                texts = _compose_extractor_tranche_cells(row_data, now_ts)
                tip = _compose_extractor_tranche_tooltip(row_data)
                for col, text in enumerate(texts):
                    cell = QTableWidgetItem(text)
                    cell.setBackground(bg)
                    cell.setForeground(fg)
                    cell.setToolTip(tip)
                    table.setItem(target_row, col, cell)

                # Item 5 — the Arbiter cell, at column 10.
                #
                # NOT FROM THE CELL COMPOSER, AND THE SPLIT IS
                # DELIBERATE. `_compose_extractor_tranche_cells` is a
                # pure text formatter and its ten strings are pinned by
                # a test that counts them. This cell is not a piece of
                # text: it is a CONTROL that has to carry the tranche's
                # identity to a click handler, which a list of strings
                # cannot do. Growing that composer to eleven would have
                # changed a settled contract to smuggle in something
                # that is not its kind of thing, and the button would
                # still have had to be built here.
                #
                # THE ITEM AND THE BUTTON ARE BOTH REAL. The item
                # carries the same word the button shows, so the model
                # states the stored value and a reader is not forced to
                # interrogate a widget; and the row's red band reaches
                # the end of the table instead of stopping one cell
                # short — the exact defect the Fire column caused on
                # fold rows. The button is painted on top of it.
                arb_value = row_data.get("arbiter")
                arb_cell = QTableWidgetItem(_arbiter_label(arb_value))
                arb_cell.setBackground(bg)
                arb_cell.setForeground(fg)
                arb_cell.setToolTip(_compose_arbiter_tooltip(arb_value))
                table.setItem(target_row, ARBITER_COLUMN_INDEX, arb_cell)

                arb_btn = QPushButton(_arbiter_label(arb_value))
                arb_btn.setToolTip(_compose_arbiter_tooltip(arb_value))
                # Same margin mechanism as the Fire button, and for the
                # same measured reason: `setCellWidget` sizes a widget
                # to the whole cell rect and paints it over the
                # delegate, so a full-height button hides the container
                # edge at its own column and the row reads as an
                # open-ended strip. The fill matches the row so the red
                # band stays continuous; the border and text are white
                # on `#b3261e`, the pair item 4 measured at 6.54:1.
                _arb_inset = TRANCHE_FIRE_BTN_INSET_PX // 2
                arb_btn.setStyleSheet(
                    f"QPushButton {{ background: "
                    f"{EXTRACTOR_TRANCHE_BG_HEX}; color: "
                    f"{EXTRACTOR_TRANCHE_FG_HEX}; border: 1px solid "
                    f"{EXTRACTOR_TRANCHE_FG_HEX}; padding: 2px 8px; "
                    f"margin: {_arb_inset}px 0px; }} "
                    f"QPushButton:hover {{ background: "
                    f"{EXTRACTOR_TRANCHE_FG_HEX}; color: "
                    f"{EXTRACTOR_TRANCHE_BG_HEX}; }}")

                # CAPTURE IDENTITY, NEVER THE ROW INDEX — the Fire
                # button's own rule, and it matters more here. This
                # table is built once and never refreshed, while the
                # child Extractors keep ticking behind it on the same
                # thread's timers, so a position can close and another
                # open while this snapshot sits on screen. `tranche_id`
                # is `bot_id|pair|opened_at`: it does not depend on any
                # list position, and `opened_at` stops a reopened
                # position on the same pair from inheriting the row.
                # `child_bot_id` is captured too, because rows from
                # several Extractors are merged into one list and the
                # write must reach the child that owns this one.
                _arb_id = str(row_data.get("tranche_id", "") or "")
                _arb_child = str(row_data.get("child_bot_id", "") or "")
                _arb_item = arb_cell
                arb_btn.clicked.connect(
                    lambda _checked=False, tid=_arb_id, cid=_arb_child,
                    btn=arb_btn, item=_arb_item:
                        self._on_arbiter_toggle_clicked(
                            tid, cid, btn, item))
                table.setCellWidget(
                    target_row, ARBITER_COLUMN_INDEX, arb_btn)

                # NO FIRE BUTTON, DELIBERATELY. `manual_fire_tranche`
                # indexes `_fold_tranches`; a button here would dispatch
                # a real fold-back against whichever fold tranche
                # happened to occupy that index. The parent does not
                # close a child's position — the Extractor's own bullish
                # exit does, and item 1 books the return. Column 9 holds
                # a painted em dash instead, set in the loop above.

        # -- issue #98 defects 1 and 3 - the operator can SEE the clear --
        #
        # WHAT WAS WRONG. Both Clear buttons worked. The trade log
        # proves it on BTC bot `7c39c7a2`: "WIRE CREDITS CLEARED ...
        # $343.6824" and "FOLD TRANCHES CLEARED ... 42 tranche(s)".
        # What the operator SAW was a panel that had not moved. Driven
        # offscreen against a stub bot, with the confirmation accepted:
        #
        #     BEFORE  table rows 58   bot tranches 58   label "58"
        #     AFTER   table rows 58   bot tranches  0   label "58"
        #             clear button still "Clear 58 Fold Tranche(s)",
        #             still enabled, 58 Fire buttons still live
        #
        # and neither clear reached disk. Both bot methods mutate memory
        # and leave the write to the 60-second rolling save
        # (`main.py:1343`), so a clear followed by a close inside that
        # window restored every record the operator had just destroyed.
        #
        # NEITHER REPAIR TOUCHES `scrumming_bot.py`. The clear itself is
        # correct and is not changed. The refresh is this dialog's own
        # widget tree, and the save is a call the CALLER can make - the
        # precedent is Reset-all-errors, which calls `save_all_state()`
        # inside its click at `main_window.py:8259` and states the same
        # reason.
        FOLD_TRANCHES_TAB_LABEL = "Fold Tranches"

        def _install_fold_tranches_tab(self, tabs: QTabWidget) -> QWidget:
            """Build the Fold Tranches tab, add it, and remember it.

            ONE INSTALL SITE, so the handle a later refresh swaps is
            never a second bookkeeping step somebody can forget. The
            tests drive this method rather than re-implementing the two
            lines, which is what makes them a test of the shipped
            wiring.
            """
            page = self._wrap_scrollable(self._create_fold_tranches_tab())
            tabs.addTab(page, self.FOLD_TRANCHES_TAB_LABEL)
            self._fold_tab_page = page
            return page

        def _refresh_fold_tranches_tab(self) -> str:
            """Rebuild the Fold Tranches tab in place. Return a status.

            Returns "refreshed", or a sentence naming why it did not.
            THE STRING IS LOAD-BEARING: the message the operator reads
            after a clear quotes it, so a rebuild that could not run
            says so instead of the panel quietly lying twice.

            THE TAB IS FOUND BY WIDGET IDENTITY, NOT BY A STORED INDEX.
            `indexOf` asks the tab bar where the page actually is, so a
            tab added, hidden or reordered anywhere else in this dialog
            cannot make the refresh rebuild somebody else's tab. A
            stored integer could.

            `removeTab` + `insertTab` AT THE SAME INDEX, so no other tab
            renumbers and the operator keeps their place in the dialog.
            `removeTab` does not delete the page - it reparents it to
            nothing - so the old page is deleted here explicitly.
            Without that, every clear would leak a whole tab's widget
            tree for the life of the dialog.

            THE DELEGATE SURVIVES BECAUSE THE BUILDER REBINDS IT.
            `setItemDelegate` does not take ownership, so the table's
            delegate is held on `self`; the rebuild overwrites that
            attribute with the new table's delegate, and the old one
            goes with the old page.
            """
            tabs = getattr(self, "_tabs", None)
            page = getattr(self, "_fold_tab_page", None)
            if tabs is None or page is None:
                return ("not refreshed: this dialog has no Fold "
                        "Tranches tab installed")
            try:
                index = tabs.indexOf(page)
            except Exception as exc:  # R28-OK: display-only rebuild
                logger.warning(
                    "Fold Tranches refresh could not locate its tab "
                    "(%s: %s)", type(exc).__name__, exc)
                return (f"not refreshed: the tab could not be located "
                        f"({type(exc).__name__})")
            if index < 0:
                return ("not refreshed: the Fold Tranches tab is no "
                        "longer in this dialog")
            label = tabs.tabText(index)
            was_current = tabs.currentIndex() == index
            try:
                fresh = self._wrap_scrollable(
                    self._create_fold_tranches_tab())
            except Exception as exc:  # R28-OK: display-only rebuild
                logger.exception(
                    "Fold Tranches refresh raised while rebuilding "
                    "the tab")
                return (f"not refreshed: rebuilding the tab raised "
                        f"{type(exc).__name__}: {exc}")
            tabs.removeTab(index)
            tabs.insertTab(index, fresh, label)
            self._fold_tab_page = fresh
            if was_current:
                tabs.setCurrentIndex(index)
            page.setParent(None)
            page.deleteLater()
            return "refreshed"

        def _fold_panel_shows(self) -> dict:
            """Report what the Fold Tranches tab shows RIGHT NOW.

            Read off the widgets, never off the bot. That is the whole
            value of it: the pin below compares this dict against the
            bot's own numbers, and two reads of one expression would
            agree whatever the panel displayed.

            `fold_rows` subtracts the Extractor rows. Those are appended
            after every fold tranche and are a child's lease, not this
            bot's inventory.
            """
            table = getattr(self, "_fold_tranche_table", None)
            lbl = getattr(self, "_fold_open_count_lbl", None)
            btn = getattr(self, "_fold_clear_btn", None)
            wire = getattr(self, "_fold_wire_btn", None)
            timer = getattr(self, "_fold_despawn_timer_lbl", None)
            preview = getattr(self, "_fold_despawn_preview_lbl", None)
            # issue #98 defects 7 and 9 - the three surfaces this unit
            # added, reported the same way as the six above: read off
            # the WIDGET, never off the bot or off a stored key. The
            # order is asked of the combo box rather than of
            # `fold_sort_order`, because a reporter that read the state
            # both controls are supposed to reflect would agree with
            # itself whatever the panel displayed.
            units = getattr(self, "_fold_units_marked_lbl", None)
            sort_box = getattr(self, "_fold_sort_combo", None)
            filter_box = getattr(self, "_fold_filter_edit", None)
            rows = None
            if table is not None:
                rows = max(
                    0,
                    table.rowCount()
                    - int(getattr(self, "_fold_ext_row_count", 0) or 0))
            elif lbl is not None:
                # No table means the builder took its empty-queue
                # branch, which renders the "fold queue is empty" note
                # and no rows at all. That is zero rows, not "unknown".
                rows = 0
            return {
                "fold_rows": rows,
                "open_tranches_label": (
                    lbl.text() if lbl is not None else None),
                "clear_button_text": (
                    btn.text() if btn is not None else None),
                "clear_button_enabled": (
                    bool(btn.isEnabled()) if btn is not None else None),
                "wire_button_enabled": (
                    bool(wire.isEnabled()) if wire is not None else None),
                "despawn_timer_text": (
                    timer.text() if timer is not None else None),
                "despawn_preview_text": (
                    preview.text() if preview is not None else None),
                "units_marked_text": (
                    units.text() if units is not None else None),
                "row_order": (
                    sort_box.currentText()
                    if sort_box is not None else None),
                "row_filter": (
                    filter_box.text() if filter_box is not None else None),
            }

        def _bot_manager_for_save(self) -> object | None:
            """Return the object that owns `save_all_state`, or None.

            `self._bm` FIRST, THEN THE BOT'S OWN MANAGER. The Simulator
            builds this dialog with no manager, and so do the listing
            tests, so `self._bm` is None on those paths; the parent
            bot's `_bot_manager` is the object that produced these rows
            in the first place. The Arbiter handler resolves its manager
            the same way and for the same reason.
            """
            for candidate in (getattr(self, "_bm", None),
                              getattr(self._bot, "_bot_manager", None)):
                if callable(getattr(candidate, "save_all_state", None)):
                    return candidate
            return None

        def _save_fleet_state_now(self, what: str) -> tuple[bool, str]:
            """Persist the fleet in this click. Return (saved, reason).

            issue #98 defect 3. `clear_fold_tranches` and
            `clear_pending_wire_credits` both write memory only
            (`scrumming_bot.py:13273` and `:13350`) and rely on the
            60-second rolling save. Clear, then close inside that
            window, and everything the operator destroyed comes back.

            WHY THIS SAVES WHERE THE ARBITER TOGGLE DELIBERATELY DOES
            NOT. That toggle's comment is right about the cost: a fleet
            serialise plus a backup copy on the GUI thread is the freeze
            class. It is also right about the risk it weighed - a
            TOGGLE lost to a crash is set again in one click. A CLEAR
            lost to a crash RESTORES records the operator deliberately
            destroyed, and no second click can un-restore them. The two
            are not the same trade, so they do not get the same answer.
            The cost is stated rather than hidden: this call blocks the
            GUI thread for as long as the fleet takes to serialise, and
            the pin beside it carries that duration, so the cost is
            measured on the operator's own machine instead of argued
            about here.

            THE FAILURE IS REPORTED, NEVER SWALLOWED. A clear that ran
            in memory and did not reach disk is exactly the gap the
            operator relies on this button to close, so the reason comes
            back as text and goes into the message they read.
            """
            manager = self._bot_manager_for_save()
            saver = getattr(manager, "save_all_state", None)
            if not callable(saver):
                return (False, "no bot manager is attached to this panel")
            try:
                saver()
            except Exception as exc:  # noqa: BLE001 - operator surface
                logger.warning(
                    "%s: cleared in memory but NOT saved (%s: %s); a "
                    "restart before the next rolling save will restore "
                    "it.", what, type(exc).__name__, exc)
                return (False, f"{type(exc).__name__}: {exc}")
            return (True, "")

        def _settle_after_clear(self, what: str) -> list[str]:
            """Save, rebuild the tab, pin the result, report the lines.

            ONE PATH FOR BOTH CLEAR BUTTONS. They discard different
            things and their confirmations differ, but what has to
            happen AFTER an accepted clear is the same three steps, and
            two copies of them would drift the first time either moved.

            THE ORDER IS SAVE, THEN REFRESH. The durable write is the
            one a crash can take away; the rebuild only reads memory
            that is already correct. Saving first means a crash between
            the two costs a stale panel, not a restored tranche.
            """
            import contextlib
            import time as _clock

            _t0 = _clock.monotonic()
            saved, why = self._save_fleet_state_now(what)
            refresh = self._refresh_fold_tranches_tab()
            _elapsed = _clock.monotonic() - _t0

            shows = self._fold_panel_shows()
            _open = len(getattr(self._bot, "_fold_tranches", []) or [])
            _parked = float(
                getattr(self._bot, "_pending_wire_credits", 0.0) or 0.0)
            with contextlib.suppress(Exception):
                from src.core.signal_contract import emit as _fold_emit
                _fold_emit(
                    "gui.04.002.postcondition.clear_settled",
                    actual={
                        "fold_rows": shows["fold_rows"],
                        "open_tranches_label": shows["open_tranches_label"],
                        "clear_button_enabled": shows[
                            "clear_button_enabled"],
                        "wire_button_enabled": shows["wire_button_enabled"],
                        "saved": saved,
                    },
                    expected={
                        "fold_rows": _open,
                        "open_tranches_label": str(_open),
                        "clear_button_enabled": bool(_open),
                        "wire_button_enabled": _parked > 1e-9,
                        "saved": True,
                    },
                    duration=_elapsed,
                    context={
                        "bot_id": getattr(self._bot, "bot_id", "?"),
                        "cleared": what,
                        "refresh": refresh,
                        "save_reason": why,
                        "clear_button_text": shows["clear_button_text"],
                    })

            lines = []
            if refresh == "refreshed":
                lines.append(
                    "The panel behind this message has been rebuilt "
                    "and now shows the new state.")
            else:
                lines.append(
                    f"The panel was {refresh}. Close and reopen this "
                    f"dialog to see the new state.")
            if saved:
                lines.append("Saved to disk.")
            else:
                lines.append(
                    f"NOT SAVED TO DISK - {why}. The change holds in "
                    f"memory, and the platform's rolling save should "
                    f"write it within 60 seconds; a restart before "
                    f"that would bring it back.")
            return lines

        def _create_fold_tranches_tab(self) -> QWidget:
            import time as _time

            # The repo's ONE admission rule, imported the way this
            # module imports every other trading symbol: locally,
            # so building a tab never drags the trading package in
            # at module import time. The Stack Tranches tab reads
            # its own ledger through this same helper.
            from ..trading.bot_container import (
                as_finite_float as _as_finite_float,
            )
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.setSpacing(8)

            # issue #98 defect 1 — THE READ-BACK HANDLES, CLEARED FIRST.
            # `_refresh_fold_tranches_tab` rebuilds this whole widget
            # and then asks the REBUILT surface what it shows, so the
            # pin compares the panel against the bot rather than
            # comparing a local variable to itself. Cleared here rather
            # than only assigned below, because a rebuild that takes the
            # empty-queue branch builds no table at all and a stale
            # handle from the previous build would answer for it.
            self._fold_tranche_table = None
            self._fold_open_count_lbl = None
            self._fold_clear_btn = None
            self._fold_wire_btn = None
            self._fold_ext_row_count = 0
            # The two despawn rows, cleared here for the same reason as
            # the four handles above: a rebuild that raised before the
            # rows were built would otherwise leave the previous
            # build's labels answering for the new panel.
            self._fold_despawn_timer_lbl = None
            self._fold_despawn_preview_lbl = None
            # issue #98 defects 7 and 9 - same reason again. The
            # allotment label, the two reach controls and the filter's
            # source text are all rebuilt below, and a stale handle
            # from the previous build would answer for the new panel.
            self._fold_units_marked_lbl: QLabel | None = None
            self._fold_sort_combo: QComboBox | None = None
            self._fold_filter_edit: QLineEdit | None = None
            self._fold_row_texts: list[list[str]] = []

            tranches = list(getattr(self._bot, "_fold_tranches", []) or [])
            # Item 4 (2026-08-11) — Extractor Tranches leased against
            # this bot's asset, read from the child that owns them.
            # A COMPUTED VIEW, kept deliberately separate from
            # `tranches` above: these are NOT in `_fold_tranches` and
            # must never be merged into it, because that list is read by
            # the fold gate, the fold buy set, the per-cycle cap packing
            # loop and the manual-fire index. They are rendered in the
            # same table and nowhere else.
            ext_rows: list[dict] = []
            try:
                _reader = getattr(
                    self._bot, "open_extractor_tranches", None)
                if callable(_reader):
                    _raw = _reader()
                    if isinstance(_raw, list):
                        ext_rows = [
                            r for r in _raw if isinstance(r, dict)]
            except Exception as _ext_exc:  # R28-OK: display-only listing
                logger.warning(
                    "Extractor Tranche listing failed for bot %s: %s: "
                    "%s — fold tranches still shown.",
                    getattr(self._bot, "bot_id", "?"),
                    type(_ext_exc).__name__, _ext_exc)
                ext_rows = []
            now_ts = _time.time()
            created_lifetime = int(getattr(
                self._bot, "_tranches_created_lifetime", 0) or 0)
            closed_lifetime = int(getattr(
                self._bot, "_tranches_closed_lifetime", 0) or 0)

            # --- Summary section ---
            summary = QGroupBox("Fold-Tranche Cycle Health")
            sf = QFormLayout(summary)
            self._configure_form(sf)

            open_count = len(tranches)

            # A REFUSED CONTRIBUTOR IS COUNTED, NOT DROPPED.
            # Silently skipping an unreadable tranche reports a
            # parked total LOWER than the truth with nothing on
            # the panel saying so, which is the shape of the
            # claim-total defect of 2026-08-10: $2,000 reported
            # against a true $3,000, with zero log lines. The
            # count rides beside the number instead.
            #
            # ONE BAD ENTRY USED TO POISON THE WHOLE TOTAL. This
            # was a `sum`, so a single `nan` or `inf` took the
            # parked figure to "$nan"/"$inf", and an int above
            # the float maximum raised OverflowError out of the
            # sum itself, with no `try` on the path to the click.
            #
            # `or 0` IS GONE. It mapped None, "" and False onto
            # the int 0 before any guard could see them, so an
            # ABSENCE was priced at a confident $0.0000.
            # `t.get("usd", 0)` still defaults an ABSENT key to
            # 0, which is what it rendered before and still
            # renders.
            parked_usd = 0.0
            parked_unreadable = 0
            for _pt in tranches:
                _pt_usd = _as_finite_float(_pt.get("usd", 0))
                if _pt_usd is None:
                    parked_unreadable += 1
                else:
                    parked_usd += _pt_usd

            # Oldest tranche age — handle missing created_ts
            # (pre-v3.16.39 tranches) by skipping them in the
            # max() and reporting "—".
            #
            # A TYPE IS NOT A DOMAIN, AND THIS GUARD WAS THE
            # EXAMPLE THAT PROVED IT. Exact type closed the TYPE
            # and stopped `True` being arithmetic'd as 1.0, which
            # dated a tranche to the epoch and reported an age of
            # about 56 years. It did NOT close the VALUE:
            # `type(inf) is float` is True and `inf > 0` is True,
            # so `inf` was admitted, and `int(seconds)` inside
            # `_format_age` then raised OverflowError. An int
            # above the float maximum was admitted the same way
            # and raised from `float()`. Neither site sits inside
            # a `try`, so the Bot Settings dialog would not open.
            #
            # `as_finite_float` closes both. It bounds huge ints
            # with an INTEGER comparison rather than
            # `math.isfinite`, which raises on the very input it
            # would be added to reject.
            ages_sec = []
            for t in tranches:
                cts = _as_finite_float(t.get("created_ts"))
                if cts is not None and cts > 0:
                    ages_sec.append(now_ts - cts)
            if ages_sec:
                oldest = max(ages_sec)
                oldest_str = self._format_age(oldest)
            elif tranches:
                oldest_str = "— (pre-v3.16.39 tranches, no timestamp)"
            else:
                oldest_str = "no open tranches"

            # Cycle close ratio — informative only, may exceed 1.0 if
            # multiple lots fold-back faster than scrums create them.
            if created_lifetime > 0:
                ratio = closed_lifetime / created_lifetime
                ratio_str = f"{ratio:.2%}  ({closed_lifetime}/{created_lifetime})"
            else:
                ratio_str = "—  (no scrums yet)"

            # issue #98 defect 6 - every row this unit owns now carries
            # the operator's own tooltip standard, on BOTH the words and
            # the number. `install_health_row` is the one call that puts
            # it on both; a tooltip on the value alone leaves the label
            # the operator points at bare.
            open_count_lbl = QLabel(str(open_count))
            self._fold_open_count_lbl = open_count_lbl
            install_health_row(sf, "Open tranches:", open_count_lbl,
                               FOLD_OPEN_COUNT_TOOLTIP)

            parked_str = f"${parked_usd:,.4f}"
            if parked_unreadable:
                parked_str += f"  (+{parked_unreadable} unreadable)"
            parked_lbl = QLabel(parked_str)
            parked_lbl.setStyleSheet("font-weight: bold; font-size: 13px; "
                                     "color: #ff9900;")
            install_health_row(sf, "Parked USD (in fold queue):",
                               parked_lbl, FOLD_PARKED_USD_TOOLTIP)

            install_health_row(sf, "Oldest tranche age:",
                               QLabel(oldest_str), FOLD_OLDEST_AGE_TOOLTIP)

            # issue #98 defect 9 - THE ALLOTMENT TOTAL. The panel
            # printed per-row Units and nothing else, so a queue that
            # had marked 1.99x the units the bot holds (PUMP/USD,
            # 2026-08-23) looked exactly like one that had marked half.
            # Both quantities are stored: the sum of tranche `units`,
            # and `_current_holdings` on the bot. The row states them
            # and their ratio, and attributes nothing.
            _units_text, _units_colour = compose_units_marked_row(
                tranches, getattr(self._bot, "_current_holdings", None))
            _units_lbl = QLabel(_units_text)
            if _units_colour:
                # The same red the close-ratio verdict on this form and
                # the over-cap row on the Settings tab already use.
                _units_lbl.setStyleSheet(f"color: {_units_colour};")
            self._fold_units_marked_lbl = _units_lbl
            install_health_row(sf, "Units marked (queue vs held):",
                               _units_lbl, FOLD_UNITS_MARKED_TOOLTIP)

            # issue #103 - the despawn window is usable. The count is
            # already on this tab; the control that acts on it was two
            # tabs away with nothing naming it. These two rows name the
            # setting and print what it would remove BEFORE it is
            # armed. They add no button: despawn is the age-driven
            # removal, clear is the manual one, and the operator's
            # model has exactly three verbs.
            install_despawn_rows(self, sf, tranches, now_ts)

            sf.addRow("Lifetime tranches opened:", QLabel(str(created_lifetime)))
            sf.addRow("Lifetime tranches closed (fold-back fired):",
                      QLabel(str(closed_lifetime)))

            ratio_lbl = QLabel(ratio_str)
            # Healthy = closed/created near 1.0 over time. Stagnation
            # warning when ratio is low AND there are open tranches.
            if created_lifetime >= 5 and open_count > 0:
                ratio_val = closed_lifetime / created_lifetime
                if ratio_val < 0.5:
                    ratio_lbl.setStyleSheet("color: #ff3366;")
                elif ratio_val < 0.8:
                    ratio_lbl.setStyleSheet("color: #ff9900;")
                else:
                    ratio_lbl.setStyleSheet("color: #00ff88;")
            sf.addRow("Cycle close ratio (closed/opened):", ratio_lbl)

            # v3.24.44 — discarded tranches are counted separately from
            # closed ones, because a discard did NOT fold. Shown only
            # once non-zero so the panel stays quiet on bots that have
            # never been cleared.
            discarded_lifetime = int(getattr(
                self._bot, "_tranches_discarded_lifetime", 0) or 0)
            if discarded_lifetime:
                sf.addRow("Lifetime tranches discarded (cleared, not folded):",
                          QLabel(str(discarded_lifetime)))

            # -- issue #98 defect 10 - three persisted quantities the
            # panel never showed ------------------------------------
            #
            # All three are written to the state file and read back on
            # restore, and none of them had a row on the surface that
            # owns them.
            #
            # 1. `_wire_credits_discarded_lifetime`. The Clear Wire
            #    Credits button on THIS tab writes it, and the tranche
            #    clear's own lifetime row sits four lines above. The
            #    two buttons were not symmetric in what they reported:
            #    BTC carried $343.68 and ETH $213.90 with nothing on
            #    screen saying so. It follows the tranche row's
            #    convention exactly - shown once it is non-zero, so a
            #    bot that has never cleared stays quiet.
            #
            # 2. `_tranches_malformed_dropped`. ALWAYS SHOWN, and that
            #    departs from the convention above on purpose. A zero
            #    here is a positive statement - no stored tranche was
            #    ever unreadable - and hiding it makes "none were
            #    dropped" indistinguishable from "this panel does not
            #    count drops". It was 0 on all 38 bots when the panel
            #    was evaluated, which is exactly the reading a hidden
            #    row would have thrown away.
            #
            # 3. `_fold_cycle_cap_consumed`, beside the budget it is
            #    spent from. It decides how much of this queue one
            #    cycle may take, so consumed alone is half a number:
            #    the Settings tab already prints the pair, and this row
            #    reads those same two fields rather than a second
            #    arithmetic of its own.
            _wire_discarded = _as_finite_float(getattr(
                self._bot, "_wire_credits_discarded_lifetime", 0.0))
            if _wire_discarded is not None and _wire_discarded > 1e-9:
                install_health_row(
                    sf, "Lifetime wire credits discarded (cleared):",
                    QLabel(f"${_wire_discarded:,.4f}"),
                    FOLD_WIRE_DISCARDED_TOOLTIP)

            _malformed = int(getattr(
                self._bot, "_tranches_malformed_dropped", 0) or 0)
            _malformed_lbl = QLabel(str(_malformed))
            if _malformed:
                # Same red the close-ratio verdict uses on this form. A
                # dropped tranche is a record the bot could not read,
                # which is a data fault rather than a trading outcome.
                _malformed_lbl.setStyleSheet(
                    f"color: {FOLD_OVER_ALLOTMENT_FG_HEX};")
            install_health_row(sf, "Tranches dropped as malformed:",
                               _malformed_lbl, FOLD_MALFORMED_TOOLTIP)

            _cap_budget = _as_finite_float(getattr(
                self._bot, "cycle_growth_cap_usd", 0.0))
            _cap_consumed = _as_finite_float(getattr(
                self._bot, "_fold_cycle_cap_consumed", 0.0))
            _cap_text = (
                f"${_cap_consumed:,.4f} spent of ${_cap_budget:,.4f}"
                if _cap_budget is not None and _cap_consumed is not None
                else "- (unreadable)")
            install_health_row(sf, "Fold budget this cycle:",
                               QLabel(_cap_text), FOLD_CYCLE_CAP_TOOLTIP)

            layout.addWidget(summary)

            # --- Clear tranches (operator directive 2026-08-06) ---
            # "let's just clear the existing tranche values and assume
            # them as invalid. They were calculated without any outgoing
            # safety rate math, have languished for weeks in some cases,
            # and just need to be produced fresh."
            clear_btn = QPushButton(
                f"Clear {open_count} Fold Tranche(s)" if open_count
                else "Clear Fold Tranches")
            clear_btn.setEnabled(bool(open_count))
            clear_btn.setToolTip(
                "Discard every queued fold tranche for this bot.\n\n"
                "Places NO order. Holdings, cost basis and target balance "
                "are untouched — only the queued intent to buy back is "
                "discarded. New tranches are created by the next SCRUM.")
            clear_btn.setStyleSheet(
                "QPushButton { background: #3a2020; color: #ff9900; "
                "border: 1px solid #ff3366; padding: 6px 12px; } "
                "QPushButton:disabled { color: #666666; "
                "border-color: #444444; }")
            clear_btn.clicked.connect(self._on_clear_fold_tranches)
            self._fold_clear_btn = clear_btn

            # v3.24.45 — operator directive 2026-08-06: "Languishing wire
            # credits can also be cleared. These too were not calculated
            # using outgoing safety rate math." Parked credit is x% of
            # GROSS scrum proceeds, so it is derived off principal rather
            # than profit; the figure is not meaningful to preserve.
            #
            # Deliberately a SEPARATE button, not folded into the tranche
            # clear: they are independent decisions, and a bot can want
            # one without the other.
            parked = float(getattr(self._bot, "_pending_wire_credits", 0.0)
                           or 0.0)
            wire_btn = QPushButton(
                f"Clear ${parked:,.2f} Wire Credits" if parked > 1e-9
                else "Clear Wire Credits")
            wire_btn.setEnabled(parked > 1e-9)
            wire_btn.setToolTip(
                "Discard this bot's parked Smart Wire credits.\n\n"
                "Releases an EARMARK only. No order is placed and no "
                "funds move — all bots share one exchange wallet, so the "
                "cash simply returns to ordinary spendable balance.")
            wire_btn.setStyleSheet(
                "QPushButton { background: #3a2020; color: #ff9900; "
                "border: 1px solid #ff3366; padding: 6px 12px; } "
                "QPushButton:disabled { color: #666666; "
                "border-color: #444444; }")
            wire_btn.clicked.connect(self._on_clear_wire_credits)
            self._fold_wire_btn = wire_btn

            btn_row = QHBoxLayout()
            btn_row.addWidget(clear_btn)
            btn_row.addWidget(wire_btn)
            btn_row.addStretch()
            layout.addLayout(btn_row)

            # v3.23.34 — retired the "How this works" prose explainer
            # per operator directive 2026-07-26 ("remove the
            # hallucinatory descriptive text inside of the window").
            # Column headers + per-column tooltips are the authoritative
            # per-tranche documentation; the meta-prose drifted out of
            # sync with runtime.

            # --- Per-tranche detail table ---
            if tranches or ext_rows:
                # The two counts are named separately and never added
                # together. A fold tranche is this bot's own parked
                # intent to buy back; an Extractor Tranche is a child's
                # lease on this bot's asset. One number covering both
                # would invite reading a lease as fold inventory, which
                # is the exact confusion item 4 has to avoid.
                if ext_rows:
                    _detail_title = (
                        f"Open Tranches ({open_count} fold, "
                        f"{len(ext_rows)} extractor)")
                else:
                    _detail_title = f"Open Tranches ({open_count})"
                detail_group = QGroupBox(_detail_title)
                dl = QVBoxLayout(detail_group)

                # v3.16.43 — Column labels updated for architectural
                # redesign. Per-tranche initial_buy_price is no longer
                # the binding fold-back gate (compound governance shifted
                # to position-level smart ceiling). Renamed
                # "Patent ceiling $" → "Original cost $" to reflect its
                # now-informational role. The OTD threshold ("Min rebuy")
                # IS the binding per-tranche price gate.
                #
                # v3.26.0 (issue #97) — THE PANEL ASKS THE CODE THAT
                # DECIDES. This read was
                #     float(getattr(cfg, 'scrumming_interval_pct', 0) or 0)
                # — the scrumming interval ALONE. The executor's
                # per-tranche fold filter (`scrumming_bot.py:9857`) uses
                # the Minimum Opposing Trade Distance, which is
                # interval + TRADING FEE, defined in `otd_math`.
                #
                # MEASURED ON THE LIVE FLEET, 2026-08-23, not argued: 24
                # of 38 bots run a 1.6% fee, so the "Min rebuy $" column
                # printed a price 1.71% ABOVE the gate the executor
                # applies. Over the 1,707 open fold tranches at their
                # stored price the panel showed Price-OK on 17 where the
                # executor accepts 11. Six green rows for a buy the
                # executor refuses, all on ALLO/USDC.
                #
                # ADDING A FEE TERM TO THE ARITHMETIC HERE WOULD BE THE
                # SAME DEFECT AGAIN. Two implementations that agree
                # today drift the next time either one moves, which is
                # exactly how this one was born: the fee entered the
                # executor in v3.25.8 and this surface never heard about
                # it. The call below is the call `scrumming_bot` makes,
                # the config read included, so nothing is left here to
                # drift. `_otd_factor` is bound ONCE and both consumers
                # below read it — the Min rebuy cell and the Status
                # verdict must never be able to disagree.
                #
                # Imported locally, matching the executor's own pattern
                # and keeping this GUI module importable without
                # `src.trading`.
                _otd_pct = 0.0
                _otd_factor = 1.0
                try:
                    from ..trading.otd_math import (
                        fold_rebuy_factor_from_pct,
                        minimum_opposing_trade_distance_pct_from_config,
                    )
                    _otd_pct = (
                        minimum_opposing_trade_distance_pct_from_config(
                            self._bot.config))
                    _otd_factor = fold_rebuy_factor_from_pct(_otd_pct)
                except Exception:  # R28-OK: best-effort config read
                    _otd_pct = 0.0
                    _otd_factor = 1.0

                table = QTableWidget()
                # v3.16.53 — added "Fire" column for per-tranche
                # operator-initiated fold-back (column 9).
                #
                # Item 5 (2026-08-10) — "Arbiter" APPENDED at column
                # 10, after Fire. See ARBITER_COLUMN_INDEX for why the
                # position is load-bearing rather than cosmetic.
                table.setColumnCount(ARBITER_COLUMN_INDEX + 1)
                table.setHorizontalHeaderLabels([
                    "#", "Age", "Units", "USD parked",
                    "Sell ref $", "Original cost $", "Min rebuy $",
                    "Status", "Source", "Fire", ARBITER_COLUMN_HEADER])

                # issue #98 defect 6 - THE AUTHORITY THE COMMENT NAMED
                # NOW EXISTS. Zero of the eleven headers carried a
                # tooltip while the comment below this table said header
                # tooltips were the authoritative per-column
                # documentation. `setHorizontalHeaderLabels` creates one
                # item per column, so each is asked for by index rather
                # than built a second time here.
                for _col, _tip in enumerate(FOLD_COLUMN_TOOLTIPS):
                    _head = table.horizontalHeaderItem(_col)
                    if _head is not None:
                        _head.setToolTip(_tip)

                table.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeToContents)
                # Extractor Tranche rows are appended AFTER every fold
                # tranche, never interleaved. This is load-bearing: the
                # Fire button resolves its target with
                # `tranches.index(tranche)` against `_fold_tranches`, so
                # fold row number must stay equal to fold list index. An
                # Extractor Tranche placed among them would shift that
                # mapping and fire an unrelated tranche.
                table.setRowCount(len(tranches) + len(ext_rows))
                # issue #98 defect 7 - the cap was a flat 280px over
                # 30px rows, so about EIGHT of up to 230 rows were on
                # screen. The height now follows the row count up to
                # `TRANCHE_TABLE_VISIBLE_ROWS`, and the header is
                # MEASURED rather than assumed: `ResizeToContents` below
                # sizes it to its own labels, so a hard-coded header
                # height would clip the last row on any theme with a
                # different font.
                table.setMaximumHeight(fold_table_max_height_px(
                    len(tranches) + len(ext_rows),
                    table.horizontalHeader().sizeHint().height()))
                table.setAlternatingRowColors(True)
                table.setEditTriggers(QTableWidget.NoEditTriggers)

                # Operator spec 2026-08-11 — "stronger borders so they
                # appear like proper containers". The delegate is
                # scoped to THIS table; the QSS in `theme_engine.py`
                # is one shared `QTableWidget, QTableView` block used
                # by twenty-odd tables across the app, so the border
                # work must never go there.
                #
                # Kept on `self` because `setItemDelegate` does NOT
                # take ownership. A delegate held only by this local
                # frame would be garbage-collected when the tab
                # finished building, and Qt would paint through a
                # dangling pointer.
                self._tranche_row_delegate = _TrancheRowBorderDelegate(
                    table)
                table.setItemDelegate(self._tranche_row_delegate)

                # `setAlternatingRowColors` above stays ON deliberately.
                # An explicit item background beats the alternating
                # brush, so once every row is painted the alternating
                # colour has no visible surface left in the populated
                # area. Turning it off would change nothing and would
                # be an edit for its own sake.

                # Vertical mass — a fill only reads as a container when
                # the band has height.
                table.verticalHeader().setDefaultSectionSize(
                    TRANCHE_ROW_HEIGHT_PX)

                # Qt's default grid draws BOTH axes at the same weight,
                # so a row boundary looked exactly like a column
                # boundary and each row read as ten separate cells
                # rather than one container. The delegate above now
                # draws the horizontal edges, so the grid is no longer
                # carrying any row separation and only the vertical
                # segmentation is left to remove.
                #
                # Safe ONLY because the delegate exists. Measured
                # without it, two adjacent painted rows butt together
                # with no separator at all and merge into one slab.
                table.setShowGrid(False)

                # Try to fetch current price for status determination.
                # Falls back to "—" if unavailable.
                cur_price = 0.0
                try:
                    stats = self._bot.get_status().get("stats", {})
                    cur_price = float(stats.get("current_price", 0) or 0)
                except Exception:  # R28-OK: best-effort price fetch for display only
                    cur_price = 0.0

                # issue #98 defect 7 - the operator chooses the order,
                # and the QUEUE INDEX travels with the row rather than
                # being re-derived from the visual position. `row` is
                # where the row is drawn; `queue_index` is where the
                # tranche sits in `_fold_tranches`. Only the second one
                # is printed, and only the second one is quoted back by
                # the Fire confirmation.
                _ordered = fold_display_order(
                    tranches, fold_sort_order(self))
                for row, (queue_index, t) in enumerate(_ordered):
                    table.setItem(
                        row, 0, QTableWidgetItem(str(queue_index + 1)))

                    # THE SAME ADMISSION AS THE SUMMARY ROW ABOVE,
                    # and it has to stay the same one. Both render
                    # the age of the SAME tranche from the SAME
                    # key, so closing one without the other gives
                    # a panel that contradicts itself, which is
                    # worse than the defect. Every refused shape
                    # prints the "—" this column already used for
                    # a tranche with no created_ts.
                    cts = _as_finite_float(t.get("created_ts"))
                    if cts is not None and cts > 0:
                        age_str = self._format_age(now_ts - cts)
                    else:
                        age_str = "—"
                    table.setItem(row, 1, QTableWidgetItem(age_str))

                    # THE FOUR MONEY CELLS — four sibling keys off
                    # the same dict the age above came from, read
                    # with no guard at all. Measured on live
                    # before this: `True` priced a stored flag at
                    # one dollar and `False` at zero; None and ""
                    # priced an ABSENCE at zero; `nan` and `inf`
                    # printed "$nan" and "$inf"; an int above the
                    # float maximum raised OverflowError out of
                    # the row builder, and a list or a dict raised
                    # TypeError. None of the four sits inside a
                    # `try` — the chain runs to
                    # `BotLiveSettingsDialog.__init__` and on to
                    # `MainWindow._on_bot_clicked` with no handler
                    # at any step — so a raise means Bot Settings
                    # does not open for that bot at all.
                    #
                    # A REFUSED MONEY VALUE MUST NOT RENDER AS
                    # ZERO. That would be a new defect rather than
                    # a fix: the operator would read a real dollar
                    # figure where there is none. The em dash is
                    # what the Age cell beside it already prints
                    # when it cannot read its key, and what an
                    # Extractor row already prints in these same
                    # price columns.
                    units = _as_finite_float(t.get("units", 0))
                    table.setItem(row, 2, QTableWidgetItem(
                        f"{units:.6f}" if units is not None
                        else "—"))

                    usd_v = _as_finite_float(t.get("usd", 0))
                    table.setItem(row, 3, QTableWidgetItem(
                        f"${usd_v:,.4f}" if usd_v is not None
                        else "—"))

                    # `ref_v` is read by three cells, not one: the
                    # Min-rebuy column and the Status column below
                    # both derive from it. A refused ref therefore
                    # takes the SAME no-ref branch those two
                    # already had for a ref of 0 or an absent key,
                    # which is why every `ref_v > 0` test below
                    # now asks `is not None` first.
                    ref_v = _as_finite_float(t.get("ref", 0))
                    table.setItem(row, 4, QTableWidgetItem(
                        f"${ref_v:.8f}" if ref_v is not None
                        else "—"))

                    ceiling_v = _as_finite_float(
                        t.get("initial_buy_price", 0))
                    table.setItem(row, 5, QTableWidgetItem(
                        f"${ceiling_v:.8f}" if ceiling_v is not None
                        else "—"))

                    # v3.16.42 — Min rebuy estimate (operator directive).
                    # OTD-derived guide ONLY — actual fold-back
                    # additionally requires TA validation in the GEP
                    # (Gating Evaluation Protocol). This column does NOT
                    # bypass TA; it shows where OTD's hysteresis gate
                    # would clear for this tranche IF TA confirms.
                    #
                    # v3.26.0 (issue #97) — `_otd_factor` comes from
                    # `otd_math`, the module the executor calls. The
                    # expression here was `ref_v * (1.0 - _otd_pct /
                    # 100.0)` over an interval-only `_otd_pct`, which is
                    # a second implementation of the executor's gate and
                    # printed a price the executor refuses.
                    if (ref_v is not None and ref_v > 0
                            and _otd_pct > 0):
                        min_rebuy_v = ref_v * _otd_factor
                        mr_item = QTableWidgetItem(f"≤${min_rebuy_v:.8f}")
                        mr_item.setToolTip(
                            f"OTD-derived guide only (ref × (1 − "
                            f"{_otd_pct:.2f}%), the Minimum Opposing "
                            f"Trade Distance = scrumming interval + "
                            f"trading fee, read from the same otd_math "
                            f"the executor uses). Fold-back requires TA "
                            f"validation in the GEP regardless. This is "
                            f"NOT a trigger price.")
                        table.setItem(row, 6, mr_item)
                    elif ref_v is not None and ref_v > 0:
                        table.setItem(row, 6, QTableWidgetItem(f"<${ref_v:.8f}"))
                    else:
                        table.setItem(row, 6, QTableWidgetItem("—"))

                    # v3.16.43 — Status reflects the new architectural
                    # design: OTD-threshold gate per tranche (binding),
                    # plus TA validation in GEP (mandatory, separate).
                    # The original-cost field is informational — does
                    # not gate fold-back. Compound saturation is governed
                    # by position-level smart ceiling (visible in Bot
                    # Settings, not per-tranche).
                    #
                    # v3.26.0 (issue #97) — the threshold is
                    # `ref_v * _otd_factor`, the SAME binding the Min
                    # rebuy cell above reads, from the SAME `otd_math`
                    # call the executor makes. It was a second copy of
                    # `ref_v * (1.0 - _otd_pct / 100.0)` over an
                    # interval-only percentage, so a row could show a
                    # green "Price-OK" for a buy the executor refuses.
                    if (cur_price > 0 and ref_v is not None
                            and ref_v > 0 and _otd_pct > 0):
                        otd_thresh = ref_v * _otd_factor
                        otd_factor_diff_pct = (cur_price - otd_thresh) / otd_thresh * 100.0
                        if cur_price <= otd_thresh:
                            status_str = f"Price-OK ({otd_factor_diff_pct:+.2f}% vs OTD)"
                            status_color = "#00ff88"
                        else:
                            status_str = f"Need price ≤ OTD ({otd_factor_diff_pct:+.2f}%)"
                            status_color = "#ff9900"
                        si_status = QTableWidgetItem(status_str)
                        si_status.setForeground(QColor(status_color))
                        si_status.setToolTip(
                            "Price-gate status only (OTD threshold per "
                            "tranche). Actual fold-back additionally "
                            "requires TA validation in the GEP (bearish "
                            "+ midline + lower-DT) AND the bot's position "
                            "must be below its smart ceiling. "
                            "'Price-OK' means the per-tranche OTD gate "
                            "would pass IF TA confirms this tick AND the "
                            "position has not saturated.")
                        table.setItem(row, 7, si_status)
                    elif (cur_price > 0 and ref_v is not None
                          and ref_v > 0):
                        # OTD == 0 → no per-tranche price gate; rely on
                        # TA + position ceiling only. Show ref-relative.
                        ref_diff_pct = (cur_price - ref_v) / ref_v * 100.0
                        below_ref = cur_price < ref_v
                        status_str = (f"Below ref ({ref_diff_pct:+.2f}%)"
                                      if below_ref
                                      else f"Above ref ({ref_diff_pct:+.2f}%)")
                        si_status = QTableWidgetItem(status_str)
                        si_status.setForeground(QColor(
                            "#00ff88" if below_ref else "#ff9900"))
                        table.setItem(row, 7, si_status)
                    else:
                        table.setItem(row, 7, QTableWidgetItem("—"))

                    # issue #98 defect 5 — THE COLUMN NAMES THE ACTION
                    # THAT CREATED THE ROW. It used to print "manual
                    # fire", a BUY, which is the action that REMOVES a
                    # tranche. The mapping and the live counts behind
                    # the three labels are at the top of this module.
                    src_str = _fold_tranche_source_label(t)
                    si = QTableWidgetItem(src_str)
                    si.setToolTip(FOLD_SOURCE_TOOLTIPS[src_str])
                    if src_str == FOLD_SOURCE_MANUAL_SCRUM:
                        # The one semantic foreground on this column,
                        # unchanged. `_paint_fold_tranche_row` measured
                        # it at 6.12:1 against the fold fill and leaves
                        # any cell that already owns a foreground alone.
                        si.setForeground(QColor(FOLD_SOURCE_MANUAL_FG_HEX))
                    table.setItem(row, 8, si)

                    # v3.16.53 — Fire button for per-tranche operator-
                    # initiated fold-back. Captures the tranche dict by
                    # identity so post-click index lookups stay correct
                    # even if other ops mutate the list in the meantime.
                    fire_btn = QPushButton("Fire")
                    fire_btn.setToolTip(
                        "Operator-initiated fold-back of THIS tranche. "
                        "Bypasses TA / OTD / Target-Delta gates. Smart "
                        "Ceiling + MEM-257 fail-closed still apply. "
                        "Bot must be RUNNING.")
                    # The inset is a stylesheet MARGIN, and it works by
                    # a different mechanism than it looks. The margin
                    # does NOT resize the widget: the button still
                    # occupies the whole cell rect and still reports
                    # the full row height. What it changes is where the
                    # button's frame is PAINTED inside that rect. The
                    # margin strip at the top and bottom is left
                    # untouched, so the delegate's rule -- drawn
                    # underneath -- shows through it.
                    #
                    # `setFixedHeight` was tried first and is wrong
                    # here: `setCellWidget` TOP-aligns a short widget,
                    # so the clearance all landed at the bottom.
                    # Measured on the render, that freed the bottom
                    # rule to its full 890px while the top rule stayed
                    # broken at 849px. The margin insets both ends.
                    # Background matches the row fill so the blue band
                    # reads as CONTINUOUS across all ten columns.
                    # `setCellWidget` sizes the button to the whole
                    # cell rect — measured — so the old `#2a3a4a` grey
                    # would punch a hole in the container at its last
                    # column and read as a separate chip sitting
                    # outside the row. Its `#00ccff` border and text
                    # are unchanged and measure 6.12:1 against the new
                    # fill, so the control stays clearly a control.
                    _inset = TRANCHE_FIRE_BTN_INSET_PX // 2
                    fire_btn.setStyleSheet(
                        f"QPushButton {{ background: "
                        f"{FOLD_TRANCHE_BG_HEX}; color: "
                        f"#00ccff; border: 1px solid #00ccff; padding: "
                        f"2px 8px; margin: {_inset}px 0px; }} "
                        f"QPushButton:hover {{ background: #00ccff; "
                        f"color: #001122; }} "
                        f"QPushButton:disabled {{ background: #1a1a1a; "
                        f"color: #555; border-color: #555; }}")
                    # Capture tranche IDENTITY (not row index) so we
                    # can resolve the current index at click time.
                    #
                    # issue #98 defect 8 - THE NUMBER ON THE ROW IS
                    # CAPTURED TOO, and it is a different thing from the
                    # identity. The confirmation used to print the index
                    # it re-resolved at click time, so a fold landing
                    # between the panel being built and the button being
                    # pressed shifted every later index and the dialog
                    # named a tranche the operator had not clicked. The
                    # BUY was always correct - identity capture saw to
                    # that - but the number authorising it was not. This
                    # is the same capture-at-build-time mechanism the
                    # Arbiter button already uses for `tranche_id`, and
                    # it is one mechanism rather than a second: what is
                    # captured is what the operator can see.
                    _captured = t
                    _captured_number = queue_index + 1
                    fire_btn.clicked.connect(
                        lambda _checked=False, tr=_captured,
                        shown=_captured_number:
                            self._on_fire_tranche_clicked(tr, shown))
                    table.setCellWidget(row, 9, fire_btn)

                    # Item 5 — a fold tranche has NO Arbiter, and the
                    # cell says so in words rather than being left
                    # blank. There is no child holding this tranche and
                    # no second party who could close it: this bot's
                    # own fold-back does, and the Fire button beside it
                    # is how the operator asks for that. An em dash is
                    # the same answer item 4 gives on the other side of
                    # the table, where an Extractor row prints one
                    # under Fire.
                    #
                    # A REAL ITEM, NOT AN EMPTY CELL. The row painter
                    # would manufacture a background-only item here
                    # anyway, so the choice is between an explained
                    # dash and a silent blank; and both row-styling
                    # tests walk every column demanding a painted item,
                    # which an empty cell would satisfy while telling
                    # the operator nothing.
                    arb_na = QTableWidgetItem(ARBITER_NOT_APPLICABLE)
                    arb_na.setToolTip(
                        "Arbiter applies to Extractor Tranches only. "
                        "This is one of this bot's own fold tranches — "
                        "no child holds it, and its Fire button is how "
                        "you close it.")
                    table.setItem(row, ARBITER_COLUMN_INDEX, arb_na)

                    # LAST in the row, so every semantic foreground set
                    # above is already on its item and is preserved.
                    self._paint_fold_tranche_row(table, row)

                self._paint_extractor_tranche_rows(
                    table, ext_rows, len(tranches), now_ts)

                # The two counts stay named apart here for the same
                # reason the group title names them apart: an Extractor
                # row is a child's lease, not this bot's fold
                # inventory, and the refresh pin subtracts one from the
                # other rather than reporting their sum.
                self._fold_tranche_table = table
                self._fold_ext_row_count = len(ext_rows)

                # issue #98 defect 7 - WHAT THE FILTER SEARCHES, read
                # off the built table and nowhere else. Every string
                # here is a cell this panel composed from a stored
                # field, so the filter can never match a quantity the
                # operator cannot see, and there is no second reading of
                # the tranche dict that could disagree with the first.
                # Harvested AFTER the Extractor rows, so a lease row is
                # filtered by the same rule as a fold row.
                # `table.item` returns `QTableWidgetItem | None`, so
                # the item is bound ONCE and narrowed before `.text()`
                # is asked for. A comprehension that called `item`
                # twice would read a different object on each call and
                # both type checkers would be right to refuse it.
                _harvested: list[list[str]] = []
                for _r in range(table.rowCount()):
                    _cells: list[str] = []
                    for _c in range(table.columnCount()):
                        _item = table.item(_r, _c)
                        _cells.append(
                            "" if _item is None else _item.text())
                    _harvested.append(_cells)
                self._fold_row_texts = _harvested

                dl.addLayout(build_fold_row_controls(self))
                dl.addWidget(table)
                layout.addWidget(detail_group)
            else:
                empty = QLabel(
                    "No open tranches. The fold queue is empty — either "
                    "the bot has not yet executed a SCRUM, or every "
                    "previous SCRUM has been closed by a FOLD-BACK.")
                empty.setStyleSheet("color: #888; font-style: italic; "
                                    "padding: 10px;")
                empty.setWordWrap(True)
                layout.addWidget(empty)

            layout.addStretch()
            return w

        def _on_arbiter_toggle_clicked(
                self, tranche_id: str, child_bot_id: str,
                button: QPushButton, item: QTableWidgetItem) -> None:
            """Flip ONE Extractor Tranche's Arbiter. Moves no money.

            WHAT THIS DOES: resolves the child Extractor that owns the
            tranche, asks it to flip one stored string, and relabels
            the button. That is the whole of it.

            WHAT THIS MUST NEVER DO, stated because the control sits
            one column from a live Fire button: no order is placed or
            cancelled, no balance and no Target Balance is touched,
            nothing is scheduled onto the async loop and nothing is
            awaited. There is no `run_coroutine_threadsafe` here, and
            there must never be one — the Fire handler beside it needs
            that machinery precisely because it spends money.

            NO SAVE IS FORCED EITHER. Writing the value is a memory
            write; the fleet's 60-second periodic save and its shutdown
            save persist it through the path everything else uses.
            Calling `save_all_state()` from inside a click would
            serialise the whole fleet and copy a backup file ON THE GUI
            THREAD, which is the freeze class the operator has already
            been bitten by. The cost is stated rather than hidden: a
            toggle set and then a crash inside 60 seconds is lost,
            exactly as it is for every other runtime field.

            THE MANAGER COMES FROM THE BOT, NOT FROM `self._bm`. The
            Simulator constructs this dialog with no manager at all,
            and the listing tests do the same, so `self._bm` is None on
            real paths. The parent bot's own `_bot_manager` is the
            object that produced these rows in the first place.

            A TRANCHE THAT CLOSED WHILE THE TABLE SAT THERE IS REFUSED,
            NOT GUESSED. The child matches the full identity string, so
            an id belonging to a closed position matches nothing and
            returns None. This then leaves the button exactly as it
            was, which is the truth: nothing was written.
            """
            from PySide6.QtWidgets import QMessageBox

            # EACH MESSAGE REPORTS THE STEP THAT ACTUALLY RAN, not a
            # blanket claim about a state nobody checked. The lookup is
            # the operation on this path, so its own result is what the
            # operator is told, and every one of these says outright
            # that nothing was written.
            manager = getattr(self._bot, "_bot_manager", None)
            getter = getattr(manager, "get_bot", None)
            if not callable(getter):
                QMessageBox.warning(
                    self, "Arbiter not changed",
                    "Nothing was written. This panel has no bot "
                    "registry attached, so the Extractor holding this "
                    "tranche could not be looked up. Reopen the panel "
                    "once the platform has finished starting.")
                return
            child = getter(child_bot_id)
            toggler = getattr(child, "toggle_tranche_arbiter", None)
            if not callable(toggler):
                # The lookup RAN, and what it produced is named, so the
                # operator is reading an observation rather than a
                # guess. `type(None).__name__` prints "NoneType", which
                # is itself the fact that the id matched no bot.
                QMessageBox.warning(
                    self, "Arbiter not changed",
                    f"Nothing was written. The Arbiter is set by the "
                    f"Extractor that holds the tranche; asking the "
                    f"registry for bot id '{child_bot_id or '?'}' "
                    f"produced a {type(child).__name__}, which cannot "
                    f"set one. Reopen the panel to rebuild the list "
                    f"from the running fleet.")
                return

            try:
                new_value = toggler(tranche_id)
            except Exception as exc:  # R28-OK: operator surface
                logger.exception(
                    "Arbiter toggle failed for tranche %s on child %s",
                    tranche_id, child_bot_id)
                QMessageBox.critical(
                    self, "Arbiter not changed",
                    f"Nothing was changed — the call failed:\n\n"
                    f"{type(exc).__name__}: {exc}")
                return

            if new_value is None:
                # The write WAS attempted: the child was asked, and it
                # answered that no open position carries this identity.
                # That answer is what gets reported, rather than a
                # guess at why.
                QMessageBox.warning(
                    self, "Arbiter not changed",
                    "Nothing was written. The Extractor reports no "
                    "open position with this tranche's identity — it "
                    "has most likely exited the position since this "
                    "panel was opened. Reopen the panel to see the "
                    "tranches it holds now.")
                return

            label = _arbiter_label(new_value)
            tip = _compose_arbiter_tooltip(new_value)
            # Both surfaces, so the model and the widget cannot
            # disagree about what is stored. Neither object can have
            # been destroyed: this tab is built once and never
            # repopulated, and a deleted button could not have emitted
            # the click that got us here.
            button.setText(label)
            button.setToolTip(tip)
            item.setText(label)
            item.setToolTip(tip)

        def _on_fire_tranche_clicked(
                self, tranche: dict,
                clicked_number: int | None = None) -> None:
            """v3.16.53 — operator-initiated per-tranche fold-back.

            Resolves the tranche's current index (in case the list
            mutated since the table was built), confirms with the
            operator, then schedules bot.manual_fire_tranche on the
            bot manager's async loop.

            issue #98 defect 8 - THE DIALOG NAMES THE ROW THAT WAS
            CLICKED. `clicked_number` is the `#` printed on that row,
            captured in the button's own closure when the row was
            built, beside the identity capture that was already there.

            WHAT WAS MEASURED. Every operator-facing string in this
            method printed `idx + 1`, the index re-resolved HERE at
            click time. The panel is a snapshot and the bot keeps
            trading behind it, so a fold that consumes an earlier
            tranche shifts every later index down by one: the operator
            clicks the row printed 7 and the confirmation offers to
            fire tranche 6. The BUY was never wrong - `tranches.index`
            finds the captured dict wherever it moved to - but a
            confirmation for a market buy named a tranche the operator
            had not pointed at, at the one moment the action cannot be
            undone.

            TWO NUMBERS, AND THEY ARE NOT INTERCHANGEABLE. `idx` is
            what the ORDER needs: `manual_fire_tranche(idx)` indexes
            the live list, so it stays the resolved one and is not
            touched. `_row_no` is what the OPERATOR needs: the number
            they read. When the two disagree the confirmation says so
            in a line of its own rather than picking one and hiding the
            other, because a queue that moved under the panel is
            something the operator should know before authorising a
            buy.

            `clicked_number` DEFAULTS TO None, and the fallback is the
            resolved index. A caller with no row number - a test
            driving this handler directly, or any future caller - gets
            exactly the pre-repair strings rather than a blank.
            """
            from PySide6.QtWidgets import QMessageBox
            import asyncio as _asyncio

            # The repo's ONE admission rule, imported the way this
            # module imports every other trading symbol: locally,
            # so this dialog never drags the trading package in at
            # module import time. The fold-row builder that made
            # the Fire button reads the SAME dict through this
            # SAME helper -- the row and its confirmation must not
            # disagree about whether a value is readable.
            from ..trading.bot_container import (
                as_finite_float as _as_finite_float,
            )

            try:
                tranches = list(getattr(self._bot, "_fold_tranches", []))
                # Resolve current index by identity
                try:
                    idx = tranches.index(tranche)
                except ValueError:
                    # The clicked number is the ONLY number available
                    # here: there is no index to resolve, because the
                    # tranche is gone. Naming the row the operator
                    # pressed is what tells them WHICH one vanished.
                    _gone = ("This tranche"
                             if clicked_number is None
                             else f"Tranche #{clicked_number}")
                    QMessageBox.warning(
                        self, "Tranche unavailable",
                        f"{_gone} is no longer in the fold queue "
                        f"(it may have just been consumed by an "
                        f"auto-fold or another manual action). Refresh "
                        f"the tab.")
                    return

                # issue #98 defect 8 - the number the operator READ.
                # Everything they are shown from here down quotes
                # `_row_no`. `idx` is kept for the order alone.
                _row_no = (idx + 1 if clicked_number is None
                           else int(clicked_number))
                _moved = (_row_no != idx + 1)

                # Confirm
                #
                # THE THREE MONEY VALUES BELOW ARE DISPLAY-ONLY IN
                # THIS METHOD. The only thing that crosses to the
                # order is `idx`, an int, at the
                # `manual_fire_tranche(idx)` call further down.
                #
                # THAT IS NOT A REASON TO ONLY FIX THE DISPLAY.
                # Each one is a MIRROR of a value the order path
                # re-derives from THIS SAME dict -- captured by
                # identity where the row was built -- using a
                # character-identical expression:
                #
                #   ScrummingBot.manual_fire_tranche
                #     cost = float(tranche.get("usd", 0) or 0)
                #     ...
                #     await self._execute_buy(cost=cost, ...)
                #
                # So a value this dialog cannot read honestly is a
                # value the MARKET BUY IS STILL SIZED FROM. Driven
                # against both live expressions, not predicted:
                # a stored `nan` renders "$nan" here and arrives as
                # `_execute_buy(cost=nan)` intact, because the
                # order's only guard is `cost <= 0` and `nan <= 0`
                # is False. `inf` does the same. A stored `True`
                # renders "$1.0000" and buys one dollar; the string
                # "20.0" renders "$20.0000" and buys twenty.
                #
                # BLANKING THE LABEL ALONE WOULD BE THE WORSE
                # OUTCOME. An em dash beside a Confirm button that
                # still buys reads as handled. So the fire is
                # REFUSED here, BEFORE the confirmation is offered,
                # and the refusal names the field and its stored
                # value so the operator can go and look at it. No
                # dash is ever rendered next to a live Confirm.
                #
                # `_as_finite_float` is the settled reader already
                # used by the fold-row builder above: EXACT type
                # (so a stored `True` is not the number 1), finite
                # (so `nan` and `inf` are not numbers), and an
                # INTEGER bound check (so `10**400` is refused
                # rather than raising, which `float()` does and
                # `math.isfinite()` also does).
                #
                # The trailing `or 0.0` is NOT redundant. It keeps
                # the live normalisation for every value the helper
                # ACCEPTS: live computed `float(x or 0)`, which maps
                # a stored `-0.0` to positive `0.0`. The helper
                # returns `-0.0` unchanged, and `"$%.4f" % -0.0` is
                # "$-0.0000". A readable value is not this unit's to
                # restyle, so it is normalised exactly as before.
                _reads = (
                    ("USD parked", "usd", tranche.get("usd", 0)),
                    ("Sell ref", "ref", tranche.get("ref", 0)),
                    ("Original cost", "initial_buy_price",
                     tranche.get("initial_buy_price",
                                 tranche.get("ref", 0))),
                )
                _clean: dict = {}
                _unreadable: list = []
                for _field, _key, _raw in _reads:
                    _val = _as_finite_float(_raw)
                    if _val is None:
                        # Bound the echo: a refused value can be a
                        # 309-digit int, and the point of the echo
                        # is to identify the bad field, not to
                        # reprint it.
                        _shown = repr(_raw)
                        if len(_shown) > 40:
                            _shown = _shown[:40] + "..."
                        _unreadable.append(
                            f"  {_field} (key {_key!r}): stored "
                            f"{type(_raw).__name__} {_shown}")
                        continue
                    _clean[_field] = _val or 0.0
                if _unreadable:
                    _bad = "\n".join(_unreadable)
                    logger.error(
                        "Bot %s manual fire REFUSED on tranche #%d "
                        "(queue index %d): unreadable stored "
                        "value(s): %s",
                        getattr(self._bot, "bot_id", "?")[:8],
                        _row_no, idx + 1, "; ".join(_unreadable))
                    QMessageBox.critical(
                        self, "Manual Fire refused — unreadable value",
                        f"Tranche #{_row_no} was NOT fired. NO ORDER "
                        f"WAS PLACED.\n\n"
                        f"This tranche stores a value that is not a "
                        f"usable number:\n\n{_bad}\n\n"
                        f"The confirmation is not being offered "
                        f"because the market buy would be sized from "
                        f"that same stored value, and you would be "
                        f"authorising an amount this dialog cannot "
                        f"show you honestly.\n\n"
                        f"Nothing has changed. The tranche is still "
                        f"in the fold queue. Check this bot's saved "
                        f"state before firing it.")
                    return
                _usd = _clean["USD parked"]
                _ref = _clean["Sell ref"]
                _ibp = _clean["Original cost"]
                # issue #98 defect 8 - the confirmation names the
                # row that was clicked. When the queue has moved
                # under the panel the shift gets a line of its own:
                # the operator is told the record they pointed at
                # has slid, rather than being shown one of the two
                # numbers with no way to tell which.
                # `manual_fire_tranche` still receives `idx`, so
                # the buy is unchanged either way.
                _moved_note = (
                    f"THE QUEUE HAS MOVED. You clicked the row "
                    f"printed #{_row_no}. That same tranche now "
                    f"sits at #{idx + 1} in the fold queue, "
                    f"because tranches before it were folded or "
                    f"cleared after this panel was built. This "
                    f"fires the tranche you clicked.\n\n"
                    if _moved else "")
                _confirm_msg = (
                    f"Fire tranche #{_row_no}?\n\n"
                    f"  USD parked:    ${_usd:.4f}\n"
                    f"  Sell ref:      ${_ref:.8f}\n"
                    f"  Original cost: ${_ibp:.8f}\n\n"
                    f"{_moved_note}"
                    f"This will execute a MARKET buy at the current "
                    f"price, bypassing TA / OTD / Target-Delta gates. "
                    f"Smart Ceiling and MEM-257 fail-closed still apply.")
                btn = QMessageBox.question(
                    self, "Manual Tranche Fire — confirm",
                    _confirm_msg,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No)
                if btn != QMessageBox.Yes:
                    return

                # Schedule on the bot manager's async loop
                _loop = getattr(self._bm, "_async_loop", None) if self._bm else None
                if _loop is None:
                    QMessageBox.warning(
                        self, "Async loop unavailable",
                        "Bot manager async loop not running. Is the "
                        "trading platform fully started? Try again "
                        "after launch completes.")
                    return

                _coro = self._bot.manual_fire_tranche(idx)
                try:
                    _future = _asyncio.run_coroutine_threadsafe(_coro, _loop)
                except Exception as _sched_exc:
                    QMessageBox.warning(
                        self, "Schedule failed",
                        f"Could not schedule the fold-back:\n\n"
                        f"{type(_sched_exc).__name__}: {_sched_exc}")
                    return

                # v3.16.55 — TRUE non-blocking dispatch. The v3.16.54
                # implementation used `_future.result(timeout=5.0)` which
                # FROZE the GUI thread waiting up to 5 seconds, then
                # presented a misleading TimeoutError dialog even when
                # the underlying buy was simply mid-flight. Operator
                # report 2026-05-12: "I should not be getting a time out
                # on the manual fire regardless... There are bugs here."
                #
                # Correct pattern: return immediately. The bot.log event
                # subscription on the main window already shows the
                # outcome via "MANUAL TRANCHE FIRE COMPLETE" / refusal
                # log lines. A QTimer polls the future periodically and
                # surfaces the result dialog when it lands, without ever
                # blocking the event loop.
                QMessageBox.information(
                    self, "Manual Fire dispatched",
                    f"Fold-back dispatched on tranche #{_row_no}.\n\n"
                    f"Watch the Activity Log for the outcome. The "
                    f"result dialog will appear here when the buy "
                    f"completes (no time limit — Coinbase market "
                    f"orders may take several seconds during busy "
                    f"windows; this is normal).")

                # Spawn a non-blocking poller via QTimer. Fires every
                # 500ms; gives up after 120 seconds (the Activity Log
                # is still authoritative regardless).
                from PySide6.QtCore import QTimer as _QTimer
                _start_ts = __import__("time").monotonic()
                _poll_timer = _QTimer(self)
                _poll_timer.setInterval(500)

                def _check_future():
                    try:
                        if _future.done():
                            _poll_timer.stop()
                            try:
                                result = _future.result(timeout=0.1)
                            except Exception as _rx:
                                # Future errored (e.g. coroutine raised).
                                QMessageBox.warning(
                                    self, "Manual Fire raised",
                                    f"Tranche #{_row_no} fold-back "
                                    f"raised:\n\n"
                                    f"{type(_rx).__name__}: {_rx}\n\n"
                                    f"See Activity Log for full trace.")
                                return
                            if isinstance(result, dict) and result.get(
                                    "applied"):
                                _fill = result.get("fill_price", 0.0)
                                _units = result.get("units_returned", 0.0)
                                _remaining = result.get(
                                    "remaining_tranches", 0)
                                # issue #98 defect 1 - THE SIBLING
                                # HOLE. A filled fold-back removes the
                                # tranche it fired, so this panel is
                                # stale for exactly the reason a clear
                                # leaves it stale, and it used to say
                                # so instead of fixing it. No save is
                                # forced here: the fill itself is a
                                # TRADE, and the trade path owns its
                                # own persistence.
                                _r = self._refresh_fold_tranches_tab()
                                QMessageBox.information(
                                    self, "Manual Fire complete",
                                    f"Tranche #{_row_no} fold-back "
                                    f"filled.\n\n"
                                    f"  Fill price:   ${_fill:.8f}\n"
                                    f"  Units back:   {_units:.6f}\n"
                                    f"  Remaining:    {_remaining} "
                                    f"tranche(s)\n\n"
                                    + ("The panel behind this message "
                                       "has been rebuilt and now shows "
                                       "the new state."
                                       if _r == "refreshed" else
                                       f"The panel was {_r}. Close and "
                                       f"reopen this dialog to see the "
                                       f"new state."))
                            else:
                                _reason = (
                                    result.get("reason", "unknown")
                                    if isinstance(result, dict)
                                    else "unknown")
                                QMessageBox.warning(
                                    self, "Manual Fire refused",
                                    f"Tranche #{_row_no} fold-back "
                                    f"NOT applied.\n\n"
                                    f"Reason: {_reason}")
                            return
                        # Not done yet — give up after 120s. The bus log
                        # will still show the eventual outcome; we just
                        # stop polling so the dialog isn't haunted.
                        if __import__("time").monotonic() - _start_ts > 120.0:
                            _poll_timer.stop()
                    except Exception:  # R28-OK: poll probe; best-effort
                        _poll_timer.stop()

                _poll_timer.timeout.connect(_check_future)
                _poll_timer.start()
            except Exception as exc:
                logger.exception(
                    "Bot %s _on_fire_tranche_clicked raised: %s",
                    getattr(self._bot, "bot_id", "?")[:8], exc)
                try:
                    QMessageBox.critical(
                        self, "Manual Fire error",
                        f"Unexpected error:\n\n"
                        f"{type(exc).__name__}: {exc}")
                except Exception as _dlg_exc:  # noqa: BLE001 - error-dialog best-effort
                    logger.debug(
                        "critical error dialog failed to display: %s",
                        _dlg_exc)

        @staticmethod
        def _format_age(seconds: float) -> str:
            """Human-readable age string. v3.16.39 P2-VIS helper."""
            if seconds < 60:
                return f"{int(seconds)}s"
            if seconds < 3600:
                return f"{int(seconds / 60)}m"
            if seconds < 86400:
                hrs = seconds / 3600
                return f"{hrs:.1f}h"
            days = seconds / 86400
            return f"{days:.1f}d"

        # ---------------------------------------------------------------
        # Tab 3.5: Stack Tranches (v3.23.28, scrumming + stack_mode only)
        # ---------------------------------------------------------------
        # Mirrors Fold Tranches styling. Reads `_bot._stack_tranches` +
        # `_bot._stack_created`. Surfaces per-tranche state (target
        # price, size, mode Visible/Invisible, status, fill price, age)
        # so operator can see Stack lifecycle without needing a log dump.
        def _create_stack_tranches_tab(self) -> QWidget:
            import time as _time

            # Item 9 (2026-08-13) — the same admission rule the despawn
            # sweep and the Settings spinbox use, imported here the way
            # this module imports every other trading symbol: locally,
            # so building a tab never drags the trading package in at
            # module import time.
            from ..trading.bot_container import (
                as_finite_float as _as_finite_float,
            )
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.setSpacing(8)

            tranches = list(getattr(self._bot, "_stack_tranches", []) or [])
            now_ts = _time.time()
            created_lifetime = int(getattr(
                self._bot, "_stack_created", 0) or 0)

            # --- Summary ---
            summary = QGroupBox("Stack-Tranche Cycle Health")
            sf = QFormLayout(summary)
            self._configure_form(sf)

            pending = [t for t in tranches if t.get("status") == "pending"]
            filled = [t for t in tranches if t.get("status") == "filled"]
            cancelled = [t for t in tranches if t.get("status") == "cancelled"]

            # Item 10 (2026-08-14) — the same admission rule
            # the two age rows already use, applied to the money keys
            # on the same dict. `size` is read here and again on the
            # detail row below, so both must refuse the same shapes
            # or the panel contradicts itself.
            #
            # A REFUSED MEMBER IS COUNTED, NOT DROPPED. Silently
            # skipping an unreadable entry reports a total lower
            # than the truth with nothing on the panel saying so.
            # That is the shape of the claim-total defect of
            # 2026-08-10, which reported $2,000 against a true
            # $3,000 and logged nothing. The count rides beside the
            # number instead.
            #
            # `or 0` IS GONE. It mapped None, "" and False onto the
            # int 0 before any guard could see them, so a missing
            # size printed a confident 0.000000 into a base-unit
            # total. `t.get("size", 0)` still defaults an ABSENT key
            # to 0, which is what it rendered before and still
            # renders.
            pending_size_total = 0.0
            pending_size_unreadable = 0
            for _pending in pending:
                _pending_size = _as_finite_float(_pending.get("size", 0))
                if _pending_size is None:
                    pending_size_unreadable += 1
                else:
                    pending_size_total += _pending_size
            filled_ratio_str = (
                f"{len(filled) / created_lifetime:.1%}  "
                f"({len(filled)}/{created_lifetime})"
                if created_lifetime > 0 else "—  (no stacks opened yet)"
            )

            sf.addRow("Pending tranches:", QLabel(str(len(pending))))
            sf.addRow("Filled tranches:", QLabel(str(len(filled))))
            sf.addRow("Cancelled tranches:", QLabel(str(len(cancelled))))

            pending_size_str = f"{pending_size_total:,.6f} base units"
            if pending_size_unreadable:
                pending_size_str += (
                    f"  (+{pending_size_unreadable} unreadable)")
            pending_lbl = QLabel(pending_size_str)
            pending_lbl.setStyleSheet(
                "font-weight: bold; font-size: 13px; color: #ff9900;")
            sf.addRow("Pending size (unfilled):", pending_lbl)

            # Oldest pending age
            # EXACT type AND finite, mirroring the Fold panel's own
            # summary row. `isinstance` admits bool, so a stored
            # `True` was arithmetic'd as 1.0 — dating the tranche to
            # the epoch and reporting an age near 57 years on the
            # row the operator reads to judge whether Stack Mode has
            # stalled. `inf` was worse than wrong: it passed the
            # `> 0` test, and `int(-inf)` inside `_format_age` then
            # raised OverflowError with no `try` between here and
            # the click, so the dialog would not open at all.
            # `as_finite_float` bounds huge ints with an integer
            # comparison rather than `math.isfinite`, which raises
            # on the very input it would be added to reject.
            ages_sec = []
            for t in pending:
                ots = _as_finite_float(t.get("opened_ts"))
                if ots is not None and ots > 0:
                    ages_sec.append(now_ts - ots)
            if ages_sec:
                oldest_str = self._format_age(max(ages_sec))
            elif pending:
                oldest_str = "— (no timestamp)"
            else:
                oldest_str = "no pending tranches"
            sf.addRow("Oldest pending age:", QLabel(oldest_str))

            sf.addRow("Lifetime tranches opened:",
                      QLabel(str(created_lifetime)))

            ratio_lbl = QLabel(filled_ratio_str)
            if created_lifetime >= 3 and len(pending) > 0:
                _ratio = len(filled) / created_lifetime
                if _ratio < 0.3:
                    ratio_lbl.setStyleSheet("color: #ff3366;")
                elif _ratio < 0.7:
                    ratio_lbl.setStyleSheet("color: #ff9900;")
                else:
                    ratio_lbl.setStyleSheet("color: #00ff88;")
            sf.addRow("Fill ratio (filled/opened):", ratio_lbl)

            # Item 9 (2026-08-13) — the mirror of the Fold panel's own
            # discarded row. `filled` counts only STANDING filled
            # tranches, `created_lifetime` counts every one ever opened,
            # and the despawn sweep removes records from the first while
            # leaving the second alone. Without this row the ratio above
            # simply falls after every sweep — into the red under 30% —
            # with nothing on the panel saying where the tranches went.
            # Shown only once non-zero, exactly as the Fold panel does,
            # so a bot that has never been swept sees no extra row.
            #
            # Read through `as_finite_float` rather than the Fold
            # panel's bare `int(... or 0)`. Same reason as the state
            # export: `int(float("nan"))` raises ValueError, and this
            # runs while the Stack tab is being built, so the operator
            # would get a traceback instead of a panel. The Fold panel's
            # line is unchanged — putting both on one rule is a separate
            # unit.
            discarded_lifetime = int(
                _as_finite_float(getattr(self._bot, "_stack_discarded", 0))
                or 0.0)
            if discarded_lifetime:
                sf.addRow("Lifetime tranches discarded (delisted, not filled):",
                          QLabel(str(discarded_lifetime)))

            layout.addWidget(summary)

            # --- Detail ---
            if not tranches:
                empty_lbl = QLabel(
                    "No stack tranches yet. When Stack Mode is enabled "
                    "and a SCRUM fires, tranches will appear here."
                )
                empty_lbl.setStyleSheet("color: #888; padding: 12px;")
                empty_lbl.setWordWrap(True)
                layout.addWidget(empty_lbl)
                layout.addStretch()
                return w

            detail_group = QGroupBox(f"Tranches ({len(tranches)})")
            dg = QVBoxLayout(detail_group)

            # Header row
            header = QLabel(
                "  #  |  Target Price  |    Size      |  Mode     |  "
                "Status     |  Fill Price   |  Age")
            header.setStyleSheet(
                "font-family: monospace; font-weight: bold; "
                "color: #66ccff; padding: 2px;")
            dg.addWidget(header)

            # Item 10 (2026-08-14) — every numeric key on
            # the row, on the one rule. NONE of these had a guard,
            # and NONE of them sits inside a `try`: the path from
            # here is `_create_stack_tranches_tab` -> `__init__` ->
            # `MainWindow._on_bot_clicked`, with no handler at any
            # step, so a raise means Bot Settings does not open for
            # that bot at all.
            #
            # Measured on live before this change: `index` of `inf`
            # raised OverflowError, of `nan` ValueError, and of None
            # or a string TypeError and ValueError; `price`, `size`
            # and `fill_price` of 10**400 raised OverflowError from
            # `float()`. `nan` and `inf` did not raise, which was
            # worse: they printed `$nan` and `$inf` into a money
            # column. `as_finite_float` bounds huge ints with an
            # integer comparison, because `math.isfinite(10**400)`
            # raises the very error it would be added to prevent.
            #
            # WHY A REFUSAL IS AN EM DASH AND NEVER A ZERO. These
            # columns carry money and size. A refused value that
            # renders 0.00000000 is a confident wrong number, which
            # is a new defect rather than a fix. The em dash is what
            # this table already prints for an absent fill price and
            # an unusable timestamp, so a refusal lands on a path
            # the panel already had. Each is padded to the minimum
            # width its valid rendering occupies, so the column
            # stays aligned.
            #
            # `index` is an ordinal, so it takes the em dash too,
            # and an accepted value goes through `int()` exactly as
            # the discarded-count row above does.
            no_value = "—"
            for t in tranches:
                _idx = _as_finite_float(t.get("index", 0))
                idx_str = (f"{int(_idx):>2}" if _idx is not None
                           else f"{no_value:>2}")
                _price = _as_finite_float(t.get("price", 0))
                price_str = (f"${_price:>10.8f}" if _price is not None
                             else f"{no_value:>11}")
                _size = _as_finite_float(t.get("size", 0))
                size_str = (f"{_size:>10.6f}" if _size is not None
                            else f"{no_value:>10}")
                status = str(t.get("status", "unknown"))
                mode = "VISIBLE" if t.get("visible") else "INVISIBLE"
                # The truthiness gate is KEPT. A stored 0.0 fill
                # price printed the em dash before this change and
                # must keep printing it; admitting it here would
                # change a valid rendering, which this unit may not
                # do.
                fill = t.get("fill_price")
                _fill = _as_finite_float(fill) if fill else None
                fill_str = (f"${_fill:.8f}" if _fill is not None
                            else no_value)
                # The same rule as the summary row above, which
                # this column must agree with: both render the age
                # of the same tranche from the same key. The bare
                # `float(ots)` here was the wider hole of the two —
                # it also admitted Decimal, Fraction, a numeric
                # string and any object with `__float__` — so
                # closing the summary alone would have left this row
                # printing an age directly beneath a summary
                # reporting no timestamp for that same tranche.
                ots = _as_finite_float(t.get("opened_ts"))
                age_str = (self._format_age(now_ts - ots)
                           if ots is not None and ots > 0 else "—")
                row = QLabel(
                    f"  {idx_str} |  {price_str}  |  {size_str}  |  "
                    f"{mode:<9}|  {status:<10} |  {fill_str:<12} |  {age_str}"
                )
                row.setStyleSheet(
                    "font-family: monospace; padding: 1px;"
                    + (" color: #00ff88;" if status == "filled"
                       else " color: #ff3366;" if status == "cancelled"
                       else "")
                )
                dg.addWidget(row)

            layout.addWidget(detail_group)
            layout.addStretch()
            return w

        # ---------------------------------------------------------------
        # Tab 4: Bot Swarm (v3.16.44 P2-VIS, scrumming-only)
        # ---------------------------------------------------------------
        # Surfaces Smart Wire / Bot Swarm state per the operator's
        # patent-flagged Invention #6 (cross-compounding network).
        # Same pre-emptive pattern that Fold Tranches tab demonstrated:
        # surface the state before issues accumulate; let the operator
        # catch architectural problems via inspection rather than
        # post-hoc forensics. Mirrors smart_wire.py:SmartWireManager
        # internal data: _wires (topology), _ledgers (per-bot profit
        # provenance), _transactions (chronological event feed). Plus
        # the bot's own _pending_wire_credits / _pending_wire_ledger.
        def _create_bot_swarm_tab(self) -> QWidget:
            import time as _time

            # The same admission rule the Fold Tranches, Stack Tranches
            # and Manual Fire surfaces already read their ages through,
            # imported the way this module imports every other trading
            # symbol: locally, so building a tab never drags the trading
            # package in at module import time.
            from ..trading.bot_container import (
                as_finite_float as _as_finite_float,
            )
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.setSpacing(8)

            # Pull the Smart Wire manager (set externally on the bot
            # via set_smart_wire). May be None if Bot Swarm not enabled
            # or bot not yet attached.
            mgr = getattr(self._bot, "_smart_wire_mgr", None)
            bot_id = getattr(self._bot, "bot_id", "")
            now_ts = _time.time()

            # If Smart Wire manager not attached, show empty state
            # explaining why and exit.
            if mgr is None:
                msg = QLabel(
                    "<b>Bot Swarm not active for this bot.</b><br><br>"
                    "Smart Wire manager has not been attached. The "
                    "bot is operating standalone — no wire connections "
                    "can fire to/from it. To enable Bot Swarm "
                    "integration, ensure the bot is registered with "
                    "the platform's Smart Wire manager (typically "
                    "automatic for scrumming bots created via the "
                    "Bot Wizard with Smart Wire enabled).")
                msg.setStyleSheet("color: #aaa; padding: 12px;")
                msg.setWordWrap(True)
                layout.addWidget(msg)
                layout.addStretch()
                return w

            # --- Pull data from manager (defensive — internal dicts) ---
            wires_dict = getattr(mgr, "_wires", {}) or {}
            ledgers = getattr(mgr, "_ledgers", {}) or {}
            transactions = getattr(mgr, "_transactions", []) or []
            bot_refs = getattr(mgr, "_bot_refs", {}) or {}

            outbound = dict(wires_dict.get(bot_id, {}))  # {target_id: pct}
            # Inbound: scan all sources for entries targeting this bot.
            inbound: dict = {}
            for src_id, targets in wires_dict.items():
                if isinstance(targets, dict) and bot_id in targets:
                    # THE KEY IS KEPT EVEN WHEN THE VALUE IS
                    # REFUSED. The wire EXISTS; only its
                    # percentage is unreadable. Dropping the
                    # entry would delete a real connection from
                    # the count above and from the table below.
                    inbound[src_id] = _as_finite_float(
                        targets[bot_id])

            ledger = ledgers.get(bot_id)

            # --- Summary section ---
            summary = QGroupBox("Swarm Connections & Capital Flow")
            sf = QFormLayout(summary)
            self._configure_form(sf)

            sf.addRow("Outbound wires:",
                      QLabel(f"{len(outbound)} target(s)"))
            sf.addRow("Inbound wires:",
                      QLabel(f"{len(inbound)} source(s)"))

            # Lifetime $ in/out from this bot's ledger
            wired_in = _as_finite_float(
                getattr(ledger, "wired_in", 0)) if ledger else 0.0
            wired_out = _as_finite_float(
                getattr(ledger, "wired_out", 0)) if ledger else 0.0
            in_lbl = QLabel("—" if wired_in is None
                            else f"${wired_in:,.4f}")
            in_lbl.setStyleSheet("font-weight: bold; color: "
                                  + ("#00ff88" if wired_in is not None
                                     and wired_in > 0 else "#aaa"))
            sf.addRow("Lifetime wired-in (received):", in_lbl)

            out_lbl = QLabel("—" if wired_out is None
                             else f"${wired_out:,.4f}")
            out_lbl.setStyleSheet("font-weight: bold; color: "
                                   + ("#ff9900" if wired_out is not None
                                      and wired_out > 0 else "#aaa"))
            sf.addRow("Lifetime wired-out (sent):", out_lbl)

            # A DERIVED MONEY FIGURE INHERITS THE REFUSAL. If
            # either side is unreadable the difference is
            # unknowable, and printing it with the missing leg
            # treated as zero would state a net flow the ledger
            # never supported.
            if wired_in is None or wired_out is None:
                net_lbl = QLabel("—")
                net_lbl.setStyleSheet("font-weight: bold; color: #aaa;")
            else:
                net_flow = wired_in - wired_out
                net_lbl = QLabel(f"${net_flow:+,.4f}")
                net_lbl.setStyleSheet(
                    "font-weight: bold; color: "
                    + ("#00ff88" if net_flow >= 0 else "#ff3366"))
            sf.addRow("Net flow (in − out):", net_lbl)

            # Pending wire credits — currently parked, waiting for next
            # tranche to absorb. v3.15.69 stacking semantics may also
            # apply if at-entry conditions are met.
            pending_usd = _as_finite_float(getattr(
                self._bot, "_pending_wire_credits", 0))
            pending_lbl = QLabel("—" if pending_usd is None
                                 else f"${pending_usd:,.4f}")
            if pending_usd is not None and pending_usd > 0:
                pending_lbl.setStyleSheet(
                    "font-weight: bold; color: #00ccff;")
            sf.addRow("Pending wire credits:", pending_lbl)

            layout.addWidget(summary)

            # --- Provenance / Spawn section (if ledger has data) ---
            if ledger is not None:
                prov_group = QGroupBox(
                    "Provenance & Mature-Profit Spawn State")
                pf = QFormLayout(prov_group)
                self._configure_form(pf)

                starting = _as_finite_float(
                    getattr(ledger, "starting_balance", 0))
                pf.addRow("Starting balance (seed):",
                          QLabel("—" if starting is None
                                 else f"${starting:,.4f}"))

                # Predominant funder (non-SEED bot that funded this most)
                pred_src = None
                try:
                    pred_src = ledger.predominant_source
                except Exception:  # R28-OK: defensive accessor probe
                    pred_src = None
                if pred_src:
                    pf.addRow("Predominant funder (PPS):",
                              QLabel(str(pred_src)))
                else:
                    pf.addRow("Predominant funder (PPS):",
                              QLabel("— (SEED-funded only)"))

                # Mature profit math (used for spawn gate)
                try:
                    mature_total = float(ledger.mature_profit_total)
                    mature_avail = float(ledger.mature_profit_available)
                    mature_alloc = float(getattr(
                        ledger, "mature_profit_allocated", 0) or 0)
                except Exception:  # R28-OK: defensive math probe
                    mature_total = mature_avail = mature_alloc = 0.0

                # v3.23.36 — read the mature ratio from the ledger's
                # class attribute so the label stays in sync with the
                # runtime constant instead of hardcoding "70%".
                _mature_ratio_pct = 70
                try:
                    from ..trading.smart_wire import BotLedger
                    _mature_ratio_pct = int(round(
                        BotLedger.MATURE_RATIO * 100))
                except Exception as _mr_exc:  # noqa: BLE001 - label defaults to 70 if import fails
                    logger.debug(
                        "MATURE_RATIO lookup failed, using 70%%: %s",
                        _mr_exc)
                pf.addRow(
                    f"Mature profit total ({_mature_ratio_pct}% of P&L):",
                    QLabel(f"${mature_total:,.4f}"))
                pf.addRow("Mature profit allocated to spawns:",
                          QLabel(f"${mature_alloc:,.4f}"))

                avail_lbl = QLabel(f"${mature_avail:,.4f}")
                if mature_avail > 0:
                    avail_lbl.setStyleSheet("color: #00ff88;")
                else:
                    avail_lbl.setStyleSheet("color: #aaa;")
                pf.addRow("Mature profit available (spawn-eligible):",
                          avail_lbl)

                # Provenance breakdown — which bots funded this one
                prov_dict = dict(getattr(ledger, "provenance", {}) or {})
                if prov_dict:
                    prov_str = ", ".join(
                        f"{k}: ${v:,.2f}" for k, v in
                        sorted(prov_dict.items(), key=lambda kv: -kv[1]))
                    prov_label = QLabel(prov_str)
                    prov_label.setWordWrap(True)
                    prov_label.setStyleSheet("color: #ccc; font-size: 11px;")
                    pf.addRow("Provenance breakdown:", prov_label)

                layout.addWidget(prov_group)

            # --- Outbound wires table ---
            if outbound:
                out_group = QGroupBox(
                    f"Outbound Wires ({len(outbound)})")
                ol = QVBoxLayout(out_group)

                out_tbl = QTableWidget()
                out_tbl.setColumnCount(3)
                out_tbl.setHorizontalHeaderLabels([
                    "Target Bot", "Wire %", "Lifetime $ to target"])
                out_tbl.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeToContents)
                out_tbl.setRowCount(len(outbound))
                out_tbl.setMaximumHeight(180)
                out_tbl.setAlternatingRowColors(True)
                out_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

                # Per-target lifetime $ derived from transactions feed.
                # AN UNREADABLE LEG POISONS THE TOTAL RATHER THAN
                # VANISHING FROM IT. Skipping the row would report
                # a confident sum that is short by the amount it
                # could not read, with nothing on screen saying so.
                out_lifetime: dict = {tgt: 0.0 for tgt in outbound}
                out_unreadable: set = set()
                for tx in transactions:
                    if (getattr(tx, "source_bot", None) == bot_id
                            and getattr(tx, "target_bot", None) in out_lifetime):
                        _amt = _as_finite_float(
                            getattr(tx, "amount", None))
                        if _amt is None:
                            out_unreadable.add(tx.target_bot)
                        else:
                            out_lifetime[tx.target_bot] += _amt

                for row, (tgt_id, pct) in enumerate(sorted(outbound.items())):
                    # Resolve target asset if the target bot is registered
                    tgt_asset = ""
                    tgt_ledger = ledgers.get(tgt_id)
                    if tgt_ledger:
                        tgt_asset = getattr(tgt_ledger, "asset", "") or ""
                    label = f"{tgt_id}" + (f" ({tgt_asset})" if tgt_asset else "")
                    out_tbl.setItem(row, 0, QTableWidgetItem(label))
                    out_tbl.setItem(row, 1,
                                     QTableWidgetItem(f"{pct:.2f}%"))
                    lifetime = out_lifetime.get(tgt_id, 0.0)
                    out_tbl.setItem(row, 2, QTableWidgetItem("—"
                        if tgt_id in out_unreadable
                        else f"${lifetime:,.4f}"))

                ol.addWidget(out_tbl)
                layout.addWidget(out_group)

            # --- Inbound wires table ---
            if inbound:
                in_group = QGroupBox(
                    f"Inbound Wires ({len(inbound)})")
                il = QVBoxLayout(in_group)

                in_tbl = QTableWidget()
                in_tbl.setColumnCount(3)
                in_tbl.setHorizontalHeaderLabels([
                    "Source Bot", "Wire %", "Lifetime $ from source"])
                in_tbl.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeToContents)
                in_tbl.setRowCount(len(inbound))
                in_tbl.setMaximumHeight(180)
                in_tbl.setAlternatingRowColors(True)
                in_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

                # Per-source lifetime $ derived from transactions feed.
                # Same rule as the outbound total above.
                in_lifetime: dict = {src: 0.0 for src in inbound}
                in_unreadable: set = set()
                for tx in transactions:
                    if (getattr(tx, "target_bot", None) == bot_id
                            and getattr(tx, "source_bot", None) in in_lifetime):
                        _amt = _as_finite_float(
                            getattr(tx, "amount", None))
                        if _amt is None:
                            in_unreadable.add(tx.source_bot)
                        else:
                            in_lifetime[tx.source_bot] += _amt

                for row, (src_id, pct) in enumerate(sorted(inbound.items())):
                    src_asset = ""
                    src_ledger = ledgers.get(src_id)
                    if src_ledger:
                        src_asset = getattr(src_ledger, "asset", "") or ""
                    label = f"{src_id}" + (f" ({src_asset})" if src_asset else "")
                    in_tbl.setItem(row, 0, QTableWidgetItem(label))
                    in_tbl.setItem(row, 1, QTableWidgetItem("—"
                        if pct is None else f"{pct:.2f}%"))
                    lifetime = in_lifetime.get(src_id, 0.0)
                    in_tbl.setItem(row, 2, QTableWidgetItem("—"
                        if src_id in in_unreadable
                        else f"${lifetime:,.4f}"))

                il.addWidget(in_tbl)
                layout.addWidget(in_group)

            # --- Pending wire credits ledger ---
            pending_ledger = list(getattr(
                self._bot, "_pending_wire_ledger", []) or [])
            if pending_ledger:
                pl_group = QGroupBox(
                    f"Pending Wire Credits ({len(pending_ledger)})")
                pll = QVBoxLayout(pl_group)

                pl_tbl = QTableWidget()
                pl_tbl.setColumnCount(4)
                pl_tbl.setHorizontalHeaderLabels([
                    "Age", "Source", "USD", "Ref"])
                pl_tbl.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeToContents)
                pl_tbl.setRowCount(len(pending_ledger))
                pl_tbl.setMaximumHeight(180)
                pl_tbl.setAlternatingRowColors(True)
                pl_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

                for row, credit in enumerate(pending_ledger):
                    # THE SAME ADMISSION THE FOLD AND STACK AGE CELLS
                    # USE, and the last dict-backed one in this file.
                    # `credit` is restored verbatim by
                    # `ScrummingBot._restore_state`, which keeps every
                    # entry as `dict(_e)` and coerces no key, so `ts`
                    # arrives exactly as `json.load` decoded it.
                    # `json.loads("NaN")` and `json.loads("Infinity")`
                    # both return real floats and JSON has no integer
                    # width limit, so a corrupted or hand-edited
                    # bot_state.json reaches this line.
                    #
                    # THE OLD SHAPE FILTERED THE WRONG HALF. Coercing
                    # first and comparing second let `nan` through the
                    # `float()` and then out at `> 0` (False), while
                    # `inf` passed BOTH and raised OverflowError inside
                    # `_format_age`'s `int()`. A truthy non-number —
                    # "abc", a list, a dict — raised at the `float()`
                    # itself, before any guard could run, and `10**400`
                    # raised there too because it exceeds float range.
                    # `True` was worse than a raise: it read as one
                    # second past the epoch and printed a confident
                    # "20833.3d" for a stored flag.
                    #
                    # No caller is inside a `try`: this loop sits in
                    # `_create_bot_swarm_tab`, called bare from
                    # `BotLiveSettingsDialog.__init__`, called bare
                    # from `MainWindow._on_bot_clicked`. A raise here
                    # means Bot Settings does not open for that bot.
                    cts = _as_finite_float(credit.get("ts"))
                    if cts is not None and cts > 0:
                        age_str = self._format_age(now_ts - cts)
                    else:
                        age_str = "—"
                    pl_tbl.setItem(row, 0, QTableWidgetItem(age_str))
                    pl_tbl.setItem(row, 1, QTableWidgetItem(
                        str(credit.get("source", "?"))))
                    # THE SAME ADMISSION THE AGE CELL ABOVE USES,
                    # on the same dict from the same restore. A
                    # row whose age is trustworthy and whose money
                    # is not must say so in the money column.
                    cusd = _as_finite_float(credit.get("usd"))
                    pl_tbl.setItem(row, 2, QTableWidgetItem(
                        "—" if cusd is None
                        else f"${cusd:,.4f}"))
                    pl_tbl.setItem(row, 3, QTableWidgetItem(
                        str(credit.get("ref", ""))))

                pll.addWidget(pl_tbl)

                # v3.23.36 — retired the mid-tab prose explainer per
                # operator directive 2026-07-26 (same "hallucinatory
                # descriptive text" pattern removed from Fold Tranches
                # this session). The column headers + the row-level
                # data are the authoritative source; the meta-prose
                # made specific version claims (v3.15.69 stacking) that
                # would drift out of sync.

                layout.addWidget(pl_group)

            # --- Recent wire transactions (last 20 involving this bot) ---
            recent_tx = [
                tx for tx in reversed(transactions)
                if (getattr(tx, "source_bot", None) == bot_id
                    or getattr(tx, "target_bot", None) == bot_id)
            ][:20]
            if recent_tx:
                tx_group = QGroupBox(
                    f"Recent Wire Transactions (last {len(recent_tx)})")
                tl = QVBoxLayout(tx_group)

                tx_tbl = QTableWidget()
                tx_tbl.setColumnCount(5)
                tx_tbl.setHorizontalHeaderLabels([
                    "Age", "Direction", "Other Bot", "USD", "Type"])
                tx_tbl.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeToContents)
                tx_tbl.setRowCount(len(recent_tx))
                tx_tbl.setMaximumHeight(280)
                tx_tbl.setAlternatingRowColors(True)
                tx_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

                for row, tx in enumerate(recent_tx):
                    # LATENT, NOT ACTIVE — and guarded anyway, because
                    # the two Age columns in this one tab must not
                    # disagree about what an unreadable timestamp
                    # means.
                    #
                    # This reads an OBJECT, not a dict, and the
                    # difference is the whole reachability story.
                    # `tx` comes from `SmartWireManager._transactions`,
                    # which has NO assignment anywhere in src/ or
                    # tests/ — only `.append()` and `.extend()`. There
                    # is no deserialisation path, so unlike the pending
                    # ledger above nothing here round-trips through
                    # bot_state.json. Both reachable constructors pass
                    # a real int: `smart_wire.py` builds
                    # `WireTransaction(timestamp=int(_t.time()), ...)`
                    # and `scrumming_bot.py` does the same at its
                    # scrum-route audit hop. The two constructors that
                    # forward a caller-supplied `timestamp`
                    # (`execute_spawn_wire`, `process_wires`) have no
                    # callers at all.
                    #
                    # So no hostile value reaches this line TODAY. It
                    # is guarded because `getattr` is duck-typed —
                    # `_transactions` is a plain public-by-convention
                    # list any future writer can append to — and
                    # because a `WireTransaction` is a `@dataclass`,
                    # which annotates `timestamp: int` without
                    # enforcing it. The guard costs one call and
                    # removes the class rather than the instance.
                    cts = _as_finite_float(getattr(tx, "timestamp", None))
                    if cts is not None and cts > 0:
                        age_str = self._format_age(now_ts - cts)
                    else:
                        age_str = "—"
                    tx_tbl.setItem(row, 0, QTableWidgetItem(age_str))

                    src = getattr(tx, "source_bot", "")
                    tgt = getattr(tx, "target_bot", "")
                    if src == bot_id:
                        direction_str = "OUT →"
                        other = tgt
                        dir_color = "#ff9900"
                    else:
                        direction_str = "← IN"
                        other = src
                        dir_color = "#00ff88"
                    di = QTableWidgetItem(direction_str)
                    di.setForeground(QColor(dir_color))
                    tx_tbl.setItem(row, 1, di)

                    tx_tbl.setItem(row, 2, QTableWidgetItem(str(other)))
                    # LATENT for the same reason the Age cell one
                    # column over is: `_transactions` is only ever
                    # appended to. Guarded so the two money
                    # columns fed by this feed cannot disagree
                    # about what an unreadable amount means.
                    tamt = _as_finite_float(
                        getattr(tx, "amount", None))
                    tx_tbl.setItem(row, 3, QTableWidgetItem(
                        "—" if tamt is None
                        else f"${tamt:,.4f}"))
                    tx_tbl.setItem(row, 4, QTableWidgetItem(
                        str(getattr(tx, "wire_type", "") or "")))

                tl.addWidget(tx_tbl)
                layout.addWidget(tx_group)

            # If bot has zero wires, zero pending, zero ledger activity:
            # show explanation so the empty tab isn't confusing.
            if (not outbound and not inbound and not pending_ledger
                    and not recent_tx and ledger is None):
                empty = QLabel(
                    "Bot Swarm manager is attached but this bot has "
                    "no wire activity yet. Outbound wires are configured "
                    "via the Bot Swarm panel (drag connections between "
                    "bot tiles). Inbound wires fire when other bots "
                    "realize fold profit and route a configured % to "
                    "this bot. Until then, this tab will populate as "
                    "swarm activity occurs.")
                empty.setStyleSheet("color: #888; font-style: italic; "
                                     "padding: 10px;")
                empty.setWordWrap(True)
                layout.addWidget(empty)

            layout.addStretch()
            return w

        # ---------------------------------------------------------------
        # Tab 5: Market Inspector (v3.23.37, scrumming-only)
        # ---------------------------------------------------------------
        # Delegates to src.gui.market_inspector.build_per_bot_view, which
        # reads the shared analyzer's most recent scan (populated by the
        # top-level Market Inspector tab's Refresh button). Renders this
        # bot's asset card, higher-scoring markets, and opposing pairs.
        # Replaces the retired Mr. Inspector tab (was a phantom for
        # crypto bots — no caller wired ScrummingBot._mr_inspector).
        def _create_market_inspector_tab(self) -> QWidget:
            try:
                from .market_inspector import build_per_bot_view
                return build_per_bot_view(self._bot)
            except Exception as exc:  # noqa: BLE001 - GUI import guard
                logger.warning(
                    "Market Inspector per-bot view unavailable: %s",
                    exc)
                w = QWidget()
                lay = QVBoxLayout(w)
                msg = QLabel(
                    "<b>Market Inspector unavailable.</b><br><br>"
                    f"{type(exc).__name__}: {exc}")
                msg.setStyleSheet("color: #ff9900; padding: 12px;")
                msg.setWordWrap(True)
                lay.addWidget(msg)
                lay.addStretch()
                return w

        # ---------------------------------------------------------------
        # Tab 2: Settings (editable)
        # ---------------------------------------------------------------
        def _create_settings_tab(self) -> QWidget:
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.setSpacing(6)

            cfg = self._bot.config
            # v3.20.4 — is_grid removed (grid_bot deleted v3.16.0;
            # BotMode.GRID dropped from the enum).
            is_scrumming = cfg.mode.value == "scrumming"

            info = QLabel("Changes take effect immediately when Apply is clicked. "
                          "The bot does not need to be restarted.")
            info.setStyleSheet("color: #888; font-size: 11px; margin-bottom: 4px;")
            info.setWordWrap(True)
            layout.addWidget(info)

            # --- Trading Mode Settings ---
            mode_group = QGroupBox("Trading Parameters")
            mf = QFormLayout(mode_group)
            self._configure_form(mf)

            # Visibility
            self._vis = QComboBox()
            self._vis.addItem("Order Book (Visible)", "orderbook")
            self._vis.addItem("Internal (Invisible)", "internal")
            idx = self._vis.findData(cfg.visibility)
            if idx >= 0:
                self._vis.setCurrentIndex(idx)
            self._vis.currentIndexChanged.connect(
                lambda: self._mark_changed("visibility", self._vis.currentData()))
            mf.addRow("Order Visibility:", self._vis)

            # v3.23.25 — Check Interval widget removed (audit 2026-07-25).
            # Backing field `market_check_interval` was declared but no
            # runtime code ever read it; tick_interval is hardcoded 5.0.
            # Operator directive 2026-07-25: "The Check Interval setting
            # can be removed as the bot does not need a secondary poll
            # rate to make trade decisions."

            # Aggressive trading
            # v3.23.25 — Aggressive Trading redefined per operator
            # directive 2026-07-25: forces all engine-initiated orders
            # to execute as IOC-limit taker orders (immediate-or-cancel
            # limit priced through the spread). Manual fire is
            # unaffected. Runtime enforcement lives in scrumming_bot's
            # _execute_* paths; that wiring lands in Sub-phase 2D.
            self._aggressive = QCheckBox("Aggressive Trading (force IOC-limit takers)")
            self._aggressive.setChecked(cfg.aggressive_trading)
            self._aggressive.setToolTip(
                "When ON, every engine-initiated buy/sell executes as "
                "an Immediate-Or-Cancel limit order priced through the "
                "spread — i.e., pays the taker fee for immediate fill. "
                "When OFF, the bot may use passive maker orders where "
                "appropriate. Manual fire is unaffected by this flag.")
            self._aggressive.toggled.connect(
                lambda v: self._mark_changed("aggressive_trading", v))
            mf.addRow(self._aggressive)

            # v3.23.25 — Stack Mode (renamed from Bulk Trading).
            # Splits a SCRUM (sell) into N tranches spaced upward from
            # the Minimum Opposing Trade Distance (== scrumming_interval_pct
            # above the trigger price) per stack_spacing_mode at
            # split_distance intervals.
            self._stack_mode = QCheckBox("Stack Mode (split SCRUM across upward tranches)")
            self._stack_mode.setChecked(getattr(cfg, "stack_mode", False))
            self._stack_mode.setToolTip(
                "When ON, a SCRUM fires as N Stack Tranches at ascending "
                "price levels instead of a single sell. First tranche at "
                "the Minimum Opposing Trade Distance (opposing hysteresis "
                "level); successive tranches spaced by Split Distance per "
                "the Spacing model. See the Stack Tranches tab for live "
                "tranche state (added Sub-phase 2E). Visibility gates "
                "book placement: orderbook = resting limits; internal = "
                "tracked off-books, market-fire on threshold cross.")
            self._stack_mode.toggled.connect(
                lambda v: self._mark_changed("stack_mode", v))
            mf.addRow(self._stack_mode)

            # v3.23.25 — Split Distance (percent between tranches).
            self._split_distance = QDoubleSpinBox()
            self._split_distance.setRange(0.1, 20.0)
            self._split_distance.setDecimals(2)
            self._split_distance.setSuffix(" %")
            self._split_distance.setValue(getattr(cfg, "split_distance", 1.0))
            self._split_distance.setToolTip(
                "Percent spacing between successive Stack tranches. "
                "Applied per stack_spacing_mode: Linear = constant "
                "delta, Logarithmic = arithmetically-growing delta, "
                "Exponential = geometrically-growing delta.")
            self._split_distance.valueChanged.connect(
                lambda v: self._mark_changed("split_distance", v))
            mf.addRow("Split Distance:", self._split_distance)

            # v3.23.25 — Target tranche count. Actual count at runtime
            # may be lower due to exchange min-order-size restrictions
            # or the 0.1% merge rule.
            self._stack_count = QSpinBox()
            self._stack_count.setRange(2, 20)
            self._stack_count.setValue(
                int(getattr(cfg, "stack_tranche_count_target", 3)))
            self._stack_count.setToolTip(
                "Target number of Stack tranches to create from a SCRUM. "
                "Actual runtime count may be lower if (a) per-tranche "
                "size falls below the exchange minimum order size, or "
                "(b) two computed tranche prices land within 0.1% of "
                "each other (then merged upwards).")
            self._stack_count.valueChanged.connect(
                lambda v: self._mark_changed("stack_tranche_count_target", v))
            mf.addRow("Tranche Count:", self._stack_count)

            # v3.23.26 — Spacing mode. Middle option renamed from
            # "Logarithmic" to "Quadratic" per operator directive
            # 2026-07-25 for mathematical accuracy (Δp grows
            # arithmetically → tranche positions follow a triangular /
            # quadratic sequence).
            self._stack_spacing = QComboBox()
            self._stack_spacing.addItem("Linear (1, 2, 3, 4…)", "linear")
            self._stack_spacing.addItem("Quadratic (1, 2, 4, 7…)", "quadratic")
            self._stack_spacing.addItem("Exponential (1, 2, 4, 8…)", "exponential")
            _cur_spacing = getattr(cfg, "stack_spacing_mode", "linear")
            _idx = self._stack_spacing.findData(_cur_spacing)
            if _idx >= 0:
                self._stack_spacing.setCurrentIndex(_idx)
            self._stack_spacing.setToolTip(
                "Spacing model for successive Stack tranches. The "
                "sequences show Δp in units of Split Distance between "
                "consecutive tranches.")
            self._stack_spacing.currentIndexChanged.connect(
                lambda: self._mark_changed(
                    "stack_spacing_mode", self._stack_spacing.currentData()))
            mf.addRow("Spacing:", self._stack_spacing)

            # v3.23.42 — F65 personal_hold_qty. Live-editable — the
            # bot re-computes its registry reservation on the next
            # tick using the new value.
            self._personal_hold_qty = QDoubleSpinBox()
            self._personal_hold_qty.setRange(0.0, 1_000_000_000.0)
            self._personal_hold_qty.setDecimals(10)
            self._personal_hold_qty.setValue(float(getattr(
                cfg, "personal_hold_qty", 0.0)))
            self._personal_hold_qty.setToolTip(
                "Target-asset units to hold OUT of the bot's view "
                "(personal reserve). The bot won't buy or sell these "
                "units; they're also reserved from any sibling bot on "
                "the same asset via the CapitalReservationRegistry.")
            self._personal_hold_qty.valueChanged.connect(
                lambda v: self._mark_changed(
                    "personal_hold_qty", float(v)))
            mf.addRow("Personal Hold (units):", self._personal_hold_qty)

            layout.addWidget(mode_group)

            # v3.20.4 — Grid Settings + Profit Folding (grid) groups
            # removed. grid_bot deleted v3.16.0; this UI was unreachable
            # since BotMode.GRID was dropped from the enum.

            # --- Scrumming-specific ---
            #
            # v3.24.87 — `scrum_group` and `sf` were bound INSIDE
            # `if is_scrumming:` and then read unconditionally from the
            # compounding surface below all the way to
            # `layout.addWidget(scrum_group)`. `_create_settings_tab` is
            # called for EVERY bot mode (the Settings tab is added with
            # no mode test), and `BotMode.EXTRACTOR` is live and
            # constructible, so opening this dialog on an Extractor bot
            # raised NameError on the first `sf.addRow` — the operator
            # got a traceback instead of a Settings tab.
            #
            # Binding both before the branch. The scrumming path is
            # unchanged: same group, same rows, same order. The title is
            # the one thing that must not lie on the non-scrumming path,
            # since those shared rows are not scrumming settings.
            scrum_group = QGroupBox(
                "Scrumming Settings" if is_scrumming
                else "Trading Parameters (continued)")
            sf = QFormLayout(scrum_group)
            self._configure_form(sf)

            if is_scrumming:
                self._scrum_interval = QDoubleSpinBox()
                self._scrum_interval.setRange(0.1, 20.0)
                self._scrum_interval.setDecimals(2)
                self._scrum_interval.setSuffix(" %")
                self._scrum_interval.setValue(cfg.scrumming_interval_pct)
                self._scrum_interval.valueChanged.connect(
                    lambda v: self._mark_changed("scrumming_interval_pct", v))
                # v3.15.53 — operator directive 2026-04-25: rename
                # "Scrumming Interval" → "Opposing Trade Interval" in
                # the GUI. Underlying config field name unchanged
                # (scrumming_interval_pct) to avoid a wide refactor.
                sf.addRow("Opposing Trade Interval:", self._scrum_interval)

                self._bb_tol = QDoubleSpinBox()
                self._bb_tol.setRange(0.25, 5.0)
                self._bb_tol.setDecimals(2)
                self._bb_tol.setSuffix(" %")
                self._bb_tol.setValue(cfg.bb_tolerance_pct)
                self._bb_tol.valueChanged.connect(
                    lambda v: self._mark_changed("bb_tolerance_pct", v))
                sf.addRow("BB Tolerance:", self._bb_tol)

                self._landing = QSpinBox()
                self._landing.setRange(2, 10)
                self._landing.setValue(cfg.bb_landing_strip_candles)
                self._landing.valueChanged.connect(
                    lambda v: self._mark_changed("bb_landing_strip_candles", v))
                sf.addRow("Landing Strip Candles:", self._landing)

                # v3.15.61 — filter TF list to what the bot's exchange
                # actually supports. Coinbase has no 4h, 12h, 1w, etc.
                self._ta_tf = QComboBox()
                try:
                    from ..exchange.timeframes import available_timeframes
                    _ex_id = getattr(cfg, "exchange_id", None)
                    _allowed_tfs = available_timeframes(_ex_id)
                except Exception:
                    _allowed_tfs = ("1m", "5m", "15m", "30m", "1h",
                                    "2h", "4h", "6h", "12h", "1d")
                for tf in _allowed_tfs:
                    self._ta_tf.addItem(tf)
                idx = self._ta_tf.findText(cfg.ta_timeframe)
                if idx >= 0:
                    self._ta_tf.setCurrentIndex(idx)
                else:
                    # Operator's saved TF is no longer supported on this
                    # exchange — fall back to 1h or first.
                    fallback_idx = self._ta_tf.findText("1h")
                    if fallback_idx < 0:
                        fallback_idx = 0
                    self._ta_tf.setCurrentIndex(fallback_idx)
                self._ta_tf.setToolTip(
                    "TA Timeframe — filtered to granularities supported "
                    "by this bot's exchange. v3.15.61.")
                self._ta_tf.currentTextChanged.connect(
                    lambda v: self._mark_changed("ta_timeframe", v))
                sf.addRow("TA Timeframe:", self._ta_tf)

                self._target_bal = QDoubleSpinBox()
                self._target_bal.setRange(1.0, 1000000.0)
                self._target_bal.setDecimals(2)
                self._target_bal.setPrefix("$ ")
                self._target_bal.setValue(cfg.target_balance)
                self._target_bal.setToolTip(
                    "The balance this bot trades relative to. HARD-CAPPED: "
                    "position can never exceed Target × (1 + Max Target Growth %/100). "
                    "MEM-246/249/251.")
                self._target_bal.valueChanged.connect(
                    lambda v: self._mark_changed("target_balance", v))
                sf.addRow("Target Balance:", self._target_bal)

            # v3.24.50 (Phase 1 Step 3) — the compounding surface.
            #
            # HAZARD, honoured deliberately: the spinbox above keeps
            # showing `cfg.target_balance` and is NOT repointed at the
            # grown value. The change-detector diffs edits against
            # `cfg.target_balance`, so a spinbox holding a different
            # number would register as an operator edit on every panel
            # open and could fire `set_target_balance_live`, which
            # collapses the anchor and wipes accrued growth. The spinbox
            # is the operator's INPUT; the grown value goes in the
            # read-only rows below.
            _live_tb = float(getattr(self._bot, "_target_balance", 0.0) or 0.0)
            _anchor_tb = float(getattr(
                self._bot, "_anchor_target_balance", 0.0) or 0.0)
            _accrued = _live_tb - _anchor_tb
            _live_lbl = QLabel(
                f"${_live_tb:,.4f}   (anchor ${_anchor_tb:,.2f}, "
                f"accrued {_accrued:+,.4f})")
            if abs(_accrued) < 1e-9:
                # Zero accrual is the condition the whole tranche repair
                # exists to change. Say so rather than showing a bare 0.
                _live_lbl.setText(
                    f"${_live_tb:,.4f}   (anchor ${_anchor_tb:,.2f} — "
                    f"never compounded)")
                _live_lbl.setStyleSheet("color: #ff9900;")
            else:
                _live_lbl.setStyleSheet("color: #00ff88;")
            _live_lbl.setToolTip(
                "The target the bot actually trades against.\n\n"
                "The spinbox above is your input value and does not "
                "move when compounding grows the target. This row is "
                "the runtime figure.")
            sf.addRow("Live target (traded against):", _live_lbl)

            _surplus = float(getattr(
                self._bot, "_standing_surplus_usd", 0.0) or 0.0)
            _surplus_lbl = QLabel(f"${_surplus:,.4f}")
            if _surplus > 1e-9:
                _surplus_lbl.setStyleSheet("color: #ff9900;")
                _surplus_lbl.setToolTip(
                    "Surplus parked above the per-cycle growth cap.\n\n"
                    "There is currently NO drain from this pool — it "
                    "accrues and stays. Implementing the drain is "
                    "Phase 2 of the tranche repair.")
            sf.addRow("Standing surplus:", _surplus_lbl)

            # Issue #106 - was `_anchor_tb * pct / 100`, the frozen
            # input value. The bot bounds each Fold with
            # `cycle_growth_cap_usd`, whose base is the grown target, so
            # this row and the "Over-cap tranches" row below it both
            # used to describe a budget the bot had stopped using. Read
            # the property rather than respelling it.
            _budget = round(float(getattr(
                self._bot, "cycle_growth_cap_usd", 0.0) or 0.0), 8)
            _consumed = float(getattr(
                self._bot, "_fold_cycle_cap_consumed", 0.0) or 0.0)
            sf.addRow(
                "Cycle growth budget:",
                QLabel(f"${_budget:,.4f} — consumed ${_consumed:,.4f}"))

            # Tranches larger than the whole budget can never be admitted:
            # the filter takes a tranche only if it fits ENTIRELY.
            _tranches = list(getattr(self._bot, "_fold_tranches", []) or [])
            _over = [float(t.get("usd", 0) or 0) for t in _tranches
                     if isinstance(t, dict)
                     and _budget > 0
                     and float(t.get("usd", 0) or 0) > _budget]
            if _over:
                _over_lbl = QLabel(
                    f"{len(_over)} of {len(_tranches)} "
                    f"(${sum(_over):,.4f})")
                _over_lbl.setStyleSheet("color: #ff3366;")
                _over_lbl.setToolTip(
                    "Tranches larger than the entire per-cycle budget.\n\n"
                    "The fold filter admits a tranche only if it fits "
                    "whole and refuses to deploy part of one, so these "
                    "are skipped on every cycle regardless of price.")
                sf.addRow("Over-cap tranches:", _over_lbl)
            # v3.24.86 - DE-INDENTED OUT OF `if _over:`.
            #
            # The `if _over:` branch above reports fold tranches larger
            # than the whole per-cycle budget. Its body was meant to be
            # the two statements that build and add `_over_lbl`. Instead
            # it had swallowed 287 statements -- every settings group
            # from here to the end of the scrumming section:
            #   Scrumming Settings, Advanced Scrumming, Hedge, Circuit
            #   Breakers, Self-Destruct, Risk, Gates, Routing.
            #
            # Those groups were still CONSTRUCTED, then added to the
            # layout only when `_over` was non-empty -- i.e. only for a
            # bot holding an over-cap fold tranche. A brand-new bot has
            # no tranches at all, so `_over` is empty and the operator
            # saw Trading Parameters followed by nothing.
            #
            # Operator report 2026-08-09: BICO/USDC and IMU/USDC, both
            # created that day, showed no scrumming settings while
            # AERO/USDC showed them in full. Both are USDC pairs, so the
            # base currency was never the discriminator -- having traded
            # was.

            # v3.23.48 — cross-pair denomination rows. Per operator
            # directive 2026-07-28: show the target's equivalent in
            # BTC + ETH plus Δ24h vs USD % so cross-pair divergence
            # is visible at a glance. Rows are read-only and hidden
            # when the pair isn't listed on the exchange OR when
            # the target asset IS BTC/ETH itself (self-reference
            # meaningless). Data comes from MarketPairsScout +
            # CurrencyRateMonitor; refreshes every 5 s via QTimer.
            self._target_btc_lbl = QLabel("—")
            self._target_btc_lbl.setToolTip(
                "Target USD ÷ (BTC/USD spot). Δ24h vs USD = "
                "pct_24h(<target>/BTC) − pct_24h(<target>/USD). "
                "Positive Δ means BTC-quoted pair is cheaper in "
                "USD terms than the USD-quoted pair right now.")
            self._target_btc_row_label = QLabel("Target BTC:")
            sf.addRow(self._target_btc_row_label, self._target_btc_lbl)
            self._target_eth_lbl = QLabel("—")
            self._target_eth_lbl.setToolTip(
                "Target USD ÷ (ETH/USD spot). Δ24h vs USD = "
                "pct_24h(<target>/ETH) − pct_24h(<target>/USD). "
                "Positive Δ means ETH-quoted pair is cheaper in "
                "USD terms than the USD-quoted pair right now.")
            self._target_eth_row_label = QLabel("Target ETH:")
            sf.addRow(self._target_eth_row_label, self._target_eth_lbl)
            self._refresh_target_denom_rows()
            try:
                from PySide6.QtCore import QTimer as _QTimer
                self._denom_refresh_timer = _QTimer(self)
                self._denom_refresh_timer.setInterval(5_000)
                self._denom_refresh_timer.timeout.connect(
                    self._refresh_target_denom_rows)
                self._denom_refresh_timer.start()
            except Exception as _tmr_exc:  # noqa: BLE001 - timer setup best-effort
                logger.debug(
                    "denom-row refresh timer failed to start: %s",
                    _tmr_exc)

            # v3.15.51 — Operator-set entry-price bounds.
            # Operator directive 2026-04-25: "Bot max / min entry
            # price should be able to be set by user." 0.0 in either
            # field means "no bound" (matches BotConfig default of
            # None — UI emits float, _apply_changes maps 0→None).
            self._max_entry_px = QDoubleSpinBox()
            self._max_entry_px.setRange(0.0, 10_000_000.0)
            self._max_entry_px.setDecimals(8)
            self._max_entry_px.setPrefix("$ ")
            _max_ep_cfg = getattr(cfg, "max_entry_price", None)
            self._max_entry_px.setValue(
                float(_max_ep_cfg) if _max_ep_cfg else 0.0)
            self._max_entry_px.setToolTip(
                "Bot REFUSES any auto-buy when current price is ABOVE "
                "this. Use to cap entry exposure at known overvaluation. "
                "0 = no ceiling (default). Manual Fire bypasses this gate.")
            self._max_entry_px.valueChanged.connect(
                lambda v: self._mark_changed(
                    "max_entry_price", float(v) if v > 0 else None))
            sf.addRow("Max Entry Price:", self._max_entry_px)

            self._min_entry_px = QDoubleSpinBox()
            self._min_entry_px.setRange(0.0, 10_000_000.0)
            self._min_entry_px.setDecimals(8)
            self._min_entry_px.setPrefix("$ ")
            _min_ep_cfg = getattr(cfg, "min_entry_price", None)
            self._min_entry_px.setValue(
                float(_min_ep_cfg) if _min_ep_cfg else 0.0)
            self._min_entry_px.setToolTip(
                "Bot REFUSES any auto-buy when current price is BELOW "
                "this. Use to avoid catching a falling knife. 0 = no "
                "floor (default). Manual Fire bypasses this gate.")
            self._min_entry_px.valueChanged.connect(
                lambda v: self._mark_changed(
                    "min_entry_price", float(v) if v > 0 else None))
            sf.addRow("Min Entry Price:", self._min_entry_px)

            # v3.15.52 — Trading fee tier (Coinbase). Operator
            # directive 2026-04-25: "total scrum interval will now
            # be the setting plus trading fees ... default at 0.6%."
            # Used by the opposite-direction hysteresis safety:
            # effective deviation threshold = scrumming_interval_pct
            # + trading_fee_pct.
            self._trading_fee = QDoubleSpinBox()
            self._trading_fee.setRange(0.0, 5.0)
            self._trading_fee.setSuffix("%")
            self._trading_fee.setDecimals(2)
            self._trading_fee.setSingleStep(0.05)
            self._trading_fee.setValue(
                float(getattr(cfg, "trading_fee_pct", 0.6) or 0.6))
            self._trading_fee.setToolTip(
                "Coinbase trading fee tier (per side). The opposite-"
                "direction hysteresis safety adds this to the scrum "
                "interval — bot will not flip BUY↔SELL until price "
                "moves ≥ (interval + fee)% in the opposing direction. "
                "0.6% = Coinbase Advanced Trade max-tier default. "
                "Lower this if you're on a discounted tier.")
            self._trading_fee.valueChanged.connect(
                lambda v: self._mark_changed("trading_fee_pct", float(v)))
            sf.addRow("Trading Fee %:", self._trading_fee)

            # MEM-252 — Max Target Growth % feature-parity with wizard.
            # ONLY mechanism that may grow the effective target ceiling via
            # fold surplus. Identical widget shape as bot_wizard.py.
            self._max_target_growth = QDoubleSpinBox()
            self._max_target_growth.setRange(0.0, 100.0)
            self._max_target_growth.setSuffix("%")
            self._max_target_growth.setDecimals(2)
            self._max_target_growth.setSingleStep(0.25)
            self._max_target_growth.setValue(
                float(getattr(cfg, "max_target_growth_pct", 1.0)))
            self._max_target_growth.setToolTip(
                "Per-event cap on how much a fold surplus may grow Target Balance.\n"
                "Absolute ceiling = Target × (1 + this%/100). Default 1%.\n"
                "THIS IS THE ONLY MECHANISM ALLOWED TO INCREASE TARGET BALANCE.\n"
                "Set to 0% to freeze Target Balance entirely (no growth at all)."
            )
            self._max_target_growth.valueChanged.connect(
                lambda v: self._mark_changed("max_target_growth_pct", v))
            sf.addRow("Max Target Growth %:", self._max_target_growth)

            # v3.23.34 — wizard-parity add: profit_folding_active.
            # The ONLY consumer that grows the effective target via
            # fold surplus (routes through _apply_fold_target_growth,
            # v3.23.30 Option B). Off = target frozen at anchor.
            self._profit_folding_active = QCheckBox(
                "Profit Folding Active")
            self._profit_folding_active.setChecked(bool(getattr(
                cfg, "profit_folding_active", True)))
            self._profit_folding_active.setToolTip(
                "When ON, fold surplus grows the effective target "
                "balance via the compounding drain (subject to Max "
                "Target Growth % cap). OFF freezes target at anchor "
                "regardless of fold profit. Wizard parity: matches "
                "the dedicated Profit Folding page at bot creation.")
            self._profit_folding_active.toggled.connect(
                lambda v: self._mark_changed(
                    "profit_folding_active", v))
            sf.addRow(self._profit_folding_active)

            layout.addWidget(scrum_group)

            # --- Advanced (P1.9 parity with wizard) ---
            # MEM-232: these fields existed on BotConfig since v3.13.8 but
            # were not exposed in the live-settings dialog. Adding them
            # here closes the parity gap between wizard and live dialog.
            adv_group = QGroupBox("Advanced Scrumming (P1.9)")
            af = QFormLayout(adv_group)
            self._configure_form(af)

            self._detect_pct = QSpinBox()
            self._detect_pct.setRange(10, 90)
            self._detect_pct.setSuffix(" %")
            self._detect_pct.setValue(int(cfg.scrum_detect_pct))
            self._detect_pct.setToolTip(
                "BB DETECT threshold: % distance from BB midline to "
                "band before SEARCH→TRACK. Lower = earlier detection. "
                "v3.15.57 — also defines the HARD GATE: SCRUM cannot "
                "occur below the Upper BB Detection Threshold; FOLD "
                "cannot occur above the Lower BB Detection Threshold. "
                "75% → upper gate at bb_pos≥0.875, lower gate at "
                "bb_pos≤0.125. Live-editable.")
            self._detect_pct.valueChanged.connect(
                lambda v: self._mark_changed("scrum_detect_pct", v))
            af.addRow("Detect Threshold:", self._detect_pct)

            self._fire_pct = QDoubleSpinBox()
            self._fire_pct.setRange(0.1, 10.0)
            self._fire_pct.setDecimals(2)
            self._fire_pct.setSuffix(" %")
            self._fire_pct.setValue(float(cfg.scrum_fire_pct))
            self._fire_pct.setToolTip(
                "FIRE threshold: % distance from BB band to trigger trade.")
            self._fire_pct.valueChanged.connect(
                lambda v: self._mark_changed("scrum_fire_pct", v))
            af.addRow("Fire Threshold:", self._fire_pct)

            self._midline_gate = QCheckBox("BB Midline Gate")
            self._midline_gate.setChecked(bool(cfg.bb_midline_gate))
            self._midline_gate.setToolTip(
                "When enabled: scrums ONLY fire above BB midline,\n"
                "folds ONLY fire below midline (sell-high/buy-low).")
            self._midline_gate.toggled.connect(
                lambda v: self._mark_changed("bb_midline_gate", v))
            af.addRow(self._midline_gate)

            self._read_rate = QSpinBox()
            self._read_rate.setRange(1, 60)
            self._read_rate.setSuffix(" min")
            self._read_rate.setValue(int(cfg.scrum_read_rate_min))
            self._read_rate.setToolTip(
                "SEARCH-mode read rate in minutes. TRACK mode reads 10x faster.")
            self._read_rate.valueChanged.connect(
                lambda v: self._mark_changed("scrum_read_rate_min", v))
            af.addRow("Read Rate:", self._read_rate)

            self._band_travel = QSpinBox()
            self._band_travel.setRange(0, 100)
            self._band_travel.setSuffix(" %")
            self._band_travel.setValue(int(cfg.band_travel_pct))
            self._band_travel.setToolTip(
                "Secondary harvest trigger: % of BB band width price must "
                "travel since last fold. 0 disables.")
            self._band_travel.valueChanged.connect(
                lambda v: self._mark_changed("band_travel_pct", v))
            af.addRow("Band Travel:", self._band_travel)

            self._bullseye = QCheckBox("BB Bullseye Check")
            self._bullseye.setChecked(bool(cfg.bb_bullseye_check))
            self._bullseye.setToolTip(
                "Rapid Fire override when price touches BB band within 0.5% "
                "(or the candle wick reaches within 0.2%).\n"
                "When triggered, bypasses the fire threshold — bullseye "
                "alone can arm a fire, subject to midline gate.")
            self._bullseye.toggled.connect(
                lambda v: self._mark_changed("bb_bullseye_check", v))
            af.addRow(self._bullseye)

            # MEM-234 — Scrum Fold Ratio (wizard parity).
            self._scrum_fold_pct = QSpinBox()
            self._scrum_fold_pct.setRange(1, 100)
            self._scrum_fold_pct.setSuffix(" %")
            self._scrum_fold_pct.setValue(int(
                getattr(cfg, "scrum_fold_pct", 100)))
            self._scrum_fold_pct.setToolTip(
                "% of scrum sale proceeds queued for fold (rebuy).\n"
                "100% = full reentry (max accumulation, max risk).\n"
                "Lower values preserve cash buffer — safer when\n"
                "price keeps falling after the scrum.")
            self._scrum_fold_pct.valueChanged.connect(
                lambda v: self._mark_changed("scrum_fold_pct", v))
            af.addRow("Scrum Fold Ratio:", self._scrum_fold_pct)

            # Item 9 (2026-08-13) — Tranche Despawn Timer. DESPAWNS
            # aged tranches from both ledgers, from this one control.
            # Whole days, the unit the Fold Tranches panel already
            # reports ages in. 0 shows as "Off" and is the default.
            #
            # issue #103 — THE DEFAULT STAYS 0, and that is a measured
            # decision rather than an omission. All 38 live bots store
            # `tranche_despawn_days` EXPLICITLY as 0, and the loader
            # reads the stored value (`bot_container.py:3687`), so
            # changing the dataclass default would not reach one bot on
            # this fleet. It would only arm the timer on bots created
            # afterwards, silently, on records their operator never
            # opted in for. What was actually missing is a surface that
            # says the setting exists and what it would cost; that is
            # now on the Fold Tranches tab, where the tranche count the
            # operator worries about already is.
            #
            # THE SEED IS READ THROUGH THE CONSUMER'S OWN RULE.
            # `despawn_threshold_days` is the function the sweep calls,
            # so this control cannot display a number the bot would not
            # act on. It also refuses a non-finite stored value, which
            # matters here and not only in the bot: reading the field
            # raw would put `int(float("nan"))` — a ValueError — in the
            # middle of building the Settings tab, and the operator
            # would get a traceback instead of a dialog.
            #
            # setValue BEFORE valueChanged is connected, so seeding the
            # control does not register as an operator edit.
            from ..trading.bot_container import despawn_threshold_days
            self._tranche_despawn_days = QSpinBox()
            self._tranche_despawn_days.setRange(0, 365)
            self._tranche_despawn_days.setSuffix(" days")
            self._tranche_despawn_days.setSpecialValueText("Off")
            self._tranche_despawn_days.setValue(
                despawn_threshold_days(cfg))
            self._tranche_despawn_days.setToolTip(
                "DESPAWN any tranche this old - both fold tranches\n"
                "and stack tranches, from this one setting. 0 = Off\n"
                "(default).\n\n"
                "MERGE, DESPAWN and CLEAR are the only three things\n"
                "that collapse or remove a tranche. This is despawn:\n"
                "the age-driven one.\n\n"
                "IT IS NOT A TRADE. No order is placed or cancelled,\n"
                "no balance moves, holdings and cost basis are\n"
                "untouched. The record goes.\n\n"
                "WHAT THE RECORD HELD: the tranche's ref price, its\n"
                "parked fold USD, its units, and its initial_buy_price\n"
                "(the MEM-171 provenance figure). The scrum sale that\n"
                "made it already happened, so those dollars are\n"
                "already in the wallet - the record was only the\n"
                "queued intent to buy the units back. A despawned\n"
                "tranche can no longer fold back, so that money goes\n"
                "from queued rebuy to ordinary spendable balance.\n\n"
                "A tranche is despawned at exactly this age or older.\n"
                "A tranche with no timestamp is NEVER despawned, and\n"
                "a stack tranche holding a resting exchange order is\n"
                "kept until that order settles.\n\n"
                "SEE THE COUNT FIRST: the Fold Tranches tab prints how\n"
                "many of this bot's tranches each candidate window\n"
                "would remove, and what they hold.")
            self._tranche_despawn_days.valueChanged.connect(
                lambda v: self._mark_changed("tranche_despawn_days", v))
            af.addRow("Tranche Despawn Timer:",
                      self._tranche_despawn_days)

            # v3.23.34 — wizard-parity add: wire_inflow_stack_pct.
            self._wire_inflow_stack_pct = QDoubleSpinBox()
            self._wire_inflow_stack_pct.setRange(0.0, 100.0)
            self._wire_inflow_stack_pct.setDecimals(2)
            self._wire_inflow_stack_pct.setSuffix(" %")
            self._wire_inflow_stack_pct.setValue(float(getattr(
                cfg, "wire_inflow_stack_pct", 1.0)))
            self._wire_inflow_stack_pct.setToolTip(
                "Wire inflow stacking percentage. Controls how "
                "aggressively the bot stacks new buy-side positions "
                "when fresh wire-inflow signals arrive. Default 1.0%; "
                "rarely adjusted in practice.")
            self._wire_inflow_stack_pct.valueChanged.connect(
                lambda v: self._mark_changed(
                    "wire_inflow_stack_pct", float(v)))
            af.addRow("Wire Inflow Stack:", self._wire_inflow_stack_pct)

            layout.addWidget(adv_group)

            # --- Hedge Rebalance ---
            hedge_group = QGroupBox("Hedge Rebalance")
            hf = QFormLayout(hedge_group)
            self._configure_form(hf)

            self._hedge_active = QCheckBox("Hedge Rebalance Active")
            self._hedge_active.setChecked(bool(cfg.hedge_rebalance_active))
            self._hedge_active.setToolTip(
                "Separate USD reserve for buying on sharp drawdowns.\n"
                "NOT taken from Target Balance.")
            self._hedge_active.toggled.connect(
                lambda v: self._mark_changed("hedge_rebalance_active", v))
            hf.addRow(self._hedge_active)

            self._hedge_balance = QDoubleSpinBox()
            self._hedge_balance.setRange(0.0, 999999999.0)
            self._hedge_balance.setDecimals(2)
            self._hedge_balance.setPrefix("$ ")
            self._hedge_balance.setValue(float(cfg.hedge_balance))
            self._hedge_balance.setToolTip(
                "USD reserve amount for hedge rebalancing (separate from "
                "Target Balance).")
            self._hedge_balance.valueChanged.connect(
                lambda v: self._mark_changed("hedge_balance", v))
            hf.addRow("Hedge Balance:", self._hedge_balance)

            layout.addWidget(hedge_group)

            # v3.15.58 — Circuit Breakers (operator directive 2026-04-25)
            cb_group = QGroupBox("Circuit Breakers (v3.15.58)")
            cf = QFormLayout(cb_group)
            self._configure_form(cf)

            self._cb_soft_pct = QDoubleSpinBox()
            self._cb_soft_pct.setRange(0.0, 100.0)
            self._cb_soft_pct.setDecimals(1)
            self._cb_soft_pct.setSuffix(" %")
            self._cb_soft_pct.setValue(float(getattr(
                cfg, "circuit_breaker_soft_pct", 25.0)))
            self._cb_soft_pct.setToolTip(
                "SOFT Circuit Breaker threshold. Single-candle move ≥ "
                "this % interrupts the side of the market that just "
                "moved (UP→SCRUM, DOWN→FOLD). Re-opens after cooldown "
                "candles. Default 25%. Set 0 to disable.")
            self._cb_soft_pct.valueChanged.connect(
                lambda v: self._mark_changed(
                    "circuit_breaker_soft_pct", float(v)))
            cf.addRow("Soft CB Threshold:", self._cb_soft_pct)

            self._cb_hard_pct = QDoubleSpinBox()
            self._cb_hard_pct.setRange(0.0, 100.0)
            self._cb_hard_pct.setDecimals(1)
            self._cb_hard_pct.setSuffix(" %")
            self._cb_hard_pct.setValue(float(getattr(
                cfg, "circuit_breaker_hard_pct", 35.0)))
            self._cb_hard_pct.setToolTip(
                "HARD Circuit Breaker threshold. Single-candle move ≥ "
                "this % PAUSES the bot. Operator reset required to "
                "resume. Persists across restart. Default 35%. Set 0 "
                "to disable.")
            self._cb_hard_pct.valueChanged.connect(
                lambda v: self._mark_changed(
                    "circuit_breaker_hard_pct", float(v)))
            cf.addRow("Hard CB Threshold:", self._cb_hard_pct)

            self._cb_cooldown = QSpinBox()
            self._cb_cooldown.setRange(1, 100)
            self._cb_cooldown.setValue(int(getattr(
                cfg, "circuit_breaker_cooldown_candles", 3)))
            self._cb_cooldown.setToolTip(
                "Number of candles the soft breaker stays active "
                "before re-opening. Default 3.")
            self._cb_cooldown.valueChanged.connect(
                lambda v: self._mark_changed(
                    "circuit_breaker_cooldown_candles", int(v)))
            cf.addRow("Soft CB Cooldown:", self._cb_cooldown)

            # v3.15.63 — Maximum Cartridge Size
            self._max_cartridge_pct = QDoubleSpinBox()
            self._max_cartridge_pct.setRange(0.0, 200.0)
            self._max_cartridge_pct.setDecimals(1)
            self._max_cartridge_pct.setSuffix(" %")
            self._max_cartridge_pct.setValue(float(getattr(
                cfg, "max_cartridge_size_pct", 10.0)))
            self._max_cartridge_pct.setToolTip(
                "Maximum |Target Delta| as % of Target Balance. "
                "When the position drifts beyond this %, the bot "
                "fires an immediate aggressive rebalance "
                "(bypasses BB Detection / hysteresis / soft CB / "
                "higher-TF bias). Default 10%. Set 0 to disable. "
                "v3.15.63.")
            self._max_cartridge_pct.valueChanged.connect(
                lambda v: self._mark_changed(
                    "max_cartridge_size_pct", float(v)))
            cf.addRow("Max Cartridge Size:", self._max_cartridge_pct)

            # v3.15.92 — Smart Cartridge calibration
            self._cartridge_smart_chk = QCheckBox(
                "Calibrate to BB range")
            self._cartridge_smart_chk.setChecked(bool(getattr(
                cfg, "max_cartridge_smart", False)))
            self._cartridge_smart_chk.setToolTip(
                "When ON, Cartridge size is derived from current BB "
                "range rather than the static % above. Hard floor at "
                "the Opposing Trade Interval (cartridge cannot fire "
                "below the interval). Soft ceiling configured below. "
                "Default OFF preserves static behavior. v3.15.92.")
            self._cartridge_smart_chk.toggled.connect(
                lambda checked: self._mark_changed(
                    "max_cartridge_smart", bool(checked)))
            cf.addRow("Smart Cartridge:", self._cartridge_smart_chk)

            self._cartridge_smart_ceiling = QDoubleSpinBox()
            self._cartridge_smart_ceiling.setRange(1.0, 100.0)
            self._cartridge_smart_ceiling.setDecimals(1)
            self._cartridge_smart_ceiling.setSuffix(" %")
            self._cartridge_smart_ceiling.setValue(float(getattr(
                cfg, "max_cartridge_smart_ceiling_pct", 30.0)))
            self._cartridge_smart_ceiling.setToolTip(
                "Maximum effective cartridge threshold under Smart "
                "calibration. Prevents cartridge from being "
                "effectively disabled during volatility expansion. "
                "Only applies when Smart Cartridge is ON. "
                "Default 30%. v3.15.92.")
            self._cartridge_smart_ceiling.valueChanged.connect(
                lambda v: self._mark_changed(
                    "max_cartridge_smart_ceiling_pct", float(v)))
            cf.addRow("Smart Ceiling:", self._cartridge_smart_ceiling)

            # Operator-initiated reset button.
            # NOTE: QPushButton + QHBoxLayout are already imported
            # at module top from PySide6.QtWidgets. The previous
            # version had a stray PyQt5 import here which broke
            # the entire dialog construction (operator-reported
            # "bot details button broken"). Fixed v3.15.60.
            reset_row = QHBoxLayout()
            self._cb_reset_all_btn = QPushButton("Reset All Breakers")
            self._cb_reset_all_btn.setToolTip(
                "Operator override: clears any active soft and hard "
                "circuit breakers. Hard reset also resumes the bot if "
                "it is PAUSED.")
            def _on_cb_reset_all():
                orig = self._cb_reset_all_btn.text()
                status = "Reset failed"
                if hasattr(self._bot, "reset_circuit_breaker"):
                    try:
                        result = self._bot.reset_circuit_breaker("all")
                        applied = (result.get("applied", [])
                                   if isinstance(result, dict) else [])
                        status = ("Reset applied"
                                  if applied else "Nothing to reset")
                    except Exception as _reset_exc:  # noqa: BLE001 - status-flash best-effort
                        logger.debug(
                            "reset_circuit_breaker raised: %s",
                            _reset_exc)
                self._cb_reset_all_btn.setText(status)
                from PySide6.QtCore import QTimer as _QTimer
                _QTimer.singleShot(
                    2000, lambda: self._cb_reset_all_btn.setText(orig))
            self._cb_reset_all_btn.clicked.connect(_on_cb_reset_all)
            reset_row.addWidget(self._cb_reset_all_btn)
            cf.addRow(reset_row)

            layout.addWidget(cb_group)

            # v3.15.62 — SELF-DESTRUCT button (operator directive
            # 2026-04-26: "Bots will now have a self-destruct button
            # under the details panel. This will aggressively exit
            # the entire position when activated.").
            #
            # Styled distinct from other buttons (red border, red
            # text) so misclick risk is minimized. Confirmation
            # dialog requires operator to type SELF-DESTRUCT
            # literally before the action fires.
            sd_group = QGroupBox("DANGER ZONE — Self-Destruct (v3.15.62)")
            sd_group.setStyleSheet(
                "QGroupBox{border:1px solid #ff3366;color:#ff3366;}"
                "QGroupBox::title{color:#ff3366;font-weight:bold;}"
            )
            sdv = QVBoxLayout(sd_group)
            sd_hint = QLabel(
                "AGGRESSIVE FULL-POSITION EXIT. Market-sells the "
                "entire holdings of this bot's target asset and "
                "PAUSES the bot. State (lots, fold tranches) is "
                "cleared. Auto gates bypassed (operator override).\n\n"
                "Confirmation required.")
            sd_hint.setWordWrap(True)
            sd_hint.setStyleSheet("color:#aaa;font-size:10px;")
            sdv.addWidget(sd_hint)
            self._self_destruct_btn = QPushButton(
                "💥  SELF-DESTRUCT  💥")
            self._self_destruct_btn.setStyleSheet(
                "QPushButton{background:#440011;color:#ff3366;"
                "border:2px solid #ff3366;border-radius:4px;"
                "padding:8px 12px;font-weight:bold;}"
                "QPushButton:hover{background:#660022;color:#ffffff;}"
            )
            self._self_destruct_btn.setToolTip(
                "Aggressively exit the entire position. "
                "Confirmation required.")
            self._self_destruct_btn.clicked.connect(
                self._on_self_destruct_clicked)
            sdv.addWidget(self._self_destruct_btn)
            layout.addWidget(sd_group)

            # MEM-244 — Risk Controls group (Position Ceiling +
            # Detonation). Operator directive: "Make that a switch.
            # Institutions are going to want it for sure. 1x~10x
            # should be reasonable. Bot should detonate on 1D or
            # higher Timeframe on BULLISH condition detection."
            risk_group = QGroupBox("Risk Controls (MEM-244)")
            rf = QFormLayout(risk_group)
            self._configure_form(rf)

            self._ceiling_enabled = QCheckBox(
                "Enable Position Ceiling")
            self._ceiling_enabled.setChecked(
                bool(getattr(cfg, "position_ceiling_enabled", False)))
            self._ceiling_enabled.setToolTip(
                "Cap accumulation at Nx of the bot's INITIAL "
                "target_balance (stable anchor set at creation).\n"
                "Fold rate tapers 100% → 10% as value approaches "
                "ceiling (ratio 0.5 → 1.0), hard-stops at ceiling.\n"
                "Scrum always allowed. Protects against runaway "
                "accumulation on conviction plays.")
            self._ceiling_enabled.toggled.connect(
                lambda v: self._mark_changed(
                    "position_ceiling_enabled", v))
            rf.addRow(self._ceiling_enabled)

            self._ceiling_mult = QDoubleSpinBox()
            self._ceiling_mult.setRange(1.0, 10.0)
            self._ceiling_mult.setDecimals(1)
            self._ceiling_mult.setSingleStep(0.5)
            self._ceiling_mult.setSuffix("x anchor")
            self._ceiling_mult.setValue(float(
                getattr(cfg, "position_ceiling_multiple", 5.0)))
            self._ceiling_mult.setToolTip(
                "Ceiling multiplier. 1x = no accumulation beyond "
                "anchor. 10x = 10x runway. Default 5x.")
            self._ceiling_mult.valueChanged.connect(
                lambda v: self._mark_changed(
                    "position_ceiling_multiple", v))
            rf.addRow("Ceiling Multiple:", self._ceiling_mult)

            self._deto_enabled = QCheckBox(
                "Enable Detonation (auto-harvest on bullish TF)")
            self._deto_enabled.setChecked(
                bool(getattr(cfg, "detonation_enabled", False)))
            self._deto_enabled.setToolTip(
                "Monitor a higher TF for BULLISH + high-confidence "
                "signal. Edge-triggered: fires ONCE per transition "
                "into bullish state.\n"
                "On trigger: MARKET sell everything above the anchor, "
                "then reset target_balance to anchor ('lock in' gains, "
                "re-accumulate from scratch).\n"
                "Rate-limited to 1 check/hour.\n"
                "Additional gate: fires only when current value is "
                "above the anchor — no harvest if the bot is below "
                "its initial anchor.")
            self._deto_enabled.toggled.connect(
                lambda v: self._mark_changed("detonation_enabled", v))
            rf.addRow(self._deto_enabled)

            self._deto_tf = QComboBox()
            self._deto_tf.addItems(["1d", "1w"])
            _cur_tf = getattr(cfg, "detonation_timeframe", "1d") or "1d"
            _idx = self._deto_tf.findText(_cur_tf)
            if _idx >= 0:
                self._deto_tf.setCurrentIndex(_idx)
            self._deto_tf.setToolTip(
                "Timeframe to monitor for bullish detonation signal. "
                "1D = daily, 1W = weekly. Higher = stronger conviction, "
                "fewer triggers.")
            self._deto_tf.currentTextChanged.connect(
                lambda v: self._mark_changed("detonation_timeframe", v))
            rf.addRow("Detonation TF:", self._deto_tf)

            self._deto_conf = QDoubleSpinBox()
            self._deto_conf.setRange(0.50, 1.00)
            self._deto_conf.setDecimals(2)
            self._deto_conf.setSingleStep(0.05)
            self._deto_conf.setValue(float(
                getattr(cfg, "detonation_confidence_min", 0.75)))
            self._deto_conf.setToolTip(
                "Minimum TA consensus confidence for detonation. "
                "Default 0.75 (high conviction only, per MEM-244).")
            self._deto_conf.valueChanged.connect(
                lambda v: self._mark_changed(
                    "detonation_confidence_min", v))
            rf.addRow("Min Confidence:", self._deto_conf)

            layout.addWidget(risk_group)

            # v3.23.34 — wizard-parity: Strategy Gate Flags group.
            # Operator picks Conservative (all ON, default) vs Lean
            # (all OFF, band-intersection harvesting). See v3.16.15
            # A/B battery — both profiles ~94.9% win rate; choice is
            # about which scenarios to optimize for.
            gates_group = QGroupBox("Strategy Gate Flags (v3.16.15)")
            gf = QFormLayout(gates_group)
            self._configure_form(gf)

            self._gate_scrum_ta = QCheckBox(
                "SCRUM requires bullish TA")
            self._gate_scrum_ta.setChecked(bool(getattr(
                cfg, "scrum_require_ta_bullish", True)))
            self._gate_scrum_ta.setToolTip(
                "ON (Conservative): scrum auto-fire requires TA "
                "consensus BULLISH. Protects against scrumming "
                "false tops. OFF (Lean): scrum fires at BB-upper + "
                "delta regardless of TA.")
            self._gate_scrum_ta.toggled.connect(
                lambda v: self._mark_changed(
                    "scrum_require_ta_bullish", v))
            gf.addRow(self._gate_scrum_ta)

            self._gate_scrum_uptrend = QCheckBox(
                "SCRUM holds in sustained uptrend")
            self._gate_scrum_uptrend.setChecked(bool(getattr(
                cfg, "scrum_hold_in_uptrend", True)))
            self._gate_scrum_uptrend.setToolTip(
                "ON (Conservative): if 65 %+ of last 20 candles "
                "were bullish, bot holds rather than scrumming "
                "each band touch. OFF (Lean): scrum every "
                "BB-upper touch regardless of trend strength.")
            self._gate_scrum_uptrend.toggled.connect(
                lambda v: self._mark_changed(
                    "scrum_hold_in_uptrend", v))
            gf.addRow(self._gate_scrum_uptrend)

            self._gate_scrum_htf = QCheckBox(
                "SCRUM defers to higher-TF bullish")
            self._gate_scrum_htf.setChecked(bool(getattr(
                cfg, "scrum_defer_to_htf", True)))
            self._gate_scrum_htf.setToolTip(
                "ON (Conservative): refuse scrum when a higher-TF "
                "phantom signals BULLISH. OFF (Lean): cartridge "
                "captures HTF swings organically; this gate is "
                "redundant if Smart Cartridge is ON.")
            self._gate_scrum_htf.toggled.connect(
                lambda v: self._mark_changed(
                    "scrum_defer_to_htf", v))
            gf.addRow(self._gate_scrum_htf)

            self._gate_fold_ta = QCheckBox(
                "FOLD requires bearish TA")
            self._gate_fold_ta.setChecked(bool(getattr(
                cfg, "fold_require_ta_bearish", True)))
            self._gate_fold_ta.setToolTip(
                "ON (Conservative): mirror of SCRUM TA gate on "
                "the fold side. OFF (Lean): fold fires at "
                "BB-lower + tranche-eligible regardless of TA.")
            self._gate_fold_ta.toggled.connect(
                lambda v: self._mark_changed(
                    "fold_require_ta_bearish", v))
            gf.addRow(self._gate_fold_ta)

            self._gate_fold_htf = QCheckBox(
                "FOLD defers to higher-TF bearish")
            self._gate_fold_htf.setChecked(bool(getattr(
                cfg, "fold_defer_to_htf", True)))
            self._gate_fold_htf.setToolTip(
                "ON (Conservative): mirror of SCRUM HTF gate on "
                "the fold side. OFF (Lean): fold fires regardless "
                "of higher-TF bearish bias.")
            self._gate_fold_htf.toggled.connect(
                lambda v: self._mark_changed(
                    "fold_defer_to_htf", v))
            gf.addRow(self._gate_fold_htf)

            layout.addWidget(gates_group)

            # v3.23.34 — wizard-parity: Profit Routing group.
            # Where realized profit flows on fold. fold_to_target =
            # compound; spendable = mark for withdrawal; split =
            # use fold % below; cross_bot = route to a target bot ID.
            routing_group = QGroupBox("Profit Routing (v3.20.85)")
            pr = QFormLayout(routing_group)
            self._configure_form(pr)

            self._profit_route = QComboBox()
            self._profit_route.addItem(
                "Fold back to target balance", "fold_to_target")
            self._profit_route.addItem(
                "Send to spendable", "spendable")
            self._profit_route.addItem(
                "Split fold/spendable per %", "split")
            self._profit_route.addItem(
                "Route to another bot (cross-bot)", "cross_bot")
            _cur_route = getattr(cfg, "profit_route", "fold_to_target")
            _r_idx = self._profit_route.findData(_cur_route)
            if _r_idx >= 0:
                self._profit_route.setCurrentIndex(_r_idx)
            self._profit_route.setToolTip(
                "Where realized profit flows on fold. "
                "fold_to_target = increase target balance "
                "(compound); spendable = mark for withdrawal; "
                "split = use fold % below; cross_bot = route to "
                "the target bot ID.")
            self._profit_route.currentIndexChanged.connect(
                lambda: self._mark_changed(
                    "profit_route", self._profit_route.currentData()))
            pr.addRow("Route:", self._profit_route)

            # profit_fold_pct intentionally omitted — schema field
            # retired v3.23.3 (see bot_container.py:629 deprecated
            # set); the wizard's matching widget is also dead. The
            # 'split' route uses profit_folding_active + max_target_
            # growth_pct upstream.

            self._profit_route_bot_id = QLineEdit()
            self._profit_route_bot_id.setText(str(getattr(
                cfg, "profit_route_bot_id", "") or ""))
            self._profit_route_bot_id.setPlaceholderText(
                "leave blank unless route = cross_bot")
            self._profit_route_bot_id.setToolTip(
                "Target bot ID for cross-bot profit routing. Only "
                "consulted when route = cross_bot. Leave blank "
                "otherwise.")
            self._profit_route_bot_id.editingFinished.connect(
                lambda: self._mark_changed(
                    "profit_route_bot_id",
                    self._profit_route_bot_id.text().strip()))
            pr.addRow("Target bot ID:", self._profit_route_bot_id)

            layout.addWidget(routing_group)

            # --- v3.19.28 — Extractor-specific live settings ---
            # Operator-reported gap (2026-05-22): Settings tab on a live
            # Extractor bot was showing ONLY the shared Trading Parameters
            # group (visibility / check_interval / aggressive / bulk).
            # The Extractor-specific knobs (chunk_size, artillery_size,
            # scan_top_n, exit_pct, etc.) were unreachable. The wizard
            # captures them at creation but operators couldn't tune them
            # after the bot was running. v3.19.28 mirrors the wizard's
            # _extractor_group widget set into the live settings dialog
            # so every Extractor parameter the wizard exposes is also
            # editable live.
            if cfg.mode.value == "extractor":
                ext_group = QGroupBox("Extractor — Pool & Artillery")
                ef = QFormLayout(ext_group)
                self._configure_form(ef)

                self._ext_chunk_size = QDoubleSpinBox()
                self._ext_chunk_size.setRange(10.0, 10_000_000.0)
                self._ext_chunk_size.setDecimals(2)
                self._ext_chunk_size.setPrefix("$")
                self._ext_chunk_size.setValue(
                    float(getattr(cfg, "extractor_chunk_size_usd", 100.0)))
                self._ext_chunk_size.setToolTip(
                    "USD-equivalent of base currency this bot owns. "
                    "Sized at construction; changing live re-anchors "
                    "the pool's reference USD value (not the held base "
                    "units — those are exchange-tracked).")
                self._ext_chunk_size.valueChanged.connect(
                    lambda v: self._mark_changed("extractor_chunk_size_usd", v))
                # v3.20.5 — operator-renamed "Chunk size" → "Pool size".
                # The internal config field name (`extractor_chunk_size_usd`)
                # stays — this is a label-only change for the operator's
                # UX. Same field, same semantic.
                ef.addRow("Pool size (USD):", self._ext_chunk_size)

                self._ext_artillery_size = QDoubleSpinBox()
                self._ext_artillery_size.setRange(0.5, 100_000.0)
                self._ext_artillery_size.setDecimals(2)
                self._ext_artillery_size.setPrefix("$")
                self._ext_artillery_size.setValue(
                    float(getattr(cfg, "extractor_artillery_size_usd", 5.0)))
                self._ext_artillery_size.setToolTip(
                    "USD-equivalent per artillery round. Smaller = more "
                    "opportunities; larger = bigger per-round impact.")
                self._ext_artillery_size.valueChanged.connect(
                    lambda v: self._mark_changed(
                        "extractor_artillery_size_usd", v))
                ef.addRow("Artillery size (USD):", self._ext_artillery_size)

                self._ext_scan_top_n = QSpinBox()
                self._ext_scan_top_n.setRange(5, 10)
                self._ext_scan_top_n.setValue(
                    int(getattr(cfg, "extractor_scan_top_n", 8)))
                self._ext_scan_top_n.setToolTip(
                    "Top-N */<base> pairs by 24h volume to keep on the "
                    "auto-scan watch list. Range [5, 10] per design "
                    "doc §6. Ignored when manual alt-targets are set.")
                self._ext_scan_top_n.valueChanged.connect(
                    lambda v: self._mark_changed("extractor_scan_top_n", v))
                ef.addRow("Auto-scan top-N:", self._ext_scan_top_n)

                self._ext_scan_refresh = QSpinBox()
                self._ext_scan_refresh.setRange(10, 600)
                self._ext_scan_refresh.setSuffix(" ticks")
                self._ext_scan_refresh.setValue(
                    int(getattr(cfg, "extractor_scan_refresh_candles", 60)))
                self._ext_scan_refresh.setToolTip(
                    "Ticks between watch-list refreshes. Lower = more "
                    "responsive; higher = less thrashing.")
                self._ext_scan_refresh.valueChanged.connect(
                    lambda v: self._mark_changed(
                        "extractor_scan_refresh_candles", v))
                ef.addRow("Scan refresh:", self._ext_scan_refresh)

                self._ext_pool_reserve = QDoubleSpinBox()
                self._ext_pool_reserve.setRange(0.0, 90.0)
                self._ext_pool_reserve.setDecimals(1)
                self._ext_pool_reserve.setSuffix(" %")
                self._ext_pool_reserve.setValue(
                    float(getattr(cfg, "extractor_pool_reserve_pct", 50.0)))
                self._ext_pool_reserve.setToolTip(
                    "% of chunk reserved as untouchable. New artillery "
                    "fires only if (chunk_free - artillery_size) >= reserve.")
                self._ext_pool_reserve.valueChanged.connect(
                    lambda v: self._mark_changed(
                        "extractor_pool_reserve_pct", v))
                ef.addRow("Pool reserve:", self._ext_pool_reserve)

                self._ext_exit_pct = QDoubleSpinBox()
                self._ext_exit_pct.setRange(10.0, 100.0)
                self._ext_exit_pct.setDecimals(1)
                self._ext_exit_pct.setSuffix(" %")
                self._ext_exit_pct.setValue(
                    float(getattr(cfg, "extractor_exit_pct", 100.0)))
                self._ext_exit_pct.setToolTip(
                    "% of alt position sold on bullish trigger. "
                    "100 = full exit; <100 leaves a rider tail.")
                self._ext_exit_pct.valueChanged.connect(
                    lambda v: self._mark_changed("extractor_exit_pct", v))
                ef.addRow("Exit %:", self._ext_exit_pct)

                self._ext_max_tier = QSpinBox()
                self._ext_max_tier.setRange(1, 10)
                self._ext_max_tier.setValue(
                    int(getattr(cfg, "extractor_max_compounding_tier", 3)))
                self._ext_max_tier.setToolTip(
                    "Compounding tier counter (currently informational — "
                    "logs ROLL_TO_NEXT_TIER vs LOCK_TO_POOL). At this "
                    "version, realized base gain always deposits directly "
                    "to the pool regardless of tier. The gain-as-next-"
                    "artillery-size rolling mechanism is a planned "
                    "enhancement (see extractor_bot.py:1264-1266).")
                self._ext_max_tier.valueChanged.connect(
                    lambda v: self._mark_changed(
                        "extractor_max_compounding_tier", v))
                ef.addRow("Max compounding tier:", self._ext_max_tier)

                self._ext_max_cost_basis = QDoubleSpinBox()
                self._ext_max_cost_basis.setRange(1.0, 10.0)
                self._ext_max_cost_basis.setDecimals(2)
                self._ext_max_cost_basis.setSuffix("x")
                self._ext_max_cost_basis.setValue(
                    float(getattr(cfg, "extractor_max_cost_basis_multiple", 2.0)))
                self._ext_max_cost_basis.setToolTip(
                    "Safety cap: cost basis of any position cannot "
                    "exceed multiplier x original artillery_size. "
                    "Hard floor against runaway averaging-down.")
                self._ext_max_cost_basis.valueChanged.connect(
                    lambda v: self._mark_changed(
                        "extractor_max_cost_basis_multiple", v))
                ef.addRow("Max cost-basis multiple:",
                          self._ext_max_cost_basis)

                layout.addWidget(ext_group)

                # Sub-group: operator alt-targets (live editable)
                # v3.19.28 — surface the manual override list. Read-only
                # display for now (multi-select live editor is a larger
                # follow-up); shows the operator what the bot is using.
                alts_group = QGroupBox("Alt Targets (manual override)")
                af = QVBoxLayout(alts_group)
                alts = list(getattr(cfg, "extractor_alt_targets", []) or [])
                if alts:
                    info_lbl = QLabel(
                        f"Manual override active — {len(alts)} pair(s):")
                    info_lbl.setStyleSheet("color: #aaa; font-size: 11px;")
                    af.addWidget(info_lbl)
                    alts_lbl = QLabel(", ".join(alts))
                    alts_lbl.setWordWrap(True)
                    alts_lbl.setStyleSheet(
                        "color: #00ffcc; font-family: monospace; "
                        "font-size: 11px;")
                    af.addWidget(alts_lbl)
                else:
                    info_lbl = QLabel(
                        "Auto-scan active (empty manual list). Bot "
                        "rotates top-N by 24h volume each refresh.")
                    info_lbl.setStyleSheet(
                        "color: #aaa; font-size: 11px; font-style: italic;")
                    af.addWidget(info_lbl)
                layout.addWidget(alts_group)

            layout.addStretch()
            return w

        # ---------------------------------------------------------------
        # Tab 6: Phantom Bots (v3.23.39 — merged from Phantom Bot +
        # Phantom State per operator directive 2026-07-27).
        # ---------------------------------------------------------------
        def _create_phantom_bots_tab(self) -> QWidget:
            """Combined Phantom Balance Bots config + runtime view.

            Config sections (top): enable toggle, active-TF checkboxes,
            lock duration. Writes route through ScrummingBot's
            ``update_phantom_config`` (phantom state lives on the bot,
            not on BotConfig).

            Runtime sections (below): coordinator status summary,
            per-phantom table (from ``_phantom_mgr.get_phantoms``),
            and cross-bot active-lock table (from ``_coordinator``).
            Everything is scrumming-only.
            """
            import time as _time
            w = QWidget()
            layout = QVBoxLayout(w)
            layout.setSpacing(8)

            bot = self._bot

            info = QLabel(
                "Multi-timeframe shadow bots. Higher TFs override lower TFs.\n"
                "Enable/disable and TF-set changes apply immediately to "
                "NEW phantoms. Already-started phantoms keep their "
                "original configuration until the next bot restart.")
            info.setStyleSheet("color: #888; font-size: 11px;")
            info.setWordWrap(True)
            layout.addWidget(info)

            # ── Config: Enable toggle ─────────────────────────────────
            enable_group = QGroupBox("Phantom Balance Bots")
            ef = QVBoxLayout(enable_group)
            self._phantom_enable = QCheckBox("Enable Phantom Balance Bots")
            self._phantom_enable.setChecked(
                bool(getattr(bot, "_phantoms_enabled", False)))
            self._phantom_enable.toggled.connect(
                lambda v: self._mark_changed("enable_phantoms", bool(v)))
            ef.addWidget(self._phantom_enable)
            layout.addWidget(enable_group)

            # ── Config: Timeframe checkboxes ─────────────────────────
            tf_group = QGroupBox("Active Timeframes")
            tf_layout = QVBoxLayout(tf_group)
            tf_hint = QLabel(
                "v3.15.61 — TFs not supported by this bot's exchange "
                "are disabled (greyed). Coinbase: 1m/5m/15m/30m/1h/2h/6h/1d. "
                "Binance: full set. Others vary.")
            tf_hint.setStyleSheet("color: #888; font-size: 10px;")
            tf_hint.setWordWrap(True)
            tf_layout.addWidget(tf_hint)

            self._phantom_tf_checks: dict = {}
            current_tfs = set(getattr(bot, "_phantom_timeframes", []) or [])
            try:
                from ..exchange.timeframes import available_timeframes
                _ex_id = getattr(bot.config, "exchange_id", None)
                _ph_allowed = set(available_timeframes(_ex_id))
            except Exception:
                _ph_allowed = {"1m", "5m", "15m", "30m", "1h", "2h",
                               "4h", "6h", "12h", "1d", "1w"}
            tf_row = QHBoxLayout()
            for tf in ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"]:
                cb = QCheckBox(tf)
                supported = tf in _ph_allowed
                cb.setChecked(tf in current_tfs and supported)
                cb.setEnabled(supported)
                cb.setToolTip(
                    f"{tf}: " +
                    ("supported" if supported
                     else f"NOT supported by exchange "
                          f"({getattr(bot.config, 'exchange_id', '?')})")
                )
                cb.toggled.connect(self._phantom_tfs_changed)
                self._phantom_tf_checks[tf] = cb
                tf_row.addWidget(cb)
            tf_layout.addLayout(tf_row)
            layout.addWidget(tf_group)

            # ── Config: Lock duration ─────────────────────────────────
            lock_group = QGroupBox("Higher-TF Lock Duration")
            lf = QFormLayout(lock_group)
            self._configure_form(lf)
            self._phantom_lock = QSpinBox()
            self._phantom_lock.setRange(1, 10)
            coord = getattr(bot, "_coordinator", None)
            current_lock = int(getattr(coord, "lock_candle_count", 2)
                               if coord else 2)
            self._phantom_lock.setValue(current_lock)
            self._phantom_lock.setToolTip(
                "When a higher-TF phantom locks a lower-TF phantom, "
                "how many candles does the lock persist?")
            self._phantom_lock.valueChanged.connect(
                lambda v: self._mark_changed("lock_candle_count", int(v)))
            lf.addRow("Candles to lock:", self._phantom_lock)
            layout.addWidget(lock_group)

            # ── Runtime: Coordinator Status ───────────────────────────
            phantoms_enabled = bool(getattr(
                bot, "_phantoms_enabled", False))
            phantoms_started = bool(getattr(
                bot, "_phantoms_started", False))
            phantom_tfs = list(getattr(
                bot, "_phantom_timeframes", []) or [])
            phantom_locked = bool(getattr(
                bot, "_phantom_locked", False))
            phantom_lock_tf = str(getattr(
                bot, "_phantom_lock_timeframe", "") or "")

            summary = QGroupBox("Coordinator Status")
            sf = QFormLayout(summary)
            self._configure_form(sf)

            en_lbl = QLabel("YES" if phantoms_enabled else "NO")
            en_lbl.setStyleSheet(
                "color: " + ("#00ff88" if phantoms_enabled else "#aaa"))
            sf.addRow("Phantoms enabled:", en_lbl)

            started_lbl = QLabel("YES" if phantoms_started else "NO")
            started_lbl.setStyleSheet(
                "color: " + ("#00ff88" if phantoms_started
                              else "#ff9900" if phantoms_enabled
                              else "#aaa"))
            sf.addRow("Phantoms started:", started_lbl)

            sf.addRow("Configured timeframes:",
                      QLabel(", ".join(phantom_tfs) if phantom_tfs
                             else "— (none)"))

            if phantom_locked:
                lock_lbl = QLabel(
                    f"LOCKED — SCRUM suppressed by {phantom_lock_tf} TF "
                    f"phantom (downside protection active)")
                lock_lbl.setStyleSheet(
                    "color: #ff9900; font-weight: bold;")
            else:
                lock_lbl = QLabel("UNLOCKED — SCRUM allowed")
                lock_lbl.setStyleSheet("color: #00ff88;")
            sf.addRow("SCRUM lock state:", lock_lbl)
            layout.addWidget(summary)

            # ── Runtime: Per-Phantom State table ─────────────────────
            phantom_mgr = getattr(bot, "_phantom_mgr", None)
            bot_id = getattr(bot, "bot_id", "")
            phantoms: list = []
            if phantom_mgr is not None:
                try:
                    phantoms = list(
                        phantom_mgr.get_phantoms(bot_id) or [])
                except Exception:  # noqa: BLE001 - defensive probe
                    phantoms = []

            if phantoms:
                ph_group = QGroupBox(
                    f"Per-Phantom State ({len(phantoms)})")
                pl = QVBoxLayout(ph_group)

                tbl = QTableWidget()
                tbl.setColumnCount(7)
                tbl.setHorizontalHeaderLabels([
                    "TF", "State", "Target", "Trades", "P&L",
                    "Bullish/Bearish", "Confidence"])
                tbl.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeToContents)
                tbl.setRowCount(len(phantoms))
                tbl.setMaximumHeight(280)
                tbl.setAlternatingRowColors(True)
                tbl.setEditTriggers(QTableWidget.NoEditTriggers)

                for row, ph in enumerate(phantoms):
                    try:
                        st = ph.get_status()
                    except Exception:  # noqa: BLE001 - defensive probe
                        st = {}

                    tbl.setItem(row, 0, QTableWidgetItem(
                        str(st.get("timeframe", "?"))))
                    tbl.setItem(row, 1, QTableWidgetItem(
                        str(st.get("state", "?"))))
                    tbl.setItem(row, 2, QTableWidgetItem(
                        f"${float(st.get('target_balance', 0) or 0):,.2f}"))
                    tbl.setItem(row, 3, QTableWidgetItem(
                        str(st.get("total_trades", 0))))

                    pnl = float(st.get("realized_pnl_exchange", 0) or 0)
                    pi = QTableWidgetItem(f"${pnl:+,.4f}")
                    pi.setForeground(QColor(
                        "#00ff88" if pnl > 0
                        else "#ff3366" if pnl < 0 else "#aaa"))
                    tbl.setItem(row, 4, pi)

                    summary_d = st.get("last_summary", {}) or {}
                    bullish = summary_d.get("bullish", 0)
                    bearish = summary_d.get("bearish", 0)
                    tbl.setItem(row, 5, QTableWidgetItem(
                        f"{bullish}/{bearish}"))

                    conf = float(summary_d.get("confidence", 0) or 0)
                    ci = QTableWidgetItem(f"{conf:.2%}")
                    if conf >= 0.50:
                        ci.setForeground(QColor("#00ff88"))
                    elif conf >= 0.25:
                        ci.setForeground(QColor("#ff9900"))
                    tbl.setItem(row, 6, ci)

                pl.addWidget(tbl)
                layout.addWidget(ph_group)

            # ── Runtime: Active Locks (cross-bot) ────────────────────
            coordinator = getattr(bot, "_coordinator", None)
            active_locks: list = []
            if coordinator is not None:
                try:
                    active_locks = list(
                        coordinator.get_active_locks() or [])
                except Exception:  # noqa: BLE001 - defensive probe
                    active_locks = []

            if active_locks:
                locks_group = QGroupBox(
                    f"Active Locks ({len(active_locks)})")
                ll = QVBoxLayout(locks_group)

                lock_tbl = QTableWidget()
                lock_tbl.setColumnCount(4)
                lock_tbl.setHorizontalHeaderLabels([
                    "Source TF", "Source Bot", "Direction",
                    "Candles left"])
                lock_tbl.horizontalHeader().setSectionResizeMode(
                    QHeaderView.ResizeToContents)
                lock_tbl.setRowCount(len(active_locks))
                lock_tbl.setMaximumHeight(220)
                lock_tbl.setAlternatingRowColors(True)
                lock_tbl.setEditTriggers(QTableWidget.NoEditTriggers)

                for row, lk in enumerate(active_locks):
                    lock_tbl.setItem(row, 0, QTableWidgetItem(
                        str(lk.get("source_tf", "?"))))
                    src_bot = str(lk.get("source_bot", "?"))
                    src_item = QTableWidgetItem(src_bot)
                    if src_bot == bot_id:
                        src_item.setForeground(QColor("#00ccff"))
                        src_item.setText(f"{src_bot} (this bot)")
                    lock_tbl.setItem(row, 1, src_item)

                    dir_str = str(lk.get("locked_direction", "?"))
                    di = QTableWidgetItem(dir_str)
                    if "BULLISH" in dir_str:
                        di.setForeground(QColor("#00ff88"))
                    elif "BEARISH" in dir_str:
                        di.setForeground(QColor("#ff3366"))
                    lock_tbl.setItem(row, 2, di)

                    cr = int(lk.get("candles_remaining", 0) or 0)
                    lock_tbl.setItem(row, 3, QTableWidgetItem(str(cr)))

                ll.addWidget(lock_tbl)
                layout.addWidget(locks_group)

            # ── Empty-state message when nothing is running ──────────
            if not phantoms and not active_locks:
                if not phantoms_enabled:
                    msg = QLabel(
                        "Phantom Bots are DISABLED on this bot. "
                        "Toggle 'Enable Phantom Balance Bots' above "
                        "to activate the multi-TF coordinator.")
                elif not phantoms_started:
                    msg = QLabel(
                        "Phantoms enabled but not yet started. They "
                        "spin up automatically on the first tick after "
                        "bot is running. If this persists, check the "
                        "Activity Log for phantom-startup errors.")
                else:
                    msg = QLabel(
                        "Phantoms active but no per-phantom state "
                        "available yet, and no locks currently held. "
                        "State populates after each phantom completes "
                        "its first signal cycle.")
                msg.setStyleSheet("color: #888; font-style: italic; "
                                  "padding: 10px;")
                msg.setWordWrap(True)
                layout.addWidget(msg)

            layout.addStretch()
            return w

        def _phantom_tfs_changed(self):
            """Called when any phantom TF checkbox toggles. Collect the
            full selected set and mark it as a single config change."""
            selected = [tf for tf, cb in self._phantom_tf_checks.items()
                        if cb.isChecked()]
            self._mark_changed("phantom_timeframes", selected)

        # v3.20.4 — Tab 4 (Adjust Stack) + _create_adjust_stack_tab +
        # _execute_adjust_stack removed. The tab was Grid-bots-only and
        # grid_bot.py was deleted v3.16.0; the methods became
        # unreachable when BotMode.GRID was dropped from the enum.
