"""risk_tab_surface.py -- the Risk and Capital Management tab, without Qt.

Describes the shelved risk dashboard: the circular drawdown gauge, the
four metric lines beside it, the two stacks of exposure bars, the risk
alerts table and the risk rules table. The tab holds 19 nodes in two
panes, and grows one exposure bar per asset and per exchange as the
manager reports them.

``DrawdownGaugeModel`` holds the gauge value and returns the arcs and
the two strings a repaint draws, in the order the shipped gauge draws
them. ``ExposureBarModel`` holds one bar's label, its asked-for share,
its printed amount and its chunk colour. ``RiskTabModel.setup_ui``
returns the widget tree in build order and ``RiskTabModel.refresh``
reads the risk manager and rebuilds every line, bar and table row.

``RiskAction``, ``RiskAlertRow``, ``PortfolioSnapshotRow`` and
``RiskManagerSnapshot`` are plain stand-ins for the risk manager and
its records, so the tab can be driven over the bridge from values
alone. Nothing here reads a saved file and nothing here reaches a
network.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``risk_tab.state`` method, which is how the Electron renderer
reaches it. Every value below is written out here rather than read from
``src.gui.risk_tab``, so a value changed on one side alone is reported.
Nothing here imports Qt.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .. import design_system as ds

METHOD = "risk_tab.state"

ACCESSIBLE_NAME = "Risk Tab"
GAUGE_ACCESSIBLE_NAME = "Drawdown Gauge"
BAR_ACCESSIBLE_NAME = "Exposure Bar"

CONTENT_MARGINS = (8, 8, 8, 8)
CONTENT_SPACING = 8
PANE_MARGINS = (0, 0, 0, 0)
BAR_MARGINS = (4, 2, 4, 2)

SPLITTER_ORIENTATION = "Horizontal"
SPLITTER_ORIENTATION_VALUE = 1
SPLITTER_HANDLE_WIDTH = 5
SPLITTER_CHILDREN_COLLAPSIBLE = False
SPLITTER_SIZES = (400, 500)

METRICS_STRETCH = 1
ALERTS_STRETCH = 2
RULES_STRETCH = 1
BAR_STRETCH = 1

GAUGE_MINIMUM_SIZE = (160, 160)
GAUGE_MAXIMUM_SIZE = (200, 200)
GAUGE_START_VALUE = 0.0
GAUGE_START_MAX_PCT = 25.0
GAUGE_SET_MAX_DEFAULT = 25
GAUGE_MARGIN = 15
GAUGE_PEN_WIDTH = 8

ANGLE_UNIT = 16
GAUGE_START_DEGREES = 225
GAUGE_SPAN_DEGREES = -270
GAUGE_START_ANGLE = GAUGE_START_DEGREES * ANGLE_UNIT
GAUGE_TRACK_SPAN = GAUGE_SPAN_DEGREES * ANGLE_UNIT

GAUGE_WARNING_RATIO = 0.4
GAUGE_DANGER_RATIO = 0.7
GAUGE_RATIO_CEILING = 1.0

GAUGE_TRACK_COLOR = ds.SURFACE_CONTROL
GAUGE_SAFE_COLOR = ds.SUCCESS
GAUGE_WARNING_COLOR = ds.WARNING
GAUGE_DANGER_COLOR = ds.ERROR
GAUGE_VALUE_COLOR = ds.TEXT_HIGH
GAUGE_LABEL_COLOR = ds.CARD_METRIC_LABEL

GAUGE_FONT_FAMILY = "Consolas"
GAUGE_VALUE_FONT_SIZE = 18
GAUGE_VALUE_FONT_WEIGHT = "Bold"
GAUGE_VALUE_FONT_WEIGHT_VALUE = 700
GAUGE_LABEL_FONT_SIZE = 9
GAUGE_LABEL_FONT_WEIGHT = "Normal"
GAUGE_LABEL_FONT_WEIGHT_VALUE = 400

GAUGE_VALUE_FORMAT = "{value:.1f}%"
GAUGE_LABEL_TEXT = "Drawdown"
GAUGE_LABEL_OFFSET = 10

GAUGE_VALUE_ALIGNMENT = "AlignCenter"
GAUGE_VALUE_ALIGNMENT_VALUE = 132
GAUGE_LABEL_ALIGNMENT = "AlignHCenter|AlignTop"
GAUGE_LABEL_ALIGNMENT_VALUE = 36
RENDER_HINT = "Antialiasing"

GAUGE_BAND_SAFE = "safe"
GAUGE_BAND_WARNING = "warning"
GAUGE_BAND_DANGER = "danger"
GAUGE_BANDS = (GAUGE_BAND_SAFE, GAUGE_BAND_WARNING, GAUGE_BAND_DANGER)
GAUGE_BAND_COLORS = {
    GAUGE_BAND_SAFE: GAUGE_SAFE_COLOR,
    GAUGE_BAND_WARNING: GAUGE_WARNING_COLOR,
    GAUGE_BAND_DANGER: GAUGE_DANGER_COLOR,
}

BAR_LABEL_MIN_WIDTH = 80
BAR_VALUE_MIN_WIDTH = 70
BAR_RANGE = (0, 100)
BAR_TEXT_VISIBLE = True
BAR_START_TEXT = "$0"
# The format a progress bar carries before the tab sets one.
BAR_START_FORMAT = "%p%"
BAR_VALUE_CEILING = 100
BAR_VALUE_ALIGNMENT = "AlignRight|AlignVCenter"
BAR_VALUE_ALIGNMENT_VALUE = 130
BAR_DEFAULT_COLOR = ds.STATUS_INFO
BAR_PERCENT_FORMAT = "{pct:.1f}%"
BAR_AMOUNT_FORMAT = "${amount:,.0f}"
BAR_NO_VALUE = None

BAR_LABEL_STYLE = f"color: {ds.TEXT_INACTIVE}; font-size: 11px;"
BAR_VALUE_STYLE = f"color: {ds.TEXT_HIGH}; font-size: 11px;"

PEAK_FORMAT = "Peak P/L: ${peak:,.4f}"
PEAK_START_TEXT = "Peak P/L: $0.00"
EXPOSURE_FORMAT = "Total Exposure: ${exposure:,.2f}"
EXPOSURE_START_TEXT = "Total Exposure: $0.00"
BOTS_FORMAT = "Running Bots: {count}"
BOTS_START_TEXT = "Running Bots: 0"

STATUS_MONITORING_TEXT = "STATUS: MONITORING"
STATUS_WARNING_TEXT = "STATUS: WARNING"
STATUS_CRITICAL_TEXT = "STATUS: CRITICAL"

PEAK_STYLE = f"color: {ds.SUCCESS}; font-size: 13px;"
EXPOSURE_STYLE = f"color: {ds.TEXT_HIGH}; font-size: 13px;"
BOTS_STYLE = f"color: {ds.TEXT_INACTIVE}; font-size: 12px;"
STATUS_STYLE_FORMAT = "color: {color}; font-size: 14px; font-weight: bold;"
STATUS_MONITORING_STYLE = STATUS_STYLE_FORMAT.format(color=ds.PRIMARY)
STATUS_WARNING_STYLE = STATUS_STYLE_FORMAT.format(color=ds.WARNING)
STATUS_CRITICAL_STYLE = STATUS_STYLE_FORMAT.format(color=ds.ERROR)

STATUS_STATE_MONITORING = "monitoring"
STATUS_STATE_WARNING = "warning"
STATUS_STATE_CRITICAL = "critical"
STATUS_STATES = (
    STATUS_STATE_MONITORING,
    STATUS_STATE_WARNING,
    STATUS_STATE_CRITICAL,
)
STATUS_LINES = {
    STATUS_STATE_MONITORING: (STATUS_MONITORING_TEXT, STATUS_MONITORING_STYLE),
    STATUS_STATE_WARNING: (STATUS_WARNING_TEXT, STATUS_WARNING_STYLE),
    STATUS_STATE_CRITICAL: (STATUS_CRITICAL_TEXT, STATUS_CRITICAL_STYLE),
}

ASSET_GROUP_TITLE = "Asset Exposure"
EXCHANGE_GROUP_TITLE = "Exchange Exposure"
ALERTS_GROUP_TITLE = "Risk Alerts"
RULES_GROUP_TITLE = "Risk Rules"

GROUP_BOX_STYLE = (
    f"QGroupBox {{ background: {ds.SURFACE_CHART}; "
    f"border: 1px solid {ds.CARD_METRIC_BORDER}; "
    f"border-radius: 6px; color: {ds.PRIMARY}; }}"
)

BAR_STYLE_FORMAT = (
    f"QProgressBar {{{{ background: {ds.SURFACE_CONTROL}; "
    f"border: 1px solid {ds.CARD_METRIC_BORDER}; "
    f"border-radius: 3px; height: 18px; color: {ds.TEXT_HIGH}; "
    "font-size: 10px; }}"
    "QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}"
)

ALERT_COLUMNS = ("Time", "Severity", "Rule", "Message", "Action")
RULE_COLUMNS = ("Rule", "Threshold", "Action", "Enabled")
ALERT_COLUMN_COUNT = 5
RULE_COLUMN_COUNT = 4

HEADER_RESIZE_MODE = "Stretch"
HEADER_RESIZE_VALUE = 1
ALTERNATING_ROW_COLORS = True
VERTICAL_HEADER_VISIBLE = False

EDIT_TRIGGERS_NONE: tuple = ()
EDIT_TRIGGERS_NONE_VALUE = 0
EDIT_TRIGGERS_DEFAULT = ("DoubleClicked", "EditKeyPressed", "AnyKeyPressed")
EDIT_TRIGGERS_DEFAULT_VALUE = 26

CELL_ALIGNMENT = "AlignCenter"
CELL_ALIGNMENT_VALUE = 132
NO_COLOR = ""
NO_ALIGNMENT = ""

STATUS_KEY_DRAWDOWN = "drawdown_pct"
STATUS_KEY_PEAK = "peak_pnl"
STATUS_KEY_EXPOSURE = "total_exposure"
STATUS_KEY_CRITICAL = "critical_alerts"
STATUS_KEY_ALERTS_HOUR = "alerts_1h"
STATUS_KEY_RULES = "rules"
STATUS_KEYS = (
    STATUS_KEY_DRAWDOWN,
    STATUS_KEY_PEAK,
    STATUS_KEY_EXPOSURE,
    STATUS_KEY_CRITICAL,
    STATUS_KEY_ALERTS_HOUR,
    STATUS_KEY_RULES,
)
STATUS_DEFAULT_NUMBER = 0

RULE_KEY_THRESHOLD = "threshold"
RULE_KEY_ACTION = "action"
RULE_KEY_ENABLED = "enabled"
RULE_KEYS = (RULE_KEY_THRESHOLD, RULE_KEY_ACTION, RULE_KEY_ENABLED)

ALERT_WINDOW_S = 86400
TIME_FORMAT = "%H:%M:%S"
MESSAGE_MAX_CHARS = 80

SEVERITY_CRITICAL = "critical"
SEVERITY_COLUMN = 1
SEVERITY_CRITICAL_COLOR = ds.ERROR
SEVERITY_OTHER_COLOR = ds.WARNING

ENABLED_COLUMN = 3
ENABLED_TEXT = "Yes"
DISABLED_TEXT = "No"
ENABLED_COLOR = ds.SUCCESS
DISABLED_COLOR = ds.ERROR
THRESHOLD_FORMAT = "{threshold:.1f}"
RULE_NAME_UNDERSCORE = "_"
RULE_NAME_SPACE = " "

ASSET_DANGER_PCT = 40
ASSET_WARNING_PCT = 25
EXCHANGE_DANGER_PCT = 60
EXCHANGE_WARNING_PCT = 40
FALLBACK_TOTAL = 1
PERCENT_SCALE = 100

BAR_BAND_INFO = "info"
BAR_BAND_WARNING = "warning"
BAR_BAND_DANGER = "danger"
BAR_BANDS = (BAR_BAND_INFO, BAR_BAND_WARNING, BAR_BAND_DANGER)
BAR_BAND_COLORS = {
    BAR_BAND_INFO: BAR_DEFAULT_COLOR,
    BAR_BAND_WARNING: ds.WARNING,
    BAR_BAND_DANGER: ds.ERROR,
}

REFRESH_PATH_NO_MANAGER = "no_manager"
REFRESH_PATH_PAINTED = "painted"
REFRESH_PATHS = (REFRESH_PATH_NO_MANAGER, REFRESH_PATH_PAINTED)
NO_PATH = ""

SETUP_START = "setup.start"
SETUP_RETURN = "setup.return"
GAUGE_SET = "gauge.set"
GAUGE_PAINT = "gauge.paint"
BAR_SET = "bar.set"
BAR_ADD = "bar.add"
REFRESH_START = "refresh.start"
REFRESH_STATUS = "refresh.status"
REFRESH_GAUGE = "refresh.gauge"
REFRESH_METRICS = "refresh.metrics"
REFRESH_STATE = "refresh.state"
REFRESH_SNAPSHOT = "refresh.snapshot"
REFRESH_ASSETS = "refresh.assets"
REFRESH_EXCHANGES = "refresh.exchanges"
REFRESH_ALERTS = "refresh.alerts"
REFRESH_RULES = "refresh.rules"
REFRESH_RETURN = "refresh.return"

ACTIONS: dict = {}
TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()
SKIN: dict = {}
TAB_STYLE_SHEET = ""

# The four metric labels are built in this order and added to the column
# in WIDGET order, which puts the status line first.
METRIC_BUILD_ORDER = ("peak_label", "exposure_label", "bots_label", "status_label")


def widget(name: str, kind: str, parent: str, **values: Any) -> dict:
    """One node of the tab's widget tree, with its parent and its values."""
    return {"name": name, "kind": kind, "parent": parent, **values}


