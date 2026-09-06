"""main_window_surface.py -- the main application window, without Qt.

Describes the window every tab lives inside: its title, its smallest
size, its four menus, the ``CANONICAL_TAB_ORDER`` book and the order they
sit in, its status line, and the values it formats before it shows them.

The window BUILDS many tabs and WIRES them to the bot manager. That part
is named in ``WIRED_TABS`` and ``WIRED_PATHS`` and is not re-modelled
here: each of those tabs already has its own surface. What is modelled
is what this window itself decides.

``MainWindowModel`` holds the window's state. ``build`` fills the title,
the menus, the tab book and the status line. ``refresh`` is one tick of
the two-second timer: it rewrites the six stat cards, the spendable
panel and the API-load pill. ``change_tab``, ``toggle_console_pause``,
``toggle_trading_mode``, ``switch_theme``, ``reset_settings``,
``settings_changed``, ``delete_bot``, ``create_extractor``,
``adopt_topology``, ``api_event``, ``tracking_beep``, ``trade_filled``,
``pulse_tick`` and ``show_about`` are the window's other paths. Every
step is appended to ``calls``.

``FleetSource``, ``SettingsSource``, ``LoadMonitorSource``,
``LoadSample``, ``BotView``, ``HistoryTabSource``, ``ConsoleHandlerSource``
and ``ThemeSource`` are plain stand-ins for the bot manager, the settings
store, the API-load monitor, one of its readings, one bot, the History
tab, the console log handler and the theme register, so the window can be
driven over the bridge from values alone. The fleet reaches
``FleetSource`` as the list of status dictionaries a stored fleet load
produces; nothing here invents one.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``main_window.state`` method. Every value below is written out here
rather than read from ``src.gui.main_window``, so a value changed on one
side alone is reported. Nothing here imports Qt and nothing here reads a
clock: a time reaches the model as a value.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from .. import design_system as ds
from . import bot_visualizer_surface
from . import console_tab_surface
from . import history_tab_surface
from . import market_inspector_surface
from . import paper_trader_tab_surface
from . import proof_of_accumulation_tab_surface
from . import simulator_tab_surface
from . import system_status_tab_surface
from . import trade_charts_tab_surface
from . import trading_tab_surface

METHOD = "main_window.state"

# Chrome

WINDOW_TITLE_FORMAT = "Acervator v{version}"


def running_version() -> str:
    """The version the title carries when the caller names none.

    Read when asked rather than at import, so the surface stays importable
    without the package having resolved its version yet. A literal default
    here would title the bridge's window differently from the Qt window,
    which reads ``src.__version__`` directly.
    """
    from src import __version__

    return str(__version__)


MINIMUM_WIDTH_PX = 1400
MINIMUM_HEIGHT_PX = 900

CRYPTO_MODE = "crypto"
STOCK_MODE = "stock"
CRYPTO_WING_TITLE = "Acervator — CRYPTO WING"
STOCK_WING_TITLE = "Acervator — STOCK WING"
WING_TITLES = {CRYPTO_MODE: CRYPTO_WING_TITLE, STOCK_MODE: STOCK_WING_TITLE}

CRYPTO_MODE_BUTTON_TEXT = "Crypto Mode"
STOCK_MODE_BUTTON_TEXT = "Stock Mode"
MODE_BUTTON_TEXTS = {
    CRYPTO_MODE: CRYPTO_MODE_BUTTON_TEXT,
    STOCK_MODE: STOCK_MODE_BUTTON_TEXT,
}
MODE_BUTTON_CHECKED = {CRYPTO_MODE: False, STOCK_MODE: True}
MODE_STACK_INDEX = {CRYPTO_MODE: 0, STOCK_MODE: 1}

CRYPTO_WING_LOG = (
    "→ CRYPTO WING: crypto exchanges + crypto Paper Trader. (Stock wing paused.)"
)
STOCK_WING_LOG = (
    "→ STOCK WING: equity exchanges + equity Paper Trader. (Crypto wing paused.)"
)
WING_LOGS = {CRYPTO_MODE: CRYPTO_WING_LOG, STOCK_MODE: STOCK_WING_LOG}

MODE_BUTTON_RGB = {CRYPTO_MODE: "0, 200, 160", STOCK_MODE: "80, 140, 255"}
MODE_BUTTON_COLOUR = {CRYPTO_MODE: ds.LAYER_CRYPTO, STOCK_MODE: ds.LAYER_STOCK}
MODE_BUTTON_STYLE_FORMAT = (
    "QPushButton {{ background: rgba({rgb}, 40); "
    "color: {colour}; border: 1px solid rgba({rgb}, 100); "
    "border-radius: 4px; font-weight: bold; font-size: 11px; }}"
    "QPushButton:hover {{ background: rgba({rgb}, 70); }}"
)
MODE_TAB_STYLE_FORMAT = (
    "QTabBar::tab:selected {{ border-bottom: 2px solid {colour}; color: {colour}; }}"
)
MODE_TAB_STYLE_CLEARED = ""

MENU_SEPARATOR = "---"
FILE_MENU_TITLE = "&File"
EXCHANGE_MENU_TITLE = "&Exchange"
THEME_MENU_TITLE = "&Theme"
HELP_MENU_TITLE = "&Help"
FILE_MENU_ITEMS = ("&Settings", "&Reset All Settings", MENU_SEPARATOR, "E&xit")
EXCHANGE_MENU_ITEMS = ("&Add Exchange",)
HELP_MENU_ITEMS = ("&About",)
MENU_TITLES = (
    FILE_MENU_TITLE,
    EXCHANGE_MENU_TITLE,
    THEME_MENU_TITLE,
    HELP_MENU_TITLE,
)

TABS_MOVABLE = True

TRADING_TAB = "Trading"
MARKET_INSPECTOR_TAB = "Market Inspector"
BOT_SWARM_TAB = "Bot Swarm"
ASSET_CHARTS_TAB = "Asset Charts"
HISTORY_TAB = "History"
SIMULATOR_TAB = "Simulator"
CONSOLE_TAB = "Console"

# Each unbuilt tab is labelled by its own surface, so the bar and the empty
# state it draws cannot carry two spellings of one name.
PAPER_TRADER_TAB = paper_trader_tab_surface.HEADING
SYSTEM_STATUS_TAB = system_status_tab_surface.HEADING
PROOF_OF_ACCUMULATION_TAB = proof_of_accumulation_tab_surface.HEADING

CANONICAL_TAB_ORDER = (
    TRADING_TAB,
    MARKET_INSPECTOR_TAB,
    BOT_SWARM_TAB,
    ASSET_CHARTS_TAB,
    HISTORY_TAB,
    SIMULATOR_TAB,
    CONSOLE_TAB,
    PAPER_TRADER_TAB,
    SYSTEM_STATUS_TAB,
    PROOF_OF_ACCUMULATION_TAB,
)

# The bridge method that serves each tab. A frontend with no tab book of its
# own joins its panels to this window's tabs on the method each one calls.
TAB_METHODS = {
    TRADING_TAB: trading_tab_surface.METHOD,
    MARKET_INSPECTOR_TAB: market_inspector_surface.METHOD,
    BOT_SWARM_TAB: bot_visualizer_surface.METHOD,
    ASSET_CHARTS_TAB: trade_charts_tab_surface.METHOD,
    HISTORY_TAB: history_tab_surface.METHOD,
    SIMULATOR_TAB: simulator_tab_surface.METHOD,
    CONSOLE_TAB: console_tab_surface.METHOD,
    PAPER_TRADER_TAB: paper_trader_tab_surface.METHOD,
    SYSTEM_STATUS_TAB: system_status_tab_surface.METHOD,
    PROOF_OF_ACCUMULATION_TAB: proof_of_accumulation_tab_surface.METHOD,
}

# The order `_setup_ui` runs the builders in, which is not the order the bar ends in.
BUILT_TAB_ORDER = (
    TRADING_TAB,
    ASSET_CHARTS_TAB,
    BOT_SWARM_TAB,
    MARKET_INSPECTOR_TAB,
    SIMULATOR_TAB,
    HISTORY_TAB,
    CONSOLE_TAB,
    PAPER_TRADER_TAB,
    SYSTEM_STATUS_TAB,
    PROOF_OF_ACCUMULATION_TAB,
)

SIMULATOR_BUILD_INDEX = 1

ISOLATED_TABS = (SIMULATOR_TAB, PAPER_TRADER_TAB)

HISTORY_STALE_AFTER_S = 300

DASHBOARD_TICK_MS = 2000
PULSE_TICK_MS = 80
TOOLTIP_TICK_MS = 5000
TOOLTIP_FIRST_SCAN_MS = 500

# Status line

STATUS_READY_TEXT = "Ready"

PILL_STYLE_FORMAT = (
    "color: {colour}; font-size: 10px; padding: 0 8px; font-family: Consolas;"
)

API_PILL_IDLE_TEXT = "API: —"
API_PILL_IDLE_COLOUR = ds.CARD_METRIC_LABEL
API_PILL_TOOLTIP = (
    "Trailing 60 s calls-per-minute on the busiest "
    "connected exchange. Green ≤ 50 %, amber ≤ 75 %, "
    "red above the 75 % phantom-creation safety threshold."
)
API_PILL_TEXT_FORMAT = (
    "API {exchange}: {calls_per_minute:.0f}/{ceiling_cpm:.0f} CPM ({percent} %)"
)
API_PILL_AMBER_ABOVE = 0.5
API_PILL_RED_COLOUR = ds.ERROR
API_PILL_AMBER_COLOUR = ds.FOLD_RATIO_AMBER
API_PILL_GREEN_COLOUR = ds.SUCCESS

AI_OFF_TEXT = "AI: OFF"
AI_OFF_COLOUR = ds.TEXT_PLACEHOLDER
AI_READY_TEXT = "AI: READY"
AI_READY_COLOUR = ds.STATUS_AUTHENTICATED

# The six stat cards and the spendable panel

SCRUMMED_FORMAT = "${value:,.2f}"
FOLDED_FORMAT = "${value:,.2f}"
PNL_FORMAT = "${value:+,.4f}"
TRADES_FORMAT = "{value}"
BOTS_FORMAT = "{value}"
ERRORS_FORMAT = "{value}"

CARD_ORDER = ("scrummed", "folded", "pnl", "trades", "bots", "errors")

SCRUMMED_KEY = "total_scrummed_usd"
FOLDED_KEY = "total_folded_usd"
PNL_KEY = "total_realised_pnl"
TRADES_KEY = "total_trades"
BOTS_KEY = "running"
ERRORS_KEY = "total_errors_lifetime"
WALLET_CASH_KEY = "wallet_cash_usd"
CRYPTO_VALUE_KEY = "crypto_position_value_usd"

SPENDABLE_UNKNOWN = None

# The console pause button

CONSOLE_PAUSE_TEXT = "⏸  Pause"
CONSOLE_RESUME_TEXT = "▶  Resume"
CONSOLE_PAUSED_INDICATOR = "PAUSED · 0 buffered"
CONSOLE_RUNNING_INDICATOR = ""
CONSOLE_BUFFERED_FORMAT = "PAUSED · {held} buffered (cap {cap})"
CONSOLE_BUFFERED_DROPPED_FORMAT = (
    "PAUSED · {held} buffered (cap {cap}, {dropped} dropped)"
)

SIGNAL_GAP_MARKER_FORMAT = (
    "──── [SIGNALS GAP] {skipped} earlier records skipped "
    "to stay current · NOT LOST · on disk in "
    "~/.acervator_logs/signals/session.jsonl ────"
)

# The API interaction log

API_EVENT_HEAD_FORMAT = "[{stamp}] {exchange} {action}"
API_EVENT_REASON_FORMAT = "  Reason: {reason}"
API_EVENT_ENDPOINT_FORMAT = "  Endpoint: {endpoint}"
API_EVENT_RESULT_FORMAT = "  Result: {result}"
API_EVENT_RESPONSE_FORMAT = "  Response: {elapsed_ms}ms"
API_EVENT_DATA_USAGE_FORMAT = "  Data usage: {data_usage}"
API_EVENT_WRONG_THREAD = "wrong_thread"
API_EVENT_BUFFERED = "buffered"
API_EVENT_APPENDED = "appended"
MAIN_THREAD_NAME = "MainThread"

# The indicator panel's empty state

CAUSE_BOT_MISSING = "bot_missing"
CAUSE_NOT_RUNNING = "not_running"
CAUSE_BOT_ERROR = "bot_error"
CAUSE_PARKED_AT_TARGET = "parked_at_target"
CAUSE_TOO_FEW_CANDLES = "too_few_candles"
CAUSE_COLD_START = "cold_start"
CAUSE_NO_SELECTION = "no_selection"
NOT_RUNNING_STATES = ("idle", "stopped")
ERROR_STATE = "error"
CANDLES_REQUIRED = 30
DEFAULT_TIMEFRAME = "1h"

# The sounds the window decides on

FIRE_SOUND = "fire"
PROFIT_SOUND = "profit"
DRIP_SOUND = "drip"
RIFLE_TRADE_TYPES = ("SCRUM", "FOLD", "DIST")
DRIP_TRADE_TYPE = "FOLD"

BEEP_FIRE_PHASE = "fire"
BEEP_TRACK_PHASE = "track"
BEEP_FIRE_CADENCE_S = 0.2
BEEP_TRACK_CADENCE_S = 0.8
BEEP_MODE = "scrumming"
BEEP_STATES = ("running", "paused")
BEEP_SILENT = "silent"
BEEP_THROTTLED = "throttled"
BEEP_PLAYED = "played"

# The pulse

PULSE_PHASE_STEP = 0.05
PULSE_OPACITY_MID = 0.91
PULSE_OPACITY_SWING = 0.09
GLOW_BLUR_MID = 17.0
GLOW_BLUR_SWING = 5.0
GLOW_PHASE_RATE = 1.6

# The boxes the window raises

BOX_QUESTION = "question"
BOX_WARNING = "warning"
BOX_CRITICAL = "critical"
BOX_INFORMATION = "information"
BOX_ABOUT = "about"

ABOUT_TITLE = "About Acervator"
ABOUT_TEXT = (
    "Acervator v1.7\n\n"
    "A multi-exchange crypto auto-trading platform.\n"
    "Grid Mode - Speculative Scrumming\n"
    "Profit Folding - Upward Distribution\n"
    "Phantom Balance Bots - 7-Indicator TA Voting\n"
    "TradingView Charts - Multi-Timeframe Analysis\n"
    "Verbose API Interaction Logging"
)

RESET_TITLE = "Reset All Settings"
RESET_TEXT = (
    "This will clear ALL settings, exchanges, and stored credentials.\n"
    "The application will restart with the setup wizard.\n\n"
    "Are you sure?"
)
RESET_DONE_TITLE = "Settings Reset"
RESET_DONE_TEXT = (
    "All settings have been cleared.\n"
    "Close and reopen the application to run the setup wizard."
)
RESET_LOG = "All settings reset. Restart the application."
RESET_SPOOL = "Settings reset. Please restart."

DELETE_TITLE = "Delete Bot"
DELETE_TEXT_FORMAT = "Delete bot {bot_id}? This cannot be undone."
DELETE_LOG_FORMAT = "Bot {bot_id} deleted."
DELETE_SPOOL_FORMAT = "Bot {bot_id} DELETED"

EXTRACTOR_REFUSAL_TITLE = "Extractor needs a parent bot"
EXTRACTOR_REFUSAL_BOX_FORMAT = "{reason}\n\nBot creation aborted."
EXTRACTOR_REFUSAL_LOG_FORMAT = "Extractor creation REFUSED — {reason}"
EXTRACTOR_REFUSAL_ACTION = "BOT_CREATE_REFUSED"
EXTRACTOR_REFUSAL_API_REASON = (
    "Extractor has no single parent Scrumming Bot for its base currency"
)
EXTRACTOR_REFUSAL_API_RESULT_FORMAT = "REFUSED: {base_currency}"
EXTRACTOR_REFUSAL_API_DATA_USAGE = "No bot was created and no state was written."

EXTRACTOR_UNKNOWN_ASSET = "?"
EXTRACTOR_UNKNOWN_VENUE = "this exchange"

EXTRACTOR_NO_ROSTER_FORMAT = (
    "The bot roster is not available, so it cannot be "
    "confirmed that a Scrumming Bot on {venue} holds "
    "{asset}.\n\n"
    "An Extractor hands its base currency back to the "
    "Scrumming Bot that holds it, so it may not be "
    "created until that bot is known to exist."
)
EXTRACTOR_NO_PARENT_FORMAT = (
    "No Scrumming Bot on {venue} holds {asset}.\n\n"
    "An Extractor is a sibling of the Scrumming Bot "
    "that holds its base currency: when the Extractor "
    "closes a position it hands {asset} back to that "
    "bot, which raises its target balance to keep the "
    "gain. With no such bot there is nowhere for the "
    "money to go.\n\n"
    "Create a Scrumming Bot for {asset} on {venue} "
    "first, then create this Extractor."
)
EXTRACTOR_AMBIGUOUS_FORMAT = (
    "{count} Scrumming Bots on {venue} hold "
    "{asset}: {ids}.\n\n"
    "The parent is ambiguous. An Extractor hands {asset} "
    "back to ONE holder, and nothing here can tell which "
    "of these earned it — choosing for you would raise the "
    "wrong bot's target on money it never received, while "
    "the right one stayed short.\n\n"
    "Naming the parent is your call. Leave exactly one "
    "Scrumming Bot holding {asset} on {venue}, then "
    "create this Extractor."
)

ADOPT_TITLE = "Adopt topology"
ADOPT_NO_MANAGER_TEXT = "Bot manager not available."
ADOPT_DEFAULT_PROPOSAL_TITLE = "topology"
ADOPT_HEAD_FORMAT = "Adopt proposal: {title}"
ADOPT_NEW_BOTS_FORMAT = "New bots to create: {count} (${budget:,.0f} total)"
ADOPT_WIRES_FORMAT = "Wires to draw: {count}"
ADOPT_COLLISION_HEAD_FORMAT = (
    "{count} of these wire(s) ALREADY EXIST. Adopting CHANGES them:"
)
ADOPT_COLLISION_ROW_FORMAT = (
    "    {source_asset} -> {target_asset}: {current_pct:.2f}% -> {proposed_pct:.2f}%"
)
ADOPT_COLLISION_OVERFLOW_FORMAT = "    ... and {count} more"
ADOPT_COLLISIONS_SHOWN = 12
ADOPT_SNAPSHOT_LINE = (
    "The previous rates are saved to a snapshot file before anything is applied."
)
ADOPT_TAIL_LINE = (
    "The Bot Wizard will open for each new bot; cancel any "
    "wizard to abort the entire adoption. Existing bots are "
    "not modified."
)
ADOPT_CANCELLED_LOG = "Topology adoption cancelled at confirm gate."

ORPHAN_LOG_FORMAT = (
    "Topology adopt: {count} bot(s) were already "
    "created before the abort and remain: "
    "{ids}. "
    "They are not wired. Remove them from the Bot Swarm tab "
    "if they are not wanted."
)
ORPHAN_ID_CHARACTERS = 8

THEME_SWITCHED_LOG_FORMAT = "Theme switched to {name}."
SETTINGS_SAVED_LOG = "Settings saved."
SETTINGS_OPEN_LOG_FORMAT = "Opening settings ({wing} wing)..."
ADD_EXCHANGE_LOG_FORMAT = "Opening settings to add exchange ({wing} wing)..."
STARTED_LOG_FORMAT = "Acervator v{version} started."
CONSOLE_ACTIVE_LOG_FORMAT = (
    "Acervator v{version} — Console logging active. " "All system messages appear here."
)
DEFAULT_THEME = "cyberpunk_dark"
AI_RECONFIGURED_LOG_FORMAT = "AI Monitor reconfigured (phrase: '{phrase}...')"
AI_PHRASE_CHARACTERS = 20

# The bus this window subscribes to, and what it never gives back

BUS_SUBSCRIPTIONS = (
    "bot.log",
    "wire.created",
    "indicator.tf_lock_changed",
    "ai.feedback",
    "trade.filled",
    "bot.error",
)
BUS_UNSUBSCRIPTIONS: tuple = ()
ERROR_BUFFER_MAX = 200

# Wiring: named here, modelled by the surface each tab already has

WIRED_TABS = (
    "_build_trading_tab",
    "_build_charts_tab",
    "_build_bot_swarm_tab",
    "_build_market_inspector_tab",
    "_build_simulator_tab",
    "_install_retired_tab_sentinels",
    "_build_history_tab",
    "_build_console_tab",
)

WIRED_PATHS = (
    "_apply_abbreviation_tooltips",
    "_build_error_log_dialog",
    "_build_topology_proposals",
    "_cancel_if_pending",
    "_connect_exchange_for_bot",
    "_create_bot",
    "_drain_signals",
    "_emit_console_health",
    "_global_bot_cmd",
    "_init_live_monitor",
    "_ivp_cached_candle_count",
    "_on_ai_feedback",
    "_on_bot_clicked",
    "_on_bot_error_for_log",
    "_on_bot_fire",
    "_on_bot_log",
    "_on_live_settings_changed",
    "_on_tf_lock_changed",
    "_on_wire_created",
    "_pump_currency_rates",
    "_pump_market_pairs_scout",
    "_refresh_all_privacy_widgets",
    "_register_fire_glow",
    "_report_stored_credentials_on_startup",
    "_schedule_async",
    "_show_error_log_dialog",
    "_snapshot_wires_for_adopt",
    "_sync_exchange_tabs",
    "_topology_wire_collisions",
    "_wire_ivp_snapshot_dir",
    "_wire_is_registered",
    "_wire_manager",
    "add_exchange_tab",
    "set_async_loop",
)

# The abbreviation tooltips the window applies to its own children

ABBREVIATION_TOOLTIPS = (
    ("P/L", "Profit / Loss - net gain or loss from closed trades"),
    ("P&L", "Profit and Loss - same as P/L"),
    (
        "Realised",
        "Realised P/L - profit/loss from positions that have been closed",
    ),
    (
        "Locked",
        "Locked - value committed to open positions less than 30 days old",
    ),
    (
        "Mature",
        "Mature - profits from positions filled 30+ days ago, safely withdrawable",
    ),
    (
        "Spendable",
        "Spendable Profits - estimated expendable liquidity from mature positions",
    ),
    (
        "Extended",
        "Extended Position - extra position created when accumulated "
        "profit reaches position size",
    ),
    ("Grid", "Grid Mode - stacked buy/sell pairs at fixed price intervals"),
    (
        "Scrumming",
        "Speculative Scrumming - TA-driven delta trading against a target balance",
    ),
    (
        "Phantom",
        "Phantom Balance Bot - shadow bot analyzing a different timeframe",
    ),
    (
        "Folding",
        "Profit Folding - distributing realized sell profits back into buy positions",
    ),
    (
        "Distribution",
        "Upward Distribution - distributing accumulated asset into sell positions",
    ),
    (
        "TA",
        "Technical Analysis - mathematical indicators computed from "
        "price/volume data",
    ),
    (
        "BB",
        "Bollinger Bands - volatility envelope 2 std deviations from a moving average",
    ),
    (
        "MACD",
        "Moving Average Convergence Divergence - trend-following momentum indicator",
    ),
    (
        "RSI",
        "Relative Strength Index - momentum oscillator measuring "
        "overbought/oversold (0-100)",
    ),
    (
        "StochRSI",
        "Stochastic RSI - RSI applied to its own values, more sensitive to extremes",
    ),
    (
        "EMA",
        "Exponential Moving Average - weighted average favoring recent data points",
    ),
    ("SMA", "Simple Moving Average - arithmetic mean of prices over N periods"),
    (
        "Ichimoku",
        "Ichimoku Cloud - trend, momentum, and support/resistance indicator system",
    ),
    (
        "Vortex",
        "Vortex Indicator - identifies trend direction and reversals using true range",
    ),
    (
        "Slingshot",
        "Slingshot Entry - custom momentum signal detecting sharp directional moves",
    ),
    ("TF", "Timeframe - candle duration (1m, 5m, 15m, 1h, 4h, 1d, 1w)"),
    (
        "OHLCV",
        "Open, High, Low, Close, Volume - the five data points per candle",
    ),
    ("Vol", "Volume - total value traded in a given period"),
    (
        "Volat",
        "Volatility - measure of price variation; higher = more price movement",
    ),
    (
        "API",
        "Application Programming Interface - how this app communicates with exchanges",
    ),
    (
        "WS",
        "WebSocket - persistent bidirectional connection for real-time data",
    ),
    (
        "CCXT",
        "CryptoCurrency eXchange Trading - library connecting to 100+ exchanges",
    ),
    (
        "Bots",
        "Automated trading agents executing buy/sell strategies continuously",
    ),
    ("IDLE", "Bot is created but not started. Click Start to begin."),
    (
        "RUNNING",
        "Bot is actively monitoring the market and executing trades.",
    ),
    ("PAUSED", "Bot is suspended. Open orders remain but no new trades."),
    ("COOLDOWN", "Bot hit max errors and is waiting before retrying."),
    ("Exch", "Exchange - cryptocurrency trading platform"),
)

TOOLTIP_STYLE = (
    "\nQToolTip { font-size: 12px; padding: 8px; "
    f"background: {ds.SURFACE_CONTROL}; color: {ds.TEXT_HIGH}; border: "
    f"1px solid {ds.MAIN_TOOLTIP_BORDER}; }}"
)


# Pure decisions


def window_title(version: Any) -> str:
    """The title bar the window carries at launch."""
    return WINDOW_TITLE_FORMAT.format(version=version)


def wing_title(mode: Any) -> str:
    """The title bar after the operator flips the trading wing."""
    return WING_TITLES[mode]


def constructed_tabs(failed: Any = None) -> list:
    """The tab bar the builders leave, with every name in `failed` skipped.

    Each builder in `BUILT_TAB_ORDER` appends; the Simulator's inserts at
    `SIMULATOR_BUILD_INDEX`.
    """
    skipped = set(failed or ())
    order: list = []
    for name in BUILT_TAB_ORDER:
        if name in skipped:
            continue
        if name == SIMULATOR_TAB:
            order.insert(SIMULATOR_BUILD_INDEX, name)
        else:
            order.append(name)
    return order


def reordered_tabs(labels: Any, desired: Any) -> list:
    """`labels` after the reorder pass moves each named tab into its slot.

    Tabs whose labels are not in `desired` keep their relative position
    at the end. The first tab carrying a name is the one that moves. A
    slot past the last tab is not a slot: with a tab missing, every name
    after it asks for an index the bar does not have and the bar moves
    nothing, so the last named tabs keep the order they were built in.
    """
    order = list(labels)
    for target_index, name in enumerate(desired):
        if target_index >= len(order):
            break
        for current_index in range(len(order)):
            if order[current_index] == name:
                if current_index != target_index:
                    moved = order.pop(current_index)
                    order.insert(target_index, moved)
                break
    return order


def header_strip_visible(tab_name: Any) -> bool:
    """Whether the window-level stat strip shows on the tab named."""
    return tab_name not in ISOLATED_TABS


def history_refresh_due(last_fetched_ts: Any, in_flight: Any, now: Any) -> bool:
    """Whether selecting the History tab starts a fetch."""
    is_stale = last_fetched_ts == 0 or now - last_fetched_ts > HISTORY_STALE_AFTER_S
    return bool(is_stale and not in_flight)


def api_pill(sample: Any, safety_pct: Any) -> dict:
    """The status-line pill for the busiest connected exchange."""
    percent = int(sample.load_score * 100)
    if sample.load_score > safety_pct:
        colour = API_PILL_RED_COLOUR
    elif sample.load_score > API_PILL_AMBER_ABOVE:
        colour = API_PILL_AMBER_COLOUR
    else:
        colour = API_PILL_GREEN_COLOUR
    return {
        "text": API_PILL_TEXT_FORMAT.format(
            exchange=sample.exchange,
            calls_per_minute=sample.calls_per_minute,
            ceiling_cpm=sample.ceiling_cpm,
            percent=percent,
        ),
        "style": PILL_STYLE_FORMAT.format(colour=colour),
    }


def api_pill_idle() -> dict:
    """The pill with no exchange connected."""
    return {
        "text": API_PILL_IDLE_TEXT,
        "style": PILL_STYLE_FORMAT.format(colour=API_PILL_IDLE_COLOUR),
    }


def ai_pill(ai_config: Any) -> dict:
    """The status-line pill for the AI monitor."""
    if ai_config.get("enabled") and ai_config.get("api_key"):
        return {
            "text": AI_READY_TEXT,
            "style": PILL_STYLE_FORMAT.format(colour=AI_READY_COLOUR),
        }
    return {
        "text": AI_OFF_TEXT,
        "style": PILL_STYLE_FORMAT.format(colour=AI_OFF_COLOUR),
    }


def stat_card_values(aggregate: Any, written: Any = None) -> dict:
    """The six card values, in the order the tick writes them onto the cards.

    `written` is filled as each card is written, so a read that refuses
    part way leaves the cards before it written and the rest untouched,
    which is what the tick leaves on screen.

    Scrummed and Folded are both read BEFORE either is written, so a bad
    Folded reading blanks the Scrummed card as well as its own.
    """
    filled = {} if written is None else written
    scrummed = float(aggregate.get(SCRUMMED_KEY, 0.0) or 0.0)
    folded = float(aggregate.get(FOLDED_KEY, 0.0) or 0.0)
    filled["scrummed"] = SCRUMMED_FORMAT.format(value=scrummed)
    filled["folded"] = FOLDED_FORMAT.format(value=folded)
    filled["pnl"] = PNL_FORMAT.format(value=aggregate[PNL_KEY])
    filled["trades"] = TRADES_FORMAT.format(value=aggregate[TRADES_KEY])
    filled["bots"] = BOTS_FORMAT.format(value=aggregate[BOTS_KEY])
    filled["errors"] = ERRORS_FORMAT.format(value=aggregate.get(ERRORS_KEY, 0))
    return filled


def spendable_payload(aggregate: Any, exchange_count: Any) -> dict:
    """What the spendable panel is handed on one tick."""
    wallet_cash = float(aggregate.get(WALLET_CASH_KEY, 0.0) or 0.0)
    crypto_value = float(aggregate.get(CRYPTO_VALUE_KEY, 0.0) or 0.0)
    if wallet_cash > 0 or crypto_value > 0:
        return {
            "spendable": wallet_cash,
            "total_realised": SPENDABLE_UNKNOWN,
            "locked": crypto_value,
            "mature": SPENDABLE_UNKNOWN,
            "exchange_count": exchange_count,
        }
    return {
        "spendable": SPENDABLE_UNKNOWN,
        "total_realised": SPENDABLE_UNKNOWN,
        "locked": SPENDABLE_UNKNOWN,
        "mature": SPENDABLE_UNKNOWN,
        "exchange_count": exchange_count,
    }


def console_buffered_text(held: Any, cap: Any, dropped: Any) -> str:
    """The buffered-count line shown every 500 ms while the console is paused."""
    if dropped > 0:
        return CONSOLE_BUFFERED_DROPPED_FORMAT.format(
            held=held, cap=cap, dropped=dropped
        )
    return CONSOLE_BUFFERED_FORMAT.format(held=held, cap=cap)


def signal_gap_marker_text(skipped: Any) -> str:
    """The line the signals pane draws over a skipped stretch."""
    return SIGNAL_GAP_MARKER_FORMAT.format(skipped=skipped)


def api_event_block(entry: Any, stamp: Any) -> str:
    """The plain-text block one API interaction adds to the API log pane."""
    lines = [
        API_EVENT_HEAD_FORMAT.format(
            stamp=stamp,
            exchange=entry["exchange"].upper(),
            action=entry["action"],
        ),
        API_EVENT_REASON_FORMAT.format(reason=entry["reason"]),
    ]
    if entry.get("endpoint"):
        lines.append(API_EVENT_ENDPOINT_FORMAT.format(endpoint=entry["endpoint"]))
    if entry.get("result"):
        lines.append(API_EVENT_RESULT_FORMAT.format(result=entry["result"]))
    if entry.get("elapsed_ms", 0) > 0:
        lines.append(API_EVENT_RESPONSE_FORMAT.format(elapsed_ms=entry["elapsed_ms"]))
    if entry.get("data_usage"):
        lines.append(API_EVENT_DATA_USAGE_FORMAT.format(data_usage=entry["data_usage"]))
    return "\n".join(lines)


def ivp_empty_state_cause(bot: Any, bot_id: Any = "") -> tuple:
    """The one reason the indicator panel is showing nothing. Never a list."""
    if bot is None:
        return CAUSE_BOT_MISSING, {"bot_id": str(bot_id or "")}

    detail: dict = {"bot_id": str(bot_id or "")}
    state = ""
    try:
        state = str(getattr(getattr(bot, "state", None), "value", "")).lower()
    except (AttributeError, TypeError, ValueError):
        state = ""

    if state in NOT_RUNNING_STATES:
        detail["state"] = state
        return CAUSE_NOT_RUNNING, detail
    if state == ERROR_STATE:
        detail["error"] = str(
            getattr(getattr(bot, "stats", None), "last_error", "") or ""
        )
        return CAUSE_BOT_ERROR, detail

    try:
        parked_ticks = int(getattr(bot, "_at_target_counter", 0) or 0)
    except (TypeError, ValueError):
        parked_ticks = 0
    if parked_ticks > 0:
        try:
            position = float(getattr(bot, "position_value_usd", 0.0) or 0.0)
            target = float(getattr(bot, "_target_balance", 0.0) or 0.0)
        except (TypeError, ValueError):
            position, target = 0.0, 0.0
        detail.update(
            {"position": position, "target": target, "delta": position - target}
        )
        return CAUSE_PARKED_AT_TARGET, detail

    cached = cached_candle_count(bot)
    if cached is not None and cached < CANDLES_REQUIRED:
        detail.update(
            {
                "candles": cached,
                "symbol": getattr(bot.config, "symbol", "") or "",
                "timeframe": (
                    getattr(bot.config, "ta_timeframe", "") or DEFAULT_TIMEFRAME
                ),
            }
        )
        return CAUSE_TOO_FEW_CANDLES, detail

    return CAUSE_COLD_START, detail


def cached_candle_count(bot: Any) -> Optional[int]:
    """Rows the shared price pool already holds for this bot, or None."""
    try:
        return bot.cached_candles
    except (AttributeError, ImportError, TypeError):
        return None


def trade_filled_sounds(trade_type: Any, profit: Any) -> list:
    """Which sounds a filled trade plays, in the order the window plays them."""
    played = []
    upper = (trade_type or "").upper()
    if upper in RIFLE_TRADE_TYPES:
        played.append(FIRE_SOUND)
    if profit > 0:
        played.append(PROFIT_SOUND)
    if upper == DRIP_TRADE_TYPE:
        played.append(DRIP_SOUND)
    return played


def hottest_beep_phase(statuses: Any) -> Optional[str]:
    """The hottest scrum phase across the fleet, or None when all are quiet."""
    hottest = None
    for status in statuses:
        if status.get("mode") != BEEP_MODE:
            continue
        if status.get("state") not in BEEP_STATES:
            continue
        phase = status.get("scrum_target_mode")
        if phase == BEEP_FIRE_PHASE:
            return BEEP_FIRE_PHASE
        if phase == BEEP_TRACK_PHASE and hottest != BEEP_FIRE_PHASE:
            hottest = BEEP_TRACK_PHASE
    return hottest


def beep_cadence_s(phase: Any) -> float:
    """The seconds between beeps for a phase."""
    return BEEP_FIRE_CADENCE_S if phase == BEEP_FIRE_PHASE else BEEP_TRACK_CADENCE_S


def pulse_opacity(phase: Any) -> float:
    """The opacity the pulse ticker writes onto every accent element."""
    return PULSE_OPACITY_MID + PULSE_OPACITY_SWING * math.sin(phase)


def glow_blur(phase: Any) -> float:
    """The blur radius the pulse ticker writes onto every armed Fire glow."""
    return GLOW_BLUR_MID + GLOW_BLUR_SWING * math.sin(phase * GLOW_PHASE_RATE)


def is_equity_exchange(exchange_id: Any, equity_ids: Any) -> bool:
    """Whether this exchange belongs to the stock layer."""
    return exchange_id.lower() in equity_ids


def tooltip_for(text: Any, existing: Any) -> Optional[str]:
    """The tooltip the window sets on a child, or None when it sets none."""
    if not text or existing:
        return None
    for abbreviation, explanation in ABBREVIATION_TOOLTIPS:
        if abbreviation in text:
            return explanation
    return None


def extractor_parent_refusal(
    base_currency: Any,
    exchange_id: Any,
    parent: Any,
    candidates: Any,
    has_roster: Any = True,
) -> Optional[str]:
    """Why an Extractor may not be created here, or None when it may."""
    asset = (base_currency or "").strip().upper() or EXTRACTOR_UNKNOWN_ASSET
    venue = (exchange_id or "").strip() or EXTRACTOR_UNKNOWN_VENUE
    if not has_roster:
        return EXTRACTOR_NO_ROSTER_FORMAT.format(venue=venue, asset=asset)
    if parent is not None:
        return None
    rows = list(candidates or [])
    if not rows:
        return EXTRACTOR_NO_PARENT_FORMAT.format(venue=venue, asset=asset)
    ids = ", ".join(bot_id for bot_id, _bot in rows)
    return EXTRACTOR_AMBIGUOUS_FORMAT.format(
        count=len(rows), venue=venue, asset=asset, ids=ids
    )


def adopt_summary_lines(proposal: Any, collisions: Any) -> list:
    """The confirmation text the adopt gate shows before it changes anything."""
    new_bots = [
        bot for bot in proposal.get("bots", []) if not bot.get("existing_bot_id")
    ]
    wires = list(proposal.get("wires", []))
    budget = sum(float(bot.get("suggested_target_usd", 0.0)) for bot in new_bots)
    lines = [
        ADOPT_HEAD_FORMAT.format(
            title=proposal.get("title", ADOPT_DEFAULT_PROPOSAL_TITLE)
        ),
        "",
        ADOPT_NEW_BOTS_FORMAT.format(count=len(new_bots), budget=budget),
        ADOPT_WIRES_FORMAT.format(count=len(wires)),
    ]
    rows = list(collisions or [])
    if rows:
        lines += ["", ADOPT_COLLISION_HEAD_FORMAT.format(count=len(rows))]
        for row in rows[:ADOPT_COLLISIONS_SHOWN]:
            lines.append(
                ADOPT_COLLISION_ROW_FORMAT.format(
                    source_asset=row["source_asset"],
                    target_asset=row["target_asset"],
                    current_pct=row["current_pct"],
                    proposed_pct=row["proposed_pct"],
                )
            )
        if len(rows) > ADOPT_COLLISIONS_SHOWN:
            lines.append(
                ADOPT_COLLISION_OVERFLOW_FORMAT.format(
                    count=len(rows) - ADOPT_COLLISIONS_SHOWN
                )
            )
        lines.append(ADOPT_SNAPSHOT_LINE)
    lines += ["", ADOPT_TAIL_LINE]
    return lines


def orphan_report_text(created_ids: Any) -> Optional[str]:
    """The line naming the bots an aborted adopt left behind, or None."""
    rows = list(created_ids or [])
    if not rows:
        return None
    return ORPHAN_LOG_FORMAT.format(
        count=len(rows),
        ids=", ".join(str(one)[:ORPHAN_ID_CHARACTERS] for one in rows),
    )


def menu_model(themes: Any) -> list:
    """The four menus the window builds, in the order it builds them."""
    return [
        {"title": FILE_MENU_TITLE, "items": list(FILE_MENU_ITEMS)},
        {"title": EXCHANGE_MENU_TITLE, "items": list(EXCHANGE_MENU_ITEMS)},
        {
            "title": THEME_MENU_TITLE,
            "items": [display for _name, display in themes],
        },
        {"title": HELP_MENU_TITLE, "items": list(HELP_MENU_ITEMS)},
    ]


def mode_button_style(mode: Any) -> str:
    """The style rule the mode button carries in one wing."""
    return MODE_BUTTON_STYLE_FORMAT.format(
        rgb=MODE_BUTTON_RGB[mode], colour=MODE_BUTTON_COLOUR[mode]
    )


def mode_tab_styles(mode: Any, tabs_ready: Any) -> dict:
    """The style rules the two layer tab books carry in one wing."""
    if not tabs_ready:
        return {}
    active = MODE_TAB_STYLE_FORMAT.format(colour=MODE_BUTTON_COLOUR[mode])
    if mode == CRYPTO_MODE:
        return {CRYPTO_MODE: active, STOCK_MODE: MODE_TAB_STYLE_CLEARED}
    return {STOCK_MODE: active, CRYPTO_MODE: MODE_TAB_STYLE_CLEARED}


# Stand-ins


class LoadSample:
    """One reading of an exchange's API load."""

    def __init__(
        self,
        exchange: Any = "",
        calls_per_minute: Any = 0.0,
        ceiling_cpm: Any = 0.0,
        load_score: Any = 0.0,
    ) -> None:
        self.exchange = exchange
        self.calls_per_minute = calls_per_minute
        self.ceiling_cpm = ceiling_cpm
        self.load_score = load_score


