# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Paper tab in Qt: the Trading tab's panes, fed by the live exchange feed.

``PaperTraderTabQt`` lays out the clone ``paper_trader_tab_surface`` describes
and draws every value from that model: the Privacy Mode row, the market
selector, the two reserved rows, the bot list, the Indicator Voting Panel, the
Live Feed pane, the Fake Balance table and the Paper Run table. ``_tick_timer``
advances one bot per fire on the wall clock, so one ask never blocks on the
whole fleet. ``LiveFeedSource`` is the one data path, and it answers no send.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..paper.live_feed_source import LiveFeedSource
from . import design_system as ds
from .main_tabs import paper_trader_tab_surface as surface

logger = logging.getLogger("acervator.gui")

ACCESSIBLE_NAME = "Paper"

PRIVACY_BUTTON_NAME = "paper-privacy-button"
NEWS_ROW_NAME = "paper-news-ticker-row"
POOL_ROW_NAME = "paper-data-pool-row"
SYMBOL_LABEL_NAME = "paper-symbol-label"
SYMBOL_SELECTOR_NAME = "paper-symbol-selector"
FLEET_LABEL_NAME = "paper-fleet-label"
FLEET_TABLE_NAME = "paper-fleet-table"
FLEET_EMPTY_NAME = "paper-fleet-empty"
INDICATOR_PANE_NAME = "paper-indicator-pane"
INDICATOR_TITLE_NAME = "paper-indicator-title"
INDICATOR_SUMMARY_NAME = "paper-indicator-summary"
INDICATOR_TABLE_NAMES = ("paper-indicator-table-a", "paper-indicator-table-b")
FEED_TITLE_NAME = "paper-feed-title"
FEED_LINES_NAME = "paper-feed-lines"
BALANCE_TITLE_NAME = "paper-balance-title"
BALANCE_TABLE_NAME = "paper-balance-table"
BALANCE_EMPTY_NAME = "paper-balance-empty"
LEDGER_TITLE_NAME = "paper-ledger-title"
LEDGER_FIGURES_NAME = "paper-ledger-figures"
LEDGER_OPENING_NAME = "paper-ledger-opening"
RUN_TITLE_NAME = "paper-run-title"
RUN_STATE_NAME = "paper-run-state"
RUN_LINES_NAME = "paper-run-lines"
RUN_TABLE_NAME = "paper-run-table"

FEED_MAX_BLOCKS = 400
RUN_MAX_BLOCKS = 2000

HEADING_STYLE = f"color: {ds.PRIMARY}; font-weight: bold;"
BODY_STYLE = f"color: {ds.TEXT_MED}; font-size: {ds.TYPE_CAPTION}px;"
VALUE_STYLE = f"color: {ds.TEXT_HIGH}; font-size: {ds.TYPE_BODY}px;"
EMPTY_STYLE = f"color: {ds.TEXT_EMPTY_STATE}; font-size: {ds.TYPE_BODY}px;"
PANEL_STYLE = f"QWidget {{ background: {ds.SURFACE_0}; }}"

SIDE_COLOURS = {"scrum": ds.SUCCESS, "fold": ds.ACCENT_GOLD}


def _colour(name: str) -> QColor:
    """A ``QColor`` for one of the surface's skin values."""
    return QColor(name)


