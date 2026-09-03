"""api_tester_tab_surface.py -- the isolated exchange API tester.

Describes the screen the operator tests an exchange from. It picks a
venue, connects with stored or hand-typed keys, runs one of seven read
calls, and reads the answer in a running response log. Two diagnostic
buttons sit under those seven: a raw HTTP probe that goes round the
exchange library, and a status-page check.

Nothing on this screen touches a bot or a live position.

Every outward step -- the exchange session, the socket, the certificate
handshake, the web request and the clock -- is taken by a ``caller``
handed in at construction. A model built with no caller reaches nothing:
each outward step refuses and the screen reports the refusal. Every
colour, wording, ordering and refusal rule lives here.

``src.core.desktop_bridge`` registers ``view_model`` as the handler for
the ``api_tester_tab.state`` method, which is how the Electron renderer
reaches it. Nothing here imports Qt.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .. import design_system as ds

logger = logging.getLogger("acervator.gui")

METHOD = "api_tester_tab.state"

LOGGER_NAME = "acervator.gui"

CONNECTION_TITLE = "Exchange Connection (Isolated - does not affect bots)"
EXCHANGE_LABEL = "Exchange:"
USE_STORED_LABEL = "Use stored credentials"
USE_STORED_TIP = "Use API keys saved in Settings instead of entering manually"
USE_STORED_DEFAULT = True

# The grey hint inside each of the three credential boxes, in the order
# the row lays them out.
CREDENTIAL_PLACEHOLDERS = ("API Key", "API Secret", "Passphrase (if needed)")
ECHO_MODE = "Password"
# Whether the credentials are hidden inside the three boxes.
CREDENTIALS_HIDDEN = ECHO_MODE == "Password"

CONNECT_LABEL = "Connect"
CONNECT_TIP = "Establish isolated connection to exchange API"
DISCONNECT_LABEL = "Disconnect"

STATUS_IDLE_TEXT = "Not connected"
STATUS_CONNECTING_FORMAT = "Connecting to {exchange}..."
STATUS_CONNECTED_FORMAT = "Connected: {exchange} ({markets} markets)"
STATUS_FAILED_TEXT = "Failed"
STATUS_DISCONNECTED_TEXT = "Disconnected"

# ds.CARD_METRIC_LABEL is "#888": three equal channels, so a swap of any
# two reads the same. Every check on it compares the exact text.
STATUS_IDLE_COLOR = ds.CARD_METRIC_LABEL
STATUS_CONNECTING_COLOR = ds.STATUS_INFO
STATUS_CONNECTED_COLOR = ds.SUCCESS
STATUS_FAILED_COLOR = ds.ERROR
STATUS_DISCONNECTED_COLOR = ds.CARD_METRIC_LABEL

STATUS_STYLE_FORMAT = "color: {color};"

OPERATIONS_TITLE = "API Operations"
RESPONSE_TITLE = "Response"

SYMBOL_DEFAULT = "BTC/USDT"
SYMBOL_TIP = "Trading pair for ticker, orderbook, OHLCV queries"

RESULT_PLACEHOLDER = "Connect to an exchange and run a test..."
RESULT_INFO_TEXT = ""
RESULT_INFO_WORD_WRAP = True
RESULT_READ_ONLY = True

TEST_MARKETS = "fetch_markets"
TEST_TICKER = "fetch_ticker"
TEST_BALANCES = "fetch_balances"
TEST_ORDERBOOK = "fetch_orderbook"
TEST_OHLCV = "fetch_ohlcv"
TEST_OPEN_ORDERS = "fetch_open_orders"
TEST_TRADES = "fetch_trades"

TEST_BUTTONS = (
    ("Fetch Markets", TEST_MARKETS, "Load all trading pairs"),
    ("Fetch Ticker", TEST_TICKER, "Current bid/ask/last price"),
    ("Fetch Balances", TEST_BALANCES, "Account balances (requires auth)"),
    ("Fetch Order Book", TEST_ORDERBOOK, "Top 20 bids and asks"),
    ("Fetch OHLCV (1h x50)", TEST_OHLCV, "50 hourly candles"),
    ("Fetch Open Orders", TEST_OPEN_ORDERS, "Currently open orders"),
    ("Fetch My Trades", TEST_TRADES, "Recent trade history"),
)

TEST_NAMES = tuple(entry[1] for entry in TEST_BUTTONS)

DIAGNOSTICS_LABEL = "--- Diagnostics ---"
DIAGNOSTICS_COLOR = ds.TEXT_PLACEHOLDER
DIAGNOSTICS_STYLE_FORMAT = "color: {color}; margin-top: 6px;"
DIAGNOSTICS_ALIGNMENT = "AlignCenter"
DIAGNOSTICS_ALIGNMENT_VALUE = 132

RAW_PROBE_LABEL = "Raw HTTP Probe"
RAW_PROBE_TIP = (
    "Bypass CCXT and make a direct HTTP request to the exchange.\n"
    "Shows exact HTTP status, headers, and response body.\n"
    "Use this to diagnose connection failures."
)
STATUS_PAGE_LABEL = "Exchange Status Page"
STATUS_PAGE_TIP = "Check if the exchange reports any known outages"

LAYOUT_MARGINS = (6, 6, 6, 6)
LAYOUT_SPACING = 4
GROUP_MARGINS = (6, 14, 6, 6)
CONNECTION_SPACING = 4
MANUAL_MARGINS = (0, 0, 0, 0)
MANUAL_SPACING = 4
OPERATIONS_SPACING = 3
SPLITTER_ORIENTATION = "Horizontal"
SPLITTER_HANDLE_WIDTH = 5
SPLITTER_CHILDREN_COLLAPSIBLE = False
SPLITTER_SIZES = (250, 750)

LEVEL_INFO = "info"
LEVEL_SUCCESS = "success"
LEVEL_WARNING = "warning"
LEVEL_ERROR = "error"

LEVEL_COLORS = {
    LEVEL_INFO: ds.STATUS_INFO,
    LEVEL_SUCCESS: ds.SUCCESS,
    LEVEL_WARNING: ds.WARNING,
    LEVEL_ERROR: ds.ERROR,
}

DEFAULT_LEVEL_COLOR = ds.TEXT_NEUTRAL
TIMESTAMP_COLOR = ds.CARD_METRIC_LABEL
DETAIL_COLOR = ds.TEXT_NEUTRAL

NO_ELAPSED = 0
TIMING_FORMAT = " ({elapsed:.0f}ms)"
NO_TIMING = ""
TIMESTAMP_FORMAT = "%H:%M:%S"

# The response log ships whole on every bridge call, so it is bounded.
ENTRY_LIMIT = 200
CALL_LIMIT = 600

HEADLINE_FORMAT = "{title}{timing}"
HEADLINE_STYLE_FORMAT = "color: {color}; font-weight: bold;"

# The tags the response-log line is written from, drawn as elements.
ENTRY_MARKS = {
    "span_open": '<span style="color:',
    "attr_close": '">',
    "span_close": "</span>",
    "strong_open": "<b>",
    "strong_close": "</b>",
    "line_break": "<br>",
    "pre_open": '<pre style="color:',
    "pre_attrs": '; margin:0; white-space:pre-wrap;">',
    "pre_close": "</pre>",
    "stamp_open": "[",
    "stamp_close": "]",
    "join": " ",
    "strong_weight": "bold",
    "detail_wrap": "pre-wrap",
}

# The entry slots the response-log line leaves for its values.
ENTRY_SLOTS = {
    "stamp_color": "{stamp_color}",
    "stamp": "{stamp}",
    "color": "{color}",
    "title": "{title}",
    "timing": "{timing}",
    "detail_color": "{detail_color}",
    "detail": "{detail}",
}


def entry_line_format() -> str:
    """The response-log line, built from the marks and slots published."""
    mark = ENTRY_MARKS
    slot = ENTRY_SLOTS
    return (
        mark["span_open"]
        + slot["stamp_color"]
        + mark["attr_close"]
        + mark["stamp_open"]
        + slot["stamp"]
        + mark["stamp_close"]
        + mark["span_close"]
        + mark["join"]
        + mark["span_open"]
        + slot["color"]
        + mark["attr_close"]
        + mark["strong_open"]
        + slot["title"]
        + mark["strong_close"]
        + slot["timing"]
        + mark["span_close"]
        + mark["line_break"]
        + mark["pre_open"]
        + slot["detail_color"]
        + mark["pre_attrs"]
        + slot["detail"]
        + mark["pre_close"]
        + mark["line_break"]
    )


ENTRY_HTML_FORMAT = entry_line_format()

NO_SETTINGS_TITLE = "ERROR"
NO_SETTINGS_DETAIL = "Settings not available"
NO_CREDENTIALS_TITLE = "NO CREDENTIALS"
NO_CREDENTIALS_FORMAT = (
    "No stored credentials for {exchange}.\n"
    "Uncheck 'Use stored credentials' to enter manually,\n"
    "or add the exchange in Settings."
)
NO_MANUAL_TITLE = "ERROR"
NO_MANUAL_DETAIL = "Enter API key and secret"
CONNECTED_TITLE_FORMAT = "CONNECTED to {exchange}"
CONNECTED_DETAIL_FORMAT = (
    "Markets: {markets}\n"
    "Auth: not checked - press Fetch Balances\n"
    "This connection is isolated from bots."
)
CONNECT_FAILED_TITLE = "CONNECTION FAILED"
NO_MARKETS = 0

# The mark shown wherever this screen took no reading at all.
UNREADABLE_MARK = "?"

DISCONNECT_FAILED_TITLE = "DISCONNECT FAILED"
DISCONNECT_FAILED_FORMAT = (
    "{error}: {message}\n"
    "The exchange session may still be open. "
    "The connector reference is dropped either "
    "way, so nothing can close it from here."
)
DISCONNECTED_TITLE = "DISCONNECTED"
DISCONNECTED_DETAIL = "Connection closed"
NOTHING_OPEN_TITLE = "NOTHING TO CLOSE"
NOTHING_OPEN_DETAIL = "No session was open, so no close was attempted."

HISTORY_CALLBACK_LOG = "History callback registration: %s"

NOT_CONNECTED_TITLE = "ERROR"
NOT_CONNECTED_DETAIL = "Connect first"
RUNNING_TITLE_FORMAT = "Running {test}..."
RUNNING_DETAIL_FORMAT = "Symbol: {symbol}"
TEST_OK_FORMAT = "{test} OK"
TEST_FAILED_FORMAT = "{test} FAILED"
TEST_UNKNOWN_FORMAT = "{test} NOT RUN"
TEST_UNKNOWN_DETAIL = (
    "This screen has no call by that name, so the venue was never asked."
)

MARKETS_SAMPLE_LIMIT = 50
SPOT_TYPE = "spot"
ORDERBOOK_LIMIT = 20
OHLCV_TIMEFRAME = "1h"
OHLCV_LIMIT = 50
TRADES_LIMIT = 20
CLOSE_INDEX = 4
NO_CLOSE = 0

BALANCE_SECTIONS = ("free", "used", "total")
NO_HOLDING = 0
JSON_INDENT = 2
DISPLAY_LIMIT = 3000
TRUNCATED_SUFFIX = "\n... (truncated)"
LIST_HEAD_FORMAT = "[{count} items]\n"
LIST_SAMPLE_LIMIT = 5
LIST_TAIL_FORMAT = "\n... and {count} more"

PROBE_HOSTS = {
    "coinbase": "api.coinbase.com",
    "binance": "api.binance.com",
    "kraken": "api.kraken.com",
    "kucoin": "api.kucoin.com",
    "bybit": "api.bybit.com",
    "okx": "www.okx.com",
}
DEFAULT_HOST_FORMAT = "api.{exchange_id}.com"
PROBE_PORT = 443
PROBE_TIMEOUT_S = 10

SSL_DIAGNOSTIC_TITLE = "SSL DIAGNOSTIC"
SSL_DIAGNOSTIC_FORMAT = "Testing SSL/TLS connection to {host}:{port}..."
TCP_OK_FORMAT = "TCP OK ({elapsed:.0f}ms)"
TCP_OK_DETAIL_FORMAT = "Connected to {host}:{port}"
TCP_FAILED_TITLE = "TCP FAILED"
TCP_FAILED_FORMAT = (
    "Cannot reach {host}:{port} - {message}\n"
    "This is a network/firewall issue, not an API issue."
)
SSL_OK_FORMAT = "SSL OK ({elapsed:.0f}ms)"
SSL_OK_DETAIL_FORMAT = (
    "Protocol: {protocol}\n"
    "Cipher: {cipher}\n"
    "Server CN: {common_name}\n"
    "Issuer: {issuer}\n"
    "Not After: {not_after}"
)
CERT_UNKNOWN = "?"
SSL_CERT_FAILED_TITLE = "SSL CERT FAILED"
SSL_CERT_FAILED_FORMAT = (
    "Python cannot verify the SSL certificate for {host}.\n"
    "Error: {message}\n"
    "FIX: Run 'pip install --upgrade certifi' then rebuild.\n"
    "This is why CCXT fails but your browser works - browsers use\n"
    "the Windows certificate store, Python uses its own CA bundle."
)
SSL_FAILED_TITLE = "SSL FAILED"
ERROR_LINE_FORMAT = "{error}: {message}"
CERTIFI_OK_FORMAT = "SSL+certifi OK ({elapsed:.0f}ms)"
CERTIFI_OK_DETAIL_FORMAT = "Certifi CA bundle: {bundle}\nProtocol: {protocol}"
CERTIFI_MISSING_TITLE = "certifi NOT INSTALLED"
CERTIFI_MISSING_DETAIL = (
    "Install with: pip install certifi\n"
    "This provides CA certificates Python needs on Windows."
)
CERTIFI_FAILED_TITLE = "SSL+certifi FAILED"

PROBE_ENDPOINTS = {
    "coinbase": (
        (
            "GET",
            "https://api.coinbase.com/api/v3/brokerage/market/products",
            "v3 Public Products (what CCXT uses)",
        ),
        ("GET", "https://api.coinbase.com/v2/currencies", "v2 Currencies (legacy)"),
        (
            "GET",
            "https://api.exchange.coinbase.com/products",
            "Exchange Products (alt)",
        ),
    ),
    "binance": (
        ("GET", "https://api.binance.com/api/v3/exchangeInfo", "Exchange Info"),
        ("GET", "https://api.binance.com/api/v3/ping", "Ping"),
    ),
    "kraken": (
        ("GET", "https://api.kraken.com/0/public/SystemStatus", "System Status"),
        ("GET", "https://api.kraken.com/0/public/AssetPairs", "Asset Pairs"),
    ),
}
DEFAULT_ENDPOINT_METHOD = "GET"
DEFAULT_ENDPOINT_URL_FORMAT = "https://api.{exchange_id}.com"
DEFAULT_ENDPOINT_DESC = "Root endpoint"

PROBE_HEADERS = (
    ("User-Agent", "Acervator/1.8 (diagnostic)"),
    ("Accept", "application/json"),
)
STATUS_HEADERS = (("User-Agent", "Acervator/1.8"), ("Accept", "application/json"))

HTTP_PROBES_TITLE = "HTTP PROBES"
HTTP_PROBES_FORMAT = "Testing {count} endpoints..."
BODY_DISPLAY_LIMIT = 1000
BODY_TRUNCATED_SUFFIX = "\n... (truncated)"
JSON_KEYS_LIMIT = 10
JSON_KEYS_FORMAT = "JSON keys: {keys}\n"
PRODUCTS_KEY = "products"
PRODUCTS_COUNT_FORMAT = "Products count: {count}\n"
JSON_BODY_LIMIT = 800
UNKNOWN_HEADER = "unknown"
CONTENT_TYPE_HEADER = "Content-Type"
CONTENT_LENGTH_HEADER = "Content-Length"

HTTP_OK_TITLE_FORMAT = "HTTP {status} - {desc}"
HTTP_OK_DETAIL_FORMAT = (
    "Endpoint: {desc}\n"
    "URL: {url}\n"
    "HTTP Status: {status}\n"
    "Content-Type: {content_type}\n"
    "Content-Length: {content_length}\n"
    "Response:\n{body}"
)
HTTP_ERROR_TITLE_FORMAT = "HTTP {status} - {desc}"
HTTP_ERROR_DETAIL_FORMAT = (
    "Endpoint: {desc}\n"
    "URL: {url}\n"
    "HTTP Status: {status}\n"
    "Reason: {reason}\n"
    "Response Body: {body}"
)
HTTP_ERROR_BODY_LIMIT = 500
UNREACHABLE_TITLE_FORMAT = "UNREACHABLE - {desc}"
UNREACHABLE_DETAIL_FORMAT = (
    "Endpoint: {desc}\n"
    "URL: {url}\n"
    "Error: {reason}\n"
    "This means the request never reached the server.\n"
    "Check: DNS resolution, firewall, VPN, proxy settings."
)
PROBE_ERROR_TITLE_FORMAT = "ERROR - {desc}"
PROBE_ERROR_DETAIL_FORMAT = "URL: {url}\n{error}: {message}"
NO_BODY = ""

HTTP_UNREAD_TITLE_FORMAT = "HTTP {status} - {desc}"
UNREADABLE_ANSWER_TITLE_FORMAT = "UNREADABLE ANSWER - {desc}"
UNREADABLE_ANSWER_DETAIL_FORMAT = (
    "Endpoint: {desc}\n"
    "URL: {url}\n"
    "The request answered with {kind}, which this screen cannot read.\n"
    "Nothing here says the endpoint is healthy or unhealthy."
)
UNREAD_STATUS_NOTE = (
    "\nNo HTTP status came back, so nothing here says the request succeeded."
)
UNREADABLE_BODY_FORMAT = "[body is {kind}, not text]"

FAILURE_HTTP = "http"
FAILURE_URL = "url"
FAILURE_OTHER = "other"

STATUS_PAGE_URLS = {
    "coinbase": "https://status.coinbase.com/api/v2/status.json",
    "binance": (
        "https://www.binance.com/bapi/composite/v1/public/cms/article/"
        "list/query?type=1&pageNo=1&pageSize=1"
    ),
    "kraken": "https://status.kraken.com/api/v2/status.json",
}

MAPPABLE_INDICATORS = ("none", "minor", "major", "critical", "maintenance")
GREEN_INDICATORS = ("none", "minor")
INDICATOR_SEEN_LIMIT = 32
UNKNOWN_INDICATOR = "unknown"
STATUS_KEY = "status"
INDICATOR_KEY = "indicator"
DESCRIPTION_KEY = "description"

NO_STATUS_PAGE_TITLE = "STATUS"
NO_STATUS_PAGE_FORMAT = "No known status page for {exchange}"
CHECKING_STATUS_TITLE = "CHECKING STATUS"
CHECKING_STATUS_FORMAT = "Querying {exchange} status page..."
STATUS_TITLE_FORMAT = "STATUS: {description}"
STATUS_DETAIL_FORMAT = (
    "Exchange: {exchange}\n"
    "Status: {indicator}\n"
    "Description: {description}\n"
    "Raw: {raw}"
)
STATUS_RAW_LIMIT = 500
PLAIN_STATUS_TITLE = "STATUS"
PLAIN_STATUS_LIMIT = 800
STATUS_CHECK_FAILED_TITLE = "STATUS CHECK FAILED"

EMPTY_TEXT = ""
SKIN: dict[str, str] = {}
STYLE_SHEET = ""
TIMERS: dict[str, int] = {}
TIMER_DELAYS_MS: tuple[int, ...] = ()
BUS_TOPICS: tuple[str, ...] = ()

ACTIONS = {
    "use_stored_toggled": "set_use_stored",
    "connect_clicked": "do_connect",
    "disconnect_clicked": "do_disconnect",
    "test_clicked": "run_test",
    "raw_probe_clicked": "raw_http_probe",
    "status_page_clicked": "check_exchange_status",
}

NO_CALLER_MESSAGE = "this surface was built with no caller, so it reaches nothing"

ENTRY_LOGGED = "entry.logged"
CONNECT_STARTED = "connect.started"
CONNECT_REFUSED = "connect.refused"
CONNECT_OPENED = "connect.opened"
CONNECT_FAILED = "connect.failed"
HISTORY_WIRED = "history.wired"
HISTORY_SKIPPED = "history.skipped"
DISCONNECT_CLOSED = "disconnect.closed"
DISCONNECT_FAILED = "disconnect.failed"
DISCONNECT_NOTHING_OPEN = "disconnect.nothing_open"
TEST_REFUSED = "test.refused"
TEST_RAN = "test.ran"
TEST_UNKNOWN = "test.unknown"
TEST_FAILED = "test.failed"
PROBE_TCP = "probe.tcp"
PROBE_HANDSHAKE = "probe.handshake"
PROBE_HANDSHAKE_UNREAD = "probe.handshake_unread"
PROBE_CERTIFI = "probe.certifi"
PROBE_REQUESTED = "probe.requested"
PROBE_GREEN = "probe.green"
PROBE_UNREAD = "probe.unread"
STATUS_REQUESTED = "status.requested"
STATUS_READ = "status.read"
STATUS_UNMAPPED = "status.unmapped"

# Every step name a call row can open with, in the order they are declared.
CALL_NAMES = (
    ENTRY_LOGGED,
    CONNECT_STARTED,
    CONNECT_REFUSED,
    CONNECT_OPENED,
    CONNECT_FAILED,
    HISTORY_WIRED,
    HISTORY_SKIPPED,
    DISCONNECT_CLOSED,
    DISCONNECT_FAILED,
    DISCONNECT_NOTHING_OPEN,
    TEST_REFUSED,
    TEST_RAN,
    TEST_UNKNOWN,
    TEST_FAILED,
    PROBE_TCP,
    PROBE_HANDSHAKE,
    PROBE_HANDSHAKE_UNREAD,
    PROBE_CERTIFI,
    PROBE_REQUESTED,
    PROBE_GREEN,
    PROBE_UNREAD,
    STATUS_REQUESTED,
    STATUS_READ,
    STATUS_UNMAPPED,
)

Call = list


class CallerRefused(RuntimeError):
    """No caller was handed in, so the outward step could not be taken."""


def timing_text(elapsed: float) -> str:
    """The ``(Nms)`` a headline carries, or nothing when there is no reading."""
    return TIMING_FORMAT.format(elapsed=elapsed) if elapsed > NO_ELAPSED else NO_TIMING


def headline_text(title: str, elapsed: float) -> str:
    """The bold line above the response log."""
    return HEADLINE_FORMAT.format(title=title, timing=timing_text(elapsed))


def level_color(level: str) -> str:
    """The colour one log level paints, grey for a level with no colour."""
    return LEVEL_COLORS.get(level, DEFAULT_LEVEL_COLOR)


def headline_style(color: str) -> str:
    """The style the headline carries, empty before anything was logged."""
    return HEADLINE_STYLE_FORMAT.format(color=color) if color else EMPTY_TEXT


def entry_html(stamp: str, title: str, timing: str, color: str, detail: str) -> str:
    """One response-log entry as the marked-up line the log receives."""
    return ENTRY_HTML_FORMAT.format(
        stamp_color=TIMESTAMP_COLOR,
        stamp=stamp,
        color=color,
        title=title,
        timing=timing,
        detail_color=DETAIL_COLOR,
        detail=detail,
    )


def exchange_title(exchange_id: Any) -> str:
    """One exchange id with its first letter raised, as the labels show it."""
    return str(exchange_id).capitalize()


def probe_host(exchange_id: Any) -> str:
    """The address the raw probe opens a socket to for one exchange."""
    found = PROBE_HOSTS.get(exchange_id)
    if found is not None:
        return found
    return DEFAULT_HOST_FORMAT.format(exchange_id=exchange_id)


def probe_endpoints(exchange_id: Any) -> list:
    """The web addresses the raw probe asks for, for one exchange."""
    found = PROBE_ENDPOINTS.get(exchange_id)
    if found is not None:
        return [list(entry) for entry in found]
    return [
        [
            DEFAULT_ENDPOINT_METHOD,
            DEFAULT_ENDPOINT_URL_FORMAT.format(exchange_id=exchange_id),
            DEFAULT_ENDPOINT_DESC,
        ]
    ]


def reading_of(value: Any) -> Optional[float]:
    """One holding as a number, or None when no reading admits it."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def positive_only(section: Any) -> dict:
    """One balance section: zero and empty dropped, unreadable marked."""
    found = {}
    for key, value in section.items():
        if not value:
            continue
        reading = reading_of(value)
        if reading is None:
            found[key] = UNREADABLE_MARK
        elif reading > NO_HOLDING:
            found[key] = value
    return found


