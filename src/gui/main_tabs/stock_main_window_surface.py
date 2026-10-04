"""stock_main_window_surface.py -- the stock trading window, without Qt.

Describes the window equity trading runs in: a market-status strip, six
stat cards, and a tab book holding a Trading tab, a Webhooks tab, an
optional Paper Trader tab and a Console tab. The Trading tab splits a
ten-column bot table against a TradingView chart and an indicator panel,
with an activity log underneath.

``StockMainWindowModel`` holds the window's state. ``build`` fills the
menu, the strip, the cards and the tabs. ``refresh`` is the two-second
tick that rewrites the market line, the webhook line, the cards, the bot
table and the alert table. ``create_bot``, ``toggle_webhook``, ``log``,
``append_to_console``, ``back_to_launcher`` and ``show_about`` are the
window's other paths. Every step is appended to ``calls``.

``BotManagerSource``, ``BridgeSource``, ``MarketSource``, ``ClockSource``,
``AlertSource`` and ``PanelSink`` are plain stand-ins for the stock bot
manager, the TradingView bridge, the market-hours reader, the clock, one
webhook alert and the indicator panel, so the window can be driven over
the bridge from values alone.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``stock_main_window.state`` method. Every value below is written out
here rather than read from ``src.gui.stock_main_window``, so a value
changed on one side alone is reported. Nothing here imports Qt and
nothing here reads a clock: a time reaches the model as a value.

``MISSING_STAT_ATTRIBUTES`` names two cards the shipped window reads and
never builds. Every refresh that has a bot manager stops there, which is
why ``SKIPPED_WHEN_MANAGER_PRESENT`` lists what no tick reaches.
"""

from __future__ import annotations

from typing import Any, Optional

from ...trading.ta_engine import DEFAULT_WEIGHTS
from .. import design_system as ds

METHOD = "stock_main_window.state"

ACCESSIBLE_NAME = "Stock Main Window"
WINDOW_TITLE = "Acervator — Stock Trading"
MINIMUM_WIDTH_PX = 1400
MINIMUM_HEIGHT_PX = 900

CONTENT_MARGINS = (16, 12, 16, 12)
CONTENT_SPACING_PX = 10

FILE_MENU_TITLE = "&File"
HELP_MENU_TITLE = "&Help"
SETTINGS_ACTION = "&Settings"
LAUNCHER_ACTION = "&Back to Launcher"
EXIT_ACTION = "E&xit"
ABOUT_ACTION = "&About"
MENU_SEPARATOR = "---"
FILE_MENU_ITEMS = (SETTINGS_ACTION, MENU_SEPARATOR, LAUNCHER_ACTION, EXIT_ACTION)
HELP_MENU_ITEMS = (ABOUT_ACTION,)

MARKET_INITIAL_TEXT = "Market Status: Loading..."
MARKET_INITIAL_STYLE = (
    f"color: {ds.STATUS_INFO}; font-size: 13px; font-weight: bold; "
    f"padding: 4px 12px; background: {ds.CARD_STOCK_PANEL}; "
    f"border-radius: 4px; border: 1px solid {ds.CARD_STOCK_BORDER};"
)
MARKET_TEXT_FORMAT = "Market: {status}"
MARKET_STYLE_FORMAT = (
    "color: {color}; font-size: 13px; font-weight: bold; "
    f"padding: 4px 12px; background: {ds.CARD_STOCK_PANEL}; "
    "border-radius: 4px; border: 1px solid {color}44;"
)

SESSION_REGULAR = "regular"
SESSION_PRE_MARKET = "pre_market"
SESSION_AFTER_HOURS = "after_hours"
SESSION_OPEN_COLOR = ds.STOCK_POSITIVE
SESSION_EXTENDED_COLOR = ds.STOCK_WARNING
SESSION_SHUT_COLOR = ds.STOCK_NEGATIVE

WEBHOOK_INITIAL_TEXT = "Webhook: Inactive"
WEBHOOK_INITIAL_STYLE = (
    f"color: {ds.CARD_METRIC_LABEL}; font-size: 11px; padding: 4px 8px;"
)
WEBHOOK_ACTIVE_TEXT_FORMAT = "Webhook: Active (port {port}) | Alerts: {total_alerts}"
WEBHOOK_ACTIVE_STYLE = f"color: {ds.STOCK_POSITIVE}; font-size: 11px;"

STAT_CARD_LABELS = (
    "Total P/L",
    "Total Trades",
    "Active Bots",
    "Open Positions",
    "Day Trades (5d)",
    "Unsettled",
)
STAT_CARD_INITIAL_VALUE = "---"
STAT_CARD_ACCESSIBLE_NAME = "Stock Stat Card"
CARD_VALUE_COLOR = ds.CARD_STOCK_VALUE
STAT_CARD_STYLE_NAME = "STOCK_CARD"
STAT_PNL_FORMAT = "${pnl:+,.2f}"
WIN_RATE_FORMAT = "{win_rate:.1f}%"

MISSING_STAT_ATTRIBUTES = ("_stat_signals", "_stat_winrate")
MISSING_ATTRIBUTE_ERROR = "AttributeError"
SKIPPED_WHEN_MANAGER_PRESENT = (
    "signals_card",
    "win_rate_card",
    "indicator_panel",
    "throttled_tabs",
    "alert_table",
)

BOT_TABLE_ACCESSIBLE_NAME = "Stock Bot Table"
BOT_TABLE_COLUMNS = (
    "Bot ID",
    "Symbol",
    "Mode",
    "State",
    "Position",
    "Entry $",
    "Current $",
    "P/L",
    "Trades",
    "Signals",
)
BOT_TABLE_COLUMN_COUNT = 10
PNL_COLUMN = 7
CELL_ALIGNMENT = "AlignCenter"
CELL_ALIGNMENT_VALUE = 132
BOT_ID_LENGTH = 8
ENTRY_FORMAT = "${avg_entry_price:.2f}"
CURRENT_FORMAT = "${current_price:.2f}"
PNL_FORMAT = "${pnl:+.2f}"
NO_CELL_COLOR: Optional[str] = None

STATS_KEY = "stats"
BOT_ID_KEY = "bot_id"
SYMBOL_KEY = "symbol"
MODE_KEY = "mode"
STATE_KEY = "state"
PNL_KEY = "total_pnl"
POSITION_KEY = "current_position"
ENTRY_KEY = "avg_entry_price"
PRICE_KEY = "current_price"
TRADES_KEY = "total_trades"
SIGNALS_KEY = "signals_received"
WINS_KEY = "winning_trades"
AGGREGATE_PNL_KEY = "total_realised_pnl"
RUNNING_KEY = "running"
PORT_KEY = "port"
TOTAL_ALERTS_KEY = "total_alerts"

DEFAULT_TEXT = ""
DEFAULT_NUMBER = 0

SPLIT_ORIENTATION = "Horizontal"
SPLIT_HANDLE_WIDTH_PX = 5
SPLIT_CHILDREN_COLLAPSIBLE = False
SPLIT_SIZES = (500, 600)
PANEL_MARGINS = (0, 0, 0, 0)

NEW_BOT_BUTTON_TEXT = "＋ New Accumulation Bot"
NEW_BOT_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.STATUS_INFO}; "
    f"color: {ds.SURFACE_CHART}; "
    "border: none; border-radius: 6px; padding: 8px 16px; "
    "font-weight: bold; }"
    f"QPushButton:hover {{ background: {ds.STOCK_BUTTON_HOVER}; }}"
)
SECONDARY_BUTTON_LABELS = ("Start", "Stop", "Delete")
SECONDARY_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.CARD_STOCK_BORDER}; "
    f"color: {ds.CARD_STOCK_BODY}; "
    f"border: 1px solid {ds.CARD_STOCK_BUTTON_BORDER}; "
    f"border-radius: 4px; padding: 6px 12px; }}"
    f"QPushButton:hover {{ background: {ds.CARD_STOCK_BUTTON_HOVER}; }}"
)

