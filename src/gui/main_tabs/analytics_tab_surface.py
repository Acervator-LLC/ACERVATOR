"""analytics_tab_surface.py -- the performance analytics dashboard, without Qt.

Describes every part the analytics tab draws: eight metric cards, one
painted equity chart, a ten-column bot table and a four-column
timeframe table, held in two splitters inside three group boxes.

The card values, the table cells and the chart geometry are built from
the numbers an analytics source hands over. Every colour, every layout
number, every column heading and every number format is written out
here rather than read from ``src.gui.analytics_tab`` or from
``src.gui.design_system``, so a value changed on one side alone is
reported.

``AnalyticsTabModel`` holds the source the tab was built with.
``refresh`` reads the four number sets the tab shows and returns them,
and returns ``None`` for a source that is missing or empty, which is
the one case where the tab shows nothing new.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``analytics.tab`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

from typing import Any, Optional

METHOD = "analytics.tab"

TAB_ACCESSIBLE_NAME = "Analytics Tab"

SUCCESS = "#00ff88"
ERROR = "#ff3366"
WARNING = "#ffaa00"
PRIMARY = "#00ffcc"
TEXT_HIGH = "#e0e0f0"
TEXT_MUTED = "#666666"
TEXT_PLACEHOLDER = "#555555"
SURFACE_CHART = "#0a0a12"
SURFACE_CONTROL = "#1a1a2e"
CARD_SURFACE = "#12121f"
CARD_BORDER = "#2a2a3f"
CARD_LABEL_COLOR = "#888"

COLORS: dict[str, str] = {
    "success": SUCCESS,
    "error": ERROR,
    "warning": WARNING,
    "primary": PRIMARY,
    "text_high": TEXT_HIGH,
    "text_muted": TEXT_MUTED,
    "text_placeholder": TEXT_PLACEHOLDER,
    "surface_chart": SURFACE_CHART,
    "surface_control": SURFACE_CONTROL,
    "card_surface": CARD_SURFACE,
    "card_border": CARD_BORDER,
    "card_label": CARD_LABEL_COLOR,
}

NO_COLOR = ""
NO_REFRESH = None
NO_ROWS: list = []

PAGE: dict[str, Any] = {
    "margins_px": [8, 8, 8, 8],
    "spacing_px": 8,
    "children": ["metrics_row", "main_splitter"],
}

CARD_CLASS_NAME = "MetricCard"
CARD_ACCESSIBLE_NAME = "Metric Card"
CARD_DEFAULT_VALUE = "---"

CARD_ORDER = (
    "pnl",
    "win_rate",
    "sharpe",
    "profit_factor",
    "trades",
    "drawdown",
    "expectancy",
    "trades_today",
)

CARD_LABELS: dict[str, str] = {
    "pnl": "Total P/L",
    "win_rate": "Win Rate",
    "sharpe": "Sharpe Ratio",
    "profit_factor": "Profit Factor",
    "trades": "Total Trades",
    "drawdown": "Max Drawdown",
    "expectancy": "Expectancy",
    "trades_today": "Trades Today",
}

CARD_SKIN: dict[str, Any] = {
    "class_name": CARD_CLASS_NAME,
    "accessible_name": CARD_ACCESSIBLE_NAME,
    "default_value": CARD_DEFAULT_VALUE,
    "frame_shape": "styled_panel",
    "label_color": CARD_LABEL_COLOR,
    "value_color": TEXT_HIGH,
    "label_size_px": 10,
    "value_size_px": 16,
    "padding_px": [10, 8, 10, 8],
    "spacing_px": 2,
    "surface": CARD_SURFACE,
    "border": CARD_BORDER,
    "radius_px": 6,
    "children": ["label", "value"],
}

CARD_FRAME_STYLE = (
    "MetricCard { background: #12121f; "
    "border: 1px solid #2a2a3f; "
    "border-radius: 6px; }"
)

CARD_LABEL_STYLE = "color: #888; font-size: 10px;"

CARD_VALUE_STYLE_FORMAT = "color: {color}; font-size: 16px; font-weight: bold;"

GROUP_STYLE_BOLD = (
    "QGroupBox { background: #0a0a12; "
    "border: 1px solid #2a2a3f; "
    "border-radius: 6px; color: #00ffcc; font-weight: bold; }"
)

GROUP_STYLE_PLAIN = (
    "QGroupBox { background: #0a0a12; "
    "border: 1px solid #2a2a3f; "
    "border-radius: 6px; color: #00ffcc; }"
)

GROUPS: dict[str, dict[str, str]] = {
    "equity": {
        "title": "Equity Curve",
        "style": GROUP_STYLE_BOLD,
        "child": "equity_chart",
    },
    "bots": {
        "title": "Bot Performance",
        "style": GROUP_STYLE_PLAIN,
        "child": "bot_table",
    },
    "timeframes": {
        "title": "Timeframe Performance",
        "style": GROUP_STYLE_PLAIN,
        "child": "timeframe_table",
    },
}

GROUP_ORDER = ("equity", "bots", "timeframes")

MAIN_SPLITTER: dict[str, Any] = {
    "orientation": "vertical",
    "handle_width_px": 5,
    "children_collapsible": False,
    "sizes_px": [250, 350],
    "children": ["equity_group", "bottom_splitter"],
}

BOTTOM_SPLITTER: dict[str, Any] = {
    "orientation": "horizontal",
    "handle_width_px": 5,
    "children_collapsible": False,
    "sizes_px": [600, 300],
    "children": ["bot_group", "timeframe_group"],
}

BOT_COLUMNS = (
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

TIMEFRAME_COLUMNS = ("Timeframe", "Trades", "Win Rate", "Total P/L")

CELL_ALIGNMENT = "center"

BOT_TABLE: dict[str, Any] = {
    "column_count": 10,
    "columns": list(BOT_COLUMNS),
    "resize_mode": "stretch",
    "alternating_row_colors": True,
    "selection_behavior": "rows",
    "edit_triggers": "none",
    "vertical_header_visible": False,
    "cell_alignment": CELL_ALIGNMENT,
    "colored_column": 4,
}

TIMEFRAME_TABLE: dict[str, Any] = {
    "column_count": 4,
    "columns": list(TIMEFRAME_COLUMNS),
    "resize_mode": "stretch",
    "alternating_row_colors": True,
    "selection_behavior": "items",
    "edit_triggers": "none",
    "vertical_header_visible": False,
    "cell_alignment": CELL_ALIGNMENT,
    "colored_column": None,
}

BOT_FIELDS = (
    "bot_id",
    "symbol",
    "total_trades",
    "win_rate",
    "total_pnl",
    "profit_factor",
    "sharpe_ratio",
    "max_drawdown_pct",
    "avg_hold_seconds",
    "expectancy",
)

TIMEFRAME_FIELDS = ("total_trades", "win_rate", "total_pnl")

CHART_MIN_HEIGHT_PX = 200
CHART_MARGIN_PX = 40
CHART_GRID_LINE_COUNT = 5
CHART_GRID_DIVISOR = 4
CHART_GRID_WIDTH_PX = 1
CHART_LINE_WIDTH_PX = 2
CHART_MIN_POINTS = 2
CHART_MIN_SCALE = 0.998
CHART_MAX_SCALE = 1.002
CHART_RANGE_FALLBACK = 1
CHART_EMPTY_TEXT = "Collecting equity data..."
CHART_FONT_FAMILY = "Consolas"
CHART_FONT_POINT_SIZE = 9
CHART_TOP_LABEL_OFFSET_PX = (5, 15)
CHART_BOTTOM_LABEL_OFFSET_PX = (5, -5)
CHART_RISE_FILL = ((0, 255, 136, 40), (0, 255, 136, 5))
CHART_FALL_FILL = ((255, 51, 102, 40), (255, 51, 102, 5))

CHART_SKIN: dict[str, Any] = {
    "accessible_name": "Mini Equity Chart",
    "min_height_px": CHART_MIN_HEIGHT_PX,
    "margin_px": CHART_MARGIN_PX,
    "grid_line_count": CHART_GRID_LINE_COUNT,
    "grid_divisor": CHART_GRID_DIVISOR,
    "grid_width_px": CHART_GRID_WIDTH_PX,
    "grid_color": SURFACE_CONTROL,
    "background": SURFACE_CHART,
    "line_width_px": CHART_LINE_WIDTH_PX,
    "min_points": CHART_MIN_POINTS,
    "min_scale": CHART_MIN_SCALE,
    "max_scale": CHART_MAX_SCALE,
    "range_fallback": CHART_RANGE_FALLBACK,
    "empty_text": CHART_EMPTY_TEXT,
    "empty_text_color": TEXT_PLACEHOLDER,
    "empty_antialiased": False,
    "antialiased": True,
    "font_family": CHART_FONT_FAMILY,
    "font_point_size": CHART_FONT_POINT_SIZE,
    "top_label_offset_px": list(CHART_TOP_LABEL_OFFSET_PX),
    "bottom_label_offset_px": list(CHART_BOTTOM_LABEL_OFFSET_PX),
    "top_label_color": TEXT_HIGH,
    "bottom_label_color": TEXT_MUTED,
    "rise_fill": [list(stop) for stop in CHART_RISE_FILL],
    "fall_fill": [list(stop) for stop in CHART_FALL_FILL],
    "rise_line_color": SUCCESS,
    "fall_line_color": ERROR,
}

EQUITY_CURVE_HOURS = 24

SUMMARY_DEFAULTS: dict[str, int] = {
    "total_pnl": 0,
    "win_rate": 0,
    "sharpe_ratio": 0,
    "profit_factor": 0,
    "total_trades": 0,
    "max_drawdown": 0,
    "expectancy": 0,
    "trades_today": 0,
}

PNL_FORMAT = "${value:+,.4f}"
PERCENT_FORMAT = "{value:.1f}%"
RATIO_FORMAT = "{value:.2f}"
MONEY_FORMAT = "${value:,.2f}"
INFINITY_TEXT = "∞"
BOT_ID_LENGTH = 8
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400
DURATION_SECOND_FORMAT = "{value:.0f}s"
DURATION_MINUTE_FORMAT = "{value:.1f}m"
DURATION_HOUR_FORMAT = "{value:.1f}h"
DURATION_DAY_FORMAT = "{value:.1f}d"

NUMBER_FORMATS: dict[str, Any] = {
    "pnl": PNL_FORMAT,
    "percent": PERCENT_FORMAT,
    "ratio": RATIO_FORMAT,
    "money": MONEY_FORMAT,
    "infinity": INFINITY_TEXT,
    "bot_id_length": BOT_ID_LENGTH,
    "seconds_per_minute": SECONDS_PER_MINUTE,
    "seconds_per_hour": SECONDS_PER_HOUR,
    "seconds_per_day": SECONDS_PER_DAY,
    "duration_second": DURATION_SECOND_FORMAT,
    "duration_minute": DURATION_MINUTE_FORMAT,
    "duration_hour": DURATION_HOUR_FORMAT,
    "duration_day": DURATION_DAY_FORMAT,
}

ACTIONS: dict[str, str] = {}
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
SKIN: dict[str, str] = {}


def pnl_text(value: Any) -> str:
    """A profit or loss as ``$+1,234.5678`` -- always signed, four decimals."""
    return PNL_FORMAT.format(value=value)


def percent_text(value: Any) -> str:
    """A percentage to one decimal, followed by the per-cent sign."""
    return PERCENT_FORMAT.format(value=value)


def ratio_text(value: Any) -> str:
    """A ratio to two decimals."""
    return RATIO_FORMAT.format(value=value)


def money_text(value: Any) -> str:
    """A dollar amount to two decimals, grouped in thousands."""
    return MONEY_FORMAT.format(value=value)


def count_text(value: Any) -> str:
    """A count, shown exactly as Python renders the value it was given."""
    return str(value)


def profit_factor_text(value: Any) -> str:
    """A profit factor to two decimals, or the infinity sign for no losses."""
    if value != float("inf"):
        return ratio_text(value)
    return INFINITY_TEXT


def duration_text(seconds: Any) -> str:
    """A hold time as seconds, minutes, hours or days.

    Carries the thresholds ``AnalyticsEngine._format_duration`` uses, so
    the frontend renders the Avg Hold column with no engine present.
    """
    if seconds < SECONDS_PER_MINUTE:
        return DURATION_SECOND_FORMAT.format(value=seconds)
    if seconds < SECONDS_PER_HOUR:
        return DURATION_MINUTE_FORMAT.format(value=seconds / SECONDS_PER_MINUTE)
    if seconds < SECONDS_PER_DAY:
        return DURATION_HOUR_FORMAT.format(value=seconds / SECONDS_PER_HOUR)
    return DURATION_DAY_FORMAT.format(value=seconds / SECONDS_PER_DAY)


def bot_id_text(bot_id: Any) -> Any:
    """The first eight characters of a bot's identifier."""
    return bot_id[:BOT_ID_LENGTH]


