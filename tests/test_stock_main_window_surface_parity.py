"""The Qt stock trading window and the Qt-free surface, driven side by side.

A failure means the view model describes a different control, a different
colour, a different column, a different number format, a different layout
number, a different message box, a different tab or a different branch
than ``StockMainWindow`` builds on the same input.
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import json
import logging
import math
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.gui.main_tabs import stock_main_window_surface as surface
from src.gui.widgets import ColumnSpec, ColumnarTableWidget, STOCK_CARD, StatCard
from tests.fixtures.host_fonts import (
    app_font_advance_px,
    has_real_fonts,
    load_run_fonts,
    skip_unless_no_fonts,
    skip_unless_real_fonts,
)
from tests.fixtures.surface_pictures import (
    assert_cases_paint_differently,
    assert_picture_can_report,
    assert_pictures_differ,
    assert_pictures_match,
    assert_same_skin,
    colour_count,
    sealed,
    unaltered,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
WINDOW_SOURCE = REPO_ROOT / "src" / "gui" / "stock_main_window.py"
SURFACE_SOURCE = (
    REPO_ROOT / "src" / "gui" / "main_tabs" / "stock_main_window_surface.py"
)
BUS_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "bot_visualizer.py"
THREAD_NEIGHBOUR = REPO_ROOT / "src" / "gui" / "crypto_news_ticker.py"

PIXEL_SIZE = (1400, 900)

SOURCE_CONNECT_TOTAL = 5
RUNTIME_CONNECT_TOTAL = 7
SHIPPED_CLASS_TOTAL = 4
SHIPPED_FUNCTION_TOTAL = 22
SIGNAL_BUILD_TOTAL = 1
SIGNAL_EMIT_TOTAL = 1
TIMER_BUILD_TOTAL = 1
TIMER_START_TOTAL = 1
THREAD_BUILD_TOTAL = 0
THREAD_START_TOTAL = 0
BUS_SUBSCRIBE_TOTAL = 0
BUS_EMIT_TOTAL = 0
PAYLOAD_KEY_TOTAL = 52
CONSTANT_TOTAL = 242

OK_FROM_QT = QMessageBox.StandardButton.Ok
CANCEL_FROM_QT = QMessageBox.StandardButton.Cancel


def app():
    """The one application object every render is taken against.

    The run's font choice is applied here, so every render in this file
    is taken in the state the run asked for rather than the one the host
    happens to ship.
    """
    from tests.qt_pixel import ensure_app

    built = ensure_app()
    load_run_fonts()
    return built


def render_offscreen(widget, size):
    from tests.qt_pixel import render_widget

    return render_widget(widget, size)


def digest(value) -> str:
    """SHA-256 over every value in `value`, at every depth."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=True, default=repr).encode(
            "utf-8"
        )
    ).hexdigest()


# ---------------------------------------------------------------------
# The bot manager, the bridge, the market reader and one alert, as the
# test owns them. The Qt window is driven with these; the surface is
# driven with its own. Neither side reads the other's.
# ---------------------------------------------------------------------


class Manager:
    """The stock bot manager the window reads its cards and its table from."""

    def __init__(self, aggregate=None, statuses=None, register_result=None):
        self.aggregate = dict(aggregate or {})
        self.statuses = list(statuses or [])
        self.register_result = register_result
        self.registered = []

    def get_aggregate_stats(self):
        return self.aggregate

    def list_bots(self):
        return self.statuses

    def register(self, bot):
        self.registered.append(bot)
        return self.register_result


class Alert:
    """One TradingView alert the webhook table shows a row for."""

    def __init__(self, timestamp=0, symbol="", action="", price=0, strategy=""):
        self.timestamp = timestamp
        self.symbol = symbol
        self.action = action
        self.price = price
        self.strategy = strategy


class Bridge:
    """The TradingView bridge the window starts, stops and reads alerts from."""

    def __init__(self, running=False, port=8742, total_alerts=0, alerts=None):
        self.running = running
        self._port = port
        self.total_alerts = total_alerts
        self.alert_history = list(alerts or [])
        self.auth_token = None
        self.scheduled = []

    def get_summary(self):
        return {"port": self._port, "total_alerts": self.total_alerts}

    def set_auth_token(self, token):
        self.auth_token = token

    async def start(self):
        self.scheduled.append("start")

    async def stop(self):
        self.scheduled.append("stop")


class MarketReader:
    """The market-hours reader the strip asks for its session and its wording."""

    def __init__(self, session_name="REGULAR", status=""):
        from src.stocks.market_hours import MarketSession

        self.session = getattr(MarketSession, session_name)
        self.status = status

    def get_session(self, *_found):
        return self.session

    def get_status_string(self, *_found):
        return self.status


class Panel:
    """The indicator panel the refresh would feed, and what it records."""

    def __init__(self):
        self.updates = []

    def update_bot_list(self, statuses):
        self.updates.append(list(statuses))


LOG_STAMP = "07:41:03"
ALERT_STAMP_SECONDS = 1_700_000_000


class FixedDateTime:
    """Stands in for ``datetime`` so the activity log stamp never moves."""

    recorded: list = []

    @staticmethod
    def now():
        return FixedDateTime()

    def strftime(self, pattern):
        FixedDateTime.recorded.append(pattern)
        return LOG_STAMP


class BoxRecorder:
    """Stands in for ``QMessageBox`` and records every box the window raises.

    ``exec`` answers with whatever ``ANSWER`` holds, which is how the
    operator's Ok or Cancel is driven. ``Ok`` and ``Cancel`` are the real
    values, so the shipped comparison against them is unchanged.
    """

    ANSWER = None
    RAISED: list = []

    Ok = OK_FROM_QT
    Cancel = CANCEL_FROM_QT

    def __init__(self, _parent=None):
        self._box = {"title": "", "text": "", "buttons_value": 0}

    def setWindowTitle(self, title):
        self._box["title"] = title

    def setText(self, text):
        self._box["text"] = text

    def setStandardButtons(self, buttons):
        self._box["buttons_value"] = int(buttons.value)

    def exec(self):
        BoxRecorder.RAISED.append(dict(self._box))
        return BoxRecorder.ANSWER

    @staticmethod
    def about(_parent, title, text):
        BoxRecorder.RAISED.append({"title": title, "text": text})


class Unprintable:
    """A record body that refuses to become text."""

    def __format__(self, _spec):
        raise TypeError("no text")


class RaisingChart:
    """Stands in for the chart so the window takes its no-chart branch."""

    def __init__(self, *_found, **_named):
        raise RuntimeError("no web engine in this run")


class RaisingPanel:
    """Stands in for the indicator panel so the window takes its no-panel branch."""

    def __init__(self, *_found, **_named):
        raise RuntimeError("no indicator panel in this run")


# ---------------------------------------------------------------------
# The seams the Qt side is driven through, and the proof they came back
# ---------------------------------------------------------------------


class CrashRecorder(logging.Handler):
    """Keeps the refusal type of every crash line the window swallows."""

    def __init__(self, sink):
        super().__init__()
        self.sink = sink

    def emit(self, record):
        if record.args and isinstance(record.args[0], BaseException):
            self.sink.append(type(record.args[0]).__name__)


def _current_loop():
    """The loop this process currently has set, or none."""
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        return None


class QtSeams:
    """Swap every process-wide name the Qt drive needs, and put it back.

    ``appended`` collects every activity-log and console line, ``html``
    the one document the guide sets, ``sizes`` the split the window asks
    for and ``strftime`` the patterns the alert table formats with. Each
    is per-drive, so no count depends on what ran before it.
    """

    def __init__(self, seconds=0.0, chart=False, panel=False):
        self.seconds = seconds
        self.chart = chart
        self.panel = panel
        self.appended: list = []
        self.html: list = []
        self.sizes: list = []
        self.strftime: list = []
        self.crashes: list = []
        self.saved: dict = {}
        self.log_handlers: list = []
        self.loop = None
        self.previous_loop = None
        self.recorder = None

    def appended_to(self, widget) -> list:
        """Every line appended to one pane, in order."""
        return [text for owner, text in self.appended if owner is widget]

    def __enter__(self):
        import src.gui.indicator_panel as panel_module
        import src.gui.stock_main_window as shipped
        import src.gui.tradingview_chart as chart_module

        seams = self
        self.saved = {
            (QTextEdit, "append"): QTextEdit.append,
            (QTextEdit, "setHtml"): QTextEdit.setHtml,
            (QSplitter, "setSizes"): QSplitter.setSizes,
            (shipped, "QMessageBox"): shipped.QMessageBox,
            (shipped, "datetime"): shipped.datetime,
            (time, "time"): time.time,
            (time, "localtime"): time.localtime,
            (time, "strftime"): time.strftime,
        }
        if not self.chart:
            self.saved[(chart_module, "TradingViewChart")] = (
                chart_module.TradingViewChart
            )
            chart_module.TradingViewChart = RaisingChart
        if not self.panel:
            self.saved[(panel_module, "IndicatorVotingPanel")] = (
                panel_module.IndicatorVotingPanel
            )
            panel_module.IndicatorVotingPanel = RaisingPanel

        real_append = self.saved[(QTextEdit, "append")]
        real_html = self.saved[(QTextEdit, "setHtml")]
        real_sizes = self.saved[(QSplitter, "setSizes")]
        real_strftime = self.saved[(time, "strftime")]

        def watched_append(widget, text):
            seams.appended.append((widget, text))
            return real_append(widget, text)

        def watched_html(widget, text):
            seams.html.append(text)
            return real_html(widget, text)

        def watched_sizes(widget, sizes):
            seams.sizes.append(list(sizes))
            return real_sizes(widget, sizes)

        def watched_strftime(pattern, *found):
            seams.strftime.append(pattern)
            return real_strftime(pattern, *found)

        QTextEdit.append = watched_append
        QTextEdit.setHtml = watched_html
        QSplitter.setSizes = watched_sizes
        shipped.QMessageBox = BoxRecorder
        shipped.datetime = FixedDateTime
        time.time = lambda: seams.seconds
        time.localtime = time.gmtime
        time.strftime = watched_strftime
        self.log_handlers = list(logging.getLogger().handlers)
        self.recorder = CrashRecorder(self.crashes)
        logging.getLogger("acervator.gui.stocks").addHandler(self.recorder)
        self.previous_loop = _current_loop()
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        return self

    def __exit__(self, *_found):
        for (owner, name), value in self.saved.items():
            setattr(owner, name, value)
        pending = asyncio.all_tasks(self.loop)
        if pending:
            self.loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        self.loop.close()
        asyncio.set_event_loop(self.previous_loop)
        logging.getLogger("acervator.gui.stocks").removeHandler(self.recorder)
        root = logging.getLogger()
        for handler in list(root.handlers):
            if handler not in self.log_handlers:
                root.removeHandler(handler)
        from tests.fixtures.chart_theme_table import restore_chart_themes

        restore_chart_themes()
        return False

    def restored(self) -> bool:
        """Every swapped name holds the value it held before the drive."""
        return all(
            getattr(owner, name) is value for (owner, name), value in self.saved.items()
        )


# ---------------------------------------------------------------------
# The cases both sides are driven with
# ---------------------------------------------------------------------


LOOPBACK = {"127.0.0.1", "::1", "localhost"}

LONG_TEXT = "A" * 200
NEWLINE_BOT_ID = "fold\nbot"
UNICODE_BOT_ID = "Δ_fold→⚡"
MARKUP_SYMBOL = "<b>AAPL</b>"
APOSTROPHE_STRATEGY = "Ekthelius" + chr(39) + " Fold"


def bot(**named):
    """One stock bot status row, with every reading the table takes."""
    stats = {
        "total_pnl": 0,
        "current_position": 0,
        "avg_entry_price": 0,
        "current_price": 0,
        "total_trades": 0,
        "signals_received": 0,
        "winning_trades": 0,
    }
    stats.update(named.pop("stats", {}))
    status = {
        "bot_id": "abcdefghij",
        "symbol": "AAPL",
        "mode": "swing",
        "state": "running",
        "stats": stats,
    }
    status.update(named)
    return status