GROUP_BOX_STYLE = (
    f"QGroupBox {{ background: {ds.CARD_STOCK_PANEL}; "
    f"border: 1px solid {ds.CARD_STOCK_BORDER}; "
    f"border-radius: 6px; color: {ds.STATUS_INFO}; }}"
)

CHART_GROUP_TITLE = "TradingView Chart"
CHART_SYMBOL = "AAPL"
CHART_THEME = "dark"
CHART_STRETCH = 3
CHART_FALLBACK_TEXT = "TradingView chart requires PySide6-WebEngine"
PANEL_STRETCH = 2
PANEL_MODE = "scrumming"
PANEL_SOURCE_MODES = ("swing", "signal")

LOG_GROUP_TITLE = "Activity Log"
LOG_MAX_HEIGHT_PX = 150
LOG_STYLE = (
    f"QTextEdit {{ background: {ds.CARD_STOCK_LOG_SURFACE}; "
    f"color: {ds.CARD_STOCK_BODY}; border: none; }}"
)
LOG_TIME_FORMAT = "%H:%M:%S"
LOG_LINE_FORMAT = (
    f'<span style="color:{ds.STOCK_LOG_TIMESTAMP}">[{{time_text}}]</span> '
    '<span style="color:{color}">{message}</span>'
)
LOG_INFO = "info"
LOG_SUCCESS = "success"
LOG_WARNING = "warning"
LOG_ERROR = "error"
LOG_LEVEL_COLORS = {
    LOG_INFO: ds.STATUS_NEUTRAL,
    LOG_SUCCESS: ds.STOCK_POSITIVE,
    LOG_WARNING: ds.STOCK_WARNING,
    LOG_ERROR: ds.STOCK_NEGATIVE,
}
LOG_FALLBACK_COLOR = ds.STATUS_NEUTRAL

WEBHOOK_CONFIG_TITLE = "TradingView Webhook Configuration"
PORT_MINIMUM = 1024
PORT_MAXIMUM = 65535
PORT_DEFAULT = 8742
PORT_ROW_LABEL = "Webhook Port:"
AUTH_ROW_LABEL = "Auth Token:"
AUTH_PLACEHOLDER = "Optional auth token for security"
AUTH_ECHO_MODE = "Password"
START_WEBHOOK_TEXT = "Start Webhook Server"
STOP_WEBHOOK_TEXT = "Stop Webhook Server"
WEBHOOK_BUTTON_STYLE = (
    f"QPushButton {{ background: {ds.STATUS_INFO}; "
    f"color: {ds.SURFACE_CHART}; "
    "border: none; border-radius: 4px; padding: 8px 16px; font-weight: bold; }"
)
URL_INITIAL_TEXT = "URL: Not started"
URL_STOPPED_TEXT = "URL: Stopped"
URL_RUNNING_FORMAT = "URL: http://localhost:{port}/webhook"
URL_LABEL_STYLE = f"color: {ds.CARD_METRIC_LABEL}; font-family: Consolas;"

GUIDE_TITLE = "TradingView Alert Format"
GUIDE_MAX_HEIGHT_PX = 200
GUIDE_STYLE = (
    f"QTextEdit {{ background: {ds.CARD_STOCK_LOG_SURFACE}; "
    f"color: {ds.CARD_STOCK_BODY}; "
    "border: none; font-family: Consolas; font-size: 11px; }"
)
GUIDE_HTML = (
    f'<span style="color:{ds.STATUS_INFO}">TradingView Alert Message Format '
    "(JSON):</span><br><br>"
    f'<span style="color:{ds.CARD_METRIC_LABEL}">Set your alert webhook URL '
    "to:</span><br>"
    f'<span style="color:{ds.STOCK_POSITIVE}">http://YOUR_IP:8742/webhook'
    "</span><br><br>"
    f'<span style="color:{ds.CARD_METRIC_LABEL}">Alert message body:</span><br>'
    f'<span style="color:{ds.TEXT_HIGH}">{{</span><br>'
    f'<span style="color:{ds.TEXT_HIGH}">&nbsp;&nbsp;"symbol": "{{{{ticker}}}}",'
    "</span><br>"
    f'<span style="color:{ds.TEXT_HIGH}">&nbsp;&nbsp;"action": "buy",</span><br>'
    f'<span style="color:{ds.TEXT_HIGH}">&nbsp;&nbsp;"price": {{{{close}}}},</span><br>'
    f'<span style="color:{ds.TEXT_HIGH}">&nbsp;&nbsp;"strategy": "My Strategy"'
    "</span><br>"
    f'<span style="color:{ds.TEXT_HIGH}">}}</span><br><br>'
    f'<span style="color:{ds.CARD_METRIC_LABEL}">Supported actions: buy, sell, '
    "close</span>"
)

ALERTS_GROUP_TITLE = "Recent Alerts"
ALERT_COLUMNS = ("Time", "Symbol", "Action", "Price", "Strategy")
ALERT_COLUMN_COUNT = 5
ALERT_HISTORY_LIMIT = 50
ALERT_TIME_FORMAT = "%H:%M:%S"
ALERT_PRICE_FORMAT = "${price:.2f}"
ALERT_HEADER_RESIZE_MODE = "Stretch"
ALERT_ALTERNATING_ROW_COLORS = True
ALERT_VERTICAL_HEADER_VISIBLE = False

TAB_TRADING = "Trading"
TAB_WEBHOOKS = "Webhooks"
TAB_PAPER_TRADER = "Paper Trader"
TAB_CONSOLE = "Console"
TABS_MOVABLE = True
TABS_DOCUMENT_MODE = True
PAPER_TRADER_ASSET_TYPE = "equity"
PAPER_TRADER_LOGGER = "acervator"
PAPER_TRADER_FAILURE_FORMAT = "Paper Trader tab unavailable: {error}"
REMOVED_TABS = ("analytics", "risk", "journal", "alerts")

CONSOLE_FONT_FAMILY = "Consolas"
CONSOLE_FONT_SIZE_PT = 9
CONSOLE_LINE_WRAP = "NoWrap"
CONSOLE_STYLE = (
    f"QTextEdit {{ background: {ds.CARD_STOCK_LOG_SURFACE}; "
    f"color: {ds.CARD_STOCK_BODY}; "
    "border: none; padding: 4px; }"
)
HANDLER_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
HANDLER_DATE_FORMAT = "%H:%M:%S"
HANDLER_CONNECTION = "AutoConnection"
HANDLER_LINE_FORMAT = '<span style="color:{color}">{message}</span>'
HANDLER_LEVEL_COLORS = {
    "DEBUG": ds.STOCK_LOG_DEBUG,
    "INFO": ds.STATUS_NEUTRAL,
    "WARNING": ds.STOCK_WARNING,
    "ERROR": ds.STOCK_NEGATIVE,
    "CRITICAL": ds.STOCK_LOG_CRITICAL,
}
HANDLER_FALLBACK_COLOR = ds.STATUS_NEUTRAL
HANDLER_ROOT_LOGGER = ""

STATUS_BAR_TEXT = "Ready — Stock Trading Mode"

REFRESH_INTERVAL_MS = 2000
TAB_REFRESH_SECONDS = 4

