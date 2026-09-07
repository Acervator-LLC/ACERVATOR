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

from ...trading import ata_spm, ata_spm_push

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

STEP_BACK_TEXT = "◀"
STEP_NEXT_TEXT = "▶"
STEP_BACK_TOOLTIP = "Show the previous entry in this zone."
STEP_NEXT_TOOLTIP = "Show the next entry in this zone."
STEP_BUTTON_WIDTH_PX = 26
# The themed QPushButton pads 20 px each side, which leaves no room for a glyph.
STEP_BUTTON_STYLE = "padding: 2px;"
POSITION_FORMAT = "{at} of {total}"
POSITION_EMPTY_TEXT = "0 of 0"
POSITION_STYLE = "color: #aaa; font-size: 11px;"

ENTRY_CLASS = "_ZoneEntry"
ENTRY_STYLE = "_ZoneEntry { border: 1px solid #333; border-radius: 6px; padding: 4px; }"
ENTRY_MARGINS_PX = (8, 6, 8, 6)
ENTRY_SPACING_PX = 4
ENTRY_HEADLINE_STYLE = "font-weight: bold;"
ENTRY_META_STYLE = "color: #888; font-size: 11px;"
ENTRY_METHOD_STYLE = "color: #00cccc; font-size: 11px;"
ENTRY_ACCESSIBLE_NAME = "Zone entry"
STEPPER_ACCESSIBLE_NAME = "Zone stepper"
ENTRY_HINT_TEXT = "Click the entry for how and why it is here."
ENTRY_HINT_STYLE = "color: #666; font-size: 10px;"

DETAIL_STYLE = "color: #ccc; font-size: 11px;"
DETAIL_FORMAT = "{name}: {value}"
DETAIL_TEST_NAME = "Test"
DETAIL_WINDOW_NAME = "Window"
DETAIL_RESULT_NAME = "Result"
DETAIL_REASON_NAME = "Why it is here"
DETAIL_TEST_FORMAT = "{label} — {test}"
DETAIL_WINDOW_BARS_FORMAT = "{observations} daily closes"
DETAIL_WINDOW_LIVE_TEXT = "the live bot state"
LIVE_WINDOW_KEY = "live"
NO_DETAIL_TEXT = "This entry records no test."

METHOD_LINE_FORMAT = "{label}  •  {window}  •  {statistic}"
METHOD_LINE_NONE_TEXT = "no method"

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

ATA_SPM_NO_SECTOR_TEXT = "No sector added. Name one and press Scan Now."
SECTOR_FIELD_PLACEHOLDER = "Sector"
SECTOR_FIELD_TOOLTIP = (
    "Name a market sector to scan. Every asset the sector holds is "
    "charted and run through the twelve voters."
)
#: The sector field takes the row's slack, so no other control's position
#: follows from the width its own text happens to take.
SECTOR_FIELD_MIN_WIDTH_PX = 72
SCAN_NOW_LABEL = "Scan Now"
SCAN_NOW_TOOLTIP = (
    "Scan this sector now on the timeframes ticked beside it, without "
    "waiting for a rotation."
)
CLASS_BOX_TOOLTIP = "The asset class this sector holds. It sets the four timeframes."
CLASS_BOX_WIDTH_PX = 92
TIMEFRAME_BOX_TOOLTIP_FORMAT = "Scan this sector on {label}."
TIMEFRAME_BOX_WIDTH_PX = 64
TIMEFRAME_BOX_HEIGHT_PX = 22

#: The indicator and its label together, which is one Qt ``QCheckBox`` and
#: one page label element.
TIMEFRAME_ROW_PART = "timeframe-row"
ATA_ROW_SPACING_PX = 6

#: The expanded ATA-SPM entry's line names, one per phase readback.
PHASE_ONE_NAME = "Phase 1 Evaluate"
PHASE_TWO_NAME = "Phase 2 Identify"
PHASE_THREE_NAME = "Phase 3 Pull"
PHASE_SEVEN_NAME = "Phase 7 Follow-Up"
PHASE_EIGHT_NAME = "Phase 8 Timeframes"
PHASE_NOTE_NAME = "Waiting on"
NO_FOLLOW_UP_TEXT = "No call is being followed up yet."
DEFERRED_TAG = "deferred"
PHASE_ROW_NAME_FORMAT = "{phase} {tag}"
CALL_TAG_FORMAT = "{symbol} {label}"
BAND_TAG_FORMAT = "{symbol} bands"
MESSAGE_ROW_NAME_FORMAT = "{symbol} {label}"
NO_CALL_TEXT = "No chart carried a reversal vote."

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

# ── phases four, five and six: the bucket, its buttons and the settings ──

APPROVE_LABEL = "Approve"
DECLINE_LABEL = "Decline"
POST_SELECTED_LABEL = "Post Selected"
POST_ALL_LABEL = "Post All"
FULL_AUTO_LABEL = "Send Bucket Full Auto"
SETTINGS_LABEL = "Settings"
SAVE_CREDENTIALS_LABEL = "Save credentials"

APPROVE_PART = "approve-button"
DECLINE_PART = "decline-button"
POST_SELECTED_PART = "post-selected"
POST_ALL_PART = "post-all"
FULL_AUTO_PART = "full-auto"
SETTINGS_PART = "settings-button"
SAVE_CREDENTIALS_PART = "save-credentials"
SETTING_FIELD_PART = "setting-field"
THUMBNAIL_PART = "post-thumbnail"

#: Every press ``MarketInspectorScreenModel.push_action`` answers, which is
#: how the Electron host knows which key to send as one.
PUSH_PARTS = (
    APPROVE_PART,
    DECLINE_PART,
    POST_SELECTED_PART,
    POST_ALL_PART,
    FULL_AUTO_PART,
    SETTINGS_PART,
    THUMBNAIL_PART,
)

#: Sized here rather than by their own text, so the Qt widget and the page
#: report one box.
PUSH_BUTTON_HEIGHT_PX = 36
FIELD_HEIGHT_PX = 37
APPROVE_WIDTH_PX = 100
DECLINE_WIDTH_PX = 92
POST_SELECTED_WIDTH_PX = 128
POST_ALL_WIDTH_PX = 92
FULL_AUTO_WIDTH_PX = 184
SETTINGS_WIDTH_PX = 96
SCAN_NOW_WIDTH_PX = 108

#: The wording each empty credential field shows, in the order
#: ``ata_spm_push.CREDENTIAL_FIELD_KEYS`` names them.
CREDENTIAL_PLACEHOLDERS = ("API key", "API signature")

#: The two fields one push target's credential is typed into, each as its
#: part name and the wording the empty field shows.
CREDENTIAL_FIELDS = tuple(
    zip(ata_spm_push.CREDENTIAL_FIELD_KEYS, CREDENTIAL_PLACEHOLDERS)
)

