"""The shipped analytics tab and the Qt-free surface, side by side.

A failure means the view model carries a different card, a different
label, a different number, a different colour, a different column, a
different table cell, a different chart geometry or a different layout
number than ``src.gui.analytics_tab`` draws.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import analytics_tab as shipped
from src.gui import design_system as ds
from src.gui.main_tabs import analytics_tab_surface as surface
from src.trading.analytics_engine import AnalyticsEngine, BotPerformance
from tests.fixtures.host_fonts import has_real_fonts
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


METHOD_NAME = "analytics.tab"

PIXEL_SIZE = (980, 700)
CHART_SIZE = (520, 260)
CARD_SIZE = (140, 70)
GROUP_SIZE = (460, 300)

CARD_TOTAL = 8
BOT_COLUMN_TOTAL = 10
TIMEFRAME_COLUMN_TOTAL = 4
GROUP_TOTAL = 3
SPLITTER_TOTAL = 2
CENTRE_ALIGNMENT = 132

# Every value typed out here rather than read from either module, so a
# value moved on both sides together is still reported.
EXPECTED_COLORS = {
    "success": "#00ff88",
    "error": "#ff3366",
    "warning": "#ffaa00",
    "primary": "#00ffcc",
    "text_high": "#e0e0f0",
    "text_muted": "#666666",
    "text_placeholder": "#555555",
    "surface_chart": "#0a0a12",
    "surface_control": "#1a1a2e",
    "card_surface": "#12121f",
    "card_border": "#2a2a3f",
    "card_label": "#888",
}

EXPECTED_CARD_LABELS = (
    "Total P/L",
    "Win Rate",
    "Sharpe Ratio",
    "Profit Factor",
    "Total Trades",
    "Max Drawdown",
    "Expectancy",
    "Trades Today",
)

EXPECTED_CARD_KEYS = (
    "pnl",
    "win_rate",
    "sharpe",
    "profit_factor",
    "trades",
    "drawdown",
    "expectancy",
    "trades_today",
)

EXPECTED_BOT_COLUMNS = (
    "Bot",
    "Symbol",
    "Trades",
    "Win%",
    "P/L",
    "Profit Factor",
    "Sharpe",
    "Max DD%",
    "Avg Hold",
    "$/Trade",
)

EXPECTED_TIMEFRAME_COLUMNS = ("Timeframe", "Trades", "Win Rate", "Total P/L")

EXPECTED_GROUP_TITLES = {
    "equity": "Equity Curve",
    "bots": "Bot Performance",
    "timeframes": "Timeframe Performance",
}

EXPECTED_CARD_FRAME_STYLE = (
    "MetricCard { background: #12121f; border: 1px solid #2a2a3f; "
    "border-radius: 6px; }"
)

EXPECTED_CARD_LABEL_STYLE = "color: #888; font-size: 10px;"

EXPECTED_GROUP_STYLE_BOLD = (
    "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
    "border-radius: 6px; color: #00ffcc; font-weight: bold; }"
)

EXPECTED_GROUP_STYLE_PLAIN = (
    "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
    "border-radius: 6px; color: #00ffcc; }"
)

EXPECTED_PAGE_MARGINS_PX = [8, 8, 8, 8]
EXPECTED_PAGE_SPACING_PX = 8
EXPECTED_CARD_PADDING_PX = [10, 8, 10, 8]
EXPECTED_CARD_SPACING_PX = 2
EXPECTED_HANDLE_WIDTH_PX = 5
EXPECTED_MAIN_SIZES_PX = [250, 350]
EXPECTED_BOTTOM_SIZES_PX = [600, 300]
EXPECTED_CHART_MIN_HEIGHT_PX = 200
EXPECTED_CHART_MARGIN_PX = 40
EXPECTED_EQUITY_CURVE_HOURS = 24

EXPECTED_NUMBER_FORMATS = {
    "pnl": "${value:+,.4f}",
    "percent": "{value:.1f}%",
    "ratio": "{value:.2f}",
    "money": "${value:,.2f}",
    "infinity": "∞",
    "bot_id_length": 8,
    "seconds_per_minute": 60,
    "seconds_per_hour": 3600,
    "seconds_per_day": 86400,
    "duration_second": "{value:.0f}s",
    "duration_minute": "{value:.1f}m",
    "duration_hour": "{value:.1f}h",
    "duration_day": "{value:.1f}d",
}

EXPECTED_SUMMARY_DEFAULTS = {
    "total_pnl": 0,
    "win_rate": 0,
    "sharpe_ratio": 0,
    "profit_factor": 0,
    "total_trades": 0,
    "max_drawdown": 0,
    "expectancy": 0,
    "trades_today": 0,
}

EXPECTED_CHART_EMPTY_TEXT = "Collecting equity data..."
EXPECTED_CHART_RISE_FILL = [[0, 255, 136, 40], [0, 255, 136, 5]]
EXPECTED_CHART_FALL_FILL = [[255, 51, 102, 40], [255, 51, 102, 5]]


# The numbers both sides are driven with


class Source:
    """An analytics engine stand-in holding one fixed set of numbers.

    Carries the four readers the tab calls and the duration formatter
    the tab reaches for, and records the hours the tab asked the equity
    curve for.
    """

    def __init__(self, summary, curve, bots, timeframes):
        self._summary = summary
        self._curve = curve
        self._bots = bots
        self._timeframes = timeframes
        self.hours_asked = []
        self.summary_calls = 0

    def get_portfolio_summary(self):
        self.summary_calls += 1
        return self._summary

    def get_equity_curve(self, hours=24):
        self.hours_asked.append(hours)
        return self._curve

    def get_bot_performance(self):
        return self._bots

    def get_timeframe_comparison(self):
        return self._timeframes

    _format_duration = staticmethod(AnalyticsEngine._format_duration)


class EmptySource(Source):
    """A source holding nothing, and reading as false to the tab."""

    def __bool__(self):
        return False


def performance(**named):
    """One bot's metrics, with every field the row reads named here."""
    return BotPerformance(**named)


FULL_SUMMARY = {
    "total_pnl": 1234.56789,
    "win_rate": 61.25,
    "sharpe_ratio": 1.8342,
    "profit_factor": 2.375,
    "total_trades": 148,
    "max_drawdown": 7.44,
    "expectancy": 8.3421,
    "trades_today": 12,
}

RISING_CURVE = [
    {"timestamp": 1000.0, "equity": 10000.0},
    {"timestamp": 2000.0, "equity": 10250.5},
    {"timestamp": 3000.0, "equity": 9980.25},
    {"timestamp": 5000.0, "equity": 10501.75},
]

FALLING_CURVE = [
    {"timestamp": 1000.0, "equity": 10501.75},
    {"timestamp": 2500.0, "equity": 10100.0},
    {"timestamp": 4000.0, "equity": 9700.5},
]

FLAT_CURVE = [
    {"timestamp": 1000.0, "equity": 5000.0},
    {"timestamp": 1000.0, "equity": 5000.0},
]

ONE_POINT_CURVE = [{"timestamp": 1000.0, "equity": 5000.0}]

HUGE_CURVE = [
    {"timestamp": 0.0, "equity": 1e12},
    {"timestamp": 1.0, "equity": -1e12},
    {"timestamp": 2.0, "equity": 0.0},
]

FULL_BOTS = [
    performance(
        bot_id="bot-abcdef-0123456789",
        symbol="BTC/USD",
        mode="live",
        total_trades=42,
        win_rate=57.5,
        total_pnl=1500.25,
        profit_factor=2.5,
        sharpe_ratio=1.25,
        max_drawdown_pct=4.5,
        avg_hold_seconds=45.0,
        expectancy=35.75,
    ),
    performance(
        bot_id="short",
        symbol="Δ→⚡/USD",
        mode="sim",
        total_trades=0,
        win_rate=0.0,
        total_pnl=-250.5,
        profit_factor=float("inf"),
        sharpe_ratio=-0.5,
        max_drawdown_pct=0.0,
        avg_hold_seconds=125000.0,
        expectancy=-12.25,
    ),
    performance(
        bot_id="X" * 200,
        symbol="<b>ETH</b>",
        mode="paper",
        total_trades=1000000,
        win_rate=100.0,
        total_pnl=98765432.1,
        profit_factor=0.0,
        sharpe_ratio=0.0,
        max_drawdown_pct=99.99,
        avg_hold_seconds=3599.0,
        expectancy=0.0,
    ),
]

FULL_TIMEFRAMES = {
    "1h": {"total_trades": 10, "win_rate": 60.0, "total_pnl": 100.5},
    "15m": {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0},
    "UPPER": {"total_trades": 3, "win_rate": 33.333, "total_pnl": -9.5},
    "Δ→⚡": {"total_trades": 7, "win_rate": 99.99, "total_pnl": 1e9},
    "a\nb": {"total_trades": 1, "win_rate": 50.0, "total_pnl": -0.0001},
}

# What the eight cards read for FULL_SUMMARY, typed out here.
EXPECTED_FULL_CARD_VALUES = (
    ("Total P/L", "$+1,234.5679", "#00ff88"),
    ("Win Rate", "61.2%", "#e0e0f0"),
    ("Sharpe Ratio", "1.83", "#e0e0f0"),
    ("Profit Factor", "2.38", "#e0e0f0"),
    ("Total Trades", "148", "#e0e0f0"),
    ("Max Drawdown", "7.4%", "#ffaa00"),
    ("Expectancy", "$+8.3421", "#e0e0f0"),
    ("Trades Today", "12", "#e0e0f0"),
)

# What the eight cards read when the summary carries nothing at all.
EXPECTED_EMPTY_CARD_VALUES = (
    ("Total P/L", "$+0.0000", "#00ff88"),
    ("Win Rate", "0.0%", "#e0e0f0"),
    ("Sharpe Ratio", "0.00", "#e0e0f0"),
    ("Profit Factor", "0.00", "#e0e0f0"),
    ("Total Trades", "0", "#e0e0f0"),
    ("Max Drawdown", "0.0%", "#ffaa00"),
    ("Expectancy", "$+0.0000", "#e0e0f0"),
    ("Trades Today", "0", "#e0e0f0"),
)

# Every cell of the bot table for FULL_BOTS, typed out here.
EXPECTED_FULL_BOT_ROWS = (
    (
        ("bot-abcd", ""),
        ("BTC/USD", ""),
        ("42", ""),
        ("57.5%", ""),
        ("$+1,500.2500", "#00ff88"),
        ("2.50", ""),
        ("1.25", ""),
        ("4.5%", ""),
        ("45s", ""),
        ("$+35.7500", ""),
    ),
    (
        ("short", ""),
        ("Δ→⚡/USD", ""),
        ("0", ""),
        ("0.0%", ""),
        ("$-250.5000", "#ff3366"),
        ("∞", ""),
        ("-0.50", ""),
        ("0.0%", ""),
        ("1.4d", ""),
        ("$-12.2500", ""),
    ),
    (
        ("XXXXXXXX", ""),
        ("<b>ETH</b>", ""),
        ("1000000", ""),
        ("100.0%", ""),
        ("$+98,765,432.1000", "#00ff88"),
        ("0.00", ""),
        ("0.00", ""),
        ("100.0%", ""),
        ("60.0m", ""),
        ("$+0.0000", ""),
    ),
)

# Every cell of the timeframe table for FULL_TIMEFRAMES, in name order.
EXPECTED_FULL_TIMEFRAME_ROWS = (
    (("15m", ""), ("0", ""), ("0.0%", ""), ("$+0.0000", "")),
    (("1h", ""), ("10", ""), ("60.0%", ""), ("$+100.5000", "")),
    (("UPPER", ""), ("3", ""), ("33.3%", ""), ("$-9.5000", "")),
    (("a\nb", ""), ("1", ""), ("50.0%", ""), ("$-0.0001", "")),
    (("Δ→⚡", ""), ("7", ""), ("100.0%", ""), ("$+1,000,000,000.0000", "")),
)