NEW_BOT_TITLE = "New Accumulation Bot"
#: The voter count is filled from DEFAULT_WEIGHTS, never typed in.
NEW_BOT_TEXT_FORMAT = (
    "Create an Accumulation Trading bot for stocks?\n\n"
    "• Harvest-Fold cycle (same as crypto mode)\n"
    "• {indicator_count}-indicator TA voting engine\n"
    "• MR Inspector + Boosted Fold\n"
    "• Smart Wire cross-compounding\n"
    "• Market hours enforcement\n"
    "• PDT protection (3 day-trades / 5 days)\n"
    "• T+2 settlement tracking\n\n"
    "Symbol: AAPL | Target: $200 | TF: 1D"
)
OK_BUTTON_VALUE = 1024
CANCEL_BUTTON_VALUE = 4194304
NEW_BOT_BUTTONS_VALUE = OK_BUTTON_VALUE | CANCEL_BUTTON_VALUE
BOT_SYMBOL = "AAPL"
BOT_TARGET_BALANCE = 200.0
BOT_TIMEFRAME = "1D"
REGISTER_REFUSED_FORMAT = "Bot creation refused by CapitalRegistry: {reason}"
BOT_CREATED_FORMAT = "Accumulation bot created: {symbol} target=${target_balance}"

START_BOT_MESSAGE = "Start bot — select a bot first"
STOP_BOT_MESSAGE = "Stop bot — select a bot first"
DELETE_BOT_MESSAGE = "Delete bot — select a bot first"
SETTINGS_MESSAGE = "Settings dialog — coming soon"
NO_BRIDGE_MESSAGE = "TradingView bridge not initialized"
WEBHOOK_STOPPED_MESSAGE = "Webhook server stopped"
WEBHOOK_STARTED_FORMAT = "Webhook server started on port {port}"

ABOUT_TITLE = "About"
#: The version is read from the program, never typed in.
ABOUT_TEXT_FORMAT = (
    "Acervator — Stock Trading v{version}\n\n"
    "TradingView Webhook Integration\n"
    "Alpaca Broker Support\n"
    "Signal • DCA • Swing • Grid Bots\n"
    "Market Hours Awareness\n"
    "Shared Analytics & Risk Management"
)


def running_version() -> str:
    """Returns ``src.__version__`` for ``ABOUT_TEXT_FORMAT``."""
    from src import __version__

    return str(__version__)


def about_text() -> str:
    """``ABOUT_TEXT_FORMAT`` filled with ``running_version``."""
    return ABOUT_TEXT_FORMAT.format(version=running_version())


WINDOW_READY_MESSAGE = "Stock Trading window initialized"
REFRESH_CRASH_FORMAT = "STOCK DASHBOARD: refresh crashed: %s"
PANEL_FAILURE_FORMAT = "stock dashboard refresh failed — tiles are stale: %s"
CONSOLE_FAILURE_FORMAT = "stock window log append failed: %s"

OUTCOME_DECLINED = "declined"
OUTCOME_REFUSED = "refused"
OUTCOME_CREATED = "created"
OUTCOME_NO_BRIDGE = "no_bridge"
OUTCOME_STOPPED = "stopped"
OUTCOME_STARTED = "started"
OUTCOME_CRASHED = "crashed"
OUTCOME_DONE = "done"
NO_OUTCOME: Optional[str] = None