APPROVE_TOOLTIP = "Approve this post so Post All and Full Auto release it."
DECLINE_TOOLTIP = "Decline this post. No button sends a declined post."
POST_SELECTED_TOOLTIP = "Send the post on screen, at no more than the configured rate."
POST_ALL_TOOLTIP = "Send every approved post, at no more than the configured rate."
FULL_AUTO_TOOLTIP = "Release approved posts without a click, at the configured rate."
SETTINGS_TOOLTIP = "Show the ATA-SPM settings page, or the scan page."
SAVE_CREDENTIALS_TOOLTIP = "Encrypt every credential typed above into the vault."
CREDENTIAL_FIELD_WIDTH_PX = 96
SETTING_FIELD_WIDTH_PX = 180
SETTINGS_ROW_SPACING_PX = 6
SETTINGS_LABEL_WIDTH_PX = 150

#: Every ATA-SPM setting a phase reads, with the wording its row carries.
SETTING_MAX_POSTS = "max_posts_per_hour"
SETTING_MAX_INDICATORS = "max_supporting_indicators"
SETTING_CONFIRMATION_SHARE = "confirmation_share_pct"
SETTING_MESSAGE_FORMAT = "message_format"
SETTING_ROWS = (
    (SETTING_MAX_POSTS, "Max posts per hour"),
    (SETTING_MAX_INDICATORS, "Max supporting indicators"),
    (SETTING_CONFIRMATION_SHARE, "Confirmation share %"),
    (SETTING_MESSAGE_FORMAT, "Standardised message text"),
)
COUNT_SETTINGS = (
    SETTING_MAX_POSTS,
    SETTING_MAX_INDICATORS,
    SETTING_CONFIRMATION_SHARE,
)

#: The chart one bucket post carries, at its thumbnail and its larger size.
THUMBNAIL_WIDTH_PX = 120
THUMBNAIL_HEIGHT_PX = 36
PREVIEW_WIDTH_PX = 320
PREVIEW_HEIGHT_PX = 160
THUMBNAIL_COLUMNS = 40
PREVIEW_COLUMNS = 80
CHART_BORDER_PX = 1
CHART_PAD_PX = 2
CHART_LINE_PX = 1
CHART_CLOSE_PX = 4
PREVIEW_PART = "post-preview"
CHART_COLUMN_PART = "chart-column"
CHART_BAND_PART = "chart-band"
CHART_CLOSE_PART = "chart-close"
CHART_BOX_STYLE_FORMAT = "border: {border}px solid {color};"
CHART_TOOLTIP_FORMAT = "{symbol} {label} · {vote} · press for the larger chart."
STRIP_TEXT_FORMAT = (
    "lower {lower:g} · middle {middle:g} · upper {upper:g} "
    "· last close {close:g} · band position {band:.4f}"
)
STRIP_TEXT_PART = "strip-text"
CHART_LOW_FLOOR = 0.0
CHART_FLAT_SPAN = 1.0

#: The ticker and the bull or bear word the bucket draws beside its thumbnail.
VOTE_PART = "post-vote"
VOTE_STYLE_FORMAT = "color: {color}; font-weight: bold; font-size: 13px;"

#: The ticker line is sized here, not by the width its own text takes, so
#: the vote word beside it sits in one place in every host.
BUCKET_HEADLINE_WIDTH_PX = 96

BUCKET_HEADLINE_FORMAT = "{symbol} {label}"
BUCKET_DETAIL_NAME_FORMAT = "{target} {symbol} line {at}"
BUCKET_FOLLOW_UP_FORMAT = "{phase} · {target} · follow-up on {follows}"
BUCKET_METHOD_FORMAT = (
    "{phase} · {target} · {bars} candles, last close {close:g} "
    "· band position {band:.4f}"
)

PUSH_ACTION_SET = "push.action"
CREDENTIAL_STORED = "credential.stored"
CREDENTIAL_REFUSED = "credential.refused"
SETTING_WRITTEN = "setting.written"
SETTINGS_PAGE_TOGGLED = "settings.toggled"

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

#: The padding and border the theme gives ``QLineEdit`` and ``QComboBox``,
#: as left, top, right and bottom.
FIELD_PADDING_PX = (12, 8, 12, 8)
FIELD_BORDER_PX = 1

#: The indicator box and the gap to its text, read off a themed ``QCheckBox``
#: as ``PM_IndicatorWidth`` 22 and ``PM_CheckBoxLabelSpacing`` 8.
CHECK_INDICATOR_PX = 22
CHECK_LABEL_SPACING_PX = 8

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

#: The strip marker colour each bucket vote draws in, and the fill behind it.
VOTE_COLORS = {
    ata_spm_push.VOTE_BULL: COLOR_ENTRY_LONG_HIGH,
    ata_spm_push.VOTE_BEAR: COLOR_ENTRY_SHORT_HIGH,
}
VOTE_FILL_COLORS = {
    ata_spm_push.VOTE_BULL: COLOR_ENTRY_LONG,
    ata_spm_push.VOTE_BEAR: COLOR_ENTRY_SHORT,
}

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
SECTOR_MAP_FAILED_LOG = "sector map read failed: %s"
CANDLE_READ_FAILED_LOG = "scanned candle read failed on %s %s: %s"
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
    "zone_stepped": "step_zone",
    "zone_toggled": "toggle_zone",
    "push_pressed": "push_action",
    "credential_saved": "store_credential",
    "setting_written": "set_setting",
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
ATA_SOURCES_SET = "ata_sources.set"
SECTOR_TEXT_SET = "sector.text"
SECTOR_CLASS_SET = "sector.class"
SECTOR_CLASS_REFUSED = "sector.class_refused"
TIMEFRAME_TOGGLED = "sector.timeframe"
TIMEFRAME_UNREACHABLE = "sector.timeframe_unreachable"
SCAN_NOW_RUN = "scan_now.run"
SCAN_NOW_UNNAMED = "scan_now.unnamed"
ZONE_STEPPED = "zone.stepped"
ZONE_TOGGLED = "zone.toggled"

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
    ATA_SOURCES_SET,
    SECTOR_TEXT_SET,
    SECTOR_CLASS_SET,
    SECTOR_CLASS_REFUSED,
    TIMEFRAME_TOGGLED,
    TIMEFRAME_UNREACHABLE,
    SCAN_NOW_RUN,
    SCAN_NOW_UNNAMED,
    ZONE_STEPPED,
    ZONE_TOGGLED,
    PUSH_ACTION_SET,
    CREDENTIAL_STORED,
    CREDENTIAL_REFUSED,
    SETTING_WRITTEN,
    SETTINGS_PAGE_TOGGLED,
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


