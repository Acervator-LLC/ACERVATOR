"""The shipped Risk and Capital Management tab and the Qt-free surface, side by side.

A failure means the view model carries a different metric line, a
different gauge arc, a different exposure bar, a different table row, a
different colour, a different widget tree, a different recorded call or
a different refusal than ``RiskTab``.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from src.gui import risk_tab as shipped
from src.gui.main_tabs import risk_tab_surface as surface
from tests.fixtures.host_fonts import (
    NARROW_LABEL,
    WIDE_LABEL,
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_pictures_differ,
    assert_pictures_match,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

TAB_PATH = REPO_ROOT / "src/gui/risk_tab.py"
SURFACE_PATH = REPO_ROOT / "src/gui/main_tabs/risk_tab_surface.py"

# Every control file is named with its full path. Two files in this tree
# share the basename ``history_tab.py`` and build different numbers of
# timers, so a bare name would name neither.
WIRING_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/privacy_dot.py"
SIGNAL_CONTROL_PATH = REPO_ROOT / "src/gui/launcher.py"
TIMER_CONTROL_PATH = REPO_ROOT / "src/gui/history_tab.py"
TIMER_QUIET_PATH = REPO_ROOT / "src/gui/main_tabs/history_tab.py"
BUS_CONTROL_PATH = REPO_ROOT / "src/gui/bot_visualizer.py"
ELEMENT_CONTROL_PATH = REPO_ROOT / "src/gui/widgets/dashboard_stat_card.py"
NESTED_CLASS_PATH = REPO_ROOT / "src/gui/stock_main_window.py"
DESCRIPTOR_CONTROL_PATH = REPO_ROOT / "src/gui/indicator_panel.py"

PIXEL_SIZE = (900, 620)
GAUGE_PIXEL_SIZE = (160, 160)

# The design-system colours these lines and cells use, typed out here
# rather than read from the surface, so a renamed or re-valued token
# cannot move both sides together.
SUCCESS_HEX = "#00ff88"
ERROR_HEX = "#ff3366"
WARNING_HEX = "#ffaa00"
PRIMARY_HEX = "#00ffcc"
INFO_HEX = "#00aaff"
LABEL_HEX = "#888"
INACTIVE_HEX = "#aaaaaa"
TEXT_HIGH_HEX = "#e0e0f0"
CHART_HEX = "#0a0a12"
CONTROL_HEX = "#1a1a2e"
CARD_BORDER_HEX = "#2a2a3f"

# The counts the shipped tab carries, measured off the file.
TAB_CONNECT_SITES = 0
TAB_TIMER_SITES = 0
TAB_BUS_SITES = 0
TAB_ELEMENTS_BUILT = 21
TAB_CLASS_COUNT = 3

# The same counters pointed at files that really carry one.
WIRING_CONTROL_SITES = 1
SIGNAL_CONTROL_SITES = 3
TIMER_CONTROL_SITES = 1
TIMER_QUIET_SITES = 0
BUS_CONTROL_SITES = 2
ELEMENT_CONTROL_BUILT = 3
NESTED_CLASS_COUNT = 4

# Alert stamps are taken from one reading of the clock, so every case
# sees the same values whatever order the run puts them in.
NOW = time.time()
RECENT_STAMP = NOW - 60
OLDER_STAMP = NOW - 3600
STALE_STAMP = NOW - 90_000
BILLION_STAMP = 1_000_000_000.0

UNICODE_NAME = "Δ_flip→⚡"
MARKUP_NAME = "<b>bot</b>_error"
NEWLINE_NAME = "two\nlines"
APOSTROPHE_NAME = "bot's_limit"
LONG_NAME = "x" * 200
LONG_MESSAGE = "Z" * 200

THOUSAND_MILLION = 1_000_000_000
ONE_BILLIONTH = 1e-9
INFINITY = float("inf")
MINUS_INFINITY = float("-inf")
NOT_A_NUMBER = float("nan")

# Values the platform decides for itself. Never compared; each is
# pinned in a test of its own.
PLATFORM_CHOSEN = ("bar_read_back_value", "splitter_settled_sizes")

WIDGETS_HELD: list = []


# ---------------------------------------------------------------------
# The risk manager both sides read
# ---------------------------------------------------------------------


class FakeAction:
    """One rule action, carrying the word the Action cell prints."""

    def __init__(self, value):
        self.value = value


class FakeAlert:
    """One risk alert, with the five fields an alert row reads."""

    def __init__(
        self,
        timestamp=RECENT_STAMP,
        severity="warning",
        rule_name="max_drawdown",
        message="drawdown 12.5% over 10.0%",
        action_taken="pause_bot",
    ):
        self.timestamp = timestamp
        self.severity = severity
        self.rule_name = rule_name
        self.message = message
        self.action_taken = FakeAction(action_taken)


class FakeSnapshot:
    """One portfolio snapshot, with the four fields the bars read."""

    def __init__(
        self,
        running_count=0,
        total_exposure=0.0,
        asset_exposures=None,
        exchange_exposures=None,
    ):
        self.running_count = running_count
        self.total_exposure = total_exposure
        self.asset_exposures = {} if asset_exposures is None else dict(asset_exposures)
        self.exchange_exposures = (
            {} if exchange_exposures is None else dict(exchange_exposures)
        )


class FakeRiskManager:
    """A risk manager whose every read is steerable."""

    def __init__(
        self,
        status=None,
        snapshots=(),
        alerts=(),
        status_error=None,
        snapshots_error=None,
        alerts_error=None,
        truthy=True,
    ):
        self._status = {} if status is None else status
        self._snapshots = [FakeSnapshot(**spec) for spec in snapshots]
        self._alerts = [FakeAlert(**spec) for spec in alerts]
        self.status_error = status_error
        self.snapshots_error = snapshots_error
        self.alerts_error = alerts_error
        self.truthy = truthy
        self.status_reads = 0

    def __bool__(self):
        return self.truthy

    def get_status(self):
        if self.status_error is not None:
            raise self.status_error
        self.status_reads += 1
        return self._status

    @property
    def snapshots(self):
        if self.snapshots_error is not None:
            raise self.snapshots_error
        return list(self._snapshots)

    @property
    def alerts(self):
        if self.alerts_error is not None:
            raise self.alerts_error
        return list(self._alerts)


def status(
    drawdown=0.0,
    peak=0.0,
    exposure=0.0,
    critical=0,
    alerts_hour=0,
    rules=None,
):
    """One status summary, as ``get_status`` returns it."""
    return {
        "drawdown_pct": drawdown,
        "peak_pnl": peak,
        "total_exposure": exposure,
        "critical_alerts": critical,
        "alerts_1h": alerts_hour,
        "rules": {} if rules is None else rules,
    }


def rule(threshold=10.0, action="pause_bot", enabled=True):
    """One risk rule, as the status summary carries it."""
    return {"threshold": threshold, "action": action, "enabled": enabled}


RULES_TWO = {
    "max_drawdown": rule(15.0, "pause_bot", True),
    "daily_loss_limit": rule(250.0, "stop_bot", False),
}

SNAPSHOT_TWO = {
    "running_count": 4,
    "total_exposure": 1000.0,
    "asset_exposures": {"BTC": 500.0, "ETH": 200.0},
    "exchange_exposures": {"coinbase": 700.0, "kraken": 300.0},
}


def alert(**over):
    """One alert's values, with the happy alert as the base."""
    base = {
        "timestamp": RECENT_STAMP,
        "severity": "warning",
        "rule_name": "max_drawdown",
        "message": "drawdown 12.5% over 10.0%",
        "action_taken": "pause_bot",
    }
    base.update(over)
    return base


def snapshot(**over):
    """One snapshot's values, with the happy snapshot as the base."""
    base = dict(SNAPSHOT_TWO)
    base.update(over)
    return base


REFRESH_CASES: dict = {
    "happy": {
        "status": status(12.5, 1234.5678, 4500.25, 0, 2, RULES_TWO),
        "snapshots": [snapshot()],
        "alerts": [
            alert(),
            alert(severity="critical", timestamp=OLDER_STAMP, rule_name="daily_loss"),
        ],
    },
    "empty": {"status": {}, "snapshots": [], "alerts": []},
    "zero": {
        "status": status(0, 0, 0, 0, 0, {}),
        "snapshots": [snapshot(running_count=0, total_exposure=0.0)],
        "alerts": [],
    },
    "negative": {
        "status": status(-5.0, -900.25, -1200.5, 0, 0, {"drift": rule(-3.5, "warn")}),
        "snapshots": [
            snapshot(
                running_count=-2,
                total_exposure=-800.0,
                asset_exposures={"BTC": -400.0},
                exchange_exposures={"kraken": -400.0},
            )
        ],
        "alerts": [alert(message="exposure fell below zero")],
    },
    "thousand_million": {
        "status": status(
            THOUSAND_MILLION,
            THOUSAND_MILLION,
            THOUSAND_MILLION,
            THOUSAND_MILLION,
            0,
            {"cap": rule(THOUSAND_MILLION)},
        ),
        "snapshots": [
            snapshot(
                running_count=THOUSAND_MILLION,
                total_exposure=float(THOUSAND_MILLION),
                asset_exposures={"BTC": float(THOUSAND_MILLION)},
                exchange_exposures={"coinbase": float(THOUSAND_MILLION)},
            )
        ],
        "alerts": [alert()],
    },
    "one_billionth": {
        "status": status(
            ONE_BILLIONTH,
            ONE_BILLIONTH,
            ONE_BILLIONTH,
            0,
            0,
            {"dust": rule(ONE_BILLIONTH)},
        ),
        "snapshots": [
            snapshot(
                total_exposure=ONE_BILLIONTH,
                asset_exposures={"BTC": ONE_BILLIONTH},
                exchange_exposures={"coinbase": ONE_BILLIONTH},
            )
        ],
        "alerts": [],
    },
    "infinity": {
        "status": status(INFINITY, INFINITY, INFINITY, 0, 0, {"cap": rule(INFINITY)}),
        "snapshots": [
            snapshot(
                total_exposure=INFINITY,
                asset_exposures={"BTC": INFINITY},
                exchange_exposures={"coinbase": INFINITY},
            )
        ],
        "alerts": [],
    },
    "infinite_threshold": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {"cap": rule(INFINITY)}),
        "snapshots": [],
        "alerts": [],
    },
    "not_a_number": {
        "status": status(
            NOT_A_NUMBER,
            NOT_A_NUMBER,
            NOT_A_NUMBER,
            0,
            0,
            {"drift": rule(NOT_A_NUMBER)},
        ),
        "snapshots": [snapshot(total_exposure=100.0)],
        "alerts": [],
    },
    "critical_status": {
        "status": status(20.0, 10.0, 5000.0, 3, 9, RULES_TWO),
        "snapshots": [snapshot()],
        "alerts": [alert(severity="critical")],
    },
    "warning_status": {
        "status": status(6.0, 10.0, 5000.0, 0, 4, RULES_TWO),
        "snapshots": [snapshot()],
        "alerts": [alert()],
    },
    "zero_total_exposure": {
        "status": status(1.0, 1.0, 0.0, 0, 0, {}),
        "snapshots": [
            snapshot(
                total_exposure=0.0,
                asset_exposures={"BTC": 25.0},
                exchange_exposures={"kraken": 25.0},
            )
        ],
        "alerts": [],
    },
    "no_snapshots": {
        "status": status(3.0, 5.0, 10.0, 0, 0, RULES_TWO),
        "snapshots": [],
        "alerts": [alert()],
    },
    "asset_bands": {
        "status": status(2.0, 1.0, 1.0, 0, 0, {}),
        "snapshots": [
            snapshot(
                total_exposure=100.0,
                asset_exposures={"BTC": 50.0, "ETH": 30.0, "SOL": 20.0},
                exchange_exposures={},
            )
        ],
        "alerts": [],
    },
    "exchange_bands": {
        "status": status(2.0, 1.0, 1.0, 0, 0, {}),
        "snapshots": [
            snapshot(
                total_exposure=100.0,
                asset_exposures={},
                exchange_exposures={"coinbase": 70.0, "kraken": 50.0, "gemini": 20.0},
            )
        ],
        "alerts": [],
    },
    "stale_alert": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "snapshots": [],
        "alerts": [alert(timestamp=STALE_STAMP), alert()],
    },
    "nan_alert_stamp": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "snapshots": [],
        "alerts": [alert(timestamp=NOT_A_NUMBER), alert()],
    },
    "billion_alert_stamp": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "snapshots": [],
        "alerts": [alert(timestamp=BILLION_STAMP), alert()],
    },
    "long_message": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {LONG_NAME: rule()}),
        "snapshots": [
            snapshot(
                asset_exposures={LONG_NAME: 100.0},
                exchange_exposures={LONG_NAME: 100.0},
            )
        ],
        "alerts": [alert(message=LONG_MESSAGE, rule_name=LONG_NAME)],
    },
    "unicode_names": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {UNICODE_NAME: rule()}),
        "snapshots": [
            snapshot(
                asset_exposures={UNICODE_NAME: 100.0},
                exchange_exposures={UNICODE_NAME: 100.0},
            )
        ],
        "alerts": [alert(rule_name=UNICODE_NAME, message=UNICODE_NAME)],
    },
    "markup_names": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {MARKUP_NAME: rule()}),
        "snapshots": [
            snapshot(
                asset_exposures={MARKUP_NAME: 100.0},
                exchange_exposures={MARKUP_NAME: 100.0},
            )
        ],
        "alerts": [alert(rule_name=MARKUP_NAME, message=MARKUP_NAME)],
    },
    "apostrophe_names": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {APOSTROPHE_NAME: rule()}),
        "snapshots": [
            snapshot(
                asset_exposures={APOSTROPHE_NAME: 100.0},
                exchange_exposures={APOSTROPHE_NAME: 100.0},
            )
        ],
        "alerts": [alert(rule_name=APOSTROPHE_NAME, message=APOSTROPHE_NAME)],
    },
    "newline_names": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {NEWLINE_NAME: rule()}),
        "snapshots": [
            snapshot(
                asset_exposures={NEWLINE_NAME: 100.0},
                exchange_exposures={NEWLINE_NAME: 100.0},
            )
        ],
        "alerts": [alert(rule_name=NEWLINE_NAME, message=NEWLINE_NAME)],
    },
    "wrong_capitals": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {"MAX_Drawdown": rule()}),
        "snapshots": [
            snapshot(
                asset_exposures={"btc": 100.0}, exchange_exposures={"COINBASE": 1.0}
            )
        ],
        "alerts": [alert(severity="CRITICAL")],
    },
    "disabled_rule": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {"halt_all": rule(1.0, "warn", False)}),
        "snapshots": [],
        "alerts": [],
    },
    "missing_status_keys": {
        "status": {"rules": RULES_TWO},
        "snapshots": [],
        "alerts": [],
    },
    "falsy_manager": {
        "status": status(9.0, 9.0, 9.0, 0, 0, RULES_TWO),
        "snapshots": [snapshot()],
        "alerts": [alert()],
        "truthy": False,
    },
    "status_raises": {"status_error": RuntimeError("status unavailable")},
    "snapshots_raises": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "snapshots_error": RuntimeError("snapshots unavailable"),
    },
    "alerts_raises": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "alerts_error": RuntimeError("alerts unavailable"),
    },
    "peak_is_text": {"status": status(1.0, "high", 1.0, 0, 0, {})},
    "exposure_is_none": {"status": status(1.0, 1.0, None, 0, 0, {})},
    "critical_is_text": {"status": status(1.0, 1.0, 1.0, "many", 0, {})},
    "minus_infinity_critical": {
        "status": status(1.0, 1.0, 1.0, MINUS_INFINITY, MINUS_INFINITY, {}),
        "snapshots": [],
        "alerts": [],
    },
    "amount_is_text": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "snapshots": [snapshot(asset_exposures={"BTC": "lots"})],
    },
    "amount_is_not_a_number": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "snapshots": [
            snapshot(
                total_exposure=100.0,
                asset_exposures={"BTC": NOT_A_NUMBER},
                exchange_exposures={},
            )
        ],
    },
    "amount_is_minus_infinity": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "snapshots": [
            snapshot(
                total_exposure=100.0,
                asset_exposures={"BTC": MINUS_INFINITY},
                exchange_exposures={},
            )
        ],
    },
    "exchange_name_is_number": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "snapshots": [
            snapshot(asset_exposures={}, exchange_exposures={7: 100.0}),
        ],
    },
    "alert_stamp_is_text": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "alerts": [alert(timestamp="noon")],
    },
    "alert_stamp_infinite": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {}),
        "alerts": [alert(timestamp=INFINITY)],
    },
    "threshold_is_text": {
        "status": status(1.0, 1.0, 1.0, 0, 0, {"cap": rule("high")}),
    },
    "rules_is_a_list": {"status": status(1.0, 1.0, 1.0, 0, 0, [])},
}

# Cases where both sides stop part way rather than painting a whole tab.
REFRESH_REFUSING = (
    "infinity",
    "status_raises",
    "snapshots_raises",
    "alerts_raises",
    "peak_is_text",
    "exposure_is_none",
    "critical_is_text",
    "amount_is_text",
    "amount_is_not_a_number",
    "amount_is_minus_infinity",
    "exchange_name_is_number",
    "alert_stamp_is_text",
    "alert_stamp_infinite",
    "threshold_is_text",
    "rules_is_a_list",
)

# The refusal each of those carries, measured off the shipped tab.
REFUSAL_TYPES = {
    "infinity": "ValueError",
    "status_raises": "RuntimeError",
    "snapshots_raises": "RuntimeError",
    "alerts_raises": "RuntimeError",
    "peak_is_text": "ValueError",
    "exposure_is_none": "TypeError",
    "critical_is_text": "TypeError",
    "amount_is_text": "TypeError",
    "amount_is_not_a_number": "ValueError",
    "amount_is_minus_infinity": "OverflowError",
    "exchange_name_is_number": "AttributeError",
    "alert_stamp_is_text": "TypeError",
    "alert_stamp_infinite": "OverflowError",
    "threshold_is_text": "ValueError",
    "rules_is_a_list": "AttributeError",
}

