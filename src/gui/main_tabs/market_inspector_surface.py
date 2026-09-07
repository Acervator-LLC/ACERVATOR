"""market_inspector_surface.py -- the Market Inspector screen, without Qt.

Describes the fleet-wide Market Inspector tab and the per-bot view the
Live Bot Settings window shows. The screen holds a Refresh button, an
"Include active markets" switch, a status line, an HTF Signals table of
six columns, an Opposing Pairs table of four, and a right pane carrying
the topology proposals. ``left_module_rows`` describes the three regions
above them: ATA-SPM, Opposing Trades and Multi-Exchange Arbitrage, each
carrying the state its own source answers with.
``build_per_bot_model`` describes the per-bot
screen: the bot's own asset card, the higher-scoring markets and the
opposing pairs that feature the asset.

The analyzer both screens read is process-wide, and the shipped screen
writes its scan results into it. ``MarketInspectorScreenModel`` reaches
that analyzer through the same accessor, resolved on the call rather
than at import, and takes an injected stand-in when one is given.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``market_inspector.state`` method, which is how the Electron
renderer reaches it. Every value below is written out here rather than
read from ``src.gui.market_inspector``, so a value changed on one side
alone is reported. Nothing here imports Qt.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("acervator.market_inspector_gui")

METHOD = "market_inspector.state"

LOGGER_NAME = "acervator.market_inspector_gui"

ACCESSIBLE_NAME = ""
STYLE_SHEET = ""
SKIN: dict = {}

REFRESH_LABEL = "Refresh"
REFRESH_TOOLTIP = (
    "Fetch HTF OHLCV from the connected exchange(s). "
    "Universe = top-volume */USD markets on those "
    "exchanges (active bot targets are always included). "
    "Runs on the app's async loop; typical time ~10-30 s "
    "depending on exchange rate limits."
)

SHOW_ACTIVE_LABEL = "Include active markets"
SHOW_ACTIVE_CHECKED = False
SHOW_ACTIVE_TOOLTIP = (
    "By default the Market Inspector focuses on markets "
    "you are NOT already trading. Check this to include "
    "your active bot targets in the table."
)

STATUS_INITIAL_TEXT = "No data yet — press Refresh."
STATUS_STYLE = "color: #aaa; font-size: 11px;"

SIGNALS_GROUP_TITLE = "HTF Signals"
SIGNAL_COLUMNS = ("Asset", "Signal", "Score", "Daily", "Weekly", "Active")
SIGNALS_MAX_HEIGHT_PX = 360

PAIRS_GROUP_TITLE = "Opposing Pairs (cointegration, Engle-Granger + Johansen, p<=0.05)"
PAIR_COLUMNS = (
    "Long side",
    "Short side",
    "Method",
    "Window",
    "Statistic",
    "Correlation",
    "Score (Long+Short)",
)
NO_METHOD_TEXT = "—"
PAIRS_MAX_HEIGHT_PX = 180

ATA_SPM_MODULE = "ata_spm"
OPPOSING_TRADES_MODULE = "opposing_trades"
ARBITRAGE_MODULE = "arbitrage"

ATA_SPM_GROUP_TITLE = "ATA-SPM"
OPPOSING_TRADES_GROUP_TITLE = "Opposing Trades"
ARBITRAGE_GROUP_TITLE = "Multi-Exchange Arbitrage"

ATA_SPM_UNWIRED_TEXT = "Phase source not wired."
ATA_SPM_NO_RUN_TEXT = "No run yet. Ready to Send holds 0."
ATA_SPM_RUN_FORMAT = "{phase}. Ready to Send holds {count}."
ATA_SPM_PHASE_KEY = "phase"
ATA_SPM_READY_KEY = "ready_to_send"

#: The share a bullish bot feeds to the bot on the opposite market condition.
OPPOSING_TRADES_PROFIT_SHARE_PCT = 50
OPPOSING_TRADES_NOUN = "opposing trades"
OPPOSING_TRADES_FOUND_FORMAT = (
    "{count} {noun}. {share}% of profit goes to the opposite side."
)

READY_TO_SEND_ZONE = "ready_to_send"
TOPOLOGIES_ZONE = "topologies"
PHANTOM_HTF_ZONE = "phantom_htf"

READY_TO_SEND_GROUP_TITLE = "ATA-SPM Ready to Send"
TOPOLOGIES_GROUP_TITLE = "Bot Swarm Topologies"
PHANTOM_HTF_GROUP_TITLE = "Phantom Bot HTF Signals"

PHANTOM_HTF_UNWIRED_TEXT = "Phantom Bot source not wired."

READY_TO_SEND_UNWIRED_TEXT = "Phase source not wired. Nothing to approve."
READY_TO_SEND_NO_RUN_TEXT = "No run yet. Nothing to approve."
READY_TO_SEND_HOLDS_FORMAT = "{count} post(s) waiting. Approve or decline each."

#: The Bot Swarm Topologies zone carries the proposal pane, not a status line.
NO_TEXT_LINE = ""

RIGHT_ZONE_KEYS = (READY_TO_SEND_ZONE, TOPOLOGIES_ZONE, PHANTOM_HTF_ZONE)
RIGHT_ZONE_TITLES = (
    READY_TO_SEND_GROUP_TITLE,
    TOPOLOGIES_GROUP_TITLE,
    PHANTOM_HTF_GROUP_TITLE,
)

ARBITRAGE_UNWIRED_TEXT = "Exchange source not wired."
ARBITRAGE_NO_VENUE_TEXT = "No exchange connected."
ARBITRAGE_ONE_VENUE_FORMAT = (
    "1 venue connected: {names}. A second venue is needed to compare."
)
ARBITRAGE_VENUES_FORMAT = "{count} venues connected: {names}."
VENUE_SEPARATOR = ", "
ONE_VENUE = 1

#: The frame a themed ``QGroupBox`` draws round one left module. Measured
#: 1 px on the running widget, whose ``contentsRect`` starts at x 1.
MODULE_FRAME_PX = 1

#: The margins the group layout keeps inside that frame, as left, top, right
#: and bottom. The top carries the band the title is drawn in, measured 41 px
#: from the widget edge, less the frame, plus the layout's own 9 px.
MODULE_MARGINS_PX = (9, 49, 9, 9)

#: The padding the theme gives ``QGroupBox::title``, as left, top, right and
#: bottom. The title is drawn in the group's own margin, so it takes no row.
MODULE_TITLE_PADDING_PX = (12, 4, 12, 4)

# The themed QPushButton, measured off the running Refresh button.
BUTTON_PADDING_PX = (20, 8, 20, 8)
BUTTON_FONT_WEIGHT = "bold"

LEFT_MODULE_KEYS = (ATA_SPM_MODULE, OPPOSING_TRADES_MODULE, ARBITRAGE_MODULE)
LEFT_MODULE_TITLES = (
    ATA_SPM_GROUP_TITLE,
    OPPOSING_TRADES_GROUP_TITLE,
    ARBITRAGE_GROUP_TITLE,
)

#: The height a ``QTableWidget`` takes when nothing sizes it. Measured 192 px,
#: and the same whatever the row count, so each table draws this tall until
#: its own maximum cuts it shorter.
TABLE_VIEWPORT_PX = 192

TABLE_RESIZE_MODE = "ResizeToContents"
TABLE_EDIT_TRIGGERS = "NoEditTriggers"
TABLE_ALTERNATING_ROWS = True

SPLITTER_ORIENTATION = "Horizontal"
SPLITTER_STRETCH = (1, 1)
SPLITTER_SIZES_PX = (800, 800)
SPLITTER_PANES = 2

#: The drag handle a ``QSplitter`` keeps between the two panes. Measured 7 px
#: under the shipped theme, which is the width the splitter reports, so the
#: panes share what is left rather than the whole tab.
SPLITTER_HANDLE_PX = 7

OUTER_MARGINS_PX = (0, 0, 0, 0)
OUTER_SPACING_PX = 0
LEFT_MARGINS_PX = (6, 6, 6, 6)
LEFT_SPACING_PX = 6
TOP_ROW_SPACING_PX = 8
PER_BOT_SPACING_PX = 8

TOP_ROW_MARGINS_PX = (0, 0, 0, 0)
PER_BOT_MARGINS_PX = (11, 11, 11, 11)
GROUP_MARGINS_PX = (11, 11, 11, 11)
GROUP_SPACING_PX = 6

SIGNAL_ENTRY_LONG_HIGH = "ENTRY_LONG_HIGH"
SIGNAL_ENTRY_LONG = "ENTRY_LONG"
SIGNAL_ENTRY_SHORT_HIGH = "ENTRY_SHORT_HIGH"
SIGNAL_ENTRY_SHORT = "ENTRY_SHORT"
SIGNAL_WATCHLIST = "WATCHLIST"

COLOR_ENTRY_LONG_HIGH = "#00ff88"
COLOR_ENTRY_LONG = "#66cc99"
COLOR_ENTRY_SHORT_HIGH = "#ff3366"
COLOR_ENTRY_SHORT = "#ff9966"
COLOR_WATCHLIST = "#ffcc00"
COLOR_OTHER = "#888"
COLOR_ACTIVE = "#00ccff"
COLOR_CORRELATION = "#ffcc66"
COLOR_METHOD = "#00cccc"
NO_COLOR = ""
NO_CELL = None

TAG_UPPER = "▲"
TAG_LOWER = "▼"
TAG_MIDDLE = "·"
TIGHT_SUFFIX = " T"
NO_TIGHT_SUFFIX = ""
EMPTY_TIMEFRAME = "—"
TIMEFRAME_FORMAT = "{tag} bb={bb_position:.2f} z={z_score:+.2f}{tight}"

ACTIVE_YES = "yes"
ACTIVE_NO = "—"
SCORE_FORMAT = "{score:.2f}"
CORRELATION_FORMAT = "{correlation:+.3f}"
PAIR_SIDE_FORMAT = "{symbol} ({signal})"
PAIR_SCORE_FORMAT = "{score:.2f}"

MINUTE_S = 60
HOUR_S = 3600
DAY_S = 86400
NO_AGE_S = 0.0
AGE_SECONDS_FORMAT = "{count}s"
AGE_MINUTES_FORMAT = "{count} min"
AGE_HOURS_FORMAT = "{hours}h"
AGE_HOURS_MINUTES_FORMAT = "{hours}h {minutes}m"
AGE_DAYS_FORMAT = "{count} days"

SOURCE_COINGECKO = "coingecko"
SOURCE_CACHE = "cache"
SOURCE_ERROR = "error"
SOURCE_NETWORK_PARTIAL = "network-partial"
SOURCE_UNKNOWN = "?"

STATUS_LIVE_FORMAT = "Live CoinGecko  ·  {count} markets  ·  just now"
STATUS_CACHE_FORMAT = "Snapshot {age} old  ·  {count} markets"
STATUS_CACHE_FALLBACK_FORMAT = "  ·  fallback: {error}"
STATUS_ERROR_FORMAT = "Fetch failed: {error}"
STATUS_PARTIAL_FORMAT = "Network partial: {error}"
UNKNOWN_ERROR_TEXT = "unknown"
NO_CANDLES_TEXT = "no OHLC"

NOT_WIRED_TEXT = (
    "Exchange source not wired — restart the app " "after connecting an exchange."
)
NO_CONNECTORS_TEXT = (
    "No exchange connectors — connect an exchange " "on the Trading tab first."
)
FETCHING_TEXT = "Fetching…"
SCHEDULER_ERROR_FORMAT = "Scheduler error: {error}"
ANALYZER_ERROR_FORMAT = "Analyzer error: {error}"
ANALYZER_UNAVAILABLE_TEXT = "Analyzer unavailable."

FETCH_FAILED_LOG = "market inspector fetch failed: %s"
SCAN_FAILED_LOG = "market inspector scan failed: %s"
PROPOSALS_FAILED_LOG = "topology proposal read failed: %s"
TOPOLOGIES_MISSING_LOG = "topologies pane unavailable: %s"
ATA_RUN_FAILED_LOG = "ATA-SPM run read failed: %s"
CONNECTORS_READ_FAILED_LOG = "exchange connector read failed: %s"

SCAN_NOT_ASKED = "not_asked"
SCAN_RUNNING = "running"
SCAN_FINISHED = "finished"
SCAN_PHASES = (SCAN_NOT_ASKED, SCAN_RUNNING, SCAN_FINISHED)

SCAN_STARTED_TOPIC = "market_inspector.scan_started"
SCAN_FINISHED_TOPIC = "market_inspector.scan_finished"

SIGNALS_NOUN = "markets"
PAIRS_NOUN = "opposing pairs"

SCANNING_FORMAT = "Scanning for {noun}…"
SCAN_EMPTY_FORMAT = "Scan finished. No {noun} found."
NO_SCAN_FORMAT = "No scan yet. Press Refresh to look for {noun}."

UNKNOWN_SOURCE = "?"
NO_DURATION_S = 0.0
SCAN_STARTED_LOG = (
    "market inspector scan started: forced=%s connectors=%d active_symbols=%d"
)
SCAN_FINISHED_LOG = (
    "market inspector scan finished: %d market(s), %d signal(s), "
    "%d pair(s) in %.2fs source=%s%s"
)
SCAN_ERROR_SUFFIX = " error={error}"
COUNT_READ_FAILED_LOG = "market inspector count read failed: %s"

ERROR_META_SOURCE = SOURCE_ERROR
ERROR_META_AGE_S = 0.0
ERROR_META_COUNT = 0

PER_BOT_UNAVAILABLE_TEXT = "Market Inspector analyzer unavailable."

STRONG_OPEN = "<b>"
STRONG_CLOSE = "</b>"
BREAK_TAG = "<br>"
STRONG_WEIGHT = "bold"
NO_BREAKS = 0
NO_PIECE = ""

NO_SCAN_HEADLINE = "No Market Inspector scan yet."
NO_SCAN_BREAKS = 2
NO_SCAN_BODY = (
    "Open the Market Inspector top-level tab and press "
    "Refresh to populate. The scan runs across the top-50 "
    "CoinGecko markets on daily and weekly candles; results "
    "are shared between the top-level tab and this per-bot "
    "view."
)


def marked_text(lead: str, strong: str, breaks: int, tail: str) -> str:
    """One label's text with its emphasis and line breaks as Qt markup."""
    return lead + STRONG_OPEN + strong + STRONG_CLOSE + BREAK_TAG * breaks + tail