def pnl_color(value: Any) -> str:
    """Green at or above zero, red below."""
    return SUCCESS if value >= 0 else ERROR


def card_value_style(color: Any) -> str:
    """The style sheet a metric card's value label carries."""
    return CARD_VALUE_STYLE_FORMAT.format(color=color)


def card(key: str, value: str, color: str = TEXT_HIGH) -> dict:
    """One metric card: its label, its shown value and its value colour."""
    return {
        "key": key,
        "label": CARD_LABELS[key],
        "value": value,
        "color": color,
        "class_name": CARD_CLASS_NAME,
        "accessible_name": CARD_ACCESSIBLE_NAME,
        "frame_style": CARD_FRAME_STYLE,
        "label_style": CARD_LABEL_STYLE,
        "value_style": card_value_style(color),
    }


def summary_value(summary: Any, field: str) -> Any:
    """One summary number, or the default the tab shows when it is absent."""
    return summary.get(field, SUMMARY_DEFAULTS[field])


def summary_cards(summary: Any) -> list[dict]:
    """The eight metric cards, in the order the header row holds them."""
    total_pnl = summary_value(summary, "total_pnl")
    return [
        card("pnl", pnl_text(total_pnl), pnl_color(total_pnl)),
        card("win_rate", percent_text(summary_value(summary, "win_rate"))),
        card("sharpe", ratio_text(summary_value(summary, "sharpe_ratio"))),
        card(
            "profit_factor",
            profit_factor_text(summary_value(summary, "profit_factor")),
        ),
        card("trades", count_text(summary_value(summary, "total_trades"))),
        card(
            "drawdown",
            percent_text(summary_value(summary, "max_drawdown")),
            WARNING,
        ),
        card("expectancy", pnl_text(summary_value(summary, "expectancy"))),
        card("trades_today", count_text(summary_value(summary, "trades_today"))),
    ]


