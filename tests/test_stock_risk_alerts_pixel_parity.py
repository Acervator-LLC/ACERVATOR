"""The stock window, risk tab and alerts tab paint the same colours after
the token migration.

A failure means a `design_system` token edit, or a change to
`src/gui/stock_main_window.py`, `src/gui/risk_tab.py` or
`src/gui/alerts_tab.py`, moved pixels in the operator's live GUI.

Every expected colour is the LITERAL the file shipped before the tokens
replaced it. An assertion fed by the token it measures cannot falsify that
token: both sides move together and a wrong colour passes.

Colours are read off the RENDER. `QPainter` calls and stylesheet strings
report what the widget was told to paint, not what reached the screen. The
`:hover` rules are the exception -- a pseudo-state paints no pixel in an
offscreen grab, so those three colours are pinned as stylesheet text and are
marked below as not pixel-proven.
"""

import logging
import os
import struct
import time
from collections import Counter

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

SUCCESS = "#00ff88"
WARNING = "#ffaa00"
ERROR = "#ff3366"
PRIMARY = "#00ffcc"
STATUS_INFO = "#00aaff"
TEXT_HIGH = "#e0e0f0"
TEXT_INACTIVE = "#aaaaaa"
TEXT_PLACEHOLDER = "#555555"
METRIC_LABEL = "#888888"
METRIC_BORDER = "#2a2a3f"
SURFACE_CHART = "#0a0a12"
SURFACE_CONTROL = "#1a1a2e"
PANEL_BORDER = "#1a1a3f"

STOCK_PANEL = "#0a1020"
STOCK_BORDER = "#1a2a4f"
STOCK_BODY = "#aabbcc"
STOCK_LOG_SURFACE = "#080c18"
STOCK_POSITIVE = "#00cc66"
STOCK_NEGATIVE = "#ff4466"
STOCK_WARNING = "#ddaa00"
STOCK_NEUTRAL = "#8899aa"
STOCK_BUTTON_BORDER = "#2a3a5f"
LOG_DEBUG = "#444455"
LOG_CRITICAL = "#ff0033"
LOG_TIMESTAMP = "#555566"

TAB_SIZE = (1100, 700)
WINDOW_SIZE = (1400, 900)


def colours_in(image):
    """Count every painted colour in `image`, keyed by #rrggbb."""
    from PySide6.QtGui import QImage

    rgb = image.convertToFormat(QImage.Format_RGB32)
    raw = bytes(rgb.constBits())
    stride, width = rgb.bytesPerLine(), rgb.width()
    packed = Counter()
    for y in range(rgb.height()):
        packed.update(struct.unpack_from(f"<{width}I", raw, y * stride))
    return Counter({f"#{v & 0xFFFFFF:06x}": n for v, n in packed.items()})


def assert_painted(widget, size, present, absent=()):
    """Assert each `present` colour reaches a pixel and each `absent` does not."""
    from tests.qt_pixel import render_widget

    seen = colours_in(render_widget(widget, size=size))
    for colour in present:
        assert seen.get(colour, 0) > 0, f"{colour} painted no pixel"
    for colour in absent:
        assert seen.get(colour, 0) == 0, f"{colour} painted {seen[colour]} pixels"
    return seen


class _Snapshot:
    total_exposure = 1000.0
    running_count = 4
    asset_exposures = {"BTC": 500.0, "ETH": 300.0, "SOL": 200.0}
    exchange_exposures = {"coinbase": 700.0, "kraken": 300.0}


class _Action:
    value = "HALT"


class _Alert:
    def __init__(self, severity):
        self.timestamp = time.time()
        self.severity = severity
        self.rule_name = "max_drawdown"
        self.message = "drawdown exceeded"
        self.action_taken = _Action()


