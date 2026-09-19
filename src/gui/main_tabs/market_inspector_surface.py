"""market_inspector_surface.py -- the Market Inspector screen, without Qt.

Describes the fleet-wide Market Inspector tab and the per-bot view the
Live Bot Settings window shows. The screen holds a Refresh button, an
"Include active markets" switch, a status line, the scored signal and
opposing-pair rows each scan holds, and a right pane carrying
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

import base64
import logging
import struct
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from ...core import encryption
from ...exchange.market_inspector_fetcher import DEFAULT_MIN_REFRESH_S, DEFAULT_QUOTES
from ...trading import (
    ata_asset_maps,
    ata_post_paths,
    ata_spm,
    ata_spm_push,
    ata_spm_signin,
)
from .. import design_system as ds
from . import indicator_panel_surface as ivp

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

SIGNAL_COLUMNS = ("Asset", "Signal", "Score", "Daily", "Weekly", "Active")

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
TICKER_FIELD_PLACEHOLDER = "Ticker"
TICKER_FIELD_TOOLTIP = (
    "Name one market to read on demand. Typing offers the tickers the "
    "sector menu beside it holds."
)
#: The ticker field takes the row's slack, so no other control's position
#: follows from the width its own text happens to take.
TICKER_FIELD_MIN_WIDTH_PX = 72

#: The most matches one typed value offers, so a one-letter entry cannot fill
#: the row with names.
TICKER_MATCH_LIMIT = 8
#: What one offer reads on the completer and the page's list: the symbol
#: and the class that lists it.
TICKER_OFFER_FORMAT = "{symbol}  ({asset_class})"
#: The characters a typed ticker may carry between its base and its quote.
TICKER_SEPARATORS = ("-", "_", " ")
TICKER_JOIN = "/"

#: What the field carries for a sector the tree lists no tickers for. The
#: field still takes a typed name.
TICKER_NO_LIST_FORMAT = "No ticker list for {sector}. A typed name still scans."
TICKER_FIELD_PART = "ticker-field"
TICKER_NOTE_PART = "ticker-note"
TICKER_MATCH_PART = "ticker-match"

#: The note's own colour and size, published so the window's style sheet and
#: the page's style read one source.
TICKER_NOTE_COLOUR = "#ccc"
TICKER_NOTE_SIZE_PX = 11
TICKER_NOTE_STYLE = f"color: {TICKER_NOTE_COLOUR}; font-size: {TICKER_NOTE_SIZE_PX}px;"
SCAN_NOW_LABEL = "Scan Now"
SCAN_NOW_TOOLTIP = (
    "Scan now on the timeframes ticked beside it, without waiting for a "
    "rotation. A ticker in the field reads that one market; an empty field "
    "reads the sector menu's markets, largest volume first, until Hits per "
    "scan markets pass the push gates."
)
CLASS_BOX_TOOLTIP = "The asset class this sector holds. It sets the four timeframes."
CLASS_BOX_WIDTH_PX = 92
TIMEFRAME_TITLE = "Timeframe"
TIMEFRAME_BOX_TOOLTIP_FORMAT = "Scan this sector on {label}."
TIMEFRAME_BOX_WIDTH_PX = 64

#: The four timeframe buttons together, which is one Qt ``QGridLayout`` and
#: one page row.
TIMEFRAME_ROW_PART = "timeframe-row"

#: The sector line and the two page buttons under the timeframes, named so a
#: reader can find either line on its own.
SECTOR_ROW_PART = "sector-row"
SCAN_ROW_PART = "scan-row"
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
UNLISTED_TAG = "unlisted"
UNSERVED_TAG = "unserved"
ORDER_TAG = "order"
PHASE_ROW_NAME_FORMAT = "{phase} {tag}"
CALL_TAG_FORMAT = "{symbol} {label}"
BAND_TAG_FORMAT = "{symbol} bands"
MESSAGE_ROW_NAME_FORMAT = "{symbol} {label}"
NO_CALL_TEXT = "No chart carried a reversal vote."
NO_CANDLE_TEXT = "No candles came back for {symbols}."
UNREAD_SYMBOL_CAP = 6
UNREAD_MORE_FORMAT = "{symbols} and {count} more"
METHOD_SENTENCE_JOIN = " "

#: The age past which a scan refetches rather than reading the universe scan's
#: candles; ``fetch_htf_universe`` serves its own cache over the same window.
CANDLES_FRESH_SECONDS = DEFAULT_MIN_REFRESH_S

#: The age ``inspector_scan_age`` answers when no universe scan has ever run.
NO_SCAN_AGE = float("inf")

#: The source name ``sector_candle_read`` answers for candles the universe
#: scan already holds.
CANDLES_FROM_SCAN = "universe scan"
#: The refusal ``sector_candle_read`` answers for a crypto name while no
#: exchange connector is in reach.
NO_CONNECTOR_TEXT = "no exchange connected"

#: The pins one Scan Now press leaves on the signal handler, in order;
#: ``ata_spm.HIT_PIN`` sits between the order and the end.
SCAN_PRESSED_PIN = "inspector.ata.scan_pressed"
SCAN_STARTED_PIN = "inspector.ata.scan_started"
VOLUME_ORDER_PIN = "inspector.ata.volume_order"
MARKET_READ_PIN = "inspector.ata.market_read"
SCAN_FINISHED_PIN = "inspector.ata.scan_finished"
#: The pin the running walk leaves every ``PROGRESS_PIN_EVERY`` markets and
#: at its end: class, read, total, hits.
SCAN_PROGRESS_PIN = "inspector.scan.progress"
PROGRESS_PIN_EVERY = 10
#: The pin one class list read leaves: class, source, count, dead.
LIST_SOURCE_PIN = "inspector.scan.list_source"

#: What ``class_markets`` names as the source of each class's order.
CRYPTO_ORDER_SOURCE_FORMAT = "24 h quote volume on {venues}"
CRYPTO_NO_CONNECTOR_SOURCE_TEXT = "name, no exchange connected for a volume figure"
CRYPTO_PUBLIC_SOURCE_TEXT = (
    "name on the coinbase public products list, no volume figure"
)
CRYPTO_NO_FIGURE_SOURCE_TEXT = "name, the exchange sent no volume figure"
VENUE_ORDER_SOURCE_FORMAT = "last complete daily bar volume x close on {venue}"
STOCKS_SCREENER_SOURCE_FORMAT = "{source}, {sectors} sector(s)"
STOCKS_PORTFOLIO_SOURCE_FORMAT = (
    "RA portfolio equities in map order, the screener refused: {refusal}"
)
ORDER_VENUE_JOIN = ", "
ORDER_LOG_FORMAT = "ATA-SPM order for {asset_class}: {line}"
VOLUME_FIGURE_REFUSED_LOG = "volume figure refused for %s: %s"

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
READY_TO_SEND_NONE_TEXT = "The last scan left no post. Nothing to approve."
READY_TO_SEND_HOLDS_FORMAT = "{count} post(s) waiting. Approve or decline each."
NO_POSTS = 0

# ── phases four, five and six: the bucket, its buttons and the settings ──

APPROVE_LABEL = "Approve"
DECLINE_LABEL = "Decline"
POST_SELECTED_LABEL = "Post Selected"
POST_ALL_LABEL = "Post All"
FULL_AUTO_LABEL = "Send Bucket Full Auto"
CHART_FOLDER_LABEL = "Chart Folder"
SETTINGS_LABEL = "Settings"

APPROVE_PART = "approve-button"
DECLINE_PART = "decline-button"
BUCKET_ROW_PART = "bucket-row"
POST_SELECTED_PART = "post-selected"
POST_ALL_PART = "post-all"
FULL_AUTO_PART = "full-auto"
CHART_FOLDER_PART = "chart-folder"
SETTINGS_PART = "settings-button"
SETTING_FIELD_PART = "setting-field"
THUMBNAIL_PART = "post-thumbnail"
CONNECT_PART = "connect-button"
BACK_PART = "back-button"
ZONES_PART = "zones-button"

#: Every press ``MarketInspectorScreenModel.push_action`` answers, which is
#: how the Electron host knows which key to send as one.
PUSH_PARTS = (
    APPROVE_PART,
    DECLINE_PART,
    POST_SELECTED_PART,
    POST_ALL_PART,
    FULL_AUTO_PART,
    CHART_FOLDER_PART,
    SETTINGS_PART,
    THUMBNAIL_PART,
    CONNECT_PART,
    BACK_PART,
    ZONES_PART,
)

#: Sized here rather than by their own text, so the Qt widget and the page
#: report one box.
PUSH_BUTTON_HEIGHT_PX = 36
FIELD_HEIGHT_PX = 37
APPROVE_WIDTH_PX = 100
DECLINE_WIDTH_PX = 92
#: One width for every Ready to Send button, so the Qt grid and the page's own
#: wrap break at the same count. It holds the longest label, Send Bucket Full
#: Auto.
BUCKET_BUTTON_WIDTH_PX = 184
SETTINGS_WIDTH_PX = 96
SCAN_NOW_WIDTH_PX = 108

#: Every credential box's part name, which is what a page reports back when
#: the operator types into one.
CREDENTIAL_FIELD_KEYS = ata_spm_push.CREDENTIAL_FIELD_KEYS

#: The two pages the ATA-SPM zone shows in place of its stepper. Level 1 is
#: the accounts, categories and settings; Level 1A is one venue's sign-in.
LEVEL_ONE = "level-1"
LEVEL_ONE_A = "level-1a"

SM_ACCOUNTS_TITLE = "SM Accounts"
ASSET_CATEGORY_TITLE = "Asset Category"
ATA_SETTINGS_TITLE = "Settings"

VENUE_BUTTON_PART = "venue-button"
ASSET_CATEGORY_PART = "asset-category"
CREDENTIAL_PAGE_PART = "credential-page"
CREDENTIAL_MESSAGE_PART = "credential-message"
SECTION_TITLE_PART = "section-title"
ENDPOINT_LINE_PART = "endpoint-line"
SCOPES_LINE_PART = "scopes-line"
REGISTRATION_LINE_PART = "registration-line"
SIGN_IN_LINE_PART = "sign-in-line"
REDIRECT_LINE_PART = "redirect-line"
PREREQUISITE_LINE_PART = "prerequisite-line"

VENUE_BUTTON_WIDTH_PX = 108
ASSET_CATEGORY_WIDTH_PX = 108
CONNECT_WIDTH_PX = 96
BACK_WIDTH_PX = 76

#: How many timeframe buttons the scan page puts on a line. The four fit the
#: zone at every width the window opens at, so this one count is a constant.
#: Level 1 and Level 1A take theirs from ``columns_for`` instead.
BUTTON_COLUMNS = 4


#: The pressed look every checkable button on this screen draws: a venue whose
#: credential is held, the asset class a scan uses, and a ticked timeframe.
#: The page paints the same two tokens through its ``data-scan-state`` rule,
#: so neither side leaves the state to the platform's own default.
CHECKED_BUTTON_STYLE = (
    f"QPushButton:checked{{background:{ds.PRIMARY};color:{ds.ON_PRIMARY};"
    f"border:1px solid {ds.PRIMARY};}}"
)

CONNECT_LABEL = "Connect"
BACK_LABEL = "Back"
VENUE_TOOLTIP_FORMAT = "{target} credentials · {state}"
CATEGORY_TOOLTIP_FORMAT = "Scan {name} sectors."
CONNECT_TOOLTIP = "Sign in to this venue and hold the credential in the vault."
BACK_TOOLTIP = "Leave this venue's page without signing in."
ZONES_TOOLTIP = "Leave the accounts page for the three scan zones."
ENDPOINT_LINE_FORMAT = "Posts to {endpoint}"
SCOPES_LINE_FORMAT = "Scopes {scopes}"
REGISTRATION_LINE_FORMAT = "Register first: {registration}"
SIGN_IN_LINE_FORMAT = "Connect opens your browser on {address}"
#: What a venue answering at its own desktop redirect carries instead. Its
#: sign-in opens inside the program, and no system browser is involved.
SIGN_IN_VIEW_LINE_FORMAT = "Connect opens a sign-in window in Acervator on {address}"
REDIRECT_LINE_FORMAT = "Redirect address to register: {redirect}"
PREREQUISITE_LINE_FORMAT = "Before it works: {prerequisite}"
SCOPE_SEPARATOR = " · "
NO_MESSAGE_TEXT = ""

APPROVE_TOOLTIP = "Approve this post so Post All and Full Auto release it."
DECLINE_TOOLTIP = "Decline this post. No button sends a declined post."
POST_SELECTED_TOOLTIP = "Send the post on screen, at no more than the configured rate."
POST_ALL_TOOLTIP = "Send every approved post, at no more than the configured rate."
FULL_AUTO_TOOLTIP = "Release approved posts without a click, at the configured rate."
CHART_FOLDER_TOOLTIP = (
    "Open the folder holding the chart images, in the system file browser. "
    "Each image carries the standardised message, so it can be posted by hand. "
    "One folder per venue holds that venue's own image and message text."
)
SETTINGS_TOOLTIP = "Show the ATA-SPM accounts page, or the scan page."
CREDENTIAL_FIELD_WIDTH_PX = 160
SETTING_FIELD_WIDTH_PX = 160
SETTINGS_ROW_SPACING_PX = 6
SETTINGS_LABEL_WIDTH_PX = 150


def grid_width(count: int, cell: int, spacing: int = SETTINGS_ROW_SPACING_PX) -> int:
    """How wide ``count`` cells of ``cell`` sit with ``spacing`` between them."""
    return count * cell + (count - 1) * spacing


def columns_for(
    available: int, cell: int, spacing: int = SETTINGS_ROW_SPACING_PX
) -> int:
    """How many ``cell`` wide cells a pane of ``available`` holds on one line.

    Every Level 1 and Level 1A group breaks at this count in both builds, and
    one ``spacing`` is left clear past the last cell so the Qt grid and the
    page's own ``calc(100% - gap)`` wrap at the same pane width.
    """
    step = cell + spacing
    if available < step:
        return 1
    return available // step


#: The scan page's timeframe buttons wrap after ``BUTTON_COLUMNS``, at the ATA
#: column's own spacing.
TIMEFRAME_GRID_WIDTH_PX = grid_width(
    BUTTON_COLUMNS, TIMEFRAME_BOX_WIDTH_PX, ATA_ROW_SPACING_PX
)
CREDENTIAL_ROW_WIDTH_PX = (
    SETTINGS_LABEL_WIDTH_PX + SETTINGS_ROW_SPACING_PX + CREDENTIAL_FIELD_WIDTH_PX
)
SETTING_ROW_WIDTH_PX = (
    SETTINGS_LABEL_WIDTH_PX + SETTINGS_ROW_SPACING_PX + SETTING_FIELD_WIDTH_PX
)

#: Every ATA-SPM setting a phase reads, with the wording its row carries.
SETTING_MAX_POSTS = "max_posts_per_hour"
SETTING_MAX_INDICATORS = "max_supporting_indicators"
SETTING_CONFIRMATION_SHARE = "confirmation_share_pct"
SETTING_MESSAGE_FORMAT = "message_format"
SETTING_HITS_PER_SCAN = "hits_per_scan"
SETTING_ROWS = (
    (SETTING_MAX_POSTS, "Max posts per hour"),
    (SETTING_MAX_INDICATORS, "Max supporting indicators"),
    (SETTING_CONFIRMATION_SHARE, "Confirmation share %"),
    (SETTING_MESSAGE_FORMAT, "Standardised message text"),
    (SETTING_HITS_PER_SCAN, "Hits per scan"),
)
COUNT_SETTINGS = (
    SETTING_MAX_POSTS,
    SETTING_MAX_INDICATORS,
    SETTING_CONFIRMATION_SHARE,
    SETTING_HITS_PER_SCAN,
)

#: The chart one bucket post carries, at its thumbnail and its larger size.
THUMBNAIL_WIDTH_PX = 120
THUMBNAIL_HEIGHT_PX = 36
PREVIEW_WIDTH_PX = 320
PREVIEW_HEIGHT_PX = 160

#: The PNG ``post_chart`` carries: a data address the page's ``img`` and the Qt
#: ``_PostChart`` both decode, and the header ``png_size`` reads the size from.
IMAGE_DATA_PREFIX = "data:image/png;base64,"
IMAGE_FORMAT = "PNG"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_SIZE_OFFSET = 16
PNG_SIZE_FORMAT = ">II"
NO_IMAGE_SIZE = (0, 0)
IMAGE_CACHE_ENTRIES = 64
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

#: The Indicator Voting Panel ATA-SMP carries, drawn inside an open entry.
PANEL_PART = "ata-voting-panel"
PANEL_CELL_PART = "ata-voting-cell"
PANEL_TABLE_ROW_PART = "ata-voting-row"
PANEL_GROUP_PART = "ata-voting-group"
PANEL_LINE_PART = "ata-voting-line"
PANEL_TF_WIDTH_PX = 44
PANEL_CELL_WIDTH_PX = 58
PANEL_NET_WIDTH_PX = 52
PANEL_CONF_WIDTH_PX = 96
PANEL_ROW_HEIGHT_PX = 18
PANEL_TABLE_GAP_PX = 6
PANEL_PLAIN_COLOR = "#cccccc"
PANEL_BOX_STYLE = "border: 1px solid #333;"
#: The tint's alpha is a percentage, which Qt and CSS read alike; a byte
#: alpha reads as a different colour on one of the two.
PANEL_CELL_STYLE_FORMAT = (
    "color: {color}; background-color: rgba({red}, {green}, {blue}, {alpha:.1f}%); "
    "font-size: 11px;"
)
PANEL_HEADER_STYLE_FORMAT = "color: {color}; font-size: 11px; font-weight: bold;"
PANEL_TITLE_FORMAT = "{symbol} {label}   {summary}"
PANEL_SUMMARY_FORMAT = "▲ {bullish}  ▼ {bearish}  ─ {neutral}"
PANEL_TOOLTIP_FORMAT = "The Indicator Voting Panel ATA-SMP read for {symbol}."

#: The gate chain result the same open entry draws beside the panel.
GATE_NAME = "Gate chain"
GATE_DISTANCE_TAG = "distance"
GATE_ROW_TAG_FORMAT = "{side} {name}"
GATE_ROW_FORMAT = "{state} {detail}"
GATE_COUNT_FORMAT = (
    "{ran} of {total} gate(s) ran · {latched} latched · {blocked} blocked "
    "· {stood_down} did not run"
)
GATE_DISTANCE_FORMAT = "opposing trade distance {pct:.2f}% · landing strip {strip}"
NO_GATE_TEXT = "No gate ran. The chart carried too few candles."
NO_STRIP_TEXT = "none"

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
CREDENTIAL_PAGE_OPENED = "credential.opened"
CREDENTIAL_PAGE_CLOSED = "credential.closed"
CREDENTIAL_PAGE_REFUSED = "credential.unknown_target"
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

LEFT_MODULE_KEYS = (ATA_SPM_MODULE, OPPOSING_TRADES_MODULE, ARBITRAGE_MODULE)
LEFT_MODULE_TITLES = (
    ATA_SPM_GROUP_TITLE,
    OPPOSING_TRADES_GROUP_TITLE,
    ARBITRAGE_GROUP_TITLE,
)
#: The share of the left pane's height each ``LEFT_MODULE_KEYS`` zone takes.
#: ATA-SPM takes two, so its control rows and its entry both stay in view.
LEFT_MODULE_SHARES = (2, 1, 1)

SPLITTER_ORIENTATION = "Horizontal"
SPLITTER_STRETCH = (1, 1)
SPLITTER_SIZES_PX = (800, 800)
SPLITTER_PANES = 2

#: The drag handle between the two panes. Both builds set it: the window calls
#: ``setHandleWidth`` and the page draws it as the split row's gap, so the two
#: panes are the same width in either build and a group wraps at the same count.
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

#: What Level 1A draws its message in. Every other line on that page is plain
#: body text, so a message in body text reads as more of the page's own prose.
MESSAGE_REFUSED_COLOUR = ds.ERROR
MESSAGE_ACCEPTED_COLOUR = ds.SUCCESS

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
CHART_FOLDER_OPENED_LOG = "ATA chart folder opened: %s"
CHART_FOLDER_FAILED_LOG = "ATA chart folder %s not opened: %s"
HANDLER_REFUSED_TEXT = "the operating system's handler refused"
CANDLE_READ_FAILED_LOG = "scanned candle read failed on %s %s: %s"
VOLUME_READ_FAILED_LOG = "quote volume read failed for %s: %s"
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
    "venue_pressed": "open_credentials",
    "credential_typed": "set_credential_text",
    "credential_held": "hold_credential",
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
SCAN_NOW_RUN = "scan_now.run"
SCAN_NOW_UNNAMED = "scan_now.unnamed"
SCAN_NOW_REFUSED = "scan_now.refused"
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
    SCAN_NOW_RUN,
    SCAN_NOW_UNNAMED,
    ZONE_STEPPED,
    ZONE_TOGGLED,
    PUSH_ACTION_SET,
    CREDENTIAL_STORED,
    CREDENTIAL_REFUSED,
    CREDENTIAL_PAGE_OPENED,
    CREDENTIAL_PAGE_CLOSED,
    CREDENTIAL_PAGE_REFUSED,
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


def ata_spm_zone_text(
    run: Any, sector_count: Any, note: Any = "", progress: Any = ""
) -> str:
    """The ATA-SPM zone's line for the run it holds and the scans added.

    A ``progress`` line of a running scan comes first, then a ``note`` the
    last press left, and a zone holding no scan reads ``ATA_SPM_NO_SECTOR_TEXT``.
    """
    if progress:
        return str(progress)
    if note:
        return str(note)
    if not int(sector_count or 0):
        return ATA_SPM_NO_SECTOR_TEXT
    return ata_spm_text(run)


def phase_row(phase: Any, tag: Any, value: Any) -> list:
    """One expanded line, named for the phase and the thing it reports on.

    The name carries ``tag`` so two rows of one phase never share a name.
    """
    return detail_row(PHASE_ROW_NAME_FORMAT.format(phase=phase, tag=tag), value)


def market_timeframe_reading(scan: Any, frame: Any) -> str:
    """One timeframe's verdict for a one-market scan: ``MARKET_HIT_READING``,
    ``MARKET_REFUSED_READING`` or ``MARKET_NO_VOTE_READING``."""
    vote = next((one for one in frame.votes if one.symbol == scan.ticker), None)
    if vote is None:
        return ata_spm.MARKET_NO_VOTE_READING
    if scan.hit_on(frame.timeframe) is not None:
        return ata_spm.MARKET_HIT_READING.format(direction=vote.direction_text)
    return ata_spm.MARKET_REFUSED_READING.format(direction=vote.direction_text)


def market_timeframe_rows(scan: Any) -> list:
    """One ``phase_row`` per timeframe of a one-market scan, carrying the
    candle count ``TimeframeScan.read`` holds and ``market_timeframe_reading``."""
    return [
        phase_row(
            PHASE_ONE_NAME,
            ata_spm.timeframe_label(frame.timeframe),
            ata_spm.MARKET_TIMEFRAME_FORMAT.format(
                candles=int(frame.read.get(scan.ticker, ata_spm.NO_CANDLES)),
                reading=market_timeframe_reading(scan, frame),
            ),
        )
        for frame in scan.timeframes
    ]


def phase_one_rows(scan: Any) -> list:
    """The expanded lines phase one leaves: one per timeframe scanned.

    ``scan.unlisted`` and ``scan.unserved`` each take a line of their own, so a
    venue gap never reads as a timeframe that voted nothing; a by-volume scan
    opens with ``ata_spm.order_line`` under ``ORDER_TAG``, and a one-market
    scan's rows come from ``market_timeframe_rows``.
    """
    if scan.note:
        rows = [detail_row(PHASE_NOTE_NAME, scan.note)]
    elif not scan.timeframes:
        rows = [detail_row(PHASE_NOTE_NAME, ata_spm.NO_TIMEFRAME_TEXT)]
    elif scan.ticker:
        rows = market_timeframe_rows(scan)
    else:
        rows = [
            phase_row(
                PHASE_ONE_NAME,
                ata_spm.timeframe_label(one.timeframe),
                ata_spm.TIMEFRAME_VOTE_FORMAT.format(
                    votes=len(one.votes),
                    unread=len(one.unread),
                    short=len(getattr(one, "short", ()) or ()),
                    floor=ata_spm.MIN_CANDLES_TO_VOTE,
                ),
            )
            for one in scan.timeframes
        ]
        if getattr(scan, "hit_target", ata_spm.NO_HIT_TARGET) > ata_spm.NO_HIT_TARGET:
            rows.insert(
                0,
                phase_row(
                    PHASE_ONE_NAME,
                    ORDER_TAG,
                    ata_spm.order_line(scan.order, scan.markets_read),
                ),
            )
    unlisted = tuple(getattr(scan, "unlisted", ()) or ())
    if unlisted and not scan.note:
        rows.append(
            phase_row(
                PHASE_ONE_NAME,
                UNLISTED_TAG,
                ata_spm.UNLISTED_TEXT.format(
                    symbols=ata_spm.SYMBOL_SEPARATOR.join(unlisted)
                ),
            )
        )
    unserved = tuple(getattr(scan, "unserved", ()) or ())
    if unserved:
        rows.append(
            phase_row(
                PHASE_ONE_NAME,
                UNSERVED_TAG,
                ata_spm.UNSERVED_TEXT.format(
                    labels=ata_spm.AGREEMENT_LABEL_SEPARATOR.join(
                        ata_spm.timeframe_label(one) for one in unserved
                    )
                ),
            )
        )
    return rows


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


def unread_symbols(scan: Any) -> tuple:
    """Every symbol one scan read no candles for, on every timeframe it ran.

    A symbol that voted on one timeframe is not named, so the sentence only
    carries the assets nothing at all came back for.
    """
    frames = list(getattr(scan, "timeframes", ()) or ())
    if not frames:
        return ()
    unread = set(frames[0].unread)
    for one in frames[1:]:
        unread &= set(one.unread)
    return tuple(sorted(unread))


def no_call_text(scan: Any) -> str:
    """The method line one sector with no reversal call carries.

    A scan that read no candles names the symbols outright rather than
    reporting a vote that never happened.
    """
    names = unread_symbols(scan)
    if not names:
        return NO_CALL_TEXT
    listed = ata_spm.SYMBOL_SEPARATOR.join(names[:UNREAD_SYMBOL_CAP])
    if len(names) > UNREAD_SYMBOL_CAP:
        listed = UNREAD_MORE_FORMAT.format(
            symbols=listed, count=len(names) - UNREAD_SYMBOL_CAP
        )
    missing = NO_CANDLE_TEXT.format(symbols=listed)
    if not scan.votes:
        return missing
    return METHOD_SENTENCE_JOIN.join((NO_CALL_TEXT, missing))


def entry_headline(scan: Any) -> str:
    """The line one scan's zone entry is named by: market, by-volume, map-order
    or sector; ``MarketOrder.by_volume`` tells the middle two apart."""
    if scan.ticker:
        return ata_spm.MARKET_LINE_FORMAT.format(
            ticker=scan.ticker, asset_class=scan.asset_class
        )
    if getattr(scan, "hit_target", ata_spm.NO_HIT_TARGET) > ata_spm.NO_HIT_TARGET:
        if scan.order.by_volume:
            return ata_spm.VOLUME_LINE_FORMAT.format(asset_class=scan.asset_class)
        return ata_spm.MAP_ORDER_LINE_FORMAT.format(asset_class=scan.asset_class)
    return ata_spm.SECTOR_LINE_FORMAT.format(
        sector=scan.sector, asset_class=scan.asset_class
    )


def entry_meta(scan: Any, calls: Any) -> str:
    """The counts one scan's zone entry carries: market, by-volume or sector.

    A by-volume scan counts the markets it read and says what stopped it,
    ``ata_spm.STOPPED_AT_TARGET_TEXT`` or ``ata_spm.SECTOR_EXHAUSTED_TEXT``.
    """
    if scan.ticker:
        return ata_spm.MARKET_META_FORMAT.format(
            venue=scan.venue or ata_spm.NO_VENUE_NAME,
            votes=len(scan.votes),
            hits=len(calls),
        )
    if getattr(scan, "hit_target", ata_spm.NO_HIT_TARGET) > ata_spm.NO_HIT_TARGET:
        return ata_spm.VOLUME_META_FORMAT.format(
            read=scan.markets_read,
            hits=len(calls),
            stop=(
                ata_spm.STOPPED_AT_TARGET_TEXT
                if scan.stopped_at_target
                else ata_spm.SECTOR_EXHAUSTED_TEXT
            ),
        )
    return ata_spm.SECTOR_META_FORMAT.format(
        assets=len(scan.assets), votes=len(scan.votes), calls=len(calls)
    )


def sector_entry(scan: Any, pulls: Any, follow_ups: Any = ()) -> dict:
    """One scan as the entry the ATA-SPM zone steps through.

    ``entry_headline`` and ``entry_meta`` say whether the scan read one market
    or a whole sector, and ``held`` narrows ``pulls`` to this scan's assets.
    """
    calls = scan.calls
    assets = set(scan.assets)
    held = [one for one in pulls if one.symbol in assets]
    strongest = calls[0] if calls else None
    return zone_entry(
        entry_headline(scan),
        entry_meta(scan, calls),
        detail=(
            phase_one_rows(scan)
            + phase_two_rows(calls)
            + phase_three_rows(held)
            + phase_seven_rows(follow_ups)
            + phase_eight_rows(scan, held)
        ),
        panels=[
            drawn for drawn in (voting_panel(one) for one in held) if drawn is not None
        ],
        method_text=(
            ata_spm.CALL_LINE_FORMAT.format(
                symbol=strongest.symbol,
                label=ata_spm.timeframe_label(strongest.timeframe),
                direction=strongest.direction_text,
            )
            if strongest is not None
            else scan.note or no_call_text(scan)
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


def png_size(raw: bytes) -> tuple:
    """The width and height a PNG header declares, or ``NO_IMAGE_SIZE``."""
    if not raw.startswith(PNG_SIGNATURE) or len(raw) < PNG_SIZE_OFFSET + 8:
        return NO_IMAGE_SIZE
    width, height = struct.unpack_from(PNG_SIZE_FORMAT, raw, PNG_SIZE_OFFSET)
    return (int(width), int(height))


@lru_cache(maxsize=IMAGE_CACHE_ENTRIES)
def _image_data(path: str, stamp: int, size: int) -> tuple:
    """The PNG at ``path`` as its data address and its size; ``stamp`` and
    ``size`` key the cache so a rewritten file is read again."""
    del stamp, size
    raw = Path(path).read_bytes()
    width, height = png_size(raw)
    if (width, height) == NO_IMAGE_SIZE:
        return ("", NO_IMAGE_SIZE)
    return (IMAGE_DATA_PREFIX + base64.b64encode(raw).decode("ascii"), (width, height))


def chart_image(path: Any) -> tuple:
    """The painter's PNG one post names, as a data address with its size.

    A post naming no file, or a file that is gone, answers an empty address
    and ``NO_IMAGE_SIZE``, and the entry draws its rectangle strip instead.
    """
    if not path:
        return ("", NO_IMAGE_SIZE)
    try:
        held = Path(str(path)).stat()
    except OSError:
        return ("", NO_IMAGE_SIZE)
    return _image_data(str(path), int(held.st_mtime_ns), int(held.st_size))


def scaled_height(width_px: Any, image_size: Any, fallback_px: Any) -> int:
    """The height ``width_px`` takes at the image's own aspect, or the fallback."""
    width, height = image_size
    if width <= 0 or height <= 0:
        return int(fallback_px)
    return max(1, int(round(int(width_px) * height / width)))