# The hold times the Avg Hold column shows, typed out here.
EXPECTED_DURATIONS = {
    0: "0s",
    0.4: "0s",
    59: "59s",
    59.9: "60s",
    60: "1.0m",
    3599: "60.0m",
    3600: "1.0h",
    86399: "24.0h",
    86400: "1.0d",
    1e9: "11574.1d",
    -5: "-5s",
}

# The awkward values a caller may put where a number or a name belongs.
AWKWARD_TEXTS = {
    "empty": "",
    "zero": "0",
    "negative": "-1",
    "very_large": "9" * 40,
    "unicode": "Δ→⚡",
    "long": "X" * 200,
    "markup": "<b>BTC</b>",
    "uppercase": "BTC/USD",
    "lowercase": "btc/usd",
    "newline": "BTC\nUSD",
    "quoted": '"BTC"',
    "spaced": "  BTC  ",
}

AWKWARD_NUMBERS = (
    0,
    -0.0,
    1,
    -1,
    0.5,
    -0.5,
    1e-9,
    -1e-9,
    1234567.891,
    -1234567.891,
    1e15,
    -1e15,
    True,
    False,
)

NON_TEXT_VALUES: tuple = (0, -1, 9.5, None, [], {}, True)


# Reading each side


def app():
    """The process application object every render needs."""
    from qt_pixel import ensure_app

    return ensure_app()


def render_offscreen(widget, size):
    from qt_pixel import render_widget

    return render_widget(widget, size)


def digest(payload):
    """A stable hash over one side's whole answer."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def shipped_tab(source=None):
    """The shipped analytics tab, built and refreshed once."""
    app()
    tab = shipped.AnalyticsTab(source)
    if source is not None:
        tab.refresh()
    return tab


def item_color(item):
    """The colour a table cell was given, or the empty string for none."""
    from PySide6.QtCore import Qt

    if item.foreground().style() == Qt.BrushStyle.NoBrush:
        return ""
    return item.foreground().color().name()


def read_table(table):
    """Every cell of one table as (text, colour) pairs, row by row."""
    rows = []
    for row in range(table.rowCount()):
        cells = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            cells.append((item.text(), item_color(item)))
        rows.append(tuple(cells))
    return tuple(rows)


def read_alignments(table):
    """The alignment of every cell of one table."""
    return [
        int(table.item(row, column).textAlignment())
        for row in range(table.rowCount())
        for column in range(table.columnCount())
    ]


def read_cards(tab):
    """Every metric card of one tab as (label, value, colour)."""
    row = tab.layout().itemAt(0).layout()
    found = []
    for index in range(row.count()):
        card = row.itemAt(index).widget()
        style = card._value.styleSheet()
        color = style.split("color: ")[1].split(";")[0]
        found.append((card._label.text(), card._value.text(), color))
    return tuple(found)


def shipped_display(source):
    """Everything the shipped tab shows for one set of numbers."""
    tab = shipped_tab(source)
    return {
        "cards": read_cards(tab),
        "bot_rows": read_table(tab._bot_table),
        "timeframe_rows": read_table(tab._tf_table),
        "curve": list(tab._equity_chart._data),
        "hours_asked": list(source.hours_asked),
    }


def surface_display(summary, curve, bots, timeframes):
    """Everything the surface says the tab shows for the same numbers."""
    source = Source(summary, curve, bots, timeframes)
    model = surface.AnalyticsTabModel(source)
    shown = model.refresh()
    return {
        "cards": tuple(
            (one["label"], one["value"], one["color"]) for one in shown["cards"]
        ),
        "bot_rows": tuple(
            tuple((one["text"], one["color"]) for one in row)
            for row in shown["bot_rows"]
        ),
        "timeframe_rows": tuple(
            tuple((one["text"], one["color"]) for one in row)
            for row in shown["timeframe_rows"]
        ),
        "curve": list(shown["curve"]),
        "hours_asked": list(source.hours_asked),
    }


def both_displays(summary, curve, bots, timeframes):
    """Drive both sides with one set of numbers in one call."""
    old = shipped_display(Source(summary, curve, bots, timeframes))
    new = surface_display(summary, curve, bots, timeframes)
    return old, new


# The window built from the payload, and nothing else


def _build_metric_card_class():
    from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout

    class MetricCard(QFrame):
        """A metric card built only from the surface's card values."""

        def __init__(self, spec, skin):
            super().__init__()
            self.setAccessibleName(spec["accessible_name"])
            self.setFrameShape(QFrame.StyledPanel)
            self.setStyleSheet(spec["frame_style"])
            box = QVBoxLayout(self)
            box.setContentsMargins(*skin["padding_px"])
            box.setSpacing(skin["spacing_px"])
            self._label = QLabel(spec["label"])
            self._label.setStyleSheet(spec["label_style"])
            self._value = QLabel(spec["value"])
            self._value.setStyleSheet(spec["value_style"])
            box.addWidget(self._label)
            box.addWidget(self._value)

    return MetricCard


def _build_chart_class():
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import (
        QColor,
        QFont,
        QLinearGradient,
        QPainter,
        QPen,
        QPolygonF,
    )
    from PySide6.QtWidgets import QWidget

    class PayloadEquityChart(QWidget):
        """An equity chart painted only from ``surface.chart_geometry``."""

        def __init__(self, points, skin):
            super().__init__()
            self.setAccessibleName(skin["accessible_name"])
            self._points = points
            self.setMinimumHeight(skin["min_height_px"])

        def paintEvent(self, _event):
            plan = surface.chart_geometry(self._points, self.width(), self.height())
            painter = QPainter(self)
            if plan["empty"]:
                painter.fillRect(self.rect(), QColor(plan["background"]))
                painter.setPen(QColor(plan["text_color"]))
                painter.drawText(self.rect(), Qt.AlignCenter, plan["text"])
                painter.end()
                return
            painter.setRenderHint(QPainter.Antialiasing)
            painter.fillRect(self.rect(), QColor(plan["background"]))
            painter.setPen(QPen(QColor(plan["grid_color"]), plan["grid_width_px"]))
            for line in plan["grid_lines_px"]:
                painter.drawLine(*line)
            gradient = QLinearGradient(
                plan["gradient"]["start_px"][0],
                plan["gradient"]["start_px"][1],
                plan["gradient"]["end_px"][0],
                plan["gradient"]["end_px"][1],
            )
            for at, channels in plan["gradient"]["stops"]:
                gradient.setColorAt(at, QColor(*channels))
            shape = QPolygonF()
            for corner in plan["polygon_px"]:
                shape.append(QPointF(corner[0], corner[1]))
            painter.setBrush(gradient)
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(shape)
            painter.setPen(QPen(QColor(plan["line_color"]), plan["line_width_px"]))
            for segment in plan["segments_px"]:
                painter.drawLine(*segment)
            for label in plan["labels"]:
                painter.setPen(QColor(label["color"]))
                painter.setFont(QFont(label["font_family"], label["font_point_size"]))
                painter.drawText(label["x_px"], label["y_px"], label["text"])
            painter.end()

    return PayloadEquityChart


def build_table(spec, rows):
    """One table built only from the surface's table values."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

    table = QTableWidget()
    table.setColumnCount(spec["column_count"])
    table.setHorizontalHeaderLabels(spec["columns"])
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setAlternatingRowColors(spec["alternating_row_colors"])
    if spec["selection_behavior"] == "rows":
        table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.verticalHeader().setVisible(spec["vertical_header_visible"])
    table.setRowCount(len(rows))
    for row, cells in enumerate(rows):
        for column, one in enumerate(cells):
            item = QTableWidgetItem(one["text"])
            item.setTextAlignment(Qt.AlignCenter)
            if one["color"]:
                item.setForeground(QColor(one["color"]))
            table.setItem(row, column, item)
    return table


def build_group(spec, child):
    """One group box built only from the surface's group values."""
    from PySide6.QtWidgets import QGroupBox, QVBoxLayout

    group = QGroupBox(spec["title"])
    group.setStyleSheet(spec["style"])
    box = QVBoxLayout(group)
    box.addWidget(child)
    return group


def build_splitter(spec):
    """One splitter built only from the surface's splitter values."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter

    orientation = Qt.Vertical if spec["orientation"] == "vertical" else Qt.Horizontal
    split = QSplitter(orientation)
    split.setHandleWidth(spec["handle_width_px"])
    split.setChildrenCollapsible(spec["children_collapsible"])
    return split


def build_tab(payload, points):
    """The whole analytics tab, built from the payload and from nothing else.

    Every label, colour, column, cell, layout number and chart corner
    comes out of ``surface.build_view_model``, so this window and the
    shipped tab is the parity comparison.
    """
    from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

    app()
    card_class = _build_metric_card_class()
    chart_class = _build_chart_class()
    root = QWidget()
    root.setAccessibleName(payload["accessible_name"])
    layout = QVBoxLayout(root)
    layout.setContentsMargins(*payload["page"]["margins_px"])
    layout.setSpacing(payload["page"]["spacing_px"])

    metrics_row = QHBoxLayout()
    for spec in payload["cards"]:
        metrics_row.addWidget(card_class(spec, payload["card_skin"]))
    layout.addLayout(metrics_row)

    splitter = build_splitter(payload["main_splitter"])
    chart = chart_class(points, payload["chart_skin"])
    splitter.addWidget(build_group(payload["groups"]["equity"], chart))

    bottom = build_splitter(payload["bottom_splitter"])
    bottom.addWidget(
        build_group(
            payload["groups"]["bots"],
            build_table(payload["bot_table"], payload["bot_rows"]),
        )
    )
    bottom.addWidget(
        build_group(
            payload["groups"]["timeframes"],
            build_table(payload["timeframe_table"], payload["timeframe_rows"]),
        )
    )
    bottom.setSizes(payload["bottom_splitter"]["sizes_px"])
    splitter.addWidget(bottom)
    splitter.setSizes(payload["main_splitter"]["sizes_px"])
    layout.addWidget(splitter)
    return root


def payload_for(summary, curve, bots, timeframes, width=800, height=300):
    """The surface's whole answer for one set of numbers."""
    return surface.build_view_model(
        summary,
        curve,
        [surface.bot_values(one) for one in bots],
        timeframes,
        width,
        height,
    )


def full_payload():
    """The surface's answer for the full set of numbers."""
    return payload_for(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)


# What the shipped file has, and where each item went

SHIPPED_CLASSES = ("MetricCard", "MiniEquityChart", "AnalyticsTab")

SHIPPED_MEMBERS = {
    "MetricCard": ("__init__",),
    "MiniEquityChart": ("__init__", "set_data", "paintEvent"),
    "AnalyticsTab": ("__init__", "_setup_ui", "refresh"),
}

SHIPPED_CALLABLE_TOTAL = 7

# Every shipped class and method, and what stands for it on the surface.
COUNTERPARTS = {
    "MetricCard": "CARD_SKIN",
    "MetricCard.__init__": "card",
    "MiniEquityChart": "CHART_SKIN",
    "MiniEquityChart.__init__": "CHART_SKIN",
    "MiniEquityChart.set_data": "chart_geometry",
    "MiniEquityChart.paintEvent": "chart_geometry",
    "AnalyticsTab": "AnalyticsTabModel",
    "AnalyticsTab.__init__": "AnalyticsTabModel.__init__",
    "AnalyticsTab._setup_ui": "build_view_model",
    "AnalyticsTab.refresh": "AnalyticsTabModel.refresh",
}

SURFACE_FUNCTIONS = (
    "pnl_text",
    "percent_text",
    "ratio_text",
    "money_text",
    "count_text",
    "profit_factor_text",
    "duration_text",
    "bot_id_text",
    "pnl_color",
    "card_value_style",
    "card",
    "summary_value",
    "summary_cards",
    "cell",
    "bot_values",
    "bot_row",
    "bot_rows",
    "timeframe_row",
    "timeframe_rows",
    "empty_chart",
    "chart_geometry",
    "build_view_model",
    "css_stop",
    "css_payload",
    "view_model",
)