class LoadMonitorSource:
    """The API-load monitor the pill reads, and the readings it answers with."""

    def __init__(self, samples: Any = None, safety_pct: Any = 0.75) -> None:
        self.samples = dict(samples or {})
        self.safety_pct = safety_pct

    def sample(self, exchange_id: Any) -> Any:
        """The reading for one exchange."""
        return self.samples[exchange_id]


class BotConfigView:
    """The config fields this window reads off a bot."""

    def __init__(
        self,
        symbol: Any = "",
        ta_timeframe: Any = "",
        exchange_id: Any = "",
    ) -> None:
        self.symbol = symbol
        self.ta_timeframe = ta_timeframe
        self.exchange_id = exchange_id


class BotStateView:
    """The state object whose ``value`` this window reads."""

    def __init__(self, value: Any = "") -> None:
        self.value = value


class BotStatsView:
    """The stats fields this window reads off a bot."""

    def __init__(self, last_error: Any = "") -> None:
        self.last_error = last_error


class BotView:
    """One bot, holding only the fields this window reads."""

    def __init__(
        self,
        state: Any = "",
        last_error: Any = "",
        at_target_counter: Any = 0,
        position_value_usd: Any = 0.0,
        target_balance: Any = 0.0,
        symbol: Any = "",
        ta_timeframe: Any = "",
        exchange_id: Any = "",
        cached_candles: Any = None,
    ) -> None:
        self.state = BotStateView(state)
        self.stats = BotStatsView(last_error)
        self._at_target_counter = at_target_counter
        self.position_value_usd = position_value_usd
        self._target_balance = target_balance
        self.config = BotConfigView(symbol, ta_timeframe, exchange_id)
        self.cached_candles = cached_candles


