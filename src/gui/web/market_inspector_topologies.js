// Draws the topology-proposal pane and its preview screen from the
// market_inspector_topologies.state payload.
(function (global) {
  "use strict";

  var METHOD = "market_inspector_topologies.state";

  var ACTIONS = "actions";
  var ADOPT_REQUESTS = "adopt_requests";
  var ARCHETYPES = "archetypes";
  var BUS_TOPICS = "bus_topics";
  var CALL_NAMES = "call_names";
  var CALLS = "calls";
  var CARD = "card";
  var CARDS = "cards";
  var CONFIRM = "confirm";
  var DEFAULTS = "defaults";
  var DIALOG = "dialog";
  var DISMISSAL = "dismissal";
  var ERROR_TYPES = "error_types";
  var LOGGER = "logger";
  var MARKS = "marks";
  var NOW = "now";
  var PANE = "pane";
  var PERSISTED = "persisted";
  var PREVIEWS = "previews";
  var PROPOSALS = "proposals";
  var SCORE = "score";
  var SCREEN = "screen";
  var SIGNALS = "signals";
  var STEPPER = "stepper";
  var STEPPER_PART = "zone-stepper";
  var PANE_MOUNT_PART = "topologies-pane";
  var PANE_MOUNT_SELECTOR = "[data-part=\"topologies-pane\"]";
  var SLOT_SELECTOR = "[data-part=\"topology-slot\"]";
  var ZONE = "zone";
  var FUNCTION_KIND = "function";
  var STEP_FIELD = "step";
  var EXPAND_FIELD = "expand";
  var REFRESH_FIELD = "refresh";
  var PREVIEW_FIELD = "preview";
  var DISMISS_FIELD = "dismiss";
  var STEP_BACK_PART = "step-back";
  var STEP_NEXT_PART = "step-next";
  var ENTRY_PART = "zone-entry";
  var PUSH_PADDING_PX = "push_padding_px";
  var PUSH_FONT_WEIGHT = "push_font_weight";
  var STATUS_TEXT = "status_text";
  var TIMER_DELAYS_MS = "timer_delays_ms";
  var TIMER_INTERVAL_MS = "timer_interval_ms";
  var TIMER_RUNNING = "timer_running";
  var TIMER_SINGLE_SHOT = "timer_single_shot";
  var TIMER_STARTED_AT_BUILD = "timer_started_at_build";
  var TIMERS = "timers";
  var WARNINGS = "warnings";

  var DECLARED_FIELDS = [
    ACTIONS,
    ADOPT_REQUESTS,
    ARCHETYPES,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CARD,
    CARDS,
    CONFIRM,
    DEFAULTS,
    DIALOG,
    DISMISSAL,
    ERROR_TYPES,
    LOGGER,
    MARKS,
    NOW,
    PANE,
    PERSISTED,
    PREVIEWS,
    PROPOSALS,
    SCORE,
    SCREEN,
    SIGNALS,
    STATUS_TEXT,
    TIMER_DELAYS_MS,
    TIMER_INTERVAL_MS,
    TIMER_RUNNING,
    TIMER_SINGLE_SHOT,
    TIMER_STARTED_AT_BUILD,
    TIMERS,
    WARNINGS
  ];

  var HELD = "held";
  var ORDER = "order";
  var PERSISTED_ORDER = "persisted_order";
  var SETTINGS_KEY = "settings_key";
  var TTL_SECONDS = "ttl_seconds";

  var HIGH = "high";
  var HIGH_COLOR = "high_color";
  var LOW_COLOR = "low_color";
  var MID = "mid";
  var MID_COLOR = "mid_color";

  var CARD_TITLE_MARK = "card_title_mark";
  var CARD_TITLES = "card_titles";
  var PREVIEW_SUMMARIES = "preview_summaries";
  var PREVIEW_TITLES = "preview_titles";
  var EMPHASIS_CLOSE = "emphasis_close";
  var EMPHASIS_OPEN = "emphasis_open";
  var EMPHASIS_SLANT = "emphasis_slant";
  var STRONG_CLOSE = "strong_close";
  var STRONG_OPEN = "strong_open";
  var STRONG_WEIGHT = "strong_weight";

  var LEVELS = "levels";
  var LOAD_FAILED_FORMAT = "load_failed_format";
  var LOAD_NOT_A_DICT_FORMAT = "load_not_a_dict_format";
  var LOAD_RESTORED_FORMAT = "load_restored_format";
  var LOGGER_NAME = "name";
  var PERSIST_FAILED_FORMAT = "persist_failed_format";
  var REFRESH_FAILED_FORMAT = "refresh_failed_format";

  var ADOPT_DISABLED_TOOLTIP = "adopt_disabled_tooltip";
  var ADOPT_TEXT = "adopt_text";
  var ADOPT_TOOLTIP = "adopt_tooltip";
  var ALTERNATING_ROW_COLORS = "alternating_row_colors";
  var BODY_SPACING = "body_spacing";
  var BOT_STATUS_EXISTING = "bot_status_existing";
  var BOT_STATUS_NEW_FORMAT = "bot_status_new_format";
  var BOTS_BOX_TITLE = "bots_box_title";
  var BOTS_COLUMNS = "bots_columns";
  var BOTS_TOOLTIP = "bots_tooltip";
  var CANCEL_IS_DEFAULT = "cancel_is_default";
  var CANCEL_TEXT = "cancel_text";
  var COLUMN_TOTAL = "column_total";
  var GROUP_MARGINS = "group_margins";
  var HEADER_TITLE_FORMAT = "header_title_format";
  var HEADER_TITLE_STYLE = "header_title_style";
  var MIN_HEIGHT = "min_height";
  var MIN_WIDTH = "min_width";
  var NEW_BOT_COLOR = "new_bot_color";
  var NOTE_FORMAT = "note_format";
  var NOTE_STYLE = "note_style";
  var NOTE_WORD_WRAP = "note_word_wrap";
  var RESIZE_MODE = "resize_mode";
  var ROOT_IS_DECORATED = "root_is_decorated";
  var SUMMARY_FORMAT = "summary_format";
  var SUMMARY_STYLE = "summary_style";
  var TITLE_FALLBACK = "title_fallback";
  var WIRE_PCT_FORMAT = "wire_pct_format";
  var WIRES_BOX_TITLE = "wires_box_title";
  var WIRES_COLUMNS = "wires_columns";
  var WIRES_TOOLTIP = "wires_tooltip";

  var ACCESSIBLE_NAME = "accessible_name";
  var BADGE_FORMAT = "badge_format";
  var BADGE_STYLE_FORMAT = "badge_style_format";
  var CLASS_NAME = "class_name";
  var DISMISS_STYLE = "dismiss_style";
  var DISMISS_TEXT = "dismiss_text";
  var DISMISS_TOOLTIP = "dismiss_tooltip";
  var FRAME_SHADOW = "frame_shadow";
  var FRAME_SHAPE = "frame_shape";
  var META_FORMAT = "meta_format";
  var META_STYLE = "meta_style";
  var METHOD_FORMAT = "method_format";
  var METHOD_STYLE = "method_style";
  var PREVIEW_TEXT = "preview_text";
  var PREVIEW_TOOLTIP = "preview_tooltip";
  var SIZE_POLICY = "size_policy";
  var STYLE = "style";
  var TITLE_FORMAT = "title_format";
  var TITLE_WORD_WRAP = "title_word_wrap";

  var EMPTY_STYLE = "empty_style";
  var EMPTY_TEXT = "empty_text";
  // The two sentences empty_proposals_text answers instead of EMPTY_TEXT when
  // the Inspector scan the detector reads has not run or is still running.
  var EMPTY_NO_SCAN_TEXT = "empty_no_scan_text";
  var EMPTY_SCANNING_TEXT = "empty_scanning_text";
  var EMPTY_WORD_WRAP = "empty_word_wrap";
  var FOOTER_STYLE = "footer_style";
  var FOOTER_TEXT = "footer_text";
  var LABEL_CLASS = "label_class";
  var LIST_GROUP_TITLE = "list_group_title";
  var REFRESH_TEXT = "refresh_text";
  var REFRESH_TOOLTIP = "refresh_tooltip";
  var REFRESH_WIDTH_PX = "refresh_width_px";
  var HEADER_WORD_WRAP = "header_word_wrap";
  var SCROLL_FRAME = "scroll_frame";
  var SCROLL_MARGINS = "scroll_margins";
  var SCROLL_SPACING = "scroll_spacing";
  var SCROLL_WIDGET_RESIZABLE = "scroll_widget_resizable";
  var STATUS_COUNT_FORMAT = "status_count_format";
  var STATUS_ERROR_FORMAT = "status_error_format";
  var STATUS_READY = "status_ready";
  var STATUS_STYLE = "status_style";
  var STATUS_UNWIRED = "status_unwired";
  var STRETCH_NAME = "stretch_name";

  var ANSWER = "answer";
  var ASKED = "asked";
  var BUTTONS = "buttons";
  var DEFAULT_BUTTON = "default_button";
  var TEXT_FORMAT = "text_format";
  var YES = "yes";

  var ERROR_TYPE = "error_type";
  var NO_TEXT = "no_text";
  var START_OF_TIME = "start_of_time";

  var MARGINS = "margins";
  var SPACING = "spacing";
  var TITLE = "title";

  var BADGE = "badge";
  var BADGE_STYLE = "badge_style";
  var META = "meta";
  var METHOD_FIELD = "method";

  var ADOPT_ENABLED = "adopt_enabled";
  var BOT_COLORS = "bot_colors";
  var BOT_ROWS = "bot_rows";
  var NOTES = "notes";
  var SUMMARY = "summary";
  var WINDOW_TITLE = "window_title";
  var WIRE_ROWS = "wire_rows";

  // BAG_FIELDS names every nested field this module reads by its bag.
  var BAG_FIELDS = {};
  BAG_FIELDS[DISMISSAL] = [HELD, ORDER, PERSISTED_ORDER, SETTINGS_KEY, TTL_SECONDS];
  BAG_FIELDS[SCORE] = [HIGH, HIGH_COLOR, LOW_COLOR, MID, MID_COLOR];
  BAG_FIELDS[MARKS] = [
    CARD_TITLE_MARK,
    CARD_TITLES,
    EMPHASIS_CLOSE,
    EMPHASIS_OPEN,
    EMPHASIS_SLANT,
    PREVIEW_SUMMARIES,
    PREVIEW_TITLES,
    STRONG_CLOSE,
    STRONG_OPEN,
    STRONG_WEIGHT
  ];
  BAG_FIELDS[LOGGER] = [
    LEVELS,
    LOAD_FAILED_FORMAT,
    LOAD_NOT_A_DICT_FORMAT,
    LOAD_RESTORED_FORMAT,
    LOGGER_NAME,
    PERSIST_FAILED_FORMAT,
    REFRESH_FAILED_FORMAT
  ];
  BAG_FIELDS[DIALOG] = [
    ADOPT_DISABLED_TOOLTIP,
    ADOPT_TEXT,
    ADOPT_TOOLTIP,
    ALTERNATING_ROW_COLORS,
    BADGE_FORMAT,
    BADGE_STYLE_FORMAT,
    BODY_SPACING,
    BOT_STATUS_EXISTING,
    BOT_STATUS_NEW_FORMAT,
    BOTS_BOX_TITLE,
    BOTS_COLUMNS,
    BOTS_TOOLTIP,
    CANCEL_IS_DEFAULT,
    CANCEL_TEXT,
    COLUMN_TOTAL,
    GROUP_MARGINS,
    HEADER_TITLE_FORMAT,
    HEADER_TITLE_STYLE,
    MARGINS,
    MIN_HEIGHT,
    MIN_WIDTH,
    NEW_BOT_COLOR,
    NOTE_FORMAT,
    NOTE_STYLE,
    NOTE_WORD_WRAP,
    RESIZE_MODE,
    ROOT_IS_DECORATED,
    SPACING,
    SUMMARY_FORMAT,
    SUMMARY_STYLE,
    TITLE_FALLBACK,
    TITLE_FORMAT,
    WIRE_PCT_FORMAT,
    WIRES_BOX_TITLE,
    WIRES_COLUMNS,
    WIRES_TOOLTIP
  ];
  BAG_FIELDS[CARD] = [
    ACCESSIBLE_NAME,
    BADGE_FORMAT,
    BADGE_STYLE_FORMAT,
    CLASS_NAME,
    DISMISS_STYLE,
    DISMISS_TEXT,
    DISMISS_TOOLTIP,
    FRAME_SHADOW,
    FRAME_SHAPE,
    MARGINS,
    META_FORMAT,
    META_STYLE,
    METHOD_FORMAT,
    METHOD_STYLE,
    PREVIEW_TEXT,
    PREVIEW_TOOLTIP,
    SIZE_POLICY,
    SPACING,
    STYLE,
    TITLE_FORMAT,
    TITLE_WORD_WRAP
  ];
  BAG_FIELDS[PANE] = [
    EMPTY_NO_SCAN_TEXT,
    EMPTY_SCANNING_TEXT,
    EMPTY_STYLE,
    EMPTY_TEXT,
    EMPTY_WORD_WRAP,
    FOOTER_STYLE,
    FOOTER_TEXT,
    GROUP_MARGINS,
    LABEL_CLASS,
    LIST_GROUP_TITLE,
    MARGINS,
    REFRESH_TEXT,
    REFRESH_TOOLTIP,
    SCROLL_FRAME,
    SCROLL_MARGINS,
    SCROLL_SPACING,
    SCROLL_WIDGET_RESIZABLE,
    SPACING,
    STATUS_COUNT_FORMAT,
    STATUS_ERROR_FORMAT,
    STATUS_READY,
    STATUS_STYLE,
    STATUS_UNWIRED,
    STRETCH_NAME
  ];
  BAG_FIELDS[CONFIRM] = [
    ANSWER,
    ASKED,
    BUTTONS,
    DEFAULT_BUTTON,
    TEXT_FORMAT,
    TITLE,
    YES
  ];
  BAG_FIELDS[DEFAULTS] = [ERROR_TYPE, NO_TEXT, START_OF_TIME];

  // WANTED_LISTS names every top-level field this module walks by index.
  var WANTED_LISTS = [
    ADOPT_REQUESTS,
    BUS_TOPICS,
    CALL_NAMES,
    CALLS,
    CARDS,
    ERROR_TYPES,
    PERSISTED,
    PREVIEWS,
    PROPOSALS,
    SCREEN,
    SIGNALS,
    TIMER_DELAYS_MS,
    WARNINGS
  ];

  // WANTED_BAGS names every top-level field this module walks by key.
  var WANTED_BAGS = [
    ACTIONS,
    ARCHETYPES,
    CARD,
    CONFIRM,
    DEFAULTS,
    DIALOG,
    DISMISSAL,
    LOGGER,
    MARKS,
    PANE,
    SCORE,
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
  var MARK_MISMATCH_FAULT = "mark-mismatch";
  var ROW_WIDTH_FAULT = "row-width";
  var DUPLICATE_NAME_FAULT = "duplicate-name";
  var UNKNOWN_ELEMENT_FAULT = "unknown-element";
  var LOST_ORDER_FAULT = "lost-order";
  var SELF_LINK_FAULT = "self-link";
  var NO_SUCH_NODE_FAULT = "no-such-node";
  var NO_SHEET_SOURCE_FAULT = "no-sheet-source";

  var NULL_KIND = "null";
  var OBJECT_KIND = "object";
  var STRING_KIND = "string";
  var NO_BRIDGE = "the preload bridge is not present";

  // MARKUP_OPEN starts a tag a Qt rich-text label reads as formatting.
  var MARKUP_OPEN = "<";

  var EMPTY = "";
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
  var COLOUR_GROUPS = ["colors"];

  var FLEX = "flex";
  var FLEX_NONE = "none";
  var AUTO = "auto";
  var ROW_WAY = "row";
  var COLUMN_WAY = "column";
  var FULL = "100%";
  var COLLAPSE = "collapse";
  var MIN_CONTENT = "min-content";
  var FIT_CONTENT = "fit-content";
  // The Qt word a header reads when each column takes its own content width.
  var TO_CONTENTS_MODE = "ResizeToContents";
  var CLIPPED = "hidden";
  var NO_SELECT = "none";
  var PRE = "pre";
  var PRE_WRAP = "pre-wrap";
  var INHERITED = "inherit";
  var LEFT_WAY = "left";
  var FLEX_START = "flex-start";
  // Qt's stretch of 1 on two labels: an equal share of the row's free width.
  var SHARED_LINE = "1 1 0";
  var BREAK_WORD = "break-word";

  var ZERO = Number(EMPTY);
  var ONE = Number(true);
  var TWO = ONE + ONE;
  var THREE = TWO + ONE;

  var DIV_TAG = "div";
  var SPAN_TAG = "span";
  var STRONG_TAG = "strong";
  var EMPHASIS_TAG = "em";
  var BUTTON_TAG = "button";
  var FIELDSET_TAG = "fieldset";
  var LEGEND_TAG = "legend";
  var TABLE_TAG = "table";
  var HEAD_TAG = "thead";
  var BODY_TAG = "tbody";
  var TR_TAG = "tr";
  var TH_TAG = "th";
  var TD_TAG = "td";

  var BUTTON_TYPE = "button";

  var PANE_PART = "pane";
  var TOP_ROW_PART = "top-row";
  var REFRESH_PART = "refresh-button";
  var STATUS_PART = "status-line";
  var EMPTY_PART = "empty-label";
  var PREVIEW_BUTTON_PART = "preview-button";
  var DISMISS_BUTTON_PART = "dismiss-button";
  var FOOTER_PART = "footer";

  var MARK_LEAD_PART = "mark-lead";
  var MARK_BODY_PART = "mark-body";
  var MARK_TAIL_PART = "mark-tail";

  var PREVIEW_PART = "preview";
  var PREVIEW_HEADER_PART = "preview-header";
  var PREVIEW_TITLE_PART = "preview-title";
  var HEADER_STRETCH_PART = "header-stretch";
  var PREVIEW_BADGE_PART = "preview-badge";
  var PREVIEW_BODY_PART = "preview-body";
  var TABLE_GROUP_PART = "table-group";
  var GROUP_LEGEND_PART = "group-legend";
  var GRID_PART = "grid";
  var GRID_HEAD_PART = "grid-head";
  var HEAD_ROW_PART = "head-row";
  var HEAD_CELL_PART = "head-cell";
  var GRID_BODY_PART = "grid-body";
  var GRID_ROW_PART = "grid-row";
  var GRID_CELL_PART = "grid-cell";
  var SUMMARY_PART = "summary";
  var NOTE_PART = "note";
  var BUTTON_ROW_PART = "button-row";
  var BUTTON_STRETCH_PART = "button-stretch";
  var CANCEL_PART = "cancel-button";
  var ADOPT_PART = "adopt-button";

  var BOTS_TABLE = "bots";
  var WIRES_TABLE = "wires";

  var TOPOLOGY_SLOT = "market-inspector-topologies";

  var PART_ATTR = "data-part";
  var TABLE_ATTR = "data-table";
  var NAME_ATTR = "data-name";
  var COLUMN_ATTR = "data-column";
  var AT_ATTR = "data-at";
  var ROWS_ATTR = "data-rows";
  var ALTERNATING_ATTR = "data-alternating";
  var SLOT_ATTR = "data-slot";
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
    var name = variableInGroups(value, COLOUR_GROUPS);
    if (name === undefined) {
      return String(value);
    }
    return VAR_OPEN + name + VAR_SPLIT + String(value) + VAR_CLOSE;
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

  // A badge keeps the spaces its format pads the score with; HTML drops them.
  function asBadge(style) {
    style.whiteSpace = PRE;
    return style;
  }

  // Qt draws every push button in the application font.
  function asButton(style) {
    style.font = INHERITED;
    style.flex = FLEX_NONE;
    return style;
  }

  function Spacer(props) {
    var spacerProps = { style: { flex: AUTO } };
    spacerProps[PART_ATTR] = props.part;
    return element(DIV_TAG, spacerProps, null);
  }

  // The three pieces of one marked label, its tag drawn as an element.
  function MarkedLabel(props) {
    var pieces = asList(props.pieces);
    var leadProps = { key: MARK_LEAD_PART };
    leadProps[PART_ATTR] = MARK_LEAD_PART;
    var bodyProps = { key: MARK_BODY_PART, style: props.bodyStyle };
    bodyProps[PART_ATTR] = MARK_BODY_PART;
    var tailProps = { key: MARK_TAIL_PART };
    tailProps[PART_ATTR] = MARK_TAIL_PART;
    var outerProps = { style: props.style };
    outerProps[PART_ATTR] = props.part;
    outerProps[ARIA_LABEL] = label(props.name);
    return element(
      DIV_TAG,
      outerProps,
      element(SPAN_TAG, leadProps, text(pieces[ZERO])),
      element(props.tag, bodyProps, text(pieces[ONE])),
      element(SPAN_TAG, tailProps, text(pieces[TWO]))
    );
  }

  function RefreshButton(props) {
    var pane = objectField(props.model, PANE);
    var style = pushStyle(props.model);
    style.width = length(pane[REFRESH_WIDTH_PX]);
    var buttonProps = {
      type: BUTTON_TYPE,
      style: style,
      title: label(pane[REFRESH_TOOLTIP])
    };
    buttonProps[PART_ATTR] = REFRESH_PART;
    buttonProps[ARIA_LABEL] = label(pane[REFRESH_TEXT]);
    buttonProps.onClick = function () {
      act(REFRESH_PART, null);
    };
    return element(BUTTON_TAG, buttonProps, text(pane[REFRESH_TEXT]));
  }

  // An equal share of what the header row has left, wrapping inside it, which
  // is the share Qt gives the same label at stretch 1.
  function headerLine(pane, sheet) {
    var style = asLabel(styleOf(sheet), pane[HEADER_WORD_WRAP] === true);
    style.flex = SHARED_LINE;
    style.minWidth = ZERO;
    style.overflowWrap = BREAK_WORD;
    return style;
  }

  function StatusLine(props) {
    var model = props.model;
    var pane = objectField(model, PANE);
    var lineProps = { style: headerLine(pane, pane[STATUS_STYLE]) };
    lineProps[PART_ATTR] = STATUS_PART;
    return element(DIV_TAG, lineProps, text(model[STATUS_TEXT]));
  }

  function TopRow(props) {
    var model = props.model;
    var rowProps = {
      style: {
        display: FLEX,
        flexDirection: ROW_WAY,
        flex: FLEX_NONE,
        alignItems: FLEX_START
      }
    };
    rowProps[PART_ATTR] = TOP_ROW_PART;
    rowProps.style.gap = length(objectField(model, PANE)[SPACING]);
    return element(
      DIV_TAG,
      rowProps,
      element(RefreshButton, { key: REFRESH_PART, model: model }),
      element(Footer, { key: FOOTER_PART, model: model }),
      element(StatusLine, { key: STATUS_PART, model: model })
    );
  }

  function Footer(props) {
    var pane = objectField(props.model, PANE);
    var footerProps = { style: headerLine(pane, pane[FOOTER_STYLE]) };
    footerProps[PART_ATTR] = FOOTER_PART;
    return element(DIV_TAG, footerProps, text(pane[FOOTER_TEXT]));
  }

  function EmptyLabel(props) {
    var pane = objectField(props.model, PANE);
    var emptyProps = {
      style: asLabel(styleOf(pane[EMPTY_STYLE]), pane[EMPTY_WORD_WRAP] === true)
    };
    emptyProps[PART_ATTR] = EMPTY_PART;
    return element(DIV_TAG, emptyProps, text(pane[EMPTY_TEXT]));
  }

  // The theme gives QPushButton 8px 20px of padding and a bold face.
  function pushStyle(model, sheet) {
    var skin = objectField(model, STEPPER);
    var style = marginStyle(asList(skin[PUSH_PADDING_PX]));
    var kept = sheet === undefined ? {} : styleOf(sheet);
    Object.keys(kept).forEach(function (name) {
      style[name] = kept[name];
    });
    style.fontWeight = text(skin[PUSH_FONT_WEIGHT]);
    return asButton(style);
  }

  // The Market Inspector screen publishes the stepper every zone draws
  // through, so the pane holds no arrows or expansion of its own.
  function stepperOf() {
    var screen = global.acervatorMarketInspector;
    return screen === undefined ? undefined : screen.ZoneStepper;
  }

  function Pane(props) {
    var model = props.model;
    if (!isPlainObject(model)) {
      return null;
    }
    var pane = objectField(model, PANE);
    var style = boxStyle(asList(pane[MARGINS]), pane[SPACING], COLUMN_WAY);
    style.height = FULL;
    style.flex = ONE;
    style.minHeight = ZERO;
    style.overflow = CLIPPED;
    var paneProps = { style: style };
    paneProps[PART_ATTR] = PANE_PART;
    paneProps[SLOT_ATTR] = TOPOLOGY_SLOT;
    var stepper = stepperOf();
    return element(
      DIV_TAG,
      paneProps,
      element(TopRow, { key: TOP_ROW_PART, model: model }),
      stepper === undefined
        ? null
        : element(stepper, {
            key: STEPPER_PART,
            skin: objectField(model, STEPPER),
            view: objectField(model, ZONE),
            act: act
          })
    );
  }

  // Qt sizes each column to its content and stretches the last one.
  function contentWide(mode, last) {
    return mode === TO_CONTENTS_MODE && !last ? MIN_CONTENT : undefined;
  }

  function HeadCell(props) {
    var style = { textAlign: LEFT_WAY, width: contentWide(props.mode, props.last) };
    var cellProps = { style: style };
    cellProps[PART_ATTR] = HEAD_CELL_PART;
    cellProps[TABLE_ATTR] = props.table;
    cellProps[COLUMN_ATTR] = text(props.name);
    return element(TH_TAG, cellProps, text(props.name));
  }

  function BodyCell(props) {
    var style = {
      color: colour(props.paint),
      width: contentWide(props.mode, props.last)
    };
    var cellProps = { style: style };
    cellProps[PART_ATTR] = GRID_CELL_PART;
    cellProps[COLUMN_ATTR] = text(props.column);
    return element(TD_TAG, cellProps, text(props.body));
  }

  function BodyRow(props) {
    var cells = asList(props.row);
    var paints = asList(props.paints);
    var rowProps = {};
    rowProps[PART_ATTR] = GRID_ROW_PART;
    rowProps[TABLE_ATTR] = props.table;
    rowProps[AT_ATTR] = String(props.at);
    rowProps[NAME_ATTR] = text(props.name);
    return element(
      TR_TAG,
      rowProps,
      props.columns.map(function (column, at) {
        return element(BodyCell, {
          key: String(at),
          column: column,
          body: cells[at],
          paint: paints[at],
          mode: props.mode,
          last: at === props.columns.length - ONE
        });
      })
    );
  }

  function Grid(props) {
    var columns = props.columns;
    var rows = props.rows;
    var gridProps = { style: { borderCollapse: COLLAPSE, width: FULL } };
    gridProps[PART_ATTR] = GRID_PART;
    gridProps[TABLE_ATTR] = props.table;
    gridProps[ROWS_ATTR] = String(rows.length);
    gridProps[ALTERNATING_ATTR] = text(props.alternating);
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
              table: props.table,
              mode: props.mode,
              last: at === columns.length - ONE
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
            row: row,
            table: props.table,
            paints: asList(props.paints)[at],
            columns: columns,
            name: rowNameOf(row, props.keyColumns),
            mode: props.mode,
            at: at
          });
        })
      )
    );
  }

  function TableGroup(props) {
    var model = props.model;
    var dialog = objectField(model, DIALOG);
    var style = marginStyle(asList(dialog[GROUP_MARGINS]));
    style.display = FLEX;
    style.flexDirection = COLUMN_WAY;
    style.flex = ONE;
    style.minWidth = ZERO;
    var groupProps = { style: style, title: label(dialog[props.tipField]) };
    groupProps[PART_ATTR] = TABLE_GROUP_PART;
    groupProps[TABLE_ATTR] = props.table;
    var legendProps = { style: asLabel({}, false) };
    legendProps[PART_ATTR] = GROUP_LEGEND_PART;
    return element(
      FIELDSET_TAG,
      groupProps,
      element(LEGEND_TAG, legendProps, text(dialog[props.titleField])),
      element(Grid, {
        key: GRID_PART,
        table: props.table,
        columns: listField(dialog, props.columnsField),
        rows: asList(props.rows),
        paints: props.paints,
        keyColumns: props.keyColumns,
        mode: dialog[RESIZE_MODE],
        alternating: dialog[ALTERNATING_ROW_COLORS]
      })
    );
  }

  function PreviewHeader(props) {
    var model = props.model;
    var entry = props.entry;
    var dialog = objectField(model, DIALOG);
    var headerProps = { style: { display: FLEX, flexDirection: ROW_WAY } };
    headerProps[PART_ATTR] = PREVIEW_HEADER_PART;
    var badgeProps = {
      key: PREVIEW_BADGE_PART,
      style: asBadge(styleOf(entry[BADGE_STYLE]))
    };
    badgeProps[PART_ATTR] = PREVIEW_BADGE_PART;
    return element(
      DIV_TAG,
      headerProps,
      element(MarkedLabel, {
        key: PREVIEW_TITLE_PART,
        part: PREVIEW_TITLE_PART,
        tag: STRONG_TAG,
        pieces: listField(objectField(model, MARKS), PREVIEW_TITLES)[props.at],
        name: entry[WINDOW_TITLE],
        style: asLabel(styleOf(dialog[HEADER_TITLE_STYLE]), false),
        bodyStyle: { fontWeight: text(objectField(model, MARKS)[STRONG_WEIGHT]) }
      }),
      element(Spacer, { key: HEADER_STRETCH_PART, part: HEADER_STRETCH_PART }),
      element(SPAN_TAG, badgeProps, text(entry[BADGE]))
    );
  }

  function PreviewButtons(props) {
    var dialog = objectField(props.model, DIALOG);
    var entry = props.entry;
    var rowProps = {
      style: { display: FLEX, flexDirection: ROW_WAY, gap: length(dialog[SPACING]) }
    };
    rowProps[PART_ATTR] = BUTTON_ROW_PART;
    var cancelProps = {
      key: CANCEL_PART,
      type: BUTTON_TYPE,
      style: asButton({}),
      autoFocus: dialog[CANCEL_IS_DEFAULT] === true
    };
    cancelProps[PART_ATTR] = CANCEL_PART;
    cancelProps.onClick = function () {
      act(CANCEL_PART, props.at);
    };
    var adoptProps = {
      key: ADOPT_PART,
      type: BUTTON_TYPE,
      style: asButton({}),
      disabled: entry[ADOPT_ENABLED] !== true,
      title: label(entry[ADOPT_TOOLTIP])
    };
    adoptProps[PART_ATTR] = ADOPT_PART;
    adoptProps.onClick = function () {
      act(ADOPT_PART, props.at);
    };
    return element(
      DIV_TAG,
      rowProps,
      element(Spacer, { key: BUTTON_STRETCH_PART, part: BUTTON_STRETCH_PART }),
      element(BUTTON_TAG, cancelProps, text(dialog[CANCEL_TEXT])),
      element(BUTTON_TAG, adoptProps, text(dialog[ADOPT_TEXT]))
    );
  }

  function PreviewNote(props) {
    var dialog = objectField(props.model, DIALOG);
    var noteProps = {
      style: asLabel(styleOf(dialog[NOTE_STYLE]), dialog[NOTE_WORD_WRAP] === true)
    };
    noteProps[PART_ATTR] = NOTE_PART;
    noteProps[AT_ATTR] = String(props.at);
    return element(DIV_TAG, noteProps, text(props.body));
  }

  function Preview(props) {
    var model = props.model;
    var entry = props.entry;
    if (!isPlainObject(model) || !isPlainObject(entry)) {
      return null;
    }
    var dialog = objectField(model, DIALOG);
    var style = boxStyle(asList(dialog[MARGINS]), dialog[SPACING], COLUMN_WAY);
    style.minWidth = length(dialog[MIN_WIDTH]);
    style.minHeight = length(dialog[MIN_HEIGHT]);
    // The Qt screen takes its minimum size, not the width of whatever holds it.
    style.width = FIT_CONTENT;
    style.height = FIT_CONTENT;
    var previewProps = { style: style };
    previewProps[PART_ATTR] = PREVIEW_PART;
    previewProps[ARIA_LABEL] = label(entry[WINDOW_TITLE]);
    var bodyStyle = boxStyle([], dialog[BODY_SPACING], ROW_WAY);
    bodyStyle.flex = ONE;
    bodyStyle.minHeight = ZERO;
    var bodyProps = { style: bodyStyle };
    bodyProps[PART_ATTR] = PREVIEW_BODY_PART;
    return element(
      DIV_TAG,
      previewProps,
      element(PreviewHeader, {
        key: PREVIEW_HEADER_PART,
        model: model,
        entry: entry,
        at: props.at
      }),
      element(
        DIV_TAG,
        bodyProps,
        element(TableGroup, {
          key: BOTS_TABLE,
          model: model,
          table: BOTS_TABLE,
          titleField: BOTS_BOX_TITLE,
          tipField: BOTS_TOOLTIP,
          columnsField: BOTS_COLUMNS,
          rows: entry[BOT_ROWS],
          paints: entry[BOT_COLORS],
          keyColumns: [ZERO]
        }),
        element(TableGroup, {
          key: WIRES_TABLE,
          model: model,
          table: WIRES_TABLE,
          titleField: WIRES_BOX_TITLE,
          tipField: WIRES_TOOLTIP,
          columnsField: WIRES_COLUMNS,
          rows: entry[WIRE_ROWS],
          paints: [],
          keyColumns: [ZERO, ONE]
        })
      ),
      element(MarkedLabel, {
        key: SUMMARY_PART,
        part: SUMMARY_PART,
        tag: EMPHASIS_TAG,
        pieces: listField(objectField(model, MARKS), PREVIEW_SUMMARIES)[props.at],
        name: entry[WINDOW_TITLE],
        style: asLabel(styleOf(dialog[SUMMARY_STYLE]), false),
        bodyStyle: { fontStyle: text(objectField(model, MARKS)[EMPHASIS_SLANT]) }
      }),
      asList(entry[NOTES]).map(function (body, at) {
        return element(PreviewNote, {
          key: String(at),
          model: model,
          body: body,
          at: at
        });
      }),
      element(PreviewButtons, {
        key: BUTTON_ROW_PART,
        model: model,
        entry: entry,
        at: props.at
      })
    );
  }

  // The name a row carries, its key columns kept apart so a repeat shows.
  function rowNameOf(row, keyColumns) {
    var cells = asList(row);
    return JSON.stringify(
      keyColumns.map(function (at) {
        return String(cells[at]);
      })
    );
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
    var cache = objectField(model, DISMISSAL);
    [ORDER, PERSISTED_ORDER].forEach(function (field) {
      if (owns(cache, field) && !Array.isArray(cache[field])) {
        note(DISMISSAL, field, NOT_A_LIST_FAULT, kindOf(cache[field]));
      }
    });
    if (owns(cache, HELD) && !isPlainObject(cache[HELD])) {
      note(DISMISSAL, HELD, NOT_AN_OBJECT_FAULT, kindOf(cache[HELD]));
    }
    var tags = objectField(model, MARKS);
    [CARD_TITLES, PREVIEW_TITLES, PREVIEW_SUMMARIES].forEach(function (field) {
      if (owns(tags, field) && !Array.isArray(tags[field])) {
        note(MARKS, field, NOT_A_LIST_FAULT, kindOf(tags[field]));
      }
    });
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

  var WORD_FIELDS = {};
  WORD_FIELDS[PANE] = [
    EMPTY_TEXT,
    FOOTER_TEXT,
    LABEL_CLASS,
    LIST_GROUP_TITLE,
    REFRESH_TEXT,
    REFRESH_TOOLTIP,
    STATUS_READY,
    STATUS_STYLE,
    STATUS_UNWIRED,
    STRETCH_NAME
  ];
  WORD_FIELDS[DIALOG] = [
    ADOPT_TEXT,
    ADOPT_TOOLTIP,
    BOTS_BOX_TITLE,
    BOTS_TOOLTIP,
    CANCEL_TEXT,
    NEW_BOT_COLOR,
    RESIZE_MODE,
    TITLE_FALLBACK,
    WIRES_BOX_TITLE,
    WIRES_TOOLTIP
  ];
  WORD_FIELDS[CARD] = [
    CLASS_NAME,
    DISMISS_TEXT,
    DISMISS_TOOLTIP,
    FRAME_SHADOW,
    FRAME_SHAPE,
    PREVIEW_TEXT,
    PREVIEW_TOOLTIP,
    STYLE
  ];
  WORD_FIELDS[SCORE] = [HIGH_COLOR, LOW_COLOR, MID_COLOR];
  WORD_FIELDS[MARKS] = [
    EMPHASIS_CLOSE,
    EMPHASIS_OPEN,
    EMPHASIS_SLANT,
    STRONG_CLOSE,
    STRONG_OPEN,
    STRONG_WEIGHT
  ];

  var COUNT_FIELDS = {};
  COUNT_FIELDS[DIALOG] = [BODY_SPACING, MIN_HEIGHT, MIN_WIDTH, SPACING];
  COUNT_FIELDS[CARD] = [SPACING];
  COUNT_FIELDS[PANE] = [SCROLL_SPACING, SPACING];
  COUNT_FIELDS[SCORE] = [HIGH, MID];

  var FLAG_FIELDS = {};
  FLAG_FIELDS[DIALOG] = [
    ALTERNATING_ROW_COLORS,
    CANCEL_IS_DEFAULT,
    NOTE_WORD_WRAP,
    ROOT_IS_DECORATED
  ];
  FLAG_FIELDS[CARD] = [TITLE_WORD_WRAP];
  FLAG_FIELDS[PANE] = [EMPTY_WORD_WRAP, SCROLL_WIDGET_RESIZABLE];

  function checkTypeGroup(model, wanted, against) {
    Object.keys(wanted).forEach(function (where) {
      var bag = objectField(model, where);
      wanted[where].forEach(function (field) {
        checkTypeAgainst(where, field, bag[field], against);
      });
    });
  }

  function checkTypes(model) {
    var dialog = objectField(model, DIALOG);
    checkTypeGroup(model, WORD_FIELDS, objectField(model, DEFAULTS)[NO_TEXT]);
    checkTypeGroup(model, COUNT_FIELDS, dialog[COLUMN_TOTAL]);
    checkTypeGroup(model, FLAG_FIELDS, dialog[ROOT_IS_DECORATED]);
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

  // paints answers whether one declaration survives into a CSS style.
  function paintsCss(one) {
    var alone = String(one.property) + COLON + GAP + String(one.value);
    return Boolean(Object.keys(styleOf(alone)).length);
  }

  function checkSheet(where, field, sheet) {
    declarations(sheet).forEach(function (one) {
      if (qtColour(one.value) !== undefined) {
        note(where, field, QT_COLOUR_FAULT, one.property);
        return;
      }
      if (!paintsCss(one)) {
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

  var SHEET_FIELDS = {};
  SHEET_FIELDS[PANE] = [EMPTY_STYLE, FOOTER_STYLE, STATUS_STYLE];
  SHEET_FIELDS[CARD] = [DISMISS_STYLE, META_STYLE, METHOD_STYLE, STYLE];
  SHEET_FIELDS[DIALOG] = [HEADER_TITLE_STYLE, NOTE_STYLE, SUMMARY_STYLE];

  function checkSheets(model) {
    if (sheetApi() === undefined) {
      note(null, STYLE, NO_SHEET_SOURCE_FAULT, null);
      return;
    }
    Object.keys(SHEET_FIELDS).forEach(function (where) {
      var bag = objectField(model, where);
      SHEET_FIELDS[where].forEach(function (field) {
        checkSheet(where, field, bag[field]);
      });
    });
    listField(model, CARDS).forEach(function (entry, at) {
      checkSheet(CARDS + PATH_SPLIT + String(at), BADGE_STYLE, badgeSheet(entry));
    });
    listField(model, PREVIEWS).forEach(function (entry, at) {
      checkSheet(PREVIEWS + PATH_SPLIT + String(at), BADGE_STYLE, badgeSheet(entry));
    });
  }

  function badgeSheet(entry) {
    return isPlainObject(entry) ? entry[BADGE_STYLE] : undefined;
  }

  function checkColours(model) {
    var ramp = objectField(model, SCORE);
    [HIGH_COLOR, MID_COLOR, LOW_COLOR].forEach(function (name) {
      checkColour(SCORE, name, ramp[name]);
    });
    checkColour(DIALOG, NEW_BOT_COLOR, objectField(model, DIALOG)[NEW_BOT_COLOR]);
    listField(model, PREVIEWS).forEach(function (entry, at) {
      var spot = PREVIEWS + PATH_SPLIT + String(at);
      asList(isPlainObject(entry) ? entry[BOT_COLORS] : []).forEach(function (row) {
        asList(row).forEach(function (paint) {
          checkColour(spot, BOT_COLORS, paint);
        });
      });
    });
  }

  // A marked label is held against the pieces the surface published for it.
  function checkMarked(where, field, carried, pieces, opener, closer) {
    var parts = asList(pieces);
    if (parts.length !== THREE) {
      note(where, field, NOT_A_LIST_FAULT, kindOf(pieces));
      checkMarkup(where, field, carried);
      return;
    }
    var built =
      String(parts[ZERO]) +
      String(opener) +
      String(parts[ONE]) +
      String(closer) +
      String(parts[TWO]);
    if (built !== carried) {
      note(where, field, MARK_MISMATCH_FAULT, built);
    }
    parts.forEach(function (piece, at) {
      checkTypeAgainst(where, field + PATH_SPLIT + String(at), piece, opener);
    });
  }

  function checkMarks(model) {
    var tags = objectField(model, MARKS);
    listField(model, CARDS).forEach(function (entry, at) {
      var spot = CARDS + PATH_SPLIT + String(at);
      var one = isPlainObject(entry) ? entry : {};
      checkMarked(
        spot,
        CARD_TITLES,
        one[TITLE],
        listField(tags, CARD_TITLES)[at],
        tags[STRONG_OPEN],
        tags[STRONG_CLOSE]
      );
      checkMarkup(spot, META, one[META]);
      checkMarkup(spot, METHOD_FIELD, one[METHOD_FIELD]);
      checkMarkup(spot, BADGE, one[BADGE]);
    });
    listField(model, PREVIEWS).forEach(function (entry, at) {
      var spot = PREVIEWS + PATH_SPLIT + String(at);
      var one = isPlainObject(entry) ? entry : {};
      checkMarked(
        spot,
        PREVIEW_TITLES,
        one[TITLE],
        listField(tags, PREVIEW_TITLES)[at],
        tags[STRONG_OPEN],
        tags[STRONG_CLOSE]
      );
      checkMarked(
        spot,
        PREVIEW_SUMMARIES,
        one[SUMMARY],
        listField(tags, PREVIEW_SUMMARIES)[at],
        tags[EMPHASIS_OPEN],
        tags[EMPHASIS_CLOSE]
      );
      checkMarkup(spot, WINDOW_TITLE, one[WINDOW_TITLE]);
      checkMarkup(spot, BADGE, one[BADGE]);
      asList(one[NOTES]).forEach(function (body, where) {
        checkMarkup(spot + PATH_SPLIT + String(where), NOTES, body);
      });
    });
  }

  function checkGrid(model, spot, rows, columnsField, keyColumns) {
    var columns = listField(objectField(model, DIALOG), columnsField);
    var seen = [];
    asList(rows).forEach(function (row, at) {
      var here = spot + PATH_SPLIT + String(at);
      if (!Array.isArray(row)) {
        note(here, columnsField, NOT_A_LIST_FAULT, kindOf(row));
        return;
      }
      if (row.length !== columns.length) {
        note(here, columnsField, ROW_WIDTH_FAULT, row.length);
      }
      var name = rowNameOf(row, keyColumns);
      if (seen.indexOf(name) >= ZERO) {
        note(here, columnsField, DUPLICATE_NAME_FAULT, name);
      }
      seen.push(name);
      row.forEach(function (cell, column) {
        checkMarkup(here + PATH_SPLIT + String(column), columnsField, cell);
      });
    });
  }

  // A wire naming one node twice, or a node the Bots list never carries.
  function checkLinks(model, spot, entry) {
    var assets = asList(entry[BOT_ROWS]).map(function (row) {
      return String(asList(row)[ZERO]);
    });
    asList(entry[WIRE_ROWS]).forEach(function (row, at) {
      var cells = asList(row);
      var here = spot + PATH_SPLIT + String(at);
      var source = String(cells[ZERO]);
      var target = String(cells[ONE]);
      if (cells.length >= TWO && source === target) {
        note(here, WIRE_ROWS, SELF_LINK_FAULT, source);
      }
      [source, target].forEach(function (end) {
        if (cells.length >= TWO && assets.indexOf(end) < ZERO) {
          note(here, WIRE_ROWS, NO_SUCH_NODE_FAULT, end);
        }
      });
    });
  }

  function checkPreviews(model) {
    listField(model, PREVIEWS).forEach(function (entry, at) {
      var spot = PREVIEWS + PATH_SPLIT + String(at);
      if (!isPlainObject(entry)) {
        note(spot, PREVIEWS, NOT_AN_OBJECT_FAULT, kindOf(entry));
        return;
      }
      checkGrid(model, spot, entry[BOT_ROWS], BOTS_COLUMNS, [ZERO]);
      checkGrid(model, spot, entry[WIRE_ROWS], WIRES_COLUMNS, [ZERO, ONE]);
      checkLinks(model, spot, entry);
    });
  }

  // checkScreen walks the screen list, naming an element it cannot draw.
  function checkScreen(model) {
    var pane = objectField(model, PANE);
    var names = [pane[LABEL_CLASS], pane[STRETCH_NAME], objectField(model, CARD)[CLASS_NAME]];
    var cardsNamed = ZERO;
    listField(model, SCREEN).forEach(function (name, at) {
      if (names.indexOf(name) < ZERO) {
        note(SCREEN + PATH_SPLIT + String(at), SCREEN, UNKNOWN_ELEMENT_FAULT, text(name));
        return;
      }
      if (name === objectField(model, CARD)[CLASS_NAME]) {
        cardsNamed += ONE;
      }
    });
    if (cardsNamed !== listField(model, CARDS).length) {
      note(null, SCREEN, ROW_WIDTH_FAULT, cardsNamed);
    }
  }

  // The cache order must be a list, since object keys come back renumbered.
  function checkOrder(model) {
    var cache = objectField(model, DISMISSAL);
    var order = listField(cache, ORDER);
    var keys = Object.keys(objectField(cache, HELD));
    if (order.length !== keys.length) {
      note(DISMISSAL, ORDER, LOST_ORDER_FAULT, order.length);
      return;
    }
    order.forEach(function (name, at) {
      if (!owns(objectField(cache, HELD), String(name))) {
        note(DISMISSAL + PATH_SPLIT + String(at), ORDER, MISSING_FAULT, text(name));
      }
    });
    listField(cache, PERSISTED_ORDER).forEach(function (names, at) {
      var write = asList(listField(model, PERSISTED)[at]);
      var wrote = Object.keys(isPlainObject(write[ONE]) ? write[ONE] : {});
      if (asList(names).length !== wrote.length) {
        note(
          DISMISSAL + PATH_SPLIT + String(at),
          PERSISTED_ORDER,
          LOST_ORDER_FAULT,
          asList(names).length
        );
      }
    });
  }

  function report() {
    var model = held.model;
    return {
      declared: {
        fields: DECLARED_FIELDS.length,
        nested: nestedPaths().length,
        cards: listField(model, CARDS).length,
        previews: listField(model, PREVIEWS).length,
        botCells: declaredCells(model, BOTS_COLUMNS, BOT_ROWS),
        wireCells: declaredCells(model, WIRES_COLUMNS, WIRE_ROWS),
        dismissals: listField(objectField(model, DISMISSAL), ORDER).length
      },
      held: {
        fields: heldFieldCount(model),
        nested: heldNestedPaths(model).length,
        cards: drawnCards(model),
        previews: heldPreviews(model),
        botCells: heldCells(model, BOT_ROWS),
        wireCells: heldCells(model, WIRE_ROWS),
        dismissals: Object.keys(objectField(objectField(model, DISMISSAL), HELD)).length
      },
      faults: screenFaults.slice()
    };
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

  // drawnCards counts the screen entries this module draws as a card.
  function drawnCards(model) {
    var wanted = objectField(model, CARD)[CLASS_NAME];
    return listField(model, SCREEN).filter(function (name) {
      return name === wanted;
    }).length;
  }

  function heldPreviews(model) {
    return listField(model, PREVIEWS).filter(isPlainObject).length;
  }

  function declaredCells(model, columnsField, rowsField) {
    var columns = listField(objectField(model, DIALOG), columnsField).length;
    var rows = ZERO;
    listField(model, PREVIEWS).forEach(function (entry) {
      rows += asList(isPlainObject(entry) ? entry[rowsField] : []).length;
    });
    return columns * rows;
  }

  function heldCells(model, rowsField) {
    var count = ZERO;
    listField(model, PREVIEWS).forEach(function (entry) {
      asList(isPlainObject(entry) ? entry[rowsField] : []).forEach(function (row) {
        count += asList(row).length;
      });
    });
    return count;
  }

  function setPane(model) {
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
    checkSheets(model);
    checkColours(model);
    checkMarks(model);
    checkPreviews(model);
    checkScreen(model);
    checkOrder(model);
    return report();
  }

  // loadPane asks METHOD once, clearing asked so a refusal retries.
  function loadPane(params) {
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
        setPane(model);
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

  // The dismissed ids in the order the pane suppressed them.
  function dismissedOrder() {
    return held === null ? [] : listField(objectField(held.model, DISMISSAL), ORDER);
  }

  function persistedOrder() {
    return held === null
      ? []
      : listField(objectField(held.model, DISMISSAL), PERSISTED_ORDER);
  }

  function cardOrder() {
    return list(PROPOSALS);
  }

  // One card read by the proposal id beside it, not by its position.
  function cardByName(wanted) {
    var found;
    cardOrder().forEach(function (name, at) {
      if (String(name) !== String(wanted) || found !== undefined) {
        return;
      }
      var entry = listField(held.model, CARDS)[at];
      found = isPlainObject(entry) ? copyOf(entry) : undefined;
    });
    return found;
  }

  function rowsOf(at, rowsField) {
    var entry = held === null ? undefined : listField(held.model, PREVIEWS)[at];
    return asList(isPlainObject(entry) ? entry[rowsField] : []);
  }

  function botOrder(at) {
    return rowsOf(at, BOT_ROWS).map(function (row) {
      return asList(row)[ZERO];
    });
  }

  function wireOrder(at) {
    return rowsOf(at, WIRE_ROWS).map(function (row) {
      return asList(row).slice(ZERO, TWO);
    });
  }

  // One preview row read by the name its key columns carry.
  function rowByName(at, rowsField, columnsField, keyColumns, wanted) {
    var found;
    var columns = listField(objectField(held.model, DIALOG), columnsField);
    rowsOf(at, rowsField).forEach(function (row) {
      if (rowNameOf(row, keyColumns) !== wanted || found !== undefined) {
        return;
      }
      found = {};
      columns.forEach(function (name, column) {
        Object.defineProperty(found, String(name), {
          value: asList(row)[column],
          enumerable: true,
          writable: true,
          configurable: true
        });
      });
    });
    return found;
  }

  function botRow(at, wanted) {
    return held === null
      ? undefined
      : rowByName(
          at,
          BOT_ROWS,
          BOTS_COLUMNS,
          [ZERO],
          JSON.stringify([String(wanted)])
        );
  }

  function wireRow(at, source, target) {
    return held === null
      ? undefined
      : rowByName(
          at,
          WIRE_ROWS,
          WIRES_COLUMNS,
          [ZERO, ONE],
          JSON.stringify([String(source), String(target)])
        );
  }

  // Every group and label pair this screen draws, group named first.
  function labelPairs() {
    var found = [];
    if (held === null) {
      return found;
    }
    var dialog = objectField(held.model, DIALOG);
    listField(dialog, BOTS_COLUMNS).forEach(function (name) {
      found.push([dialog[BOTS_BOX_TITLE], name]);
    });
    listField(dialog, WIRES_COLUMNS).forEach(function (name) {
      found.push([dialog[WIRES_BOX_TITLE], name]);
    });
    listField(held.model, PREVIEWS).forEach(function (entry, at) {
      botOrder(at).forEach(function (name) {
        found.push([dialog[BOTS_BOX_TITLE], name]);
      });
      wireOrder(at).forEach(function (pair) {
        asList(pair).forEach(function (name) {
          found.push([dialog[WIRES_BOX_TITLE], name]);
        });
      });
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

  function archetypes() {
    return bag(ARCHETYPES);
  }

  function actions() {
    return bag(ACTIONS);
  }

  function timers() {
    return bag(TIMERS);
  }

  function calls() {
    return list(CALLS);
  }

  function callNames() {
    return list(CALL_NAMES);
  }

  function warnings() {
    return list(WARNINGS);
  }

  function busTopics() {
    return list(BUS_TOPICS);
  }

  function signals() {
    return list(SIGNALS);
  }

  function method() {
    return METHOD;
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

  function renderPane(target, model) {
    return draw(target, element(Pane, { model: payloadOr(model) }));
  }

  // act hands one button press to whatever host is holding the pane.
  function act(key, name) {
    return global.acervatorTopologiesAction(key, name);
  }

  // The element the pane draws into: the Market Inspector's own slot once the
  // screen has drawn one, and the host the caller gave until then. The shell
  // mounts this panel beside the screen, so without this the pane draws into
  // a host the tab bar hides whichever tab is selected.
  function paneHost(target) {
    var slot = global.document.querySelector(SLOT_SELECTOR);
    if (slot === null) {
      return target;
    }
    var found = slot.querySelector(PANE_MOUNT_SELECTOR);
    if (found === null) {
      found = global.document.createElement(DIV_TAG);
      found.setAttribute(PART_ATTR, PANE_MOUNT_PART);
      found.style.height = FULL;
      found.style.display = FLEX;
      found.style.flexDirection = COLUMN_WAY;
      found.style.minHeight = ZERO;
      slot.appendChild(found);
    }
    return found;
  }

  // seat moves the pane into the slot once the screen has drawn one, and
  // empties whatever it was drawn into before.
  function seat() {
    if (hostTarget === null) {
      return null;
    }
    var wanted = paneHost(hostTarget);
    if (wanted !== hostTarget) {
      draw(hostTarget, null);
      hostTarget = wanted;
      renderPane(hostTarget, null);
    }
    return hostTarget;
  }

  function renderTab(target, model) {
    var mount = paneHost(target);
    if (mount === target && target !== null && target !== undefined) {
      // Names this element as the pane's mount, so a host that moves it into
      // the slot itself is found again instead of a second mount being made.
      target.setAttribute(PART_ATTR, PANE_MOUNT_PART);
    }
    hostTarget = mount;
    if (isPlainObject(model)) {
      setPane(model);
    }
    return renderPane(hostTarget, null);
  }

  function setTab(model) {
    var report = setPane(model);
    if (hostTarget !== null) {
      renderPane(hostTarget, null);
    }
    return report;
  }

  function renderPreview(target, at, model) {
    var carried = payloadOr(model);
    return draw(
      target,
      element(Preview, {
        model: carried,
        at: at === undefined ? ZERO : at,
        entry: listField(carried, PREVIEWS)[at === undefined ? ZERO : at]
      })
    );
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
  global.acervatorTopologiesAction = function (key, name) {
    if (!global.acervator || typeof global.acervator.call !== FUNCTION_KIND) {
      return null;
    }
    var asked = {};
    if (key === STEP_BACK_PART) {
      asked[STEP_FIELD] = -ONE;
    } else if (key === STEP_NEXT_PART) {
      asked[STEP_FIELD] = ONE;
    } else if (key === ENTRY_PART) {
      asked[EXPAND_FIELD] = true;
    } else if (key === REFRESH_PART) {
      asked[REFRESH_FIELD] = true;
    } else if (key === PREVIEW_BUTTON_PART) {
      asked[PREVIEW_FIELD] = name;
    } else if (key === DISMISS_BUTTON_PART) {
      asked[DISMISS_FIELD] = name;
    } else {
      return null;
    }
    return global.acervator.call(METHOD, asked).then(function (model) {
      return setTab(model);
    });
  };

  // The shell draws this pane by its module name and asks the bridge for its
  // state; it names no bridge method the application serves a tab from, so
  // the tab bar gives it no tab of its own.
  if (global.acervatorPanelHost) {
    global.acervatorPanelHost.register({
      render: renderTab,
      load: loadPane,
      loadError: loadError
    });
  }

  global.acervatorSetTopologies = setPane;
  global.acervatorLoadTopologies = loadPane;
  global.acervatorTopologies = {
    method: method,
    renderTab: renderTab,
    setTab: setTab,
    seat: seat,
    Pane: Pane,
    TopRow: TopRow,
    RefreshButton: RefreshButton,
    StatusLine: StatusLine,
    EmptyLabel: EmptyLabel,
    Footer: Footer,
    MarkedLabel: MarkedLabel,
    Preview: Preview,
    PreviewHeader: PreviewHeader,
    PreviewButtons: PreviewButtons,
    PreviewNote: PreviewNote,
    TableGroup: TableGroup,
    Grid: Grid,
    BodyRow: BodyRow,
    BodyCell: BodyCell,
    HeadCell: HeadCell,
    Spacer: Spacer,
    payload: payload,
    declaredFields: declaredFields,
    declaredNames: declaredNames,
    nestedNames: nestedNames,
    field: field,
    bag: bag,
    list: list,
    dismissedOrder: dismissedOrder,
    persistedOrder: persistedOrder,
    cardOrder: cardOrder,
    cardByName: cardByName,
    botOrder: botOrder,
    wireOrder: wireOrder,
    botRow: botRow,
    wireRow: wireRow,
    rowNameOf: rowNameOf,
    labelPairs: labelPairs,
    labelCollisions: labelCollisions,
    archetypes: archetypes,
    actions: actions,
    timers: timers,
    calls: calls,
    callNames: callNames,
    warnings: warnings,
    busTopics: busTopics,
    signals: signals,
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
    renderPane: renderPane,
    renderPreview: renderPreview,
    forget: forget
  };
})(window);