SURFACE_CLASSES = ("AnalyticsTabModel",)

SURFACE_MODEL_MEMBERS = ("__init__", "refresh", "display")


def shipped_definitions():
    """Every class the shipped module itself defines."""
    import inspect

    return {
        name
        for name, value in vars(shipped).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == shipped.__name__
    }


def shipped_callables():
    """Every method the shipped module itself defines, as Class.name."""
    import inspect

    found = set()
    for name in shipped_definitions():
        holder = getattr(shipped, name)
        for member, value in vars(holder).items():
            if inspect.isfunction(value):
                found.add(f"{name}.{member}")
    return found


def test_the_shipped_classes_each_have_a_counterpart():
    """A class on the shipped side has nothing standing for it."""
    defined = shipped_definitions()
    assert defined == set(SHIPPED_CLASSES), defined
    assert len(defined) == 3
    for name in SHIPPED_CLASSES:
        assert name in COUNTERPARTS, name
        assert hasattr(surface, COUNTERPARTS[name].split(".")[0]), name


def test_the_shipped_methods_each_have_a_counterpart():
    """A method on the shipped side has nothing standing for it."""
    found = shipped_callables()
    expected = {
        f"{holder}.{member}"
        for holder, members in SHIPPED_MEMBERS.items()
        for member in members
    }
    assert found == expected, found
    assert len(found) == SHIPPED_CALLABLE_TOTAL
    for name in found:
        assert name in COUNTERPARTS, name
        assert hasattr(surface, COUNTERPARTS[name].split(".")[0]), name
    assert len(COUNTERPARTS) == len(SHIPPED_CLASSES) + SHIPPED_CALLABLE_TOTAL


def test_the_definition_counter_can_see_a_definition():
    """The counter reported none because it can never report one."""
    import inspect

    from src.gui.main_tabs import table_cells_surface as neighbour

    defined = {
        name
        for name, value in vars(neighbour).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == neighbour.__name__
    }
    assert len(defined) > 0, "the counter cannot see a definition anywhere"
    assert "TableCellsModel" in defined
    assert shipped_callables(), "the method counter cannot see a method"


def test_the_surface_functions_are_reachable_and_described():
    """A named helper is missing, or carries no description."""
    import inspect

    found = {
        name
        for name, value in vars(surface).items()
        if inspect.isfunction(value)
        and getattr(value, "__module__", "") == surface.__name__
    }
    assert found == set(SURFACE_FUNCTIONS), found
    assert len(SURFACE_FUNCTIONS) == 25
    for name in SURFACE_FUNCTIONS:
        member = getattr(surface, name)
        assert callable(member), name
        assert (member.__doc__ or "").strip(), name
    classes = {
        name
        for name, value in vars(surface).items()
        if inspect.isclass(value)
        and getattr(value, "__module__", "") == surface.__name__
    }
    assert classes == set(SURFACE_CLASSES)
    for member in SURFACE_MODEL_MEMBERS:
        assert hasattr(surface.AnalyticsTabModel, member), member
    with pytest.raises(AttributeError):
        surface.no_such_helper()


def test_the_connect_sites_match_the_actions():
    """A signal wiring appeared on one side and not the other.

    ``connections`` counts what building each side really wires, so a signal
    connected through a helper or a loop is counted the same as a literal one.
    """
    from tests.fixtures.qt_wiring_counts import connections

    app()
    shipped_wirings, tab = connections(lambda: shipped.AnalyticsTab(None))
    assert tab is not None
    assert shipped_wirings == 0, shipped_wirings

    surface_wirings, payload = connections(lambda: surface.view_model({}))
    assert payload
    assert surface_wirings == 0, surface_wirings
    assert len(surface.ACTIONS) == shipped_wirings


def test_the_connection_counter_can_report_a_wiring():
    """POSITIVE CONTROL. The neighbour this unit did not touch wires signals, so
    a zero above is a fact about the analytics tab."""
    from tests.fixtures.qt_wiring_counts import connections
    from src.gui.widgets.bot_status_table import BotStatusTable

    app()
    wired, table = connections(BotStatusTable)
    assert table is not None
    assert wired > 0, "the counter cannot report a wiring"


def test_the_tab_declares_no_action_no_timer_and_no_skin():
    """The surface gained behaviour the tab it replaces never had."""
    from src.gui.main_tabs import console_tab_surface as neighbour

    assert surface.ACTIONS == {}
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert surface.SKIN == {}
    payload = surface.build_view_model()
    assert payload["actions"] == {}
    assert payload["timers"] == {}
    assert payload["timer_delays_ms"] == []
    assert payload["skin"] == {}
    assert len(neighbour.TIMERS) > 0, "the timer counter cannot report a timer"


# The two sides, value for value


@pytest.mark.parametrize("index", range(CARD_TOTAL))
def test_every_metric_card_carries_the_shipped_label_value_and_colour(index):
    """One metric card reads differently on the two sides."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    assert new["cards"][index] == old["cards"][index]
    assert new["cards"][index] == EXPECTED_FULL_CARD_VALUES[index]


def test_the_cards_come_back_in_one_order():
    """A card moved along the row on one side only."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    assert [one[0] for one in old["cards"]] == list(EXPECTED_CARD_LABELS)
    assert [one[0] for one in new["cards"]] == list(EXPECTED_CARD_LABELS)
    assert len(new["cards"]) == CARD_TOTAL
    swapped = list(new["cards"])
    swapped[0], swapped[1] = swapped[1], swapped[0]
    assert tuple(swapped) != old["cards"], "a swap reads as unchanged"


def test_the_cards_read_the_same_when_the_summary_carries_nothing():
    """The zero state of the cards drifted between the two sides."""
    old, new = both_displays({}, [], [], {})
    assert new["cards"] == old["cards"]
    assert new["cards"] == EXPECTED_EMPTY_CARD_VALUES


@pytest.mark.parametrize("row", range(3))
def test_every_bot_row_carries_the_shipped_cells(row):
    """One bot row reads differently on the two sides."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    assert new["bot_rows"][row] == old["bot_rows"][row]
    assert new["bot_rows"][row] == EXPECTED_FULL_BOT_ROWS[row]
    assert len(new["bot_rows"][row]) == BOT_COLUMN_TOTAL


@pytest.mark.parametrize("row", range(5))
def test_every_timeframe_row_carries_the_shipped_cells(row):
    """One timeframe row reads differently on the two sides."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    assert new["timeframe_rows"][row] == old["timeframe_rows"][row]
    assert new["timeframe_rows"][row] == EXPECTED_FULL_TIMEFRAME_ROWS[row]
    assert len(new["timeframe_rows"][row]) == TIMEFRAME_COLUMN_TOTAL


def test_the_timeframe_rows_are_sorted_by_name_on_both_sides():
    """A timeframe moved up or down the table on one side only."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    names = [row[0][0] for row in new["timeframe_rows"]]
    assert names == [row[0][0] for row in old["timeframe_rows"]]
    assert names == sorted(FULL_TIMEFRAMES)
    assert names == ["15m", "1h", "UPPER", "a\nb", "Δ→⚡"]


def test_the_two_sides_hash_the_same():
    """The two sides differ somewhere the value checks missed."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    assert new == old
    assert digest(new) == digest(old)


def test_the_sample_hashes_are_reported():
    """A hash the report quotes no longer matches what the code builds."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    empty_old, empty_new = both_displays({}, [], [], {})
    samples = {
        "shipped_full": digest(old),
        "surface_full": digest(new),
        "shipped_empty": digest(empty_old),
        "surface_empty": digest(empty_new),
    }
    assert samples["shipped_full"] == samples["surface_full"]
    assert samples["shipped_empty"] == samples["surface_empty"]
    assert samples["shipped_full"] != samples["shipped_empty"]
    assert all(len(value) == 64 for value in samples.values()), samples


def test_the_hash_can_report_a_difference():
    """The hash returns one value whatever it is handed."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    moved = dict(new)
    moved["cards"] = (("Total P/L", "$+0.0001", "#00ff88"),) + new["cards"][1:]
    assert digest(moved) != digest(old)
    assert digest(old) == digest(old)


def test_both_sides_ask_the_equity_curve_for_the_same_hours():
    """The tab asked for a different window of equity points."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    assert new["hours_asked"] == old["hours_asked"]
    assert new["hours_asked"] == [EXPECTED_EQUITY_CURVE_HOURS]
    assert surface.EQUITY_CURVE_HOURS == 24


def test_both_sides_hand_the_chart_the_same_points():
    """The chart was given a different set of equity points."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    assert new["curve"] == old["curve"]
    assert new["curve"] == RISING_CURVE


@pytest.mark.parametrize("case", sorted(AWKWARD_TEXTS))
def test_an_awkward_symbol_reads_the_same_on_both_sides(case):
    """A symbol with markup, a newline or 200 characters drifted."""
    text = AWKWARD_TEXTS[case]
    bots = [
        performance(
            bot_id=text,
            symbol=text,
            mode="live",
            total_trades=1,
            win_rate=1.0,
            total_pnl=1.0,
            profit_factor=1.0,
            sharpe_ratio=1.0,
            max_drawdown_pct=1.0,
            avg_hold_seconds=1.0,
            expectancy=1.0,
        )
    ]
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, bots, {})
    assert new["bot_rows"] == old["bot_rows"], case
    assert new["bot_rows"][0][0][0] == text[:8], case
    assert new["bot_rows"][0][1][0] == text, case


@pytest.mark.parametrize("case", sorted(AWKWARD_TEXTS))
def test_an_awkward_timeframe_name_reads_the_same_on_both_sides(case):
    """A timeframe name with markup or a newline drifted."""
    name = AWKWARD_TEXTS[case]
    timeframes = {name: {"total_trades": 2, "win_rate": 25.0, "total_pnl": -3.5}}
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, [], timeframes)
    assert new["timeframe_rows"] == old["timeframe_rows"], case
    assert new["timeframe_rows"][0][0][0] == name, case


@pytest.mark.parametrize("value", AWKWARD_NUMBERS)
def test_an_awkward_profit_and_loss_reads_the_same_on_both_sides(value):
    """A zero, a negative or a very large number drifted between sides."""
    summary = dict(FULL_SUMMARY, total_pnl=value, expectancy=value)
    old, new = both_displays(summary, RISING_CURVE, [], {})
    assert new["cards"] == old["cards"], value
    assert new["cards"][0][1] == surface.pnl_text(value)
    assert new["cards"][0][2] == ("#00ff88" if value >= 0 else "#ff3366")


def test_a_profit_factor_of_infinity_reads_as_the_infinity_sign():
    """The no-loss case stopped showing the infinity sign."""
    summary = dict(FULL_SUMMARY, profit_factor=float("inf"))
    old, new = both_displays(summary, RISING_CURVE, [], {})
    assert new["cards"] == old["cards"]
    assert new["cards"][3][1] == "∞"
    assert surface.profit_factor_text(float("inf")) == "∞"
    assert surface.profit_factor_text(2.5) == "2.50"


def test_a_missing_summary_key_falls_back_the_same_way_on_both_sides():
    """A summary short of a key showed a different number."""
    for field in sorted(EXPECTED_SUMMARY_DEFAULTS):
        short = {name: 5 for name in EXPECTED_SUMMARY_DEFAULTS if name != field}
        old, new = both_displays(short, [], [], {})
        assert new["cards"] == old["cards"], field


def test_a_timeframe_short_of_a_key_fails_the_same_way_on_both_sides():
    """One side showed a number where the other refused."""
    timeframes = {"1h": {"total_trades": 3, "win_rate": 1.0}}
    with pytest.raises(KeyError):
        shipped_display(Source(FULL_SUMMARY, [], [], timeframes))
    with pytest.raises(KeyError):
        surface_display(FULL_SUMMARY, [], [], timeframes)