NO_SCAN_TEXT = marked_text(NO_PIECE, NO_SCAN_HEADLINE, NO_SCAN_BREAKS, NO_SCAN_BODY)
NO_SCAN_STYLE = "color: #aaa; padding: 12px;"
NO_SCAN_WORD_WRAP = True

OWN_CARD_TITLE_FORMAT = "This Bot's Asset — {asset}"
UNKNOWN_ASSET_MARK = "?"
THIS_ASSET_TEXT = "this asset"
NO_SIGNAL_FORMAT = (
    "No signal for {asset} in the current "
    "scan. The universe covers CoinGecko top-50; markets "
    "outside that set are not tracked."
)
SIGNAL_LINE_LEAD = "Signal: "
SIGNAL_LINE_MARK = "{signal}"
SIGNAL_LINE_TAIL_FORMAT = "  |  Score: {score:.2f}  |  Direction: {direction}"
SIGNAL_LINE_FORMAT = marked_text(
    SIGNAL_LINE_LEAD, SIGNAL_LINE_MARK, NO_BREAKS, SIGNAL_LINE_TAIL_FORMAT
)
SIGNAL_LINE_STYLE_FORMAT = "color: {color}; font-size: 13px;"
NO_DIRECTION_MARK = "—"
TIMEFRAME_KEYS = ("1d", "1w")
TIMEFRAME_LINE_FORMAT = "{key}: {reading}"

HIGHER_GROUP_TITLE = "Higher-Scoring Markets (top-5)"
HIGHER_LIMIT = 5
NO_SCORE = 0.0
HIGHER_ROW_FORMAT = "{symbol}  ·  {signal}  ·  score {score:.2f}"
HIGHER_ROW_ACTIVE_SUFFIX = "  ·  ACTIVE"
HIGHER_ROW_QUIET_SUFFIX = ""
HIGHER_ROW_STYLE_FORMAT = "color: {color}; font-family: monospace;"

PER_BOT_PAIRS_GROUP_TITLE = "Opposing Pairs Featuring This Asset"
PER_BOT_PAIR_FORMAT = (
    "{long_symbol} (long) ⇄ " "{short_symbol} (short)  ·  " "corr {correlation:+.3f}"
)

NO_STYLE = ""
NO_WORD_WRAP = False
LABEL_ELEMENT = "label"
GROUP_ELEMENT = "group"
STRETCH_ELEMENT = "stretch"

SYMBOL_SEPARATOR = "/"
NO_SYMBOL = ""
NO_ASSET = ""

TIMERS: dict = {}
TIMER_DELAYS_MS: tuple = ()
BUS_TOPICS: tuple = ()

ACTIONS = {
    "refresh_clicked": "start_fetch",
    "show_active_toggled": "on_toggle_show_active",
    "adopt_requested": "set_adopt_handler",
}