WIDGETS = (
    widget(
        "tab",
        "QWidget",
        "",
        accessible_name=ACCESSIBLE_NAME,
        layout="QVBoxLayout",
        margins=CONTENT_MARGINS,
        spacing=CONTENT_SPACING,
        style_sheet=TAB_STYLE_SHEET,
    ),
    widget(
        "main_split",
        "QSplitter",
        "tab",
        orientation=SPLITTER_ORIENTATION,
        handle_width=SPLITTER_HANDLE_WIDTH,
        children_collapsible=SPLITTER_CHILDREN_COLLAPSIBLE,
        sizes=SPLITTER_SIZES,
    ),
    widget(
        "left",
        "QWidget",
        "main_split",
        layout="QVBoxLayout",
        margins=PANE_MARGINS,
    ),
    widget("gauge_row", "QHBoxLayout", "left"),
    widget(
        "dd_gauge",
        "DrawdownGauge",
        "gauge_row",
        accessible_name=GAUGE_ACCESSIBLE_NAME,
        minimum_size=GAUGE_MINIMUM_SIZE,
        maximum_size=GAUGE_MAXIMUM_SIZE,
    ),
    widget("metrics", "QVBoxLayout", "gauge_row", stretch=METRICS_STRETCH),
    widget(
        "status_label",
        "QLabel",
        "metrics",
        text=STATUS_MONITORING_TEXT,
        style_sheet=STATUS_MONITORING_STYLE,
    ),
    widget(
        "peak_label",
        "QLabel",
        "metrics",
        text=PEAK_START_TEXT,
        style_sheet=PEAK_STYLE,
    ),
    widget(
        "exposure_label",
        "QLabel",
        "metrics",
        text=EXPOSURE_START_TEXT,
        style_sheet=EXPOSURE_STYLE,
    ),
    widget(
        "bots_label",
        "QLabel",
        "metrics",
        text=BOTS_START_TEXT,
        style_sheet=BOTS_STYLE,
    ),
    widget("metrics_stretch", "stretch", "metrics"),
    widget(
        "asset_group",
        "QGroupBox",
        "left",
        title=ASSET_GROUP_TITLE,
        style_sheet=GROUP_BOX_STYLE,
        layout="QVBoxLayout",
    ),
    widget(
        "exchange_group",
        "QGroupBox",
        "left",
        title=EXCHANGE_GROUP_TITLE,
        style_sheet=GROUP_BOX_STYLE,
        layout="QVBoxLayout",
    ),
    widget("left_stretch", "stretch", "left"),
    widget(
        "right",
        "QWidget",
        "main_split",
        layout="QVBoxLayout",
        margins=PANE_MARGINS,
    ),
    widget(
        "alerts_group",
        "QGroupBox",
        "right",
        title=ALERTS_GROUP_TITLE,
        style_sheet=GROUP_BOX_STYLE,
        layout="QVBoxLayout",
        stretch=ALERTS_STRETCH,
    ),
    widget(
        "alerts_table",
        "QTableWidget",
        "alerts_group",
        columns=ALERT_COLUMNS,
        column_count=ALERT_COLUMN_COUNT,
        resize_mode=HEADER_RESIZE_MODE,
        alternating_row_colors=ALTERNATING_ROW_COLORS,
        vertical_header_visible=VERTICAL_HEADER_VISIBLE,
        edit_triggers=EDIT_TRIGGERS_NONE,
    ),
    widget(
        "rules_group",
        "QGroupBox",
        "right",
        title=RULES_GROUP_TITLE,
        style_sheet=GROUP_BOX_STYLE,
        layout="QVBoxLayout",
        stretch=RULES_STRETCH,
    ),
    widget(
        "rules_table",
        "QTableWidget",
        "rules_group",
        columns=RULE_COLUMNS,
        column_count=RULE_COLUMN_COUNT,
        resize_mode=HEADER_RESIZE_MODE,
        alternating_row_colors=ALTERNATING_ROW_COLORS,
        vertical_header_visible=VERTICAL_HEADER_VISIBLE,
        edit_triggers=EDIT_TRIGGERS_DEFAULT,
    ),
)