# Step sequences. A tab that shrinks a table and then stops part way
# leaves the rows it already wrote, which one input alone cannot show.
SEQUENCE_CASES: dict = {
    "grow_then_shrink": ("happy", "stale_alert", "empty"),
    "shrink_then_refuse": ("happy", "threshold_is_text", "happy"),
    "refuse_in_the_middle": ("happy", "alert_stamp_is_text", "zero"),
    "bars_then_fewer_bars": ("asset_bands", "zero_total_exposure", "asset_bands"),
    "bars_then_refuse": ("asset_bands", "amount_is_text", "exchange_bands"),
    "state_walk": ("warning_status", "critical_status", "zero"),
    "empty_then_full": ("empty", "happy"),
    "refuse_first": ("status_raises", "happy"),
}

# Gauge readings driven straight through both paints.
GAUGE_CASES: dict = {
    "safe": (2.0, 25),
    "band_edge_warning": (10.0, 25),
    "band_edge_danger": (17.5, 25),
    "over_full": (40.0, 25),
    "zero": (0.0, 25),
    "negative": (-5.0, 25),
    "thousand_million": (float(THOUSAND_MILLION), 25),
    "one_billionth": (ONE_BILLIONTH, 25),
    "infinity": (INFINITY, 25),
    "whole_number": (12, 25),
    "decimal_number": (12.0, 25),
    "minus_infinity": (MINUS_INFINITY, 25),
    "not_a_number": (NOT_A_NUMBER, 25),
    "zero_max": (5.0, 0),
    "text_value": ("high", 25),
    "text_max": (5.0, "wide"),
}

GAUGE_REFUSING = (
    "minus_infinity",
    "not_a_number",
    "zero_max",
    "text_value",
    "text_max",
)

GAUGE_REFUSAL_TYPES = {
    "minus_infinity": "OverflowError",
    "not_a_number": "ValueError",
    "zero_max": "ZeroDivisionError",
    "text_value": "TypeError",
    "text_max": "TypeError",
}

# One rule whose action is a number, kept out of the value comparison:
# a table item built from a number prints nothing and carries the
# number as its type, which is the platform's answer, not the tab's.
NUMBER_ACTION_RULES = {"cap": {"threshold": 1.0, "action": 5, "enabled": True}}


def make_manager(name):
    """One fresh manager for a case, so no case sees another's marks."""
    return FakeRiskManager(**REFRESH_CASES[name])


# ---------------------------------------------------------------------
# Reading the two sides into one shape
# ---------------------------------------------------------------------


def canon_colour(value):
    """One colour in a single spelling, so ``#888`` and ``#888888`` agree.

    The widget stores a colour, never the text it was given, so the same
    canonical form is applied to both sides.
    """
    from PySide6.QtGui import QColor

    if not value:
        return ""
    return QColor(value).name().lower()


def typed(value):
    """One value as text that keeps its type apart.

    ``12`` and ``12.0`` are one value to a plain comparison and two
    different readings on screen, and two separately built
    not-a-numbers are never equal to each other though they print the
    same. Reading each as text settles both.
    """
    return f"{type(value).__name__}:{value!r}"