SCREEN_BUILT = "screen.built"
ACTIVE_SYMBOLS_SET = "active.set"
STATUS_WRITTEN = "status.written"
ANALYZER_UNREACHABLE = "analyzer.unreachable"
SIGNALS_DRAWN = "signals.drawn"
PAIRS_DRAWN = "pairs.drawn"
FETCH_BLOCKED = "fetch.blocked"
FETCH_UNWIRED = "fetch.unwired"
FETCH_NO_CONNECTORS = "fetch.no_connectors"
FETCH_SCHEDULED = "fetch.scheduled"
FETCH_SCHEDULER_FAILED = "fetch.scheduler_failed"
FETCH_FAILED = "fetch.failed"
FETCH_ANSWERED = "fetch.answered"
SCAN_FAILED = "scan.failed"
SCAN_DONE = "scan.done"
SCAN_STARTED = "scan.started"
SCAN_RECORDED = "scan.recorded"
PROGRESS_WRITTEN = "progress.written"
SHOW_ACTIVE_TOGGLED = "show_active.toggled"
STORE_HANDED = "store.handed"
STORE_UNREACHABLE = "store.unreachable"
SOURCE_HANDED = "source.handed"
SOURCE_UNREACHABLE = "source.unreachable"
ADOPT_WIRED = "adopt.wired"
ADOPT_UNREACHABLE = "adopt.unreachable"
PROPOSALS_READ = "proposals.read"
PROPOSALS_UNREADABLE = "proposals.unreadable"
EXCHANGE_SOURCE_SET = "exchange.set"
ATA_SOURCE_SET = "ata_run.set"

CALL_NAMES = (
    SCREEN_BUILT,
    ACTIVE_SYMBOLS_SET,
    STATUS_WRITTEN,
    ANALYZER_UNREACHABLE,
    SIGNALS_DRAWN,
    PAIRS_DRAWN,
    FETCH_BLOCKED,
    FETCH_UNWIRED,
    FETCH_NO_CONNECTORS,
    FETCH_SCHEDULED,
    FETCH_SCHEDULER_FAILED,
    FETCH_FAILED,
    FETCH_ANSWERED,
    SCAN_FAILED,
    SCAN_DONE,
    SCAN_STARTED,
    SCAN_RECORDED,
    PROGRESS_WRITTEN,
    SHOW_ACTIVE_TOGGLED,
    STORE_HANDED,
    STORE_UNREACHABLE,
    SOURCE_HANDED,
    SOURCE_UNREACHABLE,
    ADOPT_WIRED,
    ADOPT_UNREACHABLE,
    PROPOSALS_READ,
    PROPOSALS_UNREADABLE,
    EXCHANGE_SOURCE_SET,
    ATA_SOURCE_SET,
)


def age_text(seconds: Any) -> str:
    """How old a snapshot is, in the words the status line uses."""
    span = max(NO_AGE_S, float(seconds))
    if span < MINUTE_S:
        return AGE_SECONDS_FORMAT.format(count=int(span))
    if span < HOUR_S:
        return AGE_MINUTES_FORMAT.format(count=int(span / MINUTE_S))
    if span < DAY_S:
        hours = int(span / HOUR_S)
        minutes = int((span % HOUR_S) / MINUTE_S)
        if minutes:
            return AGE_HOURS_MINUTES_FORMAT.format(hours=hours, minutes=minutes)
        return AGE_HOURS_FORMAT.format(hours=hours)
    return AGE_DAYS_FORMAT.format(count=int(span / DAY_S))


def signal_color(signal: Any) -> str:
    """The colour one signal name is drawn in."""
    if signal.startswith(SIGNAL_ENTRY_LONG_HIGH):
        return COLOR_ENTRY_LONG_HIGH
    if signal.startswith(SIGNAL_ENTRY_LONG):
        return COLOR_ENTRY_LONG
    if signal.startswith(SIGNAL_ENTRY_SHORT_HIGH):
        return COLOR_ENTRY_SHORT_HIGH
    if signal.startswith(SIGNAL_ENTRY_SHORT):
        return COLOR_ENTRY_SHORT
    if signal == SIGNAL_WATCHLIST:
        return COLOR_WATCHLIST
    return COLOR_OTHER


def timeframe_text(reading: Any) -> str:
    """One timeframe cell: the extreme mark, the band position and the z."""
    if reading is None:
        return EMPTY_TIMEFRAME
    if reading.at_upper_extreme:
        tag = TAG_UPPER
    elif reading.at_lower_extreme:
        tag = TAG_LOWER
    else:
        tag = TAG_MIDDLE
    tight = TIGHT_SUFFIX if reading.tightening else NO_TIGHT_SUFFIX
    return TIMEFRAME_FORMAT.format(
        tag=tag,
        bb_position=reading.bb_position,
        z_score=reading.z_score,
        tight=tight,
    )


def status_text(meta: Any) -> str:
    """The status line for one fetch report."""
    found = meta or {}
    source = found.get("source", SOURCE_UNKNOWN)
    age = float(found.get("age_seconds", NO_AGE_S) or NO_AGE_S)
    count = int(found.get("symbol_count", 0) or 0)
    error = found.get("error")
    if source == SOURCE_COINGECKO:
        return STATUS_LIVE_FORMAT.format(count=count)
    if source == SOURCE_CACHE:
        line = STATUS_CACHE_FORMAT.format(age=age_text(age), count=count)
        if error:
            line += STATUS_CACHE_FALLBACK_FORMAT.format(error=error)
        return line
    if source == SOURCE_ERROR:
        return STATUS_ERROR_FORMAT.format(error=error or UNKNOWN_ERROR_TEXT)
    if source == SOURCE_NETWORK_PARTIAL:
        return STATUS_PARTIAL_FORMAT.format(error=error or NO_CANDLES_TEXT)
    return STATUS_INITIAL_TEXT


def active_symbols_from(bot_statuses: Any) -> set:
    """The base assets the running fleet already trades."""
    found: set = set()
    for status in bot_statuses or []:
        symbol = status.get("symbol", NO_SYMBOL)
        if SYMBOL_SEPARATOR in symbol:
            found.add(symbol.split(SYMBOL_SEPARATOR)[0].upper())
        elif symbol:
            found.add(symbol.upper())
    return found


def asset_of(bot: Any) -> str:
    """One bot's base asset, or nothing when the symbol cannot be read."""
    try:
        symbol = getattr(bot.config, "symbol", NO_SYMBOL)
        if SYMBOL_SEPARATOR in symbol:
            return symbol.split(SYMBOL_SEPARATOR)[0].upper()
        return symbol.upper()
    except Exception:
        return NO_ASSET


def set_row_count(rows: list, count: int, columns: int) -> list:
    """Grow `rows` with blank rows, or drop the rows past `count`.

    A row that survives keeps the cells it already holds, which is what
    a table does when it is told how many rows it now has.
    """
    while len(rows) > count:
        rows.pop()
    while len(rows) < count:
        rows.append([[NO_CELL, NO_CELL] for _ in range(columns)])
    return rows


def fill_signal_row(cells: list, found: Any) -> None:
    """Write the six HTF Signals cells of one row, left to right.

    Each cell is written on its own, so a reading that cannot be worded
    stops the row where the shipped table stops and leaves the cells to
    its right holding whatever the previous draw put there.
    """
    cells[0] = [found.symbol, NO_COLOR]
    cells[1] = [found.signal, signal_color(found.signal)]
    cells[2] = [SCORE_FORMAT.format(score=found.score), NO_COLOR]
    cells[3] = [timeframe_text(found.per_tf.get(TIMEFRAME_KEYS[0])), NO_COLOR]
    cells[4] = [timeframe_text(found.per_tf.get(TIMEFRAME_KEYS[1])), NO_COLOR]
    cells[5] = [ACTIVE_YES, COLOR_ACTIVE] if found.is_active else [ACTIVE_NO, NO_COLOR]


def fill_pair_row(cells: list, pair: Any) -> None:
    """Write the seven Opposing Pairs cells of one row, left to right."""
    method = getattr(pair, "method", None)
    cells[0] = [
        PAIR_SIDE_FORMAT.format(
            symbol=pair.long_side.symbol, signal=pair.long_side.signal
        ),
        NO_COLOR,
    ]
    cells[1] = [
        PAIR_SIDE_FORMAT.format(
            symbol=pair.short_side.symbol, signal=pair.short_side.signal
        ),
        NO_COLOR,
    ]
    cells[2] = [method.label if method else NO_METHOD_TEXT, COLOR_METHOD]
    cells[3] = [method.window_text if method else NO_METHOD_TEXT, NO_COLOR]
    cells[4] = [method.statistic_text if method else NO_METHOD_TEXT, NO_COLOR]
    cells[5] = [
        CORRELATION_FORMAT.format(correlation=pair.correlation_30d),
        COLOR_CORRELATION,
    ]
    cells[6] = [
        PAIR_SCORE_FORMAT.format(score=pair.long_side.score + pair.short_side.score),
        NO_COLOR,
    ]


