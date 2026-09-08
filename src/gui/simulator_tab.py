# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Sim tab in Qt: the Trading tab's panes, fed by Stone Tablets.

``SimulatorTabQt`` lays out the clone ``simulator_tab_surface`` describes and
draws every value from that model: the Privacy Mode row, the two reserved rows,
the bot list, the Indicator Voting Panel, and the layer holding ``VwapView``
over ``PlaybackView``. ``LineView`` and ``PlaybackView`` scale the surface's
unit-square points to their own pixels and paint nothing they were not given.
``refresh`` re-reads the tablet through ``TabletSource``, the one data path,
which answers no send.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..simulator.tablet_source import TabletSource
from . import design_system as ds
from .main_tabs import simulator_tab_surface as surface

logger = logging.getLogger("acervator.gui")

ACCESSIBLE_NAME = "Sim"

PRIVACY_BUTTON_NAME = "sim-privacy-button"
NEWS_ROW_NAME = "sim-news-ticker-row"
POOL_ROW_NAME = "sim-data-pool-row"
FLEET_LABEL_NAME = "sim-fleet-label"
FLEET_TABLE_NAME = "sim-fleet-table"
FLEET_EMPTY_NAME = "sim-fleet-empty"
TABLET_LABEL_NAME = "sim-tablet-label"
TABLET_SELECTOR_NAME = "sim-tablet-selector"
FLIP_BUTTON_NAME = "sim-flip-button"
INDICATOR_PANE_NAME = "sim-indicator-pane"
INDICATOR_TITLE_NAME = "sim-indicator-title"
INDICATOR_SUMMARY_NAME = "sim-indicator-summary"
INDICATOR_TABLE_NAMES = ("sim-indicator-table-a", "sim-indicator-table-b")
VWAP_VIEW_NAME = "sim-vwap-view"
PLAYBACK_VIEW_NAME = "sim-playback-view"
REPLAY_LOG_NAME = "sim-replay-log"
REPLAY_TITLE_NAME = "sim-replay-title"
FLEET_BUTTON_NAMES = ("sim-import-live-fleet", "sim-generate-from-ytd")
VALIDATION_TITLE_NAME = "sim-validation-title"
VALIDATION_LINES_NAME = "sim-validation-lines"
VALIDATION_PROMPT_NAME = "sim-validation-prompt"
VALIDATION_TABLE_NAME = "sim-validation-table"
VALIDATION_LIGHTS_NAME = "sim-validation-lights"

VALIDATION_COLUMNS = (
    "Bot ID",
    "Symbol",
    "Trade",
    "Candle",
    "Gate row",
    "Lights agreed",
    "Latches",
)
LIGHT_COLUMNS = ("Bank", "Gate", "Recorded", "Rerun", "Driven by")

CHART_MIN_HEIGHT_PX = 120
LINE_WIDTH_PX = 2
WICK_WIDTH_PX = 1
CANDLE_BODY_MIN_PX = 1.0
CANDLE_GAP_RATIO = 0.7
REPLAY_MAX_BLOCKS = 2000

HEADING_STYLE = f"color: {ds.PRIMARY}; font-weight: bold;"
BODY_STYLE = f"color: {ds.TEXT_MED}; font-size: {ds.TYPE_CAPTION}px;"
EMPTY_STYLE = f"color: {ds.TEXT_EMPTY_STATE}; font-size: {ds.TYPE_BODY}px;"
PANEL_STYLE = f"QWidget {{ background: {ds.SURFACE_0}; }}"


def _colour(name: str) -> QColor:
    """A ``QColor`` for one of the surface's skin values."""
    return QColor(name)