def test_a_bot_identifier_that_is_not_text_fails_the_same_way():
    """One side showed a row where the other refused."""
    bots = [
        performance(
            bot_id=1234,
            symbol="BTC",
            mode="live",
            total_trades=1,
            win_rate=1.0,
            total_pnl=1.0,
            profit_factor=1.0,
            sharpe_ratio=1.0,
            max_drawdown_pct=1.0,
            avg_hold_seconds=1.0,
            expectancy=1.0,
        )
    ]
    with pytest.raises(TypeError):
        shipped_display(Source(FULL_SUMMARY, [], bots, {}))
    with pytest.raises(TypeError):
        surface_display(FULL_SUMMARY, [], bots, {})


def test_a_win_rate_that_is_not_a_number_fails_the_same_way():
    """One side showed a percentage where the other refused."""
    summary = dict(FULL_SUMMARY, win_rate="61.2")
    with pytest.raises((TypeError, ValueError)):
        shipped_display(Source(summary, [], [], {}))
    with pytest.raises((TypeError, ValueError)):
        surface_display(summary, [], [], {})


def outcome(work):
    """What one call did: its answer, or the name of what it raised."""
    try:
        return ("answered", work())
    except Exception as raised:
        return ("raised", type(raised).__name__)


def test_a_symbol_that_is_not_text_reaches_the_same_cell_on_both_sides():
    """A number where a symbol belongs reached different cells."""
    answers = []
    for value in NON_TEXT_VALUES:
        bots = [
            performance(
                bot_id="abcdefghij",
                symbol=value,
                mode="live",
                total_trades=1,
                win_rate=1.0,
                total_pnl=1.0,
                profit_factor=1.0,
                sharpe_ratio=1.0,
                max_drawdown_pct=1.0,
                avg_hold_seconds=1.0,
                expectancy=1.0,
            )
        ]

        def old_side(bots=bots):
            shown = shipped_display(Source(FULL_SUMMARY, [], bots, {}))
            return shown["bot_rows"][0]

        def new_side(bots=bots):
            payload = payload_for(FULL_SUMMARY, [], bots, {})
            assert payload["bot_rows"][0][1]["text"] == bots[0].symbol
            built = build_table(payload["bot_table"], payload["bot_rows"])
            return read_table(built)[0]

        old = outcome(old_side)
        new = outcome(new_side)
        assert new == old, (repr(value), old, new)
        answers.append(old[0])
    assert set(answers) == {"answered", "raised"}, answers


def test_every_cell_is_centred_on_both_sides():
    """A cell stopped being centred on one side."""
    old_tab = shipped_tab(Source(FULL_SUMMARY, [], FULL_BOTS, FULL_TIMEFRAMES))
    payload = full_payload()
    new_bots = build_table(payload["bot_table"], payload["bot_rows"])
    new_times = build_table(payload["timeframe_table"], payload["timeframe_rows"])
    assert read_alignments(new_bots) == read_alignments(old_tab._bot_table)
    assert read_alignments(new_times) == read_alignments(old_tab._tf_table)
    assert set(read_alignments(new_bots)) == {CENTRE_ALIGNMENT}
    assert len(read_alignments(new_bots)) == 3 * BOT_COLUMN_TOTAL


# Every widget, every column and every layout number


def test_the_page_layout_matches_on_both_sides():
    """The tab's margins, spacing or child order moved on one side."""
    tab = shipped_tab()
    layout = tab.layout()
    assert list(layout.getContentsMargins()) == EXPECTED_PAGE_MARGINS_PX
    assert layout.spacing() == EXPECTED_PAGE_SPACING_PX
    assert layout.count() == len(surface.PAGE["children"])
    assert surface.PAGE["margins_px"] == EXPECTED_PAGE_MARGINS_PX
    assert surface.PAGE["spacing_px"] == EXPECTED_PAGE_SPACING_PX
    assert surface.PAGE["children"] == ["metrics_row", "main_splitter"]
    assert tab.accessibleName() == surface.TAB_ACCESSIBLE_NAME
    assert surface.TAB_ACCESSIBLE_NAME == "Analytics Tab"


def test_the_metric_card_skin_matches_on_both_sides():
    """A card's colour, type size, padding or frame moved on one side.

    The declared values are read off both sides and the two cards are
    then painted, so a colour that reaches no pixel is reported here.
    """
    from PySide6.QtWidgets import QFrame
    from qt_pixel import render_widget

    tab = shipped_tab()
    card = tab.layout().itemAt(0).layout().itemAt(0).widget()
    skin = surface.CARD_SKIN
    assert card.metaObject().className() == skin["class_name"]
    assert card.accessibleName() == skin["accessible_name"]
    assert card.styleSheet() == surface.CARD_FRAME_STYLE
    assert card.styleSheet() == EXPECTED_CARD_FRAME_STYLE
    assert card._label.styleSheet() == surface.CARD_LABEL_STYLE
    assert card._label.styleSheet() == EXPECTED_CARD_LABEL_STYLE
    assert list(card.layout().getContentsMargins()) == skin["padding_px"]
    assert skin["padding_px"] == EXPECTED_CARD_PADDING_PX
    assert card.layout().spacing() == skin["spacing_px"]
    assert skin["spacing_px"] == EXPECTED_CARD_SPACING_PX
    assert card.frameShape() == QFrame.StyledPanel
    assert card.layout().count() == len(skin["children"])
    spec = surface.card("pnl", skin["default_value"])
    assert spec["value"] == card._value.text()
    card.setParent(None)
    assert_pictures_match(
        old_side=render_widget(card, CARD_SIZE),
        new_side=render_widget(_build_metric_card_class()(spec, skin), CARD_SIZE),
        note="metric card, %s" % font_note(),
    )


def test_the_default_card_value_matches_on_both_sides():
    """A card that was never refreshed shows a different value."""
    tab = shipped_tab()
    values = [one[1] for one in read_cards(tab)]
    assert values == [surface.CARD_SKIN["default_value"]] * CARD_TOTAL
    assert surface.CARD_SKIN["default_value"] == "---"
    assert [one[0] for one in read_cards(tab)] == list(EXPECTED_CARD_LABELS)


def test_the_card_labels_and_their_keys_match():
    """A card label or its key moved on one side only."""
    assert tuple(surface.CARD_ORDER) == EXPECTED_CARD_KEYS
    assert [surface.CARD_LABELS[key] for key in surface.CARD_ORDER] == list(
        EXPECTED_CARD_LABELS
    )
    assert set(surface.CARD_LABELS) == set(EXPECTED_CARD_KEYS)
    assert len(surface.CARD_LABELS) == CARD_TOTAL
    tab = shipped_tab()
    assert [one[0] for one in read_cards(tab)] == list(EXPECTED_CARD_LABELS)


def test_the_group_boxes_match_on_both_sides():
    """A group box title or style moved on one side only.

    The declared values are read off both sides and the bot group is
    then painted, so a style that reaches no pixel is reported here.
    """
    from PySide6.QtWidgets import QGroupBox
    from qt_pixel import render_widget

    tab = shipped_tab()
    boxes = {one.title(): one for one in tab.findChildren(QGroupBox)}
    groups = {title: one.styleSheet() for title, one in boxes.items()}
    assert len(groups) == GROUP_TOTAL
    for key, title in EXPECTED_GROUP_TITLES.items():
        assert surface.GROUPS[key]["title"] == title, key
        assert title in groups, key
        assert groups[title] == surface.GROUPS[key]["style"], key
    assert groups["Equity Curve"] == EXPECTED_GROUP_STYLE_BOLD
    assert groups["Bot Performance"] == EXPECTED_GROUP_STYLE_PLAIN
    assert groups["Timeframe Performance"] == EXPECTED_GROUP_STYLE_PLAIN
    assert EXPECTED_GROUP_STYLE_BOLD != EXPECTED_GROUP_STYLE_PLAIN
    payload = surface.build_view_model()
    boxes["Bot Performance"].setParent(None)
    assert_pictures_match(
        old_side=render_widget(boxes["Bot Performance"], GROUP_SIZE),
        new_side=render_widget(
            build_group(
                payload["groups"]["bots"],
                build_table(payload["bot_table"], payload["bot_rows"]),
            ),
            GROUP_SIZE,
        ),
        note="bot group, %s" % font_note(),
    )


def test_the_splitter_settings_match_on_both_sides():
    """A splitter's handle, collapsing or child order moved."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter

    tab = shipped_tab()
    splits = tab.findChildren(QSplitter)
    assert len(splits) == SPLITTER_TOTAL
    by_orientation = {one.orientation(): one for one in splits}
    main = by_orientation[Qt.Vertical]
    bottom = by_orientation[Qt.Horizontal]
    assert main.handleWidth() == surface.MAIN_SPLITTER["handle_width_px"]
    assert bottom.handleWidth() == surface.BOTTOM_SPLITTER["handle_width_px"]
    assert surface.MAIN_SPLITTER["handle_width_px"] == EXPECTED_HANDLE_WIDTH_PX
    assert main.childrenCollapsible() is False
    assert bottom.childrenCollapsible() is False
    assert surface.MAIN_SPLITTER["children_collapsible"] is False
    assert surface.BOTTOM_SPLITTER["children_collapsible"] is False
    assert main.count() == len(surface.MAIN_SPLITTER["children"])
    assert bottom.count() == len(surface.BOTTOM_SPLITTER["children"])
    assert surface.MAIN_SPLITTER["sizes_px"] == EXPECTED_MAIN_SIZES_PX
    assert surface.BOTTOM_SPLITTER["sizes_px"] == EXPECTED_BOTTOM_SIZES_PX


def settled_splitter_sizes(tab):
    """The sizes each splitter of one tab settled on, keyed by direction."""
    from PySide6.QtWidgets import QSplitter

    return {one.orientation().name: one.sizes() for one in tab.findChildren(QSplitter)}


def test_both_sides_settle_on_the_same_splitter_sizes():
    """The requested splitter sizes differ between the two sides."""
    payload = full_payload()
    old_tab = shipped_tab(Source(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, {}))
    new_tab = build_tab(payload, RISING_CURVE)
    render_offscreen(old_tab, PIXEL_SIZE)
    render_offscreen(new_tab, PIXEL_SIZE)
    old_settled = settled_splitter_sizes(old_tab)
    new_settled = settled_splitter_sizes(new_tab)
    assert len(old_settled) == SPLITTER_TOTAL
    assert new_settled == old_settled, (old_settled, new_settled)
    moved = full_payload()
    moved["main_splitter"] = dict(moved["main_splitter"], sizes_px=[900, 100])
    moved["bottom_splitter"] = dict(moved["bottom_splitter"], sizes_px=[100, 900])
    other_tab = build_tab(moved, RISING_CURVE)
    render_offscreen(other_tab, PIXEL_SIZE)
    assert (
        settled_splitter_sizes(other_tab) != old_settled
    ), "any requested sizes settle the same, so this check cannot report"


def test_the_bot_table_settings_match_on_both_sides():
    """A bot table column, heading or setting moved on one side."""
    from PySide6.QtWidgets import QHeaderView, QTableWidget

    tab = shipped_tab()
    table = tab._bot_table
    spec = surface.BOT_TABLE
    headings = [
        table.horizontalHeaderItem(i).text() for i in range(table.columnCount())
    ]
    assert table.columnCount() == spec["column_count"] == BOT_COLUMN_TOTAL
    assert headings == spec["columns"]
    assert tuple(headings) == EXPECTED_BOT_COLUMNS
    assert table.horizontalHeader().sectionResizeMode(0) == QHeaderView.Stretch
    assert table.alternatingRowColors() is spec["alternating_row_colors"]
    assert table.selectionBehavior() == QTableWidget.SelectRows
    assert spec["selection_behavior"] == "rows"
    assert table.editTriggers() == QTableWidget.NoEditTriggers
    assert table.verticalHeader().isVisible() is spec["vertical_header_visible"]
    assert spec["colored_column"] == 4
    assert spec["columns"][spec["colored_column"]] == "P/L"


def test_the_timeframe_table_settings_match_on_both_sides():
    """A timeframe table column, heading or setting moved on one side."""
    from PySide6.QtWidgets import QHeaderView, QTableWidget

    tab = shipped_tab()
    table = tab._tf_table
    spec = surface.TIMEFRAME_TABLE
    headings = [
        table.horizontalHeaderItem(i).text() for i in range(table.columnCount())
    ]
    assert table.columnCount() == spec["column_count"] == TIMEFRAME_COLUMN_TOTAL
    assert headings == spec["columns"]
    assert tuple(headings) == EXPECTED_TIMEFRAME_COLUMNS
    assert table.horizontalHeader().sectionResizeMode(0) == QHeaderView.Stretch
    assert table.alternatingRowColors() is spec["alternating_row_colors"]
    assert table.selectionBehavior() == QTableWidget.SelectItems
    assert spec["selection_behavior"] == "items"
    assert table.editTriggers() == QTableWidget.NoEditTriggers
    assert table.verticalHeader().isVisible() is spec["vertical_header_visible"]
    assert spec["colored_column"] is None


def test_the_two_tables_differ_in_the_one_setting_the_shipped_tab_gives_them():
    """The two tables stopped differing where the shipped tab differs."""
    assert (
        surface.BOT_TABLE["selection_behavior"]
        != surface.TIMEFRAME_TABLE["selection_behavior"]
    )
    tab = shipped_tab()
    assert tab._bot_table.selectionBehavior() != tab._tf_table.selectionBehavior()


def test_the_chart_settings_match_on_both_sides():
    """The chart's least height or its name moved on one side."""
    tab = shipped_tab()
    chart = tab._equity_chart
    skin = surface.CHART_SKIN
    assert chart.minimumHeight() == skin["min_height_px"]
    assert skin["min_height_px"] == EXPECTED_CHART_MIN_HEIGHT_PX
    assert chart.accessibleName() == skin["accessible_name"]
    assert skin["accessible_name"] == "Mini Equity Chart"
    assert chart._data == []
    assert skin["margin_px"] == EXPECTED_CHART_MARGIN_PX
    assert skin["empty_text"] == EXPECTED_CHART_EMPTY_TEXT
    assert skin["rise_fill"] == EXPECTED_CHART_RISE_FILL
    assert skin["fall_fill"] == EXPECTED_CHART_FALL_FILL