def mapping_or_none(found: Any) -> Optional[dict]:
    """One answer read as a mapping, or None when it is not one."""
    return found if isinstance(found, dict) else None


def body_text(found: Any) -> str:
    """One response body as text, or a mark naming what came back instead."""
    if isinstance(found, str):
        return found
    return UNREADABLE_BODY_FORMAT.format(kind=type(found).__name__)


def status_text_of(status: Any) -> str:
    """One HTTP status as the headline shows it, or the mark when unread."""
    return UNREADABLE_MARK if status is None else str(status)


def market_count_text(count: Any) -> str:
    """One market count as the status line shows it, or the mark when unread."""
    return UNREADABLE_MARK if count is None else str(count)


def markets_summary(markets: dict) -> dict:
    """The Fetch Markets answer: how many pairs, how many spot, the first 50."""
    return {
        "total": len(markets),
        "spot": sum(
            1
            for row in markets.values()
            if isinstance(row, dict) and row.get("type") == SPOT_TYPE
        ),
        "first_50": sorted(str(key) for key in markets)[:MARKETS_SAMPLE_LIMIT],
    }


def close_of(candles: list, at: int) -> Any:
    """One end candle's close, or the mark when that row carries none."""
    if not candles:
        return NO_CLOSE
    row = candles[at]
    if isinstance(row, (list, tuple)) and len(row) > CLOSE_INDEX:
        return row[CLOSE_INDEX]
    return UNREADABLE_MARK