def cell(text: Any, color: str = NO_COLOR) -> dict:
    """One table cell: its text, its centre alignment and its colour."""
    return {"text": text, "align": CELL_ALIGNMENT, "color": color}


def bot_values(performance: Any) -> dict:
    """The ten numbers one bot's row is built from, read by field name."""
    return {field: getattr(performance, field) for field in BOT_FIELDS}


def bot_row(values: Any) -> list[dict]:
    """One row of the bot table, ten cells wide.

    The P/L cell carries green at or above zero and red below. Every
    other cell carries no colour of its own.
    """
    total_pnl = values["total_pnl"]
    return [
        cell(bot_id_text(values["bot_id"])),
        cell(values["symbol"]),
        cell(count_text(values["total_trades"])),
        cell(percent_text(values["win_rate"])),
        cell(pnl_text(total_pnl), pnl_color(total_pnl)),
        cell(profit_factor_text(values["profit_factor"])),
        cell(ratio_text(values["sharpe_ratio"])),
        cell(percent_text(values["max_drawdown_pct"])),
        cell(duration_text(values["avg_hold_seconds"])),
        cell(pnl_text(values["expectancy"])),
    ]


def bot_rows(bots: Any) -> list[list[dict]]:
    """Every bot row, in the order the source handed the bots over."""
    return [bot_row(values) for values in bots]