class FleetSource:
    """The bot manager, holding the fleet a stored fleet load produced.

    ``statuses`` is the list of status dictionaries
    ``BotManager.list_bots`` answers with. ``aggregate`` is what
    ``get_aggregate_stats`` answers with. Neither is invented here: both
    reach the model as values.
    """

    def __init__(
        self,
        aggregate: Any = None,
        statuses: Any = None,
        parent: Any = None,
        candidates: Any = None,
    ) -> None:
        self.aggregate = aggregate if aggregate is not None else {}
        self.statuses = list(statuses or [])
        self.parent = parent
        self.candidates = list(candidates or [])
        self.unregistered: list = []

    def get_aggregate_stats(self) -> Any:
        """The totals the six stat cards are written from."""
        return self.aggregate

    def list_bots(self) -> list:
        """Every bot in the fleet, as status dictionaries."""
        return self.statuses

    def find_parent_bot_for_base_currency(
        self, base_currency: Any, exchange_id: Any = ""
    ) -> Any:
        """The one Scrumming Bot holding this currency, or None."""
        return self.parent

    def list_parent_bot_candidates_for_base_currency(
        self, base_currency: Any, exchange_id: Any = ""
    ) -> list:
        """Every Scrumming Bot holding this currency."""
        return self.candidates

    def unregister(self, bot_id: Any) -> None:
        """Drop one bot from the roster."""
        self.unregistered.append(bot_id)