def as_text(value):
    """One whole structure with every plain value read as its own text."""
    if isinstance(value, dict):
        return {key: as_text(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_text(item) for item in value]
    return typed(value)


def product_only(state):
    """One side's state with every platform-chosen value dropped.

    A progress bar keeps a value outside its range instead of taking
    it, and a splitter settles its panes to fit the window. Neither
    number is the tab's, so neither is compared; each is pinned in a
    test of its own.
    """
    return {key: item for key, item in state.items() if key not in PLATFORM_CHOSEN}


def canon_rows(rows):
    """One table's rows as text, canonical colour and alignment."""
    return [
        [
            {
                "text": found["text"],
                "color": canon_colour(found["color"]),
                "alignment": found["alignment"],
            }
            for found in row
        ]
        for row in rows
    ]


def read_table(table):
    """One real table's rows, read cell by cell off the widget."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor

    rows = []
    for row in range(table.rowCount()):
        cells = []
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is None:
                cells.append({"text": None, "color": "", "alignment": ""})
                continue
            brush = item.foreground()
            colour = "" if brush.style() == Qt.NoBrush else QColor(brush.color()).name()
            cells.append(
                {
                    "text": item.text(),
                    "color": colour.lower(),
                    "alignment": (
                        "AlignCenter"
                        if int(item.textAlignment()) == 132
                        else str(int(item.textAlignment()))
                    ),
                }
            )
        rows.append(cells)
    return rows


@contextmanager
def bar_values_asked():
    """Record the value every progress bar is GIVEN, for one drive.

    A progress bar rewrites what it is given, so the value it reports is
    the platform's answer. What the tab asked for is only readable here,
    as the call is made. The record is appended as each call happens, so
    a drive that stops part way keeps what it already asked for.
    """
    from PySide6.QtWidgets import QProgressBar

    asked: dict = {}
    original = QProgressBar.setValue

    def watch(self, value):
        asked[id(self)] = value
        return original(self, value)

    QProgressBar.setValue = watch
    try:
        yield asked
    finally:
        QProgressBar.setValue = original


def read_bars(bars, asked):
    """The shipped exposure bars, in the order the tab holds them."""
    return [
        {
            "label": bar._label.text(),
            "label_style": bar._label.styleSheet(),
            "asked_value": asked.get(id(bar._bar)),
            "format_text": bar._bar.format(),
            "value_text": bar._value_label.text(),
            "value_style": bar._value_label.styleSheet(),
            "bar_style": bar._bar.styleSheet(),
        }
        for bar in bars.values()
    ]


def read_model_bars(bars):
    """The surface's exposure bars, in the order the model holds them."""
    return [bar.state() for bar in bars.values()]


def read_tab(tab, asked):
    """The shipped tab's visible state, read off the live widgets."""
    return {
        "status_text": tab._lbl_status.text(),
        "status_style": tab._lbl_status.styleSheet(),
        "peak_text": tab._lbl_peak.text(),
        "peak_style": tab._lbl_peak.styleSheet(),
        "exposure_text": tab._lbl_exposure.text(),
        "exposure_style": tab._lbl_exposure.styleSheet(),
        "bots_text": tab._lbl_bots.text(),
        "bots_style": tab._lbl_bots.styleSheet(),
        "gauge_value": tab._dd_gauge._value,
        "gauge_max": tab._dd_gauge._max,
        "asset_bars": read_bars(tab._asset_bars, asked),
        "exchange_bars": read_bars(tab._exch_bars, asked),
        "alert_rows": canon_rows(read_table(tab._alerts_table)),
        "rule_rows": canon_rows(read_table(tab._rules_table)),
        "bar_read_back_value": [bar._bar.value() for bar in tab._asset_bars.values()],
    }


def read_model(model):
    """The surface model's state in the same shape as the shipped tab's."""
    return {
        "status_text": model.status_text,
        "status_style": model.status_style,
        "peak_text": model.peak_text,
        "peak_style": model.peak_style,
        "exposure_text": model.exposure_text,
        "exposure_style": model.exposure_style,
        "bots_text": model.bots_text,
        "bots_style": model.bots_style,
        "gauge_value": model.gauge.value,
        "gauge_max": model.gauge.max_pct,
        "asset_bars": read_model_bars(model.asset_bars),
        "exchange_bars": read_model_bars(model.exchange_bars),
        "alert_rows": canon_rows(model.alert_rows),
        "rule_rows": canon_rows(model.rule_rows),
        "bar_read_back_value": [],
    }


def headline(message):
    """The first line of a refusal.

    A refusal that lists every type it accepts can never report a
    changed type, so only the first line is compared.
    """
    return str(message).splitlines()[0] if str(message) else ""


def guarded(run):
    """Run one drive, keeping either what it returned or how it refused."""
    try:
        run()
        return {"error": "", "message": ""}
    except Exception as exc:
        return {"error": type(exc).__name__, "message": headline(exc)}


def digest(body):
    """One case's whole state as a single hash."""
    return hashlib.sha256(
        json.dumps(as_text(body), sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def app():
    """The process application object every render needs."""
    from tests.qt_pixel import ensure_app

    found = ensure_app()
    load_run_fonts()
    return found


def new_tab(manager):
    """One real RiskTab, held so no read reaches a collected widget."""
    app()
    tab = shipped.RiskTab(manager)
    WIDGETS_HELD.append(tab)
    return tab


# ---------------------------------------------------------------------
# Drivers
# ---------------------------------------------------------------------


def old_refresh(name, by_argument=False):
    """Drive the shipped tab's refresh over one case."""
    manager = make_manager(name)
    tab = new_tab(None if by_argument else manager)
    with bar_values_asked() as asked:
        outcome = guarded(
            lambda: tab.refresh(manager) if by_argument else tab.refresh()
        )
        state = read_tab(tab, asked)
    return {"outcome": outcome, "state": state}


def new_refresh(name, by_argument=False):
    """Drive the surface's refresh over the same case."""
    manager = make_manager(name)
    model = surface.RiskTabModel(None if by_argument else manager)
    outcome = guarded(
        lambda: model.refresh(manager) if by_argument else model.refresh()
    )
    return {"outcome": outcome, "state": read_model(model)}


def new_refresh_model(name):
    """The surface model for one case, and how the drive ended."""
    model = surface.RiskTabModel(make_manager(name))
    return model, guarded(model.refresh)


def old_no_manager_refresh():
    """Drive the shipped tab's refresh with no manager anywhere."""
    tab = new_tab(None)
    with bar_values_asked() as asked:
        outcome = guarded(tab.refresh)
        state = read_tab(tab, asked)
    return {"outcome": outcome, "state": state}


def new_no_manager_refresh():
    """Drive the surface's refresh with no manager anywhere."""
    model = surface.RiskTabModel(None)
    return {"outcome": guarded(model.refresh), "state": read_model(model)}


def old_sequence(names):
    """Drive a list of cases through ONE shipped tab, in order."""
    tab = new_tab(None)
    steps = []
    with bar_values_asked() as asked:
        for name in names:
            manager = make_manager(name)
            outcome = guarded(lambda: tab.refresh(manager))
            steps.append({"outcome": outcome, "state": read_tab(tab, asked)})
    return steps


def new_sequence(names):
    """Drive the same list of cases through ONE surface model, in order."""
    model = surface.RiskTabModel(None)
    steps = []
    for name in names:
        manager = make_manager(name)
        outcome = guarded(lambda: model.refresh(manager))
        steps.append({"outcome": outcome, "state": read_model(model)})
    return steps


# ---------------------------------------------------------------------
# Side by side, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(REFRESH_CASES))
def test_the_refresh_is_the_shipped_tabs_refresh(name):
    """The surface painted a different tab than the shipped refresh."""
    old = old_refresh(name)
    new = new_refresh(name)
    assert product_only(new["state"]) == product_only(old["state"]), name
    assert new["outcome"] == old["outcome"], name
    assert digest(product_only(new["state"])) == digest(
        product_only(old["state"])
    ), name


@pytest.mark.parametrize("name", sorted(REFRESH_CASES))
def test_the_refresh_reads_every_number_as_its_own_text(name):
    """A whole number and a decimal compared as one value."""
    old = as_text(product_only(old_refresh(name)["state"]))
    new = as_text(product_only(new_refresh(name)["state"]))
    assert new == old, name


@pytest.mark.parametrize("name", sorted(REFRESH_CASES))
def test_the_refresh_by_argument_is_the_shipped_tabs_refresh(name):
    """The manager passed to refresh reached one side and not the other."""
    old = old_refresh(name, by_argument=True)
    new = new_refresh(name, by_argument=True)
    assert product_only(new["state"]) == product_only(old["state"]), name
    assert new["outcome"] == old["outcome"], name


@pytest.mark.parametrize("name", sorted(REFRESH_CASES))
def test_the_refresh_snapshot_holds_the_whole_tab(name):
    """The comparison passed by measuring nothing."""
    old = old_refresh(name)
    refused = name in REFRESH_REFUSING
    assert (old["outcome"]["error"] != "") is refused, name
    state = old["state"]
    assert state["status_text"].startswith("STATUS: "), name
    assert state["peak_text"].startswith("Peak P/L: $"), name
    assert state["exposure_text"].startswith("Total Exposure: $"), name
    assert state["bots_text"].startswith("Running Bots: "), name
    for row in state["alert_rows"]:
        assert len(row) == 5, name
    for row in state["rule_rows"]:
        assert len(row) == 4, name
    if not refused:
        assert old["outcome"]["message"] == "", name


def test_the_no_manager_refresh_is_the_shipped_tabs():
    """A tab with no manager painted differently on the two sides."""
    old = old_no_manager_refresh()
    new = new_no_manager_refresh()
    assert product_only(new["state"]) == product_only(old["state"])
    assert digest(product_only(new["state"])) == digest(product_only(old["state"]))
    assert old["state"]["status_text"] == "STATUS: MONITORING"
    assert old["state"]["peak_text"] == "Peak P/L: $0.00"
    assert old["state"]["exposure_text"] == "Total Exposure: $0.00"
    assert old["state"]["bots_text"] == "Running Bots: 0"
    assert old["state"]["alert_rows"] == []
    assert old["state"]["rule_rows"] == []
    assert new_no_manager_refresh()["state"]["gauge_value"] == 0.0


def test_a_manager_that_reads_as_nothing_is_skipped_on_both_sides():
    """A falsy manager was read by one side and skipped by the other."""
    old = old_refresh("falsy_manager")
    new = new_refresh("falsy_manager")
    assert product_only(new["state"]) == product_only(old["state"])
    assert old["state"]["status_text"] == "STATUS: MONITORING"
    assert old["state"]["rule_rows"] == []
    model, _ = new_refresh_model("falsy_manager")
    assert model.refresh_path == surface.REFRESH_PATH_NO_MANAGER
    assert make_manager("falsy_manager").status_reads == 0
    read = make_manager("happy")
    surface.RiskTabModel(read).refresh()
    assert read.status_reads == 1


def test_the_sample_hashes_are_reported():
    """Two sides agreed by both carrying nothing at all."""
    samples = {}
    for name in ("happy", "empty", "critical_status", "asset_bands", "unicode_names"):
        old = digest(product_only(old_refresh(name)["state"]))
        new = digest(product_only(new_refresh(name)["state"]))
        samples[name] = (old, new)
        assert old == new, name
    assert len({pair[0] for pair in samples.values()}) == 5
    changed = old_refresh("happy")["state"]
    changed["status_text"] = "STATUS: OFF"
    assert digest(product_only(changed)) != samples["happy"][0]
    assert digest(product_only(old_refresh("happy")["state"])) == samples["happy"][0]


def test_two_genuinely_different_cases_hash_apart():
    """The hash reports one value for every input, so it proves nothing."""
    happy = digest(product_only(old_refresh("happy")["state"]))
    empty = digest(product_only(old_refresh("empty")["state"]))
    assert happy != empty
    assert digest(product_only(new_refresh("happy")["state"])) == happy
    assert digest(product_only(new_refresh("empty")["state"])) == empty
    assert digest(product_only(new_refresh("happy")["state"])) != empty
    assert digest(product_only(old_refresh("empty")["state"])) != happy


def test_the_hash_tells_a_whole_number_from_a_decimal():
    """The hash reads 12 and 12.0 as one value."""
    assert digest({"pct": 12}) != digest({"pct": 12.0})
    assert digest({"pct": 12}) == digest({"pct": 12})
    assert typed(12) != typed(12.0)
    assert typed(NOT_A_NUMBER) == typed(float("nan"))
    assert float("nan") != float("nan")
    assert digest({"pct": NOT_A_NUMBER}) == digest({"pct": float("nan")})
    assert digest({"pct": INFINITY}) != digest({"pct": MINUS_INFINITY})


def test_the_platform_rule_keeps_a_seeded_value_and_hides_the_platforms():
    """The rule hides a value the tab chose, or keeps one the platform did."""
    state = old_refresh("asset_bands")["state"]
    kept = product_only(state)
    assert "status_text" in kept
    assert kept["status_text"] == state["status_text"]
    assert "asset_bars" in kept
    for name in PLATFORM_CHOSEN:
        assert name not in kept, name
    assert "bar_read_back_value" in state
    assert len(state["bar_read_back_value"]) == 3
    assert len(PLATFORM_CHOSEN) == 2
    assert product_only({"splitter_settled_sizes": [1, 2], "a": 1}) == {"a": 1}


# ---------------------------------------------------------------------
# Step sequences
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SEQUENCE_CASES))
def test_a_sequence_of_refreshes_leaves_the_shipped_tabs_state(name):
    """A run of refreshes ended somewhere the shipped tab does not."""
    names = SEQUENCE_CASES[name]
    old = old_sequence(names)
    new = new_sequence(names)
    assert len(old) == len(new) == len(names), name
    for index, (old_step, new_step) in enumerate(zip(old, new)):
        assert product_only(new_step["state"]) == product_only(
            old_step["state"]
        ), f"{name} step {index}"
        assert new_step["outcome"] == old_step["outcome"], f"{name} step {index}"
    assert digest([product_only(step["state"]) for step in new]) == digest(
        [product_only(step["state"]) for step in old]
    ), name


def test_a_shrink_that_refuses_part_way_leaves_the_rows_it_already_wrote():
    """A table that stops part way was compared as one that never started."""
    steps = old_sequence(SEQUENCE_CASES["shrink_then_refuse"])
    new = new_sequence(SEQUENCE_CASES["shrink_then_refuse"])
    assert len(steps[0]["state"]["rule_rows"]) == 2
    assert steps[1]["outcome"]["error"] == "ValueError"
    assert len(steps[1]["state"]["rule_rows"]) == 1
    assert steps[1]["state"]["rule_rows"][0][0]["text"] == "Max Drawdown"
    assert steps[1]["state"]["rule_rows"][0][1]["text"] == "15.0"
    assert len(steps[1]["state"]["alert_rows"]) == 0
    assert new[1]["state"]["rule_rows"] == steps[1]["state"]["rule_rows"]
    assert new[1]["state"]["alert_rows"] == steps[1]["state"]["alert_rows"]
    assert len(steps[2]["state"]["rule_rows"]) == 2
    assert steps[2]["state"]["rule_rows"][0][0]["text"] == "Max Drawdown"


def test_a_bar_added_by_an_earlier_refresh_is_kept_by_both_sides():
    """One side dropped an exposure bar the other keeps."""
    names = SEQUENCE_CASES["bars_then_fewer_bars"]
    old = old_sequence(names)
    new = new_sequence(names)
    assert [bar["label"] for bar in old[0]["state"]["asset_bars"]] == [
        "BTC",
        "ETH",
        "SOL",
    ]
    assert [bar["label"] for bar in old[1]["state"]["asset_bars"]] == [
        "BTC",
        "ETH",
        "SOL",
    ]
    assert old[1]["state"]["asset_bars"][1]["value_text"] == "$30"
    assert new[1]["state"]["asset_bars"] == old[1]["state"]["asset_bars"]
    assert len(old[2]["state"]["asset_bars"]) == 3


def test_a_sequence_that_refuses_first_still_paints_the_second_step():
    """A refusal on the first step stopped the tab answering the second."""
    old = old_sequence(SEQUENCE_CASES["refuse_first"])
    new = new_sequence(SEQUENCE_CASES["refuse_first"])
    assert old[0]["outcome"]["error"] == "RuntimeError"
    assert old[0]["state"]["rule_rows"] == []
    assert old[1]["outcome"]["error"] == ""
    assert len(old[1]["state"]["rule_rows"]) == 2
    assert product_only(new[1]["state"]) == product_only(old[1]["state"])


# ---------------------------------------------------------------------
# What each side did when it refused
# ---------------------------------------------------------------------


def test_the_outcome_set_holds_both_an_answer_and_a_refusal():
    """Every case answered, or every case refused, so the set proves nothing."""
    outcomes = {name: old_refresh(name)["outcome"]["error"] for name in REFRESH_CASES}
    refused = {name for name, error in outcomes.items() if error}
    answered = set(outcomes) - refused
    assert refused == set(REFRESH_REFUSING)
    assert len(answered) >= 20
    assert len(refused) == 15
    for name, kind in REFUSAL_TYPES.items():
        assert outcomes[name] == kind, name
    assert len({outcomes[name] for name in REFRESH_REFUSING}) == 5
    assert outcomes["infinity"] == "ValueError"


@pytest.mark.parametrize("name", REFRESH_REFUSING)
def test_a_refusal_carries_the_same_wording_on_both_sides(name):
    """One side refused with wording the other does not carry."""
    old = old_refresh(name)["outcome"]
    new = new_refresh(name)["outcome"]
    assert new == old, name
    assert old["error"] == REFUSAL_TYPES[name], name
    assert old["message"] != "", name


def test_the_refusal_comparison_reports_two_different_wordings():
    """The refusal comparison passes whatever the second side said."""
    first = old_refresh("peak_is_text")["outcome"]
    second = old_refresh("exposure_is_none")["outcome"]
    assert first != second
    assert first["error"] != second["error"]
    assert first["message"] != second["message"]
    same_kind = old_refresh("status_raises")["outcome"]
    other_kind = old_refresh("snapshots_raises")["outcome"]
    assert same_kind["error"] == other_kind["error"]
    assert same_kind["message"] != other_kind["message"]
    assert headline("a: b") == "a: b"
    assert headline("two\nlines") == "two"


# ---------------------------------------------------------------------
# The values behind the lines, the bars and the tables
# ---------------------------------------------------------------------


def test_the_status_line_is_the_shipped_tabs_own():
    """The status line changed its wording or its colour rule."""
    for name, text, style in (
        ("critical_status", "STATUS: CRITICAL", f"color: {ERROR_HEX}; "),
        ("warning_status", "STATUS: WARNING", f"color: {WARNING_HEX}; "),
        ("zero", "STATUS: MONITORING", f"color: {PRIMARY_HEX}; "),
        (
            "minus_infinity_critical",
            "STATUS: MONITORING",
            f"color: {PRIMARY_HEX}; ",
        ),
    ):
        old = old_refresh(name)["state"]
        new = new_refresh(name)["state"]
        expected = style + "font-size: 14px; font-weight: bold;"
        assert old["status_text"] == text, name
        assert new["status_text"] == text, name
        assert old["status_style"] == expected, name
        assert new["status_style"] == expected, name
    assert surface.status_state(1, 0) == "critical"
    assert surface.status_state(0, 1) == "warning"
    assert surface.status_state(0, 0) == "monitoring"


def test_the_metric_lines_are_the_shipped_tabs_own():
    """A metric line changed its wording or its number of decimals."""
    for name, peak, exposure, bots in (
        (
            "happy",
            "Peak P/L: $1,234.5678",
            "Total Exposure: $4,500.25",
            "Running Bots: 4",
        ),
        ("zero", "Peak P/L: $0.0000", "Total Exposure: $0.00", "Running Bots: 0"),
        (
            "negative",
            "Peak P/L: $-900.2500",
            "Total Exposure: $-1,200.50",
            "Running Bots: -2",
        ),
        (
            "thousand_million",
            "Peak P/L: $1,000,000,000.0000",
            "Total Exposure: $1,000,000,000.00",
            "Running Bots: 1000000000",
        ),
        (
            "one_billionth",
            "Peak P/L: $0.0000",
            "Total Exposure: $0.00",
            "Running Bots: 4",
        ),
        ("infinity", "Peak P/L: $inf", "Total Exposure: $inf", "Running Bots: 4"),
        (
            "not_a_number",
            "Peak P/L: $nan",
            "Total Exposure: $nan",
            "Running Bots: 4",
        ),
        (
            "missing_status_keys",
            "Peak P/L: $0.0000",
            "Total Exposure: $0.00",
            "Running Bots: 0",
        ),
    ):
        old = old_refresh(name)["state"]
        new = new_refresh(name)["state"]
        assert old["peak_text"] == peak, name
        assert old["exposure_text"] == exposure, name
        assert old["bots_text"] == bots, name
        assert new["peak_text"] == peak, name
        assert new["exposure_text"] == exposure, name
        assert new["bots_text"] == bots, name
    assert surface.PEAK_FORMAT.count("{peak:") == 1
    assert surface.EXPOSURE_FORMAT.count("{exposure:") == 1
    assert surface.BOTS_FORMAT.count("{count}") == 1
    assert surface.PEAK_FORMAT.format(peak=1) == "Peak P/L: $1.0000"
    assert surface.EXPOSURE_FORMAT.format(exposure=1) == "Total Exposure: $1.00"
    assert surface.BOTS_FORMAT.format(count=1) == "Running Bots: 1"


def test_the_metric_styles_are_the_shipped_tabs_own():
    """A metric line changed its colour."""
    old = old_refresh("happy")["state"]
    assert old["peak_style"] == f"color: {SUCCESS_HEX}; font-size: 13px;"
    assert old["exposure_style"] == f"color: {TEXT_HIGH_HEX}; font-size: 13px;"
    assert old["bots_style"] == f"color: {INACTIVE_HEX}; font-size: 12px;"
    new = new_refresh("happy")["state"]
    assert new["peak_style"] == old["peak_style"]
    assert new["exposure_style"] == old["exposure_style"]
    assert new["bots_style"] == old["bots_style"]


def test_the_gauge_takes_the_drawdown_and_keeps_its_ceiling():
    """The gauge stopped reading the drawdown or changed its ceiling."""
    for name, value in (
        ("happy", 12.5),
        ("zero", 0),
        ("negative", -5.0),
        ("infinity", INFINITY),
        ("missing_status_keys", 0),
    ):
        old = old_refresh(name)["state"]
        new = new_refresh(name)["state"]
        assert old["gauge_value"] == value or (value != value), name
        assert typed(new["gauge_value"]) == typed(old["gauge_value"]), name
        assert old["gauge_max"] == 25, name
        assert new["gauge_max"] == 25, name
    assert typed(new_refresh("not_a_number")["state"]["gauge_value"]) == typed(
        old_refresh("not_a_number")["state"]["gauge_value"]
    )
    assert surface.GAUGE_SET_MAX_DEFAULT == 25
    assert surface.GAUGE_START_MAX_PCT == 25.0


def test_the_exposure_bars_are_the_shipped_tabs_own():
    """An exposure bar changed its label, its share or its colour."""
    old = old_refresh("asset_bands")["state"]["asset_bars"]
    new = new_refresh("asset_bands")["state"]["asset_bars"]
    assert new == old
    assert [bar["label"] for bar in old] == ["BTC", "ETH", "SOL"]
    assert [bar["format_text"] for bar in old] == ["50.0%", "30.0%", "20.0%"]
    assert [bar["value_text"] for bar in old] == ["$50", "$30", "$20"]
    assert [bar["asked_value"] for bar in old] == [50, 30, 20]
    assert ERROR_HEX in old[0]["bar_style"]
    assert WARNING_HEX in old[1]["bar_style"]
    assert INFO_HEX in old[2]["bar_style"]
    assert old[0]["label_style"] == f"color: {INACTIVE_HEX}; font-size: 11px;"
    assert old[0]["value_style"] == f"color: {TEXT_HIGH_HEX}; font-size: 11px;"


def test_the_exchange_bars_use_the_wider_thresholds():
    """The exchange bars stopped using their own colour thresholds."""
    old = old_refresh("exchange_bands")["state"]["exchange_bars"]
    new = new_refresh("exchange_bands")["state"]["exchange_bars"]
    assert new == old
    assert [bar["label"] for bar in old] == ["Coinbase", "Kraken", "Gemini"]
    assert ERROR_HEX in old[0]["bar_style"]
    assert WARNING_HEX in old[1]["bar_style"]
    assert INFO_HEX in old[2]["bar_style"]
    assert surface.asset_color(50.0) != surface.exchange_color(50.0)
    assert surface.ASSET_DANGER_PCT == 40
    assert surface.ASSET_WARNING_PCT == 25
    assert surface.EXCHANGE_DANGER_PCT == 60
    assert surface.EXCHANGE_WARNING_PCT == 40


def test_an_exposure_share_is_measured_against_the_reported_total():
    """A total of nothing stopped falling back to one."""
    old = old_refresh("zero_total_exposure")["state"]
    new = new_refresh("zero_total_exposure")["state"]
    assert new["asset_bars"] == old["asset_bars"]
    assert old["asset_bars"][0]["format_text"] == "2500.0%"
    assert old["asset_bars"][0]["asked_value"] == 100
    assert surface.exposure_total(0.0) == 1
    assert surface.exposure_total(0) == 1
    assert surface.exposure_total(None) == 1
    assert surface.exposure_total(250.0) == 250.0
    assert surface.FALLBACK_TOTAL == 1


def test_the_bar_value_the_tab_asked_for_is_what_is_compared():
    """The value the bar reports was compared instead of the value asked for.

    A progress bar keeps a value outside its range instead of taking it,
    so what the tab asked for and what the bar holds are two different
    numbers. The asked value is the tab's; the held value is Qt's.
    """
    from PySide6.QtWidgets import QProgressBar

    app()
    state = old_refresh("zero_total_exposure")["state"]
    assert state["asset_bars"][0]["asked_value"] == 100
    probe = QProgressBar()
    probe.setRange(0, 100)
    probe.setValue(2500)
    assert probe.value() == -1
    assert probe.value() != 2500
    settled = QProgressBar()
    settled.setRange(0, 100)
    settled.setValue(50)
    settled.setValue(-5)
    assert settled.value() == 50
    assert surface.BAR_VALUE_CEILING == 100
    assert surface.BAR_RANGE == (0, 100)


def test_the_bar_recorder_reports_what_it_watched():
    """The bar recorder records nothing, so every asked value reads as absent."""
    from PySide6.QtWidgets import QProgressBar

    app()
    with bar_values_asked() as asked:
        probe = QProgressBar()
        probe.setRange(0, 100)
        probe.setValue(37)
        assert asked[id(probe)] == 37
    after = QProgressBar()
    after.setRange(0, 100)
    with bar_values_asked() as empty:
        pass
    after.setValue(12)
    assert empty == {}
    assert after.value() == 12


def test_the_bar_recorder_keeps_what_it_saw_before_a_refusal():
    """A drive that stopped part way lost the values it had already asked for."""
    old = old_refresh("amount_is_text")
    assert old["outcome"]["error"] == "TypeError"
    assert old["state"]["asset_bars"] == []
    steps = old_sequence(SEQUENCE_CASES["bars_then_refuse"])
    assert steps[1]["outcome"]["error"] == "TypeError"
    assert [bar["asked_value"] for bar in steps[1]["state"]["asset_bars"]] == [
        50,
        30,
        20,
    ]
    new = new_sequence(SEQUENCE_CASES["bars_then_refuse"])
    assert new[1]["state"]["asset_bars"] == steps[1]["state"]["asset_bars"]


def test_the_alert_row_is_the_shipped_tabs_own():
    """An alert cell changed its text, its colour or its order."""
    old = old_refresh("happy")["state"]["alert_rows"]
    new = new_refresh("happy")["state"]["alert_rows"]
    assert new == old
    assert len(old) == 2
    assert [found["text"] for found in old[0]][1:] == [
        "CRITICAL",
        "daily_loss",
        "drawdown 12.5% over 10.0%",
        "pause_bot",
    ]
    assert old[0][1]["color"] == canon_colour(ERROR_HEX)
    assert old[1][1]["color"] == canon_colour(WARNING_HEX)
    assert [found["color"] for found in old[0]][2:] == ["", "", ""]
    for row in old:
        assert len(row[0]["text"]) == 8
        assert row[0]["text"][2] == ":" and row[0]["text"][5] == ":"


def test_the_newest_alert_is_painted_first():
    """The alerts table stopped showing the newest row at the top."""
    old = old_refresh("happy")["state"]["alert_rows"]
    assert old[0][2]["text"] == "daily_loss"
    assert old[1][2]["text"] == "max_drawdown"
    assert new_refresh("happy")["state"]["alert_rows"] == old


def test_an_alert_older_than_a_day_is_not_shown():
    """The alerts window stopped hiding a stale alert."""
    old = old_refresh("stale_alert")["state"]["alert_rows"]
    new = new_refresh("stale_alert")["state"]["alert_rows"]
    assert new == old
    assert len(old) == 1
    assert surface.ALERT_WINDOW_S == 86400
    assert surface.within_window(NOW - 10, NOW) is True
    assert surface.within_window(NOW - 90_000, NOW) is False


def test_an_alert_stamped_not_a_number_is_dropped_by_both_sides():
    """A not-a-number stamp reached the table on one side only."""
    old = old_refresh("nan_alert_stamp")["state"]["alert_rows"]
    new = new_refresh("nan_alert_stamp")["state"]["alert_rows"]
    assert new == old
    assert len(old) == 1
    assert surface.within_window(NOT_A_NUMBER, NOW) is False
    assert (NOW - NOT_A_NUMBER < 86400) is False


def test_a_long_alert_message_is_cut_where_the_shipped_tab_cuts_it():
    """The message column stopped truncating at the shipped width."""
    old = old_refresh("long_message")["state"]["alert_rows"]
    new = new_refresh("long_message")["state"]["alert_rows"]
    assert new == old
    assert old[0][3]["text"] == "Z" * 80
    assert len(old[0][3]["text"]) == 80
    assert old[0][2]["text"] == "x" * 200
    assert surface.MESSAGE_MAX_CHARS == 80


def test_a_severity_in_the_wrong_capitals_is_not_critical():
    """The severity comparison stopped being exact."""
    old = old_refresh("wrong_capitals")["state"]["alert_rows"]
    new = new_refresh("wrong_capitals")["state"]["alert_rows"]
    assert new == old
    assert old[0][1]["text"] == "CRITICAL"
    assert old[0][1]["color"] == canon_colour(WARNING_HEX)
    assert surface.severity_color("CRITICAL") == surface.SEVERITY_OTHER_COLOR
    assert surface.severity_color("critical") == surface.SEVERITY_CRITICAL_COLOR


def test_the_rule_row_is_the_shipped_tabs_own():
    """A rule cell changed its text, its colour or its order."""
    old = old_refresh("happy")["state"]["rule_rows"]
    new = new_refresh("happy")["state"]["rule_rows"]
    assert new == old
    assert len(old) == 2
    assert [found["text"] for found in old[0]] == [
        "Max Drawdown",
        "15.0",
        "pause_bot",
        "Yes",
    ]
    assert [found["text"] for found in old[1]] == [
        "Daily Loss Limit",
        "250.0",
        "stop_bot",
        "No",
    ]
    assert old[0][3]["color"] == canon_colour(SUCCESS_HEX)
    assert old[1][3]["color"] == canon_colour(ERROR_HEX)
    assert [found["color"] for found in old[0]][:3] == ["", "", ""]


def test_a_rule_name_is_titled_the_way_the_shipped_tab_titles_it():
    """The rule name column changed how it spells a name."""
    for name, expected in (
        ("wrong_capitals", "Max Drawdown"),
        ("apostrophe_names", "Bot'S Limit"),
        ("markup_names", "<B>Bot</B> Error"),
        ("unicode_names", "Δ Flip→⚡"),
    ):
        old = old_refresh(name)["state"]["rule_rows"]
        new = new_refresh(name)["state"]["rule_rows"]
        assert new == old, name
        assert old[0][0]["text"] == expected, name
    assert surface.rule_title("max_drawdown") == "Max Drawdown"
    assert surface.RULE_NAME_UNDERSCORE == "_"
    assert surface.RULE_NAME_SPACE == " "


def test_a_newline_in_a_name_is_kept_by_both_sides():
    """A name with a line break reached one side only."""
    old = old_refresh("newline_names")["state"]
    new = new_refresh("newline_names")["state"]
    assert new["rule_rows"] == old["rule_rows"]
    assert new["alert_rows"] == old["alert_rows"]
    assert old["rule_rows"][0][0]["text"] == "Two\nLines"
    assert old["alert_rows"][0][2]["text"] == NEWLINE_NAME
    assert old["asset_bars"][0]["label"] == NEWLINE_NAME
    assert new["asset_bars"] == old["asset_bars"]


def test_the_threshold_is_printed_to_one_decimal():
    """The threshold column changed how many decimals it shows."""
    for name, expected in (
        ("happy", "15.0"),
        ("negative", "-3.5"),
        ("thousand_million", "1000000000.0"),
        ("one_billionth", "0.0"),
        ("infinite_threshold", "inf"),
        ("not_a_number", "nan"),
    ):
        old = old_refresh(name)["state"]["rule_rows"]
        assert old[0][1]["text"] == expected, name
        assert new_refresh(name)["state"]["rule_rows"] == old, name
    assert surface.THRESHOLD_FORMAT.count("{threshold:") == 1
    assert surface.THRESHOLD_FORMAT.format(threshold=2) == "2.0"


def test_a_number_where_text_belongs_is_kept_by_one_side_only():
    """A non-text cell value stopped being reported the way each side reports it.

    A Qt table item built from a number takes the item-type argument, so
    the cell prints nothing and carries the number as its type. The
    surface carries the number itself. Both answers are read here rather
    than assumed equal.
    """
    app()
    manager = FakeRiskManager(status=status(1.0, 1.0, 1.0, 0, 0, NUMBER_ACTION_RULES))
    tab = new_tab(manager)
    tab.refresh()
    item = tab._rules_table.item(0, 2)
    assert item.text() == ""
    assert item.type() == 5
    model = surface.RiskTabModel(
        FakeRiskManager(status=status(1.0, 1.0, 1.0, 0, 0, NUMBER_ACTION_RULES))
    )
    model.refresh()
    assert model.rule_rows[0][2]["text"] == 5
    assert model.rule_rows[0][0]["text"] == "Cap"
    assert tab._rules_table.item(0, 0).text() == "Cap"


def test_the_colours_are_told_apart_by_the_canonical_form():
    """The colour comparison collapsed two different colours into one."""
    tokens = (
        SUCCESS_HEX,
        ERROR_HEX,
        WARNING_HEX,
        PRIMARY_HEX,
        INFO_HEX,
        LABEL_HEX,
        INACTIVE_HEX,
        TEXT_HIGH_HEX,
        CHART_HEX,
        CONTROL_HEX,
        CARD_BORDER_HEX,
    )
    assert len({canon_colour(hexed) for hexed in tokens}) == len(tokens)
    assert canon_colour(LABEL_HEX) == "#888888"
    assert canon_colour("") == ""
    assert canon_colour(SUCCESS_HEX) != canon_colour(ERROR_HEX)


def test_the_gauge_label_colour_is_compared_as_exact_text():
    """A colour whose channels are equal cannot show a swapped channel.

    ``#888`` has one value in all three channels, so no swap changes it.
    It is compared as exact text on both sides instead.
    """
    assert surface.GAUGE_LABEL_COLOR == LABEL_HEX
    assert LABEL_HEX == "#888"
    assert canon_colour("#888") == canon_colour("#888888")
    assert canon_colour("#884") != canon_colour("#488")
    assert surface.GAUGE_LABEL_COLOR != surface.GAUGE_VALUE_COLOR


def test_the_time_column_is_read_the_same_way_on_both_sides():
    """The time column stopped reading the clock the shipped tab reads."""
    stamped = time.strftime("%H:%M:%S", time.localtime(RECENT_STAMP))
    assert surface.clock_text(RECENT_STAMP) == stamped
    old = old_refresh("billion_alert_stamp")["state"]["alert_rows"]
    new = new_refresh("billion_alert_stamp")["state"]["alert_rows"]
    assert new == old
    assert surface.clock_text(RECENT_STAMP) != surface.clock_text(BILLION_STAMP)
    assert surface.TIME_FORMAT == "%H:%M:%S"


# ---------------------------------------------------------------------
# The gauge both sides paint
# ---------------------------------------------------------------------


def painter_steps(sink=None):
    """A recorder for every drawing call one paint makes.

    The steps are appended as each call is made, so a paint that stops
    part way keeps what it already drew rather than reading as a paint
    that never started. `sink` is handed each step as it happens, which
    is how a probe keeps a paint that ends its own process.
    """
    from PySide6.QtGui import QColor, QFont, QPainter, QPen

    steps: list = []
    original = {
        name: getattr(QPainter, name)
        for name in ("setPen", "setFont", "drawArc", "drawText", "setRenderHint")
    }

    def describe(value):
        if isinstance(value, QPen):
            return ["pen", QColor(value.color()).name().lower(), value.width()]
        if isinstance(value, QColor):
            return ["color", value.name().lower()]
        if isinstance(value, QFont):
            return [
                "font",
                value.family(),
                value.pointSize(),
                int(value.weight().value),
            ]
        if hasattr(value, "width") and hasattr(value, "x"):
            return ["rect", value.x(), value.y(), value.width(), value.height()]
        if hasattr(value, "value"):
            return ["flag", int(value.value)]
        return value

    def watch(name):
        def wrapper(self, *args, **kwargs):
            step = [name, [describe(item) for item in args]]
            steps.append(step)
            if sink is not None:
                sink(step)
            return original[name](self, *args, **kwargs)

        return wrapper

    return steps, original, watch


@contextmanager
def gauge_drawing():
    """Record every drawing call made while this block runs."""
    from PySide6.QtGui import QPainter

    steps, original, watch = painter_steps()
    for name in original:
        setattr(QPainter, name, watch(name))
    try:
        yield steps
    finally:
        for name, found in original.items():
            setattr(QPainter, name, found)


def gauge_probe_source(name, record_path):
    """The probe that drives the shipped gauge's paint in a fresh process.

    The case table and the recorder are imported from this module, so
    the probe drives exactly what the in-process comparison drives.
    Every drawing call is written to `record_path` and flushed as it
    happens, because a reading the gauge cannot draw ends the process
    inside the paint, before any handler of ours runs.
    """
    lines = [
        "import json, os, sys",
        "os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')",
        "from PySide6.QtWidgets import QApplication",
        "from PySide6.QtGui import QPainter",
        "QApplication([])",
        "from src.gui.risk_tab import DrawdownGauge",
        "from tests.test_risk_tab_surface_parity import (",
        "    GAUGE_CASES, GAUGE_PIXEL_SIZE, painter_steps)",
        "value, max_pct = GAUGE_CASES[%r]" % name,
        "out = open(%r, 'w', newline=chr(10))" % str(record_path),
        "def record(step):",
        "    out.write(json.dumps(step) + chr(10))",
        "    out.flush()",
        "    os.fsync(out.fileno())",
        "steps, original, watch = painter_steps(record)",
        "for found in original:",
        "    setattr(QPainter, found, watch(found))",
        "gauge = DrawdownGauge()",
        "gauge.resize(*GAUGE_PIXEL_SIZE)",
        "gauge.set_value(value, max_pct)",
        "gauge.grab()",
        "out.close()",
        "os._exit(0)",
    ]
    return "\n".join(lines) + "\n"


def run_gauge_probe(name):
    """Drive one shipped gauge paint in its own process.

    Returns how the process ended, every drawing call it made, and the
    refusal its own process reported. A reading the gauge cannot draw
    ends the process, so the calls are read back from the file rather
    than from what the process printed, and the refusal is read off the
    last line the process wrote to its error stream.
    """
    with tempfile.TemporaryDirectory() as room:
        record_path = Path(room) / "drawn.jsonl"
        done = subprocess.run(
            [sys.executable, "-"],
            input=gauge_probe_source(name, record_path).encode("utf-8"),
            capture_output=True,
            cwd=str(REPO_ROOT),
            timeout=300,
            check=False,
        )
        written = (
            record_path.read_text(encoding="utf-8") if record_path.exists() else ""
        )
    steps = [json.loads(line) for line in written.splitlines() if line]
    spoken = [
        line for line in done.stderr.decode("utf-8", "replace").splitlines() if line
    ]
    return done.returncode, steps, spoken[-1] if spoken else ""


def old_gauge(name):
    """Drive the shipped gauge's paint over one reading.

    A reading the gauge cannot draw leaves its painter open, and the
    process ends as soon as that painter is collected. Those readings
    are driven in a process of their own, so the shipped paint is the
    one measured either way.
    """
    if name in GAUGE_REFUSING:
        code, steps, refusal = run_gauge_probe(name)
        return {
            "outcome": None,
            "returncode": code,
            "shapes": drawn_shape(steps),
            "refusal": refusal,
        }
    app()
    value, max_pct = GAUGE_CASES[name]
    gauge = shipped.DrawdownGauge()
    WIDGETS_HELD.append(gauge)
    gauge.resize(*GAUGE_PIXEL_SIZE)
    gauge.set_value(value, max_pct)
    with gauge_drawing() as steps:
        outcome = guarded(gauge.grab)
    return {
        "outcome": outcome,
        "returncode": 0,
        "shapes": drawn_shape(steps),
        "refusal": "",
    }


def new_gauge(name):
    """Drive the surface's gauge paint over the same reading."""
    value, max_pct = GAUGE_CASES[name]
    model = surface.DrawdownGaugeModel()
    model.set_value(value, max_pct)
    outcome = guarded(lambda: model.paint(*GAUGE_PIXEL_SIZE))
    return {"outcome": outcome, "painted": list(model.painted)}


def drawn_shape(steps):
    """The recorded drawing calls as the arcs and strings they make."""
    shapes = []
    pen = None
    font = None
    for name, args in steps:
        if name == "setPen":
            pen = args[0]
        elif name == "setFont":
            font = args[0]
        elif name == "drawArc":
            shapes.append(
                {
                    "kind": "arc",
                    "color": pen[1],
                    "pen_width": pen[2],
                    "box": list(args[:4]),
                    "start_angle": args[4],
                    "span_angle": args[5],
                }
            )
        elif name == "drawText":
            rect = args[0]
            shapes.append(
                {
                    "kind": "text",
                    "color": pen[1],
                    "box": [rect[1], rect[2], rect[3], rect[4]],
                    "text": args[2],
                    "family": font[1],
                    "point_size": font[2],
                    "weight_value": font[3],
                    "alignment_value": args[1][1],
                }
            )
    return shapes


def model_shape(painted):
    """The surface's paint steps in the same shape as the recorded calls."""
    shapes = []
    for step in painted:
        if step["kind"] == "arc":
            shapes.append(
                {
                    "kind": "arc",
                    "color": canon_colour(step["color"]),
                    "pen_width": step["pen_width"],
                    "box": list(step["box"]),
                    "start_angle": step["start_angle"],
                    "span_angle": step["span_angle"],
                }
            )
        else:
            shapes.append(
                {
                    "kind": "text",
                    "color": canon_colour(step["color"]),
                    "box": list(step["box"]),
                    "text": step["text"],
                    "family": step["family"],
                    "point_size": step["point_size"],
                    "weight_value": step["weight_value"],
                    "alignment_value": step["alignment_value"],
                }
            )
    return shapes


@pytest.mark.parametrize("name", sorted(GAUGE_CASES))
def test_the_gauge_draws_what_the_shipped_gauge_draws(name):
    """The gauge drew a different arc, colour or string than the shipped one."""
    old = old_gauge(name)
    new = new_gauge(name)
    if name not in GAUGE_REFUSING:
        assert new["outcome"] == old["outcome"], name
    assert model_shape(new["painted"]) == old["shapes"], name
    assert digest(model_shape(new["painted"])) == digest(old["shapes"]), name


def test_the_gauge_refusals_are_the_readings_the_shipped_gauge_cannot_draw():
    """A reading the surface draws is one the shipped gauge draws too."""
    outcomes = {name: new_gauge(name)["outcome"]["error"] for name in GAUGE_CASES}
    refused = {name for name, error in outcomes.items() if error}
    answered = set(outcomes) - refused
    assert refused == set(GAUGE_REFUSING)
    assert len(answered) == 11
    for name, kind in GAUGE_REFUSAL_TYPES.items():
        assert outcomes[name] == kind, name
    assert len({outcomes[name] for name in GAUGE_REFUSING}) == 4
    for name in answered:
        assert old_gauge(name)["outcome"]["error"] == "", name
    for name in GAUGE_REFUSING:
        assert old_gauge(name)["returncode"] != 0, name


def test_a_reading_the_gauge_cannot_draw_ends_the_process():
    """A reading the gauge cannot draw was reported as harmless.

    The shipped paint opens a painter and closes it only on the way out.
    A value it cannot draw leaves that painter open and the process does
    not survive the paint, so nothing downstream ever sees a refusal.
    The surface answers with the refusal instead. The wording of a
    refusal is the platform's, so it is read off the shipped process
    and compared, never written down here.
    """
    drawable, drawn, quiet = run_gauge_probe("safe")
    assert drawable == 0
    assert len(drawn) == 11
    assert quiet == ""
    ended, partial, spoken = run_gauge_probe("zero_max")
    assert ended != 0
    assert len(partial) == 3
    refused = new_gauge("zero_max")["outcome"]
    assert refused["error"] == "ZeroDivisionError"
    assert refused["message"], refused
    assert spoken.startswith(refused["error"] + ":"), spoken
    assert spoken.endswith(refused["message"]), (spoken, refused)
    assert headline("two\nlines") == "two"
    assert headline("a: b") == "a: b"


def test_a_gauge_paint_that_stops_part_way_keeps_the_arc_it_drew():
    """A paint that stopped part way was compared as one that never started."""
    old = old_gauge("zero_max")
    new = new_gauge("zero_max")
    assert new["outcome"]["error"] == "ZeroDivisionError"
    drawn = old["shapes"]
    assert len(drawn) == 1
    assert drawn[0]["color"] == canon_colour(CONTROL_HEX)
    assert model_shape(new["painted"]) == drawn
    assert old["returncode"] != 0
    assert len(old_gauge("safe")["shapes"]) == 4
    for name in GAUGE_REFUSING:
        assert len(old_gauge(name)["shapes"]) == 1, name
        assert len(new_gauge(name)["painted"]) == 1, name


def test_the_gauge_bands_change_where_the_shipped_gauge_changes_them():
    """A colour band moved its edge."""
    assert surface.gauge_band(0.0) == "safe"
    assert surface.gauge_band(0.399) == "safe"
    assert surface.gauge_band(0.4) == "warning"
    assert surface.gauge_band(0.699) == "warning"
    assert surface.gauge_band(0.7) == "danger"
    assert surface.gauge_band(1.0) == "danger"
    assert surface.gauge_band(NOT_A_NUMBER) == "danger"
    assert canon_colour(surface.gauge_color(0.0)) == canon_colour(SUCCESS_HEX)
    assert canon_colour(surface.gauge_color(0.5)) == canon_colour(WARNING_HEX)
    assert canon_colour(surface.gauge_color(0.9)) == canon_colour(ERROR_HEX)
    edges = {
        name: old_gauge(name)["shapes"][1]["color"]
        for name in ("safe", "band_edge_warning", "band_edge_danger")
    }
    assert edges["safe"] == canon_colour(SUCCESS_HEX)
    assert edges["band_edge_warning"] == canon_colour(WARNING_HEX)
    assert edges["band_edge_danger"] == canon_colour(ERROR_HEX)


def test_the_gauge_sweep_never_passes_a_full_turn():
    """The arc swept past the end of its track."""
    assert surface.gauge_ratio(40.0, 25) == 1.0
    assert surface.gauge_ratio(INFINITY, 25) == 1.0
    assert surface.gauge_span(1.0) == -4320
    assert surface.gauge_span(0.0) == 0
    assert surface.gauge_span(0.5) == -2160
    assert surface.GAUGE_TRACK_SPAN == -4320
    assert surface.GAUGE_START_ANGLE == 3600
    full = old_gauge("over_full")["shapes"]
    assert full[1]["span_angle"] == full[0]["span_angle"] == -4320
    assert full[0]["start_angle"] == 3600


def test_a_whole_number_and_a_decimal_reading_draw_the_same_string():
    """Two readings that print alike were told apart by the drawing."""
    whole = old_gauge("whole_number")["shapes"]
    decimal = old_gauge("decimal_number")["shapes"]
    assert whole == decimal
    assert whole[2]["text"] == "12.0%"
    assert typed(GAUGE_CASES["whole_number"][0]) != typed(
        GAUGE_CASES["decimal_number"][0]
    )
    assert model_shape(new_gauge("whole_number")["painted"]) == whole


# ---------------------------------------------------------------------
# The tab the two sides paint
# ---------------------------------------------------------------------


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def colour_count(image):
    """How many distinct colours a render painted."""
    data = bytes(image.constBits())
    return len({data[index : index + 4] for index in range(0, len(data), 4)})


def payload_for(name):
    """The surface's payload for one case, sealed as it comes off."""
    model = surface.RiskTabModel(make_manager(name))
    payload = surface.build_view_model(model, action="refresh")
    return sealed({"payload": payload, "state": read_model(model)})


def build_gauge(payload):
    """One gauge widget that draws only what the surface's model draws."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QFont, QPainter, QPen
    from PySide6.QtWidgets import QWidget

    reading = payload["gauge"]

    class SurfaceGauge(QWidget):
        def __init__(self):
            super().__init__(None)
            self.setAccessibleName(reading["accessible_name"])
            self.setMinimumSize(*reading["minimum_size"])
            self.setMaximumSize(*reading["maximum_size"])
            self._model = surface.DrawdownGaugeModel()
            self._model.set_value(reading["value"], reading["max_pct"])

        def paintEvent(self, _event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            drawn = self._model.paint(self.width(), self.height())
            for step in drawn["steps"]:
                box = step["box"]
                if step["kind"] == "arc":
                    painter.setPen(QPen(QColor(step["color"]), step["pen_width"]))
                    painter.drawArc(
                        box[0],
                        box[1],
                        box[2],
                        box[3],
                        step["start_angle"],
                        step["span_angle"],
                    )
                else:
                    painter.setPen(QColor(step["color"]))
                    painter.setFont(
                        QFont(
                            step["family"],
                            step["point_size"],
                            step["weight_value"],
                        )
                    )
                    painter.drawText(
                        _box_rect(box),
                        Qt.AlignmentFlag(step["alignment_value"]),
                        step["text"],
                    )
            painter.end()

    return SurfaceGauge()


def _box_rect(box):
    """One drawing box as the rectangle a paint takes."""
    from PySide6.QtCore import QRect

    return QRect(box[0], box[1], box[2], box[3])


def build_bar(bar, payload):
    """One exposure bar built only from the surface's payload."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar

    reading = payload["bar"]
    frame = QFrame()
    frame.setAccessibleName(reading["accessible_name"])
    row = QHBoxLayout(frame)
    row.setContentsMargins(*payload["bar_margins"])
    label = QLabel(bar["label"])
    label.setMinimumWidth(reading["label_min_width"])
    label.setStyleSheet(bar["label_style"])
    progress = QProgressBar()
    progress.setRange(*reading["range"])
    progress.setTextVisible(reading["text_visible"])
    if bar["asked_value"] is not None:
        progress.setValue(bar["asked_value"])
        progress.setFormat(bar["format_text"])
    progress.setStyleSheet(bar["bar_style"])
    value = QLabel(bar["value_text"])
    value.setMinimumWidth(reading["value_min_width"])
    value.setAlignment(Qt.AlignmentFlag(reading["value_alignment_value"]))
    value.setStyleSheet(bar["value_style"])
    row.addWidget(label)
    row.addWidget(progress, stretch=payload["stretches"]["bar"])
    row.addWidget(value)
    return frame


def fill_table(table, columns, rows, payload, no_edits):
    """One table built from the payload alone, filled from one case's rows."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem

    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    table.setAlternatingRowColors(payload["alternating_row_colors"])
    if no_edits:
        table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.verticalHeader().setVisible(payload["vertical_header_visible"])
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column, found in enumerate(row):
            item = QTableWidgetItem(found["text"])
            item.setTextAlignment(Qt.AlignmentFlag(payload["cell_alignment_value"]))
            if found["color"]:
                item.setForeground(QColor(found["color"]))
            table.setItem(row_index, column, item)


def build_tab(sealed_payload):
    """One tab built only from the surface's view model and its state."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QSplitter,
        QTableWidget,
        QVBoxLayout,
        QWidget,
    )

    app()
    body = unaltered(sealed_payload)
    payload = body["payload"]
    state = body["state"]
    nodes = {node["name"]: node for node in payload["widgets"]}
    tab = QWidget()
    WIDGETS_HELD.append(tab)
    tab.setAccessibleName(payload["accessible_name"])
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(*payload["content_margins"])
    layout.setSpacing(payload["content_spacing"])

    split = QSplitter(Qt.Horizontal)
    split.setHandleWidth(payload["splitter_handle_width"])
    split.setChildrenCollapsible(payload["splitter_children_collapsible"])

    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.setContentsMargins(*payload["pane_margins"])

    gauge_row = QHBoxLayout()
    gauge_row.addWidget(build_gauge(payload))

    metrics = QVBoxLayout()
    for text, style in (
        (state["status_text"], state["status_style"]),
        (state["peak_text"], state["peak_style"]),
        (state["exposure_text"], state["exposure_style"]),
        (state["bots_text"], state["bots_style"]),
    ):
        line = QLabel(text)
        line.setStyleSheet(style)
        metrics.addWidget(line)
    metrics.addStretch()
    gauge_row.addLayout(metrics, stretch=payload["stretches"]["metrics"])
    left_layout.addLayout(gauge_row)

    for node_name, bars in (
        ("asset_group", state["asset_bars"]),
        ("exchange_group", state["exchange_bars"]),
    ):
        group = QGroupBox(nodes[node_name]["title"])
        group.setStyleSheet(nodes[node_name]["style_sheet"])
        column = QVBoxLayout(group)
        for bar in bars:
            column.addWidget(build_bar(bar, payload))
        left_layout.addWidget(group)

    left_layout.addStretch()
    split.addWidget(left)

    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(*payload["pane_margins"])

    alerts_group = QGroupBox(nodes["alerts_group"]["title"])
    alerts_group.setStyleSheet(nodes["alerts_group"]["style_sheet"])
    alerts_layout = QVBoxLayout(alerts_group)
    alerts_table = QTableWidget()
    fill_table(
        alerts_table,
        payload["alert_columns"],
        state["alert_rows"],
        payload,
        no_edits=True,
    )
    alerts_layout.addWidget(alerts_table)
    right_layout.addWidget(alerts_group, stretch=nodes["alerts_group"]["stretch"])

    rules_group = QGroupBox(nodes["rules_group"]["title"])
    rules_group.setStyleSheet(nodes["rules_group"]["style_sheet"])
    rules_layout = QVBoxLayout(rules_group)
    rules_table = QTableWidget()
    fill_table(
        rules_table,
        payload["rule_columns"],
        state["rule_rows"],
        payload,
        no_edits=False,
    )
    rules_layout.addWidget(rules_table)
    right_layout.addWidget(rules_group, stretch=nodes["rules_group"]["stretch"])

    split.addWidget(right)
    split.setSizes(payload["splitter_sizes"])
    layout.addWidget(split)
    return tab