ACTIONS = {
    "new_bot_button.clicked": "create_bot",
    "bot_button.clicked": "bot_button_handler",
    "webhook_button.clicked": "toggle_webhook",
    "refresh_timer.timeout": "refresh",
    "console_handler.append_signal": "append_to_console",
}
RUNTIME_CONNECT_TOTAL = 7
SIGNAL_NAMES = ("_append_signal",)
SIGNAL_EMIT_TOTAL = 1
TIMERS = {"refresh_timer": REFRESH_INTERVAL_MS}
TIMER_DELAYS_MS = (REFRESH_INTERVAL_MS,)
TIMERS_STARTED = ("refresh_timer",)
THREADS_BUILT: tuple[str, ...] = ()
THREADS_STARTED: tuple[str, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()
BUS_EMITS: tuple[str, ...] = ()

BUILD_START = "build.start"
BUILD_MENU = "build.menu"
BUILD_MARKET_BAR = "build.market_bar"
BUILD_CARDS = "build.cards"
BUILD_TRADING_TAB = "build.trading_tab"
BUILD_CHART = "build.chart"
BUILD_CHART_FAILED = "build.chart_failed"
BUILD_PANEL = "build.panel"
BUILD_PANEL_FAILED = "build.panel_failed"
BUILD_WEBHOOK_TAB = "build.webhook_tab"
BUILD_PAPER_TRADER = "build.paper_trader"
BUILD_PAPER_TRADER_FAILED = "build.paper_trader_failed"
BUILD_CONSOLE = "build.console"
BUILD_HANDLER = "build.handler"
BUILD_STATUS_BAR = "build.status_bar"
BUILD_TIMER = "build.timer"
BUILD_RETURN = "build.return"
REFRESH_START = "refresh.start"
REFRESH_MARKET = "refresh.market"
REFRESH_WEBHOOK = "refresh.webhook"
REFRESH_BOTS = "refresh.bots"
REFRESH_TABLE = "refresh.table"
REFRESH_POSITIONS = "refresh.positions"
REFRESH_MISSING_CARD = "refresh.missing_card"
REFRESH_THROTTLED = "refresh.throttled"
REFRESH_THROTTLE_SKIPPED = "refresh.throttle_skipped"
REFRESH_ALERTS = "refresh.alerts"
REFRESH_CRASHED = "refresh.crashed"
REFRESH_RETURN = "refresh.return"
CREATE_START = "create.start"
CREATE_DECLINED = "create.declined"
CREATE_REFUSED = "create.refused"
CREATE_MADE = "create.made"
WEBHOOK_START = "webhook.start"
WEBHOOK_NO_BRIDGE = "webhook.no_bridge"
WEBHOOK_STOPPED = "webhook.stopped"
WEBHOOK_STARTED = "webhook.started"
WEBHOOK_AUTH_SET = "webhook.token_set"
LOG_APPEND = "log.append"
CONSOLE_APPEND = "console.append"
CONSOLE_FAILED = "console.failed"
LAUNCHER_HIDDEN = "launcher.hidden"
LAUNCHER_CALLED = "launcher.called"
LAUNCHER_ABSENT = "launcher.absent"
ABOUT_SHOWN = "about.shown"
BOT_BUTTON = "bot_button"
SETTINGS_OPENED = "settings.opened"

CALL_NAMES = (
    BUILD_START,
    BUILD_MENU,
    BUILD_MARKET_BAR,
    BUILD_CARDS,
    BUILD_TRADING_TAB,
    BUILD_CHART,
    BUILD_CHART_FAILED,
    BUILD_PANEL,
    BUILD_PANEL_FAILED,
    BUILD_WEBHOOK_TAB,
    BUILD_PAPER_TRADER,
    BUILD_PAPER_TRADER_FAILED,
    BUILD_CONSOLE,
    BUILD_HANDLER,
    BUILD_STATUS_BAR,
    BUILD_TIMER,
    BUILD_RETURN,
    REFRESH_START,
    REFRESH_MARKET,
    REFRESH_WEBHOOK,
    REFRESH_BOTS,
    REFRESH_TABLE,
    REFRESH_POSITIONS,
    REFRESH_MISSING_CARD,
    REFRESH_THROTTLED,
    REFRESH_THROTTLE_SKIPPED,
    REFRESH_ALERTS,
    REFRESH_CRASHED,
    REFRESH_RETURN,
    CREATE_START,
    CREATE_DECLINED,
    CREATE_REFUSED,
    CREATE_MADE,
    WEBHOOK_START,
    WEBHOOK_NO_BRIDGE,
    WEBHOOK_STOPPED,
    WEBHOOK_STARTED,
    WEBHOOK_AUTH_SET,
    LOG_APPEND,
    CONSOLE_APPEND,
    CONSOLE_FAILED,
    LAUNCHER_HIDDEN,
    LAUNCHER_CALLED,
    LAUNCHER_ABSENT,
    ABOUT_SHOWN,
    BOT_BUTTON,
    SETTINGS_OPENED,
)

ModelCall = list


def market_color(session: Any) -> str:
    """Green while the market trades, amber either side of it, red otherwise."""
    if session == SESSION_REGULAR:
        return SESSION_OPEN_COLOR
    if session in (SESSION_PRE_MARKET, SESSION_AFTER_HOURS):
        return SESSION_EXTENDED_COLOR
    return SESSION_SHUT_COLOR


def market_style(color: Any) -> str:
    """The market line's skin, whose border is the line's own colour."""
    return MARKET_STYLE_FORMAT.format(color=color)


def market_text(status: Any) -> str:
    """The market line, from the reader's own status wording."""
    return MARKET_TEXT_FORMAT.format(status=status)


def webhook_active_text(port: Any, total_alerts: Any) -> str:
    """The webhook line while the alert server is listening."""
    return WEBHOOK_ACTIVE_TEXT_FORMAT.format(port=port, total_alerts=total_alerts)


def pnl_color(pnl: Any) -> str:
    """Green at or above break-even, red below it.

    A not-a-number is below nothing, so it takes the loss colour.
    """
    return ds.STOCK_POSITIVE if pnl >= 0 else ds.STOCK_NEGATIVE


def bot_stats(status: dict) -> dict:
    """The one nested reading block a bot row is filled from."""
    return status.get(STATS_KEY, {})


def bot_row_cells(status: dict) -> list:
    """The ten cell texts one stock bot fills a table row with."""
    stats = bot_stats(status)
    pnl = stats.get(PNL_KEY, DEFAULT_NUMBER)
    return [
        status.get(BOT_ID_KEY, DEFAULT_TEXT)[:BOT_ID_LENGTH],
        status.get(SYMBOL_KEY, DEFAULT_TEXT),
        status.get(MODE_KEY, DEFAULT_TEXT),
        status.get(STATE_KEY, DEFAULT_TEXT),
        str(stats.get(POSITION_KEY, DEFAULT_NUMBER)),
        ENTRY_FORMAT.format(avg_entry_price=stats.get(ENTRY_KEY, DEFAULT_NUMBER)),
        CURRENT_FORMAT.format(current_price=stats.get(PRICE_KEY, DEFAULT_NUMBER)),
        PNL_FORMAT.format(pnl=pnl),
        str(stats.get(TRADES_KEY, DEFAULT_NUMBER)),
        str(stats.get(SIGNALS_KEY, DEFAULT_NUMBER)),
    ]


def bot_row_colors(status: dict) -> list:
    """The colour each cell of one bot row is drawn in, or none where default."""
    colors: list = [NO_CELL_COLOR] * BOT_TABLE_COLUMN_COUNT
    colors[PNL_COLUMN] = pnl_color(bot_stats(status).get(PNL_KEY, DEFAULT_NUMBER))
    return colors


def open_position_count(statuses: list) -> int:
    """How many of the listed bots hold a position that is not flat."""
    return sum(
        1
        for status in statuses
        if bot_stats(status).get(POSITION_KEY, DEFAULT_NUMBER) != 0
    )


def total_signals(statuses: list) -> Any:
    """Every signal the listed bots have taken, added up."""
    return sum(
        bot_stats(status).get(SIGNALS_KEY, DEFAULT_NUMBER) for status in statuses
    )


def total_wins(statuses: list) -> Any:
    """Every winning trade the listed bots have booked, added up."""
    return sum(bot_stats(status).get(WINS_KEY, DEFAULT_NUMBER) for status in statuses)


def win_rate(wins: Any, trades: Any) -> Any:
    """Winning trades as a percentage, zero where no trade has closed."""
    return (wins / trades * 100) if trades > 0 else 0


def panel_statuses(statuses: list) -> list:
    """The swing and signal bots, relabelled for the indicator panel."""
    return [
        {**status, MODE_KEY: PANEL_MODE}
        for status in statuses
        if status.get(MODE_KEY) in PANEL_SOURCE_MODES
    ]


def log_color(level: Any) -> str:
    """The colour an activity line is drawn in, neutral for a level nobody set."""
    return LOG_LEVEL_COLORS.get(level, LOG_FALLBACK_COLOR)


def log_line(time_text: Any, message: Any, level: Any = LOG_INFO) -> str:
    """One activity line: a grey clock reading, then the message in its colour."""
    return LOG_LINE_FORMAT.format(
        time_text=time_text, color=log_color(level), message=message
    )


def handler_color(level_name: Any) -> str:
    """The colour a console line is drawn in, neutral for an unknown level."""
    return HANDLER_LEVEL_COLORS.get(level_name, HANDLER_FALLBACK_COLOR)


def handler_line(level_name: Any, message: Any) -> str:
    """One console line, coloured by the level the record carried."""
    return HANDLER_LINE_FORMAT.format(color=handler_color(level_name), message=message)


def alert_row_cells(alert: Any, time_text: Any) -> list:
    """The five cell texts one webhook alert fills a row with."""
    return [
        time_text,
        alert.symbol,
        alert.action,
        ALERT_PRICE_FORMAT.format(price=alert.price),
        alert.strategy,
    ]


def url_running_text(port: Any) -> str:
    """The address the alert server listens on, once it is up."""
    return URL_RUNNING_FORMAT.format(port=port)


def refused_text(reason: Any) -> str:
    """The activity line shown when the capital registry refuses a new bot."""
    return REGISTER_REFUSED_FORMAT.format(reason=reason)


def created_text(symbol: Any, target_balance: Any) -> str:
    """The activity line shown once a new accumulation bot exists."""
    return BOT_CREATED_FORMAT.format(symbol=symbol, target_balance=target_balance)


def paper_trader_failure_text(error: Any) -> str:
    """The warning logged when the Paper Trader tab cannot be built."""
    return PAPER_TRADER_FAILURE_FORMAT.format(error=error)


def new_bot_text() -> str:
    """``NEW_BOT_TEXT_FORMAT`` filled with the number of voters
    ``DEFAULT_WEIGHTS`` declares."""
    return NEW_BOT_TEXT_FORMAT.format(indicator_count=len(DEFAULT_WEIGHTS))


def new_bot_box() -> dict:
    """The Ok or Cancel box the operator answers before a bot is made."""
    return {
        "title": NEW_BOT_TITLE,
        "text": new_bot_text(),
        "buttons_value": NEW_BOT_BUTTONS_VALUE,
    }


def about_box() -> dict:
    """The box the Help menu shows."""
    return {"title": ABOUT_TITLE, "text": about_text()}


class BotConfigSource:
    """The config one stock accumulation bot is made from."""

    def __init__(
        self,
        symbol: Any = BOT_SYMBOL,
        target_balance: Any = BOT_TARGET_BALANCE,
        ta_timeframe: Any = BOT_TIMEFRAME,
    ) -> None:
        self.symbol = symbol
        self.target_balance = target_balance
        self.ta_timeframe = ta_timeframe


class BotManagerSource:
    """The stock bot manager the window reads its cards and its table from.

    ``register`` answers with whatever the caller set, so both the tuple
    the capital registry returns and the older bare answer are driven.
    """

    def __init__(
        self,
        aggregate: Any = None,
        statuses: Any = None,
        register_result: Any = None,
        aggregate_raises: Optional[BaseException] = None,
        list_raises: Optional[BaseException] = None,
    ) -> None:
        self.aggregate = dict(aggregate or {})
        self.statuses = list(statuses or [])
        self.register_result = register_result
        self.aggregate_raises = aggregate_raises
        self.list_raises = list_raises
        self.registered: list = []

    def get_aggregate_stats(self) -> dict:
        if self.aggregate_raises is not None:
            raise self.aggregate_raises
        return self.aggregate

    def list_bots(self) -> list:
        if self.list_raises is not None:
            raise self.list_raises
        return self.statuses

    def register(self, bot: Any) -> Any:
        self.registered.append(bot)
        return self.register_result


class AlertSource:
    """One TradingView alert the webhook table shows a row for."""

    def __init__(
        self,
        timestamp: Any = 0,
        symbol: Any = DEFAULT_TEXT,
        action: Any = DEFAULT_TEXT,
        price: Any = DEFAULT_NUMBER,
        strategy: Any = DEFAULT_TEXT,
    ) -> None:
        self.timestamp = timestamp
        self.symbol = symbol
        self.action = action
        self.price = price
        self.strategy = strategy


class BridgeSource:
    """The TradingView bridge the window starts, stops and reads alerts from."""

    def __init__(
        self,
        running: bool = False,
        port: Any = PORT_DEFAULT,
        total_alerts: Any = 0,
        alerts: Any = None,
    ) -> None:
        self.running = running
        self._port = port
        self.total_alerts = total_alerts
        self.alert_history = list(alerts or [])
        self.auth_token: Any = None
        self.scheduled: list = []

    def get_summary(self) -> dict:
        return {PORT_KEY: self._port, TOTAL_ALERTS_KEY: self.total_alerts}

    def set_auth_token(self, token: Any) -> None:
        self.auth_token = token

    def start(self) -> str:
        self.scheduled.append("start")
        return "start"

    def stop(self) -> str:
        self.scheduled.append("stop")
        return "stop"


class MarketSource:
    """The market-hours reader the strip asks for its session and its wording."""

    def __init__(self, session: Any = SESSION_REGULAR, status: Any = DEFAULT_TEXT):
        self.session = session
        self.status = status

    def get_session(self) -> Any:
        return self.session

    def get_status_string(self) -> Any:
        return self.status


class ClockSource:
    """The clock readings the window would take, handed in as values.

    ``seconds`` drives the four-second throttle. ``time_text`` is the
    activity-log stamp. ``alert_time_texts`` holds one alert-table stamp
    per timestamp; ``alert_time_text`` answers for a timestamp not in it.
    """

    def __init__(
        self,
        seconds: Any = 0.0,
        time_text: Any = "00:00:00",
        alert_time_text: Any = "00:00:00",
        alert_time_texts: Any = None,
    ) -> None:
        self.seconds = seconds
        self.time_text = time_text
        self.alert_time_text = alert_time_text
        self.alert_time_texts = dict(alert_time_texts or {})

    def alert_time(self, timestamp: Any) -> Any:
        """The clock reading one alert row shows, from the values handed in."""
        return self.alert_time_texts.get(timestamp, self.alert_time_text)


class PanelSink:
    """The indicator panel the refresh would feed, and what it records."""

    def __init__(self, raises: Optional[BaseException] = None) -> None:
        self.raises = raises
        self.updates: list = []

    def update_bot_list(self, statuses: list) -> None:
        if self.raises is not None:
            raise self.raises
        self.updates.append(list(statuses))


class StockMainWindowModel:
    """The stock trading window's chrome, cards, tables and every path it takes.

    ``build`` fills the menu, the strip, the cards and the tabs.
    ``refresh`` is one tick of the two-second timer. The other methods
    are the window's buttons and menu items. Every step is appended to
    ``calls`` in the order the shipped window makes it.
    """

    def __init__(
        self,
        bot_manager: Any = None,
        bridge: Any = None,
        market: Any = None,
        clock: Any = None,
        panel: Any = None,
        chart_available: bool = True,
        panel_available: bool = True,
        paper_trader_available: bool = False,
        paper_trader_error: Any = "No module named 'src.gui.paper_trader_tab'",
    ) -> None:
        self.bot_manager = bot_manager
        self.bridge = bridge
        self.market = market if market is not None else MarketSource()
        self.clock = clock if clock is not None else ClockSource()
        self.panel = panel
        self.chart_available = chart_available
        self.panel_available = panel_available
        self.paper_trader_available = paper_trader_available
        self.paper_trader_error = paper_trader_error

        self.accessible_name = ACCESSIBLE_NAME
        self.window_title = WINDOW_TITLE
        self.menus: list = []
        self.market_text = MARKET_INITIAL_TEXT
        self.market_style = MARKET_INITIAL_STYLE
        self.webhook_text = WEBHOOK_INITIAL_TEXT
        self.webhook_style = WEBHOOK_INITIAL_STYLE
        self.card_values = [STAT_CARD_INITIAL_VALUE] * len(STAT_CARD_LABELS)
        self.card_colors: list = [CARD_VALUE_COLOR] * len(STAT_CARD_LABELS)
        self.tab_titles: list = []
        self.chart_shown = False
        self.chart_fallback_shown = False
        self.panel_shown = False
        self.rows: list = []
        self.row_colors: list = []
        self.alert_rows: list = []
        self.log_lines: list = []
        self.console_lines: list = []
        self.status_bar_text = DEFAULT_TEXT
        self.webhook_button_text = START_WEBHOOK_TEXT
        self.url_text = URL_INITIAL_TEXT
        self.timer_started = False
        self.hidden = False
        self.launcher_callback: Any = None
        self.boxes: list = []
        self.warnings: list = []
        self.last_tab_refresh: Any = None
        self.outcome: Optional[str] = NO_OUTCOME
        self.calls: list[ModelCall] = []

    def build(self) -> None:
        """Fill the menu, the strip, the cards, the four tabs and the timer."""
        self.calls.append([BUILD_START])
        self.menus = [
            [FILE_MENU_TITLE, list(FILE_MENU_ITEMS)],
            [HELP_MENU_TITLE, list(HELP_MENU_ITEMS)],
        ]
        self.calls.append([BUILD_MENU, len(self.menus)])
        self.calls.append([BUILD_MARKET_BAR, self.market_text])
        self.calls.append([BUILD_CARDS, len(self.card_values)])
        self.tab_titles.append(TAB_TRADING)
        self.calls.append([BUILD_TRADING_TAB])
        if self.chart_available:
            self.chart_shown = True
            self.calls.append([BUILD_CHART, CHART_SYMBOL, CHART_THEME])
        else:
            self.chart_fallback_shown = True
            self.calls.append([BUILD_CHART_FAILED])
        if self.panel_available:
            self.panel_shown = True
            self.calls.append([BUILD_PANEL])
        else:
            self.calls.append([BUILD_PANEL_FAILED])
        self.tab_titles.append(TAB_WEBHOOKS)
        self.calls.append([BUILD_WEBHOOK_TAB])
        if self.paper_trader_available:
            self.tab_titles.append(TAB_PAPER_TRADER)
            self.calls.append([BUILD_PAPER_TRADER, PAPER_TRADER_ASSET_TYPE])
        else:
            self.warnings.append(paper_trader_failure_text(self.paper_trader_error))
            self.calls.append([BUILD_PAPER_TRADER_FAILED])
        self.tab_titles.append(TAB_CONSOLE)
        self.calls.append([BUILD_CONSOLE])
        self.calls.append([BUILD_HANDLER, HANDLER_ROOT_LOGGER])
        self.status_bar_text = STATUS_BAR_TEXT
        self.calls.append([BUILD_STATUS_BAR, self.status_bar_text])
        self.timer_started = True
        self.calls.append([BUILD_TIMER, REFRESH_INTERVAL_MS])
        self.calls.append([BUILD_RETURN, len(self.tab_titles)])
        return None

    def refresh(self) -> Optional[str]:
        """One tick: the market line, the webhook line, the cards and the tables.

        A bot manager stops this tick at the first card the window reads
        and never builds, so the alert table is reached only when there
        is no bot manager.
        """
        self.calls.append([REFRESH_START])
        self.outcome = NO_OUTCOME
        try:
            status = self.market.get_status_string()
            session = self.market.get_session()
            color = market_color(session)
            self.market_text = market_text(status)
            self.market_style = market_style(color)
            self.calls.append([REFRESH_MARKET, session, color])

            if self.bridge is not None and self.bridge.running:
                summary = self.bridge.get_summary()
                self.webhook_text = webhook_active_text(
                    summary[PORT_KEY], summary[TOTAL_ALERTS_KEY]
                )
                self.webhook_style = WEBHOOK_ACTIVE_STYLE
                self.calls.append([REFRESH_WEBHOOK, summary[PORT_KEY]])

            if self.bot_manager is not None:
                aggregate = self.bot_manager.get_aggregate_stats()
                pnl = aggregate.get(AGGREGATE_PNL_KEY, DEFAULT_NUMBER)
                self.card_values[0] = STAT_PNL_FORMAT.format(pnl=pnl)
                self.card_colors[0] = pnl_color(pnl)
                self.card_values[1] = str(aggregate.get(TRADES_KEY, DEFAULT_NUMBER))
                self.card_values[2] = str(aggregate.get(RUNNING_KEY, DEFAULT_NUMBER))
                self.calls.append([REFRESH_BOTS, self.card_values[0]])

                statuses = self.bot_manager.list_bots()
                self.rows = [[NO_CELL_COLOR] * BOT_TABLE_COLUMN_COUNT for _ in statuses]
                self.row_colors = [
                    [NO_CELL_COLOR] * BOT_TABLE_COLUMN_COUNT for _ in statuses
                ]
                for index, one in enumerate(statuses):
                    self.rows[index] = bot_row_cells(one)
                    self.row_colors[index] = bot_row_colors(one)
                self.calls.append([REFRESH_TABLE, len(self.rows)])

                self.card_values[3] = str(open_position_count(statuses))
                self.calls.append([REFRESH_POSITIONS, self.card_values[3]])

                self.calls.append([REFRESH_MISSING_CARD, MISSING_STAT_ATTRIBUTES[0]])
                raise AttributeError(
                    f"'StockMainWindow' object has no attribute "
                    f"'{MISSING_STAT_ATTRIBUTES[0]}'"
                )

            if self.last_tab_refresh is None:
                self.last_tab_refresh = 0
            if self.clock.seconds - self.last_tab_refresh >= TAB_REFRESH_SECONDS:
                self.last_tab_refresh = self.clock.seconds
                self.calls.append([REFRESH_THROTTLED, self.last_tab_refresh])
                if self.bridge is not None:
                    shown = self.bridge.alert_history[-ALERT_HISTORY_LIMIT:]
                    self.alert_rows = [
                        alert_row_cells(one, self.clock.alert_time(one.timestamp))
                        for one in reversed(shown)
                    ]
                    self.calls.append([REFRESH_ALERTS, len(self.alert_rows)])
            else:
                self.calls.append([REFRESH_THROTTLE_SKIPPED, self.clock.seconds])
        except Exception as exc:
            self.outcome = OUTCOME_CRASHED
            self.warnings.append(REFRESH_CRASH_FORMAT % (exc,))
            self.calls.append([REFRESH_CRASHED, type(exc).__name__])
            return self.outcome
        self.outcome = OUTCOME_DONE
        self.calls.append([REFRESH_RETURN, len(self.rows)])
        return self.outcome

    def log(self, message: Any, level: Any = LOG_INFO) -> None:
        """Append one line to the activity log, coloured by its level."""
        self.log_lines.append(log_line(self.clock.time_text, message, level))
        self.calls.append([LOG_APPEND, level])
        return None

    def append_to_console(self, level_name: Any, message: Any) -> None:
        """Append one record to the console pane, coloured by its level."""
        try:
            self.console_lines.append(handler_line(level_name, message))
            self.calls.append([CONSOLE_APPEND, level_name])
        except Exception as exc:
            self.warnings.append(CONSOLE_FAILURE_FORMAT % (exc,))
            self.calls.append([CONSOLE_FAILED, type(exc).__name__])
        return None

    def create_bot(self, answer: Any) -> Optional[str]:
        """Make one accumulation bot, unless the operator or the registry says no."""
        self.calls.append([CREATE_START])
        self.boxes.append(new_bot_box())
        if answer != OK_BUTTON_VALUE:
            self.outcome = OUTCOME_DECLINED
            self.calls.append([CREATE_DECLINED])
            return self.outcome
        config = BotConfigSource(BOT_SYMBOL, BOT_TARGET_BALANCE, BOT_TIMEFRAME)
        if self.bot_manager is not None:
            answered = self.bot_manager.register(config)
            if isinstance(answered, tuple) and not answered[0]:
                self.log(refused_text(answered[1]), LOG_ERROR)
                self.outcome = OUTCOME_REFUSED
                self.calls.append([CREATE_REFUSED, answered[1]])
                return self.outcome
        self.log(created_text(config.symbol, config.target_balance), LOG_SUCCESS)
        self.outcome = OUTCOME_CREATED
        self.calls.append([CREATE_MADE, config.symbol])
        return self.outcome

    def toggle_webhook(self, token: Any = DEFAULT_TEXT, port: Any = PORT_DEFAULT):
        """Start or stop the alert server, and rewrite the button and the address."""
        self.calls.append([WEBHOOK_START])
        if self.bridge is None:
            self.log(NO_BRIDGE_MESSAGE, LOG_ERROR)
            self.outcome = OUTCOME_NO_BRIDGE
            self.calls.append([WEBHOOK_NO_BRIDGE])
            return self.outcome
        if self.bridge.running:
            self.bridge.stop()
            self.webhook_button_text = START_WEBHOOK_TEXT
            self.url_text = URL_STOPPED_TEXT
            self.log(WEBHOOK_STOPPED_MESSAGE, LOG_WARNING)
            self.outcome = OUTCOME_STOPPED
            self.calls.append([WEBHOOK_STOPPED])
            return self.outcome
        stripped = token.strip() if isinstance(token, str) else token
        if stripped:
            self.bridge.set_auth_token(stripped)
            self.calls.append([WEBHOOK_AUTH_SET])
        self.bridge._port = port
        self.bridge.start()
        self.webhook_button_text = STOP_WEBHOOK_TEXT
        self.url_text = url_running_text(port)
        self.log(WEBHOOK_STARTED_FORMAT.format(port=port), LOG_SUCCESS)
        self.outcome = OUTCOME_STARTED
        self.calls.append([WEBHOOK_STARTED, port])
        return self.outcome

    def bot_button_handler(self, label: Any):
        """The callable one of the three bot buttons runs."""

        def run() -> None:
            message = {
                SECONDARY_BUTTON_LABELS[0]: START_BOT_MESSAGE,
                SECONDARY_BUTTON_LABELS[1]: STOP_BOT_MESSAGE,
                SECONDARY_BUTTON_LABELS[2]: DELETE_BOT_MESSAGE,
            }[label]
            self.log(message, LOG_WARNING)
            self.calls.append([BOT_BUTTON, label])

        return run

    def open_settings(self) -> None:
        """Log the line the File menu's Settings item still shows."""
        self.log(SETTINGS_MESSAGE, LOG_INFO)
        self.calls.append([SETTINGS_OPENED])
        return None

    def back_to_launcher(self) -> None:
        """Hide the window, then call the launcher back if one was set."""
        self.hidden = True
        self.calls.append([LAUNCHER_HIDDEN])
        if self.launcher_callback:
            self.launcher_callback()
            self.calls.append([LAUNCHER_CALLED])
        else:
            self.calls.append([LAUNCHER_ABSENT])
        return None

    def set_launcher_callback(self, callback: Any) -> None:
        """Keep the callable that returns the operator to the launcher."""
        self.launcher_callback = callback
        return None

    def show_about(self) -> None:
        """Raise the box the Help menu shows."""
        self.boxes.append(about_box())
        self.calls.append([ABOUT_SHOWN])
        return None


def build_view_model(
    model: StockMainWindowModel,
    build_now: bool = False,
    refresh_count: int = 0,
    create_answer: Any = None,
    toggle_webhook: bool = False,
) -> dict:
    """Return every value the stock trading window holds as one dict.

    `build_now` fills the chrome and the tabs. `refresh_count` runs that
    many timer ticks. `create_answer` answers the new-bot box.
    `toggle_webhook` presses the alert-server button once.
    """
    if build_now:
        model.build()
    for _ in range(refresh_count):
        model.refresh()
    if create_answer is not None:
        model.create_bot(create_answer)
    if toggle_webhook:
        model.toggle_webhook()
    return {
        "method": METHOD,
        "accessible_name": model.accessible_name,
        "window": {
            "title": model.window_title,
            "minimum_width_px": MINIMUM_WIDTH_PX,
            "minimum_height_px": MINIMUM_HEIGHT_PX,
            "margins": list(CONTENT_MARGINS),
            "spacing_px": CONTENT_SPACING_PX,
        },
        "menus": [[title, list(items)] for title, items in model.menus],
        "menu_titles": [FILE_MENU_TITLE, HELP_MENU_TITLE],
        "menu_items": {
            "file": list(FILE_MENU_ITEMS),
            "help": list(HELP_MENU_ITEMS),
            "separator": MENU_SEPARATOR,
        },
        "market_label": {
            "text": model.market_text,
            "style_sheet": model.market_style,
            "initial_text": MARKET_INITIAL_TEXT,
            "initial_style": MARKET_INITIAL_STYLE,
        },
        "webhook_label": {
            "text": model.webhook_text,
            "style_sheet": model.webhook_style,
            "initial_text": WEBHOOK_INITIAL_TEXT,
            "initial_style": WEBHOOK_INITIAL_STYLE,
            "active_style": WEBHOOK_ACTIVE_STYLE,
        },
        "sessions": {
            "regular": SESSION_REGULAR,
            "pre_market": SESSION_PRE_MARKET,
            "after_hours": SESSION_AFTER_HOURS,
            "open_color": SESSION_OPEN_COLOR,
            "extended_color": SESSION_EXTENDED_COLOR,
            "shut_color": SESSION_SHUT_COLOR,
        },
        "cards": {
            "labels": list(STAT_CARD_LABELS),
            "values": list(model.card_values),
            "colors": list(model.card_colors),
            "initial_value": STAT_CARD_INITIAL_VALUE,
            "accessible_name": STAT_CARD_ACCESSIBLE_NAME,
            "style_name": STAT_CARD_STYLE_NAME,
            "value_color": CARD_VALUE_COLOR,
        },
        "bot_table": {
            "columns": list(BOT_TABLE_COLUMNS),
            "column_count": BOT_TABLE_COLUMN_COUNT,
            "accessible_name": BOT_TABLE_ACCESSIBLE_NAME,
            "pnl_column": PNL_COLUMN,
            "cell_alignment": CELL_ALIGNMENT,
            "cell_alignment_value": CELL_ALIGNMENT_VALUE,
            "bot_id_length": BOT_ID_LENGTH,
            "row_count": len(model.rows),
            "rows": [list(row) for row in model.rows],
            "row_colors": [list(row) for row in model.row_colors],
        },
        "alert_table": {
            "columns": list(ALERT_COLUMNS),
            "column_count": ALERT_COLUMN_COUNT,
            "history_limit": ALERT_HISTORY_LIMIT,
            "header_resize_mode": ALERT_HEADER_RESIZE_MODE,
            "alternating_row_colors": ALERT_ALTERNATING_ROW_COLORS,
            "vertical_header_visible": ALERT_VERTICAL_HEADER_VISIBLE,
            "row_count": len(model.alert_rows),
            "rows": [list(row) for row in model.alert_rows],
        },
        "split": {
            "orientation": SPLIT_ORIENTATION,
            "handle_width_px": SPLIT_HANDLE_WIDTH_PX,
            "children_collapsible": SPLIT_CHILDREN_COLLAPSIBLE,
            "sizes": list(SPLIT_SIZES),
            "panel_margins": list(PANEL_MARGINS),
        },
        "buttons": {
            "new_bot_text": NEW_BOT_BUTTON_TEXT,
            "new_bot_style": NEW_BOT_BUTTON_STYLE,
            "secondary_labels": list(SECONDARY_BUTTON_LABELS),
            "secondary_style": SECONDARY_BUTTON_STYLE,
            "webhook_text": model.webhook_button_text,
            "webhook_style": WEBHOOK_BUTTON_STYLE,
            "webhook_start_text": START_WEBHOOK_TEXT,
            "webhook_stop_text": STOP_WEBHOOK_TEXT,
        },
        "groups": {
            "style_sheet": GROUP_BOX_STYLE,
            "chart": CHART_GROUP_TITLE,
            "log": LOG_GROUP_TITLE,
            "webhook_config": WEBHOOK_CONFIG_TITLE,
            "guide": GUIDE_TITLE,
            "alerts": ALERTS_GROUP_TITLE,
        },
        "chart": {
            "symbol": CHART_SYMBOL,
            "theme": CHART_THEME,
            "stretch": CHART_STRETCH,
            "fallback_text": CHART_FALLBACK_TEXT,
            "shown": model.chart_shown,
            "fallback_shown": model.chart_fallback_shown,
        },
        "panel": {
            "stretch": PANEL_STRETCH,
            "mode": PANEL_MODE,
            "source_modes": list(PANEL_SOURCE_MODES),
            "shown": model.panel_shown,
        },
        "activity_log": {
            "max_height_px": LOG_MAX_HEIGHT_PX,
            "style_sheet": LOG_STYLE,
            "time_format": LOG_TIME_FORMAT,
            "line_format": LOG_LINE_FORMAT,
            "level_colors": dict(LOG_LEVEL_COLORS),
            "fallback_color": LOG_FALLBACK_COLOR,
            "lines": list(model.log_lines),
        },
        "webhook_form": {
            "port_minimum": PORT_MINIMUM,
            "port_maximum": PORT_MAXIMUM,
            "port_default": PORT_DEFAULT,
            "port_row_label": PORT_ROW_LABEL,
            "auth_row_label": AUTH_ROW_LABEL,
            "auth_placeholder": AUTH_PLACEHOLDER,
            "auth_echo_mode": AUTH_ECHO_MODE,
            "url_text": model.url_text,
            "url_initial_text": URL_INITIAL_TEXT,
            "url_stopped_text": URL_STOPPED_TEXT,
            "url_style": URL_LABEL_STYLE,
        },
        "guide": {
            "max_height_px": GUIDE_MAX_HEIGHT_PX,
            "style_sheet": GUIDE_STYLE,
            "html": GUIDE_HTML,
        },
        "tabs": {
            "titles": list(model.tab_titles),
            "all_titles": [TAB_TRADING, TAB_WEBHOOKS, TAB_PAPER_TRADER, TAB_CONSOLE],
            "movable": TABS_MOVABLE,
            "document_mode": TABS_DOCUMENT_MODE,
            "paper_trader_asset_type": PAPER_TRADER_ASSET_TYPE,
            "paper_trader_logger": PAPER_TRADER_LOGGER,
            "removed": list(REMOVED_TABS),
        },
        "console": {
            "font_family": CONSOLE_FONT_FAMILY,
            "font_size_pt": CONSOLE_FONT_SIZE_PT,
            "line_wrap": CONSOLE_LINE_WRAP,
            "style_sheet": CONSOLE_STYLE,
            "handler_format": HANDLER_FORMAT,
            "handler_date_format": HANDLER_DATE_FORMAT,
            "handler_connection": HANDLER_CONNECTION,
            "handler_line_format": HANDLER_LINE_FORMAT,
            "handler_root_logger": HANDLER_ROOT_LOGGER,
            "level_colors": dict(HANDLER_LEVEL_COLORS),
            "fallback_color": HANDLER_FALLBACK_COLOR,
            "lines": list(model.console_lines),
        },
        "status_bar": {"text": model.status_bar_text, "ready_text": STATUS_BAR_TEXT},
        "refresh": {
            "interval_ms": REFRESH_INTERVAL_MS,
            "throttle_seconds": TAB_REFRESH_SECONDS,
            "last_tab_refresh": model.last_tab_refresh,
            "crash_format": REFRESH_CRASH_FORMAT,
            "panel_failure_format": PANEL_FAILURE_FORMAT,
            "console_failure_format": CONSOLE_FAILURE_FORMAT,
            "ready_message": WINDOW_READY_MESSAGE,
            "missing_attributes": list(MISSING_STAT_ATTRIBUTES),
            "missing_attribute_error": MISSING_ATTRIBUTE_ERROR,
            "skipped_when_manager_present": list(SKIPPED_WHEN_MANAGER_PRESENT),
        },
        "new_bot": {
            "title": NEW_BOT_TITLE,
            "text": new_bot_text(),
            "buttons_value": NEW_BOT_BUTTONS_VALUE,
            "ok_value": OK_BUTTON_VALUE,
            "cancel_value": CANCEL_BUTTON_VALUE,
            "symbol": BOT_SYMBOL,
            "target_balance": BOT_TARGET_BALANCE,
            "timeframe": BOT_TIMEFRAME,
        },
        "messages": {
            "start_bot": START_BOT_MESSAGE,
            "stop_bot": STOP_BOT_MESSAGE,
            "delete_bot": DELETE_BOT_MESSAGE,
            "settings": SETTINGS_MESSAGE,
            "no_bridge": NO_BRIDGE_MESSAGE,
            "webhook_stopped": WEBHOOK_STOPPED_MESSAGE,
        },
        "about": about_box(),
        "formats": {
            "market_text": MARKET_TEXT_FORMAT,
            "market_style": MARKET_STYLE_FORMAT,
            "webhook_active_text": WEBHOOK_ACTIVE_TEXT_FORMAT,
            "stat_pnl": STAT_PNL_FORMAT,
            "win_rate": WIN_RATE_FORMAT,
            "entry": ENTRY_FORMAT,
            "current": CURRENT_FORMAT,
            "pnl": PNL_FORMAT,
            "alert_price": ALERT_PRICE_FORMAT,
            "alert_time": ALERT_TIME_FORMAT,
            "url_running": URL_RUNNING_FORMAT,
            "register_refused": REGISTER_REFUSED_FORMAT,
            "bot_created": BOT_CREATED_FORMAT,
            "webhook_started": WEBHOOK_STARTED_FORMAT,
            "paper_trader_failure": PAPER_TRADER_FAILURE_FORMAT,
        },
        "keys": {
            "stats": STATS_KEY,
            "bot_id": BOT_ID_KEY,
            "symbol": SYMBOL_KEY,
            "mode": MODE_KEY,
            "state": STATE_KEY,
            "pnl": PNL_KEY,
            "position": POSITION_KEY,
            "entry": ENTRY_KEY,
            "price": PRICE_KEY,
            "trades": TRADES_KEY,
            "signals": SIGNALS_KEY,
            "wins": WINS_KEY,
            "aggregate_pnl": AGGREGATE_PNL_KEY,
            "running": RUNNING_KEY,
            "port": PORT_KEY,
            "total_alerts": TOTAL_ALERTS_KEY,
        },
        "defaults": {"text": DEFAULT_TEXT, "number": DEFAULT_NUMBER},
        "log_levels": [LOG_INFO, LOG_SUCCESS, LOG_WARNING, LOG_ERROR],
        "outcome": model.outcome,
        "no_outcome": NO_OUTCOME,
        "outcomes": [
            OUTCOME_DECLINED,
            OUTCOME_REFUSED,
            OUTCOME_CREATED,
            OUTCOME_NO_BRIDGE,
            OUTCOME_STOPPED,
            OUTCOME_STARTED,
            OUTCOME_CRASHED,
            OUTCOME_DONE,
        ],
        "boxes": [dict(one) for one in model.boxes],
        "warnings": list(model.warnings),
        "hidden": model.hidden,
        "timer_started": model.timer_started,
        "no_cell_color": NO_CELL_COLOR,
        "actions": dict(ACTIONS),
        "runtime_connect_total": RUNTIME_CONNECT_TOTAL,
        "signals": list(SIGNAL_NAMES),
        "signal_emit_total": SIGNAL_EMIT_TOTAL,
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "timers_started": list(TIMERS_STARTED),
        "threads_built": list(THREADS_BUILT),
        "threads_started": list(THREADS_STARTED),
        "bus_topics": list(BUS_TOPICS),
        "bus_emits": list(BUS_EMITS),
        "call_names": list(CALL_NAMES),
        "calls": [list(call) for call in model.calls],
    }


PANE_MODEL = StockMainWindowModel()


def _alert_sources(alerts: Any) -> list:
    return [
        AlertSource(
            timestamp=one.get("timestamp", 0),
            symbol=one.get("symbol", DEFAULT_TEXT),
            action=one.get("action", DEFAULT_TEXT),
            price=one.get("price", DEFAULT_NUMBER),
            strategy=one.get("strategy", DEFAULT_TEXT),
        )
        for one in alerts
    ]


def view_model(params: dict) -> dict:
    """Bridge handler for ``stock_main_window.state``.

    Reads ``reset``, ``bot_manager``, ``bridge``, ``market``, ``clock``,
    ``build``, ``refresh``, ``create_answer`` and ``toggle_webhook`` from
    the request parameters. The window's last state persists between
    calls because the window does; ``reset`` is what a fresh paint sends.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = StockMainWindowModel()
    manager = params.get("bot_manager")
    if manager is not None:
        PANE_MODEL.bot_manager = BotManagerSource(
            aggregate=manager.get("aggregate"),
            statuses=manager.get("statuses"),
            register_result=manager.get("register_result"),
        )
    bridge = params.get("bridge")
    if bridge is not None:
        PANE_MODEL.bridge = BridgeSource(
            running=bridge.get("running", False),
            port=bridge.get("port", PORT_DEFAULT),
            total_alerts=bridge.get("total_alerts", 0),
            alerts=_alert_sources(bridge.get("alerts") or []),
        )
    market = params.get("market")
    if market is not None:
        PANE_MODEL.market = MarketSource(
            session=market.get("session", SESSION_REGULAR),
            status=market.get("status", DEFAULT_TEXT),
        )
    clock = params.get("clock")
    if clock is not None:
        PANE_MODEL.clock = ClockSource(
            seconds=clock.get("seconds", 0.0),
            time_text=clock.get("time_text", "00:00:00"),
            alert_time_text=clock.get("alert_time_text", "00:00:00"),
            alert_time_texts=dict(clock.get("alert_time_texts") or []),
        )
    return build_view_model(
        PANE_MODEL,
        params.get("build", False),
        int(params.get("refresh", 0)),
        params.get("create_answer"),
        bool(params.get("toggle_webhook", False)),
    )
