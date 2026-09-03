// Draws the API tester screen, binding its module onto the page global.
(function (global) {
  "use strict";

  var ACTIONS = "actions";
  var ACTIONS_ORDER = "actions_order";
  var BALANCE_SECTIONS = "balance_sections";
  var BODY_DISPLAY_LIMIT = "body_display_limit";
  var BODY_TRUNCATED_SUFFIX = "body_truncated_suffix";
  var BUS_TOPICS = "bus_topics";
  var CALLS = "calls";
  var CALL_COUNT = "call_count";
  var CALL_LIMIT = "call_limit";
  var CALL_NAMES = "call_names";
  var CERTIFI_FAILED_TITLE = "certifi_failed_title";
  var CERTIFI_MISSING_DETAIL = "certifi_missing_detail";
  var CERTIFI_MISSING_TITLE = "certifi_missing_title";
  var CERTIFI_OK_DETAIL_FORMAT = "certifi_ok_detail_format";
  var CERTIFI_OK_FORMAT = "certifi_ok_format";
  var CERT_UNKNOWN = "cert_unknown";
  var CHECKING_STATUS_FORMAT = "checking_status_format";
  var CHECKING_STATUS_TITLE = "checking_status_title";
  var CLOSE_INDEX = "close_index";
  var CONNECTED = "connected";
  var CONNECTED_DETAIL_FORMAT = "connected_detail_format";
  var CONNECTED_TITLE_FORMAT = "connected_title_format";
  var CONNECTION_SPACING = "connection_spacing";
  var CONNECTION_TITLE = "connection_title";
  var CONNECTOR_HELD = "connector_held";
  var CONNECT_ENABLED = "connect_enabled";
  var CONNECT_FAILED_TITLE = "connect_failed_title";
  var CONNECT_LABEL = "connect_label";
  var CONNECT_TOOLTIP = "connect_tooltip";
  var CONTENT_LENGTH_HEADER = "content_length_header";
  var CONTENT_TYPE_HEADER = "content_type_header";
  var CREDENTIALS_FILLED = "credentials_filled";
  var CREDENTIALS_HIDDEN = "credentials_hidden";
  var CREDENTIAL_PLACEHOLDERS = "credential_placeholders";
  var DEFAULT_ENDPOINT_DESC = "default_endpoint_desc";
  var DEFAULT_ENDPOINT_METHOD = "default_endpoint_method";
  var DEFAULT_ENDPOINT_URL_FORMAT = "default_endpoint_url_format";
  var DEFAULT_HOST_FORMAT = "default_host_format";
  var DEFAULT_LEVEL_COLOR = "default_level_color";
  var DESCRIPTION_KEY = "description_key";
  var DETAIL_COLOR = "detail_color";
  var DIAGNOSTICS_ALIGNMENT = "diagnostics_alignment";
  var DIAGNOSTICS_ALIGNMENT_VALUE = "diagnostics_alignment_value";
  var DIAGNOSTICS_COLOR = "diagnostics_color";
  var DIAGNOSTICS_LABEL = "diagnostics_label";
  var DIAGNOSTICS_STYLE = "diagnostics_style";
  var DIAGNOSTICS_STYLE_FORMAT = "diagnostics_style_format";
  var DISCONNECTED_DETAIL = "disconnected_detail";
  var DISCONNECTED_TITLE = "disconnected_title";
  var DISCONNECT_ENABLED = "disconnect_enabled";
  var DISCONNECT_FAILED_FORMAT = "disconnect_failed_format";
  var DISCONNECT_FAILED_TITLE = "disconnect_failed_title";
  var DISCONNECT_LABEL = "disconnect_label";
  var DISPLAY_LIMIT = "display_limit";
  var ECHO_MODE = "echo_mode";
  var EMPTY_TEXT = "empty_text";
  var ENTRIES_FIELD = "entries";
  var ENTRIES_LOGGED = "entries_logged";
  var ENTRY_COUNT = "entry_count";
  var ENTRY_HTML_FORMAT = "entry_html_format";
  var ENTRY_LIMIT = "entry_limit";
  var ENTRY_MARKS = "entry_marks";
  var ENTRY_MARK_ORDER = "entry_mark_order";
  var ENTRY_SLOTS = "entry_slots";
  var ENTRY_SLOT_ORDER = "entry_slot_order";
  var ERROR_LINE_FORMAT = "error_line_format";
  var EXCHANGE_ID = "exchange_id";
  var EXCHANGE_IDS = "exchange_ids";
  var EXCHANGE_LABEL = "exchange_label";
  var EXCHANGE_OPTIONS = "exchange_options";
  var FAILURE_HTTP = "failure_http";
  var FAILURE_OTHER = "failure_other";
  var FAILURE_URL = "failure_url";
  var GREEN_INDICATORS = "green_indicators";
  var GROUP_MARGINS = "group_margins";
  var HEADLINE = "headline";
  var HEADLINE_COLOR = "headline_color";
  var HEADLINE_FORMAT = "headline_format";
  var HEADLINE_STYLE = "headline_style";
  var HEADLINE_STYLE_FORMAT = "headline_style_format";
  var HISTORY_CALLBACK_LOG = "history_callback_log";
  var HTTP_ERROR_BODY_LIMIT = "http_error_body_limit";
  var HTTP_ERROR_DETAIL_FORMAT = "http_error_detail_format";
  var HTTP_ERROR_TITLE_FORMAT = "http_error_title_format";
  var HTTP_OK_DETAIL_FORMAT = "http_ok_detail_format";
  var HTTP_OK_TITLE_FORMAT = "http_ok_title_format";
  var HTTP_PROBES_FORMAT = "http_probes_format";
  var HTTP_PROBES_TITLE = "http_probes_title";
  var HTTP_UNREAD_TITLE_FORMAT = "http_unread_title_format";
  var INDICATOR_KEY = "indicator_key";
  var INDICATOR_SEEN_LIMIT = "indicator_seen_limit";
  var JSON_BODY_LIMIT = "json_body_limit";
  var JSON_INDENT = "json_indent";
  var JSON_KEYS_FORMAT = "json_keys_format";
  var JSON_KEYS_LIMIT = "json_keys_limit";
  var LAYOUT_MARGINS = "layout_margins";
  var LAYOUT_SPACING = "layout_spacing";
  var LEVEL_COLORS = "level_colors";
  var LEVEL_COLOR_ORDER = "level_color_order";
  var LEVEL_ERROR = "level_error";
  var LEVEL_INFO = "level_info";
  var LEVEL_SUCCESS = "level_success";
  var LEVEL_WARNING = "level_warning";
  var LIST_HEAD_FORMAT = "list_head_format";
  var LIST_SAMPLE_LIMIT = "list_sample_limit";
  var LIST_TAIL_FORMAT = "list_tail_format";
  var LOGGER_NAME = "logger_name";
  var MANUAL_MARGINS = "manual_margins";
  var MANUAL_SPACING = "manual_spacing";
  var MANUAL_VISIBLE = "manual_visible";
  var MAPPABLE_INDICATORS = "mappable_indicators";
  var MARKETS_SAMPLE_LIMIT = "markets_sample_limit";
  var METHOD_FIELD = "method";
  var NOTHING_OPEN_DETAIL = "nothing_open_detail";
  var NOTHING_OPEN_TITLE = "nothing_open_title";
  var NOT_CONNECTED_DETAIL = "not_connected_detail";
  var NOT_CONNECTED_TITLE = "not_connected_title";
  var NO_BODY = "no_body";
  var NO_CALLER_MESSAGE = "no_caller_message";
  var NO_CLOSE = "no_close";
  var NO_CREDENTIALS_FORMAT = "no_credentials_format";
  var NO_CREDENTIALS_TITLE = "no_credentials_title";
  var NO_ELAPSED = "no_elapsed";
  var NO_HOLDING = "no_holding";
  var NO_MANUAL_DETAIL = "no_manual_detail";
  var NO_MANUAL_TITLE = "no_manual_title";
  var NO_MARKETS = "no_markets";
  var NO_SETTINGS_DETAIL = "no_settings_detail";
  var NO_SETTINGS_TITLE = "no_settings_title";
  var NO_STATUS_PAGE_FORMAT = "no_status_page_format";
  var NO_STATUS_PAGE_TITLE = "no_status_page_title";
  var NO_TIMING = "no_timing";
  var OHLCV_LIMIT = "ohlcv_limit";
  var OHLCV_TIMEFRAME = "ohlcv_timeframe";
  var OPERATIONS_SPACING = "operations_spacing";
  var OPERATIONS_TITLE = "operations_title";
  var ORDERBOOK_LIMIT = "orderbook_limit";
  var PLAIN_STATUS_LIMIT = "plain_status_limit";
  var PLAIN_STATUS_TITLE = "plain_status_title";
  var PROBE_ENDPOINTS = "probe_endpoints";
  var PROBE_ENDPOINT_TABLE = "probe_endpoint_table";
  var PROBE_ENDPOINT_TABLE_ORDER = "probe_endpoint_table_order";
  var PROBE_ERROR_DETAIL_FORMAT = "probe_error_detail_format";
  var PROBE_ERROR_TITLE_FORMAT = "probe_error_title_format";
  var PROBE_HEADERS = "probe_headers";
  var PROBE_HOST = "probe_host";
  var PROBE_HOSTS = "probe_hosts";
  var PROBE_HOST_ORDER = "probe_host_order";
  var PROBE_PORT = "probe_port";
  var PROBE_TIMEOUT_S = "probe_timeout_s";
  var PRODUCTS_COUNT_FORMAT = "products_count_format";
  var PRODUCTS_KEY = "products_key";
  var RAW_PROBE_LABEL = "raw_probe_label";
  var RAW_PROBE_TOOLTIP = "raw_probe_tooltip";
  var RESPONSE_TITLE = "response_title";
  var RESULT_INFO_TEXT = "result_info_text";
  var RESULT_INFO_WORD_WRAP = "result_info_word_wrap";
  var RESULT_PLACEHOLDER = "result_placeholder";
  var RESULT_READ_ONLY = "result_read_only";
  var RUNNING_DETAIL_FORMAT = "running_detail_format";
  var RUNNING_TITLE_FORMAT = "running_title_format";
  var SKIN = "skin";
  var SPLITTER_CHILDREN_COLLAPSIBLE = "splitter_children_collapsible";
  var SPLITTER_HANDLE_WIDTH = "splitter_handle_width";
  var SPLITTER_ORIENTATION = "splitter_orientation";
  var SPLITTER_SIZES = "splitter_sizes";
  var SPOT_TYPE = "spot_type";
  var SSL_CERT_FAILED_FORMAT = "ssl_cert_failed_format";
  var SSL_CERT_FAILED_TITLE = "ssl_cert_failed_title";
  var SSL_DIAGNOSTIC_FORMAT = "ssl_diagnostic_format";
  var SSL_DIAGNOSTIC_TITLE = "ssl_diagnostic_title";
  var SSL_FAILED_TITLE = "ssl_failed_title";
  var SSL_OK_DETAIL_FORMAT = "ssl_ok_detail_format";
  var SSL_OK_FORMAT = "ssl_ok_format";
  var STATUS_CHECK_FAILED_TITLE = "status_check_failed_title";
  var STATUS_COLOR = "status_color";
  var STATUS_CONNECTED_COLOR = "status_connected_color";
  var STATUS_CONNECTED_FORMAT = "status_connected_format";
  var STATUS_CONNECTING_COLOR = "status_connecting_color";
  var STATUS_CONNECTING_FORMAT = "status_connecting_format";
  var STATUS_DETAIL_FORMAT = "status_detail_format";
  var STATUS_DISCONNECTED_COLOR = "status_disconnected_color";
  var STATUS_DISCONNECTED_TEXT = "status_disconnected_text";
  var STATUS_FAILED_COLOR = "status_failed_color";
  var STATUS_FAILED_TEXT = "status_failed_text";
  var STATUS_HEADERS = "status_headers";
  var STATUS_IDLE_COLOR = "status_idle_color";
  var STATUS_IDLE_TEXT = "status_idle_text";
  var STATUS_KEY = "status_key";
  var STATUS_PAGE_LABEL = "status_page_label";
  var STATUS_PAGE_ORDER = "status_page_order";
  var STATUS_PAGE_TOOLTIP = "status_page_tooltip";
  var STATUS_PAGE_URL = "status_page_url";
  var STATUS_PAGE_URLS = "status_page_urls";
  var STATUS_RAW_LIMIT = "status_raw_limit";
  var STATUS_STYLE = "status_style";
  var STATUS_STYLE_FORMAT = "status_style_format";
  var STATUS_TEXT = "status_text";
  var STATUS_TITLE_FORMAT = "status_title_format";
  var STYLE_SHEET = "style_sheet";
  var SYMBOL = "symbol";
  var SYMBOL_DEFAULT = "symbol_default";
  var SYMBOL_TOOLTIP = "symbol_tooltip";
  var TCP_FAILED_FORMAT = "tcp_failed_format";
  var TCP_FAILED_TITLE = "tcp_failed_title";
  var TCP_OK_DETAIL_FORMAT = "tcp_ok_detail_format";
  var TCP_OK_FORMAT = "tcp_ok_format";
  var TEST_BALANCES = "test_balances";
  var TEST_BUTTONS = "test_buttons";
  var TEST_FAILED_FORMAT = "test_failed_format";
  var TEST_MARKETS = "test_markets";
  var TEST_NAMES = "test_names";
  var TEST_OHLCV = "test_ohlcv";
  var TEST_OK_FORMAT = "test_ok_format";
  var TEST_OPEN_ORDERS = "test_open_orders";
  var TEST_ORDERBOOK = "test_orderbook";
  var TEST_TICKER = "test_ticker";
  var TEST_TRADES = "test_trades";
  var TEST_UNKNOWN_DETAIL = "test_unknown_detail";
  var TEST_UNKNOWN_FORMAT = "test_unknown_format";
  var TIMERS = "timers";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMESTAMP_COLOR = "timestamp_color";
  var TIMESTAMP_FORMAT = "timestamp_format";
  var TIMING_FORMAT = "timing_format";
  var TRADES_LIMIT = "trades_limit";
  var TRUNCATED_SUFFIX = "truncated_suffix";
  var UNKNOWN_HEADER = "unknown_header";
  var UNKNOWN_INDICATOR = "unknown_indicator";
  var UNREACHABLE_DETAIL_FORMAT = "unreachable_detail_format";
  var UNREACHABLE_TITLE_FORMAT = "unreachable_title_format";
  var UNREADABLE_ANSWER_DETAIL_FORMAT = "unreadable_answer_detail_format";
  var UNREADABLE_ANSWER_TITLE_FORMAT = "unreadable_answer_title_format";
  var UNREADABLE_BODY_FORMAT = "unreadable_body_format";
  var UNREADABLE_MARK = "unreadable_mark";
  var UNREAD_STATUS_NOTE = "unread_status_note";
  var USE_STORED = "use_stored";
  var USE_STORED_DEFAULT = "use_stored_default";
  var USE_STORED_LABEL = "use_stored_label";
  var USE_STORED_TOOLTIP = "use_stored_tooltip";

  // Every top-level name the api_tester_tab.state payload carries.
  var DECLARED_FIELDS = [
    ACTIONS,
    ACTIONS_ORDER,
    BALANCE_SECTIONS,
    BODY_DISPLAY_LIMIT,
    BODY_TRUNCATED_SUFFIX,
    BUS_TOPICS,
    CALL_COUNT,
    CALL_LIMIT,
    CALL_NAMES,
    CALLS,
    CERT_UNKNOWN,
    CERTIFI_FAILED_TITLE,
    CERTIFI_MISSING_DETAIL,
    CERTIFI_MISSING_TITLE,
    CERTIFI_OK_DETAIL_FORMAT,
    CERTIFI_OK_FORMAT,
    CHECKING_STATUS_FORMAT,
    CHECKING_STATUS_TITLE,
    CLOSE_INDEX,
    CONNECT_ENABLED,
    CONNECT_FAILED_TITLE,
    CONNECT_LABEL,
    CONNECT_TOOLTIP,
    CONNECTED,
    CONNECTED_DETAIL_FORMAT,
    CONNECTED_TITLE_FORMAT,
    CONNECTION_SPACING,
    CONNECTION_TITLE,
    CONNECTOR_HELD,
    CONTENT_LENGTH_HEADER,
    CONTENT_TYPE_HEADER,
    CREDENTIAL_PLACEHOLDERS,
    CREDENTIALS_FILLED,
    CREDENTIALS_HIDDEN,
    DEFAULT_ENDPOINT_DESC,
    DEFAULT_ENDPOINT_METHOD,
    DEFAULT_ENDPOINT_URL_FORMAT,
    DEFAULT_HOST_FORMAT,
    DEFAULT_LEVEL_COLOR,
    DESCRIPTION_KEY,
    DETAIL_COLOR,
    DIAGNOSTICS_ALIGNMENT,
    DIAGNOSTICS_ALIGNMENT_VALUE,
    DIAGNOSTICS_COLOR,
    DIAGNOSTICS_LABEL,
    DIAGNOSTICS_STYLE,
    DIAGNOSTICS_STYLE_FORMAT,
    DISCONNECT_ENABLED,
    DISCONNECT_FAILED_FORMAT,
    DISCONNECT_FAILED_TITLE,
    DISCONNECT_LABEL,
    DISCONNECTED_DETAIL,
    DISCONNECTED_TITLE,
    DISPLAY_LIMIT,
    ECHO_MODE,
    EMPTY_TEXT,
    ENTRIES_FIELD,
    ENTRIES_LOGGED,
    ENTRY_COUNT,
    ENTRY_HTML_FORMAT,
    ENTRY_LIMIT,
    ENTRY_MARK_ORDER,
    ENTRY_MARKS,
    ENTRY_SLOT_ORDER,
    ENTRY_SLOTS,
    ERROR_LINE_FORMAT,
    EXCHANGE_ID,
    EXCHANGE_IDS,
    EXCHANGE_LABEL,
    EXCHANGE_OPTIONS,
    FAILURE_HTTP,
    FAILURE_OTHER,
    FAILURE_URL,
    GREEN_INDICATORS,
    GROUP_MARGINS,
    HEADLINE,
    HEADLINE_COLOR,
    HEADLINE_FORMAT,
    HEADLINE_STYLE,
    HEADLINE_STYLE_FORMAT,
    HISTORY_CALLBACK_LOG,
    HTTP_ERROR_BODY_LIMIT,
    HTTP_ERROR_DETAIL_FORMAT,
    HTTP_ERROR_TITLE_FORMAT,
    HTTP_OK_DETAIL_FORMAT,
    HTTP_OK_TITLE_FORMAT,
    HTTP_PROBES_FORMAT,
    HTTP_PROBES_TITLE,
    HTTP_UNREAD_TITLE_FORMAT,
    INDICATOR_KEY,
    INDICATOR_SEEN_LIMIT,
    JSON_BODY_LIMIT,
    JSON_INDENT,
    JSON_KEYS_FORMAT,
    JSON_KEYS_LIMIT,
    LAYOUT_MARGINS,
    LAYOUT_SPACING,
    LEVEL_COLOR_ORDER,
    LEVEL_COLORS,
    LEVEL_ERROR,
    LEVEL_INFO,
    LEVEL_SUCCESS,
    LEVEL_WARNING,
    LIST_HEAD_FORMAT,
    LIST_SAMPLE_LIMIT,
    LIST_TAIL_FORMAT,
    LOGGER_NAME,
    MANUAL_MARGINS,
    MANUAL_SPACING,
    MANUAL_VISIBLE,
    MAPPABLE_INDICATORS,
    MARKETS_SAMPLE_LIMIT,
    METHOD_FIELD,
    NO_BODY,
    NO_CALLER_MESSAGE,
    NO_CLOSE,
    NO_CREDENTIALS_FORMAT,
    NO_CREDENTIALS_TITLE,
    NO_ELAPSED,
    NO_HOLDING,
    NO_MANUAL_DETAIL,
    NO_MANUAL_TITLE,
    NO_MARKETS,
    NO_SETTINGS_DETAIL,
    NO_SETTINGS_TITLE,
    NO_STATUS_PAGE_FORMAT,
    NO_STATUS_PAGE_TITLE,
    NO_TIMING,
    NOT_CONNECTED_DETAIL,
    NOT_CONNECTED_TITLE,
    NOTHING_OPEN_DETAIL,
    NOTHING_OPEN_TITLE,
    OHLCV_LIMIT,
    OHLCV_TIMEFRAME,
    OPERATIONS_SPACING,
    OPERATIONS_TITLE,
    ORDERBOOK_LIMIT,
    PLAIN_STATUS_LIMIT,
    PLAIN_STATUS_TITLE,
    PROBE_ENDPOINT_TABLE,
    PROBE_ENDPOINT_TABLE_ORDER,
    PROBE_ENDPOINTS,
    PROBE_ERROR_DETAIL_FORMAT,
    PROBE_ERROR_TITLE_FORMAT,
    PROBE_HEADERS,
    PROBE_HOST,
    PROBE_HOST_ORDER,
    PROBE_HOSTS,
    PROBE_PORT,
    PROBE_TIMEOUT_S,
    PRODUCTS_COUNT_FORMAT,
    PRODUCTS_KEY,
    RAW_PROBE_LABEL,
    RAW_PROBE_TOOLTIP,
    RESPONSE_TITLE,
    RESULT_INFO_TEXT,
    RESULT_INFO_WORD_WRAP,
    RESULT_PLACEHOLDER,
    RESULT_READ_ONLY,
    RUNNING_DETAIL_FORMAT,
    RUNNING_TITLE_FORMAT,
    SKIN,
    SPLITTER_CHILDREN_COLLAPSIBLE,
    SPLITTER_HANDLE_WIDTH,
    SPLITTER_ORIENTATION,
    SPLITTER_SIZES,
    SPOT_TYPE,
    SSL_CERT_FAILED_FORMAT,
    SSL_CERT_FAILED_TITLE,
    SSL_DIAGNOSTIC_FORMAT,
    SSL_DIAGNOSTIC_TITLE,
    SSL_FAILED_TITLE,
    SSL_OK_DETAIL_FORMAT,
    SSL_OK_FORMAT,
    STATUS_CHECK_FAILED_TITLE,
    STATUS_COLOR,
    STATUS_CONNECTED_COLOR,
    STATUS_CONNECTED_FORMAT,
    STATUS_CONNECTING_COLOR,
    STATUS_CONNECTING_FORMAT,
    STATUS_DETAIL_FORMAT,
    STATUS_DISCONNECTED_COLOR,
    STATUS_DISCONNECTED_TEXT,
    STATUS_FAILED_COLOR,
    STATUS_FAILED_TEXT,
    STATUS_HEADERS,
    STATUS_IDLE_COLOR,
    STATUS_IDLE_TEXT,
    STATUS_KEY,
    STATUS_PAGE_LABEL,
    STATUS_PAGE_ORDER,
    STATUS_PAGE_TOOLTIP,
    STATUS_PAGE_URL,
    STATUS_PAGE_URLS,
    STATUS_RAW_LIMIT,
    STATUS_STYLE,
    STATUS_STYLE_FORMAT,
    STATUS_TEXT,
    STATUS_TITLE_FORMAT,
    STYLE_SHEET,
    SYMBOL,
    SYMBOL_DEFAULT,
    SYMBOL_TOOLTIP,
    TCP_FAILED_FORMAT,
    TCP_FAILED_TITLE,
    TCP_OK_DETAIL_FORMAT,
    TCP_OK_FORMAT,
    TEST_BALANCES,
    TEST_BUTTONS,
    TEST_FAILED_FORMAT,
    TEST_MARKETS,
    TEST_NAMES,
    TEST_OHLCV,
    TEST_OK_FORMAT,
    TEST_OPEN_ORDERS,
    TEST_ORDERBOOK,
    TEST_TICKER,
    TEST_TRADES,
    TEST_UNKNOWN_DETAIL,
    TEST_UNKNOWN_FORMAT,
    TIMER_DELAYS_MS,
    TIMERS,
    TIMESTAMP_COLOR,
    TIMESTAMP_FORMAT,
    TIMING_FORMAT,
    TRADES_LIMIT,
    TRUNCATED_SUFFIX,
    UNKNOWN_HEADER,
    UNKNOWN_INDICATOR,
    UNREACHABLE_DETAIL_FORMAT,
    UNREACHABLE_TITLE_FORMAT,
    UNREAD_STATUS_NOTE,
    UNREADABLE_ANSWER_DETAIL_FORMAT,
    UNREADABLE_ANSWER_TITLE_FORMAT,
    UNREADABLE_BODY_FORMAT,
    UNREADABLE_MARK,
    USE_STORED,
    USE_STORED_DEFAULT,
    USE_STORED_LABEL,
    USE_STORED_TOOLTIP
  ];

  var DECLARED_BAGS = [
    ACTIONS,
    ENTRY_MARKS,
    ENTRY_SLOTS,
    LEVEL_COLORS,
    PROBE_ENDPOINT_TABLE,
    PROBE_HOSTS,
    SKIN,
    STATUS_PAGE_URLS,
    TIMERS
  ];

  var DECLARED_LISTS = [
    ACTIONS_ORDER,
    BALANCE_SECTIONS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CREDENTIAL_PLACEHOLDERS,
    CREDENTIALS_FILLED,
    ENTRIES_FIELD,
    ENTRY_MARK_ORDER,
    ENTRY_SLOT_ORDER,
    EXCHANGE_IDS,
    EXCHANGE_OPTIONS,
    GREEN_INDICATORS,
    GROUP_MARGINS,
    LAYOUT_MARGINS,
    LEVEL_COLOR_ORDER,
    MANUAL_MARGINS,
    MAPPABLE_INDICATORS,
    PROBE_ENDPOINT_TABLE_ORDER,
    PROBE_ENDPOINTS,
    PROBE_HEADERS,
    PROBE_HOST_ORDER,
    SPLITTER_SIZES,
    STATUS_HEADERS,
    STATUS_PAGE_ORDER,
    TEST_BUTTONS,
    TEST_NAMES,
    TIMER_DELAYS_MS
  ];

  var METHOD = "api_tester_tab.state";

  var LABEL = "label";
  var VALUE = "value";
  var STAMP = "stamp";
  var TITLE = "title";
  var TIMING = "timing";
  var LEVEL = "level";
  var COLOR = "color";
  var DETAIL = "detail";
  var HTML = "html";

  // The seven keys one response-log entry carries.
  var ENTRY_KEYS = [STAMP, TITLE, TIMING, LEVEL, COLOR, DETAIL, HTML];

  var MARK_SPAN_OPEN = "span_open";
  var MARK_ATTR_CLOSE = "attr_close";
  var MARK_SPAN_CLOSE = "span_close";
  var MARK_STRONG_OPEN = "strong_open";
  var MARK_STRONG_CLOSE = "strong_close";
  var MARK_LINE_BREAK = "line_break";
  var MARK_PRE_OPEN = "pre_open";
  var MARK_PRE_ATTRS = "pre_attrs";
  var MARK_PRE_CLOSE = "pre_close";
  var MARK_STAMP_OPEN = "stamp_open";
  var MARK_STAMP_CLOSE = "stamp_close";
  var MARK_JOIN = "join";
  var MARK_STRONG_WEIGHT = "strong_weight";
  var MARK_DETAIL_WRAP = "detail_wrap";

  var SLOT_STAMP_COLOR = "stamp_color";
  var SLOT_STAMP = "stamp";
  var SLOT_COLOR = "color";
  var SLOT_TITLE = "title";
  var SLOT_TIMING = "timing";
  var SLOT_DETAIL_COLOR = "detail_color";
  var SLOT_DETAIL = "detail";

  // Each bag beside the list that carries its key order.
  var ORDERED_BAGS = [
    [ACTIONS, ACTIONS_ORDER],
    [ENTRY_MARKS, ENTRY_MARK_ORDER],
    [ENTRY_SLOTS, ENTRY_SLOT_ORDER],
    [LEVEL_COLORS, LEVEL_COLOR_ORDER],
    [PROBE_ENDPOINT_TABLE, PROBE_ENDPOINT_TABLE_ORDER],
    [PROBE_HOSTS, PROBE_HOST_ORDER],
    [STATUS_PAGE_URLS, STATUS_PAGE_ORDER]
  ];

  // Each paired list beside the list its own length must match.
  var PAIRED_LISTS = [
    [EXCHANGE_OPTIONS, EXCHANGE_IDS],
    [CREDENTIAL_PLACEHOLDERS, CREDENTIALS_FILLED],
    [TEST_BUTTONS, TEST_NAMES]
  ];

  var EXCHANGE_ROW_WIDTH = 2;
  var TEST_ROW_WIDTH = 3;
  var ENDPOINT_ROW_WIDTH = 3;
  var HEADER_ROW_WIDTH = 2;

  var NAME_AT = 0;
  var SECOND_AT = 1;
  var THIRD_AT = 2;

  // Each list of rows beside the width every row must have.
  var ROW_WIDTHS = [
    [EXCHANGE_OPTIONS, EXCHANGE_ROW_WIDTH],
    [TEST_BUTTONS, TEST_ROW_WIDTH],
    [PROBE_ENDPOINTS, ENDPOINT_ROW_WIDTH],
    [PROBE_HEADERS, HEADER_ROW_WIDTH],
    [STATUS_HEADERS, HEADER_ROW_WIDTH]
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_BAG_FAULT = "not-a-bag";
  var NOT_A_LIST_FAULT = "not-a-list";
  var SHORT_LIST_FAULT = "short-list";
  var SWAPPED_ALPHA_FAULT = "swapped-alpha";
  var REORDERED_KEY_FAULT = "reordered-key";
  var DISAGREES_FAULT = "disagrees";
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var UNKNOWN_STEP_FAULT = "unknown-step";
  var MARKUP_FAULT = "markup";
  var NOT_CSS_FAULT = "not-css";
  var OVER_LIMIT_FAULT = "over-limit";
  var OVERCLAIM_FAULT = "overclaim";

  var ROW_AT = "row:";
  var PATH_SPLIT = ".";
  var EMPTY = "";

  var NO_BRIDGE = "the preload bridge is not present";

  // Qt paints qlineargradient by name and no browser stylesheet runs it.
  var QT_ONLY = "qlineargradient";

  // MARKUP_OPEN starts a tag a Qt rich-text label reads as formatting.
  var MARKUP_OPEN = "<";

  var TAB_CLASS = "acervator-api-tester";

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var STRONG_TAG = "strong";
  var BUTTON_TAG = "button";
  var INPUT_TAG = "input";
  var SELECT_TAG = "select";
  var OPTION_TAG = "option";

  var TEXT_KIND = "text";
  var PASSWORD_KIND = "password";
  var CHECKBOX_KIND = "checkbox";

  var TAB_PART = "api-tester-tab";
  var CONNECTION_GROUP_PART = "connection-group";
  var CONNECTION_TITLE_PART = "connection-title";
  var EXCHANGE_LABEL_PART = "exchange-label";
  var EXCHANGE_SELECT_PART = "exchange-select";
  var EXCHANGE_OPTION_PART = "exchange-option";
  var USE_STORED_PART = "use-stored";
  var USE_STORED_LABEL_PART = "use-stored-label";
  var MANUAL_ROW_PART = "manual-row";
  var CREDENTIAL_BOX_PART = "credential-box";
  var CONNECT_BUTTON_PART = "connect-button";
  var DISCONNECT_BUTTON_PART = "disconnect-button";
  var CONNECTION_STATUS_PART = "connection-status";
  var OPERATIONS_GROUP_PART = "operations-group";
  var OPERATIONS_TITLE_PART = "operations-title";
  var SYMBOL_BOX_PART = "symbol-box";
  var TEST_BUTTON_PART = "test-button";
  var DIAGNOSTICS_LABEL_PART = "diagnostics-label";
  var RAW_PROBE_PART = "raw-probe-button";
  var STATUS_PAGE_PART = "status-page-button";
  var RESPONSE_GROUP_PART = "response-group";
  var RESPONSE_TITLE_PART = "response-title";
  var RESPONSE_HEADLINE_PART = "response-headline";
  var RESPONSE_LOG_PART = "response-log";
  var LOG_ENTRY_PART = "log-entry";
  var ENTRY_STAMP_PART = "entry-stamp";
  var ENTRY_TITLE_PART = "entry-title";
  var ENTRY_TIMING_PART = "entry-timing";
  var ENTRY_DETAIL_PART = "entry-detail";
  var PLACEHOLDER_PART = "log-placeholder";
  var STEP_PART = "tab-step";

  // PAGE_PART is the space the renderer leaves for this screen.
  var PAGE_PART = "api-tester-page";

  var PART_ATTR = "data-part";
  var KEY_ATTR = "data-key";
  var NAME_ATTR = "data-name";
  var INDEX_ATTR = "data-index";
  var LEVEL_ATTR = "data-level";
  var COUNT_ATTR = "data-count";
  var LOGGED_ATTR = "data-logged";
  var FILLED_ATTR = "data-filled";
  var SHOWN_ATTR = "data-shown";
  var ENABLED_ATTR = "data-enabled";
  var ECHO_ATTR = "data-echo";
  var HELD_ATTR = "data-connector-held";
  var WRAP_ATTR = "data-word-wrap";
  var READ_ONLY_ATTR = "data-read-only";
  var ARIA_LABEL = "aria-label";

  var SELECT_OPEN = "[";
  var SELECT_IS = "=\"";
  var SELECT_CLOSE = "\"]";

  // HASH_ESCAPE decodes to the mark every colour opens with.
  var HASH_ESCAPE = "%23";
  var HEX_MARK = decodeURIComponent(HASH_ESCAPE);
  // SWAPPED_LENGTH is the width of a colour written with eight hex digits.
  var SWAPPED_LENGTH = HEX_MARK.length + "aabbccdd".length;

  var DIGITS = "0123456789";

  var PX = "px";
  var FLEX = "flex";
  var ROW_DIRECTION = "row";
  var COLUMN_DIRECTION = "column";
  var FULL = "100%";
  var NOWRAP = "nowrap";
  var NORMAL = "normal";
  var AUTO = "auto";
  var STRING_KIND = "string";
  var NUMBER_KIND = "number";
  var BOOLEAN_KIND = "boolean";
  var FUNCTION_KIND = "function";

  var ZERO = Number(EMPTY);
  var STEP = Number(true);

  var held = null;
  var tabFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  function copyOf(bag) {
    var found = {};
    Object.keys(bag).forEach(function (key) {
      found[key] = bag[key];
    });
    return found;
  }

  function kindOf(value) {
    return value === null ? NULL_FAULT : typeof value;
  }

  function objectField(model, name) {
    return isPlainObject(model) && isPlainObject(model[name]) ? model[name] : {};
  }

  function listField(model, name) {
    return isPlainObject(model) && Array.isArray(model[name]) ? model[name] : [];
  }

  function fault(where, name, kind, detail) {
    return { where: where, field: name, fault: kind, detail: detail };
  }

  function note(where, name, kind, detail) {
    tabFaults.push(fault(where, name, kind, detail));
  }

  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  function label(value) {
    return typeof value === STRING_KIND && value.length ? value : undefined;
  }

  function length(value) {
    return value === null || value === undefined ? undefined : String(value) + PX;
  }

  function carries(value, mark) {
    return String(value).indexOf(mark) >= ZERO;
  }

  function rowOf(value) {
    return Array.isArray(value) ? value : [];
  }

  // True for a colour written with eight hex digits, which Qt reads alpha-first.
  function isSwappedAlpha(value) {
    return (
      typeof value === STRING_KIND &&
      value.length === SWAPPED_LENGTH &&
      value.charAt(ZERO) === HEX_MARK
    );
  }

  // True for a key a browser lists before every worded key of the same bag.
  function isReorderedKey(key) {
    var printed = String(key);
    if (!printed.length) {
      return false;
    }
    var digitsOnly = true;
    printed.split(EMPTY).forEach(function (letter) {
      if (DIGITS.indexOf(letter) < ZERO) {
        digitsOnly = false;
      }
    });
    return digitsOnly;
  }

  function colour(value) {
    var api = global.acervatorCells;
    if (!api || typeof api.colour !== FUNCTION_KIND) {
      return text(value);
    }
    return api.colour(value);
  }

  // header_strip.js owns the rule that turns a Qt style sheet into CSS.
  function styleOf(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== FUNCTION_KIND) {
      return {};
    }
    return api.styleOf(sheet);
  }

  function declarations(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.declarations !== FUNCTION_KIND) {
      return [];
    }
    return api.declarations(sheet);
  }

  // A selector carrying a colon names a state Qt paints on hover.
  function stateRules(sheet) {
    var api = global.acervatorHeader;
    if (!api || typeof api.stateRules !== FUNCTION_KIND) {
      return [];
    }
    return api.stateRules(sheet);
  }

  // Every declaration of one sheet, its state blocks read as well as its base.
  function wholeSheet(sheet) {
    var found = declarations(sheet).slice();
    stateRules(sheet).forEach(function (rule) {
      declarations(rule.body).forEach(function (one) {
        found.push(one);
      });
    });
    return found;
  }

  function model() {
    return held === null ? null : held.model;
  }

  function payload() {
    return held === null ? {} : copyOf(held.model);
  }

  function declaredNames() {
    return DECLARED_FIELDS.slice();
  }

  function field(name) {
    if (held === null || !owns(held.model, name)) {
      return undefined;
    }
    return held.model[name];
  }

  function bag(name) {
    return held === null ? {} : copyOf(objectField(held.model, name));
  }

  function list(name) {
    return held === null ? [] : listField(held.model, name).slice();
  }

  function bagKeys(name) {
    return Object.keys(bag(name));
  }

  function marks() {
    return objectField(model(), ENTRY_MARKS);
  }

  function slots() {
    return objectField(model(), ENTRY_SLOTS);
  }

  // The response-log line rebuilt from the marks and slots published.
  function rebuiltLineFormat() {
    var mark = marks();
    var slot = slots();
    return (
      mark[MARK_SPAN_OPEN] +
      slot[SLOT_STAMP_COLOR] +
      mark[MARK_ATTR_CLOSE] +
      mark[MARK_STAMP_OPEN] +
      slot[SLOT_STAMP] +
      mark[MARK_STAMP_CLOSE] +
      mark[MARK_SPAN_CLOSE] +
      mark[MARK_JOIN] +
      mark[MARK_SPAN_OPEN] +
      slot[SLOT_COLOR] +
      mark[MARK_ATTR_CLOSE] +
      mark[MARK_STRONG_OPEN] +
      slot[SLOT_TITLE] +
      mark[MARK_STRONG_CLOSE] +
      slot[SLOT_TIMING] +
      mark[MARK_SPAN_CLOSE] +
      mark[MARK_LINE_BREAK] +
      mark[MARK_PRE_OPEN] +
      slot[SLOT_DETAIL_COLOR] +
      mark[MARK_PRE_ATTRS] +
      slot[SLOT_DETAIL] +
      mark[MARK_PRE_CLOSE] +
      mark[MARK_LINE_BREAK]
    );
  }

  function entries() {
    return list(ENTRIES_FIELD);
  }

  function entryAt(at) {
    var found = entries()[at];
    return isPlainObject(found) ? copyOf(found) : undefined;
  }

  // One entry's marked-up line, rebuilt from the pieces that entry carries.
  function rebuiltEntryLine(at) {
    var one = entryAt(at);
    if (one === undefined) {
      return undefined;
    }
    var mark = marks();
    return (
      mark[MARK_SPAN_OPEN] +
      String(field(TIMESTAMP_COLOR)) +
      mark[MARK_ATTR_CLOSE] +
      mark[MARK_STAMP_OPEN] +
      String(one[STAMP]) +
      mark[MARK_STAMP_CLOSE] +
      mark[MARK_SPAN_CLOSE] +
      mark[MARK_JOIN] +
      mark[MARK_SPAN_OPEN] +
      String(one[COLOR]) +
      mark[MARK_ATTR_CLOSE] +
      mark[MARK_STRONG_OPEN] +
      String(one[TITLE]) +
      mark[MARK_STRONG_CLOSE] +
      String(one[TIMING]) +
      mark[MARK_SPAN_CLOSE] +
      mark[MARK_LINE_BREAK] +
      mark[MARK_PRE_OPEN] +
      String(field(DETAIL_COLOR)) +
      mark[MARK_PRE_ATTRS] +
      String(one[DETAIL]) +
      mark[MARK_PRE_CLOSE] +
      mark[MARK_LINE_BREAK]
    );
  }

  function levelNames() {
    return [
      field(LEVEL_INFO),
      field(LEVEL_SUCCESS),
      field(LEVEL_WARNING),
      field(LEVEL_ERROR)
    ];
  }

  function levelColour(name) {
    var table = bag(LEVEL_COLORS);
    return owns(table, name) ? table[name] : field(DEFAULT_LEVEL_COLOR);
  }

  function exchangeNames() {
    return list(EXCHANGE_OPTIONS).map(function (row) {
      return rowOf(row)[SECOND_AT];
    });
  }

  function exchangeOptionNamed(name) {
    var found;
    list(EXCHANGE_OPTIONS).forEach(function (row) {
      if (rowOf(row)[SECOND_AT] === name) {
        found = rowOf(row).slice();
      }
    });
    return found;
  }

  function testNames() {
    return list(TEST_BUTTONS).map(function (row) {
      return rowOf(row)[SECOND_AT];
    });
  }

  function testButtonNamed(name) {
    var found;
    list(TEST_BUTTONS).forEach(function (row) {
      if (rowOf(row)[SECOND_AT] === name) {
        found = rowOf(row).slice();
      }
    });
    return found;
  }

  function credentialNames() {
    return list(CREDENTIAL_PLACEHOLDERS).slice();
  }

  function credentialFilledNamed(name) {
    var found;
    credentialNames().forEach(function (one, at) {
      if (one === name) {
        found = list(CREDENTIALS_FILLED)[at];
      }
    });
    return found;
  }

  function endpointUrls() {
    return list(PROBE_ENDPOINTS).map(function (row) {
      return rowOf(row)[SECOND_AT];
    });
  }

  function endpointNamed(url) {
    var found;
    list(PROBE_ENDPOINTS).forEach(function (row) {
      if (rowOf(row)[SECOND_AT] === url) {
        found = rowOf(row).slice();
      }
    });
    return found;
  }

  function headerNames(name) {
    return list(name).map(function (row) {
      return rowOf(row)[NAME_AT];
    });
  }

  function headerNamed(name, wanted) {
    var found;
    list(name).forEach(function (row) {
      if (rowOf(row)[NAME_AT] === wanted) {
        found = rowOf(row)[SECOND_AT];
      }
    });
    return found;
  }

  function calls() {
    return list(CALLS);
  }

  function callNames() {
    return list(CALL_NAMES);
  }

  function hostNamed(name) {
    var table = bag(PROBE_HOSTS);
    return owns(table, name) ? table[name] : undefined;
  }

  function statusPageNamed(name) {
    var table = bag(STATUS_PAGE_URLS);
    return owns(table, name) ? table[name] : undefined;
  }

  function actionNamed(name) {
    var table = bag(ACTIONS);
    return owns(table, name) ? table[name] : undefined;
  }

  // Every entry drawn green whose own headline carries the unreadable mark.
  function overclaims() {
    var found = [];
    var green = field(LEVEL_SUCCESS);
    var mark = String(field(UNREADABLE_MARK));
    entries().forEach(function (one, at) {
      if (!isPlainObject(one) || one[LEVEL] !== green) {
        return;
      }
      if (carries(one[TITLE], mark)) {
        found.push({ at: at, title: one[TITLE] });
      }
    });
    return found;
  }

  function checkFields(found) {
    DECLARED_FIELDS.forEach(function (name) {
      if (!owns(found, name)) {
        note(null, name, MISSING_FAULT, null);
      }
    });
    DECLARED_BAGS.forEach(function (name) {
      if (owns(found, name) && !isPlainObject(found[name])) {
        note(null, name, NOT_A_BAG_FAULT, kindOf(found[name]));
      }
    });
    DECLARED_LISTS.forEach(function (name) {
      if (owns(found, name) && !Array.isArray(found[name])) {
        note(null, name, NOT_A_LIST_FAULT, kindOf(found[name]));
      }
    });
    if (found[METHOD_FIELD] !== METHOD) {
      note(null, METHOD_FIELD, DISAGREES_FAULT, found[METHOD_FIELD]);
    }
  }

  function checkPairs(found) {
    PAIRED_LISTS.forEach(function (pair) {
      var left = listField(found, pair[NAME_AT]);
      var right = listField(found, pair[SECOND_AT]);
      if (left.length !== right.length) {
        note(
          null,
          pair[NAME_AT],
          SHORT_LIST_FAULT,
          pair[SECOND_AT] + PATH_SPLIT + String(right.length)
        );
      }
    });
    var names = listField(found, TEST_BUTTONS).map(function (row) {
      return rowOf(row)[SECOND_AT];
    });
    listField(found, TEST_NAMES).forEach(function (one) {
      if (names.indexOf(one) < ZERO) {
        note(null, TEST_NAMES, DISAGREES_FAULT, one);
      }
    });
    var ids = listField(found, EXCHANGE_OPTIONS).map(function (row) {
      return rowOf(row)[SECOND_AT];
    });
    listField(found, EXCHANGE_IDS).forEach(function (one) {
      if (ids.indexOf(one) < ZERO) {
        note(null, EXCHANGE_IDS, DISAGREES_FAULT, one);
      }
    });
  }

  function checkRowWidths(found) {
    ROW_WIDTHS.forEach(function (pair) {
      listField(found, pair[NAME_AT]).forEach(function (row, at) {
        if (!Array.isArray(row)) {
          note(ROW_AT + String(at), pair[NAME_AT], NOT_A_LIST_FAULT, kindOf(row));
          return;
        }
        if (row.length !== pair[SECOND_AT]) {
          note(ROW_AT + String(at), pair[NAME_AT], SHORT_LIST_FAULT, row.length);
        }
      });
    });
  }

  function checkRepeats(name, taken) {
    var seen = [];
    taken.forEach(function (one, at) {
      var printed = String(one);
      if (seen.indexOf(printed) >= ZERO) {
        note(ROW_AT + String(at), name, DUPLICATE_NAME_FAULT, printed);
      }
      seen.push(printed);
    });
  }

  function checkNames(found) {
    checkRepeats(
      EXCHANGE_OPTIONS,
      listField(found, EXCHANGE_OPTIONS).map(function (row) {
        return rowOf(row)[SECOND_AT];
      })
    );
    checkRepeats(
      TEST_BUTTONS,
      listField(found, TEST_BUTTONS).map(function (row) {
        return rowOf(row)[SECOND_AT];
      })
    );
    checkRepeats(
      PROBE_ENDPOINTS,
      listField(found, PROBE_ENDPOINTS).map(function (row) {
        return rowOf(row)[SECOND_AT];
      })
    );
    checkRepeats(CREDENTIAL_PLACEHOLDERS, listField(found, CREDENTIAL_PLACEHOLDERS));
    [PROBE_HEADERS, STATUS_HEADERS].forEach(function (name) {
      checkRepeats(
        name,
        listField(found, name).map(function (row) {
          return rowOf(row)[NAME_AT];
        })
      );
    });
  }

  function checkSteps(found) {
    var known = listField(found, CALL_NAMES);
    listField(found, CALLS).forEach(function (row, at) {
      if (!Array.isArray(row)) {
        note(ROW_AT + String(at), CALLS, NOT_A_LIST_FAULT, kindOf(row));
        return;
      }
      if (known.indexOf(row[NAME_AT]) < ZERO) {
        note(ROW_AT + String(at), CALLS, UNKNOWN_STEP_FAULT, row[NAME_AT]);
      }
    });
  }

  function checkCounts(found) {
    var drawn = listField(found, ENTRIES_FIELD);
    var stepped = listField(found, CALLS);
    if (found[ENTRY_COUNT] !== drawn.length) {
      note(null, ENTRY_COUNT, DISAGREES_FAULT, found[ENTRY_COUNT]);
    }
    if (found[CALL_COUNT] !== stepped.length) {
      note(null, CALL_COUNT, DISAGREES_FAULT, found[CALL_COUNT]);
    }
    if (typeof found[ENTRY_LIMIT] === NUMBER_KIND && drawn.length > found[ENTRY_LIMIT]) {
      note(null, ENTRIES_FIELD, OVER_LIMIT_FAULT, drawn.length);
    }
    if (typeof found[CALL_LIMIT] === NUMBER_KIND && stepped.length > found[CALL_LIMIT]) {
      note(null, CALLS, OVER_LIMIT_FAULT, stepped.length);
    }
    if (
      typeof found[ENTRIES_LOGGED] === NUMBER_KIND &&
      found[ENTRIES_LOGGED] < drawn.length
    ) {
      note(null, ENTRIES_LOGGED, DISAGREES_FAULT, found[ENTRIES_LOGGED]);
    }
  }

  function checkEntries(found) {
    var known = [
      found[LEVEL_INFO],
      found[LEVEL_SUCCESS],
      found[LEVEL_WARNING],
      found[LEVEL_ERROR]
    ];
    var table = objectField(found, LEVEL_COLORS);
    listField(found, ENTRIES_FIELD).forEach(function (one, at) {
      var where = ROW_AT + String(at);
      if (!isPlainObject(one)) {
        note(where, ENTRIES_FIELD, NOT_AN_OBJECT_FAULT, kindOf(one));
        return;
      }
      ENTRY_KEYS.forEach(function (key) {
        if (!owns(one, key)) {
          note(where, key, MISSING_FAULT, null);
        }
      });
      if (known.indexOf(one[LEVEL]) < ZERO) {
        note(where, LEVEL, DISAGREES_FAULT, one[LEVEL]);
        return;
      }
      var wanted = owns(table, one[LEVEL])
        ? table[one[LEVEL]]
        : found[DEFAULT_LEVEL_COLOR];
      if (one[COLOR] !== wanted) {
        note(where, COLOR, DISAGREES_FAULT, one[COLOR]);
      }
    });
  }

  // An entry drawn green whose headline carries the unreadable mark overclaims.
  function checkOverclaims(found) {
    var green = found[LEVEL_SUCCESS];
    var mark = String(found[UNREADABLE_MARK]);
    listField(found, ENTRIES_FIELD).forEach(function (one, at) {
      if (!isPlainObject(one) || one[LEVEL] !== green) {
        return;
      }
      if (carries(one[TITLE], mark)) {
        note(ROW_AT + String(at), ENTRIES_FIELD, OVERCLAIM_FAULT, one[TITLE]);
      }
    });
  }

  function checkMarks(found) {
    var mark = objectField(found, ENTRY_MARKS);
    var slot = objectField(found, ENTRY_SLOTS);
    listField(found, ENTRY_MARK_ORDER).forEach(function (name) {
      if (!owns(mark, name)) {
        note(null, ENTRY_MARKS, MISSING_FAULT, name);
      }
    });
    listField(found, ENTRY_SLOT_ORDER).forEach(function (name) {
      if (!owns(slot, name)) {
        note(null, ENTRY_SLOTS, MISSING_FAULT, name);
      }
    });
    if (rebuiltLineFormat() !== found[ENTRY_HTML_FORMAT]) {
      note(null, ENTRY_HTML_FORMAT, DISAGREES_FAULT, rebuiltLineFormat());
    }
    listField(found, ENTRIES_FIELD).forEach(function (one, at) {
      if (isPlainObject(one) && rebuiltEntryLine(at) !== one[HTML]) {
        note(ROW_AT + String(at), HTML, DISAGREES_FAULT, one[HTML]);
      }
    });
  }

  function checkColour(where, name, value) {
    if (isSwappedAlpha(value)) {
      note(where, name, SWAPPED_ALPHA_FAULT, value);
    }
  }

  function colourFields() {
    return [
      STATUS_COLOR,
      STATUS_IDLE_COLOR,
      STATUS_CONNECTING_COLOR,
      STATUS_CONNECTED_COLOR,
      STATUS_FAILED_COLOR,
      STATUS_DISCONNECTED_COLOR,
      DIAGNOSTICS_COLOR,
      DEFAULT_LEVEL_COLOR,
      TIMESTAMP_COLOR,
      DETAIL_COLOR,
      HEADLINE_COLOR
    ];
  }

  function sheetFields() {
    return [STATUS_STYLE, DIAGNOSTICS_STYLE, HEADLINE_STYLE, STYLE_SHEET];
  }

  function checkColours(found) {
    colourFields().forEach(function (name) {
      checkColour(null, name, found[name]);
    });
    [LEVEL_COLORS, SKIN].forEach(function (name) {
      var table = objectField(found, name);
      Object.keys(table).forEach(function (key) {
        checkColour(null, name, table[key]);
      });
    });
    listField(found, ENTRIES_FIELD).forEach(function (one, at) {
      if (isPlainObject(one)) {
        checkColour(ROW_AT + String(at), COLOR, one[COLOR]);
      }
    });
    sheetFields().forEach(function (name) {
      checkColour(null, name, found[name]);
      wholeSheet(found[name]).forEach(function (written) {
        checkColour(null, name, written.value);
        if (carries(written.value, QT_ONLY)) {
          note(null, name, NOT_CSS_FAULT, written.property);
        }
      });
    });
    Object.keys(objectField(found, SKIN)).forEach(function (key) {
      wholeSheet(objectField(found, SKIN)[key]).forEach(function (written) {
        checkColour(null, SKIN, written.value);
      });
    });
  }

  function checkBagOrder(found) {
    DECLARED_BAGS.forEach(function (name) {
      Object.keys(objectField(found, name)).forEach(function (key) {
        if (isReorderedKey(key)) {
          note(null, name, REORDERED_KEY_FAULT, key);
        }
      });
    });
    ORDERED_BAGS.forEach(function (pair) {
      var keys = Object.keys(objectField(found, pair[NAME_AT]));
      var order = listField(found, pair[SECOND_AT]);
      if (order.length !== keys.length) {
        note(null, pair[SECOND_AT], SHORT_LIST_FAULT, order.length);
        return;
      }
      order.forEach(function (key, at) {
        if (key !== keys[at]) {
          note(ROW_AT + String(at), pair[SECOND_AT], DISAGREES_FAULT, key);
        }
      });
    });
  }

  function checkMarkup(where, name, carried) {
    if (typeof carried === STRING_KIND && carries(carried, MARKUP_OPEN)) {
      note(where, name, MARKUP_FAULT, MARKUP_OPEN);
    }
  }

  // Every word drawn as characters, swept for the tags Qt would have read.
  function checkDrawnMarkup(found) {
    [
      CONNECTION_TITLE,
      EXCHANGE_LABEL,
      USE_STORED_LABEL,
      CONNECT_LABEL,
      DISCONNECT_LABEL,
      STATUS_TEXT,
      OPERATIONS_TITLE,
      RESPONSE_TITLE,
      SYMBOL,
      DIAGNOSTICS_LABEL,
      RAW_PROBE_LABEL,
      STATUS_PAGE_LABEL,
      RESULT_PLACEHOLDER,
      HEADLINE
    ].forEach(function (name) {
      checkMarkup(null, name, found[name]);
    });
    listField(found, CREDENTIAL_PLACEHOLDERS).forEach(function (one, at) {
      checkMarkup(ROW_AT + String(at), CREDENTIAL_PLACEHOLDERS, one);
    });
    listField(found, TEST_BUTTONS).forEach(function (row, at) {
      rowOf(row).forEach(function (cell) {
        checkMarkup(ROW_AT + String(at), TEST_BUTTONS, cell);
      });
    });
    listField(found, EXCHANGE_OPTIONS).forEach(function (row, at) {
      rowOf(row).forEach(function (cell) {
        checkMarkup(ROW_AT + String(at), EXCHANGE_OPTIONS, cell);
      });
    });
    listField(found, ENTRIES_FIELD).forEach(function (one, at) {
      if (!isPlainObject(one)) {
        return;
      }
      checkMarkup(ROW_AT + String(at), TITLE, one[TITLE]);
      checkMarkup(ROW_AT + String(at), DETAIL, one[DETAIL]);
    });
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  // This screen only mirrors what the surface holds, so nothing typed lands.
  function nothingChanges() {
    return undefined;
  }

  // A bare colour carries no declaration, so it paints the text and nothing else.
  function paintedStyle(value) {
    if (value === undefined || value === null || value === EMPTY) {
      return {};
    }
    var written = declarations(value);
    if (!written.length) {
      return { color: colour(value) };
    }
    return styleOf(value);
  }

  function wrapStyle(style, wraps) {
    style.whiteSpace = wraps === true ? NORMAL : NOWRAP;
    return style;
  }

  function ExchangeSelect(props) {
    var found = props.model;
    var selectProps = {
      className: TAB_CLASS,
      value: text(found[EXCHANGE_ID]),
      onChange: nothingChanges
    };
    selectProps[PART_ATTR] = EXCHANGE_SELECT_PART;
    selectProps[COUNT_ATTR] = text(listField(found, EXCHANGE_OPTIONS).length);
    selectProps[NAME_ATTR] = text(actionNamed(EXCHANGE_ID));
    var drawn = listField(found, EXCHANGE_OPTIONS).map(function (row, at) {
      var cells = rowOf(row);
      var optionProps = {
        key: EXCHANGE_OPTION_PART + String(at),
        className: TAB_CLASS,
        value: text(cells[SECOND_AT])
      };
      optionProps[PART_ATTR] = EXCHANGE_OPTION_PART;
      optionProps[KEY_ATTR] = text(cells[SECOND_AT]);
      optionProps[INDEX_ATTR] = text(at);
      return element(OPTION_TAG, optionProps, text(cells[NAME_AT]));
    });
    return element(SELECT_TAG, selectProps, drawn);
  }

  function CredentialRow(props) {
    var found = props.model;
    var rowProps = { className: TAB_CLASS, style: { display: FLEX, gap: length(found[MANUAL_SPACING]) } };
    rowProps[PART_ATTR] = MANUAL_ROW_PART;
    rowProps[SHOWN_ATTR] = text(found[MANUAL_VISIBLE]);
    rowProps.hidden = found[MANUAL_VISIBLE] !== true;
    var filled = listField(found, CREDENTIALS_FILLED);
    var drawn = listField(found, CREDENTIAL_PLACEHOLDERS).map(function (one, at) {
      var boxProps = {
        key: CREDENTIAL_BOX_PART + String(at),
        className: TAB_CLASS,
          type: found[CREDENTIALS_HIDDEN] === true ? PASSWORD_KIND : TEXT_KIND,
        placeholder: label(one),
        value: EMPTY,
        readOnly: true
      };
      boxProps[PART_ATTR] = CREDENTIAL_BOX_PART;
      boxProps[KEY_ATTR] = text(one);
      boxProps[INDEX_ATTR] = text(at);
      boxProps[FILLED_ATTR] = text(filled[at]);
      boxProps[ECHO_ATTR] = text(found[ECHO_MODE]);
      return element(INPUT_TAG, boxProps);
    });
    return element(DIV_TAG, rowProps, drawn);
  }

  function ConnectionGroup(props) {
    var found = props.model;
    var groupProps = {
      className: TAB_CLASS,
      style: {
        display: FLEX,
        flexDirection: COLUMN_DIRECTION,
        gap: length(found[CONNECTION_SPACING])
      }
    };
    groupProps[PART_ATTR] = CONNECTION_GROUP_PART;
    var titleProps = { key: CONNECTION_TITLE_PART, className: TAB_CLASS };
    titleProps[PART_ATTR] = CONNECTION_TITLE_PART;
    var labelProps = { key: EXCHANGE_LABEL_PART, className: TAB_CLASS };
    labelProps[PART_ATTR] = EXCHANGE_LABEL_PART;
    var checkProps = {
      key: USE_STORED_PART,
      className: TAB_CLASS,
      type: CHECKBOX_KIND,
      checked: found[USE_STORED] === true,
      onChange: nothingChanges,
      title: label(found[USE_STORED_TOOLTIP])
    };
    checkProps[PART_ATTR] = USE_STORED_PART;
    checkProps[NAME_ATTR] = text(actionNamed(USE_STORED));
    var checkLabelProps = { key: USE_STORED_LABEL_PART, className: TAB_CLASS };
    checkLabelProps[PART_ATTR] = USE_STORED_LABEL_PART;
    var connectProps = {
      key: CONNECT_BUTTON_PART,
      className: TAB_CLASS,
      type: BUTTON_TAG,
      disabled: found[CONNECT_ENABLED] !== true,
      title: label(found[CONNECT_TOOLTIP])
    };
    connectProps[PART_ATTR] = CONNECT_BUTTON_PART;
    connectProps[ENABLED_ATTR] = text(found[CONNECT_ENABLED]);
    var disconnectProps = {
      key: DISCONNECT_BUTTON_PART,
      className: TAB_CLASS,
      type: BUTTON_TAG,
      disabled: found[DISCONNECT_ENABLED] !== true
    };
    disconnectProps[PART_ATTR] = DISCONNECT_BUTTON_PART;
    disconnectProps[ENABLED_ATTR] = text(found[DISCONNECT_ENABLED]);
    var statusProps = {
      key: CONNECTION_STATUS_PART,
      className: TAB_CLASS,
      style: paintedStyle(found[STATUS_STYLE])
    };
    statusProps[PART_ATTR] = CONNECTION_STATUS_PART;
    statusProps[HELD_ATTR] = text(found[CONNECTOR_HELD]);
    return element(DIV_TAG, groupProps, [
      element(DIV_TAG, titleProps, text(found[CONNECTION_TITLE])),
      element(SPAN_TAG, labelProps, text(found[EXCHANGE_LABEL])),
      element(ExchangeSelect, { key: EXCHANGE_SELECT_PART, model: found }),
      element(INPUT_TAG, checkProps),
      element(SPAN_TAG, checkLabelProps, text(found[USE_STORED_LABEL])),
      element(CredentialRow, { key: MANUAL_ROW_PART, model: found }),
      element(BUTTON_TAG, connectProps, text(found[CONNECT_LABEL])),
      element(BUTTON_TAG, disconnectProps, text(found[DISCONNECT_LABEL])),
      element(SPAN_TAG, statusProps, text(found[STATUS_TEXT]))
    ]);
  }

  function OperationsGroup(props) {
    var found = props.model;
    var groupProps = {
      className: TAB_CLASS,
      style: {
        display: FLEX,
        flexDirection: COLUMN_DIRECTION,
        gap: length(found[OPERATIONS_SPACING]),
        width: length(listField(found, SPLITTER_SIZES)[NAME_AT])
      }
    };
    groupProps[PART_ATTR] = OPERATIONS_GROUP_PART;
    var titleProps = { key: OPERATIONS_TITLE_PART, className: TAB_CLASS };
    titleProps[PART_ATTR] = OPERATIONS_TITLE_PART;
    var symbolProps = {
      key: SYMBOL_BOX_PART,
      className: TAB_CLASS,
      type: TEXT_KIND,
      value: text(found[SYMBOL]),
      readOnly: true,
      title: label(found[SYMBOL_TOOLTIP])
    };
    symbolProps[PART_ATTR] = SYMBOL_BOX_PART;
    symbolProps[NAME_ATTR] = text(actionNamed(SYMBOL));
    var drawn = [
      element(DIV_TAG, titleProps, text(found[OPERATIONS_TITLE])),
      element(INPUT_TAG, symbolProps)
    ];
    listField(found, TEST_BUTTONS).forEach(function (row, at) {
      var cells = rowOf(row);
      var buttonProps = {
        key: TEST_BUTTON_PART + String(at),
        className: TAB_CLASS,
        type: BUTTON_TAG,
        title: label(cells[THIRD_AT])
      };
      buttonProps[PART_ATTR] = TEST_BUTTON_PART;
      buttonProps[KEY_ATTR] = text(cells[SECOND_AT]);
      buttonProps[INDEX_ATTR] = text(at);
      drawn.push(element(BUTTON_TAG, buttonProps, text(cells[NAME_AT])));
    });
    var diagnosticsProps = {
      key: DIAGNOSTICS_LABEL_PART,
      className: TAB_CLASS,
      style: paintedStyle(found[DIAGNOSTICS_STYLE])
    };
    diagnosticsProps[PART_ATTR] = DIAGNOSTICS_LABEL_PART;
    diagnosticsProps[KEY_ATTR] = text(found[DIAGNOSTICS_ALIGNMENT]);
    drawn.push(element(DIV_TAG, diagnosticsProps, text(found[DIAGNOSTICS_LABEL])));
    var rawProps = {
      key: RAW_PROBE_PART,
      className: TAB_CLASS,
      type: BUTTON_TAG,
      title: label(found[RAW_PROBE_TOOLTIP])
    };
    rawProps[PART_ATTR] = RAW_PROBE_PART;
    rawProps[COUNT_ATTR] = text(listField(found, PROBE_ENDPOINTS).length);
    rawProps[KEY_ATTR] = text(found[PROBE_HOST]);
    drawn.push(element(BUTTON_TAG, rawProps, text(found[RAW_PROBE_LABEL])));
    var statusProps = {
      key: STATUS_PAGE_PART,
      className: TAB_CLASS,
      type: BUTTON_TAG,
      title: label(found[STATUS_PAGE_TOOLTIP])
    };
    statusProps[PART_ATTR] = STATUS_PAGE_PART;
    statusProps[KEY_ATTR] = text(found[STATUS_PAGE_URL]);
    drawn.push(element(BUTTON_TAG, statusProps, text(found[STATUS_PAGE_LABEL])));
    return element(DIV_TAG, groupProps, drawn);
  }

  function LogEntry(props) {
    var found = props.model;
    var one = listField(found, ENTRIES_FIELD)[props.at];
    var rowProps = { className: TAB_CLASS };
    rowProps[PART_ATTR] = LOG_ENTRY_PART;
    rowProps[INDEX_ATTR] = text(props.at);
    rowProps[LEVEL_ATTR] = text(one[LEVEL]);
    rowProps[KEY_ATTR] = text(one[TITLE]);
    var stampProps = {
      key: ENTRY_STAMP_PART,
      className: TAB_CLASS,
      style: { color: colour(found[TIMESTAMP_COLOR]) }
    };
    stampProps[PART_ATTR] = ENTRY_STAMP_PART;
    var titleProps = {
      key: ENTRY_TITLE_PART,
      className: TAB_CLASS,
      style: {
        color: colour(one[COLOR]),
        fontWeight: text(objectField(found, ENTRY_MARKS)[MARK_STRONG_WEIGHT])
      }
    };
    titleProps[PART_ATTR] = ENTRY_TITLE_PART;
    var timingProps = {
      key: ENTRY_TIMING_PART,
      className: TAB_CLASS,
      style: { color: colour(one[COLOR]) }
    };
    timingProps[PART_ATTR] = ENTRY_TIMING_PART;
    var detailProps = {
      key: ENTRY_DETAIL_PART,
      className: TAB_CLASS,
      style: {
        color: colour(found[DETAIL_COLOR]),
        whiteSpace: text(objectField(found, ENTRY_MARKS)[MARK_DETAIL_WRAP])
      }
    };
    detailProps[PART_ATTR] = ENTRY_DETAIL_PART;
    var marked = objectField(found, ENTRY_MARKS);
    return element(DIV_TAG, rowProps, [
      element(
        SPAN_TAG,
        stampProps,
        String(marked[MARK_STAMP_OPEN]) +
          String(one[STAMP]) +
          String(marked[MARK_STAMP_CLOSE])
      ),
      element(STRONG_TAG, titleProps, text(one[TITLE])),
      element(SPAN_TAG, timingProps, text(one[TIMING])),
      element(DIV_TAG, detailProps, text(one[DETAIL]))
    ]);
  }

  function ResponseGroup(props) {
    var found = props.model;
    var groupProps = {
      className: TAB_CLASS,
      style: { display: FLEX, flexDirection: COLUMN_DIRECTION, flex: STEP }
    };
    groupProps[PART_ATTR] = RESPONSE_GROUP_PART;
    var titleProps = { key: RESPONSE_TITLE_PART, className: TAB_CLASS };
    titleProps[PART_ATTR] = RESPONSE_TITLE_PART;
    var headlineProps = {
      key: RESPONSE_HEADLINE_PART,
      className: TAB_CLASS,
      style: wrapStyle(paintedStyle(found[HEADLINE_STYLE]), found[RESULT_INFO_WORD_WRAP])
    };
    headlineProps[PART_ATTR] = RESPONSE_HEADLINE_PART;
    headlineProps[WRAP_ATTR] = text(found[RESULT_INFO_WORD_WRAP]);
    var logProps = {
      key: RESPONSE_LOG_PART,
      className: TAB_CLASS,
      style: { overflowY: AUTO, width: FULL }
    };
    logProps[PART_ATTR] = RESPONSE_LOG_PART;
    logProps[COUNT_ATTR] = text(found[ENTRY_COUNT]);
    logProps[LOGGED_ATTR] = text(found[ENTRIES_LOGGED]);
    logProps[READ_ONLY_ATTR] = text(found[RESULT_READ_ONLY]);
    var drawn = listField(found, ENTRIES_FIELD).map(function (one, at) {
      return element(LogEntry, { key: LOG_ENTRY_PART + String(at), model: found, at: at });
    });
    if (!drawn.length) {
      var placeholderProps = { key: PLACEHOLDER_PART, className: TAB_CLASS };
      placeholderProps[PART_ATTR] = PLACEHOLDER_PART;
      drawn.push(
        element(DIV_TAG, placeholderProps, text(found[RESULT_PLACEHOLDER]))
      );
    }
    return element(DIV_TAG, groupProps, [
      element(DIV_TAG, titleProps, text(found[RESPONSE_TITLE])),
      element(DIV_TAG, headlineProps, text(found[HEADLINE])),
      element(DIV_TAG, logProps, drawn)
    ]);
  }

  function TabStep(props) {
    var stepProps = { className: TAB_CLASS };
    stepProps[PART_ATTR] = STEP_PART;
    stepProps[INDEX_ATTR] = text(props.at);
    stepProps[KEY_ATTR] = text(rowOf(props.row)[NAME_AT]);
    stepProps.hidden = true;
    return element(DIV_TAG, stepProps, text(rowOf(props.row)[NAME_AT]));
  }

  function Tab(props) {
    var found = isPlainObject(props.model) ? props.model : {};
    var tabProps = {
      id: props.id,
      className: TAB_CLASS,
      style: {
        display: FLEX,
        flexDirection: COLUMN_DIRECTION,
        gap: length(found[LAYOUT_SPACING]),
        minWidth: ZERO
      }
    };
    tabProps[PART_ATTR] = TAB_PART;
    tabProps[SHOWN_ATTR] = text(found[CONNECTED]);
    tabProps[ARIA_LABEL] = label(found[CONNECTION_TITLE]);
    if (!isPlainObject(props.model)) {
      return element(DIV_TAG, tabProps, []);
    }
    var drawn = [
      element(ConnectionGroup, { key: CONNECTION_GROUP_PART, model: found }),
      element(OperationsGroup, { key: OPERATIONS_GROUP_PART, model: found }),
      element(ResponseGroup, { key: RESPONSE_GROUP_PART, model: found })
    ];
    listField(found, CALLS).forEach(function (row, at) {
      drawn.push(element(TabStep, { key: STEP_PART + String(at), row: row, at: at }));
    });
    return element(DIV_TAG, tabProps, drawn);
  }

  function heldFieldCount(found) {
    return DECLARED_FIELDS.filter(function (name) {
      return owns(found, name);
    }).length;
  }

  // Counts fields, entries, buttons and steps declared against those held.
  function report() {
    var found = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        entries: found[ENTRY_COUNT],
        buttons: listField(found, TEST_NAMES).length,
        exchanges: listField(found, EXCHANGE_IDS).length,
        credentials: listField(found, CREDENTIAL_PLACEHOLDERS).length,
        steps: listField(found, CALL_NAMES).length
      },
      held: {
        fields: heldFieldCount(found),
        entries: listField(found, ENTRIES_FIELD).length,
        buttons: listField(found, TEST_BUTTONS).length,
        exchanges: listField(found, EXCHANGE_OPTIONS).length,
        credentials: listField(found, CREDENTIALS_FILLED).length,
        steps: listField(found, CALLS).length
      },
      faults: tabFaults.slice()
    };
  }

  function setTab(found) {
    if (!isPlainObject(found)) {
      held = null;
      tabFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(found))];
      return { declared: null, held: null, faults: tabFaults.slice() };
    }
    held = { model: found };
    tabFaults = [];
    checkFields(found);
    checkPairs(found);
    checkRowWidths(found);
    checkNames(found);
    checkSteps(found);
    checkCounts(found);
    checkEntries(found);
    checkOverclaims(found);
    checkMarks(found);
    checkColours(found);
    checkBagOrder(found);
    checkDrawnMarkup(found);
    return report();
  }

  // Asks METHOD once, clearing asked so a refused first ask is retried.
  function loadTab(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== FUNCTION_KIND) {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (found) {
        loadFault = null;
        setTab(found);
        return found;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function walkPayload(visit) {
    function descend(path, value) {
      if (isPlainObject(value)) {
        walk(path, value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          var inner = path + PATH_SPLIT + String(at);
          visit(inner, one);
          descend(inner, one);
        });
      }
    }
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        visit(path, node[name]);
        descend(path, node[name]);
      });
    }
    if (held !== null) {
      walk(EMPTY, held.model);
    }
  }

  function kinds() {
    var found = {};
    walkPayload(function (path, value) {
      found[path] = kindOf(value);
    });
    return found;
  }

  // Every path whose value is not a string, number, flag, list, bag or null.
  function notPlainData() {
    var found = [];
    walkPayload(function (path, value) {
      var kind = kindOf(value);
      var plain =
        kind === NULL_FAULT ||
        kind === STRING_KIND ||
        kind === NUMBER_KIND ||
        kind === BOOLEAN_KIND ||
        isPlainObject(value) ||
        Array.isArray(value);
      if (!plain) {
        found.push({ path: path, kind: kind });
      }
    });
    return found;
  }

  function faults() {
    return tabFaults.slice();
  }

  function loadError() {
    return loadFault;
  }

  function isLoaded() {
    return held !== null;
  }

  function rootFor(target) {
    var found;
    roots.forEach(function (pair) {
      if (pair.node === target) {
        found = pair.root;
      }
    });
    if (found === undefined) {
      found = global.ReactDOM.createRoot(target);
      roots.push({ node: target, root: found });
    }
    return found;
  }

  // flushSync makes the document current before draw returns.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  // A payload given here is set first, so every drawn piece reads one model.
  function renderTab(target, found) {
    if (isPlainObject(found)) {
      setTab(found);
    }
    return draw(target, element(Tab, { model: held === null ? null : held.model }));
  }

  // The named empty space the renderer left for this screen, or root itself.
  function spaceIn(root) {
    if (!root || typeof root.getAttribute !== FUNCTION_KIND) {
      return null;
    }
    if (root.getAttribute(PART_ATTR) === PAGE_PART) {
      return root;
    }
    if (typeof root.querySelector !== FUNCTION_KIND) {
      return null;
    }
    return root.querySelector(
      SELECT_OPEN + PART_ATTR + SELECT_IS + PAGE_PART + SELECT_CLOSE
    );
  }

  function fill(root, found) {
    var space = spaceIn(root);
    return space === null ? null : renderTab(space, found);
  }

  function forget() {
    held = null;
    tabFaults = [];
    loadFault = null;
    asked = null;
  }

  global.acervatorSetApiTesterTab = setTab;
  global.acervatorLoadApiTesterTab = loadTab;
  global.acervatorApiTesterTab = {
    method: METHOD,
    spacePart: PAGE_PART,
    Tab: Tab,
    ConnectionGroup: ConnectionGroup,
    OperationsGroup: OperationsGroup,
    ResponseGroup: ResponseGroup,
    LogEntry: LogEntry,
    payload: payload,
    declaredNames: declaredNames,
    field: field,
    bag: bag,
    list: list,
    bagKeys: bagKeys,
    marks: marks,
    slots: slots,
    rebuiltLineFormat: rebuiltLineFormat,
    rebuiltEntryLine: rebuiltEntryLine,
    entries: entries,
    entryAt: entryAt,
    levelNames: levelNames,
    levelColour: levelColour,
    exchangeNames: exchangeNames,
    exchangeOptionNamed: exchangeOptionNamed,
    testNames: testNames,
    testButtonNamed: testButtonNamed,
    credentialNames: credentialNames,
    credentialFilledNamed: credentialFilledNamed,
    endpointUrls: endpointUrls,
    endpointNamed: endpointNamed,
    headerNames: headerNames,
    headerNamed: headerNamed,
    hostNamed: hostNamed,
    statusPageNamed: statusPageNamed,
    actionNamed: actionNamed,
    calls: calls,
    callNames: callNames,
    overclaims: overclaims,
    wholeSheet: wholeSheet,
    paintedStyle: paintedStyle,
    isSwappedAlpha: isSwappedAlpha,
    isReorderedKey: isReorderedKey,
    kinds: kinds,
    notPlainData: notPlainData,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderTab: renderTab,
    spaceIn: spaceIn,
    fill: fill,
    forget: forget
  };
})(window);