def empty_table_text(scan_state: Any, noun: Any) -> str:
    """The sentence an empty table carries for one scan state.

    ``SCAN_NOT_ASKED``, ``SCAN_RUNNING`` and ``SCAN_FINISHED`` each get
    their own wording, so the three never read alike.
    """
    if scan_state == SCAN_RUNNING:
        return SCANNING_FORMAT.format(noun=noun)
    if scan_state == SCAN_FINISHED:
        return SCAN_EMPTY_FORMAT.format(noun=noun)
    return NO_SCAN_FORMAT.format(noun=noun)


def ata_spm_text(run: Any) -> str:
    """The ATA-SPM region's line for what the phase source reports.

    ``None`` says no source is wired, an empty report says no run has
    been made, and a report carrying a phase names it beside the count
    the Ready to Send bucket holds.
    """
    if run is None:
        return ATA_SPM_UNWIRED_TEXT
    phase = str(run.get(ATA_SPM_PHASE_KEY) or "")
    if not phase:
        return ATA_SPM_NO_RUN_TEXT
    return ATA_SPM_RUN_FORMAT.format(
        phase=phase, count=int(run.get(ATA_SPM_READY_KEY) or 0)
    )


def opposing_trades_text(scan_state: Any, count: Any) -> str:
    """The Opposing Trades region's line for one scan state and pair count.

    An unasked, a running and a finished scan each get their own
    wording, and a finished scan holding pairs names the profit share
    the bullish side feeds to the opposite one.
    """
    found = int(count or 0)
    if scan_state != SCAN_FINISHED or not found:
        return empty_table_text(scan_state, OPPOSING_TRADES_NOUN)
    return OPPOSING_TRADES_FOUND_FORMAT.format(
        count=found,
        noun=OPPOSING_TRADES_NOUN,
        share=OPPOSING_TRADES_PROFIT_SHARE_PCT,
    )


def arbitrage_text(connectors: Any) -> str:
    """The Multi-Exchange Arbitrage region's line for the venues in reach.

    ``None`` says no exchange source is wired, which no caller can
    confuse with a wired source carrying no connector. One venue names
    itself and says a second is needed to compare.
    """
    if connectors is None:
        return ARBITRAGE_UNWIRED_TEXT
    names = sorted(str(one) for one in connectors)
    if not names:
        return ARBITRAGE_NO_VENUE_TEXT
    joined = VENUE_SEPARATOR.join(names)
    if len(names) == ONE_VENUE:
        return ARBITRAGE_ONE_VENUE_FORMAT.format(names=joined)
    return ARBITRAGE_VENUES_FORMAT.format(count=len(names), names=joined)


def ready_to_send_text(run: Any) -> str:
    """The Ready to Send zone's line for what the phase source reports.

    None says no phase source is wired, which no caller can confuse
    with a wired source whose bucket is empty.
    """
    if run is None:
        return READY_TO_SEND_UNWIRED_TEXT
    count = run.get(ATA_SPM_READY_KEY)
    if count is None:
        return READY_TO_SEND_NO_RUN_TEXT
    return READY_TO_SEND_HOLDS_FORMAT.format(count=count)


def right_zone_rows(run: Any) -> list:
    """The three right-side zones as key, title and status, in screen order."""
    return [
        [READY_TO_SEND_ZONE, READY_TO_SEND_GROUP_TITLE, ready_to_send_text(run)],
        [TOPOLOGIES_ZONE, TOPOLOGIES_GROUP_TITLE, NO_TEXT_LINE],
        [PHANTOM_HTF_ZONE, PHANTOM_HTF_GROUP_TITLE, PHANTOM_HTF_UNWIRED_TEXT],
    ]


def left_module_rows(
    run: Any, scan_state: Any, pair_count: Any, connectors: Any
) -> list:
    """The three left-side regions as key, title and status, in screen order."""
    return [
        [ATA_SPM_MODULE, ATA_SPM_GROUP_TITLE, ata_spm_text(run)],
        [
            OPPOSING_TRADES_MODULE,
            OPPOSING_TRADES_GROUP_TITLE,
            opposing_trades_text(scan_state, pair_count),
        ],
        [ARBITRAGE_MODULE, ARBITRAGE_GROUP_TITLE, arbitrage_text(connectors)],
    ]


def shown_signals(signals: Any, show_active: bool) -> list:
    """The signals the table draws: scored, and active ones only on request."""
    found = list(signals)
    if not show_active:
        found = [one for one in found if not one.is_active]
    return [one for one in found if one.score > NO_SCORE]


class TimeframeState:
    """One timeframe reading, as the table cell reads it."""

    def __init__(
        self,
        bb_position: float = 0.5,
        z_score: float = 0.0,
        tightening: bool = False,
        at_upper_extreme: bool = False,
        at_lower_extreme: bool = False,
    ) -> None:
        self.bb_position = bb_position
        self.z_score = z_score
        self.tightening = tightening
        self.at_upper_extreme = at_upper_extreme
        self.at_lower_extreme = at_lower_extreme


class SignalState:
    """One market signal, as both screens read it."""

    def __init__(
        self,
        symbol: str = NO_SYMBOL,
        signal: str = NO_SYMBOL,
        score: float = NO_SCORE,
        direction: str = NO_SYMBOL,
        per_tf: Optional[dict] = None,
        is_active: bool = False,
    ) -> None:
        self.symbol = symbol
        self.signal = signal
        self.score = score
        self.direction = direction
        self.per_tf = {} if per_tf is None else per_tf
        self.is_active = is_active


class PairState:
    """One opposing pair, as both screens read it.

    method is the cointegration_test verdict that let the pair
    through, and the table prints its label, window and statistic.
    """

    def __init__(
        self,
        long_side: Any,
        short_side: Any,
        correlation_30d: float,
        method: Any = None,
    ) -> None:
        self.long_side = long_side
        self.short_side = short_side
        self.correlation_30d = correlation_30d
        self.method = method


class InspectorSource:
    """The process-wide analyzer, as a stand-in the screen is driven with.

    ``raises`` is what the analyzer throws instead of accepting a scan,
    which is how the screen's scan-failure path is driven.
    """

    def __init__(
        self,
        signals: Optional[list] = None,
        pairs: Optional[list] = None,
        raises: Optional[BaseException] = None,
    ) -> None:
        self.last_signals = [] if signals is None else list(signals)
        self.last_pairs = [] if pairs is None else list(pairs)
        self.raises = raises
        self.scans: list = []

    def scan_universe(
        self,
        candles_by_symbol_by_tf: Any,
        active_symbols: Any,
        closes_by_symbol: Any,
    ) -> None:
        """Take one scan, or refuse it the way the analyzer refuses."""
        self.scans.append(
            [
                candles_by_symbol_by_tf,
                sorted(active_symbols or []),
                closes_by_symbol,
            ]
        )
        if self.raises is not None:
            raise self.raises

    def get_signal(self, symbol: Any) -> Any:
        """The signal for one asset, or nothing when the scan missed it."""
        for found in self.last_signals:
            if found.symbol == symbol:
                return found
        return None


class TopologyPaneModel:
    """The right pane, as far as the Market Inspector screen reaches it."""

    def __init__(self, proposals: Optional[list] = None) -> None:
        self.proposals = [] if proposals is None else list(proposals)
        self.dismiss_store: Any = None
        self.proposal_source: Any = None
        self.adopt_handlers: list = []

    def set_dismiss_store(self, store: Any) -> None:
        """Take the place the pane persists its dismissals in."""
        self.dismiss_store = store

    def set_proposal_source(self, getter: Any) -> None:
        """Take the callable the pane pulls its proposals from."""
        self.proposal_source = getter

    def current_proposals(self) -> list:
        """The proposals the pane is showing."""
        return list(self.proposals)

    @property
    def adoptRequested(self) -> Any:
        """The Adopt signal the screen wires the main window onto."""
        return self

    def connect(self, handler: Any) -> None:
        """Wire one handler onto the Adopt signal."""
        self.adopt_handlers.append(handler)