def ohlcv_summary(candles: list) -> dict:
    """The Fetch OHLCV answer: how many candles, and the two end closes."""
    return {
        "candles": len(candles),
        "latest_close": close_of(candles, -1),
        "oldest_close": close_of(candles, 0),
    }


def result_display(result: Any) -> str:
    """One test answer as the text the response log shows.

    A mapping is filtered of empty balances and cut at 3000 characters.
    A sequence reports its length and its first five entries. Anything
    else is shown as it prints.
    """
    if isinstance(result, dict):
        for section in BALANCE_SECTIONS:
            if section in result and isinstance(result[section], dict):
                result[section] = positive_only(result[section])
        display = json.dumps(result, indent=JSON_INDENT, default=str)
        if len(display) > DISPLAY_LIMIT:
            display = display[:DISPLAY_LIMIT] + TRUNCATED_SUFFIX
        return display
    if isinstance(result, list):
        display = LIST_HEAD_FORMAT.format(count=len(result)) + json.dumps(
            result[:LIST_SAMPLE_LIMIT], indent=JSON_INDENT, default=str
        )
        if len(result) > LIST_SAMPLE_LIMIT:
            display += LIST_TAIL_FORMAT.format(count=len(result) - LIST_SAMPLE_LIMIT)
        return display
    return str(result)