def ata_spm_zone_text(run: Any, sector_count: Any) -> str:
    """The ATA-SPM zone's line for the run it holds and the sectors added.

    A zone holding no sector names what it waits for rather than reporting
    a run nobody asked for.
    """
    if not int(sector_count or 0):
        return ATA_SPM_NO_SECTOR_TEXT
    return ata_spm_text(run)


def phase_row(phase: Any, tag: Any, value: Any) -> list:
    """One expanded line, named for the phase and the thing it reports on.

    The name carries ``tag`` so two rows of one phase never share a name.
    """
    return detail_row(PHASE_ROW_NAME_FORMAT.format(phase=phase, tag=tag), value)


def phase_one_rows(scan: Any) -> list:
    """The expanded lines phase one leaves: one per timeframe scanned."""
    if scan.note:
        return [detail_row(PHASE_NOTE_NAME, scan.note)]
    if not scan.timeframes:
        return [detail_row(PHASE_NOTE_NAME, ata_spm.NO_TIMEFRAME_TEXT)]
    return [
        phase_row(
            PHASE_ONE_NAME,
            ata_spm.timeframe_label(one.timeframe),
            ata_spm.TIMEFRAME_VOTE_FORMAT.format(
                votes=len(one.votes), unread=len(one.unread)
            ),
        )
        for one in scan.timeframes
    ]


def phase_two_rows(calls: Any) -> list:
    """The expanded lines phase two leaves: one per reversal call."""
    if not calls:
        return [detail_row(PHASE_TWO_NAME, NO_CALL_TEXT)]
    return [
        phase_row(
            PHASE_TWO_NAME,
            CALL_TAG_FORMAT.format(
                symbol=one.symbol, label=ata_spm.timeframe_label(one.timeframe)
            ),
            ata_spm.CALL_META_FORMAT.format(
                direction=one.direction_text,
                net=one.net_score,
                confidence=ata_spm.confidence_pct(one.confidence),
                band=one.band_position,
            ),
        )
        for one in calls
    ]


def phase_three_rows(pulls: Any) -> list:
    """The expanded lines phase three leaves: the chart, its bands and each message.

    An ``ata_spm.IndicatorMessage`` is the whole line, so ``phase_row``
    writes nothing in front of it.
    """
    rows: list = []
    for one in pulls:
        tag = CALL_TAG_FORMAT.format(
            symbol=one.symbol, label=ata_spm.timeframe_label(one.timeframe)
        )
        rows.append(
            phase_row(
                PHASE_THREE_NAME,
                tag,
                ata_spm.CHART_LINE_FORMAT.format(bars=one.bars, close=one.last_close),
            )
        )
        rows.append(
            phase_row(
                PHASE_THREE_NAME,
                BAND_TAG_FORMAT.format(symbol=one.symbol),
                ata_spm.BAND_LINE_FORMAT.format(
                    lower=one.band_lower,
                    middle=one.band_middle,
                    upper=one.band_upper,
                ),
            )
        )
        rows.extend(
            [
                MESSAGE_ROW_NAME_FORMAT.format(symbol=one.symbol, label=msg.label),
                msg.message,
            ]
            for msg in one.messages
        )
    return rows


def phase_seven_rows(outcomes: Any) -> list:
    """The expanded lines phase seven leaves: one per call it followed up.

    Each line carries the original call, the outcome and its evidence.
    """
    held = list(outcomes or [])
    if not held:
        return [detail_row(PHASE_SEVEN_NAME, NO_FOLLOW_UP_TEXT)]
    return [
        phase_row(
            PHASE_SEVEN_NAME,
            CALL_TAG_FORMAT.format(
                symbol=one.call.symbol,
                label=ata_spm.timeframe_label(one.call.timeframe),
            ),
            one.line,
        )
        for one in held
    ]


def phase_eight_rows(scan: Any, pulls: Any) -> list:
    """The expanded lines phase eight leaves: the count measured, then each vote.

    The first line names the timeframes scanned against the round the
    machine measured, and each later line is one call's agreement.
    """
    available = len(ata_spm.timeframes_for(scan.asset_class))
    rows = [
        phase_row(
            PHASE_EIGHT_NAME,
            scan.sector,
            ata_spm.TIMEFRAME_COUNT_FORMAT.format(
                scanned=len(scan.timeframes),
                available=available,
                seconds=scan.round_seconds,
            ),
        )
    ]
    if scan.deferred:
        rows.append(
            phase_row(
                PHASE_EIGHT_NAME,
                DEFERRED_TAG,
                ata_spm.TIMEFRAME_DEFERRED_FORMAT.format(
                    scanned=len(scan.timeframes),
                    available=available,
                    labels=ata_spm.AGREEMENT_LABEL_SEPARATOR.join(
                        ata_spm.timeframe_label(one) for one in scan.deferred
                    ),
                ),
            )
        )
    rows.extend(
        phase_row(
            PHASE_EIGHT_NAME,
            CALL_TAG_FORMAT.format(
                symbol=one.symbol, label=ata_spm.timeframe_label(one.timeframe)
            ),
            one.agreement.text,
        )
        for one in pulls
        if one.agreement is not None
    )
    return rows


def sector_entry(scan: Any, pulls: Any, follow_ups: Any = ()) -> dict:
    """One scanned sector as the entry the ATA-SPM zone steps through.

    The expansion carries every phase readback in order, so the entry says
    how and why each call under it exists and what happened to it.
    """
    calls = scan.calls
    held = [one for one in pulls if any(one.symbol == call.symbol for call in calls)]
    strongest = calls[0] if calls else None
    return zone_entry(
        ata_spm.SECTOR_LINE_FORMAT.format(
            sector=scan.sector, asset_class=scan.asset_class
        ),
        ata_spm.SECTOR_META_FORMAT.format(
            assets=len(scan.assets), votes=len(scan.votes), calls=len(calls)
        ),
        detail=(
            phase_one_rows(scan)
            + phase_two_rows(calls)
            + phase_three_rows(held)
            + phase_seven_rows(follow_ups)
            + phase_eight_rows(scan, held)
        ),
        method_text=(
            ata_spm.CALL_LINE_FORMAT.format(
                symbol=strongest.symbol,
                label=ata_spm.timeframe_label(strongest.timeframe),
                direction=strongest.direction_text,
            )
            if strongest is not None
            else scan.note or NO_CALL_TEXT
        ),
    )


def sector_row(sector: Any) -> list:
    """One sector as the control row reads it: name, class and its check boxes."""
    return [sector.name, sector.asset_class, sector.boxes()]


def vote_color(vote: Any) -> str:
    """The colour one bull or bear vote draws its ticker and last close in."""
    return VOTE_COLORS.get(str(vote), COLOR_OTHER)


def vote_fill_color(vote: Any) -> str:
    """The colour one bull or bear vote fills its chart columns in."""
    return VOTE_FILL_COLORS.get(str(vote), COLOR_OTHER)