class _Risk:
    """The risk-manager surface `RiskTab.refresh` reads."""

    def __init__(self, critical=0, alerts_1h=0):
        self._critical = critical
        self._alerts_1h = alerts_1h
        self.snapshots = [_Snapshot()]
        self.alerts = [_Alert("critical"), _Alert("warning")]

    def get_status(self):
        return {
            "drawdown_pct": 20.0,
            "peak_pnl": 12.5,
            "total_exposure": 1000.0,
            "critical_alerts": self._critical,
            "alerts_1h": self._alerts_1h,
            "rules": {
                "max_drawdown": {"threshold": 25.0, "action": "halt", "enabled": True},
                "max_exposure": {"threshold": 80.0, "action": "warn", "enabled": False},
            },
        }


class _Priority:
    def __init__(self, value):
        self.value = value


class _Notification:
    def __init__(self, priority, acknowledged):
        self.timestamp = time.time()
        self.priority = _Priority(priority)
        self.title = "Fold complete"
        self.message = "BTC fold closed at target"
        self.channels_sent = ["IN_APP"]
        self.acknowledged = acknowledged


class _Notifications:
    """The notification-manager surface `AlertsTab.refresh` reads."""

    def __init__(self, unread=0):
        self.unacknowledged_count = unread
        self.history = [
            _Notification("low", True),
            _Notification("medium", True),
            _Notification("high", True),
            _Notification("critical", True),
            _Notification("critical", False),
        ]

    def get_config(self):
        return {
            "telegram_configured": True,
            "sms_configured": False,
            "rules": {
                "fold_complete": {"priority": "high", "channels": ["IN_APP", "SOUND"]},
                "bot_halted": {"priority": "critical", "channels": ["TELEGRAM"]},
            },
        }


BOTS = [
    {
        "bot_id": "aaaabbbbcccc",
        "symbol": "AAPL",
        "mode": "swing",
        "state": "running",
        "stats": {
            "total_pnl": 12.5,
            "current_position": 3,
            "avg_entry_price": 100.0,
            "current_price": 104.0,
            "total_trades": 7,
            "signals_received": 4,
        },
    },
    {
        "bot_id": "ddddeeeeffff",
        "symbol": "MSFT",
        "mode": "signal",
        "state": "stopped",
        "stats": {
            "total_pnl": -8.25,
            "current_position": 0,
            "avg_entry_price": 300.0,
            "current_price": 292.0,
            "total_trades": 3,
            "signals_received": 1,
        },
    },
]


class _Bridge:
    """The TradingView bridge surface `_refresh_dashboard` reads."""

    running = True
    alert_history: list[object] = []

    def get_summary(self):
        return {"port": 8742, "total_alerts": 3}


class _Telegram:
    """The notification-manager surface `AlertsTab._test_telegram` reads."""

    def __init__(self, fails=False):
        self._fails = fails
        self.configured = None
        self.sent = None

    def configure_telegram(self, token, chat_id):
        self.configured = (token, chat_id)

    def _send_telegram(self, title, message, extra):
        self.sent = (title, message, extra)
        if self._fails:
            raise RuntimeError("network down")


@pytest.fixture(autouse=True)
def app():
    """Every test in this module renders, and a render needs the application."""
    from tests.qt_pixel import ensure_app

    return ensure_app()


@pytest.fixture
def stock_window():
    """A StockMainWindow with its refresh timer stopped and its log handler
    detached on teardown; the handler installs itself on the root logger."""
    from src.gui.stock_main_window import StockMainWindow

    root = logging.getLogger()
    before = set(root.handlers)
    window = StockMainWindow()
    window._timer.stop()
    added = [h for h in root.handlers if h not in before]
    assert len(added) == 1, added
    yield window, added[0]
    root.removeHandler(added[0])


def test_drawdown_gauge_paints_each_severity_arc():
    """A failure means a drawdown severity arc, its ground or its text moved."""
    from src.gui.risk_tab import DrawdownGauge

    bands = ((5.0, SUCCESS), (15.0, WARNING), (22.0, ERROR))
    for pct, expected in bands:
        gauge = DrawdownGauge()
        gauge.set_value(pct)
        others = [c for _, c in bands if c != expected]
        assert_painted(
            gauge,
            (200, 200),
            present=[expected, SURFACE_CONTROL, TEXT_HIGH, METRIC_LABEL],
            absent=others,
        )


