"""The Fold Tranches panel chrome: row border, despawn rows, order and filter.

``_TrancheRowBorderDelegate`` strokes the row edges.
``install_despawn_rows`` adds the timer and preview rows.
``build_fold_row_controls``, ``on_fold_sort_changed`` and
``on_fold_filter_changed`` are module functions a stub dialog drives unbound.
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
    """Strokes a row edge over a painted tranche row.

    ``paint`` calls ``super().paint`` first, keeping the cell's own
    ``BackgroundRole`` brush, which a ``QTableWidget::item`` stylesheet
    rule would drop.
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
    ) -> None:
        """Paint the cell, then stroke the row's top and bottom edges.

        `TRANCHE_ROW_BORDER_BY_BG` maps the cell's own fill to the border
        colour; a fill missing from that map gets no stroke.
        """
        super().paint(painter, option, index)

        brush = index.data(Qt.ItemDataRole.BackgroundRole)
        if brush is None:
            return
        try:
            fill = brush.color().name()
        except AttributeError:
            # Qt permits a QColor in BackgroundRole as well as a QBrush.
            try:
                fill = QColor(brush).name()
            except (TypeError, ValueError):
                return
        border_hex = TRANCHE_ROW_BORDER_BY_BG.get(fill)
        if border_hex is None:
            return

        painter.save()
        pen = QPen(QColor(border_hex), TRANCHE_ROW_BORDER_PX)
        # A rounded cap would overshoot the cell edge at 2px.
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        rect = option.rect
        # A line drawn on `rect.top()` itself is half clipped by the cell.
        inset = TRANCHE_ROW_BORDER_PX // 2
        top = rect.top() + inset
        bottom = rect.bottom() - inset
        painter.drawLine(rect.left(), top, rect.right(), top)
        painter.drawLine(rect.left(), bottom, rect.right(), bottom)
        painter.restore()


#: Tooltip carried by both rows `install_despawn_rows` adds.
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
    """Return the timer row text for `days`, naming where it is set.

    `days` of 0 or less reads as Off.
    """
    _where = "Settings tab > Advanced > Tranche Despawn Timer"
    if days <= 0:
        return f"Off  -  {_where}"
    return f"{days} day(s)  -  {_where}"


def despawn_preview_text(days: int, armed: dict, windows: list) -> str:
    """Render the preview row: records first, then dollars and units.

    `days` above 0 describes `armed` at that threshold; otherwise each
    entry in `windows` prints its own count and dollars.
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
    """Emit the two rendered despawn rows beside the same rows re-read.

    `actual` is what `_fold_despawn_timer_lbl` and
    `_fold_despawn_preview_lbl` now carry; `expected` re-renders
    `despawn_timer_text` and `despawn_preview_text` from the bot's live
    ledgers, not from `fold_snapshot` and `stack_snapshot`.
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
    """Add the timer and preview rows to `form`; return the armed preview.

    `despawn_preview` counts what a sweep at `despawn_threshold_days`
    would take, and the timer row turns amber only when that threshold is
    off while the widest `DESPAWN_PREVIEW_WINDOWS` entry already holds
    records.

    Args:
      dialog: the dialog building the tab. Only `_bot` is read;
        the two label handles are set on it.
      form: the Fold-Tranche Cycle Health `QFormLayout`.
      tranches: this bot's fold tranches, as the builder read them.
      now_ts: the wall clock the Age column ages against.

    Returns:
      The preview at the armed threshold, all zeroes when the timer is
      off.

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
    _widest = windows[-1][1] if windows else armed
    if _days <= 0 and (_widest["fold_removed"] + _widest["stack_removed"]):
        timer_lbl.setStyleSheet(f"color: {ds.FOLD_RATIO_AMBER};")
    dialog._fold_despawn_timer_lbl = timer_lbl
    install_health_row(form, "Tranche despawn timer:", timer_lbl, DESPAWN_ROW_TOOLTIP)

    preview_lbl = QLabel(despawn_preview_text(_days, armed, windows))
    dialog._fold_despawn_preview_lbl = preview_lbl
    install_health_row(form, "Despawn would remove:", preview_lbl, DESPAWN_ROW_TOOLTIP)

    pin_despawn_rows(dialog, _days, tranches, _stack, now_ts, _elapsed)
    return armed


def fold_sort_order(dialog: BotLiveSettingsDialog) -> str:
    """Return the order stored on `dialog`, or `FOLD_SORT_QUEUE_ORDER`.

    An order outside `FOLD_SORT_ORDERS` reads as queue order.
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
    # `currentIndexChanged` would refire on the rebuild's `setCurrentText`.
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
    """Store `order` on `dialog` and rebuild the table to apply it.

    An `order` outside `FOLD_SORT_ORDERS`, or one `fold_sort_order`
    already returns, rebuilds nothing.
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

    # `_refresh_fold_tranches_tab` deletes the combo this signal came from.
    _QTimer.singleShot(0, rebuild)


def on_fold_filter_changed(dialog: BotLiveSettingsDialog, needle: str) -> None:
    """Hide every row whose `_fold_row_texts` entry does not match `needle`.

    `setRowHidden` moves no row; each Fire button stays on its tranche.
    """
    table = getattr(dialog, "_fold_tranche_table", None)
    if table is None:
        return
    texts = getattr(dialog, "_fold_row_texts", []) or []
    for row in range(table.rowCount()):
        cells = texts[row] if row < len(texts) else []
        table.setRowHidden(row, not fold_row_matches_filter(cells, needle))