def test_set_data_replaces_the_points_the_chart_holds():
    """The chart kept the points it was told to drop."""
    tab = shipped_tab()
    chart = tab._equity_chart
    chart.set_data(RISING_CURVE)
    assert chart._data == RISING_CURVE
    chart.set_data([])
    assert chart._data == []
    assert surface.chart_geometry([], *CHART_SIZE)["empty"] is True
    assert surface.chart_geometry(RISING_CURVE, *CHART_SIZE)["empty"] is False


# Every branch of every surface function


@pytest.mark.parametrize("seconds,expected", sorted(EXPECTED_DURATIONS.items()))
def test_duration_text_matches_the_engine_and_the_value_typed_here(seconds, expected):
    """A hold time reads differently than the engine formats it."""
    assert surface.duration_text(seconds) == AnalyticsEngine._format_duration(seconds)
    assert surface.duration_text(seconds) == expected


def test_duration_text_crosses_each_threshold_in_the_right_place():
    """A hold time changed unit at a different number of seconds."""
    assert surface.duration_text(59.4).endswith("s")
    assert surface.duration_text(60).endswith("m")
    assert surface.duration_text(3599).endswith("m")
    assert surface.duration_text(3600).endswith("h")
    assert surface.duration_text(86399).endswith("h")
    assert surface.duration_text(86400).endswith("d")
    assert len({surface.duration_text(v)[-1] for v in (1, 60, 3600, 86400)}) == 4


@pytest.mark.parametrize("value", AWKWARD_NUMBERS)
def test_pnl_text_signs_and_groups_every_number(value):
    """A profit or loss lost its sign or its thousands separators."""
    assert surface.pnl_text(value) == f"${value:+,.4f}"
    assert surface.pnl_text(value).startswith("$")
    assert surface.pnl_text(value)[1] in "+-"


def test_the_number_formats_read_as_typed_here():
    """A number format changed its placeholders on both sides together."""
    assert surface.NUMBER_FORMATS == EXPECTED_NUMBER_FORMATS
    assert surface.pnl_text(1234.5) == "$+1,234.5000"
    assert surface.percent_text(61.25) == "61.2%"
    assert surface.ratio_text(1.8342) == "1.83"
    assert surface.money_text(10501.75) == "$10,501.75"
    assert surface.count_text(0) == "0"
    assert surface.count_text(True) == "True"
    assert surface.bot_id_text("abcdefghijkl") == "abcdefgh"
    assert surface.bot_id_text("ab") == "ab"


def test_pnl_color_answers_both_ways():
    """The colour is the same whatever number it is given."""
    assert surface.pnl_color(0) == surface.SUCCESS
    assert surface.pnl_color(0.0001) == surface.SUCCESS
    assert surface.pnl_color(-0.0001) == surface.ERROR
    assert surface.pnl_color(-1e9) == surface.ERROR
    assert len({surface.pnl_color(1), surface.pnl_color(-1)}) == 2


def test_summary_value_falls_back_only_for_a_missing_key():
    """A present number was replaced by the default, or the reverse."""
    assert surface.summary_value({"win_rate": 42.0}, "win_rate") == 42.0
    assert surface.summary_value({}, "win_rate") == 0
    assert surface.summary_value({"win_rate": None}, "win_rate") is None
    assert surface.SUMMARY_DEFAULTS == EXPECTED_SUMMARY_DEFAULTS
    with pytest.raises(KeyError):
        surface.summary_value({}, "not_a_field")


def test_the_card_helper_carries_the_label_and_the_style():
    """A card came back without its label, its colour or its styles."""
    one = surface.card("pnl", "$+1.0000", surface.SUCCESS)
    assert one["key"] == "pnl"
    assert one["label"] == "Total P/L"
    assert one["value"] == "$+1.0000"
    assert one["color"] == "#00ff88"
    assert one["value_style"] == "color: #00ff88; font-size: 16px; font-weight: bold;"
    assert one["frame_style"] == EXPECTED_CARD_FRAME_STYLE
    assert one["label_style"] == EXPECTED_CARD_LABEL_STYLE
    assert surface.card("win_rate", "1.0%")["color"] == surface.TEXT_HIGH
    with pytest.raises(KeyError):
        surface.card("not_a_card", "x")


def test_the_cell_helper_carries_the_text_and_the_colour():
    """A cell came back without its text, its colour or its alignment."""
    assert surface.cell("x") == {"text": "x", "align": "center", "color": ""}
    assert surface.cell("x", surface.ERROR)["color"] == "#ff3366"
    assert surface.cell(0)["text"] == 0
    assert surface.cell(None)["text"] is None


def test_bot_values_reads_the_ten_fields_the_row_needs():
    """A field the row reads is missing from the values it is handed."""
    values = surface.bot_values(FULL_BOTS[0])
    assert tuple(values) == surface.BOT_FIELDS
    assert len(values) == BOT_COLUMN_TOTAL
    assert values["bot_id"] == "bot-abcdef-0123456789"
    assert values["avg_hold_seconds"] == 45.0
    with pytest.raises(AttributeError):
        surface.bot_values(object())


def test_bot_rows_and_timeframe_rows_are_empty_for_no_data():
    """An empty table came back carrying a row."""
    assert surface.bot_rows([]) == []
    assert surface.timeframe_rows({}) == []
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, [], {})
    assert new["bot_rows"] == old["bot_rows"] == ()
    assert new["timeframe_rows"] == old["timeframe_rows"] == ()


def test_the_model_returns_nothing_when_there_is_no_source():
    """The tab refreshed from a source that is not there."""
    model = surface.AnalyticsTabModel()
    assert model.display is None
    assert model.refresh() is surface.NO_REFRESH
    assert model.refresh() is None
    assert model.display is None
    tab = shipped.AnalyticsTab(None)
    assert tab.refresh() is None
    assert [one[1] for one in read_cards(tab)] == ["---"] * CARD_TOTAL


def test_an_empty_source_reads_as_no_source_on_both_sides():
    """A source that reads as empty was treated as present."""
    empty = EmptySource({}, [], [], {})
    assert bool(empty) is False
    assert surface.AnalyticsTabModel(empty).refresh() is None
    tab = shipped.AnalyticsTab(empty)
    assert tab.refresh() is None
    assert empty.summary_calls == 0
    assert [one[1] for one in read_cards(tab)] == ["---"] * CARD_TOTAL


def test_a_source_given_to_refresh_wins_over_the_one_held():
    """The tab read the wrong source when handed a second one."""
    held = Source(FULL_SUMMARY, [], [], {})
    given = Source({}, [], [], {})
    model = surface.AnalyticsTabModel(held)
    shown = model.refresh(given)
    assert given.summary_calls == 1
    assert held.summary_calls == 0
    assert shown["cards"][0]["value"] == "$+0.0000"
    tab = shipped.AnalyticsTab(Source(FULL_SUMMARY, [], [], {}))
    tab.refresh(Source({}, [], [], {}))
    assert read_cards(tab)[0][1] == "$+0.0000"


def test_the_model_keeps_what_it_last_showed():
    """A refresh with no source wiped what the tab was showing."""
    model = surface.AnalyticsTabModel(Source(FULL_SUMMARY, [], [], {}))
    shown = model.refresh()
    assert model.display is shown
    assert model.refresh(None) is not None
    assert surface.AnalyticsTabModel().refresh(None) is None


# The chart geometry


def test_the_chart_waits_for_a_second_point():
    """The chart drew a curve from too few points, or refused two."""
    for points in ([], None, ONE_POINT_CURVE):
        plan = surface.chart_geometry(points, *CHART_SIZE)
        assert plan["empty"] is True, points
        assert plan["text"] == EXPECTED_CHART_EMPTY_TEXT
        assert plan["text_color"] == EXPECTED_COLORS["text_placeholder"]
        assert plan["curve_px"] == []
    assert surface.chart_geometry(FLAT_CURVE, *CHART_SIZE)["empty"] is False


def test_the_chart_scales_the_curve_into_the_panel():
    """A curve point landed outside the panel or on the wrong pixel."""
    width, height = CHART_SIZE
    plan = surface.chart_geometry(RISING_CURVE, width, height)
    margin = EXPECTED_CHART_MARGIN_PX
    assert len(plan["curve_px"]) == len(RISING_CURVE)
    assert plan["curve_px"][0][0] == margin
    assert plan["curve_px"][-1][0] == width - margin
    for x, y in plan["curve_px"]:
        assert margin <= x <= width - margin, (x, y)
        assert margin <= y <= height - margin, (x, y)
    assert plan["min_equity"] == min(p["equity"] for p in RISING_CURVE) * 0.998
    assert plan["max_equity"] == max(p["equity"] for p in RISING_CURVE) * 1.002


def test_the_chart_draws_five_grid_lines_across_the_panel():
    """A grid line was lost, or drawn at the wrong height."""
    width, height = CHART_SIZE
    plan = surface.chart_geometry(RISING_CURVE, width, height)
    margin = EXPECTED_CHART_MARGIN_PX
    assert len(plan["grid_lines_px"]) == 5
    heights = [line[1] for line in plan["grid_lines_px"]]
    assert heights == sorted(heights)
    assert heights[0] == margin
    assert heights[-1] == height - margin
    for line in plan["grid_lines_px"]:
        assert line[0] == margin
        assert line[2] == width - margin
        assert line[1] == line[3]
    assert plan["grid_color"] == EXPECTED_COLORS["surface_control"]