def test_exposure_bar_paints_its_ground_border_and_chunk():
    """A failure means the exposure bar's skin or its chunk colour moved."""
    from src.gui.risk_tab import ExposureBar

    default = ExposureBar("BTC")
    default.set_value(42.0, 500.0)
    assert_painted(
        default,
        (420, 40),
        present=[SURFACE_CONTROL, METRIC_BORDER, TEXT_HIGH, TEXT_INACTIVE, STATUS_INFO],
    )

    explicit = ExposureBar("ETH")
    explicit.set_value(42.0, 500.0, ERROR)
    assert_painted(
        explicit, (420, 40), present=[SURFACE_CONTROL, ERROR], absent=[STATUS_INFO]
    )


@pytest.mark.parametrize(
    "critical,alerts_1h,expected",
    [(2, 2, ERROR), (0, 3, WARNING), (0, 0, PRIMARY)],
)
def test_risk_tab_status_label_paints_each_state(critical, alerts_1h, expected):
    """A failure means the CRITICAL, WARNING or MONITORING banner recoloured."""
    from src.gui.risk_tab import RiskTab

    tab = RiskTab()
    tab.refresh(_Risk(critical, alerts_1h))
    assert_painted(tab._lbl_status, (280, 34), present=[expected])


def test_risk_tab_paints_its_panels_and_tables():
    """A failure means a risk group box, exposure tier or table cell recoloured."""
    from src.gui.risk_tab import RiskTab

    tab = RiskTab()
    tab.refresh(_Risk(critical=1, alerts_1h=1))
    assert_painted(
        tab,
        TAB_SIZE,
        present=[
            SURFACE_CHART,
            METRIC_BORDER,
            PRIMARY,
            SUCCESS,
            WARNING,
            ERROR,
            STATUS_INFO,
            TEXT_HIGH,
            TEXT_INACTIVE,
        ],
    )


def test_risk_tab_carries_the_shipped_stylesheets():
    """A failure means the risk tab's QSS text changed."""
    from PySide6.QtWidgets import QGroupBox

    from src.gui.risk_tab import ExposureBar, RiskTab
    from tests.qt_pixel import render_widget

    group = (
        "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
        "border-radius: 6px; color: #00ffcc; }"
    )
    bar_skin = (
        "QProgressBar { background: #1a1a2e; border: 1px solid #2a2a3f; "
        "border-radius: 3px; height: 18px; color: #e0e0f0; font-size: 10px; }"
        "QProgressBar::chunk { background: %s; border-radius: 2px; }"
    )

    bar = ExposureBar("BTC")
    assert bar._bar.styleSheet() == bar_skin % STATUS_INFO
    assert bar._label.styleSheet() == "color: #aaaaaa; font-size: 11px;"
    assert bar._value_label.styleSheet() == "color: #e0e0f0; font-size: 11px;"
    bar.set_value(42.0, 500.0, ERROR)
    assert bar._bar.styleSheet() == bar_skin % ERROR

    tab = RiskTab()
    titles = {"Asset Exposure", "Exchange Exposure", "Risk Alerts", "Risk Rules"}
    boxes = [b for b in tab.findChildren(QGroupBox) if b.title() in titles]
    assert {b.title() for b in boxes} == titles
    assert {b.styleSheet() for b in boxes} == {group}
    assert tab._lbl_peak.styleSheet() == "color: #00ff88; font-size: 13px;"
    assert tab._lbl_exposure.styleSheet() == "color: #e0e0f0; font-size: 13px;"
    assert tab._lbl_bots.styleSheet() == "color: #aaaaaa; font-size: 12px;"
    assert (
        tab._lbl_status.styleSheet()
        == "color: #00ffcc; font-size: 14px; font-weight: bold;"
    )

    for widget, size, wanted in (
        (bar._bar, (420, 40), (SURFACE_CONTROL, METRIC_BORDER, ERROR)),
        (boxes[0], (400, 200), (SURFACE_CHART, METRIC_BORDER, PRIMARY)),
        (tab._lbl_peak, (240, 30), (SUCCESS,)),
        (tab._lbl_exposure, (260, 30), (TEXT_HIGH,)),
        (tab._lbl_bots, (240, 30), (TEXT_INACTIVE,)),
        (tab._lbl_status, (280, 34), (PRIMARY,)),
    ):
        seen = colours_in(render_widget(widget, size=size))
        for colour in wanted:
            assert seen.get(colour, 0) > 0, f"{colour} painted no pixel"