def timeframe_row(name: Any, stats: Any) -> list[dict]:
    """One row of the timeframe table, four cells wide."""
    return [
        cell(name),
        cell(count_text(stats["total_trades"])),
        cell(percent_text(stats["win_rate"])),
        cell(pnl_text(stats["total_pnl"])),
    ]


def timeframe_rows(timeframes: Any) -> list[list[dict]]:
    """Every timeframe row, sorted by timeframe name."""
    return [timeframe_row(name, stats) for name, stats in sorted(timeframes.items())]


def empty_chart(width: int, height: int) -> dict:
    """The chart's waiting state: one flat ground and one centred line."""
    return {
        "empty": True,
        "width_px": width,
        "height_px": height,
        "background": SURFACE_CHART,
        "antialiased": False,
        "text": CHART_EMPTY_TEXT,
        "text_color": TEXT_PLACEHOLDER,
        "rect_px": [0, 0, width, height],
        "grid_lines_px": [],
        "grid_color": NO_COLOR,
        "grid_width_px": 0,
        "curve_px": [],
        "polygon_px": [],
        "segments_px": [],
        "gradient": {},
        "line_color": NO_COLOR,
        "line_width_px": 0,
        "labels": [],
        "rising": None,
        "min_equity": 0.0,
        "max_equity": 0.0,
    }