def chart_closes(closes: Any, columns: Any) -> list:
    """``columns`` closes sampled evenly, the last close always kept."""
    held = [float(one) for one in closes or ()]
    wanted = int(columns)
    if not held or wanted <= 0:
        return []
    if wanted == 1 or len(held) <= wanted:
        return held[-1:] if wanted == 1 else held
    last = len(held) - 1
    return [held[round(one * last / (wanted - 1))] for one in range(wanted)]


def chart_range(prices: Any) -> tuple:
    """The lowest and highest price one chart draws between, never equal."""
    held = [float(one) for one in prices]
    if not held:
        return (CHART_LOW_FLOOR, CHART_LOW_FLOOR + CHART_FLAT_SPAN)
    low = min(held)
    high = max(held)
    if high <= low:
        return (low, low + CHART_FLAT_SPAN)
    return (low, high)


def chart_row_px(price: Any, low: Any, high: Any, height_px: Any) -> int:
    """The row one price sits on inside ``height_px``, the highest on top."""
    tall = max(1, int(height_px))
    span = float(high) - float(low)
    across = (float(price) - float(low)) / span if span else 0.0
    return max(0, min(tall - 1, round((1.0 - across) * (tall - 1))))


def chart_band_prices(post: Any) -> list:
    """The Bollinger band prices this post's chart draws a rule for."""
    return [
        float(one)
        for one in (post.band_lower, post.band_middle, post.band_upper)
        if float(one) != ata_spm.NO_BAND_VALUE
    ]


def chart_marks(post: Any, width_px: Any, height_px: Any, columns: Any) -> list:
    """Every rectangle one post's chart draws, each as part, box and colour.

    The close columns are drawn first, the band rules over them, and the
    last close last, so nothing the vote turns on is painted over.
    """
    wide = max(1, int(width_px) - 2 * CHART_PAD_PX)
    tall = max(1, int(height_px) - 2 * CHART_PAD_PX)
    drawn = chart_closes(post.closes, columns)
    bands = chart_band_prices(post)
    low, high = chart_range(drawn + bands)
    step = wide / len(drawn) if drawn else wide
    fill = vote_fill_color(post.vote)
    marks = []
    for column, price in enumerate(drawn):
        row = chart_row_px(price, low, high, tall)
        marks.append(
            [
                CHART_COLUMN_PART,
                CHART_PAD_PX + round(column * step),
                CHART_PAD_PX + row,
                max(1, round(step)),
                max(CHART_LINE_PX, tall - row),
                fill,
            ]
        )
    for price in bands:
        marks.append(
            [
                CHART_BAND_PART,
                CHART_PAD_PX,
                CHART_PAD_PX + chart_row_px(price, low, high, tall),
                wide,
                CHART_LINE_PX,
                COLOR_OTHER,
            ]
        )
    if drawn:
        marks.append(
            [
                CHART_CLOSE_PART,
                CHART_PAD_PX + max(0, wide - CHART_CLOSE_PX),
                CHART_PAD_PX
                + max(
                    0, chart_row_px(drawn[-1], low, high, tall) - CHART_CLOSE_PX // 2
                ),
                CHART_CLOSE_PX,
                CHART_CLOSE_PX,
                vote_color(post.vote),
            ]
        )
    return marks


def post_chart(post: Any, wide: Any = False) -> dict:
    """The chart one bucket post carries, as its thumbnail or its larger view.

    ``wide`` picks ``PREVIEW_WIDTH_PX`` over ``THUMBNAIL_WIDTH_PX``, and
    ``chart_marks`` answers every rectangle both hosts place inside it.
    """
    width_px = PREVIEW_WIDTH_PX if wide else THUMBNAIL_WIDTH_PX
    height_px = PREVIEW_HEIGHT_PX if wide else THUMBNAIL_HEIGHT_PX
    columns = PREVIEW_COLUMNS if wide else THUMBNAIL_COLUMNS
    return {
        "part": PREVIEW_PART if wide else THUMBNAIL_PART,
        "width_px": width_px,
        "height_px": height_px,
        "border_px": CHART_BORDER_PX,
        "column_part": CHART_COLUMN_PART,
        "band_part": CHART_BAND_PART,
        "close_part": CHART_CLOSE_PART,
        "marks": chart_marks(post, width_px, height_px, columns),
        "box_style": CHART_BOX_STYLE_FORMAT.format(
            border=CHART_BORDER_PX, color=COLOR_OTHER
        ),
        "symbol": post.symbol,
        "vote": post.vote,
        "label": ata_spm.timeframe_label(post.timeframe),
        "tooltip": CHART_TOOLTIP_FORMAT.format(
            symbol=post.symbol,
            label=ata_spm.timeframe_label(post.timeframe),
            vote=post.vote,
        ),
        "text": STRIP_TEXT_FORMAT.format(
            lower=post.band_lower,
            middle=post.band_middle,
            upper=post.band_upper,
            close=post.last_close,
            band=post.band_position,
        ),
    }


def post_vote(post: Any) -> list:
    """Whether the vote is bull or bear, as the word and the style beside the ticker."""
    return [
        str(post.vote),
        VOTE_STYLE_FORMAT.format(color=vote_color(post.vote)),
    ]


def action_row(
    part: Any, label: Any, tooltip: Any, width_px: Any, enabled: Any = True
) -> list:
    """One button a zone draws: its part name, its wording, its width and its state."""
    return [part, label, tooltip, bool(enabled), int(width_px)]


def bucket_actions() -> list:
    """Approve and Decline, the two buttons under one post's larger chart."""
    return [
        action_row(APPROVE_PART, APPROVE_LABEL, APPROVE_TOOLTIP, APPROVE_WIDTH_PX),
        action_row(DECLINE_PART, DECLINE_LABEL, DECLINE_TOOLTIP, DECLINE_WIDTH_PX),
    ]


def bucket_detail_rows(held: Any) -> list:
    """The expanded lines one bucket post leaves: the body that would be sent.

    Line zero is ``ata_spm_push.FIXED_HEADER``, which every artefact of the
    post composes.
    """
    post = held.post
    return [
        [
            BUCKET_DETAIL_NAME_FORMAT.format(
                target=post.target, symbol=post.symbol, at=at
            ),
            line,
        ]
        for at, line in enumerate(post.body.splitlines())
    ]


def bucket_method_text(post: Any) -> str:
    """The line one bucket entry carries about the chart behind it.

    A post carrying ``follows`` came from phase seven, so its line names
    the original post rather than the pull.
    """
    if post.follows:
        return BUCKET_FOLLOW_UP_FORMAT.format(
            phase=ata_spm_push.PHASE_FOLLOW_UP_NAME,
            target=post.target,
            follows=post.follows,
        )
    return BUCKET_METHOD_FORMAT.format(
        phase=ata_spm_push.PHASE_BUCKET_NAME,
        target=post.target,
        bars=post.bars,
        close=post.last_close,
        band=post.band_position,
    )