class LineView(QWidget):
    """The VWAP window: the close line and the VWAP line over one price span."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Start with no points and the surface's empty payload."""
        super().__init__(parent)
        self.setObjectName(VWAP_VIEW_NAME)
        self.setAccessibleName(VWAP_VIEW_NAME)
        self.setMinimumHeight(CHART_MIN_HEIGHT_PX)
        self._payload: dict = surface.vwap_payload([])

    def set_payload(self, payload: dict) -> None:
        """Take one ``vwap_payload`` and repaint."""
        self._payload = dict(payload)
        self.update()

    def payload(self) -> dict:
        """The payload the view last took."""
        return dict(self._payload)

    def _draw_line(self, painter: QPainter, points: list, colour: QColor) -> None:
        painter.setPen(QPen(colour, LINE_WIDTH_PX))
        width = float(self.width())
        height = float(self.height())
        run: list[QPointF] = []
        for point in points:
            if point is None:
                run = []
                continue
            run.append(QPointF(point[0] * width, point[1] * height))
            if len(run) >= 2:
                painter.drawLine(run[-2], run[-1])

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        """Fill the ground, then draw the close line and the VWAP line."""
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), _colour(ds.SURFACE_CHART))
        self._draw_line(
            painter, self._payload.get("close_points") or [], _colour(ds.TEXT_HIGH)
        )
        self._draw_line(
            painter, self._payload.get("vwap_points") or [], _colour(ds.ACCENT_GOLD)
        )
        painter.end()


class PlaybackView(QWidget):
    """The Stone Tablet playback window: one candle per surface shape."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Start with no candles and the surface's empty payload."""
        super().__init__(parent)
        self.setObjectName(PLAYBACK_VIEW_NAME)
        self.setAccessibleName(PLAYBACK_VIEW_NAME)
        self.setMinimumHeight(CHART_MIN_HEIGHT_PX)
        self._payload: dict = surface.playback_payload([])

    def set_payload(self, payload: dict) -> None:
        """Take one ``playback_payload`` and repaint."""
        self._payload = dict(payload)
        self.update()

    def payload(self) -> dict:
        """The payload the view last took."""
        return dict(self._payload)

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        """Fill the ground, then draw each candle's wick and body."""
        del event
        painter = QPainter(self)
        painter.fillRect(self.rect(), _colour(ds.SURFACE_CHART))
        shapes = self._payload.get("candles") or []
        width = float(self.width())
        height = float(self.height())
        column_px = width / max(len(shapes), 1)
        body_px = max(CANDLE_BODY_MIN_PX, column_px * CANDLE_GAP_RATIO)
        for shape in shapes:
            colour = _colour(ds.SUCCESS if shape["up"] else ds.ERROR)
            x = shape["x"] * width
            painter.setPen(QPen(colour, WICK_WIDTH_PX))
            painter.drawLine(
                QPointF(x, shape["wick_top"] * height),
                QPointF(x, shape["wick_bottom"] * height),
            )
            top = shape["body_top"] * height
            bottom = shape["body_bottom"] * height
            painter.fillRect(
                int(x - body_px / 2.0),
                int(top),
                max(int(body_px), 1),
                max(int(bottom - top), 1),
                colour,
            )
        painter.end()