WIDGET_NAMES = tuple(node["name"] for node in WIDGETS)
WIDGET_KINDS = {node["name"]: node["kind"] for node in WIDGETS}
WIDGET_PARENTS = {node["name"]: node["parent"] for node in WIDGETS}
WIDGET_CHILDREN = {
    parent: tuple(node["name"] for node in WIDGETS if node["parent"] == parent)
    for parent in dict.fromkeys(node["parent"] for node in WIDGETS)
}
WIDGET_INDEX = {
    node["name"]: WIDGET_CHILDREN[node["parent"]].index(node["name"])
    for node in WIDGETS
}
TABLE_NAMES = tuple(node["name"] for node in WIDGETS if node["kind"] == "QTableWidget")
BUTTON_NAMES: tuple = ()


def bar_style(color: Any) -> str:
    """The progress bar's style sheet with one chunk colour written in."""
    return BAR_STYLE_FORMAT.format(color=color)


BAR_DEFAULT_STYLE = bar_style(BAR_DEFAULT_COLOR)


def gauge_ratio(value: Any, max_pct: Any) -> Any:
    """How far round the arc sweeps, never past a full sweep."""
    return min(value / max_pct, GAUGE_RATIO_CEILING)


def gauge_band(ratio: Any) -> str:
    """Which of the three colour bands one ratio falls in."""
    if ratio < GAUGE_WARNING_RATIO:
        return GAUGE_BAND_SAFE
    if ratio < GAUGE_DANGER_RATIO:
        return GAUGE_BAND_WARNING
    return GAUGE_BAND_DANGER