class PaperTraderTabQt(QWidget):
    """The Paper tab: the Trading tab's panes over the live exchange feed."""

    def __init__(
        self,
        feed: Optional[LiveFeedSource] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Lay the panes out, then draw the live fleet with no run open."""
        super().__init__(parent)
        self.setObjectName(ACCESSIBLE_NAME)
        self.setAccessibleName(ACCESSIBLE_NAME)
        self.setStyleSheet(PANEL_STYLE)
        self._feed = feed if feed is not None else LiveFeedSource()
        self._bots: list = []
        self._run = None
        self._symbol = ""
        self._cursor = 0
        self._model: dict = {}
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self.advance_once)
        self._build()
        self.refresh()

    # -- what the window reads ------------------------------------------

    def model(self) -> dict:
        """A copy of the model the panes were last drawn from."""
        return dict(self._model)

    def symbol(self) -> str:
        """The market the Indicator Voting Panel is reading."""
        return str(self._model.get("symbol") or "")

    def run_state(self) -> str:
        """The run's state, one of ``paper_run.RUN_STATES``."""
        return str(self._model.get("run", {}).get("state") or "")

    def feed(self) -> LiveFeedSource:
        """The one data path this tab reads."""
        return self._feed

    # -- construction ---------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*surface.MARGINS_PX)
        outer.setSpacing(surface.SPACING_PX)

        self._top_splitter = QSplitter(Qt.Horizontal)
        self._top_splitter.setHandleWidth(surface.HANDLE_WIDTH_PX)
        self._top_splitter.setChildrenCollapsible(False)
        self._top_splitter.addWidget(self._build_fleet_pane())
        self._top_splitter.addWidget(self._build_indicator_pane())
        self._top_splitter.setSizes(surface.TOP_SPLITTER_SIZES)

        self._bottom_splitter = QSplitter(Qt.Horizontal)
        self._bottom_splitter.setHandleWidth(surface.HANDLE_WIDTH_PX)
        self._bottom_splitter.setChildrenCollapsible(False)
        self._bottom_splitter.addWidget(self._build_feed_pane())
        self._bottom_splitter.addWidget(self._build_run_pane())
        self._bottom_splitter.setSizes(surface.TOP_SPLITTER_SIZES)

        self._main_splitter = QSplitter(Qt.Vertical)
        self._main_splitter.setHandleWidth(surface.HANDLE_WIDTH_PX)
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.addWidget(self._top_splitter)
        self._main_splitter.addWidget(self._bottom_splitter)
        self._main_splitter.setSizes(surface.MAIN_SPLITTER_SIZES)
        outer.addWidget(self._main_splitter)

    def _build_fleet_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(*surface.MARGINS_PX)
        column.setSpacing(surface.SPACING_PX)

        header = QHBoxLayout()
        self._privacy_button = QPushButton(surface.PRIVACY_OFF_TEXT)
        self._privacy_button.setObjectName(PRIVACY_BUTTON_NAME)
        self._privacy_button.setAccessibleName(PRIVACY_BUTTON_NAME)
        self._privacy_button.setFocusPolicy(Qt.NoFocus)
        self._privacy_button.clicked.connect(self.toggle_privacy)
        header.addWidget(self._privacy_button)
        header.addStretch(1)
        column.addLayout(header)

        symbol_row = QHBoxLayout()
        self._symbol_label = QLabel(surface.SYMBOL_LABEL_TEXT)
        self._symbol_label.setObjectName(SYMBOL_LABEL_NAME)
        self._symbol_label.setAccessibleName(SYMBOL_LABEL_NAME)
        self._symbol_label.setStyleSheet(BODY_STYLE)
        symbol_row.addWidget(self._symbol_label)
        self._symbol_selector = QComboBox()
        self._symbol_selector.setObjectName(SYMBOL_SELECTOR_NAME)
        self._symbol_selector.setAccessibleName(SYMBOL_SELECTOR_NAME)
        self._symbol_selector.currentIndexChanged.connect(self._on_symbol_chosen)
        symbol_row.addWidget(self._symbol_selector, 1)
        column.addLayout(symbol_row)

        # The crypto news ticker and the data pool line are not copied; their
        # rows carry Import Live Fleet and the Start or Stop press.
        self._reserved_rows = []
        self._row_buttons = []
        presses = (self.import_live_fleet, self.toggle_run)
        for spec, name, press in zip(
            surface.reserved_rows(surface.IDLE),
            (NEWS_ROW_NAME, POOL_ROW_NAME),
            presses,
            strict=True,
        ):
            row = QWidget()
            row.setObjectName(name)
            row.setAccessibleName(name)
            row.setFixedHeight(int(spec["height_px"]))
            inner = QHBoxLayout(row)
            inner.setContentsMargins(0, 0, 0, 0)
            inner.setSpacing(surface.SPACING_PX)
            button = QPushButton(str(spec["text"]))
            button.setObjectName(str(spec["button_name"]))
            button.setAccessibleName(str(spec["button_name"]))
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(press)
            inner.addWidget(button)
            inner.addStretch(1)
            column.addWidget(row)
            self._reserved_rows.append(row)
            self._row_buttons.append(button)

        self._fleet_label = QLabel(surface.FLEET_LABEL_TEXT)
        self._fleet_label.setObjectName(FLEET_LABEL_NAME)
        self._fleet_label.setAccessibleName(FLEET_LABEL_NAME)
        self._fleet_label.setStyleSheet(HEADING_STYLE)
        column.addWidget(self._fleet_label)

        self._fleet_table = QTableWidget()
        self._fleet_table.setObjectName(FLEET_TABLE_NAME)
        self._fleet_table.setAccessibleName(FLEET_TABLE_NAME)
        self._fleet_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._fleet_table.verticalHeader().setVisible(False)
        column.addWidget(self._fleet_table, 1)

        self._fleet_empty = QLabel(surface.FLEET_EMPTY_TEXT)
        self._fleet_empty.setObjectName(FLEET_EMPTY_NAME)
        self._fleet_empty.setAccessibleName(FLEET_EMPTY_NAME)
        self._fleet_empty.setStyleSheet(EMPTY_STYLE)
        column.addWidget(self._fleet_empty)
        return pane

    def _build_indicator_pane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName(INDICATOR_PANE_NAME)
        pane.setAccessibleName(INDICATOR_PANE_NAME)
        column = QVBoxLayout(pane)
        column.setContentsMargins(*surface.MARGINS_PX)
        column.setSpacing(surface.SPACING_PX)

        head = QHBoxLayout()
        self._indicator_title = QLabel("")
        self._indicator_title.setObjectName(INDICATOR_TITLE_NAME)
        self._indicator_title.setAccessibleName(INDICATOR_TITLE_NAME)
        self._indicator_title.setStyleSheet(HEADING_STYLE)
        head.addWidget(self._indicator_title)
        head.addStretch(1)
        self._indicator_summary = QLabel("")
        self._indicator_summary.setObjectName(INDICATOR_SUMMARY_NAME)
        self._indicator_summary.setAccessibleName(INDICATOR_SUMMARY_NAME)
        self._indicator_summary.setStyleSheet(BODY_STYLE)
        head.addWidget(self._indicator_summary)
        column.addLayout(head)

        self._indicator_tables = []
        for name in INDICATOR_TABLE_NAMES:
            table = QTableWidget()
            table.setObjectName(name)
            table.setAccessibleName(name)
            table.setEditTriggers(QTableWidget.NoEditTriggers)
            table.verticalHeader().setVisible(False)
            column.addWidget(table)
            self._indicator_tables.append(table)
        column.addStretch(1)
        return pane

    def _build_feed_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(*surface.MARGINS_PX)
        column.setSpacing(surface.SPACING_PX)

        self._feed_title = QLabel(surface.FEED_TITLE)
        self._feed_title.setObjectName(FEED_TITLE_NAME)
        self._feed_title.setAccessibleName(FEED_TITLE_NAME)
        self._feed_title.setStyleSheet(HEADING_STYLE)
        column.addWidget(self._feed_title)

        self._feed_lines = QPlainTextEdit()
        self._feed_lines.setObjectName(FEED_LINES_NAME)
        self._feed_lines.setAccessibleName(FEED_LINES_NAME)
        self._feed_lines.setReadOnly(True)
        self._feed_lines.setMaximumBlockCount(FEED_MAX_BLOCKS)
        column.addWidget(self._feed_lines)

        self._ledger_title = QLabel(surface.LEDGER_TITLE)
        self._ledger_title.setObjectName(LEDGER_TITLE_NAME)
        self._ledger_title.setAccessibleName(LEDGER_TITLE_NAME)
        self._ledger_title.setStyleSheet(HEADING_STYLE)
        column.addWidget(self._ledger_title)

        self._ledger_figures = QLabel("")
        self._ledger_figures.setObjectName(LEDGER_FIGURES_NAME)
        self._ledger_figures.setAccessibleName(LEDGER_FIGURES_NAME)
        self._ledger_figures.setStyleSheet(VALUE_STYLE)
        column.addWidget(self._ledger_figures)

        self._ledger_opening = QLabel("")
        self._ledger_opening.setObjectName(LEDGER_OPENING_NAME)
        self._ledger_opening.setAccessibleName(LEDGER_OPENING_NAME)
        self._ledger_opening.setStyleSheet(BODY_STYLE)
        column.addWidget(self._ledger_opening)

        self._balance_title = QLabel(surface.BALANCE_TITLE)
        self._balance_title.setObjectName(BALANCE_TITLE_NAME)
        self._balance_title.setAccessibleName(BALANCE_TITLE_NAME)
        self._balance_title.setStyleSheet(HEADING_STYLE)
        column.addWidget(self._balance_title)

        self._balance_table = QTableWidget()
        self._balance_table.setObjectName(BALANCE_TABLE_NAME)
        self._balance_table.setAccessibleName(BALANCE_TABLE_NAME)
        self._balance_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._balance_table.verticalHeader().setVisible(False)
        column.addWidget(self._balance_table, 1)

        self._balance_empty = QLabel(surface.BALANCE_EMPTY_TEXT)
        self._balance_empty.setObjectName(BALANCE_EMPTY_NAME)
        self._balance_empty.setAccessibleName(BALANCE_EMPTY_NAME)
        self._balance_empty.setStyleSheet(EMPTY_STYLE)
        column.addWidget(self._balance_empty)
        return pane

    def _build_run_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(*surface.MARGINS_PX)
        column.setSpacing(surface.SPACING_PX)

        head = QHBoxLayout()
        self._run_title = QLabel(surface.RUN_TITLE)
        self._run_title.setObjectName(RUN_TITLE_NAME)
        self._run_title.setAccessibleName(RUN_TITLE_NAME)
        self._run_title.setStyleSheet(HEADING_STYLE)
        head.addWidget(self._run_title)
        head.addStretch(1)
        self._run_state = QLabel("")
        self._run_state.setObjectName(RUN_STATE_NAME)
        self._run_state.setAccessibleName(RUN_STATE_NAME)
        self._run_state.setStyleSheet(BODY_STYLE)
        head.addWidget(self._run_state)
        column.addLayout(head)

        self._run_lines = QPlainTextEdit()
        self._run_lines.setObjectName(RUN_LINES_NAME)
        self._run_lines.setAccessibleName(RUN_LINES_NAME)
        self._run_lines.setReadOnly(True)
        self._run_lines.setMaximumBlockCount(RUN_MAX_BLOCKS)
        column.addWidget(self._run_lines)

        self._run_table = QTableWidget()
        self._run_table.setObjectName(RUN_TABLE_NAME)
        self._run_table.setAccessibleName(RUN_TABLE_NAME)
        self._run_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._run_table.verticalHeader().setVisible(False)
        column.addWidget(self._run_table, 1)
        return pane

    # -- what the operator presses --------------------------------------

    def import_live_fleet(self) -> int:
        """Read the fleet from ``bot_state.json`` and draw it."""
        self._bots = surface.live_fleet()
        self.refresh()
        return len(self._bots)

    def toggle_run(self) -> str:
        """Start the run when none is running, otherwise stop it."""
        if self._run is not None and self._run.running:
            return self.stop_run()
        return self.start_run()

    def start_run(self) -> str:
        """Open the run and tick one bot per timer fire from now."""
        if not self._bots:
            self._bots = surface.live_fleet()
        self._run = surface.start_run(self._bots)
        self._cursor = 0
        self.advance_once()
        self._tick_timer.start(surface.tick_interval_ms(self._run, self._symbol))
        return self._run.state

    def stop_run(self) -> str:
        """Stop the wall-clock timer; the balances and trades stay readable."""
        self._tick_timer.stop()
        if self._run is not None:
            surface.stop_run(self._run)
        self.refresh()
        return "" if self._run is None else self._run.state

    def advance_once(self) -> list:
        """Tick the next open bot against its newest live window."""
        if self._run is None or not self._run.running or not self._run.bots:
            return []
        chosen = self._run.bots[self._cursor % len(self._run.bots)].bot_id
        self._cursor += 1
        made = surface.advance_run(self._run, self._feed, chosen)
        self.refresh()
        return made

    def choose_symbol(self, symbol: str) -> str:
        """Draw the market ``symbol`` names in the Indicator Voting Panel."""
        self._symbol = str(symbol or "")
        self.refresh()
        return self._symbol

    def toggle_privacy(self) -> bool:
        """Flip every registered privacy field and redraw the button."""
        masked = surface.toggle_privacy()
        self.refresh()
        return masked

    def _on_symbol_chosen(self, index: int) -> None:
        chosen = str(self._symbol_selector.itemData(index) or "")
        if chosen and chosen != self._symbol:
            self.choose_symbol(chosen)

    # -- drawing --------------------------------------------------------

    def refresh(self) -> dict:
        """Re-read the live feed and draw every pane from the new model."""
        self._model = surface.build_view_model(
            self._feed, self._bots, self._run, self._symbol
        )
        self._draw(self._model)
        return self._model

    def _draw(self, model: dict) -> None:
        self._privacy_button.setText(model["privacy_button"]["text"])
        self._symbol_label.setText(model["panes"]["symbol_label_text"])
        self._draw_reserved_rows(model["reserved_rows"])
        self._draw_symbol_selector(model)
        self._draw_fleet(model["fleet"])
        self._draw_indicators(model["indicators"])
        self._draw_feed(model["feed"])
        self._draw_ledger(model["ledger"])
        self._draw_balance(model["balance"])
        self._draw_run(model["run"])

    def _draw_reserved_rows(self, rows: list) -> None:
        for button, spec in zip(self._row_buttons, rows, strict=True):
            button.setText(str(spec["text"]))
            button.setObjectName(str(spec["button_name"]))
            button.setAccessibleName(str(spec["button_name"]))

    def _draw_symbol_selector(self, model: dict) -> None:
        selector = self._symbol_selector
        selector.blockSignals(True)
        selector.clear()
        for row in model["symbols"]:
            selector.addItem(f"{row['symbol']} {row['timeframe']}", row["symbol"])
        chosen = str(model["symbol"] or "")
        if chosen:
            found = selector.findData(chosen)
            if found >= 0:
                selector.setCurrentIndex(found)
            self._symbol = chosen
        selector.blockSignals(False)

    def _draw_fleet(self, fleet: dict) -> None:
        table = self._fleet_table
        table.setColumnCount(fleet["column_count"])
        table.setHorizontalHeaderLabels(list(fleet["columns"]))
        table.setRowCount(fleet["row_count"])
        header = table.horizontalHeader()
        for index_text, width in fleet["fixed_widths"].items():
            index = int(index_text)
            header.setSectionResizeMode(index, QHeaderView.Fixed)
            table.setColumnWidth(index, int(width))
        for row_index, row in enumerate(fleet["rows"]):
            for cell_index, cell in enumerate(row["cells"]):
                table.setItem(row_index, cell_index, QTableWidgetItem(str(cell)))
        self._fleet_empty.setText(fleet["empty_text"])
        self._fleet_empty.setVisible(fleet["row_count"] == 0)

    def _draw_indicators(self, panel: dict) -> None:
        self._indicator_title.setText(panel["title_text"])
        self._indicator_summary.setText(panel["summary_text"])
        for table, spec in zip(self._indicator_tables, panel["tables"], strict=True):
            self._fill_indicator_table(table, spec)

    def _fill_indicator_table(self, table: QTableWidget, spec: dict) -> None:
        titles = list(spec["titles"])
        rows = list(spec["rows"])
        table.setColumnCount(len(titles))
        table.setHorizontalHeaderLabels(titles)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for cell_index, cell in enumerate(row["cells"]):
                item = QTableWidgetItem(str(cell.get("text", "")))
                tooltip = cell.get("tooltip")
                if tooltip:
                    item.setToolTip(str(tooltip))
                colour = cell.get("text_color")
                if colour:
                    item.setForeground(_colour(str(colour)))
                table.setItem(row_index, cell_index, item)

    def _draw_feed(self, payload: dict) -> None:
        self._feed_title.setText(payload["title"])
        self._feed_lines.setPlainText("\n".join(payload["lines"]))

    def _draw_ledger(self, payload: dict) -> None:
        self._ledger_title.setText(payload["title"])
        self._ledger_figures.setText(
            payload["text"] if payload["opened"] else payload["empty_text"]
        )
        self._ledger_opening.setText(payload["opening_text"])

    def _draw_balance(self, payload: dict) -> None:
        self._balance_title.setText(payload["title"])
        titles = list(payload["columns"])
        rows = list(payload["rows"])
        table = self._balance_table
        table.setColumnCount(len(titles))
        table.setHorizontalHeaderLabels(titles)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for cell_index, cell in enumerate(row["cells"]):
                table.setItem(row_index, cell_index, QTableWidgetItem(str(cell)))
        self._balance_empty.setText(payload["empty_text"])
        self._balance_empty.setVisible(payload["row_count"] == 0)

    def _draw_run(self, payload: dict) -> None:
        self._run_title.setText(payload["title"])
        self._run_state.setText(payload["state_text"])
        self._run_lines.setPlainText("\n".join(payload["lines"]))
        titles = list(payload["columns"])
        rows = list(payload["rows"])
        table = self._run_table
        table.setColumnCount(len(titles))
        table.setHorizontalHeaderLabels(titles)
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            colour = _colour(SIDE_COLOURS.get(row["side"], ds.TEXT_MED))
            for cell_index, cell in enumerate(row["cells"]):
                item = QTableWidgetItem(str(cell))
                item.setForeground(colour)
                table.setItem(row_index, cell_index, item)

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Stop the wall-clock timer before the tab goes away."""
        self._tick_timer.stop()
        super().closeEvent(event)


def build_paper_trader_tab(
    feed: Optional[LiveFeedSource] = None,
) -> PaperTraderTabQt:
    """One ``PaperTraderTabQt`` over ``feed``, or over a fresh
    ``LiveFeedSource``."""
    return PaperTraderTabQt(feed)
