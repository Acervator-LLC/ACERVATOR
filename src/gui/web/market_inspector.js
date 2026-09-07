// Draws the Market Inspector screen and its per-bot view from the
// market_inspector.state payload.
(function (global) {
  "use strict";

  var METHOD = "market_inspector.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ACTIVE_SYMBOLS = "active_symbols";
  var ADOPT_SIGNAL_NAME = "adopt_signal_name";
  var AGE = "age";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var CELLS = "cells";
  var COLORS = "colors";
  var ELEMENTS = "elements";
  var EMITTED = "emitted";
  var EMPTY_TEXTS = "empty_texts";
  var ERROR_META = "error_meta";
  var EXCHANGE_SOURCE_WIRED = "exchange_source_wired";
  var FETCH_TEXTS = "fetch_texts";
  var GROUP_MARGINS_PX = "group_margins_px";
  var GROUP_SPACING_PX = "group_spacing_px";
  var LAST_META = "last_meta";
  var LEFT_MARGINS_PX = "left_margins_px";
  var LEFT_MODULE_KEYS = "left_module_keys";
  var LEFT_MODULE_TITLES = "left_module_titles";
  var LEFT_MODULES = "left_modules";
  var RIGHT_ZONES = "right_zones";
  var RIGHT_ZONE_KEYS = "right_zone_keys";
  var RIGHT_ZONE_TITLES = "right_zone_titles";
  var LEFT_SPACING_PX = "left_spacing_px";
  var LOGGER_NAME = "logger_name";
  var LOGS = "logs";
  var MARKS = "marks";
  var METHOD_FIELD = "method";
  var MODULE_FRAME_PX = "module_frame_px";
  var MODULE_MARGINS_PX = "module_margins_px";
  var MODULE_TITLE_PADDING_PX = "module_title_padding_px";
  var BUTTON_PADDING_PX = "button_padding_px";
  var BUTTON_FONT_WEIGHT = "button_font_weight";
  var NO_CELL = "no_cell";
  var OUTER_MARGINS_PX = "outer_margins_px";
  var OUTER_SPACING_PX = "outer_spacing_px";
  var PAIR_COLUMNS = "pair_columns";
  var PAIR_ROWS = "pair_rows";
  var PAIRS_GROUP_TITLE = "pairs_group_title";
  var PAIRS_MAX_HEIGHT_PX = "pairs_max_height_px";
  var PENDING_REFRESH = "pending_refresh";
  var PER_BOT = "per_bot";
  var PER_BOT_MARGINS_PX = "per_bot_margins_px";
  var PER_BOT_SPACING_PX = "per_bot_spacing_px";
  var PER_BOT_VIEW = "per_bot_view";
  var REFRESH_ENABLED = "refresh_enabled";
  var REFRESH_LABEL = "refresh_label";
  var REFRESH_TOOLTIP = "refresh_tooltip";
  var SCAN = "scan";
  var SCAN_STATE = "scan_state";
  var SCHEDULED = "scheduled";
  var SHOW_ACTIVE = "show_active";
  var SHOW_ACTIVE_CHECKED = "show_active_checked";
  var SHOW_ACTIVE_DEFAULT = "show_active_default";
  var SHOW_ACTIVE_LABEL = "show_active_label";
  var SHOW_ACTIVE_TOOLTIP = "show_active_tooltip";
  var SIGNAL_COLUMNS = "signal_columns";
  var SIGNAL_NAMES = "signal_names";
  var SIGNAL_ROWS = "signal_rows";
  var SIGNALS_GROUP_TITLE = "signals_group_title";
  var SIGNALS_MAX_HEIGHT_PX = "signals_max_height_px";
  var SKIN = "skin";
  var SOURCES = "sources";
  var SPLITTER_ORIENTATION = "splitter_orientation";
  var SPLITTER_PANES = "splitter_panes";
  var SPLITTER_HANDLE_PX = "splitter_handle_px";
  var SPLITTER_SIZES_PX = "splitter_sizes_px";
  var SPLITTER_STRETCH = "splitter_stretch";
  var STATUS_FORMATS = "status_formats";
  var STATUS_INITIAL_TEXT = "status_initial_text";
  var STATUS_STYLE = "status_style";
  var STATUS_TEXT = "status_text";
  var STYLE_SHEET = "style_sheet";
  var SYMBOLS = "symbols";
  var TABLE_ALTERNATING_ROWS = "table_alternating_rows";
  var TABLE_EDIT_TRIGGERS = "table_edit_triggers";
  var TABLE_RESIZE_MODE = "table_resize_mode";
  var TABLE_VIEWPORT_PX = "table_viewport_px";
  var TIMEFRAME = "timeframe";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMERS = "timers";
  var TOP_ROW_MARGINS_PX = "top_row_margins_px";
  var TOP_ROW_SPACING_PX = "top_row_spacing_px";

  // DECLARED_FIELDS lists every top-level field of the payload.
  var DECLARED_FIELDS = [
    ACCESSIBLE_NAME,
    ACTIONS,
    ACTIVE_SYMBOLS,
    ADOPT_SIGNAL_NAME,
    AGE,
    BUS_TOPICS,
    BUTTON_FONT_WEIGHT,
    BUTTON_PADDING_PX,
    CALL_NAMES,
    CALLS,
    CELLS,
    COLORS,
    ELEMENTS,
    EMITTED,
    EMPTY_TEXTS,
    ERROR_META,
    EXCHANGE_SOURCE_WIRED,
    FETCH_TEXTS,
    GROUP_MARGINS_PX,
    GROUP_SPACING_PX,
    LAST_META,
    LEFT_MARGINS_PX,
    LEFT_MODULE_KEYS,
    LEFT_MODULE_TITLES,
    LEFT_MODULES,
    LEFT_SPACING_PX,
    RIGHT_ZONES,
    RIGHT_ZONE_KEYS,
    RIGHT_ZONE_TITLES,
    LOGGER_NAME,
    LOGS,
    MARKS,
    METHOD_FIELD,
    MODULE_FRAME_PX,
    MODULE_MARGINS_PX,
    MODULE_TITLE_PADDING_PX,
    NO_CELL,
    OUTER_MARGINS_PX,
    OUTER_SPACING_PX,
    PAIR_COLUMNS,
    PAIR_ROWS,
    PAIRS_GROUP_TITLE,
    PAIRS_MAX_HEIGHT_PX,
    PENDING_REFRESH,
    PER_BOT,
    PER_BOT_MARGINS_PX,
    PER_BOT_SPACING_PX,
    PER_BOT_VIEW,
    REFRESH_ENABLED,
    REFRESH_LABEL,
    REFRESH_TOOLTIP,
    SCAN,
    SCAN_STATE,
    SCHEDULED,
    SHOW_ACTIVE,
    SHOW_ACTIVE_CHECKED,
    SHOW_ACTIVE_DEFAULT,
    SHOW_ACTIVE_LABEL,
    SHOW_ACTIVE_TOOLTIP,
    SIGNAL_COLUMNS,
    SIGNAL_NAMES,
    SIGNAL_ROWS,
    SIGNALS_GROUP_TITLE,
    SIGNALS_MAX_HEIGHT_PX,
    SKIN,
    SOURCES,
    SPLITTER_HANDLE_PX,
    SPLITTER_ORIENTATION,
    SPLITTER_PANES,
    SPLITTER_SIZES_PX,
    SPLITTER_STRETCH,
    STATUS_FORMATS,
    STATUS_INITIAL_TEXT,
    STATUS_STYLE,
    STATUS_TEXT,
    STYLE_SHEET,
    SYMBOLS,
    TABLE_ALTERNATING_ROWS,
    TABLE_EDIT_TRIGGERS,
    TABLE_RESIZE_MODE,
    TABLE_VIEWPORT_PX,
    TIMEFRAME,
    TIMER_DELAYS_MS,
    TIMERS,
    TOP_ROW_MARGINS_PX,
    TOP_ROW_SPACING_PX
  ];

  var ACTIVE = "active";
  var CORRELATION = "correlation";
  var ENTRY_LONG = "entry_long";
  var ENTRY_LONG_HIGH = "entry_long_high";
  var ENTRY_SHORT = "entry_short";
  var ENTRY_SHORT_HIGH = "entry_short_high";
  var NONE_COLOUR = "none";
  var OTHER = "other";
  var WATCHLIST = "watchlist";

  var COLOR_FIELDS = [
    ACTIVE,
    CORRELATION,
    ENTRY_LONG,
    ENTRY_LONG_HIGH,
    ENTRY_SHORT,
    ENTRY_SHORT_HIGH,
    NONE_COLOUR,
    OTHER,
    WATCHLIST
  ];

  var SIGNAL_NAME_FIELDS = [
    ENTRY_LONG,
    ENTRY_LONG_HIGH,
    ENTRY_SHORT,
    ENTRY_SHORT_HIGH,
    WATCHLIST
  ];

  var EMPTY_MARK = "empty";
  var FORMAT = "format";
  var KEYS = "keys";
  var LINE_FORMAT = "line_format";
  var NO_TIGHT_SUFFIX = "no_tight_suffix";
  var TAG_LOWER = "tag_lower";
  var TAG_MIDDLE = "tag_middle";
  var TAG_UPPER = "tag_upper";
  var TIGHT_SUFFIX = "tight_suffix";

  var TIMEFRAME_FIELDS = [
    EMPTY_MARK,
    FORMAT,
    KEYS,
    LINE_FORMAT,
    NO_TIGHT_SUFFIX,
    TAG_LOWER,
    TAG_MIDDLE,
    TAG_UPPER,
    TIGHT_SUFFIX
  ];

  var ACTIVE_NO = "active_no";
  var ACTIVE_YES = "active_yes";
  var CORRELATION_FORMAT = "correlation_format";
  var PAIR_SCORE_FORMAT = "pair_score_format";
  var PAIR_SIDE_FORMAT = "pair_side_format";
  var SCORE_FORMAT = "score_format";

  var CELL_FIELDS = [
    ACTIVE_NO,
    ACTIVE_YES,
    CORRELATION_FORMAT,
    PAIR_SCORE_FORMAT,
    PAIR_SIDE_FORMAT,
    SCORE_FORMAT
  ];

  var DAY_S = "day_s";
  var DAYS_FORMAT = "days_format";
  var HOUR_S = "hour_s";
  var HOURS_FORMAT = "hours_format";
  var HOURS_MINUTES_FORMAT = "hours_minutes_format";
  var MINUTE_S = "minute_s";
  var MINUTES_FORMAT = "minutes_format";
  var NO_AGE_S = "no_age_s";
  var SECONDS_FORMAT = "seconds_format";

  var AGE_FIELDS = [
    DAY_S,
    DAYS_FORMAT,
    HOUR_S,
    HOURS_FORMAT,
    HOURS_MINUTES_FORMAT,
    MINUTE_S,
    MINUTES_FORMAT,
    NO_AGE_S,
    SECONDS_FORMAT
  ];

  var CACHE = "cache";
  var COINGECKO = "coingecko";
  var ERROR_SOURCE = "error";
  var NETWORK_PARTIAL = "network_partial";
  var UNKNOWN_SOURCE = "unknown";

  var SOURCE_FIELDS = [
    CACHE,
    COINGECKO,
    ERROR_SOURCE,
    NETWORK_PARTIAL,
    UNKNOWN_SOURCE
  ];

  var CACHE_FALLBACK = "cache_fallback";
  var LIVE = "live";
  var NO_CANDLES = "no_candles";
  var PARTIAL = "partial";
  var UNKNOWN_ERROR = "unknown_error";

  var STATUS_FORMAT_FIELDS = [
    CACHE,
    CACHE_FALLBACK,
    ERROR_SOURCE,
    LIVE,
    NO_CANDLES,
    PARTIAL,
    UNKNOWN_ERROR
  ];

  var ANALYZER_ERROR = "analyzer_error";
  var ANALYZER_UNAVAILABLE = "analyzer_unavailable";
  var FETCHING = "fetching";
  var NO_CONNECTORS = "no_connectors";
  var NOT_WIRED = "not_wired";
  var SCHEDULER_ERROR = "scheduler_error";

  var FETCH_TEXT_FIELDS = [
    ANALYZER_ERROR,
    ANALYZER_UNAVAILABLE,
    FETCHING,
    NO_CONNECTORS,
    NOT_WIRED,
    SCHEDULER_ERROR
  ];

  var FETCH_FAILED = "fetch_failed";
  var PROPOSALS_FAILED = "proposals_failed";
  var SCAN_FAILED = "scan_failed";
  var TOPOLOGIES_MISSING = "topologies_missing";

  var LOG_FIELDS = [FETCH_FAILED, PROPOSALS_FAILED, SCAN_FAILED, TOPOLOGIES_MISSING];

  var AGE_SECONDS = "age_seconds";
  var SOURCE = "source";
  var SYMBOL_COUNT = "symbol_count";

  var ERROR_META_FIELDS = [AGE_SECONDS, SOURCE, SYMBOL_COUNT];

  var EMPTY_PAIRS = "pairs";
  var EMPTY_SIGNALS = "signals";
  var EMPTY_TEXT_FIELDS = [EMPTY_PAIRS, EMPTY_SIGNALS];

  var SCAN_EMPTY_FORMAT = "empty_format";
  var SCAN_ERROR_SUFFIX = "error_suffix";
  var SCAN_FINISHED = "finished";
  var SCAN_FINISHED_TOPIC = "finished_topic";
  var SCAN_NOT_ASKED = "not_asked";
  var SCAN_NO_DURATION_S = "no_duration_s";
  var SCAN_NO_SCAN_FORMAT = "no_scan_format";
  var SCAN_PAIRS_NOUN = "pairs_noun";
  var SCAN_PHASES = "phases";
  var SCAN_RUNNING = "running";
  var SCAN_SCANNING_FORMAT = "scanning_format";
  var SCAN_SIGNALS_NOUN = "signals_noun";
  var SCAN_STARTED_TOPIC = "started_topic";
  var SCAN_UNKNOWN_SOURCE = "unknown_source";
  var SCAN_FIELDS = [
    SCAN_EMPTY_FORMAT,
    SCAN_ERROR_SUFFIX,
    SCAN_FINISHED,
    SCAN_FINISHED_TOPIC,
    SCAN_NOT_ASKED,
    SCAN_NO_DURATION_S,
    SCAN_NO_SCAN_FORMAT,
    SCAN_PAIRS_NOUN,
    SCAN_PHASES,
    SCAN_RUNNING,
    SCAN_SCANNING_FORMAT,
    SCAN_SIGNALS_NOUN,
    SCAN_STARTED_TOPIC,
    SCAN_UNKNOWN_SOURCE
  ];

  var HIGHER_GROUP_TITLE = "higher_group_title";
  var HIGHER_LIMIT = "higher_limit";
  var HIGHER_ROW_ACTIVE_SUFFIX = "higher_row_active_suffix";
  var HIGHER_ROW_FORMAT = "higher_row_format";
  var HIGHER_ROW_QUIET_SUFFIX = "higher_row_quiet_suffix";
  var HIGHER_ROW_STYLE_FORMAT = "higher_row_style_format";
  var NO_DIRECTION_MARK = "no_direction_mark";
  var NO_SCAN_BODY = "no_scan_body";
  var NO_SCAN_BREAKS = "no_scan_breaks";
  var NO_SCAN_HEADLINE = "no_scan_headline";
  var NO_SCAN_STYLE = "no_scan_style";
  var NO_SCAN_TEXT = "no_scan_text";
  var NO_SCAN_WORD_WRAP = "no_scan_word_wrap";
  var NO_SCORE = "no_score";
  var NO_SIGNAL_FORMAT = "no_signal_format";
  var OWN_CARD_TITLE_FORMAT = "own_card_title_format";
  var PAIR_FORMAT = "pair_format";
  var SIGNAL_LINE_FORMAT = "signal_line_format";
  var SIGNAL_LINE_LEAD = "signal_line_lead";
  var SIGNAL_LINE_MARK = "signal_line_mark";
  var SIGNAL_LINE_STYLE_FORMAT = "signal_line_style_format";
  var SIGNAL_LINE_TAIL_FORMAT = "signal_line_tail_format";
  var THIS_ASSET_TEXT = "this_asset_text";
  var UNAVAILABLE = "unavailable";
  var UNKNOWN_ASSET_MARK = "unknown_asset_mark";

  var PER_BOT_FIELDS = [
    HIGHER_GROUP_TITLE,
    HIGHER_LIMIT,
    HIGHER_ROW_ACTIVE_SUFFIX,
    HIGHER_ROW_FORMAT,
    HIGHER_ROW_QUIET_SUFFIX,
    HIGHER_ROW_STYLE_FORMAT,
    NO_DIRECTION_MARK,
    NO_SCAN_BODY,
    NO_SCAN_BREAKS,
    NO_SCAN_HEADLINE,
    NO_SCAN_STYLE,
    NO_SCAN_TEXT,
    NO_SCAN_WORD_WRAP,
    NO_SCORE,
    NO_SIGNAL_FORMAT,
    OWN_CARD_TITLE_FORMAT,
    PAIR_FORMAT,
    PAIRS_GROUP_TITLE,
    SIGNAL_LINE_FORMAT,
    SIGNAL_LINE_LEAD,
    SIGNAL_LINE_MARK,
    SIGNAL_LINE_STYLE_FORMAT,
    SIGNAL_LINE_TAIL_FORMAT,
    THIS_ASSET_TEXT,
    UNAVAILABLE,
    UNKNOWN_ASSET_MARK
  ];

  // GROUP_ELEMENT, LABEL_ELEMENT and STRETCH_ELEMENT name one order entry.
  var GROUP_ELEMENT = "group";
  var LABEL_ELEMENT = "label";
  var STRETCH_ELEMENT = "stretch";
  var NO_STYLE = "no_style";
  var NO_WORD_WRAP = "no_word_wrap";

  var ELEMENT_FIELDS = [
    GROUP_ELEMENT,
    LABEL_ELEMENT,
    NO_STYLE,
    NO_WORD_WRAP,
    STRETCH_ELEMENT
  ];

  var NO_ASSET = "no_asset";
  var NO_SYMBOL = "no_symbol";
  var SEPARATOR = "separator";

  var SYMBOL_FIELDS = [NO_ASSET, NO_SYMBOL, SEPARATOR];

  var BREAK_TAG = "break_tag";
  var NO_BREAKS = "no_breaks";
  var NO_PIECE = "no_piece";
  var STRONG_CLOSE = "strong_close";
  var STRONG_OPEN = "strong_open";
  var STRONG_WEIGHT = "strong_weight";

  var MARK_FIELDS = [
    BREAK_TAG,
    NO_BREAKS,
    NO_PIECE,
    STRONG_CLOSE,
    STRONG_OPEN,
    STRONG_WEIGHT
  ];

  var ASSET = "asset";
  var MARGINS_PX = "margins_px";
  var ORDER = "order";
  var SPACING_PX = "spacing_px";

  var PER_BOT_VIEW_FIELDS = [ASSET, MARGINS_PX, MARKS, ORDER, SPACING_PX];

  var ADOPT_REQUESTED = "adopt_requested";
  var REFRESH_CLICKED = "refresh_clicked";
  var SHOW_ACTIVE_TOGGLED = "show_active_toggled";

  var ACTION_FIELDS = [ADOPT_REQUESTED, REFRESH_CLICKED, SHOW_ACTIVE_TOGGLED];

  var BAG_FIELDS = {};
  BAG_FIELDS[ACTIONS] = ACTION_FIELDS;
  BAG_FIELDS[AGE] = AGE_FIELDS;
  BAG_FIELDS[CELLS] = CELL_FIELDS;
  BAG_FIELDS[COLORS] = COLOR_FIELDS;
  BAG_FIELDS[ELEMENTS] = ELEMENT_FIELDS;
  BAG_FIELDS[EMPTY_TEXTS] = EMPTY_TEXT_FIELDS;
  BAG_FIELDS[ERROR_META] = ERROR_META_FIELDS;
  BAG_FIELDS[SCAN] = SCAN_FIELDS;
  BAG_FIELDS[FETCH_TEXTS] = FETCH_TEXT_FIELDS;
  BAG_FIELDS[LOGS] = LOG_FIELDS;
  BAG_FIELDS[MARKS] = MARK_FIELDS;
  BAG_FIELDS[PER_BOT] = PER_BOT_FIELDS;
  BAG_FIELDS[PER_BOT_VIEW] = PER_BOT_VIEW_FIELDS;
  BAG_FIELDS[SIGNAL_NAMES] = SIGNAL_NAME_FIELDS;
  BAG_FIELDS[SOURCES] = SOURCE_FIELDS;
  BAG_FIELDS[STATUS_FORMATS] = STATUS_FORMAT_FIELDS;
  BAG_FIELDS[SYMBOLS] = SYMBOL_FIELDS;
  BAG_FIELDS[TIMEFRAME] = TIMEFRAME_FIELDS;

  // WANTED_LISTS names every top-level field this module walks as a list.
  var WANTED_LISTS = [
    ACTIVE_SYMBOLS,
    BUS_TOPICS,
    BUTTON_PADDING_PX,
    CALL_NAMES,
    CALLS,
    EMITTED,
    GROUP_MARGINS_PX,
    LEFT_MARGINS_PX,
    LEFT_MODULE_KEYS,
    LEFT_MODULE_TITLES,
    LEFT_MODULES,
    MODULE_MARGINS_PX,
    RIGHT_ZONES,
    RIGHT_ZONE_KEYS,
    RIGHT_ZONE_TITLES,
    MODULE_TITLE_PADDING_PX,
    OUTER_MARGINS_PX,
    PAIR_COLUMNS,
    PAIR_ROWS,
    PER_BOT_MARGINS_PX,
    SCHEDULED,
    SIGNAL_COLUMNS,
    SIGNAL_ROWS,
    SPLITTER_SIZES_PX,
    SPLITTER_STRETCH,
    TIMER_DELAYS_MS,
    TOP_ROW_MARGINS_PX
  ];

  // WANTED_BAGS names every top-level field this module walks by key.
  var WANTED_BAGS = [
    ACTIONS,
    AGE,
    CELLS,
    COLORS,
    ELEMENTS,
    EMPTY_TEXTS,
    ERROR_META,
    FETCH_TEXTS,
    LAST_META,
    LOGS,
    MARKS,
    PER_BOT,
    PER_BOT_VIEW,
    SCAN,
    SIGNAL_NAMES,
    SKIN,
    SOURCES,
    STATUS_FORMATS,
    SYMBOLS,
    TIMEFRAME,
    TIMERS
  ];

  var MISSING_FAULT = "missing";
  var NULL_FAULT = "null";
  var NOT_AN_OBJECT_FAULT = "not-an-object";
  var NOT_A_LIST_FAULT = "not-a-list";
  var WRONG_TYPE_FAULT = "wrong-type";
  var QT_COLOUR_FAULT = "qt-colour";
  var NOT_CSS_FAULT = "not-css";
  var MARKUP_FAULT = "markup";
  var CELL_SHAPE_FAULT = "cell-shape";
  var COLUMN_COUNT_FAULT = "column-count";
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var UNKNOWN_ELEMENT_FAULT = "unknown-element";
  var MARK_MISMATCH_FAULT = "mark-mismatch";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";

  var NULL_KIND = "null";
  var OBJECT_KIND = "object";
  var STRING_KIND = "string";
  var NO_BRIDGE = "the preload bridge is not present";

  // MARKUP_OPEN starts a tag a Qt rich-text label reads as formatting.
  var MARKUP_OPEN = "<";

  var EMPTY = "";
  var NEWLINE = "\n";
  var PATH_SPLIT = ".";
  var HASH = "#";
  var GAP = " ";
  var COLON = ":";
  var SEMICOLON = ";";
  var COMMA = ",";
  var DOT = ".";
  var PERCENT = "%";
  var CLOSE_BRACKET = ")";
  var PX = "px";
  var VAR_OPEN = "var(--";
  var VAR_SPLIT = ", ";
  var VAR_CLOSE = ")";
  var CALC_OPEN = "calc(";
  var PX_FACTOR = " * 1px)";
  var RGBA_OPEN = "rgba(";
  // Qt reads an eight-digit hex alpha first, CSS reads it last.
  var HEX_ARGB = "AARRGGBB";

  var PADDING_SIDES = [
    "paddingLeft",
    "paddingTop",
    "paddingRight",
    "paddingBottom"
  ];

  // Every length here is a layout step, so only spacing means the same thing.
  var LENGTH_GROUPS = ["spacing"];

  // ACROSS_ORIENTATION and TO_CONTENTS_MODE are the Qt words a layout reads.
  var ACROSS_ORIENTATION = "Horizontal";
  var TO_CONTENTS_MODE = "ResizeToContents";

  var FLEX = "flex";
  var FLEX_NONE = "none";
  // Three equally sized rectangles down each side, as the Qt stretch gives.
  var EQUAL_SHARE = "1 1 0";
  // A table takes what its zone leaves and scrolls, as the Qt table does.
  var SHRINK_SHARE = "1 1 auto";
  var AUTO = "auto";
  var ROW_WAY = "row";
  var COLUMN_WAY = "column";
  var CENTER = "center";
  var FULL = "100%";
  var MIN_CONTENT = "min-content";
  var MAX_CONTENT = "max-content";
  var COLLAPSE = "collapse";
  var CLIPPED = "hidden";
  var ELLIPSIS = "ellipsis";
  var NO_WRAP = "nowrap";
  var NO_SELECT = "none";
  var PRE = "pre";
  var PRE_WRAP = "pre-wrap";
  var RELATIVE = "relative";
  var ABSOLUTE = "absolute";
  var SOLID = "solid";
  var NO_OFFSET = 0;

  var ZERO = Number(EMPTY);
  var ONE = Number(true);
  var TWO = ONE + ONE;
  var THREE = TWO + ONE;

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var STRONG_TAG = "strong";
  var BUTTON_TAG = "button";
  var LABEL_TAG = "label";
  var INPUT_TAG = "input";
  var FIELDSET_TAG = "fieldset";
  var LEGEND_TAG = "legend";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var TR_TAG = "tr";
  var TH_TAG = "th";
  var TD_TAG = "td";

  var BUTTON_TYPE = "button";
  var CHECKBOX_TYPE = "checkbox";

  var SCREEN_PART = "screen";
  var SPLIT_PART = "split";
  var LEFT_PANE_PART = "left-pane";
  var FILTER_ROW_PART = "filter-row";
  var REFRESH_PART = "refresh-button";
  var SWITCH_PART = "active-switch";
  var SWITCH_BOX_PART = "switch-box";
  var SWITCH_TEXT_PART = "switch-text";
  var FILTER_STRETCH_PART = "filter-stretch";
  var STATUS_PART = "status-line";
  var MODULE_GROUP_PART = "module-group";
  var MODULE_LEGEND_PART = "module-legend";
  var MODULE_STATUS_PART = "module-status";
  var TABLE_GROUP_PART = "table-group";
  var GROUP_LEGEND_PART = "group-legend";
  var GROUP_BODY_PART = "group-body";
  var EMPTY_NOTE_PART = "empty-note";
  var GRID_PART = "grid";
  var GRID_HEAD_PART = "grid-head";
  var HEAD_ROW_PART = "head-row";
  var HEAD_CELL_PART = "head-cell";
  var GRID_BODY_PART = "grid-body";
  var GRID_ROW_PART = "grid-row";
  var GRID_CELL_PART = "grid-cell";
  var LEFT_STRETCH_PART = "left-stretch";
  var TOPOLOGY_PART = "topology-slot";
  var RIGHT_PANE_PART = "right-pane";
  var PER_BOT_PART = "per-bot";
  var PER_BOT_LABEL_PART = "per-bot-label";
  var PER_BOT_CARD_PART = "per-bot-card";
  var CARD_LEGEND_PART = "card-legend";
  var CARD_BODY_PART = "card-body";
  var PER_BOT_STRETCH_PART = "per-bot-stretch";
  var MARK_LEAD_PART = "mark-lead";
  var MARK_STRONG_PART = "mark-strong";
  var MARK_TAIL_PART = "mark-tail";

  var STEPPER_PART = "zone-stepper";
  var STEP_ROW_PART = "step-row";
  var STEP_BACK_PART = "step-back";
  var STEP_NEXT_PART = "step-next";
  var POSITION_PART = "zone-position";
  var ENTRY_PART = "zone-entry";
  var ENTRY_BODY_PART = "entry-body";
  var ENTRY_HEAD_PART = "entry-head";
  var HEADLINE_PART = "entry-headline";
  var ENTRY_BADGE_PART = "entry-badge";
  var ENTRY_META_PART = "entry-meta";
  var ENTRY_METHOD_PART = "entry-method";
  var ENTRY_HINT_PART = "entry-hint";
  var DETAIL_PART = "entry-detail";

  var ZONES = "zones";
  var STEPPER = "stepper";
  var ZONE_KEY = "key";
  var ZONE_TOTAL = "total";
  var ZONE_POSITION = "position";
  var ZONE_HEADLINE = "headline";
  var ZONE_META = "meta";
  var ZONE_METHOD = "method";
  var ZONE_DETAIL = "detail";
  var ZONE_BADGE = "badge";
  var ZONE_BADGE_STYLE = "badge_style";

  var BACK_TEXT = "back_text";
  var NEXT_TEXT = "next_text";
  var BACK_TOOLTIP = "back_tooltip";
  var NEXT_TOOLTIP = "next_tooltip";
  var BUTTON_WIDTH_PX = "button_width_px";
  var BUTTON_STYLE = "button_style";
  var POSITION_STYLE = "position_style";
  var ENTRY_STYLE = "entry_style";
  var ENTRY_MARGINS_PX = "entry_margins_px";
  var ENTRY_SPACING_PX = "entry_spacing_px";
  var HEADLINE_STYLE = "headline_style";
  var META_STYLE = "meta_style";
  var METHOD_STYLE = "method_style";
  var HINT_TEXT = "hint_text";
  var HINT_STYLE = "hint_style";
  var DETAIL_STYLE = "detail_style";
  var ENTRY_NAME = "entry_accessible_name";
  var STEPPER_NAME = "stepper_accessible_name";

  var STEP_ZONE_FIELD = "step_zone";
  var STEP_FIELD = "step";
  var TOGGLE_ZONE_FIELD = "toggle_zone";
  var POINTER = "pointer";
  var INHERITED = "inherit";
  var PRE_SPACE = "pre";

  var SIGNALS_TABLE = "signals";
  var PAIRS_TABLE = "pairs";

  var TOPOLOGY_SLOT = "market-inspector-topologies";

  var PART_ATTR = "data-part";
  var TABLE_ATTR = "data-table";
  var STATE_ATTR = "data-scan-state";
  var NAME_ATTR = "data-name";
  var COLUMN_ATTR = "data-column";
  var AT_ATTR = "data-at";
  var ENTRIES_ATTR = "data-entries";
  var ALTERNATING_ATTR = "data-alternating";
  var ROWS_ATTR = "data-rows";
  var SLOT_ATTR = "data-slot";
  var SLOT_SELECTOR = "[data-slot=\"market-inspector-topologies\"]";
  var FUNCTION_KIND = "function";
  var ARIA_LABEL = "aria-label";

  var held = null;
  var screenFaults = [];
  var loadFault = null;
  var asked = null;
  var roots = [];
  var hostTarget = null;

  function isPlainObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function owns(bag, name) {
    return Object.prototype.hasOwnProperty.call(bag, name);
  }

  // asList answers the value when it is a list, and an empty one otherwise.
  function asList(value) {
    return Array.isArray(value) ? value : [];
  }

  function objectField(model, field) {
    return isPlainObject(model) && isPlainObject(model[field]) ? model[field] : {};
  }

  function listField(model, field) {
    return isPlainObject(model) ? asList(model[field]) : [];
  }

  function copyOf(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function kindOf(value) {
    if (value === null) {
      return NULL_KIND;
    }
    return Array.isArray(value) ? OBJECT_KIND : typeof value;
  }

  // text answers undefined so an attribute stays off the element.
  function text(value) {
    return value === null || value === undefined ? undefined : String(value);
  }

  // label answers undefined for an empty name, keeping the attribute off.
  function label(value) {
    return typeof value === STRING_KIND && value.length ? value : undefined;
  }

  function fault(where, field, kind, detail) {
    return { where: where, field: field, fault: kind, detail: detail };
  }

  function note(where, field, kind, detail) {
    screenFaults.push(fault(where, field, kind, detail));
  }

  function element() {
    return global.React.createElement.apply(null, arguments);
  }

  function afterFirst(value, splitter) {
    var parts = String(value).split(splitter);
    parts.shift();
    return parts;
  }

  function carries(value, splitter) {
    return Boolean(afterFirst(value, splitter).length);
  }

  // repeated answers `body` written `count` times, or nothing when it cannot.
  function repeated(body, count) {
    try {
      return String(body).repeat(count);
    } catch (refused) {
      return EMPTY;
    }
  }

  // The first hex word of one value, empty when it carries none.
  function hexWord(value) {
    var parts = afterFirst(value, HASH);
    if (!parts.length) {
      return EMPTY;
    }
    return String(parts.shift()).trim().split(GAP).shift();
  }

  // byteAlpha answers true for an alpha Qt counts in bytes.
  function byteAlpha(value) {
    var parts = afterFirst(value, RGBA_OPEN);
    if (!parts.length) {
      return false;
    }
    var fields = String(parts.shift()).split(CLOSE_BRACKET).shift().split(COMMA);
    fields.shift();
    fields.shift();
    fields.shift();
    var alpha = fields.shift();
    if (alpha === undefined) {
      return false;
    }
    return !carries(alpha, DOT) && !carries(alpha, PERCENT);
  }

  // The reason CSS would read one value as a different colour.
  function qtColour(value) {
    if (hexWord(value).length === HEX_ARGB.length) {
      return HEX_ARGB;
    }
    return byteAlpha(value) ? RGBA_OPEN : undefined;
  }

  // sheetApi finds acervatorHeader, which owns the Qt sheet grammar.
  function sheetApi() {
    var api = global.acervatorHeader;
    if (!api || typeof api.styleOf !== "function") {
      return undefined;
    }
    return api;
  }

  function declarations(sheet) {
    var api = sheetApi();
    return api === undefined ? [] : api.declarations(sheet);
  }

  function stateRules(sheet) {
    var api = sheetApi();
    return api === undefined ? [] : api.stateRules(sheet);
  }

  // A sheet without the declarations CSS would read as another colour.
  function keptSheet(sheet) {
    var kept = [];
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) === undefined) {
        kept.push(one.property + COLON + one.value);
      }
    });
    return kept.join(SEMICOLON);
  }

  function styleOf(sheet) {
    var api = sheetApi();
    return api === undefined ? {} : api.styleOf(keptSheet(sheet));
  }

  // variableFor asks acervatorWidgets, which owns the one-carrier token rule.
  function variableFor(value) {
    var api = global.acervatorWidgets;
    if (!api || typeof api.variableFor !== "function") {
      return undefined;
    }
    return api.variableFor(value);
  }

  // Whether `name` sits in one of `groups`, so its meaning matches.
  function inGroups(name, groups) {
    var api = global.acervatorTokens;
    if (!api || typeof api.group !== "function") {
      return false;
    }
    var matched = groups.filter(function (one) {
      return owns(api.group(one), name);
    });
    return Boolean(matched.length);
  }

  // The token name for `value`, only from a group meaning the same thing.
  function variableInGroups(value, groups) {
    var name = variableFor(value);
    if (name === undefined || !inGroups(name, groups)) {
      return undefined;
    }
    return name;
  }

  // A token holds a bare number, so `calc` scales it to a CSS length.
  function length(value) {
    if (value === null || value === undefined) {
      return undefined;
    }
    var name = variableInGroups(value, LENGTH_GROUPS);
    if (name === undefined) {
      return String(value) + PX;
    }
    return (
      CALC_OPEN + VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE + PX_FACTOR
    );
  }

  // Plain paint: a token holding a signal colour names another meaning.
  function colour(value) {
    if (value === null || value === undefined || qtColour(value) !== undefined) {
      return undefined;
    }
    return String(value);
  }

  function marginStyle(margins) {
    var style = {};
    PADDING_SIDES.forEach(function (side, at) {
      if (at < margins.length) {
        style[side] = length(margins[at]);
      }
    });
    return style;
  }

  function merged(into, from) {
    Object.keys(from).forEach(function (name) {
      into[name] = from[name];
    });
    return into;
  }

  function boxStyle(margins, spacing, way) {
    var style = marginStyle(margins);
    style.display = FLEX;
    style.flexDirection = way;
    style.gap = length(spacing);
    return style;
  }

  // Qt wraps a label at word ends, and clips it to one flow when it does not.
  function wrapMode(wraps) {
    return wraps ? PRE_WRAP : PRE;
  }

  // A Qt label carries no drag selection and never wraps on its own.
  function asLabel(style, wraps) {
    style.whiteSpace = wrapMode(wraps);
    style.userSelect = NO_SELECT;
    style.flex = FLEX_NONE;
    return style;
  }

  // A Qt table cell cuts its text on the right rather than wrapping it.
  function asCell(style) {
    style.whiteSpace = NO_WRAP;
    style.overflow = CLIPPED;
    style.textOverflow = ELLIPSIS;
    style.userSelect = NO_SELECT;
    return style;
  }

  function cellText(cell) {
    return Array.isArray(cell) ? cell[ZERO] : undefined;
  }

  function cellColour(cell) {
    return Array.isArray(cell) ? cell[ONE] : undefined;
  }

  function rowName(row) {
    return text(cellText(asList(row)[ZERO]));
  }

  function Spacer(props) {
    var spacerProps = { style: { flex: AUTO } };
    spacerProps[PART_ATTR] = props.part;
    return element(DIV_TAG, spacerProps, null);
  }

  function RefreshButton(props) {
    var model = props.model;
    // The theme gives QPushButton 8px 20px of padding and a bold face.
    var buttonStyle = marginStyle(listField(model, BUTTON_PADDING_PX));
    buttonStyle.flex = FLEX_NONE;
    buttonStyle.fontWeight = text(model[BUTTON_FONT_WEIGHT]);
    var buttonProps = {
      type: BUTTON_TYPE,
      style: buttonStyle,
      title: label(model[REFRESH_TOOLTIP]),
      disabled: model[REFRESH_ENABLED] !== true,
      onClick: function () {
        act(REFRESH_PART, true);
      }
    };
    buttonProps[PART_ATTR] = REFRESH_PART;
    buttonProps[ARIA_LABEL] = label(model[REFRESH_LABEL]);
    return element(BUTTON_TAG, buttonProps, text(model[REFRESH_LABEL]));
  }

  function ActiveSwitch(props) {
    var model = props.model;
    var switchProps = {
      style: { display: FLEX, alignItems: CENTER, flex: FLEX_NONE },
      title: label(model[SHOW_ACTIVE_TOOLTIP])
    };
    switchProps[PART_ATTR] = SWITCH_PART;
    var boxProps = {
      type: CHECKBOX_TYPE,
      checked: model[SHOW_ACTIVE_CHECKED] === true,
      onChange: function (event) {
        act(SWITCH_BOX_PART, event.target.checked === true);
      }
    };
    boxProps[PART_ATTR] = SWITCH_BOX_PART;
    boxProps[ARIA_LABEL] = label(model[SHOW_ACTIVE_LABEL]);
    var wordProps = { style: asLabel({}, false) };
    wordProps[PART_ATTR] = SWITCH_TEXT_PART;
    return element(
      LABEL_TAG,
      switchProps,
      element(INPUT_TAG, boxProps),
      element(SPAN_TAG, wordProps, text(model[SHOW_ACTIVE_LABEL]))
    );
  }

  function StatusLine(props) {
    var model = props.model;
    var lineProps = { style: asLabel(styleOf(model[STATUS_STYLE]), false) };
    lineProps[PART_ATTR] = STATUS_PART;
    return element(SPAN_TAG, lineProps, text(model[STATUS_TEXT]));
  }

  function FilterRow(props) {
    var model = props.model;
    var style = boxStyle(
      listField(model, TOP_ROW_MARGINS_PX),
      model[TOP_ROW_SPACING_PX],
      ROW_WAY
    );
    style.flex = FLEX_NONE;
    style.alignItems = CENTER;
    var rowProps = { style: style };
    rowProps[PART_ATTR] = FILTER_ROW_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(RefreshButton, { key: REFRESH_PART, model: model }),
      element(ActiveSwitch, { key: SWITCH_PART, model: model }),
      element(Spacer, { key: FILTER_STRETCH_PART, part: FILTER_STRETCH_PART }),
      element(StatusLine, { key: STATUS_PART, model: model })
    );
  }

  function HeadCell(props) {
    var style = asCell({});
    if (props.mode === TO_CONTENTS_MODE) {
      style.width = MIN_CONTENT;
    }
    var cellProps = { style: style };
    cellProps[PART_ATTR] = HEAD_CELL_PART;
    cellProps[COLUMN_ATTR] = text(props.name);
    cellProps[AT_ATTR] = String(props.at);
    cellProps[TABLE_ATTR] = props.table;
    return element(TH_TAG, cellProps, text(props.name));
  }

  function BodyCell(props) {
    var style = asCell({});
    if (props.mode === TO_CONTENTS_MODE) {
      style.width = MIN_CONTENT;
    }
    style.color = colour(cellColour(props.cell));
    var cellProps = { style: style };
    cellProps[PART_ATTR] = GRID_CELL_PART;
    cellProps[COLUMN_ATTR] = text(props.column);
    cellProps[AT_ATTR] = String(props.at);
    cellProps[TABLE_ATTR] = props.table;
    cellProps[NAME_ATTR] = props.name;
    return element(TD_TAG, cellProps, text(cellText(props.cell)));
  }

  function BodyRow(props) {
    var model = props.model;
    var columns = props.columns;
    var name = rowName(props.row);
    var rowProps = {};
    rowProps[PART_ATTR] = GRID_ROW_PART;
    rowProps[AT_ATTR] = String(props.at);
    rowProps[NAME_ATTR] = name;
    rowProps[TABLE_ATTR] = props.table;
    rowProps[ALTERNATING_ATTR] = String(model[TABLE_ALTERNATING_ROWS] === true);
    return element(
      TR_TAG,
      rowProps,
      asList(props.row).map(function (cell, at) {
        return element(BodyCell, {
          key: String(at),
          cell: cell,
          column: columns[at],
          at: at,
          name: name,
          table: props.table,
          mode: model[TABLE_RESIZE_MODE]
        });
      })
    );
  }

  // Grid draws one Qt table: its header row, then one row per record.
  function Grid(props) {
    var model = props.model;
    var columns = listField(model, props.columnsField);
    var rows = listField(model, props.rowsField);
    var mode = model[TABLE_RESIZE_MODE];
    var gridProps = {
      style: {
        width: mode === TO_CONTENTS_MODE ? MAX_CONTENT : FULL,
        borderCollapse: COLLAPSE,
        tableLayout: AUTO
      }
    };
    gridProps[PART_ATTR] = GRID_PART;
    gridProps[TABLE_ATTR] = props.table;
    gridProps[ROWS_ATTR] = String(rows.length);
    var headProps = {};
    headProps[PART_ATTR] = GRID_HEAD_PART;
    var headRowProps = {};
    headRowProps[PART_ATTR] = HEAD_ROW_PART;
    var bodyProps = {};
    bodyProps[PART_ATTR] = GRID_BODY_PART;
    return element(
      TABLE_TAG,
      gridProps,
      element(
        HEAD_TAG,
        headProps,
        element(
          TR_TAG,
          headRowProps,
          columns.map(function (name, at) {
            return element(HeadCell, {
              key: String(at),
              name: name,
              at: at,
              table: props.table,
              mode: mode
            });
          })
        )
      ),
      element(
        BODY_TAG,
        bodyProps,
        rows.map(function (row, at) {
          return element(BodyRow, {
            key: String(at),
            model: model,
            row: row,
            at: at,
            columns: columns,
            table: props.table
          });
        })
      )
    );
  }

  // EmptyNote names the scan state under a table that drew no rows, so a
  // scan nobody asked for reads differently from one that found nothing.
  function EmptyNote(props) {
    var model = props.model;
    if (listField(model, props.rowsField).length) {
      return null;
    }
    var noteProps = { style: asLabel(styleOf(model[STATUS_STYLE]), true) };
    noteProps[PART_ATTR] = EMPTY_NOTE_PART;
    noteProps[TABLE_ATTR] = props.table;
    noteProps[STATE_ATTR] = text(model[SCAN_STATE]);
    return element(
      SPAN_TAG,
      noteProps,
      text(objectField(model, EMPTY_TEXTS)[props.noteField])
    );
  }

  // tableHeight answers what the Qt table draws: its own viewport height,
  // cut short by the group's maximum. An empty table keeps that height.
  function tableHeight(model, heightField) {
    var viewport = Number(model[TABLE_VIEWPORT_PX]);
    var most = Number(model[heightField]);
    if (!isFinite(viewport)) {
      return most;
    }
    return isFinite(most) && most < viewport ? most : viewport;
  }

  // TableGroup is the Qt group box holding one table under its title.
  function TableGroup(props) {
    var model = props.model;
    var style = groupFrame(model);
    style.flex = SHRINK_SHARE;
    style.minHeight = ZERO;
    var groupProps = { style: style };
    groupProps[PART_ATTR] = TABLE_GROUP_PART;
    groupProps[TABLE_ATTR] = props.table;
    groupProps[ARIA_LABEL] = label(model[props.titleField]);
    var legendProps = { style: asLabel(groupTitleStyle(model), false) };
    legendProps[PART_ATTR] = GROUP_LEGEND_PART;
    var bodyProps = {
      style: {
        height: length(tableHeight(model, props.heightField)),
        maxHeight: length(model[props.heightField]),
        overflow: AUTO,
        flex: SHRINK_SHARE,
        minWidth: ZERO,
        minHeight: ZERO
      },
      tabIndex: ZERO
    };
    bodyProps[PART_ATTR] = GROUP_BODY_PART;
    bodyProps[TABLE_ATTR] = props.table;
    return element(
      FIELDSET_TAG,
      groupProps,
      element(LEGEND_TAG, legendProps, text(model[props.titleField])),
      element(
        DIV_TAG,
        bodyProps,
        element(Grid, {
          model: model,
          table: props.table,
          columnsField: props.columnsField,
          rowsField: props.rowsField
        })
      ),
      element(EmptyNote, {
        key: EMPTY_NOTE_PART,
        model: model,
        table: props.table,
        rowsField: props.rowsField,
        noteField: props.noteField
      })
    );
  }

  // ModuleGroup is one left-side region: its Qt group box and its status line.
  // groupFrame is the themed QGroupBox: a 1 px frame and a title drawn in the
  // group own margin, so the title takes no row.
  function groupFrame(model, shares) {
    var style = boxStyle(
      listField(model, MODULE_MARGINS_PX),
      model[GROUP_SPACING_PX],
      COLUMN_WAY
    );
    style.flex = shares === true ? EQUAL_SHARE : FLEX_NONE;
    style.minWidth = ZERO;
    if (shares === true) {
      style.minHeight = ZERO;
      style.overflow = AUTO;
    }
    style.position = RELATIVE;
    style.borderWidth = length(model[MODULE_FRAME_PX]);
    style.borderStyle = SOLID;
    return style;
  }

  function groupTitleStyle(model) {
    var frame = Number(model[MODULE_FRAME_PX]);
    var titleStyle = marginStyle(listField(model, MODULE_TITLE_PADDING_PX));
    titleStyle.position = ABSOLUTE;
    titleStyle.left = length(isFinite(frame) ? -frame : NO_OFFSET);
    titleStyle.top = length(isFinite(frame) ? -frame : NO_OFFSET);
    return titleStyle;
  }

  // The published zone view one key names, or an empty one.
  function zoneFor(model, key) {
    var found = {};
    listField(model, ZONES).forEach(function (one) {
      if (isPlainObject(one) && one[ZONE_KEY] === key) {
        found = one;
      }
    });
    return found;
  }

  // StepButton is one arrow. `by` is -1 back and +1 next.
  function StepButton(props) {
    var skin = props.skin;
    var style = styleOf(skin[BUTTON_STYLE]);
    style.font = INHERITED;
    style.flex = FLEX_NONE;
    style.width = length(skin[BUTTON_WIDTH_PX]);
    var buttonProps = {
      type: BUTTON_TYPE,
      style: style,
      disabled: props.total < TWO,
      title: label(skin[props.by < ZERO ? BACK_TOOLTIP : NEXT_TOOLTIP])
    };
    buttonProps[PART_ATTR] = props.by < ZERO ? STEP_BACK_PART : STEP_NEXT_PART;
    buttonProps[NAME_ATTR] = text(props.zone);
    buttonProps[ARIA_LABEL] = label(
      skin[props.by < ZERO ? BACK_TOOLTIP : NEXT_TOOLTIP]
    );
    buttonProps.onClick = function () {
      props.act(props.by < ZERO ? STEP_BACK_PART : STEP_NEXT_PART, props.zone);
    };
    return element(
      BUTTON_TAG,
      buttonProps,
      text(skin[props.by < ZERO ? BACK_TEXT : NEXT_TEXT])
    );
  }

  // DetailLine is one line of the expansion.
  function DetailLine(props) {
    var lineProps = { style: asLabel(styleOf(props.skin[DETAIL_STYLE]), true) };
    lineProps[PART_ATTR] = DETAIL_PART;
    lineProps[NAME_ATTR] = text(asList(props.row)[ZERO]);
    return element(DIV_TAG, lineProps, text(asList(props.row)[ONE]));
  }

  // ZoneStepper draws one zone's entry: the arrows, the position, the entry
  // itself and, while it is open, the lines saying how and why it is there.
  // Every zone on this screen and the proposals pane draw through it.
  function ZoneStepper(props) {
    var skin = props.skin;
    var view = isPlainObject(props.view) ? props.view : {};
    var total = Number(view[ZONE_TOTAL]) || ZERO;
    var press = typeof props.act === FUNCTION_KIND ? props.act : function () {};
    var outer = { display: FLEX, flexDirection: COLUMN_WAY, flex: ONE, minHeight: ZERO };
    outer.gap = length(skin[ENTRY_SPACING_PX]);
    var outerProps = { style: outer };
    outerProps[PART_ATTR] = STEPPER_PART;
    outerProps[NAME_ATTR] = text(view[ZONE_KEY]);
    outerProps[ARIA_LABEL] = label(skin[STEPPER_NAME]);
    var rowStyle = { display: FLEX, flexDirection: ROW_WAY, flex: FLEX_NONE };
    rowStyle.gap = length(skin[ENTRY_SPACING_PX]);
    var rowProps = { style: rowStyle };
    rowProps[PART_ATTR] = STEP_ROW_PART;
    var positionProps = { style: asLabel(styleOf(skin[POSITION_STYLE]), false) };
    positionProps[PART_ATTR] = POSITION_PART;
    positionProps[NAME_ATTR] = text(view[ZONE_KEY]);
    var frame = styleOf(skin[ENTRY_STYLE]);
    frame.flex = ONE;
    frame.minHeight = ZERO;
    frame.overflow = AUTO;
    frame.cursor = POINTER;
    var entryProps = { style: frame };
    entryProps[PART_ATTR] = ENTRY_PART;
    entryProps[NAME_ATTR] = text(view[ZONE_KEY]);
    entryProps[ARIA_LABEL] = label(skin[ENTRY_NAME]);
    entryProps.onClick = function () {
      press(ENTRY_PART, view[ZONE_KEY]);
    };
    var bodyProps = {
      style: boxStyle(
        asList(skin[ENTRY_MARGINS_PX]),
        skin[ENTRY_SPACING_PX],
        COLUMN_WAY
      )
    };
    bodyProps[PART_ATTR] = ENTRY_BODY_PART;
    var headStyle = { display: FLEX, flexDirection: ROW_WAY };
    headStyle.gap = length(skin[ENTRY_SPACING_PX]);
    var headProps = { style: headStyle };
    headProps[PART_ATTR] = ENTRY_HEAD_PART;
    var headlineStyle = asLabel(styleOf(skin[HEADLINE_STYLE]), true);
    headlineStyle.flex = ONE;
    headlineStyle.minWidth = ZERO;
    var headlineProps = { style: headlineStyle };
    headlineProps[PART_ATTR] = HEADLINE_PART;
    headlineProps[NAME_ATTR] = text(view[ZONE_KEY]);
    var badgeStyle = styleOf(view[ZONE_BADGE_STYLE]);
    badgeStyle.whiteSpace = PRE_SPACE;
    var badgeProps = { style: badgeStyle };
    badgeProps[PART_ATTR] = ENTRY_BADGE_PART;
    var metaProps = { style: asLabel(styleOf(skin[META_STYLE]), true) };
    metaProps[PART_ATTR] = ENTRY_META_PART;
    var methodProps = { style: asLabel(styleOf(skin[METHOD_STYLE]), true) };
    methodProps[PART_ATTR] = ENTRY_METHOD_PART;
    var hintProps = { style: asLabel(styleOf(skin[HINT_STYLE]), true) };
    hintProps[PART_ATTR] = ENTRY_HINT_PART;
    return element(
      DIV_TAG,
      outerProps,
      element(
        DIV_TAG,
        rowProps,
        element(StepButton, {
          key: STEP_BACK_PART,
          skin: skin,
          by: -ONE,
          total: total,
          zone: view[ZONE_KEY],
          act: press
        }),
        element(StepButton, {
          key: STEP_NEXT_PART,
          skin: skin,
          by: ONE,
          total: total,
          zone: view[ZONE_KEY],
          act: press
        }),
        element(DIV_TAG, positionProps, text(view[ZONE_POSITION]))
      ),
      element(
        DIV_TAG,
        entryProps,
        element(
          DIV_TAG,
          bodyProps,
          element(
            DIV_TAG,
            headProps,
            element(DIV_TAG, headlineProps, text(view[ZONE_HEADLINE])),
            text(view[ZONE_BADGE])
              ? element(SPAN_TAG, badgeProps, text(view[ZONE_BADGE]))
              : null
          ),
          text(view[ZONE_META])
            ? element(DIV_TAG, metaProps, text(view[ZONE_META]))
            : null,
          text(view[ZONE_METHOD])
            ? element(DIV_TAG, methodProps, text(view[ZONE_METHOD]))
            : null,
          listField(view, ZONE_DETAIL).map(function (row, at) {
            return element(DetailLine, {
              key: DETAIL_PART + PATH_SPLIT + String(at),
              skin: skin,
              row: row
            });
          }),
          total > ZERO
            ? element(DIV_TAG, hintProps, text(skin[HINT_TEXT]))
            : null
        )
      )
    );
  }

  function ModuleGroup(props) {
    var model = props.model;
    var entry = asList(props.entry);
    var groupProps = { style: groupFrame(model, props.shares === true) };
    groupProps[PART_ATTR] = MODULE_GROUP_PART;
    groupProps[NAME_ATTR] = text(entry[ZERO]);
    groupProps[ARIA_LABEL] = label(entry[ONE]);
    var legendProps = { style: asLabel(groupTitleStyle(model), false) };
    legendProps[PART_ATTR] = MODULE_LEGEND_PART;
    return element(
      FIELDSET_TAG,
      groupProps,
      element(LEGEND_TAG, legendProps, text(entry[ONE])),
      asList(props.children),
      element(ZoneStepper, {
        key: STEPPER_PART,
        skin: objectField(model, STEPPER),
        view: zoneFor(model, entry[ZERO]),
        act: act
      })
    );
  }

  // The three left-side zones, in the order the surface publishes them. The
  // Opposing Trades zone carries the scan controls and the two tables.
  function moduleGroups(model) {
    return listField(model, LEFT_MODULES).map(function (entry, at) {
      return element(ModuleGroup, {
        key: MODULE_GROUP_PART + PATH_SPLIT + String(at),
        model: model,
        entry: entry,
        shares: true,
        children:
          entry[ZERO] === listField(model, LEFT_MODULE_KEYS)[ONE]
            ? scanContent(model)
            : []
      });
    });
  }

  // The Refresh row the Opposing Trades zone holds above its stepper.
  function scanContent(model) {
    return [element(FilterRow, { key: FILTER_ROW_PART, model: model })];
  }

  function LeftPane(props) {
    var model = props.model;
    var sizes = listField(model, SPLITTER_SIZES_PX);
    var style = boxStyle(
      listField(model, LEFT_MARGINS_PX),
      model[LEFT_SPACING_PX],
      COLUMN_WAY
    );
    style.flexGrow = listField(model, SPLITTER_STRETCH)[ZERO];
    style.flexBasis = length(sizes[ZERO]);
    style.overflow = AUTO;
    var paneProps = { style: style };
    paneProps[PART_ATTR] = LEFT_PANE_PART;
    return element(
      DIV_TAG,
      paneProps,
      moduleGroups(model)
    );
  }

  // The right pane: the Ready to Send zone above the Bot Swarm Topologies
  // zone, which is the slot the proposals unit fills.
  function TopologySlot(props) {
    var model = props.model;
    var paneStyle = boxStyle(
      listField(model, LEFT_MARGINS_PX),
      model[LEFT_SPACING_PX],
      COLUMN_WAY
    );
    paneStyle.flexGrow = listField(model, SPLITTER_STRETCH)[ONE];
    paneStyle.flexBasis = length(listField(model, SPLITTER_SIZES_PX)[ONE]);
    paneStyle.overflow = CLIPPED;
    var paneProps = { style: paneStyle };
    paneProps[PART_ATTR] = RIGHT_PANE_PART;
    return element(
      DIV_TAG,
      paneProps,
      listField(model, RIGHT_ZONES).map(function (entry) {
        return element(RightZone, {
          key: MODULE_GROUP_PART + PATH_SPLIT + text(entry[ZERO]),
          model: model,
          entry: entry,
          fills: text(entry[TWO]) === EMPTY
        });
      })
    );
  }

  // RightZone is one themed group on the right side. The last one carries the
  // slot the proposals unit is moved into.
  function RightZone(props) {
    var model = props.model;
    var entry = asList(props.entry);
    var groupProps = { style: groupFrame(model, true) };
    groupProps[PART_ATTR] = MODULE_GROUP_PART;
    groupProps[NAME_ATTR] = text(entry[ZERO]);
    groupProps[ARIA_LABEL] = label(entry[ONE]);
    var legendProps = { style: asLabel(groupTitleStyle(model), false) };
    legendProps[PART_ATTR] = MODULE_LEGEND_PART;
    if (props.fills === true) {
      var slotProps = {
        style: {
          flex: AUTO,
          minHeight: ZERO,
          overflow: CLIPPED,
          display: FLEX,
          flexDirection: COLUMN_WAY
        }
      };
      slotProps[PART_ATTR] = TOPOLOGY_PART;
      slotProps[SLOT_ATTR] = TOPOLOGY_SLOT;
      return element(
        FIELDSET_TAG,
        groupProps,
        element(LEGEND_TAG, legendProps, text(entry[ONE])),
        element(DIV_TAG, slotProps, null)
      );
    }
    return element(
      FIELDSET_TAG,
      groupProps,
      element(LEGEND_TAG, legendProps, text(entry[ONE])),
      element(ZoneStepper, {
        key: STEPPER_PART,
        skin: objectField(model, STEPPER),
        view: zoneFor(model, entry[ZERO]),
        act: act
      })
    );
  }

  function Split(props) {
    var model = props.model;
    var across = model[SPLITTER_ORIENTATION] === ACROSS_ORIENTATION;
    var splitProps = {
      style: {
        display: FLEX,
        flexDirection: across ? ROW_WAY : COLUMN_WAY,
        gap: length(model[SPLITTER_HANDLE_PX]),
        flex: AUTO,
        overflow: CLIPPED
      }
    };
    splitProps[PART_ATTR] = SPLIT_PART;
    splitProps[ENTRIES_ATTR] = text(model[SPLITTER_PANES]);
    return element(
      DIV_TAG,
      splitProps,
      element(LeftPane, { key: LEFT_PANE_PART, model: model }),
      element(TopologySlot, { key: TOPOLOGY_PART, model: model })
    );
  }

  // The pieces the surface published for one label's text, if any.
  function marksFor(model, carried) {
    var found;
    listField(objectField(model, PER_BOT_VIEW), MARKS).forEach(function (one) {
      if (!Array.isArray(one) || one[ZERO] !== carried || found !== undefined) {
        return;
      }
      var pieces = one.slice();
      pieces.shift();
      found = {
        lead: pieces.shift(),
        strong: pieces.shift(),
        breaks: pieces.shift(),
        tail: pieces.shift()
      };
    });
    return found;
  }

  // rebuilt names the marked-up text one set of pieces builds.
  function rebuilt(model, marks) {
    var tags = objectField(model, MARKS);
    return (
      String(marks.lead) +
      String(tags[STRONG_OPEN]) +
      String(marks.strong) +
      String(tags[STRONG_CLOSE]) +
      repeated(tags[BREAK_TAG], marks.breaks) +
      String(marks.tail)
    );
  }

  // markedNodes draws one marked label's pieces, its tags left as elements.
  function markedNodes(marks, weight) {
    var leadProps = { key: MARK_LEAD_PART };
    leadProps[PART_ATTR] = MARK_LEAD_PART;
    var strongProps = { key: MARK_STRONG_PART, style: { fontWeight: text(weight) } };
    strongProps[PART_ATTR] = MARK_STRONG_PART;
    var tailProps = { key: MARK_TAIL_PART };
    tailProps[PART_ATTR] = MARK_TAIL_PART;
    return [
      element(SPAN_TAG, leadProps, text(marks.lead)),
      element(STRONG_TAG, strongProps, text(marks.strong)),
      element(
        SPAN_TAG,
        tailProps,
        repeated(NEWLINE, marks.breaks) + String(marks.tail)
      )
    ];
  }

  function PerBotLabel(props) {
    var model = props.model;
    var entry = props.entry;
    var carried = entry[ONE];
    var labelProps = {
      style: asLabel(styleOf(entry[TWO]), entry[THREE] === true)
    };
    labelProps[PART_ATTR] = PER_BOT_LABEL_PART;
    labelProps[AT_ATTR] = String(props.at);
    var marks = marksFor(model, carried);
    if (marks === undefined) {
      return element(DIV_TAG, labelProps, text(carried));
    }
    return element(
      DIV_TAG,
      labelProps,
      markedNodes(marks, objectField(model, MARKS)[STRONG_WEIGHT])
    );
  }

  function PerBotCard(props) {
    var model = props.model;
    var entry = props.entry;
    var style = boxStyle(
      listField(model, GROUP_MARGINS_PX),
      model[GROUP_SPACING_PX],
      COLUMN_WAY
    );
    style.flex = FLEX_NONE;
    var cardProps = { style: style };
    cardProps[PART_ATTR] = PER_BOT_CARD_PART;
    cardProps[AT_ATTR] = String(props.at);
    cardProps[ARIA_LABEL] = label(entry[ONE]);
    var legendProps = { style: asLabel({}, false) };
    legendProps[PART_ATTR] = CARD_LEGEND_PART;
    var bodyProps = {
      style: boxStyle([], model[GROUP_SPACING_PX], COLUMN_WAY)
    };
    bodyProps[PART_ATTR] = CARD_BODY_PART;
    return element(
      FIELDSET_TAG,
      cardProps,
      element(LEGEND_TAG, legendProps, text(entry[ONE])),
      element(
        DIV_TAG,
        bodyProps,
        asList(entry[TWO]).map(function (child, at) {
          return perBotChild(model, child, at);
        })
      )
    );
  }

  function perBotChild(model, entry, at) {
    var names = objectField(model, ELEMENTS);
    if (!Array.isArray(entry)) {
      return null;
    }
    if (entry[ZERO] === names[LABEL_ELEMENT]) {
      return element(PerBotLabel, {
        key: String(at),
        model: model,
        entry: entry,
        at: at
      });
    }
    if (entry[ZERO] === names[GROUP_ELEMENT]) {
      return element(PerBotCard, {
        key: String(at),
        model: model,
        entry: entry,
        at: at
      });
    }
    if (entry[ZERO] === names[STRETCH_ELEMENT]) {
      return element(Spacer, { key: String(at), part: PER_BOT_STRETCH_PART });
    }
    return null;
  }

  // PerBotView is what the Market Inspector tab mounts in its view slot.
  function PerBotView(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var view = objectField(model, PER_BOT_VIEW);
    var style = boxStyle(listField(view, MARGINS_PX), view[SPACING_PX], COLUMN_WAY);
    style.flex = AUTO;
    var viewProps = { style: style };
    viewProps[PART_ATTR] = PER_BOT_PART;
    viewProps[NAME_ATTR] = text(view[ASSET]);
    viewProps[ENTRIES_ATTR] = String(listField(view, ORDER).length);
    return element(
      DIV_TAG,
      viewProps,
      listField(view, ORDER).map(function (entry, at) {
        return perBotChild(model, entry, at);
      })
    );
  }

  // Screen draws the fleet-wide tab: filter row, both tables, right pane.
  function Screen(props) {
    if (!isPlainObject(props.model)) {
      return null;
    }
    var model = props.model;
    var style = boxStyle(
      listField(model, OUTER_MARGINS_PX),
      model[OUTER_SPACING_PX],
      COLUMN_WAY
    );
    merged(style, styleOf(model[STYLE_SHEET]));
    style.height = FULL;
    var screenProps = { style: style };
    screenProps[PART_ATTR] = SCREEN_PART;
    screenProps[ARIA_LABEL] = label(model[ACCESSIBLE_NAME]);
    return element(DIV_TAG, screenProps, element(Split, { model: model }));
  }

  function checkFields(model) {
    DECLARED_FIELDS.forEach(function (field) {
      if (!owns(model, field)) {
        note(null, field, MISSING_FAULT, null);
        return;
      }
      if (model[field] === null && field !== NO_CELL) {
        note(null, field, NULL_FAULT, null);
      }
    });
  }

  function checkBags(model) {
    Object.keys(BAG_FIELDS).forEach(function (where) {
      var bag = objectField(model, where);
      BAG_FIELDS[where].forEach(function (field) {
        if (!owns(bag, field)) {
          note(where, field, MISSING_FAULT, null);
          return;
        }
        if (bag[field] === null) {
          note(where, field, NULL_FAULT, null);
        }
      });
    });
  }

  // checkShapes refuses a scalar standing where a list or a bag is walked.
  function checkShapes(model) {
    WANTED_LISTS.forEach(function (field) {
      if (owns(model, field) && !Array.isArray(model[field])) {
        note(null, field, NOT_A_LIST_FAULT, kindOf(model[field]));
      }
    });
    WANTED_BAGS.forEach(function (field) {
      if (owns(model, field) && !isPlainObject(model[field])) {
        note(null, field, NOT_AN_OBJECT_FAULT, kindOf(model[field]));
      }
    });
    var view = objectField(model, PER_BOT_VIEW);
    [MARGINS_PX, MARKS, ORDER].forEach(function (field) {
      if (owns(view, field) && !Array.isArray(view[field])) {
        note(PER_BOT_VIEW, field, NOT_A_LIST_FAULT, kindOf(view[field]));
      }
    });
    var frames = objectField(model, TIMEFRAME);
    if (owns(frames, KEYS) && !Array.isArray(frames[KEYS])) {
      note(TIMEFRAME, KEYS, NOT_A_LIST_FAULT, kindOf(frames[KEYS]));
    }
  }

  // A wrong type is named only where the surface publishes a default of
  // the same meaning to hold it against.
  function checkTypeAgainst(where, field, carried, against) {
    if (against === null || against === undefined || carried === undefined) {
      return;
    }
    if (kindOf(carried) !== kindOf(against)) {
      note(where, field, WRONG_TYPE_FAULT, kindOf(carried));
    }
  }

  var WORD_FIELDS = [
    ACCESSIBLE_NAME,
    PAIRS_GROUP_TITLE,
    REFRESH_LABEL,
    SHOW_ACTIVE_LABEL,
    SIGNALS_GROUP_TITLE,
    SPLITTER_ORIENTATION,
    STATUS_STYLE,
    STATUS_TEXT,
    STYLE_SHEET,
    TABLE_EDIT_TRIGGERS,
    TABLE_RESIZE_MODE
  ];

  var FLAG_FIELDS = [
    EXCHANGE_SOURCE_WIRED,
    PENDING_REFRESH,
    REFRESH_ENABLED,
    SHOW_ACTIVE,
    SHOW_ACTIVE_CHECKED,
    TABLE_ALTERNATING_ROWS
  ];

  var COUNT_FIELDS = [
    GROUP_SPACING_PX,
    LEFT_SPACING_PX,
    OUTER_SPACING_PX,
    PAIRS_MAX_HEIGHT_PX,
    PER_BOT_SPACING_PX,
    SIGNALS_MAX_HEIGHT_PX,
    SPLITTER_PANES,
    TOP_ROW_SPACING_PX
  ];

  function checkTypes(model) {
    var words = model[STATUS_INITIAL_TEXT];
    var flag = model[SHOW_ACTIVE_DEFAULT];
    var count = objectField(model, PER_BOT)[HIGHER_LIMIT];
    WORD_FIELDS.forEach(function (field) {
      checkTypeAgainst(null, field, model[field], words);
    });
    FLAG_FIELDS.forEach(function (field) {
      checkTypeAgainst(null, field, model[field], flag);
    });
    COUNT_FIELDS.forEach(function (field) {
      checkTypeAgainst(null, field, model[field], count);
    });
  }

  function checkMarkup(where, field, carried) {
    if (typeof carried === STRING_KIND && carries(carried, MARKUP_OPEN)) {
      note(where, field, MARKUP_FAULT, MARKUP_OPEN);
    }
  }

  function checkColour(where, field, value) {
    if (typeof value === STRING_KIND && qtColour(value) !== undefined) {
      note(where, field, QT_COLOUR_FAULT, value);
    }
  }

  function checkTable(model, columnsField, rowsField) {
    var columns = listField(model, columnsField);
    var placeholder = objectField(model, CELLS)[ACTIVE_NO];
    var paint = objectField(model, COLORS)[NONE_COLOUR];
    var seen = [];
    listField(model, rowsField).forEach(function (row, at) {
      var spot = rowsField + PATH_SPLIT + String(at);
      if (!Array.isArray(row)) {
        note(spot, rowsField, NOT_A_LIST_FAULT, kindOf(row));
        return;
      }
      if (row.length !== columns.length) {
        note(spot, rowsField, COLUMN_COUNT_FAULT, row.length);
      }
      var name = rowName(row);
      if (name !== undefined && seen.indexOf(name) >= ZERO) {
        note(spot, rowsField, DUPLICATE_NAME_FAULT, name);
      }
      seen.push(name);
      row.forEach(function (cell, column) {
        var here = spot + PATH_SPLIT + String(column);
        if (!Array.isArray(cell) || cell.length !== TWO) {
          note(here, rowsField, CELL_SHAPE_FAULT, kindOf(cell));
          return;
        }
        checkTypeAgainst(here, rowsField, cellText(cell), placeholder);
        checkTypeAgainst(here, rowsField, cellColour(cell), paint);
        checkColour(here, rowsField, cellColour(cell));
        checkMarkup(here, rowsField, cellText(cell));
      });
    });
  }

  // Each left-side region carries a key, a title and a status line.
  function checkModules(model) {
    var words = model[STATUS_INITIAL_TEXT];
    var keys = listField(model, LEFT_MODULE_KEYS);
    var entries = listField(model, LEFT_MODULES);
    if (entries.length !== keys.length) {
      note(null, LEFT_MODULES, COLUMN_COUNT_FAULT, entries.length);
    }
    entries.forEach(function (entry, at) {
      var spot = LEFT_MODULES + PATH_SPLIT + String(at);
      if (!Array.isArray(entry) || entry.length !== THREE) {
        note(spot, LEFT_MODULES, NOT_A_LIST_FAULT, kindOf(entry));
        return;
      }
      if (at < keys.length && entry[ZERO] !== keys[at]) {
        note(spot, LEFT_MODULES, DUPLICATE_NAME_FAULT, entry[ZERO]);
      }
      entry.forEach(function (one, column) {
        var here = spot + PATH_SPLIT + String(column);
        checkTypeAgainst(here, LEFT_MODULES, one, words);
        checkMarkup(here, LEFT_MODULES, one);
      });
    });
  }

  // paints answers whether one declaration survives into a CSS style.
  function paints(one) {
    var alone = String(one.property) + COLON + GAP + String(one.value);
    return Boolean(Object.keys(styleOf(alone)).length);
  }

  function checkSheet(where, field, sheet) {
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) !== undefined) {
        note(where, field, QT_COLOUR_FAULT, one.property);
        return;
      }
      if (!paints(one)) {
        note(where, field, NOT_CSS_FAULT, one.property);
      }
    });
    stateRules(sheet).forEach(function (block) {
      declarations(block.body).forEach(function (one) {
        if (qtColour(one.value) !== undefined) {
          note(where, field, QT_COLOUR_FAULT, one.property);
        }
      });
    });
  }

  function checkSheets(model) {
    if (sheetApi() === undefined) {
      note(null, STYLE_SHEET, NO_SHEET_SOURCE_FAULT, null);
      return;
    }
    checkSheet(null, STYLE_SHEET, model[STYLE_SHEET]);
    checkSheet(null, STATUS_STYLE, model[STATUS_STYLE]);
    checkSheet(PER_BOT, NO_SCAN_STYLE, objectField(model, PER_BOT)[NO_SCAN_STYLE]);
    listField(objectField(model, PER_BOT_VIEW), ORDER).forEach(function (entry, at) {
      checkOrderSheet(model, entry, PER_BOT_VIEW + PATH_SPLIT + String(at));
    });
  }

  function checkOrderSheet(model, entry, spot) {
    var names = objectField(model, ELEMENTS);
    if (!Array.isArray(entry)) {
      return;
    }
    if (entry[ZERO] === names[LABEL_ELEMENT]) {
      checkSheet(spot, ORDER, entry[TWO]);
      return;
    }
    if (entry[ZERO] === names[GROUP_ELEMENT]) {
      asList(entry[TWO]).forEach(function (child, at) {
        checkOrderSheet(model, child, spot + PATH_SPLIT + String(at));
      });
    }
  }

  function checkColours(model) {
    var painted = objectField(model, COLORS);
    Object.keys(painted).forEach(function (name) {
      checkColour(COLORS, name, painted[name]);
    });
  }

  // checkOrder walks the per-bot entries, naming an element it cannot draw.
  function checkOrder(model) {
    var view = objectField(model, PER_BOT_VIEW);
    walkOrder(model, listField(view, ORDER), PER_BOT_VIEW);
  }

  function walkOrder(model, entries, where) {
    var names = objectField(model, ELEMENTS);
    entries.forEach(function (entry, at) {
      var spot = where + PATH_SPLIT + String(at);
      if (!Array.isArray(entry)) {
        note(spot, ORDER, NOT_A_LIST_FAULT, kindOf(entry));
        return;
      }
      if (entry[ZERO] === names[LABEL_ELEMENT]) {
        checkLabelEntry(model, entry, spot);
        return;
      }
      if (entry[ZERO] === names[GROUP_ELEMENT]) {
        checkMarkup(spot, ORDER, entry[ONE]);
        walkOrder(model, asList(entry[TWO]), spot);
        return;
      }
      if (entry[ZERO] !== names[STRETCH_ELEMENT]) {
        note(spot, ORDER, UNKNOWN_ELEMENT_FAULT, text(entry[ZERO]));
      }
    });
  }

  // A marked label is held against the pieces the surface published for it.
  function checkLabelEntry(model, entry, spot) {
    var carried = entry[ONE];
    var marks = marksFor(model, carried);
    if (marks === undefined) {
      checkMarkup(spot, ORDER, carried);
      return;
    }
    if (rebuilt(model, marks) !== carried) {
      note(spot, MARKS, MARK_MISMATCH_FAULT, rebuilt(model, marks));
    }
  }

  function heldFieldCount(model) {
    return DECLARED_FIELDS.filter(function (field) {
      return owns(model, field);
    }).length;
  }

  // Every nested field as one `bag.field` pair, so the two counts pair up.
  function nestedPaths() {
    var found = [];
    Object.keys(BAG_FIELDS).forEach(function (where) {
      BAG_FIELDS[where].forEach(function (name) {
        found.push({ where: where, field: name });
      });
    });
    return found;
  }

  function heldNestedPaths(model) {
    return nestedPaths().filter(function (one) {
      return owns(objectField(model, one.where), one.field);
    });
  }

  function declaredCells(model, columnsField, rowsField) {
    return listField(model, columnsField).length * listField(model, rowsField).length;
  }

  function heldCells(model, rowsField) {
    var count = ZERO;
    listField(model, rowsField).forEach(function (row) {
      count += asList(row).length;
    });
    return count;
  }

  // drawnEntries counts the per-bot entries this module draws, at any depth.
  function drawnEntries(model, entries) {
    var names = objectField(model, ELEMENTS);
    var count = ZERO;
    entries.forEach(function (entry) {
      if (!Array.isArray(entry)) {
        return;
      }
      if (entry[ZERO] === names[GROUP_ELEMENT]) {
        count += ONE + drawnEntries(model, asList(entry[TWO]));
        return;
      }
      if (
        entry[ZERO] === names[LABEL_ELEMENT] ||
        entry[ZERO] === names[STRETCH_ELEMENT]
      ) {
        count += ONE;
      }
    });
    return count;
  }

  // allEntries counts every per-bot entry the surface published, at any depth.
  function allEntries(entries) {
    var count = ZERO;
    entries.forEach(function (entry) {
      count += ONE;
      if (Array.isArray(entry) && Array.isArray(entry[TWO])) {
        count += allEntries(entry[TWO]);
      }
    });
    return count;
  }

  function report() {
    var model = held.model;
    var order = listField(objectField(model, PER_BOT_VIEW), ORDER);
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        nested: nestedPaths().length,
        signalCells: declaredCells(model, SIGNAL_COLUMNS, SIGNAL_ROWS),
        pairCells: declaredCells(model, PAIR_COLUMNS, PAIR_ROWS),
        perBot: allEntries(order)
      },
      held: {
        fields: heldFieldCount(model),
        nested: heldNestedPaths(model).length,
        signalCells: heldCells(model, SIGNAL_ROWS),
        pairCells: heldCells(model, PAIR_ROWS),
        perBot: drawnEntries(model, order)
      },
      faults: screenFaults.slice()
    };
  }

  function setScreen(model) {
    if (!isPlainObject(model)) {
      held = null;
      screenFaults = [fault(null, null, NOT_AN_OBJECT_FAULT, kindOf(model))];
      return { declared: null, held: null, faults: screenFaults.slice() };
    }
    held = { model: model };
    screenFaults = [];
    checkFields(model);
    checkBags(model);
    checkShapes(model);
    checkTypes(model);
    checkTable(model, SIGNAL_COLUMNS, SIGNAL_ROWS);
    checkTable(model, PAIR_COLUMNS, PAIR_ROWS);
    checkModules(model);
    checkOrder(model);
    checkSheets(model);
    checkColours(model);
    return report();
  }

  // loadScreen asks METHOD once, clearing asked so a refusal retries.
  function loadScreen(params) {
    if (asked !== null) {
      return asked;
    }
    if (!global.acervator || typeof global.acervator.call !== "function") {
      loadFault = NO_BRIDGE;
      return Promise.resolve(null);
    }
    asked = global.acervator
      .call(METHOD, isPlainObject(params) ? params : {})
      .then(function (model) {
        loadFault = null;
        setScreen(model);
        return model;
      })
      .catch(function (err) {
        loadFault = err.message;
        asked = null;
        return null;
      });
    return asked;
  }

  function payload() {
    return held === null ? {} : copyOf(held.model);
  }

  function declaredFields() {
    return DECLARED_FIELDS.slice();
  }

  function declaredNames() {
    var found = DECLARED_FIELDS.slice();
    Object.keys(BAG_FIELDS).forEach(function (where) {
      found = found.concat(BAG_FIELDS[where]);
    });
    return found;
  }

  function nestedNames(where) {
    return owns(BAG_FIELDS, where) ? BAG_FIELDS[where].slice() : [];
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

  function perBot() {
    return bag(PER_BOT_VIEW);
  }

  function perBotOrder() {
    return held === null ? [] : listField(objectField(held.model, PER_BOT_VIEW), ORDER);
  }

  // The name each row of one table carries, in the order it is drawn.
  function namesOf(rowsField) {
    return held === null
      ? []
      : listField(held.model, rowsField).map(function (row) {
          return rowName(row);
        });
  }

  // The key each left-side region carries, in the order it is drawn.
  function moduleOrder() {
    return list(LEFT_MODULES).map(function (entry) {
      return text(asList(entry)[ZERO]);
    });
  }

  function signalOrder() {
    return namesOf(SIGNAL_ROWS);
  }

  function pairOrder() {
    return namesOf(PAIR_ROWS);
  }

  // One row read by the name its first cell carries, column by column.
  function rowByName(columnsField, rowsField, wanted) {
    var found;
    if (held === null) {
      return found;
    }
    var columns = listField(held.model, columnsField);
    listField(held.model, rowsField).forEach(function (row) {
      if (rowName(row) !== wanted || found !== undefined) {
        return;
      }
      found = {};
      columns.forEach(function (name, at) {
        Object.defineProperty(found, String(name), {
          value: asList(row)[at],
          enumerable: true,
          writable: true,
          configurable: true
        });
      });
    });
    return found;
  }

  function signalRow(name) {
    return rowByName(SIGNAL_COLUMNS, SIGNAL_ROWS, name);
  }

  function pairRow(name) {
    return rowByName(PAIR_COLUMNS, PAIR_ROWS, name);
  }

  // Every group and label pair this screen draws, group named first.
  function labelPairs() {
    var found = [];
    if (held === null) {
      return found;
    }
    var model = held.model;
    listField(model, SIGNAL_COLUMNS).forEach(function (name) {
      found.push([model[SIGNALS_GROUP_TITLE], name]);
    });
    listField(model, PAIR_COLUMNS).forEach(function (name) {
      found.push([model[PAIRS_GROUP_TITLE], name]);
    });
    return found;
  }

  // Each label carried by more than one group, which a label alone hides.
  function labelCollisions() {
    var groups = {};
    labelPairs().forEach(function (pair) {
      var name = String(pair[ONE]);
      if (!owns(groups, name)) {
        groups[name] = [];
      }
      if (groups[name].indexOf(String(pair[ZERO])) < ZERO) {
        groups[name].push(String(pair[ZERO]));
      }
    });
    return Object.keys(groups).filter(function (name) {
      return groups[name].length > ONE;
    });
  }

  function actions() {
    return bag(ACTIONS);
  }

  function timers() {
    return bag(TIMERS);
  }

  function timerDelays() {
    return list(TIMER_DELAYS_MS);
  }

  function busTopics() {
    return list(BUS_TOPICS);
  }

  function callNames() {
    return list(CALL_NAMES);
  }

  function calls() {
    return list(CALLS);
  }

  function method() {
    return field(METHOD_FIELD);
  }

  function slots() {
    return [TOPOLOGY_SLOT];
  }

  // kinds reports the JavaScript type of every payload value by dotted path.
  function kinds() {
    var found = {};
    function descend(path, value) {
      if (isPlainObject(value)) {
        walk(path, value);
        return;
      }
      if (Array.isArray(value)) {
        value.forEach(function (one, at) {
          var inner = path + PATH_SPLIT + String(at);
          found[inner] = kindOf(one);
          descend(inner, one);
        });
      }
    }
    function walk(prefix, node) {
      Object.keys(node).forEach(function (name) {
        var path = prefix ? prefix + PATH_SPLIT + name : name;
        found[path] = kindOf(node[name]);
        descend(path, node[name]);
      });
    }
    if (held !== null) {
      walk(EMPTY, held.model);
    }
    return found;
  }

  function faults() {
    return screenFaults.slice();
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

  // draw runs flushSync so the document is current when it answers.
  function draw(target, node) {
    var root = rootFor(target);
    global.ReactDOM.flushSync(function () {
      root.render(node);
    });
    return target;
  }

  function payloadOr(model) {
    if (isPlainObject(model)) {
      return model;
    }
    return held === null ? null : held.model;
  }

  // fillSlot draws the proposals pane into the right-hand slot when no host
  // has claimed it. A Qt host moves its own pane node in and declares
  // acervatorMountTopologies, so the slot is left alone there.
  function fillSlot(target) {
    if (typeof global.acervatorMountTopologies === FUNCTION_KIND) {
      return null;
    }
    var pane = global.acervatorTopologies;
    if (!pane || typeof pane.renderTab !== FUNCTION_KIND) {
      return null;
    }
    if (!target || typeof target.querySelector !== FUNCTION_KIND) {
      return null;
    }
    var slot = target.querySelector(SLOT_SELECTOR);
    if (slot === null || slot.children.length > ZERO) {
      return null;
    }
    pane.renderTab(slot, null);
    if (typeof global.acervatorLoadTopologies === FUNCTION_KIND) {
      global.acervatorLoadTopologies().then(function () {
        pane.renderTab(slot, null);
      });
    }
    return slot;
  }

  function renderScreen(target, model) {
    var drawn = draw(target, element(Screen, { model: payloadOr(model) }));
    fillSlot(target);
    return drawn;
  }

  // act hands one control press to whatever host is holding the screen.
  function act(key, value) {
    return global.acervatorMarketInspectorAction(key, value);
  }

  function renderTab(target, model) {
    hostTarget = target;
    if (isPlainObject(model)) {
      setScreen(model);
    }
    return renderScreen(target, null);
  }

  function setTab(model) {
    var report = setScreen(model);
    if (hostTarget !== null) {
      renderScreen(hostTarget, null);
    }
    return report;
  }

  function renderPerBot(target, model) {
    return draw(target, element(PerBotView, { model: payloadOr(model) }));
  }

  function forget() {
    held = null;
    screenFaults = [];
    loadFault = null;
    asked = null;
    hostTarget = null;
  }

  // A Qt host replaces this. The shell replaces nothing, so the default
  // takes the press to the bridge itself and redraws from the answer.
  global.acervatorMarketInspectorAction = function (key, value) {
    if (!global.acervator || typeof global.acervator.call !== FUNCTION_KIND) {
      return null;
    }
    var asked = {};
    if (key === STEP_BACK_PART || key === STEP_NEXT_PART) {
      asked[STEP_ZONE_FIELD] = value;
      asked[STEP_FIELD] = key === STEP_BACK_PART ? -ONE : ONE;
    } else if (key === ENTRY_PART) {
      asked[TOGGLE_ZONE_FIELD] = value;
    } else {
      return null;
    }
    return global.acervator.call(METHOD, asked).then(function (model) {
      return setTab(model);
    });
  };

  // The shell draws this screen by its module name; the host reads that name
  // off the script tag running now, so it is written down nowhere.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      method: METHOD,
      render: renderTab,
      load: loadScreen,
      loadError: loadError
    });
  }

  global.acervatorSetMarketInspector = setScreen;
  global.acervatorLoadMarketInspector = loadScreen;
  global.acervatorMarketInspector = {
    method: METHOD,
    renderTab: renderTab,
    setTab: setTab,
    Screen: Screen,
    Split: Split,
    LeftPane: LeftPane,
    FilterRow: FilterRow,
    RefreshButton: RefreshButton,
    ActiveSwitch: ActiveSwitch,
    StatusLine: StatusLine,
    TableGroup: TableGroup,
    ModuleGroup: ModuleGroup,
    ZoneStepper: ZoneStepper,
    StepButton: StepButton,
    DetailLine: DetailLine,
    zoneFor: zoneFor,
    moduleOrder: moduleOrder,
    Grid: Grid,
    BodyRow: BodyRow,
    BodyCell: BodyCell,
    HeadCell: HeadCell,
    TopologySlot: TopologySlot,
    PerBotView: PerBotView,
    PerBotCard: PerBotCard,
    PerBotLabel: PerBotLabel,
    Spacer: Spacer,
    payload: payload,
    declaredFields: declaredFields,
    declaredNames: declaredNames,
    nestedNames: nestedNames,
    field: field,
    bag: bag,
    perBot: perBot,
    perBotOrder: perBotOrder,
    signalOrder: signalOrder,
    pairOrder: pairOrder,
    signalRow: signalRow,
    pairRow: pairRow,
    labelPairs: labelPairs,
    labelCollisions: labelCollisions,
    marksFor: marksFor,
    rebuilt: rebuilt,
    actions: actions,
    timers: timers,
    timerDelays: timerDelays,
    busTopics: busTopics,
    callNames: callNames,
    calls: calls,
    methodName: method,
    slots: slots,
    declarations: declarations,
    stateRules: stateRules,
    styleOf: styleOf,
    keptSheet: keptSheet,
    qtColour: qtColour,
    variableFor: variableFor,
    variableInGroups: variableInGroups,
    colour: colour,
    length: length,
    wrapMode: wrapMode,
    kinds: kinds,
    faults: faults,
    loadError: loadError,
    isLoaded: isLoaded,
    renderScreen: renderScreen,
    renderPerBot: renderPerBot,
    forget: forget
  };
})(window);