PICTURE_CASES = (
    "happy",
    "empty",
    "zero",
    "critical_status",
    "warning_status",
    "asset_bands",
    "exchange_bands",
    "unicode_names",
    "markup_names",
    "long_message",
    "wrong_capitals",
    "disabled_rule",
    "negative",
)


def old_picture_tab(name):
    """The shipped tab, driven over one case and ready to render."""
    tab = new_tab(make_manager(name))
    tab.refresh()
    return tab


def new_picture_tab(name):
    """A tab built only from the surface's payload for the same case."""
    return build_tab(payload_for(name))


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_render_the_same_pixels(name):
    """The surface paints a tab the shipped tab does not."""
    app()
    old_side = render_offscreen(old_picture_tab(name), PIXEL_SIZE)
    new_side = render_offscreen(new_picture_tab(name), PIXEL_SIZE)
    assert_pictures_match(old_side=old_side, new_side=new_side, note=name)
    assert colour_count(old_side) > 1, name
    assert colour_count(new_side) > 1, name


@pytest.mark.parametrize("name", sorted(set(GAUGE_CASES) - set(GAUGE_REFUSING)))
def test_the_two_gauges_render_the_same_pixels(name):
    """The surface's gauge paints an arc the shipped gauge does not."""
    app()
    value, max_pct = GAUGE_CASES[name]
    old_gauge_widget = shipped.DrawdownGauge()
    WIDGETS_HELD.append(old_gauge_widget)
    old_gauge_widget.set_value(value, max_pct)
    model = surface.RiskTabModel()
    model.gauge.set_value(value, max_pct)
    payload = surface.build_view_model(model)
    new_gauge_widget = build_gauge(payload)
    WIDGETS_HELD.append(new_gauge_widget)
    assert_pictures_match(
        old_side=render_offscreen(old_gauge_widget, GAUGE_PIXEL_SIZE),
        new_side=render_offscreen(new_gauge_widget, GAUGE_PIXEL_SIZE),
        note=name,
    )