def chart_geometry(points: Any, width: int, height: int) -> dict:
    """Every line, corner and label the equity chart paints at one size.

    Fewer than two points gives the waiting state. Otherwise the curve
    is scaled into the panel inside a 40 pixel margin, filled with a
    green wash when the last equity is at or above the first and a red
    wash below, and labelled with the latest equity and the scaled
    floor.
    """
    if not points or len(points) < CHART_MIN_POINTS:
        return empty_chart(width, height)
    equities = [point["equity"] for point in points]
    times = [point["timestamp"] for point in points]
    min_equity = min(equities) * CHART_MIN_SCALE
    max_equity = max(equities) * CHART_MAX_SCALE
    equity_range = max_equity - min_equity or CHART_RANGE_FALLBACK
    time_range = times[-1] - times[0] or CHART_RANGE_FALLBACK
    margin = CHART_MARGIN_PX
    inner_height = height - 2 * margin
    inner_width = width - 2 * margin
    grid_lines = []
    for step in range(CHART_GRID_LINE_COUNT):
        line_y = margin + inner_height * step / CHART_GRID_DIVISOR
        grid_lines.append([margin, int(line_y), width - margin, int(line_y)])
    curve = []
    for point in points:
        x = margin + (point["timestamp"] - times[0]) / time_range * inner_width
        y = margin + (1 - (point["equity"] - min_equity) / equity_range) * inner_height
        curve.append([int(x), int(y)])
    rising = equities[-1] >= equities[0]
    stops = CHART_RISE_FILL if rising else CHART_FALL_FILL
    polygon = [list(corner) for corner in curve]
    polygon.append([curve[-1][0], height - margin])
    polygon.append([curve[0][0], height - margin])
    segments = [curve[at] + curve[at + 1] for at in range(len(curve) - 1)]
    return {
        "empty": False,
        "width_px": width,
        "height_px": height,
        "background": SURFACE_CHART,
        "antialiased": True,
        "text": "",
        "text_color": NO_COLOR,
        "rect_px": [0, 0, width, height],
        "grid_lines_px": grid_lines,
        "grid_color": SURFACE_CONTROL,
        "grid_width_px": CHART_GRID_WIDTH_PX,
        "curve_px": curve,
        "polygon_px": polygon,
        "segments_px": segments,
        "gradient": {
            "start_px": [0, margin],
            "end_px": [0, height - margin],
            "stops": [[0, list(stops[0])], [1, list(stops[1])]],
        },
        "line_color": SUCCESS if rising else ERROR,
        "line_width_px": CHART_LINE_WIDTH_PX,
        "labels": [
            {
                "text": money_text(equities[-1]),
                "color": TEXT_HIGH,
                "x_px": margin + CHART_TOP_LABEL_OFFSET_PX[0],
                "y_px": margin + CHART_TOP_LABEL_OFFSET_PX[1],
                "font_family": CHART_FONT_FAMILY,
                "font_point_size": CHART_FONT_POINT_SIZE,
            },
            {
                "text": money_text(min_equity),
                "color": TEXT_MUTED,
                "x_px": margin + CHART_BOTTOM_LABEL_OFFSET_PX[0],
                "y_px": height - margin + CHART_BOTTOM_LABEL_OFFSET_PX[1],
                "font_family": CHART_FONT_FAMILY,
                "font_point_size": CHART_FONT_POINT_SIZE,
            },
        ],
        "rising": rising,
        "min_equity": min_equity,
        "max_equity": max_equity,
    }


