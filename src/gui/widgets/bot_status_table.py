"""Scrumming-bot dashboard table, its column specification and its header."""

from __future__ import annotations

import logging

from ...core.privacy_mask_registry import mask_or

from .. import design_system as ds
from ..main_tabs.bot_status_table_surface import (
    HEADER_CELL_GAP_PX,
    HEADER_CELL_PAD_PX,
    HEADER_DOT_ROW_PX,
    HEADER_LABEL_FONT_PX,
    HEADER_LABEL_MIN_FONT_PX,
    HEADER_LABEL_SIZE_FORMAT,
    HEADER_LABEL_SKIN,
    HEADER_LABEL_WRAP,
)
from ..table_cells import (
    _ammo_price_pool,
    _compose_ammo_cell,
    _compose_position_value_cell,
    _compose_table_target_denom_cell,
    _fresh_display_price,
)

logger = logging.getLogger("acervator.gui")

try:
    from PySide6.QtWidgets import (
        QHeaderView,
        QLabel,
        QPushButton,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QFontMetrics

    from . import ColumnSpec, ColumnarTableWidget
    from .bot_selection import _reanchor_bot_selection, _select_row_for_bot
    from .privacy_dot import PrivacyDot

    _HAS_QT = True
except ImportError:
    _HAS_QT = False


if _HAS_QT:

    class ColumnHeaderCell(QWidget):
        """One column's wrapped label, over the privacy dot that masks it.

        ``fit`` re-sizes the label to a width and answers the height that
        width needs, so ``WrappedColumnHeader`` can give every column the
        same height.
        """

        def __init__(self, label: str, field_id: str, on_toggle=None, parent=None):
            super().__init__(parent)
            self.setAccessibleName(label)
            self._label_text = label
            self._font_px: int = HEADER_LABEL_FONT_PX
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
            # The label is not the control; the dot under it is.
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

    SCRUMMING_COLUMNS = ColumnSpec(
        labels=(
            "Bot ID",
            "Symbol",
            "Current Position Value",
            "Trades",
            "Target",
            "Target BTC",
            "Target ETH",
            "Ammo",
            "Fire",
            "",
        ),
        tooltips={
            0: (
                "Unique identifier for this bot instance, coloured by current state.\n"
                "Green = RUNNING · Amber = PAUSED · Gray = IDLE/STOPPED\n"
                "Red = ERROR · Orange = COOLDOWN · Cyan = STARTING"
            ),
            1: "Trading pair (Target Asset / Base Currency)",
            2: (
                "Current Position Value — what this bot's holdings are worth now,\n"
                "priced from the exchange (holdings × exchange price × quote rate).\n"
                "Blank whenever no fresh exchange price exists: the cell never shows\n"
                "a last-known figure, a computed stand-in or a ledger value.\n"
                "Hover a blank cell to read which of those is missing."
            ),
            3: "Total number of executed buy and sell trades",
            4: "Target Balance — the operator-set balance this bot trades\n"
            "relative to. Hard-capped per MEM-246 Phase B.",
            5: (
                "Target Balance denominated in BTC (target USD ÷ BTC/USD spot).\n"
                "Suffix Δ = 24h % change of <target>/BTC minus 24h % of "
                "<target>/USD.\n"
                "Positive Δ (green) = BTC-quoted pair cheaper in USD terms than USD-quoted.\n"
                "Blank when pair unlisted on this exchange or target is BTC itself."
            ),
            6: (
                "Target Balance denominated in ETH (target USD ÷ ETH/USD spot).\n"
                "Suffix Δ = 24h % change of <target>/ETH minus 24h % of "
                "<target>/USD.\n"
                "Positive Δ (green) = ETH-quoted pair cheaper in USD terms than USD-quoted.\n"
                "Blank when pair unlisted on this exchange or target is ETH itself."
            ),
            7: (
                "Ammo — distance of current position value from Target.\n"
                "Green = surplus above target (Scrum territory, next action = SELL).\n"
                "Red = deficit below target (Fold territory, next action = BUY).\n"
                "Neutral grey = within dust band around target (no action pending)."
            ),
            8: "Manual Fire — force immediate scrum/fold evaluation on next tick",
            9: "Click for full bot detail and status explanation",
        },
        fixed_widths={
            8: ds.TABLE_COL_FIRE_W,
            9: ds.TABLE_COL_DETAIL_W,
        },
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

            # Last payload seen, so a dot toggle repopulates
            # without refetching from the bot manager.
            self._last_statuses: list = []

            # Symbol cell (col 1) is a hyperlink to the pair's chart on
            # the bot's exchange.
            self.cellClicked.connect(self._on_cell_clicked)

            self._build_header()

        def _build_header(self) -> None:
            """Put one wrapped label, over its own dot, on every column.

            The header item keeps the tooltip and gives up its text, so the
            section paints its ground and the cell paints the label.
            """
            header = WrappedColumnHeader(self)
            cells = []
            for col, label in enumerate(self.COLUMNS):
                item = QTableWidgetItem("")
                item.setToolTip(self.COLUMN_TOOLTIPS.get(col, ""))
                self.setHorizontalHeaderItem(col, item)
                cells.append(
                    ColumnHeaderCell(
                        label,
                        self.PRIVACY_FIELD_BY_COL.get(col, ""),
                        on_toggle=self._on_privacy_toggled,
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

        def header_cells(self) -> list:
            """Every column's header cell, in column order."""
            return self._header.cells()

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

        def update_bots(self, bot_statuses: list[dict]) -> None:
            # Kept so a header-dot toggle re-renders without refetching.
            self._last_statuses = list(bot_statuses)
            # Read before setRowCount: a row index cannot name its bot afterwards.
            _selected_before = self.get_selected_bot_id()
            self.setRowCount(len(bot_statuses))
            self._bot_ids = []
            for row, status in enumerate(bot_statuses):
                stats = status.get("stats", {})
                bid = status.get("bot_id", "")
                self._bot_ids.append(bid)
                state = status.get("state", "")
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
                    continue
                # live_target_balance is the grown target the engine re-zeros to; config is the fallback.
                target_val = float(
                    status.get("live_target_balance", status.get("target_balance", 0.0))
                    or status.get("target_balance", 0.0)
                    or 0.0
                )
                stats_pv = float(stats.get("position_value", 0.0))
                holdings = float(status.get("current_holdings", 0.0))
                # Display only; the trading path still reads stats.current_price.
                cur_price, _price_age = _fresh_display_price(
                    _ammo_price_pool(),
                    str(status.get("exchange", "") or ""),
                    str(status.get("symbol", "") or ""),
                    float(stats.get("current_price", 0.0)),
                )
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
                target_btc_text, target_btc_color = _compose_table_target_denom_cell(
                    "BTC", base_asset, exchange_id, target_val
                )
                target_eth_text, target_eth_color = _compose_table_target_denom_cell(
                    "ETH", base_asset, exchange_id, target_val
                )
                items = [
                    mask_or(bid, "bot_table.bot_id"),
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
                        try:
                            base = text.split("/")[0] if "/" in text else text
                            from ..bot_wizard import _get_coin_icon

                            icon = _get_coin_icon(
                                base, ds.COIN_ICON_SIZE_PX, download=False
                            )
                            if icon:
                                item.setIcon(icon)
                        except Exception:  # noqa: S110
                            pass
                        # UserRole carries (exchange_id, raw_symbol) for _on_cell_clicked.
                        try:
                            from ...exchange.exchange_chart_urls import (
                                chart_url as _chart_url,
                            )

                            _url = _chart_url(
                                exchange_id, status.get("symbol", "") or ""
                            )
                            if _url:
                                from PySide6.QtCore import Qt as _Qt

                                item.setData(_Qt.UserRole, _url)
                                item.setForeground(QColor(ds.TEXT_INFO_SOFT))
                                _f = item.font()
                                _f.setUnderline(True)
                                item.setFont(_f)
                                item.setToolTip(
                                    f"Open chart on {exchange_id} "
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
                        color = self.STATE_COLORS.get(state, QColor(ds.TEXT_HIGH))
                        item.setForeground(color)
                        # Tooltip on the cell shows the actual state text
                        item.setToolTip(
                            f"Mode: {mode}\nState: {state.upper() if state else 'UNKNOWN'}"
                        )
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
                    ceiling_enabled
                    and ceiling_ratio is not None
                    and ceiling_ratio >= 1.0
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
                                "auto's TA/BB/HTF gates)."
                                + _blockers_text
                                + _risk_suffix()
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
                                f"background-color: {ds.STATE_ENGAGED}; "
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

            # The highlight follows the bot, not the row.
            _reanchor_bot_selection(self, _selected_before, self._bot_ids)

        def _on_detail(self, bot_id: str) -> None:
            # Select before the modal dialog: exec() does not return until it closes.
            _select_row_for_bot(self, bot_id, self._bot_ids)
            if self._on_bot_clicked:
                self._on_bot_clicked(bot_id)

        def _on_cell_clicked(self, row: int, col: int) -> None:
            """Open the chart URL stored on a clicked Symbol cell.

            Only column 1 carries a URL; every other column is a no-op.
            """
            if col != 1:
                return
            item = self.item(row, col)
            if item is None:
                return
            from PySide6.QtCore import Qt as _Qt

            url = item.data(_Qt.UserRole)
            if not url:
                return
            try:
                import webbrowser

                webbrowser.open(str(url), new=2)
            except Exception as _wb_exc:  # noqa: BLE001 - best-effort
                logger.warning("Chart URL open failed for %r: %s", url, _wb_exc)

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