def body_display(body: str) -> str:
    """One web answer as the text the response log shows.

    Cut at 1000 characters. A body that parses as a mapping is restated
    as its first ten keys, its product count where it has one, and the
    first 800 characters of the mapping printed out.
    """
    shown = (
        body[:BODY_DISPLAY_LIMIT] + BODY_TRUNCATED_SUFFIX
        if len(body) > BODY_DISPLAY_LIMIT
        else body
    )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return shown
    if not isinstance(parsed, dict):
        return shown
    shown = JSON_KEYS_FORMAT.format(keys=list(parsed.keys())[:JSON_KEYS_LIMIT])
    if isinstance(parsed.get(PRODUCTS_KEY), list):
        shown += PRODUCTS_COUNT_FORMAT.format(count=len(parsed[PRODUCTS_KEY]))
    shown += json.dumps(parsed, indent=JSON_INDENT)[:JSON_BODY_LIMIT]
    return shown


def status_level(indicator: Any) -> str:
    """Green for a green indicator, red for a mapped one, amber for the rest."""
    if indicator in GREEN_INDICATORS:
        return LEVEL_SUCCESS
    if indicator in MAPPABLE_INDICATORS:
        return LEVEL_ERROR
    return LEVEL_WARNING


def exchange_error_text(exc: BaseException) -> str:
    """The venue failure text, from the one formatter the exchange ships.

    Imported when a failure happens rather than at module load, so
    reaching this screen loads no exchange library.
    """
    from ...exchange.ccxt_connector import CCXTConnector

    return CCXTConnector._format_exchange_error(exc)


def supported_exchanges() -> list:
    """Every venue this screen offers, in the order the picker lists them.

    Imported when first asked rather than at module load, so importing
    this file loads no exchange library and reads no settings.
    """
    from ...exchange.ccxt_connector import SUPPORTED_EXCHANGES

    return sorted(SUPPORTED_EXCHANGES.keys())


def exchange_options(exchange_ids: list) -> list:
    """The picker's entries: what each reads as, and the id behind it."""
    return [[exchange_title(found), found] for found in exchange_ids]


def test_buttons() -> list:
    """The seven read-call buttons: label, call name and tooltip."""
    return [list(entry) for entry in TEST_BUTTONS]