def test_a_rising_curve_is_green_and_a_falling_curve_is_red():
    """The chart painted a loss green, or a gain red."""
    rising = surface.chart_geometry(RISING_CURVE, *CHART_SIZE)
    falling = surface.chart_geometry(FALLING_CURVE, *CHART_SIZE)
    assert rising["rising"] is True
    assert falling["rising"] is False
    assert rising["line_color"] == EXPECTED_COLORS["success"]
    assert falling["line_color"] == EXPECTED_COLORS["error"]
    assert rising["gradient"]["stops"] == [
        [0, EXPECTED_CHART_RISE_FILL[0]],
        [1, EXPECTED_CHART_RISE_FILL[1]],
    ]
    assert falling["gradient"]["stops"] == [
        [0, EXPECTED_CHART_FALL_FILL[0]],
        [1, EXPECTED_CHART_FALL_FILL[1]],
    ]
    assert rising["line_color"] != falling["line_color"]


def test_a_flat_curve_takes_the_fallback_range_and_reads_as_rising():
    """A curve with no spread divided by zero, or read as a loss."""
    plan = surface.chart_geometry(FLAT_CURVE, *CHART_SIZE)
    assert plan["rising"] is True
    assert plan["line_color"] == EXPECTED_COLORS["success"]
    assert len(plan["curve_px"]) == 2
    assert plan["curve_px"][0][0] == EXPECTED_CHART_MARGIN_PX
    assert surface.CHART_RANGE_FALLBACK == 1


def test_a_very_large_curve_still_lands_inside_the_panel():
    """A very large or negative equity pushed the curve off the panel."""
    width, height = CHART_SIZE
    plan = surface.chart_geometry(HUGE_CURVE, width, height)
    for x, y in plan["curve_px"]:
        assert 0 <= x <= width, (x, y)
        assert 0 <= y <= height, (x, y)
    assert plan["labels"][0]["text"] == "$0.00"
    assert plan["labels"][1]["text"].startswith("$-")


def test_the_chart_closes_its_shape_on_the_bottom_margin():
    """The filled shape stopped closing on the panel floor."""
    width, height = CHART_SIZE
    plan = surface.chart_geometry(RISING_CURVE, width, height)
    floor = height - EXPECTED_CHART_MARGIN_PX
    assert len(plan["polygon_px"]) == len(plan["curve_px"]) + 2
    assert plan["polygon_px"][-2] == [plan["curve_px"][-1][0], floor]
    assert plan["polygon_px"][-1] == [plan["curve_px"][0][0], floor]
    assert plan["gradient"]["start_px"] == [0, EXPECTED_CHART_MARGIN_PX]
    assert plan["gradient"]["end_px"] == [0, floor]
    assert len(plan["segments_px"]) == len(plan["curve_px"]) - 1


def test_the_chart_labels_the_latest_equity_and_the_scaled_floor():
    """A chart label lost its number, its colour or its place."""
    width, height = CHART_SIZE
    plan = surface.chart_geometry(RISING_CURVE, width, height)
    margin = EXPECTED_CHART_MARGIN_PX
    top, bottom = plan["labels"]
    assert top["text"] == "$10,501.75"
    assert bottom["text"] == "$9,960.29"
    assert top["color"] == EXPECTED_COLORS["text_high"]
    assert bottom["color"] == EXPECTED_COLORS["text_muted"]
    assert [top["x_px"], top["y_px"]] == [margin + 5, margin + 15]
    assert [bottom["x_px"], bottom["y_px"]] == [margin + 5, height - margin - 5]
    assert top["font_family"] == bottom["font_family"] == "Consolas"
    assert top["font_point_size"] == 9


# The surface carries its own values


#: Refuses PySide6 and shiboken at the meta path, then reports what imported.
BLOCKED_QT_PROBE = """
import importlib.abc
import json
import sys


class _NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in ('PySide6', 'shiboken6'):
            raise ImportError('Qt is blocked in this probe: ' + name)
        return None


sys.meta_path.insert(0, _NoQt())
answer = {'module': '%s', 'imported': False, 'error': ''}
try:
    __import__(answer['module'])
    answer['imported'] = True
except Exception as exc:
    answer['error'] = '%%s: %%s' %% (type(exc).__name__, exc)
answer['qt_in_sys_modules'] = any(
    m.split('.')[0] in ('PySide6', 'shiboken6') for m in sys.modules)
print(json.dumps(answer))
"""


def test_the_surface_loads_no_qt_module():
    """``BLOCKED_QT_PROBE`` refuses ``PySide6`` and ``shiboken6`` at the meta
    path, so a transitive import through any other module is refused too."""
    answered = run_script(BLOCKED_QT_PROBE % "src.gui.main_tabs.analytics_tab_surface")
    assert answered["imported"] is True, answered
    assert answered["qt_in_sys_modules"] is False, answered


def test_the_colour_helper_the_surface_imports_loads_no_qt_either():
    """``color_alpha`` is the surface's only repo import and carries the same
    rule."""
    answered = run_script(BLOCKED_QT_PROBE % "src.gui.color_alpha")
    assert answered["imported"] is True, answered
    assert answered["qt_in_sys_modules"] is False, answered


def test_the_probe_refuses_a_module_that_needs_qt():
    """POSITIVE CONTROL. ``BLOCKED_QT_PROBE`` reports ``bot_status_table`` as
    unimportable, so the two greens above are facts about the surface."""
    answered = run_script(BLOCKED_QT_PROBE % "src.gui.widgets.bot_status_table")
    assert answered["imported"] is False, answered
    assert "Qt is blocked" in answered["error"], answered


def test_the_surface_does_not_follow_a_colour_moved_in_the_design_system(
    monkeypatch,
):
    """The surface read its colours off the module the tab reads.

    The tab looks its colours up at refresh time, so a colour moved
    here moves the shipped side. The surface must not move with it.
    """
    moves = (
        ("SUCCESS", "#123456", "success"),
        ("ERROR", "#654321", "error"),
        ("WARNING", "#0f0f0f", "warning"),
        ("CARD_METRIC_BORDER", "#abcdef", "card_border"),
        ("SURFACE_CHART", "#fedcba", "surface_chart"),
    )
    for token, moved, key in moves:
        was = getattr(ds, token)
        monkeypatch.setattr(ds, token, moved)
        assert getattr(ds, token) == moved, token
        assert surface.COLORS[key] == was, token
        assert surface.build_view_model()["colors"][key] == was, token
        monkeypatch.undo()
        assert getattr(ds, token) == was, token
    summary = dict(FULL_SUMMARY, total_pnl=5.0)
    monkeypatch.setattr(ds, "SUCCESS", "#123456")
    old = shipped_display(Source(summary, [], [], {}))
    new = surface_display(summary, [], [], {})
    assert old["cards"][0][2] == "#123456"
    assert new["cards"][0][2] == "#00ff88"
    assert new["cards"][0][2] != old["cards"][0][2]
    monkeypatch.undo()


def test_the_surface_does_not_follow_a_replaced_shipped_builder(monkeypatch):
    """The surface built its cards from the shipped card class."""

    class Stub:
        def __init__(self, label, _value="---", _parent=None):
            self.label = label

        def set_value(self, value, _color=None):
            self.value = value

    monkeypatch.setattr(shipped, "MetricCard", Stub)
    assert shipped.MetricCard is Stub
    payload = surface.build_view_model(FULL_SUMMARY)
    assert payload["cards"][0]["label"] == "Total P/L"
    assert payload["cards"][0]["value"] == "$+1,234.5679"
    assert surface.summary_cards(FULL_SUMMARY)[0]["value"] == "$+1,234.5679"
    monkeypatch.undo()
    assert shipped.MetricCard is not Stub


def test_the_surface_does_not_follow_a_replaced_shipped_chart(monkeypatch):
    """The surface built its chart from the shipped chart class."""

    class Stub:
        def __init__(self, _parent=None):
            self.data = None

        def set_data(self, points):
            self.data = points

    monkeypatch.setattr(shipped, "MiniEquityChart", Stub)
    assert shipped.MiniEquityChart is Stub
    plan = surface.chart_geometry(RISING_CURVE, *CHART_SIZE)
    assert plan["empty"] is False
    assert len(plan["curve_px"]) == len(RISING_CURVE)
    monkeypatch.undo()


# The pictures


def font_note():
    """Which font answer this host gave, carried into a failure message."""
    return "real fonts" if has_real_fonts() else "no fonts"


@pytest.mark.parametrize(
    "curve", [RISING_CURVE, FALLING_CURVE, FLAT_CURVE, ONE_POINT_CURVE, []]
)
def test_the_two_sides_paint_one_chart(curve):
    """The surface painted a different equity chart than the widget."""
    app()
    chart_class = _build_chart_class()
    old_chart = shipped.MiniEquityChart()
    old_chart.set_data(curve)
    new_chart = chart_class(curve, surface.CHART_SKIN)
    assert_pictures_match(
        old_side=render_offscreen(old_chart, CHART_SIZE),
        new_side=render_offscreen(new_chart, CHART_SIZE),
        note="chart, %d points, %s" % (len(curve), font_note()),
    )