def test_alerts_tab_paints_its_chrome():
    """A failure means an alerts group box, button or status label recoloured."""
    from src.gui.alerts_tab import AlertsTab

    tab = AlertsTab()
    tab.refresh(_Notifications(unread=3))
    assert_painted(
        tab,
        TAB_SIZE,
        present=[
            SURFACE_CHART,
            METRIC_BORDER,
            PRIMARY,
            PANEL_BORDER,
            STATUS_INFO,
            WARNING,
            METRIC_LABEL,
            SUCCESS,
            TEXT_PLACEHOLDER,
            ERROR,
            TEXT_HIGH,
        ],
    )
    assert_painted(tab._lbl_unread, (200, 30), present=[WARNING])
    assert_painted(tab._lbl_status, (280, 34), present=[PRIMARY])
    assert_painted(tab._sms_status, (200, 30), present=[METRIC_LABEL])
    assert_painted(tab._tg_test, (200, 44), present=[PANEL_BORDER, STATUS_INFO])
    assert_painted(tab._btn_ack, (200, 40), present=[PANEL_BORDER, WARNING])
    assert_painted(tab._btn_save, (220, 44), present=[PRIMARY, SURFACE_CHART])


def test_alerts_tab_read_state_paints_the_muted_unread_label():
    """A failure means the zero-unread label stopped being the muted grey."""
    from src.gui.alerts_tab import AlertsTab

    tab = AlertsTab()
    tab.refresh(_Notifications(unread=0))
    assert_painted(tab._lbl_unread, (200, 30), present=[METRIC_LABEL], absent=[WARNING])


def test_alerts_tab_history_paints_every_priority():
    """A failure means a notification priority cell recoloured."""
    from src.gui.alerts_tab import AlertsTab

    tab = AlertsTab()
    tab.refresh(_Notifications(unread=1))
    assert_painted(
        tab._history_table,
        (900, 220),
        present=[METRIC_LABEL, STATUS_INFO, WARNING, ERROR, TEXT_HIGH],
    )


def test_alerts_tab_routing_table_paints_yes_and_no():
    """A failure means the routing table's Yes/No colours moved."""
    from src.gui.alerts_tab import AlertsTab

    tab = AlertsTab()
    tab.refresh(_Notifications())
    assert_painted(tab._rules_table, (900, 160), present=[SUCCESS, TEXT_PLACEHOLDER])


@pytest.mark.parametrize(
    "token,fails,expected",
    [("", False, ERROR), ("tok", False, SUCCESS), ("tok", True, ERROR)],
)
def test_alerts_tab_telegram_status_paints_pass_and_fail(token, fails, expected):
    """A failure means the Telegram test result stopped painting pass or fail."""
    from src.gui.alerts_tab import AlertsTab

    tab = AlertsTab()
    tab._notif = _Telegram(fails=fails)
    tab._tg_token.setText(token)
    tab._tg_chat.setText("chat" if token else "")
    tab._test_telegram()
    assert tab._tg_status.text()
    assert_painted(tab._tg_status, (280, 30), present=[expected])


