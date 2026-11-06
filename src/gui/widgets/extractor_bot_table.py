"""Extractor-bot dashboard table and its column specification."""

from __future__ import annotations

import logging

from .. import design_system as ds
from ..main_tabs import extractor_bot_table_surface as ebts
from ..main_tabs.bot_status_table_surface import BUTTON_HEIGHT_PX, ROW_HEIGHT_PX

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import QPushButton, QTableWidgetItem
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    from . import ColumnSpec, ColumnarTableWidget
    from .bot_selection import _reanchor_bot_selection, _select_row_for_bot
    from ..tooltips import set_description

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    EXTRACTOR_COLUMNS = ColumnSpec(
        labels=ebts.COLUMN_LABELS,
        tooltips=dict(ebts.COLUMN_TOOLTIPS),
        fixed_widths=dict(ebts.COLUMN_FIXED_WIDTHS),
    )

    class ExtractorBotTable(ColumnarTableWidget):
        COLUMN_SPEC = EXTRACTOR_COLUMNS
        COLUMNS = EXTRACTOR_COLUMNS.labels
        COLUMN_TOOLTIPS = EXTRACTOR_COLUMNS.tooltips

        STATE_COLORS = {
            "running": QColor(ds.SUCCESS),
            "idle": QColor(ds.CARD_METRIC_LABEL),
            "paused": QColor(ds.WARNING),
            "error": QColor(ds.ERROR),
            "cooldown": QColor(ds.WARNING_STRONG),
            "stopped": QColor(ds.TEXT_MUTED),
            "starting": QColor(ds.STATE_STARTING),
        }

        POOL_COLORS = {
            "green": QColor(ds.SUCCESS),
            "yellow": QColor(ds.WARNING),
            "red": QColor(ds.ERROR),
        }

        def __init__(self, on_bot_clicked=None, parent=None):
            super().__init__(parent=parent)
            self._on_bot_clicked = on_bot_clicked
            self._bot_ids = []
            # One declared row height for every bot table, so Fire and
            # Detail fill a cell the style would otherwise size.
            self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT_PX)

        def sizeHint(self):  # noqa: N802
            """The header plus every row, so a stretch of 0 shows whole rows.

            ``ExchangeTab`` adds this table at ``EXTRACTOR_TABLE_STRETCH``, so the
            page hands it this height and gives the Scrumming table the rest.
            """
            hint = super().sizeHint()
            rows = sum(self.rowHeight(row) for row in range(self.rowCount()))
            frame = 2 * self.frameWidth()
            hint.setHeight(self.horizontalHeader().height() + rows + frame)
            return hint

        def update_bots(self, bot_statuses: list[dict]) -> None:
            # Read before `setRowCount` and the `_bot_ids` rebuild
            # discard the old row-to-bot mapping.
            _selected_before = self.get_selected_bot_id()
            self.setRowCount(len(bot_statuses))
            self._bot_ids = []
            for row, status in enumerate(bot_statuses):
                bid = status.get("bot_id", "")
                self._bot_ids.append(bid)
                state = status.get("state", "")
                chunk_size_usd = float(status.get("chunk_size_usd", 0.0) or 0.0)
                chunk_free_base = float(status.get("chunk_free_base", 0.0) or 0.0)
                chunk_size_base = float(status.get("chunk_size_base", 0.0) or 0.0)
                n_positions = int(status.get("n_positions_open", 0) or 0)
                n_drawdown = int(status.get("n_positions_drawdown", 0) or 0)
                pool_color_name = status.get("pool_color", "green")
                base_currency = status.get("base_currency", "")

                if chunk_size_base > 0:
                    deployed_base = max(chunk_size_base - chunk_free_base, 0.0)
                    usd_per_base = chunk_size_usd / chunk_size_base
                    free_usd = chunk_free_base * usd_per_base
                    deployed_usd = deployed_base * usd_per_base
                else:
                    deployed_base = 0.0
                    free_usd = 0.0
                    deployed_usd = 0.0

                pool_text = f"${chunk_size_usd:,.2f}" if chunk_size_usd > 0 else "---"
                liquid_text = f"${free_usd:,.2f}" if chunk_size_usd > 0 else "---"
                liquid_color = self.POOL_COLORS.get(
                    pool_color_name, QColor(ds.TEXT_MED)
                )
                liquid_tip = ebts.liquid_tooltip(
                    pool_color_name,
                    n_positions,
                    n_drawdown,
                    base_currency,
                    chunk_free_base,
                    free_usd,
                    deployed_base,
                    deployed_usd,
                )

                items = [
                    bid,
                    base_currency or status.get("symbol", ""),
                    "extractor",
                    str(status.get("stats", {}).get("total_trades", 0)),
                    pool_text,
                    liquid_text,
                    "",  # Fire button placeholder
                    "",  # Detail button placeholder
                ]
                for col, text in enumerate(items):
                    if col in (6, 7):
                        continue
                    item = QTableWidgetItem(text)
                    item.setTextAlignment(Qt.AlignCenter)
                    if col == 1 and text:
                        try:
                            from ..bot_wizard import _get_coin_icon

                            icon = _get_coin_icon(text, ds.COIN_ICON_SIZE_PX)
                            if icon:
                                item.setIcon(icon)
                        except Exception as icon_exc:
                            logger.debug(
                                "Extractor row %d: the coin mark could not be "
                                "drawn (%s: %s); the Symbol cell draws its "
                                "text without a mark",
                                row,
                                type(icon_exc).__name__,
                                icon_exc,
                            )
                    if col == 2:  # Mode cell
                        color = self.STATE_COLORS.get(state, QColor(ds.TEXT_HIGH))
                        item.setForeground(color)
                        set_description(item, ebts.mode_tooltip(state))
                    if col == 5:  # Liquid cell
                        item.setForeground(liquid_color)
                        set_description(item, liquid_tip)
                    self.setItem(row, col, item)

                fire_btn = QPushButton("Fire")
                fire_btn.setFixedHeight(BUTTON_HEIGHT_PX)
                fire_btn.setFocusPolicy(Qt.NoFocus)
                fire_btn.setEnabled(False)
                fire_btn.setStyleSheet(
                    f"font-size: 10px; padding: 1px 6px; color: {ds.TEXT_PLACEHOLDER};"
                )
                set_description(fire_btn, ebts.FIRE_TOOLTIP)
                self.setCellWidget(row, 6, fire_btn)

                detail_btn = QPushButton("Detail")
                detail_btn.setFixedHeight(BUTTON_HEIGHT_PX)
                detail_btn.setStyleSheet("font-size: 10px; padding: 1px 6px;")
                set_description(detail_btn, ebts.DETAIL_TOOLTIP)
                detail_btn.clicked.connect(lambda _checked, b=bid: self._on_detail(b))
                self.setCellWidget(row, 7, detail_btn)

            # `_reanchor_bot_selection` follows the bot, not the row index.
            _reanchor_bot_selection(self, _selected_before, self._bot_ids)

        def _on_detail(self, bot_id: str) -> None:
            # `_select_row_for_bot` moves the highlight before
            # `_on_bot_clicked` fires.
            _select_row_for_bot(self, bot_id, self._bot_ids)
            if self._on_bot_clicked:
                self._on_bot_clicked(bot_id)

        def get_selected_bot_id(self) -> str:
            # `clearSelection` leaves `currentRow` on the old row.
            if not self.selectedItems():
                return ""
            row = self.currentRow()
            if 0 <= row < len(self._bot_ids):
                return self._bot_ids[row]
            return ""