def test_the_picture_check_reports_two_different_real_cases():
    """The picture comparison passes whatever the second side paints.

    One render comes from the shipped tab and one from the surface, and
    the two carry genuinely different data. A comparison that could not
    report would call them the same.
    """
    app()
    assert_pictures_differ(
        old_side=render_offscreen(old_picture_tab("happy"), PIXEL_SIZE),
        new_side=render_offscreen(new_picture_tab("empty"), PIXEL_SIZE),
        note="happy against empty",
    )
    assert_pictures_differ(
        old_side=render_offscreen(old_picture_tab("empty"), PIXEL_SIZE),
        new_side=render_offscreen(new_picture_tab("asset_bands"), PIXEL_SIZE),
        note="empty against asset_bands",
    )
    assert_pictures_differ(
        old_side=render_offscreen(new_picture_tab("critical_status"), PIXEL_SIZE),
        new_side=render_offscreen(old_picture_tab("warning_status"), PIXEL_SIZE),
        note="the two sides the other way round",
    )
    assert_pictures_match(
        old_side=render_offscreen(old_picture_tab("happy"), PIXEL_SIZE),
        new_side=render_offscreen(new_picture_tab("happy"), PIXEL_SIZE),
        note="one case, both sides",
    )


def test_the_gauge_picture_check_reports_two_different_readings():
    """The gauge picture comparison passes whatever the second side paints."""
    app()

    def old_side(value):
        gauge = shipped.DrawdownGauge()
        WIDGETS_HELD.append(gauge)
        gauge.set_value(value, 25)
        return render_offscreen(gauge, GAUGE_PIXEL_SIZE)

    def new_side(value):
        model = surface.RiskTabModel()
        model.gauge.set_value(value, 25)
        built = build_gauge(surface.build_view_model(model))
        WIDGETS_HELD.append(built)
        return render_offscreen(built, GAUGE_PIXEL_SIZE)

    assert_pictures_differ(
        old_side=old_side(2.0), new_side=new_side(20.0), note="safe against danger"
    )
    assert_pictures_differ(
        old_side=new_side(2.0), new_side=old_side(20.0), note="the other way round"
    )
    assert_pictures_match(
        old_side=old_side(12.5), new_side=new_side(12.5), note="one reading"
    )


def test_a_payload_changed_after_it_came_off_is_refused_by_the_builder():
    """A render of a changed payload measured the host, not the product."""
    app()
    body = payload_for("happy")
    built = build_tab(body)
    assert built is not None
    body["state"]["status_text"] = "STATUS: OFF"
    with pytest.raises(AssertionError):
        build_tab(body)
    with pytest.raises(AssertionError):
        build_tab({"payload": {}, "state": {}})


def test_the_tab_declares_no_skin_of_its_own():
    """A colour the surface ships is one the tab never paints."""
    from tests.qt_pixel import render_widget

    app()
    assert surface.SKIN == {}
    assert surface.TAB_STYLE_SHEET == ""
    tab = old_picture_tab("happy")
    assert tab.styleSheet() == ""
    skinned = new_picture_tab("happy")
    skinned.setStyleSheet("QTableWidget { background: #3a1414; }")
    assert_pictures_differ(
        old_side=render_widget(old_picture_tab("happy"), PIXEL_SIZE),
        new_side=render_widget(skinned, PIXEL_SIZE),
        note="a skin the tab does not paint",
    )
    assert_pictures_match(
        old_side=render_widget(old_picture_tab("happy"), PIXEL_SIZE),
        new_side=render_widget(new_picture_tab("happy"), PIXEL_SIZE),
        note="neither side carries a skin of its own",
    )


def test_the_font_answer_changes_what_a_measurement_reads():
    """The two font runs took the same path, so one of them proves nothing."""
    app()
    narrow = app_font_advance_px(NARROW_LABEL)
    wide = app_font_advance_px(WIDE_LABEL)
    if has_real_fonts():
        assert wide > narrow
    else:
        assert wide == narrow


@skip_unless_no_fonts
def test_with_no_font_database_every_letter_advances_alike():
    """Two strings of equal length measured apart with no font database,
    so the box-font premise the picture checks rest on is stale."""
    app()
    assert app_font_advance_px(NARROW_LABEL) == app_font_advance_px(WIDE_LABEL)


@skip_unless_real_fonts
def test_with_a_font_database_the_letters_advance_apart():
    """A run holding a font database measured every glyph the same width,
    so no picture on it can report a changed string."""
    app()
    assert app_font_advance_px(WIDE_LABEL) > app_font_advance_px(NARROW_LABEL)


# ---------------------------------------------------------------------
# What a picture cannot see
# ---------------------------------------------------------------------


def test_the_splitter_sizes_are_compared_as_the_request():
    """The splitter request was read back instead of asserted.

    A window resizes the two panes to fit, so the sizes it reports are
    never the sizes it was given. The request is what the surface holds,
    and two different requests are proved to settle differently.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QSplitter, QWidget

    app()
    tab = old_picture_tab("happy")
    split = tab.findChild(QSplitter)
    assert split is not None
    assert surface.SPLITTER_SIZES == (400, 500)
    assert split.handleWidth() == surface.SPLITTER_HANDLE_WIDTH == 5
    assert split.childrenCollapsible() is surface.SPLITTER_CHILDREN_COLLAPSIBLE
    assert int(split.orientation().value) == surface.SPLITTER_ORIENTATION_VALUE
    assert surface.SPLITTER_ORIENTATION == "Horizontal"
    settled = []
    for request in ([400, 500], [700, 200]):
        probe = QSplitter(Qt.Horizontal)
        probe.addWidget(QWidget())
        probe.addWidget(QWidget())
        probe.resize(900, 400)
        probe.setSizes(request)
        render_offscreen(probe, (900, 400))
        settled.append(list(probe.sizes()))
    assert settled[0] != settled[1]
    assert settled[0] != [400, 500]


def test_the_gauge_size_limits_are_compared_as_the_request():
    """The gauge's size limits reached no pixel and were never compared."""
    app()
    tab = old_picture_tab("happy")
    gauge = tab._dd_gauge
    assert (gauge.minimumWidth(), gauge.minimumHeight()) == surface.GAUGE_MINIMUM_SIZE
    assert (gauge.maximumWidth(), gauge.maximumHeight()) == surface.GAUGE_MAXIMUM_SIZE
    assert surface.GAUGE_MINIMUM_SIZE == (160, 160)
    assert surface.GAUGE_MAXIMUM_SIZE == (200, 200)


def test_the_accessible_names_are_compared_as_strings():
    """A name a screen reader announces reached no pixel."""
    app()
    tab = old_picture_tab("asset_bands")
    assert tab.accessibleName() == surface.ACCESSIBLE_NAME
    assert tab._dd_gauge.accessibleName() == surface.GAUGE_ACCESSIBLE_NAME
    first = list(tab._asset_bars.values())[0]
    assert first.accessibleName() == surface.BAR_ACCESSIBLE_NAME
    assert surface.ACCESSIBLE_NAME == "Risk Tab"
    assert surface.GAUGE_ACCESSIBLE_NAME == "Drawdown Gauge"
    assert surface.BAR_ACCESSIBLE_NAME == "Exposure Bar"
    assert surface.RiskTabModel().accessible_name == surface.ACCESSIBLE_NAME
    assert surface.ExposureBarModel("x").accessible_name == surface.BAR_ACCESSIBLE_NAME


def test_the_edit_rule_on_the_two_tables_is_compared_as_a_value():
    """A table became editable or stopped being editable, unseen by a render."""
    from PySide6.QtWidgets import QTableWidget

    app()
    tab = old_picture_tab("happy")
    assert (
        int(tab._alerts_table.editTriggers().value)
        == surface.EDIT_TRIGGERS_NONE_VALUE
        == 0
    )
    assert (
        int(tab._rules_table.editTriggers().value)
        == surface.EDIT_TRIGGERS_DEFAULT_VALUE
        == 26
    )
    assert tab._alerts_table.editTriggers() == QTableWidget.NoEditTriggers
    assert tab._rules_table.editTriggers() != QTableWidget.NoEditTriggers
    assert surface.EDIT_TRIGGERS_NONE == ()
    assert len(surface.EDIT_TRIGGERS_DEFAULT) == 3


def test_the_table_settings_are_compared_as_values():
    """A header or a row rule drifted between the two sides."""
    from PySide6.QtWidgets import QHeaderView

    app()
    tab = old_picture_tab("happy")
    for table, columns in (
        (tab._alerts_table, surface.ALERT_COLUMNS),
        (tab._rules_table, surface.RULE_COLUMNS),
    ):
        assert table.columnCount() == len(columns)
        header = table.horizontalHeader()
        assert [
            table.horizontalHeaderItem(index).text() for index in range(len(columns))
        ] == list(columns)
        assert header.sectionResizeMode(0) == QHeaderView.Stretch
        assert int(header.sectionResizeMode(0).value) == surface.HEADER_RESIZE_VALUE
        assert table.alternatingRowColors() is surface.ALTERNATING_ROW_COLORS
        assert table.verticalHeader().isVisible() is surface.VERTICAL_HEADER_VISIBLE
    assert surface.ALERT_COLUMNS == ("Time", "Severity", "Rule", "Message", "Action")
    assert surface.RULE_COLUMNS == ("Rule", "Threshold", "Action", "Enabled")
    assert surface.ALERT_COLUMN_COUNT == 5
    assert surface.RULE_COLUMN_COUNT == 4


def test_the_layout_numbers_are_compared_as_values():
    """A margin or a spacing drifted between the two sides."""
    app()
    tab = old_picture_tab("asset_bands")
    margins = tab.layout().contentsMargins()
    assert (
        margins.left(),
        margins.top(),
        margins.right(),
        margins.bottom(),
    ) == surface.CONTENT_MARGINS
    assert tab.layout().spacing() == surface.CONTENT_SPACING == 8
    bar = list(tab._asset_bars.values())[0]
    bar_margins = bar.layout().contentsMargins()
    assert (
        bar_margins.left(),
        bar_margins.top(),
        bar_margins.right(),
        bar_margins.bottom(),
    ) == surface.BAR_MARGINS
    assert surface.CONTENT_MARGINS == (8, 8, 8, 8)
    assert surface.PANE_MARGINS == (0, 0, 0, 0)
    assert surface.BAR_MARGINS == (4, 2, 4, 2)


def test_the_bar_widths_and_alignment_are_compared_as_the_request():
    """A bar's asked-for width was read back rather than compared.

    A widget is free to give itself more room than it asked for, so the
    number it reports is the platform's. What it was GIVEN is compared.
    """
    app()
    tab = old_picture_tab("asset_bands")
    bar = list(tab._asset_bars.values())[0]
    assert bar._label.minimumWidth() == surface.BAR_LABEL_MIN_WIDTH == 80
    assert bar._value_label.minimumWidth() == surface.BAR_VALUE_MIN_WIDTH == 70
    assert (
        int(bar._value_label.alignment().value)
        == surface.BAR_VALUE_ALIGNMENT_VALUE
        == 130
    )
    assert surface.BAR_VALUE_ALIGNMENT == "AlignRight|AlignVCenter"
    assert bar._bar.isTextVisible() is surface.BAR_TEXT_VISIBLE
    assert (bar._bar.minimum(), bar._bar.maximum()) == surface.BAR_RANGE


def test_the_recorded_calls_are_compared_as_values():
    """The ordered call list reached no pixel and was never compared."""
    model, _ = new_refresh_model("happy")
    names = [call[0] for call in model.calls]
    assert names == [
        "refresh.start",
        "refresh.status",
        "refresh.gauge",
        "refresh.metrics",
        "refresh.state",
        "refresh.snapshot",
        "bar.add",
        "bar.set",
        "bar.add",
        "bar.set",
        "refresh.assets",
        "bar.add",
        "bar.set",
        "bar.add",
        "bar.set",
        "refresh.exchanges",
        "refresh.alerts",
        "refresh.rules",
        "refresh.return",
    ]
    assert model.calls[-1] == ["refresh.return", "painted", 2, 2]
    assert model.gauge.calls == [["gauge.set", 12.5, 25]]
    empty, _ = new_refresh_model("empty")
    assert [call[0] for call in empty.calls] == [
        "refresh.start",
        "refresh.status",
        "refresh.gauge",
        "refresh.metrics",
        "refresh.state",
        "refresh.alerts",
        "refresh.rules",
        "refresh.return",
    ]
    assert empty.calls[-1] == ["refresh.return", "painted", 0, 0]
    lonely = surface.RiskTabModel(None)
    lonely.refresh()
    assert [call[0] for call in lonely.calls] == ["refresh.start", "refresh.return"]