def bucket_entry(held: Any) -> dict:
    """One waiting post as the entry the Ready to Send zone steps through."""
    post = held.post
    return zone_entry(
        BUCKET_HEADLINE_FORMAT.format(
            symbol=post.symbol,
            label=ata_spm.timeframe_label(post.timeframe),
        ),
        held.meta,
        detail=bucket_detail_rows(held),
        method_text=bucket_method_text(post),
        thumbnail=post_chart(post),
        preview=post_chart(post, True),
        actions=bucket_actions(),
        vote=post_vote(post),
        headline_width_px=BUCKET_HEADLINE_WIDTH_PX,
    )


def bucket_entries(bucket: Any) -> list:
    """One entry per post the Ready to Send bucket holds."""
    return [bucket_entry(one) for one in bucket.posts]


def bucket_zone_text(bucket: Any, run: Any) -> str:
    """The Ready to Send zone's line: its own bucket, or what it waits for."""
    if bucket is not None and bucket.posts:
        return bucket.summary()
    return ready_to_send_text(run)


def credential_rows(settings: Any) -> list:
    """One row per push target: its name, whether a credential is held, the wording.

    ``AtaSpmSettings.credential_rows`` publishes no token, and this adds none.
    """
    return [list(one) for one in settings.credential_rows()]


def setting_rows(settings: Any) -> list:
    """One row per ATA-SPM setting a phase reads: its key, wording and value."""
    return [
        [key, label, str(getattr(settings, key, ""))] for key, label in SETTING_ROWS
    ]


def settings_page(board: Any) -> dict:
    """Every value the ATA-SPM settings page is drawn from, and its state."""
    return {
        "open": bool(board.settings_open),
        "settings_label": SETTINGS_LABEL,
        "settings_tooltip": SETTINGS_TOOLTIP,
        "settings_part": SETTINGS_PART,
        "save_label": SAVE_CREDENTIALS_LABEL,
        "save_tooltip": SAVE_CREDENTIALS_TOOLTIP,
        "save_part": SAVE_CREDENTIALS_PART,
        "setting_part": SETTING_FIELD_PART,
        "credential_fields": [list(one) for one in CREDENTIAL_FIELDS],
        "credential_rows": credential_rows(board.settings),
        "setting_rows": setting_rows(board.settings),
        "credential_width_px": CREDENTIAL_FIELD_WIDTH_PX,
        "setting_width_px": SETTING_FIELD_WIDTH_PX,
        "field_padding_px": list(FIELD_PADDING_PX),
        "field_border_px": FIELD_BORDER_PX,
        "field_height_px": FIELD_HEIGHT_PX,
        "button_height_px": PUSH_BUTTON_HEIGHT_PX,
        "settings_width_px": SETTINGS_WIDTH_PX,
        "label_width_px": SETTINGS_LABEL_WIDTH_PX,
        "row_spacing_px": SETTINGS_ROW_SPACING_PX,
    }


def bucket_skin(board: Any) -> dict:
    """Every value the Ready to Send buttons and the settings page are drawn from."""
    bucket = board.bucket
    return {
        "post_selected_label": POST_SELECTED_LABEL,
        "post_selected_tooltip": POST_SELECTED_TOOLTIP,
        "post_selected_part": POST_SELECTED_PART,
        "post_all_label": POST_ALL_LABEL,
        "post_all_tooltip": POST_ALL_TOOLTIP,
        "post_all_part": POST_ALL_PART,
        "full_auto_label": FULL_AUTO_LABEL,
        "full_auto_tooltip": FULL_AUTO_TOOLTIP,
        "full_auto_part": FULL_AUTO_PART,
        "button_height_px": PUSH_BUTTON_HEIGHT_PX,
        "post_selected_width_px": POST_SELECTED_WIDTH_PX,
        "post_all_width_px": POST_ALL_WIDTH_PX,
        "full_auto_width_px": FULL_AUTO_WIDTH_PX,
        "full_auto_on": bool(bucket.full_auto),
        "full_auto_text": bucket.full_auto_text(),
        "push_parts": list(PUSH_PARTS),
        "row_spacing_px": ATA_ROW_SPACING_PX,
        "summary": bucket.summary(),
        "counts": bucket.counts(),
        "records": bucket.record_lines(),
        "follow_ups": board.follow_up.lines(),
        "watching": len(board.follow_up.calls),
        "targets": list(ata_spm_push.TARGET_NAMES),
        "states": list(ata_spm_push.STATE_WORDS),
        "settings": settings_page(board),
    }


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


def right_zone_rows(run: Any, bucket: Any = None) -> list:
    """The three right-side zones as key, title and status, in screen order."""
    return [
        [
            READY_TO_SEND_ZONE,
            READY_TO_SEND_GROUP_TITLE,
            bucket_zone_text(bucket, run),
        ],
        [TOPOLOGIES_ZONE, TOPOLOGIES_GROUP_TITLE, NO_TEXT_LINE],
        [PHANTOM_HTF_ZONE, PHANTOM_HTF_GROUP_TITLE, PHANTOM_HTF_UNWIRED_TEXT],
    ]


def left_module_rows(
    run: Any,
    scan_state: Any,
    pair_count: Any,
    connectors: Any,
    sector_count: Any = 0,
) -> list:
    """The three left-side regions as key, title and status, in screen order."""
    return [
        [ATA_SPM_MODULE, ATA_SPM_GROUP_TITLE, ata_spm_zone_text(run, sector_count)],
        [
            OPPOSING_TRADES_MODULE,
            OPPOSING_TRADES_GROUP_TITLE,
            opposing_trades_text(scan_state, pair_count),
        ],
        [ARBITRAGE_MODULE, ARBITRAGE_GROUP_TITLE, arbitrage_text(connectors)],
    ]


def step_to(at: Any, total: Any, by: Any) -> int:
    """The entry index one arrow press moves to, wrapping at both ends."""
    count = int(total)
    if count <= 0:
        return 0
    return (int(at) + int(by)) % count


def position_text(at: Any, total: Any) -> str:
    """Which entry is on screen, out of how many the zone holds."""
    count = int(total)
    if count <= 0:
        return POSITION_EMPTY_TEXT
    return POSITION_FORMAT.format(at=int(at) + 1, total=count)


def method_line(method: Any) -> str:
    """One test as a single line: its name, its window and its statistic."""
    if not isinstance(method, dict) or not method.get("label"):
        return METHOD_LINE_NONE_TEXT
    return METHOD_LINE_FORMAT.format(
        label=method.get("label", ""),
        window=method.get("window", ""),
        statistic=method.get("statistic_text", ""),
    )