def test_alerts_tab_carries_the_shipped_stylesheets():
    """A failure means the alerts tab's QSS text changed.

    The save button's `:hover` colour paints no pixel offscreen, so this pin
    is the only check on it.
    """
    from PySide6.QtWidgets import QGroupBox

    from src.gui.alerts_tab import AlertsTab
    from tests.qt_pixel import render_widget

    tab = AlertsTab()
    titles = {"Telegram Bot", "SMS Alerts", "Event Routing", "Notification History"}
    boxes = [b for b in tab.findChildren(QGroupBox) if b.title() in titles]
    assert {b.title() for b in boxes} == titles
    assert {b.styleSheet() for b in boxes} == {
        "QGroupBox { background: #0a0a12; border: 1px solid #2a2a3f; "
        "border-radius: 6px; color: #00ffcc; }"
    }
    assert tab._tg_test.styleSheet() == (
        "QPushButton { background: #1a1a3f; color: #00aaff; "
        "border: 1px solid #00aaff; border-radius: 4px; padding: 6px; }"
    )
    assert tab._btn_save.styleSheet() == (
        "QPushButton { background: #00ffcc; color: #0a0a12; "
        "border: none; border-radius: 4px; padding: 8px; font-weight: bold; }"
        "QPushButton:hover { background: #00ddaa; }"
    )
    assert tab._btn_ack.styleSheet() == (
        "QPushButton { background: #1a1a3f; color: #ffaa00; "
        "border: 1px solid #ffaa00; border-radius: 4px; padding: 4px 10px; }"
    )
    assert tab._sms_status.styleSheet() == "color: #888;"
    assert tab._lbl_unread.styleSheet() == "color: #ffaa00; font-size: 12px;"

    for widget, size, wanted in (
        (boxes[0], (400, 200), (SURFACE_CHART, METRIC_BORDER, PRIMARY)),
        (tab._tg_test, (200, 44), (PANEL_BORDER, STATUS_INFO)),
        (tab._btn_save, (220, 44), (PRIMARY, SURFACE_CHART)),
        (tab._btn_ack, (200, 40), (PANEL_BORDER, WARNING)),
        (tab._sms_status, (200, 30), (METRIC_LABEL,)),
        (tab._lbl_unread, (200, 30), (WARNING,)),
    ):
        seen = colours_in(render_widget(widget, size=size))
        for colour in wanted:
            assert seen.get(colour, 0) > 0, f"{colour} painted no pixel"


def test_stock_bot_table_paints_the_pnl_colours():
    """A failure means the stock bot table's gain/loss colours moved."""
    from src.gui.stock_main_window import StockBotTable

    table = StockBotTable()
    table.update_bots(BOTS)
    assert_painted(table, (1000, 200), present=[STOCK_POSITIVE, STOCK_NEGATIVE])


@pytest.mark.parametrize(
    "pnl,expected,other",
    [(12.5, STOCK_POSITIVE, STOCK_NEGATIVE), (-12.5, STOCK_NEGATIVE, STOCK_POSITIVE)],
)
def test_stock_stat_card_paints_the_pnl_colour(pnl, expected, other):
    """A failure means the P/L stat card stopped colouring by sign."""
    from src.gui.stock_main_window import StockStatCard

    card = StockStatCard("Total P/L")
    card.set_value(f"${pnl:+,.2f}", expected)
    assert_painted(card, (220, 90), present=[expected], absent=[other])