def gauge_color(ratio: Any) -> str:
    """The colour the value arc is drawn in for one ratio."""
    return GAUGE_BAND_COLORS[gauge_band(ratio)]


def gauge_span(ratio: Any) -> int:
    """The value arc's sweep, in the sixteenths of a degree Qt takes."""
    return int(GAUGE_SPAN_DEGREES * ratio * ANGLE_UNIT)


def arc(color: Any, box: list, start_angle: int, span_angle: Any) -> dict:
    """One arc of the gauge: its colour, its box and its two angles."""
    return {
        "kind": "arc",
        "color": color,
        "pen_width": GAUGE_PEN_WIDTH,
        "box": list(box),
        "start_angle": start_angle,
        "span_angle": span_angle,
    }


def painted_text(
    color: Any,
    box: list,
    text: Any,
    point_size: int,
    weight: str,
    weight_value: int,
    alignment: str,
    alignment_value: int,
) -> dict:
    """One string of the gauge: its colour, its box, its font and its text."""
    return {
        "kind": "text",
        "color": color,
        "box": list(box),
        "text": text,
        "family": GAUGE_FONT_FAMILY,
        "point_size": point_size,
        "weight": weight,
        "weight_value": weight_value,
        "alignment": alignment,
        "alignment_value": alignment_value,
    }


def exposure_pct(amount: Any, total: Any) -> Any:
    """One holding's share of the whole book, as a percentage."""
    return amount / total * PERCENT_SCALE


def exposure_total(reported: Any) -> Any:
    """The divisor the bars use; a reported nothing becomes one."""
    return reported or FALLBACK_TOTAL


def band_for(pct: Any, danger_pct: Any, warning_pct: Any) -> str:
    """Which colour band one share falls in, for either threshold pair."""
    if pct > danger_pct:
        return BAR_BAND_DANGER
    if pct > warning_pct:
        return BAR_BAND_WARNING
    return BAR_BAND_INFO


def asset_color(pct: Any) -> str:
    """The chunk colour one asset's share is drawn in."""
    return BAR_BAND_COLORS[band_for(pct, ASSET_DANGER_PCT, ASSET_WARNING_PCT)]


def exchange_color(pct: Any) -> str:
    """The chunk colour one exchange's share is drawn in."""
    return BAR_BAND_COLORS[band_for(pct, EXCHANGE_DANGER_PCT, EXCHANGE_WARNING_PCT)]


def status_state(critical: Any, alerts_hour: Any) -> str:
    """Which of the three states the header line reports."""
    if critical > STATUS_DEFAULT_NUMBER:
        return STATUS_STATE_CRITICAL
    if alerts_hour > STATUS_DEFAULT_NUMBER:
        return STATUS_STATE_WARNING
    return STATUS_STATE_MONITORING


def rule_title(name: Any) -> str:
    """One rule's name as the first column of the rules table prints it."""
    return name.replace(RULE_NAME_UNDERSCORE, RULE_NAME_SPACE).title()


def severity_color(severity: Any) -> str:
    """The colour one alert's severity word is drawn in."""
    return (
        SEVERITY_CRITICAL_COLOR
        if severity == SEVERITY_CRITICAL
        else SEVERITY_OTHER_COLOR
    )


def enabled_text(enabled: Any) -> str:
    """Whether one rule is on, as the last column prints it."""
    return ENABLED_TEXT if enabled else DISABLED_TEXT


def enabled_color(enabled: Any) -> str:
    """The colour the on-or-off answer is drawn in."""
    return ENABLED_COLOR if enabled else DISABLED_COLOR


def clock_text(timestamp: Any) -> str:
    """One alert's local time of day, as the first column prints it."""
    return time.strftime(TIME_FORMAT, time.localtime(timestamp))


def within_window(timestamp: Any, now: Any) -> bool:
    """Whether one alert is recent enough for the table to show it."""
    return now - timestamp < ALERT_WINDOW_S


def cell(text: Any, color: str) -> dict:
    """One table cell: its text, its colour and its alignment."""
    return {"text": text, "color": color, "alignment": CELL_ALIGNMENT}


def blank_row(width: int) -> list:
    """One row that exists with no cell written into it yet.

    Both tables are given their row count before any cell is built, so a
    row a refusal never reaches stays empty rather than absent.
    """
    return [
        {"text": None, "color": NO_COLOR, "alignment": NO_ALIGNMENT}
        for _ in range(width)
    ]


def resize_rows(rows: list, count: int, width: int) -> list:
    """`rows` grown or cut to `count`, keeping the rows that stay.

    A table given a smaller row count keeps the cells of the rows
    that remain, so a rewrite that stops part way leaves the rows it
    already wrote rather than an empty table.
    """
    kept = list(rows[:count])
    while len(kept) < count:
        kept.append(blank_row(width))
    return kept


def exchange_label(name: Any) -> Any:
    """One exchange name as its bar's label prints it."""
    return name.capitalize()


class RiskAction:
    """One rule's action, carrying the word the Action cell prints."""

    def __init__(self, value: Any) -> None:
        self.value = value


class RiskAlertRow:
    """One risk alert: when it fired, what tripped, and what was done."""

    def __init__(
        self,
        timestamp: Any = 0.0,
        severity: Any = "warning",
        rule_name: Any = "",
        message: Any = "",
        action_taken: Any = "warn",
    ) -> None:
        self.timestamp = timestamp
        self.severity = severity
        self.rule_name = rule_name
        self.message = message
        self.action_taken = (
            action_taken if hasattr(action_taken, "value") else RiskAction(action_taken)
        )