class MarketInspectorScreenModel:
    """The Market Inspector screen: its filter row, its two tables, its pane.

    ``start_fetch`` refuses in the places the shipped screen refuses and
    hands the fetch to the scheduler otherwise. ``fetch_and_analyze``
    writes the fetch report, feeds the analyzer and redraws.
    ``render_signals`` fills both tables from the analyzer's most recent
    scan. Every step is appended to ``calls`` in the order the shipped
    screen makes it.
    """

    ADOPT_SIGNAL_NAME = "adoptRequested"

    def __init__(
        self,
        inspector_source: Any = None,
        fetcher: Any = None,
        topologies_pane: Any = None,
    ) -> None:
        self.inspector_source = inspector_source
        self.fetcher = fetcher
        self.topologies_pane = topologies_pane
        self.accessible_name = ACCESSIBLE_NAME
        self.style_sheet = STYLE_SHEET
        self.active_symbols: set = set()
        self.show_active = SHOW_ACTIVE_CHECKED
        self.show_active_checked = SHOW_ACTIVE_CHECKED
        self.last_meta: dict = {}
        self.pending_refresh = False
        self.scan_phase = SCAN_NOT_ASKED
        self.connectors_getter: Any = None
        self.scheduler: Any = None
        self.ata_run_source: Any = None
        self.refresh_enabled = True
        self.status_label_text = STATUS_INITIAL_TEXT
        self.signal_rows: list = []
        self.pair_rows: list = []
        self.scheduled: list = []
        self.emitted: list = []
        self.calls: list = []
        self.build_ui()

    def build_ui(self) -> None:
        """Build the filter row, the status line and the two empty tables."""
        self.refresh_enabled = True
        self.show_active_checked = SHOW_ACTIVE_CHECKED
        self.status_label_text = STATUS_INITIAL_TEXT
        self.signal_rows = []
        self.pair_rows = []
        self.calls.append([SCREEN_BUILT])

    def set_status(self, text: str) -> None:
        """Show ``text`` on the status line."""
        self.status_label_text = text

    def set_refresh_enabled(self, enabled: bool) -> None:
        """Let the operator press Refresh, or refuse while a scan runs."""
        self.refresh_enabled = bool(enabled)

    def shown_signals(self, signals: Any) -> list:
        """The scored signals the table shows under the active filter."""
        return shown_signals(signals, self.show_active)

    def fill_signal_rows(self, signals: list) -> None:
        """Draw one HTF Signals row per entry of ``signals``."""
        set_row_count(self.signal_rows, len(signals), len(SIGNAL_COLUMNS))
        for index, found in enumerate(signals):
            fill_signal_row(self.signal_rows[index], found)
        self.calls.append([SIGNALS_DRAWN, len(self.signal_rows)])

    def fill_pair_rows(self, pairs: Any) -> None:
        """Draw one Opposing Pairs row per entry of ``pairs``."""
        rows = list(pairs)
        set_row_count(self.pair_rows, len(rows), len(PAIR_COLUMNS))
        for index, found in enumerate(rows):
            fill_pair_row(self.pair_rows[index], found)
        self.calls.append([PAIRS_DRAWN, len(self.pair_rows)])

    def inspector(self) -> Any:
        """The analyzer this screen reads, injected or process-wide.

        Resolved on the call, never at import: the process-wide analyzer
        is built by the accessor the first time anything asks for it.
        """
        if self.inspector_source is not None:
            return self.inspector_source
        from ...trading.market_inspector import get_shared_inspector

        return get_shared_inspector()

    def scan_state(self) -> str:
        """Whether a scan is unasked, running, or finished.

        One of ``SCAN_NOT_ASKED``, ``SCAN_RUNNING`` or ``SCAN_FINISHED``,
        which is what tells an empty table apart from one waiting on a
        scan nobody started.
        """
        return self.scan_phase

    def empty_notes(self) -> dict:
        """The sentence each table shows while it holds no rows."""
        return {
            "signals": empty_table_text(self.scan_phase, SIGNALS_NOUN),
            "pairs": empty_table_text(self.scan_phase, PAIRS_NOUN),
        }

    def set_ata_run_source(self, getter: Any) -> None:
        """Take the callable the ATA-SPM region reads its run report from."""
        self.ata_run_source = getter
        self.calls.append([ATA_SOURCE_SET])

    def ata_run(self) -> Any:
        """The ATA-SPM run report, or None while no source answers.

        A source that raises reads as no source, so the region says it
        is unwired rather than showing a run nobody can read back.
        """
        getter = self.ata_run_source
        if getter is None:
            return None
        try:
            return dict(getter() or {})
        except Exception as exc:  # noqa: BLE001 - optional producer
            logger.debug(ATA_RUN_FAILED_LOG, exc)
            return None

    def connectors_now(self) -> Any:
        """The exchange connectors in reach, or None while none is wired.

        An unwired source and a wired source holding no connector are
        two answers, which is what lets the arbitrage region name which
        of them it is waiting on.
        """
        if not (self.connectors_getter and self.scheduler):
            return None
        try:
            return dict(self.connectors_getter() or {})
        except Exception as exc:  # noqa: BLE001 - optional producer
            logger.debug(CONNECTORS_READ_FAILED_LOG, exc)
            return None

    def left_modules(self) -> list:
        """The three left-side regions, each with the state it can read."""
        return left_module_rows(
            self.ata_run(),
            self.scan_phase,
            len(self.pair_rows),
            self.connectors_now(),
        )

    def right_zones(self) -> list:
        """The three right-side zones, in the order the screen draws them."""
        return right_zone_rows(self.ata_run())

    def fetch_universe(self) -> Any:
        """The fetch the Refresh button runs, injected or the shipped one."""
        if self.fetcher is not None:
            return self.fetcher
        from ...exchange.market_inspector_fetcher import fetch_htf_universe

        return fetch_htf_universe

    def update_active_symbols(self, bot_statuses: Any) -> None:
        """Take the base assets the fleet trades and redraw both tables."""
        self.active_symbols = active_symbols_from(bot_statuses)
        self.calls.append([ACTIVE_SYMBOLS_SET, len(self.active_symbols)])
        self.render_signals()

    def set_dismiss_store(self, store: Any) -> None:
        """Give the right pane somewhere to persist its dismissals."""
        pane = self.topologies_pane
        if pane is not None and hasattr(pane, "set_dismiss_store"):
            pane.set_dismiss_store(store)
            self.calls.append([STORE_HANDED])
            return
        self.calls.append([STORE_UNREACHABLE])

    def set_proposal_source(self, getter: Any) -> None:
        """Wire the topology-proposal source into the right pane."""
        pane = self.topologies_pane
        if pane is None:
            self.calls.append([SOURCE_UNREACHABLE])
            return
        if hasattr(pane, "set_proposal_source"):
            pane.set_proposal_source(getter)
            self.calls.append([SOURCE_HANDED])
            return
        self.calls.append([SOURCE_UNREACHABLE])

    def set_adopt_handler(self, handler: Any) -> None:
        """Wire the Adopt handoff from the right pane to the main window."""
        pane = self.topologies_pane
        if pane is None:
            self.calls.append([ADOPT_UNREACHABLE])
            return
        adopt_signal = getattr(pane, self.ADOPT_SIGNAL_NAME, None)
        if adopt_signal is None:
            self.calls.append([ADOPT_UNREACHABLE])
            return
        adopt_signal.connect(handler)
        self.calls.append([ADOPT_WIRED])

    def current_topology_proposals(self) -> Optional[list]:
        """The proposals on display, for a simulator to read.

        ``None`` says the right pane never built or refused the read, and
        a list says the pane answered, so an empty pane and an absent one
        never look alike to a caller.
        """
        pane = self.topologies_pane
        getter = getattr(pane, "current_proposals", None)
        if getter is None:
            self.calls.append([PROPOSALS_UNREADABLE])
            return None
        try:
            found = list(getter() or [])
        except Exception as exc:
            logger.debug(PROPOSALS_FAILED_LOG, exc)
            self.calls.append([PROPOSALS_UNREADABLE])
            return None
        self.calls.append([PROPOSALS_READ, len(found)])
        return found

    def set_exchange_source(self, connectors_getter: Any, scheduler: Any) -> None:
        """Wire the exchange data path the Refresh button runs on."""
        self.connectors_getter = connectors_getter
        self.scheduler = scheduler
        self.calls.append([EXCHANGE_SOURCE_SET])

    def start_fetch(self, force: bool = False) -> None:
        """Press Refresh: check the wiring, then hand the fetch to the loop."""
        if self.pending_refresh:
            self.calls.append([FETCH_BLOCKED])
            return
        if not (self.connectors_getter and self.scheduler):
            self.set_status(NOT_WIRED_TEXT)
            self.calls.append([FETCH_UNWIRED])
            return
        connectors = self.connectors_getter() or {}
        if not connectors:
            self.set_status(NO_CONNECTORS_TEXT)
            self.calls.append([FETCH_NO_CONNECTORS])
            return
        self.pending_refresh = True
        self.scan_phase = SCAN_RUNNING
        self.set_refresh_enabled(False)
        self.set_status(FETCHING_TEXT)
        logger.info(
            SCAN_STARTED_LOG,
            bool(force),
            len(connectors),
            len(self.active_symbols),
        )
        self.emitted.append(
            [
                SCAN_STARTED_TOPIC,
                {
                    "forced": bool(force),
                    "connector_count": len(connectors),
                    "active_symbols": len(self.active_symbols),
                },
            ]
        )
        self.calls.append([SCAN_STARTED, bool(force)])
        try:
            self.scheduler(self.fetch_call(connectors, force))
        except Exception as exc:
            self.pending_refresh = False
            self.scan_phase = SCAN_FINISHED
            self.set_refresh_enabled(True)
            self.set_status(SCHEDULER_ERROR_FORMAT.format(error=exc))
            self.calls.append([FETCH_SCHEDULER_FAILED, type(exc).__name__])
            return
        self.calls.append([FETCH_SCHEDULED, bool(force)])

    def fetch_call(self, connectors: dict, force: bool) -> list:
        """What the screen hands the scheduler."""
        found = [connectors, bool(force)]
        self.scheduled.append(found)
        return found

    async def fetch_and_analyze(self, connectors: dict, force: bool = False) -> None:
        """Fetch the universe, feed the analyzer and redraw both tables."""
        try:
            result = await self.fetch_universe()(
                connectors,
                active_symbols=self.active_symbols,
                progress_cb=self.on_progress,
                force_network=force,
            )
        except Exception as exc:
            logger.exception(FETCH_FAILED_LOG, exc)
            self.last_meta = {
                "source": ERROR_META_SOURCE,
                "age_seconds": ERROR_META_AGE_S,
                "error": str(exc),
                "symbol_count": ERROR_META_COUNT,
            }
            self.pending_refresh = False
            self.scan_phase = SCAN_FINISHED
            self.set_refresh_enabled(True)
            self.calls.append([FETCH_FAILED, type(exc).__name__])
            self.finish_scan_record(NO_DURATION_S, error=str(exc))
            self.render_signals()
            return
        self.last_meta = dict(result.meta or {})
        self.calls.append([FETCH_ANSWERED])
        try:
            self.inspector().scan_universe(
                result.candles_by_symbol_by_tf,
                self.active_symbols,
                result.closes_by_symbol,
            )
            self.calls.append([SCAN_DONE])
        except Exception as exc:
            logger.exception(SCAN_FAILED_LOG, exc)
            self.set_status(ANALYZER_ERROR_FORMAT.format(error=exc))
            self.calls.append([SCAN_FAILED, type(exc).__name__])
        self.pending_refresh = False
        self.scan_phase = SCAN_FINISHED
        self.set_refresh_enabled(True)
        self.finish_scan_record(NO_DURATION_S)
        self.render_signals()

    def finish_scan_record(self, duration_s: float, error: str = "") -> str:
        """The record a finished scan leaves, as one log line.

        Counts come off the analyzer the screen reads, so the record
        carries what the scan produced rather than what it asked for.
        Appends the emission to ``emitted`` in place of a bus.
        """
        signal_count = 0
        pair_count = 0
        try:
            inspector = self.inspector()
            signal_count = len(inspector.last_signals or [])
            pair_count = len(inspector.last_pairs or [])
        except Exception as exc:
            logger.debug(COUNT_READ_FAILED_LOG, exc)
        meta = self.last_meta or {}
        market_count = int(meta.get("symbol_count", 0) or 0)
        source = str(meta.get("source", UNKNOWN_SOURCE))
        suffix = SCAN_ERROR_SUFFIX.format(error=error) if error else ""
        logger.info(
            SCAN_FINISHED_LOG,
            market_count,
            signal_count,
            pair_count,
            duration_s,
            source,
            suffix,
        )
        line = SCAN_FINISHED_LOG % (
            market_count,
            signal_count,
            pair_count,
            duration_s,
            source,
            suffix,
        )
        self.emitted.append(
            [
                SCAN_FINISHED_TOPIC,
                {
                    "market_count": market_count,
                    "duration_s": round(float(duration_s), 3),
                    "signal_count": signal_count,
                    "pair_count": pair_count,
                    "source": source,
                    "error": error,
                },
            ]
        )
        self.calls.append([SCAN_RECORDED, market_count])
        return line

    def on_progress(self, message: str) -> None:
        """Write one progress line into the status label."""
        self.set_status(message)
        self.calls.append([PROGRESS_WRITTEN])

    def press_show_active(self, checked: bool) -> None:
        """Click the "Include active markets" switch.

        A switch already holding the asked-for state tells nobody it
        moved, so the slot below does not run.
        """
        if bool(checked) == self.show_active_checked:
            return
        self.show_active_checked = bool(checked)
        self.on_toggle_show_active(checked)

    def on_toggle_show_active(self, checked: bool) -> None:
        """Flip whether markets the fleet already trades are listed."""
        self.show_active = bool(checked)
        self.calls.append([SHOW_ACTIVE_TOGGLED, self.show_active])
        self.render_signals()

    def status_line(self) -> str:
        """The status line for the fetch report the screen last took."""
        return status_text(self.last_meta)

    def render_signals(self) -> None:
        """Rewrite the status line and both tables from the last scan."""
        try:
            inspector = self.inspector()
        except Exception:
            self.set_status(ANALYZER_UNAVAILABLE_TEXT)
            self.calls.append([ANALYZER_UNREACHABLE])
            return
        self.set_status(self.status_line())
        self.calls.append([STATUS_WRITTEN])
        self.fill_signal_rows(self.shown_signals(inspector.last_signals))
        self.fill_pair_rows(inspector.last_pairs)