def case(name, **named):
    """One driven case, with the readings both sides are given."""
    spec = {
        "name": name,
        "aggregate": None,
        "statuses": [],
        "bridge": None,
        "session": "REGULAR",
        "status": "Market Open (9:30-4:00 ET)",
        "seconds": 100.0,
        "refresh": 1,
        "register_result": None,
        "create_answer": None,
        "toggle_webhook": False,
        "auth": "",
        "port": surface.PORT_DEFAULT,
    }
    spec.update(named)
    return spec


AGGREGATE = {"total_realised_pnl": 12.5, "total_trades": 4, "running": 2}

CASES = [
    case("no_manager"),
    case("happy", aggregate=AGGREGATE, statuses=[bot()]),
    case("empty_statuses", aggregate=AGGREGATE, statuses=[]),
    case("empty_aggregate", aggregate={}, statuses=[bot()]),
    case(
        "many_bots",
        aggregate=AGGREGATE,
        statuses=[bot(bot_id=f"bot{index}") for index in range(4)],
    ),
    case(
        "session_pre_market", session="PRE_MARKET", status="Pre-Market (4:00-9:30 ET)"
    ),
    case(
        "session_after_hours",
        session="AFTER_HOURS",
        status="After Hours (4:00-8:00 ET)",
    ),
    case("session_closed", session="CLOSED", status="Market Closed"),
    case("session_weekend", session="WEEKEND", status="Weekend — Market Closed"),
    case("session_holiday", session="HOLIDAY", status="Holiday — New Year's Day"),
    case("bridge_idle", bridge={"running": False}),
    case("bridge_running", bridge={"running": True, "port": 9001, "total_alerts": 12}),
    case(
        "bridge_alerts",
        bridge={
            "running": True,
            "port": 8742,
            "total_alerts": 2,
            "alerts": [
                {
                    "timestamp": ALERT_STAMP_SECONDS,
                    "symbol": "AAPL",
                    "action": "buy",
                    "price": 12.5,
                    "strategy": "Fold",
                },
                {
                    "timestamp": ALERT_STAMP_SECONDS + 60,
                    "symbol": MARKUP_SYMBOL,
                    "action": "sell",
                    "price": 0.0,
                    "strategy": APOSTROPHE_STRATEGY,
                },
            ],
        },
    ),
    case(
        "alerts_over_the_limit",
        bridge={
            "running": False,
            "alerts": [
                {
                    "timestamp": ALERT_STAMP_SECONDS,
                    "symbol": f"S{index}",
                    "action": "buy",
                    "price": float(index),
                    "strategy": "s",
                }
                for index in range(60)
            ],
        },
    ),
    case("throttle_skipped", bridge={"running": False}, seconds=1.0, refresh=2),
    case("zero", aggregate={"total_realised_pnl": 0, "total_trades": 0, "running": 0}),
    case(
        "negative",
        aggregate={"total_realised_pnl": -3.25, "total_trades": 2, "running": 1},
        statuses=[bot(stats={"total_pnl": -7.5, "avg_entry_price": -1.0})],
    ),
    case(
        "thousand_million",
        aggregate={"total_realised_pnl": 1e9, "total_trades": 10**9, "running": 3},
        statuses=[bot(stats={"total_pnl": 1e9, "current_price": 1e9})],
    ),
    case(
        "one_billionth",
        aggregate={"total_realised_pnl": 1e-9},
        statuses=[bot(stats={"total_pnl": 1e-9, "avg_entry_price": 1e-9})],
    ),
    case(
        "infinity",
        aggregate={"total_realised_pnl": math.inf},
        statuses=[bot(stats={"total_pnl": math.inf, "current_price": math.inf})],
    ),
    case(
        "minus_infinity",
        aggregate={"total_realised_pnl": -math.inf},
        statuses=[bot(stats={"total_pnl": -math.inf})],
    ),
    case(
        "not_a_number",
        aggregate={"total_realised_pnl": math.nan},
        statuses=[bot(stats={"total_pnl": math.nan, "current_price": math.nan})],
    ),
    case(
        "two_to_the_1023",
        aggregate={"total_realised_pnl": 2**1023},
        statuses=[bot(stats={"total_pnl": 2**1023})],
    ),
    case(
        "stored_true",
        aggregate={"total_realised_pnl": True, "total_trades": True, "running": True},
        statuses=[bot(stats={"total_pnl": True, "current_position": True})],
    ),
    case("unicode", statuses=[bot(bot_id=UNICODE_BOT_ID, symbol="Δ/USD")]),
    case("long_text", statuses=[bot(bot_id=LONG_TEXT, symbol=LONG_TEXT)]),
    case("markup", statuses=[bot(symbol=MARKUP_SYMBOL, state="<i>run</i>")]),
    case("apostrophe", statuses=[bot(symbol=APOSTROPHE_STRATEGY)]),
    case("wrong_capitals", statuses=[bot(mode="SWING", state="RUNNING")]),
    case("newline", statuses=[bot(bot_id=NEWLINE_BOT_ID, symbol="A\nB")]),
    case("empty_text", statuses=[bot(bot_id="", symbol="", mode="", state="")]),
    case("missing_stats", statuses=[{"bot_id": "x", "symbol": "S"}]),
    case("create_declined", create_answer=CANCEL_FROM_QT),
    case("create_made", create_answer=OK_FROM_QT),
    case(
        "create_refused",
        create_answer=OK_FROM_QT,
        aggregate=AGGREGATE,
        register_result=(False, "over allocation"),
    ),
    case(
        "create_granted_tuple",
        create_answer=OK_FROM_QT,
        aggregate=AGGREGATE,
        register_result=(True, "ok"),
    ),
    case("webhook_no_bridge", toggle_webhook=True),
    case("webhook_start", bridge={"running": False}, toggle_webhook=True),
    case(
        "webhook_start_with_auth",
        bridge={"running": False},
        toggle_webhook=True,
        auth="  hunter  ",
        port=9100,
    ),
    case("webhook_stop", bridge={"running": True}, toggle_webhook=True),
]

REFUSING_CASES = {
    "text_where_a_number_belongs": case(
        "text_where_a_number_belongs",
        aggregate={"total_realised_pnl": "12.7"},
    ),
    "text_in_a_cell": case(
        "text_in_a_cell",
        aggregate=AGGREGATE,
        statuses=[bot(stats={"avg_entry_price": "12.7"})],
    ),
    "two_to_the_1024": case(
        "two_to_the_1024",
        aggregate={"total_realised_pnl": 2**1024},
    ),
    "cell_two_to_the_1024": case(
        "cell_two_to_the_1024",
        aggregate=AGGREGATE,
        statuses=[bot(stats={"current_price": 2**1024})],
    ),
    "number_where_text_belongs": case(
        "number_where_text_belongs",
        aggregate=AGGREGATE,
        statuses=[bot(bot_id=42)],
    ),
}

BY_NAME = {spec["name"]: spec for spec in CASES}
ALL_CASES = list(CASES) + list(REFUSING_CASES.values())
ALL_BY_NAME = {spec["name"]: spec for spec in ALL_CASES}


# ---------------------------------------------------------------------
# Driving the Qt window
# ---------------------------------------------------------------------


def build_window(spec, seams):
    """The shipped window, built and driven exactly as the operator drives it."""
    from src.gui.stock_main_window import StockMainWindow

    manager = (
        Manager(spec["aggregate"], spec["statuses"], spec["register_result"])
        if spec["aggregate"] is not None or spec["statuses"]
        else None
    )
    bridge = Bridge(**spec["bridge"]) if spec["bridge"] is not None else None
    if bridge is not None:
        bridge.alert_history = [Alert(**one) for one in bridge.alert_history]
    window = StockMainWindow(stock_bot_manager=manager, tv_bridge=bridge)
    window._timer.stop()
    window._market_hours = MarketReader(spec["session"], spec["status"])
    window._manager_standin = manager
    window._bridge_standin = bridge
    return window


def drive_old(spec):
    """Build the shipped window, run the case, and read every value off it."""
    app()
    BoxRecorder.RAISED = []
    BoxRecorder.ANSWER = spec["create_answer"]
    FixedDateTime.recorded = []
    refusal = None
    with QtSeams(seconds=spec["seconds"]) as seams:
        window = build_window(spec, seams)
        for _ in range(spec["refresh"]):
            window._refresh_dashboard()
        if spec["create_answer"] is not None:
            try:
                window._create_bot()
            except Exception as exc:
                refusal = type(exc).__name__
        if spec["toggle_webhook"]:
            window._wh_port.setValue(spec["port"])
            window._wh_token.setText(spec["auth"])
            window._toggle_webhook()
        state = qt_state(window, seams)
        seams_restored_during = seams.restored()
        boxes = list(BoxRecorder.RAISED)
    return {
        "state": state,
        "refusal": refusal,
        "boxes": boxes,
        "window": window,
        "seams": seams,
        "swapped_during": seams_restored_during,
    }


def qt_state(window, seams):
    """Every value the shipped window shows, as plain data."""
    tabs = window._main_tabs
    table = window._bot_table
    alerts = window._alert_table
    return {
        "accessible_name": window.accessibleName(),
        "window_title": window.windowTitle(),
        "minimum_size": [window.minimumWidth(), window.minimumHeight()],
        "menus": menu_state(window),
        "market_text": window._market_status.text(),
        "market_style": window._market_status.styleSheet(),
        "webhook_text": window._webhook_status.text(),
        "webhook_style": window._webhook_status.styleSheet(),
        "card_labels": [card._label.text() for card in cards_of(window)],
        "card_values": [card._value.text() for card in cards_of(window)],
        "card_colors": [style_color(card._value) for card in cards_of(window)],
        "card_accessible_names": [card.accessibleName() for card in cards_of(window)],
        "bot_table_accessible_name": table.accessibleName(),
        "bot_columns": header_labels(table),
        "bot_rows": table_rows(table),
        "bot_row_colors": table_colors(table, surface.PNL_COLUMN),
        "bot_alignment": cell_alignment(table),
        "alert_columns": header_labels(alerts),
        "alert_rows": table_rows(alerts),
        "alert_alternating": alerts.alternatingRowColors(),
        "tab_titles": [tabs.tabText(index) for index in range(tabs.count())],
        "tabs_movable": tabs.isMovable(),
        "tabs_document_mode": tabs.documentMode(),
        "new_bot_text": window._btn_new_bot.text(),
        "new_bot_style": window._btn_new_bot.styleSheet(),
        "secondary_labels": secondary_labels(window),
        "secondary_styles": secondary_styles(window),
        "webhook_button_text": window._btn_start_wh.text(),
        "webhook_button_style": window._btn_start_wh.styleSheet(),
        "url_text": window._wh_url_label.text(),
        "url_style": window._wh_url_label.styleSheet(),
        "port_minimum": window._wh_port.minimum(),
        "port_maximum": window._wh_port.maximum(),
        "auth_placeholder": window._wh_token.placeholderText(),
        "auth_echo_mode": window._wh_token.echoMode().name,
        "group_titles": group_titles(window),
        "group_styles": sorted({group.styleSheet() for group in groups_of(window)}),
        "log_max_height": window._status_log.maximumHeight(),
        "log_style": window._status_log.styleSheet(),
        "guide_max_height": guide_of(window).maximumHeight(),
        "guide_style": guide_of(window).styleSheet(),
        "guide_html": seams.html[-1] if seams.html else "",
        "console_font": [
            window._console.font().family(),
            window._console.font().pointSize(),
        ],
        "console_style": window._console.styleSheet(),
        "console_wrap": window._console.lineWrapMode().name,
        "status_bar_text": window.statusBar().currentMessage(),
        "split_sizes": seams.sizes[-1] if seams.sizes else [],
        "split_handle_width": splitter_of(window).handleWidth(),
        "split_children_collapsible": splitter_of(window).childrenCollapsible(),
        "split_orientation": splitter_of(window).orientation().name,
        "timer_interval": window._timer.interval(),
        "appended": seams.appended_to(window._status_log),
        "crashes": list(seams.crashes),
        "chart_shown": window._chart is not None,
        "panel_shown": window._indicator_panel is not None,
    }


def menu_state(window):
    found = []
    for action in window.menuBar().actions():
        menu = action.menu()
        items = [
            surface.MENU_SEPARATOR if inner.isSeparator() else inner.text()
            for inner in menu.actions()
        ]
        found.append([action.text(), items])
    return found


def cards_of(window):
    return [
        window._stat_pnl,
        window._stat_trades,
        window._stat_bots,
        window._stat_positions,
        window._stat_pdt,
        window._stat_settlement,
    ]


