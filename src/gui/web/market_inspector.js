// Draws the Market Inspector screen and its per-bot view from the
// market_inspector.state payload.
(function (global) {
  "use strict";

  var METHOD = "market_inspector.state";

  var ACCESSIBLE_NAME = "accessible_name";
  var ACTIONS = "actions";
  var ATA_SPM = "ata_spm";
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
  var OUTER_MARGINS_PX = "outer_margins_px";
  var OUTER_SPACING_PX = "outer_spacing_px";
  var PAIRS_GROUP_TITLE = "pairs_group_title";
  var PENDING_REFRESH = "pending_refresh";
  var PER_BOT = "per_bot";
  var PER_BOT_MARGINS_PX = "per_bot_margins_px";
  var PER_BOT_SPACING_PX = "per_bot_spacing_px";
  var PER_BOT_VIEW = "per_bot_view";
  var REFRESH_ENABLED = "refresh_enabled";
  var REFRESH_LABEL = "refresh_label";
  var REFRESH_TOOLTIP = "refresh_tooltip";
  var SCAN = "scan";
  var SCHEDULED = "scheduled";
  var SHOW_ACTIVE = "show_active";
  var SHOW_ACTIVE_CHECKED = "show_active_checked";
  var SHOW_ACTIVE_DEFAULT = "show_active_default";
  var SHOW_ACTIVE_LABEL = "show_active_label";
  var SHOW_ACTIVE_TOOLTIP = "show_active_tooltip";
  var SIGNAL_NAMES = "signal_names";
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
    ATA_SPM,
    BUS_TOPICS,
    BUTTON_FONT_WEIGHT,
    BUTTON_PADDING_PX,
    CALL_NAMES,
    CALLS,
    CELLS,
    COLORS,
    ELEMENTS,
    EMITTED,
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
    OUTER_MARGINS_PX,
    OUTER_SPACING_PX,
    PENDING_REFRESH,
    PER_BOT,
    PER_BOT_MARGINS_PX,
    PER_BOT_SPACING_PX,
    PER_BOT_VIEW,
    REFRESH_ENABLED,
    REFRESH_LABEL,
    REFRESH_TOOLTIP,
    SCAN,
    SCHEDULED,
    SHOW_ACTIVE,
    SHOW_ACTIVE_CHECKED,
    SHOW_ACTIVE_DEFAULT,
    SHOW_ACTIVE_LABEL,
    SHOW_ACTIVE_TOOLTIP,
    SIGNAL_NAMES,
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

  // The ATA-SPM control row: the sector field, its class, its four
  // timeframe boxes and Scan Now, published under one bag.
  var SECTOR_PLACEHOLDER = "sector_placeholder";
  var SECTOR_TOOLTIP = "sector_tooltip";
  var SECTOR_MIN_WIDTH_PX = "sector_min_width_px";
  var SCAN_LABEL = "scan_label";
  var SCAN_TOOLTIP = "scan_tooltip";
  var CLASS_TOOLTIP = "class_tooltip";
  var CLASS_WIDTH_PX = "class_width_px";
  var BOX_TOOLTIP_FORMAT = "box_tooltip_format";
  var BOX_ROW_PART = "box_row_part";
  var BOX_WIDTH_PX = "box_width_px";
  var BOX_GRID_WIDTH_PX = "box_grid_width_px";
  var TIMEFRAME_TITLE = "timeframe_title";
  var SECTOR_ROW_PART = "sector_row_part";
  var SCAN_ROW_PART = "scan_row_part";
  var ROW_SPACING_PX = "row_spacing_px";
  var SECTOR_TEXT = "sector_text";
  var SECTOR_CLASS = "sector_class";
  var ASSET_CLASSES = "asset_classes";
  var BOXES = "boxes";
  var FIELD_PADDING_PX = "field_padding_px";
  var FIELD_BORDER_PX = "field_border_px";

  var ATA_SPM_FIELDS = [
    ASSET_CLASSES,
    BOXES,
    BOX_GRID_WIDTH_PX,
    BOX_ROW_PART,
    BOX_TOOLTIP_FORMAT,
    BOX_WIDTH_PX,
    CLASS_TOOLTIP,
    CLASS_WIDTH_PX,
    FIELD_BORDER_PX,
    FIELD_PADDING_PX,
    ROW_SPACING_PX,
    SCAN_LABEL,
    SCAN_ROW_PART,
    SCAN_TOOLTIP,
    SECTOR_CLASS,
    SECTOR_MIN_WIDTH_PX,
    SECTOR_PLACEHOLDER,
    SECTOR_ROW_PART,
    SECTOR_TEXT,
    SECTOR_TOOLTIP,
    TIMEFRAME_TITLE
  ];

  var BAG_FIELDS = {};
  BAG_FIELDS[ACTIONS] = ACTION_FIELDS;
  BAG_FIELDS[ATA_SPM] = ATA_SPM_FIELDS;
  BAG_FIELDS[AGE] = AGE_FIELDS;
  BAG_FIELDS[CELLS] = CELL_FIELDS;
  BAG_FIELDS[COLORS] = COLOR_FIELDS;
  BAG_FIELDS[ELEMENTS] = ELEMENT_FIELDS;
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
    PER_BOT_MARGINS_PX,
    SCHEDULED,
    SPLITTER_SIZES_PX,
    SPLITTER_STRETCH,
    TIMER_DELAYS_MS,
    TOP_ROW_MARGINS_PX
  ];

  // WANTED_BAGS names every top-level field this module walks by key.
  var WANTED_BAGS = [
    ACTIONS,
    AGE,
    ATA_SPM,
    CELLS,
    COLORS,
    ELEMENTS,
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

  // ACROSS_ORIENTATION is the Qt word the splitter orientation reads.
  var ACROSS_ORIENTATION = "Horizontal";

  var FLEX = "flex";
  var FLEX_NONE = "none";
  // Three equally sized rectangles down each side, as the Qt stretch gives.
  var EQUAL_SHARE = "1 1 0";
  var AUTO = "auto";
  var ROW_WAY = "row";
  var COLUMN_WAY = "column";
  var CENTER = "center";
  var FULL = "100%";
  var CLIPPED = "hidden";
  var NO_SELECT = "none";
  var PRE = "pre";
  var PRE_WRAP = "pre-wrap";
  var WRAP = "wrap";
  var NORMAL_WRAP = "normal";
  var RELATIVE = "relative";
  var ABSOLUTE = "absolute";
  var SOLID = "solid";
  var NO_OFFSET = 0;

  var ZERO = Number(EMPTY);
  var ONE = Number(true);
  var TWO = ONE + ONE;
  var THREE = TWO + ONE;
  var FOUR = THREE + ONE;
  var FIVE = FOUR + ONE;

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var A_TAG = "a";
  var STRONG_TAG = "strong";
  var BUTTON_TAG = "button";
  var LABEL_TAG = "label";
  var INPUT_TAG = "input";
  var FIELDSET_TAG = "fieldset";
  var LEGEND_TAG = "legend";

  var SELECT_TAG = "select";
  var OPTION_TAG = "option";
  // The width a Level 1 or Level 1A group takes: the pane, less one gap at
  // the right edge, which is the clearance columns_for leaves the Qt grid.
  var PANE_WIDTH_HEAD = "calc(100% - ";
  var PANE_WIDTH_TAIL = ")";
  var BORDER_BOX = "border-box";
  var SHRINK_ONLY = "0 1 auto";

  var BUTTON_TYPE = "button";
  var CHECKBOX_TYPE = "checkbox";
  var TEXT_TYPE = "text";

  // The token the surface's box tooltip format leaves for the box wording.
  var LABEL_TOKEN = "{label}";

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
  var ZONE_HINT = "hint";
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
  var PUSH_PADDING_PX = "push_padding_px";
  var PUSH_FONT_WEIGHT = "push_font_weight";
  var PUSH_BUTTON_HEIGHT_PX = "push_button_height_px";

  var ATA_ROW_PART = "ata-row";
  var SECTOR_FIELD_PART = "sector-field";
  var CLASS_BOX_PART = "class-box";
  var TIMEFRAME_BOX_PART = "timeframe-box";
  var SCAN_NOW_PART = "scan-now";

  // Phases four, five and six: the bucket row, the settings page and the
  // band strip one waiting post draws.
  var BUCKET = "bucket";
  var BUCKET_ROW_PART = "bucket-row";
  var BUCKET_STRETCH_PART = "bucket-stretch";
  var SETTINGS_PAGE_PART = "settings-page";
  var SETTINGS_ROW_PART = "settings-row";
  var SETTINGS_LABEL_PART = "settings-label";
  var SETTINGS_GROUP_PART = "settings-group";
  var STRIP_TEXT_PART = "strip-text";

  var ZONE_THUMBNAIL = "thumbnail";
  var ZONE_PREVIEW = "preview";
  var ZONE_ACTIONS = "actions";
  var ZONE_VOTE = "vote";
  var ZONE_HEADLINE_WIDTH_PX = "headline_width_px";
  var VOTE_PART = "post-vote";
  var THUMBNAIL_PART = "post-thumbnail";

  var ZONE_PANELS = "panels";
  var PANEL_ROWS = "rows";
  var PANEL_ROW_PART = "row_part";
  var PANEL_GROUP_PART = "group_part";
  var PANEL_LINE_PART = "line_part";
  var PANEL_LINES = "lines";
  var PANEL_LINE_STYLE = "line_style";
  var CHART_SYMBOL = "symbol";

  var CHART_PART = "part";
  var CHART_WIDTH_PX = "width_px";
  var CHART_HEIGHT_PX = "height_px";
  var CHART_MARKS = "marks";
  var CHART_TOOLTIP = "tooltip";
  var STRIP_BOX_STYLE = "box_style";
  var STRIP_TEXT = "text";
  var BUTTON_HEIGHT_PX = "button_height_px";
  var FIELD_HEIGHT_PX = "field_height_px";
  var BUCKET_BUTTON_WIDTH_PX = "bucket_button_width_px";
  var SETTINGS_WIDTH_PX = "settings_width_px";
  var SCAN_WIDTH_PX = "scan_width_px";

  var POST_SELECTED_LABEL = "post_selected_label";
  var POST_SELECTED_TOOLTIP = "post_selected_tooltip";
  var POST_SELECTED_PART = "post_selected_part";
  var POST_ALL_LABEL = "post_all_label";
  var POST_ALL_TOOLTIP = "post_all_tooltip";
  var POST_ALL_PART = "post_all_part";
  var FULL_AUTO_LABEL = "full_auto_label";
  var FULL_AUTO_TOOLTIP = "full_auto_tooltip";
  var FULL_AUTO_PART = "full_auto_part";
  var FULL_AUTO_ON = "full_auto_on";
  var BUCKET_SPACING_PX = "row_spacing_px";
  var BUCKET_SETTINGS = "settings";

  var SETTINGS_OPEN = "open";
  var SETTINGS_LEVEL = "level";
  var LEVEL_ONE_A = "level-1a";
  var SETTINGS_LABEL = "settings_label";
  var SETTINGS_TOOLTIP = "settings_tooltip";
  var SETTINGS_PART = "settings_part";
  var SETTING_PART = "setting_part";
  var VENUE_PART = "venue_part";
  var CATEGORY_PART = "category_part";
  var CONNECT_PART = "connect_part";
  var BACK_PART = "back_part";
  var ZONES_PART = "zones_part";
  var ZONES_TOOLTIP = "zones_tooltip";
  var PAGE_PART = "page_part";
  var MESSAGE_PART = "message_part";
  var TITLE_PART = "title_part";
  var ENDPOINT_PART = "endpoint_part";
  var SCOPES_PART = "scopes_part";
  var SIGN_IN_PART = "sign_in_part";
  var REDIRECT_PART = "redirect_part";
  var REGISTRATION_PART = "registration_part";
  var PREREQUISITE_PART = "prerequisite_part";
  var ACCOUNTS_TITLE = "accounts_title";
  var CATEGORY_TITLE = "category_title";
  var SETTINGS_TITLE = "settings_title";
  var CONNECT_LABEL = "connect_label";
  var CONNECT_TOOLTIP = "connect_tooltip";
  var PAGE_BACK_LABEL = "back_label";
  var PAGE_BACK_TOOLTIP = "back_tooltip";
  var VENUE_TOOLTIP_FORMAT = "venue_tooltip_format";
  var CATEGORY_TOOLTIP_FORMAT = "category_tooltip_format";
  var CREDENTIAL_ROWS = "credential_rows";
  var CATEGORY_ROWS = "category_rows";
  var SETTING_ROWS = "setting_rows";
  var CREDENTIAL_PAGE = "credential";
  var PAGE_TARGET = "target";
  var PAGE_FIELDS = "fields";
  // Which boxes the vault already holds a value for. It names field keys and
  // never a value, so the held wording draws and the characters stay away.
  var PAGE_HELD_FIELDS = "held_fields";
  var PAGE_SCOPES = "scopes";
  var PAGE_SIGN_IN = "sign_in";
  var PAGE_REDIRECT = "redirect";
  var PAGE_MESSAGE = "message";
  // What the message line is drawn in. messageColour picks it, so the page and
  // the window carry the same one.
  var PAGE_MESSAGE_COLOUR = "message_colour";
  // Each is the same line as the plain value above it, split into
  // [words, address] pairs. Only a whole address the venue's own row carries
  // holds an address; every other pair holds an empty one.
  var PAGE_ENDPOINT_LINKS = "endpoint_links";
  var PAGE_REGISTRATION_LINKS = "registration_links";
  var PAGE_PREREQUISITE_LINKS = "prerequisite_links";
  var LINK_PART = "link_part";
  var LINK_COLOUR = "link_colour";
  var HELD_PART = "held_part";
  var HELD_PLACEHOLDER = "held_placeholder";
  var CREDENTIAL_WIDTH_PX = "credential_width_px";
  var SETTING_WIDTH_PX = "setting_width_px";
  var VENUE_WIDTH_PX = "venue_width_px";
  var CATEGORY_WIDTH_PX = "category_width_px";
  var CREDENTIAL_ROW_WIDTH_PX = "credential_row_width_px";
  var SETTING_ROW_WIDTH_PX = "setting_row_width_px";
  var CONNECT_WIDTH_PX = "connect_width_px";
  var BACK_WIDTH_PX = "back_width_px";
  var SETTINGS_LABEL_WIDTH_PX = "label_width_px";
  var SETTINGS_SPACING_PX = "row_spacing_px";
  var PASSWORD_TYPE = "password";
  var TARGET_TOKEN = "{target}";
  var STATE_TOKEN = "{state}";
  var NAME_TOKEN = "{name}";

  var SECTOR_TEXT_FIELD = "sector_text";
  var SECTOR_CLASS_FIELD = "sector_class";
  var TOGGLE_TIMEFRAME_FIELD = "toggle_timeframe";
  var SCAN_NOW_FIELD = "scan_now";

  var STEP_ZONE_FIELD = "step_zone";
  var STEP_FIELD = "step";
  var TOGGLE_ZONE_FIELD = "toggle_zone";
  var PUSH_ACTION_FIELD = "push_action";
  var OPEN_CREDENTIALS_FIELD = "open_credentials";
  var CREDENTIAL_TEXT_FIELD = "credential_text";
  var CREDENTIAL_HELD_FIELD = "credential_held";
  var SET_SETTING_FIELD = "set_setting";
  var PUSH_PARTS = "push_parts";
  var POINTER = "pointer";
  var INHERITED = "inherit";
  var PRE_SPACE = "pre";

  var TOPOLOGY_SLOT = "market-inspector-topologies";
  // The panel name market_inspector_topologies.js registers under.
  var TOPOLOGY_PANEL = "market_inspector_topologies";

  var PART_ATTR = "data-part";
  var STATE_ATTR = "data-scan-state";
  var NAME_ATTR = "data-name";
  var AT_ATTR = "data-at";
  var ENTRIES_ATTR = "data-entries";
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
    } catch {
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

  // ChartMark is one rectangle of a post's chart: a close column, a band
  // rule or the last close. The Qt _PostChart fills the same box.
  function ChartMark(props) {
    var mark = asList(props.mark);
    var style = {
      position: ABSOLUTE,
      left: length(mark[ONE]),
      top: length(mark[TWO]),
      width: length(mark[THREE]),
      height: length(mark[FOUR]),
      backgroundColor: text(mark[FIVE])
    };
    var markProps = { style: style };
    markProps[PART_ATTR] = text(mark[ZERO]);
    return element(DIV_TAG, markProps, null);
  }

  // PostChart is the chart one waiting post carries: its closes, its
  // Bollinger bands and its last close, at thumbnail or at preview size.
  function PostChart(props) {
    var chart = props.chart;
    var frame = styleOf(chart[STRIP_BOX_STYLE]);
    frame.boxSizing = BORDER_BOX;
    frame.position = RELATIVE;
    frame.overflow = CLIPPED;
    frame.flex = FLEX_NONE;
    frame.width = length(chart[CHART_WIDTH_PX]);
    frame.height = length(chart[CHART_HEIGHT_PX]);
    frame.cursor = POINTER;
    var frameProps = { style: frame, title: label(chart[CHART_TOOLTIP]) };
    frameProps[PART_ATTR] = text(chart[CHART_PART]);
    frameProps[NAME_ATTR] = text(chart[CHART_PART]);
    frameProps.onClick = function (event) {
      // The entry toggles on its own click, and this chart sits inside it.
      event.stopPropagation();
      act(THUMBNAIL_PART, true);
    };
    return element(
      DIV_TAG,
      frameProps,
      listField(chart, CHART_MARKS).map(function (mark, at) {
        return element(ChartMark, {
          key: CHART_MARKS + PATH_SPLIT + String(at),
          mark: mark
        });
      })
    );
  }

  // EntryAction is one button under the larger chart: Approve or Decline.
  function EntryAction(props) {
    var row = asList(props.row);
    var skin = props.skin;
    var style = marginStyle(asList(skin[PUSH_PADDING_PX]));
    style.flex = FLEX_NONE;
    style.fontWeight = text(skin[PUSH_FONT_WEIGHT]);
    style.boxSizing = BORDER_BOX;
    style.width = length(row[FOUR]);
    style.height = length(skin[PUSH_BUTTON_HEIGHT_PX]);
    var buttonProps = {
      type: BUTTON_TYPE,
      style: style,
      title: label(row[TWO]),
      disabled: row[THREE] !== true,
      onClick: function (event) {
        // The entry toggles on its own click, and this button sits inside it.
        event.stopPropagation();
        props.act(text(row[ZERO]), true);
      }
    };
    buttonProps[PART_ATTR] = text(row[ZERO]);
    buttonProps[NAME_ATTR] = text(row[ZERO]);
    buttonProps[ARIA_LABEL] = label(row[ONE]);
    return element(BUTTON_TAG, buttonProps, text(row[ONE]));
  }

  // PanelCell is one cell of the Indicator Voting Panel ATA-SMP carries.
  // The Qt _VotingPanel gives its own QLabel the same width and height.
  function PanelCell(props) {
    var cell = asList(props.cell);
    var style = asLabel(styleOf(cell[THREE]), false);
    style.flex = FLEX_NONE;
    style.boxSizing = BORDER_BOX;
    style.width = length(cell[ONE]);
    style.height = length(props.heightPx);
    style.textAlign = CENTER;
    var cellProps = { style: style, title: label(cell[FOUR]) };
    cellProps[PART_ATTR] = text(cell[ZERO]);
    return element(DIV_TAG, cellProps, text(cell[TWO]));
  }

  // PanelRow is one row of that panel: a header row, or one timeframe.
  function PanelRow(props) {
    var row = asList(props.row);
    var style = { display: FLEX, flexDirection: ROW_WAY, flex: FLEX_NONE };
    style.height = length(row[ZERO]);
    var rowProps = { style: style };
    rowProps[PART_ATTR] = text(props.part);
    return element(
      DIV_TAG,
      rowProps,
      asList(row[ONE]).map(function (cell, at) {
        return element(PanelCell, {
          key: String(at),
          cell: cell,
          heightPx: row[ZERO]
        });
      })
    );
  }

  // PanelLine is one gate chain line under the panel of its own asset.
  function PanelLine(props) {
    var lineProps = { style: asLabel(styleOf(props.style), true) };
    lineProps[PART_ATTR] = text(props.part);
    lineProps[NAME_ATTR] = text(asList(props.row)[ZERO]);
    return element(DIV_TAG, lineProps, text(asList(props.row)[ONE]));
  }

  // VotingPanel is the Indicator Voting Panel one scanned asset carries,
  // with that asset's gate chain result under it. It draws only the
  // markets ATA-SMP read; no live bot feeds it.
  function VotingPanel(props) {
    var panel = props.panel;
    var frame = styleOf(panel[STRIP_BOX_STYLE]);
    frame.display = FLEX;
    frame.flexDirection = COLUMN_WAY;
    frame.boxSizing = BORDER_BOX;
    frame.flex = FLEX_NONE;
    frame.width = length(panel[CHART_WIDTH_PX]);
    frame.height = length(panel[CHART_HEIGHT_PX]);
    var frameProps = { style: frame, title: label(panel[CHART_TOOLTIP]) };
    frameProps[PART_ATTR] = text(panel[CHART_PART]);
    frameProps[NAME_ATTR] = text(panel[CHART_PART]);
    var groupProps = {
      style: { display: FLEX, flexDirection: COLUMN_WAY, flex: FLEX_NONE }
    };
    groupProps[PART_ATTR] = text(panel[PANEL_GROUP_PART]);
    groupProps[NAME_ATTR] = text(panel[CHART_SYMBOL]);
    return element(
      DIV_TAG,
      groupProps,
      element(
        DIV_TAG,
        frameProps,
        listField(panel, PANEL_ROWS).map(function (row, at) {
          return element(PanelRow, {
            key: PANEL_ROWS + PATH_SPLIT + String(at),
            row: row,
            part: panel[PANEL_ROW_PART]
          });
        })
      ),
      listField(panel, PANEL_LINES).map(function (row, at) {
        return element(PanelLine, {
          key: PANEL_LINES + PATH_SPLIT + String(at),
          row: row,
          part: panel[PANEL_LINE_PART],
          style: panel[PANEL_LINE_STYLE]
        });
      })
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
    headlineStyle.flex = SHRINK_ONLY;
    headlineStyle.minWidth = ZERO;
    headlineStyle.boxSizing = BORDER_BOX;
    headlineStyle.width = length(view[ZONE_HEADLINE_WIDTH_PX]);
    var headlineProps = { style: headlineStyle };
    headlineProps[PART_ATTR] = HEADLINE_PART;
    headlineProps[NAME_ATTR] = text(view[ZONE_KEY]);
    var badgeStyle = styleOf(view[ZONE_BADGE_STYLE]);
    badgeStyle.whiteSpace = PRE_SPACE;
    var badgeProps = { style: badgeStyle };
    badgeProps[PART_ATTR] = ENTRY_BADGE_PART;
    var vote = asList(view[ZONE_VOTE]);
    var voteStyle = asLabel(styleOf(vote[ONE]), false);
    var voteProps = { style: voteStyle };
    voteProps[PART_ATTR] = VOTE_PART;
    voteProps[NAME_ATTR] = text(view[ZONE_KEY]);
    var metaProps = { style: asLabel(styleOf(skin[META_STYLE]), true) };
    metaProps[PART_ATTR] = ENTRY_META_PART;
    var methodProps = { style: asLabel(styleOf(skin[METHOD_STYLE]), true) };
    methodProps[PART_ATTR] = ENTRY_METHOD_PART;
    var hintProps = { style: asLabel(styleOf(skin[HINT_STYLE]), true) };
    hintProps[PART_ATTR] = ENTRY_HINT_PART;
    var thumbnail = objectField(view, ZONE_THUMBNAIL);
    var preview = objectField(view, ZONE_PREVIEW);
    var actionRowStyle = { display: FLEX, flexDirection: ROW_WAY, flex: FLEX_NONE };
    actionRowStyle.gap = length(skin[ENTRY_SPACING_PX]);
    var actionRowProps = { style: actionRowStyle };
    actionRowProps[PART_ATTR] = ZONE_ACTIONS;
    var stripTextProps = {
      style: asLabel(styleOf(skin[DETAIL_STYLE]), true)
    };
    stripTextProps[PART_ATTR] = STRIP_TEXT_PART;
    stripTextProps[NAME_ATTR] = STRIP_TEXT_PART;
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
            owns(thumbnail, CHART_PART)
              ? element(PostChart, { key: ZONE_THUMBNAIL, chart: thumbnail })
              : null,
            element(DIV_TAG, headlineProps, text(view[ZONE_HEADLINE])),
            vote.length > ZERO
              ? element(SPAN_TAG, voteProps, text(vote[ZERO]))
              : null,
            text(view[ZONE_BADGE])
              ? element(SPAN_TAG, badgeProps, text(view[ZONE_BADGE]))
              : null,
            element(Spacer, { key: ENTRY_HEAD_PART, part: ENTRY_HEAD_PART })
          ),
          text(view[ZONE_META])
            ? element(DIV_TAG, metaProps, text(view[ZONE_META]))
            : null,
          text(view[ZONE_METHOD])
            ? element(DIV_TAG, methodProps, text(view[ZONE_METHOD]))
            : null,
          owns(preview, CHART_PART)
            ? element(PostChart, { key: ZONE_PREVIEW, chart: preview })
            : null,
          owns(preview, CHART_PART)
            ? element(DIV_TAG, stripTextProps, text(preview[STRIP_TEXT]))
            : null,
          listField(view, ZONE_ACTIONS).length > ZERO
            ? element(
                DIV_TAG,
                actionRowProps,
                listField(view, ZONE_ACTIONS).map(function (row, at) {
                  return element(EntryAction, {
                    key: ZONE_ACTIONS + PATH_SPLIT + String(at),
                    skin: skin,
                    act: press,
                    row: row
                  });
                }),
                element(Spacer, {
                  key: BUCKET_STRETCH_PART,
                  part: BUCKET_STRETCH_PART
                })
              )
            : null,
          listField(view, ZONE_PANELS).map(function (panel, at) {
            return element(VotingPanel, {
              key: ZONE_PANELS + PATH_SPLIT + String(at),
              panel: panel
            });
          }),
          listField(view, ZONE_DETAIL).map(function (row, at) {
            return element(DetailLine, {
              key: DETAIL_PART + PATH_SPLIT + String(at),
              skin: skin,
              row: row
            });
          }),
          view[ZONE_HINT] === true
            ? element(DIV_TAG, hintProps, text(skin[HINT_TEXT]))
            : null
        )
      )
    );
  }

  // fieldStyle is the themed QLineEdit and QComboBox box: the theme's own
  // padding and its 1 px border, over a fixed width.
  function fieldStyle(skin, widthField) {
    var style = marginStyle(asList(skin[FIELD_PADDING_PX]));
    style.flex = FLEX_NONE;
    style.boxSizing = BORDER_BOX;
    style.width = length(skin[widthField]);
    style.height = length(skin[FIELD_HEIGHT_PX]);
    style.borderWidth = length(skin[FIELD_BORDER_PX]);
    style.borderStyle = SOLID;
    style.font = INHERITED;
    return style;
  }

  // SectorField is where the operator names a sector to scan.
  function SectorField(props) {
    var skin = props.skin;
    var style = fieldStyle(skin, SECTOR_MIN_WIDTH_PX);
    // The field takes the row's slack, so every control right of it sits
    // where the pane edge puts it rather than where the labels end.
    style.flex = ONE;
    style.width = undefined;
    style.minWidth = length(skin[SECTOR_MIN_WIDTH_PX]);
    var fieldProps = {
      type: TEXT_TYPE,
      style: style,
      value: text(skin[SECTOR_TEXT]),
      placeholder: label(skin[SECTOR_PLACEHOLDER]),
      title: label(skin[SECTOR_TOOLTIP]),
      onChange: function (event) {
        act(SECTOR_FIELD_PART, event.target.value);
      }
    };
    fieldProps[PART_ATTR] = SECTOR_FIELD_PART;
    fieldProps[ARIA_LABEL] = label(skin[SECTOR_PLACEHOLDER]);
    return element(INPUT_TAG, fieldProps);
  }

  // ClassBox picks the asset class, which is what sets the four timeframes.
  function ClassBox(props) {
    var skin = props.skin;
    var style = fieldStyle(skin, CLASS_WIDTH_PX);
    var boxProps = {
      style: style,
      value: text(skin[SECTOR_CLASS]),
      title: label(skin[CLASS_TOOLTIP]),
      onChange: function (event) {
        act(CLASS_BOX_PART, event.target.value);
      }
    };
    boxProps[PART_ATTR] = CLASS_BOX_PART;
    boxProps[ARIA_LABEL] = label(skin[CLASS_TOOLTIP]);
    return element(
      SELECT_TAG,
      boxProps,
      asList(skin[ASSET_CLASSES]).map(function (name) {
        return element(
          OPTION_TAG,
          { key: text(name), value: text(name) },
          text(name)
        );
      })
    );
  }

  // TimeframeButton is one of the four timeframes the next scan runs on. It
  // draws on while that timeframe is ticked, the way a Level 1 button does.
  function TimeframeButton(props) {
    var skin = props.skin;
    var row = asList(props.row);
    return element(PushButton, {
      key: text(row[ZERO]),
      model: props.model,
      part: TIMEFRAME_BOX_PART,
      name: text(row[ZERO]),
      label: text(row[ONE]),
      tooltip: label(skin[BOX_TOOLTIP_FORMAT]).replace(LABEL_TOKEN, text(row[ONE])),
      width: skin[BOX_WIDTH_PX],
      height: skin[BUTTON_HEIGHT_PX],
      value: text(row[ZERO]),
      on: row[TWO] === true
    });
  }

  // ScanNowButton runs phases one to three on the sector named beside it.
  function ScanNowButton(props) {
    var model = props.model;
    var skin = props.skin;
    var buttonStyle = marginStyle(listField(model, BUTTON_PADDING_PX));
    buttonStyle.flex = FLEX_NONE;
    buttonStyle.fontWeight = text(model[BUTTON_FONT_WEIGHT]);
    buttonStyle.boxSizing = BORDER_BOX;
    buttonStyle.width = length(skin[SCAN_WIDTH_PX]);
    buttonStyle.height = length(skin[BUTTON_HEIGHT_PX]);
    var buttonProps = {
      type: BUTTON_TYPE,
      style: buttonStyle,
      title: label(skin[SCAN_TOOLTIP]),
      onClick: function () {
        act(SCAN_NOW_PART, true);
      }
    };
    buttonProps[PART_ATTR] = SCAN_NOW_PART;
    buttonProps[ARIA_LABEL] = label(skin[SCAN_LABEL]);
    return element(BUTTON_TAG, buttonProps, text(skin[SCAN_LABEL]));
  }

  // PushButton is one of the buttons phases five and six are pressed with.
  function PushButton(props) {
    var style = marginStyle(listField(props.model, BUTTON_PADDING_PX));
    style.flex = FLEX_NONE;
    style.fontWeight = text(props.model[BUTTON_FONT_WEIGHT]);
    style.boxSizing = BORDER_BOX;
    style.width = length(props.width);
    style.height = length(props.height);
    var buttonProps = {
      type: BUTTON_TYPE,
      style: style,
      title: label(props.tooltip),
      onClick: function () {
        act(text(props.part), props.value === undefined ? true : props.value);
      }
    };
    buttonProps[PART_ATTR] = text(props.part);
    buttonProps[NAME_ATTR] =
      props.name === undefined ? text(props.part) : text(props.name);
    buttonProps[ARIA_LABEL] = label(props.label);
    if (props.on === true) {
      buttonProps[STATE_ATTR] = text(props.part);
    }
    return element(BUTTON_TAG, buttonProps, text(props.label));
  }

  // BucketRow is Post Selected and Post All, with Send Bucket Full Auto on
  // the right of the Ready to Send zone.
  // The three buttons are one width, so this wrap breaks at the count
  // columns_for gives the Qt grid at the same zone width.
  function BucketRow(props) {
    var model = props.model;
    var skin = objectField(model, BUCKET);
    var style = {
      display: FLEX,
      flexDirection: ROW_WAY,
      flexWrap: WRAP,
      flex: FLEX_NONE,
      alignItems: CENTER
    };
    style.gap = length(skin[BUCKET_SPACING_PX]);
    style.width =
      PANE_WIDTH_HEAD + length(skin[BUCKET_SPACING_PX]) + PANE_WIDTH_TAIL;
    var rowProps = { style: style };
    rowProps[PART_ATTR] = BUCKET_ROW_PART;
    return element(
      DIV_TAG,
      rowProps,
      element(PushButton, {
        key: POST_SELECTED_PART,
        model: model,
        part: skin[POST_SELECTED_PART],
        label: skin[POST_SELECTED_LABEL],
        tooltip: skin[POST_SELECTED_TOOLTIP],
        width: skin[BUCKET_BUTTON_WIDTH_PX],
        height: skin[BUTTON_HEIGHT_PX]
      }),
      element(PushButton, {
        key: POST_ALL_PART,
        model: model,
        part: skin[POST_ALL_PART],
        label: skin[POST_ALL_LABEL],
        tooltip: skin[POST_ALL_TOOLTIP],
        width: skin[BUCKET_BUTTON_WIDTH_PX],
        height: skin[BUTTON_HEIGHT_PX]
      }),
      element(PushButton, {
        key: FULL_AUTO_PART,
        model: model,
        part: skin[FULL_AUTO_PART],
        label: skin[FULL_AUTO_LABEL],
        tooltip: skin[FULL_AUTO_TOOLTIP],
        width: skin[BUCKET_BUTTON_WIDTH_PX],
        height: skin[BUTTON_HEIGHT_PX],
        on: skin[FULL_AUTO_ON] === true
      })
    );
  }

  // settingsRowStyle is one line of the settings page: a label of fixed
  // width, then the fields that line carries.
  function settingsRowStyle(page, width) {
    var style = {
      display: FLEX,
      flexDirection: ROW_WAY,
      flex: FLEX_NONE,
      alignItems: CENTER
    };
    style.gap = length(page[SETTINGS_SPACING_PX]);
    if (width !== undefined) {
      style.width = length(page[width]);
    }
    return style;
  }

  function settingsLabel(page, name) {
    var style = asLabel({}, false);
    style.flex = FLEX_NONE;
    style.width = length(page[SETTINGS_LABEL_WIDTH_PX]);
    var labelProps = { style: style };
    labelProps[PART_ATTR] = SETTINGS_LABEL_PART;
    labelProps[NAME_ATTR] = text(name);
    return element(DIV_TAG, labelProps, text(name));
  }

  // VenueButton is one push target's Level 1 button. Pressing it opens that
  // target's Level 1A page, and the button draws on while the vault holds it.
  function VenueButton(props) {
    var page = props.page;
    var row = asList(props.row);
    var name = text(row[ZERO]);
    var tooltip = text(page[VENUE_TOOLTIP_FORMAT])
      .split(TARGET_TOKEN)
      .join(name)
      .split(STATE_TOKEN)
      .join(text(row[TWO]));
    return element(PushButton, {
      key: name,
      model: props.model,
      part: text(page[VENUE_PART]),
      name: name,
      label: name,
      tooltip: tooltip,
      width: page[VENUE_WIDTH_PX],
      height: page[BUTTON_HEIGHT_PX],
      value: name,
      on: row[ONE] === true
    });
  }

  // CategoryButton is one asset class's Level 1 button, on while a scan uses it.
  function CategoryButton(props) {
    var page = props.page;
    var row = asList(props.row);
    var name = text(row[ZERO]);
    return element(PushButton, {
      key: name,
      model: props.model,
      part: text(page[CATEGORY_PART]),
      name: name,
      label: name,
      tooltip: text(page[CATEGORY_TOOLTIP_FORMAT]).split(NAME_TOKEN).join(name),
      width: page[CATEGORY_WIDTH_PX],
      height: page[BUTTON_HEIGHT_PX],
      value: name,
      on: row[ONE] === true
    });
  }

  // sectionTitle heads one Level 1 group, so a reader can tell the three apart.
  function sectionTitle(page, title) {
    var titleProps = { style: asLabel({}, false) };
    titleProps[PART_ATTR] = text(page[TITLE_PART]);
    titleProps[NAME_ATTR] = label(title);
    return element(DIV_TAG, titleProps, label(title));
  }

  // wrapAt is a row of cells that breaks at a published width, so the page
  // and the Qt grid put the same count on one line.
  function wrapAt(page, part, name, width, children) {
    var style = {
      display: FLEX,
      flexDirection: ROW_WAY,
      flexWrap: WRAP,
      flex: FLEX_NONE,
      alignItems: CENTER
    };
    style.gap = length(page[SETTINGS_SPACING_PX]);
    style.width = length(page[width]);
    var rowProps = { style: style };
    rowProps[PART_ATTR] = part;
    rowProps[NAME_ATTR] = label(name);
    return element(DIV_TAG, rowProps, asList(children));
  }

  // wrapInPane is a row of cells that breaks at whatever width the pane gives
  // it, holding one gap clear past the last cell so the count is the one
  // columns_for gives the Qt grid at the same pane width.
  function wrapInPane(page, part, name, children) {
    var style = {
      display: FLEX,
      flexDirection: ROW_WAY,
      flexWrap: WRAP,
      flex: FLEX_NONE,
      alignItems: CENTER
    };
    style.gap = length(page[SETTINGS_SPACING_PX]);
    style.width =
      PANE_WIDTH_HEAD + length(page[SETTINGS_SPACING_PX]) + PANE_WIDTH_TAIL;
    var rowProps = { style: style };
    rowProps[PART_ATTR] = part;
    rowProps[NAME_ATTR] = label(name);
    return element(DIV_TAG, rowProps, asList(children));
  }

  // buttonGroup is one Level 1 section: its heading and the buttons under it.
  function buttonGroup(page, title, children) {
    return [
      sectionTitle(page, title),
      wrapInPane(page, SETTINGS_GROUP_PART, title, children)
    ];
  }

  // CredentialField is one box of the open venue's Level 1A page. Nothing
  // typed here is ever drawn back, so no render carries a token. A box the
  // vault holds a value for draws the held wording and stays empty.
  function CredentialField(props) {
    var page = props.page;
    var pair = asList(props.field);
    var wording = props.held
      ? text(page[HELD_PLACEHOLDER])
      : label(pair[ONE]);
    var fieldProps = {
      type: PASSWORD_TYPE,
      style: fieldStyle(page, CREDENTIAL_WIDTH_PX),
      placeholder: wording,
      onInput: function (event) {
        act(text(pair[ZERO]), [
          text(props.target),
          text(pair[ZERO]),
          event.target.value
        ]);
      },
      // A vault write costs about 150 ms, so a box reaches the vault when he
      // leaves it and not on every keystroke.
      onBlur: function () {
        act(text(page[HELD_PART]), [text(props.target), text(pair[ZERO])]);
      }
    };
    fieldProps[PART_ATTR] = text(pair[ZERO]);
    fieldProps[NAME_ATTR] = text(pair[ZERO]) + GAP + text(props.target);
    fieldProps[ARIA_LABEL] = label(pair[ONE]);
    var rowProps = { style: settingsRowStyle(page, CREDENTIAL_ROW_WIDTH_PX) };
    rowProps[PART_ATTR] = SETTINGS_ROW_PART;
    rowProps[NAME_ATTR] = text(pair[ZERO]);
    return element(
      DIV_TAG,
      rowProps,
      settingsLabel(page, pair[ONE]),
      element(INPUT_TAG, fieldProps)
    );
  }

  // pageLine is one read-only line of Level 1A: its address, scopes, message
  // or what the operator must register before any of it works.
  function pageLine(page, part, written, colour) {
    var style = asLabel({}, false);
    style.whiteSpace = NORMAL_WRAP;
    if (colour) {
      style.color = text(colour);
    }
    var lineProps = { style: style };
    lineProps[PART_ATTR] = text(part);
    lineProps[NAME_ATTR] = text(part);
    return element(DIV_TAG, lineProps, text(written));
  }

  // pageLinkLine is one Level 1A line whose addresses are links. A click opens
  // the system browser through the host and never navigates this view.
  function pageLinkLine(page, part, segments) {
    var style = asLabel({}, false);
    style.whiteSpace = NORMAL_WRAP;
    var lineProps = { style: style };
    lineProps[PART_ATTR] = text(part);
    lineProps[NAME_ATTR] = text(part);
    var linkPart = text(page[LINK_PART]);
    var colour = text(page[LINK_COLOUR]);
    return element(
      DIV_TAG,
      lineProps,
      asList(segments).map(function (segment, at) {
        var pair = asList(segment);
        var written = text(pair[ZERO]);
        var address = text(pair[ONE]);
        if (address === EMPTY) {
          return element(SPAN_TAG, { key: part + PATH_SPLIT + String(at) }, written);
        }
        var linkProps = {
          key: part + PATH_SPLIT + String(at),
          href: address,
          style: { color: colour },
          title: address,
          onClick: function (press) {
            press.preventDefault();
            act(linkPart, address);
          }
        };
        linkProps[PART_ATTR] = linkPart;
        linkProps[NAME_ATTR] = address;
        return element(A_TAG, linkProps, written);
      })
    );
  }

  // CredentialPage is Level 1A: one venue, the boxes its own documentation
  // names, Connect, Back, and what the last press answered.
  function CredentialPage(props) {
    var model = props.model;
    var page = props.page;
    var held = objectField(page, CREDENTIAL_PAGE);
    var target = text(held[PAGE_TARGET]);
    var heldFields = listField(held, PAGE_HELD_FIELDS).map(text);
    var style = {
      display: FLEX,
      flexDirection: COLUMN_WAY,
      flex: ONE,
      minHeight: ZERO
    };
    style.gap = length(page[SETTINGS_SPACING_PX]);
    var pageProps = { style: style };
    pageProps[PART_ATTR] = text(page[PAGE_PART]);
    pageProps[NAME_ATTR] = target;
    return element(
      DIV_TAG,
      pageProps,
      sectionTitle(page, target),
      pageLinkLine(page, page[ENDPOINT_PART], held[PAGE_ENDPOINT_LINKS]),
      pageLine(page, page[SCOPES_PART], held[PAGE_SCOPES]),
      pageLine(page, page[SIGN_IN_PART], held[PAGE_SIGN_IN]),
      pageLine(page, page[REDIRECT_PART], held[PAGE_REDIRECT]),
      wrapInPane(
        page,
        SETTINGS_GROUP_PART,
        target,
        listField(held, PAGE_FIELDS).map(function (field, at) {
          return element(CredentialField, {
            key: PAGE_FIELDS + PATH_SPLIT + String(at),
            page: page,
            target: target,
            field: field,
            held: heldFields.indexOf(text(asList(field)[ZERO])) >= ZERO
          });
        })
      ),
      element(
        DIV_TAG,
        { style: settingsRowStyle(page) },
        element(PushButton, {
          key: CONNECT_PART,
          model: model,
          part: text(page[CONNECT_PART]),
          label: text(page[CONNECT_LABEL]),
          tooltip: text(page[CONNECT_TOOLTIP]),
          width: page[CONNECT_WIDTH_PX],
          height: page[BUTTON_HEIGHT_PX],
          on: false
        }),
        element(PushButton, {
          key: BACK_PART,
          model: model,
          part: text(page[BACK_PART]),
          label: text(page[PAGE_BACK_LABEL]),
          tooltip: text(page[PAGE_BACK_TOOLTIP]),
          width: page[BACK_WIDTH_PX],
          height: page[BUTTON_HEIGHT_PX],
          on: false
        })
      ),
      pageLine(
        page,
        page[MESSAGE_PART],
        held[PAGE_MESSAGE],
        held[PAGE_MESSAGE_COLOUR]
      ),
      pageLinkLine(page, page[REGISTRATION_PART], held[PAGE_REGISTRATION_LINKS]),
      pageLinkLine(page, page[PREREQUISITE_PART], held[PAGE_PREREQUISITE_LINKS])
    );
  }

  // SettingRow is one ATA-SPM setting a phase reads.
  function SettingRow(props) {
    var page = props.page;
    var row = asList(props.row);
    var style = fieldStyle(page, SETTING_WIDTH_PX);
    var fieldProps = {
      type: TEXT_TYPE,
      style: style,
      value: text(row[TWO]),
      onChange: function (event) {
        act(text(page[SETTING_PART]), [text(row[ZERO]), event.target.value]);
      }
    };
    fieldProps[PART_ATTR] = text(page[SETTING_PART]);
    fieldProps[NAME_ATTR] = text(row[ZERO]);
    fieldProps[ARIA_LABEL] = label(row[ONE]);
    var rowProps = { style: settingsRowStyle(page, SETTING_ROW_WIDTH_PX) };
    rowProps[PART_ATTR] = SETTINGS_ROW_PART;
    rowProps[NAME_ATTR] = text(row[ZERO]);
    return element(
      DIV_TAG,
      rowProps,
      settingsLabel(page, row[ONE]),
      element(INPUT_TAG, fieldProps)
    );
  }

  // AccountsPage is Level 1: one button per push target, one per asset class,
  // and the four settings a phase reads.
  function AccountsPage(props) {
    var model = props.model;
    var page = props.page;
    var style = {
      display: FLEX,
      flexDirection: COLUMN_WAY,
      flex: ONE,
      minHeight: ZERO
    };
    style.gap = length(page[SETTINGS_SPACING_PX]);
    var pageProps = { style: style };
    pageProps[PART_ATTR] = SETTINGS_GROUP_PART;
    pageProps[NAME_ATTR] = text(page[ACCOUNTS_TITLE]);
    return element(
      DIV_TAG,
      pageProps,
      buttonGroup(
        page,
        page[ACCOUNTS_TITLE],
        listField(page, CREDENTIAL_ROWS).map(function (row) {
          return element(VenueButton, {
            key: text(asList(row)[ZERO]),
            model: model,
            page: page,
            row: row
          });
        })
      ),
      buttonGroup(
        page,
        page[CATEGORY_TITLE],
        listField(page, CATEGORY_ROWS).map(function (row) {
          return element(CategoryButton, {
            key: text(asList(row)[ZERO]),
            model: model,
            page: page,
            row: row
          });
        })
      ),
      sectionTitle(page, page[SETTINGS_TITLE]),
      wrapInPane(
        page,
        SETTINGS_GROUP_PART,
        page[SETTINGS_TITLE],
        listField(page, SETTING_ROWS).map(function (row, at) {
          return element(SettingRow, {
            key: SETTING_ROWS + PATH_SPLIT + String(at),
            page: page,
            row: row
          });
        })
      ),
      element(PushButton, {
        key: ZONES_PART,
        model: model,
        part: text(page[ZONES_PART]),
        label: text(page[PAGE_BACK_LABEL]),
        tooltip: text(page[ZONES_TOOLTIP]),
        width: page[BACK_WIDTH_PX],
        height: page[BUTTON_HEIGHT_PX],
        on: false
      })
    );
  }

  // SettingsPage is what the ATA-SPM zone shows in place of its stepper:
  // Level 1, or the Level 1A page of whichever venue button was pressed.
  function SettingsPage(props) {
    var model = props.model;
    var page = objectField(objectField(model, BUCKET), BUCKET_SETTINGS);
    var style = {
      display: FLEX,
      flexDirection: COLUMN_WAY,
      flex: ONE,
      minHeight: ZERO
    };
    style.gap = length(page[SETTINGS_SPACING_PX]);
    var pageProps = { style: style };
    pageProps[PART_ATTR] = SETTINGS_PAGE_PART;
    pageProps[NAME_ATTR] = text(page[SETTINGS_LEVEL]);
    return element(
      DIV_TAG,
      pageProps,
      text(page[SETTINGS_LEVEL]) === LEVEL_ONE_A
        ? element(CredentialPage, { key: LEVEL_ONE_A, model: model, page: page })
        : element(AccountsPage, { key: SETTINGS_PAGE_PART, model: model, page: page })
    );
  }

  // ataLine is one line of the ATA-SPM scan page, named so a reader can find
  // it, and holding its controls at the column's own spacing.
  function ataLine(skin, part, children) {
    var style = {
      display: FLEX,
      flexDirection: ROW_WAY,
      flex: FLEX_NONE,
      alignItems: CENTER
    };
    style.gap = length(skin[ROW_SPACING_PX]);
    var lineProps = { style: style };
    lineProps[PART_ATTR] = text(part);
    return element(DIV_TAG, lineProps, asList(children));
  }

  // AtaRow is the ATA-SPM scan page: the sector line, the timeframe buttons
  // under their heading, then Scan Now and the way in to Level 1.
  function AtaRow(props) {
    var model = props.model;
    var skin = objectField(model, ATA_SPM);
    var style = {
      display: FLEX,
      flexDirection: COLUMN_WAY,
      flex: FLEX_NONE
    };
    style.gap = length(skin[ROW_SPACING_PX]);
    var rowProps = { style: style };
    rowProps[PART_ATTR] = ATA_ROW_PART;
    return element(
      DIV_TAG,
      rowProps,
      ataLine(skin, skin[SECTOR_ROW_PART], [
        element(SectorField, { key: SECTOR_FIELD_PART, skin: skin }),
        element(ClassBox, { key: CLASS_BOX_PART, skin: skin })
      ]),
      sectionTitle(skin, skin[TIMEFRAME_TITLE]),
      wrapAt(
        skin,
        text(skin[BOX_ROW_PART]),
        skin[TIMEFRAME_TITLE],
        BOX_GRID_WIDTH_PX,
        asList(skin[BOXES]).map(function (row) {
          return element(TimeframeButton, {
            key: TIMEFRAME_BOX_PART + PATH_SPLIT + text(asList(row)[ZERO]),
            model: model,
            skin: skin,
            row: row
          });
        })
      ),
      ataLine(skin, skin[SCAN_ROW_PART], [
        element(ScanNowButton, {
          key: SCAN_NOW_PART,
          model: model,
          skin: skin
        }),
        element(PushButton, {
          key: SETTINGS_PART,
          model: model,
          part: settingsOf(model)[SETTINGS_PART],
          label: settingsOf(model)[SETTINGS_LABEL],
          tooltip: settingsOf(model)[SETTINGS_TOOLTIP],
          width: settingsOf(model)[SETTINGS_WIDTH_PX],
          height: settingsOf(model)[BUTTON_HEIGHT_PX],
          on: settingsOf(model)[SETTINGS_OPEN] === true
        })
      ])
    );
  }

  // The ATA-SPM settings page the bucket publishes.
  function settingsOf(model) {
    return objectField(objectField(model, BUCKET), BUCKET_SETTINGS);
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
      props.hidesStepper === true
        ? null
        : element(ZoneStepper, {
            key: STEPPER_PART,
            skin: objectField(model, STEPPER),
            model: model,
            view: zoneFor(model, entry[ZERO]),
            act: act
          })
    );
  }

  // The three left-side zones, in the order the surface publishes them. The
  // ATA-SPM zone carries the sector row and Opposing Trades the scan row.
  function moduleGroups(model) {
    var keys = listField(model, LEFT_MODULE_KEYS);
    return listField(model, LEFT_MODULES).map(function (entry, at) {
      return element(ModuleGroup, {
        key: MODULE_GROUP_PART + PATH_SPLIT + String(at),
        model: model,
        entry: entry,
        shares: true,
        hidesStepper: false,
        children: zoneContent(model, entry[ZERO], keys)
      });
    });
  }

  // The row one left zone carries above its stepper, or none.
  function zoneContent(model, key, keys) {
    if (key === keys[ZERO]) {
      return [element(AtaRow, { key: ATA_ROW_PART, model: model })];
    }
    if (key === keys[ONE]) {
      return scanContent(model);
    }
    return [];
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
      settingsOf(model)[SETTINGS_OPEN] === true
        ? element(SettingsPage, { key: SETTINGS_PAGE_PART, model: model })
        : moduleGroups(model)
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
      listField(model, RIGHT_ZONES).map(function (entry, at) {
        return element(RightZone, {
          key: MODULE_GROUP_PART + PATH_SPLIT + text(entry[ZERO]),
          model: model,
          entry: entry,
          fills: text(entry[TWO]) === EMPTY,
          children:
            at === ZERO
              ? [element(BucketRow, { key: BUCKET_ROW_PART, model: model })]
              : []
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
      asList(props.children),
      element(ZoneStepper, {
        key: STEPPER_PART,
        skin: objectField(model, STEPPER),
        model: model,
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

  // Screen draws the fleet-wide tab: the six zones across two panes.
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
      if (model[field] === null) {
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
    REFRESH_LABEL,
    SHOW_ACTIVE_LABEL,
    SPLITTER_ORIENTATION,
    STATUS_STYLE,
    STATUS_TEXT,
    STYLE_SHEET
  ];

  var FLAG_FIELDS = [
    EXCHANGE_SOURCE_WIRED,
    PENDING_REFRESH,
    REFRESH_ENABLED,
    SHOW_ACTIVE,
    SHOW_ACTIVE_CHECKED
  ];

  var COUNT_FIELDS = [
    GROUP_SPACING_PX,
    LEFT_SPACING_PX,
    OUTER_SPACING_PX,
    PER_BOT_SPACING_PX,
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
        perBot: allEntries(order)
      },
      held: {
        fields: heldFieldCount(model),
        nested: heldNestedPaths(model).length,
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

  // The key each left-side region carries, in the order it is drawn.
  function moduleOrder() {
    return list(LEFT_MODULES).map(function (entry) {
      return text(asList(entry)[ZERO]);
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
  // The panel host draws it, so an unregistered TOPOLOGY_PANEL names itself
  // in the slot instead of drawing.
  function fillSlot(target) {
    if (typeof global.acervatorMountTopologies === FUNCTION_KIND) {
      return null;
    }
    var host = global.acervatorPanelHost;
    if (!host || typeof host.mount !== FUNCTION_KIND) {
      return null;
    }
    if (!target || typeof target.querySelector !== FUNCTION_KIND) {
      return null;
    }
    var slot = target.querySelector(SLOT_SELECTOR);
    if (slot === null || slot.children.length > ZERO) {
      return null;
    }
    host.mount(TOPOLOGY_PANEL, slot, null);
    if (typeof global.acervatorLoadTopologies === FUNCTION_KIND) {
      global.acervatorLoadTopologies().then(function (model) {
        host.mount(TOPOLOGY_PANEL, slot, model);
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
  // The parts the screen model answers as one push press, and the settings
  // page beside them, both read off the payload the screen holds.
  function bucketHeld() {
    return objectField(held === null ? {} : held.model, BUCKET);
  }

  function settingsHeld() {
    return objectField(bucketHeld(), BUCKET_SETTINGS);
  }

  function pushParts() {
    return listField(bucketHeld(), PUSH_PARTS).map(text);
  }

  function credentialParts() {
    return listField(
      objectField(settingsHeld(), CREDENTIAL_PAGE),
      PAGE_FIELDS
    ).map(function (field) {
      return text(asList(field)[ZERO]);
    });
  }

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
    } else if (key === SECTOR_FIELD_PART) {
      asked[SECTOR_TEXT_FIELD] = value;
    } else if (key === CLASS_BOX_PART) {
      asked[SECTOR_CLASS_FIELD] = value;
    } else if (key === TIMEFRAME_BOX_PART) {
      asked[TOGGLE_TIMEFRAME_FIELD] = value;
    } else if (key === SCAN_NOW_PART) {
      asked[SCAN_NOW_FIELD] = true;
    } else if (pushParts().indexOf(key) >= ZERO) {
      asked[PUSH_ACTION_FIELD] = key;
    } else if (key === settingsHeld()[VENUE_PART]) {
      asked[OPEN_CREDENTIALS_FIELD] = value;
    } else if (key === settingsHeld()[CATEGORY_PART]) {
      asked[SECTOR_CLASS_FIELD] = value;
    } else if (credentialParts().indexOf(key) >= ZERO) {
      asked[CREDENTIAL_TEXT_FIELD] = value;
    } else if (key === settingsHeld()[HELD_PART]) {
      asked[CREDENTIAL_HELD_FIELD] = value;
    } else if (key === settingsHeld()[SETTING_PART]) {
      asked[SET_SETTING_FIELD] = value;
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
    ModuleGroup: ModuleGroup,
    AtaRow: AtaRow,
    SectorField: SectorField,
    ClassBox: ClassBox,
    TimeframeButton: TimeframeButton,
    ScanNowButton: ScanNowButton,
    ZoneStepper: ZoneStepper,
    StepButton: StepButton,
    DetailLine: DetailLine,
    zoneFor: zoneFor,
    moduleOrder: moduleOrder,
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
