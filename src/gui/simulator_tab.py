# Copyright (c) 2025 Anthony L. Brown (Ekthelius the Accumulator). All rights reserved.
"""The Sim tab in Qt: the Trading tab's panes, fed by Stone Tablets.

``SimulatorTabQt`` lays out the clone ``simulator_tab_surface`` describes and
draws every value from that model: the Privacy Mode row, the mode selector, the
two reserved rows, the bot list, the Indicator Voting Panel, and the layer
holding ``VwapView`` over ``PlaybackView``. ``LineView`` and ``PlaybackView`` scale the surface's
unit-square points to their own pixels and paint nothing they were not given.
``refresh`` re-reads the tablet through ``TabletSource``, the one data path,
which answers no send.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
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
MODE_LABEL_NAME = "sim-mode-label"
MODE_SELECTOR_NAME = "sim-mode-selector"
BACK_TEST_TITLE_NAME = "sim-back-test-title"
BACK_TEST_LINES_NAME = "sim-back-test-lines"
BACK_TEST_TABLE_NAME = "sim-back-test-table"
BATTERY_ROW_NAME = "sim-battery-row"
PORTFOLIO_LABEL_NAME = "sim-portfolio-label"
PORTFOLIO_SELECTOR_NAME = "sim-portfolio-selector"
SPAN_LABEL_NAME = "sim-span-label"
SPAN_SELECTOR_NAME = "sim-span-selector"
BATTERY_TITLE_NAME = "sim-battery-title"
BATTERY_LINES_NAME = "sim-battery-lines"
BATTERY_TABLE_NAME = "sim-battery-table"
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
        colours = surface.replay_colours()
        painter.fillRect(self.rect(), _colour(colours["ground"]))
        self._draw_line(
            painter, self._payload.get("close_points") or [], _colour(colours["close"])
        )
        self._draw_line(
            painter, self._payload.get("vwap_points") or [], _colour(colours["vwap"])
        )
        painter.end()


class PlaybackView(QWidget):
    """The Stone Tablet playback window: one candle per surface shape, then
    one ``MARK_GLYPHS`` glyph per mark at its candle's x and its price's y."""

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
        colours = surface.replay_colours()
        painter.fillRect(self.rect(), _colour(colours["ground"]))
        shapes = self._payload.get("candles") or []
        width = float(self.width())
        height = float(self.height())
        column_px = width / max(len(shapes), 1)
        body_px = max(CANDLE_BODY_MIN_PX, column_px * CANDLE_GAP_RATIO)
        for shape in shapes:
            colour = _colour(colours["up"] if shape["up"] else colours["down"])
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
        self._draw_marks(painter, colours, column_px, width, height)
        painter.end()

    def _draw_marks(
        self,
        painter: QPainter,
        colours: dict,
        column_px: float,
        width: float,
        height: float,
    ) -> None:
        """Draw each payload mark as its ``MARK_GLYPHS`` polygon, ``mark_scrum``
        or ``mark_fold`` coloured, ``mark_width_ratio`` of ``column_px`` wide
        and ``mark_height_fraction`` of ``height`` tall."""
        glyphs = self._payload.get("glyphs") or {}
        mark_w = column_px * float(
            self._payload.get("mark_width_ratio", surface.MARK_WIDTH_RATIO)
        )
        mark_h = height * float(
            self._payload.get("mark_height_fraction", surface.MARK_HEIGHT_FRACTION)
        )
        outline = float(self._payload.get("mark_outline_px", surface.MARK_OUTLINE_PX))
        for mark in self._payload.get("marks") or []:
            glyph = glyphs.get(mark["side"])
            if glyph is None or mark.get("y") is None:
                continue
            centre_x = float(mark["x"]) * width
            centre_y = float(mark["y"]) * height
            polygon = QPolygonF(
                [
                    QPointF(centre_x + dx * mark_w, centre_y + dy * mark_h)
                    for dx, dy in glyph["points"]
                ]
            )
            colour = _colour(
                colours["mark_scrum"]
                if mark["side"] == surface.back_test.SCRUM
                else colours["mark_fold"]
            )
            painter.setPen(QPen(colour, outline))
            painter.setBrush(QBrush(colour) if glyph["filled"] else Qt.NoBrush)
            painter.drawPolygon(polygon)


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
        self._source = (
            source if source is not None else TabletSource(surface.TABLET_ROOT)
        )
        self._layer = surface.LAYER_INDICATORS
        self._mode = surface.MODE_VALIDATION
        self._tablet_key = ""
        self._model: dict = {}
        self._validation: Optional[dict] = None
        self._back_test: Optional[dict] = None
        self._battery: Optional[dict] = None
        self._portfolio = surface.DEFAULT_PORTFOLIO
        self._span = surface.DEFAULT_SPAN
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
        self._result_stack = QStackedWidget()
        self._result_stack.addWidget(self._build_validation_pane())
        self._result_stack.addWidget(self._build_back_test_pane())
        self._result_stack.addWidget(self._build_battery_pane())

        self._bottom_splitter.addWidget(self._build_replay_pane())
        self._bottom_splitter.addWidget(self._result_stack)
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

        mode_row = QHBoxLayout()
        self._mode_label = QLabel(surface.MODE_LABEL_TEXT)
        self._mode_label.setObjectName(MODE_LABEL_NAME)
        self._mode_label.setAccessibleName(MODE_LABEL_NAME)
        self._mode_label.setStyleSheet(BODY_STYLE)
        mode_row.addWidget(self._mode_label)
        self._mode_selector = QComboBox()
        self._mode_selector.setObjectName(MODE_SELECTOR_NAME)
        self._mode_selector.setAccessibleName(MODE_SELECTOR_NAME)
        for name in surface.MODES:
            self._mode_selector.addItem(surface.MODE_TEXT[name], name)
        self._mode_selector.currentIndexChanged.connect(self._on_mode_chosen)
        mode_row.addWidget(self._mode_selector, 1)
        column.addLayout(mode_row)
        column.addWidget(self._build_battery_row())

        # The crypto news ticker and the data pool line are not copied; their
        # rows carry the two ways into whichever mode is showing.
        self._reserved_rows = []
        self._fleet_buttons = []
        row_names = (NEWS_ROW_NAME, POOL_ROW_NAME)
        presses = (self.first_way_in, self.second_way_in)
        for spec, name, press in zip(
            surface.RESERVED_ROWS, row_names, presses, strict=True
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

    def _build_battery_row(self) -> QWidget:
        row = QWidget()
        row.setObjectName(BATTERY_ROW_NAME)
        row.setAccessibleName(BATTERY_ROW_NAME)
        inner = QHBoxLayout(row)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(surface.SPACING_PX)

        self._portfolio_label = QLabel(surface.PORTFOLIO_LABEL_TEXT)
        self._portfolio_label.setObjectName(PORTFOLIO_LABEL_NAME)
        self._portfolio_label.setAccessibleName(PORTFOLIO_LABEL_NAME)
        self._portfolio_label.setStyleSheet(BODY_STYLE)
        inner.addWidget(self._portfolio_label)

        self._portfolio_selector = QComboBox()
        self._portfolio_selector.setObjectName(PORTFOLIO_SELECTOR_NAME)
        self._portfolio_selector.setAccessibleName(PORTFOLIO_SELECTOR_NAME)
        for entry in surface.portfolio_rows():
            self._portfolio_selector.addItem(entry["name"], entry["name"])
        self._portfolio_selector.currentIndexChanged.connect(self._on_portfolio_chosen)
        inner.addWidget(self._portfolio_selector, 1)

        self._span_label = QLabel(surface.SPAN_LABEL_TEXT)
        self._span_label.setObjectName(SPAN_LABEL_NAME)
        self._span_label.setAccessibleName(SPAN_LABEL_NAME)
        self._span_label.setStyleSheet(BODY_STYLE)
        inner.addWidget(self._span_label)

        self._span_selector = QComboBox()
        self._span_selector.setObjectName(SPAN_SELECTOR_NAME)
        self._span_selector.setAccessibleName(SPAN_SELECTOR_NAME)
        for name in surface.BATTERY_SPANS:
            self._span_selector.addItem(name, name)
        self._span_selector.currentIndexChanged.connect(self._on_span_chosen)
        inner.addWidget(self._span_selector, 1)
        self._battery_row = row
        return row

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

    def _build_back_test_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(*surface.MARGINS_PX)
        column.setSpacing(surface.SPACING_PX)

        self._back_test_title = QLabel(surface.BACK_TEST_TITLE)
        self._back_test_title.setObjectName(BACK_TEST_TITLE_NAME)
        self._back_test_title.setAccessibleName(BACK_TEST_TITLE_NAME)
        self._back_test_title.setStyleSheet(HEADING_STYLE)
        column.addWidget(self._back_test_title)

        self._back_test_lines = QPlainTextEdit()
        self._back_test_lines.setObjectName(BACK_TEST_LINES_NAME)
        self._back_test_lines.setAccessibleName(BACK_TEST_LINES_NAME)
        self._back_test_lines.setReadOnly(True)
        self._back_test_lines.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._back_test_lines.setMaximumBlockCount(REPLAY_MAX_BLOCKS)
        column.addWidget(self._back_test_lines)

        self._back_test_table = QTableWidget()
        self._back_test_table.setObjectName(BACK_TEST_TABLE_NAME)
        self._back_test_table.setAccessibleName(BACK_TEST_TABLE_NAME)
        self._back_test_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._back_test_table.verticalHeader().setVisible(False)
        column.addWidget(self._back_test_table, 1)
        return pane

    def _build_battery_pane(self) -> QWidget:
        pane = QWidget()
        column = QVBoxLayout(pane)
        column.setContentsMargins(*surface.MARGINS_PX)
        column.setSpacing(surface.SPACING_PX)

        self._battery_title = QLabel(surface.BATTERY_TITLE)
        self._battery_title.setObjectName(BATTERY_TITLE_NAME)
        self._battery_title.setAccessibleName(BATTERY_TITLE_NAME)
        self._battery_title.setStyleSheet(HEADING_STYLE)
        column.addWidget(self._battery_title)

        self._battery_lines = QPlainTextEdit()
        self._battery_lines.setObjectName(BATTERY_LINES_NAME)
        self._battery_lines.setAccessibleName(BATTERY_LINES_NAME)
        self._battery_lines.setReadOnly(True)
        self._battery_lines.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._battery_lines.setMaximumBlockCount(REPLAY_MAX_BLOCKS)
        column.addWidget(self._battery_lines)

        self._battery_table = QTableWidget()
        self._battery_table.setObjectName(BATTERY_TABLE_NAME)
        self._battery_table.setAccessibleName(BATTERY_TABLE_NAME)
        self._battery_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._battery_table.verticalHeader().setVisible(False)
        column.addWidget(self._battery_table, 1)
        return pane

    # -- what the operator presses --------------------------------------

    def first_way_in(self) -> dict:
        """Clone the live fleet from bot_state and run the showing mode on
        it."""
        if self._mode == surface.MODE_PORTFOLIO_BATTERY:
            return self.run_mode(surface.RUN_PORTFOLIO_ACTION)
        return self.run_mode(surface.IMPORT_LIVE_FLEET_ACTION)

    def second_way_in(self) -> dict:
        """Run the showing mode's second way in: YTD, new bots, or every
        portfolio."""
        if self._mode == surface.MODE_BACK_TEST:
            return self.run_mode(surface.CREATE_NEW_BOTS_ACTION)
        if self._mode == surface.MODE_PORTFOLIO_BATTERY:
            return self.run_mode(surface.RUN_EVERY_PORTFOLIO_ACTION)
        return self.run_mode(surface.GENERATE_FROM_YTD_ACTION)

    def run_mode(self, origin: str, exchange_id: str = "") -> dict:
        """Run ``origin``'s fleet in the showing mode and redraw its pane."""
        if self._mode == surface.MODE_BACK_TEST:
            return self.run_back_test(origin, exchange_id)
        if self._mode == surface.MODE_PORTFOLIO_BATTERY:
            return self.run_battery(origin)
        return self.run_validation(origin, exchange_id)

    def import_live_fleet(self) -> dict:
        """Clone the live fleet from bot_state and validate it."""
        return self.run_validation(surface.IMPORT_LIVE_FLEET_ACTION)

    def generate_from_ytd(self) -> dict:
        """Build a fleet from the YTD trade files and validate it."""
        return self.run_validation(surface.GENERATE_FROM_YTD_ACTION)

    def create_new_bots(self) -> dict:
        """Make one simulated bot on the chosen tablet and back test it."""
        return self.run_back_test(surface.CREATE_NEW_BOTS_ACTION)

    def run_validation(self, origin: str, exchange_id: str = "") -> dict:
        """Run ``origin``'s fleet against the record and redraw the pane."""
        self._validation = surface.run_validation(origin, exchange_id)
        self.refresh()
        return dict(self._validation)

    def run_back_test(self, origin: str, exchange_id: str = "") -> dict:
        """Walk ``origin``'s fleet over the Stone Tablets and redraw the pane."""
        self._back_test = surface.run_back_test(
            origin, exchange_id, surface.new_bot_specs(self._chosen_entry())
        )
        self.refresh()
        return dict(self._back_test)

    def run_portfolio(self) -> dict:
        """Walk the chosen portfolio over the RA-StoneTablets."""
        return self.run_battery(surface.RUN_PORTFOLIO_ACTION)

    def run_every_portfolio(self) -> dict:
        """Walk every portfolio over the RA-StoneTablets."""
        return self.run_battery(surface.RUN_EVERY_PORTFOLIO_ACTION)

    def run_battery(self, origin: str) -> dict:
        """Run ``origin`` over the chosen span and redraw the battery pane."""
        self._battery = surface.run_battery(origin, self._portfolio, self._span)
        self.refresh()
        return dict(self._battery)

    def choose_portfolio(self, name: str) -> str:
        """Draw the portfolio ``name`` names on the next battery press."""
        self._portfolio = str(name or surface.DEFAULT_PORTFOLIO)
        self.refresh()
        return self._portfolio

    def choose_span(self, span: str) -> str:
        """Read the span ``span`` names on the next battery press."""
        self._span = str(span or surface.DEFAULT_SPAN)
        self.refresh()
        return self._span

    def battery(self) -> dict:
        """The Portfolio Battery payload the pane was last drawn from."""
        return dict(self._model.get("battery") or {})

    def _on_portfolio_chosen(self, index: int) -> None:
        chosen = str(self._portfolio_selector.itemData(index) or "")
        if chosen and chosen != self._portfolio:
            self.choose_portfolio(chosen)

    def _on_span_chosen(self, index: int) -> None:
        chosen = str(self._span_selector.itemData(index) or "")
        if chosen and chosen != self._span:
            self.choose_span(chosen)

    def _chosen_entry(self):
        """The tablet entry the selector is showing, or None."""
        return surface.chosen_entry(self._source, self._tablet_key)

    def validation(self) -> dict:
        """The Validation payload the pane was last drawn from."""
        return dict(self._model.get("validation") or {})

    def back_test(self) -> dict:
        """The Back Test payload the pane was last drawn from."""
        return dict(self._model.get("back_test") or {})

    def mode(self) -> str:
        """The mode the panes are showing, one of ``surface.MODES``."""
        return self._mode

    def choose_mode(self, mode: str) -> str:
        """Show ``mode``'s buttons and result pane."""
        self._mode = mode if mode in surface.MODES else surface.MODE_VALIDATION
        self.refresh()
        return self._mode

    def _on_mode_chosen(self, index: int) -> None:
        chosen = str(self._mode_selector.itemData(index) or "")
        if chosen and chosen != self._mode:
            self.choose_mode(chosen)

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
            self._source,
            self._tablet_key,
            self._layer,
            self._validation,
            self._mode,
            self._back_test,
            self._battery,
            self._portfolio,
            self._span,
        )
        self._draw(self._model)
        return self._model

    def _draw(self, model: dict) -> None:
        self._privacy_button.setText(model["privacy_button"]["text"])
        self._flip_button.setText(model["panes"]["flip_button_text"])
        self._mode_label.setText(model["panes"]["mode_label_text"])
        self._stack.setCurrentIndex(model["layers"].index(model["layer"]))
        self._result_stack.setCurrentIndex(surface.MODES.index(model["mode"]))
        self._draw_mode_selector(model["mode"])
        self._draw_reserved_rows(model["reserved_rows"])
        self._draw_fleet(model["fleet"])
        self._draw_selector(model)
        self._draw_indicators(model["indicators"])
        self._vwap_view.set_payload(model["vwap"])
        self._playback_view.set_payload(model["playback"])
        self._replay_log.setPlainText("\n".join(model["replay_log"]["lines"]))
        self._draw_validation(model["validation"])
        self._draw_back_test(model["back_test"])
        self._draw_battery(model["battery"], model["panes"])

    def _draw_mode_selector(self, mode: str) -> None:
        selector = self._mode_selector
        selector.blockSignals(True)
        found = selector.findData(mode)
        if found >= 0:
            selector.setCurrentIndex(found)
        selector.blockSignals(False)

    def _draw_reserved_rows(self, rows: list) -> None:
        for button, spec in zip(self._fleet_buttons, rows, strict=True):
            button.setText(str(spec["text"]))
            button.setObjectName(str(spec["button_name"]))
            button.setAccessibleName(str(spec["button_name"]))

    def _draw_back_test(self, payload: dict) -> None:
        self._back_test_title.setText(payload["title"])
        self._back_test_lines.setPlainText("\n".join(payload["lines"]))
        rows = list(payload["rows"])
        titles = list(payload["columns"])
        table = self._back_test_table
        table.setColumnCount(len(titles))
        table.setHorizontalHeaderLabels(titles)
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            cells = (
                row["bot_id"],
                row["symbol"],
                row["tablet_key"],
                row["candles_read"],
                row["ticks"],
                f"{row['scrum_latched']} / {row['fold_latched']}",
                f"{row['scrum_trades']} / {row['fold_trades']}",
                row["units_text"],
                row["cash_text"],
            )
            for cell_index, cell in enumerate(cells):
                table.setItem(index, cell_index, QTableWidgetItem(str(cell)))

    def _draw_battery(self, payload: dict, panes: dict) -> None:
        self._battery_title.setText(payload["title"])
        self._battery_lines.setPlainText("\n".join(payload["lines"]))
        self._portfolio_label.setText(panes["portfolio_label_text"])
        self._span_label.setText(panes["span_label_text"])
        self._battery_row.setVisible(bool(panes["battery_row_shown"]))
        self._draw_battery_selectors(payload)
        rows = list(payload["rows"])
        titles = list(payload["columns"])
        table = self._battery_table
        table.setColumnCount(len(titles))
        table.setHorizontalHeaderLabels(titles)
        table.setRowCount(len(rows))
        for index, row in enumerate(rows):
            cells = (
                row["portfolio"],
                row["timeframe"],
                row["span_text"],
                row["symbols_text"],
                row["bars"],
                row["ticks"],
                row["trades"],
                row["baseline_text"],
                row["accumulation_text"],
                row["improvement_text"],
                row["missing_text"],
            )
            colour = _colour(
                ds.SUCCESS if row["verdict"] == surface.BETTER_VERDICT else ds.TEXT_MED
            )
            for cell_index, cell in enumerate(cells):
                item = QTableWidgetItem(str(cell))
                item.setForeground(colour)
                table.setItem(index, cell_index, item)

    def _draw_battery_selectors(self, payload: dict) -> None:
        for selector, chosen in (
            (self._portfolio_selector, payload["portfolio"]),
            (self._span_selector, payload["span"]),
        ):
            selector.blockSignals(True)
            found = selector.findData(chosen)
            if found >= 0:
                selector.setCurrentIndex(found)
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
            colour = _colour(ds.SUCCESS if light["agrees"] else ds.ERROR)
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
        # no_data text is empty while the panel holds a reading, so the
        # summary label shows only the one reason there is nothing to draw.
        reason = panel["no_data"]["text"]
        self._indicator_summary.setText(reason)
        self._indicator_summary.setVisible(bool(reason))
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


def build_simulator_tab(source: Optional[TabletSource] = None) -> SimulatorTabQt:
    """One ``SimulatorTabQt`` over ``source``, or over the RA tablet root."""
    return SimulatorTabQt(source)