class SimulatorTabQt(QWidget):
    """The Sim tab: the Trading tab's panes over one Stone Tablet."""

    def __init__(
        self,
        source: Optional[TabletSource] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Lay the panes out, then draw the newest tablet."""
        super().__init__(parent)
        self.setObjectName(ACCESSIBLE_NAME)
        self.setAccessibleName(ACCESSIBLE_NAME)
        self.setStyleSheet(PANEL_STYLE)
        self._source = source if source is not None else TabletSource()
        self._layer = surface.LAYER_INDICATORS
        self._tablet_key = ""
        self._model: dict = {}
        self._validation: Optional[dict] = None
        self._build()
        self.refresh()

    # -- what the window reads ------------------------------------------

    def model(self) -> dict:
        """A copy of the model the panes were last drawn from."""
        return dict(self._model)

    def layer(self) -> str:
        """The layer the stack is showing, ``indicators`` or ``playback``."""
        return self._layer

    def tablet_key(self) -> str:
        """The key of the tablet the windows are drawn from."""
        found = self._model.get("tablet")
        return str(found["key"]) if found else ""

    # -- construction ---------------------------------------------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(*surface.MARGINS_PX)
        outer.setSpacing(surface.SPACING_PX)

        self._main_splitter = QSplitter(Qt.Vertical)
        self._main_splitter.setHandleWidth(surface.HANDLE_WIDTH_PX)
        self._main_splitter.setChildrenCollapsible(False)

        self._top_splitter = QSplitter(Qt.Horizontal)
        self._top_splitter.setHandleWidth(surface.HANDLE_WIDTH_PX)
        self._top_splitter.setChildrenCollapsible(False)
        self._top_splitter.addWidget(self._build_fleet_pane())
        self._top_splitter.addWidget(self._build_layer_pane())
        self._top_splitter.setSizes(surface.TOP_SPLITTER_SIZES)

        self._bottom_splitter = QSplitter(Qt.Horizontal)
        self._bottom_splitter.setHandleWidth(surface.HANDLE_WIDTH_PX)
        self._bottom_splitter.setChildrenCollapsible(False)
        self._bottom_splitter.addWidget(self._build_replay_pane())
        self._bottom_splitter.addWidget(self._build_validation_pane())
        self._bottom_splitter.setSizes(surface.LAYER_SPLITTER_SIZES)

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
        self._privacy_button = QPushButton(surface.PRIVACY_BUTTON_TEXT)
        self._privacy_button.setObjectName(PRIVACY_BUTTON_NAME)
        self._privacy_button.setAccessibleName(PRIVACY_BUTTON_NAME)
        self._privacy_button.setFocusPolicy(Qt.NoFocus)
        self._privacy_button.clicked.connect(self.toggle_privacy)
        header.addWidget(self._privacy_button)
        header.addStretch(1)
        column.addLayout(header)

        # The crypto news ticker and the data pool line are not copied; their
        # rows carry Import Live Fleet and Generate From YTD instead.
        self._reserved_rows = []
        self._fleet_buttons = []
        row_names = (NEWS_ROW_NAME, POOL_ROW_NAME)
        presses = (self.import_live_fleet, self.generate_from_ytd)
        for spec, name, button_name, press in zip(
            surface.RESERVED_ROWS, row_names, FLEET_BUTTON_NAMES, presses, strict=True
        ):
            row = QWidget()
            row.setObjectName(name)
            row.setAccessibleName(name)
            row.setFixedHeight(int(spec["height_px"]))
            inner = QHBoxLayout(row)
            inner.setContentsMargins(0, 0, 0, 0)
            inner.setSpacing(surface.SPACING_PX)
            button = QPushButton(str(spec["text"]))
            button.setObjectName(button_name)
            button.setAccessibleName(button_name)
            button.setFocusPolicy(Qt.NoFocus)
            button.clicked.connect(press)
            inner.addWidget(button)
            inner.addStretch(1)
            column.addWidget(row)
            self._reserved_rows.append(row)
            self._fleet_buttons.append(button)

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

    def _build_layer_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(*surface.MARGINS_PX)
        column.setSpacing(surface.SPACING_PX)

        row = QHBoxLayout()
        self._tablet_label = QLabel(surface.TABLET_LABEL_TEXT)
        self._tablet_label.setObjectName(TABLET_LABEL_NAME)
        self._tablet_label.setAccessibleName(TABLET_LABEL_NAME)
        self._tablet_label.setStyleSheet(BODY_STYLE)
        row.addWidget(self._tablet_label)
        self._tablet_selector = QComboBox()
        self._tablet_selector.setObjectName(TABLET_SELECTOR_NAME)
        self._tablet_selector.setAccessibleName(TABLET_SELECTOR_NAME)
        self._tablet_selector.currentIndexChanged.connect(self._on_tablet_chosen)
        row.addWidget(self._tablet_selector, 1)
        self._flip_button = QPushButton(
            surface.FLIP_BUTTON_TEXT[surface.LAYER_INDICATORS]
        )
        self._flip_button.setObjectName(FLIP_BUTTON_NAME)
        self._flip_button.setAccessibleName(FLIP_BUTTON_NAME)
        self._flip_button.clicked.connect(self.flip_layer)
        row.addWidget(self._flip_button)
        column.addLayout(row)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_indicator_pane())
        self._stack.addWidget(self._build_chart_pane())
        column.addWidget(self._stack, 1)
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

    def _build_chart_pane(self) -> QWidget:
        self._layer_splitter = QSplitter(Qt.Vertical)
        self._layer_splitter.setHandleWidth(surface.HANDLE_WIDTH_PX)
        self._layer_splitter.setChildrenCollapsible(False)
        self._vwap_view = LineView()
        self._playback_view = PlaybackView()
        self._layer_splitter.addWidget(self._vwap_view)
        self._layer_splitter.addWidget(self._playback_view)
        self._layer_splitter.setSizes(surface.LAYER_SPLITTER_SIZES)
        return self._layer_splitter

    def _build_replay_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(*surface.MARGINS_PX)
        column.setSpacing(surface.SPACING_PX)
        self._replay_title = QLabel(surface.REPLAY_LOG_TITLE)
        self._replay_title.setObjectName(REPLAY_TITLE_NAME)
        self._replay_title.setAccessibleName(REPLAY_TITLE_NAME)
        self._replay_title.setStyleSheet(HEADING_STYLE)
        column.addWidget(self._replay_title)
        self._replay_log = QPlainTextEdit()
        self._replay_log.setObjectName(REPLAY_LOG_NAME)
        self._replay_log.setAccessibleName(REPLAY_LOG_NAME)
        self._replay_log.setReadOnly(True)
        self._replay_log.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._replay_log.setMaximumBlockCount(REPLAY_MAX_BLOCKS)
        column.addWidget(self._replay_log, 1)
        return pane

    def _build_validation_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(*surface.MARGINS_PX)
        column.setSpacing(surface.SPACING_PX)

        self._validation_title = QLabel(surface.VALIDATION_TITLE)
        self._validation_title.setObjectName(VALIDATION_TITLE_NAME)
        self._validation_title.setAccessibleName(VALIDATION_TITLE_NAME)
        self._validation_title.setStyleSheet(HEADING_STYLE)
        column.addWidget(self._validation_title)

        self._validation_prompt = QLabel("")
        self._validation_prompt.setObjectName(VALIDATION_PROMPT_NAME)
        self._validation_prompt.setAccessibleName(VALIDATION_PROMPT_NAME)
        self._validation_prompt.setStyleSheet(EMPTY_STYLE)
        column.addWidget(self._validation_prompt)

        self._validation_lines = QPlainTextEdit()
        self._validation_lines.setObjectName(VALIDATION_LINES_NAME)
        self._validation_lines.setAccessibleName(VALIDATION_LINES_NAME)
        self._validation_lines.setReadOnly(True)
        self._validation_lines.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._validation_lines.setMaximumBlockCount(REPLAY_MAX_BLOCKS)
        column.addWidget(self._validation_lines)

        self._validation_table = QTableWidget()
        self._validation_table.setObjectName(VALIDATION_TABLE_NAME)
        self._validation_table.setAccessibleName(VALIDATION_TABLE_NAME)
        self._validation_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._validation_table.verticalHeader().setVisible(False)
        column.addWidget(self._validation_table, 1)

        self._validation_lights = QTableWidget()
        self._validation_lights.setObjectName(VALIDATION_LIGHTS_NAME)
        self._validation_lights.setAccessibleName(VALIDATION_LIGHTS_NAME)
        self._validation_lights.setEditTriggers(QTableWidget.NoEditTriggers)
        self._validation_lights.verticalHeader().setVisible(False)
        column.addWidget(self._validation_lights, 1)
        return pane

    # -- what the operator presses --------------------------------------

    def import_live_fleet(self) -> dict:
        """Clone the live fleet from bot_state and validate it."""
        return self.run_validation(surface.IMPORT_LIVE_FLEET_ACTION)

    def generate_from_ytd(self) -> dict:
        """Build a fleet from the YTD trade files and validate it."""
        return self.run_validation(surface.GENERATE_FROM_YTD_ACTION)

    def run_validation(self, origin: str, exchange_id: str = "") -> dict:
        """Run ``origin``'s fleet against the record and redraw the pane."""
        self._validation = surface.run_validation(origin, exchange_id)
        self.refresh()
        return dict(self._validation)

    def validation(self) -> dict:
        """The Validation payload the pane was last drawn from."""
        return dict(self._model.get("validation") or {})

    def toggle_privacy(self) -> bool:
        """Flip every registered privacy field and redraw the button."""
        masked = surface.toggle_privacy()
        self.refresh()
        return masked

    def flip_layer(self) -> str:
        """Swap the stack between the panel layer and the chart layer."""
        self._layer = (
            surface.LAYER_PLAYBACK
            if self._layer == surface.LAYER_INDICATORS
            else surface.LAYER_INDICATORS
        )
        self.refresh()
        return self._layer

    def _on_tablet_chosen(self, index: int) -> None:
        key = str(self._tablet_selector.itemData(index) or "")
        if key and key != self._tablet_key:
            self._tablet_key = key
            self.refresh()

    # -- drawing --------------------------------------------------------

    def refresh(self) -> dict:
        """Re-read the tablet and draw every pane from the new model."""
        self._model = surface.build_view_model(
            self._source, self._tablet_key, self._layer, self._validation
        )
        self._draw(self._model)
        return self._model

    def _draw(self, model: dict) -> None:
        self._privacy_button.setText(model["privacy_button"]["text"])
        self._flip_button.setText(model["panes"]["flip_button_text"])
        self._stack.setCurrentIndex(model["layers"].index(model["layer"]))
        self._draw_fleet(model["fleet"])
        self._draw_selector(model)
        self._draw_indicators(model["indicators"])
        self._vwap_view.set_payload(model["vwap"])
        self._playback_view.set_payload(model["playback"])
        self._replay_log.setPlainText("\n".join(model["replay_log"]["lines"]))
        self._draw_validation(model["validation"])

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

    def _draw_validation(self, payload: dict) -> None:
        self._validation_title.setText(payload["title"])
        self._validation_prompt.setText(payload["prompt_text"])
        self._validation_prompt.setVisible(bool(payload["prompt_text"]))
        self._validation_lines.setPlainText("\n".join(payload["lines"]))
        rows = list(payload["rows"])
        table = self._validation_table
        table.setColumnCount(len(VALIDATION_COLUMNS))
        table.setHorizontalHeaderLabels(list(VALIDATION_COLUMNS))
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            cells = (
                row["bot_id"],
                row["symbol"],
                row["trade_at"],
                row["candle_at"],
                row["gate_at"],
                f"{row['agreed']} of {row['light_count']}",
                "yes" if row["latches_identically"] else "no",
            )
            for cell_index, cell in enumerate(cells):
                table.setItem(index, cell_index, QTableWidgetItem(str(cell)))
        self._draw_lights(rows[0]["lights"] if rows else [])

    def _draw_lights(self, lights: list) -> None:
        table = self._validation_lights
        table.setColumnCount(len(LIGHT_COLUMNS))
        table.setHorizontalHeaderLabels(list(LIGHT_COLUMNS))
        table.setRowCount(len(lights))
        for index, light in enumerate(lights):
            cells = (
                light["bank"],
                light["label"],
                light["recorded"],
                light["rerun"],
                light["driven_by"],
            )
            colour = _colour(
                ds.SUCCESS if light["agrees"] else ds.ERROR
            )
            for cell_index, cell in enumerate(cells):
                item = QTableWidgetItem(str(cell))
                item.setForeground(colour)
                table.setItem(index, cell_index, item)

    def _draw_selector(self, model: dict) -> None:
        selector = self._tablet_selector
        selector.blockSignals(True)
        selector.clear()
        for row in model["tablets"]:
            selector.addItem(
                f"{row['asset']} {row['year']} {row['exchange_id']}", row["key"]
            )
        chosen = model.get("tablet")
        if chosen is not None:
            found = selector.findData(chosen["key"])
            if found >= 0:
                selector.setCurrentIndex(found)
            self._tablet_key = str(chosen["key"])
        selector.blockSignals(False)

    def _draw_indicators(self, panel: dict) -> None:
        self._indicator_title.setText(panel["title_text"])
        self._indicator_summary.setText(panel["summary_text"])
        for table, spec in zip(
            self._indicator_tables, panel["tables"], strict=True
        ):
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


def build_simulator_tab(source: Optional[TabletSource] = None) -> SimulatorTabQt:
    """One ``SimulatorTabQt`` over ``source``, or over the RA tablet root."""
    return SimulatorTabQt(source)