class SettingsSource:
    """The settings store the window reads its theme and AI config from."""

    def __init__(self, values: Any = None, reset_raises: Any = None) -> None:
        self.values = dict(values or {})
        self.reset_raises = reset_raises
        self.reset_count = 0

    def get(self, key: Any, default: Any = None) -> Any:
        """One stored value, or `default`."""
        return self.values.get(key, default)

    def reset_defaults(self) -> None:
        """Clear every stored value."""
        if self.reset_raises is not None:
            raise self.reset_raises
        self.reset_count += 1


class ThemeSource:
    """The themes the Theme menu lists and the switch accepts."""

    def __init__(self, themes: Any = None) -> None:
        self.themes = list(themes or [])

    def names(self) -> list:
        """Every theme name, in menu order."""
        return [name for name, _display in self.themes]

    def display_names(self) -> list:
        """Every theme label, in menu order."""
        return [display for _name, display in self.themes]


class HistoryTabSource:
    """The History tab the window asks to refresh when its tab is picked."""

    def __init__(
        self,
        last_fetched_ts: Any = 0.0,
        fetch_in_flight: Any = False,
        raises: Any = None,
    ) -> None:
        self.last_fetched_ts = last_fetched_ts
        self.fetch_in_flight = fetch_in_flight
        self.raises = raises
        self.refreshes = 0

    def refresh(self) -> None:
        """Start one fetch."""
        if self.raises is not None:
            raise self.raises
        self.refreshes += 1