class ApiTesterModel:
    """The API tester screen, and every decision it makes.

    ``caller`` takes every outward step: the exchange session, the
    socket, the certificate handshake, the web request, the stored-key
    lookup and the clock. With no caller each of those steps refuses and
    the screen reports the refusal, so a model built bare reaches
    nothing.
    """

    def __init__(self, caller: Any = None, exchange_ids: Optional[list] = None):
        self.caller = caller
        self.exchange_ids = (
            list(exchange_ids) if exchange_ids is not None else supported_exchanges()
        )
        self.exchange_id = self.exchange_ids[0] if self.exchange_ids else EMPTY_TEXT
        self.use_stored = USE_STORED_DEFAULT
        self.manual_visible = not USE_STORED_DEFAULT
        self.api_key = EMPTY_TEXT
        self.api_secret = EMPTY_TEXT
        self.api_passphrase = EMPTY_TEXT
        self.symbol = SYMBOL_DEFAULT
        self.connector = None
        self.connected = False
        self.connect_enabled = True
        self.disconnect_enabled = False
        self.status_text = STATUS_IDLE_TEXT
        self.status_color = STATUS_IDLE_COLOR
        self.headline = RESULT_INFO_TEXT
        self.headline_color = EMPTY_TEXT
        self.entries: list = []
        self.calls: list = []
        self.entries_logged = 0

    def set_exchange(self, exchange_id: Any) -> None:
        """Pick the venue every button on this screen acts against."""
        self.exchange_id = exchange_id

    def set_use_stored(self, on: Any) -> None:
        """Switch between saved keys and the three hand-typed boxes."""
        self.use_stored = bool(on)
        self.manual_visible = not self.use_stored

    def set_symbol(self, symbol: str) -> None:
        """Set the trading pair the ticker, book and candle calls use."""
        self.symbol = symbol

    def set_manual_credentials(self, key: str, secret: str, passphrase: str) -> None:
        """Fill the three hand-typed boxes. No value here reaches the payload."""
        self.api_key = key
        self.api_secret = secret
        self.api_passphrase = passphrase

    def log(
        self,
        title: str,
        detail: str,
        elapsed: float = NO_ELAPSED,
        level: str = LEVEL_INFO,
    ) -> dict:
        """Paint one headline and append one entry to the response log."""
        color = level_color(level)
        timing = timing_text(elapsed)
        self.headline = HEADLINE_FORMAT.format(title=title, timing=timing)
        self.headline_color = color
        stamp = self._stamp()
        entry = {
            "stamp": stamp,
            "title": title,
            "timing": timing,
            "level": level,
            "color": color,
            "detail": detail,
            "html": entry_html(stamp, title, timing, color, detail),
        }
        self.entries.append(entry)
        self.entries_logged += 1
        del self.entries[:-ENTRY_LIMIT]
        self.calls.append([ENTRY_LOGGED, title, level])
        del self.calls[:-CALL_LIMIT]
        return entry

    def _ask(self, step: str, *args):
        """Take one outward step through the caller, or refuse having none."""
        found = getattr(self.caller, step, None) if self.caller is not None else None
        if found is None:
            raise CallerRefused(NO_CALLER_MESSAGE)
        return found(*args)

    def _stamp(self) -> str:
        """The wall-clock time one entry carries, empty when nothing tells it."""
        try:
            return str(self._ask("stamp"))
        except Exception:
            return EMPTY_TEXT

    def _started(self):
        """A clock reading a later elapsed is measured from."""
        try:
            return self._ask("started")
        except Exception:
            return None

    def _elapsed_ms(self, started: Any) -> float:
        """How long one step took, zero when nothing measured it."""
        try:
            return float(self._ask("elapsed_ms", started))
        except Exception:
            return float(NO_ELAPSED)

    def _set_status(self, text: str, color: str) -> None:
        self.status_text = text
        self.status_color = color

    def do_connect(self) -> None:
        """Open an isolated session on the selected venue."""
        exchange = exchange_title(self.exchange_id)
        self._set_status(
            STATUS_CONNECTING_FORMAT.format(exchange=exchange),
            STATUS_CONNECTING_COLOR,
        )
        self.connect_enabled = False
        self.calls.append([CONNECT_STARTED, self.exchange_id])
        try:
            if self.use_stored:
                resolved = self._stored_credentials(exchange)
                if resolved is None:
                    return
                key, secret, passphrase = resolved
            else:
                key = self.api_key.strip()
                secret = self.api_secret.strip()
                passphrase = self.api_passphrase.strip()
                if not key or not secret:
                    self.log(NO_MANUAL_TITLE, NO_MANUAL_DETAIL, level=LEVEL_ERROR)
                    self.calls.append([CONNECT_REFUSED, NO_MANUAL_TITLE])
                    return
            started = self._started()
            session = self._ask("connect", self.exchange_id, key, secret, passphrase)
            elapsed = self._elapsed_ms(started)
            markets = self._market_count(session)
            shown = market_count_text(markets)
            self.connector = session
            self.connected = True
            self.connect_enabled = False
            self.disconnect_enabled = True
            self._set_status(
                STATUS_CONNECTED_FORMAT.format(exchange=exchange, markets=shown),
                STATUS_CONNECTED_COLOR,
            )
            self.log(
                CONNECTED_TITLE_FORMAT.format(exchange=exchange),
                CONNECTED_DETAIL_FORMAT.format(markets=shown),
                elapsed,
                LEVEL_SUCCESS,
            )
            self.calls.append([CONNECT_OPENED, markets])
            self._wire_history(session)
        except Exception as exc:
            self._set_status(STATUS_FAILED_TEXT, STATUS_FAILED_COLOR)
            self.log(CONNECT_FAILED_TITLE, exchange_error_text(exc), level=LEVEL_ERROR)
            self.calls.append([CONNECT_FAILED, type(exc).__name__])
        finally:
            if not self.connected:
                self.connect_enabled = True

    def _stored_credentials(self, exchange: str):
        """The saved key, secret and passphrase, or None having reported why."""
        try:
            found = self._ask("stored_credentials", self.exchange_id)
        except Exception:
            found = None
        if found is None:
            self.log(NO_SETTINGS_TITLE, NO_SETTINGS_DETAIL, level=LEVEL_ERROR)
            self.calls.append([CONNECT_REFUSED, NO_SETTINGS_TITLE])
            return None
        if not found.get("api_key"):
            self.log(
                NO_CREDENTIALS_TITLE,
                NO_CREDENTIALS_FORMAT.format(exchange=exchange),
                level=LEVEL_ERROR,
            )
            self.calls.append([CONNECT_REFUSED, NO_CREDENTIALS_TITLE])
            return None
        return (
            found.get("api_key", EMPTY_TEXT),
            found.get("api_secret", EMPTY_TEXT),
            found.get("passphrase", EMPTY_TEXT),
        )

    def _market_count(self, session: Any) -> Optional[int]:
        """How many pairs the fresh session loaded, None when nothing read it."""
        try:
            return int(self._ask("market_count", session))
        except Exception:
            return None

    def _wire_history(self, session: Any) -> None:
        """Hand the fresh session to the trade-history screen, if it is up."""
        try:
            self._ask("wire_history", session)
            self.calls.append([HISTORY_WIRED])
        except Exception as exc:
            logger.debug(HISTORY_CALLBACK_LOG, exc)
            self.calls.append([HISTORY_SKIPPED, type(exc).__name__])

    def do_disconnect(self) -> None:
        """Close the session, and say so whether or not a close was attempted."""
        attempted = self.connector is not None
        failure = None
        if attempted:
            started = self._started()
            try:
                self._ask("disconnect", self.connector)
            except Exception as exc:
                failure = exc
            self._elapsed_ms(started)
            if failure is not None:
                self.log(
                    DISCONNECT_FAILED_TITLE,
                    DISCONNECT_FAILED_FORMAT.format(
                        error=type(failure).__name__, message=failure
                    ),
                    level=LEVEL_ERROR,
                )
                self.calls.append([DISCONNECT_FAILED, type(failure).__name__])
            self.connector = None
        self.connected = False
        self.connect_enabled = True
        self.disconnect_enabled = False
        self._set_status(STATUS_DISCONNECTED_TEXT, STATUS_DISCONNECTED_COLOR)
        if not attempted:
            self.log(NOTHING_OPEN_TITLE, NOTHING_OPEN_DETAIL, level=LEVEL_INFO)
            self.calls.append([DISCONNECT_NOTHING_OPEN])
            return
        self.log(DISCONNECTED_TITLE, DISCONNECTED_DETAIL, level=LEVEL_INFO)
        self.calls.append([DISCONNECT_CLOSED, failure is None])

    def run_test(self, test: str) -> None:
        """Run one of the seven read calls and show what came back."""
        if not self.connected or self.connector is None:
            self.log(NOT_CONNECTED_TITLE, NOT_CONNECTED_DETAIL, level=LEVEL_ERROR)
            self.calls.append([TEST_REFUSED, test])
            return
        symbol = self.symbol.strip()
        self.log(
            RUNNING_TITLE_FORMAT.format(test=test),
            RUNNING_DETAIL_FORMAT.format(symbol=symbol),
            level=LEVEL_INFO,
        )
        started = self._started()
        nothing: dict = {}
        try:
            result = self._call_test(test, symbol, nothing)
            elapsed = self._elapsed_ms(started)
            if result is nothing:
                self.log(
                    TEST_UNKNOWN_FORMAT.format(test=test),
                    TEST_UNKNOWN_DETAIL,
                    elapsed,
                    LEVEL_WARNING,
                )
                self.calls.append([TEST_UNKNOWN, test])
                return
            display = result_display(result)
            self.log(TEST_OK_FORMAT.format(test=test), display, elapsed, LEVEL_SUCCESS)
            self.calls.append([TEST_RAN, test])
        except Exception as exc:
            elapsed = self._elapsed_ms(started)
            self.log(
                TEST_FAILED_FORMAT.format(test=test),
                exchange_error_text(exc),
                elapsed,
                LEVEL_ERROR,
            )
            self.calls.append([TEST_FAILED, test, type(exc).__name__])

    def _call_test(self, test: str, symbol: str, nothing: dict):
        """The answer one named test asks the venue for.

        An unrecognised name reaches the venue for nothing and answers
        ``nothing``, which is what tells a real answer from no call.
        """
        if test == TEST_MARKETS:
            return markets_summary(self._ask("markets", self.connector))
        if test == TEST_TICKER:
            return self._ask("ticker", self.connector, symbol)
        if test == TEST_BALANCES:
            return self._ask("balance", self.connector)
        if test == TEST_ORDERBOOK:
            return self._ask("order_book", self.connector, symbol, ORDERBOOK_LIMIT)
        if test == TEST_OHLCV:
            return ohlcv_summary(
                self._ask("ohlcv", self.connector, symbol, OHLCV_TIMEFRAME, OHLCV_LIMIT)
            )
        if test == TEST_OPEN_ORDERS:
            return self._ask("open_orders", self.connector, symbol)
        if test == TEST_TRADES:
            return self._ask("my_trades", self.connector, symbol, TRADES_LIMIT)
        return nothing

    def raw_http_probe(self) -> None:
        """Go round the exchange library: socket, certificate, then requests."""
        host = probe_host(self.exchange_id)
        self.log(
            SSL_DIAGNOSTIC_TITLE,
            SSL_DIAGNOSTIC_FORMAT.format(host=host, port=PROBE_PORT),
            level=LEVEL_INFO,
        )
        if not self._probe_tcp(host):
            return
        self._probe_handshake(host)
        self._probe_certifi(host)
        self._probe_endpoints()

    def _probe_tcp(self, host: str) -> bool:
        """Open a plain socket to the venue. False when it cannot be opened."""
        started = self._started()
        try:
            self._ask("tcp", host, PROBE_PORT, PROBE_TIMEOUT_S)
        except Exception as exc:
            self.log(
                TCP_FAILED_TITLE,
                TCP_FAILED_FORMAT.format(host=host, port=PROBE_PORT, message=exc),
                level=LEVEL_ERROR,
            )
            self.calls.append([PROBE_TCP, False])
            return False
        elapsed = self._elapsed_ms(started)
        self.log(
            TCP_OK_FORMAT.format(elapsed=elapsed),
            TCP_OK_DETAIL_FORMAT.format(host=host, port=PROBE_PORT),
            level=LEVEL_SUCCESS,
        )
        self.calls.append([PROBE_TCP, True])
        return True

    def _probe_handshake(self, host: str) -> None:
        """Shake hands with the venue using the trust store Python ships."""
        started = self._started()
        try:
            found = self._ask("handshake", host, PROBE_PORT, PROBE_TIMEOUT_S, None)
        except Exception as exc:
            if self._is_cert_error(exc):
                self.log(
                    SSL_CERT_FAILED_TITLE,
                    SSL_CERT_FAILED_FORMAT.format(host=host, message=exc),
                    level=LEVEL_ERROR,
                )
            else:
                self.log(
                    SSL_FAILED_TITLE,
                    ERROR_LINE_FORMAT.format(error=type(exc).__name__, message=exc),
                    level=LEVEL_ERROR,
                )
            self.calls.append([PROBE_HANDSHAKE, False])
            return
        elapsed = self._elapsed_ms(started)
        read = mapping_or_none(found)
        self.log(
            SSL_OK_FORMAT.format(elapsed=elapsed),
            SSL_OK_DETAIL_FORMAT.format(
                protocol=(read or {}).get("protocol", CERT_UNKNOWN),
                cipher=(read or {}).get("cipher", CERT_UNKNOWN),
                common_name=(read or {}).get("common_name", CERT_UNKNOWN),
                issuer=(read or {}).get("issuer", CERT_UNKNOWN),
                not_after=(read or {}).get("not_after", CERT_UNKNOWN),
            ),
            level=LEVEL_SUCCESS,
        )
        if read is None:
            self.calls.append([PROBE_HANDSHAKE_UNREAD, type(found).__name__])
            return
        self.calls.append([PROBE_HANDSHAKE, True])

    def _is_cert_error(self, exc: BaseException) -> bool:
        """Whether one handshake failure was the certificate being refused."""
        try:
            return bool(self._ask("is_cert_error", exc))
        except Exception:
            return False

    def _probe_certifi(self, host: str) -> None:
        """Shake hands again using the certifi trust store, where it is here."""
        try:
            bundle = self._ask("certifi_bundle")
        except Exception:
            self.log(CERTIFI_MISSING_TITLE, CERTIFI_MISSING_DETAIL, level=LEVEL_WARNING)
            self.calls.append([PROBE_CERTIFI, False])
            return
        started = self._started()
        try:
            found = self._ask("handshake", host, PROBE_PORT, PROBE_TIMEOUT_S, bundle)
        except Exception as exc:
            self.log(
                CERTIFI_FAILED_TITLE,
                ERROR_LINE_FORMAT.format(error=type(exc).__name__, message=exc),
                level=LEVEL_ERROR,
            )
            self.calls.append([PROBE_CERTIFI, False])
            return
        elapsed = self._elapsed_ms(started)
        self.log(
            CERTIFI_OK_FORMAT.format(elapsed=elapsed),
            CERTIFI_OK_DETAIL_FORMAT.format(
                bundle=bundle,
                protocol=(mapping_or_none(found) or {}).get("protocol", CERT_UNKNOWN),
            ),
            level=LEVEL_SUCCESS,
        )
        self.calls.append([PROBE_CERTIFI, True])

    def _probe_endpoints(self) -> None:
        """Ask each of the venue's public addresses and report every answer."""
        endpoints = probe_endpoints(self.exchange_id)
        self.log(
            HTTP_PROBES_TITLE,
            HTTP_PROBES_FORMAT.format(count=len(endpoints)),
            level=LEVEL_INFO,
        )
        green = 0
        green_with_body = 0
        for row in endpoints:
            url, desc = self._endpoint_of(row)
            started = self._started()
            self.calls.append([PROBE_REQUESTED, url])
            try:
                answer = self._ask("http", url, PROBE_TIMEOUT_S, list(PROBE_HEADERS))
            except Exception as exc:
                self._log_request_failure(exc, url, desc, self._elapsed_ms(started))
                continue
            elapsed = self._elapsed_ms(started)
            read = mapping_or_none(answer)
            if read is None:
                self._log_unreadable_answer(answer, url, desc, elapsed)
                continue
            headers = mapping_or_none(read.get("headers")) or {}
            body = body_text(read.get("body", NO_BODY))
            status = read.get("status")
            self._log_answer(read.get("status"), desc, url, headers, body, elapsed)
            green += 1
            if body:
                green_with_body += 1
            if status is None:
                self.calls.append([PROBE_UNREAD, url])
        self.calls.append([PROBE_GREEN, green, green_with_body])

    def _endpoint_of(self, row: Any) -> tuple:
        """The address and wording of one endpoint row, however wide it is."""
        found = list(row) if isinstance(row, (list, tuple)) else []
        url = found[1] if len(found) > 1 else EMPTY_TEXT
        desc = found[2] if len(found) > 2 else DEFAULT_ENDPOINT_DESC
        return url, desc

    def _log_answer(
        self,
        status: Any,
        desc: str,
        url: str,
        headers: dict,
        body: str,
        elapsed: float,
    ) -> None:
        """Report one answered request, marked unread when no status came back."""
        unread = status is None
        shown = status_text_of(status)
        detail = HTTP_OK_DETAIL_FORMAT.format(
            desc=desc,
            url=url,
            status=shown,
            content_type=headers.get(CONTENT_TYPE_HEADER, UNKNOWN_HEADER),
            content_length=headers.get(CONTENT_LENGTH_HEADER, UNKNOWN_HEADER),
            body=body_display(body),
        )
        self.log(
            (HTTP_UNREAD_TITLE_FORMAT if unread else HTTP_OK_TITLE_FORMAT).format(
                status=shown, desc=desc
            ),
            detail + UNREAD_STATUS_NOTE if unread else detail,
            elapsed,
            LEVEL_WARNING if unread else LEVEL_SUCCESS,
        )

    def _log_unreadable_answer(
        self, answer: Any, url: str, desc: str, elapsed: float
    ) -> None:
        """Report a request whose answer is not a mapping this screen reads."""
        self.log(
            UNREADABLE_ANSWER_TITLE_FORMAT.format(desc=desc),
            UNREADABLE_ANSWER_DETAIL_FORMAT.format(
                desc=desc, url=url, kind=type(answer).__name__
            ),
            elapsed,
            LEVEL_WARNING,
        )
        self.calls.append([PROBE_UNREAD, url])

    def _log_request_failure(
        self, exc: BaseException, url: str, desc: str, elapsed: float
    ) -> None:
        """Report one failed request as the kind of failure it was."""
        kind = self._request_failure_kind(exc)
        if kind == FAILURE_HTTP:
            status = getattr(exc, "code", EMPTY_TEXT)
            self.log(
                HTTP_ERROR_TITLE_FORMAT.format(status=status, desc=desc),
                HTTP_ERROR_DETAIL_FORMAT.format(
                    desc=desc,
                    url=url,
                    status=status,
                    reason=getattr(exc, "reason", EMPTY_TEXT),
                    body=self._error_body(exc),
                ),
                elapsed,
                LEVEL_ERROR,
            )
            return
        if kind == FAILURE_URL:
            self.log(
                UNREACHABLE_TITLE_FORMAT.format(desc=desc),
                UNREACHABLE_DETAIL_FORMAT.format(
                    desc=desc, url=url, reason=getattr(exc, "reason", EMPTY_TEXT)
                ),
                elapsed,
                LEVEL_ERROR,
            )
            return
        self.log(
            PROBE_ERROR_TITLE_FORMAT.format(desc=desc),
            PROBE_ERROR_DETAIL_FORMAT.format(
                url=url, error=type(exc).__name__, message=exc
            ),
            elapsed,
            LEVEL_ERROR,
        )

    def _request_failure_kind(self, exc: BaseException) -> str:
        """Which of the three request failures this is: http, url or other."""
        try:
            return str(self._ask("request_failure_kind", exc))
        except Exception:
            return FAILURE_OTHER

    def _error_body(self, exc: BaseException) -> str:
        """The first 500 characters the failing request answered with."""
        try:
            return str(self._ask("error_body", exc))[:HTTP_ERROR_BODY_LIMIT]
        except Exception:
            return NO_BODY

    def check_exchange_status(self) -> None:
        """Read the venue's own status page and say what it declares."""
        exchange = exchange_title(self.exchange_id)
        url = STATUS_PAGE_URLS.get(self.exchange_id)
        if not url:
            self.log(
                NO_STATUS_PAGE_TITLE,
                NO_STATUS_PAGE_FORMAT.format(exchange=exchange),
                level=LEVEL_WARNING,
            )
            return
        self.log(
            CHECKING_STATUS_TITLE,
            CHECKING_STATUS_FORMAT.format(exchange=exchange),
            level=LEVEL_INFO,
        )
        started = self._started()
        self.calls.append([STATUS_REQUESTED, url])
        try:
            answer = self._ask("http", url, PROBE_TIMEOUT_S, list(STATUS_HEADERS))
            body = body_text((mapping_or_none(answer) or {}).get("body", NO_BODY))
            data = json.loads(body)
            elapsed = self._elapsed_ms(started)
            if isinstance(data, dict) and STATUS_KEY in data:
                self._log_indicator(exchange, data, elapsed)
            else:
                self.log(
                    PLAIN_STATUS_TITLE,
                    json.dumps(data, indent=JSON_INDENT)[:PLAIN_STATUS_LIMIT],
                    elapsed,
                    LEVEL_INFO,
                )
        except Exception as exc:
            self.log(
                STATUS_CHECK_FAILED_TITLE,
                ERROR_LINE_FORMAT.format(error=type(exc).__name__, message=exc),
                level=LEVEL_ERROR,
            )

    def _log_indicator(self, exchange: str, data: dict, elapsed: float) -> None:
        """Report the word the status document carried, and paint it."""
        section = mapping_or_none(data[STATUS_KEY]) or {}
        indicator = section.get(INDICATOR_KEY, UNKNOWN_INDICATOR)
        description = section.get(DESCRIPTION_KEY, UNKNOWN_INDICATOR)
        level = status_level(indicator)
        self.log(
            STATUS_TITLE_FORMAT.format(description=description),
            STATUS_DETAIL_FORMAT.format(
                exchange=exchange,
                indicator=str(indicator).upper(),
                description=description,
                raw=json.dumps(data, indent=JSON_INDENT)[:STATUS_RAW_LIMIT],
            ),
            elapsed,
            level,
        )
        seen = str(section.get(INDICATOR_KEY, EMPTY_TEXT))[:INDICATOR_SEEN_LIMIT]
        self.calls.append(
            [STATUS_READ if seen in MAPPABLE_INDICATORS else STATUS_UNMAPPED, seen]
        )