def style_color(widget):
    """The colour a widget's own style sheet asks for, or none where unset."""
    sheet = widget.styleSheet()
    if "color: " not in sheet:
        return None
    return sheet.split("color: ", 1)[1].split(";", 1)[0]


def header_labels(table):
    return [
        table.horizontalHeaderItem(index).text() for index in range(table.columnCount())
    ]


def table_rows(table):
    return [
        [
            table.item(row, column).text() if table.item(row, column) else None
            for column in range(table.columnCount())
        ]
        for row in range(table.rowCount())
    ]


def table_colors(table, column):
    """The colour each row's one coloured cell carries, or none where unset."""
    found = []
    for row in range(table.rowCount()):
        item = table.item(row, column)
        if item is None:
            found.append(None)
            continue
        brush = item.data(Qt.ForegroundRole)
        found.append(None if brush is None else brush.color().name())
    return found


def cell_alignment(table):
    if table.rowCount() == 0 or table.item(0, 0) is None:
        return None
    return int(table.item(0, 0).textAlignment())


def secondary_buttons(window):
    return [
        button
        for button in window.findChildren(QPushButton)
        if button.text() in surface.SECONDARY_BUTTON_LABELS
    ]


def secondary_labels(window):
    return [button.text() for button in secondary_buttons(window)]


def secondary_styles(window):
    return sorted({button.styleSheet() for button in secondary_buttons(window)})


def groups_of(window):
    return window.findChildren(QGroupBox)


def group_titles(window):
    return sorted(group.title() for group in groups_of(window))


def guide_of(window):
    for edit in window.findChildren(QTextEdit):
        if edit.maximumHeight() == surface.GUIDE_MAX_HEIGHT_PX:
            return edit
    raise AssertionError("the window built no guide pane")


def splitter_of(window):
    return window.findChildren(QSplitter)[0]


# ---------------------------------------------------------------------
# Driving the surface
# ---------------------------------------------------------------------


def alert_stamp(timestamp):
    """The clock reading one alert row shows, taken in UTC on every host."""
    return time.strftime(surface.ALERT_TIME_FORMAT, time.gmtime(timestamp))


def new_model(spec):
    manager = (
        surface.BotManagerSource(
            spec["aggregate"], spec["statuses"], spec["register_result"]
        )
        if spec["aggregate"] is not None or spec["statuses"]
        else None
    )
    bridge = None
    if spec["bridge"] is not None:
        given = dict(spec["bridge"])
        bridge = surface.BridgeSource(
            running=given.get("running", False),
            port=given.get("port", surface.PORT_DEFAULT),
            total_alerts=given.get("total_alerts", 0),
            alerts=[surface.AlertSource(**one) for one in given.get("alerts", [])],
        )
    stamps = {
        one["timestamp"]: alert_stamp(one["timestamp"])
        for one in (spec["bridge"] or {}).get("alerts", [])
    }
    return surface.StockMainWindowModel(
        bot_manager=manager,
        bridge=bridge,
        market=surface.MarketSource(spec["session"].lower(), spec["status"]),
        clock=surface.ClockSource(
            seconds=spec["seconds"],
            time_text=LOG_STAMP,
            alert_time_texts=stamps,
        ),
        chart_available=False,
        panel_available=False,
        paper_trader_available=False,
    )


def drive_new(spec):
    """Run the case on the surface and return its payload."""
    model = new_model(spec)
    refusal = None
    model.build()
    for _ in range(spec["refresh"]):
        model.refresh()
    if spec["create_answer"] is not None:
        try:
            model.create_bot(spec["create_answer"])
        except Exception as exc:
            refusal = type(exc).__name__
    if spec["toggle_webhook"]:
        model.toggle_webhook(spec["auth"], spec["port"])
    payload = surface.build_view_model(model)
    return {"payload": payload, "model": model, "refusal": refusal}


def new_state(driven):
    """Every value the surface holds, in the shape the Qt reader returns."""
    payload = driven["payload"]
    model = driven["model"]
    return {
        "accessible_name": payload["accessible_name"],
        "window_title": payload["window"]["title"],
        "minimum_size": [
            payload["window"]["minimum_width_px"],
            payload["window"]["minimum_height_px"],
        ],
        "menus": payload["menus"],
        "market_text": payload["market_label"]["text"],
        "market_style": payload["market_label"]["style_sheet"],
        "webhook_text": payload["webhook_label"]["text"],
        "webhook_style": payload["webhook_label"]["style_sheet"],
        "card_labels": payload["cards"]["labels"],
        "card_values": payload["cards"]["values"],
        "card_colors": payload["cards"]["colors"],
        "card_accessible_names": [payload["cards"]["accessible_name"]]
        * len(payload["cards"]["labels"]),
        "bot_table_accessible_name": payload["bot_table"]["accessible_name"],
        "bot_columns": payload["bot_table"]["columns"],
        "bot_rows": payload["bot_table"]["rows"],
        "bot_row_colors": [
            row[surface.PNL_COLUMN] for row in payload["bot_table"]["row_colors"]
        ],
        "bot_alignment": (
            payload["bot_table"]["cell_alignment_value"]
            if payload["bot_table"]["rows"]
            and payload["bot_table"]["rows"][0][0] is not None
            else None
        ),
        "alert_columns": payload["alert_table"]["columns"],
        "alert_rows": payload["alert_table"]["rows"],
        "alert_alternating": payload["alert_table"]["alternating_row_colors"],
        "tab_titles": payload["tabs"]["titles"],
        "tabs_movable": payload["tabs"]["movable"],
        "tabs_document_mode": payload["tabs"]["document_mode"],
        "new_bot_text": payload["buttons"]["new_bot_text"],
        "new_bot_style": payload["buttons"]["new_bot_style"],
        "secondary_labels": payload["buttons"]["secondary_labels"],
        "secondary_styles": [payload["buttons"]["secondary_style"]],
        "webhook_button_text": payload["buttons"]["webhook_text"],
        "webhook_button_style": payload["buttons"]["webhook_style"],
        "url_text": payload["webhook_form"]["url_text"],
        "url_style": payload["webhook_form"]["url_style"],
        "port_minimum": payload["webhook_form"]["port_minimum"],
        "port_maximum": payload["webhook_form"]["port_maximum"],
        "auth_placeholder": payload["webhook_form"]["auth_placeholder"],
        "auth_echo_mode": payload["webhook_form"]["auth_echo_mode"],
        "group_titles": sorted(
            [
                payload["groups"]["chart"],
                payload["groups"]["log"],
                payload["groups"]["webhook_config"],
                payload["groups"]["guide"],
                payload["groups"]["alerts"],
            ]
        ),
        "group_styles": [payload["groups"]["style_sheet"]],
        "log_max_height": payload["activity_log"]["max_height_px"],
        "log_style": payload["activity_log"]["style_sheet"],
        "guide_max_height": payload["guide"]["max_height_px"],
        "guide_style": payload["guide"]["style_sheet"],
        "guide_html": payload["guide"]["html"],
        "console_font": [
            payload["console"]["font_family"],
            payload["console"]["font_size_pt"],
        ],
        "console_style": payload["console"]["style_sheet"],
        "console_wrap": payload["console"]["line_wrap"],
        "status_bar_text": payload["status_bar"]["text"],
        "split_sizes": payload["split"]["sizes"],
        "split_handle_width": payload["split"]["handle_width_px"],
        "split_children_collapsible": payload["split"]["children_collapsible"],
        "split_orientation": payload["split"]["orientation"],
        "timer_interval": payload["refresh"]["interval_ms"],
        "appended": list(model.log_lines),
        "crashes": [
            call[1] for call in payload["calls"] if call[0] == surface.REFRESH_CRASHED
        ],
        "chart_shown": payload["chart"]["shown"],
        "panel_shown": payload["panel"]["shown"],
    }


# ---------------------------------------------------------------------
# The two sides, value for value and by hash
# ---------------------------------------------------------------------


@pytest.mark.parametrize("name", [spec["name"] for spec in ALL_CASES])
def test_the_two_sides_describe_the_same_window(name):
    """The view model describes a different window than the shipped one builds."""
    spec = ALL_BY_NAME[name]
    old = drive_old(spec)["state"]
    new = new_state(drive_new(spec))
    assert set(old) == set(new), sorted(set(old) ^ set(new))
    apart = {key: (old[key], new[key]) for key in old if old[key] != new[key]}
    assert apart == {}, apart
    assert digest(old) == digest(new), (digest(old), digest(new))


@pytest.mark.parametrize("name", sorted(REFUSING_CASES))
def test_a_refused_input_names_the_same_error_on_both_sides(name):
    """One side refused an input the other accepted, or named another error."""
    spec = REFUSING_CASES[name]
    old = drive_old(spec)["state"]["crashes"]
    new = new_state(drive_new(spec))["crashes"]
    assert new, "the surface took no refusal"
    assert old == new, (old, new)
    assert new != ["AttributeError"], new


def test_the_hash_tells_two_different_answers_apart():
    """The hash returns one value whatever the two sides describe."""
    happy = new_state(drive_new(BY_NAME["happy"]))
    empty = new_state(drive_new(BY_NAME["no_manager"]))
    assert happy != empty
    assert digest(happy) != digest(empty)


@pytest.mark.parametrize("name", ["happy", "bridge_alerts", "webhook_start"])
def test_the_sample_hashes_are_reported(name):
    """A sample hash moved, so one side describes a different window."""
    spec = BY_NAME[name]
    old = digest(drive_old(spec)["state"])
    new = digest(new_state(drive_new(spec)))
    assert old == new, f"{name}: old {old}, new {new}"


def test_two_different_real_inputs_are_told_apart_in_both_directions():
    """The comparison passes whatever the second side describes."""
    first = BY_NAME["happy"]
    second = BY_NAME["many_bots"]
    old_first = drive_old(first)["state"]
    old_second = drive_old(second)["state"]
    new_first = new_state(drive_new(first))
    new_second = new_state(drive_new(second))
    assert digest(old_first) != digest(new_second), "old first vs new second"
    assert digest(old_second) != digest(new_first), "old second vs new first"
    assert digest(old_first) == digest(new_first)
    assert digest(old_second) == digest(new_second)


def test_the_same_input_twice_describes_one_window():
    """The surface answers differently on a second identical run."""
    spec = BY_NAME["happy"]
    first = digest(new_state(drive_new(spec)))
    second = digest(new_state(drive_new(spec)))
    assert first == second, (first, second)


def test_a_whole_number_and_a_decimal_are_told_apart_by_the_hash():
    """`12` and `12.0` are equal, so only the hash separates them."""
    whole_number = 12
    decimal = 12.0
    assert whole_number == decimal
    assert digest({"value": whole_number}) != digest({"value": decimal})
    whole = drive_new(case("whole", aggregate={"total_realised_pnl": 12}))
    decimal = drive_new(case("decimal", aggregate={"total_realised_pnl": 12.0}))
    assert new_state(whole)["card_values"] == new_state(decimal)["card_values"]


def test_two_not_a_numbers_are_compared_as_the_text_they_print():
    """A not-a-number is never equal to itself, so a raw comparison lies."""
    first_nan = float("nan")
    second_nan = float("nan")
    assert first_nan != second_nan, "a not-a-number compared equal to itself"
    first = new_state(drive_new(BY_NAME["not_a_number"]))
    second = new_state(drive_new(BY_NAME["not_a_number"]))
    assert first == second
    assert digest(first) == digest(second)
    assert "nan" in first["card_values"][0]
    for value in json.loads(json.dumps(first, default=repr)).values():
        assert not isinstance(value, float) or not math.isnan(value)


# ---------------------------------------------------------------------
# Step sequences, including one that refuses part way
# ---------------------------------------------------------------------


STEP_SEQUENCE = [
    ("build", None),
    ("refresh", None),
    ("create", OK_FROM_QT),
    ("webhook", None),
    ("refresh", None),
]


