"""Qt widgets, the row-border delegate and the reach controls of the Fold
Tranches panel.

The reach controls are module functions and not methods: several test
files build the tab through a stub dialog that never runs ``__init__``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QStyleOptionViewItem,
    QStyledItemDelegate,
)
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor, QPainter, QPen

from .. import design_system as ds
from .fold_tokens import (
    FOLD_FILTER_PLACEHOLDER,
    FOLD_FILTER_TOOLTIP,
    FOLD_SORT_ORDERS,
    FOLD_SORT_QUEUE_ORDER,
    FOLD_SORT_TOOLTIP,
    TRANCHE_ROW_BORDER_BY_BG,
    TRANCHE_ROW_BORDER_PX,
    fold_row_matches_filter,
    install_health_row,
)

if TYPE_CHECKING:
    from ..bot_live_settings import BotLiveSettingsDialog

logger = logging.getLogger("acervator.gui")


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

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
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
    "collapse or remove a tranche."
)


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


def despawn_preview_text(days: int, armed: dict, windows: list) -> str:
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
            f"{armed['fold_removed']} of {armed['fold_open']} " f"fold tranche(s)",
            f"${armed['usd_removed']:,.4f}",
            f"{armed['units_removed']:,.8f} units",
        ]
        if armed["stack_open"]:
            parts.append(
                f"{armed['stack_removed']} of "
                f"{armed['stack_open']} stack tranche(s)"
            )
        if armed["stack_kept_live_order"]:
            parts.append(
                f"{armed['stack_kept_live_order']} stack kept " f"(live order)"
            )
        if armed["ageless_kept"]:
            parts.append(f"{armed['ageless_kept']} kept (no timestamp)")
        return "  -  ".join(parts)
    if not windows:
        return "nothing to remove"
    return "if armed at  " + "  -  ".join(
        f"{w}d: {p['fold_removed'] + p['stack_removed']} " f"(${p['usd_removed']:,.4f})"
        for w, p in windows
    )


def pin_despawn_rows(
    dialog: BotLiveSettingsDialog,
    days: int,
    fold_snapshot: list,
    stack_snapshot: list,
    now_ts: float,
    elapsed: float,
) -> None:
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

        from ...trading.bot_container import (
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
        _preview_lbl = getattr(dialog, "_fold_despawn_preview_lbl", None)
        _despawn_emit(
            "gui.04.003.postcondition.despawn_rows_match_ledger",
            actual={
                "timer_row": (_timer_lbl.text() if _timer_lbl is not None else None),
                "preview_row": (
                    _preview_lbl.text() if _preview_lbl is not None else None
                ),
            },
            expected={
                "timer_row": despawn_timer_text(days),
                "preview_row": despawn_preview_text(days, _armed, _windows),
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
            },
        )


def install_despawn_rows(
    dialog: BotLiveSettingsDialog, form: QFormLayout, tranches: list, now_ts: float
) -> dict:
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

    from ...trading.bot_container import (
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
    if _days <= 0 and (_widest["fold_removed"] + _widest["stack_removed"]):
        timer_lbl.setStyleSheet(f"color: {ds.FOLD_RATIO_AMBER};")
    dialog._fold_despawn_timer_lbl = timer_lbl
    # issue #98 defect 6 - BOTH HALVES OF THE ROW. These two rows
    # already carried `DESPAWN_ROW_TOOLTIP` on the value; the words
    # the operator actually points at carried nothing. The text is
    # issue #103's and is not rewritten here - only the label half
    # is given the tooltip the value half already had.
    install_health_row(form, "Tranche despawn timer:", timer_lbl, DESPAWN_ROW_TOOLTIP)

    preview_lbl = QLabel(despawn_preview_text(_days, armed, windows))
    dialog._fold_despawn_preview_lbl = preview_lbl
    install_health_row(form, "Despawn would remove:", preview_lbl, DESPAWN_ROW_TOOLTIP)

    pin_despawn_rows(dialog, _days, tranches, _stack, now_ts, _elapsed)
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


def build_fold_row_controls(dialog: BotLiveSettingsDialog) -> QHBoxLayout:
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
        lambda _index, dlg=dialog, box=combo: on_fold_sort_changed(
            dlg, box.currentText()
        )
    )
    dialog._fold_sort_combo = combo

    edit = QLineEdit()
    edit.setPlaceholderText(FOLD_FILTER_PLACEHOLDER)
    edit.setToolTip(FOLD_FILTER_TOOLTIP)
    edit.setClearButtonEnabled(True)
    edit.textChanged.connect(lambda text, dlg=dialog: on_fold_filter_changed(dlg, text))
    dialog._fold_filter_edit = edit

    row.addWidget(order_lbl)
    row.addWidget(combo)
    row.addWidget(edit, 1)
    return row


def on_fold_sort_changed(dialog: BotLiveSettingsDialog, order: str) -> None:
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
        logger.warning("Fold Tranches: ignoring unknown row order %r", order)
        return
    if order == fold_sort_order(dialog):
        return
    dialog._fold_sort_key = order
    rebuild = getattr(dialog, "_refresh_fold_tranches_tab", None)
    if not callable(rebuild):
        return
    from PySide6.QtCore import QTimer as _QTimer

    _QTimer.singleShot(0, rebuild)


def on_fold_filter_changed(dialog: BotLiveSettingsDialog, needle: str) -> None:
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
        table.setRowHidden(row, not fold_row_matches_filter(cells, needle))