class PortfolioSnapshotRow:
    """One moment: how much is deployed, where, and by how many bots."""

    def __init__(
        self,
        running_count: Any = 0,
        total_exposure: Any = 0.0,
        asset_exposures: Any = None,
        exchange_exposures: Any = None,
    ) -> None:
        self.running_count = running_count
        self.total_exposure = total_exposure
        self.asset_exposures = {} if asset_exposures is None else dict(asset_exposures)
        self.exchange_exposures = (
            {} if exchange_exposures is None else dict(exchange_exposures)
        )


class RiskManagerSnapshot:
    """A risk manager built from plain values.

    Carries the three reads the tab makes -- the status summary, the
    snapshots and the alerts -- so a caller over the bridge can drive
    the tab with no manager wired.
    """

    def __init__(
        self,
        status: Optional[dict] = None,
        snapshots: Any = (),
        alerts: Any = (),
    ) -> None:
        self._status = {} if status is None else status
        self._snapshots = list(snapshots)
        self._alerts = list(alerts)

    def get_status(self) -> dict:
        return self._status

    @property
    def snapshots(self) -> list:
        return list(self._snapshots)

    @property
    def alerts(self) -> list:
        return list(self._alerts)


class DrawdownGaugeModel:
    """The circular drawdown gauge, with no Qt object behind it.

    ``set_value`` takes the percentage and its ceiling. ``paint``
    returns the arcs and the two strings a repaint draws, in the order
    the shipped gauge draws them, and leaves the steps it reached in
    ``painted`` when a value it cannot draw stops it part way.
    """

    def __init__(self) -> None:
        self.accessible_name = GAUGE_ACCESSIBLE_NAME
        self.value: Any = GAUGE_START_VALUE
        self.max_pct: Any = GAUGE_START_MAX_PCT
        self.minimum_size = GAUGE_MINIMUM_SIZE
        self.maximum_size = GAUGE_MAXIMUM_SIZE
        self.updates = 0
        self.painted: list = []
        self.calls: list = []

    def set_value(self, pct: Any, max_pct: Any = GAUGE_SET_MAX_DEFAULT) -> None:
        """Take a new drawdown reading and ask for a repaint."""
        self.value = pct
        self.max_pct = max_pct
        self.updates += 1
        self.calls.append([GAUGE_SET, pct, max_pct])

    def paint(self, width: int, height: int) -> dict:
        """The arcs and the strings one repaint draws, at this size."""
        self.painted = []
        self.calls.append([GAUGE_PAINT, width, height])
        size = min(width, height)
        rect_size = size - 2 * GAUGE_MARGIN
        box = [GAUGE_MARGIN, GAUGE_MARGIN, rect_size, rect_size]
        self.painted.append(
            arc(GAUGE_TRACK_COLOR, box, GAUGE_START_ANGLE, GAUGE_TRACK_SPAN)
        )
        ratio = gauge_ratio(self.value, self.max_pct)
        band = gauge_band(ratio)
        self.painted.append(
            arc(GAUGE_BAND_COLORS[band], box, GAUGE_START_ANGLE, gauge_span(ratio))
        )
        self.painted.append(
            painted_text(
                GAUGE_VALUE_COLOR,
                [0, 0, width, height],
                GAUGE_VALUE_FORMAT.format(value=self.value),
                GAUGE_VALUE_FONT_SIZE,
                GAUGE_VALUE_FONT_WEIGHT,
                GAUGE_VALUE_FONT_WEIGHT_VALUE,
                GAUGE_VALUE_ALIGNMENT,
                GAUGE_VALUE_ALIGNMENT_VALUE,
            )
        )
        label_top = size // 2 + GAUGE_LABEL_OFFSET
        self.painted.append(
            painted_text(
                GAUGE_LABEL_COLOR,
                [0, label_top, width, height - label_top],
                GAUGE_LABEL_TEXT,
                GAUGE_LABEL_FONT_SIZE,
                GAUGE_LABEL_FONT_WEIGHT,
                GAUGE_LABEL_FONT_WEIGHT_VALUE,
                GAUGE_LABEL_ALIGNMENT,
                GAUGE_LABEL_ALIGNMENT_VALUE,
            )
        )
        return {
            "render_hint": RENDER_HINT,
            "size": size,
            "margin": GAUGE_MARGIN,
            "rect_size": rect_size,
            "ratio": ratio,
            "band": band,
            "steps": [dict(step) for step in self.painted],
        }


class ExposureBarModel:
    """One exposure bar: its label, its share, its amount and its colour.

    ``asked_value`` is the whole number the bar is GIVEN. A progress bar
    keeps a value outside its range instead of taking it, so the asked
    value and the value the bar holds are two different things.
    """

    def __init__(self, label: Any) -> None:
        self.accessible_name = BAR_ACCESSIBLE_NAME
        self.label = label
        self.label_style = BAR_LABEL_STYLE
        self.label_min_width = BAR_LABEL_MIN_WIDTH
        self.range = BAR_RANGE
        self.text_visible = BAR_TEXT_VISIBLE
        self.margins = BAR_MARGINS
        self.asked_value: Any = BAR_NO_VALUE
        self.format_text: Any = BAR_START_FORMAT
        self.value_text: Any = BAR_START_TEXT
        self.value_style = BAR_VALUE_STYLE
        self.value_min_width = BAR_VALUE_MIN_WIDTH
        self.value_alignment = BAR_VALUE_ALIGNMENT
        self.bar_style = BAR_DEFAULT_STYLE

    def set_value(self, pct: Any, amount: Any, color: Any = BAR_DEFAULT_COLOR) -> None:
        """Take one share and one amount, in the order the bar takes them."""
        self.asked_value = int(min(pct, BAR_VALUE_CEILING))
        self.format_text = BAR_PERCENT_FORMAT.format(pct=pct)
        self.value_text = BAR_AMOUNT_FORMAT.format(amount=amount)
        self.bar_style = bar_style(color)

    def state(self) -> dict:
        """This bar's whole visible state as one dict."""
        return {
            "label": self.label,
            "label_style": self.label_style,
            "asked_value": self.asked_value,
            "format_text": self.format_text,
            "value_text": self.value_text,
            "value_style": self.value_style,
            "bar_style": self.bar_style,
        }