def test_a_step_sequence_takes_the_same_path_on_both_sides():
    """A step in the sequence changed the window on one side only."""
    spec = case("sequence", bridge={"running": False}, aggregate=AGGREGATE)
    model = new_model(spec)
    seen = []
    model.build()
    seen.append(["build", None])
    model.refresh()
    seen.append(["refresh", model.outcome])
    model.create_bot(OK_FROM_QT)
    seen.append(["create", model.outcome])
    model.toggle_webhook("", surface.PORT_DEFAULT)
    seen.append(["webhook", model.outcome])
    model.refresh()
    seen.append(["refresh", model.outcome])
    assert [step for step, _ in seen] == [step for step, _ in STEP_SEQUENCE]
    assert seen[1][1] == surface.OUTCOME_CRASHED
    assert seen[2][1] == surface.OUTCOME_CREATED
    assert seen[3][1] == surface.OUTCOME_STARTED
    assert len(model.log_lines) == 2, model.log_lines


def test_a_sequence_that_refuses_part_way_keeps_what_it_recorded():
    """A refusal part way through a sequence threw away the earlier steps."""
    spec = REFUSING_CASES["text_where_a_number_belongs"]
    model = new_model(spec)
    model.build()
    before = len(model.calls)
    steps = []
    for index, (name, answer) in enumerate(
        [("refresh", None), ("create", OK_FROM_QT), ("refresh", None)]
    ):
        if name == "refresh":
            model.refresh()
        else:
            model.create_bot(answer)
        steps.append([index, name, model.outcome])
    assert steps[0] == [0, "refresh", surface.OUTCOME_CRASHED]
    assert steps[1] == [1, "create", surface.OUTCOME_CREATED]
    assert steps[2] == [2, "refresh", surface.OUTCOME_CRASHED]
    assert len(model.calls) > before
    assert [call[0] for call in model.calls].count(surface.BUILD_START) == 1
    assert model.tab_titles == [
        surface.TAB_TRADING,
        surface.TAB_WEBHOOKS,
        surface.TAB_CONSOLE,
    ]
    assert model.warnings[0].startswith("Paper Trader tab unavailable")


# ---------------------------------------------------------------------
# What the shipped window declares, counted off the file
# ---------------------------------------------------------------------


def dotted(node) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def parsed(path):
    return ast.parse(path.read_text(encoding="utf-8"))


def declared_classes(path) -> set:
    """Every class the file declares, one inside a method included."""
    return {
        node.name for node in ast.walk(parsed(path)) if isinstance(node, ast.ClassDef)
    }


def declared_functions(path) -> list:
    return sorted(
        node.name
        for node in ast.walk(parsed(path))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def connect_sites(path) -> list:
    """Every ``.connect(`` site in `path`, as signal and target."""
    found = []
    for node in ast.walk(parsed(path)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "connect"
        ):
            target = node.args[0]
            found.append(
                (
                    dotted(node.func.value),
                    (
                        "lambda"
                        if isinstance(target, ast.Lambda)
                        else dotted(
                            target.func if isinstance(target, ast.Call) else target
                        )
                    ),
                )
            )
    return sorted(found)


def calls_named(path, ending) -> list:
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call) and dotted(node.func).endswith(ending)
    ]


def method_calls(path, name) -> list:
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == name
    ]


def bus_functions(path, name) -> list:
    """Every call to `name`, however the file spells the object it hangs off.

    Counting the function rather than a topic literal keeps an import
    alias in the count.
    """
    return [
        dotted(node.func)
        for node in ast.walk(parsed(path))
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == name)
            or (isinstance(node.func, ast.Name) and node.func.id == name)
        )
    ]


def test_the_class_counter_finds_the_class_declared_inside_a_method():
    """The class counter reads the top level only, so a nested class is lost."""
    found = declared_classes(WINDOW_SOURCE)
    assert "_StockLogHandler" in found, sorted(found)
    assert "StockMainWindow" in found, sorted(found)
    assert len(found) == SHIPPED_CLASS_TOTAL, sorted(found)
    top_level = {
        node.name
        for node in parsed(WINDOW_SOURCE).body
        if isinstance(node, ast.ClassDef)
    }
    assert top_level == set(), top_level


def test_every_shipped_function_is_counted():
    """The shipped window gained or lost a method."""
    functions = declared_functions(WINDOW_SOURCE)
    assert len(functions) == SHIPPED_FUNCTION_TOTAL, functions
    assert functions.count("__init__") == 4, functions
    assert "_refresh_dashboard" in functions
    assert "_append_to_widget" in functions


def test_the_connect_sets_match():
    """The window connects a signal the surface names no action for."""
    sites = connect_sites(WINDOW_SOURCE)
    assert len(sites) == SOURCE_CONNECT_TOTAL, sites
    assert len(surface.ACTIONS) == SOURCE_CONNECT_TOTAL, surface.ACTIONS
    assert surface.RUNTIME_CONNECT_TOTAL == RUNTIME_CONNECT_TOTAL


def test_the_connect_reader_counts_a_site_a_text_search_also_finds():
    """The connect reader returns an empty set whatever the source holds."""
    sites = connect_sites(WINDOW_SOURCE)
    assert ("self._timer.timeout", "self._refresh_dashboard") in sites
    text = WINDOW_SOURCE.read_text(encoding="utf-8").count(".connect(")
    assert text == len(sites), (text, len(sites))
    assert len(connect_sites(BUS_NEIGHBOUR)) > SOURCE_CONNECT_TOTAL


def test_the_window_connects_seven_signals_at_run_time():
    """Three of the seven connections come from one source line in a loop."""
    spec = BY_NAME["no_manager"]
    with QtSeams() as seams:
        window = build_window(spec, seams)
        window._timer.stop()
        assert len(secondary_buttons(window)) == len(surface.SECONDARY_BUTTON_LABELS)
    loop_sites = len(surface.SECONDARY_BUTTON_LABELS)
    assert SOURCE_CONNECT_TOTAL - 1 + loop_sites == RUNTIME_CONNECT_TOTAL


def test_the_signal_and_emit_counters_report_the_real_numbers():
    """A signal build or a signal emit is counted by text and lands in a comment."""
    builds = calls_named(WINDOW_SOURCE, "Signal")
    emits = method_calls(WINDOW_SOURCE, "emit")
    assert len(builds) == SIGNAL_BUILD_TOTAL, builds
    assert len(emits) == SIGNAL_EMIT_TOTAL, emits
    assert list(surface.SIGNAL_NAMES) == ["_append_signal"]
    assert surface.SIGNAL_EMIT_TOTAL == SIGNAL_EMIT_TOTAL
    text = WINDOW_SOURCE.read_text(encoding="utf-8")
    assert text.count("emit(") > len(emits), "the text search stopped over-counting"


def test_the_timer_counter_reports_one_built_and_one_started():
    """The window builds a timer the surface declares no delay for."""
    builds = calls_named(WINDOW_SOURCE, "QTimer")
    started = [
        name for name in method_calls(WINDOW_SOURCE, "start") if "_timer" in name
    ]
    assert len(builds) == TIMER_BUILD_TOTAL, builds
    assert len(started) == TIMER_START_TOTAL, started
    assert surface.TIMERS == {"refresh_timer": surface.REFRESH_INTERVAL_MS}
    assert surface.TIMER_DELAYS_MS == (surface.REFRESH_INTERVAL_MS,)
    assert list(surface.TIMERS_STARTED) == ["refresh_timer"]
    text = WINDOW_SOURCE.read_text(encoding="utf-8")
    assert text.count("QTimer") > len(builds), "the text search stopped over-counting"


def test_the_thread_counter_reports_none_and_can_report_one():
    """The window owns a worker thread the surface names none of."""
    built = [
        name
        for name in calls_named(WINDOW_SOURCE, "Thread")
        + calls_named(WINDOW_SOURCE, "QThread")
    ]
    assert built == [], built
    assert len(surface.THREADS_BUILT) == THREAD_BUILD_TOTAL
    assert len(surface.THREADS_STARTED) == THREAD_START_TOTAL
    neighbour = calls_named(THREAD_NEIGHBOUR, "Thread") + calls_named(
        THREAD_NEIGHBOUR, "QThread"
    )
    assert len(neighbour) >= 1, "the thread counter reports nothing"


def test_the_bus_counters_report_none_and_can_report_a_real_call():
    """The window talks on a bus topic the surface names none of."""
    subscribes = bus_functions(WINDOW_SOURCE, "subscribe")
    emits = bus_functions(WINDOW_SOURCE, "publish")
    assert subscribes == [], subscribes
    assert emits == [], emits
    assert len(surface.BUS_TOPICS) == BUS_SUBSCRIBE_TOTAL
    assert len(surface.BUS_EMITS) == BUS_EMIT_TOTAL
    neighbour = bus_functions(BUS_NEIGHBOUR, "subscribe")
    assert len(neighbour) >= 2, "the bus counter reports nothing"


# ---------------------------------------------------------------------
# Completeness
# ---------------------------------------------------------------------


def at_path(payload, path):
    """The payload value one dotted path names."""
    found = payload
    for step in path.split("."):
        found = found[step]
    return found


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