def test_the_metric_build_order_is_compared_as_a_value():
    """The order the four metric lines are built in reached no pixel."""
    assert surface.METRIC_BUILD_ORDER == (
        "peak_label",
        "exposure_label",
        "bots_label",
        "status_label",
    )
    assert surface.WIDGET_CHILDREN["metrics"] == (
        "status_label",
        "peak_label",
        "exposure_label",
        "bots_label",
        "metrics_stretch",
    )
    assert set(surface.METRIC_BUILD_ORDER) < set(surface.WIDGET_CHILDREN["metrics"])
    assert surface.METRIC_BUILD_ORDER[0] != surface.WIDGET_CHILDREN["metrics"][0]


BLIND_TO_THE_PICTURE = {
    "splitter_sizes": "test_the_splitter_sizes_are_compared_as_the_request",
    "splitter_handle_width": "test_the_splitter_sizes_are_compared_as_the_request",
    "splitter_collapsible": "test_the_splitter_sizes_are_compared_as_the_request",
    "gauge_size_limits": "test_the_gauge_size_limits_are_compared_as_the_request",
    "accessible_name": "test_the_accessible_names_are_compared_as_strings",
    "edit_triggers": "test_the_edit_rule_on_the_two_tables_is_compared_as_a_value",
    "header_resize_mode": "test_the_table_settings_are_compared_as_values",
    "vertical_header_visible": "test_the_table_settings_are_compared_as_values",
    "alternating_row_colors": "test_the_table_settings_are_compared_as_values",
    "content_margins": "test_the_layout_numbers_are_compared_as_values",
    "content_spacing": "test_the_layout_numbers_are_compared_as_values",
    "bar_margins": "test_the_layout_numbers_are_compared_as_values",
    "bar_min_widths": "test_the_bar_widths_and_alignment_are_compared_as_the_request",
    "bar_value_alignment": (
        "test_the_bar_widths_and_alignment_are_compared_as_the_request"
    ),
    "bar_range": "test_the_bar_widths_and_alignment_are_compared_as_the_request",
    "bar_asked_value": "test_the_bar_value_the_tab_asked_for_is_what_is_compared",
    "recorded_calls": "test_the_recorded_calls_are_compared_as_values",
    "metric_build_order": "test_the_metric_build_order_is_compared_as_a_value",
    "refusal_type": "test_the_outcome_set_holds_both_an_answer_and_a_refusal",
    "paint_refusal": "test_a_reading_the_gauge_cannot_draw_ends_the_process",
    "timer_delay": "test_the_tab_starts_no_timer",
    "bus_topic": "test_the_tab_subscribes_to_no_bus_topic",
    "action_wiring": "test_the_tab_wires_no_signal",
    "non_text_cell": "test_a_number_where_text_belongs_is_kept_by_one_side_only",
    "gauge_partial_paint": (
        "test_a_gauge_paint_that_stops_part_way_keeps_the_arc_it_drew"
    ),
}


def test_everything_a_picture_cannot_see_is_named_and_covered():
    """A value no render can report was left to the render to report."""
    app()
    assert len(BLIND_TO_THE_PICTURE) == 25
    for covered_by in BLIND_TO_THE_PICTURE.values():
        assert covered_by in globals(), covered_by
        assert callable(globals()[covered_by]), covered_by
    assert "no_such_test" not in globals()
    assert_pictures_match(
        old_side=render_offscreen(old_picture_tab("happy"), PIXEL_SIZE),
        new_side=render_offscreen(new_picture_tab("happy"), PIXEL_SIZE),
    )


# ---------------------------------------------------------------------
# The counterpart map
# ---------------------------------------------------------------------


CLASS_MAP = {
    "DrawdownGauge": "DrawdownGaugeModel",
    "ExposureBar": "ExposureBarModel",
    "RiskTab": "RiskTabModel",
}

METHOD_MAP = {
    "DrawdownGauge.__init__": "DrawdownGaugeModel.__init__",
    "DrawdownGauge.set_value": "DrawdownGaugeModel.set_value",
    "DrawdownGauge.paintEvent": "DrawdownGaugeModel.paint",
    "ExposureBar.__init__": "ExposureBarModel.__init__",
    "ExposureBar.set_value": "ExposureBarModel.set_value",
    "RiskTab.__init__": "RiskTabModel.__init__",
    "RiskTab._setup_ui": "RiskTabModel.setup_ui",
    "RiskTab.refresh": "RiskTabModel.refresh",
}

GAUGE_MEMBERS = {"__init__", "set_value", "paint"}
BAR_MEMBERS = {"__init__", "set_value", "state"}
TAB_MEMBERS = {
    "__init__",
    "setup_ui",
    "refresh",
    "_fill_bars",
    "_alert_row",
    "_rule_row",
    "_finish",
}

HELPER_MAP = {
    "widget_node": "widget",
    "bar_skin": "bar_style",
    "arc_sweep_ratio": "gauge_ratio",
    "arc_band": "gauge_band",
    "arc_colour": "gauge_color",
    "arc_sweep": "gauge_span",
    "arc_shape": "arc",
    "text_shape": "painted_text",
    "share_of_book": "exposure_pct",
    "book_total": "exposure_total",
    "band_by_threshold": "band_for",
    "asset_colour": "asset_color",
    "exchange_colour": "exchange_color",
    "header_state": "status_state",
    "rule_name": "rule_title",
    "severity_colour": "severity_color",
    "enabled_word": "enabled_text",
    "enabled_colour": "enabled_color",
    "time_of_day": "clock_text",
    "alert_is_recent": "within_window",
    "table_cell": "cell",
    "blank_table_row": "blank_row",
    "exchange_bar_label": "exchange_label",
    "manager_from_values": "build_manager",
    "payload": "build_view_model",
    "bridge_handler": "view_model",
}

SURFACE_ONLY_CLASSES = (
    "RiskAction",
    "RiskAlertRow",
    "PortfolioSnapshotRow",
    "RiskManagerSnapshot",
)


def members(owner):
    """Every method a class defines, by name.

    A plain callable test is not enough. Python reports a factory as
    callable and a read-only value as not callable, and a signal is
    callable while being no method at all. Each kind is named here.
    """
    found = set()
    for name, value in vars(owner).items():
        if name.startswith("__") and name != "__init__":
            continue
        if inspect.isfunction(value):
            found.add(name)
        elif isinstance(value, (staticmethod, classmethod, property)):
            found.add(name)
    return found


def resolve(dotted):
    """The member a dotted name in the map points at, inside the surface."""
    found = surface
    for part in dotted.split("."):
        found = getattr(found, part)
    return found


def classes_in(path):
    """Every class one file declares, including one inside another."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]


def test_the_method_counter_leaves_out_a_signal():
    """The counter reads a signal as a method, so it over-counts."""
    app()
    from src.gui import launcher

    card = vars(launcher.ModeCard)
    assert "clicked" in card
    assert type(card["clicked"]).__name__ == "Signal"
    assert callable(card["clicked"])
    assert "clicked" not in members(launcher.ModeCard)
    assert members(launcher.ModeCard) == {"__init__", "mousePressEvent"}
    assert "staticMetaObject" not in members(launcher.ModeCard)


def test_the_method_counter_finds_a_factory_and_a_read_only_value():
    """The counter misses a factory or a read-only value.

    Python reports a factory as callable and a read-only value as not
    callable, so a plain callable test gets one of the two wrong.
    """
    app()
    from src.gui import indicator_panel

    panel = vars(indicator_panel.IndicatorVotingPanel)
    assert isinstance(panel["_reading_fingerprint"], staticmethod)
    assert isinstance(panel["lock_timeframe"], property)
    assert callable(panel["_reading_fingerprint"])
    assert not callable(panel["lock_timeframe"])
    found = members(indicator_panel.IndicatorVotingPanel)
    assert "_reading_fingerprint" in found
    assert "lock_timeframe" in found
    assert "selected_bot_id" in found
    assert "snapshots" in members(surface.RiskManagerSnapshot)
    assert "alerts" in members(surface.RiskManagerSnapshot)
    assert isinstance(vars(surface.RiskManagerSnapshot)["snapshots"], property)


def test_the_class_counter_finds_a_class_inside_another():
    """The class counter misses a class declared inside another."""
    nested = classes_in(NESTED_CLASS_PATH)
    assert len(nested) == NESTED_CLASS_COUNT == 4
    assert "_StockLogHandler" in nested
    assert "StockMainWindow" in nested
    assert nested.index("StockMainWindow") < nested.index("_StockLogHandler")
    assert classes_in(TAB_PATH) == ["DrawdownGauge", "ExposureBar", "RiskTab"]
    assert len(classes_in(TAB_PATH)) == TAB_CLASS_COUNT == 3


def test_every_shipped_class_and_method_has_a_counterpart():
    """A class or a method exists on one side and nowhere on the other."""
    app()
    assert classes_in(TAB_PATH) == list(CLASS_MAP)
    assert len(CLASS_MAP) == TAB_CLASS_COUNT
    for old_name, new_name in CLASS_MAP.items():
        assert inspect.isclass(getattr(shipped, old_name)), old_name
        assert inspect.isclass(getattr(surface, new_name)), new_name
    assert members(shipped.DrawdownGauge) == {"__init__", "set_value", "paintEvent"}
    assert members(shipped.ExposureBar) == {"__init__", "set_value"}
    assert members(shipped.RiskTab) == {"__init__", "_setup_ui", "refresh"}
    assert {name.split(".")[-1] for name in METHOD_MAP} == (
        members(shipped.DrawdownGauge)
        | members(shipped.ExposureBar)
        | members(shipped.RiskTab)
    )
    assert len(METHOD_MAP) == 8
    for target in METHOD_MAP.values():
        assert callable(resolve(target)), target
    assert members(surface.DrawdownGaugeModel) == GAUGE_MEMBERS
    assert members(surface.ExposureBarModel) == BAR_MEMBERS
    assert members(surface.RiskTabModel) == TAB_MEMBERS
    for target in HELPER_MAP.values():
        assert callable(resolve(target)), target
    assert len(HELPER_MAP) == 26
    for name in SURFACE_ONLY_CLASSES:
        assert inspect.isclass(getattr(surface, name)), name


def test_a_member_added_or_lost_on_either_side_is_reported():
    """The counterpart check passed because it read one side twice."""
    app()
    assert "refresh" in members(shipped.RiskTab)
    assert "paintEvent" in members(shipped.DrawdownGauge)
    assert "logger" not in classes_in(TAB_PATH)
    assert "QWidget" not in classes_in(TAB_PATH)
    with pytest.raises(AttributeError):
        resolve("RiskTabModel.no_such_member")
    assert TAB_MEMBERS - {"refresh"} != TAB_MEMBERS
    assert members(surface.RiskTabModel) - {"setup_ui"} != TAB_MEMBERS
    assert set(METHOD_MAP) - {"RiskTab.refresh"} != set(METHOD_MAP)
    assert set(HELPER_MAP.values()) & TAB_MEMBERS == set()
    assert set(CLASS_MAP.values()) & set(SURFACE_ONLY_CLASSES) == set()


def test_the_signatures_match_the_shipped_methods():
    """A method stopped taking the arguments the window passes it."""
    app()
    for owner, old_name, new_owner, new_name in (
        (shipped.DrawdownGauge, "set_value", surface.DrawdownGaugeModel, "set_value"),
        (shipped.ExposureBar, "set_value", surface.ExposureBarModel, "set_value"),
        (shipped.RiskTab, "refresh", surface.RiskTabModel, "refresh"),
    ):
        old = list(inspect.signature(getattr(owner, old_name)).parameters)
        new = list(inspect.signature(getattr(new_owner, new_name)).parameters)
        assert new == old, old_name
    assert list(inspect.signature(shipped.RiskTab.__init__).parameters) == [
        "self",
        "risk_manager",
        "parent",
    ]
    assert list(inspect.signature(surface.RiskTabModel.__init__).parameters) == [
        "self",
        "risk_manager",
    ]
    gauge = inspect.signature(shipped.DrawdownGauge.set_value).parameters
    assert gauge["max_pct"].default == 25
    assert (
        inspect.signature(surface.DrawdownGaugeModel.set_value)
        .parameters["max_pct"]
        .default
        == 25
    )
    bar = inspect.signature(shipped.ExposureBar.set_value).parameters
    assert bar["color"].default == INFO_HEX
    assert (
        inspect.signature(surface.ExposureBarModel.set_value)
        .parameters["color"]
        .default
        == INFO_HEX
    )
    assert (
        inspect.signature(shipped.RiskTab.refresh).parameters["risk_manager"].default
        is None
    )


# ---------------------------------------------------------------------
# The counters, each proved against a file that really carries one
# ---------------------------------------------------------------------


def count_sites(path, needle):
    """How many times one call appears in one file."""
    return path.read_text(encoding="utf-8").count(needle)


def count_built(path, needle):
    """How many times one class is CONSTRUCTED in one file.

    A name counter reads the import line too, so the construction is
    what is counted.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return len(
        [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == needle
        ]
    )