def test_stock_window_paints_its_chrome(stock_window):
    """A failure means the stock window's panels, buttons or logs recoloured."""
    from PySide6.QtWidgets import QGroupBox, QPushButton, QTextEdit

    window, _ = stock_window
    assert_painted(window._market_status, (360, 40), present=[STATUS_INFO, STOCK_PANEL])
    assert_painted(window._webhook_status, (300, 30), present=[METRIC_LABEL])
    assert_painted(window._wh_url_label, (300, 30), present=[METRIC_LABEL])
    assert_painted(window._btn_new_bot, (240, 44), present=[STATUS_INFO, SURFACE_CHART])
    assert_painted(
        window._btn_start_wh, (240, 44), present=[STATUS_INFO, SURFACE_CHART]
    )
    assert_painted(window._console, (900, 120), present=[STOCK_LOG_SURFACE])

    control = [
        b for b in window.findChildren(QPushButton) if b.text() in ("Start", "Stop")
    ]
    assert len(control) == 2
    assert_painted(
        control[0],
        (120, 40),
        present=[STOCK_BORDER, STOCK_BODY, STOCK_BUTTON_BORDER],
    )

    box = [g for g in window.findChildren(QGroupBox) if g.title() == "Activity Log"]
    assert len(box) == 1
    assert_painted(box[0], (500, 220), present=[STOCK_PANEL, STOCK_BORDER, STATUS_INFO])

    guide = [
        e for e in window.findChildren(QTextEdit) if "TradingView Alert" in e.toHtml()
    ]
    assert len(guide) == 1
    assert_painted(
        guide[0],
        (760, 220),
        present=[
            STOCK_LOG_SURFACE,
            STATUS_INFO,
            METRIC_LABEL,
            STOCK_POSITIVE,
            TEXT_HIGH,
        ],
    )


def test_stock_window_webhook_guide_keeps_its_alert_placeholders(stock_window):
    """A failure means the guide's {{ticker}} / {{close}} placeholders changed."""
    from PySide6.QtWidgets import QTextEdit

    window, _ = stock_window
    guide = [
        e for e in window.findChildren(QTextEdit) if "TradingView Alert" in e.toHtml()
    ][0]
    text = guide.toPlainText()
    assert '"symbol": "{{ticker}}",' in text
    assert '"price": {{close}},' in text
    assert text.count("{") == 5 and text.count("}") == 5


@pytest.mark.parametrize(
    "level,name,expected",
    [
        (10, "DEBUG", LOG_DEBUG),
        (20, "INFO", STOCK_NEUTRAL),
        (30, "WARNING", STOCK_WARNING),
        (40, "ERROR", STOCK_NEGATIVE),
        (50, "CRITICAL", LOG_CRITICAL),
        (25, "UNMAPPED", STOCK_NEUTRAL),
    ],
)
def test_stock_console_paints_each_log_level(stock_window, level, name, expected):
    """A failure means a console log level, or the unmapped fallback, recoloured."""
    window, handler = stock_window
    window._console.clear()
    record = logging.LogRecord("acervator.probe", level, __file__, 1, "msg", None, None)
    record.levelname = name
    handler.emit(record)
    assert_painted(window._console, (900, 60), present=[expected, STOCK_LOG_SURFACE])


@pytest.mark.parametrize(
    "level,expected",
    [
        ("info", STOCK_NEUTRAL),
        ("success", STOCK_POSITIVE),
        ("warning", STOCK_WARNING),
        ("error", STOCK_NEGATIVE),
        ("unmapped", STOCK_NEUTRAL),
    ],
)
def test_stock_activity_log_paints_each_level(stock_window, level, expected):
    """A failure means an activity-log level, or its timestamp, recoloured."""
    window, _ = stock_window
    window._status_log.clear()
    window._log("message", level)
    assert_painted(
        window._status_log,
        (760, 60),
        present=[expected, LOG_TIMESTAMP, STOCK_LOG_SURFACE],
    )


@pytest.mark.parametrize(
    "session,expected",
    [
        ("REGULAR", STOCK_POSITIVE),
        ("PRE_MARKET", STOCK_WARNING),
        ("CLOSED", STOCK_NEGATIVE),
    ],
)
def test_stock_market_status_paints_each_session(stock_window, session, expected):
    """A failure means an equity market-session colour moved."""
    from src.stocks.market_hours import MarketSession

    window, _ = stock_window

    class _Hours:
        def get_status_string(self):
            return session

        def get_session(self):
            return getattr(MarketSession, session)

    window._market_hours = _Hours()
    window._refresh_dashboard()
    assert_painted(window._market_status, (360, 40), present=[expected, STOCK_PANEL])