PAYLOAD_KEYS = {
    "METHOD": "method",
    "ACCESSIBLE_NAME": "accessible_name",
    "WINDOW_TITLE": "window.title",
    "MINIMUM_WIDTH_PX": "window.minimum_width_px",
    "MINIMUM_HEIGHT_PX": "window.minimum_height_px",
    "CONTENT_MARGINS": "window.margins",
    "CONTENT_SPACING_PX": "window.spacing_px",
    "FILE_MENU_ITEMS": "menu_items.file",
    "HELP_MENU_ITEMS": "menu_items.help",
    "MENU_SEPARATOR": "menu_items.separator",
    "MARKET_INITIAL_TEXT": "market_label.initial_text",
    "MARKET_INITIAL_STYLE": "market_label.initial_style",
    "MARKET_TEXT_FORMAT": "formats.market_text",
    "MARKET_STYLE_FORMAT": "formats.market_style",
    "SESSION_REGULAR": "sessions.regular",
    "SESSION_PRE_MARKET": "sessions.pre_market",
    "SESSION_AFTER_HOURS": "sessions.after_hours",
    "SESSION_OPEN_COLOR": "sessions.open_color",
    "SESSION_EXTENDED_COLOR": "sessions.extended_color",
    "SESSION_SHUT_COLOR": "sessions.shut_color",
    "WEBHOOK_INITIAL_TEXT": "webhook_label.initial_text",
    "WEBHOOK_INITIAL_STYLE": "webhook_label.initial_style",
    "WEBHOOK_ACTIVE_TEXT_FORMAT": "formats.webhook_active_text",
    "WEBHOOK_ACTIVE_STYLE": "webhook_label.active_style",
    "STAT_CARD_LABELS": "cards.labels",
    "STAT_CARD_INITIAL_VALUE": "cards.initial_value",
    "STAT_CARD_ACCESSIBLE_NAME": "cards.accessible_name",
    "STAT_CARD_STYLE_NAME": "cards.style_name",
    "STAT_PNL_FORMAT": "formats.stat_pnl",
    "WIN_RATE_FORMAT": "formats.win_rate",
    "MISSING_STAT_ATTRIBUTES": "refresh.missing_attributes",
    "MISSING_ATTRIBUTE_ERROR": "refresh.missing_attribute_error",
    "SKIPPED_WHEN_MANAGER_PRESENT": "refresh.skipped_when_manager_present",
    "BOT_TABLE_ACCESSIBLE_NAME": "bot_table.accessible_name",
    "BOT_TABLE_COLUMNS": "bot_table.columns",
    "BOT_TABLE_COLUMN_COUNT": "bot_table.column_count",
    "PNL_COLUMN": "bot_table.pnl_column",
    "CELL_ALIGNMENT": "bot_table.cell_alignment",
    "CELL_ALIGNMENT_VALUE": "bot_table.cell_alignment_value",
    "BOT_ID_LENGTH": "bot_table.bot_id_length",
    "ENTRY_FORMAT": "formats.entry",
    "CURRENT_FORMAT": "formats.current",
    "PNL_FORMAT": "formats.pnl",
    "NO_CELL_COLOR": "no_cell_color",
    "STATS_KEY": "keys.stats",
    "BOT_ID_KEY": "keys.bot_id",
    "SYMBOL_KEY": "keys.symbol",
    "MODE_KEY": "keys.mode",
    "STATE_KEY": "keys.state",
    "PNL_KEY": "keys.pnl",
    "POSITION_KEY": "keys.position",
    "ENTRY_KEY": "keys.entry",
    "PRICE_KEY": "keys.price",
    "TRADES_KEY": "keys.trades",
    "SIGNALS_KEY": "keys.signals",
    "WINS_KEY": "keys.wins",
    "AGGREGATE_PNL_KEY": "keys.aggregate_pnl",
    "RUNNING_KEY": "keys.running",
    "PORT_KEY": "keys.port",
    "TOTAL_ALERTS_KEY": "keys.total_alerts",
    "DEFAULT_TEXT": "defaults.text",
    "DEFAULT_NUMBER": "defaults.number",
    "SPLIT_ORIENTATION": "split.orientation",
    "SPLIT_HANDLE_WIDTH_PX": "split.handle_width_px",
    "SPLIT_CHILDREN_COLLAPSIBLE": "split.children_collapsible",
    "SPLIT_SIZES": "split.sizes",
    "PANEL_MARGINS": "split.panel_margins",
    "NEW_BOT_BUTTON_TEXT": "buttons.new_bot_text",
    "NEW_BOT_BUTTON_STYLE": "buttons.new_bot_style",
    "SECONDARY_BUTTON_LABELS": "buttons.secondary_labels",
    "SECONDARY_BUTTON_STYLE": "buttons.secondary_style",
    "GROUP_BOX_STYLE": "groups.style_sheet",
    "CHART_GROUP_TITLE": "groups.chart",
    "CHART_SYMBOL": "chart.symbol",
    "CHART_THEME": "chart.theme",
    "CHART_STRETCH": "chart.stretch",
    "CHART_FALLBACK_TEXT": "chart.fallback_text",
    "PANEL_STRETCH": "panel.stretch",
    "PANEL_MODE": "panel.mode",
    "PANEL_SOURCE_MODES": "panel.source_modes",
    "LOG_GROUP_TITLE": "groups.log",
    "LOG_MAX_HEIGHT_PX": "activity_log.max_height_px",
    "LOG_STYLE": "activity_log.style_sheet",
    "LOG_TIME_FORMAT": "activity_log.time_format",
    "LOG_LINE_FORMAT": "activity_log.line_format",
    "LOG_LEVEL_COLORS": "activity_log.level_colors",
    "LOG_FALLBACK_COLOR": "activity_log.fallback_color",
    "WEBHOOK_CONFIG_TITLE": "groups.webhook_config",
    "PORT_MINIMUM": "webhook_form.port_minimum",
    "PORT_MAXIMUM": "webhook_form.port_maximum",
    "PORT_DEFAULT": "webhook_form.port_default",
    "PORT_ROW_LABEL": "webhook_form.port_row_label",
    "AUTH_ROW_LABEL": "webhook_form.auth_row_label",
    "AUTH_PLACEHOLDER": "webhook_form.auth_placeholder",
    "AUTH_ECHO_MODE": "webhook_form.auth_echo_mode",
    "START_WEBHOOK_TEXT": "buttons.webhook_start_text",
    "STOP_WEBHOOK_TEXT": "buttons.webhook_stop_text",
    "WEBHOOK_BUTTON_STYLE": "buttons.webhook_style",
    "URL_INITIAL_TEXT": "webhook_form.url_initial_text",
    "URL_STOPPED_TEXT": "webhook_form.url_stopped_text",
    "URL_RUNNING_FORMAT": "formats.url_running",
    "URL_LABEL_STYLE": "webhook_form.url_style",
    "GUIDE_TITLE": "groups.guide",
    "GUIDE_MAX_HEIGHT_PX": "guide.max_height_px",
    "GUIDE_STYLE": "guide.style_sheet",
    "GUIDE_HTML": "guide.html",
    "ALERTS_GROUP_TITLE": "groups.alerts",
    "ALERT_COLUMNS": "alert_table.columns",
    "ALERT_COLUMN_COUNT": "alert_table.column_count",
    "ALERT_HISTORY_LIMIT": "alert_table.history_limit",
    "ALERT_TIME_FORMAT": "formats.alert_time",
    "ALERT_PRICE_FORMAT": "formats.alert_price",
    "ALERT_HEADER_RESIZE_MODE": "alert_table.header_resize_mode",
    "ALERT_ALTERNATING_ROW_COLORS": "alert_table.alternating_row_colors",
    "ALERT_VERTICAL_HEADER_VISIBLE": "alert_table.vertical_header_visible",
    "TABS_MOVABLE": "tabs.movable",
    "TABS_DOCUMENT_MODE": "tabs.document_mode",
    "PAPER_TRADER_ASSET_TYPE": "tabs.paper_trader_asset_type",
    "PAPER_TRADER_LOGGER": "tabs.paper_trader_logger",
    "PAPER_TRADER_FAILURE_FORMAT": "formats.paper_trader_failure",
    "REMOVED_TABS": "tabs.removed",
    "CONSOLE_FONT_FAMILY": "console.font_family",
    "CONSOLE_FONT_SIZE_PT": "console.font_size_pt",
    "CONSOLE_LINE_WRAP": "console.line_wrap",
    "CONSOLE_STYLE": "console.style_sheet",
    "HANDLER_FORMAT": "console.handler_format",
    "HANDLER_DATE_FORMAT": "console.handler_date_format",
    "HANDLER_CONNECTION": "console.handler_connection",
    "HANDLER_LINE_FORMAT": "console.handler_line_format",
    "HANDLER_LEVEL_COLORS": "console.level_colors",
    "HANDLER_FALLBACK_COLOR": "console.fallback_color",
    "HANDLER_ROOT_LOGGER": "console.handler_root_logger",
    "STATUS_BAR_TEXT": "status_bar.ready_text",
    "REFRESH_INTERVAL_MS": "refresh.interval_ms",
    "TAB_REFRESH_SECONDS": "refresh.throttle_seconds",
    "REFRESH_CRASH_FORMAT": "refresh.crash_format",
    "PANEL_FAILURE_FORMAT": "refresh.panel_failure_format",
    "CONSOLE_FAILURE_FORMAT": "refresh.console_failure_format",
    "WINDOW_READY_MESSAGE": "refresh.ready_message",
    "NEW_BOT_TITLE": "new_bot.title",
    "NEW_BOT_TEXT": "new_bot.text",
    "NEW_BOT_BUTTONS_VALUE": "new_bot.buttons_value",
    "OK_BUTTON_VALUE": "new_bot.ok_value",
    "CANCEL_BUTTON_VALUE": "new_bot.cancel_value",
    "BOT_SYMBOL": "new_bot.symbol",
    "BOT_TARGET_BALANCE": "new_bot.target_balance",
    "BOT_TIMEFRAME": "new_bot.timeframe",
    "REGISTER_REFUSED_FORMAT": "formats.register_refused",
    "BOT_CREATED_FORMAT": "formats.bot_created",
    "START_BOT_MESSAGE": "messages.start_bot",
    "STOP_BOT_MESSAGE": "messages.stop_bot",
    "DELETE_BOT_MESSAGE": "messages.delete_bot",
    "SETTINGS_MESSAGE": "messages.settings",
    "NO_BRIDGE_MESSAGE": "messages.no_bridge",
    "WEBHOOK_STOPPED_MESSAGE": "messages.webhook_stopped",
    "WEBHOOK_STARTED_FORMAT": "formats.webhook_started",
    "ABOUT_TITLE": "about.title",
    "ABOUT_TEXT": "about.text",
    "NO_OUTCOME": "no_outcome",
    "ACTIONS": "actions",
    "RUNTIME_CONNECT_TOTAL": "runtime_connect_total",
    "SIGNAL_NAMES": "signals",
    "SIGNAL_EMIT_TOTAL": "signal_emit_total",
    "TIMERS": "timers",
    "TIMER_DELAYS_MS": "timer_delays_ms",
    "TIMERS_STARTED": "timers_started",
    "THREADS_BUILT": "threads_built",
    "THREADS_STARTED": "threads_started",
    "BUS_TOPICS": "bus_topics",
    "BUS_EMITS": "bus_emits",
    "CALL_NAMES": "call_names",
}

LIST_MEMBERS = {
    "FILE_MENU_TITLE": "menu_titles",
    "HELP_MENU_TITLE": "menu_titles",
    "TAB_TRADING": "tabs.all_titles",
    "TAB_WEBHOOKS": "tabs.all_titles",
    "TAB_PAPER_TRADER": "tabs.all_titles",
    "TAB_CONSOLE": "tabs.all_titles",
    "LOG_INFO": "log_levels",
    "LOG_SUCCESS": "log_levels",
    "LOG_WARNING": "log_levels",
    "LOG_ERROR": "log_levels",
    "OUTCOME_DECLINED": "outcomes",
    "OUTCOME_REFUSED": "outcomes",
    "OUTCOME_CREATED": "outcomes",
    "OUTCOME_NO_BRIDGE": "outcomes",
    "OUTCOME_STOPPED": "outcomes",
    "OUTCOME_STARTED": "outcomes",
    "OUTCOME_CRASHED": "outcomes",
    "OUTCOME_DONE": "outcomes",
    "SETTINGS_ACTION": "menu_items.file",
    "LAUNCHER_ACTION": "menu_items.file",
    "EXIT_ACTION": "menu_items.file",
    "ABOUT_ACTION": "menu_items.help",
}

NOT_IN_THE_SNAPSHOT = {
    "PANE_MODEL": "test_the_bridge_resets_the_window_state_on_request",
    "CARD_VALUE_COLOR": "test_the_two_sides_describe_the_same_window",
}


def test_every_value_the_surface_exports_reaches_the_snapshot():
    """A value the surface exports is in no snapshot the tests read."""
    payload = surface.build_view_model(surface.StockMainWindowModel())
    constants = surface_constants()
    assert len(constants) == CONSTANT_TOTAL, sorted(constants)
    unaccounted = []
    for name, value in constants.items():
        if name in PAYLOAD_KEYS:
            carried = at_path(payload, PAYLOAD_KEYS[name])
            if isinstance(value, tuple):
                assert carried == list(value), name
            else:
                assert carried == value, name
        elif name in LIST_MEMBERS:
            assert value in at_path(payload, LIST_MEMBERS[name]), name
        elif isinstance(value, str) and value in surface.CALL_NAMES:
            assert value in payload["call_names"], name
        elif name in NOT_IN_THE_SNAPSHOT:
            covered_by = NOT_IN_THE_SNAPSHOT[name]
            assert covered_by in globals(), (name, covered_by)
        else:
            unaccounted.append(name)
    assert unaccounted == [], unaccounted


def test_every_snapshot_key_carries_a_value_the_surface_holds():
    """The snapshot grew a key no value on the surface backs."""
    payload = surface.build_view_model(surface.StockMainWindowModel())
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {path.split(".")[0] for path in LIST_MEMBERS.values()}
    state_only = {
        "menus",
        "boxes",
        "warnings",
        "hidden",
        "timer_started",
        "outcome",
        "calls",
    }
    assert set(payload) == answered | state_only, sorted(
        set(payload) ^ (answered | state_only)
    )
    assert len(payload) == PAYLOAD_KEY_TOTAL, len(payload)


def test_the_completeness_check_can_report_a_missing_value():
    """The completeness check passed because it looks at nothing."""
    payload = surface.build_view_model(surface.StockMainWindowModel())
    invented = "INVENTED_CONSTANT"
    assert invented not in PAYLOAD_KEYS
    assert invented not in LIST_MEMBERS
    assert invented not in NOT_IN_THE_SNAPSHOT
    assert invented not in surface_constants()
    assert "GUIDE_HTML" in surface_constants()
    assert "build_view_model" not in surface_constants()
    assert "StockMainWindowModel" not in surface_constants()
    with pytest.raises(KeyError):
        at_path(payload, "groups.invented")


def test_both_completeness_checks_can_report():
    """A completeness check that cannot report a spare key is no check."""
    payload = dict(surface.build_view_model(surface.StockMainWindowModel()))
    payload["invented_key"] = 1
    answered = {path.split(".")[0] for path in PAYLOAD_KEYS.values()}
    answered |= {path.split(".")[0] for path in LIST_MEMBERS.values()}
    state_only = {
        "menus",
        "boxes",
        "warnings",
        "hidden",
        "timer_started",
        "outcome",
        "calls",
    }
    assert set(payload) != answered | state_only
    assert set(payload) - (answered | state_only) == {"invented_key"}
    constants = dict(surface_constants())
    constants["INVENTED_CONSTANT"] = "nowhere"
    unaccounted = [
        name
        for name in constants
        if name not in PAYLOAD_KEYS
        and name not in LIST_MEMBERS
        and name not in NOT_IN_THE_SNAPSHOT
        and not (
            isinstance(constants[name], str) and constants[name] in surface.CALL_NAMES
        )
    ]
    assert unaccounted == ["INVENTED_CONSTANT"], unaccounted