def screen_elements_built(path):
    """Every screen element one file constructs, in order.

    A layout is not a screen element and a painting tool is not either,
    so the names are taken from what the file imports for the screen and
    from the classes it declares.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module or "") in ("PySide6.QtGui", "PySide6.QtCore"):
                continue
            for alias in node.names:
                found = alias.asname or alias.name
                if found[:1].isupper():
                    names.add(found)
    names = {found for found in names if not found.endswith("Layout")}
    return [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in names
    ]


def test_the_tab_wires_no_signal():
    """A signal wiring appeared on one side and not the other.

    The counter is proved able to report by pointing it at two files
    that really carry one.
    """
    assert count_sites(TAB_PATH, ".connect(") == TAB_CONNECT_SITES == 0
    assert count_sites(SURFACE_PATH, ".connect(") == 0
    assert count_sites(WIRING_CONTROL_PATH, ".connect(") == WIRING_CONTROL_SITES == 1
    assert count_sites(SIGNAL_CONTROL_PATH, ".connect(") == SIGNAL_CONTROL_SITES == 3
    assert surface.ACTIONS == {}
    assert len(surface.ACTIONS) == count_sites(TAB_PATH, ".connect(")
    assert surface.BUTTON_NAMES == ()


def test_the_tab_declares_no_signal():
    """A signal declaration appeared on one side and not the other."""
    assert count_built(TAB_PATH, "Signal") == 0
    assert count_built(SURFACE_PATH, "Signal") == 0
    assert count_built(SIGNAL_CONTROL_PATH, "Signal") == SIGNAL_CONTROL_SITES == 3
    assert count_built(WIRING_CONTROL_PATH, "Signal") == 0
    assert count_sites(SIGNAL_CONTROL_PATH, "Signal") > SIGNAL_CONTROL_SITES


def test_the_tab_starts_no_timer():
    """A wait appeared on one side and not the other.

    The counter counts the construction, not the name, and is proved by
    two files whose basenames are the same and whose counts are not.
    """
    from PySide6.QtCore import QObject, QTimer

    app()
    assert count_built(TAB_PATH, "QTimer") == TAB_TIMER_SITES == 0
    assert count_built(SURFACE_PATH, "QTimer") == 0
    assert count_built(TIMER_CONTROL_PATH, "QTimer") == TIMER_CONTROL_SITES == 1
    assert count_built(TIMER_QUIET_PATH, "QTimer") == TIMER_QUIET_SITES == 0
    assert TIMER_CONTROL_PATH.name == TIMER_QUIET_PATH.name
    assert count_sites(TIMER_CONTROL_PATH, "QTimer") > TIMER_CONTROL_SITES
    started: list = []
    first_start_timer = QObject.startTimer
    first_timer_start = QTimer.start
    first_single_shot = QTimer.singleShot

    def watch_start_timer(self, *args, **kwargs):
        started.append(("startTimer", args))
        return first_start_timer(self, *args, **kwargs)

    def watch_timer_start(self, *args, **kwargs):
        started.append(("QTimer.start", args))
        return first_timer_start(self, *args, **kwargs)

    def watch_single_shot(*args, **kwargs):
        started.append(("singleShot", args))
        return first_single_shot(*args, **kwargs)

    QObject.startTimer = watch_start_timer
    QTimer.start = watch_timer_start
    QTimer.singleShot = watch_single_shot
    try:
        for name in ("happy", "empty"):
            old_picture_tab(name)
            new_picture_tab(name)
        observed = list(started)
        started.clear()
        QTimer().start(250)
    finally:
        QObject.startTimer = first_start_timer
        QTimer.start = first_timer_start
        QTimer.singleShot = first_single_shot
    assert started == [("QTimer.start", (250,))]
    assert observed == []
    assert surface.TIMERS == {}
    assert surface.TIMER_DELAYS_MS == ()
    assert len(surface.TIMERS) == len(observed) == 0


def test_the_tab_subscribes_to_no_bus_topic():
    """A bus wiring appeared on one side and not the other."""
    assert count_sites(TAB_PATH, ".subscribe(") == TAB_BUS_SITES == 0
    assert count_sites(SURFACE_PATH, ".subscribe(") == 0
    assert count_sites(BUS_CONTROL_PATH, ".subscribe(") == BUS_CONTROL_SITES == 2
    assert surface.BUS_TOPICS == ()
    assert len(surface.BUS_TOPICS) == count_sites(TAB_PATH, ".subscribe(")


def test_the_screen_elements_the_tab_builds_are_counted():
    """The element counter reads a name instead of a construction."""
    built = screen_elements_built(TAB_PATH)
    assert len(built) == TAB_ELEMENTS_BUILT == 21
    assert built.count("QLabel") == 6
    assert built.count("QGroupBox") == 4
    assert built.count("QTableWidget") == 2
    assert built.count("ExposureBar") == 2
    assert built.count("DrawdownGauge") == 1
    assert "QPainter" not in built
    assert "QColor" not in built
    assert "QVBoxLayout" not in built
    control = screen_elements_built(ELEMENT_CONTROL_PATH)
    assert len(control) == ELEMENT_CONTROL_BUILT == 3
    assert control == ["QLabel", "QLabel", "PrivacyDot"]
    made = screen_elements_built(SURFACE_PATH)
    assert [found for found in made if found.startswith("Q")] == []
    assert "RiskTabModel" in made


def layout_entries(layout):
    """Every direct entry of one layout, in the order it was added."""
    found = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item.widget() is not None:
            found.append(item.widget())
        elif item.layout() is not None:
            found.append(item.layout())
        else:
            found.append("stretch")
    return found


def entry_kinds(layout):
    """The class name of each entry of one layout, in order."""
    return [
        entry if isinstance(entry, str) else entry.metaObject().className()
        for entry in layout_entries(layout)
    ]


def test_the_widget_tree_is_the_tabs_own():
    """A widget appeared on one side, or moved to another parent."""
    from PySide6.QtWidgets import QGroupBox, QProgressBar, QTableWidget

    app()
    tab = old_picture_tab("empty")
    model = surface.RiskTabModel()
    built = model.setup_ui()
    assert [node["name"] for node in built] == list(surface.WIDGET_NAMES)
    assert len(built) == 19
    assert model.calls[0] == ["setup.start"]
    assert model.calls[-1] == ["setup.return", 19]
    assert surface.WIDGET_CHILDREN["main_split"] == ("left", "right")
    assert surface.WIDGET_CHILDREN["left"] == (
        "gauge_row",
        "asset_group",
        "exchange_group",
        "left_stretch",
    )
    assert surface.WIDGET_CHILDREN["gauge_row"] == ("dd_gauge", "metrics")
    assert surface.WIDGET_CHILDREN["right"] == ("alerts_group", "rules_group")
    assert surface.WIDGET_CHILDREN["alerts_group"] == ("alerts_table",)
    assert surface.WIDGET_PARENTS["rules_table"] == "rules_group"
    assert surface.WIDGET_KINDS["dd_gauge"] == "DrawdownGauge"
    assert surface.WIDGET_INDEX["status_label"] == 0
    assert surface.WIDGET_INDEX["bots_label"] == 3
    assert surface.WIDGET_INDEX["left_stretch"] == 3
    assert surface.TABLE_NAMES == ("alerts_table", "rules_table")
    assert len(tab.findChildren(QGroupBox)) == 4
    assert len(tab.findChildren(QTableWidget)) == 2
    assert len(tab.findChildren(QProgressBar)) == 0
    assert {group.title() for group in tab.findChildren(QGroupBox)} == {
        "Asset Exposure",
        "Exchange Exposure",
        "Risk Alerts",
        "Risk Rules",
    }
    assert entry_kinds(tab.layout()) == ["QSplitter"]
    split = layout_entries(tab.layout())[0]
    left, right = split.widget(0), split.widget(1)
    assert entry_kinds(left.layout()) == [
        "QHBoxLayout",
        "QGroupBox",
        "QGroupBox",
        "stretch",
    ]
    assert entry_kinds(right.layout()) == ["QGroupBox", "QGroupBox"]
    assert [group.title() for group in layout_entries(left.layout())[1:3]] == [
        "Asset Exposure",
        "Exchange Exposure",
    ]
    assert [group.title() for group in layout_entries(right.layout())] == [
        "Risk Alerts",
        "Risk Rules",
    ]
    gauge_row = layout_entries(left.layout())[0]
    assert entry_kinds(gauge_row) == ["DrawdownGauge", "QVBoxLayout"]
    assert entry_kinds(layout_entries(gauge_row)[1]) == [
        "QLabel",
        "QLabel",
        "QLabel",
        "QLabel",
        "stretch",
    ]
    assert list(surface.WIDGET_KINDS.values()).count("QGroupBox") == 4
    bars = old_picture_tab("asset_bands")
    assert len(bars.findChildren(QProgressBar)) == 3


def test_the_surface_loads_no_qt_module():
    """The surface grew an import that pulls Qt into the backend."""
    tree = ast.parse(SURFACE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
            else:
                imported.update(alias.name for alias in node.names)
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    assert imported == {"__future__", "time", "typing", "design_system"}
    tab_imports = {
        (node.module or "")
        for node in ast.walk(ast.parse(TAB_PATH.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    assert any(name.startswith("PySide6") for name in tab_imports), tab_imports


# ---------------------------------------------------------------------
# The surface holds its own values
# ---------------------------------------------------------------------


def moved_fields(left, right):
    """Every field whose value differs between two readings of one case."""
    return sorted(key for key in left if left[key] != right[key])


def test_the_surface_does_not_follow_a_value_changed_in_the_shipped_tab():
    """The surface reads its values from the shipped tab, not from itself.

    The colour the shipped tab reads is changed while the run is going.
    The shipped side moves; the surface does not; and the comparison
    names exactly the fields that moved and nothing else.
    """
    from src.gui import design_system

    app()
    before_old = product_only(old_refresh("happy")["state"])
    before_new = product_only(new_refresh("happy")["state"])
    assert moved_fields(before_old, before_new) == []
    first = design_system.SUCCESS
    design_system.SUCCESS = "#123456"
    try:
        after_old = product_only(old_refresh("happy")["state"])
        after_new = product_only(new_refresh("happy")["state"])
    finally:
        design_system.SUCCESS = first
    assert design_system.SUCCESS == SUCCESS_HEX
    assert moved_fields(after_new, before_new) == []
    assert moved_fields(after_old, before_old) == ["peak_style", "rule_rows"]
    assert after_old["peak_style"] == "color: #123456; font-size: 13px;"
    assert after_new["peak_style"] == f"color: {SUCCESS_HEX}; font-size: 13px;"
    assert moved_fields(after_old, after_new) == ["peak_style", "rule_rows"]
    restored = product_only(old_refresh("happy")["state"])
    assert moved_fields(restored, before_old) == []


def test_the_moved_field_report_names_nothing_when_nothing_moved():
    """The field report names a field whatever the two sides hold."""
    one = product_only(old_refresh("happy")["state"])
    same = product_only(old_refresh("happy")["state"])
    assert moved_fields(one, same) == []
    other = product_only(old_refresh("empty")["state"])
    assert moved_fields(one, other) != []
    assert "peak_style" not in moved_fields(one, other)
    assert "rule_rows" in moved_fields(one, other)


# ---------------------------------------------------------------------
# Every value reaches the compared snapshot
# ---------------------------------------------------------------------


def normalise(value):
    """One value with every tuple turned into a list."""
    if isinstance(value, (tuple, list)):
        return [normalise(item) for item in value]
    if isinstance(value, dict):
        return {key: normalise(item) for key, item in value.items()}
    return value


def freeze(value):
    """One value as a single comparable string."""
    return json.dumps(normalise(value), sort_keys=True, default=str)


def surface_constants():
    """Every value the surface exports, by name."""
    found = {}
    for name, value in vars(surface).items():
        if name.startswith("_"):
            continue
        if inspect.isfunction(value) or inspect.isclass(value):
            continue
        if inspect.ismodule(value):
            continue
        if getattr(value, "__module__", "") in ("typing", "__future__"):
            continue
        if isinstance(value, surface.RiskTabModel):
            continue
        found[name] = value
    return found


def payload_values(payloads):
    """Every value any of these payloads carries, frozen for comparison."""
    found = set()

    def walk(value):
        found.add(freeze(value))
        if isinstance(value, dict):
            for key, item in value.items():
                found.add(freeze(key))
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for payload in payloads:
        walk(payload)
    return found


def compared_payloads():
    """The payloads the completeness check reads, one per driven path."""
    payloads = []
    for name in (
        "happy",
        "empty",
        "critical_status",
        "warning_status",
        "asset_bands",
        "exchange_bands",
        "disabled_rule",
        "zero_total_exposure",
    ):
        model = surface.RiskTabModel(make_manager(name))
        model.setup_ui()
        payloads.append(surface.build_view_model(model, action="refresh"))
    lonely = surface.RiskTabModel(None)
    payloads.append(surface.build_view_model(lonely, action="refresh"))
    sized = surface.RiskTabModel(make_manager("happy"))
    sized.gauge.set_value(20.0, 25)
    payloads.append(surface.build_view_model(sized, gauge_size=(200, 200)))
    return payloads


COVERED_ELSEWHERE = {
    "STATUS_WARNING_TEXT": "test_the_status_line_is_the_shipped_tabs_own",
    "STATUS_WARNING_STYLE": "test_the_status_line_is_the_shipped_tabs_own",
    "GAUGE_START_VALUE": "test_the_gauge_takes_the_drawdown_and_keeps_its_ceiling",
    "GAUGE_SAFE_COLOR": "test_the_gauge_bands_change_where_the_shipped_gauge_changes_them",
    "GAUGE_WARNING_COLOR": (
        "test_the_gauge_bands_change_where_the_shipped_gauge_changes_them"
    ),
    "GAUGE_DANGER_COLOR": (
        "test_the_gauge_bands_change_where_the_shipped_gauge_changes_them"
    ),
    "BAR_BAND_INFO": "test_the_exposure_bars_are_the_shipped_tabs_own",
    "BAR_BAND_WARNING": "test_the_exposure_bars_are_the_shipped_tabs_own",
    "BAR_BAND_DANGER": "test_the_exposure_bars_are_the_shipped_tabs_own",
    "GAUGE_BAND_SAFE": "test_the_gauge_bands_change_where_the_shipped_gauge_changes_them",
    "GAUGE_BAND_WARNING": (
        "test_the_gauge_bands_change_where_the_shipped_gauge_changes_them"
    ),
    "GAUGE_BAND_DANGER": (
        "test_the_gauge_bands_change_where_the_shipped_gauge_changes_them"
    ),
    "STATUS_STATE_MONITORING": "test_the_status_line_is_the_shipped_tabs_own",
    "STATUS_STATE_WARNING": "test_the_status_line_is_the_shipped_tabs_own",
    "STATUS_STATE_CRITICAL": "test_the_status_line_is_the_shipped_tabs_own",
    "REFRESH_PATH_NO_MANAGER": "test_a_manager_that_reads_as_nothing_is_skipped_on_both_sides",
    "REFRESH_PATH_PAINTED": "test_every_case_reaches_the_path_it_names",
    "SETUP_START": "test_the_widget_tree_is_the_tabs_own",
    "SETUP_RETURN": "test_the_widget_tree_is_the_tabs_own",
    "GAUGE_SET": "test_the_recorded_calls_are_compared_as_values",
    "GAUGE_PAINT": "test_a_gauge_paint_that_stops_part_way_keeps_the_arc_it_drew",
    "BAR_SET": "test_the_recorded_calls_are_compared_as_values",
    "BAR_ADD": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_START": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_STATUS": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_GAUGE": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_METRICS": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_STATE": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_SNAPSHOT": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_ASSETS": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_EXCHANGES": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_ALERTS": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_RULES": "test_the_recorded_calls_are_compared_as_values",
    "REFRESH_RETURN": "test_the_recorded_calls_are_compared_as_values",
    "SEVERITY_CRITICAL": "test_a_severity_in_the_wrong_capitals_is_not_critical",
    "RULE_KEY_THRESHOLD": "test_the_threshold_is_printed_to_one_decimal",
    "RULE_KEY_ACTION": "test_the_rule_row_is_the_shipped_tabs_own",
    "RULE_KEY_ENABLED": "test_the_rule_row_is_the_shipped_tabs_own",
    "STATUS_KEY_DRAWDOWN": "test_the_gauge_takes_the_drawdown_and_keeps_its_ceiling",
    "STATUS_KEY_PEAK": "test_the_metric_lines_are_the_shipped_tabs_own",
    "STATUS_KEY_EXPOSURE": "test_the_metric_lines_are_the_shipped_tabs_own",
    "STATUS_KEY_CRITICAL": "test_the_status_line_is_the_shipped_tabs_own",
    "STATUS_KEY_ALERTS_HOUR": "test_the_status_line_is_the_shipped_tabs_own",
    "STATUS_KEY_RULES": "test_the_rule_row_is_the_shipped_tabs_own",
    "GAUGE_VALUE_FONT_WEIGHT": "test_the_gauge_draws_what_the_shipped_gauge_draws",
    "GAUGE_LABEL_FONT_WEIGHT": "test_the_gauge_draws_what_the_shipped_gauge_draws",
    "GAUGE_VALUE_ALIGNMENT": "test_the_gauge_draws_what_the_shipped_gauge_draws",
    "GAUGE_LABEL_ALIGNMENT": "test_the_gauge_draws_what_the_shipped_gauge_draws",
    "BAR_VALUE_ALIGNMENT": (
        "test_the_bar_widths_and_alignment_are_compared_as_the_request"
    ),
    "CELL_ALIGNMENT": "test_the_refresh_is_the_shipped_tabs_refresh",
    "HEADER_RESIZE_MODE": "test_the_table_settings_are_compared_as_values",
    "SPLITTER_ORIENTATION": "test_the_splitter_sizes_are_compared_as_the_request",
    "RENDER_HINT": "test_the_gauge_draws_what_the_shipped_gauge_draws",
    "TABLE_NAMES": "test_the_widget_tree_is_the_tabs_own",
    "BUTTON_NAMES": "test_the_tab_wires_no_signal",
    "METRIC_BUILD_ORDER": "test_the_metric_build_order_is_compared_as_a_value",
}


def missing_from_payload(constants, values):
    """Every exported value the payloads do not carry, by name."""
    return sorted(
        name
        for name, value in constants.items()
        if freeze(value) not in values and name not in COVERED_ELSEWHERE
    )


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface ships is never compared against the shipped tab."""
    constants = surface_constants()
    assert len(constants) > 100
    values = payload_values(compared_payloads())
    assert missing_from_payload(constants, values) == []
    for name in COVERED_ELSEWHERE.values():
        assert callable(globals()[name]), name


def test_the_completeness_check_reports_a_value_that_slipped_through():
    """The completeness check passes whatever the surface stops exporting."""
    values = payload_values(compared_payloads())
    constants = surface_constants()
    constants["A_VALUE_NO_PAYLOAD_CARRIES"] = "a-value-no-payload-carries"
    assert missing_from_payload(constants, values) == ["A_VALUE_NO_PAYLOAD_CARRIES"]
    thinned = payload_values([{"method": surface.METHOD}])
    slipped = missing_from_payload(surface_constants(), thinned)
    assert "ALERT_COLUMNS" in slipped
    assert "GROUP_BOX_STYLE" in slipped
    assert len(slipped) > 50


PAYLOAD_KEY_SOURCES = {
    "method": ("METHOD",),
    "accessible_name": ("ACCESSIBLE_NAME",),
    "widgets": ("WIDGETS",),
    "widget_names": ("WIDGET_NAMES",),
    "widget_kinds": ("WIDGET_KINDS",),
    "widget_parents": ("WIDGET_PARENTS",),
    "widget_children": ("WIDGET_CHILDREN",),
    "widget_index": ("WIDGET_INDEX",),
    "table_names": ("TABLE_NAMES",),
    "button_names": ("BUTTON_NAMES",),
    "metric_build_order": ("METRIC_BUILD_ORDER",),
    "content_margins": ("CONTENT_MARGINS",),
    "content_spacing": ("CONTENT_SPACING",),
    "pane_margins": ("PANE_MARGINS",),
    "bar_margins": ("BAR_MARGINS",),
    "splitter_orientation": ("SPLITTER_ORIENTATION",),
    "splitter_orientation_value": ("SPLITTER_ORIENTATION_VALUE",),
    "splitter_handle_width": ("SPLITTER_HANDLE_WIDTH",),
    "splitter_children_collapsible": ("SPLITTER_CHILDREN_COLLAPSIBLE",),
    "splitter_sizes": ("SPLITTER_SIZES",),
    "stretches": (
        "METRICS_STRETCH",
        "ALERTS_STRETCH",
        "RULES_STRETCH",
        "BAR_STRETCH",
    ),
    "group_titles": (
        "ASSET_GROUP_TITLE",
        "EXCHANGE_GROUP_TITLE",
        "ALERTS_GROUP_TITLE",
        "RULES_GROUP_TITLE",
    ),
    "alert_columns": ("ALERT_COLUMNS",),
    "rule_columns": ("RULE_COLUMNS",),
    "alert_column_count": ("ALERT_COLUMN_COUNT",),
    "rule_column_count": ("RULE_COLUMN_COUNT",),
    "header_resize_mode": ("HEADER_RESIZE_MODE",),
    "header_resize_value": ("HEADER_RESIZE_VALUE",),
    "alternating_row_colors": ("ALTERNATING_ROW_COLORS",),
    "vertical_header_visible": ("VERTICAL_HEADER_VISIBLE",),
    "edit_triggers_none": ("EDIT_TRIGGERS_NONE",),
    "edit_triggers_none_value": ("EDIT_TRIGGERS_NONE_VALUE",),
    "edit_triggers_default": ("EDIT_TRIGGERS_DEFAULT",),
    "edit_triggers_default_value": ("EDIT_TRIGGERS_DEFAULT_VALUE",),
    "cell_alignment": ("CELL_ALIGNMENT",),
    "cell_alignment_value": ("CELL_ALIGNMENT_VALUE",),
    "no_color": ("NO_COLOR",),
    "no_alignment": ("NO_ALIGNMENT",),
    "gauge": ("GAUGE_MARGIN",),
    "bar": ("BAR_LABEL_MIN_WIDTH",),
    "styles": ("GROUP_BOX_STYLE",),
    "texts": ("PEAK_FORMAT",),
    "status_states": ("STATUS_STATES",),
    "status_lines": ("STATUS_LINES",),
    "status_keys": ("STATUS_KEYS",),
    "status_default_number": ("STATUS_DEFAULT_NUMBER",),
    "rule_keys": ("RULE_KEYS",),
    "alert_window_s": ("ALERT_WINDOW_S",),
    "message_max_chars": ("MESSAGE_MAX_CHARS",),
    "severity_critical": ("SEVERITY_CRITICAL",),
    "severity_column": ("SEVERITY_COLUMN",),
    "severity_critical_color": ("SEVERITY_CRITICAL_COLOR",),
    "severity_other_color": ("SEVERITY_OTHER_COLOR",),
    "enabled_column": ("ENABLED_COLUMN",),
    "enabled_color": ("ENABLED_COLOR",),
    "disabled_color": ("DISABLED_COLOR",),
    "refresh_paths": ("REFRESH_PATHS",),
    "no_path": ("NO_PATH",),
    "actions": ("ACTIONS",),
    "timers": ("TIMERS",),
    "timer_delays_ms": ("TIMER_DELAYS_MS",),
    "bus_topics": ("BUS_TOPICS",),
    "skin": ("SKIN",),
    "tab_style_sheet": ("TAB_STYLE_SHEET",),
    "status_text": ("model.status_text",),
    "status_style": ("model.status_style",),
    "status_state": ("model.status_state",),
    "peak_text": ("model.peak_text",),
    "peak_style": ("model.peak_style",),
    "exposure_text": ("model.exposure_text",),
    "exposure_style": ("model.exposure_style",),
    "bots_text": ("model.bots_text",),
    "bots_style": ("model.bots_style",),
    "asset_bars": ("model.asset_bars",),
    "exchange_bars": ("model.exchange_bars",),
    "alert_rows": ("model.alert_rows",),
    "rule_rows": ("model.rule_rows",),
    "gauge_paint": ("model.gauge",),
    "refresh_path": ("model.refresh_path",),
    "has_manager": ("model.manager",),
    "calls": ("model.calls",),
}