def credentials_filled(model: "ApiTesterModel") -> list:
    """Whether each of the three credential boxes holds anything.

    What was typed is never carried. Only that something was.
    """
    return [
        bool(model.api_key),
        bool(model.api_secret),
        bool(model.api_passphrase),
    ]


def build_model(caller: Any = None, exchange_ids: Optional[list] = None):
    """One model, ready for its first press."""
    return ApiTesterModel(caller=caller, exchange_ids=exchange_ids)


def build_view_model(model: ApiTesterModel) -> dict:
    """Return the whole surface state as one serialisable dict.

    No typed key, secret or passphrase is carried. Only whether each of
    the three boxes holds anything.
    """
    return {
        "method": METHOD,
        "connection_title": CONNECTION_TITLE,
        "exchange_label": EXCHANGE_LABEL,
        "exchange_options": exchange_options(model.exchange_ids),
        "exchange_ids": list(model.exchange_ids),
        "exchange_id": model.exchange_id,
        "use_stored_label": USE_STORED_LABEL,
        "use_stored_tooltip": USE_STORED_TIP,
        "use_stored_default": USE_STORED_DEFAULT,
        "use_stored": model.use_stored,
        "manual_visible": model.manual_visible,
        "credential_placeholders": list(CREDENTIAL_PLACEHOLDERS),
        "echo_mode": ECHO_MODE,
        "credentials_hidden": CREDENTIALS_HIDDEN,
        "credentials_filled": credentials_filled(model),
        "connect_label": CONNECT_LABEL,
        "connect_tooltip": CONNECT_TIP,
        "connect_enabled": model.connect_enabled,
        "disconnect_label": DISCONNECT_LABEL,
        "disconnect_enabled": model.disconnect_enabled,
        "status_text": model.status_text,
        "status_color": model.status_color,
        "status_style": STATUS_STYLE_FORMAT.format(color=model.status_color),
        "status_idle_text": STATUS_IDLE_TEXT,
        "status_connecting_format": STATUS_CONNECTING_FORMAT,
        "status_connected_format": STATUS_CONNECTED_FORMAT,
        "status_failed_text": STATUS_FAILED_TEXT,
        "status_disconnected_text": STATUS_DISCONNECTED_TEXT,
        "status_idle_color": STATUS_IDLE_COLOR,
        "status_connecting_color": STATUS_CONNECTING_COLOR,
        "status_connected_color": STATUS_CONNECTED_COLOR,
        "status_failed_color": STATUS_FAILED_COLOR,
        "status_disconnected_color": STATUS_DISCONNECTED_COLOR,
        "status_style_format": STATUS_STYLE_FORMAT,
        "operations_title": OPERATIONS_TITLE,
        "response_title": RESPONSE_TITLE,
        "symbol": model.symbol,
        "symbol_default": SYMBOL_DEFAULT,
        "symbol_tooltip": SYMBOL_TIP,
        "test_buttons": test_buttons(),
        "test_names": list(TEST_NAMES),
        "diagnostics_label": DIAGNOSTICS_LABEL,
        "diagnostics_color": DIAGNOSTICS_COLOR,
        "diagnostics_style": DIAGNOSTICS_STYLE_FORMAT.format(color=DIAGNOSTICS_COLOR),
        "diagnostics_style_format": DIAGNOSTICS_STYLE_FORMAT,
        "diagnostics_alignment": DIAGNOSTICS_ALIGNMENT,
        "diagnostics_alignment_value": DIAGNOSTICS_ALIGNMENT_VALUE,
        "raw_probe_label": RAW_PROBE_LABEL,
        "raw_probe_tooltip": RAW_PROBE_TIP,
        "status_page_label": STATUS_PAGE_LABEL,
        "status_page_tooltip": STATUS_PAGE_TIP,
        "result_placeholder": RESULT_PLACEHOLDER,
        "result_info_text": RESULT_INFO_TEXT,
        "result_info_word_wrap": RESULT_INFO_WORD_WRAP,
        "result_read_only": RESULT_READ_ONLY,
        "headline": model.headline,
        "headline_color": model.headline_color,
        "headline_style": headline_style(model.headline_color),
        "headline_style_format": HEADLINE_STYLE_FORMAT,
        "headline_format": HEADLINE_FORMAT,
        "entries": [dict(found) for found in model.entries],
        "entry_count": len(model.entries),
        "entries_logged": model.entries_logged,
        "entry_limit": ENTRY_LIMIT,
        "call_limit": CALL_LIMIT,
        "entry_html_format": ENTRY_HTML_FORMAT,
        "entry_marks": dict(ENTRY_MARKS),
        "entry_mark_order": list(ENTRY_MARKS),
        "entry_slots": dict(ENTRY_SLOTS),
        "entry_slot_order": list(ENTRY_SLOTS),
        "level_colors": dict(LEVEL_COLORS),
        "level_color_order": list(LEVEL_COLORS),
        "default_level_color": DEFAULT_LEVEL_COLOR,
        "timestamp_color": TIMESTAMP_COLOR,
        "detail_color": DETAIL_COLOR,
        "timestamp_format": TIMESTAMP_FORMAT,
        "timing_format": TIMING_FORMAT,
        "no_timing": NO_TIMING,
        "no_elapsed": NO_ELAPSED,
        "level_info": LEVEL_INFO,
        "level_success": LEVEL_SUCCESS,
        "level_warning": LEVEL_WARNING,
        "level_error": LEVEL_ERROR,
        "connected": model.connected,
        "connector_held": model.connector is not None,
        "layout_margins": list(LAYOUT_MARGINS),
        "layout_spacing": LAYOUT_SPACING,
        "group_margins": list(GROUP_MARGINS),
        "connection_spacing": CONNECTION_SPACING,
        "manual_margins": list(MANUAL_MARGINS),
        "manual_spacing": MANUAL_SPACING,
        "operations_spacing": OPERATIONS_SPACING,
        "splitter_orientation": SPLITTER_ORIENTATION,
        "splitter_handle_width": SPLITTER_HANDLE_WIDTH,
        "splitter_children_collapsible": SPLITTER_CHILDREN_COLLAPSIBLE,
        "splitter_sizes": list(SPLITTER_SIZES),
        "no_settings_title": NO_SETTINGS_TITLE,
        "no_settings_detail": NO_SETTINGS_DETAIL,
        "no_credentials_title": NO_CREDENTIALS_TITLE,
        "no_credentials_format": NO_CREDENTIALS_FORMAT,
        "no_manual_title": NO_MANUAL_TITLE,
        "no_manual_detail": NO_MANUAL_DETAIL,
        "connected_title_format": CONNECTED_TITLE_FORMAT,
        "connected_detail_format": CONNECTED_DETAIL_FORMAT,
        "connect_failed_title": CONNECT_FAILED_TITLE,
        "no_markets": NO_MARKETS,
        "disconnect_failed_title": DISCONNECT_FAILED_TITLE,
        "disconnect_failed_format": DISCONNECT_FAILED_FORMAT,
        "disconnected_title": DISCONNECTED_TITLE,
        "disconnected_detail": DISCONNECTED_DETAIL,
        "nothing_open_title": NOTHING_OPEN_TITLE,
        "nothing_open_detail": NOTHING_OPEN_DETAIL,
        "history_callback_log": HISTORY_CALLBACK_LOG,
        "not_connected_title": NOT_CONNECTED_TITLE,
        "not_connected_detail": NOT_CONNECTED_DETAIL,
        "running_title_format": RUNNING_TITLE_FORMAT,
        "running_detail_format": RUNNING_DETAIL_FORMAT,
        "test_ok_format": TEST_OK_FORMAT,
        "test_failed_format": TEST_FAILED_FORMAT,
        "test_unknown_format": TEST_UNKNOWN_FORMAT,
        "test_unknown_detail": TEST_UNKNOWN_DETAIL,
        "markets_sample_limit": MARKETS_SAMPLE_LIMIT,
        "spot_type": SPOT_TYPE,
        "orderbook_limit": ORDERBOOK_LIMIT,
        "ohlcv_timeframe": OHLCV_TIMEFRAME,
        "ohlcv_limit": OHLCV_LIMIT,
        "trades_limit": TRADES_LIMIT,
        "close_index": CLOSE_INDEX,
        "no_close": NO_CLOSE,
        "balance_sections": list(BALANCE_SECTIONS),
        "no_holding": NO_HOLDING,
        "unreadable_mark": UNREADABLE_MARK,
        "json_indent": JSON_INDENT,
        "display_limit": DISPLAY_LIMIT,
        "truncated_suffix": TRUNCATED_SUFFIX,
        "list_head_format": LIST_HEAD_FORMAT,
        "list_sample_limit": LIST_SAMPLE_LIMIT,
        "list_tail_format": LIST_TAIL_FORMAT,
        "test_markets": TEST_MARKETS,
        "test_ticker": TEST_TICKER,
        "test_balances": TEST_BALANCES,
        "test_orderbook": TEST_ORDERBOOK,
        "test_ohlcv": TEST_OHLCV,
        "test_open_orders": TEST_OPEN_ORDERS,
        "test_trades": TEST_TRADES,
        "probe_hosts": dict(PROBE_HOSTS),
        "probe_host_order": list(PROBE_HOSTS),
        "probe_host": probe_host(model.exchange_id),
        "default_host_format": DEFAULT_HOST_FORMAT,
        "probe_port": PROBE_PORT,
        "probe_timeout_s": PROBE_TIMEOUT_S,
        "probe_endpoints": probe_endpoints(model.exchange_id),
        "probe_endpoint_table": {
            key: [list(row) for row in rows] for key, rows in PROBE_ENDPOINTS.items()
        },
        "probe_endpoint_table_order": list(PROBE_ENDPOINTS),
        "default_endpoint_method": DEFAULT_ENDPOINT_METHOD,
        "default_endpoint_url_format": DEFAULT_ENDPOINT_URL_FORMAT,
        "default_endpoint_desc": DEFAULT_ENDPOINT_DESC,
        "probe_headers": [list(row) for row in PROBE_HEADERS],
        "status_headers": [list(row) for row in STATUS_HEADERS],
        "ssl_diagnostic_title": SSL_DIAGNOSTIC_TITLE,
        "ssl_diagnostic_format": SSL_DIAGNOSTIC_FORMAT,
        "tcp_ok_format": TCP_OK_FORMAT,
        "tcp_ok_detail_format": TCP_OK_DETAIL_FORMAT,
        "tcp_failed_title": TCP_FAILED_TITLE,
        "tcp_failed_format": TCP_FAILED_FORMAT,
        "ssl_ok_format": SSL_OK_FORMAT,
        "ssl_ok_detail_format": SSL_OK_DETAIL_FORMAT,
        "cert_unknown": CERT_UNKNOWN,
        "ssl_cert_failed_title": SSL_CERT_FAILED_TITLE,
        "ssl_cert_failed_format": SSL_CERT_FAILED_FORMAT,
        "ssl_failed_title": SSL_FAILED_TITLE,
        "error_line_format": ERROR_LINE_FORMAT,
        "certifi_ok_format": CERTIFI_OK_FORMAT,
        "certifi_ok_detail_format": CERTIFI_OK_DETAIL_FORMAT,
        "certifi_missing_title": CERTIFI_MISSING_TITLE,
        "certifi_missing_detail": CERTIFI_MISSING_DETAIL,
        "certifi_failed_title": CERTIFI_FAILED_TITLE,
        "http_probes_title": HTTP_PROBES_TITLE,
        "http_probes_format": HTTP_PROBES_FORMAT,
        "body_display_limit": BODY_DISPLAY_LIMIT,
        "body_truncated_suffix": BODY_TRUNCATED_SUFFIX,
        "json_keys_limit": JSON_KEYS_LIMIT,
        "json_keys_format": JSON_KEYS_FORMAT,
        "products_key": PRODUCTS_KEY,
        "products_count_format": PRODUCTS_COUNT_FORMAT,
        "json_body_limit": JSON_BODY_LIMIT,
        "unknown_header": UNKNOWN_HEADER,
        "content_type_header": CONTENT_TYPE_HEADER,
        "content_length_header": CONTENT_LENGTH_HEADER,
        "http_ok_title_format": HTTP_OK_TITLE_FORMAT,
        "http_ok_detail_format": HTTP_OK_DETAIL_FORMAT,
        "http_error_title_format": HTTP_ERROR_TITLE_FORMAT,
        "http_error_detail_format": HTTP_ERROR_DETAIL_FORMAT,
        "http_error_body_limit": HTTP_ERROR_BODY_LIMIT,
        "unreachable_title_format": UNREACHABLE_TITLE_FORMAT,
        "unreachable_detail_format": UNREACHABLE_DETAIL_FORMAT,
        "probe_error_title_format": PROBE_ERROR_TITLE_FORMAT,
        "probe_error_detail_format": PROBE_ERROR_DETAIL_FORMAT,
        "http_unread_title_format": HTTP_UNREAD_TITLE_FORMAT,
        "unreadable_answer_title_format": UNREADABLE_ANSWER_TITLE_FORMAT,
        "unreadable_answer_detail_format": UNREADABLE_ANSWER_DETAIL_FORMAT,
        "unread_status_note": UNREAD_STATUS_NOTE,
        "unreadable_body_format": UNREADABLE_BODY_FORMAT,
        "no_body": NO_BODY,
        "failure_http": FAILURE_HTTP,
        "failure_url": FAILURE_URL,
        "failure_other": FAILURE_OTHER,
        "status_page_urls": dict(STATUS_PAGE_URLS),
        "status_page_order": list(STATUS_PAGE_URLS),
        "status_page_url": STATUS_PAGE_URLS.get(model.exchange_id, EMPTY_TEXT),
        "mappable_indicators": list(MAPPABLE_INDICATORS),
        "green_indicators": list(GREEN_INDICATORS),
        "indicator_seen_limit": INDICATOR_SEEN_LIMIT,
        "unknown_indicator": UNKNOWN_INDICATOR,
        "status_key": STATUS_KEY,
        "indicator_key": INDICATOR_KEY,
        "description_key": DESCRIPTION_KEY,
        "no_status_page_title": NO_STATUS_PAGE_TITLE,
        "no_status_page_format": NO_STATUS_PAGE_FORMAT,
        "checking_status_title": CHECKING_STATUS_TITLE,
        "checking_status_format": CHECKING_STATUS_FORMAT,
        "status_title_format": STATUS_TITLE_FORMAT,
        "status_detail_format": STATUS_DETAIL_FORMAT,
        "status_raw_limit": STATUS_RAW_LIMIT,
        "plain_status_title": PLAIN_STATUS_TITLE,
        "plain_status_limit": PLAIN_STATUS_LIMIT,
        "status_check_failed_title": STATUS_CHECK_FAILED_TITLE,
        "empty_text": EMPTY_TEXT,
        "skin": dict(SKIN),
        "style_sheet": STYLE_SHEET,
        "timers": dict(TIMERS),
        "timer_delays_ms": list(TIMER_DELAYS_MS),
        "bus_topics": list(BUS_TOPICS),
        "actions": dict(ACTIONS),
        "actions_order": list(ACTIONS),
        "no_caller_message": NO_CALLER_MESSAGE,
        "logger_name": LOGGER_NAME,
        "calls": [list(call) for call in model.calls],
        "call_count": len(model.calls),
        "call_names": list(CALL_NAMES),
    }