class RiskTabModel:
    """The Risk and Capital Management tab: its widgets, state and paths.

    ``setup_ui`` returns the widget tree in build order. ``refresh``
    reads the risk manager and rebuilds the gauge, the four metric
    lines, both stacks of exposure bars and both tables. Every step is
    appended to ``calls`` in the order the shipped tab makes it.
    """

    def __init__(self, risk_manager: Any = None) -> None:
        self.manager = risk_manager
        self.accessible_name = ACCESSIBLE_NAME
        self.gauge = DrawdownGaugeModel()
        self.status_text: Any = STATUS_MONITORING_TEXT
        self.status_style = STATUS_MONITORING_STYLE
        self.status_state = STATUS_STATE_MONITORING
        self.peak_text: Any = PEAK_START_TEXT
        self.peak_style = PEAK_STYLE
        self.exposure_text: Any = EXPOSURE_START_TEXT
        self.exposure_style = EXPOSURE_STYLE
        self.bots_text: Any = BOTS_START_TEXT
        self.bots_style = BOTS_STYLE
        self.asset_bars: dict = {}
        self.exchange_bars: dict = {}
        self.alert_rows: list = []
        self.rule_rows: list = []
        self.refresh_path = NO_PATH
        self.calls: list = []

    def setup_ui(self) -> list:
        """The tab's widget tree, in the order the tab builds it."""
        self.calls.append([SETUP_START])
        built = [dict(node) for node in WIDGETS]
        self.calls.append([SETUP_RETURN, len(built)])
        return built

    def refresh(self, risk_manager: Any = None) -> dict:
        """Read the manager and rebuild every line, bar and table row."""
        manager = risk_manager or self.manager
        self.calls.append([REFRESH_START, manager is not None])
        if not manager:
            return self._finish(REFRESH_PATH_NO_MANAGER)
        status = manager.get_status()
        self.calls.append([REFRESH_STATUS, len(status)])
        drawdown = status.get(STATUS_KEY_DRAWDOWN, STATUS_DEFAULT_NUMBER)
        self.gauge.set_value(drawdown)
        self.calls.append([REFRESH_GAUGE, drawdown])
        self.peak_text = PEAK_FORMAT.format(
            peak=status.get(STATUS_KEY_PEAK, STATUS_DEFAULT_NUMBER)
        )
        self.exposure_text = EXPOSURE_FORMAT.format(
            exposure=status.get(STATUS_KEY_EXPOSURE, STATUS_DEFAULT_NUMBER)
        )
        self.calls.append([REFRESH_METRICS, self.peak_text, self.exposure_text])
        self.status_state = status_state(
            status.get(STATUS_KEY_CRITICAL, STATUS_DEFAULT_NUMBER),
            status.get(STATUS_KEY_ALERTS_HOUR, STATUS_DEFAULT_NUMBER),
        )
        self.status_text, self.status_style = STATUS_LINES[self.status_state]
        self.calls.append([REFRESH_STATE, self.status_state])
        snapshots = manager.snapshots
        if snapshots:
            latest = snapshots[-1]
            self.bots_text = BOTS_FORMAT.format(count=latest.running_count)
            total = exposure_total(latest.total_exposure)
            self.calls.append([REFRESH_SNAPSHOT, self.bots_text, total])
            self._fill_bars(
                self.asset_bars, latest.asset_exposures, total, asset_color, str
            )
            self.calls.append([REFRESH_ASSETS, len(self.asset_bars)])
            self._fill_bars(
                self.exchange_bars,
                latest.exchange_exposures,
                total,
                exchange_color,
                exchange_label,
            )
            self.calls.append([REFRESH_EXCHANGES, len(self.exchange_bars)])
        alerts = manager.alerts
        now = time.time()
        recent = [row for row in alerts if within_window(row.timestamp, now)]
        self.alert_rows = resize_rows(self.alert_rows, len(recent), ALERT_COLUMN_COUNT)
        for index, alert in enumerate(reversed(recent)):
            self.alert_rows[index] = self._alert_row(alert)
        self.calls.append([REFRESH_ALERTS, len(self.alert_rows)])
        rules = status.get(STATUS_KEY_RULES, {})
        self.rule_rows = resize_rows(self.rule_rows, len(rules), RULE_COLUMN_COUNT)
        for index, (name, rule) in enumerate(rules.items()):
            self.rule_rows[index] = self._rule_row(name, rule)
        self.calls.append([REFRESH_RULES, len(self.rule_rows)])
        return self._finish(REFRESH_PATH_PAINTED)

    def _fill_bars(
        self, bars: dict, exposures: Any, total: Any, colour_for: Any, label_for: Any
    ) -> None:
        """Add a bar for every holding not seen before, then set them all."""
        for key, amount in exposures.items():
            pct = exposure_pct(amount, total)
            if key not in bars:
                bars[key] = ExposureBarModel(label_for(key))
                self.calls.append([BAR_ADD, key])
            bars[key].set_value(pct, amount, colour_for(pct))
            self.calls.append([BAR_SET, key, pct])

    def _alert_row(self, alert: Any) -> list:
        """One Risk Alerts row: its five cells and their colours."""
        texts = [
            clock_text(alert.timestamp),
            alert.severity.upper(),
            alert.rule_name,
            alert.message[:MESSAGE_MAX_CHARS],
            alert.action_taken.value,
        ]
        row = []
        for column, text in enumerate(texts):
            color = NO_COLOR
            if column == SEVERITY_COLUMN:
                color = severity_color(alert.severity)
            row.append(cell(text, color))
        return row

    def _rule_row(self, name: Any, rule: Any) -> list:
        """One Risk Rules row: its four cells and their colours."""
        enabled = rule[RULE_KEY_ENABLED]
        texts = [
            rule_title(name),
            THRESHOLD_FORMAT.format(threshold=rule[RULE_KEY_THRESHOLD]),
            rule[RULE_KEY_ACTION],
            enabled_text(enabled),
        ]
        row = []
        for column, text in enumerate(texts):
            color = NO_COLOR
            if column == ENABLED_COLUMN:
                color = enabled_color(enabled)
            row.append(cell(text, color))
        return row

    def _finish(self, path: str) -> dict:
        """Keep the refresh path and report the lines, bars and rows."""
        self.refresh_path = path
        answer = {
            "path": path,
            "status_text": self.status_text,
            "peak_text": self.peak_text,
            "exposure_text": self.exposure_text,
            "bots_text": self.bots_text,
            "asset_bars": [bar.state() for bar in self.asset_bars.values()],
            "exchange_bars": [bar.state() for bar in self.exchange_bars.values()],
            "alert_rows": [list(row) for row in self.alert_rows],
            "rule_rows": [list(row) for row in self.rule_rows],
        }
        self.calls.append(
            [REFRESH_RETURN, path, len(self.alert_rows), len(self.rule_rows)]
        )
        return answer