# Payload keys whose value is a group of readings rather than one
# named value. Each is checked by one reading inside it.
GROUPED_KEYS = {
    "gauge": ("margin", surface.GAUGE_MARGIN),
    "bar": ("label_min_width", surface.BAR_LABEL_MIN_WIDTH),
    "styles": ("group_box", surface.GROUP_BOX_STYLE),
    "texts": ("peak_format", surface.PEAK_FORMAT),
}


def resolve_source(name, model):
    """The value one named source holds, on the surface or on the model."""
    if name.startswith("model."):
        return getattr(model, name.split(".", 1)[1])
    return getattr(surface, name)


def backed(key, value, sources, model):
    """Whether one payload key carries exactly what its named sources hold."""
    if key in GROUPED_KEYS:
        inner, expected = GROUPED_KEYS[key]
        return freeze(value[inner]) == freeze(expected)
    if key == "has_manager":
        return value is (resolve_source(sources[0], model) is not None)
    if key in ("asset_bars", "exchange_bars"):
        held = resolve_source(sources[0], model)
        return [item["label"] for item in value] == [bar.label for bar in held.values()]
    if key == "gauge_paint":
        held = resolve_source(sources[0], model)
        return value["steps"] == [dict(step) for step in held.painted]
    resolved = [resolve_source(name, model) for name in sources]
    if len(sources) == 1:
        return freeze(value) == freeze(resolved[0])
    if isinstance(value, dict):
        return sorted(freeze(item) for item in value.values()) == sorted(
            freeze(item) for item in resolved
        )
    return [freeze(item) for item in value] == [freeze(item) for item in resolved]


def test_no_snapshot_key_exists_that_no_value_backs():
    """A payload key carries something no named surface value holds."""
    model = surface.RiskTabModel(make_manager("happy"))
    payload = surface.build_view_model(model, action="refresh")
    assert set(payload) == set(PAYLOAD_KEY_SOURCES)
    assert len(payload) == 81
    for key, sources in PAYLOAD_KEY_SOURCES.items():
        for name in sources:
            if name.startswith("model."):
                assert hasattr(model, name.split(".", 1)[1]), name
            else:
                assert hasattr(surface, name), name
        assert backed(key, payload[key], sources, model), key


def test_the_key_check_reports_a_key_backed_by_the_wrong_value():
    """The key check passes whatever a payload key carries."""
    model = surface.RiskTabModel(make_manager("happy"))
    payload = surface.build_view_model(model, action="refresh")
    assert backed(
        "cell_alignment", payload["cell_alignment"], ("CELL_ALIGNMENT",), model
    )
    assert not backed("cell_alignment", "AlignLeft", ("CELL_ALIGNMENT",), model)
    assert not backed("alert_columns", ["Time"], ("ALERT_COLUMNS",), model)
    assert not backed("skin", {"a": "b"}, ("SKIN",), model)
    assert not backed("gauge", {"margin": 99}, ("GAUGE_MARGIN",), model)
    assert not backed("has_manager", False, ("model.manager",), model)


def test_every_case_reaches_the_path_it_names():
    """A case stopped reaching the path it stands for."""
    reached = {}
    refused = set()
    for name in REFRESH_CASES:
        model, outcome = new_refresh_model(name)
        reached[name] = model.refresh_path
        if outcome["error"]:
            refused.add(name)
    assert refused == set(REFRESH_REFUSING)
    assert reached["happy"] == surface.REFRESH_PATH_PAINTED
    assert reached["falsy_manager"] == surface.REFRESH_PATH_NO_MANAGER
    for name in REFRESH_REFUSING:
        assert reached[name] == surface.NO_PATH, name
    assert set(reached.values()) == {
        surface.NO_PATH,
        surface.REFRESH_PATH_NO_MANAGER,
        surface.REFRESH_PATH_PAINTED,
    }
    assert set(surface.REFRESH_PATHS) == {
        surface.REFRESH_PATH_NO_MANAGER,
        surface.REFRESH_PATH_PAINTED,
    }


def test_every_case_table_is_driven():
    """A case table sits in the file and nothing ever drives it."""
    driven = {
        "REFRESH_CASES": set(REFRESH_CASES),
        "GAUGE_CASES": set(GAUGE_CASES),
        "SEQUENCE_CASES": set(SEQUENCE_CASES),
        "PICTURE_CASES": set(PICTURE_CASES),
        "REFRESH_REFUSING": set(REFRESH_REFUSING),
        "GAUGE_REFUSING": set(GAUGE_REFUSING),
        "REFUSAL_TYPES": set(REFUSAL_TYPES),
        "GAUGE_REFUSAL_TYPES": set(GAUGE_REFUSAL_TYPES),
    }
    assert driven["REFRESH_REFUSING"] < driven["REFRESH_CASES"]
    assert driven["REFUSAL_TYPES"] == driven["REFRESH_REFUSING"]
    assert driven["GAUGE_REFUSING"] < driven["GAUGE_CASES"]
    assert driven["GAUGE_REFUSAL_TYPES"] == driven["GAUGE_REFUSING"]
    assert driven["PICTURE_CASES"] < driven["REFRESH_CASES"]
    for names in SEQUENCE_CASES.values():
        for name in names:
            assert name in REFRESH_CASES, name
    assert len(driven["REFRESH_CASES"]) == 42
    assert len(driven["GAUGE_CASES"]) == 16
    assert len(driven["SEQUENCE_CASES"]) == 8
    assert len(driven["PICTURE_CASES"]) == 13


# ---------------------------------------------------------------------
# The tab writes nothing outside itself
# ---------------------------------------------------------------------


def test_the_shipped_tab_leaves_no_shared_state_changed():
    """A refresh changed something outside the tab, so the run order matters."""
    from src.gui import design_system

    app()
    before = {
        name: getattr(design_system, name)
        for name in ("SUCCESS", "ERROR", "WARNING", "PRIMARY", "STATUS_INFO")
    }
    tab = new_tab(make_manager("happy"))
    tab.refresh()
    surface.RiskTabModel(make_manager("happy")).refresh()
    after = {name: getattr(design_system, name) for name in before}
    assert after == before
    assert surface.WIDGETS[0]["accessible_name"] == "Risk Tab"
    assert surface.TAB_MODEL.refresh_path in ("", "painted", "no_manager")


def test_the_bridge_model_is_put_back_by_a_reset():
    """The one model the bridge keeps carried a case into the next test."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    desktop_bridge.handle_line(
        json.dumps({"id": 1, "method": surface.METHOD, "params": {"reset": True}}),
        registry,
    )
    assert surface.TAB_MODEL.refresh_path == ""
    assert surface.TAB_MODEL.asset_bars == {}
    assert surface.TAB_MODEL.calls == []


# ---------------------------------------------------------------------
# The bridge
# ---------------------------------------------------------------------


BRIDGE_MANAGER = {
    "status": {
        "drawdown_pct": 12.5,
        "peak_pnl": 1234.5678,
        "total_exposure": 4500.25,
        "critical_alerts": 1,
        "alerts_1h": 3,
        "rules": {
            "max_drawdown": {"threshold": 15.0, "action": "warn", "enabled": True}
        },
    },
    "snapshots": [
        {
            "running_count": 4,
            "total_exposure": 1000.0,
            "asset_exposures": {"BTC": 500.0},
            "exchange_exposures": {"coinbase": 700.0},
        }
    ],
    "alerts": [
        {
            "timestamp": RECENT_STAMP,
            "severity": "critical",
            "rule_name": "max_drawdown",
            "message": "drawdown 12.5% over 10.0%",
            "action_taken": "pause_bot",
        }
    ],
}


def test_view_model_is_json_serialisable():
    """The bridge cannot encode what the surface returns."""
    model = surface.RiskTabModel(make_manager("happy"))
    payload = surface.build_view_model(model, action="refresh")
    encoded = json.loads(json.dumps(payload))
    assert encoded["method"] == "risk_tab.state"
    assert encoded["accessible_name"] == "Risk Tab"
    assert encoded["status_text"] == "STATUS: WARNING"
    assert encoded["peak_text"] == "Peak P/L: $1,234.5678"
    assert encoded["exposure_text"] == "Total Exposure: $4,500.25"
    assert encoded["bots_text"] == "Running Bots: 4"
    assert encoded["refresh_path"] == "painted"
    assert encoded["alert_columns"] == ["Time", "Severity", "Rule", "Message", "Action"]
    assert encoded["rule_columns"] == ["Rule", "Threshold", "Action", "Enabled"]
    assert encoded["cell_alignment_value"] == 132
    assert encoded["splitter_sizes"] == [400, 500]
    assert encoded["actions"] == {}
    assert encoded["timers"] == {}
    assert encoded["bus_topics"] == []
    assert encoded["skin"] == {}
    assert len(encoded["widgets"]) == 19
    assert len(encoded["asset_bars"]) == 2
    assert encoded["gauge"]["value"] == 12.5
    assert encoded["gauge_paint"]["band"] == "warning"
    assert len(encoded["gauge_paint"]["steps"]) == 4
    assert [call[0] for call in encoded["calls"]][-1] == "refresh.return"


def test_bridge_registers_the_risk_tab_method():
    """The renderer cannot reach the risk tab through the bridge."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert surface.METHOD == "risk_tab.state"
    assert registry[surface.METHOD] is surface.view_model
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 71,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "manager": BRIDGE_MANAGER,
                    "action": "refresh",
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is True
    result = answer["result"]
    assert result["status_text"] == "STATUS: CRITICAL"
    assert result["bots_text"] == "Running Bots: 4"
    assert len(result["alert_rows"]) == 1
    assert len(result["rule_rows"]) == 1
    assert result["alert_rows"][0][1]["text"] == "CRITICAL"
    assert result["rule_rows"][0][0]["text"] == "Max Drawdown"
    assert result["asset_bars"][0]["label"] == "BTC"
    assert result["exchange_bars"][0]["label"] == "Coinbase"
    desktop_bridge.handle_line(
        json.dumps({"id": 72, "method": surface.METHOD, "params": {"reset": True}}),
        registry,
    )


def test_the_bridge_keeps_the_bars_until_a_reset():
    """The surface forgot the bars it grew between two bridge calls."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()

    def call(params):
        return desktop_bridge.handle_line(
            json.dumps({"id": 73, "method": surface.METHOD, "params": params}),
            registry,
        )["result"]

    first = call({"reset": True, "manager": BRIDGE_MANAGER, "action": "refresh"})
    assert len(first["asset_bars"]) == 1
    kept = call({})
    assert len(kept["asset_bars"]) == 1
    assert kept["refresh_path"] == "painted"
    fresh = call({"reset": True})
    assert fresh["asset_bars"] == []
    assert fresh["refresh_path"] == ""
    assert fresh["has_manager"] is False
    sized = call(
        {
            "reset": True,
            "manager": BRIDGE_MANAGER,
            "action": "refresh",
            "gauge_size": [200, 200],
        }
    )
    assert sized["gauge_paint"]["size"] == 200
    assert sized["gauge_paint"]["rect_size"] == 170
    call({"reset": True})


def test_a_bad_request_over_the_bridge_becomes_an_error_frame():
    """A request the surface cannot answer ended the bridge session."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    answer = desktop_bridge.handle_line(
        json.dumps(
            {
                "id": 74,
                "method": surface.METHOD,
                "params": {
                    "reset": True,
                    "manager": {"status": []},
                    "action": "refresh",
                },
            }
        ),
        registry,
    )
    assert answer["ok"] is False
    assert answer["error"]["type"] == "AttributeError"
    assert answer["id"] == 74
    desktop_bridge.handle_line(
        json.dumps({"id": 75, "method": surface.METHOD, "params": {"reset": True}}),
        registry,
    )


# ---------------------------------------------------------------------
# Without Qt at all
# ---------------------------------------------------------------------

BLOCK_QT = (
    "import sys\n"
    "import importlib.abc\n"
    "class _Refuse(importlib.abc.MetaPathFinder):\n"
    "    def find_spec(self, name, path=None, target=None):\n"
    "        if name == 'PySide6' or name.startswith('PySide6.'):\n"
    "            raise ImportError('PySide6 blocked')\n"
    "        return None\n"
    "sys.meta_path.insert(0, _Refuse())\n"
)

BRIDGE_PROBE = (
    "import json, sys;"
    "from src.core import desktop_bridge;"
    "frame = desktop_bridge.handle_line("
    "json.dumps({'id': 1, 'method': 'risk_tab.state',"
    " 'params': {'reset': True}}),"
    " desktop_bridge.build_registry());"
    "print(json.dumps({'frame': frame, 'qt': 'PySide6' in sys.modules}))"
)

HEADLESS_PROBE = (
    BLOCK_QT + "import json, sys\n"
    "from src.gui.main_tabs import risk_tab_surface as s\n"
    "manager = s.build_manager({'status': {'drawdown_pct': 12.5,\n"
    "    'peak_pnl': 1234.5678, 'total_exposure': 4500.25,\n"
    "    'critical_alerts': 1, 'alerts_1h': 3,\n"
    "    'rules': {'max_drawdown': {'threshold': 15.0,\n"
    "    'action': 'warn', 'enabled': True}}},\n"
    "    'snapshots': [{'running_count': 4, 'total_exposure': 1000.0,\n"
    "    'asset_exposures': {'BTC': 500.0},\n"
    "    'exchange_exposures': {'coinbase': 700.0}}],\n"
    "    'alerts': [{'timestamp': %r, 'severity': 'critical',\n"
    "    'rule_name': 'max_drawdown', 'message': 'over the limit',\n"
    "    'action_taken': 'pause_bot'}]})\n"
    "model = s.RiskTabModel(manager)\n"
    "painted = model.refresh()\n"
    "drawn = model.gauge.paint(160, 160)\n"
    "print(json.dumps({'qt': 'PySide6' in sys.modules,\n"
    "    'status': painted['status_text'], 'peak': painted['peak_text'],\n"
    "    'exposure': painted['exposure_text'], 'bots': painted['bots_text'],\n"
    "    'alerts': painted['alert_rows'], 'rules': painted['rule_rows'],\n"
    "    'asset_bars': painted['asset_bars'],\n"
    "    'exchange_bars': painted['exchange_bars'],\n"
    "    'band': drawn['band'], 'steps': len(drawn['steps']),\n"
    "    'refresh_path': model.refresh_path, 'widgets': len(s.WIDGETS),\n"
    "    'calls': len(model.calls)}))\n" % RECENT_STAMP
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
    return json.loads(done.stdout.decode().splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the risk tab pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] is False
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["method"] == "risk_tab.state"
    assert result["accessible_name"] == "Risk Tab"
    assert result["alert_columns"] == ["Time", "Severity", "Rule", "Message", "Action"]
    assert result["splitter_sizes"] == [400, 500]
    assert result["cell_alignment_value"] == 132
    assert result["alert_rows"] == []
    assert result["rule_rows"] == []
    assert len(result["widgets"]) == 19


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore;" + BRIDGE_PROBE)
    assert loaded["qt"] is True
    assert loaded["frame"]["ok"] is True


def test_the_surface_paints_the_tab_where_qt_cannot_be_imported():
    """The surface needs the old interface library after all."""
    answered = run_script(HEADLESS_PROBE)
    assert answered["qt"] is False
    assert answered["status"] == "STATUS: CRITICAL"
    assert answered["peak"] == "Peak P/L: $1,234.5678"
    assert answered["exposure"] == "Total Exposure: $4,500.25"
    assert answered["bots"] == "Running Bots: 4"
    assert answered["refresh_path"] == "painted"
    assert answered["widgets"] == 19
    assert answered["band"] == "warning"
    assert answered["steps"] == 4
    assert len(answered["alerts"]) == 1
    assert answered["alerts"][0][1]["text"] == "CRITICAL"
    assert [found["text"] for found in answered["rules"][0]] == [
        "Max Drawdown",
        "15.0",
        "warn",
        "Yes",
    ]
    assert answered["asset_bars"][0]["label"] == "BTC"
    assert answered["exchange_bars"][0]["label"] == "Coinbase"
    assert answered["calls"] == 15


def test_the_qt_block_can_let_qt_through():
    """The Qt-blocking probe reports absent whatever the process imports."""
    probe = (
        "import sys, json\n"
        "import PySide6.QtCore\n"
        "print(json.dumps({'qt': 'PySide6' in sys.modules}))\n"
    )
    assert run_script(probe)["qt"] is True


def test_the_qt_block_stops_the_module_that_paints_the_tab():
    """The Qt block let the shipped tab through."""
    probe = BLOCK_QT + (
        "import json\n"
        "from src.gui import risk_tab\n"
        "print(json.dumps({'built': hasattr(risk_tab, 'RiskTab'),\n"
        "    'gauge': hasattr(risk_tab, 'DrawdownGauge'),\n"
        "    'has_qt': risk_tab._HAS_QT}))\n"
    )
    answered = run_script(probe)
    assert answered["has_qt"] is False
    assert answered["built"] is False
    assert answered["gauge"] is False