class PerBotViewModel:
    """The per-bot Market Inspector screen, as one ordered element list.

    ``order`` holds one entry per element the shipped builder adds, in
    the order it adds them. A group carries its own children.
    """

    def __init__(self, bot: Any = None, inspector_source: Any = None) -> None:
        self.bot = bot
        self.inspector_source = inspector_source
        self.asset = NO_ASSET
        self.spacing_px = PER_BOT_SPACING_PX
        self.order: list = []
        self.marks: list = []

    def mark(self, lead: str, strong: str, breaks: int, tail: str) -> None:
        """Record one label's pieces beside the marked-up text they build."""
        self.marks.append(
            [marked_text(lead, strong, breaks, tail), lead, strong, breaks, tail]
        )

    def inspector(self) -> Any:
        """The analyzer this screen reads, injected or process-wide."""
        if self.inspector_source is not None:
            return self.inspector_source
        from ...trading.market_inspector import get_shared_inspector

        return get_shared_inspector()

    def build(self) -> list:
        """Fill ``order`` with every element the per-bot screen carries."""
        self.order = []
        self.marks = []
        try:
            inspector = self.inspector()
        except Exception:
            self.order.append(
                [LABEL_ELEMENT, PER_BOT_UNAVAILABLE_TEXT, NO_STYLE, NO_WORD_WRAP]
            )
            self.order.append([STRETCH_ELEMENT])
            return self.order
        self.asset = asset_of(self.bot)
        signals = inspector.last_signals
        if not signals:
            self.order.append(
                [LABEL_ELEMENT, NO_SCAN_TEXT, NO_SCAN_STYLE, NO_SCAN_WORD_WRAP]
            )
            self.mark(NO_PIECE, NO_SCAN_HEADLINE, NO_SCAN_BREAKS, NO_SCAN_BODY)
            self.order.append([STRETCH_ELEMENT])
            return self.order
        own = inspector.get_signal(self.asset)
        self.order.append(
            [
                GROUP_ELEMENT,
                OWN_CARD_TITLE_FORMAT.format(asset=self.asset or UNKNOWN_ASSET_MARK),
                self.own_card_rows(own),
            ]
        )
        higher = [
            found
            for found in signals
            if found.score > (own.score if own else NO_SCORE)
            and found.symbol != self.asset
        ][:HIGHER_LIMIT]
        if higher:
            self.order.append(
                [GROUP_ELEMENT, HIGHER_GROUP_TITLE, self.higher_rows(higher)]
            )
        related = [
            pair
            for pair in inspector.last_pairs
            if pair.long_side.symbol == self.asset
            or pair.short_side.symbol == self.asset
        ]
        if related:
            self.order.append(
                [GROUP_ELEMENT, PER_BOT_PAIRS_GROUP_TITLE, self.pair_lines(related)]
            )
        self.order.append([STRETCH_ELEMENT])
        return self.order

    def own_card_rows(self, own: Any) -> list:
        """The lines inside the bot's own asset card."""
        if own is None:
            return [
                [
                    LABEL_ELEMENT,
                    NO_SIGNAL_FORMAT.format(asset=self.asset or THIS_ASSET_TEXT),
                    NO_STYLE,
                    NO_WORD_WRAP,
                ]
            ]
        tail = SIGNAL_LINE_TAIL_FORMAT.format(
            score=own.score, direction=own.direction or NO_DIRECTION_MARK
        )
        self.mark(SIGNAL_LINE_LEAD, own.signal, NO_BREAKS, tail)
        found = [
            [
                LABEL_ELEMENT,
                SIGNAL_LINE_FORMAT.format(
                    signal=own.signal,
                    score=own.score,
                    direction=own.direction or NO_DIRECTION_MARK,
                ),
                SIGNAL_LINE_STYLE_FORMAT.format(color=signal_color(own.signal)),
                NO_WORD_WRAP,
            ]
        ]
        for key in TIMEFRAME_KEYS:
            found.append(
                [
                    LABEL_ELEMENT,
                    TIMEFRAME_LINE_FORMAT.format(
                        key=key, reading=timeframe_text(own.per_tf.get(key))
                    ),
                    NO_STYLE,
                    NO_WORD_WRAP,
                ]
            )
        return found

    def higher_rows(self, higher: list) -> list:
        """The lines inside the higher-scoring markets card."""
        return [
            [
                LABEL_ELEMENT,
                HIGHER_ROW_FORMAT.format(
                    symbol=found.symbol, signal=found.signal, score=found.score
                )
                + (
                    HIGHER_ROW_ACTIVE_SUFFIX
                    if found.is_active
                    else HIGHER_ROW_QUIET_SUFFIX
                ),
                HIGHER_ROW_STYLE_FORMAT.format(color=signal_color(found.signal)),
                NO_WORD_WRAP,
            ]
            for found in higher
        ]

    def pair_lines(self, related: list) -> list:
        """The lines inside the opposing-pairs card."""
        return [
            [
                LABEL_ELEMENT,
                PER_BOT_PAIR_FORMAT.format(
                    long_symbol=pair.long_side.symbol,
                    short_symbol=pair.short_side.symbol,
                    correlation=pair.correlation_30d,
                ),
                NO_STYLE,
                NO_WORD_WRAP,
            ]
            for pair in related
        ]