_PANE_MODEL: Optional[ApiTesterModel] = None


def pane_model() -> ApiTesterModel:
    """The one model the bridge keeps, built on the first request.

    Built here rather than at module load: a model built while this file
    is imported would read the venue registry before any test could
    redirect it.
    """
    global _PANE_MODEL
    if _PANE_MODEL is None:
        _PANE_MODEL = ApiTesterModel()
    return _PANE_MODEL


def view_model(params: dict) -> dict:
    """Bridge handler for ``api_tester_tab.state``.

    Reads ``reset``, ``exchange_id``, ``use_stored``, ``symbol``,
    ``connect``, ``disconnect``, ``test``, ``raw_probe`` and
    ``status_page`` from the request parameters. The screen keeps its
    response log between calls because the shipped screen does;
    ``reset`` is what a fresh paint sends.
    """
    global _PANE_MODEL
    if params.get("reset", False):
        _PANE_MODEL = None
    model = pane_model()
    if params.get("exchange_id") is not None:
        model.set_exchange(params["exchange_id"])
    if params.get("use_stored") is not None:
        model.set_use_stored(params["use_stored"])
    if params.get("symbol") is not None:
        model.set_symbol(params["symbol"])
    if params.get("connect"):
        model.do_connect()
    if params.get("disconnect"):
        model.do_disconnect()
    if params.get("test") is not None:
        model.run_test(params["test"])
    if params.get("raw_probe"):
        model.raw_http_probe()
    if params.get("status_page"):
        model.check_exchange_status()
    return build_view_model(model)