def test_the_surface_grew_no_name_the_file_does_not_declare():
    """A name on the module and a name in the file disagree."""
    tree = parsed(SURFACE_SOURCE)
    parsed_names = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            parsed_names.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            parsed_names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            parsed_names.add(node.name)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
    live = {name for name in vars(surface) if not name.startswith("__")}
    assert parsed_names - imported - live == set(), parsed_names - imported - live
    assert live - parsed_names - imported == set(), live - parsed_names - imported


def test_every_branch_marker_fires():
    """A branch the surface declares is never taken, or takes silently."""
    seen = set()
    for spec in ALL_CASES:
        driven = drive_new(spec)
        seen.update(call[0] for call in driven["model"].calls)
    extra = surface.StockMainWindowModel(
        chart_available=True, panel_available=True, paper_trader_available=True
    )
    extra.build()
    extra.set_launcher_callback(None)
    extra.back_to_launcher()
    extra.set_launcher_callback(lambda: None)
    extra.back_to_launcher()
    extra.show_about()
    extra.open_settings()
    for label in surface.SECONDARY_BUTTON_LABELS:
        extra.bot_button_handler(label)()
    extra.append_to_console("INFO", "a line")
    extra.append_to_console("INFO", Unprintable())
    seen.update(call[0] for call in extra.calls)
    missing = set(surface.CALL_NAMES) - seen
    assert missing == set(), sorted(missing)
    assert surface.ModelCall is list


def test_the_console_append_records_its_own_refusal():
    """The console handler swallowed a bad record without recording it."""

    model = surface.StockMainWindowModel()
    model.append_to_console("INFO", Unprintable())
    assert [call[0] for call in model.calls] == [surface.CONSOLE_FAILED]
    assert model.console_lines == []
    model.append_to_console("INFO", "a line")
    assert model.console_lines == [surface.handler_line("INFO", "a line")]


# ---------------------------------------------------------------------
# The colours, read off the surface and off the shipped window's data
# ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "session,expected",
    [
        ("regular", surface.SESSION_OPEN_COLOR),
        ("pre_market", surface.SESSION_EXTENDED_COLOR),
        ("after_hours", surface.SESSION_EXTENDED_COLOR),
        ("closed", surface.SESSION_SHUT_COLOR),
        ("weekend", surface.SESSION_SHUT_COLOR),
        ("holiday", surface.SESSION_SHUT_COLOR),
    ],
)
def test_the_market_colour_follows_the_session_exactly(session, expected):
    """The market line took the wrong colour for this session."""
    assert surface.market_color(session) == expected


@pytest.mark.parametrize(
    "pnl,expected",
    [
        (1.0, surface.SESSION_OPEN_COLOR),
        (0, surface.SESSION_OPEN_COLOR),
        (-0.01, surface.SESSION_SHUT_COLOR),
        (math.inf, surface.SESSION_OPEN_COLOR),
        (-math.inf, surface.SESSION_SHUT_COLOR),
        (math.nan, surface.SESSION_SHUT_COLOR),
    ],
)
def test_the_profit_colour_follows_the_number_exactly(pnl, expected):
    """The profit cell took the wrong colour for this number."""
    assert surface.pnl_color(pnl) == expected


def test_no_declared_colour_has_three_equal_channels():
    """A colour whose channels are equal hides a channel swap."""
    declared = set(surface.LOG_LEVEL_COLORS.values()) | set(
        surface.HANDLER_LEVEL_COLORS.values()
    )
    declared |= {
        surface.SESSION_OPEN_COLOR,
        surface.SESSION_EXTENDED_COLOR,
        surface.SESSION_SHUT_COLOR,
    }
    flat = [
        colour
        for colour in declared
        if len(set(colour.lstrip("#"))) == 1 or len(colour.lstrip("#")) == 3
    ]
    assert flat == [], flat


def test_a_channel_swap_is_reported_where_the_channels_differ():
    """The colour comparison passes whatever the channels hold."""
    green = surface.SESSION_OPEN_COLOR
    swapped = "#" + green[3:5] + green[1:3] + green[5:7]
    assert swapped != green
    assert surface.pnl_color(1.0) != swapped


# ---------------------------------------------------------------------
# The pictures
# ---------------------------------------------------------------------


PICTURE_CASES = ["no_manager", "bridge_running", "webhook_start"]
CONTROL_RULE = "QTableWidget { background: #3a1414; }"


def model_payload(spec):
    """The payload one picture is painted from, stamped as it comes off."""
    return sealed(drive_new(spec)["payload"])


def window_painted_by_the_window(spec):
    """The shipped window, driven and left for a render."""
    driven = drive_old(spec)
    return driven["window"]


class StockStatCard(StatCard):
    """A card whose class name is the one the shipped skin selects on."""

    def __init__(self, label, value):
        super().__init__(label, value, style=STOCK_CARD)


def window_painted_by_the_model(payload):
    """A window built only from the surface's view model."""
    payload = unaltered(payload)
    app()
    window = QMainWindow()
    window.setAccessibleName(payload["accessible_name"])
    window.setWindowTitle(payload["window"]["title"])
    window.setMinimumSize(
        payload["window"]["minimum_width_px"], payload["window"]["minimum_height_px"]
    )
    bar = window.menuBar()
    for title, items in payload["menus"]:
        menu = bar.addMenu(title)
        for item in items:
            if item == payload["menu_items"]["separator"]:
                menu.addSeparator()
            else:
                menu.addAction(item, lambda: None)

    central = QWidget()
    window.setCentralWidget(central)
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(*payload["window"]["margins"])
    main_layout.setSpacing(payload["window"]["spacing_px"])

    market_bar = QHBoxLayout()
    market = QLabel(payload["market_label"]["text"])
    market.setStyleSheet(payload["market_label"]["style_sheet"])
    market_bar.addWidget(market)
    market_bar.addStretch()
    webhook = QLabel(payload["webhook_label"]["text"])
    webhook.setStyleSheet(payload["webhook_label"]["style_sheet"])
    market_bar.addWidget(webhook)
    main_layout.addLayout(market_bar)

    dashboard = QHBoxLayout()
    for index, label in enumerate(payload["cards"]["labels"]):
        card = StockStatCard(label, payload["cards"]["initial_value"])
        card.set_value(
            payload["cards"]["values"][index], payload["cards"]["colors"][index]
        )
        dashboard.addWidget(card)
    main_layout.addLayout(dashboard)

    tabs = QTabWidget()
    tabs.setMovable(payload["tabs"]["movable"])
    tabs.setDocumentMode(payload["tabs"]["document_mode"])

    trading_tab = QWidget()
    trading_layout = QVBoxLayout(trading_tab)
    split = QSplitter(Qt.Horizontal)
    split.setHandleWidth(payload["split"]["handle_width_px"])
    split.setChildrenCollapsible(payload["split"]["children_collapsible"])

    left = QWidget()
    left_layout = QVBoxLayout(left)
    left_layout.setContentsMargins(*payload["split"]["panel_margins"])
    button_row = QHBoxLayout()
    new_bot = QPushButton(payload["buttons"]["new_bot_text"])
    new_bot.setStyleSheet(payload["buttons"]["new_bot_style"])
    button_row.addWidget(new_bot)
    for label in payload["buttons"]["secondary_labels"]:
        button = QPushButton(label)
        button.setStyleSheet(payload["buttons"]["secondary_style"])
        button_row.addWidget(button)
    left_layout.addLayout(button_row)
    table = ColumnarTableWidget(
        spec=ColumnSpec(
            labels=tuple(payload["bot_table"]["columns"]),
            accessible_name=payload["bot_table"]["accessible_name"],
        )
    )
    fill_table(
        table,
        payload["bot_table"]["rows"],
        payload["bot_table"]["row_colors"],
        payload["bot_table"]["cell_alignment_value"],
    )
    left_layout.addWidget(table)
    split.addWidget(left)

    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(*payload["split"]["panel_margins"])
    chart_group = QGroupBox(payload["groups"]["chart"])
    chart_group.setStyleSheet(payload["groups"]["style_sheet"])
    chart_layout = QVBoxLayout(chart_group)
    chart_layout.addWidget(QLabel(payload["chart"]["fallback_text"]))
    right_layout.addWidget(chart_group, stretch=payload["chart"]["stretch"])
    split.addWidget(right)
    split.setSizes(payload["split"]["sizes"])
    trading_layout.addWidget(split)

    log_group = QGroupBox(payload["groups"]["log"])
    log_group.setStyleSheet(payload["groups"]["style_sheet"])
    log_layout = QVBoxLayout(log_group)
    status_log = QTextEdit()
    status_log.setReadOnly(True)
    status_log.setMaximumHeight(payload["activity_log"]["max_height_px"])
    status_log.setStyleSheet(payload["activity_log"]["style_sheet"])
    for line in payload["activity_log"]["lines"]:
        status_log.append(line)
    log_layout.addWidget(status_log)
    trading_layout.addWidget(log_group)
    tabs.addTab(trading_tab, payload["tabs"]["all_titles"][0])

    webhook_tab = QWidget()
    wh_layout = QVBoxLayout(webhook_tab)
    config = QGroupBox(payload["groups"]["webhook_config"])
    config.setStyleSheet(payload["groups"]["style_sheet"])
    form = QFormLayout(config)
    port = QSpinBox()
    port.setRange(
        payload["webhook_form"]["port_minimum"], payload["webhook_form"]["port_maximum"]
    )
    port.setValue(payload["webhook_form"]["port_default"])
    form.addRow(payload["webhook_form"]["port_row_label"], port)
    token = QLineEdit()
    token.setPlaceholderText(payload["webhook_form"]["auth_placeholder"])
    token.setEchoMode(getattr(QLineEdit, payload["webhook_form"]["auth_echo_mode"]))
    form.addRow(payload["webhook_form"]["auth_row_label"], token)
    wh_button_row = QHBoxLayout()
    wh_button = QPushButton(payload["buttons"]["webhook_text"])
    wh_button.setStyleSheet(payload["buttons"]["webhook_style"])
    wh_button_row.addWidget(wh_button)
    form.addRow(wh_button_row)
    url = QLabel(payload["webhook_form"]["url_text"])
    url.setStyleSheet(payload["webhook_form"]["url_style"])
    form.addRow(url)
    wh_layout.addWidget(config)

    guide = QGroupBox(payload["groups"]["guide"])
    guide.setStyleSheet(payload["groups"]["style_sheet"])
    guide_layout = QVBoxLayout(guide)
    guide_text = QTextEdit()
    guide_text.setReadOnly(True)
    guide_text.setMaximumHeight(payload["guide"]["max_height_px"])
    guide_text.setStyleSheet(payload["guide"]["style_sheet"])
    guide_text.setHtml(payload["guide"]["html"])
    guide_layout.addWidget(guide_text)
    wh_layout.addWidget(guide)

    alerts_group = QGroupBox(payload["groups"]["alerts"])
    alerts_group.setStyleSheet(payload["groups"]["style_sheet"])
    alerts_layout = QVBoxLayout(alerts_group)
    alert_table = QTableWidget()
    alert_table.setColumnCount(payload["alert_table"]["column_count"])
    alert_table.setHorizontalHeaderLabels(payload["alert_table"]["columns"])
    from PySide6.QtWidgets import QHeaderView

    alert_table.horizontalHeader().setSectionResizeMode(
        getattr(QHeaderView, payload["alert_table"]["header_resize_mode"])
    )
    alert_table.setAlternatingRowColors(
        payload["alert_table"]["alternating_row_colors"]
    )
    alert_table.verticalHeader().setVisible(
        payload["alert_table"]["vertical_header_visible"]
    )
    fill_table(
        alert_table,
        payload["alert_table"]["rows"],
        None,
        payload["bot_table"]["cell_alignment_value"],
    )
    alerts_layout.addWidget(alert_table)
    wh_layout.addWidget(alerts_group)
    tabs.addTab(webhook_tab, payload["tabs"]["all_titles"][1])

    console = QTextEdit()
    console.setReadOnly(True)
    console.setFont(
        QFont(payload["console"]["font_family"], payload["console"]["font_size_pt"])
    )
    console.setStyleSheet(payload["console"]["style_sheet"])
    console.setLineWrapMode(
        getattr(QTextEdit, "LineWrapMode").__members__[payload["console"]["line_wrap"]]
    )
    for line in payload["console"]["lines"]:
        console.append(line)
    tabs.addTab(console, payload["tabs"]["all_titles"][3])
    main_layout.addWidget(tabs)
    window.statusBar().showMessage(payload["status_bar"]["text"])
    return window