def test_the_two_sides_paint_one_tab():
    """The surface painted a different tab than the shipped widget."""
    app()
    source = Source(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    assert_pictures_match(
        old_side=render_offscreen(shipped_tab(source), PIXEL_SIZE),
        new_side=render_offscreen(build_tab(full_payload(), RISING_CURVE), PIXEL_SIZE),
        note="full tab, %s" % font_note(),
    )


def test_the_two_sides_paint_one_empty_tab():
    """The surface painted a different waiting tab than the widget."""
    app()
    source = Source({}, [], [], {})
    assert_pictures_match(
        old_side=render_offscreen(shipped_tab(source), PIXEL_SIZE),
        new_side=render_offscreen(
            build_tab(payload_for({}, [], [], {}), []), PIXEL_SIZE
        ),
        note="empty tab, %s" % font_note(),
    )


def test_the_two_sides_paint_one_unrefreshed_tab():
    """The surface painted a different tab before any refresh."""
    app()
    payload = surface.build_view_model()
    for one in payload["cards"]:
        one["value"] = surface.CARD_SKIN["default_value"]
        one["color"] = surface.TEXT_HIGH
        one["value_style"] = surface.card_value_style(surface.TEXT_HIGH)
    assert_pictures_match(
        old_side=render_offscreen(shipped_tab(), PIXEL_SIZE),
        new_side=render_offscreen(build_tab(payload, []), PIXEL_SIZE),
        note="unrefreshed tab, %s" % font_note(),
    )


def test_the_picture_comparison_can_report_a_difference():
    """The picture check passes whatever the second side paints.

    Two real sets of numbers, one taken from each side. A pass proves
    the comparison reports a tab painted differently, so the matches
    above are not green by being unable to fail.
    """
    app()
    old_source = Source(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    assert_pictures_differ(
        old_side=render_offscreen(shipped_tab(old_source), PIXEL_SIZE),
        new_side=render_offscreen(
            build_tab(payload_for({}, [], [], {}), []), PIXEL_SIZE
        ),
        note="full numbers against no numbers, %s" % font_note(),
    )


def test_the_chart_picture_comparison_can_report_a_difference():
    """The chart picture check passes whatever the second side paints."""
    app()
    chart_class = _build_chart_class()
    old_chart = shipped.MiniEquityChart()
    old_chart.set_data(RISING_CURVE)
    assert_pictures_differ(
        old_side=render_offscreen(old_chart, CHART_SIZE),
        new_side=render_offscreen(
            chart_class(FALLING_CURVE, surface.CHART_SKIN), CHART_SIZE
        ),
        note="a gain against a loss, %s" % font_note(),
    )


@pytest.mark.parametrize("curve", [RISING_CURVE, FALLING_CURVE, []])
def test_the_painted_chart_shows_more_than_one_colour(curve):
    """The two sides matched because the chart painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    chart_class = _build_chart_class()
    image = render_offscreen(chart_class(curve, surface.CHART_SKIN), CHART_SIZE)
    assert image.width() == CHART_SIZE[0]
    assert image.height() == CHART_SIZE[1]
    seen = set()
    for x in range(0, image.width(), 3):
        for y in range(0, image.height(), 3):
            seen.add(QColor(image.pixelColor(x, y)).name())
    assert len(seen) > 1, "the chart painted one colour, so no change could show"


def test_the_painted_tab_shows_more_than_one_colour():
    """The two sides matched because the tab painted one flat colour."""
    app()
    from PySide6.QtGui import QColor

    image = render_offscreen(build_tab(full_payload(), RISING_CURVE), PIXEL_SIZE)
    seen = set()
    for x in range(0, image.width(), 5):
        for y in range(0, image.height(), 5):
            seen.add(QColor(image.pixelColor(x, y)).name())
    assert len(seen) > 2, f"the tab painted {len(seen)} colours"


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on.

    With no font database every family resolves to a box advancing one
    em per character, so two strings of equal length need equal width.
    With a font database the glyphs decide the width. Both answers are
    handled here and the file is run both ways.
    """
    app()
    from PySide6.QtWidgets import QLabel

    narrow = QLabel("iiii")
    wide = QLabel("WWWW")
    if has_real_fonts():
        assert (
            narrow.sizeHint().width() != wide.sizeHint().width()
        ), "the host reports fonts and every glyph still has one width"
    else:
        assert (
            narrow.sizeHint().width() == wide.sizeHint().width()
        ), "the host reports no fonts and the glyphs still have their own widths"


# What no picture can report, each read off both sides instead


def test_the_accessible_names_are_compared_as_text():
    """A name assistive software reads changed and no pixel moved."""
    tab = shipped_tab()
    card = tab.layout().itemAt(0).layout().itemAt(0).widget()
    assert tab.accessibleName() == surface.TAB_ACCESSIBLE_NAME
    assert card.accessibleName() == surface.CARD_SKIN["accessible_name"]
    assert tab._equity_chart.accessibleName() == surface.CHART_SKIN["accessible_name"]
    assert surface.TAB_ACCESSIBLE_NAME == "Analytics Tab"
    assert surface.CARD_SKIN["accessible_name"] == "Metric Card"
    assert surface.CHART_SKIN["accessible_name"] == "Mini Equity Chart"


def test_the_table_settings_no_picture_shows_are_compared_as_values():
    """A table setting changed that an unclicked table never shows."""
    from PySide6.QtWidgets import QTableWidget

    tab = shipped_tab()
    assert tab._bot_table.selectionBehavior() == QTableWidget.SelectRows
    assert tab._tf_table.selectionBehavior() == QTableWidget.SelectItems
    assert tab._bot_table.editTriggers() == QTableWidget.NoEditTriggers
    assert tab._tf_table.editTriggers() == QTableWidget.NoEditTriggers
    assert surface.BOT_TABLE["selection_behavior"] == "rows"
    assert surface.TIMEFRAME_TABLE["selection_behavior"] == "items"
    assert surface.BOT_TABLE["edit_triggers"] == "none"
    assert surface.TIMEFRAME_TABLE["edit_triggers"] == "none"


def test_the_alternating_row_colour_is_compared_as_a_value():
    """Alternating rows were switched off and no row was on screen."""
    tab = shipped_tab()
    assert tab._bot_table.alternatingRowColors() is True
    assert tab._tf_table.alternatingRowColors() is True
    assert surface.BOT_TABLE["alternating_row_colors"] is True
    assert surface.TIMEFRAME_TABLE["alternating_row_colors"] is True


def test_the_colour_with_two_equal_channels_is_compared_as_text():
    """A colour whose channels match had two of them swapped."""
    equal_channel = []
    for name, value in surface.COLORS.items():
        digits = value.lstrip("#")
        if len(digits) == 3:
            channels = (digits[0], digits[1], digits[2])
        else:
            channels = (digits[0:2], digits[2:4], digits[4:6])
        if len(set(channels)) < 3:
            equal_channel.append(name)
    assert "card_label" in equal_channel
    assert len(equal_channel) > 1, equal_channel
    for name in equal_channel:
        assert surface.COLORS[name] == EXPECTED_COLORS[name], name
    assert surface.CARD_LABEL_COLOR == "#888"
    assert surface.CARD_LABEL_STYLE == EXPECTED_CARD_LABEL_STYLE


def test_the_colours_two_names_share_are_compared_by_name():
    """Two names carrying one colour were swapped and nothing moved."""
    repeated = {}
    for name, value in surface.COLORS.items():
        repeated.setdefault(value, []).append(name)
    shared = {value: names for value, names in repeated.items() if len(names) > 1}
    for value, names in shared.items():
        for name in names:
            assert EXPECTED_COLORS[name] == value, name
    assert surface.COLORS == EXPECTED_COLORS
    assert len(surface.COLORS) == len(EXPECTED_COLORS) == 12


def test_the_hidden_row_number_column_is_compared_as_a_value():
    """The row number column came back and no cell moved."""
    tab = shipped_tab()
    assert tab._bot_table.verticalHeader().isVisible() is False
    assert tab._tf_table.verticalHeader().isVisible() is False
    assert surface.BOT_TABLE["vertical_header_visible"] is False
    assert surface.TIMEFRAME_TABLE["vertical_header_visible"] is False


def test_the_requested_splitter_sizes_are_compared_as_values():
    """A requested splitter size changed inside what Qt then rescales."""
    assert surface.MAIN_SPLITTER["sizes_px"] == EXPECTED_MAIN_SIZES_PX
    assert surface.BOTTOM_SPLITTER["sizes_px"] == EXPECTED_BOTTOM_SIZES_PX
    assert surface.MAIN_SPLITTER["sizes_px"] != surface.BOTTOM_SPLITTER["sizes_px"]


def test_the_hours_the_curve_is_asked_for_are_compared_as_a_value():
    """The equity window changed and the chart looked the same."""
    old, new = both_displays(FULL_SUMMARY, RISING_CURVE, [], {})
    assert old["hours_asked"] == new["hours_asked"] == [24]
    assert surface.EQUITY_CURVE_HOURS == EXPECTED_EQUITY_CURVE_HOURS


BLIND_TO_THE_PICTURE = {
    "accessible_names": "test_the_accessible_names_are_compared_as_text",
    "selection_behaviour": (
        "test_the_table_settings_no_picture_shows_are_compared_as_values"
    ),
    "edit_triggers": (
        "test_the_table_settings_no_picture_shows_are_compared_as_values"
    ),
    "alternating_rows": "test_the_alternating_row_colour_is_compared_as_a_value",
    "equal_channel_colour": (
        "test_the_colour_with_two_equal_channels_is_compared_as_text"
    ),
    "repeated_colours": "test_the_colours_two_names_share_are_compared_by_name",
    "hidden_row_numbers": "test_the_hidden_row_number_column_is_compared_as_a_value",
    "requested_splitter_sizes": (
        "test_the_requested_splitter_sizes_are_compared_as_values"
    ),
    "equity_curve_hours": (
        "test_the_hours_the_curve_is_asked_for_are_compared_as_a_value"
    ),
    "card_keys": "test_the_card_labels_and_their_keys_match",
    "number_formats": "test_the_number_formats_read_as_typed_here",
    "summary_defaults": "test_summary_value_falls_back_only_for_a_missing_key",
    "bot_fields": "test_bot_values_reads_the_ten_fields_the_row_needs",
    "no_source_branch": "test_the_model_returns_nothing_when_there_is_no_source",
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report.

    Fourteen things never reach a pixel comparison, each named here
    with the check that does cover it.
    """
    assert len(BLIND_TO_THE_PICTURE) == 14
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert len(set(BLIND_TO_THE_PICTURE.values())) == 13


# Nothing the surface holds is left out of the snapshot

# Every constant the surface exports and the payload key that carries it.
CONSTANT_LOCATION = {
    "TAB_ACCESSIBLE_NAME": ("accessible_name", None),
    "PAGE": ("page", None),
    "CARD_ORDER": ("card_order", None),
    "CARD_LABELS": ("card_labels", None),
    "CARD_SKIN": ("card_skin", None),
    "MAIN_SPLITTER": ("main_splitter", None),
    "BOTTOM_SPLITTER": ("bottom_splitter", None),
    "GROUPS": ("groups", None),
    "GROUP_ORDER": ("group_order", None),
    "BOT_TABLE": ("bot_table", None),
    "TIMEFRAME_TABLE": ("timeframe_table", None),
    "BOT_COLUMNS": ("bot_columns", None),
    "TIMEFRAME_COLUMNS": ("timeframe_columns", None),
    "BOT_FIELDS": ("bot_fields", None),
    "TIMEFRAME_FIELDS": ("timeframe_fields", None),
    "CHART_SKIN": ("chart_skin", None),
    "EQUITY_CURVE_HOURS": ("equity_curve_hours", None),
    "SUMMARY_DEFAULTS": ("summary_defaults", None),
    "NUMBER_FORMATS": ("number_formats", None),
    "COLORS": ("colors", None),
    "ACTIONS": ("actions", None),
    "TIMERS": ("timers", None),
    "TIMER_DELAYS_MS": ("timer_delays_ms", None),
    "SKIN": ("skin", None),
    "CARD_CLASS_NAME": ("card_skin", "class_name"),
    "CARD_ACCESSIBLE_NAME": ("card_skin", "accessible_name"),
    "CARD_DEFAULT_VALUE": ("card_skin", "default_value"),
    "CARD_SURFACE": ("card_skin", "surface"),
    "CARD_BORDER": ("card_skin", "border"),
    "CARD_LABEL_COLOR": ("card_skin", "label_color"),
    "SUCCESS": ("colors", "success"),
    "ERROR": ("colors", "error"),
    "WARNING": ("colors", "warning"),
    "PRIMARY": ("colors", "primary"),
    "TEXT_HIGH": ("colors", "text_high"),
    "TEXT_MUTED": ("colors", "text_muted"),
    "TEXT_PLACEHOLDER": ("colors", "text_placeholder"),
    "SURFACE_CHART": ("colors", "surface_chart"),
    "SURFACE_CONTROL": ("colors", "surface_control"),
    "CHART_MIN_HEIGHT_PX": ("chart_skin", "min_height_px"),
    "CHART_MARGIN_PX": ("chart_skin", "margin_px"),
    "CHART_GRID_LINE_COUNT": ("chart_skin", "grid_line_count"),
    "CHART_GRID_DIVISOR": ("chart_skin", "grid_divisor"),
    "CHART_GRID_WIDTH_PX": ("chart_skin", "grid_width_px"),
    "CHART_LINE_WIDTH_PX": ("chart_skin", "line_width_px"),
    "CHART_MIN_POINTS": ("chart_skin", "min_points"),
    "CHART_MIN_SCALE": ("chart_skin", "min_scale"),
    "CHART_MAX_SCALE": ("chart_skin", "max_scale"),
    "CHART_RANGE_FALLBACK": ("chart_skin", "range_fallback"),
    "CHART_EMPTY_TEXT": ("chart_skin", "empty_text"),
    "CHART_FONT_FAMILY": ("chart_skin", "font_family"),
    "CHART_FONT_POINT_SIZE": ("chart_skin", "font_point_size"),
    "PNL_FORMAT": ("number_formats", "pnl"),
    "PERCENT_FORMAT": ("number_formats", "percent"),
    "RATIO_FORMAT": ("number_formats", "ratio"),
    "MONEY_FORMAT": ("number_formats", "money"),
    "INFINITY_TEXT": ("number_formats", "infinity"),
    "BOT_ID_LENGTH": ("number_formats", "bot_id_length"),
    "SECONDS_PER_MINUTE": ("number_formats", "seconds_per_minute"),
    "SECONDS_PER_HOUR": ("number_formats", "seconds_per_hour"),
    "SECONDS_PER_DAY": ("number_formats", "seconds_per_day"),
    "DURATION_SECOND_FORMAT": ("number_formats", "duration_second"),
    "DURATION_MINUTE_FORMAT": ("number_formats", "duration_minute"),
    "DURATION_HOUR_FORMAT": ("number_formats", "duration_hour"),
    "DURATION_DAY_FORMAT": ("number_formats", "duration_day"),
    "CELL_ALIGNMENT": ("bot_table", "cell_alignment"),
}

# The constants no snapshot key carries, each with the check that
# covers it.
NOT_IN_THE_SNAPSHOT = {
    "METHOD": "test_the_bridge_registers_the_analytics_tab_method",
    "CARD_FRAME_STYLE": "test_the_metric_card_skin_matches_on_both_sides",
    "CARD_LABEL_STYLE": "test_the_metric_card_skin_matches_on_both_sides",
    "CARD_VALUE_STYLE_FORMAT": "test_the_card_helper_carries_the_label_and_the_style",
    "GROUP_STYLE_BOLD": "test_the_group_boxes_match_on_both_sides",
    "GROUP_STYLE_PLAIN": "test_the_group_boxes_match_on_both_sides",
    "CHART_TOP_LABEL_OFFSET_PX": (
        "test_the_chart_labels_the_latest_equity_and_the_scaled_floor"
    ),
    "CHART_BOTTOM_LABEL_OFFSET_PX": (
        "test_the_chart_labels_the_latest_equity_and_the_scaled_floor"
    ),
    "CHART_RISE_FILL": "test_a_rising_curve_is_green_and_a_falling_curve_is_red",
    "CHART_FALL_FILL": "test_a_rising_curve_is_green_and_a_falling_curve_is_red",
    "NO_COLOR": "test_the_cell_helper_carries_the_text_and_the_colour",
    "NO_REFRESH": "test_the_model_returns_nothing_when_there_is_no_source",
    "NO_ROWS": "test_bot_rows_and_timeframe_rows_are_empty_for_no_data",
}

CONSTANT_TOTAL = 79


def surface_constants():
    """Every value the surface exports that is not a function or a class."""
    import types

    return {
        name: value
        for name, value in vars(surface).items()
        if not name.startswith("_")
        and not callable(value)
        and not isinstance(value, types.ModuleType)
        and name != "annotations"
    }


def test_every_constant_the_surface_holds_reaches_the_snapshot():
    """A constant the surface exports is in no snapshot the tests read.

    Every constant is accounted for: a snapshot key, a key inside one,
    or one of the names below with the check that covers it.
    """
    payload = surface.build_view_model()
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in CONSTANT_LOCATION:
            key, inner = CONSTANT_LOCATION[name]
            carried = payload[key] if inner is None else payload[key][inner]
            wanted = list(value) if isinstance(value, tuple) else value
            assert carried == wanted, (name, carried, wanted)
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
            assert callable(globals()[covered_by]), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted
    assert len(CONSTANT_LOCATION) + len(NOT_IN_THE_SNAPSHOT) == CONSTANT_TOTAL


def test_every_snapshot_key_carries_a_constant_the_surface_holds():
    """The snapshot grew a key no constant on the surface backs."""
    payload = surface.build_view_model()
    from_constants = {key for key, _ in CONSTANT_LOCATION.values()}
    built_per_call = {"cards", "bot_rows", "timeframe_rows", "chart"}
    assert set(payload) == from_constants | built_per_call
    assert len(payload) == 28
    for key in built_per_call:
        assert key in payload


def test_the_completeness_check_can_report_a_missing_constant():
    """The completeness check passed because it looks at nothing.

    A constant that reaches no snapshot key and no named exception must
    land in the unaccounted list, or the check above is empty.
    """
    payload = surface.build_view_model()
    invented = "INVENTED_CONSTANT"
    assert invented not in CONSTANT_LOCATION
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in payload
    assert invented not in surface_constants()
    assert "BOT_COLUMNS" in surface_constants()
    assert "CHART_SKIN" in surface_constants()
    assert "chart_geometry" not in surface_constants()
    assert "AnalyticsTabModel" not in surface_constants()
    assert "view_model" not in surface_constants()


# The bridge


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    payload = surface.view_model(
        {
            "summary": FULL_SUMMARY,
            "curve": RISING_CURVE,
            "bots": [surface.bot_values(one) for one in FULL_BOTS[:1]],
            "timeframes": FULL_TIMEFRAMES,
            "width": 800,
            "height": 300,
        }
    )
    text = json.dumps(payload, ensure_ascii=True)
    back = json.loads(text)
    assert back["cards"][0]["value"] == "$+1,234.5679"
    assert back["bot_columns"] == list(EXPECTED_BOT_COLUMNS)
    assert back["chart"]["empty"] is False
    assert back["timeframe_rows"][0][0]["text"] == "15m"


def test_the_bridge_registers_the_analytics_tab_method():
    """The renderer cannot reach the analytics tab through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == METHOD_NAME
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 21,
                "method": surface.METHOD,
                "params": {"summary": FULL_SUMMARY},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["cards"][0]["value"] == "$+1,234.5679"
    assert result["accessible_name"] == "Analytics Tab"
    assert len(result["cards"]) == CARD_TOTAL


def test_the_bridge_registers_this_surface_once_and_by_identity():
    """The registry maps ``surface.METHOD`` to ``surface.view_model`` itself, and
    to nothing else."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert registry[surface.METHOD] is surface.view_model
    mine = [m for m, fn in registry.items() if fn is surface.view_model]
    assert mine == [surface.METHOD], mine


def test_the_bridge_answers_with_no_parameters_at_all():
    """A request carrying no numbers ended the session."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps({"id": 22, "method": surface.METHOD}), registry
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert [one["value"] for one in result["cards"]] == [
        one[1] for one in EXPECTED_EMPTY_CARD_VALUES
    ]
    assert result["bot_rows"] == []
    assert result["timeframe_rows"] == []
    assert result["chart"]["empty"] is True


def test_the_bridge_ignores_a_parameter_it_does_not_know():
    """A parameter the surface does not read ended the request."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 23,
                "method": surface.METHOD,
                "params": {"summary": {}, "invented": [1, 2], "group": "x"},
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    assert "invented" not in answer["result"]
    assert answer["result"]["accessible_name"] == "Analytics Tab"


def test_the_bridge_reports_a_request_the_surface_refuses():
    """A bad set of numbers ended the session instead of answering."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 24,
                "method": surface.METHOD,
                "params": {"timeframes": {"1h": {"win_rate": 1.0}}},
            }
        ),
        registry,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "KeyError"


def test_the_table_is_the_same_on_every_call():
    """The answer changed between two calls with the same numbers."""
    first = surface.view_model({"summary": FULL_SUMMARY})
    second = surface.view_model({})
    third = surface.view_model({"summary": FULL_SUMMARY})
    assert first == third
    assert digest(first) == digest(third)
    assert first != second
    assert first["bot_columns"] == second["bot_columns"]


# The surface without Qt, proved in a process of its own

BLOCK_QT = (
    "import sys\n"
    "class Refuse:\n"
    "    def find_module(self, name, path=None):\n"
    "        return self\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name.split('.')[0] in ('PySide6', 'shiboken6'):\n"
    "            raise ImportError('Qt is blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, Refuse())\n"
)

BRIDGE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.core import desktop_bridge\n"
    "registry = desktop_bridge.build_registry()\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1,\n"
    "    'method': 'analytics.tab',\n"
    "    'params': {'summary': {'total_pnl': 1234.56789}}}), registry)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules, 'frame': frame}))\n"
)

