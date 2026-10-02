"""Scrumming-bot dashboard table, its column specification and its header."""

from __future__ import annotations

import logging

from ...core.privacy_mask_registry import mask_or

from .. import design_system as ds
from ..main_tabs.bot_status_table_surface import (
    BOT_ID_COLUMN,
    BROWSER_NEW_WINDOW,
    COLUMN_LABELS,
    COLUMN_TOOLTIPS,
    FIXED_WIDTHS,
    HEADER_CELL_GAP_PX,
    HEADER_CELL_PAD_PX,
    HEADER_DOT_ROW_PX,
    HEADER_LABEL_FONT_PX,
    HEADER_LABEL_MIN_FONT_PX,
    HEADER_LABEL_SIZE_FORMAT,
    HEADER_LABEL_SKIN,
    HEADER_LABEL_WRAP,
    HEADER_SORT_MARK_BOX_PX,
    HEADER_SORT_MARK_STYLE,
    LINK_FIELD_BY_COLUMN,
    LOGO_SIZE_PX,
    LOGO_TIP_FORMAT,
    NO_LOGO_TIP_FORMAT,
    NO_SELECTION_BOT_ID,
    NO_SELECTION_ROW,
    NO_SORT_COLUMN,
    ROW_HEIGHT_PX,
    SORTABLE_COLUMNS,
    TOOLTIP_LINE_GAP,
    SortLookups,
    icon_asset_of,
    kept_logo_path,
    mode_tooltip,
    opening_address,
    organisation_address,
    organisation_tooltip,
    order_statuses,
    selection_after_press,
    selection_after_view_moved,
    sort_direction,
    sort_mark,
    sort_tooltip,
    target_value,
)
from ..table_cells import (
    _ammo_price_pool,
    _compose_ammo_cell,
    _compose_position_value_cell,
    _compose_table_target_denom_cell,
    _fresh_display_price,
)

logger = logging.getLogger("acervator.gui")


def _qt_lookups() -> SortLookups:
    """The ``SortLookups`` the window's own cell composers answer.

    ``_fresh_display_price`` prices one row and
    ``_compose_table_target_denom_cell`` answers what a denom cell draws.
    """

    def price(status) -> tuple:
        stats = status.get("stats", {}) or {}
        return _fresh_display_price(
            _ammo_price_pool(),
            str(status.get("exchange", "") or ""),
            str(status.get("symbol", "") or ""),
            float(stats.get("current_price", 0.0) or 0.0),
        )

    def denom_text(quote: str, base: str, exchange_id: str, target: float) -> str:
        return _compose_table_target_denom_cell(quote, base, exchange_id, target)[0]

    return SortLookups(price, denom_text)