def fill_table(table, rows, colors, alignment):
    """Put every row the payload carries into `table`."""
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QTableWidgetItem

    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column, text in enumerate(row):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignmentFlag(alignment))
            if colors is not None and colors[row_index][column] is not None:
                item.setForeground(QColor(colors[row_index][column]))
            table.setItem(row_index, column, item)


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_two_sides_paint_one_picture_and_carry_one_skin(name):
    """The surface painted a different window than the shipped one paints."""
    spec = BY_NAME[name]
    assert_same_skin(
        build_old_side=lambda: window_painted_by_the_window(spec),
        build_new_side=lambda: window_painted_by_the_model(model_payload(spec)),
        size=PIXEL_SIZE,
        control_rule=CONTROL_RULE,
        note=name,
    )


@pytest.mark.parametrize("name", PICTURE_CASES)
def test_the_painted_window_shows_more_than_one_colour(name):
    """A window that paints one colour compares against anything."""
    spec = BY_NAME[name]
    image = render_offscreen(window_painted_by_the_window(spec), PIXEL_SIZE)
    found = assert_picture_can_report(image, note=name)
    assert found > 1, name
    assert colour_count(image) == found


def test_the_picture_comparison_can_report_a_difference():
    """Two different real inputs painted one picture, so no render reports."""
    first = BY_NAME["no_manager"]
    second = BY_NAME["bridge_running"]
    assert_cases_paint_differently(
        old_side=render_offscreen(window_painted_by_the_window(first), PIXEL_SIZE),
        new_side=render_offscreen(
            window_painted_by_the_model(model_payload(second)), PIXEL_SIZE
        ),
    )
    assert_pictures_differ(
        old_side=render_offscreen(window_painted_by_the_window(second), PIXEL_SIZE),
        new_side=render_offscreen(
            window_painted_by_the_model(model_payload(first)), PIXEL_SIZE
        ),
        note="the other direction",
    )


def test_the_host_font_question_is_asked_and_not_assumed():
    """The suite pinned the machine it was written on.

    With no font database every family resolves to a box advancing one em
    per character, so two strings of equal length need equal width. With
    a font database the glyphs decide. Both answers are handled here.
    """
    app()
    narrow = QLabel("iiii")
    wide = QLabel("WWWW")
    if has_real_fonts():
        assert narrow.sizeHint().width() != wide.sizeHint().width()
    else:
        assert narrow.sizeHint().width() == wide.sizeHint().width()


@skip_unless_no_fonts
def test_two_equal_length_symbols_measure_alike_without_fonts():
    """Every family is a box font, and two equal-length names still differ."""
    app()
    assert app_font_advance_px("IIII") == app_font_advance_px("WWWW")


@skip_unless_real_fonts
def test_two_equal_length_symbols_measure_apart_with_fonts():
    """The glyphs decide their own width, and two names still measure alike."""
    app()
    assert app_font_advance_px("IIII") != app_font_advance_px("WWWW")


def test_a_payload_the_test_changed_never_reaches_a_render():
    """A changed payload reached a render, which measures the host's fonts."""
    payload = dict(model_payload(BY_NAME["no_manager"]))
    payload["status_bar"] = {"text": "changed", "ready_text": "changed"}
    with pytest.raises(AssertionError, match="never came off"):
        window_painted_by_the_model(payload)


def test_the_two_sides_paint_the_same_size():
    """One side rendered at a different size than the other."""
    spec = BY_NAME["no_manager"]
    old = render_offscreen(window_painted_by_the_window(spec), PIXEL_SIZE)
    new = render_offscreen(window_painted_by_the_model(model_payload(spec)), PIXEL_SIZE)
    assert (old.width(), old.height()) == (new.width(), new.height())
    assert_pictures_match(old_side=old, new_side=new)


# ---------------------------------------------------------------------
# What the shipped window asks for that no picture carries
# ---------------------------------------------------------------------


def test_the_split_the_window_asks_for_is_the_one_the_surface_declares():
    """Qt rewrites a split after layout, so the request is what is compared."""
    with QtSeams() as seams:
        window = build_window(BY_NAME["no_manager"], seams)
        window._timer.stop()
        assert seams.sizes == [list(surface.SPLIT_SIZES)], seams.sizes
        settled = splitter_of(window).sizes()
    assert len(settled) == 2, settled
    assert sum(surface.SPLIT_SIZES) == 1100


def strftime_patterns(spec):
    """Every pattern one drive formats a clock reading with."""
    with QtSeams(seconds=spec["seconds"]) as seams:
        window = build_window(spec, seams)
        window._refresh_dashboard()
        return list(seams.strftime)


def test_the_alert_stamp_uses_the_format_the_surface_declares():
    """The alert table formatted its clock reading with another pattern.

    Log records carry the same pattern, so the two alert rows are read as
    the difference between a drive with alerts and one without.
    """
    with_alerts = strftime_patterns(BY_NAME["bridge_alerts"])
    without = strftime_patterns(BY_NAME["bridge_running"])
    assert set(with_alerts) == {surface.ALERT_TIME_FORMAT}, set(with_alerts)
    assert len(with_alerts) - len(without) == 2, (with_alerts, without)


def test_the_activity_log_stamp_uses_the_format_the_surface_declares():
    """The activity log formatted its clock reading with another pattern."""
    FixedDateTime.recorded = []
    spec = BY_NAME["webhook_start"]
    drive_old(spec)
    assert FixedDateTime.recorded == [surface.LOG_TIME_FORMAT], FixedDateTime.recorded


def test_the_new_bot_button_values_are_the_ones_qt_carries():
    """The declared Ok and Cancel values are not the ones Qt uses."""
    assert surface.OK_BUTTON_VALUE == int(OK_FROM_QT.value)
    assert surface.CANCEL_BUTTON_VALUE == int(CANCEL_FROM_QT.value)
    assert surface.NEW_BOT_BUTTONS_VALUE == int((OK_FROM_QT | CANCEL_FROM_QT).value)


@pytest.mark.parametrize("name", ["create_declined", "create_made", "create_refused"])
def test_the_new_bot_box_is_the_same_box_on_both_sides(name):
    """The new-bot box asks a different question on one side."""
    spec = BY_NAME[name]
    old = drive_old(spec)["boxes"]
    new = drive_new(spec)["payload"]["boxes"]
    assert len(old) == 1, old
    assert len(new) == 1, new
    assert old[0] == new[0], (old[0], new[0])


def test_the_about_box_is_the_same_box_on_both_sides():
    """The About box shows different text on one side."""
    BoxRecorder.RAISED = []
    with QtSeams() as seams:
        window = build_window(BY_NAME["no_manager"], seams)
        window._timer.stop()
        window._show_about()
        raised = list(BoxRecorder.RAISED)
    model = surface.StockMainWindowModel()
    model.show_about()
    payload = surface.build_view_model(model)
    assert raised == payload["boxes"], (raised, payload["boxes"])


def test_the_bot_buttons_log_the_same_lines_on_both_sides():
    """A bot button logged a different line on one side."""
    with QtSeams() as seams:
        window = build_window(BY_NAME["no_manager"], seams)
        window._timer.stop()
        window._start_bot()
        window._stop_bot()
        window._delete_bot()
        window._open_settings()
        appended = seams.appended_to(window._status_log)
    model = surface.StockMainWindowModel(clock=surface.ClockSource(time_text=LOG_STAMP))
    for label in surface.SECONDARY_BUTTON_LABELS:
        model.bot_button_handler(label)()
    model.open_settings()
    assert appended == model.log_lines, (appended, model.log_lines)


def test_the_alert_table_hides_its_row_numbers_on_both_sides():
    """The alert table started showing a row-number column."""
    with QtSeams() as seams:
        window = build_window(BY_NAME["no_manager"], seams)
        header = window._alert_table.verticalHeader()
        assert header.isVisibleTo(window._alert_table) is False
        assert window._bot_table.verticalHeader().isVisibleTo(window._bot_table) is (
            False
        )
        assert (
            window._alert_table.horizontalHeader().isVisibleTo(window._alert_table)
            is True
        )
    payload = surface.build_view_model(surface.StockMainWindowModel())
    assert payload["alert_table"]["vertical_header_visible"] is False


def test_the_webhook_button_hands_its_coroutine_to_the_loop_on_both_sides():
    """The alert server was never handed to the loop that runs it."""
    spec = BY_NAME["webhook_start"]
    driven = drive_old(spec)
    assert driven["window"]._bridge_standin.scheduled == ["start"]
    stopped = drive_old(BY_NAME["webhook_stop"])
    assert stopped["window"]._bridge_standin.scheduled == ["stop"]
    new_start = drive_new(spec)["model"]
    assert new_start.bridge.scheduled == ["start"]
    new_stop = drive_new(BY_NAME["webhook_stop"])["model"]
    assert new_stop.bridge.scheduled == ["stop"]


def test_the_console_pane_colours_a_record_the_same_way_on_both_sides():
    """A console line took a different colour for its level on one side."""
    root = logging.getLogger()
    before = list(root.handlers)
    with QtSeams() as seams:
        window = build_window(BY_NAME["no_manager"], seams)
        handler = [one for one in root.handlers if one not in before][0]
        for level in surface.HANDLER_LEVEL_COLORS:
            record = logging.LogRecord(
                "acervator.probe",
                getattr(logging, level),
                __file__,
                1,
                f"a {level} line",
                None,
                None,
            )
            handler.emit(record)
        lines = seams.appended_to(window._console)
    model = surface.StockMainWindowModel()
    for level in surface.HANDLER_LEVEL_COLORS:
        model.append_to_console(level, f"a {level} line")
    assert len(lines) == len(surface.HANDLER_LEVEL_COLORS), lines
    for shipped, mine in zip(lines, model.console_lines):
        colour = shipped.split("color:", 1)[1].split('"', 1)[0]
        assert colour == mine.split("color:", 1)[1].split('"', 1)[0]
        assert shipped.endswith(mine.split(">", 1)[1])


def test_the_launcher_return_hides_the_window_on_both_sides():
    """Going back to the launcher left the window on screen."""
    called = []
    with QtSeams() as seams:
        window = build_window(BY_NAME["no_manager"], seams)
        window._timer.stop()
        window._back_to_launcher()
        without_callback = window.isHidden()
        window.set_launcher_callback(lambda: called.append(1))
        window._back_to_launcher()
    model = surface.StockMainWindowModel()
    model.back_to_launcher()
    assert model.hidden is without_callback is True
    model.set_launcher_callback(lambda: None)
    model.back_to_launcher()
    assert called == [1]
    assert [call[0] for call in model.calls].count(surface.LAUNCHER_CALLED) == 1
    assert [call[0] for call in model.calls].count(surface.LAUNCHER_ABSENT) == 1


# ---------------------------------------------------------------------
# Order independence, shared state and the world
# ---------------------------------------------------------------------


def test_the_shipped_window_adds_one_handler_to_the_shared_root_logger():
    """The window stopped writing the console pane from the root logger."""
    root = logging.getLogger()
    before = list(root.handlers)
    with QtSeams() as seams:
        window = build_window(BY_NAME["no_manager"], seams)
        window._timer.stop()
        added = [handler for handler in root.handlers if handler not in before]
        assert len(added) == 1, added
        assert added[0].__class__.__name__ == "_StockLogHandler"
    assert list(root.handlers) == before, root.handlers


def test_every_swapped_name_is_put_back_after_a_drive_and_after_a_refusal():
    """A swapped name outlived its drive and reached the next test."""
    plain = drive_old(BY_NAME["happy"])
    assert plain["swapped_during"] is False, "the seams were not installed"
    assert plain["seams"].restored() is True
    refused = drive_old(REFUSING_CASES["text_where_a_number_belongs"])
    assert refused["seams"].restored() is True
    assert QTextEdit.append is plain["seams"].saved[(QTextEdit, "append")]
    assert QSplitter.setSizes is plain["seams"].saved[(QSplitter, "setSizes")]