def detail_row(name: Any, value: Any) -> list:
    """One expanded line as its name and the text beside it."""
    return [name, DETAIL_FORMAT.format(name=name, value=value)]


def method_window_text(method: Any) -> str:
    """The window one test ran on, said in full rather than in bars."""
    window = str(method.get("window", ""))
    if window == LIVE_WINDOW_KEY:
        return DETAIL_WINDOW_LIVE_TEXT
    return DETAIL_WINDOW_BARS_FORMAT.format(observations=method.get("observations", 0))


def method_detail_rows(method: Any) -> list:
    """The expanded entry's lines: the test, the window, the result and why.

    Reads the verdict ``MethodResult.as_dict`` publishes, so the gate
    sentence is the one ``pair_selection`` writes rather than a second
    copy of the threshold.
    """
    if not isinstance(method, dict) or not method.get("label"):
        return [detail_row(DETAIL_REASON_NAME, NO_DETAIL_TEXT)]
    return [
        detail_row(
            DETAIL_TEST_NAME,
            DETAIL_TEST_FORMAT.format(
                label=method.get("label", ""), test=method.get("test", "")
            ),
        ),
        detail_row(DETAIL_WINDOW_NAME, method_window_text(method)),
        detail_row(DETAIL_RESULT_NAME, method.get("statistic_text", "")),
        detail_row(DETAIL_REASON_NAME, method.get("gate", NO_DETAIL_TEXT)),
    ]


def zone_entry(
    headline: Any,
    meta: Any = "",
    method: Any = None,
    detail: Any = None,
    method_text: Any = None,
    thumbnail: Any = None,
    preview: Any = None,
    actions: Any = None,
    vote: Any = None,
    headline_width_px: Any = None,
) -> dict:
    """One entry a zone steps through: its headline, its counts and its test.

    ``detail`` and ``method_text`` name the expanded lines and the method
    line outright, and ``thumbnail``, ``preview``, ``actions`` and ``vote``
    are the chart, the larger chart, the buttons and the bull or bear word
    a Ready to Send post carries.
    """
    return {
        "headline": headline,
        "meta": meta,
        "method": method,
        "detail": detail,
        "method_text": method_text,
        "thumbnail": thumbnail,
        "preview": preview,
        "actions": actions,
        "vote": vote,
        "headline_width_px": headline_width_px,
    }


def zone_view(
    key: Any, title: Any, entries: Any, at: Any, expanded: Any, empty_text: Any
) -> dict:
    """One zone as all three hosts draw it.

    A zone with no entries keeps its waiting sentence as the headline and
    still reports a position, so an empty zone reads as a state rather
    than as nothing drawn. An open entry drops the method line and the
    hint, which the four expanded lines already say, so every zone's open
    entry takes the same height whatever buttons it carries.
    """
    held = list(entries or [])
    total = len(held)
    shown = 0 if total == 0 else max(0, min(int(at), total - 1))
    entry = held[shown] if total else {}
    method = entry.get("method")
    own_detail = entry.get("detail")
    own_method_text = entry.get("method_text")
    open_now = bool(expanded) and total > 0
    lines = own_detail if own_detail is not None else method_detail_rows(method)
    written = own_method_text if own_method_text is not None else method_line(method)
    return {
        "key": key,
        "title": title,
        "total": total,
        "at": shown,
        "position": position_text(shown, total),
        "headline": entry.get("headline", "") if total else empty_text,
        "meta": entry.get("meta", "") if total else "",
        "method": "" if open_now else (written if total else ""),
        "hint": total > 0 and not open_now,
        "expanded": open_now,
        "detail": lines if open_now else [],
        "thumbnail": entry.get("thumbnail") if total else None,
        "preview": entry.get("preview") if open_now else None,
        "actions": (entry.get("actions") or []) if open_now else [],
        "vote": entry.get("vote") if total else None,
        "headline_width_px": entry.get("headline_width_px") if total else None,
    }


def stepper_skin() -> dict:
    """Every value the arrows, the position line and the entry are drawn from."""
    return {
        "back_text": STEP_BACK_TEXT,
        "next_text": STEP_NEXT_TEXT,
        "back_tooltip": STEP_BACK_TOOLTIP,
        "next_tooltip": STEP_NEXT_TOOLTIP,
        "button_width_px": STEP_BUTTON_WIDTH_PX,
        "button_style": STEP_BUTTON_STYLE,
        "push_padding_px": list(BUTTON_PADDING_PX),
        "push_font_weight": BUTTON_FONT_WEIGHT,
        "push_button_height_px": PUSH_BUTTON_HEIGHT_PX,
        "position_format": POSITION_FORMAT,
        "position_empty_text": POSITION_EMPTY_TEXT,
        "position_style": POSITION_STYLE,
        "entry_class": ENTRY_CLASS,
        "entry_accessible_name": ENTRY_ACCESSIBLE_NAME,
        "stepper_accessible_name": STEPPER_ACCESSIBLE_NAME,
        "entry_style": ENTRY_STYLE,
        "entry_margins_px": list(ENTRY_MARGINS_PX),
        "entry_spacing_px": ENTRY_SPACING_PX,
        "headline_style": ENTRY_HEADLINE_STYLE,
        "meta_style": ENTRY_META_STYLE,
        "method_style": ENTRY_METHOD_STYLE,
        "hint_text": ENTRY_HINT_TEXT,
        "hint_style": ENTRY_HINT_STYLE,
        "detail_style": DETAIL_STYLE,
        "detail_format": DETAIL_FORMAT,
        "method_line_format": METHOD_LINE_FORMAT,
        "method_line_none_text": METHOD_LINE_NONE_TEXT,
    }


def sector_assets(sector: Any, asset_class: Any) -> list:
    """The assets one named sector holds, read from the shipped sector map.

    Only ``ata_spm.CLASS_CRYPTO`` has a map in the tree, so every other
    class answers none and the zone names the source it waits for.
    """
    if str(asset_class) != ata_spm.CLASS_CRYPTO:
        return []
    from ...trading.topology_proposals import load_sector_map

    tag = str(sector).strip().lower()
    try:
        held = load_sector_map()
    except Exception as exc:  # noqa: BLE001 - the map is operator-editable
        logger.debug(SECTOR_MAP_FAILED_LOG, exc)
        return []
    return sorted(one for one, name in held.items() if str(name).lower() == tag)


def inspector_candles(inspector: Any, symbol: Any, timeframe: Any) -> list:
    """The candles the last universe scan kept for one symbol on one timeframe."""
    held = getattr(inspector, "last_candles", None) or {}
    return list((held.get(str(symbol)) or {}).get(str(timeframe)) or [])