def test_stock_webhook_status_paints_the_active_colour(stock_window):
    """A failure means the running-webhook label stopped painting green."""
    from src.stocks.market_hours import MarketSession

    window, _ = stock_window

    class _Hours:
        def get_status_string(self):
            return "REGULAR"

        def get_session(self):
            return MarketSession.REGULAR

    window._market_hours = _Hours()
    window._tv_bridge = _Bridge()
    window._refresh_dashboard()
    assert_painted(window._webhook_status, (320, 30), present=[STOCK_POSITIVE])


def test_stock_window_carries_the_shipped_stylesheets(stock_window):
    """A failure means the stock window's QSS text changed.

    The two `:hover` colours paint no pixel offscreen, so these pins are the
    only check on them.
    """
    from PySide6.QtWidgets import QGroupBox, QPushButton

    from tests.qt_pixel import render_widget

    window, handler = stock_window
    assert window._market_status.styleSheet() == (
        "color: #00aaff; font-size: 13px; font-weight: bold; "
        "padding: 4px 12px; background: #0a1020; "
        "border-radius: 4px; border: 1px solid #1a2a4f;"
    )
    assert window._webhook_status.styleSheet() == (
        "color: #888; font-size: 11px; padding: 4px 8px;"
    )
    assert window._wh_url_label.styleSheet() == "color: #888; font-family: Consolas;"
    assert window._btn_new_bot.styleSheet() == (
        "QPushButton { background: #00aaff; color: #0a0a12; "
        "border: none; border-radius: 6px; padding: 8px 16px; font-weight: bold; }"
        "QPushButton:hover { background: #0088dd; }"
    )
    assert window._btn_start_wh.styleSheet() == (
        "QPushButton { background: #00aaff; color: #0a0a12; "
        "border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold; }"
    )
    control = [
        b for b in window.findChildren(QPushButton) if b.text() in ("Start", "Stop")
    ]
    assert {b.styleSheet() for b in control} == {
        "QPushButton { background: #1a2a4f; color: #aabbcc; "
        "border: 1px solid #2a3a5f; border-radius: 4px; padding: 6px 12px; }"
        "QPushButton:hover { background: #2a3a6f; }"
    }
    assert window._status_log.styleSheet() == (
        "QTextEdit { background: #080c18; color: #aabbcc; border: none; }"
    )
    assert window._console.styleSheet() == (
        "QTextEdit { background: #080c18; color: #aabbcc; border: none; padding: 4px; }"
    )
    boxes = [
        g
        for g in window.findChildren(QGroupBox)
        if g.title()
        in {
            "TradingView Chart",
            "Activity Log",
            "TradingView Webhook Configuration",
            "TradingView Alert Format",
            "Recent Alerts",
        }
    ]
    assert len(boxes) == 5
    assert {b.styleSheet() for b in boxes} == {
        "QGroupBox { background: #0a1020; border: 1px solid #1a2a4f; "
        "border-radius: 6px; color: #00aaff; }"
    }
    assert handler.COLORS == {
        "DEBUG": "#444455",
        "INFO": "#8899aa",
        "WARNING": "#ddaa00",
        "ERROR": "#ff4466",
        "CRITICAL": "#ff0033",
    }

    for widget, size, wanted in (
        (window._market_status, (360, 40), (STATUS_INFO, STOCK_PANEL)),
        (window._webhook_status, (300, 30), (METRIC_LABEL,)),
        (window._wh_url_label, (300, 30), (METRIC_LABEL,)),
        (window._btn_new_bot, (240, 44), (STATUS_INFO, SURFACE_CHART)),
        (window._btn_start_wh, (240, 44), (STATUS_INFO, SURFACE_CHART)),
        (control[0], (120, 40), (STOCK_BORDER, STOCK_BODY, STOCK_BUTTON_BORDER)),
        (window._console, (900, 120), (STOCK_LOG_SURFACE,)),
        (boxes[0], (500, 220), (STOCK_PANEL, STOCK_BORDER, STATUS_INFO)),
    ):
        seen = colours_in(render_widget(widget, size=size))
        for colour in wanted:
            assert seen.get(colour, 0) > 0, f"{colour} painted no pixel"