def build_per_bot_model(
    bot: Any = None, inspector_source: Any = None
) -> PerBotViewModel:
    """One per-bot screen, built from one bot and one analyzer."""
    model = PerBotViewModel(bot, inspector_source)
    model.build()
    return model


def build_model(
    bot_statuses: Optional[list] = None, **wiring
) -> MarketInspectorScreenModel:
    """One Market Inspector screen, driven from one fleet list."""
    model = MarketInspectorScreenModel(**wiring)
    if bot_statuses is not None:
        model.update_active_symbols(bot_statuses)
    return model


class SymbolOnlyBot:
    """One bot as the per-bot screen reads it: a config naming a symbol.

    The renderer reaches this surface over the bridge, where a running
    bot cannot travel, so the request names the symbol and this stands
    in for the bot ``build_per_bot_model`` reads the base asset from.
    """

    class Config:
        """The one config field ``asset_of`` reads."""

        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

    def __init__(self, symbol: str) -> None:
        self.config = self.Config(symbol)


def per_bot_view(model: PerBotViewModel) -> dict:
    """One per-bot screen as the compared snapshot reads it."""
    return {
        "asset": model.asset,
        "spacing_px": model.spacing_px,
        "margins_px": list(PER_BOT_MARGINS_PX),
        "order": model.order,
        "marks": [list(one) for one in model.marks],
    }


def empty_per_bot_view() -> dict:
    """The per-bot screen a request naming no bot publishes."""
    return per_bot_view(PerBotViewModel())