def ata_spm_skin(model: Any) -> dict:
    """Every value the ATA-SPM control row is drawn from, and its state."""
    row = model.ata_row()
    return {
        "sector_placeholder": SECTOR_FIELD_PLACEHOLDER,
        "sector_tooltip": SECTOR_FIELD_TOOLTIP,
        "sector_min_width_px": SECTOR_FIELD_MIN_WIDTH_PX,
        "scan_label": SCAN_NOW_LABEL,
        "scan_tooltip": SCAN_NOW_TOOLTIP,
        "scan_width_px": SCAN_NOW_WIDTH_PX,
        "button_height_px": PUSH_BUTTON_HEIGHT_PX,
        "field_height_px": FIELD_HEIGHT_PX,
        "class_tooltip": CLASS_BOX_TOOLTIP,
        "class_width_px": CLASS_BOX_WIDTH_PX,
        "box_tooltip_format": TIMEFRAME_BOX_TOOLTIP_FORMAT,
        "box_width_px": TIMEFRAME_BOX_WIDTH_PX,
        "box_height_px": TIMEFRAME_BOX_HEIGHT_PX,
        "box_row_part": TIMEFRAME_ROW_PART,
        "row_spacing_px": ATA_ROW_SPACING_PX,
        "field_padding_px": list(FIELD_PADDING_PX),
        "field_border_px": FIELD_BORDER_PX,
        "check_indicator_px": CHECK_INDICATOR_PX,
        "check_label_spacing_px": CHECK_LABEL_SPACING_PX,
        "sector_text": row["sector_text"],
        "sector_class": row["sector_class"],
        "asset_classes": row["asset_classes"],
        "boxes": [list(one) for one in row["boxes"]],
        "sectors": [sector_row(one) for one in model.board.sectors],
        "timeframe_labels": dict(ata_spm.TIMEFRAME_LABELS),
        "crypto_timeframes": list(ata_spm.CRYPTO_TIMEFRAMES),
        "slower_timeframes": list(ata_spm.SLOWER_TIMEFRAMES),
        "no_sector_text": ATA_SPM_NO_SECTOR_TEXT,
    }


PAIR_HEADLINE_FORMAT = "{long}  ▸  {short}"
PAIR_META_FORMAT = "score {score}  •  correlation {correlation}"


