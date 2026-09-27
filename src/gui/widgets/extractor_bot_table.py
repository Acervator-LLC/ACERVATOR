"""Extractor-bot dashboard table and its column specification."""

from __future__ import annotations

from .. import design_system as ds

try:
    from PySide6.QtWidgets import QPushButton, QTableWidgetItem
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    from . import ColumnSpec, ColumnarTableWidget
    from .bot_selection import _reanchor_bot_selection, _select_row_for_bot

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    EXTRACTOR_COLUMNS = ColumnSpec(
        labels=(
            "Bot ID",
            "Symbol",
            "Mode",
            "Trades",
            "Pool",
            "Liquid",
            "Fire",
            "",
        ),
        tooltips={
            0: "Unique identifier for this Extractor instance",
            1: "Base currency this Extractor accumulates",
            2: (
                "Trading mode + current state.\n"
                "Green = RUNNING · Amber = PAUSED · Gray = IDLE/STOPPED\n"
                "Red = ERROR · Orange = COOLDOWN · Cyan = STARTING"
            ),
            3: "Total number of executed trades across all positions",
            4: (
                "Pool — operator-set chunk size in USD (the budget "
                "this Extractor owns and rotates through positions). "
                "Live-edit in the bot's Settings tab → Extractor → "
                "Pool size (USD)."
            ),
            5: (
                "Liquid — USD-equivalent of the base-currency units "
                "currently NOT deployed to any open position. As "
                "positions close back to base, Liquid grows. Pool "
                "minus Liquid is the currently-deployed amount.\n"
                "Color: green = pool fully in base (no open "
                "positions), yellow = positions open, none in "
                "drawdown, red = at least one position in drawdown."
            ),
            6: (
                "Manual Fire is per-position for Extractors. "
                "Use the Detail dialog's Positions Held tab."
            ),
            7: "Click for full bot detail and status explanation",
        },
        fixed_widths={
            6: ds.TABLE_COL_FIRE_W,
            7: ds.TABLE_COL_DETAIL_W,
        },
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
                liquid_tip = (
                    f"Extractor pool: {pool_color_name.upper()}\n"
                    f"  • {n_positions} position(s) open\n"
                    f"  • {n_drawdown} in drawdown\n"
                    f"  • {base_currency} base currency\n"
                    f"  • {chunk_free_base:.8f} {base_currency} free "
                    f"({free_usd:.2f} USD)\n"
                    f"  • {deployed_base:.8f} {base_currency} "
                    f"deployed ({deployed_usd:.2f} USD)"
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
                        except Exception:  # noqa: S110
                            pass
                    if col == 2:  # Mode cell
                        color = self.STATE_COLORS.get(state, QColor(ds.TEXT_HIGH))
                        item.setForeground(color)
                        item.setToolTip(
                            f"Mode: extractor (Base Currency "
                            f"Extractor Multi-Target)\nState: "
                            f"{state.upper() if state else 'UNKNOWN'}\n"
                            f"v3.19.1 — accumulates base-currency "
                            f"units via top-N pair scanning."
                        )
                    if col == 5:  # Liquid cell
                        item.setForeground(liquid_color)
                        item.setToolTip(liquid_tip)
                    self.setItem(row, col, item)

                fire_btn = QPushButton("Fire")
                fire_btn.setFixedHeight(22)
                fire_btn.setFocusPolicy(Qt.NoFocus)
                fire_btn.setEnabled(False)
                fire_btn.setStyleSheet(
                    f"font-size: 10px; padding: 1px 6px; color: {ds.TEXT_PLACEHOLDER};"
                )
                fire_btn.setToolTip(
                    "Manual Fire is per-position for Extractor bots. "
                    "Use the Detail dialog's Positions Held tab."
                )
                self.setCellWidget(row, 6, fire_btn)

                detail_btn = QPushButton("Detail")
                detail_btn.setFixedHeight(22)
                detail_btn.setStyleSheet("font-size: 10px; padding: 1px 6px;")
                detail_btn.setToolTip(
                    "View full bot status, configuration, and error " "details"
                )
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