class AnalyticsTabModel:
    """Holds the analytics source the tab was built with, and what it shows."""

    def __init__(self, source: Any = None) -> None:
        self._source = source
        self._display: Optional[dict] = NO_REFRESH

    def refresh(self, source: Any = None) -> Optional[dict]:
        """Read the four number sets the tab shows and return them.

        A source given here wins over the one the tab was built with. A
        source that is missing or empty leaves the tab as it was and
        returns ``None``.
        """
        chosen = source or self._source
        if not chosen:
            return NO_REFRESH
        self._display = {
            "cards": summary_cards(chosen.get_portfolio_summary()),
            "curve": chosen.get_equity_curve(hours=EQUITY_CURVE_HOURS),
            "bot_rows": bot_rows(
                bot_values(one) for one in chosen.get_bot_performance()
            ),
            "timeframe_rows": timeframe_rows(chosen.get_timeframe_comparison()),
        }
        return self._display

    @property
    def display(self) -> Optional[dict]:
        return self._display


def build_view_model(
    summary: Any = None,
    curve: Any = None,
    bots: Any = None,
    timeframes: Any = None,
    width: int = 800,
    height: int = 300,
) -> dict:
    """Return every part of the analytics tab as one dict.

    Each of the four number sets defaults to empty, which is what the
    tab shows before any trade is recorded: eight cards on their zero
    values, a waiting chart and two empty tables.
    """
    return {
        "accessible_name": TAB_ACCESSIBLE_NAME,
        "page": dict(PAGE),
        "cards": summary_cards(summary if summary is not None else {}),
        "card_order": list(CARD_ORDER),
        "card_labels": dict(CARD_LABELS),
        "card_skin": dict(CARD_SKIN),
        "main_splitter": dict(MAIN_SPLITTER),
        "bottom_splitter": dict(BOTTOM_SPLITTER),
        "groups": {name: dict(group) for name, group in GROUPS.items()},
        "group_order": list(GROUP_ORDER),
        "bot_table": dict(BOT_TABLE),
        "timeframe_table": dict(TIMEFRAME_TABLE),
        "bot_columns": list(BOT_COLUMNS),
        "timeframe_columns": list(TIMEFRAME_COLUMNS),
        "bot_fields": list(BOT_FIELDS),
        "timeframe_fields": list(TIMEFRAME_FIELDS),
        "bot_rows": bot_rows(bots if bots is not None else NO_ROWS),
        "timeframe_rows": timeframe_rows(timeframes if timeframes is not None else {}),
        "chart": chart_geometry(curve if curve is not None else NO_ROWS, width, height),
        "chart_skin": dict(CHART_SKIN),
        "equity_curve_hours": EQUITY_CURVE_HOURS,
        "summary_defaults": dict(SUMMARY_DEFAULTS),
        "number_formats": dict(NUMBER_FORMATS),
        "colors": dict(COLORS),
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "skin": dict(SKIN),
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``analytics.tab``.

    Reads ``summary``, ``curve``, ``bots``, ``timeframes``, ``width``
    and ``height`` from the request parameters. Nothing is held between
    calls, so two calls with the same parameters answer the same.
    """
    return build_view_model(
        params.get("summary"),
        params.get("curve"),
        params.get("bots"),
        params.get("timeframes"),
        params.get("width", 800),
        params.get("height", 300),
    )