TAB_MODEL = RiskTabModel()


def build_manager(spec: Optional[dict]) -> Optional[RiskManagerSnapshot]:
    """One risk manager built from a request's plain values, or None."""
    if spec is None:
        return None
    return RiskManagerSnapshot(
        status=spec.get("status"),
        snapshots=[
            PortfolioSnapshotRow(
                running_count=row.get("running_count", 0),
                total_exposure=row.get("total_exposure", 0.0),
                asset_exposures=row.get("asset_exposures"),
                exchange_exposures=row.get("exchange_exposures"),
            )
            for row in spec.get("snapshots", ())
        ],
        alerts=[
            RiskAlertRow(
                timestamp=row.get("timestamp", 0.0),
                severity=row.get("severity", "warning"),
                rule_name=row.get("rule_name", ""),
                message=row.get("message", ""),
                action_taken=row.get("action_taken", "warn"),
            )
            for row in spec.get("alerts", ())
        ],
    )


def build_view_model(
    model: RiskTabModel, action: str = "", gauge_size: Any = None
) -> dict:
    """Return the whole tab state as one serialisable dict."""
    if action == "refresh":
        model.refresh()
    width, height = GAUGE_MINIMUM_SIZE if gauge_size is None else gauge_size
    return {
        "method": METHOD,
        "accessible_name": model.accessible_name,
        "widgets": [dict(node) for node in WIDGETS],
        "widget_names": list(WIDGET_NAMES),
        "widget_kinds": dict(WIDGET_KINDS),
        "widget_parents": dict(WIDGET_PARENTS),
        "widget_children": {
            parent: list(names) for parent, names in WIDGET_CHILDREN.items()
        },
        "widget_index": dict(WIDGET_INDEX),
        "table_names": list(TABLE_NAMES),
        "button_names": list(BUTTON_NAMES),
        "metric_build_order": list(METRIC_BUILD_ORDER),
        "content_margins": list(CONTENT_MARGINS),
        "content_spacing": CONTENT_SPACING,
        "pane_margins": list(PANE_MARGINS),
        "bar_margins": list(BAR_MARGINS),
        "splitter_orientation": SPLITTER_ORIENTATION,
        "splitter_orientation_value": SPLITTER_ORIENTATION_VALUE,
        "splitter_handle_width": SPLITTER_HANDLE_WIDTH,
        "splitter_children_collapsible": SPLITTER_CHILDREN_COLLAPSIBLE,
        "splitter_sizes": list(SPLITTER_SIZES),
        "stretches": {
            "metrics": METRICS_STRETCH,
            "alerts": ALERTS_STRETCH,
            "rules": RULES_STRETCH,
            "bar": BAR_STRETCH,
        },
        "group_titles": [
            ASSET_GROUP_TITLE,
            EXCHANGE_GROUP_TITLE,
            ALERTS_GROUP_TITLE,
            RULES_GROUP_TITLE,
        ],
        "alert_columns": list(ALERT_COLUMNS),
        "rule_columns": list(RULE_COLUMNS),
        "alert_column_count": ALERT_COLUMN_COUNT,
        "rule_column_count": RULE_COLUMN_COUNT,
        "header_resize_mode": HEADER_RESIZE_MODE,
        "header_resize_value": HEADER_RESIZE_VALUE,
        "alternating_row_colors": ALTERNATING_ROW_COLORS,
        "vertical_header_visible": VERTICAL_HEADER_VISIBLE,
        "edit_triggers_none": list(EDIT_TRIGGERS_NONE),
        "edit_triggers_none_value": EDIT_TRIGGERS_NONE_VALUE,
        "edit_triggers_default": list(EDIT_TRIGGERS_DEFAULT),
        "edit_triggers_default_value": EDIT_TRIGGERS_DEFAULT_VALUE,
        "cell_alignment": CELL_ALIGNMENT,
        "cell_alignment_value": CELL_ALIGNMENT_VALUE,
        "no_color": NO_COLOR,
        "no_alignment": NO_ALIGNMENT,
        "gauge": {
            "accessible_name": GAUGE_ACCESSIBLE_NAME,
            "minimum_size": list(GAUGE_MINIMUM_SIZE),
            "maximum_size": list(GAUGE_MAXIMUM_SIZE),
            "start_value": GAUGE_START_VALUE,
            "start_max_pct": GAUGE_START_MAX_PCT,
            "set_max_default": GAUGE_SET_MAX_DEFAULT,
            "margin": GAUGE_MARGIN,
            "pen_width": GAUGE_PEN_WIDTH,
            "angle_unit": ANGLE_UNIT,
            "start_degrees": GAUGE_START_DEGREES,
            "span_degrees": GAUGE_SPAN_DEGREES,
            "start_angle": GAUGE_START_ANGLE,
            "track_span": GAUGE_TRACK_SPAN,
            "warning_ratio": GAUGE_WARNING_RATIO,
            "danger_ratio": GAUGE_DANGER_RATIO,
            "ratio_ceiling": GAUGE_RATIO_CEILING,
            "track_color": GAUGE_TRACK_COLOR,
            "value_color": GAUGE_VALUE_COLOR,
            "label_color": GAUGE_LABEL_COLOR,
            "bands": list(GAUGE_BANDS),
            "band_colors": dict(GAUGE_BAND_COLORS),
            "font_family": GAUGE_FONT_FAMILY,
            "value_font_size": GAUGE_VALUE_FONT_SIZE,
            "value_font_weight": GAUGE_VALUE_FONT_WEIGHT,
            "value_font_weight_value": GAUGE_VALUE_FONT_WEIGHT_VALUE,
            "label_font_size": GAUGE_LABEL_FONT_SIZE,
            "label_font_weight": GAUGE_LABEL_FONT_WEIGHT,
            "label_font_weight_value": GAUGE_LABEL_FONT_WEIGHT_VALUE,
            "value_format": GAUGE_VALUE_FORMAT,
            "label_text": GAUGE_LABEL_TEXT,
            "label_offset": GAUGE_LABEL_OFFSET,
            "value_alignment": GAUGE_VALUE_ALIGNMENT,
            "value_alignment_value": GAUGE_VALUE_ALIGNMENT_VALUE,
            "label_alignment": GAUGE_LABEL_ALIGNMENT,
            "label_alignment_value": GAUGE_LABEL_ALIGNMENT_VALUE,
            "render_hint": RENDER_HINT,
            "value": model.gauge.value,
            "max_pct": model.gauge.max_pct,
            "updates": model.gauge.updates,
        },
        "bar": {
            "accessible_name": BAR_ACCESSIBLE_NAME,
            "label_min_width": BAR_LABEL_MIN_WIDTH,
            "value_min_width": BAR_VALUE_MIN_WIDTH,
            "range": list(BAR_RANGE),
            "text_visible": BAR_TEXT_VISIBLE,
            "start_text": BAR_START_TEXT,
            "start_format": BAR_START_FORMAT,
            "value_ceiling": BAR_VALUE_CEILING,
            "value_alignment": BAR_VALUE_ALIGNMENT,
            "value_alignment_value": BAR_VALUE_ALIGNMENT_VALUE,
            "default_color": BAR_DEFAULT_COLOR,
            "percent_format": BAR_PERCENT_FORMAT,
            "amount_format": BAR_AMOUNT_FORMAT,
            "no_value": BAR_NO_VALUE,
            "label_style": BAR_LABEL_STYLE,
            "value_style": BAR_VALUE_STYLE,
            "style_format": BAR_STYLE_FORMAT,
            "default_style": BAR_DEFAULT_STYLE,
            "bands": list(BAR_BANDS),
            "band_colors": dict(BAR_BAND_COLORS),
            "asset_danger_pct": ASSET_DANGER_PCT,
            "asset_warning_pct": ASSET_WARNING_PCT,
            "exchange_danger_pct": EXCHANGE_DANGER_PCT,
            "exchange_warning_pct": EXCHANGE_WARNING_PCT,
            "fallback_total": FALLBACK_TOTAL,
            "percent_scale": PERCENT_SCALE,
        },
        "styles": {
            "group_box": GROUP_BOX_STYLE,
            "peak": PEAK_STYLE,
            "exposure": EXPOSURE_STYLE,
            "bots": BOTS_STYLE,
            "status_format": STATUS_STYLE_FORMAT,
            "status_monitoring": STATUS_MONITORING_STYLE,
            "status_warning": STATUS_WARNING_STYLE,
            "status_critical": STATUS_CRITICAL_STYLE,
        },
        "texts": {
            "peak_format": PEAK_FORMAT,
            "peak_start": PEAK_START_TEXT,
            "exposure_format": EXPOSURE_FORMAT,
            "exposure_start": EXPOSURE_START_TEXT,
            "bots_format": BOTS_FORMAT,
            "bots_start": BOTS_START_TEXT,
            "status_monitoring": STATUS_MONITORING_TEXT,
            "status_warning": STATUS_WARNING_TEXT,
            "status_critical": STATUS_CRITICAL_TEXT,
            "enabled": ENABLED_TEXT,
            "disabled": DISABLED_TEXT,
            "threshold_format": THRESHOLD_FORMAT,
            "time_format": TIME_FORMAT,
            "rule_name_underscore": RULE_NAME_UNDERSCORE,
            "rule_name_space": RULE_NAME_SPACE,
        },
        "status_states": list(STATUS_STATES),
        "status_lines": {name: list(pair) for name, pair in STATUS_LINES.items()},
        "status_keys": list(STATUS_KEYS),
        "status_default_number": STATUS_DEFAULT_NUMBER,
        "rule_keys": list(RULE_KEYS),
        "alert_window_s": ALERT_WINDOW_S,
        "message_max_chars": MESSAGE_MAX_CHARS,
        "severity_critical": SEVERITY_CRITICAL,
        "severity_column": SEVERITY_COLUMN,
        "severity_critical_color": SEVERITY_CRITICAL_COLOR,
        "severity_other_color": SEVERITY_OTHER_COLOR,
        "enabled_column": ENABLED_COLUMN,
        "enabled_color": ENABLED_COLOR,
        "disabled_color": DISABLED_COLOR,
        "refresh_paths": list(REFRESH_PATHS),
        "no_path": NO_PATH,
        "actions": dict(ACTIONS),
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "skin": dict(SKIN),
        "tab_style_sheet": TAB_STYLE_SHEET,
        "status_text": model.status_text,
        "status_style": model.status_style,
        "status_state": model.status_state,
        "peak_text": model.peak_text,
        "peak_style": model.peak_style,
        "exposure_text": model.exposure_text,
        "exposure_style": model.exposure_style,
        "bots_text": model.bots_text,
        "bots_style": model.bots_style,
        "asset_bars": [bar.state() for bar in model.asset_bars.values()],
        "exchange_bars": [bar.state() for bar in model.exchange_bars.values()],
        "alert_rows": [list(row) for row in model.alert_rows],
        "rule_rows": [list(row) for row in model.rule_rows],
        "gauge_paint": model.gauge.paint(width, height),
        "refresh_path": model.refresh_path,
        "has_manager": model.manager is not None,
        "calls": [list(call) for call in model.calls],
    }


def view_model(params: dict) -> dict:
    """Bridge handler for ``risk_tab.state``.

    Reads ``reset``, ``manager``, ``action`` and ``gauge_size`` from the
    request parameters. The tab keeps the bars it has grown between
    calls, so the model persists; ``reset`` is what a fresh open sends.
    """
    global TAB_MODEL
    if params.get("reset", False):
        TAB_MODEL = RiskTabModel(build_manager(params.get("manager")))
    elif "manager" in params:
        TAB_MODEL.manager = build_manager(params.get("manager"))
    return build_view_model(
        TAB_MODEL, params.get("action", ""), params.get("gauge_size")
    )