class ConsoleHandlerSource:
    """The console log handler the Pause button stops and starts."""

    def __init__(self, held: Any = 0, cap: Any = 0, dropped: Any = 0) -> None:
        self.held = held
        self.cap = cap
        self.dropped = dropped
        self.paused = False

    def set_paused(self, paused: Any) -> None:
        """Stop or start the log pane."""
        self.paused = paused


class ModelCall:
    """One step the model took, in the order the window takes it."""

    def __init__(self, name: str, detail: Any = None) -> None:
        self.name = name
        self.detail = detail

    def as_dict(self) -> dict:
        """This step as plain values."""
        return {"name": self.name, "detail": self.detail}


# The model


class MainWindowModel:
    """The window's chrome, its status line, its cards and every path it takes.

    ``build`` fills the title, the menus, the tab book and the status
    line. ``refresh`` is one tick of the two-second timer. The other
    methods are the window's menu items, its buttons and the events it
    answers. Every step is appended to ``calls``.
    """

    def __init__(
        self,
        version: Any = None,
        fleet: Any = None,
        settings: Any = None,
        themes: Any = None,
        load_monitor: Any = None,
        history_tab: Any = None,
        console_handler: Any = None,
        equity_exchange_ids: Any = None,
        exchange_tab_ids: Any = None,
        connector_ids: Any = None,
        trading_mode: Any = CRYPTO_MODE,
        tabs_ready: Any = True,
        failed_tabs: Any = None,
    ) -> None:
        self.version = running_version() if version is None else version
        self.fleet = fleet
        self.settings = settings
        self.themes = themes if themes is not None else ThemeSource()
        self.load_monitor = load_monitor
        self.history_tab = history_tab
        self.console_handler = console_handler
        self.equity_exchange_ids = set(equity_exchange_ids or ())
        self.exchange_tab_ids = list(exchange_tab_ids or [])
        self.connector_ids = list(connector_ids or [])
        self.trading_mode = trading_mode
        self.tabs_ready = tabs_ready
        self.failed_tabs = set(failed_tabs or ())

        self.window_title = ""
        self.minimum_size = (MINIMUM_WIDTH_PX, MINIMUM_HEIGHT_PX)
        self.menus: list = []
        self.tab_labels: list = []
        self.tab_methods = dict(TAB_METHODS)
        self.tabs_movable = TABS_MOVABLE
        self.current_tab = ""
        self.header_strip_shown = True
        self.status_text = ""
        self.api_pill_text = ""
        self.api_pill_style = ""
        self.api_pill_tooltip = ""
        self.ai_pill_text = ""
        self.ai_pill_style = ""
        self.card_values: dict = {}
        self.spendable: Any = None
        self.tick_error: Any = None
        self.subscriptions: list = []
        self.unsubscriptions: list = list(BUS_UNSUBSCRIPTIONS)
        self.timers: list = []
        self.log_lines: list = []
        self.spool_lines: list = []
        self.boxes: list = []
        self.api_log_lines: list = []
        self.api_records: list = []
        self.sounds: list = []
        self.console_paused = False
        self.console_button_text = CONSOLE_PAUSE_TEXT
        self.console_indicator = CONSOLE_RUNNING_INDICATOR
        self.mode_button_text = MODE_BUTTON_TEXTS[CRYPTO_MODE]
        self.mode_button_checked = MODE_BUTTON_CHECKED[CRYPTO_MODE]
        self.mode_button_style = ""
        self.mode_tab_styles: dict = {}
        self.trading_stack_index = MODE_STACK_INDEX[CRYPTO_MODE]
        self.pulse_phase = 0.0
        self.pulse_opacity = 1.0
        self.glow_blur = 0.0
        self.beep_last_ts = 0.0
        self.error_buffer: list = []
        self.calls: list = []

    # -- construction --------------------------------------------------

    def build(self) -> "MainWindowModel":
        """Fill the title, the menus, the tab book and the status line."""
        self.window_title = window_title(self.version)
        self._record("window_title", self.window_title)
        self.menus = menu_model(self.themes.themes)
        self._record("menus", [menu["title"] for menu in self.menus])
        self.subscriptions = list(BUS_SUBSCRIPTIONS)
        self._record("subscribe", self.subscriptions)
        built = constructed_tabs(self.failed_tabs)
        self.tab_labels = reordered_tabs(built, CANONICAL_TAB_ORDER)
        self._record("tabs", list(self.tab_labels))
        self.timers = [
            {"name": "dashboard", "interval_ms": DASHBOARD_TICK_MS, "started": True},
            {"name": "pulse", "interval_ms": PULSE_TICK_MS, "started": True},
            {"name": "tooltip", "interval_ms": TOOLTIP_TICK_MS, "started": True},
            {
                "name": "tooltip_first_scan",
                "interval_ms": TOOLTIP_FIRST_SCAN_MS,
                "started": True,
            },
        ]
        self._record("timers", [timer["name"] for timer in self.timers])
        self.status_text = STATUS_READY_TEXT
        idle = api_pill_idle()
        self.api_pill_text = idle["text"]
        self.api_pill_style = idle["style"]
        self.api_pill_tooltip = API_PILL_TOOLTIP
        ai_config = self._ai_config()
        pill = ai_pill(ai_config) if self.settings is not None else ai_pill({})
        self.ai_pill_text = pill["text"]
        self.ai_pill_style = pill["style"]
        self._record("status_bar", self.status_text)
        self.mode_button_text = MODE_BUTTON_TEXTS[self.trading_mode]
        self.mode_button_checked = MODE_BUTTON_CHECKED[self.trading_mode]
        self.current_tab = self.tab_labels[0] if self.tab_labels else ""
        self.log(STARTED_LOG_FORMAT.format(version=self.version), "success")
        return self

    def _ai_config(self) -> dict:
        if self.settings is None:
            return {}
        return self.settings.get("ai_monitor", {})

    # -- the two-second tick -------------------------------------------

    def refresh(self) -> "MainWindowModel":
        """One dashboard tick: the six cards, the panel and the pill.

        The pill is rewritten only when the fleet holds a bot, which is
        where the shipped tick calls it from.
        """
        if self.fleet is None:
            self._record("refresh_skipped", "no fleet")
            return self
        try:
            aggregate = self.fleet.get_aggregate_stats()
            stat_card_values(aggregate, self.card_values)
            self._record("cards", dict(self.card_values))
            self.spendable = spendable_payload(aggregate, len(self.exchange_tab_ids))
            self._record("spendable", dict(self.spendable))
            statuses = self.fleet.list_bots()
        except Exception as exc:
            self.tick_error = type(exc).__name__
            self._record("tick_crashed", self.tick_error)
            return self
        if statuses:
            self.refresh_api_pill()
        else:
            self._record("tick_empty_fleet", True)
        return self

    def refresh_api_pill(self) -> "MainWindowModel":
        """Rewrite the status-line pill from the busiest connected exchange."""
        if not self.connector_ids or self.load_monitor is None:
            idle = api_pill_idle()
            self.api_pill_text = idle["text"]
            self.api_pill_style = idle["style"]
            self._record("api_pill", self.api_pill_text)
            return self
        worst = None
        for exchange_id in self.connector_ids:
            sample = self.load_monitor.sample(exchange_id)
            if worst is None or sample.load_score > worst.load_score:
                worst = sample
        if worst is None:
            self._record("api_pill_unchanged", self.api_pill_text)
            return self
        pill = api_pill(worst, self.load_monitor.safety_pct)
        self.api_pill_text = pill["text"]
        self.api_pill_style = pill["style"]
        self._record("api_pill", self.api_pill_text)
        return self

    # -- the window's own paths ----------------------------------------

    def change_tab(self, index: Any, now: Any = 0.0) -> "MainWindowModel":
        """The operator picks a tab."""
        name = self.tab_labels[index]
        self.current_tab = name
        self.header_strip_shown = header_strip_visible(name)
        self._record("tab_changed", name)
        if name == HISTORY_TAB and self.history_tab is not None:
            due = history_refresh_due(
                self.history_tab.last_fetched_ts,
                self.history_tab.fetch_in_flight,
                now,
            )
            if due:
                try:
                    self.history_tab.refresh()
                    self._record("history_refresh", True)
                except Exception:
                    self._record("history_refresh_failed", True)
            else:
                self._record("history_refresh", False)
        return self

    def toggle_console_pause(self, paused: Any) -> "MainWindowModel":
        """The Console tab's Pause button."""
        self.console_paused = paused
        self._record("console_paused", paused)
        if self.console_handler is None:
            return self
        self.console_handler.set_paused(paused)
        if paused:
            self.console_button_text = CONSOLE_RESUME_TEXT
            self.console_indicator = CONSOLE_PAUSED_INDICATOR
        else:
            self.console_button_text = CONSOLE_PAUSE_TEXT
            self.console_indicator = CONSOLE_RUNNING_INDICATOR
        self._record("console_button", self.console_button_text)
        return self

    def refresh_console_indicator(self) -> "MainWindowModel":
        """The 500 ms buffered-count update while the console is paused."""
        handler = self.console_handler
        if handler is None or not handler.paused:
            self._record("console_indicator_skipped", True)
            return self
        self.console_indicator = console_buffered_text(
            handler.held, handler.cap, handler.dropped
        )
        self._record("console_indicator", self.console_indicator)
        return self

    def toggle_trading_mode(self) -> "MainWindowModel":
        """The Crypto / Stock wing button."""
        self.trading_mode = (
            STOCK_MODE if self.trading_mode == CRYPTO_MODE else CRYPTO_MODE
        )
        self.mode_button_text = MODE_BUTTON_TEXTS[self.trading_mode]
        self.mode_button_checked = MODE_BUTTON_CHECKED[self.trading_mode]
        self.trading_stack_index = MODE_STACK_INDEX[self.trading_mode]
        self.window_title = wing_title(self.trading_mode)
        self.log(WING_LOGS[self.trading_mode], "info")
        self.mode_button_style = mode_button_style(self.trading_mode)
        self.mode_tab_styles = mode_tab_styles(self.trading_mode, self.tabs_ready)
        self._record("trading_mode", self.trading_mode)
        return self

    def switch_theme(self, name: Any) -> "MainWindowModel":
        """A Theme menu item."""
        if name not in self.themes.names():
            raise ValueError(f"Unknown theme: {name}. Available: {self.themes.names()}")
        self.log(THEME_SWITCHED_LOG_FORMAT.format(name=name), "info")
        self._record("theme", name)
        return self

    def settings_changed(self) -> "MainWindowModel":
        """The Settings dialog reported a save."""
        if self.settings is None:
            self._record("settings_changed_skipped", True)
            return self
        self.switch_theme(self.settings.get("theme", DEFAULT_THEME))
        ai_config = self.settings.get("ai_monitor", {})
        if self.fleet is not None:
            pill = ai_pill(ai_config)
            self.ai_pill_text = pill["text"]
            self.ai_pill_style = pill["style"]
            if ai_config.get("enabled") and ai_config.get("api_key"):
                phrase = ai_config.get("connect_phrase", "")[:AI_PHRASE_CHARACTERS]
                self.log(AI_RECONFIGURED_LOG_FORMAT.format(phrase=phrase), "info")
        self.log(SETTINGS_SAVED_LOG, "success")
        return self

    def reset_settings(self, confirmed: Any) -> "MainWindowModel":
        """The File menu's Reset All Settings."""
        self.boxes.append(
            {"kind": BOX_QUESTION, "title": RESET_TITLE, "text": RESET_TEXT}
        )
        if not confirmed:
            self._record("reset_declined", True)
            return self
        if self.settings is not None:
            self.settings.reset_defaults()
        self.log(RESET_LOG, "warning")
        self.spool(RESET_SPOOL, "warning")
        self.boxes.append(
            {
                "kind": BOX_INFORMATION,
                "title": RESET_DONE_TITLE,
                "text": RESET_DONE_TEXT,
            }
        )
        self._record("reset_done", True)
        return self

    def delete_bot(self, bot_id: Any, confirmed: Any) -> "MainWindowModel":
        """The bot table's Delete command."""
        self.boxes.append(
            {
                "kind": BOX_QUESTION,
                "title": DELETE_TITLE,
                "text": DELETE_TEXT_FORMAT.format(bot_id=bot_id),
            }
        )
        if not confirmed:
            self._record("delete_declined", bot_id)
            return self
        if self.fleet is not None:
            self.fleet.unregister(bot_id)
        self.log(DELETE_LOG_FORMAT.format(bot_id=bot_id), "warning")
        self.spool(DELETE_SPOOL_FORMAT.format(bot_id=bot_id), "warning")
        self._record("delete_done", bot_id)
        return self

    def create_extractor(self, base_currency: Any, exchange_id: Any) -> bool:
        """The Extractor parent check. True when creation must stop."""
        has_roster = self.fleet is not None
        parent = None
        candidates: list = []
        if has_roster:
            parent = self.fleet.find_parent_bot_for_base_currency(
                base_currency, exchange_id=exchange_id
            )
            if parent is None:
                candidates = self.fleet.list_parent_bot_candidates_for_base_currency(
                    base_currency, exchange_id=exchange_id
                )
        reason = extractor_parent_refusal(
            base_currency, exchange_id, parent, candidates, has_roster
        )
        if reason is None:
            self._record("extractor_allowed", base_currency)
            return False
        self.boxes.append(
            {
                "kind": BOX_CRITICAL,
                "title": EXTRACTOR_REFUSAL_TITLE,
                "text": EXTRACTOR_REFUSAL_BOX_FORMAT.format(reason=reason),
            }
        )
        self.log(EXTRACTOR_REFUSAL_LOG_FORMAT.format(reason=reason), "error")
        self.api_records.append(
            {
                "exchange": exchange_id,
                "action": EXTRACTOR_REFUSAL_ACTION,
                "reason": EXTRACTOR_REFUSAL_API_REASON,
                "result": EXTRACTOR_REFUSAL_API_RESULT_FORMAT.format(
                    base_currency=base_currency
                ),
                "level": "warning",
                "data_usage": EXTRACTOR_REFUSAL_API_DATA_USAGE,
            }
        )
        self._record("extractor_refused", reason)
        return True

    def adopt_topology(
        self, proposal: Any, collisions: Any = None, confirmed: Any = True
    ) -> "MainWindowModel":
        """The Market Inspector's Adopt gate, up to the confirm."""
        if not isinstance(proposal, dict) or not proposal.get("bots"):
            self._record("adopt_ignored", True)
            return self
        if self.fleet is None:
            self.boxes.append(
                {
                    "kind": BOX_WARNING,
                    "title": ADOPT_TITLE,
                    "text": ADOPT_NO_MANAGER_TEXT,
                }
            )
            self._record("adopt_no_manager", True)
            return self
        lines = adopt_summary_lines(proposal, collisions)
        self.boxes.append(
            {"kind": BOX_QUESTION, "title": ADOPT_TITLE, "text": "\n".join(lines)}
        )
        if not confirmed:
            self.log(ADOPT_CANCELLED_LOG, "info")
            self._record("adopt_cancelled", True)
            return self
        self._record("adopt_confirmed", len(lines))
        return self

    def report_orphans(self, created_ids: Any) -> "MainWindowModel":
        """Name the bots an aborted adopt left behind."""
        text = orphan_report_text(created_ids)
        if text is None:
            self._record("orphans", 0)
            return self
        self.log(text, "warning")
        self._record("orphans", len(list(created_ids)))
        return self

    def api_event(
        self,
        entry: Any,
        stamp: Any,
        thread_name: Any = MAIN_THREAD_NAME,
        paused: Any = False,
    ) -> str:
        """One API interaction reaching the API log pane."""
        if thread_name != MAIN_THREAD_NAME:
            self._record("api_event_refused", thread_name)
            return API_EVENT_WRONG_THREAD
        block = api_event_block(entry, stamp)
        if paused:
            self._record("api_event_buffered", block)
            return API_EVENT_BUFFERED
        self.api_log_lines.append(block)
        self._record("api_event", block)
        return API_EVENT_APPENDED

    def indicator_empty_state(self, bot: Any, bot_id: Any = "") -> tuple:
        """What the indicator panel is told when it has nothing to show."""
        answer = ivp_empty_state_cause(bot, bot_id)
        self._record("indicator_empty_state", answer[0])
        return answer

    def trade_filled(self, trade_type: Any, profit: Any) -> list:
        """A filled trade, and the sounds it plays."""
        played = trade_filled_sounds(trade_type, profit)
        self.sounds.extend(played)
        self._record("trade_filled", list(played))
        return played

    def tracking_beep(self, statuses: Any, now: Any) -> str:
        """One dispatch of the tracking beep."""
        phase = hottest_beep_phase(statuses)
        if phase is None:
            self._record("beep", BEEP_SILENT)
            return BEEP_SILENT
        cadence = beep_cadence_s(phase)
        if now - self.beep_last_ts < cadence:
            self._record("beep", BEEP_THROTTLED)
            return BEEP_THROTTLED
        self.beep_last_ts = now
        self.sounds.append(BEEP_TRACK_PHASE)
        self._record("beep", BEEP_PLAYED)
        return BEEP_PLAYED

    def pulse_tick(self) -> "MainWindowModel":
        """One 80 ms pulse step."""
        self.pulse_phase += PULSE_PHASE_STEP
        self.pulse_opacity = pulse_opacity(self.pulse_phase)
        self.glow_blur = glow_blur(self.pulse_phase)
        self._record("pulse", self.pulse_phase)
        return self

    def show_about(self) -> "MainWindowModel":
        """The Help menu's About."""
        self.boxes.append({"kind": BOX_ABOUT, "title": ABOUT_TITLE, "text": ABOUT_TEXT})
        self._record("about", ABOUT_TITLE)
        return self

    def is_equity_exchange(self, exchange_id: Any) -> bool:
        """Whether this exchange belongs to the stock layer."""
        return is_equity_exchange(exchange_id, self.equity_exchange_ids)

    # -- sinks ---------------------------------------------------------

    def log(self, text: Any, level: Any = "info") -> None:
        """One line on the activity log."""
        self.log_lines.append({"text": text, "level": level})

    def spool(self, text: Any, level: Any = "info") -> None:
        """One notification on the spool."""
        self.spool_lines.append({"text": text, "level": level})

    def _record(self, name: str, detail: Any = None) -> None:
        self.calls.append(ModelCall(name, detail))

    # -- the answer ----------------------------------------------------

    def as_dict(self) -> dict:
        """Every value the window shows, as plain values."""
        return {
            "window_title": self.window_title,
            "minimum_size": list(self.minimum_size),
            "menus": self.menus,
            "tab_labels": list(self.tab_labels),
            "tab_methods": dict(self.tab_methods),
            "tabs_movable": self.tabs_movable,
            "current_tab": self.current_tab,
            "header_strip_shown": self.header_strip_shown,
            "status_text": self.status_text,
            "api_pill_text": self.api_pill_text,
            "api_pill_style": self.api_pill_style,
            "api_pill_tooltip": self.api_pill_tooltip,
            "ai_pill_text": self.ai_pill_text,
            "ai_pill_style": self.ai_pill_style,
            "card_values": dict(self.card_values),
            "spendable": self.spendable,
            "tick_error": self.tick_error,
            "subscriptions": list(self.subscriptions),
            "unsubscriptions": list(self.unsubscriptions),
            "timers": [dict(timer) for timer in self.timers],
            "log_lines": [dict(line) for line in self.log_lines],
            "spool_lines": [dict(line) for line in self.spool_lines],
            "boxes": [dict(box) for box in self.boxes],
            "api_log_lines": list(self.api_log_lines),
            "api_records": [dict(record) for record in self.api_records],
            "sounds": list(self.sounds),
            "console_paused": self.console_paused,
            "console_button_text": self.console_button_text,
            "console_indicator": self.console_indicator,
            "mode_button_text": self.mode_button_text,
            "mode_button_checked": self.mode_button_checked,
            "mode_button_style": self.mode_button_style,
            "mode_tab_styles": dict(self.mode_tab_styles),
            "trading_stack_index": self.trading_stack_index,
            "trading_mode": self.trading_mode,
            "pulse_phase": self.pulse_phase,
            "pulse_opacity": self.pulse_opacity,
            "glow_blur": self.glow_blur,
            "calls": [call.as_dict() for call in self.calls],
        }


def build_view_model(params: Any = None) -> dict:
    """Build the window from `params` and answer with everything it shows."""
    given = dict(params or {})
    themes = ThemeSource(given.get("themes") or [])
    settings = None
    if given.get("settings") is not None:
        settings = SettingsSource(given["settings"])
    fleet = None
    if given.get("fleet") is not None:
        fleet = FleetSource(
            aggregate=given["fleet"].get("aggregate"),
            statuses=given["fleet"].get("statuses"),
        )
    model = MainWindowModel(
        version=given.get("version"),
        fleet=fleet,
        settings=settings,
        themes=themes,
        equity_exchange_ids=given.get("equity_exchange_ids"),
        exchange_tab_ids=given.get("exchange_tab_ids"),
        connector_ids=given.get("connector_ids"),
        trading_mode=given.get("trading_mode", CRYPTO_MODE),
        failed_tabs=given.get("failed_tabs"),
    )
    model.build()
    if given.get("console_pause") is not None:
        model.toggle_console_pause(bool(given["console_pause"]))
    if fleet is not None:
        model.refresh()
    return model.as_dict()


def view_model(params: Any = None) -> dict:
    """The bridge handler for ``main_window.state``."""
    return build_view_model(params)