try:
    from PySide6.QtWidgets import (
        QHeaderView,
        QLabel,
        QPushButton,
        QStyledItemDelegate,
        QStyleOptionViewItem,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import QSignalBlocker, QSize, Qt
    from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon

    from . import ColumnSpec, ColumnarTableWidget
    from .bot_selection import _reanchor_bot_selection, _select_row_for_bot
    from .privacy_dot import PrivacyDot

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class CentredMarkDelegate(QStyledItemDelegate):
        """Centres a cell's decoration by setting ``decorationPosition`` to ``Top``."""

        def initStyleOption(self, option, index) -> None:  # noqa: N802
            """Take the base option, then stack the decoration over the cell's text."""
            super().initStyleOption(option, index)
            option.decorationPosition = QStyleOptionViewItem.Top

    class ColumnHeaderCell(QWidget):
        """One column's wrapped label, over the privacy dot that masks it.

        ``fit`` re-sizes the label to a width and answers the height that
        width needs, and a press anywhere but on the dot calls ``on_sort``.
        """

        def __init__(
            self,
            label: str,
            field_id: str,
            on_toggle=None,
            on_sort=None,
            column: int = NO_SORT_COLUMN,
            parent=None,
        ):
            super().__init__(parent)
            self.setAccessibleName(label)
            self._label_text = label
            self._font_px: int = HEADER_LABEL_FONT_PX
            self._on_sort = on_sort
            self._column = column
            self._pressed = False
            if column in SORTABLE_COLUMNS:
                self.setCursor(Qt.PointingHandCursor)
            box = QVBoxLayout(self)
            box.setContentsMargins(
                HEADER_CELL_PAD_PX,
                HEADER_CELL_PAD_PX,
                HEADER_CELL_PAD_PX,
                HEADER_CELL_PAD_PX,
            )
            box.setSpacing(HEADER_CELL_GAP_PX)
            self._label = QLabel(label, self)
            self._label.setWordWrap(HEADER_LABEL_WRAP)
            self._label.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self._label.setStyleSheet(self._skin())
            self._label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            box.addWidget(self._label, 1)
            self.dot = None
            if field_id:
                self.dot = PrivacyDot(field_id, on_toggle=on_toggle, parent=self)
                self.dot.setFixedHeight(HEADER_DOT_ROW_PX)
                box.addWidget(self.dot, 0, Qt.AlignHCenter)
            else:
                # A column the privacy register does not carry leaves the
                # dot's row empty, so every label sits on the same line.
                box.addSpacing(HEADER_DOT_ROW_PX)
            # The mark is outside the layout, so neither the wrap nor the
            # dot's centring moves when it appears.
            self.mark = QLabel("", self)
            self.mark.setStyleSheet(HEADER_SORT_MARK_STYLE)
            self.mark.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            self.mark.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.mark.raise_()

        def set_sort_mark(self, text: str) -> None:
            """Draw one column's own sort arrow, or nothing when it is unsorted."""
            self.mark.setText(text)
            self.mark.setVisible(bool(text))

        def sort_mark_text(self) -> str:
            """The arrow this column's header is drawing now."""
            return self.mark.text()

        def resizeEvent(self, event):  # noqa: N802
            """Keep the sort mark on the privacy dot's row, at the cell's right edge."""
            super().resizeEvent(event)
            self._place_mark()

        def _place_mark(self) -> None:
            """Give the mark the dot's row, right of the dot, inside the cell."""
            top, height = self._dot_row()
            left = max(self._dot_right(), self.width() - HEADER_SORT_MARK_BOX_PX)
            self.mark.setGeometry(left, top, max(0, self.width() - left), height)

        def _dot_row(self) -> tuple:
            """The top and the height of the row this cell's privacy dot sits on."""
            if self.dot is not None:
                box = self.dot.geometry()
                return box.y(), box.height()
            height = min(HEADER_DOT_ROW_PX, self.height())
            return max(0, self.height() - HEADER_CELL_PAD_PX - height), height

        def _dot_right(self) -> int:
            """The x this cell's privacy dot ends at, or 0 when it carries none."""
            return 0 if self.dot is None else self.dot.geometry().x() + self.dot.width()

        def mousePressEvent(self, event):  # noqa: N802
            """Take the press, so the release arrives at this same cell."""
            self._pressed = True
            event.accept()

        def mouseReleaseEvent(self, event):  # noqa: N802
            """Sort this column when the press and the release are both on it.

            The dot is its own button and consumes its own press, so a
            press that reaches here is a press on the label.
            """
            was_pressed = self._pressed
            self._pressed = False
            event.accept()
            if not was_pressed or not callable(self._on_sort):
                return
            if not self.rect().contains(event.position().toPoint()):
                return
            self._on_sort(self._column)

        def label_text(self) -> str:
            """The whole label this column draws, wrapped or not."""
            return self._label_text

        def font_px(self) -> int:
            """The size this column's label is drawing at now."""
            return self._font_px

        def drawn_lines(self, width: int) -> int:
            """How many lines the label takes at one column width."""
            metrics = QFontMetrics(self._font())
            return max(1, round(self._text_height(width) / metrics.lineSpacing()))

        def fit(self, width: int) -> int:
            """Size the label to ``width`` and answer the height it needs.

            The label steps down to ``HEADER_LABEL_MIN_FONT_PX`` when its
            longest word does not fit ``width`` at ``HEADER_LABEL_FONT_PX``.
            """
            inner = max(1, width - 2 * HEADER_CELL_PAD_PX)
            chosen = self._size_that_fits(inner)
            if chosen != self._font_px:
                self._font_px = chosen
                self._label.setStyleSheet(self._skin())
            return (
                self._text_height(width)
                + HEADER_CELL_GAP_PX
                + HEADER_DOT_ROW_PX
                + 2 * HEADER_CELL_PAD_PX
            )

        def _skin(self) -> str:
            return HEADER_LABEL_SKIN + HEADER_LABEL_SIZE_FORMAT.format(px=self._font_px)

        def _font(self) -> QFont:
            font = QFont(self._label.font())
            font.setPixelSize(self._font_px)
            return font

        def _size_that_fits(self, inner: int) -> int:
            for size in (HEADER_LABEL_FONT_PX, HEADER_LABEL_MIN_FONT_PX):
                font = QFont(self._label.font())
                font.setPixelSize(size)
                if self._longest_word_width(font) <= inner:
                    return size
            return HEADER_LABEL_MIN_FONT_PX

        def _longest_word_width(self, font: QFont) -> int:
            metrics = QFontMetrics(font)
            words = self._label_text.split() or [self._label_text]
            return max(metrics.horizontalAdvance(word) for word in words)

        def _text_height(self, width: int) -> int:
            inner = max(1, width - 2 * HEADER_CELL_PAD_PX)
            metrics = QFontMetrics(self._font())
            return metrics.boundingRect(
                0, 0, inner, 0, Qt.TextWordWrap | Qt.AlignHCenter, self._label_text
            ).height()

    class WrappedColumnHeader(QHeaderView):
        """A header that draws each column's label as a wrapped widget.

        ``build`` takes one cell a column, and every re-layout gives every
        cell the height the tallest label needs, so the header is one height
        across all columns.
        """

        def __init__(self, parent=None):
            super().__init__(Qt.Horizontal, parent)
            self._cells: list = []
            # Each cell handles its own press, so the section itself is not
            # a control and cannot fire a second time for the same click.
            self.setSectionsClickable(False)
            self.setSectionsMovable(False)
            self.sectionResized.connect(self._place)
            self.geometriesChanged.connect(self._place)

        def build(self, cells: list) -> None:
            """Hold one ``ColumnHeaderCell`` a column and lay them out."""
            for cell in self._cells:
                cell.setParent(None)
                cell.deleteLater()
            self._cells = list(cells)
            for cell in self._cells:
                cell.setParent(self)
                cell.show()
            self._place()

        def cells(self) -> list:
            """Every column's header cell, in column order."""
            return list(self._cells)

        def resizeEvent(self, event):  # noqa: N802
            """Re-fit every label whenever the header's own width changes."""
            super().resizeEvent(event)
            self._place()

        def _place(self, *_args) -> None:
            if not self._cells:
                return
            widths = [self.sectionSize(at) for at in range(len(self._cells))]
            tallest = max(cell.fit(width) for cell, width in zip(self._cells, widths))
            if self.height() != tallest:
                self.setFixedHeight(tallest)
            for at, cell in enumerate(self._cells):
                cell.setGeometry(
                    self.sectionViewportPosition(at), 0, widths[at], tallest
                )

    #: The labels, tooltips and widths the surface publishes, so the window and
    #: the renderer cannot drift apart on any of the three.
    SCRUMMING_COLUMNS = ColumnSpec(
        labels=COLUMN_LABELS,
        tooltips=dict(COLUMN_TOOLTIPS),
        fixed_widths=dict(FIXED_WIDTHS),
    )

    class BotStatusTable(ColumnarTableWidget):
        COLUMN_SPEC = SCRUMMING_COLUMNS
        COLUMNS = SCRUMMING_COLUMNS.labels
        COLUMN_TOOLTIPS = SCRUMMING_COLUMNS.tooltips

        STATE_COLORS = {
            "running": QColor(ds.SUCCESS),
            "idle": QColor(ds.CARD_METRIC_LABEL),
            "paused": QColor(ds.WARNING),
            "error": QColor(ds.ERROR),
            "cooldown": QColor(ds.WARNING_STRONG),
            "stopped": QColor(ds.TEXT_MUTED),
            "starting": QColor(ds.STATE_STARTING),
        }

        PRIVACY_FIELD_BY_COL = {
            0: "bot_table.bot_id",
            1: "bot_table.symbol",
            2: "bot_table.ammo",  # position value reuses the ammo mask
            3: "bot_table.trades",
            4: "bot_table.target",
            5: "bot_table.target",  # target_btc reuses target mask
            6: "bot_table.target",  # target_eth reuses target mask
            7: "bot_table.ammo",
            8: "bot_table.fire",
        }

        def __init__(self, on_bot_clicked=None, on_fire_clicked=None, parent=None):
            super().__init__(parent=parent)
            self._on_bot_clicked = on_bot_clicked
            self._on_fire_clicked = on_fire_clicked
            self._bot_ids = []
            self._sort_column = NO_SORT_COLUMN
            self._sort_descending = False
            # One QIcon per kept logo file, so a rewrite reads no file twice.
            self._logo_icons: dict = {}

            # Last payload seen, so a dot toggle repopulates
            # without refetching from the bot manager.
            self._last_statuses: list = []

            # The first column draws a LOGO_SIZE_PX mark, so every row takes
            # ROW_HEIGHT_PX rather than the style's own section size.
            self.setIconSize(QSize(LOGO_SIZE_PX, LOGO_SIZE_PX))
            self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT_PX)

            # Held on self: setItemDelegateForColumn does not take ownership.
            self._mark_delegate = CentredMarkDelegate(self)
            self.setItemDelegateForColumn(BOT_ID_COLUMN, self._mark_delegate)

            # Qt scrolls to its current item while autoScroll is on, which
            # takes the scroll bar away from the operator.
            self.setAutoScroll(False)
            self.verticalScrollBar().valueChanged.connect(
                lambda _value: self.release_selection_off_view()
            )

            # Symbol cell (col 1) is a hyperlink to the pair's chart on
            # the bot's exchange.
            self.cellClicked.connect(self._on_cell_clicked)

            self._build_header()

        def mousePressEvent(self, event):  # noqa: N802
            """Apply the press, then settle the selection the panel follows.

            Qt moves the highlight itself, so a press on the row already
            shown leaves it where it was; ``selection_after_press`` reads
            that as the second press and clears the selection.
            """
            shown = self.get_selected_bot_id()
            super().mousePressEvent(event)
            pressed = self.get_selected_bot_id()
            if not selection_after_press(pressed, shown):
                self.clear_bot_selection()

        def clear_bot_selection(self) -> str:
            """Take the highlight off every row and answer the bot then held."""
            self.clearSelection()
            self.setCurrentCell(-1, -1)
            return self.get_selected_bot_id()

        def visible_row_band(self) -> tuple[int, int]:
            """The first and last row the viewport draws, in row indexes."""
            last = self.rowAt(self.viewport().height() - 1)
            if last < 0:
                last = self.rowCount() - 1
            return self.rowAt(0), last

        def release_selection_off_view(self) -> str:
            """Drop the highlight when its row is outside the drawn band.

            ``QSignalBlocker`` keeps the drop off ``itemSelectionChanged``, so
            the Voting Panel keeps the bot it is drawing.
            """
            if not self.selectedItems():
                return NO_SELECTION_BOT_ID
            first, last = self.visible_row_band()
            kept = selection_after_view_moved(self.currentRow(), first, last)
            if kept != NO_SELECTION_ROW:
                return self.get_selected_bot_id()
            with QSignalBlocker(self):
                self.clearSelection()
                self.setCurrentCell(-1, -1)
            return NO_SELECTION_BOT_ID

        def highlight_bot(self, bot_id: str) -> str:
            """Put the highlight on the bot the Voting Panel draws.

            The window calls this when the panel's dropdown or an arrow
            moved the selection, so the move emits nothing back.
            """
            wanted = str(bot_id or "")
            with QSignalBlocker(self):
                if wanted:
                    _select_row_for_bot(self, wanted, self._bot_ids)
                else:
                    self.clearSelection()
                    self.setCurrentCell(-1, -1)
            return self.release_selection_off_view()

        def _build_header(self) -> None:
            """Put one wrapped label, over its own dot, on every column.

            The header item keeps the tooltip and gives up its text, so the
            section paints its ground and the cell paints the label.
            """
            header = WrappedColumnHeader(self)
            cells = []
            for col, label in enumerate(self.COLUMNS):
                item = QTableWidgetItem("")
                item.setToolTip(self._header_tooltip(col))
                self.setHorizontalHeaderItem(col, item)
                cells.append(
                    ColumnHeaderCell(
                        label,
                        self.PRIVACY_FIELD_BY_COL.get(col, ""),
                        on_toggle=self._on_privacy_toggled,
                        on_sort=self._on_header_sorted,
                        column=col,
                        parent=header,
                    )
                )
            self.setHorizontalHeader(header)
            header.setSectionResizeMode(QHeaderView.Stretch)
            for col, width in self.COLUMN_SPEC.fixed_widths.items():
                header.setSectionResizeMode(col, QHeaderView.Fixed)
                self.setColumnWidth(col, width)
            header.build(cells)
            self._header = header
            self._refresh_sort_marks()

        def header_cells(self) -> list:
            """Every column's header cell, in column order."""
            return self._header.cells()

        def _header_tooltip(self, column: int) -> str:
            """One column's tooltip, with the line about pressing to sort."""
            direction = sort_direction(column, self._sort_column, self._sort_descending)
            base = self.COLUMN_TOOLTIPS.get(column, "")
            return (base + sort_tooltip(column, direction)).strip()

        def _refresh_sort_marks(self) -> None:
            """Draw the arrow on the sorted column and clear every other one."""
            for col, cell in enumerate(self._header.cells()):
                direction = sort_direction(
                    col, self._sort_column, self._sort_descending
                )
                cell.set_sort_mark(sort_mark(direction))
                item = self.horizontalHeaderItem(col)
                if item is not None:
                    item.setToolTip(self._header_tooltip(col))

        def sort_state(self) -> tuple:
            """Which column this table is ordered by, and which way."""
            return self._sort_column, self._sort_descending

        def _on_header_sorted(self, column: int) -> None:
            """Order the rows by one column, reversing when it is already the one.

            A column outside ``SORTABLE_COLUMNS`` changes nothing.
            """
            if column not in SORTABLE_COLUMNS:
                return
            if column == self._sort_column:
                self._sort_descending = not self._sort_descending
            else:
                self._sort_column = column
                self._sort_descending = False
            self._refresh_sort_marks()
            if self._last_statuses:
                self.update_bots(self._last_statuses)

        def refresh_privacy_dots(self) -> None:
            """Re-read the privacy register into every column's own dot.

            Three of the nine dots share a field with another column, so
            one press repaints all of them.
            """
            for cell in self._header.cells():
                if cell.dot is not None:
                    cell.dot.refresh()

        def _on_privacy_toggled(self) -> None:
            """Repaint every dot and every cell after one dot was pressed.

            ``PrivacyDot`` writes the register itself, so this repaints the
            rows from the payload the table is already holding.
            """
            self.refresh_privacy_dots()
            if self._last_statuses:
                self.update_bots(self._last_statuses)

        def _sort_lookups(self) -> SortLookups:
            """The two readings ``order_statuses`` orders this table's rows by."""
            return _qt_lookups()

        def _display_price(self, status: dict, stats: dict) -> tuple:
            """One row's drawn price and its age, read from the price pool."""
            return _fresh_display_price(
                _ammo_price_pool(),
                str(status.get("exchange", "") or ""),
                str(status.get("symbol", "") or ""),
                float(stats.get("current_price", 0.0)),
            )

        def _denom_cell(
            self, quote: str, base_asset: str, exchange_id: str, target_val: float
        ) -> tuple:
            """One Target-BTC or Target-ETH cell: its text and its colour."""
            return _compose_table_target_denom_cell(
                quote, base_asset, exchange_id, target_val
            )

        def update_bots(self, bot_statuses: list[dict]) -> None:
            """Rewrite every row from one list of bot statuses.

            The order is recomputed on every rewrite, so a column whose
            figures keep moving keeps the order the last press asked for.
            """
            # Kept so a header-dot toggle re-renders without refetching.
            self._last_statuses = list(bot_statuses)
            bot_statuses = order_statuses(
                self._last_statuses,
                self._sort_column,
                self._sort_descending,
                self._sort_lookups(),
            )
            # Read before setRowCount: a row index cannot name its bot afterwards.
            _selected_before = self.get_selected_bot_id()
            self.setRowCount(len(bot_statuses))
            self._bot_ids = []
            for row, status in enumerate(bot_statuses):
                bid = status.get("bot_id", "")
                self._bot_ids.append(bid)
                mode = status.get("mode", "")
                # ExchangeTab pre-filters by mode, so a non-scrumming status is a routing fault.
                if mode != "scrumming":
                    import logging as _l

                    _l.getLogger(__name__).warning(
                        "BotStatusTable.update_bots received non-scrumming "
                        "status (mode=%r bot=%r) — should have been routed "
                        "to ExtractorBotTable. Skipping row.",
                        mode,
                        bid[:8] if bid else "?",
                    )
                    self._clear_row(row)
                    continue
                try:
                    self._write_row(row, status)
                except Exception as _row_exc:
                    # One bad field stops one row; every other bot still paints.
                    logger.warning(
                        "BotStatusTable row %d refused for bot %r: %s: %s",
                        row,
                        bid[:8] if bid else "?",
                        type(_row_exc).__name__,
                        _row_exc,
                    )
                    self._clear_row(row)
            # The highlight follows the bot, not the row.
            _reanchor_bot_selection(self, _selected_before, self._bot_ids)
            # A sort or a rewrite can put that bot on a row the viewport
            # no longer draws, and then the highlight goes rather than the
            # scroll position.
            self.release_selection_off_view()

        def _clear_row(self, row: int) -> None:
            """Empty one row's cells and take its two buttons off it."""
            for col in range(self.columnCount()):
                self.setItem(row, col, None)
                if self.cellWidget(row, col) is not None:
                    self.removeCellWidget(row, col)

        def _logo_icon(self, path: str):
            """``path``'s own icon, held in ``_logo_icons`` after one read, None for a file holding no image.

            The file is handed to ``QIcon`` whole rather than as one pixmap
            scaled to ``LOGO_SIZE_PX``, so an icon file carrying several sizes
            draws the size nearest that figure and a mark smaller than it draws
            at its own size rather than enlarged.
            """
            held = self._logo_icons.get(path)
            if held is not None:
                return held
            icon = QIcon(path)
            found = icon if icon.availableSizes() else None
            self._logo_icons[path] = found
            return found

        def _draw_logo(self, item, symbol: str, shown: str) -> None:
            """Put ``symbol``'s kept logo and organisation address on ``item``.

            ``shown`` stays as the cell's text where no logo is kept. The
            address goes on ``UserRole`` for ``_on_cell_clicked``, and the
            tooltip names where a click goes or says the mark is not a link.
            """
            asset = icon_asset_of(symbol)
            if not asset or shown != asset:
                return
            link = organisation_address(symbol)
            if link:
                from PySide6.QtCore import Qt as _Qt

                item.setData(_Qt.UserRole, link)
            mark_tip = organisation_tooltip(asset, link)
            path = kept_logo_path(symbol)
            icon = self._logo_icon(path) if path else None
            if icon is None:
                item.setToolTip(
                    NO_LOGO_TIP_FORMAT.format(asset=asset) + TOOLTIP_LINE_GAP + mark_tip
                )
                return
            item.setIcon(icon)
            item.setText("")
            item.setToolTip(
                LOGO_TIP_FORMAT.format(asset=asset) + TOOLTIP_LINE_GAP + mark_tip
            )

        def _write_row(self, row: int, status: dict) -> None:
            """Write one bot's eight cells, its Fire button and its Detail button."""
            stats = status.get("stats", {})
            bid = status.get("bot_id", "")
            state = status.get("state", "")
            mode = status.get("mode", "")
            target_val = target_value(status)
            stats_pv = float(stats.get("position_value", 0.0))
            holdings = float(status.get("current_holdings", 0.0))
            # Display only; the trading path still reads stats.current_price.
            cur_price, _price_age = self._display_price(status, stats)
            # quote_to_usd is 1.0 for USD-quoted pairs.
            qrate = float(status.get("quote_to_usd", 1.0) or 1.0)
            _position = _compose_position_value_cell(
                holdings,
                cur_price,
                qrate,
                price_age_s=_price_age,
            )
            _ammo = _compose_ammo_cell(
                stats_pv,
                holdings,
                cur_price,
                qrate,
                target_val,
                price_age_s=_price_age,
            )
            ammo_color = QColor(_ammo["color"])
            ammo_tip = _ammo["tip"]
            ammo_text = _ammo["text"]

            # Colour encodes direction, so the magnitudes print unsigned.
            def _mag(v: float) -> str:
                return f"${abs(v):,.4f}"

            target_text = _mag(target_val) if target_val > 0 else "---"
            # Blank for self-reference, or when the pair is not listed on this exchange.
            symbol = status.get("symbol", "") or ""
            base_asset = symbol.split("/")[0].upper() if "/" in symbol else ""
            exchange_id = status.get("exchange", "") or ""
            target_btc_text, target_btc_color = self._denom_cell(
                "BTC", base_asset, exchange_id, target_val
            )
            target_eth_text, target_eth_color = self._denom_cell(
                "ETH", base_asset, exchange_id, target_val
            )
            logo_asset = icon_asset_of(symbol)
            items = [
                mask_or(logo_asset, "bot_table.bot_id"),
                mask_or(status.get("symbol", ""), "bot_table.symbol"),
                mask_or(_position["text"], "bot_table.ammo"),
                mask_or(str(stats.get("total_trades", 0)), "bot_table.trades"),
                mask_or(target_text, "bot_table.target"),
                mask_or(target_btc_text, "bot_table.target"),
                mask_or(target_eth_text, "bot_table.target"),
                mask_or(ammo_text, "bot_table.ammo"),
                "",  # Fire button placeholder (col 8)
                "",  # Detail button placeholder (col 9)
            ]
            for col, text in enumerate(items):
                if col in (8, 9):
                    continue  # Buttons handled below
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                if col == 1 and text:
                    color = self.STATE_COLORS.get(state, QColor(ds.TEXT_HIGH))
                    item.setForeground(color)
                    item.setToolTip(mode_tooltip(mode, state))
                    # UserRole carries (exchange_id, raw_symbol) for _on_cell_clicked.
                    try:
                        from ...exchange.exchange_chart_urls import (
                            chart_url as _chart_url,
                        )

                        _url = _chart_url(exchange_id, status.get("symbol", "") or "")
                        if _url:
                            from PySide6.QtCore import Qt as _Qt

                            item.setData(_Qt.UserRole, _url)
                            # The state colour stays; the underline is what
                            # marks the cell as the chart's link.
                            _f = item.font()
                            _f.setUnderline(True)
                            item.setFont(_f)
                            item.setToolTip(
                                item.toolTip()
                                + TOOLTIP_LINE_GAP
                                + f"Open chart on {exchange_id} "
                                f"in default browser: {_url}"
                            )
                    except Exception as _chart_url_exc:
                        # The status dict may be the malformed input, so only the exception is logged.
                        logger.debug(
                            "Chart-URL decoration skipped: %s: %s",
                            type(_chart_url_exc).__name__,
                            _chart_url_exc,
                        )
                if col == 0:
                    self._draw_logo(item, symbol, text)
                if col == 2:
                    item.setToolTip(_position["tip"])
                if col == 5:
                    item.setForeground(QColor(target_btc_color))
                if col == 6:
                    item.setForeground(QColor(target_eth_color))
                if col == 7:
                    item.setForeground(ammo_color)
                    item.setToolTip(ammo_tip)
                self.setItem(row, col, item)

            # The fill states the direction of the rebalance before the operator clicks.
            scrum_phase = status.get("scrum_target_mode")
            armed_action = status.get("armed_action")
            ceiling_enabled = status.get("position_ceiling_enabled", False)
            ceiling_ratio = status.get("ceiling_ratio")
            ceiling_usd = status.get("position_ceiling_usd")
            fold_taper = status.get("fold_rate_taper", 1.0)
            detonation_enabled = status.get("detonation_enabled", False)
            detonation_tf = status.get("detonation_timeframe", "1d")
            # Fold is hard-stopped when ceiling enabled AND ratio >= 1.0
            fold_blocked_by_ceiling = (
                ceiling_enabled and ceiling_ratio is not None and ceiling_ratio >= 1.0
            )
            # Masking is display only; the button stays clickable.
            fire_btn = QPushButton(mask_or("Fire", "bot_table.fire"))
            fire_btn.setFixedHeight(22)
            # NoFocus stops Qt's autoScroll from jumping the table on a focus grab.
            fire_btn.setFocusPolicy(Qt.NoFocus)
            is_scrumming = mode == "scrumming"
            is_active = state in ("running", "paused")
            fire_btn.setEnabled(is_scrumming and is_active)
            if is_scrumming and is_active:
                # Helper to apply a glow effect with a given color.
                def _apply_glow(color_hex: str) -> None:
                    try:
                        from PySide6.QtWidgets import QGraphicsDropShadowEffect
                        from PySide6.QtGui import QColor as _QC

                        glow = QGraphicsDropShadowEffect(fire_btn)
                        glow.setColor(_QC(color_hex))
                        glow.setBlurRadius(18)
                        glow.setOffset(0, 0)
                        fire_btn.setGraphicsEffect(glow)
                        try:
                            _root = self.window()
                            if hasattr(_root, "_register_fire_glow"):
                                _root._register_fire_glow(glow)
                        except Exception:  # noqa: S110
                            pass
                    except Exception:  # noqa: S110
                        pass

                def _risk_suffix() -> str:
                    parts = []
                    if ceiling_enabled and ceiling_ratio is not None:
                        pct = ceiling_ratio * 100
                        if fold_blocked_by_ceiling:
                            parts.append(
                                f"\n\n⚠ CEILING REACHED "
                                f"({pct:.1f}% of ${ceiling_usd:.2f}) — "
                                f"fold hard-stopped, scrum only."
                            )
                        elif ceiling_ratio >= 0.5:
                            parts.append(
                                f"\n\n⚠ Approaching ceiling "
                                f"({pct:.1f}% of ${ceiling_usd:.2f}) — "
                                f"fold rate tapered to {fold_taper*100:.0f}%."
                            )
                        else:
                            parts.append(
                                f"\n\nCeiling: {pct:.1f}% of "
                                f"${ceiling_usd:.2f} "
                                f"(fold rate: {fold_taper*100:.0f}%)."
                            )
                    if detonation_enabled:
                        parts.append(
                            f"\nDetonation armed: monitoring "
                            f"{detonation_tf.upper()} for BULLISH "
                            f"auto-harvest."
                        )
                    return "".join(parts)

                if armed_action == "scrum":
                    # Solid means auto would fire now; outline means only manual remains.
                    _af = status.get("auto_fire", {}) or {}
                    _auto_armed_scrum = bool(_af.get("scrum_armed", False))
                    _scrum_blockers = list(_af.get("scrum_blockers", []) or [])
                    if _auto_armed_scrum:
                        # Solid red fill — auto-fire would fire NOW.
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.TEXT_MAX}; font-weight: bold; "
                            f"background-color: {ds.MAIN_ALERT_SURFACE}; "
                            f"border: 1px solid {ds.ERROR};"
                        )
                        _apply_glow(ds.ERROR)
                        fire_btn.setToolTip(
                            "ARMED for SCRUM (auto would fire). "
                            "Holdings above target; all gates clear. "
                            "Clicking fires a MARKET sell to "
                            "rebalance back to target." + _risk_suffix()
                        )
                    else:
                        # Outline only — manual override available
                        # but auto-fire is blocked by ≥1 gate.
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.ERROR}; font-weight: bold; "
                            "background-color: transparent; "
                            f"border: 1px dashed {ds.ERROR};"
                        )
                        # No glow — visually quieter so operator
                        # sees the difference at a glance.
                        _blockers_text = (
                            "\nBlocked by: " + ", ".join(_scrum_blockers)
                            if _scrum_blockers
                            else ""
                        )
                        fire_btn.setToolTip(
                            "Manual SCRUM override available — "
                            "delta > 0 but auto-fire blocked. "
                            "Clicking fires a MARKET sell sized to "
                            "rebalance back to target (bypasses "
                            "auto's TA/BB/HTF gates)." + _blockers_text + _risk_suffix()
                        )
                elif armed_action == "fold":
                    # Mirrors the SCRUM branch above.
                    _af = status.get("auto_fire", {}) or {}
                    _auto_armed_fold = bool(_af.get("fold_armed", False))
                    _fold_blockers = list(_af.get("fold_blockers", []) or [])
                    if fold_blocked_by_ceiling:
                        # Ceiling already gives this its own visual.
                        # Keep the existing muted-green dashed style.
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.TEXT_NEUTRAL}; font-weight: bold; "
                            f"background-color: {ds.STATE_ENGAGED_DIM}; "
                            f"border: 1px dashed {ds.CARD_METRIC_LABEL};"
                        )
                        _apply_glow(ds.STATE_ENGAGED_GLOW)
                        fire_btn.setToolTip(
                            "Fold would be armed, but POSITION "
                            "CEILING has been reached. Fold is "
                            "hard-stopped. Manual Fire will still "
                            "attempt to rebalance (operator "
                            "override bypasses the ceiling)." + _risk_suffix()
                        )
                    elif _auto_armed_fold:
                        # Solid green — auto-fire FOLD would fire NOW.
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.TEXT_MAX}; font-weight: bold; "
                            f"background-color: {ds.STATE_ENGAGED_DIM}; "
                            f"border: 1px solid {ds.STATE_ARMED};"
                        )
                        _apply_glow(ds.STATE_ARMED)
                        fire_btn.setToolTip(
                            "ARMED for FOLD (auto would fire). "
                            "Holdings below target; all gates clear. "
                            "Clicking fires a MARKET buy to "
                            "rebalance back to target." + _risk_suffix()
                        )
                    else:
                        # Outline only — manual override available
                        # but auto-fire is blocked.
                        fire_btn.setStyleSheet(
                            "font-size: 10px; padding: 1px 6px; "
                            f"color: {ds.STATE_ARMED}; font-weight: bold; "
                            "background-color: transparent; "
                            f"border: 1px dashed {ds.STATE_ARMED};"
                        )
                        _blockers_text = (
                            "\nBlocked by: " + ", ".join(_fold_blockers)
                            if _fold_blockers
                            else ""
                        )
                        fire_btn.setToolTip(
                            "Manual FOLD override available — "
                            "delta < 0 but auto-fire blocked. "
                            "Clicking fires a MARKET buy sized to "
                            "rebalance back to target (bypasses "
                            "auto's TA/BB/MEM-171 gates)."
                            + _blockers_text
                            + _risk_suffix()
                        )
                elif scrum_phase == "fire":
                    # Inside the dust band, so amber: no rebalance is needed.
                    fire_btn.setStyleSheet(
                        "font-size: 10px; padding: 1px 6px; "
                        f"color: {ds.TEXT_ON_LIGHT}; font-weight: bold; "
                        f"background-color: {ds.WARNING}; "
                        f"border: 1px solid {ds.STATE_PENDING};"
                    )
                    _apply_glow(ds.STATE_PENDING)
                    fire_btn.setToolTip(
                        "Organic FIRE phase — bot at band but "
                        "holdings within dust band of target. "
                        "Clicking has no effect." + _risk_suffix()
                    )
                elif scrum_phase == "track":
                    fire_btn.setStyleSheet(
                        "font-size: 10px; padding: 1px 6px; "
                        f"color: {ds.WARNING}; font-weight: bold;"
                    )
                    fire_btn.setToolTip(
                        "TRACKING — bot detected band approach. "
                        "Fire is available but bot is within dust "
                        "band; rebalance would be a no-op."
                    )
                else:
                    # SEARCH / idle — subdued red
                    fire_btn.setStyleSheet(
                        "font-size: 10px; padding: 1px 6px; "
                        f"color: {ds.ERROR}; font-weight: bold;"
                    )
                    fire_btn.setToolTip(
                        "Bot within dust band of target. "
                        "Manual Fire would be a no-op."
                    )
            else:
                fire_btn.setStyleSheet(
                    "font-size: 10px; padding: 1px 6px; color: "
                    f"{ds.TEXT_PLACEHOLDER};"
                )
                if not is_scrumming:
                    fire_btn.setToolTip("Manual Fire is scrumming-only.")
                else:
                    fire_btn.setToolTip(
                        f"Bot is {state}; start or resume to enable Fire."
                    )
            fire_btn.clicked.connect(lambda _checked, b=bid: self._on_fire(b))
            self.setCellWidget(row, 8, fire_btn)

            detail_btn = QPushButton("Detail")
            detail_btn.setFixedHeight(22)
            detail_btn.setStyleSheet("font-size: 10px; padding: 1px 6px;")
            detail_btn.setToolTip(
                "View full bot status, configuration, and error details"
            )
            detail_btn.clicked.connect(lambda _checked, b=bid: self._on_detail(b))
            self.setCellWidget(row, 9, detail_btn)

        def _on_detail(self, bot_id: str) -> None:
            # Select before the modal dialog: exec() does not return until it closes.
            _select_row_for_bot(self, bot_id, self._bot_ids)
            if self._on_bot_clicked:
                self._on_bot_clicked(bot_id)

        def _on_cell_clicked(self, row: int, col: int) -> None:
            """Open the address stored on a clicked cell, refusing any that is not https.

            ``LINK_FIELD_BY_COLUMN`` names the columns that carry one: the
            logo's own column and the Symbol column. ``opening_address``
            refuses an http, file, javascript, data or scheme-less value, so
            nothing but an https address with a host reaches the browser.
            """
            if col not in LINK_FIELD_BY_COLUMN:
                return
            item = self.item(row, col)
            if item is None:
                return
            from PySide6.QtCore import Qt as _Qt

            held = item.data(_Qt.UserRole)
            if not held:
                return
            url = opening_address(held)
            if not url:
                logger.warning("Cell address refused for %r", held)
                return
            try:
                import webbrowser

                webbrowser.open(url, new=BROWSER_NEW_WINDOW)
            except Exception as _wb_exc:  # noqa: BLE001 - best-effort
                logger.warning("Cell address open failed for %r: %s", url, _wb_exc)

        def _on_fire(self, bot_id: str) -> None:
            """MEM-236 — Manual Fire button click handler."""
            if self._on_fire_clicked:
                self._on_fire_clicked(bot_id)

        def get_selected_bot_id(self) -> str:
            # clearSelection() empties selectedItems() but leaves currentRow() stale.
            if not self.selectedItems():
                return ""
            row = self.currentRow()
            if 0 <= row < len(self._bot_ids):
                return self._bot_ids[row]
            return ""