def pair_entry(pair: Any) -> dict:
    """One opposing pair as the entry its zone steps through."""
    method = getattr(pair, "method", None)
    return zone_entry(
        PAIR_HEADLINE_FORMAT.format(
            long=PAIR_SIDE_FORMAT.format(
                symbol=pair.long_side.symbol, signal=pair.long_side.signal
            ),
            short=PAIR_SIDE_FORMAT.format(
                symbol=pair.short_side.symbol, signal=pair.short_side.signal
            ),
        ),
        PAIR_META_FORMAT.format(
            score=PAIR_SCORE_FORMAT.format(
                score=pair.long_side.score + pair.short_side.score
            ),
            correlation=CORRELATION_FORMAT.format(correlation=pair.correlation_30d),
        ),
        method.as_dict() if hasattr(method, "as_dict") else method,
    )


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
        self.ata_asset_source: Any = None
        self.ata_candle_source: Any = None
        self.board = ata_spm.SectorBoard()
        self.push = ata_spm_push.PushBoard()
        self.refresh_enabled = True
        self.status_label_text = STATUS_INITIAL_TEXT
        self.signal_rows: list = []
        self.pair_rows: list = []
        self.pairs: list = []
        self.zone_at: dict = {}
        self.zone_open: dict = {}
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
        self.pairs = rows
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

    def set_ata_sources(self, asset_source: Any, candle_source: Any) -> None:
        """Wire the assets a sector holds and the candles each one charts on."""
        self.ata_asset_source = asset_source
        self.ata_candle_source = candle_source
        self.calls.append([ATA_SOURCES_SET])

    def scanned_candles(self, symbol: Any, timeframe: Any) -> list:
        """The candles the last universe scan kept for one symbol and timeframe.

        An analyzer this screen cannot reach answers none, so the timeframe
        reads unread rather than raising into Scan Now.
        """
        try:
            return inspector_candles(self.inspector(), symbol, timeframe)
        except Exception as exc:  # noqa: BLE001 - the analyzer is process-wide
            logger.debug(CANDLE_READ_FAILED_LOG, symbol, timeframe, exc)
            return []

    def ata_report(self) -> Any:
        """The ATA-SPM zone's own run report, empty until a scan has run.

        The Ready to Send count comes off ``push.bucket``, which is what
        phase four filled.
        """
        held = self.board.report()
        if held:
            held[ATA_SPM_READY_KEY] = len(self.push.bucket.posts)
        return held

    def sector_at(self) -> Any:
        """The sector the ATA-SPM zone is showing, or None while it holds none."""
        return self.board.sector_at(self.zone_at.get(ATA_SPM_MODULE, 0))

    def set_sector_text(self, text: Any) -> None:
        """Take what the operator typed into the sector field."""
        self.board.set_text(text)
        self.calls.append([SECTOR_TEXT_SET, self.board.text])

    def set_sector_class(self, name: Any) -> None:
        """Take the asset class the sector field is naming."""
        at = self.zone_at.get(ATA_SPM_MODULE, 0)
        if not self.board.set_class(at, name):
            self.calls.append([SECTOR_CLASS_REFUSED, str(name or "")])
            return
        self.calls.append([SECTOR_CLASS_SET, self.board.asset_class])

    def toggle_timeframe(self, key: Any) -> None:
        """Tick or untick one timeframe box on the sector shown."""
        at = self.zone_at.get(ATA_SPM_MODULE, 0)
        if self.board.sector_at(at) is None:
            self.calls.append([TIMEFRAME_UNREACHABLE, str(key)])
            return
        ticked = self.board.toggle_timeframe(at, key)
        self.calls.append([TIMEFRAME_TOGGLED, str(key), ticked])

    def scan_now(self) -> Any:
        """Press Scan Now: add the typed sector if it is new, then run.

        Answers the ``ata_spm.AtaSpmRun`` the three phases produced, or
        None while the board names no sector.
        """
        added = self.board.scan_now(
            self.ata_asset_source or sector_assets,
            self.ata_candle_source or self.scanned_candles,
            self.push.settings.message_format,
        )
        if added != ata_spm.NO_NEW_SECTOR:
            self.zone_at[ATA_SPM_MODULE] = added
        if self.board.run is None:
            self.calls.append([SCAN_NOW_UNNAMED])
            return None
        self.push.load_run(self.board.run)
        self.push.after_scan(
            self.board.run, self.ata_candle_source or self.scanned_candles
        )
        self.zone_at[READY_TO_SEND_ZONE] = 0
        self.calls.append(
            [SCAN_NOW_RUN, len(self.board.sectors), len(self.board.run.calls)]
        )
        return self.board.run

    def bucket_at(self) -> int:
        """The zone index the Ready to Send stepper is showing."""
        return self.zone_at.get(READY_TO_SEND_ZONE, 0)

    def push_action(self, key: Any) -> Any:
        """Run one Ready to Send or settings press and answer what it did.

        ``key`` is the part name the button reported, and an unknown one
        answers None.
        """
        handled = {
            APPROVE_PART: lambda: self.push.bucket.approve(self.bucket_at()),
            DECLINE_PART: lambda: self.push.bucket.decline(self.bucket_at()),
            POST_SELECTED_PART: lambda: self.push.post_selected(self.bucket_at()),
            POST_ALL_PART: self.push.post_all,
            FULL_AUTO_PART: self._press_full_auto,
            SETTINGS_PART: self._press_settings,
            THUMBNAIL_PART: self._press_thumbnail,
        }.get(str(key))
        if handled is None:
            return None
        answered = handled()
        self.calls.append([PUSH_ACTION_SET, str(key)])
        return answered

    def _press_thumbnail(self) -> bool:
        """Open the Ready to Send expansion, so the larger chart is on screen."""
        self.zone_open[READY_TO_SEND_ZONE] = True
        self.calls.append([ZONE_TOGGLED, READY_TO_SEND_ZONE, True])
        return True

    def _press_full_auto(self) -> list:
        """Turn Send Bucket Full Auto on or off, and release while it is on."""
        self.push.bucket.toggle_full_auto()
        return self.push.release()

    def _press_settings(self) -> bool:
        """Show the ATA-SPM settings page, or the scan page, and answer which."""
        open_now = self.push.toggle_settings()
        self.calls.append([SETTINGS_PAGE_TOGGLED, open_now])
        return open_now

    def set_credential_text(self, target: Any, field: Any, typed: Any) -> None:
        """Hold what one credential field carries until Save reads it."""
        self.push.settings.set_credential_text(target, field, typed)

    def save_credentials(self) -> list:
        """Encrypt every typed credential into the vault and answer what landed."""
        stored = self.push.settings.save_credentials()
        for name in ata_spm_push.TARGET_NAMES:
            self.calls.append(
                [
                    CREDENTIAL_STORED if name in stored else CREDENTIAL_REFUSED,
                    str(name),
                ]
            )
        return stored

    def set_setting(self, key: Any, value: Any) -> Any:
        """Write one ATA-SPM setting and answer what the settings page now holds.

        A key in ``COUNT_SETTINGS`` takes a whole number, and text that is
        not one leaves the setting alone.
        """
        name = str(key)
        if name not in dict(SETTING_ROWS):
            return None
        if name in COUNT_SETTINGS:
            try:
                setattr(self.push.settings, name, int(str(value).strip() or 0))
            except ValueError:
                return getattr(self.push.settings, name)
        else:
            setattr(self.push.settings, name, str(value))
        held = getattr(self.push.settings, name)
        self.calls.append([SETTING_WRITTEN, name, held])
        return held

    def ata_entries(self) -> list:
        """The ATA-SPM zone's entries: one per sector the last run scanned.

        Each entry carries the phase seven outcomes the last check answered.
        """
        outcomes = self.push.follow_up.outcomes
        return self.board.entries(
            lambda scan, pulls: sector_entry(scan, pulls, outcomes)
        )

    def ata_row(self) -> dict:
        """Every value the sector field, the class box and the boxes are drawn from."""
        at = self.zone_at.get(ATA_SPM_MODULE, 0)
        sector = self.board.sector_at(at)
        return {
            "sector_text": self.board.text,
            "sector_class": self.board.asset_class,
            "asset_classes": list(ata_spm.ASSET_CLASSES),
            "boxes": self.board.boxes(at),
            "shown": sector_row(sector) if sector is not None else [],
        }

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
            self.ata_report(),
            self.scan_phase,
            len(self.pair_rows),
            self.connectors_now(),
            len(self.board.sectors),
        )

    def right_zones(self) -> list:
        """The three right-side zones, in the order the screen draws them."""
        return right_zone_rows(self.ata_run(), self.push.bucket)

    def zone_entries(self, key: Any) -> list:
        """The entries one zone steps through.

        ATA-SPM steps the sectors the last Scan Now covered, Opposing Trades
        the pairs the scan kept, and Ready to Send the posts phase four
        formatted.
        """
        if key == ATA_SPM_MODULE:
            return self.ata_entries()
        if key == OPPOSING_TRADES_MODULE:
            return [pair_entry(one) for one in self.pairs]
        if key == READY_TO_SEND_ZONE:
            return bucket_entries(self.push.bucket)
        return []

    def step_zone(self, key: Any, by: Any) -> int:
        """Move one zone to its previous or next entry and answer where it is."""
        total = len(self.zone_entries(key))
        moved = step_to(self.zone_at.get(key, 0), total, by)
        self.zone_at[key] = moved
        self.calls.append([ZONE_STEPPED, key, moved])
        return moved

    def toggle_zone(self, key: Any) -> bool:
        """Open or close one zone's expansion and answer whether it is open."""
        open_now = not self.zone_open.get(key, False)
        self.zone_open[key] = open_now
        self.calls.append([ZONE_TOGGLED, key, open_now])
        return open_now

    def zone_views(self) -> list:
        """All six zones as the stepper draws them, left three then right three."""
        rows = self.left_modules() + self.right_zones()
        return [
            zone_view(
                key,
                title,
                self.zone_entries(key),
                self.zone_at.get(key, 0),
                self.zone_open.get(key, False),
                status,
            )
            for key, title, status in rows
        ]

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
        "zones": [dict(one) for one in model.zone_views()],
        "stepper": stepper_skin(),
        "ata_spm": ata_spm_skin(model),
        "bucket": bucket_skin(model.push),
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
    ``bot_statuses``, ``sector_text``, ``sector_class``,
    ``toggle_timeframe``, ``scan_now``, ``step_zone``, ``toggle_zone``,
    ``render``, ``refresh``, ``force`` and
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
    if params.get("sector_text") is not None:
        model.set_sector_text(params["sector_text"])
    if params.get("sector_class") is not None:
        model.set_sector_class(params["sector_class"])
    if params.get("toggle_timeframe"):
        model.toggle_timeframe(params["toggle_timeframe"])
    if params.get("scan_now", False):
        model.scan_now()
    if params.get("push_action"):
        model.push_action(params["push_action"])
    if params.get("credential_text"):
        typed = list(params["credential_text"])
        model.set_credential_text(typed[0], typed[1], typed[2])
    if params.get("save_credentials", False):
        model.save_credentials()
    if params.get("set_setting"):
        asked = list(params["set_setting"])
        model.set_setting(asked[0], asked[1])
    if params.get("step_zone"):
        model.step_zone(params["step_zone"], params.get("step", 1))
    if params.get("toggle_zone"):
        model.toggle_zone(params["toggle_zone"])
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