def post_chart(post: Any, wide: Any = False) -> dict:
    """The chart one bucket post carries, as its thumbnail or its larger view.

    ``wide`` picks ``PREVIEW_WIDTH_PX`` over ``THUMBNAIL_WIDTH_PX``. ``image``
    is the painter's PNG the post's ``image_path`` names, which both hosts
    draw at the box's width; ``chart_marks`` answers the rectangles drawn
    while the post names no file.
    """
    width_px = PREVIEW_WIDTH_PX if wide else THUMBNAIL_WIDTH_PX
    image, image_size = chart_image(getattr(post, "image_path", ""))
    height_px = scaled_height(
        width_px, image_size, PREVIEW_HEIGHT_PX if wide else THUMBNAIL_HEIGHT_PX
    )
    columns = PREVIEW_COLUMNS if wide else THUMBNAIL_COLUMNS
    return {
        "part": PREVIEW_PART if wide else THUMBNAIL_PART,
        "width_px": width_px,
        "height_px": height_px,
        "image": image,
        "image_path": str(getattr(post, "image_path", "") or ""),
        "image_width_px": image_size[0],
        "image_height_px": image_size[1],
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


def panel_cell(width: Any, text: Any, style: Any, tooltip: Any = "") -> list:
    """One Indicator Voting Panel cell: its width, its text and its style."""
    return [PANEL_CELL_PART, int(width), str(text), str(style), str(tooltip)]


def panel_row(cells: Any, height_px: Any = None) -> list:
    """One panel row: how tall it is, and the cells across it."""
    return [
        int(PANEL_ROW_HEIGHT_PX if height_px is None else height_px),
        list(cells),
    ]


def panel_column_widths(subset: Any, aggregates: Any) -> list:
    """One table's column widths, the TF column first."""
    widths = [PANEL_TF_WIDTH_PX] + [PANEL_CELL_WIDTH_PX] * len(list(subset))
    if aggregates:
        widths += [PANEL_NET_WIDTH_PX, PANEL_NET_WIDTH_PX, PANEL_CONF_WIDTH_PX]
    return widths


def panel_cell_style(colors: Any) -> str:
    """One indicator cell's style, from ``indicator_cell_colors``."""
    red, green, blue = list(colors["fill_rgb"])
    return PANEL_CELL_STYLE_FORMAT.format(
        color=colors["text_color"],
        red=red,
        green=green,
        blue=blue,
        alpha=colors["fill_alpha"] / ivp.ALPHA_SCALE * ivp.PERCENT_SCALE,
    )


def panel_header_row(subset: Any, aggregates: Any) -> list:
    """One table's header row: the TF column, its voters and its aggregates."""
    widths = panel_column_widths(subset, aggregates)
    titles = ivp.column_titles(list(subset))[: 1 + len(list(subset))]
    if aggregates:
        titles = titles + list(ivp.AGGREGATE_TITLES)
    groups = [""] + [one[2] for one in subset] + [""] * (len(widths) - len(subset) - 1)
    return panel_row(
        [
            panel_cell(
                widths[at],
                title,
                PANEL_HEADER_STYLE_FORMAT.format(
                    color=ivp.GROUP_COLORS.get(groups[at], PANEL_PLAIN_COLOR)
                ),
            )
            for at, title in enumerate(titles)
        ]
    )


def panel_aggregate_cells(row: Any, widths: Any, first: Any) -> list:
    """The Net, Comp and Conf cells one table row closes with."""
    cells: list = []
    for at, built in enumerate((ivp.net_cell, ivp.comp_cell, ivp.conf_cell)):
        written = built(row)
        cells.append(
            panel_cell(
                widths[first + at],
                written["text"],
                PANEL_HEADER_STYLE_FORMAT.format(
                    color=written["text_color"] or PANEL_PLAIN_COLOR
                ),
            )
        )
    return cells


def panel_timeframe_row(row: Any, timeframe: Any, subset: Any, aggregates: Any) -> list:
    """One timeframe's row across one table, the TF name first."""
    widths = panel_column_widths(subset, aggregates)
    signals = ivp.signals_by_indicator(row)
    cells = [
        panel_cell(
            widths[0],
            str(timeframe),
            PANEL_HEADER_STYLE_FORMAT.format(color=PANEL_PLAIN_COLOR),
        )
    ]
    for at, (key, _label, _group) in enumerate(subset):
        signal = signals.get(key)
        cells.append(
            panel_cell(
                widths[at + 1],
                ivp.indicator_cell_text(key, signal),
                panel_cell_style(ivp.indicator_cell_colors(signal)),
                ivp.indicator_cell_tooltip(key, signal),
            )
        )
    if aggregates:
        cells.extend(panel_aggregate_cells(row, widths, len(list(subset)) + 1))
    return panel_row(cells)


def panel_table(rows: Any, subset: Any, aggregates: Any) -> list:
    """One table: its header row, then one row per timeframe scanned."""
    built = [panel_header_row(subset, aggregates)]
    built.extend(
        panel_timeframe_row(rows[timeframe], timeframe, subset, aggregates)
        for timeframe in ivp.ordered_timeframes(rows)
    )
    return built


def panel_tally(row: Any, key: Any) -> int:
    """One vote count off a panel row, or zero while the row carries none."""
    try:
        return int(float((row or {}).get(str(key)) or 0))
    except (AttributeError, TypeError, ValueError):
        return 0


def panel_summary_text(rows: Any) -> str:
    """The vote tally beside a voting panel title, summed over its timeframes."""
    return PANEL_SUMMARY_FORMAT.format(
        bullish=sum(panel_tally(one, "bullish") for one in (rows or {}).values()),
        bearish=sum(panel_tally(one, "bearish") for one in (rows or {}).values()),
        neutral=sum(panel_tally(one, "neutral") for one in (rows or {}).values()),
    )


def voting_panel(pull: Any) -> Optional[dict]:
    """The Indicator Voting Panel one scanned asset carries, as its rows.

    The rows are the timeframes ATA-SMP read for this asset alone, and
    every cell is drawn from ``indicator_panel_surface``.
    """
    rows = dict(getattr(pull, "panel", None) or {})
    if not rows:
        return None
    width = sum(panel_column_widths(ivp.ROW_A_INDICATOR_COLS, True))
    title = panel_row(
        [
            panel_cell(
                width,
                PANEL_TITLE_FORMAT.format(
                    symbol=pull.symbol,
                    label=ata_spm.timeframe_label(pull.timeframe),
                    summary=panel_summary_text(rows),
                ),
                PANEL_HEADER_STYLE_FORMAT.format(color=PANEL_PLAIN_COLOR),
            )
        ]
    )
    gap = panel_row([], PANEL_TABLE_GAP_PX)
    built = (
        [title]
        + panel_table(rows, ivp.ROW_A_INDICATOR_COLS, True)
        + [gap]
        + panel_table(rows, ivp.ROW_B_INDICATOR_COLS, False)
    )
    return {
        "part": PANEL_PART,
        "width_px": width,
        "height_px": sum(one[0] for one in built),
        "cell_part": PANEL_CELL_PART,
        "row_part": PANEL_TABLE_ROW_PART,
        "group_part": PANEL_GROUP_PART,
        "line_part": PANEL_LINE_PART,
        "box_style": PANEL_BOX_STYLE,
        "line_style": DETAIL_STYLE,
        "rows": built,
        "lines": gate_rows(pull),
        "symbol": pull.symbol,
        "tooltip": PANEL_TOOLTIP_FORMAT.format(symbol=pull.symbol),
    }


def gate_rows(pull: Any) -> list:
    """The expanded lines the gate chain leaves for one scanned asset.

    Every gate of both chains is named, and a gate that did not run says
    which state ``ata_gate_scan`` stood it down in.
    """
    scan = getattr(pull, "gates", None)
    tag = CALL_TAG_FORMAT.format(
        symbol=pull.symbol, label=ata_spm.timeframe_label(pull.timeframe)
    )
    if scan is None or not scan.readings:
        return [phase_row(GATE_NAME, tag, NO_GATE_TEXT)]
    rows = [
        phase_row(
            GATE_NAME,
            tag,
            GATE_COUNT_FORMAT.format(
                ran=scan.ran,
                total=len(scan.readings),
                latched=len(scan.latched),
                blocked=len(scan.blocked),
                stood_down=len(scan.not_run),
            ),
        ),
        phase_row(
            GATE_NAME,
            GATE_DISTANCE_TAG,
            GATE_DISTANCE_FORMAT.format(
                pct=pull.otd_pct, strip=pull.landing_strip_side or NO_STRIP_TEXT
            ),
        ),
    ]
    rows.extend(
        phase_row(
            GATE_NAME,
            GATE_ROW_TAG_FORMAT.format(side=one.side, name=one.name),
            GATE_ROW_FORMAT.format(state=one.state, detail=one.detail).strip(),
        )
        for one in scan.readings
    )
    return rows


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

    Line zero is the header the post's ``PushTarget`` row carries, which every
    artefact of the post composes.
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


def category_rows(asset_class: Any) -> list:
    """One row per ``ata_spm.ASSET_CLASSES`` name, and whether a scan uses it now."""
    return [[one, one == str(asset_class)] for one in ata_spm.ASSET_CLASSES]


#: A word of a Level 1A line becomes a link only where it names a host and a
#: path. ``video.publish`` carries a dot and no path, and ``/api/submit`` a path
#: and no host, so neither is one.
LINK_SCHEMES = ("https://", "http://")
LINK_DEFAULT_SCHEME = "https://"
LINK_TRAILING = ".,;:)]}"
LINK_TOP_LABEL_MIN = 2
LINK_SPACE = " "
PATH_MARK = "/"
LABEL_MARK = "."
NO_LINK = ""

#: The colour both builds draw a Level 1A link in.
LINK_COLOUR = ds.PRIMARY

#: The part name a Level 1A link reports its press under.
CREDENTIAL_LINK_PART = "credential-link"

#: The ``credential_page`` values drawn as link segments. Each is a fixed text
#: on the venue's own ``ata_spm_push.PushTarget`` row; nothing typed and nothing
#: a venue answered is on this list.
#: The ``credential_page`` list naming which boxes the vault already holds a
#: value for. It carries ``CredentialField`` keys and never a value.
PAGE_HELD_FIELDS = "held_fields"

#: The wording a box whose value the vault holds draws instead of its label.
CREDENTIAL_HELD_PLACEHOLDER = "Held · type to replace"

#: The part name a finished credential box reports itself under.
CREDENTIAL_HELD_PART = "credential-held"

PAGE_ENDPOINT_LINKS = "endpoint_links"
PAGE_REGISTRATION_LINKS = "registration_links"
PAGE_PREREQUISITE_LINKS = "prerequisite_links"
CREDENTIAL_LINK_KEYS = (
    PAGE_ENDPOINT_LINKS,
    PAGE_REGISTRATION_LINKS,
    PAGE_PREREQUISITE_LINKS,
)


def link_address(word: Any) -> str:
    """The whole address one word of a Level 1A line carries, or an empty string.

    A word naming a path and no host is not an address, and neither is a word
    carrying a dot and no path.
    """
    held = str(word).rstrip(LINK_TRAILING)
    if held.startswith(LINK_SCHEMES):
        return held
    if PATH_MARK not in held:
        return NO_LINK
    labels = held.split(PATH_MARK, 1)[0].split(LABEL_MARK)
    if len(labels) < 2 or not all(labels):
        return NO_LINK
    top = labels[-1]
    if len(top) < LINK_TOP_LABEL_MIN or not top.isalpha():
        return NO_LINK
    return LINK_DEFAULT_SCHEME + held


def link_segments(text: Any) -> list:
    """One Level 1A line as ``[words, address]`` pairs, the address empty where plain.

    Both builds draw a line from this, so a word is a link on the page exactly
    where it is a link in the window.
    """
    held: list = []
    for at, word in enumerate(str(text).split(LINK_SPACE)):
        if at:
            held.append([LINK_SPACE, NO_LINK])
        address = link_address(word)
        if not address:
            held.append([word, NO_LINK])
            continue
        bare = word.rstrip(LINK_TRAILING)
        held.append([bare, address])
        if len(bare) < len(word):
            held.append([word[len(bare) :], NO_LINK])
    if not any(one[1] for one in held):
        return [[str(text), NO_LINK]]
    return held


def page_links(board: Any) -> list:
    """Every address the open Level 1A page publishes, and nothing else.

    A host opens an address only where it is on this list, so a page reporting
    one the venue's own ``PushTarget`` row does not carry opens nothing.
    """
    page = credential_page(board)
    held: list = []
    for key in CREDENTIAL_LINK_KEYS:
        for _chunk, address in page.get(key) or []:
            if address and address not in held:
                held.append(address)
    return held


def sign_in_line(target: Any) -> str:
    """The wording one push target's Level 1A page carries for where Connect sends him.

    ``ata_spm_signin.redirects_to_view`` is what says whether the sign-in opens
    in the system browser or in the view the program draws.
    """
    address = ata_spm_signin.authorize_address(target)
    if ata_spm_signin.redirects_to_view(target):
        return SIGN_IN_VIEW_LINE_FORMAT.format(address=address)
    return SIGN_IN_LINE_FORMAT.format(address=address)


def message_colour(answered: Any) -> str:
    """The colour Level 1A draws one ``ConnectResult`` in.

    Both builds read this one value, so ``MESSAGE_REFUSED_COLOUR`` cannot reach
    one page and body text the other.
    """
    if answered is None:
        return NO_COLOR
    return MESSAGE_ACCEPTED_COLOUR if answered.ok else MESSAGE_REFUSED_COLOUR


def credential_page(board: Any) -> dict:
    """Every value one push target's Level 1A page is drawn from.

    ``target`` is empty while Level 1 is the page, and ``message`` carries
    what the last ``PushBoard.connect_credentials`` answered.
    """
    found = ata_spm_push.push_target(board.credential_target)
    answered = board.connect_result
    if found is None:
        return {
            "target": NO_SYMBOL,
            "fields": [],
            "endpoint": NO_SYMBOL,
            "scopes": NO_SYMBOL,
            "sign_in": NO_SYMBOL,
            "redirect": NO_SYMBOL,
            "registration": NO_SYMBOL,
            "prerequisite": NO_SYMBOL,
            PAGE_HELD_FIELDS: [],
            PAGE_ENDPOINT_LINKS: [],
            PAGE_REGISTRATION_LINKS: [],
            PAGE_PREREQUISITE_LINKS: [],
            "message": NO_MESSAGE_TEXT,
            "message_colour": NO_COLOR,
            "ok": False,
        }
    return {
        "target": found.name,
        "fields": [[one.key, one.label] for one in found.fields],
        PAGE_HELD_FIELDS: list(board.settings.held_fields(found.name)),
        "endpoint": ENDPOINT_LINE_FORMAT.format(endpoint=found.endpoint),
        "scopes": SCOPES_LINE_FORMAT.format(scopes=SCOPE_SEPARATOR.join(found.scopes)),
        "sign_in": sign_in_line(found.name),
        "redirect": REDIRECT_LINE_FORMAT.format(
            redirect=ata_spm_signin.registered_redirect(found.name)
        ),
        "registration": REGISTRATION_LINE_FORMAT.format(
            registration=found.registration
        ),
        "prerequisite": PREREQUISITE_LINE_FORMAT.format(
            prerequisite=found.prerequisite
        ),
        PAGE_ENDPOINT_LINKS: link_segments(
            ENDPOINT_LINE_FORMAT.format(endpoint=found.endpoint)
        ),
        PAGE_REGISTRATION_LINKS: link_segments(
            REGISTRATION_LINE_FORMAT.format(registration=found.registration)
        ),
        PAGE_PREREQUISITE_LINKS: link_segments(
            PREREQUISITE_LINE_FORMAT.format(prerequisite=found.prerequisite)
        ),
        "message": NO_MESSAGE_TEXT if answered is None else str(answered.detail),
        "message_colour": message_colour(answered),
        "ok": bool(answered is not None and answered.ok),
    }


def settings_page(board: Any, asset_class: Any = "") -> dict:
    """Every value Level 1 and Level 1A are drawn from, and which one shows."""
    return {
        "open": bool(board.settings_open),
        "level": LEVEL_ONE_A if board.credential_target else LEVEL_ONE,
        "settings_label": SETTINGS_LABEL,
        "settings_tooltip": SETTINGS_TOOLTIP,
        "settings_part": SETTINGS_PART,
        "setting_part": SETTING_FIELD_PART,
        "venue_part": VENUE_BUTTON_PART,
        "category_part": ASSET_CATEGORY_PART,
        "connect_part": CONNECT_PART,
        "back_part": BACK_PART,
        "zones_part": ZONES_PART,
        "zones_tooltip": ZONES_TOOLTIP,
        "page_part": CREDENTIAL_PAGE_PART,
        "message_part": CREDENTIAL_MESSAGE_PART,
        "title_part": SECTION_TITLE_PART,
        "endpoint_part": ENDPOINT_LINE_PART,
        "scopes_part": SCOPES_LINE_PART,
        "sign_in_part": SIGN_IN_LINE_PART,
        "redirect_part": REDIRECT_LINE_PART,
        "registration_part": REGISTRATION_LINE_PART,
        "prerequisite_part": PREREQUISITE_LINE_PART,
        "link_part": CREDENTIAL_LINK_PART,
        "link_colour": LINK_COLOUR,
        "held_part": CREDENTIAL_HELD_PART,
        "held_placeholder": CREDENTIAL_HELD_PLACEHOLDER,
        "accounts_title": SM_ACCOUNTS_TITLE,
        "category_title": ASSET_CATEGORY_TITLE,
        "settings_title": ATA_SETTINGS_TITLE,
        "connect_label": CONNECT_LABEL,
        "connect_tooltip": CONNECT_TOOLTIP,
        "back_label": BACK_LABEL,
        "back_tooltip": BACK_TOOLTIP,
        "venue_tooltip_format": VENUE_TOOLTIP_FORMAT,
        "category_tooltip_format": CATEGORY_TOOLTIP_FORMAT,
        "credential_rows": credential_rows(board.settings),
        "category_rows": category_rows(asset_class),
        "setting_rows": setting_rows(board.settings),
        "credential": credential_page(board),
        "credential_width_px": CREDENTIAL_FIELD_WIDTH_PX,
        "setting_width_px": SETTING_FIELD_WIDTH_PX,
        "venue_width_px": VENUE_BUTTON_WIDTH_PX,
        "category_width_px": ASSET_CATEGORY_WIDTH_PX,
        "connect_width_px": CONNECT_WIDTH_PX,
        "back_width_px": BACK_WIDTH_PX,
        "credential_row_width_px": CREDENTIAL_ROW_WIDTH_PX,
        "setting_row_width_px": SETTING_ROW_WIDTH_PX,
        "field_padding_px": list(FIELD_PADDING_PX),
        "field_border_px": FIELD_BORDER_PX,
        "field_height_px": FIELD_HEIGHT_PX,
        "button_height_px": PUSH_BUTTON_HEIGHT_PX,
        "settings_width_px": SETTINGS_WIDTH_PX,
        "label_width_px": SETTINGS_LABEL_WIDTH_PX,
        "row_spacing_px": SETTINGS_ROW_SPACING_PX,
    }


def bucket_skin(board: Any, asset_class: Any = "") -> dict:
    """Every value the Ready to Send buttons and the two account pages draw from."""
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
        "chart_folder_label": CHART_FOLDER_LABEL,
        "chart_folder_tooltip": CHART_FOLDER_TOOLTIP,
        "chart_folder_part": CHART_FOLDER_PART,
        "button_height_px": PUSH_BUTTON_HEIGHT_PX,
        "bucket_button_width_px": BUCKET_BUTTON_WIDTH_PX,
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
        "settings": settings_page(board, asset_class),
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
    if int(count) == NO_POSTS:
        return READY_TO_SEND_NONE_TEXT
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
    ata_note: Any = "",
    ata_progress: Any = "",
) -> list:
    """The three left-side regions as key, title and status, in screen order."""
    return [
        [
            ATA_SPM_MODULE,
            ATA_SPM_GROUP_TITLE,
            ata_spm_zone_text(run, sector_count, ata_note, ata_progress),
        ],
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
    panels: Any = None,
) -> dict:
    """One entry a zone steps through: its headline, its counts and its test.

    ``detail`` and ``method_text`` name the expanded lines and the method
    line outright, ``thumbnail``, ``preview``, ``actions`` and ``vote``
    are what a Ready to Send post carries, and ``panels`` are the
    ``voting_panel`` grids an open ATA-SMP entry draws.
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
        "panels": panels,
    }


def zone_view(
    key: Any,
    title: Any,
    entries: Any,
    at: Any,
    expanded: Any,
    empty_text: Any,
    running: Any = "",
) -> dict:
    """One zone as all three hosts draw it.

    A zone with no entries keeps its waiting sentence as the headline and
    still reports a position, so an empty zone reads as a state rather
    than as nothing drawn. An open entry drops the method line and the
    hint, which the four expanded lines already say, so every zone's open
    entry takes the same height whatever buttons it carries. A ``running``
    line is the headline while a scan runs, with no meta and no method.
    """
    held = list(entries or [])
    total = len(held)
    shown = 0 if total == 0 else max(0, min(int(at), total - 1))
    entry = held[shown] if total else {}
    method = entry.get("method")
    own_detail = entry.get("detail")
    own_method_text = entry.get("method_text")
    busy = bool(running)
    open_now = bool(expanded) and total > 0 and not busy
    lines = own_detail if own_detail is not None else method_detail_rows(method)
    written = own_method_text if own_method_text is not None else method_line(method)
    return {
        "key": key,
        "title": title,
        "total": total,
        "at": shown,
        "position": position_text(shown, total),
        "headline": (
            str(running)
            if busy
            else (entry.get("headline", "") if total else empty_text)
        ),
        "meta": entry.get("meta", "") if total and not busy else "",
        "method": "" if open_now or busy else (written if total else ""),
        "hint": total > 0 and not open_now and not busy,
        "expanded": open_now,
        "detail": lines if open_now else [],
        "thumbnail": entry.get("thumbnail") if total else None,
        "preview": entry.get("preview") if open_now else None,
        "actions": (entry.get("actions") or []) if open_now else [],
        "vote": entry.get("vote") if total else None,
        "headline_width_px": entry.get("headline_width_px") if total else None,
        "panels": (entry.get("panels") or []) if open_now else [],
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
    """The ``ata_asset_maps.AssetListing`` rows one named sector holds.

    ``ata_spm.CLASS_CRYPTO`` reads the shipped sector map and charts off the
    Market Inspector universe scan; every other class reads ``MAPS``.
    """
    if str(asset_class) != ata_spm.CLASS_CRYPTO:
        return list(ata_asset_maps.listings_for(sector, asset_class))
    from ...trading.topology_proposals import load_sector_map

    tag = str(sector).strip().lower()
    try:
        held = load_sector_map()
    except Exception as exc:  # noqa: BLE001 - the map is operator-editable
        logger.debug(SECTOR_MAP_FAILED_LOG, exc)
        return []
    return [
        ata_asset_maps.exchange_listing(one)
        for one in sorted(
            name for name, tag_of in held.items() if str(tag_of).lower() == tag
        )
    ]


def class_tickers(asset_class: Any) -> list:
    """Every ticker one sector names, read from the lists already in this tree.

    ``ata_spm.CLASS_CRYPTO`` reads the shipped sector map and every other class
    reads ``ata_asset_maps.MAPS``, so no venue is asked for a symbol.
    """
    if str(asset_class) == ata_spm.CLASS_CRYPTO:
        from ...trading.topology_proposals import load_sector_map

        try:
            held = load_sector_map()
        except Exception as exc:  # noqa: BLE001 - the map is operator-editable
            logger.debug(SECTOR_MAP_FAILED_LOG, exc)
            return []
        return sorted(str(one) for one in held)
    found = {
        str(one.symbol)
        for sector in ata_asset_maps.sectors_for(asset_class)
        for one in ata_asset_maps.listings_for(sector, asset_class)
    }
    return sorted(found)


def class_volumes(asset_class: Any, connectors: Any) -> dict:
    """The 24 h quote volume per crypto symbol, read through the fetcher.

    ``fetch_quote_volumes`` serves the figures the Refresh press already read
    inside its cache window; every other class, and no connector, answer none.
    """
    if str(asset_class) != ata_spm.CLASS_CRYPTO or not connectors:
        return {}
    import asyncio

    from ...exchange.market_inspector_fetcher import fetch_quote_volumes

    try:
        return dict(asyncio.run(fetch_quote_volumes(connectors)) or {})
    except Exception as exc:  # noqa: BLE001 - the source is off-process
        logger.debug(VOLUME_READ_FAILED_LOG, asset_class, exc)
        return {}


def listing_volumes(rows: Any) -> dict:
    """Each listed and ``volumed`` row's ``venue_quote_volume`` figure by symbol.

    A row the venue refused, and one whose figure is ``NO_VOLUME_FIGURE``,
    leave the dict, so the caller counts them as unfigured.
    """
    found: dict = {}
    for one in rows:
        if not (one.listed and one.volumed):
            continue
        figure, refusal = ata_asset_maps.venue_quote_volume(one.symbol)
        if refusal:
            logger.debug(VOLUME_FIGURE_REFUSED_LOG, one.symbol, refusal)
            continue
        if figure > ata_asset_maps.NO_VOLUME_FIGURE:
            found[str(one.symbol)] = float(figure)
    return found


def ranked_order(
    rows: Any,
    figures: dict,
    source: Any,
    bare_source: Any = ata_spm.MAP_ORDER_SOURCE_TEXT,
) -> Any:
    """The ``ata_spm.MarketOrder`` of ``rows`` by ``figures``, largest first.

    A row with no figure keeps its place after every figured row, in the
    order ``rows`` came; no figure at all keeps ``rows`` whole under
    ``bare_source``.
    """
    held = list(rows)
    if not figures:
        return ata_spm.MarketOrder(
            listings=held, source=str(bare_source), unfigured=len(held)
        )
    figured = [one for one in held if str(one.symbol) in figures]
    figured.sort(key=lambda one: (-figures[str(one.symbol)], str(one.symbol)))
    unfigured = [one for one in held if str(one.symbol) not in figures]
    return ata_spm.MarketOrder(
        listings=figured + unfigured,
        source=str(source),
        figures=dict(figures),
        unfigured=len(unfigured),
    )


def stocks_markets() -> Any:
    """The stocks ``ata_spm.MarketOrder``: ``screener_listings`` ranked by its
    volume figures, or ``MAPS`` rows in map order when the screener refused.

    The source names which list was read and, on the screener, how many
    sectors its quotes named.
    """
    rows, figures, refusal = ata_asset_maps.screener_listings()
    if rows:
        sectors = {one.sector for one in rows if one.sector}
        return ranked_order(
            rows,
            figures,
            STOCKS_SCREENER_SOURCE_FORMAT.format(
                source=ata_asset_maps.SCREENER_SOURCE_TEXT, sectors=len(sectors)
            ),
        )
    held = [
        one
        for sector in ata_asset_maps.sectors_for(ata_spm.CLASS_STOCKS)
        for one in ata_asset_maps.listings_for(sector, ata_spm.CLASS_STOCKS)
    ]
    return ata_spm.MarketOrder(
        listings=held,
        source=STOCKS_PORTFOLIO_SOURCE_FORMAT.format(refusal=refusal),
        unfigured=len(held),
    )


def crypto_markets(connectors: Any) -> Any:
    """The crypto ``ata_spm.MarketOrder``: the ``class_tickers`` names the
    venue trades, ranked by ``class_volumes``, with the rest on ``dead``.

    ``trading_products`` reads the connectors' loaded tables and
    ``public_products`` the public route while none is in reach; each row
    carries ``exchange_timeframes`` as its served table.
    """
    from ...exchange.market_inspector_fetcher import (
        exchange_timeframes,
        public_products,
        trading_products,
    )

    served = exchange_timeframes(connectors)
    trading = trading_products(connectors) if connectors else public_products()
    names = sorted(class_tickers(ata_spm.CLASS_CRYPTO))
    dead = [one for one in names if trading and not trading.get(one.upper(), False)]
    rows = [
        ata_asset_maps.exchange_listing(one, served) for one in names if one not in dead
    ]
    volumes = class_volumes(ata_spm.CLASS_CRYPTO, connectors)
    figures = {
        str(one.symbol): float(volumes[str(one.symbol).upper()])
        for one in rows
        if float(volumes.get(str(one.symbol).upper(), 0.0)) > 0.0
    }
    if not connectors:
        return ata_spm.MarketOrder(
            listings=rows,
            source=(
                CRYPTO_PUBLIC_SOURCE_TEXT
                if trading
                else CRYPTO_NO_CONNECTOR_SOURCE_TEXT
            ),
            unfigured=len(rows),
            dead=dead,
        )
    order = ranked_order(
        rows,
        figures,
        CRYPTO_ORDER_SOURCE_FORMAT.format(
            venues=ORDER_VENUE_JOIN.join(sorted(str(one) for one in connectors))
        ),
        CRYPTO_NO_FIGURE_SOURCE_TEXT,
    )
    order.dead = dead
    return order


def class_markets(asset_class: Any, connectors: Any = None) -> Any:
    """Every market one class holds as an ``ata_spm.MarketOrder``, largest first.

    Crypto is ``crypto_markets``, stocks is ``stocks_markets``; every other
    mapped class ranks ``listing_volumes`` over its ``ata_asset_maps.MAPS``
    rows, and a class whose rows carry no figure keeps map order.
    """
    if str(asset_class) == ata_spm.CLASS_CRYPTO:
        return crypto_markets(connectors)
    if str(asset_class) == ata_spm.CLASS_STOCKS:
        return stocks_markets()
    rows = [
        one
        for sector in ata_asset_maps.sectors_for(asset_class)
        for one in ata_asset_maps.listings_for(sector, asset_class)
    ]
    venues = sorted({one.venue for one in rows if one.venue})
    return ranked_order(
        rows,
        listing_volumes(rows),
        VENUE_ORDER_SOURCE_FORMAT.format(venue=ORDER_VENUE_JOIN.join(venues)),
    )


def fold_ticker(typed: Any) -> str:
    """``typed`` as the maps spell a name: upper case, outer spaces stripped,
    and each of ``TICKER_SEPARATORS`` read as ``TICKER_JOIN``."""
    asked = str(typed or "").strip().upper()
    for one in TICKER_SEPARATORS:
        asked = asked.replace(one, TICKER_JOIN)
    return asked


def pair_base(folded: Any) -> str:
    """The base of a pair whose quote is one of ``DEFAULT_QUOTES``, else empty.

    ``BTC/USD`` and ``BTCUSD`` both answer ``BTC``; a quote outside
    ``DEFAULT_QUOTES`` answers nothing.
    """
    asked = str(folded or "")
    if TICKER_JOIN in asked:
        base, _, quote = asked.partition(TICKER_JOIN)
        return base if quote in DEFAULT_QUOTES and base else ""
    for quote in DEFAULT_QUOTES:
        if asked.endswith(quote) and len(asked) > len(quote):
            return asked[: -len(quote)]
    return ""


def connector_tickers(connectors: Any = None) -> list:
    """The crypto bases the connector's ticker read listed.

    With no ``connectors`` the fetcher's ``cached_quote_volumes`` answers
    whatever its age; with them ``class_volumes`` serves the cache while it
    is fresh and asks the connector once otherwise.
    """
    if connectors:
        return sorted(class_volumes(ata_spm.CLASS_CRYPTO, connectors))
    from ...exchange.market_inspector_fetcher import cached_quote_volumes

    return sorted(cached_quote_volumes())


def class_names(asset_class: Any, connectors: Any = None) -> list:
    """Every name one class recognises: ``class_tickers`` plus, for crypto,
    ``connector_tickers``."""
    held = set(class_tickers(asset_class))
    if str(asset_class) == ata_spm.CLASS_CRYPTO:
        held.update(str(one) for one in connector_tickers(connectors))
    return sorted(held)


def class_walk(asset_class: Any) -> list:
    """``ata_spm.ASSET_CLASSES`` with ``asset_class`` first."""
    chosen = str(asset_class)
    rest = [one for one in ata_spm.ASSET_CLASSES if one != chosen]
    return ([chosen] if chosen in ata_spm.ASSET_CLASSES else []) + rest


def class_listing(symbol: Any, asset_class: Any) -> Any:
    """The ``ata_asset_maps.AssetListing`` one class charts ``symbol`` on."""
    name = str(symbol)
    if str(asset_class) == ata_spm.CLASS_CRYPTO:
        return ata_asset_maps.exchange_listing(name)
    for sector in ata_asset_maps.sectors_for(asset_class):
        for one in ata_asset_maps.listings_for(sector, asset_class):
            if one.symbol.upper() == name.upper():
                return one
    return ata_asset_maps.AssetListing(symbol=name)


def name_in(folded: str, names: Any) -> str:
    """The one of ``names`` that ``folded`` spells: whole, with ``TICKER_JOIN``
    removed from both sides, or by the base ``pair_base`` answers."""
    joined = folded.replace(TICKER_JOIN, "")
    base = pair_base(folded)
    by_whole = {str(one).upper(): str(one) for one in names}
    if folded in by_whole:
        return by_whole[folded]
    by_joined = {str(one).upper().replace(TICKER_JOIN, ""): str(one) for one in names}
    if joined in by_joined:
        return by_joined[joined]
    if base and base in by_whole:
        return by_whole[base]
    return ""


def placements_of(typed: Any, asset_class: Any, connectors: Any = None) -> list:
    """Every ``ata_spm.TickerPlacement`` the typed text names, the chosen
    class first, then the rest of ``ata_spm.ASSET_CLASSES`` in order."""
    folded = fold_ticker(typed)
    if not folded:
        return []
    found: list = []
    for one in class_walk(asset_class):
        named = name_in(folded, class_names(one, connectors))
        if named:
            found.append(
                ata_spm.TickerPlacement(
                    listing=class_listing(named, one),
                    asset_class=one,
                    typed=str(typed or ""),
                )
            )
    return found


def ticker_offer(symbol: Any, asset_class: Any) -> list:
    """One completer row: the symbol, its class and ``TICKER_OFFER_FORMAT``."""
    return [
        str(symbol),
        str(asset_class),
        TICKER_OFFER_FORMAT.format(symbol=symbol, asset_class=asset_class),
    ]


def ticker_matches(typed: Any, asset_class: Any) -> list:
    """The ``ticker_offer`` rows ``typed`` names across every class, prefix
    matches first and the chosen class first inside each, capped at
    ``TICKER_MATCH_LIMIT``. A typed pair offers the crypto base while its
    quote part starts one of ``DEFAULT_QUOTES``; no venue is asked."""
    asked = fold_ticker(typed)
    if not asked:
        return []
    base, _, quote_part = asked.partition(TICKER_JOIN)
    pair_typed = TICKER_JOIN in asked and any(
        one.startswith(quote_part) for one in DEFAULT_QUOTES
    )
    starts: list = []
    holds: list = []
    for one in class_walk(asset_class):
        for symbol in class_names(one):
            folded = symbol.upper()
            if folded.startswith(asked) or (pair_typed and folded == base):
                starts.append(ticker_offer(symbol, one))
            elif asked in folded:
                holds.append(ticker_offer(symbol, one))
    return (starts + holds)[:TICKER_MATCH_LIMIT]


def ticker_note(asset_class: Any, note: Any = "") -> str:
    """The line under the ticker field, from the last press or from the sector.

    A ``note`` the last press left is what the field carries, and a sector
    ``class_tickers`` lists nothing for carries ``TICKER_NO_LIST_FORMAT``.
    """
    if note:
        return str(note)
    if class_tickers(asset_class):
        return ""
    return TICKER_NO_LIST_FORMAT.format(sector=asset_class)


def market_listing(ticker: Any, asset_class: Any, connectors: Any = None) -> Any:
    """The ``ata_spm.TickerPlacement`` a typed ticker names, across every class.

    ``placements_of`` walks the chosen class first; a chosen class that
    ``class_tickers`` lists nothing for takes any name no class holds, which
    is what ``TICKER_NO_LIST_FORMAT`` says under the field; a name no class
    holds under a listing class answers None.
    """
    placed = placements_of(ticker, asset_class, connectors)
    if placed:
        return placed[0]
    folded = fold_ticker(ticker)
    if not folded or class_tickers(asset_class):
        return None
    return ata_spm.TickerPlacement(
        listing=ata_asset_maps.AssetListing(symbol=folded),
        asset_class=str(asset_class),
        typed=str(ticker or ""),
    )


def open_chart_folder() -> str:
    """Ask the host to show the chart image directory, and answer its path.

    ``ata_post_paths.venue_post_roots`` creates the root and one folder per
    name in ``ata_spm_push.TARGET_NAMES`` first, so the press opens a root
    holding every venue folder before any chart is drawn.
    """
    root = ata_post_paths.get_ata_post_root()
    ata_post_paths.venue_post_roots(ata_spm_push.TARGET_NAMES)
    if not ata_spm_push.open_path(root):
        logger.warning(CHART_FOLDER_FAILED_LOG, root, HANDLER_REFUSED_TEXT)
    return str(root)


def chart_folder_line(path: Any) -> str:
    """The line a Chart Folder press leaves, naming the root opened.

    The host writes it to the Activity Log and to the log in one call, so
    ``open_chart_folder`` itself logs only a refusal.
    """
    return CHART_FOLDER_OPENED_LOG % (path,)


#: The part each press reports, and the press key ``PushBoard.press_lines`` reads.
PRESS_KEYS = {
    POST_SELECTED_PART: ata_spm_push.PRESS_POST_SELECTED,
    POST_ALL_PART: ata_spm_push.PRESS_POST_ALL,
    FULL_AUTO_PART: ata_spm_push.PRESS_FULL_AUTO,
}


def push_press_lines(board: Any, key: Any, answered: Any) -> list:
    """The Activity Log lines one Ready to Send press leaves, both hosts alike.

    A post press hands its records to ``PushBoard.press_lines``; the Chart
    Folder press names the root it opened; every other press leaves none.
    """
    part = str(key)
    if part == CHART_FOLDER_PART:
        return [chart_folder_line(answered)]
    press = PRESS_KEYS.get(part)
    if press is None:
        return []
    return board.press_lines(press, answered)


def inspector_candles(inspector: Any, symbol: Any, timeframe: Any) -> list:
    """The candles the last universe scan kept for one symbol on one timeframe."""
    held = getattr(inspector, "last_candles", None) or {}
    return list((held.get(str(symbol)) or {}).get(str(timeframe)) or [])


def inspector_scan_age(inspector: Any) -> float:
    """The seconds since the Market Inspector's last universe scan.

    An analyzer that has never scanned answers ``NO_SCAN_AGE``, which no
    freshness window accepts.
    """
    import time

    at = float(getattr(inspector, "last_scan_ts", 0.0) or 0.0)
    if at <= 0.0:
        return NO_SCAN_AGE
    return max(0.0, time.time() - at)


def connector_candles(connectors: Any, symbol: Any, timeframe: Any) -> list:
    """The candles ``fetch_symbol_timeframe`` reads for one symbol now.

    It runs on the connectors already in reach, and no connector answers
    none, so the timeframe reads unread.
    """
    if not connectors:
        return []
    import asyncio

    from ...exchange.market_inspector_fetcher import fetch_symbol_timeframe

    return list(
        asyncio.run(fetch_symbol_timeframe(connectors, symbol, timeframe)) or []
    )


def sector_candle_read(
    inspector: Any, symbol: Any, timeframe: Any, connectors: Any = None
) -> tuple:
    """The source, the candles and the refusal for one scanned symbol.

    A symbol ``ata_asset_maps.listing_of`` names reads through that listing's
    venue; every other symbol takes ``inspector_candles`` while the universe
    scan is younger than ``CANDLES_FRESH_SECONDS``, ``connector_candles``
    once it is older, and ``public_candles`` on the public Coinbase route
    while no connector is in reach.
    """
    listing = ata_asset_maps.listing_of(symbol)
    if listing is not None:
        candles, refusal = ata_asset_maps.venue_candle_read(symbol, timeframe)
        return listing.venue, candles, refusal
    if inspector_scan_age(inspector) < CANDLES_FRESH_SECONDS:
        held = inspector_candles(inspector, symbol, timeframe)
        if held:
            return CANDLES_FROM_SCAN, held, ""
    if not connectors:
        from ...exchange.market_inspector_fetcher import public_candles

        return (
            ata_asset_maps.VENUE_EXCHANGE,
            list(public_candles(symbol, timeframe)),
            "",
        )
    return (
        ata_asset_maps.VENUE_EXCHANGE,
        connector_candles(connectors, symbol, timeframe),
        "",
    )


def sector_candles(
    inspector: Any, symbol: Any, timeframe: Any, connectors: Any = None
) -> list:
    """The candles ``sector_candle_read`` answers for one scanned symbol."""
    return sector_candle_read(inspector, symbol, timeframe, connectors)[1]


def ata_spm_skin(model: Any) -> dict:
    """Every value the ATA-SPM control row is drawn from, and its state."""
    row = model.ata_row()
    return {
        "ticker_placeholder": TICKER_FIELD_PLACEHOLDER,
        "ticker_tooltip": TICKER_FIELD_TOOLTIP,
        "ticker_min_width_px": TICKER_FIELD_MIN_WIDTH_PX,
        "scan_label": SCAN_NOW_LABEL,
        "scan_busy_label": ata_spm.SCAN_BUSY_LABEL,
        "scan_running": bool(model.board.scanning),
        "scan_tooltip": SCAN_NOW_TOOLTIP,
        "scan_width_px": SCAN_NOW_WIDTH_PX,
        "button_height_px": PUSH_BUTTON_HEIGHT_PX,
        "field_height_px": FIELD_HEIGHT_PX,
        "class_tooltip": CLASS_BOX_TOOLTIP,
        "class_width_px": CLASS_BOX_WIDTH_PX,
        "timeframe_title": TIMEFRAME_TITLE,
        "box_tooltip_format": TIMEFRAME_BOX_TOOLTIP_FORMAT,
        "box_width_px": TIMEFRAME_BOX_WIDTH_PX,
        "box_row_part": TIMEFRAME_ROW_PART,
        "box_grid_width_px": TIMEFRAME_GRID_WIDTH_PX,
        "sector_row_part": SECTOR_ROW_PART,
        "scan_row_part": SCAN_ROW_PART,
        "title_part": SECTION_TITLE_PART,
        "row_spacing_px": ATA_ROW_SPACING_PX,
        "field_padding_px": list(FIELD_PADDING_PX),
        "field_border_px": FIELD_BORDER_PX,
        "sector_text": row["sector_text"],
        "sector_class": row["sector_class"],
        "ticker_matches": ticker_matches(row["sector_text"], row["sector_class"]),
        "ticker_note": ticker_note(row["sector_class"], model.board.note),
        "ticker_note_part": TICKER_NOTE_PART,
        "ticker_note_colour": TICKER_NOTE_COLOUR,
        "ticker_note_size_px": TICKER_NOTE_SIZE_PX,
        "ticker_match_part": TICKER_MATCH_PART,
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
    """The signals the screen keeps: scored, and active only on request."""
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
    through, and the Opposing Trades zone prints its label and statistic.
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
    """The Market Inspector screen: its filter row, its six zones, its pane.

    ``start_fetch`` refuses in the places the shipped screen refuses and
    hands the fetch to the scheduler otherwise. ``fetch_and_analyze``
    writes the fetch report, feeds the analyzer and redraws.
    ``render_signals`` fills both row stores from the analyzer's most recent
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
        self.ata_class_source: Any = None
        self.board = ata_spm.SectorBoard()
        self.push = ata_spm_push.PushBoard()
        self.push.settings.set_vault(encryption.default_vault())
        self.push.settings.set_connector(
            ata_spm_signin.build_connector(ata_spm_signin.default_session())
        )
        self.refresh_enabled = True
        self.status_label_text = STATUS_INITIAL_TEXT
        self.signal_rows: list = []
        self.pair_rows: list = []
        self.pairs: list = []
        self.zone_at: dict = {}
        self.zone_open: dict = {}
        self.scheduled: list = []
        self.emitted: list = []
        self.press_lines: list = []
        self.calls: list = []
        self.set_ata_sources(sector_assets, self.scanned_candles, self.class_markets)
        self.build_ui()

    def build_ui(self) -> None:
        """Build the filter row, the status line and two empty row stores."""
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
        """The scored signals this screen keeps under the active filter."""
        return shown_signals(signals, self.show_active)

    def fill_signal_rows(self, signals: list) -> None:
        """Hold one HTF Signals row per entry of ``signals``."""
        set_row_count(self.signal_rows, len(signals), len(SIGNAL_COLUMNS))
        for index, found in enumerate(signals):
            fill_signal_row(self.signal_rows[index], found)
        self.calls.append([SIGNALS_DRAWN, len(self.signal_rows)])

    def fill_pair_rows(self, pairs: Any) -> None:
        """Hold one Opposing Pairs row per entry of ``pairs``."""
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

    def set_ata_sources(
        self, asset_source: Any, candle_source: Any, class_source: Any = None
    ) -> None:
        """Wire the assets a sector holds, the candles each one charts on, and
        the markets a class lists by volume."""
        self.ata_asset_source = asset_source
        self.ata_candle_source = candle_source
        self.ata_class_source = class_source
        self.calls.append([ATA_SOURCES_SET])

    def class_markets(self, asset_class: Any) -> Any:
        """The ``ata_spm.MarketOrder`` one class holds, on the connectors in reach."""
        return class_markets(asset_class, self.connectors_now())

    def scanned_candles(self, symbol: Any, timeframe: Any) -> list:
        """The candles for one scanned symbol, from the source its map names.

        A source this screen cannot reach answers none, so the timeframe
        reads unread and Scan Now takes no exception.
        """
        try:
            return sector_candles(
                self.inspector(), symbol, timeframe, self.connectors_now()
            )
        except Exception as exc:  # noqa: BLE001 - the source is off-process
            logger.debug(CANDLE_READ_FAILED_LOG, symbol, timeframe, exc)
            return []

    def market_placement(self, ticker: Any, asset_class: Any) -> Any:
        """``market_listing`` on the connectors in reach, for ``scan_now``."""
        return market_listing(ticker, asset_class, self.connectors_now())

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
        """Tick or untick one timeframe, on the sector shown or on the next one."""
        at = self.zone_at.get(ATA_SPM_MODULE, 0)
        ticked = self.board.toggle_timeframe(at, key)
        self.calls.append([TIMEFRAME_TOGGLED, str(key), ticked])

    def scan_now(self) -> Any:
        """Press Scan Now: read the typed ticker's market, or the sector menu's
        markets by volume until ``hits_per_scan`` hits.

        Answers the ``ata_spm.AtaSpmRun`` the three phases produced, or None
        when ``market_placement`` cannot place the ticker and the board is
        left carrying ``ata_spm.TICKER_UNHELD_FORMAT``.
        """
        added = self.board.scan_now(
            self.ata_asset_source or sector_assets,
            self.ata_candle_source or self.scanned_candles,
            self.push.settings.message_format,
            self.push.settings.max_supporting_indicators,
            self.market_placement,
            self.ata_class_source or self.class_markets,
            self.push.settings.hits_per_scan,
            self.zone_at.get(ATA_SPM_MODULE, 0),
        )
        if added != ata_spm.NO_NEW_SECTOR:
            self.zone_at[ATA_SPM_MODULE] = added
        if self.board.note:
            self.calls.append([SCAN_NOW_REFUSED, self.board.note])
            return None
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
            CHART_FOLDER_PART: open_chart_folder,
            SETTINGS_PART: self._press_settings,
            THUMBNAIL_PART: self._press_thumbnail,
            CONNECT_PART: self._press_connect,
            BACK_PART: self._press_back,
            ZONES_PART: self._press_settings,
        }.get(str(key))
        if handled is None:
            return None
        answered = handled()
        self.calls.append([PUSH_ACTION_SET, str(key)])
        self.press_lines = push_press_lines(self.push, key, answered)
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
        """Show Level 1, or the scan page, and answer which."""
        open_now = self.push.toggle_settings()
        self.calls.append([SETTINGS_PAGE_TOGGLED, open_now])
        return open_now

    def _press_connect(self) -> Any:
        """Sign the open Level 1A target in, and answer what the venue said."""
        answered = self.push.connect_credentials()
        if answered is None:
            return None
        self.calls.append(
            [
                CREDENTIAL_STORED if answered.ok else CREDENTIAL_REFUSED,
                str(answered.target),
                str(answered.detail),
            ]
        )
        return answered

    def _press_back(self) -> bool:
        """Leave Level 1A for Level 1 without signing in."""
        self.push.close_credentials()
        self.calls.append([CREDENTIAL_PAGE_CLOSED, LEVEL_ONE])
        return True

    def open_credentials(self, target: Any) -> Any:
        """Open one push target's Level 1A page and answer which target draws."""
        name = self.push.open_credentials(target)
        if name is None:
            self.calls.append([CREDENTIAL_PAGE_REFUSED, str(target or "")])
            return None
        self.calls.append([CREDENTIAL_PAGE_OPENED, name])
        return name

    def set_credential_text(self, target: Any, field: Any, typed: Any) -> None:
        """Hold what one credential field carries until Connect reads it."""
        self.push.settings.set_credential_text(target, field, typed)

    def hold_credential(self, target: Any, field: Any) -> bool:
        """Encrypt one finished credential box into the vault, and answer whether it holds it.

        Nothing here carries the value, so the answer says only that a box is
        held and no render or call log can carry a token.
        """
        return self.push.settings.hold_credential(target, field)

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
            self.board.note,
            self.board.progress_text,
        )

    def right_zones(self) -> list:
        """The three right-side zones, in the order the screen draws them.

        Ready to Send reads ``ata_report``, the ATA-SPM board's own run,
        so a scan that left no post says so rather than reading unwired.
        """
        return right_zone_rows(self.ata_report(), self.push.bucket)

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
        """All six zones as the stepper draws them, left three then right three.

        The ATA-SPM zone carries ``board.progress_text`` as its running line.
        """
        rows = self.left_modules() + self.right_zones()
        return [
            zone_view(
                key,
                title,
                self.zone_entries(key),
                self.zone_at.get(key, 0),
                self.zone_open.get(key, False),
                status,
                self.board.progress_text if key == ATA_SPM_MODULE else "",
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
        """Take the base assets the fleet trades and redraw the screen."""
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
        """Fetch the universe, feed the analyzer and redraw the screen."""
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
        """Rewrite the status line and both row stores from the last scan."""
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
        "show_active_default": SHOW_ACTIVE_CHECKED,
        "show_active_tooltip": SHOW_ACTIVE_TOOLTIP,
        "show_active": model.show_active,
        "status_text": model.status_label_text,
        "status_initial_text": STATUS_INITIAL_TEXT,
        "status_style": STATUS_STYLE,
        "left_modules": [list(one) for one in model.left_modules()],
        "right_zones": [list(one) for one in model.right_zones()],
        "zones": [dict(one) for one in model.zone_views()],
        "stepper": stepper_skin(),
        "ata_spm": ata_spm_skin(model),
        "bucket": bucket_skin(model.push, model.board.asset_class),
        "right_zone_keys": list(RIGHT_ZONE_KEYS),
        "right_zone_titles": list(RIGHT_ZONE_TITLES),
        "left_module_keys": list(LEFT_MODULE_KEYS),
        "left_module_titles": list(LEFT_MODULE_TITLES),
        "left_module_shares": list(LEFT_MODULE_SHARES),
        "module_frame_px": MODULE_FRAME_PX,
        "module_margins_px": list(MODULE_MARGINS_PX),
        "module_title_padding_px": list(MODULE_TITLE_PADDING_PX),
        "button_padding_px": list(BUTTON_PADDING_PX),
        "button_font_weight": BUTTON_FONT_WEIGHT,
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
    ``toggle_timeframe``, ``scan_now``, ``open_credentials``,
    ``step_zone``, ``toggle_zone``,
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
    if params.get("credential_held"):
        finished = list(params["credential_held"])
        model.hold_credential(finished[0], finished[1])
    if params.get("open_credentials"):
        model.open_credentials(params["open_credentials"])
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