def test_the_swap_watcher_reports_a_name_that_was_not_put_back():
    """The swap watcher answers restored whatever the names hold."""
    seams = QtSeams()
    with seams:
        assert seams.restored() is False
    assert seams.restored() is True
    saved = seams.saved[(QTextEdit, "append")]
    QTextEdit.append = lambda widget, text: None
    try:
        assert seams.restored() is False
    finally:
        QTextEdit.append = saved
    assert seams.restored() is True


def test_a_case_reads_the_same_whatever_ran_before_it():
    """A driven case depends on what another case left behind."""
    first = digest(new_state(drive_new(BY_NAME["happy"])))
    drive_new(BY_NAME["many_bots"])
    drive_new(BY_NAME["bridge_alerts"])
    assert digest(new_state(drive_new(BY_NAME["happy"]))) == first


@pytest.fixture
def refuse_outside_connections(monkeypatch):
    """Count and refuse every outward connection this test attempts.

    The counter watches this process only. A child process opens its own
    sockets and is never seen here; the subprocess probes below carry
    their own refusal.
    """
    attempted: list = []
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def outside(address) -> bool:
        host = address[0] if isinstance(address, tuple) else address
        return str(host) not in LOOPBACK

    def refuse(address):
        attempted.append(address)
        raise OSError("this test may not reach outside the process")

    def watched_connect(self, address, *_f, **_n):
        if outside(address):
            return refuse(address)
        return real_connect(self, address, *_f, **_n)

    def watched_connect_ex(self, address, *_f, **_n):
        if outside(address):
            return refuse(address)
        return real_connect_ex(self, address, *_f, **_n)

    monkeypatch.setattr(socket.socket, "connect", watched_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", watched_connect_ex)
    monkeypatch.setattr(
        socket, "create_connection", lambda address, *_f, **_n: refuse(address)
    )
    yield attempted


def test_no_driven_case_reaches_outside_the_process(refuse_outside_connections):
    """A driven case opened a socket to a host."""
    for spec in ALL_CASES:
        drive_new(spec)
    drive_old(BY_NAME["happy"])
    assert refuse_outside_connections == [], refuse_outside_connections


def test_the_connection_counter_reports_two_real_outside_addresses(
    refuse_outside_connections,
):
    """The connection counter reports nothing whatever a test reaches for."""
    first = ("www.tradingview.com", 443)
    second = ("api.alpaca.markets", 443)
    with pytest.raises(OSError):
        socket.create_connection(first, timeout=1)
    with pytest.raises(OSError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(second)
    assert len(refuse_outside_connections) == 2, refuse_outside_connections
    assert first in refuse_outside_connections


def test_no_driven_case_writes_a_file_under_a_throwaway_home(tmp_path, monkeypatch):
    """A driven case wrote into the operator's own tree."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("ACERVATOR_TEST_HOME", str(home))
    for spec in ALL_CASES:
        drive_new(spec)
    drive_old(BY_NAME["happy"])
    assert sorted(home.rglob("*")) == [], sorted(home.rglob("*"))


def test_the_throwaway_home_check_reports_a_file_that_was_written(tmp_path):
    """The throwaway-home check reports nothing whatever a run writes."""
    home = tmp_path / "home"
    home.mkdir()
    assert sorted(home.rglob("*")) == []
    (home / "seeded.json").write_text("{}", encoding="utf-8", newline="\n")
    assert sorted(home.rglob("*")) == [home / "seeded.json"]


# ---------------------------------------------------------------------
# The bridge, and a process that never loads Qt
# ---------------------------------------------------------------------


def fresh_pane_model():
    surface.PANE_MODEL = surface.StockMainWindowModel()


def test_the_bridge_registers_the_stock_main_window_method():
    """The Electron renderer cannot reach the stock window."""
    from src.core import desktop_bridge

    registry = desktop_bridge.build_registry()
    assert surface.METHOD in registry
    assert registry[surface.METHOD] is surface.view_model


def test_the_bridge_resets_the_window_state_on_request():
    """A fresh paint carried the last paint's rows."""
    fresh_pane_model()
    filled = surface.view_model(
        {
            "reset": True,
            "build": True,
            "bot_manager": {
                "aggregate": AGGREGATE,
                "statuses": [bot()],
            },
            "refresh": 1,
        }
    )
    assert filled["bot_table"]["row_count"] == 1
    empty = surface.view_model({"reset": True})
    assert empty["bot_table"]["row_count"] == 0
    assert empty["tabs"]["titles"] == []
    fresh_pane_model()


def test_the_bridge_answer_is_json_serialisable():
    """A value in the answer cannot cross the bridge."""
    fresh_pane_model()
    answered = surface.view_model(
        {
            "reset": True,
            "build": True,
            "bridge": {
                "running": True,
                "port": 8742,
                "total_alerts": 1,
                "alerts": [
                    {
                        "timestamp": ALERT_STAMP_SECONDS,
                        "symbol": "AAPL",
                        "action": "buy",
                        "price": 12.5,
                        "strategy": "Fold",
                    }
                ],
            },
            "clock": {"seconds": 100.0, "alert_time_text": "01:02:03"},
            "refresh": 1,
            "toggle_webhook": True,
        }
    )
    text = json.dumps(answered)
    assert json.loads(text)["alert_table"]["row_count"] == 1
    fresh_pane_model()


BRIDGE_PROBE = (
    "import json, sys\n"
    "from src.core import desktop_bridge\n"
    "frame = desktop_bridge.handle_line(json.dumps({'id': 1, 'method':"
    " 'stock_main_window.state', 'params': {'reset': True, 'build': True,"
    " 'bot_manager': {'aggregate': {'total_realised_pnl': 12.5,"
    " 'total_trades': 4, 'running': 2}, 'statuses': [{'bot_id': 'abcdefghij',"
    " 'symbol': 'AAPL', 'mode': 'swing', 'state': 'running', 'stats':"
    " {'total_pnl': 1.5, 'current_position': 3, 'avg_entry_price': 10.0,"
    " 'current_price': 11.0, 'total_trades': 2, 'signals_received': 7}}]},"
    " 'refresh': 1}}), desktop_bridge.build_registry())\n"
    "print(json.dumps({'frame': json.loads(frame) if isinstance(frame, str)"
    " else frame, 'qt': [name for name in sys.modules if"
    " name.startswith('PySide6')]}))\n"
)

NOTHING_AT_IMPORT_PROBE = """
import json
import os
import sys
import tempfile
from pathlib import Path

root = Path(tempfile.mkdtemp(prefix='acervator-stock-probe-'))
os.environ['HOME'] = str(root)
os.environ['USERPROFILE'] = str(root)

opened = []
real_open = open


def watched_open(file, *found, **named):
    opened.append(str(file))
    return real_open(file, *found, **named)


import builtins
builtins.open = watched_open

import time
clock = []
real_time = time.time
real_monotonic = time.monotonic
real_localtime = time.localtime
time.time = lambda: clock.append('time') or real_time()
time.monotonic = lambda: clock.append('monotonic') or real_monotonic()
time.localtime = lambda *a: clock.append('localtime') or real_localtime(*a)

import socket
reached = []


def refuse(address, *found, **named):
    reached.append(str(address))
    raise OSError('the probe may not reach outside')


socket.create_connection = refuse
socket.socket.connect = lambda self, address, *_f, **_n: refuse(address)

opened_before = list(opened)
clock_before = list(clock)
from src.gui.main_tabs import stock_main_window_surface as s

built_at_import = s.PANE_MODEL.tab_titles != []
opened_at_import = [name for name in opened[len(opened_before):]]
clock_at_import = list(clock[len(clock_before):])
model = s.StockMainWindowModel()
model.build()
answer = {'built_at_import': built_at_import,
          'built_on_request': model.tab_titles != [],
          'title': s.WINDOW_TITLE,
          'qt': [name for name in sys.modules if name.startswith('PySide6')],
          'opened_at_import': [n for n in opened_at_import if 'stock_main_window' in n],
          'clock_at_import': clock_at_import,
          'reached_at_import': list(reached),
          'made_under_home': sorted(str(p) for p in root.rglob('*'))}
builtins.open = real_open
print(json.dumps(answer))
"""


def run_script(source, env=None):
    """Run one probe in a fresh process and return what it printed."""
    where = dict(os.environ)
    where.pop("ACERVATOR_TEST_HOME", None)
    if env:
        where.update(env)
    done = subprocess.run(
        [sys.executable, "-"],
        input=source.encode("utf-8"),
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=300,
        check=False,
        env=where,
    )
    assert done.returncode == 0, done.stderr.decode(errors="replace")
    return json.loads(done.stdout.decode("utf-8").splitlines()[-1])


def test_the_surface_answers_over_the_bridge_without_loading_qt():
    """Reaching the stock window pulled Qt into the backend."""
    answered = run_script(BRIDGE_PROBE)
    assert answered["qt"] == [], answered["qt"]
    assert answered["frame"]["ok"] is True
    result = answered["frame"]["result"]
    assert result["bot_table"]["rows"][0] == [
        "abcdefgh",
        "AAPL",
        "swing",
        "running",
        "3",
        "$10.00",
        "$11.00",
        "$+1.50",
        "2",
        "7",
    ]
    assert result["cards"]["values"] == ["$+12.50", "4", "2", "1", "---", "---"]


def test_the_qt_probe_can_report_qt():
    """The Qt probe reports absent whatever the process loaded."""
    loaded = run_script("import PySide6.QtCore\n" + BRIDGE_PROBE)
    assert loaded["qt"] != []
    assert loaded["frame"]["ok"] is True


def test_importing_the_surface_reads_no_file_and_no_clock():
    """Loading the surface read a file, read the clock, or built the window."""
    answered = run_script(NOTHING_AT_IMPORT_PROBE)
    assert answered["built_at_import"] is False, answered
    assert answered["built_on_request"] is True, answered
    assert answered["title"] == surface.WINDOW_TITLE
    assert answered["qt"] == [], answered["qt"]
    assert answered["clock_at_import"] == [], answered
    assert answered["reached_at_import"] == [], answered
    assert answered["made_under_home"] == [], answered
    assert answered["opened_at_import"] == [], answered


def test_the_import_probe_can_report_a_file_a_clock_and_a_connection():
    """The import probe reports nothing whatever the module does."""
    probe = NOTHING_AT_IMPORT_PROBE.replace(
        "from src.gui.main_tabs import stock_main_window_surface as s",
        "time.time()\n"
        "with open(root / 'stock_main_window-seeded.json', 'w') as fh:\n"
        "    fh.write('{}')\n"
        "try:\n"
        "    socket.create_connection(('example.invalid', 443))\n"
        "except OSError:\n"
        "    pass\n"
        "from src.gui.main_tabs import stock_main_window_surface as s",
    )
    answered = run_script(probe)
    assert answered["clock_at_import"] == ["time"], answered
    assert answered["reached_at_import"] != [], answered
    assert answered["made_under_home"] != [], answered
    assert answered["opened_at_import"] != [], answered


def test_the_surface_loads_no_qt_module_and_reaches_for_nothing():
    """The surface grew an import that pulls Qt into the backend."""
    tree = parsed(SURFACE_SOURCE)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(name.startswith("PySide6") for name in imported), imported
    assert not any(name.startswith("shiboken") for name in imported), imported
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "open" not in called
    reached = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    for forbidden in ("read_text", "write_text", "mkdir", "urlopen", "monotonic"):
        assert forbidden not in reached, forbidden


def test_the_import_scan_reports_a_module_the_shipped_file_does_load():
    """The import scan reports nothing whatever a file imports."""
    imported = set()
    for node in ast.walk(parsed(WINDOW_SOURCE)):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert any(name.startswith("PySide6") for name in imported), imported


def test_this_file_imports_only_what_the_fast_lane_installs():
    """This file needs a package the CI fast lane never installs."""
    from tests.test_ci_fast_lane_packages import offending_imports

    offences = [
        line
        for line in offending_imports(REPO_ROOT / "tests")
        if Path(__file__).name in line
    ]
    assert offences == [], offences