def build_view_model(
    model: MarketInspectorScreenModel, per_bot: Optional[dict] = None
) -> dict:
    """Return the whole surface state as one serialisable dict."""
    return {
        "method": METHOD,
        "accessible_name": model.accessible_name,
        "style_sheet": model.style_sheet,
        "skin": dict(SKIN),
        "refresh_label": REFRESH_LABEL,
        "refresh_tooltip": REFRESH_TOOLTIP,
        "refresh_enabled": model.refresh_enabled,
        "show_active_label": SHOW_ACTIVE_LABEL,
        "show_active_checked": model.show_active_checked,
        "no_cell": NO_CELL,
        "show_active_default": SHOW_ACTIVE_CHECKED,
        "show_active_tooltip": SHOW_ACTIVE_TOOLTIP,
        "show_active": model.show_active,
        "status_text": model.status_label_text,
        "status_initial_text": STATUS_INITIAL_TEXT,
        "status_style": STATUS_STYLE,
        "signals_group_title": SIGNALS_GROUP_TITLE,
        "signal_columns": list(SIGNAL_COLUMNS),
        "signals_max_height_px": SIGNALS_MAX_HEIGHT_PX,
        "signal_rows": [[list(cell) for cell in row] for row in model.signal_rows],
        "pairs_group_title": PAIRS_GROUP_TITLE,
        "pair_columns": list(PAIR_COLUMNS),
        "pairs_max_height_px": PAIRS_MAX_HEIGHT_PX,
        "pair_rows": [[list(cell) for cell in row] for row in model.pair_rows],
        "left_modules": [list(one) for one in model.left_modules()],
        "right_zones": [list(one) for one in model.right_zones()],
        "right_zone_keys": list(RIGHT_ZONE_KEYS),
        "right_zone_titles": list(RIGHT_ZONE_TITLES),
        "left_module_keys": list(LEFT_MODULE_KEYS),
        "left_module_titles": list(LEFT_MODULE_TITLES),
        "module_frame_px": MODULE_FRAME_PX,
        "module_margins_px": list(MODULE_MARGINS_PX),
        "module_title_padding_px": list(MODULE_TITLE_PADDING_PX),
        "button_padding_px": list(BUTTON_PADDING_PX),
        "button_font_weight": BUTTON_FONT_WEIGHT,
        "table_viewport_px": TABLE_VIEWPORT_PX,
        "table_resize_mode": TABLE_RESIZE_MODE,
        "table_edit_triggers": TABLE_EDIT_TRIGGERS,
        "table_alternating_rows": TABLE_ALTERNATING_ROWS,
        "splitter_orientation": SPLITTER_ORIENTATION,
        "splitter_stretch": list(SPLITTER_STRETCH),
        "splitter_sizes_px": list(SPLITTER_SIZES_PX),
        "splitter_handle_px": SPLITTER_HANDLE_PX,
        "splitter_panes": SPLITTER_PANES,
        "outer_margins_px": list(OUTER_MARGINS_PX),
        "outer_spacing_px": OUTER_SPACING_PX,
        "left_margins_px": list(LEFT_MARGINS_PX),
        "left_spacing_px": LEFT_SPACING_PX,
        "top_row_spacing_px": TOP_ROW_SPACING_PX,
        "top_row_margins_px": list(TOP_ROW_MARGINS_PX),
        "per_bot_spacing_px": PER_BOT_SPACING_PX,
        "per_bot_margins_px": list(PER_BOT_MARGINS_PX),
        "group_margins_px": list(GROUP_MARGINS_PX),
        "group_spacing_px": GROUP_SPACING_PX,
        "per_bot_view": empty_per_bot_view() if per_bot is None else per_bot,
        "active_symbols": sorted(model.active_symbols),
        "last_meta": dict(model.last_meta),
        "pending_refresh": model.pending_refresh,
        "scan_state": model.scan_state(),
        "empty_texts": model.empty_notes(),
        "exchange_source_wired": bool(model.connectors_getter and model.scheduler),
        "scheduled": [list(found) for found in model.scheduled],
        "colors": {
            "entry_long_high": COLOR_ENTRY_LONG_HIGH,
            "entry_long": COLOR_ENTRY_LONG,
            "entry_short_high": COLOR_ENTRY_SHORT_HIGH,
            "entry_short": COLOR_ENTRY_SHORT,
            "watchlist": COLOR_WATCHLIST,
            "other": COLOR_OTHER,
            "active": COLOR_ACTIVE,
            "correlation": COLOR_CORRELATION,
            "method": COLOR_METHOD,
            "none": NO_COLOR,
        },
        "signal_names": {
            "entry_long_high": SIGNAL_ENTRY_LONG_HIGH,
            "entry_long": SIGNAL_ENTRY_LONG,
            "entry_short_high": SIGNAL_ENTRY_SHORT_HIGH,
            "entry_short": SIGNAL_ENTRY_SHORT,
            "watchlist": SIGNAL_WATCHLIST,
        },
        "timeframe": {
            "keys": list(TIMEFRAME_KEYS),
            "format": TIMEFRAME_FORMAT,
            "empty": EMPTY_TIMEFRAME,
            "tag_upper": TAG_UPPER,
            "tag_lower": TAG_LOWER,
            "tag_middle": TAG_MIDDLE,
            "tight_suffix": TIGHT_SUFFIX,
            "no_tight_suffix": NO_TIGHT_SUFFIX,
            "line_format": TIMEFRAME_LINE_FORMAT,
        },
        "cells": {
            "active_yes": ACTIVE_YES,
            "active_no": ACTIVE_NO,
            "score_format": SCORE_FORMAT,
            "correlation_format": CORRELATION_FORMAT,
            "pair_side_format": PAIR_SIDE_FORMAT,
            "pair_score_format": PAIR_SCORE_FORMAT,
        },
        "age": {
            "minute_s": MINUTE_S,
            "hour_s": HOUR_S,
            "day_s": DAY_S,
            "no_age_s": NO_AGE_S,
            "seconds_format": AGE_SECONDS_FORMAT,
            "minutes_format": AGE_MINUTES_FORMAT,
            "hours_format": AGE_HOURS_FORMAT,
            "hours_minutes_format": AGE_HOURS_MINUTES_FORMAT,
            "days_format": AGE_DAYS_FORMAT,
        },
        "sources": {
            "coingecko": SOURCE_COINGECKO,
            "cache": SOURCE_CACHE,
            "error": SOURCE_ERROR,
            "network_partial": SOURCE_NETWORK_PARTIAL,
            "unknown": SOURCE_UNKNOWN,
        },
        "status_formats": {
            "live": STATUS_LIVE_FORMAT,
            "cache": STATUS_CACHE_FORMAT,
            "cache_fallback": STATUS_CACHE_FALLBACK_FORMAT,
            "error": STATUS_ERROR_FORMAT,
            "partial": STATUS_PARTIAL_FORMAT,
            "unknown_error": UNKNOWN_ERROR_TEXT,
            "no_candles": NO_CANDLES_TEXT,
        },
        "fetch_texts": {
            "not_wired": NOT_WIRED_TEXT,
            "no_connectors": NO_CONNECTORS_TEXT,
            "fetching": FETCHING_TEXT,
            "scheduler_error": SCHEDULER_ERROR_FORMAT,
            "analyzer_error": ANALYZER_ERROR_FORMAT,
            "analyzer_unavailable": ANALYZER_UNAVAILABLE_TEXT,
        },
        "logs": {
            "fetch_failed": FETCH_FAILED_LOG,
            "scan_failed": SCAN_FAILED_LOG,
            "proposals_failed": PROPOSALS_FAILED_LOG,
            "topologies_missing": TOPOLOGIES_MISSING_LOG,
            "ata_run_failed": ATA_RUN_FAILED_LOG,
            "connectors_read_failed": CONNECTORS_READ_FAILED_LOG,
            "scan_started": SCAN_STARTED_LOG,
            "scan_finished": SCAN_FINISHED_LOG,
            "count_read_failed": COUNT_READ_FAILED_LOG,
        },
        "scan": {
            "phases": list(SCAN_PHASES),
            "not_asked": SCAN_NOT_ASKED,
            "running": SCAN_RUNNING,
            "finished": SCAN_FINISHED,
            "started_topic": SCAN_STARTED_TOPIC,
            "finished_topic": SCAN_FINISHED_TOPIC,
            "signals_noun": SIGNALS_NOUN,
            "pairs_noun": PAIRS_NOUN,
            "scanning_format": SCANNING_FORMAT,
            "empty_format": SCAN_EMPTY_FORMAT,
            "no_scan_format": NO_SCAN_FORMAT,
            "error_suffix": SCAN_ERROR_SUFFIX,
            "unknown_source": UNKNOWN_SOURCE,
            "no_duration_s": NO_DURATION_S,
        },
        "emitted": [list(one) for one in model.emitted],
        "error_meta": {
            "source": ERROR_META_SOURCE,
            "age_seconds": ERROR_META_AGE_S,
            "symbol_count": ERROR_META_COUNT,
        },
        "per_bot": {
            "unavailable": PER_BOT_UNAVAILABLE_TEXT,
            "no_scan_text": NO_SCAN_TEXT,
            "no_scan_style": NO_SCAN_STYLE,
            "no_scan_word_wrap": NO_SCAN_WORD_WRAP,
            "own_card_title_format": OWN_CARD_TITLE_FORMAT,
            "unknown_asset_mark": UNKNOWN_ASSET_MARK,
            "this_asset_text": THIS_ASSET_TEXT,
            "no_signal_format": NO_SIGNAL_FORMAT,
            "no_scan_headline": NO_SCAN_HEADLINE,
            "no_scan_breaks": NO_SCAN_BREAKS,
            "no_scan_body": NO_SCAN_BODY,
            "signal_line_format": SIGNAL_LINE_FORMAT,
            "signal_line_lead": SIGNAL_LINE_LEAD,
            "signal_line_mark": SIGNAL_LINE_MARK,
            "signal_line_tail_format": SIGNAL_LINE_TAIL_FORMAT,
            "signal_line_style_format": SIGNAL_LINE_STYLE_FORMAT,
            "no_direction_mark": NO_DIRECTION_MARK,
            "higher_group_title": HIGHER_GROUP_TITLE,
            "higher_limit": HIGHER_LIMIT,
            "no_score": NO_SCORE,
            "higher_row_format": HIGHER_ROW_FORMAT,
            "higher_row_active_suffix": HIGHER_ROW_ACTIVE_SUFFIX,
            "higher_row_quiet_suffix": HIGHER_ROW_QUIET_SUFFIX,
            "higher_row_style_format": HIGHER_ROW_STYLE_FORMAT,
            "pairs_group_title": PER_BOT_PAIRS_GROUP_TITLE,
            "pair_format": PER_BOT_PAIR_FORMAT,
        },
        "elements": {
            "label": LABEL_ELEMENT,
            "group": GROUP_ELEMENT,
            "stretch": STRETCH_ELEMENT,
            "no_style": NO_STYLE,
            "no_word_wrap": NO_WORD_WRAP,
        },
        "marks": {
            "strong_open": STRONG_OPEN,
            "strong_close": STRONG_CLOSE,
            "break_tag": BREAK_TAG,
            "strong_weight": STRONG_WEIGHT,
            "no_breaks": NO_BREAKS,
            "no_piece": NO_PIECE,
        },
        "symbols": {
            "separator": SYMBOL_SEPARATOR,
            "no_symbol": NO_SYMBOL,
            "no_asset": NO_ASSET,
        },
        "adopt_signal_name": MarketInspectorScreenModel.ADOPT_SIGNAL_NAME,
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "actions": dict(ACTIONS),
        "call_names": list(CALL_NAMES),
        "logger_name": LOGGER_NAME,
        "calls": [list(call) for call in model.calls],
    }


PANE_MODEL: Optional[MarketInspectorScreenModel] = None


def pane_model() -> MarketInspectorScreenModel:
    """The one screen the bridge keeps between calls.

    Built on the first request, never at import: building one and
    drawing it reaches the process-wide analyzer, which the accessor
    creates the first time anything asks for it.
    """
    global PANE_MODEL
    if PANE_MODEL is None:
        PANE_MODEL = MarketInspectorScreenModel()
    return PANE_MODEL


def view_model(params: dict) -> dict:
    """Bridge handler for ``market_inspector.state``.

    Reads ``reset``, ``proposals``, ``meta``, ``show_active``,
    ``bot_statuses``, ``render``, ``refresh``, ``force`` and
    ``bot_symbol`` from the request parameters. The screen keeps its rows
    between calls because the shipped screen does; ``reset`` is what a
    fresh paint sends. ``bot_symbol`` is what the per-bot view is built
    for; a request naming none publishes an empty one.
    """
    global PANE_MODEL
    if params.get("reset", False):
        PANE_MODEL = MarketInspectorScreenModel()
    model = pane_model()
    if params.get("proposals") is not None:
        model.topologies_pane = TopologyPaneModel(params["proposals"])
    if params.get("meta") is not None:
        model.last_meta = dict(params["meta"])
    if params.get("show_active") is not None:
        model.press_show_active(params["show_active"])
    if params.get("bot_statuses") is not None:
        model.update_active_symbols(params["bot_statuses"])
    if params.get("render", False):
        model.render_signals()
    if params.get("refresh", False):
        model.start_fetch(force=params.get("force", False))
    symbol = params.get("bot_symbol")
    if symbol is None:
        return build_view_model(model)
    per_bot = build_per_bot_model(SymbolOnlyBot(symbol), model.inspector_source)
    return build_view_model(model, per_bot_view(per_bot))


def live_view_model(params: dict, live: Any) -> dict:
    """Build the Market Inspector view model from the running fleet.

    ``live.bot_manager.list_bots`` names the bots ``update_active_symbols``
    reads the active markets from. ``view_model`` answers while no manager
    is bound, and a request naming its own ``bot_statuses`` keeps them.
    """
    manager = getattr(live, "bot_manager", None)
    asked = dict(params or {})
    if manager is not None and hasattr(manager, "list_bots"):
        if asked.get("bot_statuses") is None:
            asked["bot_statuses"] = list(manager.list_bots())
    return view_model(asked)


def bind_live(live: Any) -> Any:
    """Return a ``market_inspector.state`` handler reading ``live``.

    ``src.core.desktop_bridge.build_registry`` calls this when the running
    program serves the bridge, and the handler defers to ``live_view_model``.
    """

    def handler(params: dict) -> dict:
        return live_view_model(params or {}, live)

    return handler