TABLE_PROBE = BLOCK_QT + (
    "import json\n"
    "from src.gui.main_tabs import analytics_tab_surface as s\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'cards': s.summary_cards({}),\n"
    "    'bot_columns': list(s.BOT_COLUMNS),\n"
    "    'timeframe_columns': list(s.TIMEFRAME_COLUMNS),\n"
    "    'colors': dict(s.COLORS),\n"
    "    'chart': s.chart_geometry([], 520, 260),\n"
    "    'duration': s.duration_text(3600),\n"
    "    'no_source': s.AnalyticsTabModel().refresh()}))\n"
)


def run_script(source):
    """Run one probe in a fresh process and return what it printed."""
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the analytics tab pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["cards"][0]["value"] == "$+1,234.5679"
    assert result["accessible_name"] == "Analytics Tab"
    assert len(result["cards"]) == CARD_TOTAL


def test_the_surface_carries_every_value_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(TABLE_PROBE)
    assert answered["qt"] is False
    assert [one["value"] for one in answered["cards"]] == [
        one[1] for one in EXPECTED_EMPTY_CARD_VALUES
    ]
    assert answered["bot_columns"] == list(EXPECTED_BOT_COLUMNS)
    assert answered["timeframe_columns"] == list(EXPECTED_TIMEFRAME_COLUMNS)
    assert answered["colors"] == EXPECTED_COLORS
    assert answered["chart"]["empty"] is True
    assert answered["chart"]["text"] == EXPECTED_CHART_EMPTY_TEXT
    assert answered["duration"] == "1.0h"
    assert answered["no_source"] is None


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script(
        "import sys"
        + chr(10)
        + "import PySide6.QtCore"
        + chr(10)
        + BRIDGE_PROBE.replace(BLOCK_QT, "")
    )
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_qt_block_stops_the_shipped_tab():
    """The Qt block let the shipped tab through, so it proves nothing."""
    probe = BLOCK_QT + (
        "import json\n"
        "from src.gui import analytics_tab as t\n"
        "print(json.dumps({'has_qt': t._HAS_QT,\n"
        "    'has_tab': hasattr(t, 'AnalyticsTab')}))\n"
    )
    answered = run_script(probe)
    assert answered["has_qt"] is False
    assert answered["has_tab"] is False


# The Qt tab stays reachable while the React panel is unproven

#: Every widget the tab builds for itself. Qt furniture is left out; its count
#: moves with the interface library.
QT_CHILD_CENSUS = {
    "MetricCard": 8,
    "QLabel": 16,
    "MiniEquityChart": 1,
    "QGroupBox": 3,
    "QSplitter": 2,
    "QTableWidget": 2,
}


def qt_children(tab):
    """How many of each widget class the tab holds, its own classes only."""
    from PySide6.QtWidgets import QWidget

    found: dict = {}
    for child in tab.findChildren(QWidget):
        name = type(child).__name__
        if name in QT_CHILD_CENSUS:
            found[name] = found.get(name, 0) + 1
    return found


def test_the_shipped_tab_still_builds_every_widget_it_ever_built():
    """A Qt widget left the analytics tab.

    The React panel that draws this tab renders but is not yet verified
    by a run of the application, so the Qt tab it replaces must stay
    whole and reachable. A widget removed here is caught by the count,
    not by anyone noticing the screen is short.
    """
    tab = shipped_tab()
    assert shipped._HAS_QT is True
    assert qt_children(tab) == QT_CHILD_CENSUS
    assert sum(QT_CHILD_CENSUS.values()) == 32


def test_the_shipped_tab_still_fills_every_widget_from_a_source():
    """The Qt tab stopped showing what a source hands it."""
    source = Source(FULL_SUMMARY, RISING_CURVE, FULL_BOTS, FULL_TIMEFRAMES)
    tab = shipped_tab(source)
    assert qt_children(tab) == QT_CHILD_CENSUS
    assert tab._bot_table.rowCount() == len(FULL_BOTS)
    assert tab._tf_table.rowCount() == len(FULL_TIMEFRAMES)
    assert tab._equity_chart._data == RISING_CURVE
    assert read_cards(tab)[0][1] == "$+1,234.5679"


def test_the_child_count_reports_a_widget_that_left_the_tab():
    """The census counts nothing, so a missing widget would pass.

    One card is taken off the built tab and the census must report the
    loss. Nothing shipped is changed: the tab is thrown away afterwards.
    """
    tab = shipped_tab()
    assert qt_children(tab) == QT_CHILD_CENSUS
    tab._card_pnl.setParent(None)
    short = qt_children(tab)
    assert short != QT_CHILD_CENSUS
    assert short["MetricCard"] == QT_CHILD_CENSUS["MetricCard"] - 1
    assert short["QLabel"] == QT_CHILD_CENSUS["QLabel"] - 2
    assert qt_children(shipped_tab()) == QT_CHILD_CENSUS
